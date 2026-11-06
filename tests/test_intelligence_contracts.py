from datetime import datetime, timezone

import pytest

from intelligence.contracts import (
    AnalysisInput,
    AspectFinding,
    AspectMention,
    CompanyMention,
    EvidenceSpan,
    FinancialIntelligenceResult,
)


def test_analysis_input_accepts_title_only_body_only_and_both():
    title_only = AnalysisInput(document_ref="synthetic-1", title="Synthetic title")
    body_only = AnalysisInput(document_ref="synthetic-2", body="Synthetic body")
    both = AnalysisInput(document_ref="synthetic-3", title="Title", body="Body")

    assert title_only.title == "Synthetic title" and title_only.body is None
    assert body_only.title is None and body_only.body == "Synthetic body"
    assert both.title == "Title" and both.body == "Body"


@pytest.mark.parametrize(
    "title, body",
    [(None, None), ("", ""), (" \t\n", None), (None, " \t\n"), ("  ", "\n")],
)
def test_analysis_input_rejects_missing_or_whitespace_only_content(title, body):
    with pytest.raises(ValueError, match="at least one"):
        AnalysisInput(document_ref="synthetic-empty", title=title, body=body)


def test_analysis_input_preserves_separate_timestamp_values_without_inference():
    published_at = datetime(2026, 11, 4, 6, 29, 36, tzinfo=timezone.utc)
    unzoned = datetime(2026, 11, 4, 11, 59, 36)
    item = AnalysisInput(
        document_ref="synthetic-time",
        body="Synthetic statement",
        published_at=published_at,
        published_at_raw="04-Nov-2026 11:59:36",
        published_at_unzoned=unzoned,
        timezone_status="verified_UTC",
    )

    assert item.published_at is published_at
    assert item.published_at_raw == "04-Nov-2026 11:59:36"
    assert item.published_at_unzoned is unzoned
    assert item.timezone_status == "verified_UTC"


def test_analysis_input_rejects_naive_published_at_without_inference():
    with pytest.raises(ValueError, match="timezone-aware"):
        AnalysisInput(
            document_ref="synthetic-time",
            body="Synthetic statement",
            published_at=datetime(2026, 11, 4, 11, 59, 36),
        )


def test_contracts_default_confidence_to_none_and_separate_abstention():
    finding = AspectFinding(
        finding_id="finding-1",
        aspect_code="revenue",
        status="classified",
        sentiment="positive",
    )
    abstained = AspectFinding(
        finding_id="finding-2",
        aspect_code="profit",
        status="abstained",
        sentiment=None,
        abstention_reason="insufficient_polarity_evidence",
    )
    result = FinancialIntelligenceResult(
        document_ref="synthetic-1",
        pipeline_version="pipeline-v1",
        taxonomy_version="taxonomy-v1",
        model_name="synthetic-baseline",
        model_version="none",
        findings=(finding, abstained),
        status="partial",
    )

    assert finding.confidence is None
    assert abstained.confidence is None
    assert abstained.sentiment is None
    assert abstained.abstention_reason == "insufficient_polarity_evidence"
    assert result.status == "partial"


def test_abstained_finding_requires_reason_and_no_sentiment():
    with pytest.raises(ValueError, match="explicit reason"):
        AspectFinding(
            finding_id="finding-1",
            aspect_code="revenue",
            status="abstained",
            sentiment=None,
        )
    with pytest.raises(ValueError, match="must not have a sentiment"):
        AspectFinding(
            finding_id="finding-2",
            aspect_code="revenue",
            status="abstained",
            sentiment="neutral",
            abstention_reason="unclear",
        )


def test_company_and_aspect_mention_contracts_accept_source_field_offsets():
    company = CompanyMention(
        display_name="Synthetic Meridian",
        field="title",
        start=0,
        end=18,
        identifier="SYNTH-MER",
        resolution="resolved",
    )
    aspect = AspectMention(
        code="revenue",
        label="Revenue",
        field="body",
        start=0,
        end=8,
    )

    assert company.confidence is None
    assert company.resolution == "resolved"
    assert aspect.confidence is None


@pytest.mark.parametrize(
    "factory",
    [
        lambda confidence: CompanyMention(display_name="Synthetic Co", field="body", start=0, end=12, confidence=confidence),
        lambda confidence: AspectMention(code="revenue", label="Revenue", field="body", start=0, end=7, confidence=confidence),
        lambda confidence: AspectFinding(finding_id="finding-confidence", aspect_code="revenue", status="classified", sentiment="positive", confidence=confidence),
    ],
)
def test_legacy_contract_confidence_requires_future_calibration(factory):
    assert factory(None).confidence is None
    with pytest.raises(ValueError, match="calibration is implemented"):
        factory(0.75)


def test_evidence_span_rejects_invalid_field_and_ranges():
    with pytest.raises(ValueError, match="field"):
        EvidenceSpan(field="summary", start=0, end=1, quote="x", role="sentiment")
    with pytest.raises(ValueError, match="start"):
        EvidenceSpan(field="body", start=-1, end=1, quote="x", role="sentiment")
    with pytest.raises(ValueError, match="end"):
        EvidenceSpan(field="body", start=1, end=1, quote="x", role="sentiment")


@pytest.mark.parametrize("start,end", [(True, 1), (0, False)])
def test_evidence_span_rejects_boolean_offsets(start, end):
    with pytest.raises(TypeError, match="booleans"):
        EvidenceSpan(field="body", start=start, end=end, quote="x", role="sentiment")


def test_mentions_reject_boolean_offsets():
    with pytest.raises(TypeError, match="booleans"):
        CompanyMention(display_name="Synthetic Co", field="body", start=False, end=1)
    with pytest.raises(TypeError, match="booleans"):
        AspectMention(code="revenue", label="Revenue", field="body", start=0, end=True)
