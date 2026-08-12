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
from decimal import Decimal
from pathlib import Path

import pandas as pd
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
import assistant.research_looks as research_looks_module


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
        "data_fingerprint": "d" * 64,
        "code_commit": "c" * 40,
        "hypothesis_count": 1,
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
        data_fingerprint="d" * 64,
        code_commit="c" * 40,
    )
    b = look_fingerprint(
        surface="ui_backtest", signal_key="momentum",
        configuration={"skip_days": 21, "lookback_days": 126},
        data_source="real",
        data_fingerprint="d" * 64,
        code_commit="c" * 40,
    )
    c = look_fingerprint(
        surface="ui_backtest", signal_key="momentum",
        configuration={"lookback_days": 126, "skip_days": 22},
        data_source="real",
        data_fingerprint="d" * 64,
        code_commit="c" * 40,
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
        connection.execute(
            """
            CREATE TABLE research_looks (
                look_fingerprint TEXT PRIMARY KEY,
                surface TEXT NOT NULL,
                signal_key TEXT NOT NULL,
                configuration_json TEXT NOT NULL,
                data_source TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                repeat_count INTEGER NOT NULL
            )
            """
        )
    reopened = AssistantStore(path)
    with reopened._connect() as connection:
        recreated = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND "
            "name='research_looks'"
        ).fetchone()
    assert recreated is not None
    with reopened._connect() as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(research_looks)")
        }
    assert {"data_fingerprint", "code_commit"} <= columns
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
    window = source[start - 400 : start + 1_600]
    assert "except Exception" in window and "look_error" in window, (
        "a research-look registry failure must not block the backtest"
    )


# --- Independent-review regressions (QC2REV, 2026-08-11) ------------


def _research_frame(*, start="2026-01-02", close_shift=0.0):
    index = pd.date_range(start, periods=3, freq="B")
    close = [100.0 + close_shift, 101.0 + close_shift, 102.0 + close_shift]
    return pd.DataFrame(
        {
            "open": [99.0, 100.0, 101.0],
            "high": [101.0, 102.0, 103.0],
            "low": [98.0, 99.0, 100.0],
            "close": close,
            "volume": [1000, 1100, 1200],
        },
        index=index,
    )


def test_research_data_identity_changes_with_values_dates_or_tickers():
    """A repeat means the complete engine input is identical, not merely
    that the widgets still show the same labels."""
    fingerprint = research_looks_module.research_data_fingerprint
    original = fingerprint({"AAA": _research_frame()})
    assert fingerprint({"AAA": _research_frame()}) == original
    assert fingerprint({"AAA": _research_frame(close_shift=0.01)}) != original
    assert fingerprint({"AAA": _research_frame(start="2026-01-05")}) != original
    assert fingerprint({"BBB": _research_frame()}) != original


def test_same_settings_on_changed_data_or_code_are_distinct_looks(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    common = {
        "surface": "ui_backtest",
        "signal_key": "dips_and_ups",
        "configuration": _config(),
        "data_source": "real",
    }
    first_data = research_looks_module.research_data_fingerprint(
        {"AAA": _research_frame()}
    )
    second_data = research_looks_module.research_data_fingerprint(
        {"AAA": _research_frame(close_shift=0.01)}
    )
    record_research_look(
        store, **common, data_fingerprint=first_data, code_commit="a" * 40
    )
    record_research_look(
        store, **common, data_fingerprint=second_data, code_commit="a" * 40
    )
    record_research_look(
        store, **common, data_fingerprint=second_data, code_commit="b" * 40
    )
    assert store.count_research_looks() == 3


@pytest.mark.parametrize(
    "bad_value",
    [float("nan"), float("inf"), Decimal("1.25")],
)
def test_configuration_must_be_finite_canonical_json(tmp_path, bad_value):
    """`default=str` lets different Python values collapse to one identity
    and lets NaN/Infinity enter a supposedly canonical evidence record."""
    store = AssistantStore(tmp_path / "assistant.db")
    with pytest.raises(ResearchLookError, match="configuration"):
        _record(store, configuration={"parameter": bad_value})
    assert store.count_research_looks() == 0


def test_storage_refuses_same_fingerprint_with_different_content(tmp_path):
    """The primary key is content identity, so a conflicting row cannot be
    counted as an ordinary repeat merely because a caller supplied its hash."""
    store = AssistantStore(tmp_path / "assistant.db")
    kwargs = {
        "look_fingerprint": "a" * 64,
        "surface": "ui_backtest",
        "signal_key": "dips_and_ups",
        "data_source": "real",
        "data_fingerprint": "d" * 64,
        "code_commit": "c" * 40,
        "hypothesis_count": 1,
        "seen_at": "2026-08-11T12:00:00+00:00",
    }
    store.record_research_look(configuration={"x": 1}, **kwargs)
    with pytest.raises(ValueError, match="different research look"):
        store.record_research_look(configuration={"x": 2}, **kwargs)
    assert store.list_research_looks()[0]["repeat_count"] == 1


def test_real_market_denominator_excludes_synthetic_plumbing(tmp_path):
    """Synthetic fixtures test software, not market hypotheses, and must not
    make the displayed real-market significance threshold stricter."""
    store = AssistantStore(tmp_path / "assistant.db")
    _record(store, data_source="synthetic")
    _record(store, data_source="synthetic", configuration=_config(lookback_days=252))
    _record(store, data_source="real")
    summary = research_look_summary(
        store, surface="ui_backtest", data_source="real"
    )
    assert summary["total_looks"] == 1
    assert summary["corrected_alpha_threshold"] == 0.05
    assert summary["family"] == {
        "surface": "ui_backtest",
        "data_source": "real",
    }


def test_multi_horizon_sweep_counts_each_horizon_direction_cell(tmp_path):
    """One UI click scans horizon x direction cells. Bonferroni's
    denominator is the number of cells tested, not the number of clicks."""
    store = AssistantStore(tmp_path / "assistant.db")
    _record(
        store,
        configuration=_config(hold_days_options=[1, 5, 10]),
        hypothesis_count=6,
    )
    assert store.count_research_looks() == 6
    assert research_look_summary(store)["corrected_alpha_threshold"] == pytest.approx(
        0.05 / 6
    )


def test_ui_binds_exact_data_and_code_before_the_engine_result():
    source = (
        Path(__file__).resolve().parent.parent
        / "scripts"
        / "personal_assistant_ui.py"
    ).read_text(encoding="utf-8")
    start = source.index('if st.button("Run backtest"')
    load_at = source.index("bt_data, data_coverage =", start)
    record_at = source.index("record_research_look(", start)
    run_at = source.index("results_by_horizon = run_interactive_backtest(", start)
    assert load_at < record_at < run_at
    window = source[load_at:run_at]
    assert "research_data_fingerprint(bt_data)" in window
    assert "current_commit(require_clean=True)" in window
    assert "len(INTERACTIVE_DIRECTION_CELLS)" in window
