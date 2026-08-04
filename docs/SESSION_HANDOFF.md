# Development session handoff

Prepared: 2026-08-04 after Claude (a) counter-reviewed Codex's UI-2b review,
(b) added the UI-3 Backtest-page plan to the action plan, and (c) implemented
UI-3 and pushed it for independent review.

Audience: Codex, Claude Code, and the repository owner after a computer,
model, or session change. This file completely replaces the prior handoff.

## 1. Current outcome

**UI-2b counter-review: closed clean.** Codex's review chain (PR #140,
commits `9dcff80`/`df4d278`/`bf0e396`/`c5fea82`/`1300aaa`) was verified
commit by commit. The single finding, UI2BREV-001, was independently
re-proven: Claude applied the fetch-then-filter mutation to the real UI and
Codex's large-history AppTest failed for exactly the claimed reason, then
passed after restoration. Docs and merge topology (PR #139 second parent =
`8ff2017`, PR #140 second parent = `c5fea82`) check out. Merged branches
were deleted locally and on origin; the remote again holds only `main`.

**UI-3 — interactive Backtest page — is implemented and pushed, awaiting
independent review.** The owner requested it 2026-08-04 ("set up signals and
run backtest in the UI directly", with a result graphic); the frozen
six-point plan was written into `docs/ACTION_PLAN_2026-08-02.md` (UI-3)
BEFORE implementation and is the review contract. Implementation commit
`198339d` on `user/claude/ui-3-backtest-page-20260804`, based on
`main = 1286966` (post PR #140).

What UI-3 contains:

- `backtest/interactive.py` (new): a frozen inventory of six price-only
  signals (dip/up z-score, cross-sectional momentum, relative dip/up,
  52-week breakout, 52-week-high proximity, vol-scaled momentum) with
  per-parameter widget bounds whose defaults are asserted equal to each
  scan function's own signature defaults; `run_interactive_backtest()`
  (fail-closed on unknown signal, undeclared/missing/out-of-bounds
  parameters, empty horizons) calling the SAME
  `backtest/engine.py::run_multi_horizon_backtest` the CLI scripts use with
  entry timing fixed to executable `next_open`; `cumulative_return_frame()`
  for the chart; and the exact caveat texts the UI must render
  (SYNTHETIC_CAVEAT, EXPLORATORY_CAVEATS, CHART_CAPTION). PEAD/fundamentals
  (earnings feed) and residual/idio-vol (require a precomputed residual or
  benchmark feed) are deliberately excluded from v1.
- A ninth sidebar page, "Backtest", between Ticker Suggestions and
  Operations: signal selectbox with description, per-signal namespaced
  parameter widgets (`bt_param_<signal>_<name>`, so shared names with
  different bounds can never collide), data source radio defaulting to
  synthetic (network is never implied by opening the page), universe/basket
  scope, history length, hold-horizon multiselect, and an explicit Run
  button. Synthetic loads are cached; real yfinance loads are cached with a
  1-hour TTL. Completed runs live in the non-widget `backtest_run` session
  key, survive navigation, and render a configuration caption ("results
  reflect this configuration, not any widget changed since"), the severity-
  correct caveat, the multi-horizon summary table, and a per-direction
  cumulative net-return `st.line_chart` with a stale-selection guard on the
  chart-horizon selectbox.
- Benign backtest configuration keys joined the UINAV-001 persistence
  whitelist (statically plus a comprehension over the inventory's
  parameter keys).
- README's Streamlit section was rewritten: it still said "Five tabs" with
  Watchlist; it now documents the nine sidebar pages (including UI-2b's
  outcome filter and the Backtest page) and notes that the confirmatory
  significance pipeline remains CLI-only on purpose.

Deliberately NOT implemented: no significance/bootstrap computation in the
UI (the page states that confirmatory significance runs only in the frozen
CLI pipeline — this is a design rule, not an omission), no portfolio equity
curve (the chart caption says explicitly it is an equal-weight running sum,
not compounded equity), no registry writes, no new dependency, no CLI
change, no persistence schema change, and no path from any backtest result
toward proposals or execution.

## 2. Canonical Git state

Repository: https://github.com/SheltonChen2017/trading_agent

    base/main/origin-main = 1286966 (post PR #140)
    UI-3 implementation = 198339d
    UI-3 docs/handoff = the branch-tip commit containing this file
    branch = user/claude/ui-3-backtest-page-20260804 (pushed)

Nothing has been merged for UI-3. The owner opens the PR (this machine's gh
account cannot create PRs).

## 3. Validation (development machine, Python 3.13, exact final tree)

    new unit tests (inventory/validation/chart/boundary): 14 passed
    new AppTests (Backtest page end-to-end on deterministic synthetic
        data, incl. an engine-equivalence check): 6 passed
    UI-adjacent focused set incl. import boundary: 78 passed in 102.64s
    full suite: 2,597 passed, 1 skipped, 25 warnings in 407.67s
    compileall (all packages + root modules): clean
    git diff --check: clean

Reverse-mutation proofs (each applied, shown red, restored):

1. UI silently running a different experiment than displayed (hardcoded
   z-threshold override in the run call) → caught by
   `test_synthetic_run_completes_and_matches_the_engine`, which compares
   the UI's per-horizon row counts against a direct engine run on the same
   deterministic inputs.
2. Synthetic run labeled with the real-data exploratory caveat → caught by
   `test_synthetic_result_carries_the_synthetic_caveat`.
3. `bt_scope` removed from the persistence whitelist → caught by
   `test_results_survive_navigating_away_and_back`.

Known coverage limits, stated for the reviewer: the real-data path
(`_load_backtest_real_data`) is not exercised by tests (network); its cache
key/TTL and the engine call are shared with the tested synthetic path. The
chart itself is pinned via its caption and the frame builder's unit tests,
not by asserting rendered chart internals (AppTest has no first-class
line-chart accessor).

## 4. Review guidance

Review range: `198339d` plus this handoff commit on
`user/claude/ui-3-backtest-page-20260804`, based on `1286966`. The contract
is the UI-3 section of `docs/ACTION_PLAN_2026-08-02.md` (six numbered
points). Adversarial attention is most useful on:

- research-honesty wording: does every rendered result carry the correct
  caveat, and is there any path to a pooled-significance-looking number;
- the fail-closed validation in `run_interactive_backtest` (unknown/
  missing/out-of-bounds/empty-horizon) and int coercion of int-kind params;
- Streamlit state edge cases: switching signals mid-session, a second run
  with different horizons (the `bt_chart_horizon` stale-selection guard),
  whitelist interaction with `_preserve_page_widget_state`;
- the boundary test (`test_interactive_module_never_imports_execution_or_ml_code`)
  and whether the transitive import-boundary suite still holds; and
- README accuracy against the actual nine pages.

## 5. What is next (do not start without owner direction)

- Independent review of this branch, then the owner's merge decision.
- UI-2d (durable dismiss/archive) remains the next UI milestone after
  UI-3's review; adding its `dismissed` status must also update UI-2b's
  exhaustive outcome mapping (the exhaustiveness test will force it).
- Phase 5 (operational deployment + epoch start) remains owner-heavy,
  blocked only on the four decisions in
  `docs/PHASE5_DEPLOYMENT_SESSION.md` §2.

## 6. Non-negotiable boundaries

- Paper trading is the only execution mode in scope.
- The Backtest page is research-only: nothing on it may create, approve,
  size, submit, cancel, or reconcile an order, write to the research
  registry, or change policy.
- A backtest result — however good-looking — is never evidence of edge and
  never grounds for live trading; confirmatory significance runs only in
  the frozen CLI pipeline.
- ML/LLM output remains advisory or observational only.
- Never commit credentials, operator databases, licensed data, or evidence
  artifacts.

## 7. Machine-local state

The owner's Streamlit app may be running from an earlier checkout; it does
not gain the Backtest page until this branch merges and the app reloads.
This session did not stop, restart, or mutate that process. All tests ran
against the pytest-isolated session database. An earlier full-suite
background run in this session produced an empty output file while a
foreground rerun completed normally with identical results; both exited 0 —
recorded here so the empty file is not mistaken for a failed run.
