"""A1-only, serialized successor to the frozen V4 recovery continuation.

Every action authenticates V4 admission and completes inside one held family
session. Exclusive batches own their exact output names. An incomplete batch,
or lifecycle evidence not owned by a completed V5 batch, is a stop: it is never
renamed, repaired, retried or interpreted as a terminal outcome. Completed
capacity-only waits may be followed after the original bounded poll interval.

These are scoped held/named checks, not a same-user sandbox or continuous
integrity proof. A completed batch is NOT proof of the caller's actual exit 0;
the separately frozen operational caller and external run record must supply
that fact before any subsequent action. No operation occurs on import.
"""
from __future__ import annotations

import re
from contextlib import contextmanager

try:
    import fcntl
except ImportError:  # Importable elsewhere; operations still refuse before inputs.
    fcntl = None

from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
from scripts import arv2_newrule_storage_recovery_v4 as recovery
from scripts import arv2_newrule_execution_environment as environment

SCHEMA = "arv2-newrule-recovery-continuation-v5"
ROOT_RECEIPT = "continuation-v5-family.json"
OPERATIONS = ("capacity", "begin", "compile", "launch", "status", "read", "summarize")
FROZEN_SUBMISSION_SHA256 = "cfd2456f2835bb1a4d2c04d6bb60a633b537a2af276a478ad3bfa5f2bc348d4f"
PROFILE = {"schema": SCHEMA, "operations": list(OPERATIONS),
    "candidate_order": [row[0] for row in old.CELLS], "attempt": 1,
    "compile_interval_seconds": old.COMPILE_INTERVAL, "compile_poll_limit": old.COMPILE_POLLS,
    "status_interval_seconds": old.STATUS_INTERVAL, "status_poll_limit": old.STATUS_POLLS,
    "unresolved_batch": "stop", "mixed_lifecycle_state": "refuse",
    "actual_action_exit_confirmation_required": True,
    "paper_or_live_ready": False, "formal_forward_ready": False}
PROFILE_SHA256 = old._sha(old._canonical(PROFILE))
ContinuationRefused = old.NewruleSubmissionError
FINITE_CODES = old.FINITE_REFUSAL_CODES | frozenset(("mixed_lifecycle_state", "v5_family_binding",
    "batch_claim", "batch_completion", "batch_output_collision", "batch_output_changed",
    "batch_clock", "batch_outputs", "candidate_order", "continuation_busy", "native_lock_unavailable"))
# Real QC backtest statuses observed in this lane's earlier runs (section 305);
# the compact compile/read states are a different enum and stay unchanged.
BACKTEST_PENDING = frozenset(("In Queue...", "In Progress..."))
BACKTEST_TERMINAL = frozenset(("Completed.", "Runtime Error"))
_BATCH_RE = re.compile(r"v5-(capacity|R(?:298|299|30[0-3])-A1-(begin|compile|launch|status|read))-(\d{3})-batch-claim\.json")
_LIFECYCLE_RE = re.compile(r"(?:capacity(?:-|\.)|R(?:298|299|30[0-3])-(?:A\d+(?:-|\.)|project\.))")


def finite_failure(error):
    if type(error) is ContinuationRefused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and len(args[0]) <= 64 and args[0] in FINITE_CODES:
            return args[0]
    return "operation_refused"


@contextmanager
def _locked(directory):
    """Serialize cooperative V5 processes; this does not revoke old APIs."""
    old._require(fcntl is not None, "native_lock_unavailable")
    try:
        fcntl.flock(directory.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise ContinuationRefused("continuation_busy") from None
    try:
        yield
    finally:
        fcntl.flock(directory.fd, fcntl.LOCK_UN)


def _binding(plan, receipt):
    return {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256,
            "family_sha256": plan.family_sha256, "admission_sha256": receipt}


def _stem(operation, candidate):
    return "v5-capacity" if operation == "capacity" else f"v5-{candidate}-A1-{operation}"


def _rpc_names(marker):
    return {marker + suffix for suffix in ("-intent.json", "-observed.json")}


def _allowed(operation, marker, candidate, item):
    """The complete finite namespace a batch may produce; optional is explicit."""
    stem = f"{candidate}-A1"
    if operation == "capacity":
        return _rpc_names(marker + "-project") | _rpc_names(marker) | {marker + "-valid.json"}
    if operation == "begin":
        names = {stem + "-claim.json", candidate + "-project.json", stem + "-compile.json",
                 marker + "-capacity-valid.json"}
        for suffix in ("capacity-reference", "capacity", "create-project", "owned-project",
                       "prior-runs", "initial-files", "delete-default-notebook", "source-readback", "compile-create"):
            names |= _rpc_names(marker + "-" + suffix)
        for index, _ in enumerate(item.source_files):
            names |= _rpc_names(f"{marker}-source-{index:02d}")
        return names
    if operation == "compile":
        return _rpc_names(marker) | {marker + "-valid.json", stem + "-compile-ready.json", stem + "-terminal.json"}
    if operation == "launch":
        names = {marker + "-capacity-valid.json", stem + "-launch.json"}
        for suffix in ("project", "files", "capacity", "backtest-create"):
            names |= _rpc_names(marker + "-" + suffix)
        return names
    if operation == "status":
        return _rpc_names(marker) | {marker + "-valid.json", stem + "-terminal.json"}
    names = {stem + "-result-read-claim.json", stem + "-retained-statistics.json", stem + "-result.json"}
    for suffix in ("project", "source", "aggregate-read"):
        names |= _rpc_names(marker + "-" + suffix)
    return names


def _outputs_match(operation, marker, candidate, allowed, outputs, outcome):
    """Require the exact finite outcome inventory, including RPC pairs."""
    stem, optional = f"{candidate}-A1", set()
    required = set(allowed)
    if operation == "capacity":
        valid = outcome in {"available", "wait"}
    elif operation == "begin":
        valid = outcome in {"success", "wait"}
        if outcome == "wait":
            required = _rpc_names(marker + "-capacity-reference") | _rpc_names(marker + "-capacity") | {marker + "-capacity-valid.json"}
        else:
            optional = _rpc_names(marker + "-delete-default-notebook")
            required -= optional
    elif operation == "compile":
        valid = outcome in {"InQueue", "Building", "BuildSuccess", "BuildError"}
        required -= {stem + "-compile-ready.json", stem + "-terminal.json"}
        if outcome == "BuildSuccess": required.add(stem + "-compile-ready.json")
        if outcome == "BuildError": required.add(stem + "-terminal.json")
    elif operation == "launch":
        valid = outcome in {"success", "wait"}
        if outcome == "wait": required -= _rpc_names(marker + "-backtest-create") | {stem + "-launch.json"}
    elif operation == "status":
        valid = outcome in BACKTEST_PENDING | BACKTEST_TERMINAL
        if outcome not in BACKTEST_TERMINAL: required.remove(stem + "-terminal.json")
    else:
        valid = operation == "read" and outcome == "success"
    return valid and (set(outputs) == required or set(outputs) == required | optional)


def _state(directory, plan, record, receipt):
    """Authenticate every V5 batch and reject all unowned lifecycle evidence."""
    names = set(directory.names())
    lifecycle = {name for name in names if name.startswith("v5-") or _LIFECYCLE_RE.match(name)}
    if ROOT_RECEIPT not in names:
        old._require(not lifecycle, "mixed_lifecycle_state")
        return []
    old._require(old._same(directory.read(ROOT_RECEIPT), _binding(plan, receipt)), "v5_family_binding")
    owned, batches, groups = set(), [], {}
    for name in sorted(lifecycle):
        match = _BATCH_RE.fullmatch(name)
        if match is None:
            continue
        group, operation, digits = match.groups()
        operation = operation or "capacity"
        candidate = None if operation == "capacity" else group.split("-", 1)[0]
        item = None if candidate is None else old._cell(plan, record, candidate, 1)[1]
        marker = name[:-len("-batch-claim.json")]
        ordinal, claim = int(digits), directory.read(name)
        expected = {**_binding(plan, receipt), "operation": operation, "candidate_id": candidate,
                    "attempt": None if candidate is None else 1, "ordinal": ordinal,
                    "epoch": claim.get("epoch"), "allowed_outputs": sorted(_allowed(operation, marker, candidate, item))}
        old._require(type(claim.get("epoch")) is int and claim["epoch"] >= 0
                     and old._same(claim, expected), "batch_claim")
        completion_name = marker + "-batch-complete.json"
        old._require(completion_name in names, "prior_poll_ambiguous")
        complete = directory.read(completion_name)
        outputs = complete.get("outputs")
        old._require(set(complete) == {"schema", "claim_sha256", "epoch", "outputs", "outcome", "result_sha256"}
                     and complete["schema"] == SCHEMA
                     and complete["claim_sha256"] == old._sha(old._canonical(claim))
                     and type(complete.get("epoch")) is int and complete["epoch"] >= claim["epoch"]
                     and type(outputs) is dict and type(complete.get("outcome")) is str
                     and _outputs_match(operation, marker, candidate, claim["allowed_outputs"], outputs, complete["outcome"]),
                     "batch_completion")
        old._digest(complete["result_sha256"])
        old._require(not owned.intersection(outputs), "batch_output_collision")
        for output, digest in outputs.items():
            old._digest(digest)
            old._require(output in names and old._sha(old._canonical(directory.read(output))) == digest,
                         "batch_output_changed")
        owned.update(outputs)
        owned.update((name, completion_name))
        groups.setdefault(group, []).append(ordinal)
        batches.append((group, ordinal, complete["epoch"]))
    old._require(owned == lifecycle, "mixed_lifecycle_state")
    for ordinals in groups.values():
        old._require(sorted(ordinals) == list(range(1, len(ordinals) + 1)), "poll_budget")
    return batches


def _batch(directory, plan, record, operation, candidate, receipt, batches):
    group = _stem(operation, candidate)[len("v5-"):]
    previous = sorted((ordinal, epoch) for name, ordinal, epoch in batches if name == group)
    maximum = 1 if operation == "read" else old.COMPILE_POLLS if operation == "compile" else old.STATUS_POLLS
    interval = old.COMPILE_INTERVAL if operation == "compile" else old.STATUS_INTERVAL
    old._require(len(previous) < maximum, "poll_budget")
    now = int(old.time.time())
    old._require(now >= 0, "batch_clock")
    if previous:
        old._require(now - previous[-1][1] >= interval, "wait_before_poll")
    marker = f"{_stem(operation, candidate)}-{len(previous) + 1:03d}"
    item = None if candidate is None else old._cell(plan, record, candidate, 1)[1]
    claim = {**_binding(plan, receipt), "operation": operation, "candidate_id": candidate,
             "attempt": None if candidate is None else 1, "ordinal": len(previous) + 1,
             "epoch": now, "allowed_outputs": sorted(_allowed(operation, marker, candidate, item))}
    if ROOT_RECEIPT not in directory.names():
        directory.write(ROOT_RECEIPT, _binding(plan, receipt))
    before_names = set(directory.names())
    prior_hashes = {name: old._sha(old._canonical(directory.read(name))) for name in sorted(before_names)
        if name == ROOT_RECEIPT or name.startswith("v5-") or _LIFECYCLE_RE.match(name)}
    directory.write(marker + "-batch-claim.json", claim)
    return marker, claim, (before_names, prior_hashes)


def _finish(directory, marker, claim, before, result):
    before_names, prior_hashes = before
    after = set(directory.names())
    outputs = after - before_names - {marker + "-batch-claim.json"}
    operation = claim["operation"]
    outcome = result.get("status") if operation in {"compile", "status"} else result.get("state", "success")
    old._require(before_names <= after and _outputs_match(operation, marker, claim["candidate_id"],
        claim["allowed_outputs"], outputs, outcome), "batch_outputs")
    for name, digest in prior_hashes.items():
        old._require(old._sha(old._canonical(directory.read(name))) == digest, "batch_output_changed")
    epoch = int(old.time.time())
    old._require(epoch >= claim["epoch"], "batch_clock")
    directory.write(marker + "-batch-complete.json", {"schema": SCHEMA,
        "claim_sha256": old._sha(old._canonical(claim)), "epoch": epoch, "outcome": outcome,
        "outputs": {name: old._sha(old._canonical(directory.read(name))) for name in sorted(outputs)},
        "result_sha256": old._sha(old._canonical(result))})
    directory.verify()


def _active(directory, plan, record, *, exclude=None):
    for candidate, _, _ in old.CELLS:
        stem = candidate + "-A1"
        if stem == exclude or stem + "-claim.json" not in directory.names():
            continue
        old._require(stem + "-terminal.json" in directory.names(), "another_attempt_active_or_ambiguous")
        _, _, _, compiled = old._attempt(directory, plan, record, candidate, 1)
        terminal = directory.read(stem + "-terminal.json")
        status = terminal.get("status")
        old._require(status in {"BuildError", "Completed.", "Runtime Error"}, "another_attempt_active_or_ambiguous")
        expected = compiled if status == "BuildError" else old._launch(directory, compiled, stem)
        expected = {**expected, "status": status}
        if status != "Completed.":
            evidence = terminal.get("failure_evidence")
            old._require(type(evidence) is dict and set(evidence) == {
                "terminal_category", "known_runtime_code", "known_runtime_code_sha256", "python_error_category",
                "raw_error_retained", "cause_authenticated"}
                and evidence["raw_error_retained"] is False and evidence["cause_authenticated"] is False,
                "another_attempt_active_or_ambiguous")
            expected["failure_evidence"] = evidence
        old._require(old._same(terminal, expected), "another_attempt_active_or_ambiguous")


def _capacity(directory, plan, _record, marker, _candidate):
    api = environment.guarded_client()
    old._read_project(directory, plan, api, marker + "-project", old.REFERENCE_PROJECT, idle=False)
    value = old._capacity(old._rpc(directory, plan, api, marker, "projects/nodes/read", {"projectId": old.REFERENCE_PROJECT}))
    directory.write(marker + "-valid.json", {"family_sha256": plan.family_sha256, **value})
    return {**value, "state": "available" if value["available_count"] else "wait"}


def _begin(directory, plan, record, marker, candidate):
    cell, item, stem = old._cell(plan, record, candidate, 1)
    api = environment.guarded_client()
    old._read_project(directory, plan, api, marker + "-capacity-reference", old.REFERENCE_PROJECT, idle=False)
    value = old._capacity(old._rpc(directory, plan, api, marker + "-capacity", "projects/nodes/read", {"projectId": old.REFERENCE_PROJECT}))
    directory.write(marker + "-capacity-valid.json", {"family_sha256": plan.family_sha256, **value})
    if not value["available_count"]:
        return {**value, "state": "wait"}
    directory.write(stem + "-claim.json", {**old._identity(plan, cell, stem),
        "prior_failure_sha256": None, "retry_justification_sha256": None})
    rows = old._rpc(directory, plan, api, marker + "-create-project", "projects/create",
        {"name": cell["project_name"], "language": "Py", "organizationId": old._organization(directory, plan)}).get("projects")
    old._require(type(rows) is list and len(rows) == 1, "created_project_count")
    project = old._project(rows[0], old._organization(directory, plan), cell)
    directory.write(candidate + "-project.json", {"family_sha256": plan.family_sha256,
        "candidate_id": candidate, "project_id": project})
    old._read_project(directory, plan, api, marker + "-owned-project", project, cell)
    old._prior_inventory(directory, plan, api, marker + "-prior-runs", cell, project, 1)
    rows = old._rpc(directory, plan, api, marker + "-initial-files", "files/read", {"projectId": project}).get("files")
    old._require(type(rows) is list and len(rows) <= 2 and all(type(row) is dict
        and type(row.get("projectId")) is int and row["projectId"] == project
        and row.get("name") in {"main.py", "research.ipynb"} for row in rows), "fresh_project_files")
    existing = [row["name"] for row in rows]
    old._require(len(existing) == len(set(existing)), "duplicate_cloud_file")
    if "research.ipynb" in existing:
        old._rpc(directory, plan, api, marker + "-delete-default-notebook", "files/delete", {"projectId": project, "name": "research.ipynb"})
    for index, entry in enumerate(item.source_files):
        old._rpc(directory, plan, api, f"{marker}-source-{index:02d}",
            "files/update" if entry.project_path in existing else "files/create",
            {"projectId": project, "name": entry.project_path, "content": entry.source_bytes.decode("ascii")})
    old._files(directory, plan, api, marker + "-source-readback", project, item)
    created = old._rpc(directory, plan, api, marker + "-compile-create", "compile/create", {"projectId": project})
    compile_id = old._id(created.get("compileId"))
    old._require(type(created.get("projectId", project)) is int and created.get("projectId", project) == project, "compile_project")
    receipt = {**old._identity(plan, cell, stem), "project_id": project, "compile_id": compile_id}
    directory.write(stem + "-compile.json", receipt)
    return receipt


def _compile(directory, plan, record, marker, candidate):
    _, _, stem, compiled = old._attempt(directory, plan, record, candidate, 1)
    response = old._rpc(directory, plan, environment.guarded_client(), marker, "compile/read",
        {"projectId": compiled["project_id"], "compileId": compiled["compile_id"]})
    state = response.get("state")
    old._require(response.get("compileId") == compiled["compile_id"]
        and type(response.get("projectId", compiled["project_id"])) is int
        and response.get("projectId", compiled["project_id"]) == compiled["project_id"]
        and state in {"InQueue", "Building", "BuildSuccess", "BuildError"}, "compile_status")
    result = {**compiled, "status": state}
    directory.write(marker + "-valid.json", result)
    if state == "BuildSuccess":
        directory.write(stem + "-compile-ready.json", result)
    elif state == "BuildError":
        result["failure_evidence"] = old._failure_evidence(response, "compile_error")
        directory.write(stem + "-terminal.json", result)
    return result


def _launch(directory, plan, record, marker, candidate):
    cell, item, stem, compiled = old._attempt(directory, plan, record, candidate, 1)
    api = environment.guarded_client()
    old._read_project(directory, plan, api, marker + "-project", compiled["project_id"], cell)
    old._files(directory, plan, api, marker + "-files", compiled["project_id"], item)
    value = old._capacity(old._rpc(directory, plan, api, marker + "-capacity", "projects/nodes/read", {"projectId": compiled["project_id"]}))
    directory.write(marker + "-capacity-valid.json", {"family_sha256": plan.family_sha256, **value})
    if not value["available_count"]:
        return {**value, "state": "wait"}
    name = f"{cell['project_name']} A1 {cell['projection_sha256'][:8]}"
    result = old._rpc(directory, plan, api, marker + "-backtest-create", "backtests/create",
        {"projectId": compiled["project_id"], "compileId": compiled["compile_id"], "backtestName": name}).get("backtest")
    old._require(type(result) is dict and type(result.get("projectId")) is int
        and result["projectId"] == compiled["project_id"] and result.get("name") == name
        and result.get("status") in BACKTEST_PENDING, "created_backtest")
    receipt = {**compiled, "backtest_id": old._id(result.get("backtestId")), "backtest_name": name}
    directory.write(stem + "-launch.json", receipt)
    return receipt


def _status(directory, plan, record, marker, candidate):
    _, _, stem, compiled = old._attempt(directory, plan, record, candidate, 1)
    launch = old._launch(directory, compiled, stem)
    response = old._rpc(directory, plan, environment.guarded_client(), marker, "backtests/list",
        {"projectId": launch["project_id"], "includeStatistics": False})
    rows = response.get("backtests")
    old._require(type(rows) is list and type(response.get("count")) is int
        and response["count"] == len(rows) == 1, "backtest_census")
    row = rows[0]
    # Proven list parsers treat a summary row's projectId as optional; when
    # present it must still be the exact launched project.
    old._require(type(row) is dict and ("projectId" not in row or (type(row["projectId"]) is int
        and row["projectId"] == launch["project_id"])) and row.get("backtestId") == launch["backtest_id"]
        and row.get("name") == launch["backtest_name"]
        and row.get("status") in BACKTEST_PENDING | BACKTEST_TERMINAL, "backtest_status")
    result = {**launch, "status": row["status"]}
    if row["status"] == "Runtime Error":
        result["failure_evidence"] = old._failure_evidence(row, "runtime_error")
    directory.write(marker + "-valid.json", result)
    if row["status"] in BACKTEST_TERMINAL:
        directory.write(stem + "-terminal.json", result)
    return result


def _read(directory, plan, record, marker, candidate):
    cell, item, stem, compiled = old._attempt(directory, plan, record, candidate, 1)
    launch = old._launch(directory, compiled, stem)
    old._require(callable(getattr(old.runtime, "validate_result_statistics", None)), "result_validator_unavailable")
    directory.write(stem + "-result-read-claim.json", {**launch, "status": "Completed."})
    api = environment.guarded_client()
    old._read_project(directory, plan, api, marker + "-project", launch["project_id"], cell)
    old._files(directory, plan, api, marker + "-source", launch["project_id"], item)
    row = old._rpc(directory, plan, api, marker + "-aggregate-read", "backtests/read",
        {"projectId": launch["project_id"], "backtestId": launch["backtest_id"]}).get("backtest")
    old._require(type(row) is dict and type(row.get("projectId")) is int
        and row["projectId"] == launch["project_id"] and row.get("backtestId") == launch["backtest_id"]
        and row.get("name") == launch["backtest_name"] and row.get("status") == "Completed.", "result_identity")
    stats = row.get("statistics")
    old._require(type(stats) is dict, "result_statistics")
    selected = {name: stats.get(name) for name in (old.runtime.META_STATISTIC, old.runtime.MONTHLY_STATISTIC)}
    old._require(all(type(value) is str and 0 < len(value.encode("utf-8")) <= old.runtime.MAX_STATISTIC_BYTES
        for value in selected.values()), "aggregate_bound")
    directory.write(stem + "-retained-statistics.json", {"family_sha256": plan.family_sha256, "statistics": selected})
    validated = old.runtime.validate_result_statistics(selected, expected_profile=old._profile(item))
    result = {**launch, "status": "Completed.", "cell_completed": True,
        "family_comparable": False, "result_cell": 1, "statistics": validated}
    directory.write(stem + "-result.json", result)
    return result


def _summarize(directory, plan, record):
    completed, paths, geometry = [], set(), set()
    for candidate, _, _ in old.CELLS:
        name = candidate + "-A1-result.json"
        if name not in directory.names():
            continue
        value = directory.read(name)
        _, item, stem, compiled = old._attempt(directory, plan, record, candidate, 1)
        launch = old._launch(directory, compiled, stem)
        old._require(old._same(directory.read(stem + "-terminal.json"), {**launch, "status": "Completed."}), "not_completed")
        retained = directory.read(stem + "-retained-statistics.json")
        old._require(set(retained) == {"family_sha256", "statistics"}
            and retained["family_sha256"] == plan.family_sha256, "result_receipt")
        stats = old.runtime.validate_result_statistics(retained["statistics"], expected_profile=old._profile(item))
        expected = {**launch, "status": "Completed.", "cell_completed": True,
            "family_comparable": False, "result_cell": 1, "statistics": stats}
        old._require(old._same(value, expected), "result_changed")
        meta = stats["meta"]
        paths.add(meta["common_source_path_sha256"])
        geometry.add((meta["package_sha256"], meta["lineage_sha256"], meta["decision_count"], meta["evaluation_session_count"]))
        completed.append(candidate)
    old._require(completed == [row[0] for row in old.CELLS[:len(completed)]], "candidate_order")
    return {"family_sha256": plan.family_sha256, "completed_cells": completed,
        "family_complete": len(completed) == 6,
        "family_comparable": len(completed) == 6 and len(paths) == len(geometry) == 1,
        "comparability_mismatch": len(paths) > 1 or len(geometry) > 1,
        "actual_action_exit_confirmation_required": True,
        "paper_or_live_ready": False, "formal_forward_ready": False}


def _preconditions(directory, plan, record, operation, candidate):
    if operation in {"capacity", "summarize"}:
        return
    cell, _, stem = old._cell(plan, record, candidate, 1)
    names = directory.names()
    if operation == "begin":
        old._require(stem + "-claim.json" not in names and candidate + "-project.json" not in names, "attempt_spent")
        _active(directory, plan, record)
        completed = _summarize(directory, plan, record)["completed_cells"]
        old._require(len(completed) < 6 and candidate == old.CELLS[len(completed)][0], "candidate_order")
        return
    _, _, _, compiled = old._attempt(directory, plan, record, candidate, 1)
    if operation == "compile":
        old._require(stem + "-compile-ready.json" not in names and stem + "-terminal.json" not in names, "compile_terminal")
    elif operation == "launch":
        old._require(stem + "-launch.json" not in names and not any(
            name.startswith(stem + "-") and "backtest-create" in name for name in names), "attempt_spent")
        _active(directory, plan, record, exclude=stem)
        old._require(old._same(directory.read(stem + "-compile-ready.json"), {**compiled, "status": "BuildSuccess"})
            and stem + "-terminal.json" not in names, "compile_not_ready")
    else:
        launch = old._launch(directory, compiled, stem)
        if operation == "status":
            old._require(stem + "-terminal.json" not in names, "already_terminal")
        else:
            old._require(stem + "-result-read-claim.json" not in names, "attempt_spent")
            old._require(old._same(directory.read(stem + "-terminal.json"), {**launch, "status": "Completed."}), "not_completed")


def dispatch(operation, plan, candidate_id=None, attempt=None, *, expected_family_sha256, expected_receipt_sha256):
    """The only public lifecycle entry; every call requires a separate run freeze."""
    old._require(type(operation) is str and operation in OPERATIONS, "endpoint")
    old._digest(expected_receipt_sha256)
    if operation in {"capacity", "summarize"}:
        old._require(candidate_id is None and attempt is None, "candidate_attempt")
    else:
        old._require(type(candidate_id) is str and candidate_id in {row[0] for row in old.CELLS}
            and type(attempt) is int and attempt == 1, "candidate_attempt")
    old._require(fcntl is not None, "native_lock_unavailable")
    environment.require_safe_environment()
    with old._session(plan, expected_family_sha256) as (directory, record), _locked(directory):
        recovery.require_admission(directory, plan, record, expected_receipt_sha256)
        batches = _state(directory, plan, record, expected_receipt_sha256)
        _preconditions(directory, plan, record, operation, candidate_id)
        if operation == "summarize":
            result = _summarize(directory, plan, record)
            marker = None
        else:
            marker, claim, before = _batch(directory, plan, record, operation, candidate_id, expected_receipt_sha256, batches)
            function = {"capacity": _capacity, "begin": _begin, "compile": _compile,
                        "launch": _launch, "status": _status, "read": _read}[operation]
            result = function(directory, plan, record, marker, candidate_id)
        # Do not mark the batch complete when any postcheck fails. Terminal files
        # possibly written earlier remain evidence, but cannot release this fence.
        environment.require_safe_environment()
        fresh = old.require_family(plan, expected_family_sha256)
        old._bound(directory, plan, fresh)
        recovery.require_admission(directory, plan, fresh, expected_receipt_sha256)
        directory.verify()
        if marker is not None:
            _finish(directory, marker, claim, before, result)
        return result
