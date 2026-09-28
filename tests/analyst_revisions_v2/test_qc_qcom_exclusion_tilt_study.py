"""Offline AR-on tilt family, fake cloud, and R231 compatibility checks."""

import copy
import dataclasses
import hashlib
import json
import sys
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import six_universe_qcom_exclusion_tilt_study as study
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from tests.analyst_revisions_v2.test_qc_matched_study_submission import order_statistics
from tests.analyst_revisions_v2.test_qc_qcom_exclusion_study import (
    manifest_fixture as control_fixture, result_fixture as control_result_fixture,
)
from tests.analyst_revisions_v2.test_qc_relaxed_submission import Fake, ORG, canonical


def manifest_fixture():
    base, initial = control_fixture()
    value = {"schema": study.MANIFEST_SCHEMA, "protocol": copy.deepcopy(study.PROTOCOL),
        "package_sha256": base["package_sha256"],
        "activation_manifest_sha256": base["activation_manifest_sha256"], "candidates": []}
    projections = {}
    for candidate, percent in study.CANDIDATES.items():
        projection = copy.deepcopy(initial)
        first = projection.source_files[0]
        raw = first.source_bytes + f"tilt_percent = {percent}\n".encode("ascii")
        replaced = SimpleNamespace(project_path=first.project_path, source_bytes=raw,
            byte_count=len(raw), content_sha256=hashlib.sha256(raw).hexdigest())
        projection.source_files = (replaced, *projection.source_files[1:])
        projection.total_source_byte_count = sum(item.byte_count for item in projection.source_files)
        projection.schema = f"arv2-six-matched-qcom-excluded-tilt{percent}-projection-v1"
        projection.role = f"matched_qcom_excluded_ar_on{percent}_s0"
        projection.profile_id = f"arv2-six-matched-qcom-excluded-ar_on{percent}-s0-profile-v1"
        projection.profile_sha256 = hashlib.sha256(f"profile-{percent}".encode()).hexdigest()
        projection.projection_sha256 = adapter._sha(projection.semantic())
        row = copy.deepcopy(base["candidates"][1])
        row.update(candidate_id=candidate, tilt_percent=percent, arm=f"ar_on{percent}",
            project_name=f"QCOM excluded tilt {percent} {candidate}",
            backtest_name=f"QCOM excluded tilt result {candidate}",
            kind="order", role=projection.role, profile_id=projection.profile_id,
            profile_sha256=projection.profile_sha256,
            projection_schema=projection.schema,
            projection_sha256=projection.projection_sha256,
            meta_schema=f"arv2-six-matched-qcom-excluded-tilt{percent}-meta-v1",
            summary_schema=f"arv2-six-matched-qcom-excluded-tilt{percent}-summary-v1",
            tilt_fraction=study.TILT_FRACTIONS[percent], slippage_bps=0,
            matched_baseline_profile_sha256=study.CONTROL_AR_ON_BASELINE_PROFILE_SHA256,
            source_file_count=len(projection.source_files),
            source_files_sha256=adapter._sha(projection.semantic()["source_files"]),
            total_source_bytes=projection.total_source_byte_count)
        value["candidates"].append(row)
        projections[candidate] = projection
    return value, projections


def statistics_fixture(row):
    statistics = order_statistics(row)
    report = json.loads(statistics[study.control.DIAGNOSTIC_NAME])
    report["arm"] = "ar_on100"
    aggregate = json.loads(statistics["ARV2_SIX_GATE_ORDER_AGGREGATES"])
    aggregate.update(analyst_revision_economic_usage="entry_count_and_weight",
        stock_exclusion_policy_id=study.control.EXCLUSION_RULE,
        excluded_logical_security_sha256=study.control.EXCLUDED_STOCK_SECURITY_ID_SHA256)
    raw = canonical(aggregate).decode("ascii")
    statistics["ARV2_SIX_GATE_ORDER_AGGREGATES"] = raw
    statistics[study.control.DIAGNOSTIC_NAME] = canonical(report).decode("ascii")
    meta = json.loads(statistics["ARV2_SIX_GATE_ORDER_META"])
    meta["aggregate_sha256"] = hashlib.sha256(raw.encode("ascii")).hexdigest()
    meta["matched_diagnostics_sha256"] = adapter._sha(report)
    statistics["ARV2_SIX_GATE_ORDER_META"] = canonical(meta).decode("ascii")
    return statistics


def shared_meta_statistics(row):
    statistics = statistics_fixture(row)
    meta = json.loads(statistics["ARV2_SIX_GATE_ORDER_META"])
    meta["schema"] = study.SHARED_ORDER_META_SCHEMA
    statistics["ARV2_SIX_GATE_ORDER_META"] = canonical(meta).decode("ascii")
    return statistics


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    manifest, projections = manifest_fixture()
    path = tmp_path / "qcom-tilt.json"
    raw = canonical(manifest)
    path.write_bytes(raw)
    monkeypatch.setattr(adapter, "QCOM_EXCLUSION_TILT_MANIFEST_PATH", path)
    monkeypatch.setattr(adapter, "FROZEN_QCOM_EXCLUSION_TILT_MANIFEST_SHA256",
                        hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(adapter, "_require_inputs", lambda plan: None)
    monkeypatch.setattr(adapter.common, "_client", lambda api: None)
    fake = Fake()
    monkeypatch.setattr(adapter.common, "_post", fake.post)
    return manifest, projections, fake, tmp_path / "controls"


def test_new_family_freezes_three_distinct_zero_slippage_order_sources():
    manifest, projections = manifest_fixture()
    assert study.validate_manifest(manifest) is manifest
    assert set(projections) == set(study.CANDIDATES)
    assert [row["tilt_fraction"] for row in manifest["candidates"]] == ["0.80", "1.20", "2.00"]
    assert manifest["protocol"]["control_candidate_id"] == "R231"
    assert manifest["protocol"]["confirmation"] is False
    assert manifest["protocol"]["capacity_search"] is False


def test_real_package_projects_exact_manifest_and_previews_offline(monkeypatch, tmp_path):
    from scripts import run_arv2_qcom_exclusion as script
    from scripts import run_arv2_qcom_exclusion_tilt as tilt_script
    from research.analyst_revisions_v2_qc import accepted_risk_matched_historical_projection as source
    from research.analyst_revisions_v2_qc import six_universe_settlement_submission as common

    raw = adapter.QCOM_EXCLUSION_TILT_MANIFEST_PATH.read_bytes()
    value = json.loads(raw)
    assert study.validate_manifest(value) is value
    assert raw == (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("ascii")
    monkeypatch.setattr(adapter, "FROZEN_QCOM_EXCLUSION_TILT_MANIFEST_SHA256",
                        hashlib.sha256(raw).hexdigest())
    inputs = script.package()
    projected_by_candidate = {}
    for row in value["candidates"]:
        projected, profile = source.build_qcom_exclusion_tilt_projection(
            inputs, row["tilt_percent"], 0)
        projected_by_candidate[row["candidate_id"]] = (projected, profile)
        files = [[item.project_path, item.content_sha256, item.byte_count]
                 for item in projected.source_files]
        assert projected.projection_sha256 == row["projection_sha256"]
        assert projected.profile_sha256 == profile["profile_sha256"] == row["profile_sha256"]
        assert projected.role == row["role"]
        assert projected.schema == row["projection_schema"]
        assert projected.profile_id == row["profile_id"]
        assert profile["maximum_stock_weight_change_fraction"] == row["tilt_fraction"]
        assert profile["matched_baseline_profile_sha256"] == row["matched_baseline_profile_sha256"]
        assert hashlib.sha256(common._canonical(files)).hexdigest() == row["source_files_sha256"]
        assert projected.total_source_byte_count == row["total_source_bytes"]
        plan = adapter.build_plan(row["candidate_id"], ORG, tmp_path / "control",
                                  family=study.FAMILY)
        assert adapter.preview(plan, projected)["projection_sha256"] == row["projection_sha256"]
    monkeypatch.setattr(tilt_script, "package", lambda: inputs)
    monkeypatch.setattr(tilt_script, "projected",
                        lambda candidate, inputs=None: projected_by_candidate[candidate])
    assert tilt_script.freeze() == value
    assert tilt_script.CONTROL != script.CONTROL


@pytest.mark.parametrize("defect", ("missing", "reordered", "old_candidate", "bool_percent",
    "wrong_percent", "wrong_arm", "wrong_tilt", "wrong_cost", "wrong_package",
    "wrong_policy", "wrong_control", "wrong_baseline", "duplicate_source",
    "wrong_schema", "wrong_role", "extra_field", "false_confirmation"))
def test_manifest_refuses_alias_or_changed_economics(defect):
    value, _ = manifest_fixture()
    row = value["candidates"][0]
    if defect == "missing":
        value["candidates"].pop()
    elif defect == "reordered":
        value["candidates"].reverse()
    elif defect == "old_candidate":
        row["candidate_id"] = "R232"
    elif defect == "bool_percent":
        row["tilt_percent"] = True
    elif defect == "wrong_percent":
        row["tilt_percent"] = 100
    elif defect == "wrong_arm":
        row["arm"] = "ar_on100"
    elif defect == "wrong_tilt":
        row["tilt_fraction"] = "1.00"
    elif defect == "wrong_cost":
        row["slippage_bps"] = 5
    elif defect == "wrong_package":
        value["package_sha256"] = "f" * 64
    elif defect == "wrong_policy":
        value["protocol"]["exclusion_rule"] = "skip_price_lookup"
    elif defect == "wrong_control":
        value["protocol"]["control_candidate_id"] = "R232"
    elif defect == "wrong_baseline":
        row["matched_baseline_profile_sha256"] = "f" * 64
    elif defect == "duplicate_source":
        value["candidates"][1]["source_files_sha256"] = row["source_files_sha256"]
    elif defect == "wrong_schema":
        row["meta_schema"] = "old-family"
    elif defect == "wrong_role":
        row["role"] = "matched_qcom_excluded_ar_on100_s0"
    elif defect == "extra_field":
        row["undisclosed"] = True
    elif defect == "false_confirmation":
        value["protocol"]["confirmation"] = 0
    with pytest.raises(adapter.RelaxedQcSubmissionError):
        study.validate_manifest(value)


@pytest.mark.parametrize("candidate", tuple(study.CANDIDATES))
def test_each_candidate_fake_cloud_claim_preview_and_one_bounded_read(frozen, candidate):
    manifest, projections, fake, control = frozen
    plan = adapter.build_plan(candidate, ORG, control, family=study.FAMILY)
    identity = adapter.preview(plan, projections[candidate])
    assert identity["candidate_id"] == candidate
    assert identity["manifest_sha256"] == adapter.FROZEN_QCOM_EXCLUSION_TILT_MANIFEST_SHA256
    receipt = adapter.launch(plan, projections[candidate], fake)
    fake.status = "Completed."
    assert adapter.poll_status(plan, receipt, fake) == "Completed."
    row = next(item for item in manifest["candidates"] if item["candidate_id"] == candidate)
    fake.statistics = {**statistics_fixture(row), "Net Profit": "NOT RETAINED"}
    parsed = adapter.read_result_once(plan, receipt, fake)
    assert parsed["run_valid"] is True
    assert parsed["aggregates"]["comparison_arm"] == f"ar_on{study.CANDIDATES[candidate]}"
    assert parsed["diagnostics"]["arm"] == "ar_on100"
    assert "NOT RETAINED" not in str(parsed)
    assert sum(endpoint == "backtests/read" for endpoint, _ in fake.calls) == 1
    with pytest.raises(adapter.common.SixUniverseSettlementSubmissionError):
        adapter.read_result_once(plan, receipt, fake)


@pytest.mark.parametrize("candidate", tuple(study.CANDIDATES))
def test_shared_meta_schema_is_accepted_only_for_exact_frozen_tilt_source(tmp_path, candidate):
    manifest = adapter._qcom_exclusion_tilt_manifest()
    row = next(item for item in manifest["candidates"] if item["candidate_id"] == candidate)
    plan = adapter.build_plan(candidate, ORG, tmp_path / "control", family=study.FAMILY)
    statistics = shared_meta_statistics(row)
    parsed = adapter._parse_order(plan, statistics)
    assert parsed["run_valid"] is True
    assert parsed["meta"]["schema"] == study.SHARED_ORDER_META_SCHEMA

    for changed in ("unrelated-meta-v1", "arv2-six-matched-historical-meta-v1"):
        wrong = copy.deepcopy(statistics)
        meta = json.loads(wrong["ARV2_SIX_GATE_ORDER_META"])
        meta["schema"] = changed
        wrong["ARV2_SIX_GATE_ORDER_META"] = canonical(meta).decode("ascii")
        with pytest.raises(adapter.RelaxedQcSubmissionError):
            adapter._parse_order(plan, wrong)

    for field in ("role", "profile_sha256", "aggregate_sha256"):
        wrong = copy.deepcopy(statistics)
        meta = json.loads(wrong["ARV2_SIX_GATE_ORDER_META"])
        meta[field] = "f" * 64
        wrong["ARV2_SIX_GATE_ORDER_META"] = canonical(meta).decode("ascii")
        with pytest.raises(adapter.RelaxedQcSubmissionError):
            adapter._parse_order(plan, wrong)


def test_shared_meta_schema_refuses_other_source_census(frozen):
    manifest, _projections, _fake, control = frozen
    plan = adapter.build_plan("R235", ORG, control, family=study.FAMILY)
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="shared META source identity"):
        adapter._parse_order(plan, shared_meta_statistics(manifest["candidates"][0]))


def retained_fake_artifacts(frozen, candidate="R235"):
    manifest, projections, fake, control = frozen
    plan = adapter.build_plan(candidate, ORG, control, family=study.FAMILY)
    receipt = adapter.launch(plan, projections[candidate], fake)
    fake.status = "Completed."
    assert adapter.poll_status(plan, receipt, fake) == "Completed."
    row = next(item for item in manifest["candidates"] if item["candidate_id"] == candidate)
    expected = {"candidate_id": candidate, "attempt": 1,
        "project_id": receipt["project_id"], "backtest_id": receipt["backtest_id"],
        "status": "Completed."}
    adapter.common._write(adapter._path(plan, "read-claim"), expected)
    adapter._write_artifact(adapter._path(plan, "raw-custom"),
                            {**expected, "statistics": statistics_fixture(row)})
    return plan, fake, control, expected


@pytest.mark.parametrize("candidate", tuple(study.CANDIDATES))
def test_recover_retained_result_is_local_once_only(frozen, monkeypatch, candidate):
    from scripts import run_arv2_qcom_exclusion_tilt as script
    plan, fake, control, expected = retained_fake_artifacts(frozen, candidate)
    calls = list(fake.calls)
    monkeypatch.setattr(script.credentials, "production_client",
                        lambda: pytest.fail("recovery must not create a cloud client"))
    parsed = script.recover_retained_result(candidate, control=control)
    assert parsed["run_valid"] is True
    assert fake.calls == calls
    result = adapter._read_artifact(adapter._path(plan, "result"))
    assert result == {**expected, **parsed,
        "manifest_sha256": adapter.FROZEN_QCOM_EXCLUSION_TILT_MANIFEST_SHA256,
        "projection_sha256": adapter._candidate(plan)["projection_sha256"]}
    with pytest.raises(ValueError, match="already present"):
        script.recover_retained_result(candidate, control=control)


def test_recover_cli_uses_only_retained_local_artifacts(frozen, monkeypatch, capsys):
    from scripts import run_arv2_qcom_exclusion_tilt as script
    plan, fake, control, _expected = retained_fake_artifacts(frozen)
    calls = list(fake.calls)
    monkeypatch.chdir(script.ROOT)
    monkeypatch.setattr(script, "CONTROL", control)
    monkeypatch.setattr(script.credentials, "production_client",
                        lambda: pytest.fail("recovery must not create a cloud client"))
    monkeypatch.setattr(sys, "argv", ["run_arv2_qcom_exclusion_tilt.py", "recover", "R235"])
    script.main()
    assert json.loads(capsys.readouterr().out)["run_valid"] is True
    assert adapter._path(plan, "result").exists()
    assert fake.calls == calls


@pytest.mark.parametrize("defect", ("launch", "terminal", "read_claim", "raw_identity",
                                    "raw_schema", "existing_result"))
def test_recover_refuses_changed_or_absent_spent_read_artifacts(frozen, defect):
    from scripts import run_arv2_qcom_exclusion_tilt as script
    plan, fake, control, expected = retained_fake_artifacts(frozen)
    if defect == "launch":
        path = adapter._path(plan, "launch")
        launch = adapter.common._read(path)
        launch["projection_sha256"] = "f" * 64
        path.write_bytes(canonical(launch))
    elif defect == "terminal":
        adapter._path(plan, "terminal").write_bytes(canonical({**expected, "status": "Runtime Error"}))
    elif defect == "read_claim":
        adapter._path(plan, "read-claim").unlink()
    elif defect in ("raw_identity", "raw_schema"):
        path = adapter._path(plan, "raw-custom")
        raw = adapter._read_artifact(path)
        if defect == "raw_identity":
            raw["backtest_id"] = "f" * 32
        else:
            statistics = raw["statistics"]
            meta = json.loads(statistics["ARV2_SIX_GATE_ORDER_META"])
            meta["schema"] = "unrelated-meta-v1"
            statistics["ARV2_SIX_GATE_ORDER_META"] = canonical(meta).decode("ascii")
        path.write_bytes(canonical(raw))
    else:
        adapter._write_artifact(adapter._path(plan, "result"), {"already": "spent"})
    calls = list(fake.calls)
    with pytest.raises((ValueError, adapter.RelaxedQcSubmissionError,
                        adapter.common.SixUniverseSettlementSubmissionError)):
        script.recover_retained_result("R235", control=control)
    assert fake.calls == calls
    if defect != "existing_result":
        assert not adapter._path(plan, "result").exists()


def test_manifest_pin_or_projection_change_refuses_before_cloud(frozen):
    manifest, projections, fake, control = frozen
    plan = adapter.build_plan("R235", ORG, control, family=study.FAMILY)
    projection = projections["R235"]
    projection.profile_sha256 = "f" * 64
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="projection"):
        adapter.launch(plan, projection, fake)
    assert fake.calls == []
    projection.profile_sha256 = manifest["candidates"][0]["profile_sha256"]
    adapter.QCOM_EXCLUSION_TILT_MANIFEST_PATH.write_bytes(b"{}")
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="frozen manifest"):
        adapter.launch(plan, projection, fake)
    assert fake.calls == []


def test_three_failed_compile_attempts_exhaust_candidate_without_extra_run(frozen):
    _manifest, projections, fake, control = frozen
    fake.compile_state = "BuildError"
    for attempt in (1, 2, 3):
        plan = adapter.build_plan("R235", ORG, control, attempt, family=study.FAMILY)
        with pytest.raises(adapter.RelaxedQcSubmissionError, match="compile failed"):
            adapter.launch(plan, projections["R235"], fake)
        assert adapter._path(plan, "claim").exists()
        assert adapter._path(plan, "terminal").exists()
    assert sum(endpoint == "projects/create" for endpoint, _ in fake.calls) == 1
    assert not any(endpoint == "backtests/create" for endpoint, _ in fake.calls)
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="bound"):
        adapter.build_plan("R235", ORG, control, 4, family=study.FAMILY)


def comparison_fixture(frozen):
    manifest, _projections, _fake, _control = frozen
    control_row = adapter._qcom_exclusion_manifest()["candidates"][0]
    original = control_result_fixture()["R231"]
    results = {}
    for candidate, row in [("R231", control_row), *zip(study.CANDIDATES, manifest["candidates"])]:
        result = copy.deepcopy(original)
        percent = study.CANDIDATES.get(candidate)
        ret = "0.20" if percent is None else {80: "0.24", 120: "0.26", 200: "0.31"}[percent]
        aggregate = result["aggregates"]
        aggregate.update(comparison_arm=("ar_off" if percent is None else f"ar_on{percent}"),
            analyst_revision_economic_usage=("none_authenticated_score_clock_only" if percent is None
                else "entry_count_and_weight"),
            maximum_stock_weight_change_fraction=row["tilt_fraction"],
            matched_baseline_profile_sha256=row["matched_baseline_profile_sha256"])
        aggregate["account"]["cumulative_return"] = ret
        result["diagnostics"]["overall_cumulative_return"] = ret
        result["diagnostics"]["annual_account_rows"][-1][5] = ret
        result["diagnostics"]["arm"] = "ar_off" if percent is None else "ar_on100"
        result.update(candidate_id=candidate, attempt=1, status="Completed.",
            manifest_sha256=(adapter.FROZEN_QCOM_EXCLUSION_MANIFEST_SHA256 if percent is None
                else adapter.FROZEN_QCOM_EXCLUSION_TILT_MANIFEST_SHA256),
            projection_sha256=row["projection_sha256"])
        results[candidate] = result
    return results


def test_comparator_requires_compatible_r231_and_reports_three_spreads(frozen, monkeypatch):
    from scripts import run_arv2_qcom_exclusion_tilt as script
    results = comparison_fixture(frozen)
    assert all("decision_count" not in result["aggregates"]["execution"]
               for result in results.values())
    compared = study.compare_results(results)
    assert compared["comparison_valid"] is True
    assert compared["control_candidate_id"] == "R231"
    assert compared["formal_alpha"] is False
    assert [row["AR_on_minus_R231_AR_off_percentage_points"] for row in compared["comparisons"]] == [
        "4.00", "6.00", "11.00"]
    calls = []
    def cached(candidate, control, family):
        calls.append((candidate, control, family))
        return results[candidate]
    monkeypatch.setattr(script, "authenticated_cached_result", cached)
    assert script.compare_cached() == compared
    assert calls == [("R231", script.R231_CONTROL, "qcom_exclusion"),
        *((candidate, script.CONTROL, study.FAMILY) for candidate in study.CANDIDATES)]


@pytest.mark.parametrize("defect", ("old_family", "missing", "invalid", "wrong_arm",
    "wrong_tilt", "wrong_slippage", "wrong_exclusion", "wrong_source", "wrong_panel",
    "wrong_capital", "wrong_census", "wrong_rebalance", "nonfinite_return"))
def test_comparator_refuses_unmatched_or_invalid_results(frozen, defect):
    results = comparison_fixture(frozen)
    bad = results["R237"]
    if defect == "old_family":
        bad["manifest_sha256"] = adapter.FROZEN_QCOM_EXCLUSION_MANIFEST_SHA256
    elif defect == "missing":
        results.pop("R237")
    elif defect == "invalid":
        bad["run_valid"] = False
    elif defect == "wrong_arm":
        bad["aggregates"]["comparison_arm"] = "ar_on100"
    elif defect == "wrong_tilt":
        bad["aggregates"]["maximum_stock_weight_change_fraction"] = "1.00"
    elif defect == "wrong_slippage":
        bad["diagnostics"]["slippage_bps_per_side"] = 5
    elif defect == "wrong_exclusion":
        bad["aggregates"]["excluded_logical_security_sha256"] = "f" * 64
    elif defect == "wrong_source":
        bad["diagnostics"]["membership_cap_path_sha256"] = "f" * 64
    elif defect == "wrong_panel":
        bad["diagnostics"]["etf_daily_panel_sha256"] = "f" * 64
    elif defect == "wrong_capital":
        bad["aggregates"]["account"]["starting_equity"] = "200000"
    elif defect == "wrong_census":
        bad["aggregates"]["pit_callback_source_row_count"] += 1
    elif defect == "wrong_rebalance":
        bad["aggregates"]["execution"]["completed_rebalance_count"] = 260
    elif defect == "nonfinite_return":
        bad["aggregates"]["account"]["cumulative_return"] = "NaN"
    with pytest.raises((ValueError, study.diagnostics._base.AcceptedRiskSixUniverseOrderQcRuntimeError)):
        study.compare_results(results)
