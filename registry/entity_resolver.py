"""Production registry-backed Stage 3 entity resolution."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence.entity_contracts import (
    CandidateEvidence,
    DeterministicIdFactory,
    EntityCandidate,
    EntityMention,
    EntityResolutionResult,
    ResolutionStatus,
)
from registry.models import (
    CompanyAlias,
    ListingSymbolHistory,
    RegistrySnapshot,
    RegistryCompany,
    RegistryExchangeListing,
    RegistrySecurity,
    RegistryRowAudit,
    RegistrySource,
)
from intelligence.contracts import VerifiedEffectiveTime


PRODUCTION_RESOLVER_VERSION = "registry-resolver-v1"


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).upper()


def contract_company_id(registry_company_id: str) -> str:
    return DeterministicIdFactory().create("COMPANY", {"registry_id": registry_company_id})


def contract_security_id(registry_security_id: str) -> str:
    return DeterministicIdFactory().create("SECURITY", {"registry_id": registry_security_id})


class ProductionRegistryResolver:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _published_snapshot(self, scope: str) -> RegistrySnapshot | None:
        return self.session.scalar(
            select(RegistrySnapshot).where(
                RegistrySnapshot.dataset_scope == scope,
                RegistrySnapshot.snapshot_state == "published",
            ).order_by(RegistrySnapshot.id.desc())
        )

    def _registry_version(self) -> str:
        snapshots = self.session.scalars(
            select(RegistrySnapshot).where(RegistrySnapshot.snapshot_state == "published").order_by(
                RegistrySnapshot.dataset_scope, RegistrySnapshot.id
            )
        ).all()
        return "|".join(snapshot.external_id for snapshot in snapshots) or "registry:unpublished"

    def resolve(
        self,
        mention: EntityMention,
        *,
        effective_time=None,
        id_factory: DeterministicIdFactory | None = None,
    ) -> EntityResolutionResult:
        factory = id_factory or DeterministicIdFactory()
        if effective_time is not None:
            if not isinstance(effective_time, VerifiedEffectiveTime):
                raise TypeError("effective_time must be a VerifiedEffectiveTime")
            if effective_time.document_ref != mention.document_ref:
                raise ValueError("verified effective time belongs to a different document")
        candidates = self._candidates(mention, effective_time=effective_time)
        candidates = self._sorted_unique_candidates(candidates)

        if len(candidates) == 1:
            status: ResolutionStatus = "resolved"
            selected = candidates[0].entity_id
            rationale = _resolved_rationale(candidates[0].match_basis)
        elif len(candidates) > 1:
            status = "ambiguous"
            selected = None
            rationale = "multiple_company_candidates"
        else:
            status = "unresolved"
            selected = None
            rationale = "no_registry_match"

        resolution_id = factory.resolution_id(
            document_ref=mention.document_ref,
            mention_id=mention.mention_id,
            registry_version=self._registry_version(),
            resolver_version=PRODUCTION_RESOLVER_VERSION,
            status=status,
            selected_entity_id=selected,
            rationale_code=rationale,
            candidates=tuple(candidates),
            review_only_candidates=(),
        )
        return EntityResolutionResult(
            resolution_id=resolution_id,
            document_ref=mention.document_ref,
            mention_id=mention.mention_id,
            status=status,
            selected_entity_id=selected,
            candidates=tuple(candidates),
            review_only_candidates=(),
            rationale_code=rationale,
            registry_version=self._registry_version(),
            resolver_version=PRODUCTION_RESOLVER_VERSION,
        )

    def _candidates(self, mention: EntityMention, *, effective_time=None) -> list[EntityCandidate]:
        current = self._published_snapshot("NSE_CURRENT_LISTINGS")
        if current is None:
            return []

        text = _normalize(mention.surface_text)
        if mention.observation_kind == "security_identifier_candidate":
            if mention.security_namespace == "ISIN":
                return self._isin_candidates(text, current)
            if mention.security_namespace in ("NSE", "BSE"):
                candidates = self._symbol_candidates(
                    text, mention.security_namespace, current, effective_time=effective_time
                )
                historical = self._published_snapshot("NSE_HISTORICAL_CHANGES")
                if historical is not None:
                    candidates.extend(self._historical_symbol_candidates(
                        text, mention.security_namespace, historical, effective_time=effective_time
                    ))
                return candidates
            return []

        candidates = self._name_candidates(text, current, effective_time=effective_time)
        historical = self._published_snapshot("NSE_HISTORICAL_CHANGES")
        if historical is not None:
            candidates.extend(self._historical_name_candidates(
                text, historical, effective_time=effective_time
            ))
        return candidates

    def _isin_candidates(self, isin: str, snapshot: RegistrySnapshot) -> list[EntityCandidate]:
        securities = self.session.scalars(
            select(RegistrySecurity).where(
                RegistrySecurity.isin == isin,
                RegistrySecurity.isin_verified.is_(True),
            )
        ).unique().all()
        candidates: list[EntityCandidate] = []
        for security in securities:
            if security.issuer_company_id is None:
                continue
            company = security.issuer_company
            if company is None:
                continue
            security_ref = contract_security_id(security.external_id)
            provenance = f"registry-source:{snapshot.external_id}:security:{security.external_id}"
            candidates.append(EntityCandidate(
                contract_company_id(company.external_id),
                "verified_security_issuer_mapping",
                supporting_security_ids=(security_ref,),
                supporting_identifier_refs=(f"ISIN:{isin}",),
                provenance_refs=(provenance,),
                supporting_evidence=(CandidateEvidence(
                    "verified_security_issuer_mapping", provenance, True
                ),),
                rank=1,
            ))
        return candidates

    def _symbol_candidates(
        self,
        symbol: str,
        exchange: str,
        snapshot: RegistrySnapshot,
        *,
        effective_time=None,
    ) -> list[EntityCandidate]:
        if exchange != "NSE":
            return []
        listings = self.session.scalars(
            select(RegistryExchangeListing).where(
                RegistryExchangeListing.exchange_code == exchange,
                RegistryExchangeListing.symbol == symbol,
            )
        ).unique().all()
        candidates: list[EntityCandidate] = []
        for listing in listings:
            if listing.company is None:
                continue
            if effective_time is not None:
                effective_date = effective_time.instant.date()
                if listing.valid_from is not None and effective_date < listing.valid_from:
                    continue
                if listing.valid_to is not None and effective_date >= listing.valid_to:
                    continue
            provenance = f"registry-source:{snapshot.external_id}:listing:{listing.external_id}"
            candidate = EntityCandidate(
                contract_company_id(listing.company.external_id),
                "verified_security_issuer_mapping",
                supporting_security_ids=(
                    (contract_security_id(listing.security.external_id),)
                    if listing.security is not None
                    else ()
                ),
                supporting_identifier_refs=(f"NSE:{listing.symbol}",),
                provenance_refs=(provenance,),
                supporting_evidence=(CandidateEvidence(
                    "verified_security_issuer_mapping", provenance, True
                ),),
                rank=1,
            )
            candidates.append(candidate)
        return candidates

    def _name_candidates(
        self, text: str, snapshot: RegistrySnapshot, *, effective_time=None
    ) -> list[EntityCandidate]:
        candidates: list[EntityCandidate] = []
        companies = self.session.scalars(select(RegistryCompany)).all()
        for company in companies:
            provenance = f"registry-source:{snapshot.external_id}:company:{company.external_id}"
            if _normalize(company.canonical_legal_name) == text:
                candidates.append(EntityCandidate(
                    contract_company_id(company.external_id),
                    "legal_name",
                    provenance_refs=(provenance,),
                    supporting_evidence=(CandidateEvidence("legal_name", provenance, True),),
                    rank=1,
                ))
            aliases = [
                alias for alias in company.aliases
                if alias.valid_to is None and _normalize(alias.normalized_alias_key) == text
                and alias.source.snapshot_id == snapshot.id
            ]
            if effective_time is not None:
                effective_date = effective_time.instant.date()
                aliases = [
                    alias for alias in aliases
                    if (alias.valid_from is None or alias.valid_from <= effective_date)
                    and (alias.valid_to is None or effective_date < alias.valid_to)
                ]
            if aliases:
                provenance = f"registry-source:{aliases[0].source.external_id}:alias:{aliases[0].source_row_number or aliases[0].id}"
                candidates.append(EntityCandidate(
                    contract_company_id(company.external_id),
                    "verified_alias",
                    provenance_refs=(provenance,),
                    supporting_evidence=(CandidateEvidence("verified_alias", provenance, True),),
                    rank=1,
                ))
        return candidates

    def _historical_name_candidates(
        self, text: str, snapshot: RegistrySnapshot, *, effective_time=None
    ) -> list[EntityCandidate]:
        aliases = self.session.scalars(
            select(CompanyAlias).join(RegistrySource, CompanyAlias.source_id == RegistrySource.id).where(
                RegistrySource.snapshot_id == snapshot.id,
                CompanyAlias.normalized_alias_key == text,
            )
        ).unique().all()
        candidates: list[EntityCandidate] = []
        for alias in aliases:
            if alias.source.snapshot_id != snapshot.id:
                continue
            if effective_time is not None:
                effective_date = effective_time.instant.date()
                if alias.valid_from is not None and effective_date < alias.valid_from:
                    continue
            accepted = self.session.scalar(
                select(RegistryRowAudit.id).where(
                    RegistryRowAudit.snapshot_id == snapshot.id,
                    RegistryRowAudit.source_id == alias.source_id,
                    RegistryRowAudit.source_row_number == alias.source_row_number,
                    RegistryRowAudit.validation_outcome == "accepted",
                )
            )
            if accepted is None:
                continue
            provenance = f"registry-source:{alias.source.external_id}:row:{alias.source_row_number}"
            candidates.append(EntityCandidate(
                contract_company_id(alias.company.external_id),
                "verified_alias",
                provenance_refs=(provenance,),
                supporting_evidence=(CandidateEvidence("verified_alias", provenance, True),),
                rank=1,
            ))
        return candidates

    def _historical_symbol_candidates(
        self, symbol: str, exchange: str, snapshot: RegistrySnapshot, *, effective_time=None
    ) -> list[EntityCandidate]:
        if exchange != "NSE":
            return []
        histories = self.session.scalars(
            select(ListingSymbolHistory).join(
                RegistrySource, ListingSymbolHistory.source_id == RegistrySource.id
            ).where(
                RegistrySource.snapshot_id == snapshot.id,
                ListingSymbolHistory.previous_symbol == symbol,
                ListingSymbolHistory.review_status == "accepted",
                ListingSymbolHistory.listing_id.is_not(None),
            )
        ).unique().all()
        candidates: list[EntityCandidate] = []
        for history in histories:
            if history.listing is None or history.listing.company is None:
                continue
            if effective_time is not None and effective_time.instant.date() < history.effective_date:
                continue
            accepted = self.session.scalar(
                select(RegistryRowAudit.id).where(
                    RegistryRowAudit.snapshot_id == snapshot.id,
                    RegistryRowAudit.source_id == history.source_id,
                    RegistryRowAudit.source_row_number == history.source_row_number,
                    RegistryRowAudit.validation_outcome == "accepted",
                )
            )
            if accepted is None:
                continue
            provenance = f"registry-source:{history.source.external_id}:row:{history.source_row_number}"
            candidate = EntityCandidate(
                contract_company_id(history.listing.company.external_id),
                "verified_security_issuer_mapping",
                supporting_identifier_refs=(f"NSE:{symbol}",),
                provenance_refs=(provenance,),
                supporting_evidence=(CandidateEvidence(
                    "verified_security_issuer_mapping", provenance, True
                ),),
                rank=1,
            )
            candidates.append(candidate)
        return candidates

    @staticmethod
    def _sorted_unique_candidates(candidates: list[EntityCandidate]) -> list[EntityCandidate]:
        by_entity: dict[str, EntityCandidate] = {}
        for candidate in candidates:
            by_entity.setdefault(candidate.entity_id, candidate)
        return sorted(by_entity.values(), key=lambda candidate: (candidate.rank, candidate.entity_id))


def _resolved_rationale(match_basis: str) -> str:
    return {
        "legal_name": "unique_legal_name",
        "verified_alias": "unique_verified_alias",
        "verified_security_issuer_mapping": "verified_security_issuer_mapping",
    }[match_basis]
