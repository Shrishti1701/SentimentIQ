"""Map Python Unicode code-point offsets back to original title/body fields.

All ranges are half-open `[start, end)` character positions. Evidence offsets
are always measured in the original source field, never in UTF-8 bytes or a
combined/normalized document string.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from intelligence.contracts import AlignmentError, EvidenceSpan, NormalizedDocument
from processing.cleaner import normalize_text


SourceField = Literal["title", "body"]


@dataclass(frozen=True)
class MappedSpan:
    """Original-field range covering a normalized range."""

    field: SourceField
    start: int
    end: int
    ambiguous: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.start, bool) or isinstance(self.end, bool) or not isinstance(self.start, int) or not isinstance(self.end, int):
            raise TypeError("mapped offsets must be integers, not booleans")
        if self.field not in ("title", "body"):
            raise ValueError("field must be 'title' or 'body'")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("mapped offsets must satisfy 0 <= start < end")


def map_normalized_span(
    document: NormalizedDocument,
    field: SourceField,
    start: int,
    end: int,
) -> MappedSpan:
    """Map normalized `[start, end)` code-point indices to the original field.

    If normalization composed multiple original code points or collapsed a
    whitespace run, the result covers all contributing original characters
    and sets `ambiguous=True`. It never returns a guessed partial source span.
    """
    if field == "title":
        original = document.original_title
        normalized = document.normalized_title
        offsets = document.title_offsets
    elif field == "body":
        original = document.original_body
        normalized = document.normalized_body
        offsets = document.body_offsets
    else:
        raise ValueError("field must be 'title' or 'body'")

    if original is None or normalized is None:
        raise ValueError(f"original {field} field is absent")
    if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int):
        raise TypeError("offsets must be integers, not booleans")
    if start < 0 or end <= start or end > len(normalized):
        raise ValueError("normalized offsets must satisfy 0 <= start < end <= field length")
    if len(offsets) != len(normalized):
        raise AlignmentError("normalized text and alignment map lengths do not match")

    expected_text, expected_offsets = normalize_text(original)
    if normalized != expected_text or offsets != expected_offsets:
        raise AlignmentError("normalized text or alignment map does not match the original field")

    selected = offsets[start:end]
    source_start = min(item.start for item in selected)
    source_end = max(item.end for item in selected)
    has_gap_or_overlap = any(
        left.end != right.start for left, right in zip(selected, selected[1:])
    )
    ambiguous = has_gap_or_overlap or any(item.ambiguous for item in selected)
    if source_start < 0 or source_end > len(original) or source_end <= source_start:
        raise ValueError("alignment map produced an invalid original range")

    return MappedSpan(field, source_start, source_end, ambiguous)


def validate_evidence_span(
    span: EvidenceSpan,
    *,
    original_title: str | None,
    original_body: str | None,
) -> None:
    """Raise ValueError unless an evidence quote exactly matches its source slice."""
    if span.field == "title":
        original = original_title
    elif span.field == "body":
        original = original_body
    else:
        raise ValueError("field must be 'title' or 'body'")

    if original is None:
        raise ValueError(f"original {span.field} field is absent")
    if span.start < 0:
        raise ValueError("start must be >= 0")
    if span.end <= span.start:
        raise ValueError("end must be greater than start")
    if span.end > len(original):
        raise ValueError("end exceeds original field length")
    if span.quote != original[span.start:span.end]:
        raise ValueError("quote must exactly equal the original field slice")


def evidence_from_normalized_span(
    document: NormalizedDocument,
    *,
    field: SourceField,
    start: int,
    end: int,
    role: str,
) -> EvidenceSpan:
    """Create validated evidence from normalized positions, retaining source offsets."""
    mapped = map_normalized_span(document, field, start, end)
    original = document.original_title if field == "title" else document.original_body
    assert original is not None
    span = EvidenceSpan(
        field=field,
        start=mapped.start,
        end=mapped.end,
        quote=original[mapped.start:mapped.end],
        role=role,
        alignment_ambiguous=mapped.ambiguous,
    )
    validate_evidence_span(
        span,
        original_title=document.original_title,
        original_body=document.original_body,
    )
    return span
