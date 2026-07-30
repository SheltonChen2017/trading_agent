"""
Pins the Bonferroni multiplicity convention for research runner scripts.

Why a source-level (AST) test rather than a behavioral one: the bug this
guards against lives in a *research script's* argument, not in library
behavior. `out_of_sample_significance_by_block()` correctly applies
whatever `n_tests` it is handed -- and is already thoroughly tested for
that in tests/test_backtest.py. The defect found on 2026-07-29 was that
two multi-signal runners handed it the per-signal default (2) while
scanning 6 and 20 cells respectively for a survivor, making their
thresholds 3x and 10x too lenient in the exact direction that
manufactures a false positive. Nothing about library behavior can catch
that; only the call site can.

The invariant is NOT "never pass a literal n_tests" -- a genuinely
single-signal runner (run_analyst_target_significance_check.py) correctly
passes 2, one signal's dip + up. The invariant is that a runner scanning
SEVERAL signals must DERIVE its denominator from the list it actually
loops over, so that adding a signal tightens the correction automatically
instead of silently leaving it stale.
"""
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"

# Runners that scan more than one signal in a single pass, and therefore
# must derive n_tests rather than hardcode it.
MULTI_SIGNAL_RUNNERS = (
    "run_macro_signals_significance_check.py",
    "run_execution_timing_revalidation.py",
)

SIGNIFICANCE_FNS = {
    "out_of_sample_significance",
    "out_of_sample_significance_by_date",
    "out_of_sample_significance_by_block",
}


def _n_tests_assignment(tree: ast.Module) -> ast.expr | None:
    """The right-hand side of the module's `n_tests = ...` assignment."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "n_tests":
                    return node.value
    return None


def test_multi_signal_runners_derive_their_bonferroni_denominator():
    for filename in MULTI_SIGNAL_RUNNERS:
        path = SCRIPTS_DIR / filename
        assert path.exists(), f"{filename} is missing -- update MULTI_SIGNAL_RUNNERS"
        tree = ast.parse(path.read_text(encoding="utf-8"))

        rhs = _n_tests_assignment(tree)
        assert rhs is not None, (
            f"{filename} scans multiple signals but never assigns n_tests -- it is "
            "presumably relying on the per-signal default of 2, which under-corrects."
        )
        # A derived count is an arithmetic expression (len(runs) * 2, etc.).
        # A bare constant is exactly the staleness this test exists to stop.
        assert isinstance(rhs, ast.BinOp), (
            f"{filename} must DERIVE n_tests from the collection it loops over "
            f"(e.g. len(runs) * 2), not hardcode it -- got {ast.dump(rhs)}. A hardcoded "
            "count silently stops matching the run when a signal is added."
        )
        assert "len" in ast.dump(rhs), (
            f"{filename}'s n_tests expression does not reference len(...) of its run "
            f"list, so it cannot track the number of signals actually scanned: {ast.unparse(rhs)}"
        )


def test_multi_signal_runners_do_not_pass_a_literal_n_tests_at_any_call_site():
    """
    Guards the other half: deriving n_tests correctly but then still
    passing a literal 2 downstream would leave the derived value dead.

    Checks BOTH the significance functions themselves and any locally
    defined wrapper that forwards an n_tests parameter (these runners use
    a `_run_one(...)` helper) -- and checks positional as well as keyword
    arguments. An earlier version of this test only inspected direct
    keyword arguments to the significance functions, and a deliberate
    mutation that passed `_run_one(name, data, scan_fn, 2)` through the
    wrapper SURVIVED it. Found by mutation-testing this test.
    """
    for filename in MULTI_SIGNAL_RUNNERS:
        tree = ast.parse((SCRIPTS_DIR / filename).read_text(encoding="utf-8"))

        # Every function reachable here that takes an n_tests argument,
        # mapped to the positional index that argument occupies.
        forwarders: dict[str, int] = {name: -1 for name in SIGNIFICANCE_FNS}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                params = [a.arg for a in node.args.args]
                if "n_tests" in params:
                    forwarders[node.name] = params.index("n_tests")

        checked = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn_name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
            if fn_name not in forwarders:
                continue
            index = forwarders[fn_name]

            for kw in node.keywords:
                if kw.arg == "n_tests":
                    checked += 1
                    assert not isinstance(kw.value, ast.Constant), (
                        f"{filename} passes a hardcoded n_tests={ast.unparse(kw.value)} to "
                        f"{fn_name}() -- it must forward the derived denominator instead."
                    )
            if index >= 0 and len(node.args) > index:
                checked += 1
                assert not isinstance(node.args[index], ast.Constant), (
                    f"{filename} passes a hardcoded {ast.unparse(node.args[index])} as "
                    f"{fn_name}()'s n_tests argument (position {index}) -- it must forward "
                    "the derived denominator instead."
                )
        assert checked, (
            f"{filename} never passes an explicit n_tests anywhere -- it would fall back to "
            "the per-signal default of 2, which under-corrects a multi-signal run."
        )


def test_single_signal_runner_is_correctly_left_alone():
    """
    The convention is about matching the cells actually scanned, not about
    always inflating the denominator. A one-signal runner passing 2 (dip +
    up) is correct, and this test documents that so the AST checks above
    are never over-applied to it.
    """
    path = SCRIPTS_DIR / "run_analyst_target_significance_check.py"
    assert path.exists()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    scan_fn_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None))
        in SIGNIFICANCE_FNS
    ]
    assert len(scan_fn_calls) == 1, (
        "run_analyst_target_significance_check.py now makes more than one significance "
        "call -- if it scans multiple cells it must move to a derived n_tests and be "
        "added to MULTI_SIGNAL_RUNNERS."
    )


def test_bonferroni_denominators_match_the_documented_cell_counts():
    """
    Evaluates each runner's own n_tests expression against its own run
    list, so the arithmetic is checked rather than assumed. This is the
    test that would have failed on the original bug.
    """
    from backtest.engine import bonferroni_threshold

    expected = {
        # 3 macro signals x 2 directions
        "run_macro_signals_significance_check.py": 6,
        # 5 signals x 2 entry timings x 2 directions
        "run_execution_timing_revalidation.py": 20,
    }
    for filename, expected_cells in expected.items():
        tree = ast.parse((SCRIPTS_DIR / filename).read_text(encoding="utf-8"))
        runs_len = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "runs":
                        assert isinstance(node.value, (ast.List, ast.Tuple)), (
                            f"{filename}'s `runs` is not a literal list/tuple, so its length "
                            "cannot be verified statically."
                        )
                        runs_len = len(node.value.elts)
        assert runs_len is not None, f"{filename} defines no `runs` list to derive n_tests from"

        rhs = ast.unparse(_n_tests_assignment(tree))
        env = {"len": len, "runs": [None] * runs_len}
        if "ENTRY_TIMINGS" in rhs:
            timings = None
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "ENTRY_TIMINGS":
                            timings = len(node.value.elts)
            assert timings, f"{filename} references ENTRY_TIMINGS but does not define it as a literal"
            env["ENTRY_TIMINGS"] = [None] * timings

        actual = eval(rhs, {"__builtins__": {"len": len}}, env)  # noqa: S307 - static repo source
        assert actual == expected_cells, (
            f"{filename}: n_tests evaluates to {actual}, expected {expected_cells} "
            f"({rhs}). Either the run list changed or the correction is stale."
        )
        # And the threshold that follows must be strictly tighter than the
        # per-signal default that caused the original defect.
        assert bonferroni_threshold(actual) < bonferroni_threshold(2)


def test_the_plainly_named_significance_function_points_at_the_block_bootstrap():
    """Documentation regression, deliberately a source test.

    out_of_sample_significance()'s docstring opened "THE correct way to test
    whether a signal's edge is statistically real" while resampling individual
    ROWS -- exactly what bonferroni_threshold()'s own SECOND CAUTION, a few
    dozen lines above it, warns against. The function with the most
    authoritative name carried the most confident claim, so a future caller
    reaching for the obvious name got the weakest check (independent review,
    2026-07-30).

    There is no behavioral assertion available here: the defect is which
    function the docs send you to, which only the text can express.
    """
    from backtest.engine import out_of_sample_significance

    doc = " ".join((out_of_sample_significance.__doc__ or "").split())
    assert "THE correct way" not in doc, (
        "out_of_sample_significance() must not claim to be the definitive "
        "check -- it resamples rows and inflates significance."
    )
    assert "out_of_sample_significance_by_block()" in doc, (
        "the docstring must send callers to the block bootstrap, which is "
        "this project's standing bar for claiming an edge is real."
    )
    assert "NOT SUFFICIENT ON ITS OWN" in doc


def test_the_bonferroni_default_documents_that_it_covers_one_signal_only():
    """The default of 2 cannot detect its own misuse, so the docstring is the
    only place a sweep author is warned."""
    from backtest.engine import out_of_sample_significance

    # Whitespace-collapsed: these phrases straddle line wraps in the source,
    # and a docstring test that breaks on reflowing a paragraph is a nuisance
    # rather than a guard.
    doc = " ".join((out_of_sample_significance.__doc__ or "").split())
    assert "ONE signal" in doc, "must say the default covers a single signal"
    assert "total cell count" in doc, "must tell sweeps to pass the full cell count"


if __name__ == "__main__":
    test_multi_signal_runners_derive_their_bonferroni_denominator()
    test_multi_signal_runners_do_not_pass_a_literal_n_tests_at_any_call_site()
    test_single_signal_runner_is_correctly_left_alone()
    test_bonferroni_denominators_match_the_documented_cell_counts()
    test_the_plainly_named_significance_function_points_at_the_block_bootstrap()
    test_the_bonferroni_default_documents_that_it_covers_one_signal_only()
    print("All significance-multiplicity tests passed.")
