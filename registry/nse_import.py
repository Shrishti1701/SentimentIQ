"""NSE equity and SME registry source import."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from registry.identity import registry_id
from registry.models import (
    CompanyAlias,
    ExchangeListing,
    ListingSymbolHistory,
    RegistryCompany,
    RegistryRowAudit,
    RegistrySnapshot,
    RegistrySource,
    Security,
)


NSE_SOURCE_URL = "https://www.nseindia.com/static/market-data/securities-available-for-trading"
RETRIEVAL_DATE = date(2026, 11, 4)


@dataclass(frozen=True)
class ImportReport:
    source_files: tuple[str, ...]
    source_checksums: dict[str, str]
    equity_rows: int
    sme_rows: int
    accepted_rows: int
    duplicate_rows: int
    rejected_rows: int
    quarantined_rows: int
    unresolved_issuer_identities: int
    unique_verified_securities: int
    unique_listings: int
    overlap_details: tuple[dict[str, str], ...]
    snapshot_id: int | None
    snapshot_external_id: str
    snapshot_state: str

    def as_dict(self) -> dict[str, object]:
        return {
            "source_files": list(self.source_files),
            "source_checksums": self.source_checksums,
            "total_equity_rows": self.equity_rows,
            "total_sme_rows": self.sme_rows,
            "accepted_rows": self.accepted_rows,
            "duplicate_rows": self.duplicate_rows,
            "rejected_rows": self.rejected_rows,
            "quarantined_rows": self.quarantined_rows,
            "unresolved_issuer_identities": self.unresolved_issuer_identities,
            "unique_verified_securities": self.unique_verified_securities,
            "unique_listings": self.unique_listings,
            "equity_sme_overlap_details": list(self.overlap_details),
            "snapshot_id": self.snapshot_id,
            "snapshot_external_id": self.snapshot_external_id,
            "snapshot_state": self.snapshot_state,
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_header(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", (value or "").strip().upper()).strip("_")


def read_nse_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None:
            raise ValueError(f"{path.name} has no CSV header")
        field_map = {_normalized_header(name): name for name in reader.fieldnames}
        rows: list[dict[str, str]] = []
        for csv_row in reader:
            rows.append({_normalized_header(key): str(value or "").strip() for key, value in csv_row.items() if key is not None})
        return rows


def parse_nse_date(value: str) -> date | None:
    for date_format in ("%d-%b-%Y", "%d-%b-%y", "%d-%m-%Y", "%d-%b-%Y"):
        try:
            from datetime import datetime

            return datetime.strptime(value.strip(), date_format).date()
        except ValueError:
            continue
    return None


def _structural_isin(value: str) -> bool:
    return re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", value or "") is not None


def _required(row: dict[str, str], names: Iterable[str]) -> tuple[bool, list[str]]:
    missing = [name for name in names if not row.get(name)]
    return not missing, missing


class NSERegistryImporter:
    def __init__(self, session: Session, raw_directory: Path) -> None:
        self.session = session
        self.raw_directory = raw_directory

    def import_current_listings(self, publish: bool = True) -> ImportReport:
        equity_path = self.raw_directory / "EQUITY_L.csv"
        sme_path = self.raw_directory / "SME_EQUITY_L.csv"
        paths = (equity_path, sme_path)
        for path in paths:
            if not path.is_file():
                raise FileNotFoundError(path)

        checksums = {path.name: sha256_file(path) for path in paths}
        manifest = [{"filename": name, "sha256": checksum} for name, checksum in sorted(checksums.items())]
        external_id = registry_id(
            "SNAPSHOT",
            {"retrieval_date": RETRIEVAL_DATE.isoformat(), "scope": "NSE_CURRENT_LISTINGS", "sources": manifest},
        )

        try:
            snapshot = self.session.scalar(select(RegistrySnapshot).where(RegistrySnapshot.external_id == external_id))
            if snapshot is not None:
                return self._existing_report(snapshot, checksums, external_id)

            snapshot = RegistrySnapshot(
                external_id=external_id,
                dataset_scope="NSE_CURRENT_LISTINGS",
                snapshot_state="building",
                source_manifest_json=json.dumps(manifest, sort_keys=True),
                validation_counts_json="{}",
            )
            self.session.add(snapshot)
            self.session.flush()

            sources: dict[str, RegistrySource] = {}
            for path in paths:
                existing_source = self.session.scalar(
                    select(RegistrySource).where(
                        RegistrySource.original_filename == path.name,
                        RegistrySource.sha256_checksum == checksums[path.name],
                        RegistrySource.retrieval_date == RETRIEVAL_DATE,
                    )
                )
                if existing_source is not None:
                    sources[path.name] = existing_source
                    continue
                source = RegistrySource(
                    external_id=registry_id(
                        "SOURCE",
                        {
                            "filename": path.name,
                            "checksum": checksums[path.name],
                            "retrieval_date": RETRIEVAL_DATE.isoformat(),
                            "snapshot": snapshot.external_id,
                        },
                    ),
                    snapshot=snapshot,
                    original_filename=path.name,
                    source_url=NSE_SOURCE_URL,
                    retrieval_date=RETRIEVAL_DATE,
                    sha256_checksum=checksums[path.name],
                    file_format="csv",
                    usage_permission_status="public_nse_market_data",
                )
                self.session.add(source)
                sources[path.name] = source
            self.session.flush()

            equity_rows = read_nse_csv(equity_path)
            sme_rows = read_nse_csv(sme_path)
            accepted, duplicate, rejected, quarantined = self._import_rows(snapshot, sources, equity_rows, "equity")
            accepted2, duplicate2, rejected2, quarantined2 = self._import_rows(snapshot, sources, sme_rows, "sme")
            accepted += accepted2
            duplicate += duplicate2
            rejected += rejected2
            quarantined += quarantined2

            snapshot.validation_counts_json = json.dumps({
                "accepted": accepted,
                "duplicate": duplicate,
                "rejected": rejected,
                "quarantined": quarantined,
            }, sort_keys=True)

            if rejected or quarantined:
                snapshot.snapshot_state = "validated"
                # Publication is intentionally withheld when the source has unresolved rows.
            else:
                snapshot.snapshot_state = "validated"
                if publish:
                    published = self.session.scalars(
                        select(RegistrySnapshot).where(
                            RegistrySnapshot.snapshot_state == "published",
                            RegistrySnapshot.dataset_scope == "NSE_CURRENT_LISTINGS",
                        )
                    ).all()
                    for old in published:
                        old.snapshot_state = "superseded"
                    snapshot.published_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                    snapshot.snapshot_state = "published"

            self.session.flush()
            self.session.commit()
            return self._build_report(snapshot, checksums, equity_rows, sme_rows)
        except Exception:
            self.session.rollback()
            raise

    def _import_rows(
        self,
        snapshot: RegistrySnapshot,
        sources: dict[str, RegistrySource],
        rows: list[dict[str, str]],
        segment: str,
    ) -> tuple[int, int, int, int]:
        source = sources["EQUITY_L.csv" if segment == "equity" else "SME_EQUITY_L.csv"]
        counts = {"accepted": 0, "duplicate": 0, "rejected": 0, "quarantined": 0}
        for row_number, row in enumerate(rows, start=2):
            symbol = row.get("SYMBOL", "")
            company_name = row.get("NAME_OF_COMPANY", "")
            series = row.get("SERIES", "")
            listing_date = parse_nse_date(row.get("DATE_OF_LISTING", ""))
            isin = row.get("ISIN_NUMBER", "").upper()
            required_ok, missing = _required(
                row, ("SYMBOL", "NAME_OF_COMPANY", "SERIES", "DATE_OF_LISTING", "ISIN_NUMBER")
            )
            outcome = "accepted"
            reason = None
            normalized = {
                "symbol": symbol,
                "company_name": company_name,
                "series": series,
                "listing_date": listing_date.isoformat() if listing_date else None,
                "isin": isin,
                "segment": segment,
            }

            if not required_ok:
                outcome = "rejected"
                reason = "missing required fields: " + ", ".join(missing)
            elif listing_date is None:
                outcome = "quarantined"
                reason = "unrecognized listing date format"
            elif not _structural_isin(isin):
                outcome = "quarantined"
                reason = "invalid ISIN structure"
            else:
                outcome = self._persist_listing(snapshot, source, row, normalized, segment)
                if outcome == "duplicate":
                    reason = "same symbol, security, series, and listing date already exists in snapshot"
                elif outcome == "accepted":
                    reason = f"NSE {segment.upper()} listing reconciled by verified ISIN and exchange listing"

            counts[outcome] += 1
            audit = RegistryRowAudit(
                snapshot=snapshot,
                source=source,
                source_row_number=row_number,
                raw_row_json=json.dumps(row, ensure_ascii=False, sort_keys=True),
                validation_outcome=outcome,
                reason=reason,
                normalized_values_json=json.dumps(normalized, ensure_ascii=False, sort_keys=True),
            )
            self.session.add(audit)
        return counts["accepted"], counts["duplicate"], counts["rejected"], counts["quarantined"]

    def _persist_listing(
        self,
        snapshot: RegistrySnapshot,
        source: RegistrySource,
        row: dict[str, str],
        normalized: dict[str, object],
        segment: str,
    ) -> str:
        symbol = str(normalized["symbol"])
        series = str(normalized["series"])
        isin = str(normalized["isin"])
        listing_date = date.fromisoformat(str(normalized["listing_date"]))
        name_key = re.sub(r"\s+", " ", str(normalized["company_name"])).strip().upper()
        company_external_id = registry_id("COMPANY", {"name_key": name_key, "source": "NSE_CURRENT_LISTINGS"})
        company = self.session.scalar(select(RegistryCompany).where(RegistryCompany.external_id == company_external_id))
        if company is None:
            company = RegistryCompany(
                external_id=company_external_id,
                canonical_legal_name=str(normalized["company_name"]),
            )
            self.session.add(company)
            self.session.flush()

        security = self.session.scalar(select(Security).where(Security.isin == isin))
        if security is None:
            security = Security(
                external_id=registry_id("SECURITY", {"isin": isin, "source": "NSE_CURRENT_LISTINGS"}),
                instrument_classification="equity_sme" if segment == "sme" else "equity",
                isin=isin,
                isin_verified=True,
                issuer_company=None,
            )
            self.session.add(security)
            self.session.flush()

        listing_external_id = registry_id(
            "LISTING",
            {"exchange": "NSE", "security_isin": isin, "symbol": symbol, "series": series, "valid_from": listing_date.isoformat()},
        )
        existing = self.session.scalar(select(ExchangeListing).where(ExchangeListing.external_id == listing_external_id))
        if existing is not None:
            return "duplicate"

        listing = ExchangeListing(
            external_id=listing_external_id,
            security=security,
            company=company,
            exchange_code="NSE",
            symbol=symbol,
            series=series,
            listing_date=listing_date,
            valid_from=listing_date,
            listing_status="active",
        )
        self.session.add(listing)
        self.session.flush()
        return "accepted"

    def _existing_report(self, snapshot: RegistrySnapshot, checksums: dict[str, str], external_id: str) -> ImportReport:
        equity_rows = read_nse_csv(self.raw_directory / "EQUITY_L.csv")
        sme_rows = read_nse_csv(self.raw_directory / "SME_EQUITY_L.csv")
        return self._build_report(snapshot, checksums, equity_rows, sme_rows)

    def _build_report(
        self,
        snapshot: RegistrySnapshot,
        checksums: dict[str, str],
        equity_rows: list[dict[str, str]],
        sme_rows: list[dict[str, str]],
    ) -> ImportReport:
        counts = json.loads(snapshot.validation_counts_json)
        overlaps = []
        equity_by_symbol = {row.get("SYMBOL", ""): row for row in equity_rows}
        for row in sme_rows:
            symbol = row.get("SYMBOL", "")
            equity = equity_by_symbol.get(symbol)
            if equity and equity.get("ISIN_NUMBER", "").upper() == row.get("ISIN_NUMBER", "").upper():
                overlaps.append({
                    "symbol": symbol,
                    "isin": row.get("ISIN_NUMBER", ""),
                    "equity_series": equity.get("SERIES", ""),
                    "sme_series": row.get("SERIES", ""),
                })
        securities = self.session.scalars(select(Security).where(Security.isin.is_not(None))).unique().all()
        listings = self.session.scalars(select(ExchangeListing)).unique().all()
        unresolved = sum(1 for security in securities if security.issuer_company_id is None)
        return ImportReport(
            source_files=tuple(sorted(checksums)),
            source_checksums=checksums,
            equity_rows=len(equity_rows),
            sme_rows=len(sme_rows),
            accepted_rows=int(counts.get("accepted", 0)),
            duplicate_rows=int(counts.get("duplicate", 0)),
            rejected_rows=int(counts.get("rejected", 0)),
            quarantined_rows=int(counts.get("quarantined", 0)),
            unresolved_issuer_identities=unresolved,
            unique_verified_securities=len(securities),
            unique_listings=len(listings),
            overlap_details=tuple(overlaps),
            snapshot_id=snapshot.id,
            snapshot_external_id=snapshot.external_id,
            snapshot_state=snapshot.snapshot_state,
        )

    def import_historical_changes(self, publish: bool = False) -> dict[str, object]:
        name_path = self.raw_directory / "namechange.csv"
        symbol_path = self.raw_directory / "symbolchange.csv"
        for path in (name_path, symbol_path):
            if not path.is_file():
                raise FileNotFoundError(path)

        checksums = {path.name: sha256_file(path) for path in (name_path, symbol_path)}
        manifest = [{"filename": name, "sha256": checksum} for name, checksum in sorted(checksums.items())]
        snapshot_id = registry_id(
            "SNAPSHOT",
            {
                "retrieval_date": RETRIEVAL_DATE.isoformat(),
                "scope": "NSE_HISTORICAL_CHANGES",
                "sources": manifest,
            },
        )
        try:
            snapshot = self.session.scalar(select(RegistrySnapshot).where(RegistrySnapshot.external_id == snapshot_id))
            if snapshot is not None:
                return self._historical_report(snapshot, checksums)

            snapshot = RegistrySnapshot(
                external_id=snapshot_id,
                dataset_scope="NSE_HISTORICAL_CHANGES",
                snapshot_state="building",
                source_manifest_json=json.dumps(manifest, sort_keys=True),
                validation_counts_json="{}",
            )
            self.session.add(snapshot)
            self.session.flush()
            sources: dict[str, RegistrySource] = {}
            for path in (name_path, symbol_path):
                source = self._historical_source(snapshot, path, checksums[path.name])
                self.session.add(source)
                sources[path.name] = source
            self.session.flush()

            counts = {"accepted": 0, "duplicate": 0, "rejected": 0, "quarantined": 0, "requires_review": 0}
            name_counts = self._import_name_changes(snapshot, sources["namechange.csv"])
            symbol_counts = self._import_symbol_changes(snapshot, sources["symbolchange.csv"])
            for key in counts:
                counts[key] += name_counts[key] + symbol_counts[key]
            snapshot.validation_counts_json = json.dumps(counts, sort_keys=True)
            snapshot.snapshot_state = "validated"
            if publish:
                unresolved = counts["rejected"] + counts["quarantined"] + counts["requires_review"]
                if unresolved:
                    raise ValueError("historical snapshot contains unresolved audit rows")
                published = self.session.scalars(
                    select(RegistrySnapshot).where(
                        RegistrySnapshot.snapshot_state == "published",
                        RegistrySnapshot.dataset_scope == "NSE_HISTORICAL_CHANGES",
                        RegistrySnapshot.id != snapshot.id,
                    )
                ).all()
                for old in published:
                    old.snapshot_state = "superseded"
                snapshot.published_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                snapshot.snapshot_state = "published"
            self.session.commit()
            return self._historical_report(snapshot, checksums)
        except Exception:
            self.session.rollback()
            raise

    def _historical_source(
        self,
        snapshot: RegistrySnapshot,
        path: Path,
        checksum: str,
    ) -> RegistrySource:
        existing = self.session.scalar(
            select(RegistrySource).where(
                RegistrySource.original_filename == path.name,
                RegistrySource.sha256_checksum == checksum,
                RegistrySource.retrieval_date == RETRIEVAL_DATE,
            )
        )
        if existing is not None:
            return existing
        return RegistrySource(
            external_id=registry_id(
                "SOURCE",
                {
                    "filename": path.name,
                    "checksum": checksum,
                    "retrieval_date": RETRIEVAL_DATE.isoformat(),
                    "snapshot": snapshot.external_id,
                },
            ),
            snapshot=snapshot,
            original_filename=path.name,
            source_url=NSE_SOURCE_URL,
            retrieval_date=RETRIEVAL_DATE,
            sha256_checksum=checksum,
            file_format="csv",
            usage_permission_status="public_nse_market_data",
        )

    def _import_name_changes(self, snapshot: RegistrySnapshot, source: RegistrySource) -> dict[str, int]:
        counts = {"accepted": 0, "duplicate": 0, "rejected": 0, "quarantined": 0, "requires_review": 0}
        rows = read_nse_csv(self.raw_directory / "namechange.csv")
        seen: dict[tuple[str, str, str, str], int] = {}
        for row_number, row in enumerate(rows, start=2):
            symbol = row.get("SYMBOL", "")
            old_name = row.get("OLD_NAME_OF_THE_COMPANY", "")
            new_name = row.get("NEW_NAME_OF_THE_COMPANY", "")
            effective = parse_nse_date(row.get("EFFECTIVE_DATE", ""))
            key = (symbol, old_name.upper(), new_name.upper(), row.get("EFFECTIVE_DATE", ""))
            outcome = "accepted"
            reason = "verified by a current NSE listing symbol"
            if not all((symbol, old_name, new_name, effective)):
                outcome = "rejected" if not symbol or not old_name or not new_name else "quarantined"
                reason = "missing required historical name fields" if not all((symbol, old_name, new_name)) else "invalid effective date"
            elif key in seen:
                outcome = "duplicate"
                reason = f"duplicate transition; first appeared on source row {seen[key]}"
            else:
                seen[key] = row_number
                listings = self.session.scalars(
                    select(ExchangeListing).where(
                        ExchangeListing.exchange_code == "NSE",
                        ExchangeListing.symbol == symbol.upper(),
                    )
                ).all()
                if len(listings) != 1:
                    outcome = "quarantined"
                    reason = "company identity unresolved: current NSE symbol does not identify exactly one verified listing"
                else:
                    company = listings[0].company
                    if company is None:
                        outcome = "quarantined"
                        reason = "company identity unresolved"
                    else:
                        current_name = company.canonical_legal_name.strip().upper()
                        if current_name not in {old_name.upper(), new_name.upper()}:
                            outcome = "requires_review"
                            reason = "historical name transition does not match the verified current listing name"
                        else:
                            alias_key = re.sub(r"\s+", " ", old_name).strip().upper()
                            existing = self.session.scalar(
                                select(CompanyAlias).where(
                                    CompanyAlias.company_id == company.id,
                                    CompanyAlias.normalized_alias_key == alias_key,
                                    CompanyAlias.valid_from == effective,
                                )
                            )
                            if existing is None:
                                self.session.add(CompanyAlias(
                                    company=company,
                                    source=source,
                                    original_alias=old_name,
                                    normalized_alias_key=alias_key,
                                    alias_type="historical_name",
                                    valid_from=effective,
                                    source_row_number=row_number,
                                ))

            counts[outcome] += 1
            normalized = {
                "symbol": symbol,
                "old_name": old_name,
                "new_name": new_name,
                "effective_date": effective.isoformat() if effective else None,
            }
            self.session.add(RegistryRowAudit(
                snapshot=snapshot,
                source=source,
                source_row_number=row_number,
                raw_row_json=json.dumps(row, ensure_ascii=False, sort_keys=True),
                validation_outcome=outcome,
                reason=reason,
                normalized_values_json=json.dumps(normalized, ensure_ascii=False, sort_keys=True),
            ))
        return counts

    def _import_symbol_changes(self, snapshot: RegistrySnapshot, source: RegistrySource) -> dict[str, int]:
        counts = {"accepted": 0, "duplicate": 0, "rejected": 0, "quarantined": 0, "requires_review": 0}
        rows = read_nse_csv(self.raw_directory / "symbolchange.csv")
        seen: dict[tuple[str, str, str], str] = {}
        for row_number, row in enumerate(rows, start=2):
            company_name = row.get("NAME_OF_THE_COMPANY", "")
            previous = row.get("OLD_SYMBOL", "").upper()
            new = row.get("NEW_SYMBOL", "").upper()
            effective = parse_nse_date(row.get("EFFECTIVE_DATE", ""))
            key = (previous, new, row.get("EFFECTIVE_DATE", ""))
            outcome = "accepted"
            reason = "historical symbol transition preserved"
            if not all((company_name, previous, new, effective)):
                outcome = "rejected" if not company_name or not previous or not new else "quarantined"
                reason = "missing required symbol-transition fields" if not all((company_name, previous, new)) else "invalid effective date"
            elif previous == new:
                outcome = "quarantined"
                reason = "same-symbol transition is invalid"
            elif key in seen:
                if seen[key] != company_name:
                    outcome = "requires_review"
                    reason = "same transition conflicts with a different company name"
                else:
                    outcome = "duplicate"
                    reason = "duplicate symbol transition"
            else:
                seen[key] = company_name
                listing_matches = self.session.scalars(
                    select(ExchangeListing).where(
                        ExchangeListing.exchange_code == "NSE",
                        ExchangeListing.symbol.in_((previous, new)),
                    )
                ).all()
                listing = listing_matches[0] if len(listing_matches) == 1 else None
                if listing is None:
                    reason = "unresolved listing relationship; non-equity or historical symbol preserved"
                existing = self.session.scalar(
                    select(ListingSymbolHistory).where(
                        ListingSymbolHistory.listing_id == (listing.id if listing else None),
                        ListingSymbolHistory.previous_symbol == previous,
                        ListingSymbolHistory.new_symbol == new,
                        ListingSymbolHistory.effective_date == effective,
                    )
                )
                if existing is None:
                    self.session.add(ListingSymbolHistory(
                        listing=listing,
                        source=source,
                        previous_symbol=previous,
                        new_symbol=new,
                        effective_date=effective,
                        review_status="accepted" if listing else "requires_review",
                        source_row_number=row_number,
                    ))
                else:
                    outcome = "duplicate"
                    reason = "duplicate symbol transition"

            counts[outcome] += 1
            normalized = {
                "company_name": company_name,
                "previous_symbol": previous,
                "new_symbol": new,
                "effective_date": effective.isoformat() if effective else None,
            }
            self.session.add(RegistryRowAudit(
                snapshot=snapshot,
                source=source,
                source_row_number=row_number,
                raw_row_json=json.dumps(row, ensure_ascii=False, sort_keys=True),
                validation_outcome=outcome,
                reason=reason,
                normalized_values_json=json.dumps(normalized, ensure_ascii=False, sort_keys=True),
            ))
        return counts

    def _historical_report(self, snapshot: RegistrySnapshot, checksums: dict[str, str]) -> dict[str, object]:
        counts = json.loads(snapshot.validation_counts_json)
        return {
            "source_files": sorted(checksums),
            "source_checksums": checksums,
            "snapshot_id": snapshot.id,
            "snapshot_external_id": snapshot.external_id,
            "snapshot_state": snapshot.snapshot_state,
            "accepted": counts.get("accepted", 0),
            "duplicates": counts.get("duplicate", 0),
            "rejected": counts.get("rejected", 0),
            "quarantined": counts.get("quarantined", 0),
            "requires_review": counts.get("requires_review", 0),
        }
