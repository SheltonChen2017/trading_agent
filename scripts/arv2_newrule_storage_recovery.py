"""One-use, exact-prefix Object Store reconciliation after the owner upgrade.

No old upload/diagnostic is replayed. A complete successful listing is required
before absence is inferred; every existing object is verified before any put.
QC exposes no absent-only compare-and-swap: an object can appear/change between
the finite listing/properties checks and a put. This is not a concurrency lock.
Actual successful caller exit and a separately committed receipt pin are still
required before continuation; a receipt alone is not operational acceptance.
"""
from __future__ import annotations

import hashlib
import re
import time
import urllib.error
import urllib.request

from scripts import diagnose_arv2_newrule_object_metadata as prior
from scripts import diagnose_arv2_newrule_upload as markers
from research.analyst_revisions_v2_qc import newrule_comparison_submission as old

helpers = prior.helpers
ROOT, CONTROL = prior.ROOT, prior.CONTROL
FAMILY_SHA256, ORGANIZATION_SHA256 = prior.FAMILY_SHA256, prior.ORGANIZATION_SHA256
PREFIX = "arv2/preliminary-rating/27645603c1a6e0fc9fa81655"
SCHEMA = "arv2-newrule-storage-recovery-v1"
CLAIM, START = "storage-recovery-v1-claim.json", "storage-recovery-v1-start.json"
REPORT, ADMISSION = "storage-recovery-v1-report.json", "storage-recovery-v1-admission.json"
D9_SHA256 = "0a566b6b049f160daf6cc1a1bb2a507e18dd645c64d948dea50136cebbbede23"
D9_HEAD = "68b1cb39f719ea85d7539fab679696a16d1b4a74"
D9_REPORT_SHA256 = "5f8a1894781b60baea592c8fc14e9ae230681cc321b005e0a543cd0d79d13030"
D9_REPORT_BYTES = 1086
MAX_REQUESTS, MAX_RESPONSE_BYTES, REQUEST_SECONDS = 13, 1024*1024, 30
PROFILE = {"schema": SCHEMA, "root": str(ROOT), "control": str(CONTROL),
    "family_sha256": FAMILY_SHA256, "organization_sha256": ORGANIZATION_SHA256,
    "inventory_sha256": prior.INVENTORY_SHA256, "prefix": PREFIX,
    "d8_source_sha256": prior.D8_SOURCE_SHA256, "d8_report_sha256": prior.D8_REPORT_SHA256,
    "d8_report_bytes": prior.D8_REPORT_BYTES, "d9_source_sha256": D9_SHA256,
    "d9_report_sha256": D9_REPORT_SHA256, "d9_report_bytes": D9_REPORT_BYTES,
    "request_limit": MAX_REQUESTS, "response_byte_limit": MAX_RESPONSE_BYTES,
    "request_timeout_seconds": REQUEST_SECONDS, "parent_deadline_seconds": 500,
    "claim": CLAIM, "start": START, "report": REPORT, "admission": ADMISSION,
    "listed_page": 0, "complete_total_pages": [0, 1], "activation_last": True,
    "existing_properties_before_any_write": True, "retries": False,
    "legacy_upload_accepted": False, "atomic_absent_only_put": False,
    "actual_exit_is_external": True, "formal_forward_ready": False,
    "point_in_time_proven": False, "paper_or_live_ready": False}
PROFILE_SHA256 = hashlib.sha256(helpers.canonical_json_bytes(PROFILE)).hexdigest()


class StorageRecoveryError(ValueError):
    pass


def _require(value, code):
    if not value:
        raise StorageRecoveryError(code)


def _same(left, right):
    return type(left) is type(right) and helpers.canonical_json_bytes(left) == helpers.canonical_json_bytes(right)


def _sha(value):
    return hashlib.sha256(helpers.canonical_json_bytes(value)).hexdigest()


def _context(head, caller):
    _require(type(head) is str and re.fullmatch(r"[0-9a-f]{40}", head) is not None
        and type(caller) is str and re.fullmatch(r"[0-9a-f]{64}", caller) is not None, "source_binding")
    _require(old.ROOT == ROOT and old.CONTROL == CONTROL, "root_binding")


def claim(expected_head, caller_sha256):
    """Exclusive public binding, before the caller loads any private package."""
    _context(expected_head, caller_sha256)
    value = {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256,
        "family_sha256": FAMILY_SHA256, "expected_head": expected_head,
        "caller_sha256": caller_sha256, "attempt_consumed": True}
    with old._Directory() as directory:
        directory.write(CLAIM, value)
    return value


def _claim(directory, head, caller):
    expected = {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256,
        "family_sha256": FAMILY_SHA256, "expected_head": head,
        "caller_sha256": caller, "attempt_consumed": True}
    _require(_same(directory.read(CLAIM), expected), "claim_binding")
    return expected


def _retained(directory, plan, record, deadline):
    _require(helpers._source_digest(prior.SOURCE) == D9_SHA256
        and helpers._source_digest(prior.D8_SOURCE) == prior.D8_SOURCE_SHA256, "diagnostic_source_pin")
    current = old.require_family(plan, FAMILY_SHA256)
    _require(_same(current, record), "family_changed")
    old._bound(directory, plan, record)
    prior._d8_binding(directory, record, markers)  # exact external report, not the spent census
    raw_record = directory.read(prior.REPORT)
    raw = helpers.canonical_json_bytes(raw_record)
    _require(len(raw) == D9_REPORT_BYTES and hashlib.sha256(raw).hexdigest() == D9_REPORT_SHA256,
        "d9_report_pin")
    expected = {"schema": prior.SCHEMA, "profile_sha256": prior.PROFILE_SHA256,
        "expected_head": D9_HEAD, "caller_sha256": D9_SHA256, "family_sha256": FAMILY_SHA256,
        "started_at": raw_record.get("started_at"), "finished_at": raw_record.get("finished_at"),
        "stage": "diagnostic_completed", "terminal": "metadata_observation_completed",
        "attempt_consumed": True, "failure_code": None, "attempted_request_count": 1,
        "http_status": 200, "observation": {"response_schema_valid": True, "api_success": False,
            "metadata_schema_valid": None, "key_matches": None, "size_matches": None,
            "md5_well_formed": None, "error_category": "unknown"},
        "diagnostic_only": True, "original_upload_accepted": False, "changes_original_exit": False,
        "historical_failure_cause_reconstructed": False, "measured_server_contact": False,
        "md5_content_authentication": False, "point_in_time_proven": False,
        "formal_forward_ready": False, "paper_or_live_ready": False}
    _require(_same(raw_record, expected), "d9_report_schema")
    organization = prior._organization(directory, old)
    _require("upload-valid.json" not in directory.names(), "legacy_admission_present")
    helpers._remaining(deadline)
    return organization


def _payloads(plan, record):
    package = old._input(plan._input)
    pairs = tuple(old.compact.iter_accepted_risk_preliminary_upload_objects(package))
    inventory = record["upload_inventory"]
    _require(len(pairs) == len(inventory) == 6 and _sha(inventory) == prior.INVENTORY_SHA256,
        "inventory_binding")
    payloads = []
    for index, (descriptor, payload) in enumerate(pairs):
        row = inventory[index]
        _require(type(payload) is bytes and _same(row, [descriptor.object_store_key,
            hashlib.sha256(payload).hexdigest(), len(payload), descriptor.activation_manifest])
            and row[0].startswith(PREFIX + "/") and "/" not in row[0][len(PREFIX)+1:]
            and row[3] is (index == 5), "payload_binding")
        payloads.append(payload)
    return tuple(payloads)


def _request(directory, api, endpoint, index, body, content_type, state, deadline):
    _require(endpoint in {"object/list", "object/properties", "object/set"}
        and (index is None if endpoint == "object/list" else type(index) is int and 0 <= index < 6)
        and type(body) is bytes and 0 < len(body) <= old.compact.MAX_UPLOAD_OBJECT_BYTES+4096,
        "request_scope")
    _require(len(state["requests"]) < MAX_REQUESTS, "request_budget")
    helpers._remaining(deadline)
    entry = {"ordinal": len(state["requests"]), "endpoint": endpoint, "index": index,
        "request_sha256": hashlib.sha256(body).hexdigest(),
        "attempted": False, "http_status": None, "response_schema_valid": False,
        "api_success": None, "error_category": "unknown"}
    state["requests"].append(entry)
    stem = f"storage-recovery-v1-request-{entry['ordinal']:02d}"
    directory.write(stem + "-intent.json", {"family_sha256": FAMILY_SHA256,
        "profile_sha256": PROFILE_SHA256, "endpoint": endpoint, "index": index,
        "ordinal": entry["ordinal"], "request_sha256": hashlib.sha256(body).hexdigest()})
    old._safe_environment()
    headers = old.build_auth_headers(api._credentials, api._clock())
    headers["Content-Type"] = content_type
    url = old.API_BASE + "/" + endpoint
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    opener = prior._opener()
    timeout = min(REQUEST_SECONDS, helpers._remaining(deadline))
    response = None
    entry["attempted"] = True
    state["attempted_request_count"] += 1  # dispatch attempts, not measured server contacts
    try:
        try:
            response = opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            response = exc
        code = response.code
        _require(type(code) is int and 100 <= code <= 599 and response.geturl() == url, "response_transport")
        entry["http_status"] = code
        helpers._remaining(deadline)
        _require(200 <= code < 300, "http_status")  # no failed response body read
        raw = response.read(MAX_RESPONSE_BYTES+1)
        _require(type(raw) is bytes and len(raw) <= MAX_RESPONSE_BYTES, "response_bound")
        helpers._remaining(deadline)
        value = prior._json(raw)
        _require(type(value) is dict and type(value.get("success")) is bool, "response_schema")
        entry.update(response_schema_valid=True, api_success=value["success"],
            error_category=prior._error_category(value.get("errors", [])))
        _require(value["success"] is True, "service_refused")
        _require(not value.get("errors", []), "response_contradiction")
        directory.write(stem + "-observed.json", dict(entry, family_sha256=FAMILY_SHA256,
            profile_sha256=PROFILE_SHA256))
        return value
    finally:
        if response is not None:
            response.close()


def _listing(value, inventory):
    required = {"path", "objects", "page", "totalPages", "objectStorageUsed", "success"}
    _require(type(value) is dict and required <= set(value)
        and set(value) <= required | {"objectStorageUsedHuman", "errors"}
        and value["success"] is True and type(value["path"]) is str and value["path"] == PREFIX
        and type(value["page"]) is int and value["page"] == 0
        and type(value["totalPages"]) is int and value["totalPages"] in (0, 1)
        and type(value["objectStorageUsed"]) is int and 0 <= value["objectStorageUsed"] < 2**63
        and type(value["objects"]) is list and len(value["objects"]) <= 6,
        "listing_incomplete_or_shape")
    _require("objectStorageUsedHuman" not in value or type(value["objectStorageUsedHuman"]) is str
        and len(value["objectStorageUsedHuman"]) <= 64, "listing_human_shape")
    _require(value["totalPages"] != 0 or not value["objects"], "listing_page_census")
    expected = {row[0]: (index, row[2]) for index, row in enumerate(inventory)}
    found = set()
    for item in value["objects"]:
        _require(type(item) is dict and {"key", "name", "modified", "mime", "folder", "size"} == set(item),
            "listing_object_schema")
        key = item["key"]
        _require(type(key) is str and key in expected and key not in found and item["folder"] is False
            and type(item["size"]) is int and item["size"] == expected[key][1]
            and all(type(item[field]) is str and len(item[field]) <= 512 for field in ("name", "modified", "mime"))
            and item["name"] == key[len(PREFIX)+1:], "listing_object_mismatch")
        found.add(key)
    indices = tuple(index for index, row in enumerate(inventory) if row[0] in found)
    _require(5 not in indices or len(indices) == 6, "activation_without_data")
    return indices


def _properties(value, row, payload):
    _require(type(value) is dict and {"success", "metadata"} <= set(value)
        and set(value) <= {"success", "metadata", "errors"} and value["success"] is True,
        "properties_schema")
    data = value["metadata"]
    _require(type(data) is dict and {"key", "size", "md5"} <= set(data)
        and set(data) <= {"key", "size", "md5", "modified", "created", "mime", "preview"}
        and type(data["key"]) is str and data["key"] == row[0]
        and type(data["size"]) is int and data["size"] == row[2]
        and type(data["md5"]) is str and re.fullmatch(r"[0-9a-fA-F]{32}", data["md5"]) is not None
        and data["md5"].lower() == hashlib.md5(payload, usedforsecurity=False).hexdigest(), "properties_mismatch")


def _multipart(organization, key, payload):
    boundary = old.transport._multipart_boundary(payload)
    _require(("\r\n--" + boundary).encode("ascii") not in payload, "multipart_collision")
    head = (f'--{boundary}\r\nContent-Disposition: form-data; name="organizationId"\r\n\r\n{organization}\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="key"\r\n\r\n{key}\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="objectData"; filename="object.bin"\r\n'
        'Content-Type: application/octet-stream\r\n\r\n').encode("ascii")
    return head + payload + f"\r\n--{boundary}--\r\n".encode("ascii"), "multipart/form-data; boundary="+boundary


def finite_failure(exc):
    if type(exc) is StorageRecoveryError:
        args = BaseException.args.__get__(exc)
        if len(args) == 1 and type(args[0]) is str and len(args[0]) <= 64 and args[0] in _CODES:
            return args[0]
    return prior._failure(exc, old)


_CODES = frozenset("""source_binding root_binding claim_binding diagnostic_source_pin family_changed
d9_report_pin d9_report_schema legacy_admission_present inventory_binding payload_binding request_scope
request_budget response_transport http_status response_bound response_schema service_refused response_contradiction
listing_incomplete_or_shape listing_human_shape listing_page_census listing_object_schema listing_object_mismatch
activation_without_data properties_schema properties_mismatch multipart_collision set_schema
old_controls_changed source_postcheck publication_ambiguous admission_pin admission_schema report_pin
report_schema request_census admission_claim source_inventory""".split())
FINITE_FAILURE_CODES = _CODES | old.FINITE_REFUSAL_CODES | frozenset("""
operation_refused diagnostic_refused preflight_refused deadline claim_or_report_exists file_missing
permission_error os_error transport_error transport_timeout response_json response_encoding cancelled
value_error type_error key_error memory_error response_depth unknown_exception
""".split())


def recover(plan, expected_family_sha256, expected_head, caller_sha256, deadline):
    _context(expected_head, caller_sha256)
    _require(expected_family_sha256 == FAMILY_SHA256, "family_changed")
    state = {"attempted_request_count": 0, "requests": [], "existing_indices": [], "published_indices": [],
        "validated_indices": []}
    complete, failure, stage = False, None, "claim"
    with old._Directory() as directory:
        _claim(directory, expected_head, caller_sha256)
        directory.write(START, {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256,
            "family_sha256": FAMILY_SHA256, "expected_head": expected_head, "caller_sha256": caller_sha256})
        names = {name for name in directory.names() if not name.startswith("storage-recovery-v1-")}
        try:
            stage = "retained_authentication"
            record = old.require_family(plan, FAMILY_SHA256)
            organization = _retained(directory, plan, record, deadline)
            payloads = _payloads(plan, record)
            inventory = record["upload_inventory"]
            api = old._client()
            stage = "list"
            value = _request(directory, api, "object/list", None,
                old._canonical({"organizationId": organization, "path": PREFIX}), "application/json", state, deadline)
            existing = _listing(value, inventory)
            state["existing_indices"] = list(existing)
            stage = "existing_properties"
            for index in existing:
                row = inventory[index]
                value = _request(directory, api, "object/properties", index,
                    old._canonical({"organizationId": organization, "key": row[0]}), "application/json", state, deadline)
                _properties(value, row, payloads[index])
                state["validated_indices"].append(index)
            stage = "publish_missing"
            for index, row in enumerate(inventory):
                if index in existing:
                    continue
                body, content_type = _multipart(organization, row[0], payloads[index])
                value = _request(directory, api, "object/set", index, body, content_type, state, deadline)
                _require(set(value) <= {"success", "errors"} and value["success"] is True, "set_schema")
                state["published_indices"].append(index)
                value = _request(directory, api, "object/properties", index,
                    old._canonical({"organizationId": organization, "key": row[0]}), "application/json", state, deadline)
                _properties(value, row, payloads[index])
                state["validated_indices"].append(index)
            stage = "post_authentication"
            _require(_retained(directory, plan, record, deadline) == organization
                and _payloads(plan, record) == payloads, "source_postcheck")
            _require({name for name in directory.names() if not name.startswith("storage-recovery-v1-")} == names,
                "old_controls_changed")
            _claim(directory, expected_head, caller_sha256)
            complete, stage = True, "completed"
        except BaseException as exc:
            failure = finite_failure(exc)
        report = {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256, "family_sha256": FAMILY_SHA256,
            "organization_sha256": ORGANIZATION_SHA256, "inventory_sha256": prior.INVENTORY_SHA256,
            "expected_head": expected_head, "caller_sha256": caller_sha256, "stage": stage,
            "complete": complete, "attempt_consumed": True, "failure_code": failure, **state,
            "legacy_upload_accepted": False, "atomic_absent_only_put": False,
            "actual_exit_is_external": True, "formal_forward_ready": False,
            "point_in_time_proven": False, "paper_or_live_ready": False}
        try:
            helpers._remaining(deadline)
            _claim(directory, expected_head, caller_sha256)
            directory.write(REPORT, report)
            _require(_same(directory.read(REPORT), report), "report_schema")
            result = {"complete": complete, "report_sha256": _sha(report),
                "report_bytes": len(helpers.canonical_json_bytes(report)), "failure_code": failure,
                "attempted_request_count": state["attempted_request_count"],
                "requests": [dict(entry) for entry in state["requests"]]}
            if complete:
                receipt = {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256,
                    "family_sha256": FAMILY_SHA256, "organization_sha256": ORGANIZATION_SHA256,
                    "inventory_sha256": prior.INVENTORY_SHA256, "report_sha256": _sha(report),
                    "expected_head": expected_head, "caller_sha256": caller_sha256,
                    "validated_indices": list(range(6)), "actual_exit_is_external": True,
                    "legacy_upload_accepted": False, "formal_forward_ready": False,
                    "point_in_time_proven": False, "paper_or_live_ready": False}
                directory.write(ADMISSION, receipt)
                _require(_same(directory.read(ADMISSION), receipt), "admission_schema")
                result.update(receipt_sha256=_sha(receipt), receipt_bytes=len(helpers.canonical_json_bytes(receipt)))
            helpers._remaining(deadline)
            return result
        except BaseException:
            raise StorageRecoveryError("publication_ambiguous") from None


def require_admission(directory, plan, record, expected_receipt_sha256):
    """Authenticate the new sidecar, never create/repair the legacy receipt.

    The later caller must separately require the observed original exit 0 and
    commit this exact receipt pin before authorizing a continuation operation.
    """
    _require(type(expected_receipt_sha256) is str and re.fullmatch(r"[0-9a-f]{64}", expected_receipt_sha256), "admission_pin")
    _require(_same(old.require_family(plan, FAMILY_SHA256), record), "family_changed")
    old._bound(directory, plan, record)
    receipt = directory.read(ADMISSION)
    _require(_sha(receipt) == expected_receipt_sha256, "admission_pin")
    head, caller = receipt.get("expected_head"), receipt.get("caller_sha256")
    _context(head, caller)
    expected = {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256,
        "family_sha256": FAMILY_SHA256, "organization_sha256": ORGANIZATION_SHA256,
        "inventory_sha256": prior.INVENTORY_SHA256, "report_sha256": receipt.get("report_sha256"),
        "expected_head": head, "caller_sha256": caller, "validated_indices": list(range(6)),
        "actual_exit_is_external": True, "legacy_upload_accepted": False, "formal_forward_ready": False,
        "point_in_time_proven": False, "paper_or_live_ready": False}
    _require(_same(receipt, expected), "admission_schema")
    _claim(directory, head, caller)
    _require(_same(directory.read(START), {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256,
        "family_sha256": FAMILY_SHA256, "expected_head": head, "caller_sha256": caller}), "admission_claim")
    report = directory.read(REPORT)
    _require(_sha(report) == receipt["report_sha256"], "report_pin")
    expected_report = {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256, "family_sha256": FAMILY_SHA256,
        "organization_sha256": ORGANIZATION_SHA256, "inventory_sha256": prior.INVENTORY_SHA256,
        "expected_head": head, "caller_sha256": caller, "stage": "completed",
        "complete": True, "attempt_consumed": True, "failure_code": None,
        **{name: report.get(name) for name in ("attempted_request_count", "requests", "existing_indices",
                                             "published_indices", "validated_indices")},
        "legacy_upload_accepted": False, "atomic_absent_only_put": False,
        "actual_exit_is_external": True, "formal_forward_ready": False,
        "point_in_time_proven": False, "paper_or_live_ready": False}
    _require(_same(report, expected_report), "report_schema")
    _validate_census(report)
    for entry in report["requests"]:
        stem = f"storage-recovery-v1-request-{entry['ordinal']:02d}"
        intent = directory.read(stem + "-intent.json")
        digest = entry["request_sha256"]
        _require(type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest) is not None
            and _same(intent, {"family_sha256": FAMILY_SHA256, "profile_sha256": PROFILE_SHA256,
                "endpoint": entry["endpoint"], "index": entry["index"], "ordinal": entry["ordinal"],
                "request_sha256": digest}) and _same(directory.read(stem + "-observed.json"),
                    dict(entry, family_sha256=FAMILY_SHA256, profile_sha256=PROFILE_SHA256)), "request_census")
    _require(prior._organization(directory, old) is not None and "upload-valid.json" not in directory.names(), "admission_schema")
    return receipt


def _validate_census(report):
    existing, published, validated = (report.get(name) for name in ("existing_indices", "published_indices", "validated_indices"))
    for indices in (existing, published, validated):
        _require(type(indices) is list and all(type(i) is int and 0 <= i < 6 for i in indices)
            and len(indices) == len(set(indices)), "request_census")
    _require(existing == sorted(existing) and published == [i for i in range(6) if i not in existing]
        and validated == existing + published and (5 not in existing or len(existing) == 6), "request_census")
    expected = [("object/list", None)] + [("object/properties", i) for i in existing]
    expected += [(endpoint, i) for i in published for endpoint in ("object/set", "object/properties")]
    requests = report.get("requests")
    _require(type(requests) is list and len(requests) == len(expected) <= MAX_REQUESTS
        and type(report.get("attempted_request_count")) is int and report["attempted_request_count"] == len(requests), "request_census")
    for ordinal, (entry, (endpoint, index)) in enumerate(zip(requests, expected)):
        _require(type(entry) is dict and set(entry) == {"ordinal", "endpoint", "index", "attempted",
            "request_sha256", "http_status", "response_schema_valid", "api_success", "error_category"}
            and type(entry["ordinal"]) is int and entry["ordinal"] == ordinal
            and entry["endpoint"] == endpoint and type(entry["index"]) is type(index) and entry["index"] == index
            and type(entry["request_sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", entry["request_sha256"]) is not None
            and entry["attempted"] is True and type(entry["http_status"]) is int and 200 <= entry["http_status"] < 300
            and entry["response_schema_valid"] is True and entry["api_success"] is True
            and type(entry["error_category"]) is str
            and entry["error_category"] in {"unknown", "permission", "not_found", "quota", "subscription"}, "request_census")
