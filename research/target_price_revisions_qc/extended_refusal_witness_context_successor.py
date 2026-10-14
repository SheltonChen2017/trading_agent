"""Two first-refusal witnesses only; no runtime import, public output or launch.

Call inside an original ValueError handler, then use bare ``raise``. Ordinary
Exception diagnostic failures are contained; genuine cancellation propagates.
Use ONE persistent instance per algorithm. Native evidence supplies the job
identity; no configured/fallback job exists. This changes no original guard.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from fractions import Fraction
import gzip
import hashlib
import io
import json
import math
import re

OPERATION = "TPR-EXT26-MIA-FIRST-REFUSAL-20261014-001"
PROJECT = 37650980
CANDIDATE = "TPR-CAP-TILT-EXT26-OFF-BASE-v1"
CONFIG_SHA256 = "19a9842cfceb695d1f8256f429745247387c89bb725ee2b8be44fe98a726322a"
FREEZE_SHA256 = "90bdec5520b29bd932a3ec730f7c4c40c544ea7582731ad6680ef34ea8cf4067"
CALENDAR_SHA256 = "3eccdf3cf9a2542ffd249983241d5747c2ecd4e21bc4a71f7f826c77ec1fe53d"
MAX_BYTES = 4096
ETFS = frozenset(("SPY", "XLV", "XLE", "QQQ", "SOXX", "REMX"))
ACTION_KEYS = frozenset(("typed_warning_current", "typed_final_current", "native_ticket_current",
    "registered_final_fill_current"))
REFUSALS = {
    "membership": {"membership weight outside bounds": "weight_outside_frozen_bounds",
        "ambiguous native membership identity": "ambiguous_membership_identity",
        "future membership callback": "future_membership_callback"},
    "mark": {"held RAW native closing mark missing": "held_mark_missing",
        "held RAW closing mark stale/future": "held_mark_stale_or_future",
        "held RAW price/cache parity refused": "held_mark_cache_parity_refused"},
}
NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
CLR_NUMBERS = frozenset(("System.Decimal", "System.Double", "System.Single", "System.Int16", "System.Int32",
    "System.Int64", "System.UInt16", "System.UInt32", "System.UInt64", "System.Byte", "System.SByte"))


def _fail(): raise ValueError("bounded private refusal witness refused")
def _sha(raw): return hashlib.sha256(raw).hexdigest()
def _canonical(value): return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def _type_name(value):
    if hasattr(value, "GetType"):
        name = value.GetType().FullName
    else:
        name = type(value).__module__ + "." + type(value).__qualname__
    if type(name) is not str or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]{0,159}", name) is None: _fail()
    return name


def _scalar(value):
    """Exact supported scalar representation, not inferred provider units."""
    name = _type_name(value)
    if value is None: return {"type": name, "state": "none", "text": None}
    if type(value) is bool: return {"type": name, "state": "boolean", "text": "true" if value else "false"}
    if type(value) is Fraction:
        numerator, denominator = str(value.numerator), str(value.denominator)
        if max(len(numerator), len(denominator)) > 128: _fail()
        return {"type": name, "state": "rational", "numerator": numerator, "denominator": denominator}
    if name in CLR_NUMBERS:
        from System.Globalization import CultureInfo
        text = value.ToString(CultureInfo.InvariantCulture)
    elif type(value) in (str, int, float, Decimal):
        if type(value) is float and not math.isfinite(value):
            return {"type": name, "state": "nonfinite", "text": "nan" if math.isnan(value) else "positive_infinity" if value > 0 else "negative_infinity"}
        if type(value) is Decimal and not value.is_finite():
            return {"type": name, "state": "nonfinite", "text": "nan" if value.is_nan() else "negative_infinity" if value.is_signed() else "positive_infinity"}
        text = str(value)
    else:
        return {"type": name, "state": "unsupported", "text": None}
    if type(text) is not str or not 0 < len(text) <= 128: _fail()
    if NUMBER.fullmatch(text) is None:
        return {"type": name, "state": "non_numeric_text_withheld", "text": None}
    return {"type": name, "state": "numeric_text", "text": text}


def _clock(value):
    name = _type_name(value)
    if value is None: return {"type": name, "text": None, "offset_observed": None, "timezone_inferred": False}
    if type(value) is datetime:
        text = value.isoformat(); aware = value.utcoffset() is not None
    elif name in {"System.DateTime", "System.DateTimeOffset"}:
        from System.Globalization import CultureInfo
        text = value.ToString("O", CultureInfo.InvariantCulture)
        if type(text) is not str: _fail()
        aware = text.endswith("Z") or re.search(r"[+-][0-9]{2}:[0-9]{2}$", text) is not None
    else: _fail()
    if not 0 < len(text) <= 64 or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?(?:Z|[+-][0-9]{2}:[0-9]{2})?", text) is None: _fail()
    datetime.fromisoformat(text.replace("Z", "+00:00"))
    return {"type": name, "text": text, "offset_observed": aware, "timezone_inferred": False}


def _sid(value):
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9_ .:/-]{1,200}", value) is None: _fail()
    return value


def _native_bytes(value):
    if type(value) in (bytes, bytearray):
        if not 0 < len(value) <= MAX_BYTES: _fail()
        result = bytes(value)
    elif type(value) is memoryview:
        if value.nbytes > MAX_BYTES: _fail()
        result = bytes(value)
    else:
        from System import Array, Byte
        if type(value) is not Array[Byte] or not 0 < value.Length <= MAX_BYTES: _fail()
        result = bytes(value)
    if not 0 < len(result) <= MAX_BYTES: _fail()
    return result


class FirstRefusalWitness:
    """At most one attempted object per kind, including unsuccessful writes."""
    def __init__(self, native_evidence, native_store):
        self._evidence, self._store = native_evidence, native_store
        self._attempted, self._outcomes = set(), {}

    @property
    def outcomes(self):
        return {kind: {"status": row["status"], "descriptor": None if row["descriptor"] is None else dict(row["descriptor"])} for kind, row in self._outcomes.items()}

    def _binding(self):
        self._evidence.require_binding()
        row = self._evidence.binding
        if type(row) is not dict or set(row) != {"candidate_id", "config_sha256", "freeze_sha256", "input_hashes", "attempt", "project_id", "job_id"}: _fail()
        if (row["candidate_id"] != CANDIDATE or row["config_sha256"] != CONFIG_SHA256 or row["freeze_sha256"] != FREEZE_SHA256
                or type(row["attempt"]) is not int or row["attempt"] != 3
                or type(row["project_id"]) is not int or row["project_id"] != PROJECT
                or type(row["job_id"]) is not str or re.fullmatch(r"[A-Za-z0-9_-]{1,200}", row["job_id"]) is None): _fail()
        hashes = row["input_hashes"]
        if type(hashes) is not dict or not 1 <= len(hashes) <= 32 or hashes.get("calendar.json") != CALENDAR_SHA256: _fail()
        for key, digest in hashes.items():
            if type(key) is not str or re.fullmatch(r"[A-Za-z0-9_.-]{1,200}", key) is None or type(digest) is not str or re.fullmatch(r"[a-f0-9]{64}", digest) is None: _fail()
        return {key: row[key] for key in ("candidate_id", "config_sha256", "freeze_sha256", "attempt", "project_id", "job_id")}, _sha(_canonical(hashes))

    def _capture(self, kind, error, build):
        if kind in self._attempted: return False
        self._attempted.add(kind); self._outcomes[kind] = {"status": "failed_or_uncertain", "descriptor": None}
        try:
            if type(error) is not ValueError or len(error.args) != 1 or type(error.args[0]) is not str or error.args[0] not in REFUSALS[kind]: _fail()
            binding, inputs_hash = self._binding()
            payload = {"schema": "tpr-ext26-first-refusal-witness-v1", "operation_id": OPERATION, "look_ordinal": 31,
                **binding, "input_hashes_sha256": inputs_hash, "kind": kind, "original_refusal_code": REFUSALS[kind][error.args[0]],
                "original_refusal_preserved": True, "units_inferred": False, "economics_accepted": False,
                "new_codex_attempts": 0, "input_bound_scope": OPERATION, "details": build()}
            plain = _canonical(payload)
            if not 0 < len(plain) <= MAX_BYTES: _fail()
            stream = io.BytesIO()
            with gzip.GzipFile(fileobj=stream, mode="wb", filename="", compresslevel=9, mtime=0) as archive: archive.write(plain)
            encoded = stream.getvalue()
            if not 0 < len(encoded) <= MAX_BYTES: _fail()
            key = "tpr-ext26/refusal-witness/" + OPERATION + "/" + str(PROJECT) + "/" + binding["job_id"] + "/" + kind + "_json.gz"
            def check():
                if self._binding() != (binding, inputs_hash): _fail()
            check()
            if self._store.contains_key(key) is not False: _fail()
            check()
            if self._store.save_bytes(key, encoded) is not True: _fail()
            check()
            if self._store.contains_key(key) is not True: _fail()
            check()
            readback = _native_bytes(self._store.read_bytes(key))
            check()
            if readback != encoded or _sha(readback) != _sha(encoded) or gzip.decompress(readback) != plain: _fail()
            self._outcomes[kind] = {"status": "verified_private_witness", "descriptor": {"key": key,
                "plain_bytes": len(plain), "plain_sha256": _sha(plain), "gzip_bytes": len(encoded), "gzip_sha256": _sha(encoded)}}
            return True
        except Exception:
            return False

    def membership(self, error, *, etf, member_sid, raw_weight, guard_weight, end_time, now):
        def build():
            if etf not in ETFS: _fail()
            return {"etf": etf, "member_sid": _sid(member_sid), "raw_weight": _scalar(raw_weight),
                "guard_weight": _scalar(guard_weight), "end_time": _clock(end_time), "now": _clock(now),
                "no_unit_scaling_applied": True, "full_membership_rows_retained": False,
                "source_version": None, "unit_expected": None, "source_date": None}
        return self._capture("membership", error, build)

    def mark(self, error, *, member_sid, mark_object, end_time, mark_utc, now, session, warning, delisted, action_flags,
             bar_time=None, period=None, fill_forward=None, native_quantity=None, ledger_quantity=None, raw_price=None, cache_price=None):
        def build():
            if type(session) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", session) is None: _fail()
            datetime.strptime(session, "%Y-%m-%d")
            if type(warning) is not bool or type(delisted) is not bool or type(action_flags) is not dict or set(action_flags) != ACTION_KEYS: _fail()
            if any(value is not None and type(value) is not bool for value in action_flags.values()): _fail()
            if fill_forward is not None and type(fill_forward) is not bool: _fail()
            return {"member_sid": _sid(member_sid), "mark_type": _type_name(mark_object), "end_time": _clock(end_time),
                "mark_utc": _clock(mark_utc), "now": _clock(now), "session": session, "warning_id_observed": warning,
                "delisted_id_observed": delisted, "action_flags": dict(action_flags), "settlement_authority_proven": False,
                "freshness_exception_granted": False, "full_price_bar_rows_retained": False,
                "bar_time": _clock(bar_time), "period": _scalar(period), "fill_forward": fill_forward,
                "native_quantity": _scalar(native_quantity), "ledger_quantity": _scalar(ledger_quantity),
                "raw_price": _scalar(raw_price), "cache_price": _scalar(cache_price)}
        return self._capture("mark", error, build)


class ContextRefusalWitness(FirstRefusalWitness):
    """Thin context adapter; use ONE persistent instance inside original handlers."""
    def __init__(self, native_evidence, native_store, numeric_core, trade_bar_type):
        super().__init__(native_evidence, native_store)
        self._numeric_core, self._trade_bar_type = numeric_core, trade_bar_type
        self._context_attempted = set()

    @staticmethod
    def _identity(symbol):
        native_id = symbol.id
        if type(native_id) is str: return _sid(native_id)
        if _type_name(native_id) != "QuantConnect.SecurityIdentifier": _fail()
        return _sid(native_id.ToString())

    @staticmethod
    def _optional(obj, name):
        try: return getattr(obj, name)
        except Exception: return None

    def membership_context(self, error, etf, members, rows, now):
        try:
            if "membership" in self._context_attempted: return False
            self._context_attempted.add("membership")
            if type(error) is not ValueError or error.args != ("membership weight outside bounds",): _fail()
            if type(members) is not list or type(rows) is not list or not 0 < len(members) == len(rows) <= 4096: _fail()
            member_ids = [self._identity(member["symbol"]) for member in members]
            row_ids = [self._identity(row.symbol) for row in rows]
            if len(set(member_ids)) != len(member_ids) or len(set(row_ids)) != len(row_ids) or member_ids != row_ids: _fail()
            tickers = [member["ticker"] for member in members]
            if any(type(ticker) is not str or not ticker for ticker in tickers) or len(set(tickers)) != len(tickers): _fail()
            for index, member in enumerate(members):
                canonical = member["weight"]
                if canonical is None: continue
                number = self._numeric_core._number(canonical)
                if 0 <= number <= 1: continue
                row = rows[index]
                raw = row.weight
                if raw is None or self._numeric_core._text(self._numeric_core.native_fraction(raw)) != canonical: _fail()
                return self.membership(error, etf=etf, member_sid=member_ids[index], raw_weight=raw,
                    guard_weight=canonical, end_time=row.end_time, now=now)
            return False
        except Exception:
            return False

    def mark_context(self, error, algo, held, security, last, mark_clock, price, day, now):
        try:
            if "mark" in self._context_attempted: return False
            self._context_attempted.add("mark")
            if type(error) is not ValueError or len(error.args) != 1 or type(error.args[0]) is not str or error.args[0] not in REFUSALS["mark"]: _fail()
            sid = self._identity(held.symbol)
            warning_ids, delisted_ids = algo._warning_ids, algo._delisted_ids
            if type(warning_ids) is not set or type(delisted_ids) is not set: _fail()
            is_bar = isinstance(last, self._trade_bar_type)
            ledger = self._optional(algo, "_quantity_ledger")
            ledger_quantity = ledger.get(sid) if type(ledger) is dict else None
            return self.mark(error, member_sid=sid, mark_object=last,
                end_time=self._optional(last, "end_time") if is_bar else None,
                mark_utc=mark_clock, now=now, session=day, warning=sid in warning_ids,
                delisted=sid in delisted_ids, action_flags={key: None for key in ACTION_KEYS},
                bar_time=self._optional(last, "time") if is_bar else None,
                period=self._optional(last, "period") if is_bar else None,
                fill_forward=self._optional(last, "is_fill_forward") if is_bar else None,
                native_quantity=self._optional(held, "quantity"), ledger_quantity=ledger_quantity,
                raw_price=self._optional(last, "price") if is_bar else None, cache_price=price)
        except Exception:
            return False
