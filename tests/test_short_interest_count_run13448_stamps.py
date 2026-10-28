"""SI-CR24-001 stamp verifier; fabricated tmp layouts only, lstat only.

The only fabricated seam is the mount device: a tmp tree cannot hold a
second volume, so each test marks its fabricated mount as a separate device.
"""
import ast
import builtins
import os
from pathlib import Path
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


def test_untouched_layout_bounds_per_ticket_STARTs_to_zero_without_authority(tmp_path):
    result = _classify(_layout(tmp_path))
    assert result["per_ticket_START_directories_created"] == 0
    assert result["provider_key_read_or_GET_possible"] is False
    assert result["release_refund_or_dispatch_authority"] is False


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
    assert _classify(namespace)["containers_never_held_an_entry"] is True


def test_pins_report_any_change_since_the_recorded_observation():
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
