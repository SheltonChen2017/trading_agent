"""Built-in synthetic accounting run; never additional data or market evidence."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest

from research.target_price_revisions_development import fixture_backtest as built_in
from research.target_price_revisions_development import scoring


def body(report):
    assert hashlib.sha256(report.payload).hexdigest() == report.sha256
    result = json.loads(report.payload)
    assert report.payload == (json.dumps(result, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    return result


def test_built_in_three_session_run_is_deterministic_complete_and_zero_authority():
    first = built_in.run_builtin_fixture_backtest()
    second = built_in.run_builtin_fixture_backtest()
    assert first == second
    result = body(first)
    assert result["schema"] == "tpr-builtin-synthetic-backtest-v1"
    assert result["software_completed"] is True
    assert result["status"] == "COMPLETED"
    assert result["real_backtest_ready"] is False
    assert result["independent_review_required"] is False
    assert all(value is False for value in result["authority"].values())
    assert all(value == 0 for value in result["actual_external_actions"].values())
    assert result["d0_audit"] == "spent-not-renewable"
    assert result["d0_context"]["plan_sha256"] == built_in.readiness.D0_PLAN_SHA256
    assert result["d0_context"]["aggregate_report_sha256"] == built_in.readiness.D0_REPORT_SHA256
    assert result["execution"]["report"]["software_completed"] is True
    assert len(first.terminal_state.receipts) == 3
    assert all(row.shares == 0 for row in first.terminal_state.positions)
    for forbidden in ("alpha", "confidence", "return", "profit", "sharpe"):
        assert forbidden not in result


def test_factory_normalizes_once_at_original_cutoff_and_preserves_age(monkeypatch):
    original_normalize = built_in.normalize_fixture_events
    original_score = scoring.score_fixture_stocks
    normalizations, ages = [], []

    def normalize(*args, **kwargs):
        normalizations.append(kwargs["decision_cutoff_utc"])
        return original_normalize(*args, **kwargs)

    def score(*args, **kwargs):
        result = original_score(*args, **kwargs)
        ages.append({row.age_sessions for row in result.versions})
        return result

    monkeypatch.setattr(built_in, "normalize_fixture_events", normalize)
    monkeypatch.setattr(scoring, "score_fixture_stocks", score)
    steps = built_in.fixture_steps()
    assert normalizations == ["2026-10-01T22:00:00Z"]
    assert ages == [{1}, {2}, {3}]
    assert len(steps) == 3
    assert [step["target"].decision_session_index for step in steps] == [101, 102, 103]
    assert [step["open_session_index"] for step in steps] == [102, 103, 104]
    assert [dict((row.etf_id, row.weight) for row in step["target"].targets) for step in steps] == [
        {"SYNTHETIC-ETF-A": "0.2", "SYNTHETIC-ETF-OLD": "0"},
        {"SYNTHETIC-ETF-A": "0.1", "SYNTHETIC-ETF-OLD": "0"},
        {"SYNTHETIC-ETF-A": "0", "SYNTHETIC-ETF-OLD": "0"},
    ]


def test_builtin_transcript_has_initial_exit_buy_then_reduction_and_final_exit():
    report = built_in.run_builtin_fixture_backtest()
    fills = [json.loads(receipt.payload)["after"]["fills"] for receipt in report.terminal_state.receipts]
    assert [[(row["side"], row["etf_id"], row["shares"]) for row in session] for session in fills] == [
        [("sell", "SYNTHETIC-ETF-OLD", 10), ("buy", "SYNTHETIC-ETF-A", 19)],
        [("sell", "SYNTHETIC-ETF-A", 11)],
        [("sell", "SYNTHETIC-ETF-A", 8)],
    ]
    assert body(report)["execution"]["report"]["totals"]["fills"] == 4


def test_execution_price_mutation_cannot_rewrite_frozen_decisions():
    from research.target_price_revisions_development.backtesting import run_fixture_backtest
    from research.target_price_revisions_development.simulation import freeze_fixture_portfolio

    original = built_in.fixture_steps()
    changed = deepcopy(original)
    frozen = tuple(scoring.fixture_target_sha256(step["target"]) for step in original)
    changed[0]["quotes"]["SYNTHETIC-ETF-A"]["price"] = "11"
    changed[2]["quotes"]["SYNTHETIC-ETF-A"]["price"] = "22"
    assert tuple(scoring.fixture_target_sha256(step["target"]) for step in changed) == frozen
    initial = freeze_fixture_portfolio("900", ({"etf_id": "SYNTHETIC-ETF-OLD", "shares": 10},))
    parameters = dict(expected_initial_sha256=initial.sha256, fee_per_order="1",
                      slippage_bps="100", name_cap="0.3")
    first = run_fixture_backtest(initial, original, **parameters)
    second = run_fixture_backtest(initial, changed, **parameters)
    assert first.sha256 != second.sha256
    assert tuple(scoring.fixture_target_sha256(step["target"]) for step in built_in.fixture_steps()) == frozen


def test_pure_builtin_run_has_no_file_network_or_operator_dependency(monkeypatch):
    import builtins
    import io
    import os
    import socket

    def refuse(*args, **kwargs):
        pytest.fail("built-in synthetic run attempted I/O")

    for module, name in ((builtins, "open"), (io, "open"), (os, "open"), (socket, "socket")):
        monkeypatch.setattr(module, name, refuse)
    assert body(built_in.run_builtin_fixture_backtest())["software_completed"] is True


def test_main_stdout_only_matches_content_addressed_report(capsys):
    report = built_in.run_builtin_fixture_backtest()
    assert built_in.main([]) == 0
    captured = capsys.readouterr()
    assert captured.out.encode("utf-8") == report.payload
    assert captured.err == ""


def test_help_does_not_start_run(monkeypatch, capsys):
    def refuse():
        pytest.fail("help started fixture run")

    monkeypatch.setattr(built_in, "run_builtin_fixture_backtest", refuse)
    with pytest.raises(SystemExit) as raised:
        built_in.main(["--help"])
    assert raised.value.code == 0
    output = capsys.readouterr().out
    assert "fixture-only" in output
    assert "No file inputs" in output


@pytest.mark.parametrize("arguments", [
    ["--input", "SYNTHETIC-FILE"], ["--output", "SYNTHETIC-FILE"],
    ["--data", "SYNTHETIC-FILE"], ["SYNTHETIC-FILE"], ["--real-data"],
    ["--qc"], ["--fee", "0"], ["--help-extra"],
])
def test_cli_has_no_data_path_write_or_policy_override_arguments(arguments, monkeypatch, capsys):
    def refuse():
        pytest.fail("invalid CLI input started fixture run")

    monkeypatch.setattr(built_in, "run_builtin_fixture_backtest", refuse)
    with pytest.raises(SystemExit) as raised:
        built_in.main(arguments)
    assert raised.value.code == 2
    assert capsys.readouterr().out == ""


def test_returned_payload_and_targets_do_not_alias_later_factory_calls():
    first = built_in.fixture_steps()
    first[0]["quotes"]["SYNTHETIC-ETF-A"]["price"] = "999"
    assert built_in.fixture_steps()[0]["quotes"]["SYNTHETIC-ETF-A"]["price"] == "10"
    report = built_in.run_builtin_fixture_backtest()
    edited = body(report)
    edited["authority"]["trading"] = True
    assert body(report)["authority"]["trading"] is False


def test_recipe_binds_separate_data_config_decisions_and_execution():
    result = body(built_in.run_builtin_fixture_backtest())
    recipe = result["fixture_recipe"]
    assert recipe["decision_weights"] == ["0.2", "0.1", "0"]
    assert recipe["original_eligible_session_index"] == 100
    assert result["lineage_identity_kind"] == "fixture-content-not-source-or-code-custody"
    configuration = result["fixture_configuration"]
    assert configuration["execution"] == {"fee_per_order": "1", "slippage_bps": "100", "name_cap": "0.3"}
    assert configuration["allocation"]["additions_cap"] == "0.2"
    assert configuration["scoring"]["clip_absolute"] == "10"
    for name in ("fixture_recipe_sha256", "generated_input_sha256", "configuration_sha256",
                 "ordered_targets_sha256"):
        assert len(result[name]) == 64
    assert result["ordered_targets_sha256"] != result["execution"]["report_sha256"]
    assert result["readiness"]["report"]["software_review_policy"] == built_in.readiness.SOFTWARE_REVIEW_OWNER_WAIVED
    assert result["readiness"]["report"]["independent_review_required"] is False
    assert "independent_software_review_required" not in result["readiness"]["report"]["blockers"]


def test_run_spec_binds_exact_synthetic_open_window_not_an_unused_example():
    result = body(built_in.run_builtin_fixture_backtest())
    spec = result["readiness"]["run_spec"]
    assert spec["synthetic_outcome_window"] == {"start": "2026-10-06", "end": "2026-10-08"}
    payload = (json.dumps(spec, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    assert hashlib.sha256(payload).hexdigest() == result["readiness"]["run_spec_sha256"]
    assert spec["lineage"]["code_sha256"] == result["fixture_recipe_sha256"]
    assert result["lineage_identity_kind"] == "fixture-content-not-source-or-code-custody"
    sessions = result["execution"]["report"]["sessions"]
    assert sessions[0]["receipt"]["inputs"]["open_utc"][:10] == spec["synthetic_outcome_window"]["start"]
    assert sessions[-1]["receipt"]["inputs"]["open_utc"][:10] == spec["synthetic_outcome_window"]["end"]
