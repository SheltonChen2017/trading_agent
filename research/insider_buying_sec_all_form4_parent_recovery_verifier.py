"""Independent, read-only custody replay for a completed v3 parent continuation.

This module has no transport or publication path.  A v3 root is accepted only
after the stopped v1 campaign, diagnostic body, selected objects, new objects,
and the ordered 99,394-parent union have all been replayed from their bytes.
The receipt is source custody, never SEC authenticity, PIT, or research proof.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
import fcntl
import json
import os
import re
import stat
import subprocess

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying_sec_acquisition import (
    SecPilotError, _plain_path, _refuse_output_overlap,
)
from research.insider_buying_sec_complete_acquisition import (
    MAX_COMPLETE_TXT_BYTES, SecCompleteAcquisitionError, SecHttpResult,
)
from research.insider_buying_sec_selected_parent_runner import _strict_selected_response
import research.insider_buying_sec_all_form4_parent_campaign as campaign
import research.insider_buying_sec_all_form4_parent_recovery_preflight as partial
import research.insider_buying_sec_all_form4_parent_recovery_union as source_union


VERIFIER_VERSION = "INSETF-SEC-ALL-FORM4-PARENTS-RECOVERY-VERIFIER-v1"
EXECUTOR_VERSION = "INSETF-SEC-ALL-FORM4-PARENTS-RECOVERY-EXECUTOR-v1"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_EVENT_NAME = re.compile(r"event-([0-9]{6})-([0-9a-f]{64})\.json\Z")
_MAX_EVENT_BYTES = 2_048
_MAX_PLAN_BYTES = 256 * 1024
_MAX_INVENTORY_BYTES = campaign.MAX_SHARD_INVENTORY_BYTES
_MAX_REPORT_BYTES = campaign.MAX_SHARD_REPORT_BYTES
_MAX_JOURNAL_BYTES = campaign.MAX_SHARD_JOURNAL_BYTES
_MAX_EVENTS = campaign.SHARD_SIZE * (campaign.MAX_ATTEMPTS * 2 + 1)
_RETRY_HTTP = frozenset({500, 502, 503, 504})


class RecoveryVerificationError(ValueError):
    """The putatively complete v3 source root has not earned a receipt."""


def _refuse(reason: str) -> None:
    raise RecoveryVerificationError(f"REFUSED: {reason}")


def _raw(value: object) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def _json(raw: bytes, *, label: str) -> dict[str, object]:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                _refuse(f"{label} repeats a key")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw, object_pairs_hook=unique,
            parse_constant=lambda _: _refuse(f"{label} is nonfinite"),
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise RecoveryVerificationError(f"REFUSED: {label} is not strict JSON") from exc
    if type(value) is not dict or _raw(value) != raw:
        _refuse(f"{label} is not canonical JSON plus LF")
    return value


def _sha(value: object) -> bool:
    return type(value) is str and _SHA.fullmatch(value) is not None


def _private_directory(path: Path) -> None:
    named = path.lstat()
    if (not stat.S_ISDIR(named.st_mode)
            or stat.S_IMODE(named.st_mode) != 0o700):
        _refuse("v3 directory is not private and ordinary")


def _private_file(path: Path) -> None:
    named = path.lstat()
    if (not stat.S_ISREG(named.st_mode) or named.st_nlink != 1
            or stat.S_IMODE(named.st_mode) != 0o600):
        _refuse("v3 file is not private, regular and single-link")


@contextmanager
def _pinned_directory(
    path: Path, *, lock: bool = False,
) -> Iterator[campaign._ReadOnlyDirectory]:
    """Confine a private directory read to the inode inspected on disk."""
    try:
        _plain_path(path, must_exist=True)
        _private_directory(path)
        with campaign._ReadOnlyDirectory(path) as pinned:
            _private_directory(path)
            lock_fd: int | None = None
            try:
                if lock:
                    _empty_file(pinned, "run.lock")
                    lock_fd = os.open(
                        "run.lock", os.O_RDONLY | os.O_NOFOLLOW,
                        dir_fd=pinned.descriptor,
                    )
                    fcntl.flock(lock_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                yield pinned
                pinned.check()
                _private_directory(path)
            finally:
                if lock_fd is not None:
                    os.close(lock_fd)
    except RecoveryVerificationError:
        raise
    except (campaign.CampaignError, SecPilotError, OSError, ValueError) as exc:
        raise RecoveryVerificationError("REFUSED: v3 directory replay failed") from exc


def _read(
    pinned: campaign._ReadOnlyDirectory, name: str, *, max_bytes: int,
) -> bytes:
    path = pinned.path / name
    try:
        _private_file(path)
        raw = pinned.read(name, max_bytes=max_bytes)
        _private_file(path)
    except RecoveryVerificationError:
        raise
    except (campaign.CampaignError, OSError, ValueError) as exc:
        raise RecoveryVerificationError("REFUSED: v3 private file read failed") from exc
    return raw


def _empty_file(pinned: campaign._ReadOnlyDirectory, name: str) -> None:
    """Check the intentionally empty lock/journal without a positive-size read."""
    path = pinned.path / name
    try:
        _private_file(path)
        if path.stat().st_size != 0:
            _refuse("v3 empty control file has content")
        descriptor = os.open(
            name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
            dir_fd=pinned.descriptor,
        )
        try:
            opened = os.fstat(descriptor)
            if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                    or opened.st_size != 0 or stat.S_IMODE(opened.st_mode) != 0o600
                    or (opened.st_dev, opened.st_ino)
                    != (path.stat().st_dev, path.stat().st_ino)):
                _refuse("v3 empty control file changed")
        finally:
            os.close(descriptor)
        pinned.check()
    except RecoveryVerificationError:
        raise
    except (OSError, campaign.CampaignError, ValueError) as exc:
        raise RecoveryVerificationError(
            "REFUSED: v3 empty control file could not be verified"
        ) from exc


def _source_classes(
    plan: campaign.CampaignPlan, receipt: dict[str, object],
) -> tuple[list[str], list[dict[str, str]]]:
    """Recompute each source assignment without consulting the v3 root."""
    payload = plan.to_payload()
    if (type(receipt) is not dict
            or receipt.get("kind") != source_union.UNION_VERSION + "/read-only-preflight"
            or receipt.get("manifest_sha256") != plan.manifest_sha256
            or receipt.get("request_inventory_sha256") != payload["request_inventory_sha256"]
            or receipt.get("total_parents") != len(plan.requests)
            or receipt.get("sec_dispatches") != 0
            or any(receipt.get(key) is not False for key in (
                "complete_parent_bytes_acquired", "source_authenticated",
                "canonical_evidence", "point_in_time_data",
            ))
            or receipt.get("research_looks") != 0 or receipt.get("qc_jobs") != 0):
        _refuse("source union carries a different population or authority")
    prior_count = receipt.get("prior_completed_count")
    if type(prior_count) is not int or not 0 <= prior_count < len(plan.requests):
        _refuse("source union prior prefix is malformed")
    corrected = receipt.get("offline_corrected_diagnostic_count")
    accepted = receipt.get("accepted_diagnostic_count")
    if (type(corrected) is not int or type(accepted) is not int
            or accepted + corrected != 1 or accepted not in (0, 1)
            or corrected not in (0, 1)):
        _refuse("source union diagnostic class is ambiguous")
    diagnostic_class = (
        "offline_corrected_diagnostic" if corrected else "accepted_diagnostic"
    )
    selected = {item.accession_number for item in plan.reuses}
    if plan.requests[prior_count].accession_number in selected:
        _refuse("source union diagnostic is already selected")
    classes = ["prior_completed"] * prior_count + [diagnostic_class]
    later: list[dict[str, str]] = []
    for request in plan.requests[prior_count + 1:]:
        if request.accession_number in selected:
            classes.append("remaining_selected_reuse")
        else:
            classes.append("later_unattempted")
            later.append(request.to_payload())
    if (len(classes) != len(plan.requests)
            or hash_payload(classes) != receipt.get("source_assignment_sha256")
            or hash_payload(later)
            != receipt.get("later_unattempted_request_inventory_sha256")
            or classes.count("remaining_selected_reuse")
            != receipt.get("remaining_selected_reuse_count")
            or len(later) != receipt.get("later_unattempted_request_count")):
        _refuse("source union source-class or dispatch partition changed")
    return classes, later


def _utc(value: object) -> None:
    if type(value) is not str or re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}\+00:00",
        value,
    ) is None:
        _refuse("v3 event timestamp is malformed")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise RecoveryVerificationError("REFUSED: v3 event timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _refuse("v3 event timestamp is not UTC")


def _read_events(
    shard: campaign._ReadOnlyDirectory, inventory_raw: bytes,
) -> tuple[list[dict[str, object]], list[bytes], set[str]]:
    names = shard.names()
    numbered: list[tuple[int, str, str]] = []
    for name in names:
        if not name.startswith("event-"):
            continue
        match = _EVENT_NAME.fullmatch(name)
        if match is None:
            _refuse("v3 event filename is malformed")
        numbered.append((int(match.group(1)), name, match.group(2)))
    numbered.sort()
    if (len(numbered) > _MAX_EVENTS
            or [index for index, _, _ in numbered]
            != list(range(1, len(numbered) + 1))):
        _refuse("v3 event sequence is incomplete or excessive")
    chain = hash_bytes(inventory_raw)
    parsed: list[dict[str, object]] = []
    raw_events: list[bytes] = []
    for _, name, digest in numbered:
        raw = _read(shard, name, max_bytes=_MAX_EVENT_BYTES)
        if hash_bytes(raw) != digest:
            _refuse("v3 event content differs from its immutable name")
        event = _json(raw, label="v3 event")
        if event.get("prev_sha256") != chain:
            _refuse("v3 event hash chain changed")
        parsed.append(event)
        raw_events.append(raw)
        chain = digest
    return parsed, raw_events, {name for _, name, _ in numbered}


def _replay_new_events(
    shard: campaign._ReadOnlyDirectory,
    rows: list[dict[str, object]],
    events: list[dict[str, object]],
) -> tuple[dict[int, dict[str, object]], int, set[str]]:
    """Replay the no-duplicate attempt state without importing executor code."""
    new_rows = [row for row in rows if row["source_class"] == "later_unattempted"]
    completed: dict[int, dict[str, object]] = {}
    attempts: dict[int, int] = {}
    objects: set[str] = set()
    cursor = 0
    ordinal = 0
    pending_start: dict[str, object] | None = None
    pending_valid: dict[str, object] | None = None
    with _pinned_directory(shard.path / "objects") as object_dir:
        for event in events:
            if type(event) is not dict or cursor >= len(new_rows):
                _refuse("v3 event follows completed shard")
            row = new_rows[cursor]
            index = row["global_index"]
            request = row["request"]
            if (type(event.get("global_index")) is not int
                    or event["global_index"] != index
                    or event.get("accession_number") != request["accession_number"]):
                _refuse("v3 event does not follow exact later-dispatch order")
            kind = event.get("kind")
            if kind == "attempt-start":
                ordinal += 1
                count = attempts.get(index, 0) + 1
                if (pending_start is not None or pending_valid is not None
                        or count > campaign.MAX_ATTEMPTS
                        or set(event) != {
                            "kind", "prev_sha256", "global_index", "accession_number",
                            "ordinal", "attempt", "url", "started_utc",
                        }
                        or type(event["ordinal"]) is not int
                        or event["ordinal"] != ordinal
                        or type(event["attempt"]) is not int
                        or event["attempt"] != count
                        or event["url"] != request["url"]):
                    _refuse("v3 attempt-start is duplicate, ambiguous or out of order")
                _utc(event["started_utc"])
                attempts[index] = count
                pending_start = event
            elif kind == "attempt-finish":
                if (pending_start is None or pending_valid is not None
                        or set(event) != {
                            "kind", "prev_sha256", "global_index", "accession_number",
                            "ordinal", "outcome", "status", "body_sha256",
                            "body_size_bytes", "framing_headers", "finished_utc",
                        }
                        or type(event["ordinal"]) is not int
                        or event["ordinal"] != pending_start["ordinal"]):
                    _refuse("v3 attempt-finish lacks its exact durable start")
                _utc(event["finished_utc"])
                if (datetime.fromisoformat(event["finished_utc"])
                        < datetime.fromisoformat(pending_start["started_utc"])):
                    _refuse("v3 attempt finished before its durable start")
                if event["outcome"] == "valid_response":
                    if (type(event["status"]) is not int or event["status"] != 200
                            or not _sha(event["body_sha256"])
                            or type(event["body_size_bytes"]) is not int
                            or not 0 < event["body_size_bytes"] <= MAX_COMPLETE_TXT_BYTES
                            or type(event["framing_headers"]) is not list
                            or any(type(pair) is not list or len(pair) != 2
                                   or type(pair[0]) is not str or type(pair[1]) is not str
                                   for pair in event["framing_headers"])):
                        _refuse("v3 valid response descriptor is malformed")
                    body = _read(
                        object_dir, f'{event["body_sha256"]}.bin',
                        max_bytes=MAX_COMPLETE_TXT_BYTES,
                    )
                    if (len(body) != event["body_size_bytes"]
                            or hash_bytes(body) != event["body_sha256"]):
                        _refuse("v3 stored response bytes changed")
                    response = SecHttpResult(
                        status=200,
                        headers=tuple(tuple(pair) for pair in event["framing_headers"]),
                        body=body,
                    )
                    try:
                        if _strict_selected_response(
                            response, max_bytes=MAX_COMPLETE_TXT_BYTES,
                        ) != body:
                            _refuse("v3 response framing changed")
                    except SecCompleteAcquisitionError as exc:
                        raise RecoveryVerificationError(
                            "REFUSED: v3 response framing is invalid"
                        ) from exc
                    pending_valid = event
                elif event["outcome"] == "http_error":
                    if (type(event["status"]) is not int
                            or event["status"] not in _RETRY_HTTP
                            or event["body_sha256"] is not None
                            or event["body_size_bytes"] is not None
                            or event["framing_headers"] is not None
                            or attempts[index] >= campaign.MAX_ATTEMPTS):
                        _refuse("v3 completed root includes terminal HTTP or response ambiguity")
                else:
                    _refuse("v3 completed root includes a refusal or ambiguous transport")
                pending_start = None
            elif kind == "item-complete":
                if (pending_start is not None or pending_valid is None
                        or set(event) != {
                            "kind", "prev_sha256", "global_index", "accession_number",
                            "source", "object_sha256", "object_size_bytes",
                        }
                        or event["source"] != "new_acquired"
                        or event["object_sha256"] != pending_valid["body_sha256"]
                        or type(event["object_size_bytes"]) is not int
                        or event["object_size_bytes"] != pending_valid["body_size_bytes"]):
                    _refuse("v3 item-complete is not backed by a valid 200 response")
                digest = event["object_sha256"]
                raw = _read(object_dir, f"{digest}.bin", max_bytes=MAX_COMPLETE_TXT_BYTES)
                if len(raw) != event["object_size_bytes"] or hash_bytes(raw) != digest:
                    _refuse("v3 new parent body differs from durable response")
                try:
                    campaign._validate_parent_header(raw, request)
                except campaign.CampaignError as exc:
                    raise RecoveryVerificationError(
                        "REFUSED: v3 new parent bytes disagree with request"
                    ) from exc
                completed[index] = {
                    "object_sha256": digest,
                    "object_size_bytes": len(raw),
                    "attempts": attempts[index],
                }
                objects.add(f"{digest}.bin")
                pending_valid = None
                cursor += 1
            else:
                _refuse("v3 event kind is unknown")
        if (pending_start is not None or pending_valid is not None
                or cursor != len(new_rows) or object_dir.names() != objects):
            _refuse("v3 shard has incomplete request state or extra/missing objects")
    return completed, sum(attempts.values()), objects


def _expected_plan(
    plan: campaign.CampaignPlan, receipt: dict[str, object],
    source_roots: tuple[str | Path, str | Path, str | Path],
    *, prior_expectation: partial.PartialCampaignExpectation,
    capture_git_commit: str, capture_code_sha256: str,
) -> tuple[dict[str, object], bytes, tuple[tuple[dict[str, object], bytes], ...]]:
    if (type(prior_expectation) is not partial.PartialCampaignExpectation
            or type(capture_git_commit) is not str
            or _COMMIT.fullmatch(capture_git_commit) is None
            or not _sha(capture_code_sha256)):
        _refuse("v3 trusted code or prior-source anchor is malformed")
    prior_expectation.validate()
    classes, dispatch = _source_classes(plan, receipt)
    payload = plan.to_payload()
    paths = tuple(str(_plain_path(path, must_exist=True)) for path in source_roots)
    diagnostic_mode = (
        "offline_corrected" if receipt["offline_corrected_diagnostic_count"]
        else "originally_accepted"
    )
    body: dict[str, object] = {
        "kind": EXECUTOR_VERSION + "/plan",
        "source_scope": plan.scope,
        "capture_git_commit": capture_git_commit,
        "capture_code_sha256": capture_code_sha256,
        "manifest_sha256": plan.manifest_sha256,
        "request_inventory_sha256": payload["request_inventory_sha256"],
        "source_assignment_sha256": receipt["source_assignment_sha256"],
        "later_unattempted_request_inventory_sha256": receipt[
            "later_unattempted_request_inventory_sha256"
        ],
        "prior_campaign_root": paths[0],
        "diagnostic_root": paths[1],
        "selected_root": paths[2],
        "prior_expectation": {
            "capture_git_commit": prior_expectation.capture_git_commit,
            "shard_report_sha256s": list(prior_expectation.shard_report_sha256s),
            "completed_counts": list(prior_expectation.completed_counts),
            "reused_counts": list(prior_expectation.reused_counts),
            "total_attempt_count": prior_expectation.total_attempt_count,
        },
        "prior_campaign_plan_sha256": receipt["prior_campaign_plan_sha256"],
        "prior_shard_journal_sha256s": list(receipt["prior_shard_journal_sha256s"]),
        "diagnostic_capture_git_commit": receipt["diagnostic_capture_git_commit"],
        "diagnostic_report_sha256": receipt["diagnostic_report_sha256"],
        "diagnostic_mode": diagnostic_mode,
        "original_diagnostic_envelope_outcome": receipt[
            "original_diagnostic_envelope_outcome"
        ],
        "offline_correction_receipt_sha256": receipt[
            "offline_correction_receipt_sha256"
        ],
        "selected_report_sha256": plan.selected_report_sha256,
        "selected_receipt_lineage_sha256": plan.selected_receipt_lineage_sha256,
        "total_parents": len(plan.requests),
        "prior_completed_count": receipt["prior_completed_count"],
        "accepted_diagnostic_count": receipt["accepted_diagnostic_count"],
        "offline_corrected_diagnostic_count": receipt[
            "offline_corrected_diagnostic_count"
        ],
        "remaining_selected_reuse_count": receipt["remaining_selected_reuse_count"],
        "later_unattempted_request_count": len(dispatch),
        "shard_size": plan.shard_size,
        "max_attempts_per_parent": campaign.MAX_ATTEMPTS,
        "minimum_request_interval_ns": campaign.MIN_REQUEST_INTERVAL_NS,
        "source_authenticated": False,
        "canonical_evidence": False,
        "point_in_time_data": False,
        "outcome_looks": 0,
        "qc_jobs": 0,
    }
    source_plan_sha = hash_payload(body)
    inventories: list[tuple[dict[str, object], bytes]] = []
    requests = payload["requests"]
    for number, start in enumerate(range(0, len(requests), plan.shard_size)):
        chunk = requests[start:start + plan.shard_size]
        sources = classes[start:start + len(chunk)]
        rows = [{"global_index": start + index, "request": request,
                 "source_class": source}
                for index, (request, source) in enumerate(zip(
                    chunk, sources, strict=True,
                ))]
        later = [request for request, source in zip(chunk, sources, strict=True)
                 if source == "later_unattempted"]
        inventory: dict[str, object] = {
            "kind": EXECUTOR_VERSION + "/shard-inventory",
            "source_plan_sha256": source_plan_sha,
            "name": f"shard-{number:04d}",
            "start": start,
            "count": len(rows),
            "rows": rows,
            "request_inventory_sha256": hash_payload(chunk),
            "source_assignment_sha256": hash_payload(sources),
            "later_unattempted_request_inventory_sha256": hash_payload(later),
        }
        raw = _raw(inventory)
        if len(raw) > _MAX_INVENTORY_BYTES:
            _refuse("v3 source-bound shard inventory exceeds its cap")
        inventories.append((inventory, raw))
    body["shards"] = [{
        "name": inventory["name"], "start": inventory["start"],
        "count": inventory["count"], "inventory_sha256": hash_bytes(raw),
    } for inventory, raw in inventories]
    body["source_plan_sha256"] = source_plan_sha
    plan_raw = _raw(body)
    if (len(plan_raw) > _MAX_PLAN_BYTES
            or len(inventories) > campaign.MAX_SHARDS
            or sum(row["count"] for row, _ in inventories) != len(plan.requests)):
        _refuse("v3 root plan exceeds its frozen population")
    return body, plan_raw, tuple(inventories)


def _expected_shard_report(
    inventory: dict[str, object], inventory_raw: bytes,
    events_raw: list[bytes], completed: dict[int, dict[str, object]],
    attempt_count: int,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    source_bound = 0
    for row in inventory["rows"]:
        index = row["global_index"]
        source = row["source_class"]
        if source != "later_unattempted":
            source_bound += 1
            rows.append({
                "global_index": index, "source_class": source,
                "attempts": 0, "status": "source_bound",
            })
            continue
        descriptor = completed.get(index)
        if descriptor is None:
            _refuse("v3 shard report would omit a later parent")
        digest = descriptor["object_sha256"]
        rows.append({
            "global_index": index, "source_class": source,
            "attempts": descriptor["attempts"],
            "status": "raw_acquired_noncanonical",
            "raw_object": {
                "relative_path": f"objects/{digest}.bin",
                "sha256": digest,
                "size_bytes": descriptor["object_size_bytes"],
            },
        })
    journal = b"".join(events_raw)
    return {
        "kind": EXECUTOR_VERSION + "/shard-report",
        "source_plan_sha256": inventory["source_plan_sha256"],
        "inventory_sha256": hash_bytes(inventory_raw),
        "name": inventory["name"],
        "start": inventory["start"],
        "count": inventory["count"],
        "attempt_journal_sha256": hash_bytes(journal),
        "attempt_event_count": len(events_raw),
        "attempt_count": attempt_count,
        "new_acquired_count": len(completed),
        "source_bound_count": source_bound,
        "complete_count": source_bound + len(completed),
        "rows": rows,
        "halted_reason": None,
        "complete_shard_raw_set_acquired": True,
        "source_authenticated": False,
        "canonical_evidence": False,
        "point_in_time_data": False,
        "outcome_looks": 0,
        "qc_jobs": 0,
    }


def _verify_shard(
    root: Path, inventory: dict[str, object], inventory_raw: bytes,
) -> dict[str, object]:
    name = inventory["name"]
    shard_path = root / name
    with _pinned_directory(shard_path, lock=True) as shard:
        _empty_file(shard, "run.lock")
        if _read(shard, "inventory.json", max_bytes=_MAX_INVENTORY_BYTES) != inventory_raw:
            _refuse("v3 shard inventory differs from independent source order")
        events, raw_events, event_names = _read_events(shard, inventory_raw)
        completed, attempts, objects = _replay_new_events(
            shard, inventory["rows"], events,
        )
        journal = b"".join(raw_events)
        if len(journal) > _MAX_JOURNAL_BYTES:
            _refuse("v3 shard attempt journal exceeds its cap")
        if journal:
            if _read(shard, "attempts.jsonl", max_bytes=_MAX_JOURNAL_BYTES) != journal:
                _refuse("v3 shard journal differs from event chain")
        else:
            _empty_file(shard, "attempts.jsonl")
        report = _expected_shard_report(
            inventory, inventory_raw, raw_events, completed, attempts,
        )
        report_raw = _raw(report)
        report_sha = hash_bytes(report_raw)
        report_name = f"shard-report-{report_sha}.json"
        if _read(shard, report_name, max_bytes=_MAX_REPORT_BYTES) != report_raw:
            _refuse("v3 shard report differs from independently replayed state")
        commit = {
            "kind": EXECUTOR_VERSION + "/shard-commit",
            "report_name": report_name,
            "report_sha256": report_sha,
            "inventory_sha256": hash_bytes(inventory_raw),
            "attempt_journal_sha256": hash_bytes(journal),
        }
        if _read(shard, "commit.json", max_bytes=4096) != _raw(commit):
            _refuse("v3 shard commit differs from independently replayed state")
        expected = {
            "run.lock", "inventory.json", "objects", "attempts.jsonl",
            report_name, "commit.json",
        } | event_names
        if shard.names() != expected:
            _refuse("v3 shard has an extra or missing member")
        with _pinned_directory(shard_path / "objects") as object_dir:
            if object_dir.names() != objects:
                _refuse("v3 shard objects differ from completed responses")
    return {
        "name": name, "start": inventory["start"],
        "count": inventory["count"],
        "inventory_sha256": hash_bytes(inventory_raw),
        "report_sha256": report_sha,
        "attempt_count": attempts,
        "new_acquired_count": len(completed),
        "source_bound_count": report["source_bound_count"],
        "_new_object_bytes": sum(
            descriptor["object_size_bytes"] for descriptor in completed.values()
        ),
    }


def _verify_completed(
    plan: campaign.CampaignPlan, receipt: dict[str, object],
    prior_campaign_root: str | Path, diagnostic_root: str | Path,
    selected_root: str | Path, output_root: str | Path,
    *, capture_git_commit: str,
    prior_expectation: partial.PartialCampaignExpectation,
    capture_code_sha256: str,
) -> dict[str, object]:
    """Require byte-for-byte recomputation of every completed v3 output."""
    try:
        plan_body, plan_raw, inventories = _expected_plan(
            plan, receipt,
            (prior_campaign_root, diagnostic_root, selected_root),
            prior_expectation=prior_expectation,
            capture_git_commit=capture_git_commit,
            capture_code_sha256=capture_code_sha256,
        )
        output = _plain_path(output_root, must_exist=True)
        for protected in (
            prior_campaign_root, diagnostic_root, selected_root,
            Path(__file__).resolve().parents[1],
        ):
            _refuse_output_overlap(
                output, _plain_path(protected, must_exist=True),
            )
        if (plan.scope == "ib1b_observed_full_form4_noncanonical"
                and output != _plain_path(prior_campaign_root, must_exist=True).parent
                / "all-form4-parents-recovery-v3"):
            _refuse("observed v3 root is not the fixed continuation sibling")
        summaries: list[dict[str, object]] = []
        with _pinned_directory(output, lock=True) as top:
            _empty_file(top, "run.lock")
            if _read(top, "plan.json", max_bytes=_MAX_PLAN_BYTES) != plan_raw:
                _refuse("v3 root plan differs from independently replayed source")
            new_object_bytes = 0
            for inventory, inventory_raw in inventories:
                summary = _verify_shard(output, inventory, inventory_raw)
                new_object_bytes += summary.pop("_new_object_bytes")
                summaries.append(summary)
            if new_object_bytes > campaign.MAX_RUN_OBJECT_BYTES:
                _refuse("v3 acquired objects exceed the campaign byte cap")
            acquired = sum(item["new_acquired_count"] for item in summaries)
            attempts = sum(item["attempt_count"] for item in summaries)
            source_bound = sum(item["source_bound_count"] for item in summaries)
            if (source_bound + acquired != len(plan.requests)
                    or acquired != receipt["later_unattempted_request_count"]
                    or sum(item["count"] for item in summaries) != len(plan.requests)):
                _refuse("v3 complete union does not equal the source denominator")
            report = {
                "kind": EXECUTOR_VERSION + "/campaign-report",
                "plan_sha256": hash_bytes(plan_raw),
                "source_plan_sha256": plan_body["source_plan_sha256"],
                "manifest_sha256": plan.manifest_sha256,
                "request_inventory_sha256": plan_body["request_inventory_sha256"],
                "source_assignment_sha256": plan_body["source_assignment_sha256"],
                "later_unattempted_request_inventory_sha256": plan_body[
                    "later_unattempted_request_inventory_sha256"
                ],
                "total_parents": len(plan.requests),
                "prior_completed_count": receipt["prior_completed_count"],
                "accepted_diagnostic_count": receipt["accepted_diagnostic_count"],
                "offline_corrected_diagnostic_count": receipt[
                    "offline_corrected_diagnostic_count"
                ],
                "remaining_selected_reuse_count": receipt[
                    "remaining_selected_reuse_count"
                ],
                "later_acquired_count": acquired,
                "new_attempt_count": attempts,
                "shards": summaries,
                "complete_parent_bytes_acquired": True,
                "source_authenticated": False,
                "canonical_evidence": False,
                "point_in_time_data": False,
                "outcome_looks": 0,
                "qc_jobs": 0,
            }
            report_raw = _raw(report)
            report_sha = hash_bytes(report_raw)
            report_name = f"campaign-report-{report_sha}.json"
            if _read(top, report_name, max_bytes=_MAX_PLAN_BYTES) != report_raw:
                _refuse("v3 campaign report differs from independently replayed shards")
            commit = {
                "kind": EXECUTOR_VERSION + "/campaign-commit",
                "report_name": report_name,
                "report_sha256": report_sha,
                "plan_sha256": hash_bytes(plan_raw),
            }
            if _read(top, "commit.json", max_bytes=4096) != _raw(commit):
                _refuse("v3 campaign commit differs from source-bound union")
            expected_names = {
                "run.lock", "plan.json", report_name, "commit.json",
            } | {inventory["name"] for inventory, _ in inventories}
            if top.names() != expected_names:
                _refuse("v3 root has an extra or missing member")
        return {
            "kind": VERIFIER_VERSION + "/completed-source-custody",
            "source_scope": plan.scope,
            "capture_git_commit": capture_git_commit,
            "manifest_sha256": plan.manifest_sha256,
            "request_inventory_sha256": plan_body["request_inventory_sha256"],
            "source_assignment_sha256": plan_body["source_assignment_sha256"],
            "campaign_report_sha256": report_sha,
            "total_parents": len(plan.requests),
            "prior_completed_count": receipt["prior_completed_count"],
            "accepted_diagnostic_count": receipt["accepted_diagnostic_count"],
            "offline_corrected_diagnostic_count": receipt[
                "offline_corrected_diagnostic_count"
            ],
            "remaining_selected_reuse_count": receipt[
                "remaining_selected_reuse_count"
            ],
            "later_acquired_count": acquired,
            "new_attempt_count": attempts,
            "shard_count": len(inventories),
            "complete_parent_bytes_acquired": True,
            "source_authenticated": False,
            "canonical_evidence": False,
            "point_in_time_data": False,
            "research_looks": 0,
            "qc_jobs": 0,
        }
    except RecoveryVerificationError:
        raise
    except (campaign.CampaignError, source_union.RecoveryUnionError,
            SecPilotError, OSError, KeyError, IndexError, TypeError, ValueError,
            RecursionError) as exc:
        raise RecoveryVerificationError(
            "REFUSED: v3 completed-root replay failed"
        ) from exc


def verify_completed_synthetic_recovery_v3(
    plan: campaign.CampaignPlan,
    prior_campaign_root: str | Path,
    diagnostic_root: str | Path,
    selected_root: str | Path,
    output_root: str | Path,
    *, prior_expectation: partial.PartialCampaignExpectation,
    diagnostic_capture_git_commit: str,
    expected_diagnostic_report_sha256: str,
    capture_git_commit: str,
    diagnostic_mode: str = "originally_accepted",
) -> dict[str, object]:
    """Replay an invented-source root; never label it an observed SEC corpus."""
    if type(plan) is not campaign.CampaignPlan or plan.scope != "synthetic_test_manifest":
        _refuse("synthetic v3 verifier requires a synthetic source plan")
    try:
        receipt = source_union.preflight_source_union(
            plan, prior_campaign_root, diagnostic_root, selected_root,
            prior_expectation=prior_expectation,
            diagnostic_capture_git_commit=diagnostic_capture_git_commit,
            expected_diagnostic_report_sha256=expected_diagnostic_report_sha256,
            diagnostic_mode=diagnostic_mode,
        )
    except (source_union.RecoveryUnionError, campaign.CampaignError) as exc:
        raise RecoveryVerificationError("REFUSED: v3 source replay failed") from exc
    code_path = Path(__file__).with_name(
        "insider_buying_sec_all_form4_parent_recovery_executor.py"
    )
    result = _verify_completed(
        plan, receipt, prior_campaign_root, diagnostic_root, selected_root,
        output_root, capture_git_commit=capture_git_commit,
        prior_expectation=prior_expectation,
        capture_code_sha256=hash_bytes(code_path.read_bytes()),
    )
    try:
        replayed = source_union.preflight_source_union(
            plan, prior_campaign_root, diagnostic_root, selected_root,
            prior_expectation=prior_expectation,
            diagnostic_capture_git_commit=diagnostic_capture_git_commit,
            expected_diagnostic_report_sha256=expected_diagnostic_report_sha256,
            diagnostic_mode=diagnostic_mode,
        )
    except (source_union.RecoveryUnionError, campaign.CampaignError) as exc:
        raise RecoveryVerificationError("REFUSED: v3 source changed during replay") from exc
    if replayed != receipt:
        _refuse("synthetic source roots changed during v3 replay")
    return result


def load_observed_completed_all_form4_recovery_v3(
    raw_q4_directory: str | Path, parsed_q4_directory: str | Path,
    raw_q1_directory: str | Path, parsed_q1_directory: str | Path,
    exact16_pilot_root: str | Path, selected_root: str | Path,
    prior_campaign_root: str | Path, diagnostic_root: str | Path,
    output_root: str | Path, *, capture_git_commit: str,
    expected_capture_code_sha256: str,
    expected_campaign_report_sha256: str,
) -> dict[str, object]:
    """Replay the exact pinned two-quarter source and every completed v3 shard."""
    if (type(capture_git_commit) is not str
            or _COMMIT.fullmatch(capture_git_commit) is None
            or not _sha(expected_capture_code_sha256)
            or not _sha(expected_campaign_report_sha256)):
        _refuse("observed v3 anchors are malformed")
    lane_root = Path(__file__).resolve().parents[1]
    if lane_root != Path(
        "/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying"
    ):
        _refuse("observed verifier is not running in the designated lane")
    try:
        code_blob = subprocess.run(
            ["git", "cat-file", "blob", capture_git_commit + ":research/"
             "insider_buying_sec_all_form4_parent_recovery_executor.py"],
            cwd=lane_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise RecoveryVerificationError(
            "REFUSED: observed v3 committed code could not be read"
        ) from exc
    if (code_blob.returncode != 0
            or hash_bytes(code_blob.stdout) != expected_capture_code_sha256):
        _refuse("observed v3 executor bytes differ from committed code anchor")
    try:
        receipt = source_union.preflight_observed_all_form4_parent_recovery_union(
            raw_q4_directory, parsed_q4_directory, raw_q1_directory,
            parsed_q1_directory, exact16_pilot_root, selected_root,
            prior_campaign_root, diagnostic_root,
            diagnostic_capture_git_commit=source_union.OBSERVED_DIAGNOSTIC_CAPTURE_COMMIT,
            expected_diagnostic_report_sha256=source_union.OBSERVED_DIAGNOSTIC_REPORT_SHA256,
        )
        plan = campaign._build_real_plan(
            raw_q4_directory, parsed_q4_directory, raw_q1_directory,
            parsed_q1_directory, exact16_pilot_root, selected_root,
        )
    except (source_union.RecoveryUnionError, campaign.CampaignError) as exc:
        raise RecoveryVerificationError("REFUSED: observed v3 source replay failed") from exc
    if (len(plan.requests) != 99_394 or plan.shard_size != 8_192
            or receipt["prior_completed_count"] != 9_539
            or receipt["offline_corrected_diagnostic_count"] != 1
            or receipt["remaining_selected_reuse_count"] != 8_139
            or receipt["later_unattempted_request_count"] != 81_715):
        _refuse("observed v3 denominator differs from frozen source partition")
    result = _verify_completed(
        plan, receipt, prior_campaign_root, diagnostic_root, selected_root,
        output_root, capture_git_commit=capture_git_commit,
        capture_code_sha256=expected_capture_code_sha256,
        prior_expectation=partial.PartialCampaignExpectation(
            capture_git_commit=partial.PRIOR_CAPTURE_GIT_COMMIT,
            shard_report_sha256s=partial.PRIOR_SHARD_REPORT_SHA256S,
            completed_counts=(8_192, 1_347), reused_counts=(972, 226),
            total_attempt_count=8_342,
        ),
    )
    if result["campaign_report_sha256"] != expected_campaign_report_sha256:
        _refuse("observed v3 report differs from independent external anchor")
    try:
        replayed = source_union.preflight_observed_all_form4_parent_recovery_union(
            raw_q4_directory, parsed_q4_directory, raw_q1_directory,
            parsed_q1_directory, exact16_pilot_root, selected_root,
            prior_campaign_root, diagnostic_root,
            diagnostic_capture_git_commit=source_union.OBSERVED_DIAGNOSTIC_CAPTURE_COMMIT,
            expected_diagnostic_report_sha256=source_union.OBSERVED_DIAGNOSTIC_REPORT_SHA256,
        )
    except source_union.RecoveryUnionError as exc:
        raise RecoveryVerificationError("REFUSED: observed v3 source changed") from exc
    if replayed != receipt:
        _refuse("observed source roots changed during v3 replay")
    return result


__all__ = [
    "RecoveryVerificationError", "verify_completed_synthetic_recovery_v3",
    "load_observed_completed_all_form4_recovery_v3",
]
