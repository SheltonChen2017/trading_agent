# Verification: SBP plan counter-review and SBPA-006

- Date: 2026-08-20
- Reviewer: Codex
- Submitted remote branch: `origin/codex/review-sbp-plan-amendments-20260819`
- Prior verified head/base: `9d02ee5aec123092f33abd054635997ab5606952`
- Submitted head: `f75e79323dbb79e8b67ee9b741dd47da9f852516`
- Ordered submitted range: `9d02ee5..f75e793`
- Review branch: `codex/review-sbp-counterreview-20260820`
- Correction: `aadb238`

## Verdict

**ACCEPTED AFTER CORRECTION.** Claude independently accepted every substantive
rejection in the prior Codex review and supplied a useful new proposal:
newly listed securities should be excluded by a declared age gate before
ratings selection because they cannot yet supply the frozen 64-close input.
That proposal closes a real availability problem without restoring the
post-selection deletion rejected as SBPA-002.

One material clarification was required. “Listing history” cannot mean the
number of rows returned by the market-data provider. A missing row for an old
security would then make it look newly listed, silently excluding it instead
of triggering the whole-month refusal. Corrected SBPA-006 uses official first
trading date plus the exchange calendar for the pre-rating age gate. After a
security passes that gate, all 64 exact closes remain mandatory.

The correction also removes unproven current-candidate counts from the active
contract, changes “permanent stall” to the accurate temporary-until-seasoned
failure, records that machine-local snapshots were not verified, and keeps
the long counter-review narrative in the review record rather than duplicating
it inside the operative plan.

## Commit disposition

| Commit | Disposition | Reason |
|---|---|---|
| `f75e793` — Counter-review the SBP plan review: all rejections accepted, add SBPA-006 | **ACCEPTED AFTER CORRECTION** | The counter-review's retractions and the security-age concept are correct. The age source/failure boundary, unsupported machine-local claims, dates, topology, and active-plan presentation required correction in `aadb238`. |

## P0–P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| SBPCV-001 | P2 | Closed | `f75e793` | Strong-Buy plan §4 / SBPA-006 | “Listing history contains 64 sessions” could be implemented as provider-row count. Missing data for an old security could then masquerade as youth and be silently excluded, recreating SBPA-002 through the eligibility gate. | The submitted text required re-verification from the provenance-bound price source and did not distinguish official age from observed price completeness. | Pre-selection eligibility may depend on exogenous security age, but broken price data after age eligibility must still refuse the month. | Age gate now uses frozen official first-trading-date evidence plus the exchange calendar. Provider row count is explicitly forbidden; the exact 64 closes remain mandatory after selection. | Contract's age and data-completeness branches are now mutually exclusive and have opposite named outcomes. Focused document tests pass. |
| SBPCV-002 | P3 | Closed | `f75e793` | counter-review report; plan §4; handoff §7bp | The commit repeated unproven claims that no machine-local snapshot exists and that two candidates had 46/47 sessions, despite the prior review requiring measured operational state and reproducible provenance. | No machine-local path/count/hash or exploratory input artifact is recorded in the submitted commit. | Canonical documents must not convert unmeasured machine-local or exploratory observations into facts. | Report now says only that no committed snapshot exists and machine-local state was unverified; exact exploratory counts removed from the active contract. | Cross-document search and focused consistency tests pass. |
| SBPCV-003 | P3 | Closed | `f75e793` | plan amendment log; Session Handoff | Counter-review date was recorded as 2026-08-19 although the commit completed 2026-08-20; the active plan duplicated a long review narrative; topology still called the now-pushed prior review branch local-only. | Commit timestamp and remote ref resolve to 2026-08-20 / `f75e793`; review history belongs under `docs/Archive/Review/`. | Dates, branch availability, and the operative contract must remain concise and accurate for resumption. | Dates corrected; plan retains a concise disposition and links the review record; final handoff supersedes the stale branch-state statement. | Final diff/status checks and handoff section verify the current topology. |

No P0 or P1 findings were identified. Code, QuantConnect, broker controls,
scheduler installation, paper/live execution, and operational databases were
out of scope; the submitted commit changed documentation only.

## Validation

- Focused active-document consistency: **31 passed** in 0.71 seconds before
  the record commit; rerun after the final handoff is recorded separately.
- Full suite on the corrected review tree: **4,348 passed, 25 warnings** in
  879.47 seconds.
- Python: **3.13.14**.
- Required `compileall` surface plus `research/`: **PASS**.
- `git diff --check`: **PASS**; worktree clean before final handoff update.

## Standing

SBP remains **DRAFT**. SBPA-006 is a proposed owner decision, not an adopted
rule. No implementation, capture installation, price join, QC run, paper
order, or deployment is authorized. The next step is owner review of the
complete corrected section 2 before SBP-0 can freeze.
