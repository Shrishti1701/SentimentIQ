"""FastAPI application entry point for production SentimentIQ services."""

from __future__ import annotations

import json
import logging
import os
from datetime import date
from typing import Any, Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from config.settings import settings
from database.connection import get_engine
from database.models import (
    DocumentAnalysisRun,
    FinancialArticle,
    NSEAnnouncementMetadata,
    Stage4ARecord,
)
from intelligence.stage4a.runtime import Stage4APipeline
from registry.models import RegistryRowAudit, RegistrySnapshot
from services.api_service import ApiAnnouncementService, ApiRegistryService
from services.document_analysis_service import (
    AnalysisInProgress,
    DocumentAnalysisService,
    PIPELINE_VERSION,
)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    version=settings.api_version,
    description="Aspect-based financial sentiment intelligence; not stock-price prediction.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "SENTIMENTIQ_CORS_ORIGINS",
            "http://localhost:8501,http://127.0.0.1:8501",
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = request.headers.get("x-request-id", uuid4().hex)
    logger.info("api_request request_id=%s method=%s path=%s", request_id, request.method, request.url.path)
    try:
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        logger.info(
            "api_response request_id=%s method=%s path=%s status=%s",
            request_id, request.method, request.url.path, response.status_code,
        )
        return response
    except Exception:
        logger.exception("api_request_failed request_id=%s method=%s path=%s",
                         request_id, request.method, request.url.path)
        raise


def session_factory() -> sessionmaker[Session]:
    factory = getattr(app.state, "session_factory", None)
    if factory is not None:
        return factory
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    from database.connection import Base
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Session:
    try:
        with session_factory()() as session:
            yield session
    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail={"code": "database_unavailable", "message": "Database is unavailable"},
        )


def db_error(exc: Exception) -> HTTPException:
    logger.exception("database_api_error")
    return HTTPException(
        status_code=503,
        detail={"code": "database_error", "message": "The database operation failed and was rolled back"},
    )


def page_metadata(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "page": result["page"],
        "page_size": result["page_size"],
        "total": result["total"],
    }


def announcement_payload(article: FinancialArticle) -> dict[str, Any]:
    metadata = article.nse_metadata
    return {
        "announcement_id": article.id,
        "document_ref": (
            f"nse:{metadata.source_item_key}" if metadata is not None
            else f"article:{article.id}"
        ),
        "source_name": article.source_name,
        "source_url": article.source_url,
        "title": metadata.source_title if metadata is not None else None,
        "published_at": article.published_at,
        "collected_at": article.collected_at,
        "timezone_status": metadata.timezone_status if metadata is not None else "unknown",
    }


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {"name": settings.app_name, "description": app.description or ""}


@app.get("/health", tags=["system"])
@app.get("/api/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status", tags=["system"])
@app.get("/api/v1/status", tags=["system"])
def project_status() -> dict[str, Any]:
    try:
        if getattr(app.state, "session_factory", None) is None and not settings.database_url:
            raise RuntimeError("database is not configured")
        if getattr(app.state, "session_factory", None) is None:
            database_status = "configured"
        else:
            session = session_factory()()
            session.execute(select(func.count()).select_from(FinancialArticle)).scalar_one()
            session.close()
            database_status = "ok"
    except (SQLAlchemyError, RuntimeError):
        database_status = "unavailable"
    return {
        "project": settings.app_name,
        "stage": "production",
        "database": database_status,
        "live_data_enabled": False,
        "database_configured": bool(settings.database_url) or getattr(app.state, "session_factory", None) is not None,
        "capabilities": {
            "api": "available",
            "nse_announcements": "available",
            "document_analysis": "available",
            "stage4a": "available",
        },
    }


@app.get("/api/v1/announcements", tags=["announcements"])
def list_announcements(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    company: str | None = Query(None, max_length=300),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    result = ApiAnnouncementService(session).list(
        page, page_size, from_date=from_date, to_date=to_date, company=company
    )
    return {"items": [announcement_payload(item) for item in result["items"]],
            **page_metadata(result)}


@app.get("/api/v1/announcements/{announcement_id}", tags=["announcements"])
def announcement_detail(announcement_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    article = ApiAnnouncementService(session).get(announcement_id)
    if article is None:
        raise HTTPException(404, {"code": "not_found", "message": "Announcement was not found"})
    return announcement_payload(article)


@app.post("/api/v1/announcements/{announcement_id}/analyze", tags=["analysis"])
def analyze_announcement(announcement_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    article = session.get(FinancialArticle, announcement_id)
    if article is None:
        raise HTTPException(404, {"code": "not_found", "message": "Announcement was not found"})
    metadata = article.nse_metadata
    document_ref = f"nse:{metadata.source_item_key}" if metadata is not None else f"article:{article.id}"
    existing = session.scalar(select(DocumentAnalysisRun).where(DocumentAnalysisRun.document_ref == document_ref))
    if existing is not None:
        if existing.status == "running":
            raise HTTPException(409, {"code": "analysis_in_progress", "message": "Analysis is already running"})
        return {"run_id": existing.id, "status": existing.status,
                "summary": json.loads(existing.result_summary_json), "duplicate": True}

    try:
        session.add(DocumentAnalysisRun(
            document_ref=document_ref, pipeline_version=PIPELINE_VERSION, status="running", result_summary_json="{}"
        ))
        session.flush()
        service = DocumentAnalysisService(session, Stage4APipeline(registry=None))
        report = service.process_article(announcement_id, allow_in_progress_claim=True)
        session.commit()
        run = session.scalar(select(DocumentAnalysisRun).where(DocumentAnalysisRun.document_ref == document_ref))
        return {"run_id": run.id, "status": run.status, "summary": json.loads(run.result_summary_json),
                "duplicate": False}
    except AnalysisInProgress:
        session.rollback()
        raise HTTPException(409, {"code": "analysis_in_progress", "message": "Analysis is already running"})
    except SQLAlchemyError as exc:
        session.rollback()
        if isinstance(exc, IntegrityError):
            raise HTTPException(409, {
                "code": "analysis_in_progress",
                "message": "Analysis is already running",
            }) from exc
        raise db_error(exc)
    except Exception as exc:
        session.rollback()
        logger.exception("document_analysis_failed announcement_id=%s", announcement_id)
        raise HTTPException(500, {"code": "analysis_failed", "message": "Document analysis failed"}) from exc


@app.get("/api/v1/analysis-runs", tags=["analysis"])
def list_analysis_runs(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    query = select(DocumentAnalysisRun).order_by(DocumentAnalysisRun.id.desc())
    count = session.scalar(select(func.count()).select_from(DocumentAnalysisRun)) or 0
    items = session.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [{"run_id": item.id, "document_ref": item.document_ref,
                       "pipeline_version": item.pipeline_version, "status": item.status,
                       "summary": json.loads(item.result_summary_json)}
                      for item in items],
            "page": page, "page_size": page_size, "total": count}


@app.get("/api/v1/analysis-runs/{run_id}", tags=["analysis"])
def analysis_run_detail(run_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    item = session.get(DocumentAnalysisRun, run_id)
    if item is None:
        raise HTTPException(404, {"code": "not_found", "message": "Analysis run was not found"})
    return {"run_id": item.id, "document_ref": item.document_ref,
            "pipeline_version": item.pipeline_version, "status": item.status,
            "summary": json.loads(item.result_summary_json)}


@app.get("/api/v1/companies", tags=["companies"])
def list_companies(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    q: str | None = Query(None, max_length=300),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    result = ApiRegistryService(session).companies(page, page_size, q)
    items = [{"company_id": item.id, "registry_id": item.external_id,
              "canonical_legal_name": item.canonical_legal_name, "is_active": item.is_active}
             for item in result["items"]]
    return {"items": items, **page_metadata(result)}


@app.get("/api/v1/companies/{company_id}", tags=["companies"])
def company_detail(company_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    company = ApiRegistryService(session).company(company_id)
    if company is None:
        raise HTTPException(404, {"code": "not_found", "message": "Company was not found"})
    security_items = [
        {
            "registry_id": security.external_id,
            "isin": security.isin,
            "isin_verified": security.isin_verified,
            "instrument_classification": security.instrument_classification,
        }
        for security in company.securities
        if security.issuer_company_id == company.id
    ]
    listing_items = [
        {
            "registry_id": listing.external_id,
            "exchange_code": listing.exchange_code,
            "symbol": listing.symbol,
            "series": listing.series,
            "listing_status": listing.listing_status,
            "valid_from": listing.valid_from,
            "valid_to": listing.valid_to,
        }
        for listing in company.listings
    ]
    return {
        "company_id": company.id,
        "registry_id": company.external_id,
        "canonical_legal_name": company.canonical_legal_name,
        "is_active": company.is_active,
        "securities": security_items,
        "listings": listing_items,
    }


@app.get("/api/v1/intelligence", tags=["intelligence"])
def list_intelligence(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    document_ref: str | None = Query(None, max_length=300),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    query = select(Stage4ARecord).order_by(Stage4ARecord.id.desc())
    if document_ref:
        query = query.where(Stage4ARecord.document_ref == document_ref)
    count_query = query.order_by(None).subquery()
    total = session.scalar(select(func.count()).select_from(count_query)) or 0
    items = session.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [{"record_id": item.record_id, "record_kind": item.record_kind,
                       "document_ref": item.document_ref, "payload": json.loads(item.payload_json)}
                      for item in items],
            "page": page, "page_size": page_size, "total": total}


@app.get("/api/v1/intelligence/{record_id}", tags=["intelligence"])
def intelligence_detail(record_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    item = session.scalar(select(Stage4ARecord).where(Stage4ARecord.record_id == record_id))
    if item is None:
        raise HTTPException(404, {"code": "not_found", "message": "Intelligence record was not found"})
    return {"record_id": item.record_id, "record_kind": item.record_kind,
            "document_ref": item.document_ref, "payload": json.loads(item.payload_json)}


@app.get("/api/v1/registry/summary", tags=["registry"])
def registry_summary(session: Session = Depends(get_session)) -> dict[str, Any]:
    return ApiRegistryService(session).summary()


@app.get("/api/v1/registry/snapshots", tags=["registry"])
def registry_snapshots(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    result = ApiRegistryService(session).snapshots(page, page_size)
    return {"items": [snapshot_payload(item) for item in result["items"]],
            **page_metadata(result)}


@app.get("/api/v1/registry/snapshots/{snapshot_id}", tags=["registry"])
def registry_snapshot_detail(snapshot_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    item = ApiRegistryService(session).snapshot(snapshot_id)
    if item is None:
        raise HTTPException(404, {"code": "not_found", "message": "Snapshot was not found"})
    counts = dict(session.execute(
        select(RegistryRowAudit.validation_outcome, func.count(RegistryRowAudit.id))
        .where(RegistryRowAudit.snapshot_id == snapshot_id)
        .group_by(RegistryRowAudit.validation_outcome)
    ).all())
    payload = snapshot_payload(item)
    payload["audit_counts"] = counts
    return payload


def snapshot_payload(item: RegistrySnapshot) -> dict[str, Any]:
    return {
        "snapshot_id": item.id,
        "registry_id": item.external_id,
        "dataset_scope": item.dataset_scope,
        "snapshot_state": item.snapshot_state,
        "published_at": item.published_at,
        "validation_counts": json.loads(item.validation_counts_json),
        "source_manifest": json.loads(item.source_manifest_json),
    }
