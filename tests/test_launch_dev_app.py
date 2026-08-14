"""Safety contract for the development Streamlit launcher.

The launcher itself is PowerShell and intentionally starts a long-running
process, so these are source-level composition tests. The Python kill-switch
semantics it delegates to are exercised separately in
``tests/test_kill_switch_env.py``.
"""
from __future__ import annotations

import re
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = (_ROOT / "scripts" / "launch_dev_app.ps1").read_text(encoding="utf-8")
_HOW_TO_USE = (_ROOT / "HOW_TO_USE.md").read_text(encoding="utf-8")
_README = (_ROOT / "README.md").read_text(encoding="utf-8")
_UI_SOURCE = (_ROOT / "scripts" / "personal_assistant_ui.py").read_text(
    encoding="utf-8"
)


def test_development_launcher_uses_a_distinct_disposable_database():
    assert '"data\\dev_scratch.db"' in _SCRIPT
    assert '"data\\trading_assistant.db"' in _SCRIPT
    assert "$developmentDatabase -eq $operatorDatabase" in _SCRIPT
    assert "$env:TRADING_ASSISTANT_DB = $developmentDatabase" in _SCRIPT


def test_development_launcher_blocks_submission_by_default():
    """Database isolation alone cannot protect the shared paper account."""
    assert "[switch]$AllowPaperOrders" in _SCRIPT
    assert "if (-not $AllowPaperOrders)" in _SCRIPT
    assert '$env:TRADING_ASSISTANT_KILL_SWITCH = "1"' in _SCRIPT


def test_explicit_order_opt_in_does_not_clear_an_existing_kill_switch():
    """The escape hatch may omit the added halt; it must never force safety off."""
    assert 'TRADING_ASSISTANT_KILL_SWITCH = "0"' not in _SCRIPT
    assert 'TRADING_ASSISTANT_KILL_SWITCH = "false"' not in _SCRIPT
    assert 'TRADING_ASSISTANT_KILL_SWITCH = "off"' not in _SCRIPT
    assert "Existing environment/persistent kill switches still apply" in _SCRIPT


def test_development_launcher_lifts_every_supported_provider_key():
    match = re.search(
        r"\$UserScopeCredentialNames\s*=\s*@\((.*?)\)\s*foreach",
        _SCRIPT,
        re.DOTALL,
    )
    assert match
    assert set(re.findall(r'"([A-Z0-9_]+)"', match.group(1))) == {
        "APCA_API_KEY_ID",
        "APCA_API_SECRET_KEY",
        "ANTHROPIC_API_KEY",
        "FINNHUB_API_KEY",
        "DATABENTO_API_KEY",
    }
    assert "foreach ($credentialName in $UserScopeCredentialNames)" in _SCRIPT


def test_manual_launch_instructions_preserve_both_isolation_boundaries():
    manual = _HOW_TO_USE.split("If you prefer to run it by hand", 1)[1].split(
        "Two habits", 1
    )[0]
    assert "TRADING_ASSISTANT_DB" in manual
    assert "TRADING_ASSISTANT_KILL_SWITCH" in manual


def test_primary_docs_do_not_bypass_the_safe_development_launcher():
    assert "scripts/launch_dev_app.ps1" in _README
    assert "python -m streamlit run scripts/personal_assistant_ui.py" not in _README
    assert "scripts/launch_dev_app.ps1" in _UI_SOURCE.split('"""', 2)[1]
    assert "streamlit run scripts/personal_assistant_ui.py" not in _UI_SOURCE.split(
        '"""', 2
    )[1]
