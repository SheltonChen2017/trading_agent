"""Counts-only six-universe QC coverage diagnostic boundaries."""

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_coverage_qc_runtime as subject,
)


class Symbol:
    def __init__(self, sid):
        self.id = sid


def _bare_driver():
    driver = object.__new__(subject.SixUniverseCoverageQcDriver)
    driver._initialized = True
    driver._completed = False
    driver._algorithm = SimpleNamespace(time=datetime(2021, 1, 5, 16))
    driver._session_positions = {
        "2021-01-04": 0,
        "2021-01-05": 1,
        "2021-01-06": 2,
        "2021-01-07": 3,
    }
    driver._security_by_sid = {f"SID-{index}": f"FIGI-{index}" for index in range(20)}
    driver._label_by_sid = {f"SID-{index}": f"T{index}" for index in range(20)}
    driver._source_row_count = 0
    return driver


def _rows(weight=Decimal("0.05")):
    return tuple((f"SID-{index}", weight) for index in range(20))


def _measurement(driver, *, caps=19, weight=Decimal("0.05")):
    return driver._measure(
        "SPY", "fresh", _rows(weight), "fresh",
        {f"SID-{index}": Decimal("100") for index in range(caps)},
    )


def test_profile_and_statistic_inventory_bind_six_sleeves_without_outcomes():
    profile = subject.require_six_universe_coverage_profile()
    declared = profile.pop("profile_sha256")
    assert hashlib.sha256(subject._canonical(profile)).hexdigest() == declared
    assert profile["decision_count"] == 261
    assert profile["orders"] is False
    assert profile["price_access"] is False
    assert subject.expected_custom_summary_statistic_names() == tuple(sorted((
        "ARV2_SIX_COVERAGE_META",
        "ARV2_SIX_COVERAGE_SPY",
        "ARV2_SIX_COVERAGE_QQQ",
        "ARV2_SIX_COVERAGE_SOXX",
        "ARV2_SIX_COVERAGE_XLV",
        "ARV2_SIX_COVERAGE_REMX",
        "ARV2_SIX_COVERAGE_XLE",
    )))


def test_callback_freezes_original_timestamp_and_rows_without_replay():
    driver = _bare_driver()
    cache = {}
    row = SimpleNamespace(symbol=Symbol("SID-0"), weight=Decimal("0.05"))
    driver._algorithm.time = datetime(2021, 1, 4, 8, 15)
    driver._cache_collection(
        cache, (row,), "constituents", driver._freeze_constituent_rows
    )
    row.weight = Decimal("0.99")
    assert cache["2021-01-04"] == (
        "2021-01-04T08:15:00.000000",
        (("SID-0", Decimal("0.05")),),
    )
    assert driver._select_prior(cache, "2021-01-05", 1) == (
        "fresh", (("SID-0", Decimal("0.05")),)
    )
    assert driver._select_prior(cache, "2021-01-06", 1) == ("stale", ())
    cache["2021-01-05"] = (
        "2021-01-05T07:00:00.000000", (("SID-0", Decimal("0.01")),)
    )
    assert driver._select_prior(cache, "2021-01-05", 1)[1] == (
        ("SID-0", Decimal("0.05")),
    )
    with pytest.raises(subject.SixUniverseCoverageQcRuntimeError, match="conflicts"):
        driver._cache_collection(
            cache,
            (SimpleNamespace(symbol=Symbol("SID-0"), weight=Decimal("0.99")),),
            "constituents",
            driver._freeze_constituent_rows,
        )


def test_exact_gate_histograms_and_joint_passes_include_cause_counts():
    driver = _bare_driver()
    counts = subject._empty_counts()
    measurement = _measurement(driver, caps=19)
    subject._record_counts(counts, measurement)
    assert measurement["coverage"].cap_weight_coverage_ratio == Decimal("0.95")
    assert counts["cap_ge_95_count"] == 1
    assert counts["cap_ge_99_count"] == 0
    assert counts["joint_pass_95_count"] == 1
    assert counts["joint_pass_99_count"] == 0
    assert counts["cap_ratio_bins"]["ge_95_lt_99"] == 1
    assert counts["mapped_pit_cap_missing_member_count_sum"] == 1
    assert counts["mapping_ratio_bins"]["ge_90"] == 1
    assert counts["reported_weight_bins"]["in_95_105"] == 1

    del driver._security_by_sid["SID-17"]
    del driver._security_by_sid["SID-18"]
    del driver._security_by_sid["SID-19"]
    subject._record_counts(counts, _measurement(driver, caps=17))
    assert counts["mapping_ratio_bins"]["ge_80_lt_90"] == 1
    assert counts["cap_ratio_bins"]["ge_80_lt_90"] == 1
    assert counts["unmapped_figi_member_count_sum"] == 3
    assert counts["joint_pass_95_count"] == 1

    subject._record_counts(counts, _measurement(_bare_driver(), caps=20, weight=Decimal("0.047")))
    assert counts["reported_weight_bins"]["lt_95"] == 1
    assert counts["joint_pass_99_count"] == 0


def test_missing_stale_empty_and_nonpositive_collections_are_counted():
    driver = _bare_driver()
    counts = subject._empty_counts()
    for constituent_status, rows, fundamental_status in (
        ("missing", (), "missing"),
        ("stale", (), "stale"),
        ("fresh", (), "fresh"),
        ("fresh", (("SID-0", Decimal(0)),), "fresh"),
    ):
        subject._record_counts(counts, driver._measure(
            "SPY", constituent_status, rows, fundamental_status, {}
        ))
    assert counts["decision_count"] == 4
    assert counts["measurable_count"] == 0
    assert counts["fundamental_missing_count"] == 1
    assert counts["fundamental_stale_count"] == 1
    assert counts["constituent_missing_count"] == 1
    assert counts["constituent_stale_count"] == 1
    assert counts["empty_collection_count"] == 1
    assert counts["no_positive_weight_count"] == 2


def test_six_bounded_statistics_expose_no_ids_rows_prices_or_returns():
    driver = _bare_driver()
    driver._next_decision_index = subject.EXPECTED_DECISION_COUNT
    driver._records = {
        ticker: {"total": subject._empty_counts(), **{
            year: subject._empty_counts() for year in subject.YEARS
        }} for ticker in subject._gate.UNIVERSE_IDS
    }
    driver._package = SimpleNamespace(
        package_id="package-id", package_sha256="a" * 64,
        activation_manifest_sha256="b" * 64,
    )
    driver._resolution = SimpleNamespace(
        resolution_id="resolution-id", resolution_sha256="c" * 64,
    )
    driver._path_hash = hashlib.sha256()
    measurement = _measurement(driver, caps=19)
    for ticker in subject._gate.UNIVERSE_IDS:
        for index in range(subject.EXPECTED_DECISION_COUNT):
            year = 2021 + min(index // 52, 4)
            subject._record_counts(driver._records[ticker]["total"], measurement)
            subject._record_counts(driver._records[ticker][year], measurement)
    statistics = driver._statistics()
    assert tuple(sorted(statistics)) == subject.expected_custom_summary_statistic_names()
    assert all(len(value.encode("ascii")) <= subject.MAXIMUM_STATISTIC_BYTES for value in statistics.values())
    assert "SID-0" not in str(statistics)
    assert "FIGI-0" not in str(statistics)
    assert "returns" not in str(statistics).lower()
    meta = json.loads(statistics[subject.META_STATISTIC_NAME])
    for ticker in subject._gate.UNIVERSE_IDS:
        value = json.loads(statistics[subject.SLEEVE_STATISTIC_PREFIX + ticker])
        assert meta["sleeve_sha256s"][ticker] == subject._sha(value)
        assert value["totals"]["joint_pass_95_count"] == 261
        assert value["totals"]["joint_pass_99_count"] == 0
