"""One retained affected-quarter IB-1B preparation and IB-1C v2 assessment.

This is not the 82-quarter publication route, frozen IB-1C ingestion, or a
complete-parent acquisition route. Only the first retained quarter is read;
its nonzero mismatch proves it is the earliest affected retained quarter.
The public CLI delegates to a source-only, process-tree isolated launcher.
Private worker helpers require the launcher's fresh, write-confined namespace.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import io
from pathlib import Path
import re
import zipfile

from data.hashing import hash_bytes, hash_payload
from research.insider_buying.ib1b_82q_offline_runner import _quarter_headers
from research.insider_buying.sec_bulk_snapshot import (
    SecBulkSource, load_sec_bulk_snapshot, write_sec_bulk_snapshot,
)
from research.insider_buying.sec_bulk_parsed_snapshot import (
    build_sec_bulk_parsed_snapshot, load_sec_bulk_parsed_snapshot,
)
from research.insider_buying.sec_edgar_acceptance_snapshot import (
    _upstream_submission_filing_date,
)
from research.insider_buying.sec_ib1b_82q_schema_profile import (
    RETAINED_82Q_SCHEMA_PROFILE_SHA256,
    build_retained_82q_schema_profile_candidate,
    verify_retained_82q_schema_profile,
)
from research.insider_buying.sec_ib1c_identity_v2 import (
    _authority, assess_ib1c_v2_quarter_identity,
)
from research.insider_buying.sec_zip_corpus_census import (
    RETAINED_ZIP_MANIFEST_SHA256, RETAINED_ZIP_MANIFEST_SIZE_BYTES,
    _CAPTURE_COMMIT, _MANIFEST_NAME, _PinnedZipRoot, _plain_root,
    _manifest_bindings, _census_quarter,
)
from research.insider_buying_ib1b_82q_snapshot_runner import (
    _envelope_bytes, _parse_envelope, _publish_envelope, _quarter_payload,
    _read_anchored, _validate_roots,
)


VERSION = "INSETF-IB1C-RETAINED-AFFECTED-QUARTER-v2"
PERIOD = "2006Q1"
FILENAME = "2006q1_form345.zip"
EXPECTED_MANIFEST_SHA256 = RETAINED_ZIP_MANIFEST_SHA256
EXPECTED_MANIFEST_SIZE_BYTES = RETAINED_ZIP_MANIFEST_SIZE_BYTES
EXPECTED_ZIP_SHA256 = "62becdadbe5eaff68f03edefe2ba2357c8bb498a1f825b697003e087cf98e6ce"
EXPECTED_ZIP_SIZE_BYTES = 17_306_804
EXPECTED_HEADER_RECEIPT_SHA256 = "32e35230f653736fa702c6e8e98ba5254e0f247169c212ea8a85e832174463cf"
MAX_ASSESSMENT_BYTES = 128 * 1024 * 1024
MAX_COMPLETION_BYTES = 16 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_CIK = re.compile(r"[0-9]{1,10}\Z")


class AffectedQuarterError(ValueError):
    """A bounded supplied input or replay failed closed."""


def _refuse(reason: str) -> None:
    raise AffectedQuarterError("REFUSED: " + reason)


def _context(parser_commit: str, source_inventory_sha256: str) -> None:
    if (type(parser_commit) is not str or _COMMIT.fullmatch(parser_commit) is None
            or type(source_inventory_sha256) is not str
            or _SHA.fullmatch(source_inventory_sha256) is None):
        _refuse("parser commit or captured source inventory identity is malformed")


def _prepare_inputs(input_root: Path):
    """Recheck the exact manifest and only its first, already-retained ZIP."""
    root = _plain_root(input_root)
    with _PinnedZipRoot(root) as pinned:
        manifest = pinned.read(_MANIFEST_NAME, max_bytes=128 * 1024)
        if (hash_bytes(manifest) != EXPECTED_MANIFEST_SHA256
                or len(manifest) != EXPECTED_MANIFEST_SIZE_BYTES):
            _refuse("retained intake manifest bytes changed")
        binding = _manifest_bindings(manifest)[0]
        if (binding.period != PERIOD or binding.filename != FILENAME
                or binding.sha256 != EXPECTED_ZIP_SHA256
                or binding.size_bytes != EXPECTED_ZIP_SIZE_BYTES):
            _refuse("first retained quarter differs from the fixed affected selection")
        raw = pinned.read(FILENAME, max_bytes=EXPECTED_ZIP_SIZE_BYTES)
    if hash_bytes(raw) != EXPECTED_ZIP_SHA256 or len(raw) != EXPECTED_ZIP_SIZE_BYTES:
        _refuse("selected retained ZIP bytes changed")
    quarter = _census_quarter(raw, binding)
    profile = build_retained_82q_schema_profile_candidate()
    verify_retained_82q_schema_profile(profile)
    headers = _quarter_headers(raw, PERIOD, profile)
    if hash_payload(headers.to_payload()) != EXPECTED_HEADER_RECEIPT_SHA256:
        _refuse("selected eight-table header receipt changed")
    # The census already checks strict headers, row width, field/row caps,
    # accession uniqueness and the all-six-form inventory. Check source dates
    # and CIKs before any output; the unchanged v2 assessor repeats these checks.
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        with archive.open("SUBMISSION.tsv") as member:
            reader = csv.DictReader(io.TextIOWrapper(member, encoding="utf-8-sig", newline=""),
                                    delimiter="\t", strict=True)
            mismatches = 0
            dialect = None
            count = 0
            for row in reader:
                filed, current = _upstream_submission_filing_date(row["FILING_DATE"])
                if dialect is not None and dialect != current:
                    _refuse("selected quarter mixes filing-date dialects")
                dialect = current
                if (filed.year, (filed.month - 1) // 3 + 1) != (2006, 1):
                    _refuse("selected filing date is outside 2006Q1")
                cik = row["ISSUERCIK"]
                if _CIK.fullmatch(cik) is None or int(cik) == 0:
                    _refuse("selected issuer CIK is invalid")
                mismatches += int(row["ACCESSION_NUMBER"][11:13]) != filed.year % 100
                count += 1
    if count != quarter.submission_accessions or mismatches == 0:
        _refuse("first retained quarter is not an accounting-bound affected quarter")
    return raw, binding, quarter, profile, headers, mismatches


def _derive(quarter, raw_identity, parsed_loaded, headers, mismatches,
            parser_commit: str, source_inventory_sha256: str):
    metadata = _quarter_payload(quarter, raw_identity, parsed_loaded.identity,
                               parsed_loaded, parser_commit, parser_commit_verified=False)
    # Old helper's 82q label is not this runner's scope. Its complete checks are
    # reused, but no aggregate/82-quarter completion or frozen promotion is made.
    metadata["kind"] = "sec-insider-noncanonical-single-affected-quarter-ib1b-v2"
    assessment = assess_ib1c_v2_quarter_identity(parsed_loaded, quarter, ())
    payload = assessment.to_payload()
    if (hash_payload(payload["authority"]) != hash_payload(_authority())
            or any(type(payload[name]) is not int for name in (
                "submission_count", "accession_year_mismatch_count",
                "corroborated_count", "quarantined_count", "short_cik_count"))
            or type(payload["rows"]) is not list
            or len(payload["rows"]) != quarter.submission_accessions
            or payload["accounting_sha256"] != hash_payload(payload["rows"])
            or payload["submission_count"] != quarter.submission_accessions
            or payload["accession_year_mismatch_count"] != mismatches
            or payload["corroborated_count"] != 0
            or payload["quarantined_count"] != quarter.submission_accessions
            or payload["whole_quarter_identity_sha256"] is not None):
        _refuse("empty supplied-parent policy did not retain every row in quarantine")
    assessment_raw = _envelope_bytes(payload, max_bytes=MAX_ASSESSMENT_BYTES)
    receipt = {
        "kind": VERSION, "period": PERIOD,
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "zip_sha256": EXPECTED_ZIP_SHA256,
        "schema_profile_sha256": RETAINED_82Q_SCHEMA_PROFILE_SHA256,
        "header_receipt_sha256": hash_payload(headers.to_payload()),
        "census_quarter_sha256": hash_payload(quarter.to_payload()),
        "source_inventory_sha256": source_inventory_sha256,
        "parser_commit": parser_commit,
        "raw_snapshot_id": raw_identity.snapshot_id,
        "parsed_snapshot_id": parsed_loaded.identity.snapshot_id,
        "assessment_sha256": assessment.sha256,
        "assessment_envelope_sha256": hash_bytes(assessment_raw),
        "assessment_envelope_bytes": len(assessment_raw),
        "submission_count": payload["submission_count"],
        "corroborated_count": payload["corroborated_count"],
        "quarantined_count": payload["quarantined_count"],
        "accession_year_mismatch_count": mismatches,
        "short_cik_count": payload["short_cik_count"],
        "whole_quarter_identity_sha256": None,
        "supplied_parent_count": 0, "quarters_assessed": 1,
        **_authority(),
    }
    completion = {
        "receipt": receipt, "quarter_snapshot": metadata,
        "selection_basis": "first_chronological_retained_quarter_with_measured_nonzero_mismatch",
        "selection_scanned_quarters": 1,
        "parent_policy": "empty_supplied_parent_tuple; all_rows_retained_quarantined",
        "all_six_form_policy": "retain_all; unsupported_3_5_corroboration_stays_quarantined",
        "profile_status": "retained_header_only_candidate; no_82_quarter_promotion",
    }
    _envelope_bytes(completion, max_bytes=MAX_COMPLETION_BYTES)
    return receipt, completion, payload, assessment_raw


def _verify_quarter(input_root: Path, output_root: Path, parser_commit: str,
                    source_inventory_sha256: str) -> dict[str, object]:
    """Read-only raw-bound reparse and complete assessment regeneration."""
    _context(parser_commit, source_inventory_sha256)
    _validate_roots(input_root, output_root)
    _, _, quarter, _, headers, mismatches = _prepare_inputs(input_root)
    raw = _read_anchored(output_root, "completion.json", max_bytes=MAX_COMPLETION_BYTES)
    completion = _parse_envelope(raw)
    if type(completion.get("receipt")) is not dict:
        _refuse("completion receipt is malformed")
    received = completion["receipt"]
    raw_id, parsed_id = received.get("raw_snapshot_id"), received.get("parsed_snapshot_id")
    if (type(raw_id) is not str
            or re.fullmatch(r"sec-insider-bulk-2006q1-[0-9a-f]{16}", raw_id) is None
            or type(parsed_id) is not str
            or re.fullmatch(r"sec-insider-parsed-2006q1-[0-9a-f]{16}", parsed_id) is None):
        _refuse("completion snapshot identifiers are malformed")
    if set(item.name for item in output_root.iterdir()) != {"ib1a", "ib1b", "assessment.json", "completion.json"}:
        _refuse("completion root contains unknown or incomplete artifacts")
    for subdir, identity in (("ib1a", raw_id), ("ib1b", parsed_id)):
        lock_name = f".{identity}.publication.lock"
        if set(item.name for item in (output_root / subdir).iterdir()) != {identity, lock_name}:
            _refuse("snapshot namespace contains an unrelated publication")
        if _read_anchored(output_root / subdir, lock_name, max_bytes=1) != b"\0":
            _refuse("snapshot publication lock shape differs")
    raw_directory = output_root / "ib1a" / raw_id
    raw_loaded = load_sec_bulk_snapshot(raw_directory)
    parsed = load_sec_bulk_parsed_snapshot(output_root / "ib1b" / parsed_id,
                                          raw_snapshot_directory=raw_directory)
    receipt, expected, _, assessment_raw = _derive(quarter, raw_loaded.identity, parsed,
                                                 headers, mismatches, parser_commit,
                                                 source_inventory_sha256)
    if raw != _envelope_bytes(expected, max_bytes=MAX_COMPLETION_BYTES):
        _refuse("completion differs from the independently rederived accounting")
    if _read_anchored(output_root, "assessment.json", max_bytes=MAX_ASSESSMENT_BYTES) != assessment_raw:
        _refuse("assessment bytes differ from the raw-bound regenerated rows")
    return receipt


def _run_quarter(input_root: Path, output_root: Path, parser_commit: str,
                 source_inventory_sha256: str) -> dict[str, object]:
    """Private isolated worker; fresh namespace only, completion published last."""
    _context(parser_commit, source_inventory_sha256)
    _validate_roots(input_root, output_root)
    if not output_root.is_dir() or any(output_root.iterdir()):
        _refuse("one-quarter output must be a fresh empty private namespace")
    raw, binding, quarter, profile, headers, mismatches = _prepare_inputs(input_root)
    source = SecBulkSource(year=2006, quarter=1, source_url=binding.source_url,
                           git_commit=_CAPTURE_COMMIT,
                           retrieved_at=datetime.fromisoformat(binding.local_last_write_utc[:-1] + "+00:00"))
    identity = write_sec_bulk_snapshot(raw, source, output_root / "ib1a")
    raw_directory = output_root / "ib1a" / identity.snapshot_id
    raw_loaded = load_sec_bulk_snapshot(raw_directory)
    parsed_identity = build_sec_bulk_parsed_snapshot(raw_directory, output_root / "ib1b",
                                                    schema_profile=profile,
                                                    parser_git_commit=parser_commit)
    parsed = load_sec_bulk_parsed_snapshot(output_root / "ib1b" / parsed_identity.snapshot_id,
                                          raw_snapshot_directory=raw_directory)
    receipt, completion, assessment, _ = _derive(quarter, raw_loaded.identity, parsed,
                                                headers, mismatches, parser_commit,
                                                source_inventory_sha256)
    _publish_envelope(output_root, "assessment.json", assessment, max_bytes=MAX_ASSESSMENT_BYTES)
    _publish_envelope(output_root, "completion.json", completion, max_bytes=MAX_COMPLETION_BYTES)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args()
    # No caller can select a different quarter/profile or unisolated CLI path.
    from research.insider_buying_affected_quarter_isolation import run_isolated
    from data.hashing import canonical_json
    print(canonical_json(run_isolated(args.input_root, args.output_root, args.expected_commit)))


if __name__ == "__main__":
    main()
