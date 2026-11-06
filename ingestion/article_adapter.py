"""Adapter from persisted NSE announcements to the Stage 1 analysis contract."""

from __future__ import annotations

from intelligence.contracts import AnalysisInput
from database.models import FinancialArticle


class InvalidArticleSource(ValueError):
    pass


def article_to_analysis_input(article: FinancialArticle) -> AnalysisInput:
    if not isinstance(article, FinancialArticle):
        raise TypeError("article must be a FinancialArticle")
    if not isinstance(article.source_url, str) or not article.source_url.strip():
        raise InvalidArticleSource("article source URL is required")
    if not isinstance(article.original_text, str) or not article.original_text.strip():
        raise InvalidArticleSource("article original text is required")

    metadata = article.nse_metadata
    title = metadata.source_title if metadata is not None else None
    if title is not None and not isinstance(title, str):
        raise InvalidArticleSource("article source title must be text")

    timezone_status = metadata.timezone_status if metadata is not None else "unknown"
    published_at = article.published_at
    if timezone_status == "unknown":
        if published_at is not None:
            raise InvalidArticleSource("timezone-aware publication time requires verified NSE timezone semantics")
    elif not timezone_status.startswith("verified_"):
        raise InvalidArticleSource("unsupported NSE timezone status")

    if timezone_status.startswith("verified_"):
        if published_at is None or published_at.tzinfo is None or published_at.utcoffset() is None:
            raise InvalidArticleSource("verified publication time requires an aware datetime")

    document_ref = (
        f"nse:{metadata.source_item_key}"
        if metadata is not None and metadata.source_item_key
        else f"article:{article.id}"
    )
    return AnalysisInput(
        document_ref=document_ref,
        title=title if title and title.strip() else None,
        body=article.original_text,
        source_name=article.source_name,
        published_at=published_at if timezone_status.startswith("verified_") else None,
        published_at_raw=metadata.published_at_raw if metadata is not None else None,
        published_at_unzoned=metadata.published_at_unzoned if metadata is not None else None,
        timezone_status=timezone_status,
    )
