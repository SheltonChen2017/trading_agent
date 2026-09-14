"""Capture and reload the three Massive/Benzinga inputs used by ARV2.

This is a deliberately narrow, read-only provider adapter.  It captures the
current-version rows returned by the three reviewed Benzinga endpoints over
one common event-date range.  It does not claim pristine point-in-time history
and it performs no price, outcome, QuantConnect, broker, or trading access.

The provider credential is read only from ``MASSIVE_API_KEY`` (with the same
Windows per-user environment fallback as the older audit utility).  It is sent
only in the Authorization header and is never printed or persisted.  Every
snapshot is an immutable, timestamped, private directory below ``artifacts/``
by default.  The loader treats the persisted bytes, rather than a caller's
claims, as authority and reconstructs the reviewed ``CaptureBinding``.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from research.analyst_revisions_v2.accepted_risk_input_pair import (
    CAPTURE_PAGE_SCHEMA,
    CAPTURE_SCHEMA,
    INPUT_PAIR_CONTRACT_ID,
    INPUT_PAIR_CONTRACT_SHA256,
    MAX_PROVIDER_ROWS_PER_PAGE,
    OWNER_DECISION_ID,
    AcceptedRiskInputError,
    AcceptedRiskInputPair,
    CaptureBinding,
    MassiveSourceRole,
    bind_capture_page,
    build_capture_binding,
    render_redacted_capture_query_bytes,
    require_capture_binding,
)
from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    decode_utf8,
    format_utc_timestamp,
    parse_date,
    parse_utc_timestamp,
    require_canonical_json_bytes,
    require_exact_bool,
    require_exact_keys,
    require_identifier,
    require_int,
    require_sha256,
    sha256_bytes,
    strict_json_loads,
)


BASE_URL = "https://api.massive.com"
ARTIFACT_SCHEMA = "arv2-massive-three-role-capture-artifact-v2"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_DIGEST_FILENAME = "manifest.sha256"
DEFAULT_PAGE_LIMIT = MAX_PROVIDER_ROWS_PER_PAGE
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_RAW_RESPONSE_BYTES = 72 * 1024 * 1024
MAX_PROVIDER_ROWS_BYTES = 64 * 1024 * 1024
MAX_ARTIFACT_PAGES = 512
# Production capture is page-spooled to private storage under this aggregate
# regular-file payload-byte ceiling.  Filesystem metadata and allocation-unit
# overhead are outside this logical-byte bound; this is not a RAM allowance.
MAX_CAPTURE_STORED_BYTES = 8 * 1024 * 1024 * 1024
# The legacy in-memory loader and offline oracle remain narrowly bounded.  A
# production artifact above this limit must be consumed by the streaming
# physical bridge rather than materialized as one CaptureBinding.
MAX_CAPTURE_RETAINED_BYTES = 512 * 1024 * 1024
MAX_CAPTURE_ROWS = MAX_ARTIFACT_PAGES * MAX_PROVIDER_ROWS_PER_PAGE
REQUEST_TIMEOUT_SECONDS = 60
RESPONSE_CHUNK_BYTES = 64 * 1024

PRODUCTION_TRANSPORT = "massive_https_bearer_default_session"
TEST_TRANSPORT = "offline_test_double"
_TRANSPORTS = frozenset({PRODUCTION_TRANSPORT, TEST_TRANSPORT})

ROLE_ORDER = (
    MassiveSourceRole.ANALYST_RATINGS,
    MassiveSourceRole.EARNINGS,
    MassiveSourceRole.CORPORATE_GUIDANCE,
)
ENDPOINT_PATHS = MappingProxyType(
    {
        MassiveSourceRole.ANALYST_RATINGS: "/benzinga/v1/ratings",
        MassiveSourceRole.EARNINGS: "/benzinga/v1/earnings",
        MassiveSourceRole.CORPORATE_GUIDANCE: "/benzinga/v1/guidance",
    }
)
REPOSITORY_ROOT = Path(__file__).absolute().parents[1]
REPOSITORY_ARTIFACTS_ROOT = REPOSITORY_ROOT / "artifacts"
DEFAULT_ARTIFACT_ROOT = (
    REPOSITORY_ROOT
    / "artifacts"
    / "analyst_revisions_v2"
    / "massive_capture"
)

_ARTIFACT_ID_RE = re.compile(
    r"arv2-massive-three-role-\d{8}T\d{6}\d{6}Z"
)
_MALFORMED_PERCENT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_CREDENTIAL_QUERY_KEYS = frozenset(
    {
        "access-token",
        "access_token",
        "accesstoken",
        "api-key",
        "api_key",
        "api-token",
        "api_token",
        "apikey",
        "apitoken",
        "auth-token",
        "auth_token",
        "authtoken",
        "authorization",
        "bearer-token",
        "bearer_token",
        "bearertoken",
        "client-secret",
        "client_secret",
        "clientsecret",
        "key",
        "password",
        "secret",
        "secret-key",
        "secret_key",
        "token",
    }
)
_MANIFEST_KEYS = frozenset(
    {
        "schema",
        "artifact_id",
        "capture_id",
        "capture_sha256",
        "capture_started_at",
        "capture_completed_at",
        "requested_first_event_date",
        "requested_last_event_date",
        "page_limit",
        "role_order",
        "role_counts",
        "pages",
        "total_page_count",
        "total_row_count",
        "raw_response_total_byte_count",
        "provider_rows_total_byte_count",
        "stored_capture_byte_limit",
        "stored_capture_row_limit",
        "page_spooled_before_next_request",
        "full_capture_retained_in_memory",
        "capture_transport",
        "immutable",
        "private_artifact",
        "cursor_material_persisted_outside_raw_provider_responses",
        "provider_io_read_only",
        "outcome_access_performed",
        "quantconnect_io_performed",
    }
)
_ROLE_COUNT_KEYS = frozenset({"source_role", "page_count", "row_count"})
_PAGE_KEYS = frozenset(
    {
        "source_role",
        "endpoint_path",
        "endpoint_identifier",
        "redacted_query_sha256",
        "page_number",
        "request_cursor_sha256",
        "next_cursor_sha256",
        "terminal_page",
        "response_received_at",
        "raw_response_file",
        "raw_response_byte_count",
        "raw_response_sha256",
        "provider_rows_file",
        "provider_rows_byte_count",
        "provider_rows_sha256",
        "row_count",
    }
)


class MassiveCaptureError(ValueError):
    """A provider response or persisted capture is unsafe or inconsistent."""


@dataclasses.dataclass(frozen=True)
class LoadedMassiveCapture:
    artifact_path: Path
    manifest_sha256: str
    capture: CaptureBinding
    accepted_risk_input_pair: AcceptedRiskInputPair | None
    capture_transport: str


@dataclasses.dataclass(frozen=True)
class SpooledMassiveCapture:
    """A lightweight binding to a page-spooled production capture.

    It intentionally carries no response or provider-row bytes.  Consumers
    must authenticate the immutable artifact through the physical bridge.
    """

    artifact_path: Path
    manifest_sha256: str
    capture_id: str
    capture_sha256: str
    total_page_count: int
    total_row_count: int
    role_row_counts: tuple[tuple[MassiveSourceRole, int], ...]
    capture_transport: str


class _OwnedSessionGuard:
    """Make the production Session close-once across every preflight path."""

    def __init__(self, session: object) -> None:
        self._session = session
        self._closed = False

    def __getattr__(self, name: str) -> object:
        return getattr(self._session, name)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._session.close()


def _api_key() -> str:
    key = os.environ.get("MASSIVE_API_KEY")
    if not key and sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as handle:
                key = winreg.QueryValueEx(handle, "MASSIVE_API_KEY")[0]
        except (ImportError, OSError):
            key = None
    if (
        type(key) is not str
        or not key
        or key != key.strip()
        or len(key) < 8
        or len(key) > 4096
        or any(ord(character) < 0x21 or ord(character) > 0x7E for character in key)
    ):
        raise MassiveCaptureError(
            "MASSIVE_API_KEY is unavailable or malformed; refusing provider access"
        )
    return key


def _redact_url(url: object) -> str:
    """Return a diagnostic URL with userinfo, credentials, and fragment removed."""

    if type(url) is not str:
        return "<invalid URL redacted>"
    try:
        parts = urlsplit(url)
        if _MALFORMED_PERCENT_RE.search(parts.query) is not None:
            return "<malformed URL redacted>"
        query: list[tuple[str, str]] = []
        for name, value in parse_qsl(parts.query, keep_blank_values=True):
            query.append(
                (
                    name,
                    "REDACTED"
                    if name.casefold() in _CREDENTIAL_QUERY_KEYS
                    or name.casefold() == "cursor"
                    else value,
                )
            )
        host = parts.netloc.rsplit("@", 1)[-1]
        netloc = f"REDACTED@{host}" if "@" in parts.netloc else host
        return urlunsplit(
            (parts.scheme, netloc, parts.path, urlencode(query), "")
        )
    except (TypeError, ValueError, UnicodeError):
        return "<malformed URL redacted>"


def _sanitized_provider_failure(exc: BaseException) -> str:
    return f"{type(exc).__name__}: provider request failed; details redacted"


def _new_session() -> object:
    try:
        import requests
    except ImportError as exc:
        raise MassiveCaptureError("requests is required for Massive capture") from exc
    return requests.Session()


def _now_utc(clock: Callable[[], datetime]) -> str:
    try:
        value = clock()
        return format_utc_timestamp(value)
    except (CanonicalEvidenceError, TypeError, ValueError) as exc:
        raise MassiveCaptureError("capture clock did not return an aware instant") from exc


def _canonical_json_value(value: object) -> str:
    """Render strict-JSON values while preserving Decimal tuple significance."""

    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        return str(value)
    if type(value) is Decimal:
        if not value.is_finite():
            raise MassiveCaptureError("provider row contains a non-finite number")
        rendered_decimal = str(value)
        # json.loads calls parse_int for a bare integral token and parse_float
        # for decimal/exponent notation.  Keep an exponent marker when a
        # provider supplied a numerically integral *decimal* (for example
        # ``1e0``), otherwise the ordered-extraction proof would silently
        # change its JSON scalar kind from Decimal to int.
        return (
            rendered_decimal
            if "." in rendered_decimal or "e" in rendered_decimal.casefold()
            else rendered_decimal + "E+0"
        )
    if type(value) is str:
        try:
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError, UnicodeError) as exc:
            raise MassiveCaptureError("provider row contains invalid text") from exc
    if type(value) is list:
        return "[" + ",".join(_canonical_json_value(item) for item in value) + "]"
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise MassiveCaptureError("provider row contains a non-string object key")
        return "{" + ",".join(
            _canonical_json_value(key) + ":" + _canonical_json_value(value[key])
            for key in sorted(value)
        ) + "}"
    raise MassiveCaptureError("provider row contains an unsupported JSON scalar")


def _response_rows_and_next_url(
    payload: bytes, *, page_limit: int
) -> tuple[bytes, str | None]:
    if type(payload) is not bytes or len(payload) > MAX_RAW_RESPONSE_BYTES:
        raise MassiveCaptureError("provider response is not bounded exact bytes")
    try:
        value = strict_json_loads(
            decode_utf8(payload, "Massive response"), "Massive response"
        )
    except (CanonicalEvidenceError, RecursionError) as exc:
        raise MassiveCaptureError("provider response is not strict JSON") from exc
    if type(value) is not dict or type(value.get("results")) is not list:
        raise MassiveCaptureError(
            "provider response must contain one ordered results array"
        )
    if type(value.get("status")) is not str or value["status"] != "OK":
        # Massive can return an application-level error document with HTTP
        # 200.  Such a page is not evidence of an empty terminal result set
        # and must never enter the completeness derivation.
        raise MassiveCaptureError("provider response status is not exact OK")
    results = value["results"]
    if len(results) > page_limit:
        raise MassiveCaptureError("provider returned more rows than the requested limit")
    if any(type(row) is not dict for row in results):
        raise MassiveCaptureError("provider results must contain only JSON objects")
    if "next_url" not in value or value["next_url"] is None:
        next_url = None
    elif type(value["next_url"]) is str and value["next_url"]:
        next_url = value["next_url"]
    else:
        raise MassiveCaptureError("provider next_url must be absent, null, or nonempty text")
    try:
        rendered = (
            b""
            if not results
            else (
                "\n".join(_canonical_json_value(row) for row in results) + "\n"
            ).encode("utf-8")
        )
    except (RecursionError, UnicodeEncodeError) as exc:
        raise MassiveCaptureError("provider rows could not be rendered canonically") from exc
    if len(rendered) > MAX_PROVIDER_ROWS_BYTES:
        raise MassiveCaptureError("canonical provider rows exceed the page-byte limit")
    return rendered, next_url


def _cursor_hash_and_validated_url(
    url: str,
    *,
    source_role: MassiveSourceRole,
    requested_first_event_date: str,
    requested_last_event_date: str,
    page_limit: int,
) -> tuple[str, str]:
    if (
        type(url) is not str
        or not url
        or url != url.strip()
        or len(url) > 32_768
        or "\\" in url
    ):
        raise MassiveCaptureError("provider next_url is malformed")
    try:
        parts = urlsplit(url)
        port = parts.port
    except (TypeError, ValueError, UnicodeError) as exc:
        raise MassiveCaptureError("provider next_url is malformed") from exc
    if (
        parts.scheme != "https"
        or parts.netloc != "api.massive.com"
        or parts.hostname != "api.massive.com"
        or port is not None
        or parts.username is not None
        or parts.password is not None
        or parts.path != ENDPOINT_PATHS[source_role]
        or parts.fragment
        or not parts.query
        or _MALFORMED_PERCENT_RE.search(parts.query) is not None
    ):
        raise MassiveCaptureError(
            "provider next_url changed host, endpoint, or secret boundary"
        )
    try:
        pairs = parse_qsl(
            parts.query,
            keep_blank_values=True,
            strict_parsing=True,
            encoding="utf-8",
            errors="strict",
        )
    except (UnicodeError, ValueError) as exc:
        raise MassiveCaptureError("provider next_url query is malformed") from exc
    names = [name for name, _ in pairs]
    if len(names) != len(set(names)):
        raise MassiveCaptureError("provider next_url repeats a query parameter")
    if any(name.casefold() in _CREDENTIAL_QUERY_KEYS for name in names):
        raise MassiveCaptureError("provider next_url contains credential material")
    allowed = {"cursor", "date.gte", "date.lte", "limit", "sort"}
    if set(names) - allowed:
        raise MassiveCaptureError("provider next_url contains an unreviewed query field")
    query = dict(pairs)
    cursor = query.get("cursor")
    if (
        type(cursor) is not str
        or not cursor
        or len(cursor) > 16_384
        or any(
            ord(character) < 0x21 or ord(character) > 0x7E
            for character in cursor
        )
    ):
        raise MassiveCaptureError("provider next_url lacks one bounded cursor")
    expected_optional = {
        "date.gte": requested_first_event_date,
        "date.lte": requested_last_event_date,
        "limit": str(page_limit),
        "sort": "date.asc",
    }
    if any(
        key in query and query[key] != expected
        for key, expected in expected_optional.items()
    ):
        raise MassiveCaptureError("provider next_url changed the frozen query")
    cursor_bytes = canonical_json_bytes({"cursor": cursor})
    return sha256_bytes(cursor_bytes), url


def _validate_response_url(url: object, role: MassiveSourceRole) -> None:
    if type(url) is not str or not url or url != url.strip():
        raise MassiveCaptureError("provider response URL is malformed")
    try:
        parts = urlsplit(url)
        port = parts.port
    except (TypeError, ValueError, UnicodeError) as exc:
        raise MassiveCaptureError("provider response URL is malformed") from exc
    if (
        parts.scheme != "https"
        or parts.netloc != "api.massive.com"
        or parts.hostname != "api.massive.com"
        or port is not None
        or parts.username is not None
        or parts.password is not None
        or parts.path != ENDPOINT_PATHS[role]
        or parts.fragment
        or _MALFORMED_PERCENT_RE.search(parts.query) is not None
    ):
        raise MassiveCaptureError("provider response URL left the reviewed endpoint")
    try:
        names = [
            name
            for name, _ in parse_qsl(
                parts.query,
                keep_blank_values=True,
                strict_parsing=True,
                encoding="utf-8",
                errors="strict",
            )
        ]
    except (UnicodeError, ValueError) as exc:
        raise MassiveCaptureError("provider response URL query is malformed") from exc
    if any(name.casefold() in _CREDENTIAL_QUERY_KEYS for name in names):
        raise MassiveCaptureError("provider response URL contains credential material")


def _url_request_semantics(url: object, role: MassiveSourceRole) -> tuple[tuple[str, str], ...]:
    _validate_response_url(url, role)
    assert isinstance(url, str)
    try:
        parts = urlsplit(url)
        pairs = parse_qsl(
            parts.query,
            keep_blank_values=True,
            strict_parsing=True,
            encoding="utf-8",
            errors="strict",
        )
    except (UnicodeError, ValueError) as exc:
        raise MassiveCaptureError("prepared request URL query is malformed") from exc
    names = [name for name, _ in pairs]
    if len(names) != len(set(names)):
        raise MassiveCaptureError("prepared request URL repeats a query parameter")
    return tuple(sorted(pairs))


def _validate_prepared_request(
    response: object,
    *,
    expected_url: str,
    source_role: MassiveSourceRole,
) -> None:
    """Authenticate the request Requests actually prepared, not caller intent."""

    try:
        request = response.request
        method = request.method
        prepared_url = request.url
        response_url = response.url
    except Exception as exc:
        raise MassiveCaptureError(_sanitized_provider_failure(exc)) from None
    if type(method) is not str or method != "GET":
        raise MassiveCaptureError("provider request was not prepared as exact GET")
    expected_semantics = _url_request_semantics(expected_url, source_role)
    if _url_request_semantics(prepared_url, source_role) != expected_semantics:
        raise MassiveCaptureError("prepared provider request changed the frozen query")
    if _url_request_semantics(response_url, source_role) != expected_semantics:
        raise MassiveCaptureError("provider response URL changed the prepared request")


def _close_response(response: object) -> None:
    try:
        response.close()
    except Exception:
        # The owned Session is also closed before publication.  A Response
        # close failure must not replace the primary refusal or create an
        # ambiguous already-published artifact.
        return


def _request_page(
    session: object,
    url: str,
    *,
    params: dict[str, object] | None,
    source_role: MassiveSourceRole,
) -> bytes:
    expected_url = url
    if params is not None:
        expected_url = url + ("&" if "?" in url else "?") + urlencode(params)
    response: object | None = None
    try:
        response = session.get(
            url,
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
            allow_redirects=False,
            stream=True,
        )
    except Exception as exc:
        raise MassiveCaptureError(_sanitized_provider_failure(exc)) from None
    try:
        status_code = response.status_code
        _validate_prepared_request(
            response,
            expected_url=expected_url,
            source_role=source_role,
        )
        if type(status_code) is not int or status_code != 200:
            raise MassiveCaptureError("provider returned a non-success HTTP status")
        chunks: list[bytes] = []
        observed = 0
        for chunk in response.iter_content(chunk_size=RESPONSE_CHUNK_BYTES):
            if type(chunk) is not bytes:
                raise MassiveCaptureError("provider response stream yielded non-bytes")
            if not chunk:
                continue
            observed += len(chunk)
            if observed > MAX_RAW_RESPONSE_BYTES:
                raise MassiveCaptureError("provider response exceeded the byte limit")
            chunks.append(chunk)
        payload = b"".join(chunks)
    except Exception as exc:
        if isinstance(exc, MassiveCaptureError):
            raise
        raise MassiveCaptureError(_sanitized_provider_failure(exc)) from None
    finally:
        if response is not None:
            _close_response(response)
    if type(payload) is not bytes:
        raise MassiveCaptureError("provider response body is not exact bytes")
    return payload


def _credential_encodings(key: str) -> tuple[bytes, ...]:
    candidates = {
        key.encode("ascii"),
        quote(key, safe="").encode("ascii"),
        json.dumps(key, ensure_ascii=True)[1:-1].encode("ascii"),
    }
    return tuple(candidate for candidate in candidates if candidate)


def _assert_response_does_not_echo_credential(payload: bytes, key: str) -> None:
    if any(candidate in payload for candidate in _credential_encodings(key)):
        raise MassiveCaptureError(
            "provider response appears to echo credential material; persistence refused"
        )


def _role_page_filename(
    source_role: MassiveSourceRole, page_number: int, suffix: str
) -> str:
    role_index = ROLE_ORDER.index(source_role) + 1
    return f"{role_index:02d}-{source_role.value}-page-{page_number:06d}.{suffix}"


def _artifact_page_record(page: object) -> dict[str, object]:
    source_role = page.source_role
    raw_response = page.raw_response_bytes
    if raw_response is None:
        raise MassiveCaptureError("capture page did not retain exact raw response bytes")
    raw_name = _role_page_filename(source_role, page.page_number, "raw.json")
    rows_name = _role_page_filename(source_role, page.page_number, "rows.jsonl")
    return {
        "source_role": source_role.value,
        "endpoint_path": ENDPOINT_PATHS[source_role],
        "endpoint_identifier": page.endpoint_identifier,
        "redacted_query_sha256": page.redacted_query_sha256,
        "page_number": page.page_number,
        "request_cursor_sha256": page.request_cursor_sha256,
        "next_cursor_sha256": page.next_cursor_sha256,
        "terminal_page": page.terminal_page,
        "response_received_at": page.response_received_at,
        "raw_response_file": f"pages/{raw_name}",
        "raw_response_byte_count": len(raw_response),
        "raw_response_sha256": page.raw_response_sha256,
        "provider_rows_file": f"pages/{rows_name}",
        "provider_rows_byte_count": len(page.provider_rows_bytes),
        "provider_rows_sha256": page.provider_rows_sha256,
        "row_count": page.row_count,
    }


def _capture_lineage_page_record(page: dict[str, object]) -> dict[str, object]:
    return {
        "schema": CAPTURE_PAGE_SCHEMA,
        "source_role": page["source_role"],
        "endpoint_identifier": page["endpoint_identifier"],
        "redacted_query_sha256": page["redacted_query_sha256"],
        "page_number": page["page_number"],
        "request_cursor_sha256": page["request_cursor_sha256"],
        "next_cursor_sha256": page["next_cursor_sha256"],
        "terminal_page": page["terminal_page"],
        "response_received_at": page["response_received_at"],
        "raw_response_sha256": page["raw_response_sha256"],
        "raw_response_extraction_verified": True,
        "provider_rows_sha256": page["provider_rows_sha256"],
        "row_count": page["row_count"],
    }


def _logical_capture_record(
    *,
    capture_started_at: str,
    capture_completed_at: str,
    requested_first_event_date: str,
    requested_last_event_date: str,
    pages: tuple[dict[str, object], ...],
) -> dict[str, object]:
    counts = {
        role: sum(
            int(page["row_count"])
            for page in pages
            if page["source_role"] == role.value
        )
        for role in ROLE_ORDER
    }
    return {
        "schema": CAPTURE_SCHEMA,
        "contract_id": INPUT_PAIR_CONTRACT_ID,
        "contract_sha256": INPUT_PAIR_CONTRACT_SHA256,
        "capture_started_at": capture_started_at,
        "capture_completed_at": capture_completed_at,
        "requested_first_event_date": requested_first_event_date,
        "requested_last_event_date": requested_last_event_date,
        "pages": [_capture_lineage_page_record(page) for page in pages],
        "total_page_count": len(pages),
        "total_row_count": sum(int(page["row_count"]) for page in pages),
        "role_row_counts": [
            {"source_role": role.value, "row_count": counts[role]}
            for role in ROLE_ORDER
        ],
        "owner_decision_id": OWNER_DECISION_ID,
        "transactional_snapshot": False,
        "complete_version_history": False,
        "complete_deletion_tombstones": False,
        "point_in_time_ticker_identity": False,
        "pristine_point_in_time": False,
    }


def _manifest_from_page_records(
    *,
    artifact_id: str,
    capture_started_at: str,
    capture_completed_at: str,
    requested_first_event_date: str,
    requested_last_event_date: str,
    page_records: tuple[dict[str, object], ...],
    page_limit: int,
    capture_transport: str,
    page_spooled_before_next_request: bool,
) -> dict[str, Any]:
    if type(capture_transport) is not str or capture_transport not in _TRANSPORTS:
        raise MassiveCaptureError("capture transport is not reviewed")
    if type(page_spooled_before_next_request) is not bool:
        raise MassiveCaptureError("capture storage mode must be an exact boolean")
    logical = _logical_capture_record(
        capture_started_at=capture_started_at,
        capture_completed_at=capture_completed_at,
        requested_first_event_date=requested_first_event_date,
        requested_last_event_date=requested_last_event_date,
        pages=page_records,
    )
    capture_sha256 = sha256_bytes(canonical_json_bytes(logical))
    role_counts: list[dict[str, object]] = []
    for role in ROLE_ORDER:
        role_pages = tuple(
            page for page in page_records if page["source_role"] == role.value
        )
        role_counts.append(
            {
                "source_role": role.value,
                "page_count": len(role_pages),
                "row_count": sum(int(page["row_count"]) for page in role_pages),
            }
        )
    return {
        "schema": ARTIFACT_SCHEMA,
        "artifact_id": artifact_id,
        "capture_id": f"arv2-capture-{capture_sha256[:24]}",
        "capture_sha256": capture_sha256,
        "capture_started_at": capture_started_at,
        "capture_completed_at": capture_completed_at,
        "requested_first_event_date": requested_first_event_date,
        "requested_last_event_date": requested_last_event_date,
        "page_limit": page_limit,
        "role_order": [role.value for role in ROLE_ORDER],
        "role_counts": role_counts,
        "pages": list(page_records),
        "total_page_count": len(page_records),
        "total_row_count": sum(int(page["row_count"]) for page in page_records),
        "raw_response_total_byte_count": sum(
            int(page["raw_response_byte_count"]) for page in page_records
        ),
        "provider_rows_total_byte_count": sum(
            int(page["provider_rows_byte_count"]) for page in page_records
        ),
        "stored_capture_byte_limit": MAX_CAPTURE_STORED_BYTES,
        "stored_capture_row_limit": MAX_CAPTURE_ROWS,
        "page_spooled_before_next_request": page_spooled_before_next_request,
        "full_capture_retained_in_memory": not page_spooled_before_next_request,
        "capture_transport": capture_transport,
        "immutable": True,
        "private_artifact": True,
        "cursor_material_persisted_outside_raw_provider_responses": False,
        "provider_io_read_only": capture_transport == PRODUCTION_TRANSPORT,
        "outcome_access_performed": False,
        "quantconnect_io_performed": False,
    }


def _manifest_record(
    artifact_id: str,
    capture: CaptureBinding,
    page_limit: int,
    capture_transport: str,
) -> dict[str, Any]:
    page_records = tuple(_artifact_page_record(page) for page in capture.pages)
    manifest = _manifest_from_page_records(
        artifact_id=artifact_id,
        capture_started_at=capture.capture_started_at,
        capture_completed_at=capture.capture_completed_at,
        requested_first_event_date=capture.requested_first_event_date,
        requested_last_event_date=capture.requested_last_event_date,
        page_records=page_records,
        page_limit=page_limit,
        capture_transport=capture_transport,
        page_spooled_before_next_request=False,
    )
    if (
        manifest["capture_id"] != capture.capture_id
        or manifest["capture_sha256"] != capture.capture_sha256
    ):
        raise MassiveCaptureError("artifact manifest changed logical capture identity")
    return manifest


def _require_operational_artifact_scope(path: Path) -> None:
    """Keep non-test acquisition beneath the repository's ignored artifacts/."""

    candidate = Path(os.path.abspath(path))
    try:
        candidate.relative_to(REPOSITORY_ARTIFACTS_ROOT)
    except ValueError as exc:
        raise MassiveCaptureError(
            "operational capture root must remain beneath repository artifacts"
        ) from exc


def _require_dirfd_support() -> None:
    required = (os.open, os.mkdir, os.rename, os.stat, os.unlink, os.rmdir)
    if (
        os.name == "nt"
        or not hasattr(os, "O_DIRECTORY")
        or not hasattr(os, "O_NOFOLLOW")
        or any(call not in os.supports_dir_fd for call in required)
    ):
        raise MassiveCaptureError(
            "Massive capture requires POSIX dirfd, no-follow, and private-mode enforcement"
        )


def _directory_open_flags() -> int:
    return (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )


def _require_private_directory_metadata(metadata: os.stat_result, name: str) -> None:
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
    ):
        raise MassiveCaptureError(f"{name} must be an owner-held private 0700 directory")


def _open_directory_path(
    path: Path,
    *,
    create: bool,
    allow_missing: bool = False,
    name: str,
) -> tuple[Path, int | None]:
    """Open an absolute directory component-by-component without following links."""

    _require_dirfd_support()
    if type(path) is not type(Path()):
        raise MassiveCaptureError(f"{name} must be a Path")
    absolute = Path(os.path.abspath(path))
    parts = absolute.parts
    if not absolute.is_absolute() or not parts:
        raise MassiveCaptureError(f"{name} must be absolute")
    try:
        descriptor = os.open(absolute.anchor, _directory_open_flags())
    except OSError as exc:
        raise MassiveCaptureError(f"{name} root directory is unavailable") from exc
    try:
        for component in parts[1:]:
            created = False
            try:
                child = os.open(
                    component,
                    _directory_open_flags(),
                    dir_fd=descriptor,
                )
            except FileNotFoundError:
                if not create:
                    if allow_missing:
                        os.close(descriptor)
                        return absolute, None
                    raise MassiveCaptureError(f"{name} is unavailable") from None
                try:
                    os.mkdir(component, 0o700, dir_fd=descriptor)
                    child = os.open(
                        component,
                        _directory_open_flags(),
                        dir_fd=descriptor,
                    )
                    os.fchmod(child, 0o700)
                    created = True
                except OSError as exc:
                    raise MassiveCaptureError(
                        f"{name} could not be prepared safely"
                    ) from exc
            except OSError as exc:
                raise MassiveCaptureError(
                    f"{name} must not traverse a link and must be a directory"
                ) from exc
            os.close(descriptor)
            descriptor = child
            if created:
                _require_private_directory_metadata(os.fstat(descriptor), name)
        _require_private_directory_metadata(os.fstat(descriptor), name)
        return absolute, descriptor
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def _open_private_child_directory(parent_fd: int, child: str, name: str) -> int:
    if (
        type(child) is not str
        or not child
        or child in {".", ".."}
        or "/" in child
        or "\\" in child
    ):
        raise MassiveCaptureError(f"{name} has an unsafe directory name")
    descriptor: int | None = None
    try:
        descriptor = os.open(child, _directory_open_flags(), dir_fd=parent_fd)
        _require_private_directory_metadata(os.fstat(descriptor), name)
        return descriptor
    except MassiveCaptureError:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise
    except OSError as exc:
        raise MassiveCaptureError(f"{name} is unavailable or link-like") from exc


def _directory_identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _require_pinned_child_identity(
    parent_fd: int, child: str, child_fd: int, name: str
) -> None:
    try:
        opened = os.fstat(child_fd)
        named = os.stat(child, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise MassiveCaptureError(f"{name} directory identity is unavailable") from exc
    _require_private_directory_metadata(opened, name)
    _require_private_directory_metadata(named, name)
    if _directory_identity(opened) != _directory_identity(named):
        raise MassiveCaptureError(f"{name} directory identity changed")


def _entry_exists_at(parent_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise MassiveCaptureError("artifact directory entry could not be inspected") from exc
    return True


def _write_all(descriptor: int, payload: bytes, name: str) -> None:
    offset = 0
    while offset < len(payload):
        try:
            written = os.write(descriptor, payload[offset:])
        except InterruptedError:
            continue
        except OSError as exc:
            raise MassiveCaptureError(f"{name} write failed") from exc
        if written <= 0:
            raise MassiveCaptureError(f"{name} write stalled")
        offset += written


def _fsync_fd(descriptor: int, name: str) -> None:
    try:
        os.fsync(descriptor)
    except OSError as exc:
        raise MassiveCaptureError(f"{name} directory sync failed") from exc


def _exclusive_private_write_at(
    parent_fd: int, filename: str, payload: bytes, name: str
) -> None:
    if (
        type(filename) is not str
        or not filename
        or filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
    ):
        raise MassiveCaptureError(f"{name} filename is unsafe")
    if type(payload) is not bytes:
        raise MassiveCaptureError(f"{name} payload must be exact bytes")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | os.O_NOFOLLOW
        | getattr(os, "O_BINARY", 0)
    )
    try:
        descriptor = os.open(filename, flags, 0o600, dir_fd=parent_fd)
    except FileExistsError as exc:
        raise MassiveCaptureError(f"{name} already exists; overwrite refused") from exc
    except OSError as exc:
        raise MassiveCaptureError(f"{name} could not be created") from exc
    try:
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, payload, name)
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size != len(payload)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
            or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
        ):
            raise MassiveCaptureError(f"{name} was not written as one private file")
    except MassiveCaptureError:
        raise
    except OSError as exc:
        raise MassiveCaptureError(f"{name} could not be durably written") from exc
    finally:
        os.close(descriptor)


def _read_private_regular_at(
    parent_fd: int,
    filename: str,
    *,
    maximum_bytes: int,
    name: str,
) -> bytes:
    if (
        type(filename) is not str
        or not filename
        or filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
    ):
        raise MassiveCaptureError(f"{name} filename is unsafe")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | os.O_NOFOLLOW
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_BINARY", 0)
    )
    try:
        descriptor = os.open(filename, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise MassiveCaptureError(f"{name} is unavailable or link-like") from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size < 0
            or before.st_size > maximum_bytes
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_nlink != 1
            or (hasattr(os, "getuid") and before.st_uid != os.getuid())
        ):
            raise MassiveCaptureError(
                f"{name} must be a bounded private single-link regular file"
            )
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(RESPONSE_CHUNK_BYTES, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        named = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
    except MassiveCaptureError:
        raise
    except OSError as exc:
        raise MassiveCaptureError(f"{name} could not be read safely") from exc
    finally:
        os.close(descriptor)
    identities = tuple(
        (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        )
        for metadata in (before, after, named)
    )
    if (
        len(payload) > maximum_bytes
        or len(payload) != before.st_size
        or len(set(identities)) != 1
        or not stat.S_ISREG(named.st_mode)
        or stat.S_IMODE(named.st_mode) != 0o600
        or named.st_nlink != 1
        or (hasattr(os, "getuid") and named.st_uid != os.getuid())
    ):
        raise MassiveCaptureError(f"{name} changed while being read")
    return payload


def _artifact_id_from_timestamp(timestamp: str) -> str:
    parse_utc_timestamp(timestamp, "capture_started_at")
    compact = timestamp.translate(str.maketrans("", "", "-:."))
    artifact_id = f"arv2-massive-three-role-{compact}"
    if _ARTIFACT_ID_RE.fullmatch(artifact_id) is None:
        raise MassiveCaptureError("capture timestamp could not form an artifact ID")
    return artifact_id


def _persist_capture(
    root: Path,
    capture: CaptureBinding,
    page_limit: int,
    capture_transport: str,
) -> tuple[Path, str]:
    require_capture_binding(capture)
    retained_bytes = sum(
        len(page.raw_response_bytes or b"") + len(page.provider_rows_bytes)
        for page in capture.pages
    )
    if retained_bytes > MAX_CAPTURE_RETAINED_BYTES:
        raise MassiveCaptureError("capture exceeds the reviewed retained-byte budget")
    root, root_fd = _open_directory_path(
        Path(root), create=True, name="artifact root"
    )
    assert root_fd is not None
    artifact_id = _artifact_id_from_timestamp(capture.capture_started_at)
    artifact_path = root / artifact_id
    staging_name = f".{artifact_id}.incomplete"
    staging_fd: int | None = None
    pages_fd: int | None = None
    try:
        if _entry_exists_at(root_fd, artifact_id):
            raise MassiveCaptureError(
                "timestamped capture already exists; overwrite refused"
            )
        if _entry_exists_at(root_fd, staging_name):
            raise MassiveCaptureError(
                "timestamped incomplete capture already exists; overwrite refused"
            )
        try:
            os.mkdir(staging_name, 0o700, dir_fd=root_fd)
            staging_fd = _open_private_child_directory(
                root_fd, staging_name, "capture staging directory"
            )
            os.mkdir("pages", 0o700, dir_fd=staging_fd)
            pages_fd = _open_private_child_directory(
                staging_fd, "pages", "capture pages"
            )
        except OSError as exc:
            raise MassiveCaptureError(
                "timestamped capture staging could not be created"
            ) from exc

        manifest = _manifest_record(
            artifact_id, capture, page_limit, capture_transport
        )
        expected_page_files: set[str] = set()
        for page, record in zip(capture.pages, manifest["pages"], strict=True):
            assert isinstance(record, dict)
            if page.raw_response_bytes is None:
                raise MassiveCaptureError(
                    "raw response bytes disappeared before persistence"
                )
            raw_name = Path(str(record["raw_response_file"])).name
            rows_name = Path(str(record["provider_rows_file"])).name
            expected_page_files.update({raw_name, rows_name})
            _exclusive_private_write_at(
                pages_fd,
                raw_name,
                page.raw_response_bytes,
                "raw response page",
            )
            _exclusive_private_write_at(
                pages_fd,
                rows_name,
                page.provider_rows_bytes,
                "canonical provider-row page",
            )
        _fsync_fd(pages_fd, "capture pages")
        manifest_bytes = canonical_json_bytes(manifest)
        _exclusive_private_write_at(
            staging_fd,
            MANIFEST_FILENAME,
            manifest_bytes,
            "capture manifest",
        )
        manifest_sha256 = sha256_bytes(manifest_bytes)
        digest_bytes = (manifest_sha256 + "\n").encode("ascii")
        _exclusive_private_write_at(
            staging_fd,
            MANIFEST_DIGEST_FILENAME,
            digest_bytes,
            "capture manifest digest",
        )
        _validate_inventory_at(staging_fd, pages_fd, expected_page_files)
        _require_pinned_child_identity(
            root_fd, staging_name, staging_fd, "capture staging directory"
        )
        _fsync_fd(staging_fd, "capture staging artifact")
        try:
            os.rename(
                staging_name,
                artifact_id,
                src_dir_fd=root_fd,
                dst_dir_fd=root_fd,
            )
        except OSError as exc:
            raise MassiveCaptureError(
                "timestamped capture publication failed or overwrite was refused"
            ) from exc
        try:
            _require_pinned_child_identity(
                root_fd, artifact_id, staging_fd, "published capture artifact"
            )
        except MassiveCaptureError as identity_error:
            raise MassiveCaptureError(
                "capture publication state is ambiguous after identity verification failure"
            ) from identity_error
        try:
            _fsync_fd(root_fd, "capture root publication")
        except MassiveCaptureError as sync_error:
            try:
                os.rename(
                    artifact_id,
                    staging_name,
                    src_dir_fd=root_fd,
                    dst_dir_fd=root_fd,
                )
            except OSError as rollback_error:
                raise MassiveCaptureError(
                    "capture publication state is ambiguous after root-sync failure"
                ) from rollback_error
            raise sync_error
        return artifact_path, manifest_sha256
    finally:
        if pages_fd is not None:
            os.close(pages_fd)
        if staging_fd is not None:
            os.close(staging_fd)
        os.close(root_fd)


def _best_effort_cleanup_spooled_staging(
    *,
    root_fd: int,
    staging_name: str,
    staging_fd: int | None,
    pages_fd: int | None,
    expected_page_files: set[str],
) -> None:
    """Remove only private files created by a failed spooled capture.

    Unexpected or link-like entries are deliberately left in the hidden
    staging directory rather than deleted.  Cleanup must never replace the
    primary provider or publication refusal.
    """

    if staging_fd is None:
        # ``mkdir`` may have succeeded immediately before opening the pinned
        # descriptor failed.  Remove only that still-empty, private,
        # owner-held directory; a substituted or populated entry is left
        # untouched and remains non-publishable.
        try:
            metadata = os.stat(
                staging_name, dir_fd=root_fd, follow_symlinks=False
            )
            if (
                stat.S_ISDIR(metadata.st_mode)
                and stat.S_IMODE(metadata.st_mode) == 0o700
                and (
                    not hasattr(os, "getuid") or metadata.st_uid == os.getuid()
                )
            ):
                os.rmdir(staging_name, dir_fd=root_fd)
        except OSError:
            pass
        return
    if pages_fd is not None:
        try:
            names = set(os.listdir(pages_fd))
        except OSError:
            names = set()
        for filename in sorted(names.intersection(expected_page_files)):
            try:
                metadata = os.stat(filename, dir_fd=pages_fd, follow_symlinks=False)
                if (
                    stat.S_ISREG(metadata.st_mode)
                    and stat.S_IMODE(metadata.st_mode) == 0o600
                    and metadata.st_nlink == 1
                    and (
                        not hasattr(os, "getuid")
                        or metadata.st_uid == os.getuid()
                    )
                ):
                    os.unlink(filename, dir_fd=pages_fd)
            except OSError:
                pass
    for filename in (MANIFEST_FILENAME, MANIFEST_DIGEST_FILENAME):
        try:
            metadata = os.stat(filename, dir_fd=staging_fd, follow_symlinks=False)
            if (
                stat.S_ISREG(metadata.st_mode)
                and stat.S_IMODE(metadata.st_mode) == 0o600
                and metadata.st_nlink == 1
                and (
                    not hasattr(os, "getuid") or metadata.st_uid == os.getuid()
                )
            ):
                os.unlink(filename, dir_fd=staging_fd)
        except OSError:
            pass
    try:
        os.rmdir("pages", dir_fd=staging_fd)
    except OSError:
        pass
    try:
        os.rmdir(staging_name, dir_fd=root_fd)
    except OSError:
        pass


def _capture_massive_history_spooled_core(
    *,
    requested_first_event_date: str,
    requested_last_event_date: str,
    artifact_root: Path,
    page_limit: int,
    session: object,
    clock: Callable[[], datetime],
    api_key: str,
    capture_transport: str,
    close_owned_session: bool,
) -> SpooledMassiveCapture:
    """Acquire one capture while retaining at most one source page in memory."""

    first, last, root = _validated_capture_arguments(
        requested_first_event_date=requested_first_event_date,
        requested_last_event_date=requested_last_event_date,
        artifact_root=Path(artifact_root),
        page_limit=page_limit,
        build_input_pair=False,
    )
    if (
        type(api_key) is not str
        or not api_key
        or type(capture_transport) is not str
        or capture_transport not in _TRANSPORTS
        or type(close_owned_session) is not bool
    ):
        raise MassiveCaptureError("spooled capture configuration is not reviewed")

    started_at = _now_utc(clock)
    last_observed_at = parse_utc_timestamp(started_at, "capture_started_at")
    artifact_id = _artifact_id_from_timestamp(started_at)
    root, root_fd = _open_directory_path(root, create=True, name="artifact root")
    assert root_fd is not None
    artifact_path = root / artifact_id
    staging_name = f".{artifact_id}.incomplete"
    staging_fd: int | None = None
    pages_fd: int | None = None
    expected_page_files: set[str] = set()
    published = False
    cleanup_safe = True
    session_closed = False
    headers: object | None = None
    had_previous = False
    previous: object | None = None
    authorization_active = False
    try:
        if _entry_exists_at(root_fd, artifact_id) or _entry_exists_at(
            root_fd, staging_name
        ):
            raise MassiveCaptureError(
                "timestamped capture or incomplete staging already exists"
            )
        try:
            os.mkdir(staging_name, 0o700, dir_fd=root_fd)
            staging_fd = _open_private_child_directory(
                root_fd, staging_name, "capture staging directory"
            )
            os.mkdir("pages", 0o700, dir_fd=staging_fd)
            pages_fd = _open_private_child_directory(
                staging_fd, "pages", "capture pages"
            )
        except OSError as exc:
            raise MassiveCaptureError(
                "timestamped capture staging could not be created"
            ) from exc

        headers, had_previous, previous = _set_session_authorization(
            session, api_key
        )
        authorization_active = True
        page_records: list[dict[str, object]] = []
        stored_bytes = 0
        stored_rows = 0
        seen_cursor_hashes: dict[MassiveSourceRole, set[str]] = {
            role: set() for role in ROLE_ORDER
        }
        seen_response_hashes: dict[MassiveSourceRole, set[str]] = {
            role: set() for role in ROLE_ORDER
        }

        for role in ROLE_ORDER:
            endpoint = BASE_URL + ENDPOINT_PATHS[role]
            query_bytes = render_redacted_capture_query_bytes(
                source_role=role,
                requested_first_event_date=first.isoformat(),
                requested_last_event_date=last.isoformat(),
                limit=page_limit,
            )
            request_url = endpoint
            request_cursor_sha256: str | None = None
            first_request = True
            page_number = 1
            while True:
                if len(page_records) >= MAX_ARTIFACT_PAGES:
                    raise MassiveCaptureError(
                        "capture exceeded the bounded page count"
                    )
                params: dict[str, object] | None = None
                if first_request:
                    params = {
                        "date.gte": first.isoformat(),
                        "date.lte": last.isoformat(),
                        "limit": page_limit,
                        "sort": "date.asc",
                    }
                raw_response = _request_page(
                    session,
                    request_url,
                    params=params,
                    source_role=role,
                )
                _assert_response_does_not_echo_credential(raw_response, api_key)
                received_at = _now_utc(clock)
                received_instant = parse_utc_timestamp(
                    received_at, "response_received_at"
                )
                if received_instant < last_observed_at:
                    raise MassiveCaptureError(
                        "capture page receipt times must be nondecreasing"
                    )
                last_observed_at = received_instant
                response_sha256 = sha256_bytes(raw_response)
                if response_sha256 in seen_response_hashes[role]:
                    raise MassiveCaptureError("provider replayed a response page")
                seen_response_hashes[role].add(response_sha256)
                provider_rows_bytes, next_url = _response_rows_and_next_url(
                    raw_response, page_limit=page_limit
                )
                next_cursor_sha256: str | None = None
                validated_next_url: str | None = None
                if next_url is not None:
                    next_cursor_sha256, validated_next_url = (
                        _cursor_hash_and_validated_url(
                            next_url,
                            source_role=role,
                            requested_first_event_date=first.isoformat(),
                            requested_last_event_date=last.isoformat(),
                            page_limit=page_limit,
                        )
                    )
                    if next_cursor_sha256 in seen_cursor_hashes[role]:
                        raise MassiveCaptureError(
                            "provider cursor repeats or cycles"
                        )
                    seen_cursor_hashes[role].add(next_cursor_sha256)
                try:
                    page = bind_capture_page(
                        source_role=role,
                        redacted_query_bytes=query_bytes,
                        page_number=page_number,
                        request_cursor_sha256=request_cursor_sha256,
                        next_cursor_sha256=next_cursor_sha256,
                        terminal_page=next_url is None,
                        response_received_at=received_at,
                        raw_response_sha256=response_sha256,
                        provider_rows_bytes=provider_rows_bytes,
                        raw_response_bytes=raw_response,
                    )
                except (AcceptedRiskInputError, CanonicalEvidenceError) as exc:
                    raise MassiveCaptureError(
                        "provider page failed capture binding"
                    ) from exc
                record = _artifact_page_record(page)
                candidate_bytes = (
                    stored_bytes + len(raw_response) + len(provider_rows_bytes)
                )
                candidate_rows = stored_rows + page.row_count
                if candidate_bytes > MAX_CAPTURE_STORED_BYTES:
                    raise MassiveCaptureError(
                        "capture exceeded the reviewed stored-byte budget"
                    )
                if candidate_rows > MAX_CAPTURE_ROWS:
                    raise MassiveCaptureError(
                        "capture exceeded the reviewed stored-row budget"
                    )
                raw_name = Path(str(record["raw_response_file"])).name
                rows_name = Path(str(record["provider_rows_file"])).name
                expected_page_files.update((raw_name, rows_name))
                _exclusive_private_write_at(
                    pages_fd,
                    raw_name,
                    raw_response,
                    "raw response page",
                )
                _exclusive_private_write_at(
                    pages_fd,
                    rows_name,
                    provider_rows_bytes,
                    "canonical provider-row page",
                )
                _require_pinned_child_identity(
                    staging_fd, "pages", pages_fd, "capture pages"
                )
                # The file bodies and their directory entries are durable
                # before another provider response is requested.
                _fsync_fd(pages_fd, "capture pages checkpoint")
                page_records.append(record)
                stored_bytes = candidate_bytes
                stored_rows = candidate_rows
                # No response or normalized page bytes survive into the next
                # request.  Only the small immutable lineage record remains.
                del page, record, raw_response, provider_rows_bytes
                if validated_next_url is None:
                    break
                request_url = validated_next_url
                request_cursor_sha256 = next_cursor_sha256
                first_request = False
                page_number += 1

        completed_at = _now_utc(clock)
        if parse_utc_timestamp(
            completed_at, "capture_completed_at"
        ) < last_observed_at:
            raise MassiveCaptureError("capture chronology is reversed")
        assert headers is not None
        _restore_session_authorization(
            headers, had_previous, previous, suppress=False
        )
        authorization_active = False
        if close_owned_session:
            try:
                session.close()
            except Exception as exc:
                raise MassiveCaptureError(_sanitized_provider_failure(exc)) from None
            session_closed = True
        page_records_tuple = tuple(page_records)
        manifest = _manifest_from_page_records(
            artifact_id=artifact_id,
            capture_started_at=started_at,
            capture_completed_at=completed_at,
            requested_first_event_date=first.isoformat(),
            requested_last_event_date=last.isoformat(),
            page_records=page_records_tuple,
            page_limit=page_limit,
            capture_transport=capture_transport,
            page_spooled_before_next_request=True,
        )
        manifest_bytes = canonical_json_bytes(manifest)
        if len(manifest_bytes) > MAX_MANIFEST_BYTES:
            raise MassiveCaptureError("capture manifest exceeds the byte limit")
        if stored_bytes + len(manifest_bytes) + 65 > MAX_CAPTURE_STORED_BYTES:
            raise MassiveCaptureError(
                "capture exceeds the reviewed stored-byte budget"
            )
        _exclusive_private_write_at(
            staging_fd, MANIFEST_FILENAME, manifest_bytes, "capture manifest"
        )
        manifest_sha256 = sha256_bytes(manifest_bytes)
        _exclusive_private_write_at(
            staging_fd,
            MANIFEST_DIGEST_FILENAME,
            (manifest_sha256 + "\n").encode("ascii"),
            "capture manifest digest",
        )
        _validate_inventory_at(staging_fd, pages_fd, expected_page_files)
        _require_pinned_child_identity(
            root_fd, staging_name, staging_fd, "capture staging directory"
        )
        _fsync_fd(staging_fd, "capture staging artifact")
        try:
            os.rename(
                staging_name,
                artifact_id,
                src_dir_fd=root_fd,
                dst_dir_fd=root_fd,
            )
        except OSError as exc:
            raise MassiveCaptureError("capture publication failed") from exc
        cleanup_safe = False
        try:
            _require_pinned_child_identity(
                root_fd, artifact_id, staging_fd, "published capture artifact"
            )
        except MassiveCaptureError as identity_error:
            raise MassiveCaptureError(
                "capture publication state is ambiguous after identity verification failure"
            ) from identity_error
        try:
            _fsync_fd(root_fd, "capture root publication")
        except MassiveCaptureError as sync_error:
            try:
                os.rename(
                    artifact_id,
                    staging_name,
                    src_dir_fd=root_fd,
                    dst_dir_fd=root_fd,
                )
            except OSError as rollback_error:
                raise MassiveCaptureError(
                    "capture publication state is ambiguous after root-sync failure"
                ) from rollback_error
            try:
                _fsync_fd(root_fd, "capture root rollback")
            except MassiveCaptureError as rollback_sync_error:
                raise MassiveCaptureError(
                    "capture publication state is ambiguous after rollback sync failure"
                ) from rollback_sync_error
            cleanup_safe = True
            raise sync_error
        published = True
        return SpooledMassiveCapture(
            artifact_path=artifact_path,
            manifest_sha256=manifest_sha256,
            capture_id=str(manifest["capture_id"]),
            capture_sha256=str(manifest["capture_sha256"]),
            total_page_count=int(manifest["total_page_count"]),
            total_row_count=int(manifest["total_row_count"]),
            role_row_counts=tuple(
                (MassiveSourceRole(item["source_role"]), int(item["row_count"]))
                for item in manifest["role_counts"]
            ),
            capture_transport=capture_transport,
        )
    finally:
        if authorization_active and headers is not None:
            _restore_session_authorization(
                headers, had_previous, previous, suppress=True
            )
        if close_owned_session and not session_closed:
            try:
                session.close()
            except Exception:
                pass
        if not published and cleanup_safe:
            _best_effort_cleanup_spooled_staging(
                root_fd=root_fd,
                staging_name=staging_name,
                staging_fd=staging_fd,
                pages_fd=pages_fd,
                expected_page_files=expected_page_files,
            )
        if pages_fd is not None:
            os.close(pages_fd)
        if staging_fd is not None:
            os.close(staging_fd)
        os.close(root_fd)


def _validated_capture_arguments(
    *,
    requested_first_event_date: str,
    requested_last_event_date: str,
    artifact_root: Path,
    page_limit: int,
    build_input_pair: bool,
) -> tuple[object, object, Path]:
    if type(build_input_pair) is not bool or build_input_pair:
        raise MassiveCaptureError(
            "accepted-risk pair construction requires a separately reviewed bounded bridge"
        )
    try:
        first = parse_date(requested_first_event_date, "requested first date")
        last = parse_date(requested_last_event_date, "requested last date")
        require_int(
            page_limit,
            "page_limit",
            minimum=1,
            maximum=MAX_PROVIDER_ROWS_PER_PAGE,
        )
    except CanonicalEvidenceError as exc:
        raise MassiveCaptureError(str(exc)) from exc
    if first > last:
        raise MassiveCaptureError("requested event-date range is reversed")
    root = Path(artifact_root)
    _, descriptor = _open_directory_path(
        root,
        create=False,
        allow_missing=True,
        name="artifact root",
    )
    if descriptor is not None:
        os.close(descriptor)
    return first, last, root


def _set_session_authorization(session: object, key: str) -> tuple[object, bool, object]:
    marker = object()
    try:
        headers = session.headers
        previous = headers.get("Authorization", marker)
        headers["Authorization"] = f"Bearer {key}"
    except Exception as exc:
        raise MassiveCaptureError(_sanitized_provider_failure(exc)) from None
    return headers, previous is not marker, previous


def _restore_session_authorization(
    headers: object,
    had_previous: bool,
    previous: object,
    *,
    suppress: bool,
) -> None:
    try:
        if had_previous:
            headers["Authorization"] = previous
        else:
            headers.pop("Authorization", None)
    except Exception as exc:
        if not suppress:
            raise MassiveCaptureError(_sanitized_provider_failure(exc)) from None


def _acquire_capture(
    *,
    first: object,
    last: object,
    page_limit: int,
    session: object,
    key: str,
    clock: Callable[[], datetime],
) -> CaptureBinding:
    started_at = _now_utc(clock)
    pages = []
    retained_bytes = 0
    seen_cursor_hashes: dict[MassiveSourceRole, set[str]] = {
        role: set() for role in ROLE_ORDER
    }
    seen_response_hashes: dict[MassiveSourceRole, set[str]] = {
        role: set() for role in ROLE_ORDER
    }

    for role in ROLE_ORDER:
        endpoint = BASE_URL + ENDPOINT_PATHS[role]
        query_bytes = render_redacted_capture_query_bytes(
            source_role=role,
            requested_first_event_date=first.isoformat(),
            requested_last_event_date=last.isoformat(),
            limit=page_limit,
        )
        request_url = endpoint
        request_cursor_sha256: str | None = None
        first_request = True
        page_number = 1
        while True:
            if len(pages) >= MAX_ARTIFACT_PAGES:
                raise MassiveCaptureError("capture exceeded the bounded page count")
            params: dict[str, object] | None = None
            if first_request:
                params = {
                    "date.gte": first.isoformat(),
                    "date.lte": last.isoformat(),
                    "limit": page_limit,
                    "sort": "date.asc",
                }
            raw_response = _request_page(
                session,
                request_url,
                params=params,
                source_role=role,
            )
            _assert_response_does_not_echo_credential(raw_response, key)
            received_at = _now_utc(clock)
            response_sha256 = sha256_bytes(raw_response)
            if response_sha256 in seen_response_hashes[role]:
                raise MassiveCaptureError("provider replayed a response page")
            seen_response_hashes[role].add(response_sha256)
            provider_rows_bytes, next_url = _response_rows_and_next_url(
                raw_response, page_limit=page_limit
            )
            retained_bytes += len(raw_response) + len(provider_rows_bytes)
            if retained_bytes > MAX_CAPTURE_RETAINED_BYTES:
                raise MassiveCaptureError(
                    "capture exceeded the reviewed retained-byte budget"
                )
            next_cursor_sha256: str | None = None
            validated_next_url: str | None = None
            if next_url is not None:
                next_cursor_sha256, validated_next_url = _cursor_hash_and_validated_url(
                    next_url,
                    source_role=role,
                    requested_first_event_date=first.isoformat(),
                    requested_last_event_date=last.isoformat(),
                    page_limit=page_limit,
                )
                if next_cursor_sha256 in seen_cursor_hashes[role]:
                    raise MassiveCaptureError("provider cursor repeats or cycles")
                seen_cursor_hashes[role].add(next_cursor_sha256)
            try:
                page = bind_capture_page(
                    source_role=role,
                    redacted_query_bytes=query_bytes,
                    page_number=page_number,
                    request_cursor_sha256=request_cursor_sha256,
                    next_cursor_sha256=next_cursor_sha256,
                    terminal_page=next_url is None,
                    response_received_at=received_at,
                    raw_response_sha256=response_sha256,
                    provider_rows_bytes=provider_rows_bytes,
                    raw_response_bytes=raw_response,
                )
            except (AcceptedRiskInputError, CanonicalEvidenceError) as exc:
                raise MassiveCaptureError("provider page failed capture binding") from exc
            pages.append(page)
            if validated_next_url is None:
                break
            request_url = validated_next_url
            request_cursor_sha256 = next_cursor_sha256
            first_request = False
            page_number += 1

    completed_at = _now_utc(clock)
    try:
        capture = build_capture_binding(
            capture_started_at=started_at,
            capture_completed_at=completed_at,
            pages=tuple(pages),
        )
    except (AcceptedRiskInputError, CanonicalEvidenceError) as exc:
        raise MassiveCaptureError("complete provider capture failed authentication") from exc
    return capture


def _acquire_with_authorization(
    *,
    first: object,
    last: object,
    page_limit: int,
    session: object,
    key: str,
    clock: Callable[[], datetime],
) -> CaptureBinding:
    headers, had_previous, previous = _set_session_authorization(session, key)
    try:
        capture = _acquire_capture(
            first=first,
            last=last,
            page_limit=page_limit,
            session=session,
            key=key,
            clock=clock,
        )
    except BaseException:
        _restore_session_authorization(
            headers, had_previous, previous, suppress=True
        )
        raise
    _restore_session_authorization(headers, had_previous, previous, suppress=False)
    return capture


def _persist_and_return(
    *,
    artifact_root: Path,
    capture: CaptureBinding,
    page_limit: int,
    capture_transport: str,
) -> LoadedMassiveCapture:
    artifact_path, manifest_sha256 = _persist_capture(
        artifact_root, capture, page_limit, capture_transport
    )
    return LoadedMassiveCapture(
        artifact_path=artifact_path,
        manifest_sha256=manifest_sha256,
        capture=capture,
        accepted_risk_input_pair=None,
        capture_transport=capture_transport,
    )


def capture_massive_history(
    *,
    requested_first_event_date: str,
    requested_last_event_date: str,
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
    page_limit: int = DEFAULT_PAGE_LIMIT,
    build_input_pair: bool = False,
) -> SpooledMassiveCapture:
    """Page-spool through one owned default-TLS Session and publish atomically."""

    _require_operational_artifact_scope(Path(artifact_root))
    _first, _last, preflight_root = _validated_capture_arguments(
        requested_first_event_date=requested_first_event_date,
        requested_last_event_date=requested_last_event_date,
        artifact_root=Path(artifact_root),
        page_limit=page_limit,
        build_input_pair=build_input_pair,
    )
    key = _api_key()
    session = _OwnedSessionGuard(_new_session())
    try:
        return _capture_massive_history_spooled_core(
            requested_first_event_date=requested_first_event_date,
            requested_last_event_date=requested_last_event_date,
            artifact_root=preflight_root,
            page_limit=page_limit,
            session=session,
            clock=lambda: datetime.now(timezone.utc),
            api_key=key,
            capture_transport=PRODUCTION_TRANSPORT,
            close_owned_session=True,
        )
    finally:
        try:
            session.close()
        except Exception:
            pass


def _capture_massive_history_for_test(
    *,
    requested_first_event_date: str,
    requested_last_event_date: str,
    artifact_root: Path,
    page_limit: int = DEFAULT_PAGE_LIMIT,
    session: object,
    clock: Callable[[], datetime],
    api_key: str,
    build_input_pair: bool = False,
) -> LoadedMassiveCapture:
    """Offline-only seam; never reads a process credential or claims production I/O."""

    first, last, preflight_root = _validated_capture_arguments(
        requested_first_event_date=requested_first_event_date,
        requested_last_event_date=requested_last_event_date,
        artifact_root=Path(artifact_root),
        page_limit=page_limit,
        build_input_pair=build_input_pair,
    )
    if type(api_key) is not str or not api_key.startswith("offline-test-"):
        raise MassiveCaptureError("offline test transport requires a synthetic key")
    capture = _acquire_with_authorization(
        first=first,
        last=last,
        page_limit=page_limit,
        session=session,
        key=api_key,
        clock=clock,
    )
    return _persist_and_return(
        artifact_root=preflight_root,
        capture=capture,
        page_limit=page_limit,
        capture_transport=TEST_TRANSPORT,
    )


def _capture_massive_history_spooled_for_test(
    *,
    requested_first_event_date: str,
    requested_last_event_date: str,
    artifact_root: Path,
    page_limit: int = DEFAULT_PAGE_LIMIT,
    session: object,
    clock: Callable[[], datetime],
    api_key: str,
) -> SpooledMassiveCapture:
    """Offline seam over the exact production page-spooling implementation."""

    if type(api_key) is not str or not api_key.startswith("offline-test-"):
        raise MassiveCaptureError("offline test transport requires a synthetic key")
    return _capture_massive_history_spooled_core(
        requested_first_event_date=requested_first_event_date,
        requested_last_event_date=requested_last_event_date,
        artifact_root=Path(artifact_root),
        page_limit=page_limit,
        session=session,
        clock=clock,
        api_key=api_key,
        capture_transport=TEST_TRANSPORT,
        close_owned_session=False,
    )


def _parse_manifest(payload: bytes, artifact_path: Path) -> dict[str, Any]:
    try:
        value = require_canonical_json_bytes(payload, "Massive capture manifest")
    except CanonicalEvidenceError as exc:
        raise MassiveCaptureError("capture manifest is not canonical JSON") from exc
    if type(value) is not dict:
        raise MassiveCaptureError("capture manifest must be an object")
    try:
        require_exact_keys(value, _MANIFEST_KEYS, "Massive capture manifest")
        if value["schema"] != ARTIFACT_SCHEMA:
            raise MassiveCaptureError("capture manifest schema changed")
        require_identifier(value["artifact_id"], "artifact_id")
        if (
            _ARTIFACT_ID_RE.fullmatch(value["artifact_id"]) is None
            or value["artifact_id"] != artifact_path.name
        ):
            raise MassiveCaptureError("artifact ID does not match its directory")
        require_identifier(value["capture_id"], "capture_id")
        require_sha256(value["capture_sha256"], "capture_sha256")
        parse_utc_timestamp(value["capture_started_at"], "capture_started_at")
        parse_utc_timestamp(value["capture_completed_at"], "capture_completed_at")
        if value["artifact_id"] != _artifact_id_from_timestamp(
            value["capture_started_at"]
        ):
            raise MassiveCaptureError(
                "artifact ID timestamp does not match capture chronology"
            )
        first = parse_date(
            value["requested_first_event_date"], "requested_first_event_date"
        )
        last = parse_date(
            value["requested_last_event_date"], "requested_last_event_date"
        )
        if first > last:
            raise MassiveCaptureError("manifest date range is reversed")
        require_int(
            value["page_limit"],
            "page_limit",
            minimum=1,
            maximum=MAX_PROVIDER_ROWS_PER_PAGE,
        )
        stored_limit = require_int(
            value["stored_capture_byte_limit"],
            "stored_capture_byte_limit",
            minimum=1,
        )
        if stored_limit != MAX_CAPTURE_STORED_BYTES:
            raise MassiveCaptureError("manifest stored-byte budget changed")
        stored_row_limit = require_int(
            value["stored_capture_row_limit"],
            "stored_capture_row_limit",
            minimum=1,
        )
        if stored_row_limit != MAX_CAPTURE_ROWS:
            raise MassiveCaptureError("manifest stored-row budget changed")
        if (
            type(value["capture_transport"]) is not str
            or value["capture_transport"] not in _TRANSPORTS
        ):
            raise MassiveCaptureError("manifest capture transport is not reviewed")
        for key, expected in (
            ("immutable", True),
            ("private_artifact", True),
            ("cursor_material_persisted_outside_raw_provider_responses", False),
            ("outcome_access_performed", False),
            ("quantconnect_io_performed", False),
        ):
            require_exact_bool(value[key], key)
            if value[key] is not expected:
                raise MassiveCaptureError(f"manifest {key} boundary changed")
        for key in (
            "page_spooled_before_next_request",
            "full_capture_retained_in_memory",
        ):
            require_exact_bool(value[key], key)
        if value["page_spooled_before_next_request"] is value[
            "full_capture_retained_in_memory"
        ]:
            raise MassiveCaptureError("manifest capture storage mode is inconsistent")
        if value["capture_transport"] == PRODUCTION_TRANSPORT and (
            value["page_spooled_before_next_request"] is not True
            or value["full_capture_retained_in_memory"] is not False
        ):
            raise MassiveCaptureError("production capture was not page-spooled")
        require_exact_bool(value["provider_io_read_only"], "provider_io_read_only")
        if value["provider_io_read_only"] is not (
            value["capture_transport"] == PRODUCTION_TRANSPORT
        ):
            raise MassiveCaptureError("manifest provider-I/O classification changed")
        if value["role_order"] != [role.value for role in ROLE_ORDER]:
            raise MassiveCaptureError("manifest source-role order changed")
        for key in (
            "total_page_count",
            "total_row_count",
            "raw_response_total_byte_count",
            "provider_rows_total_byte_count",
        ):
            require_int(value[key], key, minimum=0)
        if (
            value["raw_response_total_byte_count"]
            + value["provider_rows_total_byte_count"]
            + len(payload)
            + 65
            > MAX_CAPTURE_STORED_BYTES
        ):
            raise MassiveCaptureError("manifest exceeds the stored-byte budget")
        if value["total_row_count"] > MAX_CAPTURE_ROWS:
            raise MassiveCaptureError("manifest exceeds the stored-row budget")
    except CanonicalEvidenceError as exc:
        raise MassiveCaptureError("capture manifest field is invalid") from exc
    if type(value["role_counts"]) is not list or len(value["role_counts"]) != 3:
        raise MassiveCaptureError("manifest role counts are incomplete")
    if type(value["pages"]) is not list or not value["pages"]:
        raise MassiveCaptureError("manifest page inventory is empty")
    if len(value["pages"]) > MAX_ARTIFACT_PAGES:
        raise MassiveCaptureError("manifest page inventory exceeds the bound")
    return value


def _expected_page_names(role: MassiveSourceRole, page_number: int) -> tuple[str, str]:
    return (
        f"pages/{_role_page_filename(role, page_number, 'raw.json')}",
        f"pages/{_role_page_filename(role, page_number, 'rows.jsonl')}",
    )


def _require_private_regular_metadata(metadata: os.stat_result, name: str) -> None:
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
    ):
        raise MassiveCaptureError(f"{name} must be an owner-held private regular file")


def _validate_inventory_at(
    root_fd: int,
    pages_fd: int,
    expected_page_files: set[str],
) -> None:
    try:
        root_names = set(os.listdir(root_fd))
        page_names = set(os.listdir(pages_fd))
    except OSError as exc:
        raise MassiveCaptureError("capture artifact inventory is unreadable") from exc
    if root_names != {"pages", MANIFEST_FILENAME, MANIFEST_DIGEST_FILENAME}:
        raise MassiveCaptureError("capture artifact root inventory does not match")
    if page_names != expected_page_files:
        raise MassiveCaptureError("capture artifact page inventory does not match manifest")
    _require_pinned_child_identity(root_fd, "pages", pages_fd, "capture pages")
    try:
        for filename in (MANIFEST_FILENAME, MANIFEST_DIGEST_FILENAME):
            _require_private_regular_metadata(
                os.stat(filename, dir_fd=root_fd, follow_symlinks=False),
                filename,
            )
        for filename in expected_page_files:
            _require_private_regular_metadata(
                os.stat(filename, dir_fd=pages_fd, follow_symlinks=False),
                "capture page",
            )
        if set(os.listdir(root_fd)) != root_names or set(os.listdir(pages_fd)) != page_names:
            raise MassiveCaptureError("capture artifact inventory changed during inspection")
    except MassiveCaptureError:
        raise
    except OSError as exc:
        raise MassiveCaptureError("capture artifact inventory changed") from exc


def load_massive_capture_artifact(
    artifact_path: Path, *, build_input_pair: bool = False
) -> LoadedMassiveCapture:
    """Verify one immutable capture and reconstruct its in-memory authority."""

    if type(build_input_pair) is not bool or build_input_pair:
        raise MassiveCaptureError(
            "accepted-risk pair construction requires a separately reviewed bounded bridge"
        )
    return _load_massive_capture_artifact_bounded(
        artifact_path,
        maximum_page_count=MAX_ARTIFACT_PAGES,
        maximum_row_count=MAX_ARTIFACT_PAGES * MAX_PROVIDER_ROWS_PER_PAGE,
        maximum_retained_byte_count=MAX_CAPTURE_RETAINED_BYTES,
        maximum_provider_rows_byte_count=MAX_CAPTURE_RETAINED_BYTES,
    )


def _load_massive_capture_artifact_bounded(
    artifact_path: Path,
    *,
    maximum_page_count: int,
    maximum_row_count: int,
    maximum_retained_byte_count: int,
    maximum_provider_rows_byte_count: int,
) -> LoadedMassiveCapture:
    """Private bridge seam that applies aggregate limits before page reads.

    Every supplied limit can only narrow the capture adapter's own immutable
    ceilings.  The values are checked before opening the artifact and again
    against the one authenticated manifest read inside the pinned directory,
    so a path or manifest swap cannot turn a small preflight into a larger
    materialization.
    """

    limits = (
        (
            "maximum_page_count",
            maximum_page_count,
            MAX_ARTIFACT_PAGES,
        ),
        (
            "maximum_row_count",
            maximum_row_count,
            MAX_ARTIFACT_PAGES * MAX_PROVIDER_ROWS_PER_PAGE,
        ),
        (
            "maximum_retained_byte_count",
            maximum_retained_byte_count,
            MAX_CAPTURE_RETAINED_BYTES,
        ),
        (
            "maximum_provider_rows_byte_count",
            maximum_provider_rows_byte_count,
            MAX_CAPTURE_RETAINED_BYTES,
        ),
    )
    for name, value, ceiling in limits:
        if type(value) is not int or value < 1 or value > ceiling:
            raise MassiveCaptureError(
                f"{name} must be an exact positive integer no greater than {ceiling}"
            )
    root, root_fd = _open_directory_path(
        Path(artifact_path), create=False, name="capture artifact"
    )
    assert root_fd is not None
    try:
        pages_fd = _open_private_child_directory(
            root_fd, "pages", "capture pages"
        )
    except BaseException:
        os.close(root_fd)
        raise
    try:
        return _load_massive_capture_artifact_from_fds(
            root,
            root_fd,
            pages_fd,
            maximum_page_count=maximum_page_count,
            maximum_row_count=maximum_row_count,
            maximum_retained_byte_count=maximum_retained_byte_count,
            maximum_provider_rows_byte_count=maximum_provider_rows_byte_count,
        )
    finally:
        os.close(pages_fd)
        os.close(root_fd)


def _load_massive_capture_artifact_from_fds(
    root: Path,
    root_fd: int,
    pages_fd: int,
    *,
    maximum_page_count: int = MAX_ARTIFACT_PAGES,
    maximum_row_count: int = MAX_ARTIFACT_PAGES * MAX_PROVIDER_ROWS_PER_PAGE,
    maximum_retained_byte_count: int = MAX_CAPTURE_RETAINED_BYTES,
    maximum_provider_rows_byte_count: int = MAX_CAPTURE_RETAINED_BYTES,
) -> LoadedMassiveCapture:
    _require_pinned_child_identity(root_fd, "pages", pages_fd, "capture pages")
    manifest_bytes = _read_private_regular_at(
        root_fd,
        MANIFEST_FILENAME,
        maximum_bytes=MAX_MANIFEST_BYTES,
        name="capture manifest",
    )
    digest_bytes = _read_private_regular_at(
        root_fd,
        MANIFEST_DIGEST_FILENAME,
        maximum_bytes=65,
        name="capture manifest digest",
    )
    if (
        len(digest_bytes) != 65
        or digest_bytes[-1:] != b"\n"
        or re.fullmatch(rb"[0-9a-f]{64}\n", digest_bytes) is None
        or digest_bytes[:-1].decode("ascii") != sha256_bytes(manifest_bytes)
    ):
        raise MassiveCaptureError("capture manifest digest does not authenticate bytes")
    manifest = _parse_manifest(manifest_bytes, root)
    if len(manifest["pages"]) > maximum_page_count:
        raise MassiveCaptureError("capture exceeds the bridge page-count budget")
    if manifest["total_row_count"] > maximum_row_count:
        raise MassiveCaptureError("capture exceeds the bridge row-count budget")
    if (
        manifest["raw_response_total_byte_count"]
        + manifest["provider_rows_total_byte_count"]
        > maximum_retained_byte_count
    ):
        raise MassiveCaptureError("capture exceeds the bridge retained-byte budget")
    if (
        manifest["provider_rows_total_byte_count"]
        > maximum_provider_rows_byte_count
    ):
        raise MassiveCaptureError(
            "capture exceeds the bridge provider-row byte budget"
        )
    expected_page_files: set[str] = set()
    role_counts: list[dict[str, object]] = []
    for index, raw_count in enumerate(manifest["role_counts"]):
        if type(raw_count) is not dict:
            raise MassiveCaptureError("manifest role count must be an object")
        try:
            require_exact_keys(raw_count, _ROLE_COUNT_KEYS, "manifest role count")
            role = ROLE_ORDER[index]
            if raw_count["source_role"] != role.value:
                raise MassiveCaptureError("manifest role counts are out of order")
            require_int(raw_count["page_count"], "role page_count", minimum=1)
            require_int(raw_count["row_count"], "role row_count", minimum=0)
        except CanonicalEvidenceError as exc:
            raise MassiveCaptureError("manifest role count is invalid") from exc
        role_counts.append(raw_count)

    query_bytes = {
        role: render_redacted_capture_query_bytes(
            source_role=role,
            requested_first_event_date=manifest["requested_first_event_date"],
            requested_last_event_date=manifest["requested_last_event_date"],
            limit=manifest["page_limit"],
        )
        for role in ROLE_ORDER
    }
    pages = []
    observed_role_pages = {role: 0 for role in ROLE_ORDER}
    observed_role_rows = {role: 0 for role in ROLE_ORDER}
    raw_total = 0
    rows_total = 0
    declared_row_total = 0
    prior_role_index = -1
    expected_page_number = 0
    for raw_page in manifest["pages"]:
        if type(raw_page) is not dict:
            raise MassiveCaptureError("manifest page must be an object")
        try:
            require_exact_keys(raw_page, _PAGE_KEYS, "manifest page")
            role = MassiveSourceRole(raw_page["source_role"])
        except (CanonicalEvidenceError, TypeError, ValueError) as exc:
            raise MassiveCaptureError("manifest page source role is invalid") from exc
        role_index = ROLE_ORDER.index(role)
        page_number = raw_page["page_number"]
        try:
            require_int(page_number, "page_number", minimum=1)
        except CanonicalEvidenceError as exc:
            raise MassiveCaptureError("manifest page number is invalid") from exc
        if role_index < prior_role_index:
            raise MassiveCaptureError("manifest pages are not in canonical role order")
        if role_index != prior_role_index:
            if role_index != prior_role_index + 1:
                raise MassiveCaptureError("manifest skipped a source role")
            expected_page_number = 1
            prior_role_index = role_index
        if page_number != expected_page_number:
            raise MassiveCaptureError("manifest pages are not contiguous from one")
        expected_page_number += 1
        if raw_page["endpoint_path"] != ENDPOINT_PATHS[role]:
            raise MassiveCaptureError("manifest endpoint path changed")
        if raw_page["redacted_query_sha256"] != sha256_bytes(query_bytes[role]):
            raise MassiveCaptureError("manifest query binding changed")
        expected_raw, expected_rows = _expected_page_names(role, page_number)
        if (
            raw_page["raw_response_file"] != expected_raw
            or raw_page["provider_rows_file"] != expected_rows
        ):
            raise MassiveCaptureError("manifest page filenames are not canonical")
        raw_filename = Path(expected_raw).name
        rows_filename = Path(expected_rows).name
        expected_page_files.update({raw_filename, rows_filename})
        try:
            raw_byte_count = require_int(
                raw_page["raw_response_byte_count"],
                "raw response byte count",
                minimum=0,
                maximum=MAX_RAW_RESPONSE_BYTES,
            )
            rows_byte_count = require_int(
                raw_page["provider_rows_byte_count"],
                "provider rows byte count",
                minimum=0,
                maximum=MAX_PROVIDER_ROWS_BYTES,
            )
            require_sha256(raw_page["raw_response_sha256"], "raw response sha256")
            require_sha256(raw_page["provider_rows_sha256"], "provider rows sha256")
            declared_row_count = require_int(
                raw_page["row_count"],
                "row_count",
                minimum=0,
                maximum=manifest["page_limit"],
            )
            require_exact_bool(raw_page["terminal_page"], "terminal_page")
            parse_utc_timestamp(raw_page["response_received_at"], "response_received_at")
            for key in ("request_cursor_sha256", "next_cursor_sha256"):
                if raw_page[key] is not None:
                    require_sha256(raw_page[key], key)
        except CanonicalEvidenceError as exc:
            raise MassiveCaptureError("manifest page field is invalid") from exc
        if (
            raw_total
            + rows_total
            + raw_byte_count
            + rows_byte_count
            > maximum_retained_byte_count
        ):
            raise MassiveCaptureError(
                "capture exceeds the bridge retained-byte budget"
            )
        if rows_total + rows_byte_count > maximum_provider_rows_byte_count:
            raise MassiveCaptureError(
                "capture exceeds the bridge provider-row byte budget"
            )
        if declared_row_total + declared_row_count > maximum_row_count:
            raise MassiveCaptureError("capture exceeds the bridge row-count budget")
        raw_bytes = _read_private_regular_at(
            pages_fd,
            raw_filename,
            maximum_bytes=raw_byte_count,
            name="raw response page",
        )
        rows_bytes = _read_private_regular_at(
            pages_fd,
            rows_filename,
            maximum_bytes=rows_byte_count,
            name="canonical provider-row page",
        )
        if (
            len(raw_bytes) != raw_byte_count
            or sha256_bytes(raw_bytes) != raw_page["raw_response_sha256"]
            or len(rows_bytes) != rows_byte_count
            or sha256_bytes(rows_bytes) != raw_page["provider_rows_sha256"]
        ):
            raise MassiveCaptureError("persisted page byte count or hash changed")
        reconstructed_rows, raw_next_url = _response_rows_and_next_url(
            raw_bytes, page_limit=manifest["page_limit"]
        )
        if reconstructed_rows != rows_bytes:
            raise MassiveCaptureError(
                "persisted provider rows are not the canonical ordered extraction"
            )
        if raw_next_url is None:
            reconstructed_next_cursor_sha256 = None
        else:
            reconstructed_next_cursor_sha256, _ = _cursor_hash_and_validated_url(
                raw_next_url,
                source_role=role,
                requested_first_event_date=manifest[
                    "requested_first_event_date"
                ],
                requested_last_event_date=manifest["requested_last_event_date"],
                page_limit=manifest["page_limit"],
            )
        if reconstructed_next_cursor_sha256 != raw_page["next_cursor_sha256"]:
            raise MassiveCaptureError(
                "manifest cursor hash does not match the exact provider response"
            )
        try:
            page = bind_capture_page(
                source_role=role,
                redacted_query_bytes=query_bytes[role],
                page_number=page_number,
                request_cursor_sha256=raw_page["request_cursor_sha256"],
                next_cursor_sha256=raw_page["next_cursor_sha256"],
                terminal_page=raw_page["terminal_page"],
                response_received_at=raw_page["response_received_at"],
                raw_response_sha256=raw_page["raw_response_sha256"],
                provider_rows_bytes=rows_bytes,
                raw_response_bytes=raw_bytes,
            )
        except (AcceptedRiskInputError, CanonicalEvidenceError) as exc:
            raise MassiveCaptureError("persisted page failed capture binding") from exc
        if page.endpoint_identifier != raw_page["endpoint_identifier"]:
            raise MassiveCaptureError("manifest endpoint identifier changed")
        pages.append(page)
        observed_role_pages[role] += 1
        observed_role_rows[role] += page.row_count
        declared_row_total += declared_row_count
        raw_total += len(raw_bytes)
        rows_total += len(rows_bytes)
        if (
            raw_total + rows_total > maximum_retained_byte_count
            or rows_total > maximum_provider_rows_byte_count
            or sum(observed_role_rows.values()) > maximum_row_count
        ):
            raise MassiveCaptureError("capture exceeds the active bridge budget")

    if prior_role_index != len(ROLE_ORDER) - 1:
        raise MassiveCaptureError("manifest did not contain every source role")
    _validate_inventory_at(root_fd, pages_fd, expected_page_files)
    for index, role in enumerate(ROLE_ORDER):
        if (
            role_counts[index]["page_count"] != observed_role_pages[role]
            or role_counts[index]["row_count"] != observed_role_rows[role]
        ):
            raise MassiveCaptureError("manifest role counts do not match pages")
    if (
        manifest["total_page_count"] != len(pages)
        or manifest["total_row_count"] != sum(page.row_count for page in pages)
        or manifest["raw_response_total_byte_count"] != raw_total
        or manifest["provider_rows_total_byte_count"] != rows_total
    ):
        raise MassiveCaptureError("manifest aggregate counts do not match pages")
    try:
        capture = build_capture_binding(
            capture_started_at=manifest["capture_started_at"],
            capture_completed_at=manifest["capture_completed_at"],
            pages=tuple(pages),
        )
    except (AcceptedRiskInputError, CanonicalEvidenceError) as exc:
        raise MassiveCaptureError("persisted capture failed authentication") from exc
    if (
        capture.capture_id != manifest["capture_id"]
        or capture.capture_sha256 != manifest["capture_sha256"]
        or capture.requested_first_event_date
        != manifest["requested_first_event_date"]
        or capture.requested_last_event_date != manifest["requested_last_event_date"]
    ):
        raise MassiveCaptureError("manifest capture identity does not reconstruct")
    _validate_inventory_at(root_fd, pages_fd, expected_page_files)
    return LoadedMassiveCapture(
        artifact_path=root,
        manifest_sha256=sha256_bytes(manifest_bytes),
        capture=capture,
        accepted_risk_input_pair=None,
        capture_transport=manifest["capture_transport"],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first-date", required=True)
    parser.add_argument("--last-date", required=True)
    parser.add_argument("--page-limit", type=int, default=DEFAULT_PAGE_LIMIT)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    args = parser.parse_args(argv)
    try:
        loaded = capture_massive_history(
            requested_first_event_date=args.first_date,
            requested_last_event_date=args.last_date,
            artifact_root=args.artifact_root,
            page_limit=args.page_limit,
        )
    except MassiveCaptureError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(f"artifact: {loaded.artifact_path}")
    print(f"capture_id: {loaded.capture_id}")
    print(f"pages: {loaded.total_page_count}")
    print(f"rows: {loaded.total_row_count}")
    print("point_in_time_classification: non_pristine_current_version")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ARTIFACT_SCHEMA",
    "MAX_CAPTURE_STORED_BYTES",
    "BASE_URL",
    "DEFAULT_ARTIFACT_ROOT",
    "DEFAULT_PAGE_LIMIT",
    "ENDPOINT_PATHS",
    "LoadedMassiveCapture",
    "SpooledMassiveCapture",
    "MassiveCaptureError",
    "ROLE_ORDER",
    "capture_massive_history",
    "load_massive_capture_artifact",
    "main",
]
