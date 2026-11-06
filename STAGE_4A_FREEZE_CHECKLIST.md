# Stage 4A Contract Freeze Checklist

**Status:** APPROVED AND FROZEN

Signing this checklist constitutes contract approval only. It does not implement
Stage 4A or modify repository contracts.

## A. Human approval decisions

Complete every item with named approver, date, and decision.

| ID | Decision | Approver | Date | Status |
|---|---|---|---|---|
| H-01 | Approve attribution roles: subject, possessive, coordinated_subject | human approver | 2026-11-05 | human-approved |
| H-02 | Approve unknown-aspect reason registry | human approver | 2026-11-05 | human-approved |
| H-03 | Approve proposed Stage 4A link reason registry | human approver | 2026-11-05 | human-approved |
| H-04 | Approve the aspect-taxonomy-v2 structural hierarchy other than separately decided profitability policy | human approver | 2026-11-05 | human-approved |
| H-05 | Approve profit parent/child hierarchy and profit emission policy, excluding profitability decisions | human approver | 2026-11-05 | human-approved |
| H-06 | Approve generic margin and child margin hierarchy | human approver | 2026-11-05 | human-approved |
| H-07 | Approve peer versus competitor relation semantics | human approver | 2026-11-05 | human-approved |
| H-08 | Approve UTC canonical precision policy | human approver | 2026-11-05 | human-approved |
| H-09 | Approve explicit statement-time parsing policy | human approver | 2026-11-05 | human-approved |
| H-10 | Approve timezone provenance policy | human approver | 2026-11-05 | human-approved |
| H-11 | Approve context-dependent alias activation policy | human approver | 2026-11-05 | human-approved |
| H-12 | Approve legacy comparison and competitor adapters | human approver | 2026-11-05 | human-approved |
| H-13 | Approve contradictory evidence supersession policy | human approver | 2026-11-05 | human-approved |
| H-14 | Approve profitability structural classification as a leaf under financial_performance | human approver | 2026-11-05 | human-approved |
| H-15 | Approve profitability emission evidence policy | human approver | 2026-11-05 | human-approved |
| H-16 | Approve profitability non-inference of profit, net_profit, and operating_profit | human approver | 2026-11-05 | human-approved |

### Human approval record

All H-01 through H-16 are approved by the human approver on `2026-11-05`.
The approval source is the explicit user authorization directing execution of
the recommended Stage 4A defaults. Status is recorded as `human-approved`
below.

| ID | Approval status |
|---|---|
| H-01 | human-approved |
| H-02 | human-approved |
| H-03 | human-approved; H-03 matrix closed before freeze |
| H-04 | human-approved |
| H-05 | human-approved |
| H-06 | human-approved |
| H-07 | human-approved |
| H-08 | human-approved |
| H-09 | human-approved |
| H-10 | human-approved |
| H-11 | human-approved |
| H-12 | human-approved |
| H-13 | human-approved |
| H-14 | human-approved |
| H-15 | human-approved |
| H-16 | human-approved |

## B. Contract requirements

- [ ] Four relationship dimensions are independent contracts.
- [ ] Exactly one successful link has one mention, one resolved company, and one aspect.
- [ ] Coordinated entities emit separate links.
- [ ] Unknown aspect spans are preserved.
- [ ] Relationship attempts remain separate from unknown aspects.
- [ ] Source publication and ingestion timestamps cannot be confused.
- [ ] Observation UTC is independently recorded when supported.
- [ ] Current-time inference is prohibited.
- [ ] Competitor provenance records exactly two distinct companies.
- [ ] Competitor provenance matches the exact two canonical relation company IDs.
- [ ] Provenance mentions and resolutions match their referenced company and document.
- [ ] Provenance evidence spans are source-valid for the same occurrence document.
- [ ] Every provenance evidence association repeats its exact mention-resolution-company triple.
- [ ] Multiple supporting mention-resolution pairs remain structured.
- [ ] Peer and competitor are distinct.
- [ ] All parent definitions have at least one direct child.
- [ ] `profitability` does not infer profit or child metrics.
- [ ] Every alias resolves to a declared canonical code.
- [ ] Context-dependent aliases remain disabled.
- [ ] Link identity excludes observation associations.
- [ ] Evidence correction does not change entity-aspect link identity.
- [ ] Source text or offset changes create a new aspect mention identity.
- [ ] UTC serialization uses six fractional digits and `Z`.
- [ ] Explicit statement time uses separate source-bound statement-time evidence.
- [ ] Timestamp source, UTC instant, inference method, and evidence combinations are valid.
- [ ] Candidate entity IDs and resolved company IDs use distinct registries and namespaces.
- [x] Candidate tuples are always present, canonical, unique, correctly empty, and non-null.
- [ ] Source corrections remain immutable except for their explicitly defined correction identities.
- [ ] Contradictory independently published observations remain separate and use explicit supersession references.
- [ ] Legacy constructors, IDs, and records remain unchanged.
- [ ] Stage 4B remains deferred.

## C. Context-dependent aliases disabled for activation

The following aliases must remain disabled unless separately activated through
the human approval process:

- profit after tax;
- PAT;
- operating income;
- EBITDA margin;
- sales;
- turnover;
- borrowings;
- operating costs;
- employee costs;
- staff costs;
- payroll;
- explicit statement or accounting aliases requiring jurisdictional evidence.

## D. Compatibility verification

- [ ] Stage 1 normalization/alignment tests pass unchanged.
- [ ] Stage 2 extraction tests pass unchanged.
- [ ] Stage 3 resolution tests pass unchanged.
- [ ] Legacy entity-contract constructors instantiate unchanged.
- [ ] Legacy deterministic ID vectors remain unchanged.
- [ ] Persisted legacy IDs remain resolvable.
- [ ] No Python source contract is modified.
- [ ] No migration is executed.
- [ ] No security-level Stage 4B contract is present.

## E. Freeze authorization

This section may be completed only when all A items are approved and every B-D
check is passed.

```text
Human approver:
Approval date:
Contract freeze version:
Signature or repository approval reference:
```

Current freeze state: `FROZEN`.
Contract version: `4A-1.0`.
Freeze date: `2026-11-05`.
