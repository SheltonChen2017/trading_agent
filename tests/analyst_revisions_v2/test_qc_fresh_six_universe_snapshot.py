"""Offline refusal and byte-identity checks; no QC or provider calls."""

import gzip
import hashlib
import json
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from research.analyst_revisions_v2_qc import fresh_six_universe_snapshot as snapshot


def _row(sid, ticker, *, cap=None, weight=None, end_time=None):
    return SimpleNamespace(
        symbol=SimpleNamespace(id=sid, value=ticker),
        market_cap=cap,
        weight=weight,
        end_time=end_time or datetime(2026, 9, 25, 7, 0),
    )


class _Store:
    def __init__(self):
        self.values = {}

    def contains_key(self, key):
        return key in self.values

    def save_bytes(self, key, value):
        self.values[key] = value
        return True

    def read_bytes(self, key):
        return self.values[key]


class _Algorithm:
    def __init__(self):
        self.time = datetime(2026, 9, 25, 8, 0)
        self.object_store = _Store()
        self.statistics = {}

    def set_summary_statistic(self, key, value):
        self.statistics[key] = value


class _QcDatetime(datetime):
    """A Python-bridge-compatible datetime subtype, not an exact datetime."""


def test_qc_datetime_subtypes_are_accepted_at_both_clock_boundaries():
    algo = _Algorithm()
    algo.time = _QcDatetime(2026, 9, 25, 8, 0)
    capture = snapshot.FreshSixUniverseSnapshot(algo, "2026-09-28")
    capture.accept("FUNDAMENTALS", [_row(
        "A-SID", "A", cap=100,
        end_time=_QcDatetime(2026, 9, 25, 7, 0),
    )])
    assert capture._collections["FUNDAMENTALS"]["qc_callback_time_ny"].startswith(
        "2026-09-25T08:00:00"
    )
    assert capture._collections["FUNDAMENTALS"]["qc_source_end_time_ny"].startswith(
        "2026-09-25T07:00:00"
    )


def test_non_datetime_qc_clock_and_end_time_still_refuse():
    algo = _Algorithm()
    capture = snapshot.FreshSixUniverseSnapshot(algo, "2026-09-28")
    algo.time = "2026-09-25T08:00:00"
    with pytest.raises(snapshot.FreshSixUniverseSnapshotError, match="callback clock is unavailable"):
        capture.accept("FUNDAMENTALS", [_row("A-SID", "A", cap=100)])
    algo.time = datetime(2026, 9, 25, 8, 0)
    with pytest.raises(snapshot.FreshSixUniverseSnapshotError, match="source end time is not a datetime"):
        capture.accept("FUNDAMENTALS", [_row(
            "A-SID", "A", cap=100, end_time="2026-09-25T07:00:00",
        )])


def _populated(*, qcom_cap=True, qcom_sid="QCOM-SID"):
    algo = _Algorithm()
    capture = snapshot.FreshSixUniverseSnapshot(algo, "2026-09-28")
    fundamentals = [_row("A-SID", "A", cap="100.50")]
    if qcom_cap:
        fundamentals.append(_row(qcom_sid, "QCOM", cap="200"))
    capture.accept("FUNDAMENTALS", fundamentals)
    for ticker in snapshot.ETFS:
        rows = [_row("A-SID", "A", weight="0.7")]
        if ticker in ("SPY", "QQQ", "SOXX"):
            rows.append(_row("QCOM-SID", "QCOM", weight="0.3"))
        capture.accept(ticker, rows)
    algo.time = datetime(2026, 9, 28, 9, 20)
    return algo, capture


def _capture_with_six_other_sources(omitted):
    algo = _Algorithm()
    capture = snapshot.FreshSixUniverseSnapshot(algo, "2026-09-28")
    if omitted != "FUNDAMENTALS":
        capture.accept("FUNDAMENTALS", [_row("A-SID", "A", cap="100")])
    for ticker in snapshot.ETFS:
        if ticker != omitted:
            capture.accept(ticker, [_row("A-SID", "A", weight="1")])
    return algo, capture


def test_seven_exact_prior_sources_persist_one_hash_verified_private_artifact():
    algo, capture = _populated()
    receipt = capture.persist_at_decision()
    compressed = algo.object_store.values[receipt["object_store_key"]]
    canonical = gzip.decompress(compressed)
    body = json.loads(canonical)
    assert set(body["sources"]) == set(snapshot.SOURCES)
    assert body["sources"]["FUNDAMENTALS"]["positive_market_caps"] == [
        ["A-SID", "100.50"], ["QCOM-SID", "200"]
    ]
    assert body["sources"]["QQQ"]["positive_constituents"] == [
        ["A-SID", "0.7"], ["QCOM-SID", "0.3"]
    ]
    assert body["qcom_exact_sid_status"] == "joined"
    assert body["decision_ready"] is False
    assert body["naive_qc_times_interpreted_as"] == "America/New_York"
    assert body["sources"]["QQQ"]["qc_source_end_time_ny"].startswith("2026-09-25")
    assert body["qc_callback_is_vendor_availability_time"] is False
    assert body["point_in_time_vendor_availability_proven"] is False
    assert body["order_and_outcome_access"] is False
    assert receipt["canonical_sha256"] == hashlib.sha256(canonical).hexdigest()
    assert receipt["compressed_sha256"] == hashlib.sha256(compressed).hexdigest()
    assert json.loads(algo.statistics["ARV2_FRESH_SIX_INPUT_META"]) == receipt
    with pytest.raises(snapshot.FreshSixUniverseSnapshotError, match="already persisted"):
        capture.persist_at_decision()


def test_absent_or_stale_source_is_refused():
    algo, capture = _populated()
    with pytest.raises(snapshot.FreshSixUniverseSnapshotError, match="never persisted"):
        capture.require_persisted()
    del capture._collections["REMX"]
    with pytest.raises(snapshot.FreshSixUniverseSnapshotError, match="source is absent"):
        capture.persist_at_decision()
    assert not algo.object_store.values

    algo, capture = _populated()
    capture._collections["SOXX"]["qc_source_end_time_ny"] = "2026-09-01T07:00:00-04:00"
    with pytest.raises(snapshot.FreshSixUniverseSnapshotError, match="outside diagnostic bound"):
        capture.persist_at_decision()
    assert not algo.object_store.values


def test_at_or_after_cutoff_callback_is_not_accepted():
    algo = _Algorithm()
    algo.time = datetime(2026, 9, 28, 9, 21)
    capture = snapshot.FreshSixUniverseSnapshot(algo, "2026-09-28")
    assert capture.accept("FUNDAMENTALS", [_row("A", "A", cap=10)]) == []
    assert not capture._collections


def test_same_day_pre_cutoff_callback_can_supersede_older_delivery():
    algo = _Algorithm()
    capture = snapshot.FreshSixUniverseSnapshot(algo, "2026-09-28")
    capture.accept("FUNDAMENTALS", [
        _row("A", "A", cap=10, end_time=datetime(2026, 9, 24, 7)),
    ])
    algo.time = datetime(2026, 9, 28, 8)
    capture.accept("FUNDAMENTALS", [
        _row("A", "A", cap=20, end_time=datetime(2026, 9, 25, 7)),
    ])
    assert capture._collections["FUNDAMENTALS"]["positive_market_caps"] == [["A", "20"]]
    assert capture._collections["FUNDAMENTALS"]["qc_callback_time_ny"].startswith("2026-09-28")


def test_empty_warmup_then_valid_same_clock_is_a_counted_recovery():
    algo, capture = _capture_with_six_other_sources("QQQ")
    capture.accept("QQQ", [])
    assert capture._collections["QQQ"]["degenerate_reason"] == "empty_collection"
    capture.accept("QQQ", [_row("A-SID", "A", weight="1")])
    algo.time = datetime(2026, 9, 28, 9, 20)
    receipt = capture.persist_at_decision()
    body = json.loads(gzip.decompress(algo.object_store.values[receipt["object_store_key"]]))
    assert body["sources"]["QQQ"]["collection_status"] == "valid"
    assert body["superseded_degenerate_callback_count_by_source"]["QQQ"] == 1
    assert body["superseded_degenerate_callback_count"] == 1
    assert body["decision_ready"] is False


def test_all_nonpositive_warmup_then_valid_same_end_time_is_a_counted_recovery():
    algo, capture = _capture_with_six_other_sources("FUNDAMENTALS")
    capture.accept("FUNDAMENTALS", [_row("A-SID", "A", cap=0)])
    assert capture._collections["FUNDAMENTALS"]["degenerate_reason"] == "no_positive_market_caps"
    algo.time = datetime(2026, 9, 28, 8)
    capture.accept("FUNDAMENTALS", [_row("A-SID", "A", cap=100)])
    algo.time = datetime(2026, 9, 28, 9, 20)
    receipt = capture.persist_at_decision()
    body = json.loads(gzip.decompress(algo.object_store.values[receipt["object_store_key"]]))
    assert body["sources"]["FUNDAMENTALS"]["positive_market_caps"] == [["A-SID", "100"]]
    assert body["superseded_degenerate_callback_count_by_source"]["FUNDAMENTALS"] == 1


@pytest.mark.parametrize(
    "late_rows,reason",
    [([], "empty_collection"), ([_row("A-SID", "A", weight=0)], "no_positive_constituent_weights")],
)
def test_later_degenerate_callback_invalidates_earlier_valid_before_any_write(late_rows, reason):
    algo, capture = _populated()
    algo.time = datetime(2026, 9, 28, 8)
    capture.accept("QQQ", late_rows)
    assert capture._collections["QQQ"]["degenerate_reason"] == reason
    algo.time = datetime(2026, 9, 28, 9, 20)
    with pytest.raises(snapshot.FreshSixUniverseSnapshotError, match="latest pre-cutoff collection is degenerate"):
        capture.persist_at_decision()
    assert not algo.object_store.values
    assert not algo.statistics


def test_valid_change_cannot_launder_through_an_empty_callback_at_same_end_time():
    algo = _Algorithm()
    capture = snapshot.FreshSixUniverseSnapshot(algo, "2026-09-28")
    capture.accept("FUNDAMENTALS", [_row("A", "A", cap=10)])
    capture.accept("FUNDAMENTALS", [])
    algo.time = datetime(2026, 9, 28, 8)
    with pytest.raises(snapshot.FreshSixUniverseSnapshotError, match="same-EndTime valid collection changed"):
        capture.accept("FUNDAMENTALS", [_row("A", "A", cap=20)])


def test_two_changed_valid_collections_at_one_callback_second_refuse():
    algo = _Algorithm()
    capture = snapshot.FreshSixUniverseSnapshot(algo, "2026-09-28")
    capture.accept("QQQ", [_row(
        "A", "A", weight=1, end_time=datetime(2026, 9, 24, 7),
    )])
    with pytest.raises(snapshot.FreshSixUniverseSnapshotError, match="same-clock valid collection changed"):
        capture.accept("QQQ", [_row(
            "A", "A", weight=1, end_time=datetime(2026, 9, 25, 7),
        )])


def test_mixed_or_future_source_end_time_refuses_immediately():
    algo = _Algorithm()
    capture = snapshot.FreshSixUniverseSnapshot(algo, "2026-09-28")
    with pytest.raises(snapshot.FreshSixUniverseSnapshotError, match="mixes source end times"):
        capture.accept("QQQ", [
            _row("A", "A", weight=1, end_time=datetime(2026, 9, 25, 7)),
            _row("B", "B", weight=1, end_time=datetime(2026, 9, 24, 7)),
        ])
    algo.time = datetime(2026, 9, 28, 8)
    with pytest.raises(snapshot.FreshSixUniverseSnapshotError, match="source end time follows QC callback"):
        capture.accept("QQQ", [_row(
            "A", "A", weight=1, end_time=datetime(2026, 9, 28, 8, 1),
        )])


def test_source_end_time_regression_or_same_version_edit_refuses():
    algo = _Algorithm()
    capture = snapshot.FreshSixUniverseSnapshot(algo, "2026-09-28")
    capture.accept("FUNDAMENTALS", [_row("A", "A", cap=10)])
    algo.time = datetime(2026, 9, 28, 8)
    with pytest.raises(snapshot.FreshSixUniverseSnapshotError, match="same-EndTime"):
        capture.accept("FUNDAMENTALS", [_row("A", "A", cap=20)])
    with pytest.raises(snapshot.FreshSixUniverseSnapshotError, match="regressed"):
        capture.accept("FUNDAMENTALS", [
            _row("A", "A", cap=10, end_time=datetime(2026, 9, 24, 7)),
        ])


def test_next_midnight_qc_end_time_is_a_diagnostic_not_a_prior_session_claim():
    algo, capture = _populated()
    algo.time = datetime(2026, 9, 28, 8)
    capture.accept("SPY", [
        _row("A-SID", "A", weight="0.7", end_time=datetime(2026, 9, 28)),
        _row("QCOM-SID", "QCOM", weight="0.3", end_time=datetime(2026, 9, 28)),
    ])
    algo.time = datetime(2026, 9, 28, 9, 20)
    receipt = capture.persist_at_decision()
    body = json.loads(gzip.decompress(algo.object_store.values[receipt["object_store_key"]]))
    assert body["sources"]["SPY"]["diagnostic_raw_end_time_calendar_lag_days"] == 0
    assert body["decision_ready"] is False


@pytest.mark.parametrize(
    "source,rows,reason",
    [
        ("FUNDAMENTALS", [_row("A", "A", cap="NaN")], "not finite"),
        ("FUNDAMENTALS", [_row("A", "A", cap=1), _row("A", "A", cap=2)], "duplicated"),
        ("SPY", [_row("A", "A", weight="Infinity")], "not finite"),
        ("QQQ", [_row(None, "A", weight=1)], "no QC SID"),
    ],
)
def test_invalid_numeric_and_identity_rows_refuse(source, rows, reason):
    algo = _Algorithm()
    capture = snapshot.FreshSixUniverseSnapshot(algo, "2026-09-28")
    with pytest.raises(snapshot.FreshSixUniverseSnapshotError, match=reason):
        capture.accept(source, rows)


def test_qcom_unresolved_sid_is_disclosed_not_guessed_or_removed():
    algo, capture = _populated(qcom_cap=False)
    receipt = capture.persist_at_decision()
    body = json.loads(gzip.decompress(algo.object_store.values[receipt["object_store_key"]]))
    assert body["qcom_exact_sid_status"] == "unmatched_positive_cap"
    assert ["QCOM-SID", "0.3"] in body["sources"]["QQQ"]["positive_constituents"]
    algo, capture = _populated(qcom_sid="CHANGED-QCOM-SID")
    receipt = capture.persist_at_decision()
    body = json.loads(gzip.decompress(algo.object_store.values[receipt["object_store_key"]]))
    assert body["qcom_exact_sid_status"] == "unmatched_positive_cap"


def test_invalid_fundamental_cap_is_counted_but_not_invented_as_zero():
    algo = _Algorithm()
    capture = snapshot.FreshSixUniverseSnapshot(algo, "2026-09-28")
    capture.accept("FUNDAMENTALS", [
        _row("A-SID", "A", cap="100.50"),
        _row("QCOM-SID", "QCOM", cap="200"),
        _row("BROKEN-SID", "BROKEN", cap="not-a-number"),
    ])
    for ticker in snapshot.ETFS:
        capture.accept(ticker, [_row("A-SID", "A", weight="1")])
    algo.time = datetime(2026, 9, 28, 9, 20)
    receipt = capture.persist_at_decision()
    body = json.loads(gzip.decompress(algo.object_store.values[receipt["object_store_key"]]))
    assert body["sources"]["FUNDAMENTALS"]["invalid_market_cap_count"] == 1
    assert ["BROKEN-SID", "0"] not in body["sources"]["FUNDAMENTALS"]["positive_market_caps"]


def test_source_end_time_is_required_and_cannot_be_replaced_by_callback_time():
    algo = _Algorithm()
    capture = snapshot.FreshSixUniverseSnapshot(algo, "2026-09-28")
    row = _row("A", "A", cap=10)
    row.end_time = None
    with pytest.raises(snapshot.FreshSixUniverseSnapshotError, match="source end time"):
        capture.accept("FUNDAMENTALS", [row])
    assert not capture._collections


def test_source_and_callback_order_uses_utc_instants_across_dst_fold():
    zone = ZoneInfo("America/New_York")
    algo = _Algorithm()
    algo.time = datetime(2026, 11, 1, 1, 15, tzinfo=zone, fold=1)
    capture = snapshot.FreshSixUniverseSnapshot(algo, "2026-11-02")
    capture.accept("FUNDAMENTALS", [_row(
        "A", "A", cap=10,
        end_time=datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0),
    )])
    assert "FUNDAMENTALS" in capture._collections
    with pytest.raises(snapshot.FreshSixUniverseSnapshotError, match="follows QC callback"):
        capture.accept("SPY", [_row(
            "A", "A", weight=1,
            end_time=datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=1),
        )])


def test_existing_content_addressed_key_cannot_hide_different_bytes():
    algo, capture = _populated()
    receipt = capture.persist_at_decision()
    algo2, capture2 = _populated()
    algo2.object_store.values[receipt["object_store_key"]] = b"corrupt"
    with pytest.raises(snapshot.FreshSixUniverseSnapshotError, match="key conflicts"):
        capture2.persist_at_decision()


def test_new_object_store_write_requires_exact_read_back():
    algo, capture = _populated()
    algo.object_store.read_bytes = lambda _key: b"corrupt"
    with pytest.raises(snapshot.FreshSixUniverseSnapshotError, match="read-back changed"):
        capture.persist_at_decision()


def test_generated_qc_entry_is_one_non_order_snapshot_project():
    source = snapshot.main_source("2026-09-28")
    compile(source, "main.py", "exec")
    assert "FreshSixUniverseSnapshot" in source
    assert "self.universe.etf" in source
    assert "Symbol.create(ticker, SecurityType.EQUITY, Market.USA)" in source
    assert "self.date_rules.every_day()" in source
    assert "self.time_rules.at(9, 20)" in source
    assert "def on_end_of_algorithm(self):\n        self._snapshot.require_persisted()" in source
    for forbidden in (
        "add_equity", "add_security", "add_data", "self.history",
        "market_order", "set_holdings", "portfolio", "broker",
    ):
        assert forbidden not in source.lower()
