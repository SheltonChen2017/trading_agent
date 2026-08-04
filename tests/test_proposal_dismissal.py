"""UI-2d: dismiss/archive lifecycle, eligibility, and atomicity.

Pins the archived plan's contract (docs/reference/
PROPOSAL_HISTORY_CLEANUP_IMPLEMENTATION_PLAN.md): `dismissed` is terminal
and non-inflight; only pristine `proposed`/`expired` rows qualify; any
broker/reservation/allocation-batch reference or execution-shaped payload
evidence refuses; previews hash-bind confirmations to database state; bulk
dismissal is all-or-nothing; replay is idempotent; and dismissal deletes
nothing and calls no broker.

Run with: python -m pytest tests/test_proposal_dismissal.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.proposal_status import (
    ACTIVE_BROKER_ORDER_STATUSES,
    DISMISSED,
    DISMISSIBLE_SOURCE_STATUSES,
    IN_FLIGHT_INTENT_STATUSES,
    STATUSES,
    UNRESOLVED_BROKER_STATE_STATUSES,
)
from assistant.storage import AssistantStore

_BASE_TIME = datetime(2026, 8, 4, 16, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def store(tmp_path):
    return AssistantStore(tmp_path / "dismissal.db")


def _seed(store, proposal_id, status="proposed", payload_extra=None, offset_minutes=0):
    created = _BASE_TIME + timedelta(minutes=offset_minutes)
    proposal = {
        "proposal_id": proposal_id,
        "created_at": created.isoformat(),
        "expires_at": (created + timedelta(hours=4)).isoformat(),
        "status": status,
        "idempotency_key": f"idem-{proposal_id}",
        "intent": {"ticker": "AAPL", "side": "buy", "shares": 2},
        "reasons": ["seeded"],
        "evidence_status": "test",
    }
    proposal.update(payload_extra or {})
    store.save_proposal(proposal)
    return proposal


def _dismiss(store, ids, reason="unused watchlist experiment"):
    preview = store.proposal_dismissal_eligibility(ids)
    return store.dismiss_proposals(
        ids,
        dismissed_by="local_operator",
        reason=reason,
        expected_preview_hash=preview.preview_hash,
    )


# --- lifecycle classification ----------------------------------------------


def test_dismissed_is_canonical_terminal_and_non_inflight():
    assert DISMISSED in STATUSES
    assert DISMISSED not in IN_FLIGHT_INTENT_STATUSES
    assert DISMISSED not in UNRESOLVED_BROKER_STATE_STATUSES
    assert DISMISSED not in ACTIVE_BROKER_ORDER_STATUSES
    assert DISMISSIBLE_SOURCE_STATUSES == ("proposed", "expired")


def test_dismissed_proposal_cannot_be_claimed_for_approval(store):
    _seed(store, "p-claimed", status="proposed")
    assert _dismiss(store, ["p-claimed"]).dismissed_ids == ("p-claimed",)

    claim = store.claim_proposal(
        "p-claimed", expected_status=("proposed", "override_available")
    )
    assert claim is None
    assert store.get_proposal("p-claimed")["status"] == DISMISSED


def test_dismissed_proposal_does_not_hold_its_ticker_side_slot(store):
    """Dismissal must not block an unrelated later proposal for the same
    ticker/side the way in-flight statuses deliberately do."""
    _seed(store, "p-old", status="proposed")
    _dismiss(store, ["p-old"])
    _seed(store, "p-new", status="proposed", offset_minutes=5)

    claimed = store.claim_proposal(
        "p-new",
        expected_status="proposed",
        conflicting_intent_statuses=IN_FLIGHT_INTENT_STATUSES,
    )
    assert claimed is not None
    assert claimed["status"] == "validating"


# --- eligibility ------------------------------------------------------------


def test_pristine_proposed_and_expired_are_dismissible(store):
    _seed(store, "p-proposed", status="proposed")
    _seed(store, "p-expired", status="expired")
    preview = store.proposal_dismissal_eligibility(["p-proposed", "p-expired"])
    assert preview.dismissible_ids == ("p-proposed", "p-expired")
    assert all(row.dismissible for row in preview.rows)

    result = _dismiss(store, ["p-proposed", "p-expired"])
    assert result.dismissed_ids == ("p-proposed", "p-expired")
    for proposal_id, source in (("p-proposed", "proposed"), ("p-expired", "expired")):
        row = store.get_proposal(proposal_id)
        assert row["status"] == DISMISSED
        assert row["dismissed_from_status"] == source
        assert row["dismissed_by"] == "local_operator"
        assert row["dismissed_reason"] == "unused watchlist experiment"
        assert row["dismissed_at"] == result.dismissed_at


@pytest.mark.parametrize(
    "status",
    [s for s in STATUSES if s not in ("proposed", "expired", "dismissed")],
)
def test_every_other_status_is_refused(store, status):
    _seed(store, "p-status", status=status)
    preview = store.proposal_dismissal_eligibility(["p-status"])
    assert preview.dismissible_ids == ()
    assert any("not dismissible" in r for r in preview.rows[0].refusal_reasons)
    with pytest.raises(ValueError, match="all-or-nothing"):
        store.dismiss_proposals(
            ["p-status"],
            dismissed_by="local_operator",
            reason="x",
            expected_preview_hash=preview.preview_hash,
        )
    assert store.get_proposal("p-status")["status"] == status


def test_unknown_proposal_id_is_refused_not_ignored(store):
    preview = store.proposal_dismissal_eligibility(["p-ghost"])
    assert preview.dismissible_ids == ()
    assert preview.rows[0].refusal_reasons == ("unknown proposal_id",)


def test_child_rows_refuse_dismissal(store):
    """The dangerous direction: a status corrupted back to `proposed` on a
    proposal that actually reached the broker must still refuse."""
    _seed(store, "p-order", status="proposed")
    _seed(store, "p-event", status="proposed")
    _seed(store, "p-reservation", status="proposed")
    now = _BASE_TIME.isoformat()
    with store._connect() as connection:
        connection.execute(
            "INSERT INTO broker_orders(order_id, proposal_id, submitted_at, "
            "status, payload_json) VALUES ('o1', 'p-order', ?, 'accepted', '{}')",
            (now,),
        )
        connection.execute(
            "INSERT INTO broker_orders(order_id, proposal_id, submitted_at, "
            "status, payload_json) VALUES ('o2', 'p-event', ?, 'accepted', '{}')",
            (now,),
        )
        connection.execute(
            "INSERT INTO broker_order_events(event_id, order_id, proposal_id, "
            "event_type, event_at, status, payload_json) "
            "VALUES ('e1', 'o2', 'p-event', 'accepted', ?, 'accepted', '{}')",
            (now,),
        )
        connection.execute(
            "INSERT INTO execution_reservations(proposal_id, trading_day, "
            "reserved_notional, reserved_notional_text, created_at) "
            "VALUES ('p-reservation', '2026-08-04', 100.0, '100', ?)",
            (now,),
        )

    preview = store.proposal_dismissal_eligibility(
        ["p-order", "p-event", "p-reservation"]
    )
    assert preview.dismissible_ids == ()
    reasons = {row.proposal_id: " ".join(row.refusal_reasons) for row in preview.rows}
    assert "broker order" in reasons["p-order"]
    assert "broker order event" in reasons["p-event"]
    assert "execution reservation" in reasons["p-reservation"]


def test_allocation_batch_reference_refuses_dismissal(store):
    _seed(store, "p-batched", status="proposed")
    _seed(store, "p-free", status="proposed")
    store.create_allocation_batch("batch-1", ["p-batched"], 1000.0)

    preview = store.proposal_dismissal_eligibility(["p-batched", "p-free"])
    assert preview.dismissible_ids == ("p-free",)
    batched = next(r for r in preview.rows if r.proposal_id == "p-batched")
    assert any("allocation batch" in r for r in batched.refusal_reasons)


def test_unreadable_allocation_batch_payload_fails_closed(store):
    """A corrupt batch might reference anything: 'unused' can no longer be
    proven, so every candidate refuses rather than guessing."""
    _seed(store, "p-any", status="proposed")
    now = _BASE_TIME.isoformat()
    with store._connect() as connection:
        connection.execute(
            "INSERT INTO allocation_batches(batch_id, created_at, status, "
            "payload_json, updated_at) VALUES ('bad-batch', ?, 'created', "
            "'{not json', ?)",
            (now, now),
        )
    preview = store.proposal_dismissal_eligibility(["p-any"])
    assert preview.dismissible_ids == ()
    assert any("unreadable" in r for r in preview.rows[0].refusal_reasons)


@pytest.mark.parametrize(
    "evidence_key,evidence_value",
    [
        ("approved_at", "2026-08-04T10:00:00+00:00"),
        ("broker_order", {"order_id": "o9"}),
        ("violations", ["limit breach"]),
        ("submitted_at", "2026-08-04T10:00:00+00:00"),
        ("policy_override", True),
        ("error", "submission raised"),
    ],
)
def test_execution_shaped_payload_evidence_refuses(store, evidence_key, evidence_value):
    _seed(
        store,
        "p-evidence",
        status="proposed",
        payload_extra={evidence_key: evidence_value},
    )
    preview = store.proposal_dismissal_eligibility(["p-evidence"])
    assert preview.dismissible_ids == ()
    assert any(
        evidence_key in reason for reason in preview.rows[0].refusal_reasons
    )


# --- hash binding, atomicity, idempotency ----------------------------------


def test_stale_preview_hash_is_refused(store):
    _seed(store, "p-stale", status="proposed")
    preview = store.proposal_dismissal_eligibility(["p-stale"])
    # State changes between preview and confirmation: an approval claims it.
    store.claim_proposal("p-stale", expected_status="proposed")

    with pytest.raises(ValueError, match="all-or-nothing|Stale"):
        store.dismiss_proposals(
            ["p-stale"],
            dismissed_by="local_operator",
            reason="x",
            expected_preview_hash=preview.preview_hash,
        )
    assert store.get_proposal("p-stale")["status"] == "validating"


def test_benign_state_change_with_same_verdicts_still_refuses_old_hash(store):
    """Even a change that keeps every verdict identical (a payload touch
    bumping updated_at) must invalidate the confirmation: the hash binds
    the exact database state the user saw."""
    _seed(store, "p-touch", status="proposed")
    preview = store.proposal_dismissal_eligibility(["p-touch"])
    store.update_proposal_status("p-touch", "proposed")  # same status, new updated_at

    with pytest.raises(ValueError, match="Stale"):
        store.dismiss_proposals(
            ["p-touch"],
            dismissed_by="local_operator",
            reason="x",
            expected_preview_hash=preview.preview_hash,
        )
    assert store.get_proposal("p-touch")["status"] == "proposed"


def test_bulk_dismissal_is_all_or_nothing(store):
    _seed(store, "p-good", status="proposed")
    _seed(store, "p-bad", status="approved")
    preview = store.proposal_dismissal_eligibility(["p-good", "p-bad"])

    with pytest.raises(ValueError, match="all-or-nothing"):
        store.dismiss_proposals(
            ["p-good", "p-bad"],
            dismissed_by="local_operator",
            reason="x",
            expected_preview_hash=preview.preview_hash,
        )
    assert store.get_proposal("p-good")["status"] == "proposed"
    assert store.get_proposal("p-bad")["status"] == "approved"


def test_repeated_dismissal_is_idempotently_reported_not_rewritten(store):
    _seed(store, "p-repeat", status="proposed")
    first = _dismiss(store, ["p-repeat"])
    assert first.dismissed_ids == ("p-repeat",)
    original = store.get_proposal("p-repeat")

    replay = store.dismiss_proposals(
        ["p-repeat"],
        dismissed_by="someone_else",
        reason="different reason",
        expected_preview_hash="irrelevant-on-noop",
    )
    assert replay.dismissed_ids == ()
    assert replay.already_dismissed_ids == ("p-repeat",)
    assert replay.dismissed_at is None
    # The original dismissal metadata survives untouched.
    assert store.get_proposal("p-repeat") == original


def test_empty_reason_or_actor_is_refused(store):
    _seed(store, "p-reason", status="proposed")
    preview = store.proposal_dismissal_eligibility(["p-reason"])
    for kwargs in (
        {"dismissed_by": "local_operator", "reason": "  "},
        {"dismissed_by": "", "reason": "unused"},
    ):
        with pytest.raises(ValueError):
            store.dismiss_proposals(
                ["p-reason"],
                expected_preview_hash=preview.preview_hash,
                **kwargs,
            )
    assert store.get_proposal("p-reason")["status"] == "proposed"


def test_duplicate_or_empty_id_lists_are_refused(store):
    with pytest.raises(ValueError):
        store.proposal_dismissal_eligibility([])
    with pytest.raises(ValueError):
        store.proposal_dismissal_eligibility(["p-x", "p-x"])


# --- no deletion, no broker artifacts, listing behavior --------------------


def test_dismissal_deletes_nothing_and_creates_no_execution_rows(store):
    _seed(store, "p-keep", status="proposed")
    _dismiss(store, ["p-keep"])

    with store._connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM trade_proposals"
        ).fetchone()[0] == 1
        for table in ("broker_orders", "broker_order_events", "execution_reservations"):
            assert connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0] == 0
        row = connection.execute(
            "SELECT idempotency_key FROM trade_proposals WHERE proposal_id='p-keep'"
        ).fetchone()
        assert row["idempotency_key"] == "idem-p-keep"


def test_list_proposals_visibility_flags(store):
    _seed(store, "p-live", status="proposed", offset_minutes=0)
    _seed(store, "p-exp", status="expired", offset_minutes=1)
    _seed(store, "p-dis", status="proposed", offset_minutes=2)
    _dismiss(store, ["p-dis"])

    default_ids = {p["proposal_id"] for p in store.list_proposals()}
    assert default_ids == {"p-live", "p-exp", "p-dis"}  # audit default: everything

    hidden = {
        p["proposal_id"]
        for p in store.list_proposals(include_dismissed=False, include_expired=False)
    }
    assert hidden == {"p-live"}

    only_expired_hidden = {
        p["proposal_id"] for p in store.list_proposals(include_expired=False)
    }
    assert only_expired_hidden == {"p-live", "p-dis"}

    # Explicit exact-status selection wins over visibility flags.
    explicit = store.list_proposals(
        status="dismissed", include_dismissed=False
    )
    assert [p["proposal_id"] for p in explicit] == ["p-dis"]


def test_dismissed_rows_surface_in_the_closed_without_fill_outcome(store):
    _seed(store, "p-outcome", status="proposed")
    _dismiss(store, ["p-outcome"])
    rows = store.list_proposals_for_outcomes(statuses=("dismissed",))
    assert [p["proposal_id"] for p in rows] == ["p-outcome"]


# --- CLI parity (same storage functions; preview-first) ---------------------


def _cli_args(**overrides):
    defaults = dict(
        proposal_ids=["p-cli"],
        reason=None,
        operator="local_operator",
        confirm_preview_hash=None,
        confirm_dismiss=None,
    )
    defaults.update(overrides)
    return type("Args", (), defaults)()


def test_cli_defaults_to_preview_and_mutates_nothing(store, capsys):
    import scripts.run_personal_assistant as cli

    _seed(store, "p-cli", status="proposed")
    cli.command_dismiss_proposals(_cli_args(), store)
    out = capsys.readouterr().out
    assert "[preview only]" in out
    assert "preview_hash" in out
    assert store.get_proposal("p-cli")["status"] == "proposed"


def test_cli_mutation_requires_exact_confirmation_and_hash(store, capsys):
    import scripts.run_personal_assistant as cli

    _seed(store, "p-cli", status="proposed")
    preview = store.proposal_dismissal_eligibility(["p-cli"])

    with pytest.raises(SystemExit, match="not confirmed"):
        cli.command_dismiss_proposals(
            _cli_args(
                reason="unused",
                confirm_preview_hash=preview.preview_hash,
                confirm_dismiss="yes please",
            ),
            store,
        )
    with pytest.raises(SystemExit, match="non-empty --reason"):
        cli.command_dismiss_proposals(
            _cli_args(
                reason="  ",
                confirm_preview_hash=preview.preview_hash,
                confirm_dismiss="unused-paper-proposals",
            ),
            store,
        )
    with pytest.raises(SystemExit, match="refused"):
        cli.command_dismiss_proposals(
            _cli_args(
                reason="unused",
                confirm_preview_hash="0" * 64,
                confirm_dismiss="unused-paper-proposals",
            ),
            store,
        )
    assert store.get_proposal("p-cli")["status"] == "proposed"


def test_cli_happy_path_dismisses_through_the_shared_storage_function(store, capsys):
    import scripts.run_personal_assistant as cli

    _seed(store, "p-cli", status="proposed")
    preview = store.proposal_dismissal_eligibility(["p-cli"])
    cli.command_dismiss_proposals(
        _cli_args(
            reason="unused watchlist experiment",
            confirm_preview_hash=preview.preview_hash,
            confirm_dismiss="unused-paper-proposals",
        ),
        store,
    )
    out = capsys.readouterr().out
    assert '"p-cli"' in out
    assert "remain in the local audit history" in out
    row = store.get_proposal("p-cli")
    assert row["status"] == DISMISSED
    assert row["dismissed_reason"] == "unused watchlist experiment"
