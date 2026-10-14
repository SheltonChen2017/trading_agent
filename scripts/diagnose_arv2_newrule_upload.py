"""One-use OFFLINE census of the fixed failed new-rule upload's markers.

Launch only under the separately frozen native sandbox-exec deny-network
policy. This never calls an old operation, credentials, or QC. Intent markers
precede transport and therefore cannot prove dispatch. Successful-response
markers do not establish object-properties metadata acceptance. The original
upload's observed exit 2 is external evidence, not reconstructed here.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace

ROOT = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_arv2_newrule_comparison as frozen

helpers = frozen.helpers
SOURCE = ROOT / "scripts/diagnose_arv2_newrule_upload.py"
FROZEN_CALLER_SHA256 = "533c1ebf520e9ebf836c78067b9b1480eccf49cfb01aaeb240e3a73b77087d05"
FAMILY_SHA256 = "8b8ee913dcfb5ad37f4748ea70db4fcbd6ff15580e52cd160bccf2b37e10a9e5"
CONTROL = ROOT / "artifacts/analyst_revisions_v2/newrule_comparison_qc/R298-R303-20261013"
CLAIM, REPORT = "upload-diagnostic-v1-claim.json", "upload-diagnostic-v1-report.json"
DEADLINE_SECONDS, MAX_INVENTORY, MAX_OUTPUT_BYTES = 120, 128, 16 * 1024
SCHEMA = "arv2-newrule-upload-marker-diagnostic-v1"
PROFILE = helpers.canonical_json_bytes({
    "schema": SCHEMA, "root": str(ROOT), "branch": frozen.BRANCH,
    "python": str(frozen.PYTHON), "control": str(CONTROL),
    "claim": CLAIM, "report": REPORT, "family_sha256": FAMILY_SHA256,
    "package_sha256": frozen.PACKAGE_SHA256, "lineage_sha256": frozen.LINEAGE_SHA256,
    "frozen_caller_sha256": FROZEN_CALLER_SHA256,
    "source_pins": dict(frozen.SOURCE_PINS), "new_source_pins": dict(frozen.NEW_SOURCE_PINS),
    "deadline_seconds": DEADLINE_SECONDS, "max_inventory": MAX_INVENTORY,
    "max_output_bytes": MAX_OUTPUT_BYTES,
    "native_network_denial": "required_external_sandbox-exec_deny_network",
    "marker_scope": "externally_pinned_family_preparation_claim_upload_claim_authenticate_inventory_indexed_markers",
    "organization_values_or_raw_responses_read": False,
    "private_package_or_lineage_payloads_read": False,
    "operational_family_plan_minted": False,
    "intent_is_proof_of_dispatch": False, "original_upload_accepted": False,
    "changes_original_exit": False, "qc_contact_authorized": False,
    "formal_forward_ready": False, "point_in_time_proven": False, "paper_or_live_ready": False,
})
PROFILE_SHA256 = hashlib.sha256(PROFILE).hexdigest()


class DiagnosticRefusal(ValueError):
    pass


def _require(value):
    if not value:
        raise DiagnosticRefusal("diagnostic_refused")


def _same(left, right):
    return type(left) is type(right) and helpers.canonical_json_bytes(left) == helpers.canonical_json_bytes(right)


def _preflight(head, caller, deadline):
    _require(Path.cwd() == ROOT and ROOT.resolve() == ROOT
             and Path(__file__).absolute() == SOURCE)
    helpers.require_sha256(caller, "caller")
    # Stateless source/host checks only; never frozen.run/_operation/summarize.
    frozen._preflight(SimpleNamespace(operation="summarize", expected_head=head,
        caller_sha256=FROZEN_CALLER_SHA256, candidate=None, attempt=None,
        family_sha256=FAMILY_SHA256, prior_failure_sha256=None,
        justification_sha256=None), deadline)
    _require(helpers._source_digest(SOURCE) == caller)
    helpers._remaining(deadline)


def _family_binding(directory, submission, deadline):
    # _Directory.read rejects duplicate keys, nonfinite values, noncanonical
    # bytes and unsafe held/named files. Verify the external content digest
    # before trusting any inventory field. This is not a new FamilyPlan.
    record = directory.read("family.json")
    _require(type(record) is dict and hashlib.sha256(
        helpers.canonical_json_bytes(record)).hexdigest() == FAMILY_SHA256)
    _require(_same(directory.read("preparation-claim.json"),
        {"schema": submission.SCHEMA, "family_sha256": FAMILY_SHA256}))
    _require(record.get("schema") == submission.SCHEMA
        and record.get("package_sha256") == frozen.PACKAGE_SHA256
        and record.get("lineage_sha256") == frozen.LINEAGE_SHA256
        and record.get("submission_profile_sha256") == submission.PROFILE_SHA256
        and record.get("formal_forward_ready") is False
        and record.get("paper_or_live_ready") is False)
    inventory = record.get("upload_inventory")
    _require(type(inventory) is list and 0 < len(inventory) <= MAX_INVENTORY)
    keys, byte_count = set(), 0
    for index, row in enumerate(inventory):
        _require(type(row) is list and len(row) == 4)
        key, digest, size, activation = row
        _require(type(key) is str and 0 < len(key) <= 512 and key.isascii()
            and key not in keys and type(digest) is str
            and re.fullmatch(r"[0-9a-f]{64}", digest) is not None
            and type(size) is int and 0 < size <= submission.compact.MAX_UPLOAD_OBJECT_BYTES
            and type(activation) is bool and activation is (index == len(inventory)-1))
        keys.add(key)
        byte_count += size
    _require(_same(inventory[-1], [submission.ACTIVATION_KEY, submission.ACTIVATION_SHA256,
        submission.ACTIVATION_BYTES, True]) and byte_count == submission.UPLOAD_BYTES)
    helpers._remaining(deadline)
    return record


def _marker(directory, name, endpoint, *, observed, previous_epoch):
    value = directory.read(name)
    expected = {"family_sha256", "epoch", "response_sha256"} if observed else {
        "family_sha256", "epoch", "endpoint", "request_sha256"}
    _require(type(value) is dict and set(value) == expected
             and type(value["family_sha256"]) is str and value["family_sha256"] == FAMILY_SHA256
             and type(value["epoch"]) is int and previous_epoch <= value["epoch"] < 10**11)
    digest = value["response_sha256" if observed else "request_sha256"]
    _require(type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest) is not None)
    if not observed:
        _require(type(value["endpoint"]) is str and value["endpoint"] == endpoint)
    return value["epoch"]


def _census(directory, record, deadline):
    inventory = record.get("upload_inventory")
    _require(type(inventory) is list and 0 < len(inventory) <= MAX_INVENTORY)
    digest = hashlib.sha256(helpers.canonical_json_bytes(inventory)).hexdigest()
    _require(record.get("upload_inventory_sha256") == digest)
    # The canonical, externally pinned family supplies and validates this census;
    # no object key, organization value, payload or response is exported.
    names = set(directory.names())
    claim = directory.read("upload-claim.json")
    _require(_same(claim, {"family_sha256": FAMILY_SHA256}))
    slots = [(None, "authenticate", "upload-authenticate")]
    for index in range(len(inventory)):
        slots.extend(((index, "object/set", f"upload-{index:03d}"),
                      (index, "object/properties", f"upload-{index:03d}-properties")))
    permitted = {"upload-claim.json", "upload-valid.json", CLAIM, REPORT}
    permitted.update(stem + suffix for _, _, stem in slots
                     for suffix in ("-intent.json", "-observed.json"))
    _require(all(not name.startswith("upload-") or name in permitted for name in names))
    groups = {endpoint: {"intent_indices": [], "observed_success_indices": [],
                         "missing_observation_indices": []}
              for endpoint in ("object/set", "object/properties")}
    auth = None
    previous_epoch, blocked, last = 0, False, None
    intent_count = observed_count = 0
    for index, endpoint, stem in slots:
        helpers._remaining(deadline)
        intent, observed = stem + "-intent.json" in names, stem + "-observed.json" in names
        _require(not observed or intent)
        _require(not blocked or not (intent or observed))
        if intent:
            previous_epoch = _marker(directory, stem + "-intent.json", endpoint,
                observed=False, previous_epoch=previous_epoch)
            intent_count += 1
            last = {"endpoint": endpoint, "index": index}
        if observed:
            previous_epoch = _marker(directory, stem + "-observed.json", endpoint,
                observed=True, previous_epoch=previous_epoch)
            observed_count += 1
        if endpoint == "authenticate":
            auth = {"intent_present": intent, "observed_success_present": observed,
                    "missing_observation": intent and not observed}
        else:
            group = groups[endpoint]
            if intent:
                group["intent_indices"].append(index)
            if observed:
                group["observed_success_indices"].append(index)
            elif intent:
                group["missing_observation_indices"].append(index)
        blocked = blocked or not observed
    # Only its name is inspected. The old upload receipt is never read or
    # promoted into renewed upload authority by this diagnostic.
    valid_present = "upload-valid.json" in names
    _require(not valid_present or observed_count == len(slots))
    _require(set(directory.names()) == names)
    return {"inventory_count": len(inventory), "upload_inventory_sha256": digest,
        "authenticate": auth, "endpoint_census": groups,
        "retained_intent_count": intent_count, "observed_success_count": observed_count,
        "missing_observation_count": intent_count - observed_count,
        "last_retained_request_intent": last, "actual_last_dispatch_unknown": True,
        "request_count_unknown": True, "successful_response_is_properties_validation": False,
        "original_upload_valid_marker_present": valid_present,
        "original_upload_valid_marker_content_read": False}


def _failure(exc, submission=None):
    if submission is not None and type(exc) is submission.NewruleSubmissionError:
        return submission.finite_failure(exc)
    for kind, label in ((DiagnosticRefusal, "diagnostic_refused"),
            (frozen.OperationRefusal, "preflight_refused"), (helpers.Deadline, "deadline"),
            (FileExistsError, "claim_or_report_exists"), (FileNotFoundError, "file_missing"),
            (PermissionError, "permission_error"), (OSError, "os_error"),
            (KeyboardInterrupt, "cancelled"), (SystemExit, "cancelled"),
            (ValueError, "value_error"), (TypeError, "type_error"),
            (KeyError, "key_error"), (MemoryError, "memory_error")):
        if type(exc) is kind:
            return label
    return "unknown_exception"


def _report(head, caller, started, stage, consumed, census, failure):
    return {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256,
        "expected_head": head, "caller_sha256": caller, "family_sha256": FAMILY_SHA256,
        "started_at": started, "finished_at": helpers._utc_now(), "stage": stage,
        "terminal": "marker_census_completed" if census is not None else "diagnostic_refused",
        "attempt_consumed": consumed, "failure_code": failure, "census": census,
        "diagnostic_only": True, "original_upload_accepted": False,
        "original_upload_exit_is_external_evidence": True, "changes_original_exit": False,
        "qc_contact_authorized": False, "point_in_time_proven": False,
        "formal_forward_ready": False, "paper_or_live_ready": False}


def _run(head, caller, deadline):
    stage, consumed, directory, submission = "preflight", False, None, None
    census, failure, claim = None, None, None
    started = helpers._utc_now()
    try:
        _preflight(head, caller, deadline)
        from research.analyst_revisions_v2_qc import newrule_comparison_submission as submission
        _require(submission.CONTROL == CONTROL)
        stage = "claim"
        directory = submission._Directory()
        consumed = None  # A partially created claim is ambiguous, never unspent.
        claim = {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256,
            "expected_head": head, "caller_sha256": caller, "family_sha256": FAMILY_SHA256,
            "claimed_at": helpers._utc_now(), "attempt_consumed": True}
        directory.write(CLAIM, claim)
        consumed = True
        helpers._remaining(deadline)
        stage = "family_authentication"
        record = _family_binding(directory, submission, deadline)
        _require(_same(directory.read(CLAIM), claim))
        stage = "marker_census"
        census = _census(directory, record, deadline)
        helpers._remaining(deadline)
    except BaseException as exc:
        census, failure = None, _failure(exc, submission)
    try:
        helpers._remaining(deadline)
        report = _report(head, caller, started, stage, consumed, census, failure)
        raw = helpers.canonical_json_bytes(report)
        _require(len(raw) <= MAX_OUTPUT_BYTES - 512)
        if consumed is True:
            _require(_same(directory.read(CLAIM), claim))
            directory.write(REPORT, report)
            _require(_same(directory.read(CLAIM), claim) and _same(directory.read(REPORT), report))
            envelope = {"report": report, "report_sha256": hashlib.sha256(raw).hexdigest(),
                        "report_bytes": len(raw), "report_published": True}
        else:
            envelope = {"report": report, "report_published": False}
        payload = helpers.canonical_json_bytes(envelope)
        _require(len(payload) <= MAX_OUTPUT_BYTES)
        helpers._remaining(deadline)
        print(payload.decode("ascii"))
        return 0 if census is not None else 2
    except BaseException:
        print('{"terminal":"diagnostic_publication_ambiguous","original_upload_accepted":false}')
        return 2
    finally:
        if directory is not None:
            directory.__exit__(None, None, None)


def run(head, caller):
    deadline = time.monotonic() + DEADLINE_SECONDS
    try:
        with helpers._alarm(deadline):
            return _run(head, caller, deadline)
    except BaseException:
        print('{"terminal":"diagnostic_parent_ambiguous","original_upload_accepted":false}')
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--caller-sha256", required=True)
    args = parser.parse_args(argv)
    return run(args.expected_head, args.caller_sha256)


if __name__ == "__main__":
    raise SystemExit(main())
