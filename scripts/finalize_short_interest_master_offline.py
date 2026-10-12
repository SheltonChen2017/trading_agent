"""Finalize only the named captured master offline; never retry a provider.

The original 12 requests remain consumed and their safe refusal is retained.
No credentials are read and no provider transport exists in this runtime.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.sharadar_securities_master as master
import research.short_interest_etf.sharadar_master_segments as segments
from scripts.capture_short_interest_securities_master import _metadata
from scripts.qualify_finra_short_interest import (
    CapturePlatformRefusal, CaptureRefusal, _prepare_capture_directory,
    _publish, _publish_json, _require_capture_platform,
)
from scripts.qualify_sharadar_companion import _guard, _utc_now
from scripts.qualify_short_interest_action_supplement import _clock, _parse_receipt, _protected_bytes

SOURCE = Path("artifacts/short_interest/sharadar_securities_master/sharadar-master-20261012T055800Z")
SOURCE_HEAD = "a5ac4c22499e13f04776a8fa145fd3dba72bc383"
SOURCE_REMOTE = "2a65d4a0defc73cad085642e61492e220f576d81"
SOURCE_INVENTORY_SHA256 = "af57bd5bcbfc435051946be51e6671e7de8f77b0c7739bddc23f89d0e8f48726"
BUDGET_SHA256 = "76170777b03b8a1e553777494ffa564c817975f5f4f0b15fffea0651066dcdbd"
OUTPUT_NAME = "offline-parts-v1"
RAW_ORDINALS = (1, 2, 3, 4, 5, 6, 8, 10, 12)


class MasterFinalizationRefusal(CaptureRefusal):
    pass


def _require(condition, reason):
    if not condition:
        raise MasterFinalizationRefusal(reason)


def _source_names():
    return sorted(["protocol.json", "started.json", "refused.json"]
        + [f"attempt-{i:02d}.{suffix}.json" for i in range(1, 13) for suffix in ("started", "received")]
        + [f"attempt-{i:02d}.raw" for i in RAW_ORDINALS])


def _reload(root: Path):
    """Hash captured protected bytes before parsing; no latest-file lookup."""
    _require_capture_platform()
    directory = root / SOURCE
    names = _source_names()
    # A previously created exclusive output may exist, but no source replacement
    # or new attempt/refusal file is silently ignored.
    _require({p.name for p in directory.iterdir()} - {OUTPUT_NAME} == set(names), "source_inventory_names")
    blobs = {name: _protected_bytes(directory / name,
             (master.MAXIMUM_ARCHIVE_BYTES if name.startswith(("attempt-08", "attempt-10", "attempt-12"))
              else 131072 if name.startswith(("attempt-04", "attempt-05", "attempt-06")) else 65536)
             if name.endswith(".raw") else 65536) for name in names}
    _require(hash_payload([{"name": name, "sha256": hash_bytes(blobs[name])} for name in names])
             == SOURCE_INVENTORY_SHA256, "source_inventory_hash")
    claim = _protected_bytes(directory.parent / ("budget-" + master.PROTOCOL_SHA256 + ".json"), 65536)
    _require(hash_bytes(claim) == BUDGET_SHA256, "source_budget_hash")
    budget, start, end = (_parse_receipt(value) for value in
                         (claim, blobs["started.json"], blobs["refused.json"]))
    _require(start == {
        "schema": "si-sharadar-master-capture-start-v1", "run_id": directory.name,
        "started_at": start.get("started_at"), "code_head": SOURCE_HEAD,
        "remote_head": SOURCE_REMOTE, "protocol_sha256": master.PROTOCOL_SHA256,
        "maximum_attempts": 12, "source_only": True, "outcome_looks_consumed": 0,
        "qc_launch_attempts": 0}, "source_start_binding")
    _require(type(start["maximum_attempts"]) is int and start["source_only"] is True
        and all(type(start[key]) is int for key in ("outcome_looks_consumed", "qc_launch_attempts")), "source_start_types")
    _require(budget == {
        "schema": "si-sharadar-master-whole-round-budget-v1", "run_id": directory.name,
        "protocol_sha256": master.PROTOCOL_SHA256, "code_head": SOURCE_HEAD,
        "remote_head": SOURCE_REMOTE, "maximum_attempts": 12,
        "started_at": start["started_at"], "resumption_allowed": False}, "source_budget_binding")
    _require(type(budget["maximum_attempts"]) is int and budget["resumption_allowed"] is False, "source_budget_types")
    _require(end == {"status": "capture_refused", "code": "private_report_size_limit",
        "http_status": None, "backtest_result_exists": False, "refused_at": end.get("refused_at"),
        "outcome_looks_consumed": 0, "qc_launch_attempts": 0}, "source_terminal_binding")
    _require(end["backtest_result_exists"] is False
        and all(type(end[key]) is int for key in ("outcome_looks_consumed", "qc_launch_attempts")), "source_terminal_types")
    _require(_parse_receipt(blobs["protocol.json"]) == master.qualification_protocol(), "source_protocol_binding")
    previous = _clock(start["started_at"])
    captures, metadata = [], {}
    for ordinal, request_id in enumerate(master.REQUEST_IDS, 1):
        prefix = f"attempt-{ordinal:02d}"
        began = _parse_receipt(blobs[prefix + ".started.json"])
        received = _parse_receipt(blobs[prefix + ".received.json"])
        kind, table = request_id.split("-", 1)
        _require(began == {"schema": "si-sharadar-master-request-start-v1", "attempt": ordinal,
            "request_id": request_id, "request": master.sharadar_master_request(request_id),
            "request_sha256": master.request_sha256(request_id), "code_head": SOURCE_HEAD,
            "protocol_sha256": master.PROTOCOL_SHA256, "started_at": began.get("started_at")}, "request_start_binding")
        _require(type(began.get("attempt")) is int and type(received.get("attempt")) is int,
                 "request_integer_ordinal")
        raw = None if kind == "issue" else blobs[prefix + ".raw"]
        _require(received == {"schema": "si-sharadar-master-response-receipt-v1", "attempt": ordinal,
            "request_id": request_id, "request_sha256": master.request_sha256(request_id),
            "http_status": 302 if kind == "issue" else 200,
            "content_type": None if raw is None else received.get("content_type"),
            "raw_path": None if raw is None else prefix + ".raw",
            "raw_bytes": None if raw is None else len(raw),
            "raw_sha256": None if raw is None else hash_bytes(raw),
            "received_at": received.get("received_at"), "signed_URL_persisted_or_hashed": False}, "response_receipt_binding")
        _require(type(received.get("http_status")) is int
            and received["signed_URL_persisted_or_hashed"] is False
            and (raw is None or type(received.get("raw_bytes")) is int), "response_integer_fields")
        began_at, received_at = _clock(began["started_at"]), _clock(received["received_at"])
        _require(previous <= began_at <= received_at, "source_receipt_chronology")
        previous = received_at
        if kind == "metadata":
            metadata[table] = _metadata(raw, table, received["received_at"])
        elif kind == "schema":
            text = raw.decode("utf-8")
            _require("CREATE TABLE" in text and re.search(r"\b" + table + r"\b", text, re.I), "source_schema")
        elif kind == "download":
            _require(len(raw) == metadata[table]["size"], "source_metadata_race_sentinel")
            master.validate_archive(table, raw)
            captures.append(master.CapturedSharadarMasterArchive(table, raw, master.request_sha256(request_id)))
    _require(previous <= _clock(end["refused_at"]), "source_terminal_chronology")
    # The original unpersisted report clock/hash is unavailable. This observed
    # terminal clock anchors the new offline reconstruction, explicitly.
    return tuple(captures), end["refused_at"]


def _code_identity(root: Path, head: str) -> str:
    names = ("research/short_interest_etf/sharadar_securities_master.py",
             "research/short_interest_etf/sharadar_master_segments.py",
             "scripts/finalize_short_interest_master_offline.py")
    return hash_payload({"git_commit": head, "files": [
        {"path": name, "sha256": hash_bytes((root / name).read_bytes())} for name in names]})


def _write_report(root: Path, directory: Path, captures, anchor: str, *, head: str, remote: str, started: str):
    _require_capture_platform()
    _publish_json(directory, "started.json", {"schema": "si-master-offline-finalization-start-v1",
        "code_head": head, "source_code_head": SOURCE_HEAD,
        "source_inventory_sha256": SOURCE_INVENTORY_SHA256,
        "source_reconstruction_anchor": anchor, "started_at": started,
        "provider_requests": 0, "credential_reads": 0, "qc_attempts": 0, "outcome_looks": 0})
    report = master.qualify_sharadar_securities_master(captures, retrieved_at=anchor)
    encoded = canonical_json(report.to_payload()).encode("utf-8")
    provenance = segments.MasterReportProvenance(
        source_capture_receipt_sha256=SOURCE_INVENTORY_SHA256,
        source_code_identity_sha256=hash_payload({"git_commit": SOURCE_HEAD, "protocol_sha256": master.PROTOCOL_SHA256}),
        finalizer_code_identity_sha256=_code_identity(root, head), reconstruction_anchor_utc=anchor)
    segmented = segments.encode_report(encoded, provenance=provenance)
    for ordinal, part in enumerate(segmented.parts, 1):
        _guard(root, head, remote)
        _publish(directory, f"part-{ordinal:03d}.private", part)
    _publish(directory, "index.private.json", segmented.index.to_bytes())
    _guard(root, head, remote)
    completed = _utc_now()
    _require(_clock(completed) >= _clock(started), "finalization_completion_chronology")
    result = {"schema": "si-master-offline-finalization-complete-v1", "status": "offline_finalization_complete",
              "code_head": head, "source_code_head": SOURCE_HEAD,
              "private_index_sha256": segmented.index.to_payload()["index_sha256"], "completed_at": completed,
              "provider_requests": 0, "credential_reads": 0, "qc_attempts": 0,
              "outcome_looks": 0, "backtest_result_exists": False}
    _publish_json(directory, "completed.json", result)
    return result


def _finalize(root: Path, *, head: str, remote: str):
    _require_capture_platform()
    _guard(root, head, remote)
    captures, anchor = _reload(root)
    started = _utc_now()
    _require(_clock(started) >= _clock(anchor), "finalization_start_chronology")
    directory = _prepare_capture_directory(root / SOURCE / OUTPUT_NAME)
    # Only this invocation's successful exclusive mkdir grants ownership of
    # refusal publication. An early guard or rerun cannot mutate older output.
    try:
        return _write_report(root, directory, captures, anchor, head=head, remote=remote, started=started)
    except (CaptureRefusal, ValueError, OSError, KeyError, UnicodeError):
        _publish_json(directory, "refused.json", {"status": "offline_finalization_refused",
            "refused_at": _utc_now(), "provider_requests": 0, "credential_reads": 0,
            "qc_attempts": 0, "outcome_looks": 0, "backtest_result_exists": False})
        raise MasterFinalizationRefusal("offline_owned_output_refused") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-remote", required=True)
    args = parser.parse_args(argv)
    try:
        _require_capture_platform()
        result = _finalize(Path.cwd().resolve(), head=args.expected_head, remote=args.expected_remote)
    except (CaptureRefusal, ValueError, OSError, KeyError, UnicodeError) as exc:
        # Never publish external exceptions, paths, source rows or account facts.
        result = {"status": "offline_finalization_refused", "provider_requests": 0,
                  "credential_reads": 0, "backtest_result_exists": False}
        if type(exc) is CapturePlatformRefusal:
            result.update(code=exc.code, ready_for_empirical_backtest=False)
        print(json.dumps(result))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
