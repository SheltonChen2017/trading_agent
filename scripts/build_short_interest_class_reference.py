"""Offline private native/composite/class pilot binding, never another capture.

Only the fixed original spent captures are read. There is no key, provider,
outcome or QuantConnect action. Every new output is exclusive and protected.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.massive_class_denominator as classes
import research.short_interest_etf.sharadar_class_reference as bridge
import research.short_interest_etf.sharadar_securities_master as master
import scripts.finalize_short_interest_master_offline as finalizer
import scripts.qualify_short_interest_class_denominator as class_reader
import scripts.qualify_short_interest_terminal_disclosure as terminal_reader
from scripts.qualify_finra_short_interest import (
    CapturePlatformRefusal, CaptureRefusal, _git, _prepare_capture_directory,
    _publish, _publish_json, _require_capture_platform,
)
from scripts.qualify_sharadar_companion import _guard, _utc_now
from scripts.qualify_short_interest_action_supplement import _clock, _protected_bytes, _parse_receipt


CLASS_SOURCE = Path("artifacts/short_interest/massive_class_denominator/massive-class-20261013T221700Z")
CLASS_HEAD = "4539682f1aff52fc0166c30f23dfeaa6197b72db"
CLASS_REPORT_BYTES_SHA256 = "a37a030e256e558769e040f82979c74cc98dfc24cc4123aaf118848da1edbb03"
CLASS_REPORT_SHA256 = "f4b3317db3d83b12e824fa7d2f9055666e46502d2042a9bb4a7ff9362133250a"
OUTPUT = Path("artifacts/short_interest/class_reference/class-reference-source-20261013T221700Z")
MAXIMUM_REPORT_BYTES = 128 * 1024 * 1024
_CODE_FILES = (
    "data/hashing.py", "research/short_interest_etf/contracts.py",
    "research/short_interest_etf/massive_class_denominator.py",
    "research/short_interest_etf/sharadar_securities_master.py",
    "research/short_interest_etf/sharadar_class_reference.py",
    "scripts/qualify_finra_short_interest.py", "scripts/qualify_sharadar_companion.py",
    "scripts/qualify_short_interest_action_supplement.py",
    "scripts/finalize_short_interest_master_offline.py",
    "scripts/build_short_interest_native_master_offline.py",
    "scripts/qualify_short_interest_class_denominator.py",
    "scripts/qualify_short_interest_terminal_disclosure.py",
    "scripts/build_short_interest_class_reference.py",
)


class ClassReferenceOfflineRefusal(CaptureRefusal):
    """Fixed local codes never expose rows, contacts or source fitness."""


def _require(condition, reason):
    if not condition:
        raise ClassReferenceOfflineRefusal(reason)


def build_protocol():
    return {"schema": "si-class-reference-offline-protocol-v1",
            "bridge_protocol_sha256": bridge.PROTOCOL_SHA256,
            "bridge_protocol": bridge.class_reference_protocol(),
            "class_source": str(CLASS_SOURCE), "class_source_head": CLASS_HEAD,
            "class_report_bytes_sha256": CLASS_REPORT_BYTES_SHA256,
            "class_report_sha256": CLASS_REPORT_SHA256,
            "original_source_pins": class_reader._source_pins(),
            "output": str(OUTPUT), "maximum_report_bytes": MAXIMUM_REPORT_BYTES,
            "reconstruction": "fixed_original_spent_sources_one_TICKERS_parse_no_recapture",
            "publication_scope": "private_source_only_no_rows_counts_or_fitness_publication",
            "provider_requests": 0, "credential_reads": 0, "outcome_looks": 0,
            "qc_attempts": 0, "backtest_result_exists": False}


def _class_source(root):
    """Use the verified source custodian, then reconstruct exact typed bytes."""
    _require_capture_platform()
    _require(terminal_reader.CLASS_SOURCE == CLASS_SOURCE
             and terminal_reader.CLASS_HEAD == CLASS_HEAD
             and terminal_reader.CLASS_REPORT_SHA256 == CLASS_REPORT_SHA256
             and terminal_reader.CLASS_REPORT_BYTES_SHA256 == CLASS_REPORT_BYTES_SHA256,
             "fixed_class_source_pins_changed")
    saved = terminal_reader._source(root)
    directory = root / CLASS_SOURCE
    captures = []
    for ordinal, rid in enumerate(classes.REQUEST_IDS, 1):
        prefix = f"attempt-{ordinal:02d}"
        received = _parse_receipt(_protected_bytes(directory / (prefix + ".received.json"), 65536))
        observed = received.get("body_observed")
        _require(type(observed) is bool and received.get("request_id") == rid
                 and received.get("request_sha256") == classes.request_sha256(rid),
                 "class_typed_reconstruction_receipt")
        raw = _protected_bytes(directory / (prefix + ".raw"), classes.MAXIMUM_RESPONSE_BYTES) if observed else b""
        _require((not observed and received.get("raw_sha256") is None)
                 or (observed and received.get("raw_sha256") == hash_bytes(raw)),
                 "class_typed_reconstruction_bytes")
        captures.append(classes.CapturedMassiveClassResponse(
            rid, classes.request_sha256(rid), raw, received["received_at"], hash_bytes(raw),
            received["http_status"], received.get("content_type") or "", observed))
    qualified = classes.qualify_massive_class_denominator(tuple(captures), retrieved_at=saved["retrieved_at"])
    _require(qualified.sha256 == CLASS_REPORT_SHA256
             and hash_bytes(qualified.to_bytes()) == CLASS_REPORT_BYTES_SHA256
             and canonical_json(qualified.to_payload()) == canonical_json(saved),
             "class_typed_report_rebuild")
    return qualified


def _sources(root):
    _require_capture_platform()
    # Verifies original receipts, native file pins and consumed budget; never
    # invokes the named key reader or provider transports in that runtime.
    _require(canonical_json(class_reader._source_preflight(root)) == canonical_json(class_reader._source_pins()),
             "original_native_source_pins")
    archives, _ = finalizer._reload(root)
    _require(type(archives) is tuple and len(archives) == 3
             and all(type(value) is master.CapturedSharadarMasterArchive for value in archives)
             and tuple(value.table for value in archives) == master.TABLES,
             "original_master_archive_inventory")
    return archives[0], _class_source(root)


def _code_identity(root, head):
    return hash_payload({"git_commit": head, "files": [
        {"path": name, "sha256": hash_bytes((root / name).read_bytes())} for name in _CODE_FILES]})


def _build(root, *, head, remote):
    _require_capture_platform()
    _guard(root, head, remote)
    protocol = build_protocol()
    tickers, source = _sources(root)
    started = _utc_now()
    _require(_clock(started) >= _clock(source.to_payload()["retrieved_at"]), "offline_source_chronology")
    target, owned = root / OUTPUT, False
    try:
        _guard(root, head, remote)
        _require(_git(root, "check-ignore", str(target)) == str(target), "output_not_ignored")
        try:
            directory = _prepare_capture_directory(target)
        except FileExistsError:
            raise ClassReferenceOfflineRefusal("class_reference_output_already_exists") from None
        owned = True
        _guard(root, head, remote)
        _publish_json(directory, "protocol.json", protocol)
        code_identity = _code_identity(root, head)
        _guard(root, head, remote)
        _publish_json(directory, "started.json", {
            "schema": "si-class-reference-offline-start-v1", "code_head": head,
            "code_identity_sha256": code_identity, "protocol_sha256": hash_payload(protocol),
            "source_class_report_sha256": CLASS_REPORT_SHA256, "started_at": started,
            "provider_requests": 0, "credential_reads": 0, "outcome_looks": 0, "qc_attempts": 0})
        report = bridge.qualify_sharadar_class_reference(tickers, source, retrieved_at=started)
        raw = report.to_bytes()
        _require(type(raw) is bytes and len(raw) <= MAXIMUM_REPORT_BYTES, "private_bridge_report_size")
        _guard(root, head, remote)
        _publish(directory, "reference.private.json", raw)
        completed = _utc_now()
        _require(_clock(completed) >= _clock(started), "offline_completion_chronology")
        result = {"schema": "si-class-reference-offline-completion-v1", "status": "class_reference_offline_complete",
                  "code_head": head, "code_identity_sha256": code_identity,
                  "protocol_sha256": hash_payload(protocol), "bridge_protocol_sha256": bridge.PROTOCOL_SHA256,
                  "private_report_sha256": report.sha256, "private_report_bytes_sha256": hash_bytes(raw),
                  "completed_at": completed, "provider_requests": 0, "credential_reads": 0,
                  "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}
        _guard(root, head, remote)
        _publish_json(directory, "completed.json", result)
        return result
    except (CaptureRefusal, ValueError, TypeError, OSError, KeyError, UnicodeError):
        if owned:
            _guard(root, head, remote)
            _publish_json(directory, "refused.json", {"schema": "si-class-reference-offline-refusal-v1",
                "status": "class_reference_offline_refused", "refused_at": _utc_now(),
                "provider_requests": 0, "credential_reads": 0, "outcome_looks": 0,
                "qc_attempts": 0, "backtest_result_exists": False})
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-remote", required=True)
    args = parser.parse_args(argv)
    try:
        _require_capture_platform()
        result = _build(Path.cwd().resolve(), head=args.expected_head, remote=args.expected_remote)
    except (CaptureRefusal, ValueError, TypeError, OSError, KeyError, UnicodeError) as exc:
        result = {"status": "class_reference_offline_refused", "provider_requests": 0,
                  "credential_reads": 0, "outcome_looks": 0, "qc_attempts": 0,
                  "backtest_result_exists": False}
        if type(exc) is CapturePlatformRefusal:
            result.update(code=exc.code, ready_for_empirical_backtest=False)
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
