# Independent review — UI-3 interactive Backtest page

- Date: 2026-08-04
- Reviewer: Codex
- Base: `1286966`
- Submitted branch: `user/claude/ui-3-backtest-page-20260804`
- Submitted head: `d664402`
- Review branch: `codex/review-ui-3-backtest-20260804`
- Correction: `540467e`

## Outcome

**Accepted after correction.** No P0 or P1 defect, live-authority escape,
broker interaction, secret exposure, or durable-state change was found. The
submitted page's architecture was strong: it composes the existing engine,
defaults to synthetic data, fixes entry at `next_open`, labels research
limitations, persists results without automatic reruns, and offers no path to
proposals, registry writes, policy changes, or orders.

Review resolved two P2 research-correctness defects and one P3 proof gap. The
corrected page distinguishes absent/partial data from a legitimate zero-signal
result, rejects impossible or silently coerced experiments, stores the
configuration actually used, and has stronger numerical and transitive
boundary regressions.

## Commit dispositions

| Commit | Disposition | Review result |
|---|---|---|
| `198339d` | Accepted after correction | Core architecture, signal inventory, engine composition, UI routing, caching, research caveats, and authority boundary are correct. `UI3REV-001` and `UI3REV-002` required production corrections; `UI3REV-003` required stronger proof. |
| `d664402` | Accepted after documentation replacement | The plan and README accurately described the submitted intent, and its handoff accurately marked the work awaiting review. Completion/validation and known-limit text are superseded by the corrected review records and canonical handoff. |
| `540467e` | Accepted | Corrects data coverage/sufficiency and strict experiment validation, strengthens stored attribution, exact-frame equivalence, real-result caveats, and transitive import-boundary coverage. |

## P0-P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| UI3REV-001 | P2 | Resolved | `198339d` | `backtest/interactive.py`; `scripts/personal_assistant_ui.py` | An empty yfinance response became a normal empty result, partial responses were captioned with the requested rather than loaded ticker count, and a 252-day signal could run on 120 days and report “no signals.” Missing or impossible data therefore looked like a valid fully covered research result. | On the submitted code, `run_interactive_backtest({})` returned empty frames; a dedicated breakout/160-session regression did not raise; source inspection showed `ticker_count=len(bt_tickers)` regardless of returned keys. The new empty/coverage/history regressions failed red before correction. | UI-3's research-honesty contract requires unavailable and underfilled data to be distinguished from a genuine no-signal result. | Added immutable `BacktestDataCoverage`, exact requested/loaded/full-history accounting, empty/unexpected-scope failure, visible partial-coverage warnings, actual loaded counts, and signal-specific minimum-history enforcement including exit horizons. | Red before correction; corrected unit/UI suites green. Hiding the coverage warning made the real-result AppTest fail and restoration returned it green. |
| UI3REV-002 | P2 | Resolved | `198339d` | `backtest/interactive.py` | The fail-closed helper silently truncated integer parameters (`21.9` became `21`) and forwarded zero/negative/fractional/duplicate horizons plus negative or non-finite slippage. A caller could therefore run a different or nonsensical experiment from the one requested. | Direct reproduction printed `fractional-int forwarded as 21` and `negative horizon forwarded as [-5]`; twelve new regression cases failed on the submitted code. | The milestone promises strict parameter validation and exact experiment identity; silent coercion and optimistic negative costs violate that contract. | Added finite-real validation, whole-number enforcement for integer parameters and horizons, positive unique horizons, non-negative finite slippage, and explicit validated values passed to the engine. | Twelve targeted cases passed after correction; the complete corrected `test_backtest_interactive.py` suite passed. |
| UI3REV-003 | P3 | Resolved | `198339d` | `tests/test_ui_backtest_page.py`; `tests/test_backtest_interactive.py`; `tests/test_ml_import_boundary.py` | The UI/engine “equivalence” test compared only row counts, the real-result caveat/coverage path lacked an AppTest, and the research boundary checked only direct imports. Numerical drift or an indirect authority dependency could escape the submitted proof. | Inspection of the submitted assertions and import walker confirmed the gaps. | These tests support the central claims that displayed numbers match the shared engine and that the research surface cannot reach authority code. | Replaced row-count comparison with exact DataFrame equality, added a stored-real-result caveat/coverage AppTest, froze default history semantics, and added fail-closed transitive reachability from `backtest.interactive`. | A zero-slippage UI mutation failed on changed `net_return_pct`; an indirect `backtest.interactive -> backtest.engine -> assistant` mutation failed with the full chain; both were finally restored and green. |

## Validation

Environment: Python 3.13.14.

- Submitted focused baseline re-run: 72 passed in 138.52s.
- Corrected UI-3 unit/AppTest set: 33 passed in 51.25s before the final
  history-sufficiency regression; final adjacent focused set: 88 passed in
  144.16s.
- Full suite on exact correction commit `540467e`: 2,613 passed, 1 skipped,
  25 warnings in 633.75s.
- Compileall over all required packages and root modules: clean.
- `git diff --check` and code-commit worktree check: clean.

The warnings are the existing WebSockets legacy and joblib/NumPy deprecations.
The real network fetch itself remains uncalled in tests; provider underfill and
presentation behavior are tested deterministically without contacting the
network. No operator database, Alpaca endpoint, running Streamlit process,
scheduler, evidence epoch, or external registry was touched.
