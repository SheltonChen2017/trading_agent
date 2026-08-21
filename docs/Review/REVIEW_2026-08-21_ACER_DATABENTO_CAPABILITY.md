# Independent review — ACER data-capability checker

Date: 2026-08-21  
Reviewer: Codex  
Implementation remote: `origin/user/claude/acer-databento-capability-20260821`  
Merge base: `381615bffc97195b34b2db34ddb4369f50123aeb`  
Exact reviewed head: `9304f9cc9ccc6f734a4c90b0a1469b6f1e76436d`  
Review branch: `codex/review-acer-databento-capability-20260821`

## Outcome

**Accepted after correction.** The checker is a useful fail-closed replacement
for prose-only repository inventory, and its current seven-check result remains
one available, four unavailable, two unmeasured, six blocking, and
`acer2_runnable=false`. The submitted public contracts nevertheless allowed
an incomplete or internally contradictory assessment to report runnable, and
module discovery was described as a successful import without performing one.
Correction `c9ee971` closes those dangerous directions without contacting a
vendor or changing any ACER research specification.

No ACER milestone completes. This checker establishes local declarations and
installed capability only; it does not establish Databento access, licensed
coverage, delisted/terminal-return behavior, cost, or suitability for ACER.

## Commit-by-commit disposition

| Commit | Disposition | Reason |
|---|---|---|
| `477b9971f52770b2d4cb920414de9a02681f2fee` | **Accepted** | The counter-review correctly confirms all three prior findings, preserves invalidated evidence, and leaves the state-semantics choice and data-source ruling open. No issue found in this commit. |
| `9304f9cc9ccc6f734a4c90b0a1469b6f1e76436d` | **Accepted after correction** | The seven structural checks and available/unavailable/unmeasured distinction are useful and correctly leave ACER-2 blocked, but the submitted contracts contained three fail-open paths corrected by `c9ee971`. |

## P0–P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| ACERDCR-001 | P2 | Closed | `9304f9c` | `research/acer/capability.py:CapabilityFinding` | An unavailable or unmeasured required input could be constructed with `blocks_acer2=false`, contradicting the class contract and allowing a future check to fail open. | Two new parameterized tests accepted these states on the exact pushed implementation. | Every finding in this module is an ACER-2 requirement; a missing or unverified requirement must block the study. | `c9ee971` enforces that every non-available status is blocking. | Both cases failed red before correction and pass green afterward. |
| ACERDCR-002 | P2 | Closed | `9304f9c` | `research/acer/capability.py:summarize_capabilities` | A caller-selected subset, including the calendar finding alone, reported `acer2_runnable=true` while omitting all six blocking requirements. | The new calendar-only regression returned a green summary on the exact pushed implementation. | A readiness summary is safe only when every declared requirement appears exactly once; omission cannot mean readiness. | `c9ee971` centralizes the seven requirement identities and refuses incomplete, duplicate, or substituted checklists. | The subset test failed red and passes green; the complete current checklist still reports six blockers. |
| ACERDCR-003 | P2 | Closed | `9304f9c` | `research/acer/capability.py:check_trading_session_calendar` | `find_spec()` was labelled “importable” without importing the package or constructing the NYSE calendar, so a broken installation could be reported available and non-blocking. | With import forced to fail, the exact submitted checker still returned `available`. | Exact sessions are part of the frozen methodology; discoverable metadata is not a usable calendar. | `c9ee971` imports the pinned package and constructs its NYSE calendar, returning unavailable on import/API failure. | The simulated broken-install test failed red and passes green. |

No P0, P1, or open finding remains. No product, execution, broker, database,
task, deployment, or operational path is changed.

## Boundaries and evidence

The review used repository files and installed dependencies only. It did not
read a credential, contact Databento, Massive, Benzinga, QuantConnect, Alpaca,
or another vendor, purchase or download data, join a rating to a price or
outcome, run LEAN or a backtest, consume a research look, or mutate operational
state. The existing checker still cannot promote Databento beyond
`unmeasured`; that requires separate owner authorization and external evidence.

## Validation

- Submitted focused ACER set: **140 passed**.
- Four new dangerous-direction cases: **4 failed / 14 passed** on the exact
  pushed implementation, then **18 passed** after correction.
- Expanded ACER/calendar/Databento/import-boundary/document set:
  **215 passed in 12.82 seconds**.
- Complete repository suite: **4,471 passed / 0 failed / 25 warnings in
  658.86 seconds** on Python 3.13.14.
- Required `compileall` over the complete surface including `research/`:
  **passed**.
- Final Git/remote/shared-checkout checks are recorded at handoff after the
  final review commits are complete.

## Next gate

The owner must separately authorize a zero-outcome Databento structural
capability/cost/licence audit before any API access, purchase, or download.
That audit must establish history depth, known-delisted coverage, point-in-time
security identity, adjustment and terminal investor-return semantics,
price/volume completeness, licence, cost, and immutable lineage. ACER-2 stays
blocked, ACER-0A remains incomplete, and `FEATURE_MILESTONE_RECORD.md` is not
updated.
