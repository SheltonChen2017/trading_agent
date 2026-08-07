"""Tests for ml/splits.py -- strategy doc 6.6's split-boundary test list:
every ticker on one date stays in one fold; no label interval overlaps a
validation window; embargo enforced exactly at its boundary; split output
deterministic for fixed input.
"""
from __future__ import annotations

import pytest

from ml.splits import Fold, SplitError, purged_grouped_walk_forward_splits


def _sessions(n: int) -> list[str]:
    return [f"2026-01-{day:02d}" for day in range(1, n + 1)]


def _uniform_rows(sessions: list[str], tickers: tuple[str, ...], horizon: int):
    """One row per (session, ticker); exit_session is `horizon` sessions
    later in the same fixed calendar (or the last available session if the
    horizon runs past the end -- mirrors a label builder's own tail
    handling closely enough for split tests, without importing labels.py)."""
    as_of_rows = []
    exit_rows = []
    keys = []
    for session in sessions:
        for ticker in tickers:
            idx = sessions.index(session)
            exit_idx = min(idx + horizon, len(sessions) - 1)
            as_of_rows.append(session)
            exit_rows.append(sessions[exit_idx])
            keys.append((session, ticker))
    return as_of_rows, exit_rows, keys


def test_every_ticker_on_one_date_stays_in_one_fold():
    sessions = _sessions(30)
    as_of, exit_, keys = _uniform_rows(sessions, ("AAA", "BBB", "CCC"), horizon=2)

    folds = purged_grouped_walk_forward_splits(as_of, exit_, n_splits=3, embargo_sessions=2)

    for fold in folds:
        val_sessions = {as_of[i] for i in fold.validation_row_indices}
        train_sessions = {as_of[i] for i in fold.train_row_indices}
        assert val_sessions.isdisjoint(train_sessions)
        # every row sharing a validation date is IN this fold's validation set
        for session in val_sessions:
            row_indices_for_session = {i for i, s in enumerate(as_of) if s == session}
            assert row_indices_for_session <= set(fold.validation_row_indices)


def test_no_label_interval_overlaps_validation_window():
    sessions = _sessions(30)
    as_of, exit_, _ = _uniform_rows(sessions, ("AAA",), horizon=3)

    folds = purged_grouped_walk_forward_splits(as_of, exit_, n_splits=3, embargo_sessions=3)

    for fold in folds:
        for i in fold.train_row_indices:
            assert exit_[i] < fold.validation_start


def test_embargo_enforced_exactly_at_boundary():
    sessions = _sessions(20)
    # zero horizon so purging alone never removes anything -- isolates the
    # embargo's own effect from purge's.
    as_of = list(sessions)
    exit_ = list(sessions)

    embargo = 2
    folds = purged_grouped_walk_forward_splits(as_of, exit_, n_splits=1, embargo_sessions=embargo)
    fold = folds[0]
    validation_start_idx = sessions.index(fold.validation_start)
    embargoed_sessions = set(sessions[validation_start_idx - embargo : validation_start_idx])

    trained_sessions = {as_of[i] for i in fold.train_row_indices}
    assert trained_sessions.isdisjoint(embargoed_sessions)
    # every session strictly before the embargo window (and before validation
    # in the warm-up block) IS used for training
    warmup_sessions = set(sessions[: validation_start_idx - embargo])
    assert warmup_sessions <= trained_sessions


def test_purging_removes_rows_whose_exit_reaches_into_validation():
    sessions = _sessions(20)
    as_of, exit_, _ = _uniform_rows(sessions, ("AAA",), horizon=5)

    # embargo=0 isolates purging's own effect
    folds = purged_grouped_walk_forward_splits(as_of, exit_, n_splits=1, embargo_sessions=0)
    fold = folds[0]
    assert fold.purged_row_count > 0
    for i in fold.train_row_indices:
        assert exit_[i] < fold.validation_start


def test_split_is_deterministic_for_fixed_input():
    sessions = _sessions(24)
    as_of, exit_, _ = _uniform_rows(sessions, ("AAA", "BBB"), horizon=2)

    first = purged_grouped_walk_forward_splits(as_of, exit_, n_splits=2, embargo_sessions=2)
    second = purged_grouped_walk_forward_splits(as_of, exit_, n_splits=2, embargo_sessions=2)

    assert first == second


def test_expanding_window_later_fold_trains_on_earlier_validation_sessions():
    sessions = _sessions(30)
    as_of, exit_, _ = _uniform_rows(sessions, ("AAA",), horizon=0)

    folds = purged_grouped_walk_forward_splits(as_of, exit_, n_splits=3, embargo_sessions=0)
    fold_1_validation = {as_of[i] for i in folds[0].validation_row_indices}
    fold_2_training = {as_of[i] for i in folds[1].train_row_indices}

    assert fold_1_validation <= fold_2_training


def test_rejects_mismatched_lengths():
    with pytest.raises(SplitError, match="same length"):
        purged_grouped_walk_forward_splits(["2026-01-01"], [], n_splits=1, embargo_sessions=0)


def test_rejects_empty_input():
    with pytest.raises(SplitError, match="at least one row"):
        purged_grouped_walk_forward_splits([], [], n_splits=1, embargo_sessions=0)


def test_rejects_exit_before_entry():
    with pytest.raises(SplitError, match="precedes"):
        purged_grouped_walk_forward_splits(
            ["2026-01-05"], ["2026-01-01"], n_splits=1, embargo_sessions=0
        )


@pytest.mark.parametrize(
    "bad_session", ("2026-1-5", "not-a-date", "", None)
)
def test_rejects_noncanonical_or_missing_session_values(bad_session):
    with pytest.raises(SplitError, match="canonical YYYY-MM-DD"):
        purged_grouped_walk_forward_splits(
            [bad_session, "2026-01-06"],
            ["2026-01-07", "2026-01-08"],
            n_splits=1,
            embargo_sessions=0,
        )


def test_rejects_non_positive_n_splits():
    with pytest.raises(SplitError, match="n_splits"):
        purged_grouped_walk_forward_splits(
            ["2026-01-01"], ["2026-01-01"], n_splits=0, embargo_sessions=0
        )


def test_rejects_negative_embargo():
    with pytest.raises(SplitError, match="embargo_sessions"):
        purged_grouped_walk_forward_splits(
            ["2026-01-01"], ["2026-01-01"], n_splits=1, embargo_sessions=-1
        )


def test_rejects_too_few_distinct_sessions_for_requested_splits():
    sessions = _sessions(3)
    as_of, exit_, _ = _uniform_rows(sessions, ("AAA",), horizon=0)
    with pytest.raises(SplitError, match="not enough distinct sessions"):
        purged_grouped_walk_forward_splits(as_of, exit_, n_splits=5, embargo_sessions=0)


def test_fold_to_dict_is_json_serializable():
    import json

    sessions = _sessions(20)
    as_of, exit_, _ = _uniform_rows(sessions, ("AAA",), horizon=2)
    folds = purged_grouped_walk_forward_splits(as_of, exit_, n_splits=1, embargo_sessions=2)
    json.dumps(folds[0].to_dict())
