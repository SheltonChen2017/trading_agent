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
