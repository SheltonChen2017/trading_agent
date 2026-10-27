"""Finite source-only count coordinator; production registration is pending.

The old archive's finite context closes before any new chunk begins.  Its
original closed model is lineage, not a perpetual assertion about old files.
Only this outer factory may issue terminal accounting after every original
source/code/output/storage context and all original-pin audits have closed.
No caller callback, JSON receipt, complete flag or pair closure is authority.
"""
from contextlib import contextmanager
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
from scripts import diagnose_short_interest_body_receipt_custody as antecedent

ROOT, BRANCH = transport.ROOT, lane.BRANCH
SOURCE_AUTHORITY_SHA256 = "PENDING"
RUN_PROTOCOL_SHA256 = "PENDING"
NEGATIVE_PRESERVATION_POLICY_SHA256 = "PENDING"
BASELINE_LEDGER_SHA256 = research_budget.BASELINE_LEDGER_SHA256
MAXIMUM_CHUNK_SECONDS, MAXIMUM_ARCHIVES = 3600, 1
DRIVER = "scripts/capture_short_interest_durable_counts.py"
_ARCHIVES, _ARCHIVE_PLANS, _ARCHIVE_FAILED = {}, {}, set()
_LEASES, _LEASE_FAILED, _LEASE_TERMINALS, _LEASE_PHASES, _LEASE_CLOCKS = {}, set(), {}, {}, {}
_RUNS, _RUN_ORIGINS, _TERMINALS, _TERMINAL_ORIGINS, _TERMINAL_FAILED = {}, {}, {}, {}, set()
_DIRECTORIES, _PRESERVATION_HOLD = {}, {}
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
durable_capture_unqualified_result durable_capture_retry_exhausted""".split())


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
        "research/short_interest_etf/native_count_recovery_budget.py"))))


def protocol():
    return {"schema": "si-durable-count-capture-v1", "source_authority_sha256": SOURCE_AUTHORITY_SHA256,
        "operator_protocol_sha256": transport.PROTOCOL_SHA256,
        "negative_preservation_policy_sha256": NEGATIVE_PRESERVATION_POLICY_SHA256,
        "archive_baseline_sha256": BASELINE_LEDGER_SHA256, "archive_context": "original_closed_before_new_chunk",
        "maximum_chunk_seconds": MAXIMUM_CHUNK_SECONDS, "maximum_archives": MAXIMUM_ARCHIVES,
        "maximum_inflight": 8, "positions_per_chunk": 512, "extra_STARTs_per_chunk": 16,
        "maximum_cumulative_STARTs": 84005, "maximum_cumulative_bytes": 4 * 1024 ** 3,
        "per_file_creation_seconds": 8, "volume_whole_seconds": 3600,
        "directory_width": 6, "payload": "capture", "external_claim": "claim/claim.spent.json",
        "manifest": "all_capture_files_except_self_pinned_separately_original_typed_controls",
        "closed_control": "terminal_intent_only_until_original_outer_finish",
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
        (reader, "ClosedCountChunkRefusal"), (accounting, "DurableCountBudgetRefusal")):
        if type(error) is getattr(module, name, None): return module.failure_summary(error)
    return transport.failure_summary(error)


def _digest(value): return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def registered():
    require(all(_digest(value) for value in (SOURCE_AUTHORITY_SHA256, RUN_PROTOCOL_SHA256,
        NEGATIVE_PRESERVATION_POLICY_SHA256, transport.PROTOCOL_SHA256))
        and SOURCE_AUTHORITY_SHA256 == transport.SOURCE_AUTHORITY_SHA256
        and hash_payload(protocol()) == RUN_PROTOCOL_SHA256
        and BASELINE_LEDGER_SHA256 == research_budget.BASELINE_LEDGER_SHA256
        and type(MAXIMUM_CHUNK_SECONDS) is int and MAXIMUM_CHUNK_SECONDS == 3600
        and type(MAXIMUM_ARCHIVES) is int and MAXIMUM_ARCHIVES == 1,
        "durable_capture_registration_pending")
    # This is an honest extra deployment barrier.  RAM drain alone does not
    # durably preserve an already received body after process death.  No new
    # provider invocation is valid until a fixed negative publisher exists.
    raise DurableCountCaptureRefusal("REFUSED: durable_capture_negative_preservation_pending")


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


def _expected_output(root, plan, chunk):
    return root / storage.PARENT / (storage.NAMESPACE_PREFIX + "-" + plan.sha256 + f"-chunk{chunk:03d}") / storage.MOUNT_NAME / "capture"


@contextmanager
def _prepare_registered_source_lease(token, budget, *, root, runtime_head, actual_remote, complete_code_manifest):
    registered()
    require(root == ROOT and root.resolve() == root and Path.cwd().resolve() == root,
        "durable_capture_exact_root_required")
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
    with _owned(operation, transport._control_directory(operation, "start", ticket)) as owned:
        with controls.prepare_owned_count_start(owned, operation, ticket, claim,
                boundary=lambda: _source_boundary(transport.operation_binding(operation)[12])) as start: pass
    observed = operation.dispatch(ticket, claim, start)
    require(type(observed) is transport.HttpObservation, "durable_capture_unqualified_result")
    with _owned(operation, transport._control_directory(operation, "received", ticket)) as owned:
        with controls.prepare_owned_count_received(owned, operation, observed,
                boundary=lambda: _source_boundary(transport.operation_binding(operation)[12])) as received: pass
    operation.accept_received_control(received)
    raw = transport.http_observation_binding(observed)[10]
    if type(raw) is bytes and raw:
        base = source_lease_binding(transport.operation_binding(operation)[12])[11]
        with _owned(operation, base / "responses" / f"{accounting.ticket_binding(ticket)[4]:06d}") as owned:
            with responses.prepare_owned_count_response(owned, ticket=ticket, observation=observed,
                    boundary=lambda: _source_boundary(transport.operation_binding(operation)[12])) as pair: pass
        operation.accept_closed_response(pair)
    return observed


def _capture_chunk(token, budget, *, root, runtime_head, actual_remote, complete_code_manifest):
    registered(); operation = volume = None
    try:
        with _prepare_registered_source_lease(token, budget, root=root, runtime_head=runtime_head,
                actual_remote=actual_remote, complete_code_manifest=complete_code_manifest) as lease:
            operation = transport.bind_registered_operation(lease, budget)
            with storage.prepare_registered_volume(root, operation=operation,
                    boundary=lambda: _source_boundary(lease)) as volume:
                operation.bind_volume(volume); base = source_lease_binding(lease)[11]
                for path in (base, base / "starts", base / "received", base / "responses"):
                    _new_directory(operation, path)
                with _owned(operation, transport._control_directory(operation, "claim")) as owned:
                    with controls.prepare_owned_count_claim(owned, operation,
                            boundary=lambda: _source_boundary(lease)) as claim: pass
                # Serial scheduling is within <=8 in-flight. Every retry gets
                # its own original budget ticket and durable START; dispatch
                # independently enforces the original position retry chain.
                chunk = budget.public_summary()["current_chunk"]
                for position in budget.plan.chunk_positions(chunk):
                    epoch_attempts = 0
                    while True:
                        ticket = budget.reserve_start_slot(position)
                        observed = _publish_attempt(operation, ticket, claim)
                        epoch_attempts += 1
                        bound = transport.http_observation_binding(observed)
                        if bound[9] == 200 and type(bound[10]) is bytes and bound[10]: break
                        detail = dict(bound[13] or ())
                        require(detail.get("retryable") is True and bound[9] is None,
                            "durable_capture_retry_exhausted")
                        time.sleep(2 if epoch_attempts == 1 else 10)
                candidate = operation.freeze_provisional_root()
                for role in transport.FINAL_ROLES:
                    with _owned(operation, transport._control_directory(operation, role)) as owned:
                        with controls.prepare_owned_count_final_control(owned, operation, candidate, role=role,
                                boundary=lambda: _source_boundary(lease)) as final: pass
                    operation.accept_final_control(final)
                _RUNS[operation] = transport.operation_binding(operation), candidate, volume, claim, object()
                _RUN_ORIGINS[operation] = _RUNS[operation]
                _audit_membership(operation, candidate); volume.check()
            # Volume's original contexts/FDs have closed, source/code still held.
            volume.check_after_close(); source_lease_live_binding(lease)
        # Now source/code contexts and their fresh committed-code audits closed.
        result = _finish_original_chunk(operation, candidate)
        budget.settle_closed_chunk(result)
        return result
    except BaseException:
        if operation is not None:
            transport._latch(operation)
            retained = []
            state = transport._OPERATIONS.get(operation)
            _PRESERVATION_HOLD[operation] = volume, (), state
            if state is not None:
                for observation in state[1][3]:
                    if type(observation) is transport.HttpObservation:
                        try: retained.append(transport.downgrade_http_observation_for_preservation(observation))
                        except BaseException: retained.append(observation)
                    else: retained.append(observation)
            # RAM is explicitly unqualified and not durable. Strongly retain
            # original capabilities and bytes rather than calling them closed.
            _PRESERVATION_HOLD[operation] = volume, tuple(retained), state
        raise


def run_registered(root, *, runtime_head, actual_remote, complete_code_manifest, archive_code_manifest):
    registered()
    token = load_registered_closed_archive(root, runtime_head=runtime_head, actual_remote=actual_remote,
        complete_code_manifest=archive_code_manifest)
    plan = freeze_recovery_from_archive(token); budget = accounting.open_durable_count_budget(plan)
    closed = []
    for unused in range(1, len(plan._parts[3]) + 1):
        closed.append(_capture_chunk(token, budget, root=root, runtime_head=runtime_head,
            actual_remote=actual_remote, complete_code_manifest=complete_code_manifest))
    return {"schema": "si-durable-count-transport-round-v1", "status": "transport_chunks_closed_only",
        "closed_chunks": len(closed), "budget": budget.public_summary(), "authority": authority()}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Registered finite source-only count recovery")
    parser.add_argument("command", choices=("run_registered",))
    parser.add_argument("--runtime-head", required=True); parser.add_argument("--actual-remote", required=True)
    arguments = parser.parse_args(argv)
    try:
        registered()  # CLI cannot bypass missing source/negative-preservation registration.
        raise DurableCountCaptureRefusal("REFUSED: durable_capture_registration_pending")
    except BaseException as error:
        print(canonical_json({"status": "refused", "fixed_diagnostic": failure_summary(error), "authority": authority()}))
        return 2


if __name__ == "__main__": raise SystemExit(main())
