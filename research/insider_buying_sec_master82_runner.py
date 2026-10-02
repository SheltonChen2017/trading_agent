"""Explicit, resumable SEC-only acquisition of the 82 quarterly master indexes.

The retained ZIP census fixes the requests.  An exclusive output-root lock and
immutable, hash-chained event files reserve every attempt before dispatch.
Resume verifies the exact code, plan, completed objects and parsed receipts;
an interrupted attempt consumes its attempt slot.  No filing parent, outcome,
QuantConnect, canonical signal, or trading surface is used here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import getpass
import http.client
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
from typing import Callable

from data.hashing import canonical_json, hash_bytes
from research.insider_buying.sec_bulk_snapshot import SecBulkSnapshotError, _read_regular_bytes
from research.insider_buying.sec_quarter_master_index import (
    MASTER_INDEX_PARSER_VERSION,
    SecQuarterMasterIndexError,
    parse_sec_quarter_master_index,
)
from research.insider_buying.sec_zip_corpus_census import census_retained_sec_zip_corpus
from research.insider_buying_sec_acquisition import (
    _check_output_directory,
    _open_output_directory,
    _plain_path,
    _publish_immutable,
    _refuse_output_overlap,
    _safe_roots,
    _store_object,
)
from research.insider_buying_sec_complete_acquisition import (
    SecCompleteAcquisitionError,
    SecHttpResult,
    _decompress_master,
    _sec_transport,
    _strict_response,
)
from research.insider_buying_sec_master82_acquisition import (
    MAX_ATTEMPTS_PER_ARTIFACT,
    MAX_DISTINCT_ARTIFACTS,
    MAX_MASTER_GZIP_BYTES,
    MAX_TOTAL_ATTEMPTS,
    MIN_REQUEST_INTERVAL_NS,
    SecMaster82AcquisitionPreparation,
    prepare_retained_master82_acquisition,
)


RUNNER_VERSION = "INSETF-SEC-MASTER82-RESUMABLE-v1"
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_EVENT_NAME = re.compile(r"event-([0-9]{6})-([0-9a-f]{64})\.json\Z")
_MAX_EVENT_BYTES = 2048
_MAX_EVENTS = MAX_TOTAL_ATTEMPTS * 4 + MAX_DISTINCT_ARTIFACTS + 2
_MAX_JOURNAL_BYTES = 2 * 1024 * 1024
_RETRY_STATUSES = frozenset((500, 502, 503, 504))
_EVENT_FIELDS = {
    "attempt-start": {"kind", "prev_sha256", "period", "url", "attempt", "ordinal", "started_utc"},
    "attempt-finish": {"kind", "prev_sha256", "period", "ordinal", "outcome", "status",
                       "body_sha256", "body_size_bytes", "finished_utc"},
    "attempt-abandoned": {"kind", "prev_sha256", "period", "ordinal"},
    "response-object-missing": {"kind", "prev_sha256", "period", "ordinal"},
    "quarter-complete": {"kind", "prev_sha256", "period", "attempt_ordinal",
                         "object_sha256", "object_size_bytes", "summary"},
    "quarter-refused": {"kind", "prev_sha256", "period", "reason"},
}


class SecMaster82RunnerError(ValueError):
    """The 82-quarter operational boundary refused a run or resume."""


def _refuse(message: str) -> None:
    raise SecMaster82RunnerError(f"REFUSED: {message}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _canonical_bytes(value: object) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def _host_kind() -> str:
    return os.name


def _require_supported_host() -> None:
    if _host_kind() != "posix":
        _refuse("resumable master acquisition requires POSIX directory handles")


def _strict_json(raw: bytes, *, label: str) -> dict[str, object]:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                _refuse(f"{label} repeats a JSON key")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=unique,
                           parse_constant=lambda _: _refuse(f"{label} has a nonfinite value"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SecMaster82RunnerError(f"REFUSED: {label} is not strict JSON") from exc
    if type(value) is not dict or _canonical_bytes(value) != raw:
        _refuse(f"{label} is not canonical JSON plus one LF")
    return value


def _lock_fd(fd: int) -> None:
    import fcntl
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_fd(fd: int) -> None:
    import fcntl
    fcntl.flock(fd, fcntl.LOCK_UN)


def _read_recoverable(path: Path, *, label: str, max_bytes: int,
                      expected_sha256: str | None = None,
                      expected_raw: bytes | None = None) -> bytes:
    """Recover only a linked publisher temporary left by a hard interruption."""
    try:
        raw = _read_regular_bytes(path, label=label, max_bytes=max_bytes)
    except SecBulkSnapshotError as exc:
        raise SecMaster82RunnerError(str(exc)) from exc
    if ((expected_sha256 is not None and hash_bytes(raw) != expected_sha256)
            or (expected_raw is not None and raw != expected_raw)):
        _refuse(f"{label} hash or bytes changed")
    try:
        info = path.lstat()
    except OSError as exc:
        raise SecMaster82RunnerError(f"REFUSED: {label} disappeared during recovery") from exc
    if info.st_nlink == 1:
        return raw
    if info.st_nlink != 2 or not stat.S_ISREG(info.st_mode):
        _refuse(f"{label} has unexpected hard links")
    prefix = ".sec-object-" if path.suffix == ".bin" else ".sec-publish-"
    temporary_name = re.compile(re.escape(prefix) + r"[0-9a-f]{32}\.tmp\Z")
    matches = []
    for name in os.listdir(path.parent):
        if temporary_name.fullmatch(name) is None:
            continue
        candidate_info = (path.parent / name).lstat()
        if (stat.S_ISREG(candidate_info.st_mode)
                and (candidate_info.st_dev, candidate_info.st_ino) == (info.st_dev, info.st_ino)):
            matches.append(name)
    if len(matches) != 1:
        _refuse(f"{label} cannot recover its publisher link")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_fd = os.open(path.parent, flags)
    try:
        current = os.stat(matches[0], dir_fd=directory_fd, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
            _refuse(f"{label} publisher temporary changed")
        os.unlink(matches[0], dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    try:
        checked = _read_regular_bytes(path, label=label, max_bytes=max_bytes,
                                      require_single_link=True)
    except SecBulkSnapshotError as exc:
        raise SecMaster82RunnerError(str(exc)) from exc
    if checked != raw:
        _refuse(f"{label} changed during recovery")
    return checked


def _verify_exact_committed_code(commit: str) -> None:
    if type(commit) is not str or _COMMIT.fullmatch(commit) is None:
        _refuse("code commit must be a full lowercase Git SHA")
    root = Path(__file__).resolve().parents[1]
    paths = (
        "research/insider_buying_sec_master82_runner.py",
        "research/insider_buying_sec_master82_acquisition.py",
        "research/insider_buying/sec_zip_corpus_census.py",
        "research/insider_buying/sec_quarter_master_index.py",
        "research/insider_buying_sec_complete_acquisition.py",
        "research/insider_buying_sec_acquisition.py",
        "research/insider_buying/sec_bulk_snapshot.py",
        "data/hashing.py",
    )
    try:
        command = lambda *args: subprocess.check_output(args, cwd=root, stderr=subprocess.DEVNULL)
        top = command("git", "rev-parse", "--show-toplevel").decode().strip()
        branch = command("git", "branch", "--show-current").decode().strip()
        actual = command("git", "rev-parse", "HEAD").decode().strip()
        dirty = command("git", "status", "--porcelain=v1", "--untracked-files=all")
        if (top != str(root) or branch != "codex/strategy-insider-buying"
                or actual != commit or dirty):
            _refuse("exact clean committed Insider lane is required")
        for relative in paths:
            committed = command("git", "show", f"{commit}:{relative}")
            if hash_bytes(committed) != hash_bytes((root / relative).read_bytes()):
                _refuse("committed runner dependency differs on disk")
    except (OSError, UnicodeError, subprocess.CalledProcessError) as exc:
        raise SecMaster82RunnerError("REFUSED: exact code commit could not be verified") from exc


class _RootLock:
    def __init__(self, output: Path, identity: tuple[int, int], *, resume: bool) -> None:
        self.directory_fd = _open_output_directory(output, identity)
        self.fd: int | None = None
        try:
            flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
            flags |= 0 if resume else os.O_CREAT | os.O_EXCL
            self.fd = os.open("run.lock", flags, 0o600, dir_fd=self.directory_fd)
            info = os.fstat(self.fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != 0:
                _refuse("run lock is not an empty single-link regular file")
            try:
                _lock_fd(self.fd)
            except OSError as exc:
                raise SecMaster82RunnerError("REFUSED: output root is in use") from exc
            _check_output_directory(output, self.directory_fd, identity)
            os.fsync(self.directory_fd)
        except BaseException:
            if self.fd is not None:
                os.close(self.fd)
            os.close(self.directory_fd)
            raise

    def close(self) -> None:
        try:
            try:
                _unlock_fd(self.fd)
            finally:
                os.close(self.fd)
        finally:
            os.close(self.directory_fd)


class _Events:
    def __init__(self, output: Path, identity: tuple[int, int], inventory_sha256: str) -> None:
        self.output = output
        self.identity = identity
        self.tail = inventory_sha256
        self.raw: list[bytes] = []

    def load(self) -> list[dict[str, object]]:
        directory_fd = _open_output_directory(self.output, self.identity)
        try:
            names = [name for name in os.listdir(directory_fd) if name.startswith("event-")]
            if len(names) > _MAX_EVENTS:
                _refuse("event journal exceeds its fixed budget")
            parsed: list[tuple[int, str]] = []
            for name in names:
                match = _EVENT_NAME.fullmatch(name)
                if match is None:
                    _refuse("event journal filename is malformed")
                parsed.append((int(match.group(1)), name))
            parsed.sort()
            if [index for index, _ in parsed] != list(range(1, len(parsed) + 1)):
                _refuse("event journal sequence is incomplete or duplicated")
            events: list[dict[str, object]] = []
            for _, name in parsed:
                raw = _read_recoverable(
                    self.output / name, label="master82 event", max_bytes=_MAX_EVENT_BYTES,
                    expected_sha256=_EVENT_NAME.fullmatch(name).group(2),
                )
                event = _strict_json(raw, label="master82 event")
                if event.get("prev_sha256") != self.tail:
                    _refuse("event journal hash chain changed")
                self.tail = hash_bytes(raw)
                self.raw.append(raw)
                events.append(event)
            return events
        finally:
            os.close(directory_fd)

    def append(self, payload: dict[str, object]) -> None:
        if len(self.raw) >= _MAX_EVENTS:
            _refuse("event journal exceeds its fixed budget")
        event = {**payload, "prev_sha256": self.tail}
        raw = _canonical_bytes(event)
        if len(raw) > _MAX_EVENT_BYTES:
            _refuse("event exceeds its byte budget")
        digest = hash_bytes(raw)
        name = f"event-{len(self.raw) + 1:06d}-{digest}.json"
        _publish_immutable(self.output, name, raw, self.identity)
        self.raw.append(raw)
        self.tail = digest


def _summary(raw: bytes, *, period: str) -> dict[str, object]:
    try:
        plain = _decompress_master(raw)
        receipt = parse_sec_quarter_master_index(
            plain, year=int(period[:4]), quarter=int(period[-1])
        )
    except (SecCompleteAcquisitionError, SecQuarterMasterIndexError) as exc:
        raise SecMaster82RunnerError(str(exc)) from exc
    return {
        "decoded_sha256": hash_bytes(plain),
        "decoded_size_bytes": len(plain),
        "parser_version": MASTER_INDEX_PARSER_VERSION,
        "master_receipt_sha256": receipt.receipt_sha256,
        "all_filing_row_count": receipt.all_filing_row_count,
        "form4_or_4a_path_rows": len(receipt.rows),
    }


def _read_object(output: Path, digest: str, size: int) -> bytes:
    if (type(digest) is not str or _HASH.fullmatch(digest) is None
            or type(size) is not int or not 0 < size <= MAX_MASTER_GZIP_BYTES):
        _refuse("master object descriptor is malformed")
    raw = _read_recoverable(
        output / "objects" / f"{digest}.bin", label="master82 raw object",
        max_bytes=MAX_MASTER_GZIP_BYTES, expected_sha256=digest,
    )
    if len(raw) != size or hash_bytes(raw) != digest:
        _refuse("master object hash or size changed")
    return raw


def _state(plan: SecMaster82AcquisitionPreparation, events: list[dict[str, object]],
           output: Path) -> tuple[list[dict[str, object]], dict[str, int],
                                  dict[str, object] | None, dict[str, object] | None,
                                  str | None]:
    """Replay every transition; verify completed objects before any new request."""
    completed: list[dict[str, object]] = []
    attempts: dict[str, int] = {}
    pending_start: dict[str, object] | None = None
    pending_valid: dict[str, object] | None = None
    terminal: str | None = None
    total = 0
    for event in events:
        kind = event.get("kind")
        if type(kind) is not str:
            _refuse("event kind is malformed")
        expected_fields = _EVENT_FIELDS.get(kind)
        if expected_fields is None:
            _refuse("event kind is unknown")
        if kind == "attempt-finish" and event.get("outcome") in {
            "refused_response", "transport_refusal"
        }:
            expected_fields = expected_fields | {"reason"}
        if set(event) != expected_fields:
            _refuse("event fields are not the exact journal contract")
        if terminal is not None:
            _refuse("event follows a terminal source refusal")
        if len(completed) == MAX_DISTINCT_ARTIFACTS:
            _refuse("event follows the complete 82-quarter inventory")
        request = plan.requests[len(completed)]
        period = request.period
        if kind == "attempt-start":
            if pending_start is not None or pending_valid is not None:
                _refuse("attempt starts before earlier attempt is resolved")
            total += 1
            count = attempts.get(period, 0) + 1
            if (total > MAX_TOTAL_ATTEMPTS or count > MAX_ATTEMPTS_PER_ARTIFACT
                    or event.get("ordinal") != total or event.get("attempt") != count
                    or event.get("period") != period or event.get("url") != request.url
                    or type(event.get("started_utc")) is not str):
                _refuse("attempt reservation disagrees with fixed order or ceiling")
            attempts[period] = count
            pending_start = event
        elif kind == "attempt-finish":
            if (pending_start is None or pending_valid is not None
                    or event.get("ordinal") != pending_start["ordinal"]
                    or event.get("period") != period
                    or type(event.get("finished_utc")) is not str):
                _refuse("attempt completion lacks its reservation")
            outcome = event.get("outcome")
            status = event.get("status")
            digest = event.get("body_sha256")
            size = event.get("body_size_bytes")
            if outcome == "valid_response":
                if (status != 200 or type(digest) is not str
                        or _HASH.fullmatch(digest) is None or type(size) is not int
                        or not 0 < size <= MAX_MASTER_GZIP_BYTES):
                    _refuse("valid response descriptor is malformed")
                pending_valid = event
            elif outcome == "network_error":
                if status is not None or digest is not None or size is not None:
                    _refuse("network error carries a response")
            elif outcome == "http_error":
                if type(status) is not int or status == 200 or digest is not None or size is not None:
                    _refuse("HTTP error descriptor is malformed")
                if status not in _RETRY_STATUSES:
                    terminal = f"REFUSED: SEC returned HTTP {status}"
            elif outcome == "refused_response":
                if (status != 200 or digest is not None or size is not None
                        or type(event.get("reason")) is not str):
                    _refuse("refused response descriptor is malformed")
                terminal = event["reason"]
            elif outcome == "transport_refusal":
                if (status is not None or digest is not None or size is not None
                        or type(event.get("reason")) is not str):
                    _refuse("transport refusal descriptor is malformed")
                terminal = event["reason"]
            else:
                _refuse("attempt outcome is unknown")
            pending_start = None
        elif kind == "attempt-abandoned":
            if (pending_start is None or pending_valid is not None
                    or event.get("ordinal") != pending_start["ordinal"]
                    or event.get("period") != period):
                _refuse("abandoned attempt lacks an unfinished reservation")
            pending_start = None
        elif kind == "response-object-missing":
            if (pending_valid is None or pending_start is not None
                    or event.get("ordinal") != pending_valid["ordinal"]
                    or event.get("period") != period):
                _refuse("missing response lacks a validated HTTP 200")
            candidate = output / "objects" / f'{pending_valid["body_sha256"]}.bin'
            if candidate.exists() or candidate.is_symlink():
                _refuse("response marked missing while its object exists")
            pending_valid = None
        elif kind == "quarter-complete":
            if (pending_valid is None or pending_start is not None
                    or event.get("period") != period
                    or event.get("attempt_ordinal") != pending_valid["ordinal"]
                    or event.get("object_sha256") != pending_valid["body_sha256"]
                    or event.get("object_size_bytes") != pending_valid["body_size_bytes"]):
                _refuse("quarter completion lacks its exact validated response")
            raw = _read_object(output, event["object_sha256"], event["object_size_bytes"])
            if event.get("summary") != _summary(raw, period=period):
                _refuse("completed quarter parse receipt changed")
            completed.append(event)
            pending_valid = None
        elif kind == "quarter-refused":
            if event.get("period") != period or type(event.get("reason")) is not str:
                _refuse("quarter refusal is malformed")
            terminal = event["reason"]
            pending_valid = None
            pending_start = None
        else:
            _refuse("event kind is unknown")
    return completed, attempts, pending_start, pending_valid, terminal


def _publish_same_or_new(output: Path, name: str, raw: bytes,
                         identity: tuple[int, int]) -> Path:
    path = output / name
    try:
        return _publish_immutable(output, name, raw, identity)
    except FileExistsError:
        existing = _read_recoverable(path, label="master82 immutable publication",
                                     max_bytes=_MAX_JOURNAL_BYTES, expected_raw=raw)
        if existing != raw:
            _refuse("immutable publication path contains different bytes")
        return path


def _finalize(output: Path, identity: tuple[int, int], plan: SecMaster82AcquisitionPreparation,
              code_commit: str, events: _Events, completed: list[dict[str, object]],
              attempts: dict[str, int], reason: str | None) -> Path:
    journal = b"".join(events.raw)
    if len(journal) > _MAX_JOURNAL_BYTES:
        _refuse("final attempt journal exceeds its byte budget")
    _publish_same_or_new(output, "attempts.jsonl", journal, identity)
    rows: list[dict[str, object]] = []
    for index, request in enumerate(plan.requests):
        row: dict[str, object] = {
            "period": request.period, "source_url": request.url,
            "retained_zip_sha256": request.retained_zip_sha256,
            "attempts": attempts.get(request.period, 0),
            "status": "not_attempted", "reason": None,
        }
        if index < len(completed):
            event = completed[index]
            row.update({"status": "acquired_noncanonical",
                        "raw_object": {"relative_path": f'objects/{event["object_sha256"]}.bin',
                                       "sha256": event["object_sha256"],
                                       "size_bytes": event["object_size_bytes"]},
                        "receipt": event["summary"]})
        elif index == len(completed) and reason is not None:
            row.update({"status": "refused", "reason": reason})
        rows.append(row)
    payload = {
        "kind": RUNNER_VERSION,
        "source_scope": plan.census_scope,
        "capture_git_commit_verified": (
            code_commit if plan.census_scope == "retained_noncanonical_zip_census" else None
        ),
        "source_census_sha256": plan.census_sha256,
        "request_inventory_sha256": plan.request_inventory_sha256,
        "plan_sha256": plan.sha256, "master_indexes": rows,
        "attempt_journal_sha256": hash_bytes(journal),
        "attempt_event_count": len(events.raw),
        "attempt_count": sum(attempts.values()),
        "distinct_artifact_count": len(attempts),
        "halted_reason": reason,
        "complete_82_master_indexes_acquired": reason is None and len(completed) == 82,
        "source_authenticated": False, "quarter_population_complete": False,
        "canonical_evidence": False, "point_in_time_data": False,
        "complete_parent_or_acceptance_metadata": False,
        "outcome_access_authorized": False, "qc_job_authorized": False,
        "broker_or_trading_authorized": False,
        "research_looks": 0, "authorized_outcome_looks": 0,
        "consumed_outcome_looks": 0,
    }
    raw = _canonical_bytes(payload)
    digest = hash_bytes(raw)
    name = f"sec-master82-report-{digest}.json"
    _publish_same_or_new(output, name, raw, identity)
    commit = {"kind": "sec-master82-commit", "report_name": name,
              "report_sha256": digest, "attempt_journal_sha256": hash_bytes(journal)}
    _publish_same_or_new(output, "commit.json", _canonical_bytes(commit), identity)
    return output / name


def _run_master82(plan: SecMaster82AcquisitionPreparation, output_root: str | Path, *,
                  capture_git_commit: str, transport: Callable[[str, dict[str, str], int], SecHttpResult],
                  resume: bool = False) -> Path:
    """Internal synthetic-test seam; only the public entry builds a retained plan."""
    _require_supported_host()
    if type(plan) is not SecMaster82AcquisitionPreparation or not callable(transport):
        _refuse("exact plan and transport are required")
    plan.__post_init__()
    if plan.census_scope == "retained_noncanonical_zip_census":
        _verify_exact_committed_code(capture_git_commit)
    if plan.census_scope == "synthetic_test_census" and transport is _sec_transport:
        _refuse("synthetic plan cannot use the real SEC transport")
    lane_root = Path(__file__).resolve().parents[1]
    if resume:
        output = _plain_path(output_root, must_exist=True)
        _refuse_output_overlap(output, lane_root)
    else:
        output = _plain_path(output_root, must_exist=False)
        _refuse_output_overlap(output, lane_root)
        if output.exists():
            _refuse("new output root must not exist")
        try:
            output.mkdir(mode=0o700)
        except FileExistsError as exc:
            raise SecMaster82RunnerError("REFUSED: new output root was claimed") from exc
    current = output.lstat()
    if not stat.S_ISDIR(current.st_mode):
        _refuse("output root is not a regular directory")
    identity = (current.st_dev, current.st_ino)
    lock = _RootLock(output, identity, resume=resume)
    try:
        frozen = {
            "kind": "sec-master82-frozen-inventory", "version": RUNNER_VERSION,
            "capture_git_commit": capture_git_commit,
            "source_scope": plan.census_scope,
            "source_census_sha256": plan.census_sha256,
            "request_inventory_sha256": plan.request_inventory_sha256,
            "plan_sha256": plan.sha256,
            "requests": [request.to_payload() for request in plan.requests],
            "source_authenticated": False, "canonical_evidence": False,
            "outcome_access_authorized": False, "qc_job_authorized": False,
            "research_looks": 0,
        }
        inventory_raw = _canonical_bytes(frozen)
        if resume:
            existing = _read_recoverable(output / "inventory.json", label="master82 inventory",
                                         max_bytes=64 * 1024, expected_raw=inventory_raw)
            if existing != inventory_raw:
                _refuse("resume plan, code commit, or source census changed")
            if (output / "commit.json").exists():
                _refuse("committed master82 output cannot be resumed")
            objects = _plain_path(output / "objects", must_exist=True)
            if objects != output / "objects":
                _refuse("object directory changed")
        else:
            (output / "objects").mkdir(mode=0o700)
            _publish_immutable(output, "inventory.json", inventory_raw, identity)
        events = _Events(output, identity, hash_bytes(inventory_raw))
        prior = events.load() if resume else []
        completed, attempts, pending_start, pending_valid, terminal = _state(plan, prior, output)
        if pending_start is not None:
            events.append({"kind": "attempt-abandoned", "period": pending_start["period"],
                           "ordinal": pending_start["ordinal"]})
        if pending_valid is not None:
            period = str(pending_valid["period"])
            digest = str(pending_valid["body_sha256"])
            object_path = output / "objects" / f"{digest}.bin"
            if object_path.exists() or object_path.is_symlink():
                raw = _read_object(output, digest, pending_valid["body_size_bytes"])
                try:
                    summary = _summary(raw, period=period)
                except SecMaster82RunnerError as exc:
                    terminal = str(exc)
                    events.append({"kind": "quarter-refused", "period": period,
                                   "reason": terminal})
                else:
                    events.append({"kind": "quarter-complete", "period": period,
                                   "attempt_ordinal": pending_valid["ordinal"],
                                   "object_sha256": digest,
                                   "object_size_bytes": pending_valid["body_size_bytes"],
                                   "summary": summary})
            else:
                events.append({"kind": "response-object-missing", "period": period,
                               "ordinal": pending_valid["ordinal"]})
        completed, attempts, _, _, terminal_state = _state(
            plan, events.load() if not events.raw else
            [_strict_json(raw, label="master82 event") for raw in events.raw], output
        )
        terminal = terminal or terminal_state
        if resume and terminal is None and len(completed) < 82:
            # The prior process may have ended after transport completion or
            # in-flight. Give the SEC more than the required spacing before
            # this process's first possible dispatch.
            time.sleep((MIN_REQUEST_INTERVAL_NS + 1_000_000_000) / 1_000_000_000)
        last_completion_ns: int | None = None
        while terminal is None and len(completed) < MAX_DISTINCT_ARTIFACTS:
            request = plan.requests[len(completed)]
            used = attempts.get(request.period, 0)
            if used >= MAX_ATTEMPTS_PER_ARTIFACT:
                terminal = "REFUSED: master attempt ceiling consumed"
                events.append({"kind": "quarter-refused", "period": request.period,
                               "reason": terminal})
                break
            attempt = used + 1
            start_pace = time.monotonic_ns()
            earliest = max(start_pace, (last_completion_ns + MIN_REQUEST_INTERVAL_NS)
                           if last_completion_ns is not None else start_pace)
            if attempt > 1:
                earliest = max(earliest, start_pace + attempt * 1_000_000_000)
            remaining = earliest - time.monotonic_ns()
            if remaining > 0:
                time.sleep(remaining / 1_000_000_000)
            ordinal = sum(attempts.values()) + 1
            events.append({"kind": "attempt-start", "period": request.period,
                           "url": request.url, "attempt": attempt,
                           "ordinal": ordinal, "started_utc": _utc_now()})
            if time.monotonic_ns() < earliest:
                _refuse("actual SEC dispatch pacing was too early")
            headers = {"User-Agent": f"InsiderBuyingResearch/0.1 ({plan.contact_email})",
                       "Accept": "*/*", "Accept-Encoding": "identity",
                       "Connection": "close"}
            try:
                result = transport(request.url, headers, MAX_MASTER_GZIP_BYTES)
            except (OSError, http.client.HTTPException):
                last_completion_ns = time.monotonic_ns()
                events.append({"kind": "attempt-finish", "period": request.period,
                               "ordinal": ordinal, "outcome": "network_error",
                               "status": None, "body_sha256": None,
                               "body_size_bytes": None, "finished_utc": _utc_now()})
                attempts[request.period] = attempt
                continue
            except SecCompleteAcquisitionError:
                last_completion_ns = time.monotonic_ns()
                terminal = "REFUSED: SEC transport rejected the response"
                events.append({"kind": "attempt-finish", "period": request.period,
                               "ordinal": ordinal, "outcome": "transport_refusal",
                               "status": None, "body_sha256": None,
                               "body_size_bytes": None, "finished_utc": _utc_now(),
                               "reason": terminal})
                attempts[request.period] = attempt
                break
            last_completion_ns = time.monotonic_ns()
            if type(result) is not SecHttpResult or type(result.status) is not int:
                events.append({"kind": "attempt-finish", "period": request.period,
                               "ordinal": ordinal, "outcome": "transport_refusal",
                               "status": None, "body_sha256": None,
                               "body_size_bytes": None, "finished_utc": _utc_now(),
                               "reason": "REFUSED: transport result is malformed"})
                terminal = "REFUSED: transport result is malformed"
                break
            if result.status != 200:
                events.append({"kind": "attempt-finish", "period": request.period,
                               "ordinal": ordinal, "outcome": "http_error",
                               "status": result.status, "body_sha256": None,
                               "body_size_bytes": None, "finished_utc": _utc_now()})
                attempts[request.period] = attempt
                if result.status not in _RETRY_STATUSES:
                    terminal = f"REFUSED: SEC returned HTTP {result.status}"
                continue
            try:
                raw = _strict_response(result, max_bytes=MAX_MASTER_GZIP_BYTES)
            except SecCompleteAcquisitionError as exc:
                events.append({"kind": "attempt-finish", "period": request.period,
                               "ordinal": ordinal, "outcome": "refused_response",
                               "status": 200, "body_sha256": None,
                               "body_size_bytes": None, "finished_utc": _utc_now(),
                               "reason": str(exc)})
                terminal = str(exc)
                break
            digest = hash_bytes(raw)
            events.append({"kind": "attempt-finish", "period": request.period,
                           "ordinal": ordinal, "outcome": "valid_response",
                           "status": 200, "body_sha256": digest,
                           "body_size_bytes": len(raw), "finished_utc": _utc_now()})
            attempts[request.period] = attempt
            descriptor = _store_object(output, raw, identity)
            try:
                summary = _summary(raw, period=request.period)
            except SecMaster82RunnerError as exc:
                terminal = str(exc)
                events.append({"kind": "quarter-refused", "period": request.period,
                               "reason": terminal})
                break
            events.append({"kind": "quarter-complete", "period": request.period,
                           "attempt_ordinal": ordinal,
                           "object_sha256": descriptor["sha256"],
                           "object_size_bytes": descriptor["size_bytes"],
                           "summary": summary})
            completed.append(_strict_json(events.raw[-1], label="master82 event"))
        if terminal is None and len(completed) != MAX_DISTINCT_ARTIFACTS:
            _refuse("master82 run ended without an exact outcome")
        replay = [_strict_json(raw, label="master82 event") for raw in events.raw]
        checked, final_attempts, _, _, checked_terminal = _state(plan, replay, output)
        if checked != completed or checked_terminal != terminal:
            _refuse("final journal replay disagrees with in-memory outcome")
        return _finalize(output, identity, plan, capture_git_commit,
                         events, checked, final_attempts, terminal)
    finally:
        lock.close()


def run_retained_master82_acquisition(
    input_root: str | Path, output_root: str | Path, *, contact_email: str,
    capture_git_commit: str, resume: bool = False,
    transport: Callable[[str, dict[str, str], int], SecHttpResult] | None = None,
) -> Path:
    """Acquire only the exact retained 82-index plan; never auto-resume a root."""
    _require_supported_host()
    _verify_exact_committed_code(capture_git_commit)
    source = _plain_path(input_root, must_exist=True)
    output = _plain_path(output_root, must_exist=resume)
    if not resume:
        _safe_roots(source, source, output)
    else:
        _refuse_output_overlap(output, source)
    census = census_retained_sec_zip_corpus(source)
    plan = prepare_retained_master82_acquisition(census, contact_email=contact_email)
    if plan.census_scope != "retained_noncanonical_zip_census":
        _refuse("real runner requires the exact retained 82-quarter source")
    return _run_master82(plan, output, capture_git_commit=capture_git_commit,
                         transport=_sec_transport if transport is None else transport,
                         resume=resume)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--capture-git-commit", required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    contact = getpass.getpass("SEC EDGAR identifying contact email: ")
    report = run_retained_master82_acquisition(
        args.input_root, args.output_root, contact_email=contact,
        capture_git_commit=args.capture_git_commit, resume=args.resume,
    )
    print(report)
    return 0


if __name__ == "__main__":  # pragma: no cover - explicit operator launch only
    raise SystemExit(main())
