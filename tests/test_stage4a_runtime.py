from __future__ import annotations

import json
import pytest
import sqlite3
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from intelligence.contracts import AnalysisInput
from intelligence.stage4a.contracts import canonical_utc
from intelligence.stage4a.runtime import (
    Stage4APipeline,
    adapt_legacy_comparison,
    adapt_legacy_competitor,
    extract_aspect_mentions,
)
from intelligence.synthetic_registry import (
    SyntheticCompany,
    SyntheticRegistry,
    Validity,
)
from intelligence.entity_extractor import extract_entity_mentions
from database.connection import Base
from database.models import Stage4ARecord
from database.models import Stage4ASupersession
from database.stage4a_persistence import (
    persist_stage4a_result,
    persist_stage4a_result_with_supersessions,
    replace_stage4a_record,
    delete_stage4a_record,
)
from intelligence.stage4a.contracts import EvidenceSupersession
from intelligence.stage4a.runtime_support import find_supersession_conflicts


VALIDITY = Validity(None, None)


def registry(*companies: SyntheticCompany) -> SyntheticRegistry:
    return SyntheticRegistry("runtime-test-v1", tuple(companies), ())


def company(identifier: str, name: str) -> SyntheticCompany:
    return SyntheticCompany(identifier, name, VALIDITY)


def test_valid_company_aspect_link_is_generated_from_runtime_evidence():
    pipeline = Stage4APipeline(registry(company("COMPANY:A", "Alpha Holdings")))
    result = pipeline.process(AnalysisInput("doc", body="Alpha Holdings reported revenue."))

    assert len(result.links) == 1
    link = result.links[0]
    assert link.resolved_company_id == "COMPANY:A"
    assert link.aspect_code == "revenue"
    assert link.entity_evidence.quote == "Alpha Holdings"
    assert link.aspect_evidence.quote == "revenue"
    assert len(result.observations) == 1


def test_multiple_companies_produce_separate_links():
    pipeline = Stage4APipeline(registry(
        company("COMPANY:A", "Alpha Holdings"),
        company("COMPANY:B", "Beta Holdings"),
    ))
    result = pipeline.process(AnalysisInput(
        "doc",
        body="Alpha Holdings reported revenue. Beta Holdings reported debt.",
    ))

    assert {link.resolved_company_id for link in result.links} == {"COMPANY:A", "COMPANY:B"}
    assert len({link.link_id for link in result.links}) == 2


def test_coordinated_subject_and_company_resolution_ambiguity_are_conservative():
    shared = SyntheticCompany(
        "COMPANY:A",
        "Shared Holdings",
        VALIDITY,
        aliases=(("Shared Name", VALIDITY, "fixture:a"),),
    )
    other = SyntheticCompany(
        "COMPANY:B",
        "Other Holdings",
        VALIDITY,
        aliases=(("Shared Name", VALIDITY, "fixture:b"),),
    )
    coordinated_pipeline = Stage4APipeline(registry(
        company("COMPANY:A", "Alpha Holdings"),
        company("COMPANY:B", "Beta Holdings"),
    ))
    coordinated = coordinated_pipeline.process(AnalysisInput(
        "doc",
        body="Alpha Holdings and Beta Holdings reported revenue.",
    ))
    assert {link.attribution_role for link in coordinated.links} == {"coordinated_subject"}

    ambiguous = Stage4APipeline(registry(shared, other)).process(AnalysisInput(
        "ambiguous",
        body="Shared Name reported revenue.",
    ))
    assert [resolution.status for resolution in ambiguous.resolutions] == ["ambiguous"]
    assert not ambiguous.links


def test_unknown_aspect_is_preserved():
    document = AnalysisInput("doc", body="Alpha Holdings reported customer satisfaction.")
    mentions = extract_aspect_mentions(document)

    unknown = [mention for mention in mentions if mention.aspect_code == "unknown_aspect"]
    assert len(unknown) == 1
    assert unknown[0].unknown_reason == "unlisted_taxonomy_concept"


def test_profitability_and_profit_are_separate_mentions():
    document = AnalysisInput(
        "doc",
        body="Profitability improved, while profit increased, and net profit increased.",
    )
    mentions = extract_aspect_mentions(document)
    codes = [mention.aspect_code for mention in mentions]

    assert "profitability" in codes
    assert "profit" in codes
    assert "net_profit" in codes
    assert codes.count("profit") >= 1


@pytest.mark.parametrize("raw", (
    "2026-11-04T06:29:36Z",
    "2026-11-04T06:29:36.123456Z",
))
def test_verified_publication_timestamp_is_canonically_serialized(raw):
    assert canonical_utc(raw).endswith("Z")


def test_claimed_timezone_without_authority_has_no_runtime_utc_conversion():
    document = AnalysisInput(
        "doc",
        body="Revenue rose.",
        published_at_raw="2026-11-04 06:29:36",
        timezone_status="claimed",
    )
    assert document.published_at_raw == "2026-11-04 06:29:36"
    assert document.timezone_status == "claimed"
    assert document.published_at is None


def test_competitor_relation_requires_two_resolved_endpoints():
    pipeline = Stage4APipeline(registry(
        company("COMPANY:A", "Alpha Holdings"),
        company("COMPANY:B", "Beta Holdings"),
    ))
    complete = pipeline.process(AnalysisInput(
        "doc",
        body="Alpha Holdings is a competitor of Beta Holdings.",
    ))
    assert len(complete.competitor_occurrences) == 1
    occurrence = complete.competitor_occurrences[0]
    assert {occurrence.left_company_id, occurrence.right_company_id} == {
        "COMPANY:A", "COMPANY:B",
    }

    insufficient = pipeline.process(AnalysisInput(
        "other",
        body="Alpha Holdings is a competitor of an unknown issuer.",
    ))
    assert not insufficient.competitor_occurrences


def test_duplicate_processing_is_deterministic_and_serializable():
    pipeline = Stage4APipeline(registry(company("COMPANY:A", "Alpha Holdings")))
    document = AnalysisInput("doc", body="Alpha Holdings reported revenue.")

    first = pipeline.process(document)
    second = pipeline.process(document)

    assert first.to_dict() == second.to_dict()
    assert first.links[0].link_id == second.links[0].link_id


def test_observations_are_associated_bidirectionally_and_result_is_json_serializable():
    pipeline = Stage4APipeline(registry(company("COMPANY:A", "Alpha Holdings")))
    result = pipeline.process(AnalysisInput("doc", body="Alpha Holdings reported revenue."))

    assert result.links[0].observation_ids
    observation = result.observations[0]
    assert observation.observation_id in result.links[0].observation_ids
    assert result.links[0].link_id in observation.link_ids
    assert json.loads(result.to_json())["document_ref"] == "doc"


def test_legacy_adapters_preserve_supported_records_and_abstain_when_evidence_is_missing():
    supported = adapt_legacy_comparison(
        document_ref="doc",
        legacy_id="legacy-comparison-1",
        entity_ref="COMPANY:A",
        aspect_ref="revenue",
        evidence_quote="Alpha Holdings reported revenue",
    )
    abstained = adapt_legacy_competitor(
        document_ref="doc",
        legacy_id="legacy-competitor-1",
        left_company_id="COMPANY:A",
        right_company_id=None,
        evidence_quote="Alpha competes with an unknown issuer",
    )

    assert supported.records
    assert not supported.unavailable
    assert not abstained.records
    assert abstained.unavailable[0]["reason"] == "missing_resolved_endpoints"


def test_pipeline_consumes_upstream_stage3_resolution_without_resubmitting_to_registry(monkeypatch):
    document = AnalysisInput("doc", body="Alpha Holdings reported revenue.")
    pipeline = Stage4APipeline(registry(company("COMPANY:A", "Alpha Holdings")))
    preprocessed = pipeline.process(document)
    mentions = preprocessed.entity_mentions
    alpha_mentions = tuple(item for item in mentions if item.surface_text == "Alpha Holdings")
    upstream_resolution = pipeline.registry.resolve_result(
        alpha_mentions[0],
        resolver_version="stage3-production-fixture-v1",
        effective_time=None,
        id_factory=pipeline._factory,
    )

    def fail_if_resolved(*args, **kwargs):
        raise AssertionError("upstream resolution was resubmitted to Stage 3")

    monkeypatch.setattr(type(pipeline.registry), "resolve_result", fail_if_resolved)
    result = pipeline.process(
        document,
        upstream_mentions=alpha_mentions,
        upstream_resolutions=(upstream_resolution,),
    )

    assert result.links[0].resolution_result_id == upstream_resolution.resolution_id
    assert result.links[0].resolved_company_id == "COMPANY:A"


def test_stage4a_records_persist_idempotently_in_existing_sqlalchemy_architecture():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    pipeline = Stage4APipeline(registry(company("COMPANY:A", "Alpha Holdings")))
    result = pipeline.process(AnalysisInput("doc", body="Alpha Holdings reported revenue."))

    first = persist_stage4a_result(result, factory)
    second = persist_stage4a_result(result, factory)

    assert first.inserted_count > 0
    assert second.inserted_count == 0
    assert second.duplicate_count == first.inserted_count
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Stage4ARecord)) == first.inserted_count


def test_supersession_and_records_persist_atomically_and_are_idempotent():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    pipeline = Stage4APipeline(registry(company("COMPANY:A", "Alpha Holdings")))
    result = pipeline.process(AnalysisInput("doc-a", body="Alpha Holdings reported revenue."))
    supersession = EvidenceSupersession(
        supersession_id="supersession-test-v1",
        superseded_observation_id="observation-old",
        replacement_observation_id="observation-new",
        document_ref="doc-a",
        source_field="body",
        start=0,
        end=13,
        quote="Alpha Holding",
        supersession_reason="source_correction",
    )
    supersession.validate(source="Alpha Holding")
    result = replace(result, supersessions=(supersession,))

    first = persist_stage4a_result_with_supersessions(result, factory)
    second = persist_stage4a_result_with_supersessions(result, factory)

    assert first.inserted_count > 0
    assert second.inserted_count == 0
    assert second.duplicate_count == first.inserted_count
    with factory() as session:
        persisted = session.scalar(select(Stage4ASupersession).where(
            Stage4ASupersession.supersession_id == supersession.supersession_id
        ))
        assert persisted is not None
        assert persisted.document_ref == "doc-a"


def test_failed_supersession_persistence_rolls_back_stage4a_records():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    pipeline = Stage4APipeline(registry(company("COMPANY:A", "Alpha Holdings")))
    result = pipeline.process(AnalysisInput("doc-a", body="Alpha Holdings reported revenue."))
    invalid = SimpleNamespace(
        supersession_id="invalid-supersession",
        superseded_observation_id="observation-old",
        replacement_observation_id=None,
        document_ref="doc-a",
        source_field="body",
        start=0,
        end=5,
        quote="Alpha",
        supersession_reason="source_correction",
        immutable_payload=lambda: {},
    )
    result = replace(result, supersessions=(invalid,))

    try:
        persist_stage4a_result_with_supersessions(result, factory)
    except Exception:
        pass
    else:
        raise AssertionError("missing NOT NULL constraint should fail persistence")

    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Stage4ARecord)) == 0
        assert session.scalar(select(func.count()).select_from(Stage4ASupersession)) == 0


def test_stage4a_replacement_and_deletion_are_explicit():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    pipeline = Stage4APipeline(registry(company("COMPANY:A", "Alpha Holdings")))
    result = pipeline.process(AnalysisInput("doc-a", body="Alpha Holdings reported revenue."))
    persist_stage4a_result(result, factory)
    record_id = result.links[0].link_id

    replace_stage4a_record(record_id, "entity-aspect-link", {"link_id": record_id, "replacement": True}, "doc-a", factory)
    assert delete_stage4a_record(record_id, factory)
    assert not delete_stage4a_record(record_id, factory)


def test_stage4a_migration_applies_to_existing_sqlite_schema():
    connection = sqlite3.connect(":memory:")
    connection.executescript("""
        CREATE TABLE financial_articles (id INTEGER PRIMARY KEY);
    """)
    migration = Path(__file__).resolve().parents[1] / "migrations" / "20261105_001_stage4a_records.sql"
    connection.executescript(migration.read_text())
    connection.executescript(migration.read_text())

    tables = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {"financial_articles", "stage4a_records", "stage4a_supersessions"}.issubset(tables)


def test_cross_document_supersession_conflict_is_reported():
    conflicts = find_supersession_conflicts((
        ("supersession:a", "observation-old", "observation-a"),
        ("supersession:b", "observation-old", "observation-b"),
    ))

    assert len(conflicts) == 1
    assert conflicts[0].reason == "multiple_successors_for_predecessor"
    assert set(conflicts[0].supersession_ids) == {"supersession:a", "supersession:b"}
