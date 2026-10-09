"""Invented combined selections/parents only; inherited OS network denial."""
import json
import os
from pathlib import Path
import stat
import types

import pytest

from research import insider_buying_sec_recovery_v4_continuation_capture as m
from research import insider_buying_sec_recovery_v4_capture as old
from research import insider_buying_sec_recovery_v4_selection as original_selection
from research import insider_buying_sec_recovery_v4_combined as combined
from research.insider_buying_sec_complete_acquisition import SecHttpResult
from test_insider_buying_sec_recovery_v4_projection import parent, request


CONTACT = "invented-continuation-private@unit.test"
HEAD = "a" * 40


class Clock:
    def __init__(self): self.ns, self.sleeps = 0, []
    def now(self): return self.ns
    def sleep(self, seconds): self.sleeps.append(seconds); self.ns += round(seconds * 1e9)
    def utc(self): return "2026-10-07T12:00:00.000000+00:00"


def paths(tmp_path, name="invented-next-prefix"):
    base = tmp_path.resolve().joinpath(*old.ARTIFACT_PARTS)
    return base, base / "claims", base / "runs" / name


def selection(tmp_path, items):
    base, claims, _ = paths(tmp_path)
    if claims.exists():
        folder = old._Directory(claims)
        try: inventory = tuple(m._claim_inventory(folder))
        finally: folder.close()
    else: inventory = ()
    runs = tuple(sorted(p.name for p in (base / "runs").iterdir())) if (base / "runs").exists() else ()
    return combined.make_invented_combined_v4_selection(tuple(items), repository_head=HEAD,
        claim_inventory=inventory, known_run_inventory=runs)


def seed_prior(tmp_path):
    item = request(900)
    chosen = original_selection.make_invented_test_selection((item,), repository_head=HEAD)
    raw = parent(item)
    return old._run_invented_capture(chosen, "invented-prior-capture", root=tmp_path.resolve(),
        transport=lambda *args: SecHttpResult(200, (("Content-Length", str(len(raw))),), raw),
        contact_email=CONTACT, monotonic_ns=lambda: 0, clock=lambda: "2026-10-07T12:00:00.000000+00:00")


def run(tmp_path, *, items=None, chosen=None, name="invented-next-prefix", response=None, transport=None, **kwargs):
    items = (request(),) if items is None else tuple(items)
    chosen = selection(tmp_path, items) if chosen is None else chosen
    calls, clock = [], Clock()
    _, claims, output = paths(tmp_path, name)
    def fake(url, headers, cap):
        ordinal = len(calls); calls.append((url, clock.ns))
        assert headers == {"User-Agent": f"InsiderBuyingResearch-v4-continuation/1.0 ({CONTACT})",
            "Accept": "*/*", "Accept-Encoding": "identity", "Connection": "close"}
        assert cap == m.MAX_PARENT_BYTES
        assert len(list(claims.iterdir())) == chosen.to_payload()["claim_inventory_count"] + len(items)
        assert (output / f"request-{ordinal:03d}-start.json").is_file()
        clock.ns += 100_000_000
        if response is not None: return response
        raw = parent(items[ordinal]); return SecHttpResult(200, (("Content-Length", str(len(raw))),), raw)
    result = m._run_invented_capture(chosen, name, root=tmp_path.resolve(),
        transport=fake if transport is None else transport, contact_email=CONTACT,
        monotonic_ns=clock.now, sleep=clock.sleep, clock=clock.utc, **kwargs)
    return result, calls, clock, chosen


def verify(tmp_path, result, *, project=False):
    return m._verify_capture(result["capture_id"], result["report_sha256"], root=tmp_path.resolve(),
        observed=False, project_retained=project)


def test_separate_family_preserves_prior_claims_reserves_prefix_before_http_and_replays(tmp_path):
    seed_prior(tmp_path)
    base, claims, _ = paths(tmp_path)
    prior = {p.name: old._sha(p.read_bytes()) for p in claims.iterdir()}
    items = (request(1), request(2, "4/A"), request(3))
    result, calls, clock, chosen = run(tmp_path, items=items)
    assert [stamp for _, stamp in calls] == [0, 600_000_000, 1_200_000_000]
    assert clock.sleeps == [0.5, 0.5]
    assert result["batch_completed"] is True and result["sec_dispatches"] == 3
    assert result["selection_sha256"] == chosen.sha256
    assert result["authority"]["bounded_named_source_acquisition_scope"] is False
    assert {name: old._sha((claims / name).read_bytes()) for name in prior} == prior
    before = {str(p): old._sha(p.read_bytes()) for p in base.rglob("*") if p.is_file()}
    replay = verify(tmp_path, result, project=True)
    assert replay["independent_readonly_journal_replay"] is True
    assert replay["projection_counts"] == {"header_bound_retained": 3, "complete_parent_projected": 3,
        "complete_parent_grammar_quarantined": 0}
    assert replay["projection_rows_sha256"] == m._digest(replay["projection_rows"])
    assert [row["request_sha256"] for row in replay["projection_rows"]] == [row["request_sha256"] for row in chosen.to_payload()["requests"]]
    assert b"987654.321" not in m._raw(replay) and b"Invented Owner" not in m._raw(replay)
    assert before == {str(p): old._sha(p.read_bytes()) for p in base.rglob("*") if p.is_file()}
    for p in base.rglob("*"):
        if p.is_file():
            assert stat.S_IMODE(p.stat().st_mode) == 0o600 and p.stat().st_nlink == 1
            assert CONTACT.encode() not in p.read_bytes()
        else: assert stat.S_IMODE(p.stat().st_mode) == 0o700


def test_exact_256_bound_is_substantive_not_old_64_cap(tmp_path):
    result, calls, _, _ = run(tmp_path, items=tuple(request(i + 1) for i in range(256)))
    assert result["sec_dispatches"] == result["completed_request_bound_bodies"] == len(calls) == 256
    assert result["batch_completed"] is True


@pytest.mark.parametrize("status", [301, 302, 400, 401, 403, 429, 500, 502, 503, 504])
def test_every_non200_stops_once_all_claims_stay_consumed(tmp_path, status):
    result, calls, _, chosen = run(tmp_path, items=(request(1), request(2)), response=SecHttpResult(status, (), b""))
    assert len(calls) == result["sec_dispatches"] == 1 and result["reserved_not_attempted"] == 1
    assert result["completed_request_bound_bodies"] == 0 and not result["batch_completed"]
    replay = verify(tmp_path, result)
    assert replay["complete_parent_projection_evaluated"] is False and replay["projection_rows"] is None
    with pytest.raises(m.ContinuationCaptureError):
        m._run_invented_capture(chosen, "later-id", root=tmp_path.resolve(), transport=lambda *args: pytest.fail("No retry"))


def test_timeout_claim_consumed_no_exception_text_or_contact(tmp_path):
    def failed(*args): raise TimeoutError(CONTACT)
    result, _, _, chosen = run(tmp_path, transport=failed)
    attempt = json.loads((paths(tmp_path)[2] / "request-000-result.json").read_bytes())
    assert attempt["disposition"] == "ambiguous_transport_failure" and attempt["status"] is None
    assert CONTACT not in json.dumps(result) and "Timeout" not in json.dumps(attempt)
    with pytest.raises(m.ContinuationCaptureError):
        m._run_invented_capture(chosen, "new-id", root=tmp_path.resolve(), transport=lambda *args: pytest.fail("No redispatch"))


def test_crash_after_start_never_resume_or_retry(tmp_path):
    chosen = selection(tmp_path, (request(),))
    def crashed(*args): raise SystemExit("invented crash")
    with pytest.raises(SystemExit): run(tmp_path, chosen=chosen, transport=crashed)
    output = paths(tmp_path)[2]
    assert (output / "request-000-start.json").exists() and not (output / "complete.json").exists()
    with pytest.raises(m.ContinuationCaptureError):
        m._run_invented_capture(chosen, "after-crash", root=tmp_path.resolve(), transport=lambda *args: pytest.fail("No resume"))


@pytest.mark.parametrize("change", ["claim", "run", "claim-bytes"])
def test_entire_combined_inventory_change_refuses_before_new_reservation(tmp_path, change):
    seed_prior(tmp_path); chosen = selection(tmp_path, (request(),))
    base, claims, output = paths(tmp_path)
    if change == "claim":
        leaf = claims / ("e" * 64 + ".json"); leaf.write_bytes(b"unknown\n"); leaf.chmod(0o600)
    elif change == "run": (base / "runs" / "ambiguous-extra").mkdir(mode=0o700)
    else: next(claims.iterdir()).write_bytes(b"changed-known-claim\n")
    with pytest.raises(m.ContinuationCaptureError, match="snapshot changed"):
        run(tmp_path, chosen=chosen, transport=lambda *args: pytest.fail("No dispatch"))
    assert not output.exists()


def test_old_first_prefix_family_cannot_enter_new_real_or_invented_capture(tmp_path):
    chosen = original_selection.make_invented_test_selection((request(),))
    with pytest.raises(m.ContinuationCaptureError, match="separately versioned"):
        m.run_observed_continuation_capture(chosen, "wrong-family", expected_head=HEAD, contact_email=CONTACT)
    with pytest.raises(m.ContinuationCaptureError, match="separately versioned"):
        m._run_invented_capture(chosen, "wrong-family", root=tmp_path.resolve(), transport=lambda *args: pytest.fail("No dispatch"))
    assert not paths(tmp_path)[0].exists()


@pytest.mark.parametrize("contact", ["bad", "a\r\n@host.com", True])
def test_contact_shape_fails_before_journal(tmp_path, contact):
    chosen = selection(tmp_path, (request(),))
    with pytest.raises((m.ContinuationCaptureError, old.FreshV4CaptureError)):
        m._run_invented_capture(chosen, "no-contact", root=tmp_path.resolve(), contact_email=contact,
            transport=lambda *args: pytest.fail("No dispatch"))
    assert not paths(tmp_path)[0].exists()


@pytest.mark.parametrize("encoded", [CONTACT, "\\u0069" + CONTACT[1:], CONTACT.replace("@", "%2540")])
def test_contact_echo_refuses_before_body_persistence(tmp_path, encoded):
    raw = parent(request()).replace(b"987654.321", encoded.encode())
    result, calls, _, _ = run(tmp_path, response=SecHttpResult(200, (("Content-Length", str(len(raw))),), raw))
    assert len(calls) == 1 and result["completed_request_bound_bodies"] == 0
    assert not list((paths(tmp_path)[2] / "objects").iterdir())


def test_storage_failure_not_misreported_as_invalid_source(tmp_path, monkeypatch):
    original = old._Directory.publish
    def failure(folder, name, raw, **kwargs):
        if name.endswith(".bin"): raise OSError("invented storage failure")
        return original(folder, name, raw, **kwargs)
    monkeypatch.setattr(old._Directory, "publish", failure)
    with pytest.raises(OSError): run(tmp_path)
    assert (paths(tmp_path)[2] / "request-000-start.json").exists()
    assert not (paths(tmp_path)[2] / "request-000-result.json").exists()


def test_final_report_readback_is_not_omitted(tmp_path, monkeypatch):
    original = old._Directory.publish
    def substituted(folder, name, raw, **kwargs):
        sha = original(folder, name, raw, **kwargs)
        if name == "complete.json": (folder.path / name).write_bytes(b"changed-final\n")
        return sha
    monkeypatch.setattr(old._Directory, "publish", substituted)
    with pytest.raises(m.ContinuationCaptureError, match="durable continuation"):
        run(tmp_path)


@pytest.mark.parametrize("leaf", ["complete.json", "reservation.json", "request-000-start.json", "request-000-result.json", "claim", "object"])
def test_independent_verifier_rejects_any_custody_tamper(tmp_path, leaf):
    result, _, _, _ = run(tmp_path)
    _, claims, output = paths(tmp_path)
    path = next(claims.iterdir()) if leaf == "claim" else next((output / "objects").iterdir()) if leaf == "object" else output / leaf
    path.write_bytes(b"tampered\n")
    with pytest.raises((m.ContinuationCaptureError, old.FreshV4CaptureError, ValueError)):
        verify(tmp_path, result)


@pytest.mark.parametrize("mutation", ["bool-count", "authority-int", "extra-key", "batch-int"])
def test_reanchored_report_schema_types_stay_exact(tmp_path, mutation):
    result, _, _, _ = run(tmp_path); path = paths(tmp_path)[2] / "complete.json"
    body = json.loads(path.read_bytes())
    if mutation == "bool-count": body["sec_dispatches"] = True
    elif mutation == "authority-int": body["authority"]["rights_verified"] = 0
    elif mutation == "extra-key": body["canonical_ready"] = True
    else: body["batch_completed"] = 1
    raw = m._raw(body); path.write_bytes(raw); result["report_sha256"] = old._sha(raw)
    with pytest.raises(m.ContinuationCaptureError): verify(tmp_path, result)


def test_projection_grammar_failure_named_not_zero_or_dropped(tmp_path):
    item = request(); raw = parent(item, xml="unsupported\n")
    result, _, _, _ = run(tmp_path, response=SecHttpResult(200, (("Content-Length", str(len(raw))),), raw))
    replay = verify(tmp_path, result, project=True)
    assert replay["projection_counts"] == {"header_bound_retained": 1, "complete_parent_projected": 0,
        "complete_parent_grammar_quarantined": 1}
    assert replay["projection_rows"][0]["disposition"] == "complete_parent_grammar_quarantine"
    assert replay["batch_completed"] is True and all(value is False for value in replay["authority"].values() if type(value) is bool)


def test_exact_private_inventory_and_symlink_refusal(tmp_path):
    base, _, _ = paths(tmp_path); base.mkdir(parents=True, mode=0o700)
    outside = tmp_path / "outside"; outside.mkdir(mode=0o700)
    (base / "claims").symlink_to(outside, target_is_directory=True)
    with pytest.raises((m.ContinuationCaptureError, OSError)):
        run(tmp_path, transport=lambda *args: pytest.fail("No dispatch"))
    assert not list(outside.iterdir())


def test_insufficient_disk_reserve_stops_before_claims(tmp_path):
    with pytest.raises(m.ContinuationCaptureError, match="reserve"):
        run(tmp_path, free_bytes=lambda: m.MIN_FREE_BYTES)
    assert not paths(tmp_path)[2].exists()


def test_nonprogressing_sleep_refuses_second_dispatch_not_clock_attestation(tmp_path):
    items = (request(1), request(2)); chosen = selection(tmp_path, items)
    timer, calls = Clock(), []
    def fake(url, *args):
        calls.append(url); raw = parent(items[len(calls) - 1])
        return SecHttpResult(200, (("Content-Length", str(len(raw))),), raw)
    with pytest.raises(m.ContinuationCaptureError, match="spacing"):
        m._run_invented_capture(chosen, "invented-next-prefix", root=tmp_path.resolve(), transport=fake,
            contact_email=CONTACT, monotonic_ns=timer.now, sleep=lambda seconds: None, clock=timer.utc)
    assert len(calls) == 1
    _, claims, output = paths(tmp_path)
    assert len(list(claims.iterdir())) == 2 and (output / "request-000-result.json").exists()
    assert not (output / "request-001-start.json").exists() and not (output / "complete.json").exists()


@pytest.mark.parametrize("stage", ["initial", "post-start", "final"])
def test_context_refusal_at_each_boundary_consumes_no_retry_permission(tmp_path, stage):
    calls = []
    def guard():
        calls.append(1)
        if stage == "initial" or stage == "post-start" and len(calls) == 3:
            raise m.ContinuationCaptureError("REFUSED: invented context drift")
    def final_guard():
        if stage == "final": raise m.ContinuationCaptureError("REFUSED: invented final source drift")
    with pytest.raises(m.ContinuationCaptureError, match="drift"):
        run(tmp_path, guard=guard, final_guard=final_guard)
    output = paths(tmp_path)[2]
    if stage == "initial": assert not output.exists()
    elif stage == "post-start": assert (output / "request-000-start.json").exists() and not (output / "complete.json").exists()
    else: assert (output / "complete.json").exists()


def test_readonly_verifier_rejects_changed_global_lock_bytes(tmp_path):
    result, _, _, _ = run(tmp_path)
    (paths(tmp_path)[0] / "capture.lock").write_bytes(b"changed-lock\n")
    with pytest.raises(m.ContinuationCaptureError, match="lock"):
        verify(tmp_path, result)


def test_cli_flushes_genuine_schema_summary_before_private_input_or_capture(tmp_path, monkeypatch):
    # Plumbing substitution only: no observed seal, actual combined replay,
    # Git check, provider or root acquisition is represented by this fixture.
    chosen = selection(tmp_path, (request(),))
    real_body = m._selection_body
    monkeypatch.setattr(m, "_selection_body", lambda value, observed: real_body(value, False))
    monkeypatch.setattr(combined, "run_isolated_combined_v4", lambda **kwargs: chosen)
    monkeypatch.setattr(m, "_CommitGuard", lambda *args: types.SimpleNamespace(check=lambda **kwargs: None))
    events, outputs = [], []
    class Output:
        def write(self, raw): outputs.append(raw); events.append("write")
        def flush(self): events.append("flush")
    monkeypatch.setattr(m.sys, "stdout", types.SimpleNamespace(buffer=Output()))
    def contact():
        assert events == ["write", "flush"]
        summary = json.loads(outputs[0])
        assert summary["combined_class_counts"] == chosen.to_payload()["combined_class_counts"]
        assert summary["selected_prefix_sha256"] == chosen.to_payload()["selected_prefix_sha256"]
        assert summary["sec_dispatches"] == 0
        events.append("contact"); return CONTACT
    monkeypatch.setattr(old, "_private_contact", contact)
    def capture_fixture(*args, **kwargs):
        assert events[-1] == "contact"; events.append("capture")
        return {"scope": "invented_plumbing_only", "sec_dispatches": 0}
    monkeypatch.setattr(m, "_capture", capture_fixture)
    assert m.main(["--expected-head", HEAD, "--capture-id", "invented-cli", "--maximum-requests", "1"]) == 0
    assert events == ["write", "flush", "contact", "capture", "write", "flush"]
    assert CONTACT.encode() not in b"".join(outputs)


@pytest.mark.parametrize("drift", ["head", "status", "source"])
def test_commit_guard_checks_live_context_without_reusing_cached_success(monkeypatch, drift):
    # Unit seam for the live-check method, not a forged observed selection or
    # a representation that a genuine committed baseline was established.
    base = m._base(); sources = ((m.SELF_PATH, b"INVENTED_SOURCE_IMAGE"),)
    context = object.__new__(m._CommitGuard); context.head = HEAD; context.sources = sources
    monkeypatch.setattr(base, "_repository_snapshot", lambda: (("b" * 40, "") if drift == "head" else
        (HEAD, " M invented.py\n") if drift == "status" else (HEAD, "")))
    monkeypatch.setattr(base, "_source_snapshot", lambda: ((m.SELF_PATH, b"DIFFERENT_IMAGE"),) if drift == "source" else sources)
    monkeypatch.setattr(base, "_git", lambda *args: pytest.fail("Git blob loop after live context refusal"))
    with pytest.raises(m.ContinuationCaptureError, match="HEAD/status/source"):
        context.check()


def test_commit_blob_loop_is_only_baseline_and_final_not_every_boundary(monkeypatch):
    base = m._base(); sources = ((m.SELF_PATH, b"INVENTED_SOURCE_IMAGE"),)
    context = object.__new__(m._CommitGuard); context.head = HEAD; context.sources = sources
    monkeypatch.setattr(base, "_repository_snapshot", lambda: (HEAD, ""))
    monkeypatch.setattr(base, "_source_snapshot", lambda: sources)
    monkeypatch.setattr(m, "_OWN_FILES", ())  # This unit targets the source-loop cache, not test-file publication.
    calls = []
    def git(*args): calls.append(args); return sources[0][1]
    monkeypatch.setattr(base, "_git", git)
    context.check(final=True)
    for _ in range(50): context.check()
    assert len(calls) == 1
    context.check(final=True)
    assert len(calls) == 2


def test_verifier_rechecks_namespace_after_last_byte_read(tmp_path, monkeypatch):
    result, _, _, _ = run(tmp_path); original = old._Directory.read
    base, _, _ = paths(tmp_path)
    def changed(folder, name, **kwargs):
        raw = original(folder, name, **kwargs)
        if folder.path == base and name == "capture.lock":
            # Only inject on the final retained lock read, after all parsing.
            changed.count += 1
            if changed.count == 2:
                leaf = paths(tmp_path)[2] / "unknown-final.json"; leaf.write_bytes(b"{}\n"); leaf.chmod(0o600)
        return raw
    changed.count = 0
    monkeypatch.setattr(old._Directory, "read", changed)
    with pytest.raises(m.ContinuationCaptureError, match="leaf inventory"):
        verify(tmp_path, result)


@pytest.mark.parametrize("mutation", ["status200", "missing-observed-digest"])
def test_verifier_rejects_reanchored_impossible_http_disposition(tmp_path, mutation):
    result, _, _, _ = run(tmp_path, response=SecHttpResult(403, (), b""))
    output = paths(tmp_path)[2]; attempt_path = output / "request-000-result.json"
    attempt = json.loads(attempt_path.read_bytes())
    if mutation == "status200": attempt["status"] = 200
    else: attempt["body_sha256"] = None
    attempt_raw = m._raw(attempt); attempt_path.write_bytes(attempt_raw)
    report_path = output / "complete.json"; report = json.loads(report_path.read_bytes())
    report["results"][0]["result_sha256"] = old._sha(attempt_raw)
    raw = m._raw(report); report_path.write_bytes(raw); result["report_sha256"] = old._sha(raw)
    with pytest.raises(m.ContinuationCaptureError, match="disposition"):
        verify(tmp_path, result)
