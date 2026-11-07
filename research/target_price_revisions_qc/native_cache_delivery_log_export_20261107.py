"""One fixed private full-log export for an existing OFF diagnostic job.

Imports perform no I/O. A safe bounded text capture is not proof of complete
server storage, transport framing, native origin, delivery counts or economics.
No generic endpoint allowlist is changed and no log URL is ever followed.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import time

from . import comparison_20261029_project_api as api
from . import extended_source_capture as scanner

projects, ops = api.projects, api.ops
MODULE = "research/target_price_revisions_qc/native_cache_delivery_log_export_20261107.py"
SCANNER_MODULE = "research/target_price_revisions_qc/extended_source_capture.py"
PROBE_MODULE = "research/target_price_revisions_qc/extended_source_probe.py"
AUDIT_MODULE = "research/target_price_revisions_development/source_audit.py"
REQUIRED_SOURCES = api.REQUIRED_SOURCES | frozenset((MODULE, SCANNER_MODULE, PROBE_MODULE,
    AUDIT_MODULE, "research/target_price_revisions_development/__init__.py"))
PINS = {
    "research/target_price_revisions_qc/comparison_20261028_api.py": "a2a160ac951a8a9f96b9531e5b51a5bf6b4e7b116b7873f77515780f059ebc5a",
    api.MODULE: "680f31f17447e240f919435ee1d56a9a48526f5197e37ac97332b4b70ee42b87",
    api.PROJECTS_MODULE: "6dc87f33105de9d80e7a267a6cc737bb4262f47e49c43b65247592927a5788d7",
    "research/target_price_revisions_qc/extended_operations.py": "824b3f0c180f1aeb7038d8f280c44507b5c39687fcccc87c539f242d9256d167",
    "research/target_price_revisions_qc/extended_evidence.py": "a816b1ddca5a8428f07e9029bc3a7f7db3c5e1a1f50521664992dabf556aa2d7",
    "research/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "research/target_price_revisions_qc/__init__.py": "3bc79e69bc0c775d8ef0ec154551436011cba407f37690c27ccbeb9000153c59",
    "research/target_price_revisions_development/__init__.py": "fb652de0e46bbb27fdf839d12f2d833f2fe2f5d54b19b668e9ff8cf7518c9189",
    AUDIT_MODULE: "9f2674a47d0d62bb09e2dd5ba1ce7f37eed3c68dce254e40e0d11d1218f46960",
    PROBE_MODULE: "45eba071576edb1379defa05764040c66fc06c1a4692b80a8d0e4b9410383be4",
    SCANNER_MODULE: "f96223c7e68be68955ef9163a7cdbf3815447484675313316dd193d3d85868cf"}
PRIVATE_ROOT = api.PRIVATE_ROOT.parent / "delivery-log-export-20261107"
PROJECT_ID = 38609822
BACKTEST_ID = "fb506cb363a915439998cf53ce419560"
NATIVE_SOURCE_HEAD = "e805d413bcbc00f1221275d8db28a1dc3cf8a89a"
CONFIG_SHA256 = "88517aa2505f74601ff8190de0ba6e294c3719f12ac542334248b453cb01fad4"
INVENTORY_SHA256 = "d309d29377b8d68c6841d2e56d0e8a77be90a0ab0bdf2abddb78cbec125b6826"
PROBE_OPERATION_ID = "TPR-CACHE-20261104-PLAIN-OFF-001"
ATTEMPT_ID = "TPR-CACHE-ATTEMPT-PLAIN-OFF-001"
LOOK_ID = "TPR-CACHE-LOOK-PLAIN-OFF-001"
OWNER_SHA256 = "1d0fad9452169f520b28be16f0e0f6ddd2c356dab28a7d127806e85f1f132daa"
REGISTRY_SHA256 = "154e8ff056eb776f070fd73922b724367e634b1b37d4052b70a464601d0c94f1"
CREATION_OWNER_SHA256 = "ea2dd7037a0f33ab78771a2f6deb3016da34b164ab04f5b2c69f30c4ae31157f"
ENDPOINT = "backtests/export/logs"
TAG = "TPR_PARENT_CACHE_PROBE_RESULT "
OBSERVATION_SCHEMA = "tpr-native-delivery-plain-cache-observations-v1"
SOURCE_EPOCH = "TPR-NATIVE-PARENT-DELIVERY-PLAIN-20261107-v1"
MAX_BYTES, MAX_TAG_BYTES, MAX_DEPTH, MAX_NODES = 262144, 16384, 16, 4096
MAX_TEXT_DEPTH, MAX_TEXT_CANDIDATES, MAX_TEXT_STRINGS = 64, 8192, 8192
MAX_TEXT_BYTES = 64*MAX_BYTES
SECONDS, PHASE_SECONDS, MAX_OUTPUT_BYTES = 20, 240, 1024*1024
FALSE_FLAGS = ("financial_acceptance", "delivery_counts_accepted", "economics_accepted",
    "native_origin_independently_attested", "import_origin_attested", "source_import_atomicity_attested",
    "full_log_completeness_attested", "backtesting_ready", "coverage_accepted", "market_trading_authorized")
PLAN_KEYS = frozenset(("schema", "operation_id", "git_head", "source_hashes", "project_bindings_json",
    "project_bindings_sha256", "registry_creation_owner_instruction_sha256", "latest_owner_instruction_sha256",
    "created_utc", "expires_utc", "project_id", "backtest_id", "native_source_head", "config_sha256",
    "source_inventory_sha256", "probe_operation_id", "attempt_id", "diagnostic_look_id", "request", "mode",
    "automatic_retry", "market_trading_authorized"))


class ExportRefusal(ValueError):
    pass


class ExportCancelled(KeyboardInterrupt):
    def __init__(self, report):
        self.report = api._clone(report)
        super().__init__("fixed log export cancelled; no automatic retry")


class ExportFatal(BaseException):
    def __init__(self, report):
        self.report = api._clone(report)
        super().__init__("fixed log export stopped; no automatic retry")


def _fail():
    raise ExportRefusal("fixed readonly log export refused") from None


def _closed(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        _fail()


def _safe_text(raw, credential):
    """Preserve and inspect every bounded decoding representation before retention.

    JSON string lexemes must be decoded BEFORE lossy regex normalization. Each
    independent transformation retains its parent and checks its own output;
    a later decoder cannot erase a literal credential's backslash/quote first.
    """
    if (type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES or raw.startswith(b"\xef\xbb\xbf")
            or type(credential) is not str or re.fullmatch(r"[!-~]{1,256}", credential) is None):
        _fail()
    try:
        text = raw.decode("utf-8", errors="strict")
        if credential.encode("ascii") in raw:
            _fail()
        # Keep the proven scanner as a precheck, not as a claim that its
        # composed normalization proves every JSON-serialized string safe.
        if scanner._secret_guard(raw, (credential,)) != text:
            _fail()
        queue, seen, total, strings = [], set(), 0, 0
        def keep(value, depth):
            nonlocal total
            if type(value) is not str or credential in value:
                _fail()
            size = len(value.encode("utf-8", errors="strict"))
            if size > MAX_BYTES:
                _fail()
            if value in seen:
                return
            if (depth > MAX_TEXT_DEPTH or len(queue) >= MAX_TEXT_CANDIDATES
                    or total+size > MAX_TEXT_BYTES):
                _fail()
            seen.add(value)
            queue.append((value, depth))
            total += size
        keep(text, 0)
        simple = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
        cursor = 0
        while cursor < len(queue):
            current, depth = queue[cursor]
            cursor += 1
            # Linear RFC-JSON string scanning, including ignored values/keys
            # and non-tag/control lines. Never start overlapping rescans at
            # every quote; decoded children are inspected recursively instead.
            offset = 0
            while offset < len(current):
                if current[offset] != '"':
                    offset += 1
                    continue
                strings += 1
                if strings > MAX_TEXT_STRINGS:
                    _fail()
                child, offset = json.decoder.scanstring(current, offset+1, True)
                keep(child, depth+1)
            # These are sibling representations, NOT a composed overwrite.
            # Compare after each stage before another stage may reinterpret
            # a credential's literal backslash-n/f/b/r/t, slash or quote.
            keep(re.sub(r'\\(["\\/bfnrt])', lambda match: simple[match.group(1)], current), depth+1)
            keep(re.sub(r"\\(?:u([0-9a-fA-F]{4})|x([0-9a-fA-F]{2}))",
                lambda match: chr(int(match.group(1) or match.group(2), 16)), current), depth+1)
            keep(scanner.unquote(current, errors="strict"), depth+1)
            keep(scanner.html.unescape(current), depth+1)
        return text
    except Exception:
        # Malformed/ambiguous quoted text and exhausted decoding budgets cannot
        # be certified credential-free. Refuse without hashing or retaining it.
        _fail()


def _report_object(payload):
    def pairs(items):
        value = {}
        for key, child in items:
            if key in value:
                _fail()
            value[key] = child
        return value
    def number(token):
        if len(token) > 1000:
            _fail()
        return int(token)
    try:
        value = json.loads(payload, object_pairs_hook=pairs, parse_int=number,
            parse_float=lambda _: _fail(), parse_constant=lambda _: _fail())
        nodes = 0
        def walk(item, depth=0):
            nonlocal nodes
            nodes += 1
            if nodes > MAX_NODES or depth > MAX_DEPTH:
                _fail()
            if type(item) is dict:
                for key, child in item.items():
                    walk(key, depth+1)
                    walk(child, depth+1)
            elif type(item) is list:
                for child in item:
                    walk(child, depth+1)
            elif type(item) is str:
                item.encode("utf-8", errors="strict")
            elif item is not None and type(item) not in (bool, int):
                _fail()
        walk(value)
        if type(value) is not dict:
            _fail()
        return value
    except Exception:
        _fail()


def _validate_text(raw, text):
    # JSON control envelopes, HTML/error documents and URL bodies are not logs.
    stripped = text.lstrip()
    if (not stripped or stripped[0] in '{["<'
            or re.match(r"(?i)(?:https?://|//)", stripped) or text.count(TAG) != 1):
        _fail()
    line = next(line for line in text.split("\n") if TAG in line)
    prefix, payload = line.split(TAG, 1)
    if (len(prefix) > 512 or any(ord(char) < 32 or ord(char) > 126 for char in prefix)
            or not 0 < len(payload.encode("utf-8")) <= MAX_TAG_BYTES):
        _fail()
    value = _report_object(payload)
    headers = {"schema": OBSERVATION_SCHEMA, "source_epoch": SOURCE_EPOCH,
        "operation_id": PROBE_OPERATION_ID, "root_head": NATIVE_SOURCE_HEAD, "actual_job_id": BACKTEST_ID}
    if any(type(value.get(key)) is not str or value[key] != expected for key, expected in headers.items()):
        _fail()
    for key, expected in (("project_id", PROJECT_ID), ("config_sha256", CONFIG_SHA256)):
        if key in value and (type(value[key]) is not type(expected) or value[key] != expected):
            _fail()
    for key in FALSE_FLAGS:
        if key in value and value[key] is not False:
            _fail()
    return {"schema": "tpr-delivery-log-export-validation-v1", "entire_wire_validated": True,
        "credential_echo_refused_before_retention": True, "original_wire_bytes": len(raw),
        "original_wire_sha256": api._sha(raw), "tagged_report_bytes": len(payload.encode("utf-8")),
        "tagged_report_sha256": api._sha(payload.encode("utf-8")), "tagged_json_syntax_complete": True,
        "tagged_report_binding_verified": True, "tagged_report_structure_independently_validated": False,
        "financial_metrics": None, **{key: False for key in FALSE_FLAGS}}


def validate_export(raw, *, credential):
    """Pure safe-text and complete tagged-JSON/header gate; no counts returned."""
    try:
        return _validate_text(raw, _safe_text(raw, credential))
    except Exception:
        _fail()


def _prepare(*, project_bindings_raw, expected_project_bindings_sha256, operation_id, git_head,
        source_hashes, latest_owner_instruction_sha256, created_utc, expires_utc, fixture=False):
    if (type(operation_id) is not str or re.fullmatch(r"TPR-CMP29-API-LOGEXPORT-[A-Z0-9-]{1,60}", operation_id) is None
            or type(git_head) is not str or re.fullmatch("[a-f0-9]{40}", git_head) is None
            or type(source_hashes) is not dict or set(source_hashes) != REQUIRED_SOURCES
            or latest_owner_instruction_sha256 != OWNER_SHA256):
        _fail()
    for name, digest in source_hashes.items():
        api._hash(digest)
        if name in PINS and digest != PINS[name]:
            _fail()
    created, expires = api._clock(created_utc), api._clock(expires_utc)
    if not timedelta(seconds=SECONDS) <= expires-created <= timedelta(seconds=PHASE_SECONDS):
        _fail()
    registry = projects.validate_bindings(project_bindings_raw, expected_sha256=expected_project_bindings_sha256)
    if (registry["adapter_source_sha256"] != source_hashes[api.PROJECTS_MODULE]
            or {key: row["project_id"] for key, row in registry["projects"].items()} != api.REGISTERED_PROJECTS
            or registry["owner_instruction_sha256"] != CREATION_OWNER_SHA256
            or not fixture and (len(project_bindings_raw) != 3573 or expected_project_bindings_sha256 != REGISTRY_SHA256)):
        _fail()
    payload = {"projectId": PROJECT_ID, "backtestId": BACKTEST_ID}
    return api._clone({"schema": "tpr-delivery-log-export-plan-v1", "operation_id": operation_id,
        "git_head": git_head, "source_hashes": source_hashes,
        "project_bindings_json": project_bindings_raw.decode("ascii"),
        "project_bindings_sha256": expected_project_bindings_sha256,
        "registry_creation_owner_instruction_sha256": registry["owner_instruction_sha256"],
        "latest_owner_instruction_sha256": latest_owner_instruction_sha256,
        "created_utc": created_utc, "expires_utc": expires_utc,
        "project_id": PROJECT_ID, "backtest_id": BACKTEST_ID, "native_source_head": NATIVE_SOURCE_HEAD,
        "config_sha256": CONFIG_SHA256, "source_inventory_sha256": INVENTORY_SHA256,
        "probe_operation_id": PROBE_OPERATION_ID, "attempt_id": ATTEMPT_ID, "diagnostic_look_id": LOOK_ID,
        "request": {"id": "logs", "endpoint": ENDPOINT, "payload": payload,
            "payload_sha256": api._sha(api._canonical(payload)), "max_response_bytes": MAX_BYTES, "seconds": SECONDS},
        "mode": "offline-fixture" if fixture else "production", "automatic_retry": False, "market_trading_authorized": False})


def prepare_plan(*, project_bindings_raw, expected_project_bindings_sha256, operation_id, git_head,
        source_hashes, latest_owner_instruction_sha256, created_utc, expires_utc):
    """Pure exact request; caller must freshly claim any supplied private input."""
    try:
        return _prepare(**locals())
    except Exception:
        _fail()


def _prepare_fixture(**kwargs):
    try:
        if "fixture" in kwargs:
            _fail()
        return _prepare(**kwargs, fixture=True)
    except Exception:
        _fail()


def _validated(plan):
    _closed(plan, PLAN_KEYS)
    kwargs = {key: plan[key] for key in ("operation_id", "git_head", "source_hashes",
        "latest_owner_instruction_sha256", "created_utc", "expires_utc")}
    if type(plan["project_bindings_json"]) is not str or plan["mode"] not in ("production", "offline-fixture"):
        _fail()
    expected = _prepare(**kwargs, project_bindings_raw=plan["project_bindings_json"].encode("ascii"),
        expected_project_bindings_sha256=plan["project_bindings_sha256"], fixture=plan["mode"] == "offline-fixture")
    if api._canonical(plan) != api._canonical(expected):
        _fail()
    return expected


def _guard(plan):
    api._guard(plan)
    if (Path(__file__) != api.LANE/MODULE or Path(scanner.__file__) != api.LANE/SCANNER_MODULE
            or Path(scanner.probe.__file__) != api.LANE/PROBE_MODULE
            or Path(scanner.helper.__file__) != api.LANE/AUDIT_MODULE
            or scanner.helper is not scanner.probe.helper
            or api.subprocess.run(["git", "check-ignore", "-q", str(PRIVATE_ROOT)], cwd=api.LANE,
                capture_output=True, timeout=10).returncode):
        _fail()


def _execute(plan, root, lock_root, *, transport, guard, clock, monotonic, fixture):
    plan = _validated(plan)
    if (not fixture and (root != PRIVATE_ROOT or lock_root != api.PRIVATE_ROOT
            or transport is not projects._native_request or guard is not _guard
            or clock is not api._utcnow or monotonic is not time.monotonic or plan["mode"] != "production")
            or fixture and (plan["mode"] != "offline-fixture" or root == PRIVATE_ROOT or root.is_relative_to(api.LANE)
                or lock_root != root or transport is projects._native_request)):
        _fail()
    frozen, started, previous_now, previous_tick = api._canonical(plan), monotonic(), None, None
    def check(seconds=0):
        nonlocal previous_now, previous_tick
        guard(plan)
        now, tick = clock(), monotonic()
        if (type(now) is not datetime or now.utcoffset() != timedelta(0)
                or not api._clock(plan["created_utc"]) <= now < api._clock(plan["expires_utc"])
                or type(tick) not in (int, float) or not 0 <= tick-started < PHASE_SECONDS
                or previous_now is not None and now < previous_now or previous_tick is not None and tick < previous_tick
                or api._clock(plan["expires_utc"])-now < timedelta(seconds=seconds)
                or PHASE_SECONDS-(tick-started) < seconds or api._canonical(plan) != frozen):
            _fail()
        previous_now, previous_tick = now, tick
    check()
    if root.resolve() != root or lock_root.resolve() != lock_root:
        _fail()
    for path in ((ops.PRIVATE_PARENT, api.PRIVATE_ROOT.parent, api.PRIVATE_ROOT, root) if not fixture else (root,)):
        path.mkdir(mode=0o700, exist_ok=True)
        ops._custody(path.lstat(), True)
    operation, lock, stop, written = plan["operation_id"], None, None, 0
    report = {"schema": "tpr-delivery-log-export-result-v1", "operation_id": operation,
        "git_head": plan["git_head"], "native_source_head": NATIVE_SOURCE_HEAD,
        "project_id": PROJECT_ID, "backtest_id": BACKTEST_ID, "plan_sha256": api._sha(frozen),
        "status": "failed_or_uncertain", "transport_calls_attempted": 0, "request_claim": None,
        "raw_response": None, "metadata": None, "http_status": None, "response_bytes": 0,
        "receipt_published": False, "lock_cleanup_complete": False, "operation_claim_published": None,
        "actual_new_backtests": 0, "new_source_mutations": 0, "financial_attempts_created": 0,
        "financial_outcome_looks": 0, "financial_metrics": None, "automatic_retry": False,
        **{key: False for key in FALSE_FLAGS}}
    def publish(name, raw):
        nonlocal written
        if type(raw) is not bytes or not 0 < len(raw) <= 2*MAX_BYTES or written+len(raw) > MAX_OUTPUT_BYTES:
            _fail()
        descriptor = api._publish(root, name, raw)
        written += len(raw)
        return descriptor
    try:
        publish(operation+".operation.spent.json", frozen)
        report["operation_claim_published"] = True
    except FileExistsError:
        _fail()
    except BaseException as error:
        # A failed/interrupted initial publication proves no owned claim.
        # Preserve any partial spent file, but do not acquire a lock, resolve
        # credentials or publish a receipt that could belong to another run.
        if isinstance(error, KeyboardInterrupt):
            report["status"] = "cancelled"
            raise ExportCancelled(report) from None
        if not isinstance(error, Exception):
            raise ExportFatal(report) from None
        _fail()
    lock_path = lock_root/"comparison-api.lock"
    try:
        if stop is not None:
            raise stop
        lock = os.open(lock_path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
        ops._custody(os.fstat(lock))
        wire = api._canonical({"operation_id": operation, "plan_sha256": report["plan_sha256"]})
        if os.write(lock, wire) != len(wire):
            _fail()
        os.fsync(lock)
        directory = os.open(lock_root, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try: os.fsync(directory)
        finally: os.close(directory)
        check()
        report["request_claim"] = publish(operation+".logs.request.spent.json", api._canonical({
            "plan_sha256": report["plan_sha256"], "request": plan["request"], "git_head": plan["git_head"],
            "source_hashes": plan["source_hashes"], "created_utc": plan["created_utc"], "expires_utc": plan["expires_utc"],
            "registry_creation_owner_instruction_sha256": plan["registry_creation_owner_instruction_sha256"],
            "latest_owner_instruction_sha256": plan["latest_owner_instruction_sha256"],
            "attempt_id": ATTEMPT_ID, "diagnostic_look_id": LOOK_ID, "native_source_head": NATIVE_SOURCE_HEAD,
            "source_inventory_sha256": INVENTORY_SHA256, "config_sha256": CONFIG_SHA256}))
        check(SECONDS)
        registry = projects.validate_bindings(plan["project_bindings_json"].encode("ascii"),
            expected_sha256=plan["project_bindings_sha256"])
        report["transport_calls_attempted"] = 1
        raw, status, credential, owner = transport(ENDPOINT, api._canonical(plan["request"]["payload"]),
            SECONDS, MAX_BYTES, registry["owner_id"])
        if (type(status) is not int or not 100 <= status <= 599
                or projects._integer(owner) != registry["owner_id"]):
            _fail()
        text = _safe_text(raw, credential)
        # Even control/error/malformed wires are retained only after the full
        # secret screen. No post-response guard may erase this safe history.
        report["http_status"], report["response_bytes"] = status, len(raw)
        report["raw_response"] = publish(operation+".logs.response.raw", raw)
        if status != 200:
            _fail()
        report["metadata"] = _validate_text(raw, text)
        check()
        report["status"] = "completed"
    except BaseException as error:
        stop = error
    finally:
        if lock is not None:
            try:
                current, owned = os.stat(lock_path, follow_symlinks=False), os.fstat(lock)
                if (current.st_dev, current.st_ino) != (owned.st_dev, owned.st_ino):
                    _fail()
                os.unlink(lock_path)
                os.close(lock)
                lock = None
                directory = os.open(lock_root, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                try: os.fsync(directory)
                finally: os.close(directory)
                report["lock_cleanup_complete"] = True
            except BaseException as error:
                stop = api._retain_stop(stop, error)
            finally:
                if lock is not None:
                    try: os.close(lock)
                    except BaseException as error: stop = api._retain_stop(stop, error)
        if stop is not None:
            report["status"] = "cancelled" if isinstance(stop, KeyboardInterrupt) else "failed_or_uncertain"
        report["receipt_published"] = True
        try:
            report["receipt"] = publish(operation+".result.json", api._canonical(report))
        except BaseException as error:
            report["receipt_published"] = False
            stop = api._retain_stop(stop, error)
            report["status"] = "cancelled" if isinstance(stop, KeyboardInterrupt) else "failed_or_uncertain"
    if isinstance(stop, KeyboardInterrupt):
        raise ExportCancelled(report) from None
    if stop is not None and not isinstance(stop, Exception):
        raise ExportFatal(report) from None
    return api._clone(report)


def execute_plan(plan):
    """Fixed one-shot genuine owner-bound TLS; no transport/endpoint override."""
    try:
        if type(plan) is not dict or plan.get("mode") != "production":
            _fail()
        return _execute(plan, PRIVATE_ROOT, api.PRIVATE_ROOT, transport=projects._native_request,
            guard=_guard, clock=api._utcnow, monotonic=time.monotonic, fixture=False)
    except (ExportCancelled, ExportFatal):
        raise
    except Exception:
        _fail()


def _execute_fixture(plan, root, *, transport, clock, guard=lambda _: None, monotonic=lambda: 0.0):
    try:
        return _execute(plan, root, root, transport=transport, guard=guard, clock=clock, monotonic=monotonic, fixture=True)
    except (ExportCancelled, ExportFatal):
        raise
    except Exception:
        _fail()
