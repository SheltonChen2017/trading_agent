"""Pure supplied-byte adapter for one narrowly versioned native QC export.

This module never connects to QC, obtains credentials, launches a run, reads a
file, or authenticates a response. The application's independently established
capture-manifest root is the trust boundary for response provenance, request
ranges, compile/run association and the supplied compiled-project source.
Rehashing an untrusted export does not establish that boundary.

Native profile references (checked 2026-10-06):
https://www.quantconnect.com/docs/v2/cloud-platform/api-reference/backtest-management/read-backtest/orders
https://www.quantconnect.com/docs/v2/cloud-platform/api-reference/backtest-management/read-backtest/backtest-statistics
https://www.quantconnect.com/docs/v2/cloud-platform/api-reference/backtest-management/read-backtest/logs
https://www.quantconnect.com/docs/v2/cloud-platform/api-reference/file-management/read-file
https://www.quantconnect.com/docs/v2/cloud-platform/api-reference/compiling-code/read-compilation-result

Orders contain their native events. A separately supplied native event array
must equal that complete flattened inventory; no order-events REST endpoint is
invented. Unknown profiles, fields, truncation and partial fills refuse. The
existing terminal validator remains authoritative for the order-path verdict.
Even an accepted export is UNADJUDICATED, not empirical IB-5 acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import hashlib
import json
import re
import weakref

from research.insider_buying import backtest_study_package as study


PROFILE = "INSETF-IB-QC-NATIVE-REST-EXPORT-v1"
MAX_BYTES = 16_000_000
MAX_TOTAL_BYTES = 64_000_000
MAX_PAGES = 500
MAX_ORDERS = 40_000
MAX_EVENTS = 120_000
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,79}\Z")
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z\Z")
_SEAL = object()
_BUILT: dict[int, tuple[weakref.ReferenceType, bytes]] = {}
_ORDER_REQUIRED = {"id", "symbol", "time", "quantity", "type", "status", "tag", "securityType", "direction", "events", "lastFillTime"}
_ORDER_FIELDS = _ORDER_REQUIRED | {"contingentId", "brokerId", "limitPrice", "stopPrice", "stopTriggered", "price", "priceCurrency", "createdTime", "lastUpdateTime", "canceledTime", "value", "orderSubmissionData", "isMarketable", "properties", "trailingAmount", "trailingAsPercentage", "groupOrderManager", "triggerPrice", "triggerTouched"}
_EVENT_FIELDS = {"algorithmId", "symbol", "symbolValue", "symbolPermtick", "orderId", "orderEventId", "id", "status", "orderFeeAmount", "orderFeeCurrency", "fillPrice", "fillPriceCurrency", "fillQuantity", "direction", "message", "isAssignment", "stopPrice", "limitPrice", "quantity", "time", "isInTheMoney"}
_BACKTEST_REQUIRED = {"projectId", "backtestId", "completed", "status", "error", "stacktrace", "hasInitializeError", "statistics", "runtimeStatistics", "serverStatistics"}
_BACKTEST_FIELDS = _BACKTEST_REQUIRED | {"note", "name", "organizationId", "optimizationId", "tradeableDates", "researchGuide", "backtestStart", "backtestEnd", "created", "snapshotId", "progress", "charts", "parameterSet", "rollingWindow", "totalPerformance", "nodeName", "outOfSampleMaxEndDate", "outOfSampleDays", "analysis"}
_CAPTURE_FIELDS = {"schema", "profile", "trust_scope", "origin", "mode", "package_sha256", "project_id", "compile_id", "backtest_id", "attempt_id", "compiled_source_sha256", "project_files_sha256", "signal_manifest_sha256", "gate_sha256", "calendar_sha256", "native_backtest_sha256", "native_compile_sha256", "native_order_events_sha256", "order_pages", "logs_pages"}


class QcExportAdapterError(ValueError):
    """A supplied export failed its provenance, profile or order-path binding."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise QcExportAdapterError("REFUSED: " + reason)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: object) -> str:
    _require(type(value) is str and _SHA.fullmatch(value) is not None, "exact lowercase SHA-256 required")
    return value


def _identity(value: object) -> str:
    _require(type(value) is str and _ID.fullmatch(value) is not None, "bounded identity required")
    return value


def _integer(value: object, minimum: int, maximum: int) -> int:
    _require(type(value) is int and minimum <= value <= maximum, "exact integer outside profile")
    return value


def _fields(value: object, required: set, allowed: set | None = None) -> dict:
    _require(type(value) is dict and required <= set(value) <= (required if allowed is None else allowed), "native or capture fields differ from profile")
    return value


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate JSON member")
        result[key] = value
    return result


def _decode(raw: bytes, expected: str, *, array: bool = False):
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, "supplied native bytes absent or unbounded")
    _require(_sha(raw) == _digest(expected), "supplied bytes do not match external capture root")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_float=Decimal,
                           parse_constant=lambda _: _require(False, "nonfinite native JSON"))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise QcExportAdapterError("REFUSED: malformed native JSON") from exc
    _require(type(value) is (list if array else dict), "native container type differs")
    return value


def _utc(value: object) -> datetime:
    _require(type(value) is str and _UTC.fullmatch(value) is not None, "exact native UTC timestamp required")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise QcExportAdapterError("REFUSED: invalid native timestamp") from exc


def _number(value: object) -> Decimal:
    _require(type(value) in {int, Decimal}, "native JSON number required, not bool/string/float")
    result = Decimal(value)
    _require(result.is_finite() and len(str(result)) <= 60, "native number nonfinite or unbounded")
    return result


def _native_equal(left, right, field="") -> bool:
    # JSON numbers may have equivalent integer/decimal spellings for documented
    # number fields. Identity integers and literal booleans remain exact types.
    numbers = {"orderFeeAmount", "fillPrice", "fillQuantity", "stopPrice", "limitPrice", "quantity", "time"}
    if field in numbers and type(left) in {int, Decimal} and type(right) in {int, Decimal}:
        return _number(left) == _number(right)
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return set(left) == set(right) and all(_native_equal(left[key], right[key], key) for key in left)
    if type(left) is list:
        return len(left) == len(right) and all(_native_equal(a, b, field) for a, b in zip(left, right, strict=True))
    return left == right


def _shares(value: object) -> int:
    number = _number(value)
    _require(number == number.to_integral_value() and number.copy_abs() <= 10**12, "fractional or unbounded native shares")
    return int(number)


def _event_time(value: object) -> datetime:
    seconds = _number(value)
    _require(0 <= seconds <= 4_102_444_800, "native event time outside profile")
    with localcontext() as context:
        context.prec = 100
        micros = seconds * 1_000_000
    _require(micros == micros.to_integral_value(), "native event timestamp loses submicrosecond precision")
    return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=int(micros))


def _success(body: dict) -> None:
    _require(body.get("success") is True and type(body.get("errors")) is list and body["errors"] == [], "native API response is unsuccessful")


@dataclass(frozen=True, slots=True)
class QcExportTrustRoots:
    """Application-established capture authority; this class does not authenticate."""

    trust_scope: str
    capture_manifest_sha256: str

    def validate(self) -> None:
        _require(type(self) is QcExportTrustRoots and type(self.trust_scope) is str
                 and self.trust_scope in {"fixture", "production"}, "exact separate export trust scope required")
        _digest(self.capture_manifest_sha256)


@dataclass(frozen=True, slots=True, weakref_slot=True)
class QcExportAnalysis:
    """Factory-bound terminal bytes and detached native-adaptation evidence."""

    _bytes: bytes = field(repr=False)
    _token: object = field(repr=False, compare=False)

    def _body(self) -> dict:
        registered = _BUILT.get(id(self))
        _require(type(self) is QcExportAnalysis and self._token is _SEAL
                 and registered is not None and registered[0]() is self
                 and type(self._bytes) is bytes and self._bytes == registered[1], "native analysis reconstructed or altered")
        return json.loads(self._bytes)

    def to_payload(self) -> dict:
        return self._body()["summary"]

    def terminal_bytes(self) -> bytes:
        return bytes.fromhex(self._body()["terminal_hex"])

    def analysis(self) -> dict:
        return self._body()["analysis"]

    def native_fills(self) -> list[dict]:
        """Detached observed instants, never reconstructed from session dates."""
        return self._body()["native_fills"]

    def registered_terminal_bytes(self, *, registration_raw: bytes, manifest_raw: bytes,
                                  expected_registration_sha256: str, expected_manifest_sha256: str,
                                  expected_implementation_sha256: str) -> bytes:
        """Export only the strict exact-native-open timestamp profile.

        A genuine opening-auction fill callback may arrive after the open. It
        can pass the bounded legacy minute profile yet refuse this bridge.
        Callback time is never relabeled auction time; admitting that case
        requires independently bound auction/price evidence and a successor
        profile, not a relaxed timestamp check or inferred opening fill.
        """
        return _registered_terminal(self, registration_raw, manifest_raw,
                                    expected_registration_sha256, expected_manifest_sha256,
                                    expected_implementation_sha256)

    @property
    def sha256(self) -> str:
        self._body()
        return _sha(self._bytes)


def _capture(package, raw, roots, mode):
    _require(type(package) is study.BacktestStudyPackage, "exact factory study package required")
    _require(type(roots) is QcExportTrustRoots, "exact external capture root required")
    roots.validate()
    payload, files = package.to_payload(), package.files()
    if payload["trust_scope"] == "production":
        _require(payload["candidate_enabled"] is True, "production export requires configured candidate bytes")
    capture = _fields(_decode(raw, roots.capture_manifest_sha256), _CAPTURE_FIELDS)
    _require(study.canonical_bytes(capture) == raw, "capture manifest encoding is not canonical")
    _require(capture["schema"] == "insider-qc-export-capture-v1" and capture["profile"] == PROFILE
             and capture["mode"] == mode and capture["trust_scope"] == roots.trust_scope == payload["trust_scope"]
             and capture["origin"] == {"fixture": "invented-native-QC-export", "production": "authenticated-QC-export"}[roots.trust_scope], "capture identity/profile/scope differs")
    _require(capture["package_sha256"] == package.sha256
             and capture["compiled_source_sha256"] == _sha(files["main.py"])
             and capture["signal_manifest_sha256"] == _sha(files["signals.json"])
             and capture["gate_sha256"] == _sha(files["gate.json"]), "capture compiled-source or object bindings differ")
    _integer(capture["project_id"], 1, 2**63 - 1)
    _identity(capture["compile_id"]); _identity(capture["attempt_id"])
    _require((capture["backtest_id"] is None) == (mode == "compile_failure"), "capture backtest identity inconsistent with mode")
    if mode == "backtest":
        _identity(capture["backtest_id"])
        _require(capture["native_compile_sha256"] is None, "backtest capture contains an unrelated compile export")
    else:
        _require(all(capture[name] is None for name in ("native_backtest_sha256", "native_order_events_sha256", "calendar_sha256"))
                 and capture["order_pages"] == [] and capture["logs_pages"] == [], "compile failure must not invent run telemetry")
    return capture, payload, files


def _source_and_objects(capture, files, project_files, cloud_signal_manifest, cloud_gate):
    body = _fields(_decode(project_files, capture["project_files_sha256"]), {"files", "success", "errors"})
    _success(body)
    _require(type(body["files"]) is list and len(body["files"]) == 1, "compiled project must have exactly the standalone source")
    item = _fields(body["files"][0], {"projectId", "name", "content", "isLibrary"}, {"id", "projectId", "name", "content", "modified", "open", "isLibrary"})
    _require(type(item["projectId"]) is int and item["projectId"] == capture["project_id"]
             and item["name"] == "main.py" and item["isLibrary"] is False
             and type(item["content"]) is str, "compiled project file identity differs")
    try:
        source = item["content"].encode("utf-8")
    except UnicodeError as exc:
        raise QcExportAdapterError("REFUSED: cloud source encoding differs") from exc
    _require(source == files["main.py"], "cloud source is not the exact rendered candidate")
    for name, supplied in (("signals.json", cloud_signal_manifest), ("gate.json", cloud_gate)):
        _require(type(supplied) is bytes and supplied == files[name], "cloud object bytes differ from exact package")


def _pages(raws, descriptors, *, logs=False):
    bound = 200 if logs else 99  # Documentation says order end-start must be <100.
    _require(type(raws) is tuple and 1 <= len(raws) <= MAX_PAGES
             and type(descriptors) is list and len(descriptors) == len(raws), "native pagination inventory absent or unbounded")
    cursor, values, reported_total = 0, [], None
    for index, (raw, descriptor) in enumerate(zip(raws, descriptors, strict=True)):
        descriptor = _fields(descriptor, {"start", "end", "sha256"})
        start = _integer(descriptor["start"], 0, MAX_EVENTS)
        end = _integer(descriptor["end"], 1, MAX_EVENTS)
        _require(start == cursor and 0 < end - start <= bound, "page ranges overlap, gap, reorder or exceed native profile")
        key = "logs" if logs else "orders"
        body = _fields(_decode(raw, descriptor["sha256"]), {key, "length", "success", "errors"} if logs else {key, "length"}, {key, "length", "success", "errors"})
        if logs or "success" in body or "errors" in body:
            _success(body)
        _require(type(body[key]) is list and len(body[key]) <= end - start, "native page returned count exceeds request")
        length = _integer(body["length"], 0, MAX_EVENTS)
        if logs:
            if reported_total is None:
                reported_total = length
            _require(length == reported_total, "native log total changed between pages")
            _require(len(body[key]) == min(end, length) - start, "native log page missing lines")
        else:
            _require(length == len(body[key]), "native order length is not returned-page count")
        _require(len(body[key]) == end - start or index == len(raws) - 1, "short interior native page")
        values.extend(body[key]); cursor = end
    if logs:
        _require(len(values) == reported_total and cursor >= reported_total, "native log pagination incomplete")
    return values


def _calendar(raw, capture, payload, manifest):
    _require(capture["calendar_sha256"] == payload["artifact_sha256s"]["calendar"], "capture calendar is not package evidence")
    body = _fields(_decode(raw, capture["calendar_sha256"]), {"schema", "trust_scope", "sessions"})
    _require(body["schema"] == "insider-backtest-calendar-v1" and body["trust_scope"] == payload["trust_scope"]
             and type(body["sessions"]) is list and len(body["sessions"]) == len(manifest["sessions"]), "native adaptation calendar differs")
    result = {}
    for item, session in zip(body["sessions"], manifest["sessions"], strict=True):
        _fields(item, {"session", "open_utc", "close_utc"})
        opened, closed = _utc(item["open_utc"]), _utc(item["close_utc"])
        _require(item["session"] == session and opened < closed, "calendar session identity differs")
        result[session] = (opened, closed)
    return result


def _order_fills(orders, events, capture, payload, manifest, calendar):
    _require(type(events) is list and len(events) <= MAX_EVENTS and len(orders) <= MAX_ORDERS, "native order/event inventory unbounded")
    expected = {f'IB5:{payload["registered_look_id"]}:{row["signal_id"]}:{side.upper()}': (row, side)
                for row in manifest["signals"] for side in ("entry", "exit")}
    flat, fills, native_fills, seen_ids, seen_tags, seen_event_ids = [], [], [], set(), set(), set()
    errors, net = [], {}
    for order in orders:
        _fields(order, _ORDER_REQUIRED, _ORDER_FIELDS)
        identity = _integer(order["id"], 1, 2**63 - 1)
        _require(identity not in seen_ids and type(order["tag"]) is str and order["tag"] in expected
                 and order["tag"] not in seen_tags, "duplicate, foreign or unattributed native order")
        seen_ids.add(identity); seen_tags.add(order["tag"])
        row, side = expected[order["tag"]]
        symbol = _fields(order["symbol"], {"id", "value", "permtick"})
        _require(symbol["id"] == row["qc_symbol_id"] and symbol["value"] == row["ticker"]
                 and type(symbol["permtick"]) is str and symbol["permtick"], "native SID/ticker identity differs")
        quantity = _shares(order["quantity"])
        _require(quantity != 0 and (quantity > 0) == (side == "entry")
                 and type(order["type"]) is int and order["type"] == 4
                 and type(order["securityType"]) is int and order["securityType"] == 1
                 and type(order["direction"]) is int and order["direction"] == (0 if side == "entry" else 1)
                 and type(order["status"]) is int and order["status"] in {1, 3, 5, 7}, "native order type, direction or status differs")
        fill_session = row[side + "_session"]
        prior = manifest["sessions"][manifest["sessions"].index(fill_session) - 1]
        submitted = _utc(order["time"])
        _require(submitted == calendar[prior][1] + timedelta(minutes=1), "native submission not pinned after-close decision")
        if "createdTime" in order:
            _require(_utc(order["createdTime"]) == submitted, "native created/submitted time differs")
        native_events = order["events"]
        _require(type(native_events) is list and 1 <= len(native_events) <= 100, "native event lifecycle absent or unbounded")
        previous, filled, terminal = submitted, None, False
        for event_index, event in enumerate(native_events, 1):
            _fields(event, _EVENT_FIELDS)
            event_id = _identity(event["id"])
            instant = _event_time(event["time"])
            _require(event_id not in seen_event_ids and type(event["orderId"]) is int and event["orderId"] == identity
                     and type(event["orderEventId"]) is int and event["orderEventId"] == event_index
                     and event["algorithmId"] == capture["backtest_id"] and event["symbol"] == symbol["id"]
                     and event["symbolValue"] == symbol["value"] and event["symbolPermtick"] == symbol["permtick"]
                     and instant >= previous and not terminal, "native event association, sequence or time differs")
            seen_event_ids.add(event_id); previous = instant
            _require(event["direction"] == ("buy" if side == "entry" else "sell") and _shares(event["quantity"]) == quantity
                     and event["isAssignment"] is False and event["isInTheMoney"] is False
                     and event["fillPriceCurrency"] == "USD" and event["orderFeeCurrency"] == "USD"
                     and type(event["message"]) is str and len(event["message"]) <= 2000
                     and _number(event["orderFeeAmount"]) >= 0, "native event financial or option fields differ")
            status = event["status"]
            _require(type(status) is str and status in {"new", "submitted", "filled", "canceled", "invalid"}, "partial or unknown native event status")
            fill_quantity, price = _shares(event["fillQuantity"]), _number(event["fillPrice"])
            if status == "filled":
                opening = calendar[fill_session][0]
                _require(fill_quantity == quantity and price > 0 and opening <= instant <= opening + timedelta(minutes=1), "native fill quantity, price or opening-minute time differs")
                _require(_utc(order["lastFillTime"]) == instant and order["status"] == 3, "native order/fill terminal state differs")
                filled = {"signal_id": row["signal_id"], "side": side, "qc_symbol_id": symbol["id"], "session": fill_session,
                          "quantity": quantity, "price": str(price), "status": "Filled", "order_id": str(identity)}
                native_fills.append({**filled, "filled_at_utc": instant.isoformat().replace("+00:00", "Z")})
                terminal = True
                net[symbol["id"]] = net.get(symbol["id"], 0) + quantity
            else:
                _require(fill_quantity == 0 and price == 0, "nonfill event carries execution quantities")
                if status in {"canceled", "invalid"}:
                    _require(order["status"] == (5 if status == "canceled" else 7), "native terminal rejection differs")
                    terminal = True
            flat.append(event)
        if filled is not None:
            fills.append(filled)
        else:
            _require(order["lastFillTime"] is None and order["status"] != 3, "filled native order lacks fill event")
            errors.append("native_order_not_fully_filled")
    _require(_native_equal(flat, events), "separate native order-event inventory differs or is incomplete")
    positions = [{"qc_symbol_id": sid, "quantity": quantity} for sid, quantity in sorted(net.items()) if quantity]
    return fills, positions, sorted(set(errors)), native_fills


def _terminal(package, payload, files, capture, status, errors, sessions, orders, positions, fills):
    terminal = {"schema": "insider-backtest-terminal-result-v1", "trust_scope": payload["trust_scope"],
        "package_sha256": package.sha256, "candidate_id": payload["candidate_id"], "registered_look_id": payload["registered_look_id"],
        "manifest_sha256": _sha(files["signals.json"]), "gate_sha256": _sha(files["gate.json"]),
        "candidate_source_sha256": _sha(files["main.py"]), "outcome_vintage_sha256": payload["artifact_sha256s"]["outcome"],
        "attempt_id": capture["attempt_id"], "project_id": str(capture["project_id"]), "compile_id": capture["compile_id"],
        "backtest_id": capture["backtest_id"], "status": status, "errors": errors, "processed_sessions": sessions,
        "submitted_order_count": orders, "final_positions": positions, "fills": fills}
    raw = study.canonical_bytes(terminal)
    analysis = study.analyze_terminal_result(package=package, raw=raw, expected_result_sha256=_sha(raw))
    return raw, analysis


def _seal(raw, analysis, capture, *, order_count=0, event_count=0, source_verified=True, engine_version=None,
          native_fills=None, qc_manifest=None, calendar_rows=None, package_binding=None):
    summary = {"kind": PROFILE, "capture_trust_scope": capture["trust_scope"],
        "provenance_boundary": "externally_anchored_capture_not_authenticated_here", "capture_manifest_sha256": _sha(study.canonical_bytes(capture)),
        "package_sha256": capture["package_sha256"], "compiled_source_sha256": capture["compiled_source_sha256"],
        "terminal_sha256": _sha(raw), "native_order_count": order_count, "native_order_event_count": event_count,
        "cloud_source_byte_parity": source_verified, "cloud_manifest_gate_byte_parity": True,
        "compile_run_association_verified_here": False,
        "processed_sessions_evidence": "pinned_candidate_completion_marker" if analysis["order_path_verified"] else "not_proven",
        "complete_order_path": analysis["order_path_verified"], "statistical_gate": "UNADJUDICATED", "ib5_pass": False,
        "engine_version_observed": engine_version, "engine_revision_parity_verified": False,
        "data_vintage_parity_verified": False, "brokerage_cost_model_parity_verified": False,
        "opening_price_model_parity_verified": False, "execution_performed_here": False,
        "qc_jobs_launched_here": 0, "research_looks_spent_here": 0, "broker_authority": False}
    encoded = study.canonical_bytes({"summary": summary, "analysis": analysis, "terminal_hex": raw.hex(),
        "native_fills": [] if native_fills is None else native_fills, "qc_manifest": qc_manifest,
        "calendar_rows": calendar_rows, "package_binding": package_binding})
    result = QcExportAnalysis(encoded, _SEAL)
    identity = id(result)
    _BUILT[identity] = (weakref.ref(result, lambda _: _BUILT.pop(identity, None)), encoded)
    return result


def adapt_qc_export(*, package: study.BacktestStudyPackage, native_backtest: bytes,
                    order_pages: tuple[bytes, ...], native_order_events: bytes,
                    project_files: bytes, cloud_signal_manifest: bytes, cloud_gate: bytes,
                    calendar: bytes, logs_pages: tuple[bytes, ...], capture_manifest: bytes,
                    trust_roots: QcExportTrustRoots) -> QcExportAnalysis:
    """Derive a terminal export from supplied native records, never retrieve one.

    Filled MOO events must fall at the anchored opening instant or the first
    minute bar timestamp. This narrow minute-feed profile does not certify the
    engine's opening-price, fee/slippage or data-vintage parity.
    """
    capture, payload, files = _capture(package, capture_manifest, trust_roots, "backtest")
    _require(type(order_pages) is tuple and type(logs_pages) is tuple
             and all(type(raw) is bytes for raw in order_pages + logs_pages), "exact native page-byte tuples required")
    _require(sum(len(raw) for raw in (native_backtest, native_order_events, project_files, cloud_signal_manifest, cloud_gate, calendar, capture_manifest) + order_pages + logs_pages if type(raw) is bytes) <= MAX_TOTAL_BYTES, "aggregate export bytes exceed bound")
    _source_and_objects(capture, files, project_files, cloud_signal_manifest, cloud_gate)
    manifest = study.verify_signal_manifest(cloud_signal_manifest)
    clock = _calendar(calendar, capture, payload, manifest)
    body = _fields(_decode(native_backtest, capture["native_backtest_sha256"]), {"backtest", "success", "errors"}, {"backtest", "success", "errors", "debugging"})
    _success(body)
    backtest = _fields(body["backtest"], _BACKTEST_REQUIRED, _BACKTEST_FIELDS)
    _require(type(backtest["projectId"]) is int and backtest["projectId"] == capture["project_id"]
             and backtest["backtestId"] == capture["backtest_id"] and type(backtest["completed"]) is bool
             and type(backtest["hasInitializeError"]) is bool and type(backtest["error"]) is str
             and type(backtest["stacktrace"]) is str, "native backtest identity or terminal flags differ")
    _require(type(backtest["status"]) is str and backtest["status"] in {"Completed.", "Runtime Error"}, "unknown/nonterminal native backtest status")
    _require(type(backtest["statistics"]) is dict and type(backtest["statistics"].get("Total Orders")) is str
             and re.fullmatch(r"0|[1-9][0-9]{0,5}", backtest["statistics"]["Total Orders"]) is not None, "native total-order count absent or noncanonical")
    orders = _pages(order_pages, capture["order_pages"])
    _require(len(orders) == int(backtest["statistics"]["Total Orders"]), "native order pagination is incomplete")
    events = _decode(native_order_events, capture["native_order_events_sha256"], array=True)
    fills, positions, errors, native_fills = _order_fills(orders, events, capture, payload, manifest, clock)
    logs = _pages(logs_pages, capture["logs_pages"], logs=True)
    _require(all(type(line) is str and len(line) <= 4000 for line in logs), "native log lines unbounded")
    expected_input = f'IBQC_STUDY_INPUT|look={payload["registered_look_id"]}|manifest={_sha(files["signals.json"])}|gate={_sha(files["gate.json"])}|signals={len(manifest["signals"])}|canonical=false'
    expected_end = f'IBQC_STUDY_ORDER_PATH_COMPLETE|look={payload["registered_look_id"]}|manifest={_sha(files["signals.json"])}|entries={len(manifest["signals"])}|exits={len(manifest["signals"])}|canonical=false'
    def marker(line):
        # Native exports may prepend their timestamp. No arbitrary embedded match.
        return re.sub(r"\A[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} : ", "", line)
    markers = [marker(line) for line in logs]
    _require(markers.count(expected_input) == 1, "native pinned-source input marker absent, duplicate or changed")
    status = "Completed" if backtest["status"] == "Completed." else "RuntimeError"
    clean = backtest["completed"] is True and not backtest["hasInitializeError"] and backtest["error"] == "" and backtest["stacktrace"] == ""
    complete = markers.count(expected_end) == 1 and markers.index(expected_input) < markers.index(expected_end)
    if not clean:
        errors.append("native_backtest_not_clean")
    if not complete:
        errors.append("native_completion_evidence_missing")
    holdings = backtest["runtimeStatistics"]
    _require(type(holdings) is dict and type(holdings.get("Holdings")) is str, "native terminal holdings absent")
    if re.fullmatch(r"\$0(?:\.0+)?", holdings["Holdings"]) is None:
        errors.append("native_terminal_holdings_not_zero")
    servers = backtest["serverStatistics"]
    _require(type(servers) is dict and type(servers.get("LEAN Version")) is str
             and 0 < len(servers["LEAN Version"]) <= 80, "native engine-version observation absent")
    raw, analysis = _terminal(package, payload, files, capture, status, sorted(set(errors)),
                              manifest["sessions"] if complete and clean else [], len(orders), positions, fills)
    package_binding = {"candidate_id": payload["candidate_id"], "registered_look_id": payload["registered_look_id"],
                       "artifact_sha256s": payload["artifact_sha256s"], "trust_scope": payload["trust_scope"]}
    return _seal(raw, analysis, capture, order_count=len(orders), event_count=len(events), engine_version=servers["LEAN Version"],
                 native_fills=native_fills, qc_manifest=manifest, calendar_rows=json.loads(calendar)["sessions"],
                 package_binding=package_binding)


def adapt_qc_compile_failure(*, package: study.BacktestStudyPackage, native_compile: bytes,
                             project_files: bytes, cloud_signal_manifest: bytes, cloud_gate: bytes,
                             capture_manifest: bytes, trust_roots: QcExportTrustRoots) -> QcExportAnalysis:
    """Represent native BuildError without inventing a backtest identity or fills."""
    capture, payload, files = _capture(package, capture_manifest, trust_roots, "compile_failure")
    _source_and_objects(capture, files, project_files, cloud_signal_manifest, cloud_gate)
    body = _fields(_decode(native_compile, capture["native_compile_sha256"]), {"compileId", "state", "logs", "success", "errors"})
    _success(body)
    _require(body["compileId"] == capture["compile_id"] and body["state"] == "BuildError"
             and type(body["logs"]) is list and 0 < len(body["logs"]) <= 100
             and all(type(line) is str and 0 < len(line) <= 4000 for line in body["logs"]), "native compile failure profile differs")
    raw, analysis = _terminal(package, payload, files, capture, "CompileError", ["native_compile_build_error"], [], 0, [], [])
    return _seal(raw, analysis, capture)


def _registered_terminal(value, registration_raw, manifest_raw, registration_sha,
                         manifest_sha, implementation_sha):
    """A compatible bridge, never a conversion of a different event clock."""
    _require(type(value) is QcExportAnalysis, "exact native export factory output required")
    body = value._body()
    _require(body["analysis"]["order_path_verified"] is True, "registered bridge requires proven clean native order path")
    # This shared validator checks the executable registration descriptors and
    # complete literal-first-open calendar context WITHOUT reading any panel.
    from research.insider_buying import backtest_registered_analysis as registered
    try:
        checked = registered.verify_registered_analysis_manifest(
            registration_raw=registration_raw, manifest_raw=manifest_raw,
            expected_registration_sha256=registration_sha, expected_manifest_sha256=manifest_sha,
            expected_implementation_sha256=implementation_sha)
        qc_raw = study.canonical_bytes(body["qc_manifest"])
        registered.analysis_manifest_to_qc_manifest(
            registration_raw=registration_raw, manifest_raw=manifest_raw,
            expected_registration_sha256=registration_sha, expected_manifest_sha256=manifest_sha,
            expected_implementation_sha256=implementation_sha,
            qc_manifest_template_raw=qc_raw, expected_qc_manifest_sha256=_sha(qc_raw))
    except registered.RegisteredAnalysisError as exc:
        raise QcExportAdapterError("REFUSED: registered manifest or canonical event-clock binding differs") from exc
    registration, manifest = checked["registration"], checked["manifest"]
    binding = body["package_binding"]
    _require(registration["trust_scope"] == binding["trust_scope"]
             and registration["candidate_id"] == binding["candidate_id"]
             and registration["registered_look_id"] == binding["registered_look_id"]
             and registration["rights_sha256"] == binding["artifact_sha256s"]["rights"], "registered candidate/look/rights differ from native package")
    _require(manifest["sessions"] == body["calendar_rows"], "registered full calendar instants differ from captured native calendar")
    events = {event["signal_id"]: event for event in manifest["events"]}
    clock = {row["session"]: row["open_utc"] for row in manifest["sessions"]}
    fills, seen = [], set()
    for native in body["native_fills"]:
        event = events.get(native["signal_id"])
        key = (native["signal_id"], native["side"])
        _require(event is not None and key not in seen and native["qc_symbol_id"] == event["security_id"]
                 and native["session"] == event[native["side"] + "_session"]
                 and native["filled_at_utc"] == clock[native["session"]], "native fill is not exact registered SID/session/open instant")
        seen.add(key)
        fills.append({"signal_id": native["signal_id"], "side": native["side"], "security_id": native["qc_symbol_id"],
                      "session": native["session"], "filled_at_utc": native["filled_at_utc"],
                      "quantity": native["quantity"], "price": format(Decimal(native["price"]), "f"), "order_id": native["order_id"]})
    _require(seen == {(event["signal_id"], side) for event in manifest["events"] for side in ("entry", "exit")}, "registered native fill population differs")
    return registered.canonical_bytes({"schema": "insider-stock-event-study-terminal-v1",
        "trust_scope": registration["trust_scope"], "registration_sha256": registration_sha, "manifest_sha256": manifest_sha,
        "candidate_id": registration["candidate_id"], "registered_look_id": registration["registered_look_id"],
        "outcome_vintage_sha256": registration["outcome_vintage_sha256"], "status": "Completed", "errors": [],
        "final_positions": [], "fills": fills})
