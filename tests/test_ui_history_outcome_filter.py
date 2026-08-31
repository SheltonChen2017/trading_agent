"""UI-2b: History outcome filtering behavior through the real Streamlit app.

Uses AppTest against the session-isolated database (tests/conftest.py pins
TRADING_ASSISTANT_DB away from the operator DB) with seeded proposals, and
asserts on the seeded IDs rather than exact row counts so other tests'
session rows cannot break these.

Run with: python -m pytest tests/test_ui_history_outcome_filter.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.storage import AssistantStore

_APP_PATH = Path(__file__).resolve().parents[1] / "scripts" / "personal_assistant_ui.py"
_BASE_TIME = datetime(2026, 8, 4, 15, 0, 0, tzinfo=timezone.utc)

# One proposal per interesting outcome, plus one whose status this app
# version has never heard of.
_SEEDS = (
    ("ui2b-proposed", "proposed"),
    ("ui2b-filled", "filled"),
    ("ui2b-blocked", "blocked"),
    ("ui2b-future", "status_from_a_future_release"),
)


@pytest.fixture()
def seeded_history():
    store = AssistantStore(Path(os.environ["TRADING_ASSISTANT_DB"]))
    for index, (proposal_id, status) in enumerate(_SEEDS):
        created = _BASE_TIME + timedelta(minutes=index)
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
    try:
        yield store
    finally:
        # The session database is shared by every UI test in this process:
        # leaking an approvable "proposed" row would surface an approval
        # card inside unrelated Propose & Approve tests.
        with store._connect_writable() as connection:
            connection.execute(
                "DELETE FROM trade_proposals WHERE proposal_id IN "
                f"({','.join('?' for _ in _SEEDS)})",
                tuple(proposal_id for proposal_id, _ in _SEEDS),
            )


def _history_app() -> AppTest:
    app = AppTest.from_file(str(_APP_PATH), default_timeout=120)
    app.session_state["nav_page"] = "History"
    app.run()
    assert not app.exception
    return app


def _proposal_rows(app: AppTest) -> list[dict]:
    rows: list[dict] = []
    for frame in app.dataframe:
        value = frame.value
        if hasattr(value, "columns") and "Proposal ID" in value.columns:
            rows.extend(value.to_dict("records"))
    return rows


def _seeded_ids(rows: list[dict]) -> set[str]:
    return {
        row["Proposal ID"]
        for row in rows
        if str(row["Proposal ID"]).startswith("ui2b-")
    }


def test_outcome_filter_narrows_to_the_selected_groups(seeded_history):
    app = _history_app()
    assert _seeded_ids(_proposal_rows(app)) == {
        proposal_id for proposal_id, _ in _SEEDS
    }

    app.multiselect(key="proposal_outcome_filter").set_value(["Filled"]).run()
    assert not app.exception
    assert _seeded_ids(_proposal_rows(app)) == {"ui2b-filled"}

    app.multiselect(key="proposal_outcome_filter").set_value(
        ["Filled", "Refused / failed"]
    ).run()
    assert not app.exception
    assert _seeded_ids(_proposal_rows(app)) == {"ui2b-filled", "ui2b-blocked"}


def test_unknown_status_shows_as_other_unknown_never_as_completed(seeded_history):
    """The fail-safe direction: a status from a future release must appear
    only under Other / unknown, and its Outcome cell must say so."""
    app = _history_app()

    app.multiselect(key="proposal_outcome_filter").set_value(
        ["Other / unknown"]
    ).run()
    assert not app.exception
    rows = _proposal_rows(app)
    assert _seeded_ids(rows) == {"ui2b-future"}
    future_rows = [r for r in rows if r["Proposal ID"] == "ui2b-future"]
    assert future_rows[0]["Outcome"] == "Other / unknown"

    # And the completed-looking groups must NOT include it.
    app.multiselect(key="proposal_outcome_filter").set_value(
        ["Filled", "Closed without fill"]
    ).run()
    assert not app.exception
    assert "ui2b-future" not in _seeded_ids(_proposal_rows(app))


def test_both_filters_combine_by_intersection_and_are_stated(seeded_history):
    """Outcome = Filled with exact status = proposed contradict each other:
    the result must be empty, and the UI must say which filters are active
    and that they intersect -- not show a bare inexplicable empty view."""
    app = _history_app()
    app.multiselect(key="proposal_outcome_filter").set_value(["Filled"]).run()
    app.selectbox(key="proposal_status_filter").set_value("proposed").run()
    assert not app.exception

    assert _seeded_ids(_proposal_rows(app)) == set()
    captions = " ".join(str(c.value) for c in app.caption)
    assert "Active filters" in captions
    assert "Filled" in captions
    assert "proposed" in captions
    assert "intersection" in captions
    infos = " ".join(str(i.value) for i in app.info)
    assert "No proposals match the active filters." in infos

    # A consistent pair -- outcome group containing the exact status --
    # passes rows through.
    app.multiselect(key="proposal_outcome_filter").set_value(
        ["Awaiting decision"]
    ).run()
    assert not app.exception
    assert _seeded_ids(_proposal_rows(app)) == {"ui2b-proposed"}


def test_exact_status_filter_still_works_alone(seeded_history):
    app = _history_app()
    app.selectbox(key="proposal_status_filter").set_value("blocked").run()
    assert not app.exception
    assert _seeded_ids(_proposal_rows(app)) == {"ui2b-blocked"}


def test_outcome_filter_applies_before_the_history_row_limit(seeded_history):
    """The UI must query newest-N OF the selected outcome, not filter a
    limited unfiltered page. Newer non-matching rows must not hide an older
    matching proposal."""
    extra_ids = []
    for index in range(6):
        proposal_id = f"ui2b-newer-nonmatch-{index}"
        extra_ids.append(proposal_id)
        created = _BASE_TIME + timedelta(hours=1, minutes=index)
        seeded_history.save_proposal(
            {
                "proposal_id": proposal_id,
                "created_at": created.isoformat(),
                "expires_at": (created + timedelta(hours=4)).isoformat(),
                "status": "proposed",
                "idempotency_key": f"idem-{proposal_id}",
                "intent": {"ticker": "AAPL", "side": "buy", "shares": 1},
            }
        )
    try:
        app = _history_app()
        app.slider(key="proposal_history_limit").set_value(5).run()
        app.multiselect(key="proposal_outcome_filter").set_value(["Filled"]).run()
        assert not app.exception
        assert "ui2b-filled" in _seeded_ids(_proposal_rows(app))
    finally:
        with seeded_history._connect_writable() as connection:
            connection.execute(
                "DELETE FROM trade_proposals WHERE proposal_id IN "
                f"({','.join('?' for _ in extra_ids)})",
                tuple(extra_ids),
            )


def test_outcome_filter_survives_navigating_away_and_back(seeded_history):
    """History filters are whitelisted benign page state (UINAV-001): the
    outcome selection must survive a round trip through another page."""
    app = _history_app()
    app.multiselect(key="proposal_outcome_filter").set_value(["Filled"]).run()
    assert _seeded_ids(_proposal_rows(app)) == {"ui2b-filled"}

    app.radio(key="nav_page").set_value("Budgeted Buying").run()
    assert not app.exception
    app.radio(key="nav_page").set_value("History").run()
    assert not app.exception
    assert app.multiselect(key="proposal_outcome_filter").value == ["Filled"]
    assert _seeded_ids(_proposal_rows(app)) == {"ui2b-filled"}
