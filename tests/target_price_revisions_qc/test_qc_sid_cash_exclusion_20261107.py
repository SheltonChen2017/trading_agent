"""Synthetic supplied-value and native-adapter fixtures; no market evidence.

Only this fixture substitutes a synthetic SID digest. Production computes the
fixed exclusion from canonical typed native SecurityIdentifiers inside QC.
"""
import ast
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from fractions import Fraction
import hashlib
import inspect
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from research.target_price_revisions_qc import comparison_20261028 as construction
from research.target_price_revisions_qc import sid_cash_exclusion_20261107 as mask
from tests.target_price_revisions_qc import test_qc_comparison_20261028_algorithm as off_tests
from tests.target_price_revisions_qc import test_qc_comparison_20261028_multi_algorithm as multi_tests

ARMS = ("cap_off", "cap_tilt_50", "cap_tilt_100", "cap_tilt_200", "pure_tpr")
SYNTHETIC_EXCLUDED = "SYNTHETIC-EXCLUDED"


def build(arm, *, role="receiver", overlap=False, absent=False):
    members = {sleeve: [] for sleeve in construction.SLEEVES}
    labels = construction.SLEEVES if overlap else ("SPY",)
    caps, scores = {}, {}
    for sleeve in labels:
        ids = ["KEEP-" + sleeve, SYNTHETIC_EXCLUDED]
        if absent:
            ids[1] = "ANOTHER-" + sleeve
        members[sleeve] = [{"sid": sid, "ticker": sid} for sid in ids]
        caps.update({sid: str(100 - index) for index, sid in enumerate(ids)})
        scores[ids[0]] = "-1" if role == "receiver" else "1"
        scores[ids[1]] = "1" if role == "receiver" else "-1" if role == "donor" else "0"
    finance = {row["sid"]: "noninsurance" for row in members["XLF"]}
    if arm == "cap_off":
        return construction.construct_off(members, caps, finance_insurance_by_sid=finance)
    if arm == "pure_tpr":
        return construction.construct_pure_tpr(members, scores, finance_insurance_by_sid=finance)
    return construction.construct_tilt(members, caps, scores, arm=arm, finance_insurance_by_sid=finance)


def plan(weights, report):
    digests = {sid: (mask.EXCLUDED_SID_SHA256 if sid == SYNTHETIC_EXCLUDED
                    else hashlib.sha256(sid.encode("ascii")).hexdigest()) for sid in weights}
    return mask.plan_cash_exclusion(weights, report, digests)


@pytest.mark.parametrize("arm", ARMS)
@pytest.mark.parametrize("role", ("receiver", "donor", "neutral"))
@pytest.mark.parametrize("overlap", (False, True))
def test_all_five_constructors_freeze_then_remove_only_fixed_digest(arm, role, overlap):
    weights, report = build(arm, role=role, overlap=overlap)
    before_weights, before_report = deepcopy(weights), deepcopy(report)
    after, audit = plan(weights, report)
    assert weights == before_weights and report == before_report
    assert after == {sid: value for sid, value in weights.items() if sid != SYNTHETIC_EXCLUDED}
    assert SYNTHETIC_EXCLUDED not in after
    assert audit["removed_final_weight"] == weights[SYNTHETIC_EXCLUDED]
    assert audit["cash_increment"] == sum(
        row["removed_final_weight"] for row in audit["per_sleeve"].values())
    assert audit["execution_gross_weight"] + audit["execution_cash_weight"] == 1
    assert audit["execution_cash_weight"] == report["cash_weight"] + weights[SYNTHETIC_EXCLUDED]
    assert audit["masked_selected_slot_occurrences"] == (6 if overlap else 1)
    assert audit["frozen_selected_slot_count"] == report["selected_slot_count"]
    for sleeve, row in audit["per_sleeve"].items():
        assert row["execution_weights"] == {
            sid: value for sid, value in report["per_sleeve"][sleeve]["target_weights"].items()
            if sid != SYNTHETIC_EXCLUDED}
        assert row["execution_gross_weight"] + row["execution_cash_weight"] == Fraction(1, 6)
    assert audit["supplied_digests_are_native_authority"] is False
    assert audit["orders_or_fills_identical_to_parent"] is False
    assert not any(audit[field] for field in ("redistribution", "refill", "reranking", "source_inputs_admitted", "strategy_accepted"))


@pytest.mark.parametrize("arm", ARMS)
def test_absent_name_keeps_every_weight_and_cash(arm):
    weights, report = build(arm, absent=True)
    after, audit = plan(weights, report)
    assert after == weights and audit["cash_increment"] == 0
    assert audit["masked_unique_target_count"] == audit["masked_selected_slot_occurrences"] == 0


def test_zero_donor_removed_from_execution_keys_with_zero_cash_increment():
    weights, report = build("cap_tilt_200", role="donor")
    assert weights[SYNTHETIC_EXCLUDED] == 0
    after, audit = plan(weights, report)
    assert SYNTHETIC_EXCLUDED not in after
    assert audit["cash_increment"] == 0 and audit["masked_selected_slot_occurrences"] == 1
    assert report["per_sleeve"]["SPY"]["recipient_underfill"] > 0


def test_aggregate_headroom_and_rank11_stay_frozen_after_mask():
    rows = {sleeve: [{"sid": SYNTHETIC_EXCLUDED, "ticker": "EXCLUDED"},
                    *({"sid": sleeve + str(n), "ticker": sleeve + str(n)} for n in range(11))]
            for sleeve in construction.SLEEVES}
    caps = {row["sid"]: str(100 - index) for members in rows.values() for index, row in enumerate(members)}
    scores = {sid: "8" if sid == SYNTHETIC_EXCLUDED else "-1" for sid in caps}
    weights, report = construction.construct_tilt(rows, caps, scores, arm="cap_tilt_200",
        finance_insurance_by_sid={row["sid"]: "noninsurance" for row in rows["XLF"]})
    before = deepcopy(report)
    after, audit = plan(weights, report)
    assert weights[SYNTHETIC_EXCLUDED] == Fraction(1, 10)
    assert audit["cash_increment"] == Fraction(1, 10)
    assert report == before
    for sleeve in construction.SLEEVES:
        assert sleeve + "9" not in after and sleeve + "10" not in after
        assert report["per_sleeve"][sleeve]["aggregate_cap_blocked_capacity"] > 0
        assert report["per_sleeve"][sleeve]["executable_ids"] == before["per_sleeve"][sleeve]["executable_ids"]


@pytest.mark.parametrize("mutate", (
    lambda weights, report, digests: weights.update({SYNTHETIC_EXCLUDED: -Fraction(1, 60)}),
    lambda weights, report, digests: weights.update({SYNTHETIC_EXCLUDED: 0.01}),
    lambda weights, report, digests: report.update(cash_weight=Fraction(0)),
    lambda weights, report, digests: report.update(selected_slot_count=0),
    lambda weights, report, digests: report["per_sleeve"]["SPY"].update(target_weight=Fraction(1)),
    lambda weights, report, digests: digests.update({"EXTRA": "a" * 64}),
    lambda weights, report, digests: digests.update({"KEEP-SPY": mask.EXCLUDED_SID_SHA256}),
))
def test_supplied_plan_refuses_corrupt_reconciliation(mutate):
    weights, report = build("cap_off")
    digests = {sid: mask.EXCLUDED_SID_SHA256 if sid == SYNTHETIC_EXCLUDED else "a" * 64 for sid in weights}
    mutate(weights, report, digests)
    with pytest.raises(mask.CashExclusionRefusal):
        mask.plan_cash_exclusion(weights, report, digests)


@pytest.mark.parametrize("value,expected", (
    (0.0, True), (-0.0, True), (0, True), (Fraction(0), True), (Decimal("0.000"), True),
    ("0", True), (1e-300, False), (Decimal("1e-999"), False),
    (Fraction(1, 10**999), False), (float("nan"), False), (float("inf"), False),
    (Decimal("NaN"), False), (Decimal("Infinity"), False), (True, False), (False, False), (None, False),
))
def test_exact_finite_native_zero_without_epsilon_or_nonzero_float_conversion(value, expected):
    assert mask._sid_cash_zero(value) is expected


@pytest.fixture
def driver(monkeypatch):
    module = multi_tests.driver.__wrapped__(monkeypatch)
    native = sys.modules["AlgorithmImports"]
    monkeypatch.setattr(off_tests.Sid, "parse", classmethod(lambda cls, value: cls(value)), raising=False)
    native.SecurityIdentifier = off_tests.Sid
    native.Symbol = off_tests.Symbol

    class Order:
        def __init__(self, symbol):
            self.symbol = symbol

    class OrderEvent:
        def __init__(self, symbol, quantity=0):
            self.symbol, self.fill_quantity = symbol, quantity

    class Slice:
        def __init__(self, actions=False):
            self.splits = {"synthetic": object()} if actions else {}
            self.dividends, self.delistings = {}, {}

    native.Order, native.OrderEvent, native.Slice = Order, OrderEvent, Slice

    class OrderStatus(Enum):
        NEW = "New"
        SUBMITTED = "Submitted"
        PARTIALLY_FILLED = "PartiallyFilled"
        FILLED = "Filled"
        CANCELED = "Canceled"
        INVALID = "Invalid"

    class OrderType(Enum):
        MARKET_ON_OPEN = "MarketOnOpen"
        MARKET = "Market"

    class OrderTicket:
        pass

    native.OrderStatus, native.OrderType, native.OrderTicket = OrderStatus, OrderType, OrderTicket
    native.Currencies = NS(NullCurrency="")
    original_digest = mask._sid_cash_text_digest

    def synthetic_digest(sid):
        actual = original_digest(sid)
        return mask.EXCLUDED_SID_SHA256 if sid in (SYNTHETIC_EXCLUDED, "SID-SPY") else actual

    monkeypatch.setattr(mask, "_sid_cash_text_digest", synthetic_digest)
    module.native = native
    return module


def adapter(driver, arm="cap_off"):
    original = off_tests.minimal(driver.previous) if arm == "cap_off" else multi_tests.minimal(driver, arm)
    base = driver.previous.ComparisonOffAlgorithm if arm == "cap_off" else driver.ComparisonMultiAlgorithm

    class NativeSubmission:
        def market_on_open_order(self, symbol, quantity, *args, **kwargs):
            self.actual_orders.append((str(symbol.id), quantity, args, kwargs))
            return NS(order_id=len(self.actual_orders))

    class Algorithm(mask.CashExclusionMixin, NativeSubmission, base):
        pass

    algo = Algorithm()
    algo.__dict__.update(original.__dict__)
    algo._config = {**algo._config, "study_id": mask.STUDY_ID}
    algo.live_mode = False
    algo._sid_cash_state = {"guard_calls": 0, "masked_decisions": 0,
        "masked_slot_occurrences": 0, "blocked_submission_attempts": 0,
        "excluded_submitted_orders": 0, "excluded_fill_events": 0, "initializing": False}
    algo._quantity_ledger, algo._ever_filled_ids, algo._fill_history_unknown = {}, set(), False
    algo.held, algo.open_orders, algo.history, algo.actual_orders = [], [], [], []
    algo.portfolio = NS(cash="100000", values=lambda: list(algo.held))
    algo.transactions = NS(get_orders=lambda: list(algo.history), get_open_orders=lambda: list(algo.open_orders))
    if arm == "cap_off":
        algo._evidence = NS(require_binding=lambda: None)
    else:
        # Preserve the actual signal custody guard. Rebind its exact config
        # bytes and digest after this synthetic fixture adopts the new study.
        digest = hashlib.sha256(driver._wire(algo._config)).hexdigest()
        driver.EXPECTED_CONFIG_SHA256 = digest
        algo._evidence = driver.MultiJournal(algo._config, digest,
            lambda: (algo.project_id, algo.algorithm_id, algo.get_locked()))
    algo._attempted_days = set()
    algo._decision_count = algo._refused_count = 0
    algo._assert_clock_subscription = lambda: None
    algo._prior_close_nav, algo._prior_close_day = Fraction(100000), None
    algo._assert_raw_subscriptions = lambda symbol: None
    algo._requested_shares = algo._submitted_shares = algo._submitted = 0
    algo._tickets = []
    return algo


@pytest.mark.parametrize("arm", ARMS)
def test_actual_five_arm_prepare_and_rebalance_never_request_excluded_prior_mark(driver, arm):
    algo = adapter(driver, arm)
    day = off_tests.supplied_inputs(driver.previous, algo)
    called = []

    def mark(symbol):
        sid = str(symbol.id)
        assert sid != "SID-SPY", "excluded price lookup must never occur"
        called.append(sid)
        return Fraction(100), Fraction(10000)

    algo._prior_mark = mark
    algo._rebalance()
    assert "SID-SPY" not in algo._targets and "SID-SPY" not in algo._target_weights
    assert set(called) == {"SID-" + sleeve for sleeve in construction.SLEEVES if sleeve != "SPY"}
    assert len(algo.actual_orders) == 5
    coverage = algo._decision_coverage[day]
    assert "SID-SPY" in coverage["construction"]["per_sleeve"]["SPY"]["executable_ids"]
    assert coverage["construction"]["selected_slot_count"] == 6
    assert coverage["execution_mask"]["execution_slot_count"] == 5
    assert coverage["execution_mask"]["cash_increment"] == Fraction(1, 60)
    assert coverage["coverage_semantics"]["construction_sleeves_target_gross_unallocated_target_cash"] == "frozen_pre_mask_construction"
    assert coverage["coverage_semantics"]["prior_mark_inputs_sha256"] == "remaining_execution_targets"
    audits = [row for kind, row in algo._records if kind == "COVERAGE" and row.get("kind") == "sid_cash_exclusion_execution_mask"]
    assert len(audits) == 1 and audits[0]["session"] == day
    assert not any("price" in key or "mark" in key for key in audits[0])
    assert algo._symbols["SID-SPY"] is not None and "SID-SPY" in algo._ever_targeted_ids
    assert algo._warning_ids == algo._delisted_ids == set()


def test_actual_zero_weight_donor_removed_from_both_maps_before_mark_iteration(driver):
    algo = adapter(driver, "cap_tilt_200")
    day = off_tests.supplied_inputs(driver.previous, algo)
    symbol = off_tests.Symbol("SYNTHETIC-HIGH")
    algo._snapshots["SPY"][0]["members"].append({"symbol": symbol, "ticker": symbol.value})
    algo._cap_snapshots[0]["caps"][str(symbol.id)] = {"state": "available", "value": "999"}
    algo._signal_provider = multi_tests.Provider({"SID-SPY": {"state": "available", "value": "-1"},
        "SYNTHETIC-HIGH": {"state": "available", "value": "1"}})
    algo._prepare_targets(day)
    assert algo._decision_coverage[day]["construction"]["per_sleeve"]["SPY"]["target_weights"]["SID-SPY"] == 0
    assert "SID-SPY" not in algo._targets and "SID-SPY" not in algo._target_weights
    assert algo._decision_coverage[day]["execution_mask"]["cash_increment"] == 0


def test_other_missing_held_mark_still_refuses_without_excluded_lookup(driver):
    algo = adapter(driver)
    off_tests.supplied_inputs(driver.previous, algo)
    symbol = off_tests.Symbol("SID-XLE")
    algo.held = [NS(symbol=symbol, quantity=1, invested=True)]
    algo._quantity_ledger = {str(symbol.id): Fraction(1)}

    def mark(item):
        assert str(item.id) != "SID-SPY"
        return None if str(item.id) == "SID-XLE" else (Fraction(100), Fraction(10000))

    algo._prior_mark = mark
    algo._rebalance()
    assert algo._reasons["unpriced_held_nav"] == 1
    assert algo._refused_count == 1 and not algo.actual_orders


@pytest.mark.parametrize("state", ("unknown_holding", "invested_false_nonzero", "ledger", "open_order", "history", "fill_census", "unknown_history"))
def test_unknown_excluded_exposure_and_order_history_fail_closed(driver, state):
    algo = adapter(driver)
    symbol = off_tests.Symbol(SYNTHETIC_EXCLUDED)
    if state in ("unknown_holding", "invested_false_nonzero"):
        algo.held = [NS(symbol=symbol, quantity=Fraction(1), invested=state == "unknown_holding")]
        assert str(symbol.id) not in algo._symbols
    elif state == "ledger":
        algo._quantity_ledger = {str(symbol.id): Fraction(1)}
    elif state == "open_order":
        algo.open_orders = [driver.native.Order(symbol)]
    elif state == "history":
        algo.history = [driver.native.Order(symbol)]
    elif state == "fill_census":
        algo._ever_filled_ids = {str(symbol.id)}
    else:
        algo._fill_history_unknown = True
    before = deepcopy(algo._quantity_ledger)
    with pytest.raises(mask.CashExclusionRefusal):
        algo._sid_cash_guard("synthetic", history=True)
    assert algo._quantity_ledger == before and not algo.actual_orders


@pytest.mark.parametrize("quantity", (1, -1, 0, 0.0))
def test_submission_boundary_rejects_any_excluded_moo_even_zero(driver, quantity):
    algo = adapter(driver)
    with pytest.raises(mask.CashExclusionRefusal):
        algo.market_on_open_order(off_tests.Symbol(SYNTHETIC_EXCLUDED), quantity)
    assert not algo.actual_orders and algo._sid_cash_state["blocked_submission_attempts"] == 1


@pytest.mark.parametrize("quantity", (1, -1, 0))
def test_excluded_order_event_never_reaches_parent_accounting(driver, quantity):
    algo = adapter(driver)
    event = driver.native.OrderEvent(off_tests.Symbol(SYNTHETIC_EXCLUDED), quantity)
    before = deepcopy(algo._quantity_ledger)
    with pytest.raises(mask.CashExclusionRefusal):
        algo.on_order_event(event)
    assert algo._quantity_ledger == before and not algo._ever_filled_ids


def test_native_float_zero_holding_is_allowed_without_requiring_its_mark(driver):
    algo = adapter(driver)
    algo.held = [NS(symbol=off_tests.Symbol(SYNTHETIC_EXCLUDED), quantity=0.0, invested=False)]
    algo._quantity_ledger = {SYNTHETIC_EXCLUDED: Fraction(0)}
    algo._sid_cash_guard("synthetic", history=True)


def test_typed_canonical_identity_and_wrong_variant_cannot_be_asserted_by_caller(driver, monkeypatch):
    algo = adapter(driver)
    native = driver.native
    with pytest.raises(mask.CashExclusionRefusal):
        algo._sid_cash_digest_symbol(NS(id=off_tests.Sid("X")), native)
    monkeypatch.setattr(off_tests.Sid, "parse", classmethod(lambda cls, value: cls("DIFFERENT")))
    with pytest.raises(mask.CashExclusionRefusal):
        algo._sid_cash_digest_symbol(off_tests.Symbol("X"), native)
    algo._config["study_id"] = mask.PARENT_STUDY_ID
    with pytest.raises(mask.CashExclusionRefusal):
        algo._sid_cash_context()


def test_fixed_hash_uses_ascii_and_public_planner_has_no_exclusion_override():
    assert mask.EXCLUDED_SID_SHA256 == "1122fa5f1349f79e231e106127c098da27ef730836a97052d2154ecc46f1afc1"
    assert mask._sid_cash_text_digest("SYNTHETIC-NOT-EXCLUDED") == hashlib.sha256(b"SYNTHETIC-NOT-EXCLUDED").hexdigest()
    assert tuple(inspect.signature(mask.plan_cash_exclusion).parameters) == ("weights", "construction", "sid_sha256_by_id")
    for value in ("", " bad", "bad\n", "nonascii-\u2603"):
        with pytest.raises(mask.CashExclusionRefusal):
            mask._sid_cash_text_digest(value)


def test_initialization_and_end_census_run_before_parent_journal_export(driver):
    native = driver.native

    class Parent(native.QCAlgorithm):
        def initialize(self):
            self.live_mode = False
            self.project_id = 123
            self._config = {"study_id": mask.STUDY_ID, "arm": "cap_off", "project_id": 123}
            self.get_locked = lambda: False
            self._evidence = NS(require_binding=lambda: (_ for _ in ()).throw(AssertionError("not locked during init")))
            self.portfolio = NS(values=lambda: [])
            self._quantity_ledger, self._ever_filled_ids, self._fill_history_unknown = {}, set(), False
            self.transactions = NS(get_orders=lambda: [], get_open_orders=lambda: [])
            self.records = []

        def _log_audit(self, kind, row):
            self.records.append((kind, row))

        def on_end_of_algorithm(self):
            assert self.records[-1][1]["kind"] == "sid_cash_exclusion_census"
            self.exported = True
            return "parent-export"

    class Algorithm(mask.CashExclusionMixin, Parent):
        pass

    algo = Algorithm()
    algo.initialize()
    assert algo._sid_cash_state["initializing"] is False
    assert algo._sid_cash_state["guard_calls"] == 1
    algo.get_locked = lambda: True
    algo.algorithm_id = "c" * 32
    algo._config.update(candidate_id=mask.STUDY_ID + "-OFF", operation_id="SYNTHETIC-CENSUS-001",
        attempt=1, policy_sha256="a" * 64, calendar_sha256="b" * 64,
        source_template_closure_sha256="d" * 64, prior_attempts_looks_sha256="e" * 64)
    raw = mask._sid_cash_wire(algo._config)
    digest = hashlib.sha256(raw).hexdigest()
    prefix = f"tpr-cmp28/evidence/{mask.STUDY_ID}/SYNTHETIC/{digest}/attempt-1/123/{algo.algorithm_id}/"
    algo._evidence = NS(require_binding=lambda: prefix, _config_raw=raw, _config_hash=digest)
    algo.time = algo.utc_time = datetime(2026, 10, 9, 20, 1, tzinfo=timezone.utc)
    algo._native_clock = lambda value, _zone: value
    algo.portfolio.cash = algo.portfolio.total_portfolio_value = "100000"
    algo.portfolio.total_holdings_value = "0"
    algo.object_store = off_tests.NativeStore()
    assert algo.on_end_of_algorithm() == "parent-export" and algo.exported
    row = algo.records[-1][1]
    for key in ("excluded_native_quantity", "excluded_independent_quantity", "excluded_open_orders", "excluded_submitted_orders", "excluded_fill_events"):
        assert row[key] == 0
    assert row["checked_native_order_history"] is True
    assert row["excluded_security_id_sha256"] == mask.EXCLUDED_SID_SHA256


@pytest.mark.parametrize("hook", ("_rebalance", "_daily_audit", "on_end_of_algorithm"))
def test_pre_hook_guard_prevents_unexpected_excluded_holding_before_any_parent_mark(native_history, hook):
    algo = native_history.algo
    algo.held = [NS(symbol=off_tests.Symbol(SYNTHETIC_EXCLUDED), quantity=1, invested=True)]
    algo._prior_mark = lambda *_: (_ for _ in ()).throw(AssertionError("must fail before mark"))
    with pytest.raises(mask.CashExclusionRefusal):
        getattr(algo, hook)()


def test_action_parent_error_propagates_and_post_action_exposure_refuses(driver):
    native = driver.native

    class ActionParent:
        def on_data(self, data):
            self.action_calls += 1
            if self.action_error:
                raise RuntimeError("original action failed")
            self.held.append(NS(symbol=off_tests.Symbol(SYNTHETIC_EXCLUDED), quantity=1, invested=True))

    original = adapter(driver)
    class Algorithm(mask.CashExclusionMixin, ActionParent, native.QCAlgorithm):
        pass
    algo = Algorithm()
    algo.__dict__.update(original.__dict__)
    algo.action_calls, algo.action_error = 0, True
    with pytest.raises(RuntimeError, match="original action failed"):
        algo.on_data(native.Slice(actions=True))
    assert algo.action_calls == 1
    algo.action_error = False
    with pytest.raises(mask.CashExclusionRefusal):
        algo.on_data(native.Slice(actions=True))
    assert algo.action_calls == 2 and algo.held[0].quantity == 1


def test_inline_source_has_no_resource_global_collision_or_hidden_execution():
    source = Path(mask.__file__).read_text()
    tree = ast.parse(source)
    names = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    names.update(target.id for node in tree.body if isinstance(node, ast.Assign)
                 for target in node.targets if isinstance(target, ast.Name))
    assert not names & {"_fail", "_zero", "_sid", "_ids", "_native_types", "SCHEMA", "ACTIVE_ID_LIMIT", "MAX_CENSUS_IDS", "MAX_NATIVE_ORDERS"}
    assert "from __future__" not in source
    forbidden = {"exec", "eval", "compile", "open", "getattr_static", "getenv"}
    assert not {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)} & forbidden
    assert not {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} & {"os", "pathlib", "codecs", "gzip"}


@pytest.fixture
def native_history(driver):
    """Public stubs, not an assertion about the deployed QC interface."""
    algo = adapter(driver)
    native = driver.native
    algo.algorithm_id = "c" * 32
    raw = mask._sid_cash_wire(algo._config)
    digest = hashlib.sha256(raw).hexdigest()
    prefix = f"tpr-cmp28/evidence/{mask.STUDY_ID}/SYNTHETIC/{digest}/attempt-1/{algo.project_id}/{algo.algorithm_id}/"
    algo._evidence = NS(require_binding=lambda: prefix, _config_raw=raw, _config_hash=digest)
    algo.utc_time = datetime(2026, 10, 9, 20, 1, tzinfo=timezone.utc)
    algo.time = algo.utc_time
    algo._native_clock = lambda value, _zone: value
    algo.portfolio.total_portfolio_value = "100000"
    algo.portfolio.total_holdings_value = "0"
    algo.object_store = off_tests.NativeStore()
    symbol = off_tests.Symbol("SYNTHETIC-OTHER")
    order = native.Order(symbol)
    order.id, order.type, order.status = 1, native.OrderType.MARKET_ON_OPEN, native.OrderStatus.FILLED
    order.quantity, order.price_currency, order.tag = "2", "USD", "TPRE:synthetic"
    order.time = datetime(2026, 10, 9, 13, 20, tzinfo=timezone.utc)
    submitted = native.OrderEvent(symbol, "0")
    submitted.id, submitted.order_id, submitted.status = 0, 1, native.OrderStatus.SUBMITTED
    submitted.utc_time = order.time
    submitted.fill_price, submitted.fill_price_currency = "0", None
    submitted.order_fee, submitted.is_assignment = NS(value=NS(amount="0", currency=None)), False
    filled = native.OrderEvent(symbol, "2")
    filled.id, filled.order_id, filled.status = 1, 1, native.OrderStatus.FILLED
    filled.utc_time = datetime(2026, 10, 9, 13, 30, tzinfo=timezone.utc)
    filled.fill_price, filled.fill_price_currency = "100", "USD"
    filled.order_fee, filled.is_assignment = NS(value=NS(amount="0.02", currency="USD")), False
    ticket = native.OrderTicket()
    ticket.order_id, ticket.symbol = 1, symbol
    ticket.quantity, ticket.quantity_filled, ticket.average_fill_price = "2", "2", "100"
    ticket.status, ticket.order_events = native.OrderStatus.FILLED, [submitted, filled]
    algo.history = [order]
    algo.census_calls = []

    def orders():
        assert algo.object_store.calls[-1][0] == "read", "claim must be saved and read back before native history"
        algo.census_calls.append("get_orders")
        return list(algo.history)

    def opened():
        assert algo.object_store.calls[-1][0] == "read"
        algo.census_calls.append("get_open_orders")
        return list(algo.open_orders)

    def get_ticket(order_id):
        assert order_id == 1
        algo.census_calls.append("get_order_ticket")
        return ticket

    algo.transactions = NS(get_orders=orders, get_open_orders=opened, get_order_ticket=get_ticket)
    return NS(algo=algo, native=native, order=order, ticket=ticket,
        submitted=submitted, filled=filled, prefix=prefix)


def history_rows(algo, kind):
    return [row for category, row in algo._records if category == "COVERAGE" and row.get("kind") == kind]


def test_native_history_claim_precedes_reads_and_counts_hashes_exact_full_rows(native_history):
    data = native_history
    algo = data.algo
    algo._sid_cash_native_history()
    claim_rows = history_rows(algo, "sid_cash_native_history_claim")
    orders = history_rows(algo, "sid_cash_native_order")
    events = history_rows(algo, "sid_cash_native_order_event")
    census = history_rows(algo, "sid_cash_native_history_census")
    assert len(claim_rows) == len(orders) == len(census) == 1 and len(events) == 2
    claim = claim_rows[0]
    key = data.prefix + "native-order-history-access.json"
    assert claim["claim_key"] == key
    raw = algo.object_store.values[key]
    assert len(raw) == claim["claim_bytes"] <= 4096
    assert hashlib.sha256(raw).hexdigest() == claim["claim_sha256"]
    body = json.loads(raw)
    assert body["spent_before_native_history_read"] is True
    assert body["native_history_passes"] == body["maximum_get_orders_calls"] == 2
    assert body["maximum_orders"] == 50000 and body["maximum_events"] == 250000
    assert body["order_submission_calls"] == 0 and body["raw_identities_leave_qc"] is False
    assert body["backend_durability_proven"] is False
    assert algo.census_calls.count("get_orders") == 2
    assert algo.census_calls.count("get_order_ticket") == 2
    assert algo.census_calls.count("get_open_orders") == 4
    assert orders[0]["ticket_quantity_filled"] == sum(row["fill_quantity"] for row in events) == 2
    assert events[0]["fill_currency"] is None and events[0]["fee_currency"] is None
    summary = census[0]
    assert (summary["orders"], summary["events"], summary["nonzero_fills"], summary["open_orders"]) == (1, 2, 1, 0)
    assert summary["absolute_filled_shares"] == 2 and summary["reported_fees"] == Fraction(1, 50)
    assert summary["order_rows_sha256"] == hashlib.sha256(mask.SID_CASH_ORDER_CHAIN_DOMAIN +
        b"".join(mask._sid_cash_wire(row) + b"\n" for row in orders)).hexdigest()
    assert summary["event_rows_sha256"] == hashlib.sha256(mask.SID_CASH_EVENT_CHAIN_DOMAIN +
        b"".join(mask._sid_cash_wire(row) + b"\n" for row in events)).hexdigest()
    assert summary["stable_second_capture"] is summary["known_history"] is True
    assert summary["claim_same_node_verified"] is True and summary["backend_durability_proven"] is False


def test_native_partial_fill_then_cancel_preserves_full_event_history(native_history):
    data = native_history
    data.order.status = data.ticket.status = data.native.OrderStatus.CANCELED
    data.order.quantity = data.ticket.quantity = "3"
    data.filled.status = data.native.OrderStatus.PARTIALLY_FILLED
    canceled = data.native.OrderEvent(data.order.symbol, "0")
    canceled.__dict__.update(data.submitted.__dict__)
    canceled.id, canceled.status, canceled.utc_time = 2, data.native.OrderStatus.CANCELED, data.filled.utc_time
    canceled.fill_price_currency, canceled.order_fee = "", NS(value=NS(amount="0", currency=""))
    data.ticket.order_events.append(canceled)
    data.algo._sid_cash_native_history()
    rows = history_rows(data.algo, "sid_cash_native_order_event")
    assert [row["status"] for row in rows] == ["Submitted", "PartiallyFilled", "Canceled"]
    assert rows[-1]["fill_currency"] == rows[-1]["fee_currency"] == ""
    assert history_rows(data.algo, "sid_cash_native_history_census")[0]["events"] == 3


@pytest.mark.parametrize("mutation", (
    "missing_ticket", "untyped_ticket", "untyped_event", "duplicate_event_id", "wrong_event_order", "wrong_event_symbol",
    "future_event", "backward_event", "unknown_status", "unknown_order_type", "assignment", "ticket_fill_mismatch",
    "ticket_quantity_mismatch", "average_price_outside_fills", "nonfill_status_with_fill", "negative_price", "zero_fill_price", "negative_fee", "unknown_fill_currency",
    "unknown_fee_currency", "fractional_fill", "float_fractional_fill", "float_nonfinite_price", "nonfinite_fill", "duplicate_order_id", "open_order", "excluded_order",
))
def test_native_history_unknown_or_inconsistent_fields_refuse_no_final_census(native_history, mutation):
    data = native_history
    if mutation == "missing_ticket":
        data.algo.transactions.get_order_ticket = None
    elif mutation == "untyped_ticket":
        data.algo.transactions.get_order_ticket = lambda _id: NS(**data.ticket.__dict__)
    elif mutation == "untyped_event":
        data.ticket.order_events[1] = NS(**data.filled.__dict__)
    elif mutation == "duplicate_event_id":
        data.filled.id = data.submitted.id
    elif mutation == "wrong_event_order":
        data.filled.order_id = 2
    elif mutation == "wrong_event_symbol":
        data.filled.symbol = off_tests.Symbol("SYNTHETIC-FOREIGN")
    elif mutation == "future_event":
        data.filled.utc_time = datetime(2027, 1, 1, tzinfo=timezone.utc)
    elif mutation == "backward_event":
        data.filled.utc_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
    elif mutation == "unknown_status":
        data.filled.status = "Filled"
    elif mutation == "unknown_order_type":
        data.order.type = "MarketOnOpen"
    elif mutation == "assignment":
        data.filled.is_assignment = True
    elif mutation == "ticket_fill_mismatch":
        data.ticket.quantity_filled = "1"
    elif mutation == "ticket_quantity_mismatch":
        data.ticket.quantity = "1"
    elif mutation == "average_price_outside_fills":
        data.ticket.average_fill_price = "101"
    elif mutation == "nonfill_status_with_fill":
        data.filled.status = data.native.OrderStatus.SUBMITTED
    elif mutation == "negative_price":
        data.filled.fill_price = "-1"
    elif mutation == "zero_fill_price":
        data.filled.fill_price = "0"
    elif mutation == "negative_fee":
        data.filled.order_fee.value.amount = "-0.01"
    elif mutation == "unknown_fill_currency":
        data.filled.fill_price_currency = None
    elif mutation == "unknown_fee_currency":
        data.filled.order_fee.value.currency = None
    elif mutation == "fractional_fill":
        data.filled.fill_quantity = "1.5"
    elif mutation == "float_fractional_fill":
        data.filled.fill_quantity = 1.5
    elif mutation == "float_nonfinite_price":
        data.filled.fill_price = float("inf")
    elif mutation == "nonfinite_fill":
        data.filled.fill_quantity = "NaN"
    elif mutation == "duplicate_order_id":
        data.algo.history.append(data.order)
    elif mutation == "open_order":
        data.algo.open_orders = [data.order]
    else:
        data.order.symbol = off_tests.Symbol(SYNTHETIC_EXCLUDED)
    with pytest.raises((mask.CashExclusionRefusal, ValueError, TypeError)):
        data.algo._sid_cash_native_history()
    assert not history_rows(data.algo, "sid_cash_native_history_census")
    assert not data.algo.actual_orders


@pytest.mark.parametrize("failure", ("exists", "save_false", "readback_wrong", "clock_changes", "config_changes"))
def test_native_history_access_failure_refuses_before_first_order_read(native_history, failure):
    data = native_history
    algo = data.algo
    if failure == "exists":
        algo.object_store.values[data.prefix + "native-order-history-access.json"] = b"existing"
    elif failure == "save_false":
        algo.object_store.save_bytes = lambda *_: False
    elif failure == "readback_wrong":
        algo.object_store.read_bytes = lambda key: b"wrong"
    elif failure == "clock_changes":
        def exists(_key):
            algo.utc_time = datetime(2027, 1, 1, tzinfo=timezone.utc)
            return False
        algo.object_store.contains_key = exists
    else:
        def exists(_key):
            algo._config["policy_sha256"] = "f" * 64
            return False
        algo.object_store.contains_key = exists
    with pytest.raises(mask.CashExclusionRefusal):
        algo._sid_cash_native_history()
    assert not algo.census_calls
    assert not history_rows(algo, "sid_cash_native_history_census")
    with pytest.raises(mask.CashExclusionRefusal):
        algo._sid_cash_native_history()


def test_changed_second_native_history_capture_refuses_after_retaining_first_rows(native_history):
    data = native_history
    original = data.algo.transactions.get_orders
    def changing():
        orders = original()
        if data.algo.census_calls.count("get_orders") == 2:
            data.filled.fill_price = "101"
        return orders
    data.algo.transactions.get_orders = changing
    with pytest.raises(mask.CashExclusionRefusal):
        data.algo._sid_cash_native_history()
    assert len(history_rows(data.algo, "sid_cash_native_order_event")) == 2
    assert not history_rows(data.algo, "sid_cash_native_history_census")


def test_native_history_enumeration_refuses_at_bound_without_dropping_tail(native_history, monkeypatch):
    data = native_history
    monkeypatch.setattr(mask, "_SID_CASH_HISTORY_MAX_EVENTS", 1)
    with pytest.raises(mask.CashExclusionRefusal):
        data.algo._sid_cash_native_history()
    assert not history_rows(data.algo, "sid_cash_native_history_census")


def test_native_event_ids_are_unique_within_each_order_not_globally(native_history):
    data = native_history
    order2 = data.native.Order(data.order.symbol)
    order2.__dict__.update(data.order.__dict__)
    order2.id = 2
    ticket2 = data.native.OrderTicket()
    ticket2.__dict__.update(data.ticket.__dict__)
    ticket2.order_id = 2
    events2 = []
    for original in data.ticket.order_events:
        event = data.native.OrderEvent(original.symbol)
        event.__dict__.update(original.__dict__)
        event.order_id = 2
        events2.append(event)
    ticket2.order_events = events2
    data.algo.history = [order2, data.order]
    data.algo.transactions.get_order_ticket = lambda order_id: data.ticket if order_id == 1 else ticket2
    data.algo._sid_cash_native_history()
    events = history_rows(data.algo, "sid_cash_native_order_event")
    assert [(event["order_id"], event["event_id"]) for event in events] == [(1, 0), (1, 1), (2, 0), (2, 1)]
    assert history_rows(data.algo, "sid_cash_native_history_census")[0]["orders"] == 2


def test_actual_ticket_property_is_read_only_after_durable_claim(native_history):
    data = native_history
    accesses = []
    class ObservedTicket(data.native.OrderTicket):
        @property
        def order_events(self):
            assert data.algo.object_store.calls[-1][0] == "read"
            assert data.prefix + "native-order-history-access.json" in data.algo.object_store.values
            accesses.append("native_order_events_property")
            return self.native_events
    ticket = ObservedTicket()
    ticket.__dict__.update({key: value for key, value in data.ticket.__dict__.items() if key != "order_events"})
    ticket.native_events = data.ticket.order_events
    def get_ticket(order_id):
        assert data.algo.object_store.calls[-1][0] == "read"
        accesses.append(("native_get_order_ticket", order_id))
        return ticket
    data.algo.transactions.get_order_ticket = get_ticket
    data.algo._sid_cash_native_history()
    assert accesses == [("native_get_order_ticket", 1), "native_order_events_property",
        ("native_get_order_ticket", 1), "native_order_events_property"]
