# SentimentIQ Technical Audit and Reproducible Benchmark

**Audit run:** 12 November 2026 (Asia/Kolkata)  
**Repository:** `SentimentIQ/` nested project directory  
**Purpose:** Implementation audit and local engineering benchmark. This is not a production-readiness certification or a real-market NLP evaluation.

## 1. Environment and run conditions

- Windows PowerShell; Python 3.14.6; pytest 9.0.3; other package versions were not exhaustively pinned or recorded.
- Existing installed environment was used. No package installation or upgrades were performed.
- SQLite in a temporary `.audit_tmp/` directory was used for the fixture persistence timing, then removed. Pytest’s second run used `.audit_tmp/pytest` and removed the directory afterward.
- One existing untracked `Untitled-1.txt` was present before the audit and preserved.
- The project contains two explicit XML fixtures: empty RSS and synthetic RSS. It has no manually labeled corpus for entity/aspect/sentiment quality evaluation.

## 2. Architecture and implementation status

“Tested” below means relevant automated tests pass in this run; it does not establish deployment use or model accuracy.

| Component | Status | Evidence and limits |
|---|---|---|
| FastAPI API | Implemented and tested (contract/in-process) | Health, status, list/detail, analysis, company, registry and intelligence routes exist. The health route deliberately does not check external services. No deployed server/network benchmark was done. |
| Streamlit dashboard | Implemented, partially tested | Navigation and API-backed pages exist, with explicit unavailable/empty states. Sentiment labels are expressly unavailable. No browser render or visual interaction audit was run. |
| SQLAlchemy schema and persistence | Implemented and tested with SQLite fixtures | Article/NSE metadata, registry, analysis-run and Stage 4A record models; transaction, rollback and idempotency tests exist. No live PostgreSQL database was configured or validated. |
| NSE announcement RSS parser | Implemented and tested | Parses RSS in memory, normalizes entries, deduplicates feed entries, records issues, retains timezone uncertainty. Fixture coverage is synthetic, not live-feed replay. |
| NSE RSS persistence | Implemented and tested | Transactional SQLAlchemy persistence; unique source identity and conflict handling. SQLite tests pass; production PostgreSQL semantics are not independently verified. |
| NSE live fetch script | Implemented as a manual script; fresh connectivity not tested | Uses a fixed URL, bounded timeout, user agent, refuses 401/403 and does not retry/bypass. It also persists if explicitly run with configured `DATABASE_URL`; no fetch was made during this audit. |
| NSE connector class | Placeholder / not implemented | `NSEConnector.fetch_announcements()` raises `NotImplementedError`. The manual RSS script and parser/persistence are separate implemented paths. |
| BSE and general news connectors | Placeholder / not implemented | Both connector methods raise `NotImplementedError`; no NewsAPI/TheNewsAPI integration. |
| NSE registry importer | Implemented and tested against local files/SQLite | Imports NSE registry CSV snapshots, validates/audits records, handles symbol changes. Local raw CSV files exist. This is registry import, not announcement/news ingestion. |
| Article adapter and analysis orchestration | Implemented and tested | Article-to-input adaptation, registry resolution, Stage 4A processing, duplicate run handling and persistence are exercised. The pipeline is blocked upstream for Stage 4A when a usable production registry is not present. |
| Text normalization and evidence alignment | Implemented and tested | Unicode NFC/whitespace normalization with source-offset alignment and evidence-slice validation. |
| Financial entity extraction | Implemented and tested as deterministic rules | `intelligence/entity_extractor.py` emits source-grounded organization-name candidates, explicit abbreviations, labeled security identifiers and contextual references. It is not a learned NER model and does not alone establish company identity. Edge/contract tests exercise boundaries. |
| Entity resolution | Implemented, tested, but operationally bounded | Registry resolver and temporal/security evidence contracts exist. A synthetic in-memory registry supports runtime tests; production registry path uses database records. No broad labeled entity-resolution evaluation exists. |
| Financial aspect extraction | Partially implemented | Legacy `intelligence/aspect_extractor.py` is a placeholder raising `NotImplementedError`. Stage 4A runtime does implement deterministic aspect mention taxonomy/lexicon matching, unknown-aspect retention and evidence spans; it does not provide labeled quality metrics or sentiment. |
| Sentiment classification / ABSA | Not implemented | `intelligence/sentiment_model.py` raises `NotImplementedError`; no model adapter/inference implementation found. FinBERT is described as a candidate only. No FinLin, FiQA, FinER-ABSA, or other model/dataset integration was found. |
| Evidence/provenance contracts | Implemented and tested structurally | Source-bound offsets, validated resolutions/links, provenance and supersession contracts exist. They ensure contract consistency; they do not demonstrate semantic correctness of extracted evidence. |
| Confidence calibration / abstention | Partially implemented, not a classifier confidence system | Resolver and Stage 4A contracts support unresolved/ambiguous/abstained outcomes. No calibrated probability, calibration set, or sentiment abstention system exists. Database schema contains a nullable legacy confidence field; that is not evidence of calibrated confidence. |
| Deduplication | Partially implemented | RSS identity and persistence-level duplicate handling are implemented. Generic `processing/deduplicator.py` remains a `NotImplementedError` placeholder. |
| Redis/Celery, continuous ingestion, production monitoring | Planned / not implemented | Mentioned in architecture/research material; no worker/scheduler implementation or live service checks found. |

**Documentation drift:** `README.md` says integrations/NLP are not implemented and describes database/migrations as future. That is stale relative to the implemented RSS parsing/persistence, registry importer, Stage 4A contracts/runtime, migrations, and API routes. The README is useful for the intended scope but should not be used alone as a current implementation inventory.

## 3. Fresh automated test audit

Command from project directory:

```powershell
python -m pytest -q --basetemp=.audit_tmp\pytest
```

- Collected: **340**
- Passed: **340**
- Failed: **0**
- Skipped: **0**
- Errors: **0**
- Pytest-reported execution: **93.15 s**; PowerShell wall timer: **96.61 s**
- Warnings: no warning summary was emitted.

The first unmodified invocation, `python -m pytest -q`, passed 335 tests but errored during setup of five `test_nse_registry_import.py` cases because pytest could not scan `C:\Users\prern\AppData\Local\Temp\pytest-of-prern` (`PermissionError [WinError 5]`). Giving pytest a fresh basetemp inside the workspace resolved the environment issue; all 340 then passed. This was an environment/temp-path blocker, not five code failures.

Relevant collected module counts:

| Area | Tests collected | Result |
|---|---:|---|
| API (`test_api.py`) | 5 | Passed |
| Parser (`test_nse_rss_parser.py`) | 6 | Passed |
| RSS workflow (`test_nse_rss_ingestion_workflow.py`) | 1 | Passed |
| RSS persistence (`test_nse_rss_persistence.py`) | 17 | Passed |
| Pipeline orchestration (`test_document_analysis_pipeline.py`) | 2 | Passed |
| Entity extraction (`test_entity_extractor.py`) | 131 | Passed; tests are assertions/contracts, not independent labeled gold |
| Entity contracts/resolution (`test_entity_contracts.py`, `test_entity_resolution.py`, `test_registry_entity_resolver.py`) | 80 | Passed |
| Stage 4A contracts/runtime (`test_stage4a_contracts.py`, `test_stage4a_runtime.py`) | 39 | Passed |
| Remaining registry, intelligence contracts, text normalization | 59 | Passed |

Total rows in the area table sum to 340. Parser/persistence/pipeline tests use fixtures and isolated databases; they do not exercise a production PostgreSQL service.

## 4. Financial entity extraction evaluation

- Implementation identified: deterministic rule-based extractor in `intelligence/entity_extractor.py`; database-backed/synthetic registry resolvers are separate components.
- Existing labeled ground truth: **none found**. The RSS fixture is explicitly synthetic, and extractor tests contain hand-authored expected behavior examples, not a representative annotated corpus with independent labels.
- Documents/entities/TP/FP/FN, precision, recall, F1, span match rate, and boundary accuracy: **not measurable from valid ground truth; not reported**.
- The test suite covers leading “The”, organization names/contextual words, connectors, suffix phrases, abbreviations, security labels, ambiguous boundaries, punctuation/Unicode/source-span alignment and multiple mentions. Passing these examples is unit/contract coverage only.

### Deterministic component timing (synthetic input)

A local, non-persisting microbenchmark processed 50 constructed `AnalysisInput` documents. Each contained two long company-name candidates, one bank name, aspect words and ordinary prose. The timer covered `normalize_document` plus `extract_entity_mentions`; output totaled 150 candidate mentions (3/document). The documents are synthetic and are not labeled examples.

| Measure | Result |
|---|---:|
| Documents | 50 |
| Total emitted candidate mentions | 150 |
| Mean latency/document | 6.85 ms |
| Median | 6.74 ms |
| p95 (nearest-rank, 48th of 50) | 9.24 ms |
| Throughput (50 / total measured component time) | 146.01 docs/s |

Machine load and warm-up were not controlled; treat these as indicative local single-process component timings, not service capacity or accuracy. They exclude DB registry resolution and persistence.

## 5. Financial aspect extraction evaluation

The Stage 4A runtime has a deterministic aspect vocabulary/taxonomy matcher and records aspect mention spans, including unknown aspects. It links aspects to resolved entity mentions using conservative sentence-level relationship logic. The separate legacy aspect extractor remains a placeholder. There is no labeled aspect corpus. Therefore aspect TP/FP/FN, precision/recall/F1, evidence semantic correctness and latency as an isolated user-level task are **unavailable**. Contract/runtime tests passing do not measure aspect extraction quality.

## 6. Sentiment evaluation

No sentiment inference is implemented. The callable sentiment interface raises `NotImplementedError`; no model weights, adapters, tokenizer setup, or dataset loader are present. FinBERT is only a documented candidate; FinLin, FiQA and FinER-ABSA are not integrated. Accuracy, macro/weighted F1, class metrics, confusion matrix, sentiment distribution, evidence correctness, abstention rate and inference latency are **not applicable/unavailable**. Stage 4A “observations” describe structured aspect/entity occurrences, not sentiment predictions.

## 7. Connector and ingestion audit

| Source/path | Status and auth | Fixture/live evidence | Parse, normalize, persist and reliability notes |
|---|---|---|---|
| NSE RSS parser | Implemented local parser; no credentials in parser | Synthetic and empty XML fixtures; parser tests pass. No fresh live request made. | Normalizes title/link/summary and timestamps conservatively; entry identity/dedup supported. Parser itself does not persist. |
| NSE RSS persistence | Implemented SQLAlchemy service | SQLite test fixtures, transactional/idempotency/rollback tests pass. | Persists URL-identified records; duplicate unique conflicts handled. No production DB run. Timestamp timezone remains unknown when source semantics are unverified. |
| `nse_rss_test.py` manual fetch | Implemented explicit script, no configured auth; fixed URL | Historical pilot document reports 546 parsed from HTTP 200 on 4 Nov 2026; this audit did not repeat live access. Historical pilot reported read-only/no persistence, whereas current script code includes a persistence step if DB config is supplied. | Request timeout `(5,20)`, rejects 401/403, no retries or bypass; parses then persists URL-keyed items if DB configured. No current success rate. |
| `NSEConnector` | Placeholder | No operational test | `NotImplementedError`; no automatic polling, retry, backfill or rate-limit policy. |
| `BSEConnector` | Placeholder | No fixture or live test | `NotImplementedError`; source access, credentials, limits and parser/persistence unimplemented. |
| `NewsConnector` | Placeholder | No fixture or live test | `NotImplementedError`; no NewsAPI/TheNewsAPI/provider integration or auth handling. |
| NSE registry CSV import | Implemented | Local raw NSE CSVs and importer tests (8 collected; all pass) | Snapshot validation, audit/quarantine and symbol-history paths exist. This imports registry data, not news. |

No current live connector requests were made. No fresh live retrieval, persistence, source rights, rate limits, or licensing claims are inferred from the historical RSS pilot. No retry behavior exists in the manual fetch script; persistence handles selected DB uniqueness conflicts transactionally. RSS dedupe is based on feed identity, not generic text fingerprinting. No end-to-end live ingestion count is available.

## 8. Database and pipeline benchmarks

Using `tests/fixtures/nse_rss_synthetic.xml` (713 bytes, 2 synthetic announcements), the audit parsed the fixture and persisted both URL-identified announcements into a newly created SQLite database inside the temporary audit directory.

| Operation | Records | Observed duration |
|---|---:|---:|
| RSS parse | 2 | 20.63 ms |
| SQLite persistence (initial inserts) | 2 inserted, 0 duplicates | 119.43 ms |

These timings include setup/runtime overhead, are one-shot small-fixture measurements and are not throughput benchmarks. No repeated-batch duplicate timing, PostgreSQL measurement, process RSS or traced-memory measurement was performed. Entity normalization/extraction timings are in section 4. End-to-end analysis timing was not isolated because the operational production registry/database was not configured; existing pipeline tests verify functional idempotency and persistence only. Therefore end-to-end success/failure counts, p95 and throughput are unavailable.

## 9. API and dashboard evaluation

A 100-call FastAPI `TestClient` loop called only `/health`; all returned HTTP 200.

| Measure | Result |
|---|---:|
| HTTP success rate | 100/100 (100%) |
| Mean | 9.19 ms |
| Median | 6.78 ms |
| p95 (nearest-rank) | 15.71 ms |

These are in-process TestClient timings, not network/server/production latency. No live DB-backed endpoint load test or validation/error-response benchmark was performed. The API contract suite includes database-backed endpoint tests against isolated SQLite (5 API tests total). Dashboard loading/rendering was not browser-tested; source inspection shows explicit empty/unavailable panels and no persisted sentiment charts. A rendered page is not evidence of data-backed feature operation.

## 10. Security, reliability and correctness findings

- Positive: evidence spans are bound to normalized source text and mapped to original offsets; entity links require matching source-bound mentions and validated resolutions; ambiguous attribution can abstain; timestamp timezone uncertainty is preserved.
- Positive: RSS persistence is transactional and tests cover duplicate handling/rollback; API DB failures have structured 503 paths; fetch script uses bounded timeouts and explicitly stops on access denial.
- Important limitation: registry resolution cannot be considered broad financial entity disambiguation quality without real labeled/temporal cases; one synthetic registry is not production registry evidence.
- Important limitation: no sentiment classifier, calibrated confidence, model adapter architecture, continuously running ingestion, or real-time intelligence is available despite some product-level/API wording suggesting financial sentiment intelligence.
- Generic deduplication remains a placeholder; only source-specific RSS identity logic is implemented.
- `api/v1/status` reports capability names such as `nse_announcements: available` while also reporting `live_data_enabled: false`; this can overstate operational connector availability. The RSS connector class itself is not implemented.
- README status is stale against code, and stage naming is easy to overread: Stage 4A runtime is structured extraction/linking, not sentiment classification.
- No authn/authz layer or deployment hardening assessment was performed; CORS is configured for local dashboard origins by default. Do not infer a security certification from API contract tests.
- No external live source was contacted during this audit. Source terms, RSS retention rights, NLP rights, and permitted polling remain unresolved per project research notes.

## 11. Missing capabilities and blockers

1. A representative, independently annotated Indian financial dataset with span and aspect sentiment labels and an evaluation protocol.
2. A real sentiment model and ABSA inference implementation, with versioned adapters, calibration/abstention policy and evidence evaluation.
3. Production NSE/BSE/news connector paths with confirmed access rights, polling limits, retries, backfill, monitoring and source timestamp semantics.
4. A configured production registry/database and live end-to-end execution evidence.
5. Generic deduplication implementation and dashboard browser/data-backed rendering verification.
6. Reproducible controlled performance runs with repeated batches, pinned environment, memory/RSS instrumentation, and production-like deployment conditions.

## 12. Commands and methodology

From `SentimentIQ/`:

```powershell
python -m pytest -q
python -m pytest -q --basetemp=.audit_tmp\pytest
python -m pytest --collect-only -q --basetemp=.audit_tmp\collect
```

The temporary pytest base was used after the default Windows temp root raised `PermissionError`. The suite was not modified.

Other checks were read-only code/test/fixture inspection and temporary in-memory/local operations. Component timing used `time.perf_counter()` over 50 constructed inputs; summary used arithmetic mean, median and nearest-rank p95. RSS parsing/persistence used the existing 713-byte synthetic XML fixture and SQLAlchemy SQLite. API timing used 100 sequential FastAPI TestClient calls to `/health`; it is explicitly in-process. No synthetic output is presented as real-market performance, and no accuracy metric was derived from unit tests.

