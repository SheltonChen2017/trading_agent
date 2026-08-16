"""The LEAN smoke test must stay INCAPABLE of reporting an alpha result.

Method V2 section 1.9 exempts a smoke test from the research look count
only if it cannot report an alpha statistic -- not if it merely happens not
to today. That is a property of the source, so it is checked against the
source: the file cannot be imported here because `AlgorithmImports` only
exists inside LEAN.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

# NOT named `*_test.py`: pytest collects that pattern, and this file
# imports `AlgorithmImports`, which exists only inside LEAN. The first
# name broke collection for the WHOLE suite, not just itself.
SOURCE = Path(__file__).resolve().parents[1] / "research" / "lean" / "universe_smoke.py"

#: Every LEAN call that can open, close or size a position.
ORDERING_CALLS = frozenset({
    "SetHoldings", "MarketOrder", "LimitOrder", "StopMarketOrder",
    "StopLimitOrder", "MarketOnOpenOrder", "MarketOnCloseOrder",
    "Buy", "Sell", "Liquidate", "SetLeverage", "Order",
})


def _tree() -> ast.AST:
    return ast.parse(SOURCE.read_text(encoding="utf-8"))


def test_the_smoke_test_places_no_orders_by_construction():
    called = {
        node.func.attr
        for node in ast.walk(_tree())
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    offenders = sorted(called & ORDERING_CALLS)
    assert not offenders, (
        "the smoke test calls ordering APIs and is therefore no longer "
        f"exempt from the Method V2 look count: {offenders}"
    )


def test_the_smoke_test_computes_no_alpha_statistic():
    """Checked against CODE, not prose.

    The first version of this test scanned the raw text and failed on the
    file's own docstring, which explains at length why it reports no
    Sharpe. Explaining an absence is the opposite of the defect: the
    invariant is that nothing EXECUTABLE computes a performance or signal
    metric, so identifiers and attributes are inspected and comments and
    docstrings are ignored.
    """
    tree = _tree()
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
    for node in _tree().body:
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
