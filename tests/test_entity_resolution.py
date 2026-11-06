import pytest

from intelligence.contracts import EvidenceSpan
from intelligence.entity_contracts import DeterministicIdFactory, EntityMention
from intelligence.synthetic_registry import (
    SyntheticCompany,
    SyntheticRegistry,
    SyntheticSecurity,
    Validity,
)


VALIDITY = Validity(None, None)
FACTORY = DeterministicIdFactory()


def mention(text: str, *, namespace=None, document_ref="resolution-test", start=0):
    kind = "security_identifier_candidate" if namespace is not None else "organization_name_candidate"
    mention_id = FACTORY.mention_id(
        document_ref=document_ref,
        field="body",
        start=start,
        end=start + len(text),
        observation_kind=kind,
        security_namespace=namespace,
        extractor_version="extractor-v1",
    )
    return EntityMention(
        mention_id,
        document_ref,
        text,
        "body",
        start,
        start + len(text),
        kind,
        EvidenceSpan("body", start, start + len(text), text, "entity"),
        "extractor-v1",
        namespace,
    )


def test_duplicate_verified_alias_is_ambiguous():
    registry = SyntheticRegistry(
        "resolution-test-v1",
        (
            SyntheticCompany(
                "COMPANY:A",
                "Alpha Holdings",
                VALIDITY,
                aliases=(("Shared Name", VALIDITY, "fixture:alpha-alias"),),
            ),
            SyntheticCompany(
                "COMPANY:B",
                "Beta Holdings",
                VALIDITY,
                aliases=(("Shared Name", VALIDITY, "fixture:beta-alias"),),
            ),
        ),
        (),
    )

    decision = registry.resolve(mention("Shared Name"), resolver_version="resolver-v1", effective_time=None)

    assert decision.status == "ambiguous"
    assert [candidate.entity_id for candidate in decision.candidates] == ["COMPANY:A", "COMPANY:B"]
    assert decision.selected_entity_id is None


@pytest.mark.parametrize(
    ("namespace", "identifier", "security_id"),
    [
        ("NSE", "SYNTH-A", "SECURITY:NSE-A"),
        ("BSE", "SYNTH-B", "SECURITY:BSE-B"),
        ("ISIN", "SYNUS000001", "SECURITY:ISIN-C"),
    ],
)
def test_explicit_security_namespaces_resolve_to_verified_issuer(namespace, identifier, security_id):
    registry = SyntheticRegistry(
        "resolution-test-v1",
        (SyntheticCompany("COMPANY:A", "Alpha Holdings", VALIDITY),),
        (
            SyntheticSecurity(
                security_id,
                namespace,
                identifier,
                "COMPANY:A",
                True,
                VALIDITY,
                f"fixture:{namespace.lower()}",
            ),
        ),
    )

    decision = registry.resolve(
        mention(identifier, namespace=namespace),
        resolver_version="resolver-v1",
        effective_time=None,
    )

    assert decision.status == "resolved"
    assert decision.selected_entity_id == "COMPANY:A"
    assert decision.candidates[0].supporting_security_ids == (security_id,)


def test_security_identifier_never_resolves_through_another_namespace():
    registry = SyntheticRegistry(
        "resolution-test-v1",
        (SyntheticCompany("COMPANY:A", "Alpha Holdings", VALIDITY),),
        (
            SyntheticSecurity(
                "SECURITY:NSE-A",
                "NSE",
                "SYNTH-A",
                "COMPANY:A",
                True,
                VALIDITY,
                "fixture:nse",
            ),
        ),
    )

    decision = registry.resolve(
        mention("SYNTH-A", namespace="BSE"),
        resolver_version="resolver-v1",
        effective_time=None,
    )

    assert decision.status == "unresolved"
    assert decision.candidates == ()
    assert decision.rationale_code == "no_registry_match"


def test_duplicate_security_records_do_not_collapse_to_one_resolved_issuer():
    registry = SyntheticRegistry(
        "resolution-test-v1",
        (SyntheticCompany("COMPANY:A", "Alpha Holdings", VALIDITY),),
        (
            SyntheticSecurity(
                "SECURITY:NSE-A",
                "NSE",
                "SYNTH-A",
                "COMPANY:A",
                True,
                VALIDITY,
                "fixture:nse-a",
            ),
            SyntheticSecurity(
                "SECURITY:NSE-A-2",
                "NSE",
                "SYNTH-A",
                "COMPANY:A",
                True,
                VALIDITY,
                "fixture:nse-a-2",
            ),
        ),
    )

    decision = registry.resolve(
        mention("SYNTH-A", namespace="NSE"),
        resolver_version="resolver-v1",
        effective_time=None,
    )

    assert decision.status == "unresolved"
    assert decision.selected_entity_id is None
    assert decision.candidates == ()
    assert decision.rationale_code == "conflicting_registry_evidence"


def test_unverified_or_missing_issuer_mapping_is_not_inferred():
    registry = SyntheticRegistry(
        "resolution-test-v1",
        (SyntheticCompany("COMPANY:A", "Alpha Holdings", VALIDITY),),
        (
            SyntheticSecurity(
                "SECURITY:NSE-A",
                "NSE",
                "SYNTH-A",
                "COMPANY:A",
                False,
                VALIDITY,
                "fixture:unverified",
            ),
        ),
    )

    decision = registry.resolve(
        mention("SYNTH-A", namespace="NSE"),
        resolver_version="resolver-v1",
        effective_time=None,
    )

    assert decision.status == "unresolved"
    assert decision.selected_entity_id is None
    assert decision.candidates == ()


def test_same_company_mentions_resolve_independently_and_deterministically():
    registry = SyntheticRegistry(
        "resolution-test-v1",
        (SyntheticCompany("COMPANY:A", "Alpha Holdings", VALIDITY),),
        (),
    )
    first = mention("Alpha Holdings", document_ref="same-doc", start=0)
    second = mention("Alpha Holdings", document_ref="same-doc", start=16)

    first_decision = registry.resolve(first, resolver_version="resolver-v1", effective_time=None)
    second_decision = registry.resolve(second, resolver_version="resolver-v1", effective_time=None)
    first_result = registry.resolve_result(
        first,
        resolver_version="resolver-v1",
        effective_time=None,
        id_factory=FACTORY,
    )
    second_result = registry.resolve_result(
        second,
        resolver_version="resolver-v1",
        effective_time=None,
        id_factory=FACTORY,
    )

    assert first_decision == second_decision
    assert first_result.resolution_id != second_result.resolution_id
