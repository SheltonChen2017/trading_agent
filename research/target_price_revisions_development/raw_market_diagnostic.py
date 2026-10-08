"""One error-only diagnostic; never renew or consume a market-data look.

Successful/redirect bodies are never read. Error bodies are ephemeral, bounded,
never persisted, printed or hashed. Imports perform no I/O. The private market
plan remains private; public diagnostics contain only closed coarse categories.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import http.client
import html
import json
import os
import re
import ssl
from urllib.parse import unquote, urlencode

from . import raw_market_capture as market

DIAGNOSTIC_ID = "TPR-RAWREV-MARKET-DIAGNOSTIC-20261007-001"
ORIGINAL_PLAN_SHA256 = "3a215f293cae4ad9c150e2bd0ff4d63b6d6cf970c6af7ea2bcf7b9ed2b58c76c"
FAILED_REPORT_SHA256 = "491064c4da6ea38d194a3edac2e482d9b9bfd14657db1ca66ef5a643036e03d1"
_production_credential = market._FIXED_RESOLVER
_FIXED_RESOLVER = _production_credential
PARAMETERS = ("format", "ticker", "from", "to", "fields", "limit", "skip", "sort")
ERROR_CODES = ("BAD_REQUEST", "UNAUTHORIZED", "FORBIDDEN", "INVALID_PARAMETER", "TICKER_LIMIT_EXCEEDED")


class DiagnosticError(ValueError):
    """Fixed errors never contain provider/private values."""


@dataclass(frozen=True)
class DiagnosticPlan:
    payload: bytes
    sha256: str

    def body(self):
        try:
            if type(self.payload) is not bytes or not 0 < len(self.payload) <= 16384 or market.source._digest(self.payload) != self.sha256:
                raise DiagnosticError("invalid diagnostic identity")
            body = market.raw_run._decode(self.payload, 16384)
            expected = freeze_diagnostic_plan(**{key: body[key] for key in ("code_sha256", "market_plan_sha256",
                "failed_capture_report_sha256", "git_sha", "owner_instruction_sha256", "created_utc", "expires_utc", "mode")})
            if self.payload != expected.payload:
                raise DiagnosticError("diagnostic scope differs")
            return body
        except (KeyError, TypeError, ValueError):
            raise DiagnosticError("invalid diagnostic policy") from None


def freeze_diagnostic_plan(*, code_sha256, market_plan_sha256, failed_capture_report_sha256,
                           git_sha, owner_instruction_sha256, created_utc, expires_utc, mode="production"):
    for value in (code_sha256, market_plan_sha256, failed_capture_report_sha256, owner_instruction_sha256):
        market.source._hash(value)
    market.source._hash(git_sha, 40)
    created, expires = market.source._clock(created_utc), market.source._clock(expires_utc)
    if (type(mode) is not str or mode not in ("production", "offline-fixture")
            or not created < expires <= created + timedelta(hours=48)
            or owner_instruction_sha256 != market.raw_run.OWNER_WAIVER_INSTRUCTION_SHA256):
        raise DiagnosticError("invalid diagnostic clock or owner scope")
    if mode == "production" and (market_plan_sha256 != ORIGINAL_PLAN_SHA256 or failed_capture_report_sha256 != FAILED_REPORT_SHA256):
        raise DiagnosticError("diagnostic is limited to the exact failed operation")
    payload = market.source._canonical({"schema": "tpr-raw-market-diagnostic-plan-v1", "diagnostic_id": DIAGNOSTIC_ID,
        "owner_decision": "TPR-OWN-43", "code_sha256": code_sha256, "market_plan_sha256": market_plan_sha256,
        "failed_capture_report_sha256": failed_capture_report_sha256, "git_sha": git_sha,
        "owner_instruction_sha256": owner_instruction_sha256, "created_utc": created.isoformat(), "expires_utc": expires.isoformat(),
        "mode": mode, "lane_root": str(market.raw_run.LANE_ROOT), "lane_branch": market.raw_run.LANE_BRANCH,
        "private_root": str(market.PRODUCTION_ROOT), "request": "exact-original-stocks-page-zero",
        "requests": 1, "error_bytes": 8192, "request_seconds": 30, "redirects": 0, "retries": 0,
        "successful_body_reads": 0, "raw_error_retention": False, "raw_error_identity_retention": False,
        "additional_development_looks": 0, "outcomes": False, "quantconnect": False, "trading": False})
    return DiagnosticPlan(payload, market.source._digest(payload))


@dataclass(frozen=True)
class DiagnosticResponse:
    status: int
    headers: tuple
    body: bytes
    complete: bool = True


def _https_get(tickers, credential):
    query = market.request_query("stocks", 0, tickers)
    if not market.source._valid_credential(credential):
        raise DiagnosticError("diagnostic credential unavailable")
    connection = None
    try:
        with market.source._deadline():
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname, context.verify_mode, context.keylog_filename = True, ssl.CERT_REQUIRED, None
            context.load_default_certs()
            connection = http.client.HTTPSConnection("api.sharadar.com", 443, timeout=30, context=context)
            connection.set_debuglevel(0)
            connection.request("GET", "/v1.0/data/stocks?" + urlencode(query + (("api_key", credential),)),
                headers={"Accept": "text/csv", "Accept-Encoding": "identity", "Connection": "close", "User-Agent": "TPR-private-market/1"})
            response = connection.getresponse()
            headers = tuple((key.lower(), value) for key, value in response.getheaders()
                if key.lower() in ("content-type", "content-encoding", "content-length"))
            meta = dict(headers)
            # Never read a successful, redirect, encoded or native-CSV body.
            if (200 <= response.status < 400 or len(headers) != len(meta)
                    or meta.get("content-encoding", "").strip().lower() not in ("", "identity")
                    or meta.get("content-type", "").split(";", 1)[0].strip().lower()
                        not in ("application/json", "application/problem+json", "text/plain")):
                return DiagnosticResponse(response.status, headers, b"", False)
            length = meta.get("content-length")
            if length is not None and (re.fullmatch(r"[0-9]{1,9}", length) is None or int(length) > 8192):
                return DiagnosticResponse(response.status, headers, b"", False)
            body = response.read(8192)
            complete = len(body) < 8192 or response.isclosed()
            if length is not None and len(body) != int(length):
                complete = False
            return DiagnosticResponse(response.status, headers, body, complete)
    except (OSError, http.client.HTTPException, market.source._Deadline):
        raise DiagnosticError("diagnostic transport failed") from None
    finally:
        if connection is not None:
            connection.close()


_FIXED_TRANSPORT = _https_get


def classify_error_body(payload, credential):
    if type(payload) is not bytes or len(payload) > 8192:
        raise DiagnosticError("invalid diagnostic error bytes")
    result = {"category": "unknown_response", "parameter_names": [], "error_code": None}
    if market.source._credential_echo(payload, credential):
        return dict(result, category="echo_suppressed")
    text = payload.decode("utf-8", errors="replace")
    for _ in range(3):
        text = html.unescape(unquote(text))
        text = re.sub(r"\\u([0-9a-fA-F]{4})", lambda match: chr(int(match[1], 16)), text)
    if re.search(r"https?://|api[_-]?key\s*[=:]|authorization\s*:", text, re.I):
        return dict(result, category="echo_suppressed")
    try:
        body = json.loads(text)
        if type(body) is not dict or set(body) - {"error", "message", "detail", "status", "code"}:
            return result
        if any(type(value) not in (str, int, type(None)) for value in body.values()):
            return result
        text = " ".join(body[key] for key in ("error", "message", "detail") if type(body.get(key)) is str)
        code = body.get("code")
        result["error_code"] = code if type(code) is str and code in ERROR_CODES else None
    except (ValueError, TypeError):
        if payload.lstrip().startswith((b"{", b"[")):
            return result
    if re.search(r"https?://|api[_-]?key\s*[=:]|authorization\s*:", text, re.I):
        return {"category": "echo_suppressed", "parameter_names": [], "error_code": None}
    lower = text.lower()
    if re.search(r"too many.*tickers?|tickers?.*(?:limit|maximum)|maximum.*tickers?", lower):
        result["category"] = "ticker_limit"
    elif re.search(r"unauthoriz|authentication|invalid api|missing api", lower):
        result["category"] = "authentication"
    elif re.search(r"forbid|entitlement|permission|subscription|not subscribed|access denied", lower):
        result["category"] = "entitlement"
    elif re.search(r"invalid|unsupported|unrecognized|parameter|argument", lower):
        result["category"] = "invalid_parameter"
        result["parameter_names"] = [name for name in PARAMETERS if re.search(r"\b" + name + r"\b", lower)]
    return result


def _failed_report(fd, plan, original):
    body = plan.body()
    identity = body["failed_capture_report_sha256"]
    report = market.raw_run._decode(market.raw_run._read_file(fd, market.CAPTURE_ID + "." + identity + ".aggregate.json", 65536, identity), 65536)
    if (report.get("schema") != "tpr-raw-market-capture-report-v1" or report.get("market_plan_sha256") != original.sha256
            or report.get("candidate_id") != market.CANDIDATE_ID or report.get("capture_id") != market.CAPTURE_ID
            or report.get("mode") != body["mode"] or report.get("status") != "FAILED"
            or type(report.get("last_http_status")) is not int or report["last_http_status"] != 400
            or report.get("failure_stage") != "response" or report.get("projection_sha256") is not None
            or type(report.get("native_source_row_counts")) is not dict or set(report["native_source_row_counts"]) != {"stocks", "actions"}
            or any(type(v) is not int or v != 0 for v in report["native_source_row_counts"].values())
            or type(report.get("response_bytes")) is not int or report["response_bytes"] != 0
            or type(report.get("provider_requests")) is not int or report["provider_requests"] != (1 if body["mode"] == "production" else 0)
            or type(report.get("fixture_transport_calls")) is not int or report["fixture_transport_calls"] != (1 if body["mode"] == "offline-fixture" else 0)):
        raise DiagnosticError("diagnostic requires the exact failed first request")


def _now():
    return datetime.now(timezone.utc)


def execute_diagnostic(plan, original):
    if type(plan) is not DiagnosticPlan or plan.body()["mode"] != "production":
        raise DiagnosticError("public diagnostic is production-only")
    return _execute(plan, original, market.PRODUCTION_ROOT)


def _execute_fixture_diagnostic(plan, original, root, *, now=None, credential_resolver=None, transport=None):
    if type(plan) is not DiagnosticPlan or plan.body()["mode"] != "offline-fixture" or root == market.PRODUCTION_ROOT:
        raise DiagnosticError("fixture diagnostic requires synthetic root and mode")
    return _execute(plan, original, root, now=now, credential_resolver=credential_resolver, transport=transport)


def _execute(plan, original, root, *, now=None, credential_resolver=None, transport=None):
    body = plan.body()
    if type(original) is not market.CapturePlan or original.sha256 != body["market_plan_sha256"]:
        raise DiagnosticError("original market plan differs")
    old = original.body()
    if old["mode"] != body["mode"] or old["git_sha"] != body["git_sha"]:
        raise DiagnosticError("diagnostic lane or mode differs")
    if body["mode"] == "production":
        if now is not None or credential_resolver is not None or transport is not None or root != market.PRODUCTION_ROOT:
            raise DiagnosticError("production diagnostic adapters cannot change")
        market.raw_run._verify_lane()
        market.source._verify_identity({"git_sha": body["git_sha"], "code_sha256": old["transport_parent_sha256"]})
        market._verify_code(old)
        market.source._verify_code(market.raw_run.LANE_ROOT / "research/target_price_revisions_development/raw_market_diagnostic.py", body["code_sha256"])
    elif (credential_resolver is None or transport is None or credential_resolver in (_FIXED_RESOLVER, _production_credential)
            or transport in (_FIXED_TRANSPORT, _https_get)):
        raise DiagnosticError("fixture diagnostic requires synthetic adapters")
    current = _now() if now is None else now
    market._before_expiry(body, current)
    market._before_expiry(old, current)
    fd = market.raw_run._open_root(root, body["mode"])
    try:
        market._read_reservation(fd, old, original)
        _failed_report(fd, plan, original)
        try:
            claim = os.open(DIAGNOSTIC_ID + ".spent.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            raise DiagnosticError("diagnostic already spent") from None
        stage, status, attempts, http_status, received, category = "claim", "FAILED", 0, None, 0, {"category": "unknown_response", "parameter_names": [], "error_code": None}
        interrupted = False
        try:
            try:
                market.source._write_fd(claim, market.source._canonical({"schema": "tpr-raw-market-diagnostic-spent-v1",
                    "diagnostic_id": DIAGNOSTIC_ID, "plan_sha256": plan.sha256, "started_utc": current.isoformat()}))
                os.fsync(fd)
            finally:
                os.close(claim)
            stage = "expiry"
            clock = _now() if now is None else now
            market._before_expiry(body, clock)
            market._before_expiry(old, clock)
            stage = "credential"
            resolver = _production_credential if body["mode"] == "production" else credential_resolver
            fetch = _https_get if body["mode"] == "production" else transport
            credential = resolver("sharadar")
            if not market.source._valid_credential(credential) or body["mode"] == "offline-fixture" and not credential.startswith("SYNTHETIC_"):
                raise DiagnosticError("diagnostic credential unavailable")
            stage = "transport"
            attempts = 1
            response = fetch(tuple(old["tickers"]), credential)
            stage = "response"
            if (type(response) is not DiagnosticResponse or type(response.status) is not int or not 100 <= response.status <= 599
                    or type(response.body) is not bytes or len(response.body) > 8192):
                raise DiagnosticError("diagnostic response refused")
            http_status = response.status
            if not 200 <= http_status < 400:
                received = len(response.body)
            if 200 <= http_status < 300:
                if response.body:
                    raise DiagnosticError("successful diagnostic body refused")
                category["category"] = "unexpected_success_without_body"
            elif 300 <= http_status < 400:
                category["category"] = "redirect_refused"
            elif response.complete is not True:
                category["category"] = "error_body_refused_or_incomplete"
            else:
                category = classify_error_body(response.body, credential)
            if body["mode"] == "production":
                stage = "code_identity"
                market._verify_code(old)
                market.source._verify_code(market.raw_run.LANE_ROOT / "research/target_price_revisions_development/raw_market_diagnostic.py", body["code_sha256"])
            status = "DIAGNOSED"
        except KeyboardInterrupt:
            status, interrupted = "INTERRUPTED", True
        except Exception:
            pass  # No provider exception text/credential/body enters metadata.
        report = {"schema": "tpr-raw-market-diagnostic-report-v1", "diagnostic_id": DIAGNOSTIC_ID,
            "plan_sha256": plan.sha256, "market_plan_sha256": original.sha256, "failed_capture_report_sha256": body["failed_capture_report_sha256"],
            "mode": body["mode"], "status": status, "failure_stage": stage if status != "DIAGNOSED" else None,
            "http_status": http_status, "error": category, "error_response_bytes": received,
            "provider_requests": attempts if body["mode"] == "production" else 0,
            "fixture_transport_calls": attempts if body["mode"] == "offline-fixture" else 0,
            "successful_body_reads": 0, "raw_error_retained": False, "raw_error_identity_retained": False,
            "existing_development_look_spent": 1 if body["mode"] == "production" else 0,
            "additional_development_looks": 0, "outcome_reads": 0, "quantconnect_attempts": 0, "trading": False}
        payload = market.source._canonical(report)
        digest = market.source._digest(payload)
        aggregate_name, terminal_name = DIAGNOSTIC_ID + "." + digest + ".aggregate.json", DIAGNOSTIC_ID + ".terminal.json"
        market.source._publish(fd, aggregate_name, payload)
        market.source._publish(fd, terminal_name, market.source._canonical({"schema": "tpr-raw-market-diagnostic-terminal-v1",
            "diagnostic_id": DIAGNOSTIC_ID, "plan_sha256": plan.sha256, "status": status, "aggregate_sha256": digest,
            "additional_development_looks": 0, "successful_body_reads": 0}))
        if interrupted:
            raise KeyboardInterrupt("diagnostic interrupted; diagnostic remains spent") from None
        return market.CaptureResult(payload, digest, None, root / aggregate_name, root / terminal_name)
    finally:
        os.close(fd)
