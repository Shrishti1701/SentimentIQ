"""Initial persistence schema for articles and aspect-level predictions."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.connection import Base
import registry.models  # noqa: F401 - register registry tables on the shared metadata


class FinancialArticle(Base):
    """A source article or official announcement."""

    __tablename__ = "financial_articles"
    __table_args__ = (UniqueConstraint("source_url", name="uq_article_source_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    predictions: Mapped[list["SentimentPrediction"]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )
    nse_metadata: Mapped["NSEAnnouncementMetadata | None"] = relationship(
        back_populates="article", cascade="all, delete-orphan", uselist=False
    )


class NSEAnnouncementMetadata(Base):
    """NSE RSS identity and timestamp details kept separate from article text."""

    __tablename__ = "nse_announcement_metadata"
    __table_args__ = (
        UniqueConstraint("article_id", name="uq_nse_metadata_article"),
        UniqueConstraint("source_item_key", name="uq_nse_source_item_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("financial_articles.id", ondelete="CASCADE"), nullable=False
    )
    source_item_key: Mapped[str] = mapped_column(String(100), nullable=False)
    identity_method: Mapped[str] = mapped_column(String(20), nullable=False)
    source_title: Mapped[str | None] = mapped_column(String(300))
    published_at_raw: Mapped[str | None] = mapped_column(String(100))
    published_at_unzoned: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    timezone_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unknown", server_default="unknown"
    )

    article: Mapped[FinancialArticle] = relationship(back_populates="nse_metadata")


class Company(Base):
    """A tracked company identified by a stable symbol or registry key."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    identifier: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    predictions: Mapped[list["SentimentPrediction"]] = relationship(back_populates="company")


class Aspect(Base):
    """A normalized financial aspect label, such as revenue or debt."""

    __tablename__ = "aspects"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    predictions: Mapped[list["SentimentPrediction"]] = relationship(back_populates="aspect")


class SentimentPrediction(Base):
    """An aspect-level sentiment result with evidence and model provenance."""

    __tablename__ = "sentiment_predictions"
    __table_args__ = (
        UniqueConstraint(
            "article_id", "company_id", "aspect_id", "model_version",
            name="uq_prediction_article_company_aspect_model",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("financial_articles.id"), nullable=False)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    aspect_id: Mapped[int] = mapped_column(ForeignKey("aspects.id"), nullable=False)
    sentiment_label: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    supporting_evidence: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(String(150), nullable=False)

    article: Mapped[FinancialArticle] = relationship(back_populates="predictions")
    company: Mapped[Company] = relationship(back_populates="predictions")
    aspect: Mapped[Aspect] = relationship(back_populates="predictions")


class Stage4ARecord(Base):
    """Immutable canonical Stage 4A output identified by deterministic record ID."""

    __tablename__ = "stage4a_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_ref: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    record_id: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)
    record_kind: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


class Stage4ASupersession(Base):
    __tablename__ = "stage4a_supersessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    supersession_id: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)
    predecessor_observation_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    successor_observation_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    document_ref: Mapped[str] = mapped_column(String(300), nullable=False)
    source_field: Mapped[str] = mapped_column(String(20), nullable=False)
    start: Mapped[int] = mapped_column(nullable=False)
    end: Mapped[int] = mapped_column(nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


class DocumentAnalysisRun(Base):
    """Caller-owned completion marker for article pipeline orchestration."""

    __tablename__ = "document_analysis_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_ref: Mapped[str] = mapped_column(String(300), nullable=False, unique=True, index=True)
    pipeline_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running", server_default="running")
    result_summary_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")
