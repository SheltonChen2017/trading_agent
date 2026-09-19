"""Compact authenticated-input and point-in-time parsers for QC order runs.

This module extracts the already-reviewed package loading and PIT collection
rules needed by the order runtime without pulling the outcome evaluator and
its 100KB transitive source graph into the cloud project.  It performs only
Object Store reads and deterministic parsing; it has no order capability.
"""

import dataclasses
import gzip
import hashlib
import io
import itertools
import json
import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

try:
    import accepted_risk_preliminary_rating_evaluator as evaluator
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_preliminary_rating_evaluator as evaluator,
    )


class AcceptedRiskOrderLevelInputRuntimeError(ValueError):
    """An authenticated package or PIT collection changed shape."""


TRANSPORT_MANIFEST_SCHEMA = "arv2-accepted-risk-preliminary-qc-transport-manifest-v1"
UPLOAD_OBJECT_SCHEMA = "arv2-accepted-risk-preliminary-qc-upload-object-v1"
BENCHMARK_SECURITY_ID = "arv2-benchmark-SPY"
BENCHMARK_TICKER = "SPY"
MAX_UPLOAD_OBJECT_BYTES = 32 * 1024 * 1024
MAX_TOTAL_UPLOAD_BYTES = 44 * 1024 * 1024
MAX_TRANSPORT_OBJECT_COUNT = 95
MAX_DECOMPRESSED_OBJECT_BYTES = 192 * 1024 * 1024
MAX_TOTAL_DECOMPRESSED_BYTES = 768 * 1024 * 1024
MAX_COLLECTIONS_PER_CALL = 64
MAX_COLLECTION_ROWS = 25_000
NEW_YORK = ZoneInfo("America/New_York")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,1023}\Z")
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_/-]*/[A-Za-z0-9_-]+\.[A-Za-z0-9]+\Z")
_OBJECT_FIELDS = {
    "schema", "role", "ordinal", "object_store_key", "relative_path",
    "byte_count", "content_sha256", "record_count", "compression",
    "activation_manifest",
}
_TRANSPORT_FIELDS = {
    "schema", "package_id", "package_sha256", "evaluator_manifest_id",
    "evaluator_manifest_sha256", "benchmark", "source_disposition_sha256",
    "runtime_symbol_binding_count", "runtime_symbol_bindings_sha256",
    "contribution_census", "objects", "runtime", "claims",
}
_ROLE_ORDER = (
    "evaluator_manifest", "session_axis", "memberships", "contributions",
    "runtime_symbol_bindings",
)
_EXPECTED_RUNTIME = {
    "input_loading": "QC_ObjectStore_cloud_to_cloud_no_host_export",
    "security_resolution": "composite_figi_exact_roundtrip_ticker_diagnostic_only",
    "history": "bounded_total_return_adjusted_open_batches",
    "progress": "one_bounded_work_unit_per_callback_or_train",
    "result_transport": "aggregate_only_custom_summary_statistics",
}
_EXPECTED_CLAIMS = {
    "preliminary": True,
    "current_snapshot_security_and_sector": True,
    "uniform_q_data": True,
    "point_in_time": False,
    "formal": False,
    "control_residualized": False,
    "terminal_payoff_complete": False,
    "economic_portfolio": False,
    "etf_or_leverage": False,
    "deployment": False,
    "orders": False,
    "trading": False,
}


def _error(message):
    raise AcceptedRiskOrderLevelInputRuntimeError(message)


def _canonical(value):
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise AcceptedRiskOrderLevelInputRuntimeError(
            "preliminary QC value is not canonical ASCII JSON"
        ) from exc


def _stream_hash(rows):
    digest = hashlib.sha256()
    for row in rows:
        digest.update(_canonical(row))
        digest.update(b"\n")
    return digest.hexdigest()


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _error("preliminary QC JSON has a duplicate or non-string key")
        result[key] = value
    return result


def _json(payload, name):
    if type(payload) is not bytes:
        _error(name + " is not exact bytes")
    try:
        return json.loads(payload.decode("ascii"), object_pairs_hook=_object_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise AcceptedRiskOrderLevelInputRuntimeError(
            name + " is not strict ASCII JSON"
        ) from exc


def _sha(value, name):
    if type(value) is not str or _HEX.fullmatch(value) is None:
        _error(name + " is not lowercase SHA-256")
    return value


def _safe(value, name):
    if type(value) is not str or _SAFE.fullmatch(value) is None:
        _error(name + " is not a safe identifier")
    return value


def _read_object(store, key, expected_sha256, maximum_bytes):
    if type(key) is not str or _KEY.fullmatch(key) is None:
        _error("preliminary Object Store key violates portable grammar")
    if key.rsplit("/", 1)[-1].count(".") != 1:
        _error("preliminary Object Store key has more than one extension")
    _sha(expected_sha256, "preliminary Object Store object")
    if type(maximum_bytes) is not int or not 0 < maximum_bytes <= MAX_UPLOAD_OBJECT_BYTES:
        _error("preliminary Object Store object bound changed")
    try:
        contains = store.contains_key(key)
    except Exception as exc:
        raise AcceptedRiskOrderLevelInputRuntimeError(
            "preliminary Object Store existence check failed"
        ) from exc
    if type(contains) is not bool or not contains:
        _error("preliminary Object Store object is unavailable")
    try:
        payload = bytes(store.read_bytes(key))
    except Exception as exc:
        raise AcceptedRiskOrderLevelInputRuntimeError(
            "preliminary Object Store object read failed"
        ) from exc
    if len(payload) != maximum_bytes or hashlib.sha256(payload).hexdigest() != expected_sha256:
        _error("preliminary Object Store object identity changed")
    return payload


def _descriptor(value):
    if type(value) is not dict or set(value) != _OBJECT_FIELDS:
        _error("preliminary upload descriptor schema changed")
    if value.get("schema") != UPLOAD_OBJECT_SCHEMA:
        _error("preliminary upload descriptor schema changed")
    role = value.get("role")
    ordinal = value.get("ordinal")
    byte_count = value.get("byte_count")
    record_count = value.get("record_count")
    if (
        type(role) is not str or role not in _ROLE_ORDER
        or type(ordinal) is not int or ordinal < 0
        or type(byte_count) is not int or not 0 < byte_count <= MAX_UPLOAD_OBJECT_BYTES
        or type(record_count) is not int or record_count < 1
    ):
        _error("preliminary upload descriptor count or role changed")
    key = value.get("object_store_key")
    relative = value.get("relative_path")
    if (
        type(key) is not str or _KEY.fullmatch(key) is None
        or type(relative) is not str or "/" in relative
        or relative != key.rsplit("/", 1)[-1] or relative.count(".") != 1
    ):
        _error("preliminary upload descriptor path changed")
    compression = value.get("compression")
    if (
        type(compression) is not str or compression not in ("identity", "gzip")
        or (compression == "gzip" and not relative.endswith("-jsonl.gz"))
        or (compression == "identity" and not relative.endswith(".json"))
        or (role == "evaluator_manifest") != (compression == "identity")
        or value.get("activation_manifest") is not False
    ):
        _error("preliminary upload descriptor portability contract changed")
    _sha(value.get("content_sha256"), "preliminary upload descriptor content")
    return dict(value)


def _validate_transport(value, activation_key):
    if (
        type(value) is not dict or set(value) != _TRANSPORT_FIELDS
        or value.get("schema") != TRANSPORT_MANIFEST_SCHEMA
    ):
        _error("preliminary transport manifest schema changed")
    package_id = _safe(value.get("package_id"), "preliminary package id")
    package_sha = _sha(value.get("package_sha256"), "preliminary package")
    _safe(value.get("evaluator_manifest_id"), "preliminary evaluator manifest id")
    _sha(value.get("evaluator_manifest_sha256"), "preliminary evaluator manifest")
    _sha(value.get("source_disposition_sha256"), "preliminary source disposition")
    count = value.get("runtime_symbol_binding_count")
    if type(count) is not int or not 0 < count <= 100_000:
        _error("preliminary runtime symbol binding count changed")
    _sha(value.get("runtime_symbol_bindings_sha256"), "preliminary runtime symbol bindings")
    if value.get("runtime") != _EXPECTED_RUNTIME or value.get("claims") != _EXPECTED_CLAIMS:
        _error("preliminary transport runtime or claims changed")
    if value.get("benchmark") != {
        "security_id": BENCHMARK_SECURITY_ID,
        "ticker": BENCHMARK_TICKER,
        "binding": "QC_US_equity_symbol_resolved_in_process",
    }:
        _error("preliminary benchmark binding changed")
    census = value.get("contribution_census")
    if type(census) is not dict or any(
        type(key) is not str or _SAFE.fullmatch(key) is None
        or type(item) is not int or item < 0
        for key, item in census.items()
    ):
        _error("preliminary contribution census changed")
    raw = value.get("objects")
    if type(raw) is not list or not raw or len(raw) > MAX_TRANSPORT_OBJECT_COUNT:
        _error("preliminary transport object inventory changed")
    objects = tuple(_descriptor(item) for item in raw)
    if len({item["object_store_key"] for item in objects}) != len(objects):
        _error("preliminary transport repeats an Object Store key")
    if sum(item["byte_count"] for item in objects) > MAX_TOTAL_UPLOAD_BYTES:
        _error("preliminary transport object budget changed")
    prefix = activation_key.rsplit("/", 1)[0] + "/"
    if any(not item["object_store_key"].startswith(prefix) for item in objects):
        _error("preliminary transport object escaped activation prefix")
    positions = {role: [] for role in _ROLE_ORDER}
    for item in objects:
        positions[item["role"]].append(item["ordinal"])
    if any(items != list(range(len(items))) for items in positions.values()):
        _error("preliminary transport role ordinal inventory changed")
    if len(positions["evaluator_manifest"]) != 1 or any(
        not positions[role] for role in _ROLE_ORDER[1:]
    ):
        _error("preliminary transport omits a required data role")
    seed = dict(value)
    seed["package_id"] = None
    seed["package_sha256"] = None
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    if package_sha != digest or package_id != "arv2-preliminary-qc-package-" + digest[:24]:
        _error("preliminary transport package identity is not content-derived")
    return dict(value), objects


def _gzip_rows(payload, expected_count, role):
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as stream:
            raw = stream.read(MAX_DECOMPRESSED_OBJECT_BYTES + 1)
            extra = stream.read(1)
    except (OSError, EOFError) as exc:
        raise AcceptedRiskOrderLevelInputRuntimeError(
            "preliminary " + role + " object is not valid gzip"
        ) from exc
    if len(raw) > MAX_DECOMPRESSED_OBJECT_BYTES or extra:
        _error("preliminary compressed object exceeded decompression bound")
    lines = raw.splitlines(keepends=True)
    if len(lines) != expected_count or any(not line.endswith(b"\n") for line in lines):
        _error("preliminary compressed object row census changed")
    rows = []
    for line in lines:
        value = _json(line, "preliminary " + role + " row")
        if type(value) is not dict or _canonical(value) + b"\n" != line:
            _error("preliminary " + role + " row is not exact canonical JSON")
        rows.append(value)
    return tuple(rows), len(raw)


@dataclasses.dataclass(frozen=True)
class LoadedAcceptedRiskPreliminaryPackage:
    package_id: str
    package_sha256: str
    activation_manifest_sha256: str
    evaluator_input: object
    runtime_symbol_bindings: tuple


def load_accepted_risk_preliminary_package(
    algorithm, *, activation_manifest_key, activation_manifest_sha256,
    activation_manifest_byte_count,
):
    if algorithm is None:
        _error("preliminary QC algorithm is unavailable")
    _sha(activation_manifest_sha256, "preliminary activation manifest")
    payload = _read_object(
        algorithm.object_store, activation_manifest_key,
        activation_manifest_sha256, activation_manifest_byte_count,
    )
    transport_value = _json(payload, "preliminary activation manifest")
    if _canonical(transport_value) + b"\n" != payload:
        _error("preliminary activation manifest is not exact canonical JSON")
    transport, descriptors = _validate_transport(transport_value, activation_manifest_key)
    by_role = {role: [] for role in _ROLE_ORDER}
    decompressed_total = 0
    for item in descriptors:
        object_payload = _read_object(
            algorithm.object_store, item["object_store_key"],
            item["content_sha256"], item["byte_count"],
        )
        if item["compression"] == "gzip":
            rows, raw_bytes = _gzip_rows(object_payload, item["record_count"], item["role"])
            decompressed_total += raw_bytes
            if decompressed_total > MAX_TOTAL_DECOMPRESSED_BYTES:
                _error("preliminary package exceeded total decompression bound")
            by_role[item["role"]].extend(rows)
        else:
            value = _json(object_payload, "preliminary evaluator manifest")
            if item["record_count"] != 1 or type(value) is not dict or _canonical(value) + b"\n" != object_payload:
                _error("preliminary evaluator manifest object changed")
            by_role[item["role"]].append(value)
    manifest = by_role["evaluator_manifest"]
    if (
        len(manifest) != 1
        or manifest[0].get("manifest_id") != transport["evaluator_manifest_id"]
        or manifest[0].get("manifest_sha256") != transport["evaluator_manifest_sha256"]
    ):
        _error("preliminary evaluator manifest identity diverged from transport")
    try:
        loaded = evaluator.load_preliminary_rating_input(
            manifest[0], tuple(by_role["session_axis"]),
            tuple(by_role["memberships"]), tuple(by_role["contributions"]),
        )
    except Exception as exc:
        raise AcceptedRiskOrderLevelInputRuntimeError(
            "preliminary evaluator input did not authenticate"
        ) from exc
    bindings = tuple(by_role["runtime_symbol_bindings"])
    if any(type(item) is not dict for item in bindings):
        _error("preliminary runtime symbol binding row changed")
    if len(bindings) != transport["runtime_symbol_binding_count"] or _stream_hash(bindings) != transport["runtime_symbol_bindings_sha256"]:
        _error("preliminary runtime symbol binding stream identity changed")
    return LoadedAcceptedRiskPreliminaryPackage(
        transport["package_id"], transport["package_sha256"],
        activation_manifest_sha256, loaded, bindings,
    )


def universe_sid(value, name):
    try:
        identifier = value.symbol.id
        sid = str(identifier)
    except Exception as exc:
        raise AcceptedRiskOrderLevelInputRuntimeError(
            name + " symbol is unreadable"
        ) from exc
    if identifier is None or type(sid) is not str or not sid:
        _error(name + " symbol identity changed")
    return sid


def row_sid(value, name):
    try:
        identifier = value.symbol.id
        sid = str(identifier)
    except Exception as exc:
        raise AcceptedRiskOrderLevelInputRuntimeError(name + " SID is unreadable") from exc
    if identifier is None or type(sid) is not str or not sid:
        _error(name + " SID changed")
    return sid


def local_collection_time(value, name):
    if not isinstance(value, datetime):
        _error(name + " is not datetime")
    try:
        result = value if value.tzinfo is None or value.utcoffset() is None else value.astimezone(NEW_YORK).replace(tzinfo=None)
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise AcceptedRiskOrderLevelInputRuntimeError(name + " is unreadable") from exc
    if result.time() >= datetime.min.replace(hour=9, minute=30).time():
        _error(name + " was not observed before open")
    return result


def constituent_collection_time(value, name):
    if not isinstance(value, datetime):
        _error(name + " is not datetime")
    try:
        aware = value.tzinfo is not None and value.utcoffset() is not None
        clock = (value.hour, value.minute, value.second, value.microsecond)
        # QC daily universe collections use the end of their daily period as
        # the Series key: Friday's constituent state is therefore stamped at
        # Saturday midnight.  The order runtime compares freshness on the
        # authenticated exchange-session axis, so normalize that EndTime to
        # the source session while retaining the strict-prior-session rule at
        # the caller.  Without this fixed one-day normalization, every Monday
        # decision rejects the genuine Friday snapshot as a weekend date.
        result = datetime(value.year, value.month, value.day) - timedelta(days=1)
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise AcceptedRiskOrderLevelInputRuntimeError(name + " is unreadable") from exc
    if aware:
        _error(name + " is timezone-aware")
    if clock != (0, 0, 0, 0):
        _error(name + " is not midnight")
    return result


def history_items(history, name):
    try:
        items = tuple(itertools.islice(iter(history.items()), MAX_COLLECTIONS_PER_CALL + 1))
    except AttributeError as exc:
        raise AcceptedRiskOrderLevelInputRuntimeError(
            name + " is not Series-like"
        ) from exc
    except Exception as exc:
        raise AcceptedRiskOrderLevelInputRuntimeError(
            name + " traversal failed"
        ) from exc
    if len(items) > MAX_COLLECTIONS_PER_CALL:
        _error(name + " exceeded the collection cap")
    return items


def collection_rows(rows, name):
    try:
        result = tuple(itertools.islice(iter(rows), MAX_COLLECTION_ROWS + 1))
    except Exception as exc:
        raise AcceptedRiskOrderLevelInputRuntimeError(name + " collection is unreadable") from exc
    if len(result) > MAX_COLLECTION_ROWS:
        _error(name + " collection row bound changed")
    return result


def positive_market_caps(rows):
    members = collection_rows(rows, "fundamental")
    if not members:
        _error("fundamental collection is empty")
    observed = {}
    for row in members:
        sid = row_sid(row, "fundamental row")
        try:
            raw = row.market_cap
        except AttributeError:
            raw = None
        if raw is None:
            classified = ("null", None)
        else:
            try:
                value = Decimal(str(raw))
            except (InvalidOperation, ValueError, TypeError):
                classified = ("invalid", None)
            else:
                classified = (
                    ("invalid", None) if not value.is_finite()
                    else (("nonpositive", value) if value <= 0 else ("positive", value))
                )
        prior = observed.get(sid)
        if prior is not None:
            if prior != classified:
                _error("fundamental duplicate SID value or class conflicts")
            continue
        observed[sid] = classified
    return {sid: item[1] for sid, item in observed.items() if item[0] == "positive"}


def positive_constituent_sids(rows):
    members = collection_rows(rows, "ETF constituent")
    if not members:
        _error("ETF constituent collection is empty")
    result = set()
    for row in members:
        try:
            raw = row.weight
        except AttributeError as exc:
            raise AcceptedRiskOrderLevelInputRuntimeError(
                "ETF constituent weight is unreadable"
            ) from exc
        if raw is None:
            continue
        try:
            weight = Decimal(str(raw))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise AcceptedRiskOrderLevelInputRuntimeError(
                "ETF constituent weight is not decimal"
            ) from exc
        if not weight.is_finite():
            _error("ETF constituent weight is not finite")
        if weight <= 0:
            continue
        sid = row_sid(row, "ETF constituent row")
        if sid in result:
            _error("ETF constituent collection duplicated a positive SID")
        result.add(sid)
    if not result:
        _error("ETF constituent collection has no positive members")
    return frozenset(result)


def positive_constituent_weights(rows, decimal_parser, error_type):
    members = collection_rows(rows, "order-level PIT QQQ constituent weights")
    positive_sids = positive_constituent_sids(members)
    result = {}
    for row in members:
        try:
            raw_weight = row.weight
        except AttributeError as exc:
            raise error_type(
                "order-level PIT QQQ constituent weight is unreadable"
            ) from exc
        if raw_weight is None:
            continue
        weight = decimal_parser(raw_weight, "order-level PIT QQQ constituent weight")
        if weight <= 0:
            continue
        sid = row_sid(row, "order-level PIT QQQ constituent")
        if sid not in positive_sids:
            raise error_type(
                "order-level PIT QQQ positive member identity changed"
            )
        result[sid] = weight
    if set(result) != set(positive_sids):
        raise error_type("order-level PIT QQQ constituent weights are unavailable")
    return result


def same_session_positive_raw_price(security, session, decimal_parser, error_type):
    """Read a fresh QC reference mark without substituting stale data."""

    try:
        observed = security.get_last_data().end_time
        if not isinstance(observed, datetime) or observed.date().isoformat() != session:
            return None
        return decimal_parser(
            security.price, "order-level RAW reference price", positive=True
        )
    except (AttributeError, error_type):
        return None


def current_whole_share_quantities(
    security_ids, security_for_id, portfolio, decimal_parser, error_type,
):
    """Read only exact whole-share QC holdings for the selected securities."""

    quantities = {}
    for security_id in sorted(security_ids):
        symbol, _security = security_for_id(security_id)
        value = decimal_parser(
            portfolio[symbol].quantity,
            "order-level holding quantity",
            nonnegative=True,
        )
        integral = value.to_integral_value()
        if value != integral:
            raise error_type("order-level holding quantity is not a whole share")
        if integral:
            quantities[security_id] = int(integral)
    return quantities


__all__ = (
    "AcceptedRiskOrderLevelInputRuntimeError",
    "LoadedAcceptedRiskPreliminaryPackage",
    "collection_rows",
    "constituent_collection_time",
    "history_items",
    "load_accepted_risk_preliminary_package",
    "local_collection_time",
    "positive_constituent_sids",
    "positive_constituent_weights",
    "positive_market_caps",
    "same_session_positive_raw_price",
    "current_whole_share_quantities",
    "row_sid",
    "universe_sid",
)
