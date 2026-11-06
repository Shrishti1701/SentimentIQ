# Stage 4A Contract Test Traceability Matrix

**Status:** Acceptance test specification with Stage 4A contract implementation
tests for the initial H-03, timestamp, alias, provenance, and supersession
components. This matrix remains a proposed acceptance specification unless an
individual ID is explicitly implemented in a test module.

## 1. Timestamp tests

| ID | Requirement | Required test |
|---|---|---|
| T-TS-01 | UTC canonical precision | `2026-11-04T06:29:36Z` canonicalizes to `.000000Z` |
| T-TS-02 | Microsecond loss | Six digits retain all digits |
| T-TS-03 | Unsupported precision | Seven source fractional digits reject UTC conversion |
| T-TS-04 | Source precision | Conversion validates source before Python datetime conversion |
| T-TS-05 | Unknown timezone | Unknown timezone yields null observation UTC |
| T-TS-06 | Naive timestamp | Naive source timestamp yields null UTC |
| T-TS-07 | Ingestion isolation | Ingestion time never populates publication or observation UTC |
| T-TS-08 | No current-time inference | Missing source publication remains unavailable |
| T-TS-09 | Explicit statement evidence | UTC requires exact source offset and quote |
| T-TS-10 | Publication derivation | Observation source publication copies only a verified UTC instant |
| T-TS-11 | Independent statement time | Statement instant requires evidence and timezone interpretation |
| T-TS-12 | Statement evidence type | Statement evidence uses `StatementTimeEvidenceV1`, never `ClauseReferenceV1` |
| T-TS-13 | Timestamp combination | Every timestamp source requires the documented UTC/inference/evidence combination |
| T-TS-14 | Publication evidence matrix | Each publication timezone/authority combination produces the matrix-allowed value or rejection |
| T-TS-15 | Claimed publication authority | A merely claimed timezone without approved authority yields null UTC and retains raw text |
| T-TS-16 | Publication precision | Sub-microsecond publication precision is rejected before datetime conversion |

## 2. Attribution role tests

| ID | Requirement | Required test |
|---|---|---|
| T-AR-01 | Subject role | A source subject with entity, company-resolution, and aspect evidence emits `subject` |
| T-AR-02 | Possessive role | Possessive entity evidence emits `possessive` without changing the relation semantics |
| T-AR-03 | Coordinated subject role | Coordinated entities emit separate links with `coordinated_subject` where supported |
| T-AR-04 | Unsupported role | An undeclared attribution role rejects rather than silently defaulting |

## 3. Link-attempt reason tests

| ID | Requirement | Required test |
|---|---|---|
| T-LR-01 | Relationship ambiguity | `relationship_ambiguous` requires ambiguous relationship status, matching roles, and source evidence |
| T-LR-02 | Insufficient relationship evidence | `relationship_evidence_insufficient` abstains without fabricated relationship evidence |
| T-LR-03 | Pronoun ambiguity | `pronoun_antecedent_ambiguous` requires source-supported pronoun ambiguity and does not select an identity |
| T-LR-04 | Entity ambiguity reason | `entity_registry_ambiguous` permits exactly its required entity registry candidates and rejects wrong namespaces |
| T-LR-05 | Resolved-company ambiguity reason | `resolved_company_ambiguous` permits exactly its required resolved-company candidates and rejects wrong namespaces |
| T-LR-06 | Combined ambiguity reasons | Combined entity/relationship and resolved-company/relationship reasons require both corresponding candidate sets and relationship evidence |
| T-LR-07 | Legacy reason compatibility | Legacy `insufficient_evidence` and `two_interpretations` remain valid without proposed reason substitution |
| T-LR-08 | Invalid status combination | Disallowed status, ambiguity basis, candidate fields, and reason combinations reject |

## 4. Competitor provenance tests

| ID | Requirement | Required test |
|---|---|---|
| T-CP-01 | Exactly two companies | One-company and three-company provenance reject |
| T-CP-02 | Supporting pairs | Multiple mentions/resolutions for one company accept |
| T-CP-03 | Duplicate pairs | Identical provenance triples reject |
| T-CP-04 | Resolution mapping | Mention/resolution/company mismatch reject |
| T-CP-05 | Deterministic order | Reversed processing order yields identical canonical tuple |
| T-CP-06 | Symmetric relation | Reversed company order yields the same relation ID |
| T-CP-07 | Relation type consistency | Occurrence type mismatch rejects |
| T-CP-08 | Duplicate evidence | Identical document, relation, and offsets deduplicate |
| T-CP-09 | Evidence correction | Quote correction preserves occurrence ID |
| T-CP-10 | Offset change | Changed offsets create a new occurrence ID |
| T-CP-11 | Contradictory evidence | No silent mutation of existing evidence |
| T-CP-12 | Cross-document identity | Different documents produce different relation IDs |
| T-CP-13 | Peer and competitor symmetry | Peer and competitor share symmetric canonical ordering but produce distinct relation payloads |
| T-CP-14 | Canonical relation match | Provenance rejects any company set other than the referenced relation's two IDs |
| T-CP-15 | Provenance source consistency | Mention, resolution, company, document, and evidence mismatch reject |
| T-CP-16 | Multiple supported pairs | Multiple valid mention-resolution pairs for either company remain deterministic |
| T-CP-17 | Mention document mismatch | Provenance mention from another document rejects |
| T-CP-18 | Resolution document mismatch | Provenance resolution from another document rejects |
| T-CP-19 | Resolution mention mismatch | Resolution not bound to the provenance mention rejects |
| T-CP-20 | Resolution company mismatch | Resolution company differs from provenance resolved company rejects |
| T-CP-21 | Relation endpoint mismatch | Provenance company differs from either canonical relation endpoint rejects |
| T-CP-22 | Triple document mismatch | Embedded provenance document differs from occurrence and relation rejects |
| T-CP-23 | Provenance evidence mismatch | Supporting evidence is not source-bound or not assigned to the correct company rejects |
| T-CP-24 | Evidence association identity | Each evidence association must repeat an exact provenance triple and a source-valid evidence span for that company |

## 5. Profit and profitability tests

| ID | Requirement | Required test |
|---|---|---|
| T-PF-01 | Profitability only | `"profitability improved"` emits profitability only |
| T-PF-02 | Profit only | `"profit increased"` emits profit only |
| T-PF-03 | Net profit | `"net profit increased"` emits net_profit only |
| T-PF-04 | Operating profit | `"operating profit increased"` emits operating_profit only |
| T-PF-05 | Independent parent-child | Two concepts emit together only with two source spans |
| T-PF-06 | No child inference | Parent terminology emits no child |
| T-PF-07 | Margin specificity | `"margin"` emits generic_margin only |
| T-PF-08 | Operating margin | Explicit operating margin emits operating_margin only |
| T-PF-09 | Gross margin | Explicit gross margin emits gross_margin only |
| T-PF-10 | Net margin | Explicit net margin emits net_margin only |
| T-PF-11 | Parent validation | Every parent has a direct declared child |
| T-PF-12 | Unknown aspect | `unknown_aspect` remains a leaf |
| T-PF-13 | Profitability structure | H-14 leaf status and financial_performance parent behavior validate independently |
| T-PF-14 | Profitability explicit evidence | H-15 emission occurs only for independently supported profitability wording |
| T-PF-15 | Profitability inference | Profitability evidence emits no profit, net_profit, or operating_profit unless separately evidenced |

## 6. Alias tests

| ID | Requirement | Required test |
|---|---|---|
| T-AL-01 | Valid status | Alias status belongs to exactly three allowed statuses |
| T-AL-02 | Canonical target | Every target code exists in taxonomy |
| T-AL-03 | Revenue growth | Rejected as a synthetic compound alias |
| T-AL-04 | Revenue/sales growth | Revenue and sales growth remain distinct |
| T-AL-05 | Context aliases | Context-dependent aliases emit no automatic result |
| T-AL-06 | EBIT | EBIT does not silently map to operating profit |
| T-AL-07 | Margin alias | Generic margin does not imply a subtype |
| T-AL-08 | Regulatory migration | Singular spelling migrates only by approved scope |
| T-AL-09 | Unknown alias | Unsupported alias preserves unknown source span |
| T-AL-10 | Rejected alias | A rejected alias never enters active canonical lookup |

## 7. Observation tests

| ID | Requirement | Required test |
|---|---|---|
| T-OB-01 | Exact offsets | Every clause slice equals its quote |
| T-OB-02 | Comparison/contrast | Both reference types may coexist when independently supported |
| T-OB-03 | Reference kind | Reference kind must match its containing field |
| T-OB-04 | Multiple clauses | Independent clauses create separate references or observations |
| T-OB-05 | Association validation | Every aspect/link ID belongs to the document |
| T-OB-06 | Evidence correction | Correction preserves observation ID |
| T-OB-07 | Semantic change | New observation semantics create a new ID |
| T-OB-08 | Association-only update | Link or aspect association does not change observation ID |
| T-OB-09 | Statement evidence offset | Statement-time quote and offsets exactly match its source field |
| T-OB-10 | Explicit statement timezone | Statement-time UTC is accepted only when H-09 is enabled and H-10 accepts its authority |

## 8. Identity tests

| ID | Requirement | Required test |
|---|---|---|
| T-ID-01 | Canonical JSON | Sorted keys, compact separators, UTF-8 |
| T-ID-02 | Hash | SHA-256 output and kind/version prefix |
| T-ID-03 | Cross-process | Independent factories produce identical IDs |
| T-ID-04 | Tuple ordering | Canonical tuples ignore input order |
| T-ID-05 | Null handling | Nullable values use JSON null |
| T-ID-06 | Empty collection | Empty collections use JSON arrays |
| T-ID-07 | Aspect correction | Evidence metadata correction preserves ID |
| T-ID-08 | Aspect source change | Source text change creates a new ID |
| T-ID-09 | Aspect offset change | Offset change creates a new ID |
| T-ID-10 | Link evidence | Evidence correction preserves link ID |
| T-ID-11 | Link observation | Observation association does not change link ID |
| T-ID-12 | Observation association | Associations do not change observation ID |
| T-ID-13 | Relation symmetry | Reversed pair order produces one relation ID |
| T-ID-14 | Supersession identity | Canonical supersession fields produce one hash and ID |
| T-ID-15 | Supersession cycle | Self-reference and direct/transitive cycles reject |
| T-ID-16 | Supersession duplicate | Identical supersessions deduplicate while conflicting definitions remain separate |
| T-ID-17 | Corrected evidence identity | Source correction of alignment or evidence does not create an independent observation; source/offset/semantic correction follows the applicable ID rule |
| T-ID-18 | Supersession conflict identity | The canonical pair of two supersession IDs produces one conflict record, and identical supersessions do not create a conflict |

## 9. Offset and slicing tests

| ID | Requirement | Required test |
|---|---|---|
| T-OF-01 | Contrast example | `"while Beta Limited reduced its debt"` is `[39,74)` |
| T-OF-02 | Revenue example | `"revenue"` is `[30,37)` in the contrast sentence |
| T-OF-03 | Coordinated Alpha | `"Alpha"` is `[0,5)` |
| T-OF-04 | Coordinated Beta | `"Beta"` is `[10,14)` |
| T-OF-05 | Coordinated relation | `"reported higher revenue"` is `[15,38)` |
| T-OF-06 | Coordinated links | Alpha and Beta produce separate links |
| T-OF-07 | Executable slices | Every quote slice equals its source substring |

## 10. Legacy compatibility tests

| ID | Requirement | Required test |
|---|---|---|
| T-LG-01 | Legacy constructors | Existing constructors instantiate unchanged |
| T-LG-02 | Legacy IDs | Existing ID vectors remain unchanged |
| T-LG-03 | Legacy records | Persisted records require no reinterpretation |
| T-LG-04 | Subject adapter | Legacy subject maps directly |
| T-LG-05 | Comparison adapter | Legacy comparison requires precise observation evidence |
| T-LG-06 | Competitor adapter | Legacy competitor maps to a separate relation |
| T-LG-07 | Legacy reasons | Existing reasons remain `insufficient_evidence` and `two_interpretations` |
| T-LG-08 | Stage 1–3 | Existing tests pass unchanged |
| T-LG-09 | Stage 4B | No security relation contract is produced |
| T-LG-10 | Comparison evidence mapping | Legacy comparison maps only with exact observation evidence; otherwise representation is unavailable |
| T-LG-11 | Competitor provenance mapping | Legacy competitor maps only when two verified endpoints and valid provenance exist |
| T-LG-12 | Missing legacy evidence | Legacy record remains unchanged and no fabricated Stage 4A evidence is created |

## 11. Link-attempt candidate identity tests

| ID | Requirement | Required test |
|---|---|---|
| T-LA-01 | Entity registry namespace | `candidate_entity_ids` accepts only entity registry IDs |
| T-LA-02 | Resolved-company namespace | `candidate_resolved_company_ids` accepts only `COMPANY:` IDs |
| T-LA-03 | Required fields | Both candidate tuple fields must be present; null and omitted fields reject |
| T-LA-04 | Empty semantics | Empty tuple means not applicable, never null and never omitted |
| T-LA-05 | Entity ambiguity | Entity ambiguity requires at least two valid `candidate_entity_ids` |
| T-LA-06 | Resolution ambiguity | Resolution ambiguity requires valid resolved-company candidates |
| T-LA-07 | Wrong namespace | Entity ID in resolved-company field and `COMPANY:` ID in entity field reject |
| T-LA-08 | Duplicate candidates | Duplicate candidate IDs reject |
| T-LA-09 | Canonical candidate order | Candidate tuples sort and serialize deterministically |

## 12. Unknown-aspect reason tests

| ID | Requirement | Required test |
|---|---|---|
| T-UA-01 | Unlisted concept positive and negative | Unlisted concept emits reason; listed concept does not |
| T-UA-02 | Ambiguous metric positive and negative | Supported competing metrics emit reason; single metric does not |
| T-UA-03 | Insufficient specificity positive and negative | Generic family emits reason; specific metric does not |
| T-UA-04 | Unsupported alias positive and negative | Disabled or rejected alias emits reason; related canonical phrase does not |
| T-UA-05 | Multi-aspect phrase positive and negative | Inseparable unknown compound emits `multi_aspect_phrase`; separable `"revenue and debt"` emits component aspects and no unknown aspect |
