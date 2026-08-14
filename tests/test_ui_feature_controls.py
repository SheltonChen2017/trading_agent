"""End-to-end checks for the protected Streamlit policy controls and the
sidebar navigation (UI-2a/UI-2c)."""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from assistant.policy import (
    DEFAULT_POLICY_PATH,
    bump_policy_version,
    compute_policy_fingerprint,
    load_policy,
    save_policy,
)


_ALLOW_NEW_LABEL = (
    "Allow new positions (exposure-increasing buys become policy-eligible)"
)
_CONFIRM_LABEL = 'Type exactly "UPDATE POLICY" to enable the apply button'


def _one(elements, label: str):
    matches = [element for element in elements if element.label == label]
    assert len(matches) == 1, f"expected one widget labelled {label!r}, found {len(matches)}"
    return matches[0]


def _active_policy_row(app: AppTest) -> dict:
    matches = []
    for frame in app.dataframe:
        value = frame.value
        if hasattr(value, "columns") and "Control" in value.columns:
            matches.extend(
                value[value["Control"] == "Active policy"].to_dict("records")
            )
    assert len(matches) == 1
    return matches[0]


def test_allow_new_positions_toggle_persists_and_refreshes_status(tmp_path: Path):
    """The actual button must change both durable policy and the app's
    authoritative status in the same completed interaction."""
    policy_path = tmp_path / "policy.json"
    original = load_policy(DEFAULT_POLICY_PATH)
    assert original.allow_new_positions is False
    save_policy(original, policy_path)

    app_path = Path(__file__).resolve().parents[1] / "scripts" / "personal_assistant_ui.py"
    app = AppTest.from_file(str(app_path), default_timeout=40)
    app.session_state["nav_page"] = "Settings & Features"
    app.run()
    assert not app.exception

    _one(app.text_input, "Policy file").set_value(str(policy_path)).run()
    assert not app.exception
    toggle = _one(app.checkbox, _ALLOW_NEW_LABEL)
    assert toggle.value is False

    toggle.set_value(True).run()
    assert load_policy(policy_path).allow_new_positions is False
    assert _one(app.button, "Apply policy change").disabled is True

    _one(app.text_input, _CONFIRM_LABEL).set_value("UPDATE POLICY").run()
    assert _one(app.button, "Apply policy change").disabled is False
    _one(app.button, "Apply policy change").click().run()
    assert not app.exception

    updated = load_policy(policy_path)
    assert updated.allow_new_positions is True
    assert updated.version == bump_policy_version(original.version)
    assert compute_policy_fingerprint(updated) != compute_policy_fingerprint(original)
    assert _one(app.checkbox, _ALLOW_NEW_LABEL).value is True

    active = _active_policy_row(app)
    assert updated.version in active["State"]
    assert compute_policy_fingerprint(updated)[:16] in active["Detail"]

    # The owner explicitly wants to be able to close the gate again. Exercise
    # the reverse transition through the same protected UI workflow rather
    # than assuming a symmetric boolean helper proves the widget behavior.
    _one(app.checkbox, _ALLOW_NEW_LABEL).set_value(False).run()
    assert load_policy(policy_path).allow_new_positions is True
    _one(app.text_input, _CONFIRM_LABEL).set_value("UPDATE POLICY").run()
    _one(app.button, "Apply policy change").click().run()
    assert not app.exception

    closed = load_policy(policy_path)
    assert closed.allow_new_positions is False
    assert closed.version == bump_policy_version(updated.version)
    assert _one(app.checkbox, _ALLOW_NEW_LABEL).value is False
    active = _active_policy_row(app)
    assert closed.version in active["State"]
    assert compute_policy_fingerprint(closed)[:16] in active["Detail"]


_APP_PATH = Path(__file__).resolve().parents[1] / "scripts" / "personal_assistant_ui.py"

# Each page paired with a button label its body always renders, so the test
# proves the page actually produced its content — not merely that selecting
# it raised no exception.
_ALL_PAGES = (
    ("Briefing", "Refresh briefing"),
    ("Budgeted Buying", "Check cart"),
    ("Policy Based Selling", "Check for recommended sells"),
    ("Propose & Approve", "Check for proposals"),
    ("History", "Activate kill switch and cancel all open orders"),
    ("Ticker Suggestions", "Run suggestions"),
    ("Backtest", "Run backtest"),
    ("Reports", "Build report"),
    ("Operations", "Deliver pending critical alerts"),
    # The Apply button only exists once an edit is pending, so Settings
    # uses its always-rendered master AI toggle as the marker instead.
    ("Settings & Features", "Enable optional AI features (master)"),
)


@pytest.mark.parametrize("page,marker_label", _ALL_PAGES)
def test_every_page_is_reachable_through_the_sidebar(page, marker_label):
    """UIPLAN-001: routing means each page body now executes in isolation.
    Every surface must render on its own — a cross-page variable dependency
    that tabs used to mask would surface here as an exception, and a page
    that silently rendered nothing would miss its marker widget."""
    app = AppTest.from_file(str(_APP_PATH), default_timeout=60)
    app.session_state["nav_page"] = page
    app.run()
    assert not app.exception
    assert not app.exception, f"page {page!r} failed to render in isolation"
    labels = [widget.label for widget in list(app.button) + list(app.checkbox)]
    assert marker_label in labels, (
        f"page {page!r} rendered without its marker widget; found: {labels}"
    )


def test_ai_preferences_survive_navigating_away_from_settings():
    """The AI preference keys are read by other pages. Streamlit deletes
    widget-backed keys on reruns that don't render them, so the prefs live
    in durable session keys synced from the widgets — navigating away from
    Settings must not silently reset an enabled preference."""
    app = AppTest.from_file(str(_APP_PATH), default_timeout=60)
    app.session_state["nav_page"] = "Settings & Features"
    app.run()
    assert not app.exception

    _one(app.checkbox, "Enable optional AI features (master)").set_value(True).run()
    assert app.session_state["ai_pref_master"] is True

    app.radio(key="nav_page").set_value("History").run()
    assert not app.exception
    # Two reruns without the Settings widgets: the durable key must survive
    # the widget-state cleanup both times.
    app.radio(key="nav_page").set_value("Briefing").run()
    assert app.session_state["ai_pref_master"] is True

    app.radio(key="nav_page").set_value("Settings & Features").run()
    assert _one(app.checkbox, "Enable optional AI features (master)").value is True


def test_buying_cart_survives_navigating_to_another_page():
    """A navigation control must not erase the in-progress Buying cart."""
    app = AppTest.from_file(str(_APP_PATH), default_timeout=40)
    app.session_state["nav_page"] = "Budgeted Buying"
    app.run()
    assert not app.exception

    cart = _one(app.multiselect, "Pick from common tickers")
    cart.set_value(["AAPL"]).run()
    assert _one(app.multiselect, "Pick from common tickers").value == ["AAPL"]

    app.radio(key="nav_page").set_value("History").run()
    assert not app.exception
    app.radio(key="nav_page").set_value("Budgeted Buying").run()
    assert not app.exception
    assert _one(app.multiselect, "Pick from common tickers").value == ["AAPL"]
