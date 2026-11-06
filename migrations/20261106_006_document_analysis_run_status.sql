ALTER TABLE document_analysis_runs ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'running';
ALTER TABLE document_analysis_runs ADD COLUMN result_summary_json TEXT NOT NULL DEFAULT '{}';
