"""One-use, aggregate-only characterization of retained R297 duplicate IDs.

Run only under the separately frozen native-network-denied command. This reads
each pinned leaf once, retains its original full metadata/descriptor through
final checks, and emits no IDs, rows, dates or authority. It never accepts,
quarantines, collapses or replaces the failed original acquisition.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from types import MappingProxyType

ROOT = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import diagnose_arv2_r297_authentication as diagnostic

helpers, capture, delta = diagnostic.helpers, diagnostic.capture, diagnostic.delta
BRANCH, PYTHON = diagnostic.BRANCH, diagnostic.PYTHON
SOURCE = ROOT / "scripts/characterize_arv2_r297_duplicates.py"
CONTROL = ROOT / "artifacts/analyst_revisions_v2/massive_ratings_delta/R297-20261013-D4"
CAPTURE_PATH = diagnostic.CAPTURE_PATH
MANIFEST_SHA256, MANIFEST_BYTES = diagnostic.MANIFEST_SHA256, diagnostic.MANIFEST_BYTES
DEADLINE_SECONDS = 30
SCHEMA = "arv2-r297-duplicate-characterization-v1"
SOURCE_PINS = MappingProxyType({**diagnostic.SOURCE_PINS,
    "scripts/diagnose_arv2_r297_authentication.py":
        "850864cb1d166526bd73144dbdfa5efce37d46dd9ffeadddd2037a7e29b9d8f9"})
KNOWN_CODES = frozenset({"diagnostic_refused", "manifest_external_pin", "manifest_digest_marker",
    "manifest_canonical", "artifact_inventory", "page_external_pin", "page_binding", "row_count",
    "leaf_final_changed", "directory_final_changed", "ancestor_changed"})
COUNT_FIELDS = ("total_rows", "valid_id_rows", "invalid_id_rows", "unique_ids", "repeated_groups",
    "repeated_occurrences_including_first", "excess_repeated_occurrences", "byte_identical_groups",
    "conflicting_groups", "within_page_only_groups", "across_pages_only_groups", "within_and_across_page_groups")
PROFILE = helpers.canonical_json_bytes({"schema": SCHEMA, "root": str(ROOT), "branch": BRANCH,
    "python": str(PYTHON), "control": str(CONTROL), "capture": str(CAPTURE_PATH),
    "manifest_sha256": MANIFEST_SHA256, "manifest_bytes": MANIFEST_BYTES,
    "source_pins": dict(SOURCE_PINS), "deadline_seconds": DEADLINE_SECONDS,
    "max_pages": delta.MAX_PAGES, "max_rows": delta.MAX_ROWS,
    "max_raw_page_bytes": delta.MAX_PAGE_BYTES, "max_raw_bytes": delta.MAX_RAW_BYTES,
    "max_rows_bytes": delta.MAX_ROWS_BYTES, "count_fields": list(COUNT_FIELDS),
    "repeated_occurrences": "all occurrences in groups of two or more, including the first",
    "excess_occurrences": "sum of group size minus one over repeated groups",
    "location_classes": "disjoint within-page-only, across-pages-only, both",
    "identity_equality": "exact frozen valid provider ID; exact canonical row-byte equality",
    "native_network_denial": "required_external_sandbox-exec_deny_network",
    "diagnostic_only": True, "original_capture_accepted": False, "authority_minted": False,
    "quarantine_or_collapse": False, "provider_contact_authorized": False})
PROFILE_SHA256 = hashlib.sha256(PROFILE).hexdigest()


class DuplicateDiagnosticError(ValueError):
    pass


def _require(condition, code="diagnostic_refused"):
    if not condition:
        raise DuplicateDiagnosticError(code)


def _preflight(head, caller, deadline):
    _require(sys.platform == "darwin" and os.name == "posix" and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT
        and Path(__file__).absolute() == SOURCE)
    _require(type(head) is str and re.fullmatch(r"[0-9a-f]{40}", head) is not None)
    helpers.require_sha256(caller, "caller")
    for args, expected in ((["rev-parse", "--show-toplevel"], str(ROOT)),
            (["branch", "--show-current"], BRANCH), (["rev-parse", "HEAD"], head),
            (["status", "--porcelain"], "")):
        result = subprocess.run(["git", *args], cwd=ROOT, stdin=subprocess.DEVNULL,
            capture_output=True, timeout=min(3, helpers._remaining(deadline)), check=False)
        _require(result.returncode == 0 and not result.stderr and result.stdout.decode().strip() == expected)
    for relative, expected in SOURCE_PINS.items():
        helpers.require_sha256(expected, "source pin")
        _require(helpers._source_digest(ROOT / relative) == expected)
    _require(helpers._source_digest(SOURCE) == caller)
    capture._require_dirfd_support()
    helpers._remaining(deadline)


def _check(directory, name, fd, identity):
    _require(helpers._identity(helpers._file_metadata(fd)) == identity)
    helpers._named_file(directory, name, fd)
    capture._require_reopened_artifact_identity(CONTROL, directory)


def _claim(head, caller):
    capture._require_operational_artifact_scope(CONTROL)
    _, parent = capture._open_directory_path(CONTROL.parent, create=True, name="duplicate diagnostic parent")
    directory = claim = None
    try:
        os.mkdir(CONTROL.name, 0o700, dir_fd=parent)
        os.fsync(parent)
        directory = capture._open_private_child_directory(parent, CONTROL.name, "duplicate diagnostic")
        claim, _, identity = diagnostic.original.transport._write_held(directory, "claim.json", {
            "schema": SCHEMA, "profile_sha256": PROFILE_SHA256, "expected_head": head,
            "caller_sha256": caller, "claimed_at": helpers._utc_now(), "attempt_consumed": True})
        capture._require_pinned_child_identity(parent, CONTROL.name, directory, "duplicate diagnostic")
        return directory, claim, identity
    except BaseException:
        for fd in (claim, directory):
            if fd is not None:
                os.close(fd)
        raise
    finally:
        os.close(parent)


def _characterize(deadline):
    """No authentication authority: return counters only after every final guard."""
    chain, held = [], []
    try:
        chain = delta._open_chain(CAPTURE_PATH)
        directory = chain[-1][0]
        initial_directory = delta._metadata(os.fstat(directory))
        manifest_bytes = delta._read_held(directory, "manifest.json", delta.MAX_MANIFEST_BYTES, held,
            expected_size=MANIFEST_BYTES)
        _require(hashlib.sha256(manifest_bytes).hexdigest() == MANIFEST_SHA256, "manifest_external_pin")
        marker = delta._read_held(directory, "manifest.sha256", 65, held, expected_size=65)
        _require(marker == (MANIFEST_SHA256 + "\n").encode("ascii"), "manifest_digest_marker")
        manifest = delta.strict_json_loads(manifest_bytes.decode("ascii"), "ratings manifest")
        _require(delta.canonical_bytes(manifest) == manifest_bytes, "manifest_canonical")
        delta._validate_manifest(manifest)
        inventory = {"manifest.json", "manifest.sha256"}
        for number in range(1, manifest["page_count"] + 1):
            inventory.update(delta.page_names(number))
        _require(set(os.listdir(directory)) == inventory, "artifact_inventory")
        groups, total, invalid = {}, 0, 0
        for record in manifest["pages"]:
            helpers._remaining(deadline)
            raw_name, rows_name = delta.page_names(record["page_number"])
            raw = delta._read_held(directory, raw_name, delta.MAX_PAGE_BYTES, held,
                expected_size=record["raw_response_bytes"])
            extracted = delta._read_held(directory, rows_name, delta.MAX_ROWS_BYTES, held,
                expected_size=record["provider_rows_bytes"])
            _require(hashlib.sha256(raw).hexdigest() == record["raw_response_sha256"]
                and hashlib.sha256(extracted).hexdigest() == record["provider_rows_sha256"], "page_external_pin")
            observed = delta.build_page_record(page_number=record["page_number"], raw_response=raw,
                provider_rows=extracted, response_received_at=record["response_received_at"],
                request_cursor_sha256=record["request_cursor_sha256"])
            _require(observed == record, "page_binding")
            parsed = delta._input._parse_provider_rows_bytes(extracted)
            _require(len(parsed) == record["row_count"], "row_count")
            for row, row_bytes in parsed:
                total += 1
                identifier = delta._input._candidate_provider_event_id(row)
                if identifier is None:
                    invalid += 1
                    continue
                group = groups.setdefault(identifier, {"first": row_bytes, "count": 0,
                    "pages": {}, "conflicting": False})
                group["count"] += 1
                page = record["page_number"]
                group["pages"][page] = group["pages"].get(page, 0) + 1
                group["conflicting"] |= row_bytes != group["first"]
        _require(total == manifest["row_count"], "row_count")
        result = dict.fromkeys(COUNT_FIELDS, 0)
        result.update(total_rows=total, valid_id_rows=total-invalid, invalid_id_rows=invalid,
            unique_ids=len(groups))
        for group in groups.values():
            if group["count"] < 2:
                continue
            result["repeated_groups"] += 1
            result["repeated_occurrences_including_first"] += group["count"]
            result["excess_repeated_occurrences"] += group["count"] - 1
            result["conflicting_groups" if group["conflicting"] else "byte_identical_groups"] += 1
            across = len(group["pages"]) > 1
            within = any(count > 1 for count in group["pages"].values())
            location = "within_and_across_page_groups" if across and within else (
                "across_pages_only_groups" if across else "within_page_only_groups")
            result[location] += 1
        for fd, name, identity in held:
            _require(delta._metadata(os.fstat(fd)) == identity
                and delta._metadata(os.stat(name, dir_fd=directory, follow_symlinks=False)) == identity,
                "leaf_final_changed")
        _require(set(os.listdir(directory)) == inventory
            and delta._metadata(os.fstat(directory)) == initial_directory, "directory_final_changed")
        for fd, parent, name, identity in chain:
            _require(delta._directory_binding(os.fstat(fd)) == identity and (parent is None or
                delta._directory_binding(os.stat(name, dir_fd=parent, follow_symlinks=False)) == identity),
                "ancestor_changed")
        helpers._remaining(deadline)
        return result
    finally:
        for fd, _, _ in reversed(held):
            os.close(fd)
        for fd, _, _, _ in reversed(chain):
            os.close(fd)


def _failure(exc):
    if type(exc) is DuplicateDiagnosticError:
        args = exc.args
        code = args[0] if type(args) is tuple and len(args) == 1 and type(args[0]) is str else None
        return "duplicate_diagnostic_error", code if code in KNOWN_CODES else "unknown"
    return diagnostic._failure(exc)


def _run(head, caller, deadline):
    directory = claim = report_fd = None
    consumed, stage = False, "preflight"
    counters, exception_type, refusal_code = None, None, None
    terminal = "diagnostic_refused"
    started = helpers._utc_now()
    try:
        _preflight(head, caller, deadline)
        consumed, stage = None, "claim"
        directory, claim, identity = _claim(head, caller)
        consumed, stage = True, "source_characterization"
        _check(directory, "claim.json", claim, identity)
        counters = _characterize(deadline)
        terminal = "duplicates_characterized"
    except BaseException as exc:
        counters = None
        exception_type, refusal_code = _failure(exc)
    try:
        helpers._remaining(deadline)
        if directory is None:
            print(helpers.canonical_json_bytes({"schema": SCHEMA, "terminal": terminal,
                "stage": stage, "attempt_consumed": consumed, "exception_type": exception_type,
                "refusal_code": refusal_code, "diagnostic_only": True,
                "original_capture_accepted": False}).decode())
            return 2
        _check(directory, "claim.json", claim, identity)
        report = {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256, "expected_head": head,
            "caller_sha256": caller, "started_at": started, "finished_at": helpers._utc_now(),
            "terminal": terminal, "stage": stage, "exception_type": exception_type,
            "refusal_code": refusal_code, "counters": counters, "attempt_consumed": True,
            "diagnostic_only": True, "original_capture_accepted": False, "authority_minted": False,
            "quarantine_or_collapse": False, "provider_contact_authorized": False,
            "provider_request_count": None, "point_in_time_proven": False, "backtest_ready": False,
            "paper_or_live_ready": False, "qc_calls": 0, "outcome_reads": 0}
        report_fd, payload, report_identity = diagnostic.original.transport._write_held(directory, "report.json", report)
        _check(directory, "claim.json", claim, identity)
        _check(directory, "report.json", report_fd, report_identity)
        helpers._remaining(deadline)
        print(helpers.canonical_json_bytes({"report": report,
            "report_sha256": hashlib.sha256(payload).hexdigest(), "report_bytes": len(payload)}).decode())
        return 0 if terminal == "duplicates_characterized" else 2
    except BaseException:
        print('{"terminal":"diagnostic_publication_ambiguous","original_capture_accepted":false}')
        return 2
    finally:
        for fd in (report_fd, claim, directory):
            if fd is not None:
                os.close(fd)


def run(head, caller):
    deadline = time.monotonic() + DEADLINE_SECONDS
    try:
        with helpers._alarm(deadline):
            return _run(head, caller, deadline)
    except BaseException:
        print('{"terminal":"diagnostic_parent_ambiguous","original_capture_accepted":false}')
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--caller-sha256", required=True)
    args = parser.parse_args(argv)
    return run(args.expected_head, args.caller_sha256)


if __name__ == "__main__":
    raise SystemExit(main())
