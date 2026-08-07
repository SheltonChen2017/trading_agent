"""
Analyst rating-change signal.

Uses institutional analyst upgrade/downgrade actions (firm, grade
change, price target) — a genuinely different data category from every
other signal in this project (price/volume technicals, company
fundamentals): third-party institutional OPINION about a stock, not the
company's own numbers or the stock's own trading behavior.

Flags a stock on a day where the net count of upgrades minus downgrades
among ALL analyst actions that day reaches `min_net_actions` in either
direction — filtering out single-firm noise (e.g. one "maintains" action
alongside one upgrade nets to a real signal; a lone "maintains" with no
upgrade/downgrade doesn't).

Same event-driven usage pattern as PEAD/fundamentals — needs a second
bound argument (`analyst_data`, from
data.analyst_data.fetch_analyst_actions()):

    from functools import partial
    from data.analyst_data import fetch_analyst_actions
    from signals.analyst import scan_analyst_actions

    analyst = fetch_analyst_actions(list(data.keys()))
    run_backtest(data, scan_fn=partial(scan_analyst_actions, analyst_data=analyst), scan_kwargs={})

Same output column contract as scan_dips_and_ups(), with `return_zscore`
repurposed as `net_actions` (an integer count, not a z-score).
"""
from __future__ import annotations

import pandas as pd

from config import ANALYST_MIN_NET_ACTIONS
from data.earnings_data import match_effective_date

RESULT_COLUMNS = ["ticker", "date", "close", "return_pct", "return_zscore", "volume_zscore", "direction"]


def scan_analyst_actions(
    data: dict[str, pd.DataFrame],
    analyst_data: dict[str, pd.DataFrame],
    as_of: pd.Timestamp | None = None,
    min_net_actions: int = ANALYST_MIN_NET_ACTIONS,
) -> pd.DataFrame:
    """
    Flag a stock when `as_of` matches a day with a net excess of analyst
    upgrades over downgrades (or vice versa) of at least
    `min_net_actions`. Requires `analyst_data` (from
    data.analyst_data.fetch_analyst_actions()).
    """
    if as_of is None:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    rows = []
    for ticker, price_df in data.items():
        if ticker not in analyst_data or as_of not in price_df.index:
            continue

        actions = analyst_data[ticker]
        matched = match_effective_date(as_of, actions.index, price_df.index)
        if matched is None:
            continue

        net_actions = int(actions.loc[matched, "net_actions"])
        if abs(net_actions) < min_net_actions:
            continue

        close = float(price_df.loc[as_of, "close"])
        rows.append(
            {
                "ticker": ticker,
                "date": as_of,
                "close": round(close, 2),
                "return_pct": 0.0,
                "return_zscore": float(net_actions),
                "volume_zscore": float("nan"),
                "direction": "up" if net_actions > 0 else "dip",
            }
        )

    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    result = pd.DataFrame(rows)
    return result.reindex(result["return_zscore"].abs().sort_values(ascending=False).index).reset_index(drop=True)
