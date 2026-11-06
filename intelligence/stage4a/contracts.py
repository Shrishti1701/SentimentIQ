from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Literal


AttributionRole = Literal["subject", "possessive", "coordinated_subject"]
AmbiguityBasis = Literal[
    "none",
    "entity",
    "resolved_company",
    "relationship",
    "entity_and_relationship",
    "resolved_company_and_relationship",
]
LinkAttemptStatus = Literal["ambiguous", "abstained"]
LegacyLinkAttemptReason = Literal["insufficient_evidence", "two_interpretations"]
Stage4ALinkAttemptReason = Literal[
    "relationship_ambiguous",
    "relationship_evidence_insufficient",
    "pronoun_antecedent_ambiguous",
    "entity_registry_ambiguous",
    "resolved_company_ambiguous",
    "entity_and_relationship_ambiguous",
    "resolved_company_and_relationship_ambiguous",
]


_UTC_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})T(?P<time>\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<fraction>\d{1,6}))?(?:Z|[+-]\d{2}:?\d{2})$"
)


def canonical_utc(raw: str) -> str:
    if not isinstance(raw, str):
        raise TypeError("raw timestamp must be text")
    precision_match = re.search(r"\.(\d+)(?:Z|[+-]\d{2}:?\d{2})$", raw)
    if precision_match is not None and len(precision_match.group(1)) > 6:
        raise ValueError("timestamp precision above six fractional digits is rejected")
    match = _UTC_RE.fullmatch(raw)
    if match is None:
        raise ValueError("timestamp must be a timezone-qualified ISO-8601 value")
    fraction = match.group("fraction")
    if fraction is not None and len(fraction) > 6:
        raise ValueError("timestamp precision above six fractional digits is rejected")

    normalized = raw.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("UTC serialization requires an aware timestamp")
    utc = parsed.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond:06d}Z"


_ALIASES = {
    "profit": "profit",
    "profitability": "profitability",
    "net profit": "net_profit",
    "operating profit": "operating_profit",
    "margin": "generic_margin",
    "profit margin": "profit_margin",
    "operating margin": "operating_margin",
    "gross margin": "gross_margin",
    "net margin": "net_margin",
    "revenue": "revenue",
    "sales growth": "sales_growth",
    "growth in sales": "sales_growth",
    "sales grew": "sales_growth",
    "debt": "debt",
    "debt repayment": "repayment",
    "repaid debt": "repayment",
    "debt refinancing": "refinancing",
    "refinancing": "refinancing",
    "operating expenses": "operating_expenses",
    "employee expenses": "employee_expenses",
    "management": "management",
    "management change": "management_change",
    "regulatory developments": "regulatory_developments",
    "regulatory development": "regulatory_developments",
    "business growth": "business_growth",
}


_CONTEXT_DEPENDENT_DISABLED = {
    "profit after tax",
    "pat",
    "operating income",
    "ebitda margin",
    "sales",
    "turnover",
    "borrowings",
    "operating costs",
    "employee costs",
    "staff costs",
    "payroll",
}


def resolve_alias(surface: str) -> str | None:
    key = surface.strip().lower()
    if key in _CONTEXT_DEPENDENT_DISABLED:
        return None
    return _ALIASES.get(key)


@dataclass(frozen=True)
class LinkAttempt:
    attempt_id: str
    document_ref: str
    entity_mention_id: str
    status: LinkAttemptStatus
    ambiguity_basis: AmbiguityBasis
    reason_code: LegacyLinkAttemptReason | Stage4ALinkAttemptReason
    candidate_entity_ids: tuple[str, ...]
    candidate_resolved_company_ids: tuple[str, ...]
    candidate_attribution_roles: tuple[AttributionRole, ...]
    relationship_evidence_required: bool

    def validate(self) -> None:
        for name, value in (
            ("attempt_id", self.attempt_id),
            ("document_ref", self.document_ref),
            ("entity_mention_id", self.entity_mention_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text")
        for name, value in (
            ("candidate_entity_ids", self.candidate_entity_ids),
            ("candidate_resolved_company_ids", self.candidate_resolved_company_ids),
            ("candidate_attribution_roles", self.candidate_attribution_roles),
        ):
            if not isinstance(value, tuple):
                raise TypeError(f"{name} must be a tuple")

        entity_ids = self.candidate_entity_ids
        company_ids = self.candidate_resolved_company_ids
        roles = self.candidate_attribution_roles
        if any(value.startswith("COMPANY:") for value in entity_ids):
            raise ValueError("candidate_entity_ids contains a resolved-company ID")
        if any(not value.startswith("COMPANY:") for value in company_ids):
            raise ValueError("candidate_resolved_company_ids requires COMPANY: namespace")
        if any(len(set(values)) != len(values) for values in (entity_ids, company_ids, roles)):
            raise ValueError("candidate tuples must be unique")
        if entity_ids != tuple(sorted(entity_ids)):
            raise ValueError("candidate_entity_ids must be canonically sorted")
        if company_ids != tuple(sorted(company_ids)):
            raise ValueError("candidate_resolved_company_ids must be canonically sorted")
        if type(self.relationship_evidence_required) is not bool:
            raise TypeError("relationship_evidence_required must be a bool")

        if self.status == "ambiguous":
            valid = {
                "entity": ("entity_registry_ambiguous", 1, 0, 0),
                "resolved_company": ("resolved_company_ambiguous", 0, 1, 0),
                "relationship": ("relationship_ambiguous", 0, 0, 1),
                "entity_and_relationship": (
                    "entity_and_relationship_ambiguous",
                    1,
                    0,
                    1,
                ),
                "resolved_company_and_relationship": (
                    "resolved_company_and_relationship_ambiguous",
                    0,
                    1,
                    1,
                ),
            }
            if self.ambiguity_basis == "none":
                raise ValueError("ambiguous status requires a non-none ambiguity basis")
            expected_reason, entity_required, company_required, role_required = valid[self.ambiguity_basis]
            if self.reason_code not in (
                expected_reason,
                "relationship_ambiguous",
            ):
                raise ValueError("reason_code is not valid for ambiguity basis")
            if entity_required and len(entity_ids) < 2:
                raise ValueError("entity ambiguity requires at least two entity candidates")
            if not entity_required and entity_ids:
                raise ValueError("entity candidates are forbidden for this ambiguity basis")
            if company_required and len(company_ids) < 2:
                raise ValueError("resolved-company ambiguity requires at least two company candidates")
            if not company_required and company_ids:
                raise ValueError("resolved-company candidates are forbidden for this ambiguity basis")
            if role_required and len(roles) < 2:
                raise ValueError("relationship ambiguity requires at least two roles")
            if not role_required and roles:
                raise ValueError("attribution roles are forbidden for this ambiguity basis")
            if role_required and not self.relationship_evidence_required:
                raise ValueError("relationship ambiguity requires relationship evidence")
            if not role_required and self.relationship_evidence_required:
                raise ValueError("relationship evidence is forbidden without relationship ambiguity")
        elif self.status == "abstained":
            if self.ambiguity_basis != "none":
                raise ValueError("abstained attempts must use ambiguity_basis='none'")
            if entity_ids or company_ids or roles:
                raise ValueError("abstained attempts cannot contain ambiguity candidates")
            if self.reason_code not in (
                "insufficient_evidence",
                "two_interpretations",
                "relationship_evidence_insufficient",
                "pronoun_antecedent_ambiguous",
            ):
                raise ValueError("invalid abstention reason_code")
            if self.reason_code == "relationship_evidence_insufficient" and self.relationship_evidence_required:
                raise ValueError("insufficient evidence must not claim relationship evidence")
        else:
            raise ValueError("invalid link attempt status")


def validate_supersession_graph(edges: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    if not isinstance(edges, tuple):
        raise TypeError("supersession edges must be a tuple")
    normalized = tuple(sorted(set(edges)))
    adjacency: dict[str, list[str]] = {}
    for predecessor, successor in normalized:
        if predecessor == successor:
            raise ValueError("supersession self-reference is forbidden")
        adjacency.setdefault(predecessor, []).append(successor)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError("supersession cycle is forbidden")
        if node in visited:
            return
        visiting.add(node)
        for successor in adjacency.get(node, ()):
            visit(successor)
        visiting.remove(node)
        visited.add(node)

    for node in sorted(adjacency):
        visit(node)
    return normalized


@dataclass(frozen=True)
class EvidenceSpan:
    field: Literal["title", "body"]
    start: int
    end: int
    quote: str

    def __post_init__(self) -> None:
        if self.field not in ("title", "body"):
            raise ValueError("evidence field must be title or body")
        if isinstance(self.start, bool) or isinstance(self.end, bool) or not isinstance(self.start, int) or not isinstance(self.end, int):
            raise TypeError("evidence offsets must be integers")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("evidence offsets must be a half-open positive range")
        if not isinstance(self.quote, str) or not self.quote:
            raise ValueError("evidence quote must be non-empty")

    def validate_source(self, source: str) -> None:
        if source[self.start:self.end] != self.quote:
            raise ValueError("evidence quote and source offsets do not match")


@dataclass(frozen=True)
class CompanyCompetitorProvenance:
    document_ref: str
    resolved_company_id: str
    company_mention_id: str
    resolution_result_id: str

    def validate(self) -> None:
        for name, value in vars(self).items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if not self.resolved_company_id.startswith("COMPANY:"):
            raise ValueError("resolved_company_id must use COMPANY: namespace")


@dataclass(frozen=True)
class CompanyCompetitorEvidenceAssociation:
    resolved_company_id: str
    company_mention_id: str
    resolution_result_id: str
    evidence: EvidenceSpan

    def provenance_key(self) -> tuple[str, str, str]:
        return (
            self.resolved_company_id,
            self.company_mention_id,
            self.resolution_result_id,
        )


@dataclass(frozen=True)
class CompanyCompetitorRelationOccurrence:
    occurrence_id: str
    relation_id: str
    document_ref: str
    source_field: Literal["title", "body"]
    start: int
    end: int
    quote: str
    relation_type: Literal["peer", "competitor"]
    left_company_id: str
    right_company_id: str
    provenance: tuple[CompanyCompetitorProvenance, ...]
    evidence_associations: tuple[CompanyCompetitorEvidenceAssociation, ...]
    occurrence_version: str = "company-relation-occurrence-v1"
    payload_version: Literal[1] = 1

    def validate(
        self,
        *,
        source: str,
        mention_companies: dict[str, str],
        resolution_pairs: dict[str, tuple[str, str]],
    ) -> None:
        if source[self.start:self.end] != self.quote:
            raise ValueError("occurrence quote and offsets do not match source")
        if not isinstance(self.provenance, tuple) or len(self.provenance) < 2:
            raise ValueError("competitor provenance requires two supporting records")
        if not isinstance(self.evidence_associations, tuple) or not self.evidence_associations:
            raise ValueError("competitor provenance requires evidence associations")
        for item in self.provenance:
            item.validate()
        keys = tuple(item.document_ref for item in self.provenance)
        if any(document_ref != self.document_ref for document_ref in keys):
            raise ValueError("provenance document mismatch")

        endpoint_set = {self.left_company_id, self.right_company_id}
        if len(endpoint_set) != 2:
            raise ValueError("relation endpoints must be two distinct companies")
        company_set = {item.resolved_company_id for item in self.provenance}
        if company_set != endpoint_set:
            raise ValueError("provenance companies must exactly match relation endpoints")

        provenance_keys = {
            (
                item.resolved_company_id,
                item.company_mention_id,
                item.resolution_result_id,
            )
            for item in self.provenance
        }
        if len(provenance_keys) != len(self.provenance):
            raise ValueError("duplicate provenance triples are forbidden")
        if {
            association.provenance_key()
            for association in self.evidence_associations
        } - provenance_keys:
            raise ValueError("evidence association has no matching provenance triple")

        for item in self.provenance:
            expected_company = mention_companies.get(item.company_mention_id)
            if expected_company != item.resolved_company_id:
                raise ValueError("mention-to-company mismatch")
            resolution_pair = resolution_pairs.get(item.resolution_result_id)
            if resolution_pair != (item.company_mention_id, item.resolved_company_id):
                raise ValueError("resolution-to-mention/company mismatch")
        for association in self.evidence_associations:
            if association.evidence.field != self.source_field:
                raise ValueError("evidence source field mismatch")
            association.evidence.validate_source(source)


@dataclass(frozen=True)
class EvidenceSupersession:
    supersession_id: str
    superseded_observation_id: str
    replacement_observation_id: str
    document_ref: str
    source_field: Literal["title", "body"]
    start: int
    end: int
    quote: str
    supersession_reason: str
    payload_version: Literal[1] = 1

    def validate(self, *, source: str) -> None:
        if self.superseded_observation_id == self.replacement_observation_id:
            raise ValueError("supersession self-reference is forbidden")
        if source[self.start:self.end] != self.quote:
            raise ValueError("supersession quote and offsets do not match source")
        if self.payload_version != 1:
            raise ValueError("unsupported supersession payload version")

    def immutable_payload(self) -> dict[str, object]:
        return {
            "superseded_observation_id": self.superseded_observation_id,
            "replacement_observation_id": self.replacement_observation_id,
            "document_ref": self.document_ref,
            "source_field": self.source_field,
            "start": self.start,
            "end": self.end,
            "supersession_reason": self.supersession_reason,
            "payload_version": self.payload_version,
        }
