"""Offline contract checks for the inert Insider QC order skeleton."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import types
from datetime import datetime
from pathlib import Path

import pytest


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "research"
    / "insider_buying"
    / "qc_order_algorithm.py"
)


class _Symbol:
    def __init__(self, ticker: str, sid: str) -> None:
        self.value = ticker
        self.id = sid


class _Security:
    def __init__(self, ticker: str, sid: str) -> None:
        self.symbol = _Symbol(ticker, sid)
        self.is_tradable = True
        self.is_delisted = False
        self.has_data = True
        self.price = 100.0
        self.normalization_mode = None
        self.last_data = types.SimpleNamespace(end_time=datetime(2026, 9, 24, 16, 0))

    def get_last_data(self) -> object:
        return self.last_data

    def set_data_normalization_mode(self, mode: object) -> None:
        self.normalization_mode = mode


class _Algorithm:
    def __init__(self) -> None:
        self.live_mode = False
        self.is_warming_up = False
        self.securities: dict[object, _Security] = {}
        self.portfolio: dict[object, object] = {}
        self.time = datetime(2026, 9, 24, 16, 1)
        self.utc_time = datetime(2026, 9, 24, 20, 1)
        self.orders: list[tuple[object, int, str]] = []
        self.logs: list[str] = []
        self.error_messages: list[str] = []
        self.calendar = types.SimpleNamespace(
            every_day=lambda symbol: ("every_day", symbol),
        )
        self.clock = types.SimpleNamespace(
            after_market_close=lambda symbol, minutes: (
                "after_market_close", symbol, minutes
            ),
        )
        self.schedule = types.SimpleNamespace(on=self._schedule_on)
        self.date_rules = self.calendar
        self.time_rules = self.clock
        self.scheduled = []
        self.transactions = types.SimpleNamespace(orders_count=0)
        self.object_store = types.SimpleNamespace(
            content={},
            contains_key=lambda key: key in self.object_store.content,
            read_bytes=lambda key: self.object_store.content[key],
        )

    def _schedule_on(self, *args: object) -> None:
        self.scheduled.append(args)

    def set_time_zone(self, zone: str) -> None:
        self.zone = zone

    def set_start_date(self, *parts: int) -> None:
        self.start = parts

    def set_end_date(self, *parts: int) -> None:
        self.end = parts

    def set_cash(self, amount: int) -> None:
        self.cash = amount

    def add_equity(self, ticker: str, resolution: object, **kwargs: object) -> _Security:
        sid = "SPY SID" if ticker == "SPY" else "ACME SID"
        security = _Security(ticker, sid)
        self.securities[security.symbol] = security
        self.portfolio[security.symbol] = types.SimpleNamespace(invested=False)
        return security

    def market_on_open_order(self, symbol: object, quantity: int, tag: str = "") -> object:
        self.orders.append((symbol, quantity, tag))
        self.transactions.orders_count += 1
        return types.SimpleNamespace(status="submitted")

    def log(self, message: str) -> None:
        self.logs.append(message)

    def error(self, message: str) -> None:
        self.error_messages.append(message)


@pytest.fixture
def qc_module(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    lean = types.ModuleType("AlgorithmImports")
    lean.QCAlgorithm = _Algorithm
    lean.Resolution = types.SimpleNamespace(MINUTE="minute")
    lean.DataNormalizationMode = types.SimpleNamespace(RAW="raw")
    lean.OrderStatus = types.SimpleNamespace(FILLED="filled", INVALID="invalid")
    monkeypatch.setitem(sys.modules, "AlgorithmImports", lean)
    spec = importlib.util.spec_from_file_location("insider_qc_order_under_test", SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest(**row_updates: object) -> bytes:
    row = {
        "signal_id": "synthetic-001",
        "ticker": "ACME",
        "qc_symbol_id": "ACME SID",
        "source_event_sha256": "a" * 64,
        "mapping_first_session": "2026-01-01",
        "mapping_last_session": "2026-12-31",
        "decision_session": "2026-09-24",
        "available_at_utc": "2026-09-24T19:00:00+00:00",
    }
    row.update(row_updates)
    return json.dumps(
        {
            "schema": "insider-qc-order-skeleton-manifest-v1",
            "source_manifest_sha256": "b" * 64,
            "security_master_sha256": "c" * 64,
            "calendar_sha256": "d" * 64,
            "window_start": "2026-09-01",
            "window_end": "2026-10-31",
            "signals": [row],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _configured(qc_module: types.ModuleType, raw: bytes | None = None) -> object:
    raw = _manifest() if raw is None else raw
    qc_module.SIGNAL_OBJECT_STORE_KEY = "insider-buying/synthetic-test/manifest.json"
    qc_module.APPROVED_SIGNAL_MANIFEST_SHA256 = hashlib.sha256(raw).hexdigest()
    qc_module.RESEARCH_ENTRY_SHARES = 1
    algorithm = qc_module.InsiderBuyingOrderSkeleton()
    algorithm.object_store.content[qc_module.SIGNAL_OBJECT_STORE_KEY] = raw
    algorithm.initialize()
    return algorithm


def test_defaults_refuse_a_run_and_do_not_enable_orders(qc_module: types.ModuleType) -> None:
    assert qc_module.SIGNAL_OBJECT_STORE_KEY == ""
    assert qc_module.APPROVED_SIGNAL_MANIFEST_SHA256 == ""
    assert qc_module.RESEARCH_ENTRY_SHARES == 0
    with pytest.raises(qc_module.SignalManifestError, match="unbound"):
        qc_module.InsiderBuyingOrderSkeleton().initialize()


@pytest.mark.parametrize(
    "raw,reason",
    [
        (b'{"schema":1,"schema":2}', "duplicate"),
        (_manifest(source_event_sha256="z" * 64), "source_event_sha256"),
        (_manifest(mapping_last_session="2026-09-23"), "mapping interval"),
        (_manifest(available_at_utc="2026-09-25T01:00:00+00:00"), "availability"),
        (_manifest(available_at_utc="2026-09-24T19:00:00"), "available_at_utc"),
    ],
)
def test_invalid_or_future_manifest_refuses(
    qc_module: types.ModuleType, raw: bytes, reason: str
) -> None:
    with pytest.raises(qc_module.SignalManifestError, match=reason):
        qc_module.parse_signal_manifest(raw, hashlib.sha256(raw).hexdigest())


def test_exact_raw_digest_is_required(qc_module: types.ModuleType) -> None:
    with pytest.raises(qc_module.SignalManifestError, match="digest"):
        qc_module.parse_signal_manifest(_manifest(), "0" * 64)


def test_object_store_missing_or_changed_bytes_refuse_before_subscription(
    qc_module: types.ModuleType,
) -> None:
    raw = _manifest()
    qc_module.SIGNAL_OBJECT_STORE_KEY = "insider-buying/synthetic-test/manifest.json"
    qc_module.APPROVED_SIGNAL_MANIFEST_SHA256 = hashlib.sha256(raw).hexdigest()
    qc_module.RESEARCH_ENTRY_SHARES = 1
    missing = qc_module.InsiderBuyingOrderSkeleton()
    with pytest.raises(qc_module.SignalManifestError, match="key is missing"):
        missing.initialize()
    changed = qc_module.InsiderBuyingOrderSkeleton()
    changed.object_store.content[qc_module.SIGNAL_OBJECT_STORE_KEY] = raw + b" "
    with pytest.raises(qc_module.SignalManifestError, match="digest"):
        changed.initialize()
    assert changed.securities == {} and changed.orders == []


def test_mapping_identity_is_checked_before_scheduling(qc_module: types.ModuleType) -> None:
    raw = _manifest(qc_symbol_id="OTHER SID")
    qc_module.SIGNAL_OBJECT_STORE_KEY = "insider-buying/synthetic-test/manifest.json"
    qc_module.APPROVED_SIGNAL_MANIFEST_SHA256 = hashlib.sha256(raw).hexdigest()
    qc_module.RESEARCH_ENTRY_SHARES = 1
    algorithm = qc_module.InsiderBuyingOrderSkeleton()
    algorithm.object_store.content[qc_module.SIGNAL_OBJECT_STORE_KEY] = raw
    with pytest.raises(qc_module.SignalManifestError, match="QC Symbol ID"):
        algorithm.initialize()


def test_order_requires_public_availability_and_is_once_only(qc_module: types.ModuleType) -> None:
    algorithm = _configured(qc_module)
    assert algorithm.zone == "America/New_York"
    assert algorithm.scheduled and algorithm.orders == []
    algorithm.utc_time = datetime(2026, 9, 24, 18, 59)
    with pytest.raises(qc_module.SignalManifestError, match="availability"):
        algorithm._after_market_close()
    assert algorithm.orders == []

    fresh = _configured(qc_module)
    fresh._after_market_close()
    fresh._after_market_close()
    assert len(fresh.orders) == 1
    symbol, quantity, tag = fresh.orders[0]
    assert symbol.value == "ACME"
    assert quantity == 1
    assert tag.startswith("IBQC:")
    assert fresh.attempted_orders == 1


def test_completion_requires_real_order_fill(qc_module: types.ModuleType) -> None:
    algorithm = _configured(qc_module)
    algorithm._after_market_close()
    with pytest.raises(qc_module.SignalManifestError, match="submission/fill incomplete"):
        algorithm.on_end_of_algorithm()
    algorithm.on_order_event(types.SimpleNamespace(status="filled", order_id=1))
    algorithm.on_end_of_algorithm()
    assert any("IBQC_ORDER_PATH_COMPLETE" in line for line in algorithm.logs)


def test_missing_tradeability_or_zero_quantity_refuses(qc_module: types.ModuleType) -> None:
    for field, value in (
        ("has_data", False), ("is_tradable", False), ("is_delisted", True),
        ("price", 0), ("last_data", None),
        ("last_data", types.SimpleNamespace(end_time=datetime(2026, 9, 23, 16, 0))),
    ):
        algorithm = _configured(qc_module)
        security = next(s for s in algorithm.securities.values() if s.symbol.value == "ACME")
        setattr(security, field, value)
        with pytest.raises(qc_module.SignalManifestError, match="untradable"):
            algorithm._after_market_close()
        assert algorithm.orders == []
    zero = _configured(qc_module)
    qc_module.RESEARCH_ENTRY_SHARES = 0
    zero._after_market_close()
    assert zero.orders == []


def test_live_mode_refuses_before_loading_data(qc_module: types.ModuleType) -> None:
    algorithm = qc_module.InsiderBuyingOrderSkeleton()
    algorithm.live_mode = True
    with pytest.raises(qc_module.SignalManifestError, match="live"):
        algorithm.initialize()
