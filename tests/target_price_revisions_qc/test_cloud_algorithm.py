"""Synthetic-only API-stub tests; no cloud, provider, or operator state access."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "research/target_price_revisions_qc/cloud_algorithm.py"


@pytest.fixture
def cloud(monkeypatch):
    api = ModuleType("AlgorithmImports")
    api.FeeModel = type("FeeModel", (), {})
    api.QCAlgorithm = type("QCAlgorithm", (), {})
    api.SplitType = SimpleNamespace(SPLIT_OCCURRED="occurred")
    api.OrderStatus = SimpleNamespace(INVALID="invalid", CANCELED="canceled")
    api.Universe = SimpleNamespace(UNCHANGED="unchanged")
    api.Resolution = SimpleNamespace(MINUTE="minute", DAILY="daily")
    api.TradeBar = type("TradeBar", (), {})
    monkeypatch.setitem(sys.modules, "AlgorithmImports", api)
    module = ModuleType("tpr_cloud_test")
    exec(compile(SOURCE.read_bytes(), str(SOURCE), "exec"), module.__dict__)
    return module


def encoded(body):
    text = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return text, hashlib.sha256(text.encode()).hexdigest()


def fixture_inputs(cloud):
    config = {"schema": "tpr-qc-six-config-v1", "freeze_sha256": cloud.EXPECTED_FREEZE_SHA256,
              "candidate_id": "TPR-QC6-SPY-v1", "universe_id": "sp500"}
    identities = [{"security_id": "A", "ticker": "SYNTHA", "eligible": True, "reason": "synthetic"},
                  {"security_id": "B", "ticker": "SYNTHB", "eligible": True, "reason": "synthetic"},
                  {"security_id": "C", "ticker": "SYNTHC", "eligible": False, "reason": "synthetic-refusal"}]
    packet = {"schema": "tpr-qc-six-signals-v1", "candidate_id": cloud.FAMILY,
              "freeze_sha256": cloud.EXPECTED_FREEZE_SHA256, "source_hashes": dict(cloud.FROZEN_SOURCE_HASHES),
              "identities": identities, "frames": []}
    for day in cloud.DECISIONS:
        prior = date.fromisoformat(day) - timedelta(days=1)
        while prior.weekday() >= 5 or prior.isoformat() in ("2025-01-01", "2025-01-20", "2025-02-17"):
            prior -= timedelta(days=1)
        cutoff = datetime(prior.year, prior.month, prior.day, 18, tzinfo=ZoneInfo("America/New_York"))
        packet["frames"].append({"session": day, "cutoff_utc": cutoff.astimezone(timezone.utc).isoformat(),
            "states": [{"security_id": "A", "state": "scored", "score": "0.25", "reasons": []},
                       {"security_id": "B", "state": "unknown_input", "score": None, "reasons": ["synthetic_missing"]},
                       {"security_id": "C", "state": "identity_ineligible", "score": None, "reasons": ["synthetic_refusal"]}]})
    return config, packet


def validate(cloud, config, packet):
    config_json, config_hash = encoded(config)
    packet_json, packet_hash = encoded(packet)
    return cloud.validate_inputs(config_json, packet_json, config_hash, packet_hash)


def test_valid_closed_packet_and_exact_six_case_identity(cloud):
    config, packet = fixture_inputs(cloud)
    for case, (candidate, _) in cloud.CASES.items():
        config.update(universe_id=case, candidate_id=candidate)
        admitted, identities, frames = validate(cloud, config, packet)
        assert admitted["universe_id"] == case
        assert set(identities) == {"A", "B", "C"}
        assert tuple(frames) == cloud.DECISIONS


@pytest.mark.parametrize("mutate", [
    lambda c, p: c.update(candidate_id="TPR-QC6-QQQ-v1"),
    lambda c, p: c.update(universe_id="all_nasdaq"),
    lambda c, p: c.update(freeze_sha256="1" * 64),
    lambda c, p: p.update(candidate_id="renamed-candidate"),
    lambda c, p: p.update(freeze_sha256="1" * 64),
    lambda c, p: p.update(source_hashes={}),
    lambda c, p: p["source_hashes"].update({"structure.json": "1" * 64}),
    lambda c, p: p["source_hashes"].update({"raw_candidate.py": "1" * 64}),
    lambda c, p: p["frames"].pop(),
    lambda c, p: p["frames"][0].update(session="2025-01-03"),
    lambda c, p: p["frames"][0].update(cutoff_utc="2025-01-02T23:00:00+00:00"),
    lambda c, p: p["frames"][0].update(cutoff_utc="2024-12-31T23:00:00"),
    lambda c, p: p["frames"][1].update(cutoff_utc="2025-01-05T23:00:00+00:00"),
    lambda c, p: p["frames"][0]["states"].pop(),
    lambda c, p: p["frames"][0]["states"][1].update(score="0"),
    lambda c, p: p["frames"][0]["states"][0].update(score="NaN"),
    lambda c, p: p["frames"][0]["states"][0].update(score="Infinity"),
    lambda c, p: p["frames"][0]["states"][0].update(score=0.25),
    lambda c, p: p["frames"][0]["states"][2].update(state="scored", score="1"),
    lambda c, p: p["identities"][1].update(ticker="SYNTHA"),
    lambda c, p: p["frames"][0]["states"][1].update(security_id="A"),
])
def test_packet_mutations_refuse_then_restored_control(cloud, mutate):
    config, packet = fixture_inputs(cloud)
    validate(cloud, config, packet)
    altered_config, altered_packet = deepcopy(config), deepcopy(packet)
    mutate(altered_config, altered_packet)
    with pytest.raises((ValueError, TypeError)):
        validate(cloud, altered_config, altered_packet)
    validate(cloud, config, packet)


def test_hash_and_duplicate_key_mutations_refuse(cloud):
    config, packet = fixture_inputs(cloud)
    cj, ch = encoded(config)
    pj, ph = encoded(packet)
    with pytest.raises(ValueError, match="hash"):
        cloud.validate_inputs(cj, pj + " ", ch, ph)
    duplicated = cj[:-1] + ',"schema":"tpr-qc-six-config-v1"}'
    with pytest.raises(ValueError, match="duplicate"):
        cloud.validate_inputs(duplicated, pj, hashlib.sha256(duplicated.encode()).hexdigest(), ph)


def test_membership_lag_receipt_staleness_and_boundary_mutations(cloud):
    cutoff = datetime(2025, 1, 1, tzinfo=timezone.utc)
    def snap(age, receipt_age=1):
        return {"effective": cutoff - timedelta(days=age), "received": cutoff - timedelta(days=receipt_age)}
    oldest, latest = snap(21), snap(7)
    assert cloud.select_snapshot([oldest, latest, snap(6), snap(8, -1), snap(22)], cutoff) == latest
    assert cloud.select_snapshot([oldest], cutoff) == oldest
    assert cloud.select_snapshot([snap(6), snap(8, -1), snap(22)], cutoff) is None


def test_membership_unknown_is_not_zero_and_ties_use_native_id(cloud):
    config, packet = fixture_inputs(cloud)
    _, identities, frames = validate(cloud, config, packet)
    members = [{"ticker": ticker, "weight": weight, "symbol": ticker} for ticker, weight in
               [("SYNTHA", "0.2"), ("SYNTHB", "0.3"), ("SYNTHC", "0.1"), ("MISSING", "0.1"), ("UNKNOWN", None)]]
    selected, coverage = cloud.rank_members(identities, frames[cloud.DECISIONS[0]], members)
    assert selected == {"A": "SYNTHA"}
    assert coverage["unknown_input"] == {"count": 1, "weight": Fraction(3, 10)}
    assert coverage["missing_identity"]["count"] == 1
    assert coverage["ineligible"]["count"] == 1
    assert coverage["unknown_weight"]["count"] == 1
    frames[cloud.DECISIONS[0]]["states"][0]["score"] = "0"
    assert cloud.rank_members(identities, frames[cloud.DECISIONS[0]], members)[0] == {}
    assert coverage["scored"]["count"] == 1


def test_precapped_orders_keep_requested_and_do_not_recycle_sells(cloud):
    orders = cloud.plan_orders({"B"}, {"A": 100}, {"A": (10, 10000), "B": (10, 10000)}, 10000, 0)
    assert orders[0] == {"security_id": "A", "requested": -100, "submitted": -100, "reason": "complete"}
    assert orders[1] == {"security_id": "B", "requested": 100, "submitted": 0, "reason": "cash_buffer"}
    capped = cloud.plan_orders({"B"}, {}, {"B": (10, 500)}, 10000, 10000)
    assert capped == [{"security_id": "B", "requested": 100, "submitted": 5, "reason": "volume_cap"}]


def test_money_sizing_is_decimal_context_independent_and_retains_cash_buffer(cloud):
    marks = {"A": (Fraction("3.1"), 100000)}
    expected = cloud.plan_orders({"A"}, {}, marks, 100000, 1000)
    with localcontext() as context:
        context.prec = 3
        assert cloud.plan_orders({"A"}, {}, marks, 100000, 1000) == expected
    order = expected[0]
    assert order["requested"] == 3225
    assert order["submitted"] * (Fraction("3.1") * Fraction("1.001") + Fraction("0.01")) <= 970
    assert order["reason"] == "volume_and_cash_buffer"


def test_missing_price_refuses_without_rank_substitution(cloud):
    orders = cloud.plan_orders({"A", "B"}, {}, {"B": (10, 100000)}, 100000, 100000)
    assert orders[0] == {"security_id": "A", "requested": None, "submitted": 0, "reason": "missing_mark"}
    assert len(orders) == 2


def test_stub_clock_idempotence_and_missing_snapshot_do_not_liquidate(cloud):
    algo = cloud.TargetPriceSixUniverseAlgorithm()
    algo.time = datetime(2025, 1, 2, 9, 20)
    algo.utc_time = datetime(2025, 1, 2, 14, 20)
    algo.is_warming_up = False
    config, packet = fixture_inputs(cloud)
    algo._config, algo._identities, algo._frames = validate(cloud, config, packet)
    algo._snapshots, algo._attempted_days, algo._decision_coverage = [], set(), {}
    algo._decision_count, algo._refused_count, algo._reasons = 0, 0, {}
    algo._targets = {"A": "still-held-not-zeroed"}
    algo._rebalance()
    algo._rebalance()
    assert algo._decision_count == algo._refused_count == 1
    assert algo._targets == {"A": "still-held-not-zeroed"}
    assert algo._reasons == {"missing_lagged_membership": 1}


def test_stub_order_events_reconcile_signed_cash_fee_and_status(cloud):
    algo = cloud.TargetPriceSixUniverseAlgorithm()
    algo._cash_ledger, algo._fees = Fraction(1000), Fraction(0)
    algo._fill_events, algo._filled_shares, algo._reasons = 0, 0, {}
    algo._quantity_ledger = {}
    def event(quantity, price, fee="0", status="filled"):
        return SimpleNamespace(fill_quantity=quantity, fill_price=price, symbol=SimpleNamespace(id="synthetic-id"),
            order_fee=SimpleNamespace(value=SimpleNamespace(amount=fee)), status=status)
    algo.on_order_event(event(10, "10.01", "0.10"))
    assert algo._cash_ledger == Fraction("899.80")
    algo.on_order_event(event(-10, "9.99", "0.10"))
    assert algo._cash_ledger == Fraction("999.60")
    algo.on_order_event(event(0, "0", status="invalid"))
    assert algo._fees == Fraction("0.20")
    assert algo._fill_events == 2 and algo._filled_shares == 20
    assert algo._reasons == {"qc_invalid_order": 1}
    assert algo._quantity_ledger == {"synthetic-id": Fraction(0)}


def test_stub_native_split_and_dividend_bookkeeping(cloud):
    algo = cloud.TargetPriceSixUniverseAlgorithm()
    algo.time = datetime(2025, 1, 6)
    algo.is_warming_up = False
    algo._split_factors, algo._cash_ledger = {}, Fraction(1000)
    symbol = SimpleNamespace(id="synthetic-id")
    algo._quantity_ledger, algo._dividend_keys = {"synthetic-id": Fraction(10)}, set()
    split = SimpleNamespace(symbol=symbol, type="occurred", split_factor="0.5")
    dividend = SimpleNamespace(symbol=symbol, distribution="0.20")
    algo.on_data(SimpleNamespace(splits={"s": split}, dividends={"d": dividend}))
    assert algo._split_factors == {("synthetic-id", "2025-01-06"): Fraction(1, 2)}
    assert algo._cash_ledger == 1002
    assert algo._quantity_ledger == {"synthetic-id": Fraction(20)}
    with pytest.raises(ValueError, match="duplicate split"):
        algo.on_data(SimpleNamespace(splits={"s": split}, dividends={}))


def test_source_has_no_network_loader_or_raw_data_logging(cloud):
    source = SOURCE.read_text()
    assert "object_store.read(EXPECTED_PACKET_KEY)" in source
    assert "self.market_on_open_order" in source
    assert "__PACKET_KEY__" in source
    assert "research.quantconnect" not in source
    for forbidden in ("requests", "urlopen", "base64", "zlib", "open(", "print("):
        assert forbidden not in source


def test_cloud_template_binds_the_current_complete_freeze(cloud):
    freeze = ROOT / "research/target_price_revisions_qc/six_universe_freeze.json"
    assert hashlib.sha256(freeze.read_bytes()).hexdigest() == cloud.EXPECTED_FREEZE_SHA256


def test_live_refuses_before_reading_private_input_or_creating_subscriptions(cloud):
    algo = cloud.TargetPriceSixUniverseAlgorithm()
    algo.live_mode = True
    with pytest.raises(ValueError, match="live mode refused"):
        algo.initialize()


def test_stub_deferred_preopen_clock_refuses_instead_of_placing_late_moo(cloud):
    algo = cloud.TargetPriceSixUniverseAlgorithm()
    algo.time = datetime(2025, 1, 2, 9, 31)
    algo.is_warming_up = False
    algo._frames = {"2025-01-02": {}}
    algo._attempted_days, algo._reasons = set(), {}
    algo._decision_count = algo._refused_count = 0
    algo._rebalance()
    assert algo._refused_count == 1
    assert algo._reasons == {"late_decision_clock": 1}


def test_stub_prior_close_nav_excludes_next_morning_dividend_cash(cloud):
    algo = cloud.TargetPriceSixUniverseAlgorithm()
    algo.is_warming_up = False
    algo.time = datetime(2025, 1, 3, 16, 1)
    algo._cash_ledger = Fraction(1000)
    algo._max_cash_residual = algo._max_nav_residual = Fraction(0)
    algo._quantity_ledger, algo._position_ledger_mismatches = {}, 0
    algo.portfolio = SimpleNamespace(cash="1000", total_portfolio_value="11000", total_holdings_value="10000", values=lambda: [])
    logs = []
    algo.log = logs.append
    algo._daily_audit()
    assert algo._prior_close_nav == 11000
    assert algo._prior_close_day == date(2025, 1, 3)
    # Monday's native cash credit does not mutate the prior-close sizing NAV.
    algo.portfolio.cash = "1010"
    assert algo._prior_close_nav == 11000
    assert json.loads(logs[0].split(" ", 1)[1])["nav_ledger_residual"] == "0"


def test_stub_prior_raw_mark_adjusts_splits_but_never_uses_current_day_bar(cloud):
    algo = cloud.TargetPriceSixUniverseAlgorithm()
    algo.time = datetime(2025, 1, 6, 9, 20)
    config, packet = fixture_inputs(cloud)
    _, _, algo._frames = validate(cloud, config, packet)
    class Symbol:
        id = "synthetic-id"
    symbol = Symbol()
    prior = SimpleNamespace(time=datetime(2025, 1, 3, 9, 30), end_time=datetime(2025, 1, 3, 16), close="200", volume="10000")
    future = SimpleNamespace(time=datetime(2025, 1, 6, 9, 30), end_time=datetime(2025, 1, 6, 16), close="999", volume="999999")
    class History:
        def __getitem__(self, kind):
            return lambda *args: [prior, future]
    algo.history = History()
    algo.securities = {symbol: SimpleNamespace(has_data=True)}
    algo._split_factors = {("synthetic-id", "2025-01-06"): Fraction(1, 2)}
    assert algo._prior_mark(symbol) == (Fraction(100), Fraction(20000))
    algo._split_factors = {}
    assert algo._prior_mark(symbol) == (Fraction(200), Fraction(10000))
    prior.time = datetime(2025, 1, 2, 9, 30)
    prior.end_time = datetime(2025, 1, 2, 16)
    assert algo._prior_mark(symbol) is None


def test_stub_fee_uses_exact_dotnet_decimal_boundary(cloud, monkeypatch):
    system = ModuleType("System")
    system.Decimal = SimpleNamespace(Parse=lambda text, culture: Decimal(text))
    globalization = ModuleType("System.Globalization")
    globalization.CultureInfo = SimpleNamespace(InvariantCulture="invariant")
    monkeypatch.setitem(sys.modules, "System", system)
    monkeypatch.setitem(sys.modules, "System.Globalization", globalization)
    cloud.CashAmount = lambda value, currency: (value, currency)
    cloud.OrderFee = lambda value: value
    fee = cloud.CentPerShareFee()
    assert fee.get_order_fee(SimpleNamespace(order=SimpleNamespace(quantity=-123))) == (Decimal("1.23"), "USD")


def test_stub_reverse_split_cash_in_lieu_is_reconstructed_not_absorbed(cloud):
    algo = cloud.TargetPriceSixUniverseAlgorithm()
    algo.time = datetime(2025, 1, 6)
    algo.is_warming_up = False
    algo._split_factors, algo._dividend_keys = {}, set()
    algo._cash_ledger, algo._quantity_ledger = Fraction(1000), {"synthetic-id": Fraction(3)}
    class Symbol:
        id = "synthetic-id"
    symbol = Symbol()
    algo.securities = {symbol: SimpleNamespace(get_last_data=lambda: SimpleNamespace(price="20"))}
    split = SimpleNamespace(symbol=symbol, type="occurred", split_factor="2", reference_price="10")
    algo.on_data(SimpleNamespace(splits={"s": split}, dividends={}))
    assert algo._quantity_ledger == {"synthetic-id": Fraction(1)}
    assert algo._cash_ledger == 1010


def test_stub_quantity_drift_fails_accounting_summary_even_if_native_cash_matches(cloud):
    algo = cloud.TargetPriceSixUniverseAlgorithm()
    algo.is_warming_up = False
    algo.time = datetime(2025, 1, 6, 16, 1)
    algo._cash_ledger = Fraction(1000)
    algo._quantity_ledger, algo._position_ledger_mismatches = {"synthetic-id": Fraction(10)}, 0
    algo._max_cash_residual = algo._max_nav_residual = Fraction(0)
    algo.portfolio = SimpleNamespace(cash="1000", total_portfolio_value="1100", total_holdings_value="100",
        values=lambda: [SimpleNamespace(symbol=SimpleNamespace(id="synthetic-id"), quantity=11)])
    algo.log = lambda value: None
    algo._daily_audit()
    assert algo._max_cash_residual == 0
    assert algo._position_ledger_mismatches == 1


def test_stub_stale_prior_nav_refuses_even_when_under_seven_days_old(cloud):
    algo = cloud.TargetPriceSixUniverseAlgorithm()
    algo.is_warming_up = False
    algo.time = datetime(2025, 1, 6, 9, 20)
    config, packet = fixture_inputs(cloud)
    _, _, algo._frames = validate(cloud, config, packet)
    algo._attempted_days, algo._reasons, algo._symbols, algo._targets = set(), {}, {}, {}
    algo._decision_count = algo._refused_count = 0
    algo._decision_coverage = {"2025-01-06": {"synthetic": True}}
    algo._prepare_targets = lambda day: None
    algo._prior_close_day = date(2025, 1, 2)
    algo._prior_close_nav = Fraction(1000)
    algo.portfolio = SimpleNamespace(cash="1000", values=lambda: [])
    algo.log = lambda value: None
    algo._rebalance()
    assert algo._refused_count == 1
    assert algo._reasons == {"missing_prior_close_nav": 1}
