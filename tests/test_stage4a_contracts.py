from __future__ import annotations

import pytest

from intelligence.stage4a.contracts import (
    CompanyCompetitorEvidenceAssociation,
    CompanyCompetitorRelationOccurrence,
    EvidenceSpan,
    EvidenceSupersession,
    LinkAttempt,
    canonical_utc,
    resolve_alias,
    validate_supersession_graph,
)


def attempt(**changes):
    values = {
        "attempt_id": "attempt-v1:test",
        "document_ref": "doc-1",
        "entity_mention_id": "mention-1",
        "status": "ambiguous",
        "ambiguity_basis": "entity",
        "reason_code": "entity_registry_ambiguous",
        "candidate_entity_ids": ("ENTITY:A", "ENTITY:B"),
        "candidate_resolved_company_ids": (),
        "candidate_attribution_roles": (),
        "relationship_evidence_required": False,
    }
    values.update(changes)
    if values["ambiguity_basis"] in ("relationship", "entity_and_relationship", "resolved_company_and_relationship"):
        values["relationship_evidence_required"] = True
    return LinkAttempt(**values)


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"ambiguity_basis": "resolved_company", "reason_code": "resolved_company_ambiguous", "candidate_entity_ids": (), "candidate_resolved_company_ids": ("COMPANY:A", "COMPANY:B")},
        {"ambiguity_basis": "relationship", "reason_code": "relationship_ambiguous", "candidate_entity_ids": (), "candidate_attribution_roles": ("subject", "possessive")},
        {"ambiguity_basis": "entity_and_relationship", "reason_code": "entity_and_relationship_ambiguous", "candidate_attribution_roles": ("subject", "possessive")},
        {"ambiguity_basis": "resolved_company_and_relationship", "reason_code": "resolved_company_and_relationship_ambiguous", "candidate_entity_ids": (), "candidate_resolved_company_ids": ("COMPANY:A", "COMPANY:B"), "candidate_attribution_roles": ("subject", "possessive")},
    ],
)
def test_h03_valid_ambiguity_states(changes):
    item = attempt(**changes)
    item.validate()


@pytest.mark.parametrize(
    "changes",
    [
        {"candidate_entity_ids": ("ENTITY:A",)},
        {"candidate_entity_ids": ("COMPANY:A", "COMPANY:B")},
        {"candidate_entity_ids": ("ENTITY:A", "ENTITY:A")},
        {"candidate_entity_ids": ("ENTITY:B", "ENTITY:A")},
        {"candidate_resolved_company_ids": ("ENTITY:A", "ENTITY:B")},
        {"ambiguity_basis": "relationship", "reason_code": "relationship_ambiguous", "candidate_entity_ids": (), "candidate_attribution_roles": ("subject",)},
        {"status": "ambiguous", "ambiguity_basis": "none", "reason_code": "entity_registry_ambiguous", "candidate_entity_ids": ()},
        {"status": "abstained", "ambiguity_basis": "entity", "reason_code": "relationship_evidence_insufficient", "candidate_entity_ids": ()},
    ],
)
def test_h03_invalid_ambiguity_states(changes):
    with pytest.raises(ValueError):
        attempt(**changes).validate()


def test_h03_abstention_has_empty_candidate_namespaces():
    item = attempt(
        status="abstained",
        ambiguity_basis="none",
        reason_code="relationship_evidence_insufficient",
        candidate_entity_ids=(),
        relationship_evidence_required=False,
    )
    item.validate()


def test_canonical_utc_rejects_over_precision_before_conversion():
    assert canonical_utc("2026-11-04T06:29:36Z") == "2026-11-04T06:29:36.000000Z"
    assert canonical_utc("2026-11-04T06:29:36.123456Z") == "2026-11-04T06:29:36.123456Z"
    with pytest.raises(ValueError, match="precision"):
        canonical_utc("2026-11-04T06:29:36.1234567Z")


def test_alias_registry_is_conservative():
    assert resolve_alias("sales growth") == "sales_growth"
    assert resolve_alias("revenue growth") is None
    assert resolve_alias("EBITDA margin") is None


def test_supersession_rejects_self_and_transitive_cycles():
    assert validate_supersession_graph((("A", "B"), ("B", "C"))) == (("A", "B"), ("B", "C"))
    with pytest.raises(ValueError, match="self-reference"):
        validate_supersession_graph((("A", "A"),))
    with pytest.raises(ValueError, match="cycle"):
        validate_supersession_graph((("A", "B"), ("B", "C"), ("C", "A")))


def evidence(start=0, quote="Alpha"):
    return EvidenceSpan(field="body", start=start, end=start + len(quote), quote=quote)


def provenance(company, mention, resolution):
    from intelligence.stage4a.contracts import CompanyCompetitorProvenance
    return CompanyCompetitorProvenance(
        document_ref="doc-1",
        resolved_company_id=company,
        company_mention_id=mention,
        resolution_result_id=resolution,
    )


def test_competitor_provenance_requires_exact_relation_endpoints():
    pairs = (
        provenance("COMPANY:ALPHA", "mention-alpha", "resolution-alpha"),
        provenance("COMPANY:BETA", "mention-beta", "resolution-beta"),
    )
    associations = (
        CompanyCompetitorEvidenceAssociation(pairs[0].resolved_company_id, pairs[0].company_mention_id, pairs[0].resolution_result_id, evidence(0, "Alpha")),
        CompanyCompetitorEvidenceAssociation(pairs[1].resolved_company_id, pairs[1].company_mention_id, pairs[1].resolution_result_id, evidence(6, "Beta")),
    )
    occurrence = CompanyCompetitorRelationOccurrence(
        occurrence_id="occurrence-v1:test",
        relation_id="relation-v1:test",
        document_ref="doc-1",
        source_field="body",
        start=0,
        end=10,
        quote="Alpha Beta",
        relation_type="competitor",
        left_company_id="COMPANY:ALPHA",
        right_company_id="COMPANY:BETA",
        provenance=pairs,
        evidence_associations=associations,
    )
    occurrence.validate(
        source="Alpha Beta",
        mention_companies={"mention-alpha": "COMPANY:ALPHA", "mention-beta": "COMPANY:BETA"},
        resolution_pairs={"resolution-alpha": ("mention-alpha", "COMPANY:ALPHA"), "resolution-beta": ("mention-beta", "COMPANY:BETA")},
    )


def test_competitor_provenance_rejects_wrong_endpoint():
    pairs = (
        provenance("COMPANY:ALPHA", "mention-alpha", "resolution-alpha"),
        provenance("COMPANY:GAMMA", "mention-gamma", "resolution-gamma"),
    )
    associations = (
        CompanyCompetitorEvidenceAssociation(pairs[0].resolved_company_id, pairs[0].company_mention_id, pairs[0].resolution_result_id, evidence(0, "Alpha")),
        CompanyCompetitorEvidenceAssociation(pairs[1].resolved_company_id, pairs[1].company_mention_id, pairs[1].resolution_result_id, evidence(6, "Gamma")),
    )
    occurrence = CompanyCompetitorRelationOccurrence(
        occurrence_id="occurrence-v1:test",
        relation_id="relation-v1:test",
        document_ref="doc-1",
        source_field="body",
        start=0,
        end=11,
        quote="Alpha Gamma",
        relation_type="competitor",
        left_company_id="COMPANY:ALPHA",
        right_company_id="COMPANY:BETA",
        provenance=pairs,
        evidence_associations=associations,
    )
    with pytest.raises(ValueError, match="endpoints"):
        occurrence.validate(
            source="Alpha Gamma",
            mention_companies={"mention-alpha": "COMPANY:ALPHA", "mention-gamma": "COMPANY:GAMMA"},
            resolution_pairs={"resolution-alpha": ("mention-alpha", "COMPANY:ALPHA"), "resolution-gamma": ("mention-gamma", "COMPANY:GAMMA")},
        )


def test_supersession_identity_is_deterministic_and_source_bound():
    item = EvidenceSupersession(
        supersession_id="evidence-supersession:v1:test",
        superseded_observation_id="observation-1",
        replacement_observation_id="observation-2",
        document_ref="doc-1",
        source_field="body",
        start=0,
        end=4,
        quote="fact",
        supersession_reason="independent_contradiction",
        payload_version=1,
    )
    item.validate(source="fact is published")
    assert item.immutable_payload()["document_ref"] == "doc-1"
