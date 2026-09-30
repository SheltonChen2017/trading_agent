"""Read-only replay of one stopped v3 campaign with a final ambiguous start.

This receipt identifies one already-attempted parent for a separately
authorized diagnostic. It does not complete, resume, repair, or dispatch the
v3 campaign, and it never establishes SEC authenticity or point-in-time data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import subprocess

from data.hashing import hash_bytes, hash_payload
from research.insider_buying_sec_acquisition import SecPilotError, _plain_path, _refuse_output_overlap
from research.insider_buying_sec_complete_acquisition import (
    MAX_COMPLETE_TXT_BYTES, SecCompleteAcquisitionError, SecHttpResult,
)
from research.insider_buying_sec_selected_parent_runner import _strict_selected_response
import research.insider_buying_sec_all_form4_parent_campaign as campaign
import research.insider_buying_sec_all_form4_parent_recovery_preflight as partial
import research.insider_buying_sec_all_form4_parent_recovery_union as source_union
import research.insider_buying_sec_all_form4_parent_recovery_verifier as verifier


PARTIAL_VERIFIER_VERSION = "INSETF-SEC-ALL-FORM4-PARENTS-RECOVERY-PARTIAL-VERIFIER-v1"
OBSERVED_V3_CAPTURE_COMMIT = "aa0d635d00b64825bf8003289e0a60279bd52e73"
OBSERVED_V3_EXECUTOR_SHA256 = "6305c604e78df1eed14eeb8d269cbcc07a881405e16611abf8f46e5a07be986d"
OBSERVED_V3_ROOT_PLAN_SHA256 = "f8f1d26f93f9f7e5a5fa90c0867231519b0c6c791cdc0cdc50cc165072889f41"
OBSERVED_V3_ACTIVE_JOURNAL_SHA256 = "3decc20fec36eb7bcebdf57893cc1194e0df5414f1a3143f4d0de18a5ffda6ae"
OBSERVED_V3_PENDING_START_SHA256 = "789f9595c35cf44a5974bbf62a20011480f6cb50387fa7dc142316a9a95ebb4b"
OBSERVED_SOURCE_ASSIGNMENT_SHA256 = "9c497cabeff43a40f01b8da916264cc140088a356dc18233c660e91d7a6552d2"
OBSERVED_LATER_INVENTORY_SHA256 = "2318bafbe7eec167b545b747ce5a7923fcb5dbef34bd38aca27c95bd3d7f52b8"
OBSERVED_LANE_ROOT = Path(
    "/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying"
)
OBSERVED_PRIOR_ROOT = Path(
    "/Users/sheltonchen/Documents/Codex/2026-09-03/f/"
    "insider-source-allparents-20260929.3Nut2i/all-form4-parents"
)
OBSERVED_DIAGNOSTIC_ROOT = OBSERVED_PRIOR_ROOT.parent / "refused-parent-diagnostic-v1"
OBSERVED_SELECTED_ROOT = Path(
    "/Users/sheltonchen/Documents/Codex/2026-09-03/f/"
    "insider-source-20260929.hP4utF/selected-parents-v2"
)
OBSERVED_V3_ROOT = OBSERVED_PRIOR_ROOT.parent / "all-form4-parents-recovery-v3"
_RETRY_HTTP = frozenset({500, 502, 503, 504})


class PartialV3VerificationError(ValueError):
    """The stopped root did not prove one exact unmatched v3 attempt."""


def _refuse(reason: str) -> None:
    raise PartialV3VerificationError(f"REFUSED: {reason}")


@dataclass(frozen=True, slots=True)
class VerifiedPartialV3Receipt:
    """Private request binding from an independently replayed stopped root."""

    pending_request: campaign.CampaignRequest = field(repr=False)
    pending_request_sha256: str = field(repr=False)
    pending_global_index: int = field(repr=False)
    pending_attempt_number: int = field(repr=False)
    pending_shard_name: str = field(repr=False)
    v3_root: Path = field(repr=False)
    capture_git_commit: str = field(repr=False)
    root_plan_sha256: str = field(repr=False)
    source_plan_sha256: str = field(repr=False)
    pending_shard_inventory_sha256: str = field(repr=False)
    pending_shard_journal_sha256: str = field(repr=False)
    pending_attempt_start_sha256: str = field(repr=False)
    completed_new_count: int = field(repr=False)
    attempt_count: int = field(repr=False)
    source_assignment_sha256: str = field(repr=False)


def _require_observed_anchors(receipt: VerifiedPartialV3Receipt) -> None:
    """Compare replayed custody with the independently recorded stopped root."""
    if (type(receipt) is not VerifiedPartialV3Receipt
            or receipt.root_plan_sha256 != OBSERVED_V3_ROOT_PLAN_SHA256
            or receipt.pending_shard_journal_sha256
            != OBSERVED_V3_ACTIVE_JOURNAL_SHA256
            or receipt.pending_attempt_start_sha256
            != OBSERVED_V3_PENDING_START_SHA256):
        _refuse("observed stopped v3 byte anchors changed")


def _replay_active_shard(
    shard: campaign._ReadOnlyDirectory,
    inventory: dict[str, object],
    raw_inventory: bytes,
) -> tuple[int, int, int, dict[str, object], bytes, str]:
    """Replay successful earlier responses and exactly one terminal start."""
    verifier._empty_file(shard, "run.lock")
    if verifier._read(
        shard, "inventory.json", max_bytes=verifier._MAX_INVENTORY_BYTES,
    ) != raw_inventory:
        _refuse("active v3 inventory differs from frozen source")
    events, raw_events, event_names = verifier._read_events(shard, raw_inventory)
    if not events or events[-1].get("kind") != "attempt-start":
        _refuse("active v3 journal lacks one final durable attempt-start")
    later = [row for row in inventory["rows"]
             if row["source_class"] == "later_unattempted"]
    completed = 0
    attempts: dict[int, int] = {}
    object_names: set[str] = set()
    object_bytes = 0
    pending_start: dict[str, object] | None = None
    pending_valid: dict[str, object] | None = None
    retry_allowed = True
    ordinal = 0
    with verifier._pinned_directory(shard.path / "objects") as objects:
        for event in events:
            if type(event) is not dict or completed >= len(later):
                _refuse("active v3 event exceeds ordered source inventory")
            row = later[completed]
            index = row["global_index"]
            request = row["request"]
            if (type(event.get("global_index")) is not int
                    or event["global_index"] != index
                    or event.get("accession_number") != request["accession_number"]):
                _refuse("active v3 event differs from ordered source request")
            kind = event.get("kind")
            if kind == "attempt-start":
                count = attempts.get(index, 0) + 1
                ordinal += 1
                if (pending_start is not None or pending_valid is not None
                        or not retry_allowed or count > campaign.MAX_ATTEMPTS
                        or set(event) != {
                            "kind", "prev_sha256", "global_index", "accession_number",
                            "ordinal", "attempt", "url", "started_utc",
                        }
                        or type(event["ordinal"]) is not int
                        or type(event["attempt"]) is not int
                        or event["ordinal"] != ordinal
                        or event["attempt"] != count
                        or event["url"] != request["url"]):
                    _refuse("active v3 start is duplicate or out of order")
                verifier._utc(event["started_utc"])
                attempts[index] = count
                pending_start = event
                retry_allowed = False
            elif kind == "attempt-finish":
                if (pending_start is None or pending_valid is not None
                        or set(event) != {
                            "kind", "prev_sha256", "global_index", "accession_number",
                            "ordinal", "outcome", "status", "body_sha256",
                            "body_size_bytes", "framing_headers", "finished_utc",
                        }
                        or type(event["ordinal"]) is not int
                        or event["ordinal"] != pending_start["ordinal"]):
                    _refuse("active v3 response lacks its exact start")
                verifier._utc(event["finished_utc"])
                if (datetime.fromisoformat(event["finished_utc"])
                        < datetime.fromisoformat(pending_start["started_utc"])):
                    _refuse("active v3 response precedes its start")
                outcome = event["outcome"]
                if outcome == "valid_response":
                    digest = event["body_sha256"]
                    size = event["body_size_bytes"]
                    headers = event["framing_headers"]
                    if (type(event["status"]) is not int or event["status"] != 200
                            or not verifier._sha(digest)
                            or type(size) is not int
                            or not 0 < size <= MAX_COMPLETE_TXT_BYTES
                            or type(headers) is not list
                            or any(type(pair) is not list or len(pair) != 2
                                   or type(pair[0]) is not str or type(pair[1]) is not str
                                   for pair in headers)):
                        _refuse("active v3 valid response descriptor is malformed")
                    body = verifier._read(objects, f"{digest}.bin",
                                          max_bytes=MAX_COMPLETE_TXT_BYTES)
                    if len(body) != size or hash_bytes(body) != digest:
                        _refuse("active v3 response object changed")
                    response = SecHttpResult(
                        status=200, headers=tuple(tuple(pair) for pair in headers),
                        body=body,
                    )
                    try:
                        if _strict_selected_response(
                            response, max_bytes=MAX_COMPLETE_TXT_BYTES,
                        ) != body:
                            _refuse("active v3 response framing changed")
                    except SecCompleteAcquisitionError as exc:
                        raise PartialV3VerificationError(
                            "REFUSED: active v3 response framing is invalid"
                        ) from exc
                    pending_valid = event
                    object_names.add(f"{digest}.bin")
                    object_bytes += size
                elif outcome == "http_error":
                    if (type(event["status"]) is not int
                            or event["status"] not in _RETRY_HTTP
                            or event["body_sha256"] is not None
                            or event["body_size_bytes"] is not None
                            or event["framing_headers"] is not None
                            or attempts[index] >= campaign.MAX_ATTEMPTS):
                        _refuse("active v3 prior response is terminal or ambiguous")
                    retry_allowed = True
                else:
                    _refuse("active v3 prior response did not validate")
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
                    _refuse("active v3 completion lacks its validated response")
                digest = event["object_sha256"]
                body = verifier._read(objects, f"{digest}.bin",
                                      max_bytes=MAX_COMPLETE_TXT_BYTES)
                if len(body) != event["object_size_bytes"] or hash_bytes(body) != digest:
                    _refuse("active v3 completed object changed")
                try:
                    campaign._validate_parent_header(body, request)
                except campaign.CampaignError as exc:
                    raise PartialV3VerificationError(
                        "REFUSED: active v3 parent disagrees with source request"
                    ) from exc
                completed += 1
                pending_valid = None
                retry_allowed = True
            else:
                _refuse("active v3 event kind is unknown")
        if (pending_start is None or pending_valid is not None
                or events[-1] is not pending_start
                or objects.names() != object_names):
            _refuse("active v3 state lacks exactly one unmatched final start")
    expected_names = {"run.lock", "inventory.json", "objects"} | event_names
    if shard.names() != expected_names:
        _refuse("active v3 shard has extra or missing immutable members")
    journal = b"".join(raw_events)
    if len(journal) > verifier._MAX_JOURNAL_BYTES:
        _refuse("active v3 journal exceeds its frozen cap")
    return (completed, sum(attempts.values()), object_bytes, pending_start,
            raw_events[-1], hash_bytes(journal))


def _verify_partial(
    plan: campaign.CampaignPlan,
    receipt: dict[str, object],
    prior_campaign_root: str | Path,
    diagnostic_root: str | Path,
    selected_root: str | Path,
    output_root: str | Path,
    *, prior_expectation: partial.PartialCampaignExpectation,
    capture_git_commit: str,
    capture_code_sha256: str,
) -> VerifiedPartialV3Receipt:
    """Require an exact source plan, completed prefix and one pending start."""
    try:
        plan_body, plan_raw, inventories = verifier._expected_plan(
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
            _refuse_output_overlap(output, _plain_path(protected, must_exist=True))
        if plan.scope == "ib1b_observed_full_form4_noncanonical" and output != OBSERVED_V3_ROOT:
            _refuse("observed stopped v3 root differs from fixed output")
        prior_completed = 0
        prior_attempts = 0
        prior_bytes = 0
        with verifier._pinned_directory(output, lock=True) as root:
            verifier._empty_file(root, "run.lock")
            if verifier._read(root, "plan.json", max_bytes=verifier._MAX_PLAN_BYTES) != plan_raw:
                _refuse("stopped v3 plan differs from frozen source")
            present_shards = [inventory for inventory, _ in inventories
                              if inventory["name"] in root.names()]
            if not present_shards or [item["name"] for item in present_shards] != [
                item["name"] for item, _ in inventories[:len(present_shards)]
            ]:
                _refuse("stopped v3 shards are not a contiguous prefix")
            active_name = present_shards[-1]["name"]
            if root.names() != {"run.lock", "plan.json"} | {
                item["name"] for item in present_shards
            }:
                _refuse("stopped v3 root has an extra or missing member")
            for inventory, raw_inventory in inventories[:len(present_shards) - 1]:
                summary = verifier._verify_shard(output, inventory, raw_inventory)
                prior_completed += summary["new_acquired_count"]
                prior_attempts += summary["attempt_count"]
                prior_bytes += summary["_new_object_bytes"]
            inventory, raw_inventory = inventories[len(present_shards) - 1]
            with verifier._pinned_directory(output / active_name, lock=True) as shard:
                (active_completed, active_attempts, active_bytes, pending,
                 pending_raw, journal_sha) = (
                    _replay_active_shard(shard, inventory, raw_inventory)
                )
            completed = prior_completed + active_completed
            attempts = prior_attempts + active_attempts
            if prior_bytes + active_bytes > campaign.MAX_RUN_OBJECT_BYTES:
                _refuse("stopped v3 acquired objects exceed the campaign byte cap")
            pending_index = pending["global_index"]
            pending_request = plan.requests[pending_index]
            request_payload = pending_request.to_payload()
            if (inventory["rows"][pending_index - inventory["start"]]["request"]
                    != request_payload):
                _refuse("pending v3 request differs from original source plan")
            result = VerifiedPartialV3Receipt(
                pending_request=pending_request,
                pending_request_sha256=hash_payload(request_payload),
                pending_global_index=pending_index,
                pending_attempt_number=pending["attempt"],
                pending_shard_name=active_name,
                v3_root=output,
                capture_git_commit=capture_git_commit,
                root_plan_sha256=hash_bytes(plan_raw),
                source_plan_sha256=plan_body["source_plan_sha256"],
                pending_shard_inventory_sha256=hash_bytes(raw_inventory),
                pending_shard_journal_sha256=journal_sha,
                pending_attempt_start_sha256=hash_bytes(pending_raw),
                completed_new_count=completed,
                attempt_count=attempts,
                source_assignment_sha256=receipt["source_assignment_sha256"],
            )
        return result
    except PartialV3VerificationError:
        raise
    except (verifier.RecoveryVerificationError, campaign.CampaignError,
            source_union.RecoveryUnionError, SecPilotError, OSError,
            KeyError, IndexError, TypeError, ValueError, RecursionError) as exc:
        raise PartialV3VerificationError(
            "REFUSED: stopped v3 read-only replay failed"
        ) from exc


def verify_partial_synthetic_recovery_v3(
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
) -> VerifiedPartialV3Receipt:
    """Verify an invented-source stopped root without a network request."""
    if type(plan) is not campaign.CampaignPlan or plan.scope != "synthetic_test_manifest":
        _refuse("synthetic partial v3 replay requires a synthetic source plan")
    try:
        receipt = source_union.preflight_source_union(
            plan, prior_campaign_root, diagnostic_root, selected_root,
            prior_expectation=prior_expectation,
            diagnostic_capture_git_commit=diagnostic_capture_git_commit,
            expected_diagnostic_report_sha256=expected_diagnostic_report_sha256,
            diagnostic_mode=diagnostic_mode,
        )
        code_path = Path(__file__).with_name(
            "insider_buying_sec_all_form4_parent_recovery_executor.py"
        )
        result = _verify_partial(
            plan, receipt, prior_campaign_root, diagnostic_root, selected_root,
            output_root, prior_expectation=prior_expectation,
            capture_git_commit=capture_git_commit,
            capture_code_sha256=hash_bytes(code_path.read_bytes()),
        )
        replayed = source_union.preflight_source_union(
            plan, prior_campaign_root, diagnostic_root, selected_root,
            prior_expectation=prior_expectation,
            diagnostic_capture_git_commit=diagnostic_capture_git_commit,
            expected_diagnostic_report_sha256=expected_diagnostic_report_sha256,
            diagnostic_mode=diagnostic_mode,
        )
        if replayed != receipt:
            _refuse("synthetic v3 source roots changed during partial replay")
        return result
    except (source_union.RecoveryUnionError, campaign.CampaignError) as exc:
        raise PartialV3VerificationError(
            "REFUSED: synthetic v3 source replay failed"
        ) from exc


def load_observed_partial_all_form4_recovery_v3(
    raw_q4_directory: str | Path,
    parsed_q4_directory: str | Path,
    raw_q1_directory: str | Path,
    parsed_q1_directory: str | Path,
    exact16_pilot_root: str | Path,
    selected_root: str | Path,
    prior_campaign_root: str | Path,
    diagnostic_root: str | Path,
    output_root: str | Path,
) -> VerifiedPartialV3Receipt:
    """Pin and replay the one observed stopped root; never dispatch SEC."""
    lane_root = Path(__file__).resolve().parents[1]
    try:
        if (lane_root != OBSERVED_LANE_ROOT
                or _plain_path(selected_root, must_exist=True) != OBSERVED_SELECTED_ROOT
                or _plain_path(prior_campaign_root, must_exist=True) != OBSERVED_PRIOR_ROOT
                or _plain_path(diagnostic_root, must_exist=True) != OBSERVED_DIAGNOSTIC_ROOT
                or _plain_path(output_root, must_exist=True) != OBSERVED_V3_ROOT):
            _refuse("observed partial v3 root or lane differs from pinned source")
    except SecPilotError as exc:
        raise PartialV3VerificationError(
            "REFUSED: observed partial v3 root is not the pinned source"
        ) from exc
    try:
        blob = subprocess.run(
            ["git", "cat-file", "blob", OBSERVED_V3_CAPTURE_COMMIT + ":research/"
             "insider_buying_sec_all_form4_parent_recovery_executor.py"],
            cwd=lane_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise PartialV3VerificationError(
            "REFUSED: observed stopped v3 committed executor could not be read"
        ) from exc
    if (blob.returncode != 0
            or hash_bytes(blob.stdout) != OBSERVED_V3_EXECUTOR_SHA256):
        _refuse("observed stopped v3 executor differs from committed anchor")
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
        if (len(plan.requests) != 99_394 or plan.shard_size != 8_192
                or receipt["prior_completed_count"] != 9_539
                or receipt["offline_corrected_diagnostic_count"] != 1
                or receipt["remaining_selected_reuse_count"] != 8_139
                or receipt["later_unattempted_request_count"] != 81_715
                or receipt["source_assignment_sha256"]
                != OBSERVED_SOURCE_ASSIGNMENT_SHA256
                or receipt["later_unattempted_request_inventory_sha256"]
                != OBSERVED_LATER_INVENTORY_SHA256):
            _refuse("observed partial v3 population or source partition changed")
        result = _verify_partial(
            plan, receipt, prior_campaign_root, diagnostic_root, selected_root,
            output_root,
            prior_expectation=partial.PartialCampaignExpectation(
                capture_git_commit=partial.PRIOR_CAPTURE_GIT_COMMIT,
                shard_report_sha256s=partial.PRIOR_SHARD_REPORT_SHA256S,
                completed_counts=(8_192, 1_347), reused_counts=(972, 226),
                total_attempt_count=8_342,
            ),
            capture_git_commit=OBSERVED_V3_CAPTURE_COMMIT,
            capture_code_sha256=OBSERVED_V3_EXECUTOR_SHA256,
        )
        if (result.completed_new_count != 1_846 or result.attempt_count != 1_847
                or result.source_assignment_sha256
                != OBSERVED_SOURCE_ASSIGNMENT_SHA256):
            _refuse("observed stopped v3 counts differ from frozen failure")
        _require_observed_anchors(result)
        replayed = source_union.preflight_observed_all_form4_parent_recovery_union(
            raw_q4_directory, parsed_q4_directory, raw_q1_directory,
            parsed_q1_directory, exact16_pilot_root, selected_root,
            prior_campaign_root, diagnostic_root,
            diagnostic_capture_git_commit=source_union.OBSERVED_DIAGNOSTIC_CAPTURE_COMMIT,
            expected_diagnostic_report_sha256=source_union.OBSERVED_DIAGNOSTIC_REPORT_SHA256,
        )
        if replayed != receipt:
            _refuse("observed stopped v3 sources changed during replay")
        return result
    except PartialV3VerificationError:
        raise
    except (source_union.RecoveryUnionError, campaign.CampaignError,
            OSError, KeyError, TypeError, ValueError) as exc:
        raise PartialV3VerificationError(
            "REFUSED: observed stopped v3 source replay failed"
        ) from exc


__all__ = [
    "PartialV3VerificationError", "VerifiedPartialV3Receipt",
    "verify_partial_synthetic_recovery_v3",
    "load_observed_partial_all_form4_recovery_v3",
]
