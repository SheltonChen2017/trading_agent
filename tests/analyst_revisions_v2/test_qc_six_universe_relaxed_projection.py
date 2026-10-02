"""Full generated closure and profile chain for prospective relaxed selection."""

from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import sys
import types

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_relaxed_qc_projection as subject
from tests.analyst_revisions_v2 import test_qc_recent_coverage_projection as inputs
from tests.analyst_revisions_v2 import test_qc_relaxed_selection_source as fixtures

prior_package = inputs.prior_package
actual_package = inputs.actual_package
POLICY = fixtures.POLICY


@pytest.fixture(scope="module")
def projections(prior_package, actual_package):
    return {percent: subject.build_relaxed_order_projection(prior_package, actual_package, percent, POLICY)
            for percent in subject.TILT_PERCENTS}


def _sources(projection):
    return {item.project_path: item.source_bytes.decode("ascii") for item in projection.source_files}


@pytest.mark.parametrize("percent", subject.TILT_PERCENTS)
def test_all_ten_real_package_projections_have_distinct_authenticated_profiles(projections, percent):
    projection, profile = projections[percent]
    sources = _sources(projection)
    assert len(sources) == 16
    assert projection.total_source_byte_count + 32768 <= 448 * 1024
    assert max(item.byte_count for item in projection.source_files) <= 64000
    assert profile["maximum_stock_weight_change_fraction"] == f"{percent // 100}.{percent % 100:02d}"
    assert profile["target_gross_exposure"] == "0.98"
    assert profile["settled_cash_nonnegative_required"] is True
    assert profile["end_day_gross_exposure_maximum"] == "1"
    assert profile["role"] == f"matched_revision_tilt{percent}_relaxed_recent"
    with subject._cloud_loader(sources) as (load, modules):
        for name in sorted(modules):
            load(name)
        gate = modules["accepted_risk_six_universe_gate"]
        evaluation = modules["accepted_risk_six_universe_gate_evaluator"]
        bridge = modules["accepted_risk_six_universe_order_bridge_qc_runtime"]
        runtime = modules["accepted_risk_six_universe_order_tilt_qc_runtime"]
        targets = modules["accepted_risk_six_universe_order_tilt_targets"]
        assert gate.RELAXED_COVERAGE_POLICY == POLICY
        assert profile == runtime.require_tilt_profile()
        assert profile["matched_baseline_profile_sha256"] == bridge.require_bridge_profile("matched")["profile_sha256"]
        assert profile["gate_profile_sha256"] == gate.TOP10_CAP90_EXPLORATORY_PROFILE.profile_sha256
        assert profile["evaluation_profile_sha256"] == evaluation.TOP10_CAP90_EXPLORATORY_PROFILE.profile_sha256
        assert targets.MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION == Decimal(percent) / 100
        assert "relaxed" in targets.DECISION_TARGET_SCHEMA
        assert "relaxed" in targets.TARGET_PATH_SCHEMA
        base = modules["accepted_risk_six_universe_order_qc_runtime"]
        driver = object.__new__(base.AcceptedRiskSixUniverseOrderQcDriver)
        driver._sleeve_diagnostics = base._empty_sleeve_diagnostics()
        for record in driver._sleeve_diagnostics.values():
            record["decision_count"] = 61
        assert driver._frozen_sleeve_diagnostics()["schema"] == "arv2-six-universe-order-sleeve-summary-table-v1"
        assert runtime.TILT_SUMMARY_SCHEMA == subject.SUMMARY_SCHEMAS[percent]
        assert runtime.TILT_META_SCHEMA == subject.META_SCHEMA
    for item in projection.source_files:
        assert hashlib.sha256(item.source_bytes).hexdigest() == item.content_sha256
        compile("from AlgorithmImports import *\n" + item.source_bytes.decode("ascii"), item.project_path, "exec")
    assert len({value[0].projection_sha256 for value in projections.values()}) == 10
    assert len({value[1]["profile_sha256"] for value in projections.values()}) == 10


@pytest.mark.parametrize("percent", (20, 100, 200))
def test_real_generated_tilt_conserves_partial_etf_fallback_and_xle_entry(projections, percent):
    projection, _ = projections[percent]
    with subject._cloud_loader(_sources(projection)) as (load, _):
        tilt = load("accepted_risk_six_universe_order_tilt_targets")
        gate = tilt._gate
        snapshots = fixtures._snapshots(gate, {
            "XLE": fixtures._rows(gate, "XLE", positives=0),
            "QQQ": fixtures._rows(gate, "QQQ", known=10),
        })
        construction = gate.build_six_universe_construction(snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
        xle = fixtures._sleeve(construction, "XLE")
        qqq = fixtures._sleeve(construction, "QQQ")
        assert xle.positive_score_count == 0 and len(xle.matched_security_ids) == 10
        assert qqq.coverage.mapping_ratio == Decimal("0.5")
        assert qqq.matched_etf_fallback_weight > 0
        result = tilt.tilt_matched_weights(construction, snapshots)
        before = {item.security_id: item.weight for item in construction.matched_weights if item.asset_kind == "etf"}
        after = {item.security_id: item.weight for item in result if item.asset_kind == "etf"}
        assert after == before
        with localcontext() as context:
            context.prec = 96
            assert sum((item.weight for item in result), Decimal(0)) == Decimal("0.98")
        assert all(0 < item.weight <= Decimal("0.098") for item in result if item.asset_kind == "stock")
        assert {item.security_id for item in result} == {item.security_id for item in construction.matched_weights}


def test_policy_changes_recompute_every_load_bearing_profile_hash(prior_package, actual_package, projections):
    changed = (POLICY[0], ("SOXX", "0.6", "0.6", "0.5", 5), POLICY[2])
    projection, profile = subject.build_relaxed_order_projection(prior_package, actual_package, 100, changed)
    original, original_profile = projections[100]
    for key in ("gate_profile_sha256", "evaluation_profile_sha256", "cap90_predecessor_profile_sha256", "matched_baseline_profile_sha256", "profile_sha256"):
        assert profile[key] != original_profile[key]
    assert projection.projection_sha256 != original.projection_sha256


@pytest.mark.parametrize("failure", (False, True))
def test_cloud_loader_restores_existing_and_absent_modules(projections, failure):
    sources = _sources(projections[20][0])
    names = {path[:-3] for path in sources if path != "main.py"}
    original = {name: (name in sys.modules, sys.modules.get(name)) for name in names}
    try:
        with subject._cloud_loader(sources) as (load, _):
            load("accepted_risk_six_universe_gate")
            if failure:
                raise RuntimeError("synthetic interrupted profile evaluation")
    except RuntimeError:
        assert failure
    assert {name: (name in sys.modules, sys.modules.get(name)) for name in names} == original


def test_missing_dependency_cannot_use_host_fallback(projections, monkeypatch):
    sources = _sources(projections[20][0])
    sources.pop("accepted_risk_order_level_input_runtime.py")
    monkeypatch.setitem(sys.modules, "accepted_risk_order_level_input_runtime", types.ModuleType("cached-host-copy"))
    with subject._cloud_loader(sources) as (load, _):
        with pytest.raises(subject.RelaxedOrderProjectionError, match="host fallback"):
            load("accepted_risk_six_universe_order_qc_runtime")


def test_stale_matched_profile_literal_refuses_before_outcomes(projections):
    projection, profile = projections[20]
    sources = _sources(projection)
    path = "accepted_risk_six_universe_order_tilt_qc_runtime.py"
    sources[path] = sources[path].replace(profile["matched_baseline_profile_sha256"], "0" * 64)
    with subject._cloud_loader(sources) as (load, _):
        runtime = load(path[:-3])
        with pytest.raises(runtime.AcceptedRiskSixUniverseOrderTiltQcRuntimeError, match="matched profile changed"):
            runtime.require_tilt_profile()


@pytest.mark.parametrize("percent", (0, 10, 21, 220, True, "20"))
def test_unsupported_strength_refuses_before_package_loading(percent):
    with pytest.raises(subject.RelaxedOrderProjectionError, match="20 through 200"):
        subject.build_relaxed_order_projection(object(), object(), percent, POLICY)


@pytest.fixture
def synthetic_cached_order_transport(projections):
    """Transport proof only: this rewritten fixture is NOT outcome authority.

    The retained R208 receipt has bounded account/count data, not the complete
    producer payload. Restore only synthetic legacy fixture headers/path fields;
    never create a launch, result-read claim, or a prospective outcome receipt.
    """
    from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
    from tests.analyst_revisions_v2 import test_qc_six_universe_settlement_submission as legacy

    path = Path(__file__).resolve().parents[2] / (
        "artifacts/analyst_revisions_v2/six_cap90_qc_control_20260923/"
        "R208-A1-authorized-aggregate.json"
    )
    if not path.is_file():
        pytest.skip("Optional local bounded R208 cache is unavailable; no cloud read permitted")
    cached = json.loads(path.read_bytes())
    aggregate, _ = legacy._aggregate("R195")
    retained = json.loads(adapter.common._canonical(cached["aggregates"]))
    for key, value in retained.items():
        if key in {"execution", "engine_forced_delisting", "sleeve_diagnostics"}:
            aggregate[key].update(value)
        else:
            aggregate[key] = value
    aggregate["execution"]["decision_count"] = retained["sleeve_diagnostics"]["rows"][0][2]
    projection, profile = projections[20]
    aggregate.update(
        schema=subject.SUMMARY_SCHEMAS[20], role=profile["role"],
        profile_id=profile["profile_id"], profile_sha256=profile["profile_sha256"],
        maximum_stock_weight_change_fraction=profile["maximum_stock_weight_change_fraction"],
        matched_baseline_profile_sha256=profile["matched_baseline_profile_sha256"],
    )
    # Exercise the actual new producer status, rather than accepting only legacy
    # categories. Counts remain a complete 366-sleeve/61-decision census.
    new_status = "PARTIAL_STOCK_EXPOSURE_WITH_ETF_FALLBACK"
    qqq = aggregate["sleeve_diagnostics"]["rows"][1]
    count = qqq[11].pop("COVERAGE_FALLBACK")
    qqq[11][new_status] = count
    aggregate["fallback_counts"]["COVERAGE_FALLBACK"] -= count
    aggregate["fallback_counts"][new_status] = count
    row = {
        "role": profile["role"], "summary_schema": subject.SUMMARY_SCHEMAS[20],
        "profile_id": profile["profile_id"], "profile_sha256": profile["profile_sha256"],
        "tilt_fraction": profile["maximum_stock_weight_change_fraction"],
        "matched_baseline_profile_sha256": profile["matched_baseline_profile_sha256"],
        "statistic_names": ["ARV2_SIX_GATE_ORDER_META", "ARV2_SIX_GATE_ORDER_AGGREGATES"],
        "meta_schema": subject.META_SCHEMA,
    }
    meta = dict(cached["meta"])
    meta.update(schema=row["meta_schema"], role=profile["role"],
        profile_id=profile["profile_id"], profile_sha256=profile["profile_sha256"],
        aggregate_schema=row["summary_schema"], package_sha256=projection.package_sha256,
        activation_manifest_sha256=projection.activation_manifest_sha256)
    family = {"package_sha256": projection.package_sha256,
        "activation_manifest_sha256": projection.activation_manifest_sha256}
    return adapter, aggregate, row, meta, family


@pytest.mark.parametrize("defect", (None, "aggregate_profile", "meta_profile", "raw_digest", "new_status"))
def test_generated_profile_roundtrips_cached_bounded_transport_not_outcome_authority(
        synthetic_cached_order_transport, monkeypatch, defect):
    adapter, aggregate, row, meta, family = synthetic_cached_order_transport
    if defect == "aggregate_profile":
        aggregate["profile_sha256"] = "0" * 64
    elif defect == "meta_profile":
        meta["profile_sha256"] = "0" * 64
    elif defect == "new_status":
        counts = aggregate["sleeve_diagnostics"]["rows"][1][11]
        counts["UNREGISTERED_PARTIAL_STOCK_STATUS"] = counts.pop(
            "PARTIAL_STOCK_EXPOSURE_WITH_ETF_FALLBACK")
    raw = adapter.common._canonical(aggregate).decode("ascii")
    # Use the stored text's raw ASCII digest, not the double-encoded string hash.
    meta["aggregate_sha256"] = (
        hashlib.sha256(adapter.common._canonical(raw)).hexdigest() if defect == "raw_digest"
        else hashlib.sha256(raw.encode("ascii")).hexdigest()
    )
    statistics = {"ARV2_SIX_GATE_ORDER_META": adapter.common._canonical(meta).decode("ascii"),
        "ARV2_SIX_GATE_ORDER_AGGREGATES": raw}
    monkeypatch.setattr(adapter, "_candidate", lambda plan: row)
    monkeypatch.setattr(adapter, "_manifest", lambda: family)
    if defect:
        message = ("named state" if defect == "new_status" else
            "aggregate identity" if defect == "aggregate_profile" else "metadata")
        with pytest.raises(adapter.RelaxedQcSubmissionError, match=message):
            adapter._parse_order(object(), statistics)
    else:
        result = adapter._parse_order(object(), statistics)
        assert result["run_valid"] is True
        assert result["meta"]["profile_sha256"] == row["profile_sha256"]
        assert result["aggregates"]["profile_sha256"] == row["profile_sha256"]
        assert result["aggregates"]["account"] == aggregate["account"]
        assert result["aggregates"]["sleeve_diagnostics"]["rows"][1][11] == {
            "PARTIAL_STOCK_EXPOSURE_WITH_ETF_FALLBACK": 61}
        assert set(aggregate) == (adapter.cap._AGGREGATE_FIELDS |
            adapter.common._SETTLEMENT_FIELDS | adapter.common._TILT_FIELDS)
