"""Invented complete journals and pure multi-run prefixes; no retained roots."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import types

import pytest

from research import insider_buying_sec_recovery_v4_reconciliation as m
from research import insider_buying_sec_recovery_v4_capture as capture
from research import insider_buying_sec_recovery_v4_projection as projection
from research import insider_buying_sec_recovery_v4_continuation_capture as continuation
from research import insider_buying_sec_recovery_v4_combined as combined
from research.insider_buying.sec_complete_submission import project_sec_complete_submission
from test_insider_buying_sec_recovery_v4_projection import request, parent, captured
from test_insider_buying_sec_recovery_v4_continuation_capture import run as continued


def test_all_accepted_source_pins_are_exact_current_code_bytes_not_report_literals():
    # CODE ONLY. No actual source roots, capture bodies, contact or outcomes.
    for path, digest in m._PINS.items():
        assert len(digest) == 64
        assert hashlib.sha256((m._base().LANE_ROOT / path).read_bytes()).hexdigest() == digest


def save(tmp_path, ident, raw):
    target = tmp_path.resolve().joinpath("artifacts", "insider_buying", "sec_recovery_v4_projection", ident)
    target.mkdir(parents=True, mode=0o700)
    path = target / "receipt.json"; path.write_bytes(raw); path.chmod(0o600)
    return path


def descriptor(tmp_path, result, saved, raw, *, profile, ident):
    run = tmp_path.resolve().joinpath(*capture.ARTIFACT_PARTS, "runs", result["capture_id"])
    reservation = json.loads((run / "reservation.json").read_bytes())
    return {"profile": profile, "capture_id": result["capture_id"], "report_sha256": result["report_sha256"],
        "capture_producer_head": reservation["capture_git_commit"],
        "capture_source_inventory_sha256": reservation["selection"]["current_source_inventory_sha256"],
        "selection_sha256": result["selection_sha256"], "selected_prefix_sha256": result["selected_prefix_sha256"],
        "projection_id": ident, "projection_receipt_sha256": m._sha(raw), "projection_receipt_size_bytes": len(raw),
        "projection_consumer_head": "c" * 40, "projection_consumer_inventory_sha256": "d" * 64,
        "projection_rows_sha256": saved.get("ordered_rows_sha256", saved.get("projection_rows_sha256")),
        "completed_parents": result["completed_request_bound_bodies"], "retained_body_bytes": result["retained_body_bytes"]}


def fixture(tmp_path, *, count=2, add_continuation=False):
    originals = tuple(request(index + 1) for index in range(100 + count + 5))
    first, _ = captured(tmp_path, items=originals[100:100 + count])
    p = projection._project_root(first["capture_id"], first["report_sha256"], root=tmp_path.resolve(), observed=False,
        consumer=lambda: {"declared_projection_repository_head": "c" * 40, "current_source_inventory_sha256": "d" * 64}).to_payload()
    raw = projection._raw(p); save(tmp_path, "invented-first-projection", raw)
    descriptors = [descriptor(tmp_path, first, p, raw, profile="first64-v4", ident="invented-first-projection")]
    if add_continuation:
        # Both accepted invented selection factories number their own rows from
        #100. This genuine joint custody fixture is valid, but cannot pretend to
        # be an original-order continuation: the pure prefix gate must refuse.
        result, _, _, _ = continued(tmp_path, items=originals[100 + count:102 + count])
        saved = continuation._verify_capture(result["capture_id"], result["report_sha256"], root=tmp_path.resolve(), observed=False, project_retained=True)
        saved["consumer"] = {"declared_repository_head": "c" * 40, "current_source_inventory_sha256": "d" * 64}
        raw = continuation._raw(saved); save(tmp_path, "invented-next-projection", raw)
        descriptors.append(descriptor(tmp_path, result, saved, raw, profile="combined-continuation-v1", ident="invented-next-projection"))
    inventory = {"kind": m.INVENTORY_VERSION, "scope": "invented_test_only", "runs": descriptors}
    raw_inventory = m._canonical(inventory)
    partition = [{"global_index": index, "request_sha256": m._digest(req),
        "source_class": "prior_completed" if index < 100 else "originally_unattempted"} for index, req in enumerate(originals)]
    return originals, partition, inventory, raw_inventory


def receipt(tmp_path, *, count=2):
    originals, partition, inventory, raw = fixture(tmp_path, count=count)
    result = m.reconcile_invented_capture_inventory(originals, partition, root=tmp_path.resolve(), capture_inventory_raw=raw,
        expected_capture_inventory_sha256=m._sha(raw), maximum_preview_requests=3)
    return result, inventory


def test_genuine_invented_journal_receipt_is_readonly_full_accounting_and_compact(tmp_path):
    result, inventory = receipt(tmp_path)
    body = result.to_payload()
    assert type(result) is m.InventedReconciledV4Receipt and body["scope"] == "invented_test_only"
    assert body["fresh_completed_parents"] == body["claim_inventory_count"] == 2
    assert body["prior_source_bound_count"] == 100 and body["remaining_unattempted_count"] == 5
    assert body["combined_request_bound_custody_count"] == 102
    assert body["capture_inventory"] == inventory and body["capture_inventory_sha256"] == m._digest(inventory)
    assert body["completed_run_count"] == 1
    assert [row["global_index"] for row in body["next_request_preview"]] == [102, 103, 104]
    assert body["authority"] == m._authority() and result.sha256 == m._digest(body)
    assert b"987654.321" not in result.raw_bytes and b"Invented Owner" not in result.raw_bytes
    assert b"ownershipDocument" not in result.raw_bytes and b"header_owner_ciks" not in result.raw_bytes
    before = {str(p): m._sha(p.read_bytes()) for p in tmp_path.rglob("*") if p.is_file()}
    closed, _, snapshot = m._run_closures(tmp_path.resolve(), inventory, observed=False)
    assert len(closed[0]["rows"]) == snapshot["claim_inventory_count"] == 2
    assert before == {str(p): m._sha(p.read_bytes()) for p in tmp_path.rglob("*") if p.is_file()}


def test_two_actual_invented_journal_families_project_and_bind_but_wrong_global_prefix_refuses(tmp_path):
    originals, partition, inventory, raw = fixture(tmp_path, add_continuation=True)
    closed, verified, snapshot = m._run_closures(tmp_path.resolve(), inventory, observed=False)
    assert len(closed) == len(verified) == 2 and snapshot["claim_inventory_count"] == 4
    assert all(row["counts"]["complete_parent_projected"] == 2 for row in verified)
    with pytest.raises(m.ReconciliationV4Error, match="concatenated original eligible prefix"):
        m.reconcile_invented_capture_inventory(originals, partition, root=tmp_path.resolve(), capture_inventory_raw=raw,
            expected_capture_inventory_sha256=m._sha(raw))


def pure_population(*, first=64, second=256, remaining=4):
    # Pure supplied descriptor test, NOT an acquisition journal or observed seal.
    # Actual pure parser produces every parent/child digest; claim/start/result
    # anchors are explicitly invented metadata. Real custody is tested above.
    originals = tuple(request(index + 1) for index in range(100 + first + second + remaining))
    partition = [{"global_index": index, "request_sha256": m._digest(req),
        "source_class": "prior_completed" if index < 100 else "originally_unattempted"} for index, req in enumerate(originals)]
    closed, offset = [], 100
    for ident, count in (("invented-first", first), ("invented-continuation", second)):
        rows = []
        for ordinal in range(count):
            item = originals[offset + ordinal]; raw = parent(item); target = projection._target(item)
            parsed = project_sec_complete_submission(target, raw); payload = parsed.to_payload()
            rows.append({"ordinal": ordinal, "global_index": offset + ordinal, "request_sha256": m._digest(item), "target": target.to_payload(),
                "claim_sha256": m._digest({"invented_claim": offset + ordinal}), "start_sha256": m._digest({"invented_start": offset + ordinal}),
                "result_sha256": m._digest({"invented_result": offset + ordinal}), "raw_parent": {"sha256": m._sha(raw), "size_bytes": len(raw)},
                "disposition": "complete_parent_projected_noncanonical", "projection": {"payload_sha256": parsed.sha256,
                    "header_sha256": payload["children"]["header"]["sha256"], "primary_xml_sha256": payload["children"]["primary_xml"]["sha256"]}})
        closed.append({"capture_id": ident, "rows": rows}); offset += count
    return originals, partition, closed


def test_pure_320_parent_two_run_prefix_accounts_all_without_256_closure_cap():
    originals, partition, closed = pure_population()
    result = m._reconcile_partition(originals, partition, closed, maximum_preview_requests=256)
    assert result["fresh_completed_parents"] == 320 and result["completed_run_count"] == 2
    assert result["remaining_unattempted_count"] == 4 and result["combined_request_bound_custody_count"] == 420
    assert [row["global_index"] for row in result["next_request_preview"]] == [420, 421, 422, 423]
    expected = copy.deepcopy(partition)
    for row in expected[100:420]: row["source_class"] = "fresh_v4_completed"
    assert result["combined_partition_sha256"] == m._digest(expected)
    assert result["remaining_inventory_sha256"] == m._digest(partition[420:])
    assert partition[100]["source_class"] == "originally_unattempted"


@pytest.mark.parametrize("fault", ["swap_runs", "reverse_second", "omit_first", "omit_second", "duplicate_run", "wrong_target", "duplicate_body", "quarantine", "bool_index", "wrong_child"])
def test_no_permutation_omission_or_duplicate_can_become_remaining_inventory(fault):
    originals, partition, closed = pure_population(first=2, second=3)
    if fault == "swap_runs": closed.reverse()
    elif fault == "reverse_second": closed[1]["rows"].reverse()
    elif fault == "omit_first": closed[0]["rows"].pop()
    elif fault == "omit_second": closed[1]["rows"].pop(0)
    elif fault == "duplicate_run": closed[1]["capture_id"] = closed[0]["capture_id"]
    elif fault == "wrong_target": closed[1]["rows"][0]["target"]["quarterly_index_sha256"] = "0" * 64
    elif fault == "duplicate_body": closed[1]["rows"][0]["raw_parent"]["sha256"] = closed[0]["rows"][0]["raw_parent"]["sha256"]
    elif fault == "quarantine": closed[1]["rows"][0]["disposition"] = "complete_parent_grammar_quarantine"
    elif fault == "bool_index": closed[0]["rows"][0]["global_index"] = True
    else: closed[1]["rows"][0]["projection"]["header_sha256"] = "invalid"
    with pytest.raises(m.ReconciliationV4Error): m._reconcile_partition(originals, partition, closed, maximum_preview_requests=2)


def test_true_scope_exhaustion_is_accounted_without_empty_ready_or_dispatch_claim():
    originals, partition, closed = pure_population(first=2, second=3, remaining=0)
    body = m._reconcile_partition(originals, partition, closed, maximum_preview_requests=256)
    assert body["remaining_unattempted_count"] == 0 and body["next_request_preview"] == []
    assert body["combined_request_bound_custody_count"] == body["total_parents"] == 105
    assert body["remaining_inventory_sha256"] == m._digest([])


@pytest.mark.parametrize("fault", ["body", "saved_sha", "saved_row", "old_consumer", "old_inventory", "report", "extra_claim", "extra_run", "missing_claim", "lock"])
def test_changed_saved_receipt_journal_or_whole_claim_namespace_refuses(tmp_path, fault):
    _, _, inventory, _ = fixture(tmp_path)
    descriptor = inventory["runs"][0]
    root = tmp_path.resolve().joinpath(*capture.ARTIFACT_PARTS)
    run = root / "runs" / descriptor["capture_id"]
    saved_path = tmp_path.resolve().joinpath("artifacts", "insider_buying", "sec_recovery_v4_projection", descriptor["projection_id"], "receipt.json")
    if fault == "body": next((run / "objects").iterdir()).write_bytes(b"changed")
    elif fault == "saved_sha": descriptor["projection_receipt_sha256"] = "0" * 64
    elif fault in {"saved_row", "old_consumer", "old_inventory"}:
        saved = json.loads(saved_path.read_bytes())
        if fault == "saved_row": saved["rows"][0]["projection"]["payload_sha256"] = "0" * 64
        elif fault == "old_consumer": saved["consumer"]["declared_projection_repository_head"] = "b" * 40
        else: saved["consumer"]["current_source_inventory_sha256"] = "e" * 64
        raw = projection._raw(saved); saved_path.write_bytes(raw)
        descriptor["projection_receipt_sha256"], descriptor["projection_receipt_size_bytes"] = m._sha(raw), len(raw)
    elif fault == "report": (run / "complete.json").write_bytes(b"{}\n")
    elif fault == "extra_claim": (root / "claims" / ("0" * 64 + ".json")).write_bytes(b"unknown"); (root / "claims" / ("0" * 64 + ".json")).chmod(0o600)
    elif fault == "extra_run": (root / "runs" / "unknown-incomplete-run").mkdir(mode=0o700)
    elif fault == "missing_claim": next((root / "claims").iterdir()).unlink()
    else: (root / "capture.lock").write_bytes(b"wrong\n")
    with pytest.raises((m.ReconciliationV4Error, ValueError)):
        m._run_closures(tmp_path.resolve(), inventory, observed=False)


def test_retained_parent_change_during_final_saved_receipt_readback_is_not_unchecked(tmp_path, monkeypatch):
    _, _, inventory, _ = fixture(tmp_path)
    cid = inventory["runs"][0]["capture_id"]
    body_path = next(tmp_path.resolve().joinpath(*capture.ARTIFACT_PARTS, "runs", cid, "objects").iterdir())
    original, reads = capture._Directory.read, []
    def changed(folder, name, **kwargs):
        raw = original(folder, name, **kwargs)
        if name == "receipt.json":
            reads.append(name)
            if len(reads) == 2: body_path.write_bytes(b"INVENTED_CHANGED_AFTER_PROJECT_AND_JOURNAL_REPLAY")
        return raw
    monkeypatch.setattr(capture._Directory, "read", changed)
    with pytest.raises(m.ReconciliationV4Error, match="retained body changed"):
        m._run_closures(tmp_path.resolve(), inventory, observed=False)


@pytest.mark.parametrize("fault", ["wrong_hash", "noncanonical", "reordered", "third_run", "profile", "bool_count", "unknown_key", "producer", "size"])
def test_external_inventory_is_exact_exhaustive_and_never_inferred_from_successes(fault):
    inventory = copy.deepcopy(m.OBSERVED_CAPTURE_INVENTORY)
    if fault == "reordered": inventory["runs"].reverse()
    elif fault == "third_run": row = copy.deepcopy(inventory["runs"][1]); row["capture_id"] = "unknown-third"; inventory["runs"].append(row)
    elif fault == "profile": inventory["runs"][1]["profile"] = "inferred-closure"
    elif fault == "bool_count": inventory["runs"][0]["completed_parents"] = True
    elif fault == "unknown_key": inventory["runs"][0]["retroactive_approval"] = True
    elif fault == "producer": inventory["runs"][1]["capture_producer_head"] = "bad"
    elif fault == "size": inventory["runs"][0]["projection_receipt_size_bytes"] = 0
    raw = m._canonical(inventory)
    if fault == "noncanonical": raw += b"\n"
    sha = "0" * 64 if fault == "wrong_hash" else m._sha(raw)
    with pytest.raises(m.ReconciliationV4Error): m._inventory(raw, sha, observed=True)


def test_pinned_observed_inventory_is_valid_metadata_not_an_observed_execution_seal():
    assert m._inventory(m.OBSERVED_CAPTURE_INVENTORY_BYTES, m.OBSERVED_CAPTURE_INVENTORY_SHA256, observed=True) == m.OBSERVED_CAPTURE_INVENTORY
    assert [row["completed_parents"] for row in m.OBSERVED_CAPTURE_INVENTORY["runs"]] == [64, 256]
    assert m.OBSERVED_CAPTURE_INVENTORY_SHA256 == m._digest(m.OBSERVED_CAPTURE_INVENTORY)


@pytest.mark.parametrize("value", [[], {}])
def test_nonstring_inventory_profile_is_a_typed_refusal(value):
    inventory = copy.deepcopy(m.OBSERVED_CAPTURE_INVENTORY)
    inventory["runs"][1]["profile"] = value
    raw = m._canonical(inventory)
    with pytest.raises(m.ReconciliationV4Error): m._inventory(raw, m._sha(raw), observed=True)


@pytest.mark.parametrize("value", [[], {}])
def test_nonstring_original_class_is_a_typed_refusal(value):
    originals, partition, closed = pure_population(first=1, second=1)
    partition[0]["source_class"] = value
    with pytest.raises(m.ReconciliationV4Error): m._reconcile_partition(originals, partition, closed, maximum_preview_requests=2)


@pytest.mark.parametrize("fault", ["image", "mutable", "equal_token", "detached", "observed_relabel"])
def test_factory_receipt_identity_anchor_cannot_be_mutated_or_relabelled(tmp_path, fault):
    obj, _ = receipt(tmp_path)
    if fault == "image": body = obj.to_payload(); body["repository_head"] = "b" * 40; object.__setattr__(obj, "_raw", m._canonical(body))
    elif fault == "mutable": object.__setattr__(obj, "_raw", bytearray(obj.raw_bytes))
    elif fault == "equal_token":
        class Equal:
            def __eq__(self, other): return True
        object.__setattr__(obj, "_token", Equal())
    elif fault == "detached": obj = m.InventedReconciledV4Receipt(obj.raw_bytes, obj._token)
    else: obj = m.ReconciledV4Receipt(obj.raw_bytes, m._TOKEN)
    with pytest.raises(m.ReconciliationV4Error): obj.to_payload()


@pytest.mark.parametrize("field", ["fresh_completed_parents", "remaining_unattempted_count", "prior_source_bound_count", "claim_inventory_count"])
def test_receipt_boolean_cannot_substitute_for_integer_accounting(tmp_path, field):
    obj, _ = receipt(tmp_path); body = obj.to_payload(); body[field] = True
    with pytest.raises(m.ReconciliationV4Error): m._validate_body(body, observed=False)


def test_dirty_supervisor_refuses_before_original_roots_or_worker(monkeypatch):
    monkeypatch.setattr(m, "_base", lambda: types.SimpleNamespace(_repository_snapshot=lambda: ("a" * 40, " M lane_record\n")))
    monkeypatch.setattr(m, "_run_worker", lambda *args: pytest.fail("No original roots/worker launch"))
    with pytest.raises(m.ReconciliationV4Error, match="clean committed"):
        m.run_isolated_reconciliation_v4(expected_head="a" * 40)


_CONTEXT = r'''
import importlib,pathlib,sys,types
root=pathlib.Path(sys.argv[1]); p=root/'research/insider_buying_sec_recovery_v4_historical_replay.py'
base=types.ModuleType('_invented_reconcile_base');base.__file__=str(p);sys.modules[base.__name__]=base
exec(compile(p.read_bytes(),str(p),'exec',dont_inherit=True),base.__dict__)
p=root/'research/insider_buying_sec_recovery_v4_reconciliation.py';m=types.ModuleType('_invented_reconcile_context');m.__file__=str(p);sys.modules[m.__name__]=m
source=p.read_bytes().decode()
if sys.argv[2]=='reverse':source=source.replace('combined._CAPTURED_BASE = base','pass # invented binding reversal')
exec(compile(source,str(p),'exec',dont_inherit=True),m.__dict__)
sources=base._source_snapshot();blobs=tuple((p,dict(sources)[p])for p,_ in base.HISTORICAL_FILES)
sys.addaudithook(base._audit_event)
finder,view=m._install_source_context(base,blobs,sources)
combined=importlib.import_module('research.insider_buying_sec_recovery_v4_combined')
selection=importlib.import_module('research.insider_buying_sec_recovery_v4_selection')
assert selection._base()is base and combined._base()is base, 'Accepted base was executed twice'
assert sum(row['path']==m.BASE_PATH for row in finder.executed)==1
assert combined.__loader__ is finder and selection.__loader__ is finder and combined.__cached__ is None
print('INVENTED_SOURCE_CONTEXT_ONLY_NO_ROOTS')
'''


@pytest.mark.parametrize("mode", ["correct", "reverse"])
def test_source_only_current_context_binds_both_old_factories_without_hidden_duplicate_execution(mode):
    result = subprocess.run((sys.executable, "-I", "-S", "-B", "-c", _CONTEXT, str(m._base().LANE_ROOT), mode),
        cwd=m._base().LANE_ROOT, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}, capture_output=True, timeout=10)
    if mode == "correct":
        assert result.returncode == 0, result.stderr.decode(errors="replace")
        assert result.stdout == b"INVENTED_SOURCE_CONTEXT_ONLY_NO_ROOTS\n"
    else: assert result.returncode != 0 and b"executed twice" in result.stderr


_AUDIT = '''import os,socket,sys,time
def _worker_main(b):
    if b['toy']=='overflow':sys.stdout.buffer.write(b'x'*(1024*1024+1));return
    if b['toy']=='timeout':time.sleep(2);return
    for call in (lambda:socket.socket(),lambda:open('/tmp/INVENTED_RECONCILIATION_FORBIDDEN','wb'),lambda:os.fork()):
        try:call()
        except _CAPTURED_BASE.HistoricalReplayError:pass
        else:raise AssertionError('Audit refusal bypass')
    sys.stdout.buffer.write(b'INVENTED_AUDIT_ONLY')
'''


@pytest.mark.parametrize("mode", ["controls", "overflow", "timeout"])
def test_exact_bounded_worker_launcher_and_source_bootstrap_with_invented_child(monkeypatch, mode):
    base = m._base(); raw = (base.LANE_ROOT / m.BASE_PATH).read_bytes(); toy = _AUDIT.encode()
    bundle = {"current_sources": base._encode_sources(((m.BASE_PATH, raw),)), "base_source_sha256": m._sha(raw),
        "worker_source_b64": base64.b64encode(toy).decode(), "worker_source_sha256": m._sha(toy), "toy": mode}
    actual = m.subprocess.Popen
    def launch(command, **kwargs):
        assert command[:2] == ("/usr/bin/sandbox-exec", "-p")
        assert all(s in command[2] for s in ("(deny network*)", "(deny file-write*)", "(deny process-fork)", "(deny process-exec)"))
        assert command[4:7] == ("-I", "-S", "-B") and kwargs["env"] == {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
        # Only invented stdin strips the nested Seatbelt launcher (macOS71).
        # Child inherits pytest OS network denial; base audit guards writes/fork.
        # Not independent OS all-write/fork evidence and not a retained replay.
        return actual(command[3:], **kwargs)
    monkeypatch.setattr(m.subprocess, "Popen", launch)
    if mode == "controls":
        result = m._run_worker(m._canonical(bundle), 5)
        assert result.returncode == 0 and result.stdout == b"INVENTED_AUDIT_ONLY"
    else:
        with pytest.raises(m.ReconciliationV4Error, match="cap exceeded" if mode == "overflow" else "timed out"):
            m._run_worker(m._canonical(bundle), 1)


@pytest.mark.parametrize("timeout", [0, 901, True, 1.5])
def test_exact900_second_timeout_refuses_before_launch(monkeypatch, timeout):
    monkeypatch.setattr(m.subprocess, "Popen", lambda *a, **k: pytest.fail("No process launch"))
    with pytest.raises(m.ReconciliationV4Error, match="timeout"): m._run_worker(b"{}", timeout)


# Section 153 (Claude review): a same-count registry whose claim names differ from
# the completed runs' own claims had no isolating control.
def test_claim_registry_with_same_count_but_foreign_claim_name_refuses(tmp_path):
    originals, partition, inventory, raw = fixture(tmp_path)
    claims = tmp_path.resolve().joinpath(*capture.ARTIFACT_PARTS, "claims")
    victim = sorted(claims.iterdir())[0]
    victim.rename(claims / ("f" * 64 + ".json"))
    with pytest.raises(m.ReconciliationV4Error):
        m.reconcile_invented_capture_inventory(originals, partition, root=tmp_path.resolve(), capture_inventory_raw=raw,
            expected_capture_inventory_sha256=m._sha(raw), maximum_preview_requests=3)
