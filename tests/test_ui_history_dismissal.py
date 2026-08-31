"""UI-2d: History archive visibility and the dismiss workflow, end to end
through the real Streamlit app against the session-isolated database.

Run with: python -m pytest tests/test_ui_history_dismissal.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.proposal_status import DISMISSED
from assistant.storage import AssistantStore

_APP_PATH = Path(__file__).resolve().parents[1] / "scripts" / "personal_assistant_ui.py"
_BASE_TIME = datetime(2026, 8, 4, 17, 0, 0, tzinfo=timezone.utc)

_SEED_IDS = ("ui2d-live", "ui2d-expired", "ui2d-dismissed", "ui2d-second")


def _seed_proposal(store, proposal_id, status, offset_minutes=0):
    created = _BASE_TIME + timedelta(minutes=offset_minutes)
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


@pytest.fixture()
def seeded(request):
    store = AssistantStore(Path(os.environ["TRADING_ASSISTANT_DB"]))
    _seed_proposal(store, "ui2d-live", "proposed", 0)
    _seed_proposal(store, "ui2d-expired", "expired", 1)
    _seed_proposal(store, "ui2d-dismissed", "proposed", 2)
    _seed_proposal(store, "ui2d-second", "proposed", 3)
    preview = store.proposal_dismissal_eligibility(["ui2d-dismissed"])
    store.dismiss_proposals(
        ["ui2d-dismissed"],
        dismissed_by="test",
        reason="seeded archive row",
        expected_preview_hash=preview.preview_hash,
    )
    try:
        yield store
    finally:
        # Shared session DB: an approvable leftover would leak an approval
        # card into unrelated Propose & Approve tests.
        with store._connect_writable() as connection:
            connection.execute(
                "DELETE FROM trade_proposals WHERE proposal_id IN "
                f"({','.join('?' for _ in _SEED_IDS)})",
                _SEED_IDS,
            )


def _history_app() -> AppTest:
    app = AppTest.from_file(str(_APP_PATH), default_timeout=120)
    app.session_state["nav_page"] = "History"
    app.run()
    assert not app.exception
    return app


def _visible_seed_ids(app: AppTest) -> set[str]:
    ids: set[str] = set()
    for frame in app.dataframe:
        value = frame.value
        if hasattr(value, "columns") and "Proposal ID" in value.columns:
            ids.update(
                pid
                for pid in value["Proposal ID"].tolist()
                if str(pid).startswith("ui2d-")
            )
    return ids


def test_default_view_hides_expired_and_dismissed(seeded):
    app = _history_app()
    assert _visible_seed_ids(app) == {"ui2d-live", "ui2d-second"}
    captions = " ".join(str(c.value) for c in app.caption)
    assert "Hiding expired and dismissed proposals" in captions


def test_visibility_toggles_reveal_each_archive_class(seeded):
    app = _history_app()
    app.checkbox(key="history_include_expired").set_value(True).run()
    assert not app.exception
    assert _visible_seed_ids(app) == {"ui2d-live", "ui2d-second", "ui2d-expired"}

    app.checkbox(key="history_include_dismissed").set_value(True).run()
    assert not app.exception
    assert _visible_seed_ids(app) == set(_SEED_IDS)


def test_exact_status_selection_overrides_hidden_visibility(seeded):
    """Spec 10.3: selecting the exact status cannot be contradicted by a
    hidden visibility filter."""
    app = _history_app()
    app.selectbox(key="proposal_status_filter").set_value("dismissed").run()
    assert not app.exception
    assert _visible_seed_ids(app) == {"ui2d-dismissed"}
    captions = " ".join(str(c.value) for c in app.caption)
    assert "even while their include-checkbox is off" in captions


def test_outcome_group_selection_shows_archive_rows(seeded):
    app = _history_app()
    app.multiselect(key="proposal_outcome_filter").set_value(
        ["Closed without fill"]
    ).run()
    assert not app.exception
    assert _visible_seed_ids(app) == {"ui2d-expired", "ui2d-dismissed"}


def test_dismiss_button_is_disabled_until_reason_and_exact_phrase(seeded):
    app = _history_app()
    app.multiselect(key="dismiss_selection").set_value(
        ["ui2d-live", "ui2d-second"]
    ).run()
    assert app.button(key="dismiss_button").disabled is True

    app.text_input(key="dismiss_reason").set_value("unused experiments").run()
    assert app.button(key="dismiss_button").disabled is True

    app.text_input(key="dismiss_confirmation").set_value(
        "dismiss 1 proposals"  # wrong count
    ).run()
    assert app.button(key="dismiss_button").disabled is True

    app.text_input(key="dismiss_confirmation").set_value(
        "dismiss 2 proposals"
    ).run()
    assert app.button(key="dismiss_button").disabled is False
    # Nothing was mutated by merely enabling the button.
    assert seeded.get_proposal("ui2d-live")["status"] == "proposed"


def test_dismissal_flow_end_to_end(seeded):
    app = _history_app()
    # A stale approval confirmation for one of the IDs must die with the
    # dismissal (spec 7.3 / 10.2: stale UI state cannot approve).
    app.session_state["confirm_ui2d-live"] = "approve"

    app.multiselect(key="dismiss_selection").set_value(
        ["ui2d-live", "ui2d-second"]
    ).run()
    app.text_input(key="dismiss_reason").set_value("unused experiments").run()
    app.text_input(key="dismiss_confirmation").set_value(
        "dismiss 2 proposals"
    ).run()
    app.button(key="dismiss_button").click().run()
    assert not app.exception

    for pid in ("ui2d-live", "ui2d-second"):
        row = seeded.get_proposal(pid)
        assert row["status"] == DISMISSED
        assert row["dismissed_reason"] == "unused experiments"
        assert row["dismissed_from_status"] == "proposed"

    successes = " ".join(str(s.value) for s in app.success)
    assert "Dismissed 2 proposal(s)" in successes
    assert "remain in the local audit history" in successes
    assert "confirm_ui2d-live" not in app.session_state
    # The default view no longer shows them.
    assert _visible_seed_ids(app) == set()
