"""Protected orchestration fixtures; no actual artifacts, requests or accounts."""
from copy import deepcopy
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from research import insider_buying_pilot_sec_fresh_selection_runner as m


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("invented_fresh_selection_runner_fixture",
        Path(__file__).with_name("test_insider_buying_pilot_sec_fresh_selection.py"))
    helper = importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    return helper, helper.corpus.__wrapped__(tmp_path_factory)


@pytest.fixture(scope="module")
def supplied(corpus):
    helper, data = corpus
    omitted = helper._pilot_targets(data)[0]["accession_number"]
    pipeline = helper._pipeline(data, omit=[omitted])
    selected = helper._finish(pipeline)
    source, completed, emissions = pipeline[1:]
    quarantines = [row for row in emissions if row["relevant_parent_target"] and row["selected_locator"] is None]
    assert len(quarantines) == 1 and selected.to_payload()["fixture_only"] is True
    exposure = {"schema": m.base.compiler.EXPOSURE_SCHEMA, "records": []}
    candidates = {"schema": m.base.compiler.CANDIDATE_SCHEMA, "fixture_only": True, "records": [], "masters": [],
        "authority": dict(m.base.compiler._AUTHORITY)}
    prior = {"source_roster": source.to_payload(), "parent_audit": completed.to_payload(),
        "exposure_inventory_sha256": m._sha(m._raw(exposure)), "exposure_snapshot_sha256": "e" * 64,
        "retained_body_inventory_sha256": m._sha(m._raw(candidates))}
    return SimpleNamespace(helper=helper, data=data, omitted=omitted, source=source, completed=completed,
        selected=selected, quarantines=quarantines, prior=prior, exposure_raw=m._raw(exposure), retained_raw=m._raw(candidates))


def _derive_fixture(monkeypatch, supplied):
    helper, data = supplied.helper, supplied.data
    raw_manifest, _images, selector = data[1]
    intake = SimpleNamespace(manifest_raw=raw_manifest, context={"manifest_sha256": m._sha(raw_manifest)})
    tree = object()
    holds = [SimpleNamespace(spec=SimpleNamespace(root_id="masters-v3"), tree=tree)]
    calls = []
    real_roster = m.base.roster.derive_pilot_sec_roster
    def invented_roster(**kwargs):
        # The production call must still insist on actual mode and anchors.
        # Only this invented test adapter supplies independently genuine,
        # fixture-only factories using the explicitly invented82 images.
        assert kwargs["fixture_only"] is False
        assert kwargs["expected_selection_sha256"] == m.base.prior.ACTUAL_ANCHORS.selection
        assert kwargs["intake_manifest_raw"] == raw_manifest
        calls.append("genuine_invented_roster")
        return real_roster(**data[0]._args(data[1], kwargs["consume_row"]))
    monkeypatch.setattr(m.base.roster, "derive_pilot_sec_roster", invented_roster)
    monkeypatch.setattr(m.base.roster, "held_context_quarters", lambda held: iter(()))
    def master(actual_tree, period):
        assert actual_tree is tree
        calls.append(period)
        return helper._master(period, data[3], omit=[supplied.omitted])
    monkeypatch.setattr(m.base, "_master", master)
    return intake, holds, m._raw(selector), calls


def _derived(supplied):
    rows = deepcopy(supplied.quarantines)
    lines = b"".join(m._raw(row) + b"\n" for row in rows)
    return {"selection": supplied.selected.to_payload(), "selection_sha256": supplied.selected.sha256,
        "source_roster": supplied.source.to_payload(), "parent_audit": supplied.completed.to_payload(),
        "locator_quarantines": rows, "locator_quarantine_jsonl_sha256": m._sha(lines), "locator_quarantine_jsonl_bytes": len(lines)}


def _root(supplied, identity=None):
    result = {"schema": m.SCHEMA, "audit_id": m.AUDIT_ID, "registration": deepcopy(m.REGISTRATION),
        "registration_sha256": m._sha(m._raw(m.REGISTRATION)), "execution_identity": {"invented": True} if identity is None else identity,
        "prior_audit_complete_sha256": m.retained.PINS["complete.json"][0],
        "exposure_inventory_sha256": supplied.prior["exposure_inventory_sha256"],
        "exposure_snapshot_sha256": supplied.prior["exposure_snapshot_sha256"],
        "retained_body_inventory_sha256": supplied.prior["retained_body_inventory_sha256"], **_derived(supplied),
        "native_network_fork_allwrite_securityexec_denial": True, "new_provider_requests": 0,
        "credential_reads": 0, "qc_accesses": 0, "outcome_looks": 0, "backtests": 0,
        "dispatch_authorized": False, "canonical_admitted": False, "backtesting_ready": False}
    return result


def _invented_parent_wire(monkeypatch, supplied):
    # These envelope-only fixtures do NOT claim actual population provenance.
    # Keep genuine pure factories fixture-only; isolate only the production
    # false-vs-invented flag/accounting boundary, independently tested by the
    # pure module. Every other pure request/schema/count/hash guard executes.
    original = m.selection.validate_selection_payload
    def validate_wire(value):
        invented = deepcopy(value)
        invented["fixture_only"] = True
        original(invented)
        return deepcopy(value)
    monkeypatch.setattr(m.selection, "validate_selection_payload", validate_wire)
    result = _root(supplied)
    result["selection"]["fixture_only"] = False
    result["selection_sha256"] = m._sha(m._raw(result["selection"]))
    return result


def _rehash_quarantine(result):
    raw = b"".join(m._raw(row) + b"\n" for row in result["locator_quarantines"])
    result.update(locator_quarantine_jsonl_sha256=m._sha(raw), locator_quarantine_jsonl_bytes=len(raw))


def test_new_scope_is_not_a_replay_or_transport_grant():
    assert m.AUDIT_ID != m.base.AUDIT_ID != m.retained.AUDIT_ID
    assert m.OUTPUT_PARTS not in (m.base.OUTPUT_PARTS, m.retained.OUTPUT_PARTS)
    assert m.REGISTRATION == m.base._decode(m._raw(m.REGISTRATION))
    assert m.REGISTRATION["selection_period"] == "2021Q1" and m.REGISTRATION["selection_limit"] == 64
    assert m.REGISTRATION["worker_invocations"] == 1 and m.REGISTRATION["backtesting_ready"] is False
    assert all(type(m.REGISTRATION[key]) is int and m.REGISTRATION[key] == 0
        for key in ("new_provider_requests", "credential_reads", "qc_accesses", "outcome_looks", "backtests"))


def test_derive_uses_genuine_completed_factories_and_full_stream_prior_equality(monkeypatch, supplied):
    intake, holds, selection_raw, calls = _derive_fixture(monkeypatch, supplied)
    observed = m._derive(supplied.prior, intake=intake, operational_holds=holds,
        exposure_raw=supplied.exposure_raw, retained_raw=supplied.retained_raw, selection_raw=selection_raw)
    assert observed == _derived(supplied)
    assert calls[0] == "genuine_invented_roster" and calls[1:] == list(m.base.roster.CONTEXT_PERIODS)
    assert observed["selection"]["fixture_only"] is True
    assert observed["selection"]["requests"][0]["request"]["period"] == "2021Q1"
    assert observed["locator_quarantines"][0]["request"] is None


@pytest.mark.parametrize("fault", ["master_missing", "source_prior_changed", "audit_prior_changed", "fake_factory"])
def test_derive_cannot_replace_inputs_or_completed_factories(monkeypatch, supplied, fault):
    intake, holds, selected_raw, _ = _derive_fixture(monkeypatch, supplied)
    prior = deepcopy(supplied.prior)
    if fault == "master_missing": holds = []
    if fault == "source_prior_changed": prior["source_roster"]["counts"]["context_submission_rows"] += 1
    if fault == "audit_prior_changed": prior["parent_audit"]["source_row_jsonl_sha256"] = "f" * 64
    if fault == "fake_factory":
        monkeypatch.setattr(m.selection.PilotSecFreshSelectionBuilder, "finish", lambda *a, **k: SimpleNamespace(
            to_payload=supplied.selected.to_payload, sha256=supplied.selected.sha256))
    with pytest.raises((m.FreshSelectionRunnerError, ValueError)):
        m._derive(prior, intake=intake, operational_holds=holds,
            exposure_raw=supplied.exposure_raw, retained_raw=supplied.retained_raw, selection_raw=selected_raw)


def test_production_readback_rejects_a_genuine_invented_selection(supplied):
    with pytest.raises(m.FreshSelectionRunnerError, match="crosslinks"):
        m._validate(_root(supplied), {"invented": True}, supplied.prior)


def test_parent_envelope_crosslinks_all_completed_receipts(monkeypatch, supplied):
    result = _invented_parent_wire(monkeypatch, supplied)
    assert m._validate(result, {"invented": True}, supplied.prior) is result


@pytest.mark.parametrize("change", [
    lambda r: r.update(unexpected=True), lambda r: r.update(audit_id="old-audit"),
    lambda r: r.update(registration_sha256="f" * 64), lambda r: r.update(execution_identity={}),
    lambda r: r.update(prior_audit_complete_sha256="f" * 64),
    lambda r: r.update(native_network_fork_allwrite_securityexec_denial=False),
    lambda r: r.update(credential_reads=False), lambda r: r.update(qc_accesses=1),
    lambda r: r.update(outcome_looks=1), lambda r: r.update(backtesting_ready=True),
    lambda r: r.update(dispatch_authorized=True), lambda r: r.update(selection_sha256="f" * 64),
    lambda r: r.update(exposure_inventory_sha256="f" * 64),
    lambda r: r.update(exposure_snapshot_sha256="f" * 64),
    lambda r: r.update(retained_body_inventory_sha256="f" * 64),
    lambda r: r["source_roster"]["counts"].update(context_submission_rows=0),
    lambda r: r["parent_audit"].update(fresh_request_jsonl_sha256="f" * 64),
    lambda r: r["selection"].update(parent_audit_sha256="f" * 64),
])
def test_parent_rejects_changed_source_counts_hashes_authority_or_identity(monkeypatch, supplied, change):
    result = _invented_parent_wire(monkeypatch, supplied);change(result)
    with pytest.raises((m.FreshSelectionRunnerError, ValueError)):
        m._validate(result, {"invented": True}, supplied.prior)


@pytest.mark.parametrize("stem", ["source_row", "disposition", "fresh_request"])
def test_parent_crosschecks_full_global_streams_not_only_quarter_shapes(monkeypatch, supplied, stem):
    result = _invented_parent_wire(monkeypatch, supplied)
    result["selection"]["full_" + stem + "_jsonl_sha256"] = "f" * 64
    result["selection_sha256"] = m._sha(m._raw(result["selection"]))
    with pytest.raises(m.FreshSelectionRunnerError, match="completed_streams"):
        m._validate(result, {"invented": True}, supplied.prior)


@pytest.mark.parametrize("change", [
    lambda row: row.update(schema="unknown"), lambda row: row.update(dispatch_authorized=True),
    lambda row: row.update(prior_consumed=0), lambda row: row.update(historical_ambiguous_start_preserved=True),
    lambda row: row.update(prior_exposure_evidence=[{"root_id": "old-root", "journal_sha256": "a" * 64, "state": "ambiguous"}]),
    lambda row: row.update(prior_source_occurrence={"period": "2020Q1", "source_record_ordinal": 1, "filing_metadata_sha256": "a" * 64}),
    lambda row: row.update(cross_quarter_source_identity_conflict=True),
    lambda row: row.update(pre_normalization_target={"unexpected": "PRIVATE"}),
    lambda row: row.update(locator_quarantine_reasons=["invented-private-reason"]),
    lambda row: row.update(locator_quarantine_reasons=["master_form_disagreement"]),
    lambda row: row.update(locator_quarantine_reasons=["master_locator_missing", "master_form_disagreement"]),
    lambda row: row.update(master_aliases=[{"accession_number": "invalid"}]),
    lambda row: row.update(source_record_sha256="f" * 64),
    lambda row: row.update(request={"url": "https://www.sec.gov/Archives/guessed.txt"}),
    lambda row: row.update(fresh_locatable_candidate=True),
])
def test_parent_quarantine_preserves_consumption_and_refusal_metadata_even_rehashed(monkeypatch, supplied, change):
    result = _invented_parent_wire(monkeypatch, supplied);change(result["locator_quarantines"][0]);_rehash_quarantine(result)
    with pytest.raises((m.FreshSelectionRunnerError, ValueError, TypeError, KeyError)):
        m._validate(result, {"invented": True}, supplied.prior)


def test_parent_quarantine_cannot_be_omitted_or_repeated_to_match_another_story(monkeypatch, supplied):
    for repeat in (False, True):
        result = _invented_parent_wire(monkeypatch, supplied)
        if repeat: result["locator_quarantines"].append(deepcopy(result["locator_quarantines"][0]))
        else: result["locator_quarantines"] = []
        _rehash_quarantine(result)
        with pytest.raises(m.FreshSelectionRunnerError): m._validate(result, {"invented": True}, supplied.prior)


def test_native_worker_flags_fail_before_any_prior_artifact(monkeypatch):
    monkeypatch.setattr(m.retained, "_PriorHold", lambda: pytest.fail("actual prior artifact must not be opened"))
    with pytest.raises(m.FreshSelectionRunnerError, match="worker_isolation"): m._worker({"invented": True})


def _worker_inputs(monkeypatch, supplied):
    template = _invented_parent_wire(monkeypatch, supplied)
    derived = {key: template[key] for key in _derived(supplied)}
    prior = deepcopy(supplied.prior);snapshot = b'{"invented":"operational_snapshot"}'
    prior["exposure_snapshot_sha256"] = m._sha(snapshot)
    source = {m.SELF_PATH: "d" * 64}
    identity = {"root": str(m.LANE_ROOT), "branch": m.base.LANE_BRANCH, "clean": True, "source_sha256": source,
        "source_inventory_sha256": m._sha(m._raw(source))}
    events = []
    monkeypatch.setattr(m, "sys", SimpleNamespace(flags=SimpleNamespace(isolated=1, no_site=1, dont_write_bytecode=1),
        pycache_prefix=m.base.EMPTY_CACHE_PREFIX))
    monkeypatch.setattr(m.base, "_prove_isolation", lambda: events.append("native_proof"))
    def source_bytes(_root, paths):
        frozen = tuple(paths) == tuple(m.base.FROZEN)
        events.append("frozen_sources" if frozen else "current_sources")
        return dict(m.base.FROZEN) if frozen else dict(source)
    monkeypatch.setattr(m.base.custody, "_source_bytes", source_bytes)
    class Prior:
        def report(self): events.append("prior_report");return prior
        def recheck(self): events.append("prior_recheck")
        def close(self): events.append("prior_close")
    class Accepted:
        def __init__(self, root): assert root == m.LANE_ROOT;events.append("accepted_open")
        def leaf(self, parts, name, cap, expected):
            assert parts == m.base.prior.SELECTOR_PARTS and name == "selection.json"
            assert expected == m.base.prior.ACTUAL_ANCHORS.selection
            return b'{"invented":"accepted_selector"}'
        def recheck(self): events.append("accepted_recheck")
        def close(self): events.append("accepted_close")
    class Intake:
        def recheck(self): events.append("intake_recheck")
        def close(self): events.append("intake_close")
    class Operational:
        def recheck(self): events.append("operational_recheck")
        def close(self): events.append("operational_close")
    holds = [Operational()]
    monkeypatch.setattr(m.retained, "_PriorHold", Prior)
    monkeypatch.setattr(m.base.prior, "_Held", Accepted)
    monkeypatch.setattr(m.base.prior, "_selector", lambda *_: events.append("accepted_validate"))
    monkeypatch.setattr(m.base.selector, "_HeldIntake", Intake)
    monkeypatch.setattr(m.base.exposure, "actual_roots", lambda: ("invented-only",))
    def exposures(roots, *, fixture_only):
        assert roots == ("invented-only",) and fixture_only is False
        events.append("operational_open")
        return holds, supplied.exposure_raw, snapshot, supplied.retained_raw
    monkeypatch.setattr(m.base.exposure, "observe_exposures", exposures)
    def body_hashes(received, raw):
        assert received == holds and raw == supplied.retained_raw
        events.append("hash_bodies");return raw
    monkeypatch.setattr(m.base.exposure, "hash_candidate_bodies", body_hashes)
    def derive(received_prior, **kwargs):
        assert received_prior is prior and kwargs["operational_holds"] == holds
        assert kwargs["exposure_raw"] == supplied.exposure_raw and kwargs["retained_raw"] == supplied.retained_raw
        assert kwargs["selection_raw"] == b'{"invented":"accepted_selector"}'
        events.append("derive");return deepcopy(derived)
    monkeypatch.setattr(m, "_derive", derive)
    return identity, prior, events


def test_worker_proves_native_denial_then_rechecks_every_old_source_before_return(monkeypatch, supplied):
    identity, prior, events = _worker_inputs(monkeypatch, supplied)
    result = m._worker(identity)
    assert events[0] == "native_proof" and events.count("current_sources") == 2
    assert events.index("hash_bodies") < events.index("derive") < events.index("intake_recheck")
    assert events.index("accepted_recheck") < events.index("prior_recheck") < events.index("operational_recheck")
    assert events[-4:] == ["intake_close", "accepted_close", "prior_close", "operational_close"]
    assert m._validate(result, identity, prior) == result


@pytest.mark.parametrize("fault", ["dirty", "source_digest", "snapshot", "retained", "native", "final_current_source"])
def test_worker_refusals_cannot_bypass_old_snapshot_or_final_rechecks(monkeypatch, supplied, fault):
    identity, prior, events = _worker_inputs(monkeypatch, supplied)
    if fault == "dirty": identity["clean"] = False
    if fault == "source_digest": identity["source_inventory_sha256"] = "f" * 64
    if fault == "snapshot": prior["exposure_snapshot_sha256"] = "f" * 64
    if fault == "retained": prior["retained_body_inventory_sha256"] = "f" * 64
    if fault == "native":
        def refusal(): raise m.FreshSelectionRunnerError("invented_native_denial_refused")
        monkeypatch.setattr(m.base, "_prove_isolation", refusal)
    if fault == "final_current_source":
        original, calls = m.base.custody._source_bytes, []
        def changed(root, paths):
            result = original(root, paths)
            if tuple(paths) == tuple(identity["source_sha256"]):
                calls.append(True)
                if len(calls) == 2: return {m.SELF_PATH: "f" * 64}
            return result
        monkeypatch.setattr(m.base.custody, "_source_bytes", changed)
    with pytest.raises(m.FreshSelectionRunnerError): m._worker(identity)
    if fault in {"dirty", "source_digest", "native"}: assert "operational_open" not in events
    else: assert "prior_close" in events and "operational_close" in events


def _guard():
    command = ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin", sys.executable, "-I", "-S", "-B", "-c", "pass")
    return m._Guard("a" * 40, command), command


def test_guard_uses_new_namespace_and_one_exact_worker_only():
    guard, command = _guard()
    assert guard.output == m.LANE_ROOT.joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID)
    guard("subprocess.Popen", (command[0], command, m.LANE_ROOT, None))
    with pytest.raises(m.base.PilotParentRunnerError): guard("subprocess.Popen", (command[0], command, m.LANE_ROOT, None))
    for name in ("reservation.json", "terminal.json", "complete.json"): guard._write(guard.output / name)
    for path in (guard.output / "body.bin", m.LANE_ROOT.joinpath(*m.base.OUTPUT_PARTS, m.base.AUDIT_ID, "complete.json")):
        with pytest.raises(m.base.PilotParentRunnerError): guard._write(path)


@pytest.mark.parametrize("event", ["socket.connect", "urllib.Request", "os.exec", "os.fork", "os.posix_spawn", "os.system"])
def test_guard_network_and_credential_or_unknown_processes_denied(event):
    guard, _ = _guard()
    with pytest.raises(PermissionError): guard(event, ())


def _orchestration(monkeypatch, supplied):
    worker = _invented_parent_wire(monkeypatch, supplied)
    identity = {"invented": True, "source_sha256": {m.SELF_PATH: "a" * 64}}
    worker["execution_identity"] = identity
    calls = {"identity": [], "children": [], "published": {}, "final": [], "prior": [], "closed": []}
    def identify(head): calls["identity"].append(head);return deepcopy(identity)
    monkeypatch.setattr(m.base.custody, "_identity", identify)
    monkeypatch.setattr(m.sys, "addaudithook", lambda _: None)
    class Chain:
        def __init__(self, root, parts): assert root == m.LANE_ROOT;self.fd = 123;self.parts = parts
        def recheck(self): pass
        def close(self): calls["closed"].append(self.parts)
    monkeypatch.setattr(m.base.custody, "_Chain", Chain)
    monkeypatch.setattr(m.os, "mkdir", lambda *_a, **_k: None)
    monkeypatch.setattr(m.os, "fstatvfs", lambda _: SimpleNamespace(f_bavail=1 << 32, f_frsize=4096))
    class Output:
        def __init__(self, chain): assert chain.parts == (*m.OUTPUT_PARTS, m.AUDIT_ID)
        def publish(self, name, raw):
            assert name not in calls["published"];calls["published"][name] = m.base._decode(raw);return m._sha(raw)
        def recheck(self, *, final=False): calls["final"].append(final)
        def close(self): calls["closed"].append("output")
    class Prior:
        def report(self): calls["prior"].append("report");return supplied.prior
        def recheck(self): calls["prior"].append("recheck")
        def close(self): calls["prior"].append("close")
    monkeypatch.setattr(m, "_Output", Output);monkeypatch.setattr(m.retained, "_PriorHold", Prior)
    def child(command, **kwargs):
        calls["children"].append(command)
        assert command[:3] == ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin")
        assert command[3:5] == ("/usr/bin/sandbox-exec", "-p")
        assert all(part in command[5] for part in ("(deny network*)", "(deny process-fork)", "(deny file-write*)",
            '(deny process-exec (literal "/usr/bin/security"))'))
        assert command[6] == sys.executable and command[7:10] == ("-I", "-S", "-B")
        assert "pycache_prefix=" + m.base.EMPTY_CACHE_PREFIX in command
        assert kwargs == {"cwd": m.LANE_ROOT, "env": None, "timeout": 1800, "cap": m.base.MAX_REPORT}
        assert list(calls["published"]) == ["reservation.json"]
        return subprocess.CompletedProcess(command, 0, m._raw(worker) + b"\n", b"")
    monkeypatch.setattr(m.base.launcher, "run_child", child)
    return worker, identity, calls


def test_parent_publishes_three_controls_with_exact_worker_and_terminal_crosslinks(monkeypatch, supplied):
    worker, _identity, calls = _orchestration(monkeypatch, supplied)
    result = m.run_actual("a" * 40)
    assert len(calls["children"]) == 1 and calls["identity"] == ["a" * 40, "a" * 40]
    assert list(calls["published"]) == ["reservation.json", "terminal.json", "complete.json"]
    complete, terminal = calls["published"]["complete.json"], calls["published"]["terminal.json"]
    assert complete["worker_result"] == worker
    assert complete["reservation_sha256"] == terminal["reservation_sha256"] == m._sha(m._raw(calls["published"]["reservation.json"]))
    assert complete["terminal_sha256"] == m._sha(m._raw(terminal))
    assert result["complete_sha256"] == m._sha(m._raw(complete)) and result["complete_bytes"] == len(m._raw(complete))
    assert result["selected_count"] == 64 and result["locator_quarantines"] == 1 and result["backtesting_ready"] is False
    assert calls["final"] == [True] and calls["prior"] == ["report", "recheck", "close"]
    assert "stderr" not in terminal and "stdout" not in terminal and "args" not in terminal


@pytest.mark.parametrize("fault", ["exit", "stderr", "empty", "malformed", "changed_identity", "bad_selection", "final_readback"])
def test_parent_refusal_preserves_terminal_but_never_returns_completion(monkeypatch, supplied, fault):
    worker, identity, calls = _orchestration(monkeypatch, supplied)
    original = m.base.launcher.run_child
    if fault in {"exit", "stderr", "empty", "malformed"}:
        def child(command, **kwargs):
            original(command, **kwargs)
            return subprocess.CompletedProcess(command, 2 if fault == "exit" else 0,
                b"" if fault == "empty" else b"PRIVATE malformed" if fault == "malformed" else m._raw(worker) + b"\n",
                b"PRIVATE STDERR" if fault == "stderr" else b"")
        monkeypatch.setattr(m.base.launcher, "run_child", child)
    if fault == "changed_identity":
        values = iter([identity, {**identity, "invented": "changed"}])
        monkeypatch.setattr(m.base.custody, "_identity", lambda _: next(values))
    if fault == "bad_selection": worker["selection_sha256"] = "f" * 64
    if fault == "final_readback":
        class Broken(m._Output):
            def recheck(self, *, final=False): assert final;raise ValueError("PRIVATE readback")
        monkeypatch.setattr(m, "_Output", Broken)
    with pytest.raises((m.FreshSelectionRunnerError, ValueError)): m.run_actual("a" * 40)
    assert "terminal.json" in calls["published"] and "output" in calls["closed"]
    if fault != "final_readback": assert "complete.json" not in calls["published"]
    assert b"PRIVATE" not in m._raw(calls["published"]["terminal.json"])


def test_cli_refusal_never_prints_private_source_or_exception(monkeypatch, capsys):
    def refuse(_): raise ValueError("PRIVATE path contact source body")
    monkeypatch.setattr(m, "run_actual", refuse)
    assert m.main(["--expected-head", "a" * 40]) == 2
    assert capsys.readouterr().out == '{"disposition":"pilot_fresh_selection_refused"}\n'


def _output(monkeypatch, tmp_path):
    os.chmod(tmp_path, 0o700)
    path = tmp_path.joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID);path.mkdir(parents=True, mode=0o700)
    monkeypatch.setattr(m, "LANE_ROOT", tmp_path)
    chain = m.base.custody._Chain(path, ())
    return path, chain, m._Output(chain)


def test_new_publication_is_exclusive_private_and_cannot_resume(monkeypatch, tmp_path):
    path, chain, output = _output(monkeypatch, tmp_path)
    try:
        output.publish("reservation.json", b'{"invented":"reservation"}')
        with pytest.raises(m.base.PilotParentRunnerError, match="incomplete"): output.recheck(final=True)
        output.publish("terminal.json", b'{"invented":"terminal"}')
        output.publish("complete.json", b'{"invented":"complete"}');output.recheck(final=True)
        assert all((path / name).stat().st_mode & 0o777 == 0o600 for name in os.listdir(path))
        with pytest.raises(m.FreshSelectionRunnerError, match="cannot_resume"): m._Output(chain)
    finally: output.close();chain.close()


@pytest.mark.parametrize("fault", ["content", "replacement", "extra", "mode"])
def test_new_publication_rechecks_full_hash_current_leaf_and_inventory(monkeypatch, tmp_path, fault):
    path, chain, output = _output(monkeypatch, tmp_path)
    try:
        output.publish("reservation.json", b'{"invented":"a"}')
        leaf = path / "reservation.json";version = leaf.stat()
        if fault == "content":
            leaf.write_bytes(b'{"invented":"b"}');os.utime(leaf, ns=(version.st_atime_ns, version.st_mtime_ns))
        elif fault == "replacement":
            other = path / "replacement";other.write_bytes(leaf.read_bytes());os.chmod(other, 0o600);os.replace(other, leaf)
        elif fault == "extra": (path / "extra").write_bytes(b"PRIVATE")
        else: os.chmod(leaf, 0o644)
        with pytest.raises((m.base.PilotParentRunnerError, ValueError)): output.recheck()
    finally: output.close();chain.close()
