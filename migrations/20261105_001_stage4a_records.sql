-- Stage 4A 4A-1.0 persistence integration.

CREATE TABLE IF NOT EXISTS stage4a_records (
    id INTEGER PRIMARY KEY,
    document_ref VARCHAR(300) NOT NULL,
    record_id VARCHAR(256) NOT NULL UNIQUE,
    record_kind VARCHAR(100) NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_stage4a_records_document_ref
    ON stage4a_records (document_ref);
CREATE UNIQUE INDEX IF NOT EXISTS uq_stage4a_records_record_id
    ON stage4a_records (record_id);

CREATE TABLE IF NOT EXISTS stage4a_supersessions (
    id INTEGER PRIMARY KEY,
    supersession_id VARCHAR(256) NOT NULL,
    predecessor_observation_id VARCHAR(256) NOT NULL,
    successor_observation_id VARCHAR(256) NOT NULL,
    document_ref VARCHAR(300) NOT NULL,
    source_field VARCHAR(20) NOT NULL,
    start INTEGER NOT NULL,
    end INTEGER NOT NULL,
    quote TEXT NOT NULL,
    reason VARCHAR(100) NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE (supersession_id)
);
