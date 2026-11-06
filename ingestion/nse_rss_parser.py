"""In-memory parser for the observed NSE announcements RSS entry fields.

This module parses supplied bytes/text only. It performs no network requests and
does not write feed or announcement content to disk or a database.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import feedparser


LOGGER = logging.getLogger(__name__)
SOURCE_NAME = "NSE RSS"
IDENTITY_VERSION = "v1"
PUBLISHED_FORMAT = "%d-%b-%Y %H:%M:%S"


class FeedParseError(ValueError):
    """Raised when the supplied document is not a parseable RSS feed."""


@dataclass(frozen=True)
class Announcement:
    """A parsed source record kept in memory; not an ORM/database model."""

    title: str | None
    link: str | None
    published_raw: str | None
    published_at_unzoned: datetime | None
    summary: str | None
    identity_key: str
    identity_method: str
    timezone_status: str = "unknown"

    @property
    def published_at(self) -> None:
        """ORM-compatible timestamp remains unset until NSE confirms timezone."""
        return None


@dataclass(frozen=True)
class ParseResult:
    announcements: tuple[Announcement, ...]
    duplicate_count: int
    issues: tuple[str, ...]


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_link(link: str) -> str | None:
    """Conservatively canonicalize a URL per the design; keep query/path intact."""
    try:
        parts = urlsplit(link.strip())
        scheme = parts.scheme.lower()
        hostname = parts.hostname
        if scheme not in {"http", "https"} or not hostname:
            return None
        host = hostname.lower()
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = parts.port
        if port is not None and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
            host = f"{host}:{port}"
        if parts.username or parts.password:
            return None
        return urlunsplit((scheme, host, parts.path, parts.query, ""))
    except ValueError:
        return None


def _identity(title: str | None, link: str | None, published: str | None, summary: str | None) -> tuple[str, str] | None:
    if link:
        normalized_link = _normalize_link(link)
        if normalized_link:
            payload = f"{SOURCE_NAME}\0{IDENTITY_VERSION}\0url\0{normalized_link}"
            return f"{IDENTITY_VERSION}:url:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}", "url"

    # Lower-confidence fallback from the design, used only when the link is absent/invalid.
    if title and published and summary:
        normalized_title = unicodedata.normalize("NFKC", title).casefold()
        normalized_summary = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", summary)).strip()
        fallback = [SOURCE_NAME, IDENTITY_VERSION, normalized_title, published, normalized_summary]
        payload = json.dumps(fallback, ensure_ascii=False, separators=(",", ":"))
        return f"{IDENTITY_VERSION}:fallback:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}", "fallback"
    return None


def _parse_unzoned_timestamp(raw: str | None) -> datetime | None:
    if raw is None:
        return None
    try:
        # This is the only format observed in the feasibility pilot. Keep it naive:
        # the source did not include a timezone marker and NSE semantics are unconfirmed.
        return datetime.strptime(raw.strip(), PUBLISHED_FORMAT)
    except ValueError:
        return None


def parse_rss(document: str | bytes) -> ParseResult:
    """Parse RSS data in memory and return unique entries plus content-free issues."""
    if not document or not document.strip():
        raise FeedParseError("RSS document is empty")

    parsed = feedparser.parse(document)
    if parsed.bozo:
        LOGGER.error("nse_rss_parse_failed", extra={"event": "nse_rss_parse_failed", "error_type": type(parsed.bozo_exception).__name__})
        raise FeedParseError(f"RSS XML could not be parsed ({type(parsed.bozo_exception).__name__})")

    announcements: list[Announcement] = []
    issues: list[str] = []
    seen: set[str] = set()
    duplicate_count = 0

    for entry in parsed.entries:
        title = _optional_text(entry.get("title"))
        link = _optional_text(entry.get("link"))
        published = _optional_text(entry.get("published"))
        summary = _optional_text(entry.get("summary"))
        entry_issues: list[str] = []
        if title is None:
            entry_issues.append("missing_title")
        if link is None:
            entry_issues.append("missing_link")
        elif _normalize_link(link) is None:
            entry_issues.append("malformed_link")
        if published is None:
            entry_issues.append("missing_published")
        if summary is None:
            entry_issues.append("missing_summary")

        published_at_unzoned = _parse_unzoned_timestamp(published)
        if published is not None and published_at_unzoned is None:
            entry_issues.append("malformed_published")

        identity = _identity(title, link, published, summary)
        if identity is None:
            entry_issues.append("missing_reliable_identity")
            issues.extend(entry_issues)
            LOGGER.warning("nse_rss_entry_rejected", extra={"event": "nse_rss_entry_rejected", "issue_codes": entry_issues})
            continue

        key, method = identity
        issues.extend(entry_issues)
        if key in seen:
            duplicate_count += 1
            LOGGER.info("nse_rss_duplicate", extra={"event": "nse_rss_duplicate", "identity_method": method})
            continue
        seen.add(key)
        announcements.append(
            Announcement(
                title=title,
                link=link,
                published_raw=published,
                published_at_unzoned=published_at_unzoned,
                summary=summary,
                identity_key=key,
                identity_method=method,
            )
        )

    LOGGER.info(
        "nse_rss_parse_complete",
        extra={
            "event": "nse_rss_parse_complete",
            "entry_count": len(parsed.entries),
            "announcement_count": len(announcements),
            "duplicate_count": duplicate_count,
            "issue_count": len(issues),
        },
    )
    return ParseResult(tuple(announcements), duplicate_count, tuple(issues))
