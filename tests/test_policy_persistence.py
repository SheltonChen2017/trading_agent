"""Policy persistence helpers behind the UI's protected policy-update workflow.

docs/reference/UI_FEATURE_CONTROLS_DESIGN.md section 3.1: allow_new_positions
and enable_strategy_proposals are AUTHORITATIVE policy, so a UI edit must go
through validation, produce a new version and fingerprint, persist atomically,
and leave the file untouched when anything is invalid. These tests exercise
both the success path and each dangerous failure direction.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from assistant.policy import (
    TradingPolicy,
    bump_policy_version,
    compute_policy_fingerprint,
    load_policy,
    policy_with_updated_flags,
    save_policy,
)


def _policy(**overrides) -> TradingPolicy:
    base = dict(version="1.1.0", name="test-policy", execution_mode="paper")
    base.update(overrides)
    return TradingPolicy(**base)


# --------------------------------------------------------------------------
# bump_policy_version
# --------------------------------------------------------------------------


def test_bump_increments_the_last_numeric_segment():
    assert bump_policy_version("1.1.0") == "1.1.1"
    assert bump_policy_version("1.9.9") == "1.9.10"
    assert bump_policy_version("2.0") == "2.1"


def test_bump_handles_purely_numeric_and_non_numeric_versions():
    assert bump_policy_version("3") == "4"
    # No trailing numeric segment: append rather than reject -- the
    # fingerprint carries the real change detection.
    assert bump_policy_version("v2-custom") == "v2-custom.1"


def test_bump_always_differs_from_its_input():
    for version in ("1.1.0", "0", "weird", "a.b.c", "1.2.3.4"):
        assert bump_policy_version(version) != version


# --------------------------------------------------------------------------
# policy_with_updated_flags
# --------------------------------------------------------------------------


def test_flag_update_changes_flag_version_and_fingerprint():
    policy = _policy()
    updated = policy_with_updated_flags(policy, allow_new_positions=True)
    assert updated.allow_new_positions is True
    assert updated.version == "1.1.1"
    assert compute_policy_fingerprint(updated) != compute_policy_fingerprint(policy)
    # The original frozen policy is untouched.
    assert policy.allow_new_positions is False
    assert policy.version == "1.1.0"


def test_flag_update_can_change_both_flags_in_one_bump():
    updated = policy_with_updated_flags(
        _policy(), allow_new_positions=True, enable_strategy_proposals=True
    )
    assert updated.allow_new_positions is True
    assert updated.enable_strategy_proposals is True
    assert updated.version == "1.1.1"


def test_noop_update_is_refused_not_silently_version_bumped():
    """A no-change 'update' that still bumped the version would invalidate
    every pending proposal (fingerprint binds approval) for no reason."""
    with pytest.raises(ValueError, match="No policy change requested"):
        policy_with_updated_flags(_policy(), allow_new_positions=False)
    with pytest.raises(ValueError, match="No policy change requested"):
        policy_with_updated_flags(_policy())


def test_flag_update_result_passes_validation():
    updated = policy_with_updated_flags(_policy(), enable_strategy_proposals=True)
    updated.validate()  # must not raise


# --------------------------------------------------------------------------
# save_policy
# --------------------------------------------------------------------------


def test_save_then_load_round_trips_identically(tmp_path: Path):
    policy = policy_with_updated_flags(_policy(), allow_new_positions=True)
    target = tmp_path / "policy.json"
    save_policy(policy, target)
    reloaded = load_policy(target)
    assert reloaded == policy
    assert compute_policy_fingerprint(reloaded) == compute_policy_fingerprint(policy)


def test_save_overwrites_atomically_and_leaves_no_temp_file(tmp_path: Path):
    target = tmp_path / "policy.json"
    save_policy(_policy(), target)
    original_content = target.read_text(encoding="utf-8")

    save_policy(policy_with_updated_flags(_policy(), allow_new_positions=True), target)
    assert target.read_text(encoding="utf-8") != original_content
    # os.replace semantics: the temp staging file must not linger.
    assert list(tmp_path.iterdir()) == [target]
    # And the result is complete, parseable JSON with the new flag.
    assert json.loads(target.read_text(encoding="utf-8"))["allow_new_positions"] is True


def test_invalid_policy_is_refused_before_any_filesystem_effect(tmp_path: Path):
    """The dangerous direction: validation failure must leave the existing
    file byte-identical -- never half-written, never replaced."""
    target = tmp_path / "policy.json"
    save_policy(_policy(), target)
    before = target.read_bytes()

    corrupt = dataclasses.replace(_policy(), max_order_value=float("nan"))
    with pytest.raises(ValueError):
        save_policy(corrupt, target)
    assert target.read_bytes() == before
    assert list(tmp_path.iterdir()) == [target]


def test_saved_default_policy_shape_matches_the_checked_in_file_shape():
    """The checked-in default policy must survive the exact round trip the
    UI workflow performs (load -> flag update -> save shape), so a UI edit
    can never write a file load_policy() rejects."""
    from assistant.policy import DEFAULT_POLICY_PATH

    policy = load_policy(DEFAULT_POLICY_PATH)
    updated = policy_with_updated_flags(
        policy, allow_new_positions=not policy.allow_new_positions
    )
    serialized = json.dumps(updated.to_dict(), indent=2) + "\n"
    raw = json.loads(serialized)
    raw["allowed_sides"] = tuple(raw["allowed_sides"])
    raw["allowed_order_types"] = tuple(raw["allowed_order_types"])
    reparsed = TradingPolicy(**raw)
    reparsed.validate()
    assert reparsed == updated
