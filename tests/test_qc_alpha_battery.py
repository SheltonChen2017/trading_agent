"""Regression tests for the corrected QuantConnect alpha measurement path."""
from __future__ import annotations

import ast
import base64
import math
from pathlib import Path
import struct

import pandas as pd
import pytest

from scripts import analyse_qc_alpha_battery as analyser
from scripts.analyse_qc_benchmark import parse_benchmark


ROOT = Path(__file__).resolve().parents[1]
MONTHLY = ROOT / "research" / "lean" / "alpha_battery_monthly.py"
SHORT_SPECS = (
    "ABNORMAL_VOLUME_REVERSAL", "INDUSTRY_ADJ_REVERSAL_5D", "MAX_20",
    "MAX_X_REVERSAL", "REVERSAL_5D",
)


def _load_pure_function(path: Path, name: str):
    """Load one top-level pure helper without importing AlgorithmImports."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    dependencies = []
    if name == "_residual_momentum_total":
        dependencies.append(next(
            item for item in tree.body
            if isinstance(item, ast.FunctionDef) and item.name == "_joint_residual_total"
        ))
    node = next(
        item for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    namespace = {
        "math": math,
        "RESIDUAL_ESTIMATION_SESSIONS": 252,
        "MOMENTUM_SKIP_SESSIONS": 21,
    }
    exec(
        compile(ast.Module(body=[*dependencies, node], type_ignores=[]), str(path), "exec"),
        namespace,
    )
    return namespace[name]


def test_joint_residual_momentum_fits_both_factors_before_measurement():
    residual_total = _load_pure_function(MONTHLY, "_joint_residual_total")
    market = [((index % 7) - 3) / 100 for index in range(80)]
    industry = [((index * index % 11) - 5) / 120 for index in range(80)]
    stock = [0.002 + 1.7 * m - 0.6 * i for m, i in zip(market, industry)]
    for index in range(59, 80):
        stock[index] += 0.01
    assert residual_total(stock, market, industry, 21) == pytest.approx(0.21)


def test_drift_turnover_charges_the_rebalance_after_weight_drift():
    turnover = _load_pure_function(MONTHLY, "_drift_turnover")
    previous = {name: 0.25 for name in "ABCD"}
    target = dict(previous)
    outcomes = {"A": 1.0, "B": 0.0, "C": 0.0, "D": 0.0}
    assert turnover(previous, target, outcomes) == pytest.approx(0.15)
    assert turnover({}, target, {}) == pytest.approx(0.5)
    assert turnover(previous, target, {"A": 1.0}) is None


def _full_cell(index: int, turn_ls=0.1, turn_l10=0.2, turn_l20=0.3) -> str:
    return (
        f"{index}~0.01~0.02~-0.01~0.015~"
        f"{turn_ls}~{turn_l10}~{turn_l20}~100"
    )


def _spec_header() -> str:
    return "SPECS|" + "|".join(SHORT_SPECS)


def _full_row(date: str = "202001") -> str:
    return f"ROW|{date}|" + "|".join(_full_cell(index) for index in range(5))


def test_parser_requires_every_spec_on_every_declared_row(tmp_path: Path):
    log = tmp_path / "partial.log"
    log.write_text(
        _spec_header() + "\nDATES|1\nROW|202001|" + _full_cell(0),
        encoding="utf-8",
    )
    with pytest.raises(analyser.TruncatedLog, match="every declared spec"):
        analyser.parse_log(log)


def test_parser_refuses_the_legacy_single_turnover_layout(tmp_path: Path):
    log = tmp_path / "legacy.log"
    log.write_text(
        _spec_header() + "\nDATES|1\nROW|202001|0~0.01~0.02~-0.01~0.015~0.2~100",
        encoding="utf-8",
    )
    with pytest.raises(analyser.InvalidLog, match="unsupported"):
        analyser.parse_log(log)


def test_parser_round_trips_the_full_period_binary_layout(tmp_path: Path):
    values = (1000, 20000, -10000, 15000, 1000, 2000, 3000)
    payload = struct.pack(">I", 20200102)
    payload += b"".join(struct.pack(">iiiiHHH", *values) for _ in SHORT_SPECS)
    log = tmp_path / "packed.log"
    log.write_text(
        _spec_header()
        + "\nSCALE|layout=b64block_date_u32_i32x4_u16x3|ic=1e-5|ret=1e-6|turnover=1e-4"
        + "\nDATES|1\n"
        + "\n".join(f"SPECMETA|{spec}|median_names=100|periods=1" for spec in SHORT_SPECS)
        + "\nB64BLOCK|1|"
        + base64.b64encode(payload).decode("ascii"),
        encoding="utf-8",
    )
    specs, frame, meta = analyser.parse_log(log)
    assert specs == list(SHORT_SPECS)
    assert meta["dates"] == 1
    assert frame.iloc[0]["ic"] == pytest.approx(0.01)
    assert frame.iloc[0]["long"] == pytest.approx(0.02)
    assert frame.iloc[0]["turnover_l20"] == pytest.approx(0.3)


def test_split_log_merge_refuses_overlapping_windows(tmp_path: Path):
    paths = []
    for number in range(2):
        path = tmp_path / f"part{number}.log"
        path.write_text(
            _spec_header() + "\nDATES|1\n" + _full_row(),
            encoding="utf-8",
        )
        paths.append(path)
    with pytest.raises(analyser.InvalidLog, match="not after prior"):
        analyser.merge_logs(paths)


def test_each_construction_uses_its_own_realised_turnover():
    rows = []
    for index in range(24):
        rows.append({
            "date": f"2020{index:02d}", "spec": "A", "ic": 0.01,
            "long": 0.01, "short": -0.01, "long20": 0.01, "names": 100,
            "turnover_ls": 0.5, "turnover_l10": 0.0, "turnover_l20": 0.25,
        })
    result = analyser.analyse(pd.DataFrame(rows), 12.0)["A"]
    assert result["long_only_10"]["net"]["10bps"]["mean_period_return"] == pytest.approx(0.01)
    assert result["long_only_20"]["net"]["10bps"]["mean_period_return"] == pytest.approx(0.0095)
    assert result["long_short"]["net"]["10bps"]["mean_period_return"] == pytest.approx(0.009)


def test_declared_family_counts_ic_and_all_three_constructions():
    assert analyser.DECLARED_LOOKS == 15 * 3 * 4
    assert 1.0 / (analyser.DRAWS + 1) < 0.05 / analyser.DECLARED_LOOKS


def test_benchmark_parser_requires_construction_turnover(tmp_path: Path):
    log = tmp_path / "benchmark.log"
    log.write_text("DATES|1\nBROW|202001|0.01|0.25|100", encoding="utf-8")
    frame = parse_benchmark(log)
    assert frame.loc["202001", "turnover"] == pytest.approx(0.25)


@pytest.mark.parametrize("months", (6, 12))
def test_residual_momentum_measures_months_minus_one_and_skips_latest_month(months):
    """The score must not relabel the skipped month as the signal window."""
    residual_momentum = _load_pure_function(MONTHLY, "_residual_momentum_total")
    estimation = 252
    measurement = 21 * (months - 1)
    skipped = 21
    length = estimation + measurement + skipped
    market = [((index % 7) - 3) / 100 for index in range(length)]
    industry = [((index * index % 11) - 5) / 120 for index in range(length)]
    stock = [0.002 + 1.7 * m - 0.6 * i for m, i in zip(market, industry)]

    for index in range(estimation, estimation + measurement):
        stock[index] += 0.01
    for index in range(estimation + measurement, length):
        stock[index] += 1.0  # deliberately huge; this is the skipped month

    observed = residual_momentum(
        stock,
        market,
        industry,
        months,
        estimation_sessions=estimation,
        skip_sessions=skipped,
    )
    assert observed == pytest.approx(0.01 * measurement)


def test_residual_momentum_refuses_short_or_misaligned_factor_history():
    residual_momentum = _load_pure_function(MONTHLY, "_residual_momentum_total")
    required = 252 + 21 * 11 + 21
    full = [0.0] * required
    assert residual_momentum(full[:-1], full[:-1], full[:-1], 12) is None
    assert residual_momentum(full, full[:-1], full, 12) is None
