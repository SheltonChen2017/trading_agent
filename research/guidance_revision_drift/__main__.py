"""Offline draft inspection and invented-fixture simulation; no external orders."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from data.hashing import canonical_json
from research.guidance_revision_drift.contracts import (
    CandidateError,
    load_candidate,
    verify_source_documents,
)
from research.guidance_revision_drift.readiness import preflight


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("show-candidate", "preflight", "synthetic-demo", "adapter-manifest",
                                            "review-release", "launch-preflight"))
    parser.add_argument("--output-dir", type=Path, help="existing local directory; synthetic-demo/review-release only")
    args = parser.parse_args(argv)
    if args.output_dir is not None and args.command not in ("synthetic-demo", "review-release"):
        parser.error("--output-dir is supported only for synthetic-demo or review-release")
    try:
        candidate = load_candidate()
        verify_source_documents(candidate, Path(__file__).resolve().parents[2])
    except CandidateError as exc:
        print(canonical_json({"status": "invalid_candidate", "error": str(exc)}), file=sys.stderr)
        return 1
    try:
        if args.command == "show-candidate":
            print(canonical_json(candidate.to_dict()))
            return 0
        if args.command == "adapter-manifest":
            from research.guidance_revision_drift.qc_adapter import adapter_manifest
            print(canonical_json(adapter_manifest()))
            return 0
        if args.command == "launch-preflight":
            from research.guidance_revision_drift.release import launch_preflight
            print(canonical_json(launch_preflight()))
            return 2
        if args.command == "review-release":
            from research.guidance_revision_drift.artifacts import publish_fixture
            from research.guidance_revision_drift.release import build_release
            report = build_release()
            raw = canonical_json(report).encode("utf-8")
            if args.output_dir is not None:
                artifact = publish_fixture(args.output_dir, raw)
                print(canonical_json({"status": report["status"], "artifact": str(artifact),
                                      "external_authority": False, "qc_attempts": 0}))
            else:
                print(raw.decode("utf-8"))
            return 0
        if args.command == "synthetic-demo":
            from research.guidance_revision_drift.artifacts import publish_fixture
            from research.guidance_revision_drift.scenario import run_fixture_report
            report = run_fixture_report()
            raw = canonical_json(report)
            if args.output_dir is not None:
                artifact = publish_fixture(args.output_dir, raw.encode("utf-8"))
                print(canonical_json({"status": report["status"], "artifact": str(artifact),
                                      "external_authority": False, "qc_attempts": 0}))
            else:
                print(raw)
            return 0
        print(canonical_json(preflight(candidate).to_dict()))
        # A valid inspection must not look like approval to a shell caller.
        return 2
    except (ValueError, OSError) as exc:
        print(canonical_json({"status": "offline_command_failed", "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
