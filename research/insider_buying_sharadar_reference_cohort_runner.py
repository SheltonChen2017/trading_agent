"""Isolated, local integration of the exact recovered owner-supplied capture.

No account access/download, fundamentals decode, financial calculation, QC or
outcome API. Original capture lineage remains original; today's observer does
not create historical publication/PIT evidence. Outputs are private metadata.
The parent requires clean committed lane identity and launches its own worker
under process-tree network/fork denial and fresh-output-only write permission.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import zipfile
import zlib

from research import insider_buying_sharadar_reference_cohort as cohort
from research import insider_buying_earnings_archive_assessment_runner as custody
from research import insider_buying_supplied_sharadar_audit as supplied
from research.insider_buying_eodhd_earnings_demo import FALSE_FLAGS, EodhdDemoError, _read_leaf
from research.insider_buying_provider_metadata_audit import _exclusive_json


SCHEMA = "insider-sharadar-reference-cohort-observer-v2"
LANE_ROOT = custody.LANE_ROOT
LANE_BRANCH = custody.LANE_BRANCH
CAPTURE_ROOT = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2/artifacts/analyst_revisions_v2/sharadar_capture/arv2-sharadar-source-20260914T003329843989Z")
CAPTURE_MANIFEST_SHA256 = supplied.MANIFEST_SHA256
OUTPUT_PARTS = ("artifacts", "insider_buying", "sharadar_reference_cohort")
MAX_PROJECTION_BYTES = 256 * 1024 * 1024
MAX_REPORT_BYTES = cohort.MAX_REPORT_BYTES
MIN_FREE_BYTES = 4 * 1024**3
MAX_PUBLICATION_BYTES = 2 * MAX_PROJECTION_BYTES + MAX_REPORT_BYTES + 4 * 1024 * 1024
MAX_FIELD_BYTES = 128 * 1024
MAX_METADATA_ROWS = 2_000_000
COUNT_FIELDS = ("source_filings", "all_form_issuer_count", "relevant_issuer_count", "source_ticker_rows",
                "source_action_rows", "ticker_rows_accounted", "action_rows_accounted",
                "ticker_quarantined_rows", "action_quarantined_rows", "cohort_referenced_unique_action_rows",
                "unreferenced_action_rows", "cohort_action_relation_count")
SOURCE_SEEDS = ("research/insider_buying_sharadar_reference_cohort_runner.py",
                "research/insider_buying_sharadar_reference_cohort.py")


class SharadarCohortRunnerError(ValueError):
    """Fixed codes only; source rows/OS/credential text never interpolated."""


def _need(condition, code):
    if not condition:
        raise SharadarCohortRunnerError(code)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _audit_id(value):
    _need(type(value) is str and re.fullmatch(r"ib-sharadar-cohort-[a-z0-9-]{1,80}", value), "audit_id_refused")
    return value


def _identity(expected_head):
    # Both modules are imported before the original observer inventories its
    # static plus loaded internal closure; no global monkeypatch is involved.
    value = custody._identity(expected_head)
    _need(set(SOURCE_SEEDS) <= set(value["source_sha256"]), "observer_source_closure_incomplete")
    return value


class _HeldCapture:
    """Hold no-follow ancestry/leaves with shared locks for the whole read."""
    def __init__(self, path, *, private=True):
        self.chain = custody._Chain(path, ())
        self.handles = []
        self.private = private
        try:
            named = os.fstat(self.chain.fd)
            _need(not private or (named.st_uid == os.geteuid() and stat.S_IMODE(named.st_mode) == 0o700),
                  "capture_root_not_private_owner_custody")
            self.names = set(os.listdir(self.chain.fd))
            self.fd = self.chain.fd
        except BaseException:
            self.chain.close()
            raise

    def open(self, name, cap):
        self.check()
        _need(type(name) is str and "/" not in name and name not in {"", ".", ".."}, "capture_name_refused")
        named = os.stat(name, dir_fd=self.chain.fd, follow_symlinks=False)
        _need(stat.S_ISREG(named.st_mode) and named.st_nlink == 1 and named.st_uid == os.geteuid()
              and 0 < named.st_size <= cap and (not self.private or stat.S_IMODE(named.st_mode) == 0o600),
              "capture_leaf_not_private_single_link_regular")
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.chain.fd)
        try:
            _need(custody._version(named) == custody._version(os.fstat(fd)), "capture_leaf_substituted")
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            stream = os.fdopen(fd, "rb")
        except BaseException:
            os.close(fd)
            raise
        self.handles.append((name, stream, custody._version(named), cap))
        return stream

    def check(self):
        self.chain.recheck()
        _need(set(os.listdir(self.chain.fd)) == self.names, "capture_directory_inventory_changed")
        for name, stream, version, _ in self.handles:
            _need(custody._version(os.fstat(stream.fileno())) == version
                  and custody._version(os.stat(name, dir_fd=self.chain.fd, follow_symlinks=False)) == version,
                  "capture_leaf_changed")

    def close(self):
        for _, stream, _, _ in reversed(self.handles):
            stream.close()
        self.chain.close()


def _hash_stream(stream, cap):
    stream.seek(0)
    count, digest = 0, hashlib.sha256()
    while chunk := stream.read(1024 * 1024):
        count += len(chunk)
        _need(count <= cap, "archive_byte_limit")
        digest.update(chunk)
    stream.seek(0)
    return digest.hexdigest(), count


def _project_archive(stream, entry, *, dataset, columns, schema, manifest_sha):
    digest, size = _hash_stream(stream, supplied.MAX_ARCHIVE)
    _need(digest == entry.get("archive_sha256") and type(entry.get("archive_byte_count")) is int
          and size == entry["archive_byte_count"], "archive_anchor_mismatch")
    declared = entry.get("members")
    _need(type(declared) is list and len(declared) == 1 and type(declared[0]) is dict,
          "member_inventory_refused")
    expected = declared[0]
    try:
        with zipfile.ZipFile(stream) as archive:
            members = archive.infolist()
            _need(len(members) == 1, "member_inventory_refused")
            member = members[0]
            _need(member.filename == dataset + ".csv" == expected.get("name")
                  and not member.flag_bits & 1 and not stat.S_ISLNK(member.external_attr >> 16)
                  and member.compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                  and 0 < member.file_size <= supplied.MAX_MEMBER
                  and member.file_size == expected.get("uncompressed_byte_count")
                  and member.compress_size == expected.get("compressed_byte_count")
                  and member.CRC == expected.get("crc32"), "member_envelope_mismatch")
            with archive.open(member) as source:
                hashed = supplied._HashedRaw(source, member.file_size)
                with io.TextIOWrapper(io.BufferedReader(hashed), encoding="utf-8-sig", newline="") as text:
                    reader = csv.reader(text, strict=True)
                    header = next(reader)
                    _need(header == expected.get("columns") and len(header) == len(set(header))
                          and set(columns) <= set(header), "member_header_mismatch")
                    positions = {column: header.index(column) for column in columns}
                    rows = []
                    for ordinal, values in enumerate(reader, 1):
                        _need(ordinal <= MAX_METADATA_ROWS and len(values) == len(header)
                              and all(len(value.encode()) <= MAX_FIELD_BYTES and "\x00" not in value for value in values),
                              "member_row_shape_or_bound")
                        # Other CSV fields remain opaque strings. Only exact
                        # nonfinancial metadata columns are interpreted/exported.
                        rows.append({"source_row_ordinal": ordinal,
                                     **{column: values[position] for column, position in positions.items()}})
                    member_sha, member_bytes = hashed.digest.hexdigest(), hashed.count
            _need(member_sha == expected.get("content_sha256") and member_bytes == member.file_size
                  and type(entry.get("row_count")) is int and type(expected.get("row_count")) is int
                  and len(rows) == entry["row_count"] == expected["row_count"], "member_anchor_or_row_count_mismatch")
    except (zipfile.BadZipFile, csv.Error, UnicodeError, StopIteration, KeyError, zlib.error, EOFError):
        raise SharadarCohortRunnerError("metadata_archive_decode_refused") from None
    raw = _canonical({"schema": schema, "capture_manifest_sha256": manifest_sha,
                      "archive_sha256": digest, "member_sha256": member_sha, "columns": list(columns), "rows": rows})
    _need(len(raw) <= MAX_PROJECTION_BYTES, "projection_byte_limit")
    return raw


def _inputs(*, root, capture_path, manifest_sha, inventory_sha, census_complete_sha):
    capture = _HeldCapture(capture_path)
    census = None
    try:
        census = _HeldCapture(root.joinpath(*custody.CENSUS_PARTS))
        _need(capture.names == {"manifest.json", "manifest.sha256", *supplied.FILES}, "capture_exact_inventory_required")
        manifest_stream = capture.open("manifest.json", 1024 * 1024)
        manifest_raw = manifest_stream.read(1024 * 1024 + 1)
        _need(_sha(manifest_raw) == manifest_sha, "capture_manifest_anchor_mismatch")
        sidecar = capture.open("manifest.sha256", 65)
        _need(sidecar.read(66) == (manifest_sha + "\n").encode(), "capture_sidecar_anchor_mismatch")
        manifest = supplied._strict_json(manifest_raw)
        entries = manifest.get("archives")
        _need(manifest.get("schema") == "arv2-sharadar-source-capture-artifact-v2"
              and manifest.get("api_key_persisted") is False and manifest.get("redirect_url_persisted") is False
              and type(entries) is list and len(entries) == 3
              and all(type(entry) is dict for entry in entries)
              and tuple(entry.get("dataset") for entry in entries) == supplied.DATASETS
              and tuple(entry.get("archive_file") for entry in entries) == supplied.FILES, "capture_manifest_profile_refused")
        ticker_stream = capture.open(supplied.FILES[0], supplied.MAX_ARCHIVE)
        action_stream = capture.open(supplied.FILES[1], supplied.MAX_ARCHIVE)
        fundamental_stream = capture.open(supplied.FILES[2], supplied.MAX_ARCHIVE)
        fundamental_sha, fundamental_size = _hash_stream(fundamental_stream, supplied.MAX_ARCHIVE)
        _need(fundamental_sha == entries[2].get("archive_sha256")
              and fundamental_size == entries[2].get("archive_byte_count"), "opaque_fundamentals_archive_anchor_mismatch")
        ticker_raw = _project_archive(ticker_stream, entries[0], dataset="tickers", columns=cohort.TICKER_COLUMNS,
                                     schema=cohort.TICKERS_SCHEMA, manifest_sha=manifest_sha)
        action_raw = _project_archive(action_stream, entries[1], dataset="actions", columns=cohort.ACTION_COLUMNS,
                                     schema=cohort.ACTIONS_SCHEMA, manifest_sha=manifest_sha)
        _need(set(os.listdir(census.fd)) == {"inventory.json", "complete.json"}, "census_exact_inventory_required")
        inventory_stream = census.open("inventory.json", custody.assessment.MAX_INVENTORY_BYTES)
        inventory = inventory_stream.read(custody.assessment.MAX_INVENTORY_BYTES + 1)
        complete_stream = census.open("complete.json", 1024 * 1024)
        complete_raw = complete_stream.read(1024 * 1024 + 1)
        _need(_sha(inventory) == inventory_sha and _sha(complete_raw) == census_complete_sha, "census_anchor_mismatch")
        census_receipt = custody._json(complete_raw)
        _need(census_receipt.get("inventory_sha256") == inventory_sha
              and census_receipt.get("inventory_bytes") == len(inventory)
              and census_receipt.get("accounting") == custody._json(inventory).get("accounting"), "census_receipt_binding")
        capture.check(); census.check()
        return capture, census, manifest_raw, inventory, ticker_raw, action_raw
    except BaseException:
        capture.close()
        if census is not None:
            census.close()
        raise


def _publish(directory, name, raw, cap):
    _need(type(raw) is bytes and 0 < len(raw) <= cap, "publication_byte_limit")
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=directory)
    with os.fdopen(fd, "wb") as stream:
        _need(stream.write(raw) == len(raw), "publication_short_write")
        stream.flush(); os.fsync(stream.fileno())
    os.fsync(directory)
    _need(_read_leaf(directory, name, limit=cap) == raw, "publication_reattachment_refused")


def _disk_reserve(directory):
    """Retain every private row/relationship without enlarging output caps."""
    info = os.statvfs(directory)
    _need(type(info.f_bavail) is int and type(info.f_frsize) is int and info.f_bavail >= 0 and info.f_frsize > 0
          and info.f_bavail * info.f_frsize >= MIN_FREE_BYTES + MAX_PUBLICATION_BYTES,
          "offline_publication_disk_reserve_insufficient")


def _fixture_capture_is_actual(path):
    """Reject named, resolved and same-inode aliases before capture custody."""
    _need(isinstance(path, Path), "invented_scope_identity_refused")
    try:
        return path == CAPTURE_ROOT or path.resolve() == CAPTURE_ROOT or path.samefile(CAPTURE_ROOT)
    except OSError:
        raise SharadarCohortRunnerError("invented_scope_identity_refused") from None


def _worker(*, root, audit_id, identity, capture_path, manifest_sha, inventory_sha, census_complete_sha, fixture_only=False):
    _need(type(fixture_only) is bool, "invented_scope_cannot_read_actual_inputs")
    if fixture_only:
        try:
            actual_lane = custody._fixture_root_is_lane(root)
        except custody.ArchiveAssessmentRunnerError:
            raise SharadarCohortRunnerError("invented_scope_identity_refused") from None
        _need(not actual_lane and not _fixture_capture_is_actual(capture_path),
              "invented_scope_cannot_read_actual_inputs")
    _need(fixture_only or (root == LANE_ROOT and capture_path == CAPTURE_ROOT
          and manifest_sha == CAPTURE_MANIFEST_SHA256 and inventory_sha == custody.INVENTORY_SHA256
          and census_complete_sha == custody.CENSUS_COMPLETE_SHA256), "actual_scope_requires_fixed_inputs")
    custody._effective_denial(require_fork=not fixture_only)
    _need(custody._source_bytes(root, tuple(identity["source_sha256"])) == identity["source_sha256"],
          "worker_source_image_changed")
    output = custody._Chain(root, (*OUTPUT_PARTS, audit_id))
    capture = census = None
    try:
        _need(os.listdir(output.fd) == [], "output_cannot_resume_or_overwrite")
        _disk_reserve(output.fd)
        if not fixture_only:
            sibling = root.joinpath(*OUTPUT_PARTS, "isolation-" + audit_id + ".probe")
            try:
                fd = os.open(sibling, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            except OSError as exc:
                _need(exc.errno in {1, 13}, "outside_output_write_denial_not_observed")
            else:
                os.close(fd)
                raise SharadarCohortRunnerError("outside_output_write_denial_not_observed")
        capture, census, manifest_raw, inventory, tickers, actions = _inputs(root=root, capture_path=capture_path,
            manifest_sha=manifest_sha, inventory_sha=inventory_sha, census_complete_sha=census_complete_sha)
        result = cohort.assess_sharadar_cohort(inventory_raw=inventory, inventory_sha256=inventory_sha,
            capture_manifest_raw=manifest_raw, capture_manifest_sha256=manifest_sha,
            tickers_projection_raw=tickers, tickers_projection_sha256=_sha(tickers),
            actions_projection_raw=actions, actions_projection_sha256=_sha(actions))
        raw = result.canonical_bytes()
        capture.check(); census.check()
        _need(_sha(_read_leaf(census.fd, "inventory.json", limit=custody.assessment.MAX_INVENTORY_BYTES)) == inventory_sha
              and _sha(_read_leaf(census.fd, "complete.json", limit=1024 * 1024)) == census_complete_sha,
              "census_changed_during_assessment")
        for name, stream, _, cap in capture.handles:
            expected = (manifest_sha if name == "manifest.json" else _sha((manifest_sha + "\n").encode())
                if name == "manifest.sha256" else next(entry["archive_sha256"]
                for entry in supplied._strict_json(manifest_raw)["archives"] if entry["archive_file"] == name))
            _need(_hash_stream(stream, cap)[0] == expected, "capture_changed_during_assessment")
        capture.check(); census.check()
        _need(custody._source_bytes(root, tuple(identity["source_sha256"])) == identity["source_sha256"],
              "worker_source_image_changed")
        _disk_reserve(output.fd)
        _publish(output.fd, "tickers_projection.json", tickers, MAX_PROJECTION_BYTES)
        _publish(output.fd, "actions_projection.json", actions, MAX_PROJECTION_BYTES)
        _publish(output.fd, "assessment.json", raw, MAX_REPORT_BYTES)
        body = result.to_payload()
        counts = {field: body.get(field) for field in COUNT_FIELDS}
        _need(all(type(value) is int and value >= 0 for value in counts.values()),
              "aggregate_count_schema")
        receipt = {"schema": SCHEMA, "audit_id": audit_id, "fixture_only": fixture_only,
            "observed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "execution_identity": identity, "capture_manifest_sha256": manifest_sha,
            "inventory_sha256": inventory_sha, "census_complete_sha256": census_complete_sha,
            "assessment_sha256": _sha(raw), "assessment_bytes": len(raw),
            "tickers_projection_sha256": _sha(tickers), "actions_projection_sha256": _sha(actions),
            "counts": counts, "original_capture_lineage_preserved": True,
            "fundamentals_decoded": False, "financial_values_interpreted": False,
            "provider_dispatches": 0, "credential_reads": 0, "looks_jobs_backtests": [0, 0, 0],
            "effective_process_tree_network_denial": True, "effective_process_fork_denial": not fixture_only,
            "writes_confined_to_fresh_output_by_launcher": not fixture_only,
            **{flag: False for flag in FALSE_FLAGS}}
        # Inputs remain held across publication. A changed source cannot seal
        # a success receipt merely because the earlier read was consistent.
        capture.check(); census.check()
        _need(_sha(_read_leaf(census.fd, "inventory.json", limit=custody.assessment.MAX_INVENTORY_BYTES)) == inventory_sha
              and _sha(_read_leaf(census.fd, "complete.json", limit=1024 * 1024)) == census_complete_sha,
              "census_changed_during_publication")
        _need(custody._source_bytes(root, tuple(identity["source_sha256"])) == identity["source_sha256"],
              "worker_source_image_changed")
        receipt_sha = _exclusive_json(output.fd, "complete.json", receipt)
        _need(set(os.listdir(output.fd)) == {"tickers_projection.json", "actions_projection.json", "assessment.json", "complete.json"},
              "published_inventory_refused")
        output.recheck(); capture.check(); census.check()
        _need(custody._source_bytes(root, tuple(identity["source_sha256"])) == identity["source_sha256"],
              "worker_source_image_changed")
        return {"audit_id": audit_id, "fixture_only": fixture_only, "complete_sha256": receipt_sha,
                "assessment_sha256": _sha(raw), "counts": counts, **{flag: False for flag in FALSE_FLAGS}}
    finally:
        if capture is not None:
            capture.close()
        if census is not None:
            census.close()
        output.close()


def _verify_publication(*, root, audit_id, identity, result, manifest_sha=CAPTURE_MANIFEST_SHA256, fixture_only=False):
    output = custody._Chain(root, (*OUTPUT_PARTS, audit_id))
    try:
        _need(set(os.listdir(output.fd)) == {"tickers_projection.json", "actions_projection.json", "assessment.json", "complete.json"},
              "parent_output_inventory_refused")
        receipt_raw = _read_leaf(output.fd, "complete.json", limit=4 * 1024 * 1024)
        receipt = custody._json(receipt_raw)
        _need(type(result) is dict and type(result.get("counts")) is dict and type(receipt.get("counts")) is dict
              and set(result["counts"]) == set(receipt["counts"]) == set(COUNT_FIELDS)
              and all(type(result["counts"][key]) is int and result["counts"][key] >= 0
                      and type(receipt["counts"][key]) is int and receipt["counts"][key] >= 0 for key in COUNT_FIELDS),
              "parent_typed_counts_refused")
        _need(type(result) is dict and result.get("audit_id") == audit_id
              and result.get("complete_sha256") == _sha(receipt_raw) and receipt.get("schema") == SCHEMA
              and receipt.get("execution_identity") == identity and receipt.get("capture_manifest_sha256") == manifest_sha
              and receipt.get("counts") == result.get("counts")
              and type(fixture_only) is bool and receipt.get("fixture_only") is fixture_only
              and result.get("fixture_only") is fixture_only
              and receipt.get("effective_process_tree_network_denial") is True
              and receipt.get("effective_process_fork_denial") is (not fixture_only)
              and receipt.get("writes_confined_to_fresh_output_by_launcher") is (not fixture_only)
              and receipt.get("provider_dispatches") == receipt.get("credential_reads") == 0
              and receipt.get("fundamentals_decoded") is False and receipt.get("financial_values_interpreted") is False
              and all(receipt.get(flag) is False and result.get(flag) is False for flag in FALSE_FLAGS),
              "parent_worker_receipt_refused")
        for name, key, cap in (("assessment.json", "assessment_sha256", MAX_REPORT_BYTES),
                               ("tickers_projection.json", "tickers_projection_sha256", MAX_PROJECTION_BYTES),
                               ("actions_projection.json", "actions_projection_sha256", MAX_PROJECTION_BYTES)):
            raw = _read_leaf(output.fd, name, limit=cap)
            _need(_sha(raw) == receipt.get(key), "parent_output_hash_refused")
            if name == "assessment.json":
                _need(_sha(raw) == result.get(key) and receipt.get("assessment_bytes") == len(raw), "parent_output_hash_refused")
                body = custody._json(raw)
                _need(body.get("schema") == cohort.SCHEMA
                      and body.get("action_relation_representation") == "folded_source_label_index_union_v1"
                      and body.get("action_source_rows_or_relations_dropped") is False, "parent_compact_relation_profile_refused")
                _need(all(type(body.get(key)) is int and body[key] >= 0 for key in COUNT_FIELDS),
                      "parent_typed_counts_refused")
                _need(receipt["counts"] == {field: body.get(field) for field in COUNT_FIELDS}, "parent_output_counts_refused")
                _need(all(body.get(flag) is False for flag in cohort.FALSE_FLAGS), "parent_assessment_authority_refused")
        output.recheck()
    finally:
        output.close()


def run_actual_assessment(*, audit_id, expected_head):
    _audit_id(audit_id)
    identity = _identity(expected_head)
    output = custody._Chain(LANE_ROOT, (*OUTPUT_PARTS, audit_id), create=True, exclusive_last=True)
    output.close()
    command = ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec", "-p",
               custody._policy(LANE_ROOT.joinpath(*OUTPUT_PARTS, audit_id)), sys.executable, "-B", "-m",
               "research.insider_buying_sharadar_reference_cohort_runner", "--worker", "--audit-id", audit_id,
               "--expected-head", expected_head]
    launched = subprocess.run(command, cwd=LANE_ROOT, input=_canonical(identity), capture_output=True, check=False, timeout=1800)
    _need(_identity(expected_head) == identity, "parent_source_image_changed")
    _need(launched.returncode == 0 and not launched.stderr, "worker_refused_private_outputs_preserved")
    try:
        result = json.loads(launched.stdout)
    except (ValueError, UnicodeError):
        raise SharadarCohortRunnerError("worker_result_schema_refused") from None
    _verify_publication(root=LANE_ROOT, audit_id=audit_id, identity=identity, result=result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-id", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.worker:
            _need(Path.cwd() == LANE_ROOT, "designated_lane_required")
            identity = custody._json(sys.stdin.buffer.read(4 * 1024 * 1024))
            _need(identity.get("root") == str(LANE_ROOT) and identity.get("branch") == LANE_BRANCH
                  and identity.get("head") == args.expected_head and identity.get("clean") is True
                  and set(SOURCE_SEEDS) <= set(identity.get("source_sha256", {}))
                  and identity.get("source_inventory_sha256") == _sha(_canonical(identity["source_sha256"])),
                  "parent_identity_envelope_refused")
            result = _worker(root=LANE_ROOT, audit_id=_audit_id(args.audit_id), identity=identity,
                capture_path=CAPTURE_ROOT, manifest_sha=CAPTURE_MANIFEST_SHA256,
                inventory_sha=custody.INVENTORY_SHA256, census_complete_sha=custody.CENSUS_COMPLETE_SHA256)
        else:
            result = run_actual_assessment(audit_id=args.audit_id, expected_head=args.expected_head)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (SharadarCohortRunnerError, custody.ArchiveAssessmentRunnerError, cohort.SharadarReferenceCohortError,
            supplied.SuppliedSharadarAuditError, OSError, EodhdDemoError, subprocess.SubprocessError, KeyError, TypeError, ValueError):
        print('{"disposition":"offline_reference_assessment_refused_outputs_preserved"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
