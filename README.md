# SentimentIQ

SentimentIQ is an early-stage financial intelligence platform for Indian market information. It is designed to identify companies and financial aspects in news and official announcements, then explain positive, negative, or neutral aspect-level sentiment with supporting evidence. It is **not a stock-price prediction system**.

## Problem and intended capabilities

Financial information can affect different parts of a business in different ways. SentimentIQ's intended workflow is to collect permitted source material, identify companies and financial aspects (such as revenue, profit, debt, expenses, management, and growth), classify sentiment per aspect, preserve evidence, and present the results in a dashboard.

No source integrations or NLP predictions are implemented yet. The interface reports this clearly and does not show fabricated financial information.

## Technology

Python, FastAPI, SQLAlchemy, PostgreSQL, Pandas, Streamlit, Redis/Celery (future background processing), and Hugging Face Transformers/PyTorch (future NLP). FinBERT is a candidate baseline; it is not installed or loaded by the initial setup.

## Project structure

```text
SentimentIQ/
├── api/                 # FastAPI service
├── config/              # Environment-backed settings
├── dashboard/           # Streamlit interface
├── database/            # SQLAlchemy schema and lazy connection helper
├── ingestion/           # NSE, BSE, and news connector interfaces
├── intelligence/        # Entity, aspect, and sentiment interfaces
├── processing/          # Cleaning and deduplication interfaces
├── tests/               # API contract tests
├── .env.example         # Local configuration template
├── requirements.txt     # Initial application dependencies
└── requirements-ml.txt  # Optional model-stage dependencies
```

## Windows setup

From the project directory in PowerShell:

```powershell
py -m venv .venv
```

If PowerShell blocks activation scripts, use the environment's Python directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Or, for the current PowerShell process only, activate with:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

The process-scoped policy ends when that PowerShell window closes. No system policy change is needed.

Copy `.env.example` to `.env` if you need to customize local settings. `.env` is ignored by Git; never commit credentials. PostgreSQL and Redis are not required to start the API health endpoint. Database access is lazy and requires a valid `DATABASE_URL` only when database operations are introduced.

## Run the backend

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.main:app --reload
```

Open `http://127.0.0.1:8000`, `http://127.0.0.1:8000/health`, and `http://127.0.0.1:8000/docs`.

## Run the dashboard

```powershell
.\.venv\Scripts\python.exe -m streamlit run dashboard/app.py
```

The dashboard uses a responsive Streamlit shell with Overview, Company Intelligence, News, Sentiment,
Aspect, Competitor, Evidence, Registry, Pipeline Monitoring and Settings modules. API-backed
metrics are not fabricated: modules report unavailable or empty states until a real endpoint exists.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Current development status

- API foundation: implemented; health does not connect to PostgreSQL or Redis.
- Database: initial SQLAlchemy models and lazy engine helper prepared; no migrations or live database validation yet.
- Source ingestion: interfaces only. Verify official documentation, terms, licensing, authentication requirements, and allowed polling frequency before building a connector. No endpoints or RSS feeds are assumed.
- Cleaning, deduplication, entity extraction, aspect extraction, and sentiment: interfaces only.
- Dashboard: initial status view; no live integration.
- ML dependencies: deferred to `requirements-ml.txt` for a later development stage.

## Upcoming milestones

1. Select permitted NSE/BSE and news sources after documentation and access review.
2. Define an annotated Indian financial aspect sentiment dataset and evaluation protocol.
3. Implement and evaluate entity/aspect extraction and a FinBERT-based sentiment baseline.
4. Add database migrations and persistence after choosing a PostgreSQL deployment.
5. Add scheduled ingestion with Redis/Celery and connect the dashboard to persisted results.
