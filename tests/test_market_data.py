"""
Tests for data/market_data.py's fetch_historical() -- specifically the
lookback_days-as-trading-sessions fix (GPT review, 2026-07-28: a prior
version requested yfinance's period=f"{N+10}d", which is CALENDAR days,
not trading sessions, so a 252-session request returned only ~180-190
actual bars with no indication anything was short).

These tests mock yfinance entirely (via sys.modules) so they never hit
the network. Run with: python tests/test_market_data.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import types

import pandas as pd
import pytest

from data.market_data import (
    _NYSE_CALENDAR,
    _trading_session_start_date,
    canonical_ticker,
    fetch_historical,
    validate_daily_bar_frame,
)


def _sessions(start, periods):
    start_date = pd.Timestamp(start).normalize()
    end_date = start_date + pd.Timedelta(days=periods * 2 + 30)
    sessions = pd.DatetimeIndex(
        _NYSE_CALENDAR.schedule(
            start_date=start_date.date().isoformat(),
            end_date=end_date.date().isoformat(),
        ).index
    ).tz_localize(None)
    assert len(sessions) >= periods
    return sessions[:periods]


def _ohlcv_frame(dates, seed_offset=0.0):
    return pd.DataFrame(
        {
            "Open": [100.0 + seed_offset + i for i in range(len(dates))],
            "High": [101.0 + seed_offset + i for i in range(len(dates))],
            "Low": [99.0 + seed_offset + i for i in range(len(dates))],
            "Close": [100.5 + seed_offset + i for i in range(len(dates))],
            "Volume": [1_000_000 + i for i in range(len(dates))],
        },
        index=pd.DatetimeIndex(dates, name="Date"),
    )


def _install_fake_yfinance(download_fn):
    fake_module = types.ModuleType("yfinance")
    fake_module.download = download_fn
    sys.modules["yfinance"] = fake_module


def _remove_fake_yfinance():
    sys.modules.pop("yfinance", None)


def test_252_session_request_spans_enough_calendar_days_not_262():
    # The bug: period=f"{262}d" is 262 CALENDAR days -- roughly 180-190
    # actual trading sessions, not 252. The fix must request a start date
    # that spans at least 252 REAL trading sessions.
    end = pd.Timestamp("2026-07-27")
    start = pd.Timestamp(_trading_session_start_date(252, end_date=end))
    calendar_days_spanned = (end - start).days
    # 262 calendar days back from 2026-07-27 would land around 2025-11-07;
    # the real fix must reach further back than that to cover 252 SESSIONS.
    naive_262_calendar_day_start = end - pd.Timedelta(days=262)
    assert start < naive_262_calendar_day_start, (
        f"start={start} should be well before the old period='262d' guess "
        f"({naive_262_calendar_day_start}) -- 252 trading sessions need more than 262 calendar days"
    )
    assert calendar_days_spanned > 262


def test_extra_provider_rows_are_trimmed_to_exactly_the_requested_count():
    dates = _sessions("2025-01-01", 300)  # more than the 252 requested

    def fake_download(tickers, **kwargs):
        return _ohlcv_frame(dates)

    _install_fake_yfinance(fake_download)
    try:
        data = fetch_historical(["AAPL"], lookback_days=252)
        assert len(data["AAPL"]) == 252
        assert list(data["AAPL"].index) == list(dates[-252:])
    finally:
        _remove_fake_yfinance()


def test_insufficient_history_is_returned_honestly_not_padded():
    # A recent IPO with only 30 real trading days of history -- must
    # return exactly those 30 rows, never padded/faked up to 252.
    dates = _sessions("2026-06-01", 30)

    def fake_download(tickers, **kwargs):
        return _ohlcv_frame(dates)

    _install_fake_yfinance(fake_download)
    try:
        data = fetch_historical(["NEWCO"], lookback_days=252)
        assert len(data["NEWCO"]) == 30
    finally:
        _remove_fake_yfinance()


def test_multi_ticker_multiindex_columns_format_works():
    dates = _sessions("2025-01-01", 260)
    frame_a = _ohlcv_frame(dates, seed_offset=0.0)
    frame_b = _ohlcv_frame(dates, seed_offset=50.0)
    combined = pd.concat({"AAA": frame_a, "BBB": frame_b}, axis=1)

    def fake_download(tickers, **kwargs):
        return combined

    _install_fake_yfinance(fake_download)
    try:
        data = fetch_historical(["AAA", "BBB"], lookback_days=252)
        assert set(data.keys()) == {"AAA", "BBB"}
        assert len(data["AAA"]) == 252
        assert len(data["BBB"]) == 252
        assert list(data["AAA"].columns) == ["open", "high", "low", "close", "volume"]
        # Confirms AAA and BBB weren't accidentally mixed up.
        assert data["BBB"]["close"].iloc[-1] > data["AAA"]["close"].iloc[-1]
    finally:
        _remove_fake_yfinance()


def test_single_ticker_flat_columns_format_works():
    dates = _sessions("2025-01-01", 260)
    flat = _ohlcv_frame(dates)

    def fake_download(tickers, **kwargs):
        return flat  # no MultiIndex -- single-ticker flat-column shape

    _install_fake_yfinance(fake_download)
    try:
        data = fetch_historical(["SOLO"], lookback_days=252)
        assert len(data["SOLO"]) == 252
        assert list(data["SOLO"].columns) == ["open", "high", "low", "close", "volume"]
    finally:
        _remove_fake_yfinance()


def test_out_of_order_or_duplicate_provider_rows_are_rejected_not_repaired():
    dates = list(_sessions("2025-01-01", 250))
    # Corrupt: out of order, plus a duplicated date.
    shuffled_dates = [dates[5], dates[0]] + dates[1:5] + dates[5:] + [dates[-1]]
    df = _ohlcv_frame(shuffled_dates)

    def fake_download(tickers, **kwargs):
        return df

    _install_fake_yfinance(fake_download)
    try:
        data = fetch_historical(["MESSY"], lookback_days=252)
        assert "MESSY" not in data
    finally:
        _remove_fake_yfinance()


def test_missing_ticker_does_not_corrupt_other_tickers():
    dates = _sessions("2025-01-01", 260)
    frame_a = _ohlcv_frame(dates)
    # "GONE" is requested but not present in the provider's response at all.
    combined = pd.concat({"AAA": frame_a}, axis=1)

    def fake_download(tickers, **kwargs):
        return combined

    _install_fake_yfinance(fake_download)
    try:
        data = fetch_historical(["AAA", "GONE"], lookback_days=252)
        assert "AAA" in data
        assert len(data["AAA"]) == 252
        assert "GONE" not in data  # silently skipped, not a crash
    finally:
        _remove_fake_yfinance()


def test_rows_missing_required_ohlcv_columns_are_skipped():
    dates = _sessions("2025-01-01", 260)
    incomplete = pd.DataFrame({"Close": [100.0] * len(dates)}, index=dates)  # no open/high/low/volume

    def fake_download(tickers, **kwargs):
        return incomplete

    _install_fake_yfinance(fake_download)
    try:
        data = fetch_historical(["BADCOLS"], lookback_days=252)
        assert "BADCOLS" not in data
    finally:
        _remove_fake_yfinance()


def _lower_ohlcv_frame(periods=3):
    frame = _ohlcv_frame(_sessions("2026-07-27", periods))
    frame.columns = [column.lower() for column in frame.columns]
    return frame


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("open", float("nan")),
        ("high", float("inf")),
        ("low", float("-inf")),
        ("close", "not-a-number"),
        ("open", 0.0),
        ("high", -1.0),
        ("low", 0.0),
        ("close", -1.0),
        ("volume", float("nan")),
        ("volume", float("inf")),
        ("volume", -1.0),
        ("volume", True),
    ],
)
def test_validator_rejects_each_invalid_numeric_direction(column, value):
    frame = _lower_ohlcv_frame()
    frame[column] = frame[column].astype(object)
    frame.loc[frame.index[-1], column] = value
    validation = validate_daily_bar_frame("AAA", frame)
    assert validation.usable is False
    assert validation.latest_session is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("high", 99.5),  # below open/close
        ("low", 100.25),  # above open
        ("low", 100.75),  # above close
    ],
)
def test_validator_rejects_impossible_high_low_relationships(field, value):
    frame = _lower_ohlcv_frame()
    frame.loc[frame.index[0], field] = value
    validation = validate_daily_bar_frame("AAA", frame)
    assert validation.usable is False
    assert validation.error == "provider frame contains inconsistent OHLC"


@pytest.mark.parametrize(
    "defect",
    ["non_datetime", "nat", "duplicate", "descending", "weekend", "intraday"],
)
def test_validator_rejects_invalid_session_indices(defect):
    frame = _lower_ohlcv_frame()
    if defect == "non_datetime":
        frame.index = [value.date().isoformat() for value in frame.index]
    elif defect == "nat":
        frame.index = pd.DatetimeIndex([frame.index[0], pd.NaT, frame.index[2]])
    elif defect == "duplicate":
        frame.index = pd.DatetimeIndex(
            [frame.index[0], frame.index[0], frame.index[2]]
        )
    elif defect == "descending":
        frame = frame.iloc[::-1]
    elif defect == "weekend":
        frame.index = pd.DatetimeIndex(
            [frame.index[0], pd.Timestamp("2026-08-01"), frame.index[2]]
        ).sort_values()
    elif defect == "intraday":
        frame.index = frame.index + pd.Timedelta(hours=16)
    validation = validate_daily_bar_frame("AAA", frame)
    assert validation.usable is False


def test_validator_requires_unique_columns_and_all_required_fields():
    missing = _lower_ohlcv_frame().drop(columns=["volume"])
    assert validate_daily_bar_frame("AAA", missing).usable is False

    duplicate = _lower_ohlcv_frame()
    duplicate.columns = ["open", "high", "low", "close", "close"]
    assert validate_daily_bar_frame("AAA", duplicate).usable is False


def test_validator_rejects_numeric_strings_in_uncoerced_provider_output():
    frame = _lower_ohlcv_frame()
    frame["close"] = frame["close"].map(str)
    validation = validate_daily_bar_frame("AAA", frame)
    assert validation.usable is False
    assert "non-numeric required columns" in validation.error


def test_validator_rejects_complex_numeric_values():
    frame = _lower_ohlcv_frame()
    frame["close"] = frame["close"].astype(complex) + 1j
    validation = validate_daily_bar_frame("AAA", frame)
    assert validation.usable is False
    assert "non-numeric required columns" in validation.error


def test_all_field_empty_alignment_padding_is_ignored_but_cannot_be_all_rows():
    frame = _lower_ohlcv_frame()
    frame.loc[frame.index[0], :] = float("nan")
    assert validate_daily_bar_frame("AAA", frame).usable is True

    frame.loc[:, :] = float("nan")
    validation = validate_daily_bar_frame("AAA", frame)
    assert validation.usable is False
    assert validation.error == "provider frame has no usable rows"


def test_validator_accepts_canonicalized_supported_provider_symbols():
    frame = _lower_ohlcv_frame()
    validation = validate_daily_bar_frame("  brk.b ", frame)
    assert validation.usable is True
    assert validation.ticker == "BRK.B"
    assert canonical_ticker(" ^tnx ") == "^TNX"


def test_malformed_ticker_does_not_erase_valid_multi_ticker_sibling():
    dates = _sessions("2026-07-01", 10)
    valid = _ohlcv_frame(dates)
    malformed = _ohlcv_frame(dates, seed_offset=50.0)
    malformed.loc[dates[-1], "High"] = 0.0
    combined = pd.concat({"GOOD": valid, "BAD": malformed}, axis=1)

    _install_fake_yfinance(lambda tickers, **kwargs: combined)
    try:
        data = fetch_historical(["GOOD", "BAD"], lookback_days=10)
        assert set(data) == {"GOOD"}
        assert data["GOOD"].index.equals(dates)
    finally:
        _remove_fake_yfinance()


def test_flat_response_for_multiple_tickers_is_ambiguous_and_rejected():
    dates = _sessions("2026-07-01", 10)
    _install_fake_yfinance(lambda tickers, **kwargs: _ohlcv_frame(dates))
    try:
        assert fetch_historical(["AAA", "BBB"], lookback_days=10) == {}
    finally:
        _remove_fake_yfinance()


if __name__ == "__main__":
    test_252_session_request_spans_enough_calendar_days_not_262()
    test_extra_provider_rows_are_trimmed_to_exactly_the_requested_count()
    test_insufficient_history_is_returned_honestly_not_padded()
    test_multi_ticker_multiindex_columns_format_works()
    test_single_ticker_flat_columns_format_works()
    test_out_of_order_or_duplicate_provider_rows_are_rejected_not_repaired()
    test_missing_ticker_does_not_corrupt_other_tickers()
    test_rows_missing_required_ohlcv_columns_are_skipped()
    print("All market_data tests passed.")


def test_a_transport_failure_remains_visible_to_data_and_research_callers():
    """The low-level data source must not disguise a failed request as empty."""
    import data.market_data as market_data

    real_download = None
    try:
        import yfinance as yf
        real_download = yf.download

        def exploding_download(*args, **kwargs):
            raise ConnectionError("simulated provider outage")

        yf.download = exploding_download
        with pytest.raises(ConnectionError, match="simulated provider outage"):
            market_data.fetch_historical(["SPY"], lookback_days=5)
    finally:
        if real_download is not None:
            yf.download = real_download


def test_a_transport_failure_leaves_the_market_regime_unavailable_not_raised():
    from assistant.context_builder import build_market_regime

    real_download = None
    try:
        import yfinance as yf
        real_download = yf.download

        def exploding_download(*args, **kwargs):
            raise ConnectionError("simulated provider outage")

        yf.download = exploding_download
        regime = build_market_regime("QQQ")
        assert regime.trend is None
        assert regime.volatility_regime is None
        assert regime.benchmark_ticker == "QQQ"
    finally:
        if real_download is not None:
            yf.download = real_download
