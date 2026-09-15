"""Owner-accepted current-snapshot Sharadar identity admission.

QuantConnect's historical security-master discovery remains the preferred
point-in-time identity source.  This additive boundary exists for the owner's
explicitly accepted practical-backtest fallback: it can admit only a
one-to-one mapping already derived from the authenticated physical pre-open
seed.  It never upgrades Sharadar's capture-time TICKERS snapshot into a
historical security master and never claims that a QuantConnect SecurityIdentifier
is available.

The boundary is deliberately separate from the firm-ontology owner decision.
Firm rating semantics and security identity have different evidence and
different refusal rules; neither authority can open or weaken the other.
"""
from __future__ import annotations

import dataclasses
import os
import re
import threading
import weakref
from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any, Iterable, Iterator, Mapping, NoReturn

from research.analyst_revisions_v2 import canonical as _canonical
from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    decode_utf8,
    require_identifier,
    require_sha256,
    sha256_bytes,
    strict_json_loads,
)
from research.analyst_revisions_v2_qc import physical_preopen_seed_archive as _seed
from research.analyst_revisions_v2_qc.physical_preopen_seed_archive import (
    PhysicalPreopenSeedArchive,
)


ADMISSION_SCHEMA = "arv2-owner-accepted-risk-sharadar-security-admission-v1"
MAPPING_SCHEMA = "arv2-owner-accepted-risk-sharadar-security-mapping-v1"
REFUSAL_SCHEMA = "arv2-owner-accepted-risk-sharadar-security-refusal-v1"
MAPPING_STATUS = (
    "owner_accepted_unique_current_snapshot_ticker_requires_qc_runtime_resolution"
)
OWNER_RISK_DECISION = (
    "admit_only_unique_Sharadar_TICKERS_current_snapshot_identity_for_the_"
    "practical_backtest_without_claiming_historical_security_master_semantics"
)
MAX_SOURCE_ROWS = 100_000
MAX_DOCUMENT_BYTES = 256 * 1024 * 1024

_TICKER = re.compile(r"[A-Z0-9][A-Z0-9.\-]{0,31}\Z")
_FIGI = re.compile(r"[A-Z0-9]{12}\Z")
_CUSIP = re.compile(r"[0-9A-Z]{9}\Z")
_INSTANT = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{6})?(?:Z|[+-]\d{2}:\d{2})\Z"
)
_EXCHANGES = frozenset({"XASE", "XNAS", "XNYS"})

_SOURCE_KEYS = frozenset(
    {
        "security_id",
        "issuer_id",
        "source_composite_figi",
        "listing_id",
        "sharadar_cusip_join_candidates",
        "current_snapshot_ticker_display",
        "current_snapshot_listing_exchange",
        "current_snapshot_sector_id",
        "current_snapshot_industry_id",
        "candidate_first_session",
        "candidate_last_session",
        "source_row_sha256",
        "identity_evidence_sha256",
        "classification_evidence_sha256",
        "source_snapshot_available_at",
        "qc_security_id",
        "mapping_status",
        "membership_status",
        "point_in_time",
    }
)
_SOURCE_BINDING_KEYS = frozenset(
    {
        "seed_archive_id",
        "seed_archive_sha256",
        "eligible_universe_artifact_sha256",
        "sharadar_capture_id",
        "sharadar_capture_sha256",
        "source_snapshot_available_at",
        "source_candidate_count",
    }
)
_MAPPING_KEYS = frozenset(
    {
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
)
_REFUSAL_KEYS = frozenset(
    {
        "schema",
        "refusal_id",
        "refusal_sha256",
        "source_ordinal",
        "source_row_sha256",
        "observed_security_id",
        "observed_composite_figi",
        "observed_listing_id",
        "observed_ticker",
        "reason_codes",
        "mapping_admitted",
        "qc_sid_available",
        "point_in_time",
        "independently_reviewed",
        "historical_availability_claimed",
    }
)
_CAPABILITY_NAMES = (
    "production_authority",
    "provider_access",
    "credential_access",
    "quantconnect_access",
    "outcome_access",
    "result_access",
    "deployment",
    "orders",
    "trading",
)

_PINNED_SEED_TYPE = PhysicalPreopenSeedArchive
_PINNED_REQUIRE_SEED = _seed.require_physical_preopen_seed_archive
_PINNED_ITER_UNIVERSE = _seed.iter_physical_universe_candidates
_PINNED_CANONICAL = canonical_json_bytes
_PINNED_SHA256 = sha256_bytes
_PINNED_DECODE = decode_utf8
_PINNED_LOADS = strict_json_loads
_PINNED_REQUIRE_IDENTIFIER = require_identifier
_PINNED_REQUIRE_SHA256 = require_sha256


class AcceptedRiskSecurityMasterAdmissionError(ValueError):
    """The current-snapshot security admission is not authoritative."""


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class AcceptedRiskSecurityMasterAdmission:
    """Process-local authority over the exact accepted-risk admission bytes."""

    schema: str
    admission_id: str
    admission_sha256: str
    payload_sha256: str
    document_bytes: bytes = dataclasses.field(repr=False)
    seed_archive_id: str
    seed_archive_sha256: str
    eligible_universe_artifact_sha256: str
    sharadar_capture_id: str
    sharadar_capture_sha256: str
    source_snapshot_available_at: str
    source_candidate_count: int
    admitted_mapping_count: int
    named_refusal_count: int
    refusal_reason_counts: tuple[tuple[str, int], ...]
    qc_sid_available: bool
    point_in_time: bool
    independently_reviewed: bool
    historical_availability_claimed: bool
    current_snapshot_identity_basis: bool
    owner_accepted_current_snapshot_risk: bool
    production_authority: bool
    provider_access: bool
    credential_access: bool
    quantconnect_access: bool
    outcome_access: bool
    result_access: bool
    deployment: bool
    orders: bool
    trading: bool


_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[AcceptedRiskSecurityMasterAdmission],
        tuple[object, ...],
        weakref.ReferenceType[PhysicalPreopenSeedArchive],
        int,
    ],
] = {}
_AUTHORITY_LOCK = threading.RLock()
_AUTHORITY_PID = os.getpid()


def _reset_authorities_after_fork() -> None:
    global _AUTHORITIES, _AUTHORITY_LOCK, _AUTHORITY_PID
    _AUTHORITIES = {}
    _AUTHORITY_LOCK = threading.RLock()
    _AUTHORITY_PID = os.getpid()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_authorities_after_fork)


def _forget(identity: int, reference: object) -> None:
    with _AUTHORITY_LOCK:
        current = _AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _AUTHORITIES.pop(identity, None)


def _fingerprint(value: AcceptedRiskSecurityMasterAdmission) -> tuple[object, ...]:
    return tuple(getattr(value, field.name) for field in dataclasses.fields(value))


def _refuse(message: str) -> NoReturn:
    raise AcceptedRiskSecurityMasterAdmissionError(message)


def _require_dependencies() -> None:
    if (
        _seed.PhysicalPreopenSeedArchive is not _PINNED_SEED_TYPE
        or _seed.require_physical_preopen_seed_archive is not _PINNED_REQUIRE_SEED
        or _seed.iter_physical_universe_candidates is not _PINNED_ITER_UNIVERSE
        or _canonical.canonical_json_bytes is not _PINNED_CANONICAL
        or _canonical.sha256_bytes is not _PINNED_SHA256
        or _canonical.decode_utf8 is not _PINNED_DECODE
        or _canonical.strict_json_loads is not _PINNED_LOADS
        or _canonical.require_identifier is not _PINNED_REQUIRE_IDENTIFIER
        or _canonical.require_sha256 is not _PINNED_REQUIRE_SHA256
        or canonical_json_bytes is not _PINNED_CANONICAL
        or sha256_bytes is not _PINNED_SHA256
        or decode_utf8 is not _PINNED_DECODE
        or strict_json_loads is not _PINNED_LOADS
        or require_identifier is not _PINNED_REQUIRE_IDENTIFIER
        or require_sha256 is not _PINNED_REQUIRE_SHA256
    ):
        _refuse("accepted-risk security-master dependency binding changed")


def _canonical_copy(value: object, name: str) -> Any:
    try:
        payload = _PINNED_CANONICAL(value)
        return _PINNED_LOADS(_PINNED_DECODE(payload, name), name)
    except (CanonicalEvidenceError, TypeError, ValueError, RecursionError) as exc:
        raise AcceptedRiskSecurityMasterAdmissionError(
            f"{name} is not bounded canonical JSON"
        ) from exc


def _address_record(
    record: dict[str, object], *, identifier: str, digest: str, prefix: str
) -> None:
    seed = {key: value for key, value in record.items() if key not in {identifier, digest}}
    value = _PINNED_SHA256(_PINNED_CANONICAL(seed))
    record[identifier] = f"{prefix}{value[:24]}"
    record[digest] = value


def _address_is_current(
    record: Mapping[str, object], *, identifier: str, digest: str, prefix: str
) -> bool:
    try:
        seed = {
            key: value
            for key, value in record.items()
            if key not in {identifier, digest}
        }
        value = _PINNED_SHA256(_PINNED_CANONICAL(seed))
    except (CanonicalEvidenceError, TypeError, ValueError, RecursionError):
        return False
    return record.get(identifier) == f"{prefix}{value[:24]}" and record.get(digest) == value


def _source_binding(
    archive: PhysicalPreopenSeedArchive,
    rows: tuple[dict[str, object], ...],
) -> dict[str, object]:
    bindings = tuple(
        item
        for item in archive.artifacts
        if item.role == "eligible_universe_artifact"
    )
    if len(bindings) != 1:
        _refuse("accepted-risk security-master universe artifact binding is missing")
    binding = bindings[0]
    snapshots = {
        value
        for row in rows
        if type(row) is dict
        for value in (row.get("source_snapshot_available_at"),)
        if type(value) is str
    }
    if not snapshots:
        _refuse("accepted-risk security-master source snapshot binding is missing")
    if len(snapshots) != 1:
        _refuse("accepted-risk security-master source snapshot binding is ambiguous")
    return {
        "seed_archive_id": archive.archive_id,
        "seed_archive_sha256": archive.archive_sha256,
        "eligible_universe_artifact_sha256": binding.content_sha256,
        "sharadar_capture_id": archive.sharadar_capture_id,
        "sharadar_capture_sha256": archive.sharadar_capture_sha256,
        "source_snapshot_available_at": next(iter(snapshots)),
        "source_candidate_count": archive.candidate_security_count,
    }


def _exact_date(value: object) -> str | None:
    if type(value) is not str:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return value if parsed.isoformat() == value else None


def _exact_instant(value: object) -> str | None:
    if type(value) is not str or _INSTANT.fullmatch(value) is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return value


def _id(value: object) -> str | None:
    if type(value) is not str:
        return None
    try:
        return _PINNED_REQUIRE_IDENTIFIER(value, "security-master identity")
    except CanonicalEvidenceError:
        return None


def _sha(value: object) -> str | None:
    if type(value) is not str:
        return None
    try:
        return _PINNED_REQUIRE_SHA256(value, "security-master evidence")
    except CanonicalEvidenceError:
        return None


def _observed(value: object) -> str | None:
    return value if type(value) is str and 0 < len(value) <= 256 else None


def _structural_reasons(row: dict[str, object]) -> set[str]:
    reasons: set[str] = set()
    missing = _SOURCE_KEYS - set(row)
    unexpected = set(row) - _SOURCE_KEYS
    for field in sorted(missing):
        reasons.add(f"missing_{field}")
    if unexpected:
        reasons.add("unexpected_source_candidate_fields")
    if missing:
        return reasons

    if _id(row["security_id"]) is None:
        reasons.add("invalid_security_id")
    if _id(row["issuer_id"]) is None:
        reasons.add("invalid_issuer_id")
    figi = row["source_composite_figi"]
    if type(figi) is not str or _FIGI.fullmatch(figi) is None:
        reasons.add("invalid_composite_figi")
    if _id(row["listing_id"]) is None:
        reasons.add("invalid_listing_id")
    ticker = row["current_snapshot_ticker_display"]
    if type(ticker) is not str or _TICKER.fullmatch(ticker) is None:
        reasons.add("invalid_current_snapshot_ticker")
    if row["current_snapshot_listing_exchange"] not in _EXCHANGES:
        reasons.add("invalid_current_snapshot_exchange")
    if _id(row["current_snapshot_sector_id"]) is None:
        reasons.add("invalid_current_snapshot_sector_id")
    if _id(row["current_snapshot_industry_id"]) is None:
        reasons.add("invalid_current_snapshot_industry_id")
    first = _exact_date(row["candidate_first_session"])
    last = _exact_date(row["candidate_last_session"])
    if first is None:
        reasons.add("invalid_candidate_first_session")
    if last is None:
        reasons.add("invalid_candidate_last_session")
    if first is not None and last is not None and first > last:
        reasons.add("reversed_candidate_session_interval")
    if _sha(row["source_row_sha256"]) is None:
        reasons.add("invalid_source_row_sha256")
    if _sha(row["identity_evidence_sha256"]) is None:
        reasons.add("invalid_identity_evidence_sha256")
    if _sha(row["classification_evidence_sha256"]) is None:
        reasons.add("invalid_classification_evidence_sha256")
    if _exact_instant(row["source_snapshot_available_at"]) is None:
        reasons.add("invalid_source_snapshot_available_at")
    cusips = row["sharadar_cusip_join_candidates"]
    if (
        type(cusips) is not list
        or any(type(item) is not str or _CUSIP.fullmatch(item) is None for item in cusips)
        or cusips != sorted(set(cusips))
    ):
        reasons.add("invalid_or_duplicate_cusip_join_candidates")
    if row["qc_security_id"] is not None:
        reasons.add("unexpected_qc_security_id_claim")
    if row["mapping_status"] != "requires_outcome_free_qc_discovery":
        reasons.add("source_mapping_status_changed")
    if row["membership_status"] != "review_required_current_snapshot_not_PIT":
        reasons.add("source_membership_risk_disclosure_changed")
    if row["point_in_time"] is not False:
        reasons.add("unexpected_point_in_time_claim")
    return reasons


def _mapping(row: dict[str, object], ordinal: int) -> dict[str, object]:
    return {
        "schema": MAPPING_SCHEMA,
        "source_ordinal": ordinal,
        "source_row_sha256": row["source_row_sha256"],
        "security_id": row["security_id"],
        "issuer_id": row["issuer_id"],
        "composite_figi": row["source_composite_figi"],
        "listing_id": row["listing_id"],
        "ticker": row["current_snapshot_ticker_display"],
        "exchange_id": row["current_snapshot_listing_exchange"],
        "cusip_join_candidates": row["sharadar_cusip_join_candidates"],
        "sector_id": row["current_snapshot_sector_id"],
        "industry_id": row["current_snapshot_industry_id"],
        "candidate_first_session": row["candidate_first_session"],
        "candidate_last_session": row["candidate_last_session"],
        "identity_evidence_sha256": row["identity_evidence_sha256"],
        "classification_evidence_sha256": row["classification_evidence_sha256"],
        "source_snapshot_available_at": row["source_snapshot_available_at"],
        "qc_security_id": None,
        "mapping_status": MAPPING_STATUS,
        "qc_sid_available": False,
        "point_in_time": False,
        "independently_reviewed": False,
        "historical_availability_claimed": False,
        "current_snapshot_identity_basis": True,
        "owner_accepted_current_snapshot_risk": True,
    }


def _refusal(
    row: dict[str, object], ordinal: int, row_sha256: str, reasons: Iterable[str]
) -> dict[str, object]:
    record: dict[str, object] = {
        "schema": REFUSAL_SCHEMA,
        "source_ordinal": ordinal,
        "source_row_sha256": row_sha256,
        "observed_security_id": _observed(row.get("security_id")),
        "observed_composite_figi": _observed(row.get("source_composite_figi")),
        "observed_listing_id": _observed(row.get("listing_id")),
        "observed_ticker": _observed(row.get("current_snapshot_ticker_display")),
        "reason_codes": sorted(set(reasons)),
        "mapping_admitted": False,
        "qc_sid_available": False,
        "point_in_time": False,
        "independently_reviewed": False,
        "historical_availability_claimed": False,
    }
    _address_record(
        record,
        identifier="refusal_id",
        digest="refusal_sha256",
        prefix="arv2-security-master-refusal-",
    )
    return record


def _policy() -> dict[str, object]:
    return {
        "owner_risk_decision": OWNER_RISK_DECISION,
        "admission_rule": (
            "exactly_one_source_row_per_ticker_security_composite_figi_and_listing"
        ),
        "ambiguity_rule": "refuse_every_member_of_each_ambiguous_identity_group",
        "duplicate_rule": "refuse_every_occurrence_of_duplicate_source_evidence",
        "runtime_resolution_rule": (
            "ticker_must_resolve_once_inside_QC_and_returned_QC_SID_must_be_bound_"
            "without_replacing_the_Sharadar_logical_security_id"
        ),
        "current_snapshot_identity_basis": True,
        "owner_accepted_current_snapshot_risk": True,
        "qc_sid_available": False,
        "point_in_time": False,
        "independently_reviewed": False,
        "historical_availability_claimed": False,
    }


def _compose_document(
    rows: Iterable[dict[str, object]], source: Mapping[str, object]
) -> dict[str, object]:
    if type(source) is not dict or set(source) != _SOURCE_BINDING_KEYS:
        _refuse("accepted-risk security-master source binding fields changed")
    if (
        _id(source.get("seed_archive_id")) is None
        or _sha(source.get("seed_archive_sha256")) is None
        or _sha(source.get("eligible_universe_artifact_sha256")) is None
        or _id(source.get("sharadar_capture_id")) is None
        or _sha(source.get("sharadar_capture_sha256")) is None
        or _exact_instant(source.get("source_snapshot_available_at")) is None
        or type(source.get("source_candidate_count")) is not int
        or source["source_candidate_count"] <= 0
        or source["source_candidate_count"] > MAX_SOURCE_ROWS
    ):
        _refuse("accepted-risk security-master source binding is invalid")

    candidates: list[tuple[int, dict[str, object], str, set[str]]] = []
    for ordinal, raw in enumerate(rows, start=1):
        if ordinal > MAX_SOURCE_ROWS:
            _refuse("accepted-risk security-master source exceeds row bound")
        if type(raw) is not dict:
            _refuse("accepted-risk security-master source row is not an exact object")
        row = _canonical_copy(raw, "accepted-risk security-master source row")
        assert type(row) is dict
        row_sha = _PINNED_SHA256(_PINNED_CANONICAL(row))
        candidates.append((ordinal, row, row_sha, _structural_reasons(row)))
    if len(candidates) != source["source_candidate_count"]:
        _refuse("accepted-risk security-master source candidate census changed")

    group_fields = (
        ("source_row_sha256", "duplicate_source_evidence", _sha),
        (
            "current_snapshot_ticker_display",
            "ambiguous_ticker_mapping",
            lambda value: (
                value
                if type(value) is str and _TICKER.fullmatch(value) is not None
                else None
            ),
        ),
        ("security_id", "ambiguous_security_id_mapping", _id),
        (
            "source_composite_figi",
            "ambiguous_composite_figi_mapping",
            lambda value: (
                value
                if type(value) is str and _FIGI.fullmatch(value) is not None
                else None
            ),
        ),
        ("listing_id", "ambiguous_listing_id_mapping", _id),
    )
    for field, reason, validator in group_fields:
        groups: dict[str, list[int]] = defaultdict(list)
        for index, (_ordinal, row, _row_sha, _reasons) in enumerate(candidates):
            value = validator(row.get(field))
            if value is not None:
                groups[value].append(index)
        for indexes in groups.values():
            if len(indexes) > 1:
                for index in indexes:
                    candidates[index][3].add(reason)

    admitted: list[dict[str, object]] = []
    refused: list[dict[str, object]] = []
    reason_counts: Counter[str] = Counter()
    for ordinal, row, row_sha, reasons in candidates:
        if reasons:
            refused.append(_refusal(row, ordinal, row_sha, reasons))
            reason_counts.update(reasons)
        else:
            admitted.append(_mapping(row, ordinal))
    admitted.sort(key=lambda item: (item["ticker"], item["security_id"]))
    refused.sort(key=lambda item: item["source_ordinal"])
    document: dict[str, object] = {
        "schema": ADMISSION_SCHEMA,
        "source": _canonical_copy(source, "security-master source binding"),
        "policy": _policy(),
        "census": {
            "source_candidate_count": len(candidates),
            "admitted_mapping_count": len(admitted),
            "named_refusal_count": len(refused),
            "refusal_reason_counts": dict(sorted(reason_counts.items())),
        },
        "admitted_mappings": admitted,
        "named_refusals": refused,
        "capabilities": {name: False for name in _CAPABILITY_NAMES},
    }
    _address_record(
        document,
        identifier="admission_id",
        digest="admission_sha256",
        prefix="arv2-security-master-admission-",
    )
    return document


def _decode(payload: bytes) -> dict[str, Any]:
    try:
        value = _PINNED_LOADS(
            _PINNED_DECODE(payload, "accepted-risk security-master admission"),
            "accepted-risk security-master admission",
        )
    except CanonicalEvidenceError as exc:
        raise AcceptedRiskSecurityMasterAdmissionError(
            "accepted-risk security-master admission is not strict JSON"
        ) from exc
    if type(value) is not dict or _PINNED_CANONICAL(value) != payload:
        _refuse("accepted-risk security-master admission is not one canonical object")
    return value


def _require_document(document: dict[str, object]) -> tuple[int, int, Counter[str]]:
    if set(document) != {
        "schema",
        "admission_id",
        "admission_sha256",
        "source",
        "policy",
        "census",
        "admitted_mappings",
        "named_refusals",
        "capabilities",
    }:
        _refuse("accepted-risk security-master admission fields changed")
    if document["schema"] != ADMISSION_SCHEMA:
        _refuse("accepted-risk security-master admission schema changed")
    if not _address_is_current(
        document,
        identifier="admission_id",
        digest="admission_sha256",
        prefix="arv2-security-master-admission-",
    ):
        _refuse("accepted-risk security-master admission content address changed")
    if document["policy"] != _policy():
        _refuse("accepted-risk security-master admission policy changed")
    if document["capabilities"] != {name: False for name in _CAPABILITY_NAMES}:
        _refuse("accepted-risk security-master capabilities changed")
    mappings = document["admitted_mappings"]
    refusals = document["named_refusals"]
    if type(mappings) is not list or type(refusals) is not list:
        _refuse("accepted-risk security-master disposition arrays changed")
    seen_tickers: set[str] = set()
    seen_security: set[str] = set()
    seen_figi: set[str] = set()
    seen_listing: set[str] = set()
    for row in mappings:
        if type(row) is not dict or set(row) != _MAPPING_KEYS:
            _refuse("accepted-risk security-master admitted mapping fields changed")
        if (
            row["schema"] != MAPPING_SCHEMA
            or row["mapping_status"] != MAPPING_STATUS
            or row["qc_security_id"] is not None
            or any(
                row[name] is not False
                for name in (
                    "qc_sid_available",
                    "point_in_time",
                    "independently_reviewed",
                    "historical_availability_claimed",
                )
            )
            or row["current_snapshot_identity_basis"] is not True
            or row["owner_accepted_current_snapshot_risk"] is not True
        ):
            _refuse("accepted-risk security-master mapping risk flags changed")
        ticker = row["ticker"]
        security = row["security_id"]
        figi = row["composite_figi"]
        listing = row["listing_id"]
        if (
            ticker in seen_tickers
            or security in seen_security
            or figi in seen_figi
            or listing in seen_listing
        ):
            _refuse("accepted-risk security-master admitted mappings overlap")
        seen_tickers.add(ticker)
        seen_security.add(security)
        seen_figi.add(figi)
        seen_listing.add(listing)
    reasons: Counter[str] = Counter()
    seen_refusals: set[str] = set()
    for row in refusals:
        if type(row) is not dict or set(row) != _REFUSAL_KEYS:
            _refuse("accepted-risk security-master refusal fields changed")
        refusal_id = row["refusal_id"]
        reason_codes = row["reason_codes"]
        if (
            row["schema"] != REFUSAL_SCHEMA
            or type(refusal_id) is not str
            or refusal_id in seen_refusals
            or type(reason_codes) is not list
            or not reason_codes
            or reason_codes != sorted(set(reason_codes))
            or row["mapping_admitted"] is not False
            or any(
                row[name] is not False
                for name in (
                    "qc_sid_available",
                    "point_in_time",
                    "independently_reviewed",
                    "historical_availability_claimed",
                )
            )
            or not _address_is_current(
                row,
                identifier="refusal_id",
                digest="refusal_sha256",
                prefix="arv2-security-master-refusal-",
            )
        ):
            _refuse("accepted-risk security-master refusal status changed")
        seen_refusals.add(refusal_id)
        reasons.update(reason_codes)
    census = document["census"]
    expected = {
        "source_candidate_count": len(mappings) + len(refusals),
        "admitted_mapping_count": len(mappings),
        "named_refusal_count": len(refusals),
        "refusal_reason_counts": dict(sorted(reasons.items())),
    }
    if census != expected:
        _refuse("accepted-risk security-master disposition census changed")
    return len(mappings), len(refusals), reasons


def build_accepted_risk_security_master_admission(
    archive: PhysicalPreopenSeedArchive,
) -> AcceptedRiskSecurityMasterAdmission:
    """Build a non-PIT current-snapshot admission from one physical seed."""

    _require_dependencies()
    if type(archive) is not _PINNED_SEED_TYPE:
        _refuse("accepted-risk security-master requires exact physical seed type")
    try:
        parent = _PINNED_REQUIRE_SEED(archive)
        rows = tuple(_PINNED_ITER_UNIVERSE(parent))
        binding = _source_binding(parent, rows)
    except _seed.PhysicalPreopenSeedArchiveError as exc:
        raise AcceptedRiskSecurityMasterAdmissionError(
            "accepted-risk security-master physical seed did not reauthenticate"
        ) from exc
    document = _compose_document(rows, binding)
    admitted, refused, reasons = _require_document(document)
    payload = _PINNED_CANONICAL(document)
    if not 0 < len(payload) <= MAX_DOCUMENT_BYTES:
        _refuse("accepted-risk security-master admission exceeds byte bound")
    false_capabilities = {name: False for name in _CAPABILITY_NAMES}
    value = AcceptedRiskSecurityMasterAdmission(
        schema=ADMISSION_SCHEMA,
        admission_id=document["admission_id"],
        admission_sha256=document["admission_sha256"],
        payload_sha256=_PINNED_SHA256(payload),
        document_bytes=payload,
        seed_archive_id=parent.archive_id,
        seed_archive_sha256=parent.archive_sha256,
        eligible_universe_artifact_sha256=binding[
            "eligible_universe_artifact_sha256"
        ],
        sharadar_capture_id=parent.sharadar_capture_id,
        sharadar_capture_sha256=parent.sharadar_capture_sha256,
        source_snapshot_available_at=binding["source_snapshot_available_at"],
        source_candidate_count=len(rows),
        admitted_mapping_count=admitted,
        named_refusal_count=refused,
        refusal_reason_counts=tuple(sorted(reasons.items())),
        qc_sid_available=False,
        point_in_time=False,
        independently_reviewed=False,
        historical_availability_claimed=False,
        current_snapshot_identity_basis=True,
        owner_accepted_current_snapshot_risk=True,
        **false_capabilities,
    )
    identity = id(value)
    reference = weakref.ref(value, lambda ref, key=identity: _forget(key, ref))
    with _AUTHORITY_LOCK:
        _AUTHORITIES[identity] = (
            reference,
            _fingerprint(value),
            weakref.ref(parent),
            os.getpid(),
        )
    return value


def require_accepted_risk_security_master_admission(
    value: AcceptedRiskSecurityMasterAdmission,
) -> AcceptedRiskSecurityMasterAdmission:
    """Reauthenticate the admission and its exact physical-seed parent."""

    _require_dependencies()
    current_pid = os.getpid()
    if type(value) is not AcceptedRiskSecurityMasterAdmission or current_pid != _AUTHORITY_PID:
        _refuse("accepted-risk security-master admission is not current process authority")
    with _AUTHORITY_LOCK:
        authority = _AUTHORITIES.get(id(value))
    if (
        authority is None
        or authority[0]() is not value
        or authority[1] != _fingerprint(value)
        or authority[3] != current_pid
        or any(getattr(value, name) is not False for name in _CAPABILITY_NAMES)
        or any(
            getattr(value, name) is not False
            for name in (
                "qc_sid_available",
                "point_in_time",
                "independently_reviewed",
                "historical_availability_claimed",
            )
        )
        or value.current_snapshot_identity_basis is not True
        or value.owner_accepted_current_snapshot_risk is not True
    ):
        _refuse("accepted-risk security-master admission is not current builder authority")
    parent = authority[2]()
    if parent is None:
        _refuse("accepted-risk security-master physical seed authority is unavailable")
    try:
        parent = _PINNED_REQUIRE_SEED(parent)
        rows = tuple(_PINNED_ITER_UNIVERSE(parent))
        binding = _source_binding(parent, rows)
    except _seed.PhysicalPreopenSeedArchiveError as exc:
        raise AcceptedRiskSecurityMasterAdmissionError(
            "accepted-risk security-master physical seed did not reauthenticate"
        ) from exc
    if type(value.document_bytes) is not bytes or value.payload_sha256 != _PINNED_SHA256(value.document_bytes):
        _refuse("accepted-risk security-master admission payload binding changed")
    document = _decode(value.document_bytes)
    expected = _compose_document(rows, binding)
    if document != expected:
        _refuse("accepted-risk security-master admission no longer matches physical seed")
    admitted, refused, reasons = _require_document(document)
    if (
        value.schema != ADMISSION_SCHEMA
        or value.admission_id != document["admission_id"]
        or value.admission_sha256 != document["admission_sha256"]
        or value.seed_archive_id != parent.archive_id
        or value.seed_archive_sha256 != parent.archive_sha256
        or value.eligible_universe_artifact_sha256
        != binding["eligible_universe_artifact_sha256"]
        or value.sharadar_capture_id != parent.sharadar_capture_id
        or value.sharadar_capture_sha256 != parent.sharadar_capture_sha256
        or value.source_snapshot_available_at != binding["source_snapshot_available_at"]
        or value.source_candidate_count != len(rows)
        or value.admitted_mapping_count != admitted
        or value.named_refusal_count != refused
        or value.refusal_reason_counts != tuple(sorted(reasons.items()))
    ):
        _refuse("accepted-risk security-master admission projection changed")
    return value


def iter_accepted_risk_security_master_mappings(
    value: AcceptedRiskSecurityMasterAdmission,
) -> Iterator[dict[str, object]]:
    artifact = require_accepted_risk_security_master_admission(value)
    document = _decode(artifact.document_bytes)
    for row in document["admitted_mappings"]:
        yield row
    require_accepted_risk_security_master_admission(artifact)


def iter_accepted_risk_security_master_refusals(
    value: AcceptedRiskSecurityMasterAdmission,
) -> Iterator[dict[str, object]]:
    artifact = require_accepted_risk_security_master_admission(value)
    document = _decode(artifact.document_bytes)
    for row in document["named_refusals"]:
        yield row
    require_accepted_risk_security_master_admission(artifact)


__all__ = [
    "ADMISSION_SCHEMA",
    "MAPPING_SCHEMA",
    "MAPPING_STATUS",
    "OWNER_RISK_DECISION",
    "REFUSAL_SCHEMA",
    "AcceptedRiskSecurityMasterAdmission",
    "AcceptedRiskSecurityMasterAdmissionError",
    "build_accepted_risk_security_master_admission",
    "iter_accepted_risk_security_master_mappings",
    "iter_accepted_risk_security_master_refusals",
    "require_accepted_risk_security_master_admission",
]
