"""Build the canonical ACER analyst-event dataset from a verified snapshot.

This is data plumbing under ACER-1, not research. It reads an immutable,
hash-verified vendor snapshot, normalizes it into canonical events with
named refusals, writes a content-addressed immutable dataset, and prints a
coverage report.

It performs **no** price join, return computation, ranking, or evaluation,
so running it is not a research look and it produces no `docs/alpha-result.md`
entry. It also makes no network call: the vendor API is never contacted here.

Usage:
    python scripts/build_acer_events.py <snapshot_dir> [--out-root DIR]
    python scripts/build_acer_events.py <snapshot_dir> --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:  # direct `python scripts/...` invocation
    sys.path.insert(0, str(REPO_ROOT))

from research.acer.dataset import summarize, write_dataset  # noqa: E402
from research.acer.normalize import normalize_rows  # noqa: E402
from research.acer.snapshot import (  # noqa: E402
    SnapshotError,
    load_verified_rows,
    manifest_sha256,
)

DEFAULT_OUT_ROOT = REPO_ROOT / "artifacts" / "acer_datasets"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="verified snapshot directory")
    parser.add_argument(
        "--out-root",
        type=Path,
        default=DEFAULT_OUT_ROOT,
        help="dataset root (default: artifacts/acer_datasets, gitignored)",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="analyse a snapshot whose pagination did not terminate naturally",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report coverage without writing a dataset",
    )
    args = parser.parse_args(argv)

    try:
        rows = load_verified_rows(args.snapshot, args.allow_incomplete)
        source_manifest = manifest_sha256(args.snapshot)
    except SnapshotError as exc:
        raise SystemExit(str(exc)) from exc

    events, refusals = normalize_rows(rows)
    report = summarize(events, refusals)

    if args.dry_run:
        report["dataset"] = "DRY RUN - nothing written"
    else:
        identity = write_dataset(
            events,
            refusals,
            args.out_root,
            source_snapshot_name=args.snapshot.name,
            source_manifest_sha256=source_manifest,
        )
        report["dataset"] = identity

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
