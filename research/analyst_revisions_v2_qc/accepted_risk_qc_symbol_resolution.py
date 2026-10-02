"""Owner-accepted current-ticker resolution inside QuantConnect.

This module is a deliberately narrow bridge for the 2026-09-14 section-72
accepted-risk path.  It converts an already-admitted Sharadar current-snapshot
identity into a runtime QC ``Symbol`` without pretending that the result is a
point-in-time security-master join.  The caller supplies the symbol factory so
the contract can be tested without importing LEAN on the host.

The result is suitable only for the explicitly labelled preliminary path.  It
is not a reviewed QC-SID authority and cannot make the frozen formal path true.
Every admitted row is represented by either one resolved symbol or one named
refusal; collisions refuse every member of the collision group.
"""
import dataclasses
import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, timezone
from types import MappingProxyType


class AcceptedRiskQcSymbolResolutionError(ValueError):
    """The runtime ticker-resolution input or result is not exact."""


INPUT_SCHEMA = "arv2-owner-accepted-risk-qc-runtime-ticker-binding-v1"
RESULT_SCHEMA = "arv2-owner-accepted-risk-qc-runtime-symbol-resolution-v1"
REFUSAL_SCHEMA = "arv2-owner-accepted-risk-qc-runtime-symbol-refusal-v1"
MAPPING_STATUS = (
    "owner_accepted_unique_current_snapshot_ticker_requires_qc_runtime_resolution"
)
AUTHORITY_MODE = "owner_accepted_current_snapshot_ticker_not_pit_security_master"
COMPOSITE_FIGI_AUTHORITY_MODE = (
    "owner_accepted_current_snapshot_composite_figi_roundtrip_not_pit_security_master"
)
FORMAL_ELIGIBILITY = "preliminary_only_frozen_formal_security_master_gate_open_false"
ALLOWED_EXCHANGE_MICS = ("XASE", "XNAS", "XNYS")
ADMISSION_MAPPING_SCHEMA = "arv2-owner-accepted-risk-sharadar-security-mapping-v1"

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,1023}\Z")
_TICKER = re.compile(r"[A-Z0-9][A-Z0-9.\-]{0,31}\Z")
_QC_SID = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,255}\Z")
_MAPPING_PROXY_TYPE = type(MappingProxyType({}))
_FIGI = re.compile(r"[A-Z0-9]{12}\Z")
_CUSIP = re.compile(r"[0-9A-Z]{9}\Z")
_ADMISSION_MAPPING_FIELDS = {
    "schema",
    "source_ordinal",
    "source_row_sha256",
    "security_id",
    "issuer_id",
    "composite_figi",
    "listing_id",
    "ticker",
    "exchange_id",
    "cusip_join_candidates",
    "sector_id",
    "industry_id",
    "candidate_first_session",
    "candidate_last_session",
    "identity_evidence_sha256",
    "classification_evidence_sha256",
    "source_snapshot_available_at",
    "qc_security_id",
    "mapping_status",
    "qc_sid_available",
    "point_in_time",
    "independently_reviewed",
    "historical_availability_claimed",
    "current_snapshot_identity_basis",
    "owner_accepted_current_snapshot_risk",
}
_INPUT_FIELDS = {
    "schema",
    "security_id",
    "issuer_id",
    "share_class_id",
    "listing_id",
    "current_snapshot_ticker",
    "exchange_mic",
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
    "qc_security_id",
    "current_snapshot_ticker",
    "security_type",
    "market",
    "external_composite_figi",
    "resolution_method",
    "resolution_sha256",
}
_REFUSAL_FIELDS = {
    "schema",
    "security_id",
    "source_binding_sha256",
    "reason",
    "refusal_sha256",
}


def _canonical(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime symbol resolution value is not canonical JSON"
        ) from exc


def _sha(value: object, name: str) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise AcceptedRiskQcSymbolResolutionError(f"{name} is not lowercase SHA-256")
    return value


def _safe(value: object, name: str) -> str:
    if (
        type(value) is not str
        or _SAFE.fullmatch(value) is None
        or value.startswith("/")
        or "//" in value
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise AcceptedRiskQcSymbolResolutionError(f"{name} is not a safe identifier")
    return value


def _session(value: object, name: str) -> str:
    if type(value) is not str:
        raise AcceptedRiskQcSymbolResolutionError(f"{name} is not a session date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise AcceptedRiskQcSymbolResolutionError(
            f"{name} is not a session date"
        ) from exc
    if parsed.isoformat() != value:
        raise AcceptedRiskQcSymbolResolutionError(
            f"{name} is not canonical session text"
        )
    return value


def _utc(value: object, name: str) -> str:
    if type(value) is not str or not value.endswith("Z"):
        raise AcceptedRiskQcSymbolResolutionError(f"{name} is not canonical UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise AcceptedRiskQcSymbolResolutionError(
            f"{name} is not canonical UTC"
        ) from exc
    if (
        parsed.utcoffset() != timezone.utc.utcoffset(parsed)
        or parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value
    ):
        raise AcceptedRiskQcSymbolResolutionError(f"{name} is not canonical UTC")
    return value


def _normalized_admission_utc(value: object) -> str:
    if type(value) is not str:
        raise AcceptedRiskQcSymbolResolutionError(
            "admitted security source snapshot is not an exact instant"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AcceptedRiskQcSymbolResolutionError(
            "admitted security source snapshot is not an exact instant"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AcceptedRiskQcSymbolResolutionError(
            "admitted security source snapshot is not an exact instant"
        )
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def project_admitted_security_master_mappings(
    rows: Sequence[Mapping[str, object]],
    *,
    security_master_admission_sha256: str,
    admitted_mapping_inventory_sha256: str,
) -> tuple[dict[str, object], ...]:
    """Project the exact admitted inventory into the QC-only binding schema.

    Both hashes are expected to be pinned by the reviewed project source.  The
    inventory hash prevents an admission SHA from being attached to a
    caller-selected subset or to modified mapping scalars.
    """

    _sha(security_master_admission_sha256, "security-master admission")
    _sha(admitted_mapping_inventory_sha256, "admitted mapping inventory")
    if type(rows) not in (tuple, list) or not rows:
        raise AcceptedRiskQcSymbolResolutionError(
            "admitted security mapping inventory is empty or not exact"
        )
    if any(type(row) is not dict for row in rows):
        raise AcceptedRiskQcSymbolResolutionError(
            "admitted security mapping inventory contains a non-exact row"
        )
    copied = tuple(dict(row) for row in rows)
    if hashlib.sha256(_canonical(list(copied))).hexdigest() != admitted_mapping_inventory_sha256:
        raise AcceptedRiskQcSymbolResolutionError(
            "admitted security mapping inventory escaped its reviewed hash"
        )
    ordinals: list[int] = []
    projected: list[dict[str, object]] = []
    for row in copied:
        if set(row) != _ADMISSION_MAPPING_FIELDS or row.get("schema") != ADMISSION_MAPPING_SCHEMA:
            raise AcceptedRiskQcSymbolResolutionError(
                "admitted security mapping schema or field inventory changed"
            )
        ordinal = row["source_ordinal"]
        if type(ordinal) is not int or ordinal < 0:
            raise AcceptedRiskQcSymbolResolutionError(
                "admitted security mapping source ordinal changed"
            )
        ordinals.append(ordinal)
        security_id = _safe(row["security_id"], "admitted security_id")
        issuer_id = _safe(row["issuer_id"], "admitted issuer_id")
        listing_id = _safe(row["listing_id"], "admitted listing_id")
        figi = row["composite_figi"]
        ticker = row["ticker"]
        if (
            type(figi) is not str
            or _FIGI.fullmatch(figi) is None
            or security_id != "sharadar-composite-figi-" + figi
        ):
            raise AcceptedRiskQcSymbolResolutionError(
                "admitted security external identity changed"
            )
        if type(ticker) is not str or _TICKER.fullmatch(ticker) is None:
            raise AcceptedRiskQcSymbolResolutionError(
                "admitted security current snapshot ticker changed"
            )
        if row["exchange_id"] not in ALLOWED_EXCHANGE_MICS:
            raise AcceptedRiskQcSymbolResolutionError(
                "admitted security exchange is outside the US universe"
            )
        cusips = row["cusip_join_candidates"]
        if (
            type(cusips) is not list
            or any(type(item) is not str or _CUSIP.fullmatch(item) is None for item in cusips)
            or len(cusips) != len(set(cusips))
            or cusips != sorted(cusips)
        ):
            raise AcceptedRiskQcSymbolResolutionError(
                "admitted security CUSIP candidate inventory changed"
            )
        _safe(row["sector_id"], "admitted sector_id")
        _safe(row["industry_id"], "admitted industry_id")
        first = _session(row["candidate_first_session"], "admitted first session")
        last = _session(row["candidate_last_session"], "admitted last session")
        if first > last:
            raise AcceptedRiskQcSymbolResolutionError(
                "admitted security candidate interval is reversed"
            )
        for field in (
            "source_row_sha256",
            "identity_evidence_sha256",
            "classification_evidence_sha256",
        ):
            _sha(row[field], "admitted security " + field)
        expected_risk = {
            "qc_security_id": None,
            "qc_sid_available": False,
            "point_in_time": False,
            "independently_reviewed": False,
            "historical_availability_claimed": False,
            "current_snapshot_identity_basis": True,
            "owner_accepted_current_snapshot_risk": True,
        }
        if any(row.get(field) is not expected for field, expected in expected_risk.items()):
            raise AcceptedRiskQcSymbolResolutionError(
                "admitted security accepted-risk disclosure changed"
            )
        if type(row.get("mapping_status")) is not str or row["mapping_status"] != MAPPING_STATUS:
            raise AcceptedRiskQcSymbolResolutionError(
                "admitted security accepted-risk disclosure changed"
            )
        projected.append(
            build_runtime_ticker_binding(
                security_id=security_id,
                issuer_id=issuer_id,
                share_class_id=figi,
                listing_id=listing_id,
                current_snapshot_ticker=ticker,
                exchange_mic=str(row["exchange_id"]),
                candidate_first_session=first,
                candidate_last_session=last,
                source_snapshot_available_at=_normalized_admission_utc(
                    row["source_snapshot_available_at"]
                ),
                source_row_sha256=str(row["source_row_sha256"]),
                identity_evidence_sha256=str(row["identity_evidence_sha256"]),
                security_master_admission_sha256=security_master_admission_sha256,
                admitted_mapping_inventory_sha256=admitted_mapping_inventory_sha256,
                admitted_mapping_count=len(copied),
            )
        )
    if len(ordinals) != len(set(ordinals)):
        raise AcceptedRiskQcSymbolResolutionError(
            "admitted security mapping source ordinal repeats"
        )
    if copied != tuple(sorted(copied, key=lambda item: (item["ticker"], item["security_id"]))):
        raise AcceptedRiskQcSymbolResolutionError(
            "admitted security mapping inventory is not in producer order"
        )
    result = tuple(sorted(projected, key=lambda item: item["security_id"]))
    if len({item["security_id"] for item in result}) != len(result):
        raise AcceptedRiskQcSymbolResolutionError(
            "admitted security mapping repeats a logical security"
        )
    return result


def build_runtime_ticker_binding(
    *,
    security_id: str,
    issuer_id: str,
    share_class_id: str,
    listing_id: str,
    current_snapshot_ticker: str,
    exchange_mic: str,
    candidate_first_session: str,
    candidate_last_session: str,
    source_snapshot_available_at: str,
    source_row_sha256: str,
    identity_evidence_sha256: str,
    security_master_admission_sha256: str,
    admitted_mapping_inventory_sha256: str,
    admitted_mapping_count: int,
) -> dict[str, object]:
    """Render one exact input row without accepting a caller QC SID."""

    seed: dict[str, object] = {
        "schema": INPUT_SCHEMA,
        "security_id": security_id,
        "issuer_id": issuer_id,
        "share_class_id": share_class_id,
        "listing_id": listing_id,
        "current_snapshot_ticker": current_snapshot_ticker,
        "exchange_mic": exchange_mic,
        "candidate_first_session": candidate_first_session,
        "candidate_last_session": candidate_last_session,
        "source_snapshot_available_at": source_snapshot_available_at,
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
    return _validated_input(seed)


def _validated_input(value: object) -> dict[str, object]:
    if (
        type(value) is not dict
        or set(value) != _INPUT_FIELDS
        or value.get("schema") != INPUT_SCHEMA
    ):
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime ticker binding schema or field inventory changed"
        )
    row = dict(value)
    for field in ("security_id", "issuer_id", "share_class_id", "listing_id"):
        _safe(row[field], f"runtime ticker binding {field}")
    ticker = row["current_snapshot_ticker"]
    if type(ticker) is not str or _TICKER.fullmatch(ticker) is None:
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime ticker binding current snapshot ticker is invalid"
        )
    if (
        type(row["exchange_mic"]) is not str
        or row["exchange_mic"] not in ALLOWED_EXCHANGE_MICS
    ):
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime ticker binding exchange is outside the admitted US universe"
        )
    first = _session(
        row["candidate_first_session"], "runtime ticker binding first session"
    )
    last = _session(
        row["candidate_last_session"], "runtime ticker binding last session"
    )
    if first > last:
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime ticker binding session interval is reversed"
        )
    _utc(
        row["source_snapshot_available_at"],
        "runtime ticker binding source snapshot availability",
    )
    for field in (
        "source_row_sha256",
        "identity_evidence_sha256",
        "security_master_admission_sha256",
        "admitted_mapping_inventory_sha256",
    ):
        _sha(row[field], f"runtime ticker binding {field}")
    if type(row["admitted_mapping_count"]) is not int or row["admitted_mapping_count"] < 1:
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime ticker binding admitted mapping count changed"
        )
    expected_risk = {
        "qc_security_id": None,
        "qc_sid_available": False,
        "point_in_time": False,
        "independently_reviewed": False,
        "historical_availability_claimed": False,
        "current_snapshot_identity_basis": True,
        "owner_accepted_current_snapshot_risk": True,
    }
    if any(row.get(field) is not expected for field, expected in expected_risk.items()):
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime ticker binding accepted-risk disclosure changed"
        )
    if type(row.get("mapping_status")) is not str or row["mapping_status"] != MAPPING_STATUS:
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime ticker binding accepted-risk disclosure changed"
        )
    declared = _sha(row["row_sha256"], "runtime ticker binding row")
    semantic = dict(row)
    semantic.pop("row_sha256")
    if hashlib.sha256(_canonical(semantic)).hexdigest() != declared:
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime ticker binding content hash changed"
        )
    return row


def _refusal(row: Mapping[str, object], reason: str) -> dict[str, object]:
    semantic = {
        "schema": REFUSAL_SCHEMA,
        "security_id": row["security_id"],
        "source_binding_sha256": row["row_sha256"],
        "reason": reason,
    }
    return {
        **semantic,
        "refusal_sha256": hashlib.sha256(_canonical(semantic)).hexdigest(),
    }


@dataclasses.dataclass(frozen=True, slots=True)
class AcceptedRiskQcSymbolResolution:
    schema: str
    resolution_id: str
    resolution_sha256: str
    authority_mode: str
    formal_eligibility: str
    input_row_count: int
    resolved_count: int
    named_refusal_count: int
    resolved: tuple[dict[str, object], ...]
    named_refusals: tuple[dict[str, object], ...]
    point_in_time: bool
    independently_reviewed: bool
    formal_security_master_authority: bool
    preliminary_evaluation_eligible: bool
    every_input_has_one_terminal: bool
    _input_rows: tuple[dict[str, object], ...] = dataclasses.field(repr=False)
    _symbols: tuple[tuple[str, object], ...] = dataclasses.field(repr=False)
    _roundtrip_figis: tuple[tuple[str, str], ...] = dataclasses.field(repr=False)

    def to_record(self) -> dict[str, object]:
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
            "independently_reviewed": self.independently_reviewed,
            "formal_security_master_authority": self.formal_security_master_authority,
            "preliminary_evaluation_eligible": self.preliminary_evaluation_eligible,
            "every_input_has_one_terminal": self.every_input_has_one_terminal,
        }

    def symbol_for_security(self, security_id: str) -> object:
        require_accepted_risk_qc_symbol_resolution(self)
        _safe(security_id, "resolved logical security_id")
        match = next((symbol for logical, symbol in self._symbols if logical == security_id), None)
        if match is None:
            raise AcceptedRiskQcSymbolResolutionError(
                "logical security has no accepted runtime QC symbol"
            )
        return match

    def logical_security_for_qc_sid(self, qc_security_id: str) -> str:
        """Reverse-map one SID outside a bulk History loop.

        Bulk callers must use :func:`build_accepted_risk_qc_history_bindings`
        so authentication is paid once rather than once per bar.
        """

        require_accepted_risk_qc_symbol_resolution(self)
        if type(qc_security_id) is not str or _QC_SID.fullmatch(qc_security_id) is None:
            raise AcceptedRiskQcSymbolResolutionError(
                "History bar QC SecurityIdentifier is invalid"
            )
        match = next(
            (
                str(item["security_id"])
                for item in self.resolved
                if item["qc_security_id"] == qc_security_id
            ),
            None,
        )
        if match is None:
            raise AcceptedRiskQcSymbolResolutionError(
                "History bar returned an unbound runtime QC SecurityIdentifier"
            )
        return match


@dataclasses.dataclass(frozen=True, slots=True)
class AcceptedRiskQcHistoryBindings:
    """O(1) QC History maps bracketed by explicit reauthentication."""

    resolution_sha256: str
    _resolution: AcceptedRiskQcSymbolResolution = dataclasses.field(repr=False)
    _symbol_by_security: Mapping[str, object] = dataclasses.field(repr=False)
    _logical_by_qc_sid: Mapping[str, str] = dataclasses.field(repr=False)
    _input_by_security: Mapping[str, Mapping[str, object]] = dataclasses.field(
        repr=False
    )
    _refusal_by_security: Mapping[str, str] = dataclasses.field(repr=False)
    _fingerprint: tuple[tuple[str, str, str, int], ...] = (
        dataclasses.field(repr=False)
    )

    def symbol_for_history_request(
        self,
        *,
        security_id: str,
        decision_session: str,
        historical_ticker: str,
        issuer_id: str,
        share_class_id: str,
        listing_id: str,
        security_master_row_sha256: str,
        runtime_binding_row_sha256: str,
    ) -> object:
        """Preflight one logical/current-ticker request before QC History."""

        logical = _safe(security_id, "History request logical security_id")
        session = _session(decision_session, "History request decision session")
        ticker = historical_ticker
        if type(ticker) is not str or _TICKER.fullmatch(ticker) is None:
            raise AcceptedRiskQcSymbolResolutionError(
                "History request historical ticker is invalid"
            )
        requested_issuer = _safe(issuer_id, "History request issuer_id")
        requested_share_class = _safe(
            share_class_id, "History request share_class_id"
        )
        requested_listing = _safe(listing_id, "History request listing_id")
        requested_security_master_hash = _sha(
            security_master_row_sha256, "History request security master row"
        )
        requested_runtime_hash = _sha(
            runtime_binding_row_sha256, "History request runtime binding row"
        )
        row = self._input_by_security.get(logical)
        symbol = self._symbol_by_security.get(logical)
        if row is None or symbol is None:
            raise AcceptedRiskQcSymbolResolutionError(
                "History request has no resolved accepted-risk runtime binding"
            )
        if (
            ticker != row["current_snapshot_ticker"]
            or requested_issuer != row["issuer_id"]
            or requested_share_class != row["share_class_id"]
            or requested_listing != row["listing_id"]
            or requested_security_master_hash != row["source_row_sha256"]
            or requested_runtime_hash != row["row_sha256"]
        ):
            raise AcceptedRiskQcSymbolResolutionError(
                "History request ticker or external listing identity differs from admission"
            )
        if not row["candidate_first_session"] <= session <= row["candidate_last_session"]:
            raise AcceptedRiskQcSymbolResolutionError(
                "History request session is outside the admitted candidate interval"
            )
        return symbol

    def named_refusal_reason(self, security_id: str) -> str | None:
        """Return the exact resolver refusal for one logical input, if any."""

        logical = _safe(security_id, "History request logical security_id")
        return self._refusal_by_security.get(logical)

    def logical_security_for_history_bar(self, qc_security_id: str) -> str:
        """O(1) reverse lookup for a bar inside one bracketed History call."""

        if type(qc_security_id) is not str or _QC_SID.fullmatch(qc_security_id) is None:
            raise AcceptedRiskQcSymbolResolutionError(
                "History bar QC SecurityIdentifier is invalid"
            )
        logical = self._logical_by_qc_sid.get(qc_security_id)
        if logical is None:
            raise AcceptedRiskQcSymbolResolutionError(
                "History bar returned an unbound runtime QC SecurityIdentifier"
            )
        return logical


def build_accepted_risk_qc_history_bindings(
    value: AcceptedRiskQcSymbolResolution,
) -> AcceptedRiskQcHistoryBindings:
    """Authenticate once and construct immutable O(1) bulk-History maps."""

    resolution = require_accepted_risk_qc_symbol_resolution(value)
    symbols = {logical: symbol for logical, symbol in resolution._symbols}
    reverse = {
        str(record["qc_security_id"]): str(record["security_id"])
        for record in resolution.resolved
    }
    inputs = {
        str(row["security_id"]): MappingProxyType(dict(row))
        for row in resolution._input_rows
    }
    refusals = {
        str(record["security_id"]): str(record["reason"])
        for record in resolution.named_refusals
    }
    fingerprint = tuple(
        (
            logical,
            str(record["qc_security_id"]),
            hashlib.sha256(_canonical(dict(inputs[logical]))).hexdigest(),
            id(symbols[logical]),
        )
        for logical, record in (
            (str(item["security_id"]), item) for item in resolution.resolved
        )
    )
    return AcceptedRiskQcHistoryBindings(
        resolution_sha256=resolution.resolution_sha256,
        _resolution=resolution,
        _symbol_by_security=MappingProxyType(symbols),
        _logical_by_qc_sid=MappingProxyType(reverse),
        _input_by_security=MappingProxyType(inputs),
        _refusal_by_security=MappingProxyType(refusals),
        _fingerprint=fingerprint,
    )


def require_accepted_risk_qc_history_bindings(
    value: AcceptedRiskQcHistoryBindings,
) -> AcceptedRiskQcHistoryBindings:
    """Reauthenticate the maps after a bulk QC History traversal."""

    if type(value) is not AcceptedRiskQcHistoryBindings:
        raise AcceptedRiskQcSymbolResolutionError(
            "accepted-risk QC History binding type changed"
        )
    if (
        type(value.resolution_sha256) is not str
        or _HEX.fullmatch(value.resolution_sha256) is None
        or type(value._fingerprint) is not tuple
        or any(
            type(item) is not tuple
            or len(item) != 4
            or type(item[0]) is not str
            or _SAFE.fullmatch(item[0]) is None
            or type(item[1]) is not str
            or _QC_SID.fullmatch(item[1]) is None
            or type(item[2]) is not str
            or _HEX.fullmatch(item[2]) is None
            or type(item[3]) is not int
            or item[3] < 1
            for item in value._fingerprint
        )
    ):
        raise AcceptedRiskQcSymbolResolutionError(
            "accepted-risk QC History binding identity type changed"
        )
    resolution = require_accepted_risk_qc_symbol_resolution(value._resolution)
    if (
        type(value._symbol_by_security) is not _MAPPING_PROXY_TYPE
        or type(value._logical_by_qc_sid) is not _MAPPING_PROXY_TYPE
        or type(value._input_by_security) is not _MAPPING_PROXY_TYPE
        or type(value._refusal_by_security) is not _MAPPING_PROXY_TYPE
        or any(
            type(item) is not _MAPPING_PROXY_TYPE
            for item in value._input_by_security.values()
        )
    ):
        raise AcceptedRiskQcSymbolResolutionError(
            "accepted-risk QC History binding container topology changed"
        )
    try:
        symbol_items = tuple(value._symbol_by_security.items())
        reverse_items = tuple(value._logical_by_qc_sid.items())
        input_items = tuple(value._input_by_security.items())
        refusal_items = tuple(value._refusal_by_security.items())
    except Exception as exc:
        raise AcceptedRiskQcSymbolResolutionError(
            "accepted-risk QC History binding containers are unreadable"
        ) from exc
    if (
        any(type(key) is not str or _SAFE.fullmatch(key) is None for key, _ in symbol_items)
        or any(
            type(qc_sid) is not str
            or _QC_SID.fullmatch(qc_sid) is None
            or type(logical) is not str
            or _SAFE.fullmatch(logical) is None
            for qc_sid, logical in reverse_items
        )
        or any(
            type(key) is not str
            or _SAFE.fullmatch(key) is None
            or type(row) is not _MAPPING_PROXY_TYPE
            for key, row in input_items
        )
        or any(
            type(key) is not str
            or _SAFE.fullmatch(key) is None
            or type(reason) is not str
            or reason
            not in {
                "qc_runtime_symbol_resolution_unavailable",
                "qc_runtime_security_identifier_collision",
                "qc_runtime_composite_figi_resolution_unavailable",
                "qc_runtime_composite_figi_not_us_equity",
                "qc_runtime_composite_figi_roundtrip_mismatch",
            }
            for key, reason in refusal_items
        )
    ):
        raise AcceptedRiskQcSymbolResolutionError(
            "accepted-risk QC History binding scalar type changed"
        )
    expected_symbols = {
        logical: symbol for logical, symbol in resolution._symbols
    }
    expected_reverse = {
        str(record["qc_security_id"]): str(record["security_id"])
        for record in resolution.resolved
    }
    expected_inputs = {
        str(row["security_id"]): dict(row) for row in resolution._input_rows
    }
    expected_refusals = {
        str(record["security_id"]): str(record["reason"])
        for record in resolution.named_refusals
    }
    try:
        current_inputs = {
            key: _validated_input(dict(row))
            for key, row in value._input_by_security.items()
        }
    except (AcceptedRiskQcSymbolResolutionError, TypeError, ValueError) as exc:
        raise AcceptedRiskQcSymbolResolutionError(
            "accepted-risk QC History input binding changed during traversal"
        ) from exc
    current_fingerprint = tuple(
        (
            logical,
            qc_sid,
            hashlib.sha256(
                _canonical(dict(value._input_by_security[logical]))
            ).hexdigest(),
            id(value._symbol_by_security[logical]),
        )
        for qc_sid, logical in sorted(value._logical_by_qc_sid.items(), key=lambda item: item[1])
        if logical in value._symbol_by_security and logical in value._input_by_security
    )
    if (
        value.resolution_sha256 != resolution.resolution_sha256
        or set(value._symbol_by_security) != set(expected_symbols)
        or any(
            value._symbol_by_security[key] is not expected_symbols[key]
            for key in expected_symbols
        )
        or dict(value._logical_by_qc_sid) != expected_reverse
        or dict(value._refusal_by_security) != expected_refusals
        or set(value._input_by_security) != set(expected_inputs)
        or any(
            _canonical(current_inputs[key]) != _canonical(expected_inputs[key])
            for key in expected_inputs
        )
        or value._fingerprint != current_fingerprint
    ):
        raise AcceptedRiskQcSymbolResolutionError(
            "accepted-risk QC History bindings changed during traversal"
        )
    return value


def _result_seed(
    *,
    rows: tuple[dict[str, object], ...],
    resolved: tuple[dict[str, object], ...],
    refusals: tuple[dict[str, object], ...],
    authority_mode: str = AUTHORITY_MODE,
) -> dict[str, object]:
    return {
        "schema": RESULT_SCHEMA,
        "resolution_id": None,
        "resolution_sha256": None,
        "authority_mode": authority_mode,
        "formal_eligibility": FORMAL_ELIGIBILITY,
        "input_row_count": len(rows),
        "resolved_count": len(resolved),
        "named_refusal_count": len(refusals),
        "resolved": [dict(item) for item in resolved],
        "named_refusals": [dict(item) for item in refusals],
        "point_in_time": False,
        "independently_reviewed": False,
        "formal_security_master_authority": False,
        "preliminary_evaluation_eligible": True,
        "every_input_has_one_terminal": True,
    }


def _validated_inventory(
    rows: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    if type(rows) not in (tuple, list) or not rows:
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime ticker binding inventory is empty or not an exact sequence"
        )
    if any(type(item) is not dict for item in rows):
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime ticker binding inventory contains a non-mapping row"
        )
    normalized = tuple(_validated_input(dict(item)) for item in rows)
    if normalized != tuple(sorted(normalized, key=lambda item: item["security_id"])):
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime ticker binding inventory is not ordered by logical security"
        )
    logical_ids = [row["security_id"] for row in normalized]
    tickers = [row["current_snapshot_ticker"] for row in normalized]
    row_hashes = [row["row_sha256"] for row in normalized]
    admission_hashes = {row["security_master_admission_sha256"] for row in normalized}
    inventory_hashes = {row["admitted_mapping_inventory_sha256"] for row in normalized}
    inventory_counts = {row["admitted_mapping_count"] for row in normalized}
    if len(set(logical_ids)) != len(logical_ids):
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime ticker binding repeats a logical security"
        )
    if len(set(tickers)) != len(tickers):
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime ticker binding repeats a current snapshot ticker"
        )
    if len(set(row_hashes)) != len(row_hashes):
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime ticker binding repeats a content identity"
        )
    if (
        len(admission_hashes) != 1
        or len(inventory_hashes) != 1
        or inventory_counts != {len(normalized)}
    ):
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime ticker binding inventory is a subset or mixes admission authority"
        )
    return normalized


def _finalize_resolution(
    *,
    normalized: tuple[dict[str, object], ...],
    candidates: Sequence[tuple[dict[str, object], object, str, str, str]],
    refusals: Sequence[dict[str, object]],
    authority_mode: str,
) -> AcceptedRiskQcSymbolResolution:
    if authority_mode not in (AUTHORITY_MODE, COMPOSITE_FIGI_AUTHORITY_MODE):
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime QC symbol resolution authority mode changed"
        )
    mutable_refusals = list(refusals)
    sid_counts: dict[str, int] = {}
    for _row, _symbol, encoded_sid, _ticker, _method in candidates:
        sid_counts[encoded_sid] = sid_counts.get(encoded_sid, 0) + 1
    accepted_records: list[dict[str, object]] = []
    accepted_symbols: list[tuple[str, object]] = []
    roundtrip_figis: list[tuple[str, str]] = []
    for row, symbol, encoded_sid, observed_ticker, method in candidates:
        if sid_counts[encoded_sid] != 1:
            mutable_refusals.append(
                _refusal(row, "qc_runtime_security_identifier_collision")
            )
            continue
        semantic = {
            "security_id": row["security_id"],
            "source_binding_sha256": row["row_sha256"],
            "qc_security_id": encoded_sid,
            "current_snapshot_ticker": observed_ticker,
            "security_type": "Equity",
            "market": "usa",
            "external_composite_figi": row["share_class_id"],
            "resolution_method": method,
        }
        accepted_records.append(
            {
                **semantic,
                "resolution_sha256": hashlib.sha256(_canonical(semantic)).hexdigest(),
            }
        )
        logical = str(row["security_id"])
        accepted_symbols.append((logical, symbol))
        roundtrip_figis.append((logical, str(row["share_class_id"])))
    accepted_records.sort(key=lambda item: item["security_id"])
    accepted_symbols.sort(key=lambda item: item[0])
    roundtrip_figis.sort(key=lambda item: item[0])
    mutable_refusals.sort(key=lambda item: item["security_id"])
    terminals = len(accepted_records) + len(mutable_refusals)
    if terminals != len(normalized):
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime ticker resolution omitted an admitted input terminal"
        )
    resolved_tuple = tuple(accepted_records)
    refusal_tuple = tuple(mutable_refusals)
    seed = _result_seed(
        rows=normalized,
        resolved=resolved_tuple,
        refusals=refusal_tuple,
        authority_mode=authority_mode,
    )
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    seed["resolution_id"] = "arv2-owner-accepted-qc-symbols-" + digest[:24]
    seed["resolution_sha256"] = digest
    result = AcceptedRiskQcSymbolResolution(
        schema=RESULT_SCHEMA,
        resolution_id=str(seed["resolution_id"]),
        resolution_sha256=digest,
        authority_mode=authority_mode,
        formal_eligibility=FORMAL_ELIGIBILITY,
        input_row_count=len(normalized),
        resolved_count=len(resolved_tuple),
        named_refusal_count=len(refusal_tuple),
        resolved=resolved_tuple,
        named_refusals=refusal_tuple,
        point_in_time=False,
        independently_reviewed=False,
        formal_security_master_authority=False,
        preliminary_evaluation_eligible=True,
        every_input_has_one_terminal=True,
        _input_rows=normalized,
        _symbols=tuple(accepted_symbols),
        _roundtrip_figis=tuple(roundtrip_figis),
    )
    return require_accepted_risk_qc_symbol_resolution(result)


def resolve_owner_accepted_qc_symbols(
    rows: Sequence[Mapping[str, object]],
    *,
    symbol_factory: Callable[[str], object | None],
) -> AcceptedRiskQcSymbolResolution:
    """Resolve each admitted ticker once and refuse the full collision group."""

    if not callable(symbol_factory):
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime QC symbol factory is not callable"
        )
    normalized = _validated_inventory(rows)

    candidates: list[tuple[dict[str, object], object, str, str, str]] = []
    refusals: list[dict[str, object]] = []
    for row in normalized:
        try:
            symbol = symbol_factory(str(row["current_snapshot_ticker"]))
        except Exception as exc:
            raise AcceptedRiskQcSymbolResolutionError(
                "runtime QC symbol factory raised before a named resolution terminal"
            ) from exc
        if symbol is None:
            refusals.append(_refusal(row, "qc_runtime_symbol_resolution_unavailable"))
            continue
        try:
            symbol_id = symbol.id
            symbol_value = symbol.value
            security_type = str(symbol.security_type)
            market = str(symbol_id.market)
            encoded_sid = str(symbol_id)
        except Exception as exc:
            raise AcceptedRiskQcSymbolResolutionError(
                "runtime QC symbol lacks readable ticker/type/market identity"
            ) from exc
        if symbol_id is None or _QC_SID.fullmatch(encoded_sid) is None:
            raise AcceptedRiskQcSymbolResolutionError(
                "runtime QC symbol returned an invalid SecurityIdentifier"
            )
        if (
            type(symbol_value) is not str
            or symbol_value != row["current_snapshot_ticker"]
            or security_type.lower() not in {"equity", "securitytype.equity"}
            or market.lower() != "usa"
        ):
            raise AcceptedRiskQcSymbolResolutionError(
                "runtime QC symbol differs from the requested US equity ticker"
            )
        candidates.append(
            (
                row,
                symbol,
                encoded_sid,
                symbol_value,
                "current_snapshot_ticker",
            )
        )
    return _finalize_resolution(
        normalized=normalized,
        candidates=candidates,
        refusals=refusals,
        authority_mode=AUTHORITY_MODE,
    )


def resolve_owner_accepted_qc_symbols_by_composite_figi(
    rows: Sequence[Mapping[str, object]],
    *,
    composite_figi_resolver: Callable[[str], object | None],
    composite_figi_roundtrip: Callable[[object], object],
) -> AcceptedRiskQcSymbolResolution:
    """Resolve permanent FIGIs inside QC and require the exact reverse map.

    The admitted current ticker is display evidence only on this path.  A
    different QC ``Symbol.Value`` is not a refusal because map-file ticker
    history can legitimately differ.  Permanent identity is established only
    by the exact composite-FIGI round trip.
    """

    if not callable(composite_figi_resolver) or not callable(
        composite_figi_roundtrip
    ):
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime QC composite-FIGI resolver is not callable"
        )
    normalized = _validated_inventory(rows)
    candidates: list[tuple[dict[str, object], object, str, str, str]] = []
    refusals: list[dict[str, object]] = []
    for row in normalized:
        raw_figi = row["share_class_id"]
        if type(raw_figi) is not str or _FIGI.fullmatch(raw_figi) is None:
            raise AcceptedRiskQcSymbolResolutionError(
                "runtime QC composite-FIGI input identity is malformed"
            )
        figi = raw_figi
        try:
            symbol = composite_figi_resolver(figi)
        except Exception as exc:
            raise AcceptedRiskQcSymbolResolutionError(
                "runtime QC composite-FIGI resolver raised before a terminal"
            ) from exc
        if symbol is None:
            refusals.append(
                _refusal(row, "qc_runtime_composite_figi_resolution_unavailable")
            )
            continue
        try:
            symbol_id = symbol.id
            observed_ticker = symbol.value
            security_type = str(symbol.security_type)
            market = str(symbol_id.market)
            encoded_sid = str(symbol_id)
        except Exception as exc:
            raise AcceptedRiskQcSymbolResolutionError(
                "runtime QC composite-FIGI symbol identity is unreadable"
            ) from exc
        if symbol_id is None or _QC_SID.fullmatch(encoded_sid) is None:
            raise AcceptedRiskQcSymbolResolutionError(
                "runtime QC composite-FIGI returned an invalid SecurityIdentifier"
            )
        if type(observed_ticker) is not str or _TICKER.fullmatch(observed_ticker) is None:
            raise AcceptedRiskQcSymbolResolutionError(
                "runtime QC composite-FIGI symbol ticker is unreadable"
            )
        if (
            security_type.lower() not in {"equity", "securitytype.equity"}
            or market.lower() != "usa"
        ):
            refusals.append(
                _refusal(row, "qc_runtime_composite_figi_not_us_equity")
            )
            continue
        try:
            reversed_figi = composite_figi_roundtrip(symbol)
        except Exception as exc:
            raise AcceptedRiskQcSymbolResolutionError(
                "runtime QC composite-FIGI reverse resolver raised before a terminal"
            ) from exc
        if type(reversed_figi) is not str or _FIGI.fullmatch(reversed_figi) is None:
            raise AcceptedRiskQcSymbolResolutionError(
                "runtime QC composite-FIGI reverse resolver returned malformed identity"
            )
        if reversed_figi != figi:
            refusals.append(
                _refusal(row, "qc_runtime_composite_figi_roundtrip_mismatch")
            )
            continue
        candidates.append(
            (
                row,
                symbol,
                encoded_sid,
                observed_ticker,
                "composite_figi_exact_roundtrip",
            )
        )
    return _finalize_resolution(
        normalized=normalized,
        candidates=candidates,
        refusals=refusals,
        authority_mode=COMPOSITE_FIGI_AUTHORITY_MODE,
    )


def resolve_admitted_security_master_qc_symbols(
    rows: Sequence[Mapping[str, object]],
    *,
    security_master_admission_sha256: str,
    admitted_mapping_inventory_sha256: str,
    symbol_factory: Callable[[str], object | None],
) -> AcceptedRiskQcSymbolResolution:
    """Authenticate the complete admission inventory and resolve it atomically.

    This is the production entry point.  Keeping projection and resolution in
    one call prevents an accidentally sliced projected tuple from becoming a
    selective runtime universe.
    """

    bindings = project_admitted_security_master_mappings(
        rows,
        security_master_admission_sha256=security_master_admission_sha256,
        admitted_mapping_inventory_sha256=admitted_mapping_inventory_sha256,
    )
    return resolve_owner_accepted_qc_symbols(
        bindings, symbol_factory=symbol_factory
    )


def resolve_admitted_security_master_qc_symbols_by_composite_figi(
    rows: Sequence[Mapping[str, object]],
    *,
    security_master_admission_sha256: str,
    admitted_mapping_inventory_sha256: str,
    composite_figi_resolver: Callable[[str], object | None],
    composite_figi_roundtrip: Callable[[object], object],
) -> AcceptedRiskQcSymbolResolution:
    """Authenticate the full admission then resolve every permanent FIGI."""

    bindings = project_admitted_security_master_mappings(
        rows,
        security_master_admission_sha256=security_master_admission_sha256,
        admitted_mapping_inventory_sha256=admitted_mapping_inventory_sha256,
    )
    return resolve_owner_accepted_qc_symbols_by_composite_figi(
        bindings,
        composite_figi_resolver=composite_figi_resolver,
        composite_figi_roundtrip=composite_figi_roundtrip,
    )


def require_accepted_risk_qc_symbol_resolution(
    value: AcceptedRiskQcSymbolResolution,
) -> AcceptedRiskQcSymbolResolution:
    if type(value) is not AcceptedRiskQcSymbolResolution:
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime QC symbol resolution type changed"
        )
    for field in (
        "schema",
        "resolution_id",
        "resolution_sha256",
        "authority_mode",
        "formal_eligibility",
    ):
        if type(getattr(value, field)) is not str:
            raise AcceptedRiskQcSymbolResolutionError(
                "runtime QC symbol resolution scalar type changed"
            )
    if value.authority_mode not in (AUTHORITY_MODE, COMPOSITE_FIGI_AUTHORITY_MODE):
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime QC symbol resolution authority mode changed"
        )
    for field in ("input_row_count", "resolved_count", "named_refusal_count"):
        observed = getattr(value, field)
        if type(observed) is not int or observed < 0:
            raise AcceptedRiskQcSymbolResolutionError(
                "runtime QC symbol resolution count type changed"
            )
    for field in (
        "point_in_time",
        "independently_reviewed",
        "formal_security_master_authority",
        "preliminary_evaluation_eligible",
        "every_input_has_one_terminal",
    ):
        if type(getattr(value, field)) is not bool:
            raise AcceptedRiskQcSymbolResolutionError(
                "runtime QC symbol resolution gate type changed"
            )
    if (
        type(value.resolved) is not tuple
        or type(value.named_refusals) is not tuple
        or type(value._input_rows) is not tuple
    ):
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime QC symbol resolution terminal container changed"
        )
    if any(type(item) is not dict for item in value._input_rows):
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime QC symbol resolution private input row changed"
        )
    rows = tuple(_validated_input(dict(item)) for item in value._input_rows)
    if type(value._symbols) is not tuple or any(
        type(item) is not tuple or len(item) != 2 for item in value._symbols
    ):
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime QC symbol resolution private symbol inventory changed"
        )
    if type(value._roundtrip_figis) is not tuple or any(
        type(item) is not tuple
        or len(item) != 2
        or type(item[0]) is not str
        or _SAFE.fullmatch(item[0]) is None
        or type(item[1]) is not str
        or (
            _FIGI.fullmatch(item[1]) is None
            if value.authority_mode == COMPOSITE_FIGI_AUTHORITY_MODE
            else _SAFE.fullmatch(item[1]) is None
        )
        for item in value._roundtrip_figis
    ):
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime QC symbol resolution composite-FIGI inventory changed"
        )
    if any(type(item) is not dict for item in value.resolved):
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime QC resolved symbol row changed"
        )
    if any(type(item) is not dict for item in value.named_refusals):
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime QC named symbol refusal row changed"
        )
    resolved = tuple(dict(item) for item in value.resolved)
    refusals = tuple(dict(item) for item in value.named_refusals)
    for record in resolved:
        if (
            set(record) != _RESOLVED_FIELDS
            or type(record["security_id"]) is not str
            or _SAFE.fullmatch(record["security_id"]) is None
            or type(record["source_binding_sha256"]) is not str
            or _HEX.fullmatch(record["source_binding_sha256"]) is None
            or type(record["qc_security_id"]) is not str
            or _QC_SID.fullmatch(record["qc_security_id"]) is None
            or type(record["current_snapshot_ticker"]) is not str
            or _TICKER.fullmatch(record["current_snapshot_ticker"]) is None
            or type(record["security_type"]) is not str
            or record["security_type"] != "Equity"
            or type(record["market"]) is not str
            or record["market"] != "usa"
            or type(record["external_composite_figi"]) is not str
            or (
                _FIGI.fullmatch(record["external_composite_figi"]) is None
                if value.authority_mode == COMPOSITE_FIGI_AUTHORITY_MODE
                else _SAFE.fullmatch(record["external_composite_figi"]) is None
            )
            or type(record["resolution_method"]) is not str
            or record["resolution_method"]
            not in {"current_snapshot_ticker", "composite_figi_exact_roundtrip"}
            or type(record["resolution_sha256"]) is not str
            or _HEX.fullmatch(record["resolution_sha256"]) is None
        ):
            raise AcceptedRiskQcSymbolResolutionError(
                "runtime QC resolved symbol record schema changed"
            )
        expected_method = (
            "composite_figi_exact_roundtrip"
            if value.authority_mode == COMPOSITE_FIGI_AUTHORITY_MODE
            else "current_snapshot_ticker"
        )
        if record["resolution_method"] != expected_method:
            raise AcceptedRiskQcSymbolResolutionError(
                "runtime QC resolved symbol method differs from authority mode"
            )
    for refusal in refusals:
        if (
            set(refusal) != _REFUSAL_FIELDS
            or refusal["schema"] != REFUSAL_SCHEMA
            or type(refusal["security_id"]) is not str
            or _SAFE.fullmatch(refusal["security_id"]) is None
            or type(refusal["source_binding_sha256"]) is not str
            or _HEX.fullmatch(refusal["source_binding_sha256"]) is None
            or type(refusal["reason"]) is not str
            or refusal["reason"]
            not in {
                "qc_runtime_symbol_resolution_unavailable",
                "qc_runtime_security_identifier_collision",
                "qc_runtime_composite_figi_resolution_unavailable",
                "qc_runtime_composite_figi_not_us_equity",
                "qc_runtime_composite_figi_roundtrip_mismatch",
            }
            or type(refusal["refusal_sha256"]) is not str
            or _HEX.fullmatch(refusal["refusal_sha256"]) is None
        ):
            raise AcceptedRiskQcSymbolResolutionError(
                "runtime QC named symbol refusal changed"
            )
    if (
        tuple(item["security_id"] for item in resolved)
        != tuple(item[0] for item in value._symbols)
        or tuple(
            (item["security_id"], item["external_composite_figi"])
            for item in resolved
        )
        != value._roundtrip_figis
        or len({item["security_id"] for item in resolved}) != len(resolved)
        or len({item["qc_security_id"] for item in resolved}) != len(resolved)
        or len({item["security_id"] for item in refusals}) != len(refusals)
        or {item["security_id"] for item in resolved}
        & {item["security_id"] for item in refusals}
    ):
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime QC symbol resolution terminal inventory changed"
        )
    if value.authority_mode == COMPOSITE_FIGI_AUTHORITY_MODE and not resolved:
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime QC composite-FIGI resolution produced zero usable securities"
        )
    input_hashes = {
        str(item["security_id"]): str(item["row_sha256"]) for item in rows
    }
    terminal_hashes = {
        str(item["security_id"]): str(item["source_binding_sha256"])
        for item in (*resolved, *refusals)
    }
    if terminal_hashes != input_hashes:
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime QC symbol terminals do not bind every admitted input"
        )
    for record, (_logical, symbol) in zip(resolved, value._symbols, strict=True):
        try:
            observed_id = symbol.id
            observed_sid = str(observed_id)
            observed_ticker = symbol.value
            observed_type = str(symbol.security_type)
            observed_market = str(observed_id.market)
        except Exception as exc:
            raise AcceptedRiskQcSymbolResolutionError(
                "runtime QC symbol changed after resolution"
            ) from exc
        if (
            observed_id is None
            or observed_sid != record.get("qc_security_id")
            or type(observed_ticker) is not str
            or _TICKER.fullmatch(observed_ticker) is None
            or observed_ticker != record.get("current_snapshot_ticker")
            or observed_type.lower() not in {"equity", "securitytype.equity"}
            or observed_market.lower() != record.get("market")
        ):
            raise AcceptedRiskQcSymbolResolutionError(
                "runtime QC SecurityIdentifier changed after resolution"
            )
        semantic = {
            "security_id": record.get("security_id"),
            "source_binding_sha256": record.get("source_binding_sha256"),
            "qc_security_id": record.get("qc_security_id"),
            "current_snapshot_ticker": record.get("current_snapshot_ticker"),
            "security_type": record.get("security_type"),
            "market": record.get("market"),
            "external_composite_figi": record.get("external_composite_figi"),
            "resolution_method": record.get("resolution_method"),
        }
        if (
            record.get("resolution_sha256")
            != hashlib.sha256(_canonical(semantic)).hexdigest()
        ):
            raise AcceptedRiskQcSymbolResolutionError(
                "runtime QC resolved symbol record changed"
            )
    for refusal in refusals:
        semantic = {
            "schema": refusal.get("schema"),
            "security_id": refusal.get("security_id"),
            "source_binding_sha256": refusal.get("source_binding_sha256"),
            "reason": refusal.get("reason"),
        }
        if (
            refusal.get("refusal_sha256")
            != hashlib.sha256(_canonical(semantic)).hexdigest()
        ):
            raise AcceptedRiskQcSymbolResolutionError(
                "runtime QC named symbol refusal changed"
            )
    seed = _result_seed(
        rows=rows,
        resolved=resolved,
        refusals=refusals,
        authority_mode=value.authority_mode,
    )
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    expected = {
        **seed,
        "resolution_id": "arv2-owner-accepted-qc-symbols-" + digest[:24],
        "resolution_sha256": digest,
    }
    if value.to_record() != expected:
        raise AcceptedRiskQcSymbolResolutionError(
            "runtime QC symbol resolution public record changed"
        )
    return value


__all__ = (
    "ACCEPTED_RISK_QC_SYMBOL_RESOLUTION",
    "ADMISSION_MAPPING_SCHEMA",
    "ALLOWED_EXCHANGE_MICS",
    "AUTHORITY_MODE",
    "COMPOSITE_FIGI_AUTHORITY_MODE",
    "AcceptedRiskQcHistoryBindings",
    "AcceptedRiskQcSymbolResolution",
    "AcceptedRiskQcSymbolResolutionError",
    "FORMAL_ELIGIBILITY",
    "INPUT_SCHEMA",
    "MAPPING_STATUS",
    "REFUSAL_SCHEMA",
    "RESULT_SCHEMA",
    "build_accepted_risk_qc_history_bindings",
    "build_runtime_ticker_binding",
    "project_admitted_security_master_mappings",
    "require_accepted_risk_qc_history_bindings",
    "require_accepted_risk_qc_symbol_resolution",
    "resolve_admitted_security_master_qc_symbols",
    "resolve_admitted_security_master_qc_symbols_by_composite_figi",
    "resolve_owner_accepted_qc_symbols",
    "resolve_owner_accepted_qc_symbols_by_composite_figi",
)

# Stable source marker for projection inventories.  It deliberately has no
# truth value beyond identifying this exact accepted-risk runtime contract.
ACCEPTED_RISK_QC_SYMBOL_RESOLUTION = RESULT_SCHEMA
