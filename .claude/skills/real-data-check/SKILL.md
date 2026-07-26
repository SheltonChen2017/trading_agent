---
name: Real-Data Backtest Check
description: Use when testing new tickers, baskets, thresholds, or backtest/config changes in this trading_agent project against REAL market data (fetch_historical/yfinance), not synthetic data. Verifies ticker validity and history depth first, runs the appropriate backtest/basket script in the background since real-data runs take minutes, and applies this project's standard statistical caveats when interpreting and reporting results.
when_to_use: Invoke before running any real-data backtest, basket report, or model evaluation in this repo, and whenever a new ticker is being added to config.UNIVERSE or config.BASKETS.
---

# Real-data backtest check

This project (`trading_agent`) defaults everything to synthetic data
(`generate_synthetic()`), which is safe to run freely with no setup. Real
data (`fetch_historical()`, via yfinance) is a different situation:
it hits the network, takes real time, and — critically — every result
from it needs to be interpreted with the same care every time. This
skill is the checklist for doing that consistently.

## 1. Verify new tickers before adding them anywhere

Never add a ticker to `config.UNIVERSE` or `config.BASKETS` on the
assumption that its symbol is correct or that it behaves like a normal
large-cap. Before adding, check:

```python
from data.market_data import fetch_historical
data = fetch_historical(["NEW_TICKER"], lookback_days=10)
```

- **Does it resolve at all?** `fetch_historical` silently skips tickers
  that error or return no data — a typo won't crash anything, it'll just
  vanish, so explicitly check `"NEW_TICKER" in data`.
- **Is it what you think it is?** If the ticker is unfamiliar or the
  request context is ambiguous, confirm identity before trusting it —
  `yf.Ticker(t).info` (`longName`, `sector`, `quoteType`, `exchange`,
  `marketCap`, `averageVolume`) is enough to sanity-check it's a real,
  liquid, legitimate listing and not a mislabeled/thinly-traded lookalike.
  (Precedent: `SPCX` looked like it might be a data artifact given it
  postdates this project's knowledge cutoff — it turned out to be real,
  but only after checking market cap/volume/exchange, not assuming either
  way.)
- **How much real history does it have?** A recent IPO can have far less
  history than `LOOKBACK_DAYS` (e.g. `SPCX` had ~28 days against a
  504-day lookback). Check `len(data[ticker])` — a short-history ticker
  won't crash the backtest (the scanner correctly skips dates before a
  ticker existed — see `signals/scanner.py`'s `as_of not in df.index`
  guard), but its contribution to any basket/backtest result will be
  statistically meaningless until it has real depth. Flag this explicitly
  in any report rather than letting it silently dilute a basket's numbers.

## 2. Run real-data backtests/reports in the background

Fetching + backtesting the full universe (or several baskets, or a
multi-horizon sweep) against real data reliably takes minutes, not
seconds — every prior real-data run in this project has needed
`run_in_background: true` (or exceeded the default timeout and been
auto-backgrounded). Don't block on it synchronously:

- Launch with `run_in_background: true` and a generous timeout.
- Tell the user roughly what it's doing and that it'll take a few
  minutes, rather than going silent.
- When the completion notification arrives, read the output file — don't
  poll or re-run speculatively while waiting.

## 3. Before trusting ANY new script/config change, run the test suite first

```bash
python tests/test_scanner.py && python tests/test_backtest.py && \
python tests/test_model.py && python tests/test_risk.py && \
python tests/test_alpaca_broker.py && python tests/test_baskets.py
```

This project has already caught two real bugs this way that only
surfaced under real-data conditions the synthetic tests didn't exercise
(a single-ticker `fetch_historical` MultiIndex bug, and a scanner crash
when basket tickers have mismatched history lengths). Assume real data
will find another edge case eventually — run the suite before, not after,
reporting a real-data result.

## 4. Apply these caveats every time you interpret a real-data result

Do not report a win rate, mean return, or "edge" number without checking
it against all of the following — these are standing project conclusions,
not optional extras:

- **Small samples can look like signal and be pure luck.** Roughly
  estimate how likely the observed result is under "no real edge" before
  calling anything interesting. A handful of signals (well under ~30) is
  usually not enough to trust either a positive or negative result.
- **One hold period is not enough.** Prefer
  `run_multi_horizon_backtest()`/`summarize_multi_horizon()` over a
  single `BACKTEST_HOLD_DAYS` result — a signal that only looks good at
  one arbitrary exit timing is suspect.
- **Raw returns must be compared to a baseline, not read in isolation.**
  Use `compare_signal_to_baseline_per_ticker()` (own stock's typical day)
  and, where relevant, `compare_signal_to_market_index()` (the broad
  market on the exact same dates) — trust the per-ticker/market-matched
  numbers over the pooled ones, since pooling can be confounded by
  signals clustering on naturally higher/lower-drift stocks.
- **Testing many baskets/cells at once inflates false positives.**
  With N baskets × 2 directions tested simultaneously, expect a couple of
  cells to look unusually good or bad by chance alone even with zero real
  edge anywhere. A single standout basket needs MORE skepticism, not less,
  the more baskets were tested alongside it.
- **Synthetic data is a plumbing check, not a strategy check.** A ~50%
  win rate / near-coin-flip model accuracy on synthetic data is the
  correct, expected result — never report it as "no bugs found" without
  that framing, and never let it stand in for a real-data conclusion.

## 5. Reuse the existing scripts — don't rebuild ad hoc

Prefer the already-built entry points over writing new one-off analysis:
`scripts/run_backtest.py`, `run_backtest_horizons.py`,
`run_baseline_comparison.py`, `run_basket_report.py`, `train_model.py`,
`run_agent.py`. If a one-off scratch script is genuinely needed (e.g. to
combine a specific set of tickers not covered by an existing script), put
it in the scratchpad directory, not the repo, unless the user asks for it
to become a permanent script.

## 6. Never let a real-data result justify going live

Regardless of how good a real-data result looks, this skill's output is
still just backtest/baseline evidence. Don't suggest enabling
`PAPER_TRADING = False`, connecting a funded account, or otherwise
treating any single positive finding (however many bars it clears) as
sufficient grounds to trade real money — that threshold is deliberately
higher and is not this skill's concern.
