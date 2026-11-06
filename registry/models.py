"""Authoritative registry models, separate from the legacy sentiment Company model."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates
from sqlalchemy.sql import func

from database.connection import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _valid_external_id(value: str, prefix: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
    if re.fullmatch(re.escape(prefix) + r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{field_name} must start with {prefix}")
    return value


class RegistryCompany(Base):
    __tablename__ = "registry_companies"
    __table_args__ = (
        CheckConstraint("length(canonical_legal_name) > 0", name="ck_registry_company_name"),
        CheckConstraint("is_active IN (true, false)", name="ck_registry_company_active"),
        CheckConstraint("external_id LIKE 'REGISTRY-COMPANY:v1:%'", name="ck_registry_company_external_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    canonical_legal_name: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    parent_company_id: Mapped[int | None] = mapped_column(
        ForeignKey("registry_companies.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow, server_default=func.now()
    )

    parent: Mapped["RegistryCompany | None"] = relationship(
        remote_side="RegistryCompany.id", foreign_keys=[parent_company_id], back_populates="subsidiaries"
    )
    subsidiaries: Mapped[list["RegistryCompany"]] = relationship(back_populates="parent")
    securities: Mapped[list["RegistrySecurity"]] = relationship(back_populates="issuer_company")
    listings: Mapped[list["RegistryExchangeListing"]] = relationship(back_populates="company")
    aliases: Mapped[list["CompanyAlias"]] = relationship(back_populates="company")

    @validates("external_id")
    def validate_external_id(self, key: str, value: str) -> str:
        return _valid_external_id(value, "REGISTRY-COMPANY:v1:", key)

    @validates("canonical_legal_name")
    def validate_name(self, key: str, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("canonical_legal_name must be non-empty")
        return value.strip()


class RegistrySecurity(Base):
    __tablename__ = "registry_securities"
    __table_args__ = (
        CheckConstraint("length(instrument_classification) > 0", name="ck_registry_security_class"),
        CheckConstraint("isin_verified IN (true, false)", name="ck_registry_security_isin_verified"),
        CheckConstraint(
            "(isin IS NULL AND isin_verified = false) OR (isin IS NOT NULL)",
            name="ck_registry_security_isin_state",
        ),
        CheckConstraint(
            "(isin IS NULL) OR (length(isin) = 12 AND isin = upper(isin))",
            name="ck_registry_security_isin_format",
        ),
        CheckConstraint("external_id LIKE 'REGISTRY-SECURITY:v1:%'", name="ck_registry_security_external_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    instrument_classification: Mapped[str] = mapped_column(String(100), nullable=False)
    isin: Mapped[str | None] = mapped_column(String(12), unique=True)
    isin_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    issuer_company_id: Mapped[int | None] = mapped_column(
        ForeignKey("registry_companies.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )

    issuer_company: Mapped[RegistryCompany | None] = relationship(back_populates="securities", foreign_keys=[issuer_company_id])
    listings: Mapped[list["RegistryExchangeListing"]] = relationship(back_populates="security")

    @validates("external_id")
    def validate_external_id(self, key: str, value: str) -> str:
        return _valid_external_id(value, "REGISTRY-SECURITY:v1:", key)

    @validates("isin")
    def validate_isin(self, key: str, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if len(value) != 12 or re.fullmatch(r"[A-Z0-9]{12}", value) is None:
            raise ValueError("ISIN must contain 12 uppercase letters or digits")
        return value


class RegistryExchangeListing(Base):
    __tablename__ = "registry_exchange_listings"
    __table_args__ = (
        CheckConstraint("length(exchange_code) > 0 AND length(symbol) > 0", name="ck_registry_listing_required"),
        CheckConstraint("(valid_to IS NULL) OR (valid_from IS NULL) OR (valid_to > valid_from)", name="ck_registry_listing_validity"),
        CheckConstraint("(security_id IS NOT NULL) OR (company_id IS NOT NULL)", name="ck_registry_listing_relationship"),
        UniqueConstraint("exchange_code", "symbol", "series", "valid_from", name="uq_registry_listing_period"),
        CheckConstraint("external_id LIKE 'REGISTRY-LISTING:v1:%'", name="ck_registry_listing_external_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    security_id: Mapped[int | None] = mapped_column(ForeignKey("registry_securities.id", ondelete="RESTRICT"))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("registry_companies.id", ondelete="RESTRICT"))
    exchange_code: Mapped[str] = mapped_column(String(20), nullable=False)
    symbol: Mapped[str] = mapped_column(String(100), nullable=False)
    series: Mapped[str | None] = mapped_column(String(20))
    listing_date: Mapped[date | None] = mapped_column(Date)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    listing_status: Mapped[str] = mapped_column(String(30), nullable=False, default="active", server_default="active")

    security: Mapped[RegistrySecurity | None] = relationship(back_populates="listings")
    company: Mapped[RegistryCompany | None] = relationship(back_populates="listings")
    symbol_history: Mapped[list["ListingSymbolHistory"]] = relationship(back_populates="listing")

    @validates("external_id")
    def validate_external_id(self, key: str, value: str) -> str:
        return _valid_external_id(value, "REGISTRY-LISTING:v1:", key)


class RegistrySnapshot(Base):
    __tablename__ = "registry_snapshots"
    __table_args__ = (
        CheckConstraint("snapshot_state IN ('building', 'validated', 'published', 'superseded')", name="ck_registry_snapshot_state"),
        CheckConstraint(
            "(snapshot_state != 'published') OR published_at IS NOT NULL",
            name="ck_registry_snapshot_publication",
        ),
        CheckConstraint("external_id LIKE 'REGISTRY-SNAPSHOT:v1:%'", name="ck_registry_snapshot_external_id"),
        CheckConstraint(
            "dataset_scope IN ('NSE_CURRENT_LISTINGS', 'NSE_HISTORICAL_CHANGES')",
            name="ck_registry_snapshot_dataset_scope",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    dataset_scope: Mapped[str] = mapped_column(
        String(40), nullable=False, default="NSE_CURRENT_LISTINGS", server_default="NSE_CURRENT_LISTINGS"
    )
    snapshot_state: Mapped[str] = mapped_column(String(30), nullable=False, default="building", server_default="building")
    source_manifest_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    validation_counts_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sources: Mapped[list["RegistrySource"]] = relationship(back_populates="snapshot")
    audit_rows: Mapped[list["RegistryRowAudit"]] = relationship(back_populates="snapshot")

    @validates("external_id")
    def validate_external_id(self, key: str, value: str) -> str:
        return _valid_external_id(value, "REGISTRY-SNAPSHOT:v1:", key)


class RegistrySource(Base):
    __tablename__ = "registry_sources"
    __table_args__ = (
        CheckConstraint("length(original_filename) > 0 AND length(file_format) > 0", name="ck_registry_source_required"),
        CheckConstraint(
            "length(sha256_checksum) = 64 AND sha256_checksum = lower(sha256_checksum) "
            "AND sha256_checksum = lower(sha256_checksum)",
            name="ck_registry_source_checksum",
        ),
        CheckConstraint("external_id LIKE 'REGISTRY-SOURCE:v1:%'", name="ck_registry_source_external_id"),
        UniqueConstraint("original_filename", "sha256_checksum", "retrieval_date", name="uq_registry_source_content"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("registry_snapshots.id", ondelete="RESTRICT"))
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    retrieval_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_update_date: Mapped[date | None] = mapped_column(Date)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    file_format: Mapped[str] = mapped_column(String(20), nullable=False)
    usage_permission_status: Mapped[str] = mapped_column(String(50), nullable=False, default="unreviewed", server_default="unreviewed")
    import_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now())

    snapshot: Mapped[RegistrySnapshot | None] = relationship(back_populates="sources")
    aliases: Mapped[list["CompanyAlias"]] = relationship(back_populates="source")
    symbol_history: Mapped[list["ListingSymbolHistory"]] = relationship(back_populates="source")
    audit_rows: Mapped[list["RegistryRowAudit"]] = relationship(back_populates="source")

    @validates("external_id")
    def validate_external_id(self, key: str, value: str) -> str:
        return _valid_external_id(value, "REGISTRY-SOURCE:v1:", key)

    @validates("sha256_checksum")
    def validate_checksum(self, key: str, value: str) -> str:
        if value != value.lower():
            raise ValueError("sha256_checksum must be lowercase hexadecimal")
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("sha256_checksum must contain 64 hexadecimal characters")
        return value


class CompanyAlias(Base):
    __tablename__ = "registry_company_aliases"
    __table_args__ = (
        CheckConstraint("length(original_alias) > 0 AND length(normalized_alias_key) > 0", name="ck_registry_alias_required"),
        CheckConstraint("(valid_to IS NULL) OR (valid_from IS NULL) OR (valid_to > valid_from)", name="ck_registry_alias_validity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("registry_companies.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("registry_sources.id", ondelete="RESTRICT"), nullable=False)
    original_alias: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_alias_key: Mapped[str] = mapped_column(String(500), nullable=False)
    alias_type: Mapped[str] = mapped_column(String(50), nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    source_row_number: Mapped[int | None] = mapped_column(Integer)
    company: Mapped[RegistryCompany] = relationship(
        "registry.models.RegistryCompany", foreign_keys=[company_id], back_populates="aliases"
    )
    source: Mapped[RegistrySource] = relationship(back_populates="aliases")

    @validates("source_row_number")
    def validate_source_row(self, key: str, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("source_row_number must be positive")
        return value


class ListingSymbolHistory(Base):
    __tablename__ = "registry_listing_symbol_history"
    __table_args__ = (
        CheckConstraint("length(previous_symbol) > 0 AND length(new_symbol) > 0", name="ck_registry_symbol_history_required"),
        CheckConstraint("previous_symbol <> new_symbol", name="ck_registry_symbol_history_changed"),
        CheckConstraint("review_status IN ('accepted', 'requires_review', 'rejected')", name="ck_registry_symbol_review_status"),
        UniqueConstraint("listing_id", "previous_symbol", "new_symbol", "effective_date", name="uq_registry_symbol_transition"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int | None] = mapped_column(ForeignKey("registry_exchange_listings.id", ondelete="RESTRICT"))
    source_id: Mapped[int] = mapped_column(ForeignKey("registry_sources.id", ondelete="RESTRICT"), nullable=False)
    previous_symbol: Mapped[str] = mapped_column(String(100), nullable=False)
    new_symbol: Mapped[str] = mapped_column(String(100), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="accepted", server_default="accepted")
    source_row_number: Mapped[int | None] = mapped_column(Integer)

    listing: Mapped[RegistryExchangeListing | None] = relationship(
        "registry.models.RegistryExchangeListing",
        foreign_keys=[listing_id],
        back_populates="symbol_history",
    )
    source: Mapped[RegistrySource] = relationship(back_populates="symbol_history")

    @validates("source_row_number")
    def validate_source_row(self, key: str, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("source_row_number must be positive")
        return value


class RegistryRowAudit(Base):
    __tablename__ = "registry_row_audit"
    __table_args__ = (
        CheckConstraint("source_row_number > 0", name="ck_registry_audit_row_positive"),
        CheckConstraint(
            "validation_outcome IN ('accepted', 'rejected', 'quarantined', 'duplicate', 'requires_review')",
            name="ck_registry_audit_outcome",
        ),
        UniqueConstraint("snapshot_id", "source_id", "source_row_number", name="uq_registry_audit_source_row"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("registry_snapshots.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("registry_sources.id", ondelete="RESTRICT"), nullable=False)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_row_json: Mapped[str] = mapped_column(Text, nullable=False)
    validation_outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    normalized_values_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now())

    snapshot: Mapped[RegistrySnapshot] = relationship(back_populates="audit_rows")
    source: Mapped[RegistrySource] = relationship(back_populates="audit_rows")


Index("ix_registry_companies_parent", RegistryCompany.parent_company_id)
Index("ix_registry_securities_issuer", RegistrySecurity.issuer_company_id)
Index("ix_registry_listings_security", RegistryExchangeListing.security_id)
Index("ix_registry_listings_company", RegistryExchangeListing.company_id)
Index("ix_registry_listings_symbol_valid", RegistryExchangeListing.exchange_code, RegistryExchangeListing.symbol, RegistryExchangeListing.valid_from, RegistryExchangeListing.valid_to)
Index("ix_registry_aliases_company_normalized", CompanyAlias.company_id, CompanyAlias.normalized_alias_key)
Index("ix_registry_aliases_validity", CompanyAlias.valid_from, CompanyAlias.valid_to)
Index("ix_registry_symbol_history_listing_date", ListingSymbolHistory.listing_id, ListingSymbolHistory.effective_date)
Index("ix_registry_sources_snapshot", RegistrySource.snapshot_id)
Index("ix_registry_sources_checksum", RegistrySource.sha256_checksum)
Index("ix_registry_audit_outcome", RegistryRowAudit.validation_outcome)
Index(
    "uq_registry_one_published_snapshot_per_scope",
    RegistrySnapshot.dataset_scope,
    unique=True,
    sqlite_where=text("snapshot_state = 'published'"),
    postgresql_where=text("snapshot_state = 'published'"),
)


# Public entity names remain concise while mapper class names remain collision-safe
# with the pre-existing sentiment persistence Company.
Company = RegistryCompany
Security = RegistrySecurity
ExchangeListing = RegistryExchangeListing
