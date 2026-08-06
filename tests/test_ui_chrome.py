"""App chrome: title, typography block, and the resolved policy default.

The rename and the type styling are presentation, but two properties here
are not cosmetic and are the reason this file exists:

  * the sidebar's policy default must come from `resolve_policy_path()`,
    because that is what decides which policy governs proposals; and
  * whichever file wins must be NAMED on screen, so a more permissive
    personal policy can never be in force without the owner seeing it.
"""
from __future__ import annotations

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from assistant.policy import DEFAULT_POLICY_PATH, POLICY_PATH_ENV_VAR, resolve_policy_path

_APP_PATH = Path(__file__).resolve().parents[1] / "scripts" / "personal_assistant_ui.py"


def _one(elements, label: str):
    matches = [element for element in elements if element.label == label]
    assert len(matches) == 1, f"expected one widget labelled {label!r}, found {len(matches)}"
    return matches[0]


def test_app_title_is_trading_assistant():
    app = AppTest.from_file(str(_APP_PATH), default_timeout=60)
    app.session_state["nav_page"] = "Briefing"
    app.run()
    assert not app.exception

    titles = [element.value for element in app.title]
    assert "Trading Assistant" in titles
    assert "Personal Trading Assistant" not in titles


def test_no_surface_still_says_personal_trading_assistant():
    """The rename has to reach every rendered surface, not just st.title —
    a stale heading elsewhere would read as a different app."""
    app = AppTest.from_file(str(_APP_PATH), default_timeout=60)
    app.session_state["nav_page"] = "Briefing"
    app.run()
    assert not app.exception

    rendered = " ".join(
        str(getattr(element, "value", "")) for element in list(app.markdown) + list(app.title)
    )
    assert "Personal Trading Assistant" not in rendered


def test_typography_block_is_injected_without_a_remote_font_request():
    """A webfont import would make the operational host's rendering depend
    on network reachability; the stack must stay entirely system-local."""
    app = AppTest.from_file(str(_APP_PATH), default_timeout=60)
    app.session_state["nav_page"] = "Briefing"
    app.run()
    assert not app.exception

    styles = [
        str(element.value) for element in app.markdown if "<style>" in str(element.value)
    ]
    assert styles, "expected an injected <style> block"
    css = "\n".join(styles)
    assert "font-family" in css
    assert "tabular-nums" in css
    for remote in ("@import", "https://", "http://", "fonts.googleapis", "cdn"):
        assert remote not in css, f"typography block reaches out to {remote!r}"


def test_sidebar_policy_field_defaults_to_the_resolved_policy(tmp_path, monkeypatch):
    """Wiring test: the field must be seeded by resolve_policy_path(), not
    by the hard-coded committed default. Driven through the environment
    variable so the assertion holds on a fresh clone too, where the owner's
    my_policy.json does not exist."""
    payload = json.loads(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
    payload["name"] = "resolver-probe"
    chosen = tmp_path / "probe_policy.json"
    chosen.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    monkeypatch.setenv(POLICY_PATH_ENV_VAR, str(chosen))
    assert resolve_policy_path() == chosen

    app = AppTest.from_file(str(_APP_PATH), default_timeout=60)
    app.session_state["nav_page"] = "Briefing"
    app.run()
    assert not app.exception

    assert _one(app.text_input, "Policy file").value == str(chosen)


def test_the_governing_policy_file_is_named_on_screen(tmp_path, monkeypatch):
    """The failure direction. A default that silently selects a more
    permissive policy is a hidden financial default; the resolved file has
    to be visible without opening Settings."""
    payload = json.loads(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
    chosen = tmp_path / "distinctive_policy_name.json"
    chosen.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    monkeypatch.setenv(POLICY_PATH_ENV_VAR, str(chosen))

    app = AppTest.from_file(str(_APP_PATH), default_timeout=60)
    app.session_state["nav_page"] = "Briefing"
    app.run()
    assert not app.exception

    captions = " ".join(str(element.value) for element in app.caption)
    assert "distinctive_policy_name.json" in captions


def test_a_broken_policy_env_var_degrades_visibly_instead_of_crashing(
    tmp_path, monkeypatch
):
    """A stray environment variable must not make the app unloadable, and
    the fallback must continue the implicit chain rather than skipping an
    existing personal policy."""
    import assistant.policy as policy_module

    personal = tmp_path / "my_policy.json"
    payload = json.loads(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
    payload["name"] = "personal-fallback"
    personal.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    monkeypatch.setattr(policy_module, "PERSONAL_POLICY_PATH", personal)
    monkeypatch.setenv(POLICY_PATH_ENV_VAR, str(tmp_path / "does_not_exist.json"))

    app = AppTest.from_file(str(_APP_PATH), default_timeout=60)
    app.session_state["nav_page"] = "Briefing"
    app.run()
    assert not app.exception

    assert _one(app.text_input, "Policy file").value == str(personal)
    warnings = " ".join(str(element.value) for element in app.warning)
    assert "does_not_exist.json" in warnings
    assert "my_policy.json" in warnings
