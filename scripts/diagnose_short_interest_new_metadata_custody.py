"""One prospective creator-only metadata handshake; never repair or capture.

Historical source custody remains unchanged. Only this diagnostic's freshly
created NONCLAIM inode may settle before its single original HeldFiles seal.
"""
from __future__ import annotations

from contextlib import ExitStack
import math
import os
from pathlib import Path
import stat
import time

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import diagnose_short_interest_count_custody as prior
from scripts import short_interest_new_metadata_custody as creator

count, snapshot, lane = prior.count, prior.snapshot, prior.lane
DRIVER = "scripts/diagnose_short_interest_new_metadata_custody.py"
HELPER = "scripts/short_interest_new_metadata_custody.py"
NAMESPACE = "new-metadata-custody-20261025-v1"
OUTPUT = count.old.OUTPUT.parent / NAMESPACE
METADATA_NAME = NAMESPACE + ".original.private.json"
MAXIMUM_SECONDS, MAXIMUM_BYTES = 1800, 1024
PROTOCOL_SHA256 = "08f3354d445e51ebf73b704cddfe0f93bf271642b640d633a4d27d1b37279526"
PROVISIONAL, CLOSED, REFUSED = "run.completed.provisional.json", "run.closed.json", "run.refused.json"
_FAILURE_SEAL = object()
_CODES = frozenset("""new_metadata_protocol_pending_or_changed designated_new_metadata_driver_required
exact_58_code_manifest_required new_metadata_code_route_refused new_metadata_code_binding_changed
new_metadata_current_code_changed new_metadata_output_not_ignored new_metadata_already_exists
new_metadata_parent_refused new_metadata_parent_changed
new_metadata_deadline_exhausted new_metadata_clock_refused new_metadata_clock_backdated
new_metadata_exact_original_bytes_required new_metadata_observation_changed new_metadata_controls_changed
new_metadata_control_original_stamp_changed new_metadata_control_original_bytes_changed
new_metadata_control_protection_changed new_metadata_context_result_missing new_metadata_final_code_changed
new_metadata_final_code_identity_changed new_metadata_report_missing new_metadata_closed_original_stamp_changed
""".split())
_STAGES = frozenset("""protocol_registration platform designated_driver lane_initialization code_manifest
saved_cache_loading composed_code_loading old_diagnostic_code_loading new_code_loading code_verification
refused_prefix_loading query_plan v2_zero_loading v3_zero_loading output_preflight output_creation
source_pre_audit metadata_creation metadata_preseal_observation metadata_seal_once metadata_original_read
source_post_audit provisional_publication source_code_context_exit terminal_code_audit
terminal_original_audit terminal_publication terminal_final_code_audit terminal_final_original_audit
metadata_context_close metadata_closed_final_audit output_close
""".split())


class NewMetadataDiagnosticRefusal(ValueError):
    pass


def require(value, code):
    if not value:
        raise NewMetadataDiagnosticRefusal("REFUSED: " + code)


class _StageFailure(ValueError):
    def __init__(self, stage, error, *, seal):
        require(seal is _FAILURE_SEAL and type(stage) is str and stage in _STAGES,
            "new_metadata_report_missing")
        self._anchor = self._identity = (stage, error)
        super().__init__("new_metadata_diagnostic_refused")


def _fixed_failure(error):
    if type(error) is NewMetadataDiagnosticRefusal:
        arguments = BaseException.args.__get__(error, BaseException)
        code = None
        if type(arguments) is tuple and len(arguments) == 1 and type(arguments[0]) is str:
            code = next((item for item in _CODES if arguments[0] == "REFUSED: " + item), None)
        return {"category": "local_contract_refusal", "errno_name": None, "contract_code": code}
    if type(error) is creator.NewMetadataRefusal:
        return creator.failure_summary(error)
    return prior.fixed_local_failure(error)


def failure_summary(error):
    stage, original = "unclassified_new_metadata_failure", error
    if type(error) is _StageFailure:
        try:
            anchor, identity = object.__getattribute__(error, "_anchor"), object.__getattribute__(error, "_identity")
        except AttributeError:
            anchor, identity = None, object()
        if (anchor is identity and type(anchor) is tuple and len(anchor) == 2
            and type(anchor[0]) is str and anchor[0] in _STAGES):
            stage, original = anchor
    return {"stage": stage, **_fixed_failure(original),
        "held_field_observation": prior.project_held_file_mismatch(original)}


def authority():
    return {"diagnostic_only": True, "prospective_new_metadata_handshake_only": True,
        "is_capture_claim": False, "provider_HTTP": 0, "credential_reads": 0,
        "new_capture_claims": 0, "source_START_debits": 0, "source_charged_bytes": 0,
        "historical_022_cause": "UNKNOWN", "historical_ctime_actor": "UNKNOWN",
        "historical_repair_established": False, "source_admitted": False,
        "ready_for_backtest": False, "outcome_looks": 0, "qc_attempts": 0, "trading_authority": False}


def metadata_bytes():
    value = {"schema": "si-new-metadata-nonclaim-v1", "is_capture_claim": False,
        "provider_HTTP": 0, "credential_reads": 0, "source_START_debits": 0, "padding": ""}
    empty = canonical_json(value).encode()
    require(len(empty) <= 186, "new_metadata_exact_original_bytes_required")
    value["padding"] = "p" * (186 - len(empty))
    raw = canonical_json(value).encode()
    require(len(raw) == 186, "new_metadata_exact_original_bytes_required")
    return raw


def code_paths():
    return tuple(sorted((*prior.code_paths(), HELPER, DRIVER)))


def protocol():
    return {"schema": "si-new-metadata-custody-diagnostic-protocol-v1", "driver": DRIVER,
        "helper": HELPER, "output": str(OUTPUT), "metadata_name": METADATA_NAME,
        "metadata_bytes": 186, "metadata_raw_sha256": hash_bytes(metadata_bytes()),
        "maximum_seconds": 1800, "maximum_metadata_bytes": 1024, "maximum_samples": 16,
        "sample_seconds": 0.25, "minimum_quiet_seconds": 1.0, "maximum_seal_seconds": 8.0,
        "creation_deadline_scope": "before_first_guard_O_EXCL_through_last_writer_close_caller_delay_and_first_original_seal",
        "decision": "SI-DEC-20261025-01", "creator_scope": "new_exclusive_owned_inode_only_never_existing_source",
        "metadata_absence": "anchored_nofollow_any_existing_entry_refused_before_output_creation",
        "seal": "UNSEALED_ctime_only_then_one_untouched_original_HeldFiles_construction_all_fields_strict",
        "restart_retry_reconstruction_allowed": False, "source_history": prior.protocol()["source_history"],
        "predecessor_manifest_sha256": count.PREDECESSOR_MANIFEST_SHA256,
        "v2_claim_sha256": snapshot.ZERO_CLAIM_SHA256, "v2_refusal_sha256": snapshot.ZERO_REFUSAL_SHA256,
        "v3_claim_sha256": prior.V3_CLAIM_SHA256, "v3_refusal_sha256": prior.V3_REFUSAL_SHA256,
        "Main_previously_authenticated_antecedent_not_reopened": {
            "scope": "old_NONCLAIM_diagnostic_not_current_held_count_v3_source",
            "negative_sha256": "0868da636804930cdc54cf3d8e11db0ccedb0266b720bc2e25c2a1d79bfcbe34",
            "metadata_sha256": "d7e12dc67e4cd9a07ad0a7cd481f033dfbe1f133973468ac7921fc42d481b282",
            "current_driver_reauthentication": False, "reopened_or_repaired": False},
        "terminal": "all_source_code_contexts_exit_successfully_before_stable_callback_terminal_phase;fresh58_committed_code_then_original_controls_metadata_audit_after_final_code_audit;successful_metadata_close_then_original_seal_stamp_controls_clock_deadline_sweep",
        "code_paths": list(code_paths()), "controls": [PROVISIONAL, CLOSED, REFUSED], "authority": authority()}


def registered():
    require(hash_payload(protocol()) == PROTOCOL_SHA256 and len(code_paths()) == 58
        and (creator.MAXIMUM_BYTES, creator.MAXIMUM_SAMPLES, creator.SAMPLE_SECONDS,
             creator.QUIET_SECONDS, creator.MAXIMUM_SECONDS) == (1024, 16, 0.25, 1.0, 8.0),
        "new_metadata_protocol_pending_or_changed")


class _CodeCustody:
    def __init__(self, root, composed, old_driver, new_code):
        require(type(composed) is count._ComposedCodeCustody
            and all(type(item) is count.old.cache.HeldFiles for item in (old_driver, new_code)),
            "new_metadata_code_binding_changed")
        self._anchor = self._identity = root, composed, old_driver, new_code

    def check(self):
        require(type(self) is _CodeCustody and self._anchor is self._identity,
            "new_metadata_code_binding_changed")
        for held in self._anchor[1:]: held.check()

    def read(self, path, maximum):
        self.check()
        root, composed, old_driver, new_code = self._anchor
        require(path in tuple(root / name for name in code_paths()), "new_metadata_code_route_refused")
        held = old_driver if path == root / prior.DRIVER else new_code if path in (root / HELPER, root / DRIVER) else composed
        raw = held.read(path, maximum)
        self.check(); return raw


def _final_code(root, guard, registration):
    guard.refresh(); registered()
    entries = registration["code_files"]
    require(tuple(row["path"] for row in entries) == code_paths() and len(entries) == 58
        and registration["head"] == guard.binding()[1] and registration["remote"] == guard.binding()[2],
        "exact_58_code_manifest_required")
    stamps = []
    for row in entries:
        path = root / row["path"]
        with count.old.cache.HeldFiles((path,), protected=False, boundary=guard.check) as held:
            stamp = snapshot._file_stamp(path.lstat())
            raw = held.read(path, 8 * 1024 ** 2)
            committed = count.old.cache._git(root, ["show", registration["head"] + ":" + row["path"]], guard)
            require(type(committed) is bytes and len(committed) <= 8 * 1024 ** 2
                and hash_bytes(raw) == hash_bytes(committed) == row["sha256"], "new_metadata_final_code_changed")
            held.check(); stamps.append((path, stamp))
    for path, stamp in stamps:
        guard.check()
        require(snapshot._file_stamp(path.lstat()) == stamp, "new_metadata_final_code_changed")
    require(hash_payload({row["path"]: row["sha256"] for row in entries}) == registration["code_manifest_sha256"]
        and hash_payload({"git_commit": registration["head"], "files": entries}) == registration["code_identity_sha256"],
        "new_metadata_final_code_identity_changed")
    guard.refresh(); registered()


def _audit(owned, capability, raw, sealed_observation, controls):
    owned.check(); capability.check()
    require(capability.read(maximum=1024) == raw, "new_metadata_exact_original_bytes_required")
    require(capability.observation()["seal_stamp_sha256"] == sealed_observation["seal_stamp_sha256"],
        "new_metadata_observation_changed")
    _audit_controls(owned, controls)
    capability.check(); owned.check()


def _audit_controls(owned, controls):
    owned.check(); fd = owned._anchor[2]
    require(set(count.old.cache._inventory_names(fd, boundary=owned.check)) == set(controls),
        "new_metadata_controls_changed")
    for name, (original, stamp) in controls.items():
        require(snapshot._file_stamp(os.stat(name, dir_fd=fd, follow_symlinks=False)) == stamp,
            "new_metadata_control_original_stamp_changed")
        member = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            info = os.fstat(member)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1
                and stat.S_IMODE(info.st_mode) == 0o600 and 0 <= info.st_size <= 65536,
                "new_metadata_control_protection_changed")
            observed = os.read(member, 65537)
            require(observed == original, "new_metadata_control_original_bytes_changed")
            require(snapshot._file_stamp(os.fstat(member)) == stamp,
                "new_metadata_control_original_stamp_changed")
        finally: os.close(member)
    for name, (unused, stamp) in controls.items():
        require(snapshot._file_stamp(os.stat(name, dir_fd=fd, follow_symlinks=False)) == stamp,
            "new_metadata_control_original_stamp_changed")
    owned.check()


def _after_metadata_close(owned, sealed_observation, controls):
    """Compare the ORIGINAL seal, never reopen or construct new metadata custody."""
    def original_stamp():
        info = os.stat(METADATA_NAME, dir_fd=owned._anchor[3], follow_symlinks=False)
        stamp = (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode),
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1 and info.st_size == 186
            and hash_payload(list(stamp)) == sealed_observation["seal_stamp_sha256"],
            "new_metadata_closed_original_stamp_changed")
    owned.check(); original_stamp(); _audit_controls(owned, controls); original_stamp()


def _preflight_absent_metadata(parent, boundary):
    boundary()
    require(parent.is_absolute() and parent.resolve() == parent, "new_metadata_parent_refused")
    before = parent.lstat()
    def stamp(info): return info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)
    require(stat.S_ISDIR(before.st_mode) and before.st_uid == os.getuid()
        and stat.S_IMODE(before.st_mode) == 0o700, "new_metadata_parent_refused")
    fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        require(stamp(os.fstat(fd)) == stamp(before), "new_metadata_parent_changed")
        try: os.stat(METADATA_NAME, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError: pass
        else: raise NewMetadataDiagnosticRefusal("REFUSED: new_metadata_already_exists")
        require(stamp(os.fstat(fd)) == stamp(parent.lstat()) == stamp(before), "new_metadata_parent_changed")
    finally: os.close(fd)
    boundary()


def run_registered(root, *, runtime_head, actual_remote, complete_code_manifest):
    phase = ["protocol_registration"]
    try:
        return _run(root, runtime_head, actual_remote, complete_code_manifest, phase)
    except Exception as error:
        if type(error) is _StageFailure: raise
        raise _StageFailure(phase[0], error, seal=_FAILURE_SEAL) from None


def _run(root, runtime_head, actual_remote, complete_code_manifest, phase):
    registered(); phase[0] = "platform"; prior._require_capture_platform()
    phase[0] = "designated_driver"
    require(root == lane.ROOT and Path(__file__).absolute() == root / DRIVER,
        "designated_new_metadata_driver_required")
    began, last_tick, last_clock = time.monotonic(), [None], [None]
    def window():
        now = time.monotonic()
        require(type(now) in (int, float) and type(began) in (int, float)
            and math.isfinite(now) and math.isfinite(began) and 0 <= began <= now <= 2 ** 53
            and (last_tick[0] is None or last_tick[0] <= now)
            and now - began < MAXIMUM_SECONDS, "new_metadata_deadline_exhausted")
        last_tick[0] = now
    def at():
        raw = prior._utc_now(); value = count.old.parallel.clock(raw)
        require(last_clock[0] is None or last_clock[0] <= value, "new_metadata_clock_backdated")
        last_clock[0] = value; return raw
    phase[0] = "lane_initialization"
    guard = lane.LaneGuard(root, expected_head=runtime_head, expected_remote=actual_remote); guard.refresh()
    phase[0] = "code_manifest"
    require(type(complete_code_manifest) is dict and set(complete_code_manifest) == set(code_paths()),
        "exact_58_code_manifest_required")
    owned, capability, metadata_context, registration, components = None, None, None, None, ()
    controls, observations, source_closed, failure, started = {}, {}, [False], None, None
    context_error, provisional, creation_attempts = None, None, 0
    def fail(error, stage):
        if capability is not None:
            try: observations["terminal"] = capability.observation()
            except Exception: pass  # The original fixed failure always wins.
        return {"stage": stage, **_fixed_failure(error),
            "held_field_observation": prior.project_held_file_mismatch(error, components=components)}
    def report(status, ended):
        return prior._seal({"schema": "si-new-metadata-custody-diagnostic-v1", "status": status,
            "protocol_sha256": PROTOCOL_SHA256, "registration": registration, "started_at": started,
            "completed_at": ended, "observations": observations, "failure": failure,
            "context_closure": "all_source_and_code_contexts_closed" if source_closed[0]
                else "provisional_source_and_code_contexts_not_successfully_closed",
            "closed_at": ended if status == "new_metadata_handshake_closed" else None,
            "original_provisional_report_sha256": None if provisional is None else provisional.sha256,
            "metadata_publication_attempts": creation_attempts,
            "original_creation_outcome": "accepted_original_creator_capability" if capability is not None
                else "unknown_partial_creation_possible" if creation_attempts else "not_attempted",
            "probes_published": 1 if capability is not None else None if creation_attempts else 0,
            "probes_opened": int(observations.get("sealed", {}).get("original_HeldFiles_attempted") is True),
            "probes_read": int("read" in observations), "authority": authority()})
    def publish(name, result):
        guard.check(); owned.check(); window()
        raw = result.to_bytes(); owned.publish(name, raw)
        controls[name] = raw, snapshot._file_stamp(os.stat(name, dir_fd=owned._anchor[2], follow_symlinks=False))
        guard.check(); owned.check()
    try:
        try:
            with ExitStack() as stack:
                phase[0] = "saved_cache_loading"
                saved = stack.enter_context(count.old.cache.load_registered_cache(root, runtime_head=runtime_head,
                    actual_remote=actual_remote, for_counts=True))
                phase[0] = "composed_code_loading"
                extra_names = tuple(name for name in count.code_paths() if name not in count.old.cache.COUNT_CODE_FILES)
                extra = stack.enter_context(count.old.cache.HeldFiles(tuple(root / name for name in extra_names),
                    protected=False, boundary=guard.check))
                composed = count._ComposedCodeCustody(root, saved._anchor[2], extra)
                phase[0] = "old_diagnostic_code_loading"
                old_code = stack.enter_context(count.old.cache.HeldFiles((root / prior.DRIVER,), protected=False, boundary=guard.check))
                phase[0] = "new_code_loading"
                new_code = stack.enter_context(count.old.cache.HeldFiles((root / HELPER, root / DRIVER), protected=False, boundary=guard.check))
                code = _CodeCustody(root, composed, old_code, new_code)
                phase[0] = "code_verification"
                entries, identity = count.old.cache._code_manifest(root, runtime_head, code_paths(), code, guard)
                require({row["path"]: row["sha256"] for row in entries} == complete_code_manifest,
                    "new_metadata_current_code_changed")
                phase[0] = "refused_prefix_loading"
                prefix = stack.enter_context(snapshot.load_refused_child(root, saved.plan, guard,
                    expected_manifest_sha256=count.PREDECESSOR_MANIFEST_SHA256))
                phase[0] = "query_plan"; queries = count.freeze_queries(saved.plan)
                phase[0] = "v2_zero_loading"; zero = stack.enter_context(snapshot.load_zero_start_predecessor(root, guard, queries))
                phase[0] = "v3_zero_loading"; v3_held, v3 = stack.enter_context(prior._v3_zero(root, guard, queries))
                v2_registration = count.old._parse(zero._anchor[3])["registration"]
                v3_registration = count.old._parse(v3._anchor[4])["registration"]
                registration = {"head": runtime_head, "remote": actual_remote, "branch": lane.BRANCH,
                    "ref": lane.REF, "code_files": entries,
                    "code_file_count": 58, "code_identity_sha256": identity,
                    "code_manifest_sha256": hash_payload(complete_code_manifest), "authority": authority(),
                    "historical_sources": {
                        "refused_prefix": {"head": snapshot.SOURCE_HEAD,
                            "code_identity_sha256": snapshot.SOURCE_CODE_SHA256,
                            "manifest_sha256": count.PREDECESSOR_MANIFEST_SHA256},
                        "v2_zero": {**v2_registration, "claim_sha256": snapshot.ZERO_CLAIM_SHA256,
                            "refusal_sha256": snapshot.ZERO_REFUSAL_SHA256,
                            "code_manifest_sha256": snapshot.ZERO_CODE_MANIFEST_SHA256},
                        "v3_zero": {**v3_registration, "claim_sha256": prior.V3_CLAIM_SHA256,
                            "refusal_sha256": prior.V3_REFUSAL_SHA256}}}
                def normal():
                    guard.check(); code.check(); saved.source_custody(); saved.code_custody(); prefix.check(); zero.check(); v3.check()
                def full():
                    normal(); guard.refresh(); prefix.full_check(); zero.full_check(); v3.full_check(); normal(); window()
                target = root / OUTPUT
                phase[0] = "output_preflight"
                require(count.old.cache._git(root, ["check-ignore", str(target)], guard).strip() == str(target).encode(),
                    "new_metadata_output_not_ignored")
                _preflight_absent_metadata(target.parent, guard.check)
                window(); phase[0] = "output_creation"
                owned = prior._OwnedOutput(prior._prepare_capture_directory(target), guard.check)
                def metadata_boundary():
                    # Identity never changes. Terminal routing is entered only
                    # below, after the entire source/code ExitStack succeeds.
                    if source_closed[0]: guard.check(); owned.check(); window()
                    else: normal(); owned.check(); window()
                components = ((saved._anchor[2], "base_code"), (extra, "extra_code"), (old_code, "probe_code"),
                    *tuple(zip(saved._anchor[1], ("cache_source", "master_source", "matrix_source"))),
                    (zero._anchor[1], "v2_zero"), (v3_held, "v3_zero"))
                phase[0] = "source_pre_audit"; started = at(); full()
                phase[0] = "metadata_creation"
                metadata_context = creator.prepare_owned_metadata(owned, METADATA_NAME, metadata_bytes(),
                    parent=True, boundary=metadata_boundary)
                creation_attempts = 1
                capability = metadata_context.__enter__()
                phase[0] = "metadata_preseal_observation"; observations["unsealed"] = capability.observation()
                require(observations["unsealed"]["phase"] == "UNSEALED"
                    and observations["unsealed"]["original_HeldFiles_attempted"] is False,
                    "new_metadata_observation_changed")
                phase[0] = "metadata_seal_once"; capability.seal_once()
                observations["sealed"] = capability.observation()
                phase[0] = "metadata_original_read"
                require(capability.read(maximum=1024) == metadata_bytes(), "new_metadata_exact_original_bytes_required")
                observations["read"] = capability.observation()
                phase[0] = "source_post_audit"; full()
                phase[0] = "provisional_publication"
                provisional = report("new_metadata_handshake_provisional", at()); publish(PROVISIONAL, provisional)
                _audit(owned, capability, metadata_bytes(), observations["sealed"], controls)
                phase[0] = "source_code_context_exit"
            source_closed[0] = True
        except Exception as error:
            context_error = error
            failure = fail(error, phase[0])
        if owned is None:
            if context_error is not None: raise context_error
            raise NewMetadataDiagnosticRefusal("REFUSED: new_metadata_context_result_missing")
        if failure is None:
            try:
                phase[0] = "terminal_code_audit"; _final_code(root, guard, registration); window()
                phase[0] = "terminal_original_audit"
                _audit(owned, capability, metadata_bytes(), observations["sealed"], controls)
                phase[0] = "terminal_publication"
                closed = report("new_metadata_handshake_closed", at()); publish(CLOSED, closed)
                phase[0] = "terminal_final_code_audit"; _final_code(root, guard, registration); window()
                phase[0] = "terminal_final_original_audit"
                _audit(owned, capability, metadata_bytes(), observations["sealed"], controls); at(); window()
                phase[0] = "metadata_context_close"; metadata_context.__exit__(None, None, None); metadata_context = None
                phase[0] = "metadata_closed_final_audit"; guard.refresh(); registered(); at(); window()
                _after_metadata_close(owned, observations["sealed"], controls); at(); window()
                return closed
            except Exception as error:
                failure = fail(error, phase[0])
        # Failed source exit never switches callback phase or retries sealing.
        guard.check(); owned.check()
        refused = report("new_metadata_handshake_refused", None)
        # Preserve a fixed negative even after deadline exhaustion; no new probe.
        raw = refused.to_bytes(); owned.publish(REFUSED, raw)
        return refused
    finally:
        try:
            if metadata_context is not None:
                error = NewMetadataDiagnosticRefusal("REFUSED: new_metadata_context_result_missing")
                try: metadata_context.__exit__(type(error), error, None)
                except Exception as cleanup_error:
                    raise _StageFailure("metadata_context_close", cleanup_error, seal=_FAILURE_SEAL) from None
        finally:
            if owned is not None:
                phase[0] = "output_close"; owned.close()
