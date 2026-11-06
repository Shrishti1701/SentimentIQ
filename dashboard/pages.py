"""Dashboard page renderers for the application shell."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from dashboard.api_client import (
    analyze_announcement,
    get_analysis_runs,
    get_announcements,
    get_companies,
    get_company,
    get_intelligence,
    get_registry_snapshot,
    get_registry_snapshots,
    get_registry_summary,
    get_status,
)
from dashboard.components import metric_card, section_heading, status_badge, unavailable_panel


NAVIGATION = (
    "Overview",
    "Company Intelligence",
    "Financial News",
    "Sentiment Analysis",
    "Aspect Analysis",
    "Competitor Intelligence",
    "Evidence Explorer",
    "Registry Management",
    "Data Pipeline Monitoring",
    "Settings",
)


def render_overview() -> None:
    st.title("Overview")
    st.caption("Evidence-backed financial intelligence workspace")

    status = get_status()
    if status.available:
        capabilities = status.data.get("capabilities", {}) if status.data else {}
        status_badge("API connected", "positive")
    else:
        status_badge("API unavailable", "negative")

    announcements = get_announcements(page_size=1)
    runs = get_analysis_runs(page_size=100)
    announcement_count = announcements.data["payload"].get("total", 0) if announcements.available else None
    run_items = runs.data["payload"].get("items", []) if runs.available else []
    completed = sum(item.get("status") == "completed" for item in run_items)
    unresolved = sum(item.get("summary", {}).get("unresolved_count", 0) for item in run_items)
    ambiguous = sum(item.get("summary", {}).get("ambiguous_count", 0) for item in run_items)

    st.markdown("<div class='siq-spacer'></div>", unsafe_allow_html=True)
    section_heading("Workspace summary", "Live counts are derived only from the configured APIs.")
    columns = st.columns(5)
    values = (
        ("Announcements", announcement_count if announcement_count is not None else "—"),
        ("Completed analyses", completed if runs.available else "—"),
        ("Pending analyses", max((announcement_count or 0) - completed, 0) if announcements.available and runs.available else "—"),
        ("Unresolved mentions", unresolved if runs.available else "—"),
        ("Ambiguous mentions", ambiguous if runs.available else "—"),
    )
    for column, (label, value) in zip(columns, values):
        with column:
            metric_card(label, str(value))

    left, right = st.columns([1.45, 1])
    with left:
        section_heading("Recent financial developments")
        news = get_announcements(page_size=5)
        if news.available and news.data["payload"].get("items"):
            st.dataframe(pd.DataFrame(news.data["payload"]["items"])[[
                column for column in ("title", "source_name", "published_at", "collected_at")
                if column in news.data["payload"]["items"][0]
            ]], use_container_width=True, hide_index=True)
        else:
            unavailable_panel("No announcements", "No announcement records are currently available.")
        section_heading("Recent analyzed documents")
        unavailable_panel("No analyzed documents", "Processed document records will appear here.")
    with right:
        section_heading("Sentiment distribution")
        unavailable_panel("Not reported by Stage 4A", "The persisted contract exposes observation types, not backend sentiment scores.")
        section_heading("Aspect distribution")
        unavailable_panel("Unavailable", "No aspect observations are currently available.")

    section_heading("Processing pipeline status")
    pipeline = (
        ("API", "Connected" if status.available else "Unavailable"),
        ("Database", str(status.data.get("database", "unknown")) if status.available else "Unknown"),
        ("Stage 1-2", "Available through orchestration"),
        ("Stage 3", "Registry-backed resolver"),
        ("Stage 4A", "Available through orchestration"),
        ("Persistence", "Available" if runs.available else "Unknown"),
        ("Recent runs", str(len(run_items))),
    )
    st.markdown(
        "<div class='siq-pipeline'>" +
        "".join(f"<div><strong>{index}</strong><span>{name}</span><small>{state}</small></div>"
                for index, (name, state) in enumerate(pipeline, 1)) +
        "</div>",
        unsafe_allow_html=True,
    )

    if not status.available:
        st.caption(status.detail)


def _not_available(module: str, required_api: str) -> None:
    st.title(module)
    unavailable_panel(
        "Backend integration unavailable",
        f"This module requires {required_api}. No sample records are shown.",
    )


def render_company_intelligence() -> None:
    st.title("Company Intelligence")
    search = st.text_input("Company or NSE symbol", placeholder="Search verified registry records")
    result = get_companies(page_size=50, q=search.strip() if search else None)
    if not result.available:
        unavailable_panel("Registry unavailable", result.detail or "The company API is unavailable.")
        return
    items = result.data["payload"].get("items", [])
    if not items:
        unavailable_panel("No verified companies", "No real registry-backed company matches this query.")
        return
    selected = st.selectbox(
        "Registry company",
        items,
        format_func=lambda item: item["canonical_legal_name"],
    )
    detail_result = get_company(selected["company_id"])
    if not detail_result.available:
        unavailable_panel("Company detail unavailable", detail_result.detail or "The company could not be loaded.")
        return
    detail = detail_result.data["payload"]
    st.subheader(detail["canonical_legal_name"])
    status_badge("Verified registry company" if detail["is_active"] else "Inactive registry company",
                 "positive" if detail["is_active"] else "neutral")
    st.caption(detail["registry_id"])
    left, right = st.columns(2)
    with left:
        section_heading("Verified securities")
        securities = detail.get("securities", [])
        st.dataframe(pd.DataFrame(securities), use_container_width=True, hide_index=True) if securities else unavailable_panel("No verified securities", "This registry company has no associated security records.")
    with right:
        section_heading("Exchange listings")
        listings = detail.get("listings", [])
        st.dataframe(pd.DataFrame(listings), use_container_width=True, hide_index=True) if listings else unavailable_panel("No listings", "This registry company has no exchange listing records.")


def render_financial_news() -> None:
    st.title("Financial News")
    left, center, right = st.columns([3, 1, 1])
    with left:
        search = st.text_input("Search company or source", key="news_search")
    with center:
        page = st.number_input("Page", min_value=1, value=1, step=1)
    with right:
        page_size = st.selectbox("Page size", (10, 25, 50), index=1)
    result = get_announcements(page=page, page_size=page_size,
                               company=search.strip() if search else None)
    if not result.available:
        unavailable_panel("Announcements unavailable", result.detail or "The announcement API is unavailable.")
        return
    payload = result.data["payload"]
    items = payload.get("items", [])
    if not items:
        unavailable_panel("No announcements", "No source announcements match the current filters.")
        return
    rows = pd.DataFrame(items)
    st.dataframe(rows[[column for column in (
        "announcement_id", "title", "source_name", "published_at", "collected_at"
    ) if column in rows.columns]], use_container_width=True, hide_index=True)
    st.caption(f"Page {payload['page']} · {payload['total']} announcements")
    selected_id = st.selectbox("Announcement detail", items, format_func=lambda item:
                               f"{item['announcement_id']} · {item.get('title') or 'Untitled announcement'}")
    st.write(selected_id)
    if st.button("Analyze announcement", type="primary", key=f"analyze-{selected_id['announcement_id']}"):
        analyzed = analyze_announcement(selected_id["announcement_id"])
        if analyzed.available:
            st.success("Analysis completed or an existing completed run was returned.")
            st.rerun()
        elif analyzed.detail:
            st.warning(analyzed.detail)
        else:
            st.error("Analysis could not be completed.")


def render_sentiment_analysis() -> None:
    st.title("Sentiment Analysis")
    unavailable_panel("No persisted sentiment labels", "The exposed Stage 4A observation contract does not provide sentiment scores or labels. Sentiment charts are omitted rather than fabricated.")


def render_aspect_analysis() -> None:
    st.title("Aspect Analysis")
    result = get_intelligence(page_size=100)
    if not result.available:
        unavailable_panel("Intelligence unavailable", result.detail or "The intelligence API is unavailable.")
        return
    items = result.data["payload"].get("items", [])
    aspects = [item for item in items if item.get("record_kind") == "entity-aspect-link"]
    if not aspects:
        unavailable_panel("No aspect records", "No persisted entity-aspect observations are available.")
        return
    st.dataframe(pd.DataFrame([
        {"record_id": item["record_id"], **item["payload"]} for item in aspects
    ]), use_container_width=True, hide_index=True)


def render_competitor_intelligence() -> None:
    st.title("Competitor Intelligence")
    result = get_intelligence(page_size=100)
    if not result.available:
        unavailable_panel("Intelligence unavailable", result.detail or "The intelligence API is unavailable.")
        return
    items = [
        item for item in result.data["payload"].get("items", [])
        if item.get("record_kind") == "competitor-occurrence"
    ]
    if not items:
        unavailable_panel("No verified competitor relationships", "Stage 4A has no persisted verified competitor occurrences.")
        return
    st.dataframe(pd.DataFrame([
        {"record_id": item["record_id"], **item["payload"]} for item in items
    ]), use_container_width=True, hide_index=True)


def render_evidence_explorer() -> None:
    st.title("Evidence Explorer")
    document_ref = st.text_input("Document reference", placeholder="nse:source-item-key")
    if not document_ref:
        unavailable_panel("Evidence source required", "Enter a persisted document reference to list its Stage 4A evidence.")
        return
    result = get_intelligence(document_ref=document_ref.strip())
    if not result.available:
        unavailable_panel("Evidence unavailable", result.detail or "The evidence API is unavailable.")
    elif not result.data["payload"].get("items"):
        unavailable_panel("No persisted evidence", "No Stage 4A records are associated with this document reference.")
    else:
        st.dataframe(pd.DataFrame([
            {"record_id": item["record_id"], "kind": item["record_kind"],
             "document_ref": item["document_ref"], "payload": item["payload"]}
            for item in result.data["payload"]["items"]
        ]), use_container_width=True, hide_index=True)


def render_registry_management() -> None:
    st.title("Registry Management")
    summary = get_registry_summary()
    if not summary.available:
        unavailable_panel("Registry unavailable", summary.detail or "The registry API is unavailable.")
        return
    payload = summary.data["payload"]
    st.write({
        "Verified registry companies": payload["company_count"],
        "Snapshots": payload["snapshot_count"],
        "Published snapshots": payload["published_snapshot_count"],
    })
    result = get_registry_snapshots(page_size=50)
    if not result.available:
        unavailable_panel("Snapshot list unavailable", result.detail or "Snapshots could not be loaded.")
        return
    items = result.data["payload"].get("items", [])
    if not items:
        unavailable_panel("No snapshots", "No registry snapshots are currently available.")
        return
    st.dataframe(pd.DataFrame(items), use_container_width=True, hide_index=True)


def render_pipeline_monitoring() -> None:
    st.title("Data Pipeline Monitoring")
    status = get_status()
    if status.available:
        status_badge(f"API {status.data.get('database', 'unknown')}", "positive")
    else:
        status_badge("API unavailable", "negative")
    runs = get_analysis_runs(page_size=100)
    if not runs.available:
        unavailable_panel("Analysis runs unavailable", runs.detail or "The analysis-run API is unavailable.")
        return
    items = runs.data["payload"].get("items", [])
    if not items:
        unavailable_panel("No analysis runs", "No document analysis executions have been persisted.")
        return
    st.dataframe(pd.DataFrame(items), use_container_width=True, hide_index=True)


def render_overview_pipeline_only() -> None:
    section_heading("Execution pipeline", "Only report stages that have been invoked by a real execution.")
    st.markdown(
        """
        <div class="siq-pipeline">
          <div><strong>1</strong><span>NSE ingestion</span><small>Not executed</small></div>
          <div><strong>2</strong><span>Document persistence</span><small>Not executed</small></div>
          <div><strong>3</strong><span>Stage 1</span><small>Implemented</small></div>
          <div><strong>4</strong><span>Stage 2</span><small>Implemented</small></div>
          <div><strong>5</strong><span>Stage 3</span><small>Not implemented</small></div>
          <div><strong>6</strong><span>Stage 4A</span><small>Blocked upstream</small></div>
          <div><strong>7</strong><span>Persistence</span><small>Implemented, no live run</small></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_settings() -> None:
    st.title("Settings")
    unavailable_panel(
        "Configuration",
        "Dashboard settings are environment-backed. Restart the service after changing SENTIMENTIQ_API_URL.",
    )
    st.code(f"SENTIMENTIQ_API_URL={getattr(__import__('os'), 'getenv')('SENTIMENTIQ_API_URL', 'http://127.0.0.1:8000')}")


PAGE_RENDERERS = {
    "Overview": render_overview,
    "Company Intelligence": render_company_intelligence,
    "Financial News": render_financial_news,
    "Sentiment Analysis": render_sentiment_analysis,
    "Aspect Analysis": render_aspect_analysis,
    "Competitor Intelligence": render_competitor_intelligence,
    "Evidence Explorer": render_evidence_explorer,
    "Registry Management": render_registry_management,
    "Data Pipeline Monitoring": render_pipeline_monitoring,
    "Settings": render_settings,
}
