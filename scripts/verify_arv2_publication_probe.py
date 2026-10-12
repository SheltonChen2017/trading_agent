"""Authenticate only the fixed ARV2OD272-A synthetic output after its one run.

This reader never invokes a probe, reads a source package, queries native
attributes, repairs evidence, or establishes production-publication clearance.
Reported samples remain producer claims; they cannot prove continuous stability.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import sys
import time

from scripts import audit_arv2_relocation as audit
from scripts import diagnose_arv2_publication_flags as producer

ROOT = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2")
OUTPUT = ROOT / "artifacts/analyst_revisions_v2/publication_metadata/R272-20261009-A"
PROFILE_SHA256 = "7877cea0fc80e71342e1ff613e5e5a6832130edd330289c9660d8894d39fbcd7"
DEVICE = 16777231
SECONDS = 60
MAX_REPORT_BYTES = 256 * 1024
CASES = ("direct_final", "pending_link")
OFFSETS = (0, 0.01, 0.1, 0.5, 1, 2, 3, 5, 10, 20, 30)
MAX_PROBE_SECONDS = 45
ENVELOPE_FIELDS = frozenset(("dev", "ino", "size", "mode", "uid", "gid", "nlink",
                            "mtime_ns", "ctime_ns", "flags"))
# _changed used the producer's insertion order before canonical serialization.
SAMPLE_FIELDS = ("dev", "ino", "size", "mtime_ns", "ctime_ns", "mode", "uid", "nlink",
                 "regular", "gid", "flags", "birthtime_ns", "birthtime_seconds")
ROWS = ("held", "named", "held_after_read", "named_after_read")
CHANGES = ("held_changed", "named_changed", "during_read_held_changed",
           "during_read_named_changed", "held_named_mismatch")
CHECK_KEYS = frozenset(ROWS + CHANGES + ("readback_sha256", "readback_matches", "integrity_unchanged"))
TIMING_KEYS = frozenset(("offset_seconds", "elapsed_seconds", "global_elapsed_seconds", "within_deadline"))
FALSE_FLAGS = frozenset(("production_integrity_waiver", "proves_perpetual_stability",
                        "provider_or_qc_contact", "security_attributes_queried"))
REPORT_KEYS = FALSE_FLAGS | {"schema", "source_profile", "source_profile_sha256", "fixture_mode",
    "cases", "case_count", "observation_count", "initial_verification_count",
    "refused_initial_integrity_count", "refused_integrity_observation_count", "complete",
    "elapsed_seconds", "maximum_seconds", "flags_available", "synthetic_only"}


def _require(condition, code):
    if not condition:
        raise audit.Refusal(code)


def _hash(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _same(left, right):
    return audit._json_bytes(left) == audit._json_bytes(right)


def _keys(value, keys, code):
    _require(type(value) is dict and set(value) == set(keys), code)


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


@contextmanager
def _budget():
    """Cooperative process deadline, not proof that native calls are interruptible."""
    def expired(_signum, _frame):
        raise audit.Refusal("verification_deadline")

    previous = signal.getsignal(signal.SIGALRM)
    timer = signal.getitimer(signal.ITIMER_REAL)
    _require(timer == (0.0, 0.0), "verification_existing_timer")
    deadline = time.monotonic() + SECONDS
    signal.signal(signal.SIGALRM, expired)
    try:
        signal.setitimer(signal.ITIMER_REAL, SECONDS)
        yield
        _require(time.monotonic() < deadline, "verification_deadline")
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _envelope_metadata(info):
    row = audit._metadata(info)
    _keys(row, ENVELOPE_FIELDS, "output_metadata_shape")
    _require(all(type(value) is int for value in row.values()) and row["dev"] == DEVICE,
             "output_metadata_device")
    return row


def _directory(fd):
    row = _envelope_metadata(os.fstat(fd))
    _require(stat.S_ISDIR(row["mode"]) and stat.S_IMODE(row["mode"]) == 0o700
             and row["uid"] == os.getuid(), "output_directory_security")
    return row


def _named_directory(path):
    fd = audit._open_absolute_directory(path)
    try:
        return _directory(fd)
    finally:
        os.close(fd)


def _file_security(row, *, fixture=False):
    _require(stat.S_ISREG(row["mode"]) and stat.S_IMODE(row["mode"]) == 0o600
             and row["uid"] == os.getuid() and row["nlink"] == 1
             and (row["size"] == 48 if fixture else 1 <= row["size"] <= MAX_REPORT_BYTES),
             "output_file_security")


def _read_file(stack, directory, name, *, fixture=False):
    named = _envelope_metadata(os.stat(name, dir_fd=directory, follow_symlinks=False))
    _file_security(named, fixture=fixture)
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    stack.callback(os.close, fd)
    _require(named == _envelope_metadata(os.fstat(fd)), "output_file_open_identity")
    sampled = producer._metadata(os.fstat(fd)) if fixture else None
    if fixture:
        _require(_same(sampled, producer._metadata(os.stat(name, dir_fd=directory,
                                                        follow_symlinks=False))), "fixture_open_identity")
    chunks, count = [], 0
    while True:
        part = os.read(fd, min(65536, named["size"] + 1 - count))
        if not part:
            break
        count += len(part)
        _require(count <= named["size"], "output_read_size")
        chunks.append(part)
    _require(count == named["size"], "output_read_size")
    raw = b"".join(chunks)
    _check_file(directory, name, fd, named, sampled)
    if fixture:
        _require(raw == producer.probe.PAYLOAD and len(raw) == 48
                 and hashlib.sha256(raw).hexdigest() == producer.PROFILE["fixture_sha256"],
                 "fixture_payload")
    return fd, named, sampled, raw


def _check_file(directory, name, fd, initial, sampled):
    held = os.fstat(fd)
    named = os.stat(name, dir_fd=directory, follow_symlinks=False)
    _require(initial == _envelope_metadata(held) == _envelope_metadata(named), "output_file_changed")
    if sampled is not None:
        _require(_same(sampled, producer._metadata(held)) and _same(sampled, producer._metadata(named)),
                 "fixture_metadata_changed")


def _read_envelope(expected_digest):
    """Only report.json and the two fixed synthetic final.json files are read."""
    _require(_hash(expected_digest), "report_expected_digest")
    with ExitStack() as stack:
        root = audit._open_absolute_directory(OUTPUT)
        stack.callback(os.close, root)
        root_meta = _directory(root)
        _require(root_meta == _named_directory(OUTPUT), "output_directory_identity")
        _require(set(os.listdir(root)) == {"report.json", *CASES}, "output_inventory")
        report_fd, report_meta, _none, raw = _read_file(stack, root, "report.json")
        _require(hashlib.sha256(raw).hexdigest() == expected_digest, "report_digest_mismatch")
        retained, fixtures = [], {}
        for case in CASES:
            before = _envelope_metadata(os.stat(case, dir_fd=root, follow_symlinks=False))
            child = os.open(case, audit._directory_flags(), dir_fd=root)
            stack.callback(os.close, child)
            child_meta = _directory(child)
            _require(before == child_meta == _named_directory(OUTPUT / case), "fixture_directory_identity")
            _require(os.listdir(child) == ["final.json"], "fixture_inventory")
            fd, meta, sampled, _payload = _read_file(stack, child, "final.json", fixture=True)
            fixtures[case] = sampled
            retained.append((case, child, child_meta, fd, meta, sampled))
        for case, child, child_meta, fd, meta, sampled in retained:
            _require(child_meta == _directory(child) == _named_directory(OUTPUT / case)
                     == _envelope_metadata(os.stat(case, dir_fd=root, follow_symlinks=False)),
                     "fixture_directory_changed")
            _require(os.listdir(child) == ["final.json"], "fixture_inventory")
            _require(child_meta == _directory(child) == _named_directory(OUTPUT / case),
                     "fixture_directory_changed_after_inventory")
            _check_file(child, "final.json", fd, meta, sampled)
        _require(root_meta == _directory(root) == _named_directory(OUTPUT), "output_directory_changed")
        _require(set(os.listdir(root)) == {"report.json", *CASES}, "output_inventory")
        _require(root_meta == _directory(root) == _named_directory(OUTPUT),
                 "output_directory_changed_after_inventory")
        _check_file(root, "report.json", report_fd, report_meta, None)
        return raw, fixtures


def _strict_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            _require(key not in value, "report_duplicate_key")
            value[key] = item
        return value

    def constant(_value):
        raise audit.Refusal("report_nonfinite")

    try:
        result = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
        _require(audit._json_bytes(result) == raw, "report_noncanonical")
    except (ValueError, UnicodeError, RecursionError):
        raise audit.Refusal("report_json_invalid") from None
    return result


def _sample_metadata(row):
    _keys(row, SAMPLE_FIELDS, "sample_metadata_shape")
    integer_fields = set(SAMPLE_FIELDS) - {"regular", "flags", "birthtime_ns", "birthtime_seconds"}
    _require(all(type(row[key]) is int and row[key] >= 0 for key in integer_fields)
             and type(row["regular"]) is bool
             and (row["flags"] is None or type(row["flags"]) is int and row["flags"] >= 0)
             and (row["birthtime_ns"] is None or type(row["birthtime_ns"]) is int and row["birthtime_ns"] >= 0)
             and (row["birthtime_seconds"] is None or _number(row["birthtime_seconds"])),
             "sample_metadata_types")


def _safe(row, allocation):
    return (all(row[key] == allocation[key] for key in ("dev", "ino", "gid"))
            and row["dev"] == DEVICE and row["regular"] is True and row["mode"] == 0o600
            and row["uid"] == os.getuid() and row["nlink"] == 1 and row["size"] == 48)


def _changed(before, after):
    return [key for key in SAMPLE_FIELDS if not _same(before[key], after[key])]


def _check_sample(sample, baseline, allocation, *, baseline_ok=True, timed=False):
    _keys(sample, CHECK_KEYS | TIMING_KEYS if timed else CHECK_KEYS, "sample_shape")
    for key in ROWS:
        _sample_metadata(sample[key])
    expected = {
        "held_changed": _changed(baseline["held"], sample["held_after_read"]),
        "named_changed": _changed(baseline["named"], sample["named_after_read"]),
        "during_read_held_changed": _changed(sample["held"], sample["held_after_read"]),
        "during_read_named_changed": _changed(sample["named"], sample["named_after_read"]),
        "held_named_mismatch": _changed(sample["held_after_read"], sample["named_after_read"])}
    _require(all(_same(sample[key], expected[key]) for key in CHANGES), "sample_changed_fields")
    _require(_hash(sample["readback_sha256"]), "sample_payload_digest")
    matches = sample["readback_sha256"] == producer.PROFILE["fixture_sha256"]
    _require(sample["readback_matches"] is matches, "sample_payload_claim")
    unchanged = (baseline_ok and matches
        and all(_safe(row, allocation) for row in (*baseline.values(), *(sample[key] for key in ROWS)))
        and _same(baseline["held"], baseline["named"]) and not any(expected.values()))
    _require(sample["integrity_unchanged"] is unchanged, "sample_integrity_claim")
    return unchanged, {field for values in expected.values() for field in values}


def _validate_report(report, fixtures, probe_exit_code):
    _require(type(probe_exit_code) is int and 0 <= probe_exit_code <= 255, "probe_exit_code")
    _keys(report, REPORT_KEYS, "report_shape")
    _require(report["schema"] == "arv2-authorized-relocation-flags-v1"
             and report["fixture_mode"] == "authorized_relocation_synthetic_diagnostic"
             and report["source_profile_sha256"] == PROFILE_SHA256
             and _same(report["source_profile"], producer.RELOCATION_PROFILE)
             and producer.RELOCATION_PROFILE_SHA256 == PROFILE_SHA256
             and hashlib.sha256(audit._json_bytes(report["source_profile"])).hexdigest() == PROFILE_SHA256,
             "report_profile")
    _require(report["synthetic_only"] is True and all(report[key] is False for key in FALSE_FLAGS),
             "report_flags")
    _require(type(report["maximum_seconds"]) is int and report["maximum_seconds"] == MAX_PROBE_SECONDS
             and _number(report["elapsed_seconds"]) and type(report["complete"]) is bool
             and type(report["flags_available"]) is bool, "report_timing_shape")
    _require(type(report["cases"]) is list and len(report["cases"]) == 2, "report_cases")
    _keys(fixtures, CASES, "fixture_cases")
    initial_refused = observation_refused = 0
    all_flags = all_timings = final_matches = True
    changed_fields, checks, ordered_times = {}, [], {}
    for name, case in zip(CASES, report["cases"], strict=True):
        _keys(case, {"case", "allocation", "baseline", "initial_verification",
                    "baseline_integrity_unchanged", "observations", "baseline_reset"}, "case_shape")
        _require(case["case"] == name and case["baseline_reset"] is False, "case_identity")
        _keys(case["allocation"], {"dev", "ino", "gid"}, "case_allocation")
        allocation = case["allocation"]
        _require(all(type(item) is int and item >= 0 for item in allocation.values())
                 and allocation["dev"] == DEVICE, "case_allocation")
        baseline = case["baseline"]
        _keys(baseline, {"held", "named"}, "case_baseline")
        for row in baseline.values():
            _sample_metadata(row)
        initial_ok, changed = _check_sample(case["initial_verification"], baseline, allocation)
        _require(case["baseline_integrity_unchanged"] is initial_ok, "case_baseline_claim")
        checks.append(case["initial_verification"])
        initial_refused += not initial_ok
        _require(type(case["observations"]) is list and len(case["observations"]) == len(OFFSETS),
                 "case_observations")
        previous = -1
        for index, (offset, sample) in enumerate(zip(OFFSETS, case["observations"], strict=True)):
            passed, fields = _check_sample(sample, baseline, allocation, baseline_ok=initial_ok, timed=True)
            observation_refused += not passed
            changed.update(fields)
            checks.append(sample)
            _require(_same(sample["offset_seconds"], offset) and _number(sample["elapsed_seconds"])
                     and _number(sample["global_elapsed_seconds"]) and type(sample["within_deadline"]) is bool
                     and offset <= sample["elapsed_seconds"] <= sample["global_elapsed_seconds"]
                     and sample["elapsed_seconds"] >= previous, "sample_timing")
            previous = sample["elapsed_seconds"]
            ordered_times[(index, name)] = sample["global_elapsed_seconds"]
            _require(sample["global_elapsed_seconds"] <= report["elapsed_seconds"], "sample_report_timing")
            all_timings = all_timings and sample["within_deadline"] and sample["global_elapsed_seconds"] <= MAX_PROBE_SECONDS
        changed_fields[name] = sorted(changed)
        _sample_metadata(fixtures[name])
        final_matches = final_matches and _safe(fixtures[name], allocation) and all(
            _same(fixtures[name], row) for row in (*baseline.values(),
            case["observations"][-1]["held_after_read"], case["observations"][-1]["named_after_read"]))
    times = [ordered_times[(index, name)] for index in range(len(OFFSETS)) for name in CASES]
    _require(times == sorted(times), "sample_round_robin_timing")
    _require(all(type(report[key]) is int and report[key] == value for key, value in {
        "case_count": 2, "initial_verification_count": 2, "observation_count": 22,
        "refused_initial_integrity_count": initial_refused,
        "refused_integrity_observation_count": observation_refused}.items()), "report_counts")
    flags_available = all(sample["held"]["flags"] is not None for sample in checks)
    _require(report["flags_available"] is flags_available, "report_flags_available_claim")
    all_flags = all(row["flags"] is not None for case in report["cases"] for row in case["baseline"].values())
    all_flags = all_flags and all(sample[key]["flags"] is not None for sample in checks for key in ROWS)
    accepted = (probe_exit_code == 0 and report["complete"] and flags_available and all_flags
                and all_timings and report["elapsed_seconds"] <= MAX_PROBE_SECONDS
                and initial_refused == observation_refused == 0 and final_matches)
    return {"diagnostic_accepted": accepted, "case_count": 2, "initial_verification_count": 2, "observation_count": 22,
            "integrity_check_count": 24, "refused_initial_integrity_count": initial_refused,
            "refused_integrity_observation_count": observation_refused, "changed_fields": changed_fields,
            "complete": report["complete"], "flags_available": flags_available,
            "bounded_schedule_passed": all_timings and report["elapsed_seconds"] <= MAX_PROBE_SECONDS,
            "final_fixtures_match_original_baselines": final_matches}


def authenticate_report(expected_digest, probe_exit_code):
    raw, fixtures = _read_envelope(expected_digest)
    report = _strict_json(raw)
    result = _validate_report(report, fixtures, probe_exit_code)
    return {"schema": "arv2-publication-probe-authentication-v1", "report_authenticated": True,
            "report_sha256": expected_digest, "report_size": len(raw), "source_profile_sha256": PROFILE_SHA256,
            "fixture_sha256": producer.PROFILE["fixture_sha256"], "probe_exit_code": probe_exit_code,
            **result, "production_publication_clearance": False, "continuous_stability_proven": False,
            "native_attributes_authenticated": False, "source_objects_read": False}


def _gate(expected_profile):
    _require(Path.cwd() == ROOT and Path(__file__).resolve().parents[1] == ROOT
             and producer.RELOCATION_ROOT == ROOT and producer.RELOCATION_ARTIFACT_PATH == OUTPUT,
             "verification_fixed_root")
    _require(sys.platform == "darwin" and hasattr(os.stat_result, "st_flags"), "verification_platform")
    _require(expected_profile == PROFILE_SHA256 == producer.RELOCATION_PROFILE_SHA256
             and hashlib.sha256(audit._json_bytes(producer.RELOCATION_PROFILE)).hexdigest() == PROFILE_SHA256
             and len(producer.probe.PAYLOAD) == 48, "verification_profile")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-profile-sha256", required=True)
    parser.add_argument("--expected-report-sha256", required=True)
    parser.add_argument("--probe-exit-code", type=int, required=True)
    args = parser.parse_args(argv)
    with _budget():
        _gate(args.expected_profile_sha256)
        result = authenticate_report(args.expected_report_sha256, args.probe_exit_code)
    print(audit._json_bytes(result).decode("ascii"), end="")
    return 0 if result["diagnostic_accepted"] else 1


def _entrypoint(argv=None):
    try:
        return main(argv)
    except Exception as error:
        code = getattr(error, "code", None)
        if (not isinstance(error, audit.Refusal) or type(code) is not str
                or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,159}", code) is None):
            code = "verification_operation_refused"
        print(audit._json_bytes({"schema": "arv2-publication-probe-verification-refusal-v1",
            "report_authenticated": False, "diagnostic_accepted": False, "refusal_code": code,
            "evidence_retained": True, "production_publication_clearance": False}).decode("ascii"),
            end="", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
