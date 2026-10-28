"""Finite registered source-only count coordinator; no source admission.

The old archive's finite context closes before any new chunk begins.  Its
original closed model is lineage, not a perpetual assertion about old files.
Only this outer factory may issue terminal accounting after every original
source/code/output/storage context and all original-pin audits have closed.
No caller callback, JSON receipt, complete flag or pair closure is authority.
"""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import _thread
import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
import time

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf import native_count_recovery_budget as research_budget
from research.short_interest_etf import native_count_epoch_ledger as epoch_model
from scripts import load_short_interest_count_epoch_ledger as archive_loader
from scripts import short_interest_lane_batch_guard as lane
from scripts import short_interest_count_durable_budget as accounting
from scripts import short_interest_count_durable_transport as transport
from scripts import short_interest_count_control_custody as controls
from scripts import short_interest_count_response_custody as responses
from scripts import short_interest_count_response_volume as storage
from scripts import short_interest_closed_count_chunk as reader
from scripts import short_interest_count_negative_custody as negative
from scripts import short_interest_count_transport_union as transport_union
from scripts import short_interest_count_checkpoint as checkpoints
from scripts import short_interest_count_source_authority as source_scope
from scripts import diagnose_short_interest_body_receipt_custody as antecedent

ROOT, BRANCH = transport.ROOT, lane.BRANCH
SOURCE_AUTHORITY_SHA256 = "9d67d93ad79657031befd8849659bc20fc5834173d76a569bccb9307347e3a6c"
RUN_PROTOCOL_SHA256 = "14818d707b17eef1a6b9ba26416c3c0a4dd82cdc33c8819130ffcd3cb8cc4b29"
NEGATIVE_PRESERVATION_POLICY_SHA256 = "e0e8df728d96dfaae20b43497ad150557d9a767e5d853d020ec6b9acfcc0423c"
BASELINE_LEDGER_SHA256 = research_budget.BASELINE_LEDGER_SHA256
MAXIMUM_CHUNK_SECONDS, MAXIMUM_ARCHIVES = 3600, 1
MAXIMUM_WORKERS = 8
DRIVER = "scripts/capture_short_interest_durable_counts.py"
HOLD_REPORT_DIRECTORY = ROOT / "artifacts/short_interest/count_hold_reports"
_ARCHIVES, _ARCHIVE_PLANS, _ARCHIVE_FAILED = {}, {}, set()
_LEASES, _LEASE_FAILED, _LEASE_TERMINALS, _LEASE_PHASES, _LEASE_CLOCKS = {}, set(), {}, {}, {}
_RUNS, _RUN_ORIGINS, _TERMINALS, _TERMINAL_ORIGINS, _TERMINAL_FAILED = {}, {}, {}, {}, set()
_DIRECTORIES, _PRESERVATION_HOLD = {}, {}
_PRESERVATION_LEASES, _NEGATIVE_STATUS, _NEGATIVE_ATTEMPTED = {}, {}, set()
_PRESERVATION_PROFILES = {}
_NEGATIVE_ORIGINS = {}
_NEGATIVE_FINAL_ATTEMPTED = set()
_BLOCKED_OPERATIONS, _RETENTION_ANNOUNCED = set(), set()
_PRESERVATION_FAILURES, _PRESERVATION_FAILURE_ORIGINS = {}, {}
_HOLD_BASELINE = (13992, 23452681, 84005, 4 * 1024 ** 3, 2097152)
_SOURCE_BATCHES, _SOURCE_BATCH_FAILED = {}, set()
_SETTLED_CONTRIBUTIONS, _CONTRIBUTION_ORIGINS = {}, {}
_CHECKPOINT_FACTS, _CHECKPOINT_FACTS_FAILED = {}, set()
_CHECKPOINT_CAPS, _CHECKPOINT_ROUND = {}, {}
_WRITTEN_CHECKPOINTS = {}
_ATTEMPT_SLOTS, _ATTEMPT_BY_TICKET, _RESPONSE_SLOTS = {}, {}, {}
_ATTEMPT_USED, _RESPONSE_USED, _ATTEMPT_RESULTS = set(), set(), {}
_WORKER_RETAINED = {}
_RLOCK_TYPE = type(_thread.RLock())
_CODES = frozenset("""durable_capture_registration_pending durable_capture_exact_root_required
durable_capture_archive_factory_required durable_capture_archive_not_closed
durable_capture_archive_changed durable_capture_archive_capacity durable_capture_archive_baseline
durable_capture_plan_changed durable_capture_lease_factory_required durable_capture_lease_changed
durable_capture_lease_failed durable_capture_lease_not_live durable_capture_lease_not_closed
durable_capture_clock_refused durable_capture_window_exhausted durable_capture_code_changed
durable_capture_terminal_required durable_capture_terminal_changed durable_capture_terminal_reused
durable_capture_candidate_changed durable_capture_member_changed durable_capture_directory_changed
durable_capture_fd_close_failed durable_capture_negative_preservation_pending
durable_capture_unqualified_result durable_capture_retry_exhausted durable_capture_preservation_changed
durable_capture_retention_required durable_capture_START_evidence_required
durable_capture_START_evidence_changed durable_capture_contribution_changed
durable_capture_checkpoint_changed durable_capture_checkpoint_required
durable_capture_worker_slot_changed durable_capture_worker_stage_failed
durable_capture_CLI_arguments_refused durable_capture_hold_report_refused""".split())
_HOLD_CONTRACT_CODES = frozenset((*_CODES, *transport.diagnostics.LOCAL_CONTRACT_CODES,
    *(name for module in (transport, controls, responses, storage, reader, accounting, negative,
        transport_union, checkpoints, source_scope, negative.primitive, negative.immutable,
        negative.creator) for name in module._CODES)))


class DurableCountCaptureRefusal(ValueError): pass


def require(value, code):
    if not value: raise DurableCountCaptureRefusal("REFUSED: " + code)


def authority():
    return {"source_only": True, "transport_accounting_only": True, "source_admitted": False,
        "denominator_admitted": False, "historical_PIT_admitted": False,
        "actual_input_execution_admitted": False, "ready_for_backtest": False,
        "outcome_looks": 0, "qc_attempts": 0, "trading_authority": False}


def code_paths():
    return tuple(sorted(set((*archive_loader.code_paths(), *antecedent.code_paths(), DRIVER,
        "scripts/short_interest_count_durable_budget.py", "scripts/short_interest_count_durable_transport.py",
        "scripts/short_interest_count_control_custody.py", "scripts/short_interest_count_response_custody.py",
        "scripts/short_interest_count_response_volume.py", "scripts/short_interest_closed_count_chunk.py",
        "scripts/short_interest_count_negative_custody.py",
        "scripts/short_interest_count_transport_union.py",
        "scripts/short_interest_count_checkpoint.py",
        "scripts/short_interest_count_source_authority.py",
        "research/short_interest_etf/native_count_recovery_budget.py"))))


def protocol():
    return {"schema": "si-durable-count-capture-v1", "source_authority_sha256": SOURCE_AUTHORITY_SHA256,
        "operator_protocol_sha256": transport.PROTOCOL_SHA256,
        "negative_preservation_policy_sha256": NEGATIVE_PRESERVATION_POLICY_SHA256,
        "checkpoint_policy_sha256": checkpoints.CHECKPOINT_POLICY_SHA256,
        "archive_baseline_sha256": BASELINE_LEDGER_SHA256, "archive_context": "original_closed_before_new_chunk",
        "maximum_chunk_seconds": MAXIMUM_CHUNK_SECONDS, "maximum_archives": MAXIMUM_ARCHIVES,
        "maximum_inflight": 8, "positions_per_chunk": 512, "extra_STARTs_per_chunk": 16,
        "worker_batch": MAXIMUM_WORKERS,
        "worker_order": "Main_reserve_remote_roster_START_received_dirs_workers_START_GET_received_Main_conditional_response_dirs_workers_pair_join_before_retry",
        "maximum_cumulative_STARTs": 84005, "maximum_cumulative_bytes": 4 * 1024 ** 3,
        "per_file_creation_seconds": 8, "volume_whole_seconds": 3600,
        "directory_width": 6, "payload": "capture", "external_claim": "claim/claim.spent.json",
        "manifest": "all_capture_files_except_self_pinned_separately_original_typed_controls",
        "closed_control": "terminal_intent_only_until_original_outer_finish",
        "negative_preservation": "LIVE_independent_lease_before_claim_or_key_failed_already_received_only_inside_volume_drain",
        "negative_blocker": "fixed_allowlisted_original_failure_and_authenticated_pure_journal_or_explicit_unknown_before_mandatory_no_network_process_retention",
        "hold_report": "max2MiB_content_addressed_owner_only_exclusive_original_parent_directory_and_file_anchors_positive_write_progress_file_directory_parent_fsync_original_inode_exact_readback_terminal_full_stamp_before_stdout_failure_never_releases_retention",
        "negative_final": "once_issued_preservation_manifest_after_wire_drain_all_reserved_debits_unknowns_not_process_closure",
        "remote_START_evidence": "fresh_exact_origin_ref_original_SourceLease_at_most8_exact_ticket_roster_before_START_creator",
        "contribution": "original_reader_snapshot_immediately_after_chunkclosure_before_irreversible_settle_then_original_account7_only",
        "transport_union": "all_original_ordered_contributions_and_pure_original_settlement_journal_no_expired_reader_clock",
        "checkpoint": "provisional_full_original_file_seals_and_same_mounted_epoch_roots_Main_independent_known_EXIT0_required",
        "same_original_mounted_epoch_only": True, "reattach_or_resume": False,
        "bound_antecedent_not_runtime_imported": [antecedent.previous.WRAPPER, antecedent.WRAPPER],
        "code_paths": list(code_paths()), "authority": authority()}


def failure_summary(error):
    if type(error) is DurableCountCaptureRefusal:
        args = BaseException.args.__get__(error, BaseException)
        code = (next((name for name in _CODES if args[0] == "REFUSED: " + name), None)
            if type(args) is tuple and len(args) == 1 and type(args[0]) is str else None)
        return {"category": "local_contract_refusal", "contract_code": code, "errno_name": None}
    for module, name in ((transport, "CountTransportRefusal"), (controls, "CountControlRefusal"),
        (responses, "CountResponseRefusal"), (storage, "CountResponseVolumeRefusal"),
        (reader, "ClosedCountChunkRefusal"), (accounting, "DurableCountBudgetRefusal"),
        (negative, "NegativePreservationRefusal"), (transport_union, "CountTransportUnionRefusal"),
        (checkpoints, "CountCheckpointRefusal"), (source_scope, "CountSourceAuthorityRefusal")):
        if type(error) is getattr(module, name, None): return module.failure_summary(error)
    return transport.failure_summary(error)


def _digest(value): return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def registered():
    require(all(_digest(value) for value in (SOURCE_AUTHORITY_SHA256, RUN_PROTOCOL_SHA256,
        NEGATIVE_PRESERVATION_POLICY_SHA256, transport.PROTOCOL_SHA256))
        and SOURCE_AUTHORITY_SHA256 == transport.SOURCE_AUTHORITY_SHA256 == source_scope.registered_sha256()
        and hash_payload(transport.policy()) == transport.PROTOCOL_SHA256
        and hash_payload(protocol()) == RUN_PROTOCOL_SHA256
        and NEGATIVE_PRESERVATION_POLICY_SHA256 == negative.PRESERVATION_POLICY_SHA256
        and BASELINE_LEDGER_SHA256 == research_budget.BASELINE_LEDGER_SHA256
        and type(MAXIMUM_CHUNK_SECONDS) is int and MAXIMUM_CHUNK_SECONDS == 3600
        and type(MAXIMUM_ARCHIVES) is int and MAXIMUM_ARCHIVES == 1
        and type(MAXIMUM_WORKERS) is int and MAXIMUM_WORKERS == 8,
        "durable_capture_registration_pending")
    # Check registrations before old replay, new images, claims, keys or HTTP.
    negative._registered(); checkpoints._registered()


def _require_lane_root(root):
    require(type(root) is type(ROOT) and root == ROOT and root.resolve() == root
        and Path.cwd().resolve() == root, "durable_capture_exact_root_required")


class OriginalClosedArchiveToken:
    __slots__ = ("_anchor", "_identity")
    def __init__(self): raise DurableCountCaptureRefusal("REFUSED: durable_capture_archive_factory_required")
    def __repr__(self): return "<OriginalClosedArchiveToken source-only; redacted>"


def _archive_binding(token):
    try:
        saved = _ARCHIVES.get(token) if type(token) is OriginalClosedArchiveToken else None
        require(type(saved) is tuple and len(saved) == 8 and saved[0] is token
            and token._anchor is token._identity is saved and token not in _ARCHIVE_FAILED,
            "durable_capture_archive_changed")
        wrapper, original, model = saved[1:4]
        require(type(wrapper) is archive_loader.RegisteredCountEpochLedger and wrapper._anchor is original
            and type(model) is epoch_model.CountEpochLedger and original[0] is model,
            "durable_capture_archive_changed")
        summary = wrapper.closed_summary(); raw = canonical_json(summary).encode()
        model._guard()
        require(raw == saved[4] and hash_bytes(raw) == saved[5]
            and summary["status"] == "closed_offline_source_only_slice"
            and summary["model_ledger_sha256"] == model.sha256 == BASELINE_LEDGER_SHA256
            and model._parts[1].query_plan is saved[6], "durable_capture_archive_baseline")
        return saved
    except BaseException:
        if type(token) is OriginalClosedArchiveToken: _ARCHIVE_FAILED.add(token)
        raise


def _token_from_original_closed_archive(wrapper):
    require(type(wrapper) is archive_loader.RegisteredCountEpochLedger,
        "durable_capture_archive_factory_required")
    summary = wrapper.closed_summary()  # Genuine producer rejects LIVE/provisional/failed contexts.
    original = wrapper._anchor; model = original[0]
    require(type(model) is epoch_model.CountEpochLedger and summary["model_ledger_sha256"]
        == model.sha256 == BASELINE_LEDGER_SHA256, "durable_capture_archive_baseline")
    require(len(_ARCHIVES) < MAXIMUM_ARCHIVES and not any(row[1] is wrapper for row in _ARCHIVES.values()),
        "durable_capture_archive_capacity")
    value = object.__new__(OriginalClosedArchiveToken); raw = canonical_json(summary).encode()
    anchor = value, wrapper, original, model, raw, hash_bytes(raw), model._parts[1].query_plan, object()
    value._anchor = value._identity = anchor; _ARCHIVES[value] = anchor
    _archive_binding(value); return value


def sourcelease_model(token):
    """Exact closed pure archive model; never a row, input or readiness loader."""
    return _archive_binding(token)[3]


def freeze_recovery_from_archive(token):
    original = _archive_binding(token)
    require(token not in _ARCHIVE_PLANS, "durable_capture_plan_changed")
    plan = research_budget.freeze_count_recovery_plan(original[3])
    _ARCHIVE_PLANS[token] = plan; return plan


def load_registered_closed_archive(root, *, runtime_head, actual_remote, complete_code_manifest):
    registered()  # Before old archive replay, new namespace, key or claim.
    with archive_loader.load_registered_count_epoch_ledger(root, runtime_head=runtime_head,
            actual_remote=actual_remote, complete_code_manifest=complete_code_manifest) as loaded:
        require(type(loaded) is archive_loader.RegisteredCountEpochLedger,
            "durable_capture_archive_factory_required")
    return _token_from_original_closed_archive(loaded)


def _drain_fds(fds):
    failed = False
    while fds:
        try: os.close(fds.pop())
        except BaseException: failed = True
    require(not failed, "durable_capture_fd_close_failed")


def _manifest_shape(manifest):
    require(type(manifest) is dict and tuple(sorted(manifest)) == code_paths()
        and all(type(key) is str and _digest(value) for key, value in manifest.items()),
        "durable_capture_code_changed")
    return tuple(sorted(manifest.items()))


def _code_identity(head, manifest):
    return hash_payload({"git_commit": head,
        "files": [{"path": name, "sha256": digest} for name, digest in manifest]})


def _audit_code(root, guard, manifest, held=None):
    guard.refresh(); stamps = []
    for name, digest in manifest:
        path = root / name
        if held is None:
            with archive_loader.count.old.cache.HeldFiles((path,), protected=False, boundary=guard.check) as file:
                raw = file.read(path, 8 * 1024 ** 2)
                committed = archive_loader.count.old.cache._git(root, ["show", guard.binding()[1] + ":" + name], guard)
                require(hash_bytes(raw) == hash_bytes(committed) == digest, "durable_capture_code_changed")
                file.check(); stamps.append((path, archive_loader.snapshot._file_stamp(path.lstat())))
        else:
            raw = held.read(path, 8 * 1024 ** 2)
            committed = archive_loader.count.old.cache._git(root, ["show", guard.binding()[1] + ":" + name], guard)
            require(hash_bytes(raw) == hash_bytes(committed) == digest, "durable_capture_code_changed")
            stamps.append((path, archive_loader.snapshot._file_stamp(path.lstat())))
    if held is not None: held.check()
    guard.refresh()
    for path, original in stamps:
        guard.check()
        require(archive_loader.snapshot._file_stamp(path.lstat()) == original, "durable_capture_code_changed")


class CountSourceLease:
    __slots__ = ("_anchor", "_identity")
    def __init__(self): raise DurableCountCaptureRefusal("REFUSED: durable_capture_lease_factory_required")
    def __repr__(self): return "<CountSourceLease redacted>"


def _lease_latch(lease):
    if type(lease) is CountSourceLease: _LEASE_FAILED.add(lease)


def _lease_record(lease):
    record = _LEASES.get(lease) if type(lease) is CountSourceLease else None
    require(type(record) is tuple and len(record) == 7 and lease._anchor is lease._identity is record[0]
        and type(record[0]) is tuple and len(record[0]) == 16 and record[0][0] is lease
        and lease not in _LEASE_FAILED and type(record[4]) is list and len(record[4]) == 1
        and record[4][0] is _LEASE_PHASES.get(lease) and type(record[6]) is list and len(record[6]) == 1
        and record[6][0] == _LEASE_CLOCKS.get(lease), "durable_capture_lease_changed")
    return record


def _lease_window(record):
    anchor, token, code, guard, state, policy_sha, previous = record
    now = time.monotonic()
    require(type(now) in (int, float) and 0 <= anchor[14] <= previous[0] <= now <= 2 ** 53,
        "durable_capture_clock_refused")
    require(now - anchor[14] < MAXIMUM_CHUNK_SECONDS, "durable_capture_window_exhausted")
    previous[0] = now
    _LEASE_CLOCKS[anchor[0]] = now


def source_lease_binding(lease):
    """Original16; structural lineage only, not perpetual old-file custody."""
    try:
        record = _lease_record(lease); anchor = record[0]
        with anchor[12]:
            require(type(anchor[12]) is _RLOCK_TYPE and record[5] == hash_payload(protocol())
                and anchor[9] == SOURCE_AUTHORITY_SHA256 and anchor[10] == transport.PROTOCOL_SHA256,
                "durable_capture_lease_changed")
            archive = _archive_binding(record[1]); plan = _ARCHIVE_PLANS.get(record[1])
            with accounting._lock(anchor[5]):
                actual_plan, unused = anchor[5]._guard(owner=False)
            require(actual_plan is plan is anchor[4] and plan._parts[1] is archive[3]
                and anchor[6] is archive[6] and tuple(anchor[7]) == anchor[7]
                and _code_identity(anchor[2], anchor[7]) == anchor[8], "durable_capture_plan_changed")
            return anchor
    except BaseException: _lease_latch(lease); raise


def source_lease_live_binding(lease):
    try:
        anchor = source_lease_binding(lease); record = _lease_record(lease)
        with anchor[12]:
            require(record[4][0] == "LIVE" and lease not in _LEASE_TERMINALS,
                "durable_capture_lease_not_live")
            _lease_window(record); record[3].check(); record[2].check(); _lease_window(record)
            return anchor
    except BaseException: _lease_latch(lease); raise


def source_lease_terminal_binding(lease):
    try:
        anchor = source_lease_binding(lease); record = _lease_record(lease)
        with anchor[12]:
            witness = _LEASE_TERMINALS.get(lease)
            require(record[4][0] == "CLOSED" and type(witness) is tuple and len(witness) == 5
                and witness[0] is anchor and witness[1] is record and type(witness[3]) is object,
                "durable_capture_lease_not_closed")
            _lease_window(record); record[3].check()
            require(transport.legacy.parallel.clock(anchor[13]) <= transport.legacy.parallel.clock(witness[4])
                <= transport.legacy.parallel.clock(transport._clock()), "durable_capture_clock_refused")
            _lease_window(record)
            return anchor
    except BaseException: _lease_latch(lease); raise


def _source_boundary(lease):
    """Original callback routes by issued context phase, never a caller flag."""
    record = _lease_record(lease)
    if record[4][0] == "LIVE": return source_lease_live_binding(lease)
    return source_lease_terminal_binding(lease)


class SourceStartBatchEvidence:
    __slots__ = ("_anchor", "_identity")
    def __init__(self): raise DurableCountCaptureRefusal("REFUSED: durable_capture_START_evidence_required")
    def __repr__(self): return "<SourceStartBatchEvidence exact opaque roster; redacted>"


def source_lease_authorize_start_batch(lease, operation, tickets):
    """Fresh actual-ref evidence before the unchanged START creation window."""
    source = source_lease_live_binding(lease); op = transport.active_operation_binding(operation)
    require(op[12] is lease and type(tickets) is tuple and 1 <= len(tickets) <= 8
        and len({id(ticket) for ticket in tickets}) == len(tickets)
        and len(_SOURCE_BATCHES) < 70013, "durable_capture_START_evidence_required")
    with source[12]:
        for ticket in tickets:
            bound = accounting.active_ticket_binding(ticket)
            require(bound[1] is source[5] and bound[2] is source[4] and bound[3] == op[4],
                "durable_capture_START_evidence_required")
        record = _lease_record(lease)
        evidence = record[3].refresh()
        source_lease_live_binding(lease)
        require(type(evidence) is lane.LaneEvidence, "durable_capture_START_evidence_changed")
        payload = evidence.payload()
        require(type(payload) is dict and payload.get("schema") == "si-bounded-batch-lane-evidence-v1"
            and payload.get("HEAD") == source[2] and payload.get("branch") == BRANCH
            and payload.get("actual_remote") == source[3] and payload.get("actual_ref") == lane.REF
            and payload.get("status") == "clean" and type(payload.get("maximum_HTTP_slots")) is int
            and payload["maximum_HTTP_slots"] == 8, "durable_capture_START_evidence_changed")
        value = object.__new__(SourceStartBatchEvidence)
        anchor = value, operation, source, op, tickets, evidence, hash_payload(payload), object()
        value._anchor = value._identity = anchor; _SOURCE_BATCHES[value] = anchor
        return value


def source_start_batch_binding(value):
    try:
        original = _SOURCE_BATCHES.get(value) if type(value) is SourceStartBatchEvidence else None
        require(type(original) is tuple and len(original) == 8 and original[0] is value
            and value._anchor is value._identity is original and value not in _SOURCE_BATCH_FAILED
            and source_lease_binding(original[2][0]) is original[2]
            and transport.operation_binding(original[1]) is original[3]
            and hash_payload(original[5].payload()) == original[6], "durable_capture_START_evidence_changed")
        for ticket in original[4]:
            bound = accounting.ticket_binding(ticket)
            require(bound[1] is original[3][1] and bound[2] is original[3][2] and bound[3] == original[3][4],
                "durable_capture_START_evidence_changed")
        return original
    except BaseException:
        if type(value) is SourceStartBatchEvidence: _SOURCE_BATCH_FAILED.add(value)
        raise


def _expected_output(root, plan, chunk):
    return root / storage.PARENT / (storage.NAMESPACE_PREFIX + "-" + plan.sha256 + f"-chunk{chunk:03d}") / storage.MOUNT_NAME / "capture"


@contextmanager
def _prepare_registered_source_lease(token, budget, *, root, runtime_head, actual_remote, complete_code_manifest):
    registered()
    require(root == ROOT and root.resolve() == root and Path.cwd().resolve() == root,
        "durable_capture_exact_root_required")
    source_scope.require_dispatch_allowed()
    archive = _archive_binding(token); plan = _ARCHIVE_PLANS.get(token)
    require(type(budget) is accounting.DurableCountBudget and type(plan) is research_budget.CountRecoveryPlan
        and budget.plan is plan and plan._parts[1] is archive[3], "durable_capture_plan_changed")
    manifest = _manifest_shape(complete_code_manifest); guard = lane.LaneGuard(root,
        expected_head=runtime_head, expected_remote=actual_remote)
    lock = _thread.RLock(); began = time.monotonic(); started = transport._clock()
    require(type(began) in (int, float) and 0 <= began <= 2 ** 53, "durable_capture_clock_refused")
    guard.refresh(); lease = None
    def boundary():
        with lock:
            guard.check()
            if lease is not None: _lease_window(_lease_record(lease))
    try:
        with archive_loader.count.old.cache.HeldFiles(tuple(root / name for name, unused in manifest),
                protected=False, boundary=boundary) as code:
            _audit_code(root, guard, manifest, code)
            lease = object.__new__(CountSourceLease)
            anchor = (lease, root, runtime_head, actual_remote, plan, budget, archive[6], manifest,
                _code_identity(runtime_head, manifest), SOURCE_AUTHORITY_SHA256, transport.PROTOCOL_SHA256,
                _expected_output(root, plan, budget.public_summary()["current_chunk"]), lock, started, began, object())
            lease._anchor = lease._identity = anchor
            state, previous = ["LIVE"], [began]
            record = anchor, token, code, guard, state, hash_payload(protocol()), previous
            _LEASES[lease] = record; _LEASE_PHASES[lease] = state[0]; _LEASE_CLOCKS[lease] = began
            source_lease_live_binding(lease)
            yield lease
            source_lease_live_binding(lease); state[0] = _LEASE_PHASES[lease] = "CLOSING"
            code.check(); guard.refresh(); _lease_window(record)
        # Original held-code context has now closed successfully.  A fresh
        # committed-byte audit follows, never a newly adopted source seal.
        with lock:
            _audit_code(root, guard, manifest); _lease_window(record)
            closed_at = transport._clock()
            require(transport.legacy.parallel.clock(started) <= transport.legacy.parallel.clock(closed_at),
                "durable_capture_clock_refused")
            _lease_window(record)
            _LEASE_TERMINALS[lease] = anchor, record, hash_payload({"code_identity": anchor[8],
                "archive_closure": archive[5]}), object(), closed_at
            state[0] = _LEASE_PHASES[lease] = "CLOSED"
    except BaseException:
        _lease_latch(lease); raise


def _capture_snapshot(operation, candidate):
    op = transport.operation_binding(operation); original = transport.provisional_candidate_binding(candidate)
    require(original[1] is operation and original[2] is op, "durable_capture_candidate_changed")
    claim = None; starts = []
    for ticket, obs in zip(original[3], original[4]):
        observed = transport.http_observation_binding(obs)
        require(observed[1] is operation and observed[2] is ticket, "durable_capture_candidate_changed")
        if claim is None: claim = observed[3]
        require(observed[3] is claim, "durable_capture_candidate_changed")
        starts.append(observed[4])
    finals = tuple(transport._FINAL_CAPS[operation])
    return op, original, claim, tuple(starts), finals


class CountCheckpointFacts:
    """Original provisional storage facts, never a terminal or source cap."""
    __slots__ = ("_anchor", "_identity")
    def __init__(self): raise DurableCountCaptureRefusal("REFUSED: durable_capture_checkpoint_required")
    def __repr__(self): return "<CountCheckpointFacts provisional; redacted>"


def checkpoint_facts_binding(value):
    """Pure original10; does not resurrect an expired source or volume clock."""
    try:
        require(type(value) is CountCheckpointFacts and CountCheckpointFacts.__hash__ is object.__hash__
            and CountCheckpointFacts.__eq__ is object.__eq__, "durable_capture_checkpoint_changed")
        saved = _CHECKPOINT_FACTS.get(value) if type(value) is CountCheckpointFacts else None
        require(type(saved) is tuple and len(saved) == 10 and saved[0] is value
            and value._anchor is value._identity is saved and id(value) not in _CHECKPOINT_FACTS_FAILED
            and type(saved[5]) is bytes and hash_bytes(saved[5]) == saved[6]
            and type(saved[7]) is tuple and type(saved[8]) is tuple and type(saved[9]) is object,
            "durable_capture_checkpoint_changed")
        return saved
    except BaseException:
        if type(value) is CountCheckpointFacts: _CHECKPOINT_FACTS_FAILED.add(id(value))
        raise


def _issue_checkpoint_facts(operation, candidate, payload, directory_pins, volume_pins):
    require(sys._getframe(1).f_code in (checkpoint_facts.__code__, checkpoint_round_facts.__code__),
        "durable_capture_checkpoint_required")
    require(CountCheckpointFacts.__hash__ is object.__hash__ and CountCheckpointFacts.__eq__ is object.__eq__,
        "durable_capture_checkpoint_changed")
    op = transport.operation_binding(operation); original = transport.provisional_candidate_binding(candidate)
    raw = canonical_json(payload).encode()
    require(0 < len(raw) <= 2 * 1024 ** 2, "durable_capture_checkpoint_changed")
    cap = object.__new__(CountCheckpointFacts)
    saved = (cap, operation, candidate, op, original, raw, hash_bytes(raw), directory_pins, volume_pins, object())
    cap._anchor = cap._identity = saved; _CHECKPOINT_FACTS[cap] = saved
    checkpoint_facts_binding(cap); return cap


def checkpoint_facts(operation, candidate):
    """Mint only from original LIVE fully published FINAL/control/file origins.

    The descriptor describes observed storage, not the future context exits.
    All original full9 stamps come from creator choices, never current stats.
    """
    op = transport.active_operation_binding(operation)
    with op[11]:
        source = source_lease_live_binding(op[12])
        op, original, claim, starts, finals = _capture_snapshot(operation, candidate)
        require(len(finals) == 4, "durable_capture_checkpoint_changed")
        _audit_membership(operation, candidate)
        volume = transport.volume_for_operation(operation)
        volume_origin = storage.volume_binding(volume, live=True)
        require(callable(getattr(storage, "volume_system_entries", None)), "durable_capture_checkpoint_required")
        system_entries = storage.volume_system_entries(volume, operation)
        require(type(system_entries) is tuple, "durable_capture_checkpoint_changed")
        state = volume._binding(); mount = volume_origin[2]; base = source[11]
        require(base == mount / "capture", "durable_capture_checkpoint_changed")
        rows = []
        def file_row(origin, seal, digest):
            require(type(origin) is tuple and len(origin) == 15 and type(seal) is tuple and len(seal) == 9
                and all(type(item) is int for item in seal) and seal[5] == len(origin[4])
                and hash_bytes(origin[4]) == digest, "durable_capture_checkpoint_changed")
            path = (origin[1][0] / origin[3]).relative_to(mount).as_posix()
            rows.append({"path": path, "bytes": len(origin[4]), "sha256": digest, "seal9": list(seal)})
            return path
        claimed = controls.claim_binding(claim)
        claim_path = file_row(claimed[8], claimed[9], claimed[6])
        attempts, charges = [], []
        for ticket, obs, evidence, start in zip(original[3], original[4], original[5], starts):
            reserved = accounting.ticket_binding(ticket); observed = transport.http_observation_binding(obs)
            started = controls.start_binding(start); received = controls.received_binding(evidence[0])
            start_path = file_row(started[9], started[10], started[4])
            received_path = file_row(received[7], received[8], received[6])
            body_path = receipt_path = None
            if evidence[1] is not None:
                pair = responses.response_binding(evidence[1]); ordinal = reserved[4]
                require(pair[1] is operation and pair[2] is ticket and pair[3] is obs,
                    "durable_capture_checkpoint_changed")
                body_path = f"capture/responses/{ordinal:06d}/{responses.BODY_NAME}"
                receipt_path = f"capture/responses/{ordinal:06d}/{responses.RECEIPT_NAME}"
                for name, seal, digest in ((body_path, pair[9], pair[6]), (receipt_path, pair[10], pair[8])):
                    require(type(seal) is tuple and len(seal) == 9 and all(type(item) is int for item in seal),
                        "durable_capture_checkpoint_changed")
                    rows.append({"path": name, "bytes": seal[5], "sha256": digest, "seal9": list(seal)})
                charge = pair[7]
            else: charge = 2 * 1024 ** 2
            charges.append(charge)
            attempts.append({"reservation": json.loads(reserved[13]), "reservation_sha256": reserved[9],
                "observation_sha256": observed[14], "http_invoked": observed[8], "http_status": observed[9],
                "received_at": observed[12], "fixed_diagnostic": None if observed[13] is None else dict(observed[13]),
                "START_path": start_path, "received_path": received_path, "body_path": body_path,
                "receipt_path": receipt_path, "charged_bytes": charge})
        for cap in finals:
            final = controls.final_control_binding(cap); file_row(final[4], final[5], final[3])
        require(len(rows) == len({row["path"] for row in rows}), "durable_capture_checkpoint_changed")
        directory_pins = tuple(_DIRECTORIES.get(operation, ()))
        directories = [{"path": ".", "pin4": list(state["mount_pin"])}]
        directories.extend({"path": path.relative_to(mount).as_posix(), "pin4": list(pin)}
            for path, pin in directory_pins)
        archive = _archive_binding(_lease_record(op[12])[1])
        volume_pins = (volume_origin, state["mount_pin"], state["root_creation_pin"], state["mount_native"],
            state["device_node_pin"], state["backing_pin"], tuple(state["directories"]), system_entries)
        descriptor = {"schema": "si-count-checkpoint-descriptor-v1", "phase": "PROVISIONAL_STORAGE_FACTS",
            "producer": {"head": source[2], "remote": source[3], "code_manifest": [list(row) for row in source[7]],
                "code_identity_sha256": source[8], "source_authority_sha256": source[9],
                "operator_protocol_sha256": source[10], "run_protocol_sha256": RUN_PROTOCOL_SHA256,
                "negative_policy_sha256": NEGATIVE_PRESERVATION_POLICY_SHA256, "registration_sha256": op[6]},
            "archive": {"baseline_sha256": BASELINE_LEDGER_SHA256, "closed_summary_sha256": archive[5]},
            "plan": {"sha256": op[10], "chunk": op[4], "positions": list(original[6]),
                "total_chunks": len(op[2]._parts[3])}, "payload_base": "capture",
            "files": sorted(rows, key=lambda row: row["path"]),
            "directories": sorted(directories, key=lambda row: row["path"]),
            "volume": {"mount": str(mount), "namespace": str(state["namespace"]),
                "backing_pin": list(state["backing_pin"]), "root_pin": list(state["mount_pin"]),
                "root_identity": list(state["root_creation_pin"][:4]),
                "native_identity": state["mount_native"], "device": state["device"],
                "block_node_pin": list(state["device_node_pin"]),
                "system_entries": [{"name": name, "pin5": list(pin)} for name, pin in system_entries],
                "parent_directories": [{"path": str(path), "pin4": list(pin)} for path, unused, pin in state["directories"]]},
            "attempts": attempts, "external_claim_path": claim_path,
            "final_manifest_sha256": controls.final_control_binding(finals[-1])[3],
            "account": {"chunk": op[4], "reservation_sha256s": [accounting.ticket_binding(item)[9] for item in original[3]],
                "charges": charges, "covered_positions": list(original[6]),
                "manifest_sha256": controls.final_control_binding(finals[-1])[3]},
            "authority": authority()}
        if candidate in _CHECKPOINT_CAPS:
            cap = _CHECKPOINT_CAPS[candidate]; saved = checkpoint_facts_binding(cap)
            require(saved[1] is operation and saved[2] is candidate and saved[3] is op and saved[4] is original
                and saved[5] == canonical_json(descriptor).encode() and saved[7] == directory_pins,
                "durable_capture_checkpoint_changed")
        else:
            cap = _issue_checkpoint_facts(operation, candidate, descriptor, directory_pins, volume_pins)
            _CHECKPOINT_CAPS[candidate] = cap
        source_lease_live_binding(op[12]); volume.check(); return cap


def checkpoint_round_facts(operation, candidate, original_checkpoint_caps):
    """Original ordered stored roots; final current account is still provisional."""
    from scripts import short_interest_count_checkpoint as checkpoints
    op = transport.active_operation_binding(operation)
    with op[11]:
        source_lease_live_binding(op[12]); original = transport.provisional_candidate_binding(candidate)
        require(op[4] == len(op[2]._parts[3])
            and type(original_checkpoint_caps) is tuple and len(original_checkpoint_caps) == op[4],
            "durable_capture_checkpoint_changed")
        prior = accounting.settled_chunk_accounting(op[1])[3]
        require(len(prior) == op[4] - 1, "durable_capture_checkpoint_changed")
        roots, accounts, all_positions = [], [], []
        for number, cap in enumerate(original_checkpoint_caps, 1):
            bound = checkpoints.checkpoint_binding(cap); facts = checkpoint_facts_binding(bound[4][0])
            descriptor = json.loads(facts[5]); account = descriptor["account"]
            require(bound[3] == "chunk" and facts is bound[4] and facts[3][1] is op[1]
                and facts[3][2] is op[2] and facts[3][4] == number
                and descriptor["plan"]["chunk"] == number, "durable_capture_checkpoint_changed")
            if number < op[4]:
                settled = prior[number - 1]
                require(account == {"chunk": number,
                    "reservation_sha256s": [accounting.ticket_binding(ticket)[9] for ticket in settled[3]],
                    "charges": list(settled[4]), "covered_positions": list(settled[5]), "manifest_sha256": settled[6]},
                    "durable_capture_checkpoint_changed")
            else: require(facts[2] is candidate and facts[4] is original, "durable_capture_checkpoint_changed")
            roots.append({"chunk": number, "mount": descriptor["volume"]["mount"], "relative_root": bound[10],
                "body_sha256": bound[6], "body_seal9": list(bound[7]),
                "receipt_sha256": bound[8], "receipt_seal9": list(bound[9]), "descriptor_sha256": facts[6],
                "directory_pins": [{"path": path.relative_to(Path(descriptor["volume"]["mount"])).as_posix(),
                    "pin5": list(pin)} for path, pin in checkpoints.checkpoint_directory_pins(cap)]})
            accounts.append(_checkpoint_account_root(account)); all_positions.extend(account["covered_positions"])
        require(all_positions == sorted(set(all_positions)), "durable_capture_checkpoint_changed")
        expected = {"baseline_sha256": BASELINE_LEDGER_SHA256, "plan_sha256": op[10], "accounts": accounts}
        payload = {"schema": "si-count-checkpoint-round-v1", "phase": "PROVISIONAL_STORAGE_FACTS",
            "baseline_sha256": BASELINE_LEDGER_SHA256, "plan_sha256": op[10],
            "chunks": roots, "expected_union_binding_sha256": hash_payload(expected),
            "expected_accounting": expected, "authority": authority()}
        if operation in _CHECKPOINT_ROUND:
            facts = _CHECKPOINT_ROUND[operation]; saved = checkpoint_facts_binding(facts)
            require(saved[1] is operation and saved[2] is candidate and saved[3] is op and saved[4] is original
                and saved[5] == canonical_json(payload).encode(), "durable_capture_checkpoint_changed")
        else:
            facts = _issue_checkpoint_facts(operation, candidate, payload, (), ())
            _CHECKPOINT_ROUND[operation] = facts
        return facts


def _checkpoint_account_root(account):
    """Compact root; every full per-ticket account remains in its descriptor."""
    return {"chunk": account["chunk"], "STARTs": len(account["charges"]),
        "charged_bytes": sum(account["charges"]), "reservation_roster_sha256": hash_payload(account["reservation_sha256s"]),
        "charges_sha256": hash_payload(account["charges"]), "covered_positions": len(account["covered_positions"]),
        "covered_positions_sha256": hash_payload(account["covered_positions"]), "manifest_sha256": account["manifest_sha256"]}


def final_member_rows(operation, candidate):
    """Fixed typed-cap reconstruction; no caller member rows or raw bodies."""
    try:
        op, original, claim, starts, finals = _capture_snapshot(operation, candidate)
        base = source_lease_binding(op[12])[11]; rows = []
        def control(cap, role, expected_directory, expected_name):
            bound = (controls.start_binding(cap) if role == "start" else controls.received_binding(cap)
                if role == "received" else controls.final_control_binding(cap))
            origin = bound[9] if role == "start" else bound[7] if role == "received" else bound[4]
            require(bound[1] is operation and type(origin) is tuple and len(origin) == 15
                and origin[1][0] == expected_directory and origin[3] == expected_name and type(origin[4]) is bytes,
                "durable_capture_member_changed")
            name = (expected_directory / expected_name).relative_to(base).as_posix()
            rows.append({"name": name, "bytes": len(origin[4]), "sha256": hash_bytes(origin[4])})
        for ticket, start, evidence in zip(original[3], starts, original[5]):
            ordinal = accounting.ticket_binding(ticket)[4]
            control(start, "start", base / "starts" / f"{ordinal:06d}", "START.spent.json")
            control(evidence[0], "received", base / "received" / f"{ordinal:06d}", "received.private.json")
            if evidence[1] is not None:
                pair = responses.response_binding(evidence[1]); path = base / "responses" / f"{ordinal:06d}"
                require(pair[1] is operation and pair[2] is ticket, "durable_capture_member_changed")
                for name, seal, digest in ((responses.BODY_NAME, pair[9], pair[6]),
                        (responses.RECEIPT_NAME, pair[10], pair[8])):
                    require(type(seal) is tuple and len(seal) == 9 and type(seal[5]) is int and _digest(digest),
                        "durable_capture_member_changed")
                    rows.append({"name": (path / name).relative_to(base).as_posix(), "bytes": seal[5], "sha256": digest})
        for cap, role in zip(finals, transport.FINAL_ROLES):
            if role != "manifest": control(cap, role, base / ("final_" + role),
                {"inventory": "inventory.private.json", "provisional": "provisional.json", "closed": "closed.json"}[role])
        require(type(claim) is controls.CountClaim and len(rows) == len({row["name"] for row in rows}),
            "durable_capture_member_changed")
        return sorted(rows, key=lambda row: row["name"])
    except BaseException: transport._latch(operation); raise


def _directory_stamp(info):
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
        "durable_capture_directory_changed")
    return info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)


def _new_directory(operation, path):
    """Single fresh dir relative to the original current-volume parent."""
    op = transport.active_operation_binding(operation)
    with op[11]:
        transport._control_volume_binding(operation, live=True); base = source_lease_binding(op[12])[11]
        fixed = {base, base.parent / "claim", *(base / role for role in ("starts", "received", "responses")),
            *(base / ("final_" + role) for role in transport.FINAL_ROLES)}
        for ticket in op[1].current_tickets():
            ordinal = accounting.ticket_binding(ticket)[4]
            fixed.update(base / role / f"{ordinal:06d}" for role in ("starts", "received", "responses"))
        require(path in fixed,
            "durable_capture_directory_changed")
        fds = []; parent = path.parent
        try:
            pins = dict(_DIRECTORIES.get(operation, ()))
            expected_parent = pins.get(parent)
            require(expected_parent is not None or parent == base.parent, "durable_capture_directory_changed")
            parent_pin = _directory_stamp(parent.lstat())
            require(expected_parent is None or parent_pin == expected_parent, "durable_capture_directory_changed")
            fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW); fds.append(fd)
            require(_directory_stamp(os.fstat(fd)) == _directory_stamp(parent.lstat()) == parent_pin,
                "durable_capture_directory_changed")
            os.mkdir(path.name, mode=0o700, dir_fd=fd)
            made = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd); fds.append(made)
            os.fchmod(made, 0o700)
            pin = _directory_stamp(os.fstat(made))
            require(_directory_stamp(path.lstat()) == pin and path.resolve() == path,
                "durable_capture_directory_changed")
            require(_directory_stamp(os.fstat(fd)) == _directory_stamp(parent.lstat()) == parent_pin,
                "durable_capture_directory_changed")
            _DIRECTORIES[operation] = (*_DIRECTORIES.get(operation, ()), (path, pin))
            transport._control_volume_binding(operation, live=True)
        finally: _drain_fds(fds)
        return path


@contextmanager
def _owned(operation, path):
    op = transport.active_operation_binding(operation)
    path = _new_directory(operation, path)
    def boundary():
        with op[11]: _source_boundary(op[12]); transport._control_volume_binding(operation, live=True)
    with archive_loader.prior._OwnedOutput(path, boundary) as owned:
        yield owned


def _audit_membership(operation, candidate, *, final=True):
    op = transport.operation_binding(operation); base = source_lease_binding(op[12])[11]
    rows = final_member_rows(operation, candidate)
    expected_files = {row["name"] for row in rows}
    if final: expected_files.add("final_manifest/manifest.private.json")
    expected_dirs = {"."}
    for name in expected_files:
        path = Path(name).parent
        while path != Path("."):
            expected_dirs.add(path.as_posix()); path = path.parent
    # Only original factory-created directory pins are accepted, never fresh
    # stamps substituted at the final sweep.
    pins = dict(_DIRECTORIES.get(operation, ()))
    require(base in pins, "durable_capture_directory_changed")
    observed_files, observed_dirs = set(), set()
    def walk(path):
        rel = "." if path == base else path.relative_to(base).as_posix()
        require(path in pins and _directory_stamp(path.lstat()) == pins[path], "durable_capture_directory_changed")
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            require(_directory_stamp(os.fstat(fd)) == pins[path], "durable_capture_directory_changed")
            observed_dirs.add(rel)
            for name in _member_names(operation, fd):
                info = os.stat(name, dir_fd=fd, follow_symlinks=False); child = path / name
                if stat.S_ISDIR(info.st_mode): walk(child)
                else:
                    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                        and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1,
                        "durable_capture_member_changed")
                    observed_files.add(child.relative_to(base).as_posix())
            require(_directory_stamp(os.fstat(fd)) == _directory_stamp(path.lstat()) == pins[path],
                "durable_capture_directory_changed")
        finally: os.close(fd)
    walk(base)
    require(observed_files == expected_files and observed_dirs == expected_dirs, "durable_capture_member_changed")
    claimed = controls.claim_binding(_capture_snapshot(operation, candidate)[2])
    require(claimed[8][1][0] == base.parent / "claim"
        and set(os.listdir(base.parent / "claim")) == {"claim.spent.json"}, "durable_capture_member_changed")


def _member_names(operation, fd):
    op = transport.operation_binding(operation)
    with op[11]:
        return archive_loader.count.old.cache._inventory_names(fd,
            boundary=lambda: _source_boundary(op[12]))


def _original_postchecks(operation, candidate):
    op = transport.operation_binding(operation)
    source_lease_terminal_binding(op[12])
    record = _RUNS.get(operation)
    require(type(record) is tuple and len(record) == 5 and _RUN_ORIGINS.get(operation) is record
        and record[0] is op and record[1] is candidate,
        "durable_capture_terminal_required")
    volume = record[2]; volume.check_after_close(); volume_origin = storage.volume_binding(volume)
    require(transport.volume_for_operation(operation) is volume and volume_origin[1] is operation
        and volume_origin[2] / "capture" == source_lease_binding(op[12])[11],
        "durable_capture_terminal_changed")
    _audit_code(op[7], _lease_record(op[12])[3], source_lease_binding(op[12])[7])
    _audit_membership(operation, candidate)
    from scripts import short_interest_count_checkpoint as checkpoints
    require(operation in _WRITTEN_CHECKPOINTS, "durable_capture_checkpoint_required")
    checkpoints.audit_original_checkpoint_roots()
    volume.check_after_close(); source_lease_terminal_binding(op[12])
    previous = _TERMINALS.get(operation)
    if previous is not None:
        witnessed = previous[3]
        require(type(witnessed) is tuple and len(witnessed) == 5 and witnessed[0] is volume
            and witnessed[1] is volume_origin and type(witnessed[2]) is bytes
            and hash_bytes(witnessed[2]) == witnessed[3]
            and canonical_json(volume.closed_summary()).encode() == witnessed[2]
            and type(witnessed[4]) is object, "durable_capture_terminal_changed")
        require(transport.legacy.parallel.clock(previous[11]) <= transport.legacy.parallel.clock(transport._clock()),
            "durable_capture_clock_refused")
        source_lease_terminal_binding(op[12])


def _finish_original_chunk(operation, candidate):
    # The original outer function, after its successful context exits, is the
    # only terminal issuer. Merely invoking this private helper is insufficient.
    require(sys._getframe(1).f_code is _capture_chunk.__code__, "durable_capture_terminal_required")
    require(operation not in _TERMINALS, "durable_capture_terminal_reused")
    _original_postchecks(operation, candidate)
    op, original, claim, starts, finals = _capture_snapshot(operation, candidate)
    require(len(finals) == 4, "durable_capture_terminal_required")
    manifest = controls.final_control_binding(finals[-1])[4][4]
    source = source_lease_terminal_binding(op[12]); volume = _RUNS[operation][2]
    volume_raw = canonical_json(volume.closed_summary()).encode()
    volume_witness = volume, storage.volume_binding(volume), volume_raw, hash_bytes(volume_raw), object()
    at = transport._clock()
    require(transport.legacy.parallel.clock(source[13]) <= transport.legacy.parallel.clock(at),
        "durable_capture_clock_refused")
    require(all(transport.legacy.parallel.clock(transport.http_observation_binding(obs)[12])
        <= transport.legacy.parallel.clock(at) for obs in original[4]), "durable_capture_clock_refused")
    terminal = (operation, candidate, source, volume_witness, claim, starts, original[4], original[5],
        finals, manifest, hash_bytes(manifest), at, object(), RUN_PROTOCOL_SHA256)
    _TERMINALS[operation] = terminal
    _TERMINAL_ORIGINS[operation] = _RUNS[operation], terminal, original
    # Hashing/terminal preparation may itself take time: the last check follows.
    _original_postchecks(operation, candidate)
    return reader._issue_original_closed_chunk(operation, candidate)


def terminal_chunk_binding(operation, candidate):
    try:
        record = _TERMINALS.get(operation)
        issued = _TERMINAL_ORIGINS.get(operation)
        require(type(record) is tuple and len(record) == 14 and record[0] is operation and record[1] is candidate
            and operation not in _TERMINAL_FAILED and type(record[12]) is object
            and record[13] == RUN_PROTOCOL_SHA256 and type(issued) is tuple and len(issued) == 3
            and issued[0] is _RUNS.get(operation) is _RUN_ORIGINS.get(operation) and issued[1] is record
            and issued[2] is transport.provisional_candidate_binding(candidate), "durable_capture_terminal_changed")
        _original_postchecks(operation, candidate)
        require(_TERMINALS.get(operation) is record, "durable_capture_terminal_changed")
        return record
    except BaseException:
        _TERMINAL_FAILED.add(operation); transport._latch(operation); raise


def _publish_attempt(operation, ticket, claim):
    slot = _attempt_for_ticket(operation, ticket)
    require(slot[2] is claim, "durable_capture_worker_slot_changed")
    with _prepared_owned(slot, "start") as owned:
        with controls.prepare_owned_count_start(owned, operation, ticket, claim,
                boundary=lambda: _source_boundary(transport.operation_binding(operation)[12])) as start: pass
    observed = operation.dispatch(ticket, claim, start)
    require(type(observed) is transport.HttpObservation, "durable_capture_unqualified_result")
    with _prepared_owned(slot, "received") as owned:
        with controls.prepare_owned_count_received(owned, operation, observed,
                boundary=lambda: _source_boundary(transport.operation_binding(operation)[12])) as received: pass
    operation.accept_received_control(received)
    return observed


def _batch_width():
    require(type(MAXIMUM_WORKERS) is int and 1 <= MAXIMUM_WORKERS <= 8, "durable_capture_worker_slot_changed")
    return MAXIMUM_WORKERS


def _prepare_attempt_slot(operation, ticket, claim):
    """Main alone creates the exact fresh directories, before creator timers."""
    op = transport.active_operation_binding(operation)
    with op[11]:
        require(any(ticket is value for value in op[1].current_tickets()), "durable_capture_worker_slot_changed")
        permission = transport.start_permission_binding(operation, ticket)
        require(id(ticket) not in _ATTEMPT_BY_TICKET, "durable_capture_worker_slot_changed")
        paths = []
        for role in ("start", "received"):
            path = transport._control_directory(operation, role, ticket)
            _new_directory(operation, path)
            pin = dict(_DIRECTORIES[operation]).get(path)
            require(type(pin) is tuple and len(pin) == 4, "durable_capture_worker_slot_changed")
            paths.append((role, path, pin))
        slot = (operation, ticket, claim, op, tuple(paths), permission, object())
        _ATTEMPT_SLOTS[slot[6]] = slot; _ATTEMPT_BY_TICKET[id(ticket)] = slot
        return slot


def _attempt_slot(slot):
    require(type(slot) is tuple and len(slot) == 7 and type(slot[6]) is object
        and _ATTEMPT_SLOTS.get(slot[6]) is slot, "durable_capture_worker_slot_changed")
    operation, ticket, unused_claim, op = slot[:4]
    require(transport.active_operation_binding(operation) is op and _ATTEMPT_BY_TICKET.get(id(ticket)) is slot
        and accounting.active_ticket_binding(ticket)[1] is op[1]
        and transport.start_permission_binding(operation, ticket) is slot[5], "durable_capture_worker_slot_changed")
    return slot


def _attempt_for_ticket(operation, ticket):
    accounting.active_ticket_binding(ticket)
    slot = _ATTEMPT_BY_TICKET.get(id(ticket))
    require(type(slot) is tuple and slot[0] is operation and slot[1] is ticket, "durable_capture_worker_slot_changed")
    return _attempt_slot(slot)


def _prepare_response_slot(operation, slot, observed):
    op = transport.active_operation_binding(operation)
    with op[11]:
        _attempt_slot(slot); op[1].current_tickets()  # Original owner-thread guard.
        result = _ATTEMPT_RESULTS.get(slot[6])
        require(type(result) is tuple and len(result) == 2 and result[0] is slot and result[1] is observed,
            "durable_capture_worker_slot_changed")
        bound = transport.http_observation_binding(observed)
        require(bound[1] is operation and bound[2] is slot[1] and type(bound[10]) is bytes and bound[10],
            "durable_capture_worker_slot_changed")
        path = source_lease_binding(op[12])[11] / "responses" / f"{accounting.ticket_binding(slot[1])[4]:06d}"
        _new_directory(operation, path); pin = dict(_DIRECTORIES[operation]).get(path)
        require(type(pin) is tuple and len(pin) == 4, "durable_capture_worker_slot_changed")
        response = slot, observed, path, pin, object()
        _RESPONSE_SLOTS[response[4]] = response; return response


@contextmanager
def _prepared_owned(slot, role, response=None):
    slot = _attempt_slot(slot); operation, unused_ticket, unused_claim, op = slot[:4]
    with op[11]:
        if role == "response":
            require(type(response) is tuple and len(response) == 5 and type(response[4]) is object
                and _RESPONSE_SLOTS.get(response[4]) is response and response[0] is slot,
                "durable_capture_worker_slot_changed")
            path, pin = response[2:4]
        else:
            require(role in ("start", "received"), "durable_capture_worker_slot_changed")
            unused, path, pin = next(value for value in slot[4] if value[0] == role)
        require(dict(_DIRECTORIES.get(operation, ())).get(path) is pin
            and _directory_stamp(path.lstat()) == pin, "durable_capture_directory_changed")
    def boundary():
        with op[11]:
            _attempt_slot(slot); _source_boundary(op[12]); transport._control_volume_binding(operation, live=True)
            require(_directory_stamp(path.lstat()) == pin, "durable_capture_directory_changed")
    # The directory is this exact original Main-issued slot, not adoption of a
    # caller-selected existing output. The original OwnedOutput still opens
    # and checks every original FD/name/protection boundary itself.
    with archive_loader.prior._OwnedOutput(path, boundary) as owned:
        yield owned


def _receive_worker(slot):
    try:
        slot = _attempt_slot(slot); operation, ticket, claim, op = slot[:4]
        with op[11]:
            require(slot[6] not in _ATTEMPT_USED, "durable_capture_worker_slot_changed")
            _ATTEMPT_USED.add(slot[6])
        observed = _publish_attempt(operation, ticket, claim)
        with op[11]:
            _attempt_slot(slot)
            require(type(observed) is transport.HttpObservation, "durable_capture_unqualified_result")
            _ATTEMPT_RESULTS[slot[6]] = slot, observed
        return observed
    except BaseException:
        if type(slot) is tuple and len(slot) == 7: transport._latch(slot[0])
        raise


def _response_worker(response):
    slot = response[0] if type(response) is tuple and len(response) == 5 else None
    try:
        slot = _attempt_slot(slot); operation, ticket, unused_claim, op = slot[:4]
        with op[11]:
            require(type(response[4]) is object and _RESPONSE_SLOTS.get(response[4]) is response and response[4] not in _RESPONSE_USED,
                "durable_capture_worker_slot_changed")
            _RESPONSE_USED.add(response[4]); observed = response[1]
            result = _ATTEMPT_RESULTS.get(slot[6])
            require(type(result) is tuple and len(result) == 2 and result[0] is slot and result[1] is observed,
                "durable_capture_worker_slot_changed")
        with _prepared_owned(slot, "response", response) as owned:
            with responses.prepare_owned_count_response(owned, ticket=ticket, observation=observed,
                    boundary=lambda: _source_boundary(op[12])) as pair: pass
        operation.accept_closed_response(pair); return pair
    except BaseException:
        if type(slot) is tuple and len(slot) == 7: transport._latch(slot[0])
        raise


def _run_worker_stage(operation, slots, worker):
    """Join EVERY accepted task; a failure never starts a new batch/stage."""
    require(type(slots) is tuple and 1 <= len(slots) <= _batch_width()
        and (worker is _receive_worker or worker is _response_worker), "durable_capture_worker_slot_changed")
    futures, results, errors, executor = [], [], [], None
    try:
        executor = ThreadPoolExecutor(max_workers=len(slots), thread_name_prefix="si-count")
        for slot in slots:
            try: futures.append(executor.submit(worker, slot))
            except BaseException as error:
                transport._latch(operation); errors.append(error); break
        for future in futures:
            try: results.append(future.result())
            except BaseException as error:
                transport._latch(operation); errors.append(error)
    except BaseException as error:
        transport._latch(operation); errors.append(error)
    finally:
        if executor is not None:
            try: executor.shutdown(wait=True, cancel_futures=False)
            except BaseException as error:
                transport._latch(operation); errors.append(error)
        if errors:
            _WORKER_RETAINED[operation] = executor, tuple(futures), tuple(results), tuple(errors)
            if any(not future.done() for future in futures): _BLOCKED_OPERATIONS.add(operation)
    if errors: raise errors[0]
    require(len(results) == len(slots), "durable_capture_worker_stage_failed")
    return tuple(results)


def _schedule_chunk_attempts(operation, budget, claim):
    """Main is the only reservation/retry/directory owner; workers do no such work."""
    chunk = budget.public_summary()["current_chunk"]
    fresh = list(budget.plan.chunk_positions(chunk)); retries, tries = {}, {}
    while fresh or retries:
        op = transport.active_operation_binding(operation); _source_boundary(op[12])
        width = _batch_width(); now = time.monotonic()
        positions = fresh[:width]; del fresh[:len(positions)]
        ready = sorted(position for position, deadline in retries.items() if deadline <= now)
        for position in ready[:width - len(positions)]: positions.append(position); del retries[position]
        if not positions:
            time.sleep(max(0, min(retries.values()) - time.monotonic())); continue
        tickets = tuple(budget.reserve_start_slot(position) for position in positions)
        operation.authorize_start_batch(tickets)
        slots = tuple(_prepare_attempt_slot(operation, ticket, claim) for ticket in tickets)
        observations = _run_worker_stage(operation, slots, _receive_worker)
        response_slots = []
        for slot, observed in zip(slots, observations):
            bound = transport.http_observation_binding(observed)
            if type(bound[10]) is bytes and bound[10]: response_slots.append(_prepare_response_slot(operation, slot, observed))
        if response_slots: _run_worker_stage(operation, tuple(response_slots), _response_worker)
        for position, observed in zip(positions, observations):
            bound = transport.http_observation_binding(observed); tries[position] = tries.get(position, 0) + 1
            if type(bound[9]) is int and bound[9] == 200 and type(bound[10]) is bytes and bound[10]: continue
            detail = dict(bound[13] or ())
            require(detail.get("retryable") is True and bound[9] is None, "durable_capture_retry_exhausted")
            with op[11]:
                completed = transport._OBS_COMPLETED.get(observed)
                require(type(completed) in (int, float) and 0 <= completed <= time.monotonic(),
                    "durable_capture_clock_refused")
                retries[position] = completed + (2 if tries[position] == 1 else 10)


def _failed_original_state(operation):
    """Negative-only original RAM state; never invoke a failed source guard."""
    record = transport._OPERATIONS.get(operation)
    prepared = _PRESERVATION_LEASES.get(operation)
    expected = prepared[1] if prepared is not None else (record[0] if type(record) is tuple and record else None)
    require(type(operation) is transport.CountCaptureOperation and type(expected) is tuple and len(expected) == 14
        and expected[0] is operation and operation._anchor is operation._identity is expected
        and type(record) is tuple and len(record) == 2 and record[0] is expected
        and operation in transport._FAILED, "durable_capture_preservation_changed")
    with expected[11]:
        state = transport._OPERATIONS[operation][1]
        require(type(state) is tuple and len(state) == 6 and all(type(state[index]) is tuple for index in (1, 2, 3))
            and len(state[1]) <= 528 and len(state[2]) <= 8 and len(state[3]) <= 528,
            "durable_capture_preservation_changed")
        return expected, state


def _checked_negative_report(operation, lease):
    registered_lease = _PRESERVATION_LEASES.get(operation)
    require(type(registered_lease) is tuple and len(registered_lease) == 4 and registered_lease[0] is lease
        and type(lease) is negative.OriginalPreservationLease,
        "durable_capture_preservation_changed")
    report = negative.preservation_binding(lease)
    count_names = ("retained_opaque_observations", "originally_closed_negative_attempts",
        "verified_durable_negative_attempts", "pending_already_started_attempts")
    require(type(report) is dict and report.get("schema") == "si-negative-preservation-observation-v1"
        and type(report.get("requires_process_hold")) is bool and type(report.get("original_mount_FD_retained")) is bool
        and type(report.get("final_negative_manifest_issued")) is bool
        and type(report.get("status")) is str and report["status"] in {"blocked_private_bytes_and_FDs_must_remain_alive",
            "negative_quarantine_incomplete_process_must_remain_alive", "negative_quarantine_only",
            "preservation_manifest_sealed_only"}
        and report.get("budget_changes_performed") is False
        and all(type(report.get(name)) is int and 0 <= report[name] <= 528 for name in count_names)
        and type(report.get("authority")) is dict and all(type(name) is str for name in report["authority"]),
        "durable_capture_preservation_changed")
    profile = _PRESERVATION_PROFILES.get(operation)
    require(type(profile) is tuple and bool(profile), "durable_capture_preservation_changed")
    wanted = dict(profile)
    require(set(report["authority"]) == set(wanted) and all(type(report["authority"][name]) is type(value)
        and report["authority"][name] == value for name, value in wanted.items())
        and report["verified_durable_negative_attempts"] <= report["originally_closed_negative_attempts"],
        "durable_capture_preservation_changed")
    blocked = (report["requires_process_hold"] or report["pending_already_started_attempts"] != 0
        or not report["final_negative_manifest_issued"] or not report["original_mount_FD_retained"]
        or operation in _BLOCKED_OPERATIONS)
    if report["status"] == "blocked_private_bytes_and_FDs_must_remain_alive" or not report["original_mount_FD_retained"]:
        _BLOCKED_OPERATIONS.add(operation)
    permanent = operation in _BLOCKED_OPERATIONS
    summary = {"schema": "si-count-negative-capture-state-v1",
        "status": "preservation_blocked" if permanent else "preservation_incomplete" if blocked else "negative_preservation_complete",
        "requires_process_hold": blocked, "original_mount_FD_retained": report["original_mount_FD_retained"],
        "final_negative_manifest_issued": report["final_negative_manifest_issued"],
        "source_or_process_closure_claimed": False,
        **{name: report[name] for name in count_names}, "budget_changes_performed": False,
        "additional_HTTP_from_preservation": 0, "authority": authority()}
    raw = canonical_json(summary).encode()
    _NEGATIVE_STATUS[operation] = registered_lease, raw, hash_bytes(raw)
    _NEGATIVE_ORIGINS[operation] = _NEGATIVE_STATUS[operation]
    return summary


def _blocked_negative_summary(operation):
    _BLOCKED_OPERATIONS.add(operation)
    summary = {"schema": "si-count-negative-capture-state-v1", "status": "preservation_blocked",
        "requires_process_hold": True, "original_mount_FD_retained": False,
        "final_negative_manifest_issued": False, "source_or_process_closure_claimed": False,
        "retained_opaque_observations": 0, "originally_closed_negative_attempts": 0,
        "verified_durable_negative_attempts": 0, "pending_already_started_attempts": 0,
        "budget_changes_performed": False, "additional_HTTP_from_preservation": 0, "authority": authority()}
    raw = canonical_json(summary).encode()
    _NEGATIVE_STATUS[operation] = _PRESERVATION_LEASES.get(operation), raw, hash_bytes(raw)
    _NEGATIVE_ORIGINS[operation] = _NEGATIVE_STATUS[operation]
    return summary


def _preserve_failed_chunk(operation, volume, error):
    """Drain accepted work and quarantine only opaque already-received data.

    Called inside original volume/source contexts for every body failure.
    Late context-exit failures use the same independently retained original
    mount capability; no qualified source/root guard is bypassed or cleared.
    """
    transport._latch(operation)
    prepared = _PRESERVATION_LEASES.get(operation)
    previous = _PRESERVATION_HOLD.get(operation)
    original_error = previous[4] if type(previous) is tuple and len(previous) == 6 else error
    _PRESERVATION_HOLD[operation] = volume, prepared, None, (), original_error, object()
    try:
        anchor, state = _failed_original_state(operation)
        if prepared is None:
            # Mint failure precedes claim/key. Any accepted attempt here is an
            # unexpected preservation gap and must hold the process alive.
            if state[1] or state[2] or state[3]: return _blocked_negative_summary(operation)
            return None
        lease = prepared[0]
        while True:
            anchor, state = _failed_original_state(operation); retained = []
            _PRESERVATION_HOLD[operation] = volume, prepared, state, (), original_error, anchor
            for observation in state[3]:
                try:
                    if type(observation) is transport.HttpObservation:
                        observation = transport.downgrade_http_observation_for_preservation(observation)
                    require(type(observation) is transport.UnqualifiedHttpObservation,
                        "durable_capture_preservation_changed")
                    transport.drained_http_observation_binding(observation); retained.append(observation)
                    _PRESERVATION_HOLD[operation] = volume, prepared, state, tuple(retained), original_error, anchor
                    key = operation, observation
                    if key not in _NEGATIVE_ATTEMPTED:
                        _NEGATIVE_ATTEMPTED.add(key)  # Never retry a failed quarantine publication.
                        negative.preserve_failed_observation(lease, observation)
                except BaseException as preservation_error:
                    _remember_preservation_failure(operation, preservation_error)
                    _BLOCKED_OPERATIONS.add(operation)
                    if not any(item is observation for item in retained): retained.append(observation)
                    _PRESERVATION_HOLD[operation] = volume, prepared, state, tuple(retained), original_error, anchor
            try:
                report = _checked_negative_report(operation, lease)
                unused, drained = _failed_original_state(operation)
                if (not drained[2] and report["pending_already_started_attempts"] == 0
                        and not report["final_negative_manifest_issued"] and operation not in _BLOCKED_OPERATIONS
                        and operation not in _NEGATIVE_FINAL_ATTEMPTED):
                    _NEGATIVE_FINAL_ATTEMPTED.add(operation)
                    negative.finalize_failed_chunk(lease)
                    report = _checked_negative_report(operation, lease)
            except BaseException as preservation_error:
                _remember_preservation_failure(operation, preservation_error)
                report = _blocked_negative_summary(operation)
            unused, current = _failed_original_state(operation)
            if operation in _BLOCKED_OPERATIONS: return report
            if not current[2] and report["pending_already_started_attempts"] == 0: return report
            # Existing protected wire calls drain into opaque originals. No
            # lock is held while waiting, including the original short gap
            # after inflight-pop but before observation issuance. Never
            # reserve/retry/read a key/start a GET or reset qualification.
            time.sleep(0.05)
    except BaseException as preservation_error:
        _remember_preservation_failure(operation, preservation_error)
        return _blocked_negative_summary(operation)


def _negative_summaries():
    summaries = []
    for operation, record in tuple(_NEGATIVE_STATUS.items()):
        try:
            require(type(record) is tuple and len(record) == 3 and _NEGATIVE_ORIGINS.get(operation) is record
                and type(record[1]) is bytes and hash_bytes(record[1]) == record[2], "durable_capture_preservation_changed")
            summary = json.loads(record[1])
            require(type(summary) is dict and type(summary.get("requires_process_hold")) is bool,
                "durable_capture_preservation_changed")
            summaries.append(summary)
        except BaseException: _BLOCKED_OPERATIONS.add(operation)
    return summaries


def _fixed_hold_diagnostic(value):
    """Recheck exact fixed fields; never serialize an exception or its text."""
    categories = frozenset(("local_contract_refusal", "unknown_local_error", "local_os_error",
        "lane_guard_refusal", "platform_refusal", "keychain_refusal", "local_type_error",
        "local_name_error", "local_memory_error", "local_timeout"))
    errnos = frozenset(("EACCES", "EPERM", "EMFILE", "ENFILE", "ENOSPC", "ENOMEM", "ENOENT",
        "EIO", "ETIMEDOUT", "EEXIST", "EBADF", "EINVAL", "ENOTSUP"))
    require(type(value) is dict and len(value) == 3 and all(type(key) is str for key in value)
        and set(value) == {"category", "errno_name", "contract_code"}, "durable_capture_preservation_changed")
    category, number, code = value["category"], value["errno_name"], value["contract_code"]
    require(type(category) is str and category in categories
        and (number is None or type(number) is str and number in errnos)
        and (code is None or type(code) is str and len(code) <= 256 and code in _HOLD_CONTRACT_CODES),
        "durable_capture_preservation_changed")
    return {"category": category, "errno_name": number, "contract_code": code}


def _remember_preservation_failure(operation, error):
    """Best-effort bounded RAM-only observations; cannot release a hold."""
    try:
        detail = _fixed_hold_diagnostic(failure_summary(error))
        previous = _PRESERVATION_FAILURES.get(operation, ())
        require(type(previous) is tuple and (not previous
            or _PRESERVATION_FAILURE_ORIGINS.get(operation) is previous), "durable_capture_preservation_changed")
        item = tuple(detail.items())
        if item not in previous and len(previous) < 16:
            updated = (*previous, item)
            _PRESERVATION_FAILURES[operation] = _PRESERVATION_FAILURE_ORIGINS[operation] = updated
    except BaseException:
        pass  # Diagnostic failure cannot alter mandatory private retention.


def _hold_accounting(operation):
    """Authenticate original pure journals after FAILED; never a public guard."""
    names = ("closed_chunks", "new_START_reservations", "cumulative_START_reservations_upper_bound",
        "closed_charged_bytes", "outstanding_full_page_bytes", "cumulative_charged_plus_reserved_bytes")
    unknown = {"availability": "unavailable", **{name: None for name in names},
        "actual_START_or_HTTP_observation": False}
    try:
        op, unused = _failed_original_state(operation); budget = op[1]
        require(type(budget) is accounting.DurableCountBudget, "durable_capture_preservation_changed")
        with accounting._lock(budget):
            journal = accounting.settled_chunk_accounting(budget)
            profile = tuple(getattr(research_budget, name) for name in ("PRIOR_STARTS", "PRIOR_CHARGED_BYTES",
                "MAXIMUM_CUMULATIVE_STARTS", "MAXIMUM_CUMULATIVE_BYTES", "MAXIMUM_RESPONSE_BYTES"))
            require(type(_HOLD_BASELINE) is tuple and len(_HOLD_BASELINE) == 5
                and all(type(actual) is int and type(wanted) is int and actual == wanted
                    for actual, wanted in zip(profile, _HOLD_BASELINE)), "durable_capture_preservation_changed")
            prior, historical_bytes, maximum_starts, maximum_bytes, page_bytes = profile
            original = accounting._BUDGETS.get(budget)
            require(type(original) is tuple and len(original) == 3 and original[0] is budget
                and original[1] is budget._anchor is budget._identity
                and original[2] is budget._state and journal[0] is budget
                and journal[1] is original[1][3] is op[3] and journal[2] is op[2],
                "durable_capture_preservation_changed")
            state = original[2]
            require(type(state) is tuple and len(state) == 5 and type(state[1]) is tuple
                and type(state[2]) is tuple and len(state[1]) <= maximum_starts - prior and len(state[2]) <= 528
                and type(state[0]) is int and state[0] == op[4]
                and type(state[4]) is int and 0 <= state[4] <= maximum_bytes,
                "durable_capture_preservation_changed")
            for ordinal, ticket in enumerate(state[1], 1):
                part = accounting._TICKETS.get(ticket) if type(ticket) is accounting.CountAttemptTicket else None
                require(type(part) is tuple and len(part) == 14 and part[0] is ticket
                    and ticket._anchor is ticket._identity is part and part[1] is budget and part[2] is op[2]
                    and part[12] is op[3] and type(part[4]) is int and part[4] == ordinal
                    and type(part[11]) is int and part[11] == page_bytes,
                    "durable_capture_preservation_changed")
            require(all(accounting._TICKETS[ticket][3] == state[0] for ticket in state[2]),
                "durable_capture_preservation_changed")
            starts, outstanding = len(state[1]), len(state[2]) * page_bytes
            total = historical_bytes + state[4] + outstanding
            require(prior + starts <= maximum_starts and total <= maximum_bytes,
                "durable_capture_preservation_changed")
            return {"availability": "authenticated_original_pure_journal", "closed_chunks": len(journal[3]),
                "new_START_reservations": starts, "cumulative_START_reservations_upper_bound": prior + starts,
                "closed_charged_bytes": state[4], "outstanding_full_page_bytes": outstanding,
                "cumulative_charged_plus_reserved_bytes": total, "actual_START_or_HTTP_observation": False}
    except BaseException:
        return unknown


def _hold_diagnostics(operation):
    result = {"original_failure": {"availability": "unavailable", "fixed_diagnostic": None},
        "preservation_failures": {"availability": "unavailable", "fixed_diagnostics": None,
            "maximum_reported": 16, "negative_registry_authenticated": False}, "accounting": _hold_accounting(operation)}
    try:
        op, unused = _failed_original_state(operation)
        held = _PRESERVATION_HOLD.get(operation)
        require(type(held) is tuple and len(held) == 6 and held[5] is op,
            "durable_capture_preservation_changed")
        result["original_failure"] = {"availability": "available",
            "fixed_diagnostic": _fixed_hold_diagnostic(failure_summary(held[4]))}
    except BaseException:
        pass
    try:
        failures = _PRESERVATION_FAILURES.get(operation, ())
        require(type(failures) is tuple and (not failures
            or failures is _PRESERVATION_FAILURE_ORIGINS.get(operation)) and len(failures) <= 16,
            "durable_capture_preservation_changed")
        details = [_fixed_hold_diagnostic(dict(item)) for item in failures]
        result["preservation_failures"] = {"availability": "available_partial", "fixed_diagnostics": details,
            "maximum_reported": 16, "negative_registry_authenticated": False}
        prepared = _PRESERVATION_LEASES.get(operation)
        require(type(prepared) is tuple and len(prepared) == 4
            and type(prepared[0]) is negative.OriginalPreservationLease,
            "durable_capture_preservation_changed")
        lease = prepared[0]; anchor = negative._original_anchor(lease)
        require(lease._anchor is lease._identity is anchor and anchor[1] is operation
            and anchor[2] is prepared[1] and anchor[3] is prepared[2], "durable_capture_preservation_changed")
        with anchor[10]:
            state = negative._STATES.get(lease)
            require(type(state) is tuple and len(state) == 3 and state is negative._STATE_PINS.get(lease)
                and type(state[2]) is tuple and len(state[2]) <= 528, "durable_capture_preservation_changed")
            for value in state[2]:
                detail = _fixed_hold_diagnostic(value)
                if detail not in details and len(details) < 16: details.append(detail)
        result["preservation_failures"] = {"availability": "available", "fixed_diagnostics": details,
            "maximum_reported": 16, "negative_registry_authenticated": True}
    except BaseException:
        pass
    return result


def _retention_summary():
    summaries = _negative_summaries()
    operations = tuple(_PRESERVATION_HOLD)
    require(len(operations) <= 133, "durable_capture_preservation_changed")
    return {"schema": "si-count-private-retention-hold-v1", "status": "preservation_blocked",
        "requires_process_hold": True, "blocked_operations": len(_BLOCKED_OPERATIONS) or len(summaries),
        "known_private_observations_retained": sum(item["retained_opaque_observations"] for item in summaries),
        "known_private_observations_are_complete": False,
        "operation_diagnostics": [_hold_diagnostics(operation) for operation in operations],
        "additional_HTTP_from_hold": 0, "new_claims_from_hold": 0, "new_STARTs_from_hold": 0,
        "new_credentials_from_hold": 0, "authority": authority()}


def _requires_process_hold():
    summaries = _negative_summaries()
    return bool(_BLOCKED_OPERATIONS) or any(summary["requires_process_hold"] for summary in summaries)


def _persist_hold_report(raw):
    """Durable owner-only copy of the fixed hold projection; never a release.

    Only this process retains unexported RAM bytes. A launcher's lifetime is
    a prospective risk; exec13448's disappearance cause is UNKNOWN. The copy
    lets the projection's accounting outlive
    stdout and the process. Its name is the SHA-256 of its exact bytes, so a
    truncated or edited copy is self-evidently invalid; no file is replaced.
    """
    require(type(raw) is str and bool(raw), "durable_capture_hold_report_refused")
    record = {"schema": "si-count-hold-report-v1",
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "process_id": os.getpid(), "retention_summary": json.loads(raw),
        "private_bytes_retained_only_by_holding_process": True, "release_or_settlement_authority": False}
    data = canonical_json(record).encode()
    require(0 < len(data) <= 2 * 1024 ** 2, "durable_capture_hold_report_refused")
    digest = hash_bytes(data); directory = HOLD_REPORT_DIRECTORY
    require(type(directory) is type(ROOT) and directory.is_absolute()
        and directory.resolve() == directory, "durable_capture_hold_report_refused")
    containing = directory.parent
    def directory_pin(info, *, report=False):
        mode = stat.S_IMODE(info.st_mode)
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
            and (mode == 0o700 if report else not mode & 0o022), "durable_capture_hold_report_refused")
        return info.st_dev, info.st_ino, info.st_uid, info.st_gid, mode
    def file_pin(info, size):
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o400 and info.st_nlink == 1 and info.st_size == size,
            "durable_capture_hold_report_refused")
        return info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode), info.st_nlink
    parent_pin = directory_pin(containing.lstat())
    parent = os.open(containing, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    name = "hold-" + digest + ".json"
    try:
        def check_parent():
            require(containing.resolve() == containing
                and directory_pin(os.fstat(parent)) == parent_pin
                and directory_pin(containing.lstat()) == parent_pin, "durable_capture_hold_report_refused")
        check_parent()
        try: os.mkdir(directory.name, mode=0o700, dir_fd=parent)
        except FileExistsError: pass
        named = os.stat(directory.name, dir_fd=parent, follow_symlinks=False)
        report_pin = directory_pin(named, report=True)
        report = os.open(directory.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            def check_directory():
                check_parent()
                require(directory.resolve() == directory
                    and directory_pin(os.fstat(report), report=True) == report_pin
                    and directory_pin(os.stat(directory.name, dir_fd=parent, follow_symlinks=False), report=True) == report_pin
                    and directory_pin(directory.lstat(), report=True) == report_pin,
                    "durable_capture_hold_report_refused")
            check_directory()
            fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400, dir_fd=report)
            try:
                os.fchmod(fd, 0o400)  # Exact owner-only mode even under a restrictive umask; fresh inode only.
                created = file_pin(os.fstat(fd), 0)
                def check_file(size):
                    check_directory()
                    require(file_pin(os.fstat(fd), size) == created
                        and file_pin(os.stat(name, dir_fd=report, follow_symlinks=False), size) == created,
                        "durable_capture_hold_report_refused")
                offset = 0
                while offset < len(data):
                    check_file(offset)
                    amount = os.write(fd, memoryview(data)[offset:])
                    require(type(amount) is int and 0 < amount <= len(data) - offset,
                        "durable_capture_hold_report_refused")
                    offset += amount
                def full_file_stamp(info):
                    return (*file_pin(info, len(data)), info.st_size, info.st_mtime_ns, info.st_ctime_ns,
                        getattr(info, "st_flags", None))
                sealed = full_file_stamp(os.fstat(fd))
                def check_sealed():
                    check_file(len(data))
                    require(full_file_stamp(os.fstat(fd)) == sealed
                        and full_file_stamp(os.stat(name, dir_fd=report, follow_symlinks=False)) == sealed,
                        "durable_capture_hold_report_refused")
                check_sealed(); os.fsync(fd); check_sealed()
                os.fsync(report); check_sealed()
                # This existing directory owns the newly created report-directory link.
                os.fsync(parent); check_sealed()
                # Read only this invocation's original O_EXCL inode. No named file is reopened or adopted.
                os.lseek(fd, 0, os.SEEK_SET); remaining, blocks = len(data), []
                while remaining:
                    check_sealed(); amount = min(65536, remaining)
                    block = os.read(fd, amount)
                    require(type(block) is bytes and 0 < len(block) <= amount,
                        "durable_capture_hold_report_refused")
                    blocks.append(block); remaining -= len(block); check_sealed()
                require(b"".join(blocks) == data, "durable_capture_hold_report_refused")
                check_sealed()
            finally: os.close(fd)
            check_directory()
            require(full_file_stamp(os.stat(name, dir_fd=report, follow_symlinks=False)) == sealed,
                "durable_capture_hold_report_refused")
        finally: os.close(report)
        check_parent()
        require(directory_pin(os.stat(directory.name, dir_fd=parent, follow_symlinks=False), report=True) == report_pin,
            "durable_capture_hold_report_refused")
    finally: os.close(parent)
    # Successful descriptor cleanup cannot hide a last named-entry change.
    require(containing.resolve() == containing and directory.resolve() == directory
        and directory_pin(containing.lstat()) == parent_pin
        and directory_pin(directory.lstat(), report=True) == report_pin
        and full_file_stamp((directory / name).lstat()) == sealed, "durable_capture_hold_report_refused")
    return digest


def _retain_failed_process():
    """Keep independent ROFDs/private bytes alive; no network or cleanup API."""
    require(_requires_process_hold(), "durable_capture_retention_required")
    if "announced" not in _RETENTION_ANNOUNCED:
        raw = durable = None
        try: raw = canonical_json(_retention_summary())
        except BaseException: pass  # No summary failure authorizes losing private RAM/FDs.
        if raw is not None:
            # Durable copy first: an unread stdout pipe can block, and its
            # reader can vanish with the launching session.
            try: durable = _persist_hold_report(raw)
            except BaseException: pass  # A failed copy never releases the hold.
            try:
                print(raw, flush=True)
                print(canonical_json({"schema": "si-count-hold-report-persistence-v1",
                    "durable_report_written": durable is not None, "durable_report_sha256": durable}), flush=True)
            except BaseException:
                pass  # No notification failure authorizes losing private RAM/FDs.
        _RETENTION_ANNOUNCED.add("announced")
    while True: time.sleep(30)


def _fill_live_chunk(operation, volume, lease, budget):
    base = source_lease_binding(lease)[11]
    for path in (base, base / "starts", base / "received", base / "responses"):
        _new_directory(operation, path)
    with _owned(operation, transport._control_directory(operation, "claim")) as owned:
        with controls.prepare_owned_count_claim(owned, operation,
                boundary=lambda: _source_boundary(lease)) as claim: pass
    chunk = budget.public_summary()["current_chunk"]
    _schedule_chunk_attempts(operation, budget, claim)
    candidate = operation.freeze_provisional_root()
    for role in transport.FINAL_ROLES:
        with _owned(operation, transport._control_directory(operation, role)) as owned:
            with controls.prepare_owned_count_final_control(owned, operation, candidate, role=role,
                    boundary=lambda: _source_boundary(lease)) as final: pass
        operation.accept_final_control(final)
    _RUNS[operation] = transport.operation_binding(operation), candidate, volume, claim, object()
    _RUN_ORIGINS[operation] = _RUNS[operation]
    _audit_membership(operation, candidate); volume.check()
    from scripts import short_interest_count_checkpoint as checkpoints
    checkpoint = checkpoints.publish_provisional_chunk_checkpoint(operation, candidate)
    bound = checkpoints.checkpoint_binding(checkpoint)
    require(type(bound) is tuple and len(bound) == 12 and bound[1] is operation
        and bound[2] is candidate and bound[3] == "chunk", "durable_capture_checkpoint_changed")
    _WRITTEN_CHECKPOINTS[operation] = checkpoint, bound
    if chunk == len(budget.plan._parts[3]):
        round_cap = checkpoints.publish_provisional_round_checkpoint(operation, candidate)
        round_bound = checkpoints.checkpoint_binding(round_cap)
        require(round_bound[1] is operation and round_bound[2] is candidate and round_bound[3] == "round",
            "durable_capture_checkpoint_changed")
    return candidate


def _retain_settled_contribution(budget, contribution):
    """Only an irreversible original account7 append admits the snapshot."""
    require(type(contribution) is transport_union.ClosedCountTransportContribution,
        "durable_capture_contribution_changed")
    original = transport_union.contribution_binding(contribution)
    journal = accounting.settled_chunk_accounting(budget)
    existing = _SETTLED_CONTRIBUTIONS.get(budget, ())
    require(type(existing) is tuple and (not existing or _CONTRIBUTION_ORIGINS.get(budget) is existing)
        and type(journal) is tuple and len(journal) == 4 and journal[0] is budget
        and type(journal[3]) is tuple and len(journal[3]) == len(existing) + 1
        and original[3] is budget and original[4] is journal[1] and original[2] is journal[2]
        and original[5] is journal[3][-1] and original[5][2] == len(existing) + 1,
        "durable_capture_contribution_changed")
    retained = (*existing, contribution)
    _SETTLED_CONTRIBUTIONS[budget] = _CONTRIBUTION_ORIGINS[budget] = retained


def _original_settled_contributions(budget):
    retained = _SETTLED_CONTRIBUTIONS.get(budget)
    journal = accounting.settled_chunk_accounting(budget)
    require(type(retained) is tuple and _CONTRIBUTION_ORIGINS.get(budget) is retained
        and len(retained) == len(journal[3]), "durable_capture_contribution_changed")
    for contribution, account in zip(retained, journal[3]):
        original = transport_union.contribution_binding(contribution)
        require(original[3] is budget and original[4] is journal[1] and original[2] is journal[2]
            and original[5] is account, "durable_capture_contribution_changed")
    return retained


def _capture_chunk(token, budget, *, root, runtime_head, actual_remote, complete_code_manifest):
    registered(); operation = volume = None
    try:
        with _prepare_registered_source_lease(token, budget, root=root, runtime_head=runtime_head,
                actual_remote=actual_remote, complete_code_manifest=complete_code_manifest) as lease:
            operation = transport.bind_registered_operation(lease, budget)
            with storage.prepare_registered_volume(root, operation=operation,
                    boundary=lambda: _source_boundary(lease)) as volume:
                operation.bind_volume(volume)
                from scripts import short_interest_count_checkpoint as checkpoints
                checkpoints.preflight_checkpoint_resources(operation, volume)
                preservation = negative.prepare_original_preservation_lease(operation, volume)
                require(type(preservation) is negative.OriginalPreservationLease,
                    "durable_capture_preservation_changed")
                _PRESERVATION_LEASES[operation] = preservation, transport.operation_binding(operation), volume, object()
                profile = negative.authority()
                require(type(profile) is dict and all(type(name) is str and type(value) in (bool, int)
                    for name, value in profile.items()) and profile.get("source_admitted") is False
                    and profile.get("budget_release_authority") is False and profile.get("HTTP_authority") is False
                    and profile.get("retry_authority") is False and profile.get("ready_for_backtest") is False,
                    "durable_capture_preservation_changed")
                _PRESERVATION_PROFILES[operation] = tuple(profile.items())
                try:
                    candidate = _fill_live_chunk(operation, volume, lease, budget)
                except BaseException as error:
                    report = _preserve_failed_chunk(operation, volume, error)
                    if report is not None and report["requires_process_hold"]: _retain_failed_process()
                    raise
            # Volume's original contexts/FDs have closed, source/code still held.
            volume.check_after_close(); source_lease_live_binding(lease)
        # Now source/code contexts and their fresh committed-code audits closed.
        result = _finish_original_chunk(operation, candidate)
        contribution = transport_union.freeze_closed_count_transport_contribution(result)
        budget.settle_closed_chunk(result)
        _retain_settled_contribution(budget, contribution)
        return result
    except BaseException as error:
        if operation is not None:
            report = _preserve_failed_chunk(operation, volume, error)
            if report is not None and report["requires_process_hold"]: _retain_failed_process()
        raise


def run_registered(root, *, runtime_head, actual_remote, complete_code_manifest, archive_code_manifest):
    registered(); _require_lane_root(root)
    source_scope.require_dispatch_allowed()
    token = load_registered_closed_archive(root, runtime_head=runtime_head, actual_remote=actual_remote,
        complete_code_manifest=archive_code_manifest)
    plan = freeze_recovery_from_archive(token); budget = accounting.open_durable_count_budget(plan)
    closed = []
    for unused in range(1, len(plan._parts[3]) + 1):
        closed.append(_capture_chunk(token, budget, root=root, runtime_head=runtime_head,
            actual_remote=actual_remote, complete_code_manifest=complete_code_manifest))
        progress = budget.public_summary()
        try:
            print(canonical_json({"schema": "si-count-registered-capture-progress-v1", "stage": "original_chunk_closed",
                "closed_chunks": progress["closed_chunks"], "planned_chunks": len(plan._parts[3]),
                "cumulative_START_reservations_upper_bound": progress["cumulative_START_debits_upper_bound"],
                "cumulative_charged_plus_reserved_bytes": progress["cumulative_charged_plus_reserved_bytes"],
                "source_qualified": False, "qc_attempts": 0}), flush=True)
        except OSError:
            pass  # Optional progress transport cannot discard settled data.
    union = transport_union.seal_count_transport_union(sourcelease_model(token), plan,
        _original_settled_contributions(budget), budget)
    from scripts import short_interest_count_checkpoint as checkpoints
    roots = checkpoints.final_checkpoint_roots()
    result = {"schema": "si-durable-count-transport-round-v1", "status": "transport_union_only_source_unqualified",
        "closed_chunks": len(closed), "transport_union": union.public_summary(), "transport_union_sha256": union.sha256,
        "checkpoint_roots": roots, "authority": authority()}
    # No saved pre-exit file is relabelled process closure. Only a separately
    # Main-observed actual exit0 plus independent roots can authorize rereading.
    canonical_json(result); checkpoints.audit_original_checkpoint_roots()
    return result


def _committed_CLI_manifest(guard, head):
    paths = code_paths(); manifest = {}
    guard.refresh()
    with archive_loader.count.old.cache.HeldFiles(tuple(ROOT / name for name in paths),
            protected=False, boundary=guard.check) as code:
        for name in paths:
            raw = code.read(ROOT / name, 8 * 1024 ** 2)
            committed = archive_loader.count.old.cache._git(ROOT, ["show", head + ":" + name], guard)
            require(hash_bytes(raw) == hash_bytes(committed), "durable_capture_code_changed")
            manifest[name] = hash_bytes(raw)
        code.check()
    guard.refresh(); _manifest_shape(manifest)
    return manifest


def _run_cli(arguments):
    registered(); _require_lane_root(ROOT)
    require(type(arguments) is argparse.Namespace and arguments.command == "run_registered"
        and all(type(value) is str and re.fullmatch(r"[0-9a-f]{40}", value)
            for value in (arguments.runtime_head, arguments.actual_remote)), "durable_capture_CLI_arguments_refused")
    source_scope.require_dispatch_allowed()
    guard = lane.LaneGuard(ROOT, expected_head=arguments.runtime_head, expected_remote=arguments.actual_remote)
    manifest = _committed_CLI_manifest(guard, arguments.runtime_head)
    archive_manifest = {name: manifest[name] for name in archive_loader.code_paths()}
    guard.refresh()
    print(canonical_json({"schema": "si-count-registered-capture-start-v1", "stage": "before_original_archive_replay",
        "runtime_HEAD": arguments.runtime_head, "actual_remote": arguments.actual_remote,
        "source_authority_sha256": SOURCE_AUTHORITY_SHA256, "run_protocol_sha256": RUN_PROTOCOL_SHA256,
        "new_HTTP_started": False, "authority": authority()}), flush=True)
    return run_registered(ROOT, runtime_head=arguments.runtime_head, actual_remote=arguments.actual_remote,
        complete_code_manifest=manifest, archive_code_manifest=archive_manifest)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Registered finite source-only count recovery")
    parser.add_argument("command", choices=("run_registered",))
    parser.add_argument("--runtime-head", required=True); parser.add_argument("--actual-remote", required=True)
    arguments = parser.parse_args(argv)
    try:
        result = _run_cli(arguments)
        print(canonical_json(result)); return 0
    except BaseException as error:
        if _requires_process_hold(): _retain_failed_process()
        print(canonical_json({"status": "refused", "fixed_diagnostic": failure_summary(error),
            "negative_preservation": _negative_summaries(), "authority": authority()}))
        return 2


if __name__ == "__main__":
    # Transport resolves this canonical module; never split its type/registry
    # identity by minting a second __main__.CountSourceLease.
    from scripts.capture_short_interest_durable_counts import main as canonical_main
    raise SystemExit(canonical_main())
