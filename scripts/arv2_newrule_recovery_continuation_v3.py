"""Additive six-cell continuation after separately admitted V3 storage recovery.

The frozen upload and its legacy receipt remain untouched. Capacity and begin
retain their original bodies except that the new receipt is authenticated in
place of `_uploaded`. Other lifecycle methods are delegated only after the
same V3 admission check; the spent V1 recovery supplies no continuation proof.
No global patch, invented upload-valid receipt, altered
candidate, reset attempt, changed projection, or automatic retry is involved.

Successful actual recovery exit is an external observed prerequisite: the
separately frozen operational caller must bind it and this exact receipt pin.
An import or receipt alone supplies no operational authority. The frozen RPC
response/ambiguity limitations remain unchanged.
"""
from __future__ import annotations

from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
from scripts import arv2_newrule_storage_recovery_v3 as recovery

SCHEMA = "arv2-newrule-storage-recovery-continuation-v3"
FROZEN_SUBMISSION_SHA256 = "cfd2456f2835bb1a4d2c04d6bb60a633b537a2af276a478ad3bfa5f2bc348d4f"
OPERATIONS = ("capacity", "begin", "compile", "launch", "status", "read", "summarize")


def capacity_once(plan, *, expected_family_sha256, expected_receipt_sha256):
    """Original bounded capacity observation with separate receipt admission."""
    with old._session(plan, expected_family_sha256) as (directory, record):
        recovery.require_admission(directory, plan, record, expected_receipt_sha256)
        marker = old._next(directory, "capacity", old.STATUS_INTERVAL, old.STATUS_POLLS)
        api = old._client()
        old._read_project(directory, plan, api, marker + "-project", old.REFERENCE_PROJECT, idle=False)
        value = old._capacity(old._rpc(directory, plan, api, marker, "projects/nodes/read", {"projectId": old.REFERENCE_PROJECT}))
        directory.write(marker + "-valid.json", {"family_sha256": plan.family_sha256, **value})
        return {**value, "state": "available" if value["available_count"] else "wait"}


def begin_attempt(plan, candidate_id, attempt, *, expected_family_sha256, expected_receipt_sha256,
                  prior_failure_sha256=None, retry_justification_sha256=None):
    """Original one-claim mutation/compile path with separate admission only."""
    with old._session(plan, expected_family_sha256) as (directory, record):
        recovery.require_admission(directory, plan, record, expected_receipt_sha256)
        cell, item, stem = old._cell(plan, record, candidate_id, attempt)
        old._active(directory)
        names = directory.names()
        old._require(stem + "-claim.json" not in names, "attempt_spent")
        if attempt == 1:
            old._require(prior_failure_sha256 is None and retry_justification_sha256 is None
                     and candidate_id + "-project.json" not in names, "first_attempt")
        else:
            old._digest(prior_failure_sha256)
            old._digest(retry_justification_sha256)
            prior = directory.read(f"{candidate_id}-A{attempt - 1}-terminal.json")
            old._require(prior.get("status") in {"Runtime Error", "BuildError"}
                     and old._sha(old._canonical(prior)) == prior_failure_sha256, "retry_requires_failed_prior")
        api = old._client()
        marker = old._next(directory, stem + "-capacity", old.STATUS_INTERVAL, old.STATUS_POLLS)
        old._read_project(directory, plan, api, marker + "-reference", old.REFERENCE_PROJECT, idle=False)
        capacity = old._capacity(old._rpc(directory, plan, api, marker, "projects/nodes/read", {"projectId": old.REFERENCE_PROJECT}))
        directory.write(marker + "-valid.json", {"family_sha256": plan.family_sha256, **capacity})
        old._require(capacity["available_count"] > 0, "capacity_wait")
        claim = {**old._identity(plan, cell, stem), "prior_failure_sha256": prior_failure_sha256,
                 "retry_justification_sha256": retry_justification_sha256}
        directory.write(stem + "-claim.json", claim)
        if attempt == 1:
            rows = old._rpc(directory, plan, api, stem + "-create-project", "projects/create",
                {"name": cell["project_name"], "language": "Py", "organizationId": old._organization(directory, plan)}).get("projects")
            old._require(type(rows) is list and len(rows) == 1, "created_project_count")
            project_id = old._project(rows[0], old._organization(directory, plan), cell)
            directory.write(candidate_id + "-project.json", {"family_sha256": plan.family_sha256,
                "candidate_id": candidate_id, "project_id": project_id})
        else:
            saved = directory.read(candidate_id + "-project.json")
            old._require(saved.get("family_sha256") == plan.family_sha256 and saved.get("candidate_id") == candidate_id, "saved_project")
            project_id = old._number(saved.get("project_id"))
        old._read_project(directory, plan, api, stem + "-owned-project", project_id, cell)
        old._prior_inventory(directory, plan, api, stem + "-prior-runs", cell, project_id, attempt)
        if attempt == 1:
            rows = old._rpc(directory, plan, api, stem + "-initial-files", "files/read", {"projectId": project_id}).get("files")
            old._require(type(rows) is list and len(rows) <= 2 and all(type(row) is dict
                and type(row.get("projectId")) is int and row["projectId"] == project_id
                and row.get("name") in {"main.py", "research.ipynb"} for row in rows), "fresh_project_files")
            existing = [row["name"] for row in rows]
            old._require(len(existing) == len(set(existing)), "duplicate_cloud_file")
            if "research.ipynb" in existing:
                old._rpc(directory, plan, api, stem + "-delete-default-notebook", "files/delete", {"projectId": project_id, "name": "research.ipynb"})
            for index, entry in enumerate(item.source_files):
                old._rpc(directory, plan, api, f"{stem}-source-{index:02d}",
                    "files/update" if entry.project_path in existing else "files/create",
                    {"projectId": project_id, "name": entry.project_path, "content": entry.source_bytes.decode("ascii")})
        old._files(directory, plan, api, stem + "-source-readback", project_id, item)
        created = old._rpc(directory, plan, api, stem + "-compile-create", "compile/create", {"projectId": project_id})
        compile_id = old._id(created.get("compileId"))
        old._require(type(created.get("projectId", project_id)) is int
                 and created.get("projectId", project_id) == project_id, "compile_project")
        receipt = {**old._identity(plan, cell, stem), "project_id": project_id, "compile_id": compile_id}
        directory.write(stem + "-compile.json", receipt)
        return receipt


def dispatch(operation, plan, candidate_id=None, attempt=None, *,
             expected_family_sha256, expected_receipt_sha256,
             prior_failure_sha256=None, retry_justification_sha256=None):
    """Authenticate separate recovery admission before a fixed lifecycle call.

No prepare/discovery/upload route exists. The original method reauthenticates
the family and original per-attempt state again; no sidecar proof overrides
its claims, source readback, status, result, or attempt-limit checks.
"""
    old._require(type(operation) is str and operation in OPERATIONS, "endpoint")
    old._digest(expected_receipt_sha256)
    if operation in {"capacity", "summarize"}:
        old._require(candidate_id is None and attempt is None, "candidate_attempt")
    else:
        old._require(type(candidate_id) is str and candidate_id in {row[0] for row in old.CELLS}
                     and type(attempt) is int and 1 <= attempt <= 3, "candidate_attempt")
    if operation != "begin":
        old._require(prior_failure_sha256 is None and retry_justification_sha256 is None, "first_attempt")
    common = dict(expected_family_sha256=expected_family_sha256,
                  expected_receipt_sha256=expected_receipt_sha256)
    if operation == "capacity":
        return capacity_once(plan, **common)
    if operation == "begin":
        return begin_attempt(plan, candidate_id, attempt, **common,
            prior_failure_sha256=prior_failure_sha256,
            retry_justification_sha256=retry_justification_sha256)
    with old._session(plan, expected_family_sha256) as (directory, record):
        recovery.require_admission(directory, plan, record, expected_receipt_sha256)
    common = dict(expected_family_sha256=expected_family_sha256)
    if operation == "compile":
        return old.poll_compile_once(plan, candidate_id, attempt, **common)
    if operation == "launch":
        return old.launch_compiled(plan, candidate_id, attempt, **common)
    if operation == "status":
        return old.poll_status_once(plan, candidate_id, attempt, **common)
    if operation == "read":
        return old.read_result_once(plan, candidate_id, attempt, **common)
    return old.summarize_family(plan, **common)
