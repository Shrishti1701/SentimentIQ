import re
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import database.models  # noqa: F401
from database.connection import Base
from intelligence.contracts import EvidenceSpan
from intelligence.entity_contracts import DeterministicIdFactory, EntityMention
from registry.entity_resolver import ProductionRegistryResolver
from registry.identity import registry_id
from registry.models import (
    CompanyAlias,
    ExchangeListing,
    RegistryCompany,
    RegistryRowAudit,
    RegistrySnapshot,
    RegistrySource,
    Security,
)


FACTORY = DeterministicIdFactory()


@pytest.fixture
def resolver_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session


def source(snapshot, filename):
    return RegistrySource(
        external_id=registry_id("SOURCE", {"filename": filename, "snapshot": snapshot.external_id}),
        snapshot=snapshot,
        original_filename=filename,
        source_url="https://example.test/" + filename,
        retrieval_date=date(2026, 11, 4),
        sha256_checksum="a" * 64,
        file_format="csv",
        usage_permission_status="public_nse_market_data",
    )


def snapshot(session, scope="NSE_CURRENT_LISTINGS", filename="fixture.csv"):
    item = RegistrySnapshot(
        external_id=registry_id("SNAPSHOT", {"scope": scope, "fixture": filename}),
        dataset_scope=scope,
        snapshot_state="published",
        source_manifest_json='[{"filename":"fixture.csv"}]',
        validation_counts_json='{"accepted": 1}',
        published_at=date(2026, 11, 6),
    )
    item_source = source(item, filename)
    session.add_all((item, item_source))
    session.flush()
    return item


def mention(text, namespace=None, start=0, document_ref="resolver-test"):
    observation = "security_identifier_candidate" if namespace else "organization_name_candidate"
    mention_id = FACTORY.mention_id(
        document_ref=document_ref,
        field="body",
        start=start,
        end=start + len(text),
        observation_kind=observation,
        security_namespace=namespace,
        extractor_version="extractor-v1",
    )
    return EntityMention(
        mention_id, document_ref, text, "body", start, start + len(text), observation,
        EvidenceSpan("body", start, start + len(text), text, "entity"),
        "extractor-v1", namespace,
    )


def add_verified_listing(session, name, symbol, isin):
    company = RegistryCompany(
        external_id=registry_id("COMPANY", {"name": name}),
        canonical_legal_name=name,
    )
    security = Security(
        external_id=registry_id("SECURITY", {"isin": isin}),
        instrument_classification="equity",
        isin=isin,
        isin_verified=True,
        issuer_company=company,
    )
    listing = ExchangeListing(
        external_id=registry_id("LISTING", {"symbol": symbol, "isin": isin}),
        security=security,
        company=company,
        exchange_code="NSE",
        symbol=symbol,
        series="EQ",
    )
    session.add_all((company, security, listing))
    session.flush()
    return company, security, listing


def test_exact_isin_symbol_and_name_resolution(resolver_session):
    snapshot(resolver_session)
    company, _, _ = add_verified_listing(
        resolver_session, "Alpha Holdings Limited", "ALPHA", "INE000A01012"
    )
    resolver_session.commit()
    resolver = ProductionRegistryResolver(resolver_session)

    for item in (
        mention("INE000A01012", "ISIN"),
        mention("ALPHA", "NSE"),
        mention("Alpha Holdings Limited"),
    ):
        result = resolver.resolve(item)
        assert result.status == "resolved"
        assert result.selected_entity_id.startswith("COMPANY:")

    assert resolver.resolve(mention("ALPHA", "NSE")).candidates[0].supporting_security_ids


def test_verified_alias_ambiguity_and_unknown(resolver_session):
    snapshot(resolver_session)
    first = RegistryCompany(external_id=registry_id("COMPANY", {"name": "First"}), canonical_legal_name="First")
    second = RegistryCompany(external_id=registry_id("COMPANY", {"name": "Second"}), canonical_legal_name="Second")
    resolver_session.add_all((first, second))
    resolver_session.flush()
    source_record = resolver_session.scalars(__import__("sqlalchemy").select(RegistrySource)).all()[0]
    resolver_session.add_all((
        CompanyAlias(
            company=first, source=source_record, original_alias="Shared",
            normalized_alias_key="SHARED", alias_type="verified_alias",
        ),
        CompanyAlias(
            company=second, source=source_record, original_alias="Shared",
            normalized_alias_key="SHARED", alias_type="verified_alias",
        ),
    ))
    resolver_session.commit()

    result = ProductionRegistryResolver(resolver_session).resolve(mention("SHARED"))
    assert result.status == "ambiguous"
    assert len(result.candidates) == 2
    assert ProductionRegistryResolver(resolver_session).resolve(mention("Unknown")).status == "unresolved"


def test_unverified_issuer_and_unpublished_historical_are_abstained(resolver_session):
    snapshot(resolver_session)
    company = RegistryCompany(external_id=registry_id("COMPANY", {"name": "Unverified"}), canonical_legal_name="Unverified")
    security = Security(
        external_id=registry_id("SECURITY", {"isin": "INE000A01013"}),
        instrument_classification="equity",
        isin="INE000A01013",
        isin_verified=True,
        issuer_company=None,
    )
    resolver_session.add_all((company, security))
    resolver_session.commit()
    assert ProductionRegistryResolver(resolver_session).resolve(
        mention("INE000A01013", "ISIN")
    ).status == "unresolved"


def test_resolution_is_deterministic_and_preserves_offsets(resolver_session):
    snapshot(resolver_session)
    add_verified_listing(resolver_session, "Deterministic Limited", "DET", "INE000A01014")
    resolver_session.commit()
    resolver = ProductionRegistryResolver(resolver_session)
    item = mention("DET", "NSE", start=17)
    first = resolver.resolve(item)
    second = resolver.resolve(item)
    assert first == second
    assert item.evidence.start == 17
    assert item.evidence.end == item.evidence.start + len(item.surface_text)
    assert item.evidence.quote == item.surface_text
