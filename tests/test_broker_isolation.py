"""The suite must never reach a live brokerage account.

Companion to test_test_isolation.py, which covers the operator database.
This covers the network half of the same defect: importing the Streamlit
app during collection ran build_decision_packet() with
use_live_alpaca=is_configured(), so on a machine with real credentials a
full-suite run issued a live Alpaca request before a single test executed
-- and an error from the broker aborted collection entirely.
"""
from __future__ import annotations

import os

from execution.alpaca_broker import is_configured


def test_broker_credentials_are_not_visible_to_the_suite():
    for name in ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY"):
        value = os.environ.get(name)
        # tests/test_alpaca_broker.py installs its own obvious fakes and does
        # not restore them, so a "test-" value is expected; a real credential
        # is not. Real Alpaca keys are long and start with PK/AK.
        if value:
            assert value.startswith("test-"), (
                f"{name} holds a non-test value during the suite; a live "
                "broker call could escape from any import-time code path"
            )


def test_importing_the_ui_does_not_require_a_broker():
    """The import that triggered the original collection abort."""
    import scripts.personal_assistant_ui as ui

    assert ui is not None
    assert is_configured() is False, (
        "the suite believes a broker is configured; module-scope code in the "
        "UI would then issue live requests during collection"
    )
