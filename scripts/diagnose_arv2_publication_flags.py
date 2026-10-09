"""Fixed synthetic stat/flags probe; no source inputs or integrity waiver."""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from scripts import diagnose_arv2_publication_metadata as probe

# The historical exclusive destination remains spent. This prospective source
# correction does not authorize another observation or reinterpret its v1 report.
ARTIFACT_PATH = probe.ARTIFACT_PATH.with_name("R266-20261008-A")
CASES = ("direct_final", "pending_link")
OFFSETS = (0, 0.01, 0.1, 0.5, 1, 2, 3, 5, 10, 20, 30)
MAX_SECONDS = 45
MAX_REPORT_BYTES = 256 * 1024
SCHEMA = "arv2-synthetic-publication-flags-v2"
STAT_FIELDS = ("dev", "ino", "size", "mtime_ns", "ctime_ns", "mode", "uid", "gid", "nlink",
               "regular", "flags", "birthtime_ns", "birthtime_seconds")
PROFILE = {"cases": list(CASES), "offsets_seconds": list(OFFSETS), "maximum_seconds": MAX_SECONDS,
           "stat_fields": list(STAT_FIELDS), "fixture_sha256": probe.sha256_bytes(probe.PAYLOAD),
           "allocation_policy": "exclusive_created_file_dev_ino_gid_pinned_before_write",
           "baseline_policy": "first_held_and_named_stat_before_any_read_never_reset",
           "xattr_acl_or_protection_queries": False, "metadata_changes_permitted": False}
PROFILE_SHA256 = probe.sha256_bytes(probe.canonical_json_bytes(PROFILE))

# Section 272 freezes one owner-authorized relocation trial. The historical
# R266 destination above stays spent; neither entry point accepts a free path.
RELOCATION_ROOT = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2")
RELOCATION_ARTIFACT_PATH = (RELOCATION_ROOT / "artifacts" / "analyst_revisions_v2" /
                            "publication_metadata" / "R272-20261009-A")
RELOCATION_PROFILE = {**PROFILE, "authorization_id": "ARV2OD272-A",
                      "authorized_root": str(RELOCATION_ROOT),
                      "artifact_relative_path": str(RELOCATION_ARTIFACT_PATH.relative_to(RELOCATION_ROOT))}
RELOCATION_PROFILE_SHA256 = probe.sha256_bytes(probe.canonical_json_bytes(RELOCATION_PROFILE))


def _metadata(info):
    return {**probe._metadata(info), "gid": info.st_gid, "flags": getattr(info, "st_flags", None),
            "birthtime_ns": getattr(info, "st_birthtime_ns", None),
            "birthtime_seconds": getattr(info, "st_birthtime", None)}


def _safe(row, allocated, links=1):
    return ((row["dev"], row["ino"], row["gid"]) == allocated and row["regular"] and row["mode"] == 0o600
            and row["uid"] == os.getuid() and row["nlink"] == links
            and row["size"] == len(probe.PAYLOAD))


def _sample(child, visitor, baseline, allocated, *, baseline_ok=True):
    held = _metadata(os.fstat(visitor))
    named = _metadata(os.stat("final.json", dir_fd=child, follow_symlinks=False))
    os.lseek(visitor, 0, os.SEEK_SET)
    payload = os.read(visitor, len(probe.PAYLOAD) + 1)
    after = _metadata(os.fstat(visitor))
    named_after = _metadata(os.stat("final.json", dir_fd=child, follow_symlinks=False))
    changed = {"held_changed": probe._changed(baseline["held"], after),
               "named_changed": probe._changed(baseline["named"], named_after),
               "during_read_held_changed": probe._changed(held, after),
               "during_read_named_changed": probe._changed(named, named_after),
               "held_named_mismatch": probe._changed(after, named_after)}
    matches = payload == probe.PAYLOAD
    return {"held": held, "named": named, "held_after_read": after, "named_after_read": named_after,
            **changed, "readback_sha256": probe.sha256_bytes(payload), "readback_matches": matches,
            "integrity_unchanged": baseline_ok and matches and all(_safe(row, allocated) for row in
                (baseline["held"], baseline["named"], held, named, after, named_after)) and
                baseline["held"] == baseline["named"] and not any(changed.values())}


def _establish(root, root_fd, name):
    probe._path_matches(root, root_fd)
    os.mkdir(name, 0o700, dir_fd=root_fd)
    child = probe.private._open_child_directory(root_fd, name, "synthetic flags fixture")
    writer = visitor = None
    try:
        leaf = "final.json" if name == "direct_final" else "pending.json"
        writer = probe.private._new_private_file(child, leaf, "synthetic flags writer")
        # A new file may inherit its directory's group rather than the process
        # group. Pin that allocated group, never a later rebaseline; the private
        # owner/mode and held/named equality requirements remain independent.
        allocated_metadata = _metadata(os.fstat(writer))
        allocated = tuple(allocated_metadata[key] for key in ("dev", "ino", "gid"))
        probe.private._write_all(writer, probe.PAYLOAD, "synthetic flags bytes")
        os.fsync(writer)
        if not all(_safe(_metadata(row), allocated) for row in
                   (os.fstat(writer), os.stat(leaf, dir_fd=child, follow_symlinks=False))):
            raise probe.private.SharadarCaptureError("synthetic flags allocation changed")
        os.close(writer)
        writer = None
        if name == "pending_link":
            os.link(leaf, "final.json", src_dir_fd=child, dst_dir_fd=child, follow_symlinks=False)
            if not _safe(_metadata(os.stat("final.json", dir_fd=child, follow_symlinks=False)), allocated, links=2):
                raise probe.private.SharadarCaptureError("synthetic flags linked allocation changed")
            os.unlink(leaf, dir_fd=child)  # Published final retains the synthetic fixture.
        probe.private._fsync(child, "synthetic flags child")
        probe.private._fsync(root_fd, "synthetic flags parent")
        visitor = probe.private._open_private_regular(child, "final.json", maximum=len(probe.PAYLOAD),
                                                      label="synthetic flags visitor")
        # Capture both original metadata snapshots before even the first payload read.
        baseline = {"held": _metadata(os.fstat(visitor)),
                    "named": _metadata(os.stat("final.json", dir_fd=child, follow_symlinks=False))}
        if not all(_safe(row, allocated) for row in baseline.values()):
            raise probe.private.SharadarCaptureError("synthetic flags visitor allocation changed")
        initial = _sample(child, visitor, baseline, allocated)
        result = {"case": name, "allocation": {"dev": allocated[0], "ino": allocated[1], "gid": allocated[2]},
                  "baseline": baseline, "initial_verification": initial,
                  "baseline_integrity_unchanged": initial["integrity_unchanged"],
                  "observations": [], "baseline_reset": False}
        return child, visitor, allocated, result
    except BaseException:
        if visitor is not None:
            os.close(visitor)
        os.close(child)
        raise
    finally:
        if writer is not None:
            os.close(writer)


def _run(path, monotonic, sleep, *, synthetic_test, relocation_trial=False):
    if relocation_trial and (synthetic_test or path != RELOCATION_ARTIFACT_PATH
            or Path(__file__).resolve().parents[1] != RELOCATION_ROOT
            or Path.cwd().resolve() != RELOCATION_ROOT):
        raise probe.private.SharadarCaptureError("authorized relocation root/path required")
    fixed_path = RELOCATION_ARTIFACT_PATH if relocation_trial else ARTIFACT_PATH
    if type(path) is not type(Path()) or (not synthetic_test and path != fixed_path):
        raise probe.private.SharadarCaptureError("synthetic flags production path is fixed")
    if synthetic_test and (not path.name.startswith("synthetic-test-") or path == ARTIFACT_PATH):
        raise probe.private.SharadarCaptureError("synthetic flags test path is not explicit")
    started = monotonic()
    _, parent = probe.private._open_directory_path(path.parent, create=True, name="synthetic flags parent")
    root_fd = None
    retained = []
    try:
        os.mkdir(path.name, 0o700, dir_fd=parent)
        root_fd = probe.private._open_child_directory(parent, path.name, "synthetic flags artifact")
        for name in CASES:
            if monotonic() >= started + MAX_SECONDS:
                break
            retained.append(_establish(path, root_fd, name))
        anchor = monotonic()  # Both original baselines already exist before round-robin sampling.
        for offset in OFFSETS:
            wait = max(0, anchor + offset - monotonic())
            if monotonic() + wait > started + MAX_SECONDS:
                break
            if wait:
                sleep(wait)
            for child, visitor, allocated, result in retained:
                if monotonic() >= started + MAX_SECONDS:
                    break
                probe._path_matches(path / result["case"], child)
                observed = _sample(child, visitor, result["baseline"], allocated,
                                   baseline_ok=result["baseline_integrity_unchanged"])
                result["observations"].append({"offset_seconds": offset,
                    "elapsed_seconds": monotonic() - anchor, "global_elapsed_seconds": monotonic() - started,
                    "within_deadline": monotonic() <= started + MAX_SECONDS, **observed})
        for child, _visitor, _allocated, result in retained:
            probe._path_matches(path / result["case"], child)
            probe.private._pinned_child(root_fd, result["case"], child, "retained synthetic flags fixture")
        cases = [row[3] for row in retained]
        observations = [row for case in cases for row in case["observations"]]
        checks = [case["initial_verification"] for case in cases] + observations
        report = {"schema": SCHEMA, "source_profile": PROFILE, "source_profile_sha256": PROFILE_SHA256,
                  "fixture_mode": "offline_test_double" if synthetic_test else "fixed_synthetic_diagnostic",
                  "cases": cases, "case_count": len(cases), "observation_count": len(observations),
                  "initial_verification_count": len(cases),
                  "refused_initial_integrity_count": sum(not row["initial_verification"]["integrity_unchanged"] for row in cases),
                  "refused_integrity_observation_count": sum(not row["integrity_unchanged"] for row in observations),
                  "complete": len(cases) == 2 and all(len(case["observations"]) == len(OFFSETS) for case in cases)
                      and all(row["within_deadline"] for row in observations) and monotonic() <= started + MAX_SECONDS,
                  "elapsed_seconds": monotonic() - started, "maximum_seconds": MAX_SECONDS,
                  "flags_available": bool(checks) and all(row["held"]["flags"] is not None for row in checks),
                  "synthetic_only": True, "production_integrity_waiver": False,
                  "proves_perpetual_stability": False, "provider_or_qc_contact": False,
                  "security_attributes_queried": False}
        if relocation_trial:
            report.update(schema="arv2-authorized-relocation-flags-v1",
                          source_profile=RELOCATION_PROFILE,
                          source_profile_sha256=RELOCATION_PROFILE_SHA256,
                          fixture_mode="authorized_relocation_synthetic_diagnostic")
        raw = probe.canonical_json_bytes(report)
        if len(raw) > MAX_REPORT_BYTES:
            raise probe.private.SharadarCaptureError("synthetic flags report exceeds byte limit")
        probe._path_matches(path, root_fd)
        probe.private._write_private_bytes(root_fd, "report.json", raw, "synthetic flags report")
        probe.private._fsync(root_fd, "synthetic flags report directory")
        probe.private._fsync(parent, "synthetic flags report parent")
        if probe.private._read_private_bytes(root_fd, "report.json", maximum=MAX_REPORT_BYTES,
                                             label="synthetic flags report readback") != raw:
            raise probe.private.SharadarCaptureError("synthetic flags report readback changed")
        probe._path_matches(path, root_fd)
        probe.private._pinned_child(parent, path.name, root_fd, "synthetic flags artifact")
        return report, probe.sha256_bytes(raw)
    finally:
        for child, visitor, _allocated, _result in retained:
            os.close(visitor)
            os.close(child)
        if root_fd is not None:
            os.close(root_fd)
        os.close(parent)


def _diagnose_publication_flags_for_test(path, monotonic, sleep):
    return _run(path, monotonic, sleep, synthetic_test=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorized-relocation-r272", action="store_true")
    args = parser.parse_args(argv)
    try:
        path = RELOCATION_ARTIFACT_PATH if args.authorized_relocation_r272 else ARTIFACT_PATH
        options = {"relocation_trial": True} if args.authorized_relocation_r272 else {}
        report, digest = _run(path, time.monotonic, time.sleep, synthetic_test=False, **options)
        print(f"cases={report['case_count']} observations={report['observation_count']} "
              f"initial_checks={report['initial_verification_count']} refused_initial={report['refused_initial_integrity_count']} "
              f"refused_integrity={report['refused_integrity_observation_count']} "
              f"complete={str(report['complete']).lower()} report_sha256={digest}")
        return 0
    except Exception:
        print("synthetic flags diagnostic refused; all allocated fixtures retained", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
