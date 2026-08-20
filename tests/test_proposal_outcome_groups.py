"""UI-2b: the frozen proposal-outcome mapping and its read-only storage query.

The History page's primary filter groups the 19 lifecycle statuses into
user-facing outcomes. The grouping was frozen in
section 8 of the archived docs/reference/ACTION_PLAN_2026-08-02.md before
implementation; these tests pin that contract:

  - the mapping is exhaustive over STATUSES (a future status added without a
    reviewed regrouping decision fails loudly here);
  - each status belongs to exactly one group and the group content matches
    the frozen plan literal (legacy "executed" is unresolved, never Filled);
  - an unknown status displays as Other / unknown, NEVER as anything that
    reads as completed; and
  - the storage query's row semantics match the exact-status filter path
    (newest-N-of-the-filtered-kind), including the negative-match path that
    is the only way to express "Other / unknown" in SQL.

Run with: python -m pytest tests/test_proposal_outcome_groups.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.proposal_status import (
    EXECUTED,
    FILLED,
    OUTCOME_AWAITING_DECISION,
    OUTCOME_BROKER_WORKING,
    OUTCOME_CLOSED_WITHOUT_FILL,
    OUTCOME_FILLED,
    OUTCOME_GROUPS,
    OUTCOME_OTHER_UNKNOWN,
    OUTCOME_PROCESSING,
    OUTCOME_REFUSED_FAILED,
    PROPOSED,
    STATUS_OUTCOME_GROUPS,
    STATUSES,
    outcome_group_for_status,
    statuses_for_outcome_groups,
)
from assistant.storage import AssistantStore

# THE frozen grouping from the action plan (section 8, UI-2b). Regrouping a
# status -- e.g. promoting legacy "executed" into Filled -- MUST arrive
# together with a reviewed edit of this literal, because it changes what an
# operator reads as a completed trade.
FROZEN_OUTCOME_MAPPING = {
    "proposed": "Awaiting decision",
    "override_available": "Awaiting decision",
    "validating": "Processing",
    "approved": "Processing",
    "submitting": "Broker working / unresolved",
    "submission_unknown": "Broker working / unresolved",
    "reconciling": "Broker working / unresolved",
    "broker_accepted": "Broker working / unresolved",
    "partially_filled": "Broker working / unresolved",
    "cancel_pending": "Broker working / unresolved",
    "executed": "Broker working / unresolved",
    "filled": "Filled",
    "blocked": "Refused / failed",
    "validation_failed": "Refused / failed",
    "submission_failed": "Refused / failed",
    "broker_rejected": "Refused / failed",
    "canceled": "Closed without fill",
    "broker_expired": "Closed without fill",
    "expired": "Closed without fill",
    # UI-2d (2026-08-04, deliberate reviewed regrouping): the dismissed
    # archive status joins Closed without fill exactly as the action plan's
    # frozen UI-2b group list pre-assigned it.
    "dismissed": "Closed without fill",
}


# --- the frozen mapping contract -------------------------------------------


def test_mapping_is_exhaustive_over_canonical_statuses():
    """The action plan's literal requirement: set(mapping) == set(STATUSES).
    When UI-2d adds `dismissed`, this fails until the mapping gains it as a
    reviewed decision (the plan already assigns it Closed without fill)."""
    assert set(STATUS_OUTCOME_GROUPS) == set(STATUSES)


def test_mapping_matches_the_frozen_plan_literal_exactly():
    assert STATUS_OUTCOME_GROUPS == FROZEN_OUTCOME_MAPPING


def test_every_mapped_group_is_a_declared_group():
    assert set(STATUS_OUTCOME_GROUPS.values()) <= set(OUTCOME_GROUPS)


def test_other_unknown_is_reserved_for_unmapped_statuses():
    """No canonical status may hide in the catch-all: it exists only for
    values the mapping has never seen."""
    assert OUTCOME_OTHER_UNKNOWN in OUTCOME_GROUPS
    assert OUTCOME_OTHER_UNKNOWN not in STATUS_OUTCOME_GROUPS.values()


def test_unknown_status_maps_to_other_unknown_never_completed():
    """The dangerous direction: a future status silently displaying as a
    completed trade. Anything unmapped -- including None and non-strings --
    must land in Other / unknown."""
    for weird in ("dismissed_v2_future", "", None, 42, ("filled",)):
        assert outcome_group_for_status(weird) == OUTCOME_OTHER_UNKNOWN


def test_legacy_executed_is_unresolved_not_filled():
    """`executed` historically means only broker acceptance. Displaying it
    as Filled would tell the operator an unconfirmed order completed."""
    assert outcome_group_for_status(EXECUTED) == OUTCOME_BROKER_WORKING
    assert STATUS_OUTCOME_GROUPS[FILLED] == OUTCOME_FILLED
    filled_members = [
        status
        for status, group in STATUS_OUTCOME_GROUPS.items()
        if group == OUTCOME_FILLED
    ]
    assert filled_members == [FILLED]


def test_statuses_for_outcome_groups_round_trips_each_group():
    for group in OUTCOME_GROUPS:
        members = statuses_for_outcome_groups([group])
        if group == OUTCOME_OTHER_UNKNOWN:
            # Only expressible negatively; contributes no canonical status.
            assert members == ()
            continue
        assert members, f"group {group!r} has no member statuses"
        for status in members:
            assert STATUS_OUTCOME_GROUPS[status] == group


def test_statuses_for_outcome_groups_union_covers_all_statuses():
    assert set(statuses_for_outcome_groups(OUTCOME_GROUPS)) == set(STATUSES)
    assert statuses_for_outcome_groups([]) == ()


def test_group_selection_helpers_agree_with_the_lookup():
    """The positive helper (statuses_for_outcome_groups) and the per-row
    lookup (outcome_group_for_status) are two views of one rule; a status
    selected by a group must report that group, and vice versa."""
    for group in OUTCOME_GROUPS:
        selected = set(statuses_for_outcome_groups([group]))
        reported = {
            status
            for status in STATUSES
            if outcome_group_for_status(status) == group
        }
        assert selected == reported


# --- the read-only storage query -------------------------------------------

_BASE_TIME = datetime(2026, 8, 4, 12, 0, 0, tzinfo=timezone.utc)


def _seed_proposal(store, proposal_id, status, created_offset_minutes=0):
    created = _BASE_TIME + timedelta(minutes=created_offset_minutes)
    store.save_proposal(
        {
            "proposal_id": proposal_id,
            "created_at": created.isoformat(),
            "expires_at": (created + timedelta(hours=4)).isoformat(),
            "status": status,
            "idempotency_key": f"idem-{proposal_id}",
            "intent": {"ticker": "AAPL", "side": "buy", "shares": 1},
        }
    )


def _store(tmp_path):
    return AssistantStore(tmp_path / "outcomes.db")


def test_query_returns_only_the_requested_statuses(tmp_path):
    store = _store(tmp_path)
    _seed_proposal(store, "p-filled", "filled")
    _seed_proposal(store, "p-proposed", "proposed")
    _seed_proposal(store, "p-blocked", "blocked")

    rows = store.list_proposals_for_outcomes(statuses=("filled",))
    assert [p["proposal_id"] for p in rows] == ["p-filled"]

    rows = store.list_proposals_for_outcomes(statuses=("filled", "blocked"))
    assert {p["proposal_id"] for p in rows} == {"p-filled", "p-blocked"}


def test_query_matches_unknown_statuses_only_when_asked(tmp_path):
    """The negative-match path is the only SQL expression of the
    Other / unknown group; it must include exactly the rows whose status is
    outside STATUSES and never leak canonical rows."""
    store = _store(tmp_path)
    _seed_proposal(store, "p-known", "filled")
    _seed_proposal(store, "p-future", "some_future_status")

    without = store.list_proposals_for_outcomes(statuses=("filled",))
    assert {p["proposal_id"] for p in without} == {"p-known"}

    unknown_only = store.list_proposals_for_outcomes(
        statuses=(), include_unknown_statuses=True
    )
    assert {p["proposal_id"] for p in unknown_only} == {"p-future"}

    both = store.list_proposals_for_outcomes(
        statuses=("filled",), include_unknown_statuses=True
    )
    assert {p["proposal_id"] for p in both} == {"p-known", "p-future"}


def test_empty_criteria_return_no_rows_not_everything(tmp_path):
    """Fail-closed: an empty selection must not silently become '(any)'."""
    store = _store(tmp_path)
    _seed_proposal(store, "p-any", "proposed")
    assert store.list_proposals_for_outcomes(statuses=()) == []


def test_query_orders_newest_first_and_respects_the_limit(tmp_path):
    """Row semantics must match list_proposals: the newest `limit` rows OF
    THE FILTERED KIND. A client-side filter over an unfiltered page would
    instead drop older matching rows -- the regression this test exists to
    catch."""
    store = _store(tmp_path)
    # Oldest row matches the filter; newer non-matching rows would push it
    # out of a fetch-then-filter page.
    _seed_proposal(store, "p-old-filled", "filled", created_offset_minutes=0)
    for index in range(3):
        _seed_proposal(
            store,
            f"p-newer-proposed-{index}",
            "proposed",
            created_offset_minutes=10 + index,
        )
    _seed_proposal(store, "p-new-filled", "filled", created_offset_minutes=60)

    rows = store.list_proposals_for_outcomes(statuses=("filled",), limit=2)
    assert [p["proposal_id"] for p in rows] == ["p-new-filled", "p-old-filled"]

    rows = store.list_proposals_for_outcomes(statuses=("filled",), limit=1)
    assert [p["proposal_id"] for p in rows] == ["p-new-filled"]


def test_query_reports_the_authoritative_row_status(tmp_path):
    """Like list_proposals, the row's status column wins over whatever the
    stored payload froze at save time."""
    store = _store(tmp_path)
    _seed_proposal(store, "p-move", "proposed")
    store.update_proposal_status("p-move", "filled")

    rows = store.list_proposals_for_outcomes(statuses=("filled",))
    assert [p["proposal_id"] for p in rows] == ["p-move"]
    assert rows[0]["status"] == "filled"
    assert store.list_proposals_for_outcomes(statuses=("proposed",)) == []


def test_query_is_read_only(tmp_path):
    """A History filter must never mutate proposal state."""
    store = _store(tmp_path)
    _seed_proposal(store, "p-untouched", "submission_unknown")
    before = store.get_proposal("p-untouched")

    store.list_proposals_for_outcomes(
        statuses=tuple(STATUSES), include_unknown_statuses=True
    )

    assert store.get_proposal("p-untouched") == before


# --- coherence between mapping constants and the UI's frozen plan ----------


def test_awaiting_processing_groups_hold_the_pre_broker_statuses():
    """Spot-pin the safety-relevant reading order: nothing pre-broker may
    read as broker-side, and vice versa."""
    assert statuses_for_outcome_groups([OUTCOME_AWAITING_DECISION]) == (
        PROPOSED,
        "override_available",
    )
    assert statuses_for_outcome_groups([OUTCOME_PROCESSING]) == (
        "validating",
        "approved",
    )
    broker_side = set(
        statuses_for_outcome_groups(
            [OUTCOME_BROKER_WORKING, OUTCOME_FILLED, OUTCOME_CLOSED_WITHOUT_FILL]
        )
    ) | set(statuses_for_outcome_groups([OUTCOME_REFUSED_FAILED]))
    assert "proposed" not in broker_side
    assert "validating" not in broker_side
