"""Bounded private current Sharadar identity census for seven price inputs.

Two filtered TICKERS GETs retain current stock/fund metadata, not a historical
security master. Every requested name remains a current candidate or a named
refusal; no QC SID, original availability, independent identity, formal source,
decision, order, deployment or trading authority is created. Import is inert.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import io
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import scripts.capture_arv2_sharadar as source
import scripts.capture_arv2_sharadar_prices as prices
from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError, canonical_json_bytes, parse_utc_timestamp,
    require_canonical_json_bytes, require_sha256, sha256_bytes,
)

SharadarIdentityCaptureError = source.SharadarCaptureError
SCHEMA = "arv2-sharadar-seven-current-identities-v1"
SCHEMA_WITHOUT_FIGI = "arv2-sharadar-seven-current-identities-v2"
SCHEMA_STRICT_CUSIPS = "arv2-sharadar-seven-current-identities-v3"
PRODUCTION_TRANSPORT = "sharadar_current_identities_direct_https_owned_session"
TEST_TRANSPORT = "offline_test_double"
DEFAULT_ARTIFACT_ROOT = (
    source.REPOSITORY_ARTIFACTS_ROOT / "analyst_revisions_v2" / "sharadar_identity_capture"
)
PRICE_ARTIFACT_PATH = (
    prices.DEFAULT_ARTIFACT_ROOT / "arv2-sharadar-prices-20261007T164730430845Z"
)
PRICE_MANIFEST_SHA256 = "2f5d71683a43d1118420c52677fcbb6bdd539c7c621004b4632beed9b03f6702"
PRICE_CLOSE_SESSION = "2026-10-06"
FIELDS = (
    "table", "ticker", "permaticker", "name", "exchange", "isdelisted",
    "category", "figi", "cusips", "currency", "firstadded", "firstpricedate",
    "lastpricedate", "lastupdated",
)
FIELDS_WITHOUT_FIGI = tuple(field for field in FIELDS if field != "figi")
ROLE_TICKERS = prices.ROLE_TICKERS
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 256 * 1024
MAX_FIELD_CHARS = 1024
REQUEST_ROW_LIMIT = 100
TIMEOUT_SECONDS = 60
_PERMANENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")
_FIGI = re.compile(r"[A-Z0-9]{12}")
_CUSIP = re.compile(r"[A-Z0-9]{9}")
_CUSIP_COLLISION_TOKEN = re.compile(r"(?<![A-Za-z0-9])[A-Z0-9]{9}(?![A-Za-z0-9])")
_ARTIFACT_ID = re.compile(r"arv2-sharadar-identities-\d{8}T\d{12}Z")
_COMMON_CATEGORIES = frozenset({
    "domestic common stock", "domestic common stock primary class",
    "domestic common stock secondary class",
})
_STOCK_EXCHANGES = frozenset({
    "NASDAQ", "NYSE", "AMEX", "NYSEMKT", "NYSE MKT", "NYSEAMERICAN", "NYSE AMERICAN",
})
_FUND_EXCHANGES = _STOCK_EXCHANGES | {"NYSEARCA", "NYSE ARCA", "BATS"}
FALSE_FLAGS = prices.FALSE_FLAGS + (
    "qc_sid_resolved", "historical_identity_authenticated", "independently_reviewed",
    "price_identity_binding_independently_authenticated", "validity_intervals_authenticated",
)


@dataclasses.dataclass(frozen=True)
class CurrentIdentityDisposition:
    ticker: str
    price_role: str
    status: str
    source_row_count: int
    source_row_sha256s: tuple[str, ...]
    permanent_share_class_id: str | None = dataclasses.field(repr=False)
    composite_figi: str | None = dataclasses.field(repr=False)
    issuer_name: str | None = dataclasses.field(repr=False)
    category: str | None = dataclasses.field(repr=False)
    exchange: str | None = dataclasses.field(repr=False)
    currency: str | None = dataclasses.field(repr=False)
    cusip_candidates: tuple[str, ...] = dataclasses.field(repr=False)
    first_added_date: str | None = dataclasses.field(repr=False)
    first_price_date: str | None = dataclasses.field(repr=False)
    last_price_date: str | None = dataclasses.field(repr=False)
    metadata_updated_date: str | None = dataclasses.field(repr=False)
    refusal_codes: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class IdentityCsvBinding:
    role: str
    csv_file: str
    csv_sha256: str
    csv_byte_count: int
    row_count: int


@dataclasses.dataclass(frozen=True)
class LoadedSharadarIdentityCapture:
    artifact_path: Path
    manifest_sha256: str
    capture_sha256: str
    capture_transport: str
    capture_started_at: str
    capture_completed_at: str
    price_manifest_sha256: str
    price_capture_sha256: str
    price_close_session: str
    responses: tuple[IdentityCsvBinding, ...]
    identities: tuple[CurrentIdentityDisposition, ...]
    manifest_schema: str = SCHEMA
    requested_fields: tuple[str, ...] = FIELDS

    @property
    def matched_count(self) -> int:
        return sum(row.status == "matched_current_candidate" for row in self.identities)

    @property
    def refused_count(self) -> int:
        return len(self.identities) - self.matched_count


@dataclasses.dataclass(frozen=True)
class StockHeaderDiagnostic:
    schema: str
    header_fields: tuple[str, ...]
    body_byte_count: int
    body_sha256: str
    request_query_sha256: str
    client_started_at: str
    client_completed_at: str
    body_persisted: bool = False
    source_capture_published: bool = False
    point_in_time_proven: bool = False
    formal_source_admitted: bool = False
    decision_ready: bool = False
    orders_enabled: bool = False


def _fields(schema: str) -> tuple[str, ...]:
    if type(schema) is not str or schema not in (SCHEMA, SCHEMA_WITHOUT_FIGI, SCHEMA_STRICT_CUSIPS):
        raise SharadarIdentityCaptureError("identity schema profile is not supported")
    return FIELDS_WITHOUT_FIGI if schema == SCHEMA_WITHOUT_FIGI else FIELDS


def _query(role: str, *, schema: str = SCHEMA) -> dict[str, str]:
    fields = _fields(schema)
    return {
        "format": "csv", "table": role,
        "ticker": ",".join(dict(ROLE_TICKERS)[role]), "fields": ",".join(fields),
        "sort": "ticker.asc", "skip": "0", "limit": str(REQUEST_ROW_LIMIT),
    }


def _price_binding(
    artifact_path: Path, expected_manifest_sha256: str, *, synthetic: bool,
) -> dict[str, object]:
    loaded = prices.load_sharadar_price_capture(
        artifact_path, expected_manifest_sha256=expected_manifest_sha256,
    )
    expected_transport = prices.TEST_TRANSPORT if synthetic else prices.PRODUCTION_TRANSPORT
    if loaded.capture_transport != expected_transport or loaded.close_session != PRICE_CLOSE_SESSION:
        raise SharadarIdentityCaptureError("bound price capture transport/session is not permitted")
    if not synthetic and loaded.manifest_sha256 != PRICE_MANIFEST_SHA256:
        raise SharadarIdentityCaptureError("production price capture differs from the frozen manifest")
    if tuple((row.role, row.row_count) for row in loaded.responses) != (("stocks", 1), ("funds", 6)):
        raise SharadarIdentityCaptureError("bound price capture lacks the frozen seven-name census")
    return {
        "price_manifest_sha256": loaded.manifest_sha256,
        "price_capture_sha256": loaded.capture_sha256,
        "price_artifact_id": loaded.artifact_path.name,
        "price_close_session": loaded.close_session,
        "price_capture_transport": loaded.capture_transport,
        "price_responses": [dataclasses.asdict(row) for row in loaded.responses],
    }


def _parse_csv(payload: bytes, role: str, *, schema: str = SCHEMA) -> tuple[dict[str, str], ...]:
    fields = _fields(schema)
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_RESPONSE_BYTES:
        raise SharadarIdentityCaptureError("identity CSV exceeds the bounded byte contract")
    try:
        text = payload.decode("utf-8-sig", errors="strict")
    except UnicodeError:
        raise SharadarIdentityCaptureError("identity CSV is not strict UTF-8") from None
    if "\x00" in text:
        raise SharadarIdentityCaptureError("identity CSV contains a forbidden control byte")
    expected = set(dict(ROLE_TICKERS)[role])
    observed: list[dict[str, str]] = []
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = tuple(next(reader, ()))
        if len(header) != len(fields) or set(header) != set(fields):
            raise SharadarIdentityCaptureError("identity CSV header differs from frozen fields")
        for values in reader:
            if len(observed) + 1 >= REQUEST_ROW_LIMIT:
                raise SharadarIdentityCaptureError("identity CSV reached the request row limit")
            if len(values) != len(fields) or any(
                len(value) > MAX_FIELD_CHARS
                or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
                for value in values
            ):
                raise SharadarIdentityCaptureError("identity CSV row shape is malformed")
            row = dict(zip(header, values, strict=True))
            if row["ticker"] not in expected:
                raise SharadarIdentityCaptureError("identity CSV escaped the frozen ticker scope")
            observed.append(row)
    except csv.Error:
        raise SharadarIdentityCaptureError("identity CSV cannot be parsed safely") from None
    # Header-only/duplicate responses are retained as named census refusals.
    return tuple(observed)


def _bounded_response_bytes(session: object, role: str, key: str, *, schema: str = SCHEMA) -> bytes:
    endpoint = source.BASE_URL + "/v1.0/data/tickers"
    params = {**_query(role, schema=schema), "api_key": key}
    response = None
    try:
        response = session.get(
            endpoint, params=params, timeout=TIMEOUT_SECONDS, allow_redirects=False,
            stream=True, verify=True, headers={"Accept-Encoding": "identity"},
        )
        prices._validate_response_identity(response, endpoint, params)
        encoding = response.headers.get("Content-Encoding")
        if encoding is not None and (type(encoding) is not str or encoding.casefold() != "identity"):
            raise SharadarIdentityCaptureError("identity response used unsupported content encoding")
        length = response.headers.get("Content-Length")
        if length is not None and (
            type(length) is not str or not length.isascii() or not length.isdecimal()
            or not 0 < int(length) <= MAX_RESPONSE_BYTES
        ):
            raise SharadarIdentityCaptureError("identity response length is malformed or excessive")
        size = 0
        chunks: list[bytes] = []
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if type(chunk) is not bytes:
                raise SharadarIdentityCaptureError("identity response did not stream bytes")
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise SharadarIdentityCaptureError("identity response exceeds byte limit")
            chunks.append(chunk)
        payload = b"".join(chunks)
        if length is not None and len(payload) != int(length):
            raise SharadarIdentityCaptureError("identity response length differs from header")
        if any(encoded in payload for encoded in source._credential_encodings(key)):
            raise SharadarIdentityCaptureError("provider echoed a credential; refusing persistence")
        return payload
    except SharadarIdentityCaptureError:
        raise
    except Exception:
        raise SharadarIdentityCaptureError("identity provider request failed; details redacted") from None
    finally:
        if response is not None:
            source._close_response(response)


def _response_bytes(session: object, role: str, key: str, *, schema: str = SCHEMA) -> bytes:
    payload = _bounded_response_bytes(session, role, key, schema=schema)
    _parse_csv(payload, role, schema=schema)
    return payload


def _stock_header(payload: bytes) -> tuple[str, ...]:
    """Inspect the first CSV record only; never parse or expose data records."""
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_RESPONSE_BYTES:
        raise SharadarIdentityCaptureError("stock header response violates byte bound")
    try:
        text = payload.decode("utf-8-sig", errors="strict")
        header = tuple(next(csv.reader(io.StringIO(text, newline=""), strict=True), ()))
    except (UnicodeError, csv.Error):
        raise SharadarIdentityCaptureError("stock header is not strict UTF-8 CSV") from None
    if (not 1 <= len(header) <= 64 or len(set(header)) != len(header)
            or any(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name) is None for name in header)):
        raise SharadarIdentityCaptureError("stock header fields are not bounded unique schema names")
    return header


def _inspect_stock_header_core(
    session: object, key: str, clock: Callable[[], datetime], *, close_owned_session: bool,
) -> StockHeaderDiagnostic:
    try:
        started = source._now_utc(clock)
        payload = _bounded_response_bytes(session, "stocks", key)
        header = _stock_header(payload)
        if close_owned_session:
            try:
                session.close()
            except Exception:
                raise SharadarIdentityCaptureError("owned header session closure failed; details redacted") from None
        completed = source._now_utc(clock)
        if parse_utc_timestamp(completed, "completed") < parse_utc_timestamp(started, "started"):
            raise SharadarIdentityCaptureError("stock header diagnostic clock moved backwards")
        return StockHeaderDiagnostic(
            "arv2-sharadar-stock-header-diagnostic-v1", header, len(payload), sha256_bytes(payload),
            sha256_bytes(canonical_json_bytes(_query("stocks"))), started, completed,
        )
    except SharadarIdentityCaptureError:
        raise
    except Exception:
        raise SharadarIdentityCaptureError("stock header diagnostic failed; details redacted") from None
    finally:
        if close_owned_session:
            try:
                session.close()
            except Exception:
                pass


def _date(value: str) -> str | None:
    try:
        return prices._session_date(value)
    except SharadarIdentityCaptureError:
        return None


def _cusips(value: str) -> tuple[str, ...] | None:
    """Frozen v1/v2 interpretation; historical manifests must still reproduce."""
    if not value:
        return None
    parts = tuple(part.strip() for part in value.split(","))
    if any(_CUSIP.fullmatch(part) is None for part in parts) or len(set(parts)) != len(parts):
        return None
    return tuple(sorted(parts))


def _strict_cusips(value: str) -> tuple[str, ...] | None:
    """Prospective v3 admission accepts exact comma-separated shape tokens only."""
    parts = tuple(value.split(","))
    if any(_CUSIP.fullmatch(part) is None for part in parts) or len(set(parts)) != len(parts):
        return None
    return tuple(sorted(parts))


def _cusip_collision_tokens(value: str) -> tuple[str, ...]:
    """Refusal-only tokens: never repair a field or admit an extracted candidate.

    Exact nine-character tokens bounded by non-ASCII-alphanumeric characters
    still poison cross-name ownership when the surrounding field is malformed.
    Shape matches are not checksum or independent identity verification.
    """
    return tuple(sorted(set(_CUSIP_COLLISION_TOKEN.findall(value))))


def _census(
    role_rows: tuple[tuple[str, tuple[dict[str, str], ...]], ...],
    *, schema: str = SCHEMA,
) -> tuple[CurrentIdentityDisposition, ...]:
    _fields(schema)
    parse_cusips = _strict_cusips if schema == SCHEMA_STRICT_CUSIPS else _cusips
    rows_by_ticker: dict[str, list[dict[str, str]]] = defaultdict(list)
    roles = {ticker: role for role, tickers in ROLE_TICKERS for ticker in tickers}
    for role, rows in role_rows:
        for row in rows:
            if roles.get(row["ticker"]) != role:
                raise SharadarIdentityCaptureError("identity census role/ticker binding changed")
            rows_by_ticker[row["ticker"]].append(row)
    reasons: dict[str, set[str]] = {ticker: set() for ticker in roles}
    for field, pattern, reason in (
        ("permaticker", _PERMANENT_ID, "CROSS_NAME_PERMANENT_ID_COLLISION"),
        ("figi", _FIGI, "CROSS_NAME_FIGI_COLLISION"),
    ):
        owners: dict[str, set[str]] = defaultdict(set)
        for ticker, rows in rows_by_ticker.items():
            for row in rows:
                if pattern.fullmatch(row.get(field, "")) is not None:
                    owners[row[field]].add(ticker)
        for members in owners.values():
            if len(members) > 1:
                for ticker in members:
                    reasons[ticker].add(reason)
                    if {roles[name] for name in members} == {"stocks", "funds"}:
                        reasons[ticker].add("DIRECT_STOCK_OWN_ETF_IDENTITY_COLLISION")
    cusip_owners: dict[str, set[str]] = defaultdict(set)
    for ticker, rows in rows_by_ticker.items():
        for row in rows:
            tokens = (_cusip_collision_tokens(row["cusips"]) if schema == SCHEMA_STRICT_CUSIPS
                      else parse_cusips(row["cusips"]) or ())
            for cusip in tokens:
                cusip_owners[cusip].add(ticker)
    for members in cusip_owners.values():
        if len(members) > 1:
            for ticker in members:
                reasons[ticker].add("CROSS_NAME_CUSIP_CANDIDATE_COLLISION")
                if {roles[name] for name in members} == {"stocks", "funds"}:
                    reasons[ticker].add("DIRECT_STOCK_OWN_ETF_IDENTITY_COLLISION")
    dispositions: list[CurrentIdentityDisposition] = []
    for ticker, role in roles.items():
        candidates = rows_by_ticker[ticker]
        row = candidates[0] if len(candidates) == 1 else None
        codes = reasons[ticker]
        cusips: tuple[str, ...] = ()
        dates: dict[str, str | None] = {}
        if not candidates:
            codes.add("CURRENT_IDENTITY_MISSING")
        elif len(candidates) != 1:
            codes.add("CURRENT_IDENTITY_AMBIGUOUS")
        if schema == SCHEMA_WITHOUT_FIGI:
            codes.add("COMPOSITE_FIGI_INVALID_OR_MISSING")
        if row is not None:
            allowed_tables = {role, "SEP" if role == "stocks" else "SFP"}
            if row["table"] not in allowed_tables:
                codes.add("SOURCE_TABLE_UNRECOGNIZED")
            if _PERMANENT_ID.fullmatch(row["permaticker"]) is None:
                codes.add("PERMANENT_SHARE_CLASS_ID_INVALID")
            if _FIGI.fullmatch(row.get("figi", "")) is None:
                codes.add("COMPOSITE_FIGI_INVALID_OR_MISSING")
            if not row["name"]:
                codes.add("ISSUER_NAME_MISSING")
            if row["isdelisted"] != "N":
                codes.add("CURRENT_ACTIVE_STATUS_UNPROVEN")
            allowed_categories = _COMMON_CATEGORIES if role == "stocks" else {"etf"}
            if row["category"].casefold() not in allowed_categories:
                codes.add("INSTRUMENT_CATEGORY_UNRECOGNIZED")
            allowed_exchanges = _STOCK_EXCHANGES if role == "stocks" else _FUND_EXCHANGES
            if row["exchange"] not in allowed_exchanges:
                codes.add("CURRENT_LISTING_EXCHANGE_UNRECOGNIZED")
            if row["currency"] != "USD":
                codes.add("USD_CURRENCY_UNPROVEN")
            if any(value != value.strip() for value in row.values()):
                codes.add("SOURCE_FIELD_OUTER_WHITESPACE")
            parsed_cusips = parse_cusips(row["cusips"])
            if parsed_cusips is None:
                codes.add("CUSIP_CANDIDATES_INVALID_OR_MISSING")
            else:
                cusips = parsed_cusips
            for field in ("firstadded", "firstpricedate", "lastpricedate", "lastupdated"):
                dates[field] = _date(row[field])
                if dates[field] is None:
                    codes.add("CURRENT_METADATA_DATE_INVALID_OR_MISSING")
            first, last = dates["firstpricedate"], dates["lastpricedate"]
            if first is not None and last is not None and not first <= PRICE_CLOSE_SESSION <= last:
                codes.add("BOUND_PRICE_DATE_OUTSIDE_SOURCE_PRICING_RANGE")
        def field(name: str) -> str | None:
            return row.get(name) if row is not None and row.get(name) else None
        dispositions.append(CurrentIdentityDisposition(
            ticker, role, "refused_current_candidate" if codes else "matched_current_candidate",
            len(candidates), tuple(sha256_bytes(canonical_json_bytes(candidate)) for candidate in candidates),
            field("permaticker"), field("figi"), field("name"), field("category"),
            field("exchange"), field("currency"), cusips,
            dates.get("firstadded"), dates.get("firstpricedate"), dates.get("lastpricedate"),
            dates.get("lastupdated"), tuple(sorted(codes)),
        ))
    if len(dispositions) != 7:
        raise SharadarIdentityCaptureError("identity census lost a frozen requested name")
    return tuple(dispositions)


def _artifact_id(started: str) -> str:
    value = "arv2-sharadar-identities-" + started.translate(str.maketrans("", "", "-:."))
    if _ARTIFACT_ID.fullmatch(value) is None:
        raise SharadarIdentityCaptureError("identity capture clock cannot form an artifact identity")
    return value


def _manifest(
    started: str, completed: str, transport: str, price_binding: dict[str, object],
    csv_bytes: tuple[tuple[str, bytes], ...],
    *, schema: str = SCHEMA,
) -> dict[str, object]:
    fields = _fields(schema)
    if transport not in (PRODUCTION_TRANSPORT, TEST_TRANSPORT):
        raise SharadarIdentityCaptureError("identity transport is not supported")
    if parse_utc_timestamp(completed, "completed") < parse_utc_timestamp(started, "started"):
        raise SharadarIdentityCaptureError("identity capture clock moved backwards")
    if tuple(role for role, _payload in csv_bytes) != ("stocks", "funds"):
        raise SharadarIdentityCaptureError("identity response role order changed")
    rows = tuple((role, _parse_csv(payload, role, schema=schema)) for role, payload in csv_bytes)
    dispositions = _census(rows, schema=schema)
    bindings = tuple(IdentityCsvBinding(role, role + ".csv", sha256_bytes(payload),
                                        len(payload), len(dict(rows)[role]))
                     for role, payload in csv_bytes)
    counts = Counter(code for row in dispositions for code in row.refusal_codes)
    identity = {
        "capture_started_at": started, "capture_completed_at": completed,
        "capture_transport": transport, **price_binding,
        "responses": [{**dataclasses.asdict(binding), "endpoint_path": "/v1.0/data/tickers",
                       "request_query": _query(binding.role, schema=schema)} for binding in bindings],
        "identities": [dataclasses.asdict(row) for row in dispositions],
    }
    return {
        "schema": schema, "artifact_id": _artifact_id(started), **identity,
        "capture_sha256": sha256_bytes(canonical_json_bytes(identity)),
        "fields": list(fields), "request_count": 2, "requested_name_count": 7,
        "source_row_count": sum(binding.row_count for binding in bindings),
        "matched_current_candidate_count": sum(not row.refusal_codes for row in dispositions),
        "refused_current_candidate_count": sum(bool(row.refusal_codes) for row in dispositions),
        "refusal_reason_counts": dict(sorted(counts.items())),
        "response_byte_limit": MAX_RESPONSE_BYTES, "request_row_limit": REQUEST_ROW_LIMIT,
        "identity_semantics": "vendor_current_snapshot_share_class_candidates_not_historical_or_QC_identity",
        "permaticker_semantics": "vendor_security_share_class_identifier_not_issuer_identifier",
        "date_semantics": "vendor_pricing_and_metadata_dates_not_validity_or_first_availability",
        "price_binding_semantics": "local_ticker_role_and_byte_binding_not_independent_historical_identity",
        "response_bytes_semantics": "requests_HTTP_entity_CSV_not_wire_or_signed_vendor_proof",
        "client_clock_semantics": "unsigned_local_receipt_interval_not_original_publication",
        **({
            "cusip_parser_semantics": "exact_comma_separated_ASCII_shape_tokens_without_whitespace_normalization",
            "cusip_collision_semantics": "bounded_shape_tokens_from_every_row_for_refusal_only_not_admission",
        } if schema == SCHEMA_STRICT_CUSIPS else {}),
        "private_artifact": True, "provider_io_read_only": True,
        "current_snapshot_candidates_only": True, "redirects_permitted": False,
        "retries_permitted": False, **dict.fromkeys(FALSE_FLAGS, False),
    }


def _inventory(directory_fd: int, names: set[str]) -> None:
    if set(os.listdir(directory_fd)) != names:
        raise SharadarIdentityCaptureError("identity capture inventory is not exact")


def load_sharadar_identity_capture(
    artifact_path: Path, *, expected_manifest_sha256: str,
    price_artifact_path: Path = PRICE_ARTIFACT_PATH,
) -> LoadedSharadarIdentityCapture:
    """Reauthenticate identity and price bytes; expose immutable current dispositions."""
    held: list[tuple[str, int, tuple[int, int, int, int, int], int]] = []
    root_fd = None
    try:
        require_sha256(expected_manifest_sha256, "expected_manifest_sha256")
        root, root_fd = source._open_directory_path(artifact_path, create=False, name="identity capture")
        assert root_fd is not None
        names = {"stocks.csv", "funds.csv", "manifest.json", "manifest.sha256"}
        _inventory(root_fd, names)
        captured: dict[str, bytes] = {}
        for name in sorted(names):
            maximum = 65 if name.endswith(".sha256") else (
                MAX_MANIFEST_BYTES if name == "manifest.json" else MAX_RESPONSE_BYTES
            )
            descriptor = source._open_private_regular(root_fd, name, maximum=maximum, label="identity evidence")
            try:
                payload, identity = source._read_open_private_regular(
                    descriptor, maximum=maximum, label="identity evidence"
                )
            except BaseException:
                os.close(descriptor)
                raise
            held.append((name, descriptor, identity, maximum))
            captured[name] = payload
        digest = sha256_bytes(captured["manifest.json"])
        if digest != expected_manifest_sha256 or captured["manifest.sha256"] != (digest + "\n").encode("ascii"):
            raise SharadarIdentityCaptureError("identity manifest differs from exact pinned digest")
        manifest = require_canonical_json_bytes(captured["manifest.json"], "identity manifest")
        if type(manifest) is not dict:
            raise SharadarIdentityCaptureError("identity manifest must be an object")
        try:
            schema = manifest["schema"]
            fields = _fields(schema)
            transport = manifest["capture_transport"]
            binding = _price_binding(
                price_artifact_path, manifest["price_manifest_sha256"],
                synthetic=transport == TEST_TRANSPORT,
            )
            rebuilt = _manifest(
                manifest["capture_started_at"], manifest["capture_completed_at"], transport, binding,
                tuple((role, captured[role + ".csv"]) for role, _tickers in ROLE_TICKERS),
                schema=schema,
            )
        except KeyError:
            raise SharadarIdentityCaptureError("identity manifest lacks required bindings") from None
        if canonical_json_bytes(rebuilt) != captured["manifest.json"] or root.name != rebuilt["artifact_id"]:
            raise SharadarIdentityCaptureError("identity manifest/path differs from reauthenticated census")
        dispositions = _census(tuple((role, _parse_csv(captured[role + ".csv"], role, schema=schema))
                                      for role, _tickers in ROLE_TICKERS), schema=schema)
        bindings = tuple(IdentityCsvBinding(role, role + ".csv", sha256_bytes(captured[role + ".csv"]),
                                            len(captured[role + ".csv"]), len(_parse_csv(captured[role + ".csv"], role, schema=schema)))
                         for role, _tickers in ROLE_TICKERS)
        for name, descriptor, identity, maximum in held:
            source._require_open_leaf_identity(root_fd, name, descriptor, identity,
                                               maximum=maximum, label="identity evidence")
        _inventory(root_fd, names)
        return LoadedSharadarIdentityCapture(
            root, digest, rebuilt["capture_sha256"], transport,
            rebuilt["capture_started_at"], rebuilt["capture_completed_at"],
            binding["price_manifest_sha256"], binding["price_capture_sha256"],
            binding["price_close_session"], bindings, dispositions, schema, fields,
        )
    except CanonicalEvidenceError:
        raise SharadarIdentityCaptureError("identity manifest is not canonical evidence") from None
    finally:
        for _name, descriptor, _identity, _maximum in held:
            os.close(descriptor)
        if root_fd is not None:
            os.close(root_fd)


def _capture_core(
    *, artifact_root: Path, price_artifact_path: Path, price_binding: dict[str, object],
    session: object, key: str, clock: Callable[[], datetime], transport: str,
    close_owned_session: bool, schema: str = SCHEMA,
) -> LoadedSharadarIdentityCapture:
    root_fd = child_fd = None
    marker_identity = None
    try:
        _fields(schema)
        started = source._now_utc(clock)
        artifact_id = _artifact_id(started)
        root, root_fd = source._open_directory_path(artifact_root, create=True, name="identity artifact root")
        assert root_fd is not None
        try:
            os.mkdir(artifact_id, 0o700, dir_fd=root_fd)
        except FileExistsError:
            raise SharadarIdentityCaptureError("timestamped identity capture already exists") from None
        child_fd = source._open_child_directory(root_fd, artifact_id, "identity capture")
        responses: list[tuple[str, bytes]] = []
        for role, _tickers in ROLE_TICKERS:
            payload = _response_bytes(session, role, key, schema=schema)
            source._write_private_bytes(child_fd, role + ".csv", payload, "identity CSV")
            responses.append((role, payload))
        if close_owned_session:
            try:
                session.close()
            except Exception:
                raise SharadarIdentityCaptureError("owned identity session closure failed; details redacted") from None
        completed = source._now_utc(clock)
        manifest = _manifest(started, completed, transport, price_binding, tuple(responses), schema=schema)
        payload = canonical_json_bytes(manifest)
        if len(payload) > MAX_MANIFEST_BYTES:
            raise SharadarIdentityCaptureError("identity manifest exceeds byte limit")
        digest = sha256_bytes(payload)
        source._write_private_bytes(child_fd, "manifest.pending", payload, "pending identity manifest")
        source._write_private_bytes(child_fd, "manifest.sha256", (digest + "\n").encode("ascii"), "identity digest")
        _inventory(child_fd, {"stocks.csv", "funds.csv", "manifest.pending", "manifest.sha256"})
        source._pinned_child(root_fd, artifact_id, child_fd, "identity capture")
        source._fsync(child_fd, "identity capture before publication")
        metadata = os.stat("manifest.pending", dir_fd=child_fd, follow_symlinks=False)
        source._regular_metadata(metadata, "pending identity manifest", MAX_MANIFEST_BYTES)
        marker_identity = (metadata.st_dev, metadata.st_ino)
        os.link("manifest.pending", "manifest.json", src_dir_fd=child_fd,
                dst_dir_fd=child_fd, follow_symlinks=False)
        linked = os.stat("manifest.json", dir_fd=child_fd, follow_symlinks=False)
        if (linked.st_dev, linked.st_ino) != marker_identity:
            raise SharadarIdentityCaptureError("published identity manifest changed")
        os.unlink("manifest.pending", dir_fd=child_fd)
        source._fsync(child_fd, "identity capture publication")
        source._fsync(root_fd, "identity artifact root")
        source._pinned_child(root_fd, artifact_id, child_fd, "published identity capture")
        result = load_sharadar_identity_capture(
            root / artifact_id, expected_manifest_sha256=digest, price_artifact_path=price_artifact_path,
        )
        source._pinned_child(root_fd, artifact_id, child_fd, "reauthenticated identity capture")
        return result
    except BaseException as exc:
        if marker_identity is not None and child_fd is not None:
            try:
                try:
                    named = os.stat("manifest.json", dir_fd=child_fd, follow_symlinks=False)
                except FileNotFoundError:
                    named = None
                if named is not None:
                    if (named.st_dev, named.st_ino) != marker_identity:
                        raise SharadarIdentityCaptureError("identity publication state is ambiguous")
                    os.unlink("manifest.json", dir_fd=child_fd)
                    source._fsync(child_fd, "identity completion-marker rollback")
            except (OSError, SharadarIdentityCaptureError):
                raise SharadarIdentityCaptureError("identity publication state is ambiguous") from None
        if isinstance(exc, SharadarIdentityCaptureError) or not isinstance(exc, Exception):
            raise
        raise SharadarIdentityCaptureError("private identity capture failed; details redacted") from None
    finally:
        if close_owned_session:
            try:
                session.close()
            except Exception:
                pass
        if child_fd is not None:
            os.close(child_fd)
        if root_fd is not None:
            os.close(root_fd)


def _owned_session() -> object:
    """Create only the reviewed exact, verified, no-proxy/no-retry Session."""
    raw = source._new_session()
    owned = source._OwnedSessionGuard(raw)
    try:
        import requests
        from requests.adapters import HTTPAdapter
        if type(raw) is not requests.Session or any(callable(value) for value in raw.__dict__.values()):
            raise SharadarIdentityCaptureError("identity production Session is not exact/owned")
        raw.trust_env, raw.verify, raw.auth, raw.cert = False, True, None, None
        raw.proxies.clear()
        raw.params.clear()
        raw.cookies.clear()
        raw.headers.clear()
        raw.hooks.clear()
        raw.adapters.clear()
        raw.mount("https://", HTTPAdapter(max_retries=0))
        return owned
    except BaseException as exc:
        try:
            owned.close()
        except Exception:
            pass
        if isinstance(exc, SharadarIdentityCaptureError) or not isinstance(exc, Exception):
            raise
        raise SharadarIdentityCaptureError("identity transport setup failed; details redacted") from None


def _capture_production(schema: str) -> LoadedSharadarIdentityCapture:
    _fields(schema)
    binding = _price_binding(PRICE_ARTIFACT_PATH, PRICE_MANIFEST_SHA256, synthetic=False)
    source._preflight_root(DEFAULT_ARTIFACT_ROOT)
    key = source._api_key()
    return _capture_core(
        artifact_root=DEFAULT_ARTIFACT_ROOT, price_artifact_path=PRICE_ARTIFACT_PATH,
        price_binding=binding, session=_owned_session(), key=key,
        clock=lambda: datetime.now(timezone.utc), transport=PRODUCTION_TRANSPORT,
        close_owned_session=True, schema=schema,
    )


def capture_sharadar_identities() -> LoadedSharadarIdentityCapture:
    """Default strict fourteen-field capture; never retries a different profile."""
    return _capture_production(SCHEMA)


def capture_sharadar_identities_without_figi() -> LoadedSharadarIdentityCapture:
    """Explicit thirteen-field profile; missing FIGI remains a named refusal."""
    return _capture_production(SCHEMA_WITHOUT_FIGI)


def capture_sharadar_identities_strict_cusips() -> LoadedSharadarIdentityCapture:
    """Explicit prospective v3 fourteen-field profile; never migrate old captures."""
    return _capture_production(SCHEMA_STRICT_CUSIPS)


def inspect_sharadar_stock_header() -> StockHeaderDiagnostic:
    """One exact QCOM GET; no artifact creation, body persistence or row output."""
    _price_binding(PRICE_ARTIFACT_PATH, PRICE_MANIFEST_SHA256, synthetic=False)
    key = source._api_key()
    return _inspect_stock_header_core(
        _owned_session(), key, lambda: datetime.now(timezone.utc), close_owned_session=True,
    )


def _inspect_stock_header_for_test(
    *, session: object, clock: Callable[[], datetime], api_key: str,
) -> StockHeaderDiagnostic:
    key = source._validated_api_key(api_key, synthetic=True)
    return _inspect_stock_header_core(session, key, clock, close_owned_session=False)


def _capture_sharadar_identities_for_test(
    *, artifact_root: Path, price_artifact_path: Path, expected_price_manifest_sha256: str,
    session: object, clock: Callable[[], datetime], api_key: str,
    without_figi: bool = False, strict_cusips: bool = False,
) -> LoadedSharadarIdentityCapture:
    if type(without_figi) is not bool or type(strict_cusips) is not bool:
        raise SharadarIdentityCaptureError("synthetic profile selector must be a bool")
    if without_figi and strict_cusips:
        raise SharadarIdentityCaptureError("synthetic profiles are mutually exclusive")
    schema = (SCHEMA_STRICT_CUSIPS if strict_cusips else
              SCHEMA_WITHOUT_FIGI if without_figi else SCHEMA)
    binding = _price_binding(price_artifact_path, expected_price_manifest_sha256, synthetic=True)
    key = source._validated_api_key(api_key, synthetic=True)
    source._preflight_root(artifact_root)
    return _capture_core(
        artifact_root=artifact_root, price_artifact_path=price_artifact_path, price_binding=binding,
        session=session, key=key, clock=clock, transport=TEST_TRANSPORT, close_owned_session=False,
        schema=schema,
    )


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    profile = parser.add_mutually_exclusive_group()
    profile.add_argument("--inspect-stock-header", action="store_true")
    profile.add_argument("--without-figi", action="store_true")
    profile.add_argument("--strict-cusips", action="store_true",
                         help="prospective v3 fourteen-field profile; no existing capture migration")
    args = parser.parse_args(argv)
    try:
        if args.inspect_stock_header:
            diagnostic = inspect_sharadar_stock_header()
            print(canonical_json_bytes(dataclasses.asdict(diagnostic)).decode("utf-8"), end="")
            return 0
        result = (capture_sharadar_identities_strict_cusips() if args.strict_cusips
                  else capture_sharadar_identities_without_figi() if args.without_figi
                  else capture_sharadar_identities())
    except SharadarIdentityCaptureError as exc:
        print(f"refused={exc}", file=sys.stderr)
        return 1
    print(f"artifact={result.artifact_path}")
    print(f"manifest_sha256={result.manifest_sha256}")
    print(f"capture_sha256={result.capture_sha256}")
    print(f"requested=7 matched={result.matched_count} refused={result.refused_count}")
    reasons = Counter(code for row in result.identities for code in row.refusal_codes)
    print("refusal_counts=" + ",".join(f"{code}:{count}" for code, count in sorted(reasons.items())))
    print("point_in_time_proven=false formal_source_admitted=false qc_sid_resolved=false decision_ready=false orders_enabled=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
