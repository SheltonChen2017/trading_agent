"""R267's additive eight-ETF input probe stays count-only and source-pinned."""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_delta_order_package as delta,
    accepted_risk_eight_universe_input_qc_projection as projection,
    accepted_risk_eight_universe_input_qc_runtime as runtime,
)


PACKAGE_PATH = Path(
    "artifacts/analyst_revisions_v2/"
    "accepted_risk_delta_order_package_20260918_01/"
    "arv2-preliminary-qc-package-7803b84f0841f9685a4951de"
)
MANIFEST_PATH = Path(
    "research/analyst_revisions_v2_qc/eight_universe_input_r267_candidate.json"
)


def test_profile_is_additive_and_no_outcome_capability():
    profile = runtime.require_eight_universe_input_profile()
    digest = profile.pop("profile_sha256")
    assert digest == hashlib.sha256(runtime._six._canonical(profile)).hexdigest()
    assert profile["universe_ids"] == [
        "SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE", "XLI", "XLF",
    ]
    assert profile["new_universe_ids"] == ["XLI", "XLF"]
    assert profile["decision_count"] == 261
    assert profile["same_session_callback_eligible"] is False
    assert profile["orders"] is False
    assert profile["price_access"] is False
    assert profile["outcome_access"] is False


def test_overlap_counts_unique_ids_not_eight_sleeves_of_repeated_stock():
    tickers = runtime.UNIVERSE_IDS
    positive = {ticker: set() for ticker in tickers}
    mapped = {ticker: set() for ticker in tickers}
    eligible = {ticker: set() for ticker in tickers}
    positive["SPY"] = {"SID-A", "SID-B"}
    positive["QQQ"] = {"SID-A"}
    positive["XLI"] = {"SID-A", "SID-C"}
    positive["XLF"] = {"SID-D", "SID-E"}
    for ticker in tickers:
        mapped[ticker] = {sid.replace("SID", "SEC") for sid in positive[ticker]}
        eligible[ticker] = set(mapped[ticker])
    eligible["XLF"].add("SEC-A")
    counts = runtime._empty_overlap()
    runtime._add_overlap(counts, positive, mapped, eligible)
    assert counts["positive_memberships_sum"] == 7
    assert counts["unique_positive_sid_sum"] == 5
    assert counts["duplicate_positive_sid_memberships_sum"] == 2
    assert counts["cap_eligible_memberships_sum"] == 8
    assert counts["unique_cap_eligible_security_sum"] == 5
    assert counts["duplicate_cap_eligible_memberships_sum"] == 3
    assert counts["new_sleeve_overlap_with_prior_six"] == {"XLI": 1, "XLF": 1}
    assert counts["xli_xlf_overlap_sum"] == 1


def test_overlap_refuses_missing_sleeve_and_same_day_data_is_not_selected():
    groups = {ticker: set() for ticker in runtime.UNIVERSE_IDS}
    with pytest.raises(runtime.EightUniverseInputQcRuntimeError, match="inventory"):
        runtime._add_overlap(runtime._empty_overlap(), dict(list(groups.items())[:-1]), groups, groups)
    driver = object.__new__(runtime.EightUniverseInputQcDriver)
    driver._session_positions = {"2021-01-04": 0, "2021-01-05": 1}
    cache = {"2021-01-05": ("2021-01-05T08:00:00.000000", (("SID-A", 1),))}
    assert driver._select_prior(cache, "2021-01-05", 5) == ("missing", ())


def test_callback_age_bins_refuse_status_disagreement_and_never_count_same_day():
    positions = {f"2021-01-{day:02d}": day - 4 for day in range(4, 12)}
    cache = {"2021-01-04": ("2021-01-04T08:00:00.000000", ())}
    assert runtime._callback_age_bin(cache, "2021-01-05", positions, "fresh") == "age_1"
    assert runtime._callback_age_bin(cache, "2021-01-09", positions, "fresh") == "age_5"
    assert runtime._callback_age_bin(cache, "2021-01-10", positions, "stale") == "stale"
    assert runtime._callback_age_bin({}, "2021-01-05", positions, "missing") == "missing"
    with pytest.raises(runtime.EightUniverseInputQcRuntimeError, match="disagree"):
        runtime._callback_age_bin(cache, "2021-01-10", positions, "fresh")
    with pytest.raises(runtime.EightUniverseInputQcRuntimeError, match="disagree"):
        runtime._callback_age_bin({}, "2021-01-05", positions, "fresh")
    with pytest.raises(runtime.EightUniverseInputQcRuntimeError, match="disagree"):
        runtime._callback_age_bin({"2021-01-05": ("x", ())}, "2021-01-05", positions, "fresh")


def test_decision_counts_new_sleeves_and_canonical_unique_overlap():
    driver = object.__new__(runtime.EightUniverseInputQcDriver)
    driver._initialized = True
    driver._completed = False
    driver._algorithm = SimpleNamespace(time=datetime(2021, 1, 5, 16))
    driver._session_positions = {"2021-01-04": 0, "2021-01-05": 1}
    driver._decision_sessions = ("2021-01-05",)
    driver._decision_set = frozenset(driver._decision_sessions)
    driver._next_decision_index = 0
    driver._fundamental_cache = {
        "2021-01-04": ("2021-01-04T08:00:00.000000", (
            ("SID-A", "positive", runtime.Decimal("100")),
            ("SID-B", "positive", runtime.Decimal("200")),
        )),
    }
    driver._constituent_caches = {
        ticker: {"2021-01-04": (
            "2021-01-04T08:00:00.000000",
            (("SID-A", runtime.Decimal("1")),) if ticker != "XLF" else
            (("SID-B", runtime.Decimal("1")),),
        )} for ticker in runtime.UNIVERSE_IDS
    }
    driver._security_by_sid = {"SID-A": "SEC-A", "SID-B": "SEC-B"}
    driver._label_by_sid = {"SID-A": "A", "SID-B": "B"}
    driver._records = {
        ticker: {"total": runtime._empty_counts(), **{
            year: runtime._empty_counts() for year in runtime.YEARS
        }} for ticker in runtime.UNIVERSE_IDS
    }
    driver._overlap = {"total": runtime._empty_overlap(), **{
        year: runtime._empty_overlap() for year in runtime.YEARS
    }}
    driver._path_hash = hashlib.sha256()
    assert driver.on_after_close() is True
    assert driver._next_decision_index == 1
    assert driver._records["XLI"]["total"]["joint_pass_99_count"] == 1
    assert driver._records["XLF"]["total"]["joint_pass_99_count"] == 1
    assert driver._records["XLI"]["total"]["relaxed_joint_pass_10_verified3_count"] == 0
    assert driver._records["XLI"]["total"]["constituent_callback_age_bins"]["age_1"] == 1
    assert driver._overlap["total"]["cap_eligible_memberships_sum"] == 8
    assert driver._overlap["total"]["unique_cap_eligible_security_sum"] == 2
    assert driver._overlap["total"]["duplicate_cap_eligible_memberships_sum"] == 6
    assert driver._overlap["total"]["new_sleeve_overlap_with_prior_six"] == {
        "XLI": 1, "XLF": 0,
    }
    with pytest.raises(runtime.EightUniverseInputQcRuntimeError, match="synchronization"):
        driver.on_after_close()


def test_relaxed_joint_count_requires_all_four_policy_components():
    driver = object.__new__(runtime.EightUniverseInputQcDriver)
    driver._security_by_sid = {f"SID-{index}": f"SEC-{index}" for index in range(4)}
    driver._label_by_sid = {f"SID-{index}": f"T{index}" for index in range(4)}
    rows = tuple((f"SID-{index}", runtime.Decimal("0.20")) for index in range(3))
    caps = {sid: runtime.Decimal("100") for sid, _ in rows}
    measured = driver._measure("XLI", "fresh", rows, "fresh", caps)
    assert runtime._relaxed_joint_pass(measured, rows, caps, driver._security_by_sid, driver._label_by_sid)
    assert not runtime._relaxed_joint_pass(measured, rows[:2], caps, driver._security_by_sid, driver._label_by_sid)
    assert not runtime._relaxed_joint_pass(measured, rows, {}, driver._security_by_sid, driver._label_by_sid)
    assert not runtime._relaxed_joint_pass({**measured, "fundamental_status": "stale"}, rows, caps, driver._security_by_sid, driver._label_by_sid)
    assert not runtime._relaxed_joint_pass(driver._measure(
        "XLI", "fresh", tuple((sid, runtime.Decimal("0.02")) for sid, _ in rows),
        "fresh", caps,
    ), tuple((sid, runtime.Decimal("0.02")) for sid, _ in rows), caps,
        driver._security_by_sid, driver._label_by_sid)


def test_unbounded_statistic_refuses_without_emitting_any_statistic():
    driver = object.__new__(runtime.EightUniverseInputQcDriver)
    driver._initialized = True
    driver._completed = False
    emitted = []
    driver._algorithm = SimpleNamespace(
        time=datetime(2025, 12, 31), set_summary_statistic=lambda *args: emitted.append(args),
    )
    driver._next_decision_index = runtime.EXPECTED_DECISION_COUNT
    driver._records = {
        ticker: {"total": runtime._empty_counts(), **{
            year: runtime._empty_counts() for year in runtime.YEARS
        }} for ticker in runtime.UNIVERSE_IDS
    }
    driver._overlap = {"total": runtime._empty_overlap(), **{
        year: runtime._empty_overlap() for year in runtime.YEARS
    }}
    driver._package = SimpleNamespace(
        package_id="package", package_sha256="a" * 64,
        activation_manifest_sha256="b" * 64,
    )
    driver._resolution = SimpleNamespace(
        resolution_id="resolution", resolution_sha256="c" * 64,
    )
    driver._path_hash = hashlib.sha256()
    driver._source_row_count = 0
    for index in range(runtime.EXPECTED_DECISION_COUNT):
        year = runtime.YEARS[min(index // 52, len(runtime.YEARS) - 1)]
        for ticker in runtime.UNIVERSE_IDS:
            driver._records[ticker]["total"]["decision_count"] += 1
            driver._records[ticker][year]["decision_count"] += 1
            driver._records[ticker]["total"]["constituent_callback_age_bins"]["missing"] += 1
            driver._records[ticker][year]["constituent_callback_age_bins"]["missing"] += 1
        driver._overlap["total"]["decision_count"] += 1
        driver._overlap[year]["decision_count"] += 1
    statistics = driver._statistics()
    assert tuple(sorted(statistics)) == runtime.expected_custom_summary_statistic_names()
    assert all(len(value.encode("ascii")) <= runtime.MAXIMUM_STATISTIC_BYTES for value in statistics.values())
    assert "SID-A" not in str(statistics)
    assert "net_profit" not in str(statistics).lower()
    assert "portfolio" not in str(statistics).lower()
    meta = json.loads(statistics[runtime.META_STATISTIC_NAME])
    assert meta["overlap_sha256"] == runtime._six._sha(
        json.loads(statistics[runtime.OVERLAP_STATISTIC_NAME])
    )
    runtime.MAXIMUM_STATISTIC_BYTES, old = 1, runtime.MAXIMUM_STATISTIC_BYTES
    try:
        with pytest.raises(runtime.EightUniverseInputQcRuntimeError, match="byte bound"):
            driver.on_end_of_algorithm()
    finally:
        runtime.MAXIMUM_STATISTIC_BYTES = old
    assert driver.completed is False
    assert emitted == []


@pytest.mark.skipif(not PACKAGE_PATH.is_dir(), reason="local private delta package absent")
def test_exact_ten_file_projection_and_r267_manifest():
    package = delta.load_accepted_risk_delta_order_package(
        PACKAGE_PATH,
        expected_package_sha256=delta.EXPECTED_DELTA_PACKAGE_SHA256,
        expected_lineage_sha256=delta.EXPECTED_DELTA_LINEAGE_SHA256,
    )
    candidate = projection.build_eight_universe_input_qc_projection(package)
    manifest = json.loads(MANIFEST_PATH.read_text("ascii"))
    assert manifest["candidate_id"] == projection.CANDIDATE_ID == "R267"
    assert manifest["maximum_qc_attempts"] == projection.MAXIMUM_QC_ATTEMPTS == 3
    assert manifest["project_visibility"] == "private"
    assert manifest["projection_sha256"] == candidate.projection_sha256
    assert manifest["profile_sha256"] == candidate.profile_sha256
    assert manifest["package_sha256"] == candidate.package_sha256
    assert manifest["package_lineage_sha256"] == candidate.package_lineage_sha256
    assert manifest["activation_manifest_sha256"] == candidate.activation_manifest_sha256
    assert manifest["total_source_byte_count"] == candidate.total_source_byte_count
    assert manifest["source_file_count"] == len(candidate.source_files) == 10
    assert manifest["statistic_names"] == list(candidate.statistic_names)
    assert len(candidate.statistic_names) == 10
    assert candidate.total_source_byte_count <= projection.MAXIMUM_TOTAL_SOURCE_BYTES
    assert {item.project_path for item in candidate.source_files} == {
        item.project_path for item in projection._six.build_six_universe_coverage_qc_projection(package).source_files
    } | {"accepted_risk_eight_universe_input_qc_runtime.py"}
    main = next(item.source_bytes.decode("ascii") for item in candidate.source_files if item.project_path == "main.py")
    six = projection._six.build_six_universe_coverage_qc_projection(package)
    six_main = next(item.source_bytes.decode("ascii") for item in six.source_files if item.project_path == "main.py")
    assert "'XLI', 'XLF'" in main
    for call in (
        "set_start_date(2020, 11, 1)",
        "set_end_date(2025, 12, 30)",
        "after_market_close(benchmark, 0)",
    ):
        assert call in main and call in six_main
    assert runtime.EXPECTED_DECISION_COUNT == projection._six._runtime.EXPECTED_DECISION_COUNT == 261
    assert runtime.EVALUATION_START_SESSION == "2021-01-04"
    assert runtime.EVALUATION_END_SESSION == "2025-12-31"
    assert "decisions[-1] != \"2025-12-29\"" in Path(runtime.__file__).read_text("ascii")
    assert "market_on_open_order" not in main
    assert "history(" not in main
    assert "on_order_event" not in main
    assert candidate.to_record()["outcome_access"] is False
    assert candidate.to_record()["orders"] is False
