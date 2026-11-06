"""Contract tests for the initial API endpoints."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from api.main import app
from database.models import Aspect, Company, FinancialArticle, SentimentPrediction
from database.connection import Base
from database.models import NSEAnnouncementMetadata
from registry.identity import registry_id
from registry.models import RegistryCompany

client = TestClient(app)


def test_root_returns_application_information() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["name"] == "SentimentIQ"


def test_health_does_not_require_external_services() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_status_reports_api_capabilities() -> None:
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    body = response.json()
    assert body["database"] in {"ok", "configured", "unavailable"}
    assert body["live_data_enabled"] is False
    assert body["capabilities"]["nse_announcements"] == "available"


def test_database_models_expose_expected_fields_and_constraints() -> None:
    assert {"source_url", "source_name", "published_at", "collected_at", "original_text"}.issubset(
        FinancialArticle.__table__.columns.keys()
    )
    assert "identifier" in Company.__table__.columns
    assert "label" in Aspect.__table__.columns
    assert {
        "company_id", "aspect_id", "sentiment_label", "confidence_score",
        "supporting_evidence", "model_version",
    }.issubset(SentimentPrediction.__table__.columns.keys())
    assert any(
        constraint.name == "uq_article_source_url"
        for constraint in FinancialArticle.__table__.constraints
    )


def test_api_read_and_analysis_endpoints_with_isolated_database() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app.state.session_factory = factory
    client_with_db = TestClient(app)

    with factory() as session:
        article = FinancialArticle(
            source_url="https://example.test/api-announcement",
            source_name="NSE",
            original_text="Revenue outlook remains unchanged.",
            published_at=None,
        )
        session.add(article)
        session.flush()
        article.nse_metadata = NSEAnnouncementMetadata(
            source_item_key="api-ann-1",
            identity_method="url",
            source_title="API Test Announcement",
            timezone_status="unknown",
        )
        session.add(RegistryCompany(
            external_id=registry_id("COMPANY", {"name": "API Registry Company"}),
            canonical_legal_name="API Registry Company",
        ))
        session.commit()
        article_id = article.id

    announcements = client_with_db.get("/api/v1/announcements?page=1&page_size=10")
    assert announcements.status_code == 200
    assert announcements.json()["total"] == 1
    assert client_with_db.get(f"/api/v1/announcements/{article_id}").status_code == 200
    assert client_with_db.get("/api/v1/companies?q=API").json()["total"] == 1

    analyzed = client_with_db.post(f"/api/v1/announcements/{article_id}/analyze")
    assert analyzed.status_code == 200
    assert analyzed.json()["status"] == "completed"
    duplicate = client_with_db.post(f"/api/v1/announcements/{article_id}/analyze")
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True

    runs = client_with_db.get("/api/v1/analysis-runs")
    assert runs.status_code == 200
    assert runs.json()["total"] == 1
    assert client_with_db.get(
        f"/api/v1/analysis-runs/{runs.json()['items'][0]['run_id']}"
    ).status_code == 200
    assert client_with_db.get("/api/v1/registry/summary").status_code == 200
    assert client_with_db.get("/api/v1/intelligence").status_code == 200
    del app.state.session_factory
