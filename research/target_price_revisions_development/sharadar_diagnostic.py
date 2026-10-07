"""Separate spent, metadata-only Sharadar diagnosis; import has no effects.

The original audit and its source bytes remain frozen. This diagnostic does
not renew it, validate a subscription from HTTP status, or admit market data.
"""
from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable

from .source_audit import (
    AUTHORITY, LANE_BRANCH, LANE_ROOT, PRIVATE_ROOT, REQUESTS, SourceAuditError,
    _canonical, _clock, _digest, _https_get, _private_directory,
    _production_credential, _publish, _reduce_response, _source_object,
    _valid_credential, _verify_execution_identity,
)

DIAGNOSTIC_ID = "TPR-SHARADAR-DIAGNOSTIC-20261006-001"
AUDITOR_CODE_SHA256 = "9f2674a47d0d62bb09e2dd5ba1ce7f37eed3c68dce254e40e0d11d1218f46960"
LIMITS = {"requests": 1, "response_bytes": 65536, "request_timeout_seconds": 10,
          "redirects": 0, "retries": 0, "pages_followed": 0, "rows": 0, "max_report_bytes": 32768}
FIELDS = ("table", "name", "size", "sizeLabel", "modified", "status", "code", "error", "message")
_FIXED_CREDENTIAL, _FIXED_TRANSPORT = _production_credential, _https_get


@dataclass(frozen=True)
class DiagnosticPlan:
    payload: bytes
    sha256: str

    def body(self) -> dict:
        if type(self.payload) is not bytes or len(self.payload) > 16384 or _digest(self.payload) != self.sha256:
            raise SourceAuditError("invalid diagnostic plan identity")
        try:
            body = _source_object(self.payload)
            expected = freeze_diagnostic_plan(code_sha256=body["code_sha256"], git_sha=body["git_sha"],
                owner_instruction_sha256=body["owner_instruction_sha256"], created_utc=body["created_utc"],
                expires_utc=body["expires_utc"], mode=body["mode"])
            if self.payload != expected.payload:
                raise SourceAuditError("invalid diagnostic plan policy")
            return body
        except (ValueError, TypeError, KeyError):
            raise SourceAuditError("invalid diagnostic plan policy") from None


def freeze_diagnostic_plan(*, code_sha256: str, git_sha: str, owner_instruction_sha256: str,
                           created_utc: str, expires_utc: str, mode: str = "production") -> DiagnosticPlan:
    for value, length in ((code_sha256, 64), (git_sha, 40), (owner_instruction_sha256, 64)):
        if type(value) is not str or re.fullmatch("[0-9a-f]{" + str(length) + "}", value) is None:
            raise SourceAuditError("invalid diagnostic identity")
    created, expires = _clock(created_utc), _clock(expires_utc)
    if mode not in ("production", "offline-fixture") or not created < expires <= created + timedelta(hours=48):
        raise SourceAuditError("invalid diagnostic mode or expiry")
    payload = _canonical({"schema": "tpr-sharadar-diagnostic-plan-v1", "diagnostic_id": DIAGNOSTIC_ID,
        "mode": mode, "code_sha256": code_sha256, "auditor_code_sha256": AUDITOR_CODE_SHA256,
        "git_sha": git_sha, "owner_instruction_sha256": owner_instruction_sha256,
        "created_utc": created.isoformat(), "expires_utc": expires.isoformat(),
        "lane_root": str(LANE_ROOT), "lane_branch": LANE_BRANCH,
        "private_destination": "artifacts/target_price_source_audit",
        "requests": [REQUESTS[1].body()], "limits": dict(LIMITS), "authority": dict(AUTHORITY),
        "raw_retention": False, "d0_renewed": False, "original_audit_renewed": False,
        "license_entitlement": "unestablished", "point_in_time_facts": "unestablished"})
    return DiagnosticPlan(payload, _digest(payload))


def _kind(value: object) -> str:
    return {str: "string", int: "integer", bool: "boolean", type(None): "null",
            list: "array", dict: "object", Decimal: "decimal"}.get(type(value), "unsupported")


def _empty_diagnosis() -> dict:
    return {"classification": "not_observed", "application_error": None, "clauses": [],
        "table_literal": "not_observed", "shape": {"fields": {}, "unknown_key_count": 0},
        "metadata": {"metadata_shape_observed": False, "size_bytes": None, "snapshot_utc": None}}


def diagnose_metadata(body: dict) -> dict:
    """Closed shape/reason enums, not free text or a repaired admission schema."""
    if type(body) is not dict or any(type(key) is not str for key in body):
        raise SourceAuditError("invalid diagnostic metadata object")
    result = _empty_diagnosis()
    result["shape"] = {"fields": {key: _kind(body[key]) if key in body else "absent" for key in FIELDS},
                       "unknown_key_count": len(set(body) - set(FIELDS))}
    table = body.get("table")
    result["table_literal"] = ({"tickers": "lower", "TICKERS": "upper"}.get(table,
                                "mixed_tickers" if table.lower() == "tickers" else "other")
                                if type(table) is str else "not_string")
    errors = {"INVALID_API_KEY": "invalid_api_key", "invalid_api_key": "invalid_api_key",
        "UNAUTHORIZED": "unauthorized", "Unauthorized": "unauthorized",
        "FORBIDDEN": "forbidden", "Forbidden": "forbidden", "RATE_LIMITED": "rate_limit",
        "RATE_LIMIT": "rate_limit"}
    category = next((errors[body[key]] for key in ("code", "error", "status")
                     if type(body.get(key)) is str and body[key] in errors), None)
    error = body.get("error")
    active_error = error is True or (type(error) in (str, list, dict) and len(error) > 0)
    explicit_error = (category is not None or active_error
                      or (type(body.get("status")) is str and body["status"] in ("ERROR", "error", "FAILED", "failed")))
    if explicit_error:
        if category is None and type(body.get("message")) is str:
            # Only an exact closed message is unambiguous; substring matches
            # would mistake a negated or quoted credential phrase for rejection.
            message = body["message"].strip().lower().rstrip(".")
            category = {"invalid api key": "invalid_api_key", "unauthorized": "unauthorized",
                        "forbidden": "forbidden", "rate limit": "rate_limit"}.get(message)
        result.update(classification="application_error", application_error=category or "unclassified")
        return result
    clauses = []
    required = {"table", "name", "size", "sizeLabel", "modified"}
    if set(body) - required:
        clauses.append("unexpected_keys")
    for field in sorted(required - set(body)):
        clauses.append("missing_" + field)
    if "table" in body:
        if type(table) is not str:
            clauses.append("table_type")
        elif table != "tickers":
            clauses.append("table_literal_mismatch")
    for field, label, maximum in (("name", "name", 256), ("sizeLabel", "size_label", 128)):
        if field in body:
            if type(body[field]) is not str:
                clauses.append(label + "_type")
            elif not 1 <= len(body[field]) <= maximum:
                clauses.append(label + "_length")
    if "size" in body:
        if type(body["size"]) is not int:
            clauses.append("size_type")
        elif not 0 <= body["size"] <= 10**15:
            clauses.append("size_range")
    snapshot = None
    if "modified" in body:
        if type(body["modified"]) is not str:
            clauses.append("modified_type")
        else:
            try:
                snapshot = _clock(body["modified"]).isoformat()
            except SourceAuditError:
                clauses.append("modified_utc")
    result["clauses"] = clauses
    result["classification"] = "metadata_schema_mismatch" if clauses else "metadata_verified"
    if not clauses:
        result["metadata"] = {"metadata_shape_observed": True, "size_bytes": body["size"], "snapshot_utc": snapshot}
    return result


def _verify_identity(body: dict) -> None:
    _verify_execution_identity({"git_sha": body["git_sha"], "code_sha256": AUDITOR_CODE_SHA256})
    descriptor = None
    try:
        source = Path(__file__)
        expected = LANE_ROOT / "research" / "target_price_revisions_development" / "sharadar_diagnostic.py"
        if source != expected or source.resolve() != expected:
            raise SourceAuditError("diagnostic code identity mismatch")
        descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 262144:
            raise SourceAuditError("diagnostic code identity mismatch")
        payload = os.read(descriptor, 262144)
        if len(payload) != metadata.st_size or _digest(payload) != body["code_sha256"]:
            raise SourceAuditError("diagnostic code identity mismatch")
    except OSError:
        raise SourceAuditError("diagnostic code identity unavailable") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _claim(directory_fd: int, plan: DiagnosticPlan, current: datetime) -> None:
    payload = _canonical({"schema": "tpr-sharadar-diagnostic-spent-v1", "diagnostic_id": DIAGNOSTIC_ID,
        "plan_sha256": plan.sha256, "started_utc": current.isoformat(), "mode": plan.body()["mode"]})
    try:
        descriptor = os.open(DIAGNOSTIC_ID + ".spent.json",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
    except FileExistsError:
        raise SourceAuditError("diagnostic already spent") from None
    except OSError:
        raise SourceAuditError("diagnostic claim unavailable") from None
    try:
        if os.write(descriptor, payload) != len(payload):
            raise SourceAuditError("diagnostic claim incomplete; one-shot scope remains spent")
        os.fsync(descriptor)
        os.fsync(directory_fd)
    except OSError:
        raise SourceAuditError("diagnostic claim failed; one-shot scope remains spent") from None
    finally:
        os.close(descriptor)


@dataclass(frozen=True)
class DiagnosticResult:
    payload: bytes
    sha256: str
    aggregate_path: Path
    terminal_path: Path


def execute_diagnostic(plan: DiagnosticPlan, private_root: Path, *, now: datetime | None = None,
                       credential_resolver: Callable | None = None, transport: Callable | None = None) -> DiagnosticResult:
    """Spend one new ID before lookup; only fixture mode accepts fake adapters."""
    if type(plan) is not DiagnosticPlan:
        raise SourceAuditError("invalid diagnostic plan frame")
    body, mode = plan.body(), plan.body()["mode"]
    if mode == "production":
        if now is not None or credential_resolver is not None or transport is not None:
            raise SourceAuditError("diagnostic injections require offline fixture mode")
        if private_root != PRIVATE_ROOT:
            raise SourceAuditError("production requires the fixed lane audit root")
        _verify_identity(body)
    else:
        if private_root == PRIVATE_ROOT:
            raise SourceAuditError("offline fixture cannot consume the production diagnostic")
        if (credential_resolver is None or transport is None
                or credential_resolver in (_FIXED_CREDENTIAL, _production_credential)
                or transport in (_FIXED_TRANSPORT, _https_get)):
            raise SourceAuditError("offline diagnostic requires synthetic fixtures")
    current = datetime.now(timezone.utc) if now is None else now
    if type(current) is not datetime or current.tzinfo is None or current.utcoffset() != timedelta(0):
        raise SourceAuditError("invalid diagnostic UTC clock")
    if not _clock(body["created_utc"]) <= current < _clock(body["expires_utc"]):
        raise SourceAuditError("diagnostic plan is not currently valid")
    directory_fd = _private_directory(private_root, mode)
    try:
        _claim(directory_fd, plan, current)
        status, attempts, interrupted = "COMPLETED", 0, False
        provider = {"provider": "sharadar", "http_status": None, "disposition": "not_attempted",
            "authenticated_access_observed": False, "response_bytes": 0,
            "response_bytes_complete": True, "response_sha256": None,
            "metadata": {"metadata_shape_observed": False, "size_bytes": None, "snapshot_utc": None}}
        diagnosis = _empty_diagnosis()
        try:
            resolver = _production_credential if mode == "production" else credential_resolver
            fetch = _https_get if mode == "production" else transport
            credential = resolver("sharadar")
            valid = _valid_credential(credential) and (mode == "production" or credential.startswith("SYNTHETIC_"))
            if not valid:
                provider["disposition"] = "credential_unavailable"
            else:
                attempts = 1
                response = fetch(REQUESTS[1], credential)
                provider = _reduce_response(REQUESTS[1], response, (credential,), actual=False)
                provider["authenticated_access_observed"] = False
                # Semantic/credential rejection is not a truncated capture.
                # Transport refusals skip/discard remaining body bytes and only
                # establish the reported lower bound, even at known status 200.
                if (response.refusal is not None or provider["disposition"] in
                        ("redirect_refused", "encoding_refused", "content_type_refused", "response_byte_limit_refused")):
                    provider["response_bytes_complete"] = False
                # The inherited reducer checks raw/decoded echoes BEFORE hashes.
                # No shape, raw value or digest escapes a failed privacy gate.
                if provider["response_sha256"] is not None:
                    diagnosis = diagnose_metadata(_source_object(response.body))
                    if response.status != 200:
                        diagnosis["classification"] = "http_access_refused"
        except KeyboardInterrupt:
            status, interrupted = "INTERRUPTED", True
            provider["disposition"] = "transport_interrupted" if attempts else "credential_interrupted"
            provider["response_bytes_complete"] = False
        except Exception:
            # Exception messages can contain authenticated URLs or provider data.
            status = "FAILED"
            provider["disposition"] = "transport_failed" if attempts else "credential_failed"
            provider["response_bytes_complete"] = False
        report = {"schema": "tpr-sharadar-diagnostic-report-v1", "diagnostic_id": DIAGNOSTIC_ID,
            "mode": mode, "status": status, "started_utc": current.isoformat(), "plan_sha256": plan.sha256,
            "code_sha256": body["code_sha256"], "auditor_code_sha256": AUDITOR_CODE_SHA256,
            "git_sha": body["git_sha"], "owner_instruction_sha256": body["owner_instruction_sha256"],
            "provider": provider, "diagnosis": diagnosis, "credential_state": "not_proven",
            "provider_requests": attempts if mode == "production" else 0,
            "fixture_transport_calls": attempts if mode == "offline-fixture" else 0,
            "authority": dict(AUTHORITY), "license_entitlement": "unestablished",
            "point_in_time_facts": "unestablished", "real_development_backtest_ready": False,
            "canonical_admission": False, "d0_renewed": False, "original_audit_renewed": False,
            "outcome_reads": 0, "qc_attempts": 0, "development_looks": 0}
        payload = _canonical(report)
        if len(payload) > LIMITS["max_report_bytes"]:
            raise SourceAuditError("diagnostic report exceeds budget; one-shot scope remains spent")
        identity = _digest(payload)
        aggregate_name, terminal_name = DIAGNOSTIC_ID + "." + identity + ".aggregate.json", DIAGNOSTIC_ID + ".terminal.json"
        _publish(directory_fd, aggregate_name, payload)
        _publish(directory_fd, terminal_name, _canonical({"schema": "tpr-sharadar-diagnostic-terminal-v1",
            "diagnostic_id": DIAGNOSTIC_ID, "plan_sha256": plan.sha256, "aggregate_sha256": identity,
            "status": status, "mode": mode}))
        if interrupted:
            raise KeyboardInterrupt("diagnostic interrupted; one-shot scope remains spent") from None
        return DiagnosticResult(payload, identity, private_root / aggregate_name, private_root / terminal_name)
    finally:
        os.close(directory_fd)
