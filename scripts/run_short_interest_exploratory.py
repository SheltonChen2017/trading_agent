"""Short Interest latest-revised software rehearsal, never an actual QC launch.

Run from the designated Short Interest worktree with ``python -m
scripts.run_short_interest_exploratory --demo-dir PATH --output-dir PATH``.
Actual/unknown manifests are refused before their member data is opened.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.short_interest_etf.latest_revised_fixture import publish_fabricated_files
from research.short_interest_etf.latest_revised_runner import run_public_file_rehearsal


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--demo-dir", type=Path, help="publish the fixed fabricated provider-shaped inputs")
    inputs.add_argument("--manifest", type=Path, help="replay only an exact pinned public rehearsal manifest")
    parser.add_argument("--output-dir", type=Path, required=True, help="create-exclusive rehearsal reports")
    args = parser.parse_args(argv)
    try:
        manifest = publish_fabricated_files(args.demo_dir) if args.demo_dir is not None else args.manifest
        result = run_public_file_rehearsal(manifest, args.output_dir)
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "refused", "detail": str(exc),
                          "ready_for_empirical_backtest": False}, sort_keys=True))
        return 2
    print(json.dumps({"status": "software_rehearsal_complete" if result["software_replay_complete"]
                     else "software_rehearsal_incomplete", **result}, sort_keys=True))
    return 0 if result["software_replay_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
