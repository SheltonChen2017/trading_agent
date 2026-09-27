"""Offline proofs for six prospective, same-source physical-order arms."""

import ast
import dataclasses
from datetime import datetime, timedelta
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
        assert profile["reference_price_rule"] == subject.REFERENCE_PRICE_RULE
        assert profile["engine_fee_basis"] == subject.ENGINE_FEE_BASIS
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
        def __init__(self, symbol, delisted):
            self.symbol = symbol
            self.is_delisted = delisted
            self.last_data = None
            self.last_data_calls = 0

        def get_last_data(self):
            self.last_data_calls += 1
            return self.last_data

        @property
        def price(self):
            pytest.fail("missing history must never read a stale security price")

    securities = {security_id: _Security(symbols[security_id], index == 0)
                  for index, security_id in enumerate(requested)}

    class _TradeBar(SimpleNamespace):
        pass

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
    driver._algorithm = SimpleNamespace(history=_History(), time=datetime(2022, 10, 3, 16))
    driver._trade_bar_type = _TradeBar
    driver._daily_resolution = object()
    driver._raw_normalization = object()
    driver._reference_history_call_count = 0
    driver._configured_sids = {symbol.id for symbol in symbols.values()}
    driver._reference_closing_minute_repair_count = 0
    driver._reference_closing_minute_repair_sessions = set()
    driver._reference_closing_minute_repair_path = []
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
            {"security_id_sha256": hashes[0], "role": "target_only", "holding_quantity": 0, "is_delisted": True,
             "closing_minute_refusal_reason": "not_trade_bar"},
            {"security_id_sha256": hashes[1], "role": "held_only", "holding_quantity": 7, "is_delisted": False,
             "closing_minute_refusal_reason": "not_trade_bar"},
            {"security_id_sha256": hashes[2], "role": "target_and_held", "holding_quantity": 9, "is_delisted": False,
             "closing_minute_refusal_reason": "not_trade_bar"},
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
        assert all(driver._ensure_security(security_id)[1].last_data_calls == 0 for security_id in ids)
        assert driver._reference_closing_minute_repair_count == 0
        assert driver._reference_closing_minute_repair_path == []
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


def _fresh_closing_bar(driver, security_id):
    symbol, security = driver._ensure_security(security_id)
    security.last_data = driver._trade_bar_type(symbol=symbol,
        time=driver._algorithm.time - timedelta(minutes=1), end_time=driver._algorithm.time,
        period=timedelta(minutes=1), is_fill_forward=False, close=Decimal("234.56"))
    return security


@pytest.mark.parametrize("arm,slip", tuple((arm, slip) for arm in subject.ARMS for slip in subject.SLIPPAGE_BPS))
def test_missing_daily_reference_accepts_only_exact_fresh_closing_minute(family, arm, slip):
    with subject._relaxed._cloud_loader(_sources(family[arm, slip][0])) as (load, _):
        base = load("accepted_risk_six_universe_order_qc_runtime")
        ids = tuple("security-" + str(index).zfill(3) for index in range(3))
        driver, requested, calls = _reference_driver(base, ids[:2])
        security = _fresh_closing_bar(driver, ids[2])
        assert driver._reference_prices("2022-10-03", requested,
            target_security_ids=ids, holding_quantities={ids[2]: 136}) == {
                ids[0]: Decimal("123.45"), ids[1]: Decimal("123.45"), ids[2]: Decimal("234.56")}
        assert len(calls) == driver._reference_history_call_count == security.last_data_calls == 1
        assert driver._reference_closing_minute_repair_count == 1
        assert driver._reference_closing_minute_repair_sessions == {"2022-10-03"}
        assert driver._reference_closing_minute_repair_path == [
            ["2022-10-03", hashlib.sha256(ids[2].encode("utf-8")).hexdigest()]]


@pytest.mark.parametrize("mutation,reason", (
    ("stale", "not_exact_same_session_closing_minute"),
    ("wrong_start", "not_exact_same_session_closing_minute"),
    ("wrong_end", "not_exact_same_session_closing_minute"),
    ("next_day", "not_exact_same_session_closing_minute"),
    ("wrong_session", "not_exact_same_session_closing_minute"),
    ("wrong_sid", "bar_sid_mismatch"),
    ("wrong_security_sid", "security_sid_mismatch"),
    ("fill_forward", "fill_forward_or_unknown"),
    ("unknown_fill_forward", "fill_forward_or_unknown"),
    ("zero", "closing_minute_unavailable_or_invalid"),
    ("negative", "closing_minute_unavailable_or_invalid"),
    ("nan", "closing_minute_unavailable_or_invalid"),
    ("infinity", "closing_minute_unavailable_or_invalid"),
    ("quote", "not_trade_bar"),
    ("unreadable_cache", "closing_minute_unavailable_or_invalid"),
    ("unreadable_close", "closing_minute_unavailable_or_invalid"),
    ("not_raw", "not_raw_configured"),
    ("wrong_period", "not_one_minute_period"),
))
def test_closing_minute_repair_refuses_every_stale_or_invalid_direction(family, mutation, reason):
    with subject._relaxed._cloud_loader(_sources(family["ar_off", 0][0])) as (load, _):
        base = load("accepted_risk_six_universe_order_qc_runtime")
        driver, ids, calls = _reference_driver(base, (), missing_count=1)
        security = _fresh_closing_bar(driver, ids[0])
        bar = security.last_data
        if mutation == "stale":
            bar.time -= timedelta(minutes=1)
            bar.end_time -= timedelta(minutes=1)
        elif mutation == "wrong_start":
            bar.time -= timedelta(seconds=1)
        elif mutation == "wrong_end":
            bar.end_time -= timedelta(seconds=1)
        elif mutation == "next_day":
            bar.time += timedelta(days=1)
            bar.end_time += timedelta(days=1)
        elif mutation == "wrong_session":
            driver._algorithm.time += timedelta(days=1)
            bar.time += timedelta(days=1)
            bar.end_time += timedelta(days=1)
        elif mutation == "wrong_sid":
            bar.symbol = SimpleNamespace(id="OTHER-SID")
        elif mutation == "wrong_security_sid":
            security.symbol = SimpleNamespace(id="OTHER-SID")
        elif mutation in ("fill_forward", "unknown_fill_forward"):
            bar.is_fill_forward = True if mutation == "fill_forward" else None
        elif mutation in ("zero", "negative", "nan", "infinity"):
            bar.close = Decimal({"zero": "0", "negative": "-1", "nan": "NaN", "infinity": "Infinity"}[mutation])
        elif mutation == "quote":
            security.last_data = SimpleNamespace(**vars(bar))
        elif mutation == "unreadable_cache":
            def unreadable():
                raise Exception("synthetic unreadable CLR cache")
            security.get_last_data = unreadable
        elif mutation == "unreadable_close":
            del bar.close
        elif mutation == "not_raw":
            driver._configured_sids.clear()
        elif mutation == "wrong_period":
            bar.period = timedelta(minutes=2)
        with pytest.raises(base.AcceptedRiskSixUniverseOrderQcRuntimeError,
                           match="no stale-price fallback is permitted; context=") as caught:
            driver._reference_prices("2022-10-03", ids, target_security_ids=ids, holding_quantities={ids[0]: 136})
        context = json.loads(str(caught.value).split("; context=", 1)[1])
        assert context["missing"][0]["closing_minute_refusal_reason"] == reason
        assert context["missing"][0]["role"] == "target_and_held"
        assert context["missing"][0]["holding_quantity"] == 136
        assert context["fresh_closing_minute_available_count"] == 0
        assert len(calls) == driver._reference_history_call_count == 1
        assert driver._reference_closing_minute_repair_count == 0
        assert driver._reference_closing_minute_repair_path == []


def test_partial_fresh_closing_census_is_not_committed_or_counted(family):
    with subject._relaxed._cloud_loader(_sources(family["ar_off", 0][0])) as (load, _):
        base = load("accepted_risk_six_universe_order_qc_runtime")
        driver, ids, calls = _reference_driver(base, ())
        _fresh_closing_bar(driver, ids[0])
        with pytest.raises(base.AcceptedRiskSixUniverseOrderQcRuntimeError) as caught:
            driver._reference_prices("2022-10-03", ids, target_security_ids=ids, holding_quantities={})
        context = json.loads(str(caught.value).split("; context=", 1)[1])
        assert context["fresh_closing_minute_available_count"] == 1
        assert context["missing_count"] == 3 and context["received_count"] == 0
        assert context["missing"][0]["closing_minute_refusal_reason"] == "fresh_closing_minute_available_census_incomplete"
        assert driver._reference_closing_minute_repair_count == 0
        assert driver._reference_closing_minute_repair_sessions == set()
        assert driver._reference_closing_minute_repair_path == []
        assert len(calls) == 1


def _projected_fee_model(projection):
    tree = ast.parse(_sources(projection)["main.py"])
    fee_class = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                     and node.name == "Arv2TenBpsFeeModel")
    scope = {"FeeModel": object, "Decimal": Decimal, "MODELED_FEE_RATE_PER_SIDE": Decimal("0.001"),
             "OrderType": SimpleNamespace(MARKET_ON_OPEN="moo", MARKET="market"),
             "OrderFee": lambda value: SimpleNamespace(value=value),
             "CashAmount": lambda amount, currency: SimpleNamespace(amount=amount, currency=currency)}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fee_class], type_ignores=[])),
                 "projected-fee-model", "exec"), scope)
    return scope["Arv2TenBpsFeeModel"]()


def _fee_parameters(quantity, slippage, open_price=Decimal("100")):
    calls = []
    order = SimpleNamespace(quantity=quantity, absolute_quantity=abs(quantity), type="moo")
    security = SimpleNamespace(open=open_price)
    def installed_model(asset, current_order):
        assert asset is security and current_order is order
        calls.append(current_order)
        return slippage
    security.slippage_model = SimpleNamespace(get_slippage_approximation=installed_model)
    return SimpleNamespace(security=security, order=order), calls


@pytest.mark.parametrize("arm,slip,quantity", tuple((arm, slip, quantity)
    for arm in subject.ARMS for slip in subject.SLIPPAGE_BPS for quantity in (Decimal(7), Decimal(-7))))
def test_projected_fee_matches_full_moo_fill_with_installed_slippage(family, arm, slip, quantity):
    model = _projected_fee_model(family[arm, slip][0])
    # This installed slippage deliberately differs from open * .0005, as an
    # older LEAN ConstantSlippageModel can reference the last bar's close.
    installed_slippage = Decimal(0) if slip == 0 else Decimal("0.07123")
    parameters, calls = _fee_parameters(quantity, installed_slippage)
    fee = model.get_order_fee(parameters)
    fill_price = parameters.security.open + (installed_slippage if quantity > 0 else -installed_slippage)
    assert type(fee.value.amount) is Decimal
    assert fee.value.currency == "USD"
    assert fee.value.amount == fill_price * abs(quantity) * Decimal("0.001")
    assert len(calls) == 1
    if slip == 0:
        assert fee.value.amount == parameters.security.open * abs(quantity) * Decimal("0.001")


@pytest.mark.parametrize("mutation", ("zero_open", "negative_open", "nan_open", "infinite_open",
    "negative_slippage", "nan_slippage", "infinite_slippage", "nonpositive_sell_price",
    "nan_quantity", "zero_quantity", "wrong_absolute_quantity", "unsupported_order_type", "unreadable_model"))
def test_projected_fee_refuses_invalid_model_or_fill_price_basis(family, mutation):
    model = _projected_fee_model(family["six_etf_basket", 5][0])
    parameters, calls = _fee_parameters(Decimal(-7), Decimal("0.05"))
    if mutation.endswith("_open"):
        parameters.security.open = Decimal({"zero_open": "0", "negative_open": "-1",
            "nan_open": "NaN", "infinite_open": "Infinity"}[mutation])
    elif mutation.endswith("_slippage"):
        parameters, calls = _fee_parameters(Decimal(-7), Decimal({"negative_slippage": "-1",
            "nan_slippage": "NaN", "infinite_slippage": "Infinity"}[mutation]))
    elif mutation == "nonpositive_sell_price":
        parameters, calls = _fee_parameters(Decimal(-7), Decimal("100"))
    elif mutation == "nan_quantity":
        parameters.order.quantity = Decimal("NaN")
    elif mutation == "zero_quantity":
        parameters.order.quantity = parameters.order.absolute_quantity = Decimal(0)
    elif mutation == "wrong_absolute_quantity":
        parameters.order.absolute_quantity = Decimal(8)
    elif mutation == "unsupported_order_type":
        parameters.order.type = "limit"
    elif mutation == "unreadable_model":
        def unreadable(asset, order):
            raise RuntimeError("synthetic unreadable slippage model")
        parameters.security.slippage_model.get_slippage_approximation = unreadable
    with pytest.raises(RuntimeError):
        model.get_order_fee(parameters)


@pytest.mark.parametrize("arm,slip,quantity", tuple((arm, slip, quantity)
    for arm in subject.ARMS for slip in subject.SLIPPAGE_BPS for quantity in (Decimal(7), Decimal(-7))))
def test_projected_fee_accepts_market_valuation_without_slippage_or_legacy_dispatch(family, arm, slip, quantity):
    model = _projected_fee_model(family[arm, slip][0])
    parameters, calls = _fee_parameters(quantity, Decimal("0.07123"))
    parameters.order.type = "market"
    # LEAN's valuation order only needs absolute quantity. The fee callback
    # must not read signed quantity or consult the execution slippage model.
    del parameters.order.quantity
    def unexpected_slippage(asset, order):
        pytest.fail("synthetic MARKET valuation must preserve the original RAW-open estimate")
    parameters.security.slippage_model.get_slippage_approximation = unexpected_slippage

    class _FeeModelPythonWrapper:
        """Reproduce the callback fallback that masked the original refusal."""
        extended_version = True
        legacy_calls = 0

        def get_order_fee(self, current):
            if self.extended_version:
                try:
                    return model.get_order_fee(current)
                except Exception:
                    self.extended_version = False
            self.legacy_calls += 1
            return model.get_order_fee(current.security, current.order)

    wrapper = _FeeModelPythonWrapper()
    for _ in range(2):
        fee = wrapper.get_order_fee(parameters)
        assert type(fee.value.amount) is Decimal
        assert fee.value.currency == "USD"
        assert fee.value.amount == parameters.security.open * abs(quantity) * Decimal("0.001")
    assert wrapper.extended_version and wrapper.legacy_calls == 0
    assert calls == []


@pytest.mark.parametrize("field,value", tuple((field, Decimal(value))
    for field in ("open", "absolute_quantity") for value in ("0", "NaN", "Infinity"))
    + (("open", Decimal(-1)),))
def test_projected_fee_refuses_invalid_market_valuation_inputs_before_slippage(family, field, value):
    model = _projected_fee_model(family["ar_off", 5][0])
    parameters, calls = _fee_parameters(Decimal(7), Decimal("0.05"))
    parameters.order.type = "market"
    setattr(parameters.security if field == "open" else parameters.order, field, value)
    with pytest.raises(RuntimeError, match="ARV2 fee input is invalid"):
        model.get_order_fee(parameters)
    assert calls == []


@pytest.mark.parametrize("quantity", (Decimal(7), Decimal(-7)))
def test_fee_correction_preserves_load_bearing_lifecycle_mismatch_detection(family, quantity):
    with subject._relaxed._cloud_loader(_sources(family["six_etf_basket", 5][0])) as (load, _):
        core = load("accepted_risk_order_level_core")
        starting = {} if quantity > 0 else {"stock": 20}
        target = {"stock": Decimal("0.98")} if quantity > 0 else {"proxy": Decimal("0.98")}
        plan = core.plan_rebalance(rebalance_id="fee-basis-regression",
            starting_cash=Decimal("1000000"), current_quantities=starting, target_weights=target,
            reference_prices={security_id: Decimal(100) for security_id in set(starting) | set(target)})
        # Complete every actual intent using the default full-MOO fill shape.
        model = _projected_fee_model(family["six_etf_basket", 5][0])
        events = []
        wrong = []
        for index, intent in enumerate(plan.intents):
            signed = Decimal(intent.quantity) * (Decimal(1) if intent.side == core.BUY else Decimal(-1))
            parameters, calls = _fee_parameters(signed, Decimal("0.05"))
            fill_price = Decimal(100) + (Decimal("0.05") if signed > 0 else Decimal("-0.05"))
            fee = model.get_order_fee(parameters).value.amount
            event = core.FillEvent(event_id="event-" + str(index), rebalance_id=plan.rebalance_id,
                client_order_id=intent.client_order_id, status=core.FILLED, fill_quantity=intent.quantity,
                fill_price=fill_price, engine_fee_amount=fee, engine_fee_currency="USD")
            events.append(event)
            wrong.append(dataclasses.replace(event,
                engine_fee_amount=Decimal(100) * Decimal(intent.quantity) * Decimal("0.001")))
        corrected = core.summarize_order_lifecycle(plan, tuple(events))
        assert corrected.fee_mismatch is False
        assert corrected.modeled_fee_amount == corrected.actual_engine_fee_amount
        assert core.summarize_order_lifecycle(plan, tuple(wrong)).fee_mismatch is True


def test_fee_basis_renderer_refuses_changed_original_fee_anchor():
    original = """class Arv2TenBpsFeeModel(FeeModel):
    def get_order_fee(self, parameters):
        return None
"""
    with pytest.raises(subject.MatchedHistoricalProjectionError, match="fee-basis exact anchor"):
        subject._render_fee_basis("main.py", original)


def test_fee_basis_keeps_decimal_string_conversion_and_exact_cash_amount(family):
    model = _projected_fee_model(family["six_etf_basket", 5][0])
    class _ClrDecimalLike:
        def __init__(self, text):
            self.text = text

        def __str__(self):
            return self.text

        def __float__(self):
            pytest.fail("authoritative fee values must not convert through binary float")

    order = SimpleNamespace(quantity=_ClrDecimalLike("-777"),
        absolute_quantity=_ClrDecimalLike("777"), type="moo")
    security = SimpleNamespace(open=_ClrDecimalLike("100.12345678"),
        slippage_model=SimpleNamespace(get_slippage_approximation=lambda asset, current:
            _ClrDecimalLike("0.05006172839")))
    fee = model.get_order_fee(SimpleNamespace(security=security, order=order))
    assert type(fee.value.amount) is Decimal
    assert fee.value.amount == (Decimal("100.12345678") - Decimal("0.05006172839")) * Decimal(777) * Decimal("0.001")
    assert fee.value.currency == "USD"
    assert fee.value.amount.as_tuple().exponent >= -28
