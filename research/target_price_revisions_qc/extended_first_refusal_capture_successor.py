"""Pure prospective look31 capture contracts; no opener, signer or execution.

A controller must durably spend fresh access/request claims before credentials,
retain every returned projection/envelope before validation, and retain failures
or cancellation. These builders grant no effect authority. Source preflight and
declared built-in Mia provenance are not authenticated compiled-job proof.
Raw first-refusal witnesses stay in QC; no ObjectStore request is permitted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import math
import re

from . import extended_evidence as e
from . import extended_operations as ops

PROJECT = 37650980
CANDIDATE = "TPR-CAP-TILT-EXT26-OFF-BASE-v1"
OPERATION = "TPR-EXT26-MIA-FIRST-REFUSAL-20261014-001"
ACTOR = "quantconnect-built-in-mia"
CONFIG = "19a9842cfceb695d1f8256f429745247387c89bb725ee2b8be44fe98a726322a"
FREEZE = "90bdec5520b29bd932a3ec730f7c4c40c544ea7582731ad6680ef34ea8cf4067"
CALENDAR = "3eccdf3cf9a2542ffd249983241d5747c2ecd4e21bc4a71f7f826c77ec1fe53d"
MAX_SECONDS, MAX_TOTAL, MAX_PAGES, PAGE_SIZE = 600, 64 * 1024 * 1024, 128, 99
MAX_RECEIPT, MAX_ENVELOPE = 64 * 1024, 4 * 1024 * 1024
CHARTS = ("Strategy Equity", "EXT26 Account NAV")
CHART_START, CHART_END, CHART_COUNT = 1609718400, 1791590400, 2000
READ_LIMITS = (("backtests/read", 2 * 1024 * 1024),
               ("backtests/read/log", 1024 * 1024),
               ("backtests/chart/read", 2 * 1024 * 1024),
               ("backtests/orders/read", 1024 * 1024))
PRIOR_JOBS = frozenset((
    "34e0636f373c5ed9ee97387335b52454", "f79d3ff02644ec81f20da5cc6ca7440a",
    "d7c76b7c4936c814f125a2b9a8cc2896", "e3324aef9bd2af2caf16a32468eeb101",
    "7dacf829bda2cf1bbe6d75cac5ab5ca3", "1abad98d7e15a7fa2bde33b8d6343e2c",
    "88775c7e3c8a377bece104bf33f0ba85", "ed1dd63ea51dc5e92fc7168165f65b67",
    "4f015ee786f90477b945b181a187a11f", "55a5f738feab1d57ce81219cc8a2be5f",
    "8f8276efbdb6e25651a3b993f9df3f6d", "7e4c1487e6e9ca1fd10ce8f7f4cf9dbd",
    "b20cba66e8bdec79515466d73cd9584f", "4936632376c0885358493a2694ed239b"))
# All 16 names/descriptors, including unused originals, must be retained.
SOURCES = (
    ("cap_observer.py", 8712, "cad8a3306f6b459bc8bf187c8fd8b8bb980c7b1dc0d85465fba11dd318b70c4d"),
    ("cap_tilt.py", 14373, "262f568b7c0fe0b08af8a26896431465c17746bcd32e9addc568f58631e11a5c"),
    ("extended_completion_successor.py", 6084, "336e67bff64f484b57e49e92209e22bf9471118c0ee8b8d13c3ff7b8b2511fb6"),
    ("extended_compressed_store.py", 13987, "d661b5752c35b9dd04f783f5d78850f453d5f5f299874e5cf19700599df2356e"),
    ("extended_config.py", 428, "5790ca63661f0f54a7734565342d141cbaba7797eb8c7b1e488c7ad573b01bd0"),
    ("extended_construction.py", 10567, "e61bd56ad3ff5147eedf3220b40ef77743f8e13bff9919f80bc3f684a3fe27c0"),
    ("extended_core.py", 37572, "706ed5efdcb3999400c5349dc8b5200be1d48c4bb01cbfc7fb080608a679d5da"),
    ("extended_loader.py", 51383, "f5cc9d9cb56ebbae2a22f02d6b6b7041468eadbc77d87ed2e161c9ce119a3820"),
    ("extended_runtime_successor.py", 6712, "2e6bb5c82f356ee7ece4811c9d634ce57d48533d408d4b57b8aee41de062517b"),
    ("main.py", 60658, "a098c087c14507c154a4740d0145f7af1c448ec24905f4c8b66e82869d917d86"),
    ("research.ipynb", 1029, "af27200522531d426185f4daa25d23610c164134e3ab7fdf38919616d0d5b344"),
    ("mia.ipynb", 6100, "c753fe2c1b5d6de25d4d2fcf374a5a6915e8642293427430397e485941a09425"),
    ("mia_diag.py", 5253, "ca1df38f610e29d0507cdf2be134f974211135242947effc2d63351e4b96fb14"),
    ("mia_rescale.py", 4852, "0c68d8fd7a33ac8a29233bbc1597073e050c15066baf15a9efd59183a2b75f78"),
    ("audit_key_recovery.py", 7490, "bce4182d09dc9d31132cb54d404712471ddff5e2b706c2988fbe9fcc48c93aea"),
    ("extended_refusal_witness_context_successor.py", 15742, "1b057f254fba91eee98862bbb63b2141cea63962905c458459d7a47531215a0f"))
INPUTS = (
    ("calendar.json", CALENDAR),
    ("identities.json", "2cf0efc355e551fa853db3a00a4a10f235509a729a8119425845fe7575b06561"),
    ("preparation.json", "08e1d006b9ffef3554873722d5c40ebf739ff7e6dd2c372e78069ddf6cf2808f"),
    ("signal-manifest.json", "a9cbf9ad3ec485a11a2bf5c699326b4ca792579c43efb0e5b3a388a24ab36838"))
ARGUMENTS = ("action", "capture_operation_id", "git_head", "owner_instruction_sha256",
             "created_utc", "expires_utc", "source_inventory", "preflight", "mia")
Refusal = e.EvidenceError


def _fail():
    raise Refusal("prospective first-refusal capture refused; no automatic retry")


def _int(value, maximum):
    if type(value) is e.JsonNumber and value.fraction().denominator == 1:
        value = int(value.fraction())
    if type(value) is not int or not 0 <= value <= maximum: _fail()
    return value


def _clock(value):
    if type(value) is not str or len(value) > 64: _fail()
    try: result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError: _fail()
    if result.utcoffset() != timedelta(0): _fail()
    return result


def _descriptor(value, name, maximum):
    e._closed(value, {"name", "bytes", "sha256"})
    size = _int(value["bytes"], maximum)
    if value["name"] != name or not size: _fail()
    return {"name": name, "bytes": size, "sha256": e._hash(value["sha256"])}


def build_plan(*, action, capture_operation_id, git_head, owner_instruction_sha256,
               created_utc, expires_utc, source_inventory, preflight, mia):
    """Pure bounded capture plan; no look reservation or native authentication."""
    if action not in {"status", "collect-native"}: _fail()
    if (type(capture_operation_id) is not str or re.fullmatch(
            r"TPR-EXT26-MIA-FIRST-REFUSAL-RESULT-20261014-[0-9]{3}", capture_operation_id) is None): _fail()
    e._hash(git_head, 40); e._hash(owner_instruction_sha256)
    expected = {name: {"bytes": size, "sha256": identity} for name, size, identity in SOURCES}
    if e.canonical(source_inventory) != e.canonical(expected): _fail()
    e._closed(preflight, {"operation_id", "ended_utc", "receipt", "sources", "diff"})
    post = preflight["operation_id"]
    if (type(post) is not str or re.fullmatch(r"TPR-EXT26-MIA-SOURCE-POST-20261014-[0-9]{3}", post) is None): _fail()
    created, expires, ended = _clock(created_utc), _clock(expires_utc), _clock(preflight["ended_utc"])
    if not timedelta(0) < expires - created <= timedelta(seconds=MAX_SECONDS): _fail()
    if not timedelta(0) <= created - ended <= timedelta(minutes=15): _fail()
    bound_preflight = {"operation_id": post, "ended_utc": preflight["ended_utc"]}
    for role, suffix, maximum in (("receipt", ".result.json", MAX_RECEIPT),
                                   ("sources", ".read2.sources.json", e.MAX_BYTES),
                                   ("diff", ".diff.json", e.MAX_BYTES)):
        bound_preflight[role] = _descriptor(preflight[role], post + suffix, maximum)
    e._closed(mia, {"operation_id", "actor", "compile_id", "backtest_id", "legacy_attempt",
                   "codex_attempts_consumed", "observed_looks_before", "look_ordinal",
                   "ui_ledger", "look_receipt"})
    if mia["operation_id"] != OPERATION or mia["actor"] != ACTOR: _fail()
    for key, value in (("legacy_attempt", 3), ("codex_attempts_consumed", 3),
                        ("observed_looks_before", 30), ("look_ordinal", 31)):
        if _int(mia[key], 31) != value: _fail()
    e._id(mia["compile_id"]); e._id(mia["backtest_id"])
    if (re.fullmatch(r"[0-9a-f]{31,32}", mia["backtest_id"]) is None
            or mia["backtest_id"] in PRIOR_JOBS): _fail()
    binding = dict(mia)
    for key in ("legacy_attempt", "codex_attempts_consumed", "observed_looks_before", "look_ordinal"):
        binding[key] = _int(mia[key], 31)
    binding["ui_ledger"] = _descriptor(mia["ui_ledger"], OPERATION + ".ui-ledger.json", MAX_RECEIPT)
    binding["look_receipt"] = _descriptor(mia["look_receipt"], OPERATION + ".look.json", MAX_RECEIPT)
    return {"schema": "tpr-ext26-first-refusal-capture-plan-v1", "action": action,
        "capture_operation_id": capture_operation_id, "git_head": git_head,
        "owner_instruction_sha256": owner_instruction_sha256, "created_utc": created_utc,
        "expires_utc": expires_utc, "source_inventory": expected, "preflight": bound_preflight,
        "mia": binding, "project_id": PROJECT, "candidate_id": CANDIDATE,
        "config_sha256": CONFIG, "freeze_sha256": FREEZE, "calendar_sha256": CALENDAR,
        "max_seconds": MAX_SECONDS, "max_received_bytes": MAX_TOTAL, "request_seconds": 30,
        "max_order_pages": MAX_PAGES, "max_requests": 1 if action == "status" else 5 + MAX_PAGES,
        "read_endpoints": [name for name, _ in READ_LIMITS],
        "new_codex_attempts": 0, "new_looks": 0, "mia_look_counted_externally": 31,
        "automatic_retry": False, "object_export": False, "compiled_source_proven": False,
        "native_accounting_verified": False, "accepted_metrics": None,
        "strategy_accepted": False, "canonical_admission": False, "trading": False}


def validate_plan(plan):
    if type(plan) is not dict or any(key not in plan for key in ARGUMENTS): _fail()
    expected = build_plan(**{key: plan[key] for key in ARGUMENTS})
    if e.canonical(plan) != e.canonical(expected): _fail()
    return expected


def check_scope(plan, now, elapsed_seconds, received_bytes):
    validate_plan(plan)
    if (type(now) is not datetime or now.utcoffset() != timedelta(0)
            or not _clock(plan["created_utc"]) <= now < _clock(plan["expires_utc"])
            or not timedelta(0) <= now - _clock(plan["preflight"]["ended_utc"]) <= timedelta(minutes=15)
            or type(elapsed_seconds) not in (int, float) or not math.isfinite(elapsed_seconds)
            or not 0 <= elapsed_seconds < MAX_SECONDS): _fail()
    _int(received_bytes, MAX_TOTAL)


def request_allowed(plan, endpoint, payload):
    validate_plan(plan)
    if type(payload) is not dict or endpoint not in dict(READ_LIMITS): _fail()
    base = {"projectId": PROJECT, "backtestId": plan["mia"]["backtest_id"]}
    if endpoint == "backtests/read": expected = base
    elif endpoint == "backtests/read/log":
        if payload.get("query") not in {"EXT26_SUMMARY", "EXT26_EVIDENCE_INDEX"}: _fail()
        expected = {**base, "start": 0, "end": 100, "query": payload["query"]}
    elif endpoint == "backtests/chart/read":
        if payload.get("name") not in CHARTS: _fail()
        expected = {**base, "name": payload["name"], "count": CHART_COUNT,
                    "start": CHART_START, "end": CHART_END}
    else:
        start = payload.get("start")
        if type(start) is not int or not 0 <= start < MAX_PAGES * PAGE_SIZE or start % PAGE_SIZE: _fail()
        expected = {**base, "start": start, "end": start + PAGE_SIZE}
    if (e.canonical(payload) != e.canonical(expected)
            or plan["action"] == "status" and endpoint != "backtests/read"): _fail()
    return dict(expected)


def wire_descriptor(plan, endpoint, payload, wire, http_status):
    """Bounded raw-wire identity before decode/schema checks; never return rows.

    One reserved refusal byte is allowed, so an oversized response can leave a
    descriptor. Persist the descriptor before attempting projection/validation.
    This does not authorize unredacted wire persistence or credential hashing.
    """
    expected = request_allowed(plan, endpoint, payload)
    if type(wire) is not bytes or not 0 < len(wire) <= dict(READ_LIMITS)[endpoint] + 1: _fail()
    if type(http_status) is not int or not 100 <= http_status <= 599: _fail()
    return {"endpoint": endpoint, "request": expected, "http_status": http_status,
            "bytes": len(wire), "sha256": hashlib.sha256(wire).hexdigest()}


def request_budget(plan, endpoint, request_attempts, received_bytes):
    """Check counters before transport, reserving the one oversize-refusal byte."""
    bound = validate_plan(plan)
    if endpoint not in dict(READ_LIMITS): _fail()
    attempts = _int(request_attempts, bound["max_requests"])
    received = _int(received_bytes, MAX_TOTAL)
    if (attempts >= bound["max_requests"] or dict(READ_LIMITS)[endpoint] + 1 > MAX_TOTAL - received
            or bound["action"] == "status" and endpoint != "backtests/read"): _fail()


def retain_response(plan, endpoint, payload, wire, http_status, *, credential=""):
    """Return private envelope bytes BEFORE success/schema inspection.

    Known metadata is structurally redacted, exact numeric tokens preserved.
    Original-wire size/hash and the entire distinct projection survive. Caller
    must persist these returned bytes privately even if later inspection fails.
    No wire, free-text error, order/member row or witness is safe for public logs.
    """
    descriptor = wire_descriptor(plan, endpoint, payload, wire, http_status)
    expected = descriptor["request"]
    if len(wire) > dict(READ_LIMITS)[endpoint]: _fail()
    projection = e.project_wire(wire, credential=credential)
    raw = e.canonical({"schema": "tpr-ext26-first-refusal-read-envelope-v1",
        "capture_operation_id": plan["capture_operation_id"], "endpoint": endpoint,
        "request": expected, "http_status": http_status,
        "original_wire_bytes": len(wire), "original_wire_sha256": projection["original_wire_sha256"],
        "projection_sha256": projection["projection_sha256"], "response": projection["projection"]})
    if len(raw) > MAX_ENVELOPE: _fail()
    return raw


def response_from_envelope(plan, envelope):
    validate_plan(plan)
    if type(envelope) is not bytes or not 0 < len(envelope) <= MAX_ENVELOPE: _fail()
    body = e.parse_json(envelope)
    e._closed(body, {"schema", "capture_operation_id", "endpoint", "request", "http_status",
                    "original_wire_bytes", "original_wire_sha256", "projection_sha256", "response"})
    if (body["schema"] != "tpr-ext26-first-refusal-read-envelope-v1"
            or body["capture_operation_id"] != plan["capture_operation_id"]): _fail()
    payload = body["request"]
    if body["endpoint"] == "backtests/orders/read":
        payload = dict(payload); payload["start"] = _int(payload["start"], MAX_PAGES * PAGE_SIZE)
    request_allowed(plan, body["endpoint"], payload)
    if not _int(body["original_wire_bytes"], dict(READ_LIMITS)[body["endpoint"]]): _fail()
    e._hash(body["original_wire_sha256"])
    response = body["response"]
    if (e.digest(e.canonical(response)) != e._hash(body["projection_sha256"])
            or _int(body["http_status"], 599) != 200 or type(response) is not dict
            or response.get("success") is not True): _fail()
    ops._returned_identity(response, PROJECT, plan["mia"]["backtest_id"])
    return body, response


def terminal_observation(plan, envelope):
    body, response = response_from_envelope(plan, envelope)
    if body["endpoint"] != "backtests/read" or type(response.get("backtest")) is not dict: _fail()
    row = response["backtest"]
    if row.get("backtestId") != plan["mia"]["backtest_id"]: _fail()
    native_compile = row.get("compileId")
    if native_compile is not None and native_compile != plan["mia"]["compile_id"]: _fail()
    status, error = row.get("status"), row.get("error")
    if type(status) is not str or len(status) > 80: _fail()
    if error is not None and (type(error) is not str or not error): _fail()
    terminal = row.get("completed") is True and status in {"Completed", "Completed.", "Runtime Error", "Error", "Stopped", "Cancelled"}
    if terminal and ("error" not in row or status in {"Runtime Error", "Error"} and error is None): _fail()
    if terminal and status in {"Completed", "Completed."}:
        if error is not None or type(row.get("progress")) is not e.JsonNumber or row["progress"].fraction() != 1: _fail()
    return {"terminal": terminal, "status": status if status in {
        "Completed", "Completed.", "Runtime Error", "Error", "Stopped", "Cancelled", "Running", "In Progress..."
    } else "unrecognized_nonterminal", "compile_id_returned_and_matching": native_compile is not None,
        "native_compile_id": native_compile, "compiled_source_proven": False,
        "error_present": error is not None, "error_bytes": len(error.encode()) if error else 0,
        "error_sha256": hashlib.sha256(error.encode()).hexdigest() if error else None,
        "accepted_metrics": None, "native_accounting_verified": False, "strategy_accepted": False}


def compact_observation(plan, envelope):
    body, response = response_from_envelope(plan, envelope)
    if body["endpoint"] != "backtests/read/log": _fail()
    marker = body["request"]["query"]
    count, rows = _int(response.get("length"), 100), response.get("logs")
    if type(rows) is not list or len(rows) != count or count > 1: _fail()
    manifest = {"candidate_id": CANDIDATE, "project_id": PROJECT, "arm": "tpr_off",
                "config_sha256": CONFIG, "input_hashes": dict(INPUTS)}
    aggregate = ops.compact_aggregate(rows[0], marker, manifest, 3, plan["mia"]["backtest_id"]) if count else None
    return {"count": count, "aggregate": aggregate, "full_journal_replay_verified": False,
            "accepted_metrics": None, "strategy_accepted": False}


def account_nav_observation(plan, envelope, calendar_raw):
    """Existing exact clock/census normalizer; a chart is never journal replay."""
    body, response = response_from_envelope(plan, envelope)
    if (body["endpoint"] != "backtests/chart/read" or body["request"]["name"] != "EXT26 Account NAV"
            or e.digest(calendar_raw) != CALENDAR): _fail()
    calendar = e.parse_json(calendar_raw)
    sessions = calendar.get("valuation_sessions")
    if (calendar.get("schema") != "tpr-extended-calendar-v1"
            or calendar.get("study_id") != e.STUDY_ID or calendar.get("study_freeze_sha256") != FREEZE
            or type(sessions) is not list or len(sessions) != 1449
            or any(type(day) is not str for day in sessions) or sessions != sorted(set(sessions))
            or sessions[0] != "2021-01-04" or sessions[-1] != "2026-10-09"): _fail()
    return ops._account_nav_chart(response, tuple(sessions))


@dataclass(frozen=True, slots=True)
class OrderCensus:
    """Unique native order IDs only, never fills, fees or independent sleeve P&L."""
    total: int | None = None
    ids: tuple[int, ...] = ()
    page_descriptors: tuple[tuple[int, str], ...] = ()
    capture_plan_sha256: str | None = None


def append_order_page(plan, census, envelope):
    if type(census) is not OrderCensus or type(census.ids) is not tuple or type(census.page_descriptors) is not tuple: _fail()
    pages = len(census.page_descriptors)
    if pages >= MAX_PAGES or len(set(census.ids)) != len(census.ids): _fail()
    if any(type(value) is not int or value < 0 for value in census.ids): _fail()
    plan_hash = e.digest(e.canonical(validate_plan(plan)))
    if pages == 0 and (census.total is not None or census.ids or census.capture_plan_sha256 is not None): _fail()
    if pages:
        if census.capture_plan_sha256 != plan_hash: _fail()
        if type(census.total) is not int or not 0 <= census.total <= MAX_PAGES * PAGE_SIZE: _fail()
        if len(census.ids) != min(pages * PAGE_SIZE, census.total) or len(census.ids) >= census.total: _fail()
        for size, identity in census.page_descriptors:
            if type(size) is not int or not 0 < size <= MAX_ENVELOPE: _fail()
            e._hash(identity)
    body, response = response_from_envelope(plan, envelope)
    if (body["endpoint"] != "backtests/orders/read"
            or _int(body["request"]["start"], MAX_PAGES * PAGE_SIZE) != pages * PAGE_SIZE): _fail()
    total = _int(response.get("length"), MAX_PAGES * PAGE_SIZE)
    if census.total is not None and total != census.total: _fail()
    rows = response.get("orders")
    if type(rows) is not list or len(rows) != min(PAGE_SIZE, total - pages * PAGE_SIZE): _fail()
    ids = list(census.ids)
    for row in rows:
        identity = _int(row.get("id"), 2**63 - 1) if type(row) is dict else None
        if identity is None or identity in ids: _fail()
        ids.append(identity)
    return OrderCensus(total, tuple(ids), (*census.page_descriptors, (len(envelope), hashlib.sha256(envelope).hexdigest())), plan_hash)


def initial_receipt(plan):
    validate_plan(plan)
    return {"schema": "tpr-ext26-first-refusal-capture-receipt-v1",
        "capture_operation_id": plan["capture_operation_id"], "project_id": PROJECT, "candidate_id": CANDIDATE,
        "mia_operation_id": OPERATION, "backtest_id": plan["mia"]["backtest_id"],
        "compile_id": plan["mia"]["compile_id"], "status": "FAILED_OR_UNCERTAIN",
        "retained_codex_attempts": 3, "mia_look_counted_externally": 31, "new_codex_attempts": 0, "new_looks": 0,
        "terminal": None, "summary_count": None, "index_count": None, "account_nav": None,
        "order_count": None, "order_pages": None, "fill_count": None, "fee_values": None,
        "accepted_metrics": None, "independent_sleeve_pnl": None, "full_window_verified": False,
        "native_accounting_verified": False, "private_journal_replay_verified": False,
        "compiled_source_proven": False, "strategy_accepted": False, "canonical_admission": False,
        "automatic_retry": False, "object_export": False, "trading": False}
