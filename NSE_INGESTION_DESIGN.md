# NSE RSS Ingestion Design

**Status:** Design proposal only; no production connector or storage is implemented.  
**Basis:** Read-only pilot documented in [NSE_RSS_PILOT.md](NSE_RSS_PILOT.md), the standalone [feasibility script](ingestion/nse_rss_test.py), and the current SQLAlchemy models in `database/models.py`.

## Scope and constraints

The pilot establishes that one request to the observed NSE announcements RSS URL returned an XML response that `feedparser` parsed. It does not establish permission for automated polling, durable storage, NLP, model training, customer display, or redistribution. This design keeps these rights unresolved. No RSS response or announcement content is copied into this document or retained by a connector.

The implementation below is conditional on written confirmation from NSE covering access frequency, retention, NLP/derived use, and display or redistribution. Any denied or unclear permission means the corresponding collection or processing remains disabled.

## Verified behavior and limits

The pilot checked the official NSE RSS directory at <https://www.nseindia.com/static/rss-feed>. It identifies Corporate Information > Announcements and directs users to the RSS icon. The tested URL was <https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml>. The directory page does not expose the endpoint as ordinary text, so its current icon target should be rechecked before implementation.

In the pilot response, the HTTP status was 200, the content type was `application/xml`, and 546 entries were parsed without a feedparser malformed-feed warning. That count describes one response only; it is not a completeness, retention, or history guarantee. The pilot printed a limited sample and did not save entries.

Observed entry fields exposed by `feedparser` were:

| Field | Verified observation | Design interpretation |
|---|---|---|
| `title` | Present; appeared to be the company name in sampled entries. | Preserve as a source label if permitted. It is not a verified symbol or stable company key. |
| `link` | Present; linked to an NSE-hosted filing/attachment. | Best observed candidate for item identity, but immutability and one-to-one correspondence are unverified. |
| `published` | Present as a display string. Sample format was `DD-Mon-YYYY HH:MM:SS`, with no explicit timezone marker. | Keep the original string separate; do not assume timezone or convert until NSE confirms its semantics. |
| `published_parsed` | Present as a parsed date tuple. | A parser result is not proof of timezone; do not treat it as an authoritative UTC/IST timestamp. |
| `summary` | Present as announcement description text; some samples included a `SUBJECT:` label. | Candidate announcement text only if retention and NLP rights are confirmed. |
| `summary_detail`, `title_detail`, `links` | Present as feedparser detail structures. | Useful for parser diagnostics, not independently verified stable schema. |
| `description` | No separate `description` key was observed. | Do not rely on it; pilot display used `summary` fallback. |

The observed fields did not include a distinct company symbol, source-received timestamp, dissemination timestamp, RSS GUID/stable item ID, or explicit timezone. Feed structure can change; validate the actual current response before relying on any field.

## Identity and duplicate detection

### Candidate identity hierarchy

1. **Preferred observed key:** normalized `link` URL. Canonicalization should be deliberately conservative: lowercase scheme and host, remove a fragment and default port, preserve path case and query parameters. Do not fetch the linked document to derive identity. URL immutability and whether one URL can represent multiple revisions need NSE confirmation.
2. **Fallback only if link is absent:** versioned digest of a deterministic tuple such as source name, Unicode-normalized/case-folded title, raw publication string, and whitespace-normalized summary. This is lower confidence: identical announcements may collide, while minor edits may produce a new key. Record the identity method/version and flag fallback records for review.
3. **No reliable identity:** reject from automatic persistence and count as an invalid/unidentified entry. Do not invent an identifier from the array position or current time.

If approved, a compact `source_item_key` can be a SHA-256 digest over the identity method and canonical input. A digest is still derived data and may be subject to NSE terms; it must not be retained before that permission is clear.

### Idempotence and revisions

The current `FinancialArticle` model has a unique constraint on `source_url` (`uq_article_source_url`). This supports a basic idempotent insert when the URL is stable: repeated observations of the same source URL should resolve to the existing article. The connector must handle concurrent unique-key conflicts by re-reading the existing row and treating the record as a duplicate.

Do not silently overwrite an existing article when title, summary, or publication value changes under the same URL. The current schema has no source revision history or raw source key. If NSE can revise/correct entries, add a separate revision/observation table or an explicit versioning policy before production. A unique `source_item_key` is preferable to relying on a URL alone if NSE confirms a stable item identifier.

NSE and BSE links may differ for the same filing. Do not merge cross-exchange items by fuzzy title/summary matching. A content fingerprint would require access to linked documents and additional rights; it is outside this design's present scope.

## Timestamps and timezone handling

The pilot observed a `published` string in a day-month-year/time format without a timezone suffix, plus `published_parsed`. It did not establish whether NSE means IST, server-local time, or another convention. Feedparser's parsed tuple does not resolve that ambiguity.

Proposed rules:

- Preserve the raw source timestamp string in a dedicated field if NSE permits storage.
- Until NSE confirms the timezone and semantic meaning (publication, upload, or exchange dissemination time), leave normalized `published_at` null. Never label the value UTC or IST by inference from the exchange's location.
- If NSE confirms the timestamp is IST, parse with the explicit `Asia/Kolkata` zone, then store a timezone-aware UTC instant in `published_at`; retain the raw string and source zone for audit if permitted.
- Parse failures and missing dates should not fail an otherwise valid entry. Keep the normalized date null and increment a diagnostic counter.
- `collected_at` is the connector's own observation time, generated as timezone-aware UTC (or by a database `now()` column configured consistently). It must remain distinct from publication time.

## Incremental polling design

No numeric NSE rate limit, recommended automated polling interval, freshness SLA, or retention/backfill guarantee was established by the pilot. Therefore this document does not prescribe a production interval. Obtain the permitted frequency and recovery expectations in writing before enabling a scheduler.

Subject to permission, use snapshot-based polling rather than a publication-time-only cursor:

1. Fetch the complete RSS response at the authorized interval, subject to a bounded response size and request timeout.
2. Parse the complete response in memory. Treat entries as potentially out of order and pass every identifiable entry through idempotent duplicate checks.
3. Persist a source poll state (last successful poll time, last observed timestamp for diagnostics, and optionally ETag/Last-Modified if NSE actually supplies them). Do not use the highest `published` value as proof that earlier entries cannot arrive later.
4. Advance `last_success_at` only after a successful parse and committed database transaction. A failed fetch, malformed response, or database rollback must leave it unchanged.

The pilot's 546-entry response does not establish whether the feed is a bounded rolling window or a complete archive. If the feed is bounded, missed items may be unrecoverable; confirm the window and backfill route with NSE. A future overlap window is a possible supplement, but its duration must be set from NSE's retention/backfill behavior and timestamp semantics, not guessed. Conditional HTTP requests may reduce transfer only if supported by actual response validators; this was not verified.

## Retry, logging, and recovery

Proposed network policy, subject to NSE's published/approved limits:

- Use TLS certificate validation, explicit connect/read timeouts, and a single normal feed request per poll. Do not add cookie harvesting, CAPTCHA handling, browser impersonation, or restriction bypasses.
- Retry only transient failures (connection/timeouts, HTTP 408/429, and selected 5xx) with a small bounded exponential backoff and jitter; honor `Retry-After` when present. The attempt count and delays must fit within NSE's authorized request rate.
- Treat 401/403 and other non-transient 4xx responses as a stop condition. Do not retry aggressively or attempt another endpoint to evade denial. Alert an operator and await investigation.
- Distinguish a successful, valid empty feed from an empty HTTP body or malformed XML. Neither malformed content nor an HTTP failure advances the cursor.
- On database failure, roll back the transaction. Retry database work separately from network fetch using the already parsed in-memory batch; do not refetch just because a DB transaction failed. Use unique constraints to make a replay safe.

Structured operational logs should contain source identifier, run ID, timestamps/duration, HTTP status, content type, response byte count, attempt number, parsed/invalid/duplicate/inserted/updated counts, and error class. Do not log titles, summaries, raw XML, linked-document contents, authentication material, or query-bearing URLs. Metrics should cover poll success/failure, last successful poll age, parse failures, duplicate rate, and database write failures. Apply normal log access controls and retention.

## Data representation and storage boundaries

Keep source data distinct from normalized application metadata. No raw feed data should be persisted until usage rights explicitly allow it.

| Concept | Candidate representation | Notes |
|---|---|---|
| Source identity | `source_name` = NSE RSS; `source_url` = entry link; optionally versioned `source_item_key` | Existing model supports the first two. Link stability and durable key rules need confirmation. |
| Raw title | `source_title` string | Keep separate from a matched `Company.name`; RSS title is not a verified identifier. |
| Raw summary | `source_summary` text or `original_text` | Store only if retention/NLP rights permit; preserve as source text rather than silently rewriting. |
| Subject | `source_subject` text | Extracted from summary only under confirmed rights; keep separate from the complete source summary and preserve extraction provenance. |
| Raw timestamp | `published_at_raw` string | Needed to audit parsing/timezone decisions; permission required. |
| Normalized timestamp | `published_at` timezone-aware datetime or null | Populate only after timezone/meaning confirmation. |
| Collection timestamp | `collected_at` timezone-aware UTC | Connector observation time, not an NSE timestamp. |
| Raw entry/feed snapshot | Optional JSON/XML payload in a restricted source-payload store | Contains source content; avoid duplicating the full XML unless retention is specifically approved. |
| Poll state | Source-level cursor/status row | Operational metadata; persist only after approved connector activation. |

The existing `FinancialArticle` model has `source_url`, `source_name`, nullable `published_at`, `collected_at`, and required `original_text`. It has no raw title, source item key, raw timestamp, subject, revision history, or payload field. In particular, `original_text` cannot safely be filled with a placeholder or empty value because it is non-null, and using it for summary text is allowed only after terms are clear. The synthetic persistence foundation adds an ORM-only `NSEAnnouncementMetadata` table for source key, title, and raw/unzoned timestamps; no configured database migration has been applied. See [NSE_PERSISTENCE_MIGRATION.md](NSE_PERSISTENCE_MIGRATION.md) before applying this schema to any database.

Additional production schema decisions still open include `source_subject`, revision history, and any permitted structured `source_payload`. Avoid storing the complete RSS XML by default. If raw payload storage is required, set access and retention rules before migration.

`Company.identifier` is a stable symbol/registry key, but the observed RSS fields have no symbol. Do not create or match `Company` rows from title text alone. Use an authoritative, approved symbol/name mapping or a later reviewed entity-resolution process. Consider a separate article-company association if one filing may involve multiple companies. The current `FinancialArticle` model has no direct company relation. `SentimentPrediction` should be created only by the existing downstream analysis flow, not by ingestion.

## Proposed SQLAlchemy ingestion workflow

After written permissions and required schema changes:

1. Acquire an exclusive poll lease or otherwise prevent overlapping poll jobs for this source.
2. Fetch outside any database transaction, with approved frequency, timeout, and retry policy. Do not store response bytes.
3. Parse and validate the response in memory. Build normalized candidate objects while retaining source fields separately. Reject entries without a usable identity; count rather than silently dropping them.
4. Open a short SQLAlchemy session/transaction through the existing lazy database connection utilities. Resolve by `source_item_key` (or the currently supported unique `source_url` fallback). Insert missing rows; leave identical rows unchanged; route changed same-key values to an approved revision/update policy.
5. Set `source_name`, `source_url`, allowed text fields, `published_at` only if timezone is confirmed, and `collected_at`. Do not fabricate a `Company`, `Aspect`, or prediction from RSS text.
6. Commit the article changes and source poll-state advancement atomically. On any error, roll back both. Handle uniqueness races by rollback and re-querying in a fresh session.
7. Release the poll lease and emit content-free metrics. A replay of the same successful feed must yield zero additional article rows.

The current `get_engine()` is lazy and configured through application settings; production connector startup should use the existing session utilities rather than create an independent engine. The workflow remains a proposal and does not change `database/models.py`, application modules, or the database.

## Conditional implementation plan

Proceed only after NSE confirms in writing the endpoint, automated refresh limits, timestamp timezone/meaning, retention/backfill characteristics, and permitted storage, NLP/derived use, attribution, display, and redistribution scope.

1. Recheck the official RSS icon target and feed format; record a permitted, non-production fixture only if NSE permits retaining it for development.
2. Agree the timestamp and identity rules with NSE; verify link stability, revision behavior, and feed history window.
3. Review and apply a database migration for source identity, raw/normalized field separation, and source revisions/poll state as required by the confirmed rights.
4. Implement a small fetch/parser layer with bounded retries, stop-on-denial behavior, content-free logs, and no linked-document downloads.
5. Add idempotent transactional SQLAlchemy ingestion and cursor updates, then validate replay and failure recovery against permitted fixtures.
6. Enable a scheduler only at the approved interval; monitor freshness, HTTP/parse errors, and database outcomes. Keep NLP, display, and retention disabled unless each is explicitly covered by the permission.

Until those confirmations are obtained, retain the project at the read-only feasibility stage and do not deploy a production connector.
