"""Strict analyser for the frozen allocation-policy QC family (APQ-2).

Consumes ONE saved cloud log of `research/lean/allocation_policy.py` and
writes one JSON report. It never launches or reads QuantConnect.

Reporting decision (fixed at THIS round's review, before any run exists,
per the plan's counter-review note): the optional excess-mean test family
IS reported — three cells (P1/P2/P3 versus P0), two-sided stationary
bootstrap, Bonferroni 0.05/3 — carrying BOTH required labels: its own
family identity and the explicit "this family only" scope (these three
cells are not added to the alpha program's lifetime floor; the closed
A-002 program is untouched). The descriptive table remains primary: a
gate fail is the expected outcome and ends the family either way.

Refusals (fail closed, typed): unknown policy, duplicate (date, policy),
missing or non-finite return, a PRESENT non-finite turnover token (an
empty field is a DECLARED unavailability, charged the conservative full
1.0 one-way), `priced != targeted` (per the APQ1-003 semantics note both
fields are the policy's member count, so inequality is corruption),
policy date sets that differ from P0's, truncated `DATES`, and fewer
than the frozen 24-month floor.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from backtest.engine import bonferroni_threshold  # noqa: E402
from backtest.risk_metrics import time_under_water  # noqa: E402
from scripts.run_alpha_battery_20260815 import (  # noqa: E402
    performance,
    stationary_bootstrap_p,
)

POLICY_ORDER = ("P0", "P1", "P2", "P3")
POLICY_MEMBER_COUNTS = {"P0": 1, "P1": 2, "P2": 4, "P3": 3}
BENCHMARK_POLICY = "P0"
#: Frozen (preregistration section 5/6).
MIN_MONTHS = 24
PERIODS_PER_YEAR = 12.0
COST_BPS = (0.0, 5.0, 10.0, 25.0)
DRAWS = 20_000
FAMILY_CELLS = 3
FAMILY_LABEL = "allocation-policy 2026-08-18, 3 cells (P1/P2/P3 vs P0)"
FAMILY_SCOPE = (
    "this family only; NOT added to the closed alpha program's lifetime "
    "floor (A-002 untouched)"
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class AllocationLogError(RuntimeError):
    """The log cannot establish one complete, consistent policy run."""


def parse_log(path: Path) -> pd.DataFrame:
    declared = None
    policies_header = None
    rows = []
    seen: set[tuple[str, str]] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if "POLICIES|" in line:
            found = tuple(line.split("POLICIES|", 1)[1].split("|"))
            if policies_header is not None and found != policies_header:
                raise AllocationLogError(f"{path.name}: conflicting POLICIES")
            policies_header = found
        elif "DATES|" in line:
            found = int(line.split("DATES|", 1)[1])
            if declared is not None and found != declared:
                raise AllocationLogError(f"{path.name}: conflicting DATES")
            declared = found
        elif "PROW|" in line:
            parts = line.split("PROW|", 1)[1].split("|")
            if len(parts) != 6:
                raise AllocationLogError(
                    f"{path.name}: malformed PROW payload: {parts!r}"
                )
            date, policy, ret_token, turn_token, priced, targeted = parts
            if policy not in POLICY_ORDER:
                raise AllocationLogError(
                    f"{path.name}: unknown policy {policy!r} on {date}"
                )
            if (date, policy) in seen:
                raise AllocationLogError(
                    f"{path.name}: duplicate row for {policy} on {date}"
                )
            seen.add((date, policy))
            try:
                ret = float(ret_token)
            except ValueError as exc:
                raise AllocationLogError(
                    f"{path.name}: malformed return on {date}/{policy}"
                ) from exc
            if not math.isfinite(ret):
                raise AllocationLogError(
                    f"{path.name}: non-finite return on {date}/{policy}"
                )
            if turn_token:
                try:
                    turnover = float(turn_token)
                except ValueError as exc:
                    raise AllocationLogError(
                        f"{path.name}: malformed turnover on {date}/{policy}"
                    ) from exc
                if not math.isfinite(turnover) or turnover < 0.0:
                    raise AllocationLogError(
                        f"{path.name}: invalid turnover on {date}/{policy}"
                    )
            else:
                turnover = None
            priced_count, targeted_count = int(priced), int(targeted)
            if priced_count != targeted_count:
                raise AllocationLogError(
                    f"{path.name}: priced != targeted on {date}/{policy}; "
                    "both are the policy's member count (APQ1-003), so "
                    "inequality is corruption"
                )
            if targeted_count != POLICY_MEMBER_COUNTS[policy]:
                raise AllocationLogError(
                    f"{path.name}: {policy} targets "
                    f"{POLICY_MEMBER_COUNTS[policy]} members, log says "
                    f"{targeted_count} on {date}"
                )
            rows.append({
                "date": date, "policy": policy, "ret": ret,
                "turnover": turnover,
            })
    if policies_header != POLICY_ORDER:
        raise AllocationLogError(
            f"{path.name}: POLICIES header must be exactly {POLICY_ORDER}"
        )
    if declared is None or not rows:
        raise AllocationLogError(f"{path.name}: no declared dated policy rows")
    frame = pd.DataFrame(rows)
    dates_by_policy = {
        policy: set(group["date"]) for policy, group in frame.groupby("policy")
    }
    benchmark_dates = dates_by_policy.get(BENCHMARK_POLICY, set())
    for policy in POLICY_ORDER:
        if dates_by_policy.get(policy, set()) != benchmark_dates:
            raise AllocationLogError(
                f"{path.name}: {policy} dates differ from "
                f"{BENCHMARK_POLICY}'s; the four series must share one "
                "date set"
            )
    if len(benchmark_dates) != declared:
        raise AllocationLogError(
            f"{path.name}: {len(benchmark_dates)} months, {declared} "
            "declared -- truncated"
        )
    if len(benchmark_dates) < MIN_MONTHS:
        raise AllocationLogError(
            f"{path.name}: {len(benchmark_dates)} months is below the "
            f"frozen {MIN_MONTHS}-month floor"
        )
    return frame.sort_values(["date", "policy"]).reset_index(drop=True)


def _policy_block(returns: pd.Series, turnover: pd.Series) -> dict:
    numeric_turnover = pd.to_numeric(turnover, errors="coerce")
    # Conservative in the cost direction: a declared-unavailable month is
    # charged FULL one-way turnover, the same convention every reviewed
    # analyser in this repository uses.
    charged = numeric_turnover.fillna(1.0)
    gross = performance(returns, PERIODS_PER_YEAR)
    equity = (1.0 + pd.to_numeric(returns, errors="coerce")).cumprod()
    return {
        "gross": gross,
        "time_under_water": time_under_water(equity),
        "mean_turnover": (
            float(numeric_turnover.mean())
            if numeric_turnover.notna().any() else None
        ),
        "unavailable_turnover_periods": int(numeric_turnover.isna().sum()),
        "net": {
            f"{bps:g}bps": performance(
                returns - charged.values * 2.0 * bps / 10_000.0,
                PERIODS_PER_YEAR,
            )
            for bps in COST_BPS
        },
    }


def analyse(frame: pd.DataFrame) -> dict:
    gate = bonferroni_threshold(FAMILY_CELLS)
    smallest = 1.0 / (DRAWS + 1)
    if smallest >= gate:
        raise AllocationLogError(
            f"REFUSING: {DRAWS} draws cannot resolve the {gate:.6f} gate"
        )
    by_policy = {
        policy: group.sort_values("date").reset_index(drop=True)
        for policy, group in frame.groupby("policy")
    }
    benchmark = by_policy[BENCHMARK_POLICY]
    report: dict = {
        "family": FAMILY_LABEL,
        "scope": FAMILY_SCOPE,
        "months": int(len(benchmark)),
        "bonferroni_threshold": gate,
        "bootstrap_draws": DRAWS,
        "policies": {},
        "versus_p0": {},
    }
    for policy in POLICY_ORDER:
        group = by_policy[policy]
        report["policies"][policy] = _policy_block(
            group["ret"], group["turnover"]
        )
    benchmark_perf = report["policies"][BENCHMARK_POLICY]["gross"]
    for policy in ("P1", "P2", "P3"):
        candidate = by_policy[policy]
        excess = candidate["ret"].values - benchmark["ret"].values
        excess_series = pd.Series(excess)
        candidate_perf = report["policies"][policy]["gross"]
        report["versus_p0"][policy] = {
            "excess_monthly_mean": float(excess_series.mean()),
            "sharpe_difference": (
                candidate_perf["sharpe"] - benchmark_perf["sharpe"]
                if candidate_perf.get("sharpe") is not None
                and benchmark_perf.get("sharpe") is not None else None
            ),
            "max_drawdown_difference": (
                candidate_perf["max_drawdown"]
                - benchmark_perf["max_drawdown"]
                if candidate_perf.get("max_drawdown") is not None
                and benchmark_perf.get("max_drawdown") is not None else None
            ),
            "excess_mean_p_value": stationary_bootstrap_p(
                excess_series, draws=DRAWS
            ),
        }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True)
    parser.add_argument("--run-id", required=True,
                        help="project,compile,backtest,source_sha256")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    parts = [part.strip() for part in args.run_id.split(",")]
    if (len(parts) != 4 or not parts[0].isdigit() or int(parts[0]) <= 0
            or not parts[1] or not parts[2]
            or not SHA256.fullmatch(parts[3])):
        raise SystemExit(
            "--run-id must be project,compile,backtest,source_sha256"
        )
    log_path = Path(args.log)
    frame = parse_log(log_path)
    report = analyse(frame)
    report["quantconnect_run"] = dict(zip(
        ("project_id", "compile_id", "backtest_id", "source_sha256"), parts
    ))
    report["input_log"] = {
        "name": log_path.name,
        "sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
    }
    Path(args.output).write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    print(f"months={report['months']} wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
