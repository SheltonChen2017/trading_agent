from __future__ import annotations

import ast
import inspect

import pytest

import research.analyst_revisions_v2.statistics as statistics_module
from research.analyst_revisions_v2.statistics import (
    AnalystStatisticsContractError,
    run_horizon_aware_block_bootstrap,
)


def test_twenty_session_outcome_refuses_one_session_block_before_delegate() -> None:
    calls: list[object] = []

    def delegate(*args, **kwargs):
        calls.append((args, kwargs))
        return {"should": "not run"}

    with pytest.raises(AnalystStatisticsContractError, match="at least"):
        run_horizon_aware_block_bootstrap(
            delegate,
            [0.1, -0.1],
            horizon_sessions=20,
            block_length=1,
            n_bootstrap=2_000,
        )
    assert calls == []


def test_matching_horizon_delegates_exact_arguments_once() -> None:
    sentinel = object()
    calls = []

    def delegate(values, *, block_length, n_bootstrap, seed):
        calls.append((values, block_length, n_bootstrap, seed))
        return sentinel

    values = [0.1, -0.1, 0.2]
    result = run_horizon_aware_block_bootstrap(
        delegate,
        values,
        horizon_sessions=20,
        block_length=20,
        n_bootstrap=2_000,
        seed=7,
    )
    assert result is sentinel
    assert calls == [(values, 20, 2_000, 7)]


@pytest.mark.parametrize(
    ("horizon_sessions", "block_length"),
    [
        (True, 20),
        (0, 20),
        (-1, 20),
        (1.0, 20),
        (20, True),
        (20, 0),
        (20, -1),
        (20, 20.0),
    ],
)
def test_horizon_and_block_are_exact_positive_integers_before_delegate(
    horizon_sessions, block_length
) -> None:
    called = False

    def delegate(**kwargs):
        nonlocal called
        called = True

    with pytest.raises(AnalystStatisticsContractError, match="positive integer"):
        run_horizon_aware_block_bootstrap(
            delegate,
            horizon_sessions=horizon_sessions,
            block_length=block_length,
        )
    assert called is False


def test_statistics_wrapper_has_no_outcome_or_legacy_target_dependency() -> None:
    tree = ast.parse(inspect.getsource(statistics_module))
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
    assert imported_roots.isdisjoint(
        {"backtest", "data", "execution", "ml", "signals"}
    )
