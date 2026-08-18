"""Equal-weight universe benchmark, against which long-only means anything.

The single most valuable correction the local work produced was that a
long-only decile Sharpe is uninterpretable without the return of simply
holding the same universe: on the local data that comparison turned a 35%
CAGR into market beta, and a 19.15% "market" return into 11.95% once the
universe was built honestly. This computes the same line for the
QuantConnect universes.
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

from scripts.analyse_qc_alpha_battery import _run_identities  # noqa: E402
from scripts.run_alpha_battery_20260815 import performance  # noqa: E402

COST_BPS = (0.0, 5.0, 10.0, 25.0)


def parse_benchmark(path: Path) -> pd.DataFrame:
    rows, declared = [], None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if "DATES|" in line:
            found = int(line.split("DATES|", 1)[1])
            if declared is not None and found != declared:
                raise SystemExit(f"{path.name}: conflicting DATES declarations")
            declared = found
        elif "BROW|" in line:
            parts = line.split("BROW|", 1)[1].split("|")
            # Legacy rows carry one name count (every emitted month was a
            # full book by construction); R-019 rows carry priced AND
            # entered counts so underfill is recorded instead of dropped.
            if len(parts) not in (4, 5):
                raise SystemExit(f"{path.name}: unsupported/incomplete BROW payload")
            # An EMPTY turnover field is a declared unavailability (the
            # prior book could not be priced that month, R-017); the
            # analyser charges the conservative full 1.0 for it. A PRESENT
            # value must be finite: a literal ``nan`` token would otherwise
            # be dropped before the finite validation and silently
            # relabelled as declared unavailability (S0R-003).
            turnover = float(parts[2]) if parts[2] else None
            if turnover is not None and not math.isfinite(turnover):
                raise SystemExit(f"{path.name}: invalid benchmark turnover")
            priced = int(parts[3])
            entered = int(parts[4]) if len(parts) == 5 else priced
            rows.append((parts[0], float(parts[1]), turnover, priced, entered))
    if declared is None:
        raise SystemExit(f"{path.name}: missing DATES declaration")
    if declared <= 0 or not rows:
        raise SystemExit(f"{path.name}: benchmark contains no dated observations")
    if len(rows) != declared:
        raise SystemExit(
            f"{path.name}: {len(rows)} rows, {declared} declared -- truncated"
        )
    frame = pd.DataFrame(
        rows, columns=["date", "ret", "turnover", "names", "names_entered"]
    ).sort_values("date")
    if not frame["date"].map(lambda value: bool(re.fullmatch(r"\d{6}", value))).all():
        raise SystemExit(f"{path.name}: benchmark dates must use YYYYMM")
    if frame["date"].duplicated().any():
        raise SystemExit(f"{path.name}: duplicate benchmark dates")
    if frame["ret"].isna().any():
        raise SystemExit(f"{path.name}: missing benchmark return")
    if not frame["ret"].map(math.isfinite).all():
        raise SystemExit(f"{path.name}: non-finite benchmark return")
    present_turnover = pd.to_numeric(frame["turnover"].dropna(), errors="coerce")
    if (present_turnover.isna().any()
            or not present_turnover.map(math.isfinite).all()
            or (present_turnover < 0).any()):
        raise SystemExit(f"{path.name}: invalid benchmark turnover")
    if (frame["names"] <= 0).any():
        raise SystemExit(f"{path.name}: benchmark names must be positive")
    if (frame["names_entered"] < frame["names"]).any():
        raise SystemExit(
            f"{path.name}: entered-name count below priced-name count"
        )
    return frame.set_index("date")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", action="append", required=True)
    parser.add_argument("--run-id", action="append", required=True,
                        help="label=project,compile,backtest,source_sha256")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    run_ids = _run_identities(args.run_id)
    report = {}
    seen_labels = set()
    for item in args.log:
        label, separator, path = item.partition("=")
        if not separator or not label or not path or label in seen_labels:
            raise SystemExit("--log expects one unique label=path entry")
        seen_labels.add(label)
        if label not in run_ids:
            raise SystemExit(f"{label}: missing --run-id")
        if len(run_ids[label]) != 1:
            raise SystemExit(f"{label}: benchmark requires exactly one run identity")
        log_path = Path(path)
        frame = parse_benchmark(log_path)
        series = frame["ret"]
        numeric_turnover = pd.to_numeric(frame["turnover"], errors="coerce")
        # Conservative in the cost direction: a month whose prior book could
        # not be priced (R-017) is charged FULL one-way turnover, the same
        # convention the alpha analysers use.
        charged_turnover = numeric_turnover.fillna(1.0)
        report[label] = {
            "periods": int(len(frame)),
            "quantconnect_run": run_ids[label][0],
            "input_log": {
                "name": log_path.name,
                "sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
            },
            "mean_turnover": (float(numeric_turnover.mean())
                              if numeric_turnover.notna().any() else None),
            "unavailable_turnover_periods": int(numeric_turnover.isna().sum()),
            "underfilled_months": int(
                (frame["names"] < frame["names_entered"]).sum()
            ),
            "gross": performance(series, 12.0),
            "net": {
                f"{bps:g}bps": performance(
                    series - charged_turnover * 2.0 * bps / 10_000.0, 12.0
                )
                for bps in COST_BPS
            },
            # Aggregate universe returns are already the cloud algorithm's
            # output, not exported security-level market data. Keeping them
            # makes exact same-date comparisons reproducible.
            "series": [
                {
                    "date": str(date), "return": float(row["ret"]),
                    "turnover": (None if pd.isna(row["turnover"])
                                 else float(row["turnover"])),
                    "names": int(row["names"]),
                    "names_entered": int(row["names_entered"]),
                }
                for date, row in frame.iterrows()
            ],
        }
        p = report[label]["gross"]
        rendered = {
            key: "n/a" if p.get(key) is None else f"{p[key]:.{digits}f}"
            for key, digits in (("cagr", 4), ("sharpe", 2), ("max_drawdown", 3))
        }
        print(f"{label}: n={len(frame)} CAGR={rendered['cagr']} "
              f"Sharpe={rendered['sharpe']} maxDD={rendered['max_drawdown']}")
    Path(args.output).write_text(json.dumps(report, indent=2, default=str),
                                 encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
