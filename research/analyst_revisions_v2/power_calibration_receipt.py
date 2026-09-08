"""Fail-closed ARV2-4D-B nuisance-calibration receipt boundary.

The checked-in contract authenticated here describes two input *content*
formats.  It grants no right to read either input.  A separate, exact,
content-addressed owner-authority record must bind the already authenticated
B2 manifest candidate before this module will open the two files.  The only
result is a closed nuisance receipt; outcome evaluation and every QC,
deployment, order, and trading action remain outside this module.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import threading
import weakref
from datetime import datetime, timezone
from decimal import (
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    ROUND_HALF_EVEN,
    localcontext,
)
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from .artifact_io import (
    ArtifactIOError,
    read_stable_regular as _read_artifact_stable_regular,
    _register_process_local_after_fork,
    revalidate_regular as _revalidate_artifact_regular,
)
from .four_family_multiplicity import (
    FourFamilyMultiplicityError,
    FourFamilyMultiplicityOverlay,
    OVERLAY_ARTIFACT_SHA256,
    require_loaded_four_family_multiplicity_overlay,
)
from .power_calibration_input_manifest import (
    ADMISSION_CONTRACT_ARTIFACT_SHA256,
    B1_SCHEMA_HASH,
    B1_SCHEMA_ID,
    FOUR_FAMILY_OVERLAY_HASH,
    FOUR_FAMILY_OVERLAY_ID,
    PowerCalibrationInputManifestError,
    PowerCalibrationManifestAdmission,
    ProductionCalibrationInputManifestCandidate,
    require_loaded_power_calibration_manifest_admission,
    require_loaded_production_calibration_input_manifest_candidate,
)
from .power_calibration_input_schema import (
    CALIBRATION_AXIS_SHA256,
    CALIBRATION_SESSION_COUNT,
    INPUT_ROLES,
    INPUT_SCHEMAS,
    POWER_PROTOCOL_ARTIFACT_SHA256,
    POWER_PROTOCOL_HASH,
    POWER_PROTOCOL_ID,
    SCHEMA_CONTRACT_ARTIFACT_SHA256,
    PowerCalibrationInputSchema,
    PowerCalibrationInputSchemaError,
    require_loaded_power_calibration_input_schema,
)
from .power_calibration_protocol import (
    HAC_MAX_LAG,
    MINIMUM_ABSOLUTE_FLOOR,
    PowerCalibrationProtocol,
    PowerCalibrationProtocolError,
    ProvisionalPowerDisposition,
    derive_provisional_power_requirement,
    require_loaded_power_calibration_protocol,
)


class PowerCalibrationReceiptError(ValueError):
    """The B input contract, authority, input, or receipt is invalid."""


CONTENT_CONTRACT_SCHEMA = (
    "arv2-stock-power-calibration-input-content-contract-structural-v1"
)
CONTENT_CONTRACT_STATUS = "offline_candidate_pending_independent_review"
CONTENT_CONTRACT_AUTHORITY = (
    "input_shape_and_closed_computation_only_no_input_rights_outcome_qc_"
    "deployment_or_trading_authority"
)
CONTENT_CONTRACT_ID_PREFIX = "arv2-stock-power-calibration-input-content-"
# Patched to the exact rendered artifact hash when the structural JSON is frozen.
CONTENT_CONTRACT_ARTIFACT_SHA256 = (
    "12d2724ab657721ad889810c96ec92fdfca73c3ec5c759f41ecf23966da9270a"
)

ADMISSION_CONTRACT_ID = (
    "arv2-stock-power-calibration-manifest-admission-ed654e3289185180"
)
ADMISSION_CONTRACT_HASH = (
    "ed654e32891851806af318ba7baf88f7f5b7ee3a151cecf07b126792755e670c"
)

BETA_INPUT_SCHEMA = INPUT_SCHEMAS[INPUT_ROLES[0]]
COMPONENT_INPUT_SCHEMA = INPUT_SCHEMAS[INPUT_ROLES[1]]
BETA_INPUT_ROOT_FIELDS = ("schema", "records")
BETA_RECORD_FIELDS = ("decision_session", "state", "beta_value")
COMPONENT_INPUT_ROOT_FIELDS = ("schema", "records")
COMPONENT_RECORD_FIELDS = ("decision_session", "connected_component_count")
BETA_STATES = ("valid", "missing", "refused")
MAX_INPUT_ARTIFACT_BYTES = 4 * 1024 * 1024
MAX_DECIMAL_TEXT_BYTES = 128

INPUT_AUTHORITY_SCHEMA = "arv2-power-calibration-input-authority-v1"
INPUT_AUTHORITY_STATUS = "owner_authorized_for_exact_manifest_inputs"
INPUT_AUTHORITY_SCOPE = (
    "exact_input_read_nuisance_compute_and_closed_numeric_receipt_only"
)
INPUT_AUTHORITY_ID_PREFIX = "arv2-power-calibration-input-authority-"
# The owner operation record is also exact-review pinned.  Caller-chosen
# provenance strings never grant access by themselves.
PRODUCTION_INPUT_AUTHORITY_ARTIFACT_SHA256: str | None = None

PRODUCTION_TRUTH_APPROVAL_SCHEMA = (
    "arv2-power-calibration-production-truth-approval-v1"
)
PRODUCTION_TRUTH_APPROVAL_STATUS = (
    "independently_reviewed_exact_production_truth_approval"
)
PRODUCTION_TRUTH_APPROVAL_AUTHORITY = (
    "exact_data_truth_aggregate_only_no_operation_outcome_qc_launch_"
    "deployment_or_trading_authority"
)
PRODUCTION_TRUTH_APPROVAL_ID_PREFIX = (
    "arv2-power-calibration-production-truth-approval-"
)
# Deliberately null in the committed scaffold.  Independent review must freeze
# one exact aggregate artifact before any production authority can be loaded.
PRODUCTION_TRUTH_APPROVAL_ARTIFACT_SHA256: str | None = None
# A pinned aggregate is not a substitute for opening and semantically checking
# its underlying production evidence.  This remains false until that bounded
# evidence opener is independently implemented and reviewed.
PRODUCTION_TRUTH_EVIDENCE_OPENER_IMPLEMENTED = False
PRODUCTION_TRUTH_CLAIMS = (
    "production_authorized",
    "rights_authorized",
    "vintage_proven",
    "input_artifacts_authenticated",
    "entitlement_truth_authenticated",
    "production_lineage_complete",
)
PRODUCTION_TRUTH_APPROVAL_FIELDS = (
    "schema",
    "status",
    "authority",
    "approval_id",
    "approval_hash",
    "production_manifest_binding",
    "evidence_bundle_binding",
    "authenticated_truth_claims",
    "reviewed_evidence_bindings",
    "independent_review_binding",
    "capabilities",
)
INDEPENDENT_REVIEW_BINDING_FIELDS = (
    "review_id",
    "review_evidence_sha256",
    "reviewed_at_utc",
)

RECEIPT_SCHEMA = "arv2-stock-power-calibration-numeric-receipt-v1"
RECEIPT_STATUS = "computed_candidate_pending_independent_review"
RECEIPT_AUTHORITY = (
    "numeric_power_floor_evidence_only_no_outcome_qc_launch_deployment_or_"
    "trading_authority"
)
RECEIPT_ID_PREFIX = "arv2-stock-power-calibration-receipt-"

_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,191}\Z")
_UTC_INSTANT = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z\Z"
)
_CANONICAL_DECIMAL = re.compile(
    r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?\Z"
)

_NO_ACTION_CAPABILITIES = MappingProxyType(
    {
        "input_access": False,
        "source_access": False,
        "outcome_access": False,
        "nuisance_calibration_compute": False,
        "authoritative_power_receipt": False,
        "power_plan_binding": False,
        "qc_upload": False,
        "qc_compile": False,
        "qc_launch": False,
        "result_disposition": False,
        "paper_deployment": False,
        "funded_deployment": False,
        "orders": False,
    }
)
_AUTHORITY_OPERATIONS = MappingProxyType(
    {
        "calibration_input_read": True,
        "nuisance_calibration_compute": True,
        "closed_numeric_receipt_compute": True,
        "source_provider_read": False,
        "outcome_read": False,
        "qc_upload": False,
        "qc_compile": False,
        "qc_launch": False,
        "result_disposition": False,
        "paper_deployment": False,
        "funded_deployment": False,
        "orders": False,
    }
)

ALLOWED_NUMERIC_RECEIPT_OUTPUTS = (
    "valid_beta_date_count",
    "lag_pair_counts_0_through_20",
    "long_run_variance",
    "component_count_census_sha256",
    "component_count_census_session_count",
    "q05_components_per_date",
    "raw_required_valid_dates",
    "required_valid_dates",
    "required_connected_components",
    "fixed_capacity_disposition",
)
REQUIRED_RECEIPT_FIELDS = (
    "protocol_id",
    "protocol_hash",
    "calibration_input_manifest_sha256",
    *ALLOWED_NUMERIC_RECEIPT_OUTPUTS,
)
RECEIPT_IDENTITY_FIELDS = (
    "schema",
    "status",
    "authority",
    "receipt_id",
    "receipt_hash",
    "required_receipt_fields",
    "content_contract_binding",
    "input_authority_binding",
    "production_manifest_binding",
    "evidence_bundle_binding",
    "input_artifact_bindings",
)
RECEIPT_ROOT_FIELDS = RECEIPT_IDENTITY_FIELDS


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise PowerCalibrationReceiptError("noncanonical JSON value") from exc


def _render(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise PowerCalibrationReceiptError("noncanonical JSON value") from exc


def _binding(
    *, artifact_id: str, content_sha256: str, artifact_sha256: str
) -> dict[str, str]:
    return {
        "artifact_id": artifact_id,
        "content_sha256": content_sha256,
        "artifact_sha256": artifact_sha256,
    }


def _content_identity(
    raw: Mapping[str, Any], *, id_field: str, hash_field: str, prefix: str
) -> dict[str, Any]:
    value = dict(raw)
    value[id_field] = None
    value[hash_field] = None
    digest = hashlib.sha256(_canonical(value)).hexdigest()
    value[hash_field] = digest
    value[id_field] = prefix + digest[:16]
    return value


def _contract_document() -> dict[str, Any]:
    raw: dict[str, Any] = {
        "schema": CONTENT_CONTRACT_SCHEMA,
        "status": CONTENT_CONTRACT_STATUS,
        "authority": CONTENT_CONTRACT_AUTHORITY,
        "content_contract_id": None,
        "content_contract_hash": None,
        "bound_accepted_parents": {
            "power_protocol": _binding(
                artifact_id=POWER_PROTOCOL_ID,
                content_sha256=POWER_PROTOCOL_HASH,
                artifact_sha256=POWER_PROTOCOL_ARTIFACT_SHA256,
            ),
            "input_manifest_schema": _binding(
                artifact_id=B1_SCHEMA_ID,
                content_sha256=B1_SCHEMA_HASH,
                artifact_sha256=SCHEMA_CONTRACT_ARTIFACT_SHA256,
            ),
            "production_manifest_admission": _binding(
                artifact_id=ADMISSION_CONTRACT_ID,
                content_sha256=ADMISSION_CONTRACT_HASH,
                artifact_sha256=ADMISSION_CONTRACT_ARTIFACT_SHA256,
            ),
            "four_family_overlay": _binding(
                artifact_id=FOUR_FAMILY_OVERLAY_ID,
                content_sha256=FOUR_FAMILY_OVERLAY_HASH,
                artifact_sha256=OVERLAY_ARTIFACT_SHA256,
            ),
        },
        "input_content": {
            "maximum_bytes_each": MAX_INPUT_ARTIFACT_BYTES,
            "exact_sorted_indented_utf8_json_with_one_trailing_newline": True,
            "duplicate_keys_binary_floats_and_nonfinite_constants_forbidden": True,
            "date_beta": {
                "schema": BETA_INPUT_SCHEMA,
                "root_fields": list(BETA_INPUT_ROOT_FIELDS),
                "record_fields": list(BETA_RECORD_FIELDS),
                "record_count": CALIBRATION_SESSION_COUNT,
                "session_axis_sha256": CALIBRATION_AXIS_SHA256,
                "states": list(BETA_STATES),
                "valid_beta_value": "canonical_finite_Decimal_string",
                "missing_or_refused_beta_value": None,
                "missing_gaps_are_preserved": True,
            },
            "component_count": {
                "schema": COMPONENT_INPUT_SCHEMA,
                "root_fields": list(COMPONENT_INPUT_ROOT_FIELDS),
                "record_fields": list(COMPONENT_RECORD_FIELDS),
                "record_count": CALIBRATION_SESSION_COUNT,
                "session_axis_sha256": CALIBRATION_AXIS_SHA256,
                "connected_component_count": "exact_nonnegative_integer_not_bool",
                "all_sessions_including_zero_counts_required": True,
            },
            "content_sha256": "sha256_compact_sorted_canonical_JSON",
            "artifact_sha256": "sha256_exact_rendered_bytes",
            "manifest_byte_count_and_all_state_count_inventories_must_match": True,
        },
        "calculation": {
            "valid_beta_date_minimum": MINIMUM_ABSOLUTE_FLOOR,
            "maximum_lag_sessions": HAC_MAX_LAG,
            "missing_gap_rule": "exact_axis_positions_never_compressed_or_zero_filled",
            "centering": "transient_stable_sum_valid_betas_divided_by_N",
            "autocovariance": "stable_sum_valid_exact_lag_products_divided_by_N",
            "lag_pair_requirement": "at_least_one_pair_at_every_lag_0_through_20",
            "bartlett_weight": "(21-lag)/21_for_lags_1_through_20",
            "long_run_variance": "gamma_0_plus_2_times_stable_sum_weighted_gamma_1_through_20",
            "stable_sum_order": "ascending_absolute_value_then_signed_value",
            "decimal_context": {
                "precision": 50,
                "rounding": "ROUND_HALF_EVEN",
                "Emin": -999999,
                "Emax": 999999,
                "capitals": 1,
                "clamp": 0,
                "flags_cleared": True,
                "traps": ["InvalidOperation", "DivisionByZero", "Overflow"],
            },
            "planning_arithmetic": "delegated_to_authenticated_ARV2_4D_A_public_helper",
        },
        "receipt": {
            "schema": RECEIPT_SCHEMA,
            "required_receipt_fields": list(REQUIRED_RECEIPT_FIELDS),
            "closed_numeric_output_fields": list(ALLOWED_NUMERIC_RECEIPT_OUTPUTS),
            "required_receipt_fields_are_one_exact_nested_mapping": True,
            "identity_bindings_only_besides_closed_outputs": True,
            "date_betas_mean_centered_values_covariances_returns_outcomes_p_values_and_results": "FORBIDDEN",
        },
        "authority_boundary": {
            "input_authority_schema": INPUT_AUTHORITY_SCHEMA,
            "checked_in_contract_grants_input_rights": False,
            "exact_manifest_evidence_and_input_bindings_required": True,
            "input_authority_is_separate_content_addressed_regular_file": True,
            "B2_structural_candidate_or_owner_strings_authenticate_data_truth": False,
            "production_truth_approval_schema": PRODUCTION_TRUTH_APPROVAL_SCHEMA,
            "production_truth_approval_is_separately_reviewed_and_exactly_pinned": True,
            "production_truth_evidence_opener_implemented": False,
            "truth_aggregate_pin_alone_grants_access": False,
            "committed_production_truth_approval_artifact_sha256": None,
            "input_operation_authority_is_exactly_review_pinned": True,
            "committed_input_operation_authority_artifact_sha256": None,
            "caller_rendered_owner_provenance_grants_access": False,
            "required_positive_production_truth_claims": list(
                PRODUCTION_TRUTH_CLAIMS
            ),
            "external_signed_truth_aggregate_permitted": True,
            "receipt_is_not_outcome_evaluation_or_launch_authority": True,
        },
        "external_bindings": {
            "owner_input_authority_id": None,
            "owner_input_authority_evidence_sha256": None,
            "owner_input_authority_artifact_sha256": None,
            "production_truth_approval_artifact_sha256": None,
            "numeric_receipt_sha256": None,
            "stock_successor_v3_sha256": None,
            "outcome_artifact_sha256": None,
            "qc_project_id": None,
            "qc_run_id": None,
            "evaluation_receipt_id": None,
        },
        "capabilities": dict(_NO_ACTION_CAPABILITIES),
    }
    return _content_identity(
        raw,
        id_field="content_contract_id",
        hash_field="content_contract_hash",
        prefix=CONTENT_CONTRACT_ID_PREFIX,
    )


def _reject_float(value: str) -> None:
    del value
    raise PowerCalibrationReceiptError("binary floating-point is forbidden")


def _reject_constant(value: str) -> None:
    del value
    raise PowerCalibrationReceiptError("non-finite JSON is forbidden")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise PowerCalibrationReceiptError("duplicate JSON key is forbidden")
        value[key] = item
    return value


def _read_stable_regular(
    path: Path, name: str, *, maximum_bytes: int = MAX_INPUT_ARTIFACT_BYTES
) -> tuple[Path, bytes]:
    try:
        return _read_artifact_stable_regular(
            Path(path), name=name, maximum_bytes=maximum_bytes
        )
    except ArtifactIOError as exc:
        raise PowerCalibrationReceiptError(str(exc)) from exc


def _revalidate(
    path: Path,
    payload: bytes,
    name: str,
    *,
    maximum_bytes: int = MAX_INPUT_ARTIFACT_BYTES,
) -> None:
    try:
        _revalidate_artifact_regular(
            path, payload, name=name, maximum_bytes=maximum_bytes
        )
    except ArtifactIOError as exc:
        raise PowerCalibrationReceiptError(str(exc)) from exc


def _parse_status(payload: bytes) -> tuple[str | None, dict[str, Any] | None]:
    """Return parsed content or a non-sensitive refusal status, never an error."""
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return "not_utf8", None
    try:
        raw = json.loads(
            text,
            object_pairs_hook=_object,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except PowerCalibrationReceiptError as exc:
        # Callback messages are closed constants; return only that text after
        # the payload-bearing JSON stack has unwound.
        return str(exc), None
    except (json.JSONDecodeError, ValueError, RecursionError):
        return "not_strict_json", None
    if type(raw) is not dict:
        return "root_not_object", None
    try:
        canonical = _render(raw)
    except PowerCalibrationReceiptError:
        return "not_strict_json", None
    if payload != canonical:
        return "not_canonical", None
    return None, raw


def _parse(payload: bytes, name: str) -> dict[str, Any]:
    status, raw = _parse_status(payload)
    # Do not retain the opaque bytes in the traceback frame used for a domain
    # refusal.  Decoder/parser exceptions have already unwound in the helper.
    del payload
    if status is None and raw is not None:
        return raw
    if status == "not_utf8":
        raise PowerCalibrationReceiptError(f"{name} is not UTF-8")
    if status == "not_strict_json":
        raise PowerCalibrationReceiptError(f"{name} is not strict JSON")
    if status == "root_not_object":
        raise PowerCalibrationReceiptError(f"{name} root must be an object")
    if status == "not_canonical":
        raise PowerCalibrationReceiptError(f"{name} bytes are not canonical")
    if status in {
        "binary floating-point is forbidden",
        "non-finite JSON is forbidden",
        "duplicate JSON key is forbidden",
    }:
        raise PowerCalibrationReceiptError(status)
    raise PowerCalibrationReceiptError(f"{name} is not strict JSON")


def _require_keys(value: object, fields: Iterable[str], name: str) -> dict[str, Any]:
    expected = tuple(fields)
    if type(value) is not dict or set(value) != set(expected) or len(value) != len(expected):
        raise PowerCalibrationReceiptError(f"{name} fields changed")
    return value


def _require_identifier(value: object, name: str) -> str:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        raise PowerCalibrationReceiptError(f"{name} is invalid")
    return value


def _require_sha256(value: object, name: str) -> str:
    if type(value) is not str or _HEX_64.fullmatch(value) is None:
        raise PowerCalibrationReceiptError(f"{name} must be lowercase SHA-256")
    return value


def _require_instant(value: object, name: str) -> str:
    if type(value) is not str or _UTC_INSTANT.fullmatch(value) is None:
        raise PowerCalibrationReceiptError(f"{name} is not canonical UTC")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise PowerCalibrationReceiptError(f"{name} is not a real UTC instant") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value:
        raise PowerCalibrationReceiptError(f"{name} is not canonical UTC")
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if type(value) is MappingProxyType:
        return {key: _thaw(item) for key, item in value.items()}
    if type(value) is tuple:
        return [_thaw(item) for item in value]
    return value


def _fingerprint(value: object) -> object:
    if type(value) is MappingProxyType:
        if any(type(key) is not str for key in value):
            raise PowerCalibrationReceiptError(
                "authority state contains a noncanonical mapping key"
            )
        return (
            "mapping",
            tuple(
                sorted(
                    (key, _fingerprint(item)) for key, item in value.items()
                )
            ),
        )
    if type(value) is tuple:
        return ("tuple", tuple(_fingerprint(item) for item in value))
    if type(value) is str:
        return ("str", value)
    if type(value) is bool:
        return ("bool", value)
    if type(value) is int:
        return ("int", value)
    if type(value) is Decimal:
        return ("decimal", value.as_tuple())
    if isinstance(value, ProvisionalPowerDisposition):
        return ("disposition", value.value)
    if value is None:
        return ("none", None)
    raise PowerCalibrationReceiptError("authority state contains a noncanonical value")


@dataclasses.dataclass(frozen=True, init=False)
class PowerCalibrationInputContentContract:
    content_contract_id: str
    content_contract_hash: str
    calibration_session_axis: tuple[str, ...]
    definition: Mapping[str, Any]
    capabilities: Mapping[str, bool]
    _authority: object = dataclasses.field(repr=False, compare=False)

    def __init__(self) -> None:
        raise TypeError("input-content contracts must be loader-authenticated")

    @property
    def input_access_available(self) -> bool:
        return False

    @property
    def outcome_access_available(self) -> bool:
        return False

    @property
    def qc_action_available(self) -> bool:
        return False


@dataclasses.dataclass(frozen=True, init=False)
class PowerCalibrationInputAuthority:
    authority_id: str
    authority_hash: str
    owner_authorization_id: str
    owner_authorization_evidence_sha256: str
    authorized_at_utc: str
    manifest_id: str
    production_truth_approval_id: str
    production_truth_approval_hash: str
    production_truth_approval_artifact_sha256: str
    definition: Mapping[str, Any]
    _authority: object = dataclasses.field(repr=False, compare=False)

    def __init__(self) -> None:
        raise TypeError("input authorities must be loaded from exact bytes")

    @property
    def input_read_authorized(self) -> bool:
        require_loaded_power_calibration_input_authority(self)
        return True

    @property
    def nuisance_compute_authorized(self) -> bool:
        require_loaded_power_calibration_input_authority(self)
        return True

    @property
    def closed_receipt_compute_authorized(self) -> bool:
        require_loaded_power_calibration_input_authority(self)
        return True

    @property
    def production_authorized(self) -> bool:
        return _authenticated_truth_claim(self, "production_authorized")

    @property
    def rights_authorized(self) -> bool:
        return _authenticated_truth_claim(self, "rights_authorized")

    @property
    def vintage_proven(self) -> bool:
        return _authenticated_truth_claim(self, "vintage_proven")

    @property
    def input_artifacts_authenticated(self) -> bool:
        return _authenticated_truth_claim(self, "input_artifacts_authenticated")

    @property
    def entitlement_truth_authenticated(self) -> bool:
        return _authenticated_truth_claim(self, "entitlement_truth_authenticated")

    @property
    def production_lineage_complete(self) -> bool:
        return _authenticated_truth_claim(self, "production_lineage_complete")

    @property
    def outcome_access_available(self) -> bool:
        return False

    @property
    def qc_action_available(self) -> bool:
        return False


@dataclasses.dataclass(frozen=True, init=False)
class PowerCalibrationReceipt:
    receipt_id: str
    receipt_hash: str
    protocol_id: str
    protocol_hash: str
    content_contract_id: str
    content_contract_hash: str
    manifest_id: str
    manifest_content_sha256: str
    manifest_artifact_sha256: str
    beta_input_id: str
    beta_input_content_sha256: str
    beta_input_artifact_sha256: str
    component_input_id: str
    component_input_content_sha256: str
    component_input_artifact_sha256: str
    valid_beta_date_count: int
    lag_pair_counts_0_through_20: tuple[int, ...]
    long_run_variance: Decimal
    component_count_census_sha256: str
    component_count_census_session_count: int
    q05_components_per_date: int
    raw_required_valid_dates: int
    required_valid_dates: int
    required_connected_components: int
    fixed_h20_test_session_capacity: int
    disposition: ProvisionalPowerDisposition
    definition: Mapping[str, Any]
    _authority: object = dataclasses.field(repr=False, compare=False)

    def __init__(self) -> None:
        raise TypeError("power receipts must be computed by the authenticated worker")

    @property
    def receipt_content_authenticated(self) -> bool:
        require_loaded_power_calibration_receipt(self)
        return True

    @property
    def outcome_access_available(self) -> bool:
        return False

    @property
    def qc_action_available(self) -> bool:
        return False

    @property
    def launch_authorized(self) -> bool:
        return False

    @property
    def persisted_artifact_authenticated(self) -> bool:
        require_persisted_power_calibration_receipt(self)
        return True

    @property
    def receipt_artifact_sha256(self) -> str:
        return power_calibration_receipt_artifact_sha256(self)


_LOADED_CONTRACT = object()
_LOADED_INPUT_AUTHORITY = object()
_LOADED_RECEIPT = object()


@dataclasses.dataclass(frozen=True)
class _ArtifactIdentity:
    path: Path
    artifact_sha256: str
    byte_count: int


@dataclasses.dataclass(frozen=True)
class _PowerReceiptAuthorityRecord:
    reference: weakref.ReferenceType[PowerCalibrationReceipt]
    content_contract: weakref.ReferenceType[PowerCalibrationInputContentContract]
    manifest_candidate: weakref.ReferenceType[
        ProductionCalibrationInputManifestCandidate
    ]
    input_authority: weakref.ReferenceType[PowerCalibrationInputAuthority]
    beta_artifact: _ArtifactIdentity
    component_artifact: _ArtifactIdentity
    fingerprint: tuple[object, ...]
    persisted_receipt: _ArtifactIdentity | None


_CONTENT_CONTRACT_AUTHORITIES: dict[int, tuple[Any, ...]] = {}
_INPUT_AUTHORITIES: dict[int, tuple[Any, ...]] = {}
_POWER_RECEIPT_AUTHORITIES: dict[int, _PowerReceiptAuthorityRecord] = {}
_CONTENT_CONTRACT_AUTHORITIES_LOCK = threading.RLock()
_INPUT_AUTHORITIES_LOCK = threading.RLock()
_POWER_RECEIPT_AUTHORITIES_LOCK = threading.RLock()
_INHERITED_RECEIPT_AUTHORITY_QUARANTINE: list[object] = []


def _reset_process_local_receipt_authorities_after_fork() -> None:
    """Invalidate inherited authorities without running finalizers in the child."""
    global _CONTENT_CONTRACT_AUTHORITIES
    global _CONTENT_CONTRACT_AUTHORITIES_LOCK
    global _INPUT_AUTHORITIES
    global _INPUT_AUTHORITIES_LOCK
    global _POWER_RECEIPT_AUTHORITIES
    global _POWER_RECEIPT_AUTHORITIES_LOCK
    inherited = (
        _CONTENT_CONTRACT_AUTHORITIES,
        _INPUT_AUTHORITIES,
        _POWER_RECEIPT_AUTHORITIES,
    )
    _INHERITED_RECEIPT_AUTHORITY_QUARANTINE.append(inherited)
    _CONTENT_CONTRACT_AUTHORITIES = {}
    _INPUT_AUTHORITIES = {}
    _POWER_RECEIPT_AUTHORITIES = {}
    _CONTENT_CONTRACT_AUTHORITIES_LOCK = threading.RLock()
    _INPUT_AUTHORITIES_LOCK = threading.RLock()
    _POWER_RECEIPT_AUTHORITIES_LOCK = threading.RLock()


_register_process_local_after_fork(
    _reset_process_local_receipt_authorities_after_fork
)
del _register_process_local_after_fork


def _forget_content_contract_authority(key: int, ref: Any) -> None:
    with _CONTENT_CONTRACT_AUTHORITIES_LOCK:
        current = _CONTENT_CONTRACT_AUTHORITIES.get(key)
        if current is not None and current[0] is ref:
            _CONTENT_CONTRACT_AUTHORITIES.pop(key, None)


def _forget_input_authority(key: int, ref: Any) -> None:
    with _INPUT_AUTHORITIES_LOCK:
        current = _INPUT_AUTHORITIES.get(key)
        if current is not None and current[0] is ref:
            _INPUT_AUTHORITIES.pop(key, None)


def _forget_power_receipt_authority(key: int, ref: Any) -> None:
    with _POWER_RECEIPT_AUTHORITIES_LOCK:
        current = _POWER_RECEIPT_AUTHORITIES.get(key)
        if current is not None and current.reference is ref:
            _POWER_RECEIPT_AUTHORITIES.pop(key, None)


def _contract_fingerprint(value: PowerCalibrationInputContentContract) -> tuple[object, ...]:
    return (
        _fingerprint(value.content_contract_id),
        _fingerprint(value.content_contract_hash),
        _fingerprint(value.calibration_session_axis),
        _fingerprint(value.definition),
        _fingerprint(value.capabilities),
    )


def _content_contract_parent_snapshot(
    power_protocol: PowerCalibrationProtocol,
    input_schema: PowerCalibrationInputSchema,
    manifest_admission: PowerCalibrationManifestAdmission,
    multiplicity_overlay: FourFamilyMultiplicityOverlay,
) -> Mapping[str, Any]:
    return _freeze(
        {
            "power_protocol_id": power_protocol.protocol_id,
            "power_protocol_hash": power_protocol.protocol_hash,
            "power_protocol_axis": list(power_protocol.calibration_session_axis),
            "input_schema_id": input_schema.schema_contract_id,
            "input_schema_hash": input_schema.schema_contract_hash,
            "input_schema_axis": list(input_schema.calibration_session_axis),
            "manifest_admission_id": manifest_admission.admission_contract_id,
            "manifest_admission_hash": manifest_admission.admission_contract_hash,
            "manifest_admission_axis": list(
                manifest_admission.calibration_session_axis
            ),
            "multiplicity_overlay_id": multiplicity_overlay.overlay_id,
            "multiplicity_overlay_hash": multiplicity_overlay.overlay_hash,
        }
    )


def load_power_calibration_input_content_contract(
    contract_path: Path,
    *,
    power_protocol: PowerCalibrationProtocol,
    input_schema: PowerCalibrationInputSchema,
    manifest_admission: PowerCalibrationManifestAdmission,
    multiplicity_overlay: FourFamilyMultiplicityOverlay,
) -> PowerCalibrationInputContentContract:
    """Authenticate the no-rights content contract and exact reviewed parents."""
    try:
        require_loaded_power_calibration_protocol(power_protocol)
        require_loaded_power_calibration_input_schema(input_schema)
        require_loaded_power_calibration_manifest_admission(manifest_admission)
        require_loaded_four_family_multiplicity_overlay(multiplicity_overlay)
    except (
        PowerCalibrationProtocolError,
        PowerCalibrationInputSchemaError,
        PowerCalibrationInputManifestError,
        FourFamilyMultiplicityError,
    ) as exc:
        raise PowerCalibrationReceiptError("content-contract parent authentication failed") from exc
    parent_snapshot = _content_contract_parent_snapshot(
        power_protocol, input_schema, manifest_admission, multiplicity_overlay
    )
    parent_snapshot_fingerprint = _fingerprint(parent_snapshot)
    if (
        parent_snapshot["power_protocol_id"] != POWER_PROTOCOL_ID
        or parent_snapshot["power_protocol_hash"] != POWER_PROTOCOL_HASH
        or parent_snapshot["input_schema_id"] != B1_SCHEMA_ID
        or parent_snapshot["input_schema_hash"] != B1_SCHEMA_HASH
        or parent_snapshot["manifest_admission_id"] != ADMISSION_CONTRACT_ID
        or parent_snapshot["manifest_admission_hash"] != ADMISSION_CONTRACT_HASH
        or parent_snapshot["multiplicity_overlay_id"] != FOUR_FAMILY_OVERLAY_ID
        or parent_snapshot["multiplicity_overlay_hash"] != FOUR_FAMILY_OVERLAY_HASH
        or parent_snapshot["input_schema_axis"]
        != parent_snapshot["power_protocol_axis"]
        or parent_snapshot["manifest_admission_axis"]
        != parent_snapshot["power_protocol_axis"]
    ):
        raise PowerCalibrationReceiptError("content-contract parent identity changed")
    resolved, payload = _read_stable_regular(contract_path, "input-content contract")
    raw = _parse(payload, "input-content contract")
    if not CONTENT_CONTRACT_ARTIFACT_SHA256 or hashlib.sha256(payload).hexdigest() != CONTENT_CONTRACT_ARTIFACT_SHA256:
        raise PowerCalibrationReceiptError("input-content contract bytes changed")
    if raw != _contract_document():
        raise PowerCalibrationReceiptError("input-content contract content changed")
    _revalidate(resolved, payload, "input-content contract")
    try:
        require_loaded_power_calibration_protocol(power_protocol)
        require_loaded_power_calibration_input_schema(input_schema)
        require_loaded_power_calibration_manifest_admission(manifest_admission)
        require_loaded_four_family_multiplicity_overlay(multiplicity_overlay)
    except (
        PowerCalibrationProtocolError,
        PowerCalibrationInputSchemaError,
        PowerCalibrationInputManifestError,
        FourFamilyMultiplicityError,
    ) as exc:
        raise PowerCalibrationReceiptError("content-contract parent changed") from exc
    if (
        _fingerprint(
            _content_contract_parent_snapshot(
                power_protocol,
                input_schema,
                manifest_admission,
                multiplicity_overlay,
            )
        )
        != parent_snapshot_fingerprint
    ):
        raise PowerCalibrationReceiptError("content-contract parent changed")
    _revalidate(resolved, payload, "input-content contract")
    value = object.__new__(PowerCalibrationInputContentContract)
    for name, item in {
        "content_contract_id": raw["content_contract_id"],
        "content_contract_hash": raw["content_contract_hash"],
        "calibration_session_axis": tuple(parent_snapshot["power_protocol_axis"]),
        "definition": _freeze(raw),
        "capabilities": _freeze(dict(_NO_ACTION_CAPABILITIES)),
        "_authority": _LOADED_CONTRACT,
    }.items():
        object.__setattr__(value, name, item)
    fingerprint = _contract_fingerprint(value)
    key = id(value)
    ref = weakref.ref(
        value,
        lambda item, k=key: _forget_content_contract_authority(k, item),
    )
    with _CONTENT_CONTRACT_AUTHORITIES_LOCK:
        _CONTENT_CONTRACT_AUTHORITIES[key] = (
            ref, resolved, payload, power_protocol, input_schema,
            manifest_admission, multiplicity_overlay, fingerprint,
            parent_snapshot_fingerprint,
        )
    return value


def require_loaded_power_calibration_input_content_contract(
    contract: PowerCalibrationInputContentContract,
) -> PowerCalibrationInputContentContract:
    if type(contract) is not PowerCalibrationInputContentContract or getattr(contract, "_authority", None) is not _LOADED_CONTRACT:
        raise PowerCalibrationReceiptError("input-content contract is not loader-authenticated")
    with _CONTENT_CONTRACT_AUTHORITIES_LOCK:
        record = _CONTENT_CONTRACT_AUTHORITIES.get(id(contract))
    if record is None or record[0]() is not contract:
        raise PowerCalibrationReceiptError("input-content contract authority is absent")
    if _contract_fingerprint(contract) != record[7]:
        raise PowerCalibrationReceiptError("input-content contract object changed")
    _revalidate(record[1], record[2], "input-content contract")
    try:
        require_loaded_power_calibration_protocol(record[3])
        require_loaded_power_calibration_input_schema(record[4])
        require_loaded_power_calibration_manifest_admission(record[5])
        require_loaded_four_family_multiplicity_overlay(record[6])
    except (
        PowerCalibrationProtocolError,
        PowerCalibrationInputSchemaError,
        PowerCalibrationInputManifestError,
        FourFamilyMultiplicityError,
    ) as exc:
        raise PowerCalibrationReceiptError("input-content contract parent changed") from exc
    if (
        _fingerprint(
            _content_contract_parent_snapshot(
                record[3], record[4], record[5], record[6]
            )
        )
        != record[8]
    ):
        raise PowerCalibrationReceiptError("input-content contract parent changed")
    _revalidate(record[1], record[2], "input-content contract")
    return contract


def _candidate_bindings(candidate: ProductionCalibrationInputManifestCandidate) -> list[dict[str, Any]]:
    manifest = candidate.definition["manifest"]
    return [dict(item) for item in manifest["input_artifacts"]]


def _candidate_truth_snapshot(
    candidate: ProductionCalibrationInputManifestCandidate,
) -> Mapping[str, Any]:
    return _freeze(
        {
            "manifest_id": candidate.manifest_id,
            "manifest_content_sha256": candidate.manifest_content_sha256,
            "manifest_artifact_sha256": candidate.manifest_artifact_sha256,
            "evidence_bundle_id": candidate.evidence_bundle_id,
            "evidence_bundle_content_sha256": (
                candidate.evidence_bundle_content_sha256
            ),
            "evidence_bundle_artifact_sha256": (
                candidate.evidence_bundle_artifact_sha256
            ),
            "evidence_epoch_id": candidate.evidence_epoch_id,
            "data_entitlement_audit_ids": list(
                candidate.data_entitlement_audit_ids
            ),
            "massive_benzinga_working_assumption_id": (
                candidate.massive_benzinga_working_assumption_id
            ),
            "session_count": candidate.session_count,
            "input_roles": list(candidate.input_roles),
            "definition": _thaw(candidate.definition),
        }
    )


def _snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(_thaw(snapshot))).hexdigest()


def _truth_approval_document_from_snapshot(
    candidate_snapshot: Mapping[str, Any],
    *,
    review_id: str,
    review_evidence_sha256: str,
    reviewed_at_utc: str,
) -> dict[str, Any]:
    """Build the exact expected aggregate; this helper does not approve it."""
    review_id = _require_identifier(review_id, "independent review ID")
    review_evidence_sha256 = _require_sha256(
        review_evidence_sha256, "independent review evidence hash"
    )
    reviewed_at_utc = _require_instant(reviewed_at_utc, "independent review instant")
    evidence = _thaw(candidate_snapshot["definition"]["evidence_bundle"])
    manifest = _thaw(candidate_snapshot["definition"]["manifest"])
    vintage = evidence["vintage_evidence"]
    lineage = manifest["producing_lineage"]
    inputs = [dict(item) for item in manifest["input_artifacts"]]
    raw: dict[str, Any] = {
        "schema": PRODUCTION_TRUTH_APPROVAL_SCHEMA,
        "status": PRODUCTION_TRUTH_APPROVAL_STATUS,
        "authority": PRODUCTION_TRUTH_APPROVAL_AUTHORITY,
        "approval_id": None,
        "approval_hash": None,
        "production_manifest_binding": _binding(
            artifact_id=candidate_snapshot["manifest_id"],
            content_sha256=candidate_snapshot["manifest_content_sha256"],
            artifact_sha256=candidate_snapshot["manifest_artifact_sha256"],
        ),
        "evidence_bundle_binding": _binding(
            artifact_id=candidate_snapshot["evidence_bundle_id"],
            content_sha256=candidate_snapshot["evidence_bundle_content_sha256"],
            artifact_sha256=candidate_snapshot["evidence_bundle_artifact_sha256"],
        ),
        "authenticated_truth_claims": {
            claim: True for claim in PRODUCTION_TRUTH_CLAIMS
        },
        "reviewed_evidence_bindings": {
            "data_entitlement_evidence_sha256": hashlib.sha256(
                _canonical(evidence["data_entitlement_evidence"])
            ).hexdigest(),
            "processing_rights_evidence_sha256": hashlib.sha256(
                _canonical(evidence["processing_rights_evidence"])
            ).hexdigest(),
            "vintage_evidence_sha256": hashlib.sha256(
                _canonical(vintage)
            ).hexdigest(),
            "source_snapshot_inventory_sha256": hashlib.sha256(
                _canonical(vintage["source_snapshot_bindings"])
            ).hexdigest(),
            "external_vintage_attestation_sha256": hashlib.sha256(
                _canonical(vintage["external_vintage_attestation"])
            ).hexdigest(),
            "correction_inventory_binding": _binding(
                artifact_id=vintage["correction_inventory_artifact_id"],
                content_sha256=vintage["correction_inventory_content_sha256"],
                artifact_sha256=vintage["correction_inventory_artifact_sha256"],
            ),
            "cutoff_filter_recipe_binding": {
                "artifact_id": vintage["cutoff_filter_recipe_id"],
                "content_sha256": vintage["cutoff_filter_recipe_sha256"],
            },
            "producing_lineage_binding": {
                "build_recipe_id": lineage["build_recipe_id"],
                "build_recipe_sha256": lineage["build_recipe_sha256"],
                "config_sha256": lineage["config_sha256"],
                "lineage_sha256": lineage["lineage_sha256"],
                "producer_code_sha256": lineage["producer_code_sha256"],
                "producing_commit": lineage["producing_commit"],
                "producing_tree": lineage["producing_tree"],
            },
            "input_artifact_bindings": [
                {
                    "role": item["role"],
                    "artifact_id": item["artifact_id"],
                    "content_sha256": item["content_sha256"],
                    "artifact_sha256": item["artifact_sha256"],
                }
                for item in inputs
            ],
        },
        "independent_review_binding": {
            "review_id": review_id,
            "review_evidence_sha256": review_evidence_sha256,
            "reviewed_at_utc": reviewed_at_utc,
        },
        "capabilities": dict(_NO_ACTION_CAPABILITIES),
    }
    return _content_identity(
        raw,
        id_field="approval_id",
        hash_field="approval_hash",
        prefix=PRODUCTION_TRUTH_APPROVAL_ID_PREFIX,
    )


def _truth_approval_document(
    candidate: ProductionCalibrationInputManifestCandidate,
    *,
    review_id: str,
    review_evidence_sha256: str,
    reviewed_at_utc: str,
) -> dict[str, Any]:
    """Render expected fixture/review bytes from one stable candidate view."""
    require_loaded_production_calibration_input_manifest_candidate(candidate)
    snapshot = _candidate_truth_snapshot(candidate)
    digest = _snapshot_digest(snapshot)
    result = _truth_approval_document_from_snapshot(
        snapshot,
        review_id=review_id,
        review_evidence_sha256=review_evidence_sha256,
        reviewed_at_utc=reviewed_at_utc,
    )
    require_loaded_production_calibration_input_manifest_candidate(candidate)
    if _snapshot_digest(_candidate_truth_snapshot(candidate)) != digest:
        raise PowerCalibrationReceiptError(
            "production truth candidate changed during document construction"
        )
    return result


def _validate_truth_approval_document(
    raw: dict[str, Any],
    candidate_snapshot: Mapping[str, Any],
) -> tuple[str, str, str]:
    _require_keys(raw, PRODUCTION_TRUTH_APPROVAL_FIELDS, "production truth approval")
    review = _require_keys(
        raw["independent_review_binding"],
        INDEPENDENT_REVIEW_BINDING_FIELDS,
        "independent review binding",
    )
    expected = _truth_approval_document_from_snapshot(
        candidate_snapshot,
        review_id=review["review_id"],
        review_evidence_sha256=review["review_evidence_sha256"],
        reviewed_at_utc=review["reviewed_at_utc"],
    )
    if raw != expected:
        raise PowerCalibrationReceiptError("production truth approval content changed")
    return (
        review["review_id"],
        review["review_evidence_sha256"],
        review["reviewed_at_utc"],
    )


def _load_pinned_production_truth_approval(
    approval_path: Path,
    candidate: ProductionCalibrationInputManifestCandidate,
) -> tuple[_ArtifactIdentity, dict[str, Any], tuple[str, str, str]]:
    """Load one exact reviewed aggregate; no checked-in pin means zero access."""
    if PRODUCTION_TRUTH_EVIDENCE_OPENER_IMPLEMENTED is not True:
        raise PowerCalibrationReceiptError(
            "production truth evidence opener is not implemented"
        )
    pinned = PRODUCTION_TRUTH_APPROVAL_ARTIFACT_SHA256
    if pinned is None:
        raise PowerCalibrationReceiptError(
            "no independently reviewed production truth approval is pinned"
        )
    pinned = _require_sha256(pinned, "production truth approval pin")
    require_loaded_production_calibration_input_manifest_candidate(candidate)
    candidate_snapshot = _candidate_truth_snapshot(candidate)
    candidate_snapshot_digest = _snapshot_digest(candidate_snapshot)
    resolved, payload = _read_stable_regular(
        approval_path, "production truth approval"
    )
    if hashlib.sha256(payload).hexdigest() != pinned:
        raise PowerCalibrationReceiptError(
            "production truth approval does not match the reviewed pin"
        )
    raw = _parse(payload, "production truth approval")
    review = _validate_truth_approval_document(raw, candidate_snapshot)
    _revalidate(resolved, payload, "production truth approval")
    require_loaded_production_calibration_input_manifest_candidate(candidate)
    if _snapshot_digest(_candidate_truth_snapshot(candidate)) != candidate_snapshot_digest:
        raise PowerCalibrationReceiptError(
            "production truth candidate changed during approval load"
        )
    _revalidate(resolved, payload, "production truth approval")
    return _ArtifactIdentity(resolved, pinned, len(payload)), raw, review


def _reauthenticate_production_truth_approval(
    identity: _ArtifactIdentity,
    candidate: ProductionCalibrationInputManifestCandidate,
    review: tuple[str, str, str],
) -> dict[str, Any]:
    require_loaded_production_calibration_input_manifest_candidate(candidate)
    candidate_snapshot = _candidate_truth_snapshot(candidate)
    candidate_snapshot_digest = _snapshot_digest(candidate_snapshot)
    resolved, payload = _read_stable_regular(
        identity.path, "production truth approval"
    )
    if (
        resolved != identity.path
        or len(payload) != identity.byte_count
        or hashlib.sha256(payload).hexdigest() != identity.artifact_sha256
    ):
        raise PowerCalibrationReceiptError("production truth approval bytes changed")
    raw = _parse(payload, "production truth approval")
    if _validate_truth_approval_document(raw, candidate_snapshot) != review:
        raise PowerCalibrationReceiptError("production truth review binding changed")
    _revalidate(resolved, payload, "production truth approval")
    require_loaded_production_calibration_input_manifest_candidate(candidate)
    if _snapshot_digest(_candidate_truth_snapshot(candidate)) != candidate_snapshot_digest:
        raise PowerCalibrationReceiptError(
            "production truth candidate changed during approval reauthentication"
        )
    _revalidate(resolved, payload, "production truth approval")
    return raw


def _authority_construction_snapshot(
    contract: PowerCalibrationInputContentContract,
    candidate: ProductionCalibrationInputManifestCandidate,
    *,
    truth_approval: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Capture every authority-construction parent in one immutable view."""
    return _freeze(
        {
            "content_contract": {
                "content_contract_id": contract.content_contract_id,
                "content_contract_hash": contract.content_contract_hash,
                "calibration_session_axis": list(
                    contract.calibration_session_axis
                ),
                "definition": _thaw(contract.definition),
                "capabilities": _thaw(contract.capabilities),
            },
            "manifest_candidate": _thaw(_candidate_truth_snapshot(candidate)),
            "truth_approval": _thaw(truth_approval),
        }
    )


def _authority_document_from_snapshot(
    construction_snapshot: Mapping[str, Any],
    *,
    owner_authorization_id: str,
    owner_authorization_evidence_sha256: str,
    authorized_at_utc: str,
) -> dict[str, Any]:
    owner_authorization_id = _require_identifier(owner_authorization_id, "owner authorization ID")
    owner_authorization_evidence_sha256 = _require_sha256(
        owner_authorization_evidence_sha256, "owner authorization evidence hash"
    )
    authorized_at_utc = _require_instant(authorized_at_utc, "authorization instant")
    contract = construction_snapshot["content_contract"]
    candidate = construction_snapshot["manifest_candidate"]
    truth_approval = construction_snapshot["truth_approval"]
    bindings = [
        dict(item)
        for item in candidate["definition"]["manifest"]["input_artifacts"]
    ]
    if (
        truth_approval["production_manifest_binding"]
        != _binding(
            artifact_id=candidate["manifest_id"],
            content_sha256=candidate["manifest_content_sha256"],
            artifact_sha256=candidate["manifest_artifact_sha256"],
        )
        or truth_approval["evidence_bundle_binding"]
        != _binding(
            artifact_id=candidate["evidence_bundle_id"],
            content_sha256=candidate["evidence_bundle_content_sha256"],
            artifact_sha256=candidate["evidence_bundle_artifact_sha256"],
        )
    ):
        raise PowerCalibrationReceiptError(
            "production truth approval ancestry changed"
        )
    raw: dict[str, Any] = {
        "schema": INPUT_AUTHORITY_SCHEMA,
        "status": INPUT_AUTHORITY_STATUS,
        "authority": INPUT_AUTHORITY_SCOPE,
        "authority_id": None,
        "authority_hash": None,
        "owner_authorization_id": owner_authorization_id,
        "owner_authorization_evidence_sha256": owner_authorization_evidence_sha256,
        "authorized_at_utc": authorized_at_utc,
        "content_contract_binding": _binding(
            artifact_id=contract["content_contract_id"],
            content_sha256=contract["content_contract_hash"],
            artifact_sha256=CONTENT_CONTRACT_ARTIFACT_SHA256,
        ),
        "production_manifest_binding": _binding(
            artifact_id=candidate["manifest_id"],
            content_sha256=candidate["manifest_content_sha256"],
            artifact_sha256=candidate["manifest_artifact_sha256"],
        ),
        "evidence_bundle_binding": _binding(
            artifact_id=candidate["evidence_bundle_id"],
            content_sha256=candidate["evidence_bundle_content_sha256"],
            artifact_sha256=candidate["evidence_bundle_artifact_sha256"],
        ),
        "production_truth_approval_binding": _binding(
            artifact_id=truth_approval["approval_id"],
            content_sha256=truth_approval["approval_hash"],
            artifact_sha256=hashlib.sha256(_render(_thaw(truth_approval))).hexdigest(),
        ),
        "authenticated_production_truth_claims": dict(
            truth_approval["authenticated_truth_claims"]
        ),
        "input_artifact_bindings": [
            {
                "role": item["role"],
                "artifact_id": item["artifact_id"],
                "content_sha256": item["content_sha256"],
                "artifact_sha256": item["artifact_sha256"],
            }
            for item in bindings
        ],
        "authorized_operations": dict(_AUTHORITY_OPERATIONS),
    }
    return _content_identity(
        raw,
        id_field="authority_id",
        hash_field="authority_hash",
        prefix=INPUT_AUTHORITY_ID_PREFIX,
    )


def _authority_document(
    contract: PowerCalibrationInputContentContract,
    candidate: ProductionCalibrationInputManifestCandidate,
    *,
    truth_approval: Mapping[str, Any],
    owner_authorization_id: str,
    owner_authorization_evidence_sha256: str,
    authorized_at_utc: str,
) -> dict[str, Any]:
    """Build fixture/review bytes from one stable authenticated parent view."""
    require_loaded_power_calibration_input_content_contract(contract)
    require_loaded_production_calibration_input_manifest_candidate(candidate)
    snapshot = _authority_construction_snapshot(
        contract, candidate, truth_approval=truth_approval
    )
    snapshot_digest = _snapshot_digest(snapshot)
    result = _authority_document_from_snapshot(
        snapshot,
        owner_authorization_id=owner_authorization_id,
        owner_authorization_evidence_sha256=owner_authorization_evidence_sha256,
        authorized_at_utc=authorized_at_utc,
    )
    require_loaded_power_calibration_input_content_contract(contract)
    require_loaded_production_calibration_input_manifest_candidate(candidate)
    if (
        _snapshot_digest(
            _authority_construction_snapshot(
                contract, candidate, truth_approval=truth_approval
            )
        )
        != snapshot_digest
    ):
        raise PowerCalibrationReceiptError(
            "input authority parents changed during document construction"
        )
    return result


def render_power_calibration_input_authority(
    content_contract: PowerCalibrationInputContentContract,
    manifest_candidate: ProductionCalibrationInputManifestCandidate,
    *,
    production_truth_approval_path: Path,
    owner_authorization_id: str,
    owner_authorization_evidence_sha256: str,
    authorized_at_utc: str,
) -> str:
    """Render an operation authority bound to one pinned truth aggregate."""
    require_loaded_power_calibration_input_content_contract(content_contract)
    require_loaded_production_calibration_input_manifest_candidate(manifest_candidate)
    truth_identity, truth_approval, truth_review = _load_pinned_production_truth_approval(
        production_truth_approval_path, manifest_candidate
    )
    snapshot = _authority_construction_snapshot(
        content_contract, manifest_candidate, truth_approval=truth_approval
    )
    snapshot_digest = _snapshot_digest(snapshot)
    document = _authority_document_from_snapshot(
        snapshot,
        owner_authorization_id=owner_authorization_id,
        owner_authorization_evidence_sha256=owner_authorization_evidence_sha256,
        authorized_at_utc=authorized_at_utc,
    )
    require_loaded_power_calibration_input_content_contract(content_contract)
    require_loaded_production_calibration_input_manifest_candidate(manifest_candidate)
    current_truth = _reauthenticate_production_truth_approval(
        truth_identity, manifest_candidate, truth_review
    )
    if (
        _snapshot_digest(
            _authority_construction_snapshot(
                content_contract,
                manifest_candidate,
                truth_approval=current_truth,
            )
        )
        != snapshot_digest
    ):
        raise PowerCalibrationReceiptError(
            "input authority parents changed during rendering"
        )
    return _render(document).decode("utf-8")


def _authority_fingerprint(value: PowerCalibrationInputAuthority) -> tuple[object, ...]:
    return tuple(
        _fingerprint(item)
        for item in (
            value.authority_id,
            value.authority_hash,
            value.owner_authorization_id,
            value.owner_authorization_evidence_sha256,
            value.authorized_at_utc,
            value.manifest_id,
            value.production_truth_approval_id,
            value.production_truth_approval_hash,
            value.production_truth_approval_artifact_sha256,
            value.definition,
        )
    )


def load_power_calibration_input_authority(
    authority_path: Path,
    *,
    content_contract: PowerCalibrationInputContentContract,
    manifest_candidate: ProductionCalibrationInputManifestCandidate,
    production_truth_approval_path: Path,
) -> PowerCalibrationInputAuthority:
    """Load exact operation authority plus independently pinned data truth."""
    authority_pin = PRODUCTION_INPUT_AUTHORITY_ARTIFACT_SHA256
    if authority_pin is None:
        raise PowerCalibrationReceiptError(
            "no independently reviewed input operation authority is pinned"
        )
    authority_pin = _require_sha256(
        authority_pin, "input operation authority pin"
    )
    require_loaded_power_calibration_input_content_contract(content_contract)
    require_loaded_production_calibration_input_manifest_candidate(manifest_candidate)
    truth_identity, truth_approval, truth_review = (
        _load_pinned_production_truth_approval(
            production_truth_approval_path, manifest_candidate
        )
    )
    construction_snapshot = _authority_construction_snapshot(
        content_contract,
        manifest_candidate,
        truth_approval=truth_approval,
    )
    construction_snapshot_digest = _snapshot_digest(construction_snapshot)
    resolved, payload = _read_stable_regular(authority_path, "input authority")
    if hashlib.sha256(payload).hexdigest() != authority_pin:
        raise PowerCalibrationReceiptError(
            "input operation authority does not match the reviewed pin"
        )
    raw = _parse(payload, "input authority")
    fields = (
        "schema", "status", "authority", "authority_id", "authority_hash",
        "owner_authorization_id", "owner_authorization_evidence_sha256",
        "authorized_at_utc", "content_contract_binding",
        "production_manifest_binding", "evidence_bundle_binding",
        "production_truth_approval_binding",
        "authenticated_production_truth_claims",
        "input_artifact_bindings", "authorized_operations",
    )
    _require_keys(raw, fields, "input authority")
    expected = _authority_document_from_snapshot(
        construction_snapshot,
        owner_authorization_id=raw["owner_authorization_id"],
        owner_authorization_evidence_sha256=raw["owner_authorization_evidence_sha256"],
        authorized_at_utc=raw["authorized_at_utc"],
    )
    if raw != expected:
        raise PowerCalibrationReceiptError("input authority content changed")
    _revalidate(resolved, payload, "input authority")
    require_loaded_power_calibration_input_content_contract(content_contract)
    require_loaded_production_calibration_input_manifest_candidate(manifest_candidate)
    current_truth = _reauthenticate_production_truth_approval(
        truth_identity, manifest_candidate, truth_review
    )
    if (
        _snapshot_digest(
            _authority_construction_snapshot(
                content_contract,
                manifest_candidate,
                truth_approval=current_truth,
            )
        )
        != construction_snapshot_digest
    ):
        raise PowerCalibrationReceiptError(
            "input authority parents changed during load"
        )
    _revalidate(resolved, payload, "input authority")
    value = object.__new__(PowerCalibrationInputAuthority)
    for name, item in {
        "authority_id": raw["authority_id"],
        "authority_hash": raw["authority_hash"],
        "owner_authorization_id": raw["owner_authorization_id"],
        "owner_authorization_evidence_sha256": raw["owner_authorization_evidence_sha256"],
        "authorized_at_utc": raw["authorized_at_utc"],
        "manifest_id": raw["production_manifest_binding"]["artifact_id"],
        "production_truth_approval_id": raw[
            "production_truth_approval_binding"
        ]["artifact_id"],
        "production_truth_approval_hash": raw[
            "production_truth_approval_binding"
        ]["content_sha256"],
        "production_truth_approval_artifact_sha256": (
            truth_identity.artifact_sha256
        ),
        "definition": _freeze(raw),
        "_authority": _LOADED_INPUT_AUTHORITY,
    }.items():
        object.__setattr__(value, name, item)
    fingerprint = _authority_fingerprint(value)
    key = id(value)
    ref = weakref.ref(
        value,
        lambda item, k=key: _forget_input_authority(k, item),
    )
    with _INPUT_AUTHORITIES_LOCK:
        _INPUT_AUTHORITIES[key] = (
            ref,
            resolved,
            payload,
            content_contract,
            manifest_candidate,
            fingerprint,
            truth_identity,
            truth_review,
            construction_snapshot_digest,
        )
    return value


def require_loaded_power_calibration_input_authority(
    authority: PowerCalibrationInputAuthority,
) -> PowerCalibrationInputAuthority:
    if type(authority) is not PowerCalibrationInputAuthority or getattr(authority, "_authority", None) is not _LOADED_INPUT_AUTHORITY:
        raise PowerCalibrationReceiptError("input authority is not loader-authenticated")
    with _INPUT_AUTHORITIES_LOCK:
        record = _INPUT_AUTHORITIES.get(id(authority))
    if record is None or record[0]() is not authority:
        raise PowerCalibrationReceiptError("input authority registry entry is absent")
    if _authority_fingerprint(authority) != record[5]:
        raise PowerCalibrationReceiptError("input authority object changed")
    _revalidate(record[1], record[2], "input authority")
    try:
        require_loaded_power_calibration_input_content_contract(record[3])
        require_loaded_production_calibration_input_manifest_candidate(record[4])
        truth = _reauthenticate_production_truth_approval(
            record[6], record[4], record[7]
        )
    except (
        PowerCalibrationInputManifestError,
        PowerCalibrationReceiptError,
    ) as exc:
        raise PowerCalibrationReceiptError("input authority parent changed") from exc
    if (
        _snapshot_digest(
            _authority_construction_snapshot(
                record[3], record[4], truth_approval=truth
            )
        )
        != record[8]
    ):
        raise PowerCalibrationReceiptError("input authority parent changed")
    if (
        authority.definition["authenticated_production_truth_claims"]
        != truth["authenticated_truth_claims"]
        or set(truth["authenticated_truth_claims"])
        != set(PRODUCTION_TRUTH_CLAIMS)
        or len(truth["authenticated_truth_claims"])
        != len(PRODUCTION_TRUTH_CLAIMS)
        or any(
            truth["authenticated_truth_claims"][claim] is not True
            for claim in PRODUCTION_TRUTH_CLAIMS
        )
    ):
        raise PowerCalibrationReceiptError(
            "production truth claims are not positively authenticated"
        )
    _revalidate(record[1], record[2], "input authority")
    return authority


def _authenticated_truth_claim(
    authority: PowerCalibrationInputAuthority, claim: str
) -> bool:
    if claim not in PRODUCTION_TRUTH_CLAIMS:
        raise PowerCalibrationReceiptError("production truth claim is not closed")
    require_loaded_power_calibration_input_authority(authority)
    claims = authority.definition["authenticated_production_truth_claims"]
    if claims[claim] is not True:
        raise PowerCalibrationReceiptError(
            "production truth claim is not positively authenticated"
        )
    return claims[claim] is True


def _decimal(text: object, name: str) -> Decimal:
    if (
        type(text) is not str
        or len(text.encode("utf-8")) > MAX_DECIMAL_TEXT_BYTES
        or _CANONICAL_DECIMAL.fullmatch(text) is None
    ):
        raise PowerCalibrationReceiptError(f"{name} is not a canonical Decimal string")
    value = Decimal(text)
    if not value.is_finite() or (value.is_zero() and text.startswith("-")):
        raise PowerCalibrationReceiptError(f"{name} is not a canonical finite Decimal")
    return value


def _fresh_context() -> Context:
    context = Context(
        prec=50,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
    )
    for signal in context.traps:
        context.traps[signal] = False
    for signal in (InvalidOperation, DivisionByZero, Overflow):
        context.traps[signal] = True
    context.clear_flags()
    return context


def _stable_sum(values: Iterable[Decimal]) -> Decimal:
    # Decimal.__abs__ is context-sensitive; copy_abs preserves the exact
    # magnitude required by the frozen ordering dialect before summation.
    ordered = sorted(values, key=lambda item: (item.copy_abs(), item))
    total = Decimal(0)
    for item in ordered:
        total += item
    return total


def _validate_raw_input_identity(
    payload: bytes, metadata: Mapping[str, Any], name: str
) -> None:
    if (
        hashlib.sha256(payload).hexdigest() != metadata["artifact_sha256"]
        or len(payload) != metadata["byte_count"]
    ):
        raise PowerCalibrationReceiptError(f"{name} does not match the B2 manifest")


def _validate_input_hashes(
    payload: bytes,
    raw: dict[str, Any],
    metadata: Mapping[str, Any],
    name: str,
) -> None:
    _validate_raw_input_identity(payload, metadata, name)
    if (
        hashlib.sha256(_canonical(raw)).hexdigest() != metadata["content_sha256"]
    ):
        raise PowerCalibrationReceiptError(f"{name} does not match the B2 manifest")


def _artifact_identity(
    path: Path,
    payload: bytes,
    *,
    artifact_sha256: str,
    byte_count: int,
    name: str,
) -> _ArtifactIdentity:
    if (
        hashlib.sha256(payload).hexdigest() != artifact_sha256
        or len(payload) != byte_count
    ):
        raise PowerCalibrationReceiptError(f"{name} identity changed")
    return _ArtifactIdentity(path, artifact_sha256, byte_count)


def _reauthenticate_artifact_identity(
    identity: _ArtifactIdentity,
    name: str,
    *,
    maximum_bytes: int = MAX_INPUT_ARTIFACT_BYTES,
) -> bytes:
    resolved, payload = _read_stable_regular(
        identity.path, name, maximum_bytes=maximum_bytes
    )
    if (
        resolved != identity.path
        or len(payload) != identity.byte_count
        or hashlib.sha256(payload).hexdigest() != identity.artifact_sha256
    ):
        raise PowerCalibrationReceiptError(f"{name} bytes changed")
    _revalidate(resolved, payload, name, maximum_bytes=maximum_bytes)
    return payload


def _load_beta_series(
    payload: bytes,
    metadata: Mapping[str, Any],
    sessions: tuple[str, ...],
) -> tuple[Decimal | None, ...]:
    raw = _parse(payload, "date-beta input")
    _require_keys(raw, BETA_INPUT_ROOT_FIELDS, "date-beta input")
    _validate_input_hashes(payload, raw, metadata, "date-beta input")
    if raw["schema"] != BETA_INPUT_SCHEMA or type(raw["records"]) is not list or len(raw["records"]) != CALIBRATION_SESSION_COUNT:
        raise PowerCalibrationReceiptError("date-beta input schema or count changed")
    values: list[Decimal | None] = []
    inventory: list[dict[str, str]] = []
    for index, (item, session) in enumerate(zip(raw["records"], sessions, strict=True)):
        item = _require_keys(item, BETA_RECORD_FIELDS, f"date-beta record {index}")
        state = item["state"]
        if item["decision_session"] != session or type(state) is not str or state not in BETA_STATES:
            raise PowerCalibrationReceiptError("date-beta session or state changed")
        if state == "valid":
            value = _decimal(item["beta_value"], f"date-beta value {index}")
        elif item["beta_value"] is None:
            value = None
        else:
            raise PowerCalibrationReceiptError("missing/refused beta must have null value")
        values.append(value)
        inventory.append({"session": session, "state": state})
    counts = {state: sum(item["state"] == state for item in inventory) for state in BETA_STATES}
    if (
        tuple(inventory) != tuple(dict(item) for item in metadata["session_state_inventory"])
        or counts["valid"] != metadata["valid_beta_date_count"]
        or counts["missing"] != metadata["missing_beta_date_count"]
        or counts["refused"] != metadata["refused_beta_date_count"]
        or hashlib.sha256(_canonical(inventory)).hexdigest() != metadata["state_census_sha256"]
    ):
        raise PowerCalibrationReceiptError("date-beta state inventory changed")
    return tuple(values)


def _load_component_counts(
    payload: bytes,
    metadata: Mapping[str, Any],
    sessions: tuple[str, ...],
) -> tuple[tuple[str, int], ...]:
    raw = _parse(payload, "component-count input")
    _require_keys(raw, COMPONENT_INPUT_ROOT_FIELDS, "component-count input")
    _validate_input_hashes(payload, raw, metadata, "component-count input")
    if raw["schema"] != COMPONENT_INPUT_SCHEMA or type(raw["records"]) is not list or len(raw["records"]) != CALIBRATION_SESSION_COUNT:
        raise PowerCalibrationReceiptError("component-count input schema or count changed")
    result: list[tuple[str, int]] = []
    inventory: list[dict[str, object]] = []
    for index, (item, session) in enumerate(zip(raw["records"], sessions, strict=True)):
        item = _require_keys(item, COMPONENT_RECORD_FIELDS, f"component-count record {index}")
        count = item["connected_component_count"]
        if item["decision_session"] != session or type(count) is not int or count < 0:
            raise PowerCalibrationReceiptError("component session or count changed")
        result.append((session, count))
        inventory.append({"session": session, "connected_component_count": count})
    if (
        tuple(inventory) != tuple(dict(item) for item in metadata["session_count_inventory"])
        or metadata["component_count_census_session_count"] != CALIBRATION_SESSION_COUNT
        or metadata["missing_session_count"] != 0
        or hashlib.sha256(_canonical(inventory)).hexdigest() != metadata["component_count_census_sha256"]
    ):
        raise PowerCalibrationReceiptError("component-count census changed")
    return tuple(result)


def _hac(values: tuple[Decimal | None, ...]) -> tuple[tuple[int, ...], Decimal]:
    valid = tuple(item for item in values if item is not None)
    count = len(valid)
    if count < MINIMUM_ABSOLUTE_FLOOR:
        raise PowerCalibrationReceiptError("fewer than 50 valid beta dates")
    context = _fresh_context()
    try:
        with localcontext(context) as active:
            active.clear_flags()
            mean = _stable_sum(valid) / Decimal(count)
            centered = tuple(None if item is None else item - mean for item in values)
            gammas: list[Decimal] = []
            pair_counts: list[int] = []
            for lag in range(HAC_MAX_LAG + 1):
                products = [
                    centered[index] * centered[index - lag]
                    for index in range(lag, len(centered))
                    if centered[index] is not None and centered[index - lag] is not None
                ]
                pair_counts.append(len(products))
                if not products:
                    raise PowerCalibrationReceiptError("a required HAC lag has no valid pair")
                gammas.append(_stable_sum(products) / Decimal(count))
            weighted = [
                Decimal(HAC_MAX_LAG + 1 - lag)
                / Decimal(HAC_MAX_LAG + 1)
                * gammas[lag]
                for lag in range(1, HAC_MAX_LAG + 1)
            ]
            omega = gammas[0] + Decimal(2) * _stable_sum(weighted)
    except (InvalidOperation, DivisionByZero, Overflow) as exc:
        raise PowerCalibrationReceiptError("HAC arithmetic is invalid") from exc
    if not omega.is_finite() or omega <= 0:
        raise PowerCalibrationReceiptError("long-run variance must be positive and finite")
    return tuple(pair_counts), omega


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"-0", ""} else text


def _receipt_fingerprint(value: PowerCalibrationReceipt) -> tuple[object, ...]:
    return tuple(
        _fingerprint(getattr(value, field.name))
        for field in dataclasses.fields(PowerCalibrationReceipt)
        if field.name != "_authority"
    )


def _authenticated_receipt_input_snapshot(
    content_contract: PowerCalibrationInputContentContract,
    manifest_candidate: ProductionCalibrationInputManifestCandidate,
    input_authority: PowerCalibrationInputAuthority,
    protocol: PowerCalibrationProtocol,
) -> Mapping[str, Any]:
    """Copy every authenticated construction input into one immutable view."""
    return _freeze(
        {
            "protocol": _binding(
                artifact_id=protocol.protocol_id,
                content_sha256=protocol.protocol_hash,
                artifact_sha256=POWER_PROTOCOL_ARTIFACT_SHA256,
            ),
            "content_contract": _binding(
                artifact_id=content_contract.content_contract_id,
                content_sha256=content_contract.content_contract_hash,
                artifact_sha256=CONTENT_CONTRACT_ARTIFACT_SHA256,
            ),
            "calibration_session_axis": list(
                content_contract.calibration_session_axis
            ),
            "production_manifest": _binding(
                artifact_id=manifest_candidate.manifest_id,
                content_sha256=manifest_candidate.manifest_content_sha256,
                artifact_sha256=manifest_candidate.manifest_artifact_sha256,
            ),
            "evidence_bundle": _binding(
                artifact_id=manifest_candidate.evidence_bundle_id,
                content_sha256=manifest_candidate.evidence_bundle_content_sha256,
                artifact_sha256=manifest_candidate.evidence_bundle_artifact_sha256,
            ),
            "input_artifacts": _candidate_bindings(manifest_candidate),
            "input_authority": {
                "authority_id": input_authority.authority_id,
                "authority_hash": input_authority.authority_hash,
                "owner_authorization_id": input_authority.owner_authorization_id,
                "owner_authorization_evidence_sha256": (
                    input_authority.owner_authorization_evidence_sha256
                ),
                "production_truth_approval_id": (
                    input_authority.production_truth_approval_id
                ),
                "production_truth_approval_hash": (
                    input_authority.production_truth_approval_hash
                ),
                "production_truth_approval_artifact_sha256": (
                    input_authority.production_truth_approval_artifact_sha256
                ),
            },
            "authenticated_production_truth_claims": _thaw(
                input_authority.definition[
                    "authenticated_production_truth_claims"
                ]
            ),
        }
    )


def compute_power_calibration_receipt(
    content_contract: PowerCalibrationInputContentContract,
    manifest_candidate: ProductionCalibrationInputManifestCandidate,
    *,
    input_authority: PowerCalibrationInputAuthority,
    beta_series_path: Path,
    component_count_path: Path,
) -> PowerCalibrationReceipt:
    """Read two exact authorized inputs and compute only the closed receipt."""
    require_loaded_power_calibration_input_content_contract(content_contract)
    require_loaded_production_calibration_input_manifest_candidate(manifest_candidate)
    require_loaded_power_calibration_input_authority(input_authority)
    with _CONTENT_CONTRACT_AUTHORITIES_LOCK:
        contract_record = _CONTENT_CONTRACT_AUTHORITIES.get(id(content_contract))
    if contract_record is None:
        raise PowerCalibrationReceiptError(
            "input-content contract authority disappeared"
        )
    protocol = contract_record[3]
    if (
        protocol.protocol_id != POWER_PROTOCOL_ID
        or protocol.protocol_hash != POWER_PROTOCOL_HASH
    ):
        raise PowerCalibrationReceiptError("power protocol identity changed")
    snapshot = _authenticated_receipt_input_snapshot(
        content_contract, manifest_candidate, input_authority, protocol
    )
    snapshot_fingerprint = _fingerprint(snapshot)
    truth_claims = snapshot["authenticated_production_truth_claims"]
    if (
        set(truth_claims) != set(PRODUCTION_TRUTH_CLAIMS)
        or len(truth_claims) != len(PRODUCTION_TRUTH_CLAIMS)
        or any(truth_claims[claim] is not True for claim in PRODUCTION_TRUTH_CLAIMS)
    ):
        raise PowerCalibrationReceiptError(
            "every production truth claim must be positively authenticated"
        )
    with _INPUT_AUTHORITIES_LOCK:
        authority_record = _INPUT_AUTHORITIES.get(id(input_authority))
    if authority_record is None or authority_record[3] is not content_contract or authority_record[4] is not manifest_candidate:
        raise PowerCalibrationReceiptError("input authority is not bound to these loaded objects")
    metadata = snapshot["input_artifacts"]
    if tuple(item["role"] for item in metadata) != INPUT_ROLES:
        raise PowerCalibrationReceiptError("manifest input roles changed")
    beta_path, beta_payload = _read_stable_regular(beta_series_path, "date-beta input")
    component_path, component_payload = _read_stable_regular(component_count_path, "component-count input")
    # Authenticate both opaque artifacts before either parser can inspect row
    # values or reflect parser position through a downstream error.
    _validate_raw_input_identity(beta_payload, metadata[0], "date-beta input")
    _validate_raw_input_identity(
        component_payload, metadata[1], "component-count input"
    )
    sessions = tuple(snapshot["calibration_session_axis"])
    beta_values = _load_beta_series(beta_payload, metadata[0], sessions)
    component_counts = _load_component_counts(component_payload, metadata[1], sessions)
    pair_counts, omega = _hac(beta_values)
    try:
        planned = derive_provisional_power_requirement(
            protocol,
            long_run_variance=omega,
            per_session_component_counts=component_counts,
        )
    except PowerCalibrationProtocolError as exc:
        raise PowerCalibrationReceiptError("power planning arithmetic failed") from exc
    required_fields = {
        "protocol_id": snapshot["protocol"]["artifact_id"],
        "protocol_hash": snapshot["protocol"]["content_sha256"],
        "calibration_input_manifest_sha256": snapshot["production_manifest"][
            "artifact_sha256"
        ],
        "valid_beta_date_count": len([item for item in beta_values if item is not None]),
        "lag_pair_counts_0_through_20": list(pair_counts),
        "long_run_variance": _decimal_text(omega),
        "component_count_census_sha256": metadata[1]["component_count_census_sha256"],
        "component_count_census_session_count": CALIBRATION_SESSION_COUNT,
        "q05_components_per_date": planned.q05_components_per_date,
        "raw_required_valid_dates": planned.raw_required_valid_dates,
        "required_valid_dates": planned.required_valid_dates,
        "required_connected_components": planned.required_connected_components,
        "fixed_capacity_disposition": planned.disposition.value,
    }
    if tuple(required_fields) != REQUIRED_RECEIPT_FIELDS:
        raise PowerCalibrationReceiptError("required receipt field dialect changed")
    receipt_raw: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "status": RECEIPT_STATUS,
        "authority": RECEIPT_AUTHORITY,
        "receipt_id": None,
        "receipt_hash": None,
        "required_receipt_fields": required_fields,
        "content_contract_binding": _binding(
            artifact_id=snapshot["content_contract"]["artifact_id"],
            content_sha256=snapshot["content_contract"]["content_sha256"],
            artifact_sha256=snapshot["content_contract"]["artifact_sha256"],
        ),
        "input_authority_binding": _thaw(snapshot["input_authority"]),
        "production_manifest_binding": _binding(
            artifact_id=snapshot["production_manifest"]["artifact_id"],
            content_sha256=snapshot["production_manifest"]["content_sha256"],
            artifact_sha256=snapshot["production_manifest"]["artifact_sha256"],
        ),
        "evidence_bundle_binding": _binding(
            artifact_id=snapshot["evidence_bundle"]["artifact_id"],
            content_sha256=snapshot["evidence_bundle"]["content_sha256"],
            artifact_sha256=snapshot["evidence_bundle"]["artifact_sha256"],
        ),
        "input_artifact_bindings": [
            {
                "role": item["role"],
                "artifact_id": item["artifact_id"],
                "content_sha256": item["content_sha256"],
                "artifact_sha256": item["artifact_sha256"],
            }
            for item in metadata
        ],
    }
    receipt_raw = _content_identity(
        receipt_raw,
        id_field="receipt_id",
        hash_field="receipt_hash",
        prefix=RECEIPT_ID_PREFIX,
    )
    _revalidate(beta_path, beta_payload, "date-beta input")
    _revalidate(component_path, component_payload, "component-count input")
    require_loaded_power_calibration_input_authority(input_authority)
    require_loaded_production_calibration_input_manifest_candidate(manifest_candidate)
    require_loaded_power_calibration_input_content_contract(content_contract)
    if (
        _fingerprint(
            _authenticated_receipt_input_snapshot(
                content_contract, manifest_candidate, input_authority, protocol
            )
        )
        != snapshot_fingerprint
    ):
        raise PowerCalibrationReceiptError(
            "authenticated receipt construction inputs changed"
        )
    _revalidate(beta_path, beta_payload, "date-beta input")
    _revalidate(component_path, component_payload, "component-count input")
    value = object.__new__(PowerCalibrationReceipt)
    for name, item in {
        "receipt_id": receipt_raw["receipt_id"],
        "receipt_hash": receipt_raw["receipt_hash"],
        "protocol_id": snapshot["protocol"]["artifact_id"],
        "protocol_hash": snapshot["protocol"]["content_sha256"],
        "content_contract_id": snapshot["content_contract"]["artifact_id"],
        "content_contract_hash": snapshot["content_contract"]["content_sha256"],
        "manifest_id": snapshot["production_manifest"]["artifact_id"],
        "manifest_content_sha256": snapshot["production_manifest"][
            "content_sha256"
        ],
        "manifest_artifact_sha256": snapshot["production_manifest"][
            "artifact_sha256"
        ],
        "beta_input_id": metadata[0]["artifact_id"],
        "beta_input_content_sha256": metadata[0]["content_sha256"],
        "beta_input_artifact_sha256": metadata[0]["artifact_sha256"],
        "component_input_id": metadata[1]["artifact_id"],
        "component_input_content_sha256": metadata[1]["content_sha256"],
        "component_input_artifact_sha256": metadata[1]["artifact_sha256"],
        "valid_beta_date_count": required_fields["valid_beta_date_count"],
        "lag_pair_counts_0_through_20": pair_counts,
        "long_run_variance": omega,
        "component_count_census_sha256": required_fields["component_count_census_sha256"],
        "component_count_census_session_count": CALIBRATION_SESSION_COUNT,
        "q05_components_per_date": planned.q05_components_per_date,
        "raw_required_valid_dates": planned.raw_required_valid_dates,
        "required_valid_dates": planned.required_valid_dates,
        "required_connected_components": planned.required_connected_components,
        "fixed_h20_test_session_capacity": planned.fixed_h20_test_session_capacity,
        "disposition": planned.disposition,
        "definition": _freeze(receipt_raw),
        "_authority": _LOADED_RECEIPT,
    }.items():
        object.__setattr__(value, name, item)
    fingerprint = _receipt_fingerprint(value)
    key = id(value)
    ref = weakref.ref(
        value,
        lambda item, k=key: _forget_power_receipt_authority(k, item),
    )
    with _POWER_RECEIPT_AUTHORITIES_LOCK:
        _POWER_RECEIPT_AUTHORITIES[key] = _PowerReceiptAuthorityRecord(
            reference=ref,
            content_contract=weakref.ref(content_contract),
            manifest_candidate=weakref.ref(manifest_candidate),
            input_authority=weakref.ref(input_authority),
            beta_artifact=_artifact_identity(
                beta_path,
                beta_payload,
                artifact_sha256=metadata[0]["artifact_sha256"],
                byte_count=metadata[0]["byte_count"],
                name="date-beta input",
            ),
            component_artifact=_artifact_identity(
                component_path,
                component_payload,
                artifact_sha256=metadata[1]["artifact_sha256"],
                byte_count=metadata[1]["byte_count"],
                name="component-count input",
            ),
            fingerprint=fingerprint,
            persisted_receipt=None,
        )
    return value


def render_power_calibration_receipt(receipt: PowerCalibrationReceipt) -> str:
    """Render canonical receipt bytes without exposing hidden intermediates."""
    require_loaded_power_calibration_receipt(receipt)
    return _render(_thaw(receipt.definition)).decode("utf-8")


def _bind_persisted_receipt(
    receipt: PowerCalibrationReceipt, identity: _ArtifactIdentity
) -> None:
    with _POWER_RECEIPT_AUTHORITIES_LOCK:
        record = _POWER_RECEIPT_AUTHORITIES.get(id(receipt))
        if record is None or record.reference() is not receipt:
            raise PowerCalibrationReceiptError("power receipt authority disappeared")
        existing = record.persisted_receipt
        if existing is not None and existing != identity:
            raise PowerCalibrationReceiptError(
                "power receipt is already bound to a different persisted artifact"
            )
        _POWER_RECEIPT_AUTHORITIES[id(receipt)] = dataclasses.replace(
            record, persisted_receipt=identity
        )


def power_calibration_receipt_filename(receipt: PowerCalibrationReceipt) -> str:
    """Return the sole content-versioned filename accepted by persistence."""
    require_loaded_power_calibration_receipt(receipt)
    return f"{receipt.receipt_id}.{receipt.receipt_hash}.json"


def persist_power_calibration_receipt(
    receipt: PowerCalibrationReceipt, receipt_path: Path
) -> Path:
    """Atomically create one exact receipt; never replace existing bytes."""
    # Keep the write capability function-local so this module cannot re-export
    # it to adjacent lane modules as a global callable alias.
    from .artifact_io import create_new_regular_atomically

    require_loaded_power_calibration_receipt(receipt)
    payload = _render(_thaw(receipt.definition))
    requested = Path(receipt_path)
    if requested.name != f"{receipt.receipt_id}.{receipt.receipt_hash}.json":
        raise PowerCalibrationReceiptError(
            "numeric receipt filename is not content-versioned"
        )
    try:
        normalized_requested = requested.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise PowerCalibrationReceiptError(
            "numeric receipt destination is invalid"
        ) from exc
    with _POWER_RECEIPT_AUTHORITIES_LOCK:
        record = _POWER_RECEIPT_AUTHORITIES.get(id(receipt))
        if record is None or record.reference() is not receipt:
            raise PowerCalibrationReceiptError("power receipt authority disappeared")
        if (
            record.persisted_receipt is not None
            and record.persisted_receipt.path != normalized_requested
        ):
            raise PowerCalibrationReceiptError(
                "power receipt is already bound to another path"
            )
        # Serialize the complete one-receipt transaction.  Otherwise two
        # destinations can both be durably created before either thread binds
        # the sole accepted path in the registry.
        try:
            destination = create_new_regular_atomically(
                requested,
                payload,
                name="numeric power receipt",
                maximum_bytes=MAX_INPUT_ARTIFACT_BYTES,
            )
        except ArtifactIOError as exc:
            raise PowerCalibrationReceiptError(
                "atomic numeric receipt persistence failed"
            ) from exc

        persisted_path, persisted_payload = _read_stable_regular(
            destination, "numeric power receipt"
        )
        if persisted_payload != payload:
            raise PowerCalibrationReceiptError(
                "persisted numeric receipt bytes changed after creation"
            )
        identity = _artifact_identity(
            persisted_path,
            persisted_payload,
            artifact_sha256=hashlib.sha256(payload).hexdigest(),
            byte_count=len(payload),
            name="numeric power receipt",
        )
        _bind_persisted_receipt(receipt, identity)
        require_persisted_power_calibration_receipt(receipt)
        return persisted_path


def _preflight_persisted_receipt(
    raw: dict[str, Any],
    *,
    content_contract: PowerCalibrationInputContentContract,
    manifest_candidate: ProductionCalibrationInputManifestCandidate,
    input_authority: PowerCalibrationInputAuthority,
) -> None:
    """Reject a wrong receipt envelope before either sensitive input is opened."""
    _require_keys(raw, RECEIPT_ROOT_FIELDS, "numeric power receipt")
    if (
        raw["schema"] != RECEIPT_SCHEMA
        or raw["status"] != RECEIPT_STATUS
        or raw["authority"] != RECEIPT_AUTHORITY
        or raw
        != _content_identity(
            raw,
            id_field="receipt_id",
            hash_field="receipt_hash",
            prefix=RECEIPT_ID_PREFIX,
        )
    ):
        raise PowerCalibrationReceiptError("numeric power receipt identity changed")
    required = _require_keys(
        raw["required_receipt_fields"],
        REQUIRED_RECEIPT_FIELDS,
        "required receipt fields",
    )
    if (
        required["protocol_id"] != POWER_PROTOCOL_ID
        or required["protocol_hash"] != POWER_PROTOCOL_HASH
        or required["calibration_input_manifest_sha256"]
        != manifest_candidate.manifest_artifact_sha256
    ):
        raise PowerCalibrationReceiptError("required receipt ancestry changed")
    expected_contract = _binding(
        artifact_id=content_contract.content_contract_id,
        content_sha256=content_contract.content_contract_hash,
        artifact_sha256=CONTENT_CONTRACT_ARTIFACT_SHA256,
    )
    expected_manifest = _binding(
        artifact_id=manifest_candidate.manifest_id,
        content_sha256=manifest_candidate.manifest_content_sha256,
        artifact_sha256=manifest_candidate.manifest_artifact_sha256,
    )
    expected_evidence = _binding(
        artifact_id=manifest_candidate.evidence_bundle_id,
        content_sha256=manifest_candidate.evidence_bundle_content_sha256,
        artifact_sha256=manifest_candidate.evidence_bundle_artifact_sha256,
    )
    expected_authority = {
        "authority_id": input_authority.authority_id,
        "authority_hash": input_authority.authority_hash,
        "owner_authorization_id": input_authority.owner_authorization_id,
        "owner_authorization_evidence_sha256": (
            input_authority.owner_authorization_evidence_sha256
        ),
        "production_truth_approval_id": (
            input_authority.production_truth_approval_id
        ),
        "production_truth_approval_hash": (
            input_authority.production_truth_approval_hash
        ),
        "production_truth_approval_artifact_sha256": (
            input_authority.production_truth_approval_artifact_sha256
        ),
    }
    expected_inputs = [
        {
            "role": item["role"],
            "artifact_id": item["artifact_id"],
            "content_sha256": item["content_sha256"],
            "artifact_sha256": item["artifact_sha256"],
        }
        for item in _candidate_bindings(manifest_candidate)
    ]
    if (
        raw["content_contract_binding"] != expected_contract
        or raw["input_authority_binding"] != expected_authority
        or raw["production_manifest_binding"] != expected_manifest
        or raw["evidence_bundle_binding"] != expected_evidence
        or raw["input_artifact_bindings"] != expected_inputs
    ):
        raise PowerCalibrationReceiptError("numeric power receipt binding changed")


def load_power_calibration_receipt(
    receipt_path: Path,
    *,
    content_contract: PowerCalibrationInputContentContract,
    manifest_candidate: ProductionCalibrationInputManifestCandidate,
    input_authority: PowerCalibrationInputAuthority,
    beta_series_path: Path,
    component_count_path: Path,
) -> PowerCalibrationReceipt:
    """Recompute from exact inputs, then accept only identical receipt bytes."""
    resolved, payload = _read_stable_regular(receipt_path, "numeric power receipt")
    raw = _parse(payload, "numeric power receipt")
    require_loaded_power_calibration_input_content_contract(content_contract)
    require_loaded_production_calibration_input_manifest_candidate(manifest_candidate)
    require_loaded_power_calibration_input_authority(input_authority)
    _preflight_persisted_receipt(
        raw,
        content_contract=content_contract,
        manifest_candidate=manifest_candidate,
        input_authority=input_authority,
    )
    expected_filename = f"{raw['receipt_id']}.{raw['receipt_hash']}.json"
    if Path(receipt_path).name != expected_filename:
        raise PowerCalibrationReceiptError(
            "numeric receipt filename is not content-versioned"
        )
    receipt = compute_power_calibration_receipt(
        content_contract,
        manifest_candidate,
        input_authority=input_authority,
        beta_series_path=beta_series_path,
        component_count_path=component_count_path,
    )
    if raw != _thaw(receipt.definition):
        raise PowerCalibrationReceiptError(
            "persisted numeric power receipt differs from recomputation"
        )
    _revalidate(resolved, payload, "numeric power receipt")
    require_loaded_power_calibration_receipt(receipt)
    _revalidate(resolved, payload, "numeric power receipt")
    _bind_persisted_receipt(
        receipt,
        _artifact_identity(
            resolved,
            payload,
            artifact_sha256=hashlib.sha256(payload).hexdigest(),
            byte_count=len(payload),
            name="numeric power receipt",
        ),
    )
    return receipt


def require_loaded_power_calibration_receipt(
    receipt: PowerCalibrationReceipt,
) -> PowerCalibrationReceipt:
    """Reauthenticate the receipt, authority, parents, and both source bytes."""
    if type(receipt) is not PowerCalibrationReceipt or getattr(receipt, "_authority", None) is not _LOADED_RECEIPT:
        raise PowerCalibrationReceiptError("power receipt is not worker-authenticated")
    with _POWER_RECEIPT_AUTHORITIES_LOCK:
        record = _POWER_RECEIPT_AUTHORITIES.get(id(receipt))
    if record is None or record.reference() is not receipt:
        raise PowerCalibrationReceiptError("power receipt authority is absent")
    if _receipt_fingerprint(receipt) != record.fingerprint:
        raise PowerCalibrationReceiptError("power receipt object changed")
    content_contract = record.content_contract()
    manifest_candidate = record.manifest_candidate()
    input_authority = record.input_authority()
    if (
        content_contract is None
        or manifest_candidate is None
        or input_authority is None
    ):
        raise PowerCalibrationReceiptError("power receipt parent was released")
    _reauthenticate_artifact_identity(record.beta_artifact, "date-beta input")
    _reauthenticate_artifact_identity(
        record.component_artifact, "component-count input"
    )
    require_loaded_power_calibration_input_content_contract(content_contract)
    require_loaded_production_calibration_input_manifest_candidate(manifest_candidate)
    require_loaded_power_calibration_input_authority(input_authority)
    if record.persisted_receipt is not None:
        _reauthenticate_artifact_identity(
            record.persisted_receipt, "numeric power receipt"
        )
    _reauthenticate_artifact_identity(record.beta_artifact, "date-beta input")
    _reauthenticate_artifact_identity(
        record.component_artifact, "component-count input"
    )
    return receipt


def _require_closed_receipt_registry_state(
    receipt: PowerCalibrationReceipt,
) -> tuple[
    _PowerReceiptAuthorityRecord,
    PowerCalibrationInputContentContract,
    ProductionCalibrationInputManifestCandidate,
    PowerCalibrationInputAuthority,
]:
    if (
        type(receipt) is not PowerCalibrationReceipt
        or getattr(receipt, "_authority", None) is not _LOADED_RECEIPT
    ):
        raise PowerCalibrationReceiptError(
            "power receipt is not worker-authenticated"
        )
    with _POWER_RECEIPT_AUTHORITIES_LOCK:
        record = _POWER_RECEIPT_AUTHORITIES.get(id(receipt))
    if record is None or record.reference() is not receipt:
        raise PowerCalibrationReceiptError("power receipt authority is absent")
    if _receipt_fingerprint(receipt) != record.fingerprint:
        raise PowerCalibrationReceiptError("power receipt object changed")
    content_contract = record.content_contract()
    manifest_candidate = record.manifest_candidate()
    input_authority = record.input_authority()
    if (
        content_contract is None
        or manifest_candidate is None
        or input_authority is None
    ):
        raise PowerCalibrationReceiptError("power receipt parent was released")
    return record, content_contract, manifest_candidate, input_authority


def _require_stored_input_identities(
    receipt: PowerCalibrationReceipt,
    record: _PowerReceiptAuthorityRecord,
    manifest_candidate: ProductionCalibrationInputManifestCandidate,
) -> None:
    bindings = _candidate_bindings(manifest_candidate)
    if (
        tuple(item["role"] for item in bindings) != INPUT_ROLES
        or record.beta_artifact.artifact_sha256
        != bindings[0]["artifact_sha256"]
        or record.beta_artifact.byte_count != bindings[0]["byte_count"]
        or record.component_artifact.artifact_sha256
        != bindings[1]["artifact_sha256"]
        or record.component_artifact.byte_count != bindings[1]["byte_count"]
        or receipt.beta_input_id != bindings[0]["artifact_id"]
        or receipt.beta_input_content_sha256 != bindings[0]["content_sha256"]
        or receipt.beta_input_artifact_sha256
        != bindings[0]["artifact_sha256"]
        or receipt.component_input_id != bindings[1]["artifact_id"]
        or receipt.component_input_content_sha256
        != bindings[1]["content_sha256"]
        or receipt.component_input_artifact_sha256
        != bindings[1]["artifact_sha256"]
    ):
        raise PowerCalibrationReceiptError(
            "stored calibration input identities changed"
        )


def require_persisted_power_calibration_receipt(
    receipt: PowerCalibrationReceipt,
) -> PowerCalibrationReceipt:
    """Authenticate closed persisted evidence without opening calibration inputs."""
    record, content_contract, manifest_candidate, input_authority = (
        _require_closed_receipt_registry_state(receipt)
    )
    if record.persisted_receipt is None:
        raise PowerCalibrationReceiptError(
            "power receipt has no authenticated persisted artifact"
        )
    require_loaded_power_calibration_input_content_contract(content_contract)
    require_loaded_production_calibration_input_manifest_candidate(manifest_candidate)
    require_loaded_power_calibration_input_authority(input_authority)
    _preflight_persisted_receipt(
        _thaw(receipt.definition),
        content_contract=content_contract,
        manifest_candidate=manifest_candidate,
        input_authority=input_authority,
    )
    _require_stored_input_identities(receipt, record, manifest_candidate)
    persisted_payload = _reauthenticate_artifact_identity(
        record.persisted_receipt, "numeric power receipt"
    )
    persisted_raw = _parse(persisted_payload, "numeric power receipt")
    if persisted_raw != _thaw(receipt.definition):
        raise PowerCalibrationReceiptError(
            "persisted numeric receipt content changed"
        )
    require_loaded_power_calibration_input_content_contract(content_contract)
    require_loaded_production_calibration_input_manifest_candidate(manifest_candidate)
    require_loaded_power_calibration_input_authority(input_authority)
    _require_stored_input_identities(receipt, record, manifest_candidate)
    _reauthenticate_artifact_identity(
        record.persisted_receipt, "numeric power receipt"
    )
    return receipt


def power_calibration_receipt_artifact_sha256(
    receipt: PowerCalibrationReceipt,
) -> str:
    """Return the exact persisted artifact SHA after closed reauthentication."""
    require_persisted_power_calibration_receipt(receipt)
    with _POWER_RECEIPT_AUTHORITIES_LOCK:
        record = _POWER_RECEIPT_AUTHORITIES.get(id(receipt))
    if record is None or record.persisted_receipt is None:
        raise PowerCalibrationReceiptError("persisted receipt authority disappeared")
    return record.persisted_receipt.artifact_sha256


def render_expected_power_calibration_input_content_contract() -> str:
    """Render the sole canonical checked-in ARV2-4D-B content contract."""
    return _render(_contract_document()).decode("utf-8")
