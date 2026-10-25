"""Pure source builder for a prospective ephemeral witness diagnostic.

This module performs no I/O and creates no operation, active permit, notebook,
QuantBook or job. The generated text MUST NOT be dispatched without a fresh
bounded controller scope and owner release of QC. Shape-valid permit/context
inputs are not authority or authenticated native custody. Existing forensic
programs remain unchanged and are not called by this successor.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import textwrap
from types import SimpleNamespace

from . import extended_refusal_witness_runtime_successor as runtime

MAX_SOURCE_BYTES = 32768
MAX_PROGRAM_BYTES = 98304
SOURCE_SHA256 = {
    "runtime": "cf8cd1a2c58af31643f14061cc170e99e020172f22ca7619588d801c4dae9d4f",
    "reader": "6ee5593ed2fe5e504fcef867219e5ba4a0c5883d0294a6544c3636440a8b1d22",
    "witness": "1b057f254fba91eee98862bbb63b2141cea63962905c458459d7a47531215a0f",
}
_HASH = re.compile(r"[a-f0-9]{64}")
_READER_IMPORT = "from . import extended_refusal_witness_context_successor as witness\n"
_RUNTIME_IMPORT = "from . import extended_refusal_witness_read_design as predecessor\n"
_WITNESS_FIELDS = frozenset(("PROJECT MAX_BYTES OPERATION CANDIDATE CONFIG_SHA256 FREEZE_SHA256 "
    "CALENDAR_SHA256 ETFS ACTION_KEYS CLR_NUMBERS REFUSALS").split())
_READER_FUNCTIONS = frozenset(("_fail _sha _canonical _closed witness_key _typename _number _scalar "
    "_clock _relations _details project_witness _native_bytes").split())
_READER_VALUES = frozenset(("PROJECT JOB KINDS MAX_BYTES MAX_SOURCE_BYTES HELPER_SHA256 INPUT_HASHES "
    "_DEPENDENCY_IMPORT _TYPE _SID _NUMBER _CLOCK _ROOT_KEYS _MEMBER_KEYS _MARK_KEYS").split())


class ProgramBuildRefusal(ValueError):
    """Body-free refusal; no source, native errors or supplied metadata."""


def _fail():
    raise ProgramBuildRefusal("prospective witness program build refused")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def _raw(raw, expected):
    if (type(raw) is not bytes or not 0 < len(raw) <= MAX_SOURCE_BYTES
            or type(expected) is not str or _HASH.fullmatch(expected) is None
            or hashlib.sha256(raw).hexdigest() != expected):
        _fail()
    try:
        source = raw.decode("utf-8")
        ast.parse(source)
    except (UnicodeError, SyntaxError, ValueError, RecursionError):
        _fail()
    return source


def _contract(witness_source):
    values = {}
    for node in ast.parse(witness_source).body:
        if (not isinstance(node, ast.Assign) or len(node.targets) != 1
                or not isinstance(node.targets[0], ast.Name)):
            continue
        name = node.targets[0].id
        if name not in _WITNESS_FIELDS:
            continue
        value = node.value
        if isinstance(value, ast.Call):
            if (not isinstance(value.func, ast.Name) or value.func.id != "frozenset"
                    or len(value.args) != 1 or value.keywords):
                _fail()
            parsed = frozenset(ast.literal_eval(value.args[0]))
        else:
            parsed = ast.literal_eval(value)
        if name in values or parsed != getattr(runtime.predecessor.witness, name):
            _fail()
        values[name] = parsed
    if set(values) != _WITNESS_FIELDS:
        _fail()
    return {key: sorted(value) if type(value) is frozenset else value for key, value in values.items()}


def _projection_source(reader_source, contract):
    """Exact pinned input; emit ONLY the closed projection dependency set.

    The predecessor's unsafe read_native_witnesses/build_native_program and
    external scope callback never enter the generated executable namespace.
    """
    selected, functions, values, classes = [], set(), set(), set()
    for node in ast.parse(reader_source).body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.level:
                if ast.get_source_segment(reader_source, node) + "\n" != _READER_IMPORT:
                    _fail()
                continue
            selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in _READER_FUNCTIONS:
            selected.append(node); functions.add(node.name)
        elif isinstance(node, ast.ClassDef) and node.name == "WitnessReadRefusal":
            selected.append(node); classes.add(node.name)
        elif isinstance(node, ast.Assign):
            if (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id in _READER_VALUES):
                selected.append(node); values.add(node.targets[0].id)
    if functions != _READER_FUNCTIONS or values != _READER_VALUES or classes != {"WitnessReadRefusal"}:
        _fail()
    source = ast.unparse(ast.Module(body=selected, type_ignores=[]))
    dependency = ("_tpr_contract = json.loads(" + repr(_canonical(contract).decode()) + ")\n"
        "for _tpr_field in ('ETFS', 'ACTION_KEYS', 'CLR_NUMBERS'):\n"
        "    _tpr_contract[_tpr_field] = frozenset(_tpr_contract[_tpr_field])\n"
        "witness = SimpleNamespace(**_tpr_contract)\n")
    # Future imports must remain first. Insert the literal contract immediately
    # before the first constant using witness, after the standard imports.
    marker = "PROJECT = witness.PROJECT"
    if source.count(marker) != 1:
        _fail()
    return source.replace(marker, dependency + marker, 1) + "\n"


def validate_sources(*, builder_raw, expected_builder_sha256, runtime_raw, reader_raw, witness_raw):
    """No file reads. Outer controller must separately freeze the builder pin.

    Comparing supplied builder bytes with a supplied expected digest binds
    those inputs, not this imported module's own native execution identity.
    Dependency digests below are independent constants, not caller policy.
    """
    _raw(builder_raw, expected_builder_sha256)
    result = {name: _raw(raw, SOURCE_SHA256[name]) for name, raw in
        (("runtime", runtime_raw), ("reader", reader_raw), ("witness", witness_raw))}
    if result["runtime"].count(_RUNTIME_IMPORT) != 1 or result["reader"].count(_READER_IMPORT) != 1:
        _fail()
    return result


def build_program(*, builder_raw, expected_builder_sha256, runtime_raw, reader_raw, witness_raw, permit, capsule):
    """Return text only, using explicit prospective inputs with no active dates.

    Existing ``qb`` and ``TPR_EPHEMERAL_CONTEXT`` globals are required in a
    genuine ephemeral tool. The program never constructs or replaces qb and
    never takes clocks/reference callbacks from externally supplied globals.
    Native System import happens only AFTER source, context and deadline checks.
    Actual native custody and hard SDK timeouts remain unproved.
    """
    try:
        sources = validate_sources(builder_raw=builder_raw, expected_builder_sha256=expected_builder_sha256,
            runtime_raw=runtime_raw, reader_raw=reader_raw, witness_raw=witness_raw)
        permit_wire = runtime.validate_permit(permit)
        capsule_wire = runtime.validate_capsule(capsule, operation_id=permit["operation_id"])
        contract = _contract(sources["witness"])
        projection = _projection_source(sources["reader"], contract)
        runtime_source = sources["runtime"].replace(_RUNTIME_IMPORT, "predecessor = _tpr_projection\n", 1)
        # Verify ALL original source bytes again in the standalone text before
        # executing either generated namespace or consulting any native getter.
        bindings = {name: {"raw": sources[name], "sha256": SOURCE_SHA256[name]} for name in SOURCE_SHA256}
        payloads = {name: {"raw": raw, "sha256": hashlib.sha256(raw.encode()).hexdigest()}
            for name, raw in (("projection", projection), ("runtime", runtime_source))}
        prefix = (
            "import builtins as _tpr_builtins\nimport hashlib as _tpr_hashlib\nimport json as _tpr_json\n"
            "from datetime import datetime as _tpr_datetime, timezone as _tpr_timezone\n"
            "import time as _tpr_time\nfrom types import SimpleNamespace as _tpr_NS\n"
            "_tpr_bindings = " + repr(bindings) + "\n"
            "_tpr_payloads = " + repr(payloads) + "\n"
            "_tpr_initial_result = _tpr_json.loads(" + repr(_canonical(runtime._new_result()).decode()) + ")\n"
            "_tpr_namespace = _tpr_builtins.globals()\n"
        )
        execution = (
            "try:\n"
            "    if _tpr_builtins.any(_tpr_hashlib.sha256(v['raw'].encode('utf-8')).hexdigest() != v['sha256']\n"
            "            for _tpr_group in (_tpr_bindings, _tpr_payloads) for v in _tpr_group.values()):\n"
            "        return _tpr_initial_result\n"
            "except _tpr_builtins.Exception:\n"
            "    return _tpr_initial_result\n"
            "_tpr_projection_ns = {'__name__':'_tpr_closed_witness_projection'}\n"
            "_tpr_builtins.exec(_tpr_builtins.compile(_tpr_payloads['projection']['raw'], '<pinned-pure-witness-projection>', 'exec'), _tpr_projection_ns)\n"
            "_tpr_runtime_ns = {'__name__':'_tpr_intrinsic_witness_runtime', '_tpr_projection':_tpr_NS(**_tpr_projection_ns)}\n"
            "_tpr_builtins.exec(_tpr_builtins.compile(_tpr_payloads['runtime']['raw'], '<pinned-intrinsic-witness-runtime>', 'exec'), _tpr_runtime_ns)\n"
            "_tpr_runtime = _tpr_NS(**_tpr_runtime_ns)\n"
            "_tpr_permit = _tpr_json.loads(" + repr(permit_wire.decode()) + ")\n"
            "_tpr_capsule = _tpr_json.loads(" + repr(capsule_wire.decode()) + ")\n"
            "_tpr_result = _tpr_runtime._new_result()\n"
            "try:\n"
            "    _tpr_frozen_permit = _tpr_runtime.validate_permit(_tpr_permit)\n"
            "    _tpr_result['operation_id'] = _tpr_permit['operation_id']\n"
            "    _tpr_frozen_capsule = _tpr_runtime.validate_capsule(_tpr_capsule, operation_id=_tpr_permit['operation_id'])\n"
            "    def _tpr_actual_utc_now():\n"
            "        _tpr_live = _tpr_namespace.get('TPR_EPHEMERAL_CONTEXT')\n"
            "        if _tpr_runtime.validate_capsule(_tpr_live, operation_id=_tpr_permit['operation_id']) != _tpr_frozen_capsule:\n"
            "            _tpr_runtime._fail()\n"
            "        return _tpr_datetime.now(_tpr_timezone.utc)\n"
            "    _tpr_now = _tpr_runtime._utc(_tpr_actual_utc_now())\n"
            "    _tpr_issued = _tpr_runtime._clock_text(_tpr_permit['issued_utc'])\n"
            "    _tpr_expiry = _tpr_runtime._clock_text(_tpr_permit['expires_utc'])\n"
            "    if not _tpr_issued <= _tpr_now < _tpr_expiry or 'qb' not in _tpr_namespace:\n"
            "        _tpr_runtime._fail()\n"
            "    from System import Object as _tpr_Object\n"
            "    _tpr_result = _tpr_runtime.read_runtime_witnesses(_tpr_namespace['qb'], _tpr_permit, _tpr_capsule,\n"
            "        utc_now=_tpr_actual_utc_now, monotonic_clock=_tpr_time.monotonic,\n"
            "        reference_equals=_tpr_Object.ReferenceEquals)\n"
            "except _tpr_runtime.RuntimeReadCancelled:\n"
            "    raise\n"
            "except _tpr_builtins.KeyboardInterrupt:\n"
            "    _tpr_result['status'] = 'cancelled'\n"
            "    raise _tpr_runtime.RuntimeReadCancelled(_tpr_result) from None\n"
            "except _tpr_builtins.Exception:\n"
            "    _tpr_result['status'] = 'failed_or_uncertain'\n"
            "_tpr_result = _tpr_runtime.validate_result(_tpr_result)\n"
            "return _tpr_result\n"
        )
        program = (prefix + "def _tpr_execute():\n" + textwrap.indent(execution, "    ")
            + "_tpr_result = _tpr_execute()\n"
            + "_tpr_builtins.print(_tpr_json.dumps(_tpr_result, sort_keys=True, separators=(',',':'), allow_nan=False))\n")
        if len(program.encode()) > MAX_PROGRAM_BYTES:
            _fail()
        ast.parse(program)
        return program
    except ProgramBuildRefusal:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, SyntaxError, RecursionError):
        _fail()


def design():
    return {"schema": "tpr-ext26-witness-program-successor-design-v1",
        "standalone_text_builder": True, "source_dependency_pins": dict(SOURCE_SHA256),
        "requires_existing_genuine_ephemeral_qb": True, "requires_fresh_bounded_controller": True,
        "authority_granted": False, "permit_registered": False, "ready_for_dispatch": False,
        "native_project_custody_proven": False, "sdk_hard_timeout_proven": False,
        "byte_bound_before_native_allocation_proven": False, "off_baseline_valid": False,
        "on_launch_authorized": False, "new_jobs": 0, "new_codex_attempts": 0, "new_looks": 0}
