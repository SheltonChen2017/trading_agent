"""Safety invariants of the committed operational-host bootstrap script.

scripts/setup_operational_host.ps1 lets the owner reproduce the model-2
machine setup on another computer. Source-level checks (the script's
effects are machine mutations no test should perform): it must carry the
one-host-per-epoch evidence warning, install with the Credential-Guard-
compatible Interactive logon, route everything through the real
installer/verifier rather than reimplementing them, keep one operator
database path shared by every generated component, and embed no
credential material.

Run with: python -m pytest tests/test_setup_operational_host.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "setup_operational_host.ps1"
).read_text(encoding="utf-8")


def test_carries_the_one_host_per_epoch_evidence_warning():
    assert "EVIDENCE WARNING" in _SCRIPT
    assert "ONE operational host" in _SCRIPT
    assert "paper-epoch-close" in _SCRIPT


def test_generated_installer_uses_interactive_logon_and_real_scripts():
    # Credential Guard blocks S4U task logons on domain-joined Windows 11;
    # the generated wrapper must install AND verify with Interactive.
    assert "-TaskLogonType Interactive" in _SCRIPT
    assert "-ExpectedTaskLogonType Interactive" in _SCRIPT
    assert "-RequireTaskRun" in _SCRIPT
    # Composition, not reimplementation: the wrapper calls the reviewed
    # installer and verifier from the OPERATIONAL checkout.
    assert "install_windows_operational_tasks.ps1" in _SCRIPT
    assert "verify_windows_evidence_tasks.ps1" in _SCRIPT
    assert "-Scope operational" in _SCRIPT
    # Fail-closed: a nonzero verifier exit blocks epoch actions.
    assert "do not proceed to epoch actions" in _SCRIPT


def test_single_operator_database_discipline():
    # Exactly one database parameter feeds the launcher's env var, the
    # installer, and the verifier -- a second literal DB path would let
    # evidence split across files.
    assert "TRADING_ASSISTANT_DB" in _SCRIPT
    assert _SCRIPT.count("$OperatorDatabasePath") >= 4
    assert "paper.db" not in _SCRIPT


def test_embeds_no_credential_material():
    # Names of the required variables may appear in prose; values never.
    assert not re.search(r"APCA_API_KEY_ID\s*=", _SCRIPT)
    assert not re.search(r"APCA_API_SECRET_KEY\s*=", _SCRIPT)
    assert "must\n#     exist as user-scope environment variables" in _SCRIPT
    assert "never stored in the repository" in _SCRIPT


def test_native_failures_and_dirty_checkout_fail_closed():
    # Windows PowerShell 5.1 does not turn native nonzero exit codes into
    # terminating errors merely because ErrorActionPreference is Stop.
    assert "function Assert-NativeSuccess" in _SCRIPT
    assert _SCRIPT.count("Assert-NativeSuccess") >= 7
    assert "status --porcelain" in _SCRIPT
    assert "Operational checkout is dirty" in _SCRIPT


def test_venv_interpreter_not_store_alias_rationale_present():
    # The reason the venv exists at all: scheduled tasks cannot launch the
    # Store's zero-byte execution aliases.
    assert "zero-byte" in _SCRIPT
    assert "Scripts\\python.exe" in _SCRIPT
