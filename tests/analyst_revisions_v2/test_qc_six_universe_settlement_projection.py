"""Isolated guards for the R191/R192 settlement-cash cloud projections."""

import ast
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
from pathlib import Path
import sys
import types

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_delta_order_package as delta
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_bridge_qc_projection as r182,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_tilt80_qc_projection as r186,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_settlement_qc_projection as subject,
)


PACKAGE_PATH = Path(
    "artifacts/analyst_revisions_v2/"
    "accepted_risk_delta_order_package_20260918_01/"
    "arv2-preliminary-qc-package-7803b84f0841f9685a4951de"
)
CHANGED = {
    "R191": {"accepted_risk_order_level_core.py",
             "accepted_risk_six_universe_order_bridge_qc_runtime.py", "main.py"},
    "R192": {"accepted_risk_order_level_core.py",
             "accepted_risk_six_universe_order_bridge_qc_runtime.py",
             "accepted_risk_six_universe_order_tilt_qc_runtime.py", "main.py"},
}


@pytest.fixture(scope="module")
def package():
    if not PACKAGE_PATH.is_dir():
        pytest.skip("local ignored exact delta package unavailable")
    return delta.load_accepted_risk_delta_order_package(
        PACKAGE_PATH,
        expected_package_sha256=delta.EXPECTED_DELTA_PACKAGE_SHA256,
        expected_lineage_sha256=delta.EXPECTED_DELTA_LINEAGE_SHA256,
    )


@pytest.mark.parametrize("candidate_id", ("R191", "R192"))
def test_exact_projection_changes_only_cash_runtime_and_entrypoint(package, candidate_id):
    old = (r182.build_accepted_risk_six_universe_order_bridge_qc_projection(
        package, role="matched") if candidate_id == "R191" else
        r186.build_accepted_risk_six_universe_order_tilt80_qc_projection(package))
    new = subject.build_settlement_projection(package, candidate_id)
    spec = subject.CANDIDATES[candidate_id]
    assert new.projection_sha256 == spec["projection_sha256"]
    assert new.profile_sha256 == spec["profile_sha256"]
    assert new.total_source_byte_count == spec["total_source_byte_count"]
    assert len(new.source_files) == spec["source_file_count"]
    assert new.role == old.role == spec["role"]
    assert new.variant == spec["variant"] != old.variant
    assert new.package_sha256 == old.package_sha256
    assert new.activation_manifest_sha256 == old.activation_manifest_sha256
    assert new.backtest_only is True and new.market_on_open_orders_only is True
    assert not any((new.live_orders, new.paper_orders, new.funded_orders,
                    new.deployment, new.trading))
    prior = {f.project_path: f.source_bytes for f in old.source_files}
    current = {f.project_path: f.source_bytes for f in new.source_files}
    assert set(current) == set(prior)
    assert {path for path in current if current[path] != prior[path]} == CHANGED[candidate_id]
    assert b"realized_borrowing_allowed" not in current[
        "accepted_risk_six_universe_order_bridge_qc_runtime.py"]
    assert b"order_event_cash_nonnegative" not in current[
        "accepted_risk_six_universe_order_bridge_qc_runtime.py"]
    assert b"negative_cash_requires_pending_sell_moo" in current[
        "accepted_risk_six_universe_order_bridge_qc_runtime.py"]
    assert b"self.universe_settings.leverage = 2" in current["main.py"]
    assert subject.CANDIDATES[candidate_id]["variant"].encode() in current["main.py"]
    manifest = hashlib.sha256(subject._base._canonical(tuple(
        (f.project_path, f.content_sha256, f.byte_count)
        for f in new.source_files
    ))).hexdigest()
    assert manifest == spec["source_files_sha256"]
    assert new.total_source_byte_count + subject._base.MINIMUM_REVIEW_MARGIN_BYTES <= (
        subject._base.MAXIMUM_TOTAL_SOURCE_BYTES
    )
    for f in new.source_files:
        text = f.source_bytes.decode("ascii")
        assert not any(isinstance(node, ast.ImportFrom) and node.module == "__future__"
                       for node in ast.walk(ast.parse(text)))
        compile("from AlgorithmImports import *\n" + text, f.project_path, "exec")


def test_profiles_version_transient_cash_honestly_and_bind_new_matched_baseline():
    matched = subject.require_settlement_profile("R191")
    tilt = subject.require_settlement_profile("R192")
    for profile in (matched, tilt):
        assert "realized_borrowing_allowed" not in profile
        assert profile["transient_pending_sell_cash_deficit_allowed"] is True
        assert profile["settled_cash_nonnegative_required"] is True
        assert profile["event_cash_policy_id"] == subject.SETTLEMENT_POLICY_ID
        assert "pending_sell_only_negative_event_cash" in profile["execution_validity_rule"]
    assert tilt["matched_baseline_profile_sha256"] == matched["profile_sha256"]
    assert tilt["maximum_stock_weight_change_fraction"] == "0.80"


def test_projected_cloud_runtime_profiles_equal_exact_host_pins(package, monkeypatch):
    from research.analyst_revisions_v2_qc import (
        accepted_risk_six_universe_order_qc_runtime as base_runtime,
        accepted_risk_six_universe_order_targets as base_targets,
    )
    files = {f.project_path: f.source_bytes for f in
             subject.build_settlement_projection(package, "R192").source_files}
    monkeypatch.setitem(sys.modules, "accepted_risk_six_universe_order_qc_runtime",
                        base_runtime)
    monkeypatch.setitem(sys.modules, "accepted_risk_six_universe_order_targets",
                        base_targets)
    bridge = types.ModuleType("accepted_risk_six_universe_order_bridge_qc_runtime")
    monkeypatch.setitem(sys.modules, bridge.__name__, bridge)
    exec(compile(files[bridge.__name__ + ".py"], bridge.__name__, "exec"),
         bridge.__dict__)
    assert bridge.require_bridge_profile("matched") == (
        subject.require_settlement_profile("R191")
    )
    targets = types.ModuleType("accepted_risk_six_universe_order_tilt_targets")
    monkeypatch.setitem(sys.modules, targets.__name__, targets)
    exec(compile(files[targets.__name__ + ".py"], targets.__name__, "exec"),
         targets.__dict__)
    tilt = types.ModuleType("accepted_risk_six_universe_order_tilt_qc_runtime")
    monkeypatch.setitem(sys.modules, tilt.__name__, tilt)
    exec(compile(files[tilt.__name__ + ".py"], tilt.__name__, "exec"),
         tilt.__dict__)
    assert tilt.require_tilt_profile() == subject.require_settlement_profile("R192")


def test_projection_refuses_predecessor_and_exact_pin_drift(package, monkeypatch):
    monkeypatch.setitem(subject._PREDECESSOR, "R191", ("0" * 64, *subject._PREDECESSOR["R191"][1:]))
    with pytest.raises(subject.SixUniverseSettlementQcProjectionError):
        subject.build_settlement_projection(package, "R191")
    monkeypatch.undo()
    monkeypatch.setitem(subject.CANDIDATES["R192"], "projection_sha256", "0" * 64)
    with pytest.raises(subject.SixUniverseSettlementQcProjectionError):
        subject.build_settlement_projection(package, "R192")


def _projected_module(package, project_path, *, candidate_id="R191", name=None):
    projection = subject.build_settlement_projection(package, candidate_id)
    source = next(f.source_bytes for f in projection.source_files
                  if f.project_path == project_path)
    module = types.ModuleType(name or "arv2_projected_" + project_path.removesuffix(".py"))
    sys.modules[module.__name__] = module
    exec(compile(source, project_path, "exec"), module.__dict__)
    return module


def _event(core, intent, event_id, *, price=None):
    fill_price = intent.reference_price if price is None else price
    fee = Decimal(intent.quantity) * fill_price * core.MODELED_FEE_RATE_PER_SIDE
    return core.FillEvent(event_id, intent.rebalance_id, intent.client_order_id,
                          core.FILLED, intent.quantity, fill_price, fee, "USD")


def test_projected_core_allows_only_pending_sell_funded_prefix_and_refuses_unsettled(package):
    core = _projected_module(package, "accepted_risk_order_level_core.py")
    plan = core.plan_rebalance(
        rebalance_id="rebalance-2026-01-05", starting_cash=Decimal("2000"),
        current_quantities={"TICKER_ALPHA_RAW": 100},
        reference_prices={"TICKER_ALPHA_RAW": Decimal("100"),
                          "TICKER_BETA_RAW": Decimal("50")},
        target_weights={"TICKER_ALPHA_RAW": Decimal("0.49"),
                        "TICKER_BETA_RAW": Decimal("0.49")},
    )
    sell, buy = plan.intents
    assert (sell.side, buy.side) == (core.SELL, core.BUY)
    # Buy fills before the pending sell. The signed interim cash is negative,
    # but the same rebalance's later sell settles it above zero.
    summary = core.summarize_order_lifecycle(
        plan, (_event(core, buy, "event-buy"), _event(core, sell, "event-sell"))
    )
    assert summary.final_cash > 0
    # The frozen predecessor refused this same buy-first path. This is the
    # behavioral red control, not a source-string assertion.
    from research.analyst_revisions_v2_qc import accepted_risk_order_level_core as frozen
    frozen_plan = frozen.plan_rebalance(
        rebalance_id="rebalance-2026-01-05", starting_cash=Decimal("2000"),
        current_quantities={"TICKER_ALPHA_RAW": 100},
        reference_prices={"TICKER_ALPHA_RAW": Decimal("100"),
                          "TICKER_BETA_RAW": Decimal("50")},
        target_weights={"TICKER_ALPHA_RAW": Decimal("0.49"),
                        "TICKER_BETA_RAW": Decimal("0.49")},
    )
    old_sell, old_buy = frozen_plan.intents
    with pytest.raises(frozen.OrderLevelBacktestError, match="margin"):
        frozen.summarize_order_lifecycle(
            frozen_plan, (_event(frozen, old_buy, "event-buy"),
                          _event(frozen, old_sell, "event-sell"))
        )
    # A larger buy cannot be rescued by the later sell: final settled cash
    # remains negative and must refuse despite the pending-sell allowance.
    with pytest.raises(core.OrderLevelBacktestError, match="margin"):
        core.summarize_order_lifecycle(
            plan, (_event(core, buy, "event-buy-2", price=Decimal("60")),
                   _event(core, sell, "event-sell-2"))
        )
    # If the pending-sell prefix guard were disabled, the next forged event
    # would produce UNKNOWN_ORDER instead; the margin refusal is immediate.
    forged = core.FillEvent("event-forged", plan.rebalance_id, "0" * 64,
                            core.FILLED, 1, Decimal("1"), Decimal("0.001"), "USD")
    with pytest.raises(core.OrderLevelBacktestError, match="filled buy would require margin"):
        core.summarize_order_lifecycle(
            plan, (_event(core, sell, "event-sell-first"),
                   _event(core, buy, "event-buy-too-large", price=Decimal("60")),
                   forged)
        )


def test_projected_event_cash_requires_open_sell_moo_in_same_session(package):
    bridge = _projected_module(package,
        "accepted_risk_six_universe_order_bridge_qc_runtime.py",
        name="arv2_projected_settlement_bridge_test")

    class Base:
        def on_order_event(self, _event):
            return "accepted"

    class Driver(bridge.BridgeAdmissionMixin, Base):
        def _require_initialized(self):
            return None

    session = datetime(2025, 8, 4, 9, 31)
    open_orders = [types.SimpleNamespace(id=17)]
    driver = Driver()
    driver._algorithm = types.SimpleNamespace(
        portfolio=types.SimpleNamespace(cash=Decimal("-12.5")),
        transactions=types.SimpleNamespace(get_open_orders=lambda: open_orders),
        time=session,
    )
    driver._executor = types.SimpleNamespace(_status_text=lambda status: status)
    driver._bridge_sell_moo_ids = {17: session.date()}
    driver._bridge_event_cash_count = 0
    driver._bridge_event_cash_minimum = None
    driver._bridge_negative_event_count = 0
    driver._bridge_unexplained_negative_count = 0
    ordinary_event = types.SimpleNamespace(order_id=99, status="Submitted")
    assert driver.on_order_event(ordinary_event) == "accepted"
    assert driver._bridge_negative_event_count == 1
    assert driver._bridge_event_cash_minimum == Decimal("-12.5")

    for sell_ids, orders, cash, event, refusal in (
        ({}, [types.SimpleNamespace(id=17)], Decimal("-1"),
         ordinary_event,
         "bridge negative cash has no pending SELL MOO"),  # pending BUY only
        ({17: session.date() - timedelta(days=1)}, [types.SimpleNamespace(id=17)],
         Decimal("-1"), ordinary_event,
         "bridge negative cash has no pending SELL MOO"),
        ({17: session.date()}, [], Decimal("-1"),
         ordinary_event, "bridge negative cash has no pending SELL MOO"),
        ({17: session.date()}, [types.SimpleNamespace(id=17)], Decimal("-1"),
         types.SimpleNamespace(order_id=17, status="Filled"),
         "bridge negative cash has no pending SELL MOO"),  # stale open inventory
        ({17: session.date()}, [types.SimpleNamespace(id=17)], Decimal("NaN"),
         ordinary_event, "bridge signed order-event cash is outside its finite bound"),
        ({17: session.date()}, [types.SimpleNamespace(id=17)], Decimal("Infinity"),
         ordinary_event, "bridge signed order-event cash is outside its finite bound"),
    ):
        driver._bridge_sell_moo_ids = sell_ids
        open_orders[:] = orders
        driver._algorithm.portfolio.cash = cash
        with pytest.raises(bridge._base.AcceptedRiskSixUniverseOrderQcRuntimeError,
                           match=refusal):
            driver.on_order_event(event)
    # Positive event cash never borrows the pending-sell exception.
    driver._bridge_sell_moo_ids = {}
    driver._algorithm.portfolio.cash = Decimal("1")
    assert driver.on_order_event(ordinary_event) == "accepted"
