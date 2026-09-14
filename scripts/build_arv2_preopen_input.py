"""Compose the physical ARV2 pre-open input candidate without reading outcomes.

The public builder accepts only a loader-authenticated Massive accepted-risk
bridge and a Sharadar capture whose exact ZIP bytes can be reauthenticated at
the call boundary.  It derives (rather than accepts from a caller) source
coverage classifications and streams the three Sharadar CSV archives.  It may
emit the six batch-major input roles only after the physical sources establish
the reviewed full point-in-time security/session peer census.

Sharadar TICKERS remains a capture-time current snapshot.  Its permanent IDs,
listing dates, classifications, and ticker are therefore only a non-pristine
discovery candidate for the separately gated QC SID round trip.  ACTIONS is
retained as discovery evidence only.  No firm rating order is inferred: the
builder emits a deterministic observed-vocabulary candidate whose status is
``review_required_not_authority``.  Until a later reviewed ontology exists,
the physical q-data measurement uses an exact zero-quality refusal policy;
that records the unresolved boundary and grants no rating-mapping,
control-construction, or production-signal authority.  The currently supported Sharadar TICKERS
capture is explicitly a capture-time snapshot, so this version returns a
content-addressed review/refusal candidate and deliberately leaves the
production input manifest and run-authority candidate absent.  It still
builds deterministic identity, membership, fundamental, and accepted-risk
seed projections so the missing authority is concrete and auditable; those
projections are not launchable pre-open inputs.

Importing this module performs no filesystem, provider, credential,
QuantConnect, Object Store, market, outcome, result, broker, or order access.
Calling the builder performs bounded local artifact reads only.
"""
from __future__ import annotations

import csv
import dataclasses
import hashlib
import io
import json
import os
import re
import stat
import threading
import weakref
import zipfile
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Iterator, Mapping, Sequence

from data.exchange_calendar import (
    ExchangeCalendarError,
    SUPPORTED_SESSION_START,
    resolve_nth_session_after,
    trading_sessions,
)
from research.analyst_revisions_v2.accepted_risk_input_pair import (
    AcceptedRiskSourceRow,
    MassiveSourceRole,
    RowDisposition,
)
from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    decode_utf8,
    require_identifier,
    sha256_bytes,
    strict_json_loads,
)
from research.analyst_revisions_v2.preopen_control_acquisition import SOURCE_VIEW_ID
from research.analyst_revisions_v2_qc.preopen_control_stage import (
    EARNINGS_INPUT_SCHEMA,
    FUNDAMENTAL_INPUT_SCHEMA,
    GUIDANCE_INPUT_SCHEMA,
    RATING_INPUT_SCHEMA,
)
from scripts.build_arv2_massive_input_pair import (
    MassiveAcceptedRiskBridge,
    MassiveInputPairBridgeError,
    require_massive_accepted_risk_bridge,
)
from scripts.capture_arv2_sharadar import (
    ACTIONS_AVAILABILITY,
    FUNDAMENTALS_ADMITTED_DIMENSION,
    FUNDAMENTALS_AVAILABILITY,
    MAX_ARCHIVE_BYTES,
    MAX_CSV_FIELD_BYTES,
    MAX_TOTAL_ROWS,
    TICKERS_AVAILABILITY,
    LoadedSharadarCapture,
    SharadarCaptureError,
    SharadarDataset,
    load_sharadar_capture_artifact,
)


COMPOSER_SCHEMA = "arv2-physical-preopen-input-composer-v1"
COMPOSITION_REPORT_SCHEMA = "arv2-physical-preopen-composition-report-v1"
FIRM_REVIEW_SCHEMA = "arv2-firm-ontology-observed-vocabulary-review-v1"
UNIVERSE_ARTIFACT_SCHEMA = "arv2-eligible-universe-review-candidate-v1"
SOURCE_SEED_CANDIDATE_SCHEMA = "arv2-preopen-source-seed-review-candidate-v1"
FUNDAMENTAL_SEED_INVENTORY_SCHEMA = (
    "arv2-preopen-fundamental-seed-inventory-v1"
)
QUALITY_POLICY_SCHEMA = "arv2-preopen-zero-quality-refusal-policy-v1"
FROZEN_CAPTURE_FIRST_DATE = "2013-01-02"
FROZEN_CAPTURE_LAST_DATE = "2025-12-31"
FORMAL_FIRST_SESSION = "2013-01-02"
FORMAL_LAST_SESSION = "2025-12-31"
MAX_RETAINED_TICKER_ROWS = 250_000
MAX_RETAINED_TARGET_SECURITIES = 100_000
MAX_SCANNED_FUNDAMENTAL_SOURCE_ROWS = MAX_TOTAL_ROWS
MAX_RETAINED_DERIVED_ROWS = 500_000
MAX_FIRM_VOCABULARY_ENTRIES = 100_000
MAX_FIRM_NAME_VOCABULARY_ENTRIES = 100_000
MAX_ACTION_VOCABULARY_ENTRIES = 10_000
MAX_RETAINED_FIELD_CHARACTERS = 8_192
MAX_CSV_ROW_CHARACTERS = 8 * 1024 * 1024
MAX_SOURCE_SEED_CANDIDATE_BYTES = 256 * 1024 * 1024
FUNDAMENTAL_SEED_AVAILABILITY = (
    "max_filing_date_and_lastupdated_plus_one_calendar_day_"
    "at_1200_utc_conservative"
)

STATUS_BLOCKED = "review_required_full_PIT_universe_unavailable"
FULL_PIT_UNIVERSE_REFUSAL = (
    "sharadar_TICKERS_is_capture_time_current_snapshot_and_cannot_establish_"
    "the_full_point_in_time_US_common_stock_security_session_peer_census"
)
FIRM_ONTOLOGY_REFUSAL = (
    "observed_firm_label_vocabulary_has_no_reviewed_per_firm_ordering_or_scope"
)

_TICKER = re.compile(r"[A-Z0-9][A-Z0-9.\-]{0,31}\Z")
_CUSIP = re.compile(r"[0-9A-Z]{9}\Z")
_SAFE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_STRUCTURAL_REFUSALS = frozenset(
    {
        RowDisposition.INVALID_PROVIDER_EVENT_ID,
        RowDisposition.INVALID_EVENT_DATE,
        RowDisposition.INVALID_EVENT_TIME,
        RowDisposition.EVENT_OUTSIDE_REQUESTED_CAPTURE_RANGE,
        RowDisposition.EVENT_OUTSIDE_EXCHANGE_CALENDAR_AUTHORITY,
        RowDisposition.INVALID_LAST_UPDATED_EXPLICIT_OFFSET,
        RowDisposition.LAST_UPDATED_AFTER_CAPTURE,
    }
)
_ALLOWED_COMMON_STOCK_CATEGORIES = frozenset(
    {
        "domestic common stock",
        "domestic common stock primary class",
        "domestic common stock secondary class",
    }
)
_SHARADAR_EXCHANGE_TO_MIC = {
    "AMEX": "XASE",
    "NASDAQ": "XNAS",
    "NYSE": "XNYS",
    "NYSE AMERICAN": "XASE",
    "NYSE MKT": "XASE",
    "NYSEAMERICAN": "XASE",
    "NYSEMKT": "XASE",
}


class PhysicalPreopenInputError(ValueError):
    """Physical source bytes cannot produce the closed pre-open candidate."""


@dataclasses.dataclass(frozen=True)
class _SecurityCandidate:
    security_id: str
    issuer_id: str
    composite_figi: str
    listing_id: str
    ticker: str
    cusips: tuple[str, ...]
    exchange_id: str
    sector_id: str
    industry_id: str
    first_priced_date: str
    last_priced_date: str | None
    source_row_sha256: str
    identity_evidence_sha256: str
    classification_evidence_sha256: str
    non_pristine_current_snapshot: bool


@dataclasses.dataclass(frozen=True, init=False)
class PhysicalPreopenInputCandidate:
    schema: str
    status: str
    candidate_id: str
    candidate_sha256: str
    massive_bridge_id: str
    massive_bridge_sha256: str
    pair_id: str
    pair_sha256: str
    derived_capture_id: str
    derived_capture_sha256: str
    sharadar_capture_id: str
    sharadar_capture_sha256: str
    first_session: str
    last_session: str
    calculation_session: str
    blocking_refusals: tuple[str, ...]
    closed_input_manifest_bytes: None
    run_authority_candidate_bytes: None
    firm_review_candidate_bytes: bytes
    composition_report_bytes: bytes
    eligible_universe_artifact_bytes: bytes
    source_seed_candidate_bytes: bytes
    fundamental_seed_inventory_bytes: bytes
    quality_policy_bytes: bytes
    rating_source_complete_for_frozen_query_and_accepted_risk_policy: bool
    earnings_source_complete_for_frozen_query_and_accepted_risk_policy: bool
    guidance_source_complete_for_frozen_query_and_accepted_risk_policy: bool
    firm_ontology_reviewed: bool
    sharadar_tickers_pristine_point_in_time: bool
    full_pit_universe_established: bool
    full_market_peer_census_established: bool
    six_preopen_roles_produced: bool
    production_preopen_input_available: bool
    actions_used_for_identity_or_payoff: bool
    outcome_access_performed: bool
    quantconnect_io_performed: bool


_AUTHORITIES: dict[
    int,
    tuple[weakref.ReferenceType[PhysicalPreopenInputCandidate], tuple[object, ...]],
] = {}
_AUTHORITIES_LOCK = threading.RLock()


def _fingerprint(value: PhysicalPreopenInputCandidate) -> tuple[object, ...]:
    return tuple(getattr(value, field.name) for field in dataclasses.fields(value))


def _forget(
    identity: int, reference: weakref.ReferenceType[PhysicalPreopenInputCandidate]
) -> None:
    with _AUTHORITIES_LOCK:
        current = _AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _AUTHORITIES.pop(identity, None)


def _safe_component(prefix: str, value: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise PhysicalPreopenInputError(f"{prefix} source identifier is absent")
    if _SAFE_COMPONENT.fullmatch(value) is not None:
        return f"{prefix}-{value}"
    digest = sha256_bytes(canonical_json_bytes({"kind": prefix, "value": value}))
    return f"{prefix}-{digest[:24]}"


def _text(value: object, name: str, *, required: bool = True) -> str | None:
    if value is None or value == "":
        if required:
            raise PhysicalPreopenInputError(f"{name} is absent")
        return None
    if (
        type(value) is not str
        or value != value.strip()
        or len(value) > MAX_RETAINED_FIELD_CHARACTERS
    ):
        raise PhysicalPreopenInputError(f"{name} is not bounded exact text")
    return value


def _date_text(value: object, name: str) -> str:
    text = _text(value, name)
    assert text is not None
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise PhysicalPreopenInputError(f"{name} is not a real date") from exc
    if parsed.isoformat() != text:
        raise PhysicalPreopenInputError(f"{name} is not canonical")
    return text


def _decimal_text(value: object, name: str, *, positive: bool = False) -> str:
    text = _text(value, name)
    assert text is not None
    try:
        parsed = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise PhysicalPreopenInputError(f"{name} is not decimal text") from exc
    if not parsed.is_finite() or (positive and parsed <= 0):
        raise PhysicalPreopenInputError(f"{name} is not admissible")
    return "0" if parsed == 0 else format(parsed, "f")


def _strict_provider_row(source: AcceptedRiskSourceRow) -> dict[str, object]:
    try:
        value = strict_json_loads(
            decode_utf8(source.raw_row_bytes, "accepted-risk source row"),
            "accepted-risk source row",
        )
    except CanonicalEvidenceError as exc:
        raise PhysicalPreopenInputError(
            "accepted-risk source row stopped being strict JSON"
        ) from exc
    if type(value) is not dict:
        raise PhysicalPreopenInputError("accepted-risk source row is not an object")
    return value


def _reauthenticated_sharadar(
    value: LoadedSharadarCapture,
) -> LoadedSharadarCapture:
    if type(value) is not LoadedSharadarCapture:
        raise PhysicalPreopenInputError(
            "Sharadar source requires exact LoadedSharadarCapture"
        )
    try:
        current = load_sharadar_capture_artifact(value.artifact_path)
    except SharadarCaptureError as exc:
        raise PhysicalPreopenInputError(
            "Sharadar capture failed physical reauthentication"
        ) from exc
    if current != value:
        raise PhysicalPreopenInputError("Sharadar capture changed after loading")
    return current


def _iter_sharadar_rows(
    loaded: LoadedSharadarCapture, dataset: SharadarDataset
) -> Iterator[dict[str, str]]:
    binding = next((item for item in loaded.archives if item.dataset is dataset), None)
    if binding is None:
        raise PhysicalPreopenInputError("Sharadar archive inventory is incomplete")
    path = loaded.artifact_path / binding.archive_file
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PhysicalPreopenInputError("Sharadar archive is unavailable") from exc
    previous_limit = csv.field_size_limit()
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) & 0o077
            or before.st_size != binding.archive_byte_count
            or before.st_size <= 0
            or before.st_size > MAX_ARCHIVE_BYTES
        ):
            raise PhysicalPreopenInputError("Sharadar archive is not a private file")
        archive_hash = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 128 * 1024)
            if not chunk:
                break
            archive_hash.update(chunk)
        if archive_hash.hexdigest() != binding.archive_sha256:
            raise PhysicalPreopenInputError("Sharadar archive hash changed")
        os.lseek(descriptor, 0, os.SEEK_SET)
        with os.fdopen(os.dup(descriptor), "rb", closefd=True) as source:
            with zipfile.ZipFile(source, "r", allowZip64=True) as archive:
                infos = archive.infolist()
                if [item.filename for item in infos] != [
                    item.name for item in binding.members
                ]:
                    raise PhysicalPreopenInputError("Sharadar ZIP inventory changed")
                observed_rows = 0
                for info, member in zip(infos, binding.members, strict=True):
                    if (
                        info.file_size != member.uncompressed_byte_count
                        or info.compress_size != member.compressed_byte_count
                        or info.CRC != member.crc32
                    ):
                        raise PhysicalPreopenInputError(
                            "Sharadar ZIP member metadata changed"
                        )
                    raw = archive.open(info, "r")
                    digest = hashlib.sha256()

                    class _HashingReader(io.RawIOBase):
                        def readable(self) -> bool:
                            return True

                        def readinto(self, buffer) -> int:
                            chunk = raw.read(len(buffer))
                            size = len(chunk)
                            buffer[:size] = chunk
                            digest.update(chunk)
                            return size

                    buffered = io.BufferedReader(_HashingReader(), buffer_size=128 * 1024)
                    text = io.TextIOWrapper(buffered, encoding="utf-8-sig", newline="")
                    try:
                        csv.field_size_limit(MAX_CSV_FIELD_BYTES)
                        rows = csv.DictReader(text, strict=True)
                        if tuple(rows.fieldnames or ()) != member.columns:
                            raise PhysicalPreopenInputError(
                                "Sharadar CSV columns changed"
                            )
                        member_rows = 0
                        for row in rows:
                            if (
                                None in row
                                or set(row) != set(member.columns)
                                or any(type(value) is not str for value in row.values())
                                or sum(
                                    len(key) + len(value)
                                    for key, value in row.items()
                                )
                                > MAX_CSV_ROW_CHARACTERS
                            ):
                                raise PhysicalPreopenInputError(
                                    "Sharadar CSV row width or byte proxy changed"
                                )
                            member_rows += 1
                            observed_rows += 1
                            if observed_rows > MAX_TOTAL_ROWS:
                                raise PhysicalPreopenInputError(
                                    "Sharadar row census exceeds bound"
                                )
                            yield dict(row)
                        text.read()
                    except (csv.Error, UnicodeError) as exc:
                        raise PhysicalPreopenInputError(
                            "Sharadar CSV stream is invalid"
                        ) from exc
                    finally:
                        text.close()
                        raw.close()
                    if (
                        member_rows != member.row_count
                        or digest.hexdigest() != member.content_sha256
                    ):
                        raise PhysicalPreopenInputError(
                            "Sharadar CSV content census changed"
                        )
                if observed_rows != binding.row_count:
                    raise PhysicalPreopenInputError(
                        "Sharadar archive row census changed"
                    )
        after = os.fstat(descriptor)
        named = os.stat(path, follow_symlinks=False)
        identities = {
            (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
            for item in (before, after, named)
        }
        if len(identities) != 1:
            raise PhysicalPreopenInputError("Sharadar archive changed while read")
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise PhysicalPreopenInputError("Sharadar archive could not be streamed") from exc
    finally:
        csv.field_size_limit(previous_limit)
        os.close(descriptor)


def _firm_review_candidate(
    bridge: MassiveAcceptedRiskBridge,
) -> tuple[bytes, dict[str, str]]:
    observed: Counter[tuple[str, str, str]] = Counter()
    firm_names: dict[str, set[str]] = defaultdict(set)
    observed_firm_name_count = 0
    event_dates: dict[str, list[str]] = defaultdict(list)
    source_hashes: dict[str, list[str]] = defaultdict(list)
    for source in bridge.pair.rows:
        if source.locator.source_role is not MassiveSourceRole.ANALYST_RATINGS:
            continue
        try:
            row = _strict_provider_row(source)
            firm_id = require_identifier(row.get("benzinga_firm_id"), "benzinga_firm_id")
            firm_name = _text(row.get("firm"), "firm")
            assert firm_name is not None
            event_date = _date_text(row.get("date"), "rating date")
        except (CanonicalEvidenceError, PhysicalPreopenInputError):
            continue
        names = firm_names[firm_id]
        if firm_name not in names:
            names.add(firm_name)
            observed_firm_name_count += 1
        if observed_firm_name_count > MAX_FIRM_NAME_VOCABULARY_ENTRIES:
            raise PhysicalPreopenInputError(
                "observed firm-name vocabulary exceeds reviewed bound"
            )
        event_dates[firm_id].append(event_date)
        source_hashes[firm_id].append(source.locator.raw_row_sha256)
        for field in ("rating", "previous_rating"):
            label = row.get(field)
            if (
                type(label) is str
                and label
                and label == label.strip()
                and len(label) <= MAX_RETAINED_FIELD_CHARACTERS
            ):
                observed[(firm_id, field, label)] += 1
                if len(observed) > MAX_FIRM_VOCABULARY_ENTRIES:
                    raise PhysicalPreopenInputError(
                        "observed firm vocabulary exceeds reviewed bound"
                    )
    labels_by_firm: dict[str, list[dict[str, object]]] = defaultdict(list)
    for (firm_id, field, label), count in sorted(observed.items()):
        labels_by_firm[firm_id].append(
            {
                "field": field,
                "raw_label": label,
                "observed_count": count,
            }
        )
    firms = []
    for firm_id in sorted(firm_names):
        firms.append(
            {
                "provider_firm_id": firm_id,
                "observed_firm_names": sorted(firm_names[firm_id]),
                "first_event_date": min(event_dates[firm_id]),
                "last_event_date": max(event_dates[firm_id]),
                "source_row_count": len(source_hashes[firm_id]),
                "source_row_projection_sha256": sha256_bytes(
                    canonical_json_bytes(sorted(source_hashes[firm_id]))
                ),
                "observed_labels": labels_by_firm[firm_id],
                "ordered_scale": None,
                "scope": None,
            }
        )
    semantic = {
        "schema": FIRM_REVIEW_SCHEMA,
        "status": "review_required_not_authority",
        "massive_bridge_id": bridge.bridge_id,
        "massive_bridge_sha256": bridge.bridge_sha256,
        "firm_count": len(firms),
        "observed_label_count": sum(len(item["observed_labels"]) for item in firms),
        "firms": firms,
        "ordering_inferred": False,
        "ontology_reviewed": False,
        "production_authority": False,
        "outcomes_used": False,
    }
    semantic_sha = sha256_bytes(canonical_json_bytes(semantic))
    record = {
        **semantic,
        "candidate_id": f"arv2-firm-vocabulary-{semantic_sha[:24]}",
        "candidate_semantic_sha256": semantic_sha,
    }
    payload = canonical_json_bytes(record)
    if len(payload) > MAX_SOURCE_SEED_CANDIDATE_BYTES:
        raise PhysicalPreopenInputError(
            "firm-vocabulary review candidate exceeds retained byte bound"
        )
    return payload, {
        "artifact_id": record["candidate_id"],
        "artifact_sha256": sha256_bytes(payload),
    }


def _quality_policy_bytes() -> bytes:
    return canonical_json_bytes(
        {
            "schema": QUALITY_POLICY_SCHEMA,
            "method_id": "arv2-qdata-conservative-min-v1",
            "component_order": [
                "timestamp_quality",
                "firm_label_mapping_quality",
                "security_entity_mapping_quality",
            ],
            "component_values": ["0", "0", "0"],
            "reason": (
                "accepted-risk-current-vintage-and-unreviewed-firm-or-"
                "current-snapshot-security-mapping"
            ),
            "quality": "0",
            "firm_order_inferred": False,
            "production_signal_authority": False,
            "outcome_access": False,
        }
    )


def _source_completeness(
    bridge: MassiveAcceptedRiskBridge,
) -> dict[MassiveSourceRole, bool]:
    pair = bridge.pair
    exact_range = (
        pair.capture.requested_first_event_date == FROZEN_CAPTURE_FIRST_DATE
        and pair.capture.requested_last_event_date == FROZEN_CAPTURE_LAST_DATE
    )
    result: dict[MassiveSourceRole, bool] = {}
    for role in MassiveSourceRole:
        role_rows = tuple(row for row in pair.rows if row.locator.source_role is role)
        structural = any(
            row.current_view.disposition in _STRUCTURAL_REFUSALS
            or row.censored_view.disposition in _STRUCTURAL_REFUSALS
            for row in role_rows
        )
        result[role] = exact_range and bool(role_rows) and not structural
    return result


def _sharadar_cusips(value: object) -> tuple[str, ...]:
    """Parse Sharadar's comma-delimited current-export CUSIP vocabulary.

    TICKERS is still a capture-time snapshot, so these values are join seeds,
    never historical effective intervals.  Missing or malformed values are
    retained as an empty vocabulary for the downstream reviewed QC-CUSIP
    bridge to terminal explicitly; they must not make the security disappear
    from the candidate census.
    """

    if value in (None, ""):
        return ()
    if type(value) is not str or len(value) > MAX_RETAINED_FIELD_CHARACTERS:
        return ()
    parts = tuple(part.strip().upper() for part in value.split(","))
    if (
        not parts
        or any(_CUSIP.fullmatch(part) is None for part in parts)
        or len(parts) != len(set(parts))
    ):
        return ()
    return tuple(sorted(parts))


def _ticker_candidates(
    loaded: LoadedSharadarCapture,
) -> tuple[dict[str, _SecurityCandidate], dict[str, str], dict[str, int]]:
    by_ticker: dict[str, list[_SecurityCandidate]] = defaultdict(list)
    refusal_counts: Counter[str] = Counter()
    observed = 0
    for row in _iter_sharadar_rows(loaded, SharadarDataset.TICKERS):
        observed += 1
        if observed > MAX_RETAINED_TICKER_ROWS:
            raise PhysicalPreopenInputError("TICKERS exceeds composer row bound")
        try:
            table = _text(row.get("table"), "Sharadar table")
            assert table is not None
            if table.casefold() != "fundamentals":
                raise PhysicalPreopenInputError(
                    "ticker row is outside the Sharadar fundamentals table"
                )
            ticker = _text(row.get("ticker"), "Sharadar ticker")
            assert ticker is not None
            if _TICKER.fullmatch(ticker) is None:
                raise PhysicalPreopenInputError("Sharadar ticker is unsupported")
            cusips = _sharadar_cusips(row.get("cusips"))
            permaticker = _text(row.get("permaticker"), "Sharadar permaticker")
            assert permaticker is not None
            category = _text(row.get("category"), "Sharadar category")
            assert category is not None
            if category.casefold() not in _ALLOWED_COMMON_STOCK_CATEGORIES:
                raise PhysicalPreopenInputError("not reviewed domestic common stock")
            exchange = _text(row.get("exchange"), "Sharadar exchange")
            assert exchange is not None
            exchange_id = _SHARADAR_EXCHANGE_TO_MIC.get(exchange.upper())
            if exchange_id is None:
                raise PhysicalPreopenInputError(
                    "listing exchange is outside frozen XASE/XNAS/XNYS universe"
                )
            sector = _text(row.get("sector"), "Sharadar sector")
            industry = _text(row.get("industry"), "Sharadar industry")
            first = _date_text(row.get("firstpricedate"), "firstpricedate")
            last_raw = _text(row.get("lastpricedate"), "lastpricedate", required=False)
            last = None if last_raw is None else _date_text(last_raw, "lastpricedate")
            figi = _text(row.get("figi"), "Sharadar composite FIGI", required=False)
            if figi is None:
                raise PhysicalPreopenInputError("Sharadar composite FIGI is absent")
            assert exchange is not None and sector is not None and industry is not None
            source_hash = sha256_bytes(canonical_json_bytes(row))
            identity = {
                "permaticker": permaticker,
                "composite_figi": figi,
                "source_table": table,
                "ticker": ticker,
                "cusips": list(cusips),
                "exchange": exchange,
                "exchange_mic": exchange_id,
                "firstpricedate": first,
                "lastpricedate": last,
                "source_row_sha256": source_hash,
                "availability_semantics": TICKERS_AVAILABILITY,
            }
            classification = {
                "permaticker": permaticker,
                "sector": sector,
                "industry": industry,
                "source_row_sha256": source_hash,
                "availability_semantics": TICKERS_AVAILABILITY,
            }
            candidate = _SecurityCandidate(
                security_id=_safe_component("sharadar-composite-figi", figi),
                issuer_id=_safe_component("sharadar-permaticker", permaticker),
                composite_figi=figi,
                listing_id=(
                    "sharadar-listing-"
                    + sha256_bytes(canonical_json_bytes(identity))[:24]
                ),
                ticker=ticker,
                cusips=cusips,
                exchange_id=exchange_id,
                sector_id=_safe_component("sharadar-sector", sector),
                industry_id=_safe_component("sharadar-industry", industry),
                first_priced_date=first,
                last_priced_date=last,
                source_row_sha256=source_hash,
                identity_evidence_sha256=sha256_bytes(canonical_json_bytes(identity)),
                classification_evidence_sha256=sha256_bytes(
                    canonical_json_bytes(classification)
                ),
                non_pristine_current_snapshot=True,
            )
        except PhysicalPreopenInputError as exc:
            refusal_counts[str(exc)] += 1
            continue
        by_ticker[ticker].append(candidate)
    unique: dict[str, _SecurityCandidate] = {}
    refusal_by_ticker: dict[str, str] = {}
    for ticker, candidates in by_ticker.items():
        exact = sorted(set(candidates), key=lambda item: item.security_id)
        if len(exact) != 1:
            refusal_by_ticker[ticker] = "ambiguous_current_snapshot_ticker"
            refusal_counts["ambiguous_current_snapshot_ticker"] += len(candidates)
        else:
            unique[ticker] = exact[0]
    # A second ticker or permaticker must not silently alias the same logical
    # security/share class.  The current export is not a historical interval
    # table, so an apparent rename is a review candidate rather than authority.
    by_identity: dict[tuple[str, str], list[str]] = defaultdict(list)
    for ticker, candidate in unique.items():
        by_identity[(candidate.security_id, candidate.issuer_id)].append(ticker)
    for tickers in by_identity.values():
        if len(tickers) <= 1:
            continue
        for ticker in tickers:
            unique.pop(ticker, None)
            refusal_by_ticker[ticker] = "cross_ticker_current_snapshot_identity_alias"
            refusal_counts["cross_ticker_current_snapshot_identity_alias"] += 1
    return unique, refusal_by_ticker, dict(sorted(refusal_counts.items()))


def _session_axis(last_session: str) -> tuple[dict[str, int], set[str]]:
    try:
        sessions = trading_sessions(
            SUPPORTED_SESSION_START, date.fromisoformat(last_session)
        )
    except (ExchangeCalendarError, ValueError) as exc:
        raise PhysicalPreopenInputError("NYSE session axis is unavailable") from exc
    by_text = {session.isoformat(): offset for offset, session in enumerate(sessions)}
    return by_text, set(by_text)


def _event_session(event_date: str, session_set: set[str]) -> str:
    if event_date in session_set:
        return event_date
    try:
        return resolve_nth_session_after(event_date, 1)
    except ExchangeCalendarError as exc:
        raise PhysicalPreopenInputError("event date has no later NYSE session") from exc


def _composition_terminal(
    source: AcceptedRiskSourceRow,
    *, disposition: str,
    reason: str | None,
    security_id: str | None,
) -> dict[str, object]:
    semantic = {
        "locator_sha256": sha256_bytes(canonical_json_bytes(source.locator.to_record())),
        "source_role": source.locator.source_role.value,
        "provider_event_id": source.provider_event_id,
        "raw_row_sha256": source.locator.raw_row_sha256,
        "current_view_disposition": source.current_view.disposition.value,
        "censored_view_disposition": source.censored_view.disposition.value,
        "preopen_composition_disposition": disposition,
        "reason": reason,
        "security_id": security_id,
    }
    return {**semantic, "terminal_sha256": sha256_bytes(canonical_json_bytes(semantic))}


def _source_rows(
    bridge: MassiveAcceptedRiskBridge,
    securities: Mapping[str, _SecurityCandidate],
    *, session_ordinals: Mapping[str, int], session_set: set[str],
) -> tuple[
    dict[str, list[dict[str, object]]],
    dict[tuple[str, str], str],
    list[dict[str, object]],
    set[MassiveSourceRole],
]:
    rows_by_role: dict[str, list[dict[str, object]]] = {
        "earnings": [], "guidance": [], "ratings": []
    }
    universe_sources: dict[tuple[str, str], str] = {}
    terminals: list[dict[str, object]] = []
    semantically_incomplete_roles: set[MassiveSourceRole] = set()
    seen_role_rows: dict[str, set[bytes]] = {role: set() for role in rows_by_role}
    for source in bridge.pair.rows:
        role = source.locator.source_role
        security = securities.get(source.current_restated_security_label)
        eligibility = source.censored_view
        if security is None:
            terminals.append(
                _composition_terminal(
                    source,
                    disposition="named_refusal",
                    reason="no_unique_admissible_Sharadar_identity",
                    security_id=None,
                )
            )
            continue
        if eligibility.eligible_session is None or eligibility.eligible_at is None:
            terminals.append(
                _composition_terminal(
                    source,
                    disposition="named_refusal",
                    reason="source_row_has_no_authenticated_eligibility_session",
                    security_id=security.security_id,
                )
            )
            continue
        if (
            eligibility.eligible_session < security.first_priced_date
            or (
                security.last_priced_date is not None
                and eligibility.eligible_session > security.last_priced_date
            )
        ):
            terminals.append(
                _composition_terminal(
                    source,
                    disposition="named_refusal",
                    reason=(
                        "event_eligibility_outside_current_snapshot_listing_"
                        "interval"
                    ),
                    security_id=security.security_id,
                )
            )
            continue
        ordinal = session_ordinals.get(eligibility.eligible_session)
        if ordinal is None:
            terminals.append(
                _composition_terminal(
                    source,
                    disposition="outside_composer_session_axis",
                    reason="eligibility_session_outside_formal_axis",
                    security_id=security.security_id,
                )
            )
            continue
        raw = _strict_provider_row(source)
        output: dict[str, object] | None = None
        detail = "excluded_from_conservative_censored_view"
        if role is MassiveSourceRole.ANALYST_RATINGS:
            analyst = raw.get("benzinga_analyst_id")
            firm = raw.get("benzinga_firm_id")
            try:
                analyst_id = require_identifier(analyst, "benzinga_analyst_id")
                firm_id = require_identifier(firm, "benzinga_firm_id")
            except CanonicalEvidenceError:
                analyst_id = firm_id = None
            admitted = (
                eligibility.included
                and analyst_id is not None
                and firm_id is not None
                and source.provider_event_id is not None
            )
            suffix = source.locator.raw_row_sha256[:24]
            output = {
                "schema": RATING_INPUT_SCHEMA,
                "security_id": security.security_id,
                "source_view_id": SOURCE_VIEW_ID,
                "admitted": admitted,
                "eligible_session_ordinal": ordinal,
                "available_at": eligibility.eligible_at,
                "analyst_id": analyst_id if admitted else f"refused-analyst-{suffix}",
                "institution_id": firm_id if admitted else f"refused-firm-{suffix}",
                "common_event_id": (
                    _safe_component("benzinga-event", source.provider_event_id)
                    if source.provider_event_id is not None
                    else f"refused-event-{suffix}"
                ),
            }
            if admitted:
                detail = "emitted_admitted_rating"
            elif eligibility.included:
                detail = (
                    "potentially_relevant_rating_missing_or_invalid_stable_"
                    "analyst_or_firm_identifier"
                )
                semantically_incomplete_roles.add(role)
            else:
                detail = "emitted_nonadmitted_conservative_censor_terminal"
            if (
                source.current_view.included
                and source.current_view.eligible_session is not None
                and security.first_priced_date
                <= source.current_view.eligible_session
                and (
                    security.last_priced_date is None
                    or source.current_view.eligible_session
                    <= security.last_priced_date
                )
            ):
                universe_sources.setdefault(
                    (security.security_id, source.current_view.eligible_session),
                    source.locator.raw_row_sha256,
                )
        elif role is MassiveSourceRole.EARNINGS:
            if eligibility.included and source.event_date is not None:
                try:
                    report_session = _event_session(
                        source.event_date, session_set
                    )
                    output = {
                        "schema": EARNINGS_INPUT_SCHEMA,
                        "security_id": security.security_id,
                        "report_session_ordinal": session_ordinals[report_session],
                        "available_at": eligibility.eligible_at,
                    }
                    detail = "emitted_conservative_censored_earnings"
                except (KeyError, PhysicalPreopenInputError):
                    detail = "earnings_report_session_unresolved"
                    semantically_incomplete_roles.add(role)
        else:
            if eligibility.included:
                output = {
                    "schema": GUIDANCE_INPUT_SCHEMA,
                    "security_id": security.security_id,
                    "eligible_session_ordinal": ordinal,
                    "available_at": eligibility.eligible_at,
                }
                detail = "emitted_conservative_censored_guidance"
        role_name = {
            MassiveSourceRole.ANALYST_RATINGS: "ratings",
            MassiveSourceRole.EARNINGS: "earnings",
            MassiveSourceRole.CORPORATE_GUIDANCE: "guidance",
        }[role]
        disposition = "named_refusal"
        if output is not None:
            encoded = canonical_json_bytes(output)
            if encoded not in seen_role_rows[role_name]:
                rows_by_role[role_name].append(output)
                seen_role_rows[role_name].add(encoded)
                disposition = "emitted"
            else:
                disposition = "coalesced_exact_control_anchor"
        terminals.append(
            _composition_terminal(
                source,
                disposition=disposition,
                reason=detail,
                security_id=security.security_id,
            )
        )
    return (
        rows_by_role,
        universe_sources,
        terminals,
        semantically_incomplete_roles,
    )


def _fundamental_rows(
    loaded: LoadedSharadarCapture,
    securities: Mapping[str, _SecurityCandidate],
    *, first_session: str,
    last_session: str,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    retained: dict[str, list[dict[str, str]]] = defaultdict(list)
    refusals: Counter[str] = Counter()
    earliest = (date.fromisoformat(first_session) - timedelta(days=800)).isoformat()
    source_rows = 0
    retained_fact_count = 0
    for row in _iter_sharadar_rows(loaded, SharadarDataset.FUNDAMENTALS):
        source_rows += 1
        if source_rows > MAX_SCANNED_FUNDAMENTAL_SOURCE_ROWS:
            raise PhysicalPreopenInputError(
                "FUNDAMENTALS exceeds composer source-row bound"
            )
        security = securities.get(row.get("ticker", ""))
        if security is None:
            continue
        try:
            if row.get("dimension") != FUNDAMENTALS_ADMITTED_DIMENSION:
                raise PhysicalPreopenInputError("non-ART fundamental")
            period = _date_text(row.get("calendardate"), "calendardate")
            if period < earliest or period > last_session:
                continue
            filing_date = _date_text(row.get("date"), "date")
            lastupdated = _date_text(row.get("lastupdated"), "lastupdated")
            sharesbas = _decimal_text(
                row.get("sharesbas"), "sharesbas", positive=True
            )
            equity_usd = _decimal_text(row.get("equityusd"), "equityusd")
            revenue_usd = _decimal_text(row.get("revenueusd"), "revenueusd")
        except PhysicalPreopenInputError as exc:
            refusals[str(exc)] += 1
            continue
        retained[security.security_id].append(
            {
                "calendardate": period,
                "filing_date": filing_date,
                "lastupdated": lastupdated,
                "sharesbas": sharesbas,
                "equityusd": equity_usd,
                "revenueusd": revenue_usd,
            }
        )
        retained_fact_count += 1
        if retained_fact_count > MAX_RETAINED_DERIVED_ROWS:
            raise PhysicalPreopenInputError(
                "retained relevant ART facts exceed composer bound"
            )
    output: list[dict[str, object]] = []
    for security_id, facts in retained.items():
        by_period: dict[str, list[dict[str, str]]] = defaultdict(list)
        for fact in facts:
            by_period[fact["calendardate"]].append(fact)
        unique: dict[str, dict[str, str]] = {}
        for period, candidates in by_period.items():
            encoded = {canonical_json_bytes(item) for item in candidates}
            if len(encoded) != 1:
                refusals["conflicting_ART_rows_for_period"] += len(candidates)
                continue
            unique[period] = candidates[0]
        for period in sorted(unique):
            current = unique[period]
            parsed = date.fromisoformat(period)
            try:
                prior_key = parsed.replace(year=parsed.year - 1).isoformat()
            except ValueError:
                refusals["noncomparable_prior_fiscal_year"] += 1
                continue
            prior = unique.get(prior_key)
            if prior is None:
                refusals["missing_comparable_prior_fiscal_year"] += 1
                continue
            available_date = date.fromisoformat(
                max(current["filing_date"], current["lastupdated"])
            ) + timedelta(days=1)
            fact = {
                "schema": FUNDAMENTAL_INPUT_SCHEMA,
                "security_id": security_id,
                "period_end": period,
                # Both Sharadar fields are date-only.  The official table is
                # delivered at 17:30 and 23:30 US Eastern, so noon UTC on the
                # following calendar day is a deterministic conservative
                # availability instant: after both source deliveries and
                # before the next ordinary NYSE open.
                "available_at": f"{available_date.isoformat()}T12:00:00.000000Z",
                "shares_outstanding": _decimal_text(
                    current["sharesbas"], "sharesbas", positive=True
                ),
                "book_equity_usd": _decimal_text(
                    current["equityusd"], "equityusd"
                ),
                "revenue_ttm_usd": _decimal_text(
                    current["revenueusd"], "revenueusd"
                ),
                "prior_fiscal_year_revenue_ttm_usd": _decimal_text(
                    prior["revenueusd"], "prior revenueusd"
                ),
            }
            output.append(fact)
            if len(output) > MAX_RETAINED_DERIVED_ROWS:
                raise PhysicalPreopenInputError(
                    "derived fundamental rows exceed retained bound"
                )
    encoded_output = {canonical_json_bytes(item): item for item in output}
    return [encoded_output[key] for key in sorted(encoded_output)], dict(
        sorted(refusals.items())
    )


def _action_discovery_census(
    loaded: LoadedSharadarCapture,
    target_tickers: set[str],
) -> dict[str, object]:
    counts: Counter[str] = Counter()
    matched = 0
    invalid_action_label_rows = 0
    for row in _iter_sharadar_rows(loaded, SharadarDataset.ACTIONS):
        action = row.get("action")
        ticker = row.get("ticker")
        if (
            type(action) is str
            and action
            and action == action.strip()
            and len(action) <= 128
        ):
            counts[action] += 1
            if len(counts) > MAX_ACTION_VOCABULARY_ENTRIES:
                raise PhysicalPreopenInputError(
                    "ACTIONS vocabulary exceeds reviewed bound"
                )
        else:
            invalid_action_label_rows += 1
        if ticker in target_tickers:
            matched += 1
    return {
        "availability_semantics": ACTIONS_AVAILABILITY,
        "action_counts": dict(sorted(counts.items())),
        "invalid_action_label_row_count": invalid_action_label_rows,
        "target_ticker_discovery_row_count": matched,
        "used_for_identity_or_payoff": False,
    }


def _bounded_artifact(value: object, *, name: str, maximum: int) -> bytes:
    payload = canonical_json_bytes(value)
    if len(payload) > maximum:
        raise PhysicalPreopenInputError(f"{name} exceeds retained byte bound")
    return payload


def _universe_review_candidate(
    securities: Mapping[str, _SecurityCandidate],
    sharadar: LoadedSharadarCapture,
    *,
    sessions: Sequence[str],
) -> tuple[bytes, tuple[str, ...], dict[str, int]]:
    """Compress the full current-snapshot membership proposal without expanding it.

    First/last price dates make the proposal deterministic, but they do not
    retroactively establish what the complete US-common-stock population,
    issuer link, or sector/industry classification was before each open.  The
    interval proposal is therefore retained only for independent review.
    """

    if not sessions:
        raise PhysicalPreopenInputError("formal NYSE session axis is empty")
    difference = [0] * (len(sessions) + 1)
    rows: list[dict[str, object]] = []
    interval_refusals: Counter[str] = Counter()
    seen_security_ids: set[str] = set()
    for security in sorted(securities.values(), key=lambda item: item.security_id):
        if security.security_id in seen_security_ids:
            raise PhysicalPreopenInputError(
                "current-snapshot security identity repeats after collision checks"
            )
        seen_security_ids.add(security.security_id)
        start = max(FORMAL_FIRST_SESSION, security.first_priced_date)
        end = min(
            FORMAL_LAST_SESSION,
            security.last_priced_date or FORMAL_LAST_SESSION,
        )
        first_index = bisect_left(sessions, start)
        last_index_exclusive = bisect_right(sessions, end)
        if first_index >= last_index_exclusive:
            interval_refusals["no_formal_session_intersection"] += 1
            continue
        difference[first_index] += 1
        difference[last_index_exclusive] -= 1
        rows.append(
            {
                "security_id": security.security_id,
                "issuer_id": security.issuer_id,
                "source_composite_figi": security.composite_figi,
                "listing_id": security.listing_id,
                "sharadar_cusip_join_candidates": list(security.cusips),
                "current_snapshot_ticker_display": security.ticker,
                "current_snapshot_listing_exchange": security.exchange_id,
                "current_snapshot_sector_id": security.sector_id,
                "current_snapshot_industry_id": security.industry_id,
                "candidate_first_session": sessions[first_index],
                "candidate_last_session": sessions[last_index_exclusive - 1],
                "source_row_sha256": security.source_row_sha256,
                "identity_evidence_sha256": security.identity_evidence_sha256,
                "classification_evidence_sha256": (
                    security.classification_evidence_sha256
                ),
                "source_snapshot_available_at": sharadar.capture_completed_at,
                "qc_security_id": None,
                "mapping_status": "requires_outcome_free_qc_discovery",
                "membership_status": "review_required_current_snapshot_not_PIT",
                "point_in_time": False,
            }
        )
    if not rows:
        raise PhysicalPreopenInputError(
            "Sharadar current-snapshot candidates do not intersect formal sessions"
        )
    active = 0
    session_counts = []
    expanded_terminal_count = 0
    for index, session in enumerate(sessions):
        active += difference[index]
        expanded_terminal_count += active
        session_counts.append(
            {"decision_session": session, "candidate_member_count": active}
        )
    semantic = {
        "schema": UNIVERSE_ARTIFACT_SCHEMA,
        "status": STATUS_BLOCKED,
        "blocking_refusal": FULL_PIT_UNIVERSE_REFUSAL,
        "sharadar_capture_id": sharadar.capture_id,
        "sharadar_capture_sha256": sharadar.capture_sha256,
        "source_snapshot_available_at": sharadar.capture_completed_at,
        "tickers_availability_semantics": TICKERS_AVAILABILITY,
        "formal_first_session": sessions[0],
        "formal_last_session": sessions[-1],
        "formal_session_count": len(sessions),
        "candidate_security_count": len(rows),
        "candidate_security_session_terminal_count": expanded_terminal_count,
        "candidate_security_rows": rows,
        "candidate_member_count_by_session": session_counts,
        "interval_refusal_counts": dict(sorted(interval_refusals.items())),
        "candidate_listing_exchanges": ["XASE", "XNAS", "XNYS"],
        "candidate_category_filter": sorted(_ALLOWED_COMMON_STOCK_CATEGORIES),
        "membership_interval_inferred_from_current_snapshot": True,
        "US_incorporation_point_in_time_established": False,
        "excluded_instrument_vocabulary_point_in_time_established": False,
        "historical_membership_availability_established": False,
        "historical_classification_availability_established": False,
        "full_market_peer_census_established": False,
        "qc_sid_values_present": False,
        "pristine_point_in_time": False,
        "outcomes_used": False,
    }
    semantic_sha = sha256_bytes(canonical_json_bytes(semantic))
    payload = _bounded_artifact(
        {
            **semantic,
            "artifact_id": f"arv2-universe-review-{semantic_sha[:24]}",
            "semantic_sha256": semantic_sha,
        },
        name="eligible-universe review candidate",
        maximum=MAX_SOURCE_SEED_CANDIDATE_BYTES,
    )
    return payload, tuple(item["security_id"] for item in rows), dict(
        sorted(interval_refusals.items())
    )


def _source_seed_candidate(
    *,
    bridge: MassiveAcceptedRiskBridge,
    rows_by_role: Mapping[str, list[dict[str, object]]],
    terminals: Sequence[dict[str, object]],
    completeness: Mapping[MassiveSourceRole, bool],
) -> bytes:
    normalized_roles = {
        role: [
            json.loads(payload)
            for payload in sorted(canonical_json_bytes(row) for row in rows_by_role[role])
        ]
        for role in ("earnings", "guidance", "ratings")
    }
    terminal_rows = [
        json.loads(payload)
        for payload in sorted(canonical_json_bytes(row) for row in terminals)
    ]
    semantic = {
        "schema": SOURCE_SEED_CANDIDATE_SCHEMA,
        "status": "review_candidate_not_preopen_input_authority",
        "massive_bridge_id": bridge.bridge_id,
        "massive_bridge_sha256": bridge.bridge_sha256,
        "source_view_id": SOURCE_VIEW_ID,
        "role_candidates": normalized_roles,
        "composition_terminals": terminal_rows,
        "role_candidate_counts": {
            role: len(normalized_roles[role]) for role in normalized_roles
        },
        "terminal_count": len(terminal_rows),
        "source_completeness": {
            role.value: completeness[role] for role in MassiveSourceRole
        },
        "caller_authored_completeness_accepted": False,
        "point_in_time_claimed": False,
        "outcomes_used": False,
    }
    semantic_sha = sha256_bytes(canonical_json_bytes(semantic))
    return _bounded_artifact(
        {
            **semantic,
            "artifact_id": f"arv2-source-seed-review-{semantic_sha[:24]}",
            "semantic_sha256": semantic_sha,
        },
        name="accepted-risk source seed candidate",
        maximum=MAX_SOURCE_SEED_CANDIDATE_BYTES,
    )


def _fundamental_seed_inventory(
    sharadar: LoadedSharadarCapture,
    rows: Sequence[dict[str, object]],
    refusal_counts: Mapping[str, int],
) -> bytes:
    row_payloads = sorted(canonical_json_bytes(row) for row in rows)
    normalized_rows = [json.loads(payload) for payload in row_payloads]
    semantic = {
        "schema": FUNDAMENTAL_SEED_INVENTORY_SCHEMA,
        "status": "deterministic_seed_inventory_not_preopen_input_authority",
        "sharadar_capture_id": sharadar.capture_id,
        "sharadar_capture_sha256": sharadar.capture_sha256,
        "availability_semantics": FUNDAMENTAL_SEED_AVAILABILITY,
        "source_availability_semantics": FUNDAMENTALS_AVAILABILITY,
        "seed_count": len(row_payloads),
        "seed_projection_sha256": sha256_bytes(b"".join(row_payloads)),
        "seed_rows": normalized_rows,
        "refusal_counts": dict(sorted(refusal_counts.items())),
        "caller_authored_PIT_claim_accepted": False,
        "outcomes_used": False,
    }
    semantic_sha = sha256_bytes(canonical_json_bytes(semantic))
    return _bounded_artifact(
        {
            **semantic,
            "artifact_id": f"arv2-fundamental-seeds-{semantic_sha[:24]}",
            "semantic_sha256": semantic_sha,
        },
        name="fundamental seed candidate",
        maximum=MAX_SOURCE_SEED_CANDIDATE_BYTES,
    )


def _candidate_record(
    *,
    bridge: MassiveAcceptedRiskBridge,
    sharadar: LoadedSharadarCapture,
    first_session: str,
    last_session: str,
    calculation_session: str,
    blocking_refusals: tuple[str, ...],
    firm_bytes: bytes,
    report_bytes: bytes,
    universe_bytes: bytes,
    source_seed_bytes: bytes,
    fundamental_inventory_bytes: bytes,
    quality_bytes: bytes,
    completeness: Mapping[MassiveSourceRole, bool],
) -> dict[str, object]:
    return {
        "schema": COMPOSER_SCHEMA,
        "status": STATUS_BLOCKED,
        "massive_bridge_id": bridge.bridge_id,
        "massive_bridge_sha256": bridge.bridge_sha256,
        "pair_id": bridge.pair.pair_id,
        "pair_sha256": bridge.pair.pair_sha256,
        "derived_capture_id": bridge.derived_capture_id,
        "derived_capture_sha256": bridge.derived_capture_sha256,
        "sharadar_capture_id": sharadar.capture_id,
        "sharadar_capture_sha256": sharadar.capture_sha256,
        "first_session": first_session,
        "last_session": last_session,
        "calculation_session": calculation_session,
        "blocking_refusals": list(blocking_refusals),
        "closed_input_manifest_sha256": None,
        "run_authority_candidate_sha256": None,
        "firm_review_candidate_sha256": sha256_bytes(firm_bytes),
        "composition_report_sha256": sha256_bytes(report_bytes),
        "eligible_universe_artifact_sha256": sha256_bytes(universe_bytes),
        "source_seed_candidate_sha256": sha256_bytes(source_seed_bytes),
        "fundamental_seed_inventory_sha256": sha256_bytes(
            fundamental_inventory_bytes
        ),
        "quality_policy_sha256": sha256_bytes(quality_bytes),
        "rating_source_complete_for_frozen_query_and_accepted_risk_policy": (
            completeness[MassiveSourceRole.ANALYST_RATINGS]
        ),
        "earnings_source_complete_for_frozen_query_and_accepted_risk_policy": (
            completeness[MassiveSourceRole.EARNINGS]
        ),
        "guidance_source_complete_for_frozen_query_and_accepted_risk_policy": (
            completeness[MassiveSourceRole.CORPORATE_GUIDANCE]
        ),
        "firm_ontology_reviewed": False,
        "sharadar_tickers_pristine_point_in_time": False,
        "full_pit_universe_established": False,
        "full_market_peer_census_established": False,
        "six_preopen_roles_produced": False,
        "production_preopen_input_available": False,
        "actions_used_for_identity_or_payoff": False,
        "outcome_access_performed": False,
        "quantconnect_io_performed": False,
    }


def build_physical_preopen_input_candidate(
    bridge: MassiveAcceptedRiskBridge,
    sharadar_capture: LoadedSharadarCapture,
) -> PhysicalPreopenInputCandidate:
    """Build an authenticated physical review/refusal candidate.

    The public entry point deliberately has no parameters with which a caller
    could assert completeness, point-in-time status, QC SID identity, or an
    authority waiver.  With the supported current-snapshot TICKERS source, a
    production manifest is impossible by construction.
    """

    try:
        bridge = require_massive_accepted_risk_bridge(bridge)
    except MassiveInputPairBridgeError as exc:
        raise PhysicalPreopenInputError(
            "Massive bridge failed authority revalidation"
        ) from exc
    sharadar = _reauthenticated_sharadar(sharadar_capture)
    completeness = _source_completeness(bridge)
    firm_bytes, _firm_binding = _firm_review_candidate(bridge)
    quality_bytes = _quality_policy_bytes()
    securities, ticker_refusals, ticker_census = _ticker_candidates(sharadar)
    if not securities:
        raise PhysicalPreopenInputError(
            "Sharadar snapshot has no unique admissible identity candidates"
        )

    session_ordinals, session_set = _session_axis(FORMAL_LAST_SESSION)
    formal_sessions = tuple(
        item
        for item in sorted(session_ordinals)
        if FORMAL_FIRST_SESSION <= item <= FORMAL_LAST_SESSION
    )
    if (
        not formal_sessions
        or formal_sessions[0] != FORMAL_FIRST_SESSION
        or formal_sessions[-1] != FORMAL_LAST_SESSION
    ):
        raise PhysicalPreopenInputError("formal NYSE session endpoints changed")

    source_roles, rating_sessions, terminals, semantic_incomplete = _source_rows(
        bridge,
        securities,
        session_ordinals=session_ordinals,
        session_set=session_set,
    )
    for role in semantic_incomplete:
        completeness[role] = False

    universe_bytes, universe_security_ids, universe_interval_refusals = (
        _universe_review_candidate(
            securities,
            sharadar,
            sessions=formal_sessions,
        )
    )
    universe_ids = set(universe_security_ids)
    universe_securities = {
        ticker: security
        for ticker, security in securities.items()
        if security.security_id in universe_ids
    }
    if len(universe_securities) > MAX_RETAINED_TARGET_SECURITIES:
        raise PhysicalPreopenInputError(
            "current-snapshot universe candidate exceeds retained security bound"
        )

    fundamentals, fundamental_refusals = _fundamental_rows(
        sharadar,
        universe_securities,
        first_session=FORMAL_FIRST_SESSION,
        last_session=FORMAL_LAST_SESSION,
    )
    fundamental_inventory_bytes = _fundamental_seed_inventory(
        sharadar, fundamentals, fundamental_refusals
    )
    source_seed_bytes = _source_seed_candidate(
        bridge=bridge,
        rows_by_role=source_roles,
        terminals=terminals,
        completeness=completeness,
    )
    actions = _action_discovery_census(sharadar, set(universe_securities))
    universe_record = strict_json_loads(
        decode_utf8(universe_bytes, "eligible-universe review candidate"),
        "eligible-universe review candidate",
    )
    if type(universe_record) is not dict:
        raise PhysicalPreopenInputError(
            "eligible-universe review candidate is not an object"
        )

    blocking = [FULL_PIT_UNIVERSE_REFUSAL, FIRM_ONTOLOGY_REFUSAL]
    blocking.extend(
        f"{role.value}_source_not_complete_for_frozen_query_and_accepted_risk_policy"
        for role in MassiveSourceRole
        if completeness[role] is not True
    )
    blocking_refusals = tuple(blocking)
    disposition_counts = Counter(
        item["preopen_composition_disposition"] for item in terminals
    )
    report = {
        "schema": COMPOSITION_REPORT_SCHEMA,
        "status": STATUS_BLOCKED,
        "blocking_refusals": list(blocking_refusals),
        "massive_bridge_id": bridge.bridge_id,
        "massive_bridge_sha256": bridge.bridge_sha256,
        "pair_id": bridge.pair.pair_id,
        "pair_sha256": bridge.pair.pair_sha256,
        "derived_capture_id": bridge.derived_capture_id,
        "derived_capture_sha256": bridge.derived_capture_sha256,
        "sharadar_capture_id": sharadar.capture_id,
        "sharadar_capture_sha256": sharadar.capture_sha256,
        "fixed_capture_range": [
            FROZEN_CAPTURE_FIRST_DATE,
            FROZEN_CAPTURE_LAST_DATE,
        ],
        "formal_filter_range": [FORMAL_FIRST_SESSION, FORMAL_LAST_SESSION],
        "source_completeness_semantics": (
            "complete_for_exact_frozen_event_date_query_and_accepted_risk_"
            "policy_only_never_pristine_or_complete_version_history"
        ),
        "source_completeness": {
            role.value: completeness[role] for role in MassiveSourceRole
        },
        "massive_source_row_count": len(bridge.pair.rows),
        "massive_composition_terminal_count": len(terminals),
        "massive_composition_terminal_projection_sha256": sha256_bytes(
            canonical_json_bytes(list(terminals))
        ),
        "composition_disposition_counts": dict(sorted(disposition_counts.items())),
        "rating_current_view_security_session_candidate_count": len(
            rating_sessions
        ),
        "rating_current_view_security_session_projection_sha256": sha256_bytes(
            canonical_json_bytes(
                [
                    {
                        "security_id": security_id,
                        "decision_session": session,
                        "raw_row_sha256": raw_hash,
                    }
                    for (security_id, session), raw_hash in sorted(
                        rating_sessions.items()
                    )
                ]
            )
        ),
        "ticker_candidate_refusal_counts": ticker_census,
        "ticker_ambiguity_count": len(ticker_refusals),
        "universe_interval_refusal_counts": universe_interval_refusals,
        "current_snapshot_universe_security_count": len(universe_security_ids),
        "current_snapshot_security_session_candidate_count": universe_record[
            "candidate_security_session_terminal_count"
        ],
        "fundamental_seed_count": len(fundamentals),
        "fundamental_refusal_counts": fundamental_refusals,
        "action_discovery_census": actions,
        "preopen_role_status": {
            "universe": "blocked_full_PIT_security_session_census_unavailable",
            "sid_mapping": (
                "current_snapshot_null_QC_SID_discovery_candidates_only"
            ),
            "fundamentals": "deterministic_ART_seed_inventory_only",
            "earnings": "accepted_risk_seed_review_candidate_only",
            "guidance": "accepted_risk_seed_review_candidate_only",
            "ratings": "accepted_risk_seed_review_candidate_only",
        },
        "source_seed_candidate_sha256": sha256_bytes(source_seed_bytes),
        "fundamental_seed_inventory_sha256": sha256_bytes(
            fundamental_inventory_bytes
        ),
        "firm_review_candidate_sha256": sha256_bytes(firm_bytes),
        "eligible_universe_artifact_sha256": sha256_bytes(universe_bytes),
        "q_data_policy_sha256": sha256_bytes(quality_bytes),
        "q_data_value_until_reviewed_identity_and_firm_evidence": "0",
        "firm_ontology_status": "review_required_not_authority",
        "firm_ontology_order_inferred": False,
        "tickers_availability_semantics": TICKERS_AVAILABILITY,
        "fundamentals_availability_semantics": FUNDAMENTAL_SEED_AVAILABILITY,
        "sharadar_fundamentals_source_availability_semantics": (
            FUNDAMENTALS_AVAILABILITY
        ),
        "actions_availability_semantics": ACTIONS_AVAILABILITY,
        "historical_membership_availability_established": False,
        "historical_classification_availability_established": False,
        "full_pit_universe_established": False,
        "full_market_peer_census_established": False,
        "qc_sid_values_present": False,
        "six_preopen_roles_produced": False,
        "closed_input_manifest_constructed": False,
        "run_authority_candidate_constructed": False,
        "production_preopen_input_available": False,
        "pristine_point_in_time": False,
        "outcome_access_performed": False,
        "quantconnect_io_performed": False,
    }
    report_bytes = canonical_json_bytes(report)
    calculation_session = resolve_nth_session_after(FORMAL_LAST_SESSION, 1)
    record = _candidate_record(
        bridge=bridge,
        sharadar=sharadar,
        first_session=FORMAL_FIRST_SESSION,
        last_session=FORMAL_LAST_SESSION,
        calculation_session=calculation_session,
        blocking_refusals=blocking_refusals,
        firm_bytes=firm_bytes,
        report_bytes=report_bytes,
        universe_bytes=universe_bytes,
        source_seed_bytes=source_seed_bytes,
        fundamental_inventory_bytes=fundamental_inventory_bytes,
        quality_bytes=quality_bytes,
        completeness=completeness,
    )
    digest = sha256_bytes(canonical_json_bytes(record))
    candidate = object.__new__(PhysicalPreopenInputCandidate)
    values: dict[str, object] = {
        "schema": COMPOSER_SCHEMA,
        "status": STATUS_BLOCKED,
        "candidate_id": f"arv2-physical-preopen-input-{digest[:24]}",
        "candidate_sha256": digest,
        "massive_bridge_id": bridge.bridge_id,
        "massive_bridge_sha256": bridge.bridge_sha256,
        "pair_id": bridge.pair.pair_id,
        "pair_sha256": bridge.pair.pair_sha256,
        "derived_capture_id": bridge.derived_capture_id,
        "derived_capture_sha256": bridge.derived_capture_sha256,
        "sharadar_capture_id": sharadar.capture_id,
        "sharadar_capture_sha256": sharadar.capture_sha256,
        "first_session": FORMAL_FIRST_SESSION,
        "last_session": FORMAL_LAST_SESSION,
        "calculation_session": calculation_session,
        "blocking_refusals": blocking_refusals,
        "closed_input_manifest_bytes": None,
        "run_authority_candidate_bytes": None,
        "firm_review_candidate_bytes": firm_bytes,
        "composition_report_bytes": report_bytes,
        "eligible_universe_artifact_bytes": universe_bytes,
        "source_seed_candidate_bytes": source_seed_bytes,
        "fundamental_seed_inventory_bytes": fundamental_inventory_bytes,
        "quality_policy_bytes": quality_bytes,
        "rating_source_complete_for_frozen_query_and_accepted_risk_policy": (
            completeness[MassiveSourceRole.ANALYST_RATINGS]
        ),
        "earnings_source_complete_for_frozen_query_and_accepted_risk_policy": (
            completeness[MassiveSourceRole.EARNINGS]
        ),
        "guidance_source_complete_for_frozen_query_and_accepted_risk_policy": (
            completeness[MassiveSourceRole.CORPORATE_GUIDANCE]
        ),
        "firm_ontology_reviewed": False,
        "sharadar_tickers_pristine_point_in_time": False,
        "full_pit_universe_established": False,
        "full_market_peer_census_established": False,
        "six_preopen_roles_produced": False,
        "production_preopen_input_available": False,
        "actions_used_for_identity_or_payoff": False,
        "outcome_access_performed": False,
        "quantconnect_io_performed": False,
    }
    if set(values) != {field.name for field in dataclasses.fields(candidate)}:
        raise PhysicalPreopenInputError("candidate field inventory changed")
    for name, item in values.items():
        object.__setattr__(candidate, name, item)
    identity = id(candidate)
    reference = weakref.ref(candidate, lambda ref, key=identity: _forget(key, ref))
    with _AUTHORITIES_LOCK:
        _AUTHORITIES[identity] = (reference, _fingerprint(candidate))
    return require_physical_preopen_input_candidate(candidate)


def require_physical_preopen_input_candidate(
    value: PhysicalPreopenInputCandidate,
) -> PhysicalPreopenInputCandidate:
    if type(value) is not PhysicalPreopenInputCandidate:
        raise PhysicalPreopenInputError("pre-open candidate type changed")
    with _AUTHORITIES_LOCK:
        registered = _AUTHORITIES.get(id(value))
    if (
        registered is None
        or registered[0]() is not value
        or registered[1] != _fingerprint(value)
    ):
        raise PhysicalPreopenInputError("pre-open candidate lost builder authority")
    exact_false = (
        value.firm_ontology_reviewed,
        value.sharadar_tickers_pristine_point_in_time,
        value.full_pit_universe_established,
        value.full_market_peer_census_established,
        value.six_preopen_roles_produced,
        value.production_preopen_input_available,
        value.actions_used_for_identity_or_payoff,
        value.outcome_access_performed,
        value.quantconnect_io_performed,
    )
    if (
        value.schema != COMPOSER_SCHEMA
        or value.status != STATUS_BLOCKED
        or value.candidate_id
        != f"arv2-physical-preopen-input-{value.candidate_sha256[:24]}"
        or type(value.blocking_refusals) is not tuple
        or value.blocking_refusals[:2]
        != (FULL_PIT_UNIVERSE_REFUSAL, FIRM_ONTOLOGY_REFUSAL)
        or len(set(value.blocking_refusals)) != len(value.blocking_refusals)
        or value.closed_input_manifest_bytes is not None
        or value.run_authority_candidate_bytes is not None
        or any(type(item) is not bool or item is not False for item in exact_false)
    ):
        raise PhysicalPreopenInputError("pre-open candidate boundary changed")
    completeness = {
        MassiveSourceRole.ANALYST_RATINGS: (
            value.rating_source_complete_for_frozen_query_and_accepted_risk_policy
        ),
        MassiveSourceRole.EARNINGS: (
            value.earnings_source_complete_for_frozen_query_and_accepted_risk_policy
        ),
        MassiveSourceRole.CORPORATE_GUIDANCE: (
            value.guidance_source_complete_for_frozen_query_and_accepted_risk_policy
        ),
    }
    if any(type(item) is not bool for item in completeness.values()):
        raise PhysicalPreopenInputError("source-completeness type changed")
    candidate_record = {
        "schema": value.schema,
        "status": value.status,
        "massive_bridge_id": value.massive_bridge_id,
        "massive_bridge_sha256": value.massive_bridge_sha256,
        "pair_id": value.pair_id,
        "pair_sha256": value.pair_sha256,
        "derived_capture_id": value.derived_capture_id,
        "derived_capture_sha256": value.derived_capture_sha256,
        "sharadar_capture_id": value.sharadar_capture_id,
        "sharadar_capture_sha256": value.sharadar_capture_sha256,
        "first_session": value.first_session,
        "last_session": value.last_session,
        "calculation_session": value.calculation_session,
        "blocking_refusals": list(value.blocking_refusals),
        "closed_input_manifest_sha256": None,
        "run_authority_candidate_sha256": None,
        "firm_review_candidate_sha256": sha256_bytes(
            value.firm_review_candidate_bytes
        ),
        "composition_report_sha256": sha256_bytes(value.composition_report_bytes),
        "eligible_universe_artifact_sha256": sha256_bytes(
            value.eligible_universe_artifact_bytes
        ),
        "source_seed_candidate_sha256": sha256_bytes(
            value.source_seed_candidate_bytes
        ),
        "fundamental_seed_inventory_sha256": sha256_bytes(
            value.fundamental_seed_inventory_bytes
        ),
        "quality_policy_sha256": sha256_bytes(value.quality_policy_bytes),
        "rating_source_complete_for_frozen_query_and_accepted_risk_policy": (
            value.rating_source_complete_for_frozen_query_and_accepted_risk_policy
        ),
        "earnings_source_complete_for_frozen_query_and_accepted_risk_policy": (
            value.earnings_source_complete_for_frozen_query_and_accepted_risk_policy
        ),
        "guidance_source_complete_for_frozen_query_and_accepted_risk_policy": (
            value.guidance_source_complete_for_frozen_query_and_accepted_risk_policy
        ),
        "firm_ontology_reviewed": value.firm_ontology_reviewed,
        "sharadar_tickers_pristine_point_in_time": (
            value.sharadar_tickers_pristine_point_in_time
        ),
        "full_pit_universe_established": value.full_pit_universe_established,
        "full_market_peer_census_established": (
            value.full_market_peer_census_established
        ),
        "six_preopen_roles_produced": value.six_preopen_roles_produced,
        "production_preopen_input_available": (
            value.production_preopen_input_available
        ),
        "actions_used_for_identity_or_payoff": (
            value.actions_used_for_identity_or_payoff
        ),
        "outcome_access_performed": value.outcome_access_performed,
        "quantconnect_io_performed": value.quantconnect_io_performed,
    }
    if sha256_bytes(canonical_json_bytes(candidate_record)) != value.candidate_sha256:
        raise PhysicalPreopenInputError("pre-open candidate identity changed")
    return value

__all__ = [
    "COMPOSER_SCHEMA",
    "FIRM_ONTOLOGY_REFUSAL",
    "FIRM_REVIEW_SCHEMA",
    "FORMAL_FIRST_SESSION",
    "FORMAL_LAST_SESSION",
    "FULL_PIT_UNIVERSE_REFUSAL",
    "PhysicalPreopenInputCandidate",
    "PhysicalPreopenInputError",
    "STATUS_BLOCKED",
    "build_physical_preopen_input_candidate",
    "require_physical_preopen_input_candidate",
]
