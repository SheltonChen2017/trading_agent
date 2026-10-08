"""Invented pure overlays/private journals; never actual retained-root replay."""
import copy
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import types

import pytest

from research import insider_buying_sec_recovery_v4_combined as m
from research import insider_buying_sec_recovery_v4_capture as capture
from test_insider_buying_sec_recovery_v4_projection import request, captured, project


def population(tmp_path, *, completed=2, remaining=5):
    originals = tuple(request(index + 1) for index in range(100 + completed + remaining))
    result, _ = captured(tmp_path, items=originals[100:100 + completed])
    closure = project(tmp_path, result).to_payload()["rows"]
    partition = [{"global_index": index, "request_sha256": m._hash(req),
        "source_class": "prior_completed" if index < 100 else "originally_unattempted"}
        for index, req in enumerate(originals)]
    return originals, partition, closure, result


def test_real_invented_journal_closure_overlays_only_exact_original_prefix(tmp_path):
    originals, partition, closed, _ = population(tmp_path)
    result = m._overlay_original_partition(originals, partition, closed, maximum_requests=3)
    assert result["total_parents"] == 107 and result["original_unattempted_count"] == 7
    assert result["remaining_unattempted_count"] == 5 and result["prior_source_bound_count"] == 100
    assert result["combined_request_bound_custody_count"] == 102
    assert result["combined_class_counts"]["fresh_v4_completed"] == 2
    assert [row["global_index"] for row in result["requests"]] == [102, 103, 104]
    assert all(row["request"] == originals[row["global_index"]] for row in result["requests"])
    assert all(row["source_class"] == "originally_unattempted" for row in result["requests"])
    assert partition[100]["source_class"] == "originally_unattempted"  # no caller mutation


def test_large_invented_original_population_exports_exact_next256_not_old_prefix(tmp_path):
    originals, partition, closed, _ = population(tmp_path, completed=64, remaining=350)
    result = m._overlay_original_partition(originals, partition, closed, maximum_requests=256)
    assert len(originals) == 514 and len(result["requests"]) == 256
    assert result["remaining_unattempted_count"] == 350
    assert [row["global_index"] for row in result["requests"]] == list(range(164, 420))
    expected = partition[164:]
    assert result["remaining_inventory_sha256"] == m._hash(expected)
    assert result["selected_prefix_sha256"] == m._hash(result["requests"])


@pytest.mark.parametrize("fault", ["reorder", "gap", "wrong_hash", "wrong_target", "duplicate_body", "quarantine", "bool_ordinal", "missing"])
def test_closure_identity_failure_never_skips_into_eligibility(tmp_path, fault):
    originals, partition, closed, _ = population(tmp_path); closed = copy.deepcopy(closed)
    if fault == "reorder": closed.reverse()
    elif fault == "gap": closed[1]["global_index"] += 1
    elif fault == "wrong_hash": closed[0]["request_sha256"] = "0" * 64
    elif fault == "wrong_target": closed[0]["target"]["quarterly_index_sha256"] = "0" * 64
    elif fault == "duplicate_body": closed[1]["raw_parent"]["sha256"] = closed[0]["raw_parent"]["sha256"]
    elif fault == "quarantine": closed[0]["disposition"] = "complete_parent_grammar_quarantine"
    elif fault == "bool_ordinal": closed[0]["ordinal"] = False
    else: closed[0].pop("projection")
    with pytest.raises(m.CombinedV4Error): m._overlay_original_partition(originals, partition, closed, maximum_requests=2)


@pytest.mark.parametrize("fault", ["duplicate_accession", "partition_order", "unknown_class", "bool_global", "wrong_hash"])
def test_original_population_is_exact_not_a_caller_selected_subset(tmp_path, fault):
    originals, partition, closed, _ = population(tmp_path); partition = copy.deepcopy(partition)
    if fault == "duplicate_accession": originals = (originals[1], *originals[1:])
    elif fault == "partition_order": partition[0], partition[1] = partition[1], partition[0]
    elif fault == "unknown_class": partition[0]["source_class"] = "assumed_completed"
    elif fault == "bool_global": partition[0]["global_index"] = False
    else: partition[0]["request_sha256"] = "0" * 64
    with pytest.raises(m.CombinedV4Error): m._overlay_original_partition(originals, partition, closed, maximum_requests=2)


def test_empty_or_exhausted_remaining_scope_is_not_a_ready_empty_selection(tmp_path):
    originals, partition, closed, _ = population(tmp_path, remaining=0)
    with pytest.raises(m.CombinedV4Error, match="no remaining"):
        m._overlay_original_partition(originals, partition, closed, maximum_requests=2)


def test_entire_registry_snapshot_binds_all_exact_private_claims_and_runs(tmp_path):
    _, _, _, result = population(tmp_path)
    snapshot = m._registry_snapshot(tmp_path.resolve(), expected_count=2, expected_runs=(result["capture_id"],))
    assert snapshot["claim_inventory_count"] == 2
    assert snapshot["claim_inventory_sha256"] == m._hash(snapshot["claim_inventory"])
    assert snapshot["known_run_inventory"] == [result["capture_id"]]
    assert snapshot["known_run_inventory_sha256"] == m._hash(snapshot["known_run_inventory"])


@pytest.mark.parametrize("fault", ["extra_claim", "extra_run", "missing_claim", "symlink_claim", "fifo_claim", "alter_lock"])
def test_any_unknown_missing_or_ambiguous_registry_state_refuses_no_skip(tmp_path, fault):
    _, _, _, result = population(tmp_path)
    base = tmp_path.resolve().joinpath(*capture.ARTIFACT_PARTS)
    claims = base / "claims"
    if fault == "extra_claim": (claims / ("0" * 64 + ".json")).write_bytes(b"unknown\n")
    elif fault == "extra_run": (base / "runs" / "unknown-pending-run").mkdir(mode=0o700)
    elif fault == "alter_lock": (base / "capture.lock").write_bytes(b"changed\n")
    else:
        path = next(claims.iterdir()); path.unlink()
        if fault == "symlink_claim": path.symlink_to(base / "capture.lock")
        elif fault == "fifo_claim": os.mkfifo(path, 0o600)
    with pytest.raises((m.CombinedV4Error, capture.FreshV4CaptureError, OSError)):
        m._registry_snapshot(tmp_path.resolve(), expected_count=2, expected_runs=(result["capture_id"],))


@pytest.mark.parametrize("count", [1, 64, 256])
def test_genuine_invented_factory_is_separate_and_zero_authority(count):
    selected = m.make_invented_combined_v4_selection(tuple(request(index + 1) for index in range(count)))
    body = selected.to_payload()
    assert type(selected) is m.InventedCombinedV4Selection and body["scope"] == "invented_test_only"
    assert selected.sha256 == m._hash(body) and selected.raw_bytes == m._canonical(body)
    assert body["authority"] == m._authority()


@pytest.mark.parametrize("count", [0, 257])
def test_invented_prefix_has_exact_finite_bounds(count):
    with pytest.raises(m.CombinedV4Error):
        m.make_invented_combined_v4_selection(tuple(request(index + 1) for index in range(count)))


def test_existing_claim_even_with_locator_alias_blocks_invented_nextprefix():
    name = m._sha(request()["accession_number"].encode()) + ".json"
    with pytest.raises(m.CombinedV4Error, match="permanent claim"):
        m.make_invented_combined_v4_selection((request(),), claim_inventory=({"name": name, "sha256": "a" * 64},))


@pytest.mark.parametrize("change", ["image", "mutable_bytes", "token_equal", "detached"])
def test_registered_factory_image_cannot_be_reanchored(change):
    selected = m.make_invented_combined_v4_selection((request(),))
    if change == "image":
        body = selected.to_payload(); body["requests"][0]["request"]["issuer_cik"] = "2"
        body["requests"][0]["request_sha256"] = m._hash(body["requests"][0]["request"])
        body["selected_prefix_sha256"] = m._hash(body["requests"])
        object.__setattr__(selected, "_raw", m._canonical(body))
    elif change == "mutable_bytes": object.__setattr__(selected, "_raw", bytearray(selected.raw_bytes))
    elif change == "token_equal":
        class Equal:
            def __eq__(self, other): return True
        object.__setattr__(selected, "_token", Equal())
    else: selected = m.InventedCombinedV4Selection(selected.raw_bytes, selected._token)
    with pytest.raises(m.CombinedV4Error, match="factory-bound"): selected.to_payload()


def test_invalid_embedded_inventory_and_observed_scope_are_not_seals():
    body = m.make_invented_combined_v4_selection((request(),)).to_payload()
    bad = copy.deepcopy(body); bad["claim_inventory_count"] = False
    with pytest.raises(m.CombinedV4Error): m.validate_combined_v4_selection_payload(bad, observed=False)
    with pytest.raises(m.CombinedV4Error): m.validate_combined_v4_selection_payload(body, observed=True)


@pytest.mark.parametrize("change", ["malformed_date", "wrong_form", "null_request"])
def test_embedded_request_refusal_uses_combined_public_error(change):
    body = m.make_invented_combined_v4_selection((request(),)).to_payload()
    if change == "malformed_date": body["requests"][0]["request"]["filing_date"] = "not-a-date"
    elif change == "wrong_form": body["requests"][0]["request"]["form_type"] = "3"
    else: body["requests"][0]["request"] = None
    with pytest.raises(m.CombinedV4Error): m.validate_combined_v4_selection_payload(body, observed=False)


def test_dirty_or_changed_supervisor_refuses_before_worker_or_inputs(monkeypatch):
    base = types.SimpleNamespace(_repository_snapshot=lambda: ("a" * 40, " M unrelated.py\n"))
    monkeypatch.setattr(m, "_base", lambda: base)
    monkeypatch.setattr(m, "_run_worker", lambda *args: pytest.fail("No worker/root execution"))
    with pytest.raises(m.CombinedV4Error, match="clean committed"):
        m.run_isolated_combined_v4(expected_head="a" * 40)


_CONTEXT_TOY = r'''
import hashlib, pathlib, sys, types
root=pathlib.Path(sys.argv[1]);basepath=root/'research/insider_buying_sec_recovery_v4_historical_replay.py'
b=types.ModuleType('_context_toy_base');b.__file__=str(basepath);sys.modules[b.__name__]=b
exec(compile(basepath.read_bytes(),str(basepath),'exec',dont_inherit=True),b.__dict__)
p=root/'research/insider_buying_sec_recovery_v4_combined.py'
m=types.ModuleType('_context_toy_worker');m.__file__=str(p);sys.modules[m.__name__]=m
source=p.read_bytes().decode()
if sys.argv[2]=='reverse':source=source.replace('selection._CAPTURED_BASE = base','pass  # invented guard reversal')
exec(compile(source,str(p),'exec',dont_inherit=True),m.__dict__)
sources=b._source_snapshot();blobs=tuple((p,dict(sources)[p])for p,_ in b.HISTORICAL_FILES)
sys.addaudithook(b._audit_event)
finder,view=m._install_source_context(b,blobs,sources)
import importlib
s=importlib.import_module('research.insider_buying_sec_recovery_v4_selection')
same=s._base()is b
count=sum(row['path']==m.BASE_PATH for row in finder.executed)
assert same and count==1, 'Accepted base was executed twice instead of explicitly context-bound'
assert s.__loader__ is finder and s.__cached__ is None
print('INVENTED_CONTEXT_ONLY_NO_ROOTS')
'''


@pytest.mark.parametrize("mode", ["correct", "reverse"])
def test_source_only_selection_context_prevents_duplicate_base_execution(mode):
    # Source-only wiring over real CODE bytes only; no retained data/roots,
    # historical acquisition, observed receipt or strategy outcome is accessed.
    result = subprocess.run((sys.executable, "-I", "-S", "-B", "-c", _CONTEXT_TOY,
        str(m._base().LANE_ROOT), mode), cwd=m._base().LANE_ROOT,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}, capture_output=True, timeout=10)
    if mode == "correct":
        assert result.returncode == 0, result.stderr.decode(errors="replace")
        assert result.stdout == b"INVENTED_CONTEXT_ONLY_NO_ROOTS\n"
    else: assert result.returncode != 0 and b"executed twice" in result.stderr


_AUDIT_TOY = '''import os,socket,sys,time
def _worker_main(b):
    if b['toy_mode']=='overflow': sys.stdout.buffer.write(b'x'*(1024*1024+1));return
    if b['toy_mode']=='timeout': time.sleep(2);return
    for operation in (lambda:socket.socket(),lambda:open('/tmp/INVENTED_FORBIDDEN_COMBINED_WRITE','wb'),lambda:os.fork()):
        try:operation()
        except _CAPTURED_BASE.HistoricalReplayError:pass
        else:raise AssertionError('Audit refusal was bypassed')
    sys.stdout.buffer.write(b'INVENTED_WORKER_CONTROLS_ONLY')
'''


@pytest.mark.parametrize("mode", ["controls", "overflow", "timeout"])
def test_genuine_bounded_worker_bootstrap_audit_and_launch_policy_with_invented_child(monkeypatch, mode):
    base = m._base(); raw_base = (base.LANE_ROOT / m.BASE_PATH).read_bytes()
    toy = _AUDIT_TOY.encode()
    bundle = {"current_sources": base._encode_sources(((m.BASE_PATH, raw_base),)),
        "base_source_sha256": m._sha(raw_base), "worker_source_b64": base64.b64encode(toy).decode(),
        "worker_source_sha256": m._sha(toy), "toy_mode": mode}
    actual_popen = m.subprocess.Popen
    def inherited_network_launch(command, **kwargs):
        assert command[:2] == ("/usr/bin/sandbox-exec", "-p")
        assert all(item in command[2] for item in ("(deny network*)", "(deny file-write*)", "(deny process-fork)", "(deny process-exec)"))
        assert command[4:7] == ("-I", "-S", "-B")
        assert kwargs["env"] == {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
        # macOS refuses nested Seatbelt launches (code71). Strip only that
        # launcher for INVENTED stdin; child still inherits OS network denial.
        # This proves the exact production policy/launch and base audit controls,
        # not independent OS all-write/fork denial or actual retained replay.
        return actual_popen(command[3:], **kwargs)
    monkeypatch.setattr(m.subprocess, "Popen", inherited_network_launch)
    if mode == "controls":
        result = m._run_worker(m._canonical(bundle), 5)
        assert result.returncode == 0 and result.stdout == b"INVENTED_WORKER_CONTROLS_ONLY"
    else:
        with pytest.raises(m.CombinedV4Error, match="cap exceeded" if mode == "overflow" else "timed out"):
            m._run_worker(m._canonical(bundle), 1)


@pytest.mark.parametrize("timeout", [0, 901, True, 1.5])
def test_new_worker_timeout_bound_is_exact900_and_never_launches(monkeypatch, timeout):
    monkeypatch.setattr(m.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("No worker launch"))
    with pytest.raises(m.CombinedV4Error, match="timeout"):
        m._run_worker(b"{}", timeout)
