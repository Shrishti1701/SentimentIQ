"""Production orchestration for persisted NSE announcement analysis."""

from __future__ import annotations

import logging
from dataclasses import dataclass
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import DocumentAnalysisRun, FinancialArticle
from database.stage4a_persistence import (
    Stage4APersistenceReport,
    persist_stage4a_result_with_supersessions_session,
)
from ingestion.article_adapter import article_to_analysis_input
from intelligence.contracts import verified_effective_time_from_input
from intelligence.entity_extractor import extract_entity_mentions
from intelligence.stage4a.runtime import Stage4APipeline, Stage4AResult
from registry.entity_resolver import ProductionRegistryResolver


PIPELINE_VERSION = "article-pipeline-v1"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DocumentAnalysisReport:
    document_ref: str
    result: Stage4AResult | None
    persistence: Stage4APersistenceReport
    duplicate: bool = False


class AnalysisInProgress(RuntimeError):
    pass


class DocumentAnalysisService:
    def __init__(
        self,
        session: Session,
        stage4a_pipeline: Stage4APipeline,
        *,
        extractor_version: str = "stage2-production-v1",
    ) -> None:
        self.session = session
        if not isinstance(stage4a_pipeline, Stage4APipeline):
            raise TypeError("stage4a_pipeline must be a Stage4APipeline")
        self.stage4a_pipeline = stage4a_pipeline
        self.extractor_version = extractor_version

    def process_article(
        self, article_id: int, *, allow_in_progress_claim: bool = False
    ) -> DocumentAnalysisReport:
        article = self.session.get(FinancialArticle, article_id)
        if article is None:
            raise LookupError(f"financial article not found: {article_id}")

        document = article_to_analysis_input(article)
        existing = self.session.scalar(
            select(DocumentAnalysisRun).where(
                DocumentAnalysisRun.document_ref == document.document_ref,
                DocumentAnalysisRun.pipeline_version == PIPELINE_VERSION,
            )
        )
        claimed_run: DocumentAnalysisRun | None = None
        if existing is not None:
            if existing.status == "running" and not allow_in_progress_claim:
                raise AnalysisInProgress(document.document_ref)
            if existing.status == "running":
                claimed_run = existing
            else:
                return DocumentAnalysisReport(
                    document.document_ref,
                    None,
                    Stage4APersistenceReport(0, 0),
                    duplicate=True,
                )

        try:
            logger.info("pipeline stage=stage1 document_ref=%s", document.document_ref)
            mentions = extract_entity_mentions(
                document, extractor_version=self.extractor_version
            )
            logger.info("pipeline stage=stage2 document_ref=%s", document.document_ref)

            effective_time = None
            if document.published_at is not None and document.timezone_status.startswith("verified_"):
                effective_time = verified_effective_time_from_input(document)

            resolver = ProductionRegistryResolver(self.session)
            resolutions = tuple(
                resolver.resolve(mention, effective_time=effective_time)
                for mention in mentions
            )
            logger.info("pipeline stage=stage3 document_ref=%s", document.document_ref)

            result = self.stage4a_pipeline.process(
                document,
                upstream_mentions=mentions,
                upstream_resolutions=resolutions,
            )
            logger.info("pipeline stage=stage4a document_ref=%s", document.document_ref)

            persistence = persist_stage4a_result_with_supersessions_session(
                result, self.session
            )
            unresolved = sum(item.status == "unresolved" for item in resolutions)
            ambiguous = sum(item.status == "ambiguous" for item in resolutions)
            summary = json.dumps({
                    "status": "completed_with_issues" if unresolved or ambiguous else "completed",
                    "unresolved_count": unresolved,
                    "ambiguous_count": ambiguous,
                    "mention_count": len(mentions),
                }, sort_keys=True)
            if claimed_run is not None:
                claimed_run.status = "completed"
                claimed_run.result_summary_json = summary
            else:
                self.session.add(DocumentAnalysisRun(
                    document_ref=document.document_ref,
                    pipeline_version=PIPELINE_VERSION,
                    status="completed",
                    result_summary_json=summary,
                ))
            return DocumentAnalysisReport(document.document_ref, result, persistence)
        except Exception:
            logger.exception("pipeline failed document_ref=%s", document.document_ref)
            raise
