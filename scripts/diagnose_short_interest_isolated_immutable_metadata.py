"""One isolated-volume synthetic custody proof; never provider/source admission.

Preserves the original creator, setter, nine-field seal and real EPERM
challenges. The new storage environment is a hypothesis, not actor attribution.
"""
from contextlib import ExitStack
import os
from pathlib import Path
import time

from data.hashing import hash_bytes, hash_payload
from scripts import diagnose_short_interest_immutable_metadata as base
from scripts import short_interest_isolated_custody_volume as storage

DRIVER = "scripts/diagnose_short_interest_isolated_immutable_metadata.py"
STORAGE = "scripts/short_interest_isolated_custody_volume.py"
WRAPPER = "scripts/run_short_interest_isolated_custody_offline.py"
NAME = base.NAME
INNER_DIRECTORY = "proof"
MAXIMUM_SECONDS, HOLD_SECONDS = 420, 5
PROTOCOL_SHA256 = "0e334f0018fad61e35a1b8b211a1c0a72834e566eb822ad41325c1b13756d03a"
_LAST_TRANSITION = None
_CODES = frozenset("""isolated_proof_registration_changed isolated_proof_driver_changed
isolated_proof_manifest_changed isolated_proof_code_changed isolated_proof_deadline
isolated_proof_result_missing isolated_proof_output_not_ignored
""".split())


class IsolatedProofRefusal(ValueError):
    pass


def require(value, code):
    if not value: raise IsolatedProofRefusal("REFUSED: " + code)


def authority():
    return {**base.authority(), "isolated_storage_hypothesis_only": True,
        "persistent_storage_qualified": False, "maximum_body_custody_proved": False}


def code_paths():
    return tuple(sorted((*base.code_paths(), STORAGE, DRIVER, WRAPPER)))


def protocol():
    return {"schema": "si-isolated-kernel-immutable-proof-policy-v3",
        "decision": "SI-DEC-20261027-02", "authority_id": "SI-AUTH-20261026-02",
        "driver": DRIVER, "offline_harness": WRAPPER, "storage_policy_sha256": hash_payload(storage.policy()),
        "original_immutable_policy_sha256": hash_payload(base.immutable.policy()),
        "original_observer_policy_sha256": hash_payload(base.transition.policy()),
        "inner_directory": INNER_DIRECTORY, "name": NAME,
        "raw_sha256": hash_bytes(base.previous.metadata_bytes()), "bytes": 186,
        "maximum_seconds": MAXIMUM_SECONDS, "minimum_hold_seconds": HOLD_SECONDS,
        "new_probe_inodes": 1, "native_set_calls": 1, "retries": 0,
        "challenge": ["write_open", "same_mode_fchmod", "fixed_fsetxattr"],
        "required_errno": "EPERM", "old_evidence_reopened": False,
        "original_seal_checks_unchanged": True,
        "storage_refusal_projection": "original_attach_and_selected_info_hashes_exact_device_mount_join_and_field_names_only",
        "closure": "original_metadata_output_code_exits_then_volume_exit_fresh_final_committed_code_original_seal_and_original_volume_audits",
        "code_paths": list(code_paths()), "authority": authority()}


def failure_summary(error):
    if type(error) is IsolatedProofRefusal:
        args = BaseException.args.__get__(error, BaseException)
        code = next((name for name in _CODES if type(args) is tuple and len(args) == 1
            and type(args[0]) is str and args[0] == "REFUSED: " + name), None)
        result = {"category": "local_contract_refusal", "contract_code": code, "errno_name": None}
    elif type(error) is storage.IsolatedVolumeRefusal:
        result = storage.failure_summary(error)
    else:
        result = base._failure_summary(error)
    result["storage_association"] = storage.association_diagnostic()
    if _LAST_TRANSITION is not None:
        try: result["native_transition"] = _LAST_TRANSITION.report()
        except base.transition.TransitionDiagnosticRefusal:
            result["native_transition"] = {"status": "no_closed_observer_report"}
    return result


def _code(root, guard, mapping, held):
    require(type(mapping) is dict and set(mapping) == set(code_paths()), "isolated_proof_manifest_changed")
    rows, identity = base.previous.count.old.cache._code_manifest(
        root, guard.binding()[1], code_paths(), held, guard)
    require({row["path"]: row["sha256"] for row in rows} == mapping, "isolated_proof_code_changed")
    held.check()
    return identity


def run_registered(root, *, runtime_head, actual_remote, complete_code_manifest):
    global _LAST_TRANSITION
    _LAST_TRANSITION = None
    began, last_tick = time.monotonic(), [None]
    started = base.previous.prior._utc_now()
    started_clock = base.previous.count.old.parallel.clock(started)
    def window():
        now = time.monotonic()
        require(type(now) in (int, float) and type(began) in (int, float)
            and 0 <= began <= now <= 2 ** 53
            and (last_tick[0] is None or last_tick[0] <= now)
            and now - began < MAXIMUM_SECONDS, "isolated_proof_deadline")
        last_tick[0] = now
        return now
    require(hash_payload(protocol()) == PROTOCOL_SHA256 and len(code_paths()) == 64
        and (MAXIMUM_SECONDS, HOLD_SECONDS) == (420, 5), "isolated_proof_registration_changed")
    require(root == base.previous.lane.ROOT and Path(__file__).absolute() == root / DRIVER,
        "isolated_proof_driver_changed")
    guard = base.previous.lane.LaneGuard(root, expected_head=runtime_head, expected_remote=actual_remote)
    guard.refresh(); window()
    raw, held_live, fd, result = base.previous.metadata_bytes(), [True], None, None
    with ExitStack() as code_stack:
        held = code_stack.enter_context(base.previous.count.old.cache.HeldFiles(
            tuple(root / name for name in code_paths()), protected=False, boundary=guard.check))
        identity = _code(root, guard, complete_code_manifest, held); window()
        def storage_boundary():
            guard.check(); window()
            if held_live[0]: held.check()
        with storage.prepare_registered_volume(root, boundary=storage_boundary) as volume:
            target = volume.mountpoint / INNER_DIRECTORY
            require(base.previous.count.old.cache._git(root, ["check-ignore", str(target)], guard).strip()
                == str(target).encode(), "isolated_proof_output_not_ignored")
            with base.previous.prior._OwnedOutput(
                    base.previous.prior._prepare_capture_directory(target), guard.check) as owned:
                directory_stamp, parent_stamp = owned._anchor[4:6]
                def boundary():
                    storage_boundary(); volume.check()
                try:
                    with base.transition.observe_original_transition(directory_fd=owned._anchor[2], name=NAME,
                            proof_binding=(base.require, base.ImmutableProofRefusal, base._CODES)) as diagnostic:
                        _LAST_TRANSITION = diagnostic
                        with base.immutable.prepare_owned_immutable_metadata(owned, NAME, raw,
                                parent=False, boundary=boundary) as capability:
                            capability.seal_once(); capability.check()
                            expected = capability.observation()["seal_stamp_sha256"]
                            fd = os.open(NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                dir_fd=owned._anchor[2])
                            base._original(fd, owned, expected, raw)
                            challenges = base._challenge(fd, owned)
                            until = window() + HOLD_SECONDS
                            while window() < until:
                                time.sleep(.25); capability.check()
                                base._original(fd, owned, expected, raw); window()
                            _code(root, guard, complete_code_manifest, held); window()
                            code_stack.close()
                            held_live[0] = False
                            capability.check(); guard.refresh(); window()
                        closed = capability.closed_summary()
                        base._original(fd, owned, expected, raw); boundary()
                    trace_report = diagnostic.report()
                    require(trace_report["diagnostic"]["observer_complete"] is True,
                        "isolated_proof_result_missing")
                    result = {"schema": "si-isolated-kernel-immutable-proof-closed-v3",
                        "status": "closed_offline_isolated_new_inode_only", "runtime_head": runtime_head,
                        "actual_remote": actual_remote, "code_identity_sha256": identity,
                        "code_manifest_sha256": hash_payload(complete_code_manifest),
                        "protocol_sha256": PROTOCOL_SHA256, "started_at": started,
                        "metadata_raw_sha256": hash_bytes(raw), "seal_stamp_sha256": expected,
                        "helper_closed_summary_sha256": hash_payload(closed),
                        "native_transition": trace_report, "challenges": challenges,
                        "original_code_and_metadata_contexts_closed": True, "authority": authority()}
                finally:
                    if fd is not None: os.close(fd)
            guard.refresh(); window()
            with base.previous.count.old.cache.HeldFiles(tuple(root / name for name in code_paths()),
                    protected=False, boundary=guard.check) as final:
                require(_code(root, guard, complete_code_manifest, final) == identity,
                    "isolated_proof_code_changed")
            window()
            base._after_all_closes(target, directory_stamp, parent_stamp, expected, raw, guard)
            volume.check(); window()
        # Native storage/retained-FD context exit must itself succeed. Never
        # accept a provisional synthetic result or choose a new evidence seal.
        volume.check_after_close()
        storage_summary = volume.closed_summary()
        with base.previous.count.old.cache.HeldFiles(tuple(root / name for name in code_paths()),
                protected=False, boundary=guard.check) as terminal:
            require(_code(root, guard, complete_code_manifest, terminal) == identity,
                "isolated_proof_code_changed")
        base._after_all_closes(target, directory_stamp, parent_stamp, expected, raw, guard)
        volume.check_after_close(); guard.refresh(); window()
    require(type(result) is dict, "isolated_proof_result_missing")
    closed_at = base.previous.prior._utc_now()
    require(base.previous.count.old.parallel.clock(closed_at) >= started_clock, "isolated_proof_deadline")
    result["closed_at"] = closed_at
    result["isolated_storage_closed_summary_sha256"] = hash_payload(storage_summary)
    window()
    return result
