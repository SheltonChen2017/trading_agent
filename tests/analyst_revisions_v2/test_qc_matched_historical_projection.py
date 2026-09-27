"""Offline proofs for six prospective, same-source physical-order arms."""

import ast
import dataclasses
from datetime import datetime
from decimal import Decimal, localcontext
import hashlib
import json
from types import SimpleNamespace
from pathlib import Path

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


def _reference_driver(base, available, missing_count=3):
    requested = tuple("security-" + str(index).zfill(3) for index in range(missing_count))
    symbols = {security_id: SimpleNamespace(id="SID-" + security_id) for security_id in requested}
    calls = []

    class _Security:
        def __init__(self, delisted):
            self.is_delisted = delisted

        @property
        def price(self):
            pytest.fail("missing history must never read a stale security price")

    securities = {security_id: _Security(index == 0) for index, security_id in enumerate(requested)}

    class _Batch:
        time = datetime(2022, 10, 3, 16)

        def items(self):
            return tuple((symbols[security_id], SimpleNamespace(
                symbol=symbols[security_id], time=self.time, close=Decimal("123.45")))
                for security_id in available)

    class _History:
        def __getitem__(self, _trade_bar_type):
            def read(*args, **kwargs):
                calls.append((args, kwargs))
                return (_Batch(),) if available else ()
            return read

    driver = object.__new__(base.AcceptedRiskSixUniverseOrderQcDriver)
    driver._algorithm = SimpleNamespace(history=_History())
    driver._trade_bar_type = object()
    driver._daily_resolution = object()
    driver._raw_normalization = object()
    driver._reference_history_call_count = 0
    driver._ensure_security = lambda security_id: (symbols[security_id], securities[security_id])
    return driver, requested, calls


@pytest.mark.parametrize("arm,slip", tuple((arm, slip) for arm in subject.ARMS for slip in subject.SLIPPAGE_BPS))
def test_projected_missing_reference_refuses_with_truthful_bounded_context(family, arm, slip):
    with subject._relaxed._cloud_loader(_sources(family[arm, slip][0])) as (load, _):
        base = load("accepted_risk_six_universe_order_qc_runtime")
        driver, ids, calls = _reference_driver(base, ())
        with pytest.raises(base.AcceptedRiskSixUniverseOrderQcRuntimeError,
                           match="no stale-price fallback is permitted; context=") as caught:
            driver._reference_prices("2022-10-03", ids,
                target_security_ids=(ids[0], ids[2]), holding_quantities={ids[1]: 7, ids[2]: 9})
        text = str(caught.value).split("; context=", 1)[1]
        value = json.loads(text)
        assert len(text.encode("ascii")) <= 8192
        assert text == base._canonical(value).decode("ascii")
        assert value["session"] == "2022-10-03"
        assert (value["requested_count"], value["received_count"], value["missing_count"]) == (3, 0, 3)
        assert value["omitted_missing_count"] == 0
        hashes = [hashlib.sha256(security_id.encode("utf-8")).hexdigest() for security_id in ids]
        assert value["missing_security_id_path_sha256"] == base._sha(hashes)
        assert value["missing"] == [
            {"security_id_sha256": hashes[0], "role": "target_only", "holding_quantity": 0, "is_delisted": True},
            {"security_id_sha256": hashes[1], "role": "held_only", "holding_quantity": 7, "is_delisted": False},
            {"security_id_sha256": hashes[2], "role": "target_and_held", "holding_quantity": 9, "is_delisted": False},
        ]
        assert all(security_id not in text for security_id in ids)
        assert "123.45" not in text
        assert len(calls) == driver._reference_history_call_count == 1
        assert calls[0][1]["fill_forward"] is False
        assert calls[0][1]["data_normalization_mode"] is driver._raw_normalization


def test_projected_reference_complete_and_partial_paths_keep_exact_history_marks(family):
    with subject._relaxed._cloud_loader(_sources(family["ar_off", 0][0])) as (load, _):
        base = load("accepted_risk_six_universe_order_qc_runtime")
        ids = tuple("security-" + str(index).zfill(3) for index in range(3))
        driver, requested, calls = _reference_driver(base, ids)
        assert driver._reference_prices("2022-10-03", requested,
            target_security_ids=ids, holding_quantities={}) == {security_id: Decimal("123.45") for security_id in ids}
        assert len(calls) == driver._reference_history_call_count == 1
        driver, requested, calls = _reference_driver(base, ids[:2])
        with pytest.raises(base.AcceptedRiskSixUniverseOrderQcRuntimeError) as caught:
            driver._reference_prices("2022-10-03", requested, target_security_ids=ids, holding_quantities={})
        value = json.loads(str(caught.value).split("; context=", 1)[1])
        assert (value["requested_count"], value["received_count"], value["missing_count"]) == (3, 2, 1)
        assert value["missing"][0]["security_id_sha256"] == hashlib.sha256(ids[2].encode()).hexdigest()
        assert len(calls) == driver._reference_history_call_count == 1


def test_projected_reference_refusal_bounds_large_missing_census(family):
    with subject._relaxed._cloud_loader(_sources(family["ar_off", 0][0])) as (load, _):
        base = load("accepted_risk_six_universe_order_qc_runtime")
        driver, requested, calls = _reference_driver(base, (), missing_count=base.MAXIMUM_REFERENCE_SECURITIES)
        with pytest.raises(base.AcceptedRiskSixUniverseOrderQcRuntimeError) as caught:
            driver._reference_prices("2022-10-03", requested, target_security_ids=requested, holding_quantities={})
        text = str(caught.value).split("; context=", 1)[1]
        value = json.loads(text)
        assert len(text.encode("ascii")) <= 8192
        assert len(value["missing"]) == 32
        assert value["missing_count"] == base.MAXIMUM_REFERENCE_SECURITIES
        assert value["omitted_missing_count"] == base.MAXIMUM_REFERENCE_SECURITIES - 32
        assert len(calls) == 1


def test_projected_after_close_supplies_exact_target_and_nonzero_holding_context(family):
    with subject._relaxed._cloud_loader(_sources(family["ar_off", 0][0])) as (load, _):
        base = load("accepted_risk_six_universe_order_qc_runtime")
        driver = object.__new__(base.AcceptedRiskSixUniverseOrderQcDriver)
        driver._algorithm = SimpleNamespace(time=datetime(2022, 10, 3, 16))
        driver._require_initialized = lambda: None
        driver._observe_account = lambda session: None
        driver._decision_set = {"2022-10-03"}
        driver._variant = "r177"
        driver._snapshot = lambda session: object()
        driver._target_builder = SimpleNamespace(next_required_session="2022-10-03", build=lambda *args: SimpleNamespace(
            target_weights=(SimpleNamespace(security_id="target", weight=Decimal("0.98")),),
            target_sha256="a" * 64, sleeves=()))
        driver._current_holding_census = lambda: {"held": 7}
        driver._executor = SimpleNamespace(close_open_rebalance=lambda: None, prepare_rebalance=lambda **kwargs: None)
        driver._prune_execution_subscriptions = lambda ids: None
        observed = []
        driver._reference_prices = lambda *args, **kwargs: observed.append((args, kwargs)) or {}
        driver._session_positions = {"2022-10-03": 0}
        driver._session_axis = ("2022-10-03", "2022-10-04")
        driver._decision_target_sha256s = []
        driver._record_sleeve_diagnostics = lambda sleeves: None
        driver._fallback_counts = {}
        assert driver.on_after_close() is True
        assert observed == [(("2022-10-03", ("held", "target")),
                             {"target_security_ids": ("target",), "holding_quantities": {"held": 7}})]


def test_reference_diagnostic_renderer_requires_exact_original_refusal_anchor():
    path = "accepted_risk_six_universe_order_qc_runtime.py"
    original = Path(subject.__file__).with_name(path).read_text(encoding="ascii")
    changed = original.replace("no stale-price fallback is permitted", "changed refusal", 1)
    with pytest.raises(subject.MatchedHistoricalProjectionError, match="reference-refusal exact anchor"):
        subject._render_reference_refusal(path, changed)
