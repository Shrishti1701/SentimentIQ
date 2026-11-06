from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import database.models  # noqa: F401
from database.connection import Base
from database.models import DocumentAnalysisRun, FinancialArticle, NSEAnnouncementMetadata
from ingestion.article_adapter import article_to_analysis_input
from intelligence.stage4a.runtime import Stage4APipeline
from services.document_analysis_service import DocumentAnalysisService


def make_article(session, *, text="Alpha Holdings reported revenue growth.") -> FinancialArticle:
    article = FinancialArticle(
        source_url="https://example.test/announcement",
        source_name="NSE",
        original_text=text,
        published_at=None,
    )
    session.add(article)
    session.flush()
    session.add(NSEAnnouncementMetadata(
        article_id=article.id,
        source_item_key="ann-1",
        identity_method="rss",
        source_title="Corporate Update",
        timezone_status="unknown",
    ))
    session.flush()
    return article


def test_article_adapter_preserves_source_and_conservative_time():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        article = make_article(session)
        document = article_to_analysis_input(article)

    assert document.document_ref == "nse:ann-1"
    assert document.title == "Corporate Update"
    assert document.body == "Alpha Holdings reported revenue growth."
    assert document.published_at is None
    assert document.timezone_status == "unknown"


def test_orchestration_persists_once_and_duplicate_retry_is_noop():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as session:
        article = make_article(session)
        session.commit()
        service = DocumentAnalysisService(
            session, Stage4APipeline(registry=None)
        )

        with session.begin():
            first = service.process_article(article.id)
            assert first.result is not None
            assert first.document_ref == "nse:ann-1"

        with session.begin():
            duplicate = service.process_article(article.id)
            assert duplicate.duplicate is True
            assert duplicate.result is None

    with factory() as session:
        assert session.scalar(
            DocumentAnalysisRun.__table__.select()
        ) is not None
