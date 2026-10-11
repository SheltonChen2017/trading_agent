"""Pure prospective evidence contracts for the extended paired cap/tilt study.

No I/O, credentials, provider access or cloud operation occurs here. Concrete
bytes are mutually hash-bound; this is not remote authenticity, complete-ledger
custody, historical PIT or strategy acceptance. A future controller must provide
exclusive persistent claims and a complete consumed-attempt inventory. Historical
executed modules and receipts are never modified or implicitly admitted.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
import json
import re

STUDY_ID = "TPR-CAP-TILT-EXT26-20261010-v1"
FREEZE_SHA256 = "90bdec5520b29bd932a3ec730f7c4c40c544ea7582731ad6680ef34ea8cf4067"
CANDIDATES = {"TPR-CAP-TILT-EXT26-ON-BASE-v1": "tpr_on",
              "TPR-CAP-TILT-EXT26-OFF-BASE-v1": "tpr_off"}
MAX_BYTES, MAX_NODES, MAX_DEPTH = 16 * 1024 * 1024, 100000, 32
NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
REDACTION_POLICY = "tpr-ext26-structural-pii-v1"
_STAGES = {"files/read": "source_readback", "compile/read": "compile_status",
           "backtests/create": "backtest_launch", "backtests/read": "backtest_status"}
_PII_KEYS = frozenset({"userId", "user_id", "uid", "apiToken", "api_token",
                       "email", "firstName", "lastName", "name"})


class EvidenceError(ValueError):
    """Closed, sanitized refusal; never echoes private values."""


def _fail(message):
    raise EvidenceError(message)


def digest(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        _fail("bounded bytes required")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class JsonNumber:
    """An original JSON numeric token, not a binary float or boolean."""
    lexeme: str

    def __post_init__(self):
        if (type(self.lexeme) is not str or not 0 < len(self.lexeme) <= 128
                or NUMBER.fullmatch(self.lexeme) is None):
            _fail("bounded JSON numeric token required")
        try:
            number = Decimal(self.lexeme)
            if not number.is_finite() or not -128 <= number.as_tuple().exponent <= 128:
                _fail("bounded finite decimal required")
        except InvalidOperation:
            _fail("decimal token refused")

    def fraction(self):
        return Fraction(Decimal(self.lexeme))


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate JSON key")
        result[key] = value
    return result


def canonical(value):
    """Canonical structure preserving numeric token spelling exactly."""
    visited = 0
    def encode(item, depth=0):
        nonlocal visited
        visited += 1
        if depth > MAX_DEPTH or visited > MAX_NODES:
            _fail("JSON structure resource bound")
        if type(item) is JsonNumber:
            return item.lexeme
        if item is None:
            return "null"
        if type(item) is bool:
            return "true" if item else "false"
        if type(item) is int:
            return JsonNumber(str(item)).lexeme
        if type(item) is str:
            return json.dumps(item, ensure_ascii=True)
        if type(item) is list:
            return "[" + ",".join(encode(child, depth + 1) for child in item) + "]"
        if type(item) is dict and all(type(key) is str for key in item):
            return "{" + ",".join(json.dumps(key, ensure_ascii=True) + ":" +
                encode(item[key], depth + 1) for key in sorted(item)) + "}"
        _fail("unsupported exact JSON value")
    try:
        raw = (encode(value) + "\n").encode("ascii")
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        _fail("exact JSON serialization refused")
    if len(raw) > MAX_BYTES:
        _fail("JSON byte bound")
    return raw


def parse_json(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        _fail("bounded JSON bytes required")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
            parse_int=JsonNumber, parse_float=JsonNumber,
            parse_constant=lambda _: _fail("nonfinite JSON refused"))
        canonical(value)  # Validate depth, count, types and output budget.
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        _fail("exact JSON parsing refused")


def _pii_path(path):
    # Exact metadata channels only: an order's id/uid/name is not an account.
    if len(path) == 1:
        return path[0] in {"userId", "user_id", "apiToken", "api_token"}
    if path[-1] not in _PII_KEYS:
        return False
    parent = path[:-1]
    return (parent in {("user",), ("account",), ("metadata",)}
            or len(parent) == 2 and parent[0] == "collaborators" and type(parent[1]) is int
            or len(parent) == 4 and parent[0] == "projects" and type(parent[1]) is int
            and parent[2] == "collaborators" and type(parent[3]) is int)


def redact_metadata(value):
    """Copy known PII metadata paths; never replace digits inside values."""
    canonical(value)
    def walk(item, path=()):
        if type(item) is dict:
            return {key: "[redacted]" if _pii_path(path + (key,)) else walk(child, path + (key,))
                    for key, child in item.items()}
        if type(item) is list:
            return [walk(child, path + (index,)) for index, child in enumerate(item)]
        return item
    return walk(value)


def project_wire(raw, *, credential=""):
    """Hash original wire and distinct redacted projection after echo refusal.

    This function does not persist anything. Credential content is never hashed
    separately or returned. Free text is not silently repaired: any credential
    echo, including JSON-escaped text or keys, refuses the complete response.
    """
    if type(credential) is not str or re.fullmatch(r"[!-~]{0,256}", credential) is None:
        _fail("credential echo guard refused")
    value = parse_json(raw)
    def echo(item):
        if type(item) is str:
            return bool(credential) and credential in item
        if type(item) is dict:
            return any(echo(key) or echo(child) for key, child in item.items())
        if type(item) is list:
            return any(echo(child) for child in item)
        return False
    if credential and (credential.encode("utf-8") in raw or echo(value)):
        _fail("credential echo refused before evidence retention")
    projection = redact_metadata(value)
    return {"schema": "tpr-ext26-wire-projection-v1", "redaction_policy": REDACTION_POLICY,
            "original_wire_sha256": digest(raw), "original_wire_bytes": len(raw),
            "projection_sha256": digest(canonical(projection)), "projection": projection}


def _closed(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        _fail("closed evidence schema required")


def _hash(value, size=64):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{" + str(size) + "}", value) is None:
        _fail("exact evidence hash required")
    return value


def _id(value):
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9_.-]{1,200}", value) is None:
        _fail("typed returned identity required")
    return value


def _integer(value, maximum=2**63 - 1):
    text = str(value) if type(value) is int else value.lexeme if type(value) is JsonNumber else ""
    if re.fullmatch(r"[1-9][0-9]{0,18}", text) is None or not 1 <= int(text) <= maximum:
        _fail("exact positive integer identity required")
    return int(text)


def _manifest(raw, expected_hash):
    if digest(raw) != _hash(expected_hash):
        _fail("manifest content hash mismatch")
    body = parse_json(raw)
    _closed(body, {"schema", "study_id", "freeze_sha256", "candidate_id", "arm", "project_id",
                  "baseline_git_head", "config_sha256", "source_hashes", "input_hashes", "max_attempts"})
    if (body["schema"] != "tpr-ext26-execution-manifest-v1" or body["study_id"] != STUDY_ID
            or body["freeze_sha256"] != FREEZE_SHA256 or type(body["candidate_id"]) is not str
            or body["candidate_id"] not in CANDIDATES
            or body["arm"] != CANDIDATES[body["candidate_id"]]
            or _integer(body["max_attempts"], 3) != 3):
        _fail("extended study scope refused")
    _integer(body["project_id"])
    _hash(body["baseline_git_head"], 40)
    _hash(body["config_sha256"])
    sources = body["source_hashes"]
    if (type(sources) is not dict or not 2 <= len(sources) <= 32
            or not {"main.py", "extended_config.py"}.issubset(sources)):
        _fail("extended source inventory required")
    for name, identity in sources.items():
        if type(name) is not str or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}\.py", name) is None:
            _fail("source inventory name refused")
        _hash(identity)
    inputs = body["input_hashes"]
    if type(inputs) is not dict or not 1 <= len(inputs) <= 32:
        _fail("input inventory required")
    for name, identity in inputs.items():
        _id(name)
        _hash(identity)
    return body


def _reservation(raw, manifest, manifest_hash):
    body = parse_json(raw)
    _closed(body, {"schema", "study_id", "candidate_id", "attempt", "manifest_sha256", "project_id",
                  "config_sha256", "freeze_sha256", "source_hashes", "input_hashes", "state"})
    if body["schema"] != "tpr-ext26-attempt-reservation-v1" or body["state"] != "reserved":
        _fail("immutable attempt reservation required")
    for key in ("study_id", "candidate_id", "project_id", "config_sha256", "freeze_sha256",
                "source_hashes", "input_hashes"):
        if body[key] != manifest[key]:
            _fail("reservation and manifest differ")
    if body["manifest_sha256"] != manifest_hash:
        _fail("reservation manifest hash mismatch")
    _integer(body["attempt"], 3)
    return body


def _envelope(raw, request_keys, endpoint):
    body = parse_json(raw)
    _closed(body, {"schema", "endpoint", "stage", "request", "response"})
    if (body["schema"] != "tpr-ext26-request-response-v1" or body["endpoint"] != endpoint
            or body["stage"] != _STAGES[endpoint]):
        _fail("original response envelope required")
    _closed(body["request"], request_keys)
    response = body["response"]
    if type(response) is not dict or response.get("success") is not True:
        _fail("typed successful API response required")
    return body["request"], response


def _project(request, response, manifest):
    project = _integer(manifest["project_id"])
    if _integer(request["projectId"]) != project:
        _fail("request project identity mismatch")
    if "projectId" in response and _integer(response["projectId"]) != project:
        _fail("returned project identity mismatch")
    return project


def _compile(raw, manifest):
    request, response = _envelope(raw, {"projectId", "compileId"}, "compile/read")
    _project(request, response, manifest)
    identity = _id(request["compileId"])
    if _id(response.get("compileId")) != identity:
        _fail("returned compile identity mismatch")
    state = response.get("state")
    if type(state) is not str:
        _fail("typed concrete compile state required")
    return identity, state


def _config(raw, manifest):
    if digest(raw) != manifest["config_sha256"]:
        _fail("configuration hash mismatch")
    body = parse_json(raw)
    _closed(body, {"schema", "study_id", "candidate_id", "arm", "freeze_sha256", "input_hashes"})
    if body["schema"] != "tpr-ext26-config-v1":
        _fail("extended config required")
    for key in ("study_id", "candidate_id", "arm", "freeze_sha256", "input_hashes"):
        if body[key] != manifest[key]:
            _fail("configuration manifest mismatch")
    return body


def _readback(raw, config_raw, manifest):
    request, response = _envelope(raw, {"projectId"}, "files/read")
    _project(request, response, manifest)
    files = response.get("files")
    if type(files) is not list or len(files) != len(manifest["source_hashes"]):
        _fail("exact cloud source census required")
    hashes, config_text = {}, None
    for row in files:
        _closed(row, {"name", "content"})
        if type(row["name"]) is not str or row["name"] in hashes or type(row["content"]) is not str:
            _fail("exact cloud file identity refused")
        try:
            raw_source = row["content"].encode("utf-8")
        except UnicodeError:
            _fail("cloud source UTF8 refused")
        hashes[row["name"]] = digest(raw_source)
        if row["name"] == "extended_config.py":
            try:
                tree = ast.parse(row["content"])
                if (len(tree.body) != 1 or not isinstance(tree.body[0], ast.Assign)
                        or len(tree.body[0].targets) != 1 or not isinstance(tree.body[0].targets[0], ast.Name)
                        or tree.body[0].targets[0].id != "CONFIG_JSON"
                        or not isinstance(tree.body[0].value, ast.Constant)
                        or type(tree.body[0].value.value) is not str):
                    _fail("literal cloud configuration required")
                config_text = tree.body[0].value.value.encode("utf-8")
            except (ValueError, TypeError, SyntaxError, UnicodeError, RecursionError):
                _fail("literal cloud configuration refused")
    if hashes != manifest["source_hashes"] or config_text != config_raw:
        _fail("cloud content differs from expected source/configuration")
    return hashes


def validate_execution_binding(manifest_raw, *, expected_manifest_sha256, config_raw,
        reservation_raw, compile_response_raw, compile_receipt_raw, readback_raw, launch_raw):
    """Verify concrete source/compile/request evidence, not producer self-flags."""
    manifest = _manifest(manifest_raw, expected_manifest_sha256)
    _config(config_raw, manifest)
    reservation = _reservation(reservation_raw, manifest, expected_manifest_sha256)
    sources = _readback(readback_raw, config_raw, manifest)
    compile_id, state = _compile(compile_response_raw, manifest)
    if state != "BuildSuccess":
        _fail("concrete BuildSuccess required")
    receipt = parse_json(compile_receipt_raw)
    _closed(receipt, {"schema", "manifest_sha256", "reservation_sha256", "compile_response_sha256",
                      "source_readback_sha256", "project_id", "compile_id"})
    expected = {"schema": "tpr-ext26-verified-compile-v1", "manifest_sha256": expected_manifest_sha256,
        "reservation_sha256": digest(reservation_raw), "compile_response_sha256": digest(compile_response_raw),
        "source_readback_sha256": digest(readback_raw), "project_id": manifest["project_id"], "compile_id": compile_id}
    if receipt != expected:
        _fail("concrete compile/source receipt binding mismatch")
    request, response = _envelope(launch_raw, {"projectId", "compileId", "backtestName"}, "backtests/create")
    project = _project(request, response, manifest)
    attempt = _integer(reservation["attempt"], 3)
    if (request["compileId"] != compile_id
            or request["backtestName"] != manifest["candidate_id"] + "-attempt-" + str(attempt)):
        _fail("launch request candidate/compile mismatch")
    backtest = response.get("backtest")
    if type(backtest) is not dict:
        _fail("returned backtest identity missing")
    if "projectId" in backtest and _integer(backtest["projectId"]) != project:
        _fail("returned backtest project mismatch")
    if "compileId" in backtest and backtest["compileId"] != compile_id:
        _fail("returned backtest compile mismatch")
    return {"schema": "tpr-ext26-execution-binding-v1", "candidate_id": manifest["candidate_id"],
        "attempt": attempt, "project_id": project, "compile_id": compile_id,
        "backtest_id": _id(backtest.get("backtestId")), "manifest_sha256": expected_manifest_sha256,
        "source_hashes": sources, "compile_response_sha256": digest(compile_response_raw),
        "source_readback_sha256": digest(readback_raw), "launch_sha256": digest(launch_raw),
        "binding_validated": True, "remote_authenticity_attested": False, "canonical_admission": False}


def ledger_identity(prior):
    """Hash the exact supplied ledger census, including explicit absent stages.

    The expected identity must come from separately retained controller custody;
    recomputing it over selected supplied rows does not attest completeness.
    """
    if type(prior) is not list or len(prior) > 3:
        _fail("bounded attempt census required")
    rows = []
    for item in prior:
        _closed(item, {"manifest", "reservation", "closure", "compile_response", "launch", "backtest_response"})
        rows.append({name: None if raw is None else digest(raw) for name, raw in item.items()})
    return digest(canonical(rows))


def next_attempt(prior, *, candidate_id, consumed_count, expected_ledger_sha256):
    """Validate closed predecessors from a complete persistent consumed ledger.

    Exclusive reservation and completeness of the real ledger are controller
    duties, not caller-asserted attestations granted by this pure function.
    Unknown launches never close an attempt or refund its consumed slot.
    """
    if (type(candidate_id) is not str or candidate_id not in CANDIDATES
            or type(consumed_count) is not int or not 0 <= consumed_count <= 3
            or type(prior) is not list or len(prior) != consumed_count):
        _fail("complete bounded consumed-attempt ledger required")
    if ledger_identity(prior) != _hash(expected_ledger_sha256):
        _fail("retained complete ledger identity mismatch")
    if consumed_count == 3:
        _fail("three attempts consumed; no reset or refund")
    for index, item in enumerate(prior, 1):
        _closed(item, {"manifest", "reservation", "closure", "compile_response", "launch", "backtest_response"})
        manifest_hash = digest(item["manifest"])
        manifest = _manifest(item["manifest"], manifest_hash)
        reservation = _reservation(item["reservation"], manifest, manifest_hash)
        if manifest["candidate_id"] != candidate_id or _integer(reservation["attempt"], 3) != index:
            _fail("contiguous candidate attempt history required")
        closure = parse_json(item["closure"])
        _closed(closure, {"schema", "candidate_id", "attempt", "manifest_sha256", "reservation_sha256",
            "outcome", "compile_response_sha256", "launch_sha256", "backtest_response_sha256"})
        if (closure["schema"] != "tpr-ext26-closed-attempt-v1" or closure["candidate_id"] != candidate_id
                or _integer(closure["attempt"], 3) != index or closure["manifest_sha256"] != manifest_hash
                or closure["reservation_sha256"] != digest(item["reservation"])
                or closure["compile_response_sha256"] != digest(item["compile_response"])):
            _fail("closed attempt concrete binding mismatch")
        compile_id, state = _compile(item["compile_response"], manifest)
        if closure["outcome"] == "compile_failure":
            if (state not in {"BuildError", "Error", "Failed"} or item["launch"] is not None
                    or item["backtest_response"] is not None or closure["launch_sha256"] is not None
                    or closure["backtest_response_sha256"] is not None):
                _fail("known compile failure without launch required")
        elif closure["outcome"] == "backtest_terminal":
            if (state != "BuildSuccess" or closure["launch_sha256"] != digest(item["launch"])
                    or closure["backtest_response_sha256"] != digest(item["backtest_response"])):
                _fail("known terminal attempt concrete binding required")
            request, response = _envelope(item["launch"], {"projectId", "compileId", "backtestName"}, "backtests/create")
            project = _project(request, response, manifest)
            if (request["compileId"] != compile_id or request["backtestName"] != candidate_id + "-attempt-" + str(index)
                    or type(response.get("backtest")) is not dict):
                _fail("known launch identity required")
            identity = _id(response["backtest"].get("backtestId"))
            if ("projectId" in response["backtest"] and _integer(response["backtest"]["projectId"]) != project
                    or "compileId" in response["backtest"] and response["backtest"]["compileId"] != compile_id):
                _fail("returned launch project/compile mismatch")
            status_request, status_response = _envelope(item["backtest_response"], {"projectId", "backtestId"}, "backtests/read")
            _project(status_request, status_response, manifest)
            terminal = status_response.get("backtest")
            if (status_request["backtestId"] != identity or type(terminal) is not dict
                    or terminal.get("backtestId") != identity or terminal.get("completed") is not True
                    or type(terminal.get("status")) is not str
                    or terminal.get("status") not in {"Completed", "Completed.", "Runtime Error", "Error", "Stopped", "Cancelled"}
                    or "error" not in terminal
                    or not (terminal["error"] is None or type(terminal["error"]) is str and bool(terminal["error"]))):
                _fail("exact known terminal backtest required")
            if "projectId" in terminal and _integer(terminal["projectId"]) != project:
                _fail("terminal returned project mismatch")
            if "compileId" in terminal and terminal["compileId"] != compile_id:
                _fail("terminal returned compile mismatch")
            if terminal["status"] in {"Completed", "Completed."}:
                progress = terminal.get("progress")
                if not (type(progress) is JsonNumber and progress.fraction() == 1
                        or type(progress) is int and progress == 1):
                    _fail("concrete complete progress required")
            if terminal["status"] in {"Runtime Error", "Error"} and terminal["error"] is None:
                _fail("known terminal error evidence required")
        else:
            _fail("unresolved or ambiguous predecessor blocks retry")
    return consumed_count + 1
