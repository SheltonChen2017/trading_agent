"""Cost-capped Databento ingestion CLI.

Metadata and cost-estimate calls are not billable.  ``download`` always
obtains an estimate first and refuses to request data above the operator's
explicit per-request cap.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ml.databento_source import (
    DATABENTO_API_KEY_ENV,
    DailyBarsRequest,
    DatabentoSourceError,
    create_historical_client,
    databento_is_configured,
    estimate_daily_bars_cost,
    fetch_daily_bars_snapshot,
)


def _request(args: argparse.Namespace) -> DailyBarsRequest:
    return DailyBarsRequest(
        tickers=tuple(args.symbols),
        start=args.start,
        end=args.end,
    )


def _add_request_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--start", required=True, help="inclusive YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="exclusive YYYY-MM-DD")


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
    download.add_argument("--output-dir", type=Path, required=True)
    download.add_argument("--max-cost-usd", type=float, required=True)
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
        "point_in_time_data": snapshot.manifest["point_in_time_data"],
        "raw_path": str(snapshot.raw_path),
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
        else:
            result = command_download(
                _request(args),
                output_dir=args.output_dir,
                max_cost_usd=args.max_cost_usd,
            )
    except (DatabentoSourceError, OSError, ValueError) as exc:
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
