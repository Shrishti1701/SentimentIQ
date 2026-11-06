"""Fetch and inspect NSE's official corporate-announcements RSS feed.

This manual workflow fetches the live feed, validates parsed records, and
persists them through the existing transactional NSE RSS persistence layer.
"""

from __future__ import annotations

import html
import re
import sys
from typing import Any

import feedparser
import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.settings import settings
from ingestion.nse_rss_parser import FeedParseError, parse_rss
from ingestion.nse_rss_persistence import InvalidAnnouncementError, PersistenceError, persist_announcements


FEED_URL = "https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml"
REQUEST_TIMEOUT = (5, 20)
MAX_DISPLAY_RECORDS = 20
USER_AGENT = "SentimentIQ RSS feasibility check/0.1"


def _plain_text(value: Any) -> str:
    """Convert an RSS summary to readable, bounded terminal text."""
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]*>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_and_display() -> int:
    """Retrieve, validate, and persist the current NSE announcement feed."""
    print(f"Feed URL: {FEED_URL}")

    try:
        response = requests.get(
            FEED_URL,
            headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml"},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.Timeout as exc:
        print(f"Network error: request timed out ({exc})", file=sys.stderr)
        return 2
    except requests.exceptions.RequestException as exc:
        print(f"Network error: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 2

    content_type = response.headers.get("Content-Type", "not provided")
    print(f"HTTP status: {response.status_code}")
    print(f"Content-Type: {content_type}")

    if response.status_code in (401, 403):
        print("Access denied by the server; no retry or restriction bypass was attempted.", file=sys.stderr)
        return 3
    if not response.ok:
        print(f"HTTP error: server returned {response.status_code}.", file=sys.stderr)
        return 3
    if not response.content:
        print("Empty response: the server returned no feed content.", file=sys.stderr)
        print("Records retrieved: 0")
        return 0

    try:
        response_text = getattr(response, "text", None)
        if response_text is None:
            response_text = response.content.decode(response.encoding or "utf-8", errors="replace")
        result = parse_rss(response_text)
        persistable = tuple(
            announcement
            for announcement in result.announcements
            if announcement.identity_method == "url"
        )
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        engine = create_engine(
            settings.database_url,
            connect_args={"connect_timeout": 10} if settings.database_url.startswith("postgresql") else {},
            pool_pre_ping=True,
        )
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        report = persist_announcements(persistable, factory)
    except FeedParseError as exc:
        print(f"Invalid RSS feed: {exc}", file=sys.stderr)
        return 4
    except (InvalidAnnouncementError, PersistenceError, RuntimeError) as exc:
        print(f"Persistence error: {exc}", file=sys.stderr)
        return 5

    entries = len(result.announcements) + result.duplicate_count
    print(f"Records fetched: {entries}")
    print(f"Records parsed: {len(result.announcements)}")
    print(f"Records inserted: {report.inserted_count}")
    print(f"Duplicates skipped: {report.duplicate_count}")
    if result.issues:
        print(f"Valid-entry issues: {len(result.issues)}")

    parsed_feed = feedparser.parse(response.content)
    parsed = parsed_feed

    entries = parsed.entries
    print(f"Feed title: {parsed.feed.get('title', 'not provided')}")
    print(f"Records retrieved: {len(entries)}")

    if not entries:
        if parsed.bozo:
            print("No entries could be parsed from the response.", file=sys.stderr)
        else:
            print("The feed parsed successfully but contained no records.")
        return 0

    keys = set()
    for entry in entries:
        keys.update(entry.keys())
    print("Available entry fields: " + ", ".join(sorted(keys)))

    for index, entry in enumerate(entries[:MAX_DISPLAY_RECORDS], start=1):
        title = _plain_text(entry.get("title")) or "(no title)"
        link = entry.get("link") or "(no link)"
        published = (
            entry.get("published")
            or entry.get("updated")
            or entry.get("created")
            or "(no publication date)"
        )
        description = _plain_text(
            entry.get("description") or entry.get("summary") or entry.get("subtitle")
        )
        if len(description) > 500:
            description = description[:497] + "..."

        print(f"\n[{index}] {title}")
        print(f"    Link: {link}")
        print(f"    Published: {published}")
        print(f"    Description: {description or '(not provided)'}")

    if len(entries) > MAX_DISPLAY_RECORDS:
        print(f"\nDisplayed {MAX_DISPLAY_RECORDS} of {len(entries)} parsed records.")
    if parsed.bozo and entries:
        print("Some records were parsed despite the malformed-feed warning.")
    return 0


if __name__ == "__main__":
    raise SystemExit(fetch_and_display())
