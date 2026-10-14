"""INACTIVE, explicitly called hosted LEAN class-metadata diagnostic only.

NO QuantBook instance/import, History, resolver, dataset, financial/price field,
ObjectStore/export, account/config/environment inspection, order or backtest.
No function executes automatically when this file is pasted/imported.

Before paste AND before the explicit call, the supervisor must permanently
register the exact full source SHA and fsync/publish a one-shot start. Supply
those external canonical receipt bytes and independently observed digests.
The parser and kernel guard are NOT an authenticated durable registry, nor
proof that the input source hash is the current notebook's executed bytes.
Kernel reset does not restore authority to repeat this one-shot scope.

Public source evidence (not evidence of this owner's hosted runtime):
https://raw.githubusercontent.com/QuantConnect/Lean/master/Common/Data/Fundamental/FundamentalUniverse.cs
https://raw.githubusercontent.com/QuantConnect/Lean/master/Common/Data/UniverseSelection/BaseDataCollection.cs
https://www.quantconnect.com/docs/v2/research-environment/datasets/equity-fundamental-data
"""
from datetime import datetime, timezone
import hashlib
import json
import re

PROFILE = "insider-lean-sdk-type-metadata-only-v1-inactive"
PROJECT_ID = 37465795
TARGETS = (
    "QuantConnect.Data.Fundamental.Fundamentals",
    "QuantConnect.Data.Fundamental.FundamentalUniverse",
    "QuantConnect.Data.UniverseSelection.BaseDataCollection",
    "QuantConnect.Data.Fundamental.Fundamental",
    "QuantConnect.Data.BaseData",
)
MEMBERS = ("Data", "Time", "EndTime", "Symbol")
MAX_RECEIPT_BYTES = 4096
MAX_OUTPUT_BYTES = 32 * 1024
_STARTED = globals().get("_STARTED", False)


class MetadataRefusal(ValueError):
    pass


def _need(value, code):
    if not value:
        raise MetadataRefusal("REFUSED: " + code)


def _raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(value):
    _need(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value), "digest-invalid")
    return value


def _utc(value):
    _need(type(value) is str and len(value) <= 40, "timestamp-invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MetadataRefusal("REFUSED: timestamp-invalid") from exc
    _need(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0,
          "timestamp-not-utc")
    return parsed


def _receipt(raw, expected, keys):
    _need(type(raw) is bytes and 0 < len(raw) <= MAX_RECEIPT_BYTES
          and _sha(raw) == _digest(expected), "external-receipt-hash")
    def pairs(items):
        result = {}
        for key, value in items:
            _need(key not in result, "duplicate-receipt-key")
            result[key] = value
        return result
    try:
        result = json.loads(raw, object_pairs_hook=pairs,
                            parse_constant=lambda _: (_need(False, "nonfinite-receipt")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise MetadataRefusal("REFUSED: malformed-receipt") from exc
    _need(type(result) is dict and set(result) == set(keys)
          and _raw(result) == raw, "receipt-schema-or-canonical-encoding")
    return result


def _admit(registration_raw, registration_sha256, start_raw, start_sha256,
           execution_source_sha256):
    registration = _receipt(registration_raw, registration_sha256, {
        "schema", "profile", "run_id", "project_id", "source_sha256", "registered_at_utc",
        "allowed_type_names", "allowed_member_names", "data_access_permitted"})
    start = _receipt(start_raw, start_sha256, {
        "schema", "profile", "run_id", "registration_sha256", "source_sha256", "started_at_utc"})
    _need(registration["schema"] == "insider-sdk-metadata-preregistration-v1"
          and start["schema"] == "insider-sdk-metadata-start-v1"
          and registration["profile"] == start["profile"] == PROFILE,
          "wrong-one-shot-profile")
    _need(type(registration["run_id"]) is str
          and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,127}", registration["run_id"])
          and start["run_id"] == registration["run_id"], "run-identity-invalid")
    _need(type(registration["project_id"]) is int and registration["project_id"] == PROJECT_ID,
          "wrong-owned-project-declaration")
    _need(registration["source_sha256"] == start["source_sha256"] == _digest(execution_source_sha256)
          and start["registration_sha256"] == registration_sha256,
          "source-or-registration-binding")
    _need(registration["allowed_type_names"] == list(TARGETS)
          and registration["allowed_member_names"] == list(MEMBERS)
          and registration["data_access_permitted"] is False, "scope-must-be-metadata-only")
    _need(_utc(registration["registered_at_utc"]) <= _utc(start["started_at_utc"])
          <= datetime.now(timezone.utc), "registration-or-start-chronology")
    return registration


def _public_type_name(value):
    _need(type(value) is str and 0 < len(value) <= 256
          and re.fullmatch(r"(?:QuantConnect|System)\.[A-Za-z0-9_.+`]+", value),
          "unexpected-type-metadata")
    return value


def _type_shape(clr_type):
    if clr_type is None:
        return None
    if clr_type.IsGenericType:
        name = _public_type_name(clr_type.GetGenericTypeDefinition().FullName)
        args = list(clr_type.GetGenericArguments())
        _need(len(args) <= 4, "type-generic-argument-bound")
        return {"type_name": name, "generic_argument_names": [
            _public_type_name(item.FullName) for item in args]}
    return {"type_name": _public_type_name(clr_type.FullName), "generic_argument_names": []}


def _class_metadata(name, clr_type):
    if clr_type is None:
        return {"requested_type": name, "available": False, "metadata": None}
    _need(clr_type.FullName == name, "resolved-class-identity-mismatch")
    assembly = clr_type.Assembly.GetName()
    _need(assembly.Name == "QuantConnect.Common", "unexpected-lean-common-assembly")
    version = assembly.Version.ToString()
    _need(type(version) is str and re.fullmatch(r"[0-9]{1,5}(?:\.[0-9]{1,5}){1,3}", version),
          "assembly-version-metadata-invalid")
    properties = []
    for member in MEMBERS:
        prop = clr_type.GetProperty(member)
        if prop is None:
            properties.append({"name": member, "available": False, "type": None,
                               "declaring_type": None, "can_read": None, "can_write": None})
        else:
            _need(type(prop.CanRead) is bool and type(prop.CanWrite) is bool,
                  "property-metadata-boolean-types")
            properties.append({"name": member, "available": True,
                               "type": _type_shape(prop.PropertyType),
                               "declaring_type": _public_type_name(prop.DeclaringType.FullName),
                               "can_read": prop.CanRead, "can_write": prop.CanWrite})
    interfaces = list(clr_type.GetInterfaces())
    _need(len(interfaces) <= 32, "interface-metadata-bound")
    return {"requested_type": name, "available": True, "metadata": {
        "type_name": name, "base_type": _type_shape(clr_type.BaseType),
        "assembly_name": assembly.Name, "assembly_version": version,
        "properties": properties, "interfaces": [
            _type_shape(item) for item in interfaces]}}


def _loaded_type_provider():
    # Type imports/reflection only. No instances, GetValue, property getters,
    # Config/Globals/environment, assembly locations or market data machinery.
    import clr
    import QuantConnect.Data.Fundamental as fundamentals_namespace
    import QuantConnect.Data.UniverseSelection as universe_namespace
    import QuantConnect.Data as data_namespace
    namespaces = {"QuantConnect.Data.Fundamental": fundamentals_namespace,
                  "QuantConnect.Data.UniverseSelection": universe_namespace,
                  "QuantConnect.Data": data_namespace}
    def resolve(name):
        namespace, member = name.rsplit(".", 1)
        try:
            python_type = getattr(namespaces[namespace], member)
        except AttributeError:
            return None
        return clr.GetClrType(python_type)
    return resolve


def _collect(provider, *, fixture_only, registration, registration_sha256,
             start_sha256, execution_source_sha256):
    try:
        classes = [_class_metadata(name, provider(name)) for name in TARGETS]
    except MetadataRefusal:
        raise
    except Exception:
        # Reflection exception text may contain private runtime paths. Never
        # serialize it, call repr(), or dump all modules/configuration.
        raise MetadataRefusal("REFUSED: type-metadata-operation-failed") from None
    result = {"schema": "insider-lean-sdk-type-metadata-observation-v1",
        "profile": PROFILE, "run_id": registration["run_id"],
        "registration_sha256": registration_sha256, "start_sha256": start_sha256,
        "declared_execution_source_sha256": execution_source_sha256,
        "fixture_only": fixture_only, "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "classes": classes, "source_identity_verified_here": False,
        "durable_registration_authenticated_here": False, "owner_account_verified_here": False,
        "history_return_shape_observed": False, "dataset_access_observed": False,
        "fundamental_instance_data_read": False, "financial_values_read": False,
        "market_prices_read": False, "qc_backtests": 0, "research_outcome_looks": 0,
        "platform_engine_build_observed": False, "backtest_ready": False}
    _need(len(_raw(result)) <= MAX_OUTPUT_BYTES, "metadata-output-byte-bound")
    return result


def inspect_invented(*, type_provider, registration_raw, registration_sha256,
                     start_raw, start_sha256, execution_source_sha256):
    registration = _admit(registration_raw, registration_sha256, start_raw,
                          start_sha256, execution_source_sha256)
    return _collect(type_provider, fixture_only=True, registration=registration,
                    registration_sha256=registration_sha256, start_sha256=start_sha256,
                    execution_source_sha256=execution_source_sha256)


def inspect_loaded_sdk_once(*, registration_raw, registration_sha256,
                            start_raw, start_sha256, execution_source_sha256):
    """Explicit supervisor call only; no arbitrary injected provider in this path.

    Receipts must already be durable externally BEFORE pasting/running this cell.
    Their hashes verify bytes, not real provenance or anti-rollback. Never reset
    the external one-shot journal or repeat this scope in a new kernel.
    """
    global _STARTED
    registration = _admit(registration_raw, registration_sha256, start_raw,
                          start_sha256, execution_source_sha256)
    _need(_STARTED is False, "kernel-already-started-external-start-remains-consumed")
    _STARTED = True
    try:
        provider = _loaded_type_provider()
        return _collect(provider, fixture_only=False, registration=registration,
                        registration_sha256=registration_sha256, start_sha256=start_sha256,
                        execution_source_sha256=execution_source_sha256)
    except MetadataRefusal:
        raise
    except Exception:
        raise MetadataRefusal("REFUSED: loaded-sdk-type-import-failed") from None

