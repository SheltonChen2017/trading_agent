"""Tests for signals/calendar_utils.py's is_month_end_trading_day()
(GPT review, 2026-07-31). Run with: python -m pytest tests/test_calendar_utils.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from signals.calendar_utils import is_month_end_trading_day


def test_rejects_a_mid_month_date_even_when_it_is_the_last_row():
    # A dataset truncated mid-month (e.g. fetched only through July 15,
    # 2026 -- a Wednesday) used to be treated as "month end" purely
    # because it was the LAST available row in whatever slice was
    # passed in, with no genuine calendar check at all. The real NYSE
    # calendar's actual last trading day of July 2026 is July 31 (a
    # Friday), so July 15 must NOT be classified as month-end even
    # though it's the last row of this truncated index.
    truncated_index = pd.bdate_range("2026-07-01", "2026-07-15")
    as_of = truncated_index[-1]
    assert as_of == pd.Timestamp("2026-07-15")
    assert not is_month_end_trading_day(truncated_index, as_of)


def test_accepts_the_real_last_trading_day_of_the_month():
    full_index = pd.bdate_range("2026-07-01", "2026-08-15")
    assert is_month_end_trading_day(full_index, pd.Timestamp("2026-07-31"))


def test_rejects_a_non_month_end_date_even_with_full_data_available():
    full_index = pd.bdate_range("2026-07-01", "2026-08-15")
    assert not is_month_end_trading_day(full_index, pd.Timestamp("2026-07-15"))


def test_accepts_the_real_last_trading_day_of_a_different_month():
    # August 2026's last trading day: August 31, 2026 is a Monday.
    full_index = pd.bdate_range("2026-08-01", "2026-09-15")
    assert is_month_end_trading_day(full_index, pd.Timestamp("2026-08-31"))
    assert not is_month_end_trading_day(full_index, pd.Timestamp("2026-08-28"))


if __name__ == "__main__":
    test_rejects_a_mid_month_date_even_when_it_is_the_last_row()
    test_accepts_the_real_last_trading_day_of_the_month()
    test_rejects_a_non_month_end_date_even_with_full_data_available()
    test_accepts_the_real_last_trading_day_of_a_different_month()
    print("All calendar_utils tests passed.")
