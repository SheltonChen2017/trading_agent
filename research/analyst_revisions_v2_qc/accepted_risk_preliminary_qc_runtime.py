"""Cloud-local driver for the owner-accepted ARV2 preliminary rating run.

This module is intentionally flat-importable inside a QuantConnect project.
It authenticates the activation manifest and every compact input object from
Object Store, resolves admitted composite FIGIs with an exact QC round trip,
loads adjusted daily opens through typed ``History[TradeBar]`` requests, and
advances the aggregate-only evaluator in bounded daily runtime slices.

It is not the frozen formal evaluator.  It emits only compact preliminary
custom summary statistics and has no order, portfolio, deployment, or Object
Store result-writing surface.
"""

import dataclasses
import gzip
import hashlib
import io
import json
import math
import re
import time
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from types import MappingProxyType

try:
    import accepted_risk_preliminary_rating_evaluator as evaluator
    import accepted_risk_preliminary_qc_figi as figi_authority
    import accepted_risk_regime_rating_evaluator as regime_evaluator
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_preliminary_rating_evaluator as evaluator,
    )
    from research.analyst_revisions_v2_qc import accepted_risk_preliminary_qc_figi as figi_authority
    from research.analyst_revisions_v2_qc import (
        accepted_risk_regime_rating_evaluator as regime_evaluator,
    )


class AcceptedRiskPreliminaryQcRuntimeError(ValueError):
    """The cloud package, QC identity, history, or runtime state is inexact."""


TRANSPORT_MANIFEST_SCHEMA = (
    "arv2-accepted-risk-preliminary-qc-transport-manifest-v1"
)
UPLOAD_OBJECT_SCHEMA = "arv2-accepted-risk-preliminary-qc-upload-object-v1"
BENCHMARK_SECURITY_ID = "arv2-benchmark-SPY"
BENCHMARK_TICKER = "SPY"
MAX_UPLOAD_OBJECT_BYTES = 32 * 1024 * 1024
MAX_TOTAL_UPLOAD_BYTES = 44 * 1024 * 1024
MAX_TRANSPORT_OBJECT_COUNT = 95
MAX_DECOMPRESSED_OBJECT_BYTES = 192 * 1024 * 1024
MAX_TOTAL_DECOMPRESSED_BYTES = 768 * 1024 * 1024
TRAIN_WORK_UNITS_PER_SLICE = 10
TRAIN_SLICE_SOFT_SECONDS = 240
# The persisted field retains its original ``training_slice_count`` name for
# receipt compatibility, but R055 advances it directly from daily OnData.
MAX_TRAIN_SLICE_COUNT = 113
MAX_BACKTEST_RUNTIME_SECONDS = 12 * 60 * 60
RUNTIME_META_STATISTIC = "ARV2_RUNTIME_META"
STOCK_PORTFOLIO_PROFILE_ID = "arv2-stock-long-only-2021-2025-r065-v1"
EXPECTED_CUSTOM_SUMMARY_STATISTIC_NAMES = tuple(
    sorted(
        (
            *evaluator.EVALUATOR_CUSTOM_SUMMARY_STATISTIC_NAMES,
            RUNTIME_META_STATISTIC,
        )
    )
)


def _stock_portfolio_module():
    try:
        import accepted_risk_stock_portfolio_evaluator as module
    except ImportError:
        from research.analyst_revisions_v2_qc import (
            accepted_risk_stock_portfolio_evaluator as module,
        )
    return module


def expected_custom_summary_statistic_names(evaluation_profile_id=None):
    if evaluation_profile_id is None:
        return EXPECTED_CUSTOM_SUMMARY_STATISTIC_NAMES
    if evaluation_profile_id == STOCK_PORTFOLIO_PROFILE_ID:
        stock_portfolio = _stock_portfolio_module()
        if stock_portfolio.PROFILE_ID != STOCK_PORTFOLIO_PROFILE_ID:
            _error("stock portfolio profile binding changed")
        evaluator_names = (
            stock_portfolio.expected_custom_summary_statistic_names(
                evaluation_profile_id
            )
        )
    else:
        regime_evaluator.require_regime_profile(evaluation_profile_id)
        evaluator_names = regime_evaluator.expected_custom_summary_statistic_names(
            evaluation_profile_id
        )
    return tuple(
        sorted(
            (
                *evaluator_names,
                RUNTIME_META_STATISTIC,
            )
        )
    )

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,1023}\Z")
_KEY = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_/-]*/[A-Za-z0-9_-]+\.[A-Za-z0-9]+\Z"
)
_OBJECT_FIELDS = {
    "schema",
    "role",
    "ordinal",
    "object_store_key",
    "relative_path",
    "byte_count",
    "content_sha256",
    "record_count",
    "compression",
    "activation_manifest",
}
_TRANSPORT_FIELDS = {
    "schema",
    "package_id",
    "package_sha256",
    "evaluator_manifest_id",
    "evaluator_manifest_sha256",
    "benchmark",
    "source_disposition_sha256",
    "runtime_symbol_binding_count",
    "runtime_symbol_bindings_sha256",
    "contribution_census",
    "objects",
    "runtime",
    "claims",
}
_ROLE_ORDER = (
    "evaluator_manifest",
    "session_axis",
    "memberships",
    "contributions",
    "runtime_symbol_bindings",
)
_EXPECTED_RUNTIME = {
    "input_loading": "QC_ObjectStore_cloud_to_cloud_no_host_export",
    "security_resolution": (
        "composite_figi_exact_roundtrip_ticker_diagnostic_only"
    ),
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
    raise AcceptedRiskPreliminaryQcRuntimeError(message)


def _canonical(value):
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise AcceptedRiskPreliminaryQcRuntimeError(
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
        text = payload.decode("ascii")
        return json.loads(text, object_pairs_hook=_object_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise AcceptedRiskPreliminaryQcRuntimeError(
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
    final = key.rsplit("/", 1)[-1]
    if final.count(".") != 1:
        _error("preliminary Object Store key has more than one extension")
    _sha(expected_sha256, "preliminary Object Store object")
    if type(maximum_bytes) is not int or not 0 < maximum_bytes <= MAX_UPLOAD_OBJECT_BYTES:
        _error("preliminary Object Store object bound changed")
    try:
        contains = store.contains_key(key)
    except Exception as exc:
        raise AcceptedRiskPreliminaryQcRuntimeError(
            "preliminary Object Store existence check failed"
        ) from exc
    if type(contains) is not bool or not contains:
        _error("preliminary Object Store object is unavailable")
    try:
        payload = bytes(store.read_bytes(key))
    except Exception as exc:
        raise AcceptedRiskPreliminaryQcRuntimeError(
            "preliminary Object Store object read failed"
        ) from exc
    if (
        len(payload) != maximum_bytes
        or hashlib.sha256(payload).hexdigest() != expected_sha256
    ):
        _error("preliminary Object Store object identity changed")
    return payload


def _descriptor(value):
    if type(value) is not dict or set(value) != _OBJECT_FIELDS:
        _error("preliminary upload descriptor schema changed")
    if value.get("schema") != UPLOAD_OBJECT_SCHEMA:
        _error("preliminary upload descriptor schema changed")
    role = value.get("role")
    if type(role) is not str or role not in _ROLE_ORDER:
        _error("preliminary upload descriptor role changed")
    ordinal = value.get("ordinal")
    byte_count = value.get("byte_count")
    record_count = value.get("record_count")
    if (
        type(ordinal) is not int
        or ordinal < 0
        or type(byte_count) is not int
        or not 0 < byte_count <= MAX_UPLOAD_OBJECT_BYTES
        or type(record_count) is not int
        or record_count < 1
    ):
        _error("preliminary upload descriptor count changed")
    key = value.get("object_store_key")
    relative = value.get("relative_path")
    if (
        type(key) is not str
        or _KEY.fullmatch(key) is None
        or type(relative) is not str
        or "/" in relative
        or relative != key.rsplit("/", 1)[-1]
        or relative.count(".") != 1
    ):
        _error("preliminary upload descriptor path changed")
    compression = value.get("compression")
    if compression not in ("identity", "gzip") or type(compression) is not str:
        _error("preliminary upload descriptor compression changed")
    if (
        (compression == "gzip" and not relative.endswith("-jsonl.gz"))
        or (compression == "identity" and not relative.endswith(".json"))
        or (role == "evaluator_manifest") != (compression == "identity")
        or value.get("activation_manifest") is not False
    ):
        _error("preliminary upload descriptor portability contract changed")
    _sha(value.get("content_sha256"), "preliminary upload descriptor content")
    return dict(value)


def _validate_transport(value, activation_key):
    if (
        type(value) is not dict
        or set(value) != _TRANSPORT_FIELDS
        or value.get("schema") != TRANSPORT_MANIFEST_SCHEMA
    ):
        _error("preliminary transport manifest schema changed")
    package_id = _safe(value.get("package_id"), "preliminary package id")
    package_sha = _sha(value.get("package_sha256"), "preliminary package")
    _safe(value.get("evaluator_manifest_id"), "preliminary evaluator manifest id")
    _sha(value.get("evaluator_manifest_sha256"), "preliminary evaluator manifest")
    _sha(value.get("source_disposition_sha256"), "preliminary source disposition")
    binding_count = value.get("runtime_symbol_binding_count")
    if type(binding_count) is not int or not 0 < binding_count <= 100_000:
        _error("preliminary runtime symbol binding count changed")
    _sha(
        value.get("runtime_symbol_bindings_sha256"),
        "preliminary runtime symbol bindings",
    )
    if value.get("runtime") != _EXPECTED_RUNTIME or value.get("claims") != _EXPECTED_CLAIMS:
        _error("preliminary transport runtime or claims changed")
    benchmark = value.get("benchmark")
    if benchmark != {
        "security_id": BENCHMARK_SECURITY_ID,
        "ticker": BENCHMARK_TICKER,
        "binding": "QC_US_equity_symbol_resolved_in_process",
    }:
        _error("preliminary benchmark binding changed")
    census = value.get("contribution_census")
    if (
        type(census) is not dict
        or any(
            type(key) is not str
            or _SAFE.fullmatch(key) is None
            or type(count) is not int
            or count < 0
            for key, count in census.items()
        )
    ):
        _error("preliminary contribution census changed")
    raw_objects = value.get("objects")
    if (
        type(raw_objects) is not list
        or not raw_objects
        or len(raw_objects) > MAX_TRANSPORT_OBJECT_COUNT
    ):
        _error("preliminary transport object inventory changed")
    objects = tuple(_descriptor(item) for item in raw_objects)
    if len({item["object_store_key"] for item in objects}) != len(objects):
        _error("preliminary transport repeats an Object Store key")
    if sum(item["byte_count"] for item in objects) > MAX_TOTAL_UPLOAD_BYTES:
        _error("preliminary transport object budget changed")
    prefix = activation_key.rsplit("/", 1)[0] + "/"
    if any(not item["object_store_key"].startswith(prefix) for item in objects):
        _error("preliminary transport object escaped activation prefix")
    role_positions = {role: [] for role in _ROLE_ORDER}
    for item in objects:
        role_positions[item["role"]].append(item["ordinal"])
    if any(
        positions != list(range(len(positions)))
        for positions in role_positions.values()
    ):
        _error("preliminary transport role ordinal inventory changed")
    if len(role_positions["evaluator_manifest"]) != 1:
        _error("preliminary evaluator manifest object inventory changed")
    if any(not role_positions[role] for role in _ROLE_ORDER[1:]):
        _error("preliminary transport omits a required data role")
    seed = dict(value)
    seed["package_id"] = None
    seed["package_sha256"] = None
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    if (
        package_sha != digest
        or package_id != "arv2-preliminary-qc-package-" + digest[:24]
    ):
        _error("preliminary transport package identity is not content-derived")
    return dict(value), objects


def _gzip_rows(payload, expected_count, role):
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as stream:
            raw = stream.read(MAX_DECOMPRESSED_OBJECT_BYTES + 1)
            extra = stream.read(1)
    except (OSError, EOFError) as exc:
        raise AcceptedRiskPreliminaryQcRuntimeError(
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
    algorithm,
    *,
    activation_manifest_key,
    activation_manifest_sha256,
    activation_manifest_byte_count,
):
    """Read and authenticate the compact package entirely inside QC."""

    if algorithm is None:
        _error("preliminary QC algorithm is unavailable")
    key = activation_manifest_key
    _sha(activation_manifest_sha256, "preliminary activation manifest")
    payload = _read_object(
        algorithm.object_store,
        key,
        activation_manifest_sha256,
        activation_manifest_byte_count,
    )
    transport_value = _json(payload, "preliminary activation manifest")
    if _canonical(transport_value) + b"\n" != payload:
        _error("preliminary activation manifest is not exact canonical JSON")
    transport, descriptors = _validate_transport(transport_value, key)
    by_role = {role: [] for role in _ROLE_ORDER}
    decompressed_total = 0
    for item in descriptors:
        object_payload = _read_object(
            algorithm.object_store,
            item["object_store_key"],
            item["content_sha256"],
            item["byte_count"],
        )
        if item["compression"] == "gzip":
            rows, raw_bytes = _gzip_rows(
                object_payload, item["record_count"], item["role"]
            )
            decompressed_total += raw_bytes
            if decompressed_total > MAX_TOTAL_DECOMPRESSED_BYTES:
                _error("preliminary package exceeded total decompression bound")
            by_role[item["role"]].extend(rows)
        else:
            value = _json(object_payload, "preliminary evaluator manifest")
            if (
                item["record_count"] != 1
                or type(value) is not dict
                or _canonical(value) + b"\n" != object_payload
            ):
                _error("preliminary evaluator manifest object changed")
            by_role[item["role"]].append(value)
    manifest = by_role["evaluator_manifest"]
    if (
        len(manifest) != 1
        or manifest[0].get("manifest_id") != transport["evaluator_manifest_id"]
        or manifest[0].get("manifest_sha256")
        != transport["evaluator_manifest_sha256"]
    ):
        _error("preliminary evaluator manifest identity diverged from transport")
    try:
        loaded = evaluator.load_preliminary_rating_input(
            manifest[0],
            tuple(by_role["session_axis"]),
            tuple(by_role["memberships"]),
            tuple(by_role["contributions"]),
        )
    except Exception as exc:
        raise AcceptedRiskPreliminaryQcRuntimeError(
            "preliminary evaluator input did not authenticate"
        ) from exc
    binding_rows = tuple(by_role["runtime_symbol_bindings"])
    # The resolver performs the exact row schema/hash/inventory authentication.
    try:
        if any(type(item) is not dict for item in binding_rows):
            _error("preliminary runtime symbol binding row changed")
    except TypeError as exc:
        raise AcceptedRiskPreliminaryQcRuntimeError(
            "preliminary runtime symbol binding inventory is unreadable"
        ) from exc
    if (
        len(binding_rows) != transport["runtime_symbol_binding_count"]
        or _stream_hash(binding_rows)
        != transport["runtime_symbol_bindings_sha256"]
    ):
        _error("preliminary runtime symbol binding stream identity changed")
    return LoadedAcceptedRiskPreliminaryPackage(
        transport["package_id"],
        transport["package_sha256"],
        activation_manifest_sha256,
        loaded,
        binding_rows,
    )


def _symbol_identity(symbol, name):
    try:
        symbol_id = symbol.id
        sid = str(symbol_id)
        ticker = symbol.value
        security_type = str(symbol.security_type)
        market = str(symbol_id.market)
    except Exception as exc:
        raise AcceptedRiskPreliminaryQcRuntimeError(
            name + " symbol identity is unreadable"
        ) from exc
    if (
        symbol_id is None
        or type(sid) is not str
        or not sid
        or type(ticker) is not str
        or not ticker
        or security_type.lower() not in ("equity", "securitytype.equity")
        or market.lower() != "usa"
    ):
        _error(name + " symbol is not an exact US equity")
    return sid, ticker


class QcTotalReturnOpenHistoryLoader:
    """Typed, no-fill, adjusted-open QC History adapter with O(1) reverse map."""

    def __init__(
        self,
        algorithm,
        *,
        resolution,
        benchmark_symbol,
        trade_bar_type,
        daily_resolution,
        total_return_normalization,
        permitted_security_ids,
        permitted_sessions,
    ):
        self._algorithm = algorithm
        self._resolution = figi_authority.require_preliminary_qc_figi_resolution(
            resolution
        )
        benchmark_sid, benchmark_ticker = _symbol_identity(
            benchmark_symbol, "preliminary benchmark"
        )
        if benchmark_ticker != BENCHMARK_TICKER:
            _error("preliminary benchmark ticker changed")
        resolved_sids = {
            item["qc_security_id"] for item in self._resolution.resolved
        }
        if benchmark_sid in resolved_sids:
            _error("preliminary benchmark collides with a resolved stock SID")
        if (
            type(permitted_security_ids) is not tuple
            or not permitted_security_ids
            or any(type(item) is not str for item in permitted_security_ids)
            or len(set(permitted_security_ids)) != len(permitted_security_ids)
            or BENCHMARK_SECURITY_ID not in permitted_security_ids
            or type(permitted_sessions) is not tuple
            or not permitted_sessions
            or any(type(item) is not str for item in permitted_sessions)
            or tuple(sorted(permitted_sessions)) != permitted_sessions
        ):
            _error("preliminary History permitted inventory changed")
        self._benchmark_symbol = benchmark_symbol
        self._benchmark_sid = benchmark_sid
        self._trade_bar_type = trade_bar_type
        self._daily_resolution = daily_resolution
        self._total_return_normalization = total_return_normalization
        self._permitted_security_ids = frozenset(permitted_security_ids)
        self._permitted_sessions = frozenset(permitted_sessions)
        self._refusal_count = self._resolution.named_refusal_count

    @property
    def named_refusal_count(self):
        return self._refusal_count

    def _validate_request(self, request):
        if type(request) is not evaluator.TotalReturnHistoryRequest:
            _error("preliminary History request type changed")
        if (
            type(request.schema) is not str
            or request.schema != evaluator.HISTORY_REQUEST_SCHEMA
            or type(request.request_index) is not int
            or request.request_index < 0
            or type(request.security_ids) is not tuple
            or not request.security_ids
            or any(type(item) is not str for item in request.security_ids)
            or len(set(request.security_ids)) != len(request.security_ids)
            or not set(request.security_ids).issubset(self._permitted_security_ids)
            or type(request.start_session) is not str
            or type(request.end_session) is not str
            or request.start_session > request.end_session
            or request.normalization_mode != "total_return"
            or type(request.normalization_mode) is not str
            or request.observation != "session_open"
            or type(request.observation) is not str
            or type(request.request_sha256) is not str
            or _HEX.fullmatch(request.request_sha256) is None
        ):
            _error("preliminary History request schema changed")
        seed = {
            "schema": request.schema,
            "request_index": request.request_index,
            "security_ids": list(request.security_ids),
            "start_session": request.start_session,
            "end_session": request.end_session,
            "normalization_mode": request.normalization_mode,
            "observation": request.observation,
        }
        if hashlib.sha256(_canonical(seed)).hexdigest() != request.request_sha256:
            _error("preliminary History request identity changed")
        try:
            start = datetime.strptime(request.start_session, "%Y-%m-%d")
            end = datetime.strptime(request.end_session, "%Y-%m-%d")
        except ValueError as exc:
            raise AcceptedRiskPreliminaryQcRuntimeError(
                "preliminary History request session is invalid"
            ) from exc
        if (
            start.strftime("%Y-%m-%d") != request.start_session
            or end.strftime("%Y-%m-%d") != request.end_session
        ):
            _error("preliminary History request session is not canonical")
        return start, end

    def __call__(self, request):
        start, inclusive_end = self._validate_request(request)
        figi_authority.require_preliminary_qc_figi_resolution(self._resolution)
        symbols = []
        requested_by_sid = {}
        for security_id in request.security_ids:
            if security_id == BENCHMARK_SECURITY_ID:
                symbol = self._benchmark_symbol
                sid = self._benchmark_sid
            else:
                symbol = self._resolution.symbol_for_security(security_id)
                if symbol is None:
                    # One authenticated named refusal means no observation, not
                    # a caller-selected deletion or an invented market row.
                    if self._resolution.refusal_reason(security_id) is None:
                        _error("preliminary History request has an unknown security")
                    continue
                try:
                    sid = str(symbol.id)
                except Exception as exc:
                    raise AcceptedRiskPreliminaryQcRuntimeError(
                        "preliminary History request symbol became unreadable"
                    ) from exc
            if sid in requested_by_sid:
                _error("preliminary History request contains a SID collision")
            requested_by_sid[sid] = security_id
            symbols.append(symbol)
        if not symbols:
            return ()
        try:
            typed_history = self._algorithm.history[self._trade_bar_type]
            history = typed_history(
                symbols,
                start,
                inclusive_end + timedelta(days=1),
                self._daily_resolution,
                fill_forward=False,
                extended_market_hours=False,
                data_normalization_mode=self._total_return_normalization,
            )
            if history is None:
                _error("preliminary typed TOTAL_RETURN History returned no iterable")
            rows = []
            seen = set()
            for dictionary in history:
                try:
                    dictionary_time = dictionary.time
                    dictionary_session = dictionary_time.date().isoformat()
                    items_method = dictionary.items
                except Exception as exc:
                    raise AcceptedRiskPreliminaryQcRuntimeError(
                        "preliminary typed History returned a non-dictionary batch"
                    ) from exc
                if (
                    type(dictionary_session) is not str
                    or dictionary_session < request.start_session
                    or dictionary_session > request.end_session
                    or dictionary_session not in self._permitted_sessions
                ):
                    _error("preliminary typed History dictionary is out of axis")
                if not callable(items_method):
                    _error("preliminary typed History returned a non-dictionary batch")
                try:
                    items = tuple(items_method())
                except Exception as exc:
                    raise AcceptedRiskPreliminaryQcRuntimeError(
                        "preliminary typed History dictionary is unreadable"
                    ) from exc
                if not items or any(
                    type(item) is not tuple or len(item) != 2 for item in items
                ):
                    _error("preliminary typed History dictionary shape changed")
                dictionary_sids = set()
                for dictionary_symbol, bar in items:
                    try:
                        key_sid = str(dictionary_symbol.id)
                        observed_sid = str(bar.symbol.id)
                        observed_time = bar.time
                        observed_open = bar.open
                        session = observed_time.date().isoformat()
                    except Exception as exc:
                        raise AcceptedRiskPreliminaryQcRuntimeError(
                            "preliminary typed History bar is unreadable"
                        ) from exc
                    if key_sid != observed_sid or observed_sid in dictionary_sids:
                        _error("preliminary typed History dictionary identity changed")
                    dictionary_sids.add(observed_sid)
                    if session != dictionary_session:
                        _error("preliminary typed History dictionary mixes sessions")
                    security_id = requested_by_sid.get(observed_sid)
                    if security_id is None:
                        _error("preliminary typed History returned an unrequested SID")
                    if (
                        session < request.start_session
                        or session > request.end_session
                        or session not in self._permitted_sessions
                    ):
                        _error("preliminary typed History returned an out-of-axis session")
                    if security_id != BENCHMARK_SECURITY_ID:
                        reversed_security = self._resolution.security_for_qc_sid(
                            observed_sid
                        )
                        if reversed_security != security_id:
                            _error("preliminary typed History reverse mapping changed")
                    key = (security_id, session)
                    if key in seen:
                        _error("preliminary typed History duplicated an adjusted open")
                    seen.add(key)
                    try:
                        adjusted_open = Decimal(str(observed_open))
                    except (InvalidOperation, ValueError) as exc:
                        raise AcceptedRiskPreliminaryQcRuntimeError(
                            "preliminary typed History open is not decimal"
                        ) from exc
                    if not adjusted_open.is_finite() or adjusted_open <= 0:
                        _error("preliminary typed History open is not positive finite")
                    rows.append(
                        evaluator.TotalReturnOpenObservation(
                            evaluator.HISTORY_OBSERVATION_SCHEMA,
                            security_id,
                            session,
                            adjusted_open,
                        )
                    )
        except AcceptedRiskPreliminaryQcRuntimeError:
            raise
        except Exception as exc:
            raise AcceptedRiskPreliminaryQcRuntimeError(
                "preliminary typed TOTAL_RETURN History call failed"
            ) from exc
        finally:
            figi_authority.require_preliminary_qc_figi_resolution(self._resolution)
        return tuple(sorted(rows, key=lambda item: (item.security_id, item.session)))


class AcceptedRiskPreliminaryQcDriver:
    """Resumeless state machine advanced in bounded QC runtime slices."""

    def __init__(
        self,
        algorithm,
        *,
        activation_manifest_key,
        activation_manifest_sha256,
        activation_manifest_byte_count,
        benchmark_symbol,
        trade_bar_type,
        daily_resolution,
        total_return_normalization,
        evaluation_profile_id=None,
    ):
        if evaluation_profile_id is None:
            profile = None
        elif evaluation_profile_id == STOCK_PORTFOLIO_PROFILE_ID:
            stock_portfolio = _stock_portfolio_module()
            if stock_portfolio.PROFILE_ID != STOCK_PORTFOLIO_PROFILE_ID:
                _error("stock portfolio profile binding changed")
            profile = stock_portfolio.require_stock_portfolio_profile(
                evaluation_profile_id
            )
        else:
            profile = regime_evaluator.require_regime_profile(
                evaluation_profile_id
            )
        self._algorithm = algorithm
        self._activation_manifest_key = activation_manifest_key
        self._activation_manifest_sha256 = activation_manifest_sha256
        self._activation_manifest_byte_count = activation_manifest_byte_count
        self._benchmark_symbol = benchmark_symbol
        self._trade_bar_type = trade_bar_type
        self._daily_resolution = daily_resolution
        self._total_return_normalization = total_return_normalization
        self._evaluation_profile_id = evaluation_profile_id
        self._evaluation_profile_sha256 = (
            None if profile is None else profile["profile_sha256"]
        )
        self._package = None
        self._resolution = None
        self._history_loader = None
        self._runtime = None
        self._emitted = False
        self._training_slice_count = 0
        self._runtime_started_monotonic = None

    @property
    def completed(self):
        return (
            self._runtime is not None
            and self._runtime.phase is evaluator.RuntimePhase.COMPLETED
        )

    def _initialize_in_training(self):
        if self._package is not None:
            _error("preliminary QC package initialized more than once")
        package = load_accepted_risk_preliminary_package(
            self._algorithm,
            activation_manifest_key=self._activation_manifest_key,
            activation_manifest_sha256=self._activation_manifest_sha256,
            activation_manifest_byte_count=self._activation_manifest_byte_count,
        )
        try:
            lineage = dict(package.evaluator_input.source_lineage_sha256s)
            resolution = figi_authority.resolve_preliminary_qc_figis(
                package.runtime_symbol_bindings,
                expected_security_master_admission_sha256=(
                    lineage["security_master_admission_sha256"]
                ),
                composite_figi=self._algorithm.composite_figi,
                benchmark_symbol=self._benchmark_symbol,
            )
        except Exception as exc:
            raise AcceptedRiskPreliminaryQcRuntimeError(
                "preliminary QC composite-FIGI inventory did not resolve"
            ) from exc
        permitted_ids = (
            package.evaluator_input.benchmark_security_id,
            *tuple(item.security_id for item in package.evaluator_input.memberships),
        )
        history_loader = QcTotalReturnOpenHistoryLoader(
            self._algorithm,
            resolution=resolution,
            benchmark_symbol=self._benchmark_symbol,
            trade_bar_type=self._trade_bar_type,
            daily_resolution=self._daily_resolution,
            total_return_normalization=self._total_return_normalization,
            permitted_security_ids=tuple(dict.fromkeys(permitted_ids)),
            permitted_sessions=package.evaluator_input.session_axis,
        )
        input_security_ids = tuple(
            sorted(
                {
                    item.security_id
                    for item in package.evaluator_input.memberships
                }
            )
        )
        named_refusals = tuple(
            security_id
            for security_id in input_security_ids
            if resolution.symbol_for_security(security_id) is None
        )
        if self._evaluation_profile_id is None:
            runtime = evaluator.PreliminaryRatingEvaluationRuntime(
                package.evaluator_input
            )
        elif self._evaluation_profile_id == STOCK_PORTFOLIO_PROFILE_ID:
            runtime = _stock_portfolio_module().StockPortfolioEvaluationRuntime(
                package.evaluator_input,
                profile_id=self._evaluation_profile_id,
                package_id=package.package_id,
                package_sha256=package.package_sha256,
                named_figi_resolution_refusals=named_refusals,
            )
        else:
            runtime = regime_evaluator.RegimeRatingEvaluationRuntime(
                package.evaluator_input,
                profile_id=self._evaluation_profile_id,
                named_figi_resolution_refusals=named_refusals,
            )
        self._package = package
        self._resolution = resolution
        self._history_loader = history_loader
        self._runtime = runtime

    def advance_training_slice(
        self,
        *,
        maximum_work_units=TRAIN_WORK_UNITS_PER_SLICE,
        soft_seconds=TRAIN_SLICE_SOFT_SECONDS,
        monotonic=time.monotonic,
    ):
        if (
            type(maximum_work_units) is not int
            or not 1 <= maximum_work_units <= TRAIN_WORK_UNITS_PER_SLICE
            or type(soft_seconds) is not int
            or not 1 <= soft_seconds <= TRAIN_SLICE_SOFT_SECONDS
            or not callable(monotonic)
        ):
            _error("preliminary runtime slice bound changed")
        if self.completed:
            return None
        started = monotonic()
        if type(started) not in (int, float) or not math.isfinite(started):
            _error("preliminary Train monotonic clock changed")
        if self._runtime_started_monotonic is None:
            self._runtime_started_monotonic = started
        if (
            started - self._runtime_started_monotonic
            > MAX_BACKTEST_RUNTIME_SECONDS
        ):
            _error("preliminary evaluation exceeded twelve-hour backtest bound")
        self._training_slice_count += 1
        if self._training_slice_count > MAX_TRAIN_SLICE_COUNT:
            _error("preliminary evaluation exceeded deterministic runtime-slice census")
        work = 0
        if self._runtime is None:
            self._initialize_in_training()
            work += 1
        progress = None
        while work < maximum_work_units and not self.completed:
            now = monotonic()
            if type(now) not in (int, float) or not math.isfinite(now) or now < started:
                _error("preliminary Train monotonic clock changed")
            if work and now - started >= soft_seconds:
                break
            progress = self._runtime.run_callback(self._history_loader)
            work += 1
        if self.completed:
            self.emit_completed_summary()
        return progress

    def emit_completed_summary(self):
        if not self.completed:
            _error("preliminary custom summary requested before completion")
        if self._emitted:
            return
        statistics = self._runtime.custom_summary_statistics()
        if self._evaluation_profile_id is None:
            expected_evaluator_names = evaluator.EVALUATOR_CUSTOM_SUMMARY_STATISTIC_NAMES
        elif self._evaluation_profile_id == STOCK_PORTFOLIO_PROFILE_ID:
            expected_evaluator_names = (
                _stock_portfolio_module().expected_custom_summary_statistic_names(
                    self._evaluation_profile_id
                )
            )
        else:
            expected_evaluator_names = (
                regime_evaluator.expected_custom_summary_statistic_names(
                    self._evaluation_profile_id
                )
            )
        stock_portfolio = (
            self._evaluation_profile_id == STOCK_PORTFOLIO_PROFILE_ID
        )
        if (
            type(statistics) is not dict
            or tuple(sorted(statistics))
            != expected_evaluator_names
        ):
            _error("preliminary evaluator custom summary inventory changed")
        meta = {
            "schema": (
                "arv2-accepted-risk-preliminary-qc-runtime-meta-v1"
                if self._evaluation_profile_id is None
                else (
                    "arv2-accepted-risk-stock-portfolio-qc-runtime-meta-v1"
                    if stock_portfolio
                    else "arv2-accepted-risk-regime-qc-runtime-meta-v1"
                )
            ),
            "status": (
                "PRELIMINARY_ACCEPTED_RISK_STOCK_PORTFOLIO_COMPLETED"
                if stock_portfolio
                else "PRELIMINARY_ACCEPTED_RISK_STOCK_IC_ONLY_COMPLETED"
            ),
            "package_id": self._package.package_id,
            "package_sha256": self._package.package_sha256,
            "activation_manifest_sha256": self._package.activation_manifest_sha256,
            "symbol_resolution_id": self._resolution.resolution_id,
            "symbol_resolution_sha256": self._resolution.resolution_sha256,
            "resolved_security_count": self._resolution.resolved_count,
            "named_security_refusal_count": self._resolution.named_refusal_count,
            "result_transport": "aggregate_only_custom_summary_statistics",
            "host_object_store_export_required": False,
            "preliminary": True,
            "point_in_time": False,
            "formal": False,
            "control_residualized": False,
            "economic_portfolio": stock_portfolio,
            "etf_or_leverage": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        }
        if self._evaluation_profile_id is None:
            meta["training_slice_count"] = self._training_slice_count
        else:
            meta["evaluation_profile_id"] = self._evaluation_profile_id
            meta["evaluation_profile_sha256"] = self._evaluation_profile_sha256
            meta["runtime_slice_count"] = self._training_slice_count
        statistics[RUNTIME_META_STATISTIC] = _canonical(meta).decode("ascii")
        if (
            tuple(sorted(statistics))
            != expected_custom_summary_statistic_names(
                self._evaluation_profile_id
            )
            or any(
                type(key) is not str
                or type(value) is not str
                or len(key) > 64
                or len(value) > 4096
                for key, value in statistics.items()
            )
        ):
            _error("preliminary custom summary transport exceeded bound")
        try:
            for key, value in sorted(statistics.items()):
                self._algorithm.set_summary_statistic(key, value)
        except Exception as exc:
            raise AcceptedRiskPreliminaryQcRuntimeError(
                "preliminary custom summary statistic emission failed"
            ) from exc
        self._emitted = True

    def require_completed_at_end(self):
        if not self.completed or not self._emitted:
            if self._runtime is not None:
                self._runtime.abort()
            _error("preliminary QC backtest ended before aggregate completion")
        return True


__all__ = (
    "AcceptedRiskPreliminaryQcDriver",
    "AcceptedRiskPreliminaryQcRuntimeError",
    "BENCHMARK_SECURITY_ID",
    "BENCHMARK_TICKER",
    "EXPECTED_CUSTOM_SUMMARY_STATISTIC_NAMES",
    "LoadedAcceptedRiskPreliminaryPackage",
    "QcTotalReturnOpenHistoryLoader",
    "RUNTIME_META_STATISTIC",
    "STOCK_PORTFOLIO_PROFILE_ID",
    "MAX_BACKTEST_RUNTIME_SECONDS",
    "MAX_TRAIN_SLICE_COUNT",
    "TRAIN_SLICE_SOFT_SECONDS",
    "TRAIN_WORK_UNITS_PER_SLICE",
    "TRANSPORT_MANIFEST_SCHEMA",
    "load_accepted_risk_preliminary_package",
)
