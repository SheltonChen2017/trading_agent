"""Offline proofs for six prospective, same-source physical-order arms."""

import ast
import dataclasses
from datetime import datetime
from decimal import Decimal, localcontext
import hashlib
import json
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_matched_historical_projection as subject
from tests.analyst_revisions_v2 import test_qc_six_universe_tilt_ladder_floor_projection as historical
from tests.analyst_revisions_v2 import test_qc_relaxed_selection_source as fixtures
from tests.analyst_revisions_v2 import test_qc_full_ar_ablation_projection as off_tests

package = historical.package
synthetic_input = off_tests.synthetic_input


@pytest.fixture(scope="module")
def family(package):
    return {(arm, slip): subject.build_matched_historical_projection(package, arm, slip)
            for arm in subject.ARMS for slip in subject.SLIPPAGE_BPS}


def _sources(projection):
    return {item.project_path: item.source_bytes.decode("ascii") for item in projection.source_files}


@pytest.mark.parametrize("arm,slip", ((True, 0), ("unknown", 0), ("ar_off", True),
                                     ("ar_off", Decimal(5)), ("ar_off", -5), ("ar_off", 10)))
def test_invalid_mode_refused_before_input_access(arm, slip):
    with pytest.raises(subject.MatchedHistoricalProjectionError):
        subject.build_matched_historical_projection(object(), arm, slip)


def test_family_has_identical_exact_historical_inputs_and_distinct_sources(family, package):
    before = subject._historical.build_tilt_floor_projection(package, 100)
    assert len({value.projection_sha256 for value, _ in family.values()}) == 6
    assert len({profile["profile_sha256"] for _, profile in family.values()}) == 6
    for (arm, slip), (value, profile) in family.items():
        for key in ("package_id", "package_sha256", "package_lineage_sha256", "activation_manifest_key",
                    "activation_manifest_sha256", "activation_manifest_byte_count"):
            assert getattr(value, key) == getattr(before, key)
        assert value.market_on_open_orders_only and value.backtest_only
        assert not any((value.live_orders, value.paper_orders, value.funded_orders, value.deployment, value.trading))
        assert profile["comparison_arm"] == arm
        assert profile["slippage_bps"] == str(slip)
        assert profile["evaluation_start_session"] == "2021-01-04"
        assert profile["evaluation_end_session"] == "2025-12-31"
        assert profile["decision_count"] == 261
        assert profile["evaluation_session_count"] == 1255
        assert profile["target_gross_exposure"] == "0.98"
        assert profile["modeled_fee_bps_per_side"] == "10"
        assert profile["admission_leverage"] == "2"
        assert profile["maximum_stock_weight_change_fraction"] == ("1.00" if arm == "ar_on100" else "0.00")
        assert len(value.source_files) == 17
        assert value.total_source_byte_count + subject._base.MINIMUM_REVIEW_MARGIN_BYTES <= subject._base.MAXIMUM_TOTAL_SOURCE_BYTES
        for item in value.source_files:
            assert hashlib.sha256(item.source_bytes).hexdigest() == item.content_sha256
            assert item.byte_count == len(item.source_bytes)
            subject._base._audit_source(item.project_path, item.source_bytes)
    assert before == subject._historical.build_tilt_floor_projection(package, 100)


@pytest.mark.parametrize("slip", (0, 5))
@pytest.mark.parametrize("arm", subject.ARMS)
def test_exact_cloud_profile_cost_factory_and_third_statistic(family, arm, slip):
    value, profile = family[arm, slip]
    sources = _sources(value)
    with subject._relaxed._cloud_loader(sources) as (load, _):
        runtime = load(subject._relaxed._TILT_RUNTIME_PATH[:-3])
        assert runtime.require_tilt_profile() == profile
        assert runtime.TILT_META_SCHEMA == subject.META_SCHEMA
        assert runtime.TILT_SUMMARY_SCHEMA == subject.SUMMARY_SCHEMA
        assert runtime.expected_tilt_custom_statistic_names() == tuple(sorted((
            "ARV2_SIX_GATE_ORDER_META", "ARV2_SIX_GATE_ORDER_AGGREGATES", "ARV2_SIX_GATE_ORDER_DIAGNOSTICS")))
        assert runtime._bridge.MAXIMUM_STATISTIC_BYTES == 8192
    tree = ast.parse(sources["main.py"])
    factories = [node.value for node in ast.walk(tree)
                 if isinstance(node, ast.keyword) and node.arg == "slippage_model_factory"]
    assert len(factories) == 1
    factory = eval(compile(ast.Expression(factories[0]), "factory", "eval"), {
        "NullSlippageModel": lambda: ("null",), "ConstantSlippageModel": lambda value: ("constant", value)})
    assert factory() == (("null",) if slip == 0 else ("constant", 0.0005))
    install = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
               and isinstance(node.func, ast.Name) and node.func.id == "install_matched_diagnostics"]
    assert len(install) == 1 and [item.value for item in install[0].args[1:]] == [arm, slip]


@pytest.mark.parametrize("arm", subject.ARMS)
def test_entry_count_weight_and_basket_are_economically_distinct(family, arm):
    with subject._relaxed._cloud_loader(_sources(family[arm, 0][0])) as (load, _):
        tilt = load("accepted_risk_six_universe_order_tilt_targets")
        gate = tilt._gate
        snapshots = fixtures._snapshots(gate, {name: fixtures._rows(gate, name, positives=2)
                                              for name in gate.UNIVERSE_IDS})
        construction = gate.build_six_universe_construction(snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
        weights = tilt.tilt_matched_weights(construction, snapshots)
        if arm == "ar_on100":
            assert all(not sleeve.matched_security_ids for sleeve in construction.sleeves if sleeve.universe_id != "XLE")
            assert any(item.asset_kind == "stock" for item in weights)
        elif arm == "ar_off":
            assert all(len(sleeve.matched_security_ids) == 10 for sleeve in construction.sleeves)
            assert weights == construction.matched_weights
        else:
            assert weights == construction.etf_basket_weights
            assert len(weights) == 6 and all(item.asset_kind == "etf" for item in weights)
            assert tilt._matched._role_weights(construction, tilt._matched.ROLE_MATCHED) == weights
            for sleeve in construction.sleeves:
                diagnostic = tilt._matched._sleeve_diagnostic(sleeve, tilt._matched.ROLE_MATCHED, construction.profile)
                assert not diagnostic.selected_security_ids
                assert diagnostic.post_cap_stock_target_count == 0
                assert diagnostic.etf_target_weight == sleeve.budget
                assert diagnostic.selection_status == "SIX_ETF_BASKET"
        with localcontext() as context:
            context.prec = 96
            assert sum((item.weight for item in weights), Decimal(0)) == Decimal("0.98")


def test_on100_actually_transfers_weights_while_off_does_not(family):
    for arm in ("ar_off", "ar_on100"):
        with subject._relaxed._cloud_loader(_sources(family[arm, 0][0])) as (load, _):
            tilt = load("accepted_risk_six_universe_order_tilt_targets")
            snapshots = fixtures._snapshots(tilt._gate)
            construction = tilt._gate.build_six_universe_construction(snapshots, tilt._gate.TOP10_CAP90_EXPLORATORY_PROFILE)
            assert (tilt.tilt_matched_weights(construction, snapshots) == construction.matched_weights) == (arm == "ar_off")


@pytest.mark.parametrize("arm", ("ar_off", "six_etf_basket"))
def test_actual_projected_builder_off_and_basket_ignore_score_changes(family, synthetic_input, arm):
    with subject._relaxed._cloud_loader(_sources(family[arm, 0][0])) as (load, _):
        tilt = load("accepted_risk_six_universe_order_tilt_targets")
        base = tilt._score._r055
        record = {field.name: getattr(synthetic_input, field.name)
                  for field in dataclasses.fields(synthetic_input)}
        record["memberships"] = tuple(base.SecurityMembership(**dataclasses.asdict(row))
                                      for row in synthetic_input.memberships)
        record["contributions"] = tuple(base.RatingContribution(**dataclasses.asdict(row))
                                        for row in synthetic_input.contributions)
        value = base.PreliminaryRatingInput(**record)
        session = tilt._evaluation.decision_sessions_for_input(value)[0]
        ids = tuple(row.security_id for row in value.memberships)
        snapshots = tuple(tilt._gate.UniverseSnapshot(spec.universe_id, spec.etf_ticker, "etf-" + spec.universe_id,
            tuple(tilt._gate.UniverseConstituent(Decimal("0.05"), security_id, security_id,
                Decimal(20 - index), None) for index, security_id in enumerate(ids)))
            for spec in tilt._gate.UNIVERSE_SPECS)
        pit = tilt._evaluation.PitDecisionSnapshot(session=session, universes=snapshots)
        records = []
        for positive in (False, True):
            builder = tilt.MatchedRevisionTiltTargetBuilder(value)
            original = builder._capture._scorer.score_session
            def controlled(current):
                result = original(current)
                return dataclasses.replace(result, primary_view_firm_specific_scores={
                    security_id: Decimal(index + 1) if positive else Decimal(-index - 1)
                    for index, security_id in enumerate(ids)})
            builder._capture._scorer.score_session = controlled
            decision = builder.build(session, pit)
            assert builder._capture.call_count == 1 and builder._capture.latest is None
            if arm == "six_etf_basket":
                assert len(decision.target_weights) == 6
                assert all(item.asset_kind == "etf" for item in decision.target_weights)
                assert all(item.selection_status == "SIX_ETF_BASKET" for item in decision.sleeves)
            else:
                assert all(len(item.selected_security_ids) == 10 for item in decision.sleeves)
            records.append(decision.to_record())
        assert records[0] == records[1]


def test_third_statistic_bytes_are_authenticated_by_emitted_meta(family):
    with subject._relaxed._cloud_loader(_sources(family["ar_off", 0][0])) as (load, _):
        bridge = load(subject._relaxed._BRIDGE_NAME)
        emitted = {}
        diagnostic_text = '{"synthetic":true}'
        aggregate = {"schema": subject.SUMMARY_SCHEMA}
        driver = SimpleNamespace(
            _require_initialized=lambda: None,
            _algorithm=SimpleNamespace(live_mode=False, time=datetime(2026, 1, 1),
                                       set_summary_statistic=lambda name, text: emitted.setdefault(name, text)),
            _aggregate=lambda: aggregate, _role="synthetic", _profile={"profile_id": "p", "profile_sha256": "a" * 64},
            _package=SimpleNamespace(package_id="p", package_sha256="b" * 64, activation_manifest_sha256="c" * 64),
            _resolution=SimpleNamespace(resolution_id="r", resolution_sha256="d" * 64),
            _matched_diagnostics_statistic=diagnostic_text,
            _bridge_expected_statistic_names=lambda: tuple(sorted((bridge.META_STATISTIC_NAME,
                bridge.AGGREGATES_STATISTIC_NAME, "ARV2_SIX_GATE_ORDER_DIAGNOSTICS"))))
        bridge.BridgeAdmissionMixin.on_end_of_algorithm(driver)
        assert emitted["ARV2_SIX_GATE_ORDER_DIAGNOSTICS"] == diagnostic_text
        meta = json.loads(emitted[bridge.META_STATISTIC_NAME])
        assert meta["matched_diagnostics_sha256"] == hashlib.sha256(diagnostic_text.encode("ascii")).hexdigest()
        assert meta["result_transport"] == "three_bounded_custom_summary_statistics"
        assert driver._completed and driver._emitted
