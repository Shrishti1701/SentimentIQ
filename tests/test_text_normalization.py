from dataclasses import replace

import pytest

from intelligence.contracts import AlignmentError, AnalysisInput, EvidenceSpan, SourceOffset
from processing import cleaner
from processing.cleaner import clean_text, normalize_document, normalize_text
from processing.text_alignment import (
    evidence_from_normalized_span,
    map_normalized_span,
    validate_evidence_span,
)


def test_collapses_multiple_spaces_and_newlines_without_losing_alignment():
    original = "Revenue   increased\nby 25%."
    normalized, offsets = normalize_text(original)

    assert normalized == "Revenue increased by 25%."
    assert len(offsets) == len(normalized)
    assert normalized.endswith("25%.")


def test_preserves_negation_punctuation_currency_percentages_decimals_and_dates():
    original = "Profit did not increase. Revenue increased by 25%; cash: ₹1,250.50 crore on 04-Nov-2026."

    normalized = clean_text(original)

    assert normalized == original
    assert "did not increase." in normalized
    assert "25%;" in normalized
    assert "₹1,250.50 crore" in normalized
    assert "04-Nov-2026" in normalized


def test_nfc_combining_accent_maps_back_to_full_original_sequence():
    original = "Cafe\u0301 revenue increased."
    normalized, offsets = normalize_text(original)
    start = normalized.index("Café")
    mapped = map_normalized_span(
        normalize_document(AnalysisInput(document_ref="unicode", body=original)),
        "body",
        start,
        start + len("Café"),
    )

    assert normalized == "Café revenue increased."
    assert offsets[start + 3].ambiguous is True
    assert (mapped.start, mapped.end) == (0, len("Cafe\u0301"))
    assert mapped.ambiguous is True
    assert original[mapped.start:mapped.end] == "Cafe\u0301"


def test_title_and_body_normalize_independently_and_keep_field_offsets():
    source = AnalysisInput(
        document_ref="separate-fields",
        title="  Revenue\nup  ",
        body="Profit  did not increase.",
    )
    document = normalize_document(source)

    assert document.original_title == "  Revenue\nup  "
    assert document.original_body == "Profit  did not increase."
    assert document.normalized_title == "Revenue up"
    assert document.normalized_body == "Profit did not increase."
    title_span = map_normalized_span(document, "title", 0, len("Revenue"))
    body_start = document.normalized_body.index("did not")
    body_span = map_normalized_span(document, "body", body_start, body_start + len("did not"))
    assert title_span.field == "title"
    assert source.title[title_span.start:title_span.end] == "Revenue"
    assert body_span.field == "body"
    assert source.body[body_span.start:body_span.end] == "did not"


def test_whitespace_collapse_maps_to_the_complete_source_run():
    original = "Profit \t\n did not increase."
    document = normalize_document(AnalysisInput(document_ref="space-map", body=original))
    space_index = document.normalized_body.index(" did")
    mapped = map_normalized_span(document, "body", space_index, space_index + 1)

    assert original[mapped.start:mapped.end] == " \t\n "
    assert mapped.ambiguous is True


def test_evidence_created_from_normalized_span_is_exact_original_slice():
    original = "Profit  did not increase."
    document = normalize_document(AnalysisInput(document_ref="evidence", body=original))
    start = document.normalized_body.index("did not")
    span = evidence_from_normalized_span(
        document,
        field="body",
        start=start,
        end=start + len("did not"),
        role="sentiment",
    )

    assert (span.start, span.end) == (8, 15)
    assert span.quote == "did not"
    validate_evidence_span(span, original_title=None, original_body=original)


def test_evidence_validation_rejects_out_of_bounds_and_wrong_quotes():
    with pytest.raises(ValueError, match="end exceeds"):
        validate_evidence_span(
            EvidenceSpan(field="body", start=0, end=8, quote="Revenue", role="aspect"),
            original_title=None,
            original_body="Rev",
        )
    with pytest.raises(ValueError, match="exactly equal"):
        validate_evidence_span(
            EvidenceSpan(field="body", start=0, end=3, quote="Bad", role="aspect"),
            original_title=None,
            original_body="Rev",
        )
    with pytest.raises(ValueError, match="absent"):
        validate_evidence_span(
            EvidenceSpan(field="title", start=0, end=1, quote="x", role="entity"),
            original_title=None,
            original_body="x",
        )


def test_normalized_span_validation_rejects_invalid_ranges_and_fields():
    document = normalize_document(AnalysisInput(document_ref="bad-span", body="Revenue"))

    with pytest.raises(ValueError, match="field"):
        map_normalized_span(document, "summary", 0, 1)
    with pytest.raises(ValueError, match="normalized offsets"):
        map_normalized_span(document, "body", -1, 2)
    with pytest.raises(ValueError, match="normalized offsets"):
        map_normalized_span(document, "body", 1, 1)


def test_repeated_identical_phrases_map_to_the_selected_occurrence():
    original = "Revenue grew. Revenue grew."
    document = normalize_document(AnalysisInput(document_ref="repeat", body=original))
    second = document.normalized_body.rindex("Revenue grew")
    mapped = map_normalized_span(document, "body", second, second + len("Revenue grew"))
    assert original[mapped.start:mapped.end] == "Revenue grew"
    assert mapped.start == second


def test_first_and_last_character_boundaries_are_half_open():
    original = "Revenue."
    document = normalize_document(AnalysisInput(document_ref="edges", body=original))
    first = map_normalized_span(document, "body", 0, 1)
    last = map_normalized_span(document, "body", len(document.normalized_body) - 1, len(document.normalized_body))
    assert (first.start, first.end) == (0, 1)
    assert (last.start, last.end) == (len(original) - 1, len(original))


def test_nfc_and_whitespace_normalization_keep_explicit_ambiguous_alignment():
    original = "Cafe\u0301  \n revenue"
    document = normalize_document(AnalysisInput(document_ref="nfc-space", body=original))
    assert document.normalized_body == "Caf\u00e9 revenue"
    accent = map_normalized_span(document, "body", 3, 4)
    space_index = document.normalized_body.index(" ")
    space = map_normalized_span(document, "body", space_index, space_index + 1)
    assert original[accent.start:accent.end] == "e\u0301"
    assert accent.ambiguous is True
    assert original[space.start:space.end] == "  \n "
    assert space.ambiguous is True


@pytest.mark.parametrize("start,end,expected", [(3, 4, "e\u0301"), (2, 4, "fe\u0301"), (3, 5, "e\u0301X")])
def test_spans_touching_ambiguous_nfc_mapping_keep_full_contributor(start, end, expected):
    original = "Cafe\u0301X"
    document = normalize_document(AnalysisInput(document_ref="ambiguous-edge", body=original))
    mapped = map_normalized_span(document, "body", start, end)
    assert original[mapped.start:mapped.end] == expected
    assert mapped.ambiguous is True


def test_spans_beginning_or_ending_at_collapsed_whitespace_are_ambiguous():
    original = "A  \n B"
    document = normalize_document(AnalysisInput(document_ref="space-edge", body=original))
    space = document.normalized_body.index(" ")
    starts_at_space = map_normalized_span(document, "body", space, space + 2)
    ends_at_space = map_normalized_span(document, "body", 0, space + 1)
    assert starts_at_space.ambiguous and ends_at_space.ambiguous
    assert original[starts_at_space.start:starts_at_space.end] == "  \n B"
    assert original[ends_at_space.start:ends_at_space.end] == "A  \n "


def test_corrupted_alignment_map_fails_explicitly():
    document = normalize_document(AnalysisInput(document_ref="corrupt", body="Revenue rose"))
    bad_offsets = list(document.body_offsets)
    bad_offsets[0] = SourceOffset(1, 2)
    corrupted = replace(document, body_offsets=tuple(bad_offsets))
    with pytest.raises(AlignmentError, match="does not match"):
        map_normalized_span(corrupted, "body", 0, 1)


def test_unexpected_nfc_alignment_does_not_fall_back_to_whole_field(monkeypatch):
    with pytest.raises(AlignmentError, match="could not be aligned"):
        with monkeypatch.context() as local_patch:
            calls = iter(("z", "a"))
            local_patch.setattr(cleaner.unicodedata, "normalize", lambda form, value: next(calls))
            cleaner._nfc_with_alignment("a")


@pytest.mark.parametrize("start,end", [(True, 1), (0, False)])
def test_boolean_offsets_are_rejected(start, end):
    document = normalize_document(AnalysisInput(document_ref="bool-offset", body="Revenue"))
    with pytest.raises(TypeError, match="booleans"):
        map_normalized_span(document, "body", start, end)
    with pytest.raises(TypeError, match="booleans"):
        EvidenceSpan(field="body", start=start, end=end, quote="x", role="aspect")


def test_out_of_range_original_evidence_offset_is_rejected():
    span = EvidenceSpan(field="body", start=0, end=2, quote="Re", role="aspect")
    with pytest.raises(ValueError, match="end exceeds"):
        validate_evidence_span(span, original_title=None, original_body="R")


@pytest.mark.parametrize("title,body,field,text", [("Revenue", None, "title", "Revenue"), (None, "Profit", "body", "Profit")])
def test_title_only_and_body_only_documents_align(title, body, field, text):
    document = normalize_document(AnalysisInput(document_ref="one-field", title=title, body=body))
    normalized = document.normalized_title if field == "title" else document.normalized_body
    assert normalized == text
    mapped = map_normalized_span(document, field, 0, len(text))
    assert mapped.start == 0 and mapped.end == len(text)
