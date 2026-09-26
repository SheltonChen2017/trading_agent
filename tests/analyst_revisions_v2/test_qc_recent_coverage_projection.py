"""Executable count-only recent source, partial joins and transport boundary."""

from datetime import datetime
from decimal import Decimal
import hashlib
import json
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_six_universe_recent_coverage_projection as subject
from tests.analyst_revisions_v2 import test_qc_recent_input_direct_read as input_tests
from tests.analyst_revisions_v2 import test_qc_six_universe_tilt_recent_projection as cloud_tests

prior_package = cloud_tests.prior_package
actual_package = input_tests.actual_package


@pytest.fixture(scope="module")
def projection(prior_package, actual_package):
    return subject.build_recent_coverage_projection(prior_package, actual_package)


@pytest.fixture
def runtime(projection, monkeypatch):
    sources = {item.project_path: item.source_bytes.decode("ascii")
               for item in projection.source_files}
    modules = cloud_tests._cloud_modules(sources, monkeypatch)
    return modules["accepted_risk_six_universe_coverage_qc_runtime"]


def _driver(runtime):
    driver = object.__new__(runtime.SixUniverseCoverageQcDriver)
    driver._initialized = True
    driver._completed = False
    driver._security_by_sid = {f"SID-{i}": f"FIGI-{i}" for i in range(20)}
    driver._label_by_sid = {f"SID-{i}": f"T{i}" for i in range(20)}
    return driver


def _measurement(runtime, *, unmapped=0, caps=20, weight=Decimal("0.05")):
    driver = _driver(runtime)
    for index in range(20 - unmapped, 20):
        del driver._security_by_sid[f"SID-{index}"]
    return driver._measure("QQQ", "fresh",
        tuple((f"SID-{i}", weight) for i in range(20)), "fresh",
        {f"SID-{i}": Decimal("100") for i in range(caps)})


def test_public_projection_is_exact_counts_only_recent_closure(projection):
    files = {item.project_path: item for item in projection.source_files}
    assert len(files) == 9
    assert projection.package_sha256 == subject._recent.PINNED_PACKAGE_SHA256
    assert projection.profile_sha256 == subject.require_recent_coverage_profile()["profile_sha256"]
    source = files["accepted_risk_order_level_input_runtime.py"]
    assert source.content_sha256 == subject._recent.CORRECTED_INPUT_SHA256
    assert "store.contains_key(key)" not in source.source_bytes.decode("ascii")
    main = files["main.py"].source_bytes.decode("ascii")
    assert "set_start_date(2025, 7, 24)" in main
    assert "set_end_date(2026, 9, 25)" in main
    for item in files.values():
        subject._old._audit_source(item.project_path, item.source_bytes)
        assert hashlib.sha256(item.source_bytes).hexdigest() == item.content_sha256
    assert projection.to_record()["orders"] is False
    assert projection.to_record()["price_access"] is False


def test_cloud_profile_matches_host_period_and_grid(runtime):
    assert runtime.require_six_universe_coverage_profile() == subject.require_recent_coverage_profile()
    assert runtime.EXPECTED_DECISION_COUNT == 61
    assert runtime.YEARS == (2025, 2026)
    assert runtime.EVALUATION_START_SESSION == "2025-08-01"
    assert runtime.EVALUATION_END_SESSION == "2026-09-25"


def test_unknown_catalog_sids_keep_denominator_even_with_qc_caps(runtime):
    measurement = _measurement(runtime, unmapped=3)
    assert measurement["coverage"].member_count == 20
    assert measurement["coverage"].mapping_ratio == Decimal("0.85")
    assert measurement["coverage"].cap_weight_coverage_ratio == Decimal("0.85")
    assert measurement["unmapped_positive_cap_member_count_sum"] == 3
    assert measurement["eligible_member_count"] == 17
    counts = runtime._empty_counts()
    runtime._record_counts(counts, measurement)
    assert counts["unmapped_positive_cap_member_count_sum"] == 3
    assert counts["eligible_member_count_ge5_count"] == 1
    assert counts["eligible_member_count_ge10_count"] == 1
    assert counts["candidate_joint_counts"][-1] == 0
    assert counts["candidate_joint_counts"][0] == 1


def test_unknown_sid_cap_absence_is_not_misclassified(runtime):
    measurement = _measurement(runtime, unmapped=3, caps=17)
    assert measurement["unmapped_figi_member_count_sum"] == 3
    assert measurement["unmapped_positive_cap_member_count_sum"] == 0
    assert measurement["eligible_member_count"] == 17


@pytest.mark.parametrize("eligible,expected", ((4, 0), (5, 1)))
def test_joint_grid_requires_five_usable_members_not_only_weight(runtime, eligible, expected):
    driver = _driver(runtime)
    rows = tuple((f"SID-{i}", Decimal("0.2") if i < 4 else Decimal("0.0125"))
                 for i in range(20))
    measurement = driver._measure("SOXX", "fresh", rows, "fresh",
        {f"SID-{i}": Decimal("100") for i in range(eligible)})
    assert measurement["coverage"].cap_weight_coverage_ratio >= Decimal("0.8")
    counts = runtime._empty_counts()
    runtime._record_counts(counts, measurement)
    assert counts["candidate_joint_counts"][0] == expected


@pytest.mark.parametrize("weight,expected", (("0.0475", 1), ("0.047499", 0), ("0.0525", 1), ("0.052501", 0)))
def test_grid_total_weight_boundary_is_inclusive(runtime, weight, expected):
    counts = runtime._empty_counts()
    runtime._record_counts(counts, _measurement(runtime, weight=Decimal(weight)))
    assert counts["candidate_joint_counts"][-1] == expected


def test_extrema_are_cumulative_and_year_records_omit_grid(runtime):
    counts = runtime._empty_counts()
    runtime._record_counts(counts, _measurement(runtime))
    runtime._record_counts(counts, _measurement(runtime, unmapped=3, caps=18, weight=Decimal("0.04")))
    assert counts["ratio_extrema"] == [Decimal("0.85"), Decimal(1), Decimal("0.85"), Decimal(1), Decimal("0.8"), Decimal(1)]
    assert "candidate_joint_counts" not in runtime._counts_record(counts, grid=False)
    assert runtime._counts_record(counts)["ratio_extrema"] == ["0.85", "1", "0.85", "1", "0.8", "1"]


def test_missing_collection_has_no_fabricated_ratios_or_grid_pass(runtime):
    driver = _driver(runtime)
    measurement = driver._measure("REMX", "missing", (), "fresh", {})
    counts = runtime._empty_counts()
    runtime._record_counts(counts, measurement)
    assert counts["ratio_extrema"] == [None] * 6
    assert sum(counts["candidate_joint_counts"]) == 0
    assert counts["constituent_missing_count"] == 1


def _complete_driver(runtime, measurement=None):
    driver = _driver(runtime)
    driver._next_decision_index = 61
    driver._source_row_count = 10000
    driver._path_hash = hashlib.sha256(b"synthetic-count-path")
    driver._package = SimpleNamespace(package_id="fixture", package_sha256="a" * 64,
        activation_manifest_sha256="b" * 64)
    driver._resolution = SimpleNamespace(resolution_id="fixture", resolution_sha256="c" * 64,
        input_row_count=6151, resolved_count=5113, named_refusal_count=1038,
        named_refusals=({"reason": "qc_runtime_composite_figi_resolution_unavailable"},) * 1038)
    measurement = _measurement(runtime, unmapped=3) if measurement is None else measurement
    driver._records = {}
    for ticker in runtime._gate.UNIVERSE_IDS:
        counts = {"total": runtime._empty_counts(), 2025: runtime._empty_counts(), 2026: runtime._empty_counts()}
        for index in range(61):
            runtime._record_counts(counts["total"], measurement)
            runtime._record_counts(counts[2025 if index < 22 else 2026], measurement)
        driver._records[ticker] = counts
    emitted = {}
    driver._algorithm = SimpleNamespace(time=datetime(2026, 9, 26),
        set_summary_statistic=lambda key, value: emitted.setdefault(key, value))
    return driver, emitted


def test_terminal_census_and_all_seven_payloads_fit_transport(runtime):
    driver, emitted = _complete_driver(runtime)
    statistics = driver.on_end_of_algorithm()
    assert driver._completed is True
    assert statistics == emitted
    assert len(emitted) == 7
    assert all(len(value.encode("ascii")) <= 8192 for value in emitted.values())
    meta = json.loads(emitted[runtime.META_STATISTIC_NAME])
    assert meta["resolver_counts"] == {"input": 6151, "resolved": 5113, "refused": 1038}
    assert meta["resolver_refusal_reasons"]["qc_runtime_composite_figi_resolution_unavailable"] == 1038
    assert meta["decision_count"] == 61
    assert meta["price_or_return_access"] is False


def test_repeating_exact_ratios_still_fit_transport(runtime):
    driver = _driver(runtime)
    measurement = driver._measure("REMX", "fresh",
        tuple((f"SID-{i}", Decimal("0.04")) for i in range(21)), "fresh",
        {f"SID-{i}": Decimal("100") for i in range(18)})
    assert len(measurement["coverage"].mapping_ratio.as_tuple().digits) == 96
    completed, _ = _complete_driver(runtime, measurement)
    statistics = completed._statistics()
    assert max(len(value.encode("ascii")) for value in statistics.values()) <= 8192


@pytest.mark.parametrize("clock", (datetime(2026, 9, 25), datetime(2026, 9, 27), datetime(2026, 9, 26, 0, 1)))
def test_wrong_terminal_clock_refuses_without_emission(runtime, clock):
    driver, emitted = _complete_driver(runtime)
    driver._algorithm.time = clock
    with pytest.raises(runtime.SixUniverseCoverageQcRuntimeError, match="ended outside"):
        driver.on_end_of_algorithm()
    assert not emitted


def test_missing_cloud_dependency_cannot_fall_back_to_host(projection, monkeypatch):
    sources = {item.project_path: item.source_bytes.decode("ascii") for item in projection.source_files}
    sources.pop("accepted_risk_order_level_input_runtime.py")
    monkeypatch.delitem(__import__("sys").modules, "accepted_risk_order_level_input_runtime", raising=False)
    with pytest.raises(AssertionError, match="fell back to host"):
        cloud_tests._cloud_modules(sources, monkeypatch)
