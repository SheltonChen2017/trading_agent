"""One-shot current-vintage ratings delta; not a three-role or PIT admission.

The parent, capture child, network-denied authentication child and bounded
output reader own this new protocol. No prior operational mode is invoked.
Keys and provider rows never cross the finite child/result console channels.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from types import MappingProxyType
from urllib.parse import quote, quote_plus, urlencode

ROOT = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_arv2_keychain_connection_check as transport
from research.analyst_revisions_v2_qc import accepted_risk_massive_ratings_delta as delta

helpers = transport.helpers
capture = helpers.capture
credentials = transport.credentials
canonical = helpers.canonical_json_bytes
BRANCH = "codex/strategy-analyst-revisions-v2"
PYTHON = Path("/Users/sheltonchen/.venvs/trading_agent-py313/bin/python")
SOURCE = ROOT / "scripts/capture_arv2_massive_ratings_delta.py"
CONTROL = ROOT / "artifacts/analyst_revisions_v2/massive_ratings_delta/R297-20261013-A"
SCHEMA = "arv2-massive-ratings-delta-caller-v1"
OUTPUT_SCHEMA = "arv2-massive-ratings-delta-output-v1"
FIRST, LAST = "2026-09-26", "2026-10-12"
ROLE = capture.MassiveSourceRole.ANALYST_RATINGS
ENDPOINT = "/benzinga/v1/ratings"
INITIAL_URL = "https://api.massive.com" + ENDPOINT + "?" + urlencode({
    "date.gte": FIRST, "date.lte": LAST, "limit": "1000", "sort": "date.asc"})
MAX_PAGES, MAX_ROWS = 16, 16000
MAX_RAW_PAGE, MAX_RAW_TOTAL, MAX_ROWS_TOTAL = 4 * 1024**2, 32 * 1024**2, 32 * 1024**2
MAX_MANIFEST, MAX_CHANNEL = 65536, 16384
DEADLINE_SECONDS, READER_SECONDS = 180, 30
SOURCE_PINS = MappingProxyType({**transport.SOURCE_PINS,
    "scripts/run_arv2_keychain_connection_check.py":
        "399d898d05f8696d4e5a1e6df25053d2449f96646fd870bf4dd2d75cd748af80",
    "research/analyst_revisions_v2/availability.py":
        "238738109bb7e2e3408376b143dfafc8fe5dc174b30a6a642276fda669d26ce4",
    "research/analyst_revisions_v2_qc/accepted_risk_massive_ratings_delta.py":
        "9c0ec2eede6daeabc03d150c1146d595026fe724028ead856edce9f29b872390"})
PROFILE = canonical({"schema": SCHEMA, "root": str(ROOT), "branch": BRANCH,
    "python": str(PYTHON), "control": str(CONTROL), "source_pins": dict(SOURCE_PINS),
    "source_profile_sha256": delta.SOURCE_PROFILE_SHA256,
    "purpose": "current_vintage_ratings_only_delta_after_verified_ratings_entitlement",
    "first_event_date": FIRST, "last_event_date": LAST, "endpoint": ENDPOINT,
    "page_limit": 1000, "max_pages": MAX_PAGES, "max_rows": MAX_ROWS,
    "raw_page_bytes": MAX_RAW_PAGE, "raw_total_bytes": MAX_RAW_TOTAL,
    "rows_total_bytes": MAX_ROWS_TOTAL, "manifest_bytes": MAX_MANIFEST,
    "parent_seconds": DEADLINE_SECONDS, "reader_seconds": READER_SECONDS,
    "keychain_seconds": 20, "connect_seconds": 5, "read_seconds": 15,
    "key_reads": 1, "retries": 0, "redirects": False, "tls_verify": True,
    "proxies": {}, "authentication_worker_network_denied": True,
    "point_in_time_proven": False, "three_role_complete": False,
    "backtest_ready": False, "paper_look_committed": False,
    "qc_calls": 0, "outcome_reads": 0, "separate_run_freeze_required": True})
PROFILE_SHA256 = hashlib.sha256(PROFILE).hexdigest()
_CAPTURE_TERMINALS = frozenset({"capture_completed", "control_refused", "credentials_unavailable",
    "request_refused", "send_intent_ambiguous", "transport_failure", "response_binding_refused",
    "invalid_status", "http_status", "body_refused", "credential_echo_refused", "schema_refused",
    "limits_refused", "publication_refused", "close_refused", "deadline_timeout", "cancelled"})
_TERMINALS = _CAPTURE_TERMINALS | {"accepted", "worker_channel_refused", "authentication_refused"}
_CLAIM_KEYS = {"schema", "profile_sha256", "expected_head", "caller_sha256", "parent_pid",
    "deadline_monotonic_ns", "claimed_at", "attempt_consumed"}
_BINDING_KEYS = {"manifest_sha256", "manifest_byte_count", "page_count", "row_count",
    "raw_byte_count", "rows_byte_count", "capture_started_at", "capture_completed_at"}
_RESULT_KEYS = {"terminal", "send_intent_count", "send_attempt_count", "status_code", "binding"}


class Refusal(ValueError):
    pass


def _require(condition):
    if not condition:
        raise Refusal("control_refused")


def _preflight(head, caller, deadline):
    _require("SSLKEYLOGFILE" not in os.environ)
    _require(sys.platform == "darwin" and os.name == "posix" and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT
        and Path(__file__).absolute() == SOURCE)
    _require(type(head) is str and re.fullmatch(r"[0-9a-f]{40}", head) is not None)
    helpers.require_sha256(caller, "caller")
    for args, expected in ((["rev-parse", "--show-toplevel"], str(ROOT)),
            (["branch", "--show-current"], BRANCH), (["rev-parse", "HEAD"], head),
            (["status", "--porcelain"], "")):
        value = subprocess.run(["git", *args], cwd=ROOT, stdin=subprocess.DEVNULL,
            capture_output=True, timeout=min(3, helpers._remaining(deadline)), check=False)
        _require(value.returncode == 0 and not value.stderr and value.stdout.decode().strip() == expected)
    for relative, expected in SOURCE_PINS.items():
        helpers.require_sha256(expected, "selected source pin")
        _require(helpers._source_digest(ROOT / relative) == expected)
    _require(helpers._source_digest(SOURCE) == caller)
    capture._require_dirfd_support()
    helpers._remaining(deadline)


def _check(directory, name, fd, identity):
    _require(helpers._identity(helpers._file_metadata(fd)) == identity)
    helpers._named_file(directory, name, fd)
    capture._require_reopened_artifact_identity(CONTROL, directory)


def _marker(directory, name, body):
    fd, _, _ = transport._write_held(directory, name, body)
    os.close(fd)


def _claim(head, caller, deadline):
    capture._require_operational_artifact_scope(CONTROL)
    _, parent = capture._open_directory_path(CONTROL.parent, create=True, name="ratings parent")
    directory = claim = None
    try:
        os.mkdir(CONTROL.name, 0o700, dir_fd=parent)
        os.fsync(parent)
        directory = capture._open_private_child_directory(parent, CONTROL.name, "ratings control")
        claim, _, identity = transport._write_held(directory, "claim.json", {
            "schema": SCHEMA, "profile_sha256": PROFILE_SHA256, "expected_head": head,
            "caller_sha256": caller, "parent_pid": os.getpid(), "claimed_at": helpers._utc_now(),
            "deadline_monotonic_ns": int(deadline * 1_000_000_000), "attempt_consumed": True})
        capture._require_pinned_child_identity(parent, CONTROL.name, directory, "ratings control")
        os.mkdir("runtime", 0o700, dir_fd=directory)
        os.fsync(directory)
        return directory, claim, identity
    except BaseException:
        for fd in (claim, directory):
            if fd is not None:
                os.close(fd)
        raise
    finally:
        os.close(parent)


def _require_claim(value, head, caller):
    helpers._exact(value, _CLAIM_KEYS)
    _require(value["schema"] == SCHEMA and value["profile_sha256"] == PROFILE_SHA256
        and value["expected_head"] == head and value["caller_sha256"] == caller
        and value["attempt_consumed"] is True and type(value["parent_pid"]) is int
        and value["parent_pid"] > 0 and type(value["deadline_monotonic_ns"]) is int
        and value["deadline_monotonic_ns"] > 0)
    helpers.parse_utc_timestamp(value["claimed_at"], "claim")


def _cursor(url):
    return capture._cursor_hash_and_validated_url(url, source_role=ROLE,
        requested_first_event_date=FIRST, requested_last_event_date=LAST, page_limit=1000)


def _prepare(url, key):
    _require("SSLKEYLOGFILE" not in os.environ)
    transport._check_transport_logging()
    if url != INITIAL_URL:
        _cursor(url)
    import requests
    request = requests.Request("GET", url, headers={"Authorization": "Bearer " + key}).prepare()
    _validate_request(request, url, key)
    return request


def _validate_request(request, url, key):
    _require(request.url == url and request.method == "GET" and request.body is None
        and dict(request.headers) == {"Authorization": "Bearer " + key}
        and request.hooks == {"response": []})


def _body(response, deadline):
    encoding = response.headers.get("Content-Encoding", "")
    media = response.headers.get("Content-Type", "")
    length = response.headers.get("Content-Length")
    _require(type(encoding) is str and encoding.strip().lower() in {"", "identity"})
    _require(type(media) is str and media.split(";", 1)[0].strip().lower() == "application/json")
    if length is not None:
        _require(type(length) is str and re.fullmatch(r"[0-9]{1,10}", length) is not None
            and 0 < int(length) <= MAX_RAW_PAGE)
    parts, total = [], 0
    for part in response.raw.stream(amt=16384, decode_content=False):
        helpers._remaining(deadline)
        _require(type(part) is bytes and len(part) <= 16384)
        total += len(part)
        _require(total <= MAX_RAW_PAGE)
        parts.append(part)
    _require(total > 0 and (length is None or total == int(length)))
    return b"".join(parts)


def _no_echo(raw, rows, key):
    # Frozen helper also recognizes JSON string escape representations. The
    # canonical row extraction defeats JSON Unicode-escaped credential echoes.
    capture._assert_response_does_not_echo_credential(raw, key)
    capture._assert_response_does_not_echo_credential(rows, key)
    decoded = capture.strict_json_loads(capture.decode_utf8(raw, "ratings response"), "ratings response")
    normalized = capture._canonical_json_value(decoded).encode("utf-8")
    for value in (key, quote(key, safe=""), quote_plus(key, safe="")):
        encoded = value.encode("ascii")
        _require(all(encoded not in payload for payload in (raw, rows, normalized)))


def _store(directory, name, payload, limit):
    _require(type(payload) is bytes and len(payload) <= limit)
    # This pure O_EXCL dirfd primitive fsyncs and retains all bytes on refusal.
    capture._exclusive_private_write_at(directory, name, payload, "ratings snapshot")
    os.fsync(directory)
    stored = capture._read_private_regular_at(directory, name, maximum_bytes=limit, name="ratings snapshot")
    _require(stored == payload)


def _blank_capture():
    return {"terminal": "control_refused", "send_intent_count": 0,
        "send_attempt_count": 0, "status_code": None, "binding": None}


def _capture_once(directory, claim, identity, deadline):
    result = _blank_capture()
    adapter = response = artifact = key = None
    try:
        _check(directory, "claim.json", claim, identity)
        os.mkdir("capture", 0o700, dir_fd=directory)
        os.fsync(directory)
        artifact = capture._open_private_child_directory(directory, "capture", "ratings capture")
        started = helpers._utc_now()
        adapter = transport._new_adapter()
        result["terminal"] = "credentials_unavailable"
        key = credentials.load_key("massive", timeout_seconds=min(20, helpers._remaining(deadline)))
        pages, seen, url, request_cursor = [], set(), INITIAL_URL, None
        for page_number in range(1, MAX_PAGES + 1):
            result["status_code"] = None
            result["terminal"] = "request_refused"
            request = _prepare(url, key)
            _check(directory, "claim.json", claim, identity)
            result["terminal"] = "send_intent_ambiguous"
            _marker(directory, f"send-{page_number:04d}-started.json", {"schema": SCHEMA,
                "profile_sha256": PROFILE_SHA256, "page_number": page_number,
                "endpoint": ENDPOINT, "request_cursor_sha256": request_cursor})
            result["send_intent_count"] += 1
            result["terminal"] = "control_refused"
            transport._check_transport_logging()
            remaining = helpers._remaining(deadline)
            result["terminal"] = "transport_failure"
            result["send_attempt_count"] += 1
            response = adapter.send(request, stream=True, verify=True, cert=None, proxies={},
                timeout=(min(5, remaining), min(15, remaining)))
            result["terminal"] = "response_binding_refused"
            _require(response.request is request and response.url == url)
            _validate_request(request, url, key)
            result["terminal"] = "invalid_status"
            status = response.status_code
            _require(type(status) is int and 100 <= status <= 599)
            result["status_code"] = status
            if status != 200:
                result["terminal"] = "http_status"
                break  # Never read a failed response body or another endpoint.
            result["terminal"] = "body_refused"
            raw = _body(response, deadline)
            received = helpers._utc_now()
            result["terminal"] = "schema_refused"
            rows, next_url = capture._response_rows_and_next_url(raw, page_limit=1000)
            result["terminal"] = "credential_echo_refused"
            _no_echo(raw, rows, key)
            result["terminal"] = "schema_refused"
            page = delta.build_page_record(page_number=page_number, raw_response=raw,
                provider_rows=rows, response_received_at=received, request_cursor_sha256=request_cursor)
            next_cursor = None
            if next_url is not None:
                next_cursor, next_url = _cursor(next_url)
                _require(next_cursor not in seen)
                seen.add(next_cursor)
            result["terminal"] = "limits_refused"
            _require(sum(p["raw_response_bytes"] for p in pages) + len(raw) <= MAX_RAW_TOTAL
                and sum(p["provider_rows_bytes"] for p in pages) + len(rows) <= MAX_ROWS_TOTAL
                and sum(p["row_count"] for p in pages) + page["row_count"] <= MAX_ROWS)
            result["terminal"] = "publication_refused"
            capture._require_pinned_child_identity(directory, "capture", artifact, "ratings capture")
            for name, payload, bound in zip(delta.page_names(page_number), (raw, rows),
                    (MAX_RAW_PAGE, MAX_ROWS_TOTAL), strict=True):
                _store(artifact, name, payload, bound)
            pages.append(page)
            raw = rows = None
            result["terminal"] = "close_refused"
            response.close()
            response = None
            if next_url is None:
                adapter.close()
                adapter = None
                completed = helpers._utc_now()
                manifest = delta.build_manifest(pages=pages, capture_started_at=started,
                    capture_completed_at=completed)
                payload = delta.canonical_bytes(manifest)
                result["terminal"] = "publication_refused"
                _store(artifact, "manifest.json", payload, MAX_MANIFEST)
                digest = hashlib.sha256(payload).hexdigest()
                _store(artifact, "manifest.sha256", (digest + "\n").encode(), 65)
                _check(directory, "claim.json", claim, identity)
                capture._require_pinned_child_identity(directory, "capture", artifact, "ratings capture")
                helpers._remaining(deadline)
                result["binding"] = {"manifest_sha256": digest, "manifest_byte_count": len(payload),
                    **{name: manifest[name] for name in _BINDING_KEYS - {"manifest_sha256", "manifest_byte_count"}}}
                result["terminal"] = "capture_completed"
                break
            url, request_cursor = next_url, next_cursor
            result["terminal"] = "limits_refused"
    except helpers.Deadline:
        result["terminal"] = "deadline_timeout"
    except (KeyboardInterrupt, SystemExit):
        result["terminal"] = "cancelled"
    except BaseException:
        pass  # No raw exception, request, response, key, or provider row output.
    finally:
        for item in (response, adapter):
            if item is not None:
                try:
                    item.close()
                except (KeyboardInterrupt, SystemExit):
                    result["terminal"] = "cancelled"
                except helpers.Deadline:
                    result["terminal"] = "deadline_timeout"
                except BaseException:
                    result["terminal"] = "close_refused"
        if artifact is not None:
            os.close(artifact)
        key = None
    if result["terminal"] != "capture_completed":
        result["binding"] = None
    return result


def _binding(value):
    helpers._exact(value, _BINDING_KEYS)
    helpers.require_sha256(value["manifest_sha256"], "manifest")
    for name, low, high in (("manifest_byte_count", 1, MAX_MANIFEST), ("page_count", 1, MAX_PAGES),
            ("row_count", 0, MAX_ROWS), ("raw_byte_count", 1, MAX_RAW_TOTAL), ("rows_byte_count", 0, MAX_ROWS_TOTAL)):
        _require(type(value[name]) is int and low <= value[name] <= high)
    start = helpers.parse_utc_timestamp(value["capture_started_at"], "start")
    end = helpers.parse_utc_timestamp(value["capture_completed_at"], "end")
    _require(start <= end and start.date().isoformat() > LAST
        and value["row_count"] <= 1000 * value["page_count"])
    return value


def _capture_result(value):
    helpers._exact(value, _RESULT_KEYS)
    _require(value["terminal"] in _CAPTURE_TERMINALS)
    for name in ("send_intent_count", "send_attempt_count"):
        _require(type(value[name]) is int and 0 <= value[name] <= MAX_PAGES)
    _require(value["send_attempt_count"] <= value["send_intent_count"]
        <= value["send_attempt_count"] + 1)
    code = value["status_code"]
    _require(code is None or type(code) is int and 100 <= code <= 599)
    if code is not None:
        _require(value["send_attempt_count"] > 0)
    if value["terminal"] == "http_status":
        _require(code is not None and code != 200)
    if value["terminal"] == "capture_completed":
        bound = _binding(value["binding"])
        _require(code == 200 and value["send_attempt_count"] == value["send_intent_count"] == bound["page_count"])
    else:
        _require(value["binding"] is None)
    return value


def _authenticate(binding):
    _binding(binding)
    accepted = delta.authenticate_capture(CONTROL / "capture",
        expected_manifest_sha256=binding["manifest_sha256"],
        expected_manifest_byte_count=binding["manifest_byte_count"])
    for name in ("manifest_sha256", "manifest_byte_count", "page_count", "row_count", "raw_byte_count", "rows_byte_count"):
        _require(getattr(accepted, name) == binding[name])
    _require(accepted.context.capture_started_at == binding["capture_started_at"]
        and accepted.context.capture_completed_at == binding["capture_completed_at"])
    return {"authenticated": True, "binding": binding}


def _context(directory, claim):
    capture._require_private_directory_metadata(os.fstat(directory), "ratings control")
    capture._require_reopened_artifact_identity(CONTROL, directory)
    helpers._named_file(directory, "claim.json", claim)
    value = helpers._read_channel(claim)
    _require_claim(value, value.get("expected_head"), value.get("caller_sha256"))
    _require(value["parent_pid"] == os.getppid())
    deadline = value["deadline_monotonic_ns"] / 1_000_000_000
    _require(helpers._remaining(deadline) <= DEADLINE_SECONDS)
    return value, deadline, helpers._identity(helpers._file_metadata(claim))


def _worker(stage, directory, claim, channel):
    try:
        _require(stage in {"capture", "authenticate"} and len({directory, claim, channel}) == 3)
        context, deadline, identity = _context(directory, claim)
        with helpers._alarm(deadline):
            _preflight(context["expected_head"], context["caller_sha256"], deadline)
            helpers._named_file(directory, f"{stage}-result.json", channel)
            _require(helpers._file_metadata(channel).st_size == 0)
            _marker(directory, f"{stage}-started.json", {"schema": SCHEMA,
                "stage": stage, "profile_sha256": PROFILE_SHA256})
            if stage == "capture":
                result = _capture_once(directory, claim, identity, deadline)
                _capture_result(result)
            else:
                requested = helpers._decode(sys.stdin.buffer.read(MAX_CHANNEL + 1))
                result = _authenticate(requested)
            _check(directory, "claim.json", claim, identity)
            helpers._write_channel(channel, result)
            helpers._named_file(directory, f"{stage}-result.json", channel)
            os.fsync(directory)
            helpers._remaining(deadline)
            return 0
    except BaseException:
        return 2


def _run_worker(stage, directory, claim, deadline, binding=None):
    _require(stage in {"capture", "authenticate"})
    filename = f"{stage}-result.json"
    descriptor = os.open(filename, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    process = None
    try:
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
        os.fsync(directory)
        args = [str(PYTHON), "-B", str(SOURCE), "_worker", stage, str(directory), str(claim), str(descriptor)]
        if stage == "authenticate":
            args = ["/usr/bin/sandbox-exec", "-p", "(version 1)(allow default)(deny network*)", *args]
        runtime = str(CONTROL / "runtime")
        # Deliberately do not inherit environment credentials, Python hooks,
        # proxies, tracing, plugins or shell initialization into either child.
        env = {"PATH": os.defpath, "TMPDIR": runtime, "XDG_CACHE_HOME": runtime,
            "PYTHONPYCACHEPREFIX": runtime, "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
        helpers._remaining(deadline, 2)
        process = subprocess.Popen(args, cwd=ROOT, env=env, stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            pass_fds=(directory, claim, descriptor), close_fds=True)
        process.communicate(None if binding is None else canonical(binding), timeout=helpers._remaining(deadline, 2))
        _require(process.returncode == 0)
        helpers._named_file(directory, filename, descriptor)
        return helpers._read_channel(descriptor)
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=1)
        os.close(descriptor)


def _report(head, caller):
    return {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256, "expected_head": head,
        "caller_sha256": caller, "terminal": "control_refused", "attempt_consumed": True,
        "parent_started_at": helpers._utc_now(), "parent_observed_terminal_at": None,
        "capture": None, "authentication": None, "provider_request_count": None,
        "point_in_time_proven": False, "three_role_complete": False, "backtest_ready": False,
        "paper_look_committed": False, "qc_calls": 0, "outcome_reads": 0}


def _validate(claim, report, head, caller, actual_exit):
    _require(type(actual_exit) is int and actual_exit in {0, 2})
    _require_claim(claim, head, caller)
    helpers._exact(report, set(_report(head, caller)))
    for name, expected in (("schema", SCHEMA), ("profile_sha256", PROFILE_SHA256),
            ("expected_head", head), ("caller_sha256", caller)):
        _require(report[name] == expected)
    _require(report["attempt_consumed"] is True and report["provider_request_count"] is None
        and report["terminal"] in _TERMINALS)
    for name in ("point_in_time_proven", "three_role_complete", "backtest_ready", "paper_look_committed"):
        _require(report[name] is False)
    for name in ("qc_calls", "outcome_reads"):
        _require(type(report[name]) is int and report[name] == 0)
    start = helpers.parse_utc_timestamp(report["parent_started_at"], "parent start")
    claimed = helpers.parse_utc_timestamp(claim["claimed_at"], "claim")
    end = helpers.parse_utc_timestamp(report["parent_observed_terminal_at"], "parent end")
    _require(start <= claimed <= end)
    produced = report["capture"]
    if produced is not None:
        _capture_result(produced)
        if produced["binding"] is not None:
            bound = produced["binding"]
            _require(claimed <= helpers.parse_utc_timestamp(bound["capture_started_at"], "start")
                <= helpers.parse_utc_timestamp(bound["capture_completed_at"], "end") <= end)
    if report["authentication"] is not None:
        auth = helpers._exact(report["authentication"], {"authenticated", "binding"})
        _binding(auth["binding"])
        _require(auth["authenticated"] is True and produced is not None
            and produced["terminal"] == "capture_completed" and auth["binding"] == produced["binding"])
    if report["terminal"] == "accepted":
        _require(actual_exit == 0 and report["authentication"] is not None)
    else:
        _require(actual_exit == 2)
    return {"schema": OUTPUT_SCHEMA, "output_authenticated": True,
        "capture_accepted": report["terminal"] == "accepted", "terminal": report["terminal"],
        "attempt_consumed": True, "capture": produced, "provider_request_count": None,
        "point_in_time_proven": False, "three_role_complete": False,
        "backtest_ready": False, "paper_look_committed": False, "qc_calls": 0, "outcome_reads": 0}


def _run(head, caller, deadline):
    directory = claim = report_fd = None
    consumption = False
    report = _report(head, caller)
    try:
        _preflight(head, caller, deadline)
        consumption = None
        directory, claim, identity = _claim(head, caller, deadline)
        consumption = True
        report["terminal"] = "worker_channel_refused"
        produced = _capture_result(_run_worker("capture", directory, claim, deadline))
        report["capture"], report["terminal"] = produced, produced["terminal"]
        if produced["terminal"] == "capture_completed":
            report["terminal"] = "authentication_refused"
            _require(helpers.parse_utc_timestamp(helpers._read_channel(claim)["claimed_at"], "claim")
                <= helpers.parse_utc_timestamp(produced["binding"]["capture_started_at"], "capture start")
                <= helpers.parse_utc_timestamp(produced["binding"]["capture_completed_at"], "capture end")
                <= helpers.parse_utc_timestamp(helpers._utc_now(), "observed"))
            auth = helpers._exact(_run_worker("authenticate", directory, claim, deadline, produced["binding"]),
                {"authenticated", "binding"})
            _binding(auth["binding"])
            _require(auth["authenticated"] is True and auth["binding"] == produced["binding"])
            report["authentication"], report["terminal"] = auth, "accepted"
    except (helpers.Deadline, subprocess.TimeoutExpired):
        report["terminal"] = "deadline_timeout"
    except (KeyboardInterrupt, SystemExit):
        report["terminal"] = "cancelled"
    except BaseException:
        pass
    try:
        helpers._remaining(deadline)
        if directory is None:
            print(canonical({"terminal": "claim_ambiguous" if consumption is None else "preclaim_refusal",
                "attempt_consumed": consumption, "provider_request_count": None}).decode())
            return 2
        _check(directory, "claim.json", claim, identity)
        report["parent_observed_terminal_at"] = helpers._utc_now()
        code = 0 if report["terminal"] == "accepted" else 2
        _validate(helpers._read_channel(claim), report, head, caller, code)
        report_fd, payload, report_identity = transport._write_held(directory, "report.json", report)
        _check(directory, "report.json", report_fd, report_identity)
        _check(directory, "claim.json", claim, identity)
        helpers._remaining(deadline)
        print(canonical({"terminal": report["terminal"], "profile_sha256": PROFILE_SHA256,
            "report_sha256": hashlib.sha256(payload).hexdigest(), "report_bytes": len(payload),
            "provider_request_count": None}).decode())
        return code
    except BaseException:
        print('{"terminal":"publication_ambiguous","provider_request_count":null}')
        return 2
    finally:
        for fd in (report_fd, claim, directory):
            if fd is not None:
                os.close(fd)


def run(head, caller):
    deadline = time.monotonic() + DEADLINE_SECONDS
    try:
        with helpers._alarm(deadline):
            return _run(head, caller, deadline)
    except BaseException:
        print('{"terminal":"parent_ambiguous","provider_request_count":null}')
        return 2


def read_output(head, caller, digest, size, actual_exit):
    deadline = time.monotonic() + READER_SECONDS
    with helpers._alarm(deadline):
        _require(type(size) is int and 0 < size <= MAX_CHANNEL)
        helpers.require_sha256(digest, "report")
        _preflight(head, caller, deadline)
        with ExitStack() as stack:
            _, directory = capture._open_directory_path(CONTROL, create=False, name="ratings output")
            stack.callback(os.close, directory)
            values, pins, held = {}, {}, []
            for name in ("report.json", "claim.json"):
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                stack.callback(os.close, fd)
                identity = helpers._identity(helpers._file_metadata(fd))
                _check(directory, name, fd, identity)
                payload = os.pread(fd, MAX_CHANNEL + 1, 0)
                _require(0 < len(payload) == identity[6] <= MAX_CHANNEL)
                pins[name] = (hashlib.sha256(payload).hexdigest(), len(payload))
                if name == "report.json":
                    _require(pins[name] == (digest, size))
                values[name] = helpers._decode(payload)
                held.append((name, fd, identity))
            summary = _validate(values["claim.json"], values["report.json"], head, caller, actual_exit)
            for name, fd, identity in held:
                _check(directory, name, fd, identity)
            helpers._remaining(deadline)
            summary.update(report_sha256=digest, report_bytes=size,
                claim_sha256=pins["claim.json"][0], claim_bytes=pins["claim.json"][1])
            return summary


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "_worker":
        try:
            _require(len(args) == 5)
            return _worker(args[1], *(int(x) for x in args[2:]))
        except BaseException:
            return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--caller-sha256", required=True)
    parser.add_argument("--read-output", action="store_true")
    parser.add_argument("--report-sha256")
    parser.add_argument("--report-bytes", type=int)
    parser.add_argument("--actual-parent-exit", type=int)
    parsed = parser.parse_args(args)
    if parsed.read_output:
        try:
            result = read_output(parsed.expected_head, parsed.caller_sha256, parsed.report_sha256,
                parsed.report_bytes, parsed.actual_parent_exit)
            print(canonical(result).decode())
            return 0 if result["capture_accepted"] else 2
        except BaseException:
            print('{"terminal":"output_refused","output_authenticated":false}')
            return 2
    if any(x is not None for x in (parsed.report_sha256, parsed.report_bytes, parsed.actual_parent_exit)):
        return 2
    return run(parsed.expected_head, parsed.caller_sha256)


if __name__ == "__main__":
    raise SystemExit(main())
