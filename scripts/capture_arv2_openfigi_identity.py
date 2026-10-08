"""Capture seven public current FIGI references and bind private research inputs.

Two unauthenticated mapping POSTs (5+2) use only public ticker labels. This is
current-reference evidence, not historical identity, point-in-time admission,
independent review, a decision, or permission to trade. Import performs no IO.
The public input permits only FIGI identifier strings, not vendor descriptions.
Documentation: https://www.openfigi.com/api/documentation
Identifier dedication: https://www.openfigi.com/docs/terms-of-service
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import scripts.capture_arv2_sharadar as source
import scripts.capture_arv2_sharadar_identities as identities
import scripts.capture_arv2_sharadar_prices as prices
from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError, canonical_json_bytes, parse_utc_timestamp,
    require_canonical_json_bytes, require_sha256, sha256_bytes,
)

OpenFigiIdentityCaptureError = source.SharadarCaptureError
SCHEMA = "arv2-openfigi-seven-current-public-identities-v1"
INPUT_SCHEMA = "arv2-seven-public-figi-identity-input-v1"
ENDPOINT = "https://api.openfigi.com/v3/mapping"
PRODUCTION_TRANSPORT = "openfigi_unauthenticated_direct_https_owned_session"
TEST_TRANSPORT = "offline_test_double"
DEFAULT_ARTIFACT_ROOT = source.REPOSITORY_ARTIFACTS_ROOT / "analyst_revisions_v2" / "openfigi_identity_capture"
TICKERS = ("QCOM", "SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE")
BATCHES = (TICKERS[:5], TICKERS[5:])
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
MAX_INPUT_BYTES = 16 * 1024
TIMEOUT_SECONDS = 60
_FIGI = re.compile(r"[B-DF-HJ-NP-TV-Z]{2}G[B-DF-HJ-NP-TV-Z0-9]{8}[0-9]")
_ARTIFACT_ID = re.compile(r"arv2-openfigi-identities-\d{8}T\d{12}Z")
_ROW_FIELDS = frozenset(("figi", "securityType", "marketSector", "exchCode", "securityType2",
                         "ticker", "name", "shareClassFIGI", "compositeFIGI", "securityDescription"))
FALSE_FLAGS = prices.FALSE_FLAGS + (
    "historical_identity_authenticated", "validity_intervals_authenticated",
    "availability_intervals_authenticated", "correction_deletion_completeness_authenticated",
    "qc_sid_resolved", "independently_reviewed", "server_time_authenticated",
)


@dataclasses.dataclass(frozen=True)
class PublicIdentity:
    ticker: str
    role: str
    composite_figi: str = dataclasses.field(repr=False)
    share_class_figi: str = dataclasses.field(repr=False)
    response_row_sha256: str


@dataclasses.dataclass(frozen=True)
class PublicResponseBinding:
    json_file: str
    json_sha256: str
    json_byte_count: int
    tickers: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class LoadedPublicIdentityCapture:
    artifact_path: Path
    manifest_sha256: str
    capture_sha256: str
    capture_transport: str
    capture_started_at: str
    capture_completed_at: str
    responses: tuple[PublicResponseBinding, ...]
    identities: tuple[PublicIdentity, ...]


@dataclasses.dataclass(frozen=True)
class BoundPublicIdentityInput:
    input_path: Path
    input_sha256: str
    row_count: int
    public_reference_sha256: str
    sharadar_identity_manifest_sha256: str
    price_manifest_sha256: str


def _jobs(tickers: tuple[str, ...]) -> list[dict[str, object]]:
    return [{"idType": "TICKER", "idValue": ticker, "exchCode": "US", "currency": "USD",
             "marketSecDes": "Equity", "includeUnlistedEquities": False} for ticker in tickers]


def _valid_figi(value: object) -> bool:
    if type(value) is not str or _FIGI.fullmatch(value) is None:
        return False
    # https://www.openfigi.com/docs/figi-check-digit.pdf (IBM: BBG000BLNQ16).
    # FIGI's final decimal check digit uses a base-36, alternating doubled sum.
    values = [int(character, 36) * (1 if index % 2 == 0 else 2)
              for index, character in enumerate(value[:11])]
    total = sum(number // 10 + number % 10 for number in values)
    return int(value[-1]) == (10 - total % 10) % 10


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise OpenFigiIdentityCaptureError("public response contains duplicate JSON keys")
        result[key] = value
    return result


def _constant(_value: str) -> object:
    raise OpenFigiIdentityCaptureError("public response contains a nonfinite JSON constant")


def _parse_response(payload: bytes, tickers: tuple[str, ...]) -> tuple[PublicIdentity, ...]:
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_RESPONSE_BYTES:
        raise OpenFigiIdentityCaptureError("public response exceeds the bounded byte contract")
    try:
        document = json.loads(payload.decode("utf-8", errors="strict"),
                              object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeError, ValueError, RecursionError):
        raise OpenFigiIdentityCaptureError("public response is not bounded strict JSON") from None
    if type(document) is not list or len(document) != len(tickers):
        raise OpenFigiIdentityCaptureError("public response job cardinality differs from request")
    result = []
    for ticker, job in zip(tickers, document, strict=True):
        if type(job) is not dict or set(job) != {"data"}:
            raise OpenFigiIdentityCaptureError("public mapping job has error, warning or unrecognized shape")
        data = job["data"]
        if type(data) is not list or len(data) != 1:
            raise OpenFigiIdentityCaptureError("public mapping is missing or ambiguous")
        row = data[0]
        required = {"figi", "compositeFIGI", "shareClassFIGI", "ticker", "securityType", "marketSector", "exchCode"}
        if type(row) is not dict or not required <= set(row) <= _ROW_FIELDS:
            raise OpenFigiIdentityCaptureError("public mapping row lacks exact supported identity fields")
        if any(value is not None and (type(value) is not str or len(value) > 1024
                   or any(ord(character) < 32 or ord(character) == 127 for character in value))
               for value in row.values()):
            raise OpenFigiIdentityCaptureError("public mapping row metadata is malformed")
        if row["ticker"] != ticker or row["marketSector"] != "Equity" or row["exchCode"] != "US":
            raise OpenFigiIdentityCaptureError("public mapping escaped the requested ticker/market scope")
        expected_type = "Common Stock" if ticker == "QCOM" else "ETP"
        if row["securityType"] != expected_type:
            raise OpenFigiIdentityCaptureError("public mapping instrument category is not the frozen stock/fund role")
        if not all(_valid_figi(row[key]) for key in ("figi", "compositeFIGI", "shareClassFIGI")):
            raise OpenFigiIdentityCaptureError("public mapping FIGI identifier is invalid or unavailable")
        result.append(PublicIdentity(ticker, "stock" if ticker == "QCOM" else "fund",
                                     row["compositeFIGI"], row["shareClassFIGI"],
                                     sha256_bytes(canonical_json_bytes(row))))
    return tuple(result)


def _response_bytes(session: object, tickers: tuple[str, ...]) -> bytes:
    request_bytes = canonical_json_bytes(_jobs(tickers))
    response = None
    try:
        response = session.post(
            ENDPOINT, data=request_bytes, timeout=TIMEOUT_SECONDS, allow_redirects=False,
            stream=True, verify=True,
            headers={"Content-Type": "application/json", "Accept": "application/json", "Accept-Encoding": "identity"},
        )
        request = getattr(response, "request", None)
        if (type(getattr(response, "status_code", None)) is not int or response.status_code != 200
                or getattr(response, "history", None) != []
                or getattr(response, "url", None) != ENDPOINT
                or getattr(request, "method", None) != "POST"
                or getattr(request, "url", None) != ENDPOINT
                or getattr(request, "body", None) != request_bytes):
            raise OpenFigiIdentityCaptureError("public response request identity/status is not exact")
        request_headers = getattr(request, "headers", {})
        if any(str(name).casefold() in {"authorization", "x-openfigi-apikey", "cookie", "proxy-authorization"}
               for name in request_headers):
            raise OpenFigiIdentityCaptureError("public request unexpectedly contains credentials")
        headers = getattr(response, "headers", {})
        if headers.get("Content-Encoding", "identity").casefold() not in ("identity", ""):
            raise OpenFigiIdentityCaptureError("public response content encoding is unsupported")
        content_type = headers.get("Content-Type", "application/json").split(";", 1)[0].strip().casefold()
        if content_type != "application/json":
            raise OpenFigiIdentityCaptureError("public response content type is unsupported")
        declared = headers.get("Content-Length")
        if declared is not None and (type(declared) is not str or not declared.isascii()
                or not declared.isdecimal() or not 0 < int(declared) <= MAX_RESPONSE_BYTES):
            raise OpenFigiIdentityCaptureError("public response declared length is unsupported")
        chunks = []
        size = 0
        for chunk in response.iter_content(chunk_size=source.RESPONSE_CHUNK_BYTES):
            if type(chunk) is not bytes:
                raise OpenFigiIdentityCaptureError("public response stream is not bytes")
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise OpenFigiIdentityCaptureError("public response exceeded the byte limit")
            chunks.append(chunk)
        payload = b"".join(chunks)
        if declared is not None and len(payload) != int(declared):
            raise OpenFigiIdentityCaptureError("public response length differs from declared length")
        _parse_response(payload, tickers)
        return payload
    except OpenFigiIdentityCaptureError:
        raise
    except Exception:
        raise OpenFigiIdentityCaptureError("public mapping request failed; details redacted") from None
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                raise OpenFigiIdentityCaptureError("public response close failed; details redacted") from None


def _artifact_id(started: str) -> str:
    value = "arv2-openfigi-identities-" + started.translate(str.maketrans("", "", "-:."))
    if _ARTIFACT_ID.fullmatch(value) is None:
        raise OpenFigiIdentityCaptureError("public capture clock cannot form an artifact identity")
    return value


def _manifest(started: str, completed: str, transport: str,
              payloads: tuple[bytes, bytes]) -> dict[str, object]:
    if transport not in (PRODUCTION_TRANSPORT, TEST_TRANSPORT):
        raise OpenFigiIdentityCaptureError("public capture transport is unsupported")
    if parse_utc_timestamp(completed, "completed") < parse_utc_timestamp(started, "started"):
        raise OpenFigiIdentityCaptureError("public capture clock moved backwards")
    if len(payloads) != 2:
        raise OpenFigiIdentityCaptureError("public capture requires the exact two batches")
    rows = tuple(row for payload, batch in zip(payloads, BATCHES, strict=True)
                 for row in _parse_response(payload, batch))
    if (tuple(row.ticker for row in rows) != TICKERS
            or len({row.composite_figi for row in rows}) != 7
            or len({row.share_class_figi for row in rows}) != 7):
        raise OpenFigiIdentityCaptureError("public reference contains a cross-name identity collision")
    responses = [{"json_file": f"batch{index:02}.json", "json_sha256": sha256_bytes(payload),
                  "json_byte_count": len(payload), "tickers": list(batch),
                  "request_jobs": _jobs(batch), "endpoint": ENDPOINT}
                 for index, (payload, batch) in enumerate(zip(payloads, BATCHES, strict=True), 1)]
    identity = {"capture_started_at": started, "capture_completed_at": completed,
                "capture_transport": transport, "responses": responses,
                "identities": [dataclasses.asdict(row) for row in rows]}
    return {"schema": SCHEMA, "artifact_id": _artifact_id(started), **identity,
            "capture_sha256": sha256_bytes(canonical_json_bytes(identity)),
            "request_count": 2, "request_batch_sizes": [5, 2], "requested_name_count": 7,
            "response_byte_limit": MAX_RESPONSE_BYTES, "private_artifact": True,
            "unauthenticated_requests": True, "redirects_permitted": False, "retries_permitted": False,
            "current_public_reference_only": True,
            "identifier_license_semantics": "OpenFIGI_public_domain_identifier_strings_only_not_vendor_rows",
            "identity_semantics": "current_US_composites_and_global_share_classes_not_historical_intervals",
            "client_clock_semantics": "unsigned_local_receipt_not_original_publication_or_availability",
            "response_bytes_semantics": "requests_HTTP_entity_JSON_not_raw_wire_or_signed_server_proof",
            **dict.fromkeys(FALSE_FLAGS, False)}


def _inventory(descriptor: int, names: set[str]) -> None:
    if set(os.listdir(descriptor)) != names:
        raise OpenFigiIdentityCaptureError("public capture inventory is not exact")


def _pinned_directory_path(path: Path, descriptor: int) -> None:
    """Rewalk no-follow ancestors before returning an artifact/input pathname."""
    _path, named_fd = source._open_directory_path(path, create=False, name="public evidence root")
    assert named_fd is not None
    try:
        if source._directory_identity(os.fstat(descriptor)) != source._directory_identity(os.fstat(named_fd)):
            raise OpenFigiIdentityCaptureError("public evidence directory pathname identity changed")
    finally:
        os.close(named_fd)


def load_openfigi_identity_capture(artifact_path: Path, *, expected_manifest_sha256: str) -> LoadedPublicIdentityCapture:
    """Authenticate the external manifest pin and both original response byte sets."""
    root_fd = None
    held = []
    try:
        require_sha256(expected_manifest_sha256, "expected_manifest_sha256")
        root, root_fd = source._open_directory_path(artifact_path, create=False, name="public capture")
        assert root_fd is not None
        names = {"manifest.json", "manifest.sha256", "batch01.json", "batch02.json"}
        _inventory(root_fd, names)
        captured = {}
        for name in sorted(names):
            maximum = 65 if name.endswith(".sha256") else (MAX_MANIFEST_BYTES if name == "manifest.json" else MAX_RESPONSE_BYTES)
            descriptor = source._open_private_regular(root_fd, name, maximum=maximum, label="public evidence")
            try:
                payload, identity = source._read_open_private_regular(descriptor, maximum=maximum, label="public evidence")
            except BaseException:
                os.close(descriptor)
                raise
            held.append((name, descriptor, identity, maximum))
            captured[name] = payload
        digest = sha256_bytes(captured["manifest.json"])
        if digest != expected_manifest_sha256 or captured["manifest.sha256"] != (digest + "\n").encode("ascii"):
            raise OpenFigiIdentityCaptureError("public manifest differs from its external pinned digest")
        manifest = require_canonical_json_bytes(captured["manifest.json"], "public manifest")
        if type(manifest) is not dict:
            raise OpenFigiIdentityCaptureError("public manifest must be an object")
        try:
            payloads = (captured["batch01.json"], captured["batch02.json"])
            rebuilt = _manifest(manifest["capture_started_at"], manifest["capture_completed_at"],
                                manifest["capture_transport"], payloads)
        except KeyError:
            raise OpenFigiIdentityCaptureError("public manifest lacks required bindings") from None
        if canonical_json_bytes(rebuilt) != captured["manifest.json"] or root.name != rebuilt["artifact_id"]:
            raise OpenFigiIdentityCaptureError("public manifest/path differs from physical response evidence")
        rows = tuple(row for payload, batch in zip(payloads, BATCHES, strict=True) for row in _parse_response(payload, batch))
        bindings = tuple(PublicResponseBinding(f"batch{index:02}.json", sha256_bytes(payload), len(payload), batch)
                         for index, (payload, batch) in enumerate(zip(payloads, BATCHES, strict=True), 1))
        for name, descriptor, identity, maximum in held:
            source._require_open_leaf_identity(root_fd, name, descriptor, identity, maximum=maximum, label="public evidence")
        _inventory(root_fd, names)
        _pinned_directory_path(root, root_fd)
        return LoadedPublicIdentityCapture(root, digest, rebuilt["capture_sha256"], rebuilt["capture_transport"],
                                           rebuilt["capture_started_at"], rebuilt["capture_completed_at"], bindings, rows)
    except CanonicalEvidenceError:
        raise OpenFigiIdentityCaptureError("public manifest is not canonical evidence") from None
    finally:
        for _name, descriptor, _identity, _maximum in held:
            os.close(descriptor)
        if root_fd is not None:
            os.close(root_fd)


def _rollback_marker(child_fd: int, name: str, allocated: tuple[int, int] | None) -> None:
    if allocated is None:
        return
    try:
        named = os.stat(name, dir_fd=child_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if (named.st_dev, named.st_ino) != allocated:
        raise OpenFigiIdentityCaptureError("public publication state is ambiguous")
    os.unlink(name, dir_fd=child_fd)
    source._fsync(child_fd, "public completion-marker rollback")


def _capture_core(*, artifact_root: Path, session: object, clock: Callable[[], datetime],
                  transport: str, close_owned_session: bool) -> LoadedPublicIdentityCapture:
    root_fd = child_fd = None
    marker = None
    try:
        started = source._now_utc(clock)
        artifact_id = _artifact_id(started)
        root, root_fd = source._open_directory_path(artifact_root, create=True, name="public artifact root")
        assert root_fd is not None
        os.mkdir(artifact_id, 0o700, dir_fd=root_fd)
        child_fd = source._open_child_directory(root_fd, artifact_id, "public capture")
        payloads = []
        for index, batch in enumerate(BATCHES, 1):
            payload = _response_bytes(session, batch)
            source._write_private_bytes(child_fd, f"batch{index:02}.json", payload, "public response")
            payloads.append(payload)
        if close_owned_session:
            try:
                session.close()
            except Exception:
                raise OpenFigiIdentityCaptureError("public session close failed; details redacted") from None
        completed = source._now_utc(clock)
        manifest = canonical_json_bytes(_manifest(started, completed, transport, tuple(payloads)))
        if len(manifest) > MAX_MANIFEST_BYTES:
            raise OpenFigiIdentityCaptureError("public manifest exceeds byte limit")
        digest = sha256_bytes(manifest)
        source._write_private_bytes(child_fd, "manifest.pending", manifest, "pending public manifest")
        source._write_private_bytes(child_fd, "manifest.sha256", (digest + "\n").encode("ascii"), "public digest")
        _inventory(child_fd, {"batch01.json", "batch02.json", "manifest.pending", "manifest.sha256"})
        source._pinned_child(root_fd, artifact_id, child_fd, "public capture")
        source._fsync(child_fd, "public capture before publication")
        pending = os.stat("manifest.pending", dir_fd=child_fd, follow_symlinks=False)
        source._regular_metadata(pending, "pending public manifest", MAX_MANIFEST_BYTES)
        marker = (pending.st_dev, pending.st_ino)
        os.link("manifest.pending", "manifest.json", src_dir_fd=child_fd, dst_dir_fd=child_fd, follow_symlinks=False)
        named = os.stat("manifest.json", dir_fd=child_fd, follow_symlinks=False)
        if (named.st_dev, named.st_ino) != marker:
            raise OpenFigiIdentityCaptureError("public publication marker identity changed")
        os.unlink("manifest.pending", dir_fd=child_fd)
        source._fsync(child_fd, "public capture publication")
        source._fsync(root_fd, "public artifact root")
        source._pinned_child(root_fd, artifact_id, child_fd, "published public capture")
        loaded = load_openfigi_identity_capture(root / artifact_id, expected_manifest_sha256=digest)
        source._pinned_child(root_fd, artifact_id, child_fd, "reauthenticated public capture")
        return loaded
    except BaseException as exc:
        if child_fd is not None:
            try:
                _rollback_marker(child_fd, "manifest.json", marker)
            except (OSError, OpenFigiIdentityCaptureError):
                raise OpenFigiIdentityCaptureError("public publication state is ambiguous") from None
        if isinstance(exc, OpenFigiIdentityCaptureError) or not isinstance(exc, Exception):
            raise
        raise OpenFigiIdentityCaptureError("private public capture failed; details redacted") from None
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


def capture_openfigi_identities() -> LoadedPublicIdentityCapture:
    """No-key production entry owns and sanitizes an exact TLS requests Session."""
    source._require_operational_scope(DEFAULT_ARTIFACT_ROOT)
    source._preflight_root(DEFAULT_ARTIFACT_ROOT)
    raw = source._new_session()
    owned = source._OwnedSessionGuard(raw)
    try:
        import requests
        from requests.adapters import HTTPAdapter
        if type(raw) is not requests.Session or any(callable(value) for value in raw.__dict__.values()):
            raise OpenFigiIdentityCaptureError("production public transport is not an unmodified owned requests Session")
        raw.trust_env = False
        raw.verify = True
        raw.auth = raw.cert = None
        for attribute in ("proxies", "params", "cookies", "headers", "hooks", "adapters"):
            getattr(raw, attribute).clear()
        raw.mount("https://", HTTPAdapter(max_retries=0))
        return _capture_core(artifact_root=DEFAULT_ARTIFACT_ROOT, session=owned,
                             clock=lambda: datetime.now(timezone.utc), transport=PRODUCTION_TRANSPORT,
                             close_owned_session=True)
    except BaseException as exc:
        try:
            owned.close()
        except Exception:
            pass
        if isinstance(exc, OpenFigiIdentityCaptureError) or not isinstance(exc, Exception):
            raise
        raise OpenFigiIdentityCaptureError("public transport setup failed; details redacted") from None


def _capture_openfigi_identities_for_test(*, artifact_root: Path, session: object,
                                        clock: Callable[[], datetime]) -> LoadedPublicIdentityCapture:
    source._preflight_root(artifact_root)
    return _capture_core(artifact_root=artifact_root, session=session, clock=clock,
                         transport=TEST_TRANSPORT, close_owned_session=False)


def _bound_bytes(*, public_artifact_path: Path, expected_public_manifest_sha256: str,
                 sharadar_identity_artifact_path: Path, expected_sharadar_identity_manifest_sha256: str,
                 price_artifact_path: Path, expected_price_manifest_sha256: str,
                 synthetic: bool) -> bytes:
    for digest in (expected_public_manifest_sha256, expected_sharadar_identity_manifest_sha256, expected_price_manifest_sha256):
        require_sha256(digest, "external manifest pin")
    public = load_openfigi_identity_capture(public_artifact_path, expected_manifest_sha256=expected_public_manifest_sha256)
    price = prices.load_sharadar_price_capture(price_artifact_path, expected_manifest_sha256=expected_price_manifest_sha256)
    vendor = identities.load_sharadar_identity_capture(
        sharadar_identity_artifact_path, expected_manifest_sha256=expected_sharadar_identity_manifest_sha256,
        price_artifact_path=price_artifact_path,
    )
    if (public.capture_transport != (TEST_TRANSPORT if synthetic else PRODUCTION_TRANSPORT)
            or price.capture_transport != (prices.TEST_TRANSPORT if synthetic else prices.PRODUCTION_TRANSPORT)
            or vendor.capture_transport != (identities.TEST_TRANSPORT if synthetic else identities.PRODUCTION_TRANSPORT)):
        raise OpenFigiIdentityCaptureError("bound artifacts do not share the permitted production/test transport")
    if (price.close_session != identities.PRICE_CLOSE_SESSION or vendor.price_close_session != price.close_session
            or vendor.price_manifest_sha256 != price.manifest_sha256 or vendor.price_capture_sha256 != price.capture_sha256
            or tuple((row.role, row.row_count) for row in price.responses) != (("stocks", 1), ("funds", 6))):
        raise OpenFigiIdentityCaptureError("identity artifact is not bound to the pinned seven-name price evidence")
    if tuple(row.ticker for row in vendor.identities) != TICKERS or tuple(row.ticker for row in public.identities) != TICKERS:
        raise OpenFigiIdentityCaptureError("bound current identity census is not exact")
    if (len({row.composite_figi for row in vendor.identities}) != 7
            or len({row.permanent_share_class_id for row in vendor.identities}) != 7):
        raise OpenFigiIdentityCaptureError("bound vendor identity census has cross-name collisions")
    for pub, row in zip(public.identities, vendor.identities, strict=True):
        if (row.status != "matched_current_candidate" or row.refusal_codes
                or row.price_role != ("stocks" if pub.role == "stock" else "funds")
                or row.composite_figi != pub.composite_figi):
            raise OpenFigiIdentityCaptureError("cross-provider current identity binding is refused")
    # Every outbound identifier is selected from authenticated public response bytes.
    return canonical_json_bytes({"schema": INPUT_SCHEMA,
        "rows": [{"ticker": row.ticker, "role": row.role, "composite_figi": row.composite_figi} for row in public.identities],
        "price_manifest_sha256": price.manifest_sha256, "public_reference_sha256": public.manifest_sha256,
        "sharadar_identity_manifest_sha256": vendor.manifest_sha256})


def _bind_core(*, output_path: Path, synthetic: bool, **pins: object) -> BoundPublicIdentityInput:
    parent_fd = descriptor = None
    allocated = None
    try:
        if type(output_path) is not type(Path()):
            raise OpenFigiIdentityCaptureError("public input output must be a Path")
        if not synthetic:
            source._require_operational_scope(output_path)
        payload = _bound_bytes(synthetic=synthetic, **pins)
        if len(payload) > MAX_INPUT_BYTES:
            raise OpenFigiIdentityCaptureError("public identity input exceeds byte limit")
        parent, parent_fd = source._open_directory_path(output_path.parent, create=True, name="public input root")
        assert parent_fd is not None
        filename = output_path.name
        source._safe_leaf(filename, "public identity input")
        pending = filename + ".pending"
        descriptor = source._new_private_file(parent_fd, pending, "pending public identity input")
        opened = os.fstat(descriptor)
        allocated = (opened.st_dev, opened.st_ino)
        source._write_all(descriptor, payload, "public identity input")
        source._fsync(descriptor, "public identity input")
        observed, identity = source._read_open_private_regular(descriptor, maximum=MAX_INPUT_BYTES, label="pending public identity input")
        if observed != payload or _bound_bytes(synthetic=synthetic, **pins) != payload:
            raise OpenFigiIdentityCaptureError("public identity input source/readback changed")
        source._require_open_leaf_identity(parent_fd, pending, descriptor, identity,
                                          maximum=MAX_INPUT_BYTES, label="pending public identity input")
        os.link(pending, filename, src_dir_fd=parent_fd, dst_dir_fd=parent_fd, follow_symlinks=False)
        named = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
        if (named.st_dev, named.st_ino) != allocated:
            raise OpenFigiIdentityCaptureError("public input publication marker identity changed")
        os.unlink(pending, dir_fd=parent_fd)
        observed, identity = source._read_open_private_regular(descriptor, maximum=MAX_INPUT_BYTES, label="public identity input")
        if observed != payload or _bound_bytes(synthetic=synthetic, **pins) != payload:
            raise OpenFigiIdentityCaptureError("published public identity input source/readback changed")
        source._require_open_leaf_identity(parent_fd, filename, descriptor, identity,
                                          maximum=MAX_INPUT_BYTES, label="public identity input")
        source._fsync(parent_fd, "public input root")
        _pinned_directory_path(parent, parent_fd)
        return BoundPublicIdentityInput(parent / filename, sha256_bytes(payload), 7,
            pins["expected_public_manifest_sha256"], pins["expected_sharadar_identity_manifest_sha256"],
            pins["expected_price_manifest_sha256"])
    except BaseException as exc:
        if parent_fd is not None:
            try:
                _rollback_marker(parent_fd, output_path.name, allocated)
            except (OSError, OpenFigiIdentityCaptureError):
                raise OpenFigiIdentityCaptureError("public input publication state is ambiguous") from None
        if isinstance(exc, OpenFigiIdentityCaptureError) or not isinstance(exc, Exception):
            raise
        raise OpenFigiIdentityCaptureError("private identity binding failed; details redacted") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent_fd is not None:
            os.close(parent_fd)


def bind_public_identity_input(*, public_artifact_path: Path, expected_public_manifest_sha256: str,
                               sharadar_identity_artifact_path: Path, expected_sharadar_identity_manifest_sha256: str,
                               price_artifact_path: Path, expected_price_manifest_sha256: str,
                               output_path: Path) -> BoundPublicIdentityInput:
    """Write a private public-only QC diagnostic input; no network or formal admission."""
    return _bind_core(output_path=output_path, synthetic=False,
        public_artifact_path=public_artifact_path, expected_public_manifest_sha256=expected_public_manifest_sha256,
        sharadar_identity_artifact_path=sharadar_identity_artifact_path,
        expected_sharadar_identity_manifest_sha256=expected_sharadar_identity_manifest_sha256,
        price_artifact_path=price_artifact_path, expected_price_manifest_sha256=expected_price_manifest_sha256)


def _bind_public_identity_input_for_test(*, output_path: Path, **pins: object) -> BoundPublicIdentityInput:
    return _bind_core(output_path=output_path, synthetic=True, **pins)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("capture")
    bind = sub.add_parser("bind")
    for name in ("public-artifact-path", "sharadar-identity-artifact-path", "price-artifact-path", "output-path"):
        bind.add_argument("--" + name, required=True, type=Path)
    for name in ("expected-public-manifest-sha256", "expected-sharadar-identity-manifest-sha256", "expected-price-manifest-sha256"):
        bind.add_argument("--" + name, required=True)
    args = vars(parser.parse_args(argv))
    command = args.pop("command")
    try:
        loaded = capture_openfigi_identities() if command == "capture" else bind_public_identity_input(**args)
    except OpenFigiIdentityCaptureError as exc:
        print(f"refused={exc}", file=sys.stderr)
        return 1
    except Exception:
        print("refused=public identity capture/binding failed; details redacted", file=sys.stderr)
        return 1
    if command == "capture":
        print(f"artifact={loaded.artifact_path}\nmanifest_sha256={loaded.manifest_sha256}\ncapture_sha256={loaded.capture_sha256}\nrows=7")
    else:
        print(f"input={loaded.input_path}\ninput_sha256={loaded.input_sha256}\nrows={loaded.row_count}")
    print("point_in_time_proven=false formal_source_admitted=false independently_reviewed=false decision_ready=false paper_ready=false orders_enabled=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
