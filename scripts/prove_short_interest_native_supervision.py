"""Fresh typed source-free native-supervision proof; no V1 result admission.

PTY bytes are observation only. A Root-closed in-memory result requires an
actual kernel0 receipt and independently authenticated original APFS controls.
A durable Main receipt/SourceAUTH bridge is deliberately unavailable here.
"""
import argparse
import base64
from contextlib import contextmanager
import ctypes
import errno
import json
import math
import os
from pathlib import Path
import plistlib
import re
import secrets
import socket
import stat
import subprocess
import sys
import time
import zlib

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import short_interest_count_native_supervisor as old
from scripts import diagnose_short_interest_native_supervisor_startup as startup

worker, native = old.worker, old.native
ROOT, PARENT = old.ROOT, old.PARENT
MODULE = "scripts.prove_short_interest_native_supervision"
DRIVER = "scripts/prove_short_interest_native_supervision.py"
BOOTSTRAP = "si-native-supervision-v2-v4-bootstrap"
DOMAIN = "si-native-supervision-v2-v4-domain"
LABEL = "com.openai.codex.short-interest-native-supervision-v2-v4"
POLICY_SHA256 = "848ceb48bc42aa02a4974d95da2ba113c172a26aed31d5d0827a4a8fa62c3a94"
CODE_FILES = (*old.CODE_FILES, startup.DRIVER, DRIVER)
MAXIMUM_SECONDS, COMMAND_SECONDS, VIRTUAL_BYTES = 300, 120, 8 * 1024 ** 3
MAXIMUM_NATIVE_BYTES, MAXIMUM_CONTROL_BYTES, MAX_CONFIG, MAX_WIRE = 4194304, 4096, 4096, 1024
RAW_ROLES = ("native.before.plist", "native.create.plist", "native.attach.plist", "native.initial.plist", "native.terminal.plist")
PRIVATE_ROLES = ("child.failure.buffers.private.json", "child.remaining.pipe.private.bin", "child.partial.stdout.private.bin", "child.negative.closed.json", "child.returned.stdout.private.json")
NEGATIVE_SECONDS, MAXIMUM_PRIVATE_BYTES, MAXIMUM_TRACE_FRAMES = 5, 65536, 128
SYSTEM_INITIAL_SECONDS, SYSTEM_INITIAL_SAMPLES, SYSTEM_INITIAL_INTERVAL, SYSTEM_INITIAL_QUIET = 8, 33, 0.25, 1
UF_IMMUTABLE = 2  # Fixed Darwin policy value; platform APIs are checked only at call time.
INVENTORY_ROLE, MARKER_ROLE = "metadata.inventory.private.json", "run.completed.provisional.json"
CONTROL_ROLES = ("run.started.json", "stdout.jsonl", "child.exit.provisional.json", MARKER_ROLE, "run.refused.json")
ROLES = RAW_ROLES + CONTROL_ROLES + (INVENTORY_ROLE,) + PRIVATE_ROLES
POSITIVE_ROLES = set(ROLES) - {"run.refused.json", *PRIVATE_ROLES}
LAUNCHCTL = "/bin/launchctl"
_COLLECT, _COLLECT_CODE = worker._collect, worker._collect.__code__
_USED = False
_STAGE, _COMPONENT = "registration", "operation"
_STAGES = frozenset("registration startup_import bootstrap current_code native_creation output_creation child_launch child_observation terminal_code terminal_native inventory_publication original_audit cleanup named_audit root_load root_observation root_verification root_cleanup".split())
_COMPONENTS = old._COMPONENTS | frozenset(("operation", "main_directory", "root_receipt"))
_CODES = old._CODES | startup._CODES | frozenset("supervision_unregistered supervision_arguments supervision_code supervision_factory supervision_changed supervision_wait supervision_kernel supervision_negative supervision_original supervision_unknown supervision_marker supervision_source_refused system_initialization_refused system_initial_identity_changed immutable_platform_refused immutable_creator_refused immutable_freeze_refused immutable_file_changed".split())
_ERRNOS = {**old._ERRNOS, **startup._ERRNOS}
_PRODUCERS, _CLOSED, _PREPARED, _HELD, _FAILURES, _ADVISORIES, _KERNEL_ORIGINS = {}, {}, {}, [], {}, {}, {}
_COMPARISONS, _PRESERVATIONS, _NEGATIVE_CLOSURES, _NEGATIVE_WAITS = {}, {}, {}, {}
_CAPTURED = []
_PRIVATE_FAILURES = {}
_STAMP_COMPARISON_ROLES = frozenset(("main_fd_original_seal", "main_named_original_seal", "stdout_fd_named_pair"))
_SYSTEM_PREDICATES = {"system_directory_type": "mode", "system_directory_mode": "mode", "system_directory_uid": "uid",
    "system_directory_gid": "gid", "system_directory_dev": "dev"}
_SYSTEM_COMPARISONS = frozenset(("system_original_metadata", "system_named_original_metadata"))
_COMPARISON_ROLES = _STAMP_COMPARISON_ROLES | _SYSTEM_COMPARISONS | frozenset(_SYSTEM_PREDICATES)
_CREATION_STATES, _CREATION_FAILURES, _CREATION_MANIFESTS, _SYSTEM_FAILURES, _PRODUCTION_SCOPES = {}, {}, {}, {}, {}
_NATIVE_PLANS, _NATIVE_INVOCATIONS = {}, {}
_SYSTEM_BASELINES = {}
_SYSTEM_INITIALIZATIONS, _FILE_CREATORS, _COLLECT_RETURNS, _STDOUT_FREEZES, _ACTIVE_FREEZES = {}, {}, {}, {}, {}
_RO_ORIGINS, _RO_HANDOFFS = {}, {}
CREATION_NATIVE_ROLES = tuple("creation.native." + role + ".private.plist" for role in ("before", "create", "attach", "initial", "terminal"))
CREATION_SYSTEM_ROLE = "creation.system.private.json"
CREATION_FAILURE_ROLE = "creation.failure.private.json"
CREATION_MANIFEST_ROLE = "creation.failure.manifest.private.json"
CREATION_ROLES = CREATION_NATIVE_ROLES + (CREATION_SYSTEM_ROLE, CREATION_FAILURE_ROLE, CREATION_MANIFEST_ROLE)
_stamp, _same, _dir, _drain, _write, _close = old._stamp, old._same, old._dir, old._drain, old._write, old._close


class SupervisionRefusal(ValueError): pass


def require(value, code):
    if not value: raise SupervisionRefusal("REFUSED: " + code)


def _phase(value):
    global _STAGE
    require(value in _STAGES, "supervision_arguments"); _STAGE = value


def _component(value, ordinal=0):
    global _COMPONENT
    require(value in _COMPONENTS and type(ordinal) is int and 0 <= ordinal <= 32, "supervision_arguments"); _COMPONENT = value


def _compared_stamp(actual, original, relation):
    """Keep the original comparison; attribute only this exact failed call."""
    require(relation in _STAMP_COMPARISON_ROLES, "supervision_arguments")
    try: _same(actual, original)
    except BaseException as error:
        trace = BaseException.__traceback__.__get__(error, BaseException); frame = None; genuine = False
        for unused in range(MAXIMUM_TRACE_FRAMES):
            if trace is None: break
            if trace.tb_frame.f_code is _compared_stamp.__code__ and trace.tb_frame.f_globals is globals(): frame = trace.tb_frame
            if trace.tb_frame.f_code is old._same.__code__ and trace.tb_frame.f_globals is old.__dict__: genuine = True
            trace = trace.tb_next
        caller = frame.f_back if frame is not None else None
        if genuine and frame is not None and _comparison_site(caller, relation, actual, original):
            fields = tuple(name for name, a, b in zip(old._STAMP_NAMES, actual, original) if a != b)
            _COMPARISONS[id(error)] = error, relation, fields, frame, actual, original, caller
        raise


def _comparison_site(frame, relation, actual, original):
    if (frame is None or frame.f_globals is not globals() or type(actual) is not tuple
            or type(original) is not tuple or len(actual) != 9 or len(original) != 9): return False
    local = frame.f_locals; instance = local.get("self")
    if relation == "stdout_fd_named_pair":
        return (frame.f_code is _Files.validate.__code__ and type(instance) is _Files
            and local.get("name") == "stdout.jsonl" and local.get("row") is instance.originals.get("stdout.jsonl")
            and local.get("row") is not None and local["row"][0] == local.get("fd")
            and actual == _stamp(local["a"]) and original == _stamp(local["b"]))
    return (type(instance) is _DomainVolume and original is instance.main_seal
        and (relation == "main_fd_original_seal" and frame.f_code is _DomainVolume.check.__code__
             or relation == "main_named_original_seal" and frame.f_code in (_DomainVolume.check.__code__, _DomainVolume.named.__code__)))


def _comparison(error):
    row = _COMPARISONS.get(id(error))
    if type(row) is not tuple or len(row) != 7 or row[0] is not error: return None
    frame = row[3]
    if (frame.f_code is not _compared_stamp.__code__ or frame.f_globals is not globals()
            or frame.f_locals.get("actual") is not row[4] or frame.f_locals.get("original") is not row[5]
            or frame.f_locals.get("relation") != row[1] or row[1] not in _COMPARISON_ROLES
            or not _comparison_site(row[6], row[1], row[4], row[5])): return None
    return row


def authority():
    return {"source_free_native_supervision_only": True, "source_admitted": False, "source_dispatch_authority": False,
        "budget_release_authority": False, "old_V1_admitted": False, "durable_Main_receipt": False,
        "ready_for_backtest": False, "provider_HTTP": 0, "credential_reads": 0, "source_STARTs": 0,
        "source_bytes": 0, "new_source_claims": 0, "QC_or_Safari": False, "qc_attempts": 0}


def policy():
    return {"schema": "si-native-supervision-v2-policy-v4", "root": str(ROOT), "bootstrap": BOOTSTRAP,
        "domain": DOMAIN, "label": LABEL, "code_files": list(CODE_FILES), "roles": list(ROLES),
        "virtual_bytes": VIRTUAL_BYTES, "maximum_seconds": MAXIMUM_SECONDS, "native_command_seconds": COMMAND_SECONDS,
        "config_bytes": MAX_CONFIG, "control_bytes": MAXIMUM_CONTROL_BYTES, "native_bytes": MAXIMUM_NATIVE_BYTES, "inventory_bytes": MAXIMUM_NATIVE_BYTES,
        "worker_log_bytes": worker.MAXIMUM_LOG_BYTES, "private_buffer_bytes": MAXIMUM_PRIVATE_BYTES, "private_buffer_files": list(PRIVATE_ROLES), "wire_bytes": MAX_WIRE,
        "negative_preservation": {"seconds": NEGATIVE_SECONDS, "trace_frames": MAXIMUM_TRACE_FRAMES,
            "relation_roles": sorted(_COMPARISON_ROLES), "frame": "exact_original_collector_code_globals_process_namespace_logFD_all_present_output_pending_line_block",
            "routing": "original_duplicate_reporter_FDs_only_no_positive_native_callback_no_rebaseline_no_retry_partial_names_immutable",
            "wait": "original_handle_EOF_then_known_original_or_separate_negative_wait_receipt_never_mint_positive_wait_or_recover_success",
            "closure": "all_consumed_bytes_retained_before_bounds_and_durably_preserved_original_seals_readback_fsync_cleanup_or_hold_all_contexts"},
        "private_observer_overflow": "retain_exact_original_FD_raw_and_newly_consumed_block_before_refusal_never_slice_or_continue_consuming_after_failure",
        "system_initialization": {"seconds": SYSTEM_INITIAL_SECONDS, "samples": SYSTEM_INITIAL_SAMPLES,
            "interval": SYSTEM_INITIAL_INTERVAL, "quiet_seconds": SYSTEM_INITIAL_QUIET,
            "contract": "fresh_only_required_presence_same_five_predicates_first_valid_devino_pin_only_unsealed_nlink_candidate_may_restart_quiet_one_original_six_field_baseline_no_reinitialize"},
        "immutable_evidence": {"required_kernel_flag": UF_IMMUTABLE,
            "SDK": "fixed_lazy_usr_lib_libSystem_B_dylib_fchflags_int_fd_uint32_flags_int_return_errno_no_fallback",
            "contract": "new_original_OEXCL0600_singlelink_creator_FD_only_one_attempt_before_first_seal_no_flag_clear_rebaseline_adoption_old_seal_repair",
            "handle_handoff": "creation_time_independent_original_RO_OFD_one_atomic_dup2_replaces_owned_RW_numeric_slot_before_UF_and_FIRST9_two_RO_survivors_preflush_post_RO_fsync_exact_identity_bytes_no_retry",
            "handle_limit": "closed_code_no_other_owned_data_writer_alias_export_inheritance_or_writable_mmap_dup2_suppresses_target_close_errors_no_observed_last_close0_or_global_revocation_claim",
            "reader": "actual_kernel_flag_plus_all_original_nine_fields_bytes_and_owned_parent_each_audit",
            "stdout": "only_genuine_final_collect_validate_EOF_empty_pending_stages_original_wait0_before_first_local_seal_or_genuine_failed_unsealed_partial_before_first_negative_snapshot"},
        "creation_failure": {"roles": list(CREATION_ROLES), "native_each_bytes": MAXIMUM_NATIVE_BYTES,
            "native_total_bytes": len(CREATION_NATIVE_ROLES) * MAXIMUM_NATIVE_BYTES, "private_JSON_each_bytes": MAXIMUM_PRIVATE_BYTES,
            "routing": "original_APFS_mount_domain_anchors_seeded_after_owner_mode_before_first_system_no_proof_directory_or_host_status_adoption",
            "failure": "capture_original_instance_error_trace_native_results_and_system_baseline_observations_before_cleanup_then_exclusive_private_full9_readback_fsync_or_hold_all",
            "wire": "nullable_original_manifest_SHA_only_after_all_negative_context_cleanup_and_original_postclose_seals_no_baseline_values",
            "native_invocation": "original_command_frame_plan_and_independent_before_dispatch_issuer_distinguish_recorded_not_invoked_from_unknown_stdout_no_empty_default",
            "positive": "unchanged_root_membership_system_protection_six_field_original_equality_any_negative_root_role_permanently_vetoes"},
        "volume": "fresh_original_creator_APFS_local_nobrowse_owner_writable_global_unique_no_shadow_no_retry_detach_remount_adoption",
        "evidence": "original_OEXCL0600_singlelink_full9_and_readback_all_contexts_and_postclose_named_audits_no_negative",
        "worker": "unchanged_genuine_two_second_two_line_proof_worker_collect_original_wait0_within5seconds",
        "kernel": "Root_exact_loaded_job_one_initial_kickstart_p_no_k_pending_never_exited_never_zero_final_runs1_inactive_noPID_exit0",
        "result": "own_exact_factory_provenance_kernel0_childwait0_original_marker_inventory_native_and_code_conjunction_no_V1_cast",
        "Root_context_provenance": "exact_closed_original_reader_code_config_load_transaction_objects_immutable_private_snapshot_and_issuer_retained_by_RootReceipt_no_caller_flags_or_JSON",
        "kernel_provenance": "exact_issued_parsed_object_original_typed_CompletedProcess_exact_queryargv_returncode_boundedstdout_SHA_frozen_snapshot_issuer_retained_and_revalidated_by_Closed_getter_no_JSON_flags",
        "unknown": "hold_all_original_contexts_process_buffers_and_trace_indefinitely_while_alive_no_kill_restart_positive_recovery_start_attempt_latched_and_kernel_cleared_before_dispatch",
        "Root_final_native": "complete_original_native_and_control_sweep_after_last_callbacks_then_strict_nofollow_original_pin_verification_reads_postclose_no_rebaseline_new_hdiutil_or_creator_adoption",
        "Main_receipt": "fresh_parent_seeded_empty_pinned_APFS_main_directory_only_durable_writing_unavailable_SourceAUTH_blocked",
        "wrapper_body_sha256": hash_bytes(_wrapper_body().encode()), "wrapper_inline_sha256": hash_bytes(_wrapper().encode()),
        "authority": authority()}


def registered():
    require(type(POLICY_SHA256) is str and re.fullmatch(r"[0-9a-f]{64}", POLICY_SHA256)
        and hash_payload(policy()) == POLICY_SHA256 and _COLLECT is worker._collect and _COLLECT_CODE is worker._collect.__code__, "supervision_unregistered")
    require(CODE_FILES == (*old.CODE_FILES, startup.DRIVER, DRIVER), "supervision_code")
    _require_immutable_platform()


def failure_summary(error):
    previous = _FAILURES.get(id(error))
    if previous is not None and previous[0] is error:
        detail = json.loads(previous[1]); detail["creation_manifest_sha256"] = _creation_manifest(error); return detail
    code = None
    if type(error) is SupervisionRefusal:
        args = BaseException.args.__get__(error, BaseException)
        if type(args) is tuple and len(args) == 1 and type(args[0]) is str:
            code = next((v for v in _CODES if args[0] == "REFUSED: " + v), None)
    upstream = old.failure_summary(error)
    number = OSError.errno.__get__(error, OSError) if isinstance(error, OSError) else None
    number = number if type(number) is int else None
    comparison = _comparison(error); system = _system_failure(error)
    detail = {"stage": _STAGE, "component": _COMPONENT, "contract_code": code,
        "upstream_contract_code": upstream["contract_code"] or upstream["upstream_contract_code"],
        "errno_name": _ERRNOS.get(number) or upstream["errno_name"],
        "comparison_relation": system[1] if system is not None else comparison[1] if comparison is not None else None,
        "mismatching_fields": list(system[2]) if system is not None else list(comparison[2]) if comparison is not None else upstream["mismatching_fields"],
        "creation_manifest_sha256": _creation_manifest(error)}
    _FAILURES[id(error)] = error, canonical_json(detail); return detail


class _Clock:
    def __init__(self): self.clock = time.monotonic; self.begin = self.last = self.clock(); self.check()
    def check(self):
        now = self.clock(); require(type(now) in (int, float) and math.isfinite(now) and 0 <= self.begin <= self.last <= now, "native_proof_clock")
        require(now - self.begin <= MAXIMUM_SECONDS, "native_proof_deadline"); self.last = now; return MAXIMUM_SECONDS - (now - self.begin)


def _guard(head, remote): return worker._guard(head, remote)
def _git(arguments): return worker._git(arguments)
def _platform(): return native._platform()
def _native_statfs(fd): return native._native_statfs(fd)
def _device_node(device, mount_dev): return native._node_pin(device, mount_dev)
def _native_command(arguments, timeout):
    return subprocess.run(arguments, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        check=False, close_fds=True, timeout=timeout, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
def _launch_worker(head, remote):
    return subprocess.Popen([worker.PYTHON, "-B", "-m", worker.MODULE, "proof-worker", "--head", head, "--remote", remote],
        cwd=ROOT, env=worker._environment(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        shell=False, close_fds=True, start_new_session=True)
def _new_domain(clock): return _DomainVolume(clock)


def _require_immutable_platform():
    require(sys.platform == "darwin" and os.name == "posix" and ctypes.sizeof(ctypes.c_int) == 4
        and ctypes.sizeof(ctypes.c_uint32) == 4 and ctypes.sizeof(ctypes.c_void_p) == 8
        and getattr(stat, "UF_IMMUTABLE", None) == UF_IMMUTABLE
        and hasattr(os.stat_result, "st_flags"), "immutable_platform_refused")


def _file_flags(info):
    flags = getattr(info, "st_flags", None)
    require(type(flags) is int and 0 <= flags < 2 ** 32, "immutable_platform_refused")
    return flags


def _set_file_flags(fd, flags):
    _require_immutable_platform()
    require(type(fd) is int and 0 <= fd < 2 ** 31 and type(flags) is int and 0 <= flags < 2 ** 32
        and flags & UF_IMMUTABLE, "immutable_creator_refused")
    active = _ACTIVE_FREEZES.get(fd); caller = sys._getframe(1)
    require(type(active) is tuple and len(active) == 3, "immutable_creator_refused")
    row = _creator(active[0])
    require(caller.f_code is _freeze_new_file.__code__ and caller.f_globals is globals()
        and caller.f_locals.get("row") is row and caller.f_locals.get("cap") is active[0]
        and flags == active[1] == row["target_flags"] and row["attempted"] and not row["verified"]
        and not row.get("syscall_attempted") and "failure" not in row, "immutable_creator_refused")
    _readonly_handoff(row)
    a, b = _creator_current(row)
    require(_file_flags(a) == _file_flags(b) == flags & ~UF_IMMUTABLE
        and a.st_size == b.st_size == len(row["before_raw"]), "immutable_freeze_refused")
    row["syscall_attempted"] = True
    _sdk_fchflags(fd, flags)


def _sdk_fchflags(fd, flags):
    _require_immutable_platform()
    require(type(fd) is int and 0 <= fd < 2 ** 31 and type(flags) is int and 0 <= flags < 2 ** 32, "immutable_creator_refused")
    try: operation = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True).fchflags
    except (AttributeError, OSError): raise SupervisionRefusal("REFUSED: immutable_platform_refused") from None
    operation.argtypes, operation.restype = (ctypes.c_int, ctypes.c_uint32), ctypes.c_int
    caller = sys._getframe(1); active = _ACTIVE_FREEZES.get(fd)
    require(caller.f_code is _set_file_flags.__code__ and caller.f_globals is globals()
        and type(active) is tuple and active[1] == flags, "immutable_creator_refused")
    row = _creator(active[0])
    require(caller.f_locals.get("row") is row and row.get("syscall_attempted") is True
        and not row.get("sdk_invoked") and "failure" not in row, "immutable_creator_refused")
    _readonly_handoff(row)
    a, b = _creator_current(row)
    require(_file_flags(a) == _file_flags(b) == flags & ~UF_IMMUTABLE
        and a.st_size == b.st_size == len(row["before_raw"]), "immutable_freeze_refused")
    row["sdk_invoked"] = True
    ctypes.set_errno(0); result = operation(fd, flags); number = ctypes.get_errno()
    if type(result) is not int or result != 0:
        raise OSError(number if type(number) is int and number > 0 else errno.EIO, "immutable_flag_sdk_refused")


def _require_file_immutable(info):
    require(_file_flags(info) & UF_IMMUTABLE, "immutable_file_changed")


class _FileCreator:
    def __init__(self): raise SupervisionRefusal("REFUSED: immutable_creator_refused")


def _descriptor_access(fd):
    require(os.name == "posix" and type(fd) is int and fd >= 0, "immutable_platform_refused")
    try: import fcntl
    except ImportError: raise SupervisionRefusal("REFUSED: immutable_platform_refused") from None
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    require(type(flags) is int, "immutable_platform_refused")
    return flags & os.O_ACCMODE


def _owner_data_fds(owner):
    if type(owner) is _Files: return owner.fds
    if type(owner) is _CreationCarrier: return owner.file_fds
    require(type(owner) is _NegativeReporter, "immutable_creator_refused")
    return owner.private_fds


def _owned_handle_profile(row):
    """The supported closed code owns exactly two handles for this inode."""
    fds = tuple(_owner_data_fds(row["owner"])); expected = row["fd"], row["original_ro_fd"]
    require(fds.count(expected[0]) == fds.count(expected[1]) == 1, "immutable_creator_refused")
    for fd in fds:
        info = os.fstat(fd)
        if (info.st_dev, info.st_ino) == row["identity"][:2]:
            require(fd in expected, "immutable_creator_refused")


def _issue_file_creator(owner, name, fd, parent):
    frame = sys._getframe(1)
    require(any(frame.f_code is code and type(owner) is kind for code, kind in _CREATOR_SITES)
        and frame.f_globals is globals() and frame.f_locals.get("self") is owner
        and frame.f_locals.get("name") == name and frame.f_locals.get("fd") == fd
        and name not in owner.creators, "immutable_creator_refused")
    info = os.fstat(fd); named = os.stat(name, dir_fd=parent, follow_symlinks=False)
    identity = _negative_file(info, MAXIMUM_NATIVE_BYTES, empty=True)[:6]
    require(_stamp(named)[:6] == identity and _file_flags(info) == _file_flags(named)
        and not _file_flags(info) & UF_IMMUTABLE, "immutable_creator_refused")
    value = object.__new__(_FileCreator)
    row = {"cap": value, "owner": owner, "name": name, "fd": fd, "parent": parent, "path": owner.path,
        "parent_pin": _dir(os.fstat(parent), True), "identity": identity, "initial_flags": _file_flags(info),
        "attempted": False, "verified": False, "frozen9": None, "issuer_frame": frame, "issuer": object(),
        "writer_fd": fd, "original_ro_fd": None, "handoff_attempted": False, "handoff_verified": False}
    value._anchor = row; _FILE_CREATORS[value] = row; owner.creators[name] = value
    try:
        require(_descriptor_access(fd) == os.O_RDWR and os.get_inheritable(fd) is False, "immutable_creator_refused")
        # Independent creation-time RO OFD, before writing or closing the writer.
        ro = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        row["original_ro_fd"] = ro; _owner_data_fds(owner).append(ro)
        readonly = os.fstat(ro)
        require(ro != fd and _descriptor_access(ro) == os.O_RDONLY and os.get_inheritable(ro) is False
            and _negative_file(readonly, MAXIMUM_NATIVE_BYTES, empty=True)[:6] == identity
            and _file_flags(readonly) == row["initial_flags"], "immutable_creator_refused")
        _same(_stamp(readonly), _stamp(os.fstat(fd)))
        _same(_stamp(os.stat(name, dir_fd=parent, follow_symlinks=False)), _stamp(readonly))
        _RO_ORIGINS[value] = value, row, fd, ro, parent, identity, row["initial_flags"], frame, object()
    except BaseException as error:
        row["failure"], row["trace"] = error, BaseException.__traceback__.__get__(error, BaseException)
        raise
    return value


def _creator(cap):
    require(type(cap) is _FileCreator, "immutable_creator_refused")
    row = _FILE_CREATORS.get(cap)
    require(type(row) is dict and row.get("cap") is cap and cap._anchor is row
        and row["owner"].creators.get(row["name"]) is cap, "immutable_creator_refused")
    frame = row["issuer_frame"]
    require(frame.f_globals is globals() and any(frame.f_code is code and type(row["owner"]) is kind for code, kind in _CREATOR_SITES)
        and frame.f_locals.get("self") is row["owner"] and frame.f_locals.get("name") == row["name"]
        and frame.f_locals.get("fd") == row["fd"], "immutable_creator_refused")
    origin = _RO_ORIGINS.get(cap)
    require(type(origin) is tuple and len(origin) == 9 and origin[0] is cap and origin[1] is row
        and origin[2:7] == (row["fd"], row["original_ro_fd"], row["parent"], row["identity"], row["initial_flags"])
        and origin[7] is frame and row["writer_fd"] == row["fd"], "immutable_creator_refused")
    return row


def _creator_current(row):
    require(row["path"].resolve() == row["path"] and _dir(os.fstat(row["parent"]), True)
        == _dir(row["path"].lstat(), True) == row["parent_pin"], "immutable_creator_refused")
    a, b = os.fstat(row["fd"]), os.stat(row["name"], dir_fd=row["parent"], follow_symlinks=False)
    require(_negative_file(a, MAXIMUM_NATIVE_BYTES, empty=True)[:6] == _stamp(b)[:6] == row["identity"], "immutable_creator_refused")
    return a, b


def _handoff_readonly(cap, size, raw):
    """One pre-seal OFD transition; dup2 does not attest target-close success."""
    row = _creator(cap); caller = sys._getframe(1)
    require(caller.f_code is _freeze_new_file.__code__ and caller.f_globals is globals()
        and caller.f_locals.get("row") is row and caller.f_locals.get("cap") is cap
        and row["attempted"] and not row["verified"] and not row["handoff_attempted"]
        and type(raw) is bytes and len(raw) == size and row.get("before_raw") is raw, "immutable_creator_refused")
    row["handoff_attempted"] = True
    try:
        fd, ro = row["fd"], row["original_ro_fd"]
        _owned_handle_profile(row)
        require(_descriptor_access(fd) == os.O_RDWR and _descriptor_access(ro) == os.O_RDONLY
            and os.get_inheritable(fd) is os.get_inheritable(ro) is False, "immutable_creator_refused")
        a, b = _creator_current(row); r = os.fstat(ro)
        require(_negative_file(r, MAXIMUM_NATIVE_BYTES, empty=True)[:6] == row["identity"]
            and a.st_size == b.st_size == r.st_size == size
            and _file_flags(a) == _file_flags(b) == _file_flags(r) == row["initial_flags"], "immutable_freeze_refused")
        os.fsync(fd); os.fsync(row["parent"])
        os.lseek(ro, 0, os.SEEK_SET); before = os.read(ro, size + 1); row["handoff_before_raw"] = before
        require(before == raw, "immutable_freeze_refused")
        a, b = _creator_current(row); r = os.fstat(ro)
        require(_stamp(a) == _stamp(b) == _stamp(r) and a.st_size == size
            and _file_flags(a) == _file_flags(b) == _file_flags(r) == row["initial_flags"]
            and _descriptor_access(fd) == os.O_RDWR and _descriptor_access(ro) == os.O_RDONLY, "immutable_freeze_refused")
        row["dup2_attempted"] = True
        replaced = os.dup2(ro, fd, inheritable=False); row["dup2_returned"] = replaced
        require(type(replaced) is int and replaced == fd, "immutable_freeze_refused")
        require(_descriptor_access(fd) == _descriptor_access(ro) == os.O_RDONLY
            and os.get_inheritable(fd) is os.get_inheritable(ro) is False, "immutable_freeze_refused")
        a, b = _creator_current(row); r = os.fstat(ro)
        require(_stamp(a) == _stamp(b) == _stamp(r) and a.st_size == size
            and _file_flags(a) == _file_flags(b) == _file_flags(r) == row["initial_flags"], "immutable_freeze_refused")
        os.fsync(fd); os.fsync(ro); os.fsync(row["parent"])
        os.lseek(ro, 0, os.SEEK_SET); after = os.read(ro, size + 1); row["handoff_after_raw"] = after
        require(after == raw, "immutable_freeze_refused")
        a, b = _creator_current(row); r = os.fstat(ro)
        require(_stamp(a) == _stamp(b) == _stamp(r) and a.st_size == size
            and _file_flags(a) == _file_flags(b) == _file_flags(r) == row["initial_flags"]
            and _descriptor_access(fd) == _descriptor_access(ro) == os.O_RDONLY, "immutable_freeze_refused")
        frame = sys._getframe()
        receipt = cap, row, _RO_ORIGINS[cap], frame, fd, ro, size, raw, object()
        _RO_HANDOFFS[cap] = receipt; row["handoff_receipt"], row["handoff_verified"] = receipt, True
        return receipt
    except BaseException as error:
        row["handoff_error"], row["handoff_trace"] = error, BaseException.__traceback__.__get__(error, BaseException)
        raise


def _readonly_handoff(row, *, live=True):
    cap = row["cap"]; receipt = _RO_HANDOFFS.get(cap)
    require(type(receipt) is tuple and len(receipt) == 9 and receipt[0] is cap and receipt[1] is row
        and receipt[2] is _RO_ORIGINS.get(cap) and row.get("handoff_receipt") is receipt
        and row["handoff_attempted"] is row["handoff_verified"] is True
        and receipt[4:7] == (row["fd"], row["original_ro_fd"], len(row["before_raw"]))
        and receipt[7] is row["before_raw"], "immutable_creator_refused")
    frame = receipt[3]
    require(frame.f_code is _handoff_readonly.__code__ and frame.f_globals is globals()
        and frame.f_locals.get("row") is row and frame.f_locals.get("cap") is cap
        and frame.f_locals.get("replaced") == row["fd"]
        and frame.f_locals.get("raw") is receipt[7], "immutable_creator_refused")
    if live:
        _owned_handle_profile(row)
        require(_descriptor_access(row["fd"]) == _descriptor_access(row["original_ro_fd"]) == os.O_RDONLY
            and os.get_inheritable(row["fd"]) is os.get_inheritable(row["original_ro_fd"]) is False, "immutable_file_changed")
        a, b = _creator_current(row); r = os.fstat(row["original_ro_fd"])
        require(_negative_file(r, MAXIMUM_NATIVE_BYTES, empty=True)[:6] == row["identity"]
            and _stamp(a) == _stamp(b) == _stamp(r) and _file_flags(a) == _file_flags(b) == _file_flags(r), "immutable_file_changed")
        if row["verified"]:
            for observed in (a, b, r):
                require(_file_flags(observed) == row["frozen_flags"] and _file_flags(observed) & UF_IMMUTABLE, "immutable_file_changed")
                _same(_stamp(observed), row["frozen9"])
    return receipt


def _freeze_new_file(cap, size, expected_raw=None):
    row = _creator(cap)
    require(not row["attempted"], "immutable_freeze_refused"); row["attempted"] = True
    try:
        require(type(size) is int and 0 <= size <= MAXIMUM_NATIVE_BYTES
            and (expected_raw is None or type(expected_raw) is bytes and len(expected_raw) == size), "immutable_freeze_refused")
        owner = row["owner"]; original = owner.originals.get(row["name"])
        require(original is None or type(owner) is _Files and original[2] is None, "immutable_freeze_refused")
        if type(owner) is _Files and row["name"] == "stdout.jsonl":
            require(_stdout_freeze_origin(cap), "immutable_freeze_refused")
        a, b = _creator_current(row)
        require(a.st_size == b.st_size == size and _file_flags(a) == _file_flags(b) == row["initial_flags"], "immutable_freeze_refused")
        os.fsync(row["fd"]); os.fsync(row["parent"])
        os.lseek(row["fd"], 0, os.SEEK_SET); before = os.read(row["fd"], size + 1); row["before_raw"] = before
        require(type(before) is bytes and len(before) == size and (expected_raw is None or before == expected_raw), "immutable_freeze_refused")
        a, b = _creator_current(row)
        require(a.st_size == b.st_size == size and _file_flags(a) == _file_flags(b) == row["initial_flags"], "immutable_freeze_refused")
        _handoff_readonly(cap, size, before)
        target = row["initial_flags"] | UF_IMMUTABLE; row["target_flags"] = target
        _ACTIVE_FREEZES[row["fd"]] = cap, target, object()
        _set_file_flags(row["fd"], target); row["set_returned"] = True
        a, b = _creator_current(row)
        require(_file_flags(a) == _file_flags(b) == target and a.st_size == b.st_size == size, "immutable_freeze_refused")
        candidate = _stamp(a); row["post_flag9"] = candidate; _same(_stamp(b), candidate)
        os.lseek(row["fd"], 0, os.SEEK_SET); after = os.read(row["fd"], size + 1); row["after_raw"] = after
        require(after == before, "immutable_freeze_refused")
        os.fsync(row["fd"]); os.fsync(row["parent"])
        a, b = _creator_current(row); _same(_stamp(a), candidate); _same(_stamp(b), candidate)
        require(_file_flags(a) == _file_flags(b) == target, "immutable_file_changed")
        row["frozen9"], row["frozen_flags"], row["verified"] = candidate, target, True
        return candidate
    except BaseException as error:
        row["failure"], row["trace"] = error, BaseException.__traceback__.__get__(error, BaseException)
        raise


def _check_frozen(cap, info):
    row = _creator(cap)
    _readonly_handoff(row, live=not row["owner"].closed)
    require(row["verified"] is True and row["attempted"] is True and row["frozen9"] is not None, "immutable_freeze_refused")
    require(_file_flags(info) == row["frozen_flags"] and _file_flags(info) & UF_IMMUTABLE, "immutable_file_changed")
    _same(_stamp(info), row["frozen9"])
    return row["frozen9"]


def _freeze_stdout_final(outputs, fd, size, cap):
    row = _creator(cap)
    if row["verified"]: return
    frame = sys._getframe(2)
    if frame.f_code is not _COLLECT_CODE or frame.f_globals is not worker.__dict__: return
    local = frame.f_locals; process = local.get("process"); origin = worker._CHILDREN.get(process)
    wait = worker._WAITS.get(process)
    final = (local.get("ns") is outputs and local.get("log_fd") == fd and local.get("eof") is True
        and local.get("pending") == b"" and local.get("stages") == [] and local.get("status") == 0
        and type(wait) is tuple and len(wait) == 3 and wait[0] is origin and type(wait[1]) is int and wait[1] == 0
        and type(origin) is tuple and origin[0] is process and type(local.get("output")) is bytes
        and len(local["output"]) == size)
    if not final: return
    require("seal" not in local and process not in _COLLECT_RETURNS, "immutable_freeze_refused")
    require(0 <= worker._now() - local["began"] <= worker.MAXIMUM_SECONDS, "supervision_wait")
    _STDOUT_FREEZES[cap] = cap, "collector_final", frame, process, outputs, fd, origin, wait, local["output"], object()
    _freeze_new_file(cap, size, local["output"])
    require(0 <= worker._now() - local["began"] <= worker.MAXIMUM_SECONDS, "supervision_wait")
    row["collector_final"] = frame, process, outputs, fd, origin, wait, object()


def _stdout_freeze_origin(cap):
    receipt = _STDOUT_FREEZES.get(cap)
    if type(receipt) is not tuple or receipt[0] is not cap: return False
    if receipt[1] == "collector_final":
        if len(receipt) != 10: return False
        frame, process, outputs, fd, origin, wait, raw = receipt[2:9]
        local = frame.f_locals
        return (frame.f_code is _COLLECT_CODE and frame.f_globals is worker.__dict__ and local.get("process") is process
            and local.get("ns") is outputs and local.get("log_fd") == fd and local.get("output") is raw
            and local.get("eof") is True and local.get("pending") == b"" and local.get("stages") == []
            and worker._CHILDREN.get(process) is origin and worker._WAITS.get(process) is wait and wait[0] is origin and wait[1] == 0)
    if receipt[1] == "negative_partial":
        if len(receipt) != 5: return False
        state, caller = receipt[2:4]
        return (caller.f_code is _preserve_collection_failure.__code__ and caller.f_globals is globals()
            and caller.f_locals.get("state") is state and _preservation_state(state)
            and "seal" not in state["frame"].f_locals and state["process"] not in _COLLECT_RETURNS
            and state["eof"] and state["wait"] is not None and state["outputs"].creators.get("stdout.jsonl") is cap)
    return False


def _initialization_now(): return time.monotonic()
def _initialization_sleep(seconds): time.sleep(seconds)


@contextmanager
def _source_denied():
    changed = []
    def denied(*args, **kwargs): raise SupervisionRefusal("REFUSED: supervision_source_refused")
    def replace(obj, name): changed.append((obj, name, getattr(obj, name))); setattr(obj, name, denied)
    try:
        for name in ("connect", "connect_ex"): replace(socket.socket, name)
        for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyaddr"): replace(socket, name)
        yield
    finally:
        for obj, name, value in reversed(changed): setattr(obj, name, value)

class _Directory:
    """Original nofollow ancestry to one exclusively new or bootstrap directory."""
    def __init__(self, name, *, create):
        self.fds, self.nodes, self.closed = [], [], False
        self.path = ROOT / PARENT / name
        try:
            require(ROOT.resolve() == ROOT and Path.cwd().resolve() == ROOT, "native_proof_path")
            parent = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW); self.fds.append(parent)
            self.nodes.append((ROOT, parent, _dir(os.fstat(parent))))
            path = ROOT
            for part in (*PARENT.parts, name):
                path /= part
                if path == self.path and create:
                    try: os.stat(part, dir_fd=parent, follow_symlinks=False)
                    except FileNotFoundError: pass
                    else: raise SupervisionRefusal("REFUSED: native_proof_exists")
                    os.mkdir(part, 0o700, dir_fd=parent); os.fsync(parent)
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                self.fds.append(fd); self.nodes.append((path, fd, _dir(os.fstat(fd), path == self.path)))
                parent = fd
            self.fd, self.parent = self.fds[-1], self.fds[-2]; self.check()
        except BaseException:
            try: self.close()
            except BaseException: pass
            raise
    def check(self):
        require(not self.closed and ROOT.resolve() == ROOT and Path.cwd().resolve() == ROOT, "native_proof_path")
        for path, fd, pin in self.nodes:
            require(path.resolve() == path and _dir(path.lstat(), path == self.path)
                == _dir(os.fstat(fd), path == self.path) == pin, "native_proof_path")
    def named(self):
        for path, unused, pin in self.nodes:
            require(path.resolve() == path and _dir(path.lstat(), path == self.path) == pin, "native_proof_path")
    def close(self):
        try: _drain(self.fds)
        finally: self.closed = True


class _Files:
    def __init__(self, fd, parent, path, check, roles):
        self.fd, self.parent, self.path, self.callback, self.roles = fd, parent, path, check, frozenset(roles)
        self.originals, self.fds, self.closed, self.creators = {}, [], False, {}
    def check(self):
        self.callback()
        require(not self.closed and set(os.listdir(self.fd)) <= self.roles, "native_proof_membership")
    def create(self, name):
        self.check(); require(name in self.roles and name not in self.originals, "native_proof_membership")
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        self.fds.append(fd); os.fchmod(fd, 0o600)
        info = os.fstat(fd); self.originals[name] = [fd, _stamp(info)[:6], None, None]
        _issue_file_creator(self, name, fd, self.fd)
        self.validate(fd, name, 0); return fd
    def validate(self, fd, name, size):
        self.check(); row = self.originals.get(name)
        require(row is not None and row[0] == fd, "native_proof_protection")
        cap = self.creators.get(name)
        if name == "stdout.jsonl": _freeze_stdout_final(self, fd, size, cap)
        a, b = os.fstat(fd), os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        require(stat.S_ISREG(a.st_mode) and _stamp(a)[:6] == row[1]
            and a.st_uid == os.getuid() and stat.S_IMODE(a.st_mode) == 0o600 and a.st_nlink == 1
            and a.st_size == size, "native_proof_protection")
        if name == "stdout.jsonl": _compared_stamp(_stamp(a), _stamp(b), "stdout_fd_named_pair")
        else: _same(_stamp(a), _stamp(b))
        creator = _creator(cap)
        if creator["attempted"]:
            _check_frozen(cap, a); _check_frozen(cap, b)
        else: require(row[2] is None, "immutable_freeze_refused")
    def seal(self, name, fd, stamp, raw):
        cap = self.creators.get(name); require(_check_frozen(cap, os.fstat(fd)) == stamp, "immutable_freeze_refused")
        self.validate(fd, name, len(raw)); _same(_stamp(os.fstat(fd)), stamp)
        os.lseek(fd, 0, os.SEEK_SET)
        require(os.read(fd, len(raw) + 1) == raw, "native_proof_stamp")
        _check_frozen(cap, os.fstat(fd)); _same(_stamp(os.fstat(fd)), stamp)
        require(self.originals[name][2] is None, "native_proof_stamp")
        self.originals[name][2:] = stamp, raw
    def write(self, name, raw):
        limit = MAXIMUM_NATIVE_BYTES if name in RAW_ROLES or name == INVENTORY_ROLE else 65536 if name in PRIVATE_ROLES else MAXIMUM_CONTROL_BYTES
        require(type(raw) is bytes and 0 < len(raw) <= limit, "native_proof_write")
        fd = self.create(name); _write(fd, raw); self.validate(fd, name, len(raw))
        _freeze_new_file(self.creators[name], len(raw), raw)
        os.fsync(fd); os.fsync(self.fd); os.fsync(self.parent)
        self.seal(name, fd, _stamp(os.fstat(fd)), raw)
    def audit(self):
        self.check(); require(set(os.listdir(self.fd)) == set(self.originals), "native_proof_membership")
        for name, (fd, unused, stamp, raw) in self.originals.items():
            require(stamp is not None and type(raw) is bytes, "native_proof_stamp")
            self.validate(fd, name, len(raw)); _same(_stamp(os.fstat(fd)), stamp)
            os.lseek(fd, 0, os.SEEK_SET); require(os.read(fd, len(raw) + 1) == raw, "native_proof_stamp")
            _check_frozen(self.creators.get(name), os.fstat(fd)); _same(_stamp(os.fstat(fd)), stamp)
            _check_frozen(self.creators.get(name), os.stat(name, dir_fd=self.fd, follow_symlinks=False))
    def named(self):
        require(self.path.resolve() == self.path and set(os.listdir(self.path)) == set(self.originals), "native_proof_membership")
        for name, (unused, unused_pin, stamp, unused_raw) in self.originals.items():
            require(stamp is not None, "native_proof_stamp"); info = (self.path / name).lstat()
            _check_frozen(self.creators.get(name), info); _same(_stamp(info), stamp)
    def inventory(self):
        self.audit()
        require(INVENTORY_ROLE not in self.originals and "run.completed.provisional.json" not in self.originals,
            "native_proof_membership")
        return [{"name": name, "sha256": hash_bytes(row[3]), "bytes": len(row[3]), "original_stamp": list(row[2])}
            for name, row in sorted(self.originals.items())]
    def close(self):
        try: _drain(self.fds)
        finally: self.closed = True


class _Code7:
    def __init__(self, head, remote, clock):
        self.head, self.remote, self.clock, self.rows, self.fds = head, remote, clock, {}, []
        try:
            for ordinal, name in enumerate(CODE_FILES, 1):
                _component("code_file", ordinal)
                path = ROOT / name; require(path.resolve() == path, "native_proof_path")
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK); self.fds.append(fd)
                info = os.fstat(fd)
                require(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= 1024 ** 2, "native_proof_code")
                self.rows[name] = fd, _stamp(info), b""
            self.manifest = self.audit(initial=True)
        except BaseException:
            try: self.close()
            except BaseException: pass
            raise
    def audit(self, initial=False):
        result = {}
        for ordinal, (name, (fd, stamp, original)) in enumerate(self.rows.items(), 1):
            _component("code_file", ordinal)
            _guard(self.head, self.remote); self.clock.check()
            require((ROOT / name).resolve() == ROOT / name, "native_proof_path")
            _same(_stamp(os.fstat(fd)), stamp); _same(_stamp((ROOT / name).lstat()), stamp)
            os.lseek(fd, 0, os.SEEK_SET); raw = os.read(fd, 1024 ** 2 + 1)
            require(raw == _git(["show", self.head + ":" + name]), "native_proof_code")
            if not initial: require(raw == original, "native_proof_code")
            _same(_stamp(os.fstat(fd)), stamp); self.rows[name] = fd, stamp, raw; result[name] = hash_bytes(raw)
        self.clock.check(); return result
    def named(self):
        for ordinal, (name, (unused, stamp, unused_raw)) in enumerate(self.rows.items(), 1):
            _component("code_file", ordinal)
            require((ROOT / name).resolve() == ROOT / name, "native_proof_path")
            _same(_stamp((ROOT / name).lstat()), stamp)
    def close(self): _drain(self.fds)


def _protected(info, maximum=MAX_CONFIG):
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600
        and info.st_nlink == 1 and 0 < info.st_size <= maximum, "startup_config")
    return _stamp(info)


class _Inputs:
    """Exact two-role configuration reauthentication, never an evidence seal.

    Original identity, protection, size and expected bytes never change. Each
    separate read has its own full9 FD/name barrier through its original close.
    Timestamps between operations are observations, not source custody evidence.
    """
    ROLES = ("launch.spec.json", "job.plist")
    def __init__(self, directory):
        require(type(directory) is _Directory and directory.path == ROOT / PARENT / BOOTSTRAP, "startup_config")
        directory.check(); self.directory, self.rows = directory, {}
    def _membership(self, named=False):
        self.directory.named() if named else self.directory.check()
        require(set(os.listdir(self.directory.path if named else self.directory.fd)) == set(self.ROLES), "startup_membership")
    def read(self, name, *, expected=None, original_pin=None, named=False):
        require(type(name) is str and name in self.ROLES, "startup_config"); self._membership(named)
        existing = self.rows.get(name)
        require(existing is None or expected is original_pin is None, "startup_config")
        if existing is not None:
            pin, expected, digest = existing
            require(hash_bytes(expected) == digest, "startup_config")
        else:
            require(expected is None or type(expected) is bytes and 0 < len(expected) <= MAX_CONFIG, "startup_config")
            require(original_pin is None or type(original_pin) is tuple and len(original_pin) == 7
                and all(type(v) is int for v in original_pin), "startup_config")
            pin = original_pin
        path = self.directory.path / name
        info = path.lstat() if named else os.stat(name, dir_fd=self.directory.fd, follow_symlinks=False)
        before = _protected(info)
        require(pin is None or before[:7] == pin, "startup_config")
        pin = before[:7] if pin is None else pin
        fd = os.open(path if named else name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            **({} if named else {"dir_fd": self.directory.fd})); primary = None
        try:
            require(_protected(os.fstat(fd))[:7] == pin, "startup_config")
            _same(_stamp(os.fstat(fd)), before); _same(_stamp(path.lstat()), before)
            raw = os.read(fd, MAX_CONFIG + 1)
            require(len(raw) == pin[6] and (expected is None or raw == expected), "startup_config")
            _same(_stamp(os.fstat(fd)), before); _same(_stamp(path.lstat()), before)
        except BaseException as error: primary = error; raise
        finally: _close(fd, primary)
        require(_protected(path.lstat())[:7] == pin, "startup_config")
        _same(_stamp(path.lstat()), before)  # This reader's close remains inside its full9 barrier.
        self.directory.named() if named else self.directory.check()
        if existing is None: self.rows[name] = pin, raw, hash_bytes(raw)
        return raw
    def audit(self, named=False):
        require(set(self.rows) == set(self.ROLES), "startup_config")
        self._membership(named)
        for name in self.ROLES: self.read(name, named=named)
    def close(self):
        pass  # Each original read FD is closed exactly once by that operation.


def _config_write(directory, name, raw):
    require(name in ("launch.spec.json", "job.plist") and type(raw) is bytes and 0 < len(raw) <= MAX_CONFIG, "startup_config")
    directory.check(); fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory.fd); primary = None
    try:
        os.fchmod(fd, 0o600); before = _stamp(os.fstat(fd))
        require(before[4:7] == (0o600, 1, 0), "startup_config"); _same(_stamp(os.stat(name, dir_fd=directory.fd, follow_symlinks=False)), before)
        _write(fd, raw); os.fsync(fd); os.fsync(directory.fd); os.fsync(directory.parent)
        stamp = _protected(os.fstat(fd)); _same(_stamp(os.stat(name, dir_fd=directory.fd, follow_symlinks=False)), stamp)
        os.lseek(fd, 0, os.SEEK_SET); require(os.read(fd, len(raw) + 1) == raw, "startup_config"); _same(_stamp(os.fstat(fd)), stamp)
        pin = stamp[:7]
    except BaseException as error: primary = error; raise
    finally: _close(fd, primary)
    # Configuration timestamps across separate operations confer no evidence cap.
    require(_protected(os.stat(name, dir_fd=directory.fd, follow_symlinks=False))[:7] == pin, "startup_config")
    return pin


def _production_origin(clock):
    scope = getattr(clock, "production_scope", None); row = _PRODUCTION_SCOPES.get(scope)
    if type(row) is not tuple or len(row) != 8 or row[0] is not scope or row[2] is not clock: return None
    frame = row[1]; local = frame.f_locals
    if (frame.f_code is not _produce.__code__ or frame.f_globals is not globals() or local.get("scope") is not scope
            or local.get("clock") is not clock or tuple(local.get(name) for name in ("head", "remote", "digest")) != row[3:6]
            or local.get("observer") is not row[6]): return None
    return row


def _capture_creation_failure(volume, error):
    state = _CREATION_STATES.get(volume)
    if type(state) is not dict or state.get("volume") is not volume: return None
    caller = sys._getframe(1); local = caller.f_locals
    genuine = caller.f_globals is globals() and (
        caller.f_code is _DomainVolume.__init__.__code__ and local.get("self") is volume and local.get("error") is error
        or caller.f_code is _produce.__code__ and local.get("volume") is volume and local.get("failure") is error
            and _production_origin(state["clock"]) is state["operation"] and state["operation"] is not None)
    if not genuine: return None
    if state["failure"] is None:
        # Keep the exact first exception and traceback BEFORE cleanup/report I/O.
        state["failure"], state["trace"] = error, BaseException.__traceback__.__get__(error, BaseException)
        _CREATION_FAILURES[id(error)] = error, state, object()
    return state if state["failure"] is error else None


def _system_require(instance, condition, relation, observation):
    try: require(condition, "native_proof_protection")
    except BaseException as error:
        frame = sys._getframe(1); state = _CREATION_STATES.get(instance)
        if (relation in _SYSTEM_PREDICATES and frame.f_code is _DomainVolume._system.__code__
                and frame.f_globals is globals() and frame.f_locals.get("self") is instance
                and type(state) is dict and state["volume"] is instance
                and any(item is observation for item in state["system_observations"]) and frame.f_locals.get("observation") is observation):
            _SYSTEM_FAILURES[id(error)] = error, relation, (_SYSTEM_PREDICATES[relation],), instance, frame, observation, object()
        raise


def _compared_system(instance, actual, original, relation):
    require(original is _system_baseline(instance), "supervision_original")
    try: require(actual == original, "native_proof_protection")
    except BaseException as error:
        frame = sys._getframe(1); state = _CREATION_STATES.get(instance)
        expected_code = _DomainVolume.check.__code__ if relation == "system_original_metadata" else _DomainVolume.named.__code__
        if (relation in _SYSTEM_COMPARISONS and frame.f_code is expected_code and frame.f_globals is globals()
                and frame.f_locals.get("self") is instance and type(state) is dict and state["volume"] is instance
                and original is instance.system is state["system_baseline"]
                and type(actual) is tuple and type(original) is tuple and len(actual) == len(original) == 6):
            fields = tuple(name for name, a, b in zip(old._STAMP_NAMES[:6], actual, original) if a != b)
            observation = {"relation": relation, "actual": actual, "original": original}
            state["system_observations"].append(observation)
            _SYSTEM_FAILURES[id(error)] = error, relation, fields, instance, frame, observation, object()
        raise


def _system_failure(error):
    row = _SYSTEM_FAILURES.get(id(error))
    if type(row) is not tuple or len(row) != 7 or row[0] is not error: return None
    relation, instance, frame, observation = row[1], row[3], row[4], row[5]
    state = _CREATION_STATES.get(instance)
    if (type(instance) is not _DomainVolume or type(state) is not dict or state["volume"] is not instance
            or frame.f_globals is not globals() or frame.f_locals.get("self") is not instance
            or not any(item is observation for item in state["system_observations"])): return None
    if relation in _SYSTEM_PREDICATES:
        if frame.f_code is not _DomainVolume._system.__code__ or frame.f_locals.get("observation") is not observation: return None
    elif relation in _SYSTEM_COMPARISONS:
        code = _DomainVolume.check.__code__ if relation == "system_original_metadata" else _DomainVolume.named.__code__
        if frame.f_code is not code or observation["original"] is not state["system_baseline"]: return None
    else: return None
    return row


def _system_baseline(instance):
    row = _SYSTEM_BASELINES.get(instance); state = _CREATION_STATES.get(instance)
    require(type(row) is tuple and len(row) == 3 and row[0] is instance and type(state) is dict
        and state["volume"] is instance and instance.system is row[1] and state["system_baseline"] is row[1], "supervision_original")
    return row[1]


class _CreationCarrier:
    """Failure-only records on this invocation's original APFS root anchors."""
    def __init__(self, volume, state):
        self.state, self.volume = state, volume; state["carrier"] = self
        self.path, self.domain = volume.mount, volume.path
        self.fds, self.file_fds, self.originals, self.attempted, self.creators = [], [], {}, set(), {}
        self.closed = self.started = False
        self.pins = (_dir(os.fstat(volume.mount_fd), True), _dir(os.fstat(volume.directory.fd), True))
        for fd in (volume.mount_fd, volume.directory.fd): self.fds.append(os.dup(fd))
        self.check()
    def check(self):
        require(not self.closed and len(self.fds) == 2 and _CREATION_STATES.get(self.volume) is self.state
            and self.state["carrier"] is self, "supervision_original")
        for fd, path, pin in zip(self.fds, (self.path, self.domain), self.pins):
            require(path.resolve() == path and _dir(os.fstat(fd), True) == _dir(path.lstat(), True) == pin, "supervision_original")
        require(set(os.listdir(self.fds[0])) <= {".fseventsd", "main", "proof", *CREATION_ROLES}, "supervision_negative")
    def publish(self, name, raw):
        require(name in CREATION_ROLES and name not in self.attempted, "supervision_negative")
        self.attempted.add(name)
        limit = MAXIMUM_NATIVE_BYTES if name in CREATION_NATIVE_ROLES else MAXIMUM_PRIVATE_BYTES
        require(type(raw) is bytes and len(raw) <= limit, "supervision_negative"); self.check()
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fds[0]); self.file_fds.append(fd)
        os.fchmod(fd, 0o600); _issue_file_creator(self, name, fd, self.fds[0]); _write(fd, raw); os.fsync(fd)
        _freeze_new_file(self.creators[name], len(raw), raw)
        for parent in self.fds: os.fsync(parent)
        seal = _negative_file(os.fstat(fd), limit, empty=name in CREATION_NATIVE_ROLES)
        require(seal[6] == len(raw), "supervision_negative")
        _same(_stamp(os.stat(name, dir_fd=self.fds[0], follow_symlinks=False)), seal)
        os.lseek(fd, 0, os.SEEK_SET); require(os.read(fd, len(raw) + 1) == raw, "supervision_negative")
        _check_frozen(self.creators[name], os.fstat(fd)); _same(_stamp(os.fstat(fd)), seal)
        self.originals[name] = fd, seal, raw; self.check()
    def audit(self, *, named=False):
        require(set(self.originals) == self.attempted, "supervision_negative")
        if not named: self.check()
        else:
            for path, pin in zip((self.path, self.domain), self.pins):
                require(path.resolve() == path and _dir(path.lstat(), True) == pin, "supervision_original")
        for name, (fd, seal, raw) in self.originals.items():
            info = (self.path / name).lstat(); _check_frozen(self.creators.get(name), info); _same(_stamp(info), seal)
            if not named:
                _check_frozen(self.creators.get(name), os.fstat(fd)); _same(_stamp(os.fstat(fd)), seal); os.lseek(fd, 0, os.SEEK_SET)
                require(os.read(fd, len(raw) + 1) == raw, "supervision_negative")
                _check_frozen(self.creators.get(name), os.fstat(fd)); _same(_stamp(os.fstat(fd)), seal)
                _check_frozen(self.creators.get(name), (self.path / name).lstat())
    def preserve(self, error):
        require(not self.started, "supervision_negative"); self.started = True
        state = self.state; row = _CREATION_FAILURES.get(id(error))
        require(type(row) is tuple and row[0] is error and row[1] is state and state["failure"] is error, "supervision_original")
        begin = time.monotonic(); state["preserve_begin"] = begin
        def deadline():
            now = time.monotonic()
            require(type(now) in (int, float) and math.isfinite(now) and 0 <= begin <= now
                and now - begin <= NEGATIVE_SECONDS, "supervision_unknown")
        total = 0; complete = True; invocations = []
        for role, command in state["commands"].items():
            attempted = _native_invocation(self.volume, role, command)
            invocations.append({"role": role, "invocation_attempted": attempted})
            if not attempted: continue
            raw = command["stdout"]
            if type(raw) is not bytes: complete = False; continue
            total += len(raw); require(total <= len(CREATION_NATIVE_ROLES) * MAXIMUM_NATIVE_BYTES, "supervision_negative")
            self.publish("creation.native." + role + ".private.plist", raw); deadline()
            if not command["known_terminal"] or command["stderr"] not in (None, b""): complete = False
        system = {"schema": "si-native-creation-system-v1", "original_baseline": state["system_baseline"],
            "baseline_established": self.volume in _SYSTEM_BASELINES,
            "initialization": state.get("system_initialization"),
            "present_observations": state["system_observations"], "authority": authority()}
        self.publish(CREATION_SYSTEM_ROLE, canonical_json(system).encode()); deadline()
        sites, trace = [], state["trace"]
        methods = {method.__code__: name for name, method in (("creation", _DomainVolume.__init__), ("native_command", _DomainVolume.command),
            ("system", _DomainVolume._system), ("system_initialization", _DomainVolume._initialize_system),
            ("initialization_guard", _DomainVolume._initialization_guards), ("native_check", _DomainVolume.check),
            ("output_creation", _DomainVolume.outputs), ("named_check", _DomainVolume.named))}
        for unused in range(MAXIMUM_TRACE_FRAMES):
            if trace is None: break
            frame = trace.tb_frame
            if frame.f_globals is globals() and frame.f_code in methods and frame.f_locals.get("self") is self.volume:
                sites.append({"site": methods[frame.f_code], "code_bytes_sha256": hash_bytes(frame.f_code.co_code), "line": trace.tb_lineno})
            elif (frame.f_globals is globals() and frame.f_code is _produce.__code__ and frame.f_locals.get("volume") is self.volume
                    and frame.f_locals.get("failure") is error and state["operation"] is not None
                    and frame.f_locals.get("scope") is state["operation"][0]
                    and _production_origin(state["clock"]) is state["operation"]):
                sites.append({"site": "original_producer", "code_bytes_sha256": hash_bytes(frame.f_code.co_code), "line": trace.tb_lineno})
            trace = trace.tb_next
        operation = state["operation"]
        require(operation is None or _production_origin(state["clock"]) is operation, "supervision_original")
        binding = None if operation is None else {"runtime_head": operation[3], "actual_remote": operation[4], "spec_sha256": operation[5],
            "nonce": operation[6]["nonce"], "producer_pid": os.getpid(), "policy_sha256": POLICY_SHA256}
        failure = {"schema": "si-native-creation-failure-v1", "failure": failure_summary(error), "original_own_trace_sites": sites,
            "native_roles_present": list(state["commands"]), "operation_origin_bound": state["operation"] is not None,
            "native_invocations": invocations,
            "original_operation": binding,
            "authority": authority()}
        self.publish(CREATION_FAILURE_ROLE, canonical_json(failure).encode()); deadline()
        require(complete and trace is None and bool(sites) and set(state["commands"]) <= {"before", "create", "attach", "initial", "terminal"}, "supervision_unknown")
        controls = [{"name": name, "bytes": len(row[2]), "sha256": hash_bytes(row[2]), "original_stamp": list(row[1])}
            for name, row in sorted(self.originals.items())]
        manifest = {"schema": "si-native-creation-failure-manifest-v1", "status": "negative_creation_bytes_preserved_contexts_still_open",
            "original_operation": binding, "controls": controls, "authority": authority()}
        raw = canonical_json(manifest).encode(); state["manifest_raw"] = raw
        self.publish(CREATION_MANIFEST_ROLE, raw); self.audit(); deadline()
        state["preserved"] = self, error, raw, tuple(sorted(self.originals)), object()
    def close(self):
        first = None
        try: _drain(self.file_fds)
        except BaseException as error: first = error
        try: _drain(self.fds)
        except BaseException as error:
            if first is None: first = error
        self.closed = True
        if first is not None: raise first


def _creation_manifest(error):
    row = _CREATION_MANIFESTS.get(id(error))
    if type(row) is not tuple or len(row) != 8 or row[0] is not error: return None
    state, carrier, raw, sha, original_controls, operation, cleanup = row[1:]
    try:
        if (_CREATION_STATES.get(state["volume"]) is not state or state["failure"] is not error
                or state["carrier"] is not carrier or not carrier.closed or hash_bytes(raw) != sha
                or state.get("manifest_raw") is not raw or _production_origin(state["clock"]) is not operation
                or operation is None or tuple(sorted(carrier.originals.items())) != original_controls
                or state.get("cleanup_witness") is not cleanup or cleanup[0] is not state
                or _creation_cleanup_snapshot(cleanup[1]) != cleanup[2]): return None
        # Pure issued projection: every filesystem audit already finished in
        # the protected cleanup path. No new callback can silently null a
        # known witness after contexts have been released.
        return sha
    except BaseException: return None


def _creation_cleanup_snapshot(contexts):
    code, config, directory, volume, outputs, reporter, carrier = contexts
    require(code is not None and not code.fds and type(config) is _Inputs and set(config.rows) == set(config.ROLES)
        and directory is not None and directory.closed and type(volume) is _DomainVolume and not volume.fds
        and volume.directory.closed and (outputs is None or outputs.closed)
        and (reporter is None or not reporter.fds and not reporter.private_fds)
        and carrier.closed and not carrier.fds and not carrier.file_fds, "supervision_original")
    return tuple(id(obj) for obj in contexts), tuple(sorted(carrier.originals.items())), tuple(sorted(config.rows.items()))


def _native_invocation(volume, role, command):
    plan = _NATIVE_PLANS.get((volume, role))
    require(type(plan) is tuple and len(plan) == 6 and plan[0] is volume and plan[1] == role and plan[2] is command,
        "supervision_original")
    frame = plan[3]; local = frame.f_locals
    require(frame.f_code is _DomainVolume.command.__code__ and frame.f_globals is globals()
        and local.get("self") is volume and local.get("role") == role and local.get("command") is command
        and _CREATION_STATES[volume]["commands"].get(role) is command and tuple(command["arguments"]) == plan[4], "supervision_original")
    invocation = _NATIVE_INVOCATIONS.get((volume, role))
    if invocation is None:
        require(command["invocation_attempted"] is False and command["stdout"] is None and command["result"] is None
            and command["failure"] is None and "result" not in local, "supervision_original")
        return False
    require(type(invocation) is tuple and invocation[0] is plan and command["invocation_attempted"] is True, "supervision_original")
    result = command["result"]
    if type(result) is subprocess.CompletedProcess:
        require(local.get("result") is result and command["stdout"] is result.stdout and command["stderr"] is result.stderr
            and command["known_terminal"] is (type(result.returncode) is int), "supervision_original")
    else:
        error = command["failure"]
        require(result is None and error is not None and command["known_terminal"] is False, "supervision_original")
        if type(error) is subprocess.TimeoutExpired:
            require(command["stdout"] is error.output and command["stderr"] is error.stderr, "supervision_original")
    return True


class _DomainVolume:
    def __init__(self, clock):
        self.clock, self.directory, self.fds, self.origins, self.mount_fd = clock, None, [], {}, None
        state = {"volume": self, "clock": clock, "operation": _production_origin(clock), "carrier": None,
            "commands": {}, "origins": self.origins, "system_baseline": None, "system_observations": [],
            "failure": None, "trace": None, "preserved": None}
        _CREATION_STATES[self] = state
        try:
            _component("native_platform", 1); _platform(); clock.check()
            _component("native_parent", 2); self.directory = _Directory(DOMAIN, create=True)
            self.path = self.directory.path; self.image = self.path / "backing.sparseimage"; self.mount = self.path / "mount"
            _component("native_host", 3)
            host = _native_statfs(self.directory.fd)
            require(host["flags"] & native.MNT_LOCAL and not host["flags"] & native.MNT_IGNORE_OWNERSHIP
                and host["bsize"] * host["bavail"] >= VIRTUAL_BYTES + 1024 ** 3, "native_proof_capacity")
            self.host_device = os.fstat(self.directory.fd).st_dev
            _component("native_before_info", 4)
            self.command("before", "info"); self._association(self.origins["before"], absent=True)
            _component("native_create", 5)
            self.command("create", "create")
            require(set(os.listdir(self.directory.fd)) == {"backing.sparseimage"}, "native_proof_membership")
            _component("native_backing", 6)
            fd = os.open("backing.sparseimage", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.directory.fd)
            self.fds.append(fd); self.backing_fd = fd
            require(stat.S_ISREG(os.fstat(fd).st_mode) and os.fstat(fd).st_uid == os.getuid() and os.fstat(fd).st_nlink == 1,
                "native_proof_backing"); os.fchmod(fd, 0o600); self.backing_pin = native._backing(os.fstat(fd))
            _component("native_under_mount", 7)
            os.mkdir("mount", 0o700, dir_fd=self.directory.fd)
            self.under_fd = os.open("mount", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.directory.fd)
            self.fds.append(self.under_fd); self.under_pin = _dir(os.fstat(self.under_fd), True)
            require(not os.listdir(self.under_fd), "native_proof_membership")
            _component("native_attach", 8)
            self.command("attach", "attach"); self.attach_entities = native._entities(plistlib.loads(self.origins["attach"]))
            _component("native_initial_info", 9)
            self.command("initial", "info"); self.device = self._association(self.origins["initial"])
            _component("native_mount_open", 11)
            self.mount_fd = os.open("mount", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.directory.fd)
            self.fds.append(self.mount_fd); info = os.fstat(self.mount_fd)
            self.creation = native._fresh_root_identity(info); current = _native_statfs(self.mount_fd)
            self.mount_native = native._mount_identity(current); self.node = _device_node(self.device, info.st_dev)
            self._native(current)
            _component("native_capacity", 13)
            require(type(current["bsize"]) is int and current["bsize"] > 0
                and type(current["blocks"]) is int and 4 * 1024 ** 3 <= current["blocks"] * current["bsize"] <= VIRTUAL_BYTES
                and type(current["bavail"]) is int and current["bavail"] * current["bsize"] >= 4 * 1024 ** 3,
                "native_proof_capacity")
            require(info.st_dev != self.host_device and self.creation == native._fresh_root_identity(self.mount.lstat()), "native_proof_mount")
            _component("native_root_mode", 14)
            os.fchmod(self.mount_fd, 0o700); os.fsync(self.mount_fd); self.mount_pin = _dir(os.fstat(self.mount_fd), True)
            require(native._fresh_root_identity(os.fstat(self.mount_fd)) == self.creation, "native_proof_mount")
            _CreationCarrier(self, state)
            _component("native_system", 15)
            self.system = None
            self._initialize_system()
            _component("main_directory")
            os.mkdir("main", 0o700, dir_fd=self.mount_fd)
            self.main_fd = os.open("main", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.mount_fd); self.fds.append(self.main_fd)
            self.main_seal = _stamp(os.fstat(self.main_fd)); require(not os.listdir(self.main_fd), "native_proof_membership")
            _same(_stamp((self.mount / "main").lstat()), self.main_seal)
            _component("native_first_check", 16)
            self.check()
        except BaseException as error:
            _capture_creation_failure(self, error)
            # The caller owns cleanup only after negative bytes are preserved.
            # On a pre-anchor/unknown failure it retains this original state.
            raise
    def arguments(self, verb):
        if verb == "create": return [native.HDIUTIL, "create", "-type", "SPARSE", "-size", "8g", "-fs", "APFS", "-uid", str(os.getuid()), "-gid", str(os.getgid()), "-mode", "0700", "-volname", "SI_NATIVE_SUPERVISION_V2_V4", "-nospotlight", "-plist", str(self.image)]
        if verb == "attach": return [native.HDIUTIL, "attach", "-mountpoint", str(self.mount), "-mount", "required", "-nobrowse", "-owners", "on", "-noautoopen", "-noautoopenro", "-noautoopenrw", "-plist", str(self.image)]
        require(verb == "info", "native_proof_command"); return [native.HDIUTIL, "info", "-plist"]
    def command(self, role, verb):
        require(role not in self.origins and {"before": "info", "create": "create", "attach": "attach", "initial": "info", "terminal": "info"}.get(role) == verb,
            "native_proof_command")
        state = _CREATION_STATES[self]
        require(role not in state["commands"], "native_proof_command")
        command = {"arguments": tuple(self.arguments(verb)), "stdout": None, "stderr": None, "result": None,
            "failure": None, "known_terminal": False, "invocation_attempted": False}
        state["commands"][role] = command
        plan = self, role, command, sys._getframe(), command["arguments"], object()
        _NATIVE_PLANS[self, role] = plan
        remaining = self.clock.check(); require(remaining > 0, "native_proof_deadline")
        self._pre_command(role)
        command["invocation_attempted"] = True
        _NATIVE_INVOCATIONS[self, role] = plan, object()
        try: result = _native_command(list(command["arguments"]), min(COMMAND_SECONDS, remaining))
        except BaseException as error:
            command["failure"] = error; command["trace"] = BaseException.__traceback__.__get__(error, BaseException)
            if type(error) is subprocess.TimeoutExpired:
                command["stdout"], command["stderr"] = error.output, error.stderr
            raise
        command["result"] = result
        if type(result) is subprocess.CompletedProcess:
            command["stdout"], command["stderr"] = result.stdout, result.stderr
            command["known_terminal"] = type(result.returncode) is int
        self.clock.check()
        require(type(result.returncode) is int and result.returncode == 0 and type(result.stdout) is bytes
            and 0 < len(result.stdout) <= MAXIMUM_NATIVE_BYTES, "native_proof_command")
        parsed = plistlib.loads(result.stdout)
        require((type(parsed) is list and parsed == [str(self.image)]) if verb == "create" else type(parsed) is dict,
            "native_proof_plist")
        self.origins[role] = result.stdout
    def _pre_command(self, role):
        self.directory.check()
        if role in ("before", "create"):
            require(not os.listdir(self.directory.fd), "native_proof_membership"); return
        require(set(os.listdir(self.directory.fd)) == {"backing.sparseimage", "mount"}, "native_proof_membership")
        require(native._backing(os.fstat(self.backing_fd))
            == native._backing(os.stat("backing.sparseimage", dir_fd=self.directory.fd, follow_symlinks=False))
            == native._backing(self.image.lstat()) == self.backing_pin, "native_proof_backing")
        require(_dir(os.fstat(self.under_fd), True) == self.under_pin and self.mount.resolve() == self.mount,
            "native_proof_path")
        if role == "attach":
            require(_dir(os.stat("mount", dir_fd=self.directory.fd, follow_symlinks=False), True)
                == _dir(self.mount.lstat(), True) == self.under_pin and not os.listdir(self.under_fd), "native_proof_path")
        elif role == "initial":
            mounted = [r for r in self.attach_entities if r[3] is not None]
            require(len(mounted) == 1 and mounted[0][3] == str(self.mount)
                and self.mount.lstat().st_dev != self.host_device, "native_proof_mount")
            native._fresh_root_identity(self.mount.lstat())
        else:
            require(role == "terminal", "native_proof_command"); self.check()
    def _association(self, raw, absent=False):
        _component("native_association", 10)
        parsed = plistlib.loads(raw); images = parsed.get("images")
        require(type(images) is list and len(images) <= 256 and all(type(r) is dict for r in images), "native_proof_association")
        matching = [r for r in images if r.get("image-path") == str(self.image)]
        require(len(matching) == (0 if absent else 1), "native_proof_association")
        if absent: return None
        selected = matching[0]; require(not any(k in selected for k in ("shadow-path", "shadow-file")), "native_proof_association")
        entities = native._entities(selected); mounted = [r for r in entities if r[3] is not None]
        attached = [r for r in self.attach_entities if r[3] is not None]
        require(len(mounted) == len(attached) == 1 and mounted[0][0] == attached[0][0]
            and mounted[0][3] == attached[0][3] == str(self.mount)
            and {r[0] for r in self.attach_entities} <= {r[0] for r in entities}, "native_proof_association")
        native._mounted_descriptor(mounted[0]); native._mounted_descriptor(attached[0])
        device = mounted[0][0]; own_devices = {r[0] for r in entities} | {r[0] for r in self.attach_entities}
        device_counts = {name: 0 for name in own_devices}; mounts = 0
        for image in images:
            rows = image.get("system-entities", [])
            require(type(rows) is list and len(rows) <= 64 and all(type(r) is dict for r in rows), "native_proof_association")
            for name in own_devices: device_counts[name] += sum(r.get("dev-entry") == name for r in rows)
            mounts += sum(r.get("mount-point") == str(self.mount) for r in rows)
        require(mounts == 1 and all(count == 1 for count in device_counts.values()), "native_proof_association"); return device
    def _native(self, current):
        _component("native_contract", 12)
        require(current["fstype"] == "apfs" and current["owner"] == os.getuid()
            and current["flags"] & native.MNT_LOCAL and current["flags"] & native.MNT_DONTBROWSE
            and not current["flags"] & (native.MNT_RDONLY | native.MNT_IGNORE_OWNERSHIP)
            and current["mounted_on"] == str(self.mount) and current["mounted_from"] == self.device
            and native._mount_identity(current) == self.mount_native, "native_proof_mount")
    def _initialization_guards(self):
        self.clock.check(); self.directory.check()
        require(set(os.listdir(self.directory.fd)) == {"backing.sparseimage", "mount"}, "native_proof_membership")
        require(native._backing(os.fstat(self.backing_fd)) == native._backing(self.image.lstat()) == self.backing_pin, "native_proof_backing")
        require(_dir(os.fstat(self.under_fd), True) == self.under_pin and self.mount.resolve() == self.mount
            and _dir(os.fstat(self.mount_fd), True) == _dir(self.mount.lstat(), True) == self.mount_pin, "native_proof_mount")
        self._native(_native_statfs(self.mount_fd))
        require(_device_node(self.device, os.fstat(self.mount_fd).st_dev) == self.node, "native_proof_mount")
        require(set(os.listdir(self.mount_fd)) <= {".fseventsd"}, "native_proof_membership")
    def _initialize_system(self):
        state = _CREATION_STATES[self]
        require(self not in _SYSTEM_INITIALIZATIONS and self not in _SYSTEM_BASELINES, "system_initialization_refused")
        init = {"samples": [], "first_identity": None, "candidate": None, "quiet_begin": None, "sealed": False}
        _SYSTEM_INITIALIZATIONS[self] = self, init, object(); state["system_initialization"] = init
        begin = last = _initialization_now()
        require(type(begin) in (int, float) and math.isfinite(begin) and begin >= 0, "native_proof_clock")
        for number in range(SYSTEM_INITIAL_SAMPLES):
            now = _initialization_now()
            require(type(now) in (int, float) and math.isfinite(now) and begin <= last <= now
                and now - begin <= SYSTEM_INITIAL_SECONDS, "system_initialization_refused"); last = now
            self._initialization_guards()
            present = ".fseventsd" in os.listdir(self.mount_fd)
            sample = {"number": number + 1, "at": now, "present": present}; init["samples"].append(sample)
            if not present:
                require(init["first_identity"] is None, "system_initial_identity_changed")
            else:
                actual = self._system(); sample["metadata"] = actual
            end = _initialization_now(); self.clock.check()
            require(type(end) in (int, float) and math.isfinite(end) and now <= end
                and end - begin <= SYSTEM_INITIAL_SECONDS, "system_initialization_refused")
            last = end; sample["observed_at"] = end
            if present:
                if init["first_identity"] is None: init["first_identity"] = actual[:2]
                require(actual[:2] == init["first_identity"], "system_initial_identity_changed")
                if init["candidate"] is None: init["candidate"], init["quiet_begin"] = actual, end
                else:
                    require(actual[:5] == init["candidate"][:5], "system_initial_identity_changed")
                    if actual != init["candidate"]: init["candidate"], init["quiet_begin"] = actual, end
                if end - init["quiet_begin"] >= SYSTEM_INITIAL_QUIET:
                    self.system = actual; state["system_baseline"] = actual
                    _SYSTEM_BASELINES[self] = self, actual, object(); init["sealed"] = True; return
            if number + 1 >= SYSTEM_INITIAL_SAMPLES or SYSTEM_INITIAL_SECONDS - (end - begin) < SYSTEM_INITIAL_INTERVAL: break
            _initialization_sleep(SYSTEM_INITIAL_INTERVAL)
        raise SupervisionRefusal("REFUSED: system_initialization_refused")
    def _system(self):
        _component("native_system", 15)
        info = os.stat(".fseventsd", dir_fd=self.mount_fd, follow_symlinks=False)
        state = _CREATION_STATES.get(self)
        observation = {"stat": _stamp(info), "file_mode": info.st_mode}
        if state is not None: state["system_observations"].append(observation)
        _system_require(self, stat.S_ISDIR(info.st_mode), "system_directory_type", observation)
        _system_require(self, stat.S_IMODE(info.st_mode) == 0o700, "system_directory_mode", observation)
        _system_require(self, info.st_uid == 0, "system_directory_uid", observation)
        observation["mount_gid"] = os.fstat(self.mount_fd).st_gid
        _system_require(self, info.st_gid == observation["mount_gid"], "system_directory_gid", observation)
        observation["mount_dev"] = os.fstat(self.mount_fd).st_dev
        _system_require(self, info.st_dev == observation["mount_dev"], "system_directory_dev", observation)
        return _stamp(info)[:6]
    def check(self):
        _component("native_parent", 2)
        self.clock.check(); self.directory.check()
        require(set(os.listdir(self.directory.fd)) == {"backing.sparseimage", "mount"}, "native_proof_membership")
        _component("native_backing", 6)
        require(native._backing(os.fstat(self.backing_fd)) == native._backing(self.image.lstat()) == self.backing_pin,
            "native_proof_backing")
        _component("native_under_mount", 7)
        require(_dir(os.fstat(self.under_fd), True) == self.under_pin and self.mount.resolve() == self.mount
            and _dir(os.fstat(self.mount_fd), True) == _dir(self.mount.lstat(), True) == self.mount_pin, "native_proof_mount")
        self._native(_native_statfs(self.mount_fd))
        _component("native_mount_open", 11)
        require(_device_node(self.device, os.fstat(self.mount_fd).st_dev) == self.node, "native_proof_mount")
        _component("native_system", 15)
        if self in _CREATION_STATES: _system_baseline(self)
        expected = ({".fseventsd"} if self.system is not None else set()) | {"main"} | ({"proof"} if hasattr(self, "proof_pin") else set())
        require(set(os.listdir(self.mount_fd)) == expected, "native_proof_membership")
        if self.system is not None: _compared_system(self, self._system(), self.system, "system_original_metadata")
        _compared_stamp(_stamp(os.fstat(self.main_fd)), self.main_seal, "main_fd_original_seal")
        _compared_stamp(_stamp((self.mount / "main").lstat()), self.main_seal, "main_named_original_seal")
        require(not os.listdir(self.main_fd), "native_proof_membership")
        if hasattr(self, "proof_pin"): require(_dir((self.mount / "proof").lstat(), True) == self.proof_pin, "native_proof_path")
    def outputs(self):
        self.check(); os.mkdir("proof", 0o700, dir_fd=self.mount_fd)
        fd = os.open("proof", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.mount_fd)
        self.fds.append(fd); self.proof_pin = _dir(os.fstat(fd), True); self.check()
        return _Files(fd, self.mount_fd, self.mount / "proof", self.check, ROLES)
    def terminal(self):
        self.command("terminal", "info"); require(self._association(self.origins["terminal"]) == self.device, "native_proof_association"); self.check()
    def inventory(self):
        self.check()
        return {"domain_original_identity": self.directory.nodes[-1][2], "main_original_seal": self.main_seal, "proof_original_identity": self.proof_pin, "backing_original_identity": self.backing_pin, "mount_original_identity": self.mount_pin,
            "native_original_identity": self.mount_native, "device_node_original_identity": self.node,
            "fresh_root_creation_identity": self.creation, "system_original_metadata": self.system,
            "attach_original_entities": self.attach_entities,
            "original_command_output_sha256s": {name: hash_bytes(raw) for name, raw in sorted(self.origins.items())}}
    def named(self):
        self.directory.named()
        if self in _CREATION_STATES: _system_baseline(self)
        require(set(os.listdir(self.path)) == {"backing.sparseimage", "mount"}
            and native._backing(self.image.lstat()) == self.backing_pin and _dir(self.mount.lstat(), True) == self.mount_pin,
            "native_proof_path")
        require(set(os.listdir(self.mount)) == ({".fseventsd"} if self.system is not None else set()) | {"proof", "main"}
            and _dir((self.mount / "proof").lstat(), True) == self.proof_pin, "native_proof_membership")
        if self.system is not None: _compared_system(self, _stamp((self.mount / ".fseventsd").lstat())[:6], self.system, "system_named_original_metadata")
        _compared_stamp(_stamp((self.mount / "main").lstat()), self.main_seal, "main_named_original_seal")
        require(not os.listdir(self.mount / "main"), "native_proof_membership")
    def close(self):
        first = None
        try: _drain(self.fds)
        except BaseException as error: first = error
        try: self.directory.close()
        except BaseException as error:
            if first is None: first = error
        if first is not None: raise first



def _payload(head, remote, manifest, observer):
    return {"schema": "si-native-supervision-bootstrap-v1", "runtime_head": head, "actual_remote": remote,
        "policy_sha256": POLICY_SHA256, "code_manifest": manifest, "observer": startup._observer_config(observer),
        "authority": authority()}


def _wrapper_body():
    body = startup._import_body().replace(startup.MODULE, MODULE).replace("run-readonly", "run-proof")
    body = body.replace("si-startup-PTY-observation-v7", "si-native-supervision-observation-v1")
    body = body.replace(hash_payload(startup.authority()), hash_payload(authority()))
    start = body.index("  F={"); end = body.index("\n  R={", start)
    body = body[:start] + "  F={'stage':'startup_import','component':'operation','contract_code':'startup_import_failed','upstream_contract_code':None,'errno_name':n,'mismatching_fields':[],'comparison_relation':None,'creation_manifest_sha256':None}" + body[end:]
    return body.replace("'failure':F,'authority_sha256'", "'failure':F,'marker':None,'authority_sha256'")


def _wrapper():
    encoded = base64.b64encode(zlib.compress(_wrapper_body().encode(), 9)).decode("ascii")
    return "import os\ntry:\n import base64,zlib\n exec(zlib.decompress(base64.b64decode(" + repr(encoded) + ")))\nexcept BaseException:\n os._exit(2)\n"


def build_launchd_plist(head, remote, digest, observer):
    require(worker._hash(head) and worker._hash(remote) and re.fullmatch(r"[0-9a-f]{64}", digest), "supervision_arguments")
    observer = startup._observer_config(observer)
    return {"Label": LABEL, "ProgramArguments": [worker.PYTHON, "-B", "-c", _wrapper(), "run-proof", "--head", head,
        "--remote", remote, "--spec-sha256", digest, "--observer", canonical_json(observer)],
        "WorkingDirectory": str(ROOT), "EnvironmentVariables": worker._environment(), "RunAtLoad": False, "KeepAlive": False,
        "StandardOutPath": "/dev/null", "StandardErrorPath": observer["slave_path"]}


def prepare_bootstrap(head, remote, observer):
    registered(); observer = startup._observer_config(observer); clock = _Clock()
    code = directory = inputs = None; error = None
    try:
        _phase("current_code"); _guard(head, remote); code = _Code7(head, remote, clock)
        _phase("bootstrap"); directory = _Directory(BOOTSTRAP, create=True)
        raw = canonical_json(_payload(head, remote, code.manifest, observer)).encode(); digest = hash_bytes(raw)
        job = plistlib.dumps(build_launchd_plist(head, remote, digest, observer), sort_keys=True)
        pins = {"launch.spec.json": _config_write(directory, "launch.spec.json", raw), "job.plist": _config_write(directory, "job.plist", job)}
        inputs = _Inputs(directory)
        inputs.read("launch.spec.json", expected=raw, original_pin=pins["launch.spec.json"])
        inputs.read("job.plist", expected=job, original_pin=pins["job.plist"])
        code.audit(); _guard(head, remote); inputs.audit(); clock.check()
    except BaseException as failure: error = failure; failure_summary(failure); raise
    finally:
        first = error
        for obj in (inputs, directory, code):
            if obj is not None:
                try: obj.close()
                except BaseException as failure:
                    if first is None: first = failure; failure_summary(failure)
        if error is None and first is not None: raise first
    code.named(); inputs.audit(named=True); clock.check()
    _PREPARED[(head, remote, digest, observer["nonce"])] = tuple((name, *inputs.rows[name]) for name in inputs.ROLES)
    return {"status": "prepared_not_loaded", "spec_sha256": digest, "authority": authority()}


def _read_config(head, remote, digest, observer, manifest):
    directory = _Directory(BOOTSTRAP, create=False); inputs = _Inputs(directory)
    try:
        raw = inputs.read("launch.spec.json")
        require(hash_bytes(raw) == digest and raw == canonical_json(_payload(head, remote, manifest, observer)).encode(), "supervision_code")
        require(inputs.read("job.plist") == plistlib.dumps(build_launchd_plist(head, remote, digest, observer), sort_keys=True), "supervision_code")
        inputs.audit(); return directory, inputs
    except BaseException:
        try: inputs.close()
        finally: directory.close()
        raise


def _audit_local(outputs):
    """Final original control audit with no Git/native callback side effects."""
    require(outputs.path.resolve() == outputs.path and _dir(os.fstat(outputs.fd), True) == _dir(outputs.path.lstat(), True)
        and set(os.listdir(outputs.fd)) == set(outputs.originals), "native_proof_membership")
    for name, (fd, pin, stamp, raw) in outputs.originals.items():
        require(type(raw) is bytes and stamp is not None and _stamp(os.fstat(fd))[:6] == pin, "native_proof_stamp")
        _same(_stamp(os.fstat(fd)), stamp); _same(_stamp(os.stat(name, dir_fd=outputs.fd, follow_symlinks=False)), stamp)
        _check_frozen(outputs.creators.get(name), os.fstat(fd))
        _check_frozen(outputs.creators.get(name), os.stat(name, dir_fd=outputs.fd, follow_symlinks=False))
        os.lseek(fd, 0, os.SEEK_SET); require(os.read(fd, len(raw) + 1) == raw, "native_proof_stamp")
        _check_frozen(outputs.creators.get(name), os.fstat(fd)); _same(_stamp(os.fstat(fd)), stamp)
        _check_frozen(outputs.creators.get(name), os.stat(name, dir_fd=outputs.fd, follow_symlinks=False))


class _NegativeReporter:
    def __init__(self, outputs, volume):
        self.path, self.mount, self.domain = outputs.path, volume.mount, volume.path
        self.pins = (_dir(os.fstat(outputs.fd), True), _dir(os.fstat(volume.mount_fd), True), _dir(os.fstat(volume.directory.fd), True))
        self.fds = []; self.private_fds = []; self.originals = {}; self.attempted = set(); self.used = False; self.closed = False; self.creators = {}
        try:
            for fd in (outputs.fd, volume.mount_fd, volume.directory.fd): self.fds.append(os.dup(fd))
            self.check()
        except BaseException:
            try: self.close()
            except BaseException: pass
            raise
    def check(self):
        require(len(self.fds) == 3, "supervision_original")
        for fd, path, pin in zip(self.fds, (self.path, self.mount, self.domain), self.pins):
            require(path.resolve() == path and _dir(os.fstat(fd), True) == _dir(path.lstat(), True) == pin, "supervision_original")
    def refuse(self, error):
        require(not self.used, "supervision_negative"); self.used = True
        raw = canonical_json({"schema": "si-native-supervision-refusal-v2", "failure": failure_summary(error), "authority": authority()}).encode()
        self.preserve("run.refused.json", raw)
    def preserve(self, name, raw):
        """Negative-only publication through surviving ORIGINAL duplicate anchors."""
        require(name in (*PRIVATE_ROLES, "run.refused.json") and name not in self.attempted, "supervision_negative")
        self.attempted.add(name)
        limit = MAXIMUM_CONTROL_BYTES if name in ("run.refused.json", "child.negative.closed.json") else MAXIMUM_PRIVATE_BYTES
        require(type(raw) is bytes and len(raw) <= limit, "supervision_negative")
        self.check()
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fds[0])
        self.private_fds.append(fd)
        os.fchmod(fd, 0o600); _issue_file_creator(self, name, fd, self.fds[0]); _write(fd, raw); os.fsync(fd)
        _freeze_new_file(self.creators[name], len(raw), raw)
        for parent in self.fds: os.fsync(parent)
        seal = _negative_file(os.fstat(fd), limit, empty=name in ("child.remaining.pipe.private.bin", "child.partial.stdout.private.bin"))
        require(seal[6] == len(raw), "supervision_negative")
        _same(_stamp(os.stat(name, dir_fd=self.fds[0], follow_symlinks=False)), seal)
        os.lseek(fd, 0, os.SEEK_SET); require(os.read(fd, len(raw) + 1) == raw, "supervision_negative")
        _check_frozen(self.creators[name], os.fstat(fd)); _same(_stamp(os.fstat(fd)), seal); self.check()
        self.originals[name] = fd, seal, raw
    def audit_preserved(self, *, named=False):
        require(set(self.originals) == self.attempted, "supervision_negative")
        if not named: self.check()
        else:
            for path, pin in zip((self.path, self.mount, self.domain), self.pins):
                require(path.resolve() == path and _dir(path.lstat(), True) == pin, "supervision_original")
        for name, (fd, seal, raw) in self.originals.items():
            info = (self.path / name).lstat(); _check_frozen(self.creators.get(name), info); _same(_stamp(info), seal)
            if not named:
                _check_frozen(self.creators.get(name), os.fstat(fd)); _same(_stamp(os.fstat(fd)), seal); os.lseek(fd, 0, os.SEEK_SET)
                require(os.read(fd, len(raw) + 1) == raw, "supervision_negative")
                _check_frozen(self.creators.get(name), os.fstat(fd)); _same(_stamp(os.fstat(fd)), seal)
                _check_frozen(self.creators.get(name), (self.path / name).lstat())
    def close(self):
        first = None
        try: _drain(self.private_fds)
        except BaseException as error: first = error
        try: _drain(self.fds)
        except BaseException as error:
            if first is None: first = error
        if first is not None: raise first
        self.closed = True


def _negative_file(info, maximum, *, empty=False):
    """An observed empty negative binary is evidence, never a config default."""
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600
        and info.st_nlink == 1 and (0 if empty else 1) <= info.st_size <= maximum, "supervision_negative")
    return _stamp(info)


class ProducerObservation:
    __slots__ = ("_anchor",)
    def __init__(self): raise SupervisionRefusal("REFUSED: supervision_factory")
    def public_summary(self):
        row = _PRODUCERS.get(id(self)); require(type(row) is tuple and row[0] is self and self._anchor is row, "supervision_factory")
        require(row[2][0] is row[3] and row[2][1] == 0, "supervision_wait")
        return json.loads(row[1])


class ClosedNativeSupervision:
    __slots__ = ("_anchor",)
    def __init__(self): raise SupervisionRefusal("REFUSED: supervision_factory")
    def public_summary(self):
        row = _CLOSED.get(id(self)); require(type(row) is tuple and row[0] is self and self._anchor is row and row[2] in _ROOT_RECEIPTS, "supervision_factory")
        receipt = _ROOT_RECEIPTS[row[2]]
        require(type(receipt) is tuple and len(receipt) == 6 and receipt[0] is row[3] and receipt[1] == row[1]
            and _kernel_origin(receipt[2][0]) is receipt[2] and _terminal(receipt[2][0]) and receipt[2][0]["exit"] == 0
            and _root_context_snapshot(*receipt[3]) == receipt[4], "supervision_factory")
        return json.loads(row[1])


def _capture_collection_failure(error, process, origin, outputs, log_fd, reporter):
    """Strong issuance precedes every diagnostic write or further consumed read."""
    state = {"failure": error, "trace": BaseException.__traceback__.__get__(error, BaseException),
        "process": process, "origin": origin, "outputs": outputs, "log_fd": log_fd, "reporter": reporter,
        "frame": None, "buffers": {}, "tail": b"", "blocks": (), "partial_log": None,
        "started": False, "capture_error": None, "preservation_error": None, "wait": None, "eof": False}
    _CAPTURED.append(state)
    try:
        require(id(error) not in _PRESERVATIONS, "supervision_negative")
        _PRESERVATIONS[id(error)] = error, state, object()
        state["negative_begin"] = time.monotonic()
        require(process is not None and type(origin) is tuple and origin[0] is process
            and worker._CHILDREN.get(process) is origin and type(outputs) is _Files
            and type(reporter) is _NegativeReporter, "supervision_original")
        trace = state["trace"]; frames = []
        for unused in range(MAXIMUM_TRACE_FRAMES):
            if trace is None: break
            if trace.tb_frame.f_code is _COLLECT_CODE and trace.tb_frame.f_globals is worker.__dict__: frames.append(trace.tb_frame)
            trace = trace.tb_next
        require(trace is None and len(frames) == 1, "supervision_original")
        frame = frames[0]; state["frame"] = frame; local = frame.f_locals
        require(local.get("process") is process and local.get("ns") is outputs and local.get("log_fd") == log_fd,
            "supervision_original")
        # Absent variables stay absent; an empty default would destroy evidence
        # about where the original collector failed.
        for name in ("output", "pending", "line", "block"):
            if name in local: state["buffers"][name] = local[name]
        state["collector_seal_present"] = "seal" in local
        if "seal" in local: state["collector_seal"] = local["seal"]
        require({"output", "pending"} <= set(state["buffers"])
            and all(type(raw) is bytes for raw in state["buffers"].values()), "supervision_original")
        state["stdout"] = process.stdout; state["pipe_fd"] = process.stdout.fileno()
        state["wait_method"] = process.wait
    except BaseException as secondary:
        state["capture_error"] = secondary
        state["capture_trace"] = BaseException.__traceback__.__get__(secondary, BaseException)
    return state


def _preservation_state(state):
    if type(state) is not dict: return False
    error = state.get("failure"); row = _PRESERVATIONS.get(id(error))
    if type(row) is not tuple or row[0] is not error or row[1] is not state: return False
    frame = state.get("frame")
    if (state.get("capture_error") is not None or frame is None or frame.f_code is not _COLLECT_CODE
            or frame.f_globals is not worker.__dict__): return False
    local = frame.f_locals
    return (local.get("process") is state["process"] and local.get("ns") is state["outputs"]
        and local.get("log_fd") == state["log_fd"] and worker._CHILDREN.get(state["process"]) is state["origin"]
        and state["process"].stdout is state["stdout"] and state["stdout"].fileno() == state["pipe_fd"]
        and all(name in local and local[name] is raw and type(raw) is bytes for name, raw in state["buffers"].items())
        and set(state["buffers"]) == {name for name in ("output", "pending", "line", "block") if name in local}
        and state.get("collector_seal_present") is ("seal" in local)
        and ("seal" not in local or state.get("collector_seal") is local["seal"]))


def _collector_return(process):
    row = _COLLECT_RETURNS.get(process)
    if type(row) is not tuple or len(row) != 9 or row[0] is not process: return None
    frame = row[8]; local = frame.f_locals
    if (frame.f_code is not _produce.__code__ or frame.f_globals is not globals()
            or local.get("process") is not process or local.get("outputs") is not row[1]
            or local.get("log_fd") != row[2] or local.get("origin") is not row[3]
            or local.get("status") != row[4] or local.get("stdout_sha") != row[5] or local.get("seal") is not row[6]
            or worker._CHILDREN.get(process) is not row[3]): return None
    wait = worker._WAITS.get(process)
    require(type(wait) is tuple and wait[0] is row[3] and type(wait[1]) is int and wait[1] == row[4] == 0, "supervision_wait")
    return row


def _audit_returned_stdout(receipt, *, named=False):
    process, outputs, fd, origin, status, digest, seal = receipt[:7]
    require(_collector_return(process) is receipt and type(seal) is tuple and len(seal) == 9, "supervision_original")
    cap = outputs.creators.get("stdout.jsonl")
    info = (outputs.path / "stdout.jsonl").lstat(); _check_frozen(cap, info); _same(_stamp(info), seal)
    if named: return None
    _check_frozen(cap, os.fstat(fd)); _same(_stamp(os.fstat(fd)), seal)
    os.lseek(fd, 0, os.SEEK_SET); raw = os.read(fd, worker.MAXIMUM_LOG_BYTES + 1)
    _creator(cap)["returned_negative_raw"] = raw
    require(len(raw) == seal[6] and hash_bytes(raw) == digest, "supervision_original")
    _check_frozen(cap, os.fstat(fd)); _same(_stamp(os.fstat(fd)), seal); return raw


def _negative_stdout_stamp(state):
    outputs, fd, process = state["outputs"], state["log_fd"], state["process"]
    row = outputs.originals.get("stdout.jsonl"); cap = outputs.creators.get("stdout.jsonl"); creator = _creator(cap)
    require(row is not None and row[0] == fd, "supervision_original")
    old = state.get("collector_seal") if state["collector_seal_present"] else None
    returned = _collector_return(process)
    if returned is not None:
        require(old is None or old == returned[6], "supervision_original"); old = returned[6]
    if row[2] is not None:
        require(old is None or old == row[2], "supervision_original"); old = row[2]
    if old is not None:
        require(type(old) is tuple and len(old) == 9, "supervision_original")
        _check_frozen(cap, os.fstat(fd)); _same(_stamp(os.fstat(fd)), old); return old
    require(_preservation_state(state) and "seal" not in state["frame"].f_locals and returned is None
        and row[2] is None and state["eof"] and state["wait"] is not None, "immutable_freeze_refused")
    if not creator["attempted"]:
        _STDOUT_FREEZES[cap] = cap, "negative_partial", state, sys._getframe(1), object()
        info = _negative_file(os.fstat(fd), worker.MAXIMUM_LOG_BYTES, empty=True)
        _freeze_new_file(cap, info[6])
    return _check_frozen(cap, os.fstat(fd))


def _preserve_collection_failure(state):
    """An exact terminal negative can release contexts; uncertainty keeps them."""
    if type(state) is not dict: return None
    try:
        require(not state.get("started"), "supervision_negative"); state["started"] = True
        require(_preservation_state(state), "supervision_original")
        process, outputs, reporter = state["process"], state["outputs"], state["reporter"]
        require(sum(map(len, state["buffers"].values())) <= MAXIMUM_PRIVATE_BYTES, "supervision_negative")
        raw = canonical_json({"schema": "si-native-collection-buffers-v2", "present": sorted(state["buffers"]),
            "private_bytes_hex": {name: value.hex() for name, value in state["buffers"].items()},
            "collector_seal_present": state["collector_seal_present"], "original_collector_seal": state.get("collector_seal"), "authority": authority()}).encode()
        state["buffers_raw"] = raw
        reporter.preserve("child.failure.buffers.private.json", raw)
        begin = last = state["negative_begin"]
        def remaining():
            nonlocal last
            now = time.monotonic()
            require(type(now) in (int, float) and math.isfinite(now) and 0 <= begin <= last <= now
                and now - begin < NEGATIVE_SECONDS, "supervision_unknown")
            last = now; return NEGATIVE_SECONDS - (now - begin)
        selector = worker.selectors.DefaultSelector(); state["selector"] = selector
        os.set_blocking(state["pipe_fd"], False); selector.register(state["stdout"], worker.selectors.EVENT_READ)
        while not state["eof"]:
            require(_preservation_state(state), "supervision_original")
            for key, unused in selector.select(min(0.1, remaining())):
                require(key.fd == state["pipe_fd"], "supervision_original")
                block = os.read(key.fd, 1024)
                # Keep consumed bytes BEFORE bounds, encoding or publication.
                state["blocks"] = (*state["blocks"], block); state["tail"] += block
                require(type(block) is bytes and len(state["tail"]) <= MAXIMUM_PRIVATE_BYTES, "supervision_negative")
                if not block: state["eof"] = True; break
            remaining()
        selector.close(); state["selector_closed"] = True
        reporter.preserve("child.remaining.pipe.private.bin", state["tail"])
        wait = worker._WAITS.get(process)
        if not (type(wait) is tuple and len(wait) == 3 and wait[0] is state["origin"] and type(wait[1]) is int):
            require(worker._CHILDREN.get(process) is state["origin"], "supervision_original")
            status = state["wait_method"](timeout=remaining())
            require(type(status) is int and worker._CHILDREN.get(process) is state["origin"], "supervision_wait")
            wait = state["origin"], status, object()
            _NEGATIVE_WAITS[process] = wait
        state["wait"] = wait
        row = outputs.originals.get("stdout.jsonl")
        require(row is not None and row[0] == state["log_fd"], "supervision_original")
        reporter.check()
        before = _negative_stdout_stamp(state)
        require(before[:6] == row[1], "supervision_original")
        _same(_stamp(os.stat("stdout.jsonl", dir_fd=reporter.fds[0], follow_symlinks=False)), before)
        os.fsync(state["log_fd"]); os.lseek(state["log_fd"], 0, os.SEEK_SET)
        partial = os.read(state["log_fd"], worker.MAXIMUM_LOG_BYTES + 1); state["partial_log"] = partial
        require(type(partial) is bytes and len(partial) == before[6], "supervision_original")
        _same(_stamp(os.fstat(state["log_fd"])), before)
        state["partial_stamp"] = before
        reporter.preserve("child.partial.stdout.private.bin", partial)
        require(_preservation_state(state) and state["eof"] and state["selector_closed"], "supervision_original")
        evidence = [{"name": name, "bytes": len(row[2]), "sha256": hash_bytes(row[2]), "original_stamp": list(row[1])}
            for name, row in sorted(reporter.originals.items())]
        raw = canonical_json({"schema": "si-native-collection-negative-v2", "status": "all_original_collection_bytes_preserved_negative_only",
            "actual_child_exit": wait[1], "collector_returned": False, "pipe_EOF": True, "present_buffers": sorted(state["buffers"]),
            "context_closure": "original_contexts_still_retained_until_cleanup",
            "controls": evidence, "original_failure": failure_summary(state["failure"]), "authority": authority()}).encode()
        state["closure_raw"] = raw; reporter.preserve("child.negative.closed.json", raw)
        remaining(); reporter.audit_preserved()
        token = object(); _NEGATIVE_CLOSURES[token] = state, wait, reporter, tuple(sorted(reporter.originals)), object()
        return token
    except BaseException as secondary:
        state["preservation_error"] = secondary
        state["preservation_trace"] = BaseException.__traceback__.__get__(secondary, BaseException)
        return None


def _negative_closed(token, state):
    row = _NEGATIVE_CLOSURES.get(token)
    if (type(row) is not tuple or len(row) != 5 or row[0] is not state or not _preservation_state(state)
            or row[1] is not state.get("wait") or row[2] is not state["reporter"]
            or row[3] != tuple(sorted(state["reporter"].originals)) or not state.get("eof")): return False
    wait = row[1]; process = state["process"]
    require((worker._WAITS.get(process) is wait or _NEGATIVE_WAITS.get(process) is wait)
        and wait[0] is state["origin"] and type(wait[1]) is int, "supervision_wait")
    state["reporter"].audit_preserved(); _negative_snapshot_audit(state); return True


def _negative_snapshot_audit(state, *, named=False):
    """Compare the original partial-log seal; never seal/rebaseline it positive."""
    partial, seal = state["partial_log"], state["partial_stamp"]
    _check_frozen(state["outputs"].creators.get("stdout.jsonl"), (state["reporter"].path / "stdout.jsonl").lstat())
    _same(_stamp((state["reporter"].path / "stdout.jsonl").lstat()), seal)
    if not named:
        fd = state["log_fd"]; _check_frozen(state["outputs"].creators.get("stdout.jsonl"), os.fstat(fd))
        _same(_stamp(os.fstat(fd)), seal); os.lseek(fd, 0, os.SEEK_SET)
        require(os.read(fd, len(partial) + 1) == partial, "supervision_negative")
        _check_frozen(state["outputs"].creators.get("stdout.jsonl"), os.fstat(fd)); _same(_stamp(os.fstat(fd)), seal)


def _preserve_returned_stdout(receipt, reporter, state):
    process, outputs, fd = receipt[:3]; cap = outputs.creators.get("stdout.jsonl")
    require(_collector_return(process) is receipt and _stdout_freeze_origin(cap), "supervision_original")
    final = _STDOUT_FREEZES[cap]
    require(final[1] == "collector_final", "supervision_original")
    frame = final[2]; local = frame.f_locals
    buffers = {name: local[name] for name in ("output", "pending", "line", "block") if name in local}
    state["returned_receipt"], state["returned_frame"], state["returned_buffers"] = receipt, frame, buffers
    require({"output", "pending"} <= set(buffers) and all(type(value) is bytes for value in buffers.values())
        and local.get("seal") is receipt[6] and not buffers["pending"] and local.get("stages") == [], "supervision_original")
    raw = _audit_returned_stdout(receipt); state["returned_raw"] = raw
    require(raw == buffers["output"], "supervision_original")
    payload = canonical_json({"schema": "si-native-returned-stdout-negative-v1", "collector_returned": True,
        "actual_child_exit": receipt[4], "original_stdout_sha256": receipt[5], "original_stdout_seal": list(receipt[6]),
        "present_buffers": sorted(buffers), "private_bytes_hex": {name: value.hex() for name, value in buffers.items()},
        "authority": authority()}).encode()
    state["returned_payload_raw"] = payload
    reporter.preserve("child.returned.stdout.private.json", payload)


def _hold(state):
    _HELD.append(state)
    while True:
        if state.get("master") is not None and state.get("private_failure") is None and "private_error" not in state:
            try: state["raw"], unused = _read_private(state["master"], state["raw"])
            except BaseException as error:
                state["private_failure"] = _private_failure(error, state["master"])
                state["private_error"] = error
                state["private_trace"] = BaseException.__traceback__.__get__(error, BaseException)
        time.sleep(0.1 if state.get("master") is not None else 30)


def run_registered(head, remote, digest, observer):
    global _USED
    registered(); require(not _USED, "native_proof_already_used"); _USED = True
    with _source_denied(): return _produce(head, remote, digest, startup._observer_config(observer))


def _produce(head, remote, digest, observer):
    clock = _Clock(); code = directory = config = volume = outputs = reporter = process = None
    scope = object(); _PRODUCTION_SCOPES[scope] = scope, sys._getframe(), clock, head, remote, digest, observer, object()
    clock.production_scope = scope
    error = None; held = False; entered = returned = False; origin = wait = marker = log_fd = None
    failure_state = negative_token = creation_state = return_receipt = None
    def retain_cleanup(failure):
        nonlocal failure_state
        if failure_state is None:
            failure_state = {"failure": failure, "trace": BaseException.__traceback__.__get__(failure, BaseException),
                "process": process, "origin": origin, "code": code, "directory": directory, "config": config,
                "volume": volume, "outputs": outputs, "reporter": reporter, "returned_receipt": return_receipt}
        return failure_state
    def retain_report_failure(first, secondary):
        nonlocal held
        state = retain_cleanup(first)
        state["reporter_error"], state["reporter_trace"] = secondary, BaseException.__traceback__.__get__(secondary, BaseException)
        held = True
        try: _hold(state)
        except BaseException: raise first
        raise first  # A returning observer cannot authorize releasing partial originals.
    try:
        _phase("current_code"); _guard(head, remote); code = _Code7(head, remote, clock)
        _phase("bootstrap"); directory, config = _read_config(head, remote, digest, observer, code.manifest)
        _phase("native_creation"); volume = _new_domain(clock)
        _phase("output_creation"); outputs = volume.outputs(); reporter = _NegativeReporter(outputs, volume)
        for role in ("before", "create", "attach", "initial"): outputs.write("native." + role + ".plist", volume.origins[role])
        started = {"schema": "si-native-supervision-started-v1", "runtime_head": head, "actual_remote": remote,
            "policy_sha256": POLICY_SHA256, "spec_sha256": digest, "nonce": observer["nonce"], "producer_pid": os.getpid(), "authority": authority()}
        outputs.write("run.started.json", canonical_json(started).encode())
        _guard(head, remote); code.audit(); config.audit(); volume.check(); outputs.audit()
        log_fd = outputs.create("stdout.jsonl"); os.fsync(log_fd); os.fsync(outputs.fd); os.fsync(outputs.parent)
        _phase("child_launch"); began = worker._now(); process = _launch_worker(head, remote)
        require(type(process.pid) is int and process.pid > 0 and process.stdout is not None, "supervision_wait")
        origin = (process, digest, code.manifest, object()); worker._CHILDREN[process] = origin
        _phase("child_observation"); entered = True
        status, stdout_sha, seal = _COLLECT(process, outputs, log_fd, began)
        return_receipt = process, outputs, log_fd, origin, status, stdout_sha, seal, object(), sys._getframe()
        _COLLECT_RETURNS[process] = return_receipt; returned = True
        require(0 <= worker._now() - began <= worker.MAXIMUM_SECONDS, "supervision_wait")
        wait = worker._WAITS.get(process)
        require(type(wait) is tuple and len(wait) == 3 and wait[0] is origin and worker._CHILDREN.get(process) is origin and wait[1] == status == 0, "supervision_wait")
        os.lseek(log_fd, 0, os.SEEK_SET); raw = os.read(log_fd, worker.MAXIMUM_LOG_BYTES + 1)
        require(hash_bytes(raw) == stdout_sha, "supervision_original"); outputs.seal("stdout.jsonl", log_fd, seal, raw)
        report = {**started, "schema": "si-native-supervision-child-v1", "child_pid": process.pid, "actual_child_exit": 0,
            "stdout_sha256": stdout_sha, "kernel_exit_attested": False, "status": "provisional_until_Root_kernel0"}
        outputs.write("child.exit.provisional.json", canonical_json(report).encode())
        _phase("terminal_code"); code.audit(); _guard(head, remote)
        _phase("terminal_native"); volume.terminal(); outputs.write("native.terminal.plist", volume.origins["terminal"])
        _phase("inventory_publication")
        inventory = {"schema": "si-native-supervision-inventory-v1", "controls": outputs.inventory(), "native": volume.inventory(),
            "code_manifest": code.manifest, "runtime_head": head, "policy_sha256": POLICY_SHA256, "nonce": observer["nonce"], "authority": authority()}
        inventory_raw = canonical_json(inventory).encode(); outputs.write(INVENTORY_ROLE, inventory_raw)
        inventory_stamp = outputs.originals[INVENTORY_ROLE][2]
        marker = {**report, "schema": "si-native-supervision-marker-v1", "inventory_sha256": hash_bytes(inventory_raw),
            "inventory_bytes": len(inventory_raw), "inventory_original_stamp": list(inventory_stamp), "code_manifest_sha256": hash_payload(code.manifest),
            "durable_Main_receipt": False}
        marker_raw = canonical_json(marker).encode(); outputs.write(MARKER_ROLE, marker_raw)
        marker_pin = tuple(outputs.originals[MARKER_ROLE][2]); marker_sha = hash_bytes(marker_raw)
        # Finish all Git/native callbacks before the final original-only audit.
        code.audit(); _guard(head, remote); volume.check(); config.audit(); code.close(); code.named()
        _phase("original_audit"); _audit_local(outputs); clock.check()
    except BaseException as failure:
        error = failure
        creation = _CREATION_FAILURES.get(id(failure))
        if type(creation) is tuple and creation[0] is failure and creation[1]["operation"] is _PRODUCTION_SCOPES[scope]:
            creation_state = creation[1]; volume = creation_state["volume"]
        elif volume is not None: creation_state = _capture_creation_failure(volume, failure)
        if entered and not returned:
            failure_state = _capture_collection_failure(failure, process, origin, outputs, log_fd, reporter)
        elif creation_state is not None: failure_state = creation_state
        else:
            failure_state = {"process": process, "origin": origin, "failure": failure,
                "trace": BaseException.__traceback__.__get__(failure, BaseException)}
        failure_state.update({"code": code, "directory": directory, "config": config, "volume": volume,
            "outputs": outputs, "reporter": reporter})
        if creation_state is not None: failure_state["creation_state"] = creation_state
        failure_summary(failure)
        if reporter is not None:
            try: reporter.refuse(failure)
            except BaseException as secondary:
                retain_report_failure(failure, secondary)
        if returned:
            try: _preserve_returned_stdout(return_receipt, reporter, failure_state)
            except BaseException as secondary:
                held = True; failure_state["return_preservation_error"] = secondary
                failure_state["return_preservation_trace"] = BaseException.__traceback__.__get__(secondary, BaseException)
                try: _hold(failure_state)
                except BaseException: raise failure
        if creation_state is not None:
            try:
                carrier = creation_state["carrier"]
                require(type(carrier) is _CreationCarrier, "supervision_unknown")
                carrier.preserve(failure)
            except BaseException as secondary:
                held = True; creation_state["preservation_error"] = secondary
                creation_state["preservation_trace"] = BaseException.__traceback__.__get__(secondary, BaseException)
                try: _hold(failure_state)
                except BaseException: raise failure
        actual_wait = worker._WAITS.get(process) if process is not None else None
        unknown = process is not None and not (type(actual_wait) is tuple and len(actual_wait) == 3 and actual_wait[0] is origin and type(actual_wait[1]) is int)
        preserved = False
        if entered and not returned:
            negative_token = _preserve_collection_failure(failure_state)
            if negative_token is not None:
                try: preserved = _negative_closed(negative_token, failure_state)
                except BaseException as secondary:
                    failure_state["closure_error"] = secondary
                    failure_state["closure_trace"] = BaseException.__traceback__.__get__(secondary, BaseException)
        if (unknown or entered and not returned) and not preserved:
            held = True
            try: _hold(failure_state)
            except BaseException: raise failure
        # Known-negative paths continue through original reporter cleanup.
    finally:
        if not held:
            first = error; _phase("cleanup")
            actions = []
            if process is not None and process.stdout is not None: actions.append(process.stdout.close)
            actions += [obj.close for obj in (outputs, volume, code, config, directory) if obj is not None]
            for close in actions:
                try: close()
                except BaseException as failure:
                    retain_cleanup(failure)
                    if first is None: first = failure; error = failure; failure_summary(failure)
                    if negative_token is not None or creation_state is not None or return_receipt is not None:
                        held = True; failure_state["cleanup_error"] = failure
                        failure_state["cleanup_trace"] = BaseException.__traceback__.__get__(failure, BaseException)
                        try: _hold(failure_state)
                        except BaseException: raise error
            if first is not None and reporter is not None and not reporter.used:
                try: reporter.refuse(first)
                except BaseException as secondary: retain_report_failure(first, secondary)
            if error is None and first is not None: error = first
    if held: raise SupervisionRefusal("REFUSED: supervision_unknown")
    terminal_error = error
    if terminal_error is None:
        try:
            _phase("named_audit"); volume.named(); code.named(); config.audit(named=True); outputs.named(); clock.check()
            require(set(os.listdir(outputs.path)) == POSITIVE_ROLES, "supervision_negative")
        except BaseException as failure:
            terminal_error = failure; failure_summary(failure)
            if reporter is not None:
                try: reporter.refuse(failure)
                except BaseException as secondary: retain_report_failure(failure, secondary)
    if reporter is not None:
        try:
            if negative_token is not None:
                reporter.audit_preserved(); _negative_snapshot_audit(failure_state, named=True)
            if error is not None and return_receipt is not None:
                reporter.audit_preserved(); _audit_returned_stdout(return_receipt, named=True)
            reporter.close()
            if negative_token is not None:
                reporter.audit_preserved(named=True); _negative_snapshot_audit(failure_state, named=True)
            if error is not None and return_receipt is not None:
                reporter.audit_preserved(named=True); _audit_returned_stdout(return_receipt, named=True)
        except BaseException as failure:
            if negative_token is not None or creation_state is not None or return_receipt is not None:
                retain_cleanup(failure)
                if error is None: error = failure
                failure_state["cleanup_error"] = failure
                failure_state["cleanup_trace"] = BaseException.__traceback__.__get__(failure, BaseException)
                try: _hold(failure_state)
                except BaseException: raise error
            if terminal_error is None: terminal_error = failure; failure_summary(failure)
    native_state = _CREATION_STATES.get(volume)
    carrier = native_state["carrier"] if native_state is not None else None
    if carrier is not None:
        try:
            carrier.audit(); carrier.close(); carrier.audit(named=True)
            if creation_state is not None:
                require(creation_state["preserved"] is not None and creation_state["operation"] is _PRODUCTION_SCOPES[scope], "supervision_original")
                raw = carrier.originals[CREATION_MANIFEST_ROLE][2]
                contexts = code, config, directory, volume, outputs, reporter, carrier
                cleanup = creation_state, contexts, _creation_cleanup_snapshot(contexts), object()
                creation_state["cleanup_witness"] = cleanup
                _CREATION_MANIFESTS[id(error)] = (error, creation_state, carrier, raw, hash_bytes(raw),
                    tuple(sorted(carrier.originals.items())), creation_state["operation"], cleanup)
        except BaseException as secondary:
            state = failure_state if failure_state is not None else native_state
            state["cleanup_error"] = secondary; state["cleanup_trace"] = BaseException.__traceback__.__get__(secondary, BaseException)
            try: _hold(state)
            except BaseException:
                if terminal_error is not None: raise terminal_error
                raise secondary
    if terminal_error is not None: raise terminal_error
    # Last original named seals follow reporter cleanup; no reopen/rebaseline.
    volume.named(); code.named(); config.audit(named=True); outputs.named(); clock.check()
    require(set(os.listdir(outputs.path)) == POSITIVE_ROLES, "supervision_negative")
    public = {"status": "producer_checks_complete_provisional", "marker": {"sha256": marker_sha, "stamp": list(marker_pin)},
        "actual_child_exit": 0, "kernel_exit_attested": False, "durable_Main_receipt": False, "authority": authority()}
    value = object.__new__(ProducerObservation); row = (value, canonical_json(public), wait, origin, object())
    value._anchor = row; _PRODUCERS[id(value)] = row; return value


def _observer_fd(): return 2


class _Observer:
    def __init__(self, config, digest):
        self.config = startup._observer_config(config); require(re.fullmatch(r"[0-9a-f]{64}", digest), "supervision_arguments")
        self.digest, self.fd, self.attempted = digest, _observer_fd(), False; startup._tty_check(self.fd, self.config)
    def emit(self, result=None, error=None):
        require(not self.attempted and ((result is None) != (error is None)), "supervision_original"); self.attempted = True
        startup._tty_check(self.fd, self.config)
        if result is not None:
            require(type(result) is ProducerObservation, "supervision_factory"); marker = result.public_summary()["marker"]; detail = None
        else: marker = None; detail = _checked_failure(failure_summary(error))
        payload = {"schema": "si-native-supervision-observation-v1", "nonce": self.config["nonce"], "spec_sha256": self.digest,
            "pid": os.getpid(), "status": "producer_complete_provisional" if marker is not None else "refused",
            "marker": marker, "failure": detail, "authority_sha256": hash_payload(authority())}
        raw = canonical_json(payload).encode() + b"\n"; require(0 < len(raw) <= MAX_WIRE and raw.count(b"\n") == 1, "supervision_original")
        os.set_blocking(self.fd, False); count = os.write(self.fd, raw)
        require(type(count) is int and count == len(raw), "supervision_original")


def _checked_failure(detail):
    require(type(detail) is dict and set(detail) == {"stage", "component", "contract_code", "upstream_contract_code", "errno_name", "mismatching_fields", "comparison_relation", "creation_manifest_sha256"}
        and type(detail["stage"]) is str and detail["stage"] in _STAGES
        and type(detail["component"]) is str and detail["component"] in _COMPONENTS
        and (detail["contract_code"] is None or type(detail["contract_code"]) is str and detail["contract_code"] in _CODES)
        and (detail["upstream_contract_code"] is None or type(detail["upstream_contract_code"]) is str and detail["upstream_contract_code"] in old._CODES | worker._CODES | native._CODES)
        and (detail["errno_name"] is None or type(detail["errno_name"]) is str and detail["errno_name"] in set(_ERRNOS.values()) | set(native._ERRNOS.values()) | set(worker._ERRNOS.values()))
        and (detail["comparison_relation"] is None or type(detail["comparison_relation"]) is str and detail["comparison_relation"] in _COMPARISON_ROLES)
        and (detail["creation_manifest_sha256"] is None or type(detail["creation_manifest_sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", detail["creation_manifest_sha256"]))
        and type(detail["mismatching_fields"]) is list and len(detail["mismatching_fields"]) <= 9
        and all(type(value) is str and value in old._STAMP_NAMES for value in detail["mismatching_fields"]), "supervision_original")
    return json.loads(canonical_json(detail))


def _validated_observation(raw, observer, digest, pid):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_WIRE and raw.count(b"\n") == 1, "supervision_original")
    value = json.loads(raw)
    require(type(value) is dict and set(value) == {"schema", "nonce", "spec_sha256", "pid", "status", "marker", "failure", "authority_sha256"}
        and raw == canonical_json(value).encode() + b"\n" and value["schema"] == "si-native-supervision-observation-v1"
        and value["nonce"] == observer["nonce"] and value["spec_sha256"] == digest
        and type(value["pid"]) is int and value["pid"] == pid and 0 < pid < 2 ** 31
        and value["authority_sha256"] == hash_payload(authority()), "supervision_original")
    if value["status"] == "refused":
        require(value["marker"] is None, "supervision_original"); _checked_failure(value["failure"]); return value
    require(value["status"] == "producer_complete_provisional" and value["failure"] is None, "supervision_original")
    marker = value["marker"]
    require(type(marker) is dict and set(marker) == {"sha256", "stamp"} and type(marker["sha256"]) is str
        and re.fullmatch(r"[0-9a-f]{64}", marker["sha256"]) and type(marker["stamp"]) is list and len(marker["stamp"]) == 9
        and all(type(v) is int and 0 <= v <= 2 ** 64 for v in marker["stamp"])
        and marker["stamp"][2] == os.getuid() and tuple(marker["stamp"][4:6]) == (0o600, 1)
        and 0 < marker["stamp"][6] <= MAXIMUM_CONTROL_BYTES, "supervision_marker")
    return value


def _filtered_observation(raw, observer, digest, pid):
    value = _validated_observation(raw, observer, digest, pid)
    require(value["status"] == "producer_complete_provisional" and value["failure"] is None, "supervision_negative")
    return value["marker"]


def advisory_summary(error):
    row = _ADVISORIES.get(id(error))
    return json.loads(row[1]) if type(row) is tuple and row[0] is error else None


class _LoadTransaction:
    def __init__(self, head, remote, digest, observer):
        key = (head, remote, digest, observer["nonce"]); require(key in _PREPARED, "supervision_original")
        self.directory = None; self.fds, self.rows, self.nodes = [], [], []
        try:
            self.directory = _Directory(BOOTSTRAP, create=False)
            self.nodes = [(path, fd, _stamp(os.fstat(fd))) for path, fd, unused in self.directory.nodes]
            for name, pin, raw, digest_value in _PREPARED[key]:
                require(hash_bytes(raw) == digest_value, "supervision_original")
                before = _protected(os.stat(name, dir_fd=self.directory.fd, follow_symlinks=False)); require(before[:7] == pin, "supervision_original")
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.directory.fd); self.fds.append(fd)
                self.rows.append((name, fd, before, raw))
            self.audit()
        except BaseException:
            try: self.close()
            except BaseException: pass
            raise
    def audit(self):
        self.directory.check(); require(set(os.listdir(self.directory.fd)) == set(_Inputs.ROLES), "supervision_original")
        for path, fd, stamp in self.nodes: _same(_stamp(os.fstat(fd)), stamp); _same(_stamp(path.lstat()), stamp)
        for name, fd, stamp, raw in self.rows:
            _same(_stamp(os.fstat(fd)), stamp); _same(_stamp(os.stat(name, dir_fd=self.directory.fd, follow_symlinks=False)), stamp)
            os.lseek(fd, 0, os.SEEK_SET); require(os.read(fd, len(raw) + 1) == raw, "supervision_original"); _same(_stamp(os.fstat(fd)), stamp)
    def named(self):
        self.directory.named()
        for path, unused, stamp in self.nodes: _same(_stamp(path.lstat()), stamp)
        for name, unused, stamp, unused_raw in self.rows: _same(_stamp((self.directory.path / name).lstat()), stamp)
    def close(self):
        first = None
        try: _drain(self.fds)
        except BaseException as error: first = error
        if self.directory is not None:
            try: self.directory.close()
            except BaseException as error:
                if first is None: first = error
            try: self.named()
            except BaseException as error:
                if first is None: first = error
        if first is not None: raise first


def _association(raw, image, mount, attach_entities, absent=False):
    _component("native_association", 10)
    parsed = plistlib.loads(raw); images = parsed.get("images")
    require(type(images) is list and len(images) <= 256 and all(type(r) is dict for r in images), "native_proof_association")
    matching = [r for r in images if r.get("image-path") == str(image)]
    require(len(matching) == (0 if absent else 1), "native_proof_association")
    if absent: return None
    selected = matching[0]; require(not any(k in selected for k in ("shadow-path", "shadow-file")), "native_proof_association")
    entities = native._entities(selected); mounted = [r for r in entities if r[3] is not None]
    attached = [r for r in attach_entities if r[3] is not None]
    require(len(mounted) == len(attached) == 1 and mounted[0][0] == attached[0][0]
        and mounted[0][3] == attached[0][3] == str(mount)
        and {r[0] for r in attach_entities} <= {r[0] for r in entities}, "native_proof_association")
    native._mounted_descriptor(mounted[0]); native._mounted_descriptor(attached[0])
    device = mounted[0][0]; own_devices = {r[0] for r in entities} | {r[0] for r in attach_entities}
    device_counts = {name: 0 for name in own_devices}; mounts = 0
    for image in images:
        rows = image.get("system-entities", [])
        require(type(rows) is list and len(rows) <= 64 and all(type(r) is dict for r in rows), "native_proof_association")
        for name in own_devices: device_counts[name] += sum(r.get("dev-entry") == name for r in rows)
        mounts += sum(r.get("mount-point") == str(mount) for r in rows)
    require(mounts == 1 and all(count == 1 for count in device_counts.values()), "native_proof_association"); return device


def _tuples(value):
    if type(value) is list: return tuple(_tuples(item) for item in value)
    return value


class _RootReceipt:
    __slots__ = ()
    def __init__(self): raise SupervisionRefusal("REFUSED: supervision_factory")


_ROOT_RECEIPTS = {}


class _OriginalRead:
    """Independent reads compare reported ORIGINAL seals, never a new baseline."""
    def __init__(self, head, remote, digest, observer, producer_pid, marker):
        self.head, self.remote, self.digest, self.observer, self.producer_pid = head, remote, digest, observer, producer_pid
        self.directory = None; self.fds, self.files, self.anchors = [], [], []
        try:
            self.directory = _Directory(DOMAIN, create=False); self.path = self.directory.path; self.mount = self.path / "mount"; self.image = self.path / "backing.sparseimage"
            self.mount_fd = os.open("mount", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.directory.fd); self.fds.append(self.mount_fd)
            self.proof_path = self.mount / "proof"
            self.proof_fd = os.open("proof", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.mount_fd); self.fds.append(self.proof_fd)
            marker_raw = self.read(MARKER_ROLE, marker["stamp"], marker["sha256"], MAXIMUM_CONTROL_BYTES)
            self.marker = json.loads(marker_raw); m = self.marker
            expected_keys = {"schema", "runtime_head", "actual_remote", "policy_sha256", "spec_sha256", "nonce", "producer_pid", "authority",
                "child_pid", "actual_child_exit", "stdout_sha256", "kernel_exit_attested", "status", "inventory_sha256", "inventory_bytes",
                "inventory_original_stamp", "code_manifest_sha256", "durable_Main_receipt"}
            require(type(m) is dict and set(m) == expected_keys and marker_raw == canonical_json(m).encode()
                and m["schema"] == "si-native-supervision-marker-v1" and m["runtime_head"] == head and m["actual_remote"] == remote
                and m["policy_sha256"] == POLICY_SHA256 and m["spec_sha256"] == digest and m["nonce"] == observer["nonce"]
                and type(m["producer_pid"]) is int and m["producer_pid"] == producer_pid
                and type(m["child_pid"]) is int and 0 < m["child_pid"] < 2 ** 31 and m["actual_child_exit"] == 0
                and type(m["actual_child_exit"]) is int and m["kernel_exit_attested"] is False and m["durable_Main_receipt"] is False
                and m["status"] == "provisional_until_Root_kernel0" and m["authority"] == authority(), "supervision_marker")
            raw = self.read(INVENTORY_ROLE, m["inventory_original_stamp"], m["inventory_sha256"], MAXIMUM_NATIVE_BYTES)
            require(len(raw) == m["inventory_bytes"], "supervision_original"); self.inventory = json.loads(raw); inv = self.inventory
            require(type(inv) is dict and set(inv) == {"schema", "controls", "native", "code_manifest", "runtime_head", "policy_sha256", "nonce", "authority"}
                and raw == canonical_json(inv).encode() and inv["schema"] == "si-native-supervision-inventory-v1"
                and inv["runtime_head"] == head and inv["policy_sha256"] == POLICY_SHA256 and inv["nonce"] == observer["nonce"]
                and inv["authority"] == authority() and type(inv["code_manifest"]) is dict and set(inv["code_manifest"]) == set(CODE_FILES)
                and all(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) for value in inv["code_manifest"].values())
                and hash_payload(inv["code_manifest"]) == m["code_manifest_sha256"], "supervision_original")
            controls = inv["controls"]
            require(type(controls) is list and len(controls) == len(POSITIVE_ROLES) - 2, "supervision_original")
            names = set(); self.raw_controls = {}
            for row in controls:
                require(type(row) is dict and set(row) == {"name", "sha256", "bytes", "original_stamp"}
                    and row["name"] in POSITIVE_ROLES - {MARKER_ROLE, INVENTORY_ROLE} and row["name"] not in names, "supervision_original")
                names.add(row["name"]); limit = MAXIMUM_NATIVE_BYTES if row["name"] in RAW_ROLES else MAXIMUM_CONTROL_BYTES
                body = self.read(row["name"], row["original_stamp"], row["sha256"], limit)
                require(len(body) == row["bytes"], "supervision_original"); self.raw_controls[row["name"]] = body
            require(names == POSITIVE_ROLES - {MARKER_ROLE, INVENTORY_ROLE}, "supervision_original")
            expected_stdout = b"".join(canonical_json(worker._worker_line(stage, m["child_pid"], producer_pid)).encode() + b"\n" for stage in ("entered", "completed"))
            require(self.raw_controls["stdout.jsonl"] == expected_stdout and hash_bytes(expected_stdout) == m["stdout_sha256"], "supervision_wait")
            expected_started = {"schema": "si-native-supervision-started-v1", "runtime_head": head, "actual_remote": remote,
                "policy_sha256": POLICY_SHA256, "spec_sha256": digest, "nonce": observer["nonce"], "producer_pid": producer_pid, "authority": authority()}
            expected_child = {**expected_started, "schema": "si-native-supervision-child-v1", "child_pid": m["child_pid"], "actual_child_exit": 0,
                "stdout_sha256": m["stdout_sha256"], "kernel_exit_attested": False, "status": "provisional_until_Root_kernel0"}
            require(self.raw_controls["run.started.json"] == canonical_json(expected_started).encode()
                and self.raw_controls["child.exit.provisional.json"] == canonical_json(expected_child).encode(), "supervision_wait")
            child = json.loads(self.raw_controls["child.exit.provisional.json"])
            require(type(child["actual_child_exit"]) is int and child["actual_child_exit"] == 0, "supervision_wait")
            self.native = inv["native"]; n = self.native
            native_keys = {"domain_original_identity", "main_original_seal", "proof_original_identity", "backing_original_identity", "mount_original_identity",
                "native_original_identity", "device_node_original_identity", "fresh_root_creation_identity", "system_original_metadata", "attach_original_entities", "original_command_output_sha256s"}
            require(type(n) is dict and set(n) == native_keys, "supervision_original")
            require(type(n["system_original_metadata"]) is list and len(n["system_original_metadata"]) == 6
                and all(type(value) is int and value >= 0 for value in n["system_original_metadata"]), "supervision_original")
            require(n["original_command_output_sha256s"] == {role: hash_bytes(self.raw_controls["native." + role + ".plist"]) for role in ("before", "create", "attach", "initial", "terminal")}, "supervision_original")
            require(_dir(os.fstat(self.directory.fd), True) == _tuples(n["domain_original_identity"])
                and _dir(os.fstat(self.mount_fd), True) == _tuples(n["mount_original_identity"])
                and _dir(os.fstat(self.proof_fd), True) == _tuples(n["proof_original_identity"]), "supervision_original")
            self.backing_fd = os.open("backing.sparseimage", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.directory.fd); self.fds.append(self.backing_fd)
            self.main_fd = os.open("main", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.mount_fd); self.fds.append(self.main_fd)
            self.attach_entities = native._entities(plistlib.loads(self.raw_controls["native.attach.plist"]))
            require(_tuples(n["attach_original_entities"]) == _tuples(self.attach_entities), "supervision_original")
            self.device = _association(self.raw_controls["native.terminal.plist"], self.image, self.mount, self.attach_entities)
            self.anchors = [(self.path, self.directory.fd, _tuples(n["domain_original_identity"])),
                (self.mount, self.mount_fd, _tuples(n["mount_original_identity"])), (self.proof_path, self.proof_fd, _tuples(n["proof_original_identity"]))]
            self.audit()
        except BaseException:
            try: self.close()
            except BaseException: pass
            raise
    def read(self, name, seal, digest, maximum):
        require(name in POSITIVE_ROLES and type(seal) is list and len(seal) == 9 and all(type(v) is int and v >= 0 for v in seal)
            and type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest), "supervision_original")
        seal = tuple(seal); info = os.stat(name, dir_fd=self.proof_fd, follow_symlinks=False)
        _require_file_immutable(info); _same(_protected(info, maximum), seal)
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.proof_fd); self.fds.append(fd)
        _require_file_immutable(os.fstat(fd)); _same(_stamp(os.fstat(fd)), seal); raw = os.read(fd, maximum + 1)
        require(len(raw) == seal[6] and hash_bytes(raw) == digest, "supervision_original")
        _require_file_immutable(os.fstat(fd)); _require_file_immutable(os.stat(name, dir_fd=self.proof_fd, follow_symlinks=False))
        _same(_stamp(os.fstat(fd)), seal); _same(_stamp(os.stat(name, dir_fd=self.proof_fd, follow_symlinks=False)), seal)
        self.files.append((name, fd, seal, raw)); return raw
    def native_audit(self):
        self._native_originals(self.mount_fd, self.backing_fd, self.main_fd, self.directory.fd)
    def _native_originals(self, mount_fd, backing_fd, main_fd, domain_fd):
        n = self.native; current = _native_statfs(mount_fd)
        require(native._mount_identity(current) == _tuples(n["native_original_identity"])
            and current["fstype"] == "apfs" and current["owner"] == os.getuid()
            and current["flags"] & native.MNT_LOCAL and current["flags"] & native.MNT_DONTBROWSE
            and not current["flags"] & (native.MNT_RDONLY | native.MNT_IGNORE_OWNERSHIP)
            and current["mounted_on"] == str(self.mount) and current["mounted_from"] == self.device, "supervision_original")
        require(_device_node(self.device, os.fstat(mount_fd).st_dev) == _tuples(n["device_node_original_identity"]), "supervision_original")
        require(type(current["bsize"]) is int and current["bsize"] > 0 and type(current["blocks"]) is int
            and 4 * 1024 ** 3 <= current["blocks"] * current["bsize"] <= VIRTUAL_BYTES
            and type(current["bavail"]) is int and current["bavail"] * current["bsize"] >= 4 * 1024 ** 3, "supervision_original")
        require(native._backing(os.fstat(backing_fd)) == native._backing(self.image.lstat()) == _tuples(n["backing_original_identity"]), "supervision_original")
        require(_dir(os.fstat(main_fd), True) == _dir((self.mount / "main").lstat(), True), "supervision_original")
        require(native._fresh_root_identity(os.fstat(mount_fd)) == _tuples(n["fresh_root_creation_identity"])
            and os.fstat(mount_fd).st_dev != os.fstat(domain_fd).st_dev, "supervision_original")
        expected_names = {"proof", "main"} | ({".fseventsd"} if n["system_original_metadata"] is not None else set())
        require(set(os.listdir(domain_fd)) == {"backing.sparseimage", "mount"} and set(os.listdir(mount_fd)) == expected_names, "supervision_original")
        if n["system_original_metadata"] is not None:
            info = os.stat(".fseventsd", dir_fd=mount_fd, follow_symlinks=False)
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o700
                and info.st_gid == os.fstat(mount_fd).st_gid and _stamp(info)[:6] == _tuples(n["system_original_metadata"]), "supervision_original")
        require(_stamp(os.fstat(main_fd)) == _stamp((self.mount / "main").lstat()) == _tuples(n["main_original_seal"])
            and not os.listdir(main_fd), "supervision_original")
    def current_association(self, clock):
        result = _native_command([native.HDIUTIL, "info", "-plist"], min(COMMAND_SECONDS, clock.check()))
        require(type(result.returncode) is int and result.returncode == 0 and type(result.stdout) is bytes and 0 < len(result.stdout) <= MAXIMUM_NATIVE_BYTES, "supervision_original")
        require(_association(result.stdout, self.image, self.mount, self.attach_entities) == self.device, "supervision_original")
        self.native_audit()
    def audit(self):
        self.directory.check(); self.native_audit(); self.audit_local()
    def audit_local(self):
        for path, fd, pin in self.anchors: require(path.resolve() == path and _dir(os.fstat(fd), True) == _dir(path.lstat(), True) == pin, "supervision_original")
        require(set(os.listdir(self.proof_fd)) == POSITIVE_ROLES, "supervision_negative")
        for name, fd, seal, raw in self.files:
            _require_file_immutable(os.fstat(fd)); _require_file_immutable((self.proof_path / name).lstat())
            _same(_stamp(os.fstat(fd)), seal); _same(_stamp((self.proof_path / name).lstat()), seal)
            os.lseek(fd, 0, os.SEEK_SET); require(os.read(fd, len(raw) + 1) == raw, "supervision_original")
            _require_file_immutable(os.fstat(fd)); _same(_stamp(os.fstat(fd)), seal)
            _require_file_immutable((self.proof_path / name).lstat()); _same(_stamp((self.proof_path / name).lstat()), seal)
    def _named_originals(self):
        self.directory.named()
        for path, unused, pin in self.anchors: require(path.resolve() == path and _dir(path.lstat(), True) == pin, "supervision_original")
        n = self.native
        require(native._backing(self.image.lstat()) == _tuples(n["backing_original_identity"])
            and native._fresh_root_identity(self.mount.lstat()) == _tuples(n["fresh_root_creation_identity"]), "supervision_original")
        require(set(os.listdir(self.path)) == {"backing.sparseimage", "mount"}
            and set(os.listdir(self.mount)) == {"proof", "main"} | ({".fseventsd"} if n["system_original_metadata"] is not None else set()), "supervision_original")
        if n["system_original_metadata"] is not None:
            info = (self.mount / ".fseventsd").lstat()
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o700
                and info.st_gid == self.mount.lstat().st_gid and info.st_dev == self.mount.lstat().st_dev
                and _stamp(info)[:6] == _tuples(n["system_original_metadata"]), "supervision_original")
        require(set(os.listdir(self.proof_path)) == POSITIVE_ROLES, "supervision_negative")
        for name, unused, seal, unused_raw in self.files:
            info = (self.proof_path / name).lstat(); _require_file_immutable(info); _same(_stamp(info), seal)
        _same(_stamp((self.mount / "main").lstat()), _tuples(n["main_original_seal"]))
        require(not os.listdir(self.mount / "main"), "supervision_original")
    def named(self):
        self._named_originals(); fds = []; primary = None
        try:
            # These strict independent verification reads compare ONLY original
            # producer pins; they issue no creator capability or new baseline.
            domain_fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW); fds.append(domain_fd)
            require(_dir(os.fstat(domain_fd), True) == _tuples(self.native["domain_original_identity"]), "supervision_original")
            mount_fd = os.open("mount", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=domain_fd); fds.append(mount_fd)
            require(_dir(os.fstat(mount_fd), True) == _tuples(self.native["mount_original_identity"]), "supervision_original")
            backing_fd = os.open("backing.sparseimage", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=domain_fd); fds.append(backing_fd)
            main_fd = os.open("main", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=mount_fd); fds.append(main_fd)
            self._native_originals(mount_fd, backing_fd, main_fd, domain_fd)
            self._named_originals()
        except BaseException as error: primary = error; raise
        finally:
            try: _drain(fds)
            except BaseException:
                if primary is None: raise
        self._named_originals()
    def close(self):
        first = None
        try: _drain(self.fds)
        except BaseException as error: first = error
        if self.directory is not None:
            try: self.directory.close()
            except BaseException as error:
                if first is None: first = error
        if first is not None: raise first



def _root_context_snapshot(reader, code, config, load):
    """Finite exact original contexts retained after their successful closure."""
    require(type(reader) is _OriginalRead and type(code) is _Code7 and type(config) is _Inputs
        and type(load) is _LoadTransaction and not reader.fds and not code.fds and not load.fds
        and reader.directory.closed and config.directory.closed and load.directory.closed, "supervision_factory")
    return canonical_json({
        "reader": {"head": reader.head, "remote": reader.remote, "digest": reader.digest, "observer": reader.observer,
            "producer_pid": reader.producer_pid, "marker": reader.marker, "inventory": reader.inventory,
            "anchors": [[str(path), fd, pin] for path, fd, pin in reader.anchors],
            "files": [[name, fd, seal, hash_bytes(raw), len(raw)] for name, fd, seal, raw in reader.files],
            "native": reader.native, "device": reader.device, "attach_entities": reader.attach_entities},
        "code": {"head": code.head, "remote": code.remote, "manifest": code.manifest,
            "rows": {name: [fd, seal, hash_bytes(raw), len(raw)] for name, (fd, seal, raw) in code.rows.items()}},
        "config": {name: [pin, hash_bytes(raw), len(raw), digest] for name, (pin, raw, digest) in config.rows.items()},
        "load": {"rows": [[name, fd, seal, hash_bytes(raw), len(raw)] for name, fd, seal, raw in load.rows],
            "nodes": [[str(path), fd, seal] for path, fd, seal in load.nodes]}})


def _target(): return "gui/" + str(os.getuid()) + "/" + LABEL


def _service_arguments(role):
    arguments = {"query": [LAUNCHCTL, "print", _target()],
        "load": [LAUNCHCTL, "bootstrap", "gui/" + str(os.getuid()), str(ROOT / PARENT / BOOTSTRAP / "job.plist")],
        "start": [LAUNCHCTL, "kickstart", "-p", _target()]}
    require(type(role) is str and role in arguments, "supervision_arguments"); return arguments[role]


def _launch_service(role):
    return subprocess.run(_service_arguments(role), cwd=ROOT, env=worker._environment(), stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, check=False, timeout=30)


def _kernel_metadata(raw):
    require(type(raw) is bytes and len(raw) <= 65536, "supervision_kernel")
    text = raw.decode("utf-8")
    require(text.splitlines()[:1] == [_target() + " = {"], "supervision_kernel")
    require(re.findall(r"(?m)^\tpath = ([^\r\n]+)$", text) == [str(ROOT / PARENT / BOOTSTRAP / "job.plist")], "supervision_kernel")
    values = {}
    for key, expression in (("state", r"[a-z ]+"), ("runs", r"[0-9]+"), ("active count", r"[0-9]+"), ("pid", r"[0-9]+")):
        rows = re.findall(r"(?m)^\t" + key + " = (" + expression + r")[ \t]*$", text)
        require(len(rows) <= 1 and len(rows) == len(re.findall(r"(?m)^\t" + key + " =", text)), "supervision_kernel")
        values[key] = rows[0] if rows else None
    require(all(values[key] is not None for key in ("state", "runs", "active count"))
        and values["state"] in {"running", "not running"}, "supervision_kernel")
    exits = re.findall(r"(?m)^\tlast exit code = ([^\r\n]+)$", text)
    require(len(exits) <= 1 and len(exits) == len(re.findall(r"(?m)^\tlast exit code =", text)), "supervision_kernel")
    code = None; never = exits == ["(never exited)"]
    if exits and not never:
        match = re.fullmatch(r"(-?[0-9]+)(?:: ([A-Z_]+))?[ \t]*", exits[0]); require(match is not None, "supervision_kernel")
        code = int(match[1]); require(not match[2] or startup._SYSEXITS.get(code) == match[2], "supervision_kernel")
    result = {"state": values["state"], "runs": int(values["runs"]), "active_count": int(values["active count"]),
        "pid": int(values["pid"]) if values["pid"] is not None else None, "exit": code, "pending": never or code is None}
    require(result["runs"] in (0, 1) and result["active_count"] in (0, 1)
        and (result["pid"] is None or 0 < result["pid"] < 2 ** 31)
        and (code is None or -32768 <= code <= 32767), "supervision_kernel")
    return result


def _query_service(head, remote):
    _guard(head, remote)
    result = _launch_service("query")
    require(type(result) is subprocess.CompletedProcess and type(result.returncode) is int
        and type(result.args) is list and all(type(v) is str for v in result.args) and result.args == _service_arguments("query")
        and type(result.stdout) is bytes and len(result.stdout) <= 65536, "supervision_kernel")
    if result.returncode == 113: return None
    require(result.returncode == 0, "supervision_kernel"); value = _kernel_metadata(result.stdout)
    row = (value, result, tuple(result.args), result.returncode, result.stdout, hash_bytes(result.stdout), canonical_json(value), object())
    _KERNEL_ORIGINS[id(value)] = row; return value


def _kernel_origin(value):
    row = _KERNEL_ORIGINS.get(id(value))
    require(type(row) is tuple and len(row) == 8 and row[0] is value and type(value) is dict, "supervision_factory")
    result = row[1]
    require(type(result) is subprocess.CompletedProcess and type(result.args) is list and all(type(v) is str for v in result.args)
        and tuple(result.args) == row[2] == tuple(_service_arguments("query"))
        and type(result.returncode) is int and result.returncode == row[3] == 0
        and type(result.stdout) is bytes and result.stdout == row[4] and hash_bytes(result.stdout) == row[5]
        and canonical_json(value) == row[6] and _kernel_metadata(result.stdout) == value, "supervision_changed")
    return row


def _never_started(kernel):
    require(type(kernel) is dict and kernel["runs"] == 0 and kernel["state"] == "not running"
        and kernel["active_count"] == 0 and kernel["pid"] is None and kernel["exit"] is None, "supervision_kernel")


def _terminal(kernel):
    return type(kernel) is dict and kernel["runs"] == 1 and kernel["state"] == "not running" and kernel["active_count"] == 0 and kernel["pid"] is None and type(kernel["exit"]) is int and kernel["pending"] is False


def _read_private(fd, raw):
    try: block = os.read(fd, 4096)
    except BlockingIOError: return raw, False
    if not block: return raw, True
    combined = raw + block
    if len(combined) > 65536 + 4096:
        error = SupervisionRefusal("REFUSED: supervision_unknown")
        # The actual newly consumed block is strongly retained before raising.
        _PRIVATE_FAILURES[id(error)] = error, fd, raw, block, combined, object()
        raise error
    return combined, False


def _private_failure(error, fd):
    row = _PRIVATE_FAILURES.get(id(error))
    if type(row) is not tuple or len(row) != 6 or row[0] is not error or row[1] != fd: return None
    trace = BaseException.__traceback__.__get__(error, BaseException)
    for unused in range(MAXIMUM_TRACE_FRAMES):
        if trace is None: break
        frame = trace.tb_frame
        if frame.f_code is _read_private.__code__ and frame.f_globals is globals():
            local = frame.f_locals
            if local.get("fd") == fd and local.get("raw") is row[2] and local.get("block") is row[3] and local.get("combined") is row[4]: return row
        if frame.f_code is _drain_private.__code__ and frame.f_globals is globals():
            local = frame.f_locals
            if local.get("fd") == fd and local.get("original") is row[2] and local.get("raw") is row[4] and row[2] + row[3] == row[4]: return row
        if frame.f_code is _coordinate.__code__ and frame.f_globals is globals():
            local = frame.f_locals
            if local.get("master") == fd and local.get("raw") is row[4] and row[2] == b"" and row[3] is row[4]: return row
        trace = trace.tb_next
    return None


def _drain_private(fd, raw):
    original = raw
    try:
        for unused in range(64):
            previous = raw; raw, done = _read_private(fd, raw)
            if done: return raw
            if raw is previous: return raw
        raise SupervisionRefusal("REFUSED: supervision_unknown")
    except BaseException as error:
        if id(error) not in _PRIVATE_FAILURES:
            _PRIVATE_FAILURES[id(error)] = error, fd, original, raw[len(original):], raw, object()
        raise


def coordinate_registered(head, remote):
    registered()
    with _source_denied(): return _coordinate(head, remote)


def _coordinate(head, remote):
    clock = _Clock(); code = config_directory = config = transaction = root_read = load_witness = None
    master = slave = None; raw = b""; loaded = started = start_attempt = False; kernel = None; failure = None
    scope = object(); receipt = None; public = None
    try:
        _phase("current_code"); _guard(head, remote); code = _Code7(head, remote, clock)
        require(_query_service(head, remote) is None, "supervision_kernel")
        master, slave = os.openpty(); os.set_blocking(master, False)
        settings = startup.termios.tcgetattr(slave); settings[1] &= ~startup.termios.ONLCR; settings[3] &= ~startup.termios.ECHO
        startup.termios.tcsetattr(slave, startup.termios.TCSANOW, settings)
        observer = {"nonce": secrets.token_hex(16), "terminal": list(startup._tty_pin(slave)), "slave_path": os.ttyname(slave)}
        startup._tty_check(slave, observer)
        digest = prepare_bootstrap(head, remote, observer)["spec_sha256"]
        _guard(head, remote); require(_query_service(head, remote) is None, "supervision_kernel")
        _phase("root_load"); transaction = _LoadTransaction(head, remote, digest, observer)
        startup._tty_check(slave, observer); require(_launch_service("load").returncode == 0, "supervision_kernel"); loaded = True
        transaction.audit(); startup._tty_check(slave, observer); transaction.close(); load_witness = transaction; transaction = None
        kernel = _query_service(head, remote); _never_started(kernel)
        raw = _drain_private(master, raw)
        if raw:
            error = SupervisionRefusal("REFUSED: supervision_unknown")
            _PRIVATE_FAILURES[id(error)] = error, master, b"", raw, raw, object()
            raise error
        _guard(head, remote)
        config_directory, config = _read_config(head, remote, digest, observer, code.manifest)
        kernel = _query_service(head, remote); _never_started(kernel); startup._tty_check(slave, observer)
        start_attempt = True; kernel = None
        result = _launch_service("start"); require(result.returncode == 0 and re.fullmatch(rb"[1-9][0-9]{0,9}\n?", result.stdout), "supervision_kernel")
        producer_pid = int(result.stdout); require(producer_pid < 2 ** 31, "supervision_kernel"); started = True
        _phase("root_observation")
        for unused in range(300):
            raw, unused_eof = _read_private(master, raw)
            kernel = None; kernel = _query_service(head, remote)
            require(kernel is not None and (kernel["pid"] is None or kernel["pid"] == producer_pid), "supervision_kernel")
            if _terminal(kernel): break
            clock.check(); time.sleep(1)
        require(_terminal(kernel), "supervision_unknown")
        raw = _drain_private(master, raw); startup._tty_check(slave, observer)
        try: observed = _validated_observation(raw, observer, digest, producer_pid)
        except BaseException: observed = {"status": "observer_unavailable", "failure": None}
        if kernel["exit"] != 0 or observed["status"] != "producer_complete_provisional":
            negative = SupervisionRefusal("REFUSED: supervision_negative")
            advisory = {"status": "negative_source_free_native_supervision", "target_pid": producer_pid, "actual_kernel_exit": kernel["exit"],
                "producer_observation": {"status": observed["status"], "failure": observed["failure"]}, "authority": authority()}
            _ADVISORIES[id(negative)] = negative, canonical_json(advisory); raise negative
        original_marker = _filtered_observation(raw, observer, digest, producer_pid)
        _phase("root_verification"); root_read = _OriginalRead(head, remote, digest, observer, producer_pid, original_marker)
        require(root_read.inventory["code_manifest"] == code.manifest, "supervision_code")
        root_read.current_association(clock); code.audit(); _guard(head, remote); config.audit()
        # No Git/native command after this last original-only audit.
        root_read.audit(); clock.check()
        public = {"status": "closed_source_free_native_supervision_in_memory_only", "runtime_head": head, "actual_remote": remote,
            "policy_sha256": POLICY_SHA256, "target_pid": producer_pid, "actual_kernel_exit": 0, "actual_child_exit": 0,
            "marker_sha256": original_marker["sha256"], "durable_Main_receipt": False, "sourceAUTH_blocked": True, "authority": authority()}
    except BaseException as error:
        failure = error; failure_summary(error)
        private_failure = _private_failure(error, master)
        if private_failure is not None or start_attempt and not _terminal(kernel) or loaded and kernel is None:
            state = {"master": master, "slave": slave, "code": code, "config_directory": config_directory, "config": config,
                "transaction": transaction, "load_witness": load_witness, "root_read": root_read, "raw": raw, "failure": error,
                "private_failure": private_failure,
                "start_attempted": start_attempt, "start_PID_validated": started, "kernel": kernel, "scope": scope}
            master = slave = None; code = config_directory = config = transaction = root_read = None
            try: _hold(state)
            except BaseException: raise error
    finally:
        first = failure; _phase("root_cleanup")
        for obj in (transaction, root_read, config, config_directory, code):
            if obj is not None:
                try: obj.close()
                except BaseException as error:
                    if first is None: first = error; failure_summary(error)
        for fd in (slave, master):
            if fd is not None:
                try: os.close(fd)
                except BaseException as error:
                    if first is None: first = error; failure_summary(error)
        failure = first
    if failure is not None: raise failure
    config.audit(named=True); root_read.named(); code.named(); clock.check()
    # Exact Root-issued registry witness exists only AFTER the full conjunction.
    original_kernel = _kernel_origin(kernel)
    require(_terminal(kernel) and kernel["exit"] == 0, "supervision_kernel")
    contexts = (root_read, code, config, load_witness); context_snapshot = _root_context_snapshot(*contexts)
    receipt = object.__new__(_RootReceipt); _ROOT_RECEIPTS[receipt] = (scope, canonical_json(public), original_kernel, contexts, context_snapshot, object())
    value = object.__new__(ClosedNativeSupervision); row = (value, canonical_json(public), receipt, scope)
    value._anchor = row; _CLOSED[id(value)] = row; return value


def main(argv=None):
    parser = argparse.ArgumentParser(description="One registered source-free typed native-supervision proof")
    parser.add_argument("command", choices=("prepare-proof", "run-proof", "coordinate-proof", "capture"))
    parser.add_argument("--head"); parser.add_argument("--remote"); parser.add_argument("--spec-sha256"); parser.add_argument("--observer")
    args = parser.parse_args(argv); observer = None
    try:
        if args.command == "capture": raise SupervisionRefusal("REFUSED: supervision_source_refused")
        if args.command == "run-proof":
            observer = _Observer(json.loads(args.observer), args.spec_sha256)
            result = run_registered(args.head, args.remote, args.spec_sha256, observer.config); observer.emit(result=result)
        elif args.command == "prepare-proof": print(canonical_json(prepare_bootstrap(args.head, args.remote, json.loads(args.observer))))
        else: print(canonical_json(coordinate_registered(args.head, args.remote).public_summary()))
        return 0
    except BaseException as error:
        if observer is not None:
            try: observer.emit(error=error)
            except BaseException: pass
        elif args.command != "run-proof": print(canonical_json({"status": "refused", "failure": failure_summary(error), "producer_diagnostic": advisory_summary(error), "authority": authority()}))
        return 2


_CREATOR_SITES = ((_Files.create.__code__, _Files), (_CreationCarrier.publish.__code__, _CreationCarrier),
    (_NegativeReporter.preserve.__code__, _NegativeReporter))


if __name__ == "__main__": raise SystemExit(main())
