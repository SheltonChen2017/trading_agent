"""One read-only properties matrix for six exact objects; never admission.

Nulls, API refusals and mismatches are observations, never absence. The bounded
2xx JSON (including possible preview) is parsed in memory, but only finite
schema/status/comparison facts leave the process. No object contents, keys,
organization, credentials, raw errors, upload or strategy launch is emitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import os
import re
import subprocess
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
SOURCE = ROOT / "scripts/diagnose_arv2_newrule_properties_matrix.py"
CONTROL = ROOT / "artifacts/analyst_revisions_v2/newrule_comparison_qc/R298-R303-20261013"
SCHEMA = "arv2-newrule-properties-matrix-diagnostic-v1"
CLAIM, REPORT = "properties-matrix-diagnostic-v1-claim.json", "properties-matrix-diagnostic-v1-report.json"
FAMILY_SHA256 = "8b8ee913dcfb5ad37f4748ea70db4fcbd6ff15580e52cd160bccf2b37e10a9e5"
INVENTORY_SHA256 = "b35e1bb0dfc887d6d775a7dd89155a1e8a703ee2aad148aa69cab52b718359c8"
ORGANIZATION_SHA256 = "a2d88859373df0f1fd59ede52b9b3945f847091b5fca3286841241536c38e880"
LISTING_HEAD = "9e93d11644f54c5ab3bc9c9b95cb2938fa5093bb"
LISTING_SHA256 = "292a5cafa1a7210e347d409bf18bcc282085cb751458190ae33705d31781a8ee"
LISTING_PROFILE_SHA256 = "5736226a17494d400750d10f42e7d4f220ec81605d0a0b9abb8a7f67bf7cc280"
LISTING_REPORT_SHA256 = "18cde403e00abf61989ba7e01b763fbf34c6c99e4a4b39dae69012a038b23986"
LISTING_REPORT_BYTES = 2885
FROZEN_CALLER_SHA256 = "533c1ebf520e9ebf836c78067b9b1480eccf49cfb01aaeb240e3a73b77087d05"
PINS = {
    "scripts/run_arv2_newrule_comparison.py": FROZEN_CALLER_SHA256,
    "scripts/arv2_newrule_storage_recovery.py": "c9952791bce1b802777c80b24a42a86be0d462a2b75a82b462200d58d6100682",
    "scripts/run_arv2_newrule_storage_recovery.py": "7b8aec7979c4df5f0818e06f86fe91f9ea8f6cefd4db085941ff8c04af7381b6",
    "scripts/diagnose_arv2_newrule_upload.py": "b8477fe9246b7355c9b10bec91a9ad6e6305fcd0a7e2d4f00f61da1c35ce9901",
    "scripts/diagnose_arv2_newrule_object_metadata.py": "0a566b6b049f160daf6cc1a1bb2a507e18dd645c64d948dea50136cebbbede23",
    "scripts/arv2_newrule_storage_recovery_v2.py": "02d40ea52084111cf6a04c6ffad629df0bb9008890133e16ef5b2a8f7b4406e9",
    "scripts/run_arv2_newrule_storage_recovery_v2.py": "e9ebb920b9cde45c43cf1edb2c9a21bc9eda1fbd613bd8d35d8212f90e78f86b",
    "scripts/diagnose_arv2_newrule_listing_shape.py": LISTING_SHA256,
}
ENDPOINT, REQUEST_LIMIT = "object/properties", 6
DEADLINE_SECONDS, REQUEST_SECONDS = 240, 30
MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, MAX_OUTPUT_BYTES = 4096, 1024*1024, 24*1024
FLAGS = {"diagnostic_only": True, "original_upload_accepted": False, "storage_recovery_accepted": False,
    "absence_established": False, "changes_original_exit": False, "historical_failure_cause_reconstructed": False,
    "measured_server_contact": False, "formal_forward_ready": False, "point_in_time_proven": False,
    "paper_or_live_ready": False}
PROFILE = {"schema": SCHEMA, "root": str(ROOT), "control": str(CONTROL), "branch": frozen.BRANCH,
    "python": str(frozen.PYTHON), "family_sha256": FAMILY_SHA256, "inventory_sha256": INVENTORY_SHA256,
    "organization_sha256": ORGANIZATION_SHA256, "listing_head": LISTING_HEAD,
    "listing_source_sha256": LISTING_SHA256, "listing_profile_sha256": LISTING_PROFILE_SHA256,
    "listing_report_sha256": LISTING_REPORT_SHA256, "listing_report_bytes": LISTING_REPORT_BYTES,
    "source_pins": dict(frozen.SOURCE_PINS), "new_pins": PINS, "claim": CLAIM, "report": REPORT,
    "endpoint": ENDPOINT, "request_limit": REQUEST_LIMIT, "deadline_seconds": DEADLINE_SECONDS,
    "request_seconds": REQUEST_SECONDS, "max_request_bytes": MAX_REQUEST_BYTES,
    "max_response_bytes": MAX_RESPONSE_BYTES, "max_output_bytes": MAX_OUTPUT_BYTES,
    "redirects_proxies_retries": False, "non2xx_body_read": False,
    "stop_on_non2xx": True, "stop_on_success_with_nonempty_errors": True,
    "package_sha256": frozen.PACKAGE_SHA256, "lineage_sha256": frozen.LINEAGE_SHA256, **FLAGS}
PROFILE_SHA256 = hashlib.sha256(helpers.canonical_json_bytes(PROFILE)).hexdigest()


class DiagnosticRefusal(ValueError):
    pass


def _require(value, code="diagnostic_refused"):
    if not value: raise DiagnosticRefusal(code)


def _same(left, right):
    return type(left) is type(right) and helpers.canonical_json_bytes(left) == helpers.canonical_json_bytes(right)


def _under_test():
    return "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules or any(name == "_pytest" or name.startswith("_pytest.") for name in tuple(sys.modules))


def _git(arguments, deadline, limit=65536):
    result = subprocess.run(["git", *arguments], cwd=ROOT, stdin=subprocess.DEVNULL,
        capture_output=True, timeout=min(3, helpers._remaining(deadline)), check=False)
    _require(type(result.returncode) is int and result.returncode == 0 and result.stderr == b""
        and type(result.stdout) is bytes and len(result.stdout) <= limit, "source_binding")
    return result.stdout


def _preflight(head, caller, deadline):
    _require(not _under_test(), "operational_test_context")
    _require(Path(__file__).absolute() == SOURCE and 0 < deadline-time.monotonic() <= DEADLINE_SECONDS, "source_binding")
    frozen._preflight(SimpleNamespace(operation="summarize", expected_head=head,
        caller_sha256=FROZEN_CALLER_SHA256, candidate=None, attempt=None, family_sha256=FAMILY_SHA256,
        prior_failure_sha256=None, justification_sha256=None), deadline)
    helpers.require_sha256(caller, "caller")
    _require(helpers._source_digest(SOURCE) == caller, "source_binding")
    for relative, digest in PINS.items():
        _require(helpers._source_digest(ROOT / relative) == digest, "source_binding")
    spec = head+":"+SOURCE.relative_to(ROOT).as_posix()
    size = _git(["cat-file", "-s", spec], deadline).decode("ascii").strip()
    _require(re.fullmatch(r"[1-9][0-9]{0,6}", size) is not None and int(size) <= 2*1024*1024, "source_binding")
    raw = _git(["cat-file", "blob", spec], deadline, int(size))
    _require(len(raw) == int(size) and hashlib.sha256(raw).hexdigest() == caller
        and _git(["rev-parse", "HEAD"], deadline).decode("ascii").strip() == head
        and _git(["status", "--porcelain"], deadline) == b"", "source_binding")


def _dependencies():
    from scripts import diagnose_arv2_newrule_listing_shape as listing
    modules = listing._dependencies()  # imports and fixed identities only, not any old operation
    _require(listing.PROFILE_SHA256 == LISTING_PROFILE_SHA256 and listing.CONTROL == CONTROL, "source_binding")
    return listing, modules


def _listing_binding(directory, listing):
    binding = {"schema": listing.SCHEMA, "profile_sha256": LISTING_PROFILE_SHA256,
        "family_sha256": FAMILY_SHA256, "expected_head": LISTING_HEAD, "caller_sha256": LISTING_SHA256,
        "attempt_consumed": True}
    _require(_same(directory.read(listing.CLAIM), binding), "listing_binding")
    _require(_same(directory.read(listing.START), {"schema": listing.SCHEMA,
        "profile_sha256": LISTING_PROFILE_SHA256, "family_sha256": FAMILY_SHA256,
        "endpoint": "object/list", "request_sha256": listing.PRIOR_REQUEST_SHA256}), "listing_binding")
    report = directory.read(listing.REPORT)
    raw = helpers.canonical_json_bytes(report)
    _require(len(raw) == LISTING_REPORT_BYTES and hashlib.sha256(raw).hexdigest() == LISTING_REPORT_SHA256,
        "listing_report_pin")
    expected = dict(binding, prior_report_sha256=listing.PRIOR_REPORT_SHA256,
        started_at=report.get("started_at"), finished_at=report.get("finished_at"),
        stage="diagnostic_completed", terminal="listing_shape_observed", failure_code=None,
        attempted_request_count=1, http_status=200, observation=report.get("observation"), **listing.FLAGS)
    _require(_same(report, expected), "listing_binding")
    observed = report.get("observation")
    _require(type(observed) is dict and set(observed) == {"http_body_parsed", "schema_observation"}
        and observed["http_body_parsed"] is True, "listing_binding")
    shape = observed["schema_observation"]
    _require(type(shape) is dict and shape.get("api_success") is True and shape.get("object_count") is None
        and shape.get("census_complete") is False and shape.get("original_initial_shape_conjunction") is False
        and type(shape.get("field_types")) is dict and type(shape.get("predicates")) is dict
        and shape["field_types"].get("objects") == "null"
        and shape["field_types"].get("page") == "null"
        and shape["field_types"].get("totalPages") == "null"
        and shape["predicates"].get("path_exact") is True, "listing_binding")


def _retained(directory, listing, modules, deadline):
    _listing_binding(directory, listing)
    return listing._retained(directory, modules, deadline)  # exact V2/family/org metadata only


def _package_payloads(value, submission, inventory):
    package = submission._input(value)  # genuine exact October package/lineage authority
    pairs = tuple(submission.compact.iter_accepted_risk_preliminary_upload_objects(package))
    _require(len(pairs) == len(inventory) == REQUEST_LIMIT, "inventory_binding")
    payloads = []
    for (descriptor,payload),row in zip(pairs,inventory):
        _require(type(payload) is bytes and _same(row,[descriptor.object_store_key,
            hashlib.sha256(payload).hexdigest(),len(payload),descriptor.activation_manifest])
            and descriptor.content_sha256 == row[1] and descriptor.byte_count == row[2],"inventory_binding")
        payloads.append(payload)
    return tuple(payloads)


def _load_payloads(submission, inventory):
    value = frozen.prepared_input.october.load_october_order_input_package(frozen.PACKAGE,
        expected_package_sha256=frozen.PACKAGE_SHA256, lineage_path=frozen.LINEAGE,
        expected_lineage_sha256=frozen.LINEAGE_SHA256)
    return value, _package_payloads(value,submission,inventory)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None


def _opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def _transport(api, submission, body, entry, state, deadline):
    _require(type(body) is bytes and 0 < len(body) <= MAX_REQUEST_BYTES
        and type(state["attempted_request_count"]) is int and state["attempted_request_count"] < REQUEST_LIMIT
        and entry["index"] == state["attempted_request_count"], "request_scope")
    submission._safe_environment()
    headers = submission.build_auth_headers(api._credentials, api._clock())
    headers["Content-Type"] = "application/json"
    url = submission.API_BASE+"/"+ENDPOINT
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    opener = _opener()
    timeout = min(REQUEST_SECONDS, helpers._remaining(deadline))
    response = None
    entry["attempted"] = True
    state["attempted_request_count"] += 1  # attempted dispatch, not measured server contact
    try:
        try: response = opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as error: response = error
        status = response.code
        _require(type(status) is int and 100 <= status <= 599 and response.geturl() == url, "response_transport")
        entry["http_status"] = status
        helpers._remaining(deadline)
        if not 200 <= status < 300: return None
        raw = response.read(MAX_RESPONSE_BYTES+1)
        _require(type(raw) is bytes and len(raw) <= MAX_RESPONSE_BYTES, "response_bound")
        helpers._remaining(deadline)
        return raw
    finally:
        if response is not None: response.close()


def _observation(raw, row, payload, listing, prior):
    result = {"http_body_parsed": False, "response_schema_valid": None, "api_success": None,
        "metadata_present": None, "metadata_type": "unobserved", "metadata_schema_valid": None,
        "key_matches": None, "size_matches": None, "md5_well_formed": None, "md5_matches": None,
        "error_category": "unknown", "success_with_nonempty_errors": None}
    if raw is None: return result
    value = listing._json(raw)  # strict duplicate keys, nonfinite incl overflowing exponent, UTF-8
    result["http_body_parsed"] = True
    valid = type(value) is dict and set(value) <= {"success", "metadata", "errors"} and type(value.get("success")) is bool
    result["response_schema_valid"] = valid
    if not valid: return result
    result["api_success"] = value["success"]
    errors = value.get("errors", [])
    try:
        result["error_category"] = prior._error_category(errors)
    except BaseException as error:
        if type(error) is prior.DiagnosticRefusal:
            raise DiagnosticRefusal("response_schema") from None
        raise
    result["success_with_nonempty_errors"] = value["success"] and bool(errors)
    result["metadata_present"] = "metadata" in value
    result["metadata_type"] = listing._kind(value["metadata"]) if "metadata" in value else "missing"
    metadata = value.get("metadata")
    if metadata is None: return result
    allowed = {"key", "size", "md5", "modified", "created", "mime", "preview"}
    valid = type(metadata) is dict and {"key", "size", "md5"} <= set(metadata) and set(metadata) <= allowed
    if valid:
        key, size, md5 = metadata["key"], metadata["size"], metadata["md5"]
        valid = (type(key) is str and 0 < len(key) <= 512 and key.isascii()
            and type(size) is int and 0 <= size < 2**63 and type(md5) is str and len(md5) <= 128)
    result["metadata_schema_valid"] = valid
    if valid:
        well_formed = re.fullmatch(r"[0-9a-fA-F]{32}", md5) is not None
        result.update(key_matches=key == row[0], size_matches=size == row[2], md5_well_formed=well_formed,
            md5_matches=md5.lower() == hashlib.md5(payload, usedforsecurity=False).hexdigest() if well_formed else None)
    return result


_CODES = frozenset("diagnostic_refused source_binding operational_test_context listing_binding listing_report_pin inventory_binding request_scope response_transport response_bound response_schema http_status_stop response_contradiction source_postcheck publication_ambiguous".split())


def _failure(error, listing=None, prior=None, submission=None):
    if type(error) is DiagnosticRefusal:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and len(args[0]) <= 64 and args[0] in _CODES: return args[0]
    if listing is not None and type(error) is listing.DiagnosticRefusal:
        return listing._failure(error)
    if prior is not None and type(error) is prior.DiagnosticRefusal:
        return "dependency_validation_refused"
    if submission is not None and type(error) is submission.NewruleSubmissionError:
        return submission.finite_failure(error)
    for kind, label in ((helpers.Deadline,"deadline"),(FileExistsError,"claim_or_report_exists"),
        (FileNotFoundError,"file_missing"),(PermissionError,"permission_error"),(urllib.error.URLError,"transport_error"),
        (json.JSONDecodeError,"response_json"),(UnicodeDecodeError,"response_encoding"),
        (TimeoutError,"transport_timeout"),(RecursionError,"response_depth"),(KeyboardInterrupt,"cancelled"),
        (SystemExit,"cancelled"),(OSError,"os_error"),(ValueError,"value_error"),(TypeError,"type_error"),(KeyError,"key_error")):
        if type(error) is kind: return label
    return "unknown_exception"


def _safe_pin(value,size):
    return value if type(value) is str and re.fullmatch(r"[0-9a-f]{"+str(size)+"}",value) else None


def _run(head,caller,deadline):
    directory, claim, failure, completed = None, None, None, False
    listing, prior, submission = None, None, None
    stage, consumed = "preflight", False
    state = {"attempted_request_count":0,"observations":[]}
    started = helpers._utc_now()
    try:
        _preflight(head,caller,deadline)  # compulsory even for direct _run callers
        listing, modules = _dependencies()
        recovery, prior, markers, submission = modules
        stage = "claim"
        directory = submission._Directory()
        claim = {"schema":SCHEMA,"profile_sha256":PROFILE_SHA256,"family_sha256":FAMILY_SHA256,
            "expected_head":head,"caller_sha256":caller,"attempt_consumed":True}
        consumed = None
        directory.write(CLAIM,claim)
        consumed,stage = True,"retained_authentication"
        inventory,organization = _retained(directory,listing,modules,deadline)
        stage = "input_authentication"
        value,payloads = _load_payloads(submission,inventory)
        _require(len(inventory) == len(payloads) == REQUEST_LIMIT,"inventory_binding")
        helpers._remaining(deadline)
        api = None
        for index,(row,payload) in enumerate(zip(inventory,payloads)):
            body = helpers.canonical_json_bytes({"organizationId":organization,"key":row[0]})
            stem = f"properties-matrix-diagnostic-v1-request-{index:02d}"
            stage = "request_intent"
            directory.write(stem+"-intent.json",{"schema":SCHEMA,"profile_sha256":PROFILE_SHA256,
                "family_sha256":FAMILY_SHA256,"endpoint":ENDPOINT,"index":index,
                "request_sha256":hashlib.sha256(body).hexdigest()})
            entry = {"index":index,"request_sha256":hashlib.sha256(body).hexdigest(),
                "attempted":False,"http_status":None,"observation":None}
            state["observations"].append(entry)
            if api is None:
                stage = "credentials"
                api = submission._client()
            stage = "properties_request"
            raw = _transport(api,submission,body,entry,state,deadline)
            stage = "response_validation"
            entry["observation"] = _observation(raw,row,payload,listing,prior)
            directory.write(stem+"-observed.json",dict(entry,schema=SCHEMA,profile_sha256=PROFILE_SHA256,
                family_sha256=FAMILY_SHA256))
            observation = entry["observation"]
            _require(200 <= entry["http_status"] < 300,"http_status_stop")
            _require(observation["success_with_nonempty_errors"] is not True,"response_contradiction")
            _require(observation["response_schema_valid"] is not False
                and observation["metadata_schema_valid"] is not False,"response_schema")
        stage = "post_authentication"
        _require(_same(_retained(directory,listing,modules,deadline),(inventory,organization))
            and _package_payloads(value,submission,inventory) == payloads,"source_postcheck")
        _preflight(head,caller,deadline)
        completed,stage = True,"diagnostic_completed"
    except BaseException as error:
        failure = _failure(error,listing,prior,submission)
    try:
        helpers._remaining(deadline)
        report = {"schema":SCHEMA,"profile_sha256":PROFILE_SHA256,"family_sha256":FAMILY_SHA256,
            "expected_head":_safe_pin(head,40),"caller_sha256":_safe_pin(caller,64),
            "listing_report_sha256":LISTING_REPORT_SHA256,"started_at":started,"finished_at":helpers._utc_now(),
            "stage":stage,"terminal":"properties_matrix_completed" if completed else "diagnostic_refused",
            "attempt_consumed":consumed,"failure_code":failure,"matrix_completed":completed,**state,**FLAGS}
        raw = helpers.canonical_json_bytes(report)
        _require(len(raw) <= MAX_OUTPUT_BYTES-512,"publication_ambiguous")
        envelope = {"report":report,"report_published":False}
        if consumed is True:
            _require(_same(directory.read(CLAIM),claim),"publication_ambiguous")
            directory.write(REPORT,report)
            _require(_same(directory.read(CLAIM),claim) and _same(directory.read(REPORT),report),"publication_ambiguous")
            envelope.update(report_published=True,report_sha256=hashlib.sha256(raw).hexdigest(),report_bytes=len(raw))
        helpers._remaining(deadline)
        return envelope,0 if completed else 2
    finally:
        if directory is not None:
            try: directory.verify()  # finite directory identity/ownership endpoint check
            finally: directory.__exit__(None,None,None)


def run(args):
    deadline = time.monotonic()+DEADLINE_SECONDS
    try:
        with helpers._alarm(deadline):
            result,status = _run(args.expected_head,args.caller_sha256,deadline)
            payload = helpers.canonical_json_bytes(result)
            _require(len(payload) <= MAX_OUTPUT_BYTES,"publication_ambiguous")
            helpers._remaining(deadline)
            print(payload.decode("ascii"))
            return status
    except BaseException as error:
        print(helpers.canonical_json_bytes({"terminal":"diagnostic_publication_ambiguous",
            "failure_code":_failure(error),**FLAGS}).decode("ascii"))
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head",required=True)
    parser.add_argument("--caller-sha256",required=True)
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
