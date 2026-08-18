"""Regression tests for the corrected QuantConnect alpha measurement path."""
from __future__ import annotations

import ast
import base64
import math
from pathlib import Path
import struct

import pandas as pd
import pytest

from scripts import analyse_qc_alpha_battery as analyser
from scripts import analyse_qc_benchmark as benchmark_analyser
from scripts.analyse_qc_benchmark import parse_benchmark


ROOT = Path(__file__).resolve().parents[1]
MONTHLY = ROOT / "research" / "lean" / "alpha_battery_monthly.py"
SHORT = ROOT / "research" / "lean" / "alpha_battery_short.py"
SHORT_SPECS = (
    "ABNORMAL_VOLUME_REVERSAL", "INDUSTRY_ADJ_REVERSAL_5D", "MAX_20",
    "MAX_X_REVERSAL", "REVERSAL_5D",
)


def _load_pure_function(path: Path, name: str):
    """Load one top-level pure helper without importing AlgorithmImports."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    dependencies = []
    if name == "_residual_momentum_total":
        dependencies.append(next(
            item for item in tree.body
            if isinstance(item, ast.FunctionDef) and item.name == "_joint_residual_total"
        ))
    if name == "_round_trip_turnover":
        dependencies.append(next(
            item for item in tree.body
            if isinstance(item, ast.FunctionDef) and item.name == "_drift_turnover"
        ))
    node = next(
        item for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    namespace = {
        "math": math,
        "RESIDUAL_ESTIMATION_SESSIONS": 252,
        "MOMENTUM_SKIP_SESSIONS": 21,
    }
    exec(
        compile(ast.Module(body=[*dependencies, node], type_ignores=[]), str(path), "exec"),
        namespace,
    )
    return namespace[name]


def test_joint_residual_momentum_fits_both_factors_before_measurement():
    residual_total = _load_pure_function(MONTHLY, "_joint_residual_total")
    market = [((index % 7) - 3) / 100 for index in range(80)]
    industry = [((index * index % 11) - 5) / 120 for index in range(80)]
    stock = [0.002 + 1.7 * m - 0.6 * i for m, i in zip(market, industry)]
    for index in range(59, 80):
        stock[index] += 0.01
    assert residual_total(stock, market, industry, 21) == pytest.approx(0.21)


def test_price_tail_requires_exact_market_session_alignment():
    aligned_tail = _load_pure_function(MONTHLY, "_aligned_price_tail")
    market_sessions = [1, 2, 3, 4]
    assert aligned_tail([10, 11, 12], [2, 3, 4], market_sessions, 2) == [10, 11, 12]
    assert aligned_tail([10, 11, 12], [1, 3, 4], market_sessions, 2) is None
    assert aligned_tail([10, 11, 12], [3, 4, 4], market_sessions, 2) is None


@pytest.mark.parametrize("path", (MONTHLY, SHORT))
def test_observation_tail_refuses_missing_or_duplicate_sessions(path: Path):
    aligned = _load_pure_function(path, "_aligned_observation_tail")
    market_sessions = [1, 2, 3, 4]
    assert aligned([10, 11, 12], [2, 3, 4], market_sessions, 3) == [10, 11, 12]
    assert aligned([10, 11, 12], [1, 3, 4], market_sessions, 3) is None
    assert aligned([10, 11, 12], [2, 4, 4], market_sessions, 3) is None


def test_industry_factor_uses_that_sessions_point_in_time_membership():
    peer_return = _load_pure_function(MONTHLY, "_leave_one_out_peer_return")
    symbol = "A"
    # The same stock changes industry. Each observation must use the mapping
    # known on that session, not today's classification projected backward.
    old_membership = {symbol: 10}
    new_membership = {symbol: 20}
    aggregates = {10: (0.12, 3), 20: (-0.06, 3)}
    assert peer_return(symbol, 0.02, old_membership, aggregates) == pytest.approx(0.05)
    assert peer_return(symbol, 0.02, new_membership, aggregates) == pytest.approx(-0.04)
    assert peer_return(symbol, 0.02, {}, aggregates) is None
    assert peer_return(symbol, 0.02, old_membership, {10: (0.12, 2)}) is None


def test_monthly_factor_path_is_prospective_and_not_quadratic():
    text = MONTHLY.read_text(encoding="utf-8")
    tree = ast.parse(text)
    function_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    assert "_record_factor_returns" in function_names
    assert "_factor_returns" in function_names
    assert "_index_returns" not in function_names
    assert "_industry_returns" not in function_names
    recorder = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_record_factor_returns"
    )
    called_attributes = {
        node.func.attr for node in ast.walk(recorder)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "_returns" not in called_attributes


@pytest.mark.parametrize(
    "path",
    (
        ROOT / "research" / "lean" / "universe_benchmark.py",
        ROOT / "research" / "lean" / "alpha_stage1_benchmark.py",
    ),
)
def test_benchmarks_refuse_stale_closes(path: Path):
    text = path.read_text(encoding="utf-8")
    assert "self.close_sessions" in text
    assert "self.close_sessions.get(symbol) == self.last_session" in text


def test_drift_turnover_charges_the_rebalance_after_weight_drift():
    turnover = _load_pure_function(MONTHLY, "_drift_turnover")
    previous = {name: 0.25 for name in "ABCD"}
    target = dict(previous)
    outcomes = {"A": 1.0, "B": 0.0, "C": 0.0, "D": 0.0}
    assert turnover(previous, target, outcomes) == pytest.approx(0.15)
    assert turnover({}, target, {}) == pytest.approx(0.5)
    assert turnover(previous, target, {"A": 1.0}) is None


def test_short_holding_period_charges_its_own_entry_and_exit():
    turnover = _load_pure_function(SHORT, "_round_trip_turnover")
    target = {name: 0.25 for name in "ABCD"}
    flat = {name: 0.0 for name in target}
    assert turnover(target, flat) == pytest.approx(1.0)
    assert turnover(target, {"A": 0.0}) is None


def test_short_round_trip_exit_leg_liquidates_the_drifted_book():
    """FCR-001: the exit leg's DRIFT was unpinned.

    On a long-only book the drifted weights renormalise to gross 1.0, so the
    flat-outcome case cannot tell a drifted exit from an undrifted one — a
    mutation replacing the exit leg with a second copy of the entry leg
    survived the suite. The distinction is load-bearing exactly where signed
    weights matter: a long/short book whose both legs win shrinks to gross
    0.909 of NAV before liquidation, so the true round trip is 0.9545, not
    1.0; a book whose both legs lose grows to gross 1.111 and costs 1.0556.
    """
    turnover = _load_pure_function(SHORT, "_round_trip_turnover")
    book = {"A": 0.5, "B": -0.5}
    both_win = {"A": 0.10, "B": -0.10}   # NAV 1.1, drifted gross 10/11
    assert turnover(book, both_win) == pytest.approx(0.5 + 0.5 * (10.0 / 11.0))
    both_lose = {"A": -0.10, "B": 0.10}  # NAV 0.9, drifted gross 10/9
    assert turnover(book, both_lose) == pytest.approx(0.5 + 0.5 * (10.0 / 9.0))
    # A wiped-out book refuses instead of pricing a liquidation of nothing.
    assert turnover(book, {"A": -1.0, "B": 1.0}) is None


def test_short_algorithm_assigns_round_trip_turnover_to_the_settled_period():
    tree = ast.parse(SHORT.read_text(encoding="utf-8"))
    binder = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef)
                  and node.name == "_bind_staged_entry")
    settler = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef)
                  and node.name == "_settle")
    scorer = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef)
                  and node.name == "_form_scores")
    binder_calls = {node.func.id for node in ast.walk(binder)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)}
    settler_calls = {node.func.id for node in ast.walk(settler)
                     if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Name)}
    scorer_calls = {node.func.id for node in ast.walk(scorer)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)}
    assert "_round_trip_turnover" not in binder_calls
    assert "_drift_turnover" not in binder_calls
    assert "_round_trip_turnover" in settler_calls
    assert "_max_daily_return" in scorer_calls


def test_max20_requires_exactly_twenty_valid_daily_returns():
    max_daily = _load_pure_function(SHORT, "_max_daily_return")
    values = [100.0 + index for index in range(21)]
    assert max_daily(values) == pytest.approx(1.0 / 100.0)
    assert max_daily(values[:-1]) is None
    for invalid in (0.0, -1.0, math.nan, math.inf):
        broken = list(values)
        broken[5] = invalid
        assert max_daily(broken) is None


@pytest.mark.parametrize(
    "path",
    (MONTHLY, SHORT, ROOT / "research" / "lean" / "alpha_stage1_replications.py"),
)
def test_missing_industry_is_not_turned_into_a_fake_peer_group(path: Path):
    valid_code = _load_pure_function(path, "_valid_industry_code")
    assert valid_code(123) == 123
    for invalid in (None, 0, -1, "", "not-a-code", math.inf):
        assert valid_code(invalid) is None


@pytest.mark.parametrize(
    "path",
    (MONTHLY, SHORT, ROOT / "research" / "lean" / "alpha_stage1_replications.py"),
)
def test_fine_ingestion_routes_industry_codes_through_the_strict_guard(path: Path):
    """FCRV-001: pin the live call site, not only the pure guard helper."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    fine = next(node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == "_fine")
    named_calls = {
        node.func.id for node in ast.walk(fine)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    attribute_calls = {
        node.func.attr for node in ast.walk(fine)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    direct_industry_int = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "int"
        and "morningstar_industry_code" in ast.unparse(node)
        for node in ast.walk(fine)
    )
    assert "_valid_industry_code" in named_calls
    assert not direct_industry_int
    assert "pop" in attribute_calls


def _full_cell(index: int, turn_ls=0.1, turn_l10=0.2, turn_l20=0.3) -> str:
    return (
        f"{index}~0.01~0.02~-0.01~0.015~"
        f"{turn_ls}~{turn_l10}~{turn_l20}~100"
    )


def _spec_header() -> str:
    return "SPECS|" + "|".join(SHORT_SPECS)


def _full_row(date: str = "202001") -> str:
    return f"ROW|{date}|" + "|".join(_full_cell(index) for index in range(5))


def test_parser_requires_every_spec_on_every_declared_row(tmp_path: Path):
    log = tmp_path / "partial.log"
    log.write_text(
        _spec_header() + "\nDATES|1\nROW|202001|" + _full_cell(0),
        encoding="utf-8",
    )
    with pytest.raises(analyser.TruncatedLog, match="every declared spec"):
        analyser.parse_log(log)


def test_parser_refuses_conflicting_date_declarations(tmp_path: Path):
    log = tmp_path / "conflict.log"
    log.write_text(
        _spec_header() + "\nDATES|1\nDATES|2\n" + _full_row(),
        encoding="utf-8",
    )
    with pytest.raises(analyser.InvalidLog, match="conflicting DATES"):
        analyser.parse_log(log)


def test_benchmark_parser_refuses_conflicting_date_declarations(tmp_path: Path):
    log = tmp_path / "benchmark-conflict.log"
    log.write_text(
        "DATES|1\nDATES|2\nBROW|202001|0.01|0.25|100", encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="conflicting DATES"):
        parse_benchmark(log)


def test_parsers_refuse_empty_declared_runs(tmp_path: Path):
    alpha = tmp_path / "empty-alpha.log"
    alpha.write_text(_spec_header() + "\nDATES|0", encoding="utf-8")
    with pytest.raises(analyser.InvalidLog, match="no dated observations"):
        analyser.parse_log(alpha)
    benchmark = tmp_path / "empty-benchmark.log"
    benchmark.write_text("DATES|0", encoding="utf-8")
    with pytest.raises(SystemExit, match="no dated observations"):
        parse_benchmark(benchmark)


@pytest.mark.parametrize(
    ("replacement", "message"),
    (("0~0.01~nan~-0.01~0.015~0.1", "non-finite"),
     ("0~0.01~0.02~-0.01~0.015~-0.1", "negative")),
)
def test_parser_refuses_non_finite_results_or_negative_turnover(
    tmp_path: Path, replacement: str, message: str
):
    log = tmp_path / "invalid-number.log"
    row = _full_row().replace("0~0.01~0.02~-0.01~0.015~0.1", replacement, 1)
    log.write_text(_spec_header() + "\nDATES|1\n" + row, encoding="utf-8")
    with pytest.raises(analyser.InvalidLog, match=message):
        analyser.parse_log(log)


def test_parser_refuses_the_legacy_single_turnover_layout(tmp_path: Path):
    log = tmp_path / "legacy.log"
    log.write_text(
        _spec_header() + "\nDATES|1\nROW|202001|0~0.01~0.02~-0.01~0.015~0.2~100",
        encoding="utf-8",
    )
    with pytest.raises(analyser.InvalidLog, match="unsupported"):
        analyser.parse_log(log)


def test_parser_round_trips_the_full_period_binary_layout(tmp_path: Path):
    values = (1000, 20000, -10000, 15000, 1000, 2000, 3000)
    payload = struct.pack(">I", 20200102)
    payload += b"".join(struct.pack(">iiiiHHH", *values) for _ in SHORT_SPECS)
    log = tmp_path / "packed.log"
    log.write_text(
        _spec_header()
        + "\nSCALE|layout=b64block_date_u32_i32x4_u16x3|ic=1e-5|ret=1e-6|turnover=1e-4"
        + "\nDATES|1\n"
        + "\n".join(f"SPECMETA|{spec}|median_names=100|periods=1" for spec in SHORT_SPECS)
        + "\nB64BLOCK|1|"
        + base64.b64encode(payload).decode("ascii"),
        encoding="utf-8",
    )
    specs, frame, meta = analyser.parse_log(log)
    assert specs == list(SHORT_SPECS)
    assert meta["dates"] == 1
    assert frame.iloc[0]["ic"] == pytest.approx(0.01)
    assert frame.iloc[0]["long"] == pytest.approx(0.02)
    assert frame.iloc[0]["turnover_l20"] == pytest.approx(0.3)


_MASKED_SCALE = ("SCALE|layout=b64block_date_u32_mask_u8_i32x4_u16x3"
                 "|ic=1e-5|ret=1e-6|turnover=1e-4")


def _masked_record(date: int, present: list[int],
                   turnovers=(1000, 2000, 3000)) -> bytes:
    mask = 0
    for index in present:
        mask |= 1 << index
    payload = struct.pack(">IB", date, mask)
    payload += b"".join(
        struct.pack(">iiiiHHH", 1000, 20000, -10000, 15000, *turnovers)
        for _ in present
    )
    return payload


def _masked_log(tmp_path: Path, records: list[bytes],
                periods: dict[str, int]) -> Path:
    log = tmp_path / "masked.log"
    log.write_text(
        _spec_header() + "\n" + _MASKED_SCALE
        + f"\nDATES|{len(records)}\n"
        + "\n".join(f"SPECMETA|{spec}|median_names=100|periods={periods[spec]}"
                    for spec in SHORT_SPECS)
        + f"\nB64BLOCK|{len(records)}|"
        + base64.b64encode(b"".join(records)).decode("ascii"),
        encoding="utf-8",
    )
    return log


def test_masked_layout_round_trips_absent_specs_and_turnover_sentinel(
    tmp_path: Path,
):
    # R-013: date 20160129 honestly lacks MAX_20 (spec index 2); one cell on
    # the other date declares its long-only-10 turnover unavailable (65535).
    records = [
        _masked_record(20160122, [0, 1, 2, 3, 4],
                       turnovers=(1000, 65535, 3000)),
        _masked_record(20160129, [0, 1, 3, 4]),
    ]
    periods = {spec: (1 if spec == "MAX_20" else 2) for spec in SHORT_SPECS}
    specs, frame, meta = analyser.parse_log(_masked_log(tmp_path, records, periods))
    assert specs == list(SHORT_SPECS)
    assert meta["dates"] == 2
    assert len(frame) == 9
    assert frame[(frame["spec"] == "MAX_20")
                 & (frame["date"] == "20160129")].empty
    first = frame[frame["date"] == "20160122"].iloc[0]
    assert math.isnan(float(first["turnover_l10"]))
    assert first["turnover_ls"] == pytest.approx(0.1)
    assert first["turnover_l20"] == pytest.approx(0.3)


def test_v1_layout_keeps_65535_as_a_real_turnover_value(tmp_path: Path):
    # R-002's historical logs predate the sentinel: 65535 stays 6.5535.
    values = (1000, 20000, -10000, 15000, 1000, 65535, 3000)
    payload = struct.pack(">I", 20200102)
    payload += b"".join(struct.pack(">iiiiHHH", *values) for _ in SHORT_SPECS)
    log = tmp_path / "packed-v1.log"
    log.write_text(
        _spec_header()
        + "\nSCALE|layout=b64block_date_u32_i32x4_u16x3|ic=1e-5|ret=1e-6|turnover=1e-4"
        + "\nDATES|1\n"
        + "\n".join(f"SPECMETA|{spec}|median_names=100|periods=1"
                    for spec in SHORT_SPECS)
        + "\nB64BLOCK|1|" + base64.b64encode(payload).decode("ascii"),
        encoding="utf-8",
    )
    _, frame, _ = analyser.parse_log(log)
    assert frame.iloc[0]["turnover_l10"] == pytest.approx(6.5535)


@pytest.mark.parametrize("mask_bits", ([], [5]))
def test_masked_layout_refuses_empty_or_out_of_range_masks(
    tmp_path: Path, mask_bits: list[int]
):
    records = [_masked_record(20160122, mask_bits)]
    periods = {spec: 0 for spec in SHORT_SPECS}
    with pytest.raises(analyser.InvalidLog, match="invalid spec mask"):
        analyser.parse_log(_masked_log(tmp_path, records, periods))


def test_masked_layout_refuses_trailing_bytes(tmp_path: Path):
    records = [_masked_record(20160122, [0, 1, 2, 3, 4]) + b"\x00"]
    periods = {spec: 1 for spec in SHORT_SPECS}
    with pytest.raises(analyser.InvalidLog, match="trailing bytes"):
        analyser.parse_log(_masked_log(tmp_path, records, periods))


def test_masked_layout_refuses_truncated_cells(tmp_path: Path):
    records = [_masked_record(20160122, [0, 1, 2, 3, 4])[:-4]]
    periods = {spec: 1 for spec in SHORT_SPECS}
    with pytest.raises(analyser.TruncatedLog, match="incomplete packed block"):
        analyser.parse_log(_masked_log(tmp_path, records, periods))


def test_split_log_merge_refuses_overlapping_windows(tmp_path: Path):
    paths = []
    for number in range(2):
        path = tmp_path / f"part{number}.log"
        path.write_text(
            _spec_header() + "\nDATES|1\n" + _full_row(),
            encoding="utf-8",
        )
        paths.append(path)
    with pytest.raises(analyser.InvalidLog, match="not after prior"):
        analyser.merge_logs(paths)


def test_each_construction_uses_its_own_realised_turnover():
    rows = []
    for index in range(24):
        rows.append({
            "date": f"2020{index:02d}", "spec": "A", "ic": 0.01,
            "long": 0.01, "short": -0.01, "long20": 0.01, "names": 100,
            "turnover_ls": 0.5, "turnover_l10": 0.0, "turnover_l20": 0.25,
        })
    result = analyser.analyse(pd.DataFrame(rows), 12.0)["A"]
    assert result["long_only_10"]["net"]["10bps"]["mean_period_return"] == pytest.approx(0.01)
    assert result["long_only_20"]["net"]["10bps"]["mean_period_return"] == pytest.approx(0.0095)
    assert result["long_short"]["net"]["10bps"]["mean_period_return"] == pytest.approx(0.009)


def test_analysis_cadence_is_inferred_from_each_frozen_spec_family():
    monthly = next(specs for specs in analyser.EXPECTED_SPEC_SETS if len(specs) == 10)
    short = next(specs for specs in analyser.EXPECTED_SPEC_SETS if len(specs) == 5)
    assert analyser.periods_per_year_for_specs(monthly) == pytest.approx(12.0)
    assert analyser.periods_per_year_for_specs(short) == pytest.approx(42.0)
    with pytest.raises(analyser.InvalidLog, match="unknown spec family"):
        analyser.periods_per_year_for_specs({"UNKNOWN"})


def test_cli_uses_short_family_cadence_and_rejects_monthly_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    frame = pd.DataFrame([{"date": "20200102", "spec": SHORT_SPECS[0]}])
    monkeypatch.setattr(
        analyser, "merge_logs",
        lambda paths: (list(SHORT_SPECS), frame, {"dates": 1}),
    )
    observed = []
    monkeypatch.setattr(
        analyser, "analyse",
        lambda passed_frame, periods: observed.append(periods) or {},
    )
    source_hash = "a" * 64
    common = [
        "--log", "B=ignored.log",
        "--run-id", f"B=123,compile,backtest,{source_hash}",
        "--output", str(tmp_path / "report.json"),
    ]
    assert analyser.main(common) == 0
    assert observed == [42.0]
    with pytest.raises(SystemExit, match="conflicts with the frozen 42 cadence"):
        analyser.main([*common, "--periods-per-year", "12"])


def test_declared_family_counts_ic_and_all_three_constructions():
    assert analyser.DECLARED_LOOKS == 15 * 3 * 4
    assert 1.0 / (analyser.DRAWS + 1) < 0.05 / analyser.DECLARED_LOOKS


def test_general_analyser_requires_complete_run_identity():
    source_hash = "a" * 64
    observed = analyser._run_identities([
        f"B=123,compile-1,backtest-1,{source_hash};"
        f"124,compile-2,backtest-2,{source_hash}"
    ])
    assert observed["B"][0]["project_id"] == "123"
    assert observed["B"][1]["backtest_id"] == "backtest-2"
    with pytest.raises(SystemExit, match="project,compile,backtest"):
        analyser._run_identities(["B=backtest-only"])
    with pytest.raises(SystemExit, match="project,compile,backtest"):
        analyser._run_identities(["B=123,compile,backtest,not-a-hash"])


def test_benchmark_analyser_records_complete_run_identity(tmp_path: Path):
    log = tmp_path / "benchmark.log"
    output = tmp_path / "benchmark.json"
    log.write_text("DATES|1\nBROW|202001|0.01|0.25|100", encoding="utf-8")
    source_hash = "a" * 64
    assert benchmark_analyser.main([
        "--log", f"B={log}",
        "--run-id", f"B=123,compile-1,backtest-1,{source_hash}",
        "--output", str(output),
    ]) == 0
    payload = __import__("json").loads(output.read_text(encoding="utf-8"))
    assert payload["B"]["quantconnect_run"] == {
        "project_id": "123", "compile_id": "compile-1",
        "backtest_id": "backtest-1", "source_sha256": source_hash,
    }


def test_benchmark_parser_requires_construction_turnover(tmp_path: Path):
    log = tmp_path / "benchmark.log"
    log.write_text("DATES|1\nBROW|202001|0.01|0.25|100", encoding="utf-8")
    frame = parse_benchmark(log)
    assert frame.loc["202001", "turnover"] == pytest.approx(0.25)


def test_benchmark_parser_accepts_declared_unavailable_turnover(tmp_path: Path):
    # R-017: an EMPTY turnover field declares an unpriceable prior book;
    # the month's return survives and the analyser charges the full 1.0.
    log = tmp_path / "benchmark-unavailable.log"
    log.write_text("DATES|2\nBROW|202001|0.01||100\nBROW|202002|0.02|0.25|100",
                   encoding="utf-8")
    frame = parse_benchmark(log)
    assert math.isnan(float(frame.loc["202001", "turnover"]))
    assert frame.loc["202002", "turnover"] == pytest.approx(0.25)
    assert frame.loc["202001", "ret"] == pytest.approx(0.01)


def test_benchmark_analyser_charges_full_turnover_for_unavailable_months(
    tmp_path: Path,
):
    log = tmp_path / "benchmark-charge.log"
    output = tmp_path / "benchmark-charge.json"
    # Thirteen months (performance() needs at least twelve). All present
    # turnovers are 0.0, so any 10bps-vs-0bps difference can come only from
    # the month whose turnover is declared unavailable.
    rows = [f"BROW|20200{m}|0.01|0.0|100" for m in range(1, 10)]
    rows += ["BROW|202010|0.01||100", "BROW|202011|0.01|0.0|100",
             "BROW|202012|0.01|0.0|100", "BROW|202101|0.01|0.0|100"]
    log.write_text("DATES|13\n" + "\n".join(rows), encoding="utf-8")
    assert benchmark_analyser.main([
        "--log", f"B={log}",
        "--run-id", f"B=123,compile-1,backtest-1,{'a' * 64}",
        "--output", str(output),
    ]) == 0
    payload = __import__("json").loads(output.read_text(encoding="utf-8"))
    entry = payload["B"]
    assert entry["unavailable_turnover_periods"] == 1
    assert entry["mean_turnover"] == pytest.approx(0.0)
    unavailable_rows = [row for row in entry["series"] if row["turnover"] is None]
    assert [row["date"] for row in unavailable_rows] == ["202010"]
    assert entry["net"]["10bps"]["cagr"] < entry["net"]["0bps"]["cagr"]
    assert entry["underfilled_months"] == 0


def test_benchmark_parser_records_underfill_and_refuses_impossible_counts(
    tmp_path: Path,
):
    # R-019: a five-field row discloses priced AND entered counts.
    log = tmp_path / "benchmark-underfill.log"
    log.write_text("DATES|2\nBROW|202001|0.01|0.25|97|100\n"
                   "BROW|202002|0.02|0.25|100|100", encoding="utf-8")
    frame = parse_benchmark(log)
    assert int(frame.loc["202001", "names"]) == 97
    assert int(frame.loc["202001", "names_entered"]) == 100
    bad = tmp_path / "benchmark-impossible.log"
    bad.write_text("DATES|1\nBROW|202001|0.01|0.25|100|97", encoding="utf-8")
    with pytest.raises(SystemExit, match="entered-name count"):
        parse_benchmark(bad)


@pytest.mark.parametrize(
    "row",
    ("BROW|202001|inf|0.25|100", "BROW|202001|0.01|-0.25|100",
     "BROW|202001|0.01|0.25|0"),
)
def test_benchmark_parser_refuses_invalid_numbers(tmp_path: Path, row: str):
    log = tmp_path / "benchmark-invalid.log"
    log.write_text(f"DATES|1\n{row}", encoding="utf-8")
    with pytest.raises(SystemExit):
        parse_benchmark(log)


@pytest.mark.parametrize("months", (6, 12))
def test_residual_momentum_measures_months_minus_one_and_skips_latest_month(months):
    """The score must not relabel the skipped month as the signal window."""
    residual_momentum = _load_pure_function(MONTHLY, "_residual_momentum_total")
    estimation = 252
    measurement = 21 * (months - 1)
    skipped = 21
    length = estimation + measurement + skipped
    market = [((index % 7) - 3) / 100 for index in range(length)]
    industry = [((index * index % 11) - 5) / 120 for index in range(length)]
    stock = [0.002 + 1.7 * m - 0.6 * i for m, i in zip(market, industry)]

    for index in range(estimation, estimation + measurement):
        stock[index] += 0.01
    for index in range(estimation + measurement, length):
        stock[index] += 1.0  # deliberately huge; this is the skipped month

    observed = residual_momentum(
        stock,
        market,
        industry,
        months,
        estimation_sessions=estimation,
        skip_sessions=skipped,
    )
    assert observed == pytest.approx(0.01 * measurement)


def test_residual_momentum_refuses_short_or_misaligned_factor_history():
    residual_momentum = _load_pure_function(MONTHLY, "_residual_momentum_total")
    required = 252 + 21 * 11 + 21
    full = [0.0] * required
    assert residual_momentum(full[:-1], full[:-1], full[:-1], 12) is None
    assert residual_momentum(full, full[:-1], full, 12) is None


def test_parsers_refuse_present_nonfinite_turnover_or_ic_tokens(tmp_path: Path):
    """S0R-003: a literal ``nan`` token must refuse the log, not be
    silently relabelled as the declared-unavailability channel."""
    log = tmp_path / "nan-turnover.log"
    log.write_text(
        _spec_header() + "\nDATES|1\nROW|202001|" + "|".join(
            _full_cell(i, turn_ls=("nan" if i == 0 else 0.1))
            for i in range(5)
        ),
        encoding="utf-8",
    )
    with pytest.raises(analyser.InvalidLog, match="non-finite turnover_ls"):
        analyser.parse_log(log)

    ic_log = tmp_path / "nan-ic.log"
    cells = ["0~nan~0.02~-0.01~0.015~0.1~0.2~0.3~100"]
    cells += [_full_cell(i) for i in range(1, 5)]
    ic_log.write_text(
        _spec_header() + "\nDATES|1\nROW|202001|" + "|".join(cells),
        encoding="utf-8",
    )
    with pytest.raises(analyser.InvalidLog, match="non-finite ic"):
        analyser.parse_log(ic_log)

    bench = tmp_path / "nan-bench.log"
    bench.write_text("DATES|1\nBROW|202001|0.01|nan|100", encoding="utf-8")
    with pytest.raises(SystemExit, match="invalid benchmark turnover"):
        parse_benchmark(bench)


def test_alpha_analyser_charges_full_turnover_for_unavailable_months(
    tmp_path: Path,
):
    """S0R-008: pin the MAGNITUDE of the conservative charge. The
    count-only disclosure assertions pass under fillna(0.0); the exact
    net-vs-gross mean delta does not."""
    months = [f"20{15 + i // 12:02d}{i % 12 + 1:02d}" for i in range(13)]
    lines = [_spec_header(), f"DATES|{len(months)}"]
    for index, month in enumerate(months):
        cells = []
        for spec_index in range(5):
            turn_ls = "" if index == 3 and spec_index == 0 else "0.0"
            cells.append(
                f"{spec_index}~0.01~0.02~-0.01~0.015~{turn_ls}~0.0~0.0~100"
            )
        lines.append(f"ROW|{month}|" + "|".join(cells))
    log = tmp_path / "charge.log"
    log.write_text("\n".join(lines), encoding="utf-8")

    specs, frame, meta = analyser.parse_log(log)
    report = analyser.analyse(frame, periods_per_year=12.0)

    block = report[SHORT_SPECS[0]]["long_short"]
    assert block["unavailable_turnover_periods"] == 1
    gross_mean = block["gross"]["mean_period_return"]
    net10_mean = block["net"]["10bps"]["mean_period_return"]
    # All present turnovers are 0.0, so the whole 10bps drag comes from
    # the single unavailable month charged at the full 1.0 one-way.
    assert gross_mean - net10_mean == pytest.approx(
        1.0 * 2.0 * 10.0 / 10_000.0 / len(months)
    )
    other = report[SHORT_SPECS[1]]["long_short"]
    assert other["unavailable_turnover_periods"] == 0
    assert (other["gross"]["mean_period_return"]
            - other["net"]["10bps"]["mean_period_return"]) == pytest.approx(0.0)


def test_stage1_analyser_is_invocable_in_script_mode():
    """S1R-001: `python scripts/analyse_qc_alpha_stage1.py` must not crash
    at import. The A-002 pass had to fall back to module mode because the
    script lacked the sys.path bootstrap its two sibling analysers carry."""
    import subprocess
    import sys as _sys
    result = subprocess.run(
        [_sys.executable, str(ROOT / "scripts" / "analyse_qc_alpha_stage1.py"),
         "--help"],
        capture_output=True, text=True, timeout=120, cwd=str(ROOT / "scripts"),
    )
    assert result.returncode == 0, result.stderr
    assert "ModuleNotFoundError" not in result.stderr


def test_parsers_refuse_malformed_tokens_with_typed_errors(tmp_path: Path):
    """SHR-001: a non-numeric token refuses via InvalidLog/SystemExit, not
    a bare ValueError traceback. Fail-closed either way; typed is
    diagnosable as log corruption."""
    log = tmp_path / "malformed-turnover.log"
    log.write_text(
        _spec_header() + "\nDATES|1\nROW|202001|" + "|".join(
            _full_cell(i, turn_ls=("abc" if i == 0 else 0.1))
            for i in range(5)
        ),
        encoding="utf-8",
    )
    with pytest.raises(analyser.InvalidLog, match="malformed turnover_ls"):
        analyser.parse_log(log)

    bench = tmp_path / "malformed-bench.log"
    bench.write_text("DATES|1\nBROW|202001|0.01|abc|100", encoding="utf-8")
    with pytest.raises(SystemExit, match="invalid benchmark turnover"):
        parse_benchmark(bench)
