"""Dependency-light data contracts for financial intelligence stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


SentimentLabel = Literal["positive", "negative", "neutral", "mixed"]
FindingStatus = Literal["classified", "abstained"]
ResultStatus = Literal["complete", "partial", "no_result"]
SourceField = Literal["title", "body"]
EntityResolution = Literal["resolved", "ambiguous", "unresolved"]
ScopeKind = Literal["document", "reporting_period", "event"]


class AlignmentError(ValueError):
    """Raised when normalized text cannot be mapped reliably to its source."""


@dataclass(frozen=True)
class AnalysisInput:
    """Original announcement inputs, retaining title/body and time fields separately."""

    document_ref: str
    title: str | None = None
    body: str | None = None
    source_name: str | None = None
    published_at: datetime | None = None
    published_at_raw: str | None = None
    published_at_unzoned: datetime | None = None
    timezone_status: str = "unknown"
    language_hint: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.document_ref, str) or not self.document_ref.strip():
            raise ValueError("document_ref must be non-empty text")
        for field_name in ("title", "body"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string or None")
        title_usable = self.title is not None and bool(self.title.strip())
        body_usable = self.body is not None and bool(self.body.strip())
        if not title_usable and not body_usable:
            raise ValueError("at least one of title or body must contain usable text")
        if self.published_at_raw is not None and not isinstance(self.published_at_raw, str):
            raise TypeError("published_at_raw must be a string or None")
        if self.published_at is not None:
            if not isinstance(self.published_at, datetime):
                raise TypeError("published_at must be a datetime or None")
            if self.published_at.tzinfo is None or self.published_at.utcoffset() is None:
                raise ValueError("published_at must already be timezone-aware; no timezone is inferred")
            if self.timezone_status == "unknown":
                raise ValueError("published_at requires caller-confirmed timezone semantics")
        if self.published_at_unzoned is not None:
            if not isinstance(self.published_at_unzoned, datetime):
                raise TypeError("published_at_unzoned must be a datetime or None")
            if self.published_at_unzoned.tzinfo is not None:
                raise ValueError("published_at_unzoned must remain timezone-naive")


_VERIFIED_TIME_TOKEN = object()


@dataclass(frozen=True, init=False)
class VerifiedEffectiveTime:
    """An aware publication instant gated by explicit verified timestamp semantics.

    The caller that sets an AnalysisInput timezone_status beginning with
    ``verified_`` is a trusted producer and must have verified the source's
    timestamp meaning. This wrapper does not prove external source authenticity.
    """

    document_ref: str
    instant: datetime
    _token: object


def verified_effective_time_from_input(document: AnalysisInput) -> VerifiedEffectiveTime:
    """Create a registry time only from an explicitly verified aware instant."""
    if not isinstance(document, AnalysisInput):
        raise TypeError("document must be an AnalysisInput")
    if not isinstance(document.timezone_status, str) or document.published_at is None or not document.timezone_status.startswith("verified_"):
        raise ValueError("a verified aware published_at instant is required")
    value = object.__new__(VerifiedEffectiveTime)
    object.__setattr__(value, "document_ref", document.document_ref)
    object.__setattr__(value, "instant", document.published_at)
    object.__setattr__(value, "_token", _VERIFIED_TIME_TOKEN)
    return value


@dataclass(frozen=True)
class SourceOffset:
    """Original code-point range contributing to one normalized code point."""

    start: int
    end: int
    ambiguous: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.start, bool) or isinstance(self.end, bool) or not isinstance(self.start, int) or not isinstance(self.end, int):
            raise TypeError("source offsets must be integers, not booleans")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("source offsets must satisfy 0 <= start < end")


@dataclass(frozen=True)
class NormalizedDocument:
    """Original and normalized fields with per-code-point source alignment."""

    document_ref: str
    original_title: str | None
    original_body: str | None
    normalized_title: str | None
    normalized_body: str | None
    title_offsets: tuple[SourceOffset, ...]
    body_offsets: tuple[SourceOffset, ...]
    normalization_version: str

    def __post_init__(self) -> None:
        for normalized, offsets, name in (
            (self.normalized_title, self.title_offsets, "title"),
            (self.normalized_body, self.body_offsets, "body"),
        ):
            if normalized is None and offsets:
                raise ValueError(f"absent normalized {name} cannot have offsets")
            if normalized is not None and len(normalized) != len(offsets):
                raise ValueError(f"normalized {name} length must match its alignment map")
            original = self.original_title if name == "title" else self.original_body
            if original is None and normalized is not None:
                raise ValueError(f"absent original {name} cannot have normalized text")
            if original is not None and any(item.end > len(original) for item in offsets):
                raise ValueError(f"{name} alignment exceeds original field length")


@dataclass(frozen=True)
class EvidenceSpan:
    """Evidence quoted exactly from an original title/body field."""

    field: SourceField
    start: int
    end: int
    quote: str
    role: Literal["entity", "aspect", "sentiment", "relation"]
    alignment_ambiguous: bool = False

    def __post_init__(self) -> None:
        if self.field not in ("title", "body"):
            raise ValueError("field must be 'title' or 'body'")
        if isinstance(self.start, bool) or isinstance(self.end, bool) or not isinstance(self.start, int) or not isinstance(self.end, int):
            raise TypeError("evidence offsets must be integers, not booleans")
        if self.start < 0:
            raise ValueError("start must be >= 0")
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        if not isinstance(self.quote, str):
            raise TypeError("quote must be a string")
        if self.role not in ("entity", "aspect", "sentiment", "relation"):
            raise ValueError("role must be entity, aspect, sentiment, or relation")
        if type(self.alignment_ambiguous) is not bool:
            raise TypeError("alignment_ambiguous must be an actual bool")


@dataclass(frozen=True)
class CompanyMention:
    """A company mention span; linking is optional and may remain unresolved."""

    display_name: str
    field: SourceField
    start: int
    end: int
    identifier: str | None = None
    resolution: EntityResolution = "unresolved"
    confidence: float | None = None

    def __post_init__(self) -> None:
        _validate_mention(self.display_name, self.field, self.start, self.end)
        if self.resolution not in ("resolved", "ambiguous", "unresolved"):
            raise ValueError("invalid company resolution status")
        if self.resolution == "resolved" and not self.identifier:
            raise ValueError("resolved company mention requires an identifier")
        _validate_optional_confidence(self.confidence)


@dataclass(frozen=True)
class AspectMention:
    """A taxonomy-coded aspect span."""

    code: str
    label: str
    field: SourceField
    start: int
    end: int
    confidence: float | None = None
    mention_id: str | None = None
    document_ref: str | None = None
    taxonomy_version: str | None = None
    evidence: EvidenceSpan | None = None

    def __post_init__(self) -> None:
        _validate_mention(self.label, self.field, self.start, self.end)
        if not self.code.strip():
            raise ValueError("aspect code must be non-empty")
        _validate_optional_confidence(self.confidence)
        for name in ("mention_id", "document_ref", "taxonomy_version"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be non-empty text when supplied")
        if self.evidence is not None:
            if not isinstance(self.evidence, EvidenceSpan):
                raise TypeError("evidence must be an EvidenceSpan or None")
            if self.evidence.role != "aspect" or (self.evidence.field, self.evidence.start, self.evidence.end) != (self.field, self.start, self.end):
                raise ValueError("aspect evidence must use role aspect and match the mention offsets")


@dataclass(frozen=True)
class AspectFinding:
    """One entity/aspect result with explicit classified or abstained status."""

    finding_id: str
    aspect_code: str
    status: FindingStatus
    sentiment: SentimentLabel | None
    company_identifier: str | None = None
    company_mentions: tuple[CompanyMention, ...] = ()
    aspect_mentions: tuple[AspectMention, ...] = ()
    confidence: float | None = None
    evidence: tuple[EvidenceSpan, ...] = ()
    abstention_reason: str | None = None
    scope_kind: ScopeKind = "document"
    scope_label: str | None = None
    model_version: str | None = None

    def __post_init__(self) -> None:
        if not self.finding_id.strip() or not self.aspect_code.strip():
            raise ValueError("finding_id and aspect_code must be non-empty")
        if self.status == "classified":
            if self.sentiment not in ("positive", "negative", "neutral", "mixed"):
                raise ValueError("classified findings require an approved sentiment label")
            if self.abstention_reason is not None:
                raise ValueError("classified findings cannot have an abstention reason")
        elif self.status == "abstained":
            if self.sentiment is not None:
                raise ValueError("abstained findings must not have a sentiment label")
            if not self.abstention_reason or not self.abstention_reason.strip():
                raise ValueError("abstained findings require an explicit reason")
        else:
            raise ValueError("status must be classified or abstained")
        if self.scope_kind not in ("document", "reporting_period", "event"):
            raise ValueError("invalid finding scope")
        if self.scope_kind != "document" and not self.scope_label:
            raise ValueError("event/period findings require a scope label")
        _validate_optional_confidence(self.confidence)


@dataclass(frozen=True)
class FinancialIntelligenceResult:
    """Pipeline output contract, independent of storage and model frameworks."""

    document_ref: str
    pipeline_version: str
    taxonomy_version: str
    model_name: str
    model_version: str
    findings: tuple[AspectFinding, ...] = ()
    status: ResultStatus = "no_result"
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (self.document_ref, self.pipeline_version, self.taxonomy_version, self.model_name, self.model_version)
        ):
            raise ValueError("document and version metadata must be non-empty strings")
        if self.status not in ("complete", "partial", "no_result"):
            raise ValueError("invalid result status")


def _validate_mention(text: str, field_name: str, start: int, end: int) -> None:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("mention text must be non-empty")
    if field_name not in ("title", "body"):
        raise ValueError("field must be 'title' or 'body'")
    if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int):
        raise TypeError("mention offsets must be integers, not booleans")
    if start < 0 or end <= start:
        raise ValueError("mention offsets must satisfy 0 <= start < end")


def _validate_optional_confidence(confidence: float | None) -> None:
    """Calibration is not implemented; confidence remains unavailable."""
    if confidence is not None:
        raise ValueError("confidence is unavailable until calibration is implemented")
