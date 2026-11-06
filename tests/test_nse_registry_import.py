import csv
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import database.models  # noqa: F401
from database.connection import Base
from registry.models import ExchangeListing, RegistryRowAudit, RegistrySnapshot, RegistrySource, Security
from registry.nse_import import NSERegistryImporter, read_nse_csv, sha256_file


@pytest.fixture
def registry_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session


def _write_csv(path: Path, fieldnames: list[str], rows: list[list[str]], bom: bool = False) -> None:
    encoding = "utf-8-sig" if bom else "utf-8"
    with path.open("w", encoding=encoding, newline="") as output:
        writer = csv.writer(output)
        writer.writerow(fieldnames)
        writer.writerows(rows)


def _equity_directory(directory: Path, *, sme: bool = True) -> tuple[Path, Path]:
    _write_csv(
        directory / "EQUITY_L.csv",
        ["SYMBOL", "NAME OF COMPANY", " SERIES ", " DATE OF LISTING ", "PAID UP VALUE", "MARKET LOT", " ISIN NUMBER ", "FACE VALUE"],
        [["TEST", "Test Holdings Limited", "EQ", "06-NOV-2026", "10", "1", "INE000A01012", "10"]],
        bom=True,
    )
    sme_rows = [["TEST", "Test Holdings Limited", "SM", "08-Dec-22", "10", "INE000A01012", "10", ""]]
    _write_csv(
        directory / "SME_EQUITY_L.csv",
        ["SYMBOL", "NAME_OF_COMPANY", "SERIES", "DATE_OF_LISTING", "PAID_UP_VALUE", "ISIN_NUMBER", "FACE_VALUE", ""],
        sme_rows if sme else [],
        bom=False,
    )
    return directory / "EQUITY_L.csv", directory / "SME_EQUITY_L.csv"


def test_actual_nse_headers_and_bahetis_overlap():
    raw = Path(__file__).resolve().parents[1] / "data" / "registry" / "raw" / "nse"
    equity = read_nse_csv(raw / "EQUITY_L.csv")
    sme = read_nse_csv(raw / "SME_EQUITY_L.csv")
    bahetti_equity = [row for row in equity if row.get("SYMBOL") == "BAHETI"]
    assert len(bahetti_equity) == 1
    assert bahetti_equity[0]["ISIN_NUMBER"] == "INE029Q01017"
    bahetis = [row for row in sme if row.get("SYMBOL") == "BAHETI"]
    assert len(bahetis) == 1
    assert bahetis[0]["ISIN_NUMBER"] == bahetti_equity[0]["ISIN_NUMBER"]


def test_actual_nse_import_publishes_one_snapshot(registry_session):
    raw = Path(__file__).resolve().parents[1] / "data" / "registry" / "raw" / "nse"
    importer = NSERegistryImporter(registry_session, raw)
    report = importer.import_current_listings()
    assert report.equity_rows == 2630
    assert report.sme_rows == 582
    assert report.rejected_rows == 0
    assert report.quarantined_rows == 0
    assert report.overlap_details
    assert report.snapshot_state == "published"
    assert registry_session.scalar(select(func.count()).select_from(RegistrySnapshot)) == 1
    assert registry_session.scalar(select(func.count()).select_from(Security)) == report.unique_verified_securities


def test_actual_historical_nse_import_is_validated_and_idempotent(registry_session):
    raw = Path(__file__).resolve().parents[1] / "data" / "registry" / "raw" / "nse"
    importer = NSERegistryImporter(registry_session, raw)
    importer.import_current_listings()
    first = importer.import_historical_changes()
    second = importer.import_historical_changes()
    assert first["snapshot_external_id"] == second["snapshot_external_id"]
    assert first["snapshot_state"] == "validated"
    assert first["accepted"] > 0
    assert first["duplicates"] > 0
    assert registry_session.scalar(select(func.count()).select_from(RegistrySnapshot)) == 2


def test_repeated_import_is_idempotent(registry_session, tmp_path):
    _equity_directory(tmp_path)
    importer = NSERegistryImporter(registry_session, tmp_path)
    first = importer.import_current_listings()
    second = importer.import_current_listings()
    assert first.snapshot_external_id == second.snapshot_external_id
    assert registry_session.scalar(select(func.count()).select_from(RegistrySnapshot)) == 1
    assert registry_session.scalar(select(func.count()).select_from(ExchangeListing)) == 2


def test_invalid_isin_and_missing_field_are_audited(registry_session, tmp_path):
    _write_csv(
        tmp_path / "EQUITY_L.csv",
        ["SYMBOL", "NAME OF COMPANY", "SERIES", "DATE OF LISTING", "ISIN NUMBER"],
        [["BAD", "", "EQ", "06-NOV-2026", "not-an-isin"]],
        bom=True,
    )
    _write_csv(tmp_path / "SME_EQUITY_L.csv", ["SYMBOL", "NAME_OF_COMPANY", "SERIES", "DATE_OF_LISTING", "ISIN_NUMBER"], [])
    report = NSERegistryImporter(registry_session, tmp_path).import_current_listings(publish=False)
    assert report.rejected_rows == 1
    assert report.quarantined_rows == 0
    audit = registry_session.scalars(select(RegistryRowAudit)).one()
    assert audit.validation_outcome == "rejected"
    assert "missing required fields" in audit.reason
    assert json.loads(audit.raw_row_json)["SYMBOL"] == "BAD"


def test_quarantined_invalid_isin_is_preserved(registry_session, tmp_path):
    _write_csv(
        tmp_path / "EQUITY_L.csv",
        ["SYMBOL", "NAME OF COMPANY", "SERIES", "DATE OF LISTING", "ISIN NUMBER"],
        [["BADISIN", "Test Company Limited", "EQ", "06-NOV-2026", "BAD00000001"]],
        bom=True,
    )
    _write_csv(tmp_path / "SME_EQUITY_L.csv", ["SYMBOL", "NAME_OF_COMPANY", "SERIES", "DATE_OF_LISTING", "ISIN_NUMBER"], [])
    report = NSERegistryImporter(registry_session, tmp_path).import_current_listings(publish=False)
    assert report.quarantined_rows == 1
    assert registry_session.scalar(select(func.count()).select_from(RegistryRowAudit)) == 1


def test_source_checksum_and_changed_content_create_new_snapshot(registry_session, tmp_path):
    equity_path, sme_path = _equity_directory(tmp_path)
    importer = NSERegistryImporter(registry_session, tmp_path)
    first = importer.import_current_listings(publish=False)
    original = sha256_file(equity_path)
    with equity_path.open("a", encoding="utf-8") as output:
        output.write("CHANGED,T Changed Company Limited,EQ,07-NOV-2026,10,1,INE000B01010,10\n")
    assert sha256_file(equity_path) != original
    second = importer.import_current_listings(publish=False)
    assert first.snapshot_external_id != second.snapshot_external_id
    assert registry_session.scalar(select(func.count()).select_from(RegistrySnapshot)) == 2


def test_rollback_on_database_error(registry_session, tmp_path):
    equity_path, sme_path = _equity_directory(tmp_path)
    equity_path.write_bytes(equity_path.read_bytes() + b"\xff")
    with pytest.raises((UnicodeDecodeError, UnicodeError)):
        NSERegistryImporter(registry_session, tmp_path).import_current_listings()
    assert registry_session.scalar(select(func.count()).select_from(RegistrySnapshot)) == 0
