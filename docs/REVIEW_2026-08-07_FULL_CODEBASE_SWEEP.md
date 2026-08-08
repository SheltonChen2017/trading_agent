# Full-codebase sweep — 2026-08-07

Audience: repository owner, Codex, Grok, Claude Code, and future reviewers.

Owner request: "scan the WHOLE CODE BASE, including the test, to catch
potential flaws, defects, bugs, orphans and inconsistencies," after reading
every document under `docs/` first.

Base: `011ae5c` (`main`, post PR #168). Review branch:
`user/claude/full-codebase-sweep-20260807`.
Scope: 199 production Python modules / ~62K lines, plus the 155-module test
suite. Previous full sweeps: `docs/REVIEW_2026-07-30_FULL_CODEBASE.md`
(0 P0 / 4 P1 / 10 P2) and `docs/REVIEW_2026-08-06_FULL_PROJECT_SWEEP.md`
(0 P0 / 0 P1 / 2 P2 fixed, 1 P2 open).

**Findings were recorded before any fix.** Commits `f2e1c2d`, `32e2751` and
`38373d3` are documentation only; the two highest-consequence P2s were then
fixed in a later commit on the same branch (see their ledger rows). Everything else remains open and
unfixed. Nothing is deployed; the operational checkout stays frozen at
`9a91498` under `paper-epoch-002`.

## 1. Headline

**No P0. ONE P1. Four P2. Thirteen P3. All eighteen fixed.**

> The P1 was found only after the owner pushed back on an earlier "no P1"
> headline. That challenge was correct, and §3's coverage limits are the
> reason it was warranted -- the first pass had not read the approval flow.

**Status: ALL SEVENTEEN findings are FIXED on this branch.** Corrections and
their verification are in §2b. No finding has had an independent review.

Two of the P2s are *recurrences of classes this project has already fixed
elsewhere*, at sites the earlier fix was never generalized to:

- **FCS-001** — `assistant/strategy_proposals.py` divides by
  `position.current_price` with no finiteness guard, where the sibling
  `assistant/proposals.py` carries exactly that guard with a comment naming
  the failure. Because the Streamlit handler catches only two narrow
  exception types, the resulting `ZeroDivisionError` / `ValueError`
  **suppresses risk-reduction sell proposals that were already computed**.
  CLAUDE.md §5 names that as the one direction that must never be obstructed.
- **FCS-002** — `ml/earnings_experiments.py`'s `calibration_error` divides a
  numerator computed over *scored* pairs by a denominator of *raw* rows, so
  the reported figure improves monotonically as model coverage worsens. This
  is the FPS-004 class, in the same module FPS-004 was found in, and
  `usable_pair_count()` — the helper created to prevent it — exists and is
  not used here.

The fourth, **FCS-016**, is the only *arithmetically wrong* value found:
`assistant/tax_lots.py::is_long_term` compares timestamps where its own
docstring and the IRS rule are date-based, so a sale on the one-year
anniversary at a later time of day than the purchase is classified
**long-term when it is short-term** — understating tax in the
accountant-facing GR-7a export, on precisely the "hold one year, then sell"
behaviour a tax-aware holder deliberately creates. Both existing boundary
tests use the same time-of-day for buy and sell, which is the one case where
the buggy comparison agrees with the correct one; that is why three review
rounds passed over it.

The first prior ledger is genuinely closed: all four 2026-07-30 P1s were
verified fixed in code, not assumed (§4).

## 2. Issue ledger

| ID | Pri | Status | Location | Issue and impact | Evidence | Reason for fix |
|---|---|---|---|---|---|---|
| FCS-018 | **P1** | **Fixed** | `scripts/personal_assistant_ui.py:1043` and `:1457` (both `execute_approved_paper_proposal` handlers) | Both broad handlers rendered `st.error(f"Order not submitted: {exc}")`. But a raising submit does **not** prove the broker rejected the order -- the response can be lost after acceptance -- which is why the kernel leaves the proposal in `submission_unknown`, keeps the reservation, and raises a message that literally begins *"Could not confirm whether the order ... was accepted"*. The operator therefore read: **`Order not submitted: Could not confirm whether the order for tp_abc was accepted...`** -- a definite negative prefixed onto its own contradiction, in the one sentence a human reads before deciding what to do next. | Reproduced by construction from the kernel's own message text. The CLI does **not** have this defect: it lets the exception propagate, so the kernel's wording arrives uncontaminated. The two UI submit buttons (ordinary and override) had both drifted the same way. | **P1, not P2.** *Incorrect broker outcome* and *duplicate orders* are both named in the P1 definition. The machine's own state is correct and `submission_unknown` holds the ticker/side slot, so the system cannot itself place a duplicate -- but the defect's whole effect is on the human, and an operator told the order was not submitted has an obvious next move: place it by hand at the broker. That path is outside every guard this codebase has. **Correction:** a new `_render_submission_failure()` reads the DURABLE status the kernel already wrote -- never the exception text -- and reports "Order outcome UNKNOWN -- do not resubmit" with reconciliation instructions when the proposal sits in `UNRESOLVED_BROKER_STATE_STATUSES`; it fails toward UNKNOWN when the proposal cannot be re-read. A genuine pre-broker refusal still says "Order not submitted". **Verification:** 6 tests (7 unresolved statuses, 4 failed statuses, unreadable-store fail-safe, the exact misleading string, the honest negative preserved, and an AST check that both submit paths route through the reporter). Reverse mutation disabling the unknown branch: 1 fails. |
| FCS-001 | **P2** | **Fixed** | `assistant/strategy_proposals.py:452,454,465,466`; handler `scripts/personal_assistant_ui.py:2668` | Order sizing computes `int(policy.max_order_value / leveraged_position.current_price)` with no finiteness/positivity guard. `PortfolioPosition` has no `__post_init__`, so a zero or NaN `current_price` beside a stale non-zero `market_value` is constructible from a broker snapshot. The CLI catches `Exception` and degrades; the **UI catches only `MissingResearchDependencyError` and `StrategyMarketDataError`**, so the exception escapes, `st.session_state["current_proposals"]` is never assigned, and `store.save_proposal` never runs. | Reproduced end to end. `current_price=0.0`: risk-reduction generator returns `[('sell', 25, 'SOXX')]`, strategy generator raises `ZeroDivisionError`, UI handler does not catch. `tests/test_strategy_proposals.py` had 18 tests, none covering it. **Severity correction made while fixing:** the original write-up also claimed NaN was reachable. It is not — `context_builder.build_portfolio_snapshot` rejects non-finite prices at the boundary, and `build_portfolio_snapshot_from_alpaca` delegates to it, so both production paths are covered. The first reproduction constructed a `PortfolioPosition` directly and bypassed that boundary. The reachable trigger is a **zero or negative** price — finite, so it passes the boundary, and exactly what a halted or unpriced leg looks like. | A data-quality fault in an **optional strategy** feature obstructs an already-computed **risk-reducing sell** — the exact direction CLAUDE.md §5 forbids. `assistant/proposals.py:59-70` already guards the identical idiom, citing this failure (independent review, 2026-07-29); the guard was never generalized. **Correction:** both legs' prices are validated before any sizing arithmetic, raising the new `StrategyPositionDataError` — deliberately a `StrategyMarketDataError` subclass so both existing callers already catch it rather than gaining a new escape. The UI handler is widened to `Exception`, matching the CLI, so no *unforeseen* strategy exception can suppress risk reduction either; the narrow tuple only ever covered failures somebody had already predicted. **Verification:** 7 new tests (zero/negative via the real snapshot builder, non-finite via a directly-constructed snapshot for defense in depth, the subclass contract, and an AST check that both entry points catch broadly). Reverse mutation removing the guard *and* narrowing the handler back: **7 fail**, restored green. |
| FCS-002 | **P2** | **Fixed** | `ml/earnings_experiments.py:425-429` (and `:695`) | `calibration_error = Σ_bins count·\|mean_pred − obs_freq\| / len(actual)`. `calibration_curve` calls `_finite_pairs` (`ml/evaluation.py:196`), so the bin counts sum to **finite pairs only**, while the denominator is the **raw** array length. The metric therefore shrinks toward zero as coverage worsens. Separately, `:695` publishes `candidate_evaluated_event_count = len(validation_eval)` beside `brier_score`, `log_loss`, `precision`, `recall`, and `calibration_error`, all of which drop non-finite pairs. | Quantified: 10 events / 4 finite predictions → reported 0.0600 vs correct 0.1500 (2.5× understated). Holding the same four good predictions fixed and adding NaNs: 4 events → 0.1500, 10 → 0.0600, 20 → 0.0300, 40 → 0.0150. | This is FPS-004's exact failure direction ("the number improves as coverage gets worse") in the same module, and CLAUDE.md §6 makes calibration the measurement that governs whether a probability may ever be called calibrated. `ml/volatility_evaluation.py:404-406` shows the correct house pattern (publishes both `row_count` and `usable_row_count`, computes on `[usable]`). |
| FCS-003 | **P2** | **Fixed** | `research/quantconnect.py:155-184` | `_assert_allowed` rejects literal `..`, `\`, `//`, `://` but not their percent-encoded forms. `urllib` does not normalize, and servers/CDNs routinely decode-then-route. | Executable: `backtests/../data/read` → rejected; `backtests/%2e%2e/data/read`, `backtests/%2E%2E/data/read`, `backtests/.%2e/data/read` → **ALLOWED**. | `docs/SESSION_HANDOFF.md` §5 designates this allowlist as *the* enforcement of the QuantConnect licence boundary, and QCREV-002 hardened this exact function against this exact bypass class one day earlier. Dormant module (no caller, no credentials, not in the frozen checkout), so defense-in-depth rather than a live breach. Fix: `unquote()` before checking, or reject `%` outright — no allowlisted endpoint needs it. |
| FCS-016 | **P2** | **Fixed** | `assistant/tax_lots.py:219-237` (`is_long_term`), `:581-585` (`_long_term_date`) | `is_long_term` builds `one_year_on = acquired_at.replace(year=+1)` — a full **timestamp** — then returns `sold_at > one_year_on`. Its own docstring states the rule is date-based: *"a position bought 2025-03-10 and sold exactly 2026-03-10 is still SHORT term; it becomes long term on 2026-03-11."* So any sale on the anniversary **date** at a later time of day than the purchase is classified long-term. Same defect on the leap-day branch. Separately, `_long_term_date` (which drives `days_to_long_term`) implements a *different* boundary — `replace(year=+1) + 1 day` — so the countdown and the classification disagree by up to a day. | Reproduced. Acquired 2025-03-10 15:00Z: sold 2026-03-10 at 09:00 → False, 15:00 → False, **16:00 → True (wrong)**, 20:00 → True (wrong). Leap day identical: acquired 2024-02-29 15:00Z, sold 2025-03-01 16:00 → True (wrong). A date-based comparison returns the documented answer at every time of day. | `RealizedComponent.long_term` flows into `assistant/tax_reporting.py:251` (`holding_period=LONG_TERM if …`) and the short/long totals at `:465`, i.e. the **CSV/JSON that goes to an accountant**, and into the pre-sale `tax_lot_advisory` on risk-reduction proposals. The failure direction is the harmful one: it understates tax and tells the user "long" on the anniversary, encouraging the sale. **Why three rounds missed it:** `tests/test_tax_lots.py:189-199`'s two boundary tests both use 15:00 for buy *and* sell — the single case where the timestamp comparison agrees with the date rule, so the tests cannot distinguish the correct implementation from this one. **Second dimension — timezone.** The holding period is computed on the fills' raw UTC timestamps, while `tax_reporting._market_local_text` prints `acquired_at` / `sold_at` in `TAX_YEAR_TIMEZONE` (America/New_York) and `tax_year_of` assigns the tax year the same way. So the exported row can be **self-contradictory on its face**: acquired 2025-03-10 14:30Z (10:30 ET), sold 2026-03-11 00:30Z (20:30 ET on 2026-03-10) exports as `acquired_at=2025-03-10, sold_at=2026-03-10, holding_period=LONG-TERM` — exactly one year, printed as long-term. Fix: compare **market-local dates** in `TAX_YEAR_TIMEZONE`, matching the dates actually printed, and derive `_long_term_date` from the same boundary. A naive `sold.date() > boundary` on raw UTC datetimes **does not fix this case** (verified) — it still returns long-term. **Correction:** `is_long_term` and `_long_term_date` both derive from one `_one_year_on()` helper comparing market-local dates; `MARKET_TIMEZONE` is defined once in `tax_lots` and imported by `tax_reporting` as `TAX_YEAR_TIMEZONE`, so the printed date and the classification cannot drift apart again. **Verification:** 5 new tests / 18 cases (anniversary at 7 times of day, leap-day likewise, the day after, the UTC-vs-Eastern case both directions, and countdown/classification agreement across 9 holding periods). The two original boundary tests are **kept** — they were correct, only insensitive. Reverse mutation restoring the timestamp comparison: **8 fail** (including the countdown disagreement at exactly 365 days) while both original tests still pass, which is the insensitivity made executable. Restored green. |
| FCS-017 | P3 | **Fixed** | `assistant/operations.py:117,156,184`; `assistant/readiness.py:191` | Four freshness checks compute `now - at <= limit` with no lower bound, so a **future-dated** timestamp (clock skew, a timezone misconfiguration, a hand-inserted row) reads as FRESH: ledger reconciliation, database backup, restore drill, and order-reconciliation age. Five sibling checks in the same codebase DO guard it with `timedelta(0) <= …` — `operations.py:304` (backup rotation), `alert_delivery.py:412` (self-test), and `evidence_operations.py:125,358,375` (heartbeat, backup, restore drill). | Demonstrated: limit 30 days, a drill stamped +5 days in the future → `operations.py` says fresh (True), `evidence_operations.py` says stale (False). Note `operations.py` contains **both forms**: line 304 guards, lines 156 and 184 in `operational_health` — the function that feeds readiness — do not. | Fail-open on operational readiness. These feed `operational_health` → `platform_readiness`'s operational dimension → the live-promotion gate, and `ml/evidence_operations.py` evaluates the *same two facts* (backup age, restore-drill age) fail-closed, so the platform can simultaneously report the backup fresh and stale depending on which report is read. Third instance this review of the same class: one sibling guards, the other does not. |
| FCS-004 | P3 | **Fixed** | `assistant/cash_reporting.py:98-122` | `policy_headroom` is computed from raw `snapshot.cash` and `sum(market_value)`; the module never reads `snapshot.open_orders` or `snapshot.buying_power`, both present on the dataclass. `risk/execution_gate.py` folds pending buys into both bounds — `min(cash, buying_power)` at `:857-868` and `equity − cash + total_pending_buy_value` at `:894-898`. Headroom therefore overstates deployable room by the pending-buy amount. | `grep buying_power\|open_orders assistant/cash_reporting.py` → no matches. | Third recurrence of the class already fixed in `allocation_proposals.build_allocation_plan` and `portfolio_analytics.preview_trade_impact` (2026-07-31, P1 #3). GR-7b's definition of done is "cash measured against the policy's bounds"; the gate's bounds include pending orders. |
| FCS-005 | P3 | **Fixed** | `execution/alpaca_broker.py:273-274` | `bid_decimal = Decimal(str(quote.bid_price))` — bare, outside any conversion helper. Verified: `Decimal('NaN') > 0` **raises** `InvalidOperation`; `Decimal('Infinity')` passes `> 0` and propagates as `price_decimal="Infinity"`. Currently fail-closed at every consumer (`validate.py:446` `except Exception`, `decimal_or_none`, `math.isfinite` in `allocation_proposals`), so latent, not live. | Verified in the interpreter. `_optional_float` in the same file already guards `math.isfinite`, so the codebase expects non-finite broker values. | Fourth occurrence of the `OPERATIONAL_FACTS` §3 watch class, whose own instruction is that a fourth means "a lint or AST guard banning bare `Decimal(str(...))` outside `assistant/money.py` — not another point fix". It also falsifies the counter-review's claim that the remaining `alpaca_broker` site is "wrapped in its own try/except conversion helper" — that describes line 100, a different function. |
| FCS-006 | P3 | **Fixed** | `risk/execution_gate.py:463` | `worst_case_fill_price` (float) has **zero references repo-wide including tests**; all three live sites use `worst_case_fill_price_decimal`. It is a float money function in an authoritative-money module, and it carries the canonical 26-line rationale for the worst-case-fill rule while the live function has a one-line docstring. Its own text claims "Shared by validate_trade_intent() and preflight_allocation_batch() so the two cannot drift apart" — no longer true of this function. | AST reference count = 0 across all 199 production modules and 155 test modules. | CLAUDE.md §8 forbids "comments claiming guarantees that are not enforced by code and tests". A future editor of the live `_decimal` function will not see the rationale. |
| FCS-007 | P3 | **Fixed** | `assistant/risk_copilot.py:484-554` | `check_policy_compliance` is a **fourth**, independent, float implementation of five policy caps (position, basket, leveraged, total exposure, cash reserve), reachable from the CLI (`run_personal_assistant.py:393`) and the UI (`personal_assistant_ui.py:1643`). Its own docstring positions it as "an actual policy-bound answer". | `docs/ARCHITECTURE_DEBT.md` §2 lists exactly three scatter points; this is not one of them. | The drift risk documented for three sites exists at a fourth the documentation is silent about, and GR-2 created `checks_for_phase("proposal")` specifically as the convergence target. |
| FCS-008 | P3 | **Fixed** | `risk/execution_gate.py:1275-1278`; caller `assistant/execution_kernel/validate.py:518-521` | `validate_trade_intent` mixes units across five identically-suffixed `float` parameters: `max_position_pct` / `max_total_exposure_pct` / `min_cash_reserve_pct` are **fractions** (gate multiplies ×100 internally); `max_basket_pct` / `max_leveraged_etf_pct` are **percents** (no internal conversion, defaults `40.0` / `20.0`). The single caller compensates with a hand-written `* 100` on exactly two lines. | **Mutation-tested**: changing `max_position_pct=policy.max_position_pct` to `* 100` (5% cap → 500%) is **caught by 2 tests** (`test_same_code_but_materially_different_severity_requires_fresh_review`, `test_cumulative_preflight_fails_on_collective_same_ticker_position_cap`). File restored; worktree verified clean. | The fail-open direction is pinned by tests, so this is bounded — but nothing documents or type-distinguishes the convention, and GR-2 deliberately created a second future caller. `risk_copilot` (FCS-007) already treats all five as fractions, disagreeing with the gate's signature. |
| FCS-009 | P3 | **Fixed** | `assistant/execution_telemetry.py:484-489` | The materialized ML record publishes `prices.decision` and `prices.arrival` as separate fields, but `reference_price` is assigned from the same quote the payload's `quote.price` comes from (`validate.py:442`), so they are **identical by construction**. | Traced: both resolve `quote.get("price_decimal", quote["price"])`. | A future ML-9 execution-quality model would measure delay cost as identically zero — a schema artifact, not an execution fact. The module carefully marks `recent_volume` and `liquidity_bucket` unavailable but not this. ML-9 is explicitly gated on this dataset being representative. |
| FCS-010 | P3 | **Fixed** | `docs/ACTION_PLAN_2026-08-02.md` §2.1, `docs/GENERAL_READINESS_STATUS.md` GR-1D/1E, `docs/FEATURE_MILESTONE_RECORD.md` | AP-4's doc-staleness cluster has recurred. Four line counts used as acceptance evidence are wrong: `platform_readiness.py` 683→**778**, `execution_service.py` 952→**900**, `execution_kernel/validate.py` 490→**509**, `execution_kernel/reconcile.py` 279→**258**. The GR-1E adjudication table breaks the 952 into segments. | Measured on the exact tree. | The **architectural conclusion survives**: function sizes are unchanged (281 / 91 / 72 / 75 / 98 against the documented 281 / 90 / 72 / 75 / 98); the 52 lines left `execution_service.py`'s docstring in GR-4 commit `7eef1c5`. Only the arithmetic is stale — but it is the arithmetic GR-1E's "thin composition layer" adjudication rests on. |
| FCS-011 | P3 | **Fixed** | `.github/workflows/tests.yml:18` vs the development host | CI runs Python 3.12 and 3.13. The development machine now runs **3.14.6**, and every validation report in `docs/` states 3.13. The locally-run suite therefore executes on an interpreter CI never exercises. | `python -V` → 3.14.6; workflow matrix → `["3.12","3.13"]`. Baseline suite this session: **3015 passed** vs the handoff's 3014 — worth one reconciliation. | Validation reports are the project's acceptance evidence; naming the wrong interpreter makes them unreproducible, and 3.14-only behaviour would not be caught before merge. |
| FCS-012 | P3 | **Fixed** | `scripts/run_personal_assistant.py:145`, `:1871`, `:2133` | `_non_negative_int` is fully written (both error messages) and **wired to no argument**, while `list --limit` and `tax-report --year` use bare `type=int`. The sibling `list-alerts --limit` (`:2310`) *is* validated with `_positive_int`. | Verified: SQLite treats `LIMIT -1` as unbounded (`select … limit -1` returns all 10 of 10 rows), so `list --limit -1` silently disables the row cap. | An author wrote the guard and never applied it; two sibling arguments on the same CLI disagree about whether their `--limit` is validated. |
| FCS-013 | P3 | **Fixed** | `scripts/run_personal_assistant.py:1139` (in `command_tax_report`, `:1082`) | The accountant-facing artifact is written with a bare `args.output.write_text(...)` — neither atomic nor overwrite-refusing. A crash or full disk mid-write leaves a truncated CSV that still parses as valid CSV with missing rows, and the coverage statement written into the file can itself be cut off. | AST sweep of all 199 modules for artifact writes lacking an atomic publish step returned this and `operations.append_alerts_jsonl` (an append, correctly exempt). | `backtest/research_report.write_research_report` was hardened on 2026-07-31 to be atomic (uuid temp + `os.link`) **and** to refuse overwriting. Same repo, same artifact-publication role, opposite durability discipline — and this is the artifact that leaves the machine. |
| FCS-014 | P3 | **Fixed** | six sites | Orphans, verified by AST reference count = 0 across all production and test modules: `data/analyst_data.py:22 fetch_analyst_actions` (the only production module never imported anywhere; referenced solely in `signals/analyst.py`'s docstring as a usage example), `ml/availability.py:298 PointInTimeSource` (Protocol with no implementer declaring it), `ml/earnings_gap.py:68 _sessions_between`, `ml/volatility.py:198 _clean_returns`, `risk/execution_gate.py:463 worst_case_fill_price` (see FCS-006), `scripts/run_personal_assistant.py:145 _non_negative_int` (see FCS-012). | Full import-graph + symbol-reference scan. | Dead code in safety-relevant modules drifts from the live path and misleads readers; `_clean_returns` in particular implies a cleaning step some caller may be assumed to perform. |
| FCS-015 | P3 | **Fixed** | `assistant/policy.py:save_policy` | Uses a deterministic `.tmp` sibling name, so two concurrent writers (two browser tabs) race on the temp file. `os.replace` keeps the final file untorn, so this is a lost update rather than corruption. | Source read. | Same class as the 2026-07-30 P1 #4 temp-name race that was fixed in `research_report.py` with a uuid component; the fix was not generalized. Lower severity because the outcome is one of the two intended contents, not a partial file. |


## 2b. Corrections applied (2026-08-07)

Every finding above is now fixed on this branch. What each fix actually did,
where the ledger row's "Correction" column would otherwise be a stub:

| ID | Correction | Verification |
|---|---|---|
| FCS-002 | `_classification_metrics` scores **all five** metrics on the same finite pairs via a new public `ml.evaluation.finite_pairs()`, and publishes `event_count` beside `scored_event_count`. This also fixed a second half found while fixing the first: `NaN >= threshold` is False, so an event the model DECLINED to predict was entering precision/recall as a confident negative while being dropped from its own Brier score. Fold metrics gain `<candidate>_scored_event_count` and `candidate_scored_event_count`. | 4 tests; reverse mutation restoring the raw denominator fails `test_calibration_error_denominator_is_the_scored_events_not_every_row`. |
| FCS-003 | `_assert_allowed` percent-decodes twice before the traversal check **and** rejects a literal `%` outright — no allowlisted endpoint needs one, since parameters travel in the JSON body, so this covers encodings nobody has enumerated yet. | 17 tests. Mutation matrix run deliberately: removing only the decoding → all pass (the `%` rule alone suffices); removing only the `%` rule → 1 fails; removing **both** → 5 fail. Recorded because it shows which layer is load-bearing for which input. |
| FCS-004 | `evaluate_idle_cash` nets capital already committed to working buy orders out of both bounds, publishes both the gross and net figures, and discloses orders whose value cannot be determined rather than counting them as zero. | 3 tests; reverse mutation fails 1. **The existing `test_report_carries_no_action_shaped_field` rejected the first naming attempt** (`pending_buy_value` — "buy" is a forbidden substring in a reporting payload's keys); the fields were renamed to `capital_already_committed` etc. rather than the guard weakened. That is the guard working. |
| FCS-005 | New `tests/test_decimal_conversion_guard.py` is the AST lint `OPERATIONAL_FACTS` §3 required after a fourth occurrence, with a reasoned allowlist of the four guarded conversion helpers. The quote path now uses a new local `_required_decimal`. | The guard caught all three `alpaca_broker` sites on first run. 3 guard tests + 3 broker tests, including an executable proof that `InvalidOperation` is not a `ValueError` and that Decimal-NaN ordering raises. **Kept local rather than importing `assistant.money`:** `execution/` has no `assistant` imports at all and is the package `assistant` defers an import *into*. |
| FCS-006 | Dead float `worst_case_fill_price` deleted; its 26-line rationale moved onto the live `_decimal` function, whose final paragraph was **rewritten rather than copied** — it described the deleted wrapper's fallback behaviour, which the live function does not have (it raises). `kill_switch.py`'s comment reference updated. | Behaviour spot-checked across limit/market/sell/non-finite inputs. |
| FCS-007 | `docs/ARCHITECTURE_DEBT.md` §2 now lists the fourth scatter point and says plainly that the list read "three" while a fourth existed. | Documentation. |
| FCS-008 | The unit convention is documented at the signature, where a new caller meets it. | 3 tests: one pinning percent semantics, one pinning fraction semantics **including the fail-open direction**, one pinning that the comment exists. |
| FCS-009 | The record states that `decision` and `arrival` are one observation, that delay cost is not measurable, and why — plus a `delay_cost` entry in `unavailable_fields`. | 1 test, which also asserts the provenance line in `validate.py` still reads as this reasoning assumes. |
| FCS-010 | The four stale counts corrected and labelled measurements-not-gates. **Dated review documents and the milestone record were deliberately left alone** — they are records of what was true then, and §3 of the review instructions forbids silently rewriting history. | Measured. |
| FCS-011 | CI matrix gains 3.14. | Configuration. |
| FCS-012 | `list --limit` uses `_positive_int`; `tax-report --year` uses the previously-dead `_non_negative_int`. | Existing CLI suite. |
| FCS-013 | `_write_artifact_atomically` (uuid temp + `os.replace`, cleaned up in `finally`). Overwriting stays permitted — unlike a research report, re-running `tax-report` after journaling more fills is normal. | Existing tax suite. |
| FCS-014 | `_sessions_between` and `_clean_returns` deleted. `PointInTimeSource` gained a structural-conformance test, which is now its first reference. `data/analyst_data.fetch_analyst_actions` **deliberately kept**: it is the documented data provider for `signals/analyst.scan_analyst_actions`, so it is unreferenced by design rather than dead. | Imports verified; 74 ML tests pass. |
| FCS-015 | uuid-suffixed temp name in `save_policy`, cleaned up in `finally`. | Existing policy suite. |
| FCS-017 | All four freshness checks bounded below with `timedelta(0) <=`. | 4 tests, including a source-level one that fails when a NEW freshness check is added without the guard — which is how these four diverged from their five siblings. |

## 3. Coverage, stated honestly

This sweep was **mechanical across all modules, selective in depth** — the
same honesty CLAUDE.md §10 and the 2026-08-06 sweep §7 require.

| Depth | What | Scope |
|---|---|---|
| **All 199 production modules** | AST/structural scans for: `int(<expr>/<expr>)` division class; `except: pass`; SQL string interpolation; artifact writes without an atomic publish; naive `datetime` construction; mutable class/argument defaults; `Decimal(str(...))`; `or 0` zero substitution; plus a complete import-graph and symbol-reference orphan analysis | complete, mechanical |
| **~35 modules read line-by-line** | all of `assistant/execution_kernel/`; `policy`, `proposal_status`, `order_lifecycle`, `order_reconciler`, `proposals`, `strategy_proposals`, `portfolio_analytics`, `attribution`, `cash_reporting`, `alert_delivery`, `execution_telemetry`, `risk_copilot`, `news_summary`, `money`, `kill_switch`, `share_reconciliation`, `process_singleton`, `runtime_identity`, `sample_portfolio`, `tax_lots`; `research/quantconnect`; most of `execution/alpaca_broker`; core of `data/` | ~10K of 62K lines |
| **Partial (risk-selected regions)** | `execution_service` (the 210-line coordinator), `risk/execution_gate` (cap checks, worst-case fill, `decimal_or_none`), `platform_readiness` (severity/mandatory derivation), `ai_advisor` (the shared output guard), `allocation_batch`, `context_builder`, `performance`, `storage`, `schemas`, `ml/evaluation`, `ml/volatility_evaluation`, `ml/earnings_experiments`, `backtest/research_report`, `backtest/risk_metrics` | — |
| **Not read at line level** | most of `ml/` (37 modules, 18.8K lines); most of `scripts/` (49 modules, 12.8K lines); the bulk of `storage.py` (5,264), `personal_assistant_ui.py` (3,942), `backtest/engine.py` (1,540); `portfolio_ledger`, `paper_evidence`, `tax_reporting`, `operations`, `assistant/llm/*`, `signals/` (19), `strategies/` (6) | ~44K lines |

**Absence from the ledger is not clearance for anything in the last row.**
Both P2s came from a scan flagging candidate sites *plus* a read: the
`int(x/y)` scan surfaced six sites, and only reading `proposals.py` beside
`strategy_proposals.py` revealed that one had the guard and the other did not.
The same scan-then-read pairing has not yet been applied to `ml/`, `storage.py`,
or the two entry-point scripts.

## 4. The prior ledger is genuinely closed

Verified in code rather than assumed. All four 2026-07-30 P1s are fixed:
`allocation_batch` now projects a concurrent winner's terminal state instead
of forcing `LEG_FAILED` (`:596-615`); `write_research_report` uses a
uuid-suffixed temp plus `os.link` create-exclusive (`:427-436`);
`record_split` carries its ordering guard (`:549-597`); `preview_trade_impact`
folds pending buys (`:100-114`). Sampled P2s also hold: `mandate._metric_check`
rejects `bool` before `float()`, `data/price_target_data` now applies
`MARKET_CLOSE_HOUR` like its two siblings, and every production status write
uses the fenced `update_proposal_status_if_current`.

## 5. Sweeps that came back clean

Recorded because a negative result from a systematic sweep is evidence.

| Sweep | Scope | Result |
|---|---|---|
| Mutable default arguments and mutable dataclass class-attribute defaults | all 199 modules | **none** |
| Naive `datetime(...)` construction | all 199 modules | **none** in production |
| `Decimal(str(...))` outside a guarded conversion helper | all 199 modules | one (FCS-005); no fifth |
| `int(<expr> / <expr>)` unguarded-division class | all 199 modules | 6 sites, 2 guarded, 4 unguarded — all 4 in one module (FCS-001) |
| `except …: pass` | all 199 modules | 10 sites, every one documented and deliberate (best-effort teardown, narrowed date filter, original-exception preservation) |
| SQL built by f-string / `%` / `.format()` | all 199 modules | 11 sites, all interpolating placeholder lists or internally-sourced identifiers (`sqlite_master` names, hardcoded tuples) — no injection path |
| Raw counts published beside pair-dropping metrics (FPS-004 class) | all of `ml/` | one genuine (FCS-002); `ml/volatility_evaluation.py` is the correct house pattern |
| Division by `len(...)` without an emptiness guard | `ml/`, `backtest/`, `signals/`, `strategies/`, `research/` | all guarded — including `monitoring_reports.py:589`, where `and common` short-circuits before the division |
| `dropna()` without a published count | same 70 modules | all benign (`pct_change` head, set membership) |
| Silent zero substitution (`or 0`) | `assistant/`, `risk/`, `execution/`, `ml/`, `backtest/` | none reachable; all display-only or guarded |
| Look-ahead in signals | `signals/` spot check | clean — every window is `[:idx+1]`, `shift(-1)` is entry timing only, `residual.py` operates on pre-shifted `_prior` series |
| `platform_readiness` severity handling | full read of the derivation | clean — `_validated_checks` enforces `severity ∈ {critical, warning}` and raises before use, so `mandatory=str(...)=="critical"` has no laundering gap |
| Alert-query row caps (`limit=500`) | `alert_delivery`, `storage` | not reachable — every alert fingerprint is bounded-cardinality (`category:name`, `provider:data_class`, `schedule_key:kind`) |

## 6. Candidates investigated and dismissed

Recorded so the next reviewer does not re-derive them.

- **`assistant/context_builder.py:539-544`** infers "did we observe a real
  bar" from `regime.as_of != datetime.now(timezone.utc).date()` — a UTC date
  compared against an Eastern bar date, the confusion that caused a real bug
  in `storage.get_execution_budget_usage`. **Not a defect**: the UTC/ET skew
  pushes the comparison toward True in the ET evening, which is the
  fail-closed direction, and no concrete failure could be constructed. The
  inference is fragile rather than wrong; an explicit `bars_observed` flag
  returned by `build_market_regime` would remove it.
- **`assistant/attribution.py:236`** multiplies an arithmetic mean invested
  weight by a *compounded* period return — single-period Brinson applied to
  multiple periods with no linking. **Not filed as a defect**: the error lands
  in `selection_pct`, which the module labels a residual and explicitly not a
  skill claim. Worth noting that `allocation_pct` *is* specifically called
  cash drag, the approximation is not disclosed, and the error grows with
  epoch length.
- **`assistant/proposals.py:71`** truncates fractional shares via
  `int(position.shares)`. **Not a defect**: `TradeIntent.shares` is int-typed
  throughout; the system is whole-share by design, not by accident.
- **`assistant/portfolio_analytics.py:40-45`** calls bare `float(notional)`.
  **Not a defect**: `alpaca_broker._normalize_order` already routes `notional`
  through `_optional_float`, which returns `None` for non-finite values.
- **`ml/volatility_evaluation.py:405`** publishes `row_count: len(group)`.
  **Not a defect** — it publishes `usable_row_count` beside it and computes
  every metric on `[usable]`. This is the pattern FCS-002 should adopt.

## 7. Validation

Windows, Python **3.14.6** (note FCS-011 — CI covers 3.12/3.13 only).

- Full suite on the base tree `011ae5c`, before any change: **3015 passed,
  0 failed, 0 skipped, 25 warnings** (257s). FPS-003 did not reproduce.
- Full suite after the first two fixes (FCS-001 / FCS-016): **3041 passed,
  0 failed, 0 skipped, 25 warnings** (352s) -- the +26 exactly the tests those
  two added.
- Full suite on the **exact final tree**, all seventeen fixed: **3085 passed,
  0 failed, 0 skipped, 25 warnings** (347s). The +70 over baseline is entirely
  new regression tests; **no pre-existing test changed its result**, which is
  the claim that matters -- every fix is additive to the existing contract.
- `compileall` clean; `git diff --check` clean.
- Reverse mutations, each applied in the fixed code's own location and then
  restored: FCS-016 (timestamp comparison reinstated) → **8 fail**, and
  notably the two ORIGINAL boundary tests still passed, which is the
  insensitivity made executable; FCS-001 (guard removed AND handler narrowed
  back) → **7 fail**; FCS-002 (raw denominator restored) → **1 fail**;
  FCS-003 → **5 fail** with both layers removed, **1** with only the `%` rule
  removed, and **0 with only the decoding removed** -- recorded because it
  identifies which layer carries which input rather than implying both are
  independently load-bearing; FCS-004 (headroom ignoring commitments) →
  **1 fail**. All restored green.
- FCS-008 mutation: applied, detected by 2 tests, reverted; `git status`
  verified clean afterwards.
- Every finding was reproduced in the interpreter against the real modules
  before being fixed.

No test contacted a funded account. No proposal, approval, sizing,
submission, execution, policy, schema, scheduler, evidence-epoch, ML, or
LLM-authority path was modified.

## 8. Recommended order of work

1. **FCS-001** — guard the four divisions *and* widen the UI handler. Both
   halves are needed: the guard prevents the crash, the handler prevents any
   future strategy-side exception from suppressing risk-reduction proposals.
   Regression test with `current_price` of `0.0` and `NaN`, asserting the
   risk-reduction proposals still render.
2. **FCS-016** — compare **market-local (`TAX_YEAR_TIMEZONE`) dates**, not
   timestamps and not raw UTC dates; derive `_long_term_date` from the same
   boundary. **Rewrite both existing boundary tests to vary the sell
   time-of-day, and add a UTC-vs-Eastern case** — as written they cannot fail
   on this bug, so leaving them unchanged would let the fix land with no
   red/green evidence.
3. **FCS-002** — divide by `usable_pair_count(...)`, and publish
   `scored_event_count` beside `candidate_evaluated_event_count`, matching
   `ml/volatility_evaluation.py`.
4. **FCS-003** — `unquote()` before the allowlist check, or reject `%`.
5. **FCS-005** — per `OPERATIONAL_FACTS` §3, this fourth occurrence calls for
   the AST guard banning bare `Decimal(str(...))` outside `assistant/money.py`,
   not another point fix.
6. The remaining P3s in any order; FCS-010/FCS-011 are documentation-only.

## 9. What this sweep did not do

It did not read `ml/`, `storage.py`, `personal_assistant_ui.py`,
`backtest/engine.py`, or `scripts/` at line level (§3). Only FCS-001 and
FCS-016 carry a correction and red/green verification; **FCS-002, FCS-003 and
all twelve P3s are recorded but unfixed**, and no reviewer has independently
confirmed the two fixes. It did not review the test
suite for weak assertions beyond noting that `tests/test_strategy_proposals.py`
has no coverage for the FCS-001 inputs. And it grants no authority: nothing
here changes what the machine may do.
