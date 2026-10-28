"""V2 present-stat contract; fabricated tmp layouts/metadata only, lstat only.

Temp-layout tests fabricate the separate mount device. Pure-dictionary cases
also fabricate all stamps/identities/protection observations; they authenticate
no original image or kernel flag and never certify historical dispatch.
"""
import ast
import builtins
import os
from pathlib import Path
import json
import stat
import sys

import pytest

from scripts import diagnose_short_interest_count_run13448_stamps as stamps

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="APFS directory link counts and birth times")


def _layout(base):
    namespace = base / "namespace"
    for name in ("", "mount", "mount/capture", *stamps.CONTAINERS, "mount/claim"):
        (namespace / name).mkdir(mode=0o700)
    claim = namespace / stamps.CLAIM
    claim.write_bytes(b"{}"); claim.chmod(0o600)
    return namespace


def _classify(namespace):
    facts = stamps.observe(namespace)
    facts[""]["device"] = -1  # Fabricated separate image volume.
    return stamps.classify(facts, os.getuid())


def _refusal(namespace):
    with pytest.raises(stamps.StampEvidenceRefusal) as error: _classify(namespace)
    return str(error.value)


def test_apfs_directory_links_count_every_entry(tmp_path):
    probe = tmp_path / "probe"; probe.mkdir()
    assert probe.lstat().st_nlink == 2
    (probe / "file").write_bytes(b"")
    assert probe.lstat().st_nlink == 3  # The emptiness rule depends on this.


def test_untouched_layout_observes_relationships_without_historical_authority(tmp_path):
    result = _classify(_layout(tmp_path))
    assert result["present_container_link_counts_equal_two"] is True
    assert result["present_container_mtimes_match_birth_times_within_tolerance"] is True
    assert result["present_container_ctimes_precede_present_claim_birth_time"] is True
    _assert_history_unverified(result)


def test_START_directory_created_then_removed_after_claim_is_detected(tmp_path):
    namespace = _layout(tmp_path)
    ticket = namespace / "mount/capture/starts/000001"; ticket.mkdir(); ticket.rmdir()
    assert _refusal(namespace) == "REFUSED: run13448_container_entry_changed"


def test_restored_mtime_still_leaves_a_ctime_after_the_claim(tmp_path):
    namespace = _layout(tmp_path)
    starts = namespace / "mount/capture/starts"; born = round(starts.lstat().st_birthtime * 1e9)
    ticket = starts / "000001"; ticket.mkdir(); ticket.rmdir()
    os.utime(starts, ns=(born, born))
    assert abs(starts.lstat().st_mtime_ns - born) <= stamps.BIRTH_TOLERANCE_NS
    assert _refusal(namespace) == "REFUSED: run13448_container_changed_after_claim"


def test_remaining_START_directory_refuses_as_not_empty(tmp_path):
    namespace = _layout(tmp_path)
    starts = namespace / "mount/capture/starts"; born = round(starts.lstat().st_birthtime * 1e9)
    (starts / "000001").mkdir(); os.utime(starts, ns=(born, born))
    assert _refusal(namespace) == "REFUSED: run13448_container_not_empty"


def test_same_device_mount_is_not_a_separate_volume(tmp_path):
    with pytest.raises(stamps.StampEvidenceRefusal, match="run13448_mount_not_separate_volume"):
        stamps.classify(stamps.observe(_layout(tmp_path)), os.getuid())


def test_observation_opens_and_lists_nothing(tmp_path, monkeypatch):
    namespace = _layout(tmp_path)
    def forbidden(*args, **kwargs): raise AssertionError("FORBIDDEN_OPEN_OR_LIST")
    for owner, name in ((os, "open"), (os, "scandir"), (os, "listdir"), (builtins, "open"), (Path, "iterdir")):
        monkeypatch.setattr(owner, name, forbidden)
    _assert_history_unverified(_classify(namespace))


def test_partial_leaf_pins_detect_changed_pinned_ctime():
    facts = {name: {"inode": inode, "mtime_ns": mtime, "ctime_ns": ctime}
        for name, (inode, mtime, ctime) in stamps.PINNED.items()}
    assert stamps.pins_match(facts)
    facts["mount/capture/starts"]["ctime_ns"] += 1
    assert not stamps.pins_match(facts)


def test_verifier_imports_no_source_budget_or_dispatch_capability():
    tree = ast.parse(Path(stamps.__file__).read_text(encoding="utf-8"))
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imported == {"os", "pathlib", "stat", "sys", "data.hashing"}


def _fabricated_observation():
    """Metadata values only; no original image, claim or inode is adopted."""
    facts = {name: {"device": 2, "inode": ordinal, "mode": stat.S_IFDIR | 0o700,
        "uid": os.getuid(), "links": 2, "birth_ns": 1, "mtime_ns": 1, "ctime_ns": 2,
        "flags": 0} for ordinal, name in enumerate(("", "mount", "mount/capture", "mount/claim", *stamps.CONTAINERS), 100)}
    facts[""]["device"] = 1
    for name, (inode, mtime, ctime) in stamps.PINNED.items():
        facts[name] = {"device": 2, "inode": inode, "mode": stat.S_IFDIR | 0o700,
            "uid": os.getuid(), "links": 2, "birth_ns": mtime,
            "mtime_ns": mtime, "ctime_ns": ctime, "flags": 0}
    facts[stamps.CLAIM].update(mode=stat.S_IFREG | 0o600, links=1,
        birth_ns=1793115455346106000, flags=2)
    return facts


def _assert_history_unverified(result):
    assert result["schema"] == "si-count-run13448-stamp-observation-v2"
    assert result["original_lineage_authenticated"] is False
    assert result["historical_zero_dispatch_verified"] is False
    assert result["historical_counts"] == {"per_ticket_START_directories_created": None,
        "provider_key_reads": None, "provider_GET_requests": None,
        "internal_START_reservations": None, "charged_or_reserved_bytes": None}
    assert result["required_unauthenticated_assumptions"]
    assert result["release_refund_or_dispatch_authority"] is False
    assert "containers_never_held_an_entry" not in result
    assert "provider_key_read_or_GET_possible" not in result


def test_partial_leaf_pins_never_authenticate_original_history():
    facts = _fabricated_observation()
    assert stamps.pins_match(facts)
    _assert_history_unverified(stamps.classify(facts, os.getuid()))


@pytest.mark.parametrize("change", ["claim_birth", "mount_device", "claim_flags", "capture_inode"])
def test_unpinned_metadata_changes_cannot_establish_historical_zero_dispatch(change):
    facts = _fabricated_observation()
    if change == "claim_birth": facts[stamps.CLAIM]["birth_ns"] += 1_000_000_000
    elif change == "mount_device":
        for name in facts:
            if name: facts[name]["device"] += 10
    elif change == "claim_flags": facts[stamps.CLAIM]["flags"] = 0
    else: facts["mount/capture"]["inode"] += 100
    assert stamps.pins_match(facts)
    _assert_history_unverified(stamps.classify(facts, os.getuid()))


def test_present_claim_mode_must_still_be_owner_only():
    facts = _fabricated_observation(); facts[stamps.CLAIM]["mode"] = stat.S_IFREG | 0o644
    with pytest.raises(stamps.StampEvidenceRefusal, match="run13448_claim_changed"):
        stamps.classify(facts, os.getuid())


@pytest.mark.parametrize("name", ["mount/capture", "mount/claim"])
def test_middle_ancestor_symlink_cannot_be_ignored(name):
    facts = _fabricated_observation(); facts[name]["mode"] = stat.S_IFLNK | 0o700
    with pytest.raises(stamps.StampEvidenceRefusal, match="run13448_ancestor_changed"):
        stamps.classify(facts, os.getuid())


def test_pin_mismatch_main_emits_no_positive_historical_assertion(monkeypatch, capsys):
    facts = _fabricated_observation(); facts[stamps.CLAIM]["inode"] += 100
    monkeypatch.setattr(stamps, "observe", lambda unused: facts)
    assert stamps.main() == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "partial_leaf_pin_mismatch"
    assert result["partial_leaf_pins_match_2026_10_28_observation"] is False
    _assert_history_unverified(result)
