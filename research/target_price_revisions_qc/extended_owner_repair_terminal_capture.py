"""Three newly observed own-OFF terminals, not a launch or acceptance driver.

Fresh custody and request claims precede credentials. Selective projections
validate every JSON token but retain no error/source/parameter/statistic values.
Current project files never establish the compiled source of a historical job.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
import time

from . import extended_owner_mia_terminal_successor as parser_source

capture, e, ops, files = parser_source.capture, parser_source.e, parser_source.ops, parser_source.files
LANE, PRIVATE_ROOT = capture.LANE, capture.PRIVATE_ROOT
MODULE = capture.PREFIX + "extended_owner_repair_terminal_capture.py"
SOURCE_PATHS = (*parser_source.SOURCE_PATHS, MODULE)
PARSER_SHA256 = "6e9d5cdc1ec89ec168b1523ca763f44cf2cca1f9379b3e69edd0200e379aed45"
PROJECT, CANDIDATE = 37650980, "TPR-CAP-TILT-EXT26-OFF-BASE-v1"
JOBS = (("3bcfc642896ea36e26b5cbca2988220c", 37830348, 31),
        ("1e3ffa97bfa73b25e6c46b54da8a5b5c", 37832726, 32),
        ("0407bbff60ee6ca57219743062090e5c", 37834838, 33))
MAX_RESPONSE = 4 * 1024 * 1024
# Each bounded transport may return one final byte solely to witness refusal.
MAX_TOTAL = 3 * (MAX_RESPONSE + 1)
MAX_SECONDS, REQUEST_SECONDS, MAX_RECEIPT = 120, 30, 64 * 1024
MAX_PARSE_SECONDS = 10
ENDPOINT = "backtests/read"
ARGS = ("operation_id", "git_head", "source_hashes", "owner_instruction_sha256",
        "created_utc", "expires_utc", "discovery_reference", "mode")
DATE_FIELDS = frozenset(("created", "startDate", "endDate", "startTime", "endTime", "finishTime"))
SELECTED = parser_source.SELECTED | DATE_FIELDS
STAT_KEYS = frozenset(("Total Orders", "Average Win", "Average Loss", "Compounding Annual Return",
    "Drawdown", "Expectancy", "Start Equity", "End Equity", "Net Profit", "Sharpe Ratio",
    "Sortino Ratio", "Probabilistic Sharpe Ratio", "Loss Rate", "Win Rate", "Profit-Loss Ratio",
    "Alpha", "Beta", "Annual Standard Deviation", "Annual Variance", "Information Ratio",
    "Tracking Error", "Treynor Ratio", "Total Fees", "Estimated Strategy Capacity",
    "Lowest Capacity Asset", "Portfolio Turnover", "Drawdown Recovery", "Equity", "Fees",
    "Holdings", "Net Profit", "PSR", "Return", "Unrealized", "Volume"))
PUBLIC_FILES = frozenset(("main.py", "audit_key_recovery.py", "extended_core.py", "extended_loader.py",
    "extended_construction.py", "extended_compressed_store.py", "extended_completion_successor.py",
    "extended_runtime_successor.py", "extended_refusal_witness_context_successor.py", "cap_tilt.py", "cap_observer.py"))


def _fail(): raise e.EvidenceError("bounded owner-repair terminal capture refused; no retry")
def _sha(raw): return hashlib.sha256(raw).hexdigest()
def _now(): return datetime.now(timezone.utc)


def _credential(value):
    if type(value) is not str or re.fullmatch(r"[!-~]{1,256}", value) is None: _fail()
    return value


class _Parser(parser_source.SelectiveTerminalParser):
    """Reuse the bounded tokenizer, never its old fixed-job collector."""
    def __init__(self, raw, credential):
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_RESPONSE: _fail()
        self.credential = _credential(credential)
        if credential.encode() in raw: raise parser_source.ParseRefusal("credential_echo_refused")
        try: self.text = raw.decode("utf-8")
        except UnicodeError: raise parser_source.ParseRefusal("utf8_refused") from None
        self.position, self.nodes, self.selected = 0, 0, {}
        self.backtest_object, self.root_object = False, False
        self.unselected_terminal_fields = 0
        self.composite_selected, self.unexpected_identity_containers = set(), set()
        self._path, self.statistics_keys, self.statistics_shapes = (), {}, {}

    def _primitive(self, path, value):
        if len(path) == 1 and path[0] in {"success", "projectId", "backtestId"}: self.selected[path[0]] = value
        elif len(path) == 2 and path[0] == "backtest" and path[1] in SELECTED:
            self.selected.setdefault("backtest", {})[path[1]] = value

    def _value(self, path=(), depth=0):
        previous, self._path = self._path, path
        try:
            self._space()
            char = self.text[self.position:self.position + 1]
            if len(path) == 2 and path[0] == "backtest" and path[1] in SELECTED and char in {"{", "["}:
                self.composite_selected.add(path)
            if path in {("backtest", "statistics"), ("backtest", "runtimeStatistics")}:
                self.statistics_shapes[path[-1]] = char == "{"
                self.statistics_keys[path[-1]] = []
            super()._value(path, depth)
        finally: self._path = previous

    def _string(self):
        value = super()._string()
        if (self._path in {("backtest", "statistics"), ("backtest", "runtimeStatistics")}
                and self.statistics_shapes.get(self._path[-1]) is True):
            keys = self.statistics_keys[self._path[-1]]
            if len(keys) >= 256: _fail()
            keys.append(value if value in STAT_KEYS else {"unrecognized_key_sha256": _sha(value.encode()), "bytes": len(value.encode())})
        return value


def project_terminal(raw, *, credential):
    """Safe PRIVATE projection before identity/status schema validation."""
    parser = _Parser(raw, credential)
    with ops.wall_deadline(MAX_PARSE_SECONDS): value = parser.parse()
    row = value.get("backtest", {})
    error_present = "error" in row
    error = row.pop("error", None)
    error_type = type(error) is str
    safe = {"selected": value, "selected_composite": bool(parser.composite_selected),
        "unexpected_identity_container": bool(parser.unexpected_identity_containers),
        "error_field_present": error_present,
        "error_is_null": error is None, "error_is_string": error_type,
        "error_bytes": len(error.encode()) if error_type else None,
        "error_sha256": _sha(error.encode()) if error_type else None,
        "error_enums": [name for name, needles in parser_source.ERROR_MARKERS.items()
            if error_type and any(needle in error for needle in needles)],
        "error_type_enums": [name for name in ("ValueError", "TypeError", "SyntaxError", "RuntimeError", "ImportError", "KeyError")
            if error_type and re.search(r"\b" + name + r"\b", error)],
        "public_file_frames": [], "statistics_key_names": parser.statistics_keys,
        "statistics_container_shapes": parser.statistics_shapes,
        "json_nodes_scanned": parser.nodes, "raw_error_source_parameters_statistic_values_retained": False}
    if error_type:
        frames = re.findall(r'(?:File\s+["\']?)([A-Za-z0-9_./\\-]+\.py)["\']?,?\s+(?:line\s+)?([0-9]{1,7})', error)
        safe["public_file_frames"] = [{"file": name.replace("\\", "/").rsplit("/", 1)[-1], "line": int(line)}
            for name, line in frames if name.replace("\\", "/").rsplit("/", 1)[-1] in PUBLIC_FILES][:32]
    return safe


def observation(projection, job, snapshot):
    selected = projection["selected"]
    if (selected.get("success") is not True or projection["selected_composite"]
            or projection["unexpected_identity_container"]): _fail()
    identity = ops._returned_identity(selected, PROJECT, job)
    row = selected.get("backtest")
    if (type(row) is not dict or row.get("backtestId") != job
            or capture._integer(row.get("snapshotId"), 2**63 - 1) != snapshot): _fail()
    status, progress = row.get("status"), row.get("progress")
    if (status not in parser_source.discovery.STATUS | {"RuntimeError"}
            or type(progress) is not e.JsonNumber or not 0 <= progress.fraction() <= 1
            or type(row.get("completed")) is not bool): _fail()
    compile_id = row.get("compileId")
    if compile_id is not None: e._id(compile_id)
    dates = {}
    for key in DATE_FIELDS & row.keys():
        value = row[key]
        if type(value) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})?", value) is None: _fail()
        try: datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError: _fail()
        dates[key] = value
    if row["completed"] and not projection["error_field_present"]: _fail()
    if row["completed"] and status in {"Completed", "Completed."}:
        if not projection["error_is_null"] or progress.fraction() != 1: _fail()
    if row["completed"] and status in {"RuntimeError", "Runtime Error", "Error"}:
        if not projection["error_is_string"] or not projection["error_bytes"]: _fail()
    return {"backtest_id": job, "snapshot_id": snapshot, "native_compile_id": compile_id,
        "native_status": status, "completed": row["completed"], "progress": progress,
        "native_dates": dates, "native_dates_timezone_assumption": None, "returned_identity_checks": identity,
        **{key: projection[key] for key in ("error_is_null", "error_is_string", "error_bytes", "error_sha256",
            "error_enums", "error_type_enums", "public_file_frames", "statistics_key_names", "statistics_container_shapes")},
        "compiled_source_proven": False, "full_window_accounting_verified": False, "accepted_metrics": None}


def _guard(head):
    parser_source._guard(head)
    if Path(__file__) != LANE / MODULE or Path(__file__).resolve() != LANE / MODULE: _fail()
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *SOURCE_PATHS], cwd=LANE, capture_output=True, timeout=5).returncode: _fail()


def _sources(head):
    result = parser_source._sources(head); _guard(head)
    committed = subprocess.run(["git", "show", head + ":" + MODULE], cwd=LANE, capture_output=True, timeout=5, check=True).stdout
    directory = files._directory((LANE / MODULE).parent, private=False)
    try:
        _guard(head); result[MODULE] = files._read(directory, Path(MODULE).name, expected_size=len(committed),
            expected_sha256=_sha(committed), remaining=capture.MAX_RESPONSE, private=False)
    finally: os.close(directory)
    if _sha(result[parser_source.MODULE]) != PARSER_SHA256: _fail()
    _guard(head); return result


def _plan(*, operation_id, git_head, source_hashes, owner_instruction_sha256, created_utc, expires_utc,
          discovery_reference, mode="production"):
    if (type(operation_id) is not str or re.fullmatch(r"TPR-EXT26-OWNER-REPAIR-TERMINAL-[A-Za-z0-9-]{1,60}", operation_id) is None
            or mode not in {"production", "offline-fixture"}): _fail()
    e._hash(git_head, 40); e._hash(owner_instruction_sha256)
    if type(source_hashes) is not dict or set(source_hashes) != set(SOURCE_PATHS): _fail()
    for digest in source_hashes.values(): e._hash(digest)
    if source_hashes[parser_source.MODULE] != PARSER_SHA256: _fail()
    if not timedelta(0) < capture._clock(expires_utc) - capture._clock(created_utc) <= timedelta(minutes=15): _fail()
    e._closed(discovery_reference, {"name", "bytes", "sha256"})
    reference = dict(discovery_reference)
    if (type(reference["name"]) is not str or re.fullmatch(r"TPR-EXT26-OWNER-MIA-DISCOVERY-SUCCESSOR-[A-Za-z0-9-]{1,50}\.result\.json", reference["name"]) is None
            or not capture._integer(reference["bytes"], MAX_RECEIPT)): _fail()
    reference["bytes"] = capture._integer(reference["bytes"], MAX_RECEIPT); e._hash(reference["sha256"])
    return {"schema": "tpr-ext26-owner-repair-terminal-plan-v1", "operation_id": operation_id,
        "git_head": git_head, "source_hashes": dict(source_hashes), "owner_instruction_sha256": owner_instruction_sha256,
        "created_utc": created_utc, "expires_utc": expires_utc, "discovery_reference": reference, "mode": mode,
        "project_id": PROJECT, "candidate_id": CANDIDATE, "jobs": [{"backtest_id": job, "snapshot_id": snap,
            "retrospective_look_ordinal": look} for job, snap, look in JOBS], "max_requests": 3,
        "endpoint": ENDPOINT, "max_response_bytes": MAX_RESPONSE, "max_received_bytes": MAX_TOTAL,
        "oversize_refusal_bytes_reserved": 3, "max_projection_parse_seconds": MAX_PARSE_SECONDS,
        "request_seconds": REQUEST_SECONDS, "max_seconds": MAX_SECONDS, "codex_off_attempts_consumed": 3,
        "observed_looks_before": 30, "observed_looks_after": 33, "new_looks": 0, "new_codex_attempts": 0,
        "owner_reported_mia_attribution_authenticated": False, "uncertain_prior_dispatch_attributed": False,
        "retrospective_registration_is_preregistration": False, "compiled_source_proven": False,
        "economics_accepted": False, "accepted_metrics": None, "strategy_accepted": False,
        "canonical_admission": False, "automatic_retry": False, "object_export": False, "trading": False}


def prepare_plan(**arguments):
    if Path.cwd() != LANE or Path.cwd().resolve() != LANE: _fail()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=LANE, capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    sources = _sources(head)
    plan = _plan(git_head=head, source_hashes={name: _sha(raw) for name, raw in sources.items()}, **arguments)
    raw = e.canonical(plan)
    return {"plan": plan, "plan_json": raw.decode(), "plan_sha256": _sha(raw)}


def _request(plan, payload):
    if payload not in [{"projectId": PROJECT, "backtestId": job} for job, _, _ in JOBS]: _fail()
    return e.canonical({"endpoint": ENDPOINT, "payload": payload, "plan_sha256": _sha(e.canonical(plan))})


def _access(plan):
    return e.canonical({"plan_sha256": _sha(e.canonical(plan)), "created_utc": plan["created_utc"],
        "expires_utc": plan["expires_utc"], "discovery_reference": plan["discovery_reference"],
        "jobs": plan["jobs"], "endpoint": ENDPOINT, "read_only": True, "max_requests": 3})


def _native_request(plan, payload, seconds, claim):
    rebuilt = _plan(**{key: plan[key] for key in ARGS}); raw_request = _request(rebuilt, payload)
    if (plan["mode"] != "production" or e.canonical(plan) != e.canonical(rebuilt)
            or type(seconds) not in (int, float) or not 0 < seconds <= REQUEST_SECONDS
            or claim != {"bytes": len(raw_request), "sha256": _sha(raw_request)}): _fail()
    _guard(plan["git_head"])
    if not capture._clock(plan["created_utc"]) <= _now() < capture._clock(plan["expires_utc"]): _fail()
    directory = files._directory(PRIVATE_ROOT, private=True)
    try:
        for name, raw in ((plan["operation_id"] + ".claim.spent.json", e.canonical(plan)),
                (plan["operation_id"] + ".access.json", _access(plan)),
                (plan["operation_id"] + ".request." + _sha(raw_request) + ".spent.json", raw_request)):
            files._read(directory, name, expected_size=len(raw), expected_sha256=_sha(raw), remaining=MAX_RECEIPT, private=True)
    finally: os.close(directory)
    _guard(plan["git_head"])
    if not capture._clock(plan["created_utc"]) <= _now() < capture._clock(plan["expires_utc"]): _fail()
    connection = None
    with ops.wall_deadline(seconds):
        user, token = ops.credential(); _credential(token); stamp = str(int(time.time()))
        authorization = base64.b64encode((user + ":" + _sha((token + ":" + stamp).encode())).encode()).decode()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT); context.keylog_filename = None
        context.check_hostname, context.verify_mode = True, ssl.CERT_REQUIRED; context.load_default_certs()
        try:
            connection = http.client.HTTPSConnection("www.quantconnect.com", timeout=seconds, context=context)
            connection.request("POST", "/api/v2/" + ENDPOINT, body=e.canonical(payload), headers={
                "Authorization": "Basic " + authorization, "Timestamp": stamp, "Content-Type": "application/json"})
            response = connection.getresponse()
            return response.read(MAX_RESPONSE + 1), response.status, token
        finally:
            if connection is not None: connection.close()


def _discovery(raw, reference):
    body = e.parse_json(raw)
    if (body.get("schema") != "tpr-ext26-owner-mia-discovery-successor-receipt-v1"
            or body.get("status") != "COMPLETED_METADATA" or capture._integer(body.get("project_id"), 2**31 - 1) != PROJECT
            or body.get("operation_id") + ".result.json" != reference["name"]): _fail()
    rows = body.get("jobs")
    if type(rows) is not list: _fail()
    for job, snapshot, _ in JOBS:
        matches = [row for row in rows if type(row) is dict and row.get("backtest_id") == job]
        if len(matches) != 1 or capture._integer(matches[0].get("snapshot_id_observed"), 2**63 - 1) != snapshot: _fail()


def _execute(plan, sources, root, *, guard, clock, monotonic, transport):
    rebuilt = _plan(**{key: plan[key] for key in ARGS})
    if e.canonical(plan) != e.canonical(rebuilt): _fail()
    plan = rebuilt
    if (plan["mode"] == "production" and (root != PRIVATE_ROOT or guard is not _guard or clock is not _now
            or monotonic is not time.monotonic or transport is not _native_request)
            or plan["mode"] == "offline-fixture" and (root == PRIVATE_ROOT or root.is_relative_to(LANE) or transport is _native_request)):
        _fail()
    started = monotonic()
    def check():
        guard(plan["git_head"]); now = clock(); elapsed = monotonic() - started
        if (type(now) is not datetime or now.utcoffset() != timedelta(0)
                or not capture._clock(plan["created_utc"]) <= now < capture._clock(plan["expires_utc"])
                or not 0 <= elapsed < MAX_SECONDS
                or {name: _sha(raw) for name, raw in sources.items()} != plan["source_hashes"]): _fail()
    check(); directory = files._directory(root, private=True); lock = None; operation = plan["operation_id"]
    report = {**plan, "schema": "tpr-ext26-owner-repair-terminal-receipt-v1",
        "status": "FAILED_OR_UNCERTAIN", "scope_spent": True, "plan_sha256": _sha(e.canonical(plan)),
        "request_attempts": 0, "received_bytes": 0, "discovery_read_attempts": 0, "observations": [],
        "requests": [], "cancelled": False, "full_window_accounting_verified": False,
        "current_project_source_proves_compiled_job_source": False}
    try:
        check(); capture._publish(directory, operation + ".claim.spent.json", e.canonical(plan))
        try:
            check(); lock = os.open("controller.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            info = os.fstat(lock)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600: _fail()
            check(); capture._publish(directory, operation + ".access.json", _access(plan))
            ref = plan["discovery_reference"]
            check(); capture._publish(directory, operation + ".discovery.read.spent.json", e.canonical(ref))
            report["discovery_read_attempts"] = 1
            check(); prior = files._read(directory, ref["name"], expected_size=ref["bytes"], expected_sha256=ref["sha256"], remaining=MAX_RECEIPT, private=True)
            _discovery(prior, ref); check()
            for job, snapshot, ordinal in JOBS:
                request_row = {"backtest_id": job, "retrospective_look_ordinal": ordinal,
                    "status": "FAILED_OR_UNCERTAIN", "wire": None, "projection": None,
                    "response_bytes_unknown": True, "failure": None}
                try:
                    check()
                    if report["request_attempts"] >= 3 or MAX_RESPONSE + 1 > MAX_TOTAL - report["received_bytes"]: _fail()
                    payload = {"projectId": PROJECT, "backtestId": job}; request_raw = _request(plan, payload)
                    claim = {"bytes": len(request_raw), "sha256": _sha(request_raw)}
                    check(); capture._publish(directory, operation + ".request." + claim["sha256"] + ".spent.json", request_raw)
                    report["request_attempts"] += 1; report["requests"].append(request_row)
                    check(); seconds = min(REQUEST_SECONDS, MAX_SECONDS - (monotonic() - started))
                    raw, http_status, token = transport(plan, payload, seconds, claim)
                    if type(raw) is not bytes: _fail()
                    report["received_bytes"] += len(raw); request_row["response_bytes_unknown"] = False
                    if not 0 < len(raw) <= MAX_RESPONSE + 1 or type(http_status) is not int or not 100 <= http_status <= 599: _fail()
                    descriptor = {"bytes": len(raw), "sha256": _sha(raw), "http_status": http_status,
                        "endpoint": ENDPOINT, "request": payload}
                    check(); request_row["wire"] = capture._publish(directory, operation + "." + job + ".wire-descriptor.json", e.canonical(descriptor))
                    if len(raw) > MAX_RESPONSE or report["received_bytes"] > MAX_TOTAL: _fail()
                    projection = project_terminal(raw, credential=token)
                    envelope = e.canonical({"schema": "tpr-ext26-owner-repair-terminal-envelope-v1", **descriptor,
                        "projection_sha256": _sha(e.canonical(projection)), "projection": projection})
                    check(); request_row["projection"] = capture._publish(directory, operation + "." + job + ".projection.json", envelope)
                    if http_status != 200: _fail()
                    result = observation(projection, job, snapshot); check()
                    report["observations"].append({**result, "retrospective_look_ordinal": ordinal}); request_row["status"] = "CAPTURED_TERMINAL_METADATA"
                except Exception: request_row["failure"] = "REFUSED_OR_UNCERTAIN"
            check()
            if len(report["observations"]) == 3: report["status"] = "COMPLETED_TERMINAL_METADATA"
        except KeyboardInterrupt: report["cancelled"] = True
        except Exception: pass
        report["ended_utc"] = clock().isoformat()
        raw_report = e.canonical(report)
        if len(raw_report) > MAX_RECEIPT:
            report.update(status="FAILED_OR_UNCERTAIN", observations=None, requests=None, public_receipt_overflow=True)
            raw_report = e.canonical(report)
        if len(raw_report) > MAX_RECEIPT: _fail()
        capture._publish(directory, operation + ".result.json", raw_report)
        return raw_report
    finally:
        if lock is not None:
            try:
                named, owned = os.stat("controller.lock", dir_fd=directory, follow_symlinks=False), os.fstat(lock)
                if (named.st_dev, named.st_ino) == (owned.st_dev, owned.st_ino): os.unlink("controller.lock", dir_fd=directory)
            except FileNotFoundError: pass
            finally: os.close(lock)
        os.close(directory)


def execute_plan(plan):
    if type(plan) is not dict or plan.get("mode") != "production": _fail()
    return _execute(plan, _sources(plan["git_head"]), PRIVATE_ROOT, guard=_guard, clock=_now,
        monotonic=time.monotonic, transport=_native_request)


def execute_fixture(plan, sources, root, *, clock, transport, guard=lambda _: None, monotonic=lambda: 0.0):
    if type(plan) is not dict or plan.get("mode") != "offline-fixture": _fail()
    return _execute(plan, sources, root, guard=guard, clock=clock, monotonic=monotonic, transport=transport)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-json", required=True); parser.add_argument("--plan-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        raw = args.plan_json.encode()
        if _sha(raw) != e._hash(args.plan_sha256): _fail()
        result = execute_plan(e.parse_json(raw)); print(result.decode(), end="")
        return 0 if e.parse_json(result)["status"] == "COMPLETED_TERMINAL_METADATA" else 1
    except (Exception, KeyboardInterrupt):
        print('{"status":"REFUSED_OR_UNCERTAIN","automatic_retry":false,"raw_text_returned":false}')
        return 1


if __name__ == "__main__": raise SystemExit(main())
