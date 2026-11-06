CREATE TABLE IF NOT EXISTS document_analysis_runs (
    id INTEGER PRIMARY KEY,
    document_ref VARCHAR(300) NOT NULL,
    pipeline_version VARCHAR(100) NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_document_analysis_run_document_ref
    ON document_analysis_runs(document_ref);
