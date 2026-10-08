"""Synthetic-only matched construction, custody and control-independence proofs."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
LANE = ROOT / "research/target_price_revisions_qc"
FREEZE_SHA = "a0645dce96d1153de4a6709b4d39c1d8cc0c583950a76421220e00539a9521d0"
CORE_SHA = "00f4f3a55ddca276a954e78bb550eaeaafc4b1b95051b3a7f64554edbae464e3"


@pytest.fixture
def matched(monkeypatch):
    api = ModuleType("AlgorithmImports")
    api.FeeModel = type("FeeModel", (), {})
    api.QCAlgorithm = type("QCAlgorithm", (), {})
    api.SplitType = SimpleNamespace(SPLIT_OCCURRED="occurred")
    api.OrderStatus = SimpleNamespace(INVALID="invalid", CANCELED="canceled")
    api.Universe = SimpleNamespace(UNCHANGED="unchanged")
    api.Resolution = SimpleNamespace(MINUTE="minute", DAILY="daily", HOUR="hour")
    api.TickType = SimpleNamespace(TRADE="trade", QUOTE="quote")
    api.DataNormalizationMode = SimpleNamespace(RAW=0, ADJUSTED=1)
    api.SecurityType = SimpleNamespace(EQUITY="equity", BASE="base")
    api.TradeBar = type("TradeBar", (), {})
    api.ConstantSlippageModel = lambda value: ("slippage", value)
    api.ImmediateSettlementModel = lambda: "immediate"
    monkeypatch.setitem(sys.modules, "AlgorithmImports", api)
    system = ModuleType("System")
    system.Object = SimpleNamespace(ReferenceEquals=lambda first, second: first is second)
    monkeypatch.setitem(sys.modules, "System", system)
    core = ModuleType("proxy_core")
    source = LANE / "cloud_algorithm_v2.py"
    exec(compile(source.read_bytes(), str(source), "exec"), core.__dict__)
    monkeypatch.setitem(sys.modules, "proxy_core", core)
    module = ModuleType("matched_algorithm")
    source = LANE / "matched_algorithm_v3.py"
    exec(compile(source.read_bytes(), str(source), "exec"), module.__dict__)
    return module


class Symbol:
    def __init__(self, identifier, value=None):
        self.id, self.value = identifier, value or identifier


class Security:
    def __init__(self, symbol):
        self.symbol, self.has_data = symbol, True
        self.type = "equity"
        self.subscriptions = [SimpleNamespace(data_normalization_mode=0,
            is_internal_feed=False, resolution="minute", tick_type="trade", symbol=symbol,
            type=SimpleNamespace(FullName="QuantConnect.Data.Market.TradeBar"),
            is_custom_data=False, fill_data_forward=True)]
        self.cache = object()

    @property
    def data_normalization_mode(self):
        return self.subscriptions[0].data_normalization_mode

    def set_data_normalization_mode(self, mode):
        for config in self.subscriptions:
            config.data_normalization_mode = mode

    def set_leverage(self, value):
        self.leverage = value

    def set_fee_model(self, value):
        self.fee = value

    def set_slippage_model(self, value):
        self.slippage = value

    def set_settlement_model(self, value):
        self.settlement = value


def encoded(body):
    text = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return text, hashlib.sha256(text.encode()).hexdigest()


def config(matched, arm="tpr_on", cost="baseline"):
    candidate, slippage = matched.CANDIDATES[arm, cost]
    return {"schema": "tpr-qc-matched-config-v1", "study_id": matched.STUDY,
            "freeze_sha256": FREEZE_SHA, "candidate_id": candidate,
            "arm": arm, "cost": cost, "slippage": slippage}


def member(identifier, weight="0.1", ticker=None):
    return {"symbol": Symbol(identifier, ticker), "ticker": ticker or identifier, "weight": weight}


def algorithm(matched, arm="tpr_off"):
    algo = matched.TargetPriceMatchedAlgorithm()
    algo.live_mode, algo.is_warming_up = False, False
    algo.time, algo.utc_time = datetime(2025, 1, 2, 9, 20), datetime(2025, 1, 2, 14, 20)
    algo._config = config(matched, arm)
    algo._identities, algo._frames = {}, {}
    algo._snapshots = {etf: [] for etf in matched.ETFS}
    algo._symbols, algo._split_factors, algo._custody_since = {}, {}, {}
    algo._warmup_finished_minute_validated = False
    algo._context_symbols = set()
    algo._context_initializer_skips = algo._context_change_skips = 0
    algo._benchmark_internal_config_max = 0
    algo._delisted_ids, algo._manual_symbols, algo._valuation_days = set(), set(), set()
    algo._targets, algo._target_weights, algo._decision_coverage, algo._tickets = {}, {}, {}, []
    algo._attempted_days, algo._reasons = set(), {}
    algo._cash_ledger, algo._quantity_ledger, algo._dividend_keys = Fraction(100000), {}, set()
    algo._prior_close_nav, algo._prior_close_day = Fraction(100000), None
    algo._fees, algo._fill_events, algo._submitted = Fraction(0), 0, 0
    algo._requested_shares = algo._submitted_shares = algo._filled_shares = 0
    algo._max_cash_residual = algo._max_nav_residual = Fraction(0)
    algo._decision_count = algo._refused_count = algo._position_ledger_mismatches = 0
    algo._risk_breaches, algo._name_soft_cap_breaches = 0, 0
    algo._max_name_exposure = Fraction(0)
    algo._sleeve_selected_decisions = {etf: 0 for etf in matched.ETFS}
    algo._etf_symbols = {etf: Symbol("ETF-" + etf, etf) for etf in matched.ETFS}
    algo._benchmark = algo._etf_symbols["SPY"]
    algo.benchmark = SimpleNamespace(security=None)
    algo.securities = {}
    algo.subscription_manager = SimpleNamespace(subscription_data_config_service=SimpleNamespace(
        get_subscription_data_configs=lambda symbol, internal: list(algo.securities[symbol].subscriptions)))
    algo.portfolio = SimpleNamespace(cash="100000", total_portfolio_value="100000",
                                    total_holdings_value="0", values=lambda: [])
    algo.logs, algo.orders, algo.add_calls, algo.history_calls = [], [], [], []
    algo.log = algo.logs.append
    algo.market_on_open_order = lambda symbol, quantity, **kwargs: algo.orders.append((symbol, quantity)) or "ticket"
    def add_security(symbol, resolution, **kwargs):
        algo.add_calls.append((symbol, resolution, kwargs))
        return algo.securities.setdefault(symbol, Security(symbol))
    algo.add_security = add_security
    class History:
        def __getitem__(self, kind):
            def request(symbol, count, resolution, **kwargs):
                algo.history_calls.append((symbol, count, resolution, kwargs))
                return [SimpleNamespace(time=datetime(2024, 12, 31, 9, 30),
                    end_time=datetime(2024, 12, 31, 16), close="100", volume="100000")]
            return request
    algo.history = History()
    return algo


def snapshots_for_first_decision(algo, matched):
    cutoff = matched.core._clock(matched.CUTOFFS[0])
    for etf in matched.ETFS:
        algo._snapshots[etf] = [{"effective": cutoff - timedelta(days=7),
            "received": cutoff - timedelta(days=6), "members": [member("COMMON")]}]


def complete_evidence(algo, matched):
    algo._warmup_finished_minute_validated = True
    algo._attempted_days = set(matched.DECISIONS)
    algo._decision_count, algo._fill_events = 14, 1
    algo._decision_coverage = {day: {"sleeves": {etf: {} for etf in matched.ETFS}}
                               for day in matched.DECISIONS}
    start = date(2025, 1, 2)
    holidays = {"2025-01-09", "2025-01-20", "2025-02-17"}
    algo._valuation_days = {(start + timedelta(days=offset)).isoformat() for offset in range(89)
        if (start + timedelta(days=offset)).weekday() < 5
        and (start + timedelta(days=offset)).isoformat() not in holidays}
    assert len(algo._valuation_days) == 60
    algo._prior_close_day = date(2025, 3, 31)
    algo.time, algo.utc_time = datetime(2025, 4, 1), datetime(2025, 4, 1, 4)


def summary(algo):
    algo.on_end_of_algorithm()
    return json.loads(algo.logs[-1].split(" ", 1)[1])


def test_exact_freeze_and_executed_core_remain_immutable(matched):
    assert hashlib.sha256((LANE / "matched_freeze.json").read_bytes()).hexdigest() == FREEZE_SHA
    assert hashlib.sha256((LANE / "cloud_algorithm_v2.py").read_bytes()).hexdigest() == CORE_SHA
    assert hashlib.sha256((LANE / "matched_algorithm.py").read_bytes()).hexdigest() == "ca3de46384d5aefe384245273bb697f59587e7f34528e139602f9f2fca02fa1f"
    assert hashlib.sha256((LANE / "matched_algorithm_v2.py").read_bytes()).hexdigest() == "a6c295e5e00364f6c91d6d33c750b45a3ce7c9264c4dfc2f325e9a76f394c612"
    assert matched.DECISIONS == matched.core.DECISIONS and matched.CUTOFFS == matched.core.CUTOFFS


def test_all_six_exact_configs_admitted(matched):
    for arm, cost in matched.CANDIDATES:
        body = config(matched, arm, cost)
        text, digest = encoded(body)
        assert matched.validate_config(text, digest, FREEZE_SHA) == body


@pytest.mark.parametrize("field,value", [
    ("schema", "old"), ("study_id", "renamed"), ("freeze_sha256", "1" * 64),
    ("candidate_id", "TPR-MATCHED-OFF-BASE-v1"), ("arm", "ar_on"),
    ("cost", "free"), ("slippage", "0"), ("slippage", "0.0010")])
def test_configuration_mutations_refuse(matched, field, value):
    body = config(matched)
    body[field] = value
    text, digest = encoded(body)
    with pytest.raises(ValueError, match="frozen matched"):
        matched.validate_config(text, digest, FREEZE_SHA)


def test_config_hash_unknown_field_and_duplicate_key_refuse(matched):
    body = config(matched)
    text, digest = encoded(body)
    with pytest.raises(ValueError, match="hash"):
        matched.validate_config(text + " ", digest, FREEZE_SHA)
    body["extra"] = True
    text, digest = encoded(body)
    with pytest.raises(ValueError, match="closed schema"):
        matched.validate_config(text, digest, FREEZE_SHA)
    text = text[:-1] + ',"arm":"tpr_on"}'
    with pytest.raises(ValueError, match="duplicate"):
        matched.validate_config(text, hashlib.sha256(text.encode()).hexdigest(), FREEZE_SHA)


def test_neutral_rank_uses_weight_native_id_not_input_order_or_tpr(matched):
    members = [member(f"ID-{i:02}", "0.1", f"TICK-{99-i}") for i in reversed(range(12))]
    members += [member("UNKNOWN", None), member("ZERO", "0")]
    selected, coverage = matched.rank_neutral_members(members)
    assert tuple(selected) == tuple(f"ID-{i:02}" for i in range(10))
    assert coverage["known_weight"] == {"count": 12, "weight": Fraction(6, 5)}
    assert coverage["unknown_weight"]["count"] == coverage["zero_weight"]["count"] == 1
    members[-3]["weight"] = "0.5"
    assert next(iter(matched.rank_neutral_members(members)[0])) == members[-3]["symbol"].id


@pytest.mark.parametrize("members", [
    [member("A"), member("A")], [member("A", ticker="SAME"), member("B", ticker="SAME")],
    [member("A", "-0.1")], [member("A", "1.01")], [member("A", "NaN")]])
def test_membership_ambiguity_and_invalid_weight_refuse(matched, members):
    with pytest.raises(ValueError):
        matched.rank_neutral_members(members)


def test_signal_rank_keeps_frozen_source_ties_missing_states_and_positive_rule(matched):
    identities = {sid: {"ticker": ticker, "eligible": eligible} for sid, ticker, eligible in
                  [("SOURCE-A", "A", True), ("SOURCE-Z", "Z", True), ("REFUSED", "R", False)]}
    frame = {"states": [
        {"security_id": "SOURCE-A", "state": "scored", "score": ".5"},
        {"security_id": "SOURCE-Z", "state": "scored", "score": ".5"},
        {"security_id": "REFUSED", "state": "identity_ineligible", "score": None}]}
    members = [member("NATIVE-Z", ticker="A"), member("NATIVE-A", ticker="Z"),
               member("REFUSED", ticker="R"), member("MISSING"), member("UNKNOWN", None)]
    selected, coverage = matched.rank_signal_members(identities, frame, members)
    assert tuple(selected) == ("NATIVE-Z", "NATIVE-A")  # source-ID, not native-ID score tie
    assert coverage["ineligible"]["count"] == coverage["missing_identity"]["count"] == 1
    assert coverage["unknown_weight"]["count"] == 1
    frame["states"][0]["score"] = "0"
    assert tuple(matched.rank_signal_members(identities, frame, members)[0]) == ("NATIVE-A",)


def test_overlapping_sleeves_consolidate_exact_id_and_leave_missing_slots_cash(matched):
    same = Symbol("SAME")
    selected = {etf: {same.id: same} for etf in matched.ETFS}
    symbols, weights = matched.consolidate_slots(selected)
    assert symbols == {"SAME": same} and weights == {"SAME": Fraction(1, 10)}
    selected["REMX"] = {}
    assert matched.consolidate_slots(selected)[1] == {"SAME": Fraction(1, 12)}
    selected["SPY"] = {"FOREIGN": same}
    with pytest.raises(ValueError, match="identity mismatch"):
        matched.consolidate_slots(selected)
    with pytest.raises(ValueError, match="six sleeves"):
        matched.consolidate_slots({})


def test_weighted_sizing_is_exact_consolidated_sells_first_without_recycling(matched):
    orders = matched.plan_weighted_orders({"A": Fraction(1, 60)}, {"Z": 100},
        {"A": ("10", "100000"), "Z": ("10", "100000")}, "60000", "0", "0.001")
    assert orders == [
        {"security_id": "Z", "requested": -100, "submitted": -100, "reason": "complete"},
        {"security_id": "A", "requested": 100, "submitted": 0, "reason": "cash_buffer"}]
    assert matched.plan_weighted_orders({"A": Fraction(1, 10)}, {}, {"A": (10, 100000)},
        60000, 60000, "0.001")[0]["requested"] == 600
    with localcontext() as context:
        context.prec = 2
        assert matched.plan_weighted_orders({"A": Fraction(1, 60)}, {}, {"A": (10, 100000)},
            60000, 60000, "0.001")[0]["requested"] == 100


def test_cash_volume_slippage_and_missing_marks_are_not_substitution(matched):
    baseline = matched.plan_weighted_orders({"A": Fraction(1, 10)}, {}, {"A": (100, 10000)},
        100000, 10011, "0.001")
    adverse = matched.plan_weighted_orders({"A": Fraction(1, 10)}, {}, {"A": (100, 10000)},
        100000, 10011, "0.0015")
    assert baseline[0]["submitted"] == 97 and adverse[0]["submitted"] == 96
    assert baseline[0]["submitted"] * Fraction("100.11") <= Fraction("9710.67")
    assert adverse[0]["submitted"] * Fraction("100.16") <= Fraction("9710.67")
    capped = matched.plan_weighted_orders({"A": Fraction(1, 10)}, {}, {"A": (100, 500)},
        100000, 100000, "0.001")
    assert capped[0] == {"security_id": "A", "requested": 100, "submitted": 5, "reason": "volume_cap"}
    missing = matched.plan_weighted_orders({"A": Fraction(1, 10)}, {}, {}, 100000, 100000, "0.001")
    assert missing == [{"security_id": "A", "requested": None, "submitted": 0, "reason": "missing_mark"}]


def test_etf_cap_difference_is_deliberate_and_closed(matched):
    weights = {"ETF": Fraction(1, 6)}
    with pytest.raises(ValueError, match="target weights"):
        matched.plan_weighted_orders(weights, {}, {"ETF": (100, 100000)}, 60000, 60000, ".001")
    assert matched.plan_weighted_orders(weights, {}, {"ETF": (100, 100000)},
        60000, 60000, ".001", etf_arm=True)[0]["requested"] == 100


@pytest.mark.parametrize("value", [True, None, "NaN", "Infinity", float("inf"), "-Infinity"])
def test_native_invalid_number_refuses(matched, value):
    with pytest.raises(ValueError):
        matched.native_fraction(value)


def test_native_numeric_boundary_is_decimal_capture_then_rational(matched):
    assert matched.native_fraction(Decimal("0.1")) == matched.native_fraction("0.1") == Fraction(1, 10)
    assert matched.native_fraction(0.1) == Fraction(1, 10)


@pytest.mark.parametrize("arm", ["tpr_off", "etf_basket"])
def test_neutral_and_etf_prepare_never_read_tpr_identity_state_or_score(matched, arm):
    algo = algorithm(matched, arm)
    class Forbidden(dict):
        def __getitem__(self, key):
            raise AssertionError("TPR input was read")
        def values(self):
            raise AssertionError("TPR identity was read")
    algo._frames = algo._identities = Forbidden()
    snapshots_for_first_decision(algo, matched)
    algo._prepare_targets(matched.DECISIONS[0])
    if arm == "tpr_off":
        assert algo._target_weights == {"COMMON": Fraction(1, 10)}
    else:
        assert len(algo._target_weights) == 6 and set(algo._target_weights.values()) == {Fraction(1, 6)}
    assert set(algo._decision_coverage[matched.DECISIONS[0]]["sleeves"]) == set(matched.ETFS)


def test_missing_one_membership_does_not_replace_existing_targets_or_liquidate(matched):
    algo = algorithm(matched)
    snapshots_for_first_decision(algo, matched)
    algo._snapshots["REMX"] = []
    algo._targets, algo._target_weights = {"HELD": Symbol("HELD")}, {"HELD": Fraction(1, 60)}
    algo._rebalance()
    algo._rebalance()
    assert set(algo._targets) == {"HELD"} and algo.orders == []
    assert algo._decision_count == algo._refused_count == 1
    assert algo._decision_coverage[matched.DECISIONS[0]] is None


def test_etf_positions_are_not_filtered_by_absent_constituent_inputs(matched):
    algo = algorithm(matched, "etf_basket")
    # No constituent callbacks at all: still exactly the six frozen ETF targets.
    algo._prepare_targets(matched.DECISIONS[0])
    assert len(algo._target_weights) == 6
    assert set(algo._target_weights.values()) == {Fraction(1, 6)}
    reports = algo._decision_coverage[matched.DECISIONS[0]]["sleeves"]
    assert all(row["membership_available"] is False and row["member_count"] is None
               and row["snapshot_hash"] is None and row["selected_count"] == 1
               for row in reports.values())
    assert algo._reasons == {}


def test_cutoff_and_membership_future_receipt_refuse_before_orders(matched):
    algo = algorithm(matched)
    algo.utc_time = matched.core._clock(matched.CUTOFFS[0]).replace(tzinfo=None)
    with pytest.raises(ValueError, match="not yet available"):
        algo._prepare_targets(matched.DECISIONS[0])
    assert algo.orders == [] and algo._decision_coverage == {}
    cutoff = matched.core._clock(matched.CUTOFFS[0])
    future = {"effective": cutoff - timedelta(days=7), "received": cutoff + timedelta(seconds=1)}
    assert matched.core.select_snapshot([future], cutoff) is None


def test_no_default_split_basis_until_prior_action_custody_is_proven(matched):
    cutoff = matched.core._clock(matched.CUTOFFS[0])
    early = cutoff - timedelta(days=7)
    assert matched.split_basis_with_custody(None, cutoff, None) is None
    assert matched.split_basis_with_custody(early + timedelta(seconds=1), cutoff, None) is None
    assert matched.split_basis_with_custody(early, cutoff, None) == 1
    assert matched.split_basis_with_custody(early, cutoff, 2) == 2
    assert matched.split_basis_with_custody(early, cutoff, 0) is None
    assert matched.split_basis_with_custody(early, cutoff, None, delisted=True) is None


def test_new_subscription_reverse_split_red_control_refuses_then_custody_green(matched):
    algo = algorithm(matched)
    symbol = Symbol("A")
    algo.securities[symbol] = Security(symbol)
    # Original method supplies factor=1 for a newly subscribed name whose
    # ex-date reverse split was never delivered; successor refuses that mark.
    algo._frames = {"2025-01-02": {"cutoff_utc": matched.CUTOFFS[0]}}
    assert matched.core.TargetPriceSixUniverseAlgorithm._prior_mark(algo, symbol) == (100, 100000)
    assert algo._prior_mark(symbol) is None and algo._reasons["missing_action_custody"] == 1
    algo._custody_since["A"] = matched.core._clock(matched.CUTOFFS[0]) - timedelta(days=7)
    algo._split_factors["A", "2025-01-02"] = Fraction(2)
    assert algo._prior_mark(symbol) == (200, 50000)
    assert matched.plan_weighted_orders({"A": Fraction(1, 10)}, {}, {"A": algo._prior_mark(symbol)},
        100000, 100000, ".001")[0]["requested"] == 50


def test_custody_persistent_raw_subscription_is_not_restarted_on_repeat(matched):
    algo, symbol = algorithm(matched), Symbol("A")
    security = Security(symbol)
    algo.on_securities_changed(SimpleNamespace(added_securities=[security]))
    assert algo._custody_since == {}  # Configuration alone is not custody.
    algo.on_data(SimpleNamespace(bars={"bar": SimpleNamespace(symbol=symbol)},
        dividends={}, splits={}, delistings={}))
    original = algo._custody_since["A"]
    algo.utc_time += timedelta(days=1)
    algo.on_securities_changed(SimpleNamespace(added_securities=[security]))
    assert algo._custody_since["A"] == original and len(algo.add_calls) == 1
    algo.securities[symbol].subscriptions[0].data_normalization_mode = 1
    with pytest.raises(ValueError, match="non-RAW configurations"):
        algo._ensure_raw_subscription(symbol)


def test_executed_v1_warmup_minute_refusal_red_control_then_successor_transition(matched):
    original = ModuleType("executed_matched_algorithm")
    source = LANE / "matched_algorithm.py"
    exec(compile(source.read_bytes(), str(source), "exec"), original.__dict__)
    old, new = algorithm(original), algorithm(matched)
    symbol = Symbol("SYNTHETIC")
    for algo in (old, new):
        algo.is_warming_up = True
        algo.utc_time = datetime(2024, 12, 2)
        security = Security(symbol)
        security.subscriptions[0].resolution = "daily"
        algo.securities[symbol] = security
        changes = SimpleNamespace(added_securities=[security])
        if algo is old:
            with pytest.raises(ValueError, match="active RAW minute trade subscription required"):
                algo.on_securities_changed(changes)
        else:
            algo.on_securities_changed(changes)
    assert new._custody_since == {} and new._warmup_finished_minute_validated is False
    # A genuine observed RAW warm-up bar, not manager presence, starts custody.
    new.on_data(SimpleNamespace(bars={"synthetic": SimpleNamespace(symbol=symbol)},
        dividends={}, splits={}, delistings={}))
    observed = new._custody_since[symbol.id]
    assert observed == datetime(2024, 12, 2, tzinfo=timezone.utc)
    assert new._quantity_ledger == {} and new._cash_ledger == 100000
    assert new._valuation_days == set() and new.orders == []
    # Model the native completed-warm-up registry transition explicitly.
    new.is_warming_up = False
    new.utc_time = datetime(2025, 1, 2)
    new.securities[symbol].subscriptions[0].resolution = "minute"
    new.on_warmup_finished()
    assert new._warmup_finished_minute_validated is True
    assert new._assert_raw_subscriptions(symbol) is new.securities[symbol]
    assert new._custody_since[symbol.id] == observed
    assert new.add_calls[-1][1] == "minute"


def test_empty_warmup_registry_is_pending_not_action_custody_or_postwarm_permission(matched):
    algo, symbol = algorithm(matched), Symbol("SYNTHETIC")
    algo.is_warming_up = True
    security = Security(symbol)
    algo.securities[symbol] = security
    algo.subscription_manager.subscription_data_config_service.get_subscription_data_configs = lambda *args: []
    algo.on_securities_changed(SimpleNamespace(added_securities=[security]))
    assert algo._assert_raw_subscriptions(symbol) is security
    algo.on_data(SimpleNamespace(bars={"synthetic": SimpleNamespace(symbol=symbol)},
        dividends={}, splits={}, delistings={}))
    assert algo._custody_since == {}
    algo.is_warming_up = False
    with pytest.raises(ValueError, match="no RAW configurations"):
        algo.on_warmup_finished()
    assert algo._warmup_finished_minute_validated is False
    assert algo._prior_mark(symbol) is None  # Missing custody itself refuses a usable mark.
    algo._custody_since[symbol.id] = matched.core._clock(matched.CUTOFFS[0]) - timedelta(days=7)
    with pytest.raises(ValueError, match="no RAW configurations"):
        algo._prior_mark(symbol)
    assert algo.orders == []


@pytest.mark.parametrize("state,message", [
    ("config", "non-RAW configurations count=1"),
    ("security", "non-RAW security normalization"),
    ("missing", "missing exact security"),
    ("identity", "changed exact security identity")])
def test_positive_raw_or_identity_failures_refuse_even_during_warmup(matched, state, message):
    algo, symbol = algorithm(matched), Symbol("SYNTHETIC")
    algo.is_warming_up = True
    security = Security(symbol)
    algo.securities[symbol] = security
    if state == "config":
        security.subscriptions[0].data_normalization_mode = 1
    elif state == "security":
        security.subscriptions[0].data_normalization_mode = 1
        raw = SimpleNamespace(data_normalization_mode=0, is_internal_feed=False,
            resolution="daily", tick_type="trade", symbol=symbol,
            type=SimpleNamespace(FullName="QuantConnect.Data.Market.TradeBar"),
            is_custom_data=False, fill_data_forward=True)
        algo.subscription_manager.subscription_data_config_service.get_subscription_data_configs = lambda *args: [raw]
    elif state == "missing":
        del algo.securities[symbol]
    else:
        security.symbol = Symbol("FOREIGN")
    with pytest.raises(ValueError, match=message):
        algo._assert_raw_subscriptions(symbol)
    assert algo._custody_since == {} and algo.orders == []


@pytest.mark.parametrize("resolution,internal,tick,active,daily,internals", [
    ("daily", False, "trade", 1, 1, 0),
    ("minute", True, "trade", 0, 0, 0),
    ("minute", False, "quote", 1, 0, 0)])
def test_postwarm_registry_failure_has_aggregate_diagnosis_not_data(matched, resolution, internal, tick, active, daily, internals):
    algo, symbol = algorithm(matched), Symbol("PRIVATE_SENTINEL_DO_NOT_LOG")
    security = Security(symbol)
    security.subscriptions[0].resolution = resolution
    security.subscriptions[0].is_internal_feed = internal
    security.subscriptions[0].tick_type = tick
    algo.securities[symbol] = security
    algo._symbols[symbol.id] = symbol
    expected = ("no RAW configurations" if internal else
                f"no minute trade; active={active}; daily_trade={daily}; internal={internals}")
    with pytest.raises(ValueError, match=expected) as error:
        algo.on_warmup_finished()
    assert symbol.value not in str(error.value)
    assert algo._warmup_finished_minute_validated is False
    assert algo._custody_since == {} and algo.orders == []


def test_premature_warmup_finished_callback_never_claims_validation(matched):
    algo = algorithm(matched)
    algo.is_warming_up = True
    with pytest.raises(ValueError, match="before completion"):
        algo.on_warmup_finished()
    assert algo._warmup_finished_minute_validated is False


@pytest.mark.parametrize("cost,exact", [("baseline", Fraction(1, 1000)), ("adverse", Fraction(3, 2000))])
def test_native_slippage_uses_invariant_dotnet_decimal_without_float(matched, monkeypatch, cost, exact):
    calls, culture = [], object()
    system, globalization = ModuleType("System"), ModuleType("System.Globalization")
    class NetDecimal:
        @staticmethod
        def Parse(text, provider):
            calls.append((text, provider))
            return Decimal(text)
    system.Decimal = NetDecimal
    globalization.CultureInfo = SimpleNamespace(InvariantCulture=culture)
    monkeypatch.setitem(sys.modules, "System", system)
    monkeypatch.setitem(sys.modules, "System.Globalization", globalization)
    algo, security = algorithm(matched), Security(Symbol("SYNTHETIC"))
    algo._config = config(matched, "tpr_off", cost)
    algo._initialize_security(security)
    assert calls == [(algo._config["slippage"], culture)]
    assert security.slippage[0] == "slippage"
    assert isinstance(security.slippage[1], Decimal)
    assert Fraction(security.slippage[1]) == exact
    assert security.leverage == 1 and isinstance(security.fee, matched.core.CentPerShareFee)
    assert security.settlement == "immediate"


def test_executed_v2_equity_context_refusal_red_control_and_exact_context_green(matched):
    original = ModuleType("executed_matched_algorithm_v2")
    source = LANE / "matched_algorithm_v2.py"
    exec(compile(source.read_bytes(), str(source), "exec"), original.__dict__)
    old, new = algorithm(original), algorithm(matched)
    context = Symbol("EXACT_REGISTERED_CONTEXT_WITH_NO_PREFIX")
    context.underlying, context.has_underlying = new._etf_symbols["SPY"], True
    for algo in (old, new):
        algo.is_warming_up = True
        security = Security(context)
        assert security.type == "equity"  # Matches LEAN's ETF context identity.
        # The global configuration is independent of Security's mutable bag.
        registered = deepcopy(security.subscriptions[0])
        registered.symbol = context
        registered.data_normalization_mode = 1
        registered.resolution, registered.is_custom_data = "daily", True
        registered.is_internal_feed, registered.fill_data_forward = True, False
        registered.type.FullName = "QuantConnect.Data.UniverseSelection.ETFConstituentUniverse"
        algo.securities[context] = security
        algo.subscription_manager.subscription_data_config_service.get_subscription_data_configs = lambda *args, row=registered: [row]
        algo._context_symbols.add(context)
        if algo is old:
            with pytest.raises(ValueError, match="non-RAW configurations count=1"):
                algo.on_securities_changed(SimpleNamespace(added_securities=[security]))
        else:
            def forbidden(*args):
                raise AssertionError("context received a money model or normalization mutation")
            security.set_leverage = security.set_fee_model = security.set_data_normalization_mode = forbidden
            algo._initialize_security(security)
            algo.on_securities_changed(SimpleNamespace(added_securities=[security]))
            algo._observe_raw_custody(context)
            with pytest.raises(ValueError, match="context cannot be subscribed"):
                algo._ensure_raw_subscription(context)
            with pytest.raises(ValueError, match="context is not tradable"):
                algo._raw_security_configs(context)
    assert new._context_initializer_skips == new._context_change_skips == 1
    assert new._symbols == new._custody_since == {} and new._manual_symbols == set()
    assert new.add_calls == [] and new.orders == []


def test_unregistered_equity_lookalike_is_not_skipped_by_prefix_or_underlying(matched):
    algo = algorithm(matched)
    symbol = Symbol("qc-universe-etf-constituents-lookalike")
    symbol.underlying, symbol.has_underlying = algo._etf_symbols["SPY"], True
    security = Security(symbol)
    algo.on_securities_changed(SimpleNamespace(added_securities=[security]))
    assert algo._symbols[symbol.id] is symbol and len(algo.add_calls) == 1
    assert algo._context_change_skips == 0 and algo._custody_since == {}


def benchmark_configuration(algo):
    symbol = algo._benchmark
    tradable, benchmark = Security(symbol), Security(symbol)
    algo.securities[symbol], algo.benchmark = tradable, SimpleNamespace(security=benchmark)
    algo._symbols[symbol.id] = symbol
    internal = SimpleNamespace(symbol=symbol, data_normalization_mode=1,
        is_internal_feed=True, resolution="hour", tick_type="trade",
        type=SimpleNamespace(FullName="QuantConnect.Data.Market.TradeBar"),
        is_custom_data=False, fill_data_forward=False)
    external = tradable.subscriptions[0]
    algo.subscription_manager.subscription_data_config_service.get_subscription_data_configs = lambda *args: [external, internal]
    return symbol, tradable, benchmark, external, internal


def test_executed_v2_benchmark_registry_false_alarm_red_then_narrow_isolation_green(matched, monkeypatch):
    original = ModuleType("executed_matched_algorithm_v2")
    source = LANE / "matched_algorithm_v2.py"
    exec(compile(source.read_bytes(), str(source), "exec"), original.__dict__)
    old = algorithm(original)
    symbol, _, _, _, _ = benchmark_configuration(old)
    with pytest.raises(ValueError, match="non-RAW configurations count=1"):
        old._assert_raw_subscriptions(symbol)
    new = algorithm(matched)
    symbol, security, benchmark, _, _ = benchmark_configuration(new)
    calls = []
    def native_reference_equals(first, second):
        calls.append((first, second))
        return first is second
    monkeypatch.setattr(sys.modules["System"].Object, "ReferenceEquals", native_reference_equals)
    assert new._assert_raw_subscriptions(symbol) is security
    assert calls == [(benchmark, security), (benchmark.cache, security.cache)]
    assert new._benchmark_internal_config_max == 1 and new._custody_since == {}
    new.on_data(SimpleNamespace(bars={"raw": SimpleNamespace(symbol=symbol)},
        dividends={}, splits={}, delistings={}))
    assert new._custody_since[symbol.id] == new.utc_time.replace(tzinfo=timezone.utc)


@pytest.mark.parametrize("fault", ["external", "normalization", "resolution", "tick", "type", "custom", "ff",
    "config_symbol", "benchmark_symbol", "same_security", "same_cache", "no_benchmark", "other_symbol"])
def test_benchmark_exception_refuses_every_wrong_signature_or_shared_money_reference(matched, fault):
    algo = algorithm(matched)
    symbol, security, benchmark, external, internal = benchmark_configuration(algo)
    if fault == "external":
        internal.is_internal_feed = False
    elif fault == "normalization":
        internal.data_normalization_mode = 2
    elif fault == "resolution":
        internal.resolution = "daily"
    elif fault == "tick":
        internal.tick_type = "quote"
    elif fault == "type":
        internal.type.FullName = "PRIVATE_SENTINEL_NOT_A_TRADEBAR"
    elif fault == "custom":
        internal.is_custom_data = True
    elif fault == "ff":
        internal.fill_data_forward = True
    elif fault == "config_symbol":
        internal.symbol = Symbol("PRIVATE_SYMBOL_SENTINEL")
    elif fault == "benchmark_symbol":
        benchmark.symbol = Symbol("PRIVATE_SYMBOL_SENTINEL")
    elif fault == "same_security":
        algo.benchmark.security = security
    elif fault == "same_cache":
        benchmark.cache = security.cache
    elif fault == "no_benchmark":
        algo.benchmark.security = None
    else:
        algo._benchmark = Symbol("PRIVATE_SYMBOL_SENTINEL")
    with pytest.raises(ValueError) as error:
        algo._assert_raw_subscriptions(symbol)
    assert "PRIVATE_SYMBOL_SENTINEL" not in str(error.value)
    assert algo._custody_since == {} and algo.orders == []
    assert algo._benchmark_internal_config_max == 0


def test_benchmark_only_registry_never_proves_raw_custody_or_trading_feed(matched):
    algo = algorithm(matched)
    symbol, security, _, _, internal = benchmark_configuration(algo)
    algo.subscription_manager.subscription_data_config_service.get_subscription_data_configs = lambda *args: [internal]
    algo.is_warming_up = True
    assert algo._assert_raw_subscriptions(symbol) is security
    algo._observe_raw_custody(symbol)
    assert algo._custody_since == {}
    algo.is_warming_up = False
    with pytest.raises(ValueError, match="no RAW configurations") as error:
        algo._assert_raw_subscriptions(symbol)
    assert "internal:1:hour:trade:QuantConnect.Data.Market.TradeBar:native:noff" in str(error.value)
    assert algo.orders == []


def test_isolated_benchmark_cannot_hide_nonraw_security_or_external_quote_feed(matched):
    algo = algorithm(matched)
    symbol, security, _, external, internal = benchmark_configuration(algo)
    external.data_normalization_mode = 1
    external.tick_type = "quote"
    with pytest.raises(ValueError, match="non-RAW configurations count=1; external"):
        algo._assert_raw_subscriptions(symbol)
    raw = deepcopy(external)
    raw.symbol, raw.data_normalization_mode = symbol, 0
    algo.subscription_manager.subscription_data_config_service.get_subscription_data_configs = lambda *args: [raw, internal]
    with pytest.raises(ValueError, match="non-RAW security normalization"):
        algo._assert_raw_subscriptions(symbol)


def test_native_reference_checker_absence_cannot_use_python_fallback(matched, monkeypatch):
    algo = algorithm(matched)
    symbol, _, _, _, _ = benchmark_configuration(algo)
    monkeypatch.delattr(sys.modules["System"], "Object")
    with pytest.raises(ImportError):
        algo._assert_raw_subscriptions(symbol)
    assert algo.orders == [] and algo._custody_since == {}


def test_prior_history_explicit_raw_and_active_feed_guard_precede_request(matched):
    algo = algorithm(matched)
    symbol = Symbol("SYNTHETIC")
    algo.securities[symbol] = Security(symbol)
    algo._custody_since[symbol.id] = matched.core._clock(matched.CUTOFFS[0]) - timedelta(days=7)
    assert algo._prior_mark(symbol) == (100, 100000)
    assert algo.history_calls == [(symbol, 3, "daily", {"data_normalization_mode": 0})]
    algo.securities[symbol].subscriptions[0].resolution = "daily"
    with pytest.raises(ValueError, match="no minute trade"):
        algo._prior_mark(symbol)
    assert len(algo.history_calls) == 1 and algo.orders == []


def test_custom_universe_security_is_not_attached_to_equity_custody(matched):
    algo = algorithm(matched)
    class ContextSecurity:
        type = "base"
        @property
        def symbol(self):
            raise AssertionError("custom feed treated as tradable equity")
    algo.on_securities_changed(SimpleNamespace(added_securities=[ContextSecurity()]))
    assert algo._manual_symbols == set() and algo._custody_since == {} and algo.add_calls == []


def test_callback_preregisters_members_without_signal_and_etf_does_not_subscribe_stocks(matched):
    for arm in ("tpr_off", "tpr_on", "etf_basket"):
        algo = algorithm(matched, arm)
        symbol = Symbol("MEMBER")
        rows = [SimpleNamespace(symbol=symbol, weight=Decimal(".2"), end_time=algo.utc_time)]
        selected = algo._constituents_for("SPY", rows)
        assert selected == ([] if arm == "etf_basket" else [symbol])
        assert len(algo._snapshots["SPY"]) == 1


def test_delisting_is_retained_and_not_zero_signal_or_replacement(matched):
    algo = algorithm(matched)
    algo.on_data(SimpleNamespace(dividends={}, splits={}, delistings={"d": SimpleNamespace(symbol=Symbol("COMMON"))}))
    assert algo._delisted_ids == {"COMMON"} and algo._reasons == {"delisting_event": 1}
    snapshots_for_first_decision(algo, matched)
    algo._prepare_targets(matched.DECISIONS[0])
    assert algo._targets == {} and algo._target_weights == {}
    assert algo._decision_coverage[matched.DECISIONS[0]]["unallocated_target_cash"] == "1"


def test_daily_audit_reports_soft_name_cap_and_unlevered_risk_separately(matched):
    algo = algorithm(matched)
    symbol = Symbol("A")
    algo.securities[symbol] = Security(symbol)
    held = SimpleNamespace(symbol=symbol, invested=True, quantity=110, holdings_value="11000")
    algo._quantity_ledger, algo._cash_ledger = {"A": Fraction(110)}, Fraction(89000)
    algo.portfolio = SimpleNamespace(cash="89000", total_portfolio_value="100000",
        total_holdings_value="11000", values=lambda: [held])
    algo._daily_audit()
    log = json.loads(algo.logs[-1].split(" ", 1)[1])
    assert log["risk_within_unlevered_account"] is True
    assert log["max_name_exposure"] == "0.11" and algo._name_soft_cap_breaches == 1
    assert algo._risk_breaches == 0 and algo._max_cash_residual == algo._max_nav_residual == 0
    algo.time += timedelta(days=1)
    algo.portfolio.cash, algo.portfolio.total_holdings_value = "-1", "100001"
    algo._daily_audit()
    assert algo._risk_breaches == 1


def test_invalid_and_cancel_events_retained_in_real_handler_and_summary(matched):
    for status, reason in (("invalid", "qc_invalid_order"), ("canceled", "qc_canceled_order")):
        algo = algorithm(matched)
        complete_evidence(algo, matched)
        event = SimpleNamespace(fill_quantity=0, fill_price=0, symbol=Symbol("A"),
            order_fee=SimpleNamespace(value=SimpleNamespace(amount="0")), status=status)
        algo.on_order_event(event)
        assert algo._reasons[reason] == 1 and summary(algo)["meaningful_execution"] is False


@pytest.mark.parametrize("reason", ["missing_mark", "missing_action_custody", "unpriced_held_nav",
    "missing_prior_close_nav", "qc_invalid_order", "qc_canceled_order", "delisting_event", "delisting_target_refused"])
def test_action_order_and_input_failures_disqualify_meaningful(matched, reason):
    algo = algorithm(matched)
    complete_evidence(algo, matched)
    assert summary(algo)["meaningful_execution"] is True
    algo._reasons[reason] = 1
    assert summary(algo)["meaningful_execution"] is False


@pytest.mark.parametrize("fault", ["cash", "nav", "positions", "risk", "coverage", "decisions", "days", "last", "fills", "warmup"])
def test_incomplete_evidence_never_claims_completed_matched_execution(matched, fault):
    algo = algorithm(matched)
    complete_evidence(algo, matched)
    if fault == "cash":
        algo._max_cash_residual = Fraction(".02")
    elif fault == "nav":
        algo._max_nav_residual = Fraction(".02")
    elif fault == "positions":
        algo._position_ledger_mismatches = 1
    elif fault == "risk":
        algo._risk_breaches = 1
    elif fault == "coverage":
        algo._decision_coverage[matched.DECISIONS[0]]["sleeves"].pop("REMX")
    elif fault == "decisions":
        algo._attempted_days.remove(matched.DECISIONS[0])
    elif fault == "days":
        algo._valuation_days.remove("2025-02-03")
    elif fault == "last":
        algo._prior_close_day = date(2025, 3, 28)
    elif fault == "warmup":
        algo._warmup_finished_minute_validated = False
    else:
        algo._fill_events = 0
    assert summary(algo)["meaningful_execution"] is False


def test_summary_never_invents_april_nav_sleeve_pnl_or_positive_remx(matched):
    algo = algorithm(matched, "tpr_on")
    complete_evidence(algo, matched)
    algo._sleeve_selected_decisions = {etf: 14 if etf != "REMX" else 0 for etf in matched.ETFS}
    result = summary(algo)
    assert result["last_valuation_session"] == "2025-03-31" and result["valuation_days"] == 60
    assert result["zero_selection_sleeve_diagnostics"] == ["REMX"]
    assert result["canonical_admission"] is result["independent_sleeve_pnl_observed"] is False
    assert not any(line.startswith("MATCHED_NAV ") for line in algo.logs)


@pytest.mark.parametrize("arm", ["tpr_off", "etf_basket"])
def test_neutral_initialization_does_not_touch_packet_or_old_initialize(matched, monkeypatch, arm):
    algo = algorithm(matched, arm)
    body = config(matched, arm)
    config_json, digest = encoded(body)
    matched.EXPECTED_MATCHED_CONFIG_SHA256, matched.EXPECTED_MATCHED_FREEZE_SHA256 = digest, FREEZE_SHA
    config_module = ModuleType("matched_config")
    config_module.CONFIG_JSON = config_json
    monkeypatch.setitem(sys.modules, "matched_config", config_module)
    monkeypatch.delitem(sys.modules, "signal_packet", raising=False)
    def forbidden(*args, **kwargs):
        raise AssertionError("TPR packet or original initializer accessed")
    monkeypatch.setattr(matched.core.TargetPriceSixUniverseAlgorithm, "initialize", forbidden)
    algo.object_store = SimpleNamespace(contains_key=forbidden, read=forbidden)
    for name in ("set_start_date", "set_end_date", "set_time_zone", "set_account_currency", "set_cash",
                 "add_security_initializer", "add_universe", "set_benchmark", "set_warm_up"):
        setattr(algo, name, lambda *args, **kwargs: None)
    algo.universe_settings = SimpleNamespace()
    algo.universe = SimpleNamespace(etf=lambda symbol, **kwargs: SimpleNamespace(
        symbol=Symbol("CONTEXT-" + symbol.id)))
    algo.add_equity = lambda etf, resolution, **kwargs: SimpleNamespace(symbol=Symbol(etf))
    registered = []
    def register(universe):
        assert universe.symbol in algo._context_symbols
        registered.append(universe.symbol)
    algo.add_universe = register
    algo.schedule = SimpleNamespace(on=lambda *args: None)
    algo.date_rules = SimpleNamespace(every_day=lambda symbol: None)
    algo.time_rules = SimpleNamespace(at=lambda *args: None)
    algo.initialize()
    assert algo._identities == algo._frames == {} and set(algo._etf_symbols) == set(matched.ETFS)
    assert set(registered) == algo._context_symbols and len(registered) == len(matched.ETFS) == 6


def test_live_refusal_precedes_configuration_and_all_api_access(matched):
    algo = matched.TargetPriceMatchedAlgorithm()
    algo.live_mode = True
    with pytest.raises(ValueError, match="live refused"):
        algo.initialize()
