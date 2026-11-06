"""Conservative financial text normalization with source-offset alignment."""

from __future__ import annotations

import unicodedata

from intelligence.contracts import AlignmentError, AnalysisInput, NormalizedDocument, SourceOffset


NORMALIZATION_VERSION = "nfc-whitespace-v1"


def _nfc_with_alignment(text: str) -> tuple[str, tuple[SourceOffset, ...]]:
    """Apply NFC incrementally while tracking source ranges for each output char.

    Appending a combining character can replace earlier normalized output. In
    that case the replacement is mapped to the complete original range that
    contributed to it, and marked ambiguous so later evidence keeps that full
    source range instead of inventing a narrower offset.
    """
    normalized = ""
    offsets: list[SourceOffset] = []

    for source_index, character in enumerate(text):
        updated = unicodedata.normalize("NFC", normalized + character)
        if updated == normalized + character:
            offsets.append(SourceOffset(source_index, source_index + 1))
            normalized = updated
            continue

        common_prefix = 0
        max_prefix = min(len(normalized), len(updated))
        while common_prefix < max_prefix and normalized[common_prefix] == updated[common_prefix]:
            common_prefix += 1

        common_suffix = 0
        while (
            common_suffix < len(normalized) - common_prefix
            and common_suffix < len(updated) - common_prefix
            and normalized[len(normalized) - common_suffix - 1]
            == updated[len(updated) - common_suffix - 1]
        ):
            common_suffix += 1

        old_middle_end = len(normalized) - common_suffix
        updated_middle_end = len(updated) - common_suffix
        replaced_offsets = offsets[common_prefix:old_middle_end]
        source_start = min(
            [source_index, *(offset.start for offset in replaced_offsets)]
        )
        source_end = max(
            [source_index + 1, *(offset.end for offset in replaced_offsets)]
        )
        replacement_count = updated_middle_end - common_prefix
        replacement_offsets = [
            SourceOffset(source_start, source_end, ambiguous=True)
            for _ in range(replacement_count)
        ]
        suffix_offsets = offsets[old_middle_end:] if common_suffix else []
        offsets = offsets[:common_prefix] + replacement_offsets + suffix_offsets
        normalized = updated

    expected = unicodedata.normalize("NFC", text)
    if normalized != expected or len(offsets) != len(expected):
        raise AlignmentError("NFC normalization could not be aligned to the original field")

    return normalized, tuple(offsets)


def _normalize_field(text: str | None) -> tuple[str | None, tuple[SourceOffset, ...]]:
    if text is None:
        return None, ()
    if not isinstance(text, str):
        raise TypeError("title and body values must be strings or None")

    nfc_text, nfc_offsets = _nfc_with_alignment(text)
    chars: list[str] = []
    offsets: list[SourceOffset] = []
    index = 0

    while index < len(nfc_text):
        if not nfc_text[index].isspace():
            chars.append(nfc_text[index])
            offsets.append(nfc_offsets[index])
            index += 1
            continue

        whitespace_start = index
        while index < len(nfc_text) and nfc_text[index].isspace():
            index += 1
        # Trim only leading/trailing whitespace from the model view. Internal
        # whitespace becomes one ASCII space mapped to the full original run.
        if whitespace_start == 0 or index == len(nfc_text):
            continue

        run = nfc_offsets[whitespace_start:index]
        chars.append(" ")
        offsets.append(
            SourceOffset(
                min(item.start for item in run),
                max(item.end for item in run),
                ambiguous=(len(run) > 1 or any(item.ambiguous for item in run)),
            )
        )

    return "".join(chars), tuple(offsets)


def normalize_document(document: AnalysisInput) -> NormalizedDocument:
    """Normalize title and body independently and retain per-field alignment."""
    title, title_offsets = _normalize_field(document.title)
    body, body_offsets = _normalize_field(document.body)
    return NormalizedDocument(
        document_ref=document.document_ref,
        original_title=document.title,
        original_body=document.body,
        normalized_title=title,
        normalized_body=body,
        title_offsets=title_offsets,
        body_offsets=body_offsets,
        normalization_version=NORMALIZATION_VERSION,
    )


def normalize_text(text: str) -> tuple[str, tuple[SourceOffset, ...]]:
    """Normalize one text field and return normalized text plus offset entries."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    normalized, offsets = _normalize_field(text)
    assert normalized is not None
    return normalized, offsets


def clean_text(text: str) -> str:
    """Compatibility helper returning only the conservative normalized text."""
    return normalize_text(text)[0]
