"""Analyse QuantConnect alpha-battery logs. Significance is computed HERE.

Method V2 forbids fresh significance code, so the LEAN algorithms emit
per-date series only and this script feeds them to the project's reviewed,
tested `stationary_bootstrap_p` and `bonferroni_threshold`.

It refuses rather than reporting when:

  * the gate is unreachable at the configured draw count -- the first local
    battery's headline was arithmetically impossible for exactly this
    reason (ABR-001) and nobody noticed; or
  * a log carries fewer ROW lines than its own `DATES|` declaration, which
    means QuantConnect truncated the output and the series is incomplete.
    The first monthly run lost three specifications of ten that way.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from backtest.engine import bonferroni_threshold  # noqa: E402
from scripts.run_alpha_battery_20260815 import (  # noqa: E402
    performance,
    stationary_bootstrap_p,
)

DRAWS = 20_000
DECLARED_LOOKS = 135
COST_BPS = (0.0, 5.0, 10.0, 25.0)


class TruncatedLog(RuntimeError):
    """The log is incomplete; reporting it would understate the sample."""


def parse_log(path: Path) -> tuple[list[str], pd.DataFrame, dict]:
    specs: list[str] = []
    declared = None
    meta: dict = {}
    rows: list[dict] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if "SPECS|" in line:
            specs = line.split("SPECS|", 1)[1].split("|")
        elif "DATES|" in line:
            declared = int(line.split("DATES|", 1)[1])
        elif "cap_rows=" in line:
            for part in line.split():
                if "=" in part and part.split("=")[0] in {
                    "cap_rows", "cap_fallback", "cap_missing"
                }:
                    key, value = part.split("=")
                    meta[key] = int(value)
        elif "ROW|" in line:
            body = line.split("ROW|", 1)[1]
            fields = body.split("|")
            date = fields[0]
            for cell in fields[1:]:
                parts = cell.split("~")
                if len(parts) != 7:
                    continue
                index, ic, lr, sr, l20, turn, n = parts
                rows.append({
                    "date": date,
                    "spec": specs[int(index)] if specs else index,
                    "ic": float(ic) if ic else None,
                    "long": float(lr),
                    "short": float(sr),
                    "long20": float(l20),
                    "turnover": float(turn),
                    "names": int(n),
                })
    frame = pd.DataFrame(rows)
    observed = frame["date"].nunique() if not frame.empty else 0
    if declared is not None and observed < declared:
        raise TruncatedLog(
            f"{path.name}: {observed} dates present, {declared} declared. "
            "QuantConnect truncated the log; the series is incomplete and "
            "must not be reported."
        )
    meta["dates"] = observed
    return specs, frame, meta


def analyse(frame: pd.DataFrame, periods_per_year: float) -> dict:
    out: dict = {}
    for spec, group in frame.groupby("spec"):
        group = group.sort_values("date")
        ic = group["ic"].dropna()
        gross_ls = 0.5 * group["long"] - 0.5 * group["short"]
        turnover = group["turnover"]
        entry = {
            "periods": int(len(group)),
            "median_names": float(group["names"].median()),
            "mean_ic": float(ic.mean()) if len(ic) else None,
            "std_ic": float(ic.std(ddof=1)) if len(ic) > 1 else None,
            "positive_ic_fraction": float((ic > 0).mean()) if len(ic) else None,
            "ic_p_value": stationary_bootstrap_p(ic, draws=DRAWS) if len(ic) else None,
            "mean_turnover": float(turnover.mean()),
            "long_short": {},
            "long_only_10": {},
            "long_only_20": {},
        }
        for label, series in (
            ("long_short", gross_ls),
            ("long_only_10", group["long"]),
            ("long_only_20", group["long20"]),
        ):
            entry[label]["gross"] = performance(series, periods_per_year)
            entry[label]["p_value"] = stationary_bootstrap_p(series, draws=DRAWS)
            entry[label]["net"] = {
                f"{bps:g}bps": performance(
                    series - turnover.values * 2.0 * bps / 10_000.0, periods_per_year
                )
                for bps in COST_BPS
            }
        out[spec] = entry
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", action="append", required=True,
                        help="label=path, repeatable")
    parser.add_argument("--periods-per-year", type=float, default=12.0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    threshold = bonferroni_threshold(DECLARED_LOOKS)
    smallest = 1.0 / (DRAWS + 1)
    if smallest >= threshold:
        raise SystemExit(
            f"REFUSING: {DRAWS} draws can produce no p-value below "
            f"{smallest:.8f}, but the gate is {threshold:.8f}. The test "
            "could not pass whatever the data said (ABR-001)."
        )

    report = {
        "declared_looks": DECLARED_LOOKS,
        "bonferroni_threshold": threshold,
        "bootstrap_draws": DRAWS,
        "smallest_attainable_p": smallest,
        "universes": {},
    }
    for item in args.log:
        label, _, path = item.partition("=")
        specs, frame, meta = parse_log(Path(path))
        report["universes"][label] = {
            "meta": meta,
            "specs": analyse(frame, args.periods_per_year),
        }
        print(f"{label}: {len(specs)} specs, {meta.get('dates')} dates", flush=True)

    Path(args.output).write_text(json.dumps(report, indent=2, default=str),
                                 encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
