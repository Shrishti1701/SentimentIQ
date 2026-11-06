"""Reusable presentation components for the Streamlit dashboard."""

from __future__ import annotations

import streamlit as st


def metric_card(label: str, value: str, *, helper: str | None = None) -> None:
    st.metric(label=label, value=value, help=helper)


def unavailable_panel(title: str, message: str) -> None:
    st.markdown(
        """
        <div class="siq-empty-panel">
          <div class="siq-empty-title">{title}</div>
          <div class="siq-empty-copy">{message}</div>
        </div>
        """.format(title=title, message=message),
        unsafe_allow_html=True,
    )


def section_heading(title: str, description: str | None = None) -> None:
    st.markdown(f"<div class='siq-section-heading'>{title}</div>", unsafe_allow_html=True)
    if description:
        st.caption(description)


def status_badge(label: str, tone: str = "neutral") -> None:
    st.markdown(
        f"<span class='siq-status siq-status-{tone}'>{label}</span>",
        unsafe_allow_html=True,
    )

