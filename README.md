# Trading agent — data, signal, backtest, ML, risk, and paper execution

An ML-driven trading agent built as one continuous pipeline: a data layer,
a scanner that flags statistically unusual daily moves ("dips" and "ups")
confirmed by volume, a walk-forward backtester that scores those signals'
real forward returns, an ML model that learns a win probability for new
signals, a risk manager that turns that into position sizes and
stop-losses, and an Alpaca paper-trading execution layer. Every stage
reuses the one before it unchanged — same scanner code the backtester
replays date-by-date, same sizing logic the live agent and any future
backtest-of-the-full-strategy would use.

## Structure

```
trading_agent/
├── config.py                    # universe, thresholds, risk params — the one place to tune things
├── data/
│   └── market_data.py            # fetch_historical() [yfinance] and generate_synthetic() [offline dev]
├── signals/
│   └── scanner.py                 # compute_features() + scan_dips_and_ups()
├── backtest/
│   └── engine.py                  # run_backtest() + summarize_backtest() — walk-forward signal scoring
├── ml/
│   └── model.py                   # build_features(), walk_forward_evaluate(), train/save/load, score_signals()
├── risk/
│   └── manager.py                 # size_position(), allocate(), check_stop_loss()
├── execution/
│   └── alpaca_broker.py           # Alpaca paper/live trading — dormant until API keys are set
├── scripts/
│   ├── run_scan_demo.py           # scanner only, synthetic data
│   ├── run_backtest.py            # walk-forward backtest + summary
│   ├── run_backtest_horizons.py   # backtest swept across several hold periods (1 day .. 1 month)
│   ├── run_baseline_comparison.py # flagged signals vs. "hold any day" baseline, per horizon
│   ├── train_model.py             # backtest -> train -> evaluate -> save model
│   └── run_agent.py               # full pipeline: scan -> score -> size -> (optional) execute
└── tests/
    ├── test_scanner.py
    ├── test_backtest.py
    ├── test_model.py
    ├── test_risk.py
    └── test_alpaca_broker.py
```

## Run it

```bash
pip install -r requirements.txt

python scripts/run_scan_demo.py     # scanner only
python scripts/run_backtest.py      # walk-forward backtest + win-rate summary
python scripts/train_model.py       # trains and saves ml/model.joblib
python scripts/run_agent.py         # full pipeline, synthetic data, prints sized signals

python -m pytest tests/ -v          # or: for f in tests/test_*.py; do python "$f"; done
```

Everything above uses `generate_synthetic()` by default, so it runs with
zero setup and no internet access.

## Switching to real data

```bash
pip install yfinance   # already in requirements.txt
```

In any script above, swap:

```python
from data.market_data import generate_synthetic          # remove
from data.market_data import fetch_historical             # add

data = generate_synthetic(UNIVERSE, days=LOOKBACK_DAYS)    # remove
data = fetch_historical(UNIVERSE, lookback_days=LOOKBACK_DAYS)  # add
```

## How each stage works

**Scanner** — Each stock's daily return and volume are scored against
*that stock's own* trailing rolling mean/std (a z-score), not a flat
percentage cutoff, so "a big move" means the same thing for a volatile
small-cap and a slow-moving utility. A move only counts when confirmed by
above-average volume. `scan_dips_and_ups()` takes an optional `as_of`
date — the same function that scans "today" live is what the backtester
calls for every historical date, so there's one code path and no drift
between what's validated and what's run.

**Backtest** — `run_backtest()` walks every date in the universe, calls
the live scanner as-of that date, and measures each flagged signal's
actual close-to-close return over `BACKTEST_HOLD_DAYS`, minus simulated
round-trip slippage (`SLIPPAGE_PCT`). The tested hypothesis is "go long
every flagged signal" (dip = bet on reversion, up = bet on continuation);
shorting isn't modeled. `summarize_backtest()` reports win rate and mean
return by direction.

Two extensions guard against fooling yourself with one arbitrarily chosen
setting:
- `run_multi_horizon_backtest()` / `summarize_multi_horizon()` sweep
  several hold periods (`HORIZON_SWEEP_DAYS` in config.py — 1 day, 3
  days, 1 week, 2 weeks, 1 month by default) so an apparent edge (or lack
  of one) can be checked across exit timings instead of just one.
- `run_baseline_forward_returns()` / `compare_signal_to_baseline()`
  compute the same forward return for *every* date, not just flagged
  ones — the control group a flagged signal's return needs to beat. A
  rising `edge_vs_baseline_pct` over a test window can otherwise look
  like "the signal works" when it's really just the whole universe
  drifting upward during that period.

**ML model** — `ml/model.py` trains a `RandomForestClassifier` on
backtest output to predict the probability a new signal is a winner,
using features known at signal time (`return_zscore`, `volume_zscore`,
direction). Evaluation is **walk-forward** (`TimeSeriesSplit`), not a
random split — training only ever precedes its test fold chronologically.
`score_signals()` attaches a `win_probability` column to fresh scanner
output.

**Risk manager** — `size_position()` sizes a single signal at
`MAX_POSITION_PCT` of equity, scaled down by the model's `win_probability`
(zero size at or below `MIN_WIN_PROBABILITY`, full size at 100%
confidence). `allocate()` sizes a whole batch of signals and trims lowest
confidence first if the total would exceed `MAX_TOTAL_EXPOSURE_PCT` of
equity. `check_stop_loss()` flags when a live position should exit.

**Execution** — `execution/alpaca_broker.py` is dormant until
`APCA_API_KEY_ID` / `APCA_API_SECRET_KEY` are set as environment
variables (never hardcode them). `config.PAPER_TRADING` (default `True`)
selects paper vs live; submitting a live order additionally requires
`CONFIRM_LIVE_TRADING=I_UNDERSTAND` as an explicit second safety check.
`scripts/run_agent.py` runs the whole pipeline and only calls execution if
credentials are present — otherwise it just prints what would be sized
and traded.

## Which broker?

**Alpaca** is what this repo targets: free paper trading (no funding
required), a documented REST API with an official Python SDK
(`alpaca-py`), and nearly identical paper/live endpoints so the code
barely changes when you flip to live. Sign up at alpaca.markets to get
API keys.

Not supported, and not planned:
- **Fidelity / Schwab retail / Robinhood** — no supported public API for
  retail algorithmic trading (Robinhood only has an unofficial,
  reverse-engineered client with fragile auth and no guarantees).
- **Interactive Brokers** — has a real API (TWS/IBKR), but needs a
  running Gateway/TWS app and heavier setup; worth revisiting only if
  Alpaca's asset coverage becomes a limiter.

## Known pitfalls to keep front of mind

- **Look-ahead bias**: rolling windows and the backtester only use
  trailing/already-realized data — keep it that way as you add features.
- **Walk-forward, not one train/test split**: both the backtest's
  forward-return scoring and the ML model's evaluation are time-ordered,
  since markets change regime.
- **Backtest-live gap**: `SLIPPAGE_PCT` simulates round-trip cost, but
  it's a flat estimate — real slippage varies with liquidity and order
  size.
- **Synthetic data has no real edge, by design**: `generate_synthetic()`
  is a random walk with injected shocks uncorrelated with future returns.
  A ~50% backtest win rate / ~50% model accuracy on synthetic data is the
  *correct* result — it confirms the pipeline isn't manufacturing fake
  alpha out of noise. Only real historical data can show genuine edge.
- **Survivorship bias**: if your universe only includes tickers that
  still exist today, delisted/failed names are silently excluded.
- **PDT rule**: US accounts under $25k get restricted after 4+ day trades
  in 5 business days — relevant if the scanner finds same-day-exit
  opportunities.
