"""Build one private native-key index from the named completed offline master.

This is storage/source-key binding only. It reads no credentials, contacts no
provider and consumes no outcome look or QuantConnect attempt. Source-current
rewritten dataset keys are not historical raw-market aliases or denominators.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.sharadar_native_master_index as native
import research.short_interest_etf.sharadar_native_observations as observations
import research.short_interest_etf.sharadar_master_segments as segments
import research.short_interest_etf.sharadar_securities_master as master
import scripts.finalize_short_interest_master_offline as finalizer
import scripts.qualify_short_interest_action_supplement as companion_reader
from scripts.qualify_finra_short_interest import (
    CapturePlatformRefusal, CaptureRefusal, _git, _prepare_capture_directory,
    _publish, _publish_json, _require_capture_platform,
)
from scripts.qualify_sharadar_companion import _guard, _utc_now
from scripts.qualify_short_interest_action_supplement import _clock, _parse_receipt, _protected_bytes

SOURCE_FINALIZER_HEAD = "ab169b34f8763af7bd529ba98dbe151b5aa46e6c"
SOURCE_INDEX_SHA256 = "e00a748e53e6e5800a7f54c3f9e2b442a3e35472ac03287f5d1ab0bb4e02ba54"
SOURCE_COMPLETED_AT = "2026-10-12T06:27:48.340729Z"
OUTPUT = Path("artifacts/short_interest/sharadar_native_binding/native-index-source-20261012T055800Z")
MAXIMUM_NATIVE_INDEX_BYTES = 128 * 1024 * 1024
MAXIMUM_OBSERVATION_BYTES = 128 * 1024 * 1024
_CODE_FILES = (
    "research/short_interest_etf/sharadar_securities_master.py",
    "research/short_interest_etf/sharadar_master_segments.py",
    "research/short_interest_etf/sharadar_native_master_index.py",
    "research/short_interest_etf/sharadar_native_observations.py",
    "research/short_interest_etf/sharadar_companion_qualification.py",
    "scripts/qualify_short_interest_action_supplement.py",
    "scripts/finalize_short_interest_master_offline.py",
    "scripts/build_short_interest_native_master_offline.py",
)


class NativeMasterOfflineRefusal(CaptureRefusal):
    """Fixed codes never expose captured rows or data-fitness conclusions."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise NativeMasterOfflineRefusal(reason)


def build_protocol() -> dict:
    """The committed runtime pins one capture, reconstruction and destination."""
    return {
        "schema": "si-native-master-offline-protocol-v1",
        "source_capture_path": str(finalizer.SOURCE),
        "source_capture_inventory_sha256": finalizer.SOURCE_INVENTORY_SHA256,
        "source_capture_budget_sha256": finalizer.BUDGET_SHA256,
        "source_capture_head": finalizer.SOURCE_HEAD,
        "source_finalizer_head": SOURCE_FINALIZER_HEAD,
        "source_index_sha256": SOURCE_INDEX_SHA256,
        "source_completed_at": SOURCE_COMPLETED_AT,
        "master_protocol_sha256": master.PROTOCOL_SHA256,
        "segments_protocol_sha256": segments.PROTOCOL_SHA256,
        "native_protocol_sha256": native.PROTOCOL_SHA256,
        "observation_protocol_sha256": observations.PROTOCOL_SHA256,
        "companion_source_path": str(companion_reader.SHARADAR_SOURCE),
        "companion_source_head": companion_reader.SHARADAR_CODE_HEAD,
        "companion_report_file_sha256": companion_reader.SHARADAR_REPORT_FILE_SHA256,
        "companion_start_file_sha256": companion_reader.SHARADAR_START_FILE_SHA256,
        "output": str(OUTPUT), "maximum_native_index_bytes": MAXIMUM_NATIVE_INDEX_BYTES,
        "maximum_observation_bytes": MAXIMUM_OBSERVATION_BYTES,
        "part_rule": "one_protected_part_at_a_time_ordered_lengths_hashes_aggregate_digest",
        "reconstruction_rule": "captured_archives_and_observed_refusal_anchor_not_original_report_clock",
        "native_key_rule": "source_rewritten_dataset_key_not_historical_raw_alias_or_denominator",
        "publication_scope": "private_only_not_data_usability_publication",
        "provider_requests": 0, "credential_reads": 0, "outcome_looks": 0, "qc_attempts": 0,
    }


def _code_identity(root: Path, head: str) -> str:
    return hash_payload({"git_commit": head, "files": [
        {"path": name, "sha256": hash_bytes((root / name).read_bytes())} for name in _CODE_FILES]})


def _source_index(root: Path, anchor: str) -> tuple[segments.MasterReportIndex, str]:
    """Verify the old reconstruction without concatenating its private report."""
    _require_capture_platform()
    directory = root / finalizer.SOURCE / finalizer.OUTPUT_NAME
    raw = _protected_bytes(directory / "index.private.json", segments.MAXIMUM_INDEX_BYTES)
    index = segments.MasterReportIndex.from_bytes(raw)
    payload = index.to_payload()
    _require(payload["index_sha256"] == SOURCE_INDEX_SHA256, "source_private_index_identity")
    names = {"started.json", "completed.json", "index.private.json"} | {
        f"part-{part.position + 1:03d}.private" for part in index.parts}
    _require({item.name for item in directory.iterdir()} == names, "source_offline_inventory")
    start = _parse_receipt(_protected_bytes(directory / "started.json", 65536))
    end = _parse_receipt(_protected_bytes(directory / "completed.json", 65536))
    expected_start = {
        "schema": "si-master-offline-finalization-start-v1", "code_head": SOURCE_FINALIZER_HEAD,
        "source_code_head": finalizer.SOURCE_HEAD,
        "source_inventory_sha256": finalizer.SOURCE_INVENTORY_SHA256,
        "source_reconstruction_anchor": anchor, "started_at": start.get("started_at"),
        "provider_requests": 0, "credential_reads": 0, "qc_attempts": 0, "outcome_looks": 0,
    }
    expected_end = {
        "schema": "si-master-offline-finalization-complete-v1", "status": "offline_finalization_complete",
        "code_head": SOURCE_FINALIZER_HEAD, "source_code_head": finalizer.SOURCE_HEAD,
        "private_index_sha256": SOURCE_INDEX_SHA256, "completed_at": SOURCE_COMPLETED_AT,
        "provider_requests": 0, "credential_reads": 0, "qc_attempts": 0, "outcome_looks": 0,
        "backtest_result_exists": False,
    }
    # JSON equality must not admit bools as integer counters or 0 as False.
    _require(canonical_json(start) == canonical_json(expected_start), "source_offline_start_binding")
    _require(canonical_json(end) == canonical_json(expected_end), "source_offline_completion_binding")
    _require(_clock(anchor) <= _clock(start["started_at"]) <= _clock(end["completed_at"]),
             "source_offline_chronology")
    expected_provenance = segments.MasterReportProvenance(
        source_capture_receipt_sha256=finalizer.SOURCE_INVENTORY_SHA256,
        source_code_identity_sha256=hash_payload({"git_commit": finalizer.SOURCE_HEAD,
                                                 "protocol_sha256": master.PROTOCOL_SHA256}),
        finalizer_code_identity_sha256=finalizer._code_identity(root, SOURCE_FINALIZER_HEAD),
        reconstruction_anchor_utc=anchor,
    )
    _require(canonical_json(index.provenance.to_payload()) == canonical_json(expected_provenance.to_payload()),
             "source_offline_provenance")
    aggregate, length = hashlib.sha256(), 0
    for part in index.parts:
        raw_part = _protected_bytes(directory / f"part-{part.position + 1:03d}.private",
                                    segments.MAXIMUM_PART_BYTES)
        _require(len(raw_part) == part.byte_length and hash_bytes(raw_part) == part.bytes_sha256,
                 "source_part_identity")
        aggregate.update(raw_part)
        length += len(raw_part)
        del raw_part
    _require(length == index.report_byte_length and aggregate.hexdigest() == index.report_bytes_sha256,
             "source_report_bytes_identity")
    return index, hash_bytes(raw)


def _archives(captures: tuple) -> list[dict]:
    _require(type(captures) is tuple and all(type(item) is master.CapturedSharadarMasterArchive for item in captures)
             and tuple(item.table for item in captures) == master.TABLES,
             "source_archive_inventory")
    return [{"table": item.table, "request_sha256": item.request_sha256,
             "archive_sha256": hash_bytes(item.raw)} for item in captures]


def _native_bytes(captures: tuple, anchor: str, source_index: segments.MasterReportIndex) -> tuple[bytes, native.SharadarNativeMasterIndex]:
    qualification = master.qualify_sharadar_securities_master(captures, retrieved_at=anchor)
    index = native.build_sharadar_native_master_index(qualification)
    # The native constructor validates the master once. Do not reparse a full
    # report per security or materialize old segmented report bytes here.
    payload = index.to_payload()
    pins = _archives(captures)
    _require(payload["source_report_sha256"] == source_index.report_payload_sha256
             and payload["source_capture_identity_sha256"] == source_index.capture_identity_sha256
             and payload["source_capture_identity_sha256"] == hash_payload(pins)
             and payload["source_retrieved_at"] == anchor
             and payload["master_archive_sha256"] == pins[0]["archive_sha256"],
             "native_reconstruction_binding")
    encoded = canonical_json(payload).encode("utf-8")
    _require(len(encoded) <= MAXIMUM_NATIVE_INDEX_BYTES, "native_private_index_size_limit")
    _require(payload["index_sha256"] == index.sha256, "native_private_index_seal")
    return encoded, index


def _observation_bytes(source, index: native.SharadarNativeMasterIndex) -> tuple[bytes, dict]:
    """Retain the old exact rationals; this is not a full-study input bundle."""
    bound = observations.bind_sharadar_native_observations(source, index)
    _require(type(bound) is observations.SharadarNativeObservations, "native_observation_type")
    payload = observations.SharadarNativeObservations.to_payload(bound)
    _require(payload["native_index_sha256"] == index.sha256
             and payload["protocol_sha256"] == observations.PROTOCOL_SHA256
             and payload["source_protocol_sha256"] == observations.COMPANION_PROTOCOL_SHA256
             and payload["source_report_sha256"] == bound._source_sha256
             and payload["source_capture_identity_sha256"] == source._capture_identity,
             "native_observation_source_binding")
    _require(all(row["native_resolution"] is None
                 or row["native_resolution"]["index_sha256"] == index.sha256
                 for row in payload["observations"]), "native_observation_resolution_binding")
    _require(payload["binding_sha256"] == hash_payload({key: value for key, value in payload.items()
                                                        if key != "binding_sha256"}),
             "native_observation_seal")
    encoded = canonical_json(payload).encode("utf-8")
    _require(len(encoded) <= MAXIMUM_OBSERVATION_BYTES, "native_private_observation_size_limit")
    return encoded, {key: payload[key] for key in (
        "binding_sha256", "protocol_sha256", "source_report_sha256", "source_capture_identity_sha256",
        "source_protocol_sha256", "source_retrieved_at", "native_index_sha256")}


def _build(root: Path, *, head: str, remote: str) -> dict:
    _require_capture_platform()
    _guard(root, head, remote)
    protocol = build_protocol()
    captures, anchor = finalizer._reload(root)
    index, index_bytes_sha256 = _source_index(root, anchor)
    pins = _archives(captures)
    companion = companion_reader._rebuild_sharadar(root)
    started = _utc_now()
    _require(_clock(started) >= _clock(SOURCE_COMPLETED_AT), "native_start_chronology")
    _require(_git(root, "check-ignore", str(OUTPUT)) == str(OUTPUT), "native_output_not_ignored")
    _guard(root, head, remote)
    directory = _prepare_capture_directory(root / OUTPUT)
    # Exclusive mkdir is the only authority to write a refusal in this output.
    # Early failures and reruns cannot mutate the source or a previous result.
    try:
        code_identity = _code_identity(root, head)
        bindings = {
            "code_head": head, "remote_head": remote, "code_identity_sha256": code_identity,
            "protocol_sha256": hash_payload(protocol), "source_finalizer_head": SOURCE_FINALIZER_HEAD,
            "source_capture_inventory_sha256": finalizer.SOURCE_INVENTORY_SHA256,
            "source_capture_budget_sha256": finalizer.BUDGET_SHA256,
            "source_index_sha256": SOURCE_INDEX_SHA256, "source_index_bytes_sha256": index_bytes_sha256,
            "source_report_payload_sha256": index.report_payload_sha256,
            "source_capture_identity_sha256": index.capture_identity_sha256,
            "source_archive_pins": pins, "source_reconstruction_anchor": anchor,
            "source_completed_at": SOURCE_COMPLETED_AT,
            "companion_source_head": companion_reader.SHARADAR_CODE_HEAD,
            "companion_report_file_sha256": companion_reader.SHARADAR_REPORT_FILE_SHA256,
            "companion_start_file_sha256": companion_reader.SHARADAR_START_FILE_SHA256,
            "native_observation_protocol_sha256": observations.PROTOCOL_SHA256,
            "provider_requests": 0, "credential_reads": 0, "outcome_looks": 0, "qc_attempts": 0,
            "backtest_result_exists": False,
        }
        _guard(root, head, remote)
        _publish_json(directory, "started.json", {"schema": "si-native-master-offline-start-v1",
                                                "started_at": started, **bindings})
        encoded, native_index = _native_bytes(captures, anchor, index)
        observation_bytes, observation_pins = _observation_bytes(companion, native_index)
        _guard(root, head, remote)
        _publish(directory, "native.index.private.json", encoded)
        _guard(root, head, remote)
        _publish(directory, "observations.private.json", observation_bytes)
        completed = _utc_now()
        _require(_clock(completed) >= _clock(started), "native_completion_chronology")
        result = {"schema": "si-native-master-offline-complete-v1", "status": "native_master_offline_complete",
                  "started_at": started, "completed_at": completed, **bindings,
                  "native_index_sha256": native_index.sha256, "native_index_bytes_sha256": hash_bytes(encoded),
                  "native_observation_binding_sha256": observation_pins["binding_sha256"],
                  "native_observation_bytes_sha256": hash_bytes(observation_bytes),
                  "native_observation_source_pins": observation_pins}
        _guard(root, head, remote)
        _publish_json(directory, "completed.json", result)
        # Public diagnostics deliberately exclude provider keys, rows, counts,
        # classifications, source quality conclusions and private archive pins.
        return {key: result[key] for key in (
            "status", "code_head", "code_identity_sha256", "protocol_sha256", "started_at", "completed_at",
            "native_index_sha256", "native_index_bytes_sha256", "provider_requests", "credential_reads",
            "native_observation_binding_sha256", "native_observation_bytes_sha256",
            "outcome_looks", "qc_attempts", "backtest_result_exists")}
    except (CaptureRefusal, ValueError, TypeError, OSError, KeyError, UnicodeError):
        _publish_json(directory, "refused.json", {
            "status": "native_master_offline_refused", "refused_at": _utc_now(),
            "provider_requests": 0, "credential_reads": 0, "outcome_looks": 0, "qc_attempts": 0,
            "backtest_result_exists": False})
        raise NativeMasterOfflineRefusal("native_owned_output_refused") from None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-remote", required=True)
    args = parser.parse_args(argv)
    try:
        _require_capture_platform()
        result = _build(Path.cwd().resolve(), head=args.expected_head, remote=args.expected_remote)
    except (CaptureRefusal, ValueError, TypeError, OSError, KeyError, UnicodeError) as exc:
        result = {"status": "native_master_offline_refused", "provider_requests": 0,
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
