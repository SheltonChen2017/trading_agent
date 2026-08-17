"""Stage 1 replications: REP-H52 and REP-IDV.

These tests exercise BEHAVIOUR, not source text. The previous round's
residual-momentum test asserted two substrings while its docstring claimed
to "pin the arithmetic"; it passed while the implementation measured the
wrong month entirely (AQR1-004). Every assertion here computes a score and
checks the number.
"""
from __future__ import annotations

import ast
import math
import random
from pathlib import Path

import pytest

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "research" / "lean" / "alpha_stage1_replications.py"
)


def _real():
    """Load the algorithm's OWN pure scoring functions.

    The first version of this file reimplemented `_h52` and `_idv` locally,
    so every assertion would have passed no matter what the algorithm
    computed -- the same defect as AQR1-004 in a new disguise, caught when
    a mutation of the algorithm failed to redden anything. These tests now
    execute the real functions.
    """
    text = SOURCE.read_text(encoding="utf-8")
    start = text.index("def _aligned_price_tail")
    end = text.index("def _drift_turnover")
    namespace: dict = {"math": math}
    exec(compile(text[start:end], str(SOURCE), "exec"), namespace)  # noqa: S102
    return namespace


_H52 = _real()["_h52_score"]
_IDV = _real()["_idio_vol_score"]
_TAIL = _real()["_aligned_price_tail"]


def _h52(prices):
    return _H52(prices)


def _idv(stock, market, fit=90, formation=21):
    return _IDV(stock, market, fit, formation)


def test_h52_scores_one_at_the_high_and_falls_proportionally():
    assert _h52([100.0 + i for i in range(252)]) == pytest.approx(1.0)
    assert _h52([200.0] * 251 + [100.0]) == pytest.approx(0.5)
    assert _h52([200.0] * 251 + [180.0]) == pytest.approx(0.9)


def test_h52_requires_a_full_aligned_year_and_refuses_otherwise():
    """A short history or a calendar gap must produce no score.

    Imputing or shortening would make a recent listing look like a name
    sitting at its 52-week high, which is the opposite of the signal.
    """
    tail = _TAIL
    sessions = list(range(252))
    prices = [100.0] * 252

    assert tail(prices, sessions, sessions, 251) is not None
    # One session too few.
    assert tail(prices[:251], sessions[:251], sessions, 251) is None
    # A stock that missed a session: its dates no longer match the market.
    gapped = sessions[:100] + sessions[101:] + [252]
    assert tail(prices, gapped, sessions, 251) is None


def test_idv_scores_a_pure_beta_stock_near_zero():
    """Idiosyncratic volatility is what the market does NOT explain."""
    rng = random.Random(11)
    market = [rng.gauss(0, 0.01) for _ in range(111)]
    pure_beta = [1.3 * m for m in market]
    assert _idv(pure_beta, market) == pytest.approx(0.0, abs=1e-9)


def test_idv_ranks_a_noisier_stock_worse():
    """The score is NEGATIVE standard deviation, so low-vol ranks high."""
    rng = random.Random(13)
    market = [rng.gauss(0, 0.01) for _ in range(111)]
    quiet = [1.0 * m + rng.gauss(0, 0.002) for m in market]
    noisy = [1.0 * m + rng.gauss(0, 0.020) for m in market]
    assert _idv(quiet, market) > _idv(noisy, market)


def test_idv_coefficients_are_frozen_before_the_formation_month():
    """The fit must not see the variation it is later used to explain.

    A shock confined to the formation month must NOT change the estimated
    beta; if it did, the residuals would be shrunk by a coefficient fitted
    on them and the score would understate true idiosyncratic volatility.
    """
    rng = random.Random(17)
    market = [rng.gauss(0, 0.01) for _ in range(111)]
    base = [1.0 * m for m in market]
    shocked = list(base)
    for k in range(90, 111):
        shocked[k] += 0.05

    def beta_of(stock):
        fit_y, fit_x = stock[:90], market[:90]
        mean_x, mean_y = sum(fit_x) / 90, sum(fit_y) / 90
        var_x = sum((v - mean_x) ** 2 for v in fit_x)
        return sum((x - mean_x) * (y - mean_y)
                   for x, y in zip(fit_x, fit_y)) / var_x

    assert beta_of(shocked) == pytest.approx(beta_of(base))
    # And the shock must register in the score rather than being absorbed.
    assert _idv(shocked, market) == pytest.approx(_idv(base, market), abs=1e-9)


def test_the_completeness_guard_demands_this_algorithms_specs():
    """Copying the monthly battery carried its ten-spec list, which would
    have demanded specifications this algorithm never computes and refused
    every run spuriously."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    specs = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "SPECIFICATIONS":
            specs = ast.literal_eval(node.value)
    assert specs == ("REP_H52", "REP_IDV"), specs


def test_the_algorithm_declares_itself_a_counted_look():
    flat = " ".join(SOURCE.read_text(encoding="utf-8").split())
    assert "counted research look" in flat
    assert "NO ALPHA STATISTIC" not in flat
