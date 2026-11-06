from dataclasses import replace

import pytest

from intelligence.contracts import AlignmentError, AnalysisInput, EvidenceSpan, SourceOffset
from intelligence.entity_contracts import DeterministicIdFactory, validate_entity_source
from intelligence.entity_extractor import extract_entity_mentions
from processing.cleaner import normalize_document


VERSION = "extractor-test-v1"


def extract(text=None, *, title=None, body=None, version=VERSION):
    if text is not None:
        body = text
    source = AnalysisInput("synthetic-doc", title=title, body=body)
    return source, extract_entity_mentions(source, extractor_version=version)


def assert_organization_outputs(source, mentions, expected):
    orgs = [item for item in mentions if item.observation_kind == "organization_name_candidate"]
    assert [item.surface_text for item in orgs] == expected
    factory = DeterministicIdFactory()
    for item in orgs:
        original = source.title if item.field == "title" else source.body
        assert original[item.start:item.end] == item.surface_text
        assert item.evidence.field == item.field
        assert item.evidence.role == "entity"
        assert item.evidence.quote == item.surface_text
        assert item.mention_id == factory.mention_id(
            document_ref=item.document_ref,
            field=item.field,
            start=item.start,
            end=item.end,
            observation_kind=item.observation_kind,
            security_namespace=item.security_namespace,
            extractor_version=item.extractor_version,
        )


@pytest.mark.parametrize(
    "suffix",
    [
        "Limited",
        "Ltd.",
        "Private Limited",
        "Pvt. Ltd.",
        "Public Limited",
        "LLP",
        "Limited Liability Partnership",
        "pRiVaTe lImItEd",
    ],
)
def test_organization_legal_suffixes_and_mixed_casing(suffix):
    source, mentions = extract(f"Synthetic Meridian {suffix} reported results.")
    orgs = [item for item in mentions if item.observation_kind == "organization_name_candidate"]
    assert len(orgs) == 1
    assert orgs[0].surface_text.endswith(suffix)
    assert source.body[orgs[0].start:orgs[0].end] == orgs[0].surface_text


def test_organization_boundaries_empty_prefix_embedded_suffix_and_punctuation():
    source, mentions = extract("(Synthetic Alpha Ltd.), Limitedness, (Synthetic Beta LLP).")
    surfaces = [item.surface_text for item in mentions if item.observation_kind == "organization_name_candidate"]
    assert surfaces == ["Synthetic Alpha Ltd.", "Synthetic Beta LLP"]
    assert all(not value.startswith(("(", " ")) for value in surfaces)
    assert all(not value.endswith((")", ".")) or value.endswith("Ltd.") for value in surfaces)


def test_embedded_suffix_does_not_create_a_false_organization_boundary():
    source, mentions = extract("AcmeLLP Holdings Limited")

    orgs = [
        item.surface_text
        for item in mentions
        if item.observation_kind == "organization_name_candidate"
    ]

    assert orgs == ["AcmeLLP Holdings Limited"]

    for item in mentions:
        if item.observation_kind == "organization_name_candidate":
            assert source.body[item.start:item.end] == item.surface_text
            assert item.evidence.quote == item.surface_text


@pytest.mark.parametrize("embedded", ["AcmeLtd", "AcmeLimited", "LLPLimited"])
def test_embedded_suffix_variants_do_not_create_false_boundaries(embedded):
    source, mentions = extract(f"{embedded} Holdings Limited")
    orgs = [item for item in mentions if item.observation_kind == "organization_name_candidate"]
    assert [item.surface_text for item in orgs] == [f"{embedded} Holdings Limited"]


def test_organization_name_prefix_casing_is_preserved_without_changing_span():
    _, mentions = extract("Synthetic Meridian pRiVaTe lImItEd")
    org = next(item for item in mentions if item.observation_kind == "organization_name_candidate")
    assert org.surface_text == "Synthetic Meridian pRiVaTe lImItEd"


def test_combining_mark_inside_organization_word_does_not_truncate_name():
    source, mentions = extract("Synthetic Cafe\u0338 Holdings Limited")
    org = next(item for item in mentions if item.observation_kind == "organization_name_candidate")
    assert org.surface_text == source.body
    assert source.body[org.start:org.end] == org.surface_text


@pytest.mark.parametrize("text", ["Limited reported results", "   Ltd. reported results", "Synthetic Meridian reported growth"])
def test_empty_prefix_and_capitalized_phrases_without_suffix_are_rejected(text):
    _, mentions = extract(text)
    assert not [item for item in mentions if item.observation_kind == "organization_name_candidate"]


def test_repeated_and_multiple_organization_names_are_preserved():
    source, mentions = extract("Synthetic Alpha Ltd. and Synthetic Beta LLP. Synthetic Alpha Ltd.")
    orgs = [item for item in mentions if item.observation_kind == "organization_name_candidate"]
    assert [item.surface_text for item in orgs] == ["Synthetic Alpha Ltd.", "Synthetic Beta LLP", "Synthetic Alpha Ltd."]
    assert len({(item.field, item.start, item.end) for item in orgs}) == 3
    assert len({item.mention_id for item in orgs}) == 3
    assert all(source.body[item.start:item.end] == item.surface_text for item in orgs)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Reported results by Synthetic Alpha Ltd.", "Synthetic Alpha Ltd."),
        ("announced strong results for Synthetic Alpha Ltd.", "Synthetic Alpha Ltd."),
        ("Company announced results by Synthetic Alpha Ltd.", "Synthetic Alpha Ltd."),
        ("Synthetic Alpha Ltd.", "Synthetic Alpha Ltd."),
        ("Synthetic Bank of India Limited reported. Synthetic Beta LLP.", "Synthetic Bank of India Limited"),
        ("Synthetic financial services Holdings Limited", "Synthetic financial services Holdings Limited"),
        ("(Synthetic Alpha Ltd.)", "Synthetic Alpha Ltd."),
    ],
)
def test_organization_boundary_excludes_preceding_clause_and_keeps_full_name(text, expected):
    _, mentions = extract(text)
    orgs = [item.surface_text for item in mentions if item.observation_kind == "organization_name_candidate"]
    assert expected in orgs
    assert all(not value.startswith(("Reported", "results by", "strong results", "Company announced")) for value in orgs)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Results of Synthetic Alpha Limited", ["Synthetic Alpha Limited"]),
        ("Reported results by Synthetic Alpha Limited", ["Synthetic Alpha Limited"]),
        ("announced strong results for Synthetic Alpha Limited", ["Synthetic Alpha Limited"]),
        ("The filing was approved for Synthetic Alpha Limited", ["Synthetic Alpha Limited"]),
        ("Strong Recovery Synthetic Alpha Limited", []),
        ("Quarterly Performance for Synthetic Alpha Limited", ["Synthetic Alpha Limited"]),
    ],
)
def test_organization_boundaries_are_conservative_for_ambiguous_clause_prefixes(text, expected):
    source, mentions = extract(text)
    orgs = [item for item in mentions if item.observation_kind == "organization_name_candidate"]
    assert [item.surface_text for item in orgs] == expected
    for mention in orgs:
        assert source.body[mention.start:mention.end] == mention.surface_text
        assert mention.evidence.quote == mention.surface_text


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "Synthetic Alpha Limited and Beta Holdings Limited",
            ["Synthetic Alpha Limited", "Beta Holdings Limited"],
        ),
        (
            "Synthetic Alpha Limited, Beta Holdings Limited, and Cedar Logistics LLP",
            ["Synthetic Alpha Limited", "Beta Holdings Limited", "Cedar Logistics LLP"],
        ),
        (
            "Synthetic Alpha Limited; Beta Holdings Limited. Cedar Logistics LLP",
            ["Synthetic Alpha Limited", "Beta Holdings Limited", "Cedar Logistics LLP"],
        ),
        (
            "Prior statement. Synthetic Alpha Limited. (Beta Holdings Limited)",
            ["Synthetic Alpha Limited", "Beta Holdings Limited"],
        ),
        (
            "Alpha Beta Gamma Delta Epsilon Zeta Eta Theta Iota Limited followed by Cedar LLP",
            ["Alpha Beta Gamma Delta Epsilon Zeta Eta Theta Iota Limited", "Cedar LLP"],
        ),
        (
            "Synthetic Bank of India Limited and Synthetic Research and Development LLP",
            ["Synthetic Bank of India Limited", "Synthetic Research and Development LLP"],
        ),
    ],
)
def test_multiple_organizations_keep_separate_defensible_spans(text, expected):
    source, mentions = extract(text)
    orgs = [item for item in mentions if item.observation_kind == "organization_name_candidate"]
    assert [item.surface_text for item in orgs] == expected
    assert all(source.body[item.start:item.end] == item.surface_text for item in orgs)
    assert all(item.evidence.quote == item.surface_text for item in orgs)


def test_completed_suffix_is_hard_boundary_for_repeated_names_and_overlapping_suffix_patterns():
    source, mentions = extract("Synthetic Alpha Limited Holdings Limited. Synthetic Alpha Limited")
    orgs = [item for item in mentions if item.observation_kind == "organization_name_candidate"]
    assert [item.surface_text for item in orgs] == [
        "Synthetic Alpha Limited",
        "Holdings Limited",
        "Synthetic Alpha Limited",
    ]
    assert len({item.mention_id for item in orgs}) == 3
    assert all(source.body[item.start:item.end] == item.surface_text for item in orgs)


def test_ambiguous_organization_start_logs_content_free_diagnostic(caplog):
    source, mentions = extract("Strong Recovery Synthetic Alpha Limited")
    assert not [item for item in mentions if item.observation_kind == "organization_name_candidate"]
    assert "ambiguous_organization_boundary_skipped" in caplog.text
    assert source.body not in caplog.text


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Strong Holdings Limited", ["Strong Holdings Limited"]),
        ("Strong Recovery Holdings Limited", ["Strong Recovery Holdings Limited"]),
        ("The Strong Recovery Synthetic Alpha Limited", []),
        ("The Synthetic Alpha Limited", ["The Synthetic Alpha Limited"]),
        ("The Synthetic Group Limited", ["The Synthetic Group Limited"]),
        ("Results Holdings Limited", ["Results Holdings Limited"]),
        ("Reported Holdings Limited", ["Reported Holdings Limited"]),
        ("Results of Synthetic Alpha Limited", ["Synthetic Alpha Limited"]),
        ("Reported results by Synthetic Alpha Limited", ["Synthetic Alpha Limited"]),
        ("announced strong results for Synthetic Alpha Limited", ["Synthetic Alpha Limited"]),
        ("The filing was approved for Synthetic Alpha Limited", ["Synthetic Alpha Limited"]),
        ("Strong Recovery Synthetic Alpha Limited", []),
    ],
)
def test_clause_vocabulary_and_leading_connectors_do_not_truncate_or_overreach(text, expected):
    source, mentions = extract(text)
    assert_organization_outputs(source, mentions, expected)


def test_field_start_name_with_clause_word_and_introduced_name_are_distinguished():
    source, mentions = extract(
        title="Strong Holdings Limited",
        body="Reported results for The Synthetic Alpha Limited",
    )
    assert_organization_outputs(
        source,
        mentions,
        ["Strong Holdings Limited", "The Synthetic Alpha Limited"],
    )


def test_completed_suffixes_and_punctuation_still_split_multiple_organizations():
    source, mentions = extract(
        "Synthetic Alpha Limited and Beta Holdings Limited or Cedar Mobility LLP; "
        "Synthetic Alpha Limited. Beta Holdings Limited"
    )
    assert_organization_outputs(
        source,
        mentions,
        [
            "Synthetic Alpha Limited",
            "Beta Holdings Limited",
            "Cedar Mobility LLP",
            "Synthetic Alpha Limited",
            "Beta Holdings Limited",
        ],
    )
    repeated = [item for item in mentions if item.observation_kind == "organization_name_candidate"]
    assert len({(item.start, item.end) for item in repeated}) == len(repeated)
    assert len({item.mention_id for item in repeated}) == len(repeated)


def test_ambiguous_lowercase_organization_boundary_is_skipped_with_diagnostic(caplog):
    _, mentions = extract("results for synthetic alpha limited")
    assert not [item for item in mentions if item.observation_kind == "organization_name_candidate"]
    assert "ambiguous_organization_boundary_skipped" in caplog.text


def test_long_organization_names_are_not_truncated_and_repetitions_have_distinct_ids():
    name = "Alpha Beta Gamma Delta Epsilon Zeta Eta Theta Iota Limited"
    source, mentions = extract(f"{name}. {name}.")
    orgs = [item for item in mentions if item.observation_kind == "organization_name_candidate"]
    assert [item.surface_text for item in orgs] == [name, name]
    assert orgs[0].start != orgs[1].start
    assert orgs[0].mention_id != orgs[1].mention_id
    assert all(source.body[item.start:item.end] == name for item in orgs)


def test_long_organization_after_clause_text_starts_at_name():
    name = "Alpha Beta Gamma Delta Epsilon Zeta Eta Theta Iota Limited"
    _, mentions = extract(f"announced strong results for {name}")
    org = next(item for item in mentions if item.observation_kind == "organization_name_candidate")
    assert org.surface_text == name


@pytest.mark.parametrize(
    "definition",
    [
        "Synthetic Alpha Ltd. (SAL)",
        "Synthetic Alpha Ltd. abbreviated as SAL",
        "Synthetic Alpha Ltd. abbreviated to SAL",
        "Synthetic Alpha Ltd. referred to as SAL",
        "hereafter SAL",
        "hereinafter referred to as SAL",
    ],
)
def test_explicit_abbreviation_definition_forms(definition):
    # The first form is parenthetical after a recognized organization. The
    # textual forms place the definition cue immediately before the acronym.
    text = definition if "(" in definition else f"{definition} in this notice."
    _, mentions = extract(text)
    abbreviations = [item for item in mentions if item.observation_kind == "abbreviation_candidate"]
    assert any(item.surface_text == "SAL" for item in abbreviations)


def test_abbreviation_title_scope_later_occurrences_and_case_sensitive_boundaries():
    source, mentions = extract(title="Synthetic Alpha Ltd. (SAL)", body="SAL reported growth; sal and XSAL did not.")
    occurrences = [item for item in mentions if item.observation_kind == "abbreviation_candidate"]
    assert [item.field for item in occurrences] == ["title", "body"]
    assert [item.surface_text for item in occurrences] == ["SAL", "SAL"]
    assert source.body[occurrences[1].start:occurrences[1].end] == "SAL"


def test_abbreviation_before_definition_is_not_emitted_as_definition_use():
    _, mentions = extract("SAL appeared first. Synthetic Alpha Ltd. (SAL).")
    abbreviations = [item for item in mentions if item.observation_kind == "abbreviation_candidate"]
    assert len(abbreviations) == 1
    assert abbreviations[0].start == 42  # definition token only


def test_textual_abbreviation_definition_allows_body_later_occurrences():
    _, mentions = extract(title="SAL is mentioned before definition", body="SAL is abbreviated as SAL; SAL follows.")
    abbreviations = [item for item in mentions if item.observation_kind == "abbreviation_candidate"]
    assert [item.surface_text for item in abbreviations] == ["SAL", "SAL"]
    assert abbreviations[0].start == 22  # defining occurrence; earlier title occurrence is excluded


def test_repeated_abbreviation_definitions_and_later_occurrences_are_preserved():
    _, mentions = extract("Synthetic Alpha Ltd. (SAL), later abbreviated as SAL. SAL appears again.")
    abbreviations = [item for item in mentions if item.observation_kind == "abbreviation_candidate"]
    assert len(abbreviations) == 3
    assert [item.surface_text for item in abbreviations] == ["SAL"] * 3
    assert len({item.start for item in abbreviations}) == 3


def test_arbitrary_uppercase_and_case_variants_are_not_inferred():
    _, mentions = extract("ABC XYZ Ltd. sal SALARY")
    abbreviations = [item.surface_text for item in mentions if item.observation_kind == "abbreviation_candidate"]
    assert abbreviations == []


@pytest.mark.parametrize("reference", ["the company", "the issuer", "the subsidiary", "the parent company"])
def test_allow_list_other_company_references(reference):
    _, mentions = extract(f"Synthetic Alpha Ltd. said {reference} grew.")
    found = [item.surface_text.casefold() for item in mentions if item.observation_kind == "other_company_reference"]
    assert found == [reference]


def test_other_references_are_case_insensitive_bounded_and_do_not_inherit_identity():
    _, mentions = extract("Synthetic Alpha Ltd. THE COMPANY reported. companywide expanded; it grew.")
    refs = [item for item in mentions if item.observation_kind == "other_company_reference"]
    assert [item.surface_text for item in refs] == ["THE COMPANY"]
    assert not any(item.surface_text.casefold() == "it" for item in mentions)


@pytest.mark.parametrize(
    "label,value,namespace",
    [
        ("NSE Symbol", "SYNTH-MER-A", "NSE"),
        ("BSE Scrip Code", "999001", "BSE"),
        ("ISIN", "ZZ1234567890", "ISIN"),
        ("nse symbol", "A", "NSE"),
        ("BSE scrip code", "1234567890", "BSE"),
        ("ISIN", "AB1234567890", "ISIN"),
    ],
)
def test_explicit_security_labels_extract_valid_synthetic_values(label, value, namespace):
    source, mentions = extract(f"{label}: {value} reported strong revenue growth")
    securities = [item for item in mentions if item.observation_kind == "security_identifier_candidate"]
    assert len(securities) == 1
    mention = securities[0]
    assert mention.surface_text == value
    assert mention.security_namespace == namespace
    assert source.body[mention.start:mention.end] == value


@pytest.mark.parametrize(
    "label,value",
    [
        ("NSE Symbol", "-SYNTH"),
        ("NSE Symbol", "S" * 33),
        ("NSE Symbol", "SYN.TH"),
        ("BSE Scrip Code", "12A"),
        ("BSE Scrip Code", "1" * 11),
        ("ISIN", "A12345678901"),
        ("ISIN", "AB123456789X"),
        ("ISIN", "AB123456789"),
    ],
)
def test_malformed_security_values_are_rejected_without_content_logging(caplog, label, value):
    _, mentions = extract(f"{label}: {value}")
    assert not [item for item in mentions if item.observation_kind == "security_identifier_candidate"]
    assert "malformed_security_identifier_value" in caplog.text
    assert value not in caplog.text


def test_security_labels_require_separators_and_bare_shapes_do_not_get_namespace():
    _, mentions = extract("NSE Symbol SYNTH-MER-A; BSE Scrip Code 999001; ZZ1234567890")
    assert not [item for item in mentions if item.observation_kind == "security_identifier_candidate"]


def test_security_value_excludes_trailing_prose_and_sentence_punctuation():
    source, mentions = extract("NSE Symbol: SYNTH-MER-A reported strong revenue growth.")
    security = next(item for item in mentions if item.observation_kind == "security_identifier_candidate")
    assert security.surface_text == "SYNTH-MER-A"
    assert source.body[security.start:security.end] == "SYNTH-MER-A"


def test_security_equals_separator_is_supported():
    _, mentions = extract("ISIN = ZZ1234567890")
    security = next(item for item in mentions if item.observation_kind == "security_identifier_candidate")
    assert (security.surface_text, security.security_namespace) == ("ZZ1234567890", "ISIN")


def test_same_value_under_different_explicit_labels_keeps_distinct_namespaces():
    _, mentions = extract("NSE Symbol: 123; BSE Scrip Code: 123")
    securities = [item for item in mentions if item.observation_kind == "security_identifier_candidate"]
    assert [(item.surface_text, item.security_namespace) for item in securities] == [("123", "NSE"), ("123", "BSE")]


def test_security_label_value_context_is_isolated_by_field_and_next_label():
    _, mentions = extract(title="NSE Symbol: SYNTH-MER-A", body="BSE Scrip Code: 999001 ISIN: ZZ1234567890")
    values = [(item.field, item.surface_text, item.security_namespace) for item in mentions if item.observation_kind == "security_identifier_candidate"]
    assert values == [("title", "SYNTH-MER-A", "NSE"), ("body", "999001", "BSE"), ("body", "ZZ1234567890", "ISIN")]


@pytest.mark.parametrize(
    "first_label,second_label,second_value,expected_namespace",
    [
        ("NSE Symbol", "BSE Scrip Code", "999001", "BSE"),
        ("NSE Symbol", "ISIN", "ZZ1234567890", "ISIN"),
        ("BSE Scrip Code", "NSE Symbol", "ABC", "NSE"),
        ("BSE Scrip Code", "ISIN", "ZZ1234567890", "ISIN"),
        ("ISIN", "NSE Symbol", "ABC", "NSE"),
        ("ISIN", "BSE Scrip Code", "999001", "BSE"),
    ],
)
def test_recognized_next_label_terminates_empty_previous_value(
    caplog, first_label, second_label, second_value, expected_namespace
):
    _, mentions = extract(f"{first_label}: {second_label}: {second_value}")
    securities = [item for item in mentions if item.observation_kind == "security_identifier_candidate"]
    assert [(item.surface_text, item.security_namespace) for item in securities] == [(second_value, expected_namespace)]
    assert "malformed_security_identifier_value" in caplog.text
    assert all(item.surface_text != second_label.split()[0] for item in securities)


@pytest.mark.parametrize(
    "first_label,malformed,second_label,second_value,expected_namespace",
    [
        ("NSE Symbol", "!bad", "BSE Scrip Code", "999001", "BSE"),
        ("NSE Symbol", "!bad", "ISIN", "ZZ1234567890", "ISIN"),
        ("BSE Scrip Code", "12A", "NSE Symbol", "SYNTH-A", "NSE"),
        ("BSE Scrip Code", "12A", "ISIN", "ZZ1234567890", "ISIN"),
        ("ISIN", "AB123", "NSE Symbol", "SYNTH-A", "NSE"),
        ("ISIN", "AB123", "BSE Scrip Code", "999001", "BSE"),
    ],
)
def test_malformed_security_value_does_not_consume_next_labeled_value(
    caplog, first_label, malformed, second_label, second_value, expected_namespace
):
    _, mentions = extract(f"{first_label}: {malformed} {second_label}: {second_value}")
    securities = [item for item in mentions if item.observation_kind == "security_identifier_candidate"]
    assert [(item.surface_text, item.security_namespace) for item in securities] == [
        (second_value, expected_namespace)
    ]
    assert "malformed_security_identifier_value" in caplog.text


def test_repeated_security_namespace_labels_are_independently_parsed():
    _, mentions = extract("NSE Symbol: SYNTH-A; NSE Symbol: SYNTH-B; BSE Scrip Code: 999001")
    securities = [item for item in mentions if item.observation_kind == "security_identifier_candidate"]
    assert [(item.surface_text, item.security_namespace) for item in securities] == [
        ("SYNTH-A", "NSE"),
        ("SYNTH-B", "NSE"),
        ("999001", "BSE"),
    ]


@pytest.mark.parametrize("label", ["NSE Symbol", "BSE Scrip Code", "ISIN"])
def test_empty_and_newline_values_are_not_taken_from_later_text(caplog, label):
    _, mentions = extract(f"{label}:\nABC")
    assert not [item for item in mentions if item.observation_kind == "security_identifier_candidate"]
    assert "malformed_security_identifier_value" in caplog.text


def test_deduplication_keeps_distinct_kinds_spans_and_occurrences(monkeypatch):
    import intelligence.entity_extractor as extractor

    original = extractor._organization_candidates

    def duplicate_rule(text, field):
        return original(text, field) + original(text, field)

    monkeypatch.setattr(extractor, "_organization_candidates", duplicate_rule)
    _, mentions = extract("Synthetic Alpha Ltd. (SAL) Synthetic Alpha Ltd.")
    orgs = [item for item in mentions if item.observation_kind == "organization_name_candidate"]
    abbrevs = [item for item in mentions if item.observation_kind == "abbreviation_candidate"]
    assert len(orgs) == 2
    assert len(abbrevs) == 1
    assert len({(item.start, item.end, item.observation_kind) for item in mentions}) == len(mentions)


def test_same_span_different_observation_kinds_are_preserved(monkeypatch):
    import intelligence.entity_extractor as extractor

    source = AnalysisInput("overlap-kinds", body="Synthetic Alpha Ltd.")
    candidate = extractor._Candidate("body", 0, len("Synthetic Alpha Ltd."), "organization_name_candidate")
    monkeypatch.setattr(extractor, "_organization_candidates", lambda text, field: [candidate])
    monkeypatch.setattr(
        extractor,
        "_security_candidates",
        lambda text, field: [extractor._Candidate(field, candidate.start, candidate.end, "security_identifier_candidate", "NSE")],
    )
    monkeypatch.setattr(extractor, "_security_context_has_linebreak", lambda document, candidate: False)
    mentions = extract_entity_mentions(source, extractor_version=VERSION)
    assert [item.observation_kind for item in mentions] == [
        "organization_name_candidate",
        "security_identifier_candidate",
    ]


def test_same_span_different_explicit_namespaces_are_preserved(monkeypatch):
    import intelligence.entity_extractor as extractor

    source = AnalysisInput("overlap-namespaces", body="SYNTH-MER-A")
    monkeypatch.setattr(
        extractor,
        "_security_candidates",
        lambda text, field: [
            extractor._Candidate(field, 0, len(text), "security_identifier_candidate", "NSE"),
            extractor._Candidate(field, 0, len(text), "security_identifier_candidate", "BSE"),
        ],
    )
    monkeypatch.setattr(extractor, "_security_context_has_linebreak", lambda document, candidate: False)
    mentions = extract_entity_mentions(source, extractor_version=VERSION)
    assert [item.security_namespace for item in mentions] == ["BSE", "NSE"]
    assert mentions[0].mention_id != mentions[1].mention_id


def test_every_mention_has_exact_original_evidence_and_passes_source_validation():
    source, mentions = extract(
        title="Synthetic Alpha Ltd. (SAL)",
        body="NSE Symbol: SYNTH-MER-A; the company reported growth.",
    )
    for mention in mentions:
        original = source.title if mention.field == "title" else source.body
        assert mention.surface_text == original[mention.start:mention.end]
        assert mention.evidence == EvidenceSpan(
            field=mention.field,
            start=mention.start,
            end=mention.end,
            quote=mention.surface_text,
            role="entity",
            alignment_ambiguous=mention.evidence.alignment_ambiguous,
        )
    validated = validate_entity_source(source, mentions, normalized_document=normalize_document(source))
    assert validated.entity_mentions == mentions


@pytest.mark.parametrize(
    "text,kind",
    [
        ("the company\u0338 expanded", "other_company_reference"),
        ("Synthetic Alpha Ltd. (SAL) SAL\u0338", "abbreviation_candidate"),
        ("Synthetic Alpha Ltd.\u0338", "organization_name_candidate"),
        ("\u0338the company expanded", "other_company_reference"),
    ],
)
def test_combining_marks_are_token_characters_and_do_not_allow_partial_candidates(text, kind):
    _, mentions = extract(text)
    found = [item for item in mentions if item.observation_kind == kind]
    if text.startswith("Synthetic Alpha Ltd. (SAL)") and "SAL\u0338" in text:
        assert len(found) == 1
        assert found[0].surface_text == "SAL"  # the definition remains; the marked occurrence is excluded
    else:
        assert not found


@pytest.mark.parametrize(
    "text,kind,expected",
    [
        ("the company, reported growth", "other_company_reference", "the company"),
        ("Synthetic Alpha Ltd. (SAL), SAL.", "abbreviation_candidate", "SAL"),
        ("Synthetic Alpha Ltd.; results", "organization_name_candidate", "Synthetic Alpha Ltd."),
        ("(the issuer) expanded", "other_company_reference", "the issuer"),
    ],
)
def test_combining_mark_boundary_fix_preserves_matches_before_punctuation(text, kind, expected):
    _, mentions = extract(text)
    assert any(item.observation_kind == kind and item.surface_text == expected for item in mentions)


@pytest.mark.parametrize(
    "text,kind",
    [
        ("the company\u0301\u0323 expanded", "other_company_reference"),
        ("Synthetic Alpha Ltd. (SAL) SAL\u0301\u0323", "abbreviation_candidate"),
        ("Synthetic Alpha Ltd.\u0301\u0323", "organization_name_candidate"),
        ("\u0301\u0323the company expanded", "other_company_reference"),
    ],
)
def test_multiple_combining_marks_cannot_create_partial_token_boundaries(text, kind):
    _, mentions = extract(text)
    found = [item for item in mentions if item.observation_kind == kind]
    if "(SAL)" in text:
        # The parenthetical definition remains a separate valid occurrence;
        # neither mark-attached later occurrence may be partially emitted.
        assert [item.surface_text for item in found] == ["SAL"]
    else:
        assert found == []


def test_multiple_combining_marks_with_punctuation_keep_exact_source_evidence():
    source, mentions = extract("Synthetic Alpha Ltd. (SAL), SAL!\u0301\u0323 then the company, grew.")
    abbrevs = [item for item in mentions if item.observation_kind == "abbreviation_candidate"]
    refs = [item for item in mentions if item.observation_kind == "other_company_reference"]
    # The punctuation separates the later acronym from following marks, while
    # the generic reference before punctuation remains a valid occurrence.
    assert [item.surface_text for item in abbrevs] == ["SAL", "SAL"]
    assert [item.surface_text for item in refs] == ["the company"]
    for mention in (*abbrevs, *refs):
        assert source.body[mention.start:mention.end] == mention.surface_text


def test_nfc_and_collapsed_whitespace_preserve_full_ambiguous_source_ranges():
    source, mentions = extract("Synthetic Cafe\u0301  Holdings Limited")
    mention = next(item for item in mentions if item.observation_kind == "organization_name_candidate")
    assert mention.evidence.alignment_ambiguous is True
    assert source.body[mention.start:mention.end] == mention.surface_text
    assert "Cafe\u0301  Holdings" in mention.surface_text


def test_unsafe_alignment_ambiguous_name_boundary_is_skipped_with_content_free_diagnostic(caplog, monkeypatch):
    import intelligence.entity_extractor as extractor
    from processing.text_alignment import MappedSpan

    source = AnalysisInput("unsafe", body="Context reported Synthetic Alpha Ltd.")
    original_mapper = extractor.map_normalized_span

    def overly_broad_mapper(document, field, start, end):
        if field == "body":
            return MappedSpan(field, 0, len(document.original_body), ambiguous=True)
        return original_mapper(document, field, start, end)

    monkeypatch.setattr(extractor, "map_normalized_span", overly_broad_mapper)
    mentions = extractor.extract_entity_mentions(source, extractor_version=VERSION)
    assert mentions == ()
    assert "ambiguous_candidate_boundary_skipped" in caplog.text
    assert source.body not in caplog.text


def test_corrupted_alignment_map_raises_explicit_alignment_error(monkeypatch):
    import intelligence.entity_extractor as extractor

    source = AnalysisInput("corrupt-extractor", body="Synthetic Alpha Ltd.")
    normalized = normalize_document(source)
    offsets = list(normalized.body_offsets)
    offsets[0] = SourceOffset(1, 2)
    corrupted = replace(normalized, body_offsets=tuple(offsets))
    monkeypatch.setattr(extractor, "normalize_document", lambda _: corrupted)
    with pytest.raises(AlignmentError):
        extractor.extract_entity_mentions(source, extractor_version=VERSION)


def test_title_only_and_body_only_inputs_keep_field_offsets():
    _, title_mentions = extract(title="Synthetic Alpha Ltd.")
    _, body_mentions = extract(body="Synthetic Alpha Ltd.")
    assert title_mentions[0].field == "title" and title_mentions[0].start == 0
    assert body_mentions[0].field == "body" and body_mentions[0].start == 0


def test_deterministic_output_and_id_payload_dimensions():
    text = "Synthetic Alpha Ltd. (SAL) SAL"
    source = AnalysisInput("id-test", body=text)
    first = extract_entity_mentions(source, extractor_version="v1")
    second = extract_entity_mentions(source, extractor_version="v1")
    assert first == second
    assert len({item.mention_id for item in first}) == len(first)

    factory = DeterministicIdFactory()
    base = dict(document_ref="id-test", field="body", start=0, end=5, observation_kind="organization_name_candidate", security_namespace=None)
    ids = {
        factory.mention_id(**base, extractor_version="v1"),
        factory.mention_id(**{**base, "start": 1, "end": 6}, extractor_version="v1"),
        factory.mention_id(**{**base, "field": "title"}, extractor_version="v1"),
        factory.mention_id(**{**base, "observation_kind": "abbreviation_candidate"}, extractor_version="v1"),
        factory.mention_id(**{**base, "observation_kind": "security_identifier_candidate", "security_namespace": "NSE"}, extractor_version="v1"),
        factory.mention_id(**base, extractor_version="v2"),
    }
    assert len(ids) == 6


def test_extraction_is_registry_independent_and_emits_no_resolution_or_confidence():
    _, mentions = extract("Synthetic Alpha Ltd. NSE Symbol: SYNTH-MER-A")
    assert mentions
    assert all(not hasattr(item, "entity_id") and not hasattr(item, "confidence") for item in mentions)
    assert all(item.security_namespace in (None, "NSE", "BSE", "ISIN") for item in mentions)
