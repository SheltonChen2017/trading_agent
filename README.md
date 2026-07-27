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
  leverage, order-value, stale-price, trading-hours, slippage, and earnings
  rules.
- Sells cannot exceed the shares currently held.
- `TRADING_ASSISTANT_KILL_SWITCH=1` blocks proposal execution.
- The personal-assistant execution service refuses to run if
  `config.PAPER_TRADING` is `False`.
- Live-trading support is intentionally not exposed by the assistant CLI.

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

The current dependency set is:

- pandas / numpy
- yfinance
- scikit-learn / joblib
- alpaca-py
- lxml

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
- price freshness and slippage;
- earnings blackout window;
- allowed sides and order types;
- whether new positions may be opened;
- whether validated strategy proposals (currently just the SOXX/SOXL
  wide-rebalance-band strategy) are checked by default on `propose`.

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
  "allow_new_positions": false,
  "enable_strategy_proposals": false
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

Proposal states include `proposed`, `approved`, `blocked`, `expired`,
`submission_failed`, and `executed`.

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

- The CLI is functional, but there is not yet a browser dashboard or
  conversational API.
- Earnings come from a free best-effort data source; unavailable values remain
  explicitly unavailable.
- Tax-lot selection, wash-sale handling, dividends, and realized-tax estimates
  are not yet integrated into proposals.
- SQLite stores submitted broker state, but continuous fill/partial-fill
  reconciliation and alerting are future work.
- Market data used in research is not an institutional production feed.
- Survivorship bias, delistings, liquidity, and borrow constraints remain
  important research limitations.
- No strategy is authorized to open new positions under the default policy.

These limitations should be resolved incrementally without weakening the
execution boundary or silently promoting exploratory research.
