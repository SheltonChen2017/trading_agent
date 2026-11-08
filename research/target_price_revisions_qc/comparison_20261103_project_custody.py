"""Fresh registered-project custody reads, never create/write/compile/backtest.

The old creation adapter's short-lived receipt chain remains unchanged. This
successor checks the fixed registry directly, uses that adapter's genuine TLS
transport and observed metadata schema, and shares the current native API lock.
A safe full wire is private; returned projections omit owner/org/PII values.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import time

from . import comparison_20261029_project_api as api

projects, ops, evidence = api.projects, api.ops, api.e
MODULE = "research/target_price_revisions_qc/comparison_20261103_project_custody.py"
REQUIRED_SOURCES = api.REQUIRED_SOURCES | frozenset((MODULE,))
PRIVATE_ROOT = api.PRIVATE_ROOT.parent / "project-custody-20261103"
REGISTRY_SHA256 = "154e8ff056eb776f070fd73922b724367e634b1b37d4052b70a464601d0c94f1"
CREATION_OWNER_SHA256 = "ea2dd7037a0f33ab78771a2f6deb3016da34b164ab04f5b2c69f30c4ae31157f"
RELEASE_INSTRUCTION = ("you can access QC and Safari now. proceed with QC preflight, then run OFF "
    "and the remaining arms when ready. keep the 20 REMX rows quarantined, skip Claude review, "
    "and push only once when done.")
RELEASE_SHA256 = api._sha(RELEASE_INSTRUCTION.encode())
ARMS = tuple(api.PROJECT_KEYS)
MAX_RESPONSE = 2 * 1024 * 1024
MAX_REQUESTS = 10
MAX_TOTAL_RESPONSE = MAX_REQUESTS * MAX_RESPONSE
MAX_OUTPUT = 24 * 1024 * 1024
MAX_CONTROL = 128 * 1024
PRIVACY_BASIS = "documented_private_default_and_observed_collaborators"


class CustodyRefusal(ValueError):
    pass


class CustodyCancelled(KeyboardInterrupt):
    def __init__(self, report):
        self.report = api._clone(report)
        super().__init__("registered custody read cancelled; no automatic retry")


class CustodyFatal(BaseException):
    def __init__(self, report):
        self.report = api._clone(report)
        super().__init__("registered custody read stopped; no automatic retry")


def _fail():
    raise CustodyRefusal("registered custody read refused; no automatic retry") from None


def _closed(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        _fail()


def _requests(targets):
    return [{"id": str(index) + "-" + phase, "arm": arm, "phase": phase,
        "project_id": project, "endpoint": endpoint, "payload": {"projectId": project}}
        for index, (arm, project) in enumerate(targets.items())
        for phase, endpoint in (("metadata", "projects/read"),
                                ("collaborators", "projects/collaboration/read"))]


def prepare_plan(*, project_bindings_raw, expected_project_bindings_sha256,
        operation_id, git_head, source_hashes, latest_owner_instruction_sha256,
        created_utc, expires_utc, arm=None, seconds=20, mode="production"):
    """Pure fixed-request plan; caller freshly claims the supplied registry read.

    arm=None reads all five registered projects (ten requests); one registered
    arm reads just its two endpoints. There is no endpoint/payload override.
    The registry's creation authority and the current release remain separate.
    Neither an instruction hash nor a registry is independent human/native proof.
    """
    try:
        if (type(operation_id) is not str or
                re.fullmatch(r"TPR-CUSTODY-[A-Za-z0-9_.-]{1,60}", operation_id) is None
                or type(git_head) is not str or re.fullmatch("[a-f0-9]{40}", git_head) is None
                or type(source_hashes) is not dict or set(source_hashes) != REQUIRED_SOURCES
                or mode not in ("production", "offline-fixture")
                or latest_owner_instruction_sha256 != RELEASE_SHA256
                or type(seconds) is not int or not 1 <= seconds <= 40):
            _fail()
        for digest in source_hashes.values():
            api._hash(digest)
        issued, expires = api._clock(created_utc), api._clock(expires_utc)
        if not timedelta(0) < expires - issued <= timedelta(seconds=600):
            _fail()
        registry = projects.validate_bindings(project_bindings_raw,
            expected_sha256=expected_project_bindings_sha256)
        if (registry["adapter_source_sha256"] != source_hashes[api.PROJECTS_MODULE]
                or {key: row["project_id"] for key, row in registry["projects"].items()}
                    != api.REGISTERED_PROJECTS
                or registry["owner_instruction_sha256"] == latest_owner_instruction_sha256):
            _fail()
        if mode == "production" and (len(project_bindings_raw) != 3573
                or expected_project_bindings_sha256 != REGISTRY_SHA256
                or registry["owner_instruction_sha256"] != CREATION_OWNER_SHA256):
            _fail()
        if arm is not None and (type(arm) is not str or arm not in ARMS):
            _fail()
        selected = ARMS if arm is None else (arm,)
        targets = {key: api.REGISTERED_PROJECTS[api.PROJECT_KEYS[key]] for key in selected}
        requests = _requests(targets)
        if len(requests) > MAX_REQUESTS or seconds * len(requests) > (expires - issued).total_seconds():
            _fail()
        plan = {"schema": "tpr-registered-custody-read-plan-v1",
            "operation_id": operation_id, "git_head": git_head, "source_hashes": source_hashes,
            "project_bindings_json": project_bindings_raw.decode("ascii"),
            "project_bindings_sha256": expected_project_bindings_sha256,
            "registry_creation_owner_instruction_sha256": registry["owner_instruction_sha256"],
            "latest_owner_instruction_sha256": latest_owner_instruction_sha256,
            "created_utc": created_utc, "expires_utc": expires_utc,
            "arm": arm, "targets": targets, "requests": requests, "seconds": seconds,
            "max_response_bytes_each": MAX_RESPONSE,
            "max_native_wire_probe_bytes_each": MAX_RESPONSE + 1,
            "max_total_response_bytes": len(requests) * MAX_RESPONSE,
            "max_output_bytes": MAX_OUTPUT, "max_control_bytes_each": MAX_CONTROL,
            "attempt_id": None, "financial_outcome_look": None, "automatic_retry": False,
            "market_trading_authorized": False, "mode": mode}
        if len(api._canonical(plan)) > MAX_CONTROL:
            _fail()
        return api._clone(plan)
    except CustodyRefusal:
        raise
    except Exception:
        _fail()


def _validated(plan):
    _closed(plan, ("schema", "operation_id", "git_head", "source_hashes",
        "project_bindings_json", "project_bindings_sha256",
        "registry_creation_owner_instruction_sha256", "latest_owner_instruction_sha256",
        "created_utc", "expires_utc", "arm", "targets", "requests", "seconds",
        "max_response_bytes_each", "max_native_wire_probe_bytes_each",
        "max_total_response_bytes", "max_output_bytes", "max_control_bytes_each",
        "attempt_id", "financial_outcome_look", "automatic_retry",
        "market_trading_authorized", "mode"))
    if type(plan["project_bindings_json"]) is not str:
        _fail()
    kwargs = {key: plan[key] for key in ("operation_id", "git_head", "source_hashes",
        "latest_owner_instruction_sha256", "created_utc", "expires_utc", "arm", "seconds", "mode")}
    expected = prepare_plan(project_bindings_raw=plan["project_bindings_json"].encode("ascii"),
        expected_project_bindings_sha256=plan["project_bindings_sha256"], **kwargs)
    if api._canonical(plan) != api._canonical(expected):
        _fail()
    return api._clone(plan)


def _guard(plan):
    api._guard(plan)
    if (Path(__file__) != api.LANE / MODULE
            or Path(projects.__file__) != api.LANE / projects.MODULE):
        _fail()
    if api.subprocess.run(["git", "check-ignore", "-q", str(PRIVATE_ROOT)],
            cwd=api.LANE, capture_output=True, timeout=10).returncode:
        _fail()


def _projection(body, request, registry):
    """Observed existing API schema, with no guessed privacy flag or PII output."""
    if type(body) is not dict or body.get("success") is not True or body.get("errors") not in (None, []):
        _fail()
    owner, organization = registry["owner_id"], registry["organization_id"]
    project = request["project_id"]
    if "projectId" in body and projects._integer(body["projectId"]) != project:
        _fail()
    if request["phase"] == "metadata":
        rows = body.get("projects")
        if type(rows) is not list or len(rows) != 1:
            _fail()
        metadata = projects._metadata(rows[0], owner=owner, org=organization,
            arm=api.PROJECT_KEYS[request["arm"]], project=project)
        return {"phase": "metadata", "project_id": project,
            "registered_name_matches": True, "registered_organization_matches": True,
            "registered_owner_matches": True, "owner_field_verified": True, "language": "Py",
            "collaborator_count": metadata["collaborator_count"],
            "nonowner_collaborator_count": metadata["nonowner_collaborator_count"],
            "collaborators_sha256": metadata["collaborators_sha256"],
            "explicit_privacy_flag_observed": metadata["explicit_privacy_flag_observed"],
            "privacy_basis": PRIVACY_BASIS,
            "normalized_metadata_sha256": api._sha(evidence.canonical(metadata)),
            "independent_native_origin_attested": False}
    if body.get("userPermissions") != "write":
        _fail()
    collaborators = projects._collaborators(body.get("collaborators"), owner)
    return {"phase": "collaborators", "project_id": project, **collaborators,
        "user_permissions": "write", "privacy_basis": PRIVACY_BASIS,
        "independent_native_origin_attested": False}


def _execute(plan, root, lock_root, *, transport, guard, clock, monotonic):
    plan = _validated(plan)
    production = plan["mode"] == "production"
    if ((production and (root != PRIVATE_ROOT or lock_root != api.PRIVATE_ROOT
            or transport is not projects._native_request or guard is not _guard
            or clock is not api._utcnow or monotonic is not time.monotonic))
            or (not production and (root == PRIVATE_ROOT or root.is_relative_to(api.LANE)
                or lock_root != root or transport is projects._native_request))):
        _fail()
    frozen = api._canonical(plan)
    started, previous_now, previous_tick = monotonic(), None, None
    registry = projects.validate_bindings(plan["project_bindings_json"].encode("ascii"),
        expected_sha256=plan["project_bindings_sha256"])

    def check(*, native_seconds=0):
        nonlocal previous_now, previous_tick
        guard(plan)
        now, tick = clock(), monotonic()
        if (type(now) is not datetime or now.utcoffset() != timedelta(0)
                or not api._clock(plan["created_utc"]) <= now < api._clock(plan["expires_utc"])
                or type(tick) not in (int, float) or not 0 <= tick - started < 600
                or previous_now is not None and now < previous_now
                or previous_tick is not None and tick < previous_tick
                or api._canonical(plan) != frozen
                or api._clock(plan["expires_utc"]) - now < timedelta(seconds=native_seconds)
                or 600 - (tick - started) < native_seconds):
            _fail()
        previous_now, previous_tick = now, tick

    check()
    if root.resolve() != root or lock_root.resolve() != lock_root:
        _fail()
    if production:
        for path in (ops.PRIVATE_PARENT, api.PRIVATE_ROOT.parent, api.PRIVATE_ROOT, root):
            path.mkdir(mode=0o700, exist_ok=True)
            ops._custody(path.lstat(), True)
    else:
        root.mkdir(mode=0o700, exist_ok=True)
        ops._custody(root.lstat(), True)
    report = {"schema": "tpr-registered-custody-read-result-v1",
        "operation_id": plan["operation_id"], "git_head": plan["git_head"],
        "registry_creation_owner_instruction_sha256": plan["registry_creation_owner_instruction_sha256"],
        "latest_owner_instruction_sha256": plan["latest_owner_instruction_sha256"],
        "plan_sha256": api._sha(frozen), "status": "failed_or_uncertain",
        "request_count_planned": len(plan["requests"]), "transport_calls_attempted": 0,
        "response_bytes": 0, "requests": [], "metadata_projects_completed": [],
        "collaborator_projects_completed": [], "registered_custody_metadata_complete": False,
        "source_custody_or_cloud_bytes_verified": False,
        "independent_native_origin_attested": False, "financial_acceptance": False,
        "compile_requests": 0, "backtests_created": 0, "market_trading_authorized": False,
        "automatic_retry": False, "receipt_published": False, "lock_cleanup_complete": False,
        "local_block_reason": None}
    written = 0

    def publish(name, raw, *, final=False, maximum=MAX_CONTROL):
        nonlocal written
        if not final:
            check()
        reserve = 0 if final else MAX_CONTROL
        if type(raw) is not bytes or not 0 < len(raw) <= maximum or written + len(raw) > MAX_OUTPUT - reserve:
            _fail()
        descriptor = api._publish(root, name, raw)
        written += len(raw)
        return descriptor

    operation = plan["operation_id"]
    # A spent operation is immutable and cannot reach even lock acquisition.
    try:
        publish(operation + ".operation.spent.json", frozen)
    except BaseException as error:
        if isinstance(error, KeyboardInterrupt):
            raise CustodyCancelled(report) from None
        if not isinstance(error, Exception):
            raise CustodyFatal(report) from None
        _fail()
    lock = stop = None
    lock_path = lock_root / "comparison-api.lock"
    try:
        check()
        try:
            lock = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            report["local_block_reason"] = "shared_native_api_lock_contention"
            raise
        ops._custody(os.fstat(lock))
        lock_raw = api._canonical({"operation_id": operation, "plan_sha256": report["plan_sha256"]})
        if os.write(lock, lock_raw) != len(lock_raw):
            _fail()
        os.fsync(lock)
        directory = os.open(lock_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            ops._custody(os.fstat(directory), True)
            os.fsync(directory)
        finally:
            os.close(directory)
        for request in plan["requests"]:
            check()
            prefix = operation + "." + request["id"]
            row = {"id": request["id"], "phase": request["phase"], "arm": request["arm"],
                "project_id": request["project_id"], "http_status": None, "response_bytes": 0,
                "status": "failed_or_uncertain", "stage": "claim",
                "request_claim": None, "raw_response": None, "projection": None}
            report["requests"].append(row)
            row["request_claim"] = publish(prefix + ".request.spent.json", api._canonical({
                "plan_sha256": report["plan_sha256"], "git_head": plan["git_head"],
                "source_hashes": plan["source_hashes"], "created_utc": plan["created_utc"],
                "expires_utc": plan["expires_utc"], "request": request,
                "latest_owner_instruction_sha256": plan["latest_owner_instruction_sha256"],
                "registry_creation_owner_instruction_sha256": plan["registry_creation_owner_instruction_sha256"],
                "max_response_bytes": MAX_RESPONSE, "max_native_wire_probe_bytes": MAX_RESPONSE + 1,
                "seconds": plan["seconds"], "attempt_id": None, "financial_outcome_look": None}))
            row["stage"] = "native_budget_guard"
            # Keychain and TLS share the genuine transport's whole timeout.
            # Claim fsync/source guards may have consumed the remaining grant.
            check(native_seconds=plan["seconds"])
            row["stage"] = "transport"
            report["transport_calls_attempted"] += 1
            raw, status, credential, authenticated_owner = transport(request["endpoint"],
                api._canonical(request["payload"]), plan["seconds"], MAX_RESPONSE, registry["owner_id"])
            row["stage"] = "post_transport_guard"
            check()
            row["stage"] = "wire_validation"
            if (type(raw) is not bytes or not 0 < len(raw) <= MAX_RESPONSE
                    or report["response_bytes"] + len(raw) > plan["max_total_response_bytes"]
                    or type(status) is not int or not 100 <= status <= 599
                    or projects._integer(authenticated_owner) != registry["owner_id"]
                    or type(credential) is not str or re.fullmatch(r"[!-~]{1,256}", credential) is None):
                _fail()
            report["response_bytes"] += len(raw)
            row["response_bytes"], row["http_status"] = len(raw), status
            evidence.project_wire(raw, credential=credential)
            row["raw_response"] = publish(prefix + ".response.raw", raw, maximum=MAX_RESPONSE)
            if status != 200:
                _fail()
            row["stage"] = request["phase"]
            projection = _projection(evidence.parse_json(raw), request, registry)
            row["projection"] = publish(prefix + ".projection.json", api._canonical(projection))
            (report["metadata_projects_completed"] if request["phase"] == "metadata"
                else report["collaborator_projects_completed"]).append(request["project_id"])
            row["status"], row["stage"] = "succeeded", "complete"
            check()
        report["registered_custody_metadata_complete"] = True
        report["status"] = "completed"
    except BaseException as error:
        stop = error
    finally:
        if lock is not None:
            try:
                owned = os.fstat(lock)
                current = os.stat(lock_path, follow_symlinks=False)
                if (owned.st_dev, owned.st_ino) != (current.st_dev, current.st_ino):
                    _fail()
                os.unlink(lock_path)
                os.close(lock)
                lock = None
                directory = os.open(lock_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
                report["lock_cleanup_complete"] = True
            except BaseException as error:
                stop = api._retain_stop(stop, error)
            finally:
                if lock is not None:
                    try:
                        os.close(lock)
                    except BaseException as error:
                        stop = api._retain_stop(stop, error)
        if stop is not None:
            report["status"] = "cancelled" if isinstance(stop, KeyboardInterrupt) else "failed_or_uncertain"
            report["registered_custody_metadata_complete"] = False
        try:
            report["receipt_published"] = True
            descriptor = publish(operation + ".result.json", api._canonical(report), final=True)
            report["receipt"] = descriptor
        except BaseException as error:
            report["receipt_published"] = False
            report["status"] = "failed_or_uncertain"
            stop = api._retain_stop(stop, error)
    if isinstance(stop, KeyboardInterrupt):
        raise CustodyCancelled(report) from None
    if stop is not None and not isinstance(stop, Exception):
        raise CustodyFatal(report) from None
    return api._clone(report)


def execute_plan(plan):
    """Actual read-only production transport/root/guards; no caller callbacks."""
    try:
        if type(plan) is not dict or plan.get("mode") != "production":
            _fail()
        return _execute(plan, PRIVATE_ROOT, api.PRIVATE_ROOT, transport=projects._native_request,
            guard=_guard, clock=api._utcnow, monotonic=time.monotonic)
    except (CustodyCancelled, CustodyFatal):
        raise
    except BaseException as error:
        if isinstance(error, KeyboardInterrupt):
            raise CustodyCancelled({"status": "cancelled", "receipt_published": False,
                "automatic_retry": False, "financial_acceptance": False}) from None
        if not isinstance(error, Exception):
            raise CustodyFatal({"status": "failed_or_uncertain", "receipt_published": False,
                "automatic_retry": False, "financial_acceptance": False}) from None
        _fail()


def _execute_fixture(plan, root, *, transport, clock, guard=lambda _: None, monotonic=lambda: 0.0):
    """Synthetic temp root only; never labels a fixture transport as production."""
    if type(plan) is not dict or plan.get("mode") != "offline-fixture":
        _fail()
    return _execute(plan, root, root, transport=transport, guard=guard, clock=clock, monotonic=monotonic)
