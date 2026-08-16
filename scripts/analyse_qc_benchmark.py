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
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from scripts.run_alpha_battery_20260815 import performance  # noqa: E402


def parse_benchmark(path: Path) -> pd.Series:
    rows, declared = [], None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if "DATES|" in line:
            declared = int(line.split("DATES|", 1)[1])
        elif "BROW|" in line:
            parts = line.split("BROW|", 1)[1].split("|")
            rows.append((parts[0], float(parts[1]), int(parts[2])))
    if declared is not None and len(rows) < declared:
        raise SystemExit(
            f"{path.name}: {len(rows)} rows, {declared} declared -- truncated"
        )
    frame = pd.DataFrame(rows, columns=["date", "ret", "names"]).sort_values("date")
    return frame.set_index("date")["ret"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", action="append", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = {}
    for item in args.log:
        label, _, path = item.partition("=")
        series = parse_benchmark(Path(path))
        report[label] = {"periods": int(len(series)),
                         "performance": performance(series, 12.0)}
        p = report[label]["performance"]
        print(f"{label}: n={len(series)} CAGR={p.get('cagr'):.4f} "
              f"Sharpe={p.get('sharpe'):.2f} maxDD={p.get('max_drawdown'):.3f}")
    Path(args.output).write_text(json.dumps(report, indent=2, default=str),
                                 encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
