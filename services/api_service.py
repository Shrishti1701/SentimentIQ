"""Read/query services used by the production HTTP API."""

from __future__ import annotations

from datetime import date
from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from database.models import DocumentAnalysisRun, FinancialArticle, NSEAnnouncementMetadata, Stage4ARecord
from registry.models import RegistryCompany, RegistryRowAudit, RegistrySnapshot


def _page(page: int, page_size: int) -> tuple[int, int]:
    if page < 1:
        raise ValueError("page must be at least 1")
    if page_size < 1 or page_size > 100:
        raise ValueError("page_size must be between 1 and 100")
    return page, page_size


def paginate(query, session: Session, page: int, page_size: int):
    page, page_size = _page(page, page_size)
    count_query = query.order_by(None).subquery()
    total = session.scalar(select(func.count()).select_from(count_query)) or 0
    items = session.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": items, "page": page, "page_size": page_size, "total": total}


class ApiRegistryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def companies(self, page: int, page_size: int, q: str | None = None):
        query = select(RegistryCompany).order_by(RegistryCompany.canonical_legal_name, RegistryCompany.id)
        if q:
            query = query.where(RegistryCompany.canonical_legal_name.contains(q.strip()))
        return paginate(query, self.session, page, page_size)

    def company(self, company_id: int) -> RegistryCompany | None:
        return self.session.get(RegistryCompany, company_id)

    def snapshots(self, page: int, page_size: int):
        query = select(RegistrySnapshot).order_by(RegistrySnapshot.id.desc())
        return paginate(query, self.session, page, page_size)

    def snapshot(self, snapshot_id: int) -> RegistrySnapshot | None:
        return self.session.get(RegistrySnapshot, snapshot_id)

    def summary(self) -> dict[str, object]:
        scopes = self.session.scalars(
            select(RegistrySnapshot.dataset_scope, RegistrySnapshot.snapshot_state).distinct()
        ).all()
        snapshots = self.session.scalars(select(RegistrySnapshot)).all()
        return {
            "company_count": self.session.scalar(select(func.count()).select_from(RegistryCompany)) or 0,
            "snapshot_count": len(snapshots),
            "published_snapshot_count": sum(item.snapshot_state == "published" for item in snapshots),
            "dataset_scopes": sorted({item.dataset_scope for item in snapshots}),
        }


class ApiAnnouncementService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(
        self,
        page: int,
        page_size: int,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        company: str | None = None,
    ):
        query = (
            select(FinancialArticle)
            .join(NSEAnnouncementMetadata, NSEAnnouncementMetadata.article_id == FinancialArticle.id, isouter=True)
            .options(selectinload(FinancialArticle.nse_metadata))
            .order_by(FinancialArticle.id.desc())
        )
        if from_date is not None:
            query = query.where(FinancialArticle.collected_at >= from_date)
        if to_date is not None:
            query = query.where(FinancialArticle.collected_at < to_date)
        if company:
            query = query.where(
                or_(NSEAnnouncementMetadata.source_title.contains(company.strip()),
                    FinancialArticle.source_url.contains(company.strip()))
            )
        return paginate(query, self.session, page, page_size)

    def get(self, announcement_id: int) -> FinancialArticle | None:
        return self.session.scalar(
            select(FinancialArticle)
            .where(FinancialArticle.id == announcement_id)
            .options(selectinload(FinancialArticle.nse_metadata))
        )
