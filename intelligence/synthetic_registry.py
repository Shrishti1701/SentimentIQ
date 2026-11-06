"""Tiny, versioned synthetic company/security registry for contract testing only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Literal

from intelligence.contracts import VerifiedEffectiveTime, _VERIFIED_TIME_TOKEN
from intelligence.entity_contracts import CandidateEvidence, DeterministicIdFactory, EntityCandidate, EntityMention, EntityResolutionResult


@dataclass(frozen=True)
class Validity:
    valid_from: datetime | None
    valid_to: datetime | None

    def __post_init__(self) -> None:
        for name, value in (("valid_from", self.valid_from), ("valid_to", self.valid_to)):
            if value is not None and not isinstance(value, datetime):
                raise TypeError(f"{name} must be a datetime or None")
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{name} must be timezone-aware")
        if self.valid_from is not None and self.valid_to is not None and self.valid_from >= self.valid_to:
            raise ValueError("valid_from must be earlier than valid_to")

    def contains(self, instant: datetime) -> bool:
        if not isinstance(instant, datetime):
            raise TypeError("resolution instant must be a datetime")
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("resolution instant must be timezone-aware")
        return (self.valid_from is None or self.valid_from <= instant) and (self.valid_to is None or instant < self.valid_to)


@dataclass(frozen=True)
class SyntheticCompany:
    entity_id: str
    legal_name: str
    legal_name_validity: Validity
    aliases: tuple[tuple[str, Validity, str], ...] = ()
    parent_entity_id: str | None = None
    historical_legal_names: tuple[tuple[str, Validity, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.entity_id, str) or not self.entity_id.startswith("COMPANY:") or not self.entity_id[len("COMPANY:"):].strip():
            raise ValueError("company entity IDs must use COMPANY: namespace")
        if not isinstance(self.legal_name, str) or not self.legal_name.strip():
            raise ValueError("legal_name must be non-empty")
        if not isinstance(self.legal_name_validity, Validity):
            raise TypeError("legal_name_validity must be Validity")
        if not isinstance(self.aliases, tuple):
            raise TypeError("aliases must be an immutable tuple")
        if not isinstance(self.historical_legal_names, tuple):
            raise TypeError("historical_legal_names must be an immutable tuple")
        for record in self.aliases:
            if not isinstance(record, tuple) or len(record) != 3 or not isinstance(record[1], Validity):
                raise TypeError("each alias must be (name, Validity, provenance_ref)")
            if not all(isinstance(part, str) and part.strip() for part in (record[0], record[2])):
                raise ValueError("alias and provenance must be non-empty")
        for record in self.historical_legal_names:
            if not isinstance(record, tuple) or len(record) != 3 or not isinstance(record[1], Validity):
                raise TypeError("each historical legal name must be (name, Validity, provenance_ref)")
            if not all(isinstance(part, str) and part.strip() for part in (record[0], record[2])):
                raise ValueError("historical legal name and provenance must be non-empty")
        if self.parent_entity_id is not None and not self.parent_entity_id.startswith("COMPANY:"):
            raise ValueError("parent relationship must reference a company entity ID")


@dataclass(frozen=True)
class SyntheticSecurity:
    security_id: str
    namespace: Literal["NSE", "BSE", "ISIN"]
    identifier: str
    issuer_entity_id: str
    issuer_mapping_verified: bool
    validity: Validity
    provenance_ref: str

    def __post_init__(self) -> None:
        if not isinstance(self.security_id, str) or not self.security_id.startswith("SECURITY:") or not self.security_id[len("SECURITY:"):].strip():
            raise ValueError("security IDs must use SECURITY: namespace")
        if self.issuer_entity_id.startswith("SECURITY:") or not self.issuer_entity_id.startswith("COMPANY:"):
            raise ValueError("security issuer must reference a company entity ID")
        if self.namespace not in ("NSE", "BSE", "ISIN"):
            raise ValueError("namespace must be NSE, BSE, or ISIN")
        if type(self.issuer_mapping_verified) is not bool:
            raise TypeError("issuer_mapping_verified must be an actual bool")
        if not isinstance(self.validity, Validity):
            raise TypeError("validity must be Validity")
        if not isinstance(self.identifier, str) or not isinstance(self.provenance_ref, str) or not all((self.identifier.strip(), self.provenance_ref.strip())):
            raise ValueError("security identifier and provenance must be non-empty")


@dataclass(frozen=True)
class ResolutionDecision:
    status: Literal["resolved", "ambiguous", "unresolved"]
    candidates: tuple[EntityCandidate, ...]
    review_only_candidates: tuple[EntityCandidate, ...]
    selected_entity_id: str | None
    rationale_code: str


class SyntheticRegistry:
    """Exact-match fixture registry; not a production resolver or data source."""

    __slots__ = ("version", "companies", "securities", "_locked")

    def __setattr__(self, name, value):
        if getattr(self, "_locked", False):
            raise AttributeError("SyntheticRegistry is immutable after validation")
        object.__setattr__(self, name, value)

    def __init__(self, version: str, companies: tuple[SyntheticCompany, ...], securities: tuple[SyntheticSecurity, ...]):
        if not isinstance(version, str) or not version.strip():
            raise ValueError("registry version must be non-empty")
        if not isinstance(companies, tuple) or any(not isinstance(c, SyntheticCompany) for c in companies):
            raise TypeError("companies must be a tuple of SyntheticCompany")
        if not isinstance(securities, tuple) or any(not isinstance(s, SyntheticSecurity) for s in securities):
            raise TypeError("securities must be a tuple of SyntheticSecurity")
        self.version = version
        self.companies = MappingProxyType({c.entity_id: c for c in companies})
        self.securities = MappingProxyType({s.security_id: s for s in securities})
        if len(self.companies) != len(companies) or len(self.securities) != len(securities):
            raise ValueError("registry IDs must be unique")
        for security in securities:
            if security.issuer_entity_id not in self.companies:
                raise ValueError("security issuer must exist in the registry")
        for company in companies:
            if company.parent_entity_id is not None and company.parent_entity_id not in self.companies:
                raise ValueError("parent company must exist in the registry")
            if company.parent_entity_id == company.entity_id:
                raise ValueError("company cannot be its own parent")
        for company in companies:
            seen: set[str] = set()
            current = company
            while current.parent_entity_id is not None:
                if current.entity_id in seen:
                    raise ValueError("parent relationships cannot contain cycles")
                seen.add(current.entity_id)
                current = self.companies[current.parent_entity_id]
        self._locked = True

    def resolve(self, mention: EntityMention, *, resolver_version: str, effective_time: VerifiedEffectiveTime | None) -> ResolutionDecision:
        """Resolve exact synthetic records only; unknown time never implies historical validity."""
        effective_at = None
        if effective_time is not None:
            if not isinstance(effective_time, VerifiedEffectiveTime) or effective_time._token is not _VERIFIED_TIME_TOKEN:
                raise TypeError("effective_time must come from verified_effective_time_from_input()")
            if effective_time.document_ref != mention.document_ref:
                raise ValueError("verified effective time belongs to a different document")
            effective_at = effective_time.instant
        if mention.observation_kind == "security_identifier_candidate":
            if mention.security_namespace is None:
                return ResolutionDecision("unresolved", (), (), None, "invalid_or_unverified_identifier")
            matches = [s for s in self.securities.values() if s.namespace == mention.security_namespace and s.identifier == mention.surface_text]
            if not matches:
                return ResolutionDecision("unresolved", (), (), None, "no_registry_match")
            if effective_at is None and any(s.validity.valid_from is not None or s.validity.valid_to is not None for s in matches):
                return ResolutionDecision("unresolved", (), (), None, "historical_validity_unknown")
            current = sorted((s for s in matches if effective_at is None or s.validity.contains(effective_at)), key=lambda item: (item.issuer_entity_id, item.security_id))
            if len(current) > 1:
                return ResolutionDecision("unresolved", (), (), None, "conflicting_registry_evidence")
            if any(not s.issuer_mapping_verified for s in current):
                return ResolutionDecision("unresolved", (), (), None, "conflicting_registry_evidence")
            candidates = tuple(EntityCandidate(
                entity_id=s.issuer_entity_id,
                match_basis="verified_security_issuer_mapping",
                supporting_security_ids=(s.security_id,),
                supporting_identifier_refs=(f"{s.namespace}:{s.identifier}",),
                provenance_refs=(s.provenance_ref,),
                supporting_evidence=(CandidateEvidence("verified_security_issuer_mapping", s.provenance_ref, True),),
                rank=i + 1,
            ) for i, s in enumerate(current))
        else:
            # Names and aliases also require an explicit instant when their registry interval is historical.
            candidates_list: list[EntityCandidate] = []
            historical_validity_unknown = False
            for company in self.companies.values():
                name_records = ((company.legal_name, company.legal_name_validity, f"{self.version}:{company.entity_id}:legal_name"),) + company.historical_legal_names
                for legal_name, validity, provenance in name_records:
                    if mention.surface_text != legal_name:
                        continue
                    if effective_at is None and (validity.valid_from is not None or validity.valid_to is not None):
                        historical_validity_unknown = True
                    elif effective_at is None or validity.contains(effective_at):
                        candidates_list.append(EntityCandidate(company.entity_id, "legal_name", provenance_refs=(provenance,), supporting_evidence=(CandidateEvidence("legal_name", provenance, True),), rank=1))
                for alias, validity, source in company.aliases:
                    if mention.surface_text == alias:
                        if effective_at is None and (validity.valid_from is not None or validity.valid_to is not None):
                            historical_validity_unknown = True
                        elif effective_at is None or validity.contains(effective_at):
                            candidates_list.append(EntityCandidate(company.entity_id, "verified_alias", provenance_refs=(source,), supporting_evidence=(CandidateEvidence("verified_alias", source, True),), rank=1))
            if historical_validity_unknown:
                return ResolutionDecision("unresolved", (), (), None, "historical_validity_unknown")
            # A legal name and alias for same entity count as one plausible identity; retain first exact basis.
            unique: dict[str, EntityCandidate] = {}
            for candidate in candidates_list:
                unique.setdefault(candidate.entity_id, candidate)
            candidates = tuple(sorted(unique.values(), key=lambda c: c.entity_id))

        by_entity: dict[str, EntityCandidate] = {}
        for candidate in candidates:
            by_entity.setdefault(candidate.entity_id, candidate)
        candidates = tuple(sorted(by_entity.values(), key=lambda c: c.entity_id))
        if len(candidates) == 1:
            return ResolutionDecision("resolved", candidates, (), candidates[0].entity_id, "unique_legal_name" if candidates[0].match_basis == "legal_name" else "unique_verified_alias" if candidates[0].match_basis == "verified_alias" else "verified_security_issuer_mapping")
        if len(candidates) > 1:
            return ResolutionDecision("ambiguous", candidates, (), None, "multiple_company_candidates")
        return ResolutionDecision("unresolved", (), (), None, "no_registry_match")

    def resolve_result(self, mention: EntityMention, *, resolver_version: str, effective_time: VerifiedEffectiveTime | None, id_factory: DeterministicIdFactory) -> EntityResolutionResult:
        decision = self.resolve(mention, resolver_version=resolver_version, effective_time=effective_time)
        result_id = id_factory.resolution_id(
            document_ref=mention.document_ref,
            mention_id=mention.mention_id,
            registry_version=self.version,
            resolver_version=resolver_version,
            status=decision.status,
            selected_entity_id=decision.selected_entity_id,
            rationale_code=decision.rationale_code,
            candidates=decision.candidates,
            review_only_candidates=decision.review_only_candidates,
        )
        return EntityResolutionResult(
            resolution_id=result_id,
            document_ref=mention.document_ref,
            mention_id=mention.mention_id,
            status=decision.status,
            selected_entity_id=decision.selected_entity_id,
            candidates=decision.candidates,
            review_only_candidates=decision.review_only_candidates,
            rationale_code=decision.rationale_code,
            registry_version=self.version,
            resolver_version=resolver_version,
        )

    def validate_result(self, mention: EntityMention, result: EntityResolutionResult, *, effective_time: VerifiedEffectiveTime | None) -> None:
        """Verify a result against this synthetic registry; references alone are not authority."""
        if not isinstance(result, EntityResolutionResult):
            raise TypeError("result must be EntityResolutionResult")
        expected = self.resolve_result(
            mention,
            resolver_version=result.resolver_version,
            effective_time=effective_time,
            id_factory=DeterministicIdFactory(),
        )
        if result != expected:
            raise ValueError("resolution result does not match this synthetic registry's verified records")


def default_synthetic_registry() -> SyntheticRegistry:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = datetime(2030, 1, 1, tzinfo=timezone.utc)
    interval = Validity(start, end)
    companies = (
        SyntheticCompany("COMPANY:SYN-001", "Synthetic Meridian Holdings", interval, (("Synthetic Meridian", interval, "fixture:alias:meridian"),)),
        SyntheticCompany("COMPANY:SYN-002", "Synthetic Meridian Logistics", interval, parent_entity_id="COMPANY:SYN-001"),
        SyntheticCompany("COMPANY:SYN-003", "Synthetic Cedar Industries", interval),
    )
    securities = (
        SyntheticSecurity("SECURITY:SYN-001", "NSE", "SYNTH-MER-A", "COMPANY:SYN-001", True, interval, "fixture:security:mer-a"),
        SyntheticSecurity("SECURITY:SYN-002", "BSE", "999001", "COMPANY:SYN-003", True, interval, "fixture:security:999001"),
        SyntheticSecurity("SECURITY:SYN-003", "ISIN", "SYN00FAKE001", "COMPANY:SYN-003", False, interval, "fixture:security:fake-isin"),
    )
    return SyntheticRegistry("synthetic-registry-v1", companies, securities)
