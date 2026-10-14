"""One fresh read-only listing-shape observation, never upload admission.

The bounded 2xx JSON is parsed in memory, but only fixed schema facts and
aggregate counts are retained. Dynamic field names, object keys, names,
previews, error text, organization and credentials are never emitted. Missing
pagination fields or a successful API response do not establish completeness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
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
SOURCE = ROOT / "scripts/diagnose_arv2_newrule_listing_shape.py"
CONTROL = ROOT / "artifacts/analyst_revisions_v2/newrule_comparison_qc/R298-R303-20261013"
SCHEMA = "arv2-newrule-listing-shape-diagnostic-v1"
CLAIM, START, REPORT = ("listing-shape-diagnostic-v1-"+suffix+".json" for suffix in ("claim", "request-intent", "report"))
FAMILY_SHA256 = "8b8ee913dcfb5ad37f4748ea70db4fcbd6ff15580e52cd160bccf2b37e10a9e5"
INVENTORY_SHA256 = "b35e1bb0dfc887d6d775a7dd89155a1e8a703ee2aad148aa69cab52b718359c8"
ORGANIZATION_SHA256 = "a2d88859373df0f1fd59ede52b9b3945f847091b5fca3286841241536c38e880"
PREFIX, ENDPOINT = "arv2/preliminary-rating/27645603c1a6e0fc9fa81655", "object/list"
PRIOR_HEAD = "2cdfbc6abb345b6dd5964d1721982962f76340b3"
PRIOR_CALLER_SHA256 = "e9ebb920b9cde45c43cf1edb2c9a21bc9eda1fbd613bd8d35d8212f90e78f86b"
PRIOR_PROFILE_SHA256 = "21dec8243021cea476806a2a3c759e3940af741c0746bf4b3868dce580f6aef9"
PRIOR_REPORT_SHA256 = "a58f334a146b404be5d151e3e34d1a7a9a904462a5bbdaf47deeaddb532ee2d1"
PRIOR_REPORT_BYTES = 1258
PRIOR_REQUEST_SHA256 = "85adb51cb0d57442e638e75f1f69181f2ba066080b93623d4ac478e85b47eb3c"
FROZEN_CALLER_SHA256 = "533c1ebf520e9ebf836c78067b9b1480eccf49cfb01aaeb240e3a73b77087d05"
PINS = {
    "scripts/run_arv2_newrule_comparison.py": FROZEN_CALLER_SHA256,
    "scripts/arv2_newrule_storage_recovery.py": "c9952791bce1b802777c80b24a42a86be0d462a2b75a82b462200d58d6100682",
    "scripts/run_arv2_newrule_storage_recovery.py": "7b8aec7979c4df5f0818e06f86fe91f9ea8f6cefd4db085941ff8c04af7381b6",
    "scripts/diagnose_arv2_newrule_upload.py": "b8477fe9246b7355c9b10bec91a9ad6e6305fcd0a7e2d4f00f61da1c35ce9901",
    "scripts/diagnose_arv2_newrule_object_metadata.py": "0a566b6b049f160daf6cc1a1bb2a507e18dd645c64d948dea50136cebbbede23",
    "scripts/arv2_newrule_storage_recovery_v2.py": "02d40ea52084111cf6a04c6ffad629df0bb9008890133e16ef5b2a8f7b4406e9",
    "scripts/run_arv2_newrule_storage_recovery_v2.py": PRIOR_CALLER_SHA256,
}
DEADLINE_SECONDS, REQUEST_SECONDS = 90, 30
MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, MAX_OUTPUT_BYTES, MAX_CENSUS = 4096, 1024*1024, 24*1024, 4096
TOP_FIELDS = ("path", "objects", "page", "totalPages", "objectStorageUsed", "objectStorageUsedHuman", "success", "errors")
OBJECT_FIELDS = ("key", "name", "modified", "mime", "folder", "isFolder", "size")
KINDS = ("missing", "null", "bool", "int", "float", "str", "list", "dict", "other")
FLAGS = {"diagnostic_only": True, "original_upload_accepted": False,
    "storage_recovery_accepted": False, "listing_completeness_established": False,
    "changes_original_exit": False, "historical_failure_cause_reconstructed": False,
    "measured_server_contact": False, "point_in_time_proven": False,
    "formal_forward_ready": False, "paper_or_live_ready": False}
PROFILE = {"schema": SCHEMA, "root": str(ROOT), "control": str(CONTROL),
    "branch": frozen.BRANCH, "python": str(frozen.PYTHON), "family_sha256": FAMILY_SHA256,
    "organization_sha256": ORGANIZATION_SHA256, "inventory_sha256": INVENTORY_SHA256,
    "prefix": PREFIX, "endpoint": ENDPOINT, "request_limit": 1,
    "source_pins": dict(frozen.SOURCE_PINS), "new_pins": PINS,
    "prior_head": PRIOR_HEAD, "prior_caller_sha256": PRIOR_CALLER_SHA256,
    "prior_profile_sha256": PRIOR_PROFILE_SHA256, "prior_report_sha256": PRIOR_REPORT_SHA256,
    "prior_report_bytes": PRIOR_REPORT_BYTES, "prior_request_sha256": PRIOR_REQUEST_SHA256,
    "claim": CLAIM, "request_intent": START, "report": REPORT,
    "deadline_seconds": DEADLINE_SECONDS, "request_seconds": REQUEST_SECONDS,
    "max_request_bytes": MAX_REQUEST_BYTES, "max_response_bytes": MAX_RESPONSE_BYTES,
    "max_output_bytes": MAX_OUTPUT_BYTES, "max_census": MAX_CENSUS,
    "top_fields": TOP_FIELDS, "object_fields": OBJECT_FIELDS, "type_labels": KINDS,
    "redirects_proxies_retries": False, "non2xx_body_read": False, **FLAGS}
PROFILE_SHA256 = hashlib.sha256(helpers.canonical_json_bytes(PROFILE)).hexdigest()


class DiagnosticRefusal(ValueError):
    pass


def _require(value, code="diagnostic_refused"):
    if not value:
        raise DiagnosticRefusal(code)


def _same(left, right):
    return type(left) is type(right) and helpers.canonical_json_bytes(left) == helpers.canonical_json_bytes(right)


def _git(arguments, deadline, limit=65536):
    result = subprocess.run(["git", *arguments], cwd=ROOT, stdin=subprocess.DEVNULL,
        capture_output=True, timeout=min(3, helpers._remaining(deadline)), check=False)
    _require(type(result.returncode) is int and result.returncode == 0 and result.stderr == b""
        and type(result.stdout) is bytes and len(result.stdout) <= limit, "source_binding")
    return result.stdout


def _under_test():
    return "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules or any(name == "_pytest" or name.startswith("_pytest.") for name in tuple(sys.modules))


def _preflight(head, caller, deadline):
    _require(not _under_test(), "operational_test_context")
    _require(Path(__file__).absolute() == SOURCE and 0 < deadline-time.monotonic() <= DEADLINE_SECONDS,
        "source_binding")
    frozen._preflight(SimpleNamespace(operation="summarize", expected_head=head,
        caller_sha256=FROZEN_CALLER_SHA256, candidate=None, attempt=None,
        family_sha256=FAMILY_SHA256, prior_failure_sha256=None, justification_sha256=None), deadline)
    helpers.require_sha256(caller, "caller")
    _require(helpers._source_digest(SOURCE) == caller, "source_binding")
    for relative, digest in PINS.items():
        _require(helpers._source_digest(ROOT / relative) == digest, "source_binding")
    spec = head + ":" + SOURCE.relative_to(ROOT).as_posix()
    size = _git(["cat-file", "-s", spec], deadline).decode("ascii").strip()
    _require(re.fullmatch(r"[1-9][0-9]{0,6}", size) is not None and int(size) <= 2*1024*1024, "source_binding")
    raw = _git(["cat-file", "blob", spec], deadline, int(size))
    _require(len(raw) == int(size) and hashlib.sha256(raw).hexdigest() == caller
        and _git(["rev-parse", "HEAD"], deadline).decode("ascii").strip() == head
        and _git(["status", "--porcelain"], deadline) == b"", "source_binding")


def _dependencies():
    from scripts import arv2_newrule_storage_recovery_v2 as recovery
    from scripts import diagnose_arv2_newrule_object_metadata as prior
    from scripts import diagnose_arv2_newrule_upload as markers
    from research.analyst_revisions_v2_qc import newrule_comparison_submission as submission
    _require(submission.ROOT == ROOT and submission.CONTROL == CONTROL
        and recovery.PROFILE_SHA256 == PRIOR_PROFILE_SHA256, "source_binding")
    return recovery, prior, markers, submission


def _prior_binding(directory, recovery):
    binding = {"schema": "arv2-newrule-storage-recovery-v2", "profile_sha256": PRIOR_PROFILE_SHA256,
        "family_sha256": FAMILY_SHA256, "expected_head": PRIOR_HEAD, "caller_sha256": PRIOR_CALLER_SHA256}
    _require(_same(directory.read(recovery.CLAIM), dict(binding, attempt_consumed=True))
        and _same(directory.read(recovery.START), binding), "prior_binding")
    report = directory.read(recovery.REPORT)
    raw = helpers.canonical_json_bytes(report)
    _require(len(raw) == PRIOR_REPORT_BYTES and hashlib.sha256(raw).hexdigest() == PRIOR_REPORT_SHA256,
        "prior_report_pin")
    request = {"ordinal": 0, "endpoint": ENDPOINT, "index": None, "request_sha256": PRIOR_REQUEST_SHA256,
        "attempted": True, "http_status": 200, "response_schema_valid": True,
        "api_success": True, "error_category": "unknown"}
    expected = dict(binding, organization_sha256=ORGANIZATION_SHA256, inventory_sha256=INVENTORY_SHA256,
        prior_v1_refusal_sha256=recovery.V1_REFUSAL_SHA256, stage="list", complete=False,
        attempt_consumed=True, failure_code="listing_incomplete_or_shape", attempted_request_count=1,
        requests=[request], existing_indices=[], published_indices=[], validated_indices=[],
        legacy_upload_accepted=False, atomic_absent_only_put=False, actual_exit_is_external=True,
        formal_forward_ready=False, point_in_time_proven=False, paper_or_live_ready=False)
    _require(_same(report, expected), "prior_binding")


def _retained(directory, modules, deadline):
    recovery, prior, markers, submission = modules
    _prior_binding(directory, recovery)
    record = markers._family_binding(directory, submission, deadline)  # public inventory only, no package
    inventory = record["upload_inventory"]
    _require(len(inventory) == 6 and hashlib.sha256(helpers.canonical_json_bytes(inventory)).hexdigest() == INVENTORY_SHA256,
        "inventory_binding")
    organization = prior._organization(directory, submission)
    _require("upload-valid.json" not in directory.names() and recovery.ADMISSION not in directory.names(), "admission_present")
    return inventory, organization


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def _transport(api, submission, body, state, deadline):
    _require(type(body) is bytes and 0 < len(body) <= MAX_REQUEST_BYTES
        and state["attempted_request_count"] == 0, "request_scope")
    submission._safe_environment()
    headers = submission.build_auth_headers(api._credentials, api._clock())
    headers["Content-Type"] = "application/json"
    url = submission.API_BASE + "/" + ENDPOINT
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    opener = _opener()
    timeout = min(REQUEST_SECONDS, helpers._remaining(deadline))
    response = None
    state["attempted_request_count"] = 1  # attempted dispatch, not measured server contact
    try:
        try:
            response = opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            response = exc
        status = response.code
        _require(type(status) is int and 100 <= status <= 599 and response.geturl() == url, "response_transport")
        state["http_status"] = status
        helpers._remaining(deadline)
        if not 200 <= status < 300:
            return None
        raw = response.read(MAX_RESPONSE_BYTES+1)
        _require(type(raw) is bytes and len(raw) <= MAX_RESPONSE_BYTES, "response_bound")
        helpers._remaining(deadline)
        return raw
    finally:
        if response is not None:
            response.close()


def _json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            _require(key not in value, "response_json")
            value[key] = item
        return value
    def nonfinite(_):
        raise DiagnosticRefusal("response_nonfinite")
    def number(value):
        parsed = float(value)
        _require(math.isfinite(parsed), "response_nonfinite")
        return parsed
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=nonfinite, parse_float=number)


def _kind(value):
    for kind, label in ((type(None), "null"), (bool, "bool"), (int, "int"), (float, "float"),
        (str, "str"), (list, "list"), (dict, "dict")):
        if type(value) is kind:
            return label
    return "other"


def _observation(raw, inventory):
    if raw is None:
        return {"http_body_parsed": False, "schema_observation": None}
    value = _json(raw)
    fields = value if type(value) is dict else {}
    types = {field: _kind(fields[field]) if field in fields else "missing" for field in TOP_FIELDS}
    required = {"path", "objects", "page", "totalPages", "objectStorageUsed", "success"}
    path, page, pages, used, objects = (fields.get(name) for name in ("path", "page", "totalPages", "objectStorageUsed", "objects"))
    exact_int = lambda item: type(item) is int and 0 <= item < 2**31
    predicates = {"top_is_object": type(value) is dict, "required_fields_present": required <= set(fields),
        "only_known_top_fields": set(fields) <= set(TOP_FIELDS), "success_true": fields.get("success") is True,
        "path_exact": type(path) is str and path == PREFIX,
        "path_leading_slash": type(path) is str and path == "/"+PREFIX,
        "path_trailing_slash": type(path) is str and path == PREFIX+"/",
        "path_both_slashes": type(path) is str and path == "/"+PREFIX+"/",
        "page_exact_int_zero": type(page) is int and page == 0,
        "total_pages_exact_int_zero_or_one": type(pages) is int and pages in (0, 1),
        "storage_exact_nonnegative_int_in_range": type(used) is int and 0 <= used < 2**63,
        "objects_is_list": type(objects) is list,
        "objects_count_at_most_six": type(objects) is list and len(objects) <= 6}
    old_initial = all(predicates[name] for name in ("top_is_object", "required_fields_present", "only_known_top_fields",
        "success_true", "path_exact", "page_exact_int_zero", "total_pages_exact_int_zero_or_one",
        "storage_exact_nonnegative_int_in_range", "objects_is_list", "objects_count_at_most_six"))
    counters = {name: 0 for name in ("scanned", "dict", "non_dict", "known_key", "unknown_key", "invalid_key_type",
        "duplicate_known_key", "known_size_match", "documented_exact_schema", "alternate_is_folder_schema",
        "size_integral_float", "folder_true", "is_folder_true")}
    object_types = {field: {kind: 0 for kind in KINDS} for field in OBJECT_FIELDS}
    expected, seen = {row[0]: row[2] for row in inventory}, set()
    if type(objects) is list:
        for item in objects[:MAX_CENSUS]:
            counters["scanned"] += 1
            if type(item) is not dict:
                counters["non_dict"] += 1
                continue
            counters["dict"] += 1
            for field in OBJECT_FIELDS:
                object_types[field][_kind(item[field]) if field in item else "missing"] += 1
            documented = {"key", "name", "modified", "mime", "folder", "size"}
            counters["documented_exact_schema"] += set(item) == documented
            counters["alternate_is_folder_schema"] += set(item) == documented - {"folder"} | {"isFolder"}
            key, size = item.get("key"), item.get("size")
            if type(key) is not str:
                counters["invalid_key_type"] += 1
            elif key in expected:
                counters["known_key"] += 1
                counters["duplicate_known_key"] += key in seen
                counters["known_size_match"] += type(size) is int and size == expected[key]
                seen.add(key)
            else:
                counters["unknown_key"] += 1
            counters["size_integral_float"] += type(size) is float and size.is_integer()
            counters["folder_true"] += item.get("folder") is True
            counters["is_folder_true"] += item.get("isFolder") is True
    return {"http_body_parsed": True, "schema_observation": {"top_type": _kind(value), "field_types": types,
        "missing_required_count": len(required-set(fields)), "unknown_top_field_count": len(set(fields)-set(TOP_FIELDS)),
        "api_success": fields.get("success") if type(fields.get("success")) is bool else None,
        "errors_missing_or_empty_list": "errors" not in fields or type(fields["errors"]) is list and not fields["errors"],
        "errors_nonempty_list": type(fields.get("errors")) is list and bool(fields["errors"]),
        "page_value": page if exact_int(page) else None, "total_pages_value": pages if exact_int(pages) else None,
        "predicates": predicates, "original_initial_shape_conjunction": old_initial,
        "object_count": len(objects) if type(objects) is list else None,
        "census_complete": type(objects) is list and len(objects) <= MAX_CENSUS,
        "object_counters": counters, "object_field_types": object_types}}


_CODES = frozenset("diagnostic_refused source_binding operational_test_context prior_binding prior_report_pin inventory_binding admission_present request_scope response_transport response_bound response_json response_nonfinite publication_ambiguous".split())


def _failure(error):
    if type(error) is DiagnosticRefusal:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and len(args[0]) <= 64 and args[0] in _CODES:
            return args[0]
    for kind, label in ((helpers.Deadline, "deadline"), (FileExistsError, "claim_or_report_exists"),
        (FileNotFoundError, "file_missing"), (PermissionError, "permission_error"),
        (urllib.error.URLError, "transport_error"), (TimeoutError, "transport_timeout"),
        (json.JSONDecodeError, "response_json"), (UnicodeDecodeError, "response_encoding"),
        (RecursionError, "response_depth"), (KeyboardInterrupt, "cancelled"), (SystemExit, "cancelled"),
        (OSError, "os_error"), (ValueError, "value_error"), (TypeError, "type_error"), (KeyError, "key_error")):
        if type(error) is kind:
            return label
    return "unknown_exception"


def _safe_pin(value, size):
    return value if type(value) is str and re.fullmatch(r"[0-9a-f]{"+str(size)+"}", value) else None


def _run(head, caller, deadline):
    directory, claim, observation, failure = None, None, None, None
    stage, consumed = "preflight", False
    state = {"attempted_request_count": 0, "http_status": None}
    started = helpers._utc_now()
    try:
        _preflight(head, caller, deadline)  # compulsory even for direct _run callers
        modules = _dependencies()
        recovery, prior, markers, submission = modules
        stage = "claim"
        directory = submission._Directory()
        claim = {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256, "family_sha256": FAMILY_SHA256,
            "expected_head": head, "caller_sha256": caller, "attempt_consumed": True}
        consumed = None
        directory.write(CLAIM, claim)
        consumed, stage = True, "retained_authentication"
        inventory, organization = _retained(directory, modules, deadline)
        body = helpers.canonical_json_bytes({"organizationId": organization, "path": PREFIX})
        _require(hashlib.sha256(body).hexdigest() == PRIOR_REQUEST_SHA256, "request_scope")
        directory.write(START, {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256,
            "family_sha256": FAMILY_SHA256, "endpoint": ENDPOINT, "request_sha256": PRIOR_REQUEST_SHA256})
        stage = "credentials"
        api = submission._client()
        stage = "listing_request"
        raw = _transport(api, submission, body, state, deadline)
        stage = "response_shape"
        observation = _observation(raw, inventory)
        _require(_same(_retained(directory, modules, deadline), (inventory, organization)), "prior_binding")
        _preflight(head, caller, deadline)
        stage = "diagnostic_completed"
    except BaseException as error:
        observation, failure = None, _failure(error)
    try:
        helpers._remaining(deadline)
        report = {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256, "family_sha256": FAMILY_SHA256,
            "expected_head": _safe_pin(head, 40), "caller_sha256": _safe_pin(caller, 64),
            "prior_report_sha256": PRIOR_REPORT_SHA256, "started_at": started, "finished_at": helpers._utc_now(),
            "stage": stage, "terminal": "listing_shape_observed" if observation is not None else "diagnostic_refused",
            "attempt_consumed": consumed, "failure_code": failure, **state, "observation": observation, **FLAGS}
        raw = helpers.canonical_json_bytes(report)
        _require(len(raw) <= MAX_OUTPUT_BYTES-512, "publication_ambiguous")
        envelope = {"report": report, "report_published": False}
        if consumed is True:
            _require(_same(directory.read(CLAIM), claim), "publication_ambiguous")
            directory.write(REPORT, report)
            _require(_same(directory.read(CLAIM), claim) and _same(directory.read(REPORT), report), "publication_ambiguous")
            envelope.update(report_published=True, report_sha256=hashlib.sha256(raw).hexdigest(), report_bytes=len(raw))
        helpers._remaining(deadline)
        return envelope, 0 if observation is not None else 2
    finally:
        if directory is not None:
            try:
                directory.verify()  # one final directory identity/ownership endpoint check
            finally:
                directory.__exit__(None, None, None)  # closes only; this is not continuous integrity


def run(args):
    deadline = time.monotonic()+DEADLINE_SECONDS
    try:
        with helpers._alarm(deadline):
            value, status = _run(args.expected_head, args.caller_sha256, deadline)
            payload = helpers.canonical_json_bytes(value)
            _require(len(payload) <= MAX_OUTPUT_BYTES, "publication_ambiguous")
            helpers._remaining(deadline)
            print(payload.decode("ascii"))
            return status
    except BaseException as error:
        print(helpers.canonical_json_bytes({"terminal": "diagnostic_publication_ambiguous",
            "failure_code": _failure(error), **FLAGS}).decode("ascii"))
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--caller-sha256", required=True)
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
