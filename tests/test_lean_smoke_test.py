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

#: Every LEAN call that can open, close or size a position.
ORDERING_CALLS = frozenset({
    "SetHoldings", "MarketOrder", "LimitOrder", "StopMarketOrder",
    "StopLimitOrder", "MarketOnOpenOrder", "MarketOnCloseOrder",
    "Buy", "Sell", "Liquidate", "SetLeverage", "Order",
})


def test_the_lean_directory_is_not_empty():
    """A glob that silently matches nothing would make every test below
    vacuously green."""
    assert LEAN_FILES, f"no LEAN algorithms found under {LEAN_DIR}"


SOURCE = LEAN_DIR / "universe_smoke.py"


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"))


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


@pytest.mark.parametrize("path", LEAN_FILES, ids=lambda p: p.name)
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
    assert "DataNormalizationMode.Raw" in text


def test_delistings_are_observed_rather_than_assumed():
    """The entire reason for using QuantConnect. If the algorithm never
    looks at Delistings, a cloud run proves nothing the local run did not."""
    text = SOURCE.read_text(encoding="utf-8")
    assert "Delistings" in text and "DelistingType.Delisted" in text


def test_the_declared_window_is_retargeted_not_patched():
    """Provenance. Run 3 of 2026-08-16 was produced by rewriting
    SetStartDate/SetEndDate at upload time, so the committed file said
    2013-2016 while the run that produced the "11 delistings" number used
    2022-2023. A reader comparing the document to the file would have found
    a mismatch with no way to tell which was right.

    The window is now a declared constant, and the driver rewrites THAT.
    """
    from scripts.run_quantconnect_smoke import _retarget_window

    source = (LEAN_DIR / "universe_smoke.py").read_text(encoding="utf-8")
    assert "START = (" in source and "END = (" in source
    assert "SetStartDate(*START)" in source, "the algorithm must consume the constant"

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
