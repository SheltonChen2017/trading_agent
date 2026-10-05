"""Read-only acceptance gate for one v3 ambiguous-parent diagnostic.

The separately supplied report digest is a trust anchor, not something inferred
from the directory being checked. A successful diagnostic supplies one bounded
raw parent to a later, separately versioned source union; it neither repairs
the stopped v3 journal nor establishes SEC authenticity, PIT, or QC authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import subprocess

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying_sec_acquisition import SecPilotError, _plain_path
from research.insider_buying_sec_all_form4_parent_campaign import (
    CampaignError, CampaignRequest, _check_utc, _json, _validate_parent_header,
)
from research.insider_buying_sec_all_form4_parent_recovery_partial_verifier import (
    VerifiedPartialV3Receipt, load_observed_partial_all_form4_recovery_v3,
)
from research.insider_buying_sec_all_form4_parent_recovery_verifier import (
    RecoveryVerificationError, _empty_file, _pinned_directory, _read,
)
from research.insider_buying_sec_complete_acquisition import (
    MAX_COMPLETE_TXT_BYTES, SecCompleteAcquisitionError, SecHttpResult,
)
from research.insider_buying_sec_selected_parent_runner import _strict_selected_response


VERIFIER_VERSION = "INSETF-SEC-ALL-FORM4-V3-AMBIGUOUS-DIAGNOSTIC-VERIFIER-v1"
_DIAGNOSTIC_VERSION = "INSETF-SEC-ALL-FORM4-V3-AMBIGUOUS-DIAGNOSTIC-v1"
_MAX_METADATA_BYTES = 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SHARD = re.compile(r"shard-[0-9]{4}\Z")
_OBSERVED_LANE_ROOT = Path(
    "/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying"
)
_OBSERVED_V3_ROOT = Path(
    "/Users/sheltonchen/Documents/Codex/2026-09-03/f/"
    "insider-source-allparents-20260929.3Nut2i/all-form4-parents-recovery-v3"
)
_OBSERVED_DIAGNOSTIC_ROOT = (
    _OBSERVED_V3_ROOT.parent / "all-form4-parents-v3-ambiguous-diagnostic-v1"
)
_CAPTURE_SOURCE = "research/insider_buying_sec_all_form4_parent_ambiguous_diagnostic.py"


class AmbiguousDiagnosticVerificationError(ValueError):
    """The independently checked one-shot diagnostic did not prove acceptance."""


def _refuse(reason: str) -> None:
    raise AmbiguousDiagnosticVerificationError(f"REFUSED: {reason}")


def _bytes(value: object) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


@dataclass(frozen=True, slots=True)
class VerifiedAcceptedAmbiguityDiagnostic:
    """Hash-only custody handoff; no request URL, accession, or body is exposed."""

    report_sha256: str
    diagnostic_capture_git_commit: str
    ambiguous_request_sha256: str
    original_pending_start_sha256: str
    v3_root_plan_sha256: str
    v3_source_plan_sha256: str
    v3_source_assignment_sha256: str
    pending_shard_inventory_sha256: str
    pending_shard_journal_sha256: str
    pending_global_index: int
    body_sha256: str
    body_size_bytes: int


def _expected_manifest(
    receipt: VerifiedPartialV3Receipt, capture_git_commit: str,
) -> dict[str, object]:
    """Reconstruct, rather than trust, the capture module's manifest."""
    if (type(receipt) is not VerifiedPartialV3Receipt
            or type(receipt.pending_request) is not CampaignRequest
            or type(receipt.pending_request_sha256) is not str
            or _SHA.fullmatch(receipt.pending_request_sha256) is None
            or hash_payload(receipt.pending_request.to_payload())
            != receipt.pending_request_sha256
            or type(receipt.pending_global_index) is not int
            or receipt.pending_global_index < 0
            or type(receipt.pending_attempt_number) is not int
            or receipt.pending_attempt_number != 1
            or type(receipt.pending_shard_name) is not str
            or _SHARD.fullmatch(receipt.pending_shard_name) is None
            or not isinstance(receipt.v3_root, Path)
            or not receipt.v3_root.is_absolute()
            or type(receipt.completed_new_count) is not int
            or receipt.completed_new_count < 0
            or type(receipt.attempt_count) is not int
            or receipt.attempt_count != receipt.completed_new_count + 1
            or type(receipt.capture_git_commit) is not str
            or _COMMIT.fullmatch(receipt.capture_git_commit) is None
            or type(capture_git_commit) is not str
            or _COMMIT.fullmatch(capture_git_commit) is None):
        _refuse("partial-v3 receipt or diagnostic code identity is malformed")
    for name in (
        "root_plan_sha256", "source_plan_sha256",
        "pending_shard_inventory_sha256", "pending_shard_journal_sha256",
        "pending_attempt_start_sha256", "source_assignment_sha256",
    ):
        value = getattr(receipt, name)
        if type(value) is not str or _SHA.fullmatch(value) is None:
            _refuse("partial-v3 receipt digest is malformed")
    source = _plain_path(receipt.v3_root, must_exist=True)
    return {
        "kind": _DIAGNOSTIC_VERSION + "/manifest",
        "diagnostic_capture_git_commit": capture_git_commit,
        "v3_capture_git_commit": receipt.capture_git_commit,
        "v3_root": str(source),
        "v3_root_plan_sha256": receipt.root_plan_sha256,
        "v3_source_plan_sha256": receipt.source_plan_sha256,
        "v3_source_assignment_sha256": receipt.source_assignment_sha256,
        "pending_shard_name": receipt.pending_shard_name,
        "pending_shard_inventory_sha256": receipt.pending_shard_inventory_sha256,
        "pending_shard_journal_sha256": receipt.pending_shard_journal_sha256,
        "pending_attempt_start_sha256": receipt.pending_attempt_start_sha256,
        "pending_global_index": receipt.pending_global_index,
        "ambiguous_request_sha256": receipt.pending_request_sha256,
        "ambiguous_v3_attempt_number": receipt.pending_attempt_number,
        "v3_completed_new_count": receipt.completed_new_count,
        "v3_attempt_count": receipt.attempt_count,
        "maximum_additional_dispatches": 1,
        "possible_duplicate_of_ambiguous_v3_start": True,
        "maximum_decoded_body_bytes": MAX_COMPLETE_TXT_BYTES,
        "source_authenticated": False,
        "canonical_evidence": False,
        "point_in_time_data": False,
        "outcome_looks": 0,
        "qc_jobs": 0,
    }


def verify_accepted_ambiguity_diagnostic(
    receipt: VerifiedPartialV3Receipt, diagnostic_root: str | Path,
    *, capture_git_commit: str, expected_report_sha256: str,
) -> VerifiedAcceptedAmbiguityDiagnostic:
    """Replay a fresh partial-v3 receipt against a separately pinned report.

    Callers must obtain ``receipt`` from the independent partial-v3 loader
    immediately before this check. No network call or artifact write occurs.
    """
    if (type(expected_report_sha256) is not str
            or _SHA.fullmatch(expected_report_sha256) is None):
        _refuse("trusted diagnostic report digest is malformed")
    try:
        manifest_raw = _bytes(_expected_manifest(receipt, capture_git_commit))
        manifest_sha = hash_bytes(manifest_raw)
        root = _plain_path(diagnostic_root, must_exist=True)
        if (root == receipt.v3_root or receipt.v3_root in root.parents
                or root in receipt.v3_root.parents):
            _refuse("diagnostic root overlaps the stopped v3 source")
        report_name = f"diagnostic-report-{expected_report_sha256}.json"
        expected_names = {
            "run.lock", "objects", "manifest.json", "attempt-start.json",
            "response.json", report_name, "commit.json",
        }
        with _pinned_directory(root, lock=True) as pinned:
            _empty_file(pinned, "run.lock")
            if pinned.names() != expected_names:
                _refuse("one-shot diagnostic has missing or extra members")
            if _read(pinned, "manifest.json", max_bytes=_MAX_METADATA_BYTES) != manifest_raw:
                _refuse("one-shot manifest differs from the replayed v3 start")
            start_raw = _read(pinned, "attempt-start.json", max_bytes=4096)
            start = _json(start_raw, label="v3 ambiguity diagnostic start")
            if (set(start) != {"kind", "manifest_sha256", "attempt", "started_utc"}
                    or start["kind"] != _DIAGNOSTIC_VERSION + "/attempt-start"
                    or start["manifest_sha256"] != manifest_sha
                    or type(start["attempt"]) is not int or start["attempt"] != 1):
                _refuse("one-shot start does not bind one attempt to its manifest")
            _check_utc(start["started_utc"])

            response = _json(
                _read(pinned, "response.json", max_bytes=_MAX_METADATA_BYTES),
                label="v3 ambiguity diagnostic response",
            )
            if (set(response) != {"kind", "status", "headers", "headers_sha256",
                                 "body_sha256", "body_size_bytes"}
                    or response["kind"] != _DIAGNOSTIC_VERSION + "/response"
                    or type(response["status"]) is not int or response["status"] != 200
                    or type(response["headers"]) is not list
                    or any(type(pair) is not list or len(pair) != 2
                           or type(pair[0]) is not str or type(pair[1]) is not str
                           for pair in response["headers"])
                    or response["headers_sha256"] != hash_payload(response["headers"])
                    or type(response["body_sha256"]) is not str
                    or _SHA.fullmatch(response["body_sha256"]) is None
                    or type(response["body_size_bytes"]) is not int
                    or not 0 < response["body_size_bytes"] <= MAX_COMPLETE_TXT_BYTES):
                _refuse("diagnostic response is not a bounded HTTP 200 body")
            body_sha = response["body_sha256"]
            with _pinned_directory(root / "objects") as objects:
                if objects.names() != {body_sha + ".bin"}:
                    _refuse("diagnostic object set is missing or enlarged")
                body = _read(objects, body_sha + ".bin", max_bytes=MAX_COMPLETE_TXT_BYTES)
            if len(body) != response["body_size_bytes"] or hash_bytes(body) != body_sha:
                _refuse("diagnostic body differs from its content descriptor")
            result = SecHttpResult(
                200, tuple((pair[0], pair[1]) for pair in response["headers"]), body,
            )
            if _strict_selected_response(result, max_bytes=MAX_COMPLETE_TXT_BYTES) != body:
                _refuse("diagnostic response framing changed")
            _validate_parent_header(body, receipt.pending_request.to_payload())

            report_raw = _read(pinned, report_name, max_bytes=_MAX_METADATA_BYTES)
            if hash_bytes(report_raw) != expected_report_sha256:
                _refuse("diagnostic report differs from its separate trusted digest")
            report = _json(report_raw, label="v3 ambiguity diagnostic report")
            if (set(report) != {
                    "kind", "manifest_sha256", "attempt_start_sha256",
                    "transport_outcome", "status", "response_headers_sha256",
                    "body_sha256", "body_size_bytes", "envelope_outcome",
                    "envelope_reason", "finished_utc", "v3_campaign_advanced",
                    "source_authenticated", "canonical_evidence", "point_in_time_data",
                    "outcome_looks", "qc_jobs",
                }
                    or report["kind"] != _DIAGNOSTIC_VERSION + "/report"
                    or report["manifest_sha256"] != manifest_sha
                    or report["attempt_start_sha256"] != hash_bytes(start_raw)
                    or report["transport_outcome"] != "returned"
                    or type(report["status"]) is not int or report["status"] != 200
                    or report["response_headers_sha256"] != response["headers_sha256"]
                    or report["body_sha256"] != body_sha
                    or type(report["body_size_bytes"]) is not int
                    or report["body_size_bytes"] != len(body)
                    or report["envelope_outcome"] != "accepted"
                    or report["envelope_reason"] is not None
                    or any(report[name] is not False for name in (
                        "v3_campaign_advanced", "source_authenticated",
                        "canonical_evidence", "point_in_time_data",
                    ))
                    or type(report["outcome_looks"]) is not int
                    or report["outcome_looks"] != 0
                    or type(report["qc_jobs"]) is not int or report["qc_jobs"] != 0):
                _refuse("diagnostic report does not prove an accepted, zero-authority body")
            _check_utc(report["finished_utc"])
            if (datetime.fromisoformat(report["finished_utc"])
                    < datetime.fromisoformat(start["started_utc"])):
                _refuse("diagnostic completion precedes its durable start")
            commit = _json(
                _read(pinned, "commit.json", max_bytes=4096),
                label="v3 ambiguity diagnostic commit",
            )
            if commit != {
                "kind": _DIAGNOSTIC_VERSION + "/commit",
                "report_name": report_name,
                "report_sha256": expected_report_sha256,
                "manifest_sha256": manifest_sha,
            }:
                _refuse("diagnostic commit differs from accepted report")
        return VerifiedAcceptedAmbiguityDiagnostic(
            report_sha256=expected_report_sha256,
            diagnostic_capture_git_commit=capture_git_commit,
            ambiguous_request_sha256=receipt.pending_request_sha256,
            original_pending_start_sha256=receipt.pending_attempt_start_sha256,
            v3_root_plan_sha256=receipt.root_plan_sha256,
            v3_source_plan_sha256=receipt.source_plan_sha256,
            v3_source_assignment_sha256=receipt.source_assignment_sha256,
            pending_shard_inventory_sha256=receipt.pending_shard_inventory_sha256,
            pending_shard_journal_sha256=receipt.pending_shard_journal_sha256,
            pending_global_index=receipt.pending_global_index,
            body_sha256=body_sha,
            body_size_bytes=len(body),
        )
    except AmbiguousDiagnosticVerificationError:
        raise
    except (CampaignError, RecoveryVerificationError, SecPilotError,
            SecCompleteAcquisitionError, OSError, KeyError, TypeError,
            ValueError, UnicodeError, RecursionError) as exc:
        raise AmbiguousDiagnosticVerificationError(
            "REFUSED: one-shot diagnostic read-only replay failed"
        ) from exc


def _verify_observed_capture_blob(capture_git_commit: str) -> str:
    """Tie the observed artifact to the current reviewed capture module bytes."""
    if type(capture_git_commit) is not str or _COMMIT.fullmatch(capture_git_commit) is None:
        _refuse("observed capture commit is malformed")
    lane = Path(__file__).resolve().parents[1]
    if lane != _OBSERVED_LANE_ROOT:
        _refuse("observed diagnostic verifier is outside the designated lane")
    try:
        root = subprocess.check_output(
            ("git", "rev-parse", "--show-toplevel"), cwd=lane,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        branch = subprocess.check_output(
            ("git", "branch", "--show-current"), cwd=lane,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        blob = subprocess.check_output(
            ("git", "cat-file", "blob", f"{capture_git_commit}:{_CAPTURE_SOURCE}"),
            cwd=lane, stderr=subprocess.DEVNULL,
        )
        on_disk = (lane / _CAPTURE_SOURCE).read_bytes()
    except (OSError, UnicodeError, subprocess.CalledProcessError) as exc:
        raise AmbiguousDiagnosticVerificationError(
            "REFUSED: observed capture commit blob is unavailable"
        ) from exc
    if (root != str(lane) or branch != "codex/strategy-insider-buying"
            or hash_bytes(blob) != hash_bytes(on_disk)):
        _refuse("observed capture module differs from its committed blob")
    return hash_bytes(blob)


def load_observed_accepted_v3_ambiguity_diagnostic(
    raw_q4_directory: str | Path, parsed_q4_directory: str | Path,
    raw_q1_directory: str | Path, parsed_q1_directory: str | Path,
    exact16_pilot_root: str | Path, selected_root: str | Path,
    prior_campaign_root: str | Path, old_diagnostic_root: str | Path,
    v3_root: str | Path, diagnostic_root: str | Path,
    *, capture_git_commit: str, expected_report_sha256: str,
) -> VerifiedAcceptedAmbiguityDiagnostic:
    """Observed-only read-only replay with fresh v3 source on both sides.

    The caller supplies the report digest and capture commit from outside the
    diagnostic directory. Neither is discovered from its filename or content.
    """
    if (type(expected_report_sha256) is not str
            or _SHA.fullmatch(expected_report_sha256) is None):
        _refuse("trusted observed diagnostic report digest is malformed")
    try:
        if (Path(v3_root) != _OBSERVED_V3_ROOT
                or Path(diagnostic_root) != _OBSERVED_DIAGNOSTIC_ROOT
                or _plain_path(v3_root, must_exist=True) != _OBSERVED_V3_ROOT
                or _plain_path(diagnostic_root, must_exist=True)
                != _OBSERVED_DIAGNOSTIC_ROOT):
            _refuse("observed diagnostic or stopped-v3 root differs from its fixed path")
        capture_blob_sha = _verify_observed_capture_blob(capture_git_commit)
        source_args = (
            raw_q4_directory, parsed_q4_directory, raw_q1_directory,
            parsed_q1_directory, exact16_pilot_root, selected_root,
            prior_campaign_root, old_diagnostic_root, v3_root,
        )
        before = load_observed_partial_all_form4_recovery_v3(*source_args)
        if (type(before) is not VerifiedPartialV3Receipt
                or before.v3_root != _OBSERVED_V3_ROOT):
            _refuse("observed stopped-v3 receipt differs from fixed source")
        accepted = verify_accepted_ambiguity_diagnostic(
            before, diagnostic_root, capture_git_commit=capture_git_commit,
            expected_report_sha256=expected_report_sha256,
        )
        if (_verify_observed_capture_blob(capture_git_commit) != capture_blob_sha
                or load_observed_partial_all_form4_recovery_v3(*source_args) != before):
            _refuse("observed source or capture code changed during replay")
        return accepted
    except AmbiguousDiagnosticVerificationError:
        raise
    except (OSError, SecPilotError, RecoveryVerificationError,
            ValueError, TypeError, UnicodeError) as exc:
        raise AmbiguousDiagnosticVerificationError(
            "REFUSED: observed one-shot diagnostic replay failed"
        ) from exc


__all__ = [
    "AmbiguousDiagnosticVerificationError", "VerifiedAcceptedAmbiguityDiagnostic",
    "verify_accepted_ambiguity_diagnostic",
    "load_observed_accepted_v3_ambiguity_diagnostic",
]
