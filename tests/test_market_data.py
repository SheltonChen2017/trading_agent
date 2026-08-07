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

from data.market_data import _trading_session_start_date, fetch_historical


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
    dates = pd.bdate_range("2025-01-01", periods=300)  # more than the 252 requested

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
    dates = pd.bdate_range("2026-06-01", periods=30)

    def fake_download(tickers, **kwargs):
        return _ohlcv_frame(dates)

    _install_fake_yfinance(fake_download)
    try:
        data = fetch_historical(["NEWCO"], lookback_days=252)
        assert len(data["NEWCO"]) == 30
    finally:
        _remove_fake_yfinance()


def test_multi_ticker_multiindex_columns_format_works():
    dates = pd.bdate_range("2025-01-01", periods=260)
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
    dates = pd.bdate_range("2025-01-01", periods=260)
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


def test_results_are_sorted_and_deduplicated():
    dates = list(pd.bdate_range("2025-01-01", periods=250))
    # Corrupt: out of order, plus a duplicated date.
    shuffled_dates = [dates[5], dates[0]] + dates[1:5] + dates[5:] + [dates[-1]]
    df = _ohlcv_frame(shuffled_dates)

    def fake_download(tickers, **kwargs):
        return df

    _install_fake_yfinance(fake_download)
    try:
        data = fetch_historical(["MESSY"], lookback_days=252)
        result_dates = list(data["MESSY"].index)
        assert result_dates == sorted(result_dates)
        assert len(result_dates) == len(set(result_dates))  # no duplicates survived
    finally:
        _remove_fake_yfinance()


def test_missing_ticker_does_not_corrupt_other_tickers():
    dates = pd.bdate_range("2025-01-01", periods=260)
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
    dates = pd.bdate_range("2025-01-01", periods=260)
    incomplete = pd.DataFrame({"Close": [100.0] * len(dates)}, index=dates)  # no open/high/low/volume

    def fake_download(tickers, **kwargs):
        return incomplete

    _install_fake_yfinance(fake_download)
    try:
        data = fetch_historical(["BADCOLS"], lookback_days=252)
        assert "BADCOLS" not in data
    finally:
        _remove_fake_yfinance()


if __name__ == "__main__":
    test_252_session_request_spans_enough_calendar_days_not_262()
    test_extra_provider_rows_are_trimmed_to_exactly_the_requested_count()
    test_insufficient_history_is_returned_honestly_not_padded()
    test_multi_ticker_multiindex_columns_format_works()
    test_single_ticker_flat_columns_format_works()
    test_results_are_sorted_and_deduplicated()
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
