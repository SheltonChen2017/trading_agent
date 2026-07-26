# Trading agent — data, signal, backtest, ML, risk, and paper execution

An ML-driven trading agent built as one continuous pipeline: a data
layer, one or more **pluggable signal scanners**, a walk-forward
backtester that scores those signals' real forward returns (plus
out-of-sample validation and statistical significance testing), an ML
model that learns a win probability for new signals, a risk manager that
turns that into position sizes and stop-losses, and an Alpaca
paper-trading execution layer. Every stage reuses the one before it
unchanged — same scanner code the backtester replays date-by-date, same
sizing logic the live agent and any future backtest-of-the-full-strategy
would use.

**Status (2026-07): 6 signals tested, 46 basket/direction/signal cells,
0 confirmed.** Under out-of-sample validation and Bonferroni-corrected
significance testing against real data: the original scanner scored
0/32 significant cells (the best-looking result, `unstable` "dip",
inverted sign between discovery and confirmation: +6.5% mean return
became -3.2%); momentum, relative/cross-sectional, 52-week breakout, and
PEAD scored 0/8 between them (momentum's "up" leg — the academically
well-supported half — went from +0.33 edge in discovery to -0.18 in
confirmation, despite a 7,040-signal sample); fundamentals/earnings-growth
scored 0/2, both directions flipping from ~55% win rate in discovery to
~38% in confirmation; analyst rating changes (upgrades/downgrades — a
genuinely different data category, institutional opinion rather than
price/volume or company fundamentals) scored 0/2 on the correct
confirmation-only check — its "dip" leg looked significant when
significance was computed on the POOLED discovery+confirmation sample
(p=0.014), but failed once tested on confirmation data alone (p=0.656).
That near-miss led directly to `out_of_sample_significance()` /
`basket_out_of_sample_significance()` (see "Statistical significance"
below), which now makes pooled-vs-honest significance an explicit,
impossible-to-conflate choice rather than an easy mistake. See "Known
pitfalls" and the basket/out-of-sample sections below for the full story.

## Structure

```
trading_agent/
├── config.py                    # universe, baskets, thresholds, risk params — the one place to tune things
├── baskets.py                    # overlapping themed groupings (semiconductors, ai_related, ...) + per-basket reports
├── data/
│   ├── market_data.py             # fetch_historical() [yfinance] and generate_synthetic() [offline dev]
│   ├── earnings_data.py           # fetch_earnings_history() + match_effective_date() [yfinance] — for PEAD & fundamentals
│   └── analyst_data.py            # fetch_analyst_actions() [yfinance] — for the analyst rating-change signal
├── signals/
│   ├── scanner.py                  # compute_features() + scan_dips_and_ups() — the ORIGINAL signal, does not hold up (see above)
│   ├── momentum.py                 # scan_momentum() — cross-sectional 12-1 month momentum
│   ├── relative.py                 # scan_relative_dips_and_ups() — same-day move ranked vs. the universe, not own history
│   ├── breakout.py                 # scan_52_week_breakout() — new N-day high/low + volume
│   ├── pead.py                     # scan_pead() — post-earnings-announcement drift (event-driven, needs earnings_data)
│   ├── fundamentals.py             # scan_fundamentals() — YoY reported-EPS growth (event-driven, needs earnings_data)
│   └── analyst.py                  # scan_analyst_actions() — net analyst upgrades/downgrades (event-driven, needs analyst_data)
├── backtest/
│   └── engine.py                  # run_backtest() etc. — pluggable via scan_fn/scan_kwargs, defaults to scan_dips_and_ups
├── ml/
│   └── model.py                   # build_features(), walk_forward_evaluate(), train/save/load, score_signals()
├── risk/
│   └── manager.py                 # size_position(), allocate(), check_stop_loss()
├── execution/
│   └── alpaca_broker.py           # Alpaca paper/live trading — dormant until API keys are set
├── scripts/
│   ├── run_scan_demo.py               # scanner only, synthetic data
│   ├── run_backtest.py                # walk-forward backtest + summary
│   ├── run_backtest_horizons.py       # backtest swept across several hold periods (1 day .. 1 month)
│   ├── run_baseline_comparison.py     # flagged signals vs. "hold any day" baseline (pooled + per-ticker)
│   ├── run_basket_report.py           # backtest/baseline/market results broken out by themed basket
│   ├── run_candidate_horizon_sweep.py # multi-horizon sweep scoped to the current candidate baskets
│   ├── run_out_of_sample_check.py     # discovery vs. confirmation (holdout) check for candidate baskets
│   ├── run_significance_check.py      # bootstrap significance + multiple-comparisons correction, all baskets
│   ├── run_new_signals_report.py      # backtest + out-of-sample check for momentum/relative/breakout
│   ├── train_model.py                 # backtest -> train -> evaluate -> save model
│   └── run_agent.py                   # full pipeline: scan -> score -> size -> (optional) execute
└── tests/
    ├── test_scanner.py
    ├── test_backtest.py
    ├── test_model.py
    ├── test_risk.py
    ├── test_alpaca_broker.py
    ├── test_baskets.py
    ├── test_momentum.py
    ├── test_relative.py
    ├── test_breakout.py
    ├── test_pead.py
    ├── test_fundamentals.py
    └── test_analyst.py
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

**Additional signals (2026-07)** — the original scanner didn't survive
out-of-sample testing (see status note above), so six alternatives with
better academic track records were added, all sharing the exact same
output column contract as `scan_dips_and_ups()` (`ticker, date, close,
return_pct, return_zscore, volume_zscore, direction`) so every backtest/
baseline/market/out-of-sample/significance tool in `backtest/engine.py`
works with any of them unchanged — pass `scan_fn=<the new function>`
(and `scan_kwargs` for its parameters) instead of relying on the default:

- **`signals/momentum.py`** (`scan_momentum`) — cross-sectional "12-1
  month" momentum (Jegadeesh & Titman 1993): ranks the whole universe by
  trailing return, skipping the most recent month, and flags the top
  decile as `"up"` (long continuation). The most replicated anomaly in
  academic finance. The `"dip"` leg (bottom decile) is included only for
  symmetry with this project's dip/up structure — academically that's
  usually the *short* leg, not a long candidate, so treat `"dip"` signals
  from this scanner with extra skepticism. `return_zscore` here is a
  **cross-sectional** z-score (vs. the universe that day), not vs. the
  stock's own history; `volume_zscore` is left `NaN` (momentum isn't
  volume-gated).
- **`signals/relative.py`** (`scan_relative_dips_and_ups`) — the direct
  fix for what broke the original scanner: flags a stock when today's
  move is unusual **relative to the rest of the universe that same day**
  (cross-sectional z-score), not relative to its own history, so a
  market-wide move can't by itself flag everything the way the original
  design could.
- **`signals/breakout.py`** (`scan_52_week_breakout`) — new
  `BREAKOUT_LOOKBACK_DAYS`-day high/low with volume confirmation. The
  `"up"` (new-high continuation) leg is the better-supported half; `"dip"`
  (new-low continuation) is weaker evidence, included for symmetry.
- **`signals/pead.py`** (`scan_pead`) — Post-Earnings-Announcement Drift
  (Bernard & Thomas 1989): flags a stock on the trading day its earnings
  surprise should hit if the surprise exceeds
  `PEAD_SURPRISE_THRESHOLD_PCT`. Arguably the most robust anomaly in the
  literature, but **event-driven, not daily** — needs
  `data/earnings_data.fetch_earnings_history()` (real tickers only, no
  synthetic equivalent) and has a second required argument
  (`earnings_data`), so bind it first: `scan_fn=partial(scan_pead,
  earnings_data=earnings)`. yfinance's free earnings calendar goes back
  further than expected in practice (~2020+ for large caps, ~24 quarters)
  but that's still only ~4 events/ticker/year — a much smaller, noisier
  sample than the daily signals, so treat PEAD results with even more
  small-sample caution than the rest of this project. Earnings timestamps
  at/after market close are shifted to the next trading day
  (`effective_date`), with weekend/holiday spillover handled via
  `data/earnings_data.match_effective_date()` so a single event fires
  exactly once, not on every subsequent day.
- **`signals/fundamentals.py`** (`scan_fundamentals`) — the first
  non-price/volume signal: flags a stock on its earnings date when YoY
  reported EPS growth (this quarter vs. the same quarter one year, i.e.
  4 reports, earlier) exceeds `FUNDAMENTALS_GROWTH_THRESHOLD_PCT`. Built
  from `data/earnings_data.py`'s point-in-time `reported_eps` history
  (each figure indexed by its actual disclosure date), deliberately NOT
  from yfinance's live `Ticker.info` snapshot — that only has today's
  numbers with no real history, so using it on past backtest dates would
  be textbook look-ahead bias. Same event-driven usage pattern and
  data-thinness caveat as PEAD, plus needs 4 prior quarters of history
  per ticker before its first signal can even fire, shrinking the
  usable window further still.
- **`signals/analyst.py`** (`scan_analyst_actions`) — the second
  non-price/volume signal, and a genuinely different data category from
  every other signal here (institutional analyst OPINION — upgrades/
  downgrades/price targets — not the stock's own trading behavior or the
  company's own reported numbers). Flags a stock on a day where net
  analyst upgrades minus downgrades (`data/analyst_data.py`, aggregated
  per ticker per day so multiple same-day firm actions don't each fire
  separately) reaches `ANALYST_MIN_NET_ACTIONS`. Event-driven like PEAD/
  fundamentals, but noticeably denser — analyst actions happen far more
  often per large-cap than earnings (multiple per month, not per
  quarter), so this has a much bigger real sample than the other two
  event-driven signals despite the same data-recency/thinness framing.

None of these six are proven — they're recommendations with better
starting evidence than the original scanner, not validated replacements.
Run `scripts/run_new_signals_report.py` (synthetic data, momentum/
relative/breakout) to sanity-check the plumbing, then point any of them
at real data and run them through the SAME out-of-sample +
`basket_out_of_sample_significance()` toolkit that ruled out the
original scanner before trusting anything they find — not
`basket_significance()` alone (see "Statistical significance" below for
why that distinction matters).

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
  drifting upward during that period. `compare_signal_to_baseline()`
  pools every stock's baseline together, which is simple but can be
  confounded if flagged signals cluster on naturally higher/lower-drift
  stocks than the universe average; `compare_signal_to_baseline_per_ticker()`
  matches each signal only against its own stock's baseline instead,
  removing that confound — trust the per-ticker version over the pooled
  one when they disagree.

**Baskets** — `config.BASKETS` groups the 104-ticker universe (expanded
2026-07 from 48 specifically to thicken thin baskets) into 16 overlapping
themes: `tech` (25), `semiconductors` (9), `ai_related` (12), `unstable`
(6: `TSLA`, `SPCX`, `PLTR`, `COIN`, `MSTR`, `RIVN`), `rare_earth_minerals`
(5: `MP`, `REMX`, `TMC`, `UUUU`, `LAC`), `fintech` (9), plus the original
sector groupings (`mega_cap_tech`, `consumer_discretionary`, `healthcare`,
`financials`, `energy`, `industrials`, `communication_media`,
`utilities`, `software`, `consumer_staples`), all similarly widened. A
ticker can belong to more than one basket on purpose — TSLA is both
`ai_related` and `consumer_discretionary` and `unstable`.
`baskets.compute_high_volatility_basket()` adds one basket computed
empirically from realized daily-return std, as a cross-check against the
hand-curated `unstable` list rather than a replacement for it.
`baskets.summarize_by_basket()`, `compare_baskets_to_baseline()`, and
`compare_baskets_to_market_index()` restrict the backtest/baseline/market
comparisons to each basket's tickers and report results side by side.
**Per-basket ML model training is deliberately not built yet** —
splitting the universe into smaller groups shrinks an already-thin
per-signal sample further, and the pooled 43-ticker model's own
walk-forward accuracy (~48%, close to coin-flip) is a reason for caution
about fragmenting the data more, not a green light to do it per basket.
Basket-level backtest stats are there to see which themes look more
promising before that investment is worth making. With 16 baskets × 2
directions tested at once, watch for the **multiple comparisons
problem**: testing that many combinations means a couple will look
unusually good or bad by pure chance even with zero real edge anywhere —
treat any single standout basket with extra skepticism, not less. This
project's own history proves the point: `rare_earth_minerals` "up"
looked like the best result in the whole project at 16 signals (2
tickers), then weakened sharply once the basket was widened to 5 tickers
and 58 signals — exactly the small-sample-luck failure mode the rest of
this section warns about.

`SPCX` (confirmed by the user, 2026-07, to be a real recent IPO — flagged
here rather than assumed, since it postdates this project's knowledge
cutoff) has only ~1 month of trading history as of this writing, far
short of `ROLLING_WINDOW`/backtest depth — any basket result involving it
is not yet meaningful and should be revisited once it has more history.

`config.MARKET_BENCHMARK_TICKERS` (`SPY`, `QQQ`) are reference series,
never scanned for signals — `compare_signal_to_market_index()` /
`compare_baskets_to_market_index()` match each flagged signal to what the
benchmark itself returned starting that *exact* date, the strictest of
the three baselines this project computes: beat your own history → beat
your own ticker's typical day → beat the whole market on that specific
day.

**Out-of-sample validation (discovery vs. confirmation)** — every
comparison above can be, and has been, rerun on the same historical
window while hunting for a promising basket, which risks mistaking noise
for a finding (see the `rare_earth_minerals` example above).
`out_of_sample_backtest()` / `out_of_sample_baseline_comparison()` /
`out_of_sample_market_comparison()` (and their per-basket versions in
`baskets.py`) split signals by calendar date — using the FULL universe's
date range, not the sparse signal dates, so a handful of signals can't
skew where the split lands — into an earlier **discovery** period and a
later **confirmation** (holdout) period never used to identify anything.
A real edge should look similarly positive in both; one that's strong in
discovery and weak/flipped in confirmation was very likely noise. Run via
`scripts/run_out_of_sample_check.py`.

**Statistical significance** — a mean edge alone doesn't say whether it's
distinguishable from noise. `bootstrap_edge_significance()` bootstraps a
95% confidence interval and p-value for an edge distribution (resampling,
not a parametric t-test, since trade returns are often skewed/fat-tailed).
`bonferroni_threshold()` corrects that significance bar for how many
basket/direction cells are being tested at once — with N cells tested
simultaneously, use alpha/N instead of alpha, since some cells are
expected to look "significant" by chance alone otherwise.

**Pooled vs. out-of-sample significance — use the right one.**
`baskets.basket_significance()` bootstraps the POOLED sample (discovery +
confirmation together) and is exploratory only. `out_of_sample_significance()`
/ `baskets.basket_out_of_sample_significance()` bootstrap discovery and
confirmation SEPARATELY — only a `period == "confirmation"` row with
`significant=True` is real evidence. This distinction isn't theoretical:
the `analyst` "dip" signal's pooled check said `significant=True`
(p=0.014) purely because of a strong discovery-period effect, while the
honest confirmation-only check said `significant=False` (p=0.656, CI
comfortably spanning zero) — pooling let the discovery period's expected
good look drag a misleading p-value out of an honestly-noisy holdout.
Run via `scripts/run_significance_check.py`, which shows both and labels
which one to trust.

**ML model** — `ml/model.py` trains a `RandomForestClassifier` on
backtest output to predict the probability a new signal is a winner,
using features known at signal time (`return_zscore`, `volume_zscore`,
direction, and optionally a **market-regime feature** —
`compute_trailing_market_trend()` computes the benchmark's own trailing
return as of each signal's date, purely backward-looking so it can't leak
future information; pass `benchmark_df` to `build_features()`/
`score_signals()` to include it — omit it to keep the original 3-feature
model). Evaluation is **walk-forward** (`TimeSeriesSplit`), not a random
split — training only ever precedes its test fold chronologically.
`score_signals()` attaches a `win_probability` column to fresh scanner
output; it raises a clear error if the benchmark_df usage doesn't match
what the model was trained with, rather than silently scoring on the
wrong feature set.

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
