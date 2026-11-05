"""Offline source-language qualification of the exact retained SEC original.

No transport, key reader, new source request, outcome join or QuantConnect
operation exists here. The old capture and its budget remain immutable.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.terminal_original_evidence as evidence
import scripts.verify_short_interest_terminal_originals as originals
from scripts.qualify_finra_short_interest import CapturePlatformRefusal, CaptureRefusal, _git, _prepare_capture_directory, _require_capture_platform
from scripts.qualify_sharadar_companion import _guard, _utc_now
from scripts.qualify_short_interest_action_supplement import _clock, _parse_receipt

SOURCE = Path("artifacts/short_interest/terminal_originals/terminal-originals-20261013T224853Z")
SOURCE_HEAD = "9e05c7f1c3184afeca0a1748a3335da4a37483c6"
SOURCE_PROTOCOL_SHA256 = "9ca6368824557c81610e1017f45dbc47dee8fd626cc7582b10b7caca5ee9f84c"
SOURCE_REPORT_SHA256 = "57408dcd988e3a18edd0d1721571a7b176babd57859f4e5e8814c6775cd8ebc9"
SOURCE_REPORT_BYTES_SHA256 = "e91e9a1b16cb37fb79b514774f3bee0b8c6cde3f384ce24c2787acde0c39ac58"
OUTPUT = Path("artifacts/short_interest/terminal_original_evidence/terminal-original-evidence-source-20261013T224853Z")
_CODE_FILES = originals._CODE_FILES + (
    "research/short_interest_etf/terminal_original_evidence.py",
    "scripts/qualify_short_interest_terminal_original_offline.py",
)


class TerminalOriginalOfflineRefusal(CaptureRefusal):
    def __init__(self, code):
        self.code, self.http_status = code, None
        super().__init__(code)


def _require(condition, code):
    if not condition:
        raise TerminalOriginalOfflineRefusal(code)


def build_protocol():
    return {"schema": "si-terminal-original-offline-protocol-v1", "source": str(SOURCE),
            "source_head": SOURCE_HEAD, "source_protocol_sha256": SOURCE_PROTOCOL_SHA256,
            "source_report_sha256": SOURCE_REPORT_SHA256, "source_report_bytes_sha256": SOURCE_REPORT_BYTES_SHA256,
            "evidence_policy_sha256": evidence.PROTOCOL_SHA256, "evidence_policy": evidence.evidence_protocol(),
            "output": str(OUTPUT), "scope": "private_source_language_not_semantic_or_cashflow_admission",
            "provider_requests": 0, "credential_reads": 0, "outcome_looks": 0,
            "qc_attempts": 0, "backtest_result_exists": False}


def _historical_identity(root, *, head, remote):
    _require_capture_platform()
    files = []
    for name in originals._CODE_FILES:
        _guard(root, head, remote)
        result = subprocess.run(["git", "show", SOURCE_HEAD + ":" + name], cwd=root,
                                capture_output=True, check=False)
        _require(type(result.returncode) is int and result.returncode == 0 and type(result.stdout) is bytes,
                 "original_source_code_blob")
        files.append({"path": name, "sha256": hash_bytes(result.stdout)})
    return hash_payload({"git_commit": SOURCE_HEAD, "files": files})


def _source(root, *, head, remote):
    _require_capture_platform()
    _guard(root, head, remote)
    upstream = originals._source(root, head=head, remote=remote)
    protocol = originals.build_protocol(upstream)
    _require(hash_payload(protocol) == SOURCE_PROTOCOL_SHA256
             and originals.EXPECTED_PROTOCOL_SHA256 == SOURCE_PROTOCOL_SHA256, "original_source_protocol")
    directory = root / SOURCE
    def read(name, maximum=65536):
        return originals._read(root, directory / name, maximum, head=head, remote=remote)
    _require(canonical_json(_parse_receipt(read("protocol.private.json", 131072))) == canonical_json(protocol),
             "original_source_protocol_bytes")
    start, end = (_parse_receipt(read(name)) for name in ("started.json", "completed.json"))
    _require(start.get("schema") == "si-terminal-original-start-v1"
             and start.get("code_head") == SOURCE_HEAD
             and start.get("code_identity_sha256") == _historical_identity(root, head=head, remote=remote)
             and start.get("protocol_sha256") == SOURCE_PROTOCOL_SHA256
             and end.get("schema") == "si-terminal-original-completion-v1"
             and end.get("status") == "capture_complete" and end.get("code_head") == SOURCE_HEAD
             and end.get("protocol_sha256") == SOURCE_PROTOCOL_SHA256
             and end.get("private_report_sha256") == SOURCE_REPORT_SHA256
             and end.get("backtest_result_exists") is False, "original_source_receipts")
    for receipt in (start, end):
        _require(all(type(receipt.get(key)) is int and receipt[key] == 0 for key in ("outcome_looks", "qc_attempts")),
                 "original_source_closed_counters")
    count = len(protocol["requests"])
    _require(type(start.get("maximum_attempts")) is int and start["maximum_attempts"] == count
             and type(end.get("http_attempts")) is int and end["http_attempts"] == count, "original_source_attempt_count")
    claim = _parse_receipt(originals._read(root, directory.parent / ("budget-" + SOURCE_PROTOCOL_SHA256 + ".json"),
                                         65536, head=head, remote=remote))
    _require(canonical_json(claim) == canonical_json({
        "schema": "si-terminal-original-budget-v1", "code_head": SOURCE_HEAD, "remote_head": start.get("remote_head"),
        "run_id": directory.name, "protocol_sha256": SOURCE_PROTOCOL_SHA256,
        "source_report_sha256": originals.SOURCE_REPORT_SHA256, "maximum_attempts": count,
        "started_at": start.get("started_at"), "resumption_or_restart_allowed": False}), "original_consumed_budget")
    previous = _clock(start.get("started_at"))
    _require(_clock(upstream["completed_at"]) <= previous, "original_upstream_chronology")
    inventory = {"protocol.private.json", "started.json", "completed.json", "originals.private.json"}
    documents, reconstructed_receipts = [], []
    for ordinal, descriptor in enumerate(protocol["requests"], 1):
        prefix, digest = f"attempt-{ordinal:02d}", hash_payload(descriptor)
        began = _parse_receipt(read(prefix + ".started.json"))
        received = _parse_receipt(read(prefix + ".received.json"))
        raw = read(prefix + ".raw", originals.MAXIMUM_BYTES)
        _require(canonical_json(began) == canonical_json({
            "schema": "si-terminal-original-request-start-v1", "attempt": ordinal,
            "request_id": descriptor["request_id"], "request": descriptor, "request_sha256": digest,
            "code_head": SOURCE_HEAD, "protocol_sha256": SOURCE_PROTOCOL_SHA256,
            "started_at": began.get("started_at")}), "original_request_binding")
        _require(canonical_json(received) == canonical_json({
            "schema": "si-terminal-original-response-v1", "attempt": ordinal,
            "request_id": descriptor["request_id"], "request_sha256": digest,
            "http_status": 200, "content_type": received.get("content_type"), "raw_path": prefix + ".raw",
            "raw_bytes": len(raw), "raw_sha256": hash_bytes(raw), "received_at": received.get("received_at")}),
            "original_response_binding")
        requested_at, received_at = _clock(began.get("started_at")), _clock(received.get("received_at"))
        _require(previous <= requested_at <= received_at, "original_source_chronology")
        previous = received_at
        documents.append(evidence.CapturedTerminalOriginal(canonical_json(descriptor), digest, raw, hash_bytes(raw),
                         received["received_at"], received["content_type"], SOURCE_PROTOCOL_SHA256, SOURCE_REPORT_SHA256))
        reconstructed_receipts.append({"descriptor": descriptor, "receipt": received,
                                       "HTTPS_transport_origin_verified": True,
                                       "terminal_economics_admitted": False, "payment_cash_settlement_verified": False})
        inventory.update((prefix + ".started.json", prefix + ".received.json", prefix + ".raw"))
    _guard(root, head, remote)
    _require({path.name for path in directory.iterdir()} == inventory, "original_source_inventory")
    raw = read("originals.private.json", 64 * 1024 * 1024)
    _require(hash_bytes(raw) == SOURCE_REPORT_BYTES_SHA256, "original_report_bytes")
    saved = _parse_receipt(raw)
    _require(previous <= _clock(saved.get("retrieved_at")) <= _clock(end.get("completed_at")),
             "original_source_completion_chronology")
    rebuilt = {"schema": "si-terminal-original-evidence-v1", "protocol_sha256": SOURCE_PROTOCOL_SHA256,
               "source_report_sha256": originals.SOURCE_REPORT_SHA256, "retrieved_at": saved["retrieved_at"],
               "documents": reconstructed_receipts, "missing_cases": protocol["missing_cases"],
               "terminal_economics_admitted": False, "payment_cash_settlement_verified": False,
               "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}
    rebuilt["report_sha256"] = hash_payload(rebuilt)
    _require(rebuilt["report_sha256"] == SOURCE_REPORT_SHA256
             and (canonical_json(rebuilt) + "\n").encode() == raw, "original_report_rebuild")
    return tuple(documents), end["completed_at"]


def _build(root, *, head, remote):
    _require_capture_platform()
    _guard(root, head, remote)
    documents, source_completed = _source(root, head=head, remote=remote)
    protocol = build_protocol()
    started_at = _utc_now()
    _require(_clock(source_completed) <= _clock(started_at), "offline_start_chronology")
    target = root / OUTPUT
    _require(_git(root, "check-ignore", str(target)) == str(target), "offline_output_not_ignored")
    _guard(root, head, remote)
    try:
        directory = _prepare_capture_directory(target)
    except FileExistsError:
        raise TerminalOriginalOfflineRefusal("terminal_original_output_already_exists") from None
    try:
        files = []
        for name in _CODE_FILES:
            _guard(root, head, remote)
            files.append({"path": name, "sha256": hash_bytes((root / name).read_bytes())})
        bindings = {"code_head": head, "remote_head": remote,
                    "code_identity_sha256": hash_payload({"git_commit": head, "files": files}),
                    "protocol_sha256": hash_payload(protocol), "source_report_sha256": SOURCE_REPORT_SHA256,
                    "source_report_bytes_sha256": SOURCE_REPORT_BYTES_SHA256,
                    "provider_requests": 0, "credential_reads": 0, "outcome_looks": 0,
                    "qc_attempts": 0, "backtest_result_exists": False}
        originals._publish_guarded(root, directory, "protocol.json", protocol, head=head, remote=remote)
        originals._publish_guarded(root, directory, "started.json", {
            "schema": "si-terminal-original-offline-start-v1", "started_at": started_at, **bindings}, head=head, remote=remote)
        report = evidence.qualify_terminal_original_evidence(documents, retrieved_at=started_at)
        raw = (canonical_json(report.to_payload()) + "\n").encode()
        _require(len(raw) <= 128 * 1024 * 1024, "private_evidence_size_limit")
        originals._publish_guarded(root, directory, "evidence.private.json", raw, head=head, remote=remote, raw=True)
        completed_at = _utc_now()
        _require(_clock(started_at) <= _clock(completed_at), "offline_completion_chronology")
        result = {"schema": "si-terminal-original-offline-completion-v1", "status": "terminal_original_offline_complete",
                  "started_at": started_at, "completed_at": completed_at, **bindings,
                  "private_report_sha256": report.sha256, "private_report_bytes_sha256": hash_bytes(raw)}
        originals._publish_guarded(root, directory, "completed.json", result, head=head, remote=remote)
        return result
    except (CaptureRefusal, ValueError, TypeError, OSError, UnicodeError, KeyError):
        originals._publish_guarded(root, directory, "refused.json", {
            "status": "terminal_original_offline_refused", "refused_at": _utc_now(), "provider_requests": 0,
            "credential_reads": 0, "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}, head=head, remote=remote)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-remote", required=True)
    args = parser.parse_args(argv)
    try:
        _require_capture_platform()
        result = _build(Path.cwd().resolve(), head=args.expected_head, remote=args.expected_remote)
    except (CaptureRefusal, ValueError, TypeError, OSError, UnicodeError, KeyError) as exc:
        safe = type(exc) in (CapturePlatformRefusal, TerminalOriginalOfflineRefusal)
        result = {"status": "terminal_original_offline_refused", "code": exc.code if safe else "offline_preflight_refused",
                  "provider_requests": 0, "credential_reads": 0, "outcome_looks": 0,
                  "qc_attempts": 0, "backtest_result_exists": False}
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
