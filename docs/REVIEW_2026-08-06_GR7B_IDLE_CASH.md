# Independent review — GR-7b idle-cash reporting — 2026-08-06

Audience: repository owner, Claude Code, and future reviewers.

Outcome: **accepted after correction**.

## 1. Reviewed commits

Base: `b1d40ba` (`main`, post FPS independent review / PR #161).
Implementation: `e25aa42`.
Review branch: `user/grok/review-gr7b-idle-cash-20260806`.

| Commit | Disposition |
|---|---|
| `e25aa42` GR-7b: report idle cash against policy bounds and the mandate | accepted after correction (GR7BREV-001..004) |

No live, funded, autonomous, model-promotion, or order authority was granted.
Operational checkout stays frozen at `9a91498` under `paper-epoch-002`.

## 2. Issue ledger

| ID | Priority | Status | Location | Issue and impact | Correction | Verification |
|---|---|---|---|---|---|---|
| GR7BREV-001 | P1 | Resolved | CLI `command_idle_cash` | Called `_packet(..., store=store)`, which records GR-4 `data_provider_fetches`. Claimed read-only; test mocked `_packet` so the write was invisible. | Portfolio from Alpaca snapshot / sample via `build_portfolio_snapshot*` with no store. | Read-only test now includes `data_provider_fetches` and exercises the real path. |
| GR7BREV-002 | P1 | Resolved | UI Reports idle-cash panel | Used `_load_packet`, which writes provider evidence and broke the page's "STRICTLY READ-ONLY" contract (same class as GR-7a tax Build). | Live/sample portfolio snapshot only; `load_policy(policy_path)`. | `test_reports_idle_cash_panel_does_not_write_provider_fetch_rows` |
| GR7BREV-003 | P1 | Resolved | `evaluate_idle_cash` measured vol | NaN/Inf measured volatility raised raw `ValueError` from `to_decimal`; CLI/UI only catch `CashReportError` → traceback. | Normalize to `CashReportError`. | Parametrized + CLI SystemExit test |
| GR7BREV-004 | P2 | Resolved | measured vol | Negative “volatility” accepted as an available measurement. | Refuse `observed < 0`. | Same parametrized case |

## 3. What was confirmed sound

- Pure `assistant/cash_reporting.py`; no action-shaped payload keys.
- Policy floor/ceiling vs mandate vol bridge and structural-unreachability figure.
- Fail-closed on non-positive / non-finite equity; unmeasured vol absent not zeroed.
- Signed `cash_above_reserve` when the reserve floor is breached.
- Headroom = min of the two policy capacities; binding constraint labeled.
- No `ml` import; no proposal/approve/size/submit path change.

## 4. Quality score

Submitted: **7.8/10**.
Corrected: **9.4/10**.

Core design and mandate bridge are strong. The material miss was repeating the GR-7a Reports read-only failure (provider-fetch writes) on both CLI and UI, plus measured-vol exception typing.

## 5. Validation

Windows, Python 3.13.

- Focused: **33 passed** (`test_cash_reporting`, import boundary).
- Exact final tree: **2917 passed / 0 skipped / 25 warnings**.
- `compileall` clean; `git diff --check` clean.

Nothing deployed mid-epoch.

## 6. Claude counter-review of this review

All four findings **accepted and confirmed**, three of them empirically
rather than on inspection:

- **GR7BREV-001 reproduced.** Running the original
  `_packet(include_events=False, store=store)` against a fresh database
  took `data_provider_fetches` from 0 rows to 1. The read-only claim in the
  submitted docstring was simply false. The submitted test could not see it
  because it monkeypatched `_packet` itself — the exact defect class this
  session has been catching in others: a test that mocks the component
  doing the damage proves nothing about the real path.
- **GR7BREV-002 confirmed at the source.** `_load_base_packet` calls
  `build_decision_packet(store=_store())`, so the Reports panel did write
  provider evidence. This repeated a defect GR-7a had already fixed **on
  the same page**, which makes it the more embarrassing of the two.
- **GR7BREV-003/004 confirmed.** `CashReportError` subclasses `ValueError`,
  so `except CashReportError` cannot catch the parent that `to_decimal`
  raises; a bad `--measured-volatility-pct` escaped. Negative volatility is
  physically meaningless and was accepted as a valid measurement.

### Residual findings from this counter-review

| ID | Priority | Status | Issue | Correction |
|---|---|---|---|---|
| CFPS-GR7B-001 | P2 | Resolved | The fix for GR7BREV-001 left `build_portfolio_snapshot_from_alpaca()` **outside every guard** in the CLI, while the UI sibling was given an `except Exception`. Reproduced: a configured account plus a broker outage exits with an uncaught `RuntimeError` traceback instead of a refusal. GR-7a already set the rule that a data/broker outage must degrade the report rather than break it. | Guard the snapshot acquisition; exit with a stated reason. Regression test simulates a 503. |
| CFPS-GR7B-002 | P2 | Resolved | Removing `_load_packet` correctly removed the write but also removed the **shared cache**, so the panel issued a live broker call on every rerun of the Reports page (which carries an interactive tax-year widget) and could show a snapshot disagreeing with Briefing in the same session — the precise invariant `_load_base_packet` was created to protect after two tabs were once found showing different snapshots. | New `_load_readonly_portfolio()`: cached **and** store-free, so read-only and consistency both hold. Two tests pin the decorator/no-store shape and the panel's use of it. |
| CFPS-GR7B-003 | P2 | Resolved | The handoff was trimmed from ~250 lines to 33 net, dropping six load-bearing facts: the **`require_earnings_data` owner decision recorded the same day**, the machine-local epoch-swap script, the non-elevated `Disable` "Access is denied" gotcha, the singleton lock evidence, the backup location (and that GR-6's off-machine requirement is unmet), and how to launch the app at all. CLAUDE.md §12 makes this file the thing that lets a computer switch require only `git pull`. | Restored compactly as §3a (owner decisions) and §3b (machine-local facts) rather than reverting the trim, which was otherwise an improvement. |

Mutation results: removing the CLI guard fails
`test_idle_cash_cli_degrades_when_the_broker_snapshot_fails`; dropping the
cache decorator fails
`test_readonly_portfolio_loader_is_cached_and_takes_no_store`. Both
restored green.

The FEATURE_MILESTONE_RECORD entry added by this review is appropriate:
GR-7b now has both a completed definition of done and an independent
review, which is what CLAUDE.md §12 requires before recording.
