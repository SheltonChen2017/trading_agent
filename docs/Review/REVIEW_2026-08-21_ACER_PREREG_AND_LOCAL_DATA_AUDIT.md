# Independent review — ACER preregistration counter-review and local-data audit

Status: **accepted after correction; no ACER milestone completed**

Reviewed remote: `origin/user/claude/acer-prereg-cr-20260821`

Base and merge-base: `734d521da23267deda49fb6ce8f91d35b4d09cd0`

Exact pushed head: `f93e24d7cbb282cac407a2c8b17c4eba6d90c064`

Ordered range: `734d521da23267deda49fb6ce8f91d35b4d09cd0..f93e24d7cbb282cac407a2c8b17c4eba6d90c064`

Review branch: `codex/review-acer-local-data-audit-20260821`

## Commit dispositions

| Commit | Subject | Disposition | Reason |
|---|---|---|---|
| `5372d231755c9417b8df1889dd15339577cd3f4d` | Counter-review the ACER-0A proposal review | **Accepted after correction** | It correctly confirms all six prior Codex findings and correctly surfaces a material owner choice between zeroing and preserving a prior revision. Its new quantitative evidence did not measure that choice: it used unresolved raw identities, approximate calendar-to-session conversion, and percentages for every later state replacement rather than the non-directional zero events at issue. |
| `f93e24d7cbb282cac407a2c8b17c4eba6d90c064` | Audit whether ACER-2 can run on the local path | **Accepted after correction** | It correctly proves the current EDGAR/yfinance route cannot satisfy the proposed ACER requirements and correctly identifies missing book-value/GICS inputs. Its repository-wide conclusion was false because it omitted the existing Databento bars/reference/vintage-adjustment stack, and its deterministic upward-bias claim exceeded the evidence. |

## P0–P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---:|---|---|---|---|---|---|---|---|
| ACERLDR-001 | P2 | Resolved | `5372d23` | CCPR-001; ACER-0A.6 proposal; handoff | The counter-review claimed its percentages measured how non-directional zero events degrade the three half-life cells. The scan grouped unresolved raw ticker/raw firm strings as “same issuer/firm,” converted calendar days by `252/365`, and counted all later actions, including later upgrades/downgrades that replace state under both proposed rules. Its numbers therefore could not support the owner decision. | Direct inspection of the stated numerator and grouping proves the mismatch. A read-only independent reproduction on authenticated Snapshot A found the same 584,916 events and 121,637 directional actions but did not reproduce the submitted successor counts; no committed measurement code or output identity exists. | Signal semantics must be frozen from valid evidence or an explicit unmeasured choice. Invalid numbers could steer the owner and then become irreversibly embedded in the preregistration. | Retain the two semantic options; withdraw the percentages from the active proposal; label the historical scan not decision-grade; require resolved issuer/firm identities, exact NYSE sessions, separated directional/non-directional/expiry incidence, committed code, and hashed lineage before any replacement measurement. | Three focused document guards failed red on exact pushed head `f93e24d` and pass after `32a16b0`; active-document and focused suites pass. |
| ACERLDR-002 | P2 | Resolved | `f93e24d` | local data-capability audit; action plan; handoff | The audit called yfinance the sole local price provider and concluded ACER-2 could not run locally, but the repository already contains reviewed Databento daily-bar, point-in-time reference, and vintage-adjustment paths. The owner was given an incomplete option set that could trigger an unnecessary new purchase or QC policy change. | `ml/databento_source.py` captures immutable `EQUS.SUMMARY` bars; `ml/databento_pit.py` captures `security_master` and `adjustment_factors`; `ml/databento_authoritative.py` builds vintage-correct adjusted feature batches; `docs/operations/DATABENTO_DATA_SOURCE.md` names Databento the selected vendor. No local Databento artifact or credential was present during review, so capability remains unmeasured rather than established. | A roadmap-changing capability audit must inventory the whole repository, not only the production read facade. Both false-negative and false-positive vendor conclusions can waste money or invalidate research. | Limit the negative result to the current EDGAR/yfinance path; restore Databento as an unmeasured candidate; define a zero-outcome structural audit of history, delisted/terminal-return coverage, reference access, cost, licence, and lineage; update current-state options everywhere. | Source-contract inspection plus 179 focused ACER/Databento/document tests pass; new guards fail on the omitted path and pass after correction. |
| ACERLDR-003 | P3 | Resolved | `f93e24d` | local data-capability audit; handoff | The audit elevated an existing docstring's “biases upward” sentence into a deterministic conclusion for every omitted delisting outcome. Failures often have negative terminal returns, but cash acquisitions, mergers, and other exits do not guarantee one sign. | The submitted audit did not measure exit types or terminal returns and expressly said those outcomes were unavailable. It therefore could not establish the sign it claimed. | The absence is disqualifying without overstating a direction. Research documentation must distinguish a known missing-outcome defect from an unmeasured aggregate effect. | State that magnitude and direction are unresolved across the full exit mixture; retain the fail-closed requirement for complete delisted and terminal-return coverage. | Active-document guard pins the corrected claim; review inspection confirms no result claim was substituted. |

No P0 or P1 issue was found. Nothing in the reviewed or corrected range changes
execution, broker, task, database, or operational behavior.

## Independent evidence and boundaries

The existing machine-local licensed Snapshot A was read through its verified
loader only to reproduce aggregate event/action counts and test the submitted
measurement's arithmetic. No raw row or licensed payload is committed or
disclosed. Local Databento state was checked only by credential-presence and
artifact-directory booleans; no vendor was contacted and no data was
downloaded. No QuantConnect, price/outcome join, signal, backtest, broker,
operator database, scheduled task, deployment, or research look occurred.

Correction `32a16b0` changes documentation and active-document regression
guards only. It does not choose the zero-event rule, approve a Databento audit,
establish a data source, authorize a purchase, or close ACER-0A.1–0A.10.

## Validation

- New targeted guards: **3 failed / 0 passed** on the exact pushed documents,
  then **3 passed / 0 failed in 0.15 seconds** after correction.
- Active-document suite: **47 passed** (final rerun: 0.72 seconds).
- Focused ACER normalization/identity, Databento source/PIT/authority, and
  active-document suites: **179 passed in 18.00 seconds**.
- Complete repository suite: **4,453 passed / 0 failed / 25 warnings in
  751.09 seconds** on Python 3.13.14.
- Required `compileall` over the complete surface including `research/`:
  **passed**.
- Final Git/remote/shared-checkout checks are recorded at handoff after the
  final review commits are complete.

## Acceptance and next gate

Both submitted commits are accepted after correction. The current
EDGAR/yfinance path is inadequate, while repository-wide local feasibility
remains unresolved. The next owner decision is whether to authorize a
zero-outcome Databento capability/cost audit; absent that authorization, no
vendor call, purchase, data capture, ACER implementation, or research run may
start. No feature milestone meets its definition of done, so
`FEATURE_MILESTONE_RECORD.md` remains unchanged.
