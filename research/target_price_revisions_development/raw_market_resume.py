"""One append-only continuation of the existing failed empirical look.

No imports perform I/O. An authenticated successful body-free request probe
selects only wire representation/batching, never names, economics or dates.
The original spent marker is retained and checked, not refunded or reset.
Custody is owner-local/cooperative, not an external anti-rollback guarantee.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import http.client
import os
import re
import ssl
from urllib.parse import urlencode

from . import raw_market_error_detail as detail

market, source, raw_run = detail.market, detail.market.source, detail.market.raw_run
RESUME_ID = "TPR-RAWREV-MARKET-RESUME-20261007-001"
PROBE_ID = "TPR-RAWREV-MARKET-REQUESTPROBE-20261007-001"
DETAIL_SHA = "fd3f3699c653dadc754f585100332e5e639c9271b2f987d5802719493aadc063"
DETAIL_CODE = "6e2dc2a882368bb9f056f96ae9c31131be4adebe82f175bfe984ad784e039522"
PROBE_SHA = "ad8382777e8821a2b094ccc48dfa0f17e33e18046bbc65d8340b130248e3133d"
PROBE_CODE = "3b81176c47fd8ce5c6dd4d6c00dac5c23a8396b6d8a08c7b501fc32ab81752fb"
LIMITS = {"requests": 30, "batches": 15, "pages_per_batch_dataset": 1, "rows_per_page": 10000,
    "bytes_per_page": 4194304, "total_bytes": 33554432, "request_seconds": 30, "redirects": 0, "retries": 0}
VARIANTS = ("full-frozen-inventory-literal-comma", "first-three-frozen-lexical-tickers-literal-comma")
_FIXED_RESOLVER = source._FIXED_RESOLVER


@dataclass(frozen=True)
class ResumePlan:
    payload: bytes
    sha256: str

    def body(self):
        try:
            if type(self.payload) is not bytes or not 0 < len(self.payload) <= 65536 or source._digest(self.payload) != self.sha256:
                raise ValueError()
            body = raw_run._decode(self.payload, 65536)
            original = _original(body)
            expected = freeze_resume_plan(original, **{key: body[key] for key in (
                "probe_report_sha256", "probe_code_sha256", "request_mode", "code_sha256", "git_sha",
                "owner_instruction_sha256", "created_utc", "expires_utc", "mode", "failed_capture_report_sha256", "detail_report_sha256")})
            if expected.payload != self.payload:
                raise ValueError()
            return body
        except (TypeError, ValueError, KeyError, RecursionError):
            raise ValueError("invalid market-resume plan") from None


def _original(body):
    payload = source._canonical(body["original_plan"])
    original = market.CapturePlan(payload, body["original_plan_sha256"])
    original.body()
    return original


def freeze_resume_plan(original, *, probe_report_sha256, probe_code_sha256, request_mode, code_sha256,
                       git_sha, owner_instruction_sha256, created_utc, expires_utc, mode="production",
                       failed_capture_report_sha256=detail.prior.FAILED_REPORT_SHA256, detail_report_sha256=DETAIL_SHA):
    if type(original) is not market.CapturePlan:
        raise ValueError("original market plan required")
    old = original.body()
    for value in (probe_report_sha256, probe_code_sha256, code_sha256, owner_instruction_sha256,
                  failed_capture_report_sha256, detail_report_sha256):
        source._hash(value)
    source._hash(git_sha, 40)
    created, expires = source._clock(created_utc), source._clock(expires_utc)
    if (type(mode) is not str or mode not in ("production", "offline-fixture") or old["mode"] != mode
            or type(request_mode) is not str or request_mode not in ("all", "three") or len(old["tickers"]) != 43
            or owner_instruction_sha256 != detail.OWNER or not created < expires <= created + timedelta(hours=48)
            or not source._clock(old["created_utc"]) <= created < source._clock(old["expires_utc"])
            or expires > source._clock(old["expires_utc"])):
        raise ValueError("invalid prospective resume scope")
    if mode == "production" and (git_sha != detail.HEAD or original.sha256 != detail.prior.ORIGINAL_PLAN_SHA256
            or failed_capture_report_sha256 != detail.prior.FAILED_REPORT_SHA256 or detail_report_sha256 != DETAIL_SHA
            or probe_report_sha256 != PROBE_SHA or probe_code_sha256 != PROBE_CODE or request_mode != "three"):
        raise ValueError("resume requires exact recorded history")
    body = {"schema": "tpr-raw-market-resume-plan-v1", "resume_id": RESUME_ID, "candidate_id": market.CANDIDATE_ID,
        "owner_decision": "TPR-OWN-46", "owner_instruction_sha256": owner_instruction_sha256, "mode": mode,
        "original_plan": old, "original_plan_sha256": original.sha256,
        "failed_capture_report_sha256": failed_capture_report_sha256, "detail_report_sha256": detail_report_sha256,
        "detail_code_sha256": DETAIL_CODE, "probe_report_sha256": probe_report_sha256, "probe_code_sha256": probe_code_sha256,
        "code_sha256": code_sha256, "git_sha": git_sha, "request_mode": request_mode,
        "created_utc": created.isoformat(), "expires_utc": expires.isoformat(), "limits": dict(LIMITS),
        "lane_root": str(raw_run.LANE_ROOT), "lane_branch": raw_run.LANE_BRANCH, "private_root": str(market.PRODUCTION_ROOT),
        "original_spent_file": market.CANDIDATE_ID + ".spent.json", "resume_spent_file": RESUME_ID + ".spent.json",
        "simulation_spent_file": market.CANDIDATE_ID + ".simulation.spent.json",
        "ticker_wire_encoding": "literal-comma-ticker-value-only-other-query-pairs-unchanged",
        "entire_original_inventory_required": True, "original_look_renewed": False, "additional_development_looks": 0,
        "canonical_admission": False, "rights_verified": False, "quantconnect": False, "trading": False}
    payload = source._canonical(body)
    return ResumePlan(payload, source._digest(payload))


def public_plan_summary(plan):
    body = plan.body()
    old = body["original_plan"]
    summary = {key: value for key, value in body.items() if key not in ("original_plan", "private_root")}
    summary.update(schema="tpr-raw-market-resume-plan-summary-v1", resume_plan_sha256=plan.sha256,
        ticker_count=len(old["tickers"]), native_ticker_list_published=False, code_hashes=old["code_hashes"],
        structure_sha256=old["structure_sha256"], waiver_sha256=old["waiver_sha256"], candidate_policy_sha256=old["candidate_policy_sha256"],
        price_dates=old["price_dates"], action_dates=old["action_dates"])
    return source._canonical(summary)


def _batches(body):
    tickers = tuple(body["original_plan"]["tickers"])
    return (tickers,) if body["request_mode"] == "all" else tuple(tickers[i:i + 3] for i in range(0, len(tickers), 3))


def request_path(dataset, tickers, credential):
    query = market.request_query(dataset, 0, tickers) + (("api_key", credential),)
    if not source._valid_credential(credential):
        raise ValueError("resume credential unavailable")
    return "/v1.0/data/" + dataset + "?" + "&".join(
        urlencode(((key, value),), safe="," if key == "ticker" else "") for key, value in query)


def _https_get(dataset, tickers, credential, budget):
    if type(budget) is not int or not 0 < budget <= LIMITS["bytes_per_page"]:
        raise ValueError("invalid resume response budget")
    path, connection = request_path(dataset, tickers, credential), None
    try:
        with source._deadline():
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname, context.verify_mode, context.keylog_filename = True, ssl.CERT_REQUIRED, None
            context.load_default_certs()
            connection = http.client.HTTPSConnection("api.sharadar.com", 443, timeout=30, context=context)
            connection.set_debuglevel(0)
            connection.request("GET", path, headers={"Accept": "text/csv", "Accept-Encoding": "identity",
                "Connection": "close", "User-Agent": "TPR-private-market/1"})
            response = connection.getresponse()
            headers = tuple((key.lower(), value) for key, value in response.getheaders()
                if key.lower() in ("content-type", "content-encoding", "content-length"))
            meta = dict(headers)
            if (response.status != 200 or len(headers) != len(meta) or meta.get("content-encoding", "").strip().lower() not in ("", "identity")
                    or meta.get("content-type", "").split(";", 1)[0].strip().lower()
                    not in ("text/csv", "text/plain", "application/csv", "application/octet-stream")):
                return source.CaptureResponse(response.status, headers, b"", False)
            length = meta.get("content-length")
            if length is not None and (re.fullmatch(r"[0-9]{1,9}", length) is None or int(length) > budget):
                return source.CaptureResponse(response.status, headers, b"", False)
            payload = response.read(budget)
            return source.CaptureResponse(response.status, headers, payload, len(payload) < budget or response.isclosed())
    except (OSError, http.client.HTTPException, source._Deadline):
        raise ValueError("resume transport failed") from None
    finally:
        if connection is not None:
            connection.close()


_FIXED_TRANSPORT = _https_get


def _identity(body):
    old = body["original_plan"]
    detail._identity(dict(body, code_sha256=DETAIL_CODE), old)
    for name, identity in (("raw_market_resume.py", body["code_sha256"]), ("raw_market_request_probe.py", body["probe_code_sha256"])):
        source._verify_code(raw_run.LANE_ROOT / "research/target_price_revisions_development" / name, identity)


def _read(fd, name, identity, limit=65536):
    return raw_run._decode(raw_run._read_file(fd, name, limit, identity), limit)


def _zero(body, fields):
    if any(type(body.get(key)) is not int or body[key] != 0 for key in fields):
        raise ValueError("history expanded empirical authority")


def _history(fd, plan):
    body, original = plan.body(), _original(plan.body())
    old = original.body()
    market._read_reservation(fd, old, original)
    detail.prior._failed_report(fd, plan, original)
    detail_id = body["detail_report_sha256"]
    previous = _read(fd, detail.DETAIL_ID + "." + detail_id + ".aggregate.json", detail_id)
    previous_claim = detail._owned_claim(fd, detail.DETAIL_ID + ".spent.json")
    if (previous.get("schema") != "tpr-raw-market-error-detail-report-v1" or previous.get("mode") != body["mode"]
            or previous.get("market_plan_sha256") != original.sha256 or previous.get("status") != "EXPLAINED"
            or type(previous.get("http_status")) is not int or previous["http_status"] != 400
            or previous_claim.get("detail_id") != detail.DETAIL_ID or previous_claim.get("plan_sha256") != previous.get("plan_sha256")):
        raise ValueError("resume error-detail history mismatch")
    _zero(previous, ("additional_development_looks", "outcome_reads", "successful_body_reads", "quantconnect_attempts"))
    identity = body["probe_report_sha256"]
    report = _read(fd, PROBE_ID + "." + identity + ".aggregate.json", identity)
    claim = detail._owned_claim(fd, PROBE_ID + ".spent.json")
    keys = {"schema", "probe_id", "plan_sha256", "market_plan_sha256", "detail_report_sha256", "mode", "status", "failure_stage",
        "variants", "maximum_ticker_limit_established", "provider_requests", "fixture_transport_calls", "raw_error_retained",
        "raw_error_identity_retained", "successful_body_reads", "existing_development_look_spent", "additional_development_looks",
        "outcome_reads", "quantconnect_attempts", "trading"}
    if (set(report) != keys or report["schema"] != "tpr-raw-market-request-probe-report-v1" or report["probe_id"] != PROBE_ID
            or report["market_plan_sha256"] != original.sha256 or report["detail_report_sha256"] != detail_id
            or report["mode"] != body["mode"] or report["status"] != "PROBED" or report["failure_stage"] is not None
            or claim.get("probe_id") != PROBE_ID or claim.get("plan_sha256") != report["plan_sha256"]
            or any(report[key] is not False for key in ("maximum_ticker_limit_established", "raw_error_retained", "raw_error_identity_retained", "trading"))):
        raise ValueError("resume probe history mismatch")
    _zero(report, ("additional_development_looks", "outcome_reads", "successful_body_reads", "quantconnect_attempts"))
    variants = report["variants"]
    if type(variants) is not list or len(variants) not in (1, 2):
        raise ValueError("no successful request probe")
    for index, variant in enumerate(variants):
        if (type(variant) is not dict or set(variant) != {"variant", "ticker_count", "http_status", "error_response_bytes", "error_detail"}
                or variant["variant"] != VARIANTS[index] or type(variant["ticker_count"]) is not int
                or variant["ticker_count"] != (43 if index == 0 else 3) or type(variant["http_status"]) is not int
                or type(variant["error_response_bytes"]) is not int or not 0 <= variant["error_response_bytes"] <= 8192):
            raise ValueError("invalid probe variant history")
    successful = variants[-1]
    observed_mode = "all" if len(variants) == 1 else "three"
    if (successful["http_status"] != 200 or successful["error_response_bytes"] != 0 or successful["error_detail"] is not None
            or len(variants) == 2 and variants[0]["http_status"] != 400 or observed_mode != body["request_mode"]):
        raise ValueError("resume mode lacks successful probe")
    production = body["mode"] == "production"
    for key, expected in (("provider_requests", len(variants) if production else 0), ("fixture_transport_calls", 0 if production else len(variants)),
                          ("existing_development_look_spent", 1 if production else 0)):
        if type(report[key]) is not int or report[key] != expected:
            raise ValueError("probe counter mismatch")
    market._prepare_source(fd, old)


def _claim(fd, name, payload):
    try:
        descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    except FileExistsError:
        raise ValueError("resume or simulation already spent") from None
    except OSError:
        raise ValueError("resume reservation unavailable") from None
    try:
        source._write_fd(descriptor, source._canonical(payload))
        os.fsync(fd)
    except KeyboardInterrupt:
        return market._ClaimFailure(True)
    except OSError:
        return market._ClaimFailure(False)
    finally:
        os.close(descriptor)
    return None


def _claim_body(plan, current, **extra):
    body = plan.body()
    return {"schema": "tpr-raw-resume-reservation-v1", "resume_id": RESUME_ID, "candidate_id": market.CANDIDATE_ID,
        "resume_plan_sha256": plan.sha256, "original_plan_sha256": body["original_plan_sha256"],
        "code_sha256": body["code_sha256"], "code_hashes": body["original_plan"]["code_hashes"],
        "probe_report_sha256": body["probe_report_sha256"], "started_utc": current.isoformat(), "mode": body["mode"],
        "additional_development_looks": 0, **extra}


def _check_resume_claim(fd, plan):
    claim = detail._owned_claim(fd, RESUME_ID + ".spent.json")
    started = source._clock(claim["started_utc"])
    market._before_expiry(plan.body(), started)
    if source._canonical(claim) != source._canonical(_claim_body(plan, started)):
        raise ValueError("resume reservation does not bind plan")


def _context(plan, root, now, *, resolver=None, transport=None, capture=False):
    if type(plan) is not ResumePlan:
        raise ValueError("resume plan required")
    body = plan.body()
    if body["mode"] == "production":
        if root != market.PRODUCTION_ROOT or any(value is not None for value in (now, resolver, transport)):
            raise ValueError("production resume context cannot change")
        _identity(body)
    elif (root == market.PRODUCTION_ROOT or now is None or capture and (resolver is None or transport is None
            or resolver is _FIXED_RESOLVER or transport in (_FIXED_TRANSPORT, _https_get))):
        raise ValueError("fixture resume requires synthetic context")
    current = datetime.now(timezone.utc) if now is None else now
    market._before_expiry(body, current)
    market._before_expiry(body["original_plan"], current)
    return body, current


def _check_clock(body, now):
    current = datetime.now(timezone.utc) if now is None else now
    market._before_expiry(body, current)
    market._before_expiry(body["original_plan"], current)


def execute_resume_capture(plan):
    if type(plan) is not ResumePlan or plan.body()["mode"] != "production":
        raise ValueError("public resume capture is production-only")
    return _capture(plan, market.PRODUCTION_ROOT)


def _execute_fixture_capture(plan, root, *, now, resolver, transport):
    if type(plan) is not ResumePlan or plan.body()["mode"] != "offline-fixture":
        raise ValueError("fixture resume requires offline-fixture mode")
    return _capture(plan, root, now=now, resolver=resolver, transport=transport)


def _capture(plan, root, *, now=None, resolver=None, transport=None):
    body, current = _context(plan, root, now, resolver=resolver, transport=transport, capture=True)
    old, production = body["original_plan"], body["mode"] == "production"
    fd = raw_run._open_root(root, body["mode"])
    try:
        _history(fd, plan)
        claim_failure = _claim(fd, RESUME_ID + ".spent.json", _claim_body(plan, current))
        rows, pages, counts, duplicates = ({key: [] for key in market.FIELDS}, {key: [] for key in market.FIELDS},
            {key: 0 for key in market.FIELDS}, {key: 0 for key in market.FIELDS})
        status, stage, failure, interrupted, attempts, total_bytes, http_status = "FAILED", "reservation", None, False, 0, 0, None
        projection_id, projection_path = None, None
        try:
            if claim_failure:
                if claim_failure.interrupted: raise KeyboardInterrupt
                raise claim_failure
            _check_clock(body, now)
            stage = "credential"
            credential = (_FIXED_RESOLVER if production else resolver)("sharadar")
            if not source._valid_credential(credential) or not production and not credential.startswith("SYNTHETIC_"):
                raise ValueError("resume credential unavailable")
            for dataset in market.FIELDS:
                seen = {}
                for index, batch in enumerate(_batches(body)):
                    stage = "expiry"
                    _check_clock(body, now)
                    budget = min(LIMITS["bytes_per_page"], LIMITS["total_bytes"] - total_bytes)
                    if budget <= 0 or attempts >= LIMITS["requests"]: raise ValueError("resume budget exhausted")
                    stage, attempts = "transport", attempts + 1
                    response = (_FIXED_TRANSPORT if production else transport)(dataset, batch, credential, budget)
                    http_status = response.status if type(response) is source.CaptureResponse and type(response.status) is int else None
                    stage = "response"
                    payload = source._validate_response(response, credential, budget)
                    total_bytes += len(payload)
                    name = RESUME_ID + "." + dataset + "." + str(index).zfill(3) + ".csv"
                    stage = "publication"
                    source._publish(fd, name, payload)
                    stage = "csv_schema"
                    parsed = market.parse_source_csv(payload, dataset, batch)
                    if len(parsed) == LIMITS["rows_per_page"]: raise ValueError("resume page may be truncated")
                    counts[dataset] += len(parsed)
                    for row in parsed:
                        key = (row["ticker"], row["date"]) if dataset == "stocks" else (row["ticker"], row["date"], row["action"], row["contraticker"])
                        if key in seen:
                            if seen[key] != row: raise ValueError("conflicting resumed native row")
                            duplicates[dataset] += 1
                        else:
                            seen[key] = row
                            rows[dataset].append(row)
                    if len(rows[dataset]) > 100000: raise ValueError("resume row bound")
                    pages[dataset].append({"file": name, "sha256": source._digest(payload), "bytes": len(payload), "source_rows": len(parsed)})
            if production: _identity(body)
            projection = source._canonical({"schema": "tpr-raw-market-resume-projection-v1", "resume_id": RESUME_ID,
                "resume_plan_sha256": plan.sha256, "original_plan_sha256": body["original_plan_sha256"], "mode": body["mode"],
                "structure_sha256": old["structure_sha256"], "waiver_sha256": old["waiver_sha256"], "code_hashes": old["code_hashes"],
                "resume_code_sha256": body["code_sha256"], "capture_utc": (datetime.now(timezone.utc) if now is None else now).isoformat(),
                "prices": rows["stocks"], "actions": rows["actions"], "pages": pages, "native_source_rows": counts,
                "exact_duplicate_rows": duplicates, "transactional_snapshot": False, "point_in_time_data": False, "canonical_admission": False})
            if len(projection) > LIMITS["total_bytes"]: raise ValueError("resume projection size bound")
            projection_id = source._digest(projection)
            name = RESUME_ID + "." + projection_id + ".projection.json"
            source._publish(fd, name, projection)
            projection_path, status = root / name, "CAPTURED"
        except KeyboardInterrupt:
            status, failure, interrupted = "INTERRUPTED", "resume_interrupted", True
        except Exception:
            failure = "resume_capture_failed"
        report = {"schema": "tpr-raw-market-resume-capture-report-v1", "resume_id": RESUME_ID, "resume_plan_sha256": plan.sha256,
            "original_plan_sha256": body["original_plan_sha256"], "probe_report_sha256": body["probe_report_sha256"],
            "mode": body["mode"], "status": status, "failure": failure, "failure_stage": stage if status != "CAPTURED" else None,
            "last_http_status": http_status, "request_mode": body["request_mode"], "original_ticker_count": 43,
            "page_counts": {key: len(value) for key, value in pages.items()}, "native_source_row_counts": counts,
            "unique_row_counts": {key: len(value) for key, value in rows.items()}, "exact_duplicate_rows": duplicates,
            "unique_price_ticker_count": len({row["ticker"] for row in rows["stocks"]}),
            "response_bytes": total_bytes, "projection_sha256": projection_id, "provider_requests": attempts if production else 0,
            "fixture_transport_calls": 0 if production else attempts, "existing_development_look_spent": 1 if production else 0,
            "additional_development_looks": 0, "backtest_completed": False, "real_backtest_ready": False,
            "canonical_admission": False, "rights_verified": False, "quantconnect_attempts": 0, "trading": False}
        payload = source._canonical(report)
        identity = source._digest(payload)
        aggregate, terminal = RESUME_ID + "." + identity + ".aggregate.json", RESUME_ID + ".terminal.json"
        source._publish(fd, aggregate, payload)
        source._publish(fd, terminal, source._canonical({"schema": "tpr-resume-terminal-v1", "resume_id": RESUME_ID,
            "resume_plan_sha256": plan.sha256, "aggregate_sha256": identity, "status": status,
            "projection_sha256": projection_id, "additional_development_looks": 0}))
        if interrupted: raise KeyboardInterrupt("resume interrupted; original look and resume remain spent") from None
        return market.CaptureResult(payload, identity, projection_path, root / aggregate, root / terminal)
    finally:
        os.close(fd)


def execute_resume_backtest(plan, capture_report_sha256):
    if type(plan) is not ResumePlan or plan.body()["mode"] != "production":
        raise ValueError("public resume simulation is production-only")
    return _simulate(plan, capture_report_sha256, market.PRODUCTION_ROOT)


def _execute_fixture_backtest(plan, capture_report_sha256, root, *, now):
    if type(plan) is not ResumePlan or plan.body()["mode"] != "offline-fixture":
        raise ValueError("fixture resume simulation requires offline-fixture mode")
    return _simulate(plan, capture_report_sha256, root, now=now)


def _admit_capture_report(capture, plan):
    body, production = plan.body(), plan.body()["mode"] == "production"
    keys = {"schema", "resume_id", "resume_plan_sha256", "original_plan_sha256", "probe_report_sha256", "mode", "status",
        "failure", "failure_stage", "last_http_status", "request_mode", "original_ticker_count", "page_counts",
        "native_source_row_counts", "unique_row_counts", "exact_duplicate_rows", "unique_price_ticker_count", "response_bytes",
        "projection_sha256", "provider_requests", "fixture_transport_calls", "existing_development_look_spent",
        "additional_development_looks", "backtest_completed", "real_backtest_ready", "canonical_admission", "rights_verified",
        "quantconnect_attempts", "trading"}
    if (type(capture) is not dict or set(capture) != keys or capture["schema"] != "tpr-raw-market-resume-capture-report-v1"
            or capture["resume_id"] != RESUME_ID or capture["resume_plan_sha256"] != plan.sha256
            or capture["original_plan_sha256"] != body["original_plan_sha256"] or capture["probe_report_sha256"] != body["probe_report_sha256"]
            or capture["mode"] != body["mode"] or capture["request_mode"] != body["request_mode"]
            or capture["status"] != "CAPTURED" or capture["failure"] is not None or capture["failure_stage"] is not None
            or any(capture[key] is not False for key in ("backtest_completed", "real_backtest_ready", "canonical_admission", "rights_verified", "trading"))):
        raise ValueError("resume capture not applicable to simulation")
    count = len(_batches(body))
    for key, expected in (("last_http_status", 200), ("original_ticker_count", 43), ("provider_requests", 2 * count if production else 0),
            ("fixture_transport_calls", 0 if production else 2 * count), ("existing_development_look_spent", 1 if production else 0),
            ("additional_development_looks", 0), ("quantconnect_attempts", 0)):
        if type(capture[key]) is not int or capture[key] != expected:
            raise ValueError("resume capture counter mismatch")
    for key in ("page_counts", "native_source_row_counts", "unique_row_counts", "exact_duplicate_rows"):
        values = capture[key]
        if type(values) is not dict or set(values) != set(market.FIELDS) or any(type(v) is not int or v < 0 for v in values.values()):
            raise ValueError("resume capture inventory counts invalid")
    for dataset in market.FIELDS:
        if (capture["page_counts"][dataset] != count or capture["native_source_row_counts"][dataset] >= count * LIMITS["rows_per_page"]
                or capture["native_source_row_counts"][dataset] != capture["unique_row_counts"][dataset] + capture["exact_duplicate_rows"][dataset]):
            raise ValueError("resume capture inventory incomplete")
    if (type(capture["unique_price_ticker_count"]) is not int or not 0 <= capture["unique_price_ticker_count"] <= 43
            or type(capture["response_bytes"]) is not int or not 0 < capture["response_bytes"] <= LIMITS["total_bytes"]):
        raise ValueError("resume capture bounds invalid")
    source._hash(capture["projection_sha256"])
    return capture["projection_sha256"]


def _simulate(plan, capture_report_sha256, root, *, now=None):
    body, current = _context(plan, root, now)
    source._hash(capture_report_sha256)
    old, production = body["original_plan"], body["mode"] == "production"
    fd = raw_run._open_root(root, body["mode"])
    try:
        _history(fd, plan)
        _check_resume_claim(fd, plan)
        capture = _read(fd, RESUME_ID + "." + capture_report_sha256 + ".aggregate.json", capture_report_sha256)
        projection_id = _admit_capture_report(capture, plan)
        claim_failure = _claim(fd, market.CANDIDATE_ID + ".simulation.spent.json",
            _claim_body(plan, current, capture_report_sha256=capture_report_sha256, projection_sha256=projection_id))
        status, stage, failure, interrupted, report_id, report_path, summary = "FAILED", "reservation", None, False, None, None, None
        try:
            if claim_failure:
                if claim_failure.interrupted: raise KeyboardInterrupt
                raise claim_failure
            _check_clock(body, now)
            stage = "projection"
            projection = _read(fd, RESUME_ID + "." + projection_id + ".projection.json", projection_id, LIMITS["total_bytes"])
            expected = {"schema", "resume_id", "resume_plan_sha256", "original_plan_sha256", "mode", "structure_sha256",
                "waiver_sha256", "code_hashes", "resume_code_sha256", "capture_utc", "prices", "actions", "pages",
                "native_source_rows", "exact_duplicate_rows", "transactional_snapshot", "point_in_time_data", "canonical_admission"}
            if (set(projection) != expected or projection["schema"] != "tpr-raw-market-resume-projection-v1"
                    or projection["resume_id"] != RESUME_ID or projection["resume_plan_sha256"] != plan.sha256
                    or projection["original_plan_sha256"] != body["original_plan_sha256"] or projection["mode"] != body["mode"]
                    or projection["structure_sha256"] != old["structure_sha256"] or projection["waiver_sha256"] != old["waiver_sha256"]
                    or projection["code_hashes"] != old["code_hashes"] or projection["resume_code_sha256"] != body["code_sha256"]
                    or not source._clock(body["created_utc"]) <= source._clock(projection["capture_utc"]) <= current
                    or any(projection[key] is not False for key in ("transactional_snapshot", "point_in_time_data", "canonical_admission"))):
                raise ValueError("resume projection binding mismatch")
            stage = "structure"
            structure = _read(fd, "structure.json", old["structure_sha256"], raw_run.MAX_INPUT_BYTES)
            stage = "simulation"
            result = market._compute(structure, projection)
            if production: _identity(body)
            stage = "summary"
            summary = market._result_summary(result)
            payload = source._canonical({"schema": "tpr-raw-resume-private-simulation-v1", "resume_plan_sha256": plan.sha256,
                "capture_report_sha256": capture_report_sha256, "projection_sha256": projection_id,
                "code_sha256": body["code_sha256"], "code_hashes": old["code_hashes"], "result": result, "summary": summary})
            if len(payload) > LIMITS["total_bytes"]: raise ValueError("resume simulation report size bound")
            report_id = source._digest(payload)
            name = RESUME_ID + "." + report_id + ".backtest.json"
            stage = "publication"
            source._publish(fd, name, payload)
            report_path, status = root / name, "SIMULATED"
        except KeyboardInterrupt:
            status, failure, interrupted = "INTERRUPTED", "resume_simulation_interrupted", True
        except Exception:
            failure = "resume_simulation_failed"
        aggregate_body = {"schema": "tpr-raw-resume-simulation-report-v1", "resume_id": RESUME_ID,
            "resume_plan_sha256": plan.sha256, "original_plan_sha256": body["original_plan_sha256"],
            "capture_report_sha256": capture_report_sha256, "projection_sha256": projection_id, "private_report_sha256": report_id,
            "mode": body["mode"], "status": status, "failure": failure, "failure_stage": stage if status != "SIMULATED" else None,
            "summary": summary, "existing_development_look_spent": 1 if production else 0, "additional_development_looks": 0,
            "simulation_runs": 1, "canonical_admission": False, "quantconnect_attempts": 0, "trading": False}
        payload = source._canonical(aggregate_body)
        identity = source._digest(payload)
        aggregate, terminal = RESUME_ID + "." + identity + ".simulation.aggregate.json", RESUME_ID + ".simulation.terminal.json"
        source._publish(fd, aggregate, payload)
        source._publish(fd, terminal, source._canonical({"schema": "tpr-resume-simulation-terminal-v1", "resume_id": RESUME_ID,
            "resume_plan_sha256": plan.sha256, "status": status, "aggregate_sha256": identity,
            "private_report_sha256": report_id, "additional_development_looks": 0, "simulation_runs": 1}))
        if interrupted: raise KeyboardInterrupt("resume simulation interrupted; remains spent") from None
        return market.SimulationResult(payload, identity, report_path, root / aggregate, root / terminal)
    finally:
        os.close(fd)
