"""Synthetic exact representation repair and complete quarantine provenance."""
import base64
from dataclasses import FrozenInstanceError, replace
from decimal import Inexact, Rounded, localcontext
import hashlib
import json

import pytest

from research.target_price_revisions_qc import firstrate_20261103 as strict
from research.target_price_revisions_qc import remx_repair_20261103 as m


def line(day="2021-02-10", volume="123", *, ending="\n", prices="10,11,9,10"):
    return (day + "," + prices + "," + volume + ending).encode()


def repair(raw):
    return m.repair_remx_daily(raw, expected_sha256=hashlib.sha256(raw).hexdigest())


def manifest(result):
    return json.loads(m.export_blobs(result)["manifest.json"])


def test_complete_original_ledger_and_partition_reconstruction():
    raw = line("2005-01-04", "123") + line("2021-02-10", "123.0") + line("2021-02-11", "123.25") + line("2021-02-12", "456")
    result = repair(raw)
    blobs, summary = m.export_blobs(result), manifest(result)
    assert result.source_raw == blobs["source_original.csv"] == raw
    assert [row.ordinal for row in result.rows] == [1, 2, 3, 4]
    assert b"".join(row.raw_line for row in result.rows) == raw
    assert blobs["quarantine_pre_inception.csv"] == line("2005-01-04", "123")
    assert blobs["quarantine_fractional_volume.csv"] == line("2021-02-11", "123.25")
    assert result.candidate_bytes == line("2021-02-10", "123") + line("2021-02-12", "456")
    assert summary["source_rows"] == 4 and summary["candidate_rows"] == 2
    assert summary["missing_post_inception_source_dates"] == ["2021-02-11"]
    ledger = [json.loads(row) for row in blobs["row_ledger.jsonl"].splitlines()]
    assert b"".join(base64.b64decode(row["raw_line_base64"]) for row in ledger) == raw
    assert all(row["raw_line_sha256"] == hashlib.sha256(base64.b64decode(row["raw_line_base64"])).hexdigest() for row in ledger)
    assert ledger[1]["original_fields"][-1] == "123.0"
    for name, descriptor in summary["outputs"].items():
        assert descriptor == {"bytes": len(blobs[name]), "sha256": hashlib.sha256(blobs[name]).hexdigest()}


@pytest.mark.parametrize("lexeme", ["123.0", "123.0000", "1.23E+2", "12300e-2", ".123e3", "+123", "000123.000", "123."])
def test_integral_representations_normalize_without_loss_or_rounding(lexeme):
    with localcontext() as context:
        context.prec = 2
        context.traps[Inexact] = context.traps[Rounded] = True
        result = repair(line(volume=lexeme))
    row = result.rows[0]
    assert row.canonical_volume == "123"
    assert row.original_fields[-1] == lexeme
    assert row.disposition == "post_inception_integral_volume_normalized"
    assert result.candidate_bytes == line(volume="123")


@pytest.mark.parametrize("lexeme,reason", [
    ("123.000000000000001", "volume_fractional"), ("1e-3", "volume_fractional"),
    ("0", "volume_not_positive"), ("0.0", "volume_not_positive"),
    ("-1", "volume_negative"), ("-0", "volume_negative"),
    ("", "volume_missing"), ("NaN", "volume_lexeme"), ("Infinity", "volume_lexeme"),
    (" 123", "volume_lexeme"), ("1_23", "volume_lexeme"),
    ("1e9999", "volume_lexeme"), ("1e999", "volume_bound"),
    ("9999999999999999999", "volume_bound"),
])
def test_fractional_and_invalid_volume_never_round_fill_or_become_eligible(lexeme, reason):
    raw = line(volume=lexeme)
    result = repair(raw)
    row = result.rows[0]
    assert row.reasons == (reason,) and row.candidate_line is None
    assert result.candidate_bytes == b"" and result.source_raw == raw
    assert row.disposition == ("fractional_volume_quarantine" if reason == "volume_fractional" else "invalid_row_quarantine")
    assert manifest(result)["financial_acceptance"] is False


def test_only_volume_bytes_change_and_original_line_endings_are_preserved():
    raw = b'"2021-02-10","10.00",11,9,10,"123.000"\r\n'
    result = repair(raw)
    assert result.candidate_bytes == b'"2021-02-10","10.00",11,9,10,123\r\n'
    assert result.rows[0].raw_line == raw


def test_header_and_bom_are_kept_in_source_ledger_without_inventing_rows():
    raw = b"\xef\xbb\xbfDate,Open,High,Low,Close,Volume\r\n" + line(volume="123.0", ending="\r\n")
    result = repair(raw)
    assert result.rows[0].disposition == "source_header"
    assert result.candidate_bytes == line(volume="123", ending="\r\n")
    assert manifest(result)["source_rows"] == 1
    assert b"".join(row.raw_line for row in result.rows) == raw


def test_all_duplicate_dates_are_quarantined_without_choosing_a_row():
    raw = line("2021-02-10", "123") + line("2021-02-10", "456") + line("2021-02-11", "789")
    result = repair(raw)
    assert all("duplicate_date" in row.reasons for row in result.rows[:2])
    assert all(row.candidate_line is None for row in result.rows[:2])
    assert result.candidate_bytes == line("2021-02-11", "789")
    assert manifest(result)["missing_post_inception_source_dates"] == ["2021-02-10"]


def test_out_of_order_source_is_retained_without_sorting_a_candidate():
    raw = line("2021-02-12") + line("2021-02-10")
    result = repair(raw)
    assert result.candidate_bytes == b""
    assert all("source_out_of_order" in row.reasons for row in result.rows)
    assert b"".join(row.raw_line for row in result.rows) == raw


@pytest.mark.parametrize("raw,reason", [
    (b"2021-02-10,10,11,9,10\n", "field_count"),
    (line("2021-02-30"), "date"), (line(prices="10,9,8,10"), "ohlc_geometry"),
    (line(prices="0,11,9,10"), "price"), (b"\xff\n", "encoding"),
    (b"2021-02-10,10,11,9,10,123\0\n", "row_framing"),
    (b"x" * 513 + b"\n", "line_bound"),
])
def test_malformed_rows_are_retained_with_explicit_refusal_reasons(raw, reason):
    result = repair(raw)
    assert reason in result.rows[0].reasons
    assert result.rows[0].disposition == "invalid_row_quarantine"
    assert result.source_raw == result.rows[0].raw_line == raw
    assert not result.candidate_bytes


def test_identity_boundary_is_fixed_and_does_not_guess_predecessor_issuer():
    raw = line("2010-10-26") + line("2010-10-27")
    result = repair(raw)
    assert result.rows[0].disposition == "pre_inception_identity_quarantine"
    assert result.candidate_bytes == line("2010-10-27")
    summary = manifest(result)
    assert summary["identity_boundary"] == "2010-10-27"
    assert summary["permanent_sid_bound"] is False
    with pytest.raises(TypeError):
        m.repair_remx_daily(raw, expected_sha256=hashlib.sha256(raw).hexdigest(), identity_boundary="2000-01-01")


def test_candidate_passes_old_strict_parser_but_all_admissions_stay_false():
    result = repair(line(volume="123.0") + line("2021-02-11", "456"))
    parsed = strict.parse_ohlcv(result.candidate_bytes, expected_sha256=hashlib.sha256(result.candidate_bytes).hexdigest(),
        symbol="REMX", timeframe="daily", member_name=m.SOURCE_MEMBER, instrument_kind="etf")
    assert len(parsed.bars) == 2
    summary = manifest(result)
    for key in ("source_origin_authenticated", "permanent_sid_bound", "point_in_time_data",
                "source_rights_verified", "native_qc_mark", "source_inputs_admitted",
                "full_coverage_verified", "backtesting_ready", "financial_acceptance",
                "canonical_admission", "trading_authority", "fractional_volumes_rounded_or_truncated", "gap_fill_performed"):
        assert summary[key] is False
    assert summary["candidate_strict_parser_valid"] is True


def test_source_and_result_integrity_tampering_refuses_without_echo():
    raw = line()
    with pytest.raises(m.RepairRefusal) as error:
        m.repair_remx_daily(raw, expected_sha256="0" * 64)
    assert str(error.value) == "bounded REMX repair candidate refused"
    result = repair(raw)
    with pytest.raises(FrozenInstanceError):
        result.source_raw = b"changed"
    with pytest.raises(m.RepairRefusal):
        m.export_blobs(replace(result, candidate_bytes=b"changed"))
    with pytest.raises(m.RepairRefusal):
        m.export_blobs(replace(result, rows=(replace(result.rows[0], raw_line_sha256="0" * 64),)))
    forged_line = line(volume="999")
    forged_row = replace(result.rows[0], canonical_volume="999", candidate_line=forged_line)
    with pytest.raises(m.RepairRefusal):
        m.export_blobs(replace(result, candidate_bytes=forged_line, rows=(forged_row,)))
    with pytest.raises(m.RepairRefusal):
        m.export_blobs(replace(result, source_raw="not bytes"))


def test_dispositions_partition_every_source_row_and_blobs_reconstruct_the_count():
    """TPR-CR34: candidate + every quarantine + invalid rows must equal the source rows."""
    raw = (line("2005-01-04", "123") + line("2021-02-10", "123.0") + line("2021-02-11", "123.25")
        + line("2021-02-12", "456") + line("2021-02-12", "456") + line("2021-02-15", "-1")
        + line("2021-02-16", "1,234") + line("2021-02-17", "789"))
    result = repair(raw)
    blobs, summary = m.export_blobs(result), manifest(result)
    assert summary["source_rows"] == 8
    assert sum(summary["disposition_counts"].values()) == summary["source_rows"]
    assert summary["candidate_rows"] == result.candidate_bytes.count(b"\n") == 2  # duplicate dates are quarantined
    quarantined = sum(blobs[name].count(b"\n") for name in blobs
        if name.startswith("quarantine_") and name.endswith(".csv"))
    assert summary["candidate_rows"] + quarantined == summary["source_rows"]
    assert len([row for row in blobs["row_ledger.jsonl"].splitlines() if row]) == summary["source_rows"]


def test_counterpart_rounding_or_admission_caller_flags_do_not_exist():
    raw = line(volume="123.25")
    for override in ({"counterpart_volume": 123}, {"allow_fractional": True},
                     {"financial_acceptance": True}, {"identity_boundary": "2000-01-01"}):
        with pytest.raises(TypeError):
            m.repair_remx_daily(raw, expected_sha256=hashlib.sha256(raw).hexdigest(), **override)


def test_global_input_and_record_caps_refuse_before_unsafe_partial_success(monkeypatch):
    with pytest.raises(m.RepairRefusal):
        repair(b"x" * (m.MAX_SOURCE_BYTES + 1))
    monkeypatch.setattr(m, "MAX_ROWS", 1)
    with pytest.raises(m.RepairRefusal):
        repair(line() + line("2021-02-11"))

def test_forged_nonbyte_candidate_line_refuses_with_fixed_body():
    result = repair(line())
    forged = replace(result, rows=(replace(result.rows[0], candidate_line=123),))
    with pytest.raises(m.RepairRefusal) as error:
        m.export_blobs(forged)
    assert error.value.reason == "result_integrity"
    assert str(error.value) == "bounded REMX repair candidate refused"
