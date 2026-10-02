"""Compact FIGI-only identity authority for the preliminary QC project.

This is deliberately separate from the lane's legacy current-ticker bridge so
the uploaded project has one small, reviewable identity path.  It accepts only
the host-authenticated section-72 binding schema, resolves every admitted
composite FIGI exactly once through QC, requires an exact reverse FIGI, and
constructs immutable O(1) maps for typed History traversal.
"""

import dataclasses
import hashlib
import json
import re
from datetime import date, datetime, timezone
from types import MappingProxyType


class PreliminaryQcFigiError(ValueError):
    """The projected binding, QC identity, or immutable map is inexact."""


INPUT_SCHEMA = (
    "arv2-owner-accepted-risk-preliminary-qc-composite-figi-binding-v1"
)
RESULT_SCHEMA = "arv2-owner-accepted-risk-qc-runtime-figi-resolution-v1"
REFUSAL_SCHEMA = "arv2-owner-accepted-risk-qc-runtime-figi-refusal-v1"
MAPPING_STATUS = (
    "owner_accepted_current_snapshot_composite_figi_requires_qc_exact_roundtrip"
)
AUTHORITY_MODE = (
    "owner_accepted_current_snapshot_composite_figi_roundtrip_not_pit_security_master"
)
FORMAL_ELIGIBILITY = "preliminary_only_frozen_formal_security_master_gate_open_false"
ALLOWED_EXCHANGES = ("XASE", "XNAS", "XNYS")

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/ -]{0,1023}\Z")
_FIGI = re.compile(r"[A-Z0-9]{12}\Z")
_TICKER = re.compile(r"[A-Z0-9][A-Z0-9.\-]{0,31}\Z")
_SID = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,255}\Z")
_PROXY = type(MappingProxyType({}))
_INPUT_FIELDS = {
    "schema",
    "security_id",
    "issuer_id",
    "composite_figi",
    "listing_id",
    "diagnostic_current_ticker",
    "diagnostic_exchange_mic",
    "candidate_first_session",
    "candidate_last_session",
    "source_snapshot_available_at",
    "source_row_sha256",
    "identity_evidence_sha256",
    "security_master_admission_sha256",
    "admitted_mapping_inventory_sha256",
    "admitted_mapping_count",
    "qc_security_id",
    "mapping_status",
    "qc_sid_available",
    "point_in_time",
    "independently_reviewed",
    "historical_availability_claimed",
    "current_snapshot_identity_basis",
    "owner_accepted_current_snapshot_risk",
    "row_sha256",
}
_RESOLVED_FIELDS = {
    "security_id",
    "source_binding_sha256",
    "external_composite_figi",
    "qc_security_id",
    "qc_display_ticker",
    "security_type",
    "market",
    "resolution_method",
    "resolution_sha256",
}
_REFUSAL_FIELDS = {
    "schema",
    "security_id",
    "source_binding_sha256",
    "external_composite_figi",
    "reason",
    "refusal_sha256",
}
_REFUSAL_REASONS = {
    "qc_runtime_composite_figi_resolution_unavailable",
    "qc_runtime_composite_figi_not_us_equity",
    "qc_runtime_composite_figi_roundtrip_mismatch",
    "qc_runtime_security_identifier_collision",
    "qc_runtime_benchmark_security_identifier_collision",
}


def _error(message):
    raise PreliminaryQcFigiError(message)


def _canonical(value):
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise PreliminaryQcFigiError("FIGI authority value is not canonical JSON") from exc


def _hash(value, name):
    if type(value) is not str or _HEX.fullmatch(value) is None:
        _error(name + " is not lowercase SHA-256")
    return value


def _safe(value, name):
    if type(value) is not str or _SAFE.fullmatch(value) is None:
        _error(name + " is not a safe identifier")
    return value


def _session(value, name):
    if type(value) is not str:
        _error(name + " is not a session date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise PreliminaryQcFigiError(name + " is not a session date") from exc
    if parsed.isoformat() != value:
        _error(name + " is not a canonical session date")
    return value


def _normalized_utc(value, name):
    if type(value) is not str:
        _error(name + " is not an exact instant")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PreliminaryQcFigiError(name + " is not an exact instant") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _error(name + " is not an exact instant")
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def build_preliminary_qc_figi_binding(
    *,
    security_id,
    issuer_id,
    composite_figi,
    listing_id,
    diagnostic_current_ticker,
    diagnostic_exchange_mic,
    candidate_first_session,
    candidate_last_session,
    source_snapshot_available_at,
    source_row_sha256,
    identity_evidence_sha256,
    security_master_admission_sha256,
    admitted_mapping_inventory_sha256,
    admitted_mapping_count,
):
    """Project one authenticated admission into the FIGI-only cloud schema.

    The ticker and MIC are retained only to make diagnostics intelligible.  QC
    identity is established exclusively by the explicit composite FIGI and its
    exact reverse mapping; neither diagnostic field participates in matching.
    """

    seed = {
        "schema": INPUT_SCHEMA,
        "security_id": security_id,
        "issuer_id": issuer_id,
        "composite_figi": composite_figi,
        "listing_id": listing_id,
        "diagnostic_current_ticker": diagnostic_current_ticker,
        "diagnostic_exchange_mic": diagnostic_exchange_mic,
        "candidate_first_session": candidate_first_session,
        "candidate_last_session": candidate_last_session,
        "source_snapshot_available_at": _normalized_utc(
            source_snapshot_available_at,
            "preliminary source snapshot availability",
        ),
        "source_row_sha256": source_row_sha256,
        "identity_evidence_sha256": identity_evidence_sha256,
        "security_master_admission_sha256": security_master_admission_sha256,
        "admitted_mapping_inventory_sha256": admitted_mapping_inventory_sha256,
        "admitted_mapping_count": admitted_mapping_count,
        "qc_security_id": None,
        "mapping_status": MAPPING_STATUS,
        "qc_sid_available": False,
        "point_in_time": False,
        "independently_reviewed": False,
        "historical_availability_claimed": False,
        "current_snapshot_identity_basis": True,
        "owner_accepted_current_snapshot_risk": True,
    }
    seed["row_sha256"] = hashlib.sha256(_canonical(seed)).hexdigest()
    return _input_row(seed, security_master_admission_sha256)


def _input_row(value, expected_admission_sha256):
    if type(value) is not dict or set(value) != _INPUT_FIELDS:
        _error("preliminary FIGI binding schema or fields changed")
    row = dict(value)
    if row.get("schema") != INPUT_SCHEMA:
        _error("preliminary FIGI binding schema or fields changed")
    security_id = _safe(row.get("security_id"), "preliminary security")
    _safe(row.get("issuer_id"), "preliminary issuer")
    _safe(row.get("listing_id"), "preliminary listing")
    figi = row.get("composite_figi")
    if (
        type(figi) is not str
        or _FIGI.fullmatch(figi) is None
        or security_id != "sharadar-composite-figi-" + figi
    ):
        _error("preliminary FIGI binding external identity changed")
    if (
        type(row.get("diagnostic_current_ticker")) is not str
        or _TICKER.fullmatch(row["diagnostic_current_ticker"]) is None
        or type(row.get("diagnostic_exchange_mic")) is not str
        or row["diagnostic_exchange_mic"] not in ALLOWED_EXCHANGES
    ):
        _error("preliminary FIGI binding display or exchange changed")
    first = _session(row.get("candidate_first_session"), "candidate first session")
    last = _session(row.get("candidate_last_session"), "candidate last session")
    if first > last:
        _error("preliminary FIGI binding interval is reversed")
    available = row.get("source_snapshot_available_at")
    if type(available) is not str or not available.endswith("Z"):
        _error("preliminary FIGI binding availability changed")
    try:
        parsed = datetime.fromisoformat(available[:-1] + "+00:00")
    except ValueError as exc:
        raise PreliminaryQcFigiError(
            "preliminary FIGI binding availability changed"
        ) from exc
    if (
        parsed.utcoffset() != timezone.utc.utcoffset(parsed)
        or parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != available
    ):
        _error("preliminary FIGI binding availability changed")
    for name in (
        "source_row_sha256",
        "identity_evidence_sha256",
        "security_master_admission_sha256",
        "admitted_mapping_inventory_sha256",
        "row_sha256",
    ):
        _hash(row.get(name), "preliminary FIGI binding " + name)
    if row["security_master_admission_sha256"] != expected_admission_sha256:
        _error("preliminary FIGI binding admission lineage changed")
    if (
        type(row.get("admitted_mapping_count")) is not int
        or row["admitted_mapping_count"] < 1
        or row.get("qc_security_id") is not None
        or row.get("mapping_status") != MAPPING_STATUS
        or type(row.get("mapping_status")) is not str
        or row.get("qc_sid_available") is not False
        or row.get("point_in_time") is not False
        or row.get("independently_reviewed") is not False
        or row.get("historical_availability_claimed") is not False
        or row.get("current_snapshot_identity_basis") is not True
        or row.get("owner_accepted_current_snapshot_risk") is not True
    ):
        _error("preliminary FIGI binding accepted-risk disclosure changed")
    semantic = dict(row)
    declared = semantic.pop("row_sha256")
    if hashlib.sha256(_canonical(semantic)).hexdigest() != declared:
        _error("preliminary FIGI binding content hash changed")
    return row


def _symbol_identity(symbol, name):
    try:
        symbol_id = symbol.id
        sid = str(symbol_id)
        ticker = symbol.value
        security_type = str(symbol.security_type)
        market = str(symbol_id.market)
    except Exception as exc:
        raise PreliminaryQcFigiError(name + " symbol identity is unreadable") from exc
    if (
        symbol_id is None
        or type(sid) is not str
        or _SID.fullmatch(sid) is None
        or type(ticker) is not str
        or _TICKER.fullmatch(ticker) is None
    ):
        _error(name + " symbol identity is malformed")
    return sid, ticker, security_type.lower(), market.lower()


def _refusal(row, reason):
    if reason not in _REFUSAL_REASONS:
        _error("preliminary FIGI refusal reason changed")
    semantic = {
        "schema": REFUSAL_SCHEMA,
        "security_id": row["security_id"],
        "source_binding_sha256": row["row_sha256"],
        "external_composite_figi": row["composite_figi"],
        "reason": reason,
    }
    return {
        **semantic,
        "refusal_sha256": hashlib.sha256(_canonical(semantic)).hexdigest(),
    }


@dataclasses.dataclass(frozen=True)
class PreliminaryQcFigiResolution:
    schema: str
    resolution_id: str
    resolution_sha256: str
    authority_mode: str
    formal_eligibility: str
    input_row_count: int
    resolved_count: int
    named_refusal_count: int
    resolved: tuple
    named_refusals: tuple
    point_in_time: bool
    formal_security_master_authority: bool
    preliminary_evaluation_eligible: bool
    _input_rows: tuple = dataclasses.field(repr=False)
    _symbol_by_security: object = dataclasses.field(repr=False)
    _security_by_sid: object = dataclasses.field(repr=False)
    _refusal_by_security: object = dataclasses.field(repr=False)
    _fingerprint: tuple = dataclasses.field(repr=False)

    def to_record(self):
        return {
            "schema": self.schema,
            "resolution_id": self.resolution_id,
            "resolution_sha256": self.resolution_sha256,
            "authority_mode": self.authority_mode,
            "formal_eligibility": self.formal_eligibility,
            "input_row_count": self.input_row_count,
            "resolved_count": self.resolved_count,
            "named_refusal_count": self.named_refusal_count,
            "resolved": [dict(item) for item in self.resolved],
            "named_refusals": [dict(item) for item in self.named_refusals],
            "point_in_time": self.point_in_time,
            "formal_security_master_authority": self.formal_security_master_authority,
            "preliminary_evaluation_eligible": self.preliminary_evaluation_eligible,
        }

    def symbol_for_security(self, security_id):
        if type(security_id) is not str:
            _error("preliminary History security identity changed")
        return self._symbol_by_security.get(security_id)

    def refusal_reason(self, security_id):
        if type(security_id) is not str:
            _error("preliminary History security identity changed")
        return self._refusal_by_security.get(security_id)

    def security_for_qc_sid(self, qc_sid):
        if type(qc_sid) is not str or _SID.fullmatch(qc_sid) is None:
            _error("preliminary History SID is malformed")
        value = self._security_by_sid.get(qc_sid)
        if value is None:
            _error("preliminary History returned an unbound SID")
        return value


def _public_seed(rows, resolved, refusals):
    return {
        "schema": RESULT_SCHEMA,
        "resolution_id": None,
        "resolution_sha256": None,
        "authority_mode": AUTHORITY_MODE,
        "formal_eligibility": FORMAL_ELIGIBILITY,
        "input_row_count": len(rows),
        "resolved_count": len(resolved),
        "named_refusal_count": len(refusals),
        "resolved": [dict(item) for item in resolved],
        "named_refusals": [dict(item) for item in refusals],
        "point_in_time": False,
        "formal_security_master_authority": False,
        "preliminary_evaluation_eligible": True,
    }


def resolve_preliminary_qc_figis(
    rows,
    *,
    expected_security_master_admission_sha256,
    composite_figi,
    benchmark_symbol,
):
    """Resolve the complete projected admission with exact FIGI round trips."""

    _hash(
        expected_security_master_admission_sha256,
        "preliminary expected security-master admission",
    )
    if type(rows) not in (tuple, list) or not rows or not callable(composite_figi):
        _error("preliminary FIGI resolver input changed")
    normalized = tuple(
        _input_row(item, expected_security_master_admission_sha256) for item in rows
    )
    if normalized != tuple(sorted(normalized, key=lambda item: item["security_id"])):
        _error("preliminary FIGI bindings are not in logical-security order")
    ids = [item["security_id"] for item in normalized]
    figis = [item["composite_figi"] for item in normalized]
    hashes = [item["row_sha256"] for item in normalized]
    if (
        len(set(ids)) != len(ids)
        or len(set(figis)) != len(figis)
        or len(set(hashes)) != len(hashes)
    ):
        _error("preliminary FIGI binding inventory repeats an identity")
    if (
        {item["admitted_mapping_count"] for item in normalized}
        != {len(normalized)}
        or len({item["admitted_mapping_inventory_sha256"] for item in normalized})
        != 1
    ):
        _error("preliminary FIGI binding inventory is a subset or mixed")
    benchmark_sid, benchmark_ticker, benchmark_type, benchmark_market = _symbol_identity(
        benchmark_symbol, "preliminary benchmark"
    )
    if (
        benchmark_ticker != "SPY"
        or benchmark_type not in ("equity", "securitytype.equity")
        or benchmark_market != "usa"
    ):
        _error("preliminary benchmark is not exact SPY US equity")
    candidates = []
    refusals = []
    for row in normalized:
        figi = row["composite_figi"]
        try:
            symbol = composite_figi(figi)
        except Exception as exc:
            raise PreliminaryQcFigiError(
                "preliminary composite-FIGI forward resolver raised"
            ) from exc
        if symbol is None:
            refusals.append(
                _refusal(row, "qc_runtime_composite_figi_resolution_unavailable")
            )
            continue
        sid, ticker, security_type, market = _symbol_identity(
            symbol, "preliminary composite-FIGI"
        )
        if security_type not in ("equity", "securitytype.equity") or market != "usa":
            refusals.append(_refusal(row, "qc_runtime_composite_figi_not_us_equity"))
            continue
        try:
            reversed_figi = composite_figi(symbol)
        except Exception as exc:
            raise PreliminaryQcFigiError(
                "preliminary composite-FIGI reverse resolver raised"
            ) from exc
        if type(reversed_figi) is not str or _FIGI.fullmatch(reversed_figi) is None:
            _error("preliminary composite-FIGI reverse identity is malformed")
        if reversed_figi != figi:
            refusals.append(
                _refusal(row, "qc_runtime_composite_figi_roundtrip_mismatch")
            )
            continue
        candidates.append((row, symbol, sid, ticker))
    counts = {}
    for _row, _symbol, sid, _ticker in candidates:
        counts[sid] = counts.get(sid, 0) + 1
    resolved = []
    symbols = {}
    reverse = {}
    for row, symbol, sid, ticker in candidates:
        reason = None
        if sid == benchmark_sid:
            reason = "qc_runtime_benchmark_security_identifier_collision"
        elif counts[sid] != 1:
            reason = "qc_runtime_security_identifier_collision"
        if reason is not None:
            refusals.append(_refusal(row, reason))
            continue
        semantic = {
            "security_id": row["security_id"],
            "source_binding_sha256": row["row_sha256"],
            "external_composite_figi": row["composite_figi"],
            "qc_security_id": sid,
            "qc_display_ticker": ticker,
            "security_type": "Equity",
            "market": "usa",
            "resolution_method": "composite_figi_exact_roundtrip",
        }
        record = {
            **semantic,
            "resolution_sha256": hashlib.sha256(_canonical(semantic)).hexdigest(),
        }
        resolved.append(record)
        symbols[row["security_id"]] = symbol
        reverse[sid] = row["security_id"]
    resolved.sort(key=lambda item: item["security_id"])
    refusals.sort(key=lambda item: item["security_id"])
    if len(resolved) + len(refusals) != len(normalized):
        _error("preliminary FIGI resolution omitted an input terminal")
    if not resolved:
        _error("preliminary composite-FIGI resolution produced zero usable securities")
    seed = _public_seed(normalized, tuple(resolved), tuple(refusals))
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    seed["resolution_id"] = "arv2-preliminary-qc-figis-" + digest[:24]
    seed["resolution_sha256"] = digest
    fingerprint = tuple(
        (
            item["security_id"],
            item["external_composite_figi"],
            item["qc_security_id"],
            item["qc_display_ticker"],
            id(symbols[item["security_id"]]),
        )
        for item in resolved
    )
    value = PreliminaryQcFigiResolution(
        RESULT_SCHEMA,
        seed["resolution_id"],
        digest,
        AUTHORITY_MODE,
        FORMAL_ELIGIBILITY,
        len(normalized),
        len(resolved),
        len(refusals),
        tuple(resolved),
        tuple(refusals),
        False,
        False,
        True,
        normalized,
        MappingProxyType(symbols),
        MappingProxyType(reverse),
        MappingProxyType(
            {item["security_id"]: item["reason"] for item in refusals}
        ),
        fingerprint,
    )
    return require_preliminary_qc_figi_resolution(value)


def require_preliminary_qc_figi_resolution(value):
    if type(value) is not PreliminaryQcFigiResolution:
        _error("preliminary FIGI resolution type changed")
    if any(
        type(item) is not str
        for item in (
            value.schema,
            value.resolution_id,
            value.resolution_sha256,
            value.authority_mode,
            value.formal_eligibility,
        )
    ):
        _error("preliminary FIGI resolution scalar type changed")
    if any(
        type(item) is not int or item < 0
        for item in (
            value.input_row_count,
            value.resolved_count,
            value.named_refusal_count,
        )
    ):
        _error("preliminary FIGI resolution count type changed")
    if (
        value.schema != RESULT_SCHEMA
        or value.authority_mode != AUTHORITY_MODE
        or value.formal_eligibility != FORMAL_ELIGIBILITY
        or value.point_in_time is not False
        or value.formal_security_master_authority is not False
        or value.preliminary_evaluation_eligible is not True
        or type(value.resolved) is not tuple
        or type(value.named_refusals) is not tuple
        or type(value._input_rows) is not tuple
        or type(value._fingerprint) is not tuple
        or type(value._symbol_by_security) is not _PROXY
        or type(value._security_by_sid) is not _PROXY
        or type(value._refusal_by_security) is not _PROXY
    ):
        _error("preliminary FIGI resolution topology or disclosure changed")
    admission_hashes = {
        item.get("security_master_admission_sha256")
        for item in value._input_rows
        if type(item) is dict
    }
    if len(admission_hashes) != 1:
        _error("preliminary FIGI resolution input lineage changed")
    expected_admission = next(iter(admission_hashes))
    normalized = tuple(_input_row(item, expected_admission) for item in value._input_rows)
    if (
        not normalized
        or normalized
        != tuple(sorted(normalized, key=lambda item: item["security_id"]))
        or len({item["security_id"] for item in normalized}) != len(normalized)
        or {item["admitted_mapping_count"] for item in normalized}
        != {len(normalized)}
        or len(
            {item["admitted_mapping_inventory_sha256"] for item in normalized}
        )
        != 1
    ):
        _error("preliminary FIGI resolution input inventory changed")
    if any(type(item) is not dict for item in value.resolved):
        _error("preliminary FIGI resolved record type changed")
    if any(type(item) is not dict for item in value.named_refusals):
        _error("preliminary FIGI refusal record type changed")
    resolved = tuple(dict(item) for item in value.resolved)
    refusals = tuple(dict(item) for item in value.named_refusals)
    if (
        not resolved
        or resolved
        != tuple(sorted(resolved, key=lambda item: item["security_id"]))
        or refusals
        != tuple(sorted(refusals, key=lambda item: item["security_id"]))
        or len({item.get("security_id") for item in resolved}) != len(resolved)
        or len({item.get("security_id") for item in refusals}) != len(refusals)
        or {item.get("security_id") for item in resolved}
        & {item.get("security_id") for item in refusals}
    ):
        _error("preliminary FIGI terminal inventory changed")
    input_figis = {
        item["security_id"]: item["composite_figi"] for item in normalized
    }
    for item in resolved:
        if (
            set(item) != _RESOLVED_FIELDS
            or type(item["security_id"]) is not str
            or type(item["source_binding_sha256"]) is not str
            or _HEX.fullmatch(item["source_binding_sha256"]) is None
            or type(item["external_composite_figi"]) is not str
            or _FIGI.fullmatch(item["external_composite_figi"]) is None
            or input_figis.get(item["security_id"])
            != item["external_composite_figi"]
            or type(item["qc_security_id"]) is not str
            or _SID.fullmatch(item["qc_security_id"]) is None
            or type(item["qc_display_ticker"]) is not str
            or _TICKER.fullmatch(item["qc_display_ticker"]) is None
            or type(item["security_type"]) is not str
            or item["security_type"] != "Equity"
            or type(item["market"]) is not str
            or item["market"] != "usa"
            or type(item["resolution_method"]) is not str
            or item["resolution_method"] != "composite_figi_exact_roundtrip"
            or type(item["resolution_sha256"]) is not str
            or _HEX.fullmatch(item["resolution_sha256"]) is None
        ):
            _error("preliminary FIGI resolved record schema changed")
        semantic = dict(item)
        declared = semantic.pop("resolution_sha256")
        if hashlib.sha256(_canonical(semantic)).hexdigest() != declared:
            _error("preliminary FIGI resolved record identity changed")
    for item in refusals:
        if (
            set(item) != _REFUSAL_FIELDS
            or item.get("schema") != REFUSAL_SCHEMA
            or type(item.get("security_id")) is not str
            or type(item.get("source_binding_sha256")) is not str
            or _HEX.fullmatch(item["source_binding_sha256"]) is None
            or type(item.get("external_composite_figi")) is not str
            or _FIGI.fullmatch(item["external_composite_figi"]) is None
            or input_figis.get(item["security_id"])
            != item["external_composite_figi"]
            or type(item.get("reason")) is not str
            or item["reason"] not in _REFUSAL_REASONS
            or type(item.get("refusal_sha256")) is not str
            or _HEX.fullmatch(item["refusal_sha256"]) is None
        ):
            _error("preliminary FIGI refusal record schema changed")
        semantic = dict(item)
        declared = semantic.pop("refusal_sha256")
        if hashlib.sha256(_canonical(semantic)).hexdigest() != declared:
            _error("preliminary FIGI refusal record identity changed")
    symbol_items = tuple(value._symbol_by_security.items())
    reverse_items = tuple(value._security_by_sid.items())
    refusal_items = tuple(value._refusal_by_security.items())
    if (
        any(type(key) is not str for key, _symbol in symbol_items)
        or any(
            type(sid) is not str
            or _SID.fullmatch(sid) is None
            or type(security) is not str
            for sid, security in reverse_items
        )
        or any(
            type(security) is not str
            or type(reason) is not str
            or reason not in _REFUSAL_REASONS
            for security, reason in refusal_items
        )
    ):
        _error("preliminary FIGI immutable-map scalar changed")
    expected_symbols = {item["security_id"] for item in resolved}
    expected_reverse = {
        item["qc_security_id"]: item["security_id"] for item in resolved
    }
    expected_refusals = {item["security_id"]: item["reason"] for item in refusals}
    if (
        set(value._symbol_by_security) != expected_symbols
        or dict(value._security_by_sid) != expected_reverse
        or dict(value._refusal_by_security) != expected_refusals
    ):
        _error("preliminary FIGI immutable-map inventory changed")
    fingerprint = []
    for item in resolved:
        symbol = value._symbol_by_security[item["security_id"]]
        sid, ticker, security_type, market = _symbol_identity(
            symbol, "preliminary cached composite-FIGI"
        )
        if (
            sid != item["qc_security_id"]
            or ticker != item["qc_display_ticker"]
            or security_type not in ("equity", "securitytype.equity")
            or market != "usa"
        ):
            _error("preliminary cached composite-FIGI symbol changed")
        fingerprint.append(
            (
                item["security_id"],
                item["external_composite_figi"],
                sid,
                ticker,
                id(symbol),
            )
        )
    if tuple(fingerprint) != value._fingerprint:
        _error("preliminary FIGI immutable-map fingerprint changed")
    input_hashes = {item["security_id"]: item["row_sha256"] for item in normalized}
    terminal_hashes = {
        item["security_id"]: item["source_binding_sha256"]
        for item in (*resolved, *refusals)
    }
    if terminal_hashes != input_hashes:
        _error("preliminary FIGI terminals do not cover exact inputs")
    seed = _public_seed(normalized, resolved, refusals)
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    expected = {
        **seed,
        "resolution_id": "arv2-preliminary-qc-figis-" + digest[:24],
        "resolution_sha256": digest,
    }
    if value.to_record() != expected:
        _error("preliminary FIGI resolution public record changed")
    return value


__all__ = (
    "AUTHORITY_MODE",
    "INPUT_SCHEMA",
    "MAPPING_STATUS",
    "PreliminaryQcFigiError",
    "PreliminaryQcFigiResolution",
    "build_preliminary_qc_figi_binding",
    "require_preliminary_qc_figi_resolution",
    "resolve_preliminary_qc_figis",
)
