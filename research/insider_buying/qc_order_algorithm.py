"""Research-only Insider order skeleton; every QC run is a counted research look.

This single-file LEAN entry point is deliberately unbound. A later reviewed
run must pin an immutable precomputed signal Object Store key, its exact raw
SHA-256, and a research order policy in the uploaded source. Hashes here
check byte identity, not SEC provenance, data rights, PIT correctness, or
canonical IB-5 readiness. No SEC/vendor request, Object Store write, broker
connection, live deployment, or result interpretation occurs in this file.

The skeleton submits one-share market-on-open research orders after a dated
signal is publicly available. It has no exit, portfolio sizing, cost model,
or stock-study statistic. Its default zero quantity and empty source binding
make it incapable of an accidental order or completed backtest.
"""
from __future__ import annotations

import datetime as _dt
import hashlib as _hashlib
import json as _json
import math as _math
import re as _re
from typing import NamedTuple

from AlgorithmImports import *  # noqa: F403  (LEAN's documented entry point)


MANIFEST_SCHEMA = "insider-qc-order-skeleton-manifest-v1"
SHARED_RESEARCH_CUTOFF = _dt.date(2027, 8, 31)
MAX_MANIFEST_BYTES = 2_000_000
MAX_SIGNALS = 64
STARTING_CASH = 100_000

# These values remain unbound until a separately reviewed real-data/look/QC
# gate approves the exact uploaded source and input. The key must be a private
# Insider namespace path; the digest pins raw bytes even if that key changes.
SIGNAL_OBJECT_STORE_KEY = ""
APPROVED_SIGNAL_MANIFEST_SHA256 = ""
RESEARCH_ENTRY_SHARES = 0

_SHA256 = _re.compile(r"[0-9a-f]{64}\Z")
_TICKER = _re.compile(r"[A-Z][A-Z0-9.]{0,9}\Z")
_SIGNAL_ID = _re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,79}\Z")
_UTC = _re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00\Z")
_TOP_FIELDS = frozenset({
    "schema", "source_manifest_sha256", "security_master_sha256",
    "calendar_sha256", "window_start", "window_end", "signals",
})
_ROW_FIELDS = frozenset({
    "signal_id", "ticker", "qc_symbol_id", "source_event_sha256",
    "mapping_first_session", "mapping_last_session", "decision_session",
    "available_at_utc",
})


class SignalManifestError(RuntimeError):
    """A source, timing, mapping, or order precondition failed closed."""


class SignalRow(NamedTuple):
    signal_id: str
    ticker: str
    qc_symbol_id: str
    source_event_sha256: str
    mapping_first_session: _dt.date
    mapping_last_session: _dt.date
    decision_session: _dt.date
    available_at_utc: _dt.datetime


class SignalManifest(NamedTuple):
    raw_sha256: str
    source_manifest_sha256: str
    security_master_sha256: str
    calendar_sha256: str
    window_start: _dt.date
    window_end: _dt.date
    signals: tuple[SignalRow, ...]


def _distinct_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SignalManifestError(f"REFUSED: duplicate JSON key {key!r}")
        result[key] = value
    return result


def _nonfinite(token: str) -> None:
    raise SignalManifestError(f"REFUSED: nonfinite JSON token {token}")


def _digest(value: object, field: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise SignalManifestError(f"REFUSED: {field} must be lowercase SHA-256")
    return value


def _session(value: object, field: str) -> _dt.date:
    if type(value) is not str:
        raise SignalManifestError(f"REFUSED: {field} must be an ISO session")
    try:
        parsed = _dt.date.fromisoformat(value)
    except ValueError as exc:
        raise SignalManifestError(f"REFUSED: {field} must be an ISO session") from exc
    if parsed.isoformat() != value:
        raise SignalManifestError(f"REFUSED: {field} must be an ISO session")
    return parsed


def _available_utc(value: object) -> _dt.datetime:
    if type(value) is not str or _UTC.fullmatch(value) is None:
        raise SignalManifestError("REFUSED: available_at_utc must be exact UTC")
    try:
        return _dt.datetime.fromisoformat(value)
    except ValueError as exc:
        raise SignalManifestError("REFUSED: available_at_utc must be exact UTC") from exc


def _printable_identity(value: object, field: str) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= 100
        or value.strip() != value
        or not value.isascii()
        or not value.isprintable()
    ):
        raise SignalManifestError(f"REFUSED: {field} must be a bounded identity")
    return value


def parse_signal_manifest(raw: bytes, expected_sha256: str) -> SignalManifest:
    """Validate exact bytes and a bounded, strict per-session signal inventory."""
    expected = _digest(expected_sha256, "approved manifest digest")
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_MANIFEST_BYTES:
        raise SignalManifestError("REFUSED: manifest must be bounded raw bytes")
    actual = _hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise SignalManifestError("REFUSED: manifest digest mismatch")
    try:
        payload = _json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_distinct_object,
            parse_constant=_nonfinite,
        )
    except (UnicodeError, ValueError) as exc:
        raise SignalManifestError("REFUSED: manifest is not strict UTF-8 JSON") from exc
    if type(payload) is not dict or frozenset(payload) != _TOP_FIELDS:
        raise SignalManifestError("REFUSED: manifest fields drifted")
    if payload["schema"] != MANIFEST_SCHEMA:
        raise SignalManifestError("REFUSED: manifest schema drifted")
    source_sha = _digest(payload["source_manifest_sha256"], "source_manifest_sha256")
    master_sha = _digest(payload["security_master_sha256"], "security_master_sha256")
    calendar_sha = _digest(payload["calendar_sha256"], "calendar_sha256")
    first = _session(payload["window_start"], "window_start")
    last = _session(payload["window_end"], "window_end")
    if first > last or last > SHARED_RESEARCH_CUTOFF:
        raise SignalManifestError("REFUSED: window reversed or crosses holdout")
    supplied = payload["signals"]
    if type(supplied) is not list or not 1 <= len(supplied) <= MAX_SIGNALS:
        raise SignalManifestError("REFUSED: signal inventory is empty or unbounded")

    rows: list[SignalRow] = []
    seen_ids: set[str] = set()
    seen_dates: set[_dt.date] = set()
    ticker_ids: dict[str, str] = {}
    for item in supplied:
        if type(item) is not dict or frozenset(item) != _ROW_FIELDS:
            raise SignalManifestError("REFUSED: signal row fields drifted")
        signal_id = item["signal_id"]
        ticker = item["ticker"]
        if type(signal_id) is not str or _SIGNAL_ID.fullmatch(signal_id) is None:
            raise SignalManifestError("REFUSED: signal_id is malformed")
        if type(ticker) is not str or _TICKER.fullmatch(ticker) is None:
            raise SignalManifestError("REFUSED: ticker is malformed")
        qc_id = _printable_identity(item["qc_symbol_id"], "qc_symbol_id")
        source_event_sha = _digest(item["source_event_sha256"], "source_event_sha256")
        mapping_first = _session(item["mapping_first_session"], "mapping_first_session")
        mapping_last = _session(item["mapping_last_session"], "mapping_last_session")
        decision = _session(item["decision_session"], "decision_session")
        available = _available_utc(item["available_at_utc"])
        if not (first <= decision <= last):
            raise SignalManifestError("REFUSED: decision outside frozen window")
        if not (mapping_first <= decision < mapping_last):
            raise SignalManifestError("REFUSED: mapping interval misses next-open decision")
        if available.date() > decision:
            raise SignalManifestError("REFUSED: availability follows decision session")
        if signal_id in seen_ids or decision in seen_dates:
            raise SignalManifestError("REFUSED: duplicate signal identity or decision session")
        if ticker in ticker_ids and ticker_ids[ticker] != qc_id:
            raise SignalManifestError("REFUSED: ticker maps to multiple QC Symbol IDs")
        seen_ids.add(signal_id)
        seen_dates.add(decision)
        ticker_ids[ticker] = qc_id
        rows.append(SignalRow(
            signal_id, ticker, qc_id, source_event_sha, mapping_first,
            mapping_last, decision, available,
        ))
    if rows != sorted(rows, key=lambda row: (row.decision_session, row.signal_id)):
        raise SignalManifestError("REFUSED: signals must be in canonical date order")
    return SignalManifest(actual, source_sha, master_sha, calendar_sha,
                          first, last, tuple(rows))


def _engine_utc(value: _dt.datetime) -> _dt.datetime:
    if type(value) is not _dt.datetime:
        raise SignalManifestError("REFUSED: engine UTC time is unavailable")
    # QC documents utc_time as a naive datetime already expressed in UTC.
    if value.tzinfo is None:
        return value.replace(tzinfo=_dt.timezone.utc)
    if value.utcoffset() != _dt.timedelta(0):
        raise SignalManifestError("REFUSED: engine UTC time has a non-UTC zone")
    return value


class InsiderBuyingOrderSkeleton(QCAlgorithm):  # type: ignore[name-defined]
    """One entry per date, with MOO placed only after public availability."""

    def initialize(self) -> None:
        if self.live_mode:
            raise SignalManifestError("REFUSED: live mode is prohibited")
        if (
            type(SIGNAL_OBJECT_STORE_KEY) is not str
            or not SIGNAL_OBJECT_STORE_KEY.startswith("insider-buying/")
            or ".." in SIGNAL_OBJECT_STORE_KEY
            or len(SIGNAL_OBJECT_STORE_KEY) > 160
            or not SIGNAL_OBJECT_STORE_KEY.isascii()
            or not SIGNAL_OBJECT_STORE_KEY.isprintable()
            or not APPROVED_SIGNAL_MANIFEST_SHA256
        ):
            raise SignalManifestError("REFUSED: signal Object Store source is unbound")
        _digest(APPROVED_SIGNAL_MANIFEST_SHA256, "approved manifest digest")
        if type(RESEARCH_ENTRY_SHARES) is not int or RESEARCH_ENTRY_SHARES not in (0, 1):
            raise SignalManifestError("REFUSED: research entry shares must be 0 or 1")
        if not self.object_store.contains_key(SIGNAL_OBJECT_STORE_KEY):
            raise SignalManifestError("REFUSED: signal Object Store key is missing")
        try:
            raw = bytes(self.object_store.read_bytes(SIGNAL_OBJECT_STORE_KEY))
        except (TypeError, ValueError) as exc:
            raise SignalManifestError("REFUSED: signal Object Store bytes unavailable") from exc
        manifest = parse_signal_manifest(raw, APPROVED_SIGNAL_MANIFEST_SHA256)

        self.set_time_zone("America/New_York")
        self.set_start_date(*manifest.window_start.timetuple()[:3])
        self.set_end_date(*manifest.window_end.timetuple()[:3])
        self.set_cash(STARTING_CASH)
        self._clock_symbol = self.add_equity(
            "SPY", Resolution.MINUTE, extended_market_hours=True  # type: ignore[name-defined]
        ).symbol
        self._symbols: dict[str, object] = {}
        for row in manifest.signals:
            if row.ticker not in self._symbols:
                symbol = (
                    self._clock_symbol if row.ticker == "SPY"
                    else self.add_equity(
                        row.ticker, Resolution.MINUTE, extended_market_hours=True  # type: ignore[name-defined]
                    ).symbol
                )
                self._symbols[row.ticker] = symbol
                self.securities[symbol].set_data_normalization_mode(
                    DataNormalizationMode.RAW  # type: ignore[name-defined]
                )
            if str(self._symbols[row.ticker].id) != row.qc_symbol_id:
                raise SignalManifestError("REFUSED: QC Symbol ID mismatch")
        self._manifest = manifest
        self._rows_by_session = {row.decision_session: row for row in manifest.signals}
        self._processed_sessions: set[_dt.date] = set()
        self._submitted_symbols: set[object] = set()
        self._filled_order_ids: set[int] = set()
        self.attempted_orders = 0
        self.refused_signals = 0
        self.schedule.on(
            self.date_rules.every_day(self._clock_symbol),
            self.time_rules.after_market_close(self._clock_symbol, 1),
            self._after_market_close,
        )
        self.log(f"IBQC_INPUT_READY|sha256={manifest.raw_sha256}|rows={len(manifest.signals)}")

    def _after_market_close(self) -> None:
        if self.live_mode:
            raise SignalManifestError("REFUSED: live mode is prohibited")
        if self.is_warming_up:
            return
        session = self.time.date()
        row = self._rows_by_session.get(session)
        if row is None or session in self._processed_sessions:
            return
        self._processed_sessions.add(session)
        now = _engine_utc(self.utc_time)
        if now < row.available_at_utc:
            raise SignalManifestError("REFUSED: signal availability follows order decision")
        symbol = self._symbols[row.ticker]
        security = self.securities[symbol]
        last_data = security.get_last_data()
        if str(symbol.id) != row.qc_symbol_id:
            raise SignalManifestError("REFUSED: QC Symbol ID changed after initialization")
        if (
            not security.is_tradable
            or security.is_delisted
            or not security.has_data
            or last_data is None
            or last_data.end_time.date() != session
            or not _math.isfinite(float(security.price))
            or float(security.price) <= 0
        ):
            raise SignalManifestError("REFUSED: mapped security is untradable or unpriced")
        if RESEARCH_ENTRY_SHARES == 0:
            self.refused_signals += 1
            self.log("IBQC_INERT|research order policy disabled")
            return
        if symbol in self._submitted_symbols or self.portfolio[symbol].invested:
            raise SignalManifestError("REFUSED: repeated or already invested security")
        tag = f"IBQC:{self._manifest.raw_sha256[:12]}:{self.attempted_orders + 1}"
        self._submitted_symbols.add(symbol)
        ticket = self.market_on_open_order(symbol, RESEARCH_ENTRY_SHARES, tag=tag)
        self.attempted_orders += 1
        if ticket is None or ticket.status == OrderStatus.INVALID:  # type: ignore[name-defined]
            raise SignalManifestError("REFUSED: market-on-open order was invalid")
        self.log(f"IBQC_MOO_SUBMITTED|count={self.attempted_orders}")

    def on_order_event(self, order_event) -> None:
        if order_event.status == OrderStatus.FILLED:  # type: ignore[name-defined]
            self._filled_order_ids.add(order_event.order_id)
            self.log(f"IBQC_MOO_FILLED|count={len(self._filled_order_ids)}")

    def on_end_of_algorithm(self) -> None:
        if RESEARCH_ENTRY_SHARES == 0:
            self.log("IBQC_INERT|zero research shares; no result is authorized")
            return
        if (
            self.attempted_orders != len(self._manifest.signals)
            or len(self._filled_order_ids) != self.attempted_orders
        ):
            raise SignalManifestError("REFUSED: QC order submission/fill incomplete")
        self.log(
            "IBQC_ORDER_PATH_COMPLETE|"
            f"manifest_sha256={self._manifest.raw_sha256}|"
            f"submitted={self.attempted_orders}|filled={len(self._filled_order_ids)}|"
            "canonical=false"
        )
