"""Strict analyser for the reviewed Stage 1 QC replication family.

The command refuses unknown specifications, incomplete provenance, missing
cadence-matched benchmark dates, and logs whose declared rows are incomplete.
It never launches or reads QuantConnect itself; it only consumes saved logs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

from scripts.analyse_qc_alpha_battery import (
    DRAWS,
    analyse,
    bonferroni_threshold,
    merge_logs,
)
from scripts.analyse_qc_benchmark import COST_BPS, parse_benchmark
from scripts.run_alpha_battery_20260815 import performance


STAGE_SPECS = frozenset({"REP_H52", "REP_IDV"})
STAGE_FAMILY_CELLS = 24
LIFETIME_CELLS_BEFORE_STAGE = 428
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _unique_mapping(items: list[str], option: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items:
        label, separator, value = item.partition("=")
        if not separator or not label or not value or label in out:
            raise SystemExit(f"{option}: expected one unique label=value entry")
        out[label] = value
    return out


def _run_identity(items: list[str], option: str) -> dict[str, dict[str, str]]:
    mapped = _unique_mapping(items, option)
    out: dict[str, dict[str, str]] = {}
    for label, value in mapped.items():
        parts = value.split(",")
        if (len(parts) != 4 or not parts[0].isdigit() or int(parts[0]) <= 0
                or not parts[1] or not parts[2] or not SHA256.fullmatch(parts[3])):
            raise SystemExit(
                f"{option}: {label} must be project_id,compile_id,backtest_id,source_sha256"
            )
        out[label] = dict(zip(
            ("project_id", "compile_id", "backtest_id", "source_sha256"), parts
        ))
    return out


def _input_record(path: Path) -> dict[str, str]:
    return {
        "name": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alpha-log", action="append", required=True,
                        help="universe=path")
    parser.add_argument("--benchmark-log", action="append", required=True,
                        help="universe=path")
    parser.add_argument("--alpha-run", action="append", required=True,
                        help="universe=project,compile,backtest,source_sha256")
    parser.add_argument("--benchmark-run", action="append", required=True,
                        help="universe=project,compile,backtest,source_sha256")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    alpha_logs = _unique_mapping(args.alpha_log, "--alpha-log")
    benchmark_logs = _unique_mapping(args.benchmark_log, "--benchmark-log")
    alpha_runs = _run_identity(args.alpha_run, "--alpha-run")
    benchmark_runs = _run_identity(args.benchmark_run, "--benchmark-run")
    labels = set(alpha_logs)
    if not labels or any(set(item) != labels for item in (
        benchmark_logs, alpha_runs, benchmark_runs
    )):
        raise SystemExit("alpha/benchmark logs and run identities must use identical labels")

    stage_gate = bonferroni_threshold(STAGE_FAMILY_CELLS)
    lifetime_cells = LIFETIME_CELLS_BEFORE_STAGE + STAGE_FAMILY_CELLS
    lifetime_gate = bonferroni_threshold(lifetime_cells)
    smallest = 1.0 / (DRAWS + 1)
    if smallest >= min(stage_gate, lifetime_gate):
        raise SystemExit("REFUSING: bootstrap resolution cannot reach both frozen gates")

    report = {
        "stage": "STAGE1_REPLICATIONS",
        "stage_family_cells": STAGE_FAMILY_CELLS,
        "lifetime_cells_before": LIFETIME_CELLS_BEFORE_STAGE,
        "lifetime_cells_after": lifetime_cells,
        "stage_bonferroni_threshold": stage_gate,
        "lifetime_bonferroni_threshold": lifetime_gate,
        "bootstrap_draws": DRAWS,
        "universes": {},
    }
    for label in sorted(labels):
        alpha_path = Path(alpha_logs[label])
        benchmark_path = Path(benchmark_logs[label])
        specs, frame, meta = merge_logs(
            [alpha_path], expected_spec_sets={STAGE_SPECS}
        )
        benchmark = parse_benchmark(benchmark_path)
        alpha_dates = sorted(str(value) for value in frame["date"].unique())
        missing = [date for date in alpha_dates if date not in benchmark.index]
        if missing:
            raise SystemExit(
                f"{label}: benchmark lacks {len(missing)} alpha dates; first={missing[0]}"
            )
        matched = benchmark.loc[alpha_dates]
        series = matched["ret"]
        # A month whose prior book could not be priced declares an
        # unavailable turnover (empty BROW field). Conservative in the
        # cost direction: such months are charged FULL one-way turnover,
        # the same convention the Stage 0 analysers use (S0R-002).
        numeric_turnover = pd.to_numeric(matched["turnover"], errors="coerce")
        charged_turnover = numeric_turnover.fillna(1.0)
        report["universes"][label] = {
            "alpha_run": alpha_runs[label],
            "benchmark_run": benchmark_runs[label],
            "alpha_input": _input_record(alpha_path),
            "benchmark_input": _input_record(benchmark_path),
            "meta": meta,
            "spec_order": specs,
            "specs": analyse(frame, 12.0),
            "benchmark_same_dates": {
                "periods": int(len(matched)),
                "mean_turnover": (
                    float(numeric_turnover.mean())
                    if numeric_turnover.notna().any() else None
                ),
                "unavailable_turnover_periods": int(numeric_turnover.isna().sum()),
                "underfilled_months": int(
                    (matched["names_entered"] > matched["names"]).sum()
                ),
                "gross": performance(series, 12.0),
                "net": {
                    f"{bps:g}bps": performance(
                        series - charged_turnover.values * 2.0 * bps / 10_000.0,
                        12.0,
                    )
                    for bps in COST_BPS
                },
            },
        }

    Path(args.output).write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
