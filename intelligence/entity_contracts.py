"""Entity architecture contracts; independent of sentiment and persistence."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Literal

from intelligence.contracts import AnalysisInput, AspectMention, EvidenceSpan, NormalizedDocument, VerifiedEffectiveTime
from processing.cleaner import normalize_document
from processing.text_alignment import validate_evidence_span


ObservationKind = Literal[
    "organization_name_candidate",
    "abbreviation_candidate",
    "security_identifier_candidate",
    "other_company_reference",
]
SecurityNamespace = Literal["NSE", "BSE", "ISIN"]
ResolutionStatus = Literal["resolved", "ambiguous", "unresolved"]
MatchBasis = Literal[
    "legal_name", "verified_alias", "verified_security_issuer_mapping", "contextual_rule"
]
RelationshipType = Literal["subject", "comparison", "competitor"]
AttemptRelationship = Literal["subject", "comparison", "competitor", "unknown"]
AmbiguityBasis = Literal["entity", "relationship", "entity_and_relationship", "none"]
_VALIDATION_TOKEN = object()


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")


def _role(spans: tuple[EvidenceSpan, ...], expected: str, field_name: str, *, required: bool) -> None:
    if required and not spans:
        raise ValueError(f"{field_name} is required")
    if any(span.role != expected for span in spans):
        raise ValueError(f"{field_name} evidence must use role {expected!r}")


def _require_tuple(value: object, name: str, item_type: type | None = None) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be an immutable tuple")
    if item_type is not None and any(not isinstance(item, item_type) for item in value):
        raise TypeError(f"{name} contains an invalid element type")


def _canonical_json(payload: dict[str, object]) -> str:
    if not isinstance(payload, dict) or any(not isinstance(key, str) for key in payload):
        raise TypeError("canonical payload must be a string-keyed dictionary")
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _stable_id(kind: str, payload: dict[str, object]) -> str:
    return f"{kind}:v1:{sha256(_canonical_json(payload).encode('utf-8')).hexdigest()}"


def validate_source_evidence(
    spans: tuple[EvidenceSpan, ...], *, normalized_document: NormalizedDocument
) -> None:
    """Validate exact slices and require ambiguity to match Stage 1 alignment."""
    for span in spans:
        validate_evidence_span(span, original_title=normalized_document.original_title, original_body=normalized_document.original_body)
        original, offsets = (
            (normalized_document.original_title, normalized_document.title_offsets)
            if span.field == "title"
            else (normalized_document.original_body, normalized_document.body_offsets)
        )
        normalized = normalized_document.normalized_title if span.field == "title" else normalized_document.normalized_body
        if original is None or normalized is None:
            raise ValueError("evidence field is absent from normalized source")
        selected = [
            (index, item) for index, item in enumerate(offsets)
            if max(span.start, item.start) < min(span.end, item.end)
        ]
        if not selected:
            raise ValueError("source evidence has no corresponding normalized span")
        indexes = [index for index, _ in selected]
        source_start = min(item.start for _, item in selected)
        source_end = max(item.end for _, item in selected)
        if indexes != list(range(indexes[0], indexes[-1] + 1)) or (source_start, source_end) != (span.start, span.end):
            raise ValueError("source evidence offsets are inconsistent with normalized alignment")
        has_gap_or_overlap = any(left.end != right.start for (_, left), (_, right) in zip(selected, selected[1:]))
        derived_ambiguity = has_gap_or_overlap or any(item.ambiguous for _, item in selected)
        if span.alignment_ambiguous != derived_ambiguity:
            raise ValueError("alignment_ambiguous does not match the validated Stage 1 mapping")


@dataclass(frozen=True)
class EntityMention:
    mention_id: str
    document_ref: str
    surface_text: str
    field: Literal["title", "body"]
    start: int
    end: int
    observation_kind: ObservationKind
    evidence: EvidenceSpan
    extractor_version: str
    security_namespace: SecurityNamespace | None = None

    def __post_init__(self) -> None:
        for key in ("mention_id", "document_ref", "surface_text", "extractor_version"):
            _nonempty(getattr(self, key), key)
        _validate_range(self.field, self.start, self.end)
        if self.observation_kind not in ("organization_name_candidate", "abbreviation_candidate", "security_identifier_candidate", "other_company_reference"):
            raise ValueError("invalid observation_kind")
        if self.security_namespace not in (None, "NSE", "BSE", "ISIN"):
            raise ValueError("security namespace must be explicitly NSE, BSE, ISIN, or None")
        if self.security_namespace is not None and self.observation_kind != "security_identifier_candidate":
            raise ValueError("security namespace requires a security_identifier_candidate")
        if not isinstance(self.evidence, EvidenceSpan):
            raise TypeError("evidence must be an EvidenceSpan")
        if self.evidence.role != "entity" or (self.evidence.field, self.evidence.start, self.evidence.end, self.evidence.quote) != (self.field, self.start, self.end, self.surface_text):
            raise ValueError("mention evidence must exactly match its entity span")
        expected_id = _stable_id("mention", _mention_payload(self.document_ref, self.field, self.start, self.end, self.observation_kind, self.security_namespace, self.extractor_version))
        if self.mention_id != expected_id:
            raise ValueError("mention_id does not match its canonical payload")

    def validate_source(self, *, normalized_document: NormalizedDocument) -> None:
        validate_source_evidence((self.evidence,), normalized_document=normalized_document)


@dataclass(frozen=True)
class EntityCandidate:
    entity_id: str
    match_basis: MatchBasis
    supporting_security_ids: tuple[str, ...] = ()
    supporting_identifier_refs: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()
    supporting_evidence: tuple["CandidateEvidence", ...] = ()
    rank: int = 1

    def __post_init__(self) -> None:
        _nonempty(self.entity_id, "entity_id")
        if not self.entity_id.startswith("COMPANY:"):
            raise ValueError("candidate entity_id must use COMPANY: namespace")
        if self.match_basis not in ("legal_name", "verified_alias", "verified_security_issuer_mapping", "contextual_rule"):
            raise ValueError("invalid candidate match_basis")
        if isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank < 1:
            raise ValueError("rank must be a positive integer")
        _require_tuple(self.supporting_security_ids, "supporting_security_ids")
        _require_tuple(self.supporting_identifier_refs, "supporting_identifier_refs")
        _require_tuple(self.provenance_refs, "provenance_refs")
        _require_tuple(self.supporting_evidence, "supporting_evidence", CandidateEvidence)
        for value in (*self.supporting_security_ids, *self.supporting_identifier_refs, *self.provenance_refs):
            _nonempty(value, "candidate reference")
        if any(not item.startswith("SECURITY:") for item in self.supporting_security_ids):
            raise ValueError("supporting security IDs must use SECURITY: namespace")
        if self.match_basis == "verified_security_issuer_mapping" and (not self.supporting_security_ids or not self.supporting_identifier_refs or not self.provenance_refs):
            raise ValueError("security issuer candidates require security, identifier, and provenance references")
        if not self.provenance_refs:
            raise ValueError("candidate requires registry provenance")
        if not self.supporting_evidence:
            raise ValueError("candidate requires typed supporting evidence")
        verified = [item for item in self.supporting_evidence if item.verified and not item.fuzzy_only]
        if any(item.fuzzy_only for item in self.supporting_evidence) and not verified:
            raise ValueError("fuzzy-only evidence cannot support a plausible candidate")
        evidence_sources = {item.source_ref for item in self.supporting_evidence}
        if not evidence_sources.issubset(set(self.provenance_refs)):
            raise ValueError("candidate provenance must include every supporting evidence source")
        if self.match_basis == "contextual_rule":
            if not any(item.evidence_kind == "contextual_rule" and item.context_rule_id == "explicit_issuer_statement" for item in self.supporting_evidence):
                raise ValueError("contextual_rule requires the allow-listed explicit_issuer_statement rule")
            if not any(item.evidence_kind in ("legal_name", "verified_alias", "verified_security_issuer_mapping") for item in verified):
                raise ValueError("contextual_rule requires a verified non-fuzzy identity anchor")
        else:
            if not any(item.evidence_kind == self.match_basis for item in verified):
                raise ValueError("match_basis requires matching verified supporting evidence")


@dataclass(frozen=True)
class CandidateEvidence:
    """Evidence claim from a producer; provenance authority is not established here."""

    evidence_kind: MatchBasis
    source_ref: str
    verified: bool
    fuzzy_only: bool = False
    context_rule_id: str | None = None

    def __post_init__(self) -> None:
        if self.evidence_kind not in ("legal_name", "verified_alias", "verified_security_issuer_mapping", "contextual_rule"):
            raise ValueError("invalid candidate evidence kind")
        _nonempty(self.source_ref, "source_ref")
        if type(self.verified) is not bool or type(self.fuzzy_only) is not bool:
            raise TypeError("verified and fuzzy_only must be actual bool values")
        if self.evidence_kind == "contextual_rule" and self.context_rule_id != "explicit_issuer_statement":
            raise ValueError("contextual rule is not allow-listed")
        if self.evidence_kind != "contextual_rule" and self.context_rule_id is not None:
            raise ValueError("context_rule_id is only valid for contextual_rule evidence")


@dataclass(frozen=True)
class EntityResolutionResult:
    resolution_id: str
    document_ref: str
    mention_id: str
    status: ResolutionStatus
    selected_entity_id: str | None
    candidates: tuple[EntityCandidate, ...]
    review_only_candidates: tuple[EntityCandidate, ...]
    rationale_code: str
    registry_version: str
    resolver_version: str
    confidence: float | None = None

    def __post_init__(self) -> None:
        for key in ("resolution_id", "document_ref", "mention_id", "rationale_code", "registry_version", "resolver_version"):
            _nonempty(getattr(self, key), key)
        if self.confidence is not None:
            raise ValueError("confidence is unavailable until calibration is implemented")
        _require_tuple(self.candidates, "candidates", EntityCandidate)
        _require_tuple(self.review_only_candidates, "review_only_candidates", EntityCandidate)
        ids = [item.entity_id for item in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("plausible candidates must have unique entity IDs")
        review_ids_ordered = [item.entity_id for item in self.review_only_candidates]
        if len(review_ids_ordered) != len(set(review_ids_ordered)):
            raise ValueError("review-only candidates must have unique entity IDs")
        for collection_name, collection in (("plausible", self.candidates), ("review-only", self.review_only_candidates)):
            order = [(item.rank, item.entity_id) for item in collection]
            if order != sorted(order):
                raise ValueError(f"{collection_name} candidates must use deterministic rank/entity ordering")
        review_ids = {item.entity_id for item in self.review_only_candidates}
        if review_ids.intersection(ids):
            raise ValueError("plausible and review-only candidate collections must be disjoint")
        if self.status == "resolved":
            if len(self.candidates) != 1 or self.selected_entity_id != self.candidates[0].entity_id:
                raise ValueError("resolved requires exactly one plausible candidate equal to selected_entity_id")
        elif self.status == "ambiguous":
            if len(self.candidates) < 2 or self.selected_entity_id is not None:
                raise ValueError("ambiguous requires at least two plausible candidates and no selection")
        elif self.status == "unresolved":
            if self.candidates or self.selected_entity_id is not None:
                raise ValueError("unresolved requires zero plausible candidates and no selection")
        else:
            raise ValueError("invalid resolution status")
        expected_id = _stable_id("resolution", _resolution_payload(self.document_ref, self.mention_id, self.registry_version, self.resolver_version, self.status, self.selected_entity_id, self.rationale_code, self.candidates, self.review_only_candidates))
        if self.resolution_id != expected_id:
            raise ValueError("resolution_id does not match its canonical payload")


@dataclass(frozen=True)
class EntityAspectLink:
    link_id: str
    document_ref: str
    entity_id: str
    entity_mention_ids: tuple[str, ...]
    aspect_ref: tuple[str, str]
    aspect_mention_ids: tuple[str, ...]
    relationship_type: RelationshipType
    entity_evidence: tuple[EvidenceSpan, ...]
    aspect_evidence: tuple[EvidenceSpan, ...]
    relation_evidence: tuple[EvidenceSpan, ...]
    linker_version: str
    confidence: float | None = None

    def __post_init__(self) -> None:
        for key in ("link_id", "document_ref", "entity_id", "linker_version"):
            _nonempty(getattr(self, key), key)
        if not self.entity_id.startswith("COMPANY:"):
            raise ValueError("link entity_id must use COMPANY: namespace")
        _require_tuple(self.entity_mention_ids, "entity_mention_ids")
        _require_tuple(self.aspect_mention_ids, "aspect_mention_ids")
        _require_tuple(self.entity_evidence, "entity_evidence", EvidenceSpan)
        _require_tuple(self.aspect_evidence, "aspect_evidence", EvidenceSpan)
        _require_tuple(self.relation_evidence, "relation_evidence", EvidenceSpan)
        _validate_refs(self.entity_mention_ids, "entity_mention_ids")
        _validate_refs(self.aspect_mention_ids, "aspect_mention_ids")
        _validate_unique_refs(self.entity_mention_ids, "entity_mention_ids")
        _validate_unique_refs(self.aspect_mention_ids, "aspect_mention_ids")
        _validate_aspect_ref(self.aspect_ref)
        if self.relationship_type not in ("subject", "comparison", "competitor"):
            raise ValueError("successful link requires an established relationship")
        _role(self.entity_evidence, "entity", "entity_evidence", required=True)
        _role(self.aspect_evidence, "aspect", "aspect_evidence", required=True)
        _role(self.relation_evidence, "relation", "relation_evidence", required=True)
        if self.confidence is not None:
            raise ValueError("confidence is unavailable until calibration is implemented")
        expected_id = _stable_id("entity-link", _link_payload(self.document_ref, self.entity_id, self.entity_mention_ids, self.aspect_ref, self.aspect_mention_ids, self.relationship_type, self.linker_version))
        if self.link_id != expected_id:
            raise ValueError("link_id does not match its canonical payload")

    def validate_source_evidence(self, *, normalized_document: NormalizedDocument, ambiguous_evidence_semantically_sufficient: bool = False) -> None:
        if type(ambiguous_evidence_semantically_sufficient) is not bool:
            raise TypeError("ambiguous_evidence_semantically_sufficient must be an actual bool")
        spans = self.entity_evidence + self.aspect_evidence + self.relation_evidence
        validate_source_evidence(spans, normalized_document=normalized_document)
        if any(span.alignment_ambiguous for span in spans) and ambiguous_evidence_semantically_sufficient is not True:
            raise ValueError("alignment-ambiguous evidence requires explicit semantic sufficiency")


@dataclass(frozen=True)
class EntityAspectLinkAttempt:
    attempt_id: str
    document_ref: str
    entity_mention_ids: tuple[str, ...]
    candidate_entity_ids: tuple[str, ...]
    status: Literal["ambiguous", "abstained"]
    relationship_type: AttemptRelationship
    candidate_relationship_types: tuple[RelationshipType, ...]
    ambiguity_basis: AmbiguityBasis
    reason_code: str
    linker_version: str
    aspect_ref: tuple[str, str] | None = None
    aspect_mention_ids: tuple[str, ...] = ()
    entity_evidence: tuple[EvidenceSpan, ...] = ()
    aspect_evidence: tuple[EvidenceSpan, ...] = ()
    relation_evidence: tuple[EvidenceSpan, ...] = ()
    confidence: float | None = None

    def __post_init__(self) -> None:
        for key in ("attempt_id", "document_ref", "reason_code", "linker_version"):
            _nonempty(getattr(self, key), key)
        _validate_refs(self.entity_mention_ids, "entity_mention_ids")
        _require_tuple(self.entity_mention_ids, "entity_mention_ids")
        _require_tuple(self.candidate_entity_ids, "candidate_entity_ids")
        _require_tuple(self.candidate_relationship_types, "candidate_relationship_types")
        _require_tuple(self.aspect_mention_ids, "aspect_mention_ids")
        _require_tuple(self.entity_evidence, "entity_evidence", EvidenceSpan)
        _require_tuple(self.aspect_evidence, "aspect_evidence", EvidenceSpan)
        _require_tuple(self.relation_evidence, "relation_evidence", EvidenceSpan)
        _validate_refs(self.candidate_entity_ids, "candidate_entity_ids", allow_empty=True)
        if any(not value.startswith("COMPANY:") for value in self.candidate_entity_ids):
            raise ValueError("attempt candidate entity IDs must use COMPANY: namespace")
        if len(set(self.candidate_entity_ids)) != len(self.candidate_entity_ids):
            raise ValueError("candidate_entity_ids must be unique")
        if self.aspect_ref is None:
            if self.aspect_mention_ids:
                raise ValueError("aspect mention IDs require an aspect_ref")
            if self.aspect_evidence:
                raise ValueError("aspect evidence requires an identified aspect")
        else:
            _validate_aspect_ref(self.aspect_ref)
            _validate_refs(self.aspect_mention_ids, "aspect_mention_ids")
        _validate_unique_refs(self.entity_mention_ids, "entity_mention_ids")
        _validate_unique_refs(self.aspect_mention_ids, "aspect_mention_ids")
        _role(self.entity_evidence, "entity", "entity_evidence", required=False)
        _role(self.aspect_evidence, "aspect", "aspect_evidence", required=False)
        _role(self.relation_evidence, "relation", "relation_evidence", required=False)
        if len(set(self.candidate_relationship_types)) != len(self.candidate_relationship_types):
            raise ValueError("candidate relationship types must be unique")
        if any(item not in ("subject", "comparison", "competitor") for item in self.candidate_relationship_types):
            raise ValueError("invalid candidate relationship type")
        if self.relationship_type not in ("subject", "comparison", "competitor", "unknown"):
            raise ValueError("invalid relationship_type")
        if self.relationship_type != "unknown" and self.candidate_relationship_types != (self.relationship_type,):
            raise ValueError("an established relationship must be the sole candidate relationship type")
        if len(self.candidate_relationship_types) > 1 and self.relationship_type != "unknown":
            raise ValueError("multiple relationship interpretations require relationship_type=unknown")
        if self.status == "ambiguous":
            if self.ambiguity_basis not in ("entity", "relationship", "entity_and_relationship"):
                raise ValueError("ambiguous attempts require an ambiguity basis")
            if len(self.candidate_entity_ids) > 1 and self.ambiguity_basis not in ("entity", "entity_and_relationship"):
                raise ValueError("multiple entity interpretations require entity ambiguity basis")
            if len(self.candidate_relationship_types) > 1 and self.ambiguity_basis not in ("relationship", "entity_and_relationship"):
                raise ValueError("multiple relationship interpretations require relationship ambiguity basis")
            if len(self.candidate_relationship_types) > 1 and self.ambiguity_basis not in ("relationship", "entity_and_relationship"):
                raise ValueError("multiple relationship interpretations require relationship ambiguity basis")
            if self.ambiguity_basis in ("relationship", "entity_and_relationship") and len(self.candidate_relationship_types) < 2:
                raise ValueError("relationship ambiguity requires multiple candidate relationship types")
            if self.ambiguity_basis in ("entity", "entity_and_relationship") and len(self.candidate_entity_ids) < 2:
                raise ValueError("entity ambiguity requires multiple candidate entities")
        elif self.status == "abstained":
            if self.relationship_type != "unknown":
                raise ValueError("abstained attempts cannot claim an established relationship")
            if self.ambiguity_basis != "none":
                raise ValueError("abstained attempts use ambiguity_basis=none; unresolved alternatives are ambiguous")
            if len(self.candidate_relationship_types) > 1 or len(self.candidate_entity_ids) > 1:
                raise ValueError("multiple plausible alternatives require an ambiguous attempt, not abstention")
        else:
            raise ValueError("invalid link attempt status")
        if self.confidence is not None:
            raise ValueError("confidence is unavailable until calibration is implemented")
        expected_id = _stable_id("entity-link-attempt", _attempt_payload(self.document_ref, self.entity_mention_ids, self.candidate_entity_ids, self.aspect_ref, self.aspect_mention_ids, self.candidate_relationship_types, self.relationship_type, self.ambiguity_basis, self.status, self.reason_code, self.linker_version))
        if self.attempt_id != expected_id:
            raise ValueError("attempt_id does not match its canonical payload")

    def validate_source_evidence(self, *, normalized_document: NormalizedDocument) -> None:
        validate_source_evidence(self.entity_evidence + self.aspect_evidence + self.relation_evidence, normalized_document=normalized_document)


@dataclass(frozen=True, init=False)
class ValidatedEntitySource:
    """Source-bound validation result; construct only with validate_entity_source()."""

    document_ref: str
    original_title: str | None
    original_body: str | None
    normalized_document: NormalizedDocument
    entity_mentions: tuple[EntityMention, ...]
    aspect_mentions: tuple[AspectMention, ...]
    source_digest: str
    _token: object

@dataclass(frozen=True, init=False)
class ValidatedEntityAspectLink:
    """Downstream-safe link created after source and resolution validation."""

    link: EntityAspectLink
    document_ref: str
    source_digest: str
    resolution_ids: tuple[str, ...]
    _token: object


@dataclass(frozen=True, init=False)
class ValidatedEntityAspectLinkAttempt:
    """Failed attempt whose retained evidence was checked against a source."""

    attempt: EntityAspectLinkAttempt
    document_ref: str
    source_digest: str
    _token: object


@dataclass(frozen=True, init=False)
class ValidatedEntityResolution:
    result: EntityResolutionResult
    _token: object


def validate_entity_resolution_result(
    mention: EntityMention,
    result: EntityResolutionResult,
    *,
    registry: object,
    effective_time: VerifiedEffectiveTime | None,
) -> ValidatedEntityResolution:
    """Bind a resolution to the synthetic trusted registry used in this milestone."""
    if not isinstance(mention, EntityMention) or not isinstance(result, EntityResolutionResult):
        raise TypeError("mention and result must use entity contracts")
    if result.document_ref != mention.document_ref or result.mention_id != mention.mention_id:
        raise ValueError("resolution result does not identify this mention and document")
    # Local import avoids making the registry a module-import dependency for contracts.
    from intelligence.synthetic_registry import SyntheticRegistry

    if not isinstance(registry, SyntheticRegistry):
        raise TypeError("resolution validation requires SyntheticRegistry in this milestone")
    if effective_time is not None:
        from intelligence.contracts import _VERIFIED_TIME_TOKEN
        if not isinstance(effective_time, VerifiedEffectiveTime) or effective_time._token is not _VERIFIED_TIME_TOKEN or effective_time.document_ref != mention.document_ref:
            raise ValueError("verified effective time must be bound to this mention's document")
    registry.validate_result(mention, result, effective_time=effective_time)
    wrapper = object.__new__(ValidatedEntityResolution)
    object.__setattr__(wrapper, "result", result)
    object.__setattr__(wrapper, "_token", _VALIDATION_TOKEN)
    return wrapper

def validate_entity_source(
    analysis_input: AnalysisInput,
    mentions: tuple[EntityMention, ...],
    *,
    normalized_document: NormalizedDocument,
    aspect_mentions: tuple[AspectMention, ...] = (),
) -> ValidatedEntitySource:
    """Bind mention validation to the actual immutable AnalysisInput source."""
    if not isinstance(analysis_input, AnalysisInput):
        raise TypeError("analysis_input must be an AnalysisInput")
    if not isinstance(normalized_document, NormalizedDocument):
        raise TypeError("normalized_document must be a NormalizedDocument")
    expected_normalized = normalize_document(analysis_input)
    if normalized_document != expected_normalized or normalized_document.document_ref != analysis_input.document_ref:
        raise ValueError("NormalizedDocument does not match the AnalysisInput and Stage 1 alignment")
    _require_tuple(mentions, "mentions", EntityMention)
    _require_tuple(aspect_mentions, "aspect_mentions", AspectMention)
    source_identity = {"document_ref": analysis_input.document_ref, "title": analysis_input.title, "body": analysis_input.body}
    digest = sha256(_canonical_json(source_identity).encode("utf-8")).hexdigest()
    seen: set[str] = set()
    for item in mentions:
        if item.document_ref != analysis_input.document_ref:
            raise ValueError("entity mention document_ref does not match AnalysisInput")
        if item.mention_id in seen:
            raise ValueError("mention IDs must be unique within the validated source")
        seen.add(item.mention_id)
        item.validate_source(normalized_document=normalized_document)
    aspect_ids: set[str] = set()
    for item in aspect_mentions:
        if item.mention_id is None or item.document_ref != analysis_input.document_ref or item.taxonomy_version is None:
            raise ValueError("source-bound aspect mentions require IDs, matching document_ref, and taxonomy_version")
        if item.mention_id in aspect_ids:
            raise ValueError("aspect mention IDs must be unique within the validated source")
        aspect_ids.add(item.mention_id)
        if item.evidence is None:
            raise ValueError("source-bound aspect mentions require exact aspect evidence")
        validate_source_evidence((item.evidence,), normalized_document=normalized_document)
    result = object.__new__(ValidatedEntitySource)
    for key, value in (("document_ref", analysis_input.document_ref), ("original_title", analysis_input.title), ("original_body", analysis_input.body), ("normalized_document", normalized_document), ("entity_mentions", mentions), ("aspect_mentions", aspect_mentions), ("source_digest", digest), ("_token", _VALIDATION_TOKEN)):
        object.__setattr__(result, key, value)
    return result


def validate_entity_link_attempt(
    attempt: EntityAspectLinkAttempt,
    *,
    analysis_input: AnalysisInput,
    normalized_document: NormalizedDocument,
) -> ValidatedEntityAspectLinkAttempt:
    """Bind a structurally valid failed attempt and all retained evidence to source."""
    if not isinstance(attempt, EntityAspectLinkAttempt):
        raise TypeError("attempt must be an EntityAspectLinkAttempt")
    if not isinstance(analysis_input, AnalysisInput):
        raise TypeError("analysis_input must be an AnalysisInput")
    if not isinstance(normalized_document, NormalizedDocument):
        raise TypeError("normalized_document must be a NormalizedDocument")
    if attempt.document_ref != analysis_input.document_ref:
        raise ValueError("attempt document_ref does not match AnalysisInput")
    expected_normalized = normalize_document(analysis_input)
    if normalized_document != expected_normalized or normalized_document.document_ref != analysis_input.document_ref:
        raise ValueError("NormalizedDocument does not match the AnalysisInput and Stage 1 alignment")
    spans = attempt.entity_evidence + attempt.aspect_evidence + attempt.relation_evidence
    validate_source_evidence(spans, normalized_document=normalized_document)
    result = object.__new__(ValidatedEntityAspectLinkAttempt)
    for key, value in (("attempt", attempt), ("document_ref", attempt.document_ref), ("source_digest", sha256(_canonical_json({"document_ref": analysis_input.document_ref, "title": analysis_input.title, "body": analysis_input.body}).encode("utf-8")).hexdigest()), ("_token", _VALIDATION_TOKEN)):
        object.__setattr__(result, key, value)
    return result


def validate_entity_aspect_link(
    link: EntityAspectLink,
    *,
    source: ValidatedEntitySource,
    resolutions: tuple[ValidatedEntityResolution, ...],
    candidate_relationship_types: tuple[RelationshipType, ...],
    relationship_evidence_sufficient: bool,
    ambiguous_evidence_semantically_sufficient: bool = False,
) -> ValidatedEntityAspectLink:
    """Validate link against its source-bound mentions and resolved results."""
    if type(ambiguous_evidence_semantically_sufficient) is not bool:
        raise TypeError("ambiguous_evidence_semantically_sufficient must be an actual bool")
    if not isinstance(source, ValidatedEntitySource) or source._token is not _VALIDATION_TOKEN:
        raise ValueError("a source-bound validation result is required")
    _require_tuple(resolutions, "resolutions", ValidatedEntityResolution)
    if any(item._token is not _VALIDATION_TOKEN for item in resolutions):
        raise ValueError("resolution results must pass a trusted registry validation boundary")
    if link.document_ref != source.document_ref:
        raise ValueError("link document_ref does not match validated source")
    _require_tuple(candidate_relationship_types, "candidate_relationship_types")
    if candidate_relationship_types != (link.relationship_type,):
        raise ValueError("successful link requires exactly one established relationship interpretation")
    if type(relationship_evidence_sufficient) is not bool or not relationship_evidence_sufficient:
        raise ValueError("successful link requires explicit sufficient relationship evidence")
    mentions_by_id = {item.mention_id: item for item in source.entity_mentions}
    if not link.entity_mention_ids or any(mention_id not in mentions_by_id for mention_id in link.entity_mention_ids):
        raise ValueError("link references nonexistent entity mentions")
    aspects_by_id = {item.mention_id: item for item in source.aspect_mentions}
    if not link.aspect_mention_ids or any(mention_id not in aspects_by_id for mention_id in link.aspect_mention_ids):
        raise ValueError("link references missing or nonexistent source-bound aspect mentions")
    linked_aspects = tuple(aspects_by_id[mention_id] for mention_id in link.aspect_mention_ids)
    taxonomy_version, aspect_code = link.aspect_ref
    if any(item.taxonomy_version != taxonomy_version or item.code != aspect_code for item in linked_aspects):
        raise ValueError("aspect references do not match the link aspect_ref")
    results = tuple(item.result for item in resolutions)
    if len({result.mention_id for result in results}) != len(results):
        raise ValueError("duplicate resolution results are not allowed")
    if {result.mention_id for result in results} != set(link.entity_mention_ids):
        raise ValueError("resolution results must match exactly the referenced entity mentions")
    resolution_by_mention = {result.mention_id: result for result in results}
    validated_resolution_ids: list[str] = []
    for mention_id in link.entity_mention_ids:
        mention_item = mentions_by_id[mention_id]
        result = resolution_by_mention.get(mention_id)
        if result is None:
            raise ValueError("link requires a resolution result for every entity mention")
        if result.document_ref != source.document_ref:
            raise ValueError("resolution document_ref does not match validated source")
        if result.status != "resolved":
            raise ValueError("successful link requires resolved entity results")
        if result.selected_entity_id != link.entity_id:
            raise ValueError("resolution selected_entity_id does not match link entity_id")
        if result.mention_id != mention_item.mention_id:
            raise ValueError("resolution mention does not match source mention")
        validated_resolution_ids.append(result.resolution_id)
    expected_evidence = {item.evidence for item in (mentions_by_id[key] for key in link.entity_mention_ids)}
    if not expected_evidence.issubset(set(link.entity_evidence)):
        raise ValueError("link entity evidence must include evidence for each referenced mention")
    expected_aspect_evidence = {item.evidence for item in linked_aspects}
    if not expected_aspect_evidence.issubset(set(link.aspect_evidence)):
        raise ValueError("link aspect evidence must include evidence for each referenced aspect mention")
    link.validate_source_evidence(
        normalized_document=source.normalized_document,
        ambiguous_evidence_semantically_sufficient=ambiguous_evidence_semantically_sufficient,
    )
    result = object.__new__(ValidatedEntityAspectLink)
    for key, value in (("link", link), ("document_ref", source.document_ref), ("source_digest", source.source_digest), ("resolution_ids", tuple(sorted(validated_resolution_ids))), ("_token", _VALIDATION_TOKEN)):
        object.__setattr__(result, key, value)
    return result


def require_validated_entity_link(value: ValidatedEntityAspectLink) -> EntityAspectLink:
    """Downstream consumers should accept this wrapper, not a structural link."""
    if not isinstance(value, ValidatedEntityAspectLink) or value._token is not _VALIDATION_TOKEN:
        raise ValueError("downstream use requires a validated entity-aspect link")
    return value.link


def require_validated_entity_link_attempt(value: ValidatedEntityAspectLinkAttempt) -> EntityAspectLinkAttempt:
    """Downstream consumers must distinguish validated attempts from raw structures."""
    if not isinstance(value, ValidatedEntityAspectLinkAttempt) or value._token is not _VALIDATION_TOKEN:
        raise ValueError("downstream use requires a source-validated entity-link attempt")
    return value.attempt


def _validate_range(field: str, start: int, end: int) -> None:
    if field not in ("title", "body"):
        raise ValueError("field must be title or body")
    if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int):
        raise TypeError("offsets must be integers, not booleans")
    if start < 0 or end <= start:
        raise ValueError("offsets must satisfy 0 <= start < end")


def _validate_refs(values: tuple[str, ...], name: str, *, allow_empty: bool = False) -> None:
    if not allow_empty and not values:
        raise ValueError(f"{name} must be non-empty")
    for value in values:
        _nonempty(value, name)


def _validate_unique_refs(values: tuple[str, ...], name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must contain unique references")


def _validate_aspect_ref(value: tuple[str, str]) -> None:
    if not isinstance(value, tuple) or len(value) != 2:
        raise ValueError("aspect_ref must be (taxonomy_version, aspect_code)")
    _nonempty(value[0], "taxonomy version")
    _nonempty(value[1], "aspect code")


class DeterministicIdFactory:
    """Canonical JSON + SHA-256 IDs; the in-memory collision ledger is process-local.

    Persistence adapters must store the canonical payload with each ID and call
    verify_existing_payload when an ID already exists. Separate factory instances
    cannot detect collisions without that shared persisted payload.
    """

    def __init__(self) -> None:
        self._payload_by_id: dict[str, str] = {}

    def create(self, kind: str, payload: dict[str, object]) -> str:
        _nonempty(kind, "kind")
        canonical = _canonical_json(payload)
        digest = sha256(canonical.encode("utf-8")).hexdigest()
        identifier = f"{kind}:v1:{digest}"
        previous = self._payload_by_id.get(identifier)
        if previous is not None and previous != canonical:
            raise RuntimeError("deterministic ID collision: digest maps to different canonical payloads")
        self._payload_by_id[identifier] = canonical
        return identifier

    def verify_existing_payload(self, identifier: str, kind: str, payload: dict[str, object], existing_canonical_payload: str) -> None:
        """Cross-instance/persisted collision check for an existing stored ID."""
        canonical = _canonical_json(payload)
        expected = f"{kind}:v1:{sha256(canonical.encode('utf-8')).hexdigest()}"
        if identifier != expected:
            raise ValueError("identifier does not match canonical payload")
        if existing_canonical_payload != canonical:
            raise RuntimeError("deterministic ID collision against existing canonical payload")

    def mention_id(self, *, document_ref: str, field: str, start: int, end: int, observation_kind: str, security_namespace: str | None, extractor_version: str) -> str:
        return self.create("mention", _mention_payload(document_ref, field, start, end, observation_kind, security_namespace, extractor_version))

    def resolution_id(self, *, document_ref: str, mention_id: str, registry_version: str, resolver_version: str, status: str, selected_entity_id: str | None, rationale_code: str, candidates: tuple[EntityCandidate, ...], review_only_candidates: tuple[EntityCandidate, ...]) -> str:
        return self.create("resolution", _resolution_payload(document_ref, mention_id, registry_version, resolver_version, status, selected_entity_id, rationale_code, candidates, review_only_candidates))

    def link_id(self, *, document_ref: str, entity_id: str, entity_mention_ids: tuple[str, ...], aspect_ref: tuple[str, str], aspect_mention_ids: tuple[str, ...], relationship_type: str, linker_version: str) -> str:
        return self.create("entity-link", _link_payload(document_ref, entity_id, entity_mention_ids, aspect_ref, aspect_mention_ids, relationship_type, linker_version))

    def attempt_id(self, *, document_ref: str, entity_mention_ids: tuple[str, ...], candidate_entity_ids: tuple[str, ...], aspect_ref: tuple[str, str] | None, aspect_mention_ids: tuple[str, ...], candidate_relationship_types: tuple[str, ...], relationship_type: str, ambiguity_basis: str, status: str, reason_code: str, linker_version: str) -> str:
        return self.create("entity-link-attempt", _attempt_payload(document_ref, entity_mention_ids, candidate_entity_ids, aspect_ref, aspect_mention_ids, candidate_relationship_types, relationship_type, ambiguity_basis, status, reason_code, linker_version))


def _canonical_candidates(candidates: tuple[EntityCandidate, ...]) -> list[dict[str, object]]:
    records = [{"entity_id": c.entity_id, "match_basis": c.match_basis, "supporting_security_ids": sorted(c.supporting_security_ids), "supporting_identifier_refs": sorted(c.supporting_identifier_refs), "provenance_refs": sorted(c.provenance_refs), "supporting_evidence": sorted(({"evidence_kind": e.evidence_kind, "source_ref": e.source_ref, "verified": e.verified, "fuzzy_only": e.fuzzy_only, "context_rule_id": e.context_rule_id} for e in c.supporting_evidence), key=lambda item: (item["evidence_kind"], item["source_ref"], item["verified"], item["fuzzy_only"], str(item["context_rule_id"] or "")))} for c in candidates]
    return sorted(records, key=lambda item: (str(item["entity_id"]), str(item["match_basis"])))


def _mention_payload(document_ref: str, field: str, start: int, end: int, observation_kind: str, security_namespace: str | None, extractor_version: str) -> dict[str, object]:
    return {"document_ref": document_ref, "field": field, "start": start, "end": end, "observation_kind": observation_kind, "security_namespace": security_namespace, "extractor_version": extractor_version}


def _resolution_payload(document_ref: str, mention_id: str, registry_version: str, resolver_version: str, status: str, selected_entity_id: str | None, rationale_code: str, candidates: tuple[EntityCandidate, ...], review_only_candidates: tuple[EntityCandidate, ...]) -> dict[str, object]:
    return {"document_ref": document_ref, "mention_id": mention_id, "registry_version": registry_version, "resolver_version": resolver_version, "status": status, "selected_entity_id": selected_entity_id, "rationale_code": rationale_code, "candidates": _canonical_candidates(candidates), "review_only_candidates": _canonical_candidates(review_only_candidates)}


def _link_payload(document_ref: str, entity_id: str, entity_mention_ids: tuple[str, ...], aspect_ref: tuple[str, str], aspect_mention_ids: tuple[str, ...], relationship_type: str, linker_version: str) -> dict[str, object]:
    return {"document_ref": document_ref, "entity_id": entity_id, "entity_mention_ids": sorted(entity_mention_ids), "aspect_ref": list(aspect_ref), "aspect_mention_ids": sorted(aspect_mention_ids), "relationship_type": relationship_type, "linker_version": linker_version}


def _attempt_payload(document_ref: str, entity_mention_ids: tuple[str, ...], candidate_entity_ids: tuple[str, ...], aspect_ref: tuple[str, str] | None, aspect_mention_ids: tuple[str, ...], candidate_relationship_types: tuple[str, ...], relationship_type: str, ambiguity_basis: str, status: str, reason_code: str, linker_version: str) -> dict[str, object]:
    return {"document_ref": document_ref, "entity_mention_ids": sorted(entity_mention_ids), "candidate_entity_ids": sorted(candidate_entity_ids), "aspect_ref": list(aspect_ref) if aspect_ref else None, "aspect_mention_ids": sorted(aspect_mention_ids), "candidate_relationship_types": sorted(candidate_relationship_types), "relationship_type": relationship_type, "ambiguity_basis": ambiguity_basis, "status": status, "reason_code": reason_code, "linker_version": linker_version}
