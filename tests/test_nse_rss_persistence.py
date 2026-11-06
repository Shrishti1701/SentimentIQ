import sqlite3
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, delete, event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from database.connection import Base
from database.models import FinancialArticle, NSEAnnouncementMetadata
from ingestion.nse_rss_parser import parse_rss
from ingestion.nse_rss_persistence import (
    InvalidAnnouncementError,
    PersistenceError,
    persist_announcements,
)


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def db_factory():
    """A fresh, isolated in-memory SQLite database for every test."""
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(connection, _connection_record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


def synthetic_records():
    return parse_rss((FIXTURES / "nse_rss_synthetic.xml").read_bytes()).announcements


def row_counts(factory):
    with factory() as session:
        return (
            session.scalar(select(func.count()).select_from(FinancialArticle)),
            session.scalar(select(func.count()).select_from(NSEAnnouncementMetadata)),
        )


def test_successful_insertion_preserves_timestamp_and_leaves_published_at_null(db_factory):
    report = persist_announcements(synthetic_records(), db_factory)

    assert report.inserted_count == 2
    assert report.duplicate_count == 0
    with db_factory() as session:
        articles = session.scalars(select(FinancialArticle).order_by(FinancialArticle.id)).all()
        assert len(articles) == 2
        first = articles[0]
        assert first.source_name == "NSE RSS"
        assert first.original_text.startswith("Quarterly results announced")
        assert first.published_at is None
        assert first.nse_metadata.published_at_raw == "04-Nov-2026 11:59:36"
        assert first.nse_metadata.published_at_unzoned.isoformat() == "2026-11-04T11:59:36"
        assert first.nse_metadata.timezone_status == "unknown"


def test_duplicate_is_detected_across_separate_ingestion_runs(db_factory):
    records = synthetic_records()

    first = persist_announcements(records[:1], db_factory)
    second = persist_announcements(records, db_factory)

    assert first.inserted_count == 1
    assert second.inserted_count == 1
    assert second.duplicate_count == 1
    assert row_counts(db_factory) == (2, 2)


def test_repeated_ingestion_is_idempotent(db_factory):
    records = synthetic_records()

    reports = [persist_announcements(records, db_factory) for _ in range(3)]

    assert [(item.inserted_count, item.duplicate_count) for item in reports] == [
        (2, 0),
        (0, 2),
        (0, 2),
    ]
    assert row_counts(db_factory) == (2, 2)


@pytest.mark.parametrize(
    "feed, expected_message",
    [
        (
            '<rss version="2.0"><channel><item><title>Synthetic</title>'
            '<pubDate>04-Nov-2026 11:59:36</pubDate><description>Body</description>'
            '</item></channel></rss>',
            "source link",
        ),
        (
            '<rss version="2.0"><channel><item><title>Synthetic</title>'
            '<link>https://example.invalid/no-summary</link>'
            '<pubDate>04-Nov-2026 11:59:36</pubDate></item></channel></rss>',
            "non-empty summary",
        ),
    ],
)
def test_missing_required_fields_are_rejected_without_writes(db_factory, feed, expected_message):
    record = parse_rss(feed).announcements[0]

    with pytest.raises(InvalidAnnouncementError, match=expected_message):
        persist_announcements([record], db_factory)

    assert row_counts(db_factory) == (0, 0)


@pytest.mark.parametrize(
    "changes, expected_message",
    [
        ({"link": "ftp://example.invalid/file"}, "HTTP or HTTPS"),
        ({"link": "http://[malformed"}, "HTTP or HTTPS"),
        ({"summary": " \t\n "}, "non-empty summary"),
        ({"identity_key": " \t "}, "identity key"),
        ({"identity_key": "v1:url:" + "0" * 64}, "does not match"),
        ({"published_at_unzoned": datetime(2026, 11, 4, 12, 0)}, "inconsistent"),
        ({"published_at_unzoned": "not a datetime"}, "must be a datetime"),
    ],
)
def test_rejects_invalid_or_inconsistent_announcement_objects(db_factory, changes, expected_message):
    record = replace(synthetic_records()[0], **changes)

    with pytest.raises(InvalidAnnouncementError, match=expected_message):
        persist_announcements([record], db_factory)

    assert row_counts(db_factory) == (0, 0)


def test_transaction_rolls_back_all_rows_when_later_record_fails(db_factory):
    engine = db_factory.kw["bind"]
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TRIGGER fail_synthetic_second_metadata "
                "BEFORE INSERT ON nse_announcement_metadata "
                "WHEN NEW.source_title = 'Synthetic Sample Bank Limited' "
                "BEGIN SELECT RAISE(ABORT, 'synthetic test failure'); END"
            )
        )

    with pytest.raises(PersistenceError, match="rolled back"):
        persist_announcements(synthetic_records(), db_factory)

    assert row_counts(db_factory) == (0, 0)


def test_known_unique_conflict_retries_and_rechecks_as_duplicate(db_factory):
    records = synthetic_records()
    persist_announcements(records[:1], db_factory)
    engine = db_factory.kw["bind"]
    constructed_sessions = []

    class StaleFirstReadSession(Session):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            constructed_sessions.append(self)
            self.hide_reads = len(constructed_sessions) == 1

        def scalar(self, statement, *args, **kwargs):
            # Deterministically simulate another worker committing the same
            # row after this transaction's read and before its insert.
            if self.hide_reads:
                return None
            return super().scalar(statement, *args, **kwargs)

    race_factory = sessionmaker(
        bind=engine,
        class_=StaleFirstReadSession,
        expire_on_commit=False,
    )
    report = persist_announcements(records, race_factory)

    assert report.inserted_count == 1
    assert report.duplicate_count == 1
    assert len(constructed_sessions) == 2
    assert row_counts(db_factory) == (2, 2)


def test_sqlite_rejects_invalid_foreign_key_reference(db_factory):
    with db_factory.kw["bind"].connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1

    with pytest.raises(IntegrityError):
        with db_factory.begin() as session:
            session.add(
                NSEAnnouncementMetadata(
                    article_id=9999,
                    source_item_key="synthetic-invalid-fk",
                    identity_method="url",
                )
            )


def test_database_cascade_deletes_associated_metadata(db_factory):
    persist_announcements(synthetic_records()[:1], db_factory)
    with db_factory() as session:
        article_id = session.scalar(select(FinancialArticle.id))
        assert session.scalar(
            select(NSEAnnouncementMetadata.id).where(
                NSEAnnouncementMetadata.article_id == article_id
            )
        ) is not None

    # Core DELETE bypasses ORM relationship cascades and verifies the declared
    # database ON DELETE CASCADE with SQLite foreign keys enabled.
    with db_factory.kw["bind"].begin() as connection:
        connection.execute(delete(FinancialArticle).where(FinancialArticle.id == article_id))

    assert row_counts(db_factory) == (0, 0)


def test_database_connection_failure_is_reported():
    def fail_connection():
        raise sqlite3.OperationalError("synthetic SQLite connection failure")

    engine = create_engine("sqlite://", creator=fail_connection)

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(connection, _connection_record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    broken_factory = sessionmaker(bind=engine)
    try:
        with pytest.raises(PersistenceError, match="rolled back"):
            persist_announcements(synthetic_records()[:1], broken_factory)
    finally:
        engine.dispose()
