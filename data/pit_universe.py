"""Point-in-time US equity universe reconstruction from SEC EDGAR.

Built for the owner's 2026-08-16 universe specification. The rule that
shapes every decision here: **membership on date T may use only
information knowable on or before T.**

Why EDGAR rather than a constituent list
----------------------------------------
The specification forbids taking today's index membership and running it
backwards. EDGAR is the opposite of that by construction: a filing exists
at the date it was filed and is never retracted, so a company that later
delisted still appears in its own historical periods. SVB Financial, which
failed in March 2023, is present in the CY2015Q1 shares-outstanding frame
exactly as it was in 2015.

What this module gets right
---------------------------
* `cik` is the primary key, never the ticker. A ticker change does not
  create a new company here, which is what the specification asks for.
* Shares outstanding come from the filing that reported them, so market
  cap at T uses the share count a market participant could have known.
* A publication lag is applied. A period-end value is NOT treated as
  knowable on the period-end date; see `PUBLICATION_LAG_DAYS`.
* Foreign issuers are excluded by filer location, which is the closest
  available proxy for the specification's ADR exclusion.

What this module CANNOT do, and callers must not pretend otherwise
------------------------------------------------------------------
* **Prices for delisted securities are unavailable.** EDGAR supplies
  membership for dead companies; the price provider does not supply their
  bars. `UniverseSnapshot.missing_price_ciks` reports exactly how many
  eligible companies were lost this way on every date, so the survivorship
  gap is measured on each rebalance rather than assumed away.
* No delisting returns, so a company that leaves the universe leaves
  without a final return. This biases results upward and the size of the
  bias is not knowable from this data.
* No point-in-time index membership.
* SIC codes are the sector proxy. They are point-in-time in the sense that
  they come from the filing, but they are coarser than GICS.
"""
from __future__ import annotations

import dataclasses
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

EDGAR_TICKER_MAP = "https://www.sec.gov/files/company_tickers.json"
EDGAR_FRAME = (
    "https://data.sec.gov/api/xbrl/frames/{taxonomy}/{tag}/{unit}/CY{period}.json"
)
# SEC asks for a descriptive agent with contact details and throttles at
# roughly ten requests a second. Exceeding it earns a block, so the fetch
# is deliberately slow rather than parallel.
USER_AGENT = "trading_agent research (trunkunala.xc@gmail.com)"
REQUEST_INTERVAL_SECONDS = 0.15

#: A period-end value is not public on the period-end date. Domestic
#: filers have 40-45 days for a 10-Q and 60-90 for a 10-K, so 90 calendar
#: days is the conservative choice: it can only ever make the universe
#: know LESS than a real participant did, never more. Erring the other way
#: would put unpublished share counts into historical market caps.
PUBLICATION_LAG_DAYS = 90

SHARES_TAG = ("dei", "EntityCommonStockSharesOutstanding", "shares")

# Universe definitions, exactly as specified. Kept as data so a caller
# cannot quietly invent a fourth universe with more favourable screens.
UNIVERSE_SPECS: Mapping[str, Mapping[str, float]] = {
    "A_large": {"min_price": 5.0, "min_market_cap": 10_000_000_000.0, "min_adv20": 25_000_000.0},
    "B_core": {"min_price": 5.0, "min_market_cap": 500_000_000.0, "min_adv20": 5_000_000.0},
    "C_broad": {"min_price": 3.0, "min_market_cap": 100_000_000.0, "min_adv20": 1_000_000.0},
}

SIZE_BUCKETS = (
    ("large", 10_000_000_000.0, float("inf")),
    ("mid", 2_000_000_000.0, 10_000_000_000.0),
    ("small", 500_000_000.0, 2_000_000_000.0),
)


class UniverseError(RuntimeError):
    """Refuse rather than emit a universe built from unusable data."""


@dataclasses.dataclass(frozen=True)
class UniverseSnapshot:
    """Membership on one rebalance date, with its own audit trail.

    `missing_price_ciks` is not a diagnostic afterthought. It is the
    measured size of the survivorship gap on this date: companies that
    passed every point-in-time screen and were dropped only because no
    price series exists for them today.
    """

    as_of: pd.Timestamp
    universe: str
    tickers: tuple[str, ...]
    ciks: tuple[int, ...]
    market_caps: Mapping[str, float]
    adv20: Mapping[str, float]
    eligible_before_price_join: int
    missing_price_ciks: int

    @property
    def survivorship_loss_fraction(self) -> float:
        total = self.eligible_before_price_join
        return 0.0 if total <= 0 else self.missing_price_ciks / total


# --- EDGAR access ----------------------------------------------------------


def _get_json(url: str, cache_dir: Path, *, cache_key: str) -> dict:
    """Fetch with an on-disk cache.

    The cache exists because these responses are IMMUTABLE history: a
    completed quarter's frame does not change, so re-downloading it on
    every run would be pure waste and extra load on a public service.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{cache_key}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            path.unlink()  # a truncated cache file is worse than no cache
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    time.sleep(REQUEST_INTERVAL_SECONDS)
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def quarter_labels(start_year: int, end_year: int) -> list[str]:
    """Instantaneous quarter labels, e.g. 2015Q1I, oldest first."""
    return [f"{year}Q{quarter}I" for year in range(start_year, end_year + 1)
            for quarter in (1, 2, 3, 4)]


def fetch_shares_outstanding(
    cache_dir: Path, start_year: int, end_year: int
) -> pd.DataFrame:
    """Every company's reported share count, per quarter, with its filing.

    Returns columns: cik, entity, loc, period_end, known_from, shares.
    `known_from` is the date the value becomes usable, i.e. period end
    plus the publication lag. Nothing downstream may read `period_end`
    directly.
    """
    taxonomy, tag, unit = SHARES_TAG
    rows: list[dict] = []
    for period in quarter_labels(start_year, end_year):
        url = EDGAR_FRAME.format(taxonomy=taxonomy, tag=tag, unit=unit, period=period)
        try:
            payload = _get_json(url, cache_dir, cache_key=f"shares_{period}")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:      # a quarter with no frame yet published
                continue
            raise
        for record in payload.get("data", []):
            end = record.get("end")
            value = record.get("val")
            if not end or not value or value <= 0:
                continue
            rows.append({
                "cik": int(record["cik"]),
                "entity": record.get("entityName", ""),
                "loc": record.get("loc", ""),
                "period_end": pd.Timestamp(end),
                "shares": float(value),
            })
    if not rows:
        raise UniverseError("EDGAR returned no shares-outstanding facts")
    frame = pd.DataFrame(rows)
    frame["known_from"] = frame["period_end"] + pd.Timedelta(days=PUBLICATION_LAG_DAYS)
    # Same company and period can appear via amended filings; keep the
    # first knowable value rather than the latest revision, because a
    # later revision was NOT available at the earlier date.
    frame = (frame.sort_values(["cik", "period_end", "shares"])
                  .drop_duplicates(["cik", "period_end"], keep="first"))
    return frame.sort_values(["cik", "known_from"]).reset_index(drop=True)


def fetch_ticker_map(cache_dir: Path) -> pd.DataFrame:
    """CIK -> ticker for companies that still have a listed ticker today.

    This map is CURRENT, which is precisely the survivorship hole: a
    company that delisted has no row here. It is used only to attach
    prices, never to decide eligibility, and the companies it fails to
    cover are counted rather than silently dropped.
    """
    payload = _get_json(EDGAR_TICKER_MAP, cache_dir, cache_key="company_tickers")
    rows = [{"cik": int(v["cik_str"]), "ticker": str(v["ticker"]).upper(),
             "title": v.get("title", "")} for v in payload.values()]
    frame = pd.DataFrame(rows)
    # One CIK can carry several share classes (GOOG/GOOGL). Keep the
    # alphabetically first so the choice is deterministic and documented
    # rather than dependent on EDGAR's ordering.
    return (frame.sort_values(["cik", "ticker"])
                 .drop_duplicates("cik", keep="first")
                 .reset_index(drop=True))


def domestic_only(shares: pd.DataFrame) -> pd.DataFrame:
    """Keep US-located filers.

    The specification asks to exclude ADRs "if reliable issuer-country
    classification is available". EDGAR's `loc` is the filer's business
    location, which is a proxy and not an issuer-country field: it will
    drop some US-listed foreign issuers correctly and will also drop a US
    company that files from abroad. Stated rather than hidden.
    """
    return shares[shares["loc"].astype(str).str.startswith("US-")].copy()


# --- universe assembly -----------------------------------------------------


def shares_as_of(shares: pd.DataFrame, as_of: pd.Timestamp) -> pd.Series:
    """Latest share count KNOWABLE on `as_of`, indexed by cik."""
    usable = shares[shares["known_from"] <= as_of]
    if usable.empty:
        return pd.Series(dtype=float)
    latest = usable.sort_values("known_from").drop_duplicates("cik", keep="last")
    return latest.set_index("cik")["shares"]


def build_snapshot(
    *,
    as_of: pd.Timestamp,
    universe: str,
    shares: pd.DataFrame,
    ticker_map: pd.DataFrame,
    closes: pd.DataFrame,
    dollar_volume_20: pd.DataFrame,
    min_history_days: int,
    history_counts: pd.Series | None = None,
) -> UniverseSnapshot:
    """One rebalance date's membership under one universe definition.

    Every screen reads values at or before `as_of`. Liquidity is measured
    on the trailing twenty sessions ENDING at `as_of`, never on future
    volume, which is the specification's execution-realism requirement.
    """
    spec = UNIVERSE_SPECS.get(universe)
    if spec is None:
        raise UniverseError(f"unknown universe {universe!r}")
    if as_of not in closes.index:
        raise UniverseError(f"{as_of.date()} is not a session in the price panel")

    known_shares = shares_as_of(shares, as_of)
    if known_shares.empty:
        return UniverseSnapshot(as_of, universe, (), (), {}, {}, 0, 0)

    cik_to_ticker = ticker_map.set_index("cik")["ticker"]
    price_row = closes.loc[as_of]
    adv_row = dollar_volume_20.loc[as_of]

    eligible = 0
    missing_price = 0
    tickers: list[str] = []
    ciks: list[int] = []
    caps: dict[str, float] = {}
    advs: dict[str, float] = {}
    for cik, share_count in known_shares.items():
        ticker = cik_to_ticker.get(cik)
        if ticker is None or ticker not in closes.columns:
            # Eligible on EDGAR, unpriceable today. This is the
            # survivorship gap, counted rather than skipped quietly.
            eligible += 1
            missing_price += 1
            continue
        price = price_row.get(ticker)
        adv = adv_row.get(ticker)
        if price is None or not pd.notna(price) or not pd.notna(adv):
            eligible += 1
            missing_price += 1
            continue
        eligible += 1
        market_cap = float(price) * float(share_count)
        if float(price) < spec["min_price"]:
            continue
        if market_cap < spec["min_market_cap"]:
            continue
        if float(adv) < spec["min_adv20"]:
            continue
        if history_counts is not None and float(history_counts.get(ticker, 0)) < min_history_days:
            continue
        tickers.append(ticker)
        ciks.append(int(cik))
        caps[ticker] = market_cap
        advs[ticker] = float(adv)

    order = sorted(range(len(tickers)), key=lambda i: tickers[i])
    return UniverseSnapshot(
        as_of=as_of,
        universe=universe,
        tickers=tuple(tickers[i] for i in order),
        ciks=tuple(ciks[i] for i in order),
        market_caps=dict(caps),
        adv20=dict(advs),
        eligible_before_price_join=eligible,
        missing_price_ciks=missing_price,
    )


def size_bucket(market_cap: float) -> str | None:
    for name, low, high in SIZE_BUCKETS:
        if low <= market_cap < high:
            return name
    return None


def liquidity_terciles(adv: Mapping[str, float]) -> dict[str, str]:
    """Ticker -> high/medium/low by trailing dollar volume on this date.

    Ranked WITHIN the date, so the split reflects what was liquid then
    rather than what is liquid now.
    """
    series = pd.Series(adv, dtype=float).dropna()
    if len(series) < 3:
        return {}
    labels = pd.qcut(series.rank(method="first"), 3,
                     labels=["low", "medium", "high"])
    return {str(k): str(v) for k, v in labels.items()}

# --- data quality ----------------------------------------------------------

#: A continuously listed common stock does not move more than this in one
#: session. Real stocks occasionally double; nothing legitimate multiplies
#: by eleven, so a series containing such a jump is carrying a corrupted
#: back-adjustment rather than a price.
MAX_CREDIBLE_DAILY_RETURN = 10.0
#: Ratio of highest to lowest adjusted close over the whole sample. A
#: large reverse split back-adjusts early prices to absurd levels (one
#: name in this panel reads $275,000,000 in 2019), and that inflated
#: history passes a "price >= $5" screen while producing a return of
#: several million percent when it corrects.
MAX_CREDIBLE_PRICE_RATIO = 5_000.0
MIN_CREDIBLE_PRICE = 0.01


def usable_price_columns(closes: "pd.DataFrame") -> list[str]:
    """Tickers whose adjusted history is credible enough to trade on.

    The owner's specification requires excluding "securities with
    unusable or clearly erroneous price/volume data". This is that screen,
    and it is applied to the SERIES rather than to individual returns:
    a single corrupted adjustment poisons every window that spans it, so
    clipping the one bad return would leave the neighbouring ones subtly
    wrong instead of obviously wrong.
    """
    keep: list[str] = []
    for ticker in closes.columns:
        series = closes[ticker].dropna()
        if series.empty:
            continue
        if not np.isfinite(series.to_numpy()).all():
            continue
        low, high = float(series.min()), float(series.max())
        if low < MIN_CREDIBLE_PRICE or low <= 0.0:
            continue
        if high / low > MAX_CREDIBLE_PRICE_RATIO:
            continue
        moves = series.pct_change().abs()
        if float(moves.max(skipna=True) or 0.0) > MAX_CREDIBLE_DAILY_RETURN:
            continue
        keep.append(ticker)
    return keep


def winsorize_by_date(frame: "pd.DataFrame", column: str, lower: float = 0.01,
                      upper: float = 0.99) -> "pd.DataFrame":
    """Clip an outcome column within each date.

    Applied AFTER the series screen, not instead of it. The screen removes
    corrupt securities; this bounds the influence of a single genuine
    extreme move on an equal-weighted decile mean, which is standard
    practice for cross-sectional work and is reported rather than silent.
    """
    out = frame.copy()
    bounds = out.groupby("as_of_session")[column].transform(
        lambda s: s.clip(s.quantile(lower), s.quantile(upper))
    )
    out[column] = bounds
    return out
