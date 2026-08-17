"""Every LEAN algorithm in `research/lean/` must stay INCAPABLE of
reporting an alpha result.

Method V2 section 1.9 exempts a smoke test from the research look count
only if it cannot report an alpha statistic -- not if it merely happens not
to today. That is a property of the source, so it is checked against the
source: these files cannot be imported here because `AlgorithmImports`
exists only inside LEAN.

The guard iterates the DIRECTORY rather than naming one file. The first
version named `universe_smoke.py` explicitly, which left the delisting
probe unguarded the moment it was added -- exactly the gap that lets an
un-exempt run be reported as an exempt one.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

LEAN_DIR = Path(__file__).resolve().parents[1] / "research" / "lean"
# NOT named `*_test.py`: pytest collects that pattern, and these files
# import `AlgorithmImports`. The first name broke collection for the WHOLE
# suite, not just itself.
LEAN_FILES = sorted(p for p in LEAN_DIR.glob("*.py") if p.name != "__init__.py")
RESULT_ALGORITHMS = [
    LEAN_DIR / "alpha_battery_monthly.py",
    LEAN_DIR / "alpha_battery_short.py",
    LEAN_DIR / "alpha_stage1_replications.py",
    LEAN_DIR / "alpha_stage1_benchmark.py",
    LEAN_DIR / "universe_benchmark.py",
]

#: Every LEAN call that can open, close or size a position.
ORDERING_CALLS = frozenset({
    "SetHoldings", "MarketOrder", "LimitOrder", "StopMarketOrder",
    "StopLimitOrder", "MarketOnOpenOrder", "MarketOnCloseOrder",
    "Buy", "Sell", "Liquidate", "SetLeverage", "Order",
    "set_holdings", "market_order", "limit_order", "stop_market_order",
    "stop_limit_order", "market_on_open_order", "market_on_close_order",
    "buy", "sell", "liquidate", "set_leverage", "order",
})


def test_the_lean_directory_is_not_empty():
    """A glob that silently matches nothing would make every test below
    vacuously green."""
    assert LEAN_FILES, f"no LEAN algorithms found under {LEAN_DIR}"


SOURCE = LEAN_DIR / "universe_smoke.py"


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"))


LEGACY_CALLBACKS = {"Initialize", "OnData", "OnEndOfAlgorithm"}
LEGACY_ATTRIBUTES = {
    "SetStartDate", "SetEndDate", "SetCash", "AddUniverse", "AddSecurity",
    "RemoveSecurity", "AddEquity", "Log", "Error", "UniverseSettings",
    "Transactions", "OrdersCount", "Bars", "Delistings", "Keys", "Close",
    "Volume", "Symbol", "Value", "Time", "HasFundamentalData",
    "DollarVolume", "MarketCap", "CompanyProfile", "SharesOutstanding",
    "AssetClassification", "MorningstarIndustryCode", "FinancialStatements",
    "IncomeStatement", "BalanceSheet", "CashFlowStatement", "OperationRatios",
    # CCR3-C: every remaining PascalCase counterpart of a member these files
    # actually access. A LONE legacy leaf (`.GrossProfit.value`) survived the
    # guard because only chain roots and `.Value` were listed — the same
    # incomplete-inventory shape as CR2-001, one level down. Enum members are
    # included because `Resolution.Daily` is legacy exactly like `SetCash`.
    "Price", "AdjustedPrice", "GrossProfit", "TotalAssets", "TotalDebt",
    "NetIncome", "FreeCashFlow", "ROE", "ROA", "GrossMargin",
    "MorningstarSectorCode", "TotalEquityGrossMinorityInterest",
    "Daily", "Adjusted", "Raw", "Delisted",
}


@pytest.mark.parametrize("path", LEAN_FILES, ids=lambda p: p.name)
def test_lean_sources_use_one_current_python_api_dialect(path):
    """Mixed C#/Python member names compile too permissively in LEAN.

    QuantConnect's wrapper currently aliases many legacy names, but the
    cloud editor, stubs and documentation use snake_case.  A mixed file let
    several missed conversions survive the first fix, so executable AST
    names are checked rather than comments or prose.
    """
    tree = _tree(path)
    callbacks = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    offenders = sorted((callbacks & LEGACY_CALLBACKS) | (attributes & LEGACY_ATTRIBUTES))
    assert not offenders, f"{path.name} still uses legacy LEAN names: {offenders}"
    algorithms = [
        node for node in tree.body
        if isinstance(node, ast.ClassDef)
        and any(isinstance(base, ast.Name) and base.id == "QCAlgorithm"
                for base in node.bases)
    ]
    assert len(algorithms) == 1, f"{path.name} must define one QCAlgorithm"
    methods = {
        node.name for node in algorithms[0].body if isinstance(node, ast.FunctionDef)
    }
    assert {"initialize", "on_end_of_algorithm"} <= methods


@pytest.mark.parametrize("path", LEAN_FILES, ids=lambda p: p.name)
def test_lean_algorithms_do_not_shadow_qcalgorithm_members(path):
    reserved = {
        "fundamentals", "securities", "portfolio", "transactions", "settings",
        "universe_settings", "time", "history", "benchmark", "schedule",
        "notify", "insights", "universe", "algorithm_mode", "live_mode",
    }
    offenders = []
    for node in ast.walk(_tree(path)):
        targets = []
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if (isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                    and target.attr in reserved):
                offenders.append(f"line {node.lineno}: self.{target.attr}")
    assert not offenders, f"{path.name} shadows QCAlgorithm members: {offenders}"


@pytest.mark.parametrize("path", LEAN_FILES, ids=lambda p: p.name)
def test_the_smoke_test_places_no_orders_by_construction(path):
    called = {
        node.func.attr
        for node in ast.walk(_tree(path))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    offenders = sorted(called & ORDERING_CALLS)
    assert not offenders, (
        "the smoke test calls ordering APIs and is therefore no longer "
        f"exempt from the Method V2 look count: {offenders}"
    )


EXEMPTION_MARKER = "NO ALPHA STATISTIC"
LOOK_MARKER = "counted research look"


def _flat(path: Path) -> str:
    """Source with runs of whitespace collapsed.

    A declaration must not depend on where a docstring happens to wrap.
    The first version matched raw text, so `alpha_battery_short.py` failed
    its own declaration purely because "counted research look" straddled a
    line break -- and `alpha_battery_monthly.py` passed only by the luck of
    wrapping differently.
    """
    return " ".join(path.read_text(encoding="utf-8").split())


def _claims_exemption(path: Path) -> bool:
    return EXEMPTION_MARKER in _flat(path)


@pytest.mark.parametrize("path", LEAN_FILES, ids=lambda p: p.name)
def test_every_lean_file_declares_its_look_status(path):
    """A file is either exempt or a counted look, and must say which.

    The alpha battery legitimately computes IC and decile spreads, so the
    blanket "no file may compute a statistic" rule would have to be
    weakened to admit it. Weakening a guard to fit new code is how guards
    stop meaning anything, so the rule is restated at the level that
    actually matters: a file claiming exemption must BE inert, and a file
    that is not inert must declare that running it costs a look.
    """
    text = _flat(path)
    exempt = EXEMPTION_MARKER in text
    counted = LOOK_MARKER in text
    assert exempt != counted, (
        f"{path.name} must declare exactly one of "
        f"{EXEMPTION_MARKER!r} (inert) or {LOOK_MARKER!r} (costs a look); "
        f"exempt={exempt} counted={counted}"
    )


@pytest.mark.parametrize("path", [p for p in LEAN_FILES if _claims_exemption(p)],
                         ids=lambda p: p.name)
def test_the_smoke_test_computes_no_alpha_statistic(path):
    """Checked against CODE, not prose.

    The first version of this test scanned the raw text and failed on the
    file's own docstring, which explains at length why it reports no
    Sharpe. Explaining an absence is the opposite of the defect: the
    invariant is that nothing EXECUTABLE computes a performance or signal
    metric, so identifiers and attributes are inspected and comments and
    docstrings are ignored.
    """
    tree = _tree(path)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc)

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            names.add(node.attr.lower())
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value not in docstrings:
                names.add(node.value.lower())

    banned = ("sharpe", "sortino", "information_coefficient", "spearman",
              "informationratio", "annualized_return")
    offenders = sorted(
        {b for b in banned if any(b in name for name in names)}
    )
    assert not offenders, (
        f"the smoke test computes or reports {offenders}, which makes its "
        "run a counted research look rather than an exempt smoke test"
    )


def test_the_universe_screens_match_the_owner_specification():
    """The three screens are the contract. A silently loosened screen would
    make a cloud run incomparable to the local one it is meant to replicate.
    """
    namespace: dict = {}
    for node in _tree(SOURCE).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "UNIVERSES":
            namespace = ast.literal_eval(node.value)
    assert namespace == {
        "A_large": {"min_price": 5.0, "min_cap": 10_000_000_000.0, "min_adv": 25_000_000.0},
        "B_core": {"min_price": 5.0, "min_cap": 500_000_000.0, "min_adv": 5_000_000.0},
        "C_broad": {"min_price": 3.0, "min_cap": 100_000_000.0, "min_adv": 1_000_000.0},
    }, namespace


def test_prices_are_raw_not_split_adjusted():
    """ABR-003's cloud counterpart. A split-adjusted price lets a stock pass
    a $5 screen it never met at the time, which changes membership."""
    text = SOURCE.read_text(encoding="utf-8")
    assert "DataNormalizationMode.RAW" in text


@pytest.mark.parametrize("path", RESULT_ALGORITHMS, ids=lambda p: p.name)
def test_result_returns_use_split_adjusted_trade_bars(path):
    """Raw closes belong in the screen, not in return arithmetic."""
    text = path.read_text(encoding="utf-8")
    assert "DataNormalizationMode.ADJUSTED" in text
    assert "c.price" in text and "f.price" in text


def test_delistings_are_observed_rather_than_assumed():
    """The entire reason for using QuantConnect. If the algorithm never
    looks at Delistings, a cloud run proves nothing the local run did not."""
    text = SOURCE.read_text(encoding="utf-8")
    assert "data.delistings" in text and "DelistingType.DELISTED" in text


@pytest.mark.parametrize("path", RESULT_ALGORITHMS, ids=lambda p: p.name)
def test_result_algorithms_use_delisting_outcomes(path):
    """Smoke coverage is not evidence that result-producing files use deaths."""
    text = path.read_text(encoding="utf-8")
    assert "data.delistings" in text
    assert "DelistingType.DELISTED" in text
    assert "terminal_prices" in text
    assert "add_security(symbol, Resolution.DAILY)" in text


@pytest.mark.parametrize("path", RESULT_ALGORITHMS, ids=lambda p: p.name)
def test_result_algorithms_stage_the_next_session_entry(path):
    text = path.read_text(encoding="utf-8")
    assert "self.last_session" in text
    staged_entry = all(token in text for token in (
        "self.staged", "score_session", "_bind_staged_entry"
    ))
    month_end_entry = all(token in text for token in (
        "previous_session", "_is_new_calendar_month", "score_session"
    ))
    assert staged_entry or month_end_entry


def test_the_declared_window_is_retargeted_not_patched():
    """Provenance. Run 3 of 2026-08-16 was produced by rewriting
    set_start_date/set_end_date at upload time, so the committed file said
    2013-2016 while the run that produced the "11 delistings" number used
    2022-2023. A reader comparing the document to the file would have found
    a mismatch with no way to tell which was right.

    The window is now a declared constant, and the driver rewrites THAT.
    """
    from scripts.run_quantconnect_smoke import _retarget_window

    source = (LEAN_DIR / "universe_smoke.py").read_text(encoding="utf-8")
    assert "START = (" in source and "END = (" in source
    assert "set_start_date(*START)" in source, "the algorithm must consume the constant"

    out = _retarget_window(source, "2022-06-01", "2023-12-31")
    assert "START = (2022, 6, 1)" in out
    assert "END = (2023, 12, 31)" in out
    # And it must not have touched anything else.
    assert out.replace("START = (2022, 6, 1)", "START = (2013, 1, 1)").replace(
        "END = (2023, 12, 31)", "END = (2016, 12, 31)"
    ) == source


def test_retargeting_refuses_rather_than_running_an_unknown_window():
    """Failing closed matters more than convenience here: a driver that
    silently ran the algorithm's own dates after a failed substitution
    would produce a result labelled with the window the caller asked for
    and computed over a different one."""
    from scripts.run_quantconnect_smoke import _retarget_window

    with pytest.raises(SystemExit) as excinfo:
        _retarget_window("class Foo:\n    pass\n", "2022-06-01", None)
    assert "refusing" in str(excinfo.value)


@pytest.mark.parametrize(
    ("start", "end", "message"),
    [("2022-02-30", None, "real YYYY-MM-DD"),
     ("2024-01-01", "2023-01-01", "on or before")],
)
def test_retargeting_refuses_invalid_or_reversed_dates(start, end, message):
    from scripts.run_quantconnect_smoke import _retarget_window

    source = (LEAN_DIR / "universe_smoke.py").read_text(encoding="utf-8")
    with pytest.raises(SystemExit, match=message):
        _retarget_window(source, start, end)


def test_backtest_waiter_reports_a_stalled_run_without_relaunching(monkeypatch):
    from research.quantconnect import QuantConnectError
    from scripts import run_quantconnect_smoke as runner

    class Client:
        calls = 0

        def read_backtest(self, project_id, backtest_id):
            self.calls += 1
            return {"backtest": {"completed": False, "progress": 0.865}}

    clock = iter((0.0, 0.0, 0.0, 10.0, 10.0))
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(runner.time, "sleep", lambda _: None)
    client = Client()
    with pytest.raises(QuantConnectError, match="no progress.*inspect"):
        runner._wait_for_backtest(
            client, 123, "backtest", max_wait_seconds=100, stall_seconds=10
        )
    assert client.calls == 2


def test_backtest_waiter_stalls_even_when_progress_is_never_published(monkeypatch):
    from research.quantconnect import QuantConnectError
    from scripts import run_quantconnect_smoke as runner

    class Client:
        def read_backtest(self, project_id, backtest_id):
            return {"backtest": {"completed": False, "progress": None}}

    moments = iter((0.0, 0.0, 0.0, 11.0, 11.0))
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(moments))
    monkeypatch.setattr(runner.time, "sleep", lambda _seconds: None)
    with pytest.raises(QuantConnectError, match="no progress.*progress=None.*inspect"):
        runner._wait_for_backtest(
            Client(), 123, "backtest", max_wait_seconds=100, stall_seconds=10
        )


def test_backtest_waiter_raises_on_the_overall_deadline_instead_of_returning(monkeypatch):
    """CCR3-B: the OUTER deadline path was untested.

    Both stall tests hold progress constant, so a mutation making the final
    timeout RETURN a fake result survived the suite — and a returned dict
    flows straight into the provenance summary as if the run completed. A
    run whose progress keeps advancing must still raise once the total wait
    is exhausted, never hand back an incomplete backtest as a result.
    """
    from research.quantconnect import QuantConnectError
    from scripts import run_quantconnect_smoke as runner

    class Client:
        calls = 0

        def read_backtest(self, project_id, backtest_id):
            self.calls += 1
            # Progress ADVANCES on every poll: the stall detector never fires.
            return {"backtest": {"completed": False, "progress": self.calls / 100.0}}

    moments = iter((0.0, 0.0, 0.0, 4.0, 4.0, 8.0, 8.0, 12.0))
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(moments))
    monkeypatch.setattr(runner.time, "sleep", lambda _seconds: None)
    with pytest.raises(QuantConnectError, match="did not finish within.*inspect"):
        runner._wait_for_backtest(
            Client(), 123, "backtest", max_wait_seconds=10, stall_seconds=10
        )
