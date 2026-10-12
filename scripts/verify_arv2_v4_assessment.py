"""Frozen v4 operational precheck and output-only report authentication.

Neither command allocates an assessment or grants source/publication authority.
The precheck samples metadata before a separately authorized one-shot run; it
cannot establish uninterrupted stability until that run. The reader opens only
the fixed output envelope, never native attributes or original source objects.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys

from scripts import assess_arv2_relocated_sources_v4 as v4

audit = v4.audit
v1 = v4.v1
ROOT = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2")
OUTPUT = ROOT / "artifacts/analyst_revisions_v2/relocation_trial/R282-20261011-A"
PROFILE_SHA256 = "63e286099b822faa5c33fb7ed46ce26bce80deb4152af438f104e260e1967319"
SECONDS = 60
MAX_REPORT_BYTES = 131072
_require = v1._require
FALSE_FLAGS = frozenset(("historical_audit_accepted", "historical_security_equivalence",
    "continuous_stability_proven", "all_worktree_artifacts_executable", "formal_admission",
    "production_publication_authorized", "provider_or_qc_contact", "output_acl_xattr_envelope_proven"))
PREFLIGHT_FALSE = frozenset(("source_contents_read", "source_reauthenticated",
    "output_allocated_by_preflight", "continuous_stability_proven", "formal_admission",
    "production_publication_authorized"))
BASE_KEYS = FALSE_FLAGS | {"schema", "profile_sha256", "policy_id", "policy",
    "source_metadata_projection_contract", "before_report_sha256", "after_report_sha256",
    "source_reauthenticated", "complete"}
LOADER_COUNTS = frozenset(("public_rows", "price_rows", "current_rows", "vintage_rows",
    "vintage_member_rows", "vintage_selected_rows", "vintage_excluded_rows"))
CONSUMPTION_KEYS = frozenset(("loader_results", "file_count", "directory_count",
    "directory_metadata", "security_observations", "file_security_observations"))


def _hash(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _same(value, expected):
    # JSON-byte equality distinguishes True/1 and 1/1.0 in pinned structures.
    return audit._json_bytes(value) == audit._json_bytes(expected)


def _keys(value, expected, code):
    _require(type(value) is dict and set(value) == set(expected), code)


def _scope_keys():
    directories, files = v4._paths()  # Lexical only: no object observations.
    return ({str(path.relative_to(ROOT.parent)): path for path in directories},
            {str(path.relative_to(ROOT.parent)): path for path in files})


def _metadata(value, code):
    _keys(value, v4.METADATA_FIELDS, code)
    _require(all(type(item) is int for item in value.values())
             and value["dev"] == v4.policy.PROSPECTIVE_DEVICE, code)


def _security(value, *, vintage=False):
    _keys(value, {"acl_empty", "xattrs", "policy_id"} if vintage else {"acl_empty", "xattrs"},
          "report_security_shape")
    _require(value["acl_empty"] is True, "report_security_acl")
    attrs = value["xattrs"]
    _require(type(attrs) is dict, "report_security_xattrs")
    if vintage:
        expected = v4.policy.policy_record()["xattr_pins"]
        _require(value["policy_id"] == v4.policy.POLICY_ID and _same(attrs, expected),
                 "report_vintage_security")
    else:
        _require(set(attrs) <= {"com.apple.provenance"}, "report_security_xattrs")
        for row in attrs.values():
            _keys(row, {"size", "sha256"}, "report_security_xattrs")
            _require(type(row["size"]) is int and 0 <= row["size"] <= v4.policy.MAX_VALUE_BYTES
                     and _hash(row["sha256"]), "report_security_xattrs")


def _validate_preflight(value):
    _keys(value, PREFLIGHT_FALSE | {"schema", "profile_sha256", "policy_id", "directory_count",
        "file_count", "inventory", "vintage_security", "elapsed_seconds"}, "preflight_shape")
    _require(value["schema"] == v4.PREFLIGHT_SCHEMA and value["profile_sha256"] == PROFILE_SHA256
             and value["policy_id"] == v4.policy.POLICY_ID, "preflight_pins")
    _require(type(value["directory_count"]) is int and value["directory_count"] == 12
             and type(value["file_count"]) is int and value["file_count"] == 15,
             "preflight_counts")
    _require(all(value[flag] is False for flag in PREFLIGHT_FALSE), "preflight_flags")
    elapsed = value["elapsed_seconds"]
    _require(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0,
             "preflight_elapsed")
    directories, files = _scope_keys()
    _keys(value["inventory"], directories.keys() | files.keys(), "preflight_inventory")
    for key, path in (directories | files).items():
        row = value["inventory"][key]
        _keys(row, {"metadata", "names"}, "preflight_inventory_row")
        _metadata(row["metadata"], "preflight_inventory_metadata")
        _require(v4._directory_secure(row["metadata"], path) if key in directories
                 else v1._private_file(row["metadata"]), "preflight_inventory_security")
        names = row["names"]
        _require(type(names) is list and all(type(name) is str for name in names)
                 and names == sorted(set(names)), "preflight_inventory_names")
        if path == v4.policy.VINTAGE_PATH:
            _require(_same(row["metadata"], dict(v4.policy.VINTAGE_METADATA))
                     and names == [name.decode("ascii") for name, _n, _h in v4.policy.XATTR_PINS],
                     "preflight_vintage")
        else:
            _require(set(names) <= {"com.apple.provenance"}, "preflight_inventory_names")
    _security(value["vintage_security"], vintage=True)


def _receipt(value):
    contract = v4._projection_contract()
    hashes = {"historical_rows_sha256", "prospective_rows_sha256"}
    _keys(value, contract.keys() | hashes, "report_projection_receipt")
    _require(_same({key: value[key] for key in contract}, contract)
             and all(_hash(value[key]) for key in hashes), "report_projection_receipt")


def precheck():
    """One pinned-history projection followed by one no-allocation preflight."""
    before, after = v1._read_pinned_reports(ROOT)
    projected, receipt = v4._project_sources(v1._scope(before, after))
    observed = v4.preflight_scope()
    _validate_preflight(observed)
    for relative, row in projected.items():
        key = str((ROOT / relative).relative_to(ROOT.parent))
        _require(_same(observed["inventory"][key]["metadata"], row["metadata"]),
                 "preflight_projected_metadata")
    _require(v4.profile_sha256() == PROFILE_SHA256, "precheck_profile_changed")
    return {"schema": "arv2-v4-precheck-summary-v1", "profile_sha256": PROFILE_SHA256,
            "preflight_sha256": hashlib.sha256(audit._json_bytes(observed)).hexdigest(),
            "historical_rows_sha256": receipt["historical_rows_sha256"],
            "prospective_rows_sha256": receipt["prospective_rows_sha256"],
            "directory_count": 12, "file_count": 15, "projected_metadata_match": True,
            "source_reauthenticated": False, "assessment_allocated": False,
            "continuous_stability_proven": False}


def _output_directory_metadata(fd):
    held = audit._metadata(os.fstat(fd))
    _metadata(held, "report_directory_metadata")
    _require(stat.S_ISDIR(held["mode"]) and held["uid"] == os.getuid()
             and stat.S_IMODE(held["mode"]) == 0o700, "report_directory_security")
    return held


def _named_output_metadata():
    fd = audit._open_absolute_directory(OUTPUT)
    try:
        return _output_directory_metadata(fd)
    finally:
        os.close(fd)


def _read_report(expected_digest):
    """Read only the fixed report, binding its full held/named output envelope."""
    _require(_hash(expected_digest), "report_expected_digest")
    with ExitStack() as stack:
        directory = audit._open_absolute_directory(OUTPUT)
        stack.callback(os.close, directory)
        initial_directory = _output_directory_metadata(directory)
        _require(initial_directory == _named_output_metadata(), "report_directory_identity")
        _require(os.listdir(directory) == ["report.json"], "report_inventory")
        named = audit._metadata(os.stat("report.json", dir_fd=directory, follow_symlinks=False))
        _metadata(named, "report_file_metadata")
        _require(stat.S_ISREG(named["mode"]) and named["uid"] == os.getuid()
                 and stat.S_IMODE(named["mode"]) == 0o600 and named["nlink"] == 1
                 and 1 <= named["size"] <= MAX_REPORT_BYTES, "report_file_security")
        fd = os.open("report.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        stack.callback(os.close, fd)
        _require(named == audit._metadata(os.fstat(fd)), "report_open_identity")
        chunks, count = [], 0
        while True:
            part = os.read(fd, min(65536, named["size"] + 1 - count))
            if not part:
                break
            count += len(part)
            _require(count <= named["size"], "report_read_size")
            chunks.append(part)
        _require(count == named["size"], "report_read_size")
        raw = b"".join(chunks)
        _require(named == audit._metadata(os.fstat(fd)) == audit._metadata(
            os.stat("report.json", dir_fd=directory, follow_symlinks=False)), "report_file_changed")
        _require(initial_directory == _output_directory_metadata(directory)
                 == _named_output_metadata(), "report_directory_changed")
        _require(os.listdir(directory) == ["report.json"], "report_inventory")
        _require(initial_directory == _output_directory_metadata(directory)
                 == _named_output_metadata(), "report_directory_changed_after_inventory")
        _require(named == audit._metadata(os.fstat(fd)) == audit._metadata(
            os.stat("report.json", dir_fd=directory, follow_symlinks=False)), "report_file_changed_final")
        _require(hashlib.sha256(raw).hexdigest() == expected_digest, "report_digest_mismatch")
        return raw, initial_directory, named


def _strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "report_duplicate_key")
            result[key] = value
        return result

    def constant(_value):
        raise audit.Refusal("report_nonfinite")

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
        _require(audit._json_bytes(value) == raw, "report_noncanonical")
    except (ValueError, UnicodeError, RecursionError):
        raise audit.Refusal("report_json_invalid") from None
    return value


def _validate_consumption(report):
    _require(type(report["file_count"]) is int and report["file_count"] == 15
             and type(report["directory_count"]) is int and report["directory_count"] == 12,
             "report_consumption_counts")
    directories, files = _scope_keys()
    _keys(report["directory_metadata"], directories, "report_directory_keys")
    _keys(report["security_observations"], directories, "report_directory_security_keys")
    _keys(report["file_security_observations"], v4._source_keys(), "report_file_security_keys")
    for key, path in directories.items():
        meta = report["directory_metadata"][key]
        _metadata(meta, "report_consumed_directory_metadata")
        _require(v4._directory_secure(meta, path), "report_consumed_directory_security")
        if path == v4.policy.VINTAGE_PATH:
            _require(_same(meta, dict(v4.policy.VINTAGE_METADATA)), "report_consumed_vintage")
        _security(report["security_observations"][key], vintage=path == v4.policy.VINTAGE_PATH)
    for value in report["file_security_observations"].values():
        _security(value)
    loaders = report["loader_results"]
    _keys(loaders, LOADER_COUNTS | {"current_refusals", "vintage_refusals", "manifest_pins"},
          "report_loaders_shape")
    _require(all(type(loaders[key]) is int and loaders[key] >= 0 for key in LOADER_COUNTS),
             "report_loader_counts")
    _require(_same(loaders["manifest_pins"], dict(v1.MANIFESTS)), "report_manifest_pins")
    for name in ("current_refusals", "vintage_refusals"):
        _require(type(loaders[name]) is dict and all(
            type(key) is str and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,159}", key)
            and type(value) is int and value >= 0 for key, value in loaders[name].items()),
            "report_loader_refusals")


def _validate_report(report, assessment_exit_code):
    _require(type(report) is dict and BASE_KEYS <= set(report), "report_base_shape")
    _require(report["schema"] == v4.SCHEMA and report["profile_sha256"] == PROFILE_SHA256
             and report["policy_id"] == v4.policy.POLICY_ID
             and _same(report["policy"], v4.policy.policy_record())
             and _same(report["source_metadata_projection_contract"], v4._projection_contract())
             and report["before_report_sha256"] == v1.BEFORE_SHA
             and report["after_report_sha256"] == v1.AFTER_SHA, "report_pins")
    _require(all(report[flag] is False for flag in FALSE_FLAGS), "report_flags")
    _require(type(report["complete"]) is bool and type(report["source_reauthenticated"]) is bool
             and report["complete"] is report["source_reauthenticated"], "report_completion")
    _require(type(assessment_exit_code) is int, "report_assessment_exit")
    present = set(report) - BASE_KEYS
    if "preflight" in report:
        _validate_preflight(report["preflight"])
    if "source_metadata_projection" in report:
        _require("preflight" in report, "report_receipt_without_preflight")
        _receipt(report["source_metadata_projection"])
    consumed = present & CONSUMPTION_KEYS
    if consumed:
        _require(consumed == CONSUMPTION_KEYS and "source_metadata_projection" in report,
                 "report_partial_consumption")
        _validate_consumption(report)
    required_success = CONSUMPTION_KEYS | {"preflight", "source_metadata_projection"}
    if report["complete"]:
        _require(present == required_success, "report_success_shape")
        for relative, pair in v4.CTIME_PROJECTION.items():
            key = str((ROOT / relative).relative_to(ROOT.parent))
            _require(report["preflight"]["inventory"][key]["metadata"]["ctime_ns"] == pair[1],
                     "report_success_preflight_ctime")
    else:
        _require({"refusal_type", "refusal_code"} <= present
                 and present <= required_success | {"refusal_type", "refusal_code"},
                 "report_refusal_shape")
        _require(type(report["refusal_type"]) is str and re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]{0,79}", report["refusal_type"])
            and type(report["refusal_code"]) is str and re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_ -]{0,159}", report["refusal_code"]), "report_refusal_code")
    return report["complete"] and assessment_exit_code == 0


def authenticate_report(expected_digest, assessment_exit_code):
    raw, directory_meta, file_meta = _read_report(expected_digest)
    report = _strict_json(raw)
    success = _validate_report(report, assessment_exit_code)
    _require(v4.profile_sha256() == PROFILE_SHA256, "report_profile_changed")
    return {"schema": "arv2-v4-report-authentication-v1", "report_sha256": expected_digest,
            "report_size": len(raw), "profile_sha256": PROFILE_SHA256,
            "report_authenticated": True, "assessment_accepted": success,
            "assessment_exit_code": assessment_exit_code, "complete": report["complete"],
            "source_reauthenticated": report["source_reauthenticated"],
            "directory_metadata": directory_meta, "file_metadata": file_meta,
            "directory_count": report.get("directory_count", 0),
            "file_count": report.get("file_count", 0),
            "refusal_code": report.get("refusal_code"), "output_acl_xattr_envelope_proven": False}


def _gate(expected_profile):
    _require(Path.cwd() == ROOT and Path(__file__).resolve().parents[1] == ROOT
             and v4.ROOT == ROOT and v1.ROOT == ROOT and v4.OUTPUT == OUTPUT
             and v4.policy.VINTAGE_PATH == ROOT / v1.VINTAGE, "verification_fixed_root")
    _require(sys.platform == "darwin" and hasattr(os.stat_result, "st_flags"),
             "verification_platform")
    _require(expected_profile == PROFILE_SHA256 == v4.profile_sha256(), "verification_profile")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--precheck", action="store_true")
    mode.add_argument("--report", action="store_true")
    parser.add_argument("--expected-profile-sha256", required=True)
    parser.add_argument("--expected-report-sha256")
    parser.add_argument("--assessment-exit-code", type=int)
    args = parser.parse_args(argv)
    if args.report and (args.expected_report_sha256 is None or args.assessment_exit_code is None):
        parser.error("report mode requires emitted digest and actual assessment exit code")
    if args.precheck and (args.expected_report_sha256 is not None or args.assessment_exit_code is not None):
        parser.error("report evidence arguments are only valid in report mode")
    _gate(args.expected_profile_sha256)
    with v4._budget(SECONDS):
        result = precheck() if args.precheck else authenticate_report(
            args.expected_report_sha256, args.assessment_exit_code)
    print(audit._json_bytes(result).decode("ascii"), end="")
    return 0 if args.precheck or result["assessment_accepted"] else 1


def _entrypoint(argv=None):
    try:
        return main(argv)
    except Exception as error:
        # Native/OSError text may disclose source rows or opaque attributes.
        # Only established bounded Refusal codes leave this boundary.
        code = getattr(error, "code", None)
        if (not isinstance(error, audit.Refusal) or type(code) is not str
                or re.fullmatch(r"[A-Za-z][A-Za-z0-9_ -]{0,159}", code) is None):
            code = "verification_operation_refused"
        print(audit._json_bytes({"schema": "arv2-v4-verification-refusal-v1",
            "verification_accepted": False, "refusal_code": code,
            "evidence_retained": True}).decode("ascii"), end="", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
