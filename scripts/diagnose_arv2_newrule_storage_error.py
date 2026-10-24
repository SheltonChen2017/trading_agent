"""One fresh, redacted QC storage-error observation; never upload admission.

This diagnostic deliberately reads a bounded JSON body even for non-2xx HTTP
responses. Only a fixed public vocabulary survives redaction; omitted spans
remain visible as placeholders so filtering cannot join a misleading sentence.
Provider text is a partial reported reason, not an authenticated root cause.
"""
from __future__ import annotations

import argparse
import base64
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
import urllib.parse
import urllib.request

ROOT = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_arv2_newrule_comparison as frozen

helpers = frozen.helpers
SOURCE = ROOT / "scripts/diagnose_arv2_newrule_storage_error.py"
CONTROL = ROOT / "artifacts/analyst_revisions_v2/newrule_comparison_qc/R298-R303-20261013"
SCHEMA = "arv2-newrule-storage-error-diagnostic-v1"
CLAIM, START, REPORT = ("storage-error-diagnostic-v1-" + name + ".json"
                        for name in ("claim", "request-intent", "report"))
FAMILY_SHA256 = "8b8ee913dcfb5ad37f4748ea70db4fcbd6ff15580e52cd160bccf2b37e10a9e5"
INVENTORY_SHA256 = "b35e1bb0dfc887d6d775a7dd89155a1e8a703ee2aad148aa69cab52b718359c8"
ORGANIZATION_SHA256 = "a2d88859373df0f1fd59ede52b9b3945f847091b5fca3286841241536c38e880"
REQUEST_SHA256 = "66d7248124554ac8daccecc7f1739eade6fe067db30a62df0c3e5eec19fff6a7"
D12_REPORT_SHA256 = "0d8fa1b57c8caf25b2cd16a039c3a3361a518412db912d17cd92c058f7f82b39"
FROZEN_CALLER_SHA256 = "533c1ebf520e9ebf836c78067b9b1480eccf49cfb01aaeb240e3a73b77087d05"
PINS = {
    "scripts/run_arv2_newrule_comparison.py": FROZEN_CALLER_SHA256,
    "scripts/diagnose_arv2_newrule_upload.py": "b8477fe9246b7355c9b10bec91a9ad6e6305fcd0a7e2d4f00f61da1c35ce9901",
    "scripts/diagnose_arv2_newrule_object_metadata.py": "0a566b6b049f160daf6cc1a1bb2a507e18dd645c64d948dea50136cebbbede23",
}
ENDPOINT, OBJECT_INDEX = "object/properties", 0
DEADLINE_SECONDS, REQUEST_SECONDS = 90, 30
MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, MAX_OUTPUT_BYTES = 4096, 16 * 1024, 16 * 1024
MAX_ERRORS, MAX_ERROR_CHARACTERS, MAX_SECRET_CHARACTERS = 8, 512, 8192
REDACTED = "[redacted]"
VOCABULARY = frozenset("""
a an and are as at be been being by can cannot could data denied deny disabled do
does enabled enable error exceeded exceed expired expires failed failure file files
for found from get has have in insufficient invalid is it key keys limit limited
limits maximum max may member membership metadata missing no not of on only or
organization organisations organizations owner path permission permissions plan
please product products properties quota quotas read reading request required requires
resource resources researcher research restricted restriction size storage store
subscription subscriptions support that the this to token too unauthorized unavailable
upgrade upgraded upgrading upload use used user users valid was were with without
write writing you your access account allocation amount authentication authorization
available byte bytes capacity create creation custom customdata download downloading
exist exists existing free full grant granted higher institution institutional licence
license licensed network operation permitted provision provisioned rate reached remaining
response retry service setting settings space successful success tier total unable
unable unrecognized verify verification wrong purchased paid permissioned allow allowed
doesnt dont cant needs need must contact manage managing enabled storagecreate storageread
object objects derivative export
""".split())
FLAGS = {"diagnostic_only": True, "original_upload_accepted": False,
    "storage_recovery_accepted": False, "absence_established": False,
    "fix_established": False, "provider_reason_is_root_cause": False,
    "reason_text_is_partial": True, "changes_original_exit": False,
    "measured_server_contact": False, "point_in_time_proven": False,
    "formal_forward_ready": False, "paper_or_live_ready": False}
PROFILE = {"schema": SCHEMA, "root": str(ROOT), "control": str(CONTROL),
    "branch": frozen.BRANCH, "python": str(frozen.PYTHON), "family_sha256": FAMILY_SHA256,
    "inventory_sha256": INVENTORY_SHA256, "organization_sha256": ORGANIZATION_SHA256,
    "source_pins": dict(frozen.SOURCE_PINS), "new_pins": PINS,
    "historical_d12_report_sha256_not_reread": D12_REPORT_SHA256,
    "endpoint": ENDPOINT, "index": OBJECT_INDEX, "request_sha256": REQUEST_SHA256,
    "request_limit": 1, "claim": CLAIM, "request_intent": START, "report": REPORT,
    "deadline_seconds": DEADLINE_SECONDS, "request_seconds": REQUEST_SECONDS,
    "max_request_bytes": MAX_REQUEST_BYTES, "max_response_bytes": MAX_RESPONSE_BYTES,
    "max_output_bytes": MAX_OUTPUT_BYTES, "max_errors": MAX_ERRORS,
    "max_error_characters": MAX_ERROR_CHARACTERS, "max_secret_characters": MAX_SECRET_CHARACTERS,
    "retained_vocabulary": sorted(VOCABULARY), "unknown_span_marker": REDACTED,
    "non2xx_json_body_read": True, "redirects_proxies_retries": False,
    "package_or_old_report_read": False, **FLAGS}
PROFILE_SHA256 = hashlib.sha256(helpers.canonical_json_bytes(PROFILE)).hexdigest()


class DiagnosticRefusal(ValueError):
    pass


def _require(condition, code="diagnostic_refused"):
    if not condition:
        raise DiagnosticRefusal(code)


def _same(left, right):
    return type(left) is type(right) and helpers.canonical_json_bytes(left) == helpers.canonical_json_bytes(right)


def _git(arguments, deadline, limit=65536):
    value = subprocess.run(["git", *arguments], cwd=ROOT, stdin=subprocess.DEVNULL,
        capture_output=True, check=False, timeout=min(3, helpers._remaining(deadline)))
    _require(type(value.returncode) is int and value.returncode == 0 and value.stderr == b""
        and type(value.stdout) is bytes and len(value.stdout) <= limit, "source_binding")
    return value.stdout


def _preflight(head, caller, deadline):
    _require("PYTEST_CURRENT_TEST" not in os.environ and "pytest" not in sys.modules
        and not any(name == "_pytest" or name.startswith("_pytest.") for name in tuple(sys.modules)),
        "operational_test_context")
    _require(Path(__file__).absolute() == SOURCE and 0 < deadline - time.monotonic() <= DEADLINE_SECONDS,
        "source_binding")
    frozen._preflight(SimpleNamespace(operation="summarize", expected_head=head,
        caller_sha256=FROZEN_CALLER_SHA256, candidate=None, attempt=None,
        family_sha256=FAMILY_SHA256, prior_failure_sha256=None, justification_sha256=None), deadline)
    helpers.require_sha256(caller, "caller")
    _require(helpers._source_digest(SOURCE) == caller, "source_binding")
    for relative, expected in PINS.items():
        _require(helpers._source_digest(ROOT / relative) == expected, "source_binding")
    selected = head + ":" + SOURCE.relative_to(ROOT).as_posix()
    count = _git(["cat-file", "-s", selected], deadline).decode("ascii").strip()
    _require(re.fullmatch(r"[1-9][0-9]{0,6}", count) is not None and int(count) <= 2 * 1024 * 1024,
        "source_binding")
    raw = _git(["cat-file", "blob", selected], deadline, int(count))
    _require(len(raw) == int(count) and hashlib.sha256(raw).hexdigest() == caller
        and _git(["rev-parse", "HEAD"], deadline).decode("ascii").strip() == head
        and _git(["status", "--porcelain"], deadline) == b"", "source_binding")


def _dependencies():
    from scripts import diagnose_arv2_newrule_upload as family
    from scripts import diagnose_arv2_newrule_object_metadata as organization
    from research.analyst_revisions_v2_qc import newrule_comparison_submission as submission
    _require(submission.ROOT == ROOT and submission.CONTROL == CONTROL, "source_binding")
    return family, organization, submission


def _retained(directory, modules, deadline):
    family, organization, submission = modules
    record = family._family_binding(directory, submission, deadline)
    inventory = record["upload_inventory"]
    _require(len(inventory) == 6 and hashlib.sha256(helpers.canonical_json_bytes(inventory)).hexdigest()
        == INVENTORY_SHA256, "inventory_binding")
    return inventory[OBJECT_INDEX], organization._organization(directory, submission)


def _json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            _require(key not in value, "response_json")
            value[key] = item
        return value
    def nonfinite(_):
        raise DiagnosticRefusal("response_nonfinite")
    def number(text):
        value = float(text)
        _require(math.isfinite(value), "response_nonfinite")
        return value
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
        parse_constant=nonfinite, parse_float=number)


def _secret_variants(secrets):
    _require(type(secrets) is tuple and 4 <= len(secrets) <= 8, "redaction_binding")
    variants = set()
    for secret in secrets:
        _require(type(secret) is str and 0 < len(secret) <= MAX_SECRET_CHARACTERS, "redaction_binding")
        variants.add(secret)
        variants.add(json.dumps(secret, ensure_ascii=True)[1:-1])
        variants.add(base64.b64encode(secret.encode("utf-8")).decode("ascii"))
        for encode in (urllib.parse.quote, urllib.parse.quote_plus):
            once = encode(secret, safe="")
            variants.update((once, encode(once, safe="")))
    return tuple(sorted(variants, key=lambda value: (-len(value), value)))


def _sanitize_error(error, variants):
    _require(type(error) is str and len(error) <= MAX_ERROR_CHARACTERS, "error_schema")
    text = error
    # Redact both encoded and decoded known values before lexical projection.
    for _ in range(3):
        for secret in variants:
            text = re.sub(re.escape(secret), " REDACTEDSPAN ", text, flags=re.IGNORECASE)
        text = urllib.parse.unquote_plus(text, errors="replace")
    for secret in variants:
        text = re.sub(re.escape(secret), " REDACTEDSPAN ", text, flags=re.IGNORECASE)
    for before, after in (("doesn't", "does not"), ("don't", "do not"), ("can't", "cannot"),
                          ("storage/create", "storage create"), ("storage/read", "storage read")):
        text = re.sub(re.escape(before), after, text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)(?:https?://|www\.)\S+|\S+@\S+", " REDACTEDSPAN ", text)
    text = re.sub(r"(?:[A-Za-z]:[\\/]|[~]?[\\/])[^\s,;]*|\b[\w.+-]+[\\/][^\s,;]*",
                  " REDACTEDSPAN ", text)
    output = []
    for token in re.findall(r"[^\s,;:()[\]{}<>!?=]+", text):
        word = token.strip(".\"'“”‘’").lower()
        accepted = re.fullmatch(r"[a-z]+", word) is not None and word in VOCABULARY
        current = word if accepted else REDACTED
        if current != REDACTED or not output or output[-1] != REDACTED:
            output.append(current)
    result = " ".join(output) or REDACTED
    _require(len(result) <= 2 * MAX_ERROR_CHARACTERS, "redaction_bound")
    return result


def _observation(raw, secrets):
    value = _json(raw)
    _require(type(value) is dict and set(value) <= {"success", "errors", "metadata"}
        and ("success" not in value or type(value["success"]) is bool), "response_schema")
    errors = value.get("errors", [])
    _require(type(errors) is list and len(errors) <= MAX_ERRORS
        and all(type(item) is str and len(item) <= MAX_ERROR_CHARACTERS for item in errors), "error_schema")
    variants = _secret_variants(secrets)
    reasons = [_sanitize_error(item, variants) for item in errors]
    return {"response_schema_valid": True, "api_success": value.get("success"),
        "errors_present": "errors" in value, "error_count": len(errors),
        "redacted_provider_reasons": reasons, "reason_has_redacted_spans": [REDACTED in item for item in reasons],
        "redacted_span_counts": [item.count(REDACTED) for item in reasons],
        "metadata_present": "metadata" in value,
        "success_with_errors": value.get("success") is True and bool(errors)}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def _transport(api, submission, body, organization, key, state, deadline):
    _require(type(body) is bytes and 0 < len(body) <= MAX_REQUEST_BYTES
        and state["attempted_request_count"] == 0, "request_scope")
    submission._safe_environment()
    headers = submission.build_auth_headers(api._credentials, api._clock())
    headers["Content-Type"] = "application/json"
    secrets = (api._credentials.user_id, api._credentials.api_token, organization, key,
               headers["Authorization"], headers["Timestamp"])
    _secret_variants(secrets)  # shape checks before dispatch, no fallback or output
    url = submission.API_BASE + "/" + ENDPOINT
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    opener = _opener()
    timeout = min(REQUEST_SECONDS, helpers._remaining(deadline))
    response = None
    state["attempted_request_count"] = 1
    try:
        try:
            response = opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            response = error
        status = response.code
        _require(type(status) is int and 100 <= status <= 599 and response.geturl() == url, "response_transport")
        state["http_status"] = status
        helpers._remaining(deadline)
        # Deliberate new purpose: bounded non-2xx error JSON, never old upload replay.
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        _require(type(raw) is bytes and len(raw) <= MAX_RESPONSE_BYTES, "response_bound")
        helpers._remaining(deadline)
        return _observation(raw, secrets)
    finally:
        if response is not None:
            response.close()


_CODES = frozenset("""diagnostic_refused source_binding operational_test_context inventory_binding
request_scope response_transport response_bound response_json response_nonfinite response_schema error_schema
redaction_binding redaction_bound source_postcheck publication_ambiguous""".split())


def _failure(error, modules=None):
    if type(error) is DiagnosticRefusal:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and len(args[0]) <= 64 and args[0] in _CODES:
            return args[0]
    if modules is not None and any(type(error) is kind for kind in
                                  (modules[0].DiagnosticRefusal, modules[1].DiagnosticRefusal)):
        return "dependency_validation_refused"
    for kind, label in ((frozen.OperationRefusal, "preflight_refused"), (helpers.Deadline, "deadline"),
        (FileExistsError, "claim_or_report_exists"), (FileNotFoundError, "file_missing"),
        (PermissionError, "permission_error"), (urllib.error.URLError, "transport_error"),
        (TimeoutError, "transport_timeout"), (json.JSONDecodeError, "response_json"),
        (UnicodeDecodeError, "response_encoding"), (RecursionError, "response_depth"),
        (KeyboardInterrupt, "cancelled"), (SystemExit, "cancelled"), (OSError, "os_error"),
        (ValueError, "value_error"), (TypeError, "type_error"), (KeyError, "key_error")):
        if type(error) is kind:
            return label
    return "unknown_exception"


def _safe_pin(value, size):
    return value if type(value) is str and re.fullmatch(r"[0-9a-f]{" + str(size) + "}", value) else None


def _run(head, caller, deadline):
    directory, modules, claim, observation, failure = None, None, None, None, None
    stage, consumed = "preflight", False
    state = {"attempted_request_count": 0, "http_status": None}
    started = helpers._utc_now()
    try:
        _preflight(head, caller, deadline)
        modules = _dependencies()
        submission = modules[2]
        stage = "claim"
        directory = submission._Directory()
        claim = {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256, "family_sha256": FAMILY_SHA256,
            "expected_head": head, "caller_sha256": caller, "attempt_consumed": True}
        consumed = None
        directory.write(CLAIM, claim)
        consumed, stage = True, "retained_authentication"
        row, organization = _retained(directory, modules, deadline)
        body = helpers.canonical_json_bytes({"organizationId": organization, "key": row[0]})
        _require(hashlib.sha256(body).hexdigest() == REQUEST_SHA256, "request_scope")
        directory.write(START, {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256,
            "family_sha256": FAMILY_SHA256, "endpoint": ENDPOINT, "index": OBJECT_INDEX,
            "request_sha256": REQUEST_SHA256})
        stage = "credentials"
        api = submission._client()
        stage = "error_request"
        observation = _transport(api, submission, body, organization, row[0], state, deadline)
        stage = "post_authentication"
        _require(_same(_retained(directory, modules, deadline), (row, organization)), "source_postcheck")
        _preflight(head, caller, deadline)
        stage = "diagnostic_completed"
    except BaseException as error:
        observation, failure = None, _failure(error, modules)
    try:
        helpers._remaining(deadline)
        report = {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256, "family_sha256": FAMILY_SHA256,
            "expected_head": _safe_pin(head, 40), "caller_sha256": _safe_pin(caller, 64),
            "historical_d12_report_sha256_not_reread": D12_REPORT_SHA256,
            "started_at": started, "finished_at": helpers._utc_now(), "stage": stage,
            "terminal": "storage_response_observed" if observation is not None else "diagnostic_refused",
            "attempt_consumed": consumed, "failure_code": failure, "endpoint": ENDPOINT,
            "index": OBJECT_INDEX, "request_sha256": REQUEST_SHA256, **state, "observation": observation, **FLAGS}
        raw = helpers.canonical_json_bytes(report)
        _require(len(raw) <= MAX_OUTPUT_BYTES - 512, "publication_ambiguous")
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
                directory.verify()
            finally:
                directory.__exit__(None, None, None)


def run(args):
    deadline = time.monotonic() + DEADLINE_SECONDS
    try:
        with helpers._alarm(deadline):
            value, code = _run(args.expected_head, args.caller_sha256, deadline)
            payload = helpers.canonical_json_bytes(value)
            _require(len(payload) <= MAX_OUTPUT_BYTES, "publication_ambiguous")
            helpers._remaining(deadline)
            print(payload.decode("ascii"))
            return code
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
