-- Registry hardening: deterministic ID, checksum, lifecycle, and timestamp invariants.

CREATE UNIQUE INDEX IF NOT EXISTS uq_registry_one_published_snapshot
    ON registry_snapshots(snapshot_state)
    WHERE snapshot_state = 'published';

CREATE TRIGGER IF NOT EXISTS trg_registry_source_checksum_insert
BEFORE INSERT ON registry_sources
WHEN length(NEW.sha256_checksum) <> 64
  OR NEW.sha256_checksum <> lower(NEW.sha256_checksum)
  OR NEW.sha256_checksum GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'invalid registry source SHA-256 checksum');
END;

CREATE TRIGGER IF NOT EXISTS trg_registry_source_checksum_update
BEFORE UPDATE OF sha256_checksum ON registry_sources
WHEN length(NEW.sha256_checksum) <> 64
  OR NEW.sha256_checksum <> lower(NEW.sha256_checksum)
  OR NEW.sha256_checksum GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'invalid registry source SHA-256 checksum');
END;

CREATE TRIGGER IF NOT EXISTS trg_registry_company_external_id_insert
BEFORE INSERT ON registry_companies
WHEN NEW.external_id NOT GLOB 'REGISTRY-COMPANY:v1:*'
  OR length(substr(NEW.external_id, 21)) <> 64
  OR substr(NEW.external_id, 21) GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'invalid registry company external ID');
END;

CREATE TRIGGER IF NOT EXISTS trg_registry_security_external_id_insert
BEFORE INSERT ON registry_securities
WHEN NEW.external_id NOT GLOB 'REGISTRY-SECURITY:v1:*'
  OR length(substr(NEW.external_id, 22)) <> 64
  OR substr(NEW.external_id, 22) GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'invalid registry security external ID');
END;

CREATE TRIGGER IF NOT EXISTS trg_registry_listing_external_id_insert
BEFORE INSERT ON registry_exchange_listings
WHEN NEW.external_id NOT GLOB 'REGISTRY-LISTING:v1:*'
  OR length(substr(NEW.external_id, 21)) <> 64
  OR substr(NEW.external_id, 21) GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'invalid registry listing external ID');
END;

CREATE TRIGGER IF NOT EXISTS trg_registry_snapshot_external_id_insert
BEFORE INSERT ON registry_snapshots
WHEN NEW.external_id NOT GLOB 'REGISTRY-SNAPSHOT:v1:*'
  OR length(substr(NEW.external_id, 22)) <> 64
  OR substr(NEW.external_id, 22) GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'invalid registry snapshot external ID');
END;

CREATE TRIGGER IF NOT EXISTS trg_registry_source_external_id_insert
BEFORE INSERT ON registry_sources
WHEN NEW.external_id NOT GLOB 'REGISTRY-SOURCE:v1:*'
  OR length(substr(NEW.external_id, 20)) <> 64
  OR substr(NEW.external_id, 20) GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'invalid registry source external ID');
END;

CREATE TRIGGER IF NOT EXISTS trg_registry_company_external_id_update
BEFORE UPDATE OF external_id ON registry_companies
WHEN NEW.external_id NOT GLOB 'REGISTRY-COMPANY:v1:*'
  OR length(substr(NEW.external_id, 21)) <> 64
  OR substr(NEW.external_id, 21) GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'invalid registry company external ID');
END;

CREATE TRIGGER IF NOT EXISTS trg_registry_security_external_id_update
BEFORE UPDATE OF external_id ON registry_securities
WHEN NEW.external_id NOT GLOB 'REGISTRY-SECURITY:v1:*'
  OR length(substr(NEW.external_id, 22)) <> 64
  OR substr(NEW.external_id, 22) GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'invalid registry security external ID');
END;

CREATE TRIGGER IF NOT EXISTS trg_registry_listing_external_id_update
BEFORE UPDATE OF external_id ON registry_exchange_listings
WHEN NEW.external_id NOT GLOB 'REGISTRY-LISTING:v1:*'
  OR length(substr(NEW.external_id, 21)) <> 64
  OR substr(NEW.external_id, 21) GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'invalid registry listing external ID');
END;

CREATE TRIGGER IF NOT EXISTS trg_registry_snapshot_external_id_update
BEFORE UPDATE OF external_id ON registry_snapshots
WHEN NEW.external_id NOT GLOB 'REGISTRY-SNAPSHOT:v1:*'
  OR length(substr(NEW.external_id, 22)) <> 64
  OR substr(NEW.external_id, 22) GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'invalid registry snapshot external ID');
END;

CREATE TRIGGER IF NOT EXISTS trg_registry_source_external_id_update
BEFORE UPDATE OF external_id ON registry_sources
WHEN NEW.external_id NOT GLOB 'REGISTRY-SOURCE:v1:*'
  OR length(substr(NEW.external_id, 20)) <> 64
  OR substr(NEW.external_id, 20) GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'invalid registry source external ID');
END;

CREATE TRIGGER IF NOT EXISTS trg_registry_company_updated_at
AFTER UPDATE ON registry_companies
BEGIN
    UPDATE registry_companies
    SET updated_at = CURRENT_TIMESTAMP
    WHERE id = NEW.id AND updated_at = OLD.updated_at;
END;

CREATE TRIGGER IF NOT EXISTS trg_registry_snapshot_publication_insert
BEFORE INSERT ON registry_snapshots
WHEN NEW.snapshot_state = 'published' AND NEW.published_at IS NULL
BEGIN
    SELECT RAISE(ABORT, 'published registry snapshots require publication time');
END;

CREATE TRIGGER IF NOT EXISTS trg_registry_snapshot_publication_update
BEFORE UPDATE OF snapshot_state, published_at ON registry_snapshots
WHEN NEW.snapshot_state = 'published' AND NEW.published_at IS NULL
BEGIN
    SELECT RAISE(ABORT, 'published registry snapshots require publication time');
END;
