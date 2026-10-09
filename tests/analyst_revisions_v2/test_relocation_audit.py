"""Synthetic in-root tests; never invoke the authorized fixed-path census."""
import copy
import hashlib
import json
import os
import stat

import pytest

from scripts import audit_arv2_relocation as subject


@pytest.fixture
def roots(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir()
    (old / "private.bin").write_bytes(b"secret-private-bytes\x00" + str(old).encode())
    artifact = old / "artifacts" / "analyst_revisions_v2" / "retained"
    artifact.mkdir(parents=True)
    (artifact / "historic.json").write_text(json.dumps({"source": str(old / "private.bin")}))
    (old / ".git").write_text("gitdir: some-private-administration\n")
    return old, new


def before(roots, monkeypatch):
    old, new = roots
    monkeypatch.chdir(old)
    report, digest = subject._run("before", old, new)
    assert report["complete"]
    return report, digest


def after(roots, monkeypatch, digest):
    old, new = roots
    old.rename(new)
    monkeypatch.chdir(new)
    return subject._run("after", old, new, digest)


def test_exact_rename_census_preserves_bytes_identity_and_private_reports(roots, monkeypatch):
    old, new = roots
    baseline, digest = before(roots, monkeypatch)
    report, result_digest = after(roots, monkeypatch, digest)
    assert report["complete"] and report["matches_before"]
    assert not report["mismatches"]
    assert report["before_report_sha256"] == digest
    counts = baseline["census"]
    assert counts["regular_file_count"] == 2
    assert counts["artifact_regular_file_count"] == 1
    assert counts["old_root_literal_file_count"] == 2
    assert counts["artifact_old_root_literal_file_count"] == 1
    assert ".git" not in counts["entries"]
    assert not any(name.startswith(subject.OUTPUT) for name in counts["entries"])
    assert baseline["excluded_relative_paths"] == [".git", subject.OUTPUT]
    assert not report["source_loader_authentication"]
    assert not report["proves_continuous_stability"]
    assert not report["provider_or_qc_contact"]
    output = new / subject.OUTPUT
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert sorted(path.name for path in output.iterdir()) == ["after.json", "before.json"]
    for stage, expected in (("before", digest), ("after", result_digest)):
        path = output / f"{stage}.json"
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == expected
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert b"secret-private-bytes" not in raw
        assert raw == subject._json_bytes(json.loads(raw))


def test_literal_detection_crosses_every_chunk_boundary(roots, monkeypatch):
    old, _new = roots
    monkeypatch.setattr(subject, "CHUNK_BYTES", 7)
    baseline, _digest = before(roots, monkeypatch)
    assert baseline["census"]["old_root_literal_file_count"] == 2
    assert baseline["census"]["artifact_old_root_literal_file_count"] == 1


def test_symlinks_recorded_never_followed_and_external_bytes_not_read(roots, tmp_path, monkeypatch):
    old, _new = roots
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "not-read.bin").write_bytes(b"NEVER READ THIS TARGET")
    (old / "external-directory").symlink_to(outside, target_is_directory=True)
    (old / "external-file").symlink_to(outside / "not-read.bin")
    (old / "broken-link").symlink_to(outside / "absent")
    (old / "path-bound-link").symlink_to(old / "private.bin")
    original = subject._read_regular

    def read(parent, name, relative, *args, **kwargs):
        assert name not in ("external-file", "not-read.bin", "broken-link")
        return original(parent, name, relative, *args, **kwargs)

    monkeypatch.setattr(subject, "_read_regular", read)
    baseline, _digest = before(roots, monkeypatch)
    assert baseline["census"]["symlink_count"] == 4
    assert baseline["census"]["old_root_literal_symlink_target_count"] == 1
    assert not baseline["symlink_target_resolution"]
    assert not baseline["symlink_target_compatibility_established"]
    assert baseline["census"]["regular_file_count"] == 2
    assert baseline["census"]["entries"]["external-directory"]["target"] == str(outside)
    assert not any("not-read.bin" in path for path in baseline["census"]["entries"])


@pytest.mark.parametrize("change", ["bytes", "inode", "mode", "added", "removed", "symlink"])
def test_after_reports_every_unexplained_change_and_retains_report(roots, monkeypatch, change):
    old, new = roots
    _baseline, digest = before(roots, monkeypatch)
    old.rename(new)
    monkeypatch.chdir(new)
    path = new / "private.bin"
    if change == "bytes":
        path.write_bytes(b"changed")
    elif change == "inode":
        sibling = new / "replacement"
        sibling.write_bytes(path.read_bytes())
        sibling.replace(path)
    elif change == "mode":
        path.chmod(0o600 if stat.S_IMODE(path.stat().st_mode) != 0o600 else 0o400)
    elif change == "added":
        (new / "added").write_bytes(b"new")
    elif change == "removed":
        path.unlink()
    else:
        path.unlink()
        path.symlink_to(new / "absent")
    report, _digest = subject._run("after", old, new, digest)
    assert report["complete"] and not report["matches_before"]
    assert report["mismatches"]
    assert (new / subject.OUTPUT / "after.json").is_file()


@pytest.mark.parametrize("field", ["flags", "ctime_ns", "uid", "gid", "nlink", "mtime_ns"])
def test_metadata_only_changes_are_not_waived(roots, monkeypatch, field):
    _baseline, digest = before(roots, monkeypatch)
    original = subject._metadata

    # Model a stable metadata change for an exact pre-existing file, without
    # modifying host ownership/flags or stripping any real attributes.
    size = (roots[0] / "private.bin").stat().st_size

    def metadata(info):
        row = original(info)
        if stat.S_ISREG(info.st_mode) and info.st_size == size:
            row[field] = (row[field] or 0) + 1
        return row

    monkeypatch.setattr(subject, "_metadata", metadata)
    report, _digest = after(roots, monkeypatch, digest)
    assert report["complete"] and not report["matches_before"]
    assert any(row["path"] == "private.bin" for row in report["mismatches"])


def test_drift_during_stream_read_refuses_and_retains_failure_report(roots, monkeypatch):
    old, new = roots
    monkeypatch.chdir(old)
    original = os.read
    target_inode = (old / "private.bin").stat().st_ino
    changed = False

    def read(fd, count):
        nonlocal changed
        chunk = original(fd, count)
        if not changed and os.fstat(fd).st_ino == target_inode:
            changed = True
            with (old / "private.bin").open("ab") as stream:
                stream.write(b"drift")
        return chunk

    monkeypatch.setattr(subject.os, "read", read)
    report, _digest = subject._run("before", old, new)
    assert not report["complete"]
    assert report["refusal"] == {"code": "file_changed_during_read", "path": "private.bin"}
    assert (old / subject.OUTPUT / "before.json").is_file()


def test_same_byte_named_leaf_replacement_during_read_refuses(roots, monkeypatch):
    old, new = roots
    monkeypatch.chdir(old)
    target = old / "private.bin"
    replacement = target.read_bytes()
    target_inode = target.stat().st_ino
    original = os.read
    changed = False

    def read(fd, count):
        nonlocal changed
        chunk = original(fd, count)
        if not changed and os.fstat(fd).st_ino == target_inode:
            changed = True
            staging = old / "replacement"
            staging.write_bytes(replacement)
            staging.replace(target)
        return chunk

    monkeypatch.setattr(subject.os, "read", read)
    report, _digest = subject._run("before", old, new)
    assert not report["complete"] and report["refusal"]["code"] == "file_changed_during_read"


def test_directory_names_changed_during_census_refuse(roots, monkeypatch):
    old, new = roots
    monkeypatch.chdir(old)
    original = subject._read_regular
    changed = False

    def read(*args, **kwargs):
        nonlocal changed
        result = original(*args, **kwargs)
        if not changed:
            changed = True
            (old / "concurrent-leaf").write_bytes(b"new")
        return result

    monkeypatch.setattr(subject, "_read_regular", read)
    report, _digest = subject._run("before", old, new)
    assert not report["complete"]
    assert report["refusal"]["code"] == "directory_changed_during_census"


def test_reports_and_spent_trial_directory_cannot_be_overwritten(roots, monkeypatch):
    old, new = roots
    _baseline, digest = before(roots, monkeypatch)
    raw = (old / subject.OUTPUT / "before.json").read_bytes()
    with pytest.raises(subject.Refusal, match="trial_path_already_spent"):
        subject._run("before", old, new)
    assert (old / subject.OUTPUT / "before.json").read_bytes() == raw
    after(roots, monkeypatch, digest)
    raw = (new / subject.OUTPUT / "after.json").read_bytes()
    with pytest.raises(subject.Refusal, match="report_or_pending_already_spent"):
        subject._run("after", old, new, digest)
    assert (new / subject.OUTPUT / "after.json").read_bytes() == raw


def test_pending_report_spends_after_path(roots, monkeypatch):
    old, new = roots
    _baseline, digest = before(roots, monkeypatch)
    old.rename(new)
    monkeypatch.chdir(new)
    (new / subject.OUTPUT / "after.json.pending").write_bytes(b"interrupted")
    with pytest.raises(subject.Refusal, match="report_or_pending_already_spent"):
        subject._run("after", old, new, digest)
    assert not (new / subject.OUTPUT / "after.json").exists()


def test_after_requires_correct_external_digest_and_retains_failure(roots, monkeypatch):
    _baseline, _digest = before(roots, monkeypatch)
    report, _digest = after(roots, monkeypatch, "0" * 64)
    assert not report["complete"]
    assert report["refusal"]["code"] == "before_digest_mismatch"


@pytest.mark.parametrize("pin", [None, "", "A" * 64, "x" * 64, "0" * 63])
def test_after_missing_or_malformed_pin_refuses_before_allocation(roots, monkeypatch, pin):
    old, new = roots
    old.rename(new)
    monkeypatch.chdir(new)
    with pytest.raises(subject.Refusal, match="externally_pinned_before_digest_required"):
        subject._run("after", old, new, pin)
    assert not (new / subject.OUTPUT).exists()


def test_wrong_current_root_refuses_before_any_write(roots, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(subject.Refusal, match="wrong_stage_or_working_directory"):
        subject._run("before", *roots)
    assert not (roots[0] / subject.OUTPUT).exists()


def test_output_symlink_is_not_followed(roots, tmp_path, monkeypatch):
    old, new = roots
    monkeypatch.chdir(old)
    parent = old / "artifacts" / "analyst_revisions_v2" / "relocation_trial"
    parent.symlink_to(tmp_path / "outside", target_is_directory=True)
    with pytest.raises(OSError):
        subject._run("before", old, new)
    assert not (tmp_path / "outside").exists()


def test_static_fifo_is_inventoried_and_compared_without_opening(roots, monkeypatch):
    old, new = roots
    monkeypatch.chdir(old)
    os.mkfifo(old / "fifo")
    original = os.open

    def open_file(path, *args, **kwargs):
        assert path != "fifo"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(subject.os, "open", open_file)
    report, digest = subject._run("before", old, new)
    assert report["complete"] and report["census"]["special_entry_count"] == 1
    assert report["census"]["entries"]["fifo"]["kind"] == "special"
    assert "rdev" in report["census"]["entries"]["fifo"]["metadata"]
    report, _digest = after(roots, monkeypatch, digest)
    assert report["complete"] and report["matches_before"]


def test_symlink_bytes_preserved_does_not_assert_target_compatibility(roots, monkeypatch):
    old, new = roots
    (old / "historical-link").symlink_to(old / "private.bin")
    _baseline, digest = before(roots, monkeypatch)
    report, _digest = after(roots, monkeypatch, digest)
    assert report["matches_before"] and not (new / "historical-link").exists()
    assert report["census"]["entries"]["historical-link"]["target"] == str(old / "private.bin")
    assert not report["symlink_target_compatibility_established"]


def test_cli_outputs_counts_digest_only_no_private_payload(roots, monkeypatch, capsys):
    old, new = roots
    monkeypatch.chdir(old)
    monkeypatch.setattr(subject, "OLD_ROOT", old)
    monkeypatch.setattr(subject, "NEW_ROOT", new)
    assert subject.main(["before"]) == 0
    output = capsys.readouterr()
    assert "regular_files=2" in output.out and "artifact_old_root_literal_files=1" in output.out
    assert "report_sha256=" in output.out
    assert str(old) not in output.out and "secret" not in output.out and not output.err


def test_compare_includes_exact_metadata_and_symlink_target():
    base = {"entries": {"a": {"kind": "file", "sha256": "a" * 64, "metadata": {"ino": 1}},
                        "link": {"kind": "symlink", "target": "old"}}}
    revised = copy.deepcopy(base)
    revised["entries"]["a"]["metadata"]["ino"] = 2
    revised["entries"]["link"]["target"] = "new"
    assert subject._compare(base, revised) == [
        {"path": "a", "difference": "changed", "fields": ["metadata"]},
        {"path": "link", "difference": "changed", "fields": ["target"]}]
