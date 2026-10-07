"""One fresh metadata-only structural inspection; imports have no effects.

Recognized envelopes are observations, not authentication, source rights or
data admission. The executed original collectors remain byte-frozen.
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

SHAPE_ID = "TPR-SHARADAR-SHAPE-20261007-001"
AUDITOR_CODE_SHA256 = "9f2674a47d0d62bb09e2dd5ba1ce7f37eed3c68dce254e40e0d11d1218f46960"
LIMITS = {"requests": 1, "response_bytes": 65536, "request_timeout_seconds": 10,
    "redirects": 0, "retries": 0, "pages_followed": 0, "rows": 0,
    "max_report_bytes": 32768, "max_shape_depth": 4, "max_shape_nodes": 32,
    "max_file_descriptors": 8}
FIELDS = ("table", "name", "filename", "size", "sizeLabel", "size_label", "modified",
    "lastModified", "last_modified", "status", "code", "error", "message", "years", "type",
    "url", "download_url", "downloadUrl", "path", "link")
WRAPPERS = ("file", "files", "data", "metadata", "result", "results", "bulk", "bulkFile",
    "bulk_file", "download", "downloads", "full", "5", "10", "error", "status")
FILE_ARRAYS = ("files", "downloads")
FILE_REQUIRED = frozenset(("name", "size", "sizeLabel", "modified"))
ROW_MARKERS = ("ticker", "permaticker", "cusips", "figi", "date", "price", "lastupdated",
    "last_updated", "open", "close", "volume", "rows", "columns")
_FIXED_CREDENTIAL, _FIXED_TRANSPORT = _production_credential, _https_get


@dataclass(frozen=True)
class ShapePlan:
    payload: bytes
    sha256: str

    def body(self) -> dict:
        if type(self.payload) is not bytes or len(self.payload) > 16384 or _digest(self.payload) != self.sha256:
            raise SourceAuditError("invalid shape plan identity")
        try:
            body = _source_object(self.payload)
            expected = freeze_shape_plan(code_sha256=body["code_sha256"], git_sha=body["git_sha"],
                owner_instruction_sha256=body["owner_instruction_sha256"], created_utc=body["created_utc"],
                expires_utc=body["expires_utc"], mode=body["mode"])
            if self.payload != expected.payload:
                raise SourceAuditError("invalid shape plan policy")
            return body
        except (ValueError, TypeError, KeyError):
            raise SourceAuditError("invalid shape plan policy") from None


def freeze_shape_plan(*, code_sha256: str, git_sha: str, owner_instruction_sha256: str,
                      created_utc: str, expires_utc: str, mode: str = "production") -> ShapePlan:
    for value, length in ((code_sha256, 64), (git_sha, 40), (owner_instruction_sha256, 64)):
        if type(value) is not str or re.fullmatch("[0-9a-f]{" + str(length) + "}", value) is None:
            raise SourceAuditError("invalid shape identity")
    created, expires = _clock(created_utc), _clock(expires_utc)
    if mode not in ("production", "offline-fixture") or not created < expires <= created + timedelta(hours=48):
        raise SourceAuditError("invalid shape mode or expiry")
    payload = _canonical({"schema": "tpr-sharadar-shape-plan-v1", "shape_id": SHAPE_ID,
        "mode": mode, "code_sha256": code_sha256, "auditor_code_sha256": AUDITOR_CODE_SHA256,
        "git_sha": git_sha, "owner_instruction_sha256": owner_instruction_sha256,
        "created_utc": created.isoformat(), "expires_utc": expires.isoformat(),
        "lane_root": str(LANE_ROOT), "lane_branch": LANE_BRANCH,
        "private_destination": "artifacts/target_price_source_audit",
        "requests": [REQUESTS[1].body()], "limits": dict(LIMITS), "authority": dict(AUTHORITY),
        "shape_fields": list(FIELDS), "shape_wrappers": list(WRAPPERS), "row_markers": list(ROW_MARKERS),
        "opaque_row_arrays": True, "raw_retention": False, "d0_renewed": False,
        "original_audit_renewed": False, "previous_diagnostic_renewed": False,
        "license_entitlement": "unestablished", "point_in_time_facts": "unestablished"})
    return ShapePlan(payload, _digest(payload))


def _kind(value: object) -> str:
    return {str: "string", int: "integer", bool: "boolean", type(None): "null",
        list: "array", dict: "object", Decimal: "decimal"}.get(type(value), "unsupported")


def _components(body: dict) -> dict:
    valid = {"name_valid": type(body.get("name")) is str and 1 <= len(body["name"]) <= 256,
        "size_label_valid": type(body.get("sizeLabel")) is str and 1 <= len(body["sizeLabel"]) <= 128,
        "size_valid": type(body.get("size")) is int and 0 <= body["size"] <= 10**15,
        "modified_utc_valid": False}
    if type(body.get("modified")) is str:
        try:
            _clock(body["modified"])
            valid["modified_utc_valid"] = True
        except SourceAuditError:
            pass
    return valid


def _application_error(body: dict) -> str | None:
    categories = {"INVALID_API_KEY": "invalid_api_key", "invalid_api_key": "invalid_api_key",
        "UNAUTHORIZED": "unauthorized", "Unauthorized": "unauthorized", "FORBIDDEN": "forbidden",
        "Forbidden": "forbidden", "RATE_LIMITED": "rate_limit", "RATE_LIMIT": "rate_limit"}
    category = next((categories[body[key]] for key in ("code", "error", "status")
        if type(body.get(key)) is str and body[key] in categories), None)
    error = body.get("error")
    active = error is True or (type(error) in (str, list, dict) and len(error) > 0)
    failed = type(body.get("status")) is str and body["status"] in ("ERROR", "error", "FAILED", "failed")
    return category or ("unclassified" if active or failed else None)


def _empty_diagnosis() -> dict:
    return {"classification": "not_observed", "profile": "unmapped", "application_error": None,
        "table_literal": "not_observed", "nodes": [], "shape_budget_refused": False,
        "metadata": {"metadata_shape_observed": False, "size_bytes": None, "snapshot_utc": None}}


def _selector(value: object) -> str:
    if type(value) is str:
        return value if value in ("full", "5", "10") else "other"
    if type(value) is int:
        return str(value) if value in (5, 10) else "other"
    return "not_selector"


def inspect_metadata(body: dict) -> dict:
    """Whitelisted paths/types only; row-shaped arrays are semantically opaque.

    Input JSON has already been bounded and decoded in memory by the frozen
    privacy gate. No arbitrary key/value, filename or advertised URL escapes.
    """
    if type(body) is not dict or any(type(key) is not str for key in body):
        raise SourceAuditError("invalid shape metadata object")
    result = _empty_diagnosis()
    table = body.get("table")
    result["table_literal"] = (("lower" if table == "tickers" else "upper" if table == "TICKERS"
        else "mixed_tickers" if table.lower() == "tickers" else "other")
        if type(table) is str else "not_string")
    errors = []

    def visit(value: object, path: str, depth: int, wrapper: str = "") -> None:
        if depth > LIMITS["max_shape_depth"] or len(result["nodes"]) >= LIMITS["max_shape_nodes"]:
            result["shape_budget_refused"] = True
            return
        node = {"path": path, "kind": _kind(value)}
        result["nodes"].append(node)
        if type(value) is dict:
            if any(key in ROW_MARKERS for key in value):
                node.update(opaque=True, row_shape_refused=True)
                return
            fields = {key: _kind(value[key]) if key in value else "absent" for key in FIELDS}
            unknown = [key for key in value if key not in FIELDS and key not in WRAPPERS]
            counts = {}
            for key in unknown:
                kind = _kind(value[key])
                counts[kind] = counts.get(kind, 0) + 1
            node.update(fields=fields, unknown_key_count=len(unknown), unknown_types=counts,
                components=_components(value), selector=_selector(value.get("years")))
            error = _application_error(value)
            if error is not None:
                errors.append(error)
            for key in WRAPPERS:
                if key in value:
                    visit(value[key], path + "/" + key, depth + 1, key)
        elif type(value) is list:
            # Only a closed descriptor vocabulary can be traversed. Unknown
            # row keys are checked for refusal but row values are never read.
            descriptor = (wrapper in FILE_ARRAYS and len(value) <= LIMITS["max_file_descriptors"]
                and all(type(item) is dict and all(type(key) is str and (key in FIELDS or key in WRAPPERS) for key in item)
                    for item in value))
            node.update(length=len(value), opaque=not descriptor)
            if descriptor:
                for index, item in enumerate(value):
                    visit(item, path + "/" + str(index), depth + 1)

    visit(body, "root", 0)
    result["classification"] = "metadata_shape_unmapped"
    if errors:
        result.update(classification="application_error", application_error=
            next((error for error in errors if error != "unclassified"), "unclassified"))
        return result
    selected = None
    if set(body) == FILE_REQUIRED | {"table"}:
        selected, result["profile"] = body, "flat_metadata_v1"
    elif (set(body) == {"table", "files"} and type(body["files"]) is list
            and len(body["files"]) == 1 and type(body["files"][0]) is dict
            and set(body["files"][0]) == FILE_REQUIRED):
        selected, result["profile"] = body["files"][0], "table_files_singleton_v1"
    if (selected is not None and type(table) is str and table == "tickers" and not result["shape_budget_refused"]
            and all(_components(selected).values())):
        result["classification"] = "metadata_shape_observed"
        result["metadata"] = {"metadata_shape_observed": True, "size_bytes": selected["size"],
            "snapshot_utc": _clock(selected["modified"]).isoformat()}
    return result


def _verify_identity(body: dict) -> None:
    _verify_execution_identity({"git_sha": body["git_sha"], "code_sha256": AUDITOR_CODE_SHA256})
    descriptor = None
    try:
        source = Path(__file__)
        expected = LANE_ROOT / "research" / "target_price_revisions_development" / "sharadar_shape.py"
        if source != expected or source.resolve() != expected:
            raise SourceAuditError("shape code identity mismatch")
        descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 262144:
            raise SourceAuditError("shape code identity mismatch")
        payload = os.read(descriptor, 262144)
        if len(payload) != metadata.st_size or _digest(payload) != body["code_sha256"]:
            raise SourceAuditError("shape code identity mismatch")
    except OSError:
        raise SourceAuditError("shape code identity unavailable") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _claim(directory_fd: int, plan: ShapePlan, current: datetime) -> None:
    payload = _canonical({"schema": "tpr-sharadar-shape-spent-v1", "shape_id": SHAPE_ID,
        "plan_sha256": plan.sha256, "started_utc": current.isoformat(), "mode": plan.body()["mode"]})
    try:
        descriptor = os.open(SHAPE_ID + ".spent.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=directory_fd)
    except FileExistsError:
        raise SourceAuditError("shape already spent") from None
    except OSError:
        raise SourceAuditError("shape claim unavailable") from None
    try:
        if os.write(descriptor, payload) != len(payload):
            raise SourceAuditError("shape claim incomplete; one-shot scope remains spent")
        os.fsync(descriptor)
        os.fsync(directory_fd)
    except OSError:
        raise SourceAuditError("shape claim failed; one-shot scope remains spent") from None
    finally:
        os.close(descriptor)


@dataclass(frozen=True)
class ShapeResult:
    payload: bytes
    sha256: str
    aggregate_path: Path
    terminal_path: Path


def execute_shape(plan: ShapePlan, private_root: Path, *, now: datetime | None = None,
                  credential_resolver: Callable | None = None, transport: Callable | None = None) -> ShapeResult:
    """Claim before lookup; only offline mode accepts synthetic adapters."""
    if type(plan) is not ShapePlan:
        raise SourceAuditError("invalid shape plan frame")
    body = plan.body()
    mode = body["mode"]
    if mode == "production":
        if now is not None or credential_resolver is not None or transport is not None:
            raise SourceAuditError("shape injections require offline fixture mode")
        if private_root != PRIVATE_ROOT:
            raise SourceAuditError("production requires the fixed lane audit root")
        _verify_identity(body)
    else:
        if private_root == PRIVATE_ROOT:
            raise SourceAuditError("offline fixture cannot consume the production shape")
        if (credential_resolver is None or transport is None
                or credential_resolver in (_FIXED_CREDENTIAL, _production_credential)
                or transport in (_FIXED_TRANSPORT, _https_get)):
            raise SourceAuditError("offline shape requires synthetic fixtures")
    current = datetime.now(timezone.utc) if now is None else now
    if type(current) is not datetime or current.tzinfo is None or current.utcoffset() != timedelta(0):
        raise SourceAuditError("invalid shape UTC clock")
    if not _clock(body["created_utc"]) <= current < _clock(body["expires_utc"]):
        raise SourceAuditError("shape plan is not currently valid")
    directory_fd = _private_directory(private_root, mode)
    try:
        _claim(directory_fd, plan, current)
        status, attempts, interrupted = "COMPLETED", 0, False
        provider = {"provider": "sharadar", "http_status": None, "disposition": "not_attempted",
            "authenticated_access_observed": False, "response_bytes": 0, "response_bytes_complete": True,
            "response_sha256": None, "metadata": {"metadata_shape_observed": False, "size_bytes": None, "snapshot_utc": None}}
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
                if (response.refusal is not None or provider["disposition"] in
                        ("redirect_refused", "encoding_refused", "content_type_refused", "response_byte_limit_refused")):
                    provider["response_bytes_complete"] = False
                if provider["response_sha256"] is not None:
                    diagnosis = inspect_metadata(_source_object(response.body))
                    # The frozen privacy gate may compute identity in memory;
                    # this narrow scope publishes no raw-body identity for
                    # unsolicited rows, opaque/unknown or unvisited structure.
                    if (diagnosis["shape_budget_refused"] or any(node.get("opaque")
                            or node.get("row_shape_refused") or node.get("unknown_key_count", 0)
                            for node in diagnosis["nodes"])):
                        provider["response_sha256"] = None
                    if response.status != 200:
                        diagnosis["classification"] = "http_access_refused"
        except KeyboardInterrupt:
            status, interrupted = "INTERRUPTED", True
            provider["disposition"] = "transport_interrupted" if attempts else "credential_interrupted"
            provider["response_bytes_complete"] = False
        except Exception:
            # Authenticated URLs/provider values can occur in exception text.
            status = "FAILED"
            provider["disposition"] = "transport_failed" if attempts else "credential_failed"
            provider["response_bytes_complete"] = False
        report = {"schema": "tpr-sharadar-shape-report-v1", "shape_id": SHAPE_ID,
            "mode": mode, "status": status, "started_utc": current.isoformat(), "plan_sha256": plan.sha256,
            "code_sha256": body["code_sha256"], "auditor_code_sha256": AUDITOR_CODE_SHA256,
            "git_sha": body["git_sha"], "owner_instruction_sha256": body["owner_instruction_sha256"],
            "provider": provider, "diagnosis": diagnosis, "credential_state": "not_proven",
            "provider_requests": attempts if mode == "production" else 0,
            "fixture_transport_calls": attempts if mode == "offline-fixture" else 0,
            "authority": dict(AUTHORITY), "license_entitlement": "unestablished",
            "point_in_time_facts": "unestablished", "real_development_backtest_ready": False,
            "canonical_admission": False, "d0_renewed": False, "original_audit_renewed": False,
            "previous_diagnostic_renewed": False, "outcome_reads": 0, "qc_attempts": 0, "development_looks": 0}
        payload = _canonical(report)
        if len(payload) > LIMITS["max_report_bytes"]:
            raise SourceAuditError("shape report exceeds budget; one-shot scope remains spent")
        identity = _digest(payload)
        aggregate_name, terminal_name = SHAPE_ID + "." + identity + ".aggregate.json", SHAPE_ID + ".terminal.json"
        _publish(directory_fd, aggregate_name, payload)
        _publish(directory_fd, terminal_name, _canonical({"schema": "tpr-sharadar-shape-terminal-v1",
            "shape_id": SHAPE_ID, "plan_sha256": plan.sha256, "aggregate_sha256": identity,
            "status": status, "mode": mode}))
        if interrupted:
            raise KeyboardInterrupt("shape interrupted; one-shot scope remains spent") from None
        return ShapeResult(payload, identity, private_root / aggregate_name, private_root / terminal_name)
    finally:
        os.close(directory_fd)
