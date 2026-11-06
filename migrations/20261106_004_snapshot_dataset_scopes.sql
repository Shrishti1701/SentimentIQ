-- Independently versioned NSE registry dataset publication scopes.

ALTER TABLE registry_snapshots
ADD COLUMN dataset_scope VARCHAR(40) NOT NULL DEFAULT 'NSE_CURRENT_LISTINGS'
    CHECK (dataset_scope IN ('NSE_CURRENT_LISTINGS', 'NSE_HISTORICAL_CHANGES'));

UPDATE registry_snapshots
SET dataset_scope = 'NSE_HISTORICAL_CHANGES'
WHERE lower(source_manifest_json) LIKE '%namechange.csv%'
   OR lower(source_manifest_json) LIKE '%symbolchange.csv%';

DROP INDEX IF EXISTS uq_registry_one_published_snapshot;

CREATE UNIQUE INDEX IF NOT EXISTS uq_registry_one_published_snapshot_per_scope
ON registry_snapshots(dataset_scope)
WHERE snapshot_state = 'published';

CREATE TRIGGER IF NOT EXISTS trg_registry_published_snapshot_immutable_insert
BEFORE UPDATE ON registry_snapshots
WHEN OLD.snapshot_state = 'published'
 AND NEW.snapshot_state = 'published'
 AND (
    NEW.external_id <> OLD.external_id
    OR NEW.dataset_scope <> OLD.dataset_scope
    OR NEW.source_manifest_json <> OLD.source_manifest_json
    OR NEW.validation_counts_json <> OLD.validation_counts_json
    OR NEW.created_at <> OLD.created_at
    OR NEW.published_at <> OLD.published_at
 )
BEGIN
    SELECT RAISE(ABORT, 'published registry snapshots are immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_registry_published_snapshot_immutable_supersede
BEFORE UPDATE ON registry_snapshots
WHEN OLD.snapshot_state = 'published'
 AND NEW.snapshot_state NOT IN ('published', 'superseded')
BEGIN
    SELECT RAISE(ABORT, 'published registry snapshots may only be superseded');
END;
