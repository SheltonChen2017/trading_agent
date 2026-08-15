# Independent review — REBAL-1 Stage 2 buy-only cash steering

Date: 2026-08-15
Reviewer: Codex
Base: `f64b668`
Implementation head: `7420a9992a715bc1db2be59f1147509a844445a4`
Review branch: `codex/review-rebal1-stage2-20260815`
Correction: `bdeb61d`
Disposition: **Accepted after correction; awaiting the owner's PR and not
deployed.**

## Scope and commit dispositions

Claude made the requested single push to
`origin/user/claude/rebal1-stage2-buy-steering-20260815`. The pushed range was
stable and clean before review.

| Commit | Purpose | Disposition |
|---|---|---|
| `c0d56d5` | Stage 1 residual-band correction plus Stage 2 implementation and tests | **Accepted after correction.** `SleeveRow.band_state` is sound and retained. Stage 2 required REBAL2CR-001 through REBAL2CR-005 below. |
| `7420a99` | Stage 2, owner-policy-decision, action-plan, and handoff records | **Accepted after correction.** The records accurately described intent and submitted validation, but overstated durable profile binding and staleness coverage and still marked the milestone unreviewed. REBAL2CR-006 closes that drift. |

The final feature remains buy-only. It neither creates a sell nor adds a
submit-all path. Each generated leg remains an ordinary proposal requiring
typed approval and the existing fresh paper-only execution validation. The
review did not deploy code, roll or mutate the evidence epoch, change a
scheduled task, touch the operator database, contact a broker, or grant live
authority.

## Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| REBAL2CR-001 | P2 | Closed | `c0d56d5` | `assistant/rebalance_steering.py:462`; UI persistence at `scripts/personal_assistant_ui.py:4014` | Every Stage 2 proposal retained a `Decimal` reference price. `AssistantStore.save_proposal()` JSON-encodes the proposal, so the first ordinary button use raised `TypeError` before an approval card could appear. | The integrated execution-binding regression reached storage and failed with `Object of type Decimal is not JSON serializable`; object traversal isolated `.reference_price`. | A milestone is not complete when its only action path crashes before persistence. | Preserve Decimal through sizing, then convert the established `TradeProposal.reference_price` display/persistence field to float at the boundary. | `test_every_proposal_is_a_gated_buy_bound_to_the_profile` now JSON-serializes every proposal; focused and full suites pass. |
| REBAL2CR-002 | P2 | Closed | `c0d56d5` | `assistant/rebalance_steering.py:433-455` | Budget was part of `proposal_id` but absent from `idempotency_key`. Two nearby budgets that rounded to the same whole-share intent produced different proposal IDs and the same unique idempotency key, so saving the second result could raise a database uniqueness error. | Original construction used a second `_stable_id` salted only by the profile; `trade_proposals.idempotency_key` is unique. The regression uses budgets `2000` and `2000.01` and confirms at least one equal-quantity leg. | Budget edits are an ordinary UI action and must not corrupt or reject otherwise distinct durable proposal state. | Derive the key from the already budget-bound `proposal_id` plus snapshot date, matching the established proposal pattern. | `test_budget_change_cannot_reuse_an_idempotency_key_for_the_same_shares`; full suite passes. |
| REBAL2CR-003 | P2 | Closed | `c0d56d5` | `assistant/rebalance_steering.py:440-448`; `assistant/execution_service.py:330-365`; `assistant/execution_kernel/validate.py:266-275` | The allocation fingerprint changed proposal identity but was not stored as an execution condition. A proposal persisted before a profile edit remained reachable through History and could proceed under the new profile. | Source tracing found no execution-time comparison. A moved-profile proposal now reaches the public validation facade and is refused before broker import. | The milestone explicitly requires proposals to bind to the allocation profile; changing only identity prevents row reuse but does not invalidate an already stored row. | Store profile version/fingerprint in `expected_impact`; inject a feature-context validator through the frozen GR-1C facade dependency contract; compare against the active owner profile before broker I/O and fail closed on missing/mismatched data. | `test_execution_refuses_a_proposal_from_a_non_active_profile`; the call-time seam is pinned in `test_gr1c_every_injected_seam_resolves_from_the_facade_at_call_time`; kernel zero-global-read characterization remains green. |
| REBAL2CR-004 | P2 | Closed | `c0d56d5` | `scripts/personal_assistant_ui.py:3984`; `assistant/rebalance_steering.py:152-186` | The retained-card signature covered date, equity, choices, budget, and pending totals but not position market values or the complete snapshot. Opposite same-day price moves could preserve date/equity/pending values and leave a card sized from old sleeve weights visible. | A regression builds two snapshots with identical date, equity, shares, and pending orders but growth/dividend values of `$1,000/$1,000` versus `$1,200/$800`; the old signature inputs are equal. | An approval card must disappear after any snapshot change that changes its meaning, as required by the Stage 2 definition of done. | Replace the hand-maintained UI string with a shared SHA-256 fingerprint over the complete portfolio snapshot, report, policy fingerprint, normalized choices, and exact budget. | `test_same_day_market_value_change_invalidates_the_ui_signature`; Streamlit UI suite and full suite pass. |
| REBAL2CR-005 | P3 | Closed | `c0d56d5` | `assistant/rebalance_steering.py:128-149` | Exact lower-edge dollars were reconstructed from display floats (`projected_pct` and `lower_edge_pct`). Awkward denominators introduced binary artifacts into fractional sizing despite the exact-money contract. | For `$7` equity and a `$1` growth holding, the exact 30% lower-edge shortfall is `$1.10`; the original percentage round-trip did not preserve that exact decimal. | This is a low-dollar edge, but fractional-share mode promises exact quantity and money boundaries. | Compute the lower edge from the profile's Decimal band and subtract the row's exact current and pending dollar values. | `test_lower_edge_shortfall_stays_exact_on_an_awkward_denominator`; focused/full suites pass. |
| REBAL2CR-006 | P3 | Closed | `7420a99` | Stage 2 review report, milestone plan, action plan, feature record, and session handoff | Submitted records said profile binding was in identity/idempotency and that the short UI signature covered snapshot staleness; both claims were incomplete. They also necessarily described Stage 2 as pending review. | Commit-by-commit document comparison against the corrected code and final topology. | The action plan and handoff are sequencing and cross-machine authorities; leaving those claims stale would direct the next reviewer incorrectly. | This independent report retains the original findings; current records now state execution-time profile binding, complete snapshot fingerprinting, exact correction hash, validation, and accepted-after-correction status. | Documentation diff check, full-suite guard tests, and final topology verification. |

No P0 or P1 issue was found. All six confirmed findings are closed. The Stage
1 `band_state` correction was independently checked against display-status
precedence, unknown pending exposure, breach counting, and its tests; no
additional defect was found there.

## Safety and compatibility review

- Paper-only checks, typed approval, kill switches, atomic proposal claims,
  execution reservations, reconciliation, and broker outcome handling remain
  unchanged.
- The only execution-kernel addition is a read-only, pre-broker context check
  for `evidence_status == user_directed_rebalance_buy`. Other proposal
  families return immediately from the context validator and retain their
  prior behavior.
- The new collaborator is supplied at call time through
  `ProposalValidationDeps`. The facade monkeypatch seam and the kernel's
  zero-module-global runtime boundary remain characterized.
- Idempotency now follows the repository's established
  `<proposal_id>-<snapshot-date>` construction. There is still no submit-all.
- LLM, ML, strategy-authoring, backtest, live-account, and funded-account
  paths are outside this feature and remain non-authoritative or prohibited.

## Validation

Environment: repository `.venv`, Python 3.13.14, Streamlit 1.60.0, Windows.

- Red phase: the first regression collection failed because the new complete
  staleness helper was absent. After the preliminary corrections, the
  integrated durable-profile test exposed the independent JSON persistence
  failure described in REBAL2CR-001.
- Focused final tree:
  `tests/test_rebalance_steering.py`, `tests/test_portfolio_rebalance.py`,
  `tests/test_ui_portfolio_rebalance.py`, and
  `tests/test_execution_characterization.py`: **170 passed in 45.60s**.
- Full final tree: **3,975 passed, 0 failed, 25 known dependency warnings in
  647.43s (10:47)**.
- `python -m compileall -q assistant scripts risk tests`: clean.
- `git diff --check`: clean.

The full count is four above Claude's submitted 3,971 because the review
added four test functions and strengthened existing proposal assertions.

## Assessment

**Implementation quality: 6.5/10 as submitted; 9/10 after correction.** The
scope discipline, buy-only design, projected-order handling, lower-edge
choice, separate approvals, disclosures, and Stage 1 band-state correction
were thoughtful and well tested. The submitted feature nevertheless crashed
on its main persistence path and did not fully meet three explicit durable
safety contracts (idempotency, profile invalidation, and complete staleness),
which prevents a higher submitted rating.

REBAL-1 Stage 2 now meets its reviewed definition of done in development.
Stage 3 remains not started and is not authorized by this review; it is the
first stage that would let the app originate rebalancing sells and still
requires separate explicit owner authorization.
