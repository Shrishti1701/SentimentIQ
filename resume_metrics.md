# SentimentIQ Resume Metrics and Evidence

The strongest defensible resume statements describe implemented engineering and test coverage. This repository has no valid labeled financial NLP dataset and no sentiment model, so do not claim model accuracy or ABSA performance.

## Ranked strongest three

1. **Built a deterministic financial entity-mention extraction pipeline with Unicode-aware source-span alignment, explicit security-identifier handling, conservative boundary rules, and registry-resolution contracts.**  
   **Evidence:** `intelligence/entity_extractor.py`, entity contracts/resolver, and 131 passing entity-extractor tests plus contract/resolver coverage. These are deterministic rule and contract tests, not labeled-corpus NER metrics.

2. **Implemented an NSE announcement RSS parsing and transactional persistence path, with source-identity deduplication, timestamp uncertainty preservation, and rollback/idempotency behavior.**  
   **Evidence:** parser/persistence modules; 6 parser tests, 17 persistence tests, 1 ingestion-workflow test and SQLite fixture benchmark (2 synthetic fixture records inserted; 119.43 ms one-shot). No fresh live connector result is claimed.

3. **Delivered a FastAPI, SQLAlchemy and SQLite-testable document-analysis foundation with source-bound evidence contracts and persisted Stage 4A records.**  
   **Evidence:** API/pipeline/stage tests; full suite 340/340 passing with workspace pytest temp base. In-process `/health` TestClient: 100/100 HTTP 200, median 6.78 ms and p95 15.71 ms; not production network latency.

## Additional resume-ready options

4. **Measured 50 synthetic document normalization and entity-extraction runs at 6.85 ms mean and 9.24 ms p95 (146 documents/s) in a local Python benchmark.**  
   **Evidence:** temporary audit harness, 50 constructed documents and 150 emitted candidate mentions. Report only as a local component benchmark; it is not an accuracy or deployment throughput claim.

5. **Implemented a deterministic financial-aspect mention and evidence-linking runtime with unknown-aspect retention and conservative entity/aspect attribution.**  
   **Evidence:** `intelligence/stage4a/runtime.py` and passing Stage 4A contract/runtime tests. Aspect precision/recall is unavailable because no labeled dataset was found; this is not sentiment ABSA.

6. **Added database-backed registry snapshot import and validation paths for NSE company/security data, including audit/quarantine and symbol-history handling.**  
   **Evidence:** `registry/nse_import.py`, local raw NSE CSVs, and 8 passing registry import tests. This is registry ingestion, not live announcement ingestion.

## Claims to exclude

- Any entity extraction precision, recall, F1 or span accuracy; no independent labeled ground truth exists.
- Any aspect extraction or sentiment accuracy, macro-F1, weighted-F1, confusion matrix, or evidence correctness metric.
- “Implemented ABSA”, “FinBERT-powered”, “FinLin”, “FiQA/FinER-ABSA integrated”, calibrated confidence, or sentiment abstention; no sentiment inference/model integration is present.
- “Real-time/live financial intelligence”, continuously operating NSE/BSE/news ingestion, or successful current live connectivity; this audit made no live requests and connectors are placeholders except for a manual NSE RSS script.
- Production-ready, production-scale or production latency/throughput claims; no production database/service benchmark was performed.
- Stock price prediction or trading performance; this is outside the implemented system.
- “340 model tests” or “100% NLP accuracy”; 340 is the total passing automated test count, mainly contract, implementation behavior and SQLite fixture tests.

## Recommended compact version

- Developed deterministic financial company-mention extraction with source-grounded Unicode span alignment and registry-resolution contracts; validated with 131 passing extractor tests (unit/contract coverage, no gold-set accuracy claim).
- Implemented transactional NSE RSS parsing and persistence with identity-based duplicate handling and rollback coverage; 24 parser, workflow and persistence tests passed.
- Built FastAPI/SQLAlchemy document-analysis and evidence-persistence foundations; 340/340 repository tests passed, with local TestClient health p95 of 15.71 ms (in-process only).
