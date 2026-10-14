"""Synthetic lifecycle CLI seams only; no private inputs or credentials."""
import json
import sys
import time
from types import SimpleNamespace

import pytest

from scripts import run_arv2_newrule_comparison as d

HEAD, SHA = "a" * 40, "b" * 64
REAL_OPERATION = d._operation


def args(operation="prepare", **changes):
    value = dict(operation=operation, candidate=None, attempt=None,
        expected_head=HEAD, caller_sha256=SHA, family_sha256=None,
        prior_failure_sha256=None, justification_sha256=None)
    value.update(changes)
    return SimpleNamespace(**value)


@pytest.fixture(autouse=True)
def no_real_operation(monkeypatch):
    monkeypatch.setattr(d, "_operation", lambda *_a: pytest.fail("real operation forbidden"))
    monkeypatch.setattr(d.subprocess, "run", lambda *_a, **_k: pytest.fail("real git forbidden"))


def preflight_fixtures(monkeypatch, mutation=None):
    monkeypatch.setattr(d, "SOURCE_PINS", {} if mutation == "empty" else
        {f"synthetic-{i}.py": SHA for i in range(20)})
    monkeypatch.setattr(d, "NEW_SOURCE_PINS", {f"new-{i}.py": SHA for i in range(5)})
    observations = [str(d.ROOT), d.BRANCH, HEAD, ""]
    if mutation in ("root", "branch", "head", "dirty"):
        observations[("root", "branch", "head", "dirty").index(mutation)] = "mismatch"
    monkeypatch.setattr(d.subprocess, "run", lambda *_a, **_k: SimpleNamespace(
        stdout=(observations.pop(0) + "\n").encode("ascii"),
        stderr=b"private command text" if mutation == "stderr" else b"",
        returncode=1 if mutation == "returncode" else 0))
    monkeypatch.setattr(d.helpers, "_source_digest", lambda path:
        "c"*64 if (mutation == "caller" and path == d.SOURCE
                   or mutation == "pin" and path != d.SOURCE) else SHA)


@pytest.mark.parametrize("mutation", [None, "empty", "root", "branch", "head", "dirty", "stderr", "returncode", "caller", "pin"])
def test_exact_host_head_source_preflight(monkeypatch, mutation):
    preflight_fixtures(monkeypatch, mutation)
    if mutation is None:
        d._preflight(args(), time.monotonic() + 10)
    else:
        with pytest.raises(ValueError):
            d._preflight(args(), time.monotonic() + 10)


@pytest.mark.parametrize("operation", tuple(d.DEADLINES))
def test_exact_action_geometry(monkeypatch, operation):
    preflight_fixtures(monkeypatch)
    extra = {} if operation == "prepare" else {"family_sha256": SHA}
    if operation in ("begin", "compile", "launch", "status", "read"):
        extra.update(candidate="R298", attempt=1)
    d._preflight(args(operation, **extra), time.monotonic() + 10)


@pytest.mark.parametrize("change", [
    {"candidate": "R297"}, {"candidate": "R298"}, {"attempt": 1},
    {"family_sha256": SHA}, {"prior_failure_sha256": SHA},
    {"justification_sha256": SHA}])
def test_prepare_cannot_smuggle_other_action_bindings(monkeypatch, change):
    preflight_fixtures(monkeypatch)
    with pytest.raises(ValueError):
        d._preflight(args(**change), time.monotonic() + 10)


@pytest.mark.parametrize("attempt,prior,justification,accepted", [
    (1,None,None,True), (2,None,None,False), (3,None,None,False),
    (2,SHA,SHA,True), (3,SHA,SHA,True), (4,SHA,SHA,False),
    (1,SHA,SHA,False), (2,SHA,None,False), (2,None,SHA,False)])
def test_new_attempt_requires_bound_failed_prior_and_justification(monkeypatch, attempt, prior, justification, accepted):
    preflight_fixtures(monkeypatch)
    value = args("begin", candidate="R298", attempt=attempt, family_sha256=SHA,
        prior_failure_sha256=prior, justification_sha256=justification)
    if accepted:
        d._preflight(value, time.monotonic() + 10)
    else:
        with pytest.raises(ValueError):
            d._preflight(value, time.monotonic() + 10)


def test_failure_prevents_operation_and_never_emits_command_text(monkeypatch, capsys):
    preflight_fixtures(monkeypatch, "stderr")
    assert d.run(args()) == 2
    output = capsys.readouterr().out
    assert "private command text" not in output
    assert json.loads(output)["stage"] == "preflight"


def test_operation_exit_is_not_backtest_or_formal_success(monkeypatch, capsys):
    preflight_fixtures(monkeypatch)
    monkeypatch.setattr(d, "_operation", lambda *_a: {"synthetic_only": True})
    assert d.run(args()) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["operation_completed"] is True
    for key in ("formal_forward_ready", "point_in_time_proven", "paper_or_live_ready"):
        assert value[key] is False
    assert "assistant.dispatch_fence" not in sys.modules


def test_unknown_opaque_failure_is_never_rendered(monkeypatch, capsys):
    class Opaque:
        def __str__(self):
            pytest.fail("str on private value")
        def __repr__(self):
            pytest.fail("repr on private value")
    preflight_fixtures(monkeypatch)
    def fail(*_a):
        raise RuntimeError(Opaque())
    monkeypatch.setattr(d, "_operation", fail)
    assert d.run(args()) == 2
    assert json.loads(capsys.readouterr().out)["failure_code"] == "unknown_exception"


def test_parent_deadline_prevents_late_positive_acceptance(monkeypatch, capsys):
    preflight_fixtures(monkeypatch)
    clock = time.monotonic
    def operation(*_a):
        monkeypatch.setattr(time, "monotonic", lambda: clock() + 1000)
        return {"synthetic_only": True}
    monkeypatch.setattr(d, "_operation", operation)
    assert d.run(args()) == 2
    value = json.loads(capsys.readouterr().out)
    assert value["operation_completed"] is False and "result" not in value


def test_bounded_output_refuses_before_console_publication(monkeypatch, capsys):
    preflight_fixtures(monkeypatch)
    monkeypatch.setattr(d, "_operation", lambda *_a: {"synthetic_only": "x" * d.MAX_OUTPUT_BYTES})
    assert d.run(args()) == 2
    assert "synthetic_only" not in capsys.readouterr().out


@pytest.mark.parametrize("operation,function", [
    ("prepare", "prepare_family"), ("organization", "discover_organization"),
    ("upload", "upload_inputs"), ("capacity", "capacity_once"),
    ("begin", "begin_attempt"), ("compile", "poll_compile_once"),
    ("launch", "launch_compiled"), ("status", "poll_status_once"),
    ("read", "read_result_once"), ("summarize", "summarize_family")])
def test_fixed_dispatch_authenticates_exact_new_input_before_lifecycle(monkeypatch, operation, function):
    from research.analyst_revisions_v2_qc import newrule_comparison_submission as submission
    observed, value, plan = [], object(), SimpleNamespace(family_sha256=SHA)
    monkeypatch.setattr(d, "SOURCE_PINS", {key: SHA for key in submission.HOST_SOURCE_NAMES})
    monkeypatch.setattr(d, "NEW_SOURCE_PINS", {"synthetic.py": SHA})
    def input_loader(path, **kwargs):
        assert path == d.PACKAGE
        assert kwargs == dict(expected_package_sha256=d.PACKAGE_SHA256,
            lineage_path=d.LINEAGE, expected_lineage_sha256=d.LINEAGE_SHA256)
        observed.append("input")
        return value
    monkeypatch.setattr(d.prepared_input.october, "load_october_order_input_package", input_loader)
    def load(source, **kwargs):
        assert source is value and observed == ["input"]
        assert kwargs["expected_family_sha256"] == SHA
        assert kwargs["expected_new_source_pins"] == {"synthetic.py": SHA}
        assert set(kwargs["expected_host_source_pins"]) == set(submission.HOST_SOURCE_NAMES)
        observed.append("load")
        return plan
    monkeypatch.setattr(submission, "load_family", load)
    for name in ("prepare_family", "discover_organization", "upload_inputs", "capacity_once",
                 "begin_attempt", "poll_compile_once", "launch_compiled", "poll_status_once",
                 "read_result_once", "summarize_family"):
        monkeypatch.setattr(submission, name, lambda *_a, **_k: pytest.fail("wrong lifecycle call"))
    def chosen(first, *pos, **kwargs):
        if operation == "prepare":
            assert first is value and observed == ["input"]
            assert kwargs["expected_new_source_pins"] == {"synthetic.py": SHA}
        else:
            assert first is plan and observed == ["input", "load"]
            assert kwargs["expected_family_sha256"] == SHA
            assert pos == (("R298", 1) if operation in ("begin", "compile", "launch", "status", "read") else ())
        observed.append(function)
        if operation == "prepare":
            return plan
        if operation == "read":
            result = {key: "synthetic" for key in ("family_sha256", "candidate_id", "attempt_id",
                "project_id", "backtest_id", "status", "cell_completed", "family_comparable", "result_cell")}
            result["statistics"] = {"monthly": {"months": ["not_console_output"]}, "meta": {
                "account_aggregates": {}, "common_source_path_sha256": SHA, "decision_count": 3,
                "evaluation_session_count": 5, "order_count": 2, "fill_count": 2,
                "coverage_fallback_counts": {}}}
            return result
        return {"synthetic": True}
    monkeypatch.setattr(submission, function, chosen)
    monkeypatch.setattr(submission, "require_family", lambda p, digest: {
        "cells": [dict(candidate_id="R298", projection_sha256=SHA, profile_sha256=SHA)],
        "upload_inventory_sha256": SHA})
    selected = args(operation, family_sha256=None if operation == "prepare" else SHA,
        candidate="R298" if operation in ("begin", "compile", "launch", "status", "read") else None,
        attempt=1 if operation in ("begin", "compile", "launch", "status", "read") else None)
    result = REAL_OPERATION(selected, time.monotonic() + 30)
    assert observed[-1] == function
    assert "not_console_output" not in json.dumps(result)


def test_refused_input_never_loads_family_or_contacts_qc(monkeypatch):
    from research.analyst_revisions_v2_qc import newrule_comparison_submission as submission
    def refused(*_a, **_k):
        raise ValueError("synthetic")
    monkeypatch.setattr(d.prepared_input.october, "load_october_order_input_package", refused)
    monkeypatch.setattr(submission, "load_family", lambda *_a, **_k: pytest.fail("family after refusal"))
    monkeypatch.setattr(submission, "_client", lambda: pytest.fail("credentials after refusal"))
    with pytest.raises(ValueError):
        REAL_OPERATION(args("organization", family_sha256=SHA), time.monotonic() + 10)


def test_finite_submission_failure_is_preserved():
    from research.analyst_revisions_v2_qc import newrule_comparison_submission as submission
    assert d._failure(submission.NewruleSubmissionError("capacity_wait"), submission) == "capacity_wait"
    assert d._failure(submission.NewruleSubmissionError("opaque private message"), submission) == "operation_refused"


def test_preflight_refusal_never_imports_unverified_submission(monkeypatch, capsys):
    import builtins
    preflight_fixtures(monkeypatch, "pin")
    original = builtins.__import__
    def guarded(name, globals=None, locals=None, fromlist=(), level=0):
        if "newrule_comparison_submission" in name or "newrule_comparison_submission" in fromlist:
            pytest.fail("unverified module import after preflight refusal")
        return original(name, globals, locals, fromlist, level)
    monkeypatch.setattr(builtins, "__import__", guarded)
    assert d.run(args()) == 2
    assert json.loads(capsys.readouterr().out)["failure_code"] == "operation_refused"
