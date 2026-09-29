"""Guard-specific checks for the fixed-100% eight-sleeve factorial family."""

import hashlib

import pytest

from research.analyst_revisions_v2_qc import eight_universe_attribution_study as study
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter


def _plan(candidate="R277", attempt=1):
    return adapter.build_plan(candidate, "a" * 32, study.CONTROL, attempt,
                              family=study.FAMILY)


def test_factorial_manifest_and_adapter_route_are_exact():
    frozen = study.frozen_manifest()
    assert hashlib.sha256(study.MANIFEST_PATH.read_bytes()).hexdigest() == study.FROZEN_MANIFEST_SHA256
    assert adapter._plan_manifest(_plan()) == frozen
    assert adapter._plan_manifest_sha256(_plan()) == study.FROZEN_MANIFEST_SHA256
    assert [row["candidate_id"] for row in frozen["candidates"]] == ["R277", "R278"]
    assert [row["arm"] for row in frozen["candidates"]] == [
        "ar_on100_weights_only", "ar_on0"]
    assert [row["tilt_fraction"] for row in frozen["candidates"]] == ["1.00", "0.00"]


def test_factorial_attempts_have_exact_three_slot_bound():
    assert _plan("R277", 3).attempt == 3
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="three-attempt"):
        _plan("R277", 4)
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="candidate is not frozen"):
        _plan("R279")


def _path_record(value):
    return {"aggregates": {"matched_baseline_target_path_sha256": value}}


def test_both_factorial_holdings_paths_are_load_bearing():
    parents = {key: _path_record(value) for key, value in
               study.PARENT_BASELINE_PATH_SHA256.items()}
    new = {"R277": _path_record(study.PARENT_BASELINE_PATH_SHA256["R268"]),
           "R278": _path_record(study.PARENT_BASELINE_PATH_SHA256["R270"])}
    assert study._require_fixed_holdings_paths(parents, new) is True
    for changed in ("R277", "R278"):
        mutant = {**new, changed: _path_record("0" * 64)}
        with pytest.raises(adapter.RelaxedQcSubmissionError, match="holdings paths"):
            study._require_fixed_holdings_paths(parents, mutant)


@pytest.mark.parametrize("candidate", ["R277", "R278"])
def test_parser_refuses_a_changed_attribution_arm_before_result_use(monkeypatch, candidate):
    plan = _plan(candidate)
    row = adapter._candidate(plan)
    parsed = {"meta": {"matched_diagnostics_sha256": "digest"},
              "aggregates": {
                  "comparison_arm": "unrelated",
                  "analyst_revision_economic_usage": row["analyst_revision_economic_usage"],
                  "coverage_policy_id": row["coverage_policy_id"],
                  "account": {"cumulative_return": "0.1"}}}
    monkeypatch.setattr(adapter, "_parse_order_common", lambda *a, **kw: parsed)
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="economic arm"):
        study.parse_order(plan, {key: "{}" for key in study.STATISTIC_NAMES})


def test_parser_refuses_diagnostic_digest_mismatch(monkeypatch):
    plan = _plan()
    row = adapter._candidate(plan)
    parsed = {"meta": {"matched_diagnostics_sha256": "wrong"},
              "aggregates": {
                  "comparison_arm": row["arm"],
                  "analyst_revision_economic_usage": row["analyst_revision_economic_usage"],
                  "coverage_policy_id": row["coverage_policy_id"],
                  "account": {"cumulative_return": "0.1"}}}
    monkeypatch.setattr(adapter, "_parse_order_common", lambda *a, **kw: parsed)
    monkeypatch.setattr(adapter, "_statistic", lambda *a, **kw: {
        "arm": row["arm"], "overall_cumulative_return": "0.1"})
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="diagnostic digest"):
        study.parse_order(plan, {key: "{}" for key in study.STATISTIC_NAMES})
