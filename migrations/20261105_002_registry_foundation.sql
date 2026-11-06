-- Authoritative NSE/BSE registry foundation.

CREATE TABLE IF NOT EXISTS registry_companies (
    id INTEGER PRIMARY KEY,
    external_id VARCHAR(256) NOT NULL UNIQUE,
    canonical_legal_name VARCHAR(500) NOT NULL CHECK (length(canonical_legal_name) > 0),
    is_active BOOLEAN NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    parent_company_id INTEGER REFERENCES registry_companies(id) ON DELETE RESTRICT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_registry_companies_parent ON registry_companies (parent_company_id);

CREATE TABLE IF NOT EXISTS registry_securities (
    id INTEGER PRIMARY KEY,
    external_id VARCHAR(256) NOT NULL UNIQUE,
    instrument_classification VARCHAR(100) NOT NULL CHECK (length(instrument_classification) > 0),
    isin VARCHAR(12) UNIQUE CHECK (isin IS NULL OR (length(isin) = 12 AND isin = upper(isin))),
    isin_verified BOOLEAN NOT NULL DEFAULT 0 CHECK (isin_verified IN (0, 1)),
    issuer_company_id INTEGER REFERENCES registry_companies(id) ON DELETE RESTRICT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((isin IS NULL AND isin_verified = 0) OR (isin IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS ix_registry_securities_issuer ON registry_securities (issuer_company_id);

CREATE TABLE IF NOT EXISTS registry_snapshots (
    id INTEGER PRIMARY KEY,
    external_id VARCHAR(256) NOT NULL UNIQUE,
    snapshot_state VARCHAR(30) NOT NULL DEFAULT 'building'
        CHECK (snapshot_state IN ('building', 'validated', 'published', 'superseded')),
    source_manifest_json TEXT NOT NULL DEFAULT '[]',
    validation_counts_json TEXT NOT NULL DEFAULT '{}',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at DATETIME
);

CREATE TABLE IF NOT EXISTS registry_sources (
    id INTEGER PRIMARY KEY,
    external_id VARCHAR(256) NOT NULL UNIQUE,
    snapshot_id INTEGER REFERENCES registry_snapshots(id) ON DELETE RESTRICT,
    original_filename VARCHAR(500) NOT NULL CHECK (length(original_filename) > 0),
    source_url VARCHAR(2048) NOT NULL,
    retrieval_date DATE NOT NULL,
    source_update_date DATE,
    sha256_checksum VARCHAR(64) NOT NULL CHECK (length(sha256_checksum) = 64),
    file_format VARCHAR(20) NOT NULL CHECK (length(file_format) > 0),
    usage_permission_status VARCHAR(50) NOT NULL DEFAULT 'unreviewed',
    import_timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (original_filename, sha256_checksum, retrieval_date)
);

CREATE INDEX IF NOT EXISTS ix_registry_sources_snapshot ON registry_sources (snapshot_id);
CREATE INDEX IF NOT EXISTS ix_registry_sources_checksum ON registry_sources (sha256_checksum);

CREATE TABLE IF NOT EXISTS registry_exchange_listings (
    id INTEGER PRIMARY KEY,
    external_id VARCHAR(256) NOT NULL UNIQUE,
    security_id INTEGER REFERENCES registry_securities(id) ON DELETE RESTRICT,
    company_id INTEGER REFERENCES registry_companies(id) ON DELETE RESTRICT,
    exchange_code VARCHAR(20) NOT NULL CHECK (length(exchange_code) > 0),
    symbol VARCHAR(100) NOT NULL CHECK (length(symbol) > 0),
    series VARCHAR(20),
    listing_date DATE,
    valid_from DATE,
    valid_to DATE,
    listing_status VARCHAR(30) NOT NULL DEFAULT 'active',
    CHECK ((valid_to IS NULL) OR (valid_from IS NULL) OR (valid_to > valid_from)),
    CHECK (security_id IS NOT NULL OR company_id IS NOT NULL),
    UNIQUE (exchange_code, symbol, series, valid_from)
);

CREATE INDEX IF NOT EXISTS ix_registry_listings_security ON registry_exchange_listings (security_id);
CREATE INDEX IF NOT EXISTS ix_registry_listings_company ON registry_exchange_listings (company_id);
CREATE INDEX IF NOT EXISTS ix_registry_listings_symbol_valid ON registry_exchange_listings (exchange_code, symbol, valid_from, valid_to);

CREATE TABLE IF NOT EXISTS registry_company_aliases (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES registry_companies(id) ON DELETE CASCADE,
    source_id INTEGER NOT NULL REFERENCES registry_sources(id) ON DELETE RESTRICT,
    original_alias VARCHAR(500) NOT NULL CHECK (length(original_alias) > 0),
    normalized_alias_key VARCHAR(500) NOT NULL CHECK (length(normalized_alias_key) > 0),
    alias_type VARCHAR(50) NOT NULL,
    valid_from DATE,
    valid_to DATE,
    source_row_number INTEGER,
    CHECK ((valid_to IS NULL) OR (valid_from IS NULL) OR (valid_to > valid_from)),
    CHECK (source_row_number IS NULL OR source_row_number > 0)
);

CREATE INDEX IF NOT EXISTS ix_registry_aliases_company_normalized ON registry_company_aliases (company_id, normalized_alias_key);
CREATE INDEX IF NOT EXISTS ix_registry_aliases_validity ON registry_company_aliases (valid_from, valid_to);

CREATE TABLE IF NOT EXISTS registry_listing_symbol_history (
    id INTEGER PRIMARY KEY,
    listing_id INTEGER REFERENCES registry_exchange_listings(id) ON DELETE RESTRICT,
    source_id INTEGER NOT NULL REFERENCES registry_sources(id) ON DELETE RESTRICT,
    previous_symbol VARCHAR(100) NOT NULL CHECK (length(previous_symbol) > 0),
    new_symbol VARCHAR(100) NOT NULL CHECK (length(new_symbol) > 0),
    effective_date DATE NOT NULL,
    review_status VARCHAR(30) NOT NULL DEFAULT 'accepted'
        CHECK (review_status IN ('accepted', 'requires_review', 'rejected')),
    source_row_number INTEGER CHECK (source_row_number IS NULL OR source_row_number > 0),
    CHECK (previous_symbol <> new_symbol),
    UNIQUE (listing_id, previous_symbol, new_symbol, effective_date)
);

CREATE INDEX IF NOT EXISTS ix_registry_symbol_history_listing_date
    ON registry_listing_symbol_history (listing_id, effective_date);

CREATE TABLE IF NOT EXISTS registry_row_audit (
    id INTEGER PRIMARY KEY,
    snapshot_id INTEGER NOT NULL REFERENCES registry_snapshots(id) ON DELETE CASCADE,
    source_id INTEGER NOT NULL REFERENCES registry_sources(id) ON DELETE RESTRICT,
    source_row_number INTEGER NOT NULL CHECK (source_row_number > 0),
    raw_row_json TEXT NOT NULL,
    validation_outcome VARCHAR(30) NOT NULL
        CHECK (validation_outcome IN ('accepted', 'rejected', 'quarantined', 'duplicate', 'requires_review')),
    reason TEXT,
    normalized_values_json TEXT NOT NULL DEFAULT '{}',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (snapshot_id, source_id, source_row_number)
);

CREATE INDEX IF NOT EXISTS ix_registry_audit_outcome ON registry_row_audit (validation_outcome);
