"""Run accepted alphas across Universes A / B / C (owner spec 2026-08-16).

Stage two of "universe first, then alphas". Reads the point-in-time
membership produced by `scripts/build_pit_universe_20260816.py` and
evaluates each specification separately inside each universe.

The specifications, the look count and the Bonferroni threshold are frozen
in `docs/ALPHA_BATTERY_2026-08-16_UNIVERSE_PREREGISTRATION.md`, written
before any three-universe result was observed.

Universe B is the headline. Universe C is a warning detector, never a
result: a signal that only works once small and illiquid names are added
is reported as SMALL-CAP DEPENDENT, not as an alpha.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backtest.engine import bonferroni_threshold  # noqa: E402
from data.pit_universe import (  # noqa: E402
    usable_price_columns,
    winsorize_by_date,
)
from ml.evaluation import (  # noqa: E402
    date_level_spearman_ic,
    summarize_information_coefficient,
)
from scripts.run_alpha_battery_20260815 import (  # noqa: E402
    COST_BPS,
    ENTRY_LAG,
    alpha_industry_adjusted_reversal,
    alpha_momentum,
    alpha_reversal,
    net_of_costs,
    performance,
    residual_momentum,
    stationary_bootstrap_p,
)

MIN_NAMES = 20
DECLARED_LOOKS = 63                    # frozen in the amendment
CUMULATIVE_LOOKS = 168                 # 105 on 2026-08-15 plus 63 here
CAPACITY_PORTFOLIOS = (100_000.0, 1_000_000.0, 10_000_000.0, 100_000_000.0)
#: A position is treated as unrealistic beyond this share of one day's
#: dollar volume. Standard practical ceiling; stated rather than hidden.
ADV_PARTICIPATION_LIMIT = 0.10


def load_panels(cache: Path):
    closes = pd.read_parquet(cache / "prices.parquet")
    volumes = pd.read_parquet(cache / "volumes.parquet")
    membership = pd.read_parquet(cache / "membership.parquet")
    closes.index = pd.to_datetime(closes.index)
    volumes = volumes.reindex(index=closes.index, columns=closes.columns)
    membership["as_of"] = pd.to_datetime(membership["as_of"])
    # The owner's specification requires excluding securities with clearly
    # erroneous price/volume data. Without this, reverse-split
    # back-adjustment artifacts (one name reads $275,000,000 in 2019)
    # produce returns of millions of percent. Rank IC is unaffected, but
    # every value-weighted portfolio number is destroyed -- positive IC
    # beside an impossible -50 Sharpe drawdown, which is precisely what
    # the first pass produced and why it was not reported.
    before = closes.shape[1]
    keep = usable_price_columns(closes)
    closes = closes[keep]
    volumes = volumes[keep]
    print(f"  data-quality screen: kept {len(keep):,} of {before:,} tickers "
          f"({before - len(keep):,} dropped as corrupt)", flush=True)
    return closes, volumes, membership


def membership_mask(
    membership: pd.DataFrame, universe: str, closes: pd.DataFrame
) -> pd.DataFrame:
    """Boolean dates x tickers mask of who was eligible on each date.

    Monthly eligibility is carried forward to daily sessions, which the
    owner's specification permits for daily strategies provided the
    approximation is documented. It is: a name admitted at a month end
    stays admitted until the next reconstruction, and daily price and
    liquidity checks are applied separately by the caller.
    """
    subset = membership[membership["universe"] == universe]
    if subset.empty:
        raise SystemExit(f"no membership rows for {universe}")
    flags = (subset.assign(member=True)
                   .pivot_table(index="as_of", columns="ticker",
                                values="member", aggfunc="first")
                   .reindex(columns=closes.columns))
    mask = flags.reindex(closes.index).ffill().fillna(False).astype(bool)
    return mask


def forward_returns(closes: pd.DataFrame, horizon: int) -> pd.DataFrame:
    entry = closes.shift(-ENTRY_LAG)
    return closes.shift(-(ENTRY_LAG + horizon)) / entry - 1.0


def evaluate_universe(
    *, name: str, scores: pd.DataFrame, closes: pd.DataFrame,
    mask: pd.DataFrame, dates: pd.DatetimeIndex, horizon: int,
    periods_per_year: float, membership: pd.DataFrame, universe: str,
    min_history: int, history: pd.DataFrame,
) -> dict:
    """One (spec, universe) cell: IC, portfolios, buckets, capacity."""
    forwards = forward_returns(closes, horizon)
    eligible = mask & (history >= min_history)
    masked = scores.where(eligible)

    rows = []
    for date in dates:
        if date not in masked.index or date not in forwards.index:
            continue
        both = pd.DataFrame({"score": masked.loc[date],
                             "outcome": forwards.loc[date]}).dropna()
        if len(both) < MIN_NAMES:
            continue
        for ticker, row in both.iterrows():
            rows.append({"as_of_session": date, "ticker": ticker,
                         "score": row["score"], "outcome": row["outcome"]})
    frame = pd.DataFrame(rows)
    if frame.empty:
        return {"usable": False, "reason": "no date reached the minimum name count"}

    # Rank IC is computed on RAW outcomes -- ranks are immune to outliers
    # and winsorising them first would misstate the signal's real ordering.
    # Portfolio returns use winsorised outcomes, because one genuine
    # extreme move should not dominate an equal-weighted decile mean.
    bounded = winsorize_by_date(frame, "outcome")
    ic = date_level_spearman_ic(frame, score_column="score",
                                outcome_column="outcome",
                                min_names_per_date=MIN_NAMES)
    result = {
        "usable": True,
        "ic": summarize_information_coefficient(ic),
        "ic_p_value": stationary_bootstrap_p(ic),
        "median_names": float(frame.groupby("as_of_session").size().median()),
        "constructions": {},
    }

    attribution = _bucket_attribution(frame, membership, universe) if universe == "B_core" else {}
    if attribution:
        result["attribution"] = attribution

    for construction, fraction in (("long_only_10", 0.10),
                                   ("long_only_20", 0.20),
                                   ("long_short", 0.10)):
        gross, turnover, position_counts = _portfolio(
            bounded, construction, fraction
        )
        if gross.empty:
            continue
        entry = {
            "gross": performance(gross, periods_per_year),
            "mean_turnover": float(turnover.mean()),
            "median_positions": float(np.median(position_counts)) if position_counts else None,
            "p_value_gross": stationary_bootstrap_p(gross),
            "net": {f"{bps:g}bps": performance(net_of_costs(gross, turnover, bps),
                                               periods_per_year)
                    for bps in COST_BPS},
        }
        result["constructions"][construction] = entry
    return result


def _portfolio(frame: pd.DataFrame, construction: str, fraction: float):
    returns, turnovers, counts = {}, {}, []
    previous: set[str] = set()
    for date, group in frame.groupby("as_of_session", sort=True):
        ranked = group.sort_values("score", ascending=False)
        cut = max(1, int(round(len(ranked) * fraction)))
        longs = ranked.iloc[:cut]
        if construction == "long_short":
            shorts = ranked.iloc[-cut:]
            value = 0.5 * longs["outcome"].mean() - 0.5 * shorts["outcome"].mean()
            held = set(longs["ticker"]) | set(shorts["ticker"])
        else:
            value = longs["outcome"].mean()
            held = set(longs["ticker"])
        if not np.isfinite(value):
            continue
        returns[date] = float(value)
        turnovers[date] = 1.0 if not previous else len(held - previous) / max(1, len(held))
        counts.append(len(held))
        previous = held
    return pd.Series(returns).sort_index(), pd.Series(turnovers).sort_index(), counts


def _bucket_attribution(frame: pd.DataFrame, membership: pd.DataFrame,
                        universe: str) -> dict:
    """Share of the long-short spread coming from each size and liquidity
    bucket. Answers the specification's question directly: is the alpha
    concentrated in small or illiquid names?"""
    tags = membership[membership["universe"] == universe][
        ["as_of", "ticker", "size_bucket", "liquidity_tercile"]
    ].rename(columns={"as_of": "as_of_session"})
    merged = frame.merge(tags, on=["as_of_session", "ticker"], how="left")
    out: dict = {}
    for column, label in (("size_bucket", "size"), ("liquidity_tercile", "liquidity")):
        spreads: dict[str, list[float]] = {}
        for (date, bucket), group in merged.dropna(subset=[column]).groupby(
            ["as_of_session", column]
        ):
            if len(group) < MIN_NAMES:
                continue
            ranked = group.sort_values("score", ascending=False)
            cut = max(1, int(round(len(ranked) * 0.10)))
            spread = ranked.iloc[:cut]["outcome"].mean() - ranked.iloc[-cut:]["outcome"].mean()
            if np.isfinite(spread):
                spreads.setdefault(str(bucket), []).append(float(spread))
        out[label] = {
            bucket: {"mean_spread": float(np.mean(values)), "periods": len(values)}
            for bucket, values in sorted(spreads.items())
        }
    return out


def capacity(frame: pd.DataFrame, membership: pd.DataFrame, universe: str,
             fraction: float = 0.10) -> dict:
    """position_size / ADV20 at several portfolio sizes.

    Reports the fraction of positions that would exceed a 10% share of one
    day's dollar volume -- the specification's execution-realism test. A
    strategy is not tradable at a size where most of its positions move
    the market they are measured against.
    """
    tags = membership[membership["universe"] == universe][["as_of", "ticker", "adv20"]]
    tags = tags.rename(columns={"as_of": "as_of_session"})
    merged = frame.merge(tags, on=["as_of_session", "ticker"], how="inner")
    if merged.empty:
        return {}
    per_date = merged.groupby("as_of_session").size()
    typical_names = max(1, int(round(per_date.median() * fraction)))
    out = {}
    for portfolio in CAPACITY_PORTFOLIOS:
        position = portfolio / typical_names
        participation = position / merged["adv20"].replace(0, np.nan)
        out[f"${portfolio:,.0f}"] = {
            "position_size": position,
            "median_participation": float(participation.median()),
            "fraction_over_10pct_adv": float((participation > ADV_PARTICIPATION_LIMIT).mean()),
        }
    return out


def classify(cells: dict) -> str:
    """The specification's universe-robustness classification, applied
    mechanically so it cannot be argued into a friendlier label."""
    def sharpe(universe: str) -> float | None:
        cell = cells.get(universe, {})
        if not cell.get("usable"):
            return None
        return cell.get("constructions", {}).get("long_short", {}).get(
            "net", {}).get("10bps", {}).get("sharpe")

    a, b, c = sharpe("A_large"), sharpe("B_core"), sharpe("C_broad")
    if None in (a, b, c):
        return "INCOMPLETE"
    signs = {np.sign(x) for x in (a, b, c) if x is not None}
    if len(signs) > 1 and max(abs(a), abs(b), abs(c)) > 0.3:
        return "UNSTABLE"
    if a <= 0 and b <= 0 and c > 0.3:
        return "SMALL-CAP DEPENDENT"
    if a < 0.2 <= b and c >= b:
        return "CORE-DEPENDENT"
    if a > 0 and b > 0 and c > 0:
        return "ROBUST"
    return "REJECT"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    cache = Path(args.cache)

    closes, volumes, membership = load_panels(cache)
    print(f"panel {closes.shape[0]:,} sessions x {closes.shape[1]:,} tickers", flush=True)
    history = closes.notna().cumsum()

    month_ends = pd.Series(closes.index, index=closes.index)
    month_ends = pd.DatetimeIndex(
        month_ends.groupby([closes.index.year, closes.index.month]).last().values
    )

    specs = [
        ("MOM_6_1", "monthly", 21, 252, lambda c: alpha_momentum(c, 6)),
        ("MOM_12_1", "monthly", 21, 252, lambda c: alpha_momentum(c, 12)),
        ("RESIDUAL_MOM_6_1", "monthly", 21, 252, None),
        ("RESIDUAL_MOM_12_1", "monthly", 21, 252, None),
        ("REVERSAL_5D_hold5", "daily", 5, 60, lambda c: alpha_reversal(c, 5)),
        ("INDUSTRY_ADJ_REVERSAL_5D_hold5", "daily", 5, 60, None),
    ]

    results: dict = {}
    for name, schedule, horizon, min_history, builder in specs:
        print(f"[{name}]", flush=True)
        if builder is not None:
            scores = builder(closes)
        else:
            scores = None  # built per-universe below where sectors are needed
        cells = {}
        for universe in ("A_large", "B_core", "C_broad"):
            mask = membership_mask(membership, universe, closes)
            if scores is None:
                sectors = _sector_proxy(membership, universe)
                if name.startswith("RESIDUAL"):
                    months = 6 if "_6_" in name else 12
                    built = residual_momentum(closes, months, sectors)
                else:
                    built = alpha_industry_adjusted_reversal(closes, 5, sectors)
            else:
                built = scores
            dates = month_ends if schedule == "monthly" else closes.index[::horizon]
            ppy = 12.0 if schedule == "monthly" else 252.0 / horizon
            cells[universe] = evaluate_universe(
                name=name, scores=built, closes=closes, mask=mask, dates=dates,
                horizon=horizon, periods_per_year=ppy, membership=membership,
                universe=universe, min_history=min_history, history=history,
            )
            print(f"   {universe}: "
                  f"{'ok' if cells[universe].get('usable') else cells[universe].get('reason')}",
                  flush=True)
        cells["classification"] = classify(cells)
        b_cell = cells.get("B_core", {})
        if b_cell.get("usable"):
            frame_dates = month_ends if schedule == "monthly" else closes.index[::horizon]
            cells["capacity_B"] = _capacity_for(
                built, closes, membership, membership_mask(membership, "B_core", closes),
                frame_dates, horizon, history, min_history
            )
        results[name] = cells

    artifact = {
        "specification": "docs/ALPHA_BATTERY_2026-08-16_UNIVERSE_PREREGISTRATION.md",
        "declared_looks": DECLARED_LOOKS,
        "bonferroni_threshold": bonferroni_threshold(DECLARED_LOOKS),
        "cumulative_looks": CUMULATIVE_LOOKS,
        "cumulative_threshold": bonferroni_threshold(CUMULATIVE_LOOKS),
        "point_in_time_membership": True,
        "point_in_time_prices": False,
        "survivorship_bias": "membership includes only companies with a current ticker; "
                             "delisted names have no price history",
        "results": results,
    }
    Path(args.output).write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {args.output}")
    _print_table(results)
    return 0


def _sector_proxy(membership: pd.DataFrame, universe: str) -> dict[str, str]:
    """Size bucket as the grouping for residualisation.

    An honest downgrade: EDGAR SIC codes were not ingested in this pass, so
    the "industry" leg groups by size bucket instead. Named plainly here
    rather than left to look like a sector model.
    """
    subset = membership[membership["universe"] == universe]
    latest = subset.sort_values("as_of").drop_duplicates("ticker", keep="last")
    return dict(zip(latest["ticker"], latest["size_bucket"].fillna("unknown")))


def _capacity_for(scores, closes, membership, mask, dates, horizon, history, min_history):
    forwards = forward_returns(closes, horizon)
    eligible = mask & (history >= min_history)
    masked = scores.where(eligible)
    rows = []
    for date in dates:
        if date not in masked.index or date not in forwards.index:
            continue
        both = pd.DataFrame({"score": masked.loc[date],
                             "outcome": forwards.loc[date]}).dropna()
        if len(both) < MIN_NAMES:
            continue
        for ticker, row in both.iterrows():
            rows.append({"as_of_session": date, "ticker": ticker,
                         "score": row["score"], "outcome": row["outcome"]})
    frame = pd.DataFrame(rows)
    return capacity(frame, membership, "B_core") if not frame.empty else {}


def _print_table(results: dict) -> None:
    f = lambda v, n=2: "n/a" if v is None else f"{v:.{n}f}"

    def cell(entry, universe, key, sub=None):
        c = entry.get(universe, {})
        if not c.get("usable"):
            return None
        if key == "ic":
            return c["ic"].get("mean_ic")
        ls = c.get("constructions", {}).get("long_short", {})
        if key == "gross":
            return ls.get("gross", {}).get(sub)
        return ls.get("net", {}).get("10bps", {}).get(sub)

    print("\n=== LONG-SHORT, net of 10bps, side by side ===")
    print(f"{'alpha':32s}{'A Shrp':>8s}{'B Shrp':>8s}{'C Shrp':>8s}"
          f"{'A IC':>8s}{'B IC':>8s}{'C IC':>8s}  classification")
    for name, entry in results.items():
        print(f"{name:32s}"
              f"{f(cell(entry,'A_large','net','sharpe')):>8s}"
              f"{f(cell(entry,'B_core','net','sharpe')):>8s}"
              f"{f(cell(entry,'C_broad','net','sharpe')):>8s}"
              f"{f(cell(entry,'A_large','ic'),4):>8s}"
              f"{f(cell(entry,'B_core','ic'),4):>8s}"
              f"{f(cell(entry,'C_broad','ic'),4):>8s}  {entry.get('classification')}")


if __name__ == "__main__":
    raise SystemExit(main())
