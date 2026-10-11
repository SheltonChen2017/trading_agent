"""Bounded synthetic publication metadata probe; never relax production guards."""
from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

from scripts import capture_arv2_sharadar as private
from research.analyst_revisions_v2.canonical import canonical_json_bytes, sha256_bytes

ARTIFACT_PATH = (private.REPOSITORY_ARTIFACTS_ROOT / "analyst_revisions_v2" /
                 "publication_metadata" / "R264-20261008-A")
PAYLOAD = canonical_json_bytes({"fixture": "synthetic-publication-metadata-v1"})
VARIANTS = ("direct_final", "pending_link", "pending_link_final_fsync")
OFFSETS = (0, 0.01, 0.1, 0.5, 1, 2)
MAX_SECONDS = 30
MAX_REPORT_BYTES = 256 * 1024


def _metadata(info):
    return {"dev": info.st_dev, "ino": info.st_ino, "size": info.st_size,
            "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns,
            "mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid,
            "nlink": info.st_nlink, "regular": stat.S_ISREG(info.st_mode)}


def _changed(before, after):
    return [name for name in before if before[name] != after[name]]


def _path_matches(path, descriptor):
    _, reopened = private._open_directory_path(path, create=False, name="named synthetic directory")
    try:
        if private._directory_identity(os.fstat(reopened)) != private._directory_identity(os.fstat(descriptor)):
            raise private.SharadarCaptureError("synthetic directory pathname changed")
    finally:
        os.close(reopened)


def _provenance(descriptor, path, deadline, monotonic):
    """Return only fixed-name presence; never inspect/persist attribute values."""
    if monotonic() >= deadline:
        return None
    try:
        before = _metadata(os.fstat(descriptor))
        if before != _metadata(os.stat(path, follow_symlinks=False)):
            return None
        if callable(getattr(os, "listxattr", None)):
            present = "com.apple.provenance" in os.listxattr(descriptor)
        else:
            timeout = min(0.5, max(0, deadline - monotonic()))
            if timeout <= 0:
                return None
            result = subprocess.run(["/usr/bin/xattr", "-s", str(path)], stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, timeout=timeout, check=False)
            present = (b"com.apple.provenance" in result.stdout.splitlines()
                       if result.returncode == 0 and len(result.stdout) <= 8192 else None)
        if (before == _metadata(os.fstat(descriptor))
                == _metadata(os.stat(path, follow_symlinks=False))):
            return present
    except (OSError, subprocess.TimeoutExpired, TypeError):
        pass
    return None


def _step(directory, leaf, name):
    return {"step": name, "named": _metadata(os.stat(leaf, dir_fd=directory,
                                                     follow_symlinks=False))}


def _sample(directory, descriptor):
    held = _metadata(os.fstat(descriptor))
    named = _metadata(os.stat("final.json", dir_fd=directory, follow_symlinks=False))
    os.lseek(descriptor, 0, os.SEEK_SET)
    payload = os.read(descriptor, len(PAYLOAD) + 1)
    held_after = _metadata(os.fstat(descriptor))
    named_after = _metadata(os.stat("final.json", dir_fd=directory, follow_symlinks=False))
    return {"held": held, "named": named, "held_after_read": held_after,
            "named_after_read": named_after, "readback_sha256": sha256_bytes(payload),
            "readback_matches": payload == PAYLOAD,
            "during_read_held_changed": _changed(held, held_after),
            "during_read_named_changed": _changed(named, named_after)}


def _comparison(baseline, baseline_ok, current):
    held = _changed(baseline["held"], current["held_after_read"])
    named = _changed(baseline["named"], current["named_after_read"])
    mismatch = _changed(current["held_after_read"], current["named_after_read"])
    safe = all(row["regular"] and row["mode"] == 0o600 and row["nlink"] == 1 and
               row["uid"] == os.getuid() for row in (current["held_after_read"], current["named_after_read"]))
    return {"held_changed": held, "named_changed": named, "held_named_mismatch": mismatch,
            "integrity_unchanged": baseline_ok and safe and current["readback_matches"] and not
            (held or named or mismatch or current["during_read_held_changed"] or current["during_read_named_changed"])}


def _case(root, root_fd, variant, repetition, monotonic, sleep, deadline):
    _path_matches(root, root_fd)
    name = f"{variant}-{repetition}"
    os.mkdir(name, 0o700, dir_fd=root_fd)  # Exclusive; never overwrite or clean up.
    child = private._open_child_directory(root_fd, name, "synthetic fixture")
    descriptor = None
    try:
        steps = []
        leaf = "final.json" if variant == "direct_final" else "pending.json"
        # Match the existing writer's write/fsync/CLOSE lifecycle exactly.
        private._write_private_bytes(child, leaf, PAYLOAD, "synthetic fixture")
        steps.append(_step(child, leaf, "writer_closed_after_file_fsync"))
        if variant != "direct_final":
            os.link("pending.json", "final.json", src_dir_fd=child,
                    dst_dir_fd=child, follow_symlinks=False)
            steps.append(_step(child, "final.json", "final_linked"))
            os.unlink("pending.json", dir_fd=child)  # Retained final owns the same bytes.
            steps.append(_step(child, "final.json", "pending_unlinked"))
        private._fsync(child, "synthetic child")
        private._fsync(root_fd, "synthetic parent")
        steps.append(_step(child, "final.json", "directories_fsynced"))
        if variant == "pending_link_final_fsync":
            sync_fd = private._open_private_regular(child, "final.json", maximum=len(PAYLOAD),
                                                    label="synthetic final sync")
            try:
                private._fsync(sync_fd, "synthetic final")
            finally:
                os.close(sync_fd)
            steps.append(_step(child, "final.json", "extra_final_fsync_closed"))
        descriptor = private._open_private_regular(child, "final.json", maximum=len(PAYLOAD),
                                                   label="synthetic read-only visitor")
        baseline = _sample(child, descriptor)
        baseline_ok = (not baseline["during_read_held_changed"]
                       and not baseline["during_read_named_changed"]
                       and baseline["held"] == baseline["named"]
                       and baseline["readback_matches"] and
                       all(row["regular"] and row["mode"] == 0o600 and row["nlink"] == 1 and
                           row["uid"] == os.getuid() for row in (baseline["held"], baseline["named"])))
        started = monotonic()
        _path_matches(root / name, child)
        private._pinned_child(root_fd, name, child, "synthetic provenance fixture")
        provenance_before = _provenance(descriptor, root / name / "final.json", deadline, monotonic)
        observations = []
        for offset in OFFSETS:
            remaining = max(0, started + offset - monotonic())
            if monotonic() + remaining > deadline:
                break
            if remaining:
                sleep(remaining)
            _path_matches(root / name, child)
            current = _sample(child, descriptor)
            observed_at = monotonic()
            if observed_at > deadline:
                break
            observations.append({"offset_seconds": offset, "elapsed_seconds": observed_at - started, **current,
                                 **_comparison(baseline, baseline_ok, current)})
        _path_matches(root / name, child)
        private._pinned_child(root_fd, name, child, "synthetic provenance fixture")
        provenance_after = _provenance(descriptor, root / name / "final.json", deadline, monotonic)
        _path_matches(root / name, child)
        final = _sample(child, descriptor)
        verification = {**final, **_comparison(baseline, baseline_ok, final)}
        private._pinned_child(root_fd, name, child, "retained synthetic fixture")
        return {"variant": variant, "repetition": repetition, "steps": steps,
                "baseline": baseline, "observations": observations,
                "baseline_integrity_unchanged": baseline_ok,
                "provenance_before": provenance_before, "provenance_after": provenance_after,
                "final_verification": verification, "final_integrity_unchanged": verification["integrity_unchanged"],
                "complete": len(observations) == len(OFFSETS) and monotonic() <= deadline, "diagnostic_only": True}
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(child)


def _run(path, monotonic, sleep):
    started = monotonic()
    _, parent = private._open_directory_path(path.parent, create=True, name="metadata artifact parent")
    root_fd = None
    try:
        os.mkdir(path.name, 0o700, dir_fd=parent)
        root_fd = private._open_child_directory(parent, path.name, "metadata artifact")
        cases = []
        for variant in VARIANTS:
            for repetition in range(1, 4):
                if monotonic() >= started + MAX_SECONDS or (cases and not cases[-1]["complete"]):
                    break
                cases.append(_case(path, root_fd, variant, repetition, monotonic,
                                   sleep, started + MAX_SECONDS))
        observations = [row for case in cases for row in case["observations"]]
        report = {"schema": "arv2-synthetic-publication-metadata-v1", "cases": cases,
                  "case_count": len(cases), "observation_count": len(observations),
                  "refused_integrity_observation_count": sum(not row["integrity_unchanged"] for row in observations),
                  "final_verification_count": len(cases),
                  "refused_final_integrity_count": sum(not case["final_integrity_unchanged"] for case in cases),
                  "complete": len(cases) == 9 and all(case["complete"] for case in cases),
                  "elapsed_seconds": monotonic() - started, "maximum_seconds": MAX_SECONDS,
                  "maximum_observation_seconds_per_fixture": 2, "synthetic_payload_sha256": sha256_bytes(PAYLOAD),
                  "synthetic_only": True, "production_integrity_waiver": False,
                  "proves_perpetual_stability": False, "provider_or_qc_contact": False}
        raw = canonical_json_bytes(report)
        if len(raw) > MAX_REPORT_BYTES:
            raise private.SharadarCaptureError("synthetic report exceeds byte limit")
        _path_matches(path, root_fd)
        private._write_private_bytes(root_fd, "report.json", raw, "synthetic report")
        private._fsync(root_fd, "synthetic report directory")
        private._fsync(parent, "synthetic report parent")
        if private._read_private_bytes(root_fd, "report.json", maximum=MAX_REPORT_BYTES,
                                        label="synthetic report readback") != raw:
            raise private.SharadarCaptureError("synthetic report readback changed")
        private._pinned_child(parent, path.name, root_fd, "synthetic report artifact")
        _path_matches(path, root_fd)
        return report, sha256_bytes(raw)
    finally:
        if root_fd is not None:
            os.close(root_fd)
        os.close(parent)


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    try:
        report, digest = _run(ARTIFACT_PATH, time.monotonic, time.sleep)
        print(f"cases={report['case_count']} observations={report['observation_count']} "
              f"refused_integrity={report['refused_integrity_observation_count']} "
              f"final_checks={report['final_verification_count']} refused_final={report['refused_final_integrity_count']} "
              f"complete={str(report['complete']).lower()} report_sha256={digest}")
        return 0
    except Exception:
        print("synthetic metadata diagnostic refused; all allocated fixtures retained", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
