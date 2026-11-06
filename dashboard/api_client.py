"""Small HTTP client for dashboard integration with the FastAPI service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests


DEFAULT_API_URL = "http://127.0.0.1:8000"
REQUEST_TIMEOUT_SECONDS = 3


@dataclass(frozen=True, slots=True)
class ApiResult:
    available: bool
    data: dict[str, Any] | None = None
    detail: str | None = None


def api_base_url() -> str:
    return os.getenv("SENTIMENTIQ_API_URL", DEFAULT_API_URL).rstrip("/")


def get_status() -> ApiResult:
    """Fetch the backend capability status without treating absence as success."""
    try:
        response = requests.get(
            f"{api_base_url()}/api/v1/status",
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            return ApiResult(False, detail="API returned an invalid status response.")
        return ApiResult(True, data=payload)
    except requests.RequestException as exc:
        return ApiResult(False, detail=f"API unavailable: {exc.__class__.__name__}")
    except ValueError:
        return ApiResult(False, detail="API returned invalid JSON.")


def _get(path: str, params: dict[str, Any] | None = None) -> ApiResult:
    try:
        response = requests.get(
            f"{api_base_url()}{path}", params=params, timeout=REQUEST_TIMEOUT_SECONDS
        )
        if response.status_code >= 500:
            return ApiResult(False, detail=f"Backend error ({response.status_code}).")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict | list):
            return ApiResult(False, detail="API returned an invalid response.")
        return ApiResult(True, data={"payload": payload, "status_code": response.status_code})
    except requests.RequestException as exc:
        return ApiResult(False, detail=f"API unavailable: {exc.__class__.__name__}")
    except ValueError:
        return ApiResult(False, detail="API returned invalid JSON.")


def get_announcements(page: int = 1, page_size: int = 25, **filters: Any) -> ApiResult:
    return _get("/api/v1/announcements", {"page": page, "page_size": page_size, **filters})


def get_announcement(announcement_id: int) -> ApiResult:
    return _get(f"/api/v1/announcements/{announcement_id}")


def analyze_announcement(announcement_id: int) -> ApiResult:
    try:
        response = requests.post(
            f"{api_base_url()}/api/v1/announcements/{announcement_id}/analyze",
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        payload = response.json() if response.content else {}
        return ApiResult(
            response.status_code < 400,
            data={"payload": payload, "status_code": response.status_code},
            detail=None if response.status_code < 400 else (
                "Analysis is already running." if response.status_code == 409
                else "The analysis request could not be completed."
            ),
        )
    except requests.RequestException as exc:
        return ApiResult(False, detail=f"API unavailable: {exc.__class__.__name__}")
    except ValueError:
        return ApiResult(False, detail="API returned invalid JSON.")


def get_analysis_runs(page: int = 1, page_size: int = 25) -> ApiResult:
    return _get("/api/v1/analysis-runs", {"page": page, "page_size": page_size})


def get_companies(page: int = 1, page_size: int = 25, q: str | None = None) -> ApiResult:
    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if q:
        params["q"] = q
    return _get("/api/v1/companies", params)


def get_company(company_id: int) -> ApiResult:
    return _get(f"/api/v1/companies/{company_id}")


def get_intelligence(page: int = 1, page_size: int = 100, document_ref: str | None = None) -> ApiResult:
    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if document_ref:
        params["document_ref"] = document_ref
    return _get("/api/v1/intelligence", params)


def get_intelligence_record(record_id: str) -> ApiResult:
    return _get(f"/api/v1/intelligence/{record_id}")


def get_registry_summary() -> ApiResult:
    return _get("/api/v1/registry/summary")


def get_registry_snapshots(page: int = 1, page_size: int = 25) -> ApiResult:
    return _get("/api/v1/registry/snapshots", {"page": page, "page_size": page_size})


def get_registry_snapshot(snapshot_id: int) -> ApiResult:
    return _get(f"/api/v1/registry/snapshots/{snapshot_id}")
