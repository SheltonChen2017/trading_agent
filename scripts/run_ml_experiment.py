"""Run one reproducible ML experiment from a frozen spec (ML-LR-2, plan 8.3).

A DEDICATED script, deliberately not a subcommand of anything that can
execute trades (plan 8.3: "Add a dedicated script, not a subcommand that
shares execution code"). Nothing in this file's import graph can reach the
proposal generator, broker, or execution gate -- pinned by
tests/test_ml_import_boundary.py.

Example:

    python scripts/run_ml_experiment.py \\
      --spec research/ml_specs/volatility-discovery-v1.json \\
      --dataset-dir artifacts/datasets/volatility-v1 \\
      --dataset-id volatility-v1 \\
      --output-dir artifacts/experiments/volatility-v1 \\
      --feature-columns realized_vol_10d_pct realized_vol_60d_pct \\
      --trailing-baseline-column realized_vol_10d_pct \\
      --ewma-baseline-column realized_vol_60d_pct

Exit codes: 0 on success, 1 on any hash, schema, leakage, coverage, or fit
failure (plan 8.3). A JSON summary is always printed to stdout.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.runtime_identity import RuntimeIdentityError, current_commit
from ml.experiment_contracts import ExperimentContractError, ExperimentSpec
from ml.experiments import ExperimentError, run_experiment


def _current_commit(expected_commit: str | None = None) -> str:
    """Strict runtime identity; see data/runtime_identity.py."""
    try:
        return current_commit(
            require_clean=True,
            expected_commit=expected_commit,
        )
    except RuntimeIdentityError as exc:
        raise RuntimeError(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a reproducible, immutable ML research experiment."
    )
    parser.add_argument("--spec", required=True, help="Path to a frozen ExperimentSpec JSON file.")
    parser.add_argument("--dataset-dir", required=True, help="Directory holding the dataset.")
    parser.add_argument("--dataset-id", required=True, help="Dataset ID within --dataset-dir.")
    parser.add_argument("--output-dir", required=True, help="Directory for report/artifacts.")
    parser.add_argument(
        "--feature-columns", nargs="+", required=True,
        help="Ordered feature columns; order is recorded and enforced downstream.",
    )
    parser.add_argument("--target-column", default="label_value")
    parser.add_argument("--trailing-baseline-column", default=None)
    parser.add_argument("--ewma-baseline-column", default=None)
    parser.add_argument(
        "--mode", choices=("discovery", "confirmation"), default=None,
        help=(
            "Assert the spec's own mode. A mismatch is refused so a confirmation "
            "cannot be run against a discovery spec by accident."
        ),
    )
    parser.add_argument(
        "--expect-spec-hash", default=None,
        help=(
            "Refuse to run unless the loaded spec hashes to this value. Required "
            "discipline for a confirmation run: it proves the spec was not edited "
            "after the confirmation was requested."
        ),
    )
    parser.add_argument(
        "--code-commit",
        default=None,
        help="Optional assertion that must equal the clean runtime git HEAD.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        spec = ExperimentSpec.from_dict(
            json.loads(Path(args.spec).read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": f"could not read spec: {exc}"}))
        return 1
    except ExperimentContractError as exc:
        print(json.dumps({"ok": False, "error": f"invalid spec: {exc}"}))
        return 1

    if args.mode is not None and args.mode != spec.mode:
        print(json.dumps({
            "ok": False,
            "error": f"--mode {args.mode!r} does not match spec mode {spec.mode!r}",
        }))
        return 1

    # Plan 8.3: "--mode confirmation refuses a spec whose hash differs from
    # the frozen confirmation request." Enforced for BOTH modes when the
    # caller supplies a hash, and REQUIRED for confirmation -- a confirmation
    # run whose spec could have been edited in between is not a confirmation.
    if spec.mode == "confirmation" and not args.expect_spec_hash:
        print(json.dumps({
            "ok": False,
            "error": (
                "a confirmation run requires --expect-spec-hash so the spec is "
                "provably the one that was frozen when confirmation was requested"
            ),
        }))
        return 1
    if args.expect_spec_hash and args.expect_spec_hash != spec.spec_hash:
        print(json.dumps({
            "ok": False,
            "error": (
                f"spec hash mismatch: expected {args.expect_spec_hash}, "
                f"loaded spec hashes to {spec.spec_hash}"
            ),
        }))
        return 1

    try:
        code_commit = _current_commit(args.code_commit)
    except (OSError, RuntimeError) as exc:
        print(json.dumps({"ok": False, "error": f"could not resolve code commit: {exc}"}))
        return 1

    try:
        record = run_experiment(
            spec,
            Path(args.dataset_dir),
            Path(args.output_dir),
            code_commit,
            dataset_id=args.dataset_id,
            feature_columns=args.feature_columns,
            target_column=args.target_column,
            trailing_baseline_column=args.trailing_baseline_column,
            ewma_baseline_column=args.ewma_baseline_column,
        )
    except (ExperimentError, ExperimentContractError, ValueError, OSError) as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
        return 1

    evidence_failure = "coverage_warnings_present" in record.promotion_blockers
    summary = {
        "ok": not evidence_failure,
        "experiment_id": spec.experiment_id,
        "mode": spec.mode,
        "spec_hash": spec.spec_hash,
        "dataset_hash": record.dataset_hash,
        "report_hash": record.report_hash,
        "run_hash": record.run_hash,
        "verdict": record.verdict,
        "promotion_blockers": list(record.promotion_blockers),
        "total_research_looks": record.total_research_looks,
        "artifact_hashes": dict(record.artifact_hashes),
    }
    if evidence_failure:
        # The rejected report is still valuable immutable evidence, but plan
        # 8.3 requires automation to receive a non-zero status when a fold
        # failed to fit or validation coverage fell below the frozen gate.
        summary["error"] = "experiment completed with coverage or fit failures"
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if evidence_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
