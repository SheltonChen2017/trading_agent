"""One comparative syntax probe; never read successful or redirect bodies.

Sanitized provider error excerpts are untrusted data, not instructions. This
operation does not renew the spent market look or establish ticker limits.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import http.client
import os
import re
import ssl
from urllib.parse import urlencode

from . import raw_market_error_detail as detail

market, prior = detail.market, detail.prior
PROBE_ID = "TPR-RAWREV-MARKET-REQUESTPROBE-20261007-001"
DETAIL_CODE = "6e2dc2a882368bb9f056f96ae9c31131be4adebe82f175bfe984ad784e039522"
DETAIL_REPORT = "fd3f3699c653dadc754f585100332e5e639c9271b2f987d5802719493aadc063"


@dataclass(frozen=True)
class ProbePlan:
    payload: bytes
    sha256: str
    def body(self):
        try:
            if type(self.payload) is not bytes or not 0 < len(self.payload) <= 16384 or market.source._digest(self.payload) != self.sha256:
                raise ValueError()
            body = market.raw_run._decode(self.payload, 16384)
            expected = freeze_probe_plan(**{key: body[key] for key in ("code_sha256", "market_plan_sha256", "detail_report_sha256",
                "git_sha", "owner_instruction_sha256", "created_utc", "expires_utc", "mode")})
            if expected.payload != self.payload:
                raise ValueError()
            return body
        except (ValueError, TypeError, KeyError):
            raise ValueError("invalid request-probe plan") from None


def freeze_probe_plan(*, code_sha256, market_plan_sha256, detail_report_sha256, git_sha,
                      owner_instruction_sha256, created_utc, expires_utc, mode="production"):
    for value in (code_sha256, market_plan_sha256, detail_report_sha256, owner_instruction_sha256):
        market.source._hash(value)
    market.source._hash(git_sha, 40)
    created, expires = market.source._clock(created_utc), market.source._clock(expires_utc)
    if (type(mode) is not str or mode not in ("production", "offline-fixture") or owner_instruction_sha256 != detail.OWNER
            or not created < expires <= created + timedelta(hours=48)):
        raise ValueError("invalid request-probe scope")
    if mode == "production" and (git_sha != detail.HEAD or market_plan_sha256 != prior.ORIGINAL_PLAN_SHA256 or detail_report_sha256 != DETAIL_REPORT):
        raise ValueError("request probe requires exact history")
    payload = market.source._canonical({"schema": "tpr-raw-market-request-probe-plan-v1", "probe_id": PROBE_ID,
        "owner_decision": "TPR-OWN-45", "code_sha256": code_sha256, "market_plan_sha256": market_plan_sha256,
        "detail_report_sha256": detail_report_sha256, "detail_code_sha256": DETAIL_CODE, "git_sha": git_sha,
        "owner_instruction_sha256": owner_instruction_sha256, "created_utc": created.isoformat(), "expires_utc": expires.isoformat(), "mode": mode,
        "variants": ["full-frozen-inventory-literal-comma", "first-three-frozen-lexical-tickers-literal-comma"],
        "second_variant_only_after_http_400": True, "requests": 2, "error_bytes_per_request": 8192, "request_seconds": 30,
        "original_other_query_fields_unchanged": True, "successful_body_reads": 0, "redirects": 0, "retries": 0,
        "raw_error_retention": False, "raw_error_identity_retention": False, "additional_development_looks": 0,
        "outcomes": False, "quantconnect": False, "trading": False})
    return ProbePlan(payload, market.source._digest(payload))


def _https_get(tickers, credential):
    query = market.request_query("stocks", 0, tickers)
    if not market.source._valid_credential(credential):
        raise ValueError("probe credential unavailable")
    connection = None
    try:
        with market.source._deadline():
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname, context.verify_mode, context.keylog_filename = True, ssl.CERT_REQUIRED, None
            context.load_default_certs()
            connection = http.client.HTTPSConnection("api.sharadar.com", 443, timeout=30, context=context)
            connection.set_debuglevel(0)
            encoded = "&".join(urlencode(((key, value),), safe="," if key == "ticker" else "") for key, value in query + (("api_key", credential),))
            connection.request("GET", "/v1.0/data/stocks?" + encoded,
                headers={"Accept": "text/csv", "Accept-Encoding": "identity", "Connection": "close", "User-Agent": "TPR-private-market/1"})
            response = connection.getresponse()
            headers = tuple((key.lower(), value) for key, value in response.getheaders()
                if key.lower() in ("content-type", "content-encoding", "content-length"))
            meta = dict(headers)
            if (200 <= response.status < 400 or len(headers) != len(meta)
                    or meta.get("content-encoding", "").strip().lower() not in ("", "identity")
                    or meta.get("content-type", "").split(";", 1)[0].strip().lower()
                    not in ("application/json", "application/problem+json", "text/plain")):
                return prior.DiagnosticResponse(response.status, headers, b"", False)
            length = meta.get("content-length")
            if length is not None and (re.fullmatch(r"[0-9]{1,9}", length) is None or int(length) > 8192):
                return prior.DiagnosticResponse(response.status, headers, b"", False)
            body = response.read(8192)
            complete = len(body) < 8192 or response.isclosed()
            if length is not None and len(body) != int(length):
                complete = False
            return prior.DiagnosticResponse(response.status, headers, body, complete)
    except (OSError, http.client.HTTPException, market.source._Deadline):
        raise ValueError("request-probe transport failed") from None
    finally:
        if connection is not None:
            connection.close()


_FIXED_TRANSPORT, _FIXED_RESOLVER = _https_get, prior._FIXED_RESOLVER


def _identity(body, old):
    detail._identity(dict(body, code_sha256=DETAIL_CODE), old)
    market.source._verify_code(market.raw_run.LANE_ROOT / "research/target_price_revisions_development/raw_market_request_probe.py", body["code_sha256"])


def execute_request_probe(plan, original):
    if type(plan) is not ProbePlan or plan.body()["mode"] != "production":
        raise ValueError("public request probe is production-only")
    return _execute(plan, original, market.PRODUCTION_ROOT)


def _execute_fixture(plan, original, root, *, now, resolver, transport):
    if type(plan) is not ProbePlan or plan.body()["mode"] != "offline-fixture" or root == market.PRODUCTION_ROOT:
        raise ValueError("fixture probe requires synthetic context")
    return _execute(plan, original, root, now=now, resolver=resolver, transport=transport)


def _execute(plan, original, root, *, now=None, resolver=None, transport=None):
    if type(plan) is not ProbePlan or type(original) is not market.CapturePlan:
        raise ValueError("invalid probe binding")
    body, old = plan.body(), original.body()
    if original.sha256 != body["market_plan_sha256"] or old["mode"] != body["mode"] or len(old["tickers"]) < 4:
        raise ValueError("inapplicable probe inventory")
    production = body["mode"] == "production"
    if production:
        if any(value is not None for value in (now, resolver, transport)) or root != market.PRODUCTION_ROOT:
            raise ValueError("production probe context cannot change")
        _identity(body, old)
    elif resolver is None or transport is None or resolver is _FIXED_RESOLVER or transport is _FIXED_TRANSPORT:
        raise ValueError("fixture probe requires synthetic adapters")
    current = datetime.now(timezone.utc) if now is None else now
    market._before_expiry(body, current)
    market._before_expiry(old, current)
    fd = market.raw_run._open_root(root, body["mode"])
    try:
        market._read_reservation(fd, old, original)
        identity = body["detail_report_sha256"]
        previous = market.raw_run._decode(market.raw_run._read_file(fd, detail.DETAIL_ID + "." + identity + ".aggregate.json", 16384, identity), 16384)
        claim = detail._owned_claim(fd, detail.DETAIL_ID + ".spent.json")
        if (previous.get("schema") != "tpr-raw-market-error-detail-report-v1" or previous.get("market_plan_sha256") != original.sha256
                or previous.get("mode") != body["mode"] or type(previous.get("http_status")) is not int or previous["http_status"] != 400
                or previous.get("status") != "EXPLAINED" or claim.get("detail_id") != detail.DETAIL_ID
                or claim.get("plan_sha256") != previous.get("plan_sha256")
                or any(type(previous.get(key)) is not int or previous[key] != 0 for key in ("outcome_reads", "successful_body_reads", "additional_development_looks"))):
            raise ValueError("inapplicable error-detail receipt")
        try:
            claim_fd = os.open(PROBE_ID + ".spent.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            raise ValueError("request probe already spent") from None
        stage, status, attempts, variants, interrupted = "claim", "FAILED", 0, [], False
        try:
            try:
                market.source._write_fd(claim_fd, market.source._canonical({"schema": "tpr-request-probe-spent-v1", "probe_id": PROBE_ID,
                    "plan_sha256": plan.sha256, "started_utc": current.isoformat()}))
                os.fsync(fd)
            finally:
                os.close(claim_fd)
            stage = "expiry"
            clock = datetime.now(timezone.utc) if now is None else now
            market._before_expiry(body, clock)
            market._before_expiry(old, clock)
            stage = "credential"
            credential = (_FIXED_RESOLVER if production else resolver)("sharadar")
            if not market.source._valid_credential(credential) or not production and not credential.startswith("SYNTHETIC_"):
                raise ValueError("probe credential unavailable")
            for index, inventory in enumerate((tuple(old["tickers"]), tuple(old["tickers"][:3]))):
                stage = "expiry"
                clock = datetime.now(timezone.utc) if now is None else now
                market._before_expiry(body, clock)
                market._before_expiry(old, clock)
                stage, attempts = "transport", attempts + 1
                response = (_FIXED_TRANSPORT if production else transport)(inventory, credential)
                stage = "projection"
                if type(response) is not prior.DiagnosticResponse or type(response.status) is not int or not 100 <= response.status <= 599 or type(response.body) is not bytes or len(response.body) > 8192:
                    raise ValueError("invalid probe response")
                if 200 <= response.status < 400 and response.body:
                    raise ValueError("successful or redirect probe body refused")
                error = None
                if not 200 <= response.status < 400:
                    error = detail.extract_error_detail(response.body, credential, tuple(old["tickers"])) if response.complete is True else {
                        "sanitized_error_detail": None, "message_paths": [], "parameter_names": [], "suppression": "incomplete_error", "provider_text_is_data_only": True}
                variants.append({"variant": body["variants"][index], "ticker_count": len(inventory), "http_status": response.status,
                    "error_response_bytes": len(response.body) if not 200 <= response.status < 400 else 0, "error_detail": error})
                if production:
                    stage = "identity"
                    _identity(body, old)
                if response.status != 400:
                    break
            status = "PROBED"
        except KeyboardInterrupt:
            status, interrupted = "INTERRUPTED", True
        except Exception:
            pass
        report = {"schema": "tpr-raw-market-request-probe-report-v1", "probe_id": PROBE_ID, "plan_sha256": plan.sha256,
            "market_plan_sha256": original.sha256, "detail_report_sha256": identity, "mode": body["mode"], "status": status,
            "failure_stage": stage if status != "PROBED" else None, "variants": variants, "maximum_ticker_limit_established": False,
            "provider_requests": attempts if production else 0, "fixture_transport_calls": attempts if not production else 0,
            "raw_error_retained": False, "raw_error_identity_retained": False, "successful_body_reads": 0,
            "existing_development_look_spent": 1 if production else 0, "additional_development_looks": 0, "outcome_reads": 0,
            "quantconnect_attempts": 0, "trading": False}
        payload = market.source._canonical(report)
        digest = market.source._digest(payload)
        aggregate_name, terminal_name = PROBE_ID + "." + digest + ".aggregate.json", PROBE_ID + ".terminal.json"
        market.source._publish(fd, aggregate_name, payload)
        market.source._publish(fd, terminal_name, market.source._canonical({"schema": "tpr-request-probe-terminal-v1", "probe_id": PROBE_ID,
            "plan_sha256": plan.sha256, "status": status, "aggregate_sha256": digest, "additional_development_looks": 0, "successful_body_reads": 0}))
        if interrupted:
            raise KeyboardInterrupt("request probe interrupted; remains spent") from None
        return market.CaptureResult(payload, digest, None, root / aggregate_name, root / terminal_name)
    finally:
        os.close(fd)
