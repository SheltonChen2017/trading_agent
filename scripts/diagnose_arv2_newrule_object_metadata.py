"""One fresh, bounded properties-only diagnostic; never upload acceptance.

The prior upload and D8 marker census remain spent. This checks current object
metadata, not the historical response or write permission. No failed HTTP body,
metadata preview, object key, organization, credentials or raw error is emitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace
import urllib.error
import urllib.request

ROOT = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_arv2_newrule_comparison as frozen

helpers = frozen.helpers
SOURCE = ROOT / "scripts/diagnose_arv2_newrule_object_metadata.py"
D8_SOURCE = ROOT / "scripts/diagnose_arv2_newrule_upload.py"
FROZEN_CALLER_SHA256 = "533c1ebf520e9ebf836c78067b9b1480eccf49cfb01aaeb240e3a73b77087d05"
D8_SOURCE_SHA256 = "b8477fe9246b7355c9b10bec91a9ad6e6305fcd0a7e2d4f00f61da1c35ce9901"
D8_PROFILE_SHA256 = "1477c74d17fdb8da4d3f2e0e364a26c6ecb05e14f0802b5f684a475f5fcbdfa4"
D8_HEAD = "712e81b2f30f9f8dd7bb909cc6091c4688be5bee"
D8_REPORT_SHA256 = "982e2d4cbb04da4ce8e6f5f3cc20f2a79abf4999f3241b0fe6aad52d2372bb11"
D8_REPORT_BYTES = 1617
D8_REPORT = "upload-diagnostic-v1-report.json"
FAMILY_SHA256 = "8b8ee913dcfb5ad37f4748ea70db4fcbd6ff15580e52cd160bccf2b37e10a9e5"
ORGANIZATION_SHA256 = "a2d88859373df0f1fd59ede52b9b3945f847091b5fca3286841241536c38e880"
INVENTORY_SHA256 = "b35e1bb0dfc887d6d775a7dd89155a1e8a703ee2aad148aa69cab52b718359c8"
CONTROL = ROOT / "artifacts/analyst_revisions_v2/newrule_comparison_qc/R298-R303-20261013"
CLAIM = "metadata-diagnostic-v1-claim.json"
START = "metadata-diagnostic-v1-request-intent.json"
REPORT = "metadata-diagnostic-v1-report.json"
SCHEMA = "arv2-newrule-object-metadata-diagnostic-v1"
ENDPOINT, OBJECT_INDEX = "object/properties", 0
DEADLINE_SECONDS, REQUEST_SECONDS = 90, 30
MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, MAX_OUTPUT_BYTES = 4096, 1024 * 1024, 16 * 1024
PROFILE = helpers.canonical_json_bytes({
    "schema": SCHEMA, "root": str(ROOT), "branch": frozen.BRANCH,
    "python": str(frozen.PYTHON), "control": str(CONTROL),
    "claim": CLAIM, "request_intent": START, "report": REPORT,
    "family_sha256": FAMILY_SHA256, "organization_sha256": ORGANIZATION_SHA256,
    "inventory_sha256": INVENTORY_SHA256, "endpoint": ENDPOINT, "object_index": OBJECT_INDEX,
    "d8_source_sha256": D8_SOURCE_SHA256, "d8_profile_sha256": D8_PROFILE_SHA256,
    "d8_head": D8_HEAD, "d8_report_sha256": D8_REPORT_SHA256, "d8_report_bytes": D8_REPORT_BYTES,
    "frozen_caller_sha256": FROZEN_CALLER_SHA256,
    "source_pins": dict(frozen.SOURCE_PINS), "new_source_pins": dict(frozen.NEW_SOURCE_PINS),
    "deadline_seconds": DEADLINE_SECONDS, "request_seconds": REQUEST_SECONDS,
    "max_request_bytes": MAX_REQUEST_BYTES, "max_response_bytes": MAX_RESPONSE_BYTES,
    "max_output_bytes": MAX_OUTPUT_BYTES, "request_limit": 1,
    "redirects_proxies_retries": False, "failed_response_body_read": False,
    "diagnostic_only": True, "original_upload_accepted": False,
    "historical_failure_cause_reconstructed": False, "md5_content_authentication": False,
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
    _require(Path.cwd() == ROOT and ROOT.resolve() == ROOT and Path(__file__).absolute() == SOURCE)
    helpers.require_sha256(caller, "caller")
    frozen._preflight(SimpleNamespace(operation="summarize", expected_head=head,
        caller_sha256=FROZEN_CALLER_SHA256, candidate=None, attempt=None,
        family_sha256=FAMILY_SHA256, prior_failure_sha256=None, justification_sha256=None), deadline)
    _require(helpers._source_digest(D8_SOURCE) == D8_SOURCE_SHA256
        and helpers._source_digest(SOURCE) == caller)
    helpers._remaining(deadline)


def _d8_binding(directory, record, d8):
    value = directory.read(D8_REPORT)  # strict canonical/duplicate/nonfinite and held/named checks
    raw = helpers.canonical_json_bytes(value)
    _require(len(raw) == D8_REPORT_BYTES and hashlib.sha256(raw).hexdigest() == D8_REPORT_SHA256)
    inventory = record["upload_inventory"]
    _require(len(inventory) == 6 and record["upload_inventory_sha256"] == INVENTORY_SHA256
        and hashlib.sha256(helpers.canonical_json_bytes(inventory)).hexdigest() == INVENTORY_SHA256)
    census = {"inventory_count": 6, "upload_inventory_sha256": INVENTORY_SHA256,
        "authenticate": {"intent_present": True, "observed_success_present": True, "missing_observation": False},
        "endpoint_census": {
            "object/set": {"intent_indices": [0], "observed_success_indices": [], "missing_observation_indices": [0]},
            "object/properties": {"intent_indices": [], "observed_success_indices": [], "missing_observation_indices": []}},
        "retained_intent_count": 2, "observed_success_count": 1, "missing_observation_count": 1,
        "last_retained_request_intent": {"endpoint": "object/set", "index": 0},
        "actual_last_dispatch_unknown": True, "request_count_unknown": True,
        "successful_response_is_properties_validation": False,
        "original_upload_valid_marker_present": False, "original_upload_valid_marker_content_read": False}
    expected = {"schema": d8.SCHEMA, "profile_sha256": D8_PROFILE_SHA256,
        "expected_head": D8_HEAD, "caller_sha256": D8_SOURCE_SHA256, "family_sha256": FAMILY_SHA256,
        "started_at": value.get("started_at"), "finished_at": value.get("finished_at"),
        "stage": "marker_census", "terminal": "marker_census_completed", "attempt_consumed": True,
        "failure_code": None, "census": census, "diagnostic_only": True,
        "original_upload_accepted": False, "original_upload_exit_is_external_evidence": True,
        "changes_original_exit": False, "qc_contact_authorized": False,
        "point_in_time_proven": False, "formal_forward_ready": False, "paper_or_live_ready": False}
    _require(_same(value, expected) and "upload-valid.json" not in directory.names())
    return inventory[OBJECT_INDEX]


def _organization(directory, submission):
    expected = {"family_sha256": FAMILY_SHA256, "reference_project_id": submission.REFERENCE_PROJECT}
    _require(_same(directory.read("organization-claim.json"), expected))
    value = directory.read("organization.json")
    org = value.get("organization_id")
    _require(type(org) is str and re.fullmatch(r"[0-9a-f]{32}", org) is not None
        and hashlib.sha256(org.encode("ascii")).hexdigest() == ORGANIZATION_SHA256
        and _same(value, dict(expected, organization_id=org, organization_sha256=ORGANIZATION_SHA256)))
    return org


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def _transport(api, submission, body, state, deadline):
    _require(type(body) is bytes and len(body) <= MAX_REQUEST_BYTES
        and state["attempted_request_count"] == 0)
    url = submission.API_BASE + "/" + ENDPOINT
    headers = submission.build_auth_headers(api._credentials, api._clock())
    headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    opener = _opener()
    timeout = min(REQUEST_SECONDS, helpers._remaining(deadline))
    state["attempted_request_count"] = 1  # attempted dispatch, not measured server contact
    response = None
    try:
        try:
            response = opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            response = exc
        status = response.code
        _require(type(status) is int and 100 <= status <= 599 and response.geturl() == url)
        state["http_status"] = status
        helpers._remaining(deadline)
        if not 200 <= status < 300:
            return None  # Never read a failed response body, including HTTPError.
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        _require(type(raw) is bytes and len(raw) <= MAX_RESPONSE_BYTES)
        helpers._remaining(deadline)
        return raw
    finally:
        if response is not None:
            response.close()


def _json(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            _require(key not in result)
            result[key] = value
        return result
    def constant(_):
        raise DiagnosticRefusal("diagnostic_refused")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)


def _error_category(errors):
    _require(type(errors) is list and len(errors) <= 8
        and all(type(error) is str and len(error) <= 512 for error in errors))
    # Exact finite public phrases only. No substring guesses, unknown hashing,
    # raw exceptions or provider error strings cross the output boundary.
    phrases = {
        "permission denied": "permission", "access denied": "permission", "unauthorized": "permission",
        "object not found": "not_found", "not found": "not_found",
        "quota exceeded": "quota", "storage quota exceeded": "quota",
        "subscription required": "subscription", "subscription expired": "subscription"}
    labels = {phrases.get(error.strip().lower(), "unknown") for error in errors}
    return next(iter(labels)) if len(labels) == 1 else "unknown"


def _observation(raw, row):
    result = {"response_schema_valid": None, "api_success": None, "metadata_schema_valid": None,
        "key_matches": None, "size_matches": None, "md5_well_formed": None, "error_category": "unknown"}
    if raw is None:
        return result
    value = _json(raw)
    _require(type(value) is dict and set(value) <= {"success", "errors", "metadata"}
        and type(value.get("success")) is bool)
    category = _error_category(value.get("errors", []))
    result.update(response_schema_valid=True, api_success=value["success"], error_category=category)
    if not value["success"]:
        _require("metadata" not in value or value["metadata"] is None)
        return result
    metadata = value.get("metadata")
    _require(type(metadata) is dict and {"key", "size", "md5"} <= set(metadata)
        and set(metadata) <= {"key", "modified", "created", "size", "md5", "mime", "preview"})
    key, size, md5 = metadata["key"], metadata["size"], metadata["md5"]
    _require(type(key) is str and 0 < len(key) <= 512 and key.isascii()
        and type(size) is int and 0 <= size <= 2**63-1 and type(md5) is str and len(md5) <= 128)
    result.update(metadata_schema_valid=True, key_matches=key == row[0], size_matches=size == row[2],
        md5_well_formed=re.fullmatch(r"[0-9a-fA-F]{32}", md5) is not None)
    return result


def _failure(exc, submission):
    if submission is not None and type(exc) is submission.NewruleSubmissionError:
        return submission.finite_failure(exc)
    for kind, label in ((DiagnosticRefusal, "diagnostic_refused"),
        (frozen.OperationRefusal, "preflight_refused"), (helpers.Deadline, "deadline"),
        (FileExistsError, "claim_or_report_exists"), (FileNotFoundError, "file_missing"),
        (PermissionError, "permission_error"), (OSError, "os_error"),
        (urllib.error.URLError, "transport_error"), (TimeoutError, "transport_timeout"),
        (json.JSONDecodeError, "response_json"), (UnicodeDecodeError, "response_encoding"),
        (KeyboardInterrupt, "cancelled"), (SystemExit, "cancelled"),
        (ValueError, "value_error"), (TypeError, "type_error"), (KeyError, "key_error"),
        (MemoryError, "memory_error"), (RecursionError, "response_depth")):
        if type(exc) is kind:
            return label
    return "unknown_exception"


def _safe_pin(value, length):
    return value if type(value) is str and re.fullmatch(r"[0-9a-f]{%d}" % length, value) else None


def _run(head, caller, deadline):
    stage, consumed, directory, submission = "preflight", False, None, None
    observation, failure, claim = None, None, None
    state = {"attempted_request_count": 0, "http_status": None}
    started = helpers._utc_now()
    try:
        _preflight(head, caller, deadline)
        from scripts import diagnose_arv2_newrule_upload as d8
        from research.analyst_revisions_v2_qc import newrule_comparison_submission as submission
        _require(submission.CONTROL == CONTROL and d8.PROFILE_SHA256 == D8_PROFILE_SHA256)
        stage = "claim"
        directory = submission._Directory()
        consumed = None
        claim = {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256,
            "expected_head": head, "caller_sha256": caller, "family_sha256": FAMILY_SHA256,
            "claimed_at": helpers._utc_now(), "attempt_consumed": True}
        directory.write(CLAIM, claim)
        consumed = True
        stage = "retained_evidence_authentication"
        record = d8._family_binding(directory, submission, deadline)
        row = _d8_binding(directory, record, d8)
        org = _organization(directory, submission)
        _require(_same(directory.read(CLAIM), claim))
        body = helpers.canonical_json_bytes({"organizationId": org, "key": row[0]})
        _require(len(body) <= MAX_REQUEST_BYTES)
        stage = "request_intent"
        directory.write(START, {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256,
            "family_sha256": FAMILY_SHA256, "endpoint": ENDPOINT, "object_index": OBJECT_INDEX})
        helpers._remaining(deadline)
        stage = "credentials"
        api = submission._client()
        stage = "properties_request"
        raw = _transport(api, submission, body, state, deadline)
        stage = "response_validation"
        observation = _observation(raw, row)
        helpers._remaining(deadline)
        _require(_same(d8._family_binding(directory, submission, deadline), record)
            and _same(_d8_binding(directory, record, d8), row)
            and _organization(directory, submission) == org)
        stage = "diagnostic_completed"
    except BaseException as exc:
        observation, failure = None, _failure(exc, submission)
    try:
        helpers._remaining(deadline)
        report = {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256,
            "expected_head": _safe_pin(head, 40), "caller_sha256": _safe_pin(caller, 64),
            "family_sha256": FAMILY_SHA256, "started_at": started, "finished_at": helpers._utc_now(),
            "stage": stage, "terminal": "metadata_observation_completed" if observation is not None else "diagnostic_refused",
            "attempt_consumed": consumed, "failure_code": failure, **state, "observation": observation,
            "diagnostic_only": True, "original_upload_accepted": False, "changes_original_exit": False,
            "historical_failure_cause_reconstructed": False, "measured_server_contact": False,
            "md5_content_authentication": False, "point_in_time_proven": False,
            "formal_forward_ready": False, "paper_or_live_ready": False}
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
        return 0 if observation is not None else 2
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
