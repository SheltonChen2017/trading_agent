"""Focused R268 A2 source, attempt, and redacted-read guards."""

import ast
import copy
import dataclasses
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import eight_universe_r268_a2_diagnostic as a2
from research.analyst_revisions_v2_qc import eight_universe_study as study
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_relaxed_qc_projection as loader
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from research.analyst_revisions_v2_qc import six_universe_settlement_submission as common
from scripts import run_arv2_eight_universe as script
from tests.analyst_revisions_v2.test_qc_relaxed_submission import order_fixture


ORG = "a" * 32


@pytest.fixture(scope="module")
def projections():
    inputs = script.package()
    return (script.projected("R268", inputs, attempt=1),
            script.projected("R268", inputs, attempt=2))


def _plan(tmp_path, attempt):
    return adapter.build_plan("R268", ORG, tmp_path / "control", attempt,
                              family=study.FAMILY)


def _payload(*, run_valid=False):
    rows = [] if run_valid else [{
        "execution_session": "2024-06-11",
        "classification": "missing_same_session_split_record",
        "changed_holding_count": 2,
        "rejected_holding_count": 1,
        "late_split_record_count": 0,
    }]
    return {
        "schema": a2.DIAGNOSTIC_SCHEMA,
        "candidate_id": "R268", "attempt": 2,
        "a1_manifest_sha256": adapter.FROZEN_EIGHT_UNIVERSE_MANIFEST_SHA256,
        "a1_projection_sha256": a2._a1_row()["projection_sha256"],
        "profile_sha256": a2._a1_row()["profile_sha256"],
        "run_valid": run_valid,
        "holding_drift_skip_count": len(rows),
        "rejections": rows,
    }


def _stats(payload, *, raw_skip=None):
    aggregate, _, _ = order_fixture()
    aggregate["execution"]["holding_drift_skipped_rebalance_count"] = (
        payload["holding_drift_skip_count"] if raw_skip is None else raw_skip)
    return {
        study.STATISTIC_NAMES[0]: "{}",
        study.STATISTIC_NAMES[1]: common._canonical(aggregate).decode("ascii"),
        study.STATISTIC_NAMES[2]: "{}",
        a2.STATISTIC_NAME: common._canonical(payload).decode("ascii"),
    }


def test_a1_pin_and_attempt_specific_a2_source_are_separate(projections, tmp_path):
    (a1_source, a1_profile), (a2_source, a2_profile) = projections
    a1_plan, a2_plan = _plan(tmp_path, 1), _plan(tmp_path, 2)
    original = adapter.preview(a1_plan, a1_source)
    diagnostic = adapter.preview(a2_plan, a2_source)
    assert original["manifest_sha256"] == adapter.FROZEN_EIGHT_UNIVERSE_MANIFEST_SHA256
    assert diagnostic["manifest_sha256"] == adapter.FROZEN_EIGHT_R268_A2_MANIFEST_SHA256
    assert original["projection_sha256"] != diagnostic["projection_sha256"]
    assert a1_profile == a2_profile
    assert original["profile_sha256"] == diagnostic["profile_sha256"]
    assert original["source_files"] != diagnostic["source_files"]
    changed = {old.project_path for old, new in zip(a1_source.source_files, a2_source.source_files)
               if old.content_sha256 != new.content_sha256}
    assert changed == {a2._TILT, a2._BRIDGE}
    assert [item.project_path for item in a1_source.source_files] == [
        item.project_path for item in a2_source.source_files]
    assert diagnostic["source_files"] == sorted(diagnostic["source_files"])
    raw = adapter.EIGHT_R268_A2_MANIFEST_PATH.read_bytes()
    assert raw == common._canonical(a2.freeze_manifest(script.package())) + b"\n"
    assert adapter._eight_r268_a2_manifest()["candidates"][0]["project_name"] == (
        adapter._eight_universe_manifest()["candidates"][0]["project_name"])
    a3_plan = adapter.build_plan("R268", ORG, tmp_path / "control", 3,
                                 family=study.FAMILY)
    assert adapter._plan_manifest_sha256(a3_plan) == (
        adapter.FROZEN_EIGHT_R268_A3_MANIFEST_SHA256)
    assert adapter._plan_manifest_sha256(a2_plan) == (
        adapter.FROZEN_EIGHT_R268_A2_MANIFEST_SHA256)


def test_a2_manifest_refuses_strategy_economics_or_a1_lineage_change():
    manifest = copy.deepcopy(adapter._eight_r268_a2_manifest())
    for field, replacement in (("tilt_fraction", "1.00"),
                               ("minimum_positive_score_count", 1),
                               ("profile_sha256", "f" * 64)):
        changed = copy.deepcopy(manifest)
        changed["candidates"][0][field] = replacement
        with pytest.raises(adapter.RelaxedQcSubmissionError):
            a2.validate_manifest(changed)
    manifest["a1_projection_sha256"] = "f" * 64
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="ancestry"):
        a2.validate_manifest(manifest)


def test_generated_source_adds_only_redacted_observation(projections):
    a1_source, _ = projections[0]
    a2_source, _ = projections[1]
    old = {item.project_path: item.source_bytes for item in a1_source.source_files}
    new = {item.project_path: item.source_bytes for item in a2_source.source_files}
    for path in old:
        if path not in {a2._BRIDGE, a2._TILT}:
            assert old[path] == new[path]
    tilt = ast.parse(new[a2._TILT].decode("ascii"))
    driver = next(node for node in tilt.body if isinstance(node, ast.ClassDef)
                  and node.name == "AcceptedRiskSixUniverseOrderTiltQcDriver")
    drift = next(node for node in driver.body if isinstance(node, ast.FunctionDef)
                 and node.name == "_holding_drift_replan")
    assert "super()._holding_drift_replan" in ast.unparse(drift)
    assert "market_on_open_order" not in ast.unparse(drift)
    bridge = new[a2._BRIDGE].decode("ascii")
    assert a2.STATISTIC_NAME in bridge
    assert "_r268_a2_diagnostic_payload(self, aggregate)" in bridge
    assert '"security_id"' not in a2._PAYLOAD_FUNCTION
    assert '"symbol"' not in a2._PAYLOAD_FUNCTION
    with loader._cloud_loader({path: raw.decode("ascii") for path, raw in new.items()}) as (load, _):
        runtime = load(a2._TILT[:-3])
        assert set(runtime.expected_tilt_custom_statistic_names()) == (
            set(study.STATISTIC_NAMES) | {a2.STATISTIC_NAME})


def test_missing_split_later_arrival_is_counted_without_identity_output(projections):
    # Exercise the exact methods embedded in the A2 QC source. The original
    # authority is represented by a base that rejected the pre-open replan.
    source = {item.project_path: item.source_bytes.decode("ascii")
              for item in projections[1][0].source_files}
    tilt = ast.parse(source[a2._TILT])
    driver = next(node for node in tilt.body if isinstance(node, ast.ClassDef)
                  and node.name == "AcceptedRiskSixUniverseOrderTiltQcDriver")
    method = next(node for node in driver.body if isinstance(node, ast.FunctionDef)
                  and node.name == "_holding_drift_replan")
    bridge = ast.parse(source[a2._BRIDGE])
    payload_function = next(node for node in bridge.body if isinstance(node, ast.FunctionDef)
                            and node.name == "_r268_a2_diagnostic_payload")
    namespace = {"_base": SimpleNamespace(Decimal=Decimal,
        _canonical=common._canonical, _error=lambda message: (_ for _ in ()).throw(ValueError(message))),
        "_error": lambda message: (_ for _ in ()).throw(ValueError(message))}
    exec("class Original:\n    def _holding_drift_replan(self, *args):\n"
         "        return None\nclass Probe(Original):\n    "
         + ast.unparse(method).replace("\n", "\n    ") + "\n",
         namespace)
    exec(compile(ast.Module(body=[payload_function], type_ignores=[]),
                 "a2-diagnostic-payload", "exec"), namespace)
    probe = namespace["Probe"]()
    probe._split_records_by_session = {}
    actual_time = SimpleNamespace(date=lambda: SimpleNamespace(isoformat=lambda: "2024-06-11"))
    plan = SimpleNamespace(starting_quantities=(("private-SID", 10),))
    assert probe._holding_drift_replan(plan, Decimal(0), {"private-SID": 11},
                                       actual_time) is None
    aggregate = {"execution": {"holding_drift_skipped_rebalance_count": 1},
                 "run_valid": False, "profile_sha256": a2._a1_row()["profile_sha256"]}
    first = namespace["_r268_a2_diagnostic_payload"](probe, aggregate)
    assert first["rejections"][0]["late_split_record_count"] == 0
    probe._split_records_by_session["2024-06-11"] = {
        "private-SID": {"split_factor": "1"}}
    later = namespace["_r268_a2_diagnostic_payload"](probe, aggregate)
    assert later["rejections"][0]["late_split_record_count"] == 1
    assert b"private-SID" not in common._canonical(later)
    assert b"security_id" not in common._canonical(later)
    mismatched = namespace["Probe"]()
    mismatched._split_records_by_session = {
        "2024-06-11": {"private-SID": {"split_factor": "2"}}}
    assert mismatched._holding_drift_replan(
        plan, Decimal(0), {"private-SID": 11}, actual_time) is None
    classified = namespace["_r268_a2_diagnostic_payload"](mismatched, aggregate)
    assert classified["rejections"][0]["classification"] == (
        "split_adjusted_quantity_mismatch")
    assert classified["rejections"][0]["late_split_record_count"] == 0


@pytest.mark.parametrize("valid", [False, True])
def test_a2_full_order_parser_preserves_validity_and_redacted_statistic(valid, tmp_path,
                                                                         monkeypatch):
    plan = _plan(tmp_path, 2)
    payload = _payload(run_valid=valid)
    prior = {"run_valid": valid,
             "aggregates": {"execution": {}}}
    def parse_a1(a1_plan, statistics):
        assert a1_plan.attempt == 1
        assert set(statistics) == set(study.STATISTIC_NAMES)
        return prior
    monkeypatch.setattr(study, "parse_order", parse_a1)
    parsed = a2.parse_result(plan, _stats(payload))
    assert parsed["run_valid"] is valid
    assert parsed["drift_diagnostic"] == payload
    assert "security_id" not in json.dumps(parsed["drift_diagnostic"])


@pytest.mark.parametrize("defect", ["sid", "class", "session", "terminal_session",
                                     "count", "lineage", "validity", "aggregate_count"])
def test_a2_redacted_parser_refuses_unexpected_or_mismatched_evidence(
        defect, tmp_path, monkeypatch):
    plan = _plan(tmp_path, 2)
    payload = _payload()
    prior = {"run_valid": False,
             "aggregates": {"execution": {}}}
    monkeypatch.setattr(study, "parse_order", lambda *_: prior)
    if defect == "sid":
        payload["rejections"][0]["security_id"] = "secret"
    elif defect == "class":
        payload["rejections"][0]["classification"] = "unknown"
    elif defect == "session":
        payload["rejections"][0]["execution_session"] = "2024-6-11"
    elif defect == "terminal_session":
        payload["rejections"][0]["execution_session"] = "2026-01-01"
    elif defect == "count":
        payload["rejections"][0]["rejected_holding_count"] = 3
    elif defect == "lineage":
        payload["a1_projection_sha256"] = "f" * 64
    elif defect == "validity":
        payload["run_valid"] = True
    with pytest.raises(adapter.RelaxedQcSubmissionError):
        a2.parse_result(plan, _stats(payload, raw_skip=0 if defect == "aggregate_count" else None))


def test_a2_valid_result_can_satisfy_baseline_gate_without_repinning_a1(
        tmp_path, monkeypatch):
    plan = _plan(tmp_path, 2)
    result_path = adapter._path(plan, "result")
    result_path.write_text("{}", encoding="ascii")
    row = adapter._candidate(plan)
    terminal = {"candidate_id": "R268", "attempt": 2,
                "project_id": 123, "backtest_id": "backtest", "status": "Completed."}
    launch = {"project_id": 123, "backtest_id": "backtest"}
    parsed = {"run_valid": True, "drift_diagnostic": _payload(run_valid=True)}
    saved = {**terminal, **parsed,
             "manifest_sha256": adapter.FROZEN_EIGHT_R268_A2_MANIFEST_SHA256,
             "projection_sha256": row["projection_sha256"]}
    monkeypatch.setattr(adapter, "_receipt", lambda *_: None)
    monkeypatch.setattr(adapter, "_parse_order", lambda *_: parsed)
    monkeypatch.setattr(adapter.common, "_read", lambda path: (
        launch if path.name.endswith("launch.json") else terminal))
    monkeypatch.setattr(adapter, "_read_artifact", lambda path: (
        saved if path.name.endswith("result.json") else
        {**terminal, "statistics": {name: "{}" for name in row["statistic_names"]}}))
    assert study.require_completed_baseline(plan) is True
    assert adapter._plan_manifest_sha256(dataclasses.replace(plan, attempt=1)) == (
        adapter.FROZEN_EIGHT_UNIVERSE_MANIFEST_SHA256)


@pytest.mark.parametrize("defect", ["none", "read_claim", "raw_skip", "saved_result"])
def test_a2_reauthenticates_invalid_a1_before_any_cloud_call(
        defect, projections, tmp_path, monkeypatch):
    a1 = _plan(tmp_path, 1)
    a2_plan = _plan(tmp_path, 2)
    identity = adapter.preview(a1, projections[0][0])
    row = adapter._candidate(a1)
    launch = {**identity, "project_id": 123,
              "project_name": row["project_name"], "compile_id": "compile",
              "backtest_id": "backtest",
              "backtest_name": row["backtest_name"] + " A1"}
    expected = {"candidate_id": "R268", "attempt": 1,
                "project_id": 123, "backtest_id": "backtest", "status": "Completed."}
    for suffix, value in (("claim", identity), ("launch", launch),
                          ("project", {"candidate_id": "R268", "project_id": 123,
                                       "project_name": row["project_name"]}),
                          ("terminal", expected), ("read-claim", expected)):
        common._write(adapter._path(a1, suffix), value)
    raw = _stats(_payload())
    raw.pop(a2.STATISTIC_NAME)
    aggregate = json.loads(raw[study.STATISTIC_NAMES[1]])
    aggregate["execution"].update(decision_count=261,
                                  submitted_rebalance_count=260,
                                  completed_rebalance_count=260)
    raw[study.STATISTIC_NAMES[1]] = common._canonical(aggregate).decode("ascii")
    parsed = {"run_valid": False, "aggregates": {"execution": {}}}
    adapter._write_artifact(adapter._path(a1, "raw-custom"),
                            {**expected, "statistics": raw})
    saved = {**expected, **parsed,
             "manifest_sha256": adapter.FROZEN_EIGHT_UNIVERSE_MANIFEST_SHA256,
             "projection_sha256": row["projection_sha256"]}
    adapter._write_artifact(adapter._path(a1, "result"), saved)
    monkeypatch.setattr(study, "parse_order", lambda *_: parsed)
    assert study.require_invalid_baseline_a1(a2_plan) is True

    if defect == "none":
        return
    if defect == "read_claim":
        original = common._read
        monkeypatch.setattr(common, "_read", lambda path: (
            {**expected, "status": "Runtime Error"}
            if path.name.endswith("read-claim.json") else original(path)))
    else:
        original = adapter._read_artifact
        def changed(path):
            value = original(path)
            if defect == "raw_skip" and path.name.endswith("raw-custom.json"):
                value["statistics"][study.STATISTIC_NAMES[1]] = (
                    common._canonical({**aggregate, "execution": {
                        **aggregate["execution"],
                        "holding_drift_skipped_rebalance_count": 0}}).decode("ascii"))
            if defect == "saved_result" and path.name.endswith("result.json"):
                value["projection_sha256"] = "f" * 64
            return value
        monkeypatch.setattr(adapter, "_read_artifact", changed)
    calls = []
    class NoCloud:
        def post(self, *args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("cloud was called before A1 authentication")
    monkeypatch.setattr(study, "require_input_readiness", lambda *_: True)
    monkeypatch.setattr(study, "require_completed_baseline", lambda *_: True)
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="R268 A1"):
        adapter.launch(a2_plan, projections[1][0], NoCloud())
    assert calls == []


def test_a2_cli_read_prints_only_rejection_census(monkeypatch, capsys):
    import sys
    monkeypatch.setattr(sys, "argv", ["run_arv2_eight_universe.py", "read", "R268",
                                  "--attempt", "2", "--organization", ORG])
    monkeypatch.setattr(script.credentials, "production_client", lambda: object())
    monkeypatch.setattr(script.common, "_read", lambda *_: {})
    payload = _payload()
    monkeypatch.setattr(adapter, "read_result_once", lambda *_: {
        "drift_diagnostic": payload, "aggregates": {"account": {
            "cumulative_return": "0.42"}}})
    script.main()
    output = json.loads(capsys.readouterr().out)
    assert output == {key: payload[key] for key in (
        "holding_drift_skip_count", "rejections")}
    assert "return" not in json.dumps(output).lower()
