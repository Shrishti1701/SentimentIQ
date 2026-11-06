"""SentimentIQ professional financial intelligence dashboard."""

from __future__ import annotations

import streamlit as st

from dashboard.pages import NAVIGATION, PAGE_RENDERERS


st.set_page_config(
    page_title="SentimentIQ",
    page_icon="SI",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
      --siq-navy: #111827;
      --siq-blue: #2563eb;
      --siq-border: #dfe5ec;
      --siq-muted: #64748b;
    }
    .stApp { background: #f4f6f8; }
    [data-testid="stSidebar"] {
      background: var(--siq-navy);
      width: 18rem;
    }
    [data-testid="stSidebar"] * { color: #dbe4ee; }
    [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label {
      border-radius: 6px;
      padding: 2px 6px;
      margin-bottom: 2px;
    }
    [data-testid="stMetric"] {
      background: white;
      border: 1px solid var(--siq-border);
      border-radius: 8px;
      padding: 16px;
      min-height: 118px;
    }
    h1 { color: #172033; font-size: 2rem; letter-spacing: -0.025em; }
    h2, h3 { color: #273449; }
    .siq-brand { font-weight: 750; font-size: 1.25rem; letter-spacing: 0.02em; padding-bottom: 4px; }
    .siq-brand-sub { font-size: 0.78rem; color: #94a3b8 !important; padding-bottom: 18px; }
    .siq-section-heading { font-size: 1rem; font-weight: 700; color: #273449; margin-top: 18px; }
    .siq-spacer { height: 8px; }
    .siq-empty-panel {
      background: white;
      border: 1px dashed #ccd4df;
      border-radius: 8px;
      padding: 24px;
      margin-bottom: 16px;
    }
    .siq-empty-title { color: #334155; font-weight: 650; margin-bottom: 6px; }
    .siq-empty-copy { color: var(--siq-muted); font-size: 0.88rem; line-height: 1.5; }
    .siq-status { border-radius: 999px; padding: 5px 10px; font-size: 0.78rem; font-weight: 650; }
    .siq-status-positive { background: #dcfce7; color: #166534; }
    .siq-status-negative { background: #fee2e2; color: #991b1b; }
    .siq-status-neutral { background: #e2e8f0; color: #334155; }
    .siq-pipeline {
      display: grid;
      grid-template-columns: repeat(7, minmax(110px, 1fr));
      gap: 8px;
    }
    .siq-pipeline div {
      background: white;
      border: 1px solid var(--siq-border);
      border-radius: 8px;
      min-height: 118px;
      padding: 12px;
      display: flex;
      flex-direction: column;
    }
    .siq-pipeline strong { color: var(--siq-blue); font-size: 1.1rem; }
    .siq-pipeline span { font-weight: 650; margin: 12px 0 6px; }
    .siq-pipeline small { color: var(--siq-muted); }
    @media (max-width: 900px) {
      .siq-pipeline { grid-template-columns: repeat(2, minmax(110px, 1fr)); }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("<div class='siq-brand'>SENTIMENTIQ</div>", unsafe_allow_html=True)
    st.markdown("<div class='siq-brand-sub'>Financial intelligence</div>", unsafe_allow_html=True)
    selected_page = st.radio("Workspace", NAVIGATION, label_visibility="collapsed")
    st.markdown("---")
    st.caption("Evidence-first · India markets · 4A-1.0")

PAGE_RENDERERS[selected_page]()
