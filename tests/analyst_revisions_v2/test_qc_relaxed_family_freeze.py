"""Actual prospective family pins, not a synthetic launch authority."""

import hashlib
import pytest

from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_relaxed_qc_projection as projection
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from tests.analyst_revisions_v2 import test_qc_recent_coverage_projection as inputs

prior_package = inputs.prior_package
actual_package = inputs.actual_package


def test_manifest_is_exact_prospective_policy_and_capacity_census():
    family = adapter._manifest()
    assert family["coverage_policy"] == [
        ["QQQ", "0.70", "0.80", "0.95", 5],
        ["SOXX", "0.70", "0.80", "0.95", 5],
        ["REMX", "0.50", "0.50", "0.25", 5]]
    assert [row["candidate_id"] for row in family["candidates"]] == [f"R{n}" for n in range(209, 220)]
    assert [row["tilt_fraction"] for row in family["candidates"][1:]] == [
        f"{n // 100}.{n % 100:02d}" for n in range(20, 201, 20)]
    assert family["candidates"][0]["projection_sha256"] == "5bd2733a5f05582845f707178992f56081e8fe78e615bb0294e9506c0e0b2690"
    assert hashlib.sha256(adapter.MANIFEST_PATH.read_bytes()).hexdigest() == adapter.FROZEN_MANIFEST_SHA256


@pytest.fixture(scope="module")
def family_projections(prior_package, actual_package):
    family = adapter._manifest()
    policy = tuple(tuple(item) for item in family["coverage_policy"])
    return {f"R{209 + percent // 20}": projection.build_relaxed_order_projection(
        prior_package, actual_package, percent, policy) for percent in range(20, 201, 20)}


@pytest.mark.parametrize("candidate", [f"R{n}" for n in range(210, 220)])
def test_actual_source_profile_preview_matches_frozen_row(candidate, family_projections, tmp_path):
    value, profile = family_projections[candidate]
    plan = adapter.build_plan(candidate, "a" * 32, tmp_path / "control")
    preview = adapter.preview(plan, value)
    assert preview["profile_sha256"] == profile["profile_sha256"]
    assert value.total_source_byte_count + 32768 <= 448 * 1024
    assert profile["target_gross_exposure"] == "0.98"
    assert profile["gate_profile_sha256"] == family_projections["R210"][1]["gate_profile_sha256"]
    assert profile["matched_baseline_profile_sha256"] == family_projections["R210"][1]["matched_baseline_profile_sha256"]
    row = next(row for row in adapter._manifest()["candidates"] if row["candidate_id"] == candidate)
    assert row["summary_schema"] == projection.SUMMARY_SCHEMAS[(int(candidate[1:]) - 209) * 20]
    assert row["meta_schema"] == projection.META_SCHEMA
    assert (profile["evaluation_start_session"], profile["evaluation_end_session"],
            profile["evaluation_session_count"], profile["decision_count"]) == (
                "2025-08-01", "2026-09-25", 290, 61)
