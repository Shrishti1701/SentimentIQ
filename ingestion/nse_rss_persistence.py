"""Transactional persistence for parsed NSE announcements.

This layer accepts parser records only. It performs no network access, polling,
NLP, or fetch of linked documents. Usage must remain disabled for live NSE data
until storage permissions are confirmed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from database.models import FinancialArticle, NSEAnnouncementMetadata
from ingestion.nse_rss_parser import (
    Announcement,
    SOURCE_NAME,
    _identity,
    _normalize_link,
    _parse_unzoned_timestamp,
)


LOGGER = logging.getLogger(__name__)
MAX_UNIQUE_CONFLICT_RETRIES = 2
KNOWN_UNIQUE_CONSTRAINTS = {
    "uq_article_source_url",
    "uq_nse_source_item_key",
}


class InvalidAnnouncementError(ValueError):
    """A parsed item cannot satisfy the existing article schema safely."""


class PersistenceError(RuntimeError):
    """The SQLAlchemy transaction failed and was rolled back."""


@dataclass(frozen=True)
class IngestionReport:
    inserted_count: int
    duplicate_count: int


def _validate(record: Announcement) -> None:
    # FinancialArticle.source_url and original_text are non-null, and its URL
    # has an existing unique constraint. A fallback identity without a link is
    # not representable without inventing a URL, so it must not be persisted.
    if not isinstance(record, Announcement):
        raise InvalidAnnouncementError("record must be an Announcement parsed by the RSS parser")
    if not isinstance(record.link, str) or not record.link or record.link != record.link.strip():
        raise InvalidAnnouncementError("a valid source link is required")
    if _normalize_link(record.link) is None:
        raise InvalidAnnouncementError("source link must be a valid HTTP or HTTPS URL")
    if record.identity_method != "url":
        raise InvalidAnnouncementError("only URL-based announcement identities can be persisted")
    if len(record.link) > 2048:
        raise InvalidAnnouncementError("source link exceeds the model's 2048 character limit")
    if not isinstance(record.summary, str) or not record.summary.strip():
        raise InvalidAnnouncementError("a non-empty summary is required by FinancialArticle.original_text")
    if record.title is not None and not isinstance(record.title, str):
        raise InvalidAnnouncementError("source title must be text")
    if record.title is not None and len(record.title) > 300:
        raise InvalidAnnouncementError("source title exceeds metadata column limit")
    if not isinstance(record.identity_key, str) or not record.identity_key.strip():
        raise InvalidAnnouncementError("source identity key must be non-empty text")
    if record.published_raw is not None and not isinstance(record.published_raw, str):
        raise InvalidAnnouncementError("raw timestamp must be text or None")
    expected_identity = _identity(record.title, record.link, record.published_raw, record.summary)
    if expected_identity != (record.identity_key, "url"):
        raise InvalidAnnouncementError("source identity key does not match the normalized URL")
    if len(record.identity_key) > 100:
        raise InvalidAnnouncementError("source identity key exceeds metadata column limit")
    if record.published_raw is not None and len(record.published_raw) > 100:
        raise InvalidAnnouncementError("raw timestamp exceeds metadata column limit")
    if record.published_at_unzoned is not None and not isinstance(record.published_at_unzoned, datetime):
        raise InvalidAnnouncementError("unzoned timestamp must be a datetime or None")
    if record.published_at_unzoned is not None and record.published_at_unzoned.tzinfo is not None:
        raise InvalidAnnouncementError("unzoned timestamp must not contain timezone information")
    if _parse_unzoned_timestamp(record.published_raw) != record.published_at_unzoned:
        raise InvalidAnnouncementError("raw and unzoned timestamp values are inconsistent")
    if record.timezone_status != "unknown":
        raise InvalidAnnouncementError("timestamp timezone must remain unknown until NSE confirms its semantics")


def _is_known_unique_conflict(error: IntegrityError) -> bool:
    """Recognize only the URL and source-key unique constraints.

    PostgreSQL drivers expose the declared constraint name. SQLite does not,
    so its exact unique-column diagnostic is matched as a fallback; this is
    needed for the isolated SQLite tests and does not match other integrity
    failures such as foreign-key or NOT NULL violations.
    """
    original = error.orig
    diagnostic = getattr(original, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    if constraint_name in KNOWN_UNIQUE_CONSTRAINTS:
        return True

    message = str(original)
    return message in {
        "UNIQUE constraint failed: financial_articles.source_url",
        "UNIQUE constraint failed: nse_announcement_metadata.source_item_key",
    }


def persist_announcements(
    records: Iterable[Announcement],
    session_factory: sessionmaker[Session],
) -> IngestionReport:
    """Insert parsed records atomically and idempotently using the supplied DB.

    All validation happens before opening a transaction. Existing source keys
    and existing article URLs are treated as duplicates. Unique constraints on
    both URL and source key provide database-level protection across runs.
    """
    batch = tuple(records)
    for record in batch:
        _validate(record)

    # Guard duplicate identities even if callers bypass the parser's feed-level
    # de-duplication. Preserve first occurrence and count later copies.
    unique_batch: list[Announcement] = []
    seen: set[str] = set()
    duplicates = 0
    for record in batch:
        if record.identity_key in seen:
            duplicates += 1
        else:
            seen.add(record.identity_key)
            unique_batch.append(record)
    in_batch_duplicates = duplicates

    attempt = 0
    while True:
        inserted = 0
        duplicates = in_batch_duplicates
        try:
            with session_factory.begin() as session:
                for record in unique_batch:
                    existing_metadata = session.scalar(
                        select(NSEAnnouncementMetadata).where(
                            NSEAnnouncementMetadata.source_item_key == record.identity_key
                        )
                    )
                    existing_article = session.scalar(
                        select(FinancialArticle).where(FinancialArticle.source_url == record.link)
                    )
                    if existing_metadata is not None or existing_article is not None:
                        duplicates += 1
                        continue

                    article = FinancialArticle(
                        source_url=record.link,
                        source_name=SOURCE_NAME,
                        published_at=None,
                        original_text=record.summary,
                    )
                    article.nse_metadata = NSEAnnouncementMetadata(
                        source_item_key=record.identity_key,
                        identity_method=record.identity_method,
                        source_title=record.title,
                        published_at_raw=record.published_raw,
                        published_at_unzoned=record.published_at_unzoned,
                        timezone_status=record.timezone_status,
                    )
                    session.add(article)
                    inserted += 1
        except IntegrityError as exc:
            if _is_known_unique_conflict(exc) and attempt < MAX_UNIQUE_CONFLICT_RETRIES:
                # The transaction context has rolled back. Re-run the whole
                # batch in a fresh transaction so the winning row is visible.
                attempt += 1
                LOGGER.warning(
                    "nse_rss_unique_conflict_retry",
                    extra={"event": "nse_rss_unique_conflict_retry", "attempt": attempt},
                )
                continue
            LOGGER.error(
                "nse_rss_persistence_failed",
                extra={"event": "nse_rss_persistence_failed", "error_type": type(exc).__name__},
            )
            raise PersistenceError("NSE announcement transaction failed and was rolled back") from exc
        except Exception as exc:
            # Do not put SQL text, parameters, URLs, summaries, or exception
            # messages in logs. The session context rolls back on failure.
            LOGGER.error(
                "nse_rss_persistence_failed",
                extra={"event": "nse_rss_persistence_failed", "error_type": type(exc).__name__},
            )
            if isinstance(exc, PersistenceError):
                raise
            raise PersistenceError("NSE announcement transaction failed and was rolled back") from exc

        LOGGER.info(
            "nse_rss_persistence_complete",
            extra={
                "event": "nse_rss_persistence_complete",
                "inserted_count": inserted,
                "duplicate_count": duplicates,
            },
        )
        return IngestionReport(inserted_count=inserted, duplicate_count=duplicates)
