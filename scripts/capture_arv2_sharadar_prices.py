"""Private, bounded Sharadar unadjusted-close capture; no source admission.

Exactly two read-only GETs request QCOM stock and the frozen six ETF fund rows
for one caller-supplied date. The exact CSV bytes are retained, not printed.
The date filter and ``lastupdated`` do not prove a NYSE session, availability,
permanent security identity, independent provenance, or decision readiness.
Import performs no credential, filesystem, provider, QC or execution I/O.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import io
import os
import re
import sys
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode

import scripts.capture_arv2_sharadar as source
from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    parse_utc_timestamp,
    require_canonical_json_bytes,
    require_sha256,
    sha256_bytes,
)

SharadarPriceCaptureError = source.SharadarCaptureError
ARTIFACT_SCHEMA = "arv2-sharadar-raw-close-capture-v1"
PRODUCTION_TRANSPORT = "sharadar_raw_close_direct_https_owned_session"
TEST_TRANSPORT = "offline_test_double"
DEFAULT_ARTIFACT_ROOT = (
    source.REPOSITORY_ARTIFACTS_ROOT / "analyst_revisions_v2" / "sharadar_price_capture"
)
FIELDS = ("ticker", "date", "closeunadj", "lastupdated")
ROLE_TICKERS = (("stocks", ("QCOM",)),
                ("funds", ("SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE")))
REQUEST_ROW_LIMIT = 100
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 32 * 1024
MAX_CSV_FIELD_CHARS = 128
REQUEST_TIMEOUT_SECONDS = 60
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
_ARTIFACT_ID = re.compile(r"arv2-sharadar-prices-\d{8}T\d{12}Z")
FALSE_FLAGS = (
    "point_in_time_proven", "independent_source_authenticated",
    "first_publication_authenticated", "permanent_identity_authenticated",
    "nyse_session_authenticated", "formal_source_admitted", "decision_ready", "paper_ready",
    "paper_look_committed", "orders_enabled", "quantconnect_io_performed",
    "outcome_access_performed", "performance_evaluated", "api_key_persisted",
    "paper_orders_permitted", "live_orders_permitted", "funded_orders_permitted",
    "deployment_permitted",
)


@dataclasses.dataclass(frozen=True)
class PriceCsvBinding:
    role: str
    csv_file: str
    csv_sha256: str
    csv_byte_count: int
    row_count: int


@dataclasses.dataclass(frozen=True)
class LoadedSharadarPriceCapture:
    artifact_path: Path
    manifest_sha256: str
    capture_sha256: str
    close_session: str
    capture_started_at: str
    capture_completed_at: str
    capture_transport: str
    responses: tuple[PriceCsvBinding, ...]


def _session_date(value: object) -> str:
    if type(value) is not str or _DATE.fullmatch(value) is None:
        raise SharadarPriceCaptureError("close-session must be an exact ISO date")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise SharadarPriceCaptureError("close-session is not a calendar date") from None
    return value


def _query(role: str, close_session: str) -> dict[str, str]:
    tickers = dict(ROLE_TICKERS)[role]
    return {
        "format": "csv", "from": close_session, "to": close_session,
        "fields": ",".join(FIELDS), "ticker": ",".join(tickers),
        "sort": "ticker.asc", "skip": "0", "limit": str(REQUEST_ROW_LIMIT),
    }


def _parse_csv(payload: bytes, role: str, close_session: str) -> int:
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_RESPONSE_BYTES:
        raise SharadarPriceCaptureError("price CSV exceeds its bounded byte contract")
    try:
        text = payload.decode("utf-8-sig", errors="strict")
    except UnicodeError:
        raise SharadarPriceCaptureError("price CSV is not strict UTF-8") from None
    if "\x00" in text:
        raise SharadarPriceCaptureError("price CSV contains a forbidden control byte")
    expected = set(dict(ROLE_TICKERS)[role])
    seen: set[str] = set()
    try:
        rows = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = tuple(next(rows, ()))
        if len(header) != len(FIELDS) or set(header) != set(FIELDS):
            raise SharadarPriceCaptureError("price CSV header does not match frozen fields")
        indices = tuple(header.index(field) for field in FIELDS)
        count = 0
        for row in rows:
            count += 1
            if count >= REQUEST_ROW_LIMIT:
                raise SharadarPriceCaptureError("price CSV reached the request row limit")
            if len(row) != len(FIELDS) or any(
                not value or value != value.strip() or len(value) > MAX_CSV_FIELD_CHARS
                or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)
                for value in row
            ):
                raise SharadarPriceCaptureError("price CSV row shape is malformed")
            ticker, observed_date, price, lastupdated = (row[index] for index in indices)
            if ticker not in expected or ticker in seen or observed_date != close_session:
                raise SharadarPriceCaptureError("price CSV ticker/date is unexpected or repeated")
            _session_date(lastupdated)
            if _NUMBER.fullmatch(price) is None:
                raise SharadarPriceCaptureError("unadjusted close is not a positive finite decimal")
            parsed = Decimal(price)
            if not parsed.is_finite() or parsed <= 0:
                raise SharadarPriceCaptureError("unadjusted close is not a positive finite decimal")
            seen.add(ticker)
    except (csv.Error, InvalidOperation):
        raise SharadarPriceCaptureError("price CSV cannot be parsed safely") from None
    if seen != expected:
        raise SharadarPriceCaptureError("price CSV is missing required tickers")
    return count


def _validate_response_identity(response: object, endpoint: str, params: dict[str, str]) -> None:
    expected_parts, expected_query = source._parse_url(
        endpoint + "?" + urlencode(params), provider=True
    )
    try:
        request = response.request
        if request.method != "GET" or type(request.method) is not str:
            raise SharadarPriceCaptureError("price request was not exact GET")
        if response.history:
            raise SharadarPriceCaptureError("price response followed a redirect")
        for url in (request.url, response.url):
            parts, query = source._parse_url(url, provider=True)
            if parts.path != expected_parts.path or query != expected_query:
                raise SharadarPriceCaptureError("prepared price request changed frozen identity")
        if type(response.status_code) is not int or response.status_code != 200:
            raise SharadarPriceCaptureError("price provider did not return HTTP 200")
    except SharadarPriceCaptureError:
        raise
    except Exception:
        raise SharadarPriceCaptureError("price response identity is unavailable") from None


def _response_bytes(session: object, role: str, close_session: str, key: str) -> bytes:
    endpoint = source.BASE_URL + "/v1.0/data/" + role
    params = _query(role, close_session)
    params["api_key"] = key
    response = None
    try:
        response = session.get(
            endpoint, params=params, timeout=REQUEST_TIMEOUT_SECONDS,
            allow_redirects=False, stream=True, verify=True,
            headers={"Accept-Encoding": "identity"},
        )
        _validate_response_identity(response, endpoint, params)
        encoding = response.headers.get("Content-Encoding")
        if encoding is not None and (
            type(encoding) is not str or encoding.casefold() != "identity"
        ):
            raise SharadarPriceCaptureError("price response used an unsupported content encoding")
        declared_length = response.headers.get("Content-Length")
        if declared_length is not None and (
            type(declared_length) is not str or not declared_length.isascii()
            or not declared_length.isdecimal()
            or not 0 < int(declared_length) <= MAX_RESPONSE_BYTES
        ):
            raise SharadarPriceCaptureError("price response length is malformed or excessive")
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if type(chunk) is not bytes:
                raise SharadarPriceCaptureError("price response did not stream byte chunks")
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise SharadarPriceCaptureError("price response exceeds the byte limit")
            chunks.append(chunk)
        payload = b"".join(chunks)
        if declared_length is not None and len(payload) != int(declared_length):
            raise SharadarPriceCaptureError("price response length differs from header")
        if any(encoded in payload for encoded in source._credential_encodings(key)):
            raise SharadarPriceCaptureError("provider echoed a credential; refusing persistence")
        _parse_csv(payload, role, close_session)
        return payload
    except SharadarPriceCaptureError:
        raise
    except Exception:
        # Provider exceptions can contain the query key or response body.
        raise SharadarPriceCaptureError("price provider request failed; details redacted") from None
    finally:
        if response is not None:
            source._close_response(response)


def _binding(payload: bytes, role: str, close_session: str) -> PriceCsvBinding:
    return PriceCsvBinding(
        role, f"{role}.csv", sha256_bytes(payload), len(payload),
        _parse_csv(payload, role, close_session),
    )


def _artifact_id(started: str) -> str:
    compact = started.translate(str.maketrans("", "", "-:."))
    result = "arv2-sharadar-prices-" + compact
    if _ARTIFACT_ID.fullmatch(result) is None:
        raise SharadarPriceCaptureError("capture clock cannot form an artifact identity")
    return result


def _manifest(
    close_session: str, started: str, completed: str, transport: str,
    responses: tuple[PriceCsvBinding, ...],
) -> dict[str, object]:
    if transport not in (PRODUCTION_TRANSPORT, TEST_TRANSPORT):
        raise SharadarPriceCaptureError("price capture transport is not supported")
    if parse_utc_timestamp(completed, "completed") < parse_utc_timestamp(started, "started"):
        raise SharadarPriceCaptureError("capture clock moved backwards")
    identity = {
        "close_session": close_session, "capture_started_at": started,
        "capture_completed_at": completed, "capture_transport": transport,
        "responses": [
            {
                **dataclasses.asdict(binding),
                "endpoint_path": "/v1.0/data/" + binding.role,
                "request_query": _query(binding.role, close_session),
                "request_query_sha256": sha256_bytes(canonical_json_bytes(
                    _query(binding.role, close_session)
                )),
            }
            for binding in responses
        ],
    }
    return {
        "schema": ARTIFACT_SCHEMA, "artifact_id": _artifact_id(started),
        **identity, "capture_sha256": sha256_bytes(canonical_json_bytes(identity)),
        "fields": list(FIELDS), "request_count": 2,
        "response_byte_limit": MAX_RESPONSE_BYTES, "request_row_limit": REQUEST_ROW_LIMIT,
        "total_row_count": sum(binding.row_count for binding in responses),
        "source_semantics": "vendor_closeunadj_unadjusted_USD_per_share_not_independent_RAW_proof",
        "session_semantics": "caller_supplied_date_filter_not_authenticated_NYSE_session",
        "lastupdated_semantics": "vendor_update_date_not_original_availability_or_revision_history",
        "client_clock_semantics": "unsigned_local_receipt_interval_not_server_publication_clock",
        "response_bytes_semantics": "requests_HTTP_entity_CSV_bytes_not_raw_wire_or_signed_vendor_proof",
        "private_artifact": True, "provider_io_read_only": True,
        "redirects_permitted": False, "retries_permitted": False,
        **dict.fromkeys(FALSE_FLAGS, False),
    }


def _inventory(directory_fd: int, expected: set[str]) -> None:
    if set(os.listdir(directory_fd)) != expected:
        raise SharadarPriceCaptureError("price capture inventory is not exact")


def _load(directory: Path, expected_manifest_sha256: str) -> LoadedSharadarPriceCapture:
    require_sha256(expected_manifest_sha256, "expected_manifest_sha256")
    root, root_fd = source._open_directory_path(directory, create=False, name="price capture")
    assert root_fd is not None
    held: list[tuple[str, int, tuple[int, int, int, int, int], int]] = []
    try:
        expected = {"stocks.csv", "funds.csv", "manifest.json", "manifest.sha256"}
        _inventory(root_fd, expected)
        captured: dict[str, bytes] = {}
        # Retain every descriptor until all authentication and final identity checks.
        for name in sorted(expected):
            maximum = 65 if name.endswith(".sha256") else (
                MAX_MANIFEST_BYTES if name == "manifest.json" else MAX_RESPONSE_BYTES
            )
            descriptor = source._open_private_regular(
                root_fd, name, maximum=maximum, label="private price evidence"
            )
            try:
                payload, identity = source._read_open_private_regular(
                    descriptor, maximum=maximum, label="private price evidence"
                )
            except BaseException:
                os.close(descriptor)
                raise
            held.append((name, descriptor, identity, maximum))
            captured[name] = payload
        actual_hash = sha256_bytes(captured["manifest.json"])
        if actual_hash != expected_manifest_sha256 or captured["manifest.sha256"] != (
            actual_hash + "\n"
        ).encode("ascii"):
            raise SharadarPriceCaptureError("price manifest does not match the exact pinned digest")
        manifest = require_canonical_json_bytes(captured["manifest.json"], "price manifest")
        if type(manifest) is not dict:
            raise SharadarPriceCaptureError("price manifest must be an object")
        try:
            close_session = _session_date(manifest["close_session"])
            responses = tuple(
                _binding(captured[f"{role}.csv"], role, close_session)
                for role, _tickers in ROLE_TICKERS
            )
            rebuilt = _manifest(
                close_session, manifest["capture_started_at"],
                manifest["capture_completed_at"], manifest["capture_transport"], responses,
            )
        except KeyError:
            raise SharadarPriceCaptureError("price manifest lacks required identity") from None
        if canonical_json_bytes(rebuilt) != captured["manifest.json"]:
            raise SharadarPriceCaptureError("price manifest differs from authenticated response census")
        if root.name != rebuilt["artifact_id"]:
            raise SharadarPriceCaptureError("price artifact path differs from manifest identity")
        for name, descriptor, identity, maximum in held:
            source._require_open_leaf_identity(
                root_fd, name, descriptor, identity, maximum=maximum, label="private price evidence"
            )
        _inventory(root_fd, expected)
        return LoadedSharadarPriceCapture(
            root, actual_hash, rebuilt["capture_sha256"], close_session,
            rebuilt["capture_started_at"], rebuilt["capture_completed_at"],
            rebuilt["capture_transport"], responses,
        )
    finally:
        for _name, descriptor, _identity, _maximum in held:
            os.close(descriptor)
        os.close(root_fd)


def load_sharadar_price_capture(
    artifact_path: Path, *, expected_manifest_sha256: str,
) -> LoadedSharadarPriceCapture:
    """Offline hash/census authentication, not vendor or formal source admission."""
    try:
        return _load(artifact_path, expected_manifest_sha256)
    except CanonicalEvidenceError:
        raise SharadarPriceCaptureError("price manifest is not canonical evidence") from None


def _capture_core(
    *, close_session: str, artifact_root: Path, session: object, key: str,
    clock: Callable[[], datetime], transport: str, close_owned_session: bool,
) -> LoadedSharadarPriceCapture:
    close_session = _session_date(close_session)
    started = source._now_utc(clock)
    artifact_id = _artifact_id(started)
    root_fd = child_fd = None
    marker_identity: tuple[int, int] | None = None
    try:
        root, root_fd = source._open_directory_path(
            artifact_root, create=True, name="price artifact root"
        )
        assert root_fd is not None
        # Allocate exclusively. A directory without manifest.json is incomplete;
        # publication is the exclusive atomic link of the finished manifest.
        try:
            os.mkdir(artifact_id, 0o700, dir_fd=root_fd)
        except FileExistsError:
            raise SharadarPriceCaptureError("timestamped price capture already exists") from None
        child_fd = source._open_child_directory(root_fd, artifact_id, "price capture")
        bindings: list[PriceCsvBinding] = []
        for role, _tickers in ROLE_TICKERS:
            payload = _response_bytes(session, role, close_session, key)
            binding = _binding(payload, role, close_session)
            source._write_private_bytes(child_fd, binding.csv_file, payload, "price CSV")
            bindings.append(binding)
        if close_owned_session:
            try:
                session.close()
            except Exception:
                raise SharadarPriceCaptureError("owned price session closure failed; details redacted") from None
        completed = source._now_utc(clock)
        manifest = _manifest(close_session, started, completed, transport, tuple(bindings))
        payload = canonical_json_bytes(manifest)
        if len(payload) > MAX_MANIFEST_BYTES:
            raise SharadarPriceCaptureError("price manifest exceeds byte limit")
        digest = sha256_bytes(payload)
        source._write_private_bytes(child_fd, "manifest.pending", payload, "pending manifest")
        source._write_private_bytes(
            child_fd, "manifest.sha256", (digest + "\n").encode("ascii"), "manifest digest"
        )
        _inventory(child_fd, {"stocks.csv", "funds.csv", "manifest.pending", "manifest.sha256"})
        source._pinned_child(root_fd, artifact_id, child_fd, "price capture")
        source._fsync(child_fd, "price capture before publication")
        pending_metadata = os.stat("manifest.pending", dir_fd=child_fd, follow_symlinks=False)
        source._regular_metadata(pending_metadata, "pending manifest", MAX_MANIFEST_BYTES)
        # Retain identity before an ambiguous link/interrupt, not after it.
        marker_identity = (pending_metadata.st_dev, pending_metadata.st_ino)
        os.link(
            "manifest.pending", "manifest.json", src_dir_fd=child_fd,
            dst_dir_fd=child_fd, follow_symlinks=False,
        )
        linked_metadata = os.stat("manifest.json", dir_fd=child_fd, follow_symlinks=False)
        if (linked_metadata.st_dev, linked_metadata.st_ino) != marker_identity:
            raise SharadarPriceCaptureError("published manifest identity changed")
        os.unlink("manifest.pending", dir_fd=child_fd)
        source._fsync(child_fd, "price capture publication")
        source._fsync(root_fd, "price artifact root")
        source._pinned_child(root_fd, artifact_id, child_fd, "published price capture")
        loaded = load_sharadar_price_capture(root / artifact_id, expected_manifest_sha256=digest)
        source._pinned_child(root_fd, artifact_id, child_fd, "reauthenticated price capture")
        return loaded
    except BaseException as exc:
        if marker_identity is not None and child_fd is not None:
            # Revoke only the completion marker allocated by this invocation.
            # Never remove another process's replacement or an existing marker.
            try:
                try:
                    named = os.stat("manifest.json", dir_fd=child_fd, follow_symlinks=False)
                except FileNotFoundError:
                    named = None
                if named is not None:
                    if (named.st_dev, named.st_ino) != marker_identity:
                        raise SharadarPriceCaptureError("price publication state is ambiguous")
                    os.unlink("manifest.json", dir_fd=child_fd)
                    source._fsync(child_fd, "price completion-marker rollback")
            except (OSError, SharadarPriceCaptureError):
                raise SharadarPriceCaptureError("price publication state is ambiguous") from None
        if isinstance(exc, SharadarPriceCaptureError):
            raise
        if not isinstance(exc, Exception):
            raise
        raise SharadarPriceCaptureError("private price capture failed; details redacted") from None
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


def capture_sharadar_prices(*, close_session: str) -> LoadedSharadarPriceCapture:
    """Production-only entry owns configured credential and exact requests Session."""
    close_session = _session_date(close_session)
    source._preflight_root(DEFAULT_ARTIFACT_ROOT)
    key = source._api_key()
    raw_session = source._new_session()
    owned = source._OwnedSessionGuard(raw_session)
    try:
        import requests
        from requests.adapters import HTTPAdapter
        if type(raw_session) is not requests.Session:
            raise SharadarPriceCaptureError("production price transport is not an owned requests Session")
        if any(callable(value) for value in raw_session.__dict__.values()):
            raise SharadarPriceCaptureError("production price Session has overridden transport methods")
        raw_session.trust_env = False
        raw_session.verify = True
        raw_session.auth = None
        raw_session.cert = None
        raw_session.proxies.clear()
        raw_session.params.clear()
        raw_session.cookies.clear()
        raw_session.headers.clear()
        raw_session.hooks.clear()
        raw_session.adapters.clear()
        raw_session.mount("https://", HTTPAdapter(max_retries=0))
        return _capture_core(
            close_session=close_session, artifact_root=DEFAULT_ARTIFACT_ROOT,
            session=owned, key=key, clock=lambda: datetime.now(timezone.utc),
            transport=PRODUCTION_TRANSPORT, close_owned_session=True,
        )
    except BaseException as exc:
        try:
            owned.close()
        except Exception:
            pass
        if isinstance(exc, SharadarPriceCaptureError) or not isinstance(exc, Exception):
            raise
        raise SharadarPriceCaptureError("production price transport setup failed; details redacted") from None


def _capture_sharadar_prices_for_test(
    *, close_session: str, artifact_root: Path, session: object,
    clock: Callable[[], datetime], api_key: str,
) -> LoadedSharadarPriceCapture:
    """Explicit synthetic seam; cannot choose production transport or persist real keys."""
    key = source._validated_api_key(api_key, synthetic=True)
    source._preflight_root(artifact_root)
    return _capture_core(
        close_session=close_session, artifact_root=artifact_root, session=session,
        key=key, clock=clock, transport=TEST_TRANSPORT, close_owned_session=False,
    )


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--close-session", required=True)
    args = parser.parse_args(argv)
    try:
        capture = capture_sharadar_prices(close_session=args.close_session)
    except SharadarPriceCaptureError as exc:
        print(f"refused={exc}", file=sys.stderr)
        return 1
    print(f"artifact={capture.artifact_path}")
    print(f"manifest_sha256={capture.manifest_sha256}")
    print(f"capture_sha256={capture.capture_sha256}")
    print(f"rows={sum(response.row_count for response in capture.responses)}")
    print("point_in_time_proven=false decision_ready=false paper_ready=false orders_enabled=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
