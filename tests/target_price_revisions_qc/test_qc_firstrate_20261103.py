"""Synthetic-only FirstRate decoding, identity and no-admission regressions."""
import ast
from dataclasses import FrozenInstanceError
from datetime import timedelta
from decimal import Decimal, localcontext
import hashlib
from pathlib import Path

import pytest

from research.target_price_revisions_qc import firstrate_20261103 as m


def scan(raw=b"2021-02-10 09:30:00,10.10,10.20,10.00,10.15,123\n", **kwargs):
    options = dict(expected_sha256=hashlib.sha256(raw).hexdigest(), symbol="SYNTH",
                   timeframe="minute", member_name="SYNTH_full_1min_UNADJUSTED.txt")
    options.update(kwargs)
    return m.parse_ohlcv(raw, **options)


def refusal(raw, reason, **kwargs):
    with pytest.raises(m.FirstRateRefusal) as failure:
        scan(raw, **kwargs)
    assert failure.value.reason == reason
    assert str(failure.value) == "bounded FirstRate input refused"


def test_exact_decimals_start_end_clocks_and_immutable_values():
    with localcontext() as context:
        context.prec = 2
        dataset = scan()
    bar = dataset.bars[0]
    assert bar.open == Decimal("10.10") and bar.close == Decimal("10.15")
    assert bar.volume == 123
    assert bar.utc_start.isoformat() == "2021-02-10T14:30:00+00:00"
    assert bar.utc_end.isoformat() == "2021-02-10T14:31:00+00:00"
    with pytest.raises(FrozenInstanceError):
        bar.close = Decimal("1")


def test_summer_timezone_and_gaps_are_not_synthesized():
    raw = (b"2021-07-01 09:30:00,10,11,9,10,1\n"
           b"2021-07-01 09:32:00,10,11,9,10,2\n")
    dataset = scan(raw)
    assert len(dataset.bars) == 2
    assert dataset.bars[0].utc_start.hour == 13
    assert dataset.bars[1].utc_start - dataset.bars[0].utc_end == timedelta(minutes=1)
    assert m.diagnostic_report(dataset)["gap_fill_performed"] is False


@pytest.mark.parametrize("clock", ["2021-03-14 02:30:00", "2021-11-07 01:30:00"])
def test_dst_gap_and_fold_require_an_unambiguous_source_clock(clock):
    refusal((clock + ",10,11,9,10,1\n").encode(), "ambiguous_or_nonexistent_clock")


def test_daily_labels_are_not_relabelled_as_native_market_close():
    raw = b"2021-03-14,10,11,9,10,1\n"
    dataset = scan(raw, timeframe="daily", member_name="SYNTH_full_1day_UNADJUSTED.txt")
    bar = dataset.bars[0]
    assert bar.local_start.hour == bar.local_end.hour == 0
    assert bar.utc_end - bar.utc_start == timedelta(hours=23)
    assert m.diagnostic_report(dataset)["daily_interval_is_native_close"] is False


@pytest.mark.parametrize("price", ["0", "-1", "NaN", "Infinity", "1e3", " 1", "1 ", "01", ".1", "1." , "1.0000000000001"])
def test_invalid_or_unbounded_prices_refuse_without_echo(price):
    refusal(("2021-02-10 09:30:00," + price + ",11,9,10,1\n").encode(), "price")


@pytest.mark.parametrize("volume", ["0", "-1", "1.5", "NaN", " 1", "True", "9999999999999999999"])
def test_volume_is_positive_integral_shares(volume):
    refusal(("2021-02-10 09:30:00,10,11,9,10," + volume + "\n").encode(), "volume")


@pytest.mark.parametrize("prices", ["10,9,8,10", "10,11,10.5,11", "10,8,12,10"])
def test_inconsistent_ohlc_geometry_refuses(prices):
    refusal(("2021-02-10 09:30:00," + prices + ",1\n").encode(), "ohlc_geometry")


@pytest.mark.parametrize("second", ["09:30:00", "09:29:00"])
def test_duplicate_and_descending_clocks_are_not_deduplicated_or_sorted(second):
    raw = ("2021-02-10 09:30:00,10,11,9,10,1\n2021-02-10 " + second + ",10,11,9,10,1\n").encode()
    refusal(raw, "duplicate_or_out_of_order")


def test_hash_fails_before_malformed_input_is_decoded():
    refusal(b"\xff", "source_hash", expected_sha256="0" * 64)
    refusal(b"\xff", "encoding")


def test_exact_header_and_utf8_bom_are_supported_without_loose_column_mapping():
    raw = b"\xef\xbb\xbfDateTime,Open,High,Low,Close,Volume\r\n2021-02-10 09:30:00,10,11,9,10,1\r\n"
    assert len(scan(raw).bars) == 1
    refusal(raw.replace(b"Close", b"AdjustedClose"), "minute_clock")


@pytest.mark.parametrize("raw", [b"", b"2021-02-10 09:30:00,10,11,9,10\n", b"\0"])
def test_empty_malformed_and_nul_sources_refuse(raw):
    with pytest.raises(m.FirstRateRefusal):
        scan(raw)


@pytest.mark.parametrize("names", [
    ["../SYNTH_full_1min_UNADJUSTED.txt"],
    ["dir/SYNTH_full_1min_UNADJUSTED.txt"],
    ["C:\\SYNTH_full_1min_UNADJUSTED.txt"],
    ["SYNTH_full_1min_UNADJUSTED.txt", "SYNTH_full_1min_UNADJUSTED.txt"],
    ["SYNTHX_full_1min_UNADJUSTED.txt"],
    ["SYNTH_full_1min_SPLITADJUSTED.txt"],
])
def test_member_selection_has_no_path_or_ticker_prefix_fallback(names):
    with pytest.raises(m.FirstRateRefusal):
        m.select_member(names, symbol="SYNTH", timeframe="minute")


def test_exact_member_selection_and_variant_binding():
    name = "SYNTH_full_1min_UNADJUSTED.txt"
    assert m.select_member(["OTHER.txt", name], symbol="SYNTH", timeframe="minute") == name
    refusal(b"2021-02-10 09:30:00,10,11,9,10,1\n", "adjustment", adjustment="split_adjusted")
    refusal(b"2021-02-10 09:30:00,10,11,9,10,1\n", "member_binding", member_name="OTHER.txt")


def test_pre_inception_identity_anomaly_is_retained_and_quarantined():
    raw = b"2005-01-04,10,11,9,10,1\n2021-02-10,10,11,9,10,2\n"
    dataset = scan(raw, symbol="REMX", timeframe="daily", instrument_kind="etf",
                   member_name="REMX_full_1day_UNADJUSTED.txt")
    report = m.diagnostic_report(dataset)
    assert len(dataset.bars) == report["rows"] == 2
    assert report["pre_inception_rows"] == 1
    assert report["identity_status"] == "QUARANTINED_PRE_INCEPTION"
    assert report["source_inputs_admitted"] is report["financial_acceptance"] is False


def test_coverage_reports_missing_dates_without_claiming_an_authenticated_calendar():
    dataset = scan(b"2021-02-10,10,11,9,10,1\n2021-02-12,10,11,9,10,2\n",
                   timeframe="daily", member_name="SYNTH_full_1day_UNADJUSTED.txt")
    report = m.diagnostic_report(dataset, expected_sessions=["2021-02-10", "2021-02-11", "2021-02-12"])
    assert report["missing_sessions"] == ["2021-02-11"]
    assert report["expected_calendar_authenticated"] is False
    with pytest.raises(m.FirstRateRefusal):
        m.diagnostic_report(dataset, expected_sessions=["2021-02-12", "2021-02-10"])


def test_parsing_and_mutable_report_cannot_grant_any_admission():
    dataset = scan()
    report = m.diagnostic_report(dataset)
    for key in ("source_origin_authenticated", "permanent_sid_bound", "point_in_time_data",
                "source_rights_verified", "native_qc_mark", "source_inputs_admitted",
                "backtesting_ready", "financial_acceptance", "canonical_admission", "trading_authority"):
        assert report[key] is False
        report[key] = True
        assert m.diagnostic_report(dataset)[key] is False
    assert "historical_etf_constituent_membership" in report["required_input_evidence"]
    assert "analyst_target_revision_events_with_firm_ids_and_availability_times" in report["required_input_evidence"]
    with pytest.raises(TypeError):
        scan(financial_acceptance=True)


def test_fixed_byte_and_row_caps_are_enforced(monkeypatch):
    refusal(b"x" * (m.MAX_BYTES + 1), "byte_bound")
    monkeypatch.setattr(m, "MAX_ROWS", 1)
    refusal(b"2021-02-10 09:30:00,10,11,9,10,1\n2021-02-10 09:31:00,10,11,9,10,1\n", "row_bound")


def test_module_has_no_file_network_qc_or_execution_openers():
    tree = ast.parse(Path(m.__file__).read_text())
    imports = {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    imports |= {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert not imports & {"os", "pathlib", "socket", "http", "requests", "subprocess", "sqlite3", "assistant", "execution", "ml", "AlgorithmImports"}
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"open", "eval", "exec", "compile"}]
