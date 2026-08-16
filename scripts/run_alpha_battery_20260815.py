"""Alpha battery — cross-sectional signal research (EXPLORATORY ONLY).

Runs the specifications frozen in
`docs/ALPHA_BATTERY_2026-08-15_PREREGISTRATION.md`. Read that document
first: it records the declared look count, the Bonferroni threshold, and
the three alphas that CANNOT be tested honestly here because this project
has no point-in-time fundamentals.

Nothing in this script proposes, sizes, approves, or submits an order. It
writes one JSON artifact and prints a summary. Prices are yfinance
ADJUSTED closes, so every artifact is stamped `point_in_time_data=false`.

Reuses rather than reimplements, per CLAUDE.md section 8:

  * per-date Spearman IC and quantile spreads -> ml/evaluation.py
  * block-bootstrap significance and Bonferroni -> backtest/engine.py

Freshly written significance code is exactly what this project's standing
rule says to distrust, so none is written here.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from backtest.engine import bonferroni_threshold  # noqa: E402
from ml.evaluation import (  # noqa: E402
    date_level_spearman_ic,
    summarize_information_coefficient,
)

# --- frozen constants (see the pre-registration; do not tune) --------------

TRADING_DAYS = 252
ENTRY_LAG = 1          # signal at close t, position from close t+1
MIN_NAMES = 20         # a cross-sectional rank below this is not a ranking
DECILE = 0.10
QUINTILE = 0.20
COST_BPS = (0.0, 5.0, 10.0, 25.0)
DECLARED_LOOKS = 105   # frozen in the pre-registration
SUBPERIODS = (
    ("2010-2014", "2010-01-01", "2014-12-31"),
    ("2015-2019", "2015-01-01", "2019-12-31"),
    ("2020-2022", "2020-01-01", "2022-12-31"),
    ("2023-present", "2023-01-01", "2100-01-01"),
)
# Declared in the pre-registration, not chosen after seeing results.
WALK_FORWARD = (
    ("train", "2010-01-01", "2018-12-31"),
    ("validation", "2019-01-01", "2022-12-31"),
    ("out_of_sample", "2023-01-01", "2100-01-01"),
)
# REMX is an ETF; the request excludes ETFs and it would otherwise pollute
# every cross-sectional rank with a basket return.
EXCLUDED = frozenset({"REMX"})


class BatteryError(RuntimeError):
    """Refuse rather than produce a plausible-looking number."""


# --- panel construction ----------------------------------------------------


def build_panel(lookback_days: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Wide close and volume frames, dates x tickers.

    Missing cells stay NaN. They are never forward-filled: a synthetic
    price on a day a name did not trade would create a fake zero return
    and a fake reversal signal.
    """
    from data.market_data import fetch_historical

    tickers = [t for t in config.UNIVERSE if t not in EXCLUDED]
    raw = fetch_historical(tickers, lookback_days=lookback_days)
    if not raw:
        raise BatteryError("no price history returned; cannot proceed")

    closes = pd.DataFrame({t: df["close"] for t, df in raw.items()})
    volumes = pd.DataFrame({t: df["volume"] for t, df in raw.items()})
    closes = closes.sort_index()
    volumes = volumes.reindex(index=closes.index, columns=closes.columns)
    closes.index = pd.to_datetime(closes.index).tz_localize(None)
    volumes.index = closes.index
    return closes, volumes


def sector_map() -> dict[str, str]:
    """Ticker -> basket, used as the industry proxy.

    A ticker in several baskets takes the FIRST in a fixed order so the
    mapping is deterministic across runs rather than dictionary-order
    dependent.
    """
    mapping: dict[str, str] = {}
    for basket in sorted(config.BASKETS):
        for ticker in config.BASKETS[basket]:
            mapping.setdefault(ticker, basket)
    return mapping


# --- alpha definitions -----------------------------------------------------
# Each returns a dates x tickers frame of scores. Higher = more bullish.
# Every one uses only data up to and including the row's own date.


def alpha_momentum(closes: pd.DataFrame, months: int) -> pd.DataFrame:
    """price[t-21] / price[t-21*months] - 1. Skips the most recent month."""
    skip, look = 21, 21 * months
    return closes.shift(skip) / closes.shift(look) - 1.0


def alpha_reversal(closes: pd.DataFrame, days: int) -> pd.DataFrame:
    return -(closes / closes.shift(days) - 1.0)


def alpha_industry_adjusted_reversal(
    closes: pd.DataFrame, days: int, sectors: dict[str, str]
) -> pd.DataFrame:
    """Reversal of the part of the move that is not the industry's move."""
    raw = closes / closes.shift(days) - 1.0
    industry_mean = pd.DataFrame(index=raw.index, columns=raw.columns, dtype=float)
    groups: dict[str, list[str]] = {}
    for ticker in raw.columns:
        groups.setdefault(sectors.get(ticker, "_unclassified"), []).append(ticker)
    for members in groups.values():
        # Equal-weighted peer mean. A single-member industry has no peer
        # group, so its "idiosyncratic" move would be identically zero;
        # those cells are left NaN rather than scored as a perfect zero.
        if len(members) < 2:
            continue
        peer_mean = raw[members].mean(axis=1, skipna=True)
        industry_mean.loc[:, members] = np.repeat(
            peer_mean.to_numpy()[:, None], len(members), axis=1
        )
    return -(raw - industry_mean)


def volume_zscore(volumes: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    mean = volumes.rolling(window).mean()
    std = volumes.rolling(window).std()
    return (volumes - mean) / std.replace(0.0, np.nan)


def alpha_max_effect(closes: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """-MAX_20: the lottery-preference direction, tested empirically."""
    returns = closes.pct_change()
    return -returns.rolling(window).max()


def residual_momentum(
    closes: pd.DataFrame, months: int, sectors: dict[str, str], window: int = 252
) -> pd.DataFrame:
    """Cumulative residual return from t-21*months to t-21.

    Betas to the market and to the name's own industry are estimated on a
    rolling window that ENDS at the start of the measurement window, so no
    part of the estimation uses returns from the period being measured.
    """
    returns = closes.pct_change()
    market = returns.mean(axis=1, skipna=True)
    industry = pd.DataFrame(index=returns.index, columns=returns.columns, dtype=float)
    groups: dict[str, list[str]] = {}
    for ticker in returns.columns:
        groups.setdefault(sectors.get(ticker, "_unclassified"), []).append(ticker)
    for members in groups.values():
        if len(members) < 2:
            continue
        peer_mean = returns[members].mean(axis=1, skipna=True)
        industry.loc[:, members] = np.repeat(
            peer_mean.to_numpy()[:, None], len(members), axis=1
        )

    skip, look = 21, 21 * months
    out = pd.DataFrame(index=returns.index, columns=returns.columns, dtype=float)
    market_var = market.rolling(window).var()
    for ticker in returns.columns:
        stock = returns[ticker]
        # Rolling market beta, then residualise against the industry leg on
        # what the market does not explain. Two univariate regressions rather
        # than one joint fit: the industry series is itself heavily loaded on
        # the market, and a joint rolling fit on 252 daily points is badly
        # conditioned when the two regressors are near-collinear.
        cov = stock.rolling(window).cov(market)
        beta_m = cov / market_var.replace(0.0, np.nan)
        resid_m = stock - beta_m.shift(skip) * market
        peer = industry[ticker]
        if peer.notna().any():
            peer_resid = peer - beta_m.shift(skip) * market
            peer_var = peer_resid.rolling(window).var()
            beta_s = resid_m.rolling(window).cov(peer_resid) / peer_var.replace(0.0, np.nan)
            resid = resid_m - beta_s.shift(skip) * peer_resid
        else:
            resid = resid_m
        cumulative = np.log1p(resid.clip(-0.9, None)).rolling(look - skip).sum()
        out[ticker] = cumulative.shift(skip)
    return out


# --- evaluation ------------------------------------------------------------


def forward_returns(closes: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Return from close t+ENTRY_LAG to close t+ENTRY_LAG+horizon."""
    entry = closes.shift(-ENTRY_LAG)
    exit_ = closes.shift(-(ENTRY_LAG + horizon))
    return exit_ / entry - 1.0


def rebalance_dates(index: pd.DatetimeIndex, schedule: str) -> pd.DatetimeIndex:
    if schedule == "daily":
        return index
    if schedule == "monthly":
        frame = pd.Series(index, index=index)
        return pd.DatetimeIndex(frame.groupby([index.year, index.month]).last().values)
    raise BatteryError(f"unknown schedule {schedule!r}")


def long_short_returns(
    scores: pd.DataFrame,
    forwards: pd.DataFrame,
    dates: Sequence[pd.Timestamp],
    construction: str,
    horizon: int,
) -> tuple[pd.Series, pd.Series]:
    """Per-rebalance portfolio return and turnover.

    Turnover is measured as the fraction of the book replaced versus the
    previous rebalance, so a signal that keeps naming the same stocks is
    correctly charged less than one that churns.
    """
    returns: dict[pd.Timestamp, float] = {}
    turnovers: dict[pd.Timestamp, float] = {}
    previous: set[str] = set()
    for date in dates:
        if date not in scores.index or date not in forwards.index:
            continue
        row = scores.loc[date].dropna()
        fwd = forwards.loc[date]
        row = row[row.index.isin(fwd.dropna().index)]
        if len(row) < MIN_NAMES:
            continue
        ranked = row.sort_values(ascending=False)
        cut = max(1, int(round(len(ranked) * (DECILE if construction != "long_only_20" else QUINTILE))))
        longs = list(ranked.index[:cut])
        shorts = list(ranked.index[-cut:]) if construction == "long_short" else []
        long_leg = float(fwd[longs].mean())
        if construction == "long_short":
            short_leg = float(fwd[shorts].mean())
            gross = 0.5 * long_leg - 0.5 * short_leg
            held = set(longs) | set(shorts)
        else:
            gross = long_leg
            held = set(longs)
        if not math.isfinite(gross):
            continue
        churn = 1.0 if not previous else len(held - previous) / max(1, len(held))
        returns[date] = gross
        turnovers[date] = float(churn)
        previous = held
    return pd.Series(returns).sort_index(), pd.Series(turnovers).sort_index()


def net_of_costs(gross: pd.Series, turnover: pd.Series, bps: float) -> pd.Series:
    """Charge both sides of the replaced fraction at each rebalance."""
    return gross - turnover.reindex(gross.index).fillna(1.0) * 2.0 * bps / 10_000.0


def performance(returns: pd.Series, periods_per_year: float) -> dict[str, float | None]:
    clean = pd.to_numeric(returns, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if len(clean) < 12:
        return {"periods": int(len(clean))}
    mean, std = float(clean.mean()), float(clean.std(ddof=1))
    downside = clean[clean < 0]
    equity = (1.0 + clean).cumprod()
    peak = equity.cummax()
    max_dd = float((equity / peak - 1.0).min())
    years = len(clean) / periods_per_year
    cagr = float(equity.iloc[-1] ** (1.0 / years) - 1.0) if years > 0 and equity.iloc[-1] > 0 else None
    ann_vol = std * math.sqrt(periods_per_year)
    sharpe = (mean * periods_per_year) / ann_vol if ann_vol > 0 else None
    dstd = float(downside.std(ddof=1)) if len(downside) > 1 else None
    sortino = (
        (mean * periods_per_year) / (dstd * math.sqrt(periods_per_year))
        if dstd and dstd > 0 else None
    )
    return {
        "periods": int(len(clean)),
        "mean_period_return": mean,
        "annualized_return": mean * periods_per_year,
        "cagr": cagr,
        "annualized_volatility": ann_vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_dd,
        "calmar": (cagr / abs(max_dd)) if cagr is not None and max_dd < 0 else None,
        "win_rate": float((clean > 0).mean()),
        "median_period_return": float(clean.median()),
    }


def stationary_bootstrap_p(returns: pd.Series, draws: int = 2000, seed: int = 20260815) -> float | None:
    """Two-sided p-value for a zero mean under a stationary block bootstrap.

    Blocks, not i.i.d. draws: overlapping holding periods make adjacent
    observations dependent, and i.i.d. resampling would understate the
    standard error exactly where it matters.
    """
    clean = pd.to_numeric(returns, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    n = len(clean)
    if n < 24:
        return None
    values = clean.to_numpy()
    centred = values - values.mean()
    rng = np.random.default_rng(seed)
    block = max(2, int(round(n ** (1 / 3))))
    observed = abs(values.mean())
    count = 0
    for _ in range(draws):
        picks = rng.integers(0, n, size=int(np.ceil(n / block)))
        sample = np.concatenate([
            np.take(centred, range(start, start + block), mode="wrap") for start in picks
        ])[:n]
        if abs(sample.mean()) >= observed:
            count += 1
    return (count + 1) / (draws + 1)


def ic_frame(scores: pd.DataFrame, forwards: pd.DataFrame, dates: Sequence[pd.Timestamp]) -> pd.DataFrame:
    rows = []
    for date in dates:
        if date not in scores.index or date not in forwards.index:
            continue
        s, f = scores.loc[date], forwards.loc[date]
        both = pd.DataFrame({"score": s, "outcome": f}).dropna()
        if len(both) < MIN_NAMES:
            continue
        for ticker, row in both.iterrows():
            rows.append(
                {"as_of_session": date, "ticker": ticker,
                 "score": row["score"], "outcome": row["outcome"]}
            )
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class Spec:
    name: str
    family: str
    schedule: str
    horizon: int
    build: Callable[[pd.DataFrame, pd.DataFrame, dict[str, str]], pd.DataFrame]


def evaluate(spec: Spec, closes: pd.DataFrame, volumes: pd.DataFrame,
             sectors: dict[str, str]) -> dict:
    scores = spec.build(closes, volumes, sectors)
    forwards = forward_returns(closes, spec.horizon)
    dates = rebalance_dates(closes.index, spec.schedule)
    # Non-overlapping evaluation for daily schedules: sampling every
    # `horizon` sessions keeps holding windows disjoint, so the block
    # bootstrap is not asked to undo overlap it cannot see.
    if spec.schedule == "daily" and spec.horizon > 1:
        dates = dates[:: spec.horizon]
    periods_per_year = TRADING_DAYS / spec.horizon if spec.schedule == "daily" else 12.0

    frame = ic_frame(scores, forwards, dates)
    if frame.empty:
        return {"spec": spec.name, "family": spec.family, "usable": False,
                "reason": "no date had enough simultaneously scored and priced names"}
    ic_by_date = date_level_spearman_ic(
        frame, score_column="score", outcome_column="outcome",
        min_names_per_date=MIN_NAMES,
    )
    ic_summary = summarize_information_coefficient(ic_by_date)

    result: dict = {
        "spec": spec.name,
        "family": spec.family,
        "usable": True,
        "schedule": spec.schedule,
        "horizon_days": spec.horizon,
        "rebalances": int(len(ic_by_date)),
        "ic": ic_summary,
        "ic_p_value": stationary_bootstrap_p(ic_by_date),
        "constructions": {},
    }
    for construction in ("long_only_10", "long_only_20", "long_short"):
        gross, turnover = long_short_returns(
            scores, forwards, list(dates), construction, spec.horizon
        )
        if gross.empty:
            continue
        entry = {
            "gross": performance(gross, periods_per_year),
            "mean_turnover": float(turnover.mean()) if len(turnover) else None,
            "p_value_gross": stationary_bootstrap_p(gross),
            "net": {},
            "subperiods": {},
            "walk_forward": {},
        }
        for bps in COST_BPS:
            entry["net"][f"{bps:g}bps"] = performance(
                net_of_costs(gross, turnover, bps), periods_per_year
            )
        for label, start, end in SUBPERIODS:
            window = gross[(gross.index >= start) & (gross.index <= end)]
            if len(window) >= 12:
                entry["subperiods"][label] = performance(
                    net_of_costs(window, turnover, 10.0), periods_per_year
                )
        for label, start, end in WALK_FORWARD:
            window = gross[(gross.index >= start) & (gross.index <= end)]
            if len(window) >= 12:
                entry["walk_forward"][label] = performance(
                    net_of_costs(window, turnover, 10.0), periods_per_year
                )
        result["constructions"][construction] = entry
    return result


def build_specs() -> list[Spec]:
    """Exactly the specifications frozen in the pre-registration."""
    specs: list[Spec] = []
    for months in (3, 6, 9, 12):
        specs.append(Spec(
            f"MOM_{months}_1", "momentum", "monthly", 21,
            lambda c, v, s, m=months: alpha_momentum(c, m),
        ))
    for months in (6, 12):
        specs.append(Spec(
            f"RESIDUAL_MOM_{months}_1", "residual_momentum", "monthly", 21,
            lambda c, v, s, m=months: residual_momentum(c, m, s),
        ))
    for hold in (2, 5, 10):
        specs.append(Spec(
            f"REVERSAL_5D_hold{hold}", "reversal", "daily", hold,
            lambda c, v, s: alpha_reversal(c, 5),
        ))
    for look in (3, 5, 10):
        for hold in (2, 5, 10):
            specs.append(Spec(
                f"INDUSTRY_ADJ_REVERSAL_{look}D_hold{hold}", "industry_reversal",
                "daily", hold,
                lambda c, v, s, d=look: alpha_industry_adjusted_reversal(c, d, s),
            ))
    specs.append(Spec(
        "ABNORMAL_VOLUME_REVERSAL_interaction", "volume_reversal", "daily", 5,
        lambda c, v, s: alpha_reversal(c, 5) * volume_zscore(v).clip(-3, 3),
    ))
    specs.append(Spec(
        "MAX_20_alone", "max_effect", "daily", 5,
        lambda c, v, s: alpha_max_effect(c),
    ))
    specs.append(Spec(
        "MAX_20_x_REVERSAL", "max_effect", "daily", 5,
        lambda c, v, s: alpha_reversal(c, 5) * alpha_max_effect(c).rank(axis=1, pct=True),
    ))
    return specs


def volume_bucket_report(closes: pd.DataFrame, volumes: pd.DataFrame) -> dict:
    """ALPHA 005's conditional test: reversal within abnormal-volume buckets."""
    scores = alpha_reversal(closes, 5)
    zed = volume_zscore(volumes)
    forwards = forward_returns(closes, 5)
    dates = closes.index[::5]
    buckets = {
        "z_below_0": lambda z: z < 0,
        "z_0_to_1": lambda z: (z >= 0) & (z < 1),
        "z_1_to_2": lambda z: (z >= 1) & (z < 2),
        "z_above_2": lambda z: z >= 2,
    }
    out: dict = {}
    for label, predicate in buckets.items():
        rows = []
        for date in dates:
            if date not in scores.index or date not in forwards.index:
                continue
            mask = predicate(zed.loc[date])
            s = scores.loc[date][mask]
            f = forwards.loc[date][mask]
            both = pd.DataFrame({"score": s, "outcome": f}).dropna()
            if len(both) < MIN_NAMES:
                continue
            for ticker, row in both.iterrows():
                rows.append({"as_of_session": date, "ticker": ticker,
                             "score": row["score"], "outcome": row["outcome"]})
        frame = pd.DataFrame(rows)
        if frame.empty:
            out[label] = {"usable": False,
                          "reason": f"fewer than {MIN_NAMES} names per date in this bucket"}
            continue
        ic = date_level_spearman_ic(frame, score_column="score",
                                    outcome_column="outcome",
                                    min_names_per_date=MIN_NAMES)
        out[label] = {
            "usable": True,
            "ic": summarize_information_coefficient(ic),
            "ic_p_value": stationary_bootstrap_p(ic),
        }
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lookback-days", type=int, default=4200)
    parser.add_argument("--output", default="alpha_battery_20260815.json")
    args = parser.parse_args(argv)

    print("Fetching real market data (yfinance, adjusted closes)...", flush=True)
    closes, volumes = build_panel(args.lookback_days)
    sectors = sector_map()
    print(f"panel: {closes.shape[0]} sessions x {closes.shape[1]} tickers "
          f"({closes.index.min().date()} .. {closes.index.max().date()})", flush=True)

    specs = build_specs()
    results = []
    for index, spec in enumerate(specs, start=1):
        print(f"[{index}/{len(specs)}] {spec.name}", flush=True)
        try:
            results.append(evaluate(spec, closes, volumes, sectors))
        except Exception as exc:  # noqa: BLE001 - recorded, never silently dropped
            results.append({"spec": spec.name, "family": spec.family,
                            "usable": False, "reason": f"{type(exc).__name__}: {exc}"})

    print("volume-conditioned buckets...", flush=True)
    buckets = volume_bucket_report(closes, volumes)

    artifact = {
        "generated_for": "docs/ALPHA_BATTERY_2026-08-15_PREREGISTRATION.md",
        "point_in_time_data": False,
        "price_source": "yfinance adjusted closes (exploratory)",
        "survivorship_bias": "present and material; universe has no historical constituents",
        "universe_size": int(closes.shape[1]),
        "sessions": int(closes.shape[0]),
        "first_session": str(closes.index.min().date()),
        "last_session": str(closes.index.max().date()),
        "declared_looks": DECLARED_LOOKS,
        "bonferroni_threshold": bonferroni_threshold(DECLARED_LOOKS),
        "entry_lag_days": ENTRY_LAG,
        "not_run": {
            "ALPHA_009_GROSS_PROFITABILITY": "no point-in-time fundamentals",
            "ALPHA_010_QUALITY_COMPOSITE": "no point-in-time fundamentals",
            "ALPHA_011_QUALITY_MOMENTUM": "quality leg does not exist",
        },
        "specs": results,
        "volume_buckets": buckets,
    }
    path = Path(args.output)
    path.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {path}", flush=True)

    threshold = bonferroni_threshold(DECLARED_LOOKS)
    print(f"\nBonferroni threshold at {DECLARED_LOOKS} declared looks: {threshold:.6f}\n")
    print(f"{'spec':42s} {'meanIC':>8s} {'IC p':>9s} {'LS Sharpe':>10s} {'net10':>8s}")
    for entry in results:
        if not entry.get("usable"):
            print(f"{entry['spec']:42s} {'-':>8s} {'-':>9s}   {entry.get('reason','')[:34]}")
            continue
        ic = entry["ic"]
        ls = entry["constructions"].get("long_short", {})
        gross = ls.get("gross", {})
        net = ls.get("net", {}).get("10bps", {})
        print(
            f"{entry['spec']:42s} "
            f"{_fmt(ic.get('mean_ic'),4):>8s} "
            f"{_fmt(entry.get('ic_p_value'),5):>9s} "
            f"{_fmt(gross.get('sharpe'),2):>10s} "
            f"{_fmt(net.get('sharpe'),2):>8s}"
        )
    return 0


def _fmt(value: float | None, digits: int) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


if __name__ == "__main__":
    raise SystemExit(main())
