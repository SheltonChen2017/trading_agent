"""
Shared calendar utilities for signals that only rebalance on a specific
calendar boundary (currently: month-end).
"""
from __future__ import annotations

import pandas as pd
import pandas_market_calendars as mcal

_NYSE_CALENDAR = mcal.get_calendar("NYSE")


def is_month_end_trading_day(date_index: pd.DatetimeIndex, as_of: pd.Timestamp) -> bool:
    """True iff `as_of` is the ACTUAL last NYSE trading session of its
    calendar month, determined from a real exchange calendar -- NOT from
    whether `as_of` happens to be the last row of whatever `date_index`
    slice was passed in (GPT review, 2026-07-31, reproduced: a private
    `_is_month_end()` duplicated identically across signals/idio_vol.py,
    signals/residual_momentum.py, and signals/variance_risk_premium.py
    treated a dataset fetched only through July 15 as being "month end"
    on July 15, purely because that happened to be the last available
    row -- there was no genuine calendar check at all, only "is there no
    next row, or does the next row belong to a different month").

    `date_index` is accepted (matching every call site's existing
    signature, which already checks `as_of in date_index` beforehand) but
    is otherwise unused for the month-end determination itself now. If
    the real exchange calendar's actual last trading session of `as_of`'s
    month is not even present in the caller's dataset (a short/truncated
    fetch), this correctly returns False for every date in that month --
    the signal simply never fires for a month it doesn't have complete
    data for, rather than firing on the wrong day.
    """
    month_start = as_of.replace(day=1)
    next_month_start = month_start + pd.DateOffset(months=1)
    schedule = _NYSE_CALENDAR.schedule(
        start_date=month_start.date().isoformat(),
        end_date=(next_month_start - pd.Timedelta(days=1)).date().isoformat(),
    )
    if schedule.empty:
        return False
    last_session_of_month = pd.Timestamp(schedule.index[-1]).normalize()
    return as_of.normalize() == last_session_of_month
