"""Build the point-in-time universe panel (owner spec, 2026-08-16).

Stage one of "universe first, then alphas". This script produces and
audits the universe itself; it runs no alpha and makes no trading claim.

Outputs, all under `--cache`:

  prices.parquet       adjusted close panel for return calculations
  screen_prices.parquet unadjusted close panel for price/cap screens
  volumes.parquet      share volume panel, same shape
  membership.parquet   one row per (date, universe, ticker) with the
                       market cap, ADV20, size bucket and liquidity
                       tercile that were TRUE ON THAT DATE
  universe_audit.json  per-date counts, including the measured
                       survivorship gap

Reproducibility: membership is written out in full, so any later alpha
run can be checked against the exact set of names it was allowed to see.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.pit_universe import (  # noqa: E402
    UNIVERSE_SPECS,
    UNIVERSE_SCHEMA_VERSION,
    build_snapshot,
    domestic_only,
    fetch_shares_outstanding,
    fetch_ticker_map,
    liquidity_terciles,
    size_bucket,
    usable_price_columns,
)

BATCH = 120          # yfinance degrades badly on very large ticker lists
MIN_SESSIONS = 60    # below this a name cannot satisfy any history rule


def fetch_prices(
    tickers: list[str], start: str, cache: Path
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Batched download with per-batch caching.

    Each batch is cached separately so an interrupted run resumes instead
    of restarting a multi-hour download.
    """
    import yfinance as yf

    closes: list[pd.DataFrame] = []
    screen_closes: list[pd.DataFrame] = []
    volumes: list[pd.DataFrame] = []
    batch_dir = cache / "price_batches"
    batch_dir.mkdir(parents=True, exist_ok=True)

    for index in range(0, len(tickers), BATCH):
        chunk = tickers[index:index + BATCH]
        tag = f"{index:05d}"
        close_path = batch_dir / f"close_{tag}.parquet"
        screen_close_path = batch_dir / f"screen_close_{tag}.parquet"
        volume_path = batch_dir / f"volume_{tag}.parquet"
        if close_path.exists() and screen_close_path.exists() and volume_path.exists():
            closes.append(pd.read_parquet(close_path))
            screen_closes.append(pd.read_parquet(screen_close_path))
            volumes.append(pd.read_parquet(volume_path))
            continue
        for attempt in range(3):
            try:
                raw = yf.download(chunk, start=start, interval="1d",
                                  group_by="ticker", auto_adjust=False,
                                  progress=False, threads=True)
                break
            except Exception as exc:  # noqa: BLE001 - transient provider errors
                if attempt == 2:
                    print(f"  batch {tag} FAILED: {type(exc).__name__}", flush=True)
                    raw = None
                    break
                time.sleep(5 * (attempt + 1))
        if raw is None or raw.empty:
            continue
        close_cols, screen_close_cols, volume_cols = {}, {}, {}
        for ticker in chunk:
            try:
                frame = raw[ticker] if isinstance(raw.columns, pd.MultiIndex) else raw
            except KeyError:
                continue
            frame.columns = [str(c).lower() for c in frame.columns]
            if not {"close", "adj close", "volume"}.issubset(frame.columns):
                continue
            series = frame["adj close"].dropna()
            if len(series) < MIN_SESSIONS:
                continue
            close_cols[ticker] = frame["adj close"]
            screen_close_cols[ticker] = frame["close"]
            volume_cols[ticker] = frame["volume"]
        if not close_cols:
            continue
        close_frame = pd.DataFrame(close_cols)
        screen_close_frame = pd.DataFrame(screen_close_cols)
        volume_frame = pd.DataFrame(volume_cols)
        close_frame.to_parquet(close_path)
        screen_close_frame.to_parquet(screen_close_path)
        volume_frame.to_parquet(volume_path)
        closes.append(close_frame)
        screen_closes.append(screen_close_frame)
        volumes.append(volume_frame)
        print(f"  batch {tag}: {len(close_cols)}/{len(chunk)} usable", flush=True)

    if not closes:
        raise SystemExit("no price data downloaded")
    close_panel = pd.concat(closes, axis=1).sort_index()
    screen_close_panel = pd.concat(screen_closes, axis=1).reindex(
        index=close_panel.index, columns=close_panel.columns
    )
    volume_panel = pd.concat(volumes, axis=1).reindex(
        index=close_panel.index, columns=close_panel.columns
    )
    close_panel.index = pd.to_datetime(close_panel.index).tz_localize(None)
    screen_close_panel.index = close_panel.index
    volume_panel.index = close_panel.index
    return close_panel, screen_close_panel, volume_panel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--start", default="2009-06-01")
    parser.add_argument("--start-year", type=int, default=2009)
    parser.add_argument("--end-year", type=int, default=2026)
    args = parser.parse_args(argv)
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)

    print("EDGAR: shares outstanding + ticker map", flush=True)
    shares = domestic_only(fetch_shares_outstanding(cache, args.start_year, args.end_year))
    ticker_map = fetch_ticker_map(cache)
    priceable = sorted(set(ticker_map["cik"]) & set(shares["cik"]))
    tickers = sorted(ticker_map[ticker_map["cik"].isin(priceable)]["ticker"])
    print(f"  {shares['cik'].nunique():,} US filers, {len(tickers):,} with a current ticker",
          flush=True)

    print(f"prices for {len(tickers):,} tickers (batched, cached)", flush=True)
    closes, screen_closes, volumes = fetch_prices(tickers, args.start, cache)
    # Remove corrupted adjusted histories before they can affect membership,
    # market-cap screens, ADV, or the audit counts.
    keep = usable_price_columns(closes)
    closes = closes[keep]
    screen_closes = screen_closes[keep]
    volumes = volumes[keep]
    closes.to_parquet(cache / "prices.parquet")
    screen_closes.to_parquet(cache / "screen_prices.parquet")
    volumes.to_parquet(cache / "volumes.parquet")
    print(f"  panel: {closes.shape[0]:,} sessions x {closes.shape[1]:,} tickers", flush=True)

    dollar_volume = (screen_closes * volumes).rolling(20).mean()
    history = closes.notna().cumsum()

    month_ends = pd.Series(closes.index, index=closes.index)
    month_ends = pd.DatetimeIndex(
        month_ends.groupby([closes.index.year, closes.index.month]).last().values
    )

    rows: list[dict] = []
    audit: list[dict] = []
    for as_of in month_ends:
        for universe in UNIVERSE_SPECS:
            snapshot = build_snapshot(
                as_of=as_of, universe=universe, shares=shares,
                ticker_map=ticker_map, closes=closes,
                screen_closes=screen_closes,
                dollar_volume_20=dollar_volume, min_history_days=MIN_SESSIONS,
                history_counts=history.loc[as_of],
            )
            liquidity = liquidity_terciles(snapshot.adv20)
            for ticker in snapshot.tickers:
                cap = snapshot.market_caps[ticker]
                rows.append({
                    "as_of": as_of, "universe": universe, "ticker": ticker,
                    "universe_schema_version": UNIVERSE_SCHEMA_VERSION,
                    "market_cap": cap, "adv20": snapshot.adv20[ticker],
                    "size_bucket": size_bucket(cap),
                    "liquidity_tercile": liquidity.get(ticker),
                })
            audit.append({
                "as_of": str(as_of.date()), "universe": universe,
                "members": len(snapshot.tickers),
                "candidate_filers_before_price_join": snapshot.candidate_filers_before_price_join,
                "missing_current_ticker_or_price": snapshot.missing_current_ticker_or_price,
                "price_coverage_gap_fraction": snapshot.price_coverage_gap_fraction,
            })
        if as_of.month == 12:
            counts = {a["universe"]: a["members"] for a in audit if a["as_of"] == str(as_of.date())}
            print(f"  {as_of.date()}  " +
                  "  ".join(f"{k}={v}" for k, v in counts.items()), flush=True)

    membership = pd.DataFrame(rows)
    membership.to_parquet(cache / "membership.parquet")
    (cache / "universe_audit.json").write_text(
        json.dumps({
            "point_in_time_data": False,
            "universe_schema_version": UNIVERSE_SCHEMA_VERSION,
            "point_in_time_caveat": (
                "Share counts use actual SEC filing dates and market-cap screens use "
                "unadjusted historical closes. Ticker identity and prices are current-provider "
                "data, security type and venue are not verified point-in-time, and delisted "
                "securities have no price history. This is not a point-in-time universe."
            ),
            "survivorship_bias": "present and not measurable from this dataset",
            "coverage_gap": "current-ticker/price join gap reported in `by_date`; not survivorship loss",
            "universes": {k: dict(v) for k, v in UNIVERSE_SPECS.items()},
            "by_date": audit,
        }, indent=2), encoding="utf-8")

    print("\nmedian members per universe:")
    frame = pd.DataFrame(audit)
    for universe in UNIVERSE_SPECS:
        subset = frame[frame["universe"] == universe]
        print(f"  {universe:9s} median {subset['members'].median():6.0f}   "
              f"min {subset['members'].min():5.0f}   max {subset['members'].max():5.0f}")
    print(f"\ncurrent-ticker/price coverage gap (median across dates): "
          f"{frame['price_coverage_gap_fraction'].median():.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
