"""One-shot, metadata-only provider probes; import is inert.

This module has no dataset, upload, compile, job, or outcome endpoint. HTTP
access is not a licence, subscription, historical-coverage, or research grant.
Massive's public market-status response cannot prove the bearer key was used.
Sharadar's bulk-file status cannot prove the contents or paid history rights.
The caller must journal its authorized attempt BEFORE calling the probe.

Profiles: QuantConnect's authenticate RestResponse; Massive market-status-now;
direct Sharadar tickers bulk status (table/name/size/sizeLabel/modified). Their
public documentation is the schema reference, not an authenticated capture.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import os
import re
import ssl
import time
from typing import Callable, Mapping
from urllib import error, request

from research.quantconnect import QuantConnectCredentials, build_auth_headers

MAX_BODY_BYTES = 1024 * 1024
TIMEOUT_SECONDS = 15
SHARADAR_KEY_ENV = "SHARADAR_API_KEY"
_PROFILES = {
    "quantconnect": ("qc-authenticate-v1", "POST", "https://www.quantconnect.com/api/v2/authenticate", b"{}"),
    "massive": ("massive-marketstatus-now-v1", "GET", "https://api.massive.com/v1/marketstatus/now", None),
    "sharadar": ("sharadar-tickers-bulk-status-v1", "GET", "https://api.sharadar.com/v1.0/data/tickers?status=True", None),
}
_STATUSES = frozenset({"open", "closed", "extended-hours"})
_UTC_TEXT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z")


class ProviderMetadataTransportError(ValueError):
    """A caller used a non-profile operation; messages contain no values."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ProviderMetadataTransportError(code)


@dataclass(frozen=True, slots=True)
class ProviderMetadataRequest:
    provider: str
    method: str
    url: str
    headers: tuple[tuple[str, str], ...] = field(repr=False)
    body: bytes | None = field(repr=False)
    timeout_seconds: int = TIMEOUT_SECONDS

    def __repr__(self) -> str:
        # Do not print a reconstructed/mutated URL, header, body, or provider.
        return "ProviderMetadataRequest(<fixed metadata profile; credentials redacted>)"


@dataclass(frozen=True, slots=True)
class ProviderMetadataResponse:
    status: int | None
    body: bytes = field(repr=False)
    body_complete: bool = True
    disposition: str | None = None

    def __repr__(self) -> str:
        return "ProviderMetadataResponse(<body redacted>)"


@dataclass(frozen=True, slots=True)
class ProviderMetadataReceipt:
    provider: str
    request_profile: str
    http_status: int | None
    body_sha256: str | None
    body_size_bytes: int
    body_complete: bool
    disposition: str
    _facts: bytes = field(repr=False)

    @property
    def facts(self) -> dict:
        return json.loads(self._facts)

    def to_dict(self) -> dict:
        return {
            "kind": "insider-provider-metadata-receipt-v1", "provider": self.provider,
            "request_profile": self.request_profile, "http_status": self.http_status,
            "body_sha256": self.body_sha256, "body_size_bytes": self.body_size_bytes,
            "body_complete": self.body_complete, "disposition": self.disposition,
            "facts": self.facts,
            "http_access_observed": self.http_status is not None,
            "authentication_observed": self.disposition == "qc-authentication-observed",
            "entitlement_verified": False, "rights_verified": False,
            "historical_coverage_verified": False, "research_ready": False,
            "qc_backtest_authorized": False, "outcome_access_authorized": False,
        }

    def to_payload(self) -> dict:
        return self.to_dict()


def _receipt(provider: str, response: ProviderMetadataResponse | None, disposition: str,
             facts: dict | None = None) -> ProviderMetadataReceipt:
    raw = None if response is None else response.body
    return ProviderMetadataReceipt(provider, _PROFILES[provider][0],
        None if response is None else response.status,
        None if raw is None else hashlib.sha256(raw).hexdigest(),
        0 if raw is None else len(raw), False if response is None else response.body_complete,
        disposition, json.dumps(facts or {}, sort_keys=True, separators=(",", ":")).encode())


def _credential(source: Mapping[str, str], name: str) -> str:
    value = source.get(name)
    _require(value is not None and value != "", "credentials-missing")
    _require(type(value) is str and 1 <= len(value) <= 4096
             and all(33 <= ord(char) <= 126 for char in value), "credentials-invalid")
    _require(value.casefold() != "test-api-key", "credentials-invalid")
    return value


def _build_request(provider: str, environ: Mapping[str, str], clock: Callable[[], int]) -> ProviderMetadataRequest:
    _require(type(provider) is str and provider in _PROFILES, "unknown-provider")
    _, method, url, body = _PROFILES[provider]
    headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
    if provider == "quantconnect":
        user = _credential(environ, "QC_USER_ID")
        token = _credential(environ, "QC_API_TOKEN")
        _require(re.fullmatch(r"[0-9]{1,20}", user) is not None, "credentials-invalid")
        stamp = clock()
        _require(type(stamp) is int and 0 < stamp <= 2**63 - 1, "clock-invalid")
        headers.update(build_auth_headers(QuantConnectCredentials(user, token), stamp))
        headers["Content-Type"] = "application/json"
    elif provider == "massive":
        headers["Authorization"] = "Bearer " + _credential(environ, "MASSIVE_API_KEY")
    else:
        headers["x-api-key"] = _credential(environ, SHARADAR_KEY_ENV)
    result = ProviderMetadataRequest(provider, method, url, tuple(headers.items()), body)
    _validate_request(result)
    return result


def _validate_request(item: ProviderMetadataRequest) -> None:
    _require(type(item) is ProviderMetadataRequest and type(item.provider) is str
             and item.provider in _PROFILES, "invalid-request")
    _, method, url, body = _PROFILES[item.provider]
    _require(type(item.method) is str and item.method == method and type(item.url) is str
             and item.url == url and type(item.body) is type(body) and item.body == body
             and type(item.timeout_seconds) is int and item.timeout_seconds == TIMEOUT_SECONDS,
             "invalid-request")
    _require(type(item.headers) is tuple and all(type(row) is tuple and len(row) == 2
             and all(type(value) is str for value in row) for row in item.headers), "invalid-request")
    headers = dict(item.headers)
    expected = {"Accept", "Accept-Encoding"}
    expected |= {"Authorization", "Timestamp", "Content-Type"} if item.provider == "quantconnect" else {
        "Authorization" if item.provider == "massive" else "x-api-key"}
    _require(len(headers) == len(item.headers) and set(headers) == expected
             and headers["Accept"] == "application/json" and headers["Accept-Encoding"] == "identity"
             and all(0 < len(value) <= 8192 and all(32 <= ord(char) <= 126 for char in value)
                     for value in headers.values()), "invalid-request")
    if item.provider == "quantconnect":
        _require(re.fullmatch(r"Basic [A-Za-z0-9+/]+={0,2}", headers["Authorization"]) is not None
                 and re.fullmatch(r"[1-9][0-9]{0,18}", headers["Timestamp"]) is not None
                 and headers["Content-Type"] == "application/json", "invalid-request")
    elif item.provider == "massive":
        _require(headers["Authorization"].startswith("Bearer ")
                 and re.fullmatch(r"[!-~]{1,4096}", headers["Authorization"][7:]) is not None,
                 "invalid-request")
    else:
        _require(re.fullmatch(r"[!-~]{1,4096}", headers["x-api-key"]) is not None
                 and headers["x-api-key"].casefold() != "test-api-key", "invalid-request")


class _DenyRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _read_bounded(stream, status: int) -> ProviderMetadataResponse:
    """Read at most MAX+1 transient bytes, even for error responses."""
    chunks: list[bytes] = []
    count = 0
    length = None
    try:
        encoding = stream.headers.get("Content-Encoding")
        if encoding is not None and encoding.lower().strip() != "identity":
            return ProviderMetadataResponse(status, b"", False, "unsupported-content-encoding")
        declared = stream.headers.get("Content-Length")
        if declared is not None:
            if re.fullmatch(r"[0-9]{1,20}", declared) is None:
                return ProviderMetadataResponse(status, b"", False, "invalid-content-length")
            length = int(declared)
            if length > MAX_BODY_BYTES:
                return ProviderMetadataResponse(status, b"", False, "oversized-response")
        while count <= MAX_BODY_BYTES:
            chunk = stream.read(min(65536, MAX_BODY_BYTES + 1 - count))
            if type(chunk) is not bytes:
                return ProviderMetadataResponse(status, b"".join(chunks), False, "partial-read")
            if not chunk:
                raw = b"".join(chunks)
                if length is not None and length != count:
                    return ProviderMetadataResponse(status, raw, False, "truncated-response")
                return ProviderMetadataResponse(status, raw)
            # Defend injected/misbehaving streams that ignore their size argument.
            chunk = chunk[:MAX_BODY_BYTES + 1 - count]
            chunks.append(chunk)
            count += len(chunk)
            if count > MAX_BODY_BYTES:
                return ProviderMetadataResponse(status, b"".join(chunks), False, "oversized-response")
    except Exception:
        return ProviderMetadataResponse(status, b"".join(chunks), False, "partial-read")
    return ProviderMetadataResponse(status, b"".join(chunks), False, "oversized-response")


def _default_transport(item: ProviderMetadataRequest) -> ProviderMetadataResponse:
    _validate_request(item)
    # Explicit empty proxy configuration prevents ambient HTTP(S)_PROXY use.
    opener = request.build_opener(request.ProxyHandler({}), _DenyRedirect(),
                                 request.HTTPSHandler(context=ssl.create_default_context()))
    req = request.Request(item.url, data=item.body, headers=dict(item.headers), method=item.method)
    stream = None
    try:
        try:
            stream = opener.open(req, timeout=TIMEOUT_SECONDS)
        except error.HTTPError as exc:
            stream = exc
        status = stream.getcode()
        if type(status) is not int or not 100 <= status <= 599:
            return ProviderMetadataResponse(None, b"", False, "invalid-http-status")
        if stream.geturl() != item.url:
            return ProviderMetadataResponse(status, b"", False, "response-origin-mismatch")
        response = _read_bounded(stream, status)
        if 300 <= status < 400:
            return ProviderMetadataResponse(status, response.body, response.body_complete, "redirect-refused")
        return response
    except (TimeoutError,):
        return ProviderMetadataResponse(None, b"", False, "transport-timeout")
    except error.URLError as exc:
        code = "transport-timeout" if isinstance(exc.reason, TimeoutError) else "transport-error"
        return ProviderMetadataResponse(None, b"", False, code)
    except Exception:
        return ProviderMetadataResponse(None, b"", False, "transport-error")
    finally:
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "invalid-metadata-schema")
        result[key] = value
    return result


def _json(raw: bytes) -> dict:
    def refuse_number(value):
        raise ProviderMetadataTransportError("invalid-metadata-schema")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                       parse_float=refuse_number, parse_constant=refuse_number)
    _require(type(value) is dict, "invalid-metadata-schema")
    return value


def _timestamp(value: object, *, utc_only: bool = False) -> None:
    _require(type(value) is str and _UTC_TEXT.fullmatch(value) is not None, "invalid-metadata-schema")
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _require(instant.utcoffset() is not None and (not utc_only or instant.utcoffset().total_seconds() == 0),
             "invalid-metadata-schema")


def _facts(provider: str, raw: bytes) -> tuple[str, dict]:
    body = _json(raw)
    if provider == "quantconnect":
        _require(set(body) <= {"success", "errors"} and type(body.get("success")) is bool,
                 "invalid-metadata-schema")
        errors = body.get("errors", [])
        _require(type(errors) is list and len(errors) <= 100 and all(type(v) is str for v in errors)
                 and (body["success"] is False or not errors), "invalid-metadata-schema")
        return ("qc-authentication-observed" if body["success"] else "authentication-refused"), {
            "success": body["success"]}
    if provider == "massive":
        _require(set(body) <= {"market", "earlyHours", "afterHours", "serverTime", "currencies",
                              "exchanges", "indicesGroups"} and "market" in body,
                 "invalid-metadata-schema")
        _require(type(body["market"]) is str and body["market"] in _STATUSES, "invalid-metadata-schema")
        for name in ("earlyHours", "afterHours"):
            if name in body:
                _require(type(body[name]) is bool, "invalid-metadata-schema")
        if "serverTime" in body:
            _timestamp(body["serverTime"])
        for name, keys in (
            ("currencies", {"crypto", "fx"}), ("exchanges", {"nasdaq", "nyse", "otc"}),
            ("indicesGroups", {"cccy", "cgi", "dow_jones", "ftse_russell", "msci", "mstar",
                               "mstarc", "nasdaq", "s_and_p", "societe_generale"}),
        ):
            if name in body:
                _require(type(body[name]) is dict and set(body[name]) <= keys and
                         all(type(v) is str and v in _STATUSES for v in body[name].values()),
                         "invalid-metadata-schema")
        return "public-market-status-observed", body
    _require(set(body) == {"table", "name", "size", "sizeLabel", "modified"}
             and body["table"] == "tickers" and type(body["table"]) is str
             and body["name"] == "tickers.csv.zip" and type(body["name"]) is str
             and type(body["size"]) is int and 0 <= body["size"] <= 2**63 - 1
             and type(body["sizeLabel"]) is str and len(body["sizeLabel"]) <= 32
             and re.fullmatch(r"[0-9]{1,20}(?:\.[0-9]{1,2})? (?:B|KB|MB|GB|TB)", body["sizeLabel"]) is not None,
             "invalid-metadata-schema")
    _timestamp(body["modified"], utc_only=True)
    return "bulk-status-metadata-observed", {key: body[key] for key in ("table", "name", "size", "modified")}


def parse_provider_metadata(provider: str, status: int, raw: bytes) -> ProviderMetadataReceipt:
    """Pure content parsing; an injected/supplied response proves no provenance."""
    _require(type(provider) is str and provider in _PROFILES, "unknown-provider")
    _require(type(status) is int and 100 <= status <= 599 and type(raw) is bytes, "invalid-response")
    response = ProviderMetadataResponse(status, raw)
    if len(raw) > MAX_BODY_BYTES:
        # Do not preserve an unbounded caller buffer in the receipt.
        response = ProviderMetadataResponse(status, raw[:MAX_BODY_BYTES + 1], False)
        return _receipt(provider, response, "oversized-response")
    if 300 <= status < 400:
        return _receipt(provider, response, "redirect-refused")
    if status in {401, 403}:
        return _receipt(provider, response, "authentication-http-refused")
    if status == 429:
        return _receipt(provider, response, "rate-limited")
    if not 200 <= status < 300:
        return _receipt(provider, response, "http-error")
    try:
        disposition, facts = _facts(provider, raw)
    except Exception:
        return _receipt(provider, response, "invalid-metadata-schema")
    return _receipt(provider, response, disposition, facts)


def probe_provider_metadata(provider: str, *, environ: Mapping[str, str] | None = None,
                            transport: Callable[[ProviderMetadataRequest], ProviderMetadataResponse] | None = None,
                            clock: Callable[[], int] | None = None) -> ProviderMetadataReceipt:
    """Exactly one fixed metadata request, no retry, after caller authorization.

    Raw bodies and secrets are transient and never retained in the receipt.
    Exceptions from credentials, injected transports, and reads are classified,
    never interpolated or chained into output.
    """
    _require(type(provider) is str and provider in _PROFILES, "unknown-provider")
    try:
        item = _build_request(provider, os.environ if environ is None else environ,
                              (lambda: int(time.time())) if clock is None else clock)
    except ProviderMetadataTransportError as exc:
        code = str(exc)
        return _receipt(provider, None, code if code in {"credentials-missing", "credentials-invalid", "clock-invalid"}
                        else "request-refused")
    except Exception:
        return _receipt(provider, None, "request-refused")
    try:
        response = (_default_transport if transport is None else transport)(item)
    except Exception:
        return _receipt(provider, None, "transport-error")
    allowed = {None, "unsupported-content-encoding", "invalid-content-length", "oversized-response",
               "truncated-response", "partial-read", "redirect-refused", "invalid-http-status",
               "response-origin-mismatch", "transport-timeout", "transport-error"}
    if (type(response) is not ProviderMetadataResponse or type(response.body) is not bytes
        or type(response.body_complete) is not bool
        or (response.disposition is not None and type(response.disposition) is not str)
        or response.disposition not in allowed
        or (response.status is not None and (type(response.status) is not int or not 100 <= response.status <= 599))):
        return _receipt(provider, None, "invalid-transport-result")
    if len(response.body) > MAX_BODY_BYTES:
        bounded = ProviderMetadataResponse(response.status, response.body[:MAX_BODY_BYTES + 1], False)
        return _receipt(provider, bounded, "oversized-response")
    if response.disposition is not None or response.status is None or not response.body_complete:
        return _receipt(provider, response, response.disposition or "partial-read")
    return parse_provider_metadata(provider, response.status, response.body)
