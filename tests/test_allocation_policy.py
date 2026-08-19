"""APQ-1 regressions: the allocation-policy LEAN algorithm.

Dangerous directions per the plan: policy series diverging onto
different date sets, a silent substitute for an unpriceable member, the
retargeter finding an ACTIVE_UNIVERSE to rewrite, and an incomplete run
emitting rows anyway.
"""
from __future__ import annotations

import datetime as dt
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ALGORITHM = ROOT / "research" / "lean" / "allocation_policy.py"


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
    space: dict = {"__name__": "allocation_policy_sim"}
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


JAN31 = dt.date(2022, 1, 31)
FEB01 = dt.date(2022, 2, 1)
FEB28 = dt.date(2022, 2, 28)
MAR01 = dt.date(2022, 3, 1)
MAR31 = dt.date(2022, 3, 31)
APR01 = dt.date(2022, 4, 1)
APR29 = dt.date(2022, 4, 29)
MAY02 = dt.date(2022, 5, 2)


def _prows(algorithm) -> list[list[str]]:
    return [line.split("PROW|", 1)[1].split("|")
            for line in algorithm.log_lines if "PROW|" in line]


def test_frozen_weights_sum_to_one_and_p3_energy_is_exactly_ten_percent(
    namespace,
):
    for policy, weights in namespace["POLICY_WEIGHTS"].items():
        assert sum(weights.values()) == pytest.approx(1.0), policy
    assert namespace["POLICY_WEIGHTS"]["P3"]["XLE"] == 0.10
    assert namespace["START"] == (2022, 1, 1)
    assert namespace["END"] == (2026, 8, 18)
    assert namespace["MIN_MONTHS"] == 24


def test_source_contains_no_active_universe_for_the_retargeter():
    """APQ-1 spec: the Stage 0 driver's ACTIVE_UNIVERSE rewriter must have
    nothing to silently rewrite in this file. The rewriter matches the
    ASSIGNMENT (`^ACTIVE_UNIVERSE = "..."`), so that is what must be
    absent; the docstring's prose mention is deliberate documentation."""
    import re
    source = ALGORITHM.read_text(encoding="utf-8")
    assert not re.search(r"^ACTIVE_UNIVERSE\s*=", source, flags=re.M)


def test_two_priced_months_emit_four_aligned_policies_with_hand_math(
    namespace,
):
    namespace["MIN_MONTHS"] = 2
    algorithm = namespace["AllocationPolicy"]()
    algorithm.initialize()
    flat = {t: 100.0 for t in namespace["TICKERS"]}
    _drive(algorithm, JAN31, flat)                       # entry boundary
    _drive(algorithm, FEB01, flat)
    feb = dict(flat, SPY=110.0)                          # SPY +10% in Feb
    _drive(algorithm, FEB28, feb)
    _drive(algorithm, MAR01, feb)
    mar = dict(feb)                                      # all flat in Mar
    _drive(algorithm, MAR31, mar)
    _drive(algorithm, APR01, mar)                        # completes March
    algorithm.on_end_of_algorithm()

    rows = _prows(algorithm)
    # Vacuous-pass guard from the plan: exactly 4 policies * n months.
    assert len(rows) == 4 * 2
    assert any("DATES|2" in line for line in algorithm.log_lines)
    assert any(line.endswith("POLICIES|P0|P1|P2|P3")
               for line in algorithm.log_lines)
    by_key = {(row[0], row[1]): row for row in rows}
    assert set(by_key) == {(d, p) for d in ("202202", "202203")
                           for p in ("P0", "P1", "P2", "P3")}
    # February returns: P0 = 10%, P1 = 4%, P2 = 4%, P3 = 3.5%.
    assert float(by_key[("202202", "P0")][2]) == pytest.approx(0.10)
    assert float(by_key[("202202", "P1")][2]) == pytest.approx(0.04)
    assert float(by_key[("202202", "P2")][2]) == pytest.approx(0.04)
    assert float(by_key[("202202", "P3")][2]) == pytest.approx(0.035)
    # February carries the true ENTRY turnover 0.5 (reviewed definition).
    assert float(by_key[("202202", "P1")][3]) == pytest.approx(0.5)
    # March turnover: P0 drifts onto itself -> 0; P1 rebalances the
    # drifted (0.44, 0.60)/1.04 book back to 40/60 -> 0.023077.
    assert float(by_key[("202203", "P0")][3]) == pytest.approx(0.0)
    assert float(by_key[("202203", "P1")][3]) == pytest.approx(
        0.5 * (abs(0.40 - 0.44 / 1.04) + abs(0.60 - 0.60 / 1.04)),
        abs=5e-5,   # PROW emits turnover rounded to 4 decimals
    )
    # priced == targeted == the policy's member count.
    assert by_key[("202202", "P0")][4] == "1"
    assert by_key[("202202", "P2")][5] == "4"


def test_one_unpriceable_ticker_refuses_the_boundary_for_all_four_policies(
    namespace,
):
    """The union-refusal alignment rule: XLE missing at the March boundary
    drops BOTH adjacent months for every policy — including P0, which
    does not even hold XLE — and the next measured month declares its
    turnover unavailable (empty field)."""
    namespace["MIN_MONTHS"] = 1
    algorithm = namespace["AllocationPolicy"]()
    algorithm.initialize()
    flat = {t: 100.0 for t in namespace["TICKERS"]}
    _drive(algorithm, JAN31, flat)
    _drive(algorithm, FEB01, flat)
    _drive(algorithm, FEB28, dict(flat, SPY=110.0))
    _drive(algorithm, MAR01, flat)
    no_xle = {t: 120.0 for t in namespace["TICKERS"] if t != "XLE"}
    _drive(algorithm, MAR31, no_xle)                     # XLE unpriceable
    _drive(algorithm, APR01, flat)
    everything = {t: 130.0 for t in namespace["TICKERS"]}
    _drive(algorithm, APR29, everything)
    _drive(algorithm, MAY02, everything)                 # completes April
    algorithm.on_end_of_algorithm()

    rows = _prows(algorithm)
    dates = {row[0] for row in rows}
    # 202202 measured; 202203 AND 202204 dropped for all four (the March
    # boundary close is missing for both adjacent months)... April's
    # return needs the March boundary too, so only Feb survives... but a
    # re-entry happened at APR29? No: the April boundary (APR29) is the
    # re-entry; the month it would complete has no priced start. So the
    # emitted months are exactly {202202}.
    assert dates == {"202202"}
    assert all(len([r for r in rows if r[0] == d]) == 4 for d in dates)


def test_month_after_a_gap_declares_turnover_unavailable(namespace):
    namespace["MIN_MONTHS"] = 1
    algorithm = namespace["AllocationPolicy"]()
    algorithm.initialize()
    flat = {t: 100.0 for t in namespace["TICKERS"]}
    _drive(algorithm, JAN31, flat)
    _drive(algorithm, FEB01, flat)
    no_xle = {t: 110.0 for t in namespace["TICKERS"] if t != "XLE"}
    _drive(algorithm, FEB28, no_xle)                     # refused boundary
    _drive(algorithm, MAR01, flat)
    re_entry = {t: 120.0 for t in namespace["TICKERS"]}
    _drive(algorithm, MAR31, re_entry)                   # re-entry boundary
    _drive(algorithm, APR01, re_entry)
    done = {t: 132.0 for t in namespace["TICKERS"]}      # +10% in April
    _drive(algorithm, APR29, done)
    _drive(algorithm, MAY02, done)                       # completes April
    algorithm.on_end_of_algorithm()

    rows = _prows(algorithm)
    assert {row[0] for row in rows} == {"202204"}
    for row in rows:
        assert float(row[2]) == pytest.approx(0.10)
        assert row[3] == ""          # declared unavailability, all four


def test_nonfinite_close_refuses_the_boundary_for_all_four_policies(namespace):
    """Preregistration section 3: a non-finite close is unpriceable.
    Positivity alone is not enough — NaN <= 0 is False."""
    namespace["MIN_MONTHS"] = 1
    for poison in (float("nan"), float("inf"), float("-inf")):
        algorithm = namespace["AllocationPolicy"]()
        algorithm.initialize()
        flat = {t: 100.0 for t in namespace["TICKERS"]}
        _drive(algorithm, JAN31, flat)
        _drive(algorithm, FEB01, flat)
        _drive(algorithm, FEB28, dict(flat, SPY=poison))
        _drive(algorithm, MAR01, flat)
        algorithm.on_end_of_algorithm()
        assert _prows(algorithm) == [], poison
        assert not any("PROW|" in line for line in algorithm.log_lines)


def test_incomplete_run_emits_no_rows_at_the_frozen_floor(namespace):
    """Fail-closed: two measured months < MIN_MONTHS=24 refuses the whole
    run — INCOMPLETE and not a single PROW."""
    algorithm = namespace["AllocationPolicy"]()
    algorithm.initialize()
    flat = {t: 100.0 for t in namespace["TICKERS"]}
    _drive(algorithm, JAN31, flat)
    _drive(algorithm, FEB01, flat)
    _drive(algorithm, FEB28, dict(flat, SPY=105.0))
    _drive(algorithm, MAR01, flat)
    _drive(algorithm, MAR31, dict(flat, SPY=110.0))
    _drive(algorithm, APR01, flat)
    algorithm.on_end_of_algorithm()
    assert any("INCOMPLETE|" in line and "months=2" in line
               and "required=24" in line
               for line in algorithm.log_lines)
    assert _prows(algorithm) == []
