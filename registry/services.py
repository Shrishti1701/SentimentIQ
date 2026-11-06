"""Transactional validation and lifecycle services for the registry."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from registry.models import (
    Company,
    CompanyAlias,
    ExchangeListing,
    ListingSymbolHistory,
    RegistrySnapshot,
    RegistryRowAudit,
)


class RegistryValidationError(ValueError):
    pass


def _overlap(
    left_from: object,
    left_to: object,
    right_from: object,
    right_to: object,
) -> bool:
    if left_to is not None and right_from is not None and left_to <= right_from:
        return False
    if right_to is not None and left_from is not None and right_to <= left_from:
        return False
    return True


class RegistryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def validate_parent(self, company: Company) -> None:
        seen: set[int] = {company.id} if company.id is not None else set()
        current = company.parent
        while current is not None:
            if current.id in seen or current is company:
                raise RegistryValidationError("registry company parent relationship contains a cycle")
            seen.add(current.id if current.id is not None else -id(current))
            current = current.parent

    def validate_aliases(self, alias: CompanyAlias) -> None:
        if alias.company_id is None:
            raise RegistryValidationError("company alias must reference a persisted company")
        existing = self.session.scalars(
            select(CompanyAlias).where(
                CompanyAlias.company_id == alias.company_id,
                CompanyAlias.normalized_alias_key == alias.normalized_alias_key,
                CompanyAlias.id != alias.id if alias.id is not None else True,
            )
        )
        for other in existing:
            if _overlap(alias.valid_from, alias.valid_to, other.valid_from, other.valid_to):
                raise RegistryValidationError("overlapping alias periods are not allowed for the same company and key")

    def validate_listing(self, listing: ExchangeListing) -> None:
        existing = self.session.scalars(
            select(ExchangeListing).where(
                ExchangeListing.exchange_code == listing.exchange_code,
                ExchangeListing.symbol == listing.symbol,
                ExchangeListing.series == listing.series,
                ExchangeListing.id != listing.id if listing.id is not None else True,
            )
        )
        for other in existing:
            if other.security_id == listing.security_id and other.company_id == listing.company_id:
                continue
            if _overlap(listing.valid_from, listing.valid_to, other.valid_from, other.valid_to):
                raise RegistryValidationError("overlapping listing periods are not allowed for the same identity")

    def validate_symbol_history(self, history: ListingSymbolHistory) -> None:
        if history.listing_id is None:
            return
        existing = self.session.scalars(
            select(ListingSymbolHistory).where(
                ListingSymbolHistory.listing_id == history.listing_id,
                ListingSymbolHistory.id != history.id if history.id is not None else True,
            )
        )
        for other in existing:
            if other.effective_date == history.effective_date:
                raise RegistryValidationError("multiple symbol transitions cannot have the same effective date")

    def transition_snapshot(self, snapshot: RegistrySnapshot, target_state: str) -> None:
        allowed = {
            "building": {"validated"},
            "validated": {"published", "superseded"},
            "published": {"superseded"},
            "superseded": set(),
        }
        if target_state not in allowed.get(snapshot.snapshot_state, set()):
            raise RegistryValidationError(
                f"invalid registry snapshot transition: {snapshot.snapshot_state} -> {target_state}"
            )

        if target_state == "validated":
            self._validate_snapshot_completeness(snapshot)
        elif target_state == "published":
            self._validate_snapshot_publication(snapshot)
            published = self.session.scalars(
                select(RegistrySnapshot).where(
                    RegistrySnapshot.snapshot_state == "published",
                    RegistrySnapshot.id != snapshot.id,
                    RegistrySnapshot.dataset_scope == snapshot.dataset_scope,
                )
            ).all()
            for old in published:
                old.snapshot_state = "superseded"
            snapshot.published_at = datetime.now(timezone.utc)
            snapshot.snapshot_state = "published"
            return
        elif target_state == "superseded":
            snapshot.published_at = snapshot.published_at

        snapshot.snapshot_state = target_state

    def _validate_snapshot_completeness(self, snapshot: RegistrySnapshot) -> None:
        if not snapshot.sources:
            raise RegistryValidationError("validated snapshots require at least one source")
        try:
            manifest = json.loads(snapshot.source_manifest_json)
            counts = json.loads(snapshot.validation_counts_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise RegistryValidationError("snapshot JSON fields must contain valid JSON") from exc
        if not isinstance(manifest, list) or not manifest:
            raise RegistryValidationError("validated snapshots require a non-empty source manifest")
        if not isinstance(counts, dict):
            raise RegistryValidationError("snapshot validation counts must be a JSON object")

    def _validate_snapshot_publication(self, snapshot: RegistrySnapshot) -> None:
        self._validate_snapshot_completeness(snapshot)
        unresolved = self.session.scalars(
            select(RegistryRowAudit).where(
                RegistryRowAudit.snapshot_id == snapshot.id,
                RegistryRowAudit.validation_outcome.in_(("rejected", "quarantined", "requires_review")),
            )
        ).all()
        if unresolved:
            raise RegistryValidationError("snapshot contains rows requiring resolution before publication")
