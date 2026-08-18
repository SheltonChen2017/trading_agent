"""R-017 regression: the benchmark series must survive a zombie month.

R-017 (2026-08-18): the A_large benchmark reported 48 of ~156 months. A
held name whose market data ends without a delisting event (the R-010
zombie pattern) made `_drift_turnover` return None in January 2016; the
old `_bind_staged_entry` refused to bind on that, leaving
`previous_weights` holding the stale book forever — every later month's
turnover was None, every later bind refused, and the series died silently
while the run "completed" normally.

This test drives the REAL algorithm's bind/settle state machine through a
zombie month and asserts the series recovers: the unpriceable month's
return is honestly absent, the NEXT month binds with a declared-unavailable
turnover, settles, emits, and round-trips through the real parser.
"""
from __future__ import annotations

import datetime as dt
import sys
import types
from pathlib import Path

import pandas as pd
import pytest

from scripts.analyse_qc_benchmark import parse_benchmark

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "research" / "lean" / "universe_benchmark.py"


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


@pytest.fixture()
def benchmark_namespace():
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
    try:
        namespace: dict = {"__name__": "universe_benchmark_sim"}
        exec(compile(BENCHMARK.read_text(encoding="utf-8"),
                     str(BENCHMARK), "exec"), namespace)
        yield namespace
    finally:
        if previous is None:
            sys.modules.pop("AlgorithmImports", None)
        else:
            sys.modules["AlgorithmImports"] = previous


def test_zombie_month_cannot_kill_the_benchmark_series(
    benchmark_namespace, tmp_path
):
    namespace = benchmark_namespace
    algorithm = namespace["UniverseBenchmark"]()
    algorithm.initialize()
    min_names = namespace["MIN_NAMES"]
    names = [f"S{i:02d}" for i in range(min_names + 1)]
    zombie = names[0]
    date1 = dt.date(2015, 12, 1)
    date2 = dt.date(2016, 1, 4)
    date3 = dt.date(2016, 2, 1)

    algorithm.closes = {s: 100.0 for s in names}
    algorithm.close_sessions = {s: date1 for s in names}
    algorithm.last_session = date1
    algorithm.staged = {"names": list(names), "date": str(date1),
                       "score_session": date1}
    algorithm._bind_staged_entry()
    assert algorithm.pending is not None
    assert len(algorithm.pending["entry"]) == min_names + 1

    # The zombie's data ends silently: no delisting event, no new bars.
    algorithm.last_session = date2
    for s in names[1:]:
        algorithm.closes[s] = 110.0
        algorithm.close_sessions[s] = date2
    algorithm.staged = {"names": names[1:], "date": str(date2),
                       "score_session": date2}
    algorithm._bind_staged_entry()
    # December EMITS over the priced subset with the underfill recorded
    # (R-019: dropping the month made coverage collapse to a selectively
    # calm sample), and the bind MUST survive with a declared-unavailable
    # turnover — the old turnover-gated bind returned early here and the
    # series never recovered (R-017).
    assert len(algorithm.rows) == 1
    row_date, ret, turnover, priced, entered = algorithm.rows[0]
    assert row_date == str(date1)
    assert ret == pytest.approx(0.1)
    assert priced == min_names
    assert entered == min_names + 1
    assert algorithm.pending is not None
    assert algorithm.pending["turnover"] is None
    assert zombie not in algorithm.pending["entry"]

    # The next month settles normally: the series has recovered.
    algorithm.last_session = date3
    for s in names[1:]:
        algorithm.closes[s] = 121.0
        algorithm.close_sessions[s] = date3
    algorithm.staged = {"names": names[1:], "date": str(date3),
                       "score_session": date3}
    algorithm._bind_staged_entry()
    assert len(algorithm.rows) == 2
    row_date, ret, turnover, priced, entered = algorithm.rows[1]
    assert row_date == str(date2)
    assert ret == pytest.approx(0.1)
    assert turnover is None
    assert priced == entered == min_names

    algorithm.on_end_of_algorithm()
    log = tmp_path / "benchmark_zombie.log"
    log.write_text("\n".join(algorithm.log_lines) + "\n", encoding="utf-8")
    frame = parse_benchmark(log)
    assert len(frame) == 2
    first, second = frame.iloc[0], frame.iloc[1]
    assert first["ret"] == pytest.approx(0.1)
    assert int(first["names"]) == min_names
    assert int(first["names_entered"]) == min_names + 1
    assert pd.isna(second["turnover"])
    assert int(second["names"]) == int(second["names_entered"]) == min_names
