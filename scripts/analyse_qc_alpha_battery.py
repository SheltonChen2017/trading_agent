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
import base64
import binascii
import hashlib
import json
import math
import re
import struct
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
# Each spec/universe produces four tested hypotheses: IC and the returns of
# three portfolio constructions.  The old 135 count omitted IC even though
# IC was the headline gate, understating the family from 135 to 180.
DECLARED_LOOKS = 180
COST_BPS = (0.0, 5.0, 10.0, 25.0)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_SPEC_SETS = {
    frozenset({
        "GROSS_PROFITABILITY", "MOM_12_1", "MOM_3_1", "MOM_6_1", "MOM_9_1",
        "MULTI_ALPHA_COMPOSITE", "QUALITY_COMPOSITE", "QUALITY_MOMENTUM",
        "RESIDUAL_MOM_12_1", "RESIDUAL_MOM_6_1",
    }),
    frozenset({
        "ABNORMAL_VOLUME_REVERSAL", "INDUSTRY_ADJ_REVERSAL_5D", "MAX_20",
        "MAX_X_REVERSAL", "REVERSAL_5D",
    }),
}
MONTHLY_PERIODS_PER_YEAR = 12.0
# The short algorithm owns a non-overlapping six-session cycle: one
# next-session entry plus five later holding sessions.  Annualising it as a
# monthly series (the old global CLI default) materially understated Sharpe.
SHORT_PERIODS_PER_YEAR = 252.0 / 6.0


class TruncatedLog(RuntimeError):
    """The log is incomplete; reporting it would understate the sample."""


class InvalidLog(RuntimeError):
    """The log cannot establish one complete, internally consistent run."""


def periods_per_year_for_specs(specs) -> float:
    """Return the frozen cadence for one recognised Stage 0 spec family."""
    family = frozenset(specs)
    for expected in EXPECTED_SPEC_SETS:
        if family == expected:
            return (MONTHLY_PERIODS_PER_YEAR if len(expected) == 10
                    else SHORT_PERIODS_PER_YEAR)
    raise InvalidLog("unknown spec family has no frozen annualisation cadence")


def parse_log(
    path: Path,
    expected_spec_sets: set[frozenset[str]] | None = None,
) -> tuple[list[str], pd.DataFrame, dict]:
    specs: list[str] = []
    declared = None
    meta: dict = {}
    rows: list[dict] = []
    spec_names: dict[str, int] = {}
    spec_periods: dict[str, int] = {}
    scale_declaration: str | None = None
    date_indices: dict[str, set[int]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if "SPECS|" in line:
            found = line.split("SPECS|", 1)[1].split("|")
            if specs and found != specs:
                raise InvalidLog(f"{path.name}: conflicting SPECS declarations")
            specs = found
        elif "SCALE|" in line:
            found = line.split("SCALE|", 1)[1]
            if scale_declaration is not None and found != scale_declaration:
                raise InvalidLog(f"{path.name}: conflicting SCALE declarations")
            scale_declaration = found
        elif "DATES|" in line:
            found = int(line.split("DATES|", 1)[1])
            if declared is not None and found != declared:
                raise InvalidLog(f"{path.name}: conflicting DATES declarations")
            declared = found
        elif "cap_rows=" in line:
            for part in line.split():
                if "=" in part and part.split("=")[0] in {
                    "cap_rows", "cap_fallback", "cap_missing"
                }:
                    key, value = part.split("=")
                    meta[key] = int(value)
        elif "SPECMETA|" in line:
            body = line.split("SPECMETA|", 1)[1].split("|")
            spec = body[0]
            for field in body[1:]:
                key, _, value = field.partition("=")
                if key == "median_names":
                    spec_names[spec] = int(value)
                elif key == "periods":
                    spec_periods[spec] = int(value)
        elif "B64BLOCK|" in line:
            body = line.split("B64BLOCK|", 1)[1]
            count_text, separator, encoded = body.partition("|")
            expected_scale = (
                "layout=b64block_date_u32_i32x4_u16x3|"
                "ic=1e-5|ret=1e-6|turnover=1e-4"
            )
            if (not separator or not count_text.isdigit() or not specs
                    or scale_declaration != expected_scale):
                raise InvalidLog(f"{path.name}: B64BLOCK lacks its exact schema")
            count = int(count_text)
            if count < 1 or count > 10:
                raise InvalidLog(f"{path.name}: invalid B64BLOCK count {count}")
            try:
                payload = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise InvalidLog(f"{path.name}: invalid base64 block") from exc
            cell_width = struct.calcsize(">iiiiHHH")
            row_width = 4 + cell_width * len(specs)
            if len(payload) != row_width * count:
                raise TruncatedLog(f"{path.name}: incomplete packed block")
            for row_index in range(count):
                offset = row_index * row_width
                date = str(struct.unpack_from(">I", payload, offset)[0])
                if date in date_indices:
                    raise InvalidLog(f"{path.name}: duplicate ROW date {date}")
                indices = date_indices.setdefault(date, set())
                offset += 4
                for numeric_index, spec in enumerate(specs):
                    values = struct.unpack_from(">iiiiHHH", payload,
                                                offset + numeric_index * cell_width)
                    ic, lr, sr, l20, turn_ls, turn_l10, turn_l20 = values
                    indices.add(numeric_index)
                    rows.append({
                        "date": date, "spec": spec,
                        "ic": None if ic == -2147483648 else ic * 1e-5,
                        "long": lr * 1e-6, "short": sr * 1e-6,
                        "long20": l20 * 1e-6,
                        "turnover_ls": turn_ls * 1e-4,
                        "turnover_l10": turn_l10 * 1e-4,
                        "turnover_l20": turn_l20 * 1e-4,
                        "names": spec_names.get(spec),
                    })
        elif "ROW|" in line:
            body = line.split("ROW|", 1)[1]
            fields = body.split("|")
            date = fields[0]
            if not specs:
                raise InvalidLog(f"{path.name}: ROW appeared before SPECS")
            if date in date_indices:
                raise InvalidLog(f"{path.name}: duplicate ROW date {date}")
            indices = date_indices.setdefault(date, set())
            for cell in fields[1:]:
                index, _, payload = cell.partition("~")
                if not payload or not index.isdigit():
                    raise InvalidLog(f"{path.name}: malformed cell on {date}: {cell!r}")
                numeric_index = int(index)
                if numeric_index >= len(specs) or numeric_index in indices:
                    raise InvalidLog(
                        f"{path.name}: duplicate/out-of-range spec index {index} on {date}"
                    )
                indices.add(numeric_index)
                parts = payload.split("~") if "~" in payload else payload.split(",")
                spec = specs[numeric_index]
                if len(parts) == 8:
                    # Full decimal layout: IC, three returns, the matching
                    # three construction turnovers, and usable-name count.
                    # An EMPTY turnover field is a declared unavailability
                    # (the prior book could not be priced that month); the
                    # analyser charges the conservative full 1.0 for it.
                    ic, lr, sr, l20, turn_ls, turn_l10, turn_l20, n = parts
                    rows.append({
                        "date": date, "spec": spec,
                        "ic": float(ic) if ic else None,
                        "long": float(lr), "short": float(sr),
                        "long20": float(l20),
                        "turnover_ls": float(turn_ls) if turn_ls else None,
                        "turnover_l10": float(turn_l10) if turn_l10 else None,
                        "turnover_l20": float(turn_l20) if turn_l20 else None,
                        "names": int(n),
                    })
                else:
                    raise InvalidLog(
                        f"{path.name}: unsupported/incomplete payload on {date}: {payload!r}"
                    )
    if not specs or declared is None:
        raise InvalidLog(f"{path.name}: missing SPECS or DATES declaration")
    if declared <= 0 or not date_indices:
        raise InvalidLog(f"{path.name}: result log contains no dated observations")
    allowed = EXPECTED_SPEC_SETS if expected_spec_sets is None else expected_spec_sets
    if frozenset(specs) not in allowed or len(specs) != len(set(specs)):
        raise InvalidLog(f"{path.name}: incomplete or unknown frozen spec inventory")
    if set(spec_periods) == set(specs):
        # Every specification declares its exact emitted period count, so
        # honest per-spec month raggedness (turnover retries, residual
        # warm-up, missing basket outcomes) is distinguishable from
        # truncation by the per-spec count verification below. R-007 was a
        # complete cloud run that this parser wrongly refused because its
        # dates carried legitimate spec subsets.
        pass
    else:
        expected_indices = set(range(len(specs)))
        incomplete = [date for date, indices in date_indices.items()
                      if indices != expected_indices]
        if incomplete:
            raise TruncatedLog(
                f"{path.name}: {len(incomplete)} ROW lines do not contain "
                "every declared spec and no complete SPECMETA inventory "
                "declares the per-spec counts"
            )
    frame = pd.DataFrame(rows)
    observed = frame["date"].nunique() if not frame.empty else 0
    if declared is not None and observed < declared:
        raise TruncatedLog(
            f"{path.name}: {observed} dates present, {declared} declared. "
            "QuantConnect truncated the log; the series is incomplete and "
            "must not be reported."
        )
    if observed != declared:
        raise InvalidLog(
            f"{path.name}: {observed} distinct dates but DATES declared {declared}"
        )
    for spec, periods in spec_periods.items():
        if spec not in specs:
            raise InvalidLog(f"{path.name}: SPECMETA names unknown spec {spec!r}")
        observed_periods = int((frame["spec"] == spec).sum())
        if periods != observed_periods:
            raise TruncatedLog(
                f"{path.name}: {spec} has {observed_periods} rows, {periods} declared"
            )
    for column in ("long", "short", "long20"):
        numeric = pd.to_numeric(frame[column], errors="coerce")
        if numeric.isna().any() or not numeric.map(math.isfinite).all():
            raise InvalidLog(f"{path.name}: {column} contains non-finite values")
    for column in ("turnover_ls", "turnover_l10", "turnover_l20"):
        # A missing value is a DECLARED unavailability (unpriceable prior
        # book) handled conservatively at analysis; a present value must
        # still be finite and non-negative.
        numeric = pd.to_numeric(frame[column].dropna(), errors="coerce")
        if numeric.isna().any() or not numeric.map(math.isfinite).all():
            raise InvalidLog(f"{path.name}: {column} contains non-finite values")
        if (numeric < 0).any():
            raise InvalidLog(f"{path.name}: {column} contains negative turnover")
    finite_ic = pd.to_numeric(frame["ic"].dropna(), errors="coerce")
    if (finite_ic.isna().any() or not finite_ic.map(math.isfinite).all()
            or (finite_ic.abs() > 1.0).any()):
        raise InvalidLog(f"{path.name}: IC must be finite and within [-1, 1]")
    finite_names = pd.to_numeric(frame["names"].dropna(), errors="coerce")
    if finite_names.isna().any() or (finite_names <= 0).any():
        raise InvalidLog(f"{path.name}: usable-name counts must be positive")
    meta["dates"] = observed
    meta["first_date"] = min(date_indices)
    meta["last_date"] = max(date_indices)
    return specs, frame, meta


def merge_logs(
    paths: list[Path],
    expected_spec_sets: set[frozenset[str]] | None = None,
) -> tuple[list[str], pd.DataFrame, dict]:
    """Merge chronological split windows, rejecting overlap or mismatch."""
    if not paths:
        raise InvalidLog("at least one log path is required")
    frames: list[pd.DataFrame] = []
    expected_specs: list[str] | None = None
    merged_meta: dict = {}
    last_date: str | None = None
    for path in paths:
        specs, frame, meta = parse_log(path, expected_spec_sets=expected_spec_sets)
        if expected_specs is None:
            expected_specs = specs
        elif specs != expected_specs:
            raise InvalidLog(f"{path.name}: spec inventory/order differs across windows")
        first_date = str(meta["first_date"])
        if last_date is not None and first_date <= last_date:
            raise InvalidLog(
                f"{path.name}: window starts at {first_date}, not after prior {last_date}"
            )
        last_date = str(meta["last_date"])
        frames.append(frame)
        for key, value in meta.items():
            if key in {"first_date", "last_date"}:
                continue
            if isinstance(value, int):
                merged_meta[key] = merged_meta.get(key, 0) + value
            elif key not in merged_meta:
                merged_meta[key] = value
    combined = pd.concat(frames, ignore_index=True)
    duplicates = combined.duplicated(subset=["date", "spec"], keep=False)
    if duplicates.any():
        raise InvalidLog("split logs contain overlapping date/spec observations")
    merged_meta["first_date"] = str(combined["date"].min())
    merged_meta["last_date"] = str(combined["date"].max())
    merged_meta["input_logs"] = [
        {
            "name": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in paths
    ]
    return expected_specs or [], combined, merged_meta


def _run_identities(items: list[str]) -> dict[str, list[dict[str, str]]]:
    """Parse complete run provenance for one or more chronological logs."""
    mapped: dict[str, list[dict[str, str]]] = {}
    for item in items:
        label, separator, values = item.partition("=")
        entries = [value.strip() for value in values.split(";") if value.strip()]
        if not separator or not label or not entries or label in mapped:
            raise SystemExit(
                "--run-id: expected one unique "
                "label=project,compile,backtest,source_sha256[;...] entry"
            )
        records = []
        for entry in entries:
            parts = [part.strip() for part in entry.split(",")]
            if (len(parts) != 4 or not parts[0].isdigit()
                    or int(parts[0]) <= 0 or not parts[1] or not parts[2]
                    or not SHA256.fullmatch(parts[3])):
                raise SystemExit(
                    "--run-id: each run must be "
                    "project,compile,backtest,source_sha256"
                )
            records.append(dict(zip(
                ("project_id", "compile_id", "backtest_id", "source_sha256"),
                parts,
            )))
        mapped[label] = records
    return mapped


def analyse(frame: pd.DataFrame, periods_per_year: float) -> dict:
    out: dict = {}
    for spec, group in frame.groupby("spec"):
        group = group.sort_values("date")
        ic = group["ic"].dropna()
        gross_ls = 0.5 * group["long"] - 0.5 * group["short"]
        entry = {
            "periods": int(len(group)),
            "median_names": (float(group["names"].median())
                             if group["names"].notna().any() else None),
            "mean_ic": float(ic.mean()) if len(ic) else None,
            "std_ic": float(ic.std(ddof=1)) if len(ic) > 1 else None,
            "positive_ic_fraction": float((ic > 0).mean()) if len(ic) else None,
            "ic_p_value": stationary_bootstrap_p(ic, draws=DRAWS) if len(ic) else None,
            "long_short": {},
            "long_only_10": {},
            "long_only_20": {},
        }
        constructions = (
            ("long_short", gross_ls, group["turnover_ls"]),
            ("long_only_10", group["long"], group["turnover_l10"]),
            ("long_only_20", group["long20"], group["turnover_l20"]),
        )
        for label, series, turnover in constructions:
            numeric_turnover = pd.to_numeric(turnover, errors="coerce")
            if not numeric_turnover.dropna().map(math.isfinite).all():
                raise InvalidLog(f"{spec}/{label}: non-finite turnover")
            unavailable = int(numeric_turnover.isna().sum())
            # Conservative in the cost direction: a month whose prior book
            # could not be priced is charged FULL one-way turnover, the same
            # convention the reviewed local battery's `net_of_costs` uses.
            charged_turnover = numeric_turnover.fillna(1.0)
            entry[label]["mean_turnover"] = (
                float(numeric_turnover.mean())
                if numeric_turnover.notna().any() else None
            )
            entry[label]["unavailable_turnover_periods"] = unavailable
            entry[label]["gross"] = performance(series, periods_per_year)
            entry[label]["p_value"] = stationary_bootstrap_p(series, draws=DRAWS)
            entry[label]["net"] = {
                f"{bps:g}bps": performance(
                    series - charged_turnover.values * 2.0 * bps / 10_000.0,
                    periods_per_year,
                )
                for bps in COST_BPS
            }
        out[spec] = entry
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", action="append", required=True,
                        help="label=path, repeatable")
    parser.add_argument(
        "--periods-per-year", type=float, default=None,
        help=("optional assertion of the frozen family cadence; monthly=12, "
              "short=42. The analyser always infers cadence per input log."),
    )
    parser.add_argument(
        "--run-id", action="append", required=True,
        help=("label=project,compile,backtest,source_sha256[;...], "
              "one complete identity per input log"),
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if (args.periods_per_year is not None
            and (not math.isfinite(args.periods_per_year)
                 or args.periods_per_year <= 0)):
        raise SystemExit("--periods-per-year must be a positive finite number")
    run_ids = _run_identities(args.run_id)

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
    seen_labels = set()
    for item in args.log:
        label, separator, paths = item.partition("=")
        if not separator or not label or not paths or label in seen_labels:
            raise SystemExit("--log expects one unique label=path[,path...] entry")
        seen_labels.add(label)
        # A label may name SEVERAL logs. The short-horizon battery is split
        # into date windows because its full series exceeds the ~100KB log
        # cap; merging here keeps the analysis on one continuous series
        # rather than reporting two half-samples as if they were separate
        # experiments.
        log_paths = [Path(part.strip()) for part in paths.split(",") if part.strip()]
        if label not in run_ids or len(run_ids[label]) != len(log_paths):
            raise SystemExit(
                f"{label}: --run-id count must match the {len(log_paths)} input logs"
            )
        specs, frame, meta = merge_logs(log_paths)
        periods_per_year = periods_per_year_for_specs(specs)
        if (args.periods_per_year is not None
                and not math.isclose(args.periods_per_year, periods_per_year,
                                     rel_tol=0.0, abs_tol=1e-12)):
            raise SystemExit(
                f"{label}: --periods-per-year={args.periods_per_year:g} "
                f"conflicts with the frozen {periods_per_year:g} cadence"
            )
        report["universes"][label] = {
            "quantconnect_runs": run_ids[label],
            "meta": meta,
            "periods_per_year": periods_per_year,
            "specs": analyse(frame, periods_per_year),
        }
        print(f"{label}: {len(specs)} specs, {meta.get('dates')} dates", flush=True)

    Path(args.output).write_text(json.dumps(report, indent=2, default=str),
                                 encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
