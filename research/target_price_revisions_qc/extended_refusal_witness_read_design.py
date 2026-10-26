"""Public native-Mia read design; importing/building/projecting performs no I/O.

Effects are possible only through explicitly calling read_native_witnesses
with an already available native store and an external scope check. This is
not authorization, authentication, a transport timeout or a launch interface.
The native program requires an existing ephemeral genuine-Mia tool; never
create/modify project source, a notebook or a job to make that tool available.
"""
from __future__ import annotations

import ast
from datetime import datetime
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
import json
import re
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import zlib

from . import extended_refusal_witness_context_successor as witness

PROJECT = witness.PROJECT
JOB = "3bcfc642896ea36e26b5cbca2988220c"
KINDS = ("membership", "mark")
MAX_BYTES = witness.MAX_BYTES
MAX_SOURCE_BYTES = 32768
HELPER_SHA256 = "1b057f254fba91eee98862bbb63b2141cea63962905c458459d7a47531215a0f"
INPUT_HASHES = {
    "calendar.json": witness.CALENDAR_SHA256,
    "identities.json": "2cf0efc355e551fa853db3a00a4a10f235509a729a8119425845fe7575b06561",
    "preparation.json": "08e1d006b9ffef3554873722d5c40ebf739ff7e6dd2c372e78069ddf6cf2808f",
    "signal-manifest.json": "a9cbf9ad3ec485a11a2bf5c699326b4ca792579c43efb0e5b3a388a24ab36838",
}
_DEPENDENCY_IMPORT = "from . import extended_refusal_witness_context_successor as witness\n"
_TYPE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{0,159}")
_SID = re.compile(r"[A-Za-z0-9_ .:/-]{1,200}")
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
_CLOCK = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?(?:Z|[+-][0-9]{2}:[0-9]{2})?")
_ROOT_KEYS = frozenset(("schema operation_id look_ordinal candidate_id config_sha256 freeze_sha256 attempt "
    "project_id job_id input_hashes_sha256 kind original_refusal_code original_refusal_preserved "
    "units_inferred economics_accepted new_codex_attempts input_bound_scope details").split())
_MEMBER_KEYS = frozenset(("etf member_sid raw_weight guard_weight end_time now no_unit_scaling_applied "
    "full_membership_rows_retained source_version unit_expected source_date").split())
_MARK_KEYS = frozenset(("member_sid mark_type end_time mark_utc now session warning_id_observed "
    "delisted_id_observed action_flags settlement_authority_proven freshness_exception_granted "
    "full_price_bar_rows_retained bar_time period fill_forward native_quantity ledger_quantity raw_price cache_price").split())


class WitnessReadRefusal(ValueError):
    """Body-free refusal; never embed a returned value or exception text."""


def _fail():
    raise WitnessReadRefusal("bounded native witness read refused")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def _closed(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        _fail()


def witness_key(kind):
    if kind not in KINDS:
        _fail()
    return ("tpr-ext26/refusal-witness/" + witness.OPERATION + "/" + str(PROJECT)
        + "/" + JOB + "/" + kind + "_json.gz")


def design():
    """Fresh effect scope and actual tool capability remain caller obligations."""
    return {"schema": "tpr-ext26-native-witness-read-design-v1", "project_id": PROJECT, "job_id": JOB,
        "keys": [witness_key(kind) for kind in KINDS], "max_contains_key": 2, "max_read_bytes": 2,
        "max_compressed_bytes_each": MAX_BYTES, "max_plain_bytes_each": MAX_BYTES,
        "byte_bound_before_native_allocation_proven": False, "sdk_hard_timeout_proven": False,
        "requires_existing_genuine_mia_ephemeral_tool": True,
        "stop_if_notebook_or_source_or_job_creation_required": True,
        "global_enumeration": False, "writes": False, "history": False, "external_export": False,
        "launch": False, "authority_granted": False}


def _typename(value):
    if type(value) is not str or _TYPE.fullmatch(value) is None:
        _fail()
    return value


def _number(text):
    if type(text) is not str or not 0 < len(text) <= 128 or _NUMBER.fullmatch(text) is None:
        _fail()
    try: value = Decimal(text)
    except (InvalidOperation, ValueError, OverflowError): _fail()
    # The writer bounds lexical length, not exponent magnitude. Refuse before
    # constructing a huge rational; do not normalize unsupported values to zero.
    if not value.is_finite() or len(value.as_tuple().digits) > 128 or abs(value.as_tuple().exponent) > 128:
        _fail()
    return Fraction(value)


def _scalar(value):
    if type(value) is not dict:
        _fail()
    name, state = _typename(value.get("type")), value.get("state")
    if type(state) is not str:
        _fail()
    number = None
    if state == "rational":
        _closed(value, ("type", "state", "numerator", "denominator"))
        numerator, denominator = value["numerator"], value["denominator"]
        if (name != "fractions.Fraction" or type(numerator) is not str or type(denominator) is not str
                or not 0 < len(numerator) <= 128 or not 0 < len(denominator) <= 128
                or re.fullmatch(r"-?(?:0|[1-9][0-9]*)", numerator) is None
                or re.fullmatch(r"[1-9][0-9]*", denominator) is None):
            _fail()
        number = Fraction(int(numerator), int(denominator))
        if str(number.numerator) != numerator or str(number.denominator) != denominator:
            _fail()
    else:
        _closed(value, ("type", "state", "text"))
        text = value["text"]
        if state == "numeric_text":
            if name not in witness.CLR_NUMBERS | {"builtins.str", "builtins.int", "builtins.float", "decimal.Decimal"}:
                _fail()
            number = _number(text)
        elif state == "none":
            if name != "builtins.NoneType" or text is not None: _fail()
        elif state == "boolean":
            if name != "builtins.bool" or text not in ("true", "false"): _fail()
        elif state == "nonfinite":
            if name not in {"builtins.float", "decimal.Decimal"} or text not in ("nan", "positive_infinity", "negative_infinity"): _fail()
        elif state in {"unsupported", "non_numeric_text_withheld"}:
            supported = witness.CLR_NUMBERS | {"builtins.str", "builtins.int", "builtins.float", "decimal.Decimal"}
            if (text is not None or state == "unsupported" and name in supported | {"builtins.NoneType", "builtins.bool", "fractions.Fraction"}
                    or state == "non_numeric_text_withheld" and name not in supported):
                _fail()
        else:
            _fail()
    classes = {"builtins.NoneType": "none", "builtins.bool": "boolean", "fractions.Fraction": "rational",
        "builtins.str": "string", "builtins.int": "integer", "builtins.float": "float", "decimal.Decimal": "decimal"}
    category = "clr_numeric" if name in witness.CLR_NUMBERS else classes.get(name, "other_withheld")
    range_class = ("unknown" if number is None else "below_zero" if number < 0 else "zero" if number == 0
        else "below_one" if number < 1 else "one" if number == 1 else "above_one")
    return {"type_class": category, "state": state, "range": range_class}, number


def _clock(value):
    _closed(value, ("type", "text", "offset_observed", "timezone_inferred"))
    name, text = _typename(value["type"]), value["text"]
    if value["timezone_inferred"] is not False:
        _fail()
    if text is None:
        if name != "builtins.NoneType" or value["offset_observed"] is not None: _fail()
        return None
    if (name not in {"datetime.datetime", "System.DateTime", "System.DateTimeOffset"}
            or type(text) is not str or not 0 < len(text) <= 64 or _CLOCK.fullmatch(text) is None):
        _fail()
    # Native clocks may preserve 100ns/nanosecond digits. Python silently
    # truncates beyond microseconds; refuse nonzero discarded precision rather
    # than falsely reporting a future mark as equal. Extra zeros are lossless.
    fraction = re.search(r"\.([0-9]+)", text)
    if fraction is not None and any(digit != "0" for digit in fraction.group(1)[6:]):
        _fail()
    try: parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError: _fail()
    if type(value["offset_observed"]) is not bool or value["offset_observed"] != (parsed.utcoffset() is not None):
        _fail()
    return parsed


def _relations(left, right):
    comparable = left is not None and right is not None and left.utcoffset() is not None and right.utcoffset() is not None
    return {"left_present": left is not None, "right_present": right is not None,
        "offsets_both_observed": comparable, "left_after_right": left > right if comparable else None}


def _details(kind, row):
    if kind == "membership":
        _closed(row, _MEMBER_KEYS)
    else:
        _closed(row, _MARK_KEYS)
    if type(row["member_sid"]) is not str or _SID.fullmatch(row["member_sid"]) is None:
        _fail()
    if kind == "membership":
        if (type(row["etf"]) is not str or row["etf"] not in witness.ETFS or row["no_unit_scaling_applied"] is not True
                or row["full_membership_rows_retained"] is not False
                or any(row[key] is not None for key in ("source_version", "unit_expected", "source_date"))):
            _fail()
        raw, raw_number = _scalar(row["raw_weight"])
        guard, guard_number = _scalar(row["guard_weight"])
        return {"etf": row["etf"], "raw_weight": raw, "guard_weight": guard,
            "numeric_values_equal": raw_number == guard_number if raw_number is not None and guard_number is not None else None,
            "callback_clock": _relations(_clock(row["end_time"]), _clock(row["now"])),
            "source_date_proven": False, "source_version_proven": False, "units_proven": False}
    _typename(row["mark_type"])
    if (type(row["session"]) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", row["session"]) is None
            or any(type(row[key]) is not bool for key in ("warning_id_observed", "delisted_id_observed"))
            or any(row[key] is not False for key in ("settlement_authority_proven", "freshness_exception_granted", "full_price_bar_rows_retained"))
            or row["fill_forward"] is not None and type(row["fill_forward"]) is not bool):
        _fail()
    try: datetime.strptime(row["session"], "%Y-%m-%d")
    except ValueError: _fail()
    _closed(row["action_flags"], witness.ACTION_KEYS)
    if any(value is not None and type(value) is not bool for value in row["action_flags"].values()): _fail()
    end, mark, now, bar = (_clock(row[key]) for key in ("end_time", "mark_utc", "now", "bar_time"))
    scalars = {key: _scalar(row[key]) for key in ("period", "native_quantity", "ledger_quantity", "raw_price", "cache_price")}
    native, ledger = scalars["native_quantity"][1], scalars["ledger_quantity"][1]
    raw, cache = scalars["raw_price"][1], scalars["cache_price"][1]
    return {"mark_type_class": "native_tradebar" if row["mark_type"] == "QuantConnect.Data.Market.TradeBar" else "other_withheld",
        "end_vs_now": _relations(end, now), "mark_vs_now": _relations(mark, now), "bar_vs_now": _relations(bar, now),
        "mark_matches_session": mark.astimezone(ZoneInfo("America/New_York")).date().isoformat() == row["session"]
            if mark is not None and mark.utcoffset() is not None else None,
        "warning_id_observed": row["warning_id_observed"], "delisted_id_observed": row["delisted_id_observed"],
        "action_flags": dict(row["action_flags"]), "all_action_flags_unknown": all(value is None for value in row["action_flags"].values()),
        "fill_forward": row["fill_forward"], "scalars": {key: value[0] for key, value in scalars.items()},
        "native_ledger_quantity_equal": native == ledger if native is not None and ledger is not None else None,
        "raw_cache_price_equal": raw == cache if raw is not None and cache is not None else None,
        "settlement_authority_proven": False, "freshness_exception_granted": False}


def project_witness(encoded, *, kind):
    """Pure bounded validation. Returned hashes are observations, not custody."""
    witness_key(kind)
    if type(encoded) is not bytes or not 0 < len(encoded) <= MAX_BYTES:
        _fail()
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        plain = decoder.decompress(encoded, MAX_BYTES + 1)
        if (not 0 < len(plain) <= MAX_BYTES or not decoder.eof or decoder.unconsumed_tail
                or decoder.unused_data or decoder.flush(1)):
            _fail()
    except zlib.error:
        _fail()
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value: _fail()
            value[key] = item
        return value
    def noninteger(_value): _fail()
    try:
        body = json.loads(plain.decode("utf-8"), object_pairs_hook=pairs, parse_float=noninteger, parse_constant=noninteger)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        _fail()
    pending, nodes = [(body, 0)], 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if nodes > 256 or depth > 12: _fail()
        if type(value) is dict:
            if any(type(key) is not str or len(key) > 160 for key in value): _fail()
            pending.extend((item, depth + 1) for item in value.values())
        elif type(value) is list:
            pending.extend((item, depth + 1) for item in value)
        elif type(value) is str and len(value) > 200:
            _fail()
    _closed(body, _ROOT_KEYS)
    if (body["schema"] != "tpr-ext26-first-refusal-witness-v1" or body["operation_id"] != witness.OPERATION
            or type(body["look_ordinal"]) is not int or body["look_ordinal"] != 31
            or body["candidate_id"] != witness.CANDIDATE or body["config_sha256"] != witness.CONFIG_SHA256
            or body["freeze_sha256"] != witness.FREEZE_SHA256
            or type(body["attempt"]) is not int or body["attempt"] != 3
            or type(body["project_id"]) is not int or body["project_id"] != PROJECT or body["job_id"] != JOB
            or body["input_hashes_sha256"] != _sha(_canonical(INPUT_HASHES)) or INPUT_HASHES["calendar.json"] != witness.CALENDAR_SHA256
            or body["kind"] != kind or body["original_refusal_code"] not in witness.REFUSALS[kind].values()
            or body["original_refusal_preserved"] is not True or body["units_inferred"] is not False
            or body["economics_accepted"] is not False or type(body["new_codex_attempts"]) is not int
            or body["new_codex_attempts"] != 0 or body["input_bound_scope"] != witness.OPERATION):
        _fail()
    detail = _details(kind, body["details"])
    if _canonical(body) != plain:
        _fail()
    return {"kind": kind, "key": witness_key(kind), "status": "validated_diagnostic",
        "gzip_bytes": len(encoded), "gzip_sha256": _sha(encoded), "plain_bytes": len(plain), "plain_sha256": _sha(plain),
        "binding_matches": True, "refusal_code": body["original_refusal_code"], "diagnostic": detail,
        "actual_look_ordinal_claimed": False, "actor_or_dispatch_proven": False,
        "historical_compiled_source_proven": False, "snapshot_binding_proven": False,
        "creation_hash_independently_verified": False, "units_proven": False, "source_date_proven": False,
        "economics_accepted": False, "off_baseline_valid": False, "on_launch_authorized": False}


def _native_bytes(value):
    # The native method has already returned. This does NOT bound its transport
    # allocation or duration. Bound the supported conversion before copying.
    if type(value) in (bytes, bytearray, memoryview):
        size = value.nbytes if type(value) is memoryview else len(value)
        if not 0 < size <= MAX_BYTES: _fail()
        return bytes(value)
    from System import Array, Byte
    if type(value) is not Array[Byte] or not 0 < value.Length <= MAX_BYTES: _fail()
    return bytes(value)


def _check_scope(check):
    # A failed check returning False must not silently authorize another read.
    # A successful external check follows the existing guard's None contract.
    if check() is not None: _fail()


def read_native_witnesses(native_store, *, observed_project_id, scope_check):
    """Explicit native-only effect seam; external fresh scope/custody required."""
    result = {"schema": "tpr-ext26-native-witness-read-result-v1", "project_id": PROJECT, "job_id": JOB,
        "status": "failed_or_uncertain", "contains_calls": 0, "read_calls": 0, "objects": [],
        "byte_bound_before_native_allocation_proven": False, "sdk_hard_timeout_proven": False,
        "new_jobs": 0, "new_codex_attempts": 0, "authority_granted": False}
    try:
        if type(observed_project_id) is not int or observed_project_id != PROJECT or not callable(scope_check): _fail()
        _check_scope(scope_check)
        for kind in KINDS:
            key = witness_key(kind)
            _check_scope(scope_check); result["contains_calls"] += 1
            present = native_store.contains_key(key)
            _check_scope(scope_check)
            if type(present) is not bool: _fail()
            row = {"kind": kind, "key": key, "present": present,
                "status": "present_unvalidated" if present else "absent_uninterpreted"}
            result["objects"].append(row)
            if not present: continue
            _check_scope(scope_check); result["read_calls"] += 1
            returned = native_store.read_bytes(key)
            _check_scope(scope_check)
            encoded = _native_bytes(returned)
            row.update(gzip_bytes=len(encoded), gzip_sha256=_sha(encoded))
            row.update(project_witness(encoded, kind=kind))
            _check_scope(scope_check)
        _check_scope(scope_check)
        result["status"] = "completed_diagnostic_only"
    except Exception:
        # No returned body, exception text, SID, raw scalar or clock is exposed.
        result["status"] = "failed_or_uncertain"
        if result["objects"] and result["objects"][-1]["status"] == "present_unvalidated":
            result["objects"][-1]["status"] = "failed_or_refused"
    return result


def build_native_program(module_raw, *, expected_module_sha256, witness_raw):
    """Embed exact public source; caller freezes its hash BEFORE any Mia effect.

    Required existing ephemeral-tool variables are NATIVE_OBJECT_STORE,
    OBSERVED_PROJECT_ID and SCOPE_CHECK. Their actual native custody and the
    genuine Mia surface are external obligations, not caller-asserted proof.
    """
    if (type(module_raw) is not bytes or not 0 < len(module_raw) <= MAX_SOURCE_BYTES
            or type(expected_module_sha256) is not str or re.fullmatch(r"[a-f0-9]{64}", expected_module_sha256) is None
            or _sha(module_raw) != expected_module_sha256 or type(witness_raw) is not bytes
            or _sha(witness_raw) != HELPER_SHA256):
        _fail()
    try: source = module_raw.decode("utf-8")
    except UnicodeError: _fail()
    if source.count(_DEPENDENCY_IMPORT) != 1: _fail()
    ast.parse(source)
    fields = ("PROJECT", "MAX_BYTES", "OPERATION", "CANDIDATE", "CONFIG_SHA256", "FREEZE_SHA256",
        "CALENDAR_SHA256", "ETFS", "ACTION_KEYS", "CLR_NUMBERS", "REFUSALS")
    values = {}
    for node in ast.parse(witness_raw).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        key = node.targets[0].id
        if key not in fields: continue
        value = node.value
        if isinstance(value, ast.Call):
            if not isinstance(value.func, ast.Name) or value.func.id != "frozenset" or len(value.args) != 1 or value.keywords: _fail()
            parsed = frozenset(ast.literal_eval(value.args[0]))
        else:
            parsed = ast.literal_eval(value)
        if key in values or parsed != getattr(witness, key): _fail()
        values[key] = parsed
    if set(values) != set(fields): _fail()
    wire_values = {key: sorted(value) if type(value) is frozenset else value for key, value in values.items()}
    dependency = ("_tpr_contract = json.loads(" + repr(_canonical(wire_values).decode()) + ")\n"
        "for _tpr_field in ('ETFS', 'ACTION_KEYS', 'CLR_NUMBERS'):\n"
        "    _tpr_contract[_tpr_field] = frozenset(_tpr_contract[_tpr_field])\n"
        "witness = SimpleNamespace(**_tpr_contract)\n")
    native_source = source.replace(_DEPENDENCY_IMPORT, dependency, 1)
    # No writer source is embedded/imported. The supplied pinned helper is only
    # an integrity reference for the already reviewed constant contract.
    return ("import json as _tpr_json\n"
        "_tpr_required = ('NATIVE_OBJECT_STORE', 'OBSERVED_PROJECT_ID', 'SCOPE_CHECK')\n"
        "if not all(name in globals() for name in _tpr_required):\n"
        "    print(_tpr_json.dumps({'status':'STOP_EPHEMERAL_NATIVE_TOOL_UNAVAILABLE','effects':0}))\n"
        "else:\n"
        "    _tpr_namespace = {'__name__':'_tpr_native_witness_read_design'}\n"
        "    exec(compile(" + repr(native_source) + ", '<exact-public-native-witness-read-design>', 'exec'), _tpr_namespace)\n"
        "    _tpr_report = _tpr_namespace['read_native_witnesses'](NATIVE_OBJECT_STORE, observed_project_id=OBSERVED_PROJECT_ID, scope_check=SCOPE_CHECK)\n"
        "    print(_tpr_json.dumps(_tpr_report, sort_keys=True, separators=(',',':')))\n")
