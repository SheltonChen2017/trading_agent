"""Crash-resumable, noncanonical acquisition of an exact selected SEC parent set.

The public real entry is bound to a separately validated locator manifest.  This
module only retains bounded complete-submission .txt bytes and acquisition
lineage outside Git; it does not parse a Form 4, assert completeness, consume
outcomes, or launch QuantConnect.  Importing it performs no I/O.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
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
from typing import Callable, Mapping

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying.sec_bulk_snapshot import SecBulkSnapshotError, _read_regular_bytes
from research.insider_buying.sec_complete_submission import SecCompleteSubmissionTarget
from research.insider_buying_sec_acquisition import (
    _ascii_decimal,
    _check_output_directory,
    _open_output_directory,
    _plain_path,
    _publish_immutable,
    _refuse_output_overlap,
    _store_object,
)
from research.insider_buying_sec_complete_acquisition import (
    MAX_COMPLETE_TXT_BYTES,
    SecCompleteAcquisitionError,
    SecHttpResult,
    _sec_transport,
    _strict_response,
)
from research.insider_buying_sec_master82_runner import (
    SecMaster82RunnerError, _RootLock, _read_recoverable,
)


RUNNER_VERSION = "INSETF-SEC-SELECTED-PARENTS-RESUMABLE-v1"
PINNED_REAL_LOCATOR_SHA256 = (
    "7084c851a3420e38b570b13396eb8e768930249d64c90e9b2975b1355800cb9b"
)
# Replayed from the two exact retained IB-1B snapshots and both hash-verified
# master indexes. The reuse digest is the selected intersection (9/16) of the
# pinned complete-pilot receipt, not an arbitrary caller-declared prior root.
PINNED_REAL_REQUEST_INVENTORY_SHA256 = (
    "8e251c91ff89b87f6f3e83b8f968d63b83fe5f5e19e6d48a650afbed06b7742d"
)
PINNED_REAL_REUSE_INVENTORY_SHA256 = (
    "6c8fe9038d98a8278e7bd9955992ff719e4fa6665beab16075d8f60b0d99809e"
)
MAX_SELECTED = 9_337
MAX_ATTEMPTS_PER_ARTIFACT = 3
MAX_TOTAL_ATTEMPTS = MAX_SELECTED * MAX_ATTEMPTS_PER_ARTIFACT
MIN_REQUEST_INTERVAL_NS = 500_000_000
MAX_RUN_OBJECT_BYTES = 48 * 1024 * 1024 * 1024
MIN_FREE_BYTES = 8 * 1024 * 1024 * 1024
_MAX_EVENT_BYTES = 2_048
_MAX_EVENTS = MAX_TOTAL_ATTEMPTS * 3 + MAX_SELECTED + 8
_MAX_JOURNAL_BYTES = 256 * 1024 * 1024
_MAX_REPORT_BYTES = 32 * 1024 * 1024
_EVENT_NAME = re.compile(r"event-([0-9]{6})-([0-9a-f]{64})\.json\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_CONTACT = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}\Z")
_ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_RETRY_STATUSES = frozenset({500, 502, 503, 504})
_ENVELOPE_REFUSAL = "REFUSED: SEC HTTP 200 body lacks complete-text envelope"
_SEC_ARCHIVE_PREFIX = "https://www.sec.gov/Archives/"


class SecSelectedParentRunnerError(ValueError):
    """The selected-parent acquisition boundary refused a run or resume."""


def _refuse(message: str) -> None:
    raise SecSelectedParentRunnerError(f"REFUSED: {message}")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _bytes(value: object) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


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
                           parse_constant=lambda _: _refuse(f"{label} is nonfinite"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SecSelectedParentRunnerError(f"REFUSED: {label} is not strict JSON") from exc
    if type(value) is not dict or _bytes(value) != raw:
        _refuse(f"{label} is not canonical JSON plus LF")
    return value


def _selected_framing(headers: tuple[tuple[str, str], ...],
                      max_bytes: int) -> tuple[str, int | None]:
    """Accept one bounded length or one identity-encoded chunked framing."""
    if (type(max_bytes) is not int or not 0 < max_bytes <= MAX_COMPLETE_TXT_BYTES
            or type(headers) is not tuple
            or any(type(pair) is not tuple or len(pair) != 2
                   or type(pair[0]) is not str or type(pair[1]) is not str
                   for pair in headers)):
        raise SecCompleteAcquisitionError("REFUSED: selected SEC response framing is malformed")
    lengths = [value for name, value in headers if name.lower() == "content-length"]
    transfers = [value for name, value in headers if name.lower() == "transfer-encoding"]
    encodings = [value for name, value in headers if name.lower() == "content-encoding"]
    if len(encodings) > 1 or (encodings and encodings[0].strip().lower() != "identity"):
        raise SecCompleteAcquisitionError("REFUSED: selected SEC response framing is compressed")
    if len(lengths) == 1 and not transfers and _ascii_decimal(lengths[0]):
        size = int(lengths[0])
        if 0 < size <= max_bytes:
            return "length", size
    # Match http.client.HTTPResponse's decoder condition exactly. It does not
    # de-chunk a value such as "chunked "; accepting that spelling here would
    # mistake raw chunk framing for decoded complete-submission bytes.
    if not lengths and len(transfers) == 1 and transfers[0].lower() == "chunked":
        return "chunked", None
    raise SecCompleteAcquisitionError("REFUSED: selected SEC response framing is ambiguous or oversized")


def _strict_selected_response(result: SecHttpResult, *, max_bytes: int) -> bytes:
    """Keep the observed wire framing; do not invent Content-Length."""
    if type(result) is not SecHttpResult or type(result.status) is not int or result.status != 200:
        raise SecCompleteAcquisitionError("REFUSED: selected SEC response is not HTTP 200")
    mode, _ = _selected_framing(result.headers, max_bytes)
    if mode == "length":
        return _strict_response(result, max_bytes=max_bytes)
    if type(result.body) is not bytes or not 0 < len(result.body) <= max_bytes:
        raise SecCompleteAcquisitionError("REFUSED: selected SEC chunked body exceeds its bound")
    return result.body


def _selected_sec_transport(url: str, headers: dict[str, str], max_bytes: int) -> SecHttpResult:
    """Selected-parent-only SEC transport; http.client de-chunks at a hard cap."""
    if (type(url) is not str or not url.startswith(_SEC_ARCHIVE_PREFIX)
            or "?" in url or "#" in url or "%" in url):
        raise SecCompleteAcquisitionError("REFUSED: request escaped the exact SEC Archives host")
    if type(max_bytes) is not int or not 0 < max_bytes <= MAX_COMPLETE_TXT_BYTES:
        raise SecCompleteAcquisitionError("REFUSED: selected SEC response bound is invalid")
    connection = http.client.HTTPSConnection("www.sec.gov", timeout=15)
    try:
        connection.request("GET", url.removeprefix("https://www.sec.gov"), headers=headers)
        response = connection.getresponse()
        if type(response.status) is not int:
            raise SecCompleteAcquisitionError("REFUSED: selected SEC HTTP status is malformed")
        if response.status != 200:
            # No redirect follow and no non-200 body read, including 403/429.
            return SecHttpResult(response.status, tuple(response.getheaders()), b"")
        response_headers = tuple(response.getheaders())
        mode, size = _selected_framing(response_headers, max_bytes)
        if mode == "chunked" and response.chunked is not True:
            raise SecCompleteAcquisitionError(
                "REFUSED: selected SEC response framing decoder disagrees"
            )
        try:
            if mode == "length":
                if size is None:
                    raise SecCompleteAcquisitionError(
                        "REFUSED: selected SEC length framing has no size"
                    )
                body = response.read(size)
                if len(body) != size:
                    raise SecCompleteAcquisitionError("REFUSED: selected SEC response was truncated")
            else:
                # HTTPResponse validates the chunk syntax and returns decoded
                # bytes. Read one over the cap and demand the terminal chunk.
                body = response.read(max_bytes + 1)
                if len(body) > max_bytes:
                    raise SecCompleteAcquisitionError("REFUSED: selected SEC chunked body exceeds its bound")
                if response.read(1) != b"" or not response.isclosed():
                    raise SecCompleteAcquisitionError("REFUSED: selected SEC chunked body is malformed")
        except http.client.HTTPException as exc:
            raise SecCompleteAcquisitionError("REFUSED: selected SEC response was truncated or malformed") from exc
        result = SecHttpResult(200, response_headers, body)
        _strict_selected_response(result, max_bytes=max_bytes)
        return result
    except http.client.HTTPException as exc:
        raise SecCompleteAcquisitionError(
            "REFUSED: selected SEC response was truncated or malformed"
        ) from exc
    finally:
        connection.close()


def _recover(path: Path, *, label: str, max_bytes: int,
             expected_sha256: str | None = None,
             expected_raw: bytes | None = None) -> bytes:
    try:
        return _read_recoverable(path, label=label, max_bytes=max_bytes,
                                 expected_sha256=expected_sha256,
                                 expected_raw=expected_raw)
    except (SecMaster82RunnerError, SecBulkSnapshotError, OSError) as exc:
        raise SecSelectedParentRunnerError(str(exc)) from exc


def _validate_real_reuses(rows: list[dict[str, object]]) -> None:
    # Empty means all selected parents will be requested. Any reuse must be
    # exactly the independently replayed nine-parent intersection; this keeps
    # the private test seam from laundering caller-supplied bytes as real.
    if rows and hash_payload(rows) != PINNED_REAL_REUSE_INVENTORY_SHA256:
        _refuse("real reuse inventory is not the pinned complete-pilot subset")


@dataclass(frozen=True)
class SelectedParentRequest:
    period: str
    accession_number: str
    form_type: str
    filing_date: str
    issuer_cik: str
    master_source_sha256: str
    parsed_lineage_hash: str
    url: str

    def to_payload(self) -> dict[str, str]:
        if type(self) is not SelectedParentRequest:
            _refuse("request must be an exact selected-parent record")
        values = {name: getattr(self, name) for name in (
            "period", "accession_number", "form_type", "filing_date", "issuer_cik",
            "master_source_sha256", "parsed_lineage_hash", "url",
        )}
        if any(type(value) is not str for value in values.values()):
            _refuse("request fields must be exact strings")
        if _SHA.fullmatch(self.parsed_lineage_hash) is None:
            _refuse("parsed lineage hash is invalid")
        try:
            SecCompleteSubmissionTarget(
                period=self.period, accession_number=self.accession_number,
                form_type=self.form_type, filing_date=self.filing_date,
                issuer_cik=self.issuer_cik,
                quarterly_index_sha256=self.master_source_sha256,
                complete_submission_url=self.url,
            )
        except ValueError as exc:
            raise SecSelectedParentRunnerError(str(exc)) from exc
        return values


@dataclass(frozen=True)
class SelectedParentReuse:
    accession_number: str
    object_sha256: str
    object_size_bytes: int
    prior_report_sha256: str

    def to_payload(self) -> dict[str, object]:
        if (type(self) is not SelectedParentReuse
                or type(self.accession_number) is not str
                or _ACCESSION.fullmatch(self.accession_number) is None
                or type(self.object_sha256) is not str
                or _SHA.fullmatch(self.object_sha256) is None
                or type(self.prior_report_sha256) is not str
                or _SHA.fullmatch(self.prior_report_sha256) is None
                or type(self.object_size_bytes) is not int
                or not 0 < self.object_size_bytes <= MAX_COMPLETE_TXT_BYTES):
            _refuse("prior parent reuse descriptor is invalid")
        return {"accession_number": self.accession_number,
                "object_sha256": self.object_sha256,
                "object_size_bytes": self.object_size_bytes,
                "prior_report_sha256": self.prior_report_sha256}


@dataclass(frozen=True)
class SelectedParentPlan:
    scope: str
    locator_manifest_sha256: str
    requests: tuple[SelectedParentRequest, ...]
    request_inventory_sha256: str
    reuses: tuple[SelectedParentReuse, ...] = ()
    _real_token: object | None = field(default=None, repr=False, compare=False)

    def to_payload(self) -> dict[str, object]:
        if (type(self) is not SelectedParentPlan
                or type(self.scope) is not str
                or self.scope not in {"synthetic_test_manifest", "ib1b_observed_noncanonical"}
                or type(self.locator_manifest_sha256) is not str
                or _SHA.fullmatch(self.locator_manifest_sha256) is None
                or type(self.requests) is not tuple or not self.requests
                or len(self.requests) > MAX_SELECTED
                or any(type(request) is not SelectedParentRequest for request in self.requests)
                or type(self.request_inventory_sha256) is not str
                or _SHA.fullmatch(self.request_inventory_sha256) is None
                or type(self.reuses) is not tuple
                or any(type(reuse) is not SelectedParentReuse for reuse in self.reuses)):
            _refuse("selected-parent plan identity or size is invalid")
        request_rows = [request.to_payload() for request in self.requests]
        if (tuple((row["period"], row["accession_number"]) for row in request_rows)
                != tuple(sorted({(row["period"], row["accession_number"]) for row in request_rows}))
                or len({row["accession_number"] for row in request_rows}) != len(request_rows)
                or hash_payload(request_rows) != self.request_inventory_sha256):
            _refuse("request inventory order, uniqueness, or digest changed")
        reuse_rows = [reuse.to_payload() for reuse in self.reuses]
        selected = {row["accession_number"] for row in request_rows}
        if (tuple(row["accession_number"] for row in reuse_rows)
                != tuple(sorted({row["accession_number"] for row in reuse_rows}))
                or any(row["accession_number"] not in selected for row in reuse_rows)):
            _refuse("reuse inventory is duplicated or outside the selected requests")
        if self.scope == "ib1b_observed_noncanonical" and (
            self._real_token is not _REAL_TOKEN
            or self.locator_manifest_sha256 != PINNED_REAL_LOCATOR_SHA256
            or self.request_inventory_sha256 != PINNED_REAL_REQUEST_INVENTORY_SHA256
            or len(self.requests) != MAX_SELECTED
            or sum(row["period"] == "2022Q4" for row in request_rows) != 4_613
            or sum(row["period"] == "2023Q1" for row in request_rows) != 4_724
        ):
            _refuse("real plan is not the validated two-quarter observed cohort")
        if self.scope == "ib1b_observed_noncanonical":
            _validate_real_reuses(reuse_rows)
        if self.scope == "synthetic_test_manifest" and self._real_token is not None:
            _refuse("synthetic plan carries a real-source token")
        return {"kind": RUNNER_VERSION, "scope": self.scope,
                "locator_manifest_sha256": self.locator_manifest_sha256,
                "request_inventory_sha256": self.request_inventory_sha256,
                "requests": request_rows, "reuses": reuse_rows,
                "source_authenticated": False, "canonical_evidence": False,
                "point_in_time_data": False, "research_looks": 0}


_REAL_TOKEN = object()


def _verify_exact_committed_code(commit: str) -> None:
    if type(commit) is not str or _COMMIT.fullmatch(commit) is None:
        _refuse("code commit must be a full lowercase Git SHA")
    root = Path(__file__).resolve().parents[1]
    paths = (
        "research/insider_buying_sec_selected_parent_runner.py",
        "research/insider_buying_sec_master82_runner.py",
        "research/insider_buying_sec_complete_acquisition.py",
        "research/insider_buying_sec_acquisition.py",
        "research/insider_buying_sec_complete_projection_adapter.py",
        "research/insider_buying/ib1b_observed_master_locators.py",
        "research/insider_buying/sec_complete_submission.py",
        "research/insider_buying/sec_bulk_snapshot.py",
        "data/hashing.py",
    )
    try:
        command = lambda *args: subprocess.check_output(args, cwd=root, stderr=subprocess.DEVNULL)
        top = command("git", "rev-parse", "--show-toplevel").decode().strip()
        branch = command("git", "branch", "--show-current").decode().strip()
        actual = command("git", "rev-parse", "HEAD").decode().strip()
        dirty = command("git", "status", "--porcelain=v1", "--untracked-files=all")
        if top != str(root) or branch != "codex/strategy-insider-buying" or actual != commit or dirty:
            _refuse("exact clean committed Insider lane is required")
        for relative in paths:
            if hash_bytes(command("git", "show", f"{commit}:{relative}")) != hash_bytes((root / relative).read_bytes()):
                _refuse("committed runner dependency differs on disk")
    except (OSError, UnicodeError, subprocess.CalledProcessError) as exc:
        raise SecSelectedParentRunnerError("REFUSED: exact code commit could not be verified") from exc


class _Events:
    def __init__(self, output: Path, identity: tuple[int, int], inventory_sha256: str) -> None:
        self.output = output
        self.identity = identity
        self.tail = inventory_sha256
        self.raw: list[bytes] = []

    def load(self) -> list[dict[str, object]]:
        descriptor = _open_output_directory(self.output, self.identity)
        try:
            names = [name for name in os.listdir(descriptor) if name.startswith("event-")]
            if len(names) > _MAX_EVENTS:
                _refuse("event count exceeds bound")
            parsed: list[tuple[int, str]] = []
            for name in names:
                match = _EVENT_NAME.fullmatch(name)
                if match is None:
                    _refuse("event filename is malformed")
                parsed.append((int(match.group(1)), name))
            parsed.sort()
            if [ordinal for ordinal, _ in parsed] != list(range(1, len(parsed) + 1)):
                _refuse("event sequence is incomplete")
            result = []
            for _, name in parsed:
                match = _EVENT_NAME.fullmatch(name)
                raw = _recover(self.output / name, label="selected-parent event",
                               max_bytes=_MAX_EVENT_BYTES, expected_sha256=match.group(2))
                event = _strict_json(raw, label="selected-parent event")
                if event.get("prev_sha256") != self.tail:
                    _refuse("event hash chain changed")
                self.raw.append(raw)
                self.tail = hash_bytes(raw)
                result.append(event)
            return result
        finally:
            os.close(descriptor)

    def append(self, payload: dict[str, object]) -> None:
        if len(self.raw) >= _MAX_EVENTS:
            _refuse("event count exceeds bound")
        raw = _bytes({**payload, "prev_sha256": self.tail})
        if len(raw) > _MAX_EVENT_BYTES:
            _refuse("event exceeds byte bound")
        digest = hash_bytes(raw)
        _publish_immutable(self.output, f"event-{len(self.raw)+1:06d}-{digest}.json",
                           raw, self.identity)
        self.raw.append(raw)
        self.tail = digest


def _read_object(output: Path, digest: str, size: int) -> bytes:
    if (type(digest) is not str or _SHA.fullmatch(digest) is None
            or type(size) is not int or not 0 < size <= MAX_COMPLETE_TXT_BYTES):
        _refuse("parent object descriptor is malformed")
    raw = _recover(output / "objects" / f"{digest}.bin",
                   label="selected-parent object", max_bytes=MAX_COMPLETE_TXT_BYTES,
                   expected_sha256=digest)
    if len(raw) != size:
        _refuse("parent object size changed")
    return raw


def _state(plan: SelectedParentPlan, events: list[dict[str, object]], output: Path
           ) -> tuple[list[dict[str, object]], dict[str, int], dict[str, object] | None,
                      dict[str, object] | None, int | None, str | None]:
    completed: list[dict[str, object]] = []
    attempts: dict[str, int] = {}
    pending_start: dict[str, object] | None = None
    pending_valid: dict[str, object] | None = None
    pending_missing: int | None = None
    terminal: str | None = None
    total = 0
    reused = {item.accession_number: item for item in plan.reuses}
    for event in events:
        if type(event) is not dict or type(event.get("kind")) is not str:
            _refuse("event shape is malformed")
        if terminal is not None or len(completed) >= len(plan.requests):
            _refuse("event follows a terminal or complete state")
        request = plan.requests[len(completed)]
        accession = request.accession_number
        kind = event["kind"]
        if event.get("accession_number") != accession:
            _refuse("event accession differs from selected order")
        if kind == "attempt-start":
            total += 1
            count = attempts.get(accession, 0) + 1
            if (pending_start is not None or pending_valid is not None or pending_missing is not None
                    or accession in reused or total > MAX_TOTAL_ATTEMPTS
                    or count > MAX_ATTEMPTS_PER_ARTIFACT
                    or set(event) != {"kind", "prev_sha256", "accession_number", "ordinal",
                                      "attempt", "url", "started_utc"}
                    or event.get("ordinal") != total or event.get("attempt") != count
                    or event.get("url") != request.url or type(event.get("started_utc")) is not str):
                _refuse("attempt reservation disagrees with frozen request or cap")
            attempts[accession] = count
            pending_start = event
        elif kind == "attempt-finish":
            if (pending_start is None or pending_valid is not None
                    or set(event) != {"kind", "prev_sha256", "accession_number", "ordinal",
                                      "outcome", "status", "body_sha256", "body_size_bytes", "finished_utc"}
                    or event.get("ordinal") != pending_start["ordinal"]
                    or type(event.get("finished_utc")) is not str):
                _refuse("attempt finish lacks an exact reservation")
            outcome = event.get("outcome")
            status = event.get("status")
            digest = event.get("body_sha256")
            size = event.get("body_size_bytes")
            if outcome == "valid_response":
                if (status != 200 or type(digest) is not str or _SHA.fullmatch(digest) is None
                        or type(size) is not int or not 0 < size <= MAX_COMPLETE_TXT_BYTES):
                    _refuse("valid response descriptor is malformed")
                pending_valid = event
            elif outcome == "network_error":
                if status is not None or digest is not None or size is not None:
                    _refuse("network error carries a body")
            elif outcome == "http_error":
                if type(status) is not int or status == 200 or digest is not None or size is not None:
                    _refuse("HTTP error descriptor is malformed")
                if status not in _RETRY_STATUSES | {404, 410}:
                    terminal = f"REFUSED: SEC returned HTTP {status}"
                elif status in {404, 410}:
                    pending_missing = status
            elif outcome == "transport_refusal":
                if status is not None or digest is not None or size is not None:
                    _refuse("transport refusal has a body")
                terminal = "REFUSED: SEC transport rejected response framing"
            elif outcome == "source_envelope_refusal":
                if status != 200 or digest is not None or size is not None:
                    _refuse("source envelope refusal descriptor is malformed")
                terminal = _ENVELOPE_REFUSAL
            else:
                _refuse("unknown attempt outcome")
            pending_start = None
        elif kind == "attempt-abandoned":
            if (pending_start is None or pending_valid is not None
                    or set(event) != {"kind", "prev_sha256", "accession_number", "ordinal"}
                    or event.get("ordinal") != pending_start["ordinal"]):
                _refuse("abandoned attempt lacks an unfinished reservation")
            pending_start = None
        elif kind == "response-object-missing":
            if (pending_valid is None or pending_start is not None
                    or set(event) != {"kind", "prev_sha256", "accession_number", "ordinal"}
                    or event.get("ordinal") != pending_valid["ordinal"]):
                _refuse("missing response object lacks a valid response")
            pending_valid = None
        elif kind == "item-complete":
            if (set(event) != {"kind", "prev_sha256", "accession_number", "source",
                              "object_sha256", "object_size_bytes", "prior_report_sha256"}
                    or pending_start is not None or pending_missing is not None):
                _refuse("completed item event is malformed")
            source = event.get("source")
            if source == "acquired":
                if (pending_valid is None or event.get("object_sha256") != pending_valid["body_sha256"]
                        or event.get("object_size_bytes") != pending_valid["body_size_bytes"]
                        or event.get("prior_report_sha256") is not None):
                    _refuse("acquired object differs from completed response")
            elif source == "reused":
                descriptor = reused.get(accession)
                if (pending_valid is not None or descriptor is None
                        or event.get("object_sha256") != descriptor.object_sha256
                        or event.get("object_size_bytes") != descriptor.object_size_bytes
                        or event.get("prior_report_sha256") != descriptor.prior_report_sha256):
                    _refuse("reused object differs from frozen prior descriptor")
            else:
                _refuse("completed item source is unknown")
            _read_object(output, event["object_sha256"], event["object_size_bytes"])
            completed.append(event)
            pending_valid = None
        elif kind == "item-not-found":
            if (set(event) != {"kind", "prev_sha256", "accession_number", "status"}
                    or pending_start is not None or pending_valid is not None
                    or pending_missing is None or event.get("status") != pending_missing):
                _refuse("not-found item transition is malformed")
            completed.append(event)
            pending_missing = None
        else:
            _refuse("event kind is unknown")
    return completed, attempts, pending_start, pending_valid, pending_missing, terminal


def _capacity(output: Path, identity: tuple[int, int], used_bytes: int) -> bool:
    descriptor = _open_output_directory(output, identity)
    try:
        info = os.statvfs(descriptor)
        available = info.f_bavail * info.f_frsize
        _check_output_directory(output, descriptor, identity)
        return (available >= MIN_FREE_BYTES + MAX_COMPLETE_TXT_BYTES + 4 * _MAX_EVENT_BYTES
                and used_bytes + MAX_COMPLETE_TXT_BYTES <= MAX_RUN_OBJECT_BYTES)
    finally:
        os.close(descriptor)


def _publish_same_or_new(output: Path, name: str, raw: bytes,
                         identity: tuple[int, int], *, max_bytes: int) -> Path:
    if len(raw) > max_bytes:
        _refuse("immutable publication exceeds its byte budget")
    try:
        return _publish_immutable(output, name, raw, identity)
    except FileExistsError:
        checked = _recover(output / name, label="selected-parent publication",
                           max_bytes=max_bytes, expected_raw=raw)
        if checked != raw:
            _refuse("immutable publication changed")
        return output / name


def _finalize(plan: SelectedParentPlan, output: Path, identity: tuple[int, int],
              code_commit: str, events: _Events, completed: list[dict[str, object]],
              attempts: dict[str, int], reason: str | None) -> Path:
    journal = b"".join(events.raw)
    _publish_same_or_new(output, "attempts.jsonl", journal, identity, max_bytes=_MAX_JOURNAL_BYTES)
    rows = []
    for index, request in enumerate(plan.requests):
        event = completed[index] if index < len(completed) else None
        row: dict[str, object] = {"accession_number": request.accession_number,
                                  "period": request.period, "attempts": attempts.get(request.accession_number, 0),
                                  "status": "not_attempted"}
        if event is not None and event["kind"] == "item-complete":
            row.update({"status": "raw_acquired_noncanonical", "source": event["source"],
                        "raw_object": {"relative_path": f'objects/{event["object_sha256"]}.bin',
                                       "sha256": event["object_sha256"],
                                       "size_bytes": event["object_size_bytes"]},
                        "prior_report_sha256": event["prior_report_sha256"]})
        elif event is not None:
            row.update({"status": "not_found", "http_status": event["status"]})
        elif index == len(completed) and reason is not None:
            row.update({"status": "refused", "reason": reason})
        rows.append(row)
    report = {"kind": RUNNER_VERSION, "source_scope": plan.scope,
              "locator_manifest_sha256": plan.locator_manifest_sha256,
              "request_inventory_sha256": plan.request_inventory_sha256,
              "capture_git_commit_verified": code_commit if plan.scope != "synthetic_test_manifest" else None,
              "attempt_journal_sha256": hash_bytes(journal),
              "attempt_event_count": len(events.raw), "attempt_count": sum(attempts.values()),
              "distinct_requested": len(attempts), "rows": rows,
              "halted_reason": reason,
              "complete_selected_raw_set_acquired": reason is None and len(completed) == len(plan.requests)
                and all(item["kind"] == "item-complete" for item in completed),
              "source_authenticated": False, "quarter_population_complete": False,
              "complete_parent_projection_verified": False,
              "acceptance_metadata_verified": False, "point_in_time_data": False,
              "canonical_evidence": False, "outcome_access_authorized": False,
              "qc_job_authorized": False, "broker_or_trading_authorized": False,
              "research_looks": 0, "authorized_outcome_looks": 0,
              "consumed_outcome_looks": 0}
    raw = _bytes(report)
    digest = hash_bytes(raw)
    name = f"sec-selected-parents-report-{digest}.json"
    _publish_same_or_new(output, name, raw, identity, max_bytes=_MAX_REPORT_BYTES)
    commit = {"kind": "sec-selected-parents-commit", "report_name": name,
              "report_sha256": digest, "attempt_journal_sha256": hash_bytes(journal)}
    _publish_same_or_new(output, "commit.json", _bytes(commit), identity, max_bytes=4096)
    return output / name


def _run_selected(plan: SelectedParentPlan, output_root: str | Path, *,
                  contact_email: str, capture_git_commit: str,
                  transport: Callable[[str, dict[str, str], int], SecHttpResult],
                  reused_bytes: Mapping[str, bytes] | None = None,
                  resume: bool = False) -> Path:
    """Synthetic-test seam. Real plans are constructed only by the public binder."""
    if os.name != "posix":
        _refuse("selected-parent resume requires POSIX directory handles")
    if (type(contact_email) is not str or len(contact_email) > 254
            or _CONTACT.fullmatch(contact_email) is None):
        _refuse("identifying SEC contact is required")
    if type(plan) is not SelectedParentPlan or not callable(transport):
        _refuse("exact selected plan and transport are required")
    frozen_plan = plan.to_payload()
    if plan.scope == "ib1b_observed_noncanonical":
        _verify_exact_committed_code(capture_git_commit)
    elif transport in {_sec_transport, _selected_sec_transport}:
        _refuse("synthetic plan cannot reach the real SEC transport")
    if type(capture_git_commit) is not str or _COMMIT.fullmatch(capture_git_commit) is None:
        _refuse("capture commit is invalid")
    supplied = {} if reused_bytes is None else dict(reused_bytes)
    expected_reuses = {item.accession_number: item for item in plan.reuses}
    if set(supplied) != set(expected_reuses):
        _refuse("prior bytes are missing or have an extra accession")
    for accession, raw in supplied.items():
        descriptor = expected_reuses[accession]
        if (type(raw) is not bytes or len(raw) != descriptor.object_size_bytes
                or hash_bytes(raw) != descriptor.object_sha256):
            _refuse("prior bytes differ from the frozen reuse descriptor")
    output = _plain_path(output_root, must_exist=resume)
    lane_root = Path(__file__).resolve().parents[1]
    _refuse_output_overlap(output, lane_root)
    if not resume:
        if output.exists():
            _refuse("fresh output root must not exist")
        output.mkdir(mode=0o700)
    current = output.lstat()
    if not stat.S_ISDIR(current.st_mode):
        _refuse("output root changed")
    identity = (current.st_dev, current.st_ino)
    try:
        lock = _RootLock(output, identity, resume=resume)
    except (SecMaster82RunnerError, OSError) as exc:
        raise SecSelectedParentRunnerError(str(exc)) from exc
    try:
        inventory = {**frozen_plan, "capture_git_commit": capture_git_commit,
                     "max_attempts_per_artifact": MAX_ATTEMPTS_PER_ARTIFACT,
                     "minimum_transport_completion_spacing_ns": MIN_REQUEST_INTERVAL_NS,
                     "max_success_bytes": MAX_COMPLETE_TXT_BYTES,
                     "max_run_object_bytes": MAX_RUN_OBJECT_BYTES,
                     "minimum_free_bytes": MIN_FREE_BYTES}
        inventory_raw = _bytes(inventory)
        if resume:
            _recover(output / "inventory.json", label="selected-parent inventory",
                     max_bytes=8 * 1024 * 1024, expected_raw=inventory_raw)
            if (output / "commit.json").exists():
                _refuse("committed selected-parent root cannot be resumed")
            _plain_path(output / "objects", must_exist=True)
        else:
            (output / "objects").mkdir(mode=0o700)
            _publish_immutable(output, "inventory.json", inventory_raw, identity)
        events = _Events(output, identity, hash_bytes(inventory_raw))
        prior = events.load() if resume else []
        completed, attempts, pending_start, pending_valid, pending_missing, terminal = _state(plan, prior, output)
        if pending_start is not None:
            events.append({"kind": "attempt-abandoned", "accession_number": pending_start["accession_number"],
                           "ordinal": pending_start["ordinal"]})
        if pending_valid is not None:
            accession = str(pending_valid["accession_number"])
            digest = str(pending_valid["body_sha256"])
            object_path = output / "objects" / f"{digest}.bin"
            if object_path.exists() or object_path.is_symlink():
                _read_object(output, digest, pending_valid["body_size_bytes"])
                events.append({"kind": "item-complete", "accession_number": accession,
                               "source": "acquired", "object_sha256": digest,
                               "object_size_bytes": pending_valid["body_size_bytes"],
                               "prior_report_sha256": None})
            else:
                events.append({"kind": "response-object-missing", "accession_number": accession,
                               "ordinal": pending_valid["ordinal"]})
        if pending_missing is not None:
            accession = plan.requests[len(completed)].accession_number
            events.append({"kind": "item-not-found", "accession_number": accession,
                           "status": pending_missing})
        replay = [_strict_json(raw, label="selected-parent event") for raw in events.raw]
        completed, attempts, _, _, _, terminal = _state(plan, replay, output)
        if resume and terminal is None and len(completed) < len(plan.requests):
            time.sleep((MIN_REQUEST_INTERVAL_NS + 1_000_000_000) / 1_000_000_000)
        used_bytes = sum(event["object_size_bytes"] for event in completed
                         if event["kind"] == "item-complete")
        last_completion_ns: int | None = None
        reason = terminal
        while reason is None and len(completed) < len(plan.requests):
            request = plan.requests[len(completed)]
            accession = request.accession_number
            reuse = expected_reuses.get(accession)
            if reuse is not None:
                if not _capacity(output, identity, used_bytes):
                    _refuse("capacity pause before prior-object publication; resume this root")
                descriptor = _store_object(output, supplied[accession], identity)
                events.append({"kind": "item-complete", "accession_number": accession,
                               "source": "reused", "object_sha256": descriptor["sha256"],
                               "object_size_bytes": descriptor["size_bytes"],
                               "prior_report_sha256": reuse.prior_report_sha256})
                completed.append(_strict_json(events.raw[-1], label="selected-parent event"))
                used_bytes += reuse.object_size_bytes
                continue
            used = attempts.get(accession, 0)
            if used >= MAX_ATTEMPTS_PER_ARTIFACT:
                reason = "REFUSED: selected parent attempt ceiling consumed"
                break
            if not _capacity(output, identity, used_bytes):
                _refuse("capacity pause before SEC dispatch; resume this root")
            started = time.monotonic_ns()
            earliest = max(started, last_completion_ns + MIN_REQUEST_INTERVAL_NS
                           if last_completion_ns is not None else started)
            if used:
                earliest = max(earliest, started + used * 1_000_000_000)
            remaining = earliest - time.monotonic_ns()
            if remaining > 0:
                time.sleep(remaining / 1_000_000_000)
            ordinal = sum(attempts.values()) + 1
            attempt = used + 1
            events.append({"kind": "attempt-start", "accession_number": accession,
                           "ordinal": ordinal, "attempt": attempt,
                           "url": request.url, "started_utc": _utc()})
            if time.monotonic_ns() < earliest:
                _refuse("actual SEC dispatch pacing was too early")
            headers = {"User-Agent": f"InsiderBuyingResearch/0.1 ({contact_email})",
                       "Accept": "*/*", "Accept-Encoding": "identity", "Connection": "close"}
            try:
                result = transport(request.url, headers, MAX_COMPLETE_TXT_BYTES)
            except (OSError, http.client.HTTPException):
                last_completion_ns = time.monotonic_ns()
                events.append({"kind": "attempt-finish", "accession_number": accession,
                               "ordinal": ordinal, "outcome": "network_error", "status": None,
                               "body_sha256": None, "body_size_bytes": None,
                               "finished_utc": _utc()})
                attempts[accession] = attempt
                continue
            except SecCompleteAcquisitionError:
                last_completion_ns = time.monotonic_ns()
                events.append({"kind": "attempt-finish", "accession_number": accession,
                               "ordinal": ordinal, "outcome": "transport_refusal", "status": None,
                               "body_sha256": None, "body_size_bytes": None,
                               "finished_utc": _utc()})
                attempts[accession] = attempt
                reason = "REFUSED: SEC transport rejected response framing"
                break
            last_completion_ns = time.monotonic_ns()
            if type(result) is not SecHttpResult or type(result.status) is not int:
                events.append({"kind": "attempt-finish", "accession_number": accession,
                               "ordinal": ordinal, "outcome": "transport_refusal", "status": None,
                               "body_sha256": None, "body_size_bytes": None,
                               "finished_utc": _utc()})
                attempts[accession] = attempt
                reason = "REFUSED: SEC transport rejected response framing"
                break
            if result.status != 200:
                events.append({"kind": "attempt-finish", "accession_number": accession,
                               "ordinal": ordinal, "outcome": "http_error", "status": result.status,
                               "body_sha256": None, "body_size_bytes": None,
                               "finished_utc": _utc()})
                attempts[accession] = attempt
                if result.status in {404, 410}:
                    events.append({"kind": "item-not-found", "accession_number": accession,
                                   "status": result.status})
                    completed.append(_strict_json(events.raw[-1], label="selected-parent event"))
                elif result.status not in _RETRY_STATUSES:
                    reason = f"REFUSED: SEC returned HTTP {result.status}"
                continue
            try:
                raw = _strict_selected_response(result, max_bytes=MAX_COMPLETE_TXT_BYTES)
            except SecCompleteAcquisitionError:
                events.append({"kind": "attempt-finish", "accession_number": accession,
                               "ordinal": ordinal, "outcome": "transport_refusal", "status": None,
                               "body_sha256": None, "body_size_bytes": None,
                               "finished_utc": _utc()})
                attempts[accession] = attempt
                reason = "REFUSED: SEC transport rejected response framing"
                break
            # A framed HTTP 200 can still be an HTML challenge or error page.
            # This only checks the minimal SEC text-submission envelope; it is
            # not XML extraction, source authentication, or PIT validation.
            if not raw.startswith(b"<SEC-DOCUMENT>"):
                events.append({"kind": "attempt-finish", "accession_number": accession,
                               "ordinal": ordinal, "outcome": "source_envelope_refusal",
                               "status": 200, "body_sha256": None, "body_size_bytes": None,
                               "finished_utc": _utc()})
                attempts[accession] = attempt
                reason = _ENVELOPE_REFUSAL
                break
            digest = hash_bytes(raw)
            events.append({"kind": "attempt-finish", "accession_number": accession,
                           "ordinal": ordinal, "outcome": "valid_response", "status": 200,
                           "body_sha256": digest, "body_size_bytes": len(raw),
                           "finished_utc": _utc()})
            attempts[accession] = attempt
            descriptor = _store_object(output, raw, identity)
            events.append({"kind": "item-complete", "accession_number": accession,
                           "source": "acquired", "object_sha256": descriptor["sha256"],
                           "object_size_bytes": descriptor["size_bytes"],
                           "prior_report_sha256": None})
            completed.append(_strict_json(events.raw[-1], label="selected-parent event"))
            used_bytes += len(raw)
        replay = [_strict_json(raw, label="selected-parent event") for raw in events.raw]
        checked, final_attempts, _, _, _, terminal_state = _state(plan, replay, output)
        if checked != completed or (reason is not None and terminal_state not in {None, reason}):
            _refuse("final journal replay disagrees with in-memory result")
        if plan.scope == "ib1b_observed_noncanonical":
            _verify_exact_committed_code(capture_git_commit)
        return _finalize(plan, output, identity, capture_git_commit,
                         events, checked, final_attempts, reason)
    finally:
        lock.close()


def run_observed_selected_parent_acquisition(
    quarter_inputs: object, output_root: str | Path, *, contact_email: str,
    capture_git_commit: str, prior_complete_pilot_root: str | Path | None = None,
    resume: bool = False,
) -> Path:
    """Bind two validated source quarters, optionally reuse exact pilot parents.

    This is the only real transport entry. The caller must supply both loaded
    parsed IB-1B quarters and parsed master receipts; a persisted digest alone
    cannot authorize a URL. The complete-pilot loader validates its own source
    tree before any of its bytes can be reused. No outcome/QC path is called.
    """
    _verify_exact_committed_code(capture_git_commit)
    from research.insider_buying.ib1b_observed_master_locators import (
        ObservedMasterLocatorQuarterInput,
        build_ib1b_observed_master_locator_manifest,
    )
    from research.insider_buying_sec_complete_projection_adapter import (
        SecCompletePilotProjectionReceipt, load_fixed_complete_pilot,
    )

    if (type(quarter_inputs) is not tuple or len(quarter_inputs) != 2
            or any(type(item) is not ObservedMasterLocatorQuarterInput for item in quarter_inputs)):
        _refuse("the two exact caller-loaded locator quarter inputs are required")
    manifest = build_ib1b_observed_master_locator_manifest(quarter_inputs)
    manifest.verify_digest()
    requests = tuple(
        SelectedParentRequest(
            period=quarter.period, accession_number=item.accession_number,
            form_type=item.form_type, filing_date=item.filing_date,
            issuer_cik=item.issuer_cik,
            master_source_sha256=quarter.master_source_sha256,
            parsed_lineage_hash=quarter.parsed_lineage_hash,
            url="https://www.sec.gov/Archives/" + item.archive_path,
        )
        for quarter in manifest.quarters for item in quarter.locators
    )
    if (manifest.content_sha256 != PINNED_REAL_LOCATOR_SHA256
            or manifest.selected_count != MAX_SELECTED or len(requests) != MAX_SELECTED):
        _refuse("selected source cohort is not the measured exact 9,337")
    reuse_bytes: dict[str, bytes] = {}
    reuse: list[SelectedParentReuse] = []
    if prior_complete_pilot_root is not None:
        prior = _plain_path(prior_complete_pilot_root, must_exist=True)
        output = _plain_path(output_root, must_exist=resume)
        _refuse_output_overlap(output, prior)
        pilot = load_fixed_complete_pilot(prior)
        if type(pilot) is not SecCompletePilotProjectionReceipt:
            _refuse("prior complete-pilot loader did not return its exact receipt")
        pilot_payload = pilot.to_payload()
        if (pilot_payload["authority"]["input_scope"]
                != "retained_noncanonical_complete_pilot"):
            _refuse("prior complete-pilot receipt is not the pinned real source")
        by_accession = {request.accession_number: request for request in requests}
        for projection in pilot.projections:
            projection_payload = projection.to_payload()
            request = by_accession.get(projection.target.accession_number)
            if request is None:
                continue
            if (projection.target.period != request.period
                    or projection.target.form_type != request.form_type
                    or projection.target.filing_date != request.filing_date
                    or projection.target.issuer_cik != request.issuer_cik
                    or projection.target.quarterly_index_sha256 != request.master_source_sha256
                    or projection.target.complete_submission_url != request.url):
                continue
            raw = projection.raw_bytes
            if (hash_bytes(raw) != projection_payload["raw_parent"]["sha256"]
                    or len(raw) != projection_payload["raw_parent"]["size_bytes"]):
                _refuse("prior parent bytes differ from the verified pilot projection")
            reuse_bytes[request.accession_number] = raw
            reuse.append(SelectedParentReuse(
                accession_number=request.accession_number,
                object_sha256=hash_bytes(raw), object_size_bytes=len(raw),
                prior_report_sha256=pilot.report_sha256,
            ))
    plan = SelectedParentPlan(
        scope="ib1b_observed_noncanonical",
        locator_manifest_sha256=manifest.content_sha256,
        requests=requests,
        request_inventory_sha256=hash_payload([request.to_payload() for request in requests]),
        reuses=tuple(sorted(reuse, key=lambda item: item.accession_number)),
        _real_token=_REAL_TOKEN,
    )
    plan.to_payload()
    return _run_selected(plan, output_root, contact_email=contact_email,
                         capture_git_commit=capture_git_commit,
                         transport=_selected_sec_transport, reused_bytes=reuse_bytes,
                         resume=resume)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locator-manifest-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--capture-git-commit", required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    _refuse("CLI cannot load source quarters; call the source-bound API explicitly")


if __name__ == "__main__":  # pragma: no cover - explicit operator launch only
    raise SystemExit(main())
