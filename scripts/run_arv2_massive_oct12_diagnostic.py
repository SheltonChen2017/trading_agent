"""Prospective R293 first-vintage Oct12 capture diagnostic, not a strategy run.

UNREVIEWED/UNINVOKED candidate: independent review and a separately committed
one-shot run decision must precede operational use. No CLI switch grants that
authority. This new date acquisition cannot recover or renew spent R287.

The parent claims once before credentials/contact, runs one capture worker,
then authenticates its result in a separate native-network-denied worker.
Producer return is not success. Only bounded, validated metadata crosses the
worker boundary; raw returns, exceptions, credentials and provider rows never
do. An ambiguous terminal event spends the claim. No orchestration cleanup or
retry exists; the frozen adapter retains its own unpublished staging cleanup.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time
from types import MappingProxyType

ROOT = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.analyst_revisions_v2 import forward_data_quality as quality
from research.analyst_revisions_v2.canonical import (
    canonical_json_bytes, parse_utc_timestamp, require_canonical_json_bytes,
    require_identifier, require_sha256,
)
from scripts import capture_arv2_massive as capture
from scripts.arv2_massive_capture_diagnostic import (
    CaptureObservation, observe_capture_once,
)

BRANCH = "codex/strategy-analyst-revisions-v2"
PYTHON = Path("/Users/sheltonchen/.venvs/trading_agent-py313/bin/python")
SOURCE = ROOT / "scripts/run_arv2_massive_oct12_diagnostic.py"
CONTROL = ROOT / "artifacts/analyst_revisions_v2/massive_diagnostic/R293-20261013-A"
CAPTURE_ROOT = ROOT / "artifacts/analyst_revisions_v2/massive_capture"
EVENT_DATE = "2026-10-12"
SCHEMA = "arv2-massive-oct12-diagnostic-v1"
MAX_CHANNEL = 16 * 1024
DEADLINE_SECONDS = 150
SOURCE_PINS = MappingProxyType({
    "scripts/capture_arv2_massive.py": "e67cabf821a3df804d157c790b6df1c7cd1a13a7c50d717a48b55b3d32e5e906",
    "scripts/run_arv2_forward_data_quality.py": "b82475a9ddbad73b4d38c7469f881f50b23bc0bbf7f57cfbd59dbcc927372557",
    "research/analyst_revisions_v2/forward_data_quality.py": "2391ab4d465fead135c9836231294c0de5fce0eae959c15fc67827d82191f557",
    "research/analyst_revisions_v2/accepted_risk_input_pair.py": "4aa82377661420e4ee017b3cdefd54f038af75eca2b3cf086f57d11a6c55a037",
    "research/analyst_revisions_v2/canonical.py": "c1d1d1aab633b16868fccc371de7c4cf4f3a692943e04a8d785109110e17ae6e",
    "scripts/arv2_massive_capture_failure.py": "737c3a0cd5b33e42eb906a84e817a74037a6c4e55c4d534d390a19947624edc6",
    "scripts/arv2_massive_capture_diagnostic.py": "8c571988252d5f1ee9364f98d6a163d8da22e88023730f829d11eb7cb1a7ba1a",
})
PROFILE = canonical_json_bytes({
    "schema": SCHEMA, "purpose": "new_oct12_first_vintage_and_finite_failure_evidence",
    "root": str(ROOT), "branch": BRANCH, "host": "darwin-posix-python3.13",
    "python": str(PYTHON), "control": str(CONTROL), "capture_root": str(CAPTURE_ROOT),
    "first_event_date": EVENT_DATE, "last_event_date": EVENT_DATE,
    "roles": [r.value for r in quality.ROLE_ORDER], "page_limit": 1000,
    "build_input_pair": False, "parent_deadline_seconds": DEADLINE_SECONDS,
    "channel_limit_bytes": MAX_CHANNEL, "source_pins": dict(SOURCE_PINS),
    "provider_request_count": None, "point_in_time_proven": False,
    "paper_look_committed": False, "qc_calls": 0, "outcome_reads": 0,
    "independent_review_required": True, "separate_run_freeze_required": True,
})
PROFILE_SHA256 = hashlib.sha256(PROFILE).hexdigest()
_BINDING_KEYS = frozenset({
    "artifact_path", "manifest_sha256", "capture_id", "capture_sha256",
    "capture_started_at", "capture_completed_at", "total_page_count",
    "total_row_count", "role_row_counts", "capture_transport",
})
_TERMINALS = frozenset({
    "accepted", "producer_raised", "invalid_producer_return", "authentication_refused",
    "worker_nonzero", "worker_channel_refused", "worker_timeout", "control_refused",
    "claim_ambiguous",
})


class Refusal(ValueError):
    """Only fixed code labels are allowed at this boundary."""


class Deadline(BaseException):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _remaining(deadline: float, reserve: float = 0.0) -> float:
    left = deadline - time.monotonic() - reserve
    if left <= 0:
        raise Deadline()
    return left


@contextmanager
def _alarm(deadline: float):
    def expired(_signum, _frame):
        raise Deadline()
    old = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, _remaining(deadline))
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def _decode(payload: bytes) -> dict:
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_CHANNEL:
        raise Refusal("worker_channel_refused")
    value = require_canonical_json_bytes(payload, "diagnostic channel")
    if type(value) is not dict:
        raise Refusal("worker_channel_refused")
    return value


def _exact(value: object, keys: set | frozenset) -> dict:
    if type(value) is not dict or value.keys() != keys:
        raise Refusal("worker_channel_refused")
    return value


def _file_metadata(fd: int) -> os.stat_result:
    item = os.fstat(fd)
    if (not stat.S_ISREG(item.st_mode) or stat.S_IMODE(item.st_mode) != 0o600
            or item.st_nlink != 1 or item.st_uid != os.getuid()
            or not 0 <= item.st_size <= MAX_CHANNEL):
        raise Refusal("control_refused")
    return item


def _identity(item: os.stat_result) -> tuple:
    return (item.st_dev, item.st_ino, item.st_mode, item.st_uid, item.st_gid,
            item.st_nlink, item.st_size, item.st_mtime_ns, item.st_ctime_ns,
            getattr(item, "st_flags", None))


def _read_channel(fd: int) -> dict:
    before = _file_metadata(fd)
    payload = os.pread(fd, MAX_CHANNEL + 1, 0)
    if _identity(before) != _identity(_file_metadata(fd)):
        raise Refusal("worker_channel_refused")
    return _decode(payload)


def _named_file(directory: int, name: str, fd: int) -> None:
    if _identity(os.stat(name, dir_fd=directory, follow_symlinks=False)) != _identity(_file_metadata(fd)):
        raise Refusal("control_refused")


def _write_channel(fd: int, value: dict) -> None:
    if _file_metadata(fd).st_size != 0:
        raise Refusal("worker_channel_refused")
    payload = canonical_json_bytes(value)
    if len(payload) > MAX_CHANNEL:
        raise Refusal("worker_channel_refused")
    capture._write_all(fd, payload, "diagnostic channel")
    os.fsync(fd)
    if _file_metadata(fd).st_size != len(payload):
        raise Refusal("worker_channel_refused")


def _source_digest(path: Path) -> str:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > 2 * 1024 * 1024:
            raise Refusal("control_refused")
        data = os.read(descriptor, 2 * 1024 * 1024 + 1)
        after = os.fstat(descriptor)
        if (_identity(before) != _identity(after) or len(data) != before.st_size
                or _identity(after) != _identity(os.stat(path, follow_symlinks=False))):
            raise Refusal("control_refused")
        return hashlib.sha256(data).hexdigest()
    finally:
        os.close(descriptor)


def _preflight(expected_head: str, caller_sha256: str, deadline: float) -> None:
    if (sys.platform != "darwin" or os.name != "posix" or sys.version_info[:2] != (3, 13)
            or Path(sys.executable) != PYTHON or Path.cwd() != ROOT
            or Path(__file__).absolute() != SOURCE or ROOT.resolve() != ROOT):
        raise Refusal("control_refused")
    if type(expected_head) is not str or re.fullmatch(r"[0-9a-f]{40}", expected_head) is None:
        raise Refusal("control_refused")
    require_sha256(caller_sha256, "frozen caller pin")
    checks = ((["rev-parse", "--show-toplevel"], str(ROOT)),
              (["branch", "--show-current"], BRANCH),
              (["rev-parse", "HEAD"], expected_head),
              (["status", "--porcelain"], ""))
    for args, expected in checks:
        result = subprocess.run(["git", *args], cwd=ROOT, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=min(3, _remaining(deadline)), check=False)
        if result.returncode != 0 or result.stdout.decode("utf-8").strip() != expected or result.stderr:
            raise Refusal("control_refused")
    for relative, digest in SOURCE_PINS.items():
        if _source_digest(ROOT / relative) != digest:
            raise Refusal("control_refused")
    if _source_digest(SOURCE) != caller_sha256:
        raise Refusal("control_refused")
    capture._require_dirfd_support()


def _binding(value: object) -> dict:
    # Never inspect or render an arbitrary opaque return.
    if type(value) is not capture.SpooledMassiveCapture:
        raise Refusal("invalid_producer_return")
    path = value.artifact_path
    if type(path) is not type(Path()):
        raise Refusal("invalid_producer_return")
    fields = {key: getattr(value, key) for key in _BINDING_KEYS if key not in {"artifact_path", "role_row_counts"}}
    roles = value.role_row_counts
    if type(roles) is not tuple or len(roles) != 3:
        raise Refusal("invalid_producer_return")
    role_counts = []
    for pair, expected in zip(roles, quality.ROLE_ORDER, strict=True):
        if (type(pair) is not tuple or len(pair) != 2 or type(pair[0]) is not type(expected)
                or pair[0] is not expected or type(pair[1]) is not int):
            raise Refusal("invalid_producer_return")
        role_counts.append([expected.value, pair[1]])
    fields.update(artifact_path=str(path), role_row_counts=role_counts)
    return _require_binding(fields)


def _require_binding(fields: dict) -> dict:
    _exact(fields, _BINDING_KEYS)
    for name in ("manifest_sha256", "capture_sha256"):
        require_sha256(fields[name], name)
    require_identifier(fields["capture_id"], "capture ID")
    if fields["capture_id"] != f"arv2-capture-{fields['capture_sha256'][:24]}":
        raise Refusal("invalid_producer_return")
    for name in ("artifact_path", "capture_started_at", "capture_completed_at", "capture_transport"):
        if type(fields[name]) is not str or len(fields[name]) > 512:
            raise Refusal("invalid_producer_return")
    started = parse_utc_timestamp(fields["capture_started_at"], "capture start")
    ended = parse_utc_timestamp(fields["capture_completed_at"], "capture end")
    if (started > ended or started.date().isoformat() <= EVENT_DATE
            or fields["artifact_path"] != str(CAPTURE_ROOT / capture._artifact_id_from_timestamp(fields["capture_started_at"]))
            or fields["capture_transport"] != capture.PRODUCTION_TRANSPORT):
        raise Refusal("invalid_producer_return")
    if (type(fields["total_page_count"]) is not int or not 3 <= fields["total_page_count"] <= capture.MAX_ARTIFACT_PAGES
            or type(fields["total_row_count"]) is not int or not 0 <= fields["total_row_count"] <= quality.MAX_OBSERVATIONS
            or type(fields["role_row_counts"]) is not list or len(fields["role_row_counts"]) != 3):
        raise Refusal("invalid_producer_return")
    for item, expected in zip(fields["role_row_counts"], quality.ROLE_ORDER, strict=True):
        if (type(item) is not list or len(item) != 2 or type(item[0]) is not str
                or item[0] != expected.value or type(item[1]) is not int
                or not 0 <= item[1] <= quality.MAX_OBSERVATIONS):
            raise Refusal("invalid_producer_return")
    if sum(item[1] for item in fields["role_row_counts"]) != fields["total_row_count"]:
        raise Refusal("invalid_producer_return")
    return fields


def _capture_once() -> dict:
    observed, opaque = observe_capture_once(lambda: capture.capture_massive_history(
        requested_first_event_date=EVENT_DATE, requested_last_event_date=EVENT_DATE,
        artifact_root=CAPTURE_ROOT, page_limit=1000, build_input_pair=False,
    ))
    result = {"observation": asdict(observed), "binding": None, "terminal": "producer_raised"}
    if observed.producer_return_received:
        try:
            result["binding"] = _binding(opaque)
            result["terminal"] = "producer_returned"
        except BaseException:
            result["terminal"] = "invalid_producer_return"
    return result


def _require_capture_result(value: dict) -> dict:
    _exact(value, {"observation", "binding", "terminal"})
    observed = _exact(value["observation"], {
        "capture_invoked", "producer_return_received", "terminal_state", "failure_code", "provider_request_count",
    })
    if observed["provider_request_count"] is not None:
        raise Refusal("worker_channel_refused")
    observation = CaptureObservation(**{k: v for k, v in observed.items() if k != "provider_request_count"})
    terminal = value["terminal"]
    if type(terminal) is not str or not observation.capture_invoked:
        raise Refusal("worker_channel_refused")
    if terminal == "producer_raised":
        if observation.producer_return_received or value["binding"] is not None:
            raise Refusal("worker_channel_refused")
    elif terminal == "invalid_producer_return":
        if not observation.producer_return_received or value["binding"] is not None:
            raise Refusal("worker_channel_refused")
    elif terminal == "producer_returned":
        if not observation.producer_return_received:
            raise Refusal("worker_channel_refused")
        _require_binding(value["binding"])
    else:
        raise Refusal("worker_channel_refused")
    return value


def _authenticate(binding: dict) -> dict:
    _require_binding(binding)
    visited = []

    def visit_pages(visit):
        source = capture._visit_authenticated_massive_capture_pages_for_bridge(
            Path(binding["artifact_path"]), expected_transport=capture.PRODUCTION_TRANSPORT,
            visit_page=visit,
        )
        # ALL producer fields must match the independently authenticated bridge.
        if _binding(source) != binding:
            raise Refusal("authentication_refused")
        visited.append(True)
        return source

    # The external manifest comparison follows authenticated page traversal;
    # this is final fail-closed acceptance, NOT an external-pin-before-read claim.
    payload, digest = quality.build_receipt_from_authenticated_pages(
        visit_pages, binding["manifest_sha256"], first_event_date=EVENT_DATE,
        last_event_date=EVENT_DATE, expected_transport=capture.PRODUCTION_TRANSPORT,
    )
    receipt = quality._require_receipt(payload, digest)
    if (visited != [True] or receipt["first_event_date"] != EVENT_DATE
            or receipt["last_event_date"] != EVENT_DATE
            or receipt["point_in_time_proven"] is not False
            or receipt["paper_look_committed"] is not False
            or type(receipt["qc_calls"]) is not int or receipt["qc_calls"] != 0
            or type(receipt["outcome_reads"]) is not int or receipt["outcome_reads"] != 0):
        raise Refusal("authentication_refused")
    for key, field in (("capture_id", "capture_id"), ("capture_sha256", "capture_sha256"),
                       ("capture_manifest_sha256", "manifest_sha256"),
                       ("capture_started_at", "capture_started_at"),
                       ("capture_completed_at", "capture_completed_at"),
                       ("capture_transport", "capture_transport"), ("source_row_count", "total_row_count")):
        if receipt[key] != binding[field]:
            raise Refusal("authentication_refused")
    return {"binding": binding, "authenticated": True, "receipt_sha256": digest,
            "receipt_byte_count": len(payload), "receipt_published": False,
            "point_in_time_proven": False, "paper_look_committed": False,
            "qc_calls": 0, "outcome_reads": 0}


def _require_authentication(value: dict, binding: dict) -> dict:
    _exact(value, {"binding", "authenticated", "receipt_sha256", "receipt_byte_count",
                   "receipt_published", "point_in_time_proven", "paper_look_committed", "qc_calls", "outcome_reads"})
    if (_require_binding(value["binding"]) != _require_binding(binding) or value["authenticated"] is not True
            or any(value[key] is not False for key in ("receipt_published", "point_in_time_proven", "paper_look_committed"))
            or any(type(value[key]) is not int or value[key] != 0 for key in ("qc_calls", "outcome_reads"))
            or type(value["receipt_byte_count"]) is not int
            or not 0 < value["receipt_byte_count"] <= quality.MAX_RECEIPT_BYTES):
        raise Refusal("worker_channel_refused")
    require_sha256(value["receipt_sha256"], "receipt hash")
    return value


def _claim(expected_head: str, caller_sha256: str, deadline: float) -> tuple[int, int]:
    capture._require_operational_artifact_scope(CONTROL)
    _, parent = capture._open_directory_path(CONTROL.parent, create=True, name="diagnostic parent")
    directory = claim = None
    try:
        os.mkdir(CONTROL.name, 0o700, dir_fd=parent)  # Existing or ambiguous leaf is spent.
        os.fsync(parent)
        directory = capture._open_private_child_directory(parent, CONTROL.name, "diagnostic claim")
        body = {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256,
                "expected_head": expected_head, "caller_sha256": caller_sha256,
                "parent_pid": os.getpid(), "deadline_monotonic_ns": int(deadline * 1_000_000_000),
                "claimed_at": _utc_now(), "attempt_consumed": True}
        capture._exclusive_private_write_at(directory, "claim.json", canonical_json_bytes(body), "diagnostic claim")
        os.fsync(directory)
        claim = os.open("claim.json", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        _named_file(directory, "claim.json", claim)
        capture._require_pinned_child_identity(parent, CONTROL.name, directory, "diagnostic claim")
        os.mkdir("runtime", 0o700, dir_fd=directory)
        os.fsync(directory)
        return directory, claim
    except BaseException:
        if claim is not None:
            os.close(claim)
        if directory is not None:
            os.close(directory)
        raise
    finally:
        os.close(parent)


def _require_context(directory: int, claim: int) -> tuple[dict, float]:
    capture._require_private_directory_metadata(os.fstat(directory), "diagnostic claim")
    capture._require_reopened_artifact_identity(CONTROL, directory)
    _named_file(directory, "claim.json", claim)
    value = _exact(_read_channel(claim), {"schema", "profile_sha256", "expected_head", "caller_sha256",
                                            "parent_pid", "deadline_monotonic_ns", "claimed_at", "attempt_consumed"})
    parse_utc_timestamp(value["claimed_at"], "claim time")
    if (value["schema"] != SCHEMA or value["profile_sha256"] != PROFILE_SHA256
            or value["attempt_consumed"] is not True or type(value["parent_pid"]) is not int
            or value["parent_pid"] != os.getppid() or type(value["deadline_monotonic_ns"]) is not int):
        raise Refusal("control_refused")
    deadline = value["deadline_monotonic_ns"] / 1_000_000_000
    if _remaining(deadline) > DEADLINE_SECONDS:
        raise Refusal("control_refused")
    return value, deadline


def _worker(stage: str, directory: int, claim: int, channel: int) -> int:
    try:
        if stage not in ("capture", "authenticate") or len({directory, claim, channel}) != 3:
            return 2
        context, deadline = _require_context(directory, claim)
        with _alarm(deadline):
            _preflight(context["expected_head"], context["caller_sha256"], deadline)
            _named_file(directory, f"{stage}-result.json", channel)
            if _file_metadata(channel).st_size != 0:
                return 2
            # A duplicated direct worker invocation cannot dispatch a second time.
            capture._exclusive_private_write_at(directory, f"{stage}-started.json",
                canonical_json_bytes({"stage": stage, "profile_sha256": PROFILE_SHA256}), "worker start")
            os.fsync(directory)
            if stage == "capture":
                result = _capture_once()
            else:
                requested = _decode(sys.stdin.buffer.read(MAX_CHANNEL + 1))
                _require_binding(requested)
                result = _authenticate(requested)
            _named_file(directory, "claim.json", claim)
            _write_channel(channel, result)
            _named_file(directory, f"{stage}-result.json", channel)
            os.fsync(directory)
            return 0
    except BaseException:
        # Raw failure, opaque return and traceback are intentionally never emitted.
        return 2


def _run_worker(stage: str, directory: int, claim: int, deadline: float, binding: dict | None = None) -> dict:
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
        env = dict(os.environ)
        runtime = str(CONTROL / "runtime")
        env.update(TMPDIR=runtime, XDG_CACHE_HOME=runtime, PYTHONPYCACHEPREFIX=runtime,
                   PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
        if stage == "authenticate":
            env.pop("MASSIVE_API_KEY", None)
        _remaining(deadline, 2.0)
        process = subprocess.Popen(args, cwd=ROOT, env=env, stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            pass_fds=(directory, claim, descriptor), close_fds=True)
        try:
            process.communicate(None if binding is None else canonical_json_bytes(binding),
                                timeout=_remaining(deadline, 2.0))
        except subprocess.TimeoutExpired:
            raise Refusal("worker_timeout") from None
        if process.returncode != 0:
            raise Refusal("worker_nonzero")
        _named_file(directory, filename, descriptor)
        return _read_channel(descriptor)
    finally:
        if process is not None and process.poll() is None:
            process.kill()  # Only this invocation's own child; no other lane processes.
            process.wait(timeout=1)
        os.close(descriptor)


def _run(expected_head: str, caller_sha256: str, deadline: float) -> int:
    directory = claim = None
    result = {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256, "terminal": "control_refused",
              "attempt_consumed": False, "capture_observation": None, "binding": None,
              "parent_started_at": _utc_now(), "parent_observed_terminal_at": None,
              "authentication": None, "provider_request_count": None,
              "point_in_time_proven": False, "paper_look_committed": False, "qc_calls": 0, "outcome_reads": 0}
    try:
        _preflight(expected_head, caller_sha256, deadline)
        # A failure after mkdir can leave a spent leaf without returning its fd.
        # Unknown claim consumption must never be described as a preclaim refusal.
        result["terminal"] = "claim_ambiguous"
        result["attempt_consumed"] = None
        directory, claim = _claim(expected_head, caller_sha256, deadline)
        result["attempt_consumed"] = True
        result["terminal"] = "worker_channel_refused"
        produced = _require_capture_result(_run_worker("capture", directory, claim, deadline))
        result["capture_observation"] = produced["observation"]
        result["terminal"] = produced["terminal"]
        if produced["terminal"] == "producer_returned":
            claimed_at = parse_utc_timestamp(_read_channel(claim)["claimed_at"], "claim time")
            if not (claimed_at <= parse_utc_timestamp(produced["binding"]["capture_started_at"], "capture start")
                    <= parse_utc_timestamp(produced["binding"]["capture_completed_at"], "capture end")
                    <= parse_utc_timestamp(_utc_now(), "capture observed")):
                raise Refusal("invalid_producer_return")
            result["binding"] = produced["binding"]
            result["terminal"] = "authentication_refused"
            authenticated = _run_worker("authenticate", directory, claim, deadline, produced["binding"])
            result["authentication"] = _require_authentication(authenticated, produced["binding"])
            result["terminal"] = "accepted"
        _remaining(deadline)
    except Refusal as exc:
        label = BaseException.args.__get__(exc)
        result["terminal"] = label[0] if len(label) == 1 and type(label[0]) is str and label[0] in _TERMINALS else "control_refused"
    except (Deadline, subprocess.TimeoutExpired):
        result["terminal"] = "worker_timeout"
    except BaseException:
        if result["terminal"] not in _TERMINALS:
            result["terminal"] = "control_refused"
    try:
        _remaining(deadline)
        result["parent_observed_terminal_at"] = _utc_now()
        if directory is not None:
            capture._require_reopened_artifact_identity(CONTROL, directory)
            _named_file(directory, "claim.json", claim)
            payload = canonical_json_bytes(result)
            if len(payload) > MAX_CHANNEL:
                raise Refusal("control_refused")
            capture._exclusive_private_write_at(directory, "report.json", payload, "diagnostic report")
            os.fsync(directory)
            stored, _ = capture._read_and_pin_private_regular_at(directory, "report.json", maximum_bytes=MAX_CHANNEL, name="diagnostic report")
            if stored != payload or time.monotonic() >= deadline:
                raise Refusal("control_refused")
            capture._require_reopened_artifact_identity(CONTROL, directory)
            print(canonical_json_bytes({"terminal": result["terminal"], "profile_sha256": PROFILE_SHA256,
                "report_sha256": hashlib.sha256(payload).hexdigest(), "report_bytes": len(payload),
                "provider_request_count": None}).decode("utf-8"))
        else:
            print(canonical_json_bytes({"terminal": "claim_ambiguous" if result["attempt_consumed"] is None else "preclaim_refusal",
                "attempt_consumed": result["attempt_consumed"], "provider_request_count": None}).decode("utf-8"))
        return 0 if result["terminal"] == "accepted" else 2
    except BaseException:
        print('{"terminal":"publication_ambiguous","provider_request_count":null}')
        return 2
    finally:
        if claim is not None:
            os.close(claim)
        if directory is not None:
            os.close(directory)


def run(expected_head: str, caller_sha256: str) -> int:
    # SIGALRM also covers parent preflight/publication, not merely child wait.
    # It cannot promise a bound on an uninterruptible kernel operation or host
    # suspension. Any late/nonzero/unknown process exit remains inadmissible.
    deadline = time.monotonic() + DEADLINE_SECONDS
    try:
        with _alarm(deadline):
            return _run(expected_head, caller_sha256, deadline)
    except BaseException:
        print('{"terminal":"parent_ambiguous","provider_request_count":null}')
        return 2


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "_worker":
        try:
            if len(args) != 5:
                return 2
            return _worker(args[1], *(int(x) for x in args[2:]))
        except BaseException:
            return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--caller-sha256", required=True)
    parsed = parser.parse_args(args)
    return run(parsed.expected_head, parsed.caller_sha256)


if __name__ == "__main__":
    raise SystemExit(main())
