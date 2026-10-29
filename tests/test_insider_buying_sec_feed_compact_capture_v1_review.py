"""Independent invented-only compact-front ordering review.

Run under native process-tree network/Keychain-exec denial with writes only
to a fresh registered pytest temporary root. No actual source or account IO.
"""
from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
from research import insider_buying_sec_feed_compact_capture_v1 as m


CONTACT = "invented-review@unit-test.org"


def test_review_worker_readback_rechecks_current_source_after_operation(monkeypatch):
    # Only source-order cutpoints are invented. The real _worker executes;
    # this is not a claim that fake callbacks prove production isolation.
    changed = False
    calls = []
    def current(identity):
        calls.append("source")
        if changed:
            raise m.CompactCaptureError("source_changed")
    def readback(*args, **kwargs):
        nonlocal changed
        calls.append("readback")
        changed = True
        return {"invented": True}
    class Memory:
        def check(self):
            calls.append("memory")
        def close(self):
            calls.append("close")
    monkeypatch.setattr(m.previous, "_isolated", lambda: calls.append("flags"))
    monkeypatch.setattr(m.source_runner, "_prove_isolation", lambda: calls.append("native"))
    monkeypatch.setattr(m.previous, "_WorkerMemoryGuard", Memory)
    monkeypatch.setattr(m, "_current", current)
    monkeypatch.setattr(m, "_verify_files", readback)
    header = m._raw({"contact": CONTACT, "report_sha256": "a"*64})+b"\n"
    monkeypatch.setattr(m.sys, "stdin", SimpleNamespace(buffer=BytesIO(header)))
    with pytest.raises(m.CompactCaptureError, match="source_changed"):
        m._worker("readback", {"invented": True})
    assert calls.index("readback") < len(calls)-1
    assert calls.count("source") >= 2
    assert calls[-1] == "close"


def test_review_actual_readback_parent_rechecks_exact_identity_before_return(monkeypatch):
    changed = False
    calls = []
    identity = {"invented_identity": True}
    plan = {"execution_identity": identity, "invented_plan": True}
    def current(head):
        calls.append("identity")
        if changed:
            raise m.CompactCaptureError("source_changed")
        return identity
    def child(role, supplied, payload=b""):
        nonlocal changed
        calls.append(role)
        assert supplied is identity
        if role == "preflight":
            return plan
        assert role == "readback"
        changed = True
        return {"producer_execution_identity": identity, "original_input_plan": plan,
            "invented_result": True}
    monkeypatch.setattr(m, "_identity", current)
    monkeypatch.setattr(m, "_child", child)
    monkeypatch.setattr(m, "_parent_plan_proofs", lambda value: calls.append("old-plan"))
    monkeypatch.setattr(m.previous, "_source_git", lambda value: calls.append("old-source"))
    monkeypatch.setattr(m.contact_io, "_stdin_contact", lambda: CONTACT)
    with pytest.raises(m.CompactCaptureError, match="source_changed"):
        m.verify_actual(expected_head="a"*40, expected_report_sha256="b"*64)
    assert calls.count("identity") == 2
    assert calls[-1] == "identity"


def test_review_real_identity_builder_inherits_string_named_tests_and_pure_review(monkeypatch):
    # This exercises the REAL qualified inheritance/guards against only Python
    # source bytes. The emulated Git view is NOT a clean committed-state proof.
    campaign = m.batch.campaign
    omitted = {campaign.first.TEST_PATH, campaign.archive.TEST_PATH}
    paths = set(m.custody._internal_source_paths(m.LANE_ROOT))-omitted
    sources = m.custody._source_bytes(m.LANE_ROOT, tuple(sorted(paths)))
    generic = {"root": str(m.LANE_ROOT), "branch": m.LANE_BRANCH, "head": "a"*40,
        "clean": True, "source_sha256": sources,
        "source_inventory_sha256": m._sha(m._raw(sources))}
    monkeypatch.setattr(m.previous, "_isolated", lambda: None)
    monkeypatch.setattr(m.custody, "_identity", lambda head: generic.copy())
    def show(root, *args):
        assert root == m.LANE_ROOT and args[0] == "show"
        assert args[1].startswith("a"*40+":")
        return (root/args[1].split(":", 1)[1]).read_bytes()
    monkeypatch.setattr(m.custody, "_git", show)
    identity = m._identity("a"*40)
    campaign._current(identity)
    assert omitted | {m.SELF_PATH, m.TEST_PATH, m.PURE_PATH,
        m.PURE_TEST_PATH, m.PURE_REVIEW_TEST_PATH} <= set(identity["source_sha256"])
