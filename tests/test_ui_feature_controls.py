"""End-to-end checks for the protected Streamlit policy controls."""
from __future__ import annotations

from pathlib import Path

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
    app = AppTest.from_file(str(app_path), default_timeout=40).run()
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
