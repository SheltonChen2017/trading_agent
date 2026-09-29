"""Read-only, noncanonical replay of a complete selected-parent acquisition root.

The acquisition root is never an IB-1C, canonical, or PIT source merely because
its local hashes agree.  The real entry also rebinds the exact two parsed IB-1B
quarters and master indexes; its 9,337 selected accessions remain a retrieval
priority, not the complete 99,394-accession Form 4/4-A population.  This file
does no network, publication, outcome, QC, broker, or trading operation.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import stat
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying.ib1b_observed_master_locators import (
    ObservedMasterLocatorQuarterInput,
    ObservedMasterLocatorError,
    build_ib1b_observed_master_locator_manifest,
)
from research.insider_buying.sec_complete_submission import (
    MAX_COMPLETE_SUBMISSION_BYTES,
    SecCompleteSubmissionError,
    SecCompleteSubmissionTarget,
    project_sec_complete_submission,
)
from research.insider_buying_sec_complete_projection_adapter import (
    SecCompletePilotAdapterError,
    _PinnedRoot,
    _plain_root,
)
from research.insider_buying_sec_selected_parent_runner import (
    SelectedParentPlan,
    SelectedParentRequest,
    SelectedParentReuse,
)


ADAPTER_VERSION = "INSETF-SEC-SELECTED-PARENTS-OFFLINE-REPLAY-v1"
_RUNNER_VERSION = "INSETF-SEC-SELECTED-PARENTS-RESUMABLE-v1"
_REAL_LOCATOR_SHA256 = "7084c851a3420e38b570b13396eb8e768930249d64c90e9b2975b1355800cb9b"
_REAL_REQUEST_SHA256 = "8e251c91ff89b87f6f3e83b8f968d63b83fe5f5e19e6d48a650afbed06b7742d"
_REAL_REUSE_SHA256 = "6c8fe9038d98a8278e7bd9955992ff719e4fa6665beab16075d8f60b0d99809e"
_MAX_SELECTED = 9_337
_MAX_EVENTS = _MAX_SELECTED * 3 * 3 + _MAX_SELECTED + 8
_EVENT_NAME = re.compile(r"event-([0-9]{6})-([0-9a-f]{64})\.json\Z")
_REPORT_NAME = re.compile(r"sec-selected-parents-report-([0-9a-f]{64})\.json\Z")
_OBJECT_NAME = re.compile(r"([0-9a-f]{64})\.bin\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}\+00:00\Z")
_RETRY_STATUSES = {500, 502, 503, 504}
_INVENTORY_FIELDS = {
    "kind", "scope", "locator_manifest_sha256", "request_inventory_sha256",
    "requests", "reuses", "source_authenticated", "canonical_evidence",
    "point_in_time_data", "research_looks", "capture_git_commit",
    "max_attempts_per_artifact", "minimum_transport_completion_spacing_ns",
    "max_success_bytes", "max_run_object_bytes", "minimum_free_bytes",
}
_REPORT_FIELDS = {
    "kind", "source_scope", "locator_manifest_sha256", "request_inventory_sha256",
    "capture_git_commit_verified", "attempt_journal_sha256", "attempt_event_count",
    "attempt_count", "distinct_requested", "rows", "halted_reason",
    "complete_selected_raw_set_acquired", "source_authenticated",
    "quarter_population_complete", "complete_parent_projection_verified",
    "acceptance_metadata_verified", "point_in_time_data", "canonical_evidence",
    "outcome_access_authorized", "qc_job_authorized", "broker_or_trading_authorized",
    "research_looks", "authorized_outcome_looks", "consumed_outcome_looks",
}
_FALSE_REPORT_FIELDS = (
    "source_authenticated", "quarter_population_complete",
    "complete_parent_projection_verified", "acceptance_metadata_verified",
    "point_in_time_data", "canonical_evidence", "outcome_access_authorized",
    "qc_job_authorized", "broker_or_trading_authorized",
)


class SecSelectedParentProjectionError(ValueError):
    """An exact selected acquisition root or source binding failed closed."""


_LOADER_TOKEN = object()


def _refuse(message: str) -> None:
    raise SecSelectedParentProjectionError(f"REFUSED: {message}")


def _json(raw: bytes, *, label: str) -> dict[str, object]:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                _refuse(f"{label} repeats a key")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                           parse_constant=lambda _: _refuse(f"{label} is nonfinite"))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise SecSelectedParentProjectionError(f"REFUSED: {label} is not strict JSON") from exc
    if type(value) is not dict or (canonical_json(value) + "\n").encode() != raw:
        _refuse(f"{label} is not canonical JSON plus LF")
    return value


def _time(value: object) -> None:
    if type(value) is not str or _UTC.fullmatch(value) is None:
        _refuse("event timestamp is not canonical UTC")
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SecSelectedParentProjectionError("REFUSED: event UTC timestamp is invalid") from exc
    if stamp.utcoffset() != timedelta(0) or stamp.isoformat(timespec="microseconds") != value:
        _refuse("event timestamp is not canonical UTC")


@dataclass(frozen=True, slots=True)
class SelectedParentProjectionRow:
    period: str
    accession_number: str
    form_type: str
    submission_row_id: str | None
    source: str
    raw_parent_sha256: str
    raw_parent_size_bytes: int
    header_sha256: str
    xml_sha256: str
    projection_sha256: str
    accepted_at_raw: str
    header_owner_ciks: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "period": self.period, "accession_number": self.accession_number,
            "form_type": self.form_type, "submission_row_id": self.submission_row_id,
            "source": self.source, "raw_parent_sha256": self.raw_parent_sha256,
            "raw_parent_size_bytes": self.raw_parent_size_bytes,
            "header_sha256": self.header_sha256, "xml_sha256": self.xml_sha256,
            "projection_sha256": self.projection_sha256,
            "accepted_at_raw": self.accepted_at_raw,
            "header_owner_ciks": list(self.header_owner_ciks),
            "amendment_link_verified": False,
            "multi_owner_economic_attribution_verified": False,
        }


@dataclass(frozen=True, slots=True)
class SelectedParentProjectionReceipt:
    source_scope: str
    locator_manifest_sha256: str
    request_inventory_sha256: str
    inventory_sha256: str
    attempt_journal_sha256: str
    report_sha256: str
    capture_git_commit: str
    rows: tuple[SelectedParentProjectionRow, ...]
    lineage_sha256: str
    _loader_token: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._loader_token is not _LOADER_TOKEN:
            _refuse("projection receipt must come from the pinned loader")

    @property
    def amendment_count(self) -> int:
        return sum(row.form_type == "4/A" for row in self.rows)

    @property
    def multi_owner_count(self) -> int:
        return sum(len(row.header_owner_ciks) > 1 for row in self.rows)

    @property
    def projections_verified(self) -> bool:
        return True

    @property
    def quarter_population_complete(self) -> bool:
        return False

    @property
    def acceptance_timezone_verified(self) -> bool:
        return False

    @property
    def amendment_links_verified(self) -> bool:
        return False

    @property
    def multi_owner_economic_attribution_verified(self) -> bool:
        return False

    @property
    def canonical_evidence(self) -> bool:
        return False

    @property
    def point_in_time_data(self) -> bool:
        return False

    @property
    def research_looks(self) -> int:
        return 0

    def to_payload(self) -> dict[str, object]:
        payload = {
            "version": ADAPTER_VERSION, "source_scope": self.source_scope,
            "locator_manifest_sha256": self.locator_manifest_sha256,
            "request_inventory_sha256": self.request_inventory_sha256,
            "inventory_sha256": self.inventory_sha256,
            "attempt_journal_sha256": self.attempt_journal_sha256,
            "report_sha256": self.report_sha256,
            "capture_git_commit": self.capture_git_commit,
            "rows": [row.to_payload() for row in self.rows],
            "projections_verified": True,
            "quarter_population_complete": False,
            "acceptance_timezone_verified": False,
            "amendment_links_verified": False,
            "multi_owner_economic_attribution_verified": False,
            "canonical_evidence": False, "point_in_time_data": False,
            "source_authenticated": False, "outcome_access_authorized": False,
            "qc_job_authorized": False, "research_looks": 0,
        }
        if hash_payload(payload) != self.lineage_sha256:
            _refuse("receipt lineage changed")
        return payload


def _expected_real(quarter_inputs: tuple[ObservedMasterLocatorQuarterInput, ...]
                   ) -> tuple[str, str, tuple[dict[str, str], ...], tuple[str | None, ...]]:
    if type(quarter_inputs) is not tuple or len(quarter_inputs) != 2:
        _refuse("two exact source-quarter inputs are required")
    try:
        manifest = build_ib1b_observed_master_locator_manifest(quarter_inputs)
        manifest.verify_digest()
    except ObservedMasterLocatorError as exc:
        raise SecSelectedParentProjectionError(str(exc)) from exc
    requests: list[dict[str, str]] = []
    submission_ids: list[str] = []
    for quarter in manifest.quarters:
        for locator in quarter.locators:
            request = SelectedParentRequest(
                period=quarter.period, accession_number=locator.accession_number,
                form_type=locator.form_type, filing_date=locator.filing_date,
                issuer_cik=locator.issuer_cik,
                master_source_sha256=quarter.master_source_sha256,
                parsed_lineage_hash=quarter.parsed_lineage_hash,
                url="https://www.sec.gov/Archives/" + locator.archive_path,
            )
            requests.append(request.to_payload())
            submission_ids.append(locator.submission_row_id)
    if (manifest.content_sha256 != _REAL_LOCATOR_SHA256
            or manifest.selected_count != _MAX_SELECTED
            or hash_payload(requests) != _REAL_REQUEST_SHA256):
        _refuse("observed source quarters are not the pinned selected cohort")
    return ("ib1b_observed_noncanonical", manifest.content_sha256,
            tuple(requests), tuple(submission_ids))


def _expected_synthetic(plan: SelectedParentPlan
                        ) -> tuple[str, str, tuple[dict[str, str], ...], tuple[str | None, ...]]:
    if type(plan) is not SelectedParentPlan or plan.scope != "synthetic_test_manifest":
        _refuse("synthetic replay requires an exact synthetic plan")
    try:
        payload = plan.to_payload()
    except ValueError as exc:
        raise SecSelectedParentProjectionError(str(exc)) from exc
    return ("synthetic_test_manifest", payload["locator_manifest_sha256"],
            tuple(payload["requests"]), (None,) * len(plan.requests))


def _check_inventory(value: dict[str, object], *, scope: str, locator_sha: str,
                     requests: tuple[dict[str, str], ...],
                     expected_reuses: tuple[dict[str, object], ...] | None
                     ) -> tuple[dict[str, dict[str, object]], str]:
    if (set(value) != _INVENTORY_FIELDS or value["kind"] != _RUNNER_VERSION
            or value["scope"] != scope
            or value["locator_manifest_sha256"] != locator_sha
            or value["request_inventory_sha256"] != hash_payload(list(requests))
            or value["requests"] != list(requests)
            or value["source_authenticated"] is not False
            or value["canonical_evidence"] is not False
            or value["point_in_time_data"] is not False
            or type(value["research_looks"]) is not int or value["research_looks"] != 0
            or type(value["capture_git_commit"]) is not str
            or _COMMIT.fullmatch(value["capture_git_commit"]) is None
            or type(value["max_attempts_per_artifact"]) is not int
            or value["max_attempts_per_artifact"] != 3
            or type(value["minimum_transport_completion_spacing_ns"]) is not int
            or value["minimum_transport_completion_spacing_ns"] != 500_000_000
            or type(value["max_success_bytes"]) is not int
            or value["max_success_bytes"] != MAX_COMPLETE_SUBMISSION_BYTES
            or type(value["max_run_object_bytes"]) is not int
            or value["max_run_object_bytes"] != 48 * 1024**3
            or type(value["minimum_free_bytes"]) is not int
            or value["minimum_free_bytes"] != 8 * 1024**3
            or type(value["reuses"]) is not list):
        _refuse("inventory scope, source identity, or authority changed")
    reuses = value["reuses"]
    if expected_reuses is not None and reuses != list(expected_reuses):
        _refuse("synthetic reuse inventory differs from expected plan")
    try:
        validated = [SelectedParentReuse(**row).to_payload() for row in reuses]
    except (TypeError, ValueError) as exc:
        raise SecSelectedParentProjectionError("REFUSED: reuse descriptor is malformed") from exc
    if validated != reuses or [row["accession_number"] for row in reuses] != sorted({row["accession_number"] for row in reuses}):
        _refuse("reuse descriptors repeat or are unordered")
    selected = {row["accession_number"] for row in requests}
    if any(row["accession_number"] not in selected for row in reuses):
        _refuse("reuse descriptor is outside the selected source set")
    if scope == "ib1b_observed_noncanonical" and reuses and hash_payload(reuses) != _REAL_REUSE_SHA256:
        _refuse("real reuse descriptors differ from the pinned pilot subset")
    return {row["accession_number"]: row for row in reuses}, value["capture_git_commit"]


def _events(root: _PinnedRoot, inventory_sha: str,
            requests: tuple[dict[str, str], ...],
            reuses: dict[str, dict[str, object]], names: set[str]
            ) -> tuple[list[dict[str, object]], bytes, list[dict[str, object]], dict[str, int]]:
    event_names = sorted(name for name in names if name.startswith("event-"))
    if (len(event_names) > _MAX_EVENTS
            or any(_EVENT_NAME.fullmatch(name) is None for name in event_names)
            or [int(_EVENT_NAME.fullmatch(name).group(1)) for name in event_names]
            != list(range(1, len(event_names) + 1))):
        _refuse("event names or sequence changed")
    chain = inventory_sha
    raws: list[bytes] = []
    parsed: list[dict[str, object]] = []
    for name in event_names:
        raw = root.read(name, label="selected event", max_bytes=2048)
        if hash_bytes(raw) != _EVENT_NAME.fullmatch(name).group(2):
            _refuse("event filename hash changed")
        event = _json(raw, label="selected event")
        if event.get("prev_sha256") != chain:
            _refuse("event chain changed")
        chain = hash_bytes(raw)
        raws.append(raw)
        parsed.append(event)
    journal = root.read("attempts.jsonl", label="selected journal", max_bytes=256 * 1024**2)
    if journal != b"".join(raws):
        _refuse("attempt journal differs from event chain")
    completed: list[dict[str, object]] = []
    attempts: dict[str, int] = {}
    pending_start: dict[str, object] | None = None
    pending_valid: dict[str, object] | None = None
    ordinal = 0
    used_reuses: set[str] = set()
    for event in parsed:
        if len(completed) >= len(requests) or type(event.get("kind")) is not str:
            _refuse("event follows completion or has malformed kind")
        request = requests[len(completed)]
        accession = request["accession_number"]
        if event.get("accession_number") != accession:
            _refuse("event accession differs from selected source order")
        kind = event["kind"]
        if kind == "attempt-start":
            ordinal += 1
            count = attempts.get(accession, 0) + 1
            if (pending_start is not None or pending_valid is not None
                    or accession in reuses or ordinal > _MAX_SELECTED * 3
                    or count > 3
                    or set(event) != {"kind", "prev_sha256", "accession_number", "ordinal", "attempt", "url", "started_utc"}
                    or event["ordinal"] != ordinal or event["attempt"] != count
                    or event["url"] != request["url"]):
                _refuse("attempt reservation differs from selected source")
            _time(event["started_utc"])
            attempts[accession] = count
            pending_start = event
        elif kind == "attempt-finish":
            if (pending_start is None or pending_valid is not None
                    or set(event) != {"kind", "prev_sha256", "accession_number", "ordinal", "outcome", "status", "body_sha256", "body_size_bytes", "finished_utc"}
                    or event["ordinal"] != pending_start["ordinal"]):
                _refuse("attempt completion lacks an exact reservation")
            _time(event["finished_utc"])
            outcome = event["outcome"]
            if outcome == "valid_response":
                if (event["status"] != 200 or type(event["body_sha256"]) is not str
                        or _SHA.fullmatch(event["body_sha256"]) is None
                        or type(event["body_size_bytes"]) is not int
                        or not 0 < event["body_size_bytes"] <= MAX_COMPLETE_SUBMISSION_BYTES):
                    _refuse("valid response descriptor changed")
                pending_valid = event
            elif outcome == "network_error":
                if any(event[name] is not None for name in ("status", "body_sha256", "body_size_bytes")):
                    _refuse("network failure carries response bytes")
            elif outcome == "http_error":
                if (type(event["status"]) is not int
                        or event["status"] not in _RETRY_STATUSES
                        or event["body_sha256"] is not None
                        or event["body_size_bytes"] is not None):
                    _refuse("nonretryable HTTP result cannot complete selected set")
            else:
                _refuse("terminal or unknown attempt outcome cannot complete selected set")
            pending_start = None
        elif kind == "attempt-abandoned":
            if (pending_start is None or pending_valid is not None
                    or set(event) != {"kind", "prev_sha256", "accession_number", "ordinal"}
                    or event["ordinal"] != pending_start["ordinal"]):
                _refuse("abandoned attempt is not a reserved attempt")
            pending_start = None
        elif kind == "response-object-missing":
            if (pending_valid is None or pending_start is not None
                    or set(event) != {"kind", "prev_sha256", "accession_number", "ordinal"}
                    or event["ordinal"] != pending_valid["ordinal"]):
                _refuse("missing object event lacks valid response")
            pending_valid = None
        elif kind == "item-complete":
            if (pending_start is not None
                    or set(event) != {"kind", "prev_sha256", "accession_number", "source", "object_sha256", "object_size_bytes", "prior_report_sha256"}
                    or type(event["object_sha256"]) is not str
                    or _SHA.fullmatch(event["object_sha256"]) is None
                    or type(event["object_size_bytes"]) is not int
                    or not 0 < event["object_size_bytes"] <= MAX_COMPLETE_SUBMISSION_BYTES):
                _refuse("completed object event is malformed")
            if event["source"] == "acquired":
                if (pending_valid is None
                        or event["object_sha256"] != pending_valid["body_sha256"]
                        or event["object_size_bytes"] != pending_valid["body_size_bytes"]
                        or event["prior_report_sha256"] is not None):
                    _refuse("completed acquisition differs from valid response")
            elif event["source"] == "reused":
                reuse = reuses.get(accession)
                if (pending_valid is not None or reuse is None
                        or event["object_sha256"] != reuse["object_sha256"]
                        or event["object_size_bytes"] != reuse["object_size_bytes"]
                        or event["prior_report_sha256"] != reuse["prior_report_sha256"]):
                    _refuse("reused object differs from frozen descriptor")
                used_reuses.add(accession)
            else:
                _refuse("completed object source is unknown")
            completed.append(event)
            pending_valid = None
        else:
            _refuse("incomplete or unknown item event cannot complete selected set")
    if (len(completed) != len(requests) or pending_start is not None
            or pending_valid is not None or used_reuses != set(reuses)):
        _refuse("selected acquisition root is incomplete")
    return parsed, journal, completed, attempts


def _replay(root_path: str | Path, *, scope: str, locator_sha: str,
            requests: tuple[dict[str, str], ...],
            submission_ids: tuple[str | None, ...],
            expected_reuses: tuple[dict[str, object], ...] | None
            ) -> SelectedParentProjectionReceipt:
    if not requests or len(requests) > _MAX_SELECTED or len(submission_ids) != len(requests):
        _refuse("expected selected source inventory is empty or unbounded")
    try:
        plain = _plain_root(root_path)
        with _PinnedRoot(plain) as root:
            lock_fd = os.open("run.lock", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root.root_fd)
            try:
                lock_info = os.fstat(lock_fd)
                if (not stat.S_ISREG(lock_info.st_mode) or lock_info.st_nlink != 1
                        or lock_info.st_size != 0):
                    _refuse("selected root lock is malformed")
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                except OSError as exc:
                    raise SecSelectedParentProjectionError("REFUSED: selected root is in use") from exc
                names = root.names()
                inventory_raw = root.read("inventory.json", label="selected inventory", max_bytes=8 * 1024**2)
                inventory = _json(inventory_raw, label="selected inventory")
                reuses, capture_commit = _check_inventory(
                    inventory, scope=scope, locator_sha=locator_sha,
                    requests=requests, expected_reuses=expected_reuses,
                )
                inventory_sha = hash_bytes(inventory_raw)
                events, journal, completed, attempts = _events(
                    root, inventory_sha, requests, reuses, names
                )
                journal_sha = hash_bytes(journal)
                commit = _json(root.read("commit.json", label="selected commit", max_bytes=4096), label="selected commit")
                if (set(commit) != {"kind", "report_name", "report_sha256", "attempt_journal_sha256"}
                        or commit["kind"] != "sec-selected-parents-commit"
                        or type(commit["report_name"]) is not str
                        or _REPORT_NAME.fullmatch(commit["report_name"]) is None
                        or commit["report_sha256"] != _REPORT_NAME.fullmatch(commit["report_name"]).group(1)
                        or commit["attempt_journal_sha256"] != journal_sha):
                    _refuse("selected commit does not bind report and journal")
                report_raw = root.read(commit["report_name"], label="selected report", max_bytes=32 * 1024**2)
                if hash_bytes(report_raw) != commit["report_sha256"]:
                    _refuse("selected report hash changed")
                report = _json(report_raw, label="selected report")
                if (set(report) != _REPORT_FIELDS or report["kind"] != _RUNNER_VERSION
                        or report["source_scope"] != scope
                        or report["locator_manifest_sha256"] != locator_sha
                        or report["request_inventory_sha256"] != hash_payload(list(requests))
                        or report["capture_git_commit_verified"] != (
                            capture_commit if scope == "ib1b_observed_noncanonical" else None
                        )
                        or report["attempt_journal_sha256"] != journal_sha
                        or type(report["attempt_event_count"]) is not int
                        or report["attempt_event_count"] != len(events)
                        or type(report["attempt_count"]) is not int
                        or report["attempt_count"] != sum(attempts.values())
                        or type(report["distinct_requested"]) is not int
                        or report["distinct_requested"] != len(attempts)
                        or report["halted_reason"] is not None
                        or report["complete_selected_raw_set_acquired"] is not True
                        or any(report[name] is not False for name in _FALSE_REPORT_FIELDS)
                        or any(type(report[name]) is not int or report[name] != 0 for name in (
                            "research_looks", "authorized_outcome_looks", "consumed_outcome_looks"
                        ))
                        or type(report["rows"]) is not list
                        or len(report["rows"]) != len(requests)):
                    _refuse("selected report source, count, or authority changed")
                expected_names = {"run.lock", "objects", "inventory.json", "attempts.jsonl",
                                  "commit.json", commit["report_name"]}
                expected_names.update(name for name in names if name.startswith("event-"))
                if names != expected_names:
                    _refuse("selected root has an unknown or missing member")
                expected_objects = {
                    f'{event["object_sha256"]}.bin' for event in completed
                }
                if root.names(objects=True) != expected_objects:
                    _refuse("selected object directory has extra or missing objects")
                rows: list[SelectedParentProjectionRow] = []
                for request, submission_id, event, reported in zip(
                    requests, submission_ids, completed, report["rows"], strict=True
                ):
                    descriptor = {"relative_path": f'objects/{event["object_sha256"]}.bin',
                                  "sha256": event["object_sha256"],
                                  "size_bytes": event["object_size_bytes"]}
                    if (type(reported) is not dict
                            or set(reported) != {"accession_number", "period", "attempts", "status", "source", "raw_object", "prior_report_sha256"}
                            or reported["accession_number"] != request["accession_number"]
                            or reported["period"] != request["period"]
                            or type(reported["attempts"]) is not int
                            or reported["attempts"] != attempts.get(request["accession_number"], 0)
                            or reported["status"] != "raw_acquired_noncanonical"
                            or reported["source"] != event["source"]
                            or reported["raw_object"] != descriptor
                            or reported["prior_report_sha256"] != event["prior_report_sha256"]):
                        _refuse("selected report row differs from journal or source request")
                    raw = root.read(descriptor["relative_path"], label="selected raw parent",
                                    max_bytes=MAX_COMPLETE_SUBMISSION_BYTES)
                    if len(raw) != descriptor["size_bytes"] or hash_bytes(raw) != descriptor["sha256"]:
                        _refuse("selected raw parent bytes changed")
                    target = SecCompleteSubmissionTarget(
                        period=request["period"], accession_number=request["accession_number"],
                        form_type=request["form_type"], filing_date=request["filing_date"],
                        issuer_cik=request["issuer_cik"],
                        quarterly_index_sha256=request["master_source_sha256"],
                        complete_submission_url=request["url"],
                    )
                    projection = project_sec_complete_submission(target, raw)
                    payload = projection.to_payload()
                    rows.append(SelectedParentProjectionRow(
                        period=request["period"], accession_number=request["accession_number"],
                        form_type=request["form_type"], submission_row_id=submission_id,
                        source=event["source"], raw_parent_sha256=descriptor["sha256"],
                        raw_parent_size_bytes=descriptor["size_bytes"],
                        header_sha256=payload["children"]["header"]["sha256"],
                        xml_sha256=payload["children"]["primary_xml"]["sha256"],
                        projection_sha256=projection.sha256,
                        accepted_at_raw=projection.accepted_at_raw,
                        header_owner_ciks=projection.header_owner_ciks,
                    ))
                payload = {
                    "version": ADAPTER_VERSION, "source_scope": scope,
                    "locator_manifest_sha256": locator_sha,
                    "request_inventory_sha256": hash_payload(list(requests)),
                    "inventory_sha256": inventory_sha,
                    "attempt_journal_sha256": journal_sha,
                    "report_sha256": commit["report_sha256"],
                    "capture_git_commit": capture_commit,
                    "rows": [row.to_payload() for row in rows],
                    "projections_verified": True, "quarter_population_complete": False,
                    "acceptance_timezone_verified": False,
                    "amendment_links_verified": False,
                    "multi_owner_economic_attribution_verified": False,
                    "canonical_evidence": False, "point_in_time_data": False,
                    "source_authenticated": False, "outcome_access_authorized": False,
                    "qc_job_authorized": False, "research_looks": 0,
                }
                result = SelectedParentProjectionReceipt(
                    source_scope=scope, locator_manifest_sha256=locator_sha,
                    request_inventory_sha256=hash_payload(list(requests)),
                    inventory_sha256=inventory_sha, attempt_journal_sha256=journal_sha,
                    report_sha256=commit["report_sha256"],
                    capture_git_commit=capture_commit, rows=tuple(rows),
                    lineage_sha256=hash_payload(payload),
                    _loader_token=_LOADER_TOKEN,
                )
                result.to_payload()
                named_lock = os.stat("run.lock", dir_fd=root.root_fd,
                                     follow_symlinks=False)
                if (not stat.S_ISREG(named_lock.st_mode) or named_lock.st_nlink != 1
                        or named_lock.st_size != 0
                        or (named_lock.st_dev, named_lock.st_ino)
                        != (lock_info.st_dev, lock_info.st_ino)):
                    _refuse("selected root lock identity changed during replay")
                root.check()
                return result
            finally:
                os.close(lock_fd)
    except (SecCompletePilotAdapterError, SecCompleteSubmissionError, OSError,
            TypeError, ValueError) as exc:
        if isinstance(exc, SecSelectedParentProjectionError):
            raise
        raise SecSelectedParentProjectionError(f"REFUSED: selected replay failed: {exc}") from exc


def replay_synthetic_selected_parent_root(
    root: str | Path, plan: SelectedParentPlan,
) -> SelectedParentProjectionReceipt:
    """Replay invented runner output only; never label it retained SEC evidence."""
    scope, locator_sha, requests, source_ids = _expected_synthetic(plan)
    expected_reuses = tuple(item.to_payload() for item in plan.reuses)
    return _replay(root, scope=scope, locator_sha=locator_sha, requests=requests,
                   submission_ids=source_ids, expected_reuses=expected_reuses)


def load_observed_selected_parent_root(
    root: str | Path,
    quarter_inputs: tuple[ObservedMasterLocatorQuarterInput, ...],
) -> SelectedParentProjectionReceipt:
    """Replay the exact 9,337 observed-priority cohort, still noncanonical."""
    scope, locator_sha, requests, source_ids = _expected_real(quarter_inputs)
    return _replay(root, scope=scope, locator_sha=locator_sha, requests=requests,
                   submission_ids=source_ids, expected_reuses=None)


__all__ = [
    "ADAPTER_VERSION", "SecSelectedParentProjectionError",
    "SelectedParentProjectionRow", "SelectedParentProjectionReceipt",
    "replay_synthetic_selected_parent_root", "load_observed_selected_parent_root",
]
