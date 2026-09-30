"""One-shot custody of the campaign's refused SEC parent response.

The real entry accepts only the exact request returned by independent,
read-only replay of the incomplete original campaign. It writes to a new
private sibling root and never modifies that campaign or advances its status.
No import, preflight, or offline inspection sends a request.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import http.client
import os
import re
import stat
import subprocess

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying_sec_acquisition import (
    _plain_path, _publish_immutable, _refuse_output_overlap, _store_object,
)
from research.insider_buying_sec_all_form4_parent_campaign import (
    CampaignError, CampaignRequest, _validate_parent_header,
)
from research.insider_buying_sec_complete_acquisition import (
    MAX_COMPLETE_TXT_BYTES, SecCompleteAcquisitionError, SecHttpResult,
)
from research.insider_buying_sec_master82_runner import _RootLock
from research.insider_buying_sec_selected_parent_runner import (
    _selected_sec_transport, _strict_selected_response, _utc,
)


DIAGNOSTIC_VERSION = "INSETF-SEC-REFUSED-PARENT-DIAGNOSTIC-v1"
MAX_RESPONSE_METADATA_BYTES = 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_CONTACT = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}\Z")
_LANE_ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
_PRIOR_CAMPAIGN_ROOT = Path(
    "/Users/sheltonchen/Documents/Codex/2026-09-03/f/"
    "insider-source-allparents-20260929.3Nut2i/all-form4-parents"
)


class RefusedParentDiagnosticError(ValueError):
    """The one-shot diagnostic refused an input or publication."""


def _refuse(reason: str) -> None:
    raise RefusedParentDiagnosticError(f"REFUSED: {reason}")


def _bytes(value: object) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


@dataclass(frozen=True, slots=True)
class RefusedParentBinding:
    """Frozen identity supplied by the partial campaign replayer."""

    request: CampaignRequest
    prior_campaign_plan_sha256: str
    prior_shard_report_sha256s: tuple[str, str]
    prior_shard_journal_sha256s: tuple[str, str]

    def to_manifest(self, *, capture_git_commit: str) -> dict[str, object]:
        if (type(self) is not RefusedParentBinding
                or type(self.request) is not CampaignRequest
                or type(self.prior_campaign_plan_sha256) is not str
                or _SHA.fullmatch(self.prior_campaign_plan_sha256) is None
                or type(self.prior_shard_report_sha256s) is not tuple
                or len(self.prior_shard_report_sha256s) != 2
                or type(self.prior_shard_journal_sha256s) is not tuple
                or len(self.prior_shard_journal_sha256s) != 2
                or any(type(value) is not str or _SHA.fullmatch(value) is None
                       for value in (*self.prior_shard_report_sha256s,
                                     *self.prior_shard_journal_sha256s))
                or type(capture_git_commit) is not str
                or _COMMIT.fullmatch(capture_git_commit) is None):
            _refuse("diagnostic source binding is malformed")
        request = self.request.to_payload()
        return {
            "kind": DIAGNOSTIC_VERSION + "/manifest",
            "capture_git_commit": capture_git_commit,
            "prior_campaign_plan_sha256": self.prior_campaign_plan_sha256,
            "prior_shard_report_sha256s": list(self.prior_shard_report_sha256s),
            "prior_shard_journal_sha256s": list(self.prior_shard_journal_sha256s),
            # The private manifest does not repeat the locator or SEC contact.
            "refused_request_sha256": hash_payload(request),
            "maximum_decoded_body_bytes": MAX_COMPLETE_TXT_BYTES,
            "maximum_dispatches": 1,
            "source_authenticated": False,
            "canonical_evidence": False,
            "point_in_time_data": False,
            "outcome_looks": 0,
            "qc_jobs": 0,
        }


def _verify_exact_committed_code(commit: str) -> None:
    """The real request is allowed only from this exact clean committed lane."""
    if type(commit) is not str or _COMMIT.fullmatch(commit) is None:
        _refuse("diagnostic capture commit is malformed")
    root = Path(__file__).resolve().parents[1]
    paths = (
        "research/insider_buying_sec_parent_refusal_diagnostic.py",
        "research/insider_buying_sec_all_form4_parent_recovery_preflight.py",
        "research/insider_buying_sec_all_form4_parent_campaign.py",
        "research/insider_buying_sec_selected_parent_runner.py",
        "research/insider_buying_sec_complete_acquisition.py",
        "research/insider_buying_sec_acquisition.py",
        "research/insider_buying/sec_complete_submission.py",
        "data/hashing.py",
    )
    try:
        command = lambda *args: subprocess.check_output(args, cwd=root, stderr=subprocess.DEVNULL)
        if (root != _LANE_ROOT
                or command("git", "rev-parse", "--show-toplevel").decode().strip() != str(root)
                or command("git", "branch", "--show-current").decode().strip()
                != "codex/strategy-insider-buying"
                or command("git", "rev-parse", "HEAD").decode().strip() != commit
                or command("git", "status", "--porcelain=v1", "--untracked-files=all")):
            _refuse("exact clean committed Insider lane is required")
        for relative in paths:
            committed = command("git", "show", f"{commit}:{relative}")
            if hash_bytes(committed) != hash_bytes((root / relative).read_bytes()):
                _refuse("committed diagnostic dependency differs on disk")
    except (OSError, UnicodeError, subprocess.CalledProcessError) as exc:
        raise RefusedParentDiagnosticError(
            "REFUSED: exact diagnostic code commit could not be verified"
        ) from exc


def _response_headers(result: SecHttpResult) -> list[list[str]]:
    if (type(result) is not SecHttpResult or type(result.status) is not int
            or type(result.headers) is not tuple
            or any(type(pair) is not tuple or len(pair) != 2
                   or type(pair[0]) is not str or type(pair[1]) is not str
                   for pair in result.headers)):
        _refuse("SEC transport result has malformed status or headers")
    headers = [[name, value] for name, value in result.headers]
    if len(_bytes(headers)) > MAX_RESPONSE_METADATA_BYTES:
        _refuse("SEC response headers exceed diagnostic bound")
    return headers


def _capture_one(
    binding: RefusedParentBinding,
    output_root: str | Path,
    *,
    transport: Callable[[str, dict[str, str], int], SecHttpResult],
    contact_email: str,
    capture_git_commit: str,
    protected_roots: tuple[Path, ...],
) -> Path:
    """One injected transport call for synthetic tests; real entry fixes it.

    A durable start marker consumes the one request. A process interrupted
    afterward has no resume or retry path, including when its result is lost.
    """
    if (type(contact_email) is not str or _CONTACT.fullmatch(contact_email) is None
            or len(contact_email) > 254 or not contact_email.isascii()
            or not callable(transport)):
        _refuse("diagnostic contact or transport is malformed")
    manifest = binding.to_manifest(capture_git_commit=capture_git_commit)
    output = _plain_path(output_root, must_exist=False)
    for protected in (_LANE_ROOT, *protected_roots):
        _refuse_output_overlap(output, _plain_path(protected, must_exist=True))
    if output.exists() or output.is_symlink():
        _refuse("one-shot diagnostic root already exists")
    output.mkdir(mode=0o700)
    current = output.lstat()
    if not stat.S_ISDIR(current.st_mode):
        _refuse("diagnostic root is not a directory")
    # The one-shot reservation must survive a power loss before a network
    # dispatch. Fsyncing only files inside the new root does not make the
    # parent's newly created directory entry durable.
    parent_fd = os.open(
        output.parent,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
    )
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
        _publish_immutable(output, "manifest.json", manifest_raw, identity)
        start_raw = _bytes({
            "kind": DIAGNOSTIC_VERSION + "/attempt-start",
            "manifest_sha256": manifest_sha256,
            "attempt": 1,
            "started_utc": _utc(),
        })
        _publish_immutable(output, "attempt-start.json", start_raw, identity)
        # Nothing after this point may dispatch again into this or another
        # recovered root. The original campaign's attempt remains immutable.
        request = binding.request.to_payload()
        headers = {
            "User-Agent": f"InsiderBuyingResearch/0.1 ({contact_email})",
            "Accept": "*/*", "Accept-Encoding": "identity", "Connection": "close",
        }
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
                    # Framing is checked before custody; the request-bound
                    # SEC envelope is checked only after fsynced publication.
                    raw = _strict_selected_response(result, max_bytes=MAX_COMPLETE_TXT_BYTES)
                    descriptor = _store_object(output, raw, identity)
                    body_sha256 = descriptor["sha256"]
                    body_size_bytes = descriptor["size_bytes"]
                elif result.body != b"":
                    _refuse("non-200 response unexpectedly includes a body")
            except (RefusedParentDiagnosticError, SecCompleteAcquisitionError):
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
                    _refuse("response descriptor exceeds diagnostic bound")
                _publish_immutable(output, "response.json", response_raw, identity)
                if status == 200:
                    try:
                        _validate_parent_header(raw, request)
                    except CampaignError as exc:
                        envelope_outcome = "refused"
                        # The parser emits static reasons. Keep them only in
                        # the private report, never in terminal output.
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
            "campaign_advanced": False,
            "source_authenticated": False,
            "canonical_evidence": False,
            "point_in_time_data": False,
            "outcome_looks": 0,
            "qc_jobs": 0,
        }
        report_raw = _bytes(report)
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


def run_observed_refused_parent_diagnostic(
    raw_q4_directory: str | Path,
    parsed_q4_directory: str | Path,
    raw_q1_directory: str | Path,
    parsed_q1_directory: str | Path,
    exact16_pilot_root: str | Path,
    selected_root: str | Path,
    prior_campaign_root: str | Path,
    *,
    contact_email: str,
    capture_git_commit: str,
) -> Path:
    """Verify the old campaign, then make at most one diagnostic SEC request.

    The output name is deterministic beside the original campaign root. An
    existing root is a consumed authorization and is never resumed.
    """
    _verify_exact_committed_code(capture_git_commit)
    # Lazy import keeps the standalone synthetic core testable while the
    # read-only recovery verifier is implemented in its own lane file.
    from research.insider_buying_sec_all_form4_parent_recovery_preflight import (
        load_observed_partial_all_form4_parent_campaign,
    )

    prior = _plain_path(prior_campaign_root, must_exist=True)
    if prior != _PRIOR_CAMPAIGN_ROOT:
        _refuse("exact prior campaign root is required")
    receipt = load_observed_partial_all_form4_parent_campaign(
        raw_q4_directory, parsed_q4_directory, raw_q1_directory,
        parsed_q1_directory, exact16_pilot_root, selected_root, prior,
    )
    binding = RefusedParentBinding(
        request=receipt.refused_request,
        prior_campaign_plan_sha256=receipt.prior_campaign_plan_sha256,
        prior_shard_report_sha256s=receipt.prior_shard_report_sha256s,
        prior_shard_journal_sha256s=receipt.prior_shard_journal_sha256s,
    )
    # No alternative root name or resume flag can turn a failed diagnostic
    # into a second dispatch through this entry.
    output = prior.parent / "refused-parent-diagnostic-v1"
    result = _capture_one(
        binding, output, transport=_selected_sec_transport,
        contact_email=contact_email, capture_git_commit=capture_git_commit,
        protected_roots=(prior, _plain_path(raw_q4_directory, must_exist=True),
                         _plain_path(parsed_q4_directory, must_exist=True),
                         _plain_path(raw_q1_directory, must_exist=True),
                         _plain_path(parsed_q1_directory, must_exist=True),
                         _plain_path(exact16_pilot_root, must_exist=True),
                         _plain_path(selected_root, must_exist=True)),
    )
    _verify_exact_committed_code(capture_git_commit)
    return result
