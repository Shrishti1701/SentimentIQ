from pathlib import Path

import pytest

from ingestion.nse_rss_parser import FeedParseError, parse_rss


FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_observed_fields_without_assigning_a_timezone():
    result = parse_rss((FIXTURES / "nse_rss_synthetic.xml").read_bytes())

    assert len(result.announcements) == 2
    first = result.announcements[0]
    assert first.title == "Synthetic Example Finance Limited"
    assert first.link == "https://example.invalid/filings/synthetic-001.pdf"
    assert first.published_raw == "04-Nov-2026 11:59:36"
    assert first.published_at_unzoned.isoformat() == "2026-11-04T11:59:36"
    assert first.timezone_status == "unknown"
    assert first.published_at is None
    assert "SUBJECT: Synthetic quarterly results" in first.summary
    assert first.identity_method == "url"
    assert result.issues == ()


def test_reports_missing_fields_and_uses_design_fallback_identity():
    feed = """<rss version="2.0"><channel><item>
      <title>Synthetic Missing Link Co</title>
      <pubDate>04-Nov-2026 11:59:36</pubDate>
      <description>Synthetic missing-link record</description>
    </item></channel></rss>"""

    result = parse_rss(feed)

    assert len(result.announcements) == 1
    assert result.announcements[0].identity_method == "fallback"
    assert "missing_link" in result.issues


def test_deduplicates_by_conservatively_normalized_link():
    feed = """<rss version="2.0"><channel>
      <item><title>Synthetic A</title><link>HTTPS://EXAMPLE.INVALID:443/path#section</link><pubDate>04-Nov-2026 11:59:36</pubDate><description>One</description></item>
      <item><title>Changed title</title><link>https://example.invalid/path</link><pubDate>05-Nov-2026 11:59:36</pubDate><description>Two</description></item>
    </channel></rss>"""

    result = parse_rss(feed)

    assert len(result.announcements) == 1
    assert result.duplicate_count == 1


def test_malformed_timestamp_is_reported_and_not_normalized():
    feed = """<rss version="2.0"><channel><item>
      <title>Synthetic Date Case</title><link>https://example.invalid/date</link>
      <pubDate>not-a-date</pubDate><description>Synthetic timestamp test</description>
    </item></channel></rss>"""

    result = parse_rss(feed)

    assert len(result.announcements) == 1
    assert result.announcements[0].published_raw == "not-a-date"
    assert result.announcements[0].published_at_unzoned is None
    assert "malformed_published" in result.issues


def test_empty_valid_feed_returns_no_announcements():
    result = parse_rss((FIXTURES / "nse_rss_empty.xml").read_bytes())

    assert result.announcements == ()
    assert result.duplicate_count == 0
    assert result.issues == ()


def test_malformed_xml_and_empty_document_raise_feed_parse_error():
    with pytest.raises(FeedParseError):
        parse_rss(b"<rss><channel><item>")
    with pytest.raises(FeedParseError, match="empty"):
        parse_rss("  \n")
