# Stage 4A Contract Approval Package

**Status:** APPROVED AND FROZEN

This package consolidates the approved and frozen Stage 4A design. Contract
version `4A-1.0` was human-approved and frozen on `2026-11-05`. Implementation
may proceed without changing the recorded policy decisions.

## 1. Architecture boundary

Stage 4A is company-only. It includes:

- versioned aspect taxonomy and aliases;
- source-bound aspect mentions;
- company entity-aspect attribution;
- separate statement observations and evidence;
- company peer and competitor relationships.

Stage 4A does not include:

- security-level entity-aspect linking;
- entity resolution implementation;
- sentiment classification;
- aspect-aspect linking;
- live financial data integration;
- automatic real-world identity resolution.

## 2. Contracts

### 2.1 Attribution role

```python
AttributionRole = Literal[
    "subject",
    "possessive",
    "coordinated_subject",
]
```

`comparison` and `competitor` are not attribution roles. Comparison and contrast
belong to statement observations. Company-to-company competition belongs to the
separate competitor relation contract.

### 2.2 Aspect mention

```python
AspectMentionV1 = {
    "mention_id": str,
    "document_ref": str,
    "aspect_code": str,
    "label": str,
    "field": Literal["title", "body"],
    "start": int,
    "end": int,
    "surface_text": str,
    "evidence": EvidenceSpan,
    "taxonomy_version": str,
    "unknown_reason_code": UnknownAspectReasonCode | None,
    "extractor_version": str,
    "payload_version": Literal[1],
}
```

Validation invariants:

- `0 <= start < end`;
- `surface_text == source[field][start:end]`;
- evidence uses role `aspect`;
- evidence field, offsets, and quote match the mention;
- known aspect codes require a null unknown reason;
- unknown aspects require `aspect_code="unknown_aspect"` and a non-null
  approved reason;
- evidence spans use the Stage 1 source-offset convention.

### 2.3 Entity-aspect link

```python
EntityAspectLinkV1 = {
    "link_id": str,
    "document_ref": str,
    "entity_mention_id": str,
    "resolution_result_id": str,
    "resolved_company_id": str,
    "aspect_mention_id": str,
    "aspect_code": str,
    "taxonomy_version": str,
    "attribution_role": AttributionRole,
    "entity_evidence": EvidenceSpan,
    "aspect_evidence": EvidenceSpan,
    "relationship_evidence": EvidenceSpan,
    "observation_ids": tuple[str, ...],
    "linker_version": str,
    "payload_version": Literal[1],
}
```

Validation invariants:

- exactly one entity mention, resolution, company identity, and aspect mention;
- resolved company IDs begin with `COMPANY:`;
- resolution status is `resolved`;
- resolution selection matches the linked company;
- entity evidence has role `entity`;
- aspect evidence has role `aspect`;
- relationship evidence has role `relation`;
- observation IDs are sorted and unique;
- confidence is absent;
- security identities are not supported.

### 2.4 Entity-aspect link attempt

```python
EntityAspectLinkAttemptV1 = {
    "attempt_id": str,
    "document_ref": str,
    "entity_mention_id": str,
    "resolution_result_id": str | None,
    "aspect_mention_id": str | None,
    "status": Literal["ambiguous", "abstained"],
    "ambiguity_basis": Literal[
        "none",
        "entity",
        "resolved_company",
        "relationship",
        "entity_and_relationship",
        "resolved_company_and_relationship",
    ],
    "candidate_entity_ids": tuple[str, ...],
    "candidate_resolved_company_ids": tuple[str, ...],
    "candidate_attribution_roles": tuple[AttributionRole, ...],
    "relationship_evidence": EvidenceSpan | None,
    "reason_code": LegacyEntityLinkAttemptReason | ProposedEntityLinkAttemptReason,
    "linker_version": str,
    "payload_version": Literal[1],
}
```

Validation invariants:

- ambiguous status requires a non-`none` basis;
- abstained status uses `ambiguity_basis="none"`;
- entity ambiguity requires at least two `candidate_entity_ids`;
- resolved-company ambiguity requires at least two
  `candidate_resolved_company_ids`;
- relationship ambiguity requires at least two candidate roles;
- combined ambiguity requires both candidate sets;
- candidate IDs are distinct, sorted, and use `COMPANY:`;
- entity, aspect, and relationship evidence roles and source spans are valid;
- no ambiguous attempt may claim an established selected identity.
- `candidate_entity_ids` contains entity registry IDs, not resolved
  `COMPANY:` identifiers, when entity ambiguity is represented as unresolved
  registry candidates;
- both candidate fields are required contract fields and are serialized as
  tuples; JSON `null` is forbidden;
- absent and empty are distinct only in storage APIs that support field
  omission: omission is invalid in this contract; canonical serialization always
  emits each field as either a populated array or `[]`;
- an empty `candidate_entity_ids` is valid when the attempt is relationship-only
  and is invalid for `ambiguity_basis="entity"` or
  `"entity_and_relationship"`;
- an empty `candidate_resolved_company_ids` is valid when resolution is not
  ambiguous and is invalid when ambiguity is represented at resolved-company
  level;
- entity ambiguity must be validated using `candidate_entity_ids`; company
  resolution ambiguity must be validated using
  `candidate_resolved_company_ids`; relationship ambiguity must use
  `candidate_attribution_roles`;
- an attempt may use entity IDs or resolved company IDs as alternative
  representations of the entity ambiguity namespace, but must not populate
  both sets for one candidate unless each candidate namespace is independently
  justified;
- positive cases require all candidate values to resolve in the documented
  registry and to be sorted and unique;
- negative cases include duplicate IDs, an entity-registry ID in
  `candidate_resolved_company_ids`, a `COMPANY:` ID in
  `candidate_entity_ids`, unresolved registry IDs, and unresolved companies;
- wrong-namespace values invalidate the record rather than being normalized or
  renamed.
- resolved company identities are accepted only in
  `candidate_resolved_company_ids`, which is always present but is empty when
  no resolved-company ambiguity candidates apply;
- candidate fields must not mix entity registry IDs and `COMPANY:` IDs.

Attempt-state rules:

| status | ambiguity_basis | required candidates | empty candidates | permitted reasons | relationship evidence |
|---|---|---|---|---|---|
| `ambiguous` | `entity` | at least 2 `candidate_entity_ids` | resolved-company and roles empty | `entity_registry_ambiguous` | optional, same-source span if present |
| `ambiguous` | `resolved_company` | at least 2 `candidate_resolved_company_ids` | entity and roles empty | `resolved_company_ambiguous` | optional, same-source span if present |
| `ambiguous` | `relationship` | at least 2 candidate roles | entity and resolved-company empty | `relationship_ambiguous` | required |
| `ambiguous` | `entity_and_relationship` | at least 2 entity IDs and 2 roles | resolved-company empty | `relationship_ambiguous` or `entity_and_relationship_ambiguous` | required |
| `ambiguous` | `resolved_company_and_relationship` | at least 2 resolved-company IDs and 2 roles | entity empty | `relationship_ambiguous` or `resolved_company_and_relationship_ambiguous` | required |
| `abstained` | `none` | both candidate lists and roles empty | all empty | existing legacy reason or `relationship_evidence_insufficient`, `pronoun_antecedent_ambiguous` | none for evidence insufficiency; required for pronoun ambiguity when source text exists |

Complete H-03 ambiguity mapping is the deterministic union below. Each row is
an independently reachable state; no other basis/reason/status combination is
valid.

| State | ambiguity_basis | status | reason_code | candidate_entity_ids | candidate_resolved_company_ids | candidate_attribution_roles | relationship evidence |
|---|---|---|---|---|---|---|---|
| No ambiguity / insufficient evidence | `none` | `abstained` | legacy `insufficient_evidence`, legacy `two_interpretations`, `relationship_evidence_insufficient`, or `pronoun_antecedent_ambiguous` | `[]` required | `[]` required | `[]` or one role only | legacy status supplies no newly fabricated evidence; pronoun/insufficient relationship cases follow their documented evidence rules |
| Entity registry ambiguity | `entity` | `ambiguous` | `entity_registry_ambiguous` | >=2 entity-registry IDs, unique/sorted | `[]` required | `[]` required | forbidden unless separate evidentiary support exists |
| Resolved-company ambiguity | `resolved_company` | `ambiguous` | `resolved_company_ambiguous` | `[]` required | >=2 `COMPANY:` IDs, unique/sorted | `[]` required | forbidden |
| Relationship ambiguity | `relationship` | `ambiguous` | `relationship_ambiguous` | `[]` required | `[]` required | >=2 roles, unique/sorted | required |
| Entity registry + relationship ambiguity | `entity_and_relationship` | `ambiguous` | `entity_and_relationship_ambiguous` or `relationship_ambiguous` | >=2 entity-registry IDs | `[]` required | >=2 roles | required |
| Resolved-company + relationship ambiguity | `resolved_company_and_relationship` | `ambiguous` | `resolved_company_and_relationship_ambiguous` or `relationship_ambiguous` | `[]` required | >=2 `COMPANY:` IDs | >=2 roles | required |

Entity registry candidates use their entity-registry namespace and are validated
against the entity registry. Resolved-company candidates use the resolved
company namespace and must begin with `COMPANY:`. The fields are never aliases
for each other. Null and omitted candidate fields are invalid; canonical absence
is the empty tuple `[]`.

### 2.5 Clause reference

```python
ClauseReferenceV1 = {
    "field": Literal["title", "body"],
    "start": int,
    "end": int,
    "quote": str,
    "reference_kind": Literal["contrast", "comparison"],
    "alignment_ambiguous": bool,
}
```

Offsets are half-open. The quote must equal the exact source slice. Cross-field
clause spans are prohibited. Clause text must contain explicit comparative or
contrastive syntax; proximity alone is not a clause reference.

### 2.6 Statement observation timestamp

```python
SourcePublicationTimestampEvidenceV1 = {
    "document_ref": str,
    "field": Literal["title", "body"],
    "start": int,
    "end": int,
    "quote": str,
    "raw_timestamp": str,
}

SourcePublicationTimeV1 = {
    "utc_instant": str | None,
    "raw_timestamp": str | None,
    "timezone_status": Literal[
        "verified",
        "claimed",
        "unknown",
        "unavailable",
        "invalid",
    ],
    "timezone_identifier": str | None,
    "provenance": Literal["source_observed", "source_parsed", "unavailable"],
}
```

```python
IngestionTimeV1 = {
    "utc_instant": str,
    "source": Literal["connector", "database", "pipeline"],
    "provenance": Literal["observed"],
}
```

```python
ObservationTimestampV1 = {
    "utc_instant": str | None,
    "observation_source": Literal[
        "source_publication",
        "explicit_statement_time",
        "unavailable",
    ],
    "source_publication_time": SourcePublicationTimeV1 | None,
    "source_publication_evidence": SourcePublicationTimestampEvidenceV1 | None,
    "statement_time_evidence": StatementTimeEvidenceV1 | None,
    "inference_method": Literal[
        "none",
        "verified_timezone_parse",
        "explicit_statement_timezone_parse",
    ] | None,
}
```

```python
StatementTimeEvidenceV1 = {
    "document_ref": str,
    "field": Literal["title", "body"],
    "start": int,
    "end": int,
    "quote": str,
    "timezone_identifier": str | None,
    "timezone_status": Literal[
        "verified",
        "claimed",
        "unknown",
        "unavailable",
        "invalid",
    ],
    "alignment_ambiguous": bool,
}
```

Timestamp invariants:

- UTC strings use `YYYY-MM-DDTHH:mm:ss.ffffffZ`;
- values with source precision greater than six fractional digits are rejected;
- original sub-microsecond precision is never silently truncated;
- no naive UTC instant is permitted;
- unknown source timezone produces no UTC instant;
- ingestion time remains pipeline metadata only;
- ingestion time never populates source publication or observation UTC;
- wall-clock inference is prohibited;
- explicit statement time requires exact source evidence and approved timezone
  semantics.
- source publication raw evidence remains present when timezone conversion is
  rejected;
- `SourcePublicationTimestampEvidenceV1` is required whenever
  `source_publication_time` is non-null;
- UTC conversion may use only `verified_timezone_parse` for a verified timezone
  or an H-10-approved claimed timezone authority; unapproved claimed, unknown,
  unavailable, invalid, naive, and over-precision timestamps remain null.
- `StatementTimeEvidenceV1` is source-bound temporal evidence; it is not a
  `ClauseReferenceV1`.
- when `observation_source="explicit_statement_time"`:
  `utc_instant` must be non-null and `statement_time_evidence` must be present
  and non-null;
- when `observation_source="source_publication"`:
  `utc_instant` must equal the verified or approved source publication instant;
  statement-time evidence must be absent;
- when `observation_source="unavailable"`:
  `utc_instant`, statement-time evidence, source publication time, and
  timezone-dependent inference must all be absent or null, and
  `inference_method` must be `"none"`;
- the valid inference-method combinations are:
  publication plus verified timezone => `"verified_timezone_parse"`;
  explicit statement plus approved timezone interpretation =>
  `"explicit_statement_timezone_parse"`;
  unavailable => `"none"`;
- ingestion timestamps never participate in these combinations.

Publication-time evidence matrix:

| source publication data | timezone status / authority | Source evidence | UTC conversion | Result |
|---|---|---|---|---|
| Absent | unavailable | none | rejected | `utc_instant=null`; no fallback |
| `source_publication_time` present | verified source authority | one `SourcePublicationTimestampEvidenceV1` span whose quote equals the preserved raw timestamp | permitted | `utc_instant` equals canonical converted instant |
| Raw timestamp present; timezone absent | unknown / unavailable | exact publication field or timestamp evidence | rejected | timestamp preserved raw; UTC null |
| Raw timestamp present; timezone merely claimed | claimed without approved authority | exact timestamp text | rejected | raw text retained; UTC null |
| Raw timestamp present; timezone claimed | claimed with approved authority | exact timestamp text and timezone evidence | accepted | UTC converted |
| Raw timestamp present; timezone verified | verified authority | exact timestamp text | accepted | UTC converted |
| Raw timestamp present; timezone invalid | invalid | exact timestamp text | rejected | raw text retained; UTC null |
| Timestamp precision > 6 fractional digits | any | exact timestamp text | rejected | UTC null |
| Naive timestamp plus assumed timezone | unknown | exact text only | rejected | UTC null |
| Explicit statement time with source-bound evidence | claimed or verified under approved H-10 authority | exact statement-time evidence | accepted only when H-09 permits it | UTC converted |
| Ingestion timestamp present | any | no publication evidence | rejected as publication/observation time | publication and observation UTC remain null |

`source_publication_time` is populated from publication evidence only. It may
be null independently of the observation record. `utc_instant` is permitted
only for a source publication row that passed timezone authority and precision
validation. The canonical raw timestamp remains unchanged.

### 2.7 Statement observation

```python
StatementObservationV1 = {
    "observation_id": str,
    "document_ref": str,
    "source_field": Literal["title", "body"],
    "start": int,
    "end": int,
    "evidence": EvidenceSpan,
    "observation_type": Literal[
        "statement",
        "comparison",
        "contrast",
        "conditional",
    ],
    "negation": bool,
    "modality": Literal[
        "none",
        "possibility",
        "necessity",
        "expectation",
        "reported",
    ],
    "uncertainty": Literal["none", "explicit", "modal"],
    "temporal_reference": Literal[
        "past",
        "present",
        "future",
        "unspecified",
    ],
    "forward_looking": bool,
    "conditionality": Literal["none", "conditional"],
    "contrast_references": tuple[ClauseReferenceV1, ...],
    "comparison_references": tuple[ClauseReferenceV1, ...],
    "observation_timestamp": ObservationTimestampV1 | None,
    "aspect_mention_ids": tuple[str, ...],
    "link_ids": tuple[str, ...],
    "observation_version": str,
    "payload_version": Literal[1],
}
```

Multiple contrast or comparison clauses may be represented as separate
references in one observation only when they describe the same observation.
Multiple independent observations remain separate records.

Cross-record consistency requires:

- every aspect mention and entity-aspect link referenced by an observation has
  the same `document_ref`;
- every link's `observation_ids` contains the observation when referenced by
  that link and no observation ID may be invented without the corresponding
  cross-reference;
- every aspect mention belongs to the same source document and within the same
  document field as the observation or link evidence that cites it;
- resolution, entity mention, resolved company, and aspect evidence referenced
  by a link must describe the same document and agree with their source records;
- source offsets in evidence must be validated against `source[field][start:end]`;
- document references in evidence, mentions, resolutions, and links may not be
  treated as interchangeable.

### 2.8 Competitor/peer relation

```python
CompanyCompetitorProvenanceV1 = {
    "document_ref": str,
    "resolved_company_id": str,
    "company_mention_id": str,
    "resolution_result_id": str,
}
```

```python
CompanyCompetitorEvidenceAssociationV1 = {
    "resolved_company_id": str,
    "company_mention_id": str,
    "resolution_result_id": str,
    "evidence": EvidenceSpan,
}
```

```python
CompanyCompetitorRelationV1 = {
    "relation_id": str,
    "document_ref": str,
    "left_company_id": str,
    "right_company_id": str,
    "relation_type": Literal["peer", "competitor"],
    "relation_version": str,
    "payload_version": Literal[1],
}
```

```python
CompanyCompetitorRelationOccurrenceV1 = {
    "occurrence_id": str,
    "relation_id": str,
    "document_ref": str,
    "source_field": Literal["title", "body"],
    "start": int,
    "end": int,
    "quote": str,
    "relation_type": Literal["peer", "competitor"],
    "provenance": tuple[CompanyCompetitorProvenanceV1, ...],
    "evidence_associations": tuple[CompanyCompetitorEvidenceAssociationV1, ...],
    "occurrence_version": str,
    "payload_version": Literal[1],
}
```

The symmetric relation identity orders company IDs lexicographically. Provenance
is sorted by
`(document_ref, resolved_company_id, company_mention_id, resolution_result_id)`.

Occurrence validation requires:

- exactly two distinct resolved company IDs across provenance;
- those two resolved company IDs must be exactly
  `{left_company_id, right_company_id}` from the referenced canonical relation;
- provenance mentions and resolution results must be matched one-to-one in
  the same provenance triple;
- every provenance `company_mention_id` resolves through the corresponding
  `resolution_result_id` to the same `resolved_company_id`;
- every provenance `document_ref`, if present, must equal the relation and
  occurrence document; provenance is embedded in a document-scoped occurrence,
  so mismatched or cross-document references are invalid;
- each `evidence_associations` row must repeat the exact company, mention, and
  resolution triple represented in `provenance`; evidence association therefore
  cannot independently pair a company with an unrelated mention or resolution;
- every evidence association is duplicate-free and source-bound to the
  occurrence document; its span field and offset quote must match the source;
- evidence associations are canonical-sorted by
  `(resolved_company_id, company_mention_id, resolution_result_id, evidence.field,
  evidence.start, evidence.end, evidence.quote)`;
- `evidence_spans` is not a standalone occurrence field;
- at least one evidence provenance pair for each company;
- no duplicate provenance triples;
- matching resolved IDs, mentions, and resolutions;
- occurrence relation type equals relation relation type;
- the relation and occurrence share one document;
- exact source quotes and offsets.

## 3. Reason registries

### 3.1 Unknown aspect reasons — proposed, unapproved

```python
UnknownAspectReasonCode = Literal[
    "unlisted_taxonomy_concept",
    "ambiguous_metric",
    "insufficient_specificity",
    "unsupported_alias",
    "multi_aspect_phrase",
]
```

Unknown source spans must be preserved.

Separating `"revenue and debt"` requires separate aspect spans when each
concept is extractable. A separable multi-aspect source span must not be
discarded or collapsed into one unknown concept.

Unknown-aspect reason decision table:

| Code | Trigger; must not trigger | Required evidence | Expected output | Precedence |
|---|---|---|---|---|
| `unlisted_taxonomy_concept` | Trigger: exact source concept not represented by any taxonomy leaf or approved parent. Must not trigger for a listed concept or unsupported alias of a listed concept. | Exact span and document field. | Preserve span as `unknown_aspect` with this reason. | After exact taxonomy lookup and alias lookup, before unsupported_alias. |
| `ambiguous_metric` | Trigger: two or more conflicting metric interpretations are semantically supportable from the same span. Must not trigger when only one listed metric is supported. | Span plus both candidate interpretations or their source evidence. | Preserve span as unknown and report candidates without selecting one. | Highest for genuinely ambiguous semantic metrics. |
| `insufficient_specificity` | Trigger: source wording is too generic to select a particular metric but names a valid metric family. Must not trigger for a specific named metric or ambiguous mapping with multiple concrete candidates. | Exact generic span. | Preserve span with reason and no inferred child code. | After ambiguous_metric; before unlisted. |
| `unsupported_alias` | Trigger: source wording is plausibly an alias but alias activation is absent, rejected, or context-dependent. Must not trigger when the alias is not semantically related to a taxonomy concept. | Span plus reference alias entry. | Preserve span as unknown; do not activate alias. | After ambiguous_metric and insufficient_specificity. |
| `multi_aspect_phrase` | Trigger only when one inseparable source span requires unknown classification even though a separable-component analysis has been exhausted. Must not trigger for successfully separated concepts and must not trigger for one valid aspect represented by a compound or alias. | Exact compound span, evidence for the attempted component spans, and separation outcome. | Emit no unknown record for successful separation; emit separate component mentions plus optional audit evidence for the compound span. If inseparable and no single aspect fits, preserve the span as unknown with this reason. | After exact taxonomy lookup, alias lookup, ambiguity and specificity checks, and successful compound-span separation; lowest precedence. |

Positive/negative acceptance examples:

- `unlisted_taxonomy_concept`: positive `"cloud subscriber metric"` when absent
  from taxonomy; negative `"revenue"` is not unknown and must match
  `revenue`.
- `ambiguous_metric`: positive `"return"` when source supports both return on
  assets and return on equity; negative `"net profit"` when no second metric
  interpretation is supported.
- `insufficient_specificity`: positive `"margin"` remains generic only if the
  generic-margin policy is not approved; negative `"operating margin"`
  is specific.
- `unsupported_alias`: positive `"EBITDA margin"` while the alias remains
  disabled; negative an exact listed canonical `operating_margin` term.
- `multi_aspect_phrase`: positive an inseparable unknown phrase that has no
  valid independent aspect mapping; negative `"revenue and debt"` when both
  component spans are successfully extracted (no unknown mention is emitted).

### 3.2 Entity-link attempt reasons — existing

Existing repository callsites establish:

```python
LegacyEntityLinkAttemptReason = Literal[
    "insufficient_evidence",
    "two_interpretations",
]
```

These reason values are preserved. No unknown-aspect reason is added to this
registry.

### 3.3 Proposed Stage 4A link reasons — human approval required

```python
ProposedEntityLinkAttemptReason = Literal[
    "relationship_ambiguous",
    "relationship_evidence_insufficient",
    "pronoun_antecedent_ambiguous",
    "entity_registry_ambiguous",
    "resolved_company_ambiguous",
    "entity_and_relationship_ambiguous",
    "resolved_company_and_relationship_ambiguous",
]
```

## 4. Taxonomy proposal

Version: `aspect-taxonomy-v2`.

Explicit parent-to-child relationships:

```python
ASPECT_PARENT_CHILDREN_V2 = {
    "financial_performance": ("revenue", "sales_growth", "profitability", "profit"),
    "profit": ("net_profit", "operating_profit"),
    "generic_margin": (
        "profit_margin",
        "operating_margin",
        "gross_margin",
        "net_margin",
    ),
    "capital_structure": ("debt", "equity", "cash_flow"),
    "corporate_actions": ("repayment", "refinancing"),
    "operating_costs": ("operating_expenses", "employee_expenses"),
    "operating_expenses": ("employee_expenses",),
    "corporate_development": (
        "business_growth",
        "management",
        "management_change",
    ),
    "regulatory": ("regulatory_developments",),
}
```

The hierarchy above is normative. No parent/child relationship is inferred
from names, ordering, or a shared namespace. Parent concepts are not emitted
from child terminology and child concepts are not emitted from parent
terminology. Under this proposal `profitability` has been declared a leaf; its
independent structural classification remains subject to H-14, its emission
policy remains subject to H-15, and its inference policy remains subject to
H-16.

### 4.1 Definitions and kinds

```text
financial_performance       parent
revenue                     leaf
sales_growth                leaf
profitability               leaf
profit                      parent
net_profit                  leaf
operating_profit            leaf
generic_margin              parent
profit_margin               leaf
operating_margin            leaf
gross_margin                leaf
net_margin                   leaf

capital_structure           parent
debt                        leaf
equity                      leaf
cash_flow                   leaf

corporate_actions           parent
repayment                   leaf
refinancing                 leaf

operating_costs             parent
operating_expenses          parent
employee_expenses           leaf

corporate_development       parent
business_growth             leaf
management                  leaf
management_change           leaf

regulatory                  parent
regulatory_developments     leaf

unknown_aspect              leaf
```

Every parent must have at least one declared direct child. `unknown_aspect` is
always a leaf.

### 4.2 Profit emission

- `profitability` describes general profitability.
- It does not imply `profit`, `net_profit`, or `operating_profit`.
- `profit` is explicit general profit and does not imply either child.
- `net_profit` and `operating_profit` require explicit source evidence.
- Parent and child concepts may be emitted together only with separate source
  evidence supporting both.

### 4.3 Alias registry

Allowed statuses are exactly:

- `approved`;
- `context_dependent`;
- `rejected`.

Context-dependent aliases are disabled until a controlling policy decision is
approved. They shall not be enabled by ordinary fuzzy or substring matching.

| Alias | Canonical code | Status | Migration scope |
|---|---|---|---|
| profit | profit | approved | none |
| profitability | profitability | approved | none |
| net profit | net_profit | approved | none |
| profit after tax | net_profit | context_dependent | none |
| PAT | net_profit | context_dependent | abbreviation |
| operating profit | operating_profit | approved | none |
| operating income | operating_profit | context_dependent | jurisdiction |
| EBIT | operating_profit | rejected | none |
| margin | generic_margin | approved | none |
| profit margin | profit_margin | approved | none |
| operating margin | operating_margin | approved | none |
| gross margin | gross_margin | approved | none |
| net margin | net_margin | approved | none |
| EBITDA margin | generic_margin | context_dependent | accounting |
| revenue | revenue | approved | none |
| sales | revenue | context_dependent | accounting |
| turnover | revenue | context_dependent | jurisdiction |
| top line | revenue | rejected | none |
| sales growth | sales_growth | approved | none |
| growth in sales | sales_growth | approved | none |
| sales grew | sales_growth | approved | none |
| revenue growth | none | rejected | no alias mapping |
| growth | business_growth | rejected | none |
| debt | debt | approved | none |
| borrowings | debt | context_dependent | accounting |
| debt repayment | repayment | approved | none |
| repaid debt | repayment | approved | none |
| debt refinancing | refinancing | approved | none |
| refinancing | refinancing | approved | none |
| operating expenses | operating_expenses | approved | none |
| operating costs | operating_expenses | context_dependent | accounting |
| employee expenses | employee_expenses | approved | none |
| employee costs | employee_expenses | context_dependent | accounting |
| staff costs | employee_expenses | context_dependent | accounting |
| payroll | employee_expenses | context_dependent | accounting |
| management | management | approved | none |
| management change | management_change | approved | none |
| regulatory developments | regulatory_developments | approved | legacy canonical |
| regulatory development | regulatory_developments | approved | legacy name migration |
| business growth | business_growth | approved | none |
| unknown aliases | unknown_aspect | rejected | preserve as unknown |

## 5. Deterministic identity

Canonical serialization:

```text
json.dumps(
    payload,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
    allow_nan=False,
)
```

Hash representation:

- canonical input is the UTF-8 encoding of the canonical compact JSON string;
- SHA-256 output is the lowercase 64-character hexadecimal digest;
- object identity is `<kind>:v1:<digest>`;
- dictionary keys are sorted lexicographically by `sort_keys=True`;
- tuple values are sorted only when the payload contract declares them as a
  set; ordered tuple fields retain their declared order;
- provenance and candidate tuples use their documented canonical tuple keys;
- duplicate canonical values are rejected rather than silently deduplicated.

Rules:

- tuples are arrays;
- sorted collections are canonical;
- absent values are JSON `null`;
- empty collections are JSON `[]`;
- evidence objects are excluded unless explicitly designated as identity data;
- payload schema changes require a payload version;
- semantic version changes require a corresponding extractor, taxonomy, linker,
  observation, or relation version.

### 5.1 Aspect identity payload

```json
{
  "document_ref": "doc",
  "field": "body",
  "start": 31,
  "end": 38,
  "surface_text": "revenue",
  "aspect_code": "revenue",
  "taxonomy_version": "aspect-taxonomy-v2",
  "unknown_reason_code": null,
  "extractor_version": "aspect-v1",
  "payload_version": 1
}
```

Evidence metadata may be corrected without changing identity. Source text
changes, offset changes, taxonomy changes, semantic aspect changes, or unknown
reason changes require a new identity.

### 5.2 Link identity payload

```json
{
  "document_ref": "doc",
  "entity_mention_id": "mention:v1:digest",
  "resolution_result_id": "resolution:v1:digest",
  "resolved_company_id": "COMPANY:SYN-001",
  "aspect_mention_id": "aspect-mention:v1:digest",
  "aspect_code": "revenue",
  "taxonomy_version": "aspect-taxonomy-v2",
  "attribution_role": "subject",
  "linker_version": "linker-v1",
  "payload_version": 1
}
```

Evidence correction preserves identity. Observation association changes do not
change link identity.

### 5.3 Attempt identity payload

```json
{
  "document_ref": "doc",
  "entity_mention_id": "mention:v1:digest",
  "resolution_result_id": null,
  "aspect_mention_id": "aspect-mention:v1:digest",
  "status": "ambiguous",
  "ambiguity_basis": "relationship",
  "candidate_entity_ids": [],
  "candidate_resolved_company_ids": [],
  "candidate_attribution_roles": ["possessive", "subject"],
  "reason_code": "relationship_ambiguous",
  "linker_version": "linker-v1",
  "payload_version": 1
}
```

### 5.4 Observation identity payload

```json
{
  "document_ref": "doc",
  "source_field": "body",
  "start": 39,
  "end": 74,
  "observation_type": "contrast",
  "negation": false,
  "modality": "none",
  "uncertainty": "none",
  "temporal_reference": "unspecified",
  "forward_looking": false,
  "conditionality": "none",
  "observation_version": "observation-v1",
  "payload_version": 1
}
```

Evidence, references, timestamp, aspect associations, and link associations are
excluded.

### 5.5 Competitor relation identity payload

```json
{
  "document_ref": "doc",
  "left_company_id": "COMPANY:SYN-001",
  "right_company_id": "COMPANY:SYN-002",
  "relation_type": "competitor",
  "relation_version": "company-relation-v1",
  "payload_version": 1
}
```

### 5.6 Competitor occurrence identity payload

```json
{
  "document_ref": "doc",
  "relation_id": "company-relation:v1:digest",
  "source_field": "body",
  "start": 12,
  "end": 45,
  "relation_type": "competitor",
  "occurrence_version": "company-relation-occurrence-v1",
  "payload_version": 1
}
```

## 6. Human policy decisions

Approval record for contract version `4A-1.0`:

- Approval date: `2026-11-05`
- Approver: human user
- Decision status: H-01 through H-16 human-approved
- Contract freeze date: `2026-11-05`
- Contract freeze version: `4A-1.0`

The following remain human decisions. None may be silently accepted:

- approval of proposed unknown-aspect reason codes;
- approval of proposed Stage 4A link attempt reason codes;
- approval of `profit` as an explicit parent rather than an umbrella alias;
- approval of `aspect-taxonomy-v2`;
- approval of every context-dependent alias;
- approval of explicit statement-time parsing;
- approval of timezone authorities and `claimed` timestamp handling;
- approval of a peer relation as distinct from competitor;
- approval of legacy `"comparison"` adaptation behavior;
- approval of legacy `"competitor"` adaptation behavior;
- approval of contradictory-evidence supersession policy;
- approval of UTC precision and source precision rejection.
- H-14: structural classification of `profitability` (proposed: leaf under parent `financial_performance`);
- H-15: profitability emission evidence (proposed: independent explicit profitability terminology);
- H-16: profitability inference policy (proposed: no inference of profit, net_profit, or operating_profit).

H-09 and H-10 are independent but ordered decisions: H-09 controls whether
explicit statement-time extraction exists; H-10 controls the timezone authority
and provenance that may make a reported time convertible. Explicit statement
time therefore remains unavailable while H-09 is rejected, even if H-10 permits
a timezone authority. Publication timezone conversion depends on H-10 only.

### H-13 evidence lifecycle resolution

Source correction means correction of a document's existing evidence metadata,
quoted text, alignment, offsets, or resolution provenance without changing the
underlying reported fact. Source corrections preserve the affected record
identity unless source text, offsets, semantic classification, or resolution
selection changes as defined by that record's identity contract.

An independently published contradictory observation is a separate source
document or time-distinct report. It must not mutate the earlier observation.
Its supersession reference must name both records explicitly:

```python
EvidenceSupersessionV1 = {
    "supersession_id": str,
    "superseded_observation_id": str,
    "replacement_observation_id": str,
    "document_ref": str,
    "source_field": Literal["title", "body"],
    "start": int,
    "end": int,
    "quote": str,
    "supersession_reason": str,
}
```

```python
EvidenceSupersessionConflictV1 = {
    "conflict_id": str,
    "first_supersession_id": str,
    "second_supersession_id": str,
    "document_ref": str,
    "detected_at": str,
    "conflict_reason": Literal[
        "different_successors_for_same_predecessor",
        "conflicting_evidence_definitions",
    ],
    "resolution_status": Literal["unresolved", "under_review"],
}
```

Its canonical identity payload is:

```json
{
  "superseded_observation_id": "observation:v1:digest",
  "replacement_observation_id": "observation:v1:digest",
  "document_ref": "doc",
  "source_field": "body",
  "start": 10,
  "end": 30,
  "supersession_reason": "independent_contradiction",
  "payload_version": 1
}
```

Canonical serialization uses the contract-wide compact JSON, sorted-key,
UTF-8, SHA-256, and `evidence-supersession:v1:<digest>` rules. Hash version 1
includes predecessor, successor, document, evidence offsets, and canonical
reason; it excludes mutable evidence objects and timestamps.

Validation requires both referenced observations to exist. Their `document_ref`
values must equal the supersession document or independently represent two
different documents. The evidence span is half-open and `source[field][start:end]`
must equal `quote`. Predecessor and successor must be different IDs. Direct
cycles and transitive cycles are forbidden. Duplicate canonical supersessions
are deduplicated; contradictory definitions are retained, marked conflict, and
never merged automatically.

Conflicting supersessions produce `EvidenceSupersessionConflictV1`, not a
new merged supersession. Conflict IDs are the lexicographic canonical pair of
the two supersession IDs, with input order ignored. Detection state does not
modify either predecessor or successor. Both conflicting records remain
immutable, while only the conflict record's `resolution_status` may transition
from `unresolved` to `under_review`; approval or closure requires an explicit
human record and may not infer a winner.

Predecessors and successors are immutable once referenced. A source correction
of evidence metadata or alignment does not create a supersession. If correction
changes source text, offsets, semantics, or source resolution, the corrected
record receives its own identity rule; an observation semantic change creates a
new observation and occurrence-specific evidence creates a new evidence ID or
occurrence ID as applicable. It does not replace the independent contradictory
observation unless a human-approved supersession explicitly records that
relationship.

Before immutability is applied, the superseded observation remains retrievable.
No processing order determines the replacement record; contradictory evidence
is represented by separate observations linked through explicit supersession
references.

## 7. Compatibility guarantees

Legacy adapter mapping:

| Legacy record | Legacy source field | Destination contract | Transformation | Missing or ambiguous handling | Identity |
|---|---|---|---|---|---|
| Link/attempt | `relationship="comparison"` | `StatementObservationV1` | Preserve comparison semantics and source span; emit independent aspect/entity links only when each association is supported. | Missing precise clause evidence or ambiguous observation type => preserve legacy record and mark Stage 4A unavailable for review. | Legacy ID unchanged; no synthetic Stage 4A ID without supported evidence |
| Link/attempt | `relationship="competitor"` | `CompanyCompetitorRelationV1` + occurrence | Map only when exactly two resolved endpoints and source provenance are present. | Missing mention/resolution/evidence => preserve legacy record; create no relation or occurrence. | Legacy ID unchanged; canonical relation created only from verified company endpoints |
| Link/attempt | `relationship="subject"` | `EntityAspectLinkV1.attribution_role="subject"` | Direct semantic mapping only when entity, resolution, aspect, and evidence remain valid. | Missing required evidence => preserve legacy record; stage unavailable. | Legacy ID retained as provenance reference |
| Existing attempt | reason `insufficient_evidence`, `two_interpretations` | Existing legacy reason unchanged | No proposed Stage 4A reason is substituted. | Ambiguous fields remain legacy data. | Legacy attempt ID unchanged |

- Existing legacy Python constructors remain unchanged.
- Existing legacy deterministic payloads and IDs remain unchanged.
- Existing persisted legacy records remain unchanged.
- Legacy adapter output must reference original records and IDs.
- Legacy `"subject"` maps only to subject attribution.
- Legacy `"comparison"` maps to observations and independent links only where
  source evidence supports both.
- Legacy `"competitor"` maps to a separate company relation, not an aspect link.
- Legacy `"insufficient_evidence"` and `"two_interpretations"` remain valid.
- No historical record is silently reinterpreted or retroactively aliased.
- Stage 1 source offsets, normalization, and alignment contracts are unchanged.
- Stage 2 entity extraction contracts are unchanged.
- Stage 3 resolution contracts are unchanged.
- Stage 4B security linking remains outside Stage 4A.
