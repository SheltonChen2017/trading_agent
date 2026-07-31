# Full-codebase review — 2026-07-30

Independent, read-only review requested by the project owner ahead of continued
rapid development, given growing tech-debt/quality concerns. Five parallel
subsystem reviews, each reading the actual code (not just docstrings/comments
claiming correctness) and cross-checking behavior against `README.md`'s
documented safety claims. No code was changed as part of this review.

**Result: 0 P0, 4 P1, 10 P2.** This codebase has already been through 19+
documented rounds of adversarial review on its execution kernel alone, and it
shows — most subsystems came back clean. The findings below are what a 20th
reviewer still caught: mostly race conditions and drift between two
independently-computed values, not missing safety logic.

Severity key: **P0** = safety-critical exploitable gap. **P1** = real bug,
lower blast radius or self-healing. **P2** = inconsistency / minor / latent.

---

## P1 findings

### 1. Allocation batch: concurrent execution mislabels an in-flight leg as failed
`assistant/allocation_batch.py:516-521`, `execute_allocation_batch()`'s
`ProposalExecutionError` handler only treats the literal status
`"submission_unknown"` as "ambiguous, stop and mark unknown." Every other
in-flight status (`"validating"`, `"approved"`, `"submitting"`,
`"reconciling"`) falls through to `LEG_FAILED` — a *terminal* outcome that
lets the batch continue and eventually report `BATCH_COMPLETED`. This
directly contradicts `_sync_leg_from_proposal()` in the same file, which
deliberately maps those same statuses to `LEG_UNKNOWN` with an explicit
comment: a prior attempt may be in progress, so stop for investigation
rather than guess.

**Trigger:** two overlapping invocations of `execute_allocation_batch()` for
the same `batch_id` (e.g. two browser tabs, or a slow in-flight run
overlapping a Streamlit auto-rerun — `execute_allocation_batch()` runs
unconditionally on every rerun while `active_batch_id` is set). The losing
process's `claim_proposal()` fails, it reads back a `"validating"`/`"approved"`
status (the winner's in-flight state, not `"submission_unknown"`), and marks
the leg `LEG_FAILED` even though the winning process is about to submit it
successfully. Self-healing on the *next* call (which re-syncs every leg from
the authoritative proposal), but until then an operator can see an incorrect
"failed" leg for an order that actually went through.

**Fix direction:** treat any non-terminal proposal status (not just
`submission_unknown`) the same way `_sync_leg_from_proposal()` already does —
`LEG_UNKNOWN`, not `LEG_FAILED`.

### 2. Portfolio ledger: split adjustment can be sized against an incomplete share count
`assistant/portfolio_ledger.py:542-556`, `record_split()` computes
`held_at_effective` by summing only postings *already in the journal* as of
the split's effective date. If `ledger-split` runs before `ledger-sync` has
journaled every pre-split fill (e.g. a delayed poll picks up an old fill
after the split was already recorded), the adjustment posting is sized
against too few shares, and the late-arriving fill posts its original
(non-split-adjusted) qty/price with no corresponding correction — silently
understating post-split share count and cost basis.

**Trigger:** running `ledger-split` shortly after a real corporate action,
before a `ledger-sync` has caught up on all pre-split fills.

**Note:** not a silent permanent corruption — surfaces later via
`ledger-reconcile`'s share-mismatch check. But there's no ordering guard or
warning at `record_split()` time itself, so the gap between "corrupted" and
"detected" is real.

**Fix direction:** require a fresh `ledger-sync` (or verify no pending fills
predate the effective date) before `record_split()` proceeds, or fail closed
if it can't confirm completeness.

### 3. Proposal-card previews don't account for pending orders (execution gate does)
`assistant/portfolio_analytics.py:36-59`, `preview_trade_impact()` computes
`existing_value` purely from `snapshot.positions`, with no pending-order
adjustment. It's called from all three proposal generators
(`proposals.py:251`, `strategy_proposals.py:444`, `allocation_proposals.py:269`).
By contrast, `risk/execution_gate.py` explicitly folds in
`pending_buy_value_by_ticker` for every exposure check — precisely because
README's safety model requires that two proposals approved back-to-back
can't each look individually fine while together exceeding a cap.
`allocation_proposals.py`'s own `build_allocation_plan()` already fixed this
exact bug for the Watchlist cart preview (its docstring cites the earlier
version of this bug directly) — but the per-proposal `TradeProposal.expected_impact`
field that renders on each proposal card still uses the unfixed function.

**Trigger:** approve one leg of a multi-ticker Watchlist purchase (now a
pending/working order), then view or regenerate the second leg's individual
proposal card — its displayed "position X% → Y%" preview omits the first
leg's reserved notional. This is a **display/preview bug, not an execution
safety bug** — the actual execution gate still correctly accounts for
pending orders at approval time — but a user reading the preview before
approving is shown a number that won't match what actually happens.

**Fix direction:** route `preview_trade_impact()` through the same
pending-order-aware exposure calculation `execution_gate.py` uses (or reuse
`build_allocation_plan()`'s logic).

### 4. "Immutable" research reports can be silently overwritten under concurrent writes
`backtest/research_report.py:408-423`, `write_research_report()` checks
`target.exists()` and then calls `os.replace(temp, target)` — but
`os.replace()` unconditionally overwrites its destination on both POSIX and
Windows, and the existence check is not atomic with the write. Two
concurrent calls targeting the same path can both pass the existence check
before either writes; the second `os.replace()` then **silently replaces the
first report's content under the same identifier**, no exception. The
deterministic (non-PID/UUID-suffixed) temp filename (`target.name + ".tmp"`)
also races between concurrent writers.

**Trigger:** a retried or duplicated invocation of
`scripts/run_portfolio_research_report.py --output <path>`, or any future
scheduled automation running this pipeline concurrently with itself.

**Impact:** this directly breaks the "immutable report" guarantee the module
is named for — a report that's supposed to be a fixed, auditable record of
what data/parameters produced a given verdict could get overwritten by a
different run without any trace.

**Fix direction:** use `os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY)`
(or `open(target, "x")`) as the actual atomic create-exclusive guard instead
of `exists()` + `replace()`; give the temp file a unique (PID/UUID)
component.

---

## P2 findings

| # | Location | Issue |
|---|---|---|
| 1 | `assistant/storage.py:2376-2389` (`update_allocation_batch`, `create_allocation_batch`) | Plain read-then-write with no `BEGIN IMMEDIATE`/conditional-`UPDATE` guard, unlike every other proposal-mutating method in this file. Compounds P1 #1: last-writer-wins under concurrent batch execution can overwrite a correct leg result with a stale one. |
| 2 | `assistant/execution_service.py:1342-1349` | Unsupported-order-type fallback branch writes status via plain `store.update_proposal_status()` instead of the file's own `_transition_pre_broker_claim()` fenced pattern. Currently unreachable (policy validation already rejects non-market/limit order types) — latent inconsistency only, would matter if a new order type were ever added without updating this dispatch. |
| 3 | `assistant/portfolio_analytics.py` | "Invested value" is computed two different ways in the same file: `compute_portfolio_analytics()` sums `position.market_value` directly; `preview_trade_impact()` backs it out via `total_equity - cash`. These three broker-sourced fields have no enforced invariant between them — could silently disagree (unsettled cash, timing skew) between the ordinary briefing and a trade preview for the same snapshot. |
| 4 | `assistant/tax_lots.py`, `assistant/performance.py` | Cost-basis/IRR/TWR arithmetic done in plain floats, never via `assistant/money.py`'s Decimal helpers (unlike `portfolio_ledger.py`, `execution_gate.py`, `portfolio_history.py`, `allocation_batch.py`, `execution_service.py`). Looks like an intentional "advisory numbers only" scoping rather than an oversight, but means tax-lot/performance figures can drift from the ledger's exact figures by float epsilon. |
| 5 | `assistant/mandate.py:161-165` (`_metric_check`) | `float(actual)` doesn't exclude `bool` before casting, unlike every other numeric-validation path touched in this review (`money.py`, `tax_lots.py`, `portfolio_ledger.py`, `allocation_proposals.py`). `isinstance(True, int)` is `True`, so a stray boolean would silently coerce to `0.0`/`1.0` rather than being rejected. Currently unreachable from user input (metrics dict is built internally). |
| 6 | `data/price_target_data.py:29-87` | Missing the after-close effective-date correction that its sibling modules (`data/earnings_data.py`, `data/analyst_data.py`) apply to the *same underlying yfinance field* (`upgrades_downgrades`/`GradeDate`). Depending on whether yfinance preserves the hour for this field, this either creates a same-day look-ahead or over-conservatively delays same-day targets. Currently low-stakes: the consuming signal (`analyst_target`) is already recorded `rejected`, but would bite silently if this signal or data module were reused. |
| 7 | `assistant/llm/projection.py:310-331` + `validators.py:204-212` | Event facts (earnings/ex-dividend) are hardcoded `critical=False` regardless of availability, unlike `regime.trend`/`regime.volatility`/`data_freshness` facts. An unavailable earnings-date fact can be silently omitted from `data_quality_warnings` without tripping the fail-closed "concealed critical warning" check. The entire `assistant/llm/` committee package is currently unwired to any live path (confirmed via grep — no script imports it), so this carries **zero current risk**, but should be closed before that package is ever activated. |
| 8 | `assistant/ai_advisor.py:366-370` (`_validate_allocation_review`) | For a multi-ticker observation, the allowed-numbers set is the *union* across all tickers in that observation, with ticker membership checked separately from number attribution — so a true number belonging to ticker B could pass validation attached to a claim about ticker A. Can't invent numbers or produce an allocation instruction, but is a real content-integrity gap; the single-ticker cross-observation version of this exact bug was already fixed elsewhere in the file, this multi-ticker-within-one-observation variant wasn't. |
| 9 | `scripts/personal_assistant_ui.py` (Selling tab ~1956, History tab ~2189) | Trivial position-weight percentage computed inline in the Streamlit script rather than sourced from `assistant/`. Display-only, not used in any policy/approval decision, and no canonical per-position weight field exists on the schema to reuse instead — but it's the one arithmetic expression in either front end that isn't sourced from `assistant/*.py`, which is what the "no separate logic between CLI and UI" design claims to rule out everywhere else. |
| 10 | CI / branch protection | `.github/workflows/tests.yml` genuinely runs the full suite on push/PR to `main` with no `continue-on-error` or masking. Whether that check is configured as a **required** GitHub branch-protection status check (i.e. whether it can actually block a merge, as README implies) is a GitHub settings-page fact, not something verifiable from repo contents. Worth confirming directly if that guarantee needs to be load-bearing. |

*(P2 #3 also noted independently as the disclosed-and-safety-neutral drift
between `proposals.py`'s own concentration check and `risk/execution_gate.py`
— already flagged in that file's own comments as intentional, benign because
it can only under-suggest a sell, not omitted here since it's not new.)*

---

## Clean — verified, not just assumed

- **Execution kernel** (`risk/execution_gate.py`, `execution/alpaca_broker.py`,
  `order_lifecycle.py`, `order_reconciler.py`, `kill_switch.py`,
  `proposal_status.py`, the core of `execution_service.py`): every specific
  claim in README's "Safety model" section was traced against the actual
  code and held — HMAC-bound authorization, atomic claiming, strict
  share-quantity validation, worst-case-fill pricing, override scoping,
  three-way submission reconciliation, kill-switch enforcement inside the
  service itself, no bare-except swallowing found anywhere.
- **Ledger balance invariant** (`portfolio_ledger.py`): every insertion path
  funnels through validated zero-sum postings; balance is independently
  re-derived and re-checked on every read by replaying full history, not
  just trusted.
- **Mandate fail-closed gate** (`mandate.py`): traced end to end, including
  its only real CLI caller — no missing/malformed-field path found that
  flips a check to permissive.
- **Tax-lot FIFO/LIFO/HIFO selection, wash-sale self-exclusion**
  (`tax_lots.py`): no double-counting or off-by-one found.
- **Look-ahead bias / statistical rigor**
  (`backtest/engine.py`, `portfolio_simulator.py`, `risk_metrics.py`,
  all `signals/*.py`, all `strategies/*.py`): the documented
  `compute_features()` shift fix is correctly downstream everywhere it needs
  to be; next-day-open execution discipline correctly implemented in every
  strategy; `risk_metrics.py` formulas are textbook-correct; no new
  look-ahead found in any of the 12 signal files.
- **`config.py`/`baskets.py`**: no ticker/basket inconsistencies;
  `DEFENSIVE_CARRY_TICKERS` correctly excluded from `UNIVERSE`/`BASKETS`.
- **LLM/advisory boundary**: `ai_advisor.py`'s "can never advise an
  allocation" claim holds under tracing (schema-constrained output +
  layered denylist + number/ticker grounding, every display site in the UI
  confirmed to only render post-validation output). `explanations.py`
  contains zero LLM calls — the "explanation layer never computes financial
  quantities from prose" claim holds literally. `news_summary.py`'s prompt
  injection mitigation is real and honestly self-scoped. `llm/validators.py`
  and `llm/projection.py` have no bypass found; privacy projection never
  leaks account/order identifiers.
- **CLI/UI parity, test coverage, CI, config drift**: confirmation phrases
  enforced inside `assistant/` (not just argparse), no risky flag defaults
  on, exit codes correct, paper-only enforcement is genuine defense-in-depth
  (checked independently at both the service and broker layer, no script
  outside the two production entry points touches the broker or DB),
  Streamlit session-state and batch resumption are genuinely idempotent
  across reruns, `requirements.txt` fully pinned, default policy matches
  documented values field-for-field, and every safety-critical module has
  substantive (not trivial) test coverage.

---

## How to read this

None of the P1s are exploitable safety gaps in the sense of "a real order
gets placed that shouldn't." Three of the four P1s are self-healing
(re-sync/reconciliation catches them) or display-only; the fourth
(research-report immutability) affects research auditability, not trading
safety. That's consistent with the project's own framing: the execution
kernel has been hardened far more than the surrounding subsystems, and this
review's findings land almost entirely in the newer/less-scrutinized layers
(allocation batch concurrency, ledger corporate-action ordering, preview
math, research-report writes) rather than in the core gate.

No code was changed. Recommended next step: prioritize and fix, starting
with P1 #1 (allocation batch) and #4 (research report immutability) since
both have concrete concurrent-execution triggers, not just theoretical ones.
