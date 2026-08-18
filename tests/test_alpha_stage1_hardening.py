"""Stage 1 hardening regressions (review findings S0R-001 and S0R-002).

The Stage 0 battery chased one defect class through three file-local
copies: an unavailable turnover or unpriceable prior book must NEVER gate
a result row, because refusing to bind leaves ``previous_weights`` holding
a book that can never be priced again — one zombie name then silently
kills every later period. The independent 2026-08-18 review found the
same class alive in both Stage 1 algorithms and the Stage 1 analyser.
These tests drive the REAL algorithm classes (stub-loaded, no LEAN) and
the real analyser end to end.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import types
from pathlib import Path

import pandas as pd
import pytest

from scripts import analyse_qc_alpha_battery as battery_analyser
from scripts import analyse_qc_alpha_stage1 as stage1_analyser
from scripts.analyse_qc_benchmark import parse_benchmark

ROOT = Path(__file__).resolve().parents[1]
REPLICATIONS = ROOT / "research" / "lean" / "alpha_stage1_replications.py"
BENCHMARK = ROOT / "research" / "lean" / "alpha_stage1_benchmark.py"
STAGE_SPECS = frozenset({"REP_H52", "REP_IDV"})


class _Transactions:
    orders_count = 0


class _StubQCAlgorithm:
    def __init__(self):
        self.universe_settings = types.SimpleNamespace()
        self.transactions = _Transactions()
        self.time = dt.datetime(2012, 1, 3)
        self.log_lines: list[str] = []

    def set_start_date(self, *args): pass
    def set_end_date(self, *args): pass
    def set_cash(self, *args): pass
    def add_universe(self, *args): pass
    def add_security(self, symbol, resolution=None): pass
    def remove_security(self, symbol): pass
    def log(self, message): self.log_lines.append(str(message))
    def error(self, message): self.log_lines.append("ERROR: " + str(message))


def _load(path: Path, module_name: str):
    fake = types.ModuleType("AlgorithmImports")
    fake.QCAlgorithm = _StubQCAlgorithm
    fake.Resolution = types.SimpleNamespace(DAILY="daily")
    fake.DataNormalizationMode = types.SimpleNamespace(ADJUSTED="adjusted",
                                                       RAW="raw")
    fake.Universe = types.SimpleNamespace(UNCHANGED="unchanged")
    fake.DelistingType = types.SimpleNamespace(DELISTED="delisted",
                                               WARNING="warning")
    previous = sys.modules.get("AlgorithmImports")
    sys.modules["AlgorithmImports"] = fake
    namespace: dict = {"__name__": module_name}
    try:
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"),
             namespace)
    finally:
        if previous is None:
            sys.modules.pop("AlgorithmImports", None)
        else:
            sys.modules["AlgorithmImports"] = previous
    return namespace


@pytest.fixture()
def replications_namespace():
    return _load(REPLICATIONS, "alpha_stage1_replications_sim")


@pytest.fixture()
def benchmark_namespace():
    return _load(BENCHMARK, "alpha_stage1_benchmark_sim")


def test_replications_bind_survives_unpriceable_turnover(replications_namespace):
    """S0R-001: an unpriceable prior book must not gate the cohort bind."""
    namespace = replications_namespace
    algorithm = namespace["AlphaStage1Replications"]()
    algorithm.initialize()

    names = [f"S{i:02d}" for i in range(34)]
    scores = {spec: {name: float(index) * (0.01 if spec == "REP_IDV" else 1.0)
                     for index, name in enumerate(names)}
              for spec in namespace["SPECIFICATIONS"]}
    algorithm._form_scores = lambda selected, end_ago=0: scores
    algorithm._price = lambda symbol, ago: 100.0
    # Simulate the R-010 zombie condition: every construction's prior book
    # is unpriceable, so every rebalance turnover is unavailable.
    algorithm._rebalance_turnover = lambda key, target: None
    algorithm.session_index = 500

    algorithm._form_and_bind(names, dt.date(2015, 1, 30))

    assert len(algorithm.cohorts) == 1
    cohort = algorithm.cohorts[0]
    # Completeness: an empty portfolios dict is exactly what the removed
    # bind gate produces, so assert the full spec set is present.
    assert set(cohort["portfolios"]) == set(namespace["SPECIFICATIONS"])
    for spec in namespace["SPECIFICATIONS"]:
        assert cohort["portfolios"][spec]["turnovers"] == (None, None, None)
        for construction in ("long_short", "long_only_10", "long_only_20"):
            key = (spec, construction)
            assert algorithm.previous_weights.get(key), (
                "the bind must replace the book even when turnover is "
                "unavailable, or the series dies permanently"
            )


def test_replications_emitter_declares_unavailability_and_raggedness(
    replications_namespace, tmp_path: Path
):
    """S0R-001: None turnover emits as a declared-empty field, and a
    per-spec ragged date round-trips via the SPECMETA inventory (R-007)."""
    namespace = replications_namespace
    algorithm = namespace["AlphaStage1Replications"]()
    algorithm.initialize()
    algorithm.results = {
        "REP_H52": [
            ("2015-01-30", 0.12, 0.01, -0.02, 0.015, None, 0.5, None, 50),
            ("2015-02-27", 0.08, 0.02, -0.01, 0.011, 0.3, 0.4, 0.2, 51),
        ],
        # REP_IDV legitimately skips 2015-02: the date is RAGGED.
        "REP_IDV": [
            ("2015-01-30", -0.05, 0.005, -0.004, 0.007, 0.25, 0.35, 0.15, 50),
        ],
    }

    algorithm.on_end_of_algorithm()

    log_path = tmp_path / "stage1_replications.log"
    log_path.write_text("\n".join(algorithm.log_lines) + "\n", encoding="utf-8")
    specs, frame, meta = battery_analyser.merge_logs(
        [log_path], expected_spec_sets={STAGE_SPECS}
    )
    assert sorted(specs) == sorted(STAGE_SPECS)
    assert len(frame) == 3
    ragged = frame[(frame["spec"] == "REP_H52") & (frame["date"] == "201501")]
    assert len(ragged) == 1
    assert pd.isna(ragged.iloc[0]["turnover_ls"])
    assert pd.isna(ragged.iloc[0]["turnover_l20"])
    assert ragged.iloc[0]["turnover_l10"] == pytest.approx(0.5)


def test_stage1_benchmark_zombie_month_cannot_kill_the_series(
    benchmark_namespace, tmp_path: Path
):
    """S0R-002: the bind must not return on an unpriceable prior book, the
    settle must record underfill instead of dropping the month, and the
    emitted five-field BROW must round-trip the real parser."""
    namespace = benchmark_namespace
    algorithm = namespace["AlphaStage1Benchmark"]()
    algorithm.initialize()
    session = dt.date(2015, 2, 2)
    algorithm.last_session = session
    algorithm.session_index = 100

    # Prior month's book holds a zombie: its data ended silently, so it has
    # no terminal price and its last close is stale.
    prior_names = [f"P{i:02d}" for i in range(31)]
    algorithm.previous_weights = {name: 1.0 / 31 for name in prior_names}
    algorithm.previous_entries = {name: 100.0 for name in prior_names}
    for name in prior_names[1:]:
        algorithm.closes[name] = 105.0
        algorithm.close_sessions[name] = session
    algorithm.closes["P00"] = 100.0
    algorithm.close_sessions["P00"] = dt.date(2015, 1, 15)  # stale = zombie

    entry_names = [f"E{i:02d}" for i in range(31)]
    for name in entry_names:
        algorithm.closes[name] = 50.0
        algorithm.close_sessions[name] = session

    algorithm._enter(entry_names, dt.date(2015, 1, 30))

    assert len(algorithm.cohorts) == 1, (
        "one zombie name must not gate the bind (R-017 died this way)"
    )
    cohort = algorithm.cohorts[0]
    assert cohort["turnover"] is None
    assert set(algorithm.previous_weights) == set(entry_names), (
        "the bind must replace the book or the series dies permanently"
    )

    # 21 sessions later one entered name is itself a zombie at settlement:
    # the month must emit over the 30 priced names with both counts.
    algorithm.session_index = 121
    later = dt.date(2015, 3, 4)
    algorithm.last_session = later
    for name in entry_names[1:]:
        algorithm.closes[name] = 55.0
        algorithm.close_sessions[name] = later
    algorithm.close_sessions["E00"] = session  # stale = unpriceable

    algorithm._settle_due()

    assert len(algorithm.rows) == 1, (
        "an underfilled month must be recorded, not dropped (R-019)"
    )
    date, ret, turnover, priced, entered = algorithm.rows[0]
    assert priced == 30 and entered == 31
    assert ret == pytest.approx(0.1)
    assert turnover is None

    algorithm.on_end_of_algorithm()
    log_path = tmp_path / "stage1_benchmark.log"
    log_path.write_text("\n".join(algorithm.log_lines) + "\n", encoding="utf-8")
    frame = parse_benchmark(log_path)
    assert len(frame) == 1
    assert pd.isna(frame.iloc[0]["turnover"])
    assert int(frame.iloc[0]["names"]) == 30
    assert int(frame.iloc[0]["names_entered"]) == 31


def _stage1_alpha_log(tmp_path: Path, months: list[str]) -> Path:
    cells = []
    for month in months:
        cells.append(
            f"ROW|{month}|"
            + "|".join(
                f"{index}~0.05~0.01~-0.01~0.008~0.0~0.0~0.0~50"
                for index in range(2)
            )
        )
    path = tmp_path / "stage1_alpha.log"
    path.write_text(
        "SPECS|REP_H52|REP_IDV\n" + f"DATES|{len(months)}\n"
        + "\n".join(cells) + "\n",
        encoding="utf-8",
    )
    return path


def test_stage1_analyser_charges_full_turnover_and_discloses(tmp_path: Path):
    """S0R-002 (analyser copy): a declared-unavailable benchmark turnover
    month must be charged the FULL 1.0 one-way, with counts disclosed.
    The exact net-vs-gross mean delta pins the fillna(1.0) magnitude, the
    mutation the count-only assertions could not see (S0R-008 class)."""
    months = [f"20{15 + i // 12:02d}{i % 12 + 1:02d}" for i in range(13)]
    alpha_path = _stage1_alpha_log(tmp_path, months)
    benchmark_rows = []
    for index, month in enumerate(months):
        turnover = "" if index == 3 else "0.0"
        entered = 51 if index == 3 else 50
        benchmark_rows.append(f"BROW|{month}|0.01|{turnover}|50|{entered}")
    benchmark_path = tmp_path / "stage1_benchmark.log"
    benchmark_path.write_text(
        f"DATES|{len(months)}\n" + "\n".join(benchmark_rows) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "stage1_report.json"
    source_hash = "a" * 64
    assert stage1_analyser.main([
        "--alpha-log", f"B={alpha_path}",
        "--benchmark-log", f"B={benchmark_path}",
        "--alpha-run", f"B=1,compile-a,backtest-a,{source_hash}",
        "--benchmark-run", f"B=2,compile-b,backtest-b,{source_hash}",
        "--output", str(output),
    ]) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    block = payload["universes"]["B"]["benchmark_same_dates"]
    assert block["unavailable_turnover_periods"] == 1
    assert block["underfilled_months"] == 1
    # All present turnovers are 0.0, so the entire 10bps drag comes from
    # the single month charged at the conservative full 1.0 one-way.
    gross_mean = block["gross"]["mean_period_return"]
    net10_mean = block["net"]["10bps"]["mean_period_return"]
    assert gross_mean - net10_mean == pytest.approx(
        1.0 * 2.0 * 10.0 / 10_000.0 / len(months)
    )
    assert block["mean_turnover"] == pytest.approx(0.0)
