"""Synthetic local archives and private temp dirs only; never the USB disk."""
import io
import json
import os
from pathlib import Path
import stat
import zipfile

import pytest

from research.target_price_revisions_qc import remx_prepare_20261103 as p

SOURCE = (b"2005-01-04 00:00:00,1,2,1,2,10\n"
          b"2026-02-20 00:00:00,1,2,1,2,20\n"
          b"2026-02-23 00:00:00,1,2,1,2,30.0\n"
          b"2026-02-24 00:00:00,1,2,1,2,30.5\n")
HEAD = "a" * 40
OP = "REMX-20261103-EXPORT-SYNTHETIC-001"


def archive_bytes(raw=SOURCE, *, duplicate=False, compression=zipfile.ZIP_DEFLATED):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=compression) as archive:
        archive.writestr(p.MEMBER, raw)
        if duplicate:
            with pytest.warns(UserWarning):
                archive.writestr(p.MEMBER, raw)
    return output.getvalue()


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "lane"
    root.mkdir(mode=0o700)
    monkeypatch.chdir(root)
    monkeypatch.setattr(p, "ROOT", root)
    usb = tmp_path / "synthetic_usb"
    usb.mkdir(mode=0o700)
    monkeypatch.setattr(p, "USB_ROOT", usb)
    monkeypatch.setattr(p, "MEMBER_BYTES", len(SOURCE))
    monkeypatch.setattr(p, "MEMBER_SHA256", p._sha(SOURCE))
    texts = {}
    for name in p.REQUIRED_SOURCES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = b"# public synthetic source\n"
        path.write_bytes(raw)
        texts[name] = raw
    record = root / p.RECORD
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text("Synthetic public record\n")
    archive = usb / p.ARCHIVE
    archive.parent.mkdir(parents=True)
    archive.write_bytes(archive_bytes())

    def git(*args):
        if args == ("rev-parse", "--show-toplevel"):
            return str(root).encode()
        if args == ("branch", "--show-current"):
            return p.BRANCH.encode()
        if args == ("rev-parse", "HEAD"):
            return HEAD.encode()
        if args in (("diff", "--name-only", "-z"), ("diff", "--cached", "--name-only", "-z")):
            return b""
        if args[0] == "show":
            return texts[args[1].split(":", 1)[1]]
        raise AssertionError(args)
    monkeypatch.setattr(p, "_git", git)
    return root, usb, archive, record, texts


def test_export_claim_precedes_source_read_and_preserves_every_row(workspace, monkeypatch):
    root, usb, archive, record, _ = workspace
    before_archive = archive.read_bytes()
    original_read = p._read_member
    def read():
        operation = root / p.DESTINATION / OP
        claim = json.loads((operation / "claim.json").read_bytes())
        assert claim["private_source"]["sha256"] == p._sha(SOURCE)
        assert claim["max_member_reads"] == 1
        assert claim["reserved_attempt"] is None
        assert claim["financial_outcome_look"] is None
        assert set(claim["source_hashes"]) == p.REQUIRED_SOURCES
        assert "BEFORE the one fixed USB member read" in record.read_text()
        return original_read()
    monkeypatch.setattr(p, "_read_member", read)
    receipt, descriptor = p.prepare_workspace(OP)
    assert receipt["status"] == "prepared_partial_local_candidate"
    operation = root / p.DESTINATION / OP
    assert archive.read_bytes() == before_archive
    assert (operation / "source_original.csv").read_bytes() == SOURCE
    assert set(receipt["outputs"]) == p.OUTPUT_NAMES
    manifest = json.loads((operation / "manifest.json").read_bytes())
    assert manifest["source_rows"] == 4
    assert manifest["candidate_rows"] == 2
    assert manifest["missing_post_inception_source_dates"] == ["2026-02-24"]
    assert not manifest["full_coverage_verified"]
    assert not receipt["financial_acceptance"] and not receipt["backtesting_ready"]
    assert receipt["source_proof"]["archive_sha256"] is None
    assert receipt["source_proof"]["archive_hash_not_computed"] is True
    assert receipt["source_proof"]["member_sha256"] == p._sha(SOURCE)
    assert descriptor["sha256"] == p._sha((operation / "receipt.json").read_bytes())
    for child in operation.iterdir():
        assert stat.S_IMODE(child.stat().st_mode) == 0o600
    assert stat.S_IMODE(operation.stat().st_mode) == 0o700


def test_replay_refused_before_second_member_read(workspace, monkeypatch):
    p.prepare_workspace(OP)
    monkeypatch.setattr(p, "_read_member", lambda: pytest.fail("spent scope reused"))
    with pytest.raises(FileExistsError):
        p.prepare_workspace(OP)


@pytest.mark.parametrize("operation", ["", "../escape", "REMX-20261103-EXPORT-", "x" * 100, 1])
def test_invalid_operation_refuses_before_context_or_io(operation, monkeypatch):
    monkeypatch.setattr(p, "_context", lambda: pytest.fail("context reached"))
    with pytest.raises(p.PreparationRefusal):
        p.prepare_workspace(operation)


def test_uncommitted_source_refuses_before_claim_or_member_read(workspace, monkeypatch):
    root, _, _, _, texts = workspace
    (root / p.MODULE).write_bytes(b"# changed\n")
    monkeypatch.setattr(p, "_read_member", lambda: pytest.fail("private read"))
    with pytest.raises(p.PreparationRefusal):
        p.prepare_workspace(OP)
    assert not (root / p.DESTINATION).exists()


def test_source_change_after_claim_is_retained_refusal_before_private_read(workspace, monkeypatch):
    root, _, _, _, _ = workspace
    note = p._note
    def changed(message):
        note(message)
        if message.startswith("Fresh REMX"):
            (root / p.MODULE).write_bytes(b"# replaced\n")
    monkeypatch.setattr(p, "_note", changed)
    monkeypatch.setattr(p, "_read_member", lambda: pytest.fail("private read"))
    receipt, _ = p.prepare_workspace(OP)
    assert receipt["status"] == "refused"
    assert receipt["outputs"] == {}
    assert (root / p.DESTINATION / OP / "claim.json").exists()


def test_deadline_after_read_prevents_processing_and_export(workspace, monkeypatch):
    clock = [10]
    monkeypatch.setattr(p.time, "monotonic", lambda: clock[0])
    read = p._read_member
    def expired():
        result = read()
        clock[0] += p.MAX_LIFETIME_SECONDS
        return result
    monkeypatch.setattr(p, "_read_member", expired)
    monkeypatch.setattr(p.repair, "repair_remx_daily", lambda *a, **k: pytest.fail("processing after deadline"))
    receipt, _ = p.prepare_workspace(OP)
    assert receipt["status"] == "refused" and receipt["outputs"] == {}


@pytest.mark.parametrize("damage", ["hash", "duplicate", "central", "directory", "parent_link", "leaf_link"])
def test_invalid_archive_has_body_free_refusal(workspace, damage):
    root, _, archive, _, _ = workspace
    if damage == "hash":
        archive.write_bytes(archive_bytes(SOURCE.replace(b"30.5", b"30.6")))
    elif damage == "duplicate":
        archive.write_bytes(archive_bytes(duplicate=True))
    elif damage == "central":
        raw = bytearray(archive.read_bytes())
        raw[-10:-6] = (p.MAX_CENTRAL_BYTES + 1).to_bytes(4, "little")
        archive.write_bytes(raw)
    elif damage == "directory":
        archive.unlink()
        archive.mkdir()
    elif damage == "parent_link":
        parent = archive.parent
        actual = parent.with_name("original")
        parent.rename(actual)
        parent.symlink_to(actual, target_is_directory=True)
    else:
        actual = archive.with_name("actual.zip")
        archive.rename(actual)
        archive.symlink_to(actual)
    receipt, _ = p.prepare_workspace(OP)
    assert receipt["status"] == "refused"
    assert receipt["outputs"] == {}
    raw = (root / p.DESTINATION / OP / "receipt.json").read_text()
    assert "Traceback" not in raw and "30.5" not in raw and "exception" not in raw


def test_export_symlink_refuses_without_escape(workspace):
    root, _, _, _, _ = workspace
    (root / "artifacts").mkdir()
    outside = root / "outside"
    outside.mkdir()
    (root / p.DESTINATION).symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        p.prepare_workspace(OP)
    assert list(outside.iterdir()) == []


def test_public_private_directory_refused(workspace):
    root, _, _, _, _ = workspace
    destination = root / p.DESTINATION
    destination.mkdir(parents=True, mode=0o755)
    destination.chmod(0o755)
    with pytest.raises(p.PreparationRefusal):
        p.prepare_workspace(OP)


def test_partial_write_failure_retains_original_and_refusal(workspace, monkeypatch):
    root, _, _, _, _ = workspace
    retain = p._retain
    def interrupted(path, raw):
        if path.name == "row_ledger.jsonl":
            raise OSError("sensitive body not persisted")
        return retain(path, raw)
    monkeypatch.setattr(p, "_retain", interrupted)
    receipt, _ = p.prepare_workspace(OP)
    assert receipt["status"] == "refused"
    assert receipt["outputs"]
    assert (root / p.DESTINATION / OP / "source_original.csv").read_bytes() == SOURCE
    assert not receipt["financial_acceptance"]
    assert "sensitive body" not in (root / p.DESTINATION / OP / "receipt.json").read_text()


def test_context_rejects_wrong_branch_and_staged_changes(workspace, monkeypatch):
    original = p._git
    for replacement in (("branch", b"main"), ("staged", b"user.txt\0")):
        def git(*args):
            if replacement[0] == "branch" and args == ("branch", "--show-current"):
                return replacement[1]
            if replacement[0] == "staged" and args == ("diff", "--cached", "--name-only", "-z"):
                return replacement[1]
            return original(*args)
        monkeypatch.setattr(p, "_git", git)
        with pytest.raises(p.PreparationRefusal):
            p._context()


@pytest.mark.parametrize("target", ["archive", "public_source", "record"])
def test_fifo_refused_before_blocking_open(workspace, monkeypatch, target):
    root, _, archive, record, _ = workspace
    path = {"archive": archive, "public_source": root / p.MODULE, "record": record}[target]
    path.unlink()
    os.mkfifo(path, mode=0o600)
    if target == "archive":
        receipt, _ = p.prepare_workspace(OP)
        assert receipt["status"] == "refused"
    else:
        with pytest.raises(p.PreparationRefusal):
            p.prepare_workspace(OP)


def test_nonregular_record_refused_by_durable_note_without_block(workspace):
    _, _, _, record, _ = workspace
    record.unlink()
    os.mkfifo(record, mode=0o600)
    with pytest.raises(p.PreparationRefusal):
        p._note("synthetic metadata")
