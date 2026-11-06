import sqlite3
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import database.models  # noqa: F401
from database.connection import Base
from registry.identity import registry_id
from registry.services import RegistryService, RegistryValidationError
from registry.models import (
    Company,
    CompanyAlias,
    ExchangeListing,
    ListingSymbolHistory,
    RegistryRowAudit,
    RegistrySnapshot,
    RegistrySource,
    Security,
)


@pytest.fixture
def registry_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session


def make_source(snapshot=None):
    return RegistrySource(
        external_id=registry_id("SOURCE", {"filename": "fixture.csv", "checksum": "a" * 64}),
        snapshot=snapshot,
        original_filename="fixture.csv",
        source_url="https://example.test/fixture.csv",
        retrieval_date=date(2026, 11, 4),
        sha256_checksum="a" * 64,
        file_format="csv",
        usage_permission_status="review_required",
    )


def test_registry_models_create_all_relationships(registry_session):
    snapshot = RegistrySnapshot(
        external_id=registry_id("SNAPSHOT", {"version": "fixture-1"}),
        snapshot_state="validated",
        source_manifest_json="[]",
        validation_counts_json='{"accepted": 1}',
    )
    registry_source = make_source(snapshot)
    company = Company(
        external_id=registry_id("COMPANY", {"name": "Fixture Holdings"}),
        canonical_legal_name="Fixture Holdings",
    )
    security = Security(
        external_id=registry_id("SECURITY", {"isin": "US0000000001"}),
        instrument_classification="equity",
        isin="US0000000001",
        isin_verified=True,
        issuer_company=company,
    )
    listing = ExchangeListing(
        external_id=registry_id("LISTING", {"exchange": "NSE", "symbol": "FIXTURE"}),
        security=security,
        company=company,
        exchange_code="NSE",
        symbol="FIXTURE",
        series="EQ",
        listing_date=date(2020, 1, 1),
        valid_from=date(2020, 1, 1),
    )
    alias = CompanyAlias(
        company=company,
        source=registry_source,
        original_alias="Fixture Holdings Limited",
        normalized_alias_key="fixture holdings",
        alias_type="verified_name",
        valid_from=date(2020, 1, 1),
        source_row_number=1,
    )
    history = ListingSymbolHistory(
        listing=listing,
        source=registry_source,
        previous_symbol="OLDFIX",
        new_symbol="FIXTURE",
        effective_date=date(2020, 1, 1),
        source_row_number=2,
    )
    audit = RegistryRowAudit(
        snapshot=snapshot,
        source=registry_source,
        source_row_number=1,
        raw_row_json='{"SYMBOL":"FIXTURE"}',
        validation_outcome="accepted",
        normalized_values_json='{"symbol":"FIXTURE"}',
    )
    registry_session.add_all((snapshot, registry_source, company, security, listing, alias, history, audit))
    registry_session.commit()

    assert security.issuer_company_id == company.id
    assert listing.security_id == security.id
    assert alias.company_id == company.id
    assert history.listing_id == listing.id
    assert audit.snapshot_id == snapshot.id


def test_company_security_and_multiple_exchange_listings(registry_session):
    company = Company(external_id=registry_id("COMPANY", {"name": "Multi Listing"}), canonical_legal_name="Multi Listing")
    security = Security(
        external_id=registry_id("SECURITY", {"isin": "US0000000002"}),
        instrument_classification="equity",
        isin="US0000000002",
        isin_verified=True,
        issuer_company=company,
    )
    nse = ExchangeListing(
        external_id=registry_id("LISTING", {"exchange": "NSE", "symbol": "ML"}),
        security=security,
        company=company,
        exchange_code="NSE",
        symbol="ML",
        valid_from=date(2021, 1, 1),
    )
    bse = ExchangeListing(
        external_id=registry_id("LISTING", {"exchange": "BSE", "symbol": "500001"}),
        security=security,
        company=company,
        exchange_code="BSE",
        symbol="500001",
        valid_from=date(2021, 1, 1),
    )
    registry_session.add_all((company, security, nse, bse))
    registry_session.commit()

    assert security.issuer_company_id == company.id
    assert {listing.exchange_code for listing in security.listings} == {"NSE", "BSE"}


def test_duplicate_external_id_and_isin_are_rejected(registry_session):
    registry_session.add_all((
        Company(external_id=registry_id("COMPANY", {"name": "Duplicate"}), canonical_legal_name="One"),
        Company(external_id=registry_id("COMPANY", {"name": "Duplicate"}), canonical_legal_name="Two"),
    ))
    with pytest.raises(IntegrityError):
        registry_session.commit()
    registry_session.rollback()

    registry_session.add_all((
        Security(external_id=registry_id("SECURITY", {"isin": "US0000000003"}), instrument_classification="equity", isin="US0000000003"),
        Security(external_id=registry_id("SECURITY", {"isin": "US0000000004"}), instrument_classification="equity", isin="US0000000003"),
    ))
    with pytest.raises(IntegrityError):
        registry_session.commit()


def test_invalid_isin_and_symbol_transition_are_rejected(registry_session):
    with pytest.raises(ValueError):
        Security(
            external_id=registry_id("SECURITY", {"isin": "invalid"}),
            instrument_classification="equity",
            isin="invalid",
        )

    snapshot = RegistrySnapshot(external_id=registry_id("SNAPSHOT", {"version": "invalid-1"}))
    registry_source = make_source(snapshot)
    registry_session.add_all((snapshot, registry_source))
    registry_session.flush()
    registry_session.add(ListingSymbolHistory(
        source=registry_source,
        previous_symbol="SAME",
        new_symbol="SAME",
        effective_date=date(2026, 1, 1),
        review_status="accepted",
    ))
    with pytest.raises(IntegrityError):
        registry_session.commit()


def test_snapshot_audit_and_alias_validity(registry_session):
    snapshot = RegistrySnapshot(external_id=registry_id("SNAPSHOT", {"version": "audit-1"}))
    registry_source = make_source(snapshot)
    registry_session.add_all((snapshot, registry_source))
    registry_session.flush()
    registry_session.add(RegistryRowAudit(
        snapshot=snapshot,
        source=registry_source,
        source_row_number=1,
        raw_row_json='{"SYMBOL":"TEST"}',
        validation_outcome="requires_review",
        reason="manual review fixture",
    ))
    registry_session.commit()
    assert registry_source.snapshot_id == snapshot.id

    company = Company(external_id=registry_id("COMPANY", {"name": "Validity Fixture"}), canonical_legal_name="Validity Fixture")
    registry_session.add(company)
    registry_session.flush()
    registry_session.add(CompanyAlias(
        company=company,
        source=registry_source,
        original_alias="Invalid Range",
        normalized_alias_key="invalid range",
        alias_type="historical_name",
        valid_from=date(2026, 2, 1),
        valid_to=date(2026, 1, 1),
    ))
    with pytest.raises(IntegrityError):
        registry_session.commit()


def test_registry_migration_is_idempotent_and_existing_database_compatible():
    migration = Path(__file__).resolve().parents[1] / "migrations" / "20261105_002_registry_foundation.sql"
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE existing_document (id INTEGER PRIMARY KEY)")
    connection.executescript(migration.read_text())
    connection.executescript(migration.read_text())
    tables = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {
        "existing_document",
        "registry_companies",
        "registry_securities",
        "registry_exchange_listings",
        "registry_company_aliases",
        "registry_listing_symbol_history",
        "registry_sources",
        "registry_snapshots",
        "registry_row_audit",
    }.issubset(tables)


def test_invalid_checksum_and_external_id_namespace_are_rejected(registry_session):
    with pytest.raises(ValueError):
        RegistrySource(
            external_id="REGISTRY-SOURCE:v1:" + "a" * 64,
            original_filename="bad.csv",
            source_url="https://example.test/bad.csv",
            retrieval_date=date(2026, 11, 4),
            sha256_checksum="A" * 64,
            file_format="csv",
        )

    with pytest.raises(ValueError):
        Company(
            external_id="REGISTRY-SECURITY:v1:" + "a" * 64,
            canonical_legal_name="Wrong Namespace",
        )


def test_snapshot_lifecycle_requires_complete_unresolved_free_snapshot(registry_session):
    snapshot = RegistrySnapshot(
        external_id=registry_id("SNAPSHOT", {"version": "lifecycle-1"}),
        source_manifest_json='["fixture.csv"]',
        validation_counts_json='{"accepted": 1}',
    )
    source = make_source(snapshot)
    source.external_id = registry_id("SOURCE", {"filename": "fixture.csv", "checksum": "a" * 64})
    registry_session.add_all((snapshot, source))
    registry_session.flush()

    service = RegistryService(registry_session)
    service.transition_snapshot(snapshot, "validated")
    assert snapshot.snapshot_state == "validated"

    service.transition_snapshot(snapshot, "published")
    assert snapshot.snapshot_state == "published"
    assert snapshot.published_at is not None

    with pytest.raises(RegistryValidationError):
        service.transition_snapshot(snapshot, "validated")


def test_snapshot_publication_is_independent_by_dataset_scope(registry_session):
    current = RegistrySnapshot(
        external_id=registry_id("SNAPSHOT", {"scope": "current"}),
        dataset_scope="NSE_CURRENT_LISTINGS",
        source_manifest_json='["EQUITY_L.csv"]',
        validation_counts_json='{"accepted": 1}',
    )
    historical = RegistrySnapshot(
        external_id=registry_id("SNAPSHOT", {"scope": "historical"}),
        dataset_scope="NSE_HISTORICAL_CHANGES",
        source_manifest_json='["namechange.csv"]',
        validation_counts_json='{"accepted": 1}',
    )
    current_source = make_source(current)
    current_source.external_id = registry_id("SOURCE", {"filename": "current.csv", "checksum": "a" * 64})
    current_source.original_filename = "current.csv"
    historical_source = make_source(historical)
    historical_source.external_id = registry_id("SOURCE", {"filename": "historical.csv", "checksum": "a" * 64})
    historical_source.original_filename = "historical.csv"
    registry_session.add_all((current, current_source, historical, historical_source))
    registry_session.flush()
    service = RegistryService(registry_session)
    service.transition_snapshot(current, "validated")
    service.transition_snapshot(historical, "validated")
    service.transition_snapshot(current, "published")
    service.transition_snapshot(historical, "published")
    assert current.snapshot_state == "published"
    assert historical.snapshot_state == "published"


def test_snapshot_scope_migration_preserves_existing_current_snapshot(registry_session):
    migration = Path(__file__).resolve().parents[1] / "migrations" / "20261106_004_snapshot_dataset_scopes.sql"
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        (Path(__file__).resolve().parents[1] / "migrations" / "20261105_002_registry_foundation.sql").read_text()
    )
    connection.executescript(
        (Path(__file__).resolve().parents[1] / "migrations" / "20261106_003_registry_hardening.sql").read_text()
    )
    connection.execute(
        "INSERT INTO registry_snapshots (external_id, snapshot_state, source_manifest_json, validation_counts_json, published_at) "
        "VALUES (?, 'published', '[{\"filename\":\"EQUITY_L.csv\"}]', '{}', CURRENT_TIMESTAMP)",
        ("REGISTRY-SNAPSHOT:v1:" + "a" * 64,),
    )
    connection.commit()
    connection.executescript(migration.read_text())
    scope = connection.execute(
        "SELECT dataset_scope FROM registry_snapshots WHERE snapshot_state = 'published'"
    ).fetchone()[0]
    assert scope == "NSE_CURRENT_LISTINGS"


def test_registry_hardening_migration_is_idempotent(registry_session):
    migration = Path(__file__).resolve().parents[1] / "migrations" / "20261106_003_registry_hardening.sql"
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        (Path(__file__).resolve().parents[1] / "migrations" / "20261105_002_registry_foundation.sql").read_text()
    )
    connection.executescript(migration.read_text())
    connection.executescript(migration.read_text())
