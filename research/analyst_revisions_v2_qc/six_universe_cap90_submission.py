"""One-use, host-only QC submission for the exploratory cap-90 order family.

This module never acts on import.  A1 creates one private project per role;
later corrected attempts require a separately reviewed in-place continuation.
Only two bounded custom statistics may be retained from a completed run.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from research.quantconnect import API_BASE, QuantConnectClient

from . import accepted_risk_six_universe_order_qc_projection as projection_module
from . import accepted_risk_six_universe_order_qc_runtime as runtime
from .six_universe_coverage_submission import _bounded_transport, production_client


class Cap90QcSubmissionError(ValueError):
    """A frozen identity, private control, or bounded QC response changed."""


_ROLES = {"R181": "signal", "R182": "matched", "R183": "six_etf_basket"}
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ORG = re.compile(r"[0-9a-f]{32}\Z")
_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._ -]*\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
_PATH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*\.py\Z")
_CUSTOM = tuple(sorted((runtime.META_STATISTIC_NAME, runtime.AGGREGATES_STATISTIC_NAME)))
_DEFAULT_FILES = frozenset(("main.py", "research.ipynb"))
_META_FIELDS = frozenset({
    "schema", "role", "profile_id", "profile_sha256", "package_id",
    "package_sha256", "activation_manifest_sha256", "symbol_resolution_id",
    "symbol_resolution_sha256", "aggregate_schema", "aggregate_sha256",
    "result_transport", "raw_provider_rows", "raw_price_rows",
    "raw_order_rows", "preliminary", "formal", "backtest_only", "trading",
})
_AGGREGATE_FIELDS = frozenset({
    "schema", "role", "profile_id", "profile_sha256", "account",
    "account_observation_path_sha256", "gross_exposure_path_sha256",
    "mean_gross_exposure", "maximum_gross_exposure", "target_path_id",
    "target_path_sha256", "construction_path_sha256",
    "decision_target_path_sha256", "fallback_counts", "sleeve_diagnostics",
    "execution", "engine_forced_delisting", "reference_history_call_count",
    "active_dynamic_minute_security_count",
    "maximum_active_dynamic_minute_security_count",
    "removed_dynamic_minute_security_count", "pit_callback_source_row_count",
    "fundamental_snapshot_unavailable_decision_count",
    "fundamental_snapshot_unavailable_session_sha256",
    "constituent_collection_unavailable_decision_count",
    "constituent_collection_unavailable_universe_counts",
    "constituent_collection_unavailable_path_sha256", "run_valid",
    "preliminary", "formal", "backtest_only", "live_orders", "paper_orders",
    "funded_orders", "deployment", "trading",
})
_ACCOUNT_FIELDS = frozenset({
    "observation_count", "first_observation_session", "last_observation_session",
    "starting_equity", "ending_equity", "cumulative_return", "maximum_drawdown",
    "annualized_volatility", "zero_rate_sharpe",
})
_SLEEVE_FIELDS = (
    "universe_id", "etf_ticker", "decision_count", "coverage_valid_count",
    "coverage_invalid_count", "positive_score_count_sum",
    "selected_security_count_sum", "post_cap_stock_target_count_sum",
    "etf_target_weight_sum", "duplicate_cap_excess_weight_sum",
    "coverage_refusal_reason_counts", "selection_status_counts",
)
_UNIVERSES = ("SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE")
_COVERAGE_REASONS = frozenset({
    "TOTAL_REPORTED_WEIGHT_OUT_OF_RANGE", "SID_NAME_MAPPING_BELOW_MINIMUM",
    "MARKET_CAP_WEIGHT_COVERAGE_BELOW_MINIMUM",
    "CONSTITUENT_COLLECTION_UNAVAILABLE",
})
_SELECTION_STATUSES = frozenset({
    "SIX_ETF_BASKET", "COVERAGE_FALLBACK", "POSITIVE_SCORE_FLOOR_FALLBACK",
    "DUPLICATE_CAP_ETF_FALLBACK", "PARTIAL_STOCK_SLOTS_WITH_ETF_FALLBACK",
    "FULL_STOCK_SLOTS",
})
@dataclass(frozen=True)
class Cap90QcPlan:
    candidate_id: str
    attempt: int
    role: str
    project_name: str
    backtest_name: str
    organization_id: str = field(repr=False)
    projection_sha256: str
    profile_sha256: str
    package_sha256: str
    activation_manifest_sha256: str
    control_directory: Path


def _fail(message: str):
    raise Cap90QcSubmissionError(message)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _client(api: QuantConnectClient) -> None:
    if (
        type(api) is not QuantConnectClient
        or api._base_url != API_BASE
        or api._transport is not _bounded_transport
    ):
        _fail("cap-90 QC client is not the bounded redirect-refusing transport")


def _post(api: QuantConnectClient, endpoint: str, payload: dict) -> dict:
    if endpoint not in {
        "authenticate", "projects/read", "projects/create", "files/read",
        "files/delete", "files/create", "files/update", "compile/create",
        "compile/read", "backtests/create", "backtests/list", "backtests/read",
    }:
        _fail("cap-90 QC endpoint is not allowlisted")
    try:
        response = api.request(endpoint, payload)
    except Exception:
        raise Cap90QcSubmissionError("cap-90 QC " + endpoint + " failed") from None
    if type(response) is not dict or response.get("success") is not True:
        _fail("cap-90 QC " + endpoint + " response changed")
    return response


def preview(plan: Cap90QcPlan, projection: object) -> dict:
    """Validate the exact role, profile, and 13-file source without I/O."""
    if type(plan) is not Cap90QcPlan or (
        type(plan.candidate_id) is not str
        or plan.candidate_id not in _ROLES
        or type(plan.attempt) is not int
        or plan.attempt != 1
        or plan.role != _ROLES[plan.candidate_id]
        or type(plan.project_name) is not str
        or not _SAFE.fullmatch(plan.project_name)
        or len(plan.project_name.encode("ascii")) > 100
        or type(plan.backtest_name) is not str
        or not _SAFE.fullmatch(plan.backtest_name)
        or len(plan.backtest_name.encode("ascii")) > 200
        or type(plan.organization_id) is not str
        or not _ORG.fullmatch(plan.organization_id)
        or not isinstance(plan.control_directory, Path)
        or not plan.control_directory.is_absolute()
        or any(type(value) is not str or not _HEX.fullmatch(value) for value in (
            plan.projection_sha256, plan.profile_sha256,
            plan.package_sha256, plan.activation_manifest_sha256,
        ))
    ):
        _fail("cap-90 plan identity is not an exact A1 role")
    profile = runtime.require_six_universe_order_profile(
        plan.role, variant=runtime.CAP90_VARIANT,
    )
    if type(projection) is not projection_module.AcceptedRiskSixUniverseOrderQcProjection or (
        projection.variant != runtime.CAP90_VARIANT
        or projection.role != plan.role
        or projection.projection_sha256 != plan.projection_sha256
        or projection.profile_id != profile["profile_id"]
        or projection.profile_sha256 != profile["profile_sha256"]
        or projection.profile_sha256 != plan.profile_sha256
        or projection.package_sha256 != plan.package_sha256
        or projection.activation_manifest_sha256 != plan.activation_manifest_sha256
    ):
        _fail("cap-90 source or profile identity changed")
    files = projection.source_files
    if type(files) is not tuple or len(files) != 13:
        _fail("cap-90 projected source inventory changed")
    paths = []
    for item in files:
        path, source = item.project_path, item.source_bytes
        if (
            type(path) is not str or not _PATH.fullmatch(path)
            or ".." in Path(path).parts
            or type(source) is not bytes
            or not 0 < len(source) <= projection_module.MAXIMUM_SOURCE_FILE_BYTES
            or item.byte_count != len(source)
            or hashlib.sha256(source).hexdigest() != item.content_sha256
        ):
            _fail("cap-90 projected file identity changed")
        try:
            source.decode("ascii")
        except UnicodeError:
            _fail("cap-90 projected source is not ASCII")
        paths.append(path)
    if (
        len(set(paths)) != 13 or "main.py" not in paths
        or tuple(paths) != tuple(sorted(paths))
        or sum(item.byte_count for item in files) != projection.total_source_byte_count
        or projection.total_source_byte_count
        + projection_module.MINIMUM_REVIEW_MARGIN_BYTES
        > projection_module.MAXIMUM_TOTAL_SOURCE_BYTES
    ):
        _fail("cap-90 source closure or byte bound changed")
    return {
        "candidate_id": plan.candidate_id,
        "role": plan.role,
        "projection_sha256": plan.projection_sha256,
        "profile_id": profile["profile_id"],
        "profile_sha256": plan.profile_sha256,
        "source_files": tuple((item.project_path, item.content_sha256, item.byte_count) for item in files),
    }


def _control_path(plan: Cap90QcPlan, name: str) -> Path:
    root = plan.control_directory
    try:
        root.mkdir(mode=0o700)
    except FileExistsError:
        pass
    except OSError:
        _fail("cap-90 control directory is unavailable")
    info = root.stat(follow_symlinks=False)
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700 or (
        hasattr(os, "getuid") and info.st_uid != os.getuid()
    ):
        _fail("cap-90 control directory is not private")
    return root / (plan.candidate_id + "-A1-" + name + ".json")


def _write_once(path: Path, value: dict) -> None:
    raw = _canonical(value)
    if len(raw) > 16 * 1024:
        _fail("cap-90 control record is oversized")
    try:
        descriptor = os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600,
        )
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(descriptor)
    except OSError:
        raise Cap90QcSubmissionError("cap-90 one-use control was already spent") from None


def _read_control(path: Path) -> dict:
    try:
        info = path.stat(follow_symlinks=False)
        raw = path.read_bytes()
        value = json.loads(raw.decode("ascii"))
    except (OSError, ValueError, UnicodeError):
        raise Cap90QcSubmissionError("cap-90 control record is unavailable") from None
    if (
        not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
        or not 0 < len(raw) <= 16 * 1024 or type(value) is not dict
        or _canonical(value) != raw
    ):
        _fail("cap-90 control record changed")
    return value


def _project(response: dict, plan: Cap90QcPlan) -> int:
    projects = response.get("projects")
    if type(projects) is not list or len(projects) != 1 or type(projects[0]) is not dict:
        _fail("cap-90 project response changed")
    row = projects[0]
    project_id = row.get("projectId")
    if (
        type(project_id) is not int or project_id <= 0
        or row.get("name") != plan.project_name
        or row.get("organizationId") != plan.organization_id
        or row.get("language") != "Py"
    ):
        _fail("cap-90 project identity changed")
    return project_id


def _launch_matches_plan(plan: Cap90QcPlan, launch: dict) -> None:
    if type(launch) is not dict or (
        launch.get("candidate_id") != plan.candidate_id
        or launch.get("role") != plan.role
        or launch.get("project_name") != plan.project_name
        or launch.get("backtest_name") != plan.backtest_name
        or launch.get("projection_sha256") != plan.projection_sha256
        or launch.get("profile_sha256") != plan.profile_sha256
    ):
        _fail("cap-90 launch and frozen plan identity differ")


def _require_prior_valid_role(plan: Cap90QcPlan) -> None:
    prior = {"R182": "R181", "R183": "R182"}.get(plan.candidate_id)
    if prior is None:
        return
    prior_path = plan.control_directory / (prior + "-A1-result-valid.json")
    prior_result = _read_control(prior_path)
    if (
        prior_result.get("candidate_id") != prior
        or prior_result.get("run_valid") is not True
        or type(prior_result.get("aggregate_sha256")) is not str
        or not _HEX.fullmatch(prior_result["aggregate_sha256"])
    ):
        _fail("cap-90 preceding matched role is not authenticated valid")


def launch_a1(plan: Cap90QcPlan, projection: object, api: QuantConnectClient) -> dict:
    """Claim before mutation; create, byte-check, compile, and launch once."""
    identity = preview(plan, projection)
    _client(api)
    _require_prior_valid_role(plan)
    if _control_path(plan, "claim").exists():
        _fail("cap-90 A1 was already claimed")
    _post(api, "authenticate", {})
    projects = _post(api, "projects/read", {}).get("projects")
    if type(projects) is not list or any(
        type(item) is not dict or item.get("name") == plan.project_name
        for item in projects
    ):
        _fail("cap-90 project name is not fresh")
    _write_once(_control_path(plan, "claim"), identity)
    project_id = _project(_post(api, "projects/create", {
        "name": plan.project_name, "language": "Py", "organizationId": plan.organization_id,
    }), plan)
    verified = _post(api, "projects/read", {"projectId": project_id})
    if _project(verified, plan) != project_id:
        _fail("cap-90 project readback changed")
    project = verified["projects"][0]
    collaborators = project.get("collaborators")
    if (
        project.get("owner") is not True or project.get("codeRunning") is not False
        or type(collaborators) is not list or len(collaborators) > 1
        or any(type(item) is not dict or item.get("owner") is not True for item in collaborators)
    ):
        _fail("cap-90 project is not private and idle")
    initial = _post(api, "files/read", {"projectId": project_id}).get("files")
    if type(initial) is not list or any(
        type(item) is not dict or item.get("name") not in _DEFAULT_FILES
        for item in initial
    ):
        _fail("cap-90 default file inventory changed")
    initial_names = [item["name"] for item in initial]
    if len(initial_names) != len(set(initial_names)):
        _fail("cap-90 duplicate default file")
    if "research.ipynb" in initial_names:
        _post(api, "files/delete", {"projectId": project_id, "name": "research.ipynb"})
    for item in projection.source_files:
        endpoint = "files/update" if item.project_path == "main.py" and "main.py" in initial_names else "files/create"
        _post(api, endpoint, {
            "projectId": project_id, "name": item.project_path,
            "content": item.source_bytes.decode("ascii"),
        })
    readback = _post(api, "files/read", {"projectId": project_id}).get("files")
    if type(readback) is not list or len(readback) != 13:
        _fail("cap-90 uploaded file inventory changed")
    observed = {}
    for item in readback:
        if (
            type(item) is not dict or type(item.get("name")) is not str
            or type(item.get("content")) is not str or item.get("projectId") != project_id
            or item["name"] in observed
        ):
            _fail("cap-90 uploaded file identity changed")
        observed[item["name"]] = item["content"]
    if set(observed) != {item.project_path for item in projection.source_files}:
        _fail("cap-90 uploaded paths changed")
    for item in projection.source_files:
        if observed[item.project_path].encode("ascii") != item.source_bytes:
            _fail("cap-90 uploaded bytes changed")
    started = _post(api, "compile/create", {"projectId": project_id})
    compile_id = started.get("compileId")
    if type(compile_id) is not str or not _ID.fullmatch(compile_id):
        _fail("cap-90 compile identity changed")
    for poll in range(120):
        state = _post(api, "compile/read", {"projectId": project_id, "compileId": compile_id})
        if state.get("compileId") != compile_id or state.get("state") not in {
            "InQueue", "Building", "BuildSuccess", "BuildError",
        }:
            _fail("cap-90 compile state changed")
        if state["state"] in {"BuildSuccess", "BuildError"}:
            break
        if poll < 119:
            time.sleep(2)
    else:
        _fail("cap-90 compile poll exhausted; A1 remains spent")
    if state["state"] == "BuildError":
        _write_once(_control_path(plan, "terminal"), {
            "candidate_id": plan.candidate_id, "status": "BuildError",
            "project_id": project_id, "compile_id": compile_id,
        })
        _fail("cap-90 compile failed; A1 was consumed")
    launched = _post(api, "backtests/create", {
        "projectId": project_id, "compileId": compile_id,
        "backtestName": plan.backtest_name,
    }).get("backtest")
    if type(launched) is not dict or (
        type(launched.get("backtestId")) is not str
        or not _ID.fullmatch(launched["backtestId"])
        or launched.get("projectId") != project_id
        or launched.get("name") != plan.backtest_name
        or launched.get("status") not in {"In Queue...", "In Progress..."}
    ):
        _fail("cap-90 backtest launch identity changed")
    receipt = {
        "candidate_id": plan.candidate_id, "role": plan.role,
        "project_id": project_id, "project_name": plan.project_name,
        "compile_id": compile_id, "backtest_id": launched["backtestId"],
        "backtest_name": plan.backtest_name,
        "projection_sha256": plan.projection_sha256,
        "profile_id": identity["profile_id"], "profile_sha256": plan.profile_sha256,
    }
    _write_once(_control_path(plan, "launch"), receipt)
    return receipt


def poll_status(plan: Cap90QcPlan, launch: dict, api: QuantConnectClient) -> str:
    """Read exact run status only; QC may send unrelated fields, which are ignored."""
    _client(api)
    _launch_matches_plan(plan, launch)
    if _read_control(_control_path(plan, "launch")) != launch:
        _fail("cap-90 launch receipt changed")
    terminal_path = _control_path(plan, "terminal")
    if terminal_path.exists():
        return _read_control(terminal_path)["status"]
    response = _post(api, "backtests/list", {
        "projectId": launch["project_id"], "includeStatistics": False,
    })
    rows = response.get("backtests")
    if type(rows) is not list or response.get("count", len(rows)) != len(rows):
        _fail("cap-90 status inventory changed")
    matches = [item for item in rows if type(item) is dict and item.get("backtestId") == launch["backtest_id"]]
    if len(matches) != 1:
        _fail("cap-90 exact backtest status is absent")
    item = matches[0]
    status = item.get("status")
    if (
        item.get("name") != launch["backtest_name"]
        or ("projectId" in item and item["projectId"] != launch["project_id"])
        or status not in {"In Queue...", "In Progress...", "Completed.", "Runtime Error"}
    ):
        _fail("cap-90 backtest status identity changed")
    if status in {"Completed.", "Runtime Error"}:
        _write_once(terminal_path, {
            "candidate_id": plan.candidate_id, "status": status,
            "project_id": launch["project_id"], "backtest_id": launch["backtest_id"],
        })
    return status


def _statistic(value: object) -> tuple[str, dict]:
    if type(value) is not str:
        _fail("cap-90 custom statistic is not text")
    try:
        raw = value.encode("ascii")
        parsed = json.loads(value)
    except (UnicodeError, ValueError):
        _fail("cap-90 custom statistic is not ASCII JSON")
    if not 0 < len(raw) <= runtime.MAXIMUM_STATISTIC_BYTES or type(parsed) is not dict or _canonical(parsed) != raw:
        _fail("cap-90 custom statistic is not bounded canonical JSON")
    return value, parsed


def _finite_decimal(value: object) -> bool:
    if type(value) is not str or len(value) > 120:
        return False
    try:
        return Decimal(value).is_finite()
    except InvalidOperation:
        return False


def _bounded_counts(value: object, *, maximum: int = 1_000_000,
                    keys: frozenset | None = None) -> bool:
    return type(value) is dict and len(value) <= 24 and all(
        type(key) is str and 0 < len(key) <= 80
        and (keys is None or key in keys)
        and type(count) is int and 0 <= count <= maximum
        for key, count in value.items()
    )


def _project_aggregate(aggregate: dict) -> dict:
    """Retain bounded comparison diagnostics, never arbitrary nested fields."""
    account = aggregate.get("account")
    sleeves = aggregate.get("sleeve_diagnostics")
    execution = aggregate.get("execution")
    forced = aggregate.get("engine_forced_delisting")
    if (
        type(account) is not dict or set(account) != _ACCOUNT_FIELDS
        or account["observation_count"] != runtime.EXPECTED_SESSION_COUNT
        or account["first_observation_session"] != runtime.EVALUATION_START_SESSION
        or account["last_observation_session"] != runtime.EVALUATION_END_SESSION
        or any(not _finite_decimal(account[key]) for key in (
            "starting_equity", "ending_equity", "cumulative_return",
            "maximum_drawdown", "annualized_volatility",
        ))
        or (account["zero_rate_sharpe"] is not None and not _finite_decimal(account["zero_rate_sharpe"]))
        or type(sleeves) is not dict
        or sleeves.get("schema") != "arv2-six-universe-order-sleeve-summary-table-v1"
        or sleeves.get("fields") != list(_SLEEVE_FIELDS)
        or type(sleeves.get("rows")) is not list or len(sleeves["rows"]) != 6
        or type(execution) is not dict
        or execution.get("schema") != "arv2-simulated-moo-executor-summary-v1"
        or execution.get("decision_count") != runtime.EXPECTED_DECISION_COUNT
        or execution.get("raw_order_rows_in_summary") is not False
        or execution.get("raw_security_rows_in_summary") is not False
        or execution.get("backtest_only") is not True
        or execution.get("live_orders") is not False
        or execution.get("paper_orders") is not False
        or execution.get("funded_orders") is not False
        or execution.get("deployment") is not False
        or execution.get("trading") is not False
        or type(forced) is not dict
        or forced.get("schema") != runtime._forced.FORCED_DELISTING_SUMMARY_SCHEMA
        or forced.get("accounting_complete") is not True
        or forced.get("raw_order_rows_in_summary") is not False
        or forced.get("raw_security_rows_in_summary") is not False
    ):
        _fail("cap-90 nested aggregate identity changed")
    clean_rows = []
    for ticker, row in zip(_UNIVERSES, sleeves["rows"]):
        if (
            type(row) is not list or len(row) != len(_SLEEVE_FIELDS)
            or row[0] != ticker or row[1] != ticker
            or row[2] != runtime.EXPECTED_DECISION_COUNT
            or any(type(row[index]) is not int or row[index] < 0 for index in range(2, 8))
            or not _finite_decimal(row[8]) or not _finite_decimal(row[9])
            or not _bounded_counts(row[10], keys=_COVERAGE_REASONS)
            or not _bounded_counts(row[11], keys=_SELECTION_STATUSES)
        ):
            _fail("cap-90 sleeve aggregate shape changed")
        clean_rows.append(row[:10] + [dict(row[10]), dict(row[11])])
    counts = aggregate.get("fallback_counts")
    unavailable = aggregate.get("constituent_collection_unavailable_universe_counts")
    count_keys = (
        "reference_history_call_count", "pit_callback_source_row_count",
        "fundamental_snapshot_unavailable_decision_count",
        "constituent_collection_unavailable_decision_count",
    )
    execution_counts = (
        "submitted_rebalance_count", "completed_rebalance_count",
        "submitted_order_count", "filled_order_count_sum",
        "canceled_order_count_sum", "invalid_order_count_sum",
    )
    execution_amounts = (
        "modeled_fee_amount", "actual_engine_fee_amount", "total_filled_notional",
    )
    if (
        not _bounded_counts(counts, maximum=6 * runtime.EXPECTED_DECISION_COUNT, keys=_SELECTION_STATUSES)
        or sum(counts.values()) != 6 * runtime.EXPECTED_DECISION_COUNT
        or not _bounded_counts(unavailable, maximum=runtime.EXPECTED_DECISION_COUNT, keys=frozenset(_UNIVERSES))
        or set(unavailable) != set(_UNIVERSES)
        or any(type(aggregate.get(key)) is not int or aggregate[key] < 0 for key in count_keys)
        or any(not _finite_decimal(aggregate.get(key)) for key in (
            "mean_gross_exposure", "maximum_gross_exposure",
        ))
        or any(type(execution.get(key)) is not int or execution[key] < 0 for key in execution_counts)
        or any(not _finite_decimal(execution.get(key)) for key in execution_amounts)
        or type(execution.get("run_valid")) is not bool
        or type(execution.get("execution_failure")) is not bool
        or type(forced.get("order_count")) is not int or forced["order_count"] < 0
        or type(forced.get("event_count")) is not int or forced["event_count"] < 0
    ):
        _fail("cap-90 comparison diagnostic shape changed")
    return {
        "schema": aggregate["schema"], "role": aggregate["role"],
        "profile_id": aggregate["profile_id"],
        "profile_sha256": aggregate["profile_sha256"],
        "account": dict(account),
        "mean_gross_exposure": aggregate["mean_gross_exposure"],
        "maximum_gross_exposure": aggregate["maximum_gross_exposure"],
        "fallback_counts": dict(counts),
        "sleeve_diagnostics": {"fields": list(_SLEEVE_FIELDS), "rows": clean_rows},
        "execution": {key: execution[key] for key in (*execution_counts, *execution_amounts, "run_valid", "execution_failure")},
        "engine_forced_delisting": {
            "order_count": forced["order_count"], "event_count": forced["event_count"],
        },
        **{key: aggregate[key] for key in count_keys},
        "constituent_collection_unavailable_universe_counts": dict(unavailable),
        "run_valid": aggregate["run_valid"],
    }


def _attest_uploaded_source(plan: Cap90QcPlan, launch: dict, api: QuantConnectClient) -> None:
    """Recheck current project bytes; historical run-snapshot bytes remain unproven."""
    claim = _read_control(_control_path(plan, "claim"))
    if (
        claim.get("projection_sha256") != launch["projection_sha256"]
        or claim.get("profile_sha256") != launch["profile_sha256"]
        or type(claim.get("source_files")) is not list
        or len(claim["source_files"]) != 13
        or any(
            type(record) is not list or len(record) != 3
            or type(record[0]) is not str or type(record[1]) is not str
            or type(record[2]) is not int
            for record in claim["source_files"]
        )
    ):
        _fail("cap-90 claimed source identity changed")
    files = _post(api, "files/read", {"projectId": launch["project_id"]}).get("files")
    if type(files) is not list or len(files) != 13:
        _fail("cap-90 result-time project source inventory changed")
    observed = {}
    for item in files:
        if (
            type(item) is not dict or item.get("projectId") != launch["project_id"]
            or type(item.get("name")) is not str or type(item.get("content")) is not str
            or item["name"] in observed
        ):
            _fail("cap-90 result-time project source identity changed")
        observed[item["name"]] = item["content"]
    if set(observed) != {record[0] for record in claim["source_files"]}:
        _fail("cap-90 result-time project source paths changed")
    for path, digest, size in claim["source_files"]:
        try:
            raw = observed[path].encode("ascii")
        except UnicodeError:
            _fail("cap-90 result-time source is not ASCII")
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
            _fail("cap-90 result-time source bytes changed")


def read_aggregates_once(plan: Cap90QcPlan, launch: dict, api: QuantConnectClient) -> dict:
    """One read after Completed.; authenticate only META/AGGREGATES."""
    _client(api)
    _launch_matches_plan(plan, launch)
    if _read_control(_control_path(plan, "launch")) != launch:
        _fail("cap-90 launch receipt changed")
    terminal = _read_control(_control_path(plan, "terminal"))
    if terminal != {
        "candidate_id": plan.candidate_id, "status": "Completed.",
        "project_id": launch["project_id"], "backtest_id": launch["backtest_id"],
    }:
        _fail("cap-90 exact run did not complete")
    if _control_path(plan, "result-read-claim").exists():
        _fail("cap-90 result read was already claimed")
    _attest_uploaded_source(plan, launch, api)
    _write_once(_control_path(plan, "result-read-claim"), {
        "candidate_id": plan.candidate_id, "project_id": launch["project_id"],
        "backtest_id": launch["backtest_id"],
    })
    response = _post(api, "backtests/read", {
        "projectId": launch["project_id"], "backtestId": launch["backtest_id"],
    })
    backtest = response.get("backtest")
    if type(backtest) is not dict or (
        backtest.get("projectId") != launch["project_id"]
        or backtest.get("backtestId") != launch["backtest_id"]
        or backtest.get("name") != launch["backtest_name"]
        or backtest.get("status") != "Completed."
    ):
        _fail("cap-90 result identity changed")
    statistics = backtest.get("statistics")
    if type(statistics) is not dict or tuple(sorted(
        key for key in statistics
        if type(key) is str and key.startswith("ARV2_SIX_GATE_ORDER_")
    )) != _CUSTOM:
        _fail("cap-90 custom statistic inventory changed")
    _meta_text, meta = _statistic(statistics[runtime.META_STATISTIC_NAME])
    aggregate_text, aggregate = _statistic(statistics[runtime.AGGREGATES_STATISTIC_NAME])
    if (
        set(meta) != _META_FIELDS
        or set(aggregate) != _AGGREGATE_FIELDS
        or meta.get("schema") != runtime.META_SCHEMA
        or meta.get("role") != plan.role
        or meta.get("profile_id") != launch["profile_id"]
        or meta.get("profile_sha256") != plan.profile_sha256
        or meta.get("package_sha256") != plan.package_sha256
        or meta.get("activation_manifest_sha256") != plan.activation_manifest_sha256
        or type(meta.get("package_id")) is not str
        or not _ID.fullmatch(meta["package_id"])
        or type(meta.get("symbol_resolution_id")) is not str
        or not _ID.fullmatch(meta["symbol_resolution_id"])
        or type(meta.get("symbol_resolution_sha256")) is not str
        or not _HEX.fullmatch(meta["symbol_resolution_sha256"])
        or meta.get("result_transport") != "two_bounded_custom_summary_statistics"
        or meta.get("aggregate_schema") != runtime.CAP90_SUMMARY_SCHEMA
        or meta.get("aggregate_sha256") != hashlib.sha256(aggregate_text.encode("ascii")).hexdigest()
        or meta.get("raw_provider_rows") is not False
        or meta.get("raw_price_rows") is not False
        or meta.get("raw_order_rows") is not False
        or meta.get("backtest_only") is not True
        or meta.get("preliminary") is not True
        or meta.get("formal") is not False
        or meta.get("trading") is not False
        or aggregate.get("schema") != runtime.CAP90_SUMMARY_SCHEMA
        or aggregate.get("role") != plan.role
        or aggregate.get("profile_id") != launch["profile_id"]
        or aggregate.get("profile_sha256") != plan.profile_sha256
        or aggregate.get("backtest_only") is not True
        or aggregate.get("trading") is not False
        or aggregate.get("preliminary") is not True
        or aggregate.get("formal") is not False
        or aggregate.get("live_orders") is not False
        or aggregate.get("paper_orders") is not False
        or aggregate.get("funded_orders") is not False
        or aggregate.get("deployment") is not False
        or type(aggregate.get("run_valid")) is not bool
        or type(aggregate.get("execution")) is not dict
        or type(aggregate["execution"].get("run_valid")) is not bool
        or (aggregate["run_valid"] is True and aggregate["execution"]["run_valid"] is not True)
    ):
        _fail("cap-90 result profile, digest, or safety flag changed")
    selected_aggregate = _project_aggregate(aggregate)
    valid = aggregate["run_valid"] is True
    if valid:
        _write_once(_control_path(plan, "result-valid"), {
            "candidate_id": plan.candidate_id, "run_valid": True,
            "aggregate_sha256": meta["aggregate_sha256"],
        })
    return {"meta": meta, "aggregates": selected_aggregate, "run_valid": valid}


__all__ = (
    "Cap90QcPlan", "Cap90QcSubmissionError", "launch_a1", "poll_status",
    "preview", "production_client", "read_aggregates_once",
)
