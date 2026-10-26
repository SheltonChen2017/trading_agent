"""Synthetic writer-lifecycle/provenance factorial; no production workaround."""
from __future__ import annotations

import argparse
import os
import sys
import time

from scripts import diagnose_arv2_publication_metadata as probe

ARTIFACT_PATH = probe.ARTIFACT_PATH.with_name("R264-20261008-B")
MAX_SECONDS = 50
MAX_REPORT_BYTES = probe.MAX_REPORT_BYTES


def _allocated_file(metadata, identity, links=1):
    row = probe._metadata(metadata)
    if ((row["dev"], row["ino"]) != identity or not row["regular"] or
            row["mode"] != 0o600 or row["uid"] != os.getuid() or
            row["nlink"] != links or row["size"] != len(probe.PAYLOAD)):
        raise probe.private.SharadarCaptureError("synthetic writer allocation changed")


def _window(root, child, visitor, baseline, baseline_ok, stage_start, case_start,
            monotonic, sleep, deadline):
    observations = []
    for offset in probe.OFFSETS:
        remaining = max(0, stage_start + offset - monotonic())
        if monotonic() + remaining > deadline:
            break
        if remaining:
            sleep(remaining)
        probe._path_matches(root, child)
        current = probe._sample(child, visitor)
        observed = monotonic()
        if observed > deadline:
            break
        observations.append({"offset_seconds": offset, "stage_elapsed_seconds": observed - stage_start,
                             "case_elapsed_seconds": observed - case_start, **current,
                             **probe._comparison(baseline, baseline_ok, current)})
    return observations


def _case(root, root_fd, retained, provenance, repetition, monotonic, sleep, deadline):
    probe._path_matches(root, root_fd)
    name = f"writer_{'retained' if retained else 'early'}-provenance_{'on' if provenance else 'off'}-{repetition}"
    os.mkdir(name, 0o700, dir_fd=root_fd)
    child = probe.private._open_child_directory(root_fd, name, "synthetic B fixture")
    writer = visitor = consumer = None
    try:
        writer = probe.private._new_private_file(child, "pending.json", "synthetic B pending")
        allocated = probe.private._directory_identity(os.fstat(writer))
        probe.private._write_all(writer, probe.PAYLOAD, "synthetic B bytes")
        os.fsync(writer)
        _allocated_file(os.fstat(writer), allocated)
        _allocated_file(os.stat("pending.json", dir_fd=child, follow_symlinks=False), allocated)
        if not retained:
            os.close(writer)
            writer = None
        os.link("pending.json", "final.json", src_dir_fd=child, dst_dir_fd=child, follow_symlinks=False)
        _allocated_file(os.stat("final.json", dir_fd=child, follow_symlinks=False), allocated, links=2)
        os.unlink("pending.json", dir_fd=child)  # Final retains the same synthetic bytes.
        _allocated_file(os.stat("final.json", dir_fd=child, follow_symlinks=False), allocated)
        probe.private._fsync(child, "synthetic B child")
        probe.private._fsync(root_fd, "synthetic B parent")
        visitor = probe.private._open_private_regular(child, "final.json", maximum=len(probe.PAYLOAD),
                                                       label="synthetic B read-only visitor")
        _allocated_file(os.fstat(visitor), allocated)
        baseline = probe._sample(child, visitor)  # One original visitor across both windows.
        if (any((baseline[key]["dev"], baseline[key]["ino"]) != allocated for key in
                ("held", "named", "held_after_read", "named_after_read")) or not baseline["readback_matches"]):
            raise probe.private.SharadarCaptureError("synthetic visitor allocation changed")
        baseline_ok = probe._comparison(baseline, True, baseline)["integrity_unchanged"]
        case_start = monotonic()
        probe._path_matches(root / name, child)
        before_presence = (probe._provenance(visitor, root / name / "final.json", deadline, monotonic)
                           if provenance else None)
        before = _window(root / name, child, visitor, baseline, baseline_ok, case_start,
                         case_start, monotonic, sleep, deadline)
        close_started = monotonic()
        if writer is not None:
            os.close(writer)
            writer = None
        close_completed = monotonic()
        close_metadata = probe._step(child, "final.json", "writer_closed" if retained else "early_close_noop")
        after = _window(root / name, child, visitor, baseline, baseline_ok, close_completed,
                        case_start, monotonic, sleep, deadline)
        probe._path_matches(root / name, child)
        after_presence = (probe._provenance(visitor, root / name / "final.json", deadline, monotonic)
                          if provenance else None)
        probe._path_matches(root / name, child)
        final_sample = probe._sample(child, visitor)
        final = {**final_sample, **probe._comparison(baseline, baseline_ok, final_sample)}
        os.close(visitor)
        visitor = None
        probe._path_matches(root / name, child)
        consumer = probe.private._open_private_regular(child, "final.json", maximum=len(probe.PAYLOAD),
                                                        label="synthetic B final consumer")
        consumed = probe._sample(child, consumer)
        consumer_verification = {**consumed, **probe._comparison(baseline, baseline_ok, consumed)}
        probe._path_matches(root / name, child)
        probe.private._pinned_child(root_fd, name, child, "retained synthetic B fixture")
        return {"writer_retained": retained, "provenance_enabled": provenance,
                "writer_allocation": {"dev": allocated[0], "ino": allocated[1]},
                "provenance_requested": provenance, "provenance_before": before_presence,
                "provenance_after": after_presence, "repetition": repetition,
                "baseline": baseline, "baseline_integrity_unchanged": baseline_ok,
                "before_writer_close": before, "after_writer_close": after,
                "writer_close_start_elapsed_seconds": close_started - case_start,
                "writer_close_end_elapsed_seconds": close_completed - case_start,
                "writer_close_metadata": close_metadata, "writer_close_performed": retained,
                "final_verification": final, "final_integrity_unchanged": final["integrity_unchanged"],
                "consumer_verification": consumer_verification,
                "consumer_integrity_unchanged": consumer_verification["integrity_unchanged"],
                "complete": len(before) == len(after) == len(probe.OFFSETS) and monotonic() <= deadline,
                "baseline_reset": False, "diagnostic_only": True}
    finally:
        if consumer is not None:
            os.close(consumer)
        if visitor is not None:
            os.close(visitor)
        if writer is not None:
            os.close(writer)
        os.close(child)


def _run(path, monotonic, sleep):
    started = monotonic()
    _, parent = probe.private._open_directory_path(path.parent, create=True, name="synthetic B parent")
    root_fd = None
    try:
        os.mkdir(path.name, 0o700, dir_fd=parent)
        root_fd = probe.private._open_child_directory(parent, path.name, "synthetic B artifact")
        cases = []
        for retained, provenance in ((False, True), (False, False), (True, True), (True, False)):
            for repetition in (1, 2):
                if monotonic() >= started + MAX_SECONDS or (cases and not cases[-1]["complete"]):
                    break
                cases.append(_case(path, root_fd, retained, provenance, repetition,
                                   monotonic, sleep, started + MAX_SECONDS))
        observations = [row for case in cases for phase in ("before_writer_close", "after_writer_close")
                        for row in case[phase]]
        report = {"schema": "arv2-synthetic-publication-writer-lifecycle-v1", "cases": cases,
                  "case_count": len(cases), "observation_count": len(observations),
                  "refused_integrity_observation_count": sum(not row["integrity_unchanged"] for row in observations),
                  "final_verification_count": len(cases),
                  "refused_final_integrity_count": sum(not case["final_integrity_unchanged"] for case in cases),
                  "consumer_verification_count": len(cases),
                  "refused_consumer_integrity_count": sum(not case["consumer_integrity_unchanged"] for case in cases),
                  "complete": len(cases) == 8 and all(case["complete"] for case in cases),
                  "elapsed_seconds": monotonic() - started, "maximum_seconds": MAX_SECONDS,
                  "maximum_observation_seconds_per_stage": 2,
                  "synthetic_payload_sha256": probe.sha256_bytes(probe.PAYLOAD),
                  "synthetic_only": True, "production_integrity_waiver": False,
                  "proves_perpetual_stability": False, "provider_or_qc_contact": False}
        raw = probe.canonical_json_bytes(report)
        if len(raw) > MAX_REPORT_BYTES:
            raise probe.private.SharadarCaptureError("synthetic B report exceeds byte limit")
        probe._path_matches(path, root_fd)
        probe.private._write_private_bytes(root_fd, "report.json", raw, "synthetic B report")
        probe.private._fsync(root_fd, "synthetic B report directory")
        probe.private._fsync(parent, "synthetic B report parent")
        if probe.private._read_private_bytes(root_fd, "report.json", maximum=MAX_REPORT_BYTES,
                                             label="synthetic B report readback") != raw:
            raise probe.private.SharadarCaptureError("synthetic B report readback changed")
        probe.private._pinned_child(parent, path.name, root_fd, "synthetic B artifact")
        probe._path_matches(path, root_fd)
        return report, probe.sha256_bytes(raw)
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
              f"consumer_checks={report['consumer_verification_count']} refused_consumer={report['refused_consumer_integrity_count']} "
              f"complete={str(report['complete']).lower()} report_sha256={digest}")
        return 0
    except Exception:
        print("synthetic writer diagnostic refused; all allocated fixtures retained", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
