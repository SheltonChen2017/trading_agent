"""Render the offline ARV2 production pre-QC gate report.

This CLI is intentionally not a data loader or a QuantConnect runner. The
positive orchestration API accepts only builder-authenticated in-process
objects, so no command-line value can supply data, review, signature, or launch
authority. The safe CLI operation deterministically enumerates the default
closed gates without reading providers, credentials, outcomes, or QuantConnect
state.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.analyst_revisions_v2_qc.pre_qc_orchestrator import (
    build_pre_qc_preflight_report,
    render_pre_qc_preflight_report_bytes,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render the deterministic, non-authorizing ARV2 pre-QC report."
    )
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="return exit status 2 while any pre-QC gate is closed",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    report = build_pre_qc_preflight_report()
    sys.stdout.buffer.write(render_pre_qc_preflight_report_bytes(report))
    if arguments.require_ready and not report.ready_for_one_shot_submission:
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised as a subprocess.
    raise SystemExit(main())
