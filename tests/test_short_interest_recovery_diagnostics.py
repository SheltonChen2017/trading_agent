"""Fabricated, network-denied fixed local failure projections; no capture."""
from __future__ import annotations

import errno
import json
import socket
import subprocess

import pytest

from research.short_interest_etf.native_reported_anchor_cache import AnchorCacheRefusal

# The runtime under test imports POSIX-only stdlib modules at import time, so
# this module cannot even be collected on the supported Windows host; see the
# lane record SI-CR18-001. Portable contract logic stays covered on POSIX.
pytest.importorskip(
    "resource",
    reason=(
        "the protected-capture runtime imports the POSIX-only module "
        "resource at import time; it cannot execute on this host, see the "
        "lane record SI-CR18-001"
    ),
)

from scripts.capture_short_interest_count_recovery import RecoveryRefusal
from scripts.qualify_finra_short_interest import CapturePlatformRefusal, CaptureRefusal
from scripts.qualify_sharadar_companion import SharadarCaptureRefusal
from scripts.short_interest_keychain import ShortInterestKeychainError
from scripts.short_interest_lane_batch_guard import LaneBatchRefusal
from scripts.short_interest_refused_count_snapshot import RefusedSnapshotError
from scripts import short_interest_recovery_diagnostics as diagnostics


SECRET = "fabricated-never-publish-url-token"


class HostileFormatting:
    def __str__(self):
        raise AssertionError("external str forbidden")

    def __repr__(self):
        raise AssertionError("external repr forbidden")


@pytest.fixture(autouse=True)
def deny_network_and_processes(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("diagnostics cannot perform I/O")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(subprocess, "run", denied)


def project(error):
    result = diagnostics.fixed_local_failure(error)
    assert type(result) is dict and set(result) == {"category", "errno_name", "contract_code"}
    assert SECRET not in json.dumps(result)
    return result


@pytest.mark.parametrize("error_type,code,category", [
    (diagnostics.RecoveryLocalRefusal, "new_claim_original_bytes_changed", "local_contract_refusal"),
    (RecoveryRefusal, "insufficient_preclaim_descriptor_headroom", "local_contract_refusal"),
    (RefusedSnapshotError, "snapshot_spent_claim_changed", "local_contract_refusal"),
    (AnchorCacheRefusal, "held_custody_file_changed", "local_contract_refusal"),
    (LaneBatchRefusal, "matching_actual_remote_advanced_or_ambiguous", "lane_guard_refusal"),
    (CaptureRefusal, "dirty_worktree", "local_contract_refusal"),
    (SharadarCaptureRefusal, "credential_echo", "local_contract_refusal"),
    (ShortInterestKeychainError, "owner_keychain_item_unavailable", "keychain_refusal"),
])
def test_exact_controlled_types_project_only_fixed_catalogue_code(error_type, code, category):
    for prefix in ("", "REFUSED: "):
        result = project(error_type(prefix + code))
        assert result == {"category": category, "errno_name": None, "contract_code": code}


def test_platform_refusal_is_fixed_without_reading_attributes():
    assert project(CapturePlatformRefusal()) == {
        "category": "platform_refusal", "errno_name": None,
        "contract_code": "protected_capture_platform_unavailable"}


def test_every_new_local_catalogue_code_is_safely_projected():
    assert diagnostics.LOCAL_CONTRACT_CODES
    for code in diagnostics.LOCAL_CONTRACT_CODES:
        assert type(code) is str and SECRET not in code
        assert project(diagnostics.RecoveryLocalRefusal("REFUSED: " + code))["contract_code"] == code


@pytest.mark.parametrize("value", [SECRET, "REFUSED: " + SECRET, "\nheld_custody_file_changed", "REFUSED:  held_custody_file_changed",
                                  "held_custody_file_changed\n", None, 1, b"held_custody_file_changed"])
def test_controlled_type_cannot_publish_unknown_or_nonexact_contract_argument(value):
    result = project(diagnostics.RecoveryLocalRefusal(value))
    assert result == {"category": "local_contract_refusal", "errno_name": None, "contract_code": None}


def test_multiple_args_or_untrusted_string_subclass_never_project():
    class HostileString(str):
        def __hash__(self):
            raise AssertionError("untrusted string hash forbidden")
        def __eq__(self, other):
            raise AssertionError("untrusted string equality forbidden")
    assert project(diagnostics.RecoveryLocalRefusal("held_custody_file_changed", SECRET))["contract_code"] is None
    assert project(diagnostics.RecoveryLocalRefusal(HostileString("held_custody_file_changed")))["contract_code"] is None


def test_plain_value_error_cannot_impersonate_a_controlled_refusal():
    for value in (SECRET, "held_custody_file_changed", "REFUSED: new_claim_original_bytes_changed"):
        assert project(ValueError(value)) == {"category": "unknown_local_error", "errno_name": None, "contract_code": None}


def test_controlled_subclasses_are_not_trusted_for_contract_codes():
    class Impersonator(HostileFormatting, diagnostics.RecoveryLocalRefusal):
        pass
    assert project(Impersonator("REFUSED: new_claim_original_bytes_changed")) == {
        "category": "unknown_local_error", "errno_name": None, "contract_code": None}


@pytest.mark.parametrize("base,category", [(TypeError, "local_type_error"), (NameError, "local_name_error"),
    (UnboundLocalError, "local_name_error"), (MemoryError, "local_memory_error"), (TimeoutError, "local_timeout")])
def test_standard_local_errors_are_fixed_and_never_read_formatted_text(base, category):
    class Hostile(HostileFormatting, base):
        pass
    assert project(Hostile(SECRET)) == {"category": category, "errno_name": None, "contract_code": None}


@pytest.mark.parametrize("name", ["EACCES", "EPERM", "EMFILE", "ENFILE", "ENOSPC", "ENOMEM", "ENOENT", "EIO", "ETIMEDOUT"])
def test_os_errno_names_are_allowlisted_from_builtin_numeric_slot(name):
    class HostileOS(HostileFormatting, OSError):
        @property
        def errno(self):
            raise AssertionError("untrusted errno property forbidden")
    assert project(HostileOS(getattr(errno, name), SECRET)) == {
        "category": "local_os_error", "errno_name": name, "contract_code": None}


@pytest.mark.parametrize("number", [918273, SECRET, None, True])
def test_unknown_errno_or_noninteger_slot_is_never_echoed(number):
    assert project(OSError(number, SECRET))["errno_name"] is None


def test_unknown_error_properties_and_dynamic_type_name_are_never_inspected():
    class HostileMeta(type):
        def __getattribute__(self, name):
            if name in {"__name__", "__qualname__", "__mro__"}:
                raise AssertionError("dynamic type metadata forbidden")
            return super().__getattribute__(name)
    class Unknown(HostileFormatting, Exception, metaclass=HostileMeta):
        @property
        def __class__(self):
            raise AssertionError("untrusted class property forbidden")
        @property
        def code(self):
            raise AssertionError("untrusted code property forbidden")
        @property
        def args(self):
            raise AssertionError("untrusted args property forbidden")
        @property
        def errno(self):
            raise AssertionError("untrusted errno property forbidden")
    assert project(Unknown(SECRET)) == {"category": "unknown_local_error", "errno_name": None, "contract_code": None}


def test_exact_controlled_error_uses_base_exception_slot_not_overridden_property(monkeypatch):
    def forbidden(*unused):
        raise AssertionError("controlled exception property/formatting forbidden")
    error = diagnostics.RecoveryLocalRefusal("REFUSED: new_claim_original_bytes_changed")
    monkeypatch.setattr(diagnostics.RecoveryLocalRefusal, "args", property(forbidden), raising=False)
    monkeypatch.setattr(diagnostics.RecoveryLocalRefusal, "code", property(forbidden), raising=False)
    monkeypatch.setattr(diagnostics.RecoveryLocalRefusal, "__str__", forbidden)
    monkeypatch.setattr(diagnostics.RecoveryLocalRefusal, "__repr__", forbidden)
    assert project(error)["contract_code"] == "new_claim_original_bytes_changed"


def test_projection_is_fresh_and_cannot_mutate_later_results():
    error = diagnostics.RecoveryLocalRefusal("REFUSED: new_claim_original_bytes_changed")
    first = project(error)
    first["category"] = SECRET
    assert project(error)["category"] == "local_contract_refusal"
