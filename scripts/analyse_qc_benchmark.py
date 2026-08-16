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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from scripts.run_alpha_battery_20260815 import performance  # noqa: E402

COST_BPS = (0.0, 5.0, 10.0, 25.0)


def parse_benchmark(path: Path) -> pd.DataFrame:
    rows, declared = [], None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if "DATES|" in line:
            declared = int(line.split("DATES|", 1)[1])
        elif "BROW|" in line:
            parts = line.split("BROW|", 1)[1].split("|")
            if len(parts) != 4:
                raise SystemExit(f"{path.name}: unsupported/incomplete BROW payload")
            rows.append((parts[0], float(parts[1]), float(parts[2]), int(parts[3])))
    if declared is None:
        raise SystemExit(f"{path.name}: missing DATES declaration")
    if len(rows) != declared:
        raise SystemExit(
            f"{path.name}: {len(rows)} rows, {declared} declared -- truncated"
        )
    frame = pd.DataFrame(
        rows, columns=["date", "ret", "turnover", "names"]
    ).sort_values("date")
    if frame["date"].duplicated().any():
        raise SystemExit(f"{path.name}: duplicate benchmark dates")
    if frame[["ret", "turnover"]].isna().any().any():
        raise SystemExit(f"{path.name}: missing return or turnover")
    return frame.set_index("date")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", action="append", required=True)
    parser.add_argument("--run-id", action="append", required=True,
                        help="label=QuantConnect-backtest-id")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    run_ids = {}
    for item in args.run_id:
        label, separator, run_id = item.partition("=")
        if not separator or not label or not run_id or label in run_ids:
            raise SystemExit("--run-id expects one unique label=backtest-id entry")
        run_ids[label] = run_id
    report = {}
    for item in args.log:
        label, _, path = item.partition("=")
        if label not in run_ids:
            raise SystemExit(f"{label}: missing --run-id")
        log_path = Path(path)
        frame = parse_benchmark(log_path)
        series = frame["ret"]
        report[label] = {
            "periods": int(len(frame)),
            "quantconnect_backtest_id": run_ids[label],
            "input_log": {
                "name": log_path.name,
                "sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
            },
            "mean_turnover": float(frame["turnover"].mean()),
            "gross": performance(series, 12.0),
            "net": {
                f"{bps:g}bps": performance(
                    series - frame["turnover"] * 2.0 * bps / 10_000.0, 12.0
                )
                for bps in COST_BPS
            },
            # Aggregate universe returns are already the cloud algorithm's
            # output, not exported security-level market data. Keeping them
            # makes exact same-date comparisons reproducible.
            "series": [
                {
                    "date": str(date), "return": float(row["ret"]),
                    "turnover": float(row["turnover"]), "names": int(row["names"]),
                }
                for date, row in frame.iterrows()
            ],
        }
        p = report[label]["gross"]
        print(f"{label}: n={len(frame)} CAGR={p.get('cagr'):.4f} "
              f"Sharpe={p.get('sharpe'):.2f} maxDD={p.get('max_drawdown'):.3f}")
    Path(args.output).write_text(json.dumps(report, indent=2, default=str),
                                 encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
