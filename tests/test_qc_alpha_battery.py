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
    node = next(
        item for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    namespace = {"math": math}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
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


def test_residual_momentum_peer_series_is_sliced_not_length_matched():
    """Counter-review of QCAR-004's correction.

    The corrected `_industry_returns` builds leave-one-out peer series over
    `count` sessions (260), while `_returns(symbol, span)` yields 21*months
    entries (126 or 252). The correction rejected on `len(peers) !=
    len(stock)`, an equality that can never hold, so residual momentum
    returned None for every name on every date.

    The consequence was visible in the cloud run rather than in any test:
    the monthly battery refused to emit, reporting
    `INCOMPLETE|missing_specs=MULTI_ALPHA_COMPOSITE|RESIDUAL_MOM_12_1|
    RESIDUAL_MOM_6_1`. The completeness guard did its job; nothing else
    caught it. This pins the arithmetic so a future edit cannot restore
    the impossible comparison.
    """
    source = (
        Path(__file__).resolve().parents[1]
        / "research" / "lean" / "alpha_battery_monthly.py"
    ).read_text(encoding="utf-8")

    assert "len(peers) != len(stock)" not in source, (
        "strict length equality between the 260-session peer series and the "
        "21*months stock window can never hold"
    )
    assert "peers = peers[-len(stock):]" in source, (
        "the peer series must be sliced to the stock window, exactly as the "
        "market series already is"
    )

    # The arithmetic that makes equality impossible, asserted directly.
    peer_sessions = 260
    for months in (6, 12):
        assert 21 * months != peer_sessions, (
            f"{months}-month span coincidentally equals the peer window; "
            "this test would stop protecting anything"
        )
