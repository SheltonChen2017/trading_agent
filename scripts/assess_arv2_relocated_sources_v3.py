"""Fixed read-only v3 candidate; independent review and run authority are external.

A matching profile pin authenticates a declared contract, not its approval.
Neither this entry point nor a retained complete report grants permission to
run, publish production sources, contact a provider or launch QuantConnect.
The spent R273/R277 identities and all v1/v2 implementations remain unchanged.
The accepted device-ID projection is prospective, never historical continuity.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import signal
import stat
import sys
import time

from scripts import assess_arv2_relocated_sources as v1
from scripts import audit_arv2_relocation as audit
from scripts import arv2_relocation_security_v3 as policy

ROOT = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2")
OUTPUT = ROOT / "artifacts/analyst_revisions_v2/relocation_trial/R279-20261010-A"
SCHEMA = "arv2-relocated-source-fresh-use-v3"
PREFLIGHT_SCHEMA = "arv2-relocated-source-prefreeze-v3"
PREFLIGHT_SECONDS = 15
ASSESSMENT_SECONDS = 60
EXPECTED_FILES = 15
EXPECTED_DIRECTORIES = 12
MAX_REPORT_BYTES = 128 * 1024
_require = v1._require
METADATA_FIELDS = frozenset(("dev", "ino", "mode", "uid", "gid", "nlink", "size",
                             "mtime_ns", "ctime_ns", "flags"))


def profile():
    """Fresh JSON contract; source-code hashes are frozen separately in Git."""
    return {
        "schema": SCHEMA, "preflight_schema": PREFLIGHT_SCHEMA,
        "mode": "offline-read-only-source-reauthentication",
        "root": str(ROOT), "output": str(OUTPUT), "policy": policy.policy_record(),
        "source_device_projection": _projection_contract(),
        "source_packages": {path: list(leaves) for path, leaves in v1.PACKAGES.items()},
        "manifest_pins": dict(v1.MANIFESTS),
        "before_report_sha256": v1.BEFORE_SHA, "after_report_sha256": v1.AFTER_SHA,
        "expected_files": EXPECTED_FILES, "expected_directories": EXPECTED_DIRECTORIES,
        "preflight_seconds": PREFLIGHT_SECONDS, "assessment_seconds": ASSESSMENT_SECONDS,
        "budget_kind": "cooperative-signal-and-return-check-not-hard-native-interruption",
        "attempt_protocol": "one-exclusive-fsynced-directory-before-source-reads-no-cleanup-no-retry",
        "publication_protocol": "late-private-pending-exclusive-link-readback-strict-v1-helper",
        "output_security_scope": "metadata-and-private-mode-not-ACL-or-xattr-envelope",
        "acceptance": "authenticated-report-and-successful-exit-and-final-output-verification",
        "independent_review_required_before_assessment": True,
        "separately_recorded_run_authority_required": True,
        "baseline_acceptance_is_not_run_authority": True,
        "historical_audit_accepted": False, "historical_security_equivalence": False,
        "continuous_stability_proven": False, "all_worktree_artifacts_executable": False,
        "formal_admission": False, "production_publication_authorized": False,
        "provider_or_qc_contact": False,
    }


def _source_keys():
    return frozenset(package + "/" + leaf
                     for package, leaves in v1.PACKAGES.items() for leaf in leaves)


def _projection_contract():
    return {"historical_device": policy.HISTORICAL_DEVICE,
            "prospective_device": policy.PROSPECTIVE_DEVICE,
            "source_paths": sorted(_source_keys()), "source_count": EXPECTED_FILES,
            "current_device_scope": "12-directories-15-source-files-and-output-allocation",
            "changed_metadata_fields": ["dev"],
            "purpose": "fixed-source-fresh-use-only",
            "historical_device_continuity_proven": False,
            "historical_evidence_modified": False,
            "other_metadata_waived": False}


def _require_device(meta, code):
    _require(type(meta.get("dev")) is int
             and meta["dev"] == policy.PROSPECTIVE_DEVICE, code)


def _validate_source_scope(expected, device, code):
    _require(type(expected) is dict and len(expected) == EXPECTED_FILES
             and set(expected) == _source_keys(), code + "_paths")
    for row in expected.values():
        _require(type(row) is dict and row.get("kind") == "file", code + "_row")
        meta = row.get("metadata")
        _require(type(meta) is dict and set(meta) == METADATA_FIELDS
                 and all(type(value) is int for value in meta.values()),
                 code + "_metadata")
        _require(meta["dev"] == device, code + "_device")
        _require(type(row.get("sha256")) is str and len(row["sha256"]) == 64
                 and set(row["sha256"]) <= set("0123456789abcdef"), code + "_hash")


def _project_sources(historical):
    """Copy exactly the pinned 15 historical rows, changing only device ID.

    A changed prospective baseline does not authenticate the cause of the
    identity change or restore the failed historical preservation result.
    """
    _validate_source_scope(historical, policy.HISTORICAL_DEVICE, "historical_projection")
    original_digest = hashlib.sha256(audit._json_bytes(historical)).hexdigest()
    projected = deepcopy(historical)
    for row in projected.values():
        row["metadata"]["dev"] = policy.PROSPECTIVE_DEVICE
    _validate_source_scope(projected, policy.PROSPECTIVE_DEVICE, "prospective_projection")
    _require(hashlib.sha256(audit._json_bytes(historical)).hexdigest() == original_digest,
             "historical_projection_input_changed")
    receipt = {**_projection_contract(),
               "historical_rows_sha256": original_digest,
               "prospective_rows_sha256": hashlib.sha256(audit._json_bytes(projected)).hexdigest()}
    return projected, receipt


def profile_sha256():
    return hashlib.sha256(audit._json_bytes(profile())).hexdigest()


@contextmanager
def _budget(seconds):
    """Bound cooperative work; a blocked native call may return after its budget."""
    started = time.monotonic()
    previous_delay, previous_interval = signal.getitimer(signal.ITIMER_REAL)
    _require(previous_interval == 0, "periodic_alarm_not_supported")
    previous_handler = signal.getsignal(signal.SIGALRM)

    def expired(_signum, _frame):
        raise audit.Refusal("cooperative_budget_exceeded")

    delay = min(seconds, previous_delay) if previous_delay else seconds
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, delay)
    try:
        yield
        elapsed = time.monotonic() - started
        _require(elapsed <= delay, "cooperative_budget_exceeded")
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_delay:
            remaining = previous_delay - (time.monotonic() - started)
            if remaining > 0:
                signal.setitimer(signal.ITIMER_REAL, remaining)


def _paths():
    files = {ROOT / package / leaf for package, leaves in v1.PACKAGES.items() for leaf in leaves}
    directories = {ROOT.parent, ROOT}
    for source in files:
        _require(source.is_relative_to(ROOT), "source_scope_outside_root")
        path = source.parent
        while path != ROOT:
            directories.add(path)
            path = path.parent
    _require(len(files) == EXPECTED_FILES and len(directories) == EXPECTED_DIRECTORIES,
             "source_scope_count")
    return sorted(directories, key=lambda p: (len(p.parts), str(p))), sorted(files)


def _directory_secure(meta, path, root=None):
    root = ROOT if root is None else root
    return (stat.S_ISDIR(meta["mode"]) and meta["uid"] == os.getuid()
            and stat.S_IMODE(meta["mode"]) == (0o755 if path == root else 0o700)
            and type(meta["flags"]) is int
            and not meta["flags"] & ~(stat.UF_TRACKED | stat.UF_HIDDEN))


def _check_names(path, names):
    if path == policy.VINTAGE_PATH:
        _require(names == tuple(name for name, _size, _digest in policy.XATTR_PINS),
                 "preflight_vintage_names")
    else:
        _require(set(names) <= policy.legacy.ALLOWED_XATTRS, "preflight_other_names")


def _named_metadata(path, held_dirs):
    if path in held_dirs:
        check = audit._open_absolute_directory(path)
        try:
            return audit._metadata(os.fstat(check))
        finally:
            os.close(check)
    return audit._metadata(os.stat(path.name, dir_fd=held_dirs[path.parent], follow_symlinks=False))


def preflight_scope():
    """One metadata-only 27-object observation; never allocate or read source bytes.

    All names are checked before the four vintage values. Only this directory
    receives a value observation here. Checks sample endpoints, not continuity.
    """
    started = time.monotonic()
    with _budget(PREFLIGHT_SECONDS), ExitStack() as stack:
        directories, files = _paths()
        held_dirs, objects = {}, {}
        native = policy.legacy._native()
        for path in directories:
            fd = audit._open_absolute_directory(path)
            stack.callback(os.close, fd)
            meta = audit._metadata(os.fstat(fd))
            _require_device(meta, "preflight_directory_device")
            _require(_directory_secure(meta, path), "preflight_directory_security")
            held_dirs[path] = fd
            _require(meta == _named_metadata(path, held_dirs), "preflight_named_directory")
            objects[path] = (fd, meta)
        for path in files:
            parent = held_dirs[path.parent]
            named = audit._metadata(os.stat(path.name, dir_fd=parent, follow_symlinks=False))
            _require_device(named, "preflight_source_device")
            _require(v1._private_file(named), "preflight_private_regular_required")
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            stack.callback(os.close, fd)
            meta = audit._metadata(os.fstat(fd))
            _require(meta == named and v1._private_file(meta), "preflight_open_identity")
            objects[path] = (fd, meta)
        names_by_path = {}
        for path, (fd, _meta) in objects.items():
            names = policy._names(native, fd)
            _check_names(path, names)
            names_by_path[path] = names
        _require(policy.VINTAGE_PATH in held_dirs, "preflight_vintage_outside_scope")
        _require(objects[policy.VINTAGE_PATH][1] == dict(policy.VINTAGE_METADATA),
                 "preflight_vintage_metadata")
        vintage_security = policy.snapshot(held_dirs[policy.VINTAGE_PATH])
        for path, (fd, meta) in objects.items():
            _require(meta == audit._metadata(os.fstat(fd)) == _named_metadata(path, held_dirs),
                     "preflight_metadata_changed")
            _require(policy._names(native, fd) == names_by_path[path], "preflight_names_changed")
            _require(meta == audit._metadata(os.fstat(fd)) == _named_metadata(path, held_dirs),
                     "preflight_metadata_changed_after_names")
        inventory = {str(path.relative_to(ROOT.parent)): {
            "metadata": meta, "names": [name.decode("ascii") for name in names_by_path[path]]}
            for path, (_fd, meta) in objects.items()}
    return {"schema": PREFLIGHT_SCHEMA, "profile_sha256": profile_sha256(),
            "policy_id": policy.POLICY_ID, "directory_count": len(directories),
            "file_count": len(files), "inventory": inventory,
            "vintage_security": vintage_security, "elapsed_seconds": time.monotonic() - started,
            "source_contents_read": False, "source_reauthenticated": False,
            "output_allocated_by_preflight": False, "continuous_stability_proven": False,
            "formal_admission": False, "production_publication_authorized": False}


def _guarded_consume(root, expected, consume, snapshot):
    """V3 retains v2 guards and compares full prospective projected metadata.

    A separate stat and open cannot eliminate syscall-boundary races. The held
    object must match both that sampled name and the exact projected row.
    """
    _validate_source_scope(expected, policy.PROSPECTIVE_DEVICE, "guarded_projection")
    with ExitStack() as stack:
        held_dirs = {}
        directories = {root.parent, root}
        for relative in expected:
            path = (root / relative).parent
            while path != root:
                directories.add(path)
                path = path.parent
        for path in sorted(directories, key=lambda p: (len(p.parts), str(p))):
            fd = audit._open_absolute_directory(path)
            stack.callback(os.close, fd)
            meta = audit._metadata(os.fstat(fd))
            _require_device(meta, "current_directory_device")
            _require(_directory_secure(meta, path, root), "current_directory_security")
            secured = snapshot(fd)
            _require(meta == audit._metadata(os.fstat(fd)), "directory_changed_during_security_read")
            held_dirs[path] = (fd, meta, secured)
        held_files = {}
        for relative, prior in sorted(expected.items()):
            path = root / relative
            parent = held_dirs[path.parent][0]
            named = audit._metadata(os.stat(path.name, dir_fd=parent, follow_symlinks=False))
            _require(named == prior["metadata"] and v1._private_file(named), "source_preopen_identity")
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            stack.callback(os.close, fd)
            meta = audit._metadata(os.fstat(fd))
            _require(meta == named == prior["metadata"] and v1._private_file(meta), "current_source_metadata_changed")
            _require(meta == audit._metadata(os.stat(path.name, dir_fd=parent, follow_symlinks=False)),
                     "current_source_named_identity")
            secured = snapshot(fd)
            _require(v1._digest_held(fd, meta["size"]) == prior["sha256"], "current_source_hash")
            _require(meta == audit._metadata(os.fstat(fd)), "source_changed_during_initial_read")
            held_files[relative] = (fd, meta, secured)
        result = consume()
        for relative, (fd, meta, secured) in held_files.items():
            path = root / relative
            parent = held_dirs[path.parent][0]
            _require(meta == audit._metadata(os.fstat(fd))
                     == audit._metadata(os.stat(path.name, dir_fd=parent, follow_symlinks=False)),
                     "source_changed_across_consumer")
            _require(secured == snapshot(fd), "source_security_changed_across_consumer")
            _require(v1._digest_held(fd, meta["size"]) == expected[relative]["sha256"], "source_hash_after_consumer")
            _require(meta == audit._metadata(os.fstat(fd))
                     == audit._metadata(os.stat(path.name, dir_fd=parent, follow_symlinks=False)),
                     "source_changed_during_final_read")
        for path, (fd, meta, secured) in reversed(tuple(held_dirs.items())):
            check = audit._open_absolute_directory(path)
            try:
                _require(meta == audit._metadata(os.fstat(fd)) == audit._metadata(os.fstat(check)),
                         "directory_changed_across_consumer")
                _require(secured == snapshot(fd), "directory_security_changed_across_consumer")
                _require(meta == audit._metadata(os.fstat(fd)), "directory_changed_during_final_security")
            finally:
                os.close(check)
        return {"loader_results": result, "file_count": len(held_files), "directory_count": len(held_dirs),
                "directory_metadata": {str(path.relative_to(root.parent)): meta
                                       for path, (_fd, meta, _secure) in held_dirs.items()},
                "security_observations": {str(path.relative_to(root.parent)): secure
                                          for path, (_fd, _meta, secure) in held_dirs.items()},
                "file_security_observations": {path: secure for path, (_fd, _meta, secure) in held_files.items()}}


def _assess(expected_profile):
    parent = audit._open_absolute_directory(OUTPUT.parent)
    output = None
    try:
        _require_device(audit._metadata(os.fstat(parent)), "assessment_parent_device")
        os.mkdir(OUTPUT.name, 0o700, dir_fd=parent)
        named = audit._metadata(os.stat(OUTPUT.name, dir_fd=parent, follow_symlinks=False))
        output = os.open(OUTPUT.name, audit._directory_flags(), dir_fd=parent)
        _require_device(named, "assessment_directory_device")
        _require(named == audit._metadata(os.fstat(output)) and stat.S_ISDIR(named["mode"])
                 and named["uid"] == os.getuid() and stat.S_IMODE(named["mode"]) == 0o700,
                 "assessment_directory_security")
        allocated = named
        os.fsync(output)
        os.fsync(parent)
        _require(allocated == audit._metadata(os.fstat(output))
                 == audit._metadata(os.stat(OUTPUT.name, dir_fd=parent, follow_symlinks=False)),
                 "assessment_directory_changed_during_claim")
        _require(os.listdir(output) == [], "assessment_directory_not_empty_at_claim")
        report = {"schema": SCHEMA, "profile_sha256": expected_profile, "policy_id": policy.POLICY_ID,
                  "policy": policy.policy_record(), "source_device_projection": _projection_contract(),
                  "before_report_sha256": v1.BEFORE_SHA,
                  "after_report_sha256": v1.AFTER_SHA, "source_reauthenticated": False, "complete": False,
                  "historical_audit_accepted": False, "historical_security_equivalence": False,
                  "continuous_stability_proven": False, "all_worktree_artifacts_executable": False,
                  "formal_admission": False, "production_publication_authorized": False,
                  "provider_or_qc_contact": False,
                  "output_acl_xattr_envelope_proven": False}
        try:
            report["preflight"] = preflight_scope()
            before, after = v1._read_pinned_reports(ROOT)
            expected, projection = _project_sources(v1._scope(before, after))
            report["source_metadata_projection"] = projection
            report.update(_guarded_consume(ROOT, expected, v1._load_sources, policy.snapshot))
            _require(profile_sha256() == expected_profile, "profile_changed_across_assessment")
            report.update(source_reauthenticated=True, complete=True)
        except Exception as error:
            report["refusal_type"] = type(error).__name__
            report["refusal_code"] = error.code if isinstance(error, (audit.Refusal, policy.legacy.Refusal)) else "current_security_or_source_refused"
        raw = audit._json_bytes(report)
        _require(len(raw) <= MAX_REPORT_BYTES, "assessment_report_size")
        audit._assert_root(OUTPUT.parent, parent)
        _require(allocated == audit._metadata(os.fstat(output))
                 == audit._metadata(os.stat(OUTPUT.name, dir_fd=parent, follow_symlinks=False)),
                 "assessment_directory_changed")
        _require(os.listdir(output) == [], "assessment_directory_not_empty")
        digest = audit._publish_report(output, "report.json", raw)
        audit._assert_root(OUTPUT.parent, parent)
        published = {key: allocated[key] for key in audit.DIRECTORY_FIELDS}
        published["nlink"] += 1
        _require(published == audit._directory_metadata(os.fstat(output))
                 == audit._directory_metadata(os.stat(OUTPUT.name, dir_fd=parent, follow_symlinks=False)),
                 "assessment_directory_changed_after_publication")
        _require(os.listdir(output) == ["report.json"], "assessment_directory_extra_entry")
        return report, digest
    finally:
        if output is not None:
            os.close(output)
        os.close(parent)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight-only", action="store_true")
    mode.add_argument("--assess", action="store_true")
    parser.add_argument("--expected-profile-sha256", required=True)
    args = parser.parse_args(argv)
    _require(Path.cwd() == ROOT and Path(__file__).resolve().parents[1] == ROOT
             and v1.ROOT == ROOT and policy.VINTAGE_PATH == ROOT / v1.VINTAGE, "fixed_root_required")
    v1._require_supported_platform()
    _require(args.expected_profile_sha256 == profile_sha256(), "profile_pin_mismatch")
    if args.preflight_only:
        report = preflight_scope()
        _require(report["profile_sha256"] == args.expected_profile_sha256, "profile_changed_during_preflight")
        print(audit._json_bytes(report).decode("ascii"), end="")
        return 0
    with _budget(ASSESSMENT_SECONDS):
        report, digest = _assess(args.expected_profile_sha256)
    print(f"complete={str(report['complete']).lower()} sources_reauthenticated={str(report['source_reauthenticated']).lower()} report_sha256={digest}")
    return 0 if report["complete"] and report["source_reauthenticated"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("fixed v3 assessment/preflight refused; any allocated evidence retained", file=sys.stderr)
        raise SystemExit(1)
