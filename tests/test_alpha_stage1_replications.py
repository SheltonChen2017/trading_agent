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


def test_daily_factor_recorder_does_not_rebuild_full_price_histories():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    recorder = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_record_market_return"
    )
    called_attributes = {
        node.func.attr for node in ast.walk(recorder)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "_returns" not in called_attributes


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
    with pytest.raises(SystemExit, match="project_id,compile_id"):
        stage1_analyser._run_identity(
            ["A=not-numeric,compile,backtest," + "a" * 64], "--run"
        )


# --- Counter-review closures (CR2-001..003, 2026-08-17) -----------------
#
# Three mutations survived the suite during Claude's counter-review of the
# round-2 audit: scoring on the entry close (`end_ago=0`), fabricating a
# 0.0 market return for a thin session, and removing drift from Stage 1's
# own `_drift_turnover` copy. Each test below was written to redden under
# exactly one of those mutations and was verified to do so.


def test_score_binding_freezes_features_at_the_prior_close_call_site():
    """CR2-001: the helper honoured ``end_ago=1`` but nothing pinned the CALL.

    The behavioural tests above prove `_aligned_price_tail` excludes the
    entry bar when asked; this pins that `_form_and_bind` actually asks.
    LEAN cannot be imported locally, so the wiring is an AST invariant —
    the arithmetic itself stays behaviourally tested, which is the split
    AQR1-004 demands.
    """
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    form = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_form_and_bind"
    )
    calls = [
        node for node in ast.walk(form)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_form_scores"
    ]
    assert calls, "_form_and_bind no longer calls _form_scores"
    for call in calls:
        keywords = {kw.arg: kw.value for kw in call.keywords}
        assert "end_ago" in keywords, "score call lost its feature cutoff"
        value = keywords["end_ago"]
        assert isinstance(value, ast.Constant) and value.value == 1, (
            "scores must be formed as of the close BEFORE the entry session"
        )


def _min_names_constant() -> int:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "MIN_NAMES":
                    return int(node.value.value)
    raise AssertionError("MIN_NAMES constant not found")


def _extracted_method(name: str):
    text = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(text)
    cls = next(node for node in ast.walk(tree) if isinstance(node, ast.ClassDef))
    fn = next(
        node for node in cls.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )
    segment = ast.get_source_segment(text, fn)
    lines = segment.splitlines()
    indent = len(lines[0]) - len(lines[0].lstrip())
    source = "\n".join(line[indent:] for line in lines)
    namespace: dict = {"MIN_NAMES": _min_names_constant()}
    exec(compile(source, str(SOURCE), "exec"), namespace)  # noqa: S102
    return namespace[name]


def test_market_recorder_refuses_rather_than_fabricating_a_zero_return():
    """CR2-002: a fabricated 0.0 factor day survived every existing test.

    The recorder must skip a session with too few point-in-time names so
    the aligned factor window later REFUSES; appending 0.0 with the session
    recorded would instead feed an invented return into every beta fit.
    This executes the algorithm's own method against a stub.
    """
    recorder = _extracted_method("_record_market_return")
    min_names = _min_names_constant()

    class Stub:
        pass

    algo = Stub()
    algo.selected = [f"S{i}" for i in range(min_names)]
    algo.market_returns = []
    algo.market_return_sessions = []
    algo.last_session = dt.date(2026, 1, 5)

    recorder(algo, {})
    assert algo.market_returns == []
    assert algo.market_return_sessions == []

    thin = {f"S{i}": 0.01 for i in range(min_names - 1)}
    recorder(algo, thin)
    assert algo.market_returns == []
    assert algo.market_return_sessions == []

    full = {f"S{i}": 0.01 for i in range(min_names)}
    recorder(algo, full)
    assert algo.market_returns == [pytest.approx(0.01)]
    assert algo.market_return_sessions == [dt.date(2026, 1, 5)]


# --- Final counter-review closures (CCR3-A, 2026-08-17) ------------------


def test_stage1_look_accounting_constants_match_the_permanent_ledger():
    """CCR3-A: the frozen multiplicity gates were unpinned constants.

    Lowering ``LIFETIME_CELLS_BEFORE_STAGE`` from 428 to 24 — loosening the
    lifetime Bonferroni gate by an order of magnitude — survived the whole
    suite. The 428 floor comes from `docs/alpha-result.md` (348 declared
    cells + 80 emitted cells) and the 24-cell stage family from the frozen
    plan §6 (2 specs × 3 universes × 4 outcomes). Changing either is a
    research-contract change that must be made loudly, with the ledger.
    """
    assert stage1_analyser.STAGE_FAMILY_CELLS == 24
    assert stage1_analyser.LIFETIME_CELLS_BEFORE_STAGE == 428
    assert stage1_analyser.DRAWS == 20_000


def _stage1_args(tmp_path, benchmark_date: str = "202001") -> list[str]:
    alpha = tmp_path / "alpha.log"
    alpha.write_text(
        "SPECS|REP_H52|REP_IDV\nDATES|1\n"
        "ROW|202001|0~0.01~0.02~-0.01~0.015~0.1~0.2~0.3~100|"
        "1~-0.01~0.01~-0.02~0.005~0.2~0.3~0.4~100\n",
        encoding="utf-8",
    )
    benchmark = tmp_path / "benchmark.log"
    benchmark.write_text(
        f"DATES|1\nBROW|{benchmark_date}|0.02|0.5|100\n", encoding="utf-8"
    )
    identity = "123,compile-1,backtest-1," + "a" * 64
    return [
        "--alpha-log", f"B={alpha}",
        "--benchmark-log", f"B={benchmark}",
        "--alpha-run", f"B={identity}",
        "--benchmark-run", f"B={identity}",
        "--output", str(tmp_path / "report.json"),
    ]


def test_stage1_report_carries_both_frozen_gates(tmp_path):
    """The emitted report must state the exact 24-cell and 452-cell gates."""
    import json

    assert stage1_analyser.main(_stage1_args(tmp_path)) == 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["stage_family_cells"] == 24
    assert report["lifetime_cells_before"] == 428
    assert report["lifetime_cells_after"] == 452
    assert report["stage_bonferroni_threshold"] == pytest.approx(0.05 / 24)
    assert report["lifetime_bonferroni_threshold"] == pytest.approx(0.05 / 452)
    universe = report["universes"]["B"]
    assert universe["alpha_run"]["project_id"] == "123"
    assert universe["benchmark_same_dates"]["periods"] == 1


def test_stage1_refuses_a_benchmark_missing_an_alpha_date(tmp_path):
    """Same-date comparison is the gate; a hole must refuse, not narrow."""
    with pytest.raises(SystemExit, match="benchmark lacks"):
        stage1_analyser.main(_stage1_args(tmp_path, benchmark_date="202002"))


def test_stage1_own_drift_turnover_charges_drift_like_the_reviewed_battery():
    """CR2-003: only the monthly battery's copy was tested.

    The `_real()` loader stops BEFORE ``def _drift_turnover``, so removing
    drift from Stage 1's own copy reddened nothing. This executes Stage 1's
    copy directly with the Method V2 §1.2 cases.
    """
    text = SOURCE.read_text(encoding="utf-8")
    start = text.index("def _drift_turnover")
    end = text.index("class AlphaStage1Replications")
    namespace: dict = {}
    exec(compile(text[start:end], str(SOURCE), "exec"), namespace)  # noqa: S102
    turnover = namespace["_drift_turnover"]

    targets = {"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25}
    doubled = {"A": 1.0, "B": 0.0, "C": 0.0, "D": 0.0}
    # One name doubles: the book drifts to 40/20/20/20 and restoring equal
    # weight trades 15% one-way. Counting it as zero was ABR-002's defect.
    assert turnover(targets, targets, doubled) == pytest.approx(0.15)
    # Flat returns: re-entering the same book is free.
    flat = {name: 0.0 for name in targets}
    assert turnover(targets, targets, flat) == pytest.approx(0.0)
    # A held name with no outcome refuses instead of assuming zero drift.
    assert turnover(targets, targets, {"A": 0.0}) is None
    # An empty previous book charges half the gross target weight.
    assert turnover({}, targets, {}) == pytest.approx(0.5)
