"""Synthetic-only guard and order-path checks; no QC cloud call or market data."""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import sys
import types
from decimal import Decimal
from pathlib import Path

import pytest


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "research" / "insider_buying_qc_stock_order_study.py"
)
FIRST = dt.date(2026, 9, 1)
SESSIONS = [(FIRST + dt.timedelta(days=i)).isoformat() for i in range(22)]


class _Symbol:
    def __init__(self, ticker: str, sid: str) -> None:
        self.value = ticker
        self.id = sid


class _Security:
    def __init__(self, symbol: _Symbol) -> None:
        self.symbol = symbol
        self.is_tradable = True
        self.is_delisted = False
        self.has_data = True
        self.price = 100
        self.last_data = types.SimpleNamespace(
            end_time=dt.datetime(2026, 9, 1, 16, 0), is_fill_forward=False
        )
        self.normalization_mode = None

    def get_last_data(self) -> object:
        return self.last_data

    def set_data_normalization_mode(self, mode: object) -> None:
        self.normalization_mode = mode


class _Algorithm:
    def __init__(self) -> None:
        self.live_mode = False
        self.is_warming_up = False
        self.time = dt.datetime(2026, 9, 1, 16, 1)
        self.utc_time = dt.datetime(2026, 9, 1, 20, 1)
        self.securities: dict[_Symbol, _Security] = {}
        self.subscriptions: list[tuple[str, dict[str, object]]] = []
        self.portfolio = types.SimpleNamespace(cash=100_000)
        self.holdings: dict[_Symbol, object] = {}
        self.orders: list[tuple[_Symbol, int, str, int]] = []
        self.logs: list[str] = []
        self.date_rules = types.SimpleNamespace(every_day=lambda symbol: ("every", symbol))
        self.time_rules = types.SimpleNamespace(
            after_market_close=lambda symbol, minutes: ("after", symbol, minutes)
        )
        self.schedule = types.SimpleNamespace(on=lambda *items: None)
        self.object_store = types.SimpleNamespace(content={})
        self.object_store.contains_key = lambda key: key in self.object_store.content
        self.object_store.read_bytes = lambda key: self.object_store.content[key]

    def set_time_zone(self, value: str) -> None:
        self.zone = value

    def set_start_date(self, *parts: int) -> None:
        self.start = parts

    def set_end_date(self, *parts: int) -> None:
        self.end = parts

    def set_cash(self, amount: int) -> None:
        self.portfolio.cash = amount

    def set_brokerage_model(self, brokerage: object, account: object) -> None:
        self.brokerage_model = (brokerage, account)

    def add_equity(self, ticker: str, resolution: object, **kwargs: object) -> object:
        self.subscriptions.append((ticker, kwargs))
        symbol = _Symbol(ticker, f"{ticker} SID")
        self.securities[symbol] = _Security(symbol)
        self.holdings[symbol] = types.SimpleNamespace(quantity=0)
        return types.SimpleNamespace(symbol=symbol)

    def market_on_open_order(self, symbol: _Symbol, quantity: int, tag: str) -> object:
        order_id = len(self.orders) + 1
        self.orders.append((symbol, quantity, tag, order_id))
        return types.SimpleNamespace(status="submitted", order_id=order_id)

    def log(self, message: str) -> None:
        self.logs.append(message)

    def __getitem__(self, symbol: _Symbol) -> object:
        return self.holdings[symbol]


@pytest.fixture
def study(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    lean = types.ModuleType("AlgorithmImports")
    lean.QCAlgorithm = _Algorithm
    lean.Resolution = types.SimpleNamespace(MINUTE="minute")
    lean.DataNormalizationMode = types.SimpleNamespace(RAW="raw")
    lean.OrderStatus = types.SimpleNamespace(
        FILLED="filled", PARTIALLY_FILLED="partially_filled", CANCELED="canceled",
        INVALID="invalid",
    )
    lean.BrokerageName = types.SimpleNamespace(QUANT_CONNECT_BROKERAGE="qc-paper-model")
    lean.AccountType = types.SimpleNamespace(CASH="cash")
    monkeypatch.setitem(sys.modules, "AlgorithmImports", lean)
    spec = importlib.util.spec_from_file_location("ib_qc_stock_study_under_test", SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(ticker: str = "ACME", signal_id: str = "S1", **updates: object) -> dict:
    row = {
        "signal_id": signal_id,
        "ticker": ticker,
        "qc_symbol_id": f"{ticker} SID",
        "source_event_sha256": "a" * 64,
        "mapping_first_session": "2026-01-01",
        "mapping_last_session": "2027-01-01",
        "available_at_utc": "2026-09-01T18:00:00+00:00",
        "decision_session": SESSIONS[0],
        "entry_session": SESSIONS[1],
        "exit_session": SESSIONS[21],
    }
    row.update(updates)
    return row


def _manifest(rows: list[dict] | None = None, **updates: object) -> bytes:
    payload = {
        "schema": "insider-qc-stock-order-study-v1",
        "source_manifest_sha256": "b" * 64,
        "security_master_sha256": "c" * 64,
        "calendar_sha256": hashlib.sha256(
            json.dumps(SESSIONS, separators=(",", ":")).encode()
        ).hexdigest(),
        "outcome_vintage_sha256": "d" * 64,
        "sessions": SESSIONS,
        "signals": [_row()] if rows is None else rows,
    }
    payload.update(updates)
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _gate(manifest: bytes, **updates: object) -> bytes:
    payload = {
        "schema": "insider-qc-single-backtest-gate-v1",
        "scope": "single-research-backtest-only",
        "registered_look_id": "IB5-TEST-LOOK-1",
        "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
        "rights_record_sha256": "e" * 64,
        "outcome_vintage_sha256": "d" * 64,
    }
    payload.update(updates)
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _configured(study: types.ModuleType, rows: list[dict] | None = None) -> object:
    manifest = _manifest(rows)
    gate = _gate(manifest)
    study.RESEARCH_BACKTEST_ENABLED = True
    study.SIGNAL_OBJECT_STORE_KEY = "insider-buying/synthetic/signals.json"
    study.APPROVED_SIGNAL_SHA256 = hashlib.sha256(manifest).hexdigest()
    study.GATE_OBJECT_STORE_KEY = "insider-buying/synthetic/gate.json"
    study.APPROVED_GATE_SHA256 = hashlib.sha256(gate).hexdigest()
    study.APPROVED_LOOK_ID = "IB5-TEST-LOOK-1"
    algorithm = study.InsiderBuyingStockOrderStudy()
    algorithm.object_store.content[study.SIGNAL_OBJECT_STORE_KEY] = manifest
    algorithm.object_store.content[study.GATE_OBJECT_STORE_KEY] = gate
    algorithm.initialize()
    # The fake portfolio is separate from the algorithm stub's attributes.
    algorithm.portfolio = _Portfolio(algorithm.portfolio.cash, algorithm.holdings)
    return algorithm


class _Portfolio:
    def __init__(self, cash: int, holdings: dict[_Symbol, object]) -> None:
        self.cash = cash
        self.holdings = holdings

    def __getitem__(self, symbol: _Symbol) -> object:
        return self.holdings[symbol]


def _fill(study: types.ModuleType, algorithm: object, order: tuple) -> None:
    symbol, quantity, _tag, order_id = order
    algorithm.time = dt.datetime.combine(
        algorithm._pending[order_id].fill_session, dt.time(9, 31)
    )
    algorithm.portfolio[symbol].quantity += quantity
    algorithm.on_order_event(types.SimpleNamespace(
        status="filled", order_id=order_id, symbol=symbol,
        fill_quantity=quantity, fill_price=100,
    ))


def test_default_is_inert_before_object_store_or_subscription(study: types.ModuleType) -> None:
    assert study.RESEARCH_BACKTEST_ENABLED is False
    assert study.SIGNAL_OBJECT_STORE_KEY == ""
    algorithm = study.InsiderBuyingStockOrderStudy()
    with pytest.raises(study.StockStudyRefusal, match="gate disabled"):
        algorithm.initialize()
    assert algorithm.securities == {} and algorithm.orders == []
    algorithm.live_mode = True
    with pytest.raises(study.StockStudyRefusal, match="live mode"):
        algorithm.initialize()


@pytest.mark.parametrize("raw,reason", [
    (_manifest(calendar_sha256="0" * 64), "calendar digest"),
    (_manifest([_row(exit_session=SESSIONS[20])]), "next-open/20-session"),
    (_manifest([_row(mapping_last_session=SESSIONS[21])]), "mapping interval"),
    (_manifest([_row(), _row(signal_id="S2")]), "overlapping"),
    (_manifest([_row(available_at_utc="2026-09-02T00:00:00+00:00")]), "availability"),
    (_manifest([_row(qc_symbol_id="WRONG")]), None),
])
def test_manifest_time_and_identity_guards(
    study: types.ModuleType, raw: bytes, reason: str | None
) -> None:
    if reason is None:
        assert study.parse_study_manifest(raw, hashlib.sha256(raw).hexdigest())
    else:
        with pytest.raises(study.StockStudyRefusal, match=reason):
            study.parse_study_manifest(raw, hashlib.sha256(raw).hexdigest())


def test_manifest_rejects_digest_duplicates_nonfinite_and_holdout(
    study: types.ModuleType,
) -> None:
    raw = _manifest()
    with pytest.raises(study.StockStudyRefusal, match="digest"):
        study.parse_study_manifest(raw, "0" * 64)
    for payload, reason in (
        (b'{"schema":1,"schema":2}', "duplicate"),
        (b'{"value":NaN}', "nonfinite"),
    ):
        with pytest.raises(study.StockStudyRefusal, match=reason):
            study.parse_study_manifest(payload, hashlib.sha256(payload).hexdigest())
    late = _manifest(sessions=[*SESSIONS, "2027-09-01"])
    with pytest.raises(study.StockStudyRefusal, match="holdout"):
        study.parse_study_manifest(late, hashlib.sha256(late).hexdigest())


def test_manifest_refuses_same_day_capacity_before_subscription(
    study: types.ModuleType,
) -> None:
    rows = [_row(f"A{chr(65 + i)}", f"S{i:02d}") for i in range(21)]
    raw = _manifest(rows)
    gate = _gate(raw)
    study.RESEARCH_BACKTEST_ENABLED = True
    study.SIGNAL_OBJECT_STORE_KEY = "insider-buying/synthetic/signals.json"
    study.APPROVED_SIGNAL_SHA256 = hashlib.sha256(raw).hexdigest()
    study.GATE_OBJECT_STORE_KEY = "insider-buying/synthetic/gate.json"
    study.APPROVED_GATE_SHA256 = hashlib.sha256(gate).hexdigest()
    study.APPROVED_LOOK_ID = "IB5-TEST-LOOK-1"
    algorithm = study.InsiderBuyingStockOrderStudy()
    algorithm.object_store.content[study.SIGNAL_OBJECT_STORE_KEY] = raw
    algorithm.object_store.content[study.GATE_OBJECT_STORE_KEY] = gate
    with pytest.raises(study.StockStudyRefusal, match="capacity"):
        algorithm.initialize()
    assert algorithm.subscriptions == [] and algorithm.orders == []


def test_manifest_refuses_next_open_exit_reuse_before_exit_fill(
    study: types.ModuleType,
) -> None:
    sessions = [(FIRST + dt.timedelta(days=i)).isoformat() for i in range(42)]
    rows = [_row(f"A{chr(65 + i)}", f"S{i:02d}") for i in range(20)]
    rows.append(_row(
        "AZ", "S20", decision_session=sessions[20], entry_session=sessions[21],
        exit_session=sessions[41],
    ))
    raw = _manifest(
        rows, sessions=sessions,
        calendar_sha256=hashlib.sha256(
            json.dumps(sessions, separators=(",", ":")).encode()
        ).hexdigest(),
    )
    with pytest.raises(study.StockStudyRefusal, match="capacity"):
        study.parse_study_manifest(raw, hashlib.sha256(raw).hexdigest())


def test_manifest_accepts_exact_capacity_and_reuse_after_filled_exit(
    study: types.ModuleType,
) -> None:
    sessions = [(FIRST + dt.timedelta(days=i)).isoformat() for i in range(43)]
    rows = [_row(f"A{chr(65 + i)}", f"S{i:02d}") for i in range(20)]
    rows.append(_row(
        "AZ", "S20", decision_session=sessions[21], entry_session=sessions[22],
        exit_session=sessions[42],
    ))
    raw = _manifest(
        rows, sessions=sessions,
        calendar_sha256=hashlib.sha256(
            json.dumps(sessions, separators=(",", ":")).encode()
        ).hexdigest(),
    )
    parsed = study.parse_study_manifest(raw, hashlib.sha256(raw).hexdigest())
    assert len(parsed.signals) == 21


def test_manifest_refuses_impossible_fixed_cash_slot_capacity(
    study: types.ModuleType, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(study, "SLOT_BUDGET", Decimal("90001"))
    raw = _manifest()
    with pytest.raises(study.StockStudyRefusal, match="capacity"):
        study.parse_study_manifest(raw, hashlib.sha256(raw).hexdigest())


def test_gate_hash_scope_look_and_vintage_must_match(study: types.ModuleType) -> None:
    raw = _manifest()
    manifest = study.parse_study_manifest(raw, hashlib.sha256(raw).hexdigest())
    for gate, reason in (
        (_gate(raw, scope="live"), "scope"),
        (_gate(raw, registered_look_id="OTHER"), "look ID"),
        (_gate(raw, manifest_sha256="0" * 64), "manifest"),
        (_gate(raw, outcome_vintage_sha256="0" * 64), "vintage"),
    ):
        with pytest.raises(study.StockStudyRefusal, match=reason):
            study.parse_study_gate(gate, hashlib.sha256(gate).hexdigest(),
                                   manifest, "IB5-TEST-LOOK-1")


def test_multi_signal_batch_is_deterministic_and_next_open_only(
    study: types.ModuleType,
) -> None:
    algorithm = _configured(study, [_row(), _row("BETA", "S2")])
    assert algorithm.subscriptions[0] == (
        "SPY", {"extended_market_hours": True, "fill_forward": False}
    )
    assert algorithm.subscriptions[1] == ("ACME", {"fill_forward": False})
    assert algorithm.brokerage_model == ("qc-paper-model", "cash")
    algorithm.utc_time = dt.datetime(2026, 9, 1, 17, 59)
    with pytest.raises(study.StockStudyRefusal, match="availability"):
        algorithm._after_market_close()
    assert algorithm.orders == []
    algorithm = _configured(study, [_row(), _row("BETA", "S2")])
    algorithm._after_market_close()
    assert [(symbol.value, quantity) for symbol, quantity, _, _ in algorithm.orders] == [
        ("ACME", 42), ("BETA", 42)
    ]
    assert all("ENTRY" in tag for _, _, tag, _ in algorithm.orders)
    with pytest.raises(study.StockStudyRefusal, match="session drift"):
        algorithm._after_market_close()


def test_underfill_refuses_entire_same_day_batch_before_any_order(
    study: types.ModuleType,
) -> None:
    algorithm = _configured(study, [_row(), _row("BETA", "S2")])
    algorithm.portfolio.cash = 10_400
    with pytest.raises(study.StockStudyRefusal, match="underfill"):
        algorithm._after_market_close()
    assert algorithm.orders == []

    absent_second = _configured(study, [_row(), _row("BETA", "S2")])
    beta = next(s for s in absent_second.securities.values() if s.symbol.value == "BETA")
    beta.has_data = False
    with pytest.raises(study.StockStudyRefusal, match="missing"):
        absent_second._after_market_close()
    assert absent_second.orders == []


def test_entry_then_exact_twentieth_session_exit_and_completion(
    study: types.ModuleType,
) -> None:
    algorithm = _configured(study)
    for index, session in enumerate(SESSIONS):
        day = dt.date.fromisoformat(session)
        if index == 1:
            _fill(study, algorithm, algorithm.orders[0])
            algorithm.portfolio.cash -= 4_200
        if index == 21:
            _fill(study, algorithm, algorithm.orders[1])
        algorithm.time = dt.datetime.combine(day, dt.time(16, 1))
        algorithm.utc_time = dt.datetime.combine(day, dt.time(20, 1))
        for security in algorithm.securities.values():
            security.last_data.end_time = dt.datetime.combine(day, dt.time(16, 0))
        algorithm._after_market_close()
        if index < 20:
            assert len(algorithm.orders) == 1
        elif index == 20:
            assert algorithm.orders[1][1] == -42
            assert "EXIT" in algorithm.orders[1][2]
    algorithm.on_end_of_algorithm()
    assert any("IBQC_STUDY_ORDER_PATH_COMPLETE" in log for log in algorithm.logs)


def test_missing_bar_partial_fill_delisting_and_no_fabricated_completion(
    study: types.ModuleType,
) -> None:
    missing = _configured(study)
    security = next(s for s in missing.securities.values() if s.symbol.value == "ACME")
    security.has_data = False
    with pytest.raises(study.StockStudyRefusal, match="missing"):
        missing._after_market_close()
    assert missing.orders == []

    filled_forward = _configured(study)
    security = next(s for s in filled_forward.securities.values() if s.symbol.value == "ACME")
    security.last_data.is_fill_forward = True
    with pytest.raises(study.StockStudyRefusal, match="missing"):
        filled_forward._after_market_close()
    assert filled_forward.orders == []

    partial = _configured(study)
    partial._after_market_close()
    pending = partial.orders[0]
    partial.time = dt.datetime(2026, 9, 2, 9, 31)
    with pytest.raises(study.StockStudyRefusal, match="partial"):
        partial.on_order_event(types.SimpleNamespace(
            status="partially_filled", order_id=pending[3], symbol=pending[0],
            fill_quantity=1, fill_price=100,
        ))

    delisted = _configured(study)
    delisted._after_market_close()
    with pytest.raises(study.StockStudyRefusal, match="delisted"):
        delisted.on_data(types.SimpleNamespace(delistings={delisted.orders[0][0]: object()}))

    incomplete = _configured(study)
    incomplete._after_market_close()
    with pytest.raises(study.StockStudyRefusal, match="unproved"):
        incomplete.on_end_of_algorithm()


@pytest.mark.parametrize("position_state", ["pending-entry", "held", "pending-exit"])
@pytest.mark.parametrize("split_type", ["warning", "split_occurred"])
def test_split_notification_refuses_affected_order_or_position_before_exit_quantity_drifts(
    study: types.ModuleType, position_state: str, split_type: str,
) -> None:
    algorithm = _configured(study)
    algorithm._after_market_close()
    symbol = algorithm.orders[0][0]
    if position_state != "pending-entry":
        _fill(study, algorithm, algorithm.orders[0])
        if position_state == "pending-exit":
            row = algorithm._manifest.signals[0]
            algorithm._submit(row, symbol, "EXIT", -42, row.exit_session)
    before_orders = list(algorithm.orders)
    with pytest.raises(study.StockStudyRefusal, match="split"):
        algorithm.on_data(types.SimpleNamespace(
            delistings={}, splits={symbol: types.SimpleNamespace(type=split_type)},
        ))
    assert algorithm.orders == before_orders


def test_unrelated_clock_split_does_not_discard_held_security(
    study: types.ModuleType,
) -> None:
    algorithm = _configured(study)
    algorithm._after_market_close()
    _fill(study, algorithm, algorithm.orders[0])
    clock = algorithm._clock_symbol
    algorithm.on_data(types.SimpleNamespace(
        delistings={}, splits={clock: types.SimpleNamespace(type="split_occurred")},
    ))
    assert len(algorithm._active) == 1


def test_missing_intermediate_holding_bar_refuses_entire_study(
    study: types.ModuleType,
) -> None:
    algorithm = _configured(study)
    algorithm._after_market_close()
    _fill(study, algorithm, algorithm.orders[0])
    acme = next(s for s in algorithm.securities.values() if s.symbol.value == "ACME")
    entry_day = dt.date.fromisoformat(SESSIONS[1])
    algorithm.time = dt.datetime.combine(entry_day, dt.time(16, 1))
    algorithm.utc_time = dt.datetime.combine(entry_day, dt.time(20, 1))
    acme.last_data.end_time = dt.datetime.combine(entry_day, dt.time(16, 0))
    algorithm._after_market_close()

    missing_day = dt.date.fromisoformat(SESSIONS[2])
    algorithm.time = dt.datetime.combine(missing_day, dt.time(16, 1))
    algorithm.utc_time = dt.datetime.combine(missing_day, dt.time(20, 1))
    with pytest.raises(study.StockStudyRefusal, match="missing"):
        algorithm._after_market_close()
    assert len(algorithm.orders) == 1


def test_spy_signal_cannot_use_a_fill_forward_clock_bar(
    study: types.ModuleType,
) -> None:
    algorithm = _configured(study, [_row("SPY")])
    clock = next(s for s in algorithm.securities.values() if s.symbol.value == "SPY")
    clock.last_data.is_fill_forward = True
    with pytest.raises(study.StockStudyRefusal, match="missing"):
        algorithm._after_market_close()
    assert algorithm.orders == []


def test_wrong_fill_session_and_unexpected_terminal_order_refuse(
    study: types.ModuleType,
) -> None:
    algorithm = _configured(study)
    algorithm._after_market_close()
    symbol, quantity, _tag, order_id = algorithm.orders[0]
    with pytest.raises(study.StockStudyRefusal, match="session drift"):
        algorithm.on_order_event(types.SimpleNamespace(
            status="filled", order_id=order_id, symbol=symbol,
            fill_quantity=quantity, fill_price=100,
        ))
    with pytest.raises(study.StockStudyRefusal, match="unexpected"):
        algorithm.on_order_event(types.SimpleNamespace(
            status="filled", order_id=999, symbol=symbol,
            fill_quantity=quantity, fill_price=100,
        ))


def test_opening_gap_or_cash_reserve_breach_cannot_complete(
    study: types.ModuleType,
) -> None:
    gap = _configured(study)
    gap._after_market_close()
    symbol, quantity, _tag, order_id = gap.orders[0]
    gap.time = dt.datetime(2026, 9, 2, 9, 31)
    with pytest.raises(study.StockStudyRefusal, match="slot budget"):
        gap.on_order_event(types.SimpleNamespace(
            status="filled", order_id=order_id, symbol=symbol,
            fill_quantity=quantity, fill_price=120,
        ))

    reserve = _configured(study)
    reserve._after_market_close()
    symbol, quantity, _tag, order_id = reserve.orders[0]
    reserve.time = dt.datetime(2026, 9, 2, 9, 31)
    reserve.portfolio.cash = 9_999
    with pytest.raises(study.StockStudyRefusal, match="cash reserve"):
        reserve.on_order_event(types.SimpleNamespace(
            status="filled", order_id=order_id, symbol=symbol,
            fill_quantity=quantity, fill_price=100,
        ))


# Section 119 (Claude review): isolate the study's per-session and per-order
# research-only gates, which no earlier test reached after initialization.
@pytest.mark.parametrize("state", ["live", "disabled"])
def test_session_handler_rechecks_live_mode_and_the_research_gate(
    study: types.ModuleType, state: str,
) -> None:
    algorithm = _configured(study)
    if state == "live":
        algorithm.live_mode = True
    else:
        study.RESEARCH_BACKTEST_ENABLED = False
    with pytest.raises(study.StockStudyRefusal, match="live or unapproved order path"):
        algorithm._after_market_close()
    assert algorithm.orders == []


@pytest.mark.parametrize("state", ["live", "disabled"])
def test_order_submission_rechecks_live_mode_and_the_research_gate(
    study: types.ModuleType, state: str,
) -> None:
    algorithm = _configured(study)
    row = algorithm._manifest.signals[0]
    symbol = next(iter(algorithm.securities))
    if state == "live":
        algorithm.live_mode = True
    else:
        study.RESEARCH_BACKTEST_ENABLED = False
    with pytest.raises(study.StockStudyRefusal, match="research-only order gate disabled"):
        algorithm._submit(row, symbol, "ENTRY", 1, row.decision_session)
    assert algorithm.orders == []


@pytest.mark.parametrize("side,quantity,reason", [
    ("ENTRY", 0, "zero or malformed order quantity"),
    ("ENTRY", 1.0, "zero or malformed order quantity"),
    ("ENTRY", True, "zero or malformed order quantity"),
    ("ENTRY", -1, "order direction drifted"),
    ("EXIT", 1, "order direction drifted"),
])
def test_order_submission_refuses_malformed_quantity_or_direction(
    study: types.ModuleType, side: str, quantity: object, reason: str,
) -> None:
    algorithm = _configured(study)
    row = algorithm._manifest.signals[0]
    symbol = next(iter(algorithm.securities))
    with pytest.raises(study.StockStudyRefusal, match=reason):
        algorithm._submit(row, symbol, side, quantity, row.decision_session)
    assert algorithm.orders == []
