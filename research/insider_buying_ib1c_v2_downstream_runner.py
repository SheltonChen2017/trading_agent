"""Read-only downstream accounting for the one retained 2006Q1 v2 preparation.

The original producer identities stay fixed. A new consumer verifies the raw
archive, publicly reloads/reparses its parsed snapshot, and rederives every
assessment/completion byte before constructing source-only pilot and scope
views. No publisher, recovery, source access, or financial admission is used.
The public CLI always delegates to a process-tree network/write-denied worker.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

from data.hashing import canonical_json, hash_bytes, hash_payload
from research import insider_buying_ib1c_v2_affected_quarter_runner as preparation
from research.insider_buying.sec_bulk_snapshot import load_sec_bulk_snapshot
from research.insider_buying.sec_bulk_parsed_snapshot import load_sec_bulk_parsed_snapshot
from research.insider_buying.sec_ib1c_identity_v2 import _authority, assess_ib1c_v2_quarter_identity
from research.insider_buying.sec_ib1c_v2_downstream import (
    EXPECTED_PERIODS, V2PreparationBinding, V2QuarterCoverage,
    build_v2_quarter_coverage, compose_v2_scope_coverage,
)
from research.insider_buying_ib1b_82q_snapshot_runner import (
    _envelope_bytes, _parse_envelope, _read_anchored, _validate_roots,
)


VERSION = "INSETF-IB1C-V2-RETAINED-DOWNSTREAM-READBACK-v1"
PRODUCER_COMMIT = "b0efb31262d0eca6c972673ca36403fee20a34cb"
PRODUCER_SOURCE_INVENTORY_SHA256 = "7b34fdfe67d408d4435ff610d9fc672bc181f7b257c6a487b64df546053fe3e0"
EXPECTED_COMPLETION_SHA256 = "d05e0345124b96599fbbd82a81828452ea63d39a90b3be28b599ef1e462bbfd0"
EXPECTED_ASSESSMENT_SHA256 = "402fa1860bd9549f6d0eadcf7dc9a956cc0dc006d91f038290c294c102083ad5"
EXPECTED_ASSESSMENT_BYTES = 63_409_968
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class Ib1cV2DownstreamLoadError(ValueError):
    """The fixed retained artifact cannot be independently replayed."""


def _refuse(reason: str) -> None:
    raise Ib1cV2DownstreamLoadError("REFUSED: " + reason)


def _pins() -> None:
    if (type(PRODUCER_COMMIT) is not str or _COMMIT.fullmatch(PRODUCER_COMMIT) is None
            or any(type(value) is not str or _SHA.fullmatch(value) is None for value in (
                PRODUCER_SOURCE_INVENTORY_SHA256, EXPECTED_COMPLETION_SHA256,
                EXPECTED_ASSESSMENT_SHA256))
            or type(EXPECTED_ASSESSMENT_BYTES) is not int
            or not 0 < EXPECTED_ASSESSMENT_BYTES <= preparation.MAX_ASSESSMENT_BYTES):
        _refuse("fixed producer or artifact pins are malformed")


def load_retained_2006_coverage(input_root: Path, preparation_root: Path) -> V2QuarterCoverage:
    """Private isolated-worker entry; never repair or write supplied artifacts."""
    try:
        _pins()
        _validate_roots(input_root, preparation_root)
        _, _, quarter, _, headers, mismatches = preparation._prepare_inputs(input_root)
        completion_raw = _read_anchored(preparation_root, "completion.json",
                                        max_bytes=preparation.MAX_COMPLETION_BYTES)
        if hash_bytes(completion_raw) != EXPECTED_COMPLETION_SHA256:
            _refuse("observed producer completion bytes differ")
        completion = _parse_envelope(completion_raw)
        received = completion.get("receipt")
        if type(received) is not dict:
            _refuse("producer completion receipt is malformed")
        raw_id, parsed_id = received.get("raw_snapshot_id"), received.get("parsed_snapshot_id")
        if (type(raw_id) is not str
                or re.fullmatch(r"sec-insider-bulk-2006q1-[0-9a-f]{16}", raw_id) is None
                or type(parsed_id) is not str
                or re.fullmatch(r"sec-insider-parsed-2006q1-[0-9a-f]{16}", parsed_id) is None):
            _refuse("producer snapshot identifiers are malformed")
        if {item.name for item in preparation_root.iterdir()} != {
                "ib1a", "ib1b", "assessment.json", "completion.json"}:
            _refuse("preparation root contains unknown or incomplete artifacts")
        for subdir, identity in (("ib1a", raw_id), ("ib1b", parsed_id)):
            namespace = preparation_root / subdir
            lock = f".{identity}.publication.lock"
            if {item.name for item in namespace.iterdir()} != {identity, lock}:
                _refuse("snapshot namespace contains another or incomplete publication")
            if _read_anchored(namespace, lock, max_bytes=1) != b"\0":
                _refuse("retained publication lock differs")
        raw_directory = preparation_root / "ib1a" / raw_id
        raw_loaded = load_sec_bulk_snapshot(raw_directory)
        parsed = load_sec_bulk_parsed_snapshot(preparation_root / "ib1b" / parsed_id,
                                              raw_snapshot_directory=raw_directory)
        receipt, expected, _, expected_assessment = preparation._derive(
            quarter, raw_loaded.identity, parsed, headers, mismatches,
            PRODUCER_COMMIT, PRODUCER_SOURCE_INVENTORY_SHA256)
        if completion_raw != _envelope_bytes(expected, max_bytes=preparation.MAX_COMPLETION_BYTES):
            _refuse("completion differs from the original producer's raw-bound accounting")
        assessment_raw = _read_anchored(preparation_root, "assessment.json",
                                       max_bytes=preparation.MAX_ASSESSMENT_BYTES)
        if (len(assessment_raw) != EXPECTED_ASSESSMENT_BYTES
                or hash_bytes(assessment_raw) != EXPECTED_ASSESSMENT_SHA256
                or assessment_raw != expected_assessment):
            _refuse("assessment differs from the original raw-bound all-row accounting")
        assessment = assess_ib1c_v2_quarter_identity(parsed, quarter, ())
        binding = V2PreparationBinding(
            period=preparation.PERIOD, producer_commit=PRODUCER_COMMIT,
            producer_source_inventory_sha256=PRODUCER_SOURCE_INVENTORY_SHA256,
            completion_envelope_sha256=hash_bytes(completion_raw),
            assessment_envelope_sha256=hash_bytes(assessment_raw),
            assessment_envelope_bytes=len(assessment_raw),
            raw_snapshot_id=raw_loaded.identity.snapshot_id,
            raw_lineage_sha256=raw_loaded.identity.lineage_hash,
            parsed_snapshot_id=parsed.identity.snapshot_id,
            parsed_lineage_sha256=parsed.identity.lineage_hash,
            profile_sha256=receipt["schema_profile_sha256"],
            census_quarter_sha256=receipt["census_quarter_sha256"],
        )
        return build_v2_quarter_coverage(assessment, binding)
    except Ib1cV2DownstreamLoadError:
        raise
    except (OSError, AttributeError, TypeError, ValueError, KeyError, IndexError,
            RecursionError) as exc:
        raise Ib1cV2DownstreamLoadError("REFUSED: retained downstream replay failed validation") from exc


def build_retained_2006_handoff(input_root: Path, preparation_root: Path) -> dict[str, object]:
    """Small replay receipt; the already-retained assessment holds the full ledger."""
    from research.insider_buying.backtest_evidence_pipeline import analyze_v2_coverage

    quarter = load_retained_2006_coverage(input_root, preparation_root)
    selected = compose_v2_scope_coverage((quarter,), (preparation.PERIOD,))
    partial = compose_v2_scope_coverage((quarter,), EXPECTED_PERIODS)
    rows = quarter.pilot_rows()
    return {
        "kind": VERSION, "quarter": quarter.to_payload(),
        "selected_scope": selected.to_payload(),
        "retained_82_partial_scope": partial.to_payload(),
        "backtest_pipeline": analyze_v2_coverage(quarter),
        "pilot": {
            "row_count": len(rows), "ledger_sha256": hash_payload(rows),
            "source_only_admitted_count": len(quarter.admitted_rows()),
            "quarantined_count": sum(row["disposition"] == "quarantined" for row in rows),
            "event_eligibility": "not_evaluated", "candidate_signal_count": None,
        },
        "artifact_validation": {
            "public_raw_bound_parsed_reload": True, "complete_assessment_rederived": True,
            "complete_completion_rederived": True, "producer_lineage_preserved": True,
            "source_only": True, "publisher_or_recovery_called": False,
        },
        "authority": _authority(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--preparation-root", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args()
    from research.insider_buying_affected_quarter_isolation import run_readonly_consumer
    print(canonical_json(run_readonly_consumer(args.input_root, args.preparation_root,
                                              args.expected_commit)))


if __name__ == "__main__":
    main()
