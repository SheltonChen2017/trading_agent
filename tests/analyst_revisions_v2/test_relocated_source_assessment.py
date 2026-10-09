"""Synthetic-only coverage; no historical source or native security reads."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat

import pytest

from scripts import assess_arv2_relocated_sources as assessment


def secure_snapshot(_fd):
    return {"acl_empty": True, "xattrs": {}}


@pytest.fixture
def scoped_source(tmp_path):
    anchor = tmp_path / "Code"
    anchor.mkdir(mode=0o700)
    root = anchor / "lane"
    root.mkdir(mode=0o755)
    root.chmod(0o755)
    package = root / "package"
    package.mkdir(mode=0o700)
    source = package / "source.bin"
    source.write_bytes(b"synthetic-source-only\n")
    source.chmod(0o600)
    row = {
        "kind": "file",
        "metadata": assessment.audit._metadata(source.stat()),
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "contains_old_root_literal": False,
    }
    return root, source, {"package/source.bin": row}


def test_guarded_consume_reaches_fresh_callback_and_preserves_qualifications(scoped_source):
    root, source, expected = scoped_source
    calls = []

    def consume():
        calls.append(source.read_bytes())
        return {"qualified_refusals": ["not_formally_admitted"]}

    result = assessment._guarded_consume(root, expected, consume, secure_snapshot)
    assert calls == [b"synthetic-source-only\n"]
    assert result["loader_results"] == {"qualified_refusals": ["not_formally_admitted"]}
    assert result["file_count"] == 1
    assert result["directory_count"] == 3
    assert result["file_security_observations"] == {
        "package/source.bin": {"acl_empty": True, "xattrs": {}}
    }


@pytest.mark.parametrize("field", [
    "ctime_ns", "mtime_ns", "mode", "gid", "flags", "nlink", "ino", "dev", "size", "uid",
])
def test_initial_metadata_must_exactly_match_after_snapshot(scoped_source, field):
    root, _source, expected = scoped_source
    expected = deepcopy(expected)
    expected["package/source.bin"]["metadata"][field] += 1
    reached = []
    with pytest.raises(assessment.audit.Refusal, match="current_source_metadata_changed"):
        assessment._guarded_consume(root, expected, lambda: reached.append(True), secure_snapshot)
    assert reached == []


def test_matching_metadata_does_not_excuse_wrong_bytes(scoped_source):
    root, _source, expected = scoped_source
    expected = deepcopy(expected)
    expected["package/source.bin"]["sha256"] = "0" * 64
    reached = []
    with pytest.raises(assessment.audit.Refusal, match="current_source_hash"):
        assessment._guarded_consume(root, expected, lambda: reached.append(True), secure_snapshot)
    assert reached == []


@pytest.mark.parametrize("field,value", [
    ("mode", stat.S_IFREG | 0o644), ("uid", os.getuid() + 1),
    ("nlink", 2), ("flags", stat.UF_IMMUTABLE), ("flags", None),
])
def test_matching_historical_metadata_cannot_admit_insecure_current_file(
        scoped_source, monkeypatch, field, value):
    root, source, expected = scoped_source
    expected = deepcopy(expected)
    expected["package/source.bin"]["metadata"][field] = value
    original = assessment.audit._metadata
    inode = source.stat().st_ino

    def metadata(info):
        result = original(info)
        if info.st_ino == inode:
            result[field] = value
        return result

    monkeypatch.setattr(assessment.audit, "_metadata", metadata)
    reached = []
    with pytest.raises(assessment.audit.Refusal, match="current_source_metadata_changed"):
        assessment._guarded_consume(root, expected, lambda: reached.append(True), secure_snapshot)
    assert reached == []


@pytest.mark.parametrize("target,mode", [("anchor", 0o755), ("root", 0o777), ("package", 0o755)])
def test_current_directory_modes_are_not_inferred_from_file_hashes(scoped_source, target, mode):
    root, source, expected = scoped_source
    path = {"anchor": root.parent, "root": root, "package": source.parent}[target]
    path.chmod(mode)
    reached = []
    with pytest.raises(assessment.audit.Refusal, match="current_directory_security"):
        assessment._guarded_consume(root, expected, lambda: reached.append(True), secure_snapshot)
    assert reached == []


def test_changed_source_security_snapshot_blocks_even_unchanged_bytes(scoped_source):
    root, _source, expected = scoped_source
    counts = {}

    def snapshot(fd):
        info = os.fstat(fd)
        counts[info.st_ino] = counts.get(info.st_ino, 0) + 1
        result = secure_snapshot(fd)
        if stat.S_ISREG(info.st_mode) and counts[info.st_ino] > 1:
            result["xattrs"] = {"synthetic.attribute": {"size": 1, "sha256": "1" * 64}}
        return result

    with pytest.raises(assessment.audit.Refusal, match="source_security_changed_across_consumer"):
        assessment._guarded_consume(root, expected, lambda: {}, snapshot)


def test_changed_directory_security_snapshot_blocks_unchanged_sources(scoped_source):
    root, source, expected = scoped_source
    target_inode = source.parent.stat().st_ino
    counts = {}

    def snapshot(fd):
        inode = os.fstat(fd).st_ino
        counts[inode] = counts.get(inode, 0) + 1
        result = secure_snapshot(fd)
        if inode == target_inode and counts[inode] > 1:
            result["acl_empty"] = False
        return result

    with pytest.raises(assessment.audit.Refusal, match="directory_security_changed_across_consumer"):
        assessment._guarded_consume(root, expected, lambda: {}, snapshot)


def test_security_observation_failure_never_reaches_consumer(scoped_source):
    root, _source, expected = scoped_source
    reached = []

    def snapshot(_fd):
        raise assessment.security.Refusal("synthetic security failure")

    with pytest.raises(assessment.security.Refusal):
        assessment._guarded_consume(root, expected, lambda: reached.append(True), snapshot)
    assert reached == []


def test_named_source_swap_is_refused_after_consumer(scoped_source):
    root, source, expected = scoped_source

    def consume():
        replacement = source.with_name("replacement.bin")
        replacement.write_bytes(source.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, source)
        return {}

    with pytest.raises(assessment.audit.Refusal, match="source_changed_across_consumer"):
        assessment._guarded_consume(root, expected, consume, secure_snapshot)


def test_source_change_and_restore_cannot_reuse_matching_hash(scoped_source):
    root, source, expected = scoped_source
    initial = source.stat()
    raw = source.read_bytes()

    def consume():
        source.write_bytes(b"different-buffer\n")
        source.write_bytes(raw)
        os.utime(source, ns=(initial.st_atime_ns, initial.st_mtime_ns))
        return {}

    with pytest.raises(assessment.audit.Refusal, match="source_changed_across_consumer"):
        assessment._guarded_consume(root, expected, consume, secure_snapshot)
    assert source.read_bytes() == raw
    assert source.stat().st_mtime_ns == initial.st_mtime_ns
    assert source.stat().st_ctime_ns != initial.st_ctime_ns


@pytest.mark.parametrize("field", ["ctime_ns", "flags", "mode", "gid", "nlink"])
def test_fresh_consumer_never_waives_metadata_drift(scoped_source, monkeypatch, field):
    root, source, expected = scoped_source
    original = assessment.audit._metadata
    inode = source.stat().st_ino
    consumed = False

    def metadata(info):
        result = original(info)
        if consumed and info.st_ino == inode:
            result[field] += 1
        return result

    def consume():
        nonlocal consumed
        consumed = True
        return {}

    monkeypatch.setattr(assessment.audit, "_metadata", metadata)
    with pytest.raises(assessment.audit.Refusal, match="source_changed_across_consumer"):
        assessment._guarded_consume(root, expected, consume, secure_snapshot)


def test_parent_directory_drift_during_consumer_is_refused(scoped_source):
    root, source, expected = scoped_source

    def consume():
        source.parent.chmod(0o755)
        return {}

    with pytest.raises(assessment.audit.Refusal, match="directory_changed_across_consumer"):
        assessment._guarded_consume(root, expected, consume, secure_snapshot)


def test_source_drift_during_security_read_is_refused_before_consumer(scoped_source, monkeypatch):
    root, source, expected = scoped_source
    original = assessment.audit._metadata
    inode = source.stat().st_ino
    changed = False
    reached = []

    def metadata(info):
        result = original(info)
        if changed and info.st_ino == inode:
            result["ctime_ns"] += 1
        return result

    def snapshot(fd):
        nonlocal changed
        if os.fstat(fd).st_ino == inode:
            changed = True
        return secure_snapshot(fd)

    monkeypatch.setattr(assessment.audit, "_metadata", metadata)
    with pytest.raises(assessment.audit.Refusal, match="source_changed_during_initial_read"):
        assessment._guarded_consume(root, expected, lambda: reached.append(True), snapshot)
    assert reached == []


def test_directory_drift_during_security_read_is_refused_before_consumer(scoped_source, monkeypatch):
    root, _source, expected = scoped_source
    original = assessment.audit._metadata
    inode = root.parent.stat().st_ino
    changed = False
    reached = []

    def metadata(info):
        result = original(info)
        if changed and info.st_ino == inode:
            result["ctime_ns"] += 1
        return result

    def snapshot(fd):
        nonlocal changed
        if os.fstat(fd).st_ino == inode:
            changed = True
        return secure_snapshot(fd)

    monkeypatch.setattr(assessment.audit, "_metadata", metadata)
    with pytest.raises(assessment.audit.Refusal, match="directory_changed_during_security_read"):
        assessment._guarded_consume(root, expected, lambda: reached.append(True), snapshot)
    assert reached == []


@pytest.fixture
def historical_pair(scoped_source, monkeypatch):
    _root, _source, expected = scoped_source
    monkeypatch.setattr(assessment, "PACKAGES", {"package": ("source.bin",)})
    before = {"census": {"entries": deepcopy(expected)}, "complete": True}
    after = {"census": {"entries": deepcopy(expected)}, "complete": True, "matches_before": False}
    after["census"]["entries"]["package/source.bin"]["metadata"]["ctime_ns"] += 1
    return before, after


def test_scope_retains_failed_historical_result_and_only_qualifies_old_ctime(historical_pair):
    before, after = historical_pair
    original_before, original_after = deepcopy(before), deepcopy(after)
    expected = assessment._scope(before, after)
    assert expected == after["census"]["entries"]
    assert before == original_before
    assert after == original_after
    assert after["matches_before"] is False


@pytest.mark.parametrize("field", ["size", "dev", "ino", "mode", "uid", "gid", "nlink", "mtime_ns", "flags"])
def test_scope_refuses_other_historical_metadata_changes(historical_pair, field):
    before, after = historical_pair
    after["census"]["entries"]["package/source.bin"]["metadata"][field] += 1
    with pytest.raises(assessment.audit.Refusal, match="historical_source_metadata"):
        assessment._scope(before, after)


def test_scope_refuses_backwards_ctime(historical_pair):
    before, after = historical_pair
    after["census"]["entries"]["package/source.bin"]["metadata"]["ctime_ns"] = 0
    with pytest.raises(assessment.audit.Refusal, match="historical_source_metadata"):
        assessment._scope(before, after)


def test_scope_refuses_historical_content_change(historical_pair):
    before, after = historical_pair
    after["census"]["entries"]["package/source.bin"]["sha256"] = "0" * 64
    with pytest.raises(assessment.audit.Refusal, match="historical_source_bytes"):
        assessment._scope(before, after)


@pytest.mark.parametrize("size", [0, assessment.MAX_SOURCE_BYTES + 1])
def test_scope_bounds_each_source_size(historical_pair, size):
    before, after = historical_pair
    for report in (before, after):
        report["census"]["entries"]["package/source.bin"]["metadata"]["size"] = size
    with pytest.raises(assessment.audit.Refusal, match="source_byte_limit"):
        assessment._scope(before, after)


def test_historical_ctime_exception_is_not_a_fresh_current_exception(scoped_source, historical_pair):
    root, _source, _expected = scoped_source
    expected = assessment._scope(*historical_pair)
    reached = []
    with pytest.raises(assessment.audit.Refusal, match="current_source_metadata_changed"):
        assessment._guarded_consume(root, expected, lambda: reached.append(True), secure_snapshot)
    assert reached == []


@pytest.fixture
def pinned_reports(scoped_source, monkeypatch):
    root, _source, _expected = scoped_source
    directory = root / assessment.audit.OUTPUT
    directory.mkdir(parents=True, mode=0o700)
    reports = {}
    for stage in ("before", "after"):
        report = {"schema": assessment.audit.SCHEMA, "stage": stage, "complete": True}
        if stage == "after":
            report["matches_before"] = False
        reports[stage] = report

    def publish():
        for stage, report in reports.items():
            raw = assessment.audit._json_bytes(report)
            (directory / (stage + ".json")).write_bytes(raw)
            monkeypatch.setattr(assessment, stage.upper() + "_SHA", hashlib.sha256(raw).hexdigest())

    publish()
    return root, directory, reports, publish


def test_pinned_reports_authenticate_before_parsing_and_retain_failure(pinned_reports):
    root, _directory, reports, _publish = pinned_reports
    assert assessment._read_pinned_reports(root) == [reports["before"], reports["after"]]
    assert assessment._read_pinned_reports(root)[1]["matches_before"] is False


def test_pinned_report_changed_bytes_are_rejected_before_json_parse(pinned_reports):
    root, directory, _reports, _publish = pinned_reports
    (directory / "before.json").write_bytes(b"not-json-synthetic-tamper")
    with pytest.raises(assessment.audit.Refusal, match="historical_report_digest"):
        assessment._read_pinned_reports(root)


@pytest.mark.parametrize("stage,field,value,code", [
    ("before", "schema", "different-schema", "historical_report_contract"),
    ("after", "stage", "before", "historical_report_contract"),
    ("before", "complete", False, "historical_report_contract"),
    ("after", "matches_before", True, "historical_refusal_must_remain"),
])
def test_pinned_report_digest_does_not_replace_contract(pinned_reports, stage, field, value, code):
    root, _directory, reports, publish = pinned_reports
    reports[stage][field] = value
    publish()
    with pytest.raises(assessment.audit.Refusal, match=code):
        assessment._read_pinned_reports(root)


@pytest.fixture
def main_scope(scoped_source, monkeypatch):
    root, _source, expected = scoped_source
    parent = root / "reports"
    parent.mkdir(mode=0o700)
    output = parent / "exclusive-assessment"
    monkeypatch.setattr(assessment, "ROOT", root)
    monkeypatch.setattr(assessment, "OUTPUT", output)
    monkeypatch.setattr(assessment, "__file__", str(root / "scripts" / "synthetic_assessment.py"))
    monkeypatch.chdir(root)
    monkeypatch.setattr(assessment, "_read_pinned_reports", lambda _root: ({}, {}))
    monkeypatch.setattr(assessment, "_scope", lambda _before, _after: expected)
    monkeypatch.setattr(assessment.security, "snapshot", secure_snapshot)
    monkeypatch.setattr(assessment, "_load_sources", lambda: {"synthetic": True})
    return root, output


def test_main_success_is_exclusive_and_does_not_admit_history(main_scope, capsys):
    _root, output = main_scope
    assert assessment.main() == 0
    report_path = output / "report.json"
    raw = report_path.read_bytes()
    report = json.loads(raw)
    assert report["complete"] is True
    assert report["source_reauthenticated"] is True
    for key in ("historical_audit_accepted", "historical_security_equivalence",
                "continuous_stability_proven", "all_worktree_artifacts_executable",
                "formal_admission", "production_publication_authorized", "provider_or_qc_contact"):
        assert report[key] is False
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert stat.S_IMODE(report_path.stat().st_mode) == 0o600
    assert hashlib.sha256(raw).hexdigest() in capsys.readouterr().out
    with pytest.raises(FileExistsError):
        assessment.main()
    assert report_path.read_bytes() == raw


def test_main_failure_retains_spent_report_without_private_exception(main_scope, monkeypatch, capsys):
    _root, output = main_scope

    def consume():
        raise ValueError("PRIVATE-SYNTHETIC-EXCEPTION-MUST-NOT-PERSIST")

    monkeypatch.setattr(assessment, "_load_sources", consume)
    assert assessment.main() == 1
    raw = (output / "report.json").read_bytes()
    report = json.loads(raw)
    assert report["complete"] is False
    assert report["source_reauthenticated"] is False
    assert report["refusal_type"] == "ValueError"
    assert report["refusal_code"] == "current_security_or_source_refused"
    assert b"PRIVATE-SYNTHETIC" not in raw
    assert "PRIVATE-SYNTHETIC" not in capsys.readouterr().out
    with pytest.raises(FileExistsError):
        assessment.main()
    assert (output / "report.json").read_bytes() == raw


def test_main_security_refusal_is_coded_without_attribute_values(main_scope, monkeypatch):
    _root, output = main_scope

    def snapshot(_fd):
        raise assessment.security.Refusal("extended ACL entry present")

    monkeypatch.setattr(assessment.security, "snapshot", snapshot)
    assert assessment.main() == 1
    report = json.loads((output / "report.json").read_bytes())
    assert report["refusal_code"] == "acl_entry_present"
    assert report["complete"] is False
    assert report["source_reauthenticated"] is False


def test_main_foreign_output_entry_is_not_allowed_as_own_publication(main_scope, monkeypatch):
    _root, output = main_scope

    def consume():
        (output / "foreign-synthetic-entry").write_bytes(b"retain")
        return {}

    monkeypatch.setattr(assessment, "_load_sources", consume)
    with pytest.raises(assessment.audit.Refusal):
        assessment.main()
    assert (output / "foreign-synthetic-entry").read_bytes() == b"retain"
    assert not (output / "report.json").exists()


def test_main_named_output_directory_swap_is_refused(main_scope, monkeypatch):
    _root, output = main_scope
    retained = output.with_name("retained-original")

    def consume():
        output.rename(retained)
        output.mkdir(mode=0o700)
        return {}

    monkeypatch.setattr(assessment, "_load_sources", consume)
    with pytest.raises(assessment.audit.Refusal, match="assessment_directory_changed"):
        assessment.main()
    assert retained.exists()
    assert output.exists()
    assert not (output / "report.json").exists()
    assert not (retained / "report.json").exists()


def test_main_postpublication_foreign_entry_is_refused_and_retained(main_scope, monkeypatch):
    _root, output = main_scope
    original = assessment.audit._publish_report

    def publish(fd, name, raw):
        digest = original(fd, name, raw)
        (output / "foreign-after-publication").write_bytes(b"retain")
        return digest

    monkeypatch.setattr(assessment.audit, "_publish_report", publish)
    with pytest.raises(assessment.audit.Refusal):
        assessment.main()
    assert (output / "foreign-after-publication").read_bytes() == b"retain"
    assert (output / "report.json").is_file()


@pytest.mark.parametrize("field", ["mode", "flags"])
def test_main_postpublication_security_drift_is_not_own_nlink_change(main_scope, monkeypatch, field):
    _root, output = main_scope
    original_publish = assessment.audit._publish_report
    original_metadata = assessment.audit._directory_metadata
    published_inode = None

    def publish(fd, name, raw):
        nonlocal published_inode
        digest = original_publish(fd, name, raw)
        published_inode = os.fstat(fd).st_ino
        return digest

    def metadata(info):
        values = original_metadata(info)
        if info.st_ino == published_inode:
            values[field] ^= 0o040 if field == "mode" else stat.UF_TRACKED
        return values

    monkeypatch.setattr(assessment.audit, "_publish_report", publish)
    monkeypatch.setattr(assessment.audit, "_directory_metadata", metadata)
    with pytest.raises(assessment.audit.Refusal, match="assessment_directory_changed"):
        assessment.main()
    assert (output / "report.json").is_file()


@pytest.mark.parametrize("wrong", ["cwd", "module"])
def test_main_wrong_root_refuses_before_output_allocation(main_scope, monkeypatch, wrong):
    root, output = main_scope
    if wrong == "cwd":
        monkeypatch.chdir(root.parent)
    else:
        monkeypatch.setattr(assessment, "__file__", str(root.parent / "scripts" / "wrong.py"))
    with pytest.raises(assessment.audit.Refusal, match="fixed_root_required"):
        assessment.main()
    assert not output.exists()
