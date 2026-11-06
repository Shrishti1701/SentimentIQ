from dataclasses import replace
from datetime import datetime, timezone

import pytest

from intelligence.contracts import AspectMention, EvidenceSpan
from intelligence.contracts import verified_effective_time_from_input
from intelligence.entity_contracts import (
    CandidateEvidence,
    DeterministicIdFactory,
    EntityAspectLink,
    EntityAspectLinkAttempt,
    EntityCandidate,
    EntityMention,
    EntityResolutionResult,
    validate_entity_aspect_link,
    validate_entity_source,
    require_validated_entity_link,
    ValidatedEntitySource,
    ValidatedEntityAspectLink,
    validate_entity_resolution_result,
    validate_entity_link_attempt,
    require_validated_entity_link_attempt,
)
from intelligence.contracts import AnalysisInput
from intelligence.synthetic_registry import (
    SyntheticCompany,
    SyntheticRegistry,
    SyntheticSecurity,
    Validity,
    default_synthetic_registry,
)
from processing.cleaner import normalize_document


NOW = datetime(2026, 5, 4, 12, tzinfo=timezone.utc)


def span(field, start, quote, role, *, ambiguous=False):
    return EvidenceSpan(field=field, start=start, end=start + len(quote), quote=quote, role=role, alignment_ambiguous=ambiguous)


def mention(text="Synthetic Meridian", *, namespace=None, kind="organization_name_candidate", start=0, field="body", doc="doc-1", factory=None):
    factory = factory or DeterministicIdFactory()
    mention_id = factory.mention_id(document_ref=doc, field=field, start=start, end=start + len(text), observation_kind=kind, security_namespace=namespace, extractor_version="extractor-v1")
    return EntityMention(mention_id, doc, text, field, start, start + len(text), kind, span(field, start, text, "entity"), "extractor-v1", namespace)


def candidate(entity="COMPANY:SYN-001", basis="legal_name", rank=1):
    return EntityCandidate(entity, basis, provenance_refs=("fixture:verified",), supporting_evidence=(CandidateEvidence(basis, "fixture:verified", True),), rank=rank)


def make_resolution(*, doc="doc", mention_id="m1", status="resolved", entity_id="COMPANY:SYN-001", candidates=None, review=(), rationale="unique_legal_name"):
    factory = DeterministicIdFactory()
    candidates = candidates if candidates is not None else (candidate(entity_id),) if status == "resolved" else ()
    selected = entity_id if status == "resolved" else None
    resolution_id = factory.resolution_id(document_ref=doc, mention_id=mention_id, registry_version="reg-v1", resolver_version="resolver-v1", status=status, selected_entity_id=selected, rationale_code=rationale, candidates=candidates, review_only_candidates=review)
    return EntityResolutionResult(resolution_id, doc, mention_id, status, selected, candidates, review, rationale, "reg-v1", "resolver-v1")


def make_link(**overrides):
    values = dict(document_ref="doc", entity_id="COMPANY:SYN-001", entity_mention_ids=("m1",), aspect_ref=("tax-v1", "revenue"), aspect_mention_ids=("a1",), relationship_type="subject", entity_evidence=(span("body", 0, "Meridian", "entity"),), aspect_evidence=(span("body", 18, "revenue", "aspect"),), relation_evidence=(span("body", 0, "Meridian reported revenue", "relation"),), linker_version="linker-v1")
    values.update(overrides)
    link_id = DeterministicIdFactory().link_id(**{key: values[key] for key in ("document_ref", "entity_id", "entity_mention_ids", "aspect_ref", "aspect_mention_ids", "relationship_type", "linker_version")})
    return EntityAspectLink(link_id=link_id, **values)


def trusted_resolution(item):
    registry = default_synthetic_registry()
    time = verified_time(item.document_ref)
    result = registry.resolve_result(item, resolver_version="resolver-v1", effective_time=time, id_factory=DeterministicIdFactory())
    return validate_entity_resolution_result(item, result, registry=registry, effective_time=time)


def verified_time(document_ref="doc-1", instant=NOW):
    source = AnalysisInput(document_ref, body="synthetic", published_at=instant, timezone_status="verified_UTC")
    return verified_effective_time_from_input(source)


def aspect_mention(source, *, mention_id="a1", code="revenue", taxonomy_version="tax-v1", field="body", phrase="revenue", start=None, evidence_role="aspect"):
    original = source.title if field == "title" else source.body
    if start is None:
        start = original.index(phrase)
    evidence = span(field, start, original[start:start + len(phrase)], evidence_role)
    return AspectMention(
        code=code,
        label=code.title(),
        field=field,
        start=start,
        end=start + len(phrase),
        mention_id=mention_id,
        document_ref=source.document_ref,
        taxonomy_version=taxonomy_version,
        evidence=evidence,
    )


def source_validation(source, mentions, aspect_mentions=()):
    return validate_entity_source(
        source,
        mentions,
        normalized_document=normalize_document(source),
        aspect_mentions=aspect_mentions,
    )


def test_entity_mention_preserves_observed_kind_and_exact_evidence():
    item = mention()
    source = AnalysisInput("doc-1", body="Synthetic Meridian reported growth")
    item.validate_source(normalized_document=normalize_document(source))
    assert item.observation_kind == "organization_name_candidate"
    assert item.security_namespace is None


def test_source_validation_boundary_binds_mention_to_actual_analysis_input():
    item = mention("Meridian", doc="doc")
    source = AnalysisInput("doc", body="Meridian reported revenue")
    validated = source_validation(source, (item,))
    assert validated.document_ref == source.document_ref
    with pytest.raises(ValueError, match="quote"):
        source_validation(AnalysisInput("doc", body="Other Co reported revenue"), (item,))
    with pytest.raises(ValueError, match="document_ref"):
        source_validation(AnalysisInput("different-doc", body="Meridian reported revenue"), (item,))
    with pytest.raises(TypeError):
        ValidatedEntitySource("doc", "Meridian", None, (item,), "digest", None)


def test_structural_link_is_not_accepted_without_source_and_resolution_validation():
    text = "Synthetic Meridian reported revenue"
    item = mention("Synthetic Meridian", doc="doc")
    source_input = AnalysisInput("doc", body=text)
    source = source_validation(source_input, (item,), (aspect_mention(source_input),))
    link = make_link(document_ref="doc", entity_mention_ids=(item.mention_id,), entity_evidence=(item.evidence,), aspect_evidence=(span("body", text.index("revenue"), "revenue", "aspect"),), relation_evidence=(span("body", 0, text, "relation"),))
    with pytest.raises(TypeError):
        validate_entity_aspect_link(link, source=source)  # resolution results are mandatory
    with pytest.raises(ValueError, match="resolution result"):
        validate_entity_aspect_link(link, source=source, resolutions=(), candidate_relationship_types=("subject",), relationship_evidence_sufficient=True)
    resolution = trusted_resolution(item)
    validated = validate_entity_aspect_link(link, source=source, resolutions=(resolution,), candidate_relationship_types=("subject",), relationship_evidence_sufficient=True)
    assert require_validated_entity_link(validated) is link
    with pytest.raises(ValueError, match="validated entity-aspect link"):
        require_validated_entity_link(link)
    with pytest.raises(TypeError):
        ValidatedEntityAspectLink(link, "doc", source.source_digest, (resolution.result.resolution_id,), None)
    with pytest.raises(ValueError, match="exactly one established"):
        validate_entity_aspect_link(link, source=source, resolutions=(resolution,), candidate_relationship_types=("subject", "comparison"), relationship_evidence_sufficient=True)
    with pytest.raises(ValueError, match="explicit sufficient"):
        validate_entity_aspect_link(link, source=source, resolutions=(resolution,), candidate_relationship_types=("subject",), relationship_evidence_sufficient=False)


def test_successful_link_rejects_unresolved_mismatched_and_wrong_document_resolutions():
    text = "Synthetic Meridian reported revenue"
    item = mention("Synthetic Meridian", doc="doc")
    source_input = AnalysisInput("doc", body=text)
    source = source_validation(source_input, (item,), (aspect_mention(source_input),))
    link = make_link(document_ref="doc", entity_mention_ids=(item.mention_id,), entity_evidence=(item.evidence,), aspect_evidence=(span("body", text.index("revenue"), "revenue", "aspect"),), relation_evidence=(span("body", 0, text, "relation"),))
    empty_registry = SyntheticRegistry("empty-v1", (), ())
    time = verified_time(item.document_ref)
    unresolved_result = empty_registry.resolve_result(item, resolver_version="resolver-v1", effective_time=time, id_factory=DeterministicIdFactory())
    unresolved = validate_entity_resolution_result(item, unresolved_result, registry=empty_registry, effective_time=time)
    with pytest.raises(ValueError, match="resolved entity results"):
        validate_entity_aspect_link(link, source=source, resolutions=(unresolved,), candidate_relationship_types=("subject",), relationship_evidence_sufficient=True)
    matching_result = trusted_resolution(item)
    mismatch_link = make_link(document_ref="doc", entity_id="COMPANY:SYN-002", entity_mention_ids=(item.mention_id,), entity_evidence=(item.evidence,), aspect_evidence=link.aspect_evidence, relation_evidence=link.relation_evidence)
    with pytest.raises(ValueError, match="does not match"):
        validate_entity_aspect_link(mismatch_link, source=source, resolutions=(matching_result,), candidate_relationship_types=("subject",), relationship_evidence_sufficient=True)
    original_result = matching_result.result
    wrong_doc_id = DeterministicIdFactory().resolution_id(document_ref="other", mention_id=item.mention_id, registry_version=original_result.registry_version, resolver_version=original_result.resolver_version, status=original_result.status, selected_entity_id=original_result.selected_entity_id, rationale_code=original_result.rationale_code, candidates=original_result.candidates, review_only_candidates=original_result.review_only_candidates)
    wrong_doc_result = replace(original_result, document_ref="other", resolution_id=wrong_doc_id)
    with pytest.raises(ValueError, match="document"):
        validate_entity_resolution_result(item, wrong_doc_result, registry=default_synthetic_registry(), effective_time=verified_time(item.document_ref))


def test_successful_link_requires_source_bound_matching_aspect_mentions():
    text = "Synthetic Meridian reported revenue"
    source_input = AnalysisInput("doc", body=text)
    entity = mention("Synthetic Meridian", doc="doc")
    aspect = aspect_mention(source_input)
    source = source_validation(source_input, (entity,), (aspect,))
    resolution = trusted_resolution(entity)
    link = make_link(document_ref="doc", entity_mention_ids=(entity.mention_id,), entity_evidence=(entity.evidence,), aspect_evidence=(aspect.evidence,), relation_evidence=(span("body", 0, text, "relation"),))
    assert validate_entity_aspect_link(
        link, source=source, resolutions=(resolution,), candidate_relationship_types=("subject",),
        relationship_evidence_sufficient=True,
    ).link is link

    fabricated = make_link(document_ref="doc", entity_mention_ids=(entity.mention_id,), aspect_mention_ids=("fabricated",), entity_evidence=(entity.evidence,), aspect_evidence=(aspect.evidence,), relation_evidence=link.relation_evidence)
    with pytest.raises(ValueError, match="missing or nonexistent"):
        validate_entity_aspect_link(fabricated, source=source, resolutions=(resolution,), candidate_relationship_types=("subject",), relationship_evidence_sufficient=True)
    no_aspect_source = source_validation(source_input, (entity,))
    with pytest.raises(ValueError, match="missing or nonexistent"):
        validate_entity_aspect_link(link, source=no_aspect_source, resolutions=(resolution,), candidate_relationship_types=("subject",), relationship_evidence_sufficient=True)
    duplicate = aspect_mention(source_input, mention_id="a2")
    with pytest.raises(ValueError, match="IDs must be unique"):
        source_validation(source_input, (entity,), (aspect, replace(duplicate, mention_id="a1")))
    with pytest.raises(ValueError, match="matching document_ref"):
        source_validation(source_input, (entity,), (replace(aspect, document_ref="other"),))
    wrong_taxonomy_link = make_link(document_ref="doc", entity_mention_ids=(entity.mention_id,), aspect_ref=("tax-v2", "revenue"), entity_evidence=(entity.evidence,), aspect_evidence=(aspect.evidence,), relation_evidence=link.relation_evidence)
    with pytest.raises(ValueError, match="do not match"):
        validate_entity_aspect_link(wrong_taxonomy_link, source=source, resolutions=(resolution,), candidate_relationship_types=("subject",), relationship_evidence_sufficient=True)
    wrong_code_link = make_link(document_ref="doc", entity_mention_ids=(entity.mention_id,), aspect_ref=("tax-v1", "profit"), entity_evidence=(entity.evidence,), aspect_evidence=(aspect.evidence,), relation_evidence=link.relation_evidence)
    with pytest.raises(ValueError, match="do not match"):
        validate_entity_aspect_link(wrong_code_link, source=source, resolutions=(resolution,), candidate_relationship_types=("subject",), relationship_evidence_sufficient=True)

    invented = replace(aspect, evidence=span("body", aspect.start, "profits", "aspect"))
    with pytest.raises(ValueError, match="quote"):
        source_validation(source_input, (entity,), (invented,))
    out_of_range = AspectMention(
        code="revenue", label="Revenue", field="body", start=len(text), end=len(text) + 3,
        mention_id="a-oob", document_ref="doc", taxonomy_version="tax-v1",
        evidence=span("body", len(text), "xyz", "aspect"),
    )
    with pytest.raises(ValueError, match="end exceeds"):
        source_validation(source_input, (entity,), (out_of_range,))
    with pytest.raises(ValueError, match="role aspect"):
        replace(aspect, evidence=span("body", aspect.start, "revenue", "entity"))


def test_link_contract_rejects_duplicate_mention_references_and_accepts_unique_refs():
    with pytest.raises(ValueError, match="entity_mention_ids must contain unique"):
        make_link(entity_mention_ids=("m1", "m1"))
    with pytest.raises(ValueError, match="aspect_mention_ids must contain unique"):
        make_link(aspect_mention_ids=("a1", "a1"))

    link = make_link(entity_mention_ids=("m1", "m2"), aspect_mention_ids=("a1", "a2"))
    assert link.entity_mention_ids == ("m1", "m2")
    assert link.aspect_mention_ids == ("a1", "a2")


def test_link_attempt_contract_rejects_duplicate_mention_references_and_accepts_unique_refs():
    with pytest.raises(ValueError, match="entity_mention_ids must contain unique"):
        attempt(entity_mention_ids=("m1", "m1"))
    with pytest.raises(ValueError, match="aspect_mention_ids must contain unique"):
        attempt(
            aspect_ref=("tax-v1", "revenue"),
            aspect_mention_ids=("a1", "a1"),
            aspect_evidence=(span("body", 0, "Meridian", "aspect"),),
        )

    value = attempt(
        entity_mention_ids=("m1", "m2"),
        aspect_ref=("tax-v1", "revenue"),
        aspect_mention_ids=("a1", "a2"),
        aspect_evidence=(span("body", 0, "Meridian", "aspect"),),
    )
    assert value.entity_mention_ids == ("m1", "m2")
    assert value.aspect_mention_ids == ("a1", "a2")


@pytest.mark.parametrize("start,end", [(True, 4), (0, False), (-1, 3), (4, 4)])
def test_entity_mention_rejects_invalid_offsets(start, end):
    with pytest.raises((ValueError, TypeError)):
        EntityMention("m", "d", "x", "body", start, end, "other_company_reference", span("body", 0, "x", "entity"), "v1")


def test_entity_mention_rejects_namespace_inference_and_evidence_mismatch():
    with pytest.raises(ValueError, match="security_identifier_candidate"):
        mention(namespace="NSE")
    with pytest.raises(ValueError, match="exactly match"):
        EntityMention("m", "d", "Meridian", "body", 0, 8, "organization_name_candidate", span("body", 0, "Meridian", "aspect"), "v1")


def test_security_namespace_is_only_recorded_when_explicitly_supplied():
    with pytest.raises(ValueError, match="security namespace"):
        EntityMention("m", "d", "SYNTH-MER-A", "body", 0, 12, "security_identifier_candidate", span("body", 0, "SYNTH-MER-A", "entity"), "v1", "NASDAQ")
    item = mention("SYNTH-MER-A", kind="security_identifier_candidate", namespace="NSE")
    assert item.security_namespace == "NSE"


def test_resolution_cardinality_and_review_only_separation():
    plausible = candidate()
    review = candidate("COMPANY:SYN-002")
    resolved_id = DeterministicIdFactory().resolution_id(document_ref="d", mention_id="m", registry_version="reg-v1", resolver_version="resolver-v1", status="resolved", selected_entity_id=plausible.entity_id, rationale_code="unique_legal_name", candidates=(plausible,), review_only_candidates=(review,))
    EntityResolutionResult(resolved_id, "d", "m", "resolved", plausible.entity_id, (plausible,), (review,), "unique_legal_name", "reg-v1", "resolver-v1")
    with pytest.raises(ValueError, match="exactly one"):
        EntityResolutionResult("r", "d", "m", "resolved", plausible.entity_id, (plausible, candidate("COMPANY:SYN-003")), (), "x", "reg-v1", "resolver-v1")
    with pytest.raises(ValueError, match="at least two"):
        EntityResolutionResult("r", "d", "m", "ambiguous", None, (plausible,), (), "x", "reg-v1", "resolver-v1")
    with pytest.raises(ValueError, match="zero plausible"):
        EntityResolutionResult("r", "d", "m", "unresolved", None, (plausible,), (), "x", "reg-v1", "resolver-v1")
    with pytest.raises(ValueError, match="disjoint"):
        EntityResolutionResult("r", "d", "m", "resolved", plausible.entity_id, (plausible,), (plausible,), "x", "reg-v1", "resolver-v1")


def test_review_only_candidate_cannot_resolve_an_unmatched_mention():
    review = candidate("COMPANY:SYN-001")
    result = make_resolution(doc="d", mention_id="m", status="unresolved", candidates=(), review=(review,), rationale="no_registry_match")
    assert result.status == "unresolved"
    assert result.selected_entity_id is None
    assert result.candidates == ()
    assert result.review_only_candidates == (review,)


def test_security_candidates_require_security_identifier_and_provenance():
    with pytest.raises(ValueError, match="require security"):
        EntityCandidate("COMPANY:SYN-1", "verified_security_issuer_mapping")
    valid = EntityCandidate("COMPANY:SYN-1", "verified_security_issuer_mapping", ("SECURITY:SYN-1",), ("NSE:SYNTH",), ("fixture:map",), (CandidateEvidence("verified_security_issuer_mapping", "fixture:map", True),))
    assert valid.entity_id.startswith("COMPANY:")
    with pytest.raises(ValueError, match="COMPANY:"):
        EntityCandidate("SECURITY:SYN-1", "legal_name")
    with pytest.raises(ValueError, match="SECURITY:"):
        EntityCandidate("COMPANY:SYN-1", "verified_security_issuer_mapping", ("COMPANY:SYN-2",), ("NSE:SYNTH",), ("fixture:map",), (CandidateEvidence("verified_security_issuer_mapping", "fixture:map", True),))
    with pytest.raises(ValueError, match="provenance"):
        EntityCandidate("COMPANY:SYN-1", "legal_name")


def test_fuzzy_only_and_invalid_contextual_evidence_cannot_make_plausible_candidate():
    with pytest.raises(ValueError, match="fuzzy-only"):
        EntityCandidate("COMPANY:SYN-1", "legal_name", provenance_refs=("review:fuzzy",), supporting_evidence=(CandidateEvidence("legal_name", "review:fuzzy", False, True),))
    with pytest.raises(ValueError, match="allow-listed"):
        CandidateEvidence("contextual_rule", "context:1", True, context_rule_id="fuzzy_name_similarity")
    with pytest.raises(ValueError, match="verified non-fuzzy identity anchor"):
        EntityCandidate("COMPANY:SYN-1", "contextual_rule", provenance_refs=("context:1",), supporting_evidence=(CandidateEvidence("contextual_rule", "context:1", True, context_rule_id="explicit_issuer_statement"),))
    anchored = EntityCandidate("COMPANY:SYN-1", "contextual_rule", provenance_refs=("registry:name", "context:1"), supporting_evidence=(CandidateEvidence("legal_name", "registry:name", True), CandidateEvidence("contextual_rule", "context:1", True, context_rule_id="explicit_issuer_statement")))
    assert anchored.match_basis == "contextual_rule"


def test_resolution_candidates_require_deterministic_ordering():
    first, second = candidate("COMPANY:SYN-001", rank=2), candidate("COMPANY:SYN-002", rank=1)
    with pytest.raises(ValueError, match="deterministic rank/entity ordering"):
        EntityResolutionResult("r", "d", "m", "ambiguous", None, (first, second), (), "multiple", "reg-v1", "resolver-v1")


def test_successful_link_requires_typed_evidence_and_valid_source_slices():
    link = make_link()
    link.validate_source_evidence(normalized_document=normalize_document(AnalysisInput("doc", body="Meridian reported revenue")))
    with pytest.raises(ValueError, match="role 'relation'"):
        replace(link, relation_evidence=(span("body", 0, "Meridian", "sentiment"),))


def test_alignment_ambiguous_link_evidence_requires_explicit_sufficiency():
    text = "e\u0301 reported revenue"
    source = AnalysisInput("doc", body=text)
    normalized = normalize_document(source)
    link = make_link(
        entity_evidence=(span("body", 0, "e\u0301", "entity", ambiguous=True),),
        aspect_evidence=(span("body", text.index("revenue"), "revenue", "aspect"),),
        relation_evidence=(span("body", 0, text, "relation", ambiguous=True),),
    )
    with pytest.raises(ValueError, match="semantic sufficiency"):
        link.validate_source_evidence(normalized_document=normalized)
    link.validate_source_evidence(normalized_document=normalized, ambiguous_evidence_semantically_sufficient=True)
    with pytest.raises(ValueError, match="semantic sufficiency"):
        link.validate_source_evidence(normalized_document=normalized, ambiguous_evidence_semantically_sufficient=False)
    falsely_precise = replace(link, entity_evidence=(span("body", 0, "e\u0301", "entity"),))
    with pytest.raises(ValueError, match="does not match"):
        falsely_precise.validate_source_evidence(normalized_document=normalized, ambiguous_evidence_semantically_sufficient=True)


@pytest.mark.parametrize("value", [None, "no", "yes", 0, 1, object()])
def test_alignment_sufficiency_rejects_non_boolean_values_even_for_unambiguous_evidence(value):
    link = make_link()
    normalized = normalize_document(AnalysisInput("doc", body="Meridian reported revenue"))
    with pytest.raises(TypeError, match="actual bool"):
        link.validate_source_evidence(normalized_document=normalized, ambiguous_evidence_semantically_sufficient=value)


def test_unambiguous_evidence_accepts_literal_true_or_false():
    link = make_link()
    normalized = normalize_document(AnalysisInput("doc", body="Meridian reported revenue"))
    link.validate_source_evidence(normalized_document=normalized, ambiguous_evidence_semantically_sufficient=True)
    link.validate_source_evidence(normalized_document=normalized, ambiguous_evidence_semantically_sufficient=False)


@pytest.mark.parametrize("value", [None, "no", "yes", 0, 1])
def test_validated_link_boundary_rejects_non_boolean_alignment_sufficiency(value):
    text = "Synthetic Meridian reported revenue"
    source_input = AnalysisInput("doc", body=text)
    entity = mention("Synthetic Meridian", doc="doc")
    aspect = aspect_mention(source_input)
    source = source_validation(source_input, (entity,), (aspect,))
    link = make_link(document_ref="doc", entity_mention_ids=(entity.mention_id,), entity_evidence=(entity.evidence,), aspect_evidence=(aspect.evidence,), relation_evidence=(span("body", 0, text, "relation"),))
    with pytest.raises(TypeError, match="actual bool"):
        validate_entity_aspect_link(
            link, source=source, resolutions=(trusted_resolution(entity),),
            candidate_relationship_types=("subject",), relationship_evidence_sufficient=True,
            ambiguous_evidence_semantically_sufficient=value,
        )


def test_source_validation_requires_matching_normalized_document_and_alignment_map():
    item = mention("Meridian", doc="doc")
    source = AnalysisInput("doc", body="Meridian reported revenue")
    with pytest.raises(ValueError, match="does not match"):
        validate_entity_source(source, (item,), normalized_document=normalize_document(AnalysisInput("doc", body="Meridian changed revenue")))

    normalized = normalize_document(source)
    corrupted_offsets = list(normalized.body_offsets)
    corrupted_offsets[0] = replace(corrupted_offsets[0], start=1, end=2)
    corrupted = replace(normalized, body_offsets=tuple(corrupted_offsets))
    with pytest.raises(ValueError, match="does not match"):
        validate_entity_source(source, (item,), normalized_document=corrupted)


def test_unambiguous_stage1_evidence_is_accepted():
    source = AnalysisInput("doc", body="Meridian reported revenue")
    item = mention("Meridian", doc="doc")
    validated = validate_entity_source(source, (item,), normalized_document=normalize_document(source))
    assert validated.document_ref == "doc"


def attempt(**overrides):
    values = dict(
        attempt_id="", document_ref="doc", entity_mention_ids=("m1",), candidate_entity_ids=(),
        status="abstained", relationship_type="unknown", candidate_relationship_types=(), ambiguity_basis="none",
        reason_code="insufficient_evidence", linker_version="linker-v1",
        aspect_ref=None, aspect_mention_ids=(),
        entity_evidence=(span("body", 0, "Meridian", "entity"),),
    )
    values.update(overrides)
    values["attempt_id"] = DeterministicIdFactory().attempt_id(**{key: values[key] for key in ("document_ref", "entity_mention_ids", "candidate_entity_ids", "aspect_ref", "aspect_mention_ids", "candidate_relationship_types", "relationship_type", "ambiguity_basis", "status", "reason_code", "linker_version")})
    return EntityAspectLinkAttempt(**values)


def test_link_attempt_requires_aspect_reference_and_mentions_together():
    with pytest.raises(ValueError, match="aspect_mention_ids"):
        attempt(aspect_ref=("tax-v1", "revenue"))
    with pytest.raises(ValueError, match="aspect_ref"):
        attempt(aspect_mention_ids=("a1",))
    attempt(aspect_ref=("tax-v1", "revenue"), aspect_mention_ids=("a1",), aspect_evidence=(span("body", 12, "revenue", "aspect"),))


def test_link_attempt_evidence_roles_are_preserved():
    with pytest.raises(ValueError, match="role 'aspect'"):
        attempt(aspect_ref=("tax-v1", "revenue"), aspect_mention_ids=("a1",), aspect_evidence=(span("body", 0, "Meridian", "entity"),))
    value = attempt(relation_evidence=(span("body", 0, "Meridian", "relation"),))
    assert value.relation_evidence[0].role == "relation"


def test_relationship_case_one_established_relation_can_link():
    link = make_link(linker_version="lv1", entity_mention_ids=("m",), aspect_ref=("tax", "revenue"), aspect_mention_ids=("a",))
    assert link.relationship_type == "subject"


def test_relationship_case_multiple_interpretations_are_ambiguous():
    value = attempt(status="ambiguous", candidate_entity_ids=("COMPANY:SYN-001",), candidate_relationship_types=("subject", "comparison"), ambiguity_basis="relationship")
    assert value.relationship_type == "unknown"


def test_relationship_case_entity_and_relationship_both_ambiguous():
    value = attempt(status="ambiguous", candidate_entity_ids=("COMPANY:SYN-001", "COMPANY:SYN-002"), candidate_relationship_types=("subject", "competitor"), ambiguity_basis="entity_and_relationship")
    assert value.ambiguity_basis == "entity_and_relationship"


def test_relationship_case_one_possible_but_insufficient_is_abstained():
    value = attempt(candidate_relationship_types=("subject",))
    assert value.status == "abstained" and value.relationship_type == "unknown" and value.ambiguity_basis == "none"
    with pytest.raises(ValueError, match="cannot claim an established relationship"):
        attempt(candidate_relationship_types=("subject",), relationship_type="subject")


def test_relationship_case_no_plausible_interpretation_is_abstained():
    value = attempt(candidate_relationship_types=(), ambiguity_basis="none")
    assert value.relationship_type == "unknown" and not value.candidate_relationship_types


def test_relationship_case_contradictory_attempt_combinations_are_rejected():
    with pytest.raises(ValueError, match="sole candidate relationship"):
        attempt(status="ambiguous", candidate_relationship_types=("subject", "comparison"), relationship_type="subject", ambiguity_basis="relationship")
    with pytest.raises(ValueError, match="ambiguous attempts"):
        attempt(status="ambiguous", ambiguity_basis="none")


def test_deterministic_ids_are_repeatable_and_ignore_candidate_ordering():
    factory = DeterministicIdFactory()
    mention_args = dict(document_ref="doc", field="body", start=2, end=5, observation_kind="organization_name_candidate", security_namespace=None, extractor_version="v1")
    assert factory.mention_id(**mention_args) == factory.mention_id(**mention_args)
    first, second = candidate("COMPANY:SYN-001"), candidate("COMPANY:SYN-002")
    args = dict(document_ref="doc", mention_id="m", registry_version="r1", resolver_version="rv1", status="ambiguous", selected_entity_id=None, rationale_code="multiple", review_only_candidates=())
    assert factory.resolution_id(candidates=(first, second), **args) == factory.resolution_id(candidates=(second, first), **args)


def test_link_and_attempt_ids_are_repeatable_and_order_independent():
    factory = DeterministicIdFactory()
    link = dict(document_ref="d", entity_id="COMPANY:SYN-1", entity_mention_ids=("m2", "m1"), aspect_ref=("tax-v1", "revenue"), aspect_mention_ids=("a2", "a1"), relationship_type="subject", linker_version="link-v1")
    assert factory.link_id(**link) == factory.link_id(**{**link, "entity_mention_ids": tuple(reversed(link["entity_mention_ids"])), "aspect_mention_ids": tuple(reversed(link["aspect_mention_ids"]))})
    attempt_args = dict(document_ref="d", entity_mention_ids=("m2", "m1"), candidate_entity_ids=("COMPANY:SYN-2", "COMPANY:SYN-1"), aspect_ref=None, aspect_mention_ids=(), candidate_relationship_types=("subject", "comparison"), relationship_type="unknown", ambiguity_basis="relationship", status="ambiguous", reason_code="two_interpretations", linker_version="link-v1")
    permuted = {**attempt_args, "entity_mention_ids": tuple(reversed(attempt_args["entity_mention_ids"])), "candidate_entity_ids": tuple(reversed(attempt_args["candidate_entity_ids"])), "candidate_relationship_types": tuple(reversed(attempt_args["candidate_relationship_types"]))}
    assert factory.attempt_id(**attempt_args) == factory.attempt_id(**permuted)


def test_deterministic_id_factory_detects_digest_collision(monkeypatch):
    class SameDigest:
        def hexdigest(self):
            return "0" * 64

    monkeypatch.setattr("intelligence.entity_contracts.sha256", lambda payload: SameDigest())
    factory = DeterministicIdFactory()
    factory.create("test", {"a": 1})
    with pytest.raises(RuntimeError, match="collision"):
        factory.create("test", {"a": 2})


def test_contract_objects_reject_caller_supplied_ids_that_do_not_match_payload():
    item = mention("Meridian")
    with pytest.raises(ValueError, match="mention_id does not match"):
        replace(item, mention_id="caller-chosen")
    result = make_resolution(mention_id=item.mention_id)
    with pytest.raises(ValueError, match="resolution_id does not match"):
        replace(result, resolution_id="caller-chosen")
    link = make_link()
    with pytest.raises(ValueError, match="link_id does not match"):
        replace(link, link_id="caller-chosen")
    link_attempt = attempt()
    with pytest.raises(ValueError, match="attempt_id does not match"):
        replace(link_attempt, attempt_id="caller-chosen")


def test_link_and_attempt_confidence_remain_unavailable_until_calibration():
    assert make_link().confidence is None
    assert attempt().confidence is None
    with pytest.raises(ValueError, match="calibration is implemented"):
        replace(make_link(), confidence=0.8)
    with pytest.raises(ValueError, match="calibration is implemented"):
        attempt(confidence=0.8)


def test_cross_factory_collision_check_is_process_local(monkeypatch):
    class SameDigest:
        def hexdigest(self):
            return "1" * 64

    monkeypatch.setattr("intelligence.entity_contracts.sha256", lambda payload: SameDigest())
    first = DeterministicIdFactory()
    second = DeterministicIdFactory()
    one = first.create("test", {"a": 1})
    two = second.create("test", {"a": 2})
    assert one == two  # independent instances have no shared collision ledger
    with pytest.raises(RuntimeError, match="existing canonical payload"):
        first.verify_existing_payload(one, "test", {"a": 2}, '{"a":1}')


def test_id_factory_rejects_noncanonical_payload_shapes():
    with pytest.raises(TypeError, match="string-keyed dictionary"):
        DeterministicIdFactory().create("test", {1: "not a string key"})


def test_synthetic_registry_resolves_names_and_verified_security_mapping():
    registry = default_synthetic_registry()
    name = mention()
    resolved = registry.resolve_result(name, resolver_version="exact-v1", effective_time=verified_time(name.document_ref), id_factory=DeterministicIdFactory())
    assert resolved.status == "resolved" and resolved.selected_entity_id == "COMPANY:SYN-001"

    security = mention("SYNTH-MER-A", kind="security_identifier_candidate", namespace="NSE")
    resolved_security = registry.resolve(security, resolver_version="exact-v1", effective_time=verified_time(security.document_ref))
    assert resolved_security.selected_entity_id == "COMPANY:SYN-001"
    assert resolved_security.candidates[0].supporting_security_ids == ("SECURITY:SYN-001",)


def test_synthetic_registry_does_not_infer_security_namespace_or_time():
    registry = default_synthetic_registry()
    untyped = mention("SYNTH-MER-A", kind="security_identifier_candidate")
    assert registry.resolve(untyped, resolver_version="v1", effective_time=verified_time(untyped.document_ref)).rationale_code == "invalid_or_unverified_identifier"
    typed = mention("SYNTH-MER-A", kind="security_identifier_candidate", namespace="NSE")
    assert registry.resolve(typed, resolver_version="v1", effective_time=None).rationale_code == "historical_validity_unknown"


@pytest.mark.parametrize("namespace", ["NASDAQ", "", None])
def test_synthetic_security_rejects_invalid_namespace(namespace):
    with pytest.raises(ValueError, match="namespace"):
        SyntheticSecurity("SECURITY:X", namespace, "X", "COMPANY:X", True, Validity(None, None), "fixture")


@pytest.mark.parametrize("verified", ["yes", 1, None])
def test_synthetic_security_requires_actual_boolean_verification(verified):
    with pytest.raises(TypeError, match="actual bool"):
        SyntheticSecurity("SECURITY:X", "NSE", "X", "COMPANY:X", verified, Validity(None, None), "fixture")


def test_synthetic_registry_requires_verified_security_issuer_mapping_and_validity():
    registry = default_synthetic_registry()
    unverified = mention("SYN00FAKE001", kind="security_identifier_candidate", namespace="ISIN")
    assert registry.resolve(unverified, resolver_version="v1", effective_time=verified_time(unverified.document_ref)).status == "unresolved"
    outdated = mention("SYNTH-MER-A", kind="security_identifier_candidate", namespace="NSE")
    before_validity = datetime(2020, 1, 1, tzinfo=timezone.utc)
    assert registry.resolve(outdated, resolver_version="v1", effective_time=verified_time(outdated.document_ref, before_validity)).rationale_code == "no_registry_match"


def test_validity_requires_aware_ordered_boundaries_and_half_open_end():
    with pytest.raises(ValueError, match="timezone-aware"):
        Validity(datetime(2025, 1, 1), datetime(2026, 1, 1, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="earlier"):
        Validity(datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2025, 1, 1, tzinfo=timezone.utc))
    with pytest.raises(TypeError, match="datetime or None"):
        Validity("2025-01-01", None)
    interval = Validity(datetime(2025, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert interval.contains(datetime(2025, 1, 1, tzinfo=timezone.utc))
    assert not interval.contains(datetime(2026, 1, 1, tzinfo=timezone.utc))


def test_historical_legal_name_changes_fail_closed():
    old = Validity(datetime(2010, 1, 1, tzinfo=timezone.utc), datetime(2020, 1, 1, tzinfo=timezone.utc))
    current = Validity(datetime(2020, 1, 1, tzinfo=timezone.utc), None)
    company = SyntheticCompany("COMPANY:HIST-1", "Synthetic Current Name", current, historical_legal_names=(("Synthetic Former Name", old, "fixture:former-name"),))
    registry = SyntheticRegistry("historical-v1", (company,), ())
    old_name_mention = mention("Synthetic Former Name", kind="organization_name_candidate")
    current_name_mention = mention("Synthetic Current Name", kind="organization_name_candidate")
    assert registry.resolve(old_name_mention, resolver_version="v1", effective_time=verified_time(old_name_mention.document_ref, datetime(2015, 1, 1, tzinfo=timezone.utc))).status == "resolved"
    assert registry.resolve(old_name_mention, resolver_version="v1", effective_time=verified_time(old_name_mention.document_ref, datetime(2021, 1, 1, tzinfo=timezone.utc))).status == "unresolved"
    assert registry.resolve(current_name_mention, resolver_version="v1", effective_time=verified_time(current_name_mention.document_ref, datetime(2015, 1, 1, tzinfo=timezone.utc))).status == "unresolved"
    assert old.valid_to == current.valid_from


def test_contract_collections_reject_mutable_lists():
    with pytest.raises(TypeError, match="immutable tuple"):
        EntityResolutionResult("x", "d", "m", "unresolved", None, [], (), "no_match", "rv", "resolver")
    with pytest.raises(TypeError, match="immutable tuple"):
        replace(make_link(), entity_mention_ids=["m1"])
    with pytest.raises(TypeError, match="immutable tuple"):
        attempt(entity_mention_ids=["m1"])
    with pytest.raises(TypeError, match="immutable tuple"):
        EntityCandidate("COMPANY:SYN-1", "legal_name", provenance_refs=["fixture"], supporting_evidence=(CandidateEvidence("legal_name", "fixture", True),))


def test_registry_records_and_maps_cannot_be_mutated_after_validation():
    registry = default_synthetic_registry()
    with pytest.raises(TypeError):
        registry.companies["COMPANY:INJECTED"] = SyntheticCompany("COMPANY:INJECTED", "Injected", Validity(None, None))
    with pytest.raises((AttributeError, TypeError)):
        registry.companies["COMPANY:SYN-001"].aliases += (("Mutated", Validity(None, None), "fake"),)


def test_synthetic_parent_and_subsidiary_remain_distinct():
    registry = default_synthetic_registry()
    parent = registry.companies["COMPANY:SYN-001"]
    subsidiary = registry.companies["COMPANY:SYN-002"]
    assert parent.entity_id != subsidiary.entity_id
    assert subsidiary.parent_entity_id == parent.entity_id


def test_registry_rejects_company_security_id_conflation():
    with pytest.raises(ValueError, match="company entity ID"):
        SyntheticSecurity("SECURITY:S", "NSE", "X", "SECURITY:OTHER", True, Validity(None, None), "fixture")
    with pytest.raises(ValueError, match="COMPANY:"):
        SyntheticCompany("SECURITY:bad", "Synthetic Company", Validity(None, None))


def test_registry_version_and_unknown_alias_history_are_enforced():
    registry = default_synthetic_registry()
    alias = mention("Synthetic Meridian", kind="organization_name_candidate")
    assert registry.resolve(alias, resolver_version="v1", effective_time=None).rationale_code == "historical_validity_unknown"
    instant = datetime(2026, 5, 4, tzinfo=timezone.utc)
    assert registry.resolve(alias, resolver_version="v1", effective_time=verified_time(alias.document_ref, instant)).status == "resolved"


def test_verified_effective_time_requires_explicit_aware_timestamp_semantics():
    known = AnalysisInput("doc-time", body="Synthetic", published_at=NOW, timezone_status="verified_UTC")
    effective = verified_effective_time_from_input(known)
    assert effective.instant is NOW

    unknown = AnalysisInput("doc-unknown", body="Synthetic")
    with pytest.raises(ValueError, match="verified aware"):
        verified_effective_time_from_input(unknown)
    unverified = AnalysisInput("doc-unverified", body="Synthetic", published_at=NOW, timezone_status="claimed_UTC")
    with pytest.raises(ValueError, match="verified aware"):
        verified_effective_time_from_input(unverified)
    with pytest.raises(ValueError, match="timezone-aware"):
        AnalysisInput("doc-naive", body="Synthetic", published_at=datetime(2026, 5, 4, 12), timezone_status="verified_UTC")

    item = mention("Synthetic Meridian", doc="doc-unknown")
    registry = default_synthetic_registry()
    assert registry.resolve(item, resolver_version="v1", effective_time=None).rationale_code == "historical_validity_unknown"
    with pytest.raises(TypeError, match="verified_effective_time"):
        registry.resolve(item, resolver_version="v1", effective_time=NOW)


def test_effective_time_cannot_be_reused_for_a_different_document():
    item = mention("Synthetic Meridian", doc="doc-other")
    with pytest.raises(ValueError, match="different document"):
        default_synthetic_registry().resolve(item, resolver_version="v1", effective_time=verified_time("some-other-doc"))


def test_failed_attempt_validation_binds_document_and_all_evidence_roles():
    text = "Meridian reported revenue after review"
    source = AnalysisInput("doc", body=text)
    valid_attempt = attempt(
        aspect_ref=("tax-v1", "revenue"),
        aspect_mention_ids=("a1",),
        aspect_evidence=(span("body", text.index("revenue"), "revenue", "aspect"),),
        relation_evidence=(span("body", 0, text, "relation"),),
    )
    validated = validate_entity_link_attempt(valid_attempt, analysis_input=source, normalized_document=normalize_document(source))
    assert require_validated_entity_link_attempt(validated) is valid_attempt

    missing_evidence = attempt()
    accepted_missing = validate_entity_link_attempt(missing_evidence, analysis_input=source, normalized_document=normalize_document(source))
    assert require_validated_entity_link_attempt(accepted_missing).aspect_evidence == ()

    invented = replace(valid_attempt, entity_evidence=(span("body", 0, "Invented", "entity"),))
    with pytest.raises(ValueError, match="quote"):
        validate_entity_link_attempt(invented, analysis_input=source, normalized_document=normalize_document(source))
    out_of_range = replace(valid_attempt, relation_evidence=(EvidenceSpan(field="body", start=0, end=len(text) + 20, quote="x" * (len(text) + 20), role="relation"),))
    with pytest.raises(ValueError, match="exceeds"):
        validate_entity_link_attempt(out_of_range, analysis_input=source, normalized_document=normalize_document(source))
    with pytest.raises(ValueError, match="document_ref"):
        validate_entity_link_attempt(valid_attempt, analysis_input=AnalysisInput("other", body=text), normalized_document=normalize_document(AnalysisInput("other", body=text)))
    with pytest.raises(ValueError, match="source-validated"):
        require_validated_entity_link_attempt(valid_attempt)
