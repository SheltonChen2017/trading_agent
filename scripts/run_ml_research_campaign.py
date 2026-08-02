"""Review-gated ML discovery/confirmation campaign commands (ML-FS-6)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ml.research_orchestration import (
    ResearchOrchestrationError,
    load_reviewed_spec,
    materialize_content_addressed_dataset,
    prepare_confirmation_request,
    run_reviewed_experiment,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize and run review-gated ML research campaigns."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    materialize = commands.add_parser("materialize-dataset")
    materialize.add_argument("--source-dir", required=True)
    materialize.add_argument("--dataset-id", required=True)
    materialize.add_argument("--store-root", required=True)

    verify = commands.add_parser("verify-spec-review")
    verify.add_argument("--spec", required=True)
    verify.add_argument("--review", required=True)

    prepare = commands.add_parser("prepare-confirmation")
    prepare.add_argument("--discovery-output-dir", required=True)
    prepare.add_argument("--discovery-experiment-id", required=True)
    prepare.add_argument("--confirmation-dataset-dir", required=True)
    prepare.add_argument("--confirmation-dataset-id", required=True)
    prepare.add_argument("--confirmation-experiment-id", required=True)
    prepare.add_argument("--created-at", required=True)
    prepare.add_argument("--spec-output", required=True)
    prepare.add_argument("--request-output", required=True)

    run = commands.add_parser("run-reviewed")
    run.add_argument("--spec", required=True)
    run.add_argument("--review", required=True)
    run.add_argument("--dataset-dir", required=True)
    run.add_argument("--dataset-id", required=True)
    run.add_argument("--output-dir", required=True)
    run.add_argument("--code-commit", required=True)
    run.add_argument("--confirmation-request")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "materialize-dataset":
            address = materialize_content_addressed_dataset(
                Path(args.source_dir), args.dataset_id, Path(args.store_root)
            )
            summary = {
                "ok": True,
                "command": args.command,
                **address.to_dict(),
                "production_authoritative": False,
            }
        elif args.command == "verify-spec-review":
            spec, review = load_reviewed_spec(Path(args.spec), Path(args.review))
            summary = {
                "ok": True,
                "command": args.command,
                "experiment_id": spec.experiment_id,
                "mode": spec.mode,
                "spec_hash": spec.spec_hash,
                "review_hash": review.review_hash,
                "production_authoritative": False,
            }
        elif args.command == "prepare-confirmation":
            spec, request = prepare_confirmation_request(
                discovery_output_directory=Path(args.discovery_output_dir),
                discovery_experiment_id=args.discovery_experiment_id,
                confirmation_dataset_directory=Path(args.confirmation_dataset_dir),
                confirmation_dataset_id=args.confirmation_dataset_id,
                confirmation_experiment_id=args.confirmation_experiment_id,
                created_at=args.created_at,
                spec_output_path=Path(args.spec_output),
                request_output_path=Path(args.request_output),
            )
            summary = {
                "ok": True,
                "command": args.command,
                "confirmation_experiment_id": spec.experiment_id,
                "confirmation_spec_hash": spec.spec_hash,
                "confirmation_request_hash": request.request_hash,
                "review_status": request.review_status,
                "production_authoritative": False,
            }
        else:
            record, evidence = run_reviewed_experiment(
                spec_path=Path(args.spec),
                review_path=Path(args.review),
                dataset_directory=Path(args.dataset_dir),
                dataset_id=args.dataset_id,
                output_directory=Path(args.output_dir),
                code_commit=args.code_commit,
                confirmation_request_path=(
                    Path(args.confirmation_request)
                    if args.confirmation_request
                    else None
                ),
            )
            summary = {
                "ok": True,
                "command": args.command,
                "experiment_id": record.identity.experiment_id,
                **dict(evidence),
            }
    except (ResearchOrchestrationError, ValueError, OSError) as exc:
        summary = {
            "ok": False,
            "command": args.command,
            "error": f"{type(exc).__name__}: {exc}",
            "production_authoritative": False,
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
