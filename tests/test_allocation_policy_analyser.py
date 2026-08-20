"""APQ-2 regressions: the allocation-policy analyser.

Dangerous directions per the plan: a non-finite present turnover token
relabelled as unavailability, misaligned policy dates surviving the
join, the charge magnitude unpinned (S0R-008 class), corruption in the
priced/targeted fields, and the frozen floor bypassed.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import analyse_qc_allocation_policy as analyser

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 64
MEMBERS = {"P0": 1, "P1": 2, "P2": 4, "P3": 3}


def _months(n: int) -> list[str]:
    out = []
    year, month = 2022, 2
    for _ in range(n):
        out.append(f"{year}{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return out


def _log(tmp_path: Path, months=None, mutate=None) -> Path:
    """Default log: 24 aligned months, P0 +1%/mo, others +0.5%/mo, all
    turnovers 0.0 except one declared-unavailable month for P1."""
    months = months or _months(analyser.MIN_MONTHS)
    lines = ["POLICIES|P0|P1|P2|P3", f"DATES|{len(months)}"]
    rows = []
    for index, month in enumerate(months):
        for policy in ("P0", "P1", "P2", "P3"):
            ret = "0.01" if policy == "P0" else "0.005"
            turn = "" if (policy == "P1" and index == 3) else "0.0"
            count = MEMBERS[policy]
            rows.append([month, policy, ret, turn, str(count), str(count)])
    if mutate:
        rows = mutate(rows)
    lines += ["PROW|" + "|".join(row) for row in rows]
    path = tmp_path / "allocation.log"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_report_carries_descriptives_labels_and_pinned_charge(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(analyser, "DRAWS", 100)   # >= 60 clears 0.05/3
    frame = analyser.parse_log(_log(tmp_path))
    report = analyser.analyse(frame)
    assert report["months"] == 24
    # Both required labels for reporting the optional test family.
    assert "3 cells" in report["family"]
    assert "NOT added" in report["scope"]
    assert report["bonferroni_threshold"] == pytest.approx(0.05 / 3)
    # Descriptive primary table fields.
    p0 = report["policies"]["P0"]
    assert p0["gross"]["cagr"] is not None
    assert "max_days_under_water" in p0["time_under_water"]
    # versus_p0: excess mean is exactly -0.5%/month for every candidate.
    for policy in ("P1", "P2", "P3"):
        block = report["versus_p0"][policy]
        assert block["excess_monthly_mean"] == pytest.approx(-0.005)
        assert block["excess_mean_p_value"] is not None
    # S0R-008-class magnitude pin: P1's one declared-unavailable month is
    # charged the full 1.0 one-way; all its present turnovers are 0.0.
    p1 = report["policies"]["P1"]
    assert p1["unavailable_turnover_periods"] == 1
    delta = (p1["net"]["0bps"]["mean_period_return"]
             - p1["net"]["10bps"]["mean_period_return"])
    assert delta == pytest.approx(1.0 * 2.0 * 10.0 / 10_000.0 / 24)
    # P0 has no unavailable months: zero net drag at 0.0 turnover.
    p0_delta = (p0["net"]["0bps"]["mean_period_return"]
                - p0["net"]["10bps"]["mean_period_return"])
    assert p0_delta == pytest.approx(0.0)


def test_present_nonfinite_turnover_token_is_refused(tmp_path: Path):
    def mutate(rows):
        rows[5][3] = "nan"
        return rows
    with pytest.raises(analyser.AllocationLogError, match="invalid turnover"):
        analyser.parse_log(_log(tmp_path, mutate=mutate))


def test_misaligned_policy_dates_are_refused(tmp_path: Path):
    def mutate(rows):
        return [row for row in rows
                if not (row[0] == "202205" and row[1] == "P3")]
    with pytest.raises(analyser.AllocationLogError, match="dates differ"):
        analyser.parse_log(_log(tmp_path, mutate=mutate))


def test_unknown_policy_duplicate_and_corrupt_counts_are_refused(
    tmp_path: Path,
):
    def unknown(rows):
        rows[0][1] = "P4"
        return rows
    with pytest.raises(analyser.AllocationLogError, match="unknown policy"):
        analyser.parse_log(_log(tmp_path, mutate=unknown))

    def duplicate(rows):
        return rows + [rows[0]]
    with pytest.raises(analyser.AllocationLogError, match="duplicate"):
        analyser.parse_log(_log(tmp_path, mutate=duplicate))

    def corrupt(rows):
        rows[2][4] = "5"          # priced != targeted
        return rows
    with pytest.raises(analyser.AllocationLogError, match="priced != targeted"):
        analyser.parse_log(_log(tmp_path, mutate=corrupt))


def test_truncation_and_frozen_floor_are_refused(tmp_path: Path):
    short = _log(tmp_path, months=_months(23))
    with pytest.raises(analyser.AllocationLogError, match="24-month floor"):
        analyser.parse_log(short)

    def drop_month(rows):
        return [row for row in rows if row[0] != "202303"]
    with pytest.raises(analyser.AllocationLogError, match="truncated"):
        analyser.parse_log(_log(tmp_path, mutate=drop_month))


def test_nonfinite_return_is_refused(tmp_path: Path):
    def mutate(rows):
        rows[1][2] = "inf"
        return rows
    with pytest.raises(analyser.AllocationLogError, match="non-finite return"):
        analyser.parse_log(_log(tmp_path, mutate=mutate))


def test_noncanonical_month_label_is_refused(tmp_path: Path):
    def mutate(rows):
        for row in rows:
            if row[0] == "202202":
                row[0] = "202213"
        return rows
    with pytest.raises(analyser.AllocationLogError, match="month label"):
        analyser.parse_log(_log(tmp_path, mutate=mutate))


def test_analyser_is_invocable_in_script_mode():
    """S1R-001 lesson: the script must run as a script, not only as a
    module."""
    result = subprocess.run(
        [sys.executable,
         str(ROOT / "scripts" / "analyse_qc_allocation_policy.py"), "--help"],
        capture_output=True, text=True, timeout=120,
        cwd=str(ROOT / "scripts"),
    )
    assert result.returncode == 0, result.stderr
    assert "ModuleNotFoundError" not in result.stderr


def test_main_records_full_run_identity(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(analyser, "DRAWS", 100)   # >= 60 clears 0.05/3
    log = _log(tmp_path)
    output = tmp_path / "report.json"
    assert analyser.main([
        "--log", str(log),
        "--run-id", f"123,compile-1,backtest-1,{SHA}",
        "--output", str(output),
    ]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["quantconnect_run"] == {
        "project_id": "123", "compile_id": "compile-1",
        "backtest_id": "backtest-1", "source_sha256": SHA,
    }
    assert payload["input_log"]["sha256"]


def test_module_never_calls_the_alpha_battery_analyse():
    """Plan requirement: this analyser must not call analyse() from the
    alpha battery (that computes IC / long-short — different family)."""
    import ast
    source = (ROOT / "scripts" / "analyse_qc_allocation_policy.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and \
                "analyse_qc_alpha_battery" in node.module:
            imported = {alias.name for alias in node.names}
            assert "analyse" not in imported
