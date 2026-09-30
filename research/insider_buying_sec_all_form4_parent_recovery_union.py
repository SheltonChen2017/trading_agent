"""Offline custody gate for the halted all-Form-4 parent campaign.

This module never dispatches a request or writes a recovery root.  It replays
the immutable v1 prefix, independently checks the one-shot diagnostic, and
accounts for the exact source of each still-needed parent.  Its receipt is an
acquisition plan, not complete, canonical, PIT, or authenticated evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import os
import re
import stat

from data.hashing import hash_bytes, hash_payload
from research.insider_buying_sec_acquisition import SecPilotError, _plain_path
from research.insider_buying_sec_complete_acquisition import (
    MAX_COMPLETE_TXT_BYTES, SecCompleteAcquisitionError, SecHttpResult,
)
from research.insider_buying_sec_complete_projection_adapter import (
    SecCompletePilotAdapterError, _PinnedRoot,
)
from research.insider_buying_sec_selected_parent_runner import _strict_selected_response
import research.insider_buying_sec_all_form4_parent_campaign as campaign
import research.insider_buying_sec_all_form4_parent_recovery_preflight as partial
import research.insider_buying_sec_parent_refusal_diagnostic as diagnostic


UNION_VERSION = "INSETF-SEC-ALL-FORM4-PARENTS-RECOVERY-UNION-v1"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_DIAGNOSTIC_NAME = "refused-parent-diagnostic-v1"


class RecoveryUnionError(ValueError):
    """An offline source binding or custody replay refused."""


def _refuse(reason: str) -> None:
    raise RecoveryUnionError(f"REFUSED: {reason}")


def _require_private_diagnostic_mode(
    pinned: _PinnedRoot, name: str | None = None, *, object_file: bool = False,
) -> None:
    """Keep the private raw response and possible echoed headers owner-only."""
    if pinned.root_fd is None or pinned.objects_fd is None:
        _refuse("diagnostic directory handle is closed")
    info = (os.fstat(pinned.root_fd) if name is None else os.stat(
        name, dir_fd=pinned.objects_fd if object_file else pinned.root_fd,
        follow_symlinks=False,
    ))
    if (not (stat.S_ISDIR(info.st_mode) if name is None or name == "objects"
             else stat.S_ISREG(info.st_mode))
            or stat.S_IMODE(info.st_mode) & 0o077):
        _refuse("diagnostic custody mode is not owner-only")


@dataclass(frozen=True, slots=True)
class VerifiedAcceptedDiagnostic:
    report_sha256: str
    capture_git_commit: str
    body_sha256: str
    body_size_bytes: int
    refused_request_sha256: str


def verify_accepted_diagnostic(
    diagnostic_root: str | Path,
    binding: diagnostic.RefusedParentBinding,
    *, capture_git_commit: str, expected_report_sha256: str,
) -> VerifiedAcceptedDiagnostic:
    """Read every committed diagnostic member and recheck its raw 200 body.

    The report hash is a separate trusted anchor.  A self-consistent copied or
    rewritten diagnostic directory alone is not evidence for this transition.
    """
    if (type(binding) is not diagnostic.RefusedParentBinding
            or type(capture_git_commit) is not str
            or _COMMIT.fullmatch(capture_git_commit) is None
            or type(expected_report_sha256) is not str
            or _SHA.fullmatch(expected_report_sha256) is None):
        _refuse("diagnostic replay binding is malformed")
    try:
        manifest = binding.to_manifest(capture_git_commit=capture_git_commit)
        manifest_raw = diagnostic._bytes(manifest)
        manifest_sha = hash_bytes(manifest_raw)
        root = _plain_path(diagnostic_root, must_exist=True)
        with _PinnedRoot(root) as pinned:
            _require_private_diagnostic_mode(pinned)
            _require_private_diagnostic_mode(pinned, "objects")
            with partial._hold_read_lock(pinned.root_fd):
                if pinned.read("manifest.json", label="diagnostic manifest",
                               max_bytes=diagnostic.MAX_RESPONSE_METADATA_BYTES) != manifest_raw:
                    _refuse("diagnostic manifest differs from the stopped source")
                start = campaign._json(
                    pinned.read("attempt-start.json", label="diagnostic start",
                                max_bytes=4096), label="diagnostic start",
                )
                if (set(start) != {"kind", "manifest_sha256", "attempt", "started_utc"}
                        or start["kind"] != diagnostic.DIAGNOSTIC_VERSION + "/attempt-start"
                        or start["manifest_sha256"] != manifest_sha
                        or type(start["attempt"]) is not int or start["attempt"] != 1):
                    _refuse("diagnostic start differs from its one-shot manifest")
                campaign._check_utc(start["started_utc"])
                start_sha = hash_bytes(diagnostic._bytes(start))

                response = campaign._json(
                    pinned.read("response.json", label="diagnostic response",
                                max_bytes=diagnostic.MAX_RESPONSE_METADATA_BYTES),
                    label="diagnostic response",
                )
                if (set(response) != {"kind", "status", "headers", "headers_sha256",
                                      "body_sha256", "body_size_bytes"}
                        or response["kind"] != diagnostic.DIAGNOSTIC_VERSION + "/response"
                        or type(response["status"]) is not int or response["status"] != 200
                        or type(response["headers"]) is not list
                        or any(type(pair) is not list or len(pair) != 2
                               or any(type(value) is not str for value in pair)
                               for pair in response["headers"])
                        or response["headers_sha256"] != hash_payload(response["headers"])
                        or type(response["body_sha256"]) is not str
                        or _SHA.fullmatch(response["body_sha256"]) is None
                        or type(response["body_size_bytes"]) is not int
                        or not 0 < response["body_size_bytes"] <= MAX_COMPLETE_TXT_BYTES):
                    _refuse("diagnostic response metadata is not a bounded HTTP 200 body")
                body_sha = response["body_sha256"]
                body = pinned.read(f"objects/{body_sha}.bin",
                                   label="diagnostic parent body",
                                   max_bytes=MAX_COMPLETE_TXT_BYTES)
                if len(body) != response["body_size_bytes"] or hash_bytes(body) != body_sha:
                    _refuse("diagnostic body differs from its response descriptor")
                headers = tuple((pair[0], pair[1]) for pair in response["headers"])
                if _strict_selected_response(
                    SecHttpResult(200, headers, body), max_bytes=MAX_COMPLETE_TXT_BYTES,
                ) != body:
                    _refuse("diagnostic response framing changed")
                campaign._validate_parent_header(body, binding.request.to_payload())

                report_name = f"diagnostic-report-{expected_report_sha256}.json"
                report_raw = pinned.read(report_name, label="diagnostic report",
                                         max_bytes=diagnostic.MAX_RESPONSE_METADATA_BYTES)
                if hash_bytes(report_raw) != expected_report_sha256:
                    _refuse("diagnostic report differs from its trusted digest")
                report = campaign._json(report_raw, label="diagnostic report")
                expected_fields = {
                    "kind", "manifest_sha256", "attempt_start_sha256", "transport_outcome",
                    "status", "response_headers_sha256", "body_sha256", "body_size_bytes",
                    "envelope_outcome", "envelope_reason", "finished_utc",
                    "campaign_advanced", "source_authenticated", "canonical_evidence",
                    "point_in_time_data", "outcome_looks", "qc_jobs",
                }
                if (set(report) != expected_fields
                        or report["kind"] != diagnostic.DIAGNOSTIC_VERSION + "/report"
                        or report["manifest_sha256"] != manifest_sha
                        or report["attempt_start_sha256"] != start_sha
                        or report["transport_outcome"] != "returned"
                        or type(report["status"]) is not int or report["status"] != 200
                        or report["response_headers_sha256"] != response["headers_sha256"]
                        or report["body_sha256"] != body_sha
                        or type(report["body_size_bytes"]) is not int
                        or report["body_size_bytes"] != len(body)
                        or report["envelope_outcome"] != "accepted"
                        or report["envelope_reason"] is not None
                        or any(report[name] is not False for name in (
                            "campaign_advanced", "source_authenticated", "canonical_evidence",
                            "point_in_time_data",
                        ))
                        or type(report["outcome_looks"]) is not int
                        or report["outcome_looks"] != 0
                        or type(report["qc_jobs"]) is not int or report["qc_jobs"] != 0):
                    _refuse("diagnostic report does not prove accepted raw custody")
                campaign._check_utc(report["finished_utc"])
                if datetime.fromisoformat(report["finished_utc"]) < datetime.fromisoformat(
                    start["started_utc"]
                ):
                    _refuse("diagnostic finished before its durable start")
                commit = campaign._json(
                    pinned.read("commit.json", label="diagnostic commit", max_bytes=4096),
                    label="diagnostic commit",
                )
                if commit != {
                    "kind": diagnostic.DIAGNOSTIC_VERSION + "/commit",
                    "report_name": report_name,
                    "report_sha256": expected_report_sha256,
                    "manifest_sha256": manifest_sha,
                }:
                    _refuse("diagnostic commit differs from the accepted report")
                if (pinned.names() != {
                    "run.lock", "objects", "manifest.json", "attempt-start.json",
                    "response.json", report_name, "commit.json",
                } or pinned.names(objects=True) != {body_sha + ".bin"}):
                    _refuse("diagnostic root has missing or extra members")
                for name in (
                    "run.lock", "manifest.json", "attempt-start.json",
                    "response.json", report_name, "commit.json",
                ):
                    _require_private_diagnostic_mode(pinned, name)
                _require_private_diagnostic_mode(
                    pinned, f"{body_sha}.bin", object_file=True,
                )
        return VerifiedAcceptedDiagnostic(
            report_sha256=expected_report_sha256,
            capture_git_commit=capture_git_commit,
            body_sha256=body_sha,
            body_size_bytes=len(body),
            refused_request_sha256=manifest["refused_request_sha256"],
        )
    except RecoveryUnionError:
        raise
    except (campaign.CampaignError, diagnostic.RefusedParentDiagnosticError,
            SecPilotError, SecCompletePilotAdapterError, SecCompleteAcquisitionError,
            OSError, KeyError, TypeError, ValueError, RecursionError) as exc:
        raise RecoveryUnionError("REFUSED: accepted diagnostic replay failed") from exc


def preflight_source_union(
    plan: campaign.CampaignPlan,
    prior_campaign_root: str | Path,
    diagnostic_root: str | Path,
    selected_root: str | Path,
    *, prior_expectation: partial.PartialCampaignExpectation,
    diagnostic_capture_git_commit: str,
    expected_diagnostic_report_sha256: str,
) -> dict[str, object]:
    """Return aggregate-only source assignment after three offline replays."""
    if type(plan) is not campaign.CampaignPlan:
        _refuse("recovery plan is malformed")
    try:
        receipt = partial.verify_partial_campaign(
            plan, prior_campaign_root, expected=prior_expectation,
        )
        binding = diagnostic.RefusedParentBinding(
            request=receipt.refused_request,
            prior_campaign_plan_sha256=receipt.prior_campaign_plan_sha256,
            prior_shard_report_sha256s=receipt.prior_shard_report_sha256s,
            prior_shard_journal_sha256s=receipt.prior_shard_journal_sha256s,
        )
        accepted = verify_accepted_diagnostic(
            diagnostic_root, binding,
            capture_git_commit=diagnostic_capture_git_commit,
            expected_report_sha256=expected_diagnostic_report_sha256,
        )
        payload = plan.to_payload()
        selected = {row["accession_number"]: row for row in payload["reuses"]}
        old_count = receipt.completed_count
        if (old_count >= len(plan.requests)
                or accepted.refused_request_sha256
                != hash_payload(plan.requests[old_count].to_payload())):
            _refuse("diagnostic does not fill the exact refused request")
        later_selected = 0
        later_dispatch: list[dict[str, str]] = []
        classes = ["prior_completed"] * old_count + ["accepted_diagnostic"]
        selected_path = _plain_path(selected_root, must_exist=True)
        with _PinnedRoot(selected_path) as pinned:
            for request in plan.requests[old_count + 1:]:
                descriptor = selected.get(request.accession_number)
                if descriptor is None:
                    later_dispatch.append(request.to_payload())
                    classes.append("later_unattempted")
                    continue
                raw = pinned.read(
                    f'objects/{descriptor["object_sha256"]}.bin',
                    label="remaining selected parent", max_bytes=MAX_COMPLETE_TXT_BYTES,
                )
                if (len(raw) != descriptor["object_size_bytes"]
                        or hash_bytes(raw) != descriptor["object_sha256"]):
                    _refuse("remaining selected object differs from its frozen descriptor")
                campaign._validate_parent_header(raw, request.to_payload())
                later_selected += 1
                classes.append("remaining_selected_reuse")
        if (len(classes) != len(plan.requests)
                or old_count + 1 + later_selected + len(later_dispatch) != len(plan.requests)
                or later_selected != receipt.remaining_selected_reuse_count
                or len(later_dispatch) + 1 != receipt.remaining_new_request_count
                or receipt.prior_selected_reused_count + later_selected != len(selected)
                or receipt.prior_attempt_count < receipt.prior_newly_acquired_count + 1
                or accepted.body_size_bytes > MAX_COMPLETE_TXT_BYTES):
            _refuse("recovery source classes do not partition the frozen population")
        return {
            "kind": UNION_VERSION + "/read-only-preflight",
            "manifest_sha256": receipt.manifest_sha256,
            "request_inventory_sha256": receipt.request_inventory_sha256,
            "prior_capture_git_commit": receipt.prior_capture_git_commit,
            "prior_campaign_plan_sha256": receipt.prior_campaign_plan_sha256,
            "prior_shard_report_sha256s": receipt.prior_shard_report_sha256s,
            "prior_shard_journal_sha256s": receipt.prior_shard_journal_sha256s,
            "diagnostic_capture_git_commit": accepted.capture_git_commit,
            "diagnostic_report_sha256": accepted.report_sha256,
            "source_assignment_sha256": hash_payload(classes),
            "later_unattempted_request_inventory_sha256": hash_payload(later_dispatch),
            "total_parents": len(plan.requests),
            "prior_completed_count": old_count,
            "prior_selected_reused_count": receipt.prior_selected_reused_count,
            "prior_newly_acquired_count": receipt.prior_newly_acquired_count,
            "prior_attempt_count": receipt.prior_attempt_count,
            "accepted_diagnostic_count": 1,
            "diagnostic_attempt_count": 1,
            "known_attempt_count": receipt.prior_attempt_count + 1,
            "refused_parent_total_attempt_count": receipt.refused_prior_attempt_count + 1,
            "remaining_selected_reuse_count": later_selected,
            "later_unattempted_request_count": len(later_dispatch),
            "sec_dispatches": 0,
            "complete_parent_bytes_acquired": False,
            "source_authenticated": False,
            "canonical_evidence": False,
            "point_in_time_data": False,
            "research_looks": 0,
            "qc_jobs": 0,
        }
    except RecoveryUnionError:
        raise
    except (campaign.CampaignError, SecPilotError, SecCompletePilotAdapterError,
            OSError, KeyError, IndexError, TypeError, ValueError, RecursionError) as exc:
        raise RecoveryUnionError("REFUSED: source-union preflight failed") from exc


def preflight_observed_all_form4_parent_recovery_union(
    raw_q4_directory: str | Path, parsed_q4_directory: str | Path,
    raw_q1_directory: str | Path, parsed_q1_directory: str | Path,
    exact16_pilot_root: str | Path, selected_root: str | Path,
    prior_campaign_root: str | Path, diagnostic_root: str | Path,
    *, diagnostic_capture_git_commit: str,
    expected_diagnostic_report_sha256: str,
) -> dict[str, object]:
    """Exact real-source, read-only gate; no arbitrary copied recovery roots."""
    try:
        prior = _plain_path(prior_campaign_root, must_exist=True)
        candidate = _plain_path(diagnostic_root, must_exist=True)
        if (prior != diagnostic._PRIOR_CAMPAIGN_ROOT
                or candidate != prior.parent / _DIAGNOSTIC_NAME):
            _refuse("recovery roots differ from the stopped campaign and one-shot diagnostic")
        plan = campaign._build_real_plan(
            raw_q4_directory, parsed_q4_directory, raw_q1_directory,
            parsed_q1_directory, exact16_pilot_root, selected_root,
        )
        if plan.to_payload()["request_inventory_sha256"] != partial.PRIOR_REQUEST_INVENTORY_SHA256:
            _refuse("real source request inventory differs from the stopped campaign")
        result = preflight_source_union(
            plan, prior, candidate, selected_root,
            prior_expectation=partial.PartialCampaignExpectation(
                capture_git_commit=partial.PRIOR_CAPTURE_GIT_COMMIT,
                shard_report_sha256s=partial.PRIOR_SHARD_REPORT_SHA256S,
                completed_counts=(8_192, 1_347), reused_counts=(972, 226),
                total_attempt_count=8_342,
            ),
            diagnostic_capture_git_commit=diagnostic_capture_git_commit,
            expected_diagnostic_report_sha256=expected_diagnostic_report_sha256,
        )
        if (result["total_parents"] != 99_394
                or result["prior_completed_count"] != 9_539
                or result["prior_selected_reused_count"] != 1_198
                or result["prior_newly_acquired_count"] != 8_341
                or result["prior_attempt_count"] != 8_342
                or result["refused_parent_total_attempt_count"] != 2
                or result["remaining_selected_reuse_count"] != 8_139
                or result["later_unattempted_request_count"] != 81_715):
            _refuse("real recovery union differs from the frozen 99,394-source partition")
        return result
    except RecoveryUnionError:
        raise
    except (campaign.CampaignError, SecPilotError, OSError, KeyError, TypeError,
            ValueError, RecursionError) as exc:
        raise RecoveryUnionError("REFUSED: real recovery source preflight failed") from exc


__all__ = [
    "RecoveryUnionError", "VerifiedAcceptedDiagnostic",
    "verify_accepted_diagnostic", "preflight_source_union",
    "preflight_observed_all_form4_parent_recovery_union",
]
