"""Single NEW notebook wrapper; pure builders, no implicit research operation.

Root verified official QuantBook source exposes project_id. That observation
is mutable runtime configuration, NOT cryptographic/native custody or source
attestation. A genuine Mia create/execute tool supplies the external capsule.
One QuantBook construction initializes research-node/platform infrastructure;
do not misdescribe that initialization as only four total runtime I/O calls.
"""
from __future__ import annotations

import ast
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from types import SimpleNamespace

from . import extended_refusal_witness_read_design as reader

PROJECT = reader.PROJECT
NOTEBOOK = "tpr_ext26_witness_read_20261022_001.ipynb"
OPERATION = "TPR-EXT26-MIA-WITNESS-NOTEBOOK-READ-20261022-001"
DEADLINE_UTC = "2026-10-22T01:35:00+00:00"
MAX_SECONDS = 600
READER_SHA256 = "6ee5593ed2fe5e504fcef867219e5ba4a0c5883d0294a6544c3636440a8b1d22"
READER_PROGRAM_SHA256 = "c7b677612b01ace2bb019e94f3047449cbf6c98cc55614b8ad5de9bb11f7e88e"
_IMPORT = "from . import extended_refusal_witness_read_design as reader\n"
_CAPSULE_KEYS = frozenset(("schema operation_id tool_project_id notebook_filename "
    "creation_metadata_sha256 tool_context_identity_sha256 project_identity_provenance").split())


def _fail():
    raise ValueError("bounded new-notebook witness read refused")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def validate_capsule(capsule):
    """Shape/binding only: actual authenticated tool provenance is external."""
    if (type(capsule) is not dict or set(capsule) != _CAPSULE_KEYS
            or capsule["schema"] != "tpr-ext26-new-notebook-context-v1"
            or capsule["operation_id"] != OPERATION
            or type(capsule["tool_project_id"]) is not int or capsule["tool_project_id"] != PROJECT
            or capsule["notebook_filename"] != NOTEBOOK
            or capsule["project_identity_provenance"] != "genuine_mia_research_tool_metadata"):
        _fail()
    for key in ("creation_metadata_sha256", "tool_context_identity_sha256"):
        if type(capsule[key]) is not str or re.fullmatch(r"[a-f0-9]{64}", capsule[key]) is None:
            _fail()
    return _canonical(capsule)


def _utc(value):
    if type(value) is not datetime or value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
        _fail()
    return value


def _tick(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        _fail()
    return value


def read_new_notebook(qb, capsule, *, utc_now, monotonic_clock, reference_equals,
                      started_utc, started_monotonic):
    """Caller supplies actual UTC/monotonic/native-reference functions.

    Real execution uses datetime.now(timezone.utc), time.monotonic and
    System.Object.ReferenceEquals. Synthetic injected functions prove only
    software semantics. Scope does not extend the fixed deadline or permit
    another run. No store writes/enumeration/History/launch occur here.
    """
    result = {"schema": "tpr-ext26-new-notebook-witness-read-result-v1", "status": "failed_or_uncertain",
        "notebook_filename": NOTEBOOK, "operation_id": OPERATION, "diagnostic": None,
        "native_internal_project_id_observed": False, "native_project_custody_proven": False,
        "cryptographic_project_attestation_proven": False, "external_capsule_authentication_proven": False,
        "historical_compiled_source_proven": False, "new_jobs": 0, "new_codex_attempts": 0,
        "research_node_initialization_may_use_platform_infrastructure": True,
        "explicit_price_history_provider_requests": 0, "sdk_hard_timeout_proven": False,
        "byte_bound_before_native_allocation_proven": False}
    try:
        if not all(callable(value) for value in (utc_now, monotonic_clock, reference_equals)):
            _fail()
        original_capsule = validate_capsule(capsule)
        begin, tick = _utc(started_utc), _tick(started_monotonic)
        deadline = datetime.fromisoformat(DEADLINE_UTC)
        if begin >= deadline: _fail()
        if type(qb.project_id) is not int or qb.project_id != PROJECT:
            _fail()
        store = qb.object_store

        def check():
            now, current_tick = _utc(utc_now()), _tick(monotonic_clock())
            if (now < begin or now >= deadline or current_tick < tick or current_tick - tick >= MAX_SECONDS
                    or (now - begin).total_seconds() >= MAX_SECONDS):
                _fail()
            if validate_capsule(capsule) != original_capsule:
                _fail()
            if type(qb.project_id) is not int or qb.project_id != PROJECT:
                _fail()
            if reference_equals(store, qb.object_store) is not True:
                _fail()

        check()
        result["native_internal_project_id_observed"] = True
        result["external_capsule_sha256"] = _sha(original_capsule)
        result["diagnostic"] = reader.read_native_witnesses(
            store, observed_project_id=qb.project_id, scope_check=check)
        check()
        if result["diagnostic"]["status"] == "completed_diagnostic_only":
            result["status"] = "completed_diagnostic_only"
    except Exception:
        # No private/native exception text or source/market content is returned.
        result["status"] = "failed_or_uncertain"
    return result


def build_notebook_cell(module_raw, *, expected_module_sha256, reader_raw, witness_raw, capsule):
    """One public cell; genuine tools create a collision-free NEW notebook first.

    The capsule must come from that actual own-project tool response, not a
    fabricated constant claiming native custody. Its body-free hashes and the
    final cell hash must be retained by the actual effect controller. Building
    this cell does NOT create a notebook or authenticate supplied metadata.
    """
    capsule = json.loads(validate_capsule(capsule))
    if (type(module_raw) is not bytes or not 0 < len(module_raw) <= 16384
            or type(expected_module_sha256) is not str or re.fullmatch(r"[a-f0-9]{64}", expected_module_sha256) is None
            or _sha(module_raw) != expected_module_sha256
            or type(reader_raw) is not bytes or _sha(reader_raw) != READER_SHA256):
        _fail()
    program = reader.build_native_program(reader_raw, expected_module_sha256=READER_SHA256, witness_raw=witness_raw)
    if _sha(program.encode()) != READER_PROGRAM_SHA256:
        _fail()
    calls = [node for node in ast.walk(ast.parse(program)) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id == "compile"]
    if len(calls) != 1 or not isinstance(calls[0].args[0], ast.Constant) or type(calls[0].args[0].value) is not str:
        _fail()
    reader_source = calls[0].args[0].value
    try: source = module_raw.decode("utf-8")
    except UnicodeError: _fail()
    if source.count(_IMPORT) != 1: _fail()
    ast.parse(source)
    wrapper_source = source.replace(_IMPORT, "reader = _tpr_reader_namespace\n", 1)
    # The actual cell uses only actual clock/reference functions, not no-op
    # guards or a constant configured ID standing in for qb.project_id.
    return ("import json as _tpr_json\n"
        "from datetime import datetime as _tpr_datetime, timezone as _tpr_timezone\n"
        "import time as _tpr_time\n"
        "from types import SimpleNamespace as _tpr_namespace_type\n"
        "_tpr_begin = _tpr_datetime.now(_tpr_timezone.utc)\n"
        "_tpr_tick = _tpr_time.monotonic()\n"
        "if _tpr_begin >= _tpr_datetime.fromisoformat(" + repr(DEADLINE_UTC) + "):\n"
        "    print(_tpr_json.dumps({'status':'STOP_FIXED_DEADLINE_EXPIRED','effects':0}))\n"
        "else:\n"
        "    try:\n"
        "        _tpr_reader = {}\n"
        "        exec(compile(" + repr(reader_source) + ", '<pinned-public-witness-reader>', 'exec'), _tpr_reader)\n"
        "        _tpr_wrapper = {'_tpr_reader_namespace':_tpr_namespace_type(**_tpr_reader)}\n"
        "        exec(compile(" + repr(wrapper_source) + ", '<exact-public-notebook-wrapper>', 'exec'), _tpr_wrapper)\n"
        "        from QuantConnect.Research import QuantBook as _tpr_QuantBook\n"
        "        from System import Object as _tpr_NativeObject\n"
        "        _tpr_qb = _tpr_QuantBook()\n"
        "        _tpr_result = _tpr_wrapper['read_new_notebook'](_tpr_qb, " + repr(capsule) + ",\n"
        "            utc_now=lambda:_tpr_datetime.now(_tpr_timezone.utc), monotonic_clock=_tpr_time.monotonic,\n"
        "            reference_equals=_tpr_NativeObject.ReferenceEquals, started_utc=_tpr_begin, started_monotonic=_tpr_tick)\n"
        "        print(_tpr_json.dumps(_tpr_result, sort_keys=True, separators=(',',':')))\n"
        "    except Exception:\n"
        "        print(_tpr_json.dumps({'status':'STOP_NATIVE_CONTEXT_UNAVAILABLE_OR_REFUSED','details_withheld':True}))\n")
