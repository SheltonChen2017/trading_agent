"""Invented controls only; never load actual retained artifacts or credentials."""
from __future__ import annotations

import copy
import gzip
import os
from pathlib import Path
import subprocess
import sys

import pytest

from research import insider_buying_pilot_sec_parent_audit_runner as m


@pytest.fixture(autouse=True)
def _isolate_root_report_from_separately_tested_summary_contract(monkeypatch):
    # Root-envelope fixtures intentionally contain only invented small stubs.
    # The real 25-quarter crosslink contract has its own exhaustive test file.
    monkeypatch.setattr(m.readback, "validate_summaries", lambda _: None)


def test_registration_has_no_transport_outcome_or_qc_scope():
    assert m.REGISTRATION["new_provider_requests"] == 0
    assert m.REGISTRATION["credential_reads"] == 0
    assert m.REGISTRATION["worker_invocations"] == 1
    assert not m.REGISTRATION["qc_access"]
    assert not m.REGISTRATION["outcome_access"]
    assert not m.REGISTRATION["backtest_readiness_granted"]
    assert m.REGISTRATION["source_tables_interpreted"] == ["SUBMISSION.tsv"]
    assert m.REGISTRATION["stopped_v3_ambiguity_preserved"]


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'[]', b'{ "a":1}', b'{"a":1}\n'])
def test_control_refuses_duplicates_nonfinite_and_unframed(raw):
    with pytest.raises((m.PilotParentRunnerError, ValueError)):
        m._decode(raw)


def test_invented_control_roundtrip():
    body = {"field": ["invented", 1, False]}
    assert m._decode(m._raw(body)) == body


def _guard():
    command = ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin", sys.executable, "-c", "pass")
    return m._ParentGuard("a" * 40, command), command


def test_parent_guard_allows_exact_one_worker_only():
    guard, command = _guard()
    args = (command[0], command, m.LANE_ROOT, None)
    guard("subprocess.Popen", args)
    with pytest.raises(m.PilotParentRunnerError, match="child_refused"):
        guard("subprocess.Popen", args)


@pytest.mark.parametrize("alter", [lambda c: ("/usr/bin/security", "help"), lambda c: (*c, "unexpected")])
def test_parent_guard_denies_other_processes(alter):
    guard, command = _guard()
    changed = alter(command)
    with pytest.raises(m.PilotParentRunnerError, match="child_refused"):
        guard("subprocess.Popen", (changed[0], changed, m.LANE_ROOT, None))


@pytest.mark.parametrize("event,args", [("socket.connect", ()), ("urllib.Request", ()),
    ("os.exec", ()), ("os.posix_spawn", ()), ("os.system", ()), ("os.fork", ())])
def test_trusted_parent_network_credential_and_unknown_exec_denied(event, args):
    guard, _ = _guard()
    with pytest.raises(PermissionError):
        guard(event, args)


@pytest.mark.parametrize("leaf", ["reservation.json", "terminal.json", "complete.json"])
def test_parent_guard_output_is_exact_three_leaves(leaf):
    guard, _ = _guard()
    guard._write(guard.output / leaf)
    for path in (guard.output / "source.bin", guard.output.parent / leaf, m.LANE_ROOT / "CLAUDE.md"):
        with pytest.raises(m.PilotParentRunnerError):
            guard._write(path)


def test_guard_git_stays_exact_lane_head_and_readonly():
    guard, _ = _guard()
    guard("subprocess.Popen", ("/usr/bin/git", ("/usr/bin/git", "rev-parse", "HEAD"), m.LANE_ROOT, {"PATH": "/usr/bin:/bin"}))
    for args in (("reset", "--hard"), ("show", "b" * 40 + ":research/fake.py")):
        with pytest.raises(m.PilotParentRunnerError):
            guard("subprocess.Popen", ("/usr/bin/git", ("/usr/bin/git", *args), m.LANE_ROOT, {"PATH": "/usr/bin:/bin"}))


def _master_fixture(monkeypatch):
    raw = (b"Description: Master Index of EDGAR Dissemination Feed\n"
        b"Last Data Received: March 31, 2023\nComments: webmaster@sec.gov\n\n"
        b"CIK|Company Name|Form Type|Date Filed|Filename\n--------------------------------------------------\n"
        b"1001|Invented Example|4|2023-02-10|edgar/data/987654/0000001001-23-000003.txt\n")
    receipt = m.parse_sec_quarter_master_index(raw, year=2023, quarter=1)
    compressed = gzip.compress(raw, mtime=0)
    digest = m._sha(compressed)
    row = {"period": "2023Q1", "source_url": "https://www.sec.gov/Archives/edgar/full-index/2023/QTR1/master.gz",
        "raw_object": {"sha256": digest, "relative_path": "objects/" + digest + ".bin", "size_bytes": len(compressed)},
        "receipt": {"decoded_sha256": m._sha(raw), "decoded_size_bytes": len(raw), "master_receipt_sha256": receipt.receipt_sha256}}
    report = {"master_indexes": [row, *({"period": "invented-" + str(i)} for i in range(81))]}
    report_raw = m._raw(report)
    commit_raw = m._raw({"report_name": "invented-report.json", "report_sha256": m._sha(report_raw)})
    monkeypatch.setattr(m.bootstrap, "MASTER_COMMIT_SHA256", m._sha(commit_raw))
    monkeypatch.setattr(m.bootstrap, "MASTER_REPORT_SHA256", m._sha(report_raw))
    leaves = {((), "commit.json"): commit_raw, ((), "invented-report.json"): report_raw,
        (("objects",), digest + ".bin"): compressed}
    class Tree:
        def read(self, parts, name, *, cap=None, expected=None):
            value = leaves[(parts, name)]
            assert expected == m._sha(value)
            return value
    return Tree(), row, report, leaves, receipt


def test_master_reparse_binds_decoded_receipt_and_exact_archive_path(monkeypatch):
    tree, row, report, leaves, receipt = _master_fixture(monkeypatch)
    result = m._master(tree, "2023Q1")
    assert result == receipt
    assert result.rows[0].archive_path.startswith("edgar/data/987654/")


@pytest.mark.parametrize("change", [lambda row: row.update(source_url="https://invalid.example/"),
    lambda row: row["raw_object"].update(relative_path="../object"),
    lambda row: row["raw_object"].update(size_bytes=0),
    lambda row: row["receipt"].update(decoded_sha256="f" * 64),
    lambda row: row["receipt"].update(master_receipt_sha256="f" * 64)])
def test_master_changed_identity_cannot_be_accepted(monkeypatch, change):
    tree, row, report, leaves, _ = _master_fixture(monkeypatch)
    change(row)
    report_raw = m._raw(report)
    commit_raw = m._raw({"report_name": "invented-report.json", "report_sha256": m._sha(report_raw)})
    leaves[((), "commit.json")] = commit_raw
    leaves[((), "invented-report.json")] = report_raw
    monkeypatch.setattr(m.bootstrap, "MASTER_COMMIT_SHA256", m._sha(commit_raw))
    monkeypatch.setattr(m.bootstrap, "MASTER_REPORT_SHA256", m._sha(report_raw))
    with pytest.raises(m.PilotParentRunnerError):
        m._master(tree, "2023Q1")


def test_cli_never_prints_private_exception(monkeypatch, capsys):
    def refusal(_):
        raise ValueError("private source text must not escape")
    monkeypatch.setattr(m, "run_actual", refusal)
    assert m.main(["--expected-head", "a" * 40]) == 2
    assert capsys.readouterr().out == '{"disposition":"pilot_sec_parent_audit_refused"}\n'


def _result():
    value = {key: 0 for key in ("new_provider_requests", "credential_reads", "qc_accesses", "outcome_looks", "backtests")}
    value.update({key: False for key in ("parent_financial_bodies_parsed", "original_parent_admission_established", "backtesting_ready")})
    value.update(schema=m.SCHEMA, audit_id=m.AUDIT_ID, execution_identity={"invented": True},
        registration=m.REGISTRATION, registration_sha256=m._sha(m._raw(m.REGISTRATION)),
        source_roster={"authority": {"source_authenticated": False}, "counts": {"invented": 1}},
        parent_audit={"context_counts": {"invented": 1}, "pilot_counts": {"invented": 1}},
        exposure_inventory_sha256="a" * 64, exposure_observer={"invented": True},
        retained_body_inventory={"authority": {"dispatch_enabled": False}}, accepted_selector_pilot_counts={"invented": 1},
        intake_context={"invented": True}, effective_native_network_fork_allwrite_denial=True,
        effective_native_credential_exec_denial=True)
    value["exposure_snapshot_sha256"] = m._sha(m._raw(value["exposure_observer"]))
    value["retained_body_inventory_sha256"] = m._sha(m._raw(value["retained_body_inventory"]))
    return value


def test_parent_validates_strict_worker_result():
    result = _result()
    assert m._validate_result(result, {"invented": True}) == result


def test_parent_does_not_skip_deep_summary_readback(monkeypatch):
    def refuse(_):
        raise m.readback.PilotParentReadbackError("invented_crosslink_refusal")
    monkeypatch.setattr(m.readback, "validate_summaries", refuse)
    with pytest.raises(m.readback.PilotParentReadbackError):
        m._validate_result(_result(), {"invented": True})


@pytest.mark.parametrize("change", [lambda v: v.update(unexpected=True), lambda v: v.update(credential_reads=False),
    lambda v: v.update(qc_accesses=1), lambda v: v.update(backtesting_ready=True),
    lambda v: v.update(effective_native_credential_exec_denial=False),
    lambda v: v.update(registration_sha256="b" * 64), lambda v: v.update(exposure_snapshot_sha256="b" * 64),
    lambda v: v["source_roster"]["authority"].update(source_authenticated=True)])
def test_parent_rejects_result_identity_authority_and_hash_laundering(change):
    value = copy.deepcopy(_result())
    change(value)
    with pytest.raises(m.PilotParentRunnerError):
        m._validate_result(value, {"invented": True})


def test_parent_publication_uses_terminal_completedprocess_not_a_dict(monkeypatch):
    """A control-only synthetic run catches orchestration errors pre-activation."""
    result = _result()
    identity = {"invented": True, "source_sha256": {m.SELF_PATH: "a" * 64}}
    result["execution_identity"] = identity
    monkeypatch.setattr(m.custody, "_identity", lambda _: identity)
    monkeypatch.setattr(m.sys, "addaudithook", lambda _: None)
    class Chain:
        def __init__(self, *args):self.fd = 123
        def recheck(self):pass
        def close(self):pass
    monkeypatch.setattr(m.custody, "_Chain", Chain)
    monkeypatch.setattr(m.os, "mkdir", lambda *a, **k: None)
    monkeypatch.setattr(m.os, "fstatvfs", lambda _: type("Disk", (), {"f_bavail": 1 << 32, "f_frsize": 4096})())
    published = {}
    class Publication:
        def __init__(self, chain):pass
        def publish(self, name, raw):
            assert name not in published
            published[name] = m._decode(raw)
            return m._sha(raw)
        def recheck(self, *, final=False):assert final
        def close(self):pass
    monkeypatch.setattr(m, "_Publication", Publication)
    def child(command, **kwargs):
        assert command[:2] == ("/usr/bin/env", "-i")
        assert "(deny network*)" in command[5]
        assert "-S" in command and "-I" in command and "-B" in command
        assert "pycache_prefix=" + m.EMPTY_CACHE_PREFIX in command
        assert kwargs["cwd"] == m.LANE_ROOT
        assert kwargs["env"] is None
        assert kwargs["cap"] == m.MAX_REPORT
        return subprocess.CompletedProcess(command, 0, m._raw(result) + b"\n", b"")
    monkeypatch.setattr(m.launcher, "run_child", child)
    receipt = m.run_actual("a" * 40)
    assert receipt["complete_sha256"] == m._sha(m._raw(result))
    assert set(published) == {"reservation.json", "terminal.json", "complete.json"}
    assert published["terminal.json"]["exit_code"] == 0
    assert published["terminal.json"]["success"] is True
    assert "args" not in published["terminal.json"]


def test_new_output_hold_rechecks_all_three_leaves_and_forbids_resume(tmp_path):
    os.chmod(tmp_path, 0o700)
    chain = m.custody._Chain(tmp_path, ())
    publication = m._Publication(chain, fixture_path=tmp_path)
    try:
        for name in ("reservation.json", "terminal.json", "complete.json"):
            if name == "terminal.json":
                with pytest.raises(m.PilotParentRunnerError, match="incomplete"):
                    publication.recheck(final=True)
            publication.publish(name, m._raw({"invented": name}))
        publication.recheck(final=True)
        with pytest.raises(m.PilotParentRunnerError):
            publication.publish("complete.json", b"{}")
        with pytest.raises(m.PilotParentRunnerError):
            m._Publication(chain, fixture_path=tmp_path)
    finally:
        publication.close()
        chain.close()


@pytest.mark.parametrize("change", ["content", "replacement", "mode", "extra"])
def test_new_output_continuous_hold_catches_changed_reservation(tmp_path, change):
    os.chmod(tmp_path, 0o700)
    chain = m.custody._Chain(tmp_path, ())
    publication = m._Publication(chain, fixture_path=tmp_path)
    try:
        publication.publish("reservation.json", b'{"invented":"a"}')
        path = tmp_path / "reservation.json"
        info = path.stat()
        if change == "content":
            path.write_bytes(b'{"invented":"b"}')
            os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
        elif change == "replacement":
            other = tmp_path / "replacement"
            other.write_bytes(path.read_bytes())
            os.chmod(other, 0o600)
            os.replace(other, path)
        elif change == "mode":
            os.chmod(path, 0o644)
        else:
            (tmp_path / "extra").write_bytes(b"invented")
        with pytest.raises((m.PilotParentRunnerError, ValueError)):
            publication.recheck()
    finally:
        publication.close()
        chain.close()


def test_new_output_ctime_only_mode_has_owner_and_mtime_not_ctime(tmp_path):
    os.chmod(tmp_path, 0o700)
    chain = m.custody._Chain(tmp_path, ())
    publication = m._Publication(chain, fixture_path=tmp_path)
    try:
        publication.publish("reservation.json", b'{"invented":true}')
        path = tmp_path / "reservation.json"
        os.chmod(path, 0o600)
        publication.recheck()
        assert publication.tree._version is m.selector.held_io._settled_version
        assert m.selector._HeldIntake.__doc__.startswith("Hold/recheck full namespace")
    finally:
        publication.close()
        chain.close()


def test_real_guard_call_stack_allows_only_known_child_stdin_devnull():
    # No new native sandbox: both test descendants inherit the initial test
    # process-tree denial. A separate interpreter contains the permanent hook.
    script = ("import sys;sys.path.insert(0," + repr(str(m.LANE_ROOT)) + ");"
        "from research import insider_buying_pilot_sec_parent_audit_runner as m;"
        "cmd=('/usr/bin/env','-i','PATH=/usr/bin:/bin',sys.executable,'-I','-S','-B','-c','print(123)');"
        "sys.addaudithook(m._ParentGuard('a'*40,cmd));"
        "r=m.launcher.run_child(cmd,cwd=m.LANE_ROOT,env=None,timeout=10,cap=1024);"
        "assert r.returncode==0 and r.stdout==b'123\\n' and r.stderr==b'';print('guard_control_probe_passed')")
    child = subprocess.run((sys.executable, "-I", "-S", "-B", "-c", script),
        capture_output=True, cwd=m.LANE_ROOT, env={"PATH": "/usr/bin:/bin"}, timeout=20)
    assert child.returncode == 0, child.stderr.decode()
    assert child.stdout == b"guard_control_probe_passed\n"
