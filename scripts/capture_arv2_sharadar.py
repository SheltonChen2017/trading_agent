"""Bounded source-only capture of the three Sharadar inputs used by ARV2.

The adapter retains exact bulk ZIP responses for TICKERS, ACTIONS, and
FUNDAMENTALS.  It deliberately does *not* construct a point-in-time security
master, infer a terminal shareholder payoff, or build a backtest input.  The
TICKERS export is labelled as a capture-time snapshot even though it includes
active and delisted securities; ACTIONS is discovery evidence only; and the
FUNDAMENTALS request is restricted to the point-in-time As-Reported ``ART``
dimension.

Operational capture is POSIX-only and publishes one private, immutable-style
directory below the repository's ignored ``artifacts/`` tree.  Downloads and
ZIP/CSV validation are streamed under hard byte, member, and row ceilings.
The provider key is used only in the initial request query and is neither
logged nor persisted.  Importing this module performs no provider, credential,
filesystem, QuantConnect, outcome, broker, or trading I/O.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import io
import ipaddress
import json
import os
import re
import stat
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Callable
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    decode_utf8,
    format_utc_timestamp,
    parse_utc_timestamp,
    require_canonical_json_bytes,
    require_exact_bool,
    require_exact_keys,
    require_identifier,
    require_int,
    require_sha256,
    sha256_bytes,
)


BASE_URL = "https://api.sharadar.com"
ARTIFACT_SCHEMA = "arv2-sharadar-source-capture-artifact-v2"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_DIGEST_FILENAME = "manifest.sha256"
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_BYTES = 4 * 1024 * 1024 * 1024
MAX_TOTAL_ARCHIVE_BYTES = 8 * 1024 * 1024 * 1024
MAX_ZIP_MEMBERS = 64
MAX_TOTAL_ZIP_MEMBERS = 128
MAX_MEMBER_UNCOMPRESSED_BYTES = 16 * 1024 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 24 * 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 250
MAX_TOTAL_ROWS = 100_000_000
MAX_CSV_COLUMNS = 1024
MAX_CSV_FIELD_BYTES = 4 * 1024 * 1024
RESPONSE_CHUNK_BYTES = 128 * 1024
REQUEST_TIMEOUT_SECONDS = 120

PRODUCTION_TRANSPORT = "sharadar_direct_https_query_key_owned_session"
TEST_TRANSPORT = "offline_test_double"
_TRANSPORTS = frozenset({PRODUCTION_TRANSPORT, TEST_TRANSPORT})

TICKERS_AVAILABILITY = (
    "capture_time_current_snapshot_active_and_delisted_not_point_in_time"
)
ACTIONS_AVAILABILITY = (
    "full_history_current_export_for_identity_and_terminal_event_discovery_only"
)
FUNDAMENTALS_AVAILABILITY = (
    "point_in_time_as_reported_art_full_history_date_fields_only_"
    "no_intraday_availability"
)


class SharadarDataset(str, Enum):
    TICKERS = "tickers"
    ACTIONS = "actions"
    FUNDAMENTALS = "fundamentals"


DATASET_ORDER = (
    SharadarDataset.TICKERS,
    SharadarDataset.ACTIONS,
    SharadarDataset.FUNDAMENTALS,
)
ENDPOINT_PATHS = MappingProxyType(
    {role: f"/v1.0/data/{role.value}" for role in DATASET_ORDER}
)
REQUEST_QUERIES = MappingProxyType(
    {
        SharadarDataset.TICKERS: (("years", "full"),),
        SharadarDataset.ACTIONS: (("years", "full"),),
        SharadarDataset.FUNDAMENTALS: (
            ("dimension", "ART"),
            ("years", "full"),
        ),
    }
)
REQUIRED_FIELDS = MappingProxyType(
    {
        SharadarDataset.TICKERS: frozenset(
            {
                "table",
                "ticker",
                "permaticker",
                "isdelisted",
                "category",
                "exchange",
                "sector",
                "industry",
                "figi",
                "firstpricedate",
                "lastpricedate",
            }
        ),
        SharadarDataset.ACTIONS: frozenset(
            {"date", "action", "ticker"}
        ),
        SharadarDataset.FUNDAMENTALS: frozenset(
            {
                "ticker",
                "dimension",
                "calendardate",
                "date",
                "reportperiod",
                "lastupdated",
                "sharesbas",
                "equityusd",
                "revenueusd",
            }
        ),
    }
)
ARCHIVE_FILENAMES = MappingProxyType(
    {
        role: f"{index:02d}-{role.value}-years-full.zip"
        for index, role in enumerate(DATASET_ORDER, 1)
    }
)

REPOSITORY_ROOT = Path(__file__).absolute().parents[1]
REPOSITORY_ARTIFACTS_ROOT = REPOSITORY_ROOT / "artifacts"
DEFAULT_ARTIFACT_ROOT = (
    REPOSITORY_ARTIFACTS_ROOT / "analyst_revisions_v2" / "sharadar_capture"
)

_ARTIFACT_ID_RE = re.compile(r"arv2-sharadar-source-\d{8}T\d{12}Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_MALFORMED_PERCENT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_CREDENTIAL_QUERY_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "api-key",
        "access_token",
        "token",
        "authorization",
        "password",
        "secret",
        "key",
    }
)
_REDIRECT_HOST_SUFFIXES = (
    ".amazonaws.com",
    ".cloudfront.net",
    ".googleapis.com",
    ".googleusercontent.com",
    ".sharadar.com",
)
_REDIRECT_EXACT_HOSTS = frozenset(
    {"static-sharadar.nyc3.digitaloceanspaces.com"}
)
_ALLOWED_ZIP_COMPRESSION = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})

_MANIFEST_KEYS = frozenset(
    {
        "schema",
        "artifact_id",
        "capture_id",
        "capture_sha256",
        "capture_started_at",
        "capture_completed_at",
        "capture_transport",
        "dataset_order",
        "archives",
        "total_archive_byte_count",
        "total_uncompressed_byte_count",
        "total_member_count",
        "total_row_count",
        "archive_byte_limit",
        "total_archive_byte_limit",
        "member_uncompressed_byte_limit",
        "total_uncompressed_byte_limit",
        "archive_member_count_limit",
        "total_member_count_limit",
        "row_count_limit",
        "tickers_availability_semantics",
        "actions_availability_semantics",
        "fundamentals_availability_semantics",
        "tickers_contains_active_and_delisted",
        "tickers_unknown_delisting_flag_row_count",
        "fundamentals_dimension",
        "pit_security_master_constructed",
        "terminal_payoff_constructed",
        "backtest_input_constructed",
        "provider_io_read_only",
        "quantconnect_io_performed",
        "outcome_access_performed",
        "private_artifact",
        "api_key_persisted",
        "redirect_url_persisted",
    }
)
_ARCHIVE_KEYS = frozenset(
    {
        "dataset",
        "endpoint_path",
        "request_query_sha256",
        "archive_file",
        "archive_byte_count",
        "archive_sha256",
        "member_count",
        "uncompressed_byte_count",
        "row_count",
        "active_ticker_row_count",
        "delisted_ticker_row_count",
        "unknown_ticker_delisting_flag_row_count",
        "redirect_used",
        "members",
    }
)
_MEMBER_KEYS = frozenset(
    {
        "name",
        "compressed_byte_count",
        "uncompressed_byte_count",
        "crc32",
        "content_sha256",
        "row_count",
        "columns",
    }
)


class SharadarCaptureError(ValueError):
    """The Sharadar source response or persisted capture is unsafe."""


@dataclasses.dataclass(frozen=True)
class SharadarMemberBinding:
    name: str
    compressed_byte_count: int
    uncompressed_byte_count: int
    crc32: int
    content_sha256: str
    row_count: int
    columns: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class SharadarArchiveBinding:
    dataset: SharadarDataset
    endpoint_path: str
    request_query_sha256: str
    archive_file: str
    archive_byte_count: int
    archive_sha256: str
    active_ticker_row_count: int
    delisted_ticker_row_count: int
    unknown_ticker_delisting_flag_row_count: int
    redirect_used: bool
    members: tuple[SharadarMemberBinding, ...]

    @property
    def member_count(self) -> int:
        return len(self.members)

    @property
    def uncompressed_byte_count(self) -> int:
        return sum(member.uncompressed_byte_count for member in self.members)

    @property
    def row_count(self) -> int:
        return sum(member.row_count for member in self.members)


@dataclasses.dataclass(frozen=True)
class LoadedSharadarCapture:
    artifact_path: Path
    manifest_sha256: str
    capture_id: str
    capture_sha256: str
    capture_started_at: str
    capture_completed_at: str
    capture_transport: str
    archives: tuple[SharadarArchiveBinding, ...]


@dataclasses.dataclass
class _DatasetCensus:
    active: int = 0
    delisted: int = 0
    unknown_delisting_flag: int = 0
    rows: int = 0


class _OwnedSessionGuard:
    """Make closure of the one production Session idempotent and observable."""

    def __init__(self, session: object) -> None:
        self._session = session
        self._closed = False

    def __getattr__(self, name: str) -> object:
        return getattr(self._session, name)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._session.close()


class _HashingRawReader(io.RawIOBase):
    def __init__(self, source: object) -> None:
        super().__init__()
        self._source = source
        self._hasher = hashlib.sha256()
        self.byte_count = 0

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: object) -> int:
        data = self._source.read(len(buffer))
        if not data:
            return 0
        if type(data) is not bytes:
            raise SharadarCaptureError("ZIP member stream yielded non-bytes")
        buffer[: len(data)] = data
        self._hasher.update(data)
        self.byte_count += len(data)
        return len(data)

    def close(self) -> None:
        try:
            self._source.close()
        finally:
            super().close()

    @property
    def sha256(self) -> str:
        return self._hasher.hexdigest()


def _validated_api_key(value: object, *, synthetic: bool) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) < 8
        or len(value) > 4096
        or any(ord(character) < 0x21 or ord(character) > 0x7E for character in value)
        or value.startswith("offline-test-") is not synthetic
    ):
        kind = "synthetic test" if synthetic else "SHARADAR_API_KEY"
        raise SharadarCaptureError(f"{kind} credential is unavailable or malformed")
    return value


def _api_key() -> str:
    value = os.environ.get("SHARADAR_API_KEY")
    if value:
        return _validated_api_key(value, synthetic=False)
    if sys.platform == "darwin":
        try:
            import pwd

            account = pwd.getpwuid(os.getuid()).pw_name
            result = subprocess.run(
                [
                    "/usr/bin/security",
                    "find-generic-password",
                    "-a",
                    account,
                    "-s",
                    "SHARADAR_API_KEY",
                    "-w",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            result = None
        if result is not None and result.returncode == 0:
            try:
                candidate = result.stdout.decode("ascii").rstrip("\r\n")
            except UnicodeError:
                candidate = None
            if candidate:
                return _validated_api_key(candidate, synthetic=False)
    raise SharadarCaptureError(
        "SHARADAR_API_KEY is unavailable; refusing provider access"
    )


def _new_session() -> object:
    try:
        import requests
    except ImportError as exc:
        raise SharadarCaptureError("requests is required for Sharadar capture") from exc
    return requests.Session()


def _now_utc(clock: Callable[[], datetime]) -> str:
    try:
        return format_utc_timestamp(clock())
    except (CanonicalEvidenceError, TypeError, ValueError) as exc:
        raise SharadarCaptureError("capture clock did not return an aware instant") from exc


def _sanitized_provider_failure(exc: BaseException) -> str:
    return f"{type(exc).__name__}: provider request failed; details redacted"


def _credential_encodings(key: str) -> tuple[bytes, ...]:
    return tuple(
        value
        for value in {
            key.encode("ascii"),
            quote(key, safe="").encode("ascii"),
            json.dumps(key, ensure_ascii=True)[1:-1].encode("ascii"),
        }
        if value
    )


def _redact_url(url: object) -> str:
    if type(url) is not str:
        return "<invalid URL redacted>"
    try:
        parts = urlsplit(url)
        if _MALFORMED_PERCENT_RE.search(parts.query):
            return "<malformed URL redacted>"
        query = [
            (
                name,
                "REDACTED"
                if name.casefold() in _CREDENTIAL_QUERY_KEYS
                or name.casefold().startswith("x-amz-")
                or name.casefold().startswith("x-goog-")
                or "signature" in name.casefold()
                or "credential" in name.casefold()
                else value,
            )
            for name, value in parse_qsl(parts.query, keep_blank_values=True)
        ]
        host = parts.netloc.rsplit("@", 1)[-1]
        return urlunsplit((parts.scheme, host, parts.path, urlencode(query), ""))
    except (TypeError, UnicodeError, ValueError):
        return "<malformed URL redacted>"


def _request_query_bytes(dataset: SharadarDataset) -> bytes:
    return canonical_json_bytes(
        {"dataset": dataset.value, "query": dict(REQUEST_QUERIES[dataset])}
    )


def _parse_url(url: object, *, provider: bool) -> tuple[object, tuple[tuple[str, str], ...]]:
    if (
        type(url) is not str
        or not url
        or url != url.strip()
        or len(url) > 32_768
        or "\\" in url
        or any(ord(character) < 0x20 for character in url)
    ):
        raise SharadarCaptureError("provider URL is malformed")
    try:
        parts = urlsplit(url)
        port = parts.port
        pairs = parse_qsl(
            parts.query,
            keep_blank_values=True,
            strict_parsing=True,
            encoding="utf-8",
            errors="strict",
        )
    except (TypeError, UnicodeError, ValueError) as exc:
        raise SharadarCaptureError("provider URL is malformed") from exc
    names = [name for name, _ in pairs]
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or port not in (None, 443)
        or parts.fragment
        or _MALFORMED_PERCENT_RE.search(parts.query)
        or len(names) != len(set(names))
    ):
        raise SharadarCaptureError("provider URL left the reviewed HTTPS boundary")
    hostname = parts.hostname.casefold()
    if provider and hostname != "api.sharadar.com":
        raise SharadarCaptureError("provider request changed host")
    return parts, tuple(sorted(pairs))


def _validate_initial_request(
    response: object,
    *,
    dataset: SharadarDataset,
    expected_url: str,
) -> None:
    try:
        request = response.request
        method = request.method
        prepared_url = request.url
        response_url = response.url
    except Exception as exc:
        raise SharadarCaptureError(_sanitized_provider_failure(exc)) from None
    if type(method) is not str or method != "GET":
        raise SharadarCaptureError("provider request was not prepared as exact GET")
    expected_parts, expected_query = _parse_url(expected_url, provider=True)
    for candidate in (prepared_url, response_url):
        parts, query = _parse_url(candidate, provider=True)
        if (
            parts.path != ENDPOINT_PATHS[dataset]
            or query != expected_query
            or parts.hostname.casefold() != expected_parts.hostname.casefold()
        ):
            raise SharadarCaptureError("prepared provider request changed frozen query")


def _validate_redirect_url(url: object, key: str) -> str:
    parts, _ = _parse_url(url, provider=False)
    hostname = parts.hostname.casefold()
    try:
        ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        pass
    else:
        raise SharadarCaptureError("provider redirect used an IP literal")
    if hostname in {"localhost", "localhost.localdomain"} or (
        hostname not in _REDIRECT_EXACT_HOSTS
        and not any(
            hostname.endswith(suffix) for suffix in _REDIRECT_HOST_SUFFIXES
        )
    ):
        raise SharadarCaptureError("provider redirect host is not reviewed")
    encoded = url.encode("utf-8")
    if any(candidate in encoded for candidate in _credential_encodings(key)):
        raise SharadarCaptureError("provider redirect echoed the API key")
    return url


def _validate_redirected_request(response: object, expected_url: str) -> None:
    try:
        request = response.request
        method = request.method
        prepared_url = request.url
        response_url = response.url
    except Exception as exc:
        raise SharadarCaptureError(_sanitized_provider_failure(exc)) from None
    if type(method) is not str or method != "GET":
        raise SharadarCaptureError("redirected request was not exact GET")
    expected_parts, expected_query = _parse_url(expected_url, provider=False)
    for candidate in (prepared_url, response_url):
        parts, query = _parse_url(candidate, provider=False)
        if (
            parts.scheme != expected_parts.scheme
            or parts.netloc != expected_parts.netloc
            or parts.path != expected_parts.path
            or query != expected_query
        ):
            raise SharadarCaptureError("redirected request changed signed URL semantics")


def _close_response(response: object) -> None:
    try:
        response.close()
    except Exception:
        return


def _request_archive_response(
    session: object, dataset: SharadarDataset, key: str
) -> tuple[object, bool]:
    endpoint = BASE_URL + ENDPOINT_PATHS[dataset]
    params = dict(REQUEST_QUERIES[dataset])
    params["api_key"] = key
    expected_url = endpoint + "?" + urlencode(params)
    first: object | None = None
    try:
        first = session.get(
            endpoint,
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
            allow_redirects=False,
            stream=True,
        )
        _validate_initial_request(first, dataset=dataset, expected_url=expected_url)
        status = first.status_code
        if type(status) is not int:
            raise SharadarCaptureError("provider returned a malformed HTTP status")
        if status == 200:
            return first, False
        if status not in {302, 303, 307, 308}:
            raise SharadarCaptureError("provider returned a non-success HTTP status")
        try:
            location = first.headers.get("Location")
        except Exception as exc:
            raise SharadarCaptureError(_sanitized_provider_failure(exc)) from None
        redirect_url = _validate_redirect_url(location, key)
    except Exception as exc:
        if first is not None:
            _close_response(first)
        if isinstance(exc, SharadarCaptureError):
            raise
        raise SharadarCaptureError(_sanitized_provider_failure(exc)) from None
    _close_response(first)
    final: object | None = None
    try:
        final = session.get(
            redirect_url,
            params=None,
            timeout=REQUEST_TIMEOUT_SECONDS,
            allow_redirects=False,
            stream=True,
        )
        _validate_redirected_request(final, redirect_url)
        if type(final.status_code) is not int or final.status_code != 200:
            raise SharadarCaptureError("provider download did not return HTTP 200")
        return final, True
    except Exception as exc:
        if final is not None:
            _close_response(final)
        if isinstance(exc, SharadarCaptureError):
            raise
        raise SharadarCaptureError(_sanitized_provider_failure(exc)) from None


def _require_dirfd_support() -> None:
    required = (os.open, os.mkdir, os.rename, os.stat)
    if (
        os.name == "nt"
        or not hasattr(os, "O_DIRECTORY")
        or not hasattr(os, "O_NOFOLLOW")
        or any(call not in os.supports_dir_fd for call in required)
    ):
        raise SharadarCaptureError(
            "Sharadar capture requires POSIX dirfd and no-follow enforcement"
        )


def _directory_flags() -> int:
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _private_directory(metadata: os.stat_result, name: str) -> None:
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or metadata.st_uid != os.getuid()
    ):
        raise SharadarCaptureError(f"{name} must be an owner-held 0700 directory")


def _open_directory_path(
    path: Path, *, create: bool, allow_missing: bool = False, name: str
) -> tuple[Path, int | None]:
    _require_dirfd_support()
    if type(path) is not type(Path()):
        raise SharadarCaptureError(f"{name} must be a Path")
    absolute = Path(os.path.abspath(path))
    descriptor = os.open(absolute.anchor, _directory_flags())
    try:
        for component in absolute.parts[1:]:
            created = False
            try:
                child = os.open(component, _directory_flags(), dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    if allow_missing:
                        os.close(descriptor)
                        return absolute, None
                    raise SharadarCaptureError(f"{name} is unavailable") from None
                try:
                    os.mkdir(component, 0o700, dir_fd=descriptor)
                    child = os.open(component, _directory_flags(), dir_fd=descriptor)
                    os.fchmod(child, 0o700)
                    created = True
                except OSError as exc:
                    raise SharadarCaptureError(f"{name} could not be prepared") from exc
            except OSError as exc:
                raise SharadarCaptureError(f"{name} traversed a link") from exc
            os.close(descriptor)
            descriptor = child
            if created:
                _private_directory(os.fstat(descriptor), name)
        _private_directory(os.fstat(descriptor), name)
        return absolute, descriptor
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def _safe_leaf(name: str, label: str) -> None:
    if (
        type(name) is not str
        or not name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or "\x00" in name
    ):
        raise SharadarCaptureError(f"{label} name is unsafe")


def _open_child_directory(parent_fd: int, name: str, label: str) -> int:
    _safe_leaf(name, label)
    descriptor: int | None = None
    try:
        descriptor = os.open(name, _directory_flags(), dir_fd=parent_fd)
        _private_directory(os.fstat(descriptor), label)
        return descriptor
    except SharadarCaptureError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise SharadarCaptureError(f"{label} is unavailable or link-like") from exc


def _pinned_child(parent_fd: int, name: str, child_fd: int, label: str) -> None:
    try:
        opened = os.fstat(child_fd)
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise SharadarCaptureError(f"{label} identity is unavailable") from exc
    _private_directory(opened, label)
    _private_directory(named, label)
    if (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino):
        raise SharadarCaptureError(f"{label} identity changed")


def _entry_exists(parent_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise SharadarCaptureError("artifact entry could not be inspected") from exc
    return True


def _regular_metadata(metadata: os.stat_result, label: str, maximum: int) -> None:
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
        or metadata.st_size < 0
        or metadata.st_size > maximum
    ):
        raise SharadarCaptureError(
            f"{label} must be a bounded owner-held 0600 single-link file"
        )


def _new_private_file(parent_fd: int, filename: str, label: str) -> int:
    _safe_leaf(filename, label)
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | os.O_EXCL
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0)
    )
    descriptor: int | None = None
    try:
        descriptor = os.open(filename, flags, 0o600, dir_fd=parent_fd)
        os.fchmod(descriptor, 0o600)
        return descriptor
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise SharadarCaptureError(f"{label} could not be created") from exc


def _write_all(descriptor: int, payload: bytes, label: str) -> None:
    offset = 0
    while offset < len(payload):
        try:
            written = os.write(descriptor, payload[offset:])
        except InterruptedError:
            continue
        except OSError as exc:
            raise SharadarCaptureError(f"{label} write failed") from exc
        if written <= 0:
            raise SharadarCaptureError(f"{label} write stalled")
        offset += written


def _write_private_bytes(parent_fd: int, filename: str, payload: bytes, label: str) -> None:
    descriptor = _new_private_file(parent_fd, filename, label)
    try:
        _write_all(descriptor, payload, label)
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        _regular_metadata(metadata, label, len(payload))
        if metadata.st_size != len(payload):
            raise SharadarCaptureError(f"{label} byte count changed")
    finally:
        os.close(descriptor)


def _read_private_bytes(
    parent_fd: int, filename: str, *, maximum: int, label: str
) -> bytes:
    _safe_leaf(filename, label)
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(filename, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise SharadarCaptureError(f"{label} is unavailable or link-like") from exc
    try:
        before = os.fstat(descriptor)
        _regular_metadata(before, label, maximum)
        chunks = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(RESPONSE_CHUNK_BYTES, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        named = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise SharadarCaptureError(f"{label} could not be read safely") from exc
    finally:
        os.close(descriptor)
    for metadata in (after, named):
        _regular_metadata(metadata, label, maximum)
    identities = {
        (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
        for item in (before, after, named)
    }
    if len(payload) != before.st_size or len(identities) != 1:
        raise SharadarCaptureError(f"{label} changed while being read")
    return payload


def _open_private_regular(
    parent_fd: int, filename: str, *, maximum: int, label: str
) -> int:
    _safe_leaf(filename, label)
    descriptor: int | None = None
    try:
        descriptor = os.open(
            filename,
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_fd,
        )
        _regular_metadata(os.fstat(descriptor), label, maximum)
        return descriptor
    except SharadarCaptureError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise SharadarCaptureError(f"{label} is unavailable or link-like") from exc


def _stream_archive(
    response: object,
    descriptor: int,
    *,
    key: str,
    remaining_total: int,
) -> tuple[int, str]:
    limit = min(MAX_ARCHIVE_BYTES, remaining_total)
    patterns = _credential_encodings(key)
    overlap = max(len(pattern) for pattern in patterns) - 1
    tail = b""
    observed = 0
    digest = hashlib.sha256()
    try:
        for chunk in response.iter_content(chunk_size=RESPONSE_CHUNK_BYTES):
            if type(chunk) is not bytes:
                raise SharadarCaptureError("provider response stream yielded non-bytes")
            if not chunk:
                continue
            observed += len(chunk)
            if observed > limit:
                raise SharadarCaptureError("Sharadar archive exceeded the byte limit")
            scan = tail + chunk
            if any(pattern in scan for pattern in patterns):
                raise SharadarCaptureError("provider response echoed the API key")
            tail = scan[-overlap:] if overlap else b""
            _write_all(descriptor, chunk, "Sharadar archive")
            digest.update(chunk)
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        _regular_metadata(metadata, "Sharadar archive", MAX_ARCHIVE_BYTES)
        if metadata.st_size != observed or observed == 0:
            raise SharadarCaptureError("Sharadar archive byte count changed")
        os.lseek(descriptor, 0, os.SEEK_SET)
        return observed, digest.hexdigest()
    except SharadarCaptureError:
        raise
    except Exception:
        raise SharadarCaptureError("Sharadar archive could not be stored") from None
    finally:
        _close_response(response)


def _safe_zip_member(info: zipfile.ZipInfo) -> None:
    name = info.filename
    try:
        encoded_name = name.encode("utf-8") if type(name) is str else b""
    except UnicodeError as exc:
        raise SharadarCaptureError("ZIP member name is invalid text") from exc
    path = PurePosixPath(name)
    unix_mode = info.external_attr >> 16
    file_type = stat.S_IFMT(unix_mode)
    if (
        type(name) is not str
        or not name
        or len(encoded_name) > 1024
        or "\\" in name
        or "\x00" in name
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or info.is_dir()
        or len(path.parts) != 1
        or not name.casefold().endswith(".csv")
        or info.flag_bits & 0x1
        or info.compress_type not in _ALLOWED_ZIP_COMPRESSION
        or file_type not in {0, stat.S_IFREG}
        or info.file_size < 0
        or info.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES
        or info.compress_size < 0
    ):
        raise SharadarCaptureError("ZIP contains an unsafe or unsupported member")


def _inspect_csv_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    dataset: SharadarDataset,
    census: _DatasetCensus,
) -> SharadarMemberBinding:
    source = archive.open(info, "r")
    hashing = _HashingRawReader(source)
    buffered = io.BufferedReader(hashing, buffer_size=RESPONSE_CHUNK_BYTES)
    text = io.TextIOWrapper(buffered, encoding="utf-8-sig", newline="")
    previous_limit = csv.field_size_limit()
    try:
        csv.field_size_limit(MAX_CSV_FIELD_BYTES)
        rows = csv.reader(text, strict=True)
        try:
            header_list = next(rows)
        except StopIteration:
            raise SharadarCaptureError("CSV member is empty") from None
        if (
            not header_list
            or len(header_list) > MAX_CSV_COLUMNS
            or any(not name or name != name.strip() for name in header_list)
            or len(header_list) != len(set(header_list))
        ):
            raise SharadarCaptureError("CSV member header is malformed")
        fields = set(header_list)
        if not REQUIRED_FIELDS[dataset].issubset(fields):
            raise SharadarCaptureError("CSV member omits required Sharadar fields")
        indexes = {name: header_list.index(name) for name in REQUIRED_FIELDS[dataset]}
        row_count = 0
        for row in rows:
            if len(row) != len(header_list):
                raise SharadarCaptureError("CSV row width differs from its header")
            row_count += 1
            if census.rows + row_count > MAX_TOTAL_ROWS:
                raise SharadarCaptureError("Sharadar capture exceeded the row limit")
            if dataset is SharadarDataset.TICKERS:
                if any(
                    not row[indexes[field]]
                    for field in ("table", "ticker", "permaticker")
                ):
                    raise SharadarCaptureError("TICKERS row lacks permanent identity")
                state = row[indexes["isdelisted"]].strip().casefold()
                if state in {"y", "yes", "1", "true"}:
                    census.delisted += 1
                elif state in {"n", "no", "0", "false"}:
                    census.active += 1
                elif state == "":
                    # Sharadar's production TICKERS export contains blank
                    # isdelisted values.  A blank is retained as unknown: it
                    # is neither evidence that a security is active nor that
                    # it is delisted.  The exact count is authenticated in the
                    # archive and top-level manifests below.
                    census.unknown_delisting_flag += 1
                else:
                    raise SharadarCaptureError("TICKERS delisting flag is unreviewed")
            elif dataset is SharadarDataset.ACTIONS:
                if any(not row[indexes[field]] for field in ("date", "action", "ticker")):
                    raise SharadarCaptureError("ACTIONS row lacks discovery identity")
            else:
                if row[indexes["dimension"]] != "ART":
                    raise SharadarCaptureError("FUNDAMENTALS contains a non-ART row")
                if any(
                    not row[indexes[field]]
                    for field in (
                        "ticker",
                        "calendardate",
                        "date",
                        "reportperiod",
                        "lastupdated",
                    )
                ):
                    raise SharadarCaptureError("FUNDAMENTALS row lacks PIT identity")
        if row_count == 0:
            raise SharadarCaptureError("CSV member contains no data rows")
        census.rows += row_count
        text.read()
    except (csv.Error, UnicodeError) as exc:
        raise SharadarCaptureError("ZIP member is not bounded strict UTF-8 CSV") from exc
    finally:
        csv.field_size_limit(previous_limit)
        text.close()
    if hashing.byte_count != info.file_size:
        raise SharadarCaptureError("ZIP member uncompressed byte count changed")
    return SharadarMemberBinding(
        name=info.filename,
        compressed_byte_count=info.compress_size,
        uncompressed_byte_count=info.file_size,
        crc32=info.CRC,
        content_sha256=hashing.sha256,
        row_count=row_count,
        columns=tuple(header_list),
    )


def _inspect_zip_fd(
    descriptor: int,
    dataset: SharadarDataset,
    *,
    remaining_uncompressed: int,
    remaining_rows: int,
    remaining_members: int,
) -> tuple[tuple[SharadarMemberBinding, ...], _DatasetCensus]:
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        with os.fdopen(os.dup(descriptor), "rb", closefd=True) as source:
            with zipfile.ZipFile(source, "r", allowZip64=True) as archive:
                infos = archive.infolist()
                if (
                    not infos
                    or len(infos) > MAX_ZIP_MEMBERS
                    or len(infos) > remaining_members
                ):
                    raise SharadarCaptureError("ZIP member inventory exceeds the limit")
                names = [info.filename for info in infos]
                if len(names) != len(set(names)):
                    raise SharadarCaptureError("ZIP contains duplicate member names")
                for info in infos:
                    _safe_zip_member(info)
                declared = sum(info.file_size for info in infos)
                compressed = sum(info.compress_size for info in infos)
                if (
                    declared > remaining_uncompressed
                    or compressed == 0
                    or declared > max(compressed, 1) * MAX_COMPRESSION_RATIO
                ):
                    raise SharadarCaptureError("ZIP expansion exceeds the reviewed limit")
                census = _DatasetCensus()
                members = tuple(
                    _inspect_csv_member(archive, info, dataset, census)
                    for info in infos
                )
                if census.rows > remaining_rows:
                    raise SharadarCaptureError("Sharadar capture exceeded the row limit")
    except SharadarCaptureError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise SharadarCaptureError("provider response is not a safe ZIP archive") from exc
    if dataset is SharadarDataset.TICKERS and (
        census.active == 0 or census.delisted == 0
    ):
        raise SharadarCaptureError(
            "TICKERS snapshot does not demonstrate active and delisted coverage"
        )
    return members, census


def _capture_one_archive(
    stage_fd: int,
    session: object,
    dataset: SharadarDataset,
    key: str,
    *,
    remaining_archive: int,
    remaining_uncompressed: int,
    remaining_rows: int,
    remaining_members: int,
) -> SharadarArchiveBinding:
    response, redirected = _request_archive_response(session, dataset, key)
    filename = ARCHIVE_FILENAMES[dataset]
    try:
        descriptor = _new_private_file(stage_fd, filename, "Sharadar archive")
    except BaseException:
        _close_response(response)
        raise
    try:
        byte_count, archive_sha256 = _stream_archive(
            response,
            descriptor,
            key=key,
            remaining_total=remaining_archive,
        )
        members, census = _inspect_zip_fd(
            descriptor,
            dataset,
            remaining_uncompressed=remaining_uncompressed,
            remaining_rows=remaining_rows,
            remaining_members=remaining_members,
        )
        before = os.fstat(descriptor)
        named = os.stat(filename, dir_fd=stage_fd, follow_symlinks=False)
        _regular_metadata(before, "Sharadar archive", MAX_ARCHIVE_BYTES)
        _regular_metadata(named, "Sharadar archive", MAX_ARCHIVE_BYTES)
        if (before.st_dev, before.st_ino, before.st_size) != (
            named.st_dev,
            named.st_ino,
            named.st_size,
        ):
            raise SharadarCaptureError("Sharadar archive identity changed")
    finally:
        os.close(descriptor)
    return SharadarArchiveBinding(
        dataset=dataset,
        endpoint_path=ENDPOINT_PATHS[dataset],
        request_query_sha256=sha256_bytes(_request_query_bytes(dataset)),
        archive_file=filename,
        archive_byte_count=byte_count,
        archive_sha256=archive_sha256,
        active_ticker_row_count=census.active,
        delisted_ticker_row_count=census.delisted,
        unknown_ticker_delisting_flag_row_count=census.unknown_delisting_flag,
        redirect_used=redirected,
        members=members,
    )


def _member_record(member: SharadarMemberBinding) -> dict[str, object]:
    return {
        "name": member.name,
        "compressed_byte_count": member.compressed_byte_count,
        "uncompressed_byte_count": member.uncompressed_byte_count,
        "crc32": member.crc32,
        "content_sha256": member.content_sha256,
        "row_count": member.row_count,
        "columns": list(member.columns),
    }


def _archive_record(archive: SharadarArchiveBinding) -> dict[str, object]:
    return {
        "dataset": archive.dataset.value,
        "endpoint_path": archive.endpoint_path,
        "request_query_sha256": archive.request_query_sha256,
        "archive_file": archive.archive_file,
        "archive_byte_count": archive.archive_byte_count,
        "archive_sha256": archive.archive_sha256,
        "member_count": archive.member_count,
        "uncompressed_byte_count": archive.uncompressed_byte_count,
        "row_count": archive.row_count,
        "active_ticker_row_count": archive.active_ticker_row_count,
        "delisted_ticker_row_count": archive.delisted_ticker_row_count,
        "unknown_ticker_delisting_flag_row_count": (
            archive.unknown_ticker_delisting_flag_row_count
        ),
        "redirect_used": archive.redirect_used,
        "members": [_member_record(member) for member in archive.members],
    }


def _capture_identity_document(
    started: str,
    completed: str,
    transport: str,
    archives: tuple[SharadarArchiveBinding, ...],
) -> dict[str, object]:
    return {
        "schema": ARTIFACT_SCHEMA,
        "capture_started_at": started,
        "capture_completed_at": completed,
        "capture_transport": transport,
        "archives": [_archive_record(archive) for archive in archives],
    }


def _manifest(
    artifact_id: str,
    started: str,
    completed: str,
    transport: str,
    archives: tuple[SharadarArchiveBinding, ...],
) -> dict[str, object]:
    identity = canonical_json_bytes(
        _capture_identity_document(started, completed, transport, archives)
    )
    capture_sha256 = sha256_bytes(identity)
    return {
        "schema": ARTIFACT_SCHEMA,
        "artifact_id": artifact_id,
        "capture_id": f"arv2-sharadar-source-{capture_sha256[:16]}",
        "capture_sha256": capture_sha256,
        "capture_started_at": started,
        "capture_completed_at": completed,
        "capture_transport": transport,
        "dataset_order": [role.value for role in DATASET_ORDER],
        "archives": [_archive_record(archive) for archive in archives],
        "total_archive_byte_count": sum(a.archive_byte_count for a in archives),
        "total_uncompressed_byte_count": sum(a.uncompressed_byte_count for a in archives),
        "total_member_count": sum(a.member_count for a in archives),
        "total_row_count": sum(a.row_count for a in archives),
        "archive_byte_limit": MAX_ARCHIVE_BYTES,
        "total_archive_byte_limit": MAX_TOTAL_ARCHIVE_BYTES,
        "member_uncompressed_byte_limit": MAX_MEMBER_UNCOMPRESSED_BYTES,
        "total_uncompressed_byte_limit": MAX_TOTAL_UNCOMPRESSED_BYTES,
        "archive_member_count_limit": MAX_ZIP_MEMBERS,
        "total_member_count_limit": MAX_TOTAL_ZIP_MEMBERS,
        "row_count_limit": MAX_TOTAL_ROWS,
        "tickers_availability_semantics": TICKERS_AVAILABILITY,
        "actions_availability_semantics": ACTIONS_AVAILABILITY,
        "fundamentals_availability_semantics": FUNDAMENTALS_AVAILABILITY,
        "tickers_contains_active_and_delisted": True,
        "tickers_unknown_delisting_flag_row_count": next(
            archive.unknown_ticker_delisting_flag_row_count
            for archive in archives
            if archive.dataset is SharadarDataset.TICKERS
        ),
        "fundamentals_dimension": "ART",
        "pit_security_master_constructed": False,
        "terminal_payoff_constructed": False,
        "backtest_input_constructed": False,
        "provider_io_read_only": transport == PRODUCTION_TRANSPORT,
        "quantconnect_io_performed": False,
        "outcome_access_performed": False,
        "private_artifact": True,
        "api_key_persisted": False,
        "redirect_url_persisted": False,
    }


def _artifact_id(started: str) -> str:
    parse_utc_timestamp(started, "capture_started_at")
    compact = started.translate(str.maketrans("", "", "-:."))
    value = f"arv2-sharadar-source-{compact}"
    if _ARTIFACT_ID_RE.fullmatch(value) is None:
        raise SharadarCaptureError("capture timestamp could not form an artifact ID")
    return value


def _fsync(descriptor: int, label: str) -> None:
    try:
        os.fsync(descriptor)
    except OSError as exc:
        raise SharadarCaptureError(f"{label} sync failed") from exc


def _validate_inventory(
    stage_fd: int, expected_archives: set[str], *, published: bool = False
) -> None:
    expected = expected_archives | {MANIFEST_FILENAME, MANIFEST_DIGEST_FILENAME}
    try:
        actual = set(os.listdir(stage_fd))
    except OSError as exc:
        raise SharadarCaptureError("capture inventory is unreadable") from exc
    if actual != expected:
        raise SharadarCaptureError("capture inventory does not match manifest")
    for filename in expected_archives:
        metadata = os.stat(filename, dir_fd=stage_fd, follow_symlinks=False)
        _regular_metadata(metadata, "Sharadar archive", MAX_ARCHIVE_BYTES)
    for filename, maximum in (
        (MANIFEST_FILENAME, MAX_MANIFEST_BYTES),
        (MANIFEST_DIGEST_FILENAME, 65),
    ):
        metadata = os.stat(filename, dir_fd=stage_fd, follow_symlinks=False)
        _regular_metadata(metadata, filename, maximum)
    if set(os.listdir(stage_fd)) != actual:
        raise SharadarCaptureError("capture inventory changed during inspection")


def _require_operational_scope(path: Path) -> None:
    candidate = Path(os.path.abspath(path))
    try:
        candidate.relative_to(REPOSITORY_ARTIFACTS_ROOT)
    except ValueError as exc:
        raise SharadarCaptureError(
            "operational capture root must remain beneath repository artifacts"
        ) from exc


def _preflight_root(path: Path) -> Path:
    root = Path(path)
    _, descriptor = _open_directory_path(
        root, create=False, allow_missing=True, name="artifact root"
    )
    if descriptor is not None:
        os.close(descriptor)
    return root


def _capture_core(
    *,
    artifact_root: Path,
    session: object,
    key: str,
    clock: Callable[[], datetime],
    transport: str,
    close_owned_session: bool,
) -> LoadedSharadarCapture:
    if transport not in _TRANSPORTS:
        raise SharadarCaptureError("capture transport is not reviewed")
    started = _now_utc(clock)
    artifact_id = _artifact_id(started)
    root, root_fd = _open_directory_path(
        Path(artifact_root), create=True, name="artifact root"
    )
    assert root_fd is not None
    staging_name = f".{artifact_id}.incomplete"
    stage_fd: int | None = None
    session_closed = False
    try:
        if _entry_exists(root_fd, artifact_id) or _entry_exists(root_fd, staging_name):
            raise SharadarCaptureError("timestamped capture already exists")
        os.mkdir(staging_name, 0o700, dir_fd=root_fd)
        stage_fd = _open_child_directory(root_fd, staging_name, "capture staging")
        archives_list: list[SharadarArchiveBinding] = []
        archive_total = uncompressed_total = row_total = member_total = 0
        try:
            for dataset in DATASET_ORDER:
                archive = _capture_one_archive(
                    stage_fd,
                    session,
                    dataset,
                    key,
                    remaining_archive=MAX_TOTAL_ARCHIVE_BYTES - archive_total,
                    remaining_uncompressed=MAX_TOTAL_UNCOMPRESSED_BYTES
                    - uncompressed_total,
                    remaining_rows=MAX_TOTAL_ROWS - row_total,
                    remaining_members=MAX_TOTAL_ZIP_MEMBERS - member_total,
                )
                archives_list.append(archive)
                archive_total += archive.archive_byte_count
                uncompressed_total += archive.uncompressed_byte_count
                row_total += archive.row_count
                member_total += archive.member_count
        except BaseException:
            if close_owned_session:
                try:
                    session.close()
                except Exception:
                    pass
                session_closed = True
            raise
        if close_owned_session:
            try:
                session.close()
            except Exception as exc:
                raise SharadarCaptureError(_sanitized_provider_failure(exc)) from None
            session_closed = True
        completed = _now_utc(clock)
        archives = tuple(archives_list)
        manifest = _manifest(artifact_id, started, completed, transport, archives)
        manifest_bytes = canonical_json_bytes(manifest)
        if len(manifest_bytes) > MAX_MANIFEST_BYTES:
            raise SharadarCaptureError("capture manifest exceeds the byte limit")
        manifest_sha256 = sha256_bytes(manifest_bytes)
        _write_private_bytes(stage_fd, MANIFEST_FILENAME, manifest_bytes, "manifest")
        _write_private_bytes(
            stage_fd,
            MANIFEST_DIGEST_FILENAME,
            (manifest_sha256 + "\n").encode("ascii"),
            "manifest digest",
        )
        expected_archives = {archive.archive_file for archive in archives}
        _validate_inventory(stage_fd, expected_archives)
        _pinned_child(root_fd, staging_name, stage_fd, "capture staging")
        _fsync(stage_fd, "capture staging")
        try:
            os.rename(
                staging_name,
                artifact_id,
                src_dir_fd=root_fd,
                dst_dir_fd=root_fd,
            )
        except OSError as exc:
            raise SharadarCaptureError("capture publication failed") from exc
        _pinned_child(root_fd, artifact_id, stage_fd, "published capture")
        try:
            _fsync(root_fd, "capture publication")
        except SharadarCaptureError as sync_error:
            try:
                os.rename(
                    artifact_id,
                    staging_name,
                    src_dir_fd=root_fd,
                    dst_dir_fd=root_fd,
                )
            except OSError as rollback_error:
                raise SharadarCaptureError(
                    "capture publication state is ambiguous"
                ) from rollback_error
            raise sync_error
        return LoadedSharadarCapture(
            artifact_path=root / artifact_id,
            manifest_sha256=manifest_sha256,
            capture_id=manifest["capture_id"],
            capture_sha256=manifest["capture_sha256"],
            capture_started_at=started,
            capture_completed_at=completed,
            capture_transport=transport,
            archives=archives,
        )
    finally:
        if close_owned_session and not session_closed:
            try:
                session.close()
            except Exception:
                pass
        if stage_fd is not None:
            os.close(stage_fd)
        os.close(root_fd)


def capture_sharadar_history(
    *, artifact_root: Path = DEFAULT_ARTIFACT_ROOT
) -> LoadedSharadarCapture:
    """Capture the reviewed full-history exports using the configured key."""

    _require_operational_scope(Path(artifact_root))
    root = _preflight_root(Path(artifact_root))
    key = _api_key()
    session = _OwnedSessionGuard(_new_session())
    try:
        return _capture_core(
            artifact_root=root,
            session=session,
            key=key,
            clock=lambda: datetime.now(timezone.utc),
            transport=PRODUCTION_TRANSPORT,
            close_owned_session=True,
        )
    except BaseException:
        # ``Session.close`` is idempotent.  This outer guard covers failures
        # before the core obtains its first directory descriptor; the core
        # itself closes before any successful publication.
        try:
            session.close()
        except Exception:
            pass
        raise


def _capture_sharadar_history_for_test(
    *,
    artifact_root: Path,
    session: object,
    clock: Callable[[], datetime],
    api_key: str,
) -> LoadedSharadarCapture:
    """Private offline seam; artifacts are permanently labelled test-double."""

    root = _preflight_root(Path(artifact_root))
    key = _validated_api_key(api_key, synthetic=True)
    return _capture_core(
        artifact_root=root,
        session=session,
        key=key,
        clock=clock,
        transport=TEST_TRANSPORT,
        close_owned_session=False,
    )


def _parse_member(value: object, dataset: SharadarDataset) -> SharadarMemberBinding:
    if type(value) is not dict:
        raise SharadarCaptureError("manifest member must be an object")
    try:
        require_exact_keys(value, _MEMBER_KEYS, "Sharadar member")
        name = value["name"]
        if type(name) is not str:
            raise SharadarCaptureError("manifest member name is invalid")
        _safe_zip_member(
            zipfile.ZipInfo(name)
        )
        compressed = require_int(
            value["compressed_byte_count"], "compressed bytes", minimum=0
        )
        uncompressed = require_int(
            value["uncompressed_byte_count"],
            "uncompressed bytes",
            minimum=1,
            maximum=MAX_MEMBER_UNCOMPRESSED_BYTES,
        )
        crc32 = require_int(value["crc32"], "crc32", minimum=0, maximum=0xFFFFFFFF)
        content_sha256 = require_sha256(value["content_sha256"], "member sha256")
        row_count = require_int(
            value["row_count"], "member rows", minimum=1, maximum=MAX_TOTAL_ROWS
        )
        columns = value["columns"]
        if (
            type(columns) is not list
            or not columns
            or len(columns) > MAX_CSV_COLUMNS
            or any(type(item) is not str or not item for item in columns)
            or len(columns) != len(set(columns))
            or not REQUIRED_FIELDS[dataset].issubset(set(columns))
        ):
            raise SharadarCaptureError("manifest member columns are invalid")
    except CanonicalEvidenceError as exc:
        raise SharadarCaptureError("manifest member field is invalid") from exc
    return SharadarMemberBinding(
        name=name,
        compressed_byte_count=compressed,
        uncompressed_byte_count=uncompressed,
        crc32=crc32,
        content_sha256=content_sha256,
        row_count=row_count,
        columns=tuple(columns),
    )


def _parse_archive(value: object, expected: SharadarDataset) -> SharadarArchiveBinding:
    if type(value) is not dict:
        raise SharadarCaptureError("manifest archive must be an object")
    try:
        require_exact_keys(value, _ARCHIVE_KEYS, "Sharadar archive")
        if value["dataset"] != expected.value:
            raise SharadarCaptureError("manifest dataset order changed")
        if value["endpoint_path"] != ENDPOINT_PATHS[expected]:
            raise SharadarCaptureError("manifest endpoint changed")
        if value["request_query_sha256"] != sha256_bytes(_request_query_bytes(expected)):
            raise SharadarCaptureError("manifest request query changed")
        if value["archive_file"] != ARCHIVE_FILENAMES[expected]:
            raise SharadarCaptureError("manifest archive filename changed")
        archive_bytes = require_int(
            value["archive_byte_count"],
            "archive bytes",
            minimum=1,
            maximum=MAX_ARCHIVE_BYTES,
        )
        archive_sha256 = require_sha256(value["archive_sha256"], "archive sha256")
        active_ticker_rows = require_int(
            value["active_ticker_row_count"],
            "active_ticker_row_count",
            minimum=0,
            maximum=MAX_TOTAL_ROWS,
        )
        delisted_ticker_rows = require_int(
            value["delisted_ticker_row_count"],
            "delisted_ticker_row_count",
            minimum=0,
            maximum=MAX_TOTAL_ROWS,
        )
        unknown_ticker_rows = require_int(
            value["unknown_ticker_delisting_flag_row_count"],
            "unknown_ticker_delisting_flag_row_count",
            minimum=0,
            maximum=MAX_TOTAL_ROWS,
        )
        require_exact_bool(value["redirect_used"], "redirect_used")
        members_raw = value["members"]
        if (
            type(members_raw) is not list
            or not members_raw
            or len(members_raw) > MAX_ZIP_MEMBERS
        ):
            raise SharadarCaptureError("manifest member inventory is invalid")
        members = tuple(_parse_member(item, expected) for item in members_raw)
        if len({member.name for member in members}) != len(members):
            raise SharadarCaptureError("manifest member names repeat")
        for key, actual in (
            ("member_count", len(members)),
            (
                "uncompressed_byte_count",
                sum(member.uncompressed_byte_count for member in members),
            ),
            ("row_count", sum(member.row_count for member in members)),
        ):
            if require_int(value[key], key, minimum=1) != actual:
                raise SharadarCaptureError(f"manifest {key} does not match members")
        if expected is SharadarDataset.TICKERS:
            if (
                active_ticker_rows < 1
                or delisted_ticker_rows < 1
                or active_ticker_rows + delisted_ticker_rows + unknown_ticker_rows
                != sum(member.row_count for member in members)
            ):
                raise SharadarCaptureError(
                    "manifest TICKERS delisting-flag census is inconsistent"
                )
        elif any(
            count != 0
            for count in (
                active_ticker_rows,
                delisted_ticker_rows,
                unknown_ticker_rows,
            )
        ):
            raise SharadarCaptureError(
                "non-TICKERS archive carries a delisting-flag census"
            )
    except CanonicalEvidenceError as exc:
        raise SharadarCaptureError("manifest archive field is invalid") from exc
    return SharadarArchiveBinding(
        dataset=expected,
        endpoint_path=ENDPOINT_PATHS[expected],
        request_query_sha256=value["request_query_sha256"],
        archive_file=value["archive_file"],
        archive_byte_count=archive_bytes,
        archive_sha256=archive_sha256,
        active_ticker_row_count=active_ticker_rows,
        delisted_ticker_row_count=delisted_ticker_rows,
        unknown_ticker_delisting_flag_row_count=unknown_ticker_rows,
        redirect_used=value["redirect_used"],
        members=members,
    )


def _parse_manifest(payload: bytes, artifact_path: Path) -> tuple[dict[str, object], tuple[SharadarArchiveBinding, ...]]:
    try:
        value = require_canonical_json_bytes(payload, "Sharadar capture manifest")
        if type(value) is not dict:
            raise SharadarCaptureError("capture manifest must be an object")
        require_exact_keys(value, _MANIFEST_KEYS, "Sharadar capture manifest")
        if value["schema"] != ARTIFACT_SCHEMA:
            raise SharadarCaptureError("capture manifest schema changed")
        require_identifier(value["artifact_id"], "artifact_id")
        if value["artifact_id"] != artifact_path.name or not _ARTIFACT_ID_RE.fullmatch(value["artifact_id"]):
            raise SharadarCaptureError("artifact ID does not match its directory")
        started = format_utc_timestamp(parse_utc_timestamp(value["capture_started_at"], "capture_started_at"))
        completed = format_utc_timestamp(parse_utc_timestamp(value["capture_completed_at"], "capture_completed_at"))
        if started != value["capture_started_at"] or completed != value["capture_completed_at"] or completed < started:
            raise SharadarCaptureError("capture chronology is invalid")
        if _artifact_id(started) != value["artifact_id"]:
            raise SharadarCaptureError("artifact ID timestamp changed")
        if (
            type(value["capture_transport"]) is not str
            or value["capture_transport"] not in _TRANSPORTS
        ):
            raise SharadarCaptureError("capture transport is not reviewed")
        if value["dataset_order"] != [role.value for role in DATASET_ORDER]:
            raise SharadarCaptureError("manifest dataset order changed")
        archives_raw = value["archives"]
        if type(archives_raw) is not list or len(archives_raw) != len(DATASET_ORDER):
            raise SharadarCaptureError("manifest archive inventory is incomplete")
        archives = tuple(
            _parse_archive(raw, role)
            for raw, role in zip(archives_raw, DATASET_ORDER, strict=True)
        )
        identity_sha = sha256_bytes(
            canonical_json_bytes(
                _capture_identity_document(
                    started, completed, value["capture_transport"], archives
                )
            )
        )
        if (
            require_sha256(value["capture_sha256"], "capture_sha256") != identity_sha
            or value["capture_id"] != f"arv2-sharadar-source-{identity_sha[:16]}"
        ):
            raise SharadarCaptureError("capture identity does not authenticate archives")
        require_identifier(value["capture_id"], "capture_id")
        totals = {
            "total_archive_byte_count": sum(a.archive_byte_count for a in archives),
            "total_uncompressed_byte_count": sum(a.uncompressed_byte_count for a in archives),
            "total_member_count": sum(a.member_count for a in archives),
            "total_row_count": sum(a.row_count for a in archives),
        }
        for key, expected in totals.items():
            if require_int(value[key], key, minimum=1) != expected:
                raise SharadarCaptureError(f"manifest {key} is inconsistent")
        if (
            totals["total_archive_byte_count"] > MAX_TOTAL_ARCHIVE_BYTES
            or totals["total_uncompressed_byte_count"]
            > MAX_TOTAL_UNCOMPRESSED_BYTES
            or totals["total_member_count"] > MAX_TOTAL_ZIP_MEMBERS
            or totals["total_row_count"] > MAX_TOTAL_ROWS
        ):
            raise SharadarCaptureError("manifest aggregate exceeds reviewed capacity")
        for key, expected in (
            ("archive_byte_limit", MAX_ARCHIVE_BYTES),
            ("total_archive_byte_limit", MAX_TOTAL_ARCHIVE_BYTES),
            ("member_uncompressed_byte_limit", MAX_MEMBER_UNCOMPRESSED_BYTES),
            ("total_uncompressed_byte_limit", MAX_TOTAL_UNCOMPRESSED_BYTES),
            ("archive_member_count_limit", MAX_ZIP_MEMBERS),
            ("total_member_count_limit", MAX_TOTAL_ZIP_MEMBERS),
            ("row_count_limit", MAX_TOTAL_ROWS),
        ):
            if require_int(value[key], key, minimum=1) != expected:
                raise SharadarCaptureError("manifest capacity contract changed")
        for key, expected in (
            ("tickers_availability_semantics", TICKERS_AVAILABILITY),
            ("actions_availability_semantics", ACTIONS_AVAILABILITY),
            ("fundamentals_availability_semantics", FUNDAMENTALS_AVAILABILITY),
            ("fundamentals_dimension", "ART"),
        ):
            if value[key] != expected:
                raise SharadarCaptureError(f"manifest {key} changed")
        for key, expected in (
            ("tickers_contains_active_and_delisted", True),
            ("pit_security_master_constructed", False),
            ("terminal_payoff_constructed", False),
            ("backtest_input_constructed", False),
            ("quantconnect_io_performed", False),
            ("outcome_access_performed", False),
            ("private_artifact", True),
            ("api_key_persisted", False),
            ("redirect_url_persisted", False),
        ):
            require_exact_bool(value[key], key)
            if value[key] is not expected:
                raise SharadarCaptureError(f"manifest {key} boundary changed")
        tickers_archive = archives[0]
        if (
            require_int(
                value["tickers_unknown_delisting_flag_row_count"],
                "tickers_unknown_delisting_flag_row_count",
                minimum=0,
                maximum=MAX_TOTAL_ROWS,
            )
            != tickers_archive.unknown_ticker_delisting_flag_row_count
        ):
            raise SharadarCaptureError(
                "manifest unknown TICKERS delisting-flag count changed"
            )
        require_exact_bool(value["provider_io_read_only"], "provider_io_read_only")
        if value["provider_io_read_only"] is not (value["capture_transport"] == PRODUCTION_TRANSPORT):
            raise SharadarCaptureError("manifest provider-I/O classification changed")
    except CanonicalEvidenceError as exc:
        raise SharadarCaptureError("capture manifest field is invalid") from exc
    return value, archives


def load_sharadar_capture_artifact(artifact_path: Path) -> LoadedSharadarCapture:
    """Reauthenticate exact ZIP bytes and their deterministic CSV census."""

    root, root_fd = _open_directory_path(
        Path(artifact_path), create=False, name="capture artifact"
    )
    assert root_fd is not None
    try:
        manifest_bytes = _read_private_bytes(
            root_fd,
            MANIFEST_FILENAME,
            maximum=MAX_MANIFEST_BYTES,
            label="manifest",
        )
        digest = _read_private_bytes(
            root_fd,
            MANIFEST_DIGEST_FILENAME,
            maximum=65,
            label="manifest digest",
        )
        manifest_sha256 = sha256_bytes(manifest_bytes)
        if digest != (manifest_sha256 + "\n").encode("ascii"):
            raise SharadarCaptureError("manifest digest does not authenticate bytes")
        manifest, declared_archives = _parse_manifest(manifest_bytes, root)
        observed: list[SharadarArchiveBinding] = []
        archive_total = uncompressed_total = row_total = member_total = 0
        for declared in declared_archives:
            descriptor = _open_private_regular(
                root_fd,
                declared.archive_file,
                maximum=MAX_ARCHIVE_BYTES,
                label="Sharadar archive",
            )
            try:
                digest_hasher = hashlib.sha256()
                byte_count = 0
                while True:
                    chunk = os.read(descriptor, RESPONSE_CHUNK_BYTES)
                    if not chunk:
                        break
                    byte_count += len(chunk)
                    if byte_count > MAX_ARCHIVE_BYTES:
                        raise SharadarCaptureError("archive exceeds byte limit")
                    digest_hasher.update(chunk)
                if byte_count != declared.archive_byte_count or digest_hasher.hexdigest() != declared.archive_sha256:
                    raise SharadarCaptureError("archive bytes do not match manifest")
                members, census = _inspect_zip_fd(
                    descriptor,
                    declared.dataset,
                    remaining_uncompressed=MAX_TOTAL_UNCOMPRESSED_BYTES - uncompressed_total,
                    remaining_rows=MAX_TOTAL_ROWS - row_total,
                    remaining_members=MAX_TOTAL_ZIP_MEMBERS - member_total,
                )
                after = os.fstat(descriptor)
                named = os.stat(declared.archive_file, dir_fd=root_fd, follow_symlinks=False)
                _regular_metadata(after, "Sharadar archive", MAX_ARCHIVE_BYTES)
                _regular_metadata(named, "Sharadar archive", MAX_ARCHIVE_BYTES)
                if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (named.st_dev, named.st_ino, named.st_size, named.st_mtime_ns, named.st_ctime_ns):
                    raise SharadarCaptureError("archive changed while being read")
            finally:
                os.close(descriptor)
            rebuilt = dataclasses.replace(
                declared,
                members=members,
                active_ticker_row_count=census.active,
                delisted_ticker_row_count=census.delisted,
                unknown_ticker_delisting_flag_row_count=(
                    census.unknown_delisting_flag
                ),
            )
            if rebuilt != declared:
                raise SharadarCaptureError("ZIP member census differs from manifest")
            observed.append(rebuilt)
            archive_total += byte_count
            uncompressed_total += rebuilt.uncompressed_byte_count
            row_total += rebuilt.row_count
            member_total += rebuilt.member_count
            if archive_total > MAX_TOTAL_ARCHIVE_BYTES:
                raise SharadarCaptureError("capture archives exceed aggregate limit")
        _validate_inventory(root_fd, {item.archive_file for item in observed}, published=True)
        if tuple(observed) != declared_archives:
            raise SharadarCaptureError("capture archive order changed")
        return LoadedSharadarCapture(
            artifact_path=root,
            manifest_sha256=manifest_sha256,
            capture_id=manifest["capture_id"],
            capture_sha256=manifest["capture_sha256"],
            capture_started_at=manifest["capture_started_at"],
            capture_completed_at=manifest["capture_completed_at"],
            capture_transport=manifest["capture_transport"],
            archives=tuple(observed),
        )
    finally:
        os.close(root_fd)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    args = parser.parse_args(argv)
    capture = capture_sharadar_history(artifact_root=args.artifact_root)
    print(f"artifact={capture.artifact_path}")
    print(f"manifest_sha256={capture.manifest_sha256}")
    print(f"capture_id={capture.capture_id}")
    print(f"archives={len(capture.archives)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "ACTIONS_AVAILABILITY",
    "FUNDAMENTALS_AVAILABILITY",
    "LoadedSharadarCapture",
    "SharadarArchiveBinding",
    "SharadarCaptureError",
    "SharadarDataset",
    "SharadarMemberBinding",
    "TICKERS_AVAILABILITY",
    "capture_sharadar_history",
    "load_sharadar_capture_artifact",
]
