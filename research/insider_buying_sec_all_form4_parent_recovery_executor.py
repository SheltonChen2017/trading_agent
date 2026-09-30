"""Fail-closed v3 continuation executor for a source-bound parent campaign.

The public executable path is synthetic and receives an injected transport.
Callers of that test seam must supply an offline fake; an arbitrary callback
cannot be proven network-free merely by checking its function identity.
The observed SEC entry is deliberately disabled until source rights and
publication/PIT gates are evidenced.  An interrupted request-start is never
interpreted as permission to send its URL again.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable
from datetime import datetime
import http.client
import os
import re
import stat
import time

from data.hashing import hash_bytes, hash_payload
from research.insider_buying_sec_acquisition import (
    SecPilotError, _plain_path, _publish_immutable, _refuse_output_overlap,
    _store_object,
)
from research.insider_buying_sec_complete_acquisition import (
    MAX_COMPLETE_TXT_BYTES, SecCompleteAcquisitionError, SecHttpResult,
)
from research.insider_buying_sec_master82_runner import _RootLock
from research.insider_buying_sec_selected_parent_runner import (
    SecSelectedParentRunnerError, _Events, _strict_selected_response, _utc,
)
import research.insider_buying_sec_all_form4_parent_campaign as campaign
import research.insider_buying_sec_all_form4_parent_recovery_campaign as recovery
import research.insider_buying_sec_all_form4_parent_recovery_preflight as partial
import research.insider_buying_sec_all_form4_parent_recovery_union as union


EXECUTOR_VERSION = "INSETF-SEC-ALL-FORM4-PARENTS-RECOVERY-EXECUTOR-v1"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_CONTACT = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}\Z")
_RETRY = frozenset({500, 502, 503, 504})
_PLAN_MAX = 256 * 1024


class RecoveryExecutorError(ValueError):
    """An executable continuation boundary refused without broadening scope."""


def _refuse(reason: str) -> None:
    raise RecoveryExecutorError(f"REFUSED: {reason}")


def _bytes(value: object) -> bytes:
    return campaign._bytes(value)


def _recover(path: Path, *, cap: int, label: str, expected: bytes | None = None) -> bytes:
    return campaign._recover(path, label=label, max_bytes=cap, expected_raw=expected)


def _publish(root: Path, identity: tuple[int, int], name: str, raw: bytes,
             *, cap: int) -> None:
    if len(raw) > cap:
        _refuse("publication exceeds its byte cap")
    if (root / name).exists() or (root / name).is_symlink():
        _recover(root / name, cap=cap, label="v3 immutable publication", expected=raw)
    else:
        _publish_immutable(root, name, raw, identity)


def _source_and_plan(
    plan: campaign.CampaignPlan, prior_campaign_root: str | Path,
    diagnostic_root: str | Path, selected_root: str | Path, output_root: str | Path,
    *, prior_expectation: partial.PartialCampaignExpectation,
    diagnostic_capture_git_commit: str, expected_diagnostic_report_sha256: str,
    diagnostic_mode: str, capture_git_commit: str, resume: bool,
) -> tuple[Path, dict[str, object], bytes, tuple[tuple[dict[str, object], bytes], ...]]:
    """Revalidate all external sources and construct exact immutable inventories."""
    if (type(plan) is not campaign.CampaignPlan or type(resume) is not bool
            or type(capture_git_commit) is not str
            or _COMMIT.fullmatch(capture_git_commit) is None):
        _refuse("source plan or code identity is malformed")
    plan_payload = plan.to_payload()
    receipt = union.preflight_source_union(
        plan, prior_campaign_root, diagnostic_root, selected_root,
        prior_expectation=prior_expectation,
        diagnostic_capture_git_commit=diagnostic_capture_git_commit,
        expected_diagnostic_report_sha256=expected_diagnostic_report_sha256,
        diagnostic_mode=diagnostic_mode,
    )
    classes, dispatch = recovery._source_layout(plan, receipt)
    output = _plain_path(output_root, must_exist=resume)
    source_paths = tuple(_plain_path(path, must_exist=True) for path in (
        prior_campaign_root, diagnostic_root, selected_root,
    ))
    for protected in (*source_paths, Path(__file__).resolve().parents[1]):
        _refuse_output_overlap(output, protected)
    if not resume and (output.exists() or output.is_symlink()):
        _refuse("new v3 output root already exists")
    if plan.scope == "ib1b_observed_full_form4_noncanonical":
        _refuse("observed SEC continuation is gated off pending rights and PIT evidence")
    if plan.scope != "synthetic_test_manifest":
        _refuse("v3 synthetic executor requires a synthetic-only source plan")
    if (receipt["total_parents"] != len(plan.requests)
            or receipt["later_unattempted_request_count"] != len(dispatch)):
        _refuse("source-union population changed")
    plan_body: dict[str, object] = {
        "kind": EXECUTOR_VERSION + "/plan", "source_scope": plan.scope,
        "capture_git_commit": capture_git_commit,
        "capture_code_sha256": hash_bytes(Path(__file__).read_bytes()),
        "manifest_sha256": plan.manifest_sha256,
        "request_inventory_sha256": plan_payload["request_inventory_sha256"],
        "source_assignment_sha256": receipt["source_assignment_sha256"],
        "later_unattempted_request_inventory_sha256": receipt[
            "later_unattempted_request_inventory_sha256"],
        "prior_campaign_root": str(source_paths[0]),
        "diagnostic_root": str(source_paths[1]),
        "selected_root": str(source_paths[2]),
        "prior_expectation": {
            "capture_git_commit": prior_expectation.capture_git_commit,
            "shard_report_sha256s": list(prior_expectation.shard_report_sha256s),
            "completed_counts": list(prior_expectation.completed_counts),
            "reused_counts": list(prior_expectation.reused_counts),
            "total_attempt_count": prior_expectation.total_attempt_count,
        },
        "prior_campaign_plan_sha256": receipt["prior_campaign_plan_sha256"],
        "prior_shard_journal_sha256s": list(receipt["prior_shard_journal_sha256s"]),
        "diagnostic_capture_git_commit": diagnostic_capture_git_commit,
        "diagnostic_report_sha256": expected_diagnostic_report_sha256,
        "diagnostic_mode": diagnostic_mode,
        "original_diagnostic_envelope_outcome": receipt[
            "original_diagnostic_envelope_outcome"],
        "offline_correction_receipt_sha256": receipt[
            "offline_correction_receipt_sha256"],
        "selected_report_sha256": plan.selected_report_sha256,
        "selected_receipt_lineage_sha256": plan.selected_receipt_lineage_sha256,
        "total_parents": len(plan.requests),
        "prior_completed_count": receipt["prior_completed_count"],
        "accepted_diagnostic_count": receipt["accepted_diagnostic_count"],
        "offline_corrected_diagnostic_count": receipt[
            "offline_corrected_diagnostic_count"],
        "remaining_selected_reuse_count": receipt["remaining_selected_reuse_count"],
        "later_unattempted_request_count": len(dispatch),
        "shard_size": plan.shard_size,
        "max_attempts_per_parent": campaign.MAX_ATTEMPTS,
        "minimum_request_interval_ns": campaign.MIN_REQUEST_INTERVAL_NS,
        "source_authenticated": False, "canonical_evidence": False,
        "point_in_time_data": False, "outcome_looks": 0, "qc_jobs": 0,
    }
    # The plan hash binds source provenance; shard inventories bind that hash.
    source_plan_sha = hash_payload(plan_body)
    inventories: list[tuple[dict[str, object], bytes]] = []
    requests = plan_payload["requests"]
    for shard_number, start in enumerate(range(0, len(requests), plan.shard_size)):
        these = requests[start:start + plan.shard_size]
        sources = classes[start:start + len(these)]
        rows = [{"global_index": start + offset, "request": request,
                 "source_class": source}
                for offset, (request, source) in enumerate(zip(
                    these, sources, strict=True,
                ))]
        later = [request for request, source in zip(these, sources, strict=True)
                 if source == "later_unattempted"]
        inventory = {
            "kind": EXECUTOR_VERSION + "/shard-inventory",
            "source_plan_sha256": source_plan_sha,
            "name": f"shard-{shard_number:04d}", "start": start,
            "count": len(rows), "rows": rows,
            "request_inventory_sha256": hash_payload(these),
            "source_assignment_sha256": hash_payload(sources),
            "later_unattempted_request_inventory_sha256": hash_payload(later),
        }
        raw = _bytes(inventory)
        if len(raw) > campaign.MAX_SHARD_INVENTORY_BYTES:
            _refuse("v3 shard inventory exceeds its byte cap")
        inventories.append((inventory, raw))
    plan_body["shards"] = [{"name": item["name"], "start": item["start"],
                            "count": item["count"], "inventory_sha256": hash_bytes(raw)}
                           for item, raw in inventories]
    plan_body["source_plan_sha256"] = source_plan_sha
    plan_raw = _bytes(plan_body)
    if (len(plan_raw) > _PLAN_MAX or len(inventories) > campaign.MAX_SHARDS
            or sum(item["count"] for item, _ in inventories) != len(plan.requests)):
        _refuse("v3 root plan exceeds its frozen bounds")
    return output, plan_body, plan_raw, tuple(inventories)


def _read_object(shard: Path, digest: object, size: object) -> bytes:
    if (type(digest) is not str or _SHA.fullmatch(digest) is None
            or type(size) is not int or not 0 < size <= MAX_COMPLETE_TXT_BYTES):
        _refuse("v3 object descriptor is malformed")
    raw = _recover(shard / "objects" / f"{digest}.bin", cap=MAX_COMPLETE_TXT_BYTES,
                   label="v3 parent object")
    if len(raw) != size or hash_bytes(raw) != digest:
        _refuse("v3 parent object bytes changed")
    return raw


def _require_private_members(directory: Path, *, recurse_objects: bool = False) -> None:
    """Reject broadened modes, links, or symlinks before trusting local custody."""
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
        _refuse("v3 directory is not private")
    for member in directory.iterdir():
        info = member.lstat()
        if member.name == "objects" and recurse_objects:
            _require_private_members(member)
        elif stat.S_ISDIR(info.st_mode):
            if stat.S_IMODE(info.st_mode) != 0o700:
                _refuse("v3 shard directory is not private")
        elif (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
              or stat.S_IMODE(info.st_mode) != 0o600):
            _refuse("v3 metadata or object is not a private single-link file")


def _state(inventory: dict[str, object], parsed: list[dict[str, object]], shard: Path
           ) -> tuple[dict[int, dict[str, object]], dict[int, int],
                      dict[str, object] | None, dict[str, object] | None, str | None]:
    """Replay only later-unattempted requests; all other classes stay external."""
    later = [row for row in inventory["rows"]
             if row["source_class"] == "later_unattempted"]
    completed: dict[int, dict[str, object]] = {}
    attempts: dict[int, int] = {}
    pending_start: dict[str, object] | None = None
    pending_valid: dict[str, object] | None = None
    terminal: str | None = None
    retry_allowed = True
    ordinal = 0
    for event in parsed:
        if type(event) is not dict or terminal is not None or len(completed) >= len(later):
            _refuse("v3 event follows terminal or complete shard")
        row = later[len(completed)]
        index = row["global_index"]
        request = row["request"]
        if (type(event.get("global_index")) is not int
                or event.get("global_index") != index
                or event.get("accession_number") != request["accession_number"]):
            _refuse("v3 event differs from ordered later request")
        kind = event.get("kind")
        if kind == "attempt-start":
            count = attempts.get(index, 0) + 1
            ordinal += 1
            if (pending_start is not None or pending_valid is not None
                    or not retry_allowed or count > campaign.MAX_ATTEMPTS
                    or set(event) != {"kind", "prev_sha256", "global_index",
                                      "accession_number", "ordinal", "attempt",
                                      "url", "started_utc"}
                    or type(event["ordinal"]) is not int
                    or type(event["attempt"]) is not int
                    or event["ordinal"] != ordinal or event["attempt"] != count
                    or event["url"] != request["url"]):
                _refuse("v3 attempt reservation violates frozen inventory")
            campaign._check_utc(event["started_utc"])
            attempts[index] = count
            pending_start = event
            retry_allowed = False
        elif kind == "attempt-finish":
            if (pending_start is None or pending_valid is not None
                    or set(event) != {"kind", "prev_sha256", "global_index",
                                      "accession_number", "ordinal", "outcome",
                                      "status", "body_sha256", "body_size_bytes",
                                      "framing_headers", "finished_utc"}
                    or type(event["ordinal"]) is not int
                    or event["ordinal"] != pending_start["ordinal"]):
                _refuse("v3 response has no exact durable start")
            campaign._check_utc(event["finished_utc"])
            if (datetime.fromisoformat(event["finished_utc"])
                    < datetime.fromisoformat(pending_start["started_utc"])):
                _refuse("v3 response clock precedes its durable attempt start")
            outcome = event["outcome"]
            if outcome in {"valid_response", "source_envelope_refusal",
                           "framing_refusal"}:
                if (type(event["status"]) is not int or event["status"] != 200
                        or type(event["framing_headers"]) is not list
                        or any(type(pair) is not list or len(pair) != 2
                               or type(pair[0]) is not str or type(pair[1]) is not str
                               for pair in event["framing_headers"])):
                    _refuse("v3 HTTP 200 response descriptor is malformed")
                raw = _read_object(shard, event["body_sha256"],
                                   event["body_size_bytes"])
                response = SecHttpResult(
                    status=200, headers=tuple(tuple(pair) for pair in event["framing_headers"]),
                    body=raw,
                )
                if outcome != "framing_refusal":
                    try:
                        framed = _strict_selected_response(
                            response, max_bytes=MAX_COMPLETE_TXT_BYTES,
                        )
                    except SecCompleteAcquisitionError as exc:
                        raise RecoveryExecutorError(
                            "REFUSED: v3 event claims invalid response framing"
                        ) from exc
                    if framed != raw:
                        _refuse("v3 framed bytes changed")
                if outcome == "valid_response":
                    campaign._validate_parent_header(raw, request)
                    pending_valid = event
                else:
                    terminal = "REFUSED: v3 HTTP 200 parent is not validated"
            elif outcome == "http_error":
                status = event["status"]
                if (type(status) is not int or status == 200
                        or event["body_sha256"] is not None
                        or event["body_size_bytes"] is not None
                        or event["framing_headers"] is not None):
                    _refuse("v3 HTTP error descriptor is malformed")
                if status in _RETRY and attempts[index] < campaign.MAX_ATTEMPTS:
                    retry_allowed = True
                else:
                    terminal = "REFUSED: v3 HTTP status is terminal or attempts consumed"
            else:
                _refuse("v3 attempt outcome is unrecognized")
            pending_start = None
        elif kind == "item-complete":
            if (pending_start is not None or pending_valid is None
                    or set(event) != {"kind", "prev_sha256", "global_index",
                                      "accession_number", "source", "object_sha256",
                                      "object_size_bytes"}
                    or event["source"] != "new_acquired"
                    or event["object_sha256"] != pending_valid["body_sha256"]
                    or event["object_size_bytes"] != pending_valid["body_size_bytes"]):
                _refuse("v3 item completion lacks an exact validated response")
            _read_object(shard, event["object_sha256"], event["object_size_bytes"])
            completed[index] = event
            pending_valid = None
            retry_allowed = True
        else:
            _refuse("v3 event kind is unknown")
    return completed, attempts, pending_start, pending_valid, terminal


def _report(inventory: dict[str, object], raw_inventory: bytes, events: _Events,
            completed: dict[int, dict[str, object]], attempts: dict[int, int],
            reason: str | None) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for row in inventory["rows"]:
        index = row["global_index"]
        source = row["source_class"]
        event = completed.get(index)
        item: dict[str, object] = {"global_index": index, "source_class": source,
                                   "attempts": attempts.get(index, 0),
                                   "status": "source_bound" if source != "later_unattempted"
                                   else "not_attempted"}
        if event is not None:
            item.update({"status": "raw_acquired_noncanonical",
                         "raw_object": {"relative_path": f'objects/{event["object_sha256"]}.bin',
                                        "sha256": event["object_sha256"],
                                        "size_bytes": event["object_size_bytes"]}})
        elif source == "later_unattempted" and reason is not None:
            if index == next((r["global_index"] for r in inventory["rows"]
                              if r["source_class"] == "later_unattempted"
                              and r["global_index"] not in completed), None):
                item.update({"status": "refused", "reason": reason})
        rows.append(item)
    journal = b"".join(events.raw)
    source_bound = sum(row["source_class"] != "later_unattempted"
                       for row in inventory["rows"])
    return {
        "kind": EXECUTOR_VERSION + "/shard-report",
        "source_plan_sha256": inventory["source_plan_sha256"],
        "inventory_sha256": hash_bytes(raw_inventory),
        "name": inventory["name"], "start": inventory["start"],
        "count": inventory["count"],
        "attempt_journal_sha256": hash_bytes(journal),
        "attempt_event_count": len(events.raw),
        "attempt_count": sum(attempts.values()),
        "new_acquired_count": len(completed),
        "source_bound_count": source_bound,
        "complete_count": source_bound + len(completed),
        "rows": rows, "halted_reason": reason,
        "complete_shard_raw_set_acquired": reason is None
        and source_bound + len(completed) == inventory["count"],
        "source_authenticated": False, "canonical_evidence": False,
        "point_in_time_data": False, "outcome_looks": 0, "qc_jobs": 0,
    }


def _expected_shard_members(events: _Events, report_name: str | None) -> tuple[set[str], set[str]]:
    names = {"run.lock", "inventory.json", "objects"}
    names.update(f"event-{i:06d}-{hash_bytes(raw)}.json"
                 for i, raw in enumerate(events.raw, 1))
    if report_name is not None:
        names.update({"attempts.jsonl", report_name, "commit.json"})
    objects = set()
    for raw in events.raw:
        event = campaign._json(raw, label="v3 event")
        if event["kind"] == "attempt-finish" and event["body_sha256"] is not None:
            objects.add(event["body_sha256"] + ".bin")
    return names, objects


def _check_shard_members(shard: Path, events: _Events, report_name: str | None) -> None:
    names, objects = _expected_shard_members(events, report_name)
    if set(os.listdir(shard)) != names or set(os.listdir(shard / "objects")) != objects:
        _refuse("v3 shard has missing or extra immutable members")


def _run_shard(root: Path, root_identity: tuple[int, int],
               inventory: dict[str, object], raw_inventory: bytes,
               transport: Callable[[str, dict[str, str], int], SecHttpResult],
               *, contact_email: str, resume: bool, used_bytes: int,
               last_completion_ns: int | None,
               ) -> tuple[dict[str, object], str, int, int | None]:
    shard = root / inventory["name"]
    exists = shard.exists() or shard.is_symlink()
    if exists and not resume:
        _refuse("new v3 shard already exists")
    if not exists:
        shard.mkdir(mode=0o700)
        directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    info = shard.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
        _refuse("v3 shard is not a private directory")
    identity = info.st_dev, info.st_ino
    prior_names = set(os.listdir(shard)) if exists else set()
    lock = _RootLock(shard, identity, resume=bool(prior_names))
    try:
        if "inventory.json" in prior_names:
            _recover(shard / "inventory.json", cap=campaign.MAX_SHARD_INVENTORY_BYTES,
                     label="v3 shard inventory", expected=raw_inventory)
        elif prior_names in (set(), {"run.lock"}):
            (shard / "objects").mkdir(mode=0o700)
            directory_fd = os.open(shard, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            _publish(shard, identity, "inventory.json", raw_inventory,
                     cap=campaign.MAX_SHARD_INVENTORY_BYTES)
        else:
            _refuse("v3 pre-inventory shard has unexpected members")
        object_info = (shard / "objects").lstat()
        if not stat.S_ISDIR(object_info.st_mode) or stat.S_IMODE(object_info.st_mode) != 0o700:
            _refuse("v3 object directory is not private")
        events = _Events(shard, identity, hash_bytes(raw_inventory))
        try:
            parsed = events.load() if "inventory.json" in prior_names else []
        except SecSelectedParentRunnerError as exc:
            raise RecoveryExecutorError("REFUSED: v3 event chain changed") from exc
        _require_private_members(shard, recurse_objects=True)
        completed, attempts, pending_start, pending_valid, terminal = _state(
            inventory, parsed, shard,
        )
        if (shard / "commit.json").exists():
            if pending_start is not None or pending_valid is not None:
                _refuse("committed v3 shard contains an unfinished attempt")
            report = _report(inventory, raw_inventory, events, completed, attempts, terminal)
            raw_report = _bytes(report)
            digest = hash_bytes(raw_report)
            name = f"shard-report-{digest}.json"
            journal = b"".join(events.raw)
            expected_commit = {"kind": EXECUTOR_VERSION + "/shard-commit",
                               "report_name": name, "report_sha256": digest,
                               "inventory_sha256": report["inventory_sha256"],
                               "attempt_journal_sha256": report["attempt_journal_sha256"]}
            if (campaign._json(_recover(shard / "commit.json", cap=4096,
                                        label="v3 shard commit"), label="v3 shard commit")
                    != expected_commit):
                _refuse("v3 shard commit differs from replayed source")
            _recover(shard / name, cap=campaign.MAX_SHARD_REPORT_BYTES,
                     label="v3 shard report", expected=raw_report)
            _recover(shard / "attempts.jsonl", cap=campaign.MAX_SHARD_JOURNAL_BYTES,
                     label="v3 shard journal", expected=journal)
            _check_shard_members(shard, events, name)
            if not report["complete_shard_raw_set_acquired"]:
                _refuse("terminal incomplete v3 shard cannot be resumed")
            return report, digest, used_bytes + sum(
                event["object_size_bytes"] for event in completed.values()
            ), last_completion_ns
        if pending_start is not None:
            _refuse("ambiguous durable v3 attempt-start cannot be redispatched")
        if pending_valid is not None:
            # A fsynced valid response can be completed without new transport.
            row = next(row for row in inventory["rows"]
                       if row["global_index"] == pending_valid["global_index"])
            raw = _read_object(shard, pending_valid["body_sha256"],
                               pending_valid["body_size_bytes"])
            campaign._validate_parent_header(raw, row["request"])
            events.append({"kind": "item-complete",
                           "global_index": row["global_index"],
                           "accession_number": row["request"]["accession_number"],
                           "source": "new_acquired",
                           "object_sha256": pending_valid["body_sha256"],
                           "object_size_bytes": pending_valid["body_size_bytes"]})
            parsed = [campaign._json(raw, label="v3 event") for raw in events.raw]
            completed, attempts, _, _, terminal = _state(inventory, parsed, shard)
        reason: str | None = terminal
        if resume and reason is None and len(completed) < sum(
                row["source_class"] == "later_unattempted" for row in inventory["rows"]):
            time.sleep(1.5)
        used_bytes += sum(item["object_size_bytes"] for item in completed.values())
        later = [row for row in inventory["rows"]
                 if row["source_class"] == "later_unattempted"]
        while reason is None and len(completed) < len(later):
            row = later[len(completed)]
            index = row["global_index"]
            request = row["request"]
            if not campaign._capacity_ok(root, root_identity, used_bytes):
                _refuse("capacity pause before v3 SEC dispatch")
            attempt = attempts.get(index, 0) + 1
            if attempt > campaign.MAX_ATTEMPTS:
                reason = "REFUSED: v3 parent attempt ceiling consumed"
                break
            now = time.monotonic_ns()
            earliest = max(now, last_completion_ns + campaign.MIN_REQUEST_INTERVAL_NS
                           if last_completion_ns is not None else now)
            if attempt > 1:
                earliest = max(earliest, now + (attempt - 1) * 1_000_000_000)
            remaining = earliest - time.monotonic_ns()
            if remaining > 0:
                time.sleep(remaining / 1_000_000_000)
            ordinal = sum(attempts.values()) + 1
            events.append({"kind": "attempt-start", "global_index": index,
                           "accession_number": request["accession_number"],
                           "ordinal": ordinal, "attempt": attempt,
                           "url": request["url"], "started_utc": _utc()})
            if time.monotonic_ns() < earliest:
                _refuse("v3 dispatch pacing was too early")
            headers = {"User-Agent": f"InsiderBuyingResearch/0.1 ({contact_email})",
                       "Accept": "*/*", "Accept-Encoding": "identity",
                       "Connection": "close"}
            # A timeout or exception after dispatch is ambiguous. Leave the
            # fsynced start unresolved and refuse all future redispatch.
            try:
                result = transport(request["url"], headers, MAX_COMPLETE_TXT_BYTES)
            except (OSError, http.client.HTTPException, SecCompleteAcquisitionError) as exc:
                raise RecoveryExecutorError(
                    "REFUSED: v3 transport result is ambiguous; start remains unresolved"
                ) from exc
            last_completion_ns = time.monotonic_ns()
            if type(result) is not SecHttpResult or type(result.status) is not int:
                _refuse("v3 transport result is malformed; start remains unresolved")
            framing_headers = [[key, value] for key, value in result.headers
                               if key.lower() in {"content-length", "transfer-encoding",
                                                  "content-encoding"}]
            if result.status != 200:
                if result.body != b"":
                    _refuse("v3 non-200 body is ambiguous; start remains unresolved")
                outcome = "http_error"
                digest = size = None
                framing_headers = None
            else:
                if (type(result.body) is not bytes
                        or not 0 < len(result.body) <= MAX_COMPLETE_TXT_BYTES):
                    _refuse("v3 HTTP 200 body is unbounded; start remains unresolved")
                descriptor = _store_object(shard, result.body, identity)
                digest, size = descriptor["sha256"], descriptor["size_bytes"]
                used_bytes += size
                try:
                    _strict_selected_response(result, max_bytes=MAX_COMPLETE_TXT_BYTES)
                except SecCompleteAcquisitionError:
                    outcome = "framing_refusal"
                else:
                    try:
                        campaign._validate_parent_header(result.body, request)
                    except campaign.CampaignError:
                        outcome = "source_envelope_refusal"
                    else:
                        outcome = "valid_response"
            events.append({"kind": "attempt-finish", "global_index": index,
                           "accession_number": request["accession_number"],
                           "ordinal": ordinal, "outcome": outcome,
                           "status": result.status, "body_sha256": digest,
                           "body_size_bytes": size,
                           "framing_headers": framing_headers,
                           "finished_utc": _utc()})
            attempts[index] = attempt
            if outcome == "valid_response":
                events.append({"kind": "item-complete", "global_index": index,
                               "accession_number": request["accession_number"],
                               "source": "new_acquired", "object_sha256": digest,
                               "object_size_bytes": size})
                completed[index] = campaign._json(events.raw[-1], label="v3 event")
            elif outcome == "http_error" and result.status in _RETRY and attempt < campaign.MAX_ATTEMPTS:
                continue
            else:
                reason = "REFUSED: v3 response did not validate or attempts consumed"
                break
        replay = [campaign._json(raw, label="v3 event") for raw in events.raw]
        checked, final_attempts, pending_start, pending_valid, terminal = _state(
            inventory, replay, shard,
        )
        if (checked != completed or final_attempts != attempts
                or pending_start is not None or pending_valid is not None
                or (reason is None) != (terminal is None)):
            _refuse("v3 final journal differs from in-memory state")
        # Persist the reason reproduced from the immutable event sequence,
        # not an in-memory exception summary that could drift on resume.
        reason = terminal
        if reason is None and len(completed) != len(later):
            _refuse("v3 shard stopped without a complete source assignment")
        report = _report(inventory, raw_inventory, events, checked, final_attempts,
                         reason)
        journal = b"".join(events.raw)
        _publish(shard, identity, "attempts.jsonl", journal,
                 cap=campaign.MAX_SHARD_JOURNAL_BYTES)
        raw_report = _bytes(report)
        digest = hash_bytes(raw_report)
        report_name = f"shard-report-{digest}.json"
        _publish(shard, identity, report_name, raw_report,
                 cap=campaign.MAX_SHARD_REPORT_BYTES)
        commit = {"kind": EXECUTOR_VERSION + "/shard-commit",
                  "report_name": report_name, "report_sha256": digest,
                  "inventory_sha256": report["inventory_sha256"],
                  "attempt_journal_sha256": report["attempt_journal_sha256"]}
        _publish(shard, identity, "commit.json", _bytes(commit), cap=4096)
        _check_shard_members(shard, events, report_name)
        _require_private_members(shard, recurse_objects=True)
        if not report["complete_shard_raw_set_acquired"]:
            _refuse("v3 shard ended incomplete; continuation cannot advance")
        return report, digest, used_bytes, last_completion_ns
    finally:
        lock.close()


def _run(
    plan: campaign.CampaignPlan, prior_campaign_root: str | Path,
    diagnostic_root: str | Path, selected_root: str | Path, output_root: str | Path,
    *, prior_expectation: partial.PartialCampaignExpectation,
    diagnostic_capture_git_commit: str, expected_diagnostic_report_sha256: str,
    diagnostic_mode: str, capture_git_commit: str,
    transport: Callable[[str, dict[str, str], int], SecHttpResult],
    contact_email: str, resume: bool,
) -> Path:
    if (type(contact_email) is not str or _CONTACT.fullmatch(contact_email) is None
            or not contact_email.isascii() or len(contact_email) > 254
            or not callable(transport) or transport is campaign._selected_sec_transport):
        _refuse("synthetic contact or injected transport is invalid")
    output, plan_body, plan_raw, inventories = _source_and_plan(
        plan, prior_campaign_root, diagnostic_root, selected_root, output_root,
        prior_expectation=prior_expectation,
        diagnostic_capture_git_commit=diagnostic_capture_git_commit,
        expected_diagnostic_report_sha256=expected_diagnostic_report_sha256,
        diagnostic_mode=diagnostic_mode, capture_git_commit=capture_git_commit,
        resume=resume,
    )
    if resume:
        info = output.lstat()
    else:
        output.mkdir(mode=0o700)
        parent_fd = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(parent_fd)
            opened = os.fstat(parent_fd)
            named = output.parent.lstat()
            if (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino):
                _refuse("v3 output parent changed before durable reservation")
        finally:
            os.close(parent_fd)
        info = output.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
        _refuse("v3 output root is not private")
    identity = info.st_dev, info.st_ino
    prior_names = set(os.listdir(output)) if resume else set()
    lock = _RootLock(output, identity, resume=bool(prior_names))
    try:
        if "plan.json" in prior_names:
            _recover(output / "plan.json", cap=_PLAN_MAX, label="v3 root plan",
                     expected=plan_raw)
        elif prior_names in (set(), {"run.lock"}):
            _publish(output, identity, "plan.json", plan_raw, cap=_PLAN_MAX)
        else:
            _refuse("v3 pre-plan root has unexpected members")
        _require_private_members(output)
        if (output / "commit.json").exists():
            _refuse("completed v3 campaign cannot be relaunched")
        allowed = {"run.lock", "plan.json"} | {
            item["name"] for item, _ in inventories
        }
        if not set(os.listdir(output)) <= allowed:
            _refuse("v3 root has unexpected members")
        if resume:
            time.sleep(1.5)
        used_bytes = 0
        last_completion_ns: int | None = None
        shard_summaries: list[dict[str, object]] = []
        for inventory, raw in inventories:
            report, digest, used_bytes, last_completion_ns = _run_shard(
                output, identity, inventory, raw, transport,
                contact_email=contact_email, resume=resume,
                used_bytes=used_bytes, last_completion_ns=last_completion_ns,
            )
            shard_summaries.append({
                "name": inventory["name"], "start": inventory["start"],
                "count": inventory["count"],
                "inventory_sha256": hash_bytes(raw),
                "report_sha256": digest,
                "attempt_count": report["attempt_count"],
                "new_acquired_count": report["new_acquired_count"],
                "source_bound_count": report["source_bound_count"],
            })
        # This is intentionally expensive. The external old, diagnostic, and
        # selected roots are read-only inputs but are not held under one lock
        # for the entire multi-hour campaign. Replaying their exact bytes at
        # the final publication point prevents a mid-run source edit from
        # producing a seemingly complete v3 root.
        _, _, final_plan_raw, final_inventories = _source_and_plan(
            plan, prior_campaign_root, diagnostic_root, selected_root, output,
            prior_expectation=prior_expectation,
            diagnostic_capture_git_commit=diagnostic_capture_git_commit,
            expected_diagnostic_report_sha256=expected_diagnostic_report_sha256,
            diagnostic_mode=diagnostic_mode,
            capture_git_commit=capture_git_commit, resume=True,
        )
        if (final_plan_raw != plan_raw
                or [raw for _, raw in final_inventories]
                != [raw for _, raw in inventories]):
            _refuse("v3 source union changed before final report")
        report = {
            "kind": EXECUTOR_VERSION + "/campaign-report",
            "plan_sha256": hash_bytes(plan_raw),
            "source_plan_sha256": plan_body["source_plan_sha256"],
            "manifest_sha256": plan_body["manifest_sha256"],
            "request_inventory_sha256": plan_body["request_inventory_sha256"],
            "source_assignment_sha256": plan_body["source_assignment_sha256"],
            "later_unattempted_request_inventory_sha256": plan_body[
                "later_unattempted_request_inventory_sha256"],
            "total_parents": plan_body["total_parents"],
            "prior_completed_count": plan_body["prior_completed_count"],
            "accepted_diagnostic_count": plan_body["accepted_diagnostic_count"],
            "offline_corrected_diagnostic_count": plan_body[
                "offline_corrected_diagnostic_count"],
            "remaining_selected_reuse_count": plan_body["remaining_selected_reuse_count"],
            "later_acquired_count": sum(item["new_acquired_count"]
                                        for item in shard_summaries),
            "new_attempt_count": sum(item["attempt_count"] for item in shard_summaries),
            "shards": shard_summaries,
            "complete_parent_bytes_acquired": True,
            "source_authenticated": False, "canonical_evidence": False,
            "point_in_time_data": False, "outcome_looks": 0, "qc_jobs": 0,
        }
        if (report["prior_completed_count"] + report["accepted_diagnostic_count"]
                + report["offline_corrected_diagnostic_count"]
                + report["remaining_selected_reuse_count"]
                + report["later_acquired_count"] != report["total_parents"]):
            _refuse("v3 completed union does not equal its frozen denominator")
        raw_report = _bytes(report)
        digest = hash_bytes(raw_report)
        name = f"campaign-report-{digest}.json"
        _publish(output, identity, name, raw_report, cap=_PLAN_MAX)
        _publish(output, identity, "commit.json", _bytes({
            "kind": EXECUTOR_VERSION + "/campaign-commit",
            "report_name": name, "report_sha256": digest,
            "plan_sha256": hash_bytes(plan_raw),
        }), cap=4096)
        if set(os.listdir(output)) != allowed | {name, "commit.json"}:
            _refuse("v3 completed root has extra or missing members")
        return output / name
    finally:
        lock.close()


def run_synthetic_recovery_continuation(
    plan: campaign.CampaignPlan, prior_campaign_root: str | Path,
    diagnostic_root: str | Path, selected_root: str | Path, output_root: str | Path,
    *, prior_expectation: partial.PartialCampaignExpectation,
    diagnostic_capture_git_commit: str, expected_diagnostic_report_sha256: str,
    diagnostic_mode: str, capture_git_commit: str,
    transport: Callable[[str, dict[str, str], int], SecHttpResult],
    contact_email: str, resume: bool = False,
) -> Path:
    """Execute only a verified synthetic source union with injected transport."""
    try:
        return _run(
            plan, prior_campaign_root, diagnostic_root, selected_root, output_root,
            prior_expectation=prior_expectation,
            diagnostic_capture_git_commit=diagnostic_capture_git_commit,
            expected_diagnostic_report_sha256=expected_diagnostic_report_sha256,
            diagnostic_mode=diagnostic_mode, capture_git_commit=capture_git_commit,
            transport=transport, contact_email=contact_email, resume=resume,
        )
    except RecoveryExecutorError:
        raise
    except (campaign.CampaignError, union.RecoveryUnionError,
            recovery.RecoveryCampaignPlanError, SecPilotError,
            SecSelectedParentRunnerError, OSError, KeyError, TypeError,
            ValueError, RecursionError) as exc:
        raise RecoveryExecutorError("REFUSED: v3 source or journal verification failed") from exc


def run_observed_recovery_continuation(*_args: object, **_kwargs: object) -> None:
    """Real SEC continuation remains closed; no caller can turn on transport."""
    _refuse("observed SEC continuation is gated off pending rights and PIT evidence")


__all__ = ["RecoveryExecutorError", "run_synthetic_recovery_continuation",
           "run_observed_recovery_continuation"]
