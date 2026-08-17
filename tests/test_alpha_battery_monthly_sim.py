"""LEAN-stub integration simulation of the monthly battery.

R-005/R-006 (2026-08-17): both Stage 0 monthly cloud runs refused with every
residual-momentum specification empty, while every unit test in this
repository was green. The defect was only visible at the EVENT-MODEL level:
LEAN labels a daily bar with the next calendar day, so the last bar of a
month that ends on a Friday arrives labeled Saturday-the-1st — before the
new month's universe selection exists — and the factor recorder, which keyed
membership by the label's month, recorded that day with empty industry
buckets. One poisoned day refused every 504-session residual window that
spanned it; months end on Fridays about one in four, so every window was
poisoned and residual momentum refused everywhere, on every universe.

This test drives the REAL algorithm class through that exact event model
(coarse selection at trading-day midnight, bars labeled the following
calendar day, weekend labels included) and asserts the residual
specifications actually emit. It is the missing integration seam: pure
helpers were behaviourally tested, but the composition never executed under
LEAN's timestamp semantics.
"""
from __future__ import annotations

import datetime as dt
import random
import sys
import types
from collections import deque
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MONTHLY = ROOT / "research" / "lean" / "alpha_battery_monthly.py"


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
def monthly_algorithm_class():
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
        namespace: dict = {"__name__": "alpha_battery_monthly_sim"}
        exec(compile(MONTHLY.read_text(encoding="utf-8"),
                     str(MONTHLY), "exec"), namespace)
        yield namespace
    finally:
        if previous is None:
            sys.modules.pop("AlgorithmImports", None)
        else:
            sys.modules["AlgorithmImports"] = previous


class _Value:
    def __init__(self, value): self.value = value


class _Fine:
    def __init__(self, symbol, industry, price, seed):
        self.symbol = symbol
        self.has_fundamental_data = True
        self.dollar_volume = 1e9
        self.market_cap = 1e12
        self.price = price
        self.company_profile = types.SimpleNamespace(shares_outstanding=1e9)
        self.asset_classification = types.SimpleNamespace(
            morningstar_industry_code=industry)
        self.financial_statements = types.SimpleNamespace(
            income_statement=types.SimpleNamespace(
                gross_profit=_Value(5e9 * (1.0 + seed))),
            balance_sheet=types.SimpleNamespace(
                total_assets=_Value(5e10),
                total_debt=_Value(1e10 * (1.0 + 2.0 * seed))),
            cash_flow_statement=types.SimpleNamespace(
                free_cash_flow=_Value(3e9 * (1.0 - seed))),
        )
        self.operation_ratios = types.SimpleNamespace(roe=_Value(0.1 + seed))


class _Bar:
    def __init__(self, close): self.close = close


class _Slice:
    def __init__(self, bars): self.bars = bars; self.delistings = {}


def test_residual_momentum_survives_weekend_month_boundaries(
    monthly_algorithm_class,
):
    namespace = monthly_algorithm_class
    algorithm = namespace["AlphaBatteryMonthly"]()
    algorithm.initialize()

    rng = random.Random(7)
    names = [f"SYM{i:02d}" for i in range(40)]
    industry_of = {name: 100 + (i % 4) for i, name in enumerate(names)}
    seed_of = {name: (i % 7) * 0.03 for i, name in enumerate(names)}
    prices = {name: 100.0 for name in names}

    sessions_run = 0
    selection_label_month = None
    last_trading_day = None
    calendar_day = dt.date(2012, 1, 2)
    while sessions_run < 40 * 21:
        day = calendar_day
        algorithm.time = dt.datetime(day.year, day.month, day.day)
        if day.weekday() < 5:
            # Coarse/fine slice fires at the TRADING day's midnight.
            month = (day.year, day.month)
            if month != selection_label_month:
                selection_label_month = month
                fine = [_Fine(n, industry_of[n], prices[n], seed_of[n])
                        for n in names]
                algorithm._coarse(fine)
                algorithm._fine(fine)
        if (last_trading_day is not None
                and day == last_trading_day + dt.timedelta(days=1)):
            # The previous trading day's bar arrives labeled TODAY — which
            # is Saturday whenever a month ends on a Friday. That label is
            # the whole defect.
            for name in names:
                prices[name] *= 1.0 + rng.gauss(0.0004, 0.015)
            algorithm.on_data(_Slice({n: _Bar(prices[n]) for n in names}))
            sessions_run += 1
        if day.weekday() < 5:
            last_trading_day = day
        calendar_day += dt.timedelta(days=1)

    residual_6 = algorithm.results.get("RESIDUAL_MOM_6_1", [])
    residual_12 = algorithm.results.get("RESIDUAL_MOM_12_1", [])
    assert len(residual_6) >= 10, (
        "residual momentum emitted no rows under LEAN's weekend bar labels — "
        "the R-005/R-006 refusal has returned"
    )
    assert len(residual_12) >= 10
    # And the ordinary specifications keep emitting alongside them.
    assert len(algorithm.results.get("MOM_12_1", [])) >= 20
    assert len(algorithm.results.get("GROSS_PROFITABILITY", [])) >= 20


def test_recovers_from_a_skipped_month_and_emits_a_parseable_log(
    monthly_algorithm_class, tmp_path,
):
    """R-008's die-off and R-007's unparseable log, in one drive.

    Two defects escaped every prior test because no test ran the WHOLE
    pipeline: (1) one month in which every specification skipped left
    `prior_outcomes` empty against stale non-empty weights, refusing every
    later month forever — B_core emitted nothing after 2017-01; and (2) the
    algorithm legitimately emits per-spec subsets per date, which the frozen
    parser refused as truncation, so even A_large's complete run was
    unanalysable. This drives the real class through a forced skip month and
    then feeds its own emitted log into the REAL parser.
    """
    from scripts import analyse_qc_alpha_battery as analyser

    namespace = monthly_algorithm_class
    algorithm = namespace["AlphaBatteryMonthly"]()
    algorithm.initialize()

    rng = random.Random(11)
    names = [f"SYM{i:02d}" for i in range(40)]
    industry_of = {name: 100 + (i % 4) for i, name in enumerate(names)}
    seed_of = {name: (i % 7) * 0.03 for i, name in enumerate(names)}
    prices = {name: 100.0 for name in names}

    sessions_run = 0
    selection_label_month = None
    last_trading_day = None
    starve_month = (2013, 9)          # after warm-up, starve one bind day
    starved = False
    calendar_day = dt.date(2012, 1, 2)
    while sessions_run < 52 * 21:
        day = calendar_day
        algorithm.time = dt.datetime(day.year, day.month, day.day)
        if day.weekday() < 5:
            month = (day.year, day.month)
            if month != selection_label_month:
                selection_label_month = month
                fine = [_Fine(n, industry_of[n], prices[n], seed_of[n])
                        for n in names]
                algorithm._coarse(fine)
                algorithm._fine(fine)
        if (last_trading_day is not None
                and day == last_trading_day + dt.timedelta(days=1)):
            for name in names:
                prices[name] *= 1.0 + rng.gauss(0.0004, 0.015)
            bars = {n: _Bar(prices[n]) for n in names}
            if ((day.year, day.month) == starve_month
                    and algorithm.staged is not None and not starved):
                # The bind day sees too few priced names: entry < MIN_NAMES,
                # every specification skips, and the OLD code then refused
                # every later month.
                starved = True
                bars = {n: bars[n] for n in names[:25]}
            algorithm.on_data(_Slice(bars))
            sessions_run += 1
        if day.weekday() < 5:
            last_trading_day = day
        calendar_day += dt.timedelta(days=1)

    assert starved, "the starvation month never armed; the fixture is broken"
    mom_dates = [row[0] for row in algorithm.results.get("MOM_12_1", [])]
    # The 15 starved names need ~253 sessions to re-align, so recovery is
    # expected about a year after the gap, not the next month.
    assert any(date > "2014-12" for date in mom_dates), (
        "no month after the skipped one ever emitted — the R-008 refusal "
        "spiral has returned"
    )

    algorithm.on_end_of_algorithm()
    log_lines = [line for line in algorithm.log_lines
                 if not line.startswith("ERROR:")]
    assert not any("INCOMPLETE" in line for line in algorithm.log_lines), (
        algorithm.log_lines[-3:]
    )
    log_path = tmp_path / "monthly_sim.log"
    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    specs, frame, meta = analyser.parse_log(log_path)
    assert specs == list(namespace["SPECIFICATIONS"])
    assert meta["dates"] == len({row for row in frame["date"]})
    # The starve poisons the 504-session residual factor tail for ~2 years,
    # so only the pre-starve months and the final recovered stretch emit
    # residual rows in a 52-month simulation; presence, not count, is the
    # invariant here (the first test pins the undisturbed count).
    assert (frame["spec"] == "RESIDUAL_MOM_6_1").sum() >= 3
    assert (frame["spec"] == "MOM_12_1").sum() >= 20


def test_prior_day_bar_keeps_prior_membership_when_new_month_selects_first(
    monthly_algorithm_class,
):
    """The new month's point-in-time selection cannot label yesterday's return."""
    namespace = monthly_algorithm_class
    algorithm = namespace["AlphaBatteryMonthly"]()
    algorithm.initialize()
    names = [f"SYM{i:02d}" for i in range(40)]

    algorithm.time = dt.datetime(2012, 1, 31)
    january = [_Fine(name, 100 + (index % 4), 100.0, 0.01)
               for index, name in enumerate(names)]
    algorithm._coarse(january)
    algorithm._fine(january)

    prior_session = dt.date(2012, 1, 31)
    algorithm.last_session = prior_session
    algorithm.sessions.append(prior_session)
    for name in names:
        algorithm.closes[name] = deque([100.0], maxlen=namespace["LOOKBACK"])
        algorithm.close_sessions[name] = deque(
            [prior_session], maxlen=namespace["LOOKBACK"]
        )

    # LEAN may run the February universe selection before delivering the
    # Jan-31 daily bar at the Feb-1 timestamp. The return and industry
    # classification still belong to the January membership snapshot.
    algorithm.time = dt.datetime(2012, 2, 1)
    new_names = names[:35] + [f"NEW{i:02d}" for i in range(5)]
    february = [_Fine(name, 200 + (index % 4), 101.0, 0.02)
                for index, name in enumerate(new_names)]
    algorithm._coarse(february)
    algorithm._fine(february)
    algorithm.on_data(_Slice({name: _Bar(101.0)
                              for name in set(names) | set(new_names)}))

    assert algorithm.factor_membership_months[-1] == (2012, 1)
    assert set(algorithm.industry_aggregates[-1]) == {100, 101, 102, 103}
    assert {size for _total, size in algorithm.industry_aggregates[-1].values()} == {10}

    # QCS0CR-001: the boundary exception must not become the rule. A
    # mutation that ALWAYS used the previous month's snapshot — month-stale
    # membership on every ordinary day — passed this test as written. The
    # next session is a plain February day (no selection change in its
    # slice), so it must record under the ACTIVE February selection,
    # including February's new industry codes.
    algorithm.time = dt.datetime(2012, 2, 2)
    algorithm.on_data(_Slice({name: _Bar(102.0)
                              for name in set(names) | set(new_names)}))
    assert algorithm.factor_membership_months[-1] == (2012, 2)
    assert set(algorithm.industry_aggregates[-1]) == {200, 201, 202, 203}
