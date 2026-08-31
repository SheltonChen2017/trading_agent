# Portfolio Mandate

**Status: APPROVED by the owner (sheltonchen), 2026-08-04, with the §2
targets adopted unchanged from the draft values.** The machine-readable
counterpart `assistant/default_mandate.json` carries the approval metadata
and an `approved_fingerprint` bound to the exact behavior fields; changing
any target requires a new reviewed approval, not an edit. Approval plants
the goalposts for the live-promotion gate — it does not itself enable live
trading, autonomous execution, or anything beyond the paper-evidence
collection it now makes countable.

## 1. Purpose

"Steady, risk-managed growth" is not a testable goal — it can't tell you
whether a backtest, a paper-trading run, or a proposed change is actually
moving this project in the right direction. This document exists to turn
that goal into numeric, falsifiable targets this project can be graded
against, and to record the scope decisions (which sleeves/ideas are
in-flight vs. explicitly shelved) that follow from it.

This supersedes the informal "steady growth" language in the README intro
as the operative goal statement — the README stays the operational
entry point (how to run things); this document carries the why and the
numbers.

## 2. Numeric targets (approved 2026-08-04; "Draft value" column kept as
the historical basis record)

Where this project has direct evidence, targets are anchored to it rather
than picked from thin air. Where it doesn't yet, that's called out
explicitly rather than presented as more precise than it is.

| Target | Draft value | Basis |
|---|---|---|
| Target annualized volatility | 12–18% | Rough range for a moderate-risk equity/leveraged-ETF-adjacent book — not yet measured against this project's own paper-trading equity curve, since one doesn't exist yet. Revise once real data exists. |
| Max acceptable drawdown | 25% | Anchored loosely to the confirmed SOXX/SOXL trend+volatility rotation result (`research_findings.json`: "Maximum drawdown remained materially lower... across confirmation, walk-forward, sensitivity, and tax/cost checks" — that finding is directionally supportive but doesn't carry a precise percentage in the registry; re-run `scripts/run_idea_comparison_soxx_soxl.py` to pull the actual number when tightening this target). |
| Max acceptable time-under-water | 180 trading days (~9 months) | Placeholder — no project history to anchor this to yet; will be measurable via `backtest.risk_metrics.time_under_water()` (added alongside this document) going forward. |
| Downside capture vs. SPY | ≤ 70% | Standard defensive-allocation target range; not yet measured for anything in this project — measurable via `backtest.risk_metrics.downside_capture_pct()`. |
| Upside capture vs. SPY | ≥ 70% | Same status as downside capture — the pair matters more than either number alone (very low downside capture achieved by giving up most upside isn't the goal). |
| Leverage / liquidity limits | See `assistant/policy.py` | Not restated here — `assistant/default_policy.json`'s `max_leveraged_etf_pct` (0.20), `max_position_pct` (0.05), `max_total_exposure_pct` (0.50), `min_cash_reserve_pct` (0.10), and `max_order_value` ($5,000) are the single source of truth for these limits, enforced by `risk/execution_gate.py`. |
| Recovery-time target | Not yet set | Depends on the time-under-water figure above settling first. |
| Rebalancing frequency | Event-driven, not calendar-driven | Matches the existing wide-rebalance-band finding (`research_findings.json`: "~89% less tax/turnover for essentially the same performance") — rebalance on band breach, not on a fixed schedule. |
| Tax sensitivity | High | Every rotation idea tested so far that looked good pre-tax lost some or all of its edge once realistic tax modeling was added (see `strategies/leverage_rotation.py`'s `tax_rate` parameter and the trend+volatility rotation return finding above). Any future proposal must be evaluated after-tax, not before. |
| Hedge-cost tolerance | Not yet set as a number | HEDGE-1 (2026-08-14) adds an owner-directed DEFENSIVE ETF sleeve, so a hedge can now be held and therefore paid for. Options and futures remain out of scope — see §4. No tolerance figure is set because none has been measured: this project has NOT confirmed that the sleeve reduces drawdown, and setting a cost budget for unmeasured protection would dress a preference as a finding. Measurable via `backtest.risk_metrics` once prospective data exists. |
| Permitted instrument types | Equities and ETFs only (no shorting, futures, or options) | Matches current broker capability (Alpaca paper, long-only equities/ETFs) — see §4. **Unchanged by HEDGE-1:** its instruments (SH, BTAL, TLT, GLD) are all long-only ETFs, so `permitted_instruments` in `assistant/default_mandate.json` still reads `["equity", "etf"]` and the owner-approved fingerprint is untouched. Buying an inverse ETF is a long ETF purchase, not a short position. |

The same approved fingerprint also binds the non-metric promotion safeguards
below. They are listed explicitly because they are behavior fields in
`assistant/default_mandate.json`, even though they are evidence requirements
rather than portfolio-return targets:

| Promotion safeguard | Approved value |
|---|---|
| Minimum paper evidence | 60 independent sessions and 30 broker-observed orders in one immutable evidence epoch |
| Unresolved operational state | 0 unreconciled items and 0 critical alerts |
| Research evidence | Reproduction required |
| Historical-data evidence | Point-in-time data required |
| Recovery evidence | A successful backup/restore drill required |
| Execution authority | Autonomous execution prohibited; exact human approval remains required |

**Explicit non-goal**: no CAGR or Sharpe ratio target is stated as a
primary objective here. They can still be reported for context, but a
result that improves CAGR/Sharpe while missing the drawdown/capture
targets above is not a win by this document's standard.

## 3. Evaluation cadence

- **During research** (backtesting): compute the table-2 metrics from
  `backtest.portfolio_simulator.simulate_portfolio()`'s returned
  `equity_curve`, using `backtest/risk_metrics.py` (`max_drawdown_pct`,
  `expected_shortfall_pct`, `time_under_water`, `downside_capture_pct`,
  `upside_capture_pct`).
- **During paper trading**: once a real paper-trading equity history
  exists, compute the same metrics against it, not just against
  backtests — a backtest passing this mandate is necessary, not
  sufficient.
- Any research finding entering `assistant/research_findings.json` at
  `confirmed` or `promising_unconfirmed` should report, where
  computable, how it performed against this table — not just CAGR/win
  rate.

**Current reality check (2026-07-29):** a reusable first pipeline now exists:
`scripts/run_portfolio_research_report.py` chains the shared-capital
portfolio simulator into `backtest/research_report.py`, fingerprints its
input data and parameters, applies a hold-period embargo, computes the
risk-shape metrics, and writes an immutable report against the
machine-readable mandate. Its current yfinance-backed data is explicitly
marked `point_in_time_data=false`, so the report remains promotion-blocked.
Historical registry findings have not yet been reproduced through this
pipeline.

## 4. Scope decisions

These record how this project responded to a 2026-07 conversation with
GPT that proposed a four-sleeve portfolio-OS blueprint (strategic
growth / defensive carry / crisis-response trend-following /
deterministic risk governor). See §5 for the full disposition; two
specific scope calls are recorded here because they determine what does
and doesn't compete for this project's roadmap priority:

- **Crisis-response / cross-asset trend-following sleeve: someday, not
  roadmap.** This sleeve (the GPT blueprint's proposed source of gains
  *during* equity declines, via diversified long/short trend-following
  across equities/rates/commodities/currencies) is explicitly **not**
  planned. Two reasons: (1) it needs futures or real short-selling
  access this project's infrastructure doesn't have (Alpaca paper
  trading, long-only equities/ETFs); (2) every comparably-ambitious
  rotation/timing idea tried in this project so far has failed once put
  through its own rigor toolkit — Kelly-criterion sizing with a
  one-way ratchet looked like a breakthrough on one discovery/
  confirmation split but failed walk-forward (structurally can't
  re-lever after trimming, so it misses bull-market upside); most
  vol-targeting pairs tested failed to beat buy-and-hold on CAGR. The
  one exception — the wide-rebalance-band idea — shows the bar is
  passable, just rarely cleared, which argues for skepticism rather
  than for scaling up ambition here.
- **Ad-hoc individual-stock signal hunting remains off the roadmap; the
  owner-directed three-strategy stock-first program is active.** The 7+
  legacy signals in `research_findings.json` (0 confirmed) remain closed or
  exploratory methodology history. They do not authorize opportunistic
  reruns. Separately, `docs/THREE_STRATEGY_PROJECT_DIRECTION.md` now requires
  bounded, preregistered stock-level validation for Analyst Revisions V2,
  Insider Buying, and Short Interest before any ETF aggregation can proceed.
  That stock-first work is research-only, must satisfy this mandate's evidence
  standards, and grants no execution or deployment authority.

## 5. Four-sleeve blueprint disposition

| GPT's sleeve | This project's disposition |
|---|---|
| Strategic growth | Existing `UNIVERSE`/`BASKETS` signal-scanning work, unchanged by this document. |
| Defensive carry | **Probe status.** `config.DEFENSIVE_CARRY_TICKERS` (TLT/IEF/SHY/GLD) added 2026-07-28 as an exploratory research candidate — see `scripts/run_defensive_carry_probe.py` and the corresponding `exploratory`-status entry in `research_findings.json`. First-pass real-data result: blending the carry basket into an equal-weight UNIVERSE portfolio monotonically reduced drawdown/expected-shortfall as weight increased from 0% to 30%, with downside capture narrowing slightly faster than upside capture at 30% — a single-window, unconfirmed result, not a live/paper allocation. |
| Crisis-response trend-following | **Shelved** — see §4. |
| Deterministic risk governor | `risk/execution_gate.py`'s `validate_trade_intent()`, labeled explicitly as this project's risk governor 2026-07-28 (see that module's docstring). Consolidating the scattered risk-adjacent logic (see `docs/architecture/ARCHITECTURE_DEBT.md`) is deferred to a dedicated future session, not attempted alongside this document. |

A separate, related gap (not one of GPT's four sleeves, raised in a later
2026-08 review): the current Watchlist allocation feature is user-directed
inverse-volatility splitting, not automated market-volatility-driven
allocation. See `docs/Archive/Plans/ALLOCATION_SERVICE_DESIGN.md` for a design-only
proposal — not implemented beyond a small persisted-cadence storage table.

## 6. Change control

Versioned like `research_findings.json` — bump the entry below whenever
targets in §2 change, so revisions are visible, not silent edits.

- **2026-07-28** — initial draft, all §2 targets marked DRAFT pending
  user revision.
- **2026-07-28** — §5 cross-links `docs/Archive/Plans/ALLOCATION_SERVICE_DESIGN.md`
  (a new gap raised in a later review, not one of the original four
  sleeves); no §2 target changes.
- **2026-07-29** — status changed from draft to proposed; added the
  fingerprint-bound machine-readable mandate and immutable mandate-scored
  research-report pipeline. Numeric targets were not changed or approved.
- **2026-08-04** — **owner approval** (Phase 5 decision 2): sheltonchen
  approved every §2 target unchanged after a plain-language walkthrough
  (including the 60-session/30-order evidence minimums).
  `assistant/default_mandate.json` now carries status `approved` with the
  bound `approved_fingerprint`; the evidence epoch will bind that exact
  fingerprint. `allow_autonomous_execution` remains `false` — approval
  changes what evidence counts, never what the machine may do.
- **2026-08-14** — HEDGE-1: an owner-directed defensive ETF hedge sleeve
  was added (`assistant/hedge_sleeve.py`, `config.HEDGE_SLEEVE_TICKERS`).
  §2's hedge-cost row now says a hedge can be held; the permitted-instrument
  row is annotated but its VALUE is unchanged. **No behavior field in
  `assistant/default_mandate.json` changed, so `approved_fingerprint` is
  untouched** (verified against `compute_mandate_fingerprint`). The active
  `paper-epoch-005` remains unchanged only because HEDGE-1 is development-only
  and has not been deployed. Any later deployment changes the epoch's
  `code_commit` lineage and therefore closes that epoch even though the
  mandate fingerprint is stable. §4's shelving of the crisis-response
  trend-following sleeve also stands: that sleeve needs futures or real
  shorting, which this milestone deliberately does not add.
