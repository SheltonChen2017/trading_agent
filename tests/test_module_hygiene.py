"""
Guards against three classes of rot found by an orphan/dead-code audit
(independent review, 2026-07-29):

  * documentation and printed instructions naming symbols that do not exist,
  * imports that no longer have a use,
  * duplicate private wrappers left behind by a refactor.

Deliberately NOT here: a general "every import is used" rule. A first version
of that check immediately produced false positives on `from __future__ import
annotations`, and it would also have to model intentional re-exports
(strategies/trend_vol_rotation re-exports classify_trend) and TYPE_CHECKING
string annotations (order_lifecycle's AssistantStore) -- all legitimate. That
is a linter's job, not a hand-rolled test's; what is pinned instead is the
narrower, reliable property that the SPECIFIC names removed by the audit do
not come back.

These are cheap, deterministic checks. The first one matters most: the PEAD
usage snippet printed by scripts/run_new_signals_report.py told users to
`from data.earnings_data import fetch_earnings_surprises`, a function that has
never existed (the real name is fetch_earnings_history). Anyone copying the
displayed instructions got an immediate ImportError, which also made an
implemented-but-dormant signal look integrated when its only executable
guidance was broken.
"""
from __future__ import annotations

import ast
import importlib
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Directories whose .py files are checked for referencing-real-symbols.
SOURCE_DIRS = ("assistant", "backtest", "data", "execution", "risk", "scripts",
               "signals", "strategies", "tests")


def _python_files():
    for directory in SOURCE_DIRS:
        yield from (REPO_ROOT / directory).rglob("*.py")
    for name in ("config.py", "baskets.py", "market_analytics.py"):
        candidate = REPO_ROOT / name
        if candidate.exists():
            yield candidate


def test_no_reference_anywhere_to_a_nonexistent_earnings_loader():
    """The obsolete name must not reappear -- in code, docstrings, or printed
    help. data.earnings_data exports fetch_earnings_history.

    The forbidden string is assembled at runtime rather than written literally,
    because this file has to be able to talk about it: a literal would make
    this guard flag itself (it did, on the first run).
    """
    forbidden = "fetch_earnings_" + "surprises"
    offenders = []
    for path in _python_files():
        if path.resolve() == pathlib.Path(__file__).resolve():
            continue
        if forbidden in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        f"{forbidden}() does not exist; use fetch_earnings_history(). Found in: {offenders}"
    )


def test_the_documented_earnings_loader_is_actually_importable():
    """The name the docs now use has to resolve -- otherwise this test just
    swaps one broken string for another."""
    module = importlib.import_module("data.earnings_data")
    assert hasattr(module, "fetch_earnings_history")
    assert callable(module.fetch_earnings_history)


def test_every_symbol_named_in_the_pead_snippet_resolves():
    """Parse the actual snippet the script prints and check each `from X import
    Y` line it advertises, so the instructions cannot drift from reality
    again."""
    source = (REPO_ROOT / "scripts" / "run_new_signals_report.py").read_text(encoding="utf-8")
    pairs = re.findall(r"from\s+([\w.]+)\s+import\s+(\w+)", source)
    assert pairs, "no import instructions found -- has the snippet moved?"
    for module_name, symbol in pairs:
        module = importlib.import_module(module_name)
        assert hasattr(module, symbol), (
            f"scripts/run_new_signals_report.py advertises {module_name}.{symbol}, "
            "which does not exist"
        )


def test_the_pead_snippet_does_not_call_a_loader_it_never_imported():
    """The import-line check above is not sufficient on its own: the snippet
    could import the correct name and then CALL a different one. A deliberate
    mutation renaming only the call site (fetch_earnings_history -> a
    nonexistent name) survived the first version of this file -- found by
    mutation-testing the test.

    Every fetch_*/scan_* name written as a CALL anywhere in this script --
    executable code, docstring, or printed snippet -- must be a function that
    actually exists somewhere in the project. Checking existence rather than
    "was imported here" deliberately: the module docstring legitimately
    mentions real functions it does not import (`fetch_historical()`), and
    flagging those would be a false positive, which an earlier version of this
    test produced.
    """
    source = (REPO_ROOT / "scripts" / "run_new_signals_report.py").read_text(encoding="utf-8")

    real_names: set[str] = set()
    for directory in ("data", "signals", "backtest", "strategies"):
        for path in (REPO_ROOT / directory).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            real_names.update(
                node.name for node in tree.body if isinstance(node, ast.FunctionDef)
            )
    for name in ("market_analytics.py", "baskets.py"):
        tree = ast.parse((REPO_ROOT / name).read_text(encoding="utf-8"))
        real_names.update(node.name for node in tree.body if isinstance(node, ast.FunctionDef))

    # Every fetch_*/scan_* identifier, not only those immediately followed by
    # "(": a name passed as a REFERENCE (`partial(scan_pead, ...)`) is just as
    # broken if it does not exist, and a call-site-only regex missed exactly
    # that -- a `scan_pead` -> `scan_pead_typo` mutation survived.
    mentioned = set(re.findall(r"\b((?:fetch|scan)_\w+)\b", source))

    # Names this file binds itself are not claims about the project's API.
    tree = ast.parse(source)
    locally_bound = {
        node.id for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }
    locally_bound.update(
        arg.arg for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) for arg in node.args.args
    )
    # Keyword-argument NAMES of functions defined elsewhere (run_backtest's
    # scan_fn=/scan_kwargs=) are parameters, not functions in their own right.
    locally_bound.update({"scan_fn", "scan_kwargs"})

    candidates = mentioned - locally_bound
    assert candidates, "no fetch_*/scan_* references found -- has the snippet moved?"
    nonexistent = sorted(candidates - real_names)
    assert not nonexistent, (
        "scripts/run_new_signals_report.py names function(s) that do not exist anywhere "
        f"in the project, so anyone copying its instructions gets an error: {nonexistent}"
    )


def test_the_duplicate_private_soxx_soxl_wrapper_is_gone():
    """A private _generate_soxx_soxl_rebalance_proposals() duplicated the
    public wrapper with zero callers -- a leftover from the generic
    leveraged-pair refactor."""
    source = (REPO_ROOT / "assistant" / "strategy_proposals.py").read_text(encoding="utf-8")
    assert "_generate_soxx_soxl_rebalance_proposals" not in source


def test_the_public_soxx_soxl_wrapper_still_delegates_to_the_generic_path():
    """Removing the private duplicate must not touch the public compatibility
    surface, which is what callers and tests actually use."""
    from assistant import strategy_proposals

    assert hasattr(strategy_proposals, "generate_soxx_soxl_rebalance_proposals")
    tree = ast.parse((REPO_ROOT / "assistant" / "strategy_proposals.py").read_text(encoding="utf-8"))
    wrapper = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "generate_soxx_soxl_rebalance_proposals"
    )
    body = ast.unparse(wrapper)
    assert "generate_leveraged_pair_rebalance_proposals" in body, (
        "the public wrapper must keep delegating to the generic implementation"
    )
    assert "SOXX_SOXL_PAIR" in body


def test_no_unused_imports_in_the_modules_the_audit_cleaned():
    """Pins the five removals so they cannot silently return. Deliberately
    scoped to the audited files rather than the whole repo: a repo-wide unused-
    import rule would need to model re-exports (strategies/trend_vol_rotation
    intentionally re-exports classify_trend) and TYPE_CHECKING string
    annotations (order_lifecycle's AssistantStore), both of which are
    legitimate here and would produce false failures."""
    cleaned = {
        "assistant/allocation_batch.py": "timezone",
        "assistant/context_builder.py": "MARKET_BENCHMARK_TICKERS",
        "backtest/portfolio_simulator.py": "np",
        "scripts/personal_assistant_ui.py": "pd",
        "scripts/run_leverage_rotation_backtest.py": "max_drawdown_pct",
    }
    for relative, name in cleaned.items():
        tree = ast.parse((REPO_ROOT / relative).read_text(encoding="utf-8"))
        imported = {
            (alias.asname or alias.name.split(".")[0])
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert name not in imported, (
            f"{relative} re-imported {name}, which the orphan audit removed as unused"
        )


if __name__ == "__main__":
    test_no_reference_anywhere_to_a_nonexistent_earnings_loader()
    test_the_documented_earnings_loader_is_actually_importable()
    test_every_symbol_named_in_the_pead_snippet_resolves()
    test_the_pead_snippet_does_not_call_a_loader_it_never_imported()
    test_the_duplicate_private_soxx_soxl_wrapper_is_gone()
    test_the_public_soxx_soxl_wrapper_still_delegates_to_the_generic_path()
    test_no_unused_imports_in_the_modules_the_audit_cleaned()
    print("All module-hygiene tests passed.")
