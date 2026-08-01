"""Fail-closed Databento evidence-capture CLI.

Metadata and cost-estimate calls are not billable.  ``download`` always
obtains an estimate first and refuses to request data above the operator's
explicit per-request cap. Statistics use the same cap. Reference requests
instead require an explicit licensed-subscription acknowledgement because
that service uses account allocations rather than the historical cost API.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ml.databento_source import (
    DATABENTO_API_KEY_ENV,
    DailyBarsRequest,
    DatabentoSnapshotRetainedError,
    DatabentoSourceError,
    create_historical_client,
    databento_is_configured,
    estimate_daily_bars_cost,
    fetch_daily_bars_snapshot,
)
from ml.databento_pit import (
    ReferenceRequest,
    StatisticsRequest,
    estimate_statistics_cost,
    fetch_reference_snapshot,
    fetch_statistics_snapshot,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_OUTPUT_DIR = _REPOSITORY_ROOT / "artifacts" / "databento"


def assert_output_dir_is_git_ignored(output_dir: Path) -> None:
    """Refuse to write licensed vendor data to a tracked path.

    Committing a Databento snapshot would redistribute licensed data, and git
    history is impractical to purge once pushed -- so this is checked before
    the download rather than caught in review afterwards. `git check-ignore`
    is the authority, so the repository's real ignore rules apply instead of a
    reimplementation of them.
    """
    resolved = Path(output_dir).resolve()
    try:
        inside_repository = resolved.is_relative_to(_REPOSITORY_ROOT)
    except (OSError, ValueError):
        inside_repository = False
    if not inside_repository:
        # It may be inside another repository. This process cannot prove the
        # ignore rules or licensing controls of an arbitrary external tree.
        raise DatabentoSourceError(
            f"cannot prove that {resolved} is protected by this repository's "
            f"ignore rules. Use {_DEFAULT_OUTPUT_DIR}."
        )
    probe = resolved / ".databento-write-probe"
    try:
        completed = subprocess.run(
            ["git", "check-ignore", "--quiet", str(probe)],
            cwd=_REPOSITORY_ROOT,
            check=False,
            capture_output=True,
        )
    except OSError:
        # Without git we cannot prove the path is ignored, so fail closed.
        raise DatabentoSourceError(
            f"cannot verify that {resolved} is git-ignored; refusing to write "
            "licensed vendor data to a possibly tracked path"
        ) from None
    if completed.returncode != 0:
        raise DatabentoSourceError(
            f"{resolved} is not git-ignored. Licensed Databento data must not "
            f"enter version control. Use {_DEFAULT_OUTPUT_DIR}, or add an "
            "ignore rule for this directory first."
        )


def _request(args: argparse.Namespace) -> DailyBarsRequest:
    return DailyBarsRequest(
        tickers=tuple(args.symbols),
        start=args.start,
        end=args.end,
    )


def _statistics_request(args: argparse.Namespace) -> StatisticsRequest:
    return StatisticsRequest(
        tickers=tuple(args.symbols),
        start=args.start,
        end=args.end,
        summary_flag=args.summary_flag,
    )


def _reference_request(args: argparse.Namespace) -> ReferenceRequest:
    return ReferenceRequest(
        kind=args.kind,
        tickers=tuple(args.symbols),
        start=args.start,
        end=args.end,
    )


def _add_request_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--start", required=True, help="inclusive YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="exclusive YYYY-MM-DD")


def _add_statistics_arguments(parser: argparse.ArgumentParser) -> None:
    _add_request_arguments(parser)
    parser.add_argument(
        "--summary-flag",
        type=int,
        choices=(1, 2),
        required=True,
        help="preliminary EOD summary vintage (1 near 16:15 ET; 2 near 17:00 ET)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "status", help="check local credential visibility without printing the key"
    )

    check = subparsers.add_parser(
        "check-access", help="make a free metadata request and verify dataset access"
    )
    check.add_argument("--dataset", default="EQUS.SUMMARY")

    estimate = subparsers.add_parser(
        "estimate", help="obtain a free cost estimate without downloading data"
    )
    _add_request_arguments(estimate)

    download = subparsers.add_parser(
        "download", help="cost-cap and save one immutable raw DBN snapshot"
    )
    _add_request_arguments(download)
    download.add_argument(
        "--output-dir",
        type=Path,
        default=_DEFAULT_OUTPUT_DIR,
        help=(
            "Destination for the licensed snapshot. Must be a git-ignored path; "
            f"defaults to {_DEFAULT_OUTPUT_DIR}."
        ),
    )
    download.add_argument("--max-cost-usd", type=float, required=True)

    estimate_statistics = subparsers.add_parser(
        "estimate-statistics",
        help="obtain a free cost estimate for receipt-timestamped statistics",
    )
    _add_statistics_arguments(estimate_statistics)

    download_statistics = subparsers.add_parser(
        "download-statistics",
        help="cost-cap and save receipt-timestamped preliminary EOD statistics",
    )
    _add_statistics_arguments(download_statistics)
    download_statistics.add_argument(
        "--output-dir",
        type=Path,
        default=_DEFAULT_OUTPUT_DIR,
        help=(
            "Destination for the licensed snapshot. Must be a git-ignored path; "
            f"defaults to {_DEFAULT_OUTPUT_DIR}."
        ),
    )
    download_statistics.add_argument("--max-cost-usd", type=float, required=True)

    download_reference = subparsers.add_parser(
        "download-reference",
        help=(
            "save a licensed point-in-time reference response; this uses the "
            "account's reference subscription allocation"
        ),
    )
    _add_request_arguments(download_reference)
    download_reference.add_argument(
        "--kind",
        choices=("security_master", "adjustment_factors"),
        required=True,
    )
    download_reference.add_argument(
        "--output-dir",
        type=Path,
        default=_DEFAULT_OUTPUT_DIR,
        help=(
            "Destination for the licensed snapshot. Must be a git-ignored path; "
            f"defaults to {_DEFAULT_OUTPUT_DIR}."
        ),
    )
    download_reference.add_argument(
        "--acknowledge-reference-subscription",
        action="store_true",
        help=(
            "confirm that the operator understands this call requires licensed "
            "reference access and may consume the account's symbol allocation"
        ),
    )
    return parser


def command_status() -> dict[str, object]:
    configured = databento_is_configured()
    return {
        "ok": configured,
        "environment_variable": DATABENTO_API_KEY_ENV,
        "configured": configured,
        "secret_printed": False,
    }


def command_check_access(dataset: str) -> dict[str, object]:
    client = create_historical_client()
    try:
        datasets = tuple(str(value) for value in client.metadata.list_datasets())
    except Exception as exc:
        raise DatabentoSourceError(
            f"Databento metadata access check failed: {type(exc).__name__}: {exc}"
        ) from exc
    available = dataset in datasets
    return {
        "ok": available,
        "dataset": dataset,
        "available": available,
        "metadata_request_billable": False,
    }


def command_estimate(request: DailyBarsRequest) -> dict[str, object]:
    estimate = estimate_daily_bars_cost(request)
    return {
        "ok": True,
        "request": request.to_dict(),
        "request_hash": request.request_hash,
        "estimated_cost_usd": estimate,
        "data_downloaded": False,
    }


def command_download(
    request: DailyBarsRequest, *, output_dir: Path, max_cost_usd: float
) -> dict[str, object]:
    assert_output_dir_is_git_ignored(output_dir)
    snapshot = fetch_daily_bars_snapshot(
        request,
        directory=output_dir,
        max_cost_usd=max_cost_usd,
    )
    return {
        "ok": True,
        "estimated_cost_usd": snapshot.manifest["estimated_cost_usd"],
        "max_cost_usd": max_cost_usd,
        "row_count": snapshot.manifest["row_count"],
        "session_count": snapshot.manifest["session_count"],
        "validation_status": snapshot.manifest["validation_status"],
        "underfilled": snapshot.manifest["underfilled"],
        "refusal_count": snapshot.manifest["refusal_count"],
        "non_session_refusal_count": snapshot.manifest["non_session_refusal_count"],
        "point_in_time_data": snapshot.manifest["point_in_time_data"],
        "raw_path": str(snapshot.raw_path),
        "manifest_path": str(snapshot.manifest_path),
    }


def command_estimate_statistics(request: StatisticsRequest) -> dict[str, object]:
    estimate = estimate_statistics_cost(request)
    return {
        "ok": True,
        "request": request.to_dict(),
        "request_hash": request.request_hash,
        "estimated_cost_usd": estimate,
        "data_downloaded": False,
        "point_in_time_data": False,
    }


def command_download_statistics(
    request: StatisticsRequest, *, output_dir: Path, max_cost_usd: float
) -> dict[str, object]:
    assert_output_dir_is_git_ignored(output_dir)
    snapshot = fetch_statistics_snapshot(
        request,
        directory=output_dir,
        max_cost_usd=max_cost_usd,
    )
    return {
        "ok": True,
        "estimated_cost_usd": snapshot.manifest["estimated_cost_usd"],
        "max_cost_usd": max_cost_usd,
        "validation_status": snapshot.manifest["validation_status"],
        "record_count": snapshot.manifest["record_count"],
        "refusal_count": snapshot.manifest["refusal_count"],
        "invalid_cohort_count": snapshot.manifest["invalid_cohort_count"],
        "point_in_time_data": snapshot.manifest["point_in_time_data"],
        "blockers": snapshot.manifest["blockers"],
        "raw_path": str(snapshot.raw_path),
        "manifest_path": str(snapshot.manifest_path),
    }


def command_download_reference(
    request: ReferenceRequest,
    *,
    output_dir: Path,
    acknowledge_reference_subscription: bool,
) -> dict[str, object]:
    assert_output_dir_is_git_ignored(output_dir)
    snapshot = fetch_reference_snapshot(
        request,
        directory=output_dir,
        acknowledge_reference_subscription=acknowledge_reference_subscription,
    )
    return {
        "ok": True,
        "kind": snapshot.manifest["kind"],
        "row_count": snapshot.manifest["row_count"],
        "validation_status": snapshot.manifest["validation_status"],
        "point_in_time_reference": snapshot.manifest["point_in_time_reference"],
        "point_in_time_data": snapshot.manifest["point_in_time_data"],
        "limitation": snapshot.manifest["limitation"],
        "data_path": str(snapshot.data_path),
        "manifest_path": str(snapshot.manifest_path),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "status":
            result = command_status()
        elif args.command == "check-access":
            result = command_check_access(args.dataset)
        elif args.command == "estimate":
            result = command_estimate(_request(args))
        elif args.command == "download":
            result = command_download(
                _request(args),
                output_dir=args.output_dir,
                max_cost_usd=args.max_cost_usd,
            )
        elif args.command == "estimate-statistics":
            result = command_estimate_statistics(_statistics_request(args))
        elif args.command == "download-statistics":
            result = command_download_statistics(
                _statistics_request(args),
                output_dir=args.output_dir,
                max_cost_usd=args.max_cost_usd,
            )
        else:
            result = command_download_reference(
                _reference_request(args),
                output_dir=args.output_dir,
                acknowledge_reference_subscription=(
                    args.acknowledge_reference_subscription
                ),
            )
    except DatabentoSnapshotRetainedError as exc:
        # Surfaced distinctly so the operator knows a retry costs nothing.
        result = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "paid_snapshot_retained": True,
            "raw_path": str(exc.raw_path),
            "manifest_path": str(exc.manifest_path),
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    except (DatabentoSourceError, OSError, ValueError) as exc:
        result = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "paid_snapshot_retained": False,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
