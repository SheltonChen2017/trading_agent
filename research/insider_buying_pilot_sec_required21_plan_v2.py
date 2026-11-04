"""Fresh protected retained-input plan after the selected 20,052 consumption chain.

All 25 context quarters finish before the first eight required-window requests
seal. This operation has no transport, credential, original admission or QC
entry point. The old campaign's unchained-capture refusal remains unchanged.
Only new private controls use the separately qualified stable data receiver.
"""
from __future__ import annotations

import argparse
import errno
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid

from research import insider_buying_pilot_fmp_eod_qualification_v2 as storage
from research import insider_buying_pilot_sec_consumption_chain_v1 as chain_source
from research import insider_buying_pilot_sec_parent_audit_runner as base
from research import insider_buying_pilot_stable_custody_v2 as stable

SCHEMA = "insider-pilot-sec-required21-chained-plan-v2"
AUDIT_ID = "ib-required21-chained-plan-v2-20261103-once"
SELF_PATH = "research/insider_buying_pilot_sec_required21_plan_v2.py"
TEST_PATH = "tests/test_insider_buying_pilot_sec_required21_plan_v2.py"
LANE_ROOT, LANE_BRANCH = base.LANE_ROOT, base.LANE_BRANCH
MAX_CONTROL, MAX_EPOCH, WORKER_SECONDS = 2*1024**2, 16*1024**2, 900
STORAGE_RECEIPT_SHA256 = "e801524572f54c9c7415798386b5c579f66b35fcc46eb7a9b9e57aa977ad81b3"
ROSTER_SHA256 = "801661a5285ec79b02f1ce57e921eb3ff5116f23d671fcc64a64f0a896a364be"
AUDIT_SHA256 = "ce6a0a0eb678e0f90e9821efc1a0460808c5536202c1bb5407d9ec89b044f056"
CHAIN_SHA256 = "9a77f2b2130bce5b0ebcaa4ae90843bc7475811741cb9d6be63108646932d8e9"
CONSUMED_SHA256 = "9be3ca7b6999e0d4d0e6d2506b7a752915e000c7aa690fbf1188581356fe6a0f"
MANIFEST_SHA256 = "dc254e4e023bf9990028e085450fc4a5c1c2ae22e1d562f2efc4ada532f9f76d"
MANIFEST_BYTES = 34381
OWN_PATHS = (SELF_PATH, TEST_PATH,
    "research/insider_buying_pilot_sec_consumption_chain_v1.py", "tests/test_insider_buying_pilot_sec_consumption_chain_v1.py",
    "research/insider_buying_pilot_sec_required21_selection_v1.py", "tests/test_insider_buying_pilot_sec_required21_selection_v1.py",
    "research/insider_buying_pilot_sec_parent_audit_runner.py", "tests/test_insider_buying_pilot_sec_parent_audit_runner.py",
    "research/insider_buying_pilot_sec_parent_audit.py", "tests/test_insider_buying_pilot_sec_parent_audit.py",
    "research/insider_buying_pilot_sec_roster.py", "tests/test_insider_buying_pilot_sec_roster.py",
    "research/insider_buying_pilot_sec_exposure.py", "tests/test_insider_buying_pilot_sec_exposure.py",
    "research/insider_buying_affected_quarter_selector_verification_v2.py", "tests/test_insider_buying_affected_quarter_selector_verification_v2.py",
    "research/insider_buying_pilot_coverage_audit.py", "tests/test_insider_buying_pilot_coverage_audit.py",
    "research/insider_buying_sec_2006q1_parent_bootstrap.py", "tests/test_insider_buying_sec_2006q1_parent_bootstrap.py")
_raw, _sha = base._raw, base._sha
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_CODES = frozenset({"arguments_refused", "identity_refused", "storage_unqualified", "native_refused",
    "worker_refused", "input_refused", "chain_refused", "selection_refused", "output_refused", "cleanup_refused"})
_PHASES = frozenset({"arguments", "identity", "health", "proof", "reservation", "plan", "readback", "final"})
_NAMES = ("reservation.json", "storage-qualification.json", "observation-started.json", "plan.json", "complete.json")


class Required21PlanError(ValueError):
    """Finite codes only; no source body, path, accession or exception text."""


def _need(ok, code):
    if not ok:
        raise Required21PlanError(code)


def authority():
    return {"new_source_requests": 0, "credential_reads": 0, "qc_accesses": 0, "outcome_looks": 0,
        "backtests": 0, "dispatch_authorized": False, "original_parent_admission": False,
        "historical_public_known_by_verified": False, "point_in_time_data": False, "rights_verified": False,
        "canonical_admitted": False, "complete_required21_corpus": False, "backtesting_ready": False}


def registration(storage_receipt_sha256):
    _need(type(storage_receipt_sha256) is str and _SHA.fullmatch(storage_receipt_sha256), "storage_unqualified")
    return {"schema": SCHEMA+"/registration", "audit_id": AUDIT_ID,
        "purpose": "retained_input_non_dispatch_selection", "storage_receipt_sha256": storage_receipt_sha256,
        "context_periods": list(chain_source.selection.CONTEXT_PERIODS),
        "required_periods": list(chain_source.selection.REQUIRED_PERIODS), "maximum_selected": 8,
        "complete_source_rederivation_required": True, "intake_opaque_leaf_hashes": 84,
        "interpreted_quarter_count": 25, "interpreted_table": "SUBMISSION.tsv",
        "retained_parent_bodies": "opaque_hash_only_no_financial_XML_decode",
        "selected_consumption_chain_sha256": CHAIN_SHA256, "known_consumed_count": 20052,
        "consumed_accessions_sha256": CONSUMED_SHA256,
        "source_roster_sha256": ROSTER_SHA256, "parent_audit_sha256": AUDIT_SHA256,
        "manifest_sha256": MANIFEST_SHA256, "manifest_bytes": MANIFEST_BYTES,
        "maximum_leaf_bytes": MAX_CONTROL, "maximum_epoch_bytes": MAX_EPOCH,
        "worker_seconds": WORKER_SECONDS, "maximum_planning_worker_invocations": 1,
        "diagnostic_worker_roles": ["source_identity", "health", "proof", "readback"],
        "old_campaign_refusal_preserved": True, "new_SEC_or_provider_requests_permitted": False,
        "no_original_admission_or_readiness_promotion": True, "authority": authority()}


def _current(identity):
    storage._current(identity)
    _need(set(OWN_PATHS) <= set(identity["source_sha256"])
        and base.custody._source_bytes(LANE_ROOT, OWN_PATHS)
        == {name: identity["source_sha256"][name] for name in OWN_PATHS}, "identity_refused")


def _identity(head):
    _need(Path(__file__).resolve() == LANE_ROOT/SELF_PATH and Path.cwd() == LANE_ROOT, "identity_refused")
    loaded_identity = storage._identity(head)
    own = base.custody._source_bytes(LANE_ROOT, OWN_PATHS)
    for name, pin in own.items():
        _need(_sha(base.custody._git(LANE_ROOT, "show", head+":"+name)) == pin, "identity_refused")
    sources = {**loaded_identity["source_sha256"], **own}
    result = {**loaded_identity, "source_sha256": sources, "source_inventory_sha256": _sha(_raw(sources))}
    _current(result)
    proof_identity = _proof_source_identity(head)
    _proof_subset(proof_identity, result)
    return result, proof_identity


def _proof_subset(proof_identity, identity):
    # The fresh storage-only interpreter checked its current source closure.
    # Calling that dynamic-closure check again here would include this loaded
    # planner and mislabel the intentionally smaller proof identity as stale.
    keys = {"root", "branch", "head", "clean", "source_sha256", "source_inventory_sha256"}
    _need(type(proof_identity) is dict and type(identity) is dict
        and set(proof_identity) == set(identity) == keys
        and proof_identity["root"] == str(LANE_ROOT) and proof_identity["branch"] == LANE_BRANCH
        and proof_identity["clean"] is True
        and type(proof_identity["head"]) is str and re.fullmatch(r"[0-9a-f]{40}", proof_identity["head"])
        and type(proof_identity["source_sha256"]) is dict
        and set(storage.OWN_PATHS) <= set(proof_identity["source_sha256"])
        and proof_identity["source_inventory_sha256"] == _sha(_raw(proof_identity["source_sha256"]))
        and all(proof_identity[key] == identity[key] for key in ("root", "branch", "head", "clean"))
        and set(proof_identity["source_sha256"]) < set(identity["source_sha256"])
        and all(pin == identity["source_sha256"][name] for name, pin in proof_identity["source_sha256"].items()),
        "identity_refused")


def _proof_source_identity(head):
    # Source discovery includes loaded internal modules. A fresh interpreter
    # imports unchanged storage v2 alone so this proof keeps its own source
    # scope; the caller separately authenticates the complete planner union.
    code = ("import sys;sys.path.insert(0,"+repr(str(LANE_ROOT))+");"
        "from research import insider_buying_pilot_fmp_eod_qualification_v2 as m;"
        "m.legacy.native._isolated();m.legacy.custody._effective_denial(require_fork=False);"
        "g=m.legacy.native._WorkerMemoryGuard();\ntry:\n"
        " g.check();v=m._identity("+repr(head)+");g.check();w=m._raw({'ok':True,'value':v});"
        "sys.stdout.buffer.write(w+b'\\n');sys.stdout.buffer.flush();g.check()\nfinally:g.close()")
    command = ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec", "-p", _source_identity_policy(),
        sys.executable, "-I", "-S", "-B", "-X", "pycache_prefix="+chain_source.producer.EMPTY_CACHE_PREFIX, "-c", code)
    try: return storage.legacy.ipc._launch(command, b"", timeout=120)
    except Exception: raise Required21PlanError("identity_refused") from None


def _derive(chain, *, intake_manifest_raw, expected_manifest_sha256, selection_raw, expected_selection_sha256,
            quarter_inputs, exposure_raw, candidates_raw, master_for_period, expected_roster_sha256,
            expected_audit_sha256, fixture=False):
    _need(type(fixture) is bool, "input_refused")
    summary = chain_source.public_summary(chain)
    _need(summary["fixture_only"] is fixture, "chain_refused")
    if not fixture:
        _need(chain.sha256 == CHAIN_SHA256 and summary["consumed_count"] == 20052
            and summary["consumed_accessions_sha256"] == CONSUMED_SHA256
            and summary["selected_metadata_custody_verified"] is True
            and expected_roster_sha256 == ROSTER_SHA256 and expected_audit_sha256 == AUDIT_SHA256
            and expected_manifest_sha256 == MANIFEST_SHA256 and len(intake_manifest_raw) == MANIFEST_BYTES,
            "chain_refused")
    observed_old = set(base.compiler._exposures(base._decode(exposure_raw)))
    _need(observed_old <= set(chain_source.consumed_accessions(chain)), "chain_refused")
    builder = chain_source.required21_selection_builder(chain, limit=8)
    compiler = base.compiler.PilotSecParentAuditCompiler(exposure_raw=exposure_raw,
        expected_exposure_sha256=_sha(exposure_raw), candidates_raw=candidates_raw,
        expected_candidates_sha256=_sha(candidates_raw), master_for_period=master_for_period, emit_row=builder.consume)
    roster = base.roster.derive_pilot_sec_roster(intake_manifest_raw=intake_manifest_raw,
        expected_manifest_sha256=expected_manifest_sha256, selection_raw=selection_raw,
        expected_selection_sha256=expected_selection_sha256, quarter_inputs=quarter_inputs,
        consume_row=compiler.consume, fixture_only=fixture)
    audit = compiler.finish(roster)
    chosen = builder.finish(source_roster=roster, parent_audit=audit,
        expected_roster_sha256=expected_roster_sha256, expected_audit_sha256=expected_audit_sha256)
    _need(roster.sha256 == expected_roster_sha256 and audit.sha256 == expected_audit_sha256, "input_refused")
    return {"plan": chosen.to_payload(), "plan_sha256": chosen.sha256,
        "source_roster": roster.to_payload(), "parent_audit": audit.to_payload(), "consumption": summary,
        "exposure_inventory_sha256": _sha(exposure_raw), "retained_body_inventory_sha256": _sha(candidates_raw)}


def _result(derived, identity, *, fixture=False):
    # Keep the full factories internal. The old audit report also embeds a
    # large exposure inventory, which must never inflate this control/IPC path.
    compact = {key: value for key, value in derived.items() if key not in {"source_roster", "parent_audit"}}
    compact.update(source_roster_sha256=_sha(_raw(derived["source_roster"])),
        parent_audit_sha256=_sha(_raw(derived["parent_audit"])),
        source_roster_counts=derived["source_roster"]["counts"],
        parent_context_counts=derived["parent_audit"]["context_counts"])
    return {"schema": SCHEMA+"/plan", "audit_id": AUDIT_ID, "fixture_only": fixture,
        "execution_identity": identity, **compact, "native_network_fork_allwrite_securityexec_denial": True,
        "provider_requests": 0, "credential_reads": 0, "qc_accesses": 0, "outcome_looks": 0, "backtests": 0,
        "dispatch_authorized": False, "canonical_admitted": False, "backtesting_ready": False}


def _validate_result(value, identity, *, fixture=False):
    keys = {"schema", "audit_id", "fixture_only", "execution_identity", "plan", "plan_sha256", "source_roster_sha256",
        "parent_audit_sha256", "source_roster_counts", "parent_context_counts", "consumption", "exposure_inventory_sha256", "retained_body_inventory_sha256",
        "native_network_fork_allwrite_securityexec_denial", "provider_requests", "credential_reads", "qc_accesses",
        "outcome_looks", "backtests", "dispatch_authorized", "canonical_admitted", "backtesting_ready"}
    _need(type(fixture) is bool and type(value) is dict and set(value) == keys
        and value["schema"] == SCHEMA+"/plan" and value["audit_id"] == AUDIT_ID
        and value["fixture_only"] is fixture and _raw(value["execution_identity"]) == _raw(identity)
        and value["native_network_fork_allwrite_securityexec_denial"] is True, "selection_refused")
    _need(all(type(value[key]) is int and value[key] == 0 for key in
        ("provider_requests", "credential_reads", "qc_accesses", "outcome_looks", "backtests"))
        and all(value[key] is False for key in ("dispatch_authorized", "canonical_admitted", "backtesting_ready")),
        "selection_refused")
    selected = chain_source.selection.validate_selection_payload(value["plan"])
    _need(selected["fixture_only"] is fixture and selected["limit"] == 8
        and value["plan_sha256"] == _sha(_raw(selected))
        and selected["source_roster_sha256"] == value["source_roster_sha256"]
        and selected["parent_audit_sha256"] == value["parent_audit_sha256"]
        and _raw(selected["source_roster_counts"]) == _raw(value["source_roster_counts"])
        and _raw(selected["parent_context_counts"]) == _raw(value["parent_context_counts"]), "selection_refused")
    summary = value["consumption"]
    summary_keys = {"schema", "fixture_only", "control_sha256", "prior_count", "started_added_count", "consumed_count",
        "consumed_accessions_sha256", "selected_metadata_custody_verified", "full_root_inventory_verified",
        "claim_start_result_leaves_replayed", "original_bodies_replayed", "producer_git_images_verified_here",
        "archive_membership_known", "unknown_prior_archive_memberships_remain_unknown", "new_source_requests",
        "original_body_reads", "credential_reads", "qc_accesses", "outcome_looks", "backtests", "authority", "chain_sha256"}
    _need(type(summary) is dict and set(summary) == summary_keys and summary["schema"] == chain_source.SCHEMA
        and summary["fixture_only"] is fixture
        and selected["consumption_sha256"] == summary["chain_sha256"]
        and selected["consumed_accessions_sha256"] == summary["consumed_accessions_sha256"]
        and len(selected["consumed_accessions"]) == summary["consumed_count"]
        and summary["full_root_inventory_verified"] is summary["claim_start_result_leaves_replayed"]
            is summary["original_bodies_replayed"] is summary["producer_git_images_verified_here"]
            is summary["archive_membership_known"] is False
        and summary["selected_metadata_custody_verified"] is (not fixture)
        and summary["unknown_prior_archive_memberships_remain_unknown"] is True
        and _raw(summary["authority"]) == _raw(chain_source.producer._authority()), "chain_refused")
    _need(all(type(summary[key]) is int and summary[key] == 0 for key in
        ("new_source_requests", "original_body_reads", "credential_reads", "qc_accesses", "outcome_looks", "backtests"))
        and all(type(summary[key]) is int and 0 <= summary[key] <= chain_source.selection.MAX_CONSUMED
            for key in ("prior_count", "started_added_count", "consumed_count"))
        and 1 <= summary["started_added_count"] <= 8
        and summary["consumed_count"] == summary["prior_count"]+summary["started_added_count"], "chain_refused")
    pins = summary["control_sha256"]
    _need(type(pins) is dict and set(pins) == set(chain_source.CONTROL_PINS)
        and all(type(pin) is str and _SHA.fullmatch(pin) for pin in pins.values()), "chain_refused")
    reconstructed = {key: item for key, item in summary.items() if key != "chain_sha256"}
    reconstructed["accessions"] = selected["consumed_accessions"]
    _need(_sha(_raw(reconstructed)) == summary["chain_sha256"], "chain_refused")
    for field in ("exposure_inventory_sha256", "retained_body_inventory_sha256"):
        _need(type(value[field]) is str and _SHA.fullmatch(value[field]), "selection_refused")
    if not fixture:
        _need(summary["chain_sha256"] == CHAIN_SHA256 and summary["consumed_count"] == 20052
            and summary["consumed_accessions_sha256"] == CONSUMED_SHA256
            and summary["selected_metadata_custody_verified"] is True
            and selected["source_roster_sha256"] == ROSTER_SHA256
            and selected["parent_audit_sha256"] == AUDIT_SHA256, "chain_refused")
    _need(len(_raw(value)) <= MAX_CONTROL, "output_refused")
    return json.loads(_raw(value))


def _plan_actual(identity, memory):
    accepted = intake = None
    holds = []
    try:
        chain = chain_source.read_actual_chain(memory=memory)
        accepted = base.prior._Held(LANE_ROOT)
        base.prior._selector(accepted, base.prior.ACTUAL_ANCHORS)
        selected = accepted.leaf(base.prior.SELECTOR_PARTS, "selection.json", base.prior.MAX_CONTROL,
            base.prior.ACTUAL_ANCHORS.selection)
        holds, exposure_raw, snapshot_raw, candidates = base.exposure.observe_exposures(
            base.exposure.actual_roots(), fixture_only=False)
        candidates = base.exposure.hash_candidate_bodies(holds, candidates)
        masters = next(item for item in holds if item.spec.root_id == "masters-v3")
        intake = base.selector._HeldIntake()
        result = _derive(chain, intake_manifest_raw=intake.manifest_raw,
            expected_manifest_sha256=intake.context["manifest_sha256"], selection_raw=selected,
            expected_selection_sha256=base.prior.ACTUAL_ANCHORS.selection,
            quarter_inputs=base.roster.held_context_quarters(intake), exposure_raw=exposure_raw,
            candidates_raw=candidates, master_for_period=lambda period: base._master(masters.tree, period),
            expected_roster_sha256=ROSTER_SHA256, expected_audit_sha256=AUDIT_SHA256)
        # Operational snapshot is rederived and held, never promoted or copied.
        _need(type(snapshot_raw) is bytes and snapshot_raw, "input_refused")
        intake.recheck(); accepted.recheck()
        for held in holds: held.recheck()
        _need(chain_source.read_actual_chain(memory=memory).sha256 == chain.sha256, "chain_refused")
        memory.check(); _current(identity)
        return _validate_result(_result(result, identity), identity)
    finally:
        base.selector._close_all((intake, accepted, *reversed(holds)), phase="required21_plan_cleanup")


def _scope_paths():
    """Fixed source paths only; constructing this tuple performs no I/O."""
    roots = [LANE_ROOT.joinpath(*base.selector.INPUT_PARTS), LANE_ROOT.joinpath(*base.prior.SELECTOR_PARTS),
        LANE_ROOT.joinpath(*base.prior.OBSERVER_PARTS)]
    roots.extend(spec.path for spec in base.exposure.actual_roots())
    leaves = [LANE_ROOT.joinpath(*chain_source.ROOT_PARTS, name) for name in
        ("scope.lock", "complete.json", "reservation.json", "plan.json", "consumed-index.json")]
    leaves.extend(LANE_ROOT.joinpath(*chain_source.PRIOR_PARTS, name) for name in ("scope.lock", "consumed-index.json"))
    return tuple(roots), tuple(leaves)


def _choices(paths, subtrees=()):
    clauses = ["(literal "+json.dumps(str(path))+")" for path in sorted(set(paths))]
    clauses.extend("(subpath "+json.dumps(str(path))+")" for path in sorted(set(subtrees)))
    return "(require-any "+" ".join(clauses)+")"


def _policy(role):
    _need(role in {"health", "proof", "plan", "readback"}, "arguments_refused")
    if role == "proof": return storage._policy("proof")
    policy = '(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    roots, leaves = _scope_paths() if role == "plan" else ((), ())
    ancestors = {p for path in (*roots, *leaves) for p in (path, *path.parents) if p.is_relative_to(LANE_ROOT.parent)}
    allowed = _choices(ancestors, roots) if ancestors else None
    artifact = LANE_ROOT/"artifacts"
    policy += '(deny file-read* '+('(require-all (subpath '+json.dumps(str(artifact))+') (require-not '+allowed+'))' if allowed else '(subpath '+json.dumps(str(artifact))+')')+')'
    # The exposure observer has an explicit fixed set of retained sibling roots.
    siblings = _choices({LANE_ROOT.parent, *ancestors}, (LANE_ROOT, *roots))
    policy += '(deny file-read* (require-all (subpath '+json.dumps(str(LANE_ROOT.parent))+') (require-not '+siblings+')))'
    data = stable.PRIVATE_CUSTODY_ROOT
    if role == "readback":
        permitted = _choices({data}, (data/AUDIT_ID,))
        policy += '(deny file-read* (require-all (subpath '+json.dumps(str(data))+') (require-not '+permitted+')))'
    else: policy += '(deny file-read* (subpath '+json.dumps(str(data))+'))'
    for path in (Path("/Volumes"), Path("/Users/sheltonchen/Library/Keychains")):
        policy += '(deny file-read* (subpath '+json.dumps(str(path))+'))'
    return policy


def parent_native_policy():
    """Network-denied controller; Git may fork and only its fresh data epoch writes.

    Git's shared administrative tree is permitted; no sibling checkout source
    is used. The old synthetic probe is readable and can never be rewritten.
    """
    policy = _policy("plan").replace('(deny process-fork)', '')
    # Git must be able to stat tracked ZIP pointers; unrelated source data
    # remains unreadable. The actual plan worker retains the stricter read*.
    marker = '(deny file-read* (require-all (subpath '+json.dumps(str(LANE_ROOT/'artifacts'))+')'
    policy = policy.replace(marker, marker.replace('file-read*', 'file-read-data'))
    policy = policy.replace('(deny file-write*)', '')
    data = stable.PRIVATE_CUSTODY_ROOT
    policy = policy.replace('(deny file-read* (subpath '+json.dumps(str(data))+'))', '')
    permitted_data = _choices({data}, (data/storage.PROBE_ID, data/AUDIT_ID))
    policy += '(deny file-read* (require-all (subpath '+json.dumps(str(data))+') (require-not '+permitted_data+')))'
    permitted_writes = _choices({Path('/dev/null'), data}, (data/AUDIT_ID,))
    policy += '(deny file-write* (require-not '+permitted_writes+'))'
    # The plan child excludes all sibling checkouts. The controller additionally
    # needs only this common Git directory for no-optional-locks status/show.
    roots, leaves = _scope_paths()
    ancestors = {p for path in (*roots, *leaves) for p in (path, *path.parents) if p.is_relative_to(LANE_ROOT.parent)}
    old = _choices({LANE_ROOT.parent, *ancestors}, (LANE_ROOT, *roots))
    new = _choices({LANE_ROOT.parent, *ancestors, LANE_ROOT.parent/'trading_agent'},
        (LANE_ROOT, *roots, LANE_ROOT.parent/'trading_agent'/'.git'))
    return policy.replace('(require-not '+old+')', '(require-not '+new+')')


def _source_identity_policy():
    policy = _policy("health").replace('(deny process-fork)', '')
    policy = policy.replace('(deny file-write*)', '(deny file-write* (require-not (literal "/dev/null")))')
    policy = policy.replace('(deny file-read* (subpath '+json.dumps(str(LANE_ROOT/'artifacts'))+'))',
        '(deny file-read-data (subpath '+json.dumps(str(LANE_ROOT/'artifacts'))+'))')
    old = _choices({LANE_ROOT.parent}, (LANE_ROOT,))
    new = _choices({LANE_ROOT.parent, LANE_ROOT.parent/'trading_agent'},
        (LANE_ROOT, LANE_ROOT.parent/'trading_agent'/'.git'))
    return policy.replace('(require-not '+old+')', '(require-not '+new+')')


def _parent_native(memory):
    _need(type(memory) is chain_source.producer.previous._WorkerMemoryGuard, "native_refused")
    base.custody._effective_denial(require_fork=False)
    try: os.execve('/usr/bin/security', ['security', 'help'], {'PATH': '/usr/bin:/bin'})
    except OSError as error: _need(error.errno in {errno.EPERM, errno.EACCES}, "native_refused")
    else: raise Required21PlanError('native_refused')
    probe = Path('/private/tmp')/('ib-required21-parent-denial-'+uuid.uuid4().hex)
    try: fd = os.open(probe, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
    except OSError as error: _need(error.errno in {errno.EPERM, errno.EACCES}, 'native_refused')
    else:
        os.close(fd)
        raise Required21PlanError('native_refused')
    memory.check()


def _worker(role, identity, supplied=None):
    memory = None
    try:
        chain_source.producer.previous._isolated()
        base._prove_isolation()
        memory = chain_source.producer.previous._WorkerMemoryGuard()
        _current(identity); memory.check()
        _need(type(supplied) is dict, "input_refused")
        if role == "health":
            _need(supplied == {}, "input_refused")
            value = {"passed": True, "source_only": True, "authority": authority()}
        elif role == "proof":
            # A separate unchanged 164-source identity qualifies the old probe.
            _need(set(supplied) == {"proof_identity", "sha256"}, "input_refused")
            _proof_subset(supplied["proof_identity"], identity)
            value = storage._proof(supplied["proof_identity"], {"sha256": supplied["sha256"]}, memory)
        elif role == "plan":
            _need(supplied == {}, "input_refused")
            value = _plan_actual(identity, memory)
        elif role == "readback":
            _need(set(supplied) == {"complete_sha256"}, "input_refused")
            value = stable.read_epoch_controls(AUDIT_ID, list(_NAMES),
                {"complete.json": {"bytes": None, "sha256": supplied["complete_sha256"]}}, memory=memory)
        else: raise Required21PlanError("arguments_refused")
        _current(identity); memory.check()
        wire = {"passed": True, "value": value}
    except Exception as error:
        code = str(error) if type(error) is Required21PlanError and str(error) in _CODES else "worker_refused"
        wire = {"passed": False, "code": code}
    try:
        if memory is not None: memory.check()
        encoded = _raw({"ok": True, "value": wire}); _need(len(encoded) <= MAX_CONTROL, "output_refused")
        sys.stdout.buffer.write(encoded+b"\n"); sys.stdout.buffer.flush()
        if memory is not None: memory.check()
    finally:
        if memory is not None: memory.close()


def _child(role, identity, supplied=None):
    _need(role in {"health", "proof", "plan", "readback"}, "arguments_refused")
    supplied = {} if supplied is None else supplied
    code = "import sys,json;sys.path.insert(0,"+repr(str(LANE_ROOT))+");from research import insider_buying_pilot_sec_required21_plan_v2 as m;raw=sys.stdin.buffer.read(m.MAX_CONTROL+1);m._need(len(raw)<=m.MAX_CONTROL,'input_refused');m._worker("+repr(role)+",json.loads("+repr(_raw(identity).decode())+"),json.loads(raw.decode()))"
    command = ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec", "-p", _policy(role),
        sys.executable, "-I", "-S", "-B", "-X", "pycache_prefix="+chain_source.producer.EMPTY_CACHE_PREFIX, "-c", code)
    payload = _raw(supplied); _need(len(payload) <= MAX_CONTROL, "input_refused")
    try: result = storage.legacy.ipc._launch(command, payload, timeout=WORKER_SECONDS if role == "plan" else 120)
    except Exception: raise Required21PlanError("worker_refused") from None
    _need(type(result) is dict and type(result.get("passed")) is bool, "worker_refused")
    if result["passed"] is not True:
        _need(set(result) == {"passed", "code"} and result["code"] in _CODES, "worker_refused")
        raise Required21PlanError(result["code"])
    _need(set(result) == {"passed", "value"}, "worker_refused")
    return result["value"]


def _publish(context, result):
    _validate_result(result, context.identity, fixture=context.fixture)
    pin = context.publish("plan.json", result)
    complete = {"schema": SCHEMA+"/complete", "audit_id": AUDIT_ID, "fixture_only": context.fixture,
        "execution_identity": context.identity, "registration_sha256": _sha(_raw(context.registration)),
        "plan_control_sha256": pin, "selection_sha256": result["plan_sha256"], "storage_identity": context.storage_identity,
        "published_leaf_pins": {name: {"bytes": value["bytes"], "sha256": value["sha256"]}
            for name, value in context.pins.items()}, "authority": authority()}
    complete_pin = context.publish("complete.json", complete)
    context.check()
    return complete_pin


def run_invented(epoch, result):
    _need(type(epoch) is stable.Epoch and epoch.fixture is True
        and _raw(epoch.registration) == _raw(registration(epoch.registration.get("storage_receipt_sha256"))),
        "arguments_refused")
    return _publish(epoch, _validate_result(result, epoch.identity, fixture=True))


def run_actual(expected_head, storage_receipt_sha256):
    phase, context, memory = "identity", None, None
    answer = {"passed": False, "phase": phase, "code": "worker_refused"}
    began = time.monotonic_ns()
    try:
        _need(storage_receipt_sha256 == STORAGE_RECEIPT_SHA256, "storage_unqualified")
        memory = chain_source.producer.previous._WorkerMemoryGuard()
        _parent_native(memory)
        identity, proof_identity = _identity(expected_head)
        stable.production_parent_current(identity)
        phase = "health"; health = _child("health", identity)
        _need(health == {"passed": True, "source_only": True, "authority": authority()}, "native_refused")
        phase = "proof"; proof = _child("proof", identity,
            {"proof_identity": proof_identity, "sha256": storage_receipt_sha256})
        _need(proof["passed"] is True and proof["fixture_only"] is False
            and proof["receipt_sha256"] == storage_receipt_sha256
            and proof["qualification_head"] == expected_head
            and proof["qualification_source_inventory_sha256"] == proof_identity["source_inventory_sha256"],
            "storage_unqualified")
        phase = "reservation"; context = stable.Epoch(identity, registration(storage_receipt_sha256))
        _need(context.storage_identity == proof["storage_identity"], "storage_unqualified")
        context.publish("storage-qualification.json", proof)
        context.publish("observation-started.json", {"schema": SCHEMA+"/observation-started", "audit_id": AUDIT_ID,
            "execution_identity": identity, "registration_sha256": _sha(_raw(context.registration)),
            "storage_qualification_sha256": context.pins["storage-qualification.json"]["sha256"],
            "maximum_planning_worker_invocations": 1, "started_monotonic_ns": time.monotonic_ns(), "authority": authority()})
        phase = "plan"; result = _validate_result(_child("plan", identity), identity)
        context.check(); _need(context.storage_identity == proof["storage_identity"], "storage_unqualified")
        complete_pin = _publish(context, result)
        phase = "readback"; back = _child("readback", identity, {"complete_sha256": complete_pin})
        _need(set(back) == {"schema", "audit_id", "controls", "pins", "storage_identity"}
            and back["schema"] == stable.SCHEMA+"/readback" and back["audit_id"] == AUDIT_ID
            and set(back["controls"]) == set(_NAMES)
            and back["storage_identity"] == context.storage_identity
            and back["pins"] == {name: {"bytes": pin["bytes"], "sha256": pin["sha256"]}
                for name, pin in context.pins.items()}
            and _raw(back["controls"]["plan.json"]) == _raw(result)
            and _raw(back["controls"]["storage-qualification.json"]) == _raw(proof), "output_refused")
        phase = "final"; context.check(); stable.production_parent_current(identity); memory.check()
        answer = {"passed": True, "audit_id": AUDIT_ID, "complete_sha256": complete_pin,
            "plan_control_sha256": context.pins["plan.json"]["sha256"], "selection_sha256": result["plan_sha256"],
            "selected_count": result["plan"]["selected_count"],
            "underfilled": result["plan"]["underfilled"], "consumed_count": 20052,
            "elapsed_nanoseconds": time.monotonic_ns()-began, "authority": authority()}
    except Exception as error:
        if type(error) is stable.CustodyError:
            safe = stable.safe_failure(error)
            answer = {"passed": False, "phase": phase, "code": safe["code"], "role": safe["role"], "changed_fields": safe["changed_fields"]}
        else:
            answer = {"passed": False, "phase": phase,
                "code": str(error) if type(error) is Required21PlanError and str(error) in _CODES else "worker_refused"}
    finally:
        try: base.selector._close_all((context, memory), phase="required21_parent_cleanup")
        except BaseException:
            if answer["passed"]: answer = {"passed": False, "phase": "final", "code": "cleanup_refused"}
    return answer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--storage-receipt-sha256", required=True)
    args = parser.parse_args()
    result = run_actual(args.expected_head, args.storage_receipt_sha256)
    print(_raw(result).decode())
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
