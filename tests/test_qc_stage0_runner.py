"""The Stage 0 run driver's pure pieces: naming, retargeting, log paging."""
from __future__ import annotations

import pytest

from scripts import run_qc_stage0 as runner


def test_project_name_follows_the_owner_convention():
    assert (runner._project_name(1, "MONTHLY_BATTERY", "A_large", "20260817")
            == "1. MONTHLY_BATTERY_A_LARGE - 20260817")
    assert (runner._project_name(7, "UNIVERSE_BENCHMARK", "C_broad", "20260817")
            == "7. UNIVERSE_BENCHMARK_C_BROAD - 20260817")


def test_universe_retarget_rewrites_exactly_one_declared_constant():
    source = 'HEADER = 1\nACTIVE_UNIVERSE = "B_core"\nTAIL = 2\n'
    out = runner._retarget_universe(source, "C_broad")
    assert 'ACTIVE_UNIVERSE = "C_broad"' in out
    assert out.replace('"C_broad"', '"B_core"') == source


def test_universe_retarget_refuses_missing_or_duplicate_constants():
    with pytest.raises(SystemExit, match="refusing"):
        runner._retarget_universe("class Foo:\n    pass\n", "A_large")
    doubled = 'ACTIVE_UNIVERSE = "B_core"\nACTIVE_UNIVERSE = "B_core"\n'
    with pytest.raises(SystemExit, match="refusing"):
        runner._retarget_universe(doubled, "A_large")
    with pytest.raises(SystemExit, match="unknown universe"):
        runner._retarget_universe('ACTIVE_UNIVERSE = "B_core"\n', "D_typo")


def test_every_family_maps_to_an_existing_reviewed_lean_file():
    for label, path in runner.FAMILIES.values():
        assert path.exists(), path
        assert label.isupper()


class _PagedClient:
    """Stub returning a fixed log across page boundaries."""

    def __init__(self, lines):
        self._lines = lines
        self.calls = 0

    def request(self, path, payload):
        assert path == "backtests/read/log"
        self.calls += 1
        start = payload["start"]
        return {"logs": self._lines[start:start + runner.LOG_PAGE_LINES]}


def test_log_fetch_pages_until_the_short_final_page():
    lines = [f"line-{index}" for index in range(runner.LOG_PAGE_LINES * 2 + 5)]
    client = _PagedClient(lines)
    fetched = runner._fetch_full_log(client, 1, "bt")
    assert fetched == lines
    assert client.calls == 3


def test_log_fetch_refuses_a_run_that_never_ends(monkeypatch):
    class Endless:
        def request(self, path, payload):
            return {"logs": ["x"] * runner.LOG_PAGE_LINES}

    monkeypatch.setattr(runner, "MAX_LOG_PAGES", 3)
    with pytest.raises(runner.QuantConnectError, match="truncated"):
        runner._fetch_full_log(Endless(), 1, "bt")
