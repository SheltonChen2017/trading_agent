"""Default-disabled, order-based Insider stock-study candidate for LEAN Cloud.

This file is standalone for a future owner-authorized QC upload. Its two Object Store
objects and their literal SHA-256 bindings must be registered outside this
file before a counted research look. A structurally valid gate is not proof of
SEC provenance, point-in-time mapping, licensed outcome rights, QC processing
rights, preregistration, or independent review. No such claim is made here.

The candidate buys at the next open after an after-close decision and sells
at the open exactly 20 pinned trading sessions after entry. Any missed fill,
delisting, absent bar, calendar drift, overlap, or capacity underfill makes the
study invalid rather than silently selecting a surviving sample. It is not a
paper/live algorithm. Default constants prohibit subscriptions and orders.
"""
from __future__ import annotations

import datetime as _dt
import hashlib as _hashlib
import json as _json
import re as _re
from decimal import Decimal as _Decimal, InvalidOperation as _InvalidOperation
from typing import NamedTuple

from AlgorithmImports import *  # noqa: F403  (single-file LEAN entry point)


SCHEMA = "insider-qc-stock-order-study-v1"
GATE_SCHEMA = "insider-qc-single-backtest-gate-v1"
SHARED_RESEARCH_CUTOFF = _dt.date(2027, 8, 31)
HORIZON_SESSIONS = 20
MAX_CALENDAR_SESSIONS = 6_000
MAX_SIGNALS = 20_000
MAX_MANIFEST_BYTES = 16_000_000
MAX_GATE_BYTES = 4_096
STARTING_CASH = 100_000
MAX_POSITIONS = 20
CASH_RESERVE = _Decimal("10000")
SLOT_BUDGET = _Decimal("4500")
OPEN_GAP_PAD = _Decimal("1.05")

# None of these are bound in this candidate. Changing them requires a scoped,
# counted-look decision and exact artifact registration; review timing is
# governed separately by the owner's instruction for the first backtest.
RESEARCH_BACKTEST_ENABLED = False
SIGNAL_OBJECT_STORE_KEY = ""
APPROVED_SIGNAL_SHA256 = ""
GATE_OBJECT_STORE_KEY = ""
APPROVED_GATE_SHA256 = ""
APPROVED_LOOK_ID = ""

_SHA256 = _re.compile(r"[0-9a-f]{64}\Z")
_LOOK_ID = _re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,79}\Z")
_TICKER = _re.compile(r"[A-Z][A-Z0-9.]{0,9}\Z")
_UTC = _re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00\Z")
_MANIFEST_FIELDS = frozenset({
    "schema", "source_manifest_sha256", "security_master_sha256",
    "calendar_sha256", "outcome_vintage_sha256", "sessions", "signals",
})
_SIGNAL_FIELDS = frozenset({
    "signal_id", "ticker", "qc_symbol_id", "source_event_sha256",
    "mapping_first_session", "mapping_last_session", "available_at_utc",
    "decision_session", "entry_session", "exit_session",
})
_GATE_FIELDS = frozenset({
    "schema", "scope", "registered_look_id", "manifest_sha256",
    "rights_record_sha256", "outcome_vintage_sha256",
})


class StockStudyRefusal(RuntimeError):
    """A counted study is not admissible or did not complete as specified."""


class Signal(NamedTuple):
    signal_id: str
    ticker: str
    qc_symbol_id: str
    source_event_sha256: str
    mapping_first_session: _dt.date
    mapping_last_session: _dt.date
    available_at_utc: _dt.datetime
    decision_session: _dt.date
    entry_session: _dt.date
    exit_session: _dt.date


class StudyManifest(NamedTuple):
    raw_sha256: str
    source_manifest_sha256: str
    security_master_sha256: str
    calendar_sha256: str
    outcome_vintage_sha256: str
    sessions: tuple[_dt.date, ...]
    signals: tuple[Signal, ...]


class StudyGate(NamedTuple):
    raw_sha256: str
    registered_look_id: str
    manifest_sha256: str
    rights_record_sha256: str
    outcome_vintage_sha256: str


class PendingOrder(NamedTuple):
    signal: Signal
    symbol: object
    side: str
    quantity: int
    fill_session: _dt.date


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise StockStudyRefusal(f"REFUSED: duplicate JSON key {key!r}")
        result[key] = value
    return result


def _nonfinite(token: str) -> None:
    raise StockStudyRefusal(f"REFUSED: nonfinite JSON token {token}")


def _digest(value: object, field: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise StockStudyRefusal(f"REFUSED: {field} must be lowercase SHA-256")
    return value


def _session(value: object, field: str) -> _dt.date:
    if type(value) is not str:
        raise StockStudyRefusal(f"REFUSED: {field} must be an ISO session")
    try:
        result = _dt.date.fromisoformat(value)
    except ValueError as exc:
        raise StockStudyRefusal(f"REFUSED: {field} must be an ISO session") from exc
    if result.isoformat() != value:
        raise StockStudyRefusal(f"REFUSED: {field} must be an ISO session")
    return result


def _utc(value: object) -> _dt.datetime:
    if type(value) is not str or _UTC.fullmatch(value) is None:
        raise StockStudyRefusal("REFUSED: available_at_utc must be exact UTC")
    try:
        return _dt.datetime.fromisoformat(value)
    except ValueError as exc:
        raise StockStudyRefusal("REFUSED: available_at_utc must be exact UTC") from exc


def _identity(value: object, field: str) -> str:
    if (
        type(value) is not str or not 1 <= len(value) <= 100
        or value.strip() != value or not value.isascii() or not value.isprintable()
    ):
        raise StockStudyRefusal(f"REFUSED: {field} is not a bounded identity")
    return value


def _decode(raw: bytes, expected_sha256: str, *, max_bytes: int) -> tuple[dict, str]:
    expected = _digest(expected_sha256, "approved raw digest")
    if type(raw) is not bytes or not 1 <= len(raw) <= max_bytes:
        raise StockStudyRefusal("REFUSED: raw artifact absent or unbounded")
    actual = _hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise StockStudyRefusal("REFUSED: raw artifact digest mismatch")
    try:
        value = _json.loads(raw.decode("utf-8"), object_pairs_hook=_object,
                            parse_constant=_nonfinite)
    except (UnicodeError, ValueError) as exc:
        raise StockStudyRefusal("REFUSED: artifact is not strict UTF-8 JSON") from exc
    if type(value) is not dict:
        raise StockStudyRefusal("REFUSED: artifact must be an object")
    return value, actual


def parse_study_manifest(raw: bytes, expected_sha256: str) -> StudyManifest:
    """Pin bytes, provenance declarations, full calendar, and every trade date."""
    value, actual = _decode(raw, expected_sha256, max_bytes=MAX_MANIFEST_BYTES)
    if frozenset(value) != _MANIFEST_FIELDS or value["schema"] != SCHEMA:
        raise StockStudyRefusal("REFUSED: manifest schema or fields drifted")
    source_sha = _digest(value["source_manifest_sha256"], "source manifest")
    master_sha = _digest(value["security_master_sha256"], "security master")
    calendar_sha = _digest(value["calendar_sha256"], "calendar")
    outcome_sha = _digest(value["outcome_vintage_sha256"], "outcome vintage")
    supplied_sessions = value["sessions"]
    if (
        type(supplied_sessions) is not list
        or not HORIZON_SESSIONS + 2 <= len(supplied_sessions) <= MAX_CALENDAR_SESSIONS
    ):
        raise StockStudyRefusal("REFUSED: calendar is empty or unbounded")
    sessions = tuple(_session(item, "calendar session") for item in supplied_sessions)
    if tuple(sorted(set(sessions))) != sessions or sessions[-1] > SHARED_RESEARCH_CUTOFF:
        raise StockStudyRefusal("REFUSED: calendar is unsorted, duplicate, or holdout")
    # The raw calendar spelling, not a caller-provided claim, has this digest.
    calendar_bytes = _json.dumps(supplied_sessions, separators=(",", ":"),
                                 ensure_ascii=True).encode("ascii")
    if _hashlib.sha256(calendar_bytes).hexdigest() != calendar_sha:
        raise StockStudyRefusal("REFUSED: calendar digest mismatch")
    index = {day: number for number, day in enumerate(sessions)}
    supplied_signals = value["signals"]
    if type(supplied_signals) is not list or not 1 <= len(supplied_signals) <= MAX_SIGNALS:
        raise StockStudyRefusal("REFUSED: signal inventory empty or unbounded")

    rows: list[Signal] = []
    ids: set[str] = set()
    by_sid: dict[str, list[Signal]] = {}
    ticker_ids: dict[str, str] = {}
    for item in supplied_signals:
        if type(item) is not dict or frozenset(item) != _SIGNAL_FIELDS:
            raise StockStudyRefusal("REFUSED: signal row fields drifted")
        signal_id = item["signal_id"]
        ticker = item["ticker"]
        if type(signal_id) is not str or _LOOK_ID.fullmatch(signal_id) is None:
            raise StockStudyRefusal("REFUSED: signal_id malformed")
        if type(ticker) is not str or _TICKER.fullmatch(ticker) is None:
            raise StockStudyRefusal("REFUSED: ticker malformed")
        sid = _identity(item["qc_symbol_id"], "QC Symbol ID")
        source_event = _digest(item["source_event_sha256"], "source event")
        mapping_first = _session(item["mapping_first_session"], "mapping first")
        mapping_last = _session(item["mapping_last_session"], "mapping last")
        available = _utc(item["available_at_utc"])
        decision = _session(item["decision_session"], "decision")
        entry = _session(item["entry_session"], "entry")
        exit_day = _session(item["exit_session"], "exit")
        if decision not in index or index[decision] + HORIZON_SESSIONS + 1 >= len(sessions):
            raise StockStudyRefusal("REFUSED: decision lacks complete 20-session horizon")
        if (
            entry != sessions[index[decision] + 1]
            or exit_day != sessions[index[decision] + HORIZON_SESSIONS + 1]
        ):
            raise StockStudyRefusal("REFUSED: entry/exit is not pinned next-open/20-session")
        if not (mapping_first <= decision < entry < exit_day < mapping_last):
            raise StockStudyRefusal("REFUSED: PIT mapping interval misses trade horizon")
        if available.date() > decision:
            raise StockStudyRefusal("REFUSED: public availability follows decision")
        if signal_id in ids:
            raise StockStudyRefusal("REFUSED: duplicate signal ID")
        if ticker in ticker_ids and ticker_ids[ticker] != sid:
            raise StockStudyRefusal("REFUSED: ticker has conflicting QC Symbol IDs")
        ids.add(signal_id)
        ticker_ids[ticker] = sid
        row = Signal(signal_id, ticker, sid, source_event, mapping_first,
                     mapping_last, available, decision, entry, exit_day)
        by_sid.setdefault(sid, []).append(row)
        rows.append(row)
    if rows != sorted(rows, key=lambda row: (row.decision_session, row.signal_id)):
        raise StockStudyRefusal("REFUSED: signal rows not in canonical order")
    for symbol_rows in by_sid.values():
        symbol_rows.sort(key=lambda row: row.entry_session)
        for left, right in zip(symbol_rows, symbol_rows[1:]):
            if right.entry_session <= left.exit_session:
                raise StockStudyRefusal("REFUSED: overlapping same-security positions")
    _preflight_capacity(rows, sessions, index)
    return StudyManifest(actual, source_sha, master_sha, calendar_sha,
                         outcome_sha, sessions, tuple(rows))


def parse_study_gate(raw: bytes, expected_sha256: str, manifest: StudyManifest,
                     approved_look_id: str) -> StudyGate:
    """Check a pinned external registration claim, never manufacture approval."""
    value, actual = _decode(raw, expected_sha256, max_bytes=MAX_GATE_BYTES)
    if frozenset(value) != _GATE_FIELDS or value["schema"] != GATE_SCHEMA:
        raise StockStudyRefusal("REFUSED: gate schema or fields drifted")
    if value["scope"] != "single-research-backtest-only":
        raise StockStudyRefusal("REFUSED: gate scope is not a single backtest")
    look_id = value["registered_look_id"]
    if (
        type(approved_look_id) is not str or _LOOK_ID.fullmatch(approved_look_id) is None
        or look_id != approved_look_id
    ):
        raise StockStudyRefusal("REFUSED: registered look ID is unbound or mismatched")
    if _digest(value["manifest_sha256"], "gate manifest") != manifest.raw_sha256:
        raise StockStudyRefusal("REFUSED: gate points to another signal manifest")
    rights = _digest(value["rights_record_sha256"], "rights record")
    outcome = _digest(value["outcome_vintage_sha256"], "gate outcome vintage")
    if outcome != manifest.outcome_vintage_sha256:
        raise StockStudyRefusal("REFUSED: gate outcome vintage mismatch")
    return StudyGate(actual, look_id, manifest.raw_sha256, rights, outcome)


def _positive_decimal(value: object, field: str) -> _Decimal:
    try:
        result = _Decimal(str(value))
    except (_InvalidOperation, ValueError) as exc:
        raise StockStudyRefusal(f"REFUSED: {field} is not finite positive") from exc
    if not result.is_finite() or result <= 0:
        raise StockStudyRefusal(f"REFUSED: {field} is not finite positive")
    return result


def _preflight_capacity(
    rows: list[Signal], sessions: tuple[_dt.date, ...], index: dict[_dt.date, int]
) -> None:
    """Refuse impossible full-slot schedules before subscriptions or orders.

    An exit submitted after close remains an active position until its next-open
    fill.  Exit proceeds cannot fund an entry decided on that same evening.
    This static bound cannot prove future prices, fills, fees, or available cash;
    the run-time checks remain necessary.
    """
    if type(MAX_POSITIONS) is not int or MAX_POSITIONS <= 0:
        raise StockStudyRefusal("REFUSED: fixed position capacity is invalid")
    cash = _positive_decimal(STARTING_CASH, "starting cash")
    reserve = _positive_decimal(CASH_RESERVE, "cash reserve")
    slot = _positive_decimal(SLOT_BUDGET, "slot budget")
    if cash <= reserve:
        raise StockStudyRefusal("REFUSED: fixed cash/slot capacity is impossible")
    cash_slots = int((cash - reserve) // slot)
    capacity = min(MAX_POSITIONS, cash_slots)
    if capacity < 1:
        raise StockStudyRefusal("REFUSED: fixed cash/slot capacity is impossible")

    decisions = [0] * len(sessions)
    active_deltas = [0] * (len(sessions) + 1)
    for row in rows:
        decisions[index[row.decision_session]] += 1
        active_deltas[index[row.entry_session]] += 1
        active_deltas[index[row.exit_session]] -= 1
    active = 0
    for day_index in range(len(sessions)):
        active += active_deltas[day_index]
        if active + decisions[day_index] > capacity:
            raise StockStudyRefusal(
                "REFUSED: declared positions exceed fixed position/cash-slot capacity"
            )


def _engine_utc(value: object) -> _dt.datetime:
    if type(value) is not _dt.datetime:
        raise StockStudyRefusal("REFUSED: engine UTC unavailable")
    if value.tzinfo is None:
        return value.replace(tzinfo=_dt.timezone.utc)
    if value.utcoffset() != _dt.timedelta(0):
        raise StockStudyRefusal("REFUSED: engine time has non-UTC zone")
    return value


class InsiderBuyingStockOrderStudy(QCAlgorithm):  # type: ignore[name-defined]
    """A single registered stock study, not a portfolio deployment strategy."""

    def initialize(self) -> None:
        if self.live_mode:
            raise StockStudyRefusal("REFUSED: live mode prohibited")
        if RESEARCH_BACKTEST_ENABLED is not True:
            raise StockStudyRefusal("REFUSED: research backtest gate disabled")
        for key, field in (
            (SIGNAL_OBJECT_STORE_KEY, "signal"),
            (GATE_OBJECT_STORE_KEY, "gate"),
        ):
            if (
                type(key) is not str or not key.startswith("insider-buying/")
                or ".." in key or not key.isascii() or not key.isprintable()
                or len(key) > 160
            ):
                raise StockStudyRefusal(f"REFUSED: {field} Object Store key unbound")
        if SIGNAL_OBJECT_STORE_KEY == GATE_OBJECT_STORE_KEY:
            raise StockStudyRefusal("REFUSED: gate and signal keys collide")
        _digest(APPROVED_SIGNAL_SHA256, "signal binding")
        _digest(APPROVED_GATE_SHA256, "gate binding")
        if type(APPROVED_LOOK_ID) is not str or _LOOK_ID.fullmatch(APPROVED_LOOK_ID) is None:
            raise StockStudyRefusal("REFUSED: look ID unbound")
        if not self.object_store.contains_key(SIGNAL_OBJECT_STORE_KEY):
            raise StockStudyRefusal("REFUSED: signal Object Store key absent")
        if not self.object_store.contains_key(GATE_OBJECT_STORE_KEY):
            raise StockStudyRefusal("REFUSED: gate Object Store key absent")
        try:
            signal_raw = bytes(self.object_store.read_bytes(SIGNAL_OBJECT_STORE_KEY))
            gate_raw = bytes(self.object_store.read_bytes(GATE_OBJECT_STORE_KEY))
        except (TypeError, ValueError) as exc:
            raise StockStudyRefusal("REFUSED: Object Store bytes unavailable") from exc
        manifest = parse_study_manifest(signal_raw, APPROVED_SIGNAL_SHA256)
        gate = parse_study_gate(gate_raw, APPROVED_GATE_SHA256,
                                manifest, APPROVED_LOOK_ID)

        self.set_time_zone("America/New_York")
        self.set_start_date(*manifest.sessions[0].timetuple()[:3])
        self.set_end_date(*manifest.sessions[-1].timetuple()[:3])
        self.set_cash(STARTING_CASH)
        # Cash-account modeling prevents a large opening gap from quietly
        # turning this stock diagnostic into a leveraged portfolio test.
        self.set_brokerage_model(  # type: ignore[name-defined]
            BrokerageName.QUANT_CONNECT_BROKERAGE, AccountType.CASH
        )
        # After-close callbacks need a 16:01 data clock; a regular-hours-only
        # minute subscription can defer the callback until the next open.
        self._clock_symbol = self.add_equity(  # type: ignore[name-defined]
            "SPY", Resolution.MINUTE, extended_market_hours=True,
            fill_forward=False,
        ).symbol
        self._symbols: dict[str, object] = {}
        for row in manifest.signals:
            if row.ticker not in self._symbols:
                symbol = (
                    self._clock_symbol if row.ticker == "SPY"
                    else self.add_equity(  # type: ignore[name-defined]
                        row.ticker, Resolution.MINUTE, fill_forward=False
                    ).symbol
                )
                self._symbols[row.ticker] = symbol
                self.securities[symbol].set_data_normalization_mode(
                    DataNormalizationMode.RAW  # type: ignore[name-defined]
                )
            if str(self._symbols[row.ticker].id) != row.qc_symbol_id:
                raise StockStudyRefusal("REFUSED: QC Symbol ID mismatch")
        self._manifest = manifest
        self._gate = gate
        self._by_decision: dict[_dt.date, list[Signal]] = {}
        self._by_exit_decision: dict[_dt.date, list[Signal]] = {}
        session_index = {day: i for i, day in enumerate(manifest.sessions)}
        for row in manifest.signals:
            self._by_decision.setdefault(row.decision_session, []).append(row)
            previous = manifest.sessions[session_index[row.exit_session] - 1]
            self._by_exit_decision.setdefault(previous, []).append(row)
        self._next_session_index = 0
        self._pending: dict[int, PendingOrder] = {}
        self._active: dict[str, tuple[Signal, int]] = {}
        self._entry_count = 0
        self._exit_count = 0
        self._submitted_count = 0
        self.schedule.on(
            self.date_rules.every_day(self._clock_symbol),
            self.time_rules.after_market_close(self._clock_symbol, 1),
            self._after_market_close,
        )
        self.log(
            f"IBQC_STUDY_INPUT|look={gate.registered_look_id}|"
            f"manifest={manifest.raw_sha256}|gate={gate.raw_sha256}|"
            f"signals={len(manifest.signals)}|canonical=false"
        )

    def _check_security(self, row: Signal, session: _dt.date) -> tuple[object, _Decimal]:
        symbol = self._symbols[row.ticker]
        if str(symbol.id) != row.qc_symbol_id:
            raise StockStudyRefusal("REFUSED: QC Symbol ID changed")
        security = self.securities[symbol]
        last_data = security.get_last_data()
        if (
            not security.is_tradable or security.is_delisted or not security.has_data
            or last_data is None or last_data.end_time.date() != session
            or getattr(last_data, "is_fill_forward", False)
        ):
            raise StockStudyRefusal("REFUSED: missing, stale, or delisted security bar")
        return symbol, _positive_decimal(security.price, "security price")

    def _cash_with_reserve(self) -> _Decimal:
        cash = _positive_decimal(self.portfolio.cash, "portfolio cash")
        if cash < CASH_RESERVE:
            raise StockStudyRefusal("REFUSED: cash reserve breached")
        return cash

    def _submit(self, row: Signal, symbol: object, side: str, quantity: int,
                fill_session: _dt.date) -> None:
        if self.live_mode or RESEARCH_BACKTEST_ENABLED is not True:
            raise StockStudyRefusal("REFUSED: research-only order gate disabled")
        if type(quantity) is not int or quantity == 0:
            raise StockStudyRefusal("REFUSED: zero or malformed order quantity")
        if (side == "ENTRY") != (quantity > 0):
            raise StockStudyRefusal("REFUSED: order direction drifted")
        tag = f"IB5:{self._gate.registered_look_id}:{row.signal_id}:{side}"
        ticket = self.market_on_open_order(symbol, quantity, tag=tag)
        if (
            ticket is None or ticket.status == OrderStatus.INVALID  # type: ignore[name-defined]
            or type(ticket.order_id) is not int or ticket.order_id in self._pending
        ):
            raise StockStudyRefusal("REFUSED: MOO order rejected or lacks unique ID")
        self._pending[ticket.order_id] = PendingOrder(
            row, symbol, side, quantity, fill_session
        )
        self._submitted_count += 1

    def _after_market_close(self) -> None:
        if self.live_mode or RESEARCH_BACKTEST_ENABLED is not True:
            raise StockStudyRefusal("REFUSED: live or unapproved order path")
        if self.is_warming_up:
            return
        session = self.time.date()
        sessions = self._manifest.sessions
        if (
            self._next_session_index >= len(sessions)
            or session != sessions[self._next_session_index]
        ):
            raise StockStudyRefusal("REFUSED: QC/calendar session drift")
        for order in self._pending.values():
            if order.fill_session <= session:
                raise StockStudyRefusal("REFUSED: MOO missed its pinned opening fill")
        cash = self._cash_with_reserve()
        for sid, (held_row, held_quantity) in self._active.items():
            held_symbol, _ = self._check_security(held_row, session)
            if (
                str(held_symbol.id) != sid
                or self.portfolio[held_symbol].quantity != held_quantity
            ):
                raise StockStudyRefusal("REFUSED: held quantity changed outside study orders")
        self._next_session_index += 1
        now = _engine_utc(self.utc_time)

        # Plan the whole batch before the first order. A later missing bar or
        # capacity refusal cannot leave earlier same-day orders submitted.
        # Exit proceeds are not available for entries until actually filled.
        planned_exits: list[tuple[Signal, object, int]] = []
        for row in self._by_exit_decision.get(session, ()):
            held = self._active.get(row.qc_symbol_id)
            if held is None or held[0] != row:
                raise StockStudyRefusal("REFUSED: scheduled exit has no filled entry")
            symbol, _ = self._check_security(row, session)
            if self.portfolio[symbol].quantity != held[1]:
                raise StockStudyRefusal("REFUSED: held position differs from filled entry")
            planned_exits.append((row, symbol, -held[1]))

        batch_reserved = _Decimal("0")
        planned_entries: list[tuple[Signal, object, int]] = []
        for row in self._by_decision.get(session, ()):
            if now < row.available_at_utc:
                raise StockStudyRefusal("REFUSED: public availability follows order decision")
            symbol, price = self._check_security(row, session)
            if row.qc_symbol_id in self._active or any(
                order.signal.qc_symbol_id == row.qc_symbol_id
                for order in self._pending.values()
            ):
                raise StockStudyRefusal("REFUSED: overlapping security position")
            position_count = len(self._active) + len(planned_entries) + sum(
                order.side == "ENTRY" for order in self._pending.values()
            )
            if position_count >= MAX_POSITIONS:
                raise StockStudyRefusal("REFUSED: position capacity underfill")
            spendable = cash - CASH_RESERVE - batch_reserved
            budget = min(SLOT_BUDGET, spendable)
            if budget <= 0:
                raise StockStudyRefusal("REFUSED: cash-reserve capacity underfill")
            unit_cost = price * OPEN_GAP_PAD
            quantity = int(budget // unit_cost)
            if quantity <= 0:
                raise StockStudyRefusal("REFUSED: one share exceeds protected budget; underfill")
            batch_reserved += unit_cost * quantity
            planned_entries.append((row, symbol, quantity))
        for row, symbol, quantity in planned_exits:
            self._submit(row, symbol, "EXIT", quantity, row.exit_session)
        for row, symbol, quantity in planned_entries:
            self._submit(row, symbol, "ENTRY", quantity, row.entry_session)

    def on_data(self, slice) -> None:
        if not hasattr(self, "_active"):
            return
        for symbol, _delisting in slice.delistings.items():
            if str(symbol.id) in self._active or any(
                order.symbol == symbol for order in self._pending.values()
            ):
                raise StockStudyRefusal("REFUSED: held or pending security delisted")

    def on_order_event(self, order_event) -> None:
        if not hasattr(self, "_pending"):
            return
        status = order_event.status
        if status not in (
            OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED,  # type: ignore[name-defined]
            OrderStatus.CANCELED, OrderStatus.INVALID,  # type: ignore[name-defined]
        ):
            return
        pending = self._pending.get(order_event.order_id)
        if pending is None:
            raise StockStudyRefusal("REFUSED: unexpected terminal order event")
        if status != OrderStatus.FILLED:  # type: ignore[name-defined]
            raise StockStudyRefusal("REFUSED: MOO partial, canceled, or invalid")
        if (
            order_event.symbol != pending.symbol
            or order_event.fill_quantity != pending.quantity
            or self.time.date() != pending.fill_session
        ):
            raise StockStudyRefusal("REFUSED: MOO fill identity, size, or session drift")
        fill_price = _positive_decimal(order_event.fill_price, "MOO fill price")
        if pending.side == "ENTRY":
            if fill_price * pending.quantity > SLOT_BUDGET:
                raise StockStudyRefusal("REFUSED: actual opening fill exceeds slot budget")
            self._cash_with_reserve()
        del self._pending[order_event.order_id]
        sid = pending.signal.qc_symbol_id
        if pending.side == "ENTRY":
            if sid in self._active:
                raise StockStudyRefusal("REFUSED: duplicate filled position")
            self._active[sid] = (pending.signal, pending.quantity)
            self._entry_count += 1
        else:
            held = self._active.get(sid)
            if held is None or held != (pending.signal, -pending.quantity):
                raise StockStudyRefusal("REFUSED: exit fill differs from entry")
            del self._active[sid]
            self._exit_count += 1

    def on_end_of_algorithm(self) -> None:
        if not hasattr(self, "_manifest"):
            raise StockStudyRefusal("REFUSED: study never initialized")
        expected = len(self._manifest.signals)
        self._cash_with_reserve()
        if (
            self._next_session_index != len(self._manifest.sessions)
            or self._pending or self._active
            or self._entry_count != expected or self._exit_count != expected
            or self._submitted_count != 2 * expected
            or any(self.portfolio[symbol].quantity != 0 for symbol in self._symbols.values())
        ):
            raise StockStudyRefusal("REFUSED: complete 20-session order path unproved")
        self.log(
            f"IBQC_STUDY_ORDER_PATH_COMPLETE|look={self._gate.registered_look_id}|"
            f"manifest={self._manifest.raw_sha256}|entries={self._entry_count}|"
            f"exits={self._exit_count}|canonical=false"
        )
