"""Stage 1 replications: REP-H52 and REP-IDV.

These tests exercise BEHAVIOUR, not source text. The previous round's
residual-momentum test asserted two substrings while its docstring claimed
to "pin the arithmetic"; it passed while the implementation measured the
wrong month entirely (AQR1-004). Every assertion here computes a score and
checks the number.
"""
from __future__ import annotations

import ast
import datetime as dt
import math
import random
from pathlib import Path

import pytest

from scripts import analyse_qc_alpha_battery as battery_analyser
from scripts import analyse_qc_alpha_stage1 as stage1_analyser
from scripts.analyse_qc_benchmark import parse_benchmark

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "research" / "lean" / "alpha_stage1_replications.py"
)
BENCHMARK_SOURCE = SOURCE.with_name("alpha_stage1_benchmark.py")


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
_OBSERVATIONS = _real()["_aligned_observation_tail"]
_NEW_MONTH = _real()["_is_new_calendar_month"]
_HOLD_COMPLETE = _real()["_holding_period_complete"]


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


def test_month_end_score_uses_prior_close_and_next_session_entry():
    """The first February session identifies January's actual last close."""
    jan_29 = dt.date(2026, 1, 29)
    jan_30 = dt.date(2026, 1, 30)
    feb_2 = dt.date(2026, 2, 2)
    assert not _NEW_MONTH(jan_29, jan_30)
    assert _NEW_MONTH(jan_30, feb_2)

    sessions = [jan_29, jan_30, feb_2]
    prices = [90.0, 100.0, 80.0]
    # end_ago=1 freezes the feature at Jan 30; the Feb 2 entry bar cannot
    # leak into the score window.
    assert _TAIL(prices, sessions, sessions, 0, end_ago=1) == [100.0]


def test_holding_period_is_exactly_21_distinct_session_gaps():
    assert not _HOLD_COMPLETE(100, 120)
    assert _HOLD_COMPLETE(100, 121)
    assert _HOLD_COMPLETE(100, 122)


def test_market_factor_refuses_a_missing_point_in_time_session():
    sessions = list(range(112))
    values = [0.001] * 111
    factor_sessions = sessions[:50] + sessions[51:]
    # Even with 111 numeric values, one missing exchange session means the
    # 90+21 factor window is not the frozen daily window.
    assert _OBSERVATIONS(values, factor_sessions, sessions, 111) is None
    assert _OBSERVATIONS([0.001] * 112, sessions, sessions, 111, end_ago=1) == [0.001] * 111


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


def test_stage1_parser_accepts_only_the_two_frozen_specs(tmp_path: Path):
    log = tmp_path / "stage1.log"
    log.write_text(
        "SPECS|REP_H52|REP_IDV\nDATES|1\n"
        "ROW|202001|0~0.01~0.02~-0.01~0.015~0.1~0.2~0.3~100|"
        "1~-0.01~0.01~-0.02~0.005~0.2~0.3~0.4~100\n",
        encoding="utf-8",
    )
    specs, frame, meta = battery_analyser.parse_log(
        log, expected_spec_sets={stage1_analyser.STAGE_SPECS}
    )
    assert specs == ["REP_H52", "REP_IDV"]
    assert len(frame) == 2
    assert meta["dates"] == 1


def test_stage1_has_a_separate_exact_cadence_benchmark(tmp_path: Path):
    text = BENCHMARK_SOURCE.read_text(encoding="utf-8")
    assert "HOLD_SESSIONS = 21" in text
    assert "_is_new_calendar_month(previous_session, session)" in text

    log = tmp_path / "benchmark.log"
    log.write_text("DATES|1\nBROW|202001|0.02|0.5|100\n", encoding="utf-8")
    frame = parse_benchmark(log)
    assert list(frame.index) == ["202001"]
    assert frame.loc["202001", "ret"] == pytest.approx(0.02)


def test_stage1_run_identity_refuses_missing_compile_or_bad_source_hash():
    with pytest.raises(SystemExit, match="project_id,compile_id"):
        stage1_analyser._run_identity(["A=project,,backtest," + "a" * 64], "--run")
    with pytest.raises(SystemExit, match="project_id,compile_id"):
        stage1_analyser._run_identity(["A=project,compile,backtest,not-a-hash"], "--run")
