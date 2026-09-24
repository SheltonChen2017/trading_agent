"""One-use, host-only QC submission for the exploratory cap-90 order family.

This module never acts on import. A1 creates one private project per role;
the narrowly pinned R181 A2 and final A3 repair that same project in place.
The owner-waived bridge is limited to R181 A3 and R182 A1, with exact source,
predecessor, and one-use controls; R183 retains its detached-signature gate.
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
from . import accepted_risk_six_universe_order_bridge_qc_projection as bridge_projection_module
from . import accepted_risk_six_universe_order_bridge_qc_runtime as bridge_runtime
from .owner_signature_authority import (
    FORMAL_EXECUTION_PURPOSE,
    OwnerSignatureAuthority,
    OwnerSignatureAuthorityError,
    load_formal_execution_owner_signature,
    require_formal_execution_owner_signature,
)
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
_QC_MAXIMUM_FILE_CHARACTERS = 64_000
_LAUNCH_PERMIT_SCHEMA = "arv2-cap90-qc-owner-launch-permit-v1"
_EXPLORATORY_WAIVER_SCHEMA = "arv2-cap90-qc-exact-owner-waiver-v1"
_EXPLORATORY_WAIVER_ID = "ARV2-OWNER-2026-09-24-R181A3-R182-TILT-EXPLORATORY-SIGNATURE-WAIVER"
_R181_A2_PROJECT_ID = 36_891_750
_R181_A2_PROJECT_NAME = "104 ARV2 SIX CAP90 SIGNAL R181 2021 2025"
_R181_A2_PROJECTION_SHA256 = "b68661ec2f90f98eb47e09242b8b9d4cd8ed21101667f355afba0a4a48461c29"
_R181_A2_PROFILE_SHA256 = "d27c558b71d20694e803a244e89f3feb79ba5084971c8d6d8eefa7cf8ecf09f0"
_R181_A2_BACKTEST_ID = "a74626d4d6ce7360ae95d2e1d7930910"
_R181_A2_AGGREGATE_SHA256 = "1376e1096b63e2189b0c44eccd54935391cf0e830ae736fd13b9fa20f604cc78"
_R181_A2_CONTROL_SHA256 = {
    "claim": "e34ff7ac35719104f176cfeb7f2442a23f5971da89c6467197468a297212cbc5",
    "launch": "fd404d384f1d71c1846dc477c0d4365e2d19a815e8fb07519e125e01e0b0e316",
    "terminal": "07801499a69f5de7eb3924fa43784ba3669a5a4b66696e52f32a5cf9471bbcc6",
    "result-read-claim": "6c6f816a9e8c78d812f6dff0c71142868aafa1ed7a13cfd11ef6a316c7dcb001",
    "invalid-order-diagnostic-v4-claim": "f74617c047ec53e9f8e0e277b70d19681ba15f2e39eb15118331c80f48f41f8d",
    "invalid-order-diagnostic-v4-result": "bb20244ea0b2b9b3af673f601aeb80a2c4236ee452e0548adfbb8a5ce50fbf9e",
    "buying-power-timing-v5-claim": "8aa59ec0f993e1482628b40b37a64bb2d3d129ae2046f5bd15c5b365bbdd13e3",
    "buying-power-timing-v5-result": "7b5dc5a699e88ae3496d0024c566c03f96d5057dd9e2f1377dd5b19f4e33d53f",
}
_R181_A3_PROJECTION_SHA256 = "f75725c37cb5e66f7db4070fcf89a05d5efe29cda60b6fc75086615d622cce0d"
_R182_BRIDGE_PROJECTION_SHA256 = "186cb2bb3dbd2a37358c9c0b2dbfa86e1e685203dba33795eb192f74faa9feeb"
_R181_A3_PROFILE_SHA256 = "9e1b93c3fc5fca0cd3154f8c8270fd10cdb2acc67742e9712aafb5682fbed031"
_R182_BRIDGE_PROFILE_SHA256 = "b419d3f2b149a1509ef09bd0a5bf607bea8c25a3363cbc8a9dc04a40910f9c0c"
_R181_A1_PROJECTION_SHA256 = "947fd40922e2503a118e54bde8c0475cd9504fa0d2d212ccdc40e36f6fc72dc0"
_R181_A1_CLAIM_SHA256 = "bcef1a218cd15cd22b9f470b5cdbba9e08b3bb555b74edfd09c5a961329983ff"
_R181_A1_FAILED_RUNTIME = (1, "334359b90efed75da5f0ada1d5e6b256f4a6bd0aee7eb39c0f90182a021ffc8b")
_R181_A1_DEFAULT_MAIN = (406, "215476644fd846a1488ca4c45876ed21c9c736faa79b31a59fcaaa1643aac608")
_R181_A2_RUNTIME = (56_398, "66cbc2966972467d3d38511e541c984d3932ad1dca2bcf05ccf69830307349b1")
_R181_RUNTIME_PATH = "accepted_risk_six_universe_order_qc_runtime.py"
_R181_TARGETS_PATH = "accepted_risk_six_universe_order_targets.py"
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
_BRIDGE_AGGREGATE_FIELDS = _AGGREGATE_FIELDS | frozenset({
    "admission_leverage", "target_gross_exposure", "minimum_end_day_cash",
    "daily_cash_nonnegative", "order_event_cash_observation_count",
    "minimum_observed_order_event_cash", "order_event_cash_nonnegative",
    "cash_observation_granularity", "end_day_gross_at_most_one",
    "target_tracking_valid", "maximum_mean_target_weight_l1_error",
    "maximum_single_target_weight_l1_error",
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


def _preview_exact(
    plan: Cap90QcPlan, projection: object, *, attempt: int, bridge: bool = False,
) -> dict:
    """Validate one exact attempt's role, profile, and projected source."""
    if type(plan) is not Cap90QcPlan or (
        type(plan.candidate_id) is not str
        or plan.candidate_id not in _ROLES
        or type(plan.attempt) is not int
        or plan.attempt != attempt
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
        _fail("cap-90 plan identity is not an exact attempt role")
    profile = (
        bridge_runtime.require_bridge_profile(plan.role)
        if bridge else runtime.require_six_universe_order_profile(
            plan.role, variant=runtime.CAP90_VARIANT,
        )
    )
    expected_variant = bridge_runtime.BRIDGE_VARIANT if bridge else runtime.CAP90_VARIANT
    expected_schema = (
        bridge_projection_module.PROJECTION_SCHEMA if bridge
        else projection_module.CAP90_PROJECTION_SCHEMA
    )
    expected_file_count = 14 if bridge else 13
    if type(projection) is not projection_module.AcceptedRiskSixUniverseOrderQcProjection or (
        projection.schema != expected_schema
        or projection.variant != expected_variant
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
    if type(files) is not tuple or len(files) != expected_file_count:
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
        if len(source) > _QC_MAXIMUM_FILE_CHARACTERS:
            _fail("cap-90 projected source exceeds QC's 64000-character file cap")
        paths.append(path)
    if (
        len(set(paths)) != expected_file_count or "main.py" not in paths
        or (bridge and bridge_projection_module.BRIDGE_RUNTIME_PATH not in paths)
        or tuple(paths) != tuple(sorted(paths))
        or sum(item.byte_count for item in files) != projection.total_source_byte_count
        or projection.total_source_byte_count
        + projection_module.MINIMUM_REVIEW_MARGIN_BYTES
        > projection_module.MAXIMUM_TOTAL_SOURCE_BYTES
    ):
        _fail("cap-90 source closure or byte bound changed")
    if bridge:
        record = projection.to_record()
        semantic = {
            key: value for key, value in record.items()
            if key not in ("projection_id", "projection_sha256")
        }
        actual_digest = hashlib.sha256(_canonical(semantic)).hexdigest()
        if (
            actual_digest != plan.projection_sha256
            or projection.projection_id != (
                "arv2-six-universe-order-bridge-qc-projection-"
                + actual_digest[:24]
            )
        ):
            _fail("cap-90 bridge source manifest is not self-authenticating")
    return {
        "candidate_id": plan.candidate_id,
        "role": plan.role,
        "projection_sha256": plan.projection_sha256,
        "profile_id": profile["profile_id"],
        "profile_sha256": plan.profile_sha256,
        "source_files": tuple((item.project_path, item.content_sha256, item.byte_count) for item in files),
    }


def preview(plan: Cap90QcPlan, projection: object) -> dict:
    """Validate the original A1 source without I/O."""
    return _preview_exact(plan, projection, attempt=1)


def preview_a2(plan: Cap90QcPlan, projection: object) -> dict:
    """Bind only R181's diagnosed in-place 64,000-character repair."""
    identity = _preview_exact(plan, projection, attempt=2)
    if (
        plan.candidate_id != "R181"
        or plan.project_name != _R181_A2_PROJECT_NAME
        or plan.projection_sha256 != _R181_A2_PROJECTION_SHA256
        or plan.backtest_name != (
            "ARV2 R181A2 six cap90 signal 2021 2025 "
            + _R181_A2_PROJECTION_SHA256[:8]
        )
    ):
        _fail("cap-90 R181 A2 correction is not the frozen source and run")
    return identity


def preview_bridge(plan: Cap90QcPlan, projection: object) -> dict:
    """Admit only the separately pinned bridge source for R181 A3 or R182 A1."""
    if type(plan) is not Cap90QcPlan or (
        plan.candidate_id, plan.attempt
    ) not in {("R181", 3), ("R182", 1)}:
        _fail("cap-90 bridge attempt is not R181 A3 or R182 A1")
    identity = _preview_exact(plan, projection, attempt=plan.attempt, bridge=True)
    expected_sha = (
        _R181_A3_PROJECTION_SHA256 if plan.candidate_id == "R181"
        else _R182_BRIDGE_PROJECTION_SHA256
    )
    expected_profile_sha = (
        _R181_A3_PROFILE_SHA256 if plan.candidate_id == "R181"
        else _R182_BRIDGE_PROFILE_SHA256
    )
    expected_project_name = (
        _R181_A2_PROJECT_NAME if plan.candidate_id == "R181"
        else "105 ARV2 SIX CAP90 MATCHED R182 2021 2025"
    )
    backtest_prefix = (
        "ARV2 R181A3 six cap90 bridge signal 2021 2025 "
        if plan.candidate_id == "R181" else
        "ARV2 R182A1 six cap90 bridge matched 2021 2025 "
    )
    if (
        type(expected_sha) is not str or not _HEX.fullmatch(expected_sha)
        or type(expected_profile_sha) is not str
        or not _HEX.fullmatch(expected_profile_sha)
        or plan.projection_sha256 != expected_sha
        or plan.profile_sha256 != expected_profile_sha
        or plan.project_name != expected_project_name
        or plan.backtest_name != backtest_prefix + expected_sha[:8]
    ):
        _fail("cap-90 bridge source, project, or run is not the frozen candidate")
    return identity


def render_owner_launch_permit(plan: Cap90QcPlan, projection: object) -> bytes:
    """Render the exact exploratory launch bytes for the owner's detached signature.

    The existing formal-QC execution signature namespace is used only as a
    cryptographic verifier. This distinct schema and exact payload cannot be
    substituted for any formal-run authority receipt.
    """
    if type(plan) is not Cap90QcPlan:
        _fail("cap-90 signed launch plan type changed")
    if plan.attempt == 1:
        identity = (
            preview_bridge(plan, projection) if plan.candidate_id == "R182"
            else preview(plan, projection)
        )
        project_id = None
        mutations = {
            "projects/create": 1, "files/delete": 1,
            "files/create": len(identity["source_files"]), "files/update": 1,
            "compile/create": 1, "backtests/create": 1,
        }
    elif plan.attempt == 2:
        identity = preview_a2(plan, projection)
        project_id = _R181_A2_PROJECT_ID
        mutations = {
            "files/create": 1, "files/update": 2,
            "compile/create": 1, "backtests/create": 1,
        }
    elif plan.attempt == 3:
        identity = preview_bridge(plan, projection)
        project_id = _R181_A2_PROJECT_ID
        mutations = {
            "files/create": 1, "files/update": 1,
            "compile/create": 1, "backtests/create": 1,
        }
    else:
        _fail("cap-90 signed launch attempt is unsupported")
    return _canonical({
        "schema": _LAUNCH_PERMIT_SCHEMA,
        "signature_purpose": FORMAL_EXECUTION_PURPOSE,
        "action": "one_private_exploratory_order_backtest_launch",
        "candidate_id": plan.candidate_id,
        "attempt": plan.attempt,
        "role": plan.role,
        "organization_id_sha256": hashlib.sha256(plan.organization_id.encode("ascii")).hexdigest(),
        "project_id": project_id,
        "project_name": plan.project_name,
        "backtest_name": plan.backtest_name,
        "control_directory": str(plan.control_directory),
        "projection_sha256": plan.projection_sha256,
        "profile_id": identity["profile_id"],
        "profile_sha256": plan.profile_sha256,
        "package_sha256": plan.package_sha256,
        "activation_manifest_sha256": plan.activation_manifest_sha256,
        "source_files_sha256": hashlib.sha256(_canonical(identity["source_files"])).hexdigest(),
        "mutating_endpoint_budget": mutations,
        "maximum_backtest_submissions": 1,
        "result_read_authorized": False,
        "raw_provider_rows_authorized": False,
        "raw_logs_orders_charts_authorized": False,
        "paper_live_deployment_funded_trading_authorized": False,
    })


def load_owner_launch_permit(
    plan: Cap90QcPlan, projection: object, *,
    allowed_signers_path: Path, signature_path: Path,
) -> OwnerSignatureAuthority:
    """Verify owner-controlled files against the rendered exact launch bytes."""
    payload = render_owner_launch_permit(plan, projection)
    try:
        return load_formal_execution_owner_signature(
            authority_payload=payload,
            allowed_signers_path=allowed_signers_path,
            signature_path=signature_path,
        )
    except OwnerSignatureAuthorityError as exc:
        raise Cap90QcSubmissionError("cap-90 owner launch signature is unavailable") from exc


def _require_owner_launch_permit(
    plan: Cap90QcPlan, projection: object,
    owner_signature: OwnerSignatureAuthority | None,
) -> dict:
    payload = render_owner_launch_permit(plan, projection)
    try:
        verified = require_formal_execution_owner_signature(
            owner_signature, authority_payload=payload,
        )
    except OwnerSignatureAuthorityError as exc:
        raise Cap90QcSubmissionError("cap-90 owner launch signature is unavailable") from exc
    if (
        verified.purpose != FORMAL_EXECUTION_PURPOSE
        or verified.authority_payload_sha256 != hashlib.sha256(payload).hexdigest()
        or type(verified.authority_sha256) is not str
        or not _HEX.fullmatch(verified.authority_sha256)
        or type(verified.signature_sha256) is not str
        or not _HEX.fullmatch(verified.signature_sha256)
    ):
        _fail("cap-90 owner launch signature identity changed")
    return {
        "owner_signature_authority_sha256": verified.authority_sha256,
        "owner_signature_sha256": verified.signature_sha256,
        "owner_signed_payload_sha256": verified.authority_payload_sha256,
    }


def _launch_authority(
    plan: Cap90QcPlan, projection: object, *,
    owner_signature: OwnerSignatureAuthority | None,
    owner_waiver_id: str | None,
) -> dict:
    """Bind the owner's narrow exploratory waiver or require a real signature."""
    if owner_waiver_id is None:
        return _require_owner_launch_permit(plan, projection, owner_signature)
    if (
        owner_signature is not None
        or type(owner_waiver_id) is not str
        or owner_waiver_id != _EXPLORATORY_WAIVER_ID
        or (plan.candidate_id, plan.attempt) not in {("R181", 3), ("R182", 1)}
    ):
        _fail("cap-90 owner exploratory waiver does not cover this launch")
    payload = render_owner_launch_permit(plan, projection)
    return {
        "owner_launch_authority_mode": "exact_exploratory_signature_waiver",
        "owner_launch_waiver_schema": _EXPLORATORY_WAIVER_SCHEMA,
        "owner_launch_waiver_id": _EXPLORATORY_WAIVER_ID,
        "owner_waived_payload_sha256": hashlib.sha256(payload).hexdigest(),
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
    if type(plan.attempt) is not int or plan.attempt not in (1, 2, 3) or (
        plan.attempt == 3 and plan.candidate_id != "R181"
    ):
        _fail("cap-90 attempt control path is unsupported")
    return root / (plan.candidate_id + "-A" + str(plan.attempt) + "-" + name + ".json")


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
        or (plan.attempt in (2, 3) and launch.get("attempt") != plan.attempt)
    ):
        _fail("cap-90 launch and frozen plan identity differ")


def _require_prior_valid_role(plan: Cap90QcPlan) -> None:
    prior = {"R182": "R181", "R183": "R182"}.get(plan.candidate_id)
    if prior is None:
        return
    # R181 A2 completed but was invalid. Only the prospectively corrected A3
    # may unlock the matched bridge role; an A2 receipt never does so.
    prior_attempt = 3 if prior == "R181" else 1
    prior_path = plan.control_directory / (prior + "-A" + str(prior_attempt) + "-result-valid.json")
    prior_result = _read_control(prior_path)
    if (
        prior_result.get("candidate_id") != prior
        or prior_result.get("run_valid") is not True
        or type(prior_result.get("aggregate_sha256")) is not str
        or not _HEX.fullmatch(prior_result["aggregate_sha256"])
        or (prior == "R181" and (
            prior_result.get("attempt") != 3
            or prior_result.get("projection_sha256") != _R181_A3_PROJECTION_SHA256
            or prior_result.get("profile_sha256") != _R181_A3_PROFILE_SHA256
            or prior_result.get("project_id") != _R181_A2_PROJECT_ID
        ))
        or (prior == "R182" and (
            prior_result.get("projection_sha256") != _R182_BRIDGE_PROJECTION_SHA256
            or prior_result.get("profile_sha256") != _R182_BRIDGE_PROFILE_SHA256
        ))
    ):
        _fail("cap-90 preceding matched role is not authenticated valid")
    if prior == "R181":
        root = plan.control_directory
        claim = _read_control(root / "R181-A3-claim.json")
        launch = _read_control(root / "R181-A3-launch.json")
        terminal = _read_control(root / "R181-A3-terminal.json")
        result_read = _read_control(root / "R181-A3-result-read-claim.json")
        if (
            claim.get("candidate_id") != "R181"
            or claim.get("attempt") != 3
            or claim.get("role") != "signal"
            or claim.get("project_id") != _R181_A2_PROJECT_ID
            or claim.get("projection_sha256") != _R181_A3_PROJECTION_SHA256
            or claim.get("profile_sha256") != _R181_A3_PROFILE_SHA256
            or type(claim.get("source_files")) is not list
            or len(claim["source_files"]) != 14
            or claim.get("a2_control_sha256") != _R181_A2_CONTROL_SHA256
            or launch.get("candidate_id") != "R181"
            or launch.get("attempt") != 3
            or launch.get("project_id") != _R181_A2_PROJECT_ID
            or launch.get("projection_sha256") != _R181_A3_PROJECTION_SHA256
            or launch.get("profile_sha256") != _R181_A3_PROFILE_SHA256
            or launch.get("backtest_id") != prior_result.get("backtest_id")
            or terminal != {
                "candidate_id": "R181", "status": "Completed.",
                "project_id": _R181_A2_PROJECT_ID,
                "backtest_id": launch.get("backtest_id"),
            }
            or result_read != {
                "candidate_id": "R181", "project_id": _R181_A2_PROJECT_ID,
                "backtest_id": launch.get("backtest_id"),
            }
        ):
            _fail("cap-90 R181 A3 predecessor chain changed")


def _r181_a2_invalid_receipts(plan: Cap90QcPlan) -> dict:
    """Authenticate spent A2 and its count-only invalid-order diagnosis."""
    if plan.candidate_id != "R181" or plan.attempt != 3:
        _fail("cap-90 A2 predecessor check is only for R181 A3")
    _control_path(plan, "claim")
    root = plan.control_directory
    receipts = {}
    for name, expected_sha in _R181_A2_CONTROL_SHA256.items():
        path = root / ("R181-A2-" + name + ".json")
        record = _read_control(path)
        if hashlib.sha256(_canonical(record)).hexdigest() != expected_sha:
            _fail("cap-90 R181 A2 predecessor receipt bytes changed")
        receipts[name] = record
    if (root / "R181-A2-result-valid.json").exists():
        _fail("cap-90 R181 A2 is not a valid predecessor")
    claim = receipts["claim"]
    launch = receipts["launch"]
    terminal = receipts["terminal"]
    result_read = receipts["result-read-claim"]
    v4_claim = receipts["invalid-order-diagnostic-v4-claim"]
    v4_result = receipts["invalid-order-diagnostic-v4-result"]
    v5_claim = receipts["buying-power-timing-v5-claim"]
    v5_result = receipts["buying-power-timing-v5-result"]
    if (
        claim.get("candidate_id") != "R181"
        or claim.get("attempt") != 2
        or claim.get("project_id") != _R181_A2_PROJECT_ID
        or claim.get("projection_sha256") != _R181_A2_PROJECTION_SHA256
        or claim.get("profile_sha256") != _R181_A2_PROFILE_SHA256
        or type(claim.get("source_files")) is not list
        or len(claim["source_files"]) != 13
        or launch.get("candidate_id") != "R181"
        or launch.get("attempt") != 2
        or launch.get("project_id") != _R181_A2_PROJECT_ID
        or launch.get("backtest_id") != _R181_A2_BACKTEST_ID
        or launch.get("projection_sha256") != _R181_A2_PROJECTION_SHA256
        or launch.get("profile_sha256") != _R181_A2_PROFILE_SHA256
        or terminal != {
            "candidate_id": "R181", "status": "Completed.",
            "project_id": _R181_A2_PROJECT_ID,
            "backtest_id": _R181_A2_BACKTEST_ID,
        }
        or result_read != {
            "candidate_id": "R181", "project_id": _R181_A2_PROJECT_ID,
            "backtest_id": _R181_A2_BACKTEST_ID,
        }
        or any(
            record.get("aggregate_sha256") != _R181_A2_AGGREGATE_SHA256
            or record.get("backtest_id") != _R181_A2_BACKTEST_ID
            or record.get("project_id") != _R181_A2_PROJECT_ID
            or record.get("profile_sha256") != _R181_A2_PROFILE_SHA256
            or record.get("raw_order_values_retained") is not False
            for record in (v4_claim, v5_claim)
        )
        or v4_result.get("schema") != "arv2-r181-a2-redacted-order-reasons-v4"
        or v4_result.get("filled_order_count") != 6267
        or v4_result.get("invalid_order_count") != 22
        or v4_result.get("reason_counts", {}).get("INSUFFICIENT_BUYING_POWER") != 22
        or v5_result.get("schema") != "arv2-r181-a2-buying-power-timing-v5"
        or v5_result.get("filled_order_count") != 6267
        or v5_result.get("invalid_order_count") != 22
        or v5_result.get("direction_counts") != {"BUY": 22, "SELL": 0, "UNKNOWN": 0}
        or v5_result.get("time_bin_counts") != {
            "PRE_OPEN": 22, "AT_OR_AFTER_OPEN": 0, "UNKNOWN": 0,
        }
        or v5_claim.get("v4_claim_sha256") != _R181_A2_CONTROL_SHA256["invalid-order-diagnostic-v4-claim"]
        or v5_claim.get("v4_result_sha256") != _R181_A2_CONTROL_SHA256["invalid-order-diagnostic-v4-result"]
    ):
        _fail("cap-90 R181 A2 invalid predecessor identity changed")
    return claim


def _r181_a1_claim(plan: Cap90QcPlan, projection: object) -> dict:
    """Reconcile A2 against the exact locally spent A1 claim, not a caller story."""
    path = plan.control_directory / "R181-A1-claim.json"
    try:
        raw = path.read_bytes()
    except OSError:
        _fail("cap-90 R181 A1 claim is unavailable")
    if hashlib.sha256(raw).hexdigest() != _R181_A1_CLAIM_SHA256:
        _fail("cap-90 R181 A1 claim bytes changed")
    claim = _read_control(path)
    old_files = claim.get("source_files")
    if (
        claim.get("candidate_id") != "R181"
        or claim.get("role") != "signal"
        or claim.get("projection_sha256") != _R181_A1_PROJECTION_SHA256
        or claim.get("profile_sha256") != plan.profile_sha256
        or claim.get("profile_id") != projection.profile_id
        or type(old_files) is not list or len(old_files) != 13
        or any(type(row) is not list or len(row) != 3 for row in old_files)
    ):
        _fail("cap-90 R181 A1 claim identity changed")
    old = {row[0]: (row[2], row[1]) for row in old_files}
    new = {item.project_path: (item.byte_count, item.content_sha256) for item in projection.source_files}
    if (
        len(old) != 13 or set(old) != set(new)
        or old[_R181_RUNTIME_PATH] != (67_316, "84e4d69135ff13f592e071574d22b30255088f4df22bd11f33943c652d81a46a")
        or new[_R181_RUNTIME_PATH] != _R181_A2_RUNTIME
        or any(new[path] != prior for path, prior in old.items() if path != _R181_RUNTIME_PATH)
    ):
        _fail("cap-90 R181 A2 changes more than the diagnosed runtime projection")
    for name in ("launch", "terminal", "result-read-claim", "result-valid"):
        if (plan.control_directory / ("R181-A1-" + name + ".json")).exists():
            _fail("cap-90 R181 A1 already progressed beyond the diagnosed upload failure")
    return old


def _r181_residual_files(response: dict, old: dict) -> None:
    """Authenticate all 12 A1 residue files, including the 1-byte failure."""
    files = response.get("files")
    if type(files) is not list or len(files) != 12:
        _fail("cap-90 R181 A1 residual file inventory changed")
    seen = set()
    for item in files:
        if (
            type(item) is not dict
            or item.get("projectId") != _R181_A2_PROJECT_ID
            or type(item.get("name")) is not str
            or type(item.get("content")) is not str
            or item["name"] in seen
        ):
            _fail("cap-90 R181 A1 residual file identity changed")
        path = item["name"]
        seen.add(path)
        try:
            raw = item["content"].encode("ascii")
        except UnicodeError:
            _fail("cap-90 R181 A1 residual file is not ASCII")
        expected = (
            _R181_A1_FAILED_RUNTIME if path == _R181_RUNTIME_PATH
            else _R181_A1_DEFAULT_MAIN if path == "main.py"
            else old.get(path)
        )
        if expected is None or (len(raw), hashlib.sha256(raw).hexdigest()) != expected:
            _fail("cap-90 R181 A1 residual file bytes changed")
    if seen != set(old) - {_R181_TARGETS_PATH}:
        _fail("cap-90 R181 A1 residual paths changed")


def _r181_a2_uploaded_files(response: dict, claim: dict) -> dict:
    """Compare current cloud source with every A2 claimed file before A3 mutation."""
    expected = claim["source_files"]
    if any(
        type(row) is not list or len(row) != 3
        or type(row[0]) is not str or not _PATH.fullmatch(row[0])
        or type(row[1]) is not str or not _HEX.fullmatch(row[1])
        or type(row[2]) is not int or row[2] <= 0
        for row in expected
    ):
        _fail("cap-90 R181 A2 claimed source inventory changed")
    old = {path: (digest, size) for path, digest, size in expected}
    files = response.get("files")
    if len(old) != 13 or type(files) is not list or len(files) != 13:
        _fail("cap-90 R181 A2 current file inventory changed")
    seen = set()
    for item in files:
        if (
            type(item) is not dict
            or item.get("projectId") != _R181_A2_PROJECT_ID
            or type(item.get("name")) is not str
            or type(item.get("content")) is not str
            or item["name"] in seen or item["name"] not in old
        ):
            _fail("cap-90 R181 A2 current file identity changed")
        seen.add(item["name"])
        try:
            raw = item["content"].encode("ascii")
        except UnicodeError:
            _fail("cap-90 R181 A2 current source is not ASCII")
        if (hashlib.sha256(raw).hexdigest(), len(raw)) != old[item["name"]]:
            _fail("cap-90 R181 A2 current source bytes changed")
    if seen != set(old):
        _fail("cap-90 R181 A2 current source paths changed")
    return old


def launch_r181_a3(
    plan: Cap90QcPlan, projection: object, api: QuantConnectClient, *,
    owner_signature: OwnerSignatureAuthority | None = None,
    owner_waiver_id: str | None = None,
) -> dict:
    """Spend the final R181 attempt only in A2's exact private project."""
    identity = preview_bridge(plan, projection)
    authority = _launch_authority(
        plan, projection, owner_signature=owner_signature,
        owner_waiver_id=owner_waiver_id,
    )
    _client(api)
    if _control_path(plan, "claim").exists():
        _fail("cap-90 R181 A3 final attempt was already claimed")
    a2_claim = _r181_a2_invalid_receipts(plan)
    source = {item.project_path: item.source_bytes.decode("ascii") for item in projection.source_files}
    old = {path: (digest, size) for path, digest, size in a2_claim["source_files"]}
    added = set(source) - set(old)
    changed = {
        path for path in set(source) & set(old)
        if (hashlib.sha256(source[path].encode("ascii")).hexdigest(), len(source[path])) != old[path]
    }
    if (
        set(old) - set(source)
        or added != {bridge_projection_module.BRIDGE_RUNTIME_PATH}
        or changed != {"main.py"}
    ):
        _fail("cap-90 R181 A3 changes more than main and the admission bridge")
    _post(api, "authenticate", {})
    verified = _post(api, "projects/read", {"projectId": _R181_A2_PROJECT_ID})
    if _project(verified, plan) != _R181_A2_PROJECT_ID:
        _fail("cap-90 R181 A3 existing project identity changed")
    project = verified["projects"][0]
    collaborators = project.get("collaborators")
    if (
        project.get("owner") is not True or project.get("codeRunning") is not False
        or type(collaborators) is not list or len(collaborators) > 1
        or any(type(item) is not dict or item.get("owner") is not True for item in collaborators)
    ):
        _fail("cap-90 R181 A3 project is not private and idle")
    listing = _post(api, "backtests/list", {
        "projectId": _R181_A2_PROJECT_ID, "includeStatistics": False,
    })
    rows = listing.get("backtests")
    if (
        type(rows) is not list or len(rows) != 1 or listing.get("count") != 1
        or type(rows[0]) is not dict
        or rows[0].get("backtestId") != _R181_A2_BACKTEST_ID
        or rows[0].get("name") != "ARV2 R181A2 six cap90 signal 2021 2025 b68661ec"
        or rows[0].get("status") != "Completed."
        or ("projectId" in rows[0] and rows[0]["projectId"] != _R181_A2_PROJECT_ID)
    ):
        _fail("cap-90 R181 A3 project has an unexpected backtest census")
    _r181_a2_uploaded_files(
        _post(api, "files/read", {"projectId": _R181_A2_PROJECT_ID}), a2_claim,
    )
    _write_once(_control_path(plan, "claim"), {
        **identity, **authority, "attempt": 3,
        "project_id": _R181_A2_PROJECT_ID,
        "a2_control_sha256": dict(_R181_A2_CONTROL_SHA256),
        "a2_invalid_order_count": 22,
    })
    _post(api, "files/update", {
        "projectId": _R181_A2_PROJECT_ID, "name": "main.py", "content": source["main.py"],
    })
    _post(api, "files/create", {
        "projectId": _R181_A2_PROJECT_ID,
        "name": bridge_projection_module.BRIDGE_RUNTIME_PATH,
        "content": source[bridge_projection_module.BRIDGE_RUNTIME_PATH],
    })
    readback = _post(api, "files/read", {"projectId": _R181_A2_PROJECT_ID}).get("files")
    if type(readback) is not list or len(readback) != 14:
        _fail("cap-90 R181 A3 uploaded file inventory changed")
    observed = {}
    for item in readback:
        if (
            type(item) is not dict or item.get("projectId") != _R181_A2_PROJECT_ID
            or type(item.get("name")) is not str or type(item.get("content")) is not str
            or item["name"] in observed
        ):
            _fail("cap-90 R181 A3 uploaded file identity changed")
        observed[item["name"]] = item["content"]
    if set(observed) != set(source):
        _fail("cap-90 R181 A3 uploaded paths changed")
    for item in projection.source_files:
        try:
            raw = observed[item.project_path].encode("ascii")
        except UnicodeError:
            _fail("cap-90 R181 A3 uploaded source is not ASCII")
        if raw != item.source_bytes:
            _fail("cap-90 R181 A3 uploaded source bytes changed")
    started = _post(api, "compile/create", {"projectId": _R181_A2_PROJECT_ID})
    compile_id = started.get("compileId")
    if type(compile_id) is not str or not _ID.fullmatch(compile_id):
        _fail("cap-90 R181 A3 compile identity changed")
    for poll in range(120):
        state = _post(api, "compile/read", {
            "projectId": _R181_A2_PROJECT_ID, "compileId": compile_id,
        })
        if state.get("compileId") != compile_id or state.get("state") not in {
            "InQueue", "Building", "BuildSuccess", "BuildError",
        }:
            _fail("cap-90 R181 A3 compile state changed")
        if state["state"] in {"BuildSuccess", "BuildError"}:
            break
        if poll < 119:
            time.sleep(2)
    else:
        _fail("cap-90 R181 A3 compile poll exhausted; final attempt remains spent")
    if state["state"] == "BuildError":
        _write_once(_control_path(plan, "terminal"), {
            "candidate_id": "R181", "status": "BuildError",
            "project_id": _R181_A2_PROJECT_ID, "compile_id": compile_id,
        })
        _fail("cap-90 R181 A3 compile failed; final attempt was consumed")
    launched = _post(api, "backtests/create", {
        "projectId": _R181_A2_PROJECT_ID, "compileId": compile_id,
        "backtestName": plan.backtest_name,
    }).get("backtest")
    if type(launched) is not dict or (
        type(launched.get("backtestId")) is not str
        or not _ID.fullmatch(launched["backtestId"])
        or launched.get("projectId") != _R181_A2_PROJECT_ID
        or launched.get("name") != plan.backtest_name
        or launched.get("status") not in {"In Queue...", "In Progress..."}
    ):
        _fail("cap-90 R181 A3 backtest launch identity changed")
    receipt = {
        "candidate_id": "R181", "attempt": 3, "role": "signal", **authority,
        "project_id": _R181_A2_PROJECT_ID, "project_name": plan.project_name,
        "compile_id": compile_id, "backtest_id": launched["backtestId"],
        "backtest_name": plan.backtest_name,
        "projection_sha256": plan.projection_sha256,
        "profile_id": identity["profile_id"], "profile_sha256": plan.profile_sha256,
    }
    _write_once(_control_path(plan, "launch"), receipt)
    return receipt


def launch_r181_a2(
    plan: Cap90QcPlan, projection: object, api: QuantConnectClient, *,
    owner_signature: OwnerSignatureAuthority | None = None,
) -> dict:
    """One-use in-place A2: exact A1 residue, repair, byte-check, compile, run."""
    identity = preview_a2(plan, projection)
    signature = _require_owner_launch_permit(plan, projection, owner_signature)
    _client(api)
    if _control_path(plan, "claim").exists():
        _fail("cap-90 R181 A2 was already claimed")
    old = _r181_a1_claim(plan, projection)
    _post(api, "authenticate", {})
    verified = _post(api, "projects/read", {"projectId": _R181_A2_PROJECT_ID})
    if _project(verified, plan) != _R181_A2_PROJECT_ID:
        _fail("cap-90 R181 A2 existing project identity changed")
    project = verified["projects"][0]
    collaborators = project.get("collaborators")
    if (
        project.get("owner") is not True or project.get("codeRunning") is not False
        or type(collaborators) is not list or len(collaborators) > 1
        or any(type(item) is not dict or item.get("owner") is not True for item in collaborators)
    ):
        _fail("cap-90 R181 A2 project is not private and idle")
    listing = _post(api, "backtests/list", {
        "projectId": _R181_A2_PROJECT_ID, "includeStatistics": False,
    })
    if listing.get("backtests") != [] or listing.get("count") != 0:
        _fail("cap-90 R181 A2 project has an unexpected prior backtest")
    _r181_residual_files(_post(api, "files/read", {
        "projectId": _R181_A2_PROJECT_ID,
    }), old)
    _write_once(_control_path(plan, "claim"), {
        **identity,
        **signature,
        "attempt": 2,
        "project_id": _R181_A2_PROJECT_ID,
        "a1_claim_sha256": _R181_A1_CLAIM_SHA256,
    })
    source = {item.project_path: item.source_bytes.decode("ascii") for item in projection.source_files}
    _post(api, "files/update", {
        "projectId": _R181_A2_PROJECT_ID, "name": _R181_RUNTIME_PATH,
        "content": source[_R181_RUNTIME_PATH],
    })
    _post(api, "files/create", {
        "projectId": _R181_A2_PROJECT_ID, "name": _R181_TARGETS_PATH,
        "content": source[_R181_TARGETS_PATH],
    })
    _post(api, "files/update", {
        "projectId": _R181_A2_PROJECT_ID, "name": "main.py",
        "content": source["main.py"],
    })
    readback = _post(api, "files/read", {"projectId": _R181_A2_PROJECT_ID}).get("files")
    if type(readback) is not list or len(readback) != 13:
        _fail("cap-90 R181 A2 uploaded file inventory changed")
    observed = {}
    for item in readback:
        if (
            type(item) is not dict or item.get("projectId") != _R181_A2_PROJECT_ID
            or type(item.get("name")) is not str or type(item.get("content")) is not str
            or item["name"] in observed
        ):
            _fail("cap-90 R181 A2 uploaded file identity changed")
        observed[item["name"]] = item["content"]
    if set(observed) != set(source):
        _fail("cap-90 R181 A2 uploaded paths changed")
    for item in projection.source_files:
        try:
            raw = observed[item.project_path].encode("ascii")
        except UnicodeError:
            _fail("cap-90 R181 A2 uploaded source is not ASCII")
        if raw != item.source_bytes:
            _fail("cap-90 R181 A2 uploaded source bytes changed")
    started = _post(api, "compile/create", {"projectId": _R181_A2_PROJECT_ID})
    compile_id = started.get("compileId")
    if type(compile_id) is not str or not _ID.fullmatch(compile_id):
        _fail("cap-90 R181 A2 compile identity changed")
    for poll in range(120):
        state = _post(api, "compile/read", {
            "projectId": _R181_A2_PROJECT_ID, "compileId": compile_id,
        })
        if state.get("compileId") != compile_id or state.get("state") not in {
            "InQueue", "Building", "BuildSuccess", "BuildError",
        }:
            _fail("cap-90 R181 A2 compile state changed")
        if state["state"] in {"BuildSuccess", "BuildError"}:
            break
        if poll < 119:
            time.sleep(2)
    else:
        _fail("cap-90 R181 A2 compile poll exhausted; attempt remains spent")
    if state["state"] == "BuildError":
        _write_once(_control_path(plan, "terminal"), {
            "candidate_id": "R181", "status": "BuildError",
            "project_id": _R181_A2_PROJECT_ID, "compile_id": compile_id,
        })
        _fail("cap-90 R181 A2 compile failed; attempt was consumed")
    launched = _post(api, "backtests/create", {
        "projectId": _R181_A2_PROJECT_ID, "compileId": compile_id,
        "backtestName": plan.backtest_name,
    }).get("backtest")
    if type(launched) is not dict or (
        type(launched.get("backtestId")) is not str
        or not _ID.fullmatch(launched["backtestId"])
        or launched.get("projectId") != _R181_A2_PROJECT_ID
        or launched.get("name") != plan.backtest_name
        or launched.get("status") not in {"In Queue...", "In Progress..."}
    ):
        _fail("cap-90 R181 A2 backtest launch identity changed")
    receipt = {
        "candidate_id": "R181", "attempt": 2, "role": "signal",
        **signature,
        "project_id": _R181_A2_PROJECT_ID, "project_name": plan.project_name,
        "compile_id": compile_id, "backtest_id": launched["backtestId"],
        "backtest_name": plan.backtest_name,
        "projection_sha256": plan.projection_sha256,
        "profile_id": identity["profile_id"], "profile_sha256": plan.profile_sha256,
    }
    _write_once(_control_path(plan, "launch"), receipt)
    return receipt


def launch_a1(
    plan: Cap90QcPlan, projection: object, api: QuantConnectClient, *,
    owner_signature: OwnerSignatureAuthority | None = None,
    owner_waiver_id: str | None = None,
) -> dict:
    """Claim before mutation; create, byte-check, compile, and launch once."""
    identity = (
        preview_bridge(plan, projection) if plan.candidate_id == "R182"
        else preview(plan, projection)
    )
    _require_prior_valid_role(plan)
    authority = _launch_authority(
        plan, projection, owner_signature=owner_signature,
        owner_waiver_id=owner_waiver_id,
    )
    _client(api)
    if _control_path(plan, "claim").exists():
        _fail("cap-90 A1 was already claimed")
    _post(api, "authenticate", {})
    projects = _post(api, "projects/read", {}).get("projects")
    if type(projects) is not list or any(
        type(item) is not dict or item.get("name") == plan.project_name
        for item in projects
    ):
        _fail("cap-90 project name is not fresh")
    _write_once(_control_path(plan, "claim"), {**identity, **authority})
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
    if type(readback) is not list or len(readback) != len(projection.source_files):
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
        **authority,
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


def _project_aggregate(aggregate: dict, *, bridge: bool = False) -> dict:
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
    bridge_fields = {}
    if bridge:
        mean_error = execution.get("mean_target_weight_l1_error")
        maximum_error = execution.get("maximum_target_weight_l1_error")
        minimum_cash = aggregate.get("minimum_end_day_cash")
        event_count = aggregate.get("order_event_cash_observation_count")
        event_minimum = aggregate.get("minimum_observed_order_event_cash")
        if (
            aggregate.get("admission_leverage") != "2"
            or aggregate.get("target_gross_exposure") != "0.98"
            or aggregate.get("maximum_mean_target_weight_l1_error") != "0.02"
            or aggregate.get("maximum_single_target_weight_l1_error") != "0.05"
            or not _finite_decimal(minimum_cash)
            or not _finite_decimal(mean_error)
            or not _finite_decimal(maximum_error)
            or Decimal(minimum_cash) < 0
            or type(event_count) is not int or event_count < 0
            or (event_count == 0 and event_minimum is not None)
            or (event_count > 0 and (
                not _finite_decimal(event_minimum)
                or Decimal(event_minimum) < 0
            ))
            or Decimal(mean_error) < 0
            or Decimal(maximum_error) < 0
            or aggregate.get("daily_cash_nonnegative") is not True
            or aggregate.get("order_event_cash_nonnegative") is not True
            or aggregate.get("cash_observation_granularity") != (
                "daily_close_and_post_order_event_not_continuous_intraday"
            )
            or aggregate.get("end_day_gross_at_most_one") is not (
                Decimal(aggregate["maximum_gross_exposure"]) <= Decimal("1")
            )
            or aggregate.get("target_tracking_valid") is not (
                Decimal(mean_error) <= Decimal("0.02")
                and Decimal(maximum_error) <= Decimal("0.05")
            )
            or (aggregate.get("run_valid") is True and (
                aggregate.get("target_tracking_valid") is not True
                or aggregate.get("end_day_gross_at_most_one") is not True
                or execution.get("run_valid") is not True
                or execution.get("invalid_order_count_sum") != 0
                or execution.get("canceled_order_count_sum") != 0
                or execution.get("filled_order_count_sum") != execution.get("submitted_order_count")
            ))
        ):
            _fail("cap-90 bridge cash, exposure, or target tracking changed")
        bridge_fields = {
            "admission_leverage": "2", "target_gross_exposure": "0.98",
            "minimum_end_day_cash": minimum_cash,
            "daily_cash_nonnegative": aggregate["daily_cash_nonnegative"],
            "order_event_cash_observation_count": event_count,
            "minimum_observed_order_event_cash": event_minimum,
            "order_event_cash_nonnegative": aggregate["order_event_cash_nonnegative"],
            "cash_observation_granularity": aggregate["cash_observation_granularity"],
            "end_day_gross_at_most_one": aggregate["end_day_gross_at_most_one"],
            "target_tracking_valid": aggregate["target_tracking_valid"],
            "mean_target_weight_l1_error": mean_error,
            "maximum_target_weight_l1_error": maximum_error,
        }
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
        **bridge_fields,
    }


def _attest_uploaded_source(plan: Cap90QcPlan, launch: dict, api: QuantConnectClient) -> None:
    """Recheck current project bytes; historical run-snapshot bytes remain unproven."""
    claim = _read_control(_control_path(plan, "claim"))
    expected_file_count = 14 if (
        plan.candidate_id, plan.attempt
    ) in {("R181", 3), ("R182", 1)} else 13
    if (
        claim.get("projection_sha256") != launch["projection_sha256"]
        or claim.get("profile_sha256") != launch["profile_sha256"]
        or type(claim.get("source_files")) is not list
        or len(claim["source_files"]) != expected_file_count
        or any(
            type(record) is not list or len(record) != 3
            or type(record[0]) is not str or type(record[1]) is not str
            or type(record[2]) is not int
            for record in claim["source_files"]
        )
    ):
        _fail("cap-90 claimed source identity changed")
    if expected_file_count == 14:
        authority_keys = (
            "owner_launch_authority_mode", "owner_launch_waiver_schema",
            "owner_launch_waiver_id", "owner_waived_payload_sha256",
        )
        if any(claim.get(key) != launch.get(key) for key in authority_keys) or (
            launch.get("owner_launch_authority_mode") == "exact_exploratory_signature_waiver"
            and (
                launch.get("owner_launch_waiver_schema") != _EXPLORATORY_WAIVER_SCHEMA
                or launch.get("owner_launch_waiver_id") != _EXPLORATORY_WAIVER_ID
                or type(launch.get("owner_waived_payload_sha256")) is not str
                or not _HEX.fullmatch(launch["owner_waived_payload_sha256"])
            )
        ):
            _fail("cap-90 bridge launch waiver identity changed")
    files = _post(api, "files/read", {"projectId": launch["project_id"]}).get("files")
    if type(files) is not list or len(files) != expected_file_count:
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
    bridge_run = (plan.candidate_id, plan.attempt) in {
        ("R181", 3), ("R182", 1),
    }
    summary_schema = (
        bridge_runtime.BRIDGE_SUMMARY_SCHEMA if bridge_run
        else runtime.CAP90_SUMMARY_SCHEMA
    )
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
        or set(aggregate) != (
            _BRIDGE_AGGREGATE_FIELDS if bridge_run else _AGGREGATE_FIELDS
        )
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
        or meta.get("aggregate_schema") != summary_schema
        or meta.get("aggregate_sha256") != hashlib.sha256(aggregate_text.encode("ascii")).hexdigest()
        or meta.get("raw_provider_rows") is not False
        or meta.get("raw_price_rows") is not False
        or meta.get("raw_order_rows") is not False
        or meta.get("backtest_only") is not True
        or meta.get("preliminary") is not True
        or meta.get("formal") is not False
        or meta.get("trading") is not False
        or aggregate.get("schema") != summary_schema
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
    selected_aggregate = _project_aggregate(aggregate, bridge=bridge_run)
    valid = aggregate["run_valid"] is True
    if valid:
        valid_receipt = {
            "candidate_id": plan.candidate_id, "run_valid": True,
            "aggregate_sha256": meta["aggregate_sha256"],
        }
        if bridge_run:
            valid_receipt.update({
                "attempt": plan.attempt,
                "projection_sha256": plan.projection_sha256,
                "profile_sha256": plan.profile_sha256,
                "project_id": launch["project_id"],
                "backtest_id": launch["backtest_id"],
            })
        elif plan.attempt == 2:
            valid_receipt.update({
                "attempt": 2, "projection_sha256": plan.projection_sha256,
            })
        _write_once(_control_path(plan, "result-valid"), valid_receipt)
    return {"meta": meta, "aggregates": selected_aggregate, "run_valid": valid}


__all__ = (
    "Cap90QcPlan", "Cap90QcSubmissionError", "launch_a1", "launch_r181_a2",
    "launch_r181_a3", "preview_bridge",
    "load_owner_launch_permit", "poll_status", "preview", "preview_a2",
    "production_client", "render_owner_launch_permit",
    "read_aggregates_once",
)
