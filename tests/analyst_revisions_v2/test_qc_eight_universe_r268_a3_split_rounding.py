"""R268 A3 split arithmetic, profile lineage, and predecessor admission."""

import copy
import dataclasses
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import eight_universe_r268_a2_diagnostic as a2
from research.analyst_revisions_v2_qc import eight_universe_r268_a3_split_rounding as a3
from research.analyst_revisions_v2_qc import eight_universe_split_truncation_projection as split
from research.analyst_revisions_v2_qc import eight_universe_study as study
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_relaxed_qc_projection as loader
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from research.analyst_revisions_v2_qc import six_universe_settlement_submission as common
from scripts import run_arv2_eight_universe as script
from tests.analyst_revisions_v2.test_qc_eight_universe_r268_a2_diagnostic import _stats


ORG = "a" * 32
_RUNTIME = "accepted_risk_six_universe_order_qc_runtime.py"


@pytest.fixture(scope="module")
def projections():
    inputs = script.package()
    return (script.projected("R268", inputs, attempt=1),
            script.projected("R268", inputs, attempt=2),
            script.projected("R268", inputs, attempt=3))


def _plan(tmp_path, attempt):
    return adapter.build_plan("R268", ORG, tmp_path / "control", attempt,
                              family=study.FAMILY)


def test_a3_has_separate_source_profile_pin_and_same_project(projections, tmp_path):
    (a1_source, a1_profile), (a2_source, a2_profile), (a3_source, a3_profile) = projections
    identities = [adapter.preview(_plan(tmp_path, attempt), source)
                  for attempt, source in enumerate((a1_source, a2_source, a3_source), 1)]
    assert [identity["manifest_sha256"] for identity in identities] == [
        adapter.FROZEN_EIGHT_UNIVERSE_MANIFEST_SHA256,
        adapter.FROZEN_EIGHT_R268_A2_MANIFEST_SHA256,
        adapter.FROZEN_EIGHT_R268_A3_MANIFEST_SHA256,
    ]
    assert len({identity["projection_sha256"] for identity in identities}) == 3
    assert a1_profile == a2_profile
    assert a3_profile["profile_sha256"] != a1_profile["profile_sha256"]
    assert a3_profile["matched_baseline_profile_sha256"] != (
        a1_profile["matched_baseline_profile_sha256"])
    assert a3_profile["overnight_holding_drift_rule"] == split._RULE
    allowed = {"schema", "profile_id", "profile_sha256",
               "overnight_holding_drift_rule", "cap90_predecessor_profile_sha256",
               "matched_baseline_profile_sha256"}
    assert {key: value for key, value in a3_profile.items() if key not in allowed} == {
        key: value for key, value in a1_profile.items() if key not in allowed}
    a1_files = {item.project_path: item.source_bytes for item in a1_source.source_files}
    a3_files = {item.project_path: item.source_bytes for item in a3_source.source_files}
    assert {path for path in a1_files if a1_files[path] != a3_files[path]} == {
        split._RUNTIME, split._BRIDGE, split._TILT}
    assert len(a2_source.source_files) == len(a3_source.source_files) == 17
    assert adapter._candidate(_plan(tmp_path, 1))["project_name"] == (
        adapter._candidate(_plan(tmp_path, 3))["project_name"])
    raw = adapter.EIGHT_R268_A3_MANIFEST_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == adapter.FROZEN_EIGHT_R268_A3_MANIFEST_SHA256
    assert raw == common._canonical(a3.freeze_manifest(script.package())) + b"\n"


def _replan(projection, expected, observed, factors, *, cash="100", session="2021-06-29"):
    sources = {item.project_path: item.source_bytes.decode("ascii")
               for item in projection.source_files}
    with loader._cloud_loader(sources) as (load, _):
        runtime = load(_RUNTIME[:-3])
        driver = object.__new__(runtime.AcceptedRiskSixUniverseOrderQcDriver)
        symbol = SimpleNamespace(id="SID-A")
        driver._ensure_security = lambda _security_id: (
            symbol, SimpleNamespace(symbol=symbol, price=Decimal("50")))
        driver._split_records_by_session = {session: {
            security_id: {"security_id_sha256": hashlib.sha256(
                security_id.encode("ascii")).hexdigest(),
                "split_factor": factor, "reference_price": "50"}
            for security_id, factor in factors.items()}}
        plan = SimpleNamespace(starting_quantities=tuple(sorted(expected.items())),
                               target_weights=tuple((security_id, Decimal("0.49"))
                                                    for security_id in sorted(expected)),
                               plan_sha256="a" * 64)
        return driver._holding_drift_replan(
            plan, Decimal(cash), observed,
            datetime.fromisoformat(session + "T09:20:00"))


def test_generated_runtime_accepts_only_recorded_factor_integer_truncation(projections):
    a1, a3 = projections[0][0], projections[2][0]
    factor = "0.0666667"  # Recorded LEAN factor; 3 / factor truncates to 44.
    assert _replan(a1, {"A": 3}, {"A": 44}, {"A": factor}) is None
    accepted = _replan(a3, {"A": 3}, {"A": 44}, {"A": factor})
    assert accepted["reference_prices"] == {"A": Decimal("50")}
    assert len(accepted["receipt_sha256"]) == 64
    assert _replan(a3, {"A": 3}, {"A": 44}, {"A": factor}, cash="101")[
        "receipt_sha256"] != accepted["receipt_sha256"]
    for wrong in (43, 45):
        assert _replan(a3, {"A": 3}, {"A": wrong}, {"A": factor}) is None
    assert _replan(a3, {"A": 3}, {"A": 44}, {}) is None
    assert _replan(a3, {"A": 10}, {"A": 20}, {"A": "0.5"}) is not None
    assert _replan(a3, {"A": -3}, {"A": -44}, {"A": factor}) is None
    assert _replan(a3, {"A": 3, "B": 10}, {"A": 44, "B": 21},
                   {"A": factor, "B": "0.5"}) is None
    assert _replan(a3, {"A": 3, "B": 10}, {"A": 44, "B": 20},
                   {"A": factor}) is None


def test_generic_overlay_accepts_an_unlaunched_ar_on_projection():
    original, profile = a3.renderer.build_eight_universe_projection(
        script.package(), study.CANDIDATE_ARMS["R269"], "R269")
    corrected, successor = split.correct_projection(
        original, profile,
        schema="arv2-eight-r269-split-truncation-projection-v1",
        projection_id_prefix="arv2-eight-r269-split-truncation-projection-")
    assert successor["overnight_holding_drift_rule"] == split._RULE
    assert successor["maximum_stock_weight_change_fraction"] == (
        profile["maximum_stock_weight_change_fraction"])
    assert successor["maximum_stock_weight_change_fraction"] == "0.80"
    assert successor["modeled_fee_bps_per_side"] == profile["modeled_fee_bps_per_side"]
    assert successor["target_gross_exposure"] == profile["target_gross_exposure"]
    assert corrected.profile_sha256 != original.profile_sha256
    assert _replan(corrected, {"A": 3}, {"A": 44}, {"A": "0.0666667"}) is not None
    assert adapter._eight_universe_manifest()["candidates"][1]["projection_sha256"] == (
        original.projection_sha256)


@pytest.mark.parametrize("candidate", ["R276"])
def test_valid_a3_cannot_unlock_original_nonbaseline_source(
        candidate, tmp_path, monkeypatch):
    plan = adapter.build_plan(candidate, ORG, tmp_path / "control",
                              family=study.FAMILY)
    assert adapter._plan_manifest_sha256(plan) == (
        adapter.FROZEN_EIGHT_UNIVERSE_MANIFEST_SHA256)
    monkeypatch.setattr(adapter, "preview", lambda *_: {})
    monkeypatch.setattr(study, "require_input_readiness", lambda *_: True)
    # This represents a fully authenticated, valid R268 A3 result.
    monkeypatch.setattr(study, "require_completed_baseline", lambda *_: True)
    calls = []
    class NoCloud:
        def post(self, *args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("original split policy reached cloud")
    with pytest.raises(adapter.RelaxedQcSubmissionError,
                       match="prospective corrected source freeze"):
        adapter.launch(plan, object(), NoCloud())
    assert calls == []
    assert not adapter._path(plan, "claim").exists()


@pytest.mark.parametrize("candidate", ["R269", "R275"])
def test_original_ar_on_source_cannot_preview_as_corrected(candidate, tmp_path):
    plan = adapter.build_plan(candidate, ORG, tmp_path / "control",
                              family=study.FAMILY)
    assert adapter._plan_manifest_sha256(plan) == (
        adapter.FROZEN_EIGHT_AR_ON_SPLIT_MANIFEST_SHA256)
    original, _ = a3.renderer.build_eight_universe_projection(
        script.package(), study.CANDIDATE_ARMS[candidate], candidate)
    with pytest.raises(adapter.RelaxedQcSubmissionError,
                       match="projection or profile changed"):
        adapter.preview(plan, original)


@pytest.mark.parametrize("defect", ["diagnosis", "saved", "read_claim", "project"])
def test_a3_refuses_changed_a2_evidence_before_cloud(
        defect, projections, tmp_path, monkeypatch):
    a2_plan = _plan(tmp_path, 2)
    a3_plan = _plan(tmp_path, 3)
    identity = adapter.preview(a2_plan, projections[1][0])
    row = adapter._candidate(a2_plan)
    launch = {**identity, "project_id": 123,
              "project_name": row["project_name"], "compile_id": "compile",
              "backtest_id": "backtest", "backtest_name": row["backtest_name"] + " A2"}
    expected = {"candidate_id": "R268", "attempt": 2,
                "project_id": 123, "backtest_id": "backtest", "status": "Completed."}
    for suffix, value in (("claim", identity), ("launch", launch),
                          ("project", {"candidate_id": "R268", "project_id": 123,
                                       "project_name": row["project_name"]}),
                          ("terminal", expected), ("read-claim", expected)):
        common._write(adapter._path(a2_plan, suffix), value)
    payload = {
        "schema": a2.DIAGNOSTIC_SCHEMA, "candidate_id": "R268", "attempt": 2,
        "a1_manifest_sha256": adapter.FROZEN_EIGHT_UNIVERSE_MANIFEST_SHA256,
        "a1_projection_sha256": a2._a1_row()["projection_sha256"],
        "profile_sha256": a2._a1_row()["profile_sha256"],
        "run_valid": False, "holding_drift_skip_count": 1,
        "rejections": [{"execution_session": "2021-06-29",
                        "classification": "split_adjusted_quantity_mismatch",
                        "changed_holding_count": 1, "rejected_holding_count": 1,
                        "late_split_record_count": 0}],
    }
    raw = _stats(payload)
    aggregate = json.loads(raw[study.STATISTIC_NAMES[1]])
    aggregate["execution"].update(decision_count=261,
                                  holding_drift_skipped_rebalance_count=1,
                                  submitted_rebalance_count=260,
                                  completed_rebalance_count=260)
    raw[study.STATISTIC_NAMES[1]] = common._canonical(aggregate).decode("ascii")
    parsed_base = {"run_valid": False, "aggregates": {"execution": {}}}
    monkeypatch.setattr(study, "parse_order", lambda *_: parsed_base)
    parsed = a2.parse_result(a2_plan, raw)
    adapter._write_artifact(adapter._path(a2_plan, "raw-custom"),
                            {**expected, "statistics": raw})
    adapter._write_artifact(adapter._path(a2_plan, "result"), {
        **expected, **parsed,
        "manifest_sha256": adapter.FROZEN_EIGHT_R268_A2_MANIFEST_SHA256,
        "projection_sha256": row["projection_sha256"]})
    monkeypatch.setattr(study, "require_invalid_baseline_a1", lambda *_: True)
    assert study.require_invalid_baseline_a2(a3_plan) is True
    if defect in {"read_claim", "project"}:
        original = common._read
        suffix = "read-claim.json" if defect == "read_claim" else "project.json"
        monkeypatch.setattr(common, "_read", lambda path: (
            {"status": "Runtime Error"} if path.name.endswith(suffix)
            else original(path)))
    else:
        original = adapter._read_artifact
        def altered(path):
            value = original(path)
            if defect == "diagnosis" and path.name.endswith("raw-custom.json"):
                value["statistics"][a2.STATISTIC_NAME] = common._canonical({
                    **payload, "rejections": [{**payload["rejections"][0],
                        "classification": "missing_same_session_split_record"}]}
                ).decode("ascii")
            if defect == "saved" and path.name.endswith("result.json"):
                value["projection_sha256"] = "f" * 64
            return value
        monkeypatch.setattr(adapter, "_read_artifact", altered)
    monkeypatch.setattr(adapter, "preview", lambda *_: {})
    monkeypatch.setattr(study, "require_input_readiness", lambda *_: True)
    monkeypatch.setattr(study, "require_completed_baseline", lambda *_: True)
    calls = []
    class NoCloud:
        def post(self, *args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("cloud call preceded A2 authentication")
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="R268 A2"):
        adapter.launch(a3_plan, object(), NoCloud())
    assert calls == []


def test_a3_manifest_refuses_old_strategy_or_profile_identity():
    value = copy.deepcopy(adapter._eight_r268_a3_manifest())
    for key, replacement in (("profile_sha256", a3._a1_row()["profile_sha256"]),
                             ("profile_id", "arbitrary-lean-int-split-truncation-v1"),
                             ("tilt_fraction", "1.00"),
                             ("matched_baseline_profile_sha256", "f" * 64)):
        changed = copy.deepcopy(value)
        changed["candidates"][0][key] = replacement
        with pytest.raises(adapter.RelaxedQcSubmissionError):
            a3.validate_manifest(changed)
