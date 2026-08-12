"""QC-2 research-look registry.

The registry exists so the multiplicity correction has an honest
denominator. These tests pin the properties that make the count honest --
that a look cannot be dropped, that a repeat is not a new test, and that a
changed parameter is -- rather than merely that rows can be written.

Run with: python -m pytest tests/test_research_looks.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.research_looks import (
    ResearchLookError,
    look_fingerprint,
    record_research_look,
    research_look_summary,
)
from assistant.storage import AssistantStore
from backtest.engine import bonferroni_threshold


def _config(**overrides):
    configuration = {
        "params": {"return_z_threshold": 2.0, "volume_z_threshold": 1.5},
        "scope": "universe",
        "lookback_days": 504,
        "hold_days_options": [5, 10],
        "entry_timing": "next_open",
        "slippage_pct": 0.05,
    }
    configuration.update(overrides)
    return configuration


def _record(store, **overrides):
    kwargs = {
        "surface": "ui_backtest",
        "signal_key": "dips_and_ups",
        "configuration": _config(),
        "data_source": "real",
    }
    kwargs.update(overrides)
    return record_research_look(store, **kwargs)


def test_an_empty_registry_reports_the_uncorrected_alpha(tmp_path):
    """No tests run means no penalty earned."""
    store = AssistantStore(tmp_path / "assistant.db")
    summary = research_look_summary(store)
    assert summary["total_looks"] == 0
    assert summary["corrected_alpha_threshold"] == 0.05


def test_each_distinct_configuration_tightens_the_threshold(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    _record(store)
    _record(store, configuration=_config(lookback_days=252))
    _record(store, configuration=_config(hold_days_options=[21]))
    summary = research_look_summary(store)
    assert summary["total_looks"] == 3
    assert summary["corrected_alpha_threshold"] == bonferroni_threshold(3, alpha=0.05)
    assert summary["corrected_alpha_threshold"] < 0.05


def test_rerunning_an_identical_configuration_is_not_a_new_test(tmp_path):
    """The engine is deterministic: the same configuration returns the same
    answer, so counting it twice would inflate the denominator and make the
    threshold unfairly strict."""
    store = AssistantStore(tmp_path / "assistant.db")
    first = _record(store)
    assert first["is_new_look"] is True
    assert first["repeat_count"] == 1
    second = _record(store)
    assert second["is_new_look"] is False
    assert second["repeat_count"] == 2
    assert research_look_summary(store)["total_looks"] == 1


def test_changing_any_parameter_is_a_new_look(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    _record(store)
    _record(store, configuration=_config(params={"return_z_threshold": 2.5}))
    assert research_look_summary(store)["total_looks"] == 2


def test_the_same_configuration_on_different_data_is_a_different_test(tmp_path):
    """Synthetic and real history are not the same experiment; collapsing
    them into one look would hide a real test."""
    store = AssistantStore(tmp_path / "assistant.db")
    _record(store, data_source="synthetic")
    _record(store, data_source="real")
    assert research_look_summary(store)["total_looks"] == 2


def test_a_recorded_look_cannot_be_removed_or_rewritten(tmp_path):
    """Discarding disappointing looks is the exact behaviour the
    correction exists to price in, so the registry offers no way to do it."""
    store = AssistantStore(tmp_path / "assistant.db")
    _record(store)
    for forbidden in ("delete_research_look", "remove_research_look",
                      "clear_research_looks", "update_research_look"):
        assert not hasattr(store, forbidden), (
            f"AssistantStore exposes {forbidden!r}; a look that happened "
            "must not be removable from the multiplicity denominator"
        )
    # The stored configuration is immutable: re-recording the same
    # fingerprint bumps counters only.
    before = store.list_research_looks()[0]
    _record(store)
    after = store.list_research_looks()[0]
    assert after["configuration"] == before["configuration"]
    assert after["first_seen_at"] == before["first_seen_at"]
    assert after["repeat_count"] == before["repeat_count"] + 1


def test_the_fingerprint_ignores_key_order_but_not_values():
    """Dict ordering is not a new experiment; a different value is."""
    a = look_fingerprint(
        surface="ui_backtest", signal_key="momentum",
        configuration={"lookback_days": 126, "skip_days": 21},
        data_source="real",
    )
    b = look_fingerprint(
        surface="ui_backtest", signal_key="momentum",
        configuration={"skip_days": 21, "lookback_days": 126},
        data_source="real",
    )
    c = look_fingerprint(
        surface="ui_backtest", signal_key="momentum",
        configuration={"lookback_days": 126, "skip_days": 22},
        data_source="real",
    )
    assert a == b
    assert a != c


def test_incomplete_provenance_is_refused(tmp_path):
    """A look with no surface, signal, or data source cannot be attributed,
    and an unattributable look is not an auditable one."""
    store = AssistantStore(tmp_path / "assistant.db")
    for field in ("surface", "signal_key", "data_source"):
        with pytest.raises(ResearchLookError, match="required"):
            _record(store, **{field: "  "})
    with pytest.raises(ResearchLookError, match="must be an object"):
        _record(store, configuration=["not", "a", "dict"])
    with pytest.raises(ResearchLookError, match="timezone-aware"):
        _record(store, now=datetime(2026, 8, 11, 12, 0))
    assert research_look_summary(store)["total_looks"] == 0


def test_alpha_is_validated(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    for bad in (0, 1, -0.1, 1.5, True):
        with pytest.raises(ResearchLookError, match="alpha"):
            research_look_summary(store, alpha=bad)


def test_the_summary_says_the_threshold_is_not_sufficient(tmp_path):
    """The number invites over-reading, so the wording must not."""
    store = AssistantStore(tmp_path / "assistant.db")
    _record(store)
    text = research_look_summary(store)["interpretation"].lower()
    assert "necessary, not sufficient" in text
    assert "confirmation-only" in text and "by-block" in text


def test_the_registry_table_migrates_onto_a_pre_migration_database(tmp_path):
    """CLAUDE.md 7: idempotent and backward-compatible, both directions."""
    path = tmp_path / "assistant.db"
    store = AssistantStore(path)
    _record(store)
    with store._connect() as connection:
        connection.execute("DROP TABLE research_looks")
    reopened = AssistantStore(path)
    with reopened._connect() as connection:
        recreated = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND "
            "name='research_looks'"
        ).fetchone()
    assert recreated is not None
    assert reopened.count_research_looks() == 0
    assert AssistantStore(path).count_research_looks() == 0


def test_the_ui_records_the_look_before_the_result_is_known():
    """Source-level: recording must precede the engine call.

    If the look were recorded after results came back, an exception -- or a
    future edit that returns early on a bad result -- would silently drop a
    configuration from the denominator. That is the one ordering that makes
    the count dishonest, and it cannot be observed at runtime.
    """
    source = (
        Path(__file__).resolve().parent.parent
        / "scripts"
        / "personal_assistant_ui.py"
    ).read_text(encoding="utf-8")
    record_at = source.index("record_research_look(")
    run_at = source.index("results_by_horizon = run_interactive_backtest(")
    assert record_at < run_at, (
        "the research look must be recorded BEFORE the backtest runs, so a "
        "configuration cannot be dropped once its answer disappoints"
    )


def test_the_registry_never_blocks_research():
    """Source-level: the UI must treat a registry failure as a warning."""
    source = (
        Path(__file__).resolve().parent.parent
        / "scripts"
        / "personal_assistant_ui.py"
    ).read_text(encoding="utf-8")
    start = source.index("record_research_look(")
    window = source[start - 400 : start + 900]
    assert "except Exception" in window and "look_error" in window, (
        "a research-look registry failure must not block the backtest"
    )
