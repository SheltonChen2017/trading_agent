"""Purged, grouped walk-forward splitting (strategy doc section 6.5).

Ordinary row-level `TimeSeriesSplit` or a random train/test split both leak:
a session with several tickers must stay entirely on one side of a split
(grouping), and any training row whose label OUTCOME interval overlaps the
validation window must be dropped (purging) even if its own `as_of_session`
is strictly earlier than the validation window -- its label was computed
using prices generated during (or after) the validation period. An embargo
buffer immediately before validation removes additional serially-correlated
training rows on top of pure purging.

This module is deliberately data-free: it operates only on the
`as_of_session` and label `exit_session` strings every row in
ml/labels.py's output already carries, so it has no dependency on price
data, tickers, or the feature engine.
"""
from __future__ import annotations

import dataclasses
from typing import Sequence

import pandas as pd


class SplitError(ValueError):
    """The requested split cannot be constructed from the given sessions."""


@dataclasses.dataclass(frozen=True)
class Fold:
    fold_index: int
    train_start: str
    train_end: str
    validation_start: str
    validation_end: str
    train_row_indices: tuple[int, ...]
    validation_row_indices: tuple[int, ...]
    purged_row_count: int
    embargoed_row_count: int
    embargo_sessions: int

    def to_dict(self) -> dict:
        return {
            "fold_index": self.fold_index,
            "train_start": self.train_start,
            "train_end": self.train_end,
            "validation_start": self.validation_start,
            "validation_end": self.validation_end,
            "train_row_count": len(self.train_row_indices),
            "validation_row_count": len(self.validation_row_indices),
            "purged_row_count": self.purged_row_count,
            "embargoed_row_count": self.embargoed_row_count,
            "embargo_sessions": self.embargo_sessions,
        }


def _split_into_blocks(items: list[str], n_blocks: int) -> list[list[str]]:
    """Deterministic, contiguous, near-equal partition -- no randomness, so
    output is reproducible for a fixed input regardless of any caller seed."""
    n = len(items)
    base, remainder = divmod(n, n_blocks)
    blocks: list[list[str]] = []
    start = 0
    for i in range(n_blocks):
        size = base + (1 if i < remainder else 0)
        blocks.append(items[start : start + size])
        start += size
    return blocks


def _canonical_session(value: str, *, row_index: int, field: str) -> str:
    if not isinstance(value, str):
        raise SplitError(
            f"row {row_index}: {field} must use canonical YYYY-MM-DD format"
        )
    parsed = pd.to_datetime(value, format="%Y-%m-%d", errors="coerce")
    if pd.isna(parsed) or parsed.strftime("%Y-%m-%d") != value:
        raise SplitError(
            f"row {row_index}: {field} must use canonical YYYY-MM-DD format"
        )
    return value


def purged_grouped_walk_forward_splits(
    as_of_sessions: Sequence[str],
    exit_sessions: Sequence[str],
    *,
    n_splits: int,
    embargo_sessions: int,
) -> tuple[Fold, ...]:
    """One Fold per validation block, using an expanding training window.

    `as_of_sessions[i]` / `exit_sessions[i]` are row i's entry session and
    the session its label's outcome was realized on (ml/labels.py's
    `LabelRow.as_of_session`/`.exit_session`) -- purging uses the row's own
    realized exit, not an assumed uniform horizon, so it is exact even if
    different rows carry different horizons.

    Blocks are built from the distinct `as_of_session` values only, split
    into `n_splits + 1` contiguous chunks (chronological order): the first
    chunk is a training-only warm-up period, and each of the remaining
    `n_splits` chunks is one fold's validation window, with a strictly
    expanding training window drawn from every earlier chunk (validated
    rows from an earlier fold legitimately become training data for a
    later one -- they are simply the past by then).
    """
    if len(as_of_sessions) != len(exit_sessions):
        raise SplitError("as_of_sessions and exit_sessions must be the same length")
    if not as_of_sessions:
        raise SplitError("at least one row is required")
    if isinstance(n_splits, bool) or not isinstance(n_splits, int) or n_splits < 1:
        raise SplitError("n_splits must be a positive integer")
    if (
        isinstance(embargo_sessions, bool)
        or not isinstance(embargo_sessions, int)
        or embargo_sessions < 0
    ):
        raise SplitError("embargo_sessions must be a non-negative integer")
    canonical_as_of: list[str] = []
    canonical_exit: list[str] = []
    for index, (entry, exit_session) in enumerate(zip(as_of_sessions, exit_sessions)):
        entry = _canonical_session(entry, row_index=index, field="as_of_session")
        exit_session = _canonical_session(
            exit_session, row_index=index, field="exit_session"
        )
        if exit_session < entry:
            raise SplitError(
                f"row {index}: exit_session {exit_session!r} precedes "
                f"as_of_session {entry!r}"
            )
        canonical_as_of.append(entry)
        canonical_exit.append(exit_session)

    as_of_unique = sorted(set(canonical_as_of))
    if len(as_of_unique) < n_splits + 1:
        raise SplitError(
            f"not enough distinct sessions ({len(as_of_unique)}) for "
            f"{n_splits} splits plus a warm-up block"
        )
    blocks = _split_into_blocks(as_of_unique, n_splits + 1)

    folds: list[Fold] = []
    for fold_index in range(1, n_splits + 1):
        validation_sessions = set(blocks[fold_index])
        validation_start = blocks[fold_index][0]
        validation_end = blocks[fold_index][-1]
        candidate_sessions = {
            session for block in blocks[:fold_index] for session in block
        }
        embargo_cutoff_index = (
            as_of_unique.index(validation_start) - embargo_sessions - 1
        )
        embargo_cutoff = (
            as_of_unique[embargo_cutoff_index] if embargo_cutoff_index >= 0 else ""
        )

        train_indices: list[int] = []
        validation_indices: list[int] = []
        purged = 0
        embargoed = 0
        for row_index, (entry, exit_session) in enumerate(
            zip(canonical_as_of, canonical_exit)
        ):
            if entry in validation_sessions:
                validation_indices.append(row_index)
                continue
            if entry not in candidate_sessions:
                continue  # belongs to a later, not-yet-reached block
            if exit_session >= validation_start:
                purged += 1
                continue
            if entry > embargo_cutoff:
                embargoed += 1
                continue
            train_indices.append(row_index)

        if not train_indices:
            raise SplitError(
                f"fold {fold_index}: purging and embargo removed every "
                "candidate training row"
            )
        if not validation_indices:
            raise SplitError(f"fold {fold_index}: validation block has no rows")

        train_sessions = sorted(
            {canonical_as_of[i] for i in train_indices}
        )
        folds.append(
            Fold(
                fold_index=fold_index,
                train_start=train_sessions[0],
                train_end=train_sessions[-1],
                validation_start=validation_start,
                validation_end=validation_end,
                train_row_indices=tuple(train_indices),
                validation_row_indices=tuple(validation_indices),
                purged_row_count=purged,
                embargoed_row_count=embargoed,
                embargo_sessions=embargo_sessions,
            )
        )
    return tuple(folds)
