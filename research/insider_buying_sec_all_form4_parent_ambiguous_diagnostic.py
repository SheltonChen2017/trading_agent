"""One additional, separately journaled SEC diagnostic for the stopped v3 parent.

The observed entry obtains its request from independent replay of the v3
trailing request-start. Its synthetic test seam accepts an injected callback,
which must not be treated as inherently network-free. The original v3 root
is never resumed or modified. A new private root consumes this narrowly
authorized diagnostic even if transport fails or the process stops after its
durable start. No result promotes source custody to SEC authenticity,
publication/PIT evidence, or backtest authority.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable
import http.client
import os
import re
import stat
import subprocess

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying_sec_acquisition import (
    SecPilotError, _plain_path, _publish_immutable, _refuse_output_overlap,
    _store_object,
)
from research.insider_buying_sec_all_form4_parent_campaign import (
    CampaignError, CampaignRequest, _validate_parent_header,
)
from research.insider_buying_sec_all_form4_parent_recovery_partial_verifier import (
    VerifiedPartialV3Receipt, load_observed_partial_all_form4_recovery_v3,
)
from research.insider_buying_sec_complete_acquisition import (
    MAX_COMPLETE_TXT_BYTES, SecCompleteAcquisitionError, SecHttpResult,
)
from research.insider_buying_sec_master82_runner import _RootLock
from research.insider_buying_sec_selected_parent_runner import (
    _selected_sec_transport, _strict_selected_response, _utc,
)


DIAGNOSTIC_VERSION = "INSETF-SEC-ALL-FORM4-V3-AMBIGUOUS-DIAGNOSTIC-v1"
MAX_RESPONSE_METADATA_BYTES = 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SHARD = re.compile(r"shard-[0-9]{4}\Z")
_CONTACT = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}\Z")
_LANE_ROOT = Path(
    "/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying"
)
_OBSERVED_V3_ROOT = Path(
    "/Users/sheltonchen/Documents/Codex/2026-09-03/f/"
    "insider-source-allparents-20260929.3Nut2i/all-form4-parents-recovery-v3"
)
_OBSERVED_DIAGNOSTIC_ROOT = (
    _OBSERVED_V3_ROOT.parent / "all-form4-parents-v3-ambiguous-diagnostic-v1"
)
_COMMITTED_DEPENDENCIES = (
    "research/insider_buying_sec_all_form4_parent_ambiguous_diagnostic.py",
    "research/insider_buying_sec_all_form4_parent_recovery_partial_verifier.py",
    "research/insider_buying_sec_all_form4_parent_recovery_verifier.py",
    "research/insider_buying_sec_all_form4_parent_recovery_executor.py",
    "research/insider_buying_sec_all_form4_parent_recovery_campaign.py",
    "research/insider_buying_sec_all_form4_parent_recovery_union.py",
    "research/insider_buying_sec_all_form4_parent_recovery_preflight.py",
    "research/insider_buying_sec_all_form4_parent_campaign.py",
    "research/insider_buying_sec_selected_parent_runner.py",
    "research/insider_buying_sec_complete_acquisition.py",
    "research/insider_buying_sec_acquisition.py",
    "research/insider_buying_sec_master82_runner.py",
    "data/hashing.py",
)


class AmbiguousParentDiagnosticError(ValueError):
    """The one-shot duplicate-risk diagnostic refused an input or publication."""


def _refuse(reason: str) -> None:
    raise AmbiguousParentDiagnosticError(f"REFUSED: {reason}")


def _bytes(value: object) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def _binding_manifest(
    receipt: VerifiedPartialV3Receipt, *, capture_git_commit: str,
) -> dict[str, object]:
    """Bind the one possible duplicate to a trusted v3 pending start."""
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
        _refuse("v3 pending-start binding is malformed")
    for name in (
        "root_plan_sha256", "source_plan_sha256",
        "pending_shard_inventory_sha256", "pending_shard_journal_sha256",
        "pending_attempt_start_sha256", "source_assignment_sha256",
    ):
        value = getattr(receipt, name)
        if type(value) is not str or _SHA.fullmatch(value) is None:
            _refuse("v3 pending-start digest binding is malformed")
    try:
        source = _plain_path(receipt.v3_root, must_exist=True)
    except SecPilotError as exc:
        raise AmbiguousParentDiagnosticError(
            "REFUSED: v3 pending-start root is unsafe"
        ) from exc
    return {
        "kind": DIAGNOSTIC_VERSION + "/manifest",
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


def _verify_exact_committed_code(commit: str) -> None:
    """Real transport requires the designated clean lane and exact code bytes."""
    if type(commit) is not str or _COMMIT.fullmatch(commit) is None:
        _refuse("diagnostic capture commit is malformed")
    root = Path(__file__).resolve().parents[1]
    try:
        def command(*args: str) -> bytes:
            return subprocess.check_output(
                ("git", *args), cwd=root, stderr=subprocess.DEVNULL,
            )

        if (root != _LANE_ROOT
                or command("rev-parse", "--show-toplevel").decode().strip()
                != str(root)
                or command("branch", "--show-current").decode().strip()
                != "codex/strategy-insider-buying"
                or command("rev-parse", "HEAD").decode().strip() != commit
                or command("status", "--porcelain=v1", "--untracked-files=all")):
            _refuse("exact clean committed Insider lane is required")
        for relative in _COMMITTED_DEPENDENCIES:
            committed = command("show", f"{commit}:{relative}")
            if hash_bytes(committed) != hash_bytes((root / relative).read_bytes()):
                _refuse("committed diagnostic dependency differs on disk")
    except (OSError, UnicodeError, subprocess.CalledProcessError) as exc:
        raise AmbiguousParentDiagnosticError(
            "REFUSED: exact diagnostic code commit could not be verified"
        ) from exc


def _response_headers(result: SecHttpResult) -> list[list[str]]:
    if (type(result) is not SecHttpResult or type(result.status) is not int
            or type(result.headers) is not tuple
            or any(type(pair) is not tuple or len(pair) != 2
                   or type(pair[0]) is not str or type(pair[1]) is not str
                   for pair in result.headers)):
        _refuse("diagnostic transport result has malformed status or headers")
    headers = [[name, value] for name, value in result.headers]
    if len(_bytes(headers)) > MAX_RESPONSE_METADATA_BYTES:
        _refuse("diagnostic response headers exceed their bound")
    return headers


def _capture_one(
    receipt: VerifiedPartialV3Receipt, output_root: str | Path, *,
    transport: Callable[[str, dict[str, str], int], SecHttpResult],
    contact_email: str, capture_git_commit: str,
    protected_roots: tuple[Path, ...],
    observed: bool = False,
) -> Path:
    """Dispatch once after fsynced reservation; never resume an existing root."""
    if (type(contact_email) is not str or _CONTACT.fullmatch(contact_email) is None
            or len(contact_email) > 254 or not contact_email.isascii()
            or not callable(transport) or type(protected_roots) is not tuple
            or type(observed) is not bool):
        _refuse("diagnostic contact or transport is malformed")
    manifest = _binding_manifest(receipt, capture_git_commit=capture_git_commit)
    if observed:
        if (transport is not _selected_sec_transport
                or Path(output_root) != _OBSERVED_DIAGNOSTIC_ROOT
                or receipt.v3_root != _OBSERVED_V3_ROOT
                or receipt.capture_git_commit
                != "aa0d635d00b64825bf8003289e0a60279bd52e73"
                or receipt.completed_new_count != 1_846
                or receipt.attempt_count != 1_847):
            _refuse("observed diagnostic transport or fixed binding differs")
        _verify_exact_committed_code(capture_git_commit)
    elif transport is _selected_sec_transport:
        _refuse("synthetic diagnostic cannot use production SEC transport")
    try:
        output = _plain_path(output_root, must_exist=False)
        protected = tuple(_plain_path(path, must_exist=True)
                          for path in (receipt.v3_root, *protected_roots))
        for source in (_LANE_ROOT, *protected):
            _refuse_output_overlap(output, source)
    except SecPilotError as exc:
        raise AmbiguousParentDiagnosticError(
            "REFUSED: diagnostic output overlaps or traverses a source"
        ) from exc
    if output.exists() or output.is_symlink():
        _refuse("one-shot v3 ambiguity diagnostic root already exists")
    output.mkdir(mode=0o700)
    current = output.lstat()
    if not stat.S_ISDIR(current.st_mode) or stat.S_IMODE(current.st_mode) != 0o700:
        _refuse("diagnostic root is not a private directory")
    # Fsync the new directory entry before any network operation.  The
    # subsequent immutable manifest/start publishes fsync their own files.
    parent_fd = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(parent_fd)
        named_parent = output.parent.lstat()
        opened_parent = os.fstat(parent_fd)
        if (not stat.S_ISDIR(named_parent.st_mode)
                or (named_parent.st_dev, named_parent.st_ino)
                != (opened_parent.st_dev, opened_parent.st_ino)):
            _refuse("diagnostic parent changed during durable reservation")
    finally:
        os.close(parent_fd)
    identity = current.st_dev, current.st_ino
    lock = _RootLock(output, identity, resume=False)
    try:
        (output / "objects").mkdir(mode=0o700)
        manifest_raw = _bytes(manifest)
        manifest_sha256 = hash_bytes(manifest_raw)
        if len(manifest_raw) > MAX_RESPONSE_METADATA_BYTES:
            _refuse("diagnostic manifest exceeds its bound")
        _publish_immutable(output, "manifest.json", manifest_raw, identity)
        start_raw = _bytes({
            "kind": DIAGNOSTIC_VERSION + "/attempt-start",
            "manifest_sha256": manifest_sha256,
            "attempt": 1,
            "started_utc": _utc(),
        })
        _publish_immutable(output, "attempt-start.json", start_raw, identity)
        # The existing v3 start is not resolved by this separate request.
        # The new start consumes exactly one duplicate-risk authorization.
        request = receipt.pending_request.to_payload()
        headers = {
            "User-Agent": f"InsiderBuyingResearch/0.1 ({contact_email})",
            "Accept": "*/*", "Accept-Encoding": "identity", "Connection": "close",
        }
        if observed:
            # The root/manifest/start are durable; lane drift here consumes
            # the diagnostic without allowing a network request.
            _verify_exact_committed_code(capture_git_commit)
        status: int | None = None
        response_headers: list[list[str]] | None = None
        body_sha256: str | None = None
        body_size_bytes: int | None = None
        transport_outcome = "returned"
        envelope_outcome = "not_checked"
        envelope_reason: str | None = None
        try:
            result = transport(request["url"], headers, MAX_COMPLETE_TXT_BYTES)
        except (OSError, http.client.HTTPException):
            transport_outcome = "network_error"
        except SecCompleteAcquisitionError:
            transport_outcome = "transport_refusal"
        else:
            status = result.status if type(result) is SecHttpResult and type(result.status) is int else None
            try:
                response_headers = _response_headers(result)
                if status == 200:
                    raw = _strict_selected_response(result, max_bytes=MAX_COMPLETE_TXT_BYTES)
                    descriptor = _store_object(output, raw, identity)
                    body_sha256 = descriptor["sha256"]
                    body_size_bytes = descriptor["size_bytes"]
                elif type(result.body) is not bytes or result.body != b"":
                    _refuse("non-200 diagnostic response unexpectedly includes a body")
            except (AmbiguousParentDiagnosticError, SecCompleteAcquisitionError):
                transport_outcome = "transport_refusal"
            else:
                response_raw = _bytes({
                    "kind": DIAGNOSTIC_VERSION + "/response",
                    "status": status,
                    "headers": response_headers,
                    "headers_sha256": hash_payload(response_headers),
                    "body_sha256": body_sha256,
                    "body_size_bytes": body_size_bytes,
                })
                if len(response_raw) > MAX_RESPONSE_METADATA_BYTES:
                    _refuse("diagnostic response descriptor exceeds its bound")
                _publish_immutable(output, "response.json", response_raw, identity)
                if status == 200:
                    try:
                        _validate_parent_header(raw, request)
                    except CampaignError as exc:
                        envelope_outcome = "refused"
                        # A static parser reason stays in the private report.
                        envelope_reason = str(exc)
                    else:
                        envelope_outcome = "accepted"
        report = {
            "kind": DIAGNOSTIC_VERSION + "/report",
            "manifest_sha256": manifest_sha256,
            "attempt_start_sha256": hash_bytes(start_raw),
            "transport_outcome": transport_outcome,
            "status": status,
            "response_headers_sha256": (
                hash_payload(response_headers) if response_headers is not None else None
            ),
            "body_sha256": body_sha256,
            "body_size_bytes": body_size_bytes,
            "envelope_outcome": envelope_outcome,
            "envelope_reason": envelope_reason,
            "finished_utc": _utc(),
            "v3_campaign_advanced": False,
            "source_authenticated": False,
            "canonical_evidence": False,
            "point_in_time_data": False,
            "outcome_looks": 0,
            "qc_jobs": 0,
        }
        report_raw = _bytes(report)
        if len(report_raw) > MAX_RESPONSE_METADATA_BYTES:
            _refuse("diagnostic report exceeds its bound")
        report_sha256 = hash_bytes(report_raw)
        report_name = f"diagnostic-report-{report_sha256}.json"
        _publish_immutable(output, report_name, report_raw, identity)
        _publish_immutable(output, "commit.json", _bytes({
            "kind": DIAGNOSTIC_VERSION + "/commit",
            "report_name": report_name,
            "report_sha256": report_sha256,
            "manifest_sha256": manifest_sha256,
        }), identity)
        return output / report_name
    finally:
        lock.close()


def run_observed_v3_ambiguous_parent_diagnostic(
    raw_q4_directory: str | Path, parsed_q4_directory: str | Path,
    raw_q1_directory: str | Path, parsed_q1_directory: str | Path,
    exact16_pilot_root: str | Path, selected_root: str | Path,
    prior_campaign_root: str | Path, diagnostic_root: str | Path,
    v3_root: str | Path, *, contact_email: str, capture_git_commit: str,
) -> Path:
    """Make at most one SEC request for the exact observed v3 pending parent."""
    _verify_exact_committed_code(capture_git_commit)
    try:
        old = _plain_path(prior_campaign_root, must_exist=True)
        prior_diagnostic = _plain_path(diagnostic_root, must_exist=True)
        selected = _plain_path(selected_root, must_exist=True)
        v3 = _plain_path(v3_root, must_exist=True)
        if (v3 != _OBSERVED_V3_ROOT
                or old != _OBSERVED_V3_ROOT.parent / "all-form4-parents"
                or prior_diagnostic != old.parent / "refused-parent-diagnostic-v1"
                or selected != Path(
                    "/Users/sheltonchen/Documents/Codex/2026-09-03/f/"
                    "insider-source-20260929.hP4utF/selected-parents-v2"
                )):
            _refuse("observed diagnostic source paths differ from stopped v3")
    except SecPilotError as exc:
        raise AmbiguousParentDiagnosticError(
            "REFUSED: observed diagnostic source path is unsafe"
        ) from exc
    receipt = load_observed_partial_all_form4_recovery_v3(
        raw_q4_directory, parsed_q4_directory,
        raw_q1_directory, parsed_q1_directory,
        exact16_pilot_root, selected, old, prior_diagnostic, v3,
    )
    if receipt.v3_root != v3 or receipt.capture_git_commit != (
        "aa0d635d00b64825bf8003289e0a60279bd52e73"
    ):
        _refuse("observed diagnostic binding differs from stopped v3")
    _verify_exact_committed_code(capture_git_commit)
    result = _capture_one(
        receipt, _OBSERVED_DIAGNOSTIC_ROOT,
        transport=_selected_sec_transport, contact_email=contact_email,
        capture_git_commit=capture_git_commit,
        protected_roots=(
            old, prior_diagnostic, selected,
            _plain_path(raw_q4_directory, must_exist=True),
            _plain_path(parsed_q4_directory, must_exist=True),
            _plain_path(raw_q1_directory, must_exist=True),
            _plain_path(parsed_q1_directory, must_exist=True),
            _plain_path(exact16_pilot_root, must_exist=True),
        ),
        observed=True,
    )
    _verify_exact_committed_code(capture_git_commit)
    return result


__all__ = [
    "AmbiguousParentDiagnosticError", "DIAGNOSTIC_VERSION",
    "run_observed_v3_ambiguous_parent_diagnostic",
]
