"""Isolating checks for the fixed-100%, 5-bps eight-arm source projection."""

import ast
from datetime import datetime
from decimal import Decimal
import hashlib
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import eight_universe_execution_stress_projection as stress
from research.analyst_revisions_v2_qc import eight_universe_execution_stress_study as study
from research.analyst_revisions_v2_qc import eight_universe_study as eight
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from scripts.run_arv2_qcom_restored import package
from tests.analyst_revisions_v2.test_qc_eight_universe_study import _eight_report


PINS = {
    "R280": ("4cc0a420bc4c0ed48c65aef1d27be49b840913f0045beed23f92ec28a3f3ffdd",
             "15f5f52f9d084ea9c7af1755867e1b016054aacd1e6498ac561ac132bfae8f72"),
    "R281": ("7a725fe4dc8d913cf56916b1f3d87409e6019a0cb01c7f1c73231e679fdddc2d",
             "5e5c53cbda74b2a1e4cb30f55ad22b5027baedbe67087ba236a24c1715a1d57e"),
    "R282": ("ce56c5860e2c76af685f02da53fcc18d5c93e5caa208e09b37ef8749ada1b5fe",
             "3563d10778d2ea843aad7e6c15a9e7d056567f25770879d76899e030cded075c"),
    "R283": ("bf5a8a130efe4a89d57ee06c62333bccd59c0d0ad72fbae0b6fbee4687ff12b1",
             "9119debdeaf8108eff46cffe74cc4d5df46b92ba59d09612a8ed03bbe5db310c"),
}


@pytest.fixture(scope="module")
def projections():
    current = package()
    return {candidate: stress.build_projection(current, candidate)
            for candidate in stress.CANDIDATE_PARENTS}


def _source(projection, path):
    return next(item.source_bytes.decode("ascii") for item in projection.source_files
                if item.project_path == path)


@pytest.mark.parametrize("candidate", PINS)
def test_exact_projection_profile_and_model_pin(projections, candidate):
    projection, profile = projections[candidate]
    assert (projection.projection_sha256, projection.profile_sha256) == PINS[candidate]
    assert profile["slippage_bps"] == "5"
    assert profile["modeled_fee_bps_per_side"] == "10"
    assert profile["target_gross_exposure"] == "0.98"
    assert profile["admission_leverage"] == "2"
    tree = ast.parse(_source(projection, "main.py"))
    models = [ast.unparse(node.value) for node in ast.walk(tree)
              if isinstance(node, ast.keyword) and node.arg == "slippage_model_factory"]
    assert models == ["lambda: ConstantSlippageModel(0.0005)"]
    diagnostic_calls = [node for node in ast.walk(tree)
                        if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id == "install_matched_diagnostics"]
    assert len(diagnostic_calls) == 1
    assert len(diagnostic_calls[0].args) == 3
    assert isinstance(diagnostic_calls[0].args[2], ast.Constant)
    assert diagnostic_calls[0].args[2].value == 5
    assert len(projection.source_files) == 17


def _fee_model(projection):
    tree = ast.parse(_source(projection, "main.py"))
    fee_classes = [node for node in tree.body if isinstance(node, ast.ClassDef)
                   and node.name == "Arv2TenBpsFeeModel"]
    assert len(fee_classes) == 1
    scope = {
        "FeeModel": object, "Decimal": Decimal,
        "MODELED_FEE_RATE_PER_SIDE": Decimal("0.001"),
        "OrderType": SimpleNamespace(MARKET_ON_OPEN="moo", MARKET="market"),
        "OrderFee": lambda value: SimpleNamespace(value=value),
        "CashAmount": lambda amount, currency: SimpleNamespace(amount=amount, currency=currency),
    }
    module = ast.fix_missing_locations(ast.Module(body=fee_classes, type_ignores=[]))
    exec(compile(module, "projected-five-bps-fee-model", "exec"), scope)
    return scope["Arv2TenBpsFeeModel"]()


@pytest.mark.parametrize("candidate", PINS)
@pytest.mark.parametrize("quantity", (Decimal(7), Decimal(-7)))
def test_signed_installed_slippage_changes_actual_moo_fee_in_adverse_direction(
        projections, candidate, quantity):
    model = _fee_model(projections[candidate][0])
    order = SimpleNamespace(type="moo", quantity=quantity,
                            absolute_quantity=abs(quantity))
    security = SimpleNamespace(open=Decimal("100"))
    calls = []

    def installed(asset, current):
        assert asset is security and current is order
        calls.append(True)
        return Decimal("0.07123")  # Deliberately not open * 5 bps.

    security.slippage_model = SimpleNamespace(get_slippage_approximation=installed)
    amount = model.get_order_fee(SimpleNamespace(security=security, order=order)).value.amount
    fill = Decimal("100.07123") if quantity > 0 else Decimal("99.92877")
    assert amount == fill * abs(quantity) * Decimal("0.001")
    assert calls == [True]


@pytest.mark.parametrize("candidate", PINS)
def test_market_valuation_callback_never_uses_execution_slippage(
        projections, candidate):
    model = _fee_model(projections[candidate][0])
    order = SimpleNamespace(type="market", absolute_quantity=Decimal(7))
    security = SimpleNamespace(open=Decimal("100"), slippage_model=SimpleNamespace(
        get_slippage_approximation=lambda *_: pytest.fail("valuation used execution slippage")))
    amount = model.get_order_fee(SimpleNamespace(security=security, order=order)).value.amount
    assert amount == Decimal("0.7")


def _projected_fill_audit(projection):
    tree = ast.parse(_source(projection, "main.py"))
    algorithm = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                     and node.name.startswith("ARV2"))
    methods = [node for node in algorithm.body if isinstance(node, ast.FunctionDef)
               and node.name in {"_arv2_capture_stress_fill", "_arv2_stress_aggregate"}]
    assert len(methods) == 2
    audit_class = ast.ClassDef(name="ProjectedAudit", bases=[], keywords=[],
                               body=methods, decorator_list=[])
    class TradeBar:
        def __init__(self, price, session="2021-01-05"):
            self.open = Decimal(price)
            self.end_time = datetime.fromisoformat(session + "T09:31:00")
    namespace = {"Decimal": Decimal, "TradeBar": TradeBar,
                 "OrderType": SimpleNamespace(MARKET_ON_OPEN="moo")}
    exec(compile(ast.fix_missing_locations(ast.Module(
        body=[audit_class], type_ignores=[])), "projected-fill-audit", "exec"), namespace)
    return namespace["ProjectedAudit"], TradeBar


@pytest.mark.parametrize("candidate", PINS)
def test_projected_fill_audit_checks_both_order_sides_without_order_export(
        projections, candidate):
    cls, bar_type = _projected_fill_audit(projections[candidate][0])
    subject = cls()
    subject._arv2_stress_fills = {
        "buy": 0, "sell": 0, "unverifiable": 0,
        "non_adverse": 0, "minimum_signed_bps": None}
    subject._arv2_prior_aggregate = lambda: {
        "execution": {"filled_order_count_sum": 2}, "run_valid": True}
    subject.time = datetime(2021, 1, 5, 9, 31)
    subject.transactions = SimpleNamespace(get_order_by_id=lambda _: SimpleNamespace(type="moo"))
    subject.securities = {"SID": SimpleNamespace(get_last_data=lambda: bar_type("100"))}
    for quantity, fill in ((7, "100.05"), (-7, "99.95")):
        subject._arv2_capture_stress_fill(SimpleNamespace(
            fill_quantity=quantity, fill_price=fill, order_id=1, symbol="SID"))
    result = subject._arv2_stress_aggregate()
    audit = result["execution_stress_fill_audit"]
    assert result["run_valid"] is True
    assert audit["valid"] is True
    assert audit["buy_fill_count"] == audit["sell_fill_count"] == 1
    assert Decimal(audit["minimum_signed_adverse_bps"]) == Decimal("5")
    assert not any("SID" in str(value) for value in audit.values())


@pytest.mark.parametrize("fill,bar_session,expected", [
    ("100", "2021-01-05", "non_adverse_fill_count"),
    ("100.05", "2021-01-04", "unverifiable_fill_count"),
])
def test_projected_fill_audit_refuses_zero_slip_or_stale_bar(
        projections, fill, bar_session, expected):
    cls, bar_type = _projected_fill_audit(projections["R281"][0])
    subject = cls()
    subject._arv2_stress_fills = {
        "buy": 0, "sell": 0, "unverifiable": 0,
        "non_adverse": 0, "minimum_signed_bps": None}
    subject._arv2_prior_aggregate = lambda: {
        "execution": {"filled_order_count_sum": 1}, "run_valid": True}
    subject.time = datetime(2021, 1, 5, 9, 31)
    subject.transactions = SimpleNamespace(get_order_by_id=lambda _: SimpleNamespace(type="moo"))
    subject.securities = {"SID": SimpleNamespace(get_last_data=lambda: bar_type(
        "100", bar_session))}
    subject._arv2_capture_stress_fill(SimpleNamespace(
        fill_quantity=7, fill_price=fill, order_id=1, symbol="SID"))
    result = subject._arv2_stress_aggregate()
    assert result["run_valid"] is False
    assert result["execution_stress_fill_audit"][expected] == 1


def test_null_model_mutation_is_refused():
    projection, _ = stress._parent(package(), "R281")
    source = _source(projection, "main.py")
    mutated = source.replace("lambda: NullSlippageModel()", "lambda: WrongSlippageModel()")
    assert mutated != source
    with pytest.raises(stress.EightUniverseExecutionStressProjectionError,
                       match="installed-model anchor"):
        tree = ast.parse(_source(projection, "accepted_risk_six_universe_order_tilt_qc_runtime.py"))
        variant = next(node.value.value for node in tree.body if isinstance(node, ast.Assign)
                       and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                       and node.targets[0].id == "TILT_VARIANT")
        stress._render("main.py", mutated, projection, variant, "R281")


def test_diagnostic_slippage_anchor_mutation_is_refused():
    projection, _ = stress._parent(package(), "R281")
    source = _source(projection, "main.py")
    mutated = source.replace("install_matched_diagnostics(self._arv2_driver, 'ar_on100_weights_only', 0)",
                             "install_matched_diagnostics(self._arv2_driver, 'ar_on100_weights_only', 1)")
    assert mutated != source
    with pytest.raises(stress.EightUniverseExecutionStressProjectionError,
                       match="diagnostic slippage anchor"):
        tree = ast.parse(_source(projection, "accepted_risk_six_universe_order_tilt_qc_runtime.py"))
        variant = next(node.value.value for node in tree.body if isinstance(node, ast.Assign)
                       and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                       and node.targets[0].id == "TILT_VARIANT")
        stress._render("main.py", mutated, projection, variant, "R281")


def test_unfrozen_candidate_refused():
    with pytest.raises(stress.EightUniverseExecutionStressProjectionError,
                       match="not frozen"):
        stress._parent(object(), "R284")


def test_frozen_stress_manifest_keeps_capacity_unavailable_not_a_zero_pass(projections):
    frozen = study.frozen_manifest()
    assert frozen["protocol"]["liquidity_capacity_diagnostic"] == {
        "status": "unavailable",
        "reason": "no_authenticated_prior_20_closed_session_RAW_volume_feed_in_source_v1",
    }
    assert [row["candidate_id"] for row in frozen["candidates"]] == list(PINS)
    assert [row["slippage_bps"] for row in frozen["candidates"]] == [5] * 4
    assert all((row["projection_sha256"], row["profile_sha256"],
                row["source_files_sha256"]) == study.PINS[row["candidate_id"]]
               for row in frozen["candidates"])
    serialized = study.source_contract._canonical(frozen).decode("ascii")
    for forbidden in ("eligible_within_one_percent", "over_one_percent",
                      "maximum_participation", "p95_participation",
                      "missing_volume_count", '"capacity_valid":true'):
        assert forbidden not in serialized


def test_frozen_manifest_matches_rendered_source(projections):
    actual = study.freeze_manifest(package())
    assert actual == study.frozen_manifest()


@pytest.mark.parametrize("candidate", PINS)
def test_stress_candidate_routes_to_exact_manifest_and_previews(tmp_path, projections, candidate):
    plan = adapter.build_plan(candidate, "a" * 32, tmp_path / "control",
                              family=study.FAMILY)
    identity = adapter.preview(plan, projections[candidate][0])
    assert identity["manifest_sha256"] == study.FROZEN_MANIFEST_SHA256
    assert identity["projection_sha256"] == PINS[candidate][0]
    assert identity["profile_sha256"] == PINS[candidate][1]


def test_eight_diagnostic_rejects_zero_slippage_as_five():
    report = _eight_report("ar_off")
    report["slippage_bps_per_side"] = 5
    assert eight._validate_eight_diagnostics(
        report, "ar_off", expected_slippage_bps=5) is True
    with pytest.raises(adapter.RelaxedQcSubmissionError):
        eight._validate_eight_diagnostics(report, "ar_off")
    report["slippage_bps_per_side"] = 0
    with pytest.raises(adapter.RelaxedQcSubmissionError):
        eight._validate_eight_diagnostics(
            report, "ar_off", expected_slippage_bps=5)


@pytest.mark.parametrize("candidate", PINS)
def test_stress_parser_refuses_changed_economic_arm(monkeypatch, tmp_path, candidate):
    plan = adapter.build_plan(candidate, "a" * 32, tmp_path / "control",
                              family=study.FAMILY)
    row = adapter._candidate(plan)
    parsed = {"meta": {"matched_diagnostics_sha256": "digest"},
              "aggregates": {
                  "comparison_arm": "unrelated",
                  "analyst_revision_economic_usage": row["analyst_revision_economic_usage"],
                  "coverage_policy_id": row["coverage_policy_id"],
                  "account": {"cumulative_return": "0"}}}
    monkeypatch.setattr(adapter, "_parse_order_common", lambda *a, **kw: parsed)
    with pytest.raises(study.EightUniverseExecutionStressStudyError,
                       match="economic arm"):
        adapter._parse_order(plan, {key: "{}" for key in row["statistic_names"]})


def test_stress_parser_accepts_only_digest_bound_five_bps_report(monkeypatch, tmp_path):
    plan = adapter.build_plan("R280", "a" * 32, tmp_path / "control",
                              family=study.FAMILY)
    row = adapter._candidate(plan)
    report = _eight_report(row["arm"])
    report["slippage_bps_per_side"] = 5
    parsed = {"meta": {"matched_diagnostics_sha256": adapter._sha(report)},
              "aggregates": {
                  "comparison_arm": row["arm"],
                  "analyst_revision_economic_usage": row["analyst_revision_economic_usage"],
                  "coverage_policy_id": row["coverage_policy_id"],
                  "matched_baseline_target_path_sha256":
                      study.attribution.PARENT_BASELINE_PATH_SHA256["R268"],
                  "execution": {"filled_order_count_sum": 2},
                  "execution_stress_fill_audit": {
                      "schema": "arv2-eight-five-bps-moo-fill-audit-v1",
                      "filled_moo_count": 2, "buy_fill_count": 1, "sell_fill_count": 1,
                      "unverifiable_fill_count": 0,
                      "non_adverse_fill_count": 0,
                      "minimum_signed_adverse_bps": "5",
                      "reference": "same-session-TradeBar-open", "valid": True,
                  },
                  "account": {"cumulative_return": report["overall_cumulative_return"]}}}
    parsed["run_valid"] = True
    monkeypatch.setattr(adapter, "_parse_order_common", lambda *a, **kw: parsed)
    monkeypatch.setattr(adapter, "_statistic", lambda *a, **kw: report)
    stats = {key: "{}" for key in row["statistic_names"]}
    assert adapter._parse_order(plan, stats)["diagnostics"] is report
    parsed["meta"]["matched_diagnostics_sha256"] = "wrong"
    with pytest.raises(study.EightUniverseExecutionStressStudyError,
                       match="diagnostic identity"):
        adapter._parse_order(plan, stats)
    parsed["meta"]["matched_diagnostics_sha256"] = adapter._sha(report)
    parsed["aggregates"]["matched_baseline_target_path_sha256"] = "0" * 64
    with pytest.raises(study.EightUniverseExecutionStressStudyError,
                       match="matched selected-name/weight baseline path"):
        adapter._parse_order(plan, stats)


def test_stress_parser_refuses_unverified_or_zero_adversity(monkeypatch, tmp_path):
    plan = adapter.build_plan("R280", "a" * 32, tmp_path / "control",
                              family=study.FAMILY)
    row = adapter._candidate(plan)
    report = _eight_report(row["arm"])
    report["slippage_bps_per_side"] = 5
    audit = {"schema": "arv2-eight-five-bps-moo-fill-audit-v1",
             "filled_moo_count": 2, "buy_fill_count": 1, "sell_fill_count": 1,
             "unverifiable_fill_count": 1, "non_adverse_fill_count": 0,
             "minimum_signed_adverse_bps": "5",
             "reference": "same-session-TradeBar-open", "valid": True}
    parsed = {"meta": {"matched_diagnostics_sha256": adapter._sha(report)},
              "aggregates": {
                  "comparison_arm": row["arm"],
                  "analyst_revision_economic_usage": row["analyst_revision_economic_usage"],
                  "coverage_policy_id": row["coverage_policy_id"],
                  "matched_baseline_target_path_sha256":
                      study.attribution.PARENT_BASELINE_PATH_SHA256["R268"],
                  "execution": {"filled_order_count_sum": 2},
                  "execution_stress_fill_audit": audit,
                  "account": {"cumulative_return": report["overall_cumulative_return"]}},
              "run_valid": True}
    monkeypatch.setattr(adapter, "_parse_order_common", lambda *a, **kw: parsed)
    monkeypatch.setattr(adapter, "_statistic", lambda *a, **kw: report)
    stats = {key: "{}" for key in row["statistic_names"]}
    with pytest.raises(study.EightUniverseExecutionStressStudyError,
                       match="fill audit"):
        adapter._parse_order(plan, stats)


def test_saved_four_arm_stress_requires_common_input_and_valid_fills(monkeypatch, tmp_path):
    """The comparison refuses a tampered arm, not merely a completed QC job."""
    originals = {candidate: {
        "run_valid": True,
        "aggregates": {
            "account": {
                "cumulative_return": str(Decimal(index) / Decimal(10)),
                "maximum_drawdown": "0.1", "starting_equity": "1000000",
                "first_observation_session": "2021-01-04",
                "last_observation_session": "2025-12-31",
                "observation_count": 1255,
            },
            "execution": {
                "submitted_rebalance_count": 261,
                "completed_rebalance_count": 261,
                "invalid_order_count_sum": 0,
                "canceled_order_count_sum": 0,
                "submitted_order_count": 2,
                "filled_order_count_sum": 2,
                "actual_engine_fee_amount": "10",
                "modeled_fee_amount": "10",
            },
            "execution_stress_fill_audit": {"valid": True},
            "matched_baseline_target_path_sha256":
                study.attribution.PARENT_BASELINE_PATH_SHA256[
                    "R268" if candidate in ("R280", "R281") else "R270"],
            "target_gross_exposure": "0.98", "admission_leverage": "2",
        },
        "diagnostics": {
            "membership_cap_path_sha256": "member-pin",
            "etf_daily_panel_sha256": "etf-pin",
            "slippage_bps_per_side": 5,
        },
    } for index, candidate in enumerate(study.PARENT_BY_CANDIDATE)}
    parents = {study.PARENT_BY_CANDIDATE[candidate]: {
        "aggregates": {
            "account": {"starting_equity": "1000000", "cumulative_return": "0",
                        "maximum_drawdown": "0.1"},
            "execution": {"modeled_fee_amount": "8"},
        },
        "diagnostics": {
            "membership_cap_path_sha256": "member-pin",
            "etf_daily_panel_sha256": "etf-pin",
        },
    } for candidate in originals}
    monkeypatch.setattr(study, "require_parents", lambda plan: {"results": parents})
    monkeypatch.setattr(study.attribution, "_annual_contrasts", lambda arms: ([], {}))
    monkeypatch.setattr(adapter, "_path", lambda plan, kind: tmp_path / (
        plan.candidate_id + "-" + str(plan.attempt) + "-" + kind))
    for candidate in originals:
        (tmp_path / (candidate + "-1-result")).touch()
    monkeypatch.setattr(study, "_authenticated_result", lambda plan:
                        originals[plan.candidate_id])
    common = study.compare_from_saved("a" * 32)
    assert common["valid"] is True
    assert common["all_moo_fill_audits_valid"] is True
    assert common["contrasts"]["full_minus_cap_base_pp"] == "30.0"
    assert common["paired_five_bps_minus_zero_bps"]["R281"]["net_return_change_pp"] == "10.0"

    originals["R281"]["aggregates"]["execution_stress_fill_audit"]["valid"] = False
    with pytest.raises(study.EightUniverseExecutionStressStudyError,
                       match="fill, fee or order gate"):
        study.compare_from_saved("a" * 32)
    originals["R281"]["aggregates"]["execution_stress_fill_audit"]["valid"] = True
    originals["R282"]["diagnostics"]["etf_daily_panel_sha256"] = "changed"
    with pytest.raises(study.EightUniverseExecutionStressStudyError,
                       match="common input"):
        study.compare_from_saved("a" * 32)
    originals["R282"]["diagnostics"]["etf_daily_panel_sha256"] = "etf-pin"
    parents["R278"]["diagnostics"]["etf_daily_panel_sha256"] = "old-vintage"
    with pytest.raises(study.EightUniverseExecutionStressStudyError,
                       match="common input"):
        study.compare_from_saved("a" * 32)


def test_retrospective_stress_result_refuses_changed_private_project_receipt(
        monkeypatch, tmp_path):
    plan = adapter.build_plan("R280", "a" * 32, tmp_path / "control",
                              family=study.FAMILY)
    launch = {"project_id": 123, "backtest_id": "exact-run"}
    monkeypatch.setattr(adapter, "_receipt", lambda *args: None)
    monkeypatch.setattr(adapter, "_path", lambda _plan, kind: tmp_path / kind)
    monkeypatch.setattr(adapter.common, "_read", lambda path:
                        launch if path.name == "launch" else {
                            "candidate_id": "R280", "project_id": 123,
                            "project_name": "wrong-project"})
    with pytest.raises(study.EightUniverseExecutionStressStudyError,
                       match="retained terminal or read claim"):
        study._authenticated_result(plan)


def test_stress_parser_refuses_a_valid_run_whose_consistent_audit_is_invalid(
        monkeypatch, tmp_path):
    """run_valid=True must carry a valid fill audit even when the audit's own
    valid flag agrees with its counts; an invalid run may still be parsed."""
    plan = adapter.build_plan("R280", "a" * 32, tmp_path / "control",
                              family=study.FAMILY)
    row = adapter._candidate(plan)
    report = _eight_report(row["arm"])
    report["slippage_bps_per_side"] = 5
    audit = {"schema": "arv2-eight-five-bps-moo-fill-audit-v1",
             "filled_moo_count": 2, "buy_fill_count": 1, "sell_fill_count": 1,
             "unverifiable_fill_count": 0, "non_adverse_fill_count": 1,
             "minimum_signed_adverse_bps": "0",
             "reference": "same-session-TradeBar-open", "valid": False}
    parsed = {"meta": {"matched_diagnostics_sha256": adapter._sha(report)},
              "aggregates": {
                  "comparison_arm": row["arm"],
                  "analyst_revision_economic_usage": row["analyst_revision_economic_usage"],
                  "coverage_policy_id": row["coverage_policy_id"],
                  "matched_baseline_target_path_sha256":
                      study.attribution.PARENT_BASELINE_PATH_SHA256["R268"],
                  "execution": {"filled_order_count_sum": 2},
                  "execution_stress_fill_audit": audit,
                  "account": {"cumulative_return": report["overall_cumulative_return"]}},
              "run_valid": False}
    monkeypatch.setattr(adapter, "_parse_order_common", lambda *a, **kw: parsed)
    monkeypatch.setattr(adapter, "_statistic", lambda *a, **kw: report)
    stats = {key: "{}" for key in row["statistic_names"]}
    assert adapter._parse_order(plan, stats)["run_valid"] is False
    parsed["run_valid"] = True
    with pytest.raises(study.EightUniverseExecutionStressStudyError,
                       match="fill audit is inconsistent"):
        adapter._parse_order(plan, stats)


@pytest.mark.parametrize("tampered", ("R268", "R277", "R278", "R270"))
def test_stress_parent_result_bytes_are_pinned_for_every_parent(
        monkeypatch, tmp_path, tampered):
    """R277/R278 result bytes are pinned only here; the attribution family pins
    R268 and R270 alone. Equal JSON with different bytes must still refuse."""
    plan = adapter.build_plan("R280", "a" * 32, tmp_path / "control",
                              family=study.FAMILY)
    served = {parent: ('{"parent": "' + parent + '"}').encode()
              for parent in study.PARENT_RESULT_SHA256}
    monkeypatch.setattr(study, "PARENT_RESULT_SHA256", {
        parent: hashlib.sha256(raw).hexdigest() for parent, raw in served.items()})
    monkeypatch.setattr(study.attribution, "compare_from_saved", lambda organization_id: {
        "valid": True, "common_input_not_full_stock_minute_fill_tape": True})
    monkeypatch.setattr(study.attribution, "_authenticated_result",
                        lambda prior: {"run_valid": True})
    monkeypatch.setattr(adapter, "_path", lambda prior, kind: SimpleNamespace(
        read_bytes=lambda: served[prior.candidate_id]))
    assert set(study.require_parents(plan)["results"]) == set(served)
    served[tampered] = served[tampered].replace(b": ", b":")
    with pytest.raises(study.EightUniverseExecutionStressStudyError,
                       match="parent result bytes changed"):
        study.require_parents(plan)
