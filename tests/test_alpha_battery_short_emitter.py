"""R-013 regression: the packed short-battery log must declare absence.

R-013 (2026-08-18): the A_large short run computed 533 dates but MAX_20
honestly lacked one (2016-01-29) — per-spec ragged dates are ordinary and
already the accepted norm in the monthly battery. The v1 packed layout had
no way to say "this spec is absent today", so the emitter refused the
ENTIRE run: 2,664 honest spec-date cells withheld because one was absent.

These tests drive the REAL algorithm's ``on_end_of_algorithm`` emitter and
the REAL parser end to end over a ragged date and a declared-unavailable
turnover, asserting the run still emits, round-trips, and analyses with the
conservative full 1.0 turnover charge — while a genuinely unrepresentable
turnover still refuses fail-closed.
"""
from __future__ import annotations

import datetime as dt
import math
import sys
import types
from pathlib import Path

import pytest

from scripts import analyse_qc_alpha_battery as analyser

ROOT = Path(__file__).resolve().parents[1]
SHORT = ROOT / "research" / "lean" / "alpha_battery_short.py"


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
def short_algorithm_namespace():
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
        namespace: dict = {"__name__": "alpha_battery_short_sim"}
        exec(compile(SHORT.read_text(encoding="utf-8"),
                     str(SHORT), "exec"), namespace)
        yield namespace
    finally:
        if previous is None:
            sys.modules.pop("AlgorithmImports", None)
        else:
            sys.modules["AlgorithmImports"] = previous


DATES = ("2016-01-15", "2016-01-22", "2016-01-29")
RAGGED_SPEC = "MAX_20"
RAGGED_DATE = "2016-01-29"
SENTINEL_SPEC = "REVERSAL_5D"
SENTINEL_DATE = "2016-01-15"


def _populate(algorithm, order, ragged=True, sentinel=True,
              oversized_turnover=False):
    for spec in order:
        rows = []
        for date in DATES:
            if ragged and spec == RAGGED_SPEC and date == RAGGED_DATE:
                continue
            turn_l10 = 0.2
            if sentinel and spec == SENTINEL_SPEC and date == SENTINEL_DATE:
                turn_l10 = None
            turn_l20 = 7.0 if oversized_turnover else 0.3
            rows.append((date, 0.01, 0.02, -0.01, 0.015,
                         0.1, turn_l10, turn_l20, 100))
        algorithm.results[spec] = rows


def test_ragged_date_and_unavailable_turnover_still_emit_and_round_trip(
    short_algorithm_namespace, tmp_path, monkeypatch
):
    namespace = short_algorithm_namespace
    algorithm = namespace["AlphaBatteryShort"]()
    algorithm.initialize()
    order = list(namespace["SPECIFICATIONS"])
    _populate(algorithm, order)
    algorithm.on_end_of_algorithm()

    errors = [line for line in algorithm.log_lines if "INCOMPLETE" in line]
    assert not errors, errors
    assert any("B64BLOCK|" in line for line in algorithm.log_lines)

    log = tmp_path / "short_ragged.log"
    log.write_text("\n".join(algorithm.log_lines) + "\n", encoding="utf-8")
    specs, frame, meta = analyser.parse_log(log)
    assert specs == order
    assert meta["dates"] == len(DATES)
    assert len(frame) == len(order) * len(DATES) - 1

    ragged_rows = frame[(frame["spec"] == RAGGED_SPEC)
                        & (frame["date"] == RAGGED_DATE.replace("-", ""))]
    assert ragged_rows.empty
    sentinel_rows = frame[(frame["spec"] == SENTINEL_SPEC)
                          & (frame["date"] == SENTINEL_DATE.replace("-", ""))]
    assert len(sentinel_rows) == 1
    assert math.isnan(float(sentinel_rows.iloc[0]["turnover_l10"]))
    assert sentinel_rows.iloc[0]["turnover_ls"] == pytest.approx(0.1)

    monkeypatch.setattr(analyser, "DRAWS", 50)
    periods_per_year = analyser.periods_per_year_for_specs(specs)
    report = analyser.analyse(frame, periods_per_year)
    unavailable = sum(
        spec_entry[label]["unavailable_turnover_periods"]
        for spec_entry in report.values()
        for label in ("long_short", "long_only_10", "long_only_20")
    )
    assert unavailable >= 1


def test_unrepresentable_real_turnover_still_refuses_fail_closed(
    short_algorithm_namespace,
):
    namespace = short_algorithm_namespace
    algorithm = namespace["AlphaBatteryShort"]()
    algorithm.initialize()
    order = list(namespace["SPECIFICATIONS"])
    _populate(algorithm, order, ragged=False, sentinel=False,
              oversized_turnover=True)
    algorithm.on_end_of_algorithm()

    assert any("INCOMPLETE|turnover_out_of_range" in line
               for line in algorithm.log_lines)
    assert not any("B64BLOCK|" in line for line in algorithm.log_lines)


def test_settle_emits_the_row_when_exit_turnover_is_unpriceable(
    short_algorithm_namespace,
):
    """Turnover is a COST input, never a gate on the result (R-010/R-013)."""
    namespace = short_algorithm_namespace
    algorithm = namespace["AlphaBatteryShort"]()
    algorithm.initialize()
    min_names = namespace["MIN_NAMES"]
    names = [f"S{i:02d}" for i in range(min_names + 4)]
    longs, shorts = names[:2], names[2:4]
    long20 = names[:2]
    # The long-only-10 target holds a name whose outcome exists but whose
    # weight-drift NAV denominator is destroyed: outcome exactly -1.0 makes
    # the exit book unpriceable for that construction only.
    weights_ls = {s: (0.5 if s in longs else -0.5) for s in longs + shorts}
    weights_l10 = {names[4]: 1.0}
    weights_l20 = {s: 0.5 for s in long20}
    entry = {s: 100.0 for s in names}
    scores = {spec: {s: float(i) for i, s in enumerate(names)}
              for spec in namespace["SPECIFICATIONS"]}
    algorithm.pending = {
        "date": "2016-01-15",
        "entry": entry,
        "scores": scores,
        "portfolios": {
            spec: {
                "longs": longs, "shorts": shorts, "long20": long20,
                "weights": (weights_ls, weights_l10, weights_l20),
            }
            for spec in namespace["SPECIFICATIONS"]
        },
    }
    algorithm.terminal_prices = {s: 110.0 for s in names}
    algorithm.terminal_prices[names[4]] = 0.0
    algorithm.in_universe = set(names)
    algorithm._settle()

    for spec, rows in algorithm.results.items():
        assert len(rows) == 1, spec
        row = rows[0]
        assert row[0] == "2016-01-15"
        assert row[5] is not None      # long/short exit book priceable
        assert row[6] is None          # long-only-10 exit book unpriceable
        assert row[7] is not None
