"""One properties-first publication with exact prospective absence grammar.

The templates below are selected supported forms, not reconstructed D13 text.
Every initial object is checked before any write. An absent object is checked
again immediately before its sole put. QC offers no conditional absent-only
write, so the finite checks do not eliminate a concurrent-create race.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

from scripts import diagnose_arv2_newrule_storage_error as error_text
from scripts import diagnose_arv2_newrule_properties_matrix as payload_reader
from scripts import arv2_newrule_storage_recovery_v2 as primitives
from scripts import diagnose_arv2_newrule_upload as family
from scripts import diagnose_arv2_newrule_object_metadata as organization_reader
from research.analyst_revisions_v2_qc import newrule_comparison_submission as old

helpers, frozen = error_text.helpers, error_text.frozen
ROOT, CONTROL = error_text.ROOT, error_text.CONTROL
SOURCE = ROOT / "scripts/arv2_newrule_storage_recovery_v3.py"
CALLER_SOURCE = ROOT / "scripts/run_arv2_newrule_storage_recovery_v3.py"
FAMILY_SHA256, INVENTORY_SHA256 = error_text.FAMILY_SHA256, error_text.INVENTORY_SHA256
ORGANIZATION_SHA256 = error_text.ORGANIZATION_SHA256
SCHEMA, STEM = "arv2-newrule-storage-recovery-v3", "storage-recovery-v3-"
CLAIM, START, REPORT, ADMISSION = (STEM + name + ".json" for name in ("claim", "start", "report", "admission"))
DEADLINE_SECONDS, REQUEST_SECONDS, MAX_REQUESTS, MAX_SETS = 300, 30, 24, 6
MAX_RESPONSE_BYTES, MAX_REPORT_BYTES, MAX_OUTPUT_BYTES = 16384, 256 * 1024, 64 * 1024
ABSENCE_TEMPLATES = ("File not found: {key}", "File not found: '{key}'", 'File not found: "{key}"')
D13_HEAD = "ccc3efffcba40d149beba2f6a52a6671e60f8444"
D13_REPORT_SHA256 = "d5a00781879ef8d6561ea19ce52fbddb78c5006df643d7654e496cb4df4db07c"
D13_REPORT_BYTES = 1478
ADDITIONS = {
    **error_text.PINS,
    "scripts/arv2_newrule_storage_recovery_v2.py": "02d40ea52084111cf6a04c6ffad629df0bb9008890133e16ef5b2a8f7b4406e9",
    "scripts/diagnose_arv2_newrule_properties_matrix.py": "47b8eec8296beb0433a1223adea38c471ba2034b26ac81cb20a2e4143431f363",
    "scripts/diagnose_arv2_newrule_storage_error.py": "090c0ad92811820cb87d37df7c13f8b63033d14b5d23f20cac770c729760a252",
}
FLAGS = {"legacy_upload_accepted": False, "atomic_absent_only_put": False,
    "actual_exit_is_external": True, "measured_server_contact": False,
    "reason_text_is_partial": True, "provider_reason_is_root_cause": False,
    "formal_forward_ready": False, "point_in_time_proven": False, "paper_or_live_ready": False}
PROFILE = {"schema": SCHEMA, "root": str(ROOT), "control": str(CONTROL),
    "helper_path": str(SOURCE), "caller_path": str(CALLER_SOURCE),
    "branch": frozen.BRANCH, "python": str(frozen.PYTHON),
    "family_sha256": FAMILY_SHA256, "inventory_sha256": INVENTORY_SHA256,
    "organization_sha256": ORGANIZATION_SHA256, "package_sha256": frozen.PACKAGE_SHA256,
    "lineage_sha256": frozen.LINEAGE_SHA256, "source_pins": dict(frozen.SOURCE_PINS),
    "additional_pins": ADDITIONS, "claim": CLAIM, "start": START, "report": REPORT, "admission": ADMISSION,
    "historical_d13_head_not_reread": D13_HEAD, "historical_d13_report_sha256_not_reread": D13_REPORT_SHA256,
    "historical_d13_report_bytes_not_reread": D13_REPORT_BYTES,
    "absence_templates": list(ABSENCE_TEMPLATES), "absence_exact_http_status": 200,
    "initial_six_properties_before_any_set": True, "immediate_absence_recheck": True,
    "activation_last": True, "request_limit": MAX_REQUESTS, "set_limit": MAX_SETS,
    "parent_deadline_seconds": DEADLINE_SECONDS, "request_seconds": REQUEST_SECONDS,
    "max_response_bytes": MAX_RESPONSE_BYTES, "max_report_bytes": MAX_REPORT_BYTES,
    "max_output_bytes": MAX_OUTPUT_BYTES, "redaction_profile_sha256": error_text.PROFILE_SHA256,
    "non2xx_json_body_read": True, "retry_redirect_proxy": False,
    "old_report_read": False, "list_get_delete": False, "non_authorizing_error_shape": True, **FLAGS}
PROFILE_SHA256 = hashlib.sha256(helpers.canonical_json_bytes(PROFILE)).hexdigest()


class StorageRecoveryError(ValueError):
    pass


def _require(value, code):
    if not value: raise StorageRecoveryError(code)


def _same(left, right):
    return type(left) is type(right) and helpers.canonical_json_bytes(left) == helpers.canonical_json_bytes(right)


def _sha(value): return hashlib.sha256(helpers.canonical_json_bytes(value)).hexdigest()


def _context(head, caller):
    _require(type(head) is str and re.fullmatch(r"[0-9a-f]{40}", head) is not None
        and type(caller) is str and re.fullmatch(r"[0-9a-f]{64}", caller) is not None, "source_binding")


def _under_test():
    return "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules or any(
        name == "_pytest" or name.startswith("_pytest.") for name in tuple(sys.modules))


def _git(args, deadline, limit=65536):
    value = subprocess.run(["git", *args], cwd=ROOT, stdin=subprocess.DEVNULL,
        capture_output=True, check=False, timeout=min(3, helpers._remaining(deadline)))
    _require(type(value.returncode) is int and value.returncode == 0 and value.stderr == b""
        and type(value.stdout) is bytes and len(value.stdout) <= limit, "source_binding")
    return value.stdout


def _runtime_gate(head, caller, deadline):
    _context(head, caller)
    _require(not _under_test(), "operational_test_context")
    _require(sys.platform == "darwin" and os.name == "posix" and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == frozen.PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT
        and Path(__file__).absolute() == SOURCE and old.ROOT == ROOT and old.CONTROL == CONTROL
        and 0 < deadline - time.monotonic() <= DEADLINE_SECONDS, "runtime_identity")
    for args, expected in ((["rev-parse", "--show-toplevel"], str(ROOT)),
        (["branch", "--show-current"], frozen.BRANCH), (["rev-parse", "HEAD"], head), (["status", "--porcelain"], "")):
        _require(_git(args, deadline).decode("ascii").strip() == expected, "source_binding")
    _require(len(frozen.SOURCE_PINS) == 51 and len(ADDITIONS) == 6, "source_inventory")
    for name, digest in (*frozen.SOURCE_PINS.items(), *ADDITIONS.items()):
        _require(helpers._source_digest(ROOT / name) == digest, "source_binding")
    helper_sha = helpers._source_digest(SOURCE)
    _require(helpers._source_digest(CALLER_SOURCE) == caller, "source_binding")
    for path, digest in ((SOURCE, helper_sha), (CALLER_SOURCE, caller)):
        spec = head + ":" + path.relative_to(ROOT).as_posix()
        size = _git(["cat-file", "-s", spec], deadline).decode("ascii").strip()
        _require(re.fullmatch(r"[1-9][0-9]{0,6}", size) is not None and int(size) <= 2 * 1024 * 1024, "source_binding")
        raw = _git(["cat-file", "blob", spec], deadline, int(size))
        _require(len(raw) == int(size) and hashlib.sha256(raw).hexdigest() == digest, "source_binding")
    _require(_git(["rev-parse", "HEAD"], deadline).decode("ascii").strip() == head
        and _git(["status", "--porcelain"], deadline) == b"", "source_binding")
    helpers._remaining(deadline)


def _binding(head, caller):
    return {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256, "family_sha256": FAMILY_SHA256,
        "expected_head": head, "caller_sha256": caller}


def _claim(directory, head, caller):
    value = dict(_binding(head, caller), attempt_consumed=True)
    _require(_same(directory.read(CLAIM), value), "claim_binding")
    return value


def _retained(directory, deadline):
    record = family._family_binding(directory, old, deadline)
    inventory = record["upload_inventory"]
    _require(len(inventory) == 6 and _sha(inventory) == INVENTORY_SHA256
        and "upload-valid.json" not in directory.names(), "inventory_binding")
    return record, organization_reader._organization(directory, old)


def _properties_state(value, row, payload):
    _require(type(value) is dict and set(value) <= {"success", "errors", "metadata"}
        and type(value.get("success")) is bool, "response_schema")
    errors = value.get("errors", [])
    _require(type(errors) is list and len(errors) <= 8
        and all(type(item) is str and len(item) <= 512 for item in errors), "response_schema")
    if value["success"] is True:
        _require(errors == [], "response_contradiction")
        primitives._properties(value, row, payload)
        return "present", None
    _require(("metadata" not in value or value["metadata"] is None) and len(errors) == 1, "absence_unproven")
    matches = [index for index, template in enumerate(ABSENCE_TEMPLATES) if errors[0] == template.format(key=row[0])]
    _require(len(matches) == 1, "absence_unproven")
    return "absent", matches[0]


def _body(phase, organization, row, payload):
    if phase == "put":
        body, content_type = primitives._multipart(organization, row[0], payload)
        return "object/set", body, content_type
    _require(phase in {"initial", "recheck", "verify"}, "request_scope")
    return "object/properties", helpers.canonical_json_bytes({"organizationId": organization, "key": row[0]}), "application/json"


def _intent(entry):
    return {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256, "family_sha256": FAMILY_SHA256,
        **{key: entry[key] for key in ("ordinal", "phase", "endpoint", "index", "request_sha256")}}


def _stem(ordinal): return STEM + f"request-{ordinal:02d}"


def _error_shape(value, key):
    errors = value.get("errors", [])
    if len(errors) != 1: return None
    text = errors[0]
    count = text.count(key)
    position = text.find(key) if count == 1 else None
    return {"file_not_found_prefix": text.startswith("File not found"),
        "requested_key_occurrences": count, "prefix_characters": position,
        "suffix_characters": len(text) - position - len(key) if position is not None else None}


def _validate_error_shape(value):
    if value is None: return
    _require(type(value) is dict and set(value) == {"file_not_found_prefix", "requested_key_occurrences", "prefix_characters", "suffix_characters"}
        and type(value["file_not_found_prefix"]) is bool and type(value["requested_key_occurrences"]) is int
        and 0 <= value["requested_key_occurrences"] <= 512, "observation_schema")
    for key in ("prefix_characters", "suffix_characters"):
        _require(type(value[key]) is int and 0 <= value[key] <= 512 if value["requested_key_occurrences"] == 1
            else value[key] is None, "observation_schema")


def _transport(api, endpoint, body, content_type, organization, key, entry, state, deadline):
    old._safe_environment()
    headers = old.build_auth_headers(api._credentials, api._clock())
    headers["Content-Type"] = content_type
    secrets = (api._credentials.user_id, api._credentials.api_token, organization, key,
        headers["Authorization"], headers["Timestamp"])
    error_text._secret_variants(secrets)
    url = old.API_BASE + "/" + endpoint
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    opener = error_text._opener()
    response = None
    try:
        timeout = min(REQUEST_SECONDS, helpers._remaining(deadline))
        entry["attempted"] = True
        state["attempted_request_count"] += 1
        try: response = opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as error: response = error
        status = response.code
        _require(type(status) is int and 100 <= status <= 599 and response.geturl() == url, "response_transport")
        entry["http_status"] = status
        helpers._remaining(deadline)
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        _require(type(raw) is bytes and len(raw) <= MAX_RESPONSE_BYTES, "response_bound")
        helpers._remaining(deadline)
        entry["observation"] = error_text._observation(raw, secrets)
        value = error_text._json(raw)
        entry["error_shape"] = _error_shape(value, key)
        _require(status == 200, "http_status")
        return value
    finally:
        if response is not None: response.close()


def _request(directory, api, phase, index, organization, row, payload, state, deadline):
    _require(type(index) is int and 0 <= index < 6 and phase in {"initial", "recheck", "put", "verify"}
        and type(payload) is bytes and len(state["requests"]) < MAX_REQUESTS, "request_scope")
    _require(phase != "put" or sum(item["phase"] == "put" for item in state["requests"]) < MAX_SETS, "request_budget")
    endpoint, body, content_type = _body(phase, organization, row, payload)
    _require(type(body) is bytes and 0 < len(body) <= old.compact.MAX_UPLOAD_OBJECT_BYTES + 4096, "request_scope")
    entry = {"ordinal": len(state["requests"]), "phase": phase, "endpoint": endpoint, "index": index,
        "request_sha256": hashlib.sha256(body).hexdigest(), "attempted": False, "http_status": None,
        "observation": None, "error_shape": None, "object_state": None, "absence_template_index": None, "failure_code": None}
    state["requests"].append(entry)
    stem = _stem(entry["ordinal"])
    directory.write(stem + "-intent.json", _intent(entry))
    try:
        value = _transport(api, endpoint, body, content_type, organization, row[0], entry, state, deadline)
        if phase == "put":
            _require(type(value) is dict and set(value) <= {"success", "errors"}
                and value.get("success") is True and value.get("errors", []) == [], "set_refused")
            entry["object_state"] = "published"
        else:
            entry["object_state"], entry["absence_template_index"] = _properties_state(value, row, payload)
        return entry["object_state"]
    except BaseException as error:
        entry["failure_code"] = finite_failure(error)
        raise
    finally:
        directory.write(stem + "-observed.json", dict(_intent(entry), observation_record=dict(entry)))


_CODES = frozenset("""source_binding source_inventory runtime_identity operational_test_context claim_binding
inventory_binding family_changed response_schema response_contradiction absence_unproven request_scope
request_budget response_transport response_bound http_status set_refused activation_without_data recheck_changed
verification_failed source_postcheck old_controls_changed publication_ambiguous admission_pin admission_schema
report_pin report_schema request_census observation_schema control_census""".split())
FINITE_FAILURE_CODES = (_CODES | primitives.FINITE_FAILURE_CODES | error_text._CODES | frozenset("""
response_nonfinite response_depth redaction_binding redaction_bound error_schema response_encoding unknown_exception
dependency_validation_refused
""".split()))


def finite_failure(error):
    if type(error) is StorageRecoveryError:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and len(args[0]) <= 64 and args[0] in _CODES: return args[0]
    if type(error) is primitives.StorageRecoveryError: return primitives.finite_failure(error)
    if type(error) is old.NewruleSubmissionError: return old.finite_failure(error)
    return error_text._failure(error, (family, organization_reader, old))


def _base_report(head, caller):
    return dict(_binding(head, caller), organization_sha256=ORGANIZATION_SHA256,
        inventory_sha256=INVENTORY_SHA256, historical_d13_report_sha256_not_reread=D13_REPORT_SHA256,
        attempt_consumed=True, **FLAGS)


def _receipt(head, caller, report):
    return dict(_binding(head, caller), organization_sha256=ORGANIZATION_SHA256,
        inventory_sha256=INVENTORY_SHA256, historical_d13_report_sha256_not_reread=D13_REPORT_SHA256,
        report_sha256=_sha(report), report_bytes=len(helpers.canonical_json_bytes(report)),
        validated_indices=list(range(6)), **FLAGS)


def recover(expected_head, caller_sha256, deadline):
    """Own the single new claim before retained input or credentials are read."""
    _runtime_gate(expected_head, caller_sha256, deadline)
    state = {"attempted_request_count": 0, "requests": [], "initial_states": [],
        "published_indices": [], "validated_indices": []}
    directory = old._Directory()
    try:
        directory.write(CLAIM, dict(_binding(expected_head, caller_sha256), attempt_consumed=True))
        directory.write(START, _binding(expected_head, caller_sha256))
        other_names = {name for name in directory.names() if not name.startswith(STEM)}
        complete, failure, stage = False, None, "input_authentication"
        try:
            record, organization = _retained(directory, deadline)
            inventory = record["upload_inventory"]
            value, payloads = payload_reader._load_payloads(old, inventory)
            helpers._remaining(deadline)
            api = old._client()
            stage = "initial_properties"
            for index, row in enumerate(inventory):
                status = _request(directory, api, "initial", index, organization, row, payloads[index], state, deadline)
                state["initial_states"].append(status)
                if status == "present": state["validated_indices"].append(index)
            _require(state["initial_states"][5] != "present" or all(item == "present" for item in state["initial_states"]),
                "activation_without_data")
            for index, row in enumerate(inventory):
                if state["initial_states"][index] == "present": continue
                stage = "absence_recheck"
                _require(_request(directory, api, "recheck", index, organization, row, payloads[index], state, deadline)
                    == "absent", "recheck_changed")
                stage = "publish_missing"
                _request(directory, api, "put", index, organization, row, payloads[index], state, deadline)
                state["published_indices"].append(index)
                stage = "verify_publication"
                _require(_request(directory, api, "verify", index, organization, row, payloads[index], state, deadline)
                    == "present", "verification_failed")
                state["validated_indices"].append(index)
            stage = "post_authentication"
            _require(_same(_retained(directory, deadline), (record, organization)), "source_postcheck")
            fresh_value, fresh_payloads = payload_reader._load_payloads(old, inventory)
            _require(payloads == fresh_payloads and payload_reader._package_payloads(value, old, inventory) == payloads
                and payload_reader._package_payloads(fresh_value, old, inventory) == payloads, "source_postcheck")
            _runtime_gate(expected_head, caller_sha256, deadline)
            _require({name for name in directory.names() if not name.startswith(STEM)} == other_names, "old_controls_changed")
            _claim(directory, expected_head, caller_sha256)
            complete, stage = True, "completed"
        except BaseException as error:
            failure = finite_failure(error)
        report = dict(_base_report(expected_head, caller_sha256), stage=stage, complete=complete,
            failure_code=failure, **state)
        helpers._remaining(deadline)
        _claim(directory, expected_head, caller_sha256)
        _require(len(helpers.canonical_json_bytes(report)) <= MAX_REPORT_BYTES, "publication_ambiguous")
        if complete: _validate_census(directory, report, inventory, payloads, organization, include_final=False)
        directory.write(REPORT, report)
        _require(_same(directory.read(REPORT), report), "publication_ambiguous")
        result = {"complete": complete, "report_sha256": _sha(report),
            "report_bytes": len(helpers.canonical_json_bytes(report)), "failure_code": failure,
            "attempted_request_count": state["attempted_request_count"], "requests": [dict(item) for item in state["requests"]]}
        if complete:
            receipt = _receipt(expected_head, caller_sha256, report)
            directory.write(ADMISSION, receipt)
            _require(_same(directory.read(ADMISSION), receipt), "publication_ambiguous")
            _validate_census(directory, report, inventory, payloads, organization, include_final=True)
            result.update(receipt_sha256=_sha(receipt), receipt_bytes=len(helpers.canonical_json_bytes(receipt)))
        helpers._remaining(deadline)
        _claim(directory, expected_head, caller_sha256)
        return result
    finally:
        try: directory.verify()
        finally: directory.__exit__(None, None, None)


def _validate_observation(value):
    fields = {"response_schema_valid", "api_success", "errors_present", "error_count", "redacted_provider_reasons",
        "reason_has_redacted_spans", "redacted_span_counts", "metadata_present", "success_with_errors"}
    _require(type(value) is dict and set(value) == fields and value["response_schema_valid"] is True
        and (value["api_success"] is None or type(value["api_success"]) is bool) and type(value["errors_present"]) is bool
        and type(value["metadata_present"]) is bool and type(value["success_with_errors"]) is bool
        and type(value["error_count"]) is int and 0 <= value["error_count"] <= 8, "observation_schema")
    reasons, flags, counts = (value[name] for name in ("redacted_provider_reasons", "reason_has_redacted_spans", "redacted_span_counts"))
    _require(all(type(items) is list and len(items) == value["error_count"] for items in (reasons, flags, counts)), "observation_schema")
    for reason, flag, count in zip(reasons, flags, counts):
        _require(type(reason) is str and 0 < len(reason) <= 1024 and reason == " ".join(reason.split())
            and all(word in error_text.VOCABULARY or word == error_text.REDACTED for word in reason.split())
            and type(flag) is bool and flag is (error_text.REDACTED in reason)
            and type(count) is int and count == reason.count(error_text.REDACTED), "observation_schema")
    _require(value["success_with_errors"] is (value["api_success"] is True and bool(reasons)), "observation_schema")


def _validate_census(directory, report, inventory, payloads, organization, *, include_final):
    initial = report.get("initial_states")
    _require(type(initial) is list and len(initial) == 6 and all(type(item) is str and item in {"present", "absent"} for item in initial)
        and (initial[5] != "present" or all(item == "present" for item in initial)), "request_census")
    present, missing = ([i for i in range(6) if initial[i] == status] for status in ("present", "absent"))
    _require(_same(report.get("published_indices"), missing)
        and _same(report.get("validated_indices"), present + missing), "request_census")
    expected = [("initial", i, initial[i]) for i in range(6)]
    expected += [(phase, i, result) for i in missing for phase, result in (("recheck", "absent"), ("put", "published"), ("verify", "present"))]
    trace = report.get("requests")
    _require(type(trace) is list and len(trace) == len(expected) <= MAX_REQUESTS
        and type(report.get("attempted_request_count")) is int and report["attempted_request_count"] == len(expected), "request_census")
    names = {CLAIM, START} | ({REPORT, ADMISSION} if include_final else set())
    fields = {"ordinal", "phase", "endpoint", "index", "request_sha256", "attempted", "http_status", "observation",
        "object_state", "absence_template_index", "failure_code", "error_shape"}
    for ordinal, (entry, (phase, index, result)) in enumerate(zip(trace, expected)):
        endpoint, body, _ = _body(phase, organization, inventory[index], payloads[index])
        _require(type(entry) is dict and set(entry) == fields and type(entry["ordinal"]) is int and entry["ordinal"] == ordinal
            and type(entry["index"]) is int and entry["index"] == index and entry["phase"] == phase and entry["endpoint"] == endpoint
            and entry["request_sha256"] == hashlib.sha256(body).hexdigest() and entry["attempted"] is True
            and type(entry["http_status"]) is int and entry["http_status"] == 200 and entry["object_state"] == result
            and entry["failure_code"] is None, "request_census")
        observation = entry["observation"]
        _validate_observation(observation)
        _validate_error_shape(entry["error_shape"])
        if result == "absent":
            _require(type(entry["absence_template_index"]) is int and 0 <= entry["absence_template_index"] < len(ABSENCE_TEMPLATES)
                and observation["api_success"] is False and observation["error_count"] == 1, "request_census")
            expected_shape = _error_shape({"errors": [ABSENCE_TEMPLATES[entry["absence_template_index"]].format(key=inventory[index][0])]}, inventory[index][0])
            _require(_same(entry["error_shape"], expected_shape), "request_census")
        else:
            _require(entry["absence_template_index"] is None and observation["api_success"] is True
                and observation["error_count"] == 0 and observation["metadata_present"] is (phase != "put"), "request_census")
            _require(entry["error_shape"] is None, "request_census")
        stem = _stem(ordinal)
        _require(_same(directory.read(stem + "-intent.json"), _intent(entry))
            and _same(directory.read(stem + "-observed.json"), dict(_intent(entry), observation_record=entry)), "request_census")
        names.update((stem + "-intent.json", stem + "-observed.json"))
    _require({name for name in directory.names() if name.startswith(STEM)} == names, "control_census")


def require_admission(directory, plan, record, expected_receipt_sha256):
    """Only this new sidecar; actual successful recovery exit is separately bound."""
    _require(type(expected_receipt_sha256) is str and re.fullmatch(r"[0-9a-f]{64}", expected_receipt_sha256) is not None, "admission_pin")
    _require(_same(old.require_family(plan, FAMILY_SHA256), record), "family_changed")
    old._bound(directory, plan, record)
    receipt = directory.read(ADMISSION)
    _require(_sha(receipt) == expected_receipt_sha256, "admission_pin")
    head, caller = receipt.get("expected_head"), receipt.get("caller_sha256")
    _context(head, caller)
    report = directory.read(REPORT)
    _require(_sha(report) == receipt.get("report_sha256") and len(helpers.canonical_json_bytes(report)) == receipt.get("report_bytes"), "report_pin")
    _require(_same(receipt, _receipt(head, caller, report)), "admission_schema")
    expected = dict(_base_report(head, caller), stage="completed", complete=True, failure_code=None,
        **{name: report.get(name) for name in ("attempted_request_count", "requests", "initial_states", "published_indices", "validated_indices")})
    _require(_same(report, expected), "report_schema")
    _claim(directory, head, caller)
    _require(_same(directory.read(START), _binding(head, caller)), "claim_binding")
    _require(_same(family._family_binding(directory, old, time.monotonic() + 30), record), "family_changed")
    organization = organization_reader._organization(directory, old)
    payloads = payload_reader._package_payloads(plan._input, old, record["upload_inventory"])
    _validate_census(directory, report, record["upload_inventory"], payloads, organization, include_final=True)
    _require("upload-valid.json" not in directory.names(), "admission_schema")
    directory.verify()
    return receipt
