# Personal trading assistant

A safety-first personal trading assistant and quantitative research
workbench. It combines portfolio awareness, deterministic risk analysis,
versioned research evidence, structured trade proposals, explicit approval,
and Alpaca paper execution.

The project does **not** claim to have discovered reliable stock-selection
alpha. Its production workflow therefore generates exposure-reducing
proposals from policy breaches; rejected or exploratory signals cannot create
buy orders.

## What it does

- Reads positions, cash, buying power, and open orders from Alpaca, or uses an
  explicit sample/manual portfolio when Alpaca is not configured.
- Builds a versioned `DecisionPacket` containing portfolio state, exposure,
  market regime, upcoming earnings, research evidence, warnings, analytics,
  and data-freshness metadata.
- Produces morning briefings and persists them to SQLite.
- Answers deterministic portfolio-risk questions such as concentration,
  leveraged/unleveraged duplication, and benchmark stress impact.
- Generates typed, short-lived risk-reduction proposals with reasons,
  uncertainties, alternatives, and before/after portfolio previews.
- Requires an exact user approval phrase and reruns every risk check against a
  fresh broker snapshot before submission.
- Submits approved orders to Alpaca **paper trading only** and journals the
  resulting proposal and broker order.
- Preserves the existing signal, backtest, statistical-validation, ML, and
  leveraged-ETF research toolkit.

## Safety model

The assistant is deliberately split into layers:

```text
broker / market / event data
            |
            v
versioned DecisionPacket
            |
            v
deterministic analytics and policy
            |
            v
typed TradeProposal
            |
            v
exact user approval
            |
            v
execution gate revalidation
            |
            v
short-lived intent-bound authorization
            |
            v
Alpaca paper broker
            |
            v
SQLite journal and reconciliation record
```

Important guarantees:

- The explanation layer never computes financial quantities from prose.
- Broker order functions reject calls without a short-lived execution-gate
  authorization tied to the exact ticker, side, quantity, and order type.
- Proposals are single-use and expire after 15 minutes by default.
- Repeated proposal generation cannot reset an executed proposal.
- Open broker orders and recently executed intents are checked for duplicates.
- Buys are checked against cash reserve, position, total-exposure, basket,
  leverage, order-value, stale-price, trading-hours, spread, slippage, and
  earnings rules.
- Trading-hours checks use a real NYSE calendar (`pandas_market_calendars`),
  including holidays and early closes -- not just a weekday + fixed
  9:30-16:00 window, which would incorrectly approve a trade on a market
  holiday.
- A wide bid/ask spread blocks a trade (`max_spread_pct`) even for market
  orders, which have no limit price of their own to compare against. A
  one-sided or crossed quote fails closed rather than silently skipping the
  check, and a limit order requires a positive, finite `limit_price`.
- Sells cannot exceed the shares currently held.
- `TRADING_ASSISTANT_KILL_SWITCH=1` blocks proposal execution -- enforced
  inside the execution service itself (not only by callers that remember to
  read the env var and pass it in), so it can't be silently bypassed.
- The personal-assistant execution service refuses to run if
  `config.PAPER_TRADING` is `False`.
- Live-trading support is intentionally not exposed by the assistant CLI.
- If a broker submission fails ambiguously (e.g. a network timeout after the
  order may have already been accepted), the service reconciles by looking
  the order up under its own idempotency key before concluding anything --
  see "Submission reconciliation" below.

## Current research status

The research registry lives in
`assistant/research_findings.json` and is loaded at runtime. Claims are
versioned and labeled independently:

- The original z-score scanner, momentum, relative, breakout, PEAD,
  fundamentals, and analyst-rating hypotheses did not survive the full
  confirmation and dependence-aware testing process.
- Analyst price-target and cross-asset macro signals are exploratory; they are
  implemented but have no registered production edge.
- QQQ/TQQQ regime rotation did not reliably beat its baseline after correcting
  execution timing.
- SOXX/SOXL trend/volatility rotation has a confirmed **drawdown-reduction**
  result, not a confirmed after-tax excess-return result.

Research status is never converted automatically into production authority.
Promotion remains an explicit, auditable decision.

## Installation

Python 3.10 or newer is recommended.

```bash
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS/Linux
source .venv/bin/activate

python -m pip install -r requirements.txt
python -m pytest tests -q
```

Dependencies in `requirements.txt` are version-pinned (exact versions, not
ranges) so a fresh install always reproduces the environment this project was
actually tested against, instead of silently picking up a newer release that
could change behavior. Bump pins deliberately and re-run the full test suite,
rather than leaving them unpinned.

**Windows note:** `streamlit`'s wheel unpacks a deeply nested `static/`
directory; on a Microsoft Store Python install (or any install path that's
already long), this can exceed Windows' default 260-character path limit and
leave `pip install` failing partway through with streamlit partially removed.
If that happens, either enable long paths
(`git config --system core.longpaths true` plus the Windows policy setting at
`HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled`), or create
your virtualenv at a short path (e.g. `C:\venv\ta` instead of a deeply nested
project directory) before installing.

The current dependency set is:

- pandas / numpy
- yfinance
- scikit-learn / joblib
- alpaca-py
- lxml
- pandas_market_calendars (real NYSE trading-hours/holiday calendar)

### Continuous integration

`.github/workflows/tests.yml` runs `python -m pytest tests/` automatically on
every push and pull request to `main` via GitHub Actions -- the full suite
(deterministic/synthetic data and mocked broker calls only, no network or
credentials required) so a regression can't be merged without the CI check
failing first, instead of relying on a human remembering to run `pytest`
locally before every merge.

## Configure Alpaca paper trading

Create Alpaca paper credentials and provide them as environment variables.
Never commit credentials.

```powershell
$env:APCA_API_KEY_ID = "..."
$env:APCA_API_SECRET_KEY = "..."
```

```bash
export APCA_API_KEY_ID="..."
export APCA_API_SECRET_KEY="..."
```

Keep this setting unchanged:

```python
# config.py
PAPER_TRADING = True
```

Without credentials, briefings and proposals use
`assistant/sample_portfolio.py` and clearly identify the source as `manual`.

## Personal policy

The default versioned policy is
`assistant/default_policy.json`. It controls:

- read-only versus paper execution;
- user-approval requirement;
- per-position, total, basket, and leveraged-ETF exposure;
- minimum cash reserve;
- maximum order value;
- price freshness, spread, and slippage;
- earnings blackout window;
- allowed sides and order types (market and limit are both routed correctly
  to the matching broker call; anything else is rejected at policy-load time
  by `TradingPolicy.validate()`, which also rejects empty/negative/
  wrong-typed fields instead of failing silently later);
- whether new positions may be opened;
- whether validated strategy proposals (currently just the SOXX/SOXL
  wide-rebalance-band strategy) are checked by default on `propose`;
- whether a BUY is blocked when live earnings-date data can't be
  resolved at approval time (`require_earnings_data`; risk-reducing
  SELLs are always exempt, since blocking a concentration-reducing sale
  would increase risk, not reduce it).

The checked-in default is deliberately restrictive:

```json
{
  "execution_mode": "paper",
  "max_position_pct": 0.05,
  "max_total_exposure_pct": 0.50,
  "max_basket_pct": 0.40,
  "max_leveraged_etf_pct": 0.20,
  "min_cash_reserve_pct": 0.10,
  "max_order_value": 5000.0,
  "max_spread_pct": 0.5,
  "allow_new_positions": false,
  "enable_strategy_proposals": false,
  "require_earnings_data": false
}
```

Create a separate policy file for personal changes and pass it using
`--policy`. Increment its version whenever behavior changes.

## Use the assistant

### Build a briefing

```bash
python scripts/run_personal_assistant.py briefing
```

This retrieves the portfolio, market regime, open orders, research registry,
and upcoming earnings, then stores the packet in
`data/trading_assistant.db`.

Skip live earnings lookup when working offline:

```bash
python scripts/run_personal_assistant.py briefing --no-events
```

The older formatted briefing remains available:

```bash
python scripts/run_morning_briefing.py
```

It writes both the compatibility JSONL journal and SQLite.

### Generate proposals

```bash
python scripts/run_personal_assistant.py propose
```

Only deterministic exposure reductions are generated. A proposal resembles:

```text
tp_0123456789abcdef: SELL 10 SOXL at reference $55.00
  - Leveraged-ETF exposure exceeds the 20.0% policy limit.
  Preview: position 12.4% -> 9.8%
  Approval phrase: "APPROVE tp_0123456789abcdef"
```

Generating a proposal does not place or approve an order.

### Review proposal state

```bash
python scripts/run_personal_assistant.py list
python scripts/run_personal_assistant.py list --status proposed
```

Proposal states (`assistant/proposal_status.py` is the single source of
truth used by the service, the UI's History filter, and tests -- so these
can't drift out of sync with each other again): `proposed`, `validating`,
`blocked`, `validation_failed`, `approved`, `submitting`,
`submission_unknown`, `reconciling`, `submission_failed`, `executed`,
`expired`.

### Approve one paper order

Run this during standard US market hours with a fresh proposal:

```bash
python scripts/run_personal_assistant.py approve tp_0123456789abcdef \
  --confirm "APPROVE tp_0123456789abcdef"
```

Immediately before submission the service:

1. verifies the proposal is still `proposed`, unexpired, and uses the active
   policy version;
2. confirms Alpaca is configured for paper trading;
3. refreshes positions, cash, buying power, prices, and open orders;
4. checks duplicates and every execution-gate rule;
5. creates a short-lived authorization bound to that exact intent;
6. submits the paper order with an idempotent client order ID;
7. records the order and marks the proposal executed.

To stop all approvals without changing code:

```powershell
$env:TRADING_ASSISTANT_KILL_SWITCH = "1"
```

### Submission reconciliation

An exception while submitting an order to Alpaca does not prove the broker
rejected it -- a network timeout, for instance, can lose the response after
the order was actually accepted. Treating that as a plain failure risks a
later retry submitting a genuine duplicate real order. On any submission
exception, the service:

1. looks the order up at the broker by the same idempotency key
   (`client_order_id`) it originally submitted;
2. if found, journals it and marks the proposal `executed`, same as a normal
   success (`reconciled_after_error` records what the original error was);
3. if the lookup itself can't confirm either way, marks the proposal
   `submission_unknown` -- a distinct, non-terminal status. Proposals in
   `submitting` or `submission_unknown` are treated as live duplicate-order
   risk by the duplicate check, so a regenerated proposal for the same
   ticker/side is blocked until a human checks the Alpaca account directly
   and reconciles it.

Separately, if the broker call succeeds but the local SQLite journal write
afterward fails, the proposal is still marked `executed` (the order really
was accepted) with the local failure recorded in its `error` field --
never silently reported as failed when a real order exists.

The broker lookup itself distinguishes a *confirmed* absence (the broker's
own HTTP 404 -- genuinely no such order) from an *unconfirmed* one (the
lookup itself failed, e.g. a network error) -- only a confirmed absence
resolves straight to `submission_failed`; an unconfirmed one stays
`submission_unknown`.

### Resolving a stuck `submitting` / `submission_unknown` proposal

Re-running `approve` cannot help here -- the proposal is no longer
`proposed`. Reconcile it directly:

```bash
python scripts/run_personal_assistant.py reconcile tp_0123456789abcdef
```

(Also available as a "Reconcile" button in the browser UI's History tab,
shown automatically whenever a proposal has an unresolved broker
submission.) This re-queries Alpaca by the same idempotency key and
cross-checks the ticker/side against the proposal's own intent before
trusting it -- a mismatched order is left unresolved rather than silently
accepted. Every outcome (executed, submission_failed, or still
submission_unknown) is timestamped in `reconciled_at` as an audit trail.

## Browser UI (optional)

`scripts/personal_assistant_ui.py` is a Streamlit front end over the exact
same functions the CLI above uses -- no separate logic, just a different way
to view/click through briefing, proposals, and approval instead of typing
commands. Run it with:

```bash
python -m streamlit run scripts/personal_assistant_ui.py
```

then open the local URL it prints (defaults to `http://localhost:8501`).
The same safety property as the CLI is preserved: each proposal has a text
box requiring you to type the exact `APPROVE <proposal_id>` phrase before
the submit button becomes clickable -- there is no one-click "approve"
button that could submit an order by accident.

## Persistence

`assistant/storage.py` manages `data/trading_assistant.db` with these logical
records:

- versioned decision packets;
- immutable proposal identity and current status;
- broker-order submissions linked to proposals.

The database and its WAL files are gitignored because they contain personal
account state. The research registry and default policy are committed because
they define behavior and evidence, not private runtime data.

## Main packages

```text
assistant/
  context_builder.py       portfolio + regime + evidence DecisionPacket
  policy.py                validated, versioned personal policy
  portfolio_analytics.py   deterministic portfolio metrics and previews
  research_registry.py     file-backed evidence claims
  proposals.py             exposure-reducing typed proposals
  execution_service.py     approval, revalidation, paper submission
  storage.py               SQLite state and idempotency
  risk_copilot.py          concentration, duplication, stress analysis
  explanations.py          "why was this ticker flagged?"

data/
  market_data.py           historical and synthetic price data
  event_data.py            upcoming earnings with availability metadata
  earnings_data.py         point-in-time earnings history
  analyst_data.py          analyst actions
  price_target_data.py     point-in-time price-target consensus
  macro_data.py            credit-spread and yield-curve proxies

risk/
  manager.py               sizing and stop calculations for research
  execution_gate.py        typed validation and short-lived authorization

execution/
  alpaca_broker.py         authorized broker reads and paper/live endpoint

signals/                   pluggable research signals
backtest/engine.py         walk-forward and dependence-aware testing
strategies/                leveraged-ETF rotation research
ml/model.py                walk-forward-evaluated signal classifier
```

## Research workflow

The signal API returns:

```text
ticker, date, close, return_pct, return_zscore,
volume_zscore, direction
```

This lets every signal reuse the same:

- forward-return backtest;
- own-ticker and market baselines;
- discovery/confirmation split;
- by-date and moving-block bootstrap;
- equal-date and trade weighting;
- multiple-comparison correction.

The most rigorous available check is
`out_of_sample_significance_by_block()`. Only the pre-specified primary row
in the confirmation period counts as evidence. Sensitivity variants are not
independent chances to declare success.

Useful research commands:

```bash
python scripts/run_backtest.py
python scripts/run_backtest_horizons.py
python scripts/run_baseline_comparison.py
python scripts/run_out_of_sample_check.py
python scripts/run_significance_check.py
python scripts/run_macro_signals_significance_check.py
python scripts/run_analyst_target_significance_check.py
```

The leveraged-ETF strategies enforce next-day-open execution after using a
day's close to classify state. Tax and transaction-cost modeling are
available in their simulators.

## Legacy agent behavior

`scripts/run_agent.py` is now a research-only synthetic-data demo:

- it cannot submit orders;
- it refuses to size signals when the model artifact is missing;
- it does not treat an absent model as full confidence;
- it identifies the original scanner as research rather than a production
  strategy.

Production paper orders belong exclusively to the proposal and approval
workflow.

## Tests

```bash
python -m pytest tests -q
```

The suite covers scanners, backtests, research statistics, strategies, ML,
risk sizing, assistant schemas, context building, explanations, stress
analysis, execution limits, policy validation, SQLite idempotency, proposal
generation, authorization binding, and approved paper submission with a
mocked broker.

Broker tests do not contact Alpaca. Real-data research scripts do require
network access.

## Remaining limitations

- There is a CLI and a browser UI (Streamlit), but no conversational API.
- Earnings come from a free best-effort data source; unavailable values remain
  explicitly unavailable.
- Tax-lot selection, wash-sale handling, dividends, and realized-tax estimates
  are not yet integrated into proposals.
- SQLite stores submitted broker state, but continuous fill/partial-fill
  reconciliation and alerting are future work.
- Market data used in research is not an institutional production feed.
- Survivorship bias, delistings, liquidity, and borrow constraints remain
  important research limitations. Quantified 2026-07-26: `config.UNIVERSE`
  is confirmed survivorship-biased -- of the three regional banks that
  failed/were seized during this project's own 7-year lookback window
  (SIVB, SBNY, FRC, all Mar-May 2023), none are in the universe. SIVB and
  FRC return no data at all via yfinance ("possibly delisted"); SBNY is
  worse -- that ticker symbol was silently REUSED by an unrelated company
  starting Aug 2024, so fetching "SBNY" today returns a different
  company's ~1.9 years of history with no error, not an absence. Any
  future universe expansion should sanity-check a new ticker's listing
  date/company identity (see the `real-data-check` skill), not just that
  `fetch_historical` returned something. Separately, 11/104 current
  UNIVERSE tickers (PLTR, SNOW, ABNB, COIN, SOFI, AFRM, RIVN, TMC, LAC,
  MP, and SPCX at only 28 days) have under 90% of the 1764-day lookback,
  diluting their contribution to any 7-year backtest.
  Practical impact on this project's findings: LOW for the "0 signals
  confirmed" conclusions, since each signal's edge is measured against
  that same ticker's own baseline return, and survivorship bias inflates
  both sides roughly equally -- if anything this makes the rejections
  more credible, not less. HIGHER for any absolute return number (e.g.
  buy-and-hold CAGR baselines, portfolio-simulator equity curves), which
  are computed on a "survivors only" universe and likely run somewhat
  optimistic. The "dip" signal specifically never saw a real
  bought-the-dip-and-it-went-to-zero case, since bankrupt names aren't in
  the universe at all -- its measured downside tail is understated
  (low-stakes since it's already rejected).
- No strategy is authorized to open new positions under the default policy.

These limitations should be resolved incrementally without weakening the
execution boundary or silently promoting exploratory research.
