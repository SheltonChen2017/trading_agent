"""Guard-specific checks for the fixed-100% eight-sleeve factorial family."""

import hashlib
from decimal import Decimal

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


def test_annual_factorial_contrasts_pin_the_common_calendar_axis():
    def arm(value):
        return {"diagnostics": {"annual_account_rows": [
            [str(year), 250 + (year == 2021), year != 2021,
             f"{year}-01-04", f"{year}-12-31", value, "-0.1", "0.2", "0.5"]
            for year in range(2021, 2026)]}}
    arms = {"cap_base": arm("0"), "cap_AR_weight": arm("0.1"),
            "AR_entry_base_weight": arm("0.2"), "AR_entry_AR_weight": arm("0.4")}
    annual, uncertainty = study._annual_contrasts(arms)
    assert len(annual) == 5
    assert Decimal(annual[0]["AR_weight_on_cap_holdings_pp"]) == 10
    assert Decimal(annual[0]["AR_entry_count_at_base_weights_pp"]) == 20
    assert Decimal(annual[0]["AR_weight_on_AR_entry_holdings_pp"]) == 20
    assert Decimal(annual[0]["entry_weight_interaction_pp"]) == 10
    assert Decimal(annual[0]["full_minus_cap_base_pp"]) == 40
    assert uncertainty["full_minus_cap_base_pp"]["t_over_five_years"] is None
    arms["AR_entry_AR_weight"]["diagnostics"]["annual_account_rows"][2][4] = "2023-12-28"
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="annual axes differ"):
        study._annual_contrasts(arms)


@pytest.mark.parametrize("unavailable", [True, False])
def test_predecessor_result_bytes_must_be_available_and_exact(monkeypatch, unavailable):
    class ResultPath:
        def read_bytes(self):
            if unavailable:
                raise OSError("not available")
            return b"changed predecessor result"

    old_path = adapter._path
    monkeypatch.setattr(adapter, "_path", lambda plan, kind: (
        ResultPath() if kind == "result" else old_path(plan, kind)))
    with pytest.raises(adapter.RelaxedQcSubmissionError, match=(
            "predecessor result is unavailable" if unavailable else
            "predecessor result bytes changed")):
        study.require_parents(_plan())
