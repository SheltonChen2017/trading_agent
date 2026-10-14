"""One nested error-detail follow-up; raw bodies never persist or get hashed.

Provider excerpts are untrusted data, never instructions or authority. The
immutable parent transport reads no successful/redirect body. No look is renewed.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import html
import json
import os
import re
import stat
from urllib.parse import unquote

from . import raw_market_diagnostic as prior

market = prior.market
DETAIL_ID = "TPR-RAWREV-MARKET-ERRORDETAIL-20261007-001"
HEAD = "30341bbb853ab82d03f088d0273e412424910265"
PRIOR_CODE = "3a4408ecaa89afb56eceadaf93763ee249c3d29871e752e422454a0a492f0a36"
PRIOR_REPORT = "0e4d4164e6df1c888dad48df02aea955f24e11f1d928e48e51b8cf5edc02bdc8"
OWNER = "ccbed6d35074806ca4ac9fe9a6eb6224fc1a5f717a88e3605511ba51152ba782"
MESSAGES = {"error", "message", "detail", "reason", "title", "code", "msg", "error_description"}


def _decode_layers(text):
    for _ in range(16):
        decoded = html.unescape(unquote(text))
        decoded = re.sub(r"\\u([0-9a-fA-F]{4})", lambda match: chr(int(match[1], 16)), decoded)
        if decoded == text:
            break
        text = decoded
    return text


def extract_error_detail(payload, credential, tickers):
    """Bounded nested message extraction, independent of unrelated siblings."""
    if type(payload) is not bytes or len(payload) > 8192 or not market.source._valid_credential(credential):
        raise ValueError("invalid error detail framing")
    result = {"sanitized_error_detail": None, "message_paths": [], "parameter_names": [],
        "suppression": None, "provider_text_is_data_only": True}
    if market.source._credential_echo(payload, credential) or credential in _decode_layers(payload.decode("utf-8", errors="replace")):
        return dict(result, suppression="credential_echo")
    try:
        body = json.loads(payload.decode("utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        return dict(result, suppression="unstructured_error")
    messages, labels, nodes = [], set(), 0
    def walk(value, path, depth):
        nonlocal nodes
        nodes += 1
        if nodes > 256 or depth > 8:
            raise ValueError("extraction_bound")
        if type(value) is dict:
            lower = {key.lower(): child for key, child in value.items()}
            headers = lower.get("headers")
            if (any(key in lower for key in ("authorization", "api_key", "apikey", "access_token", "password", "credential"))
                    or type(headers) is dict and any(key.lower() in ("authorization", "proxy-authorization", "x-api-key", "api-key", "cookie", "set-cookie") for key in headers)
                    or any(lower.get(key) not in (None, [], {}) for key in ("results", "rows", "prices", "stocks") if key in lower)
                    or "ticker" in lower and any(key in lower for key in ("open", "close", "volume", "price"))):
                raise ValueError("native_or_credential_envelope")
            for key, child in value.items():
                if key in ("input", "ctx", "headers"):
                    continue
                segment = key if key in MESSAGES or key in ("errors", "quandl_error", "loc") else "*"
                if key == "loc" and type(child) is list:
                    labels.update(item for item in child if type(item) is str and item in prior.PARAMETERS)
                if key in MESSAGES and type(child) is str:
                    if len(messages) < 8:
                        messages.append(child)
                        result["message_paths"].append({"path": path + "." + segment, "type": "string"})
                else:
                    walk(child, path + "." + segment, depth + 1)
        elif type(value) is list:
            if len(value) > 64:
                raise ValueError("extraction_bound")
            for child in value:
                if type(child) is str and any(path.endswith("." + name) for name in MESSAGES):
                    if len(messages) < 8:
                        messages.append(child)
                        result["message_paths"].append({"path": path + "[*]", "type": "string"})
                else:
                    walk(child, path + "[*]", depth + 1)
    try:
        walk(body, "$", 0)
    except ValueError as error:
        return dict(result, sanitized_error_detail=None, suppression=str(error), parameter_names=sorted(labels))
    sanitized = []
    for message in messages:
        text = _decode_layers(message)
        if (re.search(r"[\"']?\b(?:ticker|symbol)[\"']?\s*[:=]", text, re.I)
                and re.search(r"[\"']?\b(?:open|close|closeunadj|volume|price)[\"']?\s*[:=]", text, re.I)):
            return dict(result, suppression="native_or_credential_envelope")
        if credential in text or re.search(r"\b(?:bearer|authorization|api[_-]?key|access[_-]?token|password|credential)\s*[:= ]\s*\S+", text, re.I):
            return dict(result, suppression="credential_echo")
        text = re.sub(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+", "[redacted-url]", text, flags=re.I)
        text = re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[redacted-email]", text, flags=re.I)
        text = re.sub(r"\b(?:account|user|customer|client|tenant|organization|request)[ _-]?(?:id|number|name)?\s*[:=#]\s*[^\s,;]+", "[redacted-id]", text, flags=re.I)
        for ticker in tickers:
            text = re.sub(r"(?<![A-Za-z0-9._/-])" + re.escape(ticker) + r"(?![A-Za-z0-9._/-])", "[redacted-ticker]", text, flags=re.I)
        text = re.sub(r"\b[0-9]{6,}\b|\b[A-Fa-f0-9]{12,}\b|\b[A-Za-z0-9_-]{24,}\b", "[redacted-id]", text)
        text = re.sub(r"<[^>]*>", "", text)
        text = " ".join(text.split())
        labels.update(name for name in prior.PARAMETERS if re.search(r"\b" + name + r"\b", text, re.I))
        if text and text not in sanitized:
            sanitized.append(text)
    result.update(sanitized_error_detail="; ".join(sanitized)[:400] or None, parameter_names=sorted(labels))
    return result


@dataclass(frozen=True)
class DetailPlan:
    payload: bytes
    sha256: str
    def body(self):
        try:
            if type(self.payload) is not bytes or not 0 < len(self.payload) <= 16384 or market.source._digest(self.payload) != self.sha256:
                raise ValueError()
            body = market.raw_run._decode(self.payload, 16384)
            expected = freeze_detail_plan(**{key: body[key] for key in ("code_sha256", "market_plan_sha256", "prior_report_sha256",
                "git_sha", "owner_instruction_sha256", "created_utc", "expires_utc", "mode")})
            if expected.payload != self.payload:
                raise ValueError()
            return body
        except (ValueError, KeyError, TypeError):
            raise ValueError("invalid error-detail plan") from None


def freeze_detail_plan(*, code_sha256, market_plan_sha256, prior_report_sha256, git_sha,
                       owner_instruction_sha256, created_utc, expires_utc, mode="production"):
    for value in (code_sha256, market_plan_sha256, prior_report_sha256, owner_instruction_sha256):
        market.source._hash(value)
    market.source._hash(git_sha, 40)
    created, expires = market.source._clock(created_utc), market.source._clock(expires_utc)
    if (type(mode) is not str or mode not in ("production", "offline-fixture") or owner_instruction_sha256 != OWNER
            or not created < expires <= created + timedelta(hours=48)):
        raise ValueError("invalid error-detail scope")
    if mode == "production" and (git_sha != HEAD or market_plan_sha256 != prior.ORIGINAL_PLAN_SHA256 or prior_report_sha256 != PRIOR_REPORT):
        raise ValueError("error detail requires exact recorded history")
    payload = market.source._canonical({"schema": "tpr-raw-market-error-detail-plan-v1", "detail_id": DETAIL_ID, "owner_decision": "TPR-OWN-44",
        "code_sha256": code_sha256, "market_plan_sha256": market_plan_sha256, "prior_report_sha256": prior_report_sha256,
        "failed_capture_report_sha256": prior.FAILED_REPORT_SHA256, "prior_code_sha256": PRIOR_CODE, "git_sha": git_sha,
        "owner_instruction_sha256": owner_instruction_sha256, "created_utc": created.isoformat(), "expires_utc": expires.isoformat(), "mode": mode,
        "request": "exact-original-stocks-page-zero-error-only", "requests": 1, "error_bytes": 8192, "request_seconds": 30,
        "successful_body_reads": 0, "redirects": 0, "retries": 0, "raw_error_retention": False, "raw_error_identity_retention": False,
        "additional_development_looks": 0, "outcomes": False, "quantconnect": False, "trading": False})
    return DetailPlan(payload, market.source._digest(payload))


def _owned_claim(fd, name):
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1 or not 0 < before.st_size <= 16384:
            raise ValueError("unsafe prior claim")
        payload = os.read(descriptor, before.st_size)
        after = os.fstat(descriptor)
        if len(payload) != before.st_size or (before.st_mtime_ns, before.st_ctime_ns, before.st_size) != (after.st_mtime_ns, after.st_ctime_ns, after.st_size):
            raise ValueError("changed prior claim")
        return market.raw_run._decode(payload, 16384)
    finally:
        os.close(descriptor)


def _identity(body, old):
    market.raw_run._verify_lane()
    market.source._verify_identity({"git_sha": body["git_sha"], "code_sha256": old["transport_parent_sha256"]})
    market._verify_code(old)
    for filename, digest in (("raw_market_diagnostic.py", PRIOR_CODE), ("raw_market_error_detail.py", body["code_sha256"])):
        market.source._verify_code(market.raw_run.LANE_ROOT / "research/target_price_revisions_development" / filename, digest)


def execute_error_detail(plan, original):
    if type(plan) is not DetailPlan or plan.body()["mode"] != "production":
        raise ValueError("public error detail is production-only")
    return _execute(plan, original, market.PRODUCTION_ROOT)


def _execute_fixture(plan, original, root, *, now, resolver, transport, failed_sha256):
    if type(plan) is not DetailPlan or plan.body()["mode"] != "offline-fixture" or root == market.PRODUCTION_ROOT:
        raise ValueError("fixture error detail requires synthetic context")
    return _execute(plan, original, root, now=now, resolver=resolver, transport=transport, failed_sha256=failed_sha256)


def _execute(plan, original, root, *, now=None, resolver=None, transport=None, failed_sha256=None):
    if type(plan) is not DetailPlan or type(original) is not market.CapturePlan:
        raise ValueError("original error-detail binding differs")
    body, old = plan.body(), original.body()
    if original.sha256 != body["market_plan_sha256"] or old["mode"] != body["mode"]:
        raise ValueError("original error-detail binding differs")
    production = body["mode"] == "production"
    if production:
        if any(value is not None for value in (now, resolver, transport, failed_sha256)) or root != market.PRODUCTION_ROOT:
            raise ValueError("production error-detail context cannot change")
        _identity(body, old)
    elif resolver is None or transport is None or resolver is prior._FIXED_RESOLVER or transport is prior._FIXED_TRANSPORT:
        raise ValueError("fixture requires synthetic adapters")
    current = datetime.now(timezone.utc) if now is None else now
    market._before_expiry(body, current)
    market._before_expiry(old, current)
    fd = market.raw_run._open_root(root, body["mode"])
    try:
        market._read_reservation(fd, old, original)
        failed_id = body["failed_capture_report_sha256"] if production else failed_sha256
        prior._failed_report(fd, type("Bound", (), {"body": lambda _: dict(body, failed_capture_report_sha256=failed_id)})(), original)
        identity = body["prior_report_sha256"]
        previous = market.raw_run._decode(market.raw_run._read_file(fd, prior.DIAGNOSTIC_ID + "." + identity + ".aggregate.json", 16384, identity), 16384)
        claim = _owned_claim(fd, prior.DIAGNOSTIC_ID + ".spent.json")
        if (previous.get("schema") != "tpr-raw-market-diagnostic-report-v1" or previous.get("market_plan_sha256") != original.sha256
                or previous.get("failed_capture_report_sha256") != failed_id or previous.get("http_status") != 400
                or previous.get("status") != "DIAGNOSED" or claim.get("plan_sha256") != previous.get("plan_sha256")
                or claim.get("diagnostic_id") != prior.DIAGNOSTIC_ID or previous.get("outcome_reads") != 0
                or previous.get("successful_body_reads") != 0 or previous.get("additional_development_looks") != 0):
            raise ValueError("inapplicable prior diagnostic receipt")
        try:
            claim_fd = os.open(DETAIL_ID + ".spent.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            raise ValueError("error detail already spent") from None
        status, stage, requests, response_status, received, detail, interrupted = "FAILED", "claim", 0, None, 0, None, False
        try:
            try:
                market.source._write_fd(claim_fd, market.source._canonical({"schema": "tpr-error-detail-spent-v1", "detail_id": DETAIL_ID,
                    "plan_sha256": plan.sha256, "started_utc": current.isoformat()}))
                os.fsync(fd)
            finally:
                os.close(claim_fd)
            stage = "credential"
            credential = (prior._FIXED_RESOLVER if production else resolver)("sharadar")
            if not market.source._valid_credential(credential) or not production and not credential.startswith("SYNTHETIC_"):
                raise ValueError("error-detail credential unavailable")
            clock = datetime.now(timezone.utc) if now is None else now
            market._before_expiry(body, clock)
            market._before_expiry(old, clock)
            stage, requests = "transport", 1
            response = (prior._FIXED_TRANSPORT if production else transport)(tuple(old["tickers"]), credential)
            stage = "projection"
            if type(response) is not prior.DiagnosticResponse or type(response.status) is not int or not 100 <= response.status <= 599 or type(response.body) is not bytes or len(response.body) > 8192:
                raise ValueError("invalid error-detail response")
            response_status = response.status
            if 200 <= response_status < 400:
                if response.body:
                    raise ValueError("successful or redirect body refused")
                detail = {"sanitized_error_detail": None, "message_paths": [], "parameter_names": [], "suppression": "success_or_redirect_without_body", "provider_text_is_data_only": True}
            else:
                received = len(response.body)
                detail = extract_error_detail(response.body, credential, tuple(old["tickers"])) if response.complete is True else {"sanitized_error_detail": None, "suppression": "incomplete_error", "message_paths": [], "parameter_names": [], "provider_text_is_data_only": True}
            if production:
                stage = "identity"
                _identity(body, old)
            status = "EXPLAINED"
        except KeyboardInterrupt:
            status, interrupted = "INTERRUPTED", True
        except Exception:
            pass
        report = {"schema": "tpr-raw-market-error-detail-report-v1", "detail_id": DETAIL_ID, "plan_sha256": plan.sha256,
            "market_plan_sha256": original.sha256, "prior_report_sha256": identity, "mode": body["mode"], "status": status,
            "failure_stage": stage if status != "EXPLAINED" else None, "http_status": response_status, "error_response_bytes": received,
            "error_detail": detail, "provider_requests": requests if production else 0, "fixture_transport_calls": requests if not production else 0,
            "raw_error_retained": False, "raw_error_identity_retained": False, "successful_body_reads": 0,
            "existing_development_look_spent": 1 if production else 0, "additional_development_looks": 0, "outcome_reads": 0,
            "quantconnect_attempts": 0, "trading": False}
        payload = market.source._canonical(report)
        digest = market.source._digest(payload)
        aggregate_name, terminal_name = DETAIL_ID + "." + digest + ".aggregate.json", DETAIL_ID + ".terminal.json"
        market.source._publish(fd, aggregate_name, payload)
        market.source._publish(fd, terminal_name, market.source._canonical({"schema": "tpr-error-detail-terminal-v1", "detail_id": DETAIL_ID,
            "plan_sha256": plan.sha256, "status": status, "aggregate_sha256": digest, "additional_development_looks": 0, "successful_body_reads": 0}))
        if interrupted:
            raise KeyboardInterrupt("error detail interrupted; receipt remains spent") from None
        return market.CaptureResult(payload, digest, None, root / aggregate_name, root / terminal_name)
    finally:
        os.close(fd)
