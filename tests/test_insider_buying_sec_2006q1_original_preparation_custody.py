"""Invented fixed-layout custody fixtures; no actual retained rows or replay."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest
pytest.importorskip("fcntl", reason="macOS/POSIX custody support")

SOURCE = Path(__file__).resolve().parents[1] / "research/insider_buying_sec_2006q1_parent_projection_v1.py"
SPEC = importlib.util.spec_from_file_location("original_preparation_private_qa180", SOURCE)
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def sha(raw): return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def fixture_layout(tmp_path):
    root = tmp_path / "invented-legacy"
    rows = b'INVENTED OPAQUE ROW BYTES\n'
    leaf_raw = {("completion.json",): b'{}', ("assessment.json",): b'{}',
        ("ib1a", module.RAW_ID, "archive.zip"): b"INVENTED RAW ZIP",
        ("ib1a", module.RAW_ID, "manifest.json"): b'{}',
        ("ib1a", module.RAW_ID, "snapshot.commit.json"): b'{}',
        ("ib1b", module.PARSED_ID, "manifest.json"): json.dumps({"rows": {"sha256": sha(rows), "size_bytes": len(rows)}}).encode(),
        ("ib1b", module.PARSED_ID, "rows.jsonl"): rows,
        ("ib1b", module.PARSED_ID, "accessions.jsonl"): b'INVENTED OPAQUE ACCESSIONS\n',
        ("ib1b", module.PARSED_ID, "snapshot.commit.json"): b'{}',
        ("ib1a", "." + module.RAW_ID + ".publication.lock"): b'\0',
        ("ib1b", "." + module.PARSED_ID + ".publication.lock"): b'\0'}
    for parts in module.DIRECTORIES:
        path = root.joinpath(*parts)
        path.mkdir(parents=True, mode=0o700 if not parts else 0o755)
        path.chmod(0o700 if not parts else 0o755)
    for parts, raw in leaf_raw.items():
        path = root.joinpath(*parts)
        path.write_bytes(raw);path.chmod(0o644 if parts[-1].endswith(".publication.lock") else 0o600)
    pins = module.InventedPins(sha(b'{}'), sha(b'{}'), sha(rows), len(rows))
    return root, pins


def test_exact_public_publisher_layout_is_readonly_supported_without_rewriting_modes(fixture_layout):
    root, pins = fixture_layout
    before = {str(path.relative_to(root)): path.stat().st_mode for path in root.rglob("*")}
    reader = module.PinnedOriginalPreparation(root, invented=pins)
    try:
        assert len(reader.leaves) == 11
        assert len(reader.locks) == 2
        assert reader.leaves[(("ib1b", module.PARSED_ID), "rows.jsonl")][1] == pins.rows_sha256
        reader.recheck()
        with pytest.raises(module.OriginalPreparationCustodyError, match="streaming_pin_only"):
            reader.read(("ib1b", module.PARSED_ID), "rows.jsonl", cap=1024)
    finally: reader.close()
    assert {str(path.relative_to(root)): path.stat().st_mode for path in root.rglob("*")} == before


def test_generic_private_tree_still_refuses_public_nested_layout(fixture_layout):
    root, _ = fixture_layout
    tree = module.capture.bootstrap._Tree(module.capture.bootstrap.RootSpec("invented-legacy", root, "fixture"))
    try:
        with pytest.raises(module.capture.bootstrap.ParentBootstrapError, match="private_directory_owner_required"):
            tree.open(("ib1a",))
    finally: tree.close()


@pytest.mark.parametrize("mutation", ["data644", "directory700", "extra_leaf", "lock_bytes", "lock600", "symlink", "hardlink", "rows_hash", "completion_hash"])
def test_profile_does_not_widen_arbitrary_modes_names_links_or_hashes(fixture_layout, mutation):
    root, pins = fixture_layout
    target = root / "ib1b" / module.PARSED_ID / "rows.jsonl"
    if mutation == "data644": target.chmod(0o644)
    elif mutation == "directory700": target.parent.chmod(0o700)
    elif mutation == "extra_leaf": (target.parent / "unregistered.json").write_bytes(b'{}')
    elif mutation == "lock_bytes": (root / "ib1b" / ("." + module.PARSED_ID + ".publication.lock")).write_bytes(b'X')
    elif mutation == "lock600": (root / "ib1b" / ("." + module.PARSED_ID + ".publication.lock")).chmod(0o600)
    elif mutation == "symlink":
        real = target.parent / "hidden-real";target.rename(real);target.symlink_to(real.name)
    elif mutation == "hardlink": os.link(target, root.parent / "invented-hardlink")
    elif mutation == "rows_hash": target.write_bytes(b'INVENTED DIFFERENT ROWS\n')
    else: (root / "completion.json").write_bytes(b'{"changed":true}')
    with pytest.raises((module.OriginalPreparationCustodyError, OSError, ValueError)):
        module.PinnedOriginalPreparation(root, invented=pins)


@pytest.mark.parametrize("mutation", ["append_rows", "replace_leaf", "new_name", "mode_drift", "replace_directory"])
def test_held_versions_names_and_hashes_reject_concurrent_drift(fixture_layout, mutation):
    root, pins = fixture_layout
    reader = module.PinnedOriginalPreparation(root, invented=pins)
    try:
        target = root / "ib1b" / module.PARSED_ID / "rows.jsonl"
        if mutation == "append_rows":
            with target.open("ab") as file: file.write(b'INVENTED NEW BYTES')
        elif mutation == "replace_leaf":
            new = target.parent / "new";new.write_bytes(target.read_bytes());new.chmod(0o600);new.replace(target)
        elif mutation == "new_name": (root / "extra").write_bytes(b'X')
        elif mutation == "mode_drift": target.chmod(0o644)
        else:
            target.parent.rename(target.parent.with_name("old"));target.parent.mkdir(mode=0o755)
        with pytest.raises((module.OriginalPreparationCustodyError, OSError, ValueError)):
            reader.recheck()
    finally: reader.close()


def test_invented_profile_cannot_inspect_the_real_original_preparation(monkeypatch):
    monkeypatch.setattr(module.capture, "_fixture_root", lambda *_: None)
    monkeypatch.setattr(module.capture.bootstrap.custody, "_Chain", lambda *_: pytest.fail("must fence before real root read"))
    with pytest.raises(module.OriginalPreparationCustodyError, match="invented_preparation_root_refused"):
        module.PinnedOriginalPreparation(module.PREPARATION_ROOT, invented=module.InventedPins("a"*64, "b"*64, "c"*64, 1))


def test_inactive_private_reader_cannot_open_any_production_root(monkeypatch):
    monkeypatch.setattr(module, "__file__", str(module.capture.bootstrap.custody.LANE_ROOT / "artifacts/insider_buying/development_drafts/inactive-reader.py"))
    monkeypatch.setattr(module.capture.bootstrap.custody, "_Chain", lambda *_: pytest.fail("inactive reader must not open actual root"))
    with pytest.raises(module.OriginalPreparationCustodyError, match="inactive_original_reader_not_production_source"):
        module.PinnedOriginalPreparation()
