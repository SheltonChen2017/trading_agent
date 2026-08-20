"""LEV-1 regressions: the leveraged-threshold LEAN algorithm.

Dangerous directions per the frozen preregistration: a trigger
executing at its own close instead of the next one, a pullback variant
re-entering without the pullback, series diverging onto different date
sets, dropped turnover events across refusal gaps, and an incomplete
run emitting rows anyway.
"""
from __future__ import annotations

import datetime as dt
import re
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ALGORITHM = ROOT / "research" / "lean" / "leveraged_threshold.py"


class _Transactions:
    orders_count = 0


class _Equity:
    def set_data_normalization_mode(self, mode):
        pass


class _StubQCAlgorithm:
    def __init__(self):
        self.transactions = _Transactions()
        self.time = dt.datetime(2022, 1, 3)
        self.log_lines: list[str] = []

    def set_start_date(self, *args): pass
    def set_end_date(self, *args): pass
    def set_cash(self, *args): pass
    def add_equity(self, ticker, resolution=None): return _Equity()
    def log(self, message): self.log_lines.append(str(message))
    def error(self, message): self.log_lines.append("ERROR: " + str(message))


@pytest.fixture()
def namespace():
    fake = types.ModuleType("AlgorithmImports")
    fake.QCAlgorithm = _StubQCAlgorithm
    fake.Resolution = types.SimpleNamespace(DAILY="daily")
    fake.DataNormalizationMode = types.SimpleNamespace(ADJUSTED="adjusted")
    previous = sys.modules.get("AlgorithmImports")
    sys.modules["AlgorithmImports"] = fake
    space: dict = {"__name__": "leveraged_threshold_sim"}
    try:
        exec(compile(ALGORITHM.read_text(encoding="utf-8"),
                     str(ALGORITHM), "exec"), space)
        yield space
    finally:
        if previous is None:
            sys.modules.pop("AlgorithmImports", None)
        else:
            sys.modules["AlgorithmImports"] = previous


class _Bar:
    def __init__(self, close): self.close = close


class _Slice:
    def __init__(self, bars): self.bars = bars


def _drive(algorithm, session: dt.date, closes: dict[str, float]):
    algorithm.time = dt.datetime(session.year, session.month, session.day)
    algorithm.on_data(_Slice({t: _Bar(c) for t, c in closes.items()}))


def _all(price: float) -> dict[str, float]:
    return {"TQQQ": price, "QQQ": price, "SPY": price}


D = dt.date


# ---------------------------------------------------------------- pure


def test_take_profit_triggers_at_threshold_and_fills_next_close(namespace):
    state = namespace["new_variant_state"](100.0, D(2022, 1, 3))
    spec = {"take_profit": 0.20, "reentry": "month_end"}
    # Just below the threshold: no trigger.
    namespace["advance_variant"](state, spec, 119.99, D(2022, 1, 4))
    assert state["pending"] is None and state["invested"]
    # At the threshold exactly: trigger, but still invested today.
    namespace["advance_variant"](state, spec, 120.0, D(2022, 1, 5))
    assert state["pending"] == "sell" and state["invested"]
    # Next close fills the sale AT THAT close, not the trigger close.
    namespace["advance_variant"](state, spec, 125.0, D(2022, 1, 6))
    assert not state["invested"]
    assert state["equity"] == pytest.approx(1.25)
    assert state["await_month_end"] is True
    assert state["sales"] == [(D(2022, 1, 3), D(2022, 1, 6),
                               pytest.approx(0.25))]
    assert state["month_turnover"] == pytest.approx(0.5)


def test_pullback_reentry_requires_the_full_pullback(namespace):
    state = namespace["new_variant_state"](100.0, D(2022, 1, 3))
    spec = {"take_profit": 0.20, "reentry": "pullback"}
    namespace["advance_variant"](state, spec, 120.0, D(2022, 1, 4))
    namespace["advance_variant"](state, spec, 126.0, D(2022, 1, 5))
    assert not state["invested"] and state["sale_fill"] == 126.0
    assert state["await_month_end"] is False
    # 0.91 x sale fill: NOT a pullback; the variant must stay in cash.
    namespace["advance_variant"](state, spec, 114.7, D(2022, 1, 6))
    assert state["pending"] is None and not state["invested"]
    # At exactly 90% of the sale fill: trigger; fill at the NEXT close.
    namespace["advance_variant"](state, spec, 113.4, D(2022, 1, 7))
    assert state["pending"] == "buy" and not state["invested"]
    namespace["advance_variant"](state, spec, 110.0, D(2022, 1, 10))
    assert state["invested"] and state["entry_fill"] == 110.0
    # Cash equity carried through: 1.26 at the new fill.
    assert state["equity_at_fill"] == pytest.approx(1.26)
    assert namespace["variant_equity"](state, 121.0) == pytest.approx(
        1.26 * 121.0 / 110.0
    )


def test_equity_is_flat_while_in_cash(namespace):
    state = namespace["new_variant_state"](100.0, D(2022, 1, 3))
    spec = {"take_profit": 0.20, "reentry": "pullback"}
    namespace["advance_variant"](state, spec, 130.0, D(2022, 1, 4))
    namespace["advance_variant"](state, spec, 130.0, D(2022, 1, 5))
    assert state["equity"] == pytest.approx(1.30)
    for close in (140.0, 90.0, 200.0):
        assert namespace["variant_equity"](state, close) == pytest.approx(1.30)


def test_fresh_buy_does_not_retrigger_on_its_own_fill(namespace):
    state = namespace["new_variant_state"](100.0, D(2022, 1, 3))
    spec = {"take_profit": 0.20, "reentry": "pullback"}
    namespace["advance_variant"](state, spec, 125.0, D(2022, 1, 4))
    namespace["advance_variant"](state, spec, 125.0, D(2022, 1, 5))   # sale
    namespace["advance_variant"](state, spec, 112.0, D(2022, 1, 6))   # trigger
    namespace["advance_variant"](state, spec, 112.0, D(2022, 1, 7))   # fill
    # The fill close equals the new entry; +20% is not met at the fill.
    assert state["invested"] and state["pending"] is None


def test_month_end_reentry_fills_only_when_awaiting(namespace):
    state = namespace["new_variant_state"](100.0, D(2022, 1, 3))
    namespace["reenter_at_month_end"](state, 100.0, D(2022, 1, 31))
    assert state["month_turnover"] == 0.0        # invested: no-op
    spec = {"take_profit": 0.20, "reentry": "month_end"}
    namespace["advance_variant"](state, spec, 125.0, D(2022, 1, 4))
    namespace["advance_variant"](state, spec, 125.0, D(2022, 1, 5))
    assert state["await_month_end"]
    namespace["reenter_at_month_end"](state, 111.0, D(2022, 1, 31))
    assert state["invested"] and state["entry_fill"] == 111.0
    assert not state["await_month_end"]
    assert state["month_turnover"] == pytest.approx(1.0)  # sale + re-entry


# --------------------------------------------------------- integration


def _run_two_clean_months(namespace):
    algorithm = namespace["LeveragedThreshold"]()
    algorithm.initialize()
    _drive(algorithm, D(2022, 1, 3), _all(100.0))        # entry
    _drive(algorithm, D(2022, 1, 31), _all(100.0))
    _drive(algorithm, D(2022, 2, 1), _all(100.0))        # marks set
    _drive(algorithm, D(2022, 2, 28), _all(110.0))
    _drive(algorithm, D(2022, 3, 1), _all(110.0))        # 202202 measured
    _drive(algorithm, D(2022, 3, 31), _all(110.0))
    _drive(algorithm, D(2022, 4, 1), _all(110.0))        # 202203 measured
    return algorithm


def test_complete_log_is_aligned_and_charges_entry_once(namespace):
    namespace["MIN_MONTHS"] = 2
    algorithm = _run_two_clean_months(namespace)
    algorithm.on_end_of_algorithm()
    lines = algorithm.log_lines
    assert "LEVSERIES|L0|L1|L2|L3|L4|QREF|SREF" in lines
    assert "LEVDATES|2" in lines
    rows = [line for line in lines if line.startswith("LROW|")]
    assert len(rows) == 14                                # 2 months x 7
    feb = {row.split("|")[2]: row.split("|") for row in rows
           if row.split("|")[1] == "202202"}
    assert set(feb) == {"L0", "L1", "L2", "L3", "L4", "QREF", "SREF"}
    for series, parts in feb.items():
        assert float(parts[3]) == pytest.approx(0.10)     # +10% month
        assert parts[4] == "0.5"                          # entry charge
        assert parts[5] == "1" and parts[6] == "1"
    mar = {row.split("|")[2]: row.split("|") for row in rows
           if row.split("|")[1] == "202203"}
    for series, parts in mar.items():
        assert float(parts[3]) == pytest.approx(0.0)
        assert parts[4] == "0.0"                          # held, no trades


def test_union_refusal_keeps_all_seven_series_aligned(namespace):
    namespace["MIN_MONTHS"] = 1
    algorithm = namespace["LeveragedThreshold"]()
    algorithm.initialize()
    _drive(algorithm, D(2022, 1, 3), _all(100.0))
    _drive(algorithm, D(2022, 1, 31), _all(100.0))
    _drive(algorithm, D(2022, 2, 1), _all(100.0))         # marks set
    # QQQ is missing at the February month-end: the boundary is refused
    # for ALL series, so 202202 AND 202203 are both unmeasurable.
    _drive(algorithm, D(2022, 2, 28), {"TQQQ": 105.0, "SPY": 105.0})
    _drive(algorithm, D(2022, 3, 1), _all(105.0))
    _drive(algorithm, D(2022, 3, 31), _all(105.0))
    _drive(algorithm, D(2022, 4, 1), _all(105.0))         # marks re-set
    _drive(algorithm, D(2022, 4, 29), _all(105.0))
    _drive(algorithm, D(2022, 5, 2), _all(105.0))         # 202204 measured
    dates = {row[0] for row in algorithm.rows}
    assert dates == {"202204"}
    assert {row[1] for row in algorithm.rows} == {
        "L0", "L1", "L2", "L3", "L4", "QREF", "SREF"
    }
    # Declared unavailability: attribution spans the refusal gap.
    assert all(row[3] is None for row in algorithm.rows)


def test_incomplete_run_emits_no_rows(namespace):
    namespace["MIN_MONTHS"] = 5
    algorithm = _run_two_clean_months(namespace)
    algorithm.on_end_of_algorithm()
    joined = "\n".join(algorithm.log_lines)
    assert "INCOMPLETE|" in joined
    assert "months=2" in joined and "required=5" in joined
    assert "LROW|" not in joined and "LSALE|" not in joined


def test_sales_are_logged_and_gap_events_roll_forward(namespace):
    namespace["MIN_MONTHS"] = 1
    algorithm = namespace["LeveragedThreshold"]()
    algorithm.initialize()
    _drive(algorithm, D(2022, 1, 3), _all(100.0))         # entry
    _drive(algorithm, D(2022, 1, 10), _all(125.0))        # L1/L3 trigger
    _drive(algorithm, D(2022, 1, 11), _all(126.0))        # sale fill 126
    _drive(algorithm, D(2022, 1, 31), _all(100.0))        # L3 pullback trig
    _drive(algorithm, D(2022, 2, 1), _all(100.0))         # L1 fills at 100
    _drive(algorithm, D(2022, 2, 28), _all(100.0))        # (boundary above)
    _drive(algorithm, D(2022, 3, 1), _all(100.0))         # 202202 measured
    algorithm.on_end_of_algorithm()
    sales = [line for line in algorithm.log_lines if line.startswith("LSALE|")]
    assert "LSALE|L1|2022-01-03|2022-01-11|0.26" in sales
    assert "LSALE|L3|2022-01-03|2022-01-11|0.26" in sales
    assert len(sales) == 2                                # L2/L4 never sold
    feb = {row[1]: row for row in algorithm.rows if row[0] == "202202"}
    # January's sale (0.5) plus the re-entry (0.5) happened in unmeasured
    # months and must ROLL INTO the first measured row on top of the 0.5
    # entry charge — never be silently dropped.
    assert feb["L1"][3] == pytest.approx(1.5)
    assert feb["L3"][3] == pytest.approx(1.5)
    assert feb["L2"][3] == pytest.approx(0.5)             # entry only
    assert feb["L0"][3] == pytest.approx(0.5)
    # L1 sold at 126 and re-entered at the 100 month-end close: equity
    # 1.26 flat through the measured month. L2 held: -20.6% not -0%.
    assert feb["L1"][2] == pytest.approx(0.0)
    assert feb["L2"][2] == pytest.approx(0.0)
    assert feb["QREF"][2] == pytest.approx(0.0)


def test_no_active_universe_declaration():
    """The driver must upload these bytes unchanged (universe-free
    family); a declaring line would route it into the retargeter."""
    source = ALGORITHM.read_text(encoding="utf-8")
    assert not re.search(r"^ACTIVE_UNIVERSE\b", source, flags=re.M)
