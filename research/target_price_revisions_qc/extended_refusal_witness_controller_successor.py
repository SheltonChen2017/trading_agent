"""Offline-prepared local custody for a future exact-key witness read.

No CLI, current permit, native adapter, credential, client or notebook is
created. Exact inert program bytes are rebuilt for comparison, never executed.
Current callers/tests must inject SYNTHETIC seams only. A future real
read needs fresh owner-released QC scope, genuine ephemeral Mia capability and
reviewed adapter/clock/repository bindings; passing dictionaries is not proof
of those facts. Native reads cannot be preempted or bounded before allocation.
This module never launches a job or changes/renews an attempt or spent scope.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import uuid

from . import extended_refusal_witness_runtime_successor as runtime
from . import extended_refusal_witness_program_successor as program

LANE = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__target_price_revisions")
BRANCH = "codex/strategy-target-price-revisions"
PREFIX = "research/target_price_revisions_qc/"
SOURCE_PATHS = tuple(PREFIX + name for name in (
    "extended_refusal_witness_controller_successor.py",
    "extended_refusal_witness_runtime_successor.py",
    "extended_refusal_witness_read_design.py",
    "extended_refusal_witness_context_successor.py",
    "extended_refusal_witness_program_successor.py"))
MAX_RECEIPT_BYTES = 16384
_PLAN_KEYS = frozenset(("schema operation_id mode git_head physical_root branch source_hashes "
    "owner_instruction_sha256 permit capsule_sha256 program_sha256 receipt_directory").split())
_RECEIPT_KEYS = frozenset(("schema operation_id invocation_id plan_sha256 status failure_stage "
    "lock_acquired lock_cleanup_complete claim_attempted claim_written access_written native_read_invocations "
    "contains_calls read_calls runtime_result scope_spent authority_granted ready_for_dispatch "
    "native_binding_proven sdk_hard_timeout_proven byte_bound_before_native_allocation_proven "
    "off_baseline_valid on_launch_authorized new_jobs new_codex_attempts new_looks").split())
_FALSE_KEYS = frozenset(("authority_granted ready_for_dispatch native_binding_proven "
    "sdk_hard_timeout_proven byte_bound_before_native_allocation_proven off_baseline_valid "
    "on_launch_authorized").split())
_HASH = re.compile(r"[a-f0-9]{64}")
_HEAD = re.compile(r"[a-f0-9]{40}")
_NONCE = re.compile(r"[a-f0-9]{32}")
_STAGES = frozenset(("preflight", "lock", "claim", "access", "native_read", "post_read", "cleanup", "complete"))


class ControllerRefusal(ValueError):
    """Fixed body-free refusal, with no caller/native exception text."""


class ControllerReceiptUnavailable(ControllerRefusal):
    """No durable receipt was possible; no success/receipt claim is returned."""


class ControllerCancelled(KeyboardInterrupt):
    """Cancellation propagates only after its closed receipt is durable."""
    def __init__(self, receipt):
        super().__init__("prepared witness controller cancelled; no continued reads")
        self._receipt = validate_receipt(receipt)

    @property
    def receipt(self):
        return validate_receipt(self._receipt)


def _fail():
    raise ControllerRefusal("prepared witness controller refused")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _closed(value, keys):
    if type(value) is not dict or set(value) != keys:
        _fail()


def _hash(value):
    if type(value) is not str or _HASH.fullmatch(value) is None:
        _fail()
    return value


def _public_sources():
    """Read fixed PUBLIC source bytes only, not private evidence or Git state."""
    result = {}
    for relative in SOURCE_PATHS:
        path = LANE / relative
        if path.resolve() != path:
            _fail()
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 65536:
                _fail()
            raw = os.read(fd, 65537)
            if len(raw) != info.st_size:
                _fail()
            result[relative] = raw
        finally:
            os.close(fd)
    return result


def source_hashes():
    return {name: _sha(raw) for name, raw in _public_sources().items()}


def _program_bytes(plan, capsule, sources):
    return program.build_program(builder_raw=sources[PREFIX + "extended_refusal_witness_program_successor.py"],
        expected_builder_sha256=plan["source_hashes"][PREFIX + "extended_refusal_witness_program_successor.py"],
        runtime_raw=sources[PREFIX + "extended_refusal_witness_runtime_successor.py"],
        reader_raw=sources[PREFIX + "extended_refusal_witness_read_design.py"],
        witness_raw=sources[PREFIX + "extended_refusal_witness_context_successor.py"],
        permit=plan["permit"], capsule=capsule).encode("utf-8")


NATIVE_ADAPTER_PERMITTED = False


def _lane_identity(path, lane):
    """True when `path` is the lane, one of its parents, or inside it, decided by
    real paths and directory identity rather than text, so case aliases and
    firmlinks cannot slip past the boundary."""
    candidate, lane_real = Path(path), Path(os.path.realpath(lane))
    real = Path(os.path.realpath(candidate))
    if (candidate == lane or candidate in lane.parents or candidate.is_relative_to(lane)
            or real == lane_real or real in lane_real.parents or real.is_relative_to(lane_real)):
        return True
    try:
        lane_info = os.stat(lane)
    except OSError:
        return False
    current = candidate
    while True:
        try:
            info = os.stat(current)
        except OSError:
            info = None
        if info is not None and (info.st_dev, info.st_ino) == (lane_info.st_dev, lane_info.st_ino):
            return True
        if current.parent == current:
            return False
        current = current.parent


def _validate_plan(plan, capsule):
    """Pure prospective shape check; not owner authorization or registration."""
    _closed(plan, _PLAN_KEYS)
    if (plan["schema"] != "tpr-ext26-witness-controller-contract-v1"
            or plan["mode"] != "offline-prepared-synthetic-only"
            or plan["physical_root"] != str(LANE) or plan["branch"] != BRANCH
            or type(plan["git_head"]) is not str or _HEAD.fullmatch(plan["git_head"]) is None):
        _fail()
    runtime.validate_permit(plan["permit"])
    if plan["operation_id"] != plan["permit"]["operation_id"]:
        _fail()
    encoded_capsule = runtime.validate_capsule(capsule, operation_id=plan["operation_id"])
    if _hash(plan["capsule_sha256"]) != _sha(encoded_capsule):
        _fail()
    _hash(plan["owner_instruction_sha256"])
    _hash(plan["program_sha256"])
    path = plan["receipt_directory"]
    if (type(path) is not str or not 1 <= len(path) <= 1024 or not Path(path).is_absolute()
            or str(Path(path)) != path or _lane_identity(path, LANE)):
        _fail()
    _closed(plan["source_hashes"], frozenset(SOURCE_PATHS))
    for value in plan["source_hashes"].values():
        _hash(value)
    raw = _canonical(plan)
    if len(raw) > 8192:
        _fail()
    return json.loads(raw)


def validate_plan(plan, capsule):
    try:
        return _validate_plan(plan, capsule)
    except (runtime.RuntimeReadRefusal, TypeError, ValueError, OverflowError):
        _fail()


def design():
    return {"schema": "tpr-ext26-witness-controller-design-v1", "controller_prepared": True,
        "mandatory_injected_seam": True, "lock_before_claim": True, "unique_failure_receipts": True,
        "current_permit_registered": False, "native_adapter_constructed": False,
        "ready_for_dispatch": False, "authority_granted": False, "off_baseline_valid": False,
        "on_launch_authorized": False, "native_binding_proven": False}


def validate_receipt(receipt):
    _closed(receipt, _RECEIPT_KEYS)
    if (receipt["schema"] != "tpr-ext26-witness-controller-receipt-v1"
            or type(receipt["invocation_id"]) is not str or _NONCE.fullmatch(receipt["invocation_id"]) is None
            or type(receipt["status"]) is not str
            or receipt["status"] not in {"failed_or_uncertain", "completed_diagnostic_only", "cancelled"}
            or type(receipt["failure_stage"]) is not str or receipt["failure_stage"] not in _STAGES
            or any(receipt[key] is not False for key in _FALSE_KEYS)):
        _fail()
    runtime._operation(receipt["operation_id"])
    _hash(receipt["plan_sha256"])
    for key in ("lock_acquired", "lock_cleanup_complete", "claim_attempted", "claim_written", "access_written", "scope_spent"):
        if type(receipt[key]) is not bool:
            _fail()
    if (receipt["scope_spent"] != receipt["claim_attempted"]
            or receipt["claim_attempted"] and not receipt["lock_acquired"]
            or receipt["claim_written"] and not receipt["claim_attempted"]
            or receipt["claim_written"] and not receipt["lock_acquired"]
            or receipt["access_written"] and not receipt["claim_written"]
            or type(receipt["native_read_invocations"]) is not int
            or receipt["native_read_invocations"] not in (0, 1)
            or receipt["native_read_invocations"] and not receipt["access_written"]):
        _fail()
    for key in ("new_jobs", "new_codex_attempts", "new_looks"):
        if type(receipt[key]) is not int or receipt[key] != 0:
            _fail()
    if receipt["runtime_result"] is not None:
        result = runtime.validate_result(receipt["runtime_result"])
        if (receipt["native_read_invocations"] != 1 or result["operation_id"] != receipt["operation_id"]
                or any(type(receipt[key]) is not int for key in ("contains_calls", "read_calls"))
                or receipt["contains_calls"] != result["contains_calls"] or receipt["read_calls"] != result["read_calls"]):
            _fail()
    elif receipt["native_read_invocations"]:
        if receipt["contains_calls"] is not None or receipt["read_calls"] is not None:
            _fail()
    elif any(type(receipt[key]) is not int or receipt[key] != 0 for key in ("contains_calls", "read_calls")):
        _fail()
    if receipt["status"] == "completed_diagnostic_only" and (receipt["failure_stage"] != "complete"
            or receipt["runtime_result"] is None
            or receipt["runtime_result"]["status"] != "completed_diagnostic_only"
            or not receipt["lock_cleanup_complete"]):
        _fail()
    raw = _canonical(receipt)
    if len(raw) > MAX_RECEIPT_BYTES:
        _fail()
    return json.loads(raw)


def _file_ok(info):
    return (stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid()
        and stat.S_IMODE(info.st_mode) == 0o600)


def _publish(directory, name, raw):
    """Atomic no-replace publication; only the invocation's own temp is removed."""
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_RECEIPT_BYTES:
        _fail()
    temporary = ".pending-" + uuid.uuid4().hex
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        if not _file_ok(os.fstat(fd)):
            _fail()
        offset = 0
        while offset < len(raw):
            written = os.write(fd, raw[offset:])
            if written <= 0:
                _fail()
            offset += written
        os.fsync(fd)
        os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
        os.fsync(directory)
    finally:
        try:
            named, owned = os.stat(temporary, dir_fd=directory, follow_symlinks=False), os.fstat(fd)
            if (named.st_dev, named.st_ino) == (owned.st_dev, owned.st_ino):
                os.unlink(temporary, dir_fd=directory)
                os.fsync(directory)
        finally:
            os.close(fd)


def _open_directory(path):
    path = Path(path)
    if (not path.is_absolute() or path.resolve() != path or _lane_identity(path, LANE)):
        _fail()
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(fd)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700):
        os.close(fd)
        _fail()
    return fd


def execute_prepared_read(plan, capsule, directory, *, program_raw, native_read, repository_guard, utc_now, monotonic_clock):
    """Synthetic use ONLY now; there is no production mode or genuine adapter.

    ``native_read(program_raw, permit, capsule)`` is mandatory and called once
    at most, with exact bytes independently rebuilt from pinned public sources.
    It
    must return runtime's body-free result, never wire text. Unknown native
    counts remain null after an unreturned/invalid seam, not manufactured zero.
    Repository/context/clocks remain externally authenticated future obligations.
    """
    checked = validate_plan(plan, capsule)
    if (type(program_raw) is not bytes or not 0 < len(program_raw) <= program.MAX_PROGRAM_BYTES
            or _sha(program_raw) != checked["program_sha256"]
            or str(Path(directory)) != checked["receipt_directory"]
            or not all(callable(item) for item in (native_read, repository_guard, utc_now, monotonic_clock))):
        _fail()
    # Synthetic-only is enforced, not labelled: an adapter must declare itself
    # synthetic until a reviewed change permits a genuine native adapter.
    if not NATIVE_ADAPTER_PERMITTED and getattr(native_read, "tpr_synthetic_adapter", None) is not True:
        _fail()
    frozen_plan, frozen_capsule = _canonical(checked), runtime.validate_capsule(capsule, operation_id=checked["operation_id"])
    receipt = {"schema": "tpr-ext26-witness-controller-receipt-v1", "operation_id": checked["operation_id"],
        "invocation_id": uuid.uuid4().hex, "plan_sha256": _sha(frozen_plan), "status": "failed_or_uncertain",
        "failure_stage": "preflight", "lock_acquired": False, "lock_cleanup_complete": False,
        "claim_attempted": False, "claim_written": False, "access_written": False, "native_read_invocations": 0,
        "contains_calls": 0, "read_calls": 0, "runtime_result": None, "scope_spent": False,
        **dict.fromkeys(_FALSE_KEYS, False), "new_jobs": 0, "new_codex_attempts": 0, "new_looks": 0}
    try:
        fd = _open_directory(directory)
    except Exception:
        raise ControllerReceiptUnavailable("prepared witness receipt unavailable; no read attempted") from None
    lock = None
    cancelled = False
    escaped = None
    start = previous_tick = None
    previous_now = None
    issued = runtime._clock_text(checked["permit"]["issued_utc"])
    expires = runtime._clock_text(checked["permit"]["expires_utc"])
    maximum = checked["permit"]["max_elapsed_seconds"]

    def check():
        nonlocal start, previous_tick, previous_now
        observed = repository_guard()
        _closed(observed, frozenset(("physical_root", "git_toplevel", "branch", "git_head")))
        sources = _public_sources()
        if (observed != {"physical_root": str(LANE), "git_toplevel": str(LANE), "branch": BRANCH, "git_head": checked["git_head"]}
                or _canonical(validate_plan(plan, capsule)) != frozen_plan
                or runtime.validate_capsule(capsule, operation_id=checked["operation_id"]) != frozen_capsule
                or {name: _sha(raw) for name, raw in sources.items()} != checked["source_hashes"]
                or _program_bytes(checked, capsule, sources) != program_raw):
            _fail()
        now, tick = utc_now(), monotonic_clock()
        if (type(now) is not datetime or now.utcoffset() != timedelta(0)
                or type(tick) not in (int, float) or not math.isfinite(tick)):
            _fail()
        if start is None:
            start = tick
        if (not issued <= now < expires or not 0 <= tick - start < maximum
                or previous_tick is not None and tick < previous_tick
                or previous_now is not None and now < previous_now):
            _fail()
        previous_tick, previous_now = tick, now

    try:
        try:
            check()
            receipt["failure_stage"] = "lock"
            lock = os.open("controller.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            receipt["lock_acquired"] = True
            if not _file_ok(os.fstat(lock)):
                _fail()
            os.fsync(lock); os.fsync(fd)
            check()
            receipt["failure_stage"] = "claim"
            # An interrupted publication may have linked the immutable claim
            # before its fsync returned. Treat the reservation as spent/uncertain
            # rather than authorizing a retry from a false "unspent" result.
            receipt["claim_attempted"] = receipt["scope_spent"] = True
            _publish(fd, checked["operation_id"] + ".claim.spent.json", frozen_plan)
            receipt["claim_written"] = True
            check()
            receipt["failure_stage"] = "access"
            _publish(fd, checked["operation_id"] + ".access.json", _canonical({"schema": "tpr-ext26-witness-controller-access-v1",
                "plan_sha256": receipt["plan_sha256"], "capsule_sha256": checked["capsule_sha256"],
                "max_invocations": 1, "max_contains_calls": 2, "max_read_calls": 2, "launch": False}))
            receipt["access_written"] = True
            check()
            receipt["failure_stage"] = "native_read"
            receipt["native_read_invocations"] = 1
            receipt["contains_calls"] = receipt["read_calls"] = None
            result = native_read(program_raw, json.loads(runtime.validate_permit(checked["permit"])), json.loads(frozen_capsule))
            result = runtime.validate_result(result)
            if result["operation_id"] != checked["operation_id"]:
                _fail()
            receipt["runtime_result"] = result
            receipt["contains_calls"], receipt["read_calls"] = result["contains_calls"], result["read_calls"]
            receipt["failure_stage"] = "post_read"
            check()
            if result["status"] == "completed_diagnostic_only":
                receipt["status"], receipt["failure_stage"] = "completed_diagnostic_only", "complete"
            elif result["status"] == "cancelled":
                cancelled = True
                receipt["status"] = "cancelled"
        except runtime.RuntimeReadCancelled as error:
            try:
                result = runtime.validate_result(error.result)
                if result["operation_id"] == checked["operation_id"] and receipt["native_read_invocations"] == 1:
                    receipt["runtime_result"] = result
                    receipt["contains_calls"], receipt["read_calls"] = result["contains_calls"], result["read_calls"]
            except Exception:
                pass  # Native counts stay explicitly unknown, never reset.
            cancelled = True
            receipt["status"] = "cancelled"
        except KeyboardInterrupt:
            cancelled = True
            receipt["status"] = "cancelled"
        except Exception:
            receipt["status"] = "failed_or_uncertain"
        except BaseException as error:
            # SystemExit and friends still get a durable receipt before escaping.
            receipt["status"] = "failed_or_uncertain"
            escaped = error
        finally:
            if lock is not None:
                try:
                    named, owned = os.stat("controller.lock", dir_fd=fd, follow_symlinks=False), os.fstat(lock)
                    if (named.st_dev, named.st_ino) == (owned.st_dev, owned.st_ino):
                        os.unlink("controller.lock", dir_fd=fd)
                        os.fsync(fd)
                        receipt["lock_cleanup_complete"] = True
                    else:
                        receipt["status"], receipt["failure_stage"] = ("cancelled" if cancelled else "failed_or_uncertain"), "cleanup"
                except KeyboardInterrupt:
                    cancelled = True
                    receipt["status"], receipt["failure_stage"] = "cancelled", "cleanup"
                except Exception:
                    receipt["status"], receipt["failure_stage"] = ("cancelled" if cancelled else "failed_or_uncertain"), "cleanup"
                finally:
                    try:
                        os.close(lock)
                    except KeyboardInterrupt:
                        cancelled = True
                        receipt["status"], receipt["failure_stage"] = "cancelled", "cleanup"
                    except Exception:
                        receipt["status"], receipt["failure_stage"] = ("cancelled" if cancelled else "failed_or_uncertain"), "cleanup"
        try:
            final = validate_receipt(receipt)
        except Exception:
            raise ControllerReceiptUnavailable("prepared witness receipt unavailable; no automatic retry") from None
        try:
            _publish(fd, checked["operation_id"] + ".attempt-" + receipt["invocation_id"] + ".result.json", _canonical(final))
        except Exception:
            if cancelled:
                # A cancellation stays a cancellation even when its receipt cannot be written.
                raise ControllerCancelled(final) from None
            raise ControllerReceiptUnavailable("prepared witness receipt unavailable; no automatic retry") from None
        if escaped is not None:
            raise escaped
        if cancelled:
            raise ControllerCancelled(final) from None
        return final
    finally:
        os.close(fd)
