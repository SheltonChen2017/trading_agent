"""Authenticated outcome-free ARV2 stock-v3 power-floor successor.

The successor built here is an additive child of the unchanged ARV2-4C stock
successor.  It binds one *persisted* nuisance-calibration receipt and carries
forward only the receipt's required date/component floors and fixed-capacity
disposition.  It cannot read source data or outcomes, operate QuantConnect,
inspect results, deploy, order, or trade.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import threading
import weakref
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from .artifact_io import (
    ArtifactIOError,
    _register_process_local_after_fork,
    read_stable_regular as _read_artifact_stable_regular,
    revalidate_regular as _revalidate_artifact_regular,
)
from .four_family_multiplicity import (
    OVERLAY_ARTIFACT_SHA256,
    FourFamilyMultiplicityError,
    FourFamilyMultiplicityOverlay,
    require_loaded_four_family_multiplicity_overlay,
)
from .global_benchmark_contract import (
    SUCCESSOR_BINDING,
    GlobalBenchmarkContract,
    GlobalBenchmarkContractError,
    require_loaded_global_benchmark_contract,
)
from .power_calibration_input_manifest import (
    FOUR_FAMILY_OVERLAY_HASH,
    FOUR_FAMILY_OVERLAY_ID,
)
from .power_calibration_input_schema import (
    POWER_PROTOCOL_ARTIFACT_SHA256,
    POWER_PROTOCOL_HASH,
    POWER_PROTOCOL_ID,
)
from .power_calibration_protocol import (
    MINIMUM_ABSOLUTE_FLOOR,
    TEST_SESSION_CAPACITY,
    PowerCalibrationProtocol,
    PowerCalibrationProtocolError,
    ProvisionalPowerDisposition,
    require_loaded_power_calibration_protocol,
)
class StockPowerSuccessorError(ValueError):
    """The stock-v3 successor or one of its exact parents is unauthentic."""


MAX_AUTHENTICATED_ARTIFACT_BYTES = 4 * 1024 * 1024

SCHEMA = "arv2-stock-historical-power-successor-structural-v3"
ID_PREFIX = "arv2-stock-historical-power-successor-"
AUTHORITY = (
    "power_floor_binding_only_no_source_outcome_qc_result_deployment_order_or_"
    "trading_authority"
)
FEASIBLE_STATUS = (
    "feasible_fixed_design_candidate_pending_independent_review_counter_review_"
    "and_separate_ARV2_4_authority"
)
UNDERPOWERED_STATUS = (
    "underpowered_fixed_design_hard_no_launch_pending_independent_review_and_"
    "counter_review"
)

_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")

_CAPABILITIES = MappingProxyType(
    {
        "source_access": False,
        "calibration_input_access": False,
        "outcome_access": False,
        "arv2_4_outcome_evaluation": False,
        "research_result_access": False,
        "research_result_disposition": False,
        "qc_upload": False,
        "qc_compile": False,
        "qc_launch": False,
        "paper_deployment": False,
        "funded_deployment": False,
        "orders": False,
        "trading": False,
    }
)

_DIRECT_PARENT_ROLES = (
    "stock_successor_v2",
    "power_calibration_protocol",
    "four_family_multiplicity_overlay",
    "numeric_power_receipt",
)

_DIRECT_PARENT_EDGES = tuple(
    ("stock_successor_v3", parent) for parent in _DIRECT_PARENT_ROLES
)


def _direct_parent_edge_documents() -> list[dict[str, str]]:
    """Materialize fresh JSON objects from the immutable edge contract."""
    return [
        {"child": child, "parent": parent}
        for child, parent in _DIRECT_PARENT_EDGES
    ]


_POWER_AMENDMENT_FIELDS = (
    "calibration_input_manifest_sha256",
    "numeric_power_receipt_sha256",
    "power_plan_sha256",
    "required_valid_dates",
    "required_connected_components",
    "fixed_capacity_disposition",
)


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
        raise StockPowerSuccessorError("noncanonical JSON value") from exc


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
        raise StockPowerSuccessorError("noncanonical JSON value") from exc


def _content_identity(raw: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(raw)
    value["spec_id"] = None
    value["spec_hash"] = None
    digest = hashlib.sha256(_canonical(value)).hexdigest()
    value["spec_hash"] = digest
    value["spec_id"] = f"{ID_PREFIX}{digest[:16]}"
    return value


def _binding(
    *, artifact_id: str, content_sha256: str, artifact_sha256: str
) -> dict[str, str]:
    return {
        "artifact_id": artifact_id,
        "content_sha256": content_sha256,
        "artifact_sha256": artifact_sha256,
    }


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
            raise StockPowerSuccessorError(
                "stock power successor contains a noncanonical mapping key"
            )
        return (
            "mapping",
            tuple(sorted((key, _fingerprint(item)) for key, item in value.items())),
        )
    if type(value) is tuple:
        return ("tuple", tuple(_fingerprint(item) for item in value))
    if type(value) is ProvisionalPowerDisposition:
        return ("disposition", value.value)
    if type(value) is str:
        return ("str", value)
    if type(value) is bool:
        return ("bool", value)
    if type(value) is int:
        return ("int", value)
    if value is None:
        return ("none", None)
    raise StockPowerSuccessorError(
        "stock power successor contains noncanonical authority state"
    )


def _read_stable_regular(path: Path, name: str) -> tuple[Path, bytes]:
    try:
        return _read_artifact_stable_regular(
            Path(path),
            name=name,
            maximum_bytes=MAX_AUTHENTICATED_ARTIFACT_BYTES,
        )
    except ArtifactIOError as exc:
        raise StockPowerSuccessorError(str(exc)) from exc


def _revalidate(path: Path, payload: bytes, name: str) -> None:
    try:
        _revalidate_artifact_regular(
            path,
            payload,
            name=name,
            maximum_bytes=MAX_AUTHENTICATED_ARTIFACT_BYTES,
        )
    except ArtifactIOError as exc:
        raise StockPowerSuccessorError(str(exc)) from exc


def _reject_float(value: str) -> None:
    del value
    raise StockPowerSuccessorError("binary floating-point is forbidden")


def _reject_constant(value: str) -> None:
    del value
    raise StockPowerSuccessorError("non-finite JSON is forbidden")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise StockPowerSuccessorError("duplicate JSON key is forbidden")
        value[key] = item
    return value


def _parse(payload: bytes) -> dict[str, Any]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StockPowerSuccessorError("stock-v3 successor is not UTF-8") from exc
    try:
        raw = json.loads(
            text,
            object_pairs_hook=_object,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except StockPowerSuccessorError:
        raise
    except (ValueError, RecursionError) as exc:
        raise StockPowerSuccessorError(
            "stock-v3 successor is not strict JSON"
        ) from exc
    if type(raw) is not dict:
        raise StockPowerSuccessorError("stock-v3 successor root must be an object")
    if payload != _render(raw):
        raise StockPowerSuccessorError("stock-v3 successor bytes are not canonical")
    return raw


def _require_sha256(value: object, name: str) -> str:
    if type(value) is not str or _HEX_64.fullmatch(value) is None:
        raise StockPowerSuccessorError(f"{name} must be lowercase SHA-256")
    return value


def _validate_content_identity(raw: Mapping[str, Any]) -> None:
    if set(raw) != {
        "schema",
        "status",
        "authority",
        "spec_id",
        "spec_hash",
        "evaluation_id",
        "direct_parent_bindings",
        "inheritance_contract",
        "power_amendment",
        "disposition_gate",
        "direct_parent_projection",
        "capabilities",
    }:
        raise StockPowerSuccessorError("stock-v3 successor fields changed")
    expected = _content_identity(raw)
    if (
        type(raw.get("spec_id")) is not str
        or type(raw.get("spec_hash")) is not str
        or raw["spec_id"] != expected["spec_id"]
        or raw["spec_hash"] != expected["spec_hash"]
    ):
        raise StockPowerSuccessorError("stock-v3 successor identity changed")


def _validate_direct_parent_projection(
    raw: Mapping[str, Any],
) -> Mapping[str, tuple[str, ...]]:
    """Validate the bounded direct-edge projection, never a full ancestry DAG."""
    projection = raw.get("direct_parent_projection")
    expected_fields = {
        "projection_scope",
        "child_node",
        "ordered_direct_parent_nodes",
        "ordered_direct_edges",
        "complete_ancestry_graph",
        "parent_subgraphs",
    }
    if type(projection) is not dict or set(projection) != expected_fields:
        raise StockPowerSuccessorError("stock-v3 direct-parent projection changed")
    parents = projection["ordered_direct_parent_nodes"]
    edges = projection["ordered_direct_edges"]
    if (
        projection["projection_scope"]
        != "stock_successor_v3_direct_edges_only_not_complete_ancestry"
        or projection["child_node"] != "stock_successor_v3"
        or type(parents) is not list
        or len(parents) != len(_DIRECT_PARENT_ROLES)
        or tuple(parents) != _DIRECT_PARENT_ROLES
        or type(edges) is not list
        or len(edges) != len(_DIRECT_PARENT_ROLES)
        or edges != _direct_parent_edge_documents()
        or projection["complete_ancestry_graph"] is not False
        or projection["parent_subgraphs"]
        != "authenticated_by_each_parent_loader_and_deliberately_not_redeclared"
    ):
        raise StockPowerSuccessorError(
            "stock-v3 direct-parent projection is invalid"
        )
    return MappingProxyType({"stock_successor_v3": tuple(parents)})


def _validate_power_amendment(value: object) -> None:
    if type(value) is not dict or tuple(sorted(value)) != tuple(
        sorted(_POWER_AMENDMENT_FIELDS)
    ):
        raise StockPowerSuccessorError("power amendment fields changed")
    for field in (
        "calibration_input_manifest_sha256",
        "numeric_power_receipt_sha256",
        "power_plan_sha256",
    ):
        _require_sha256(value[field], field.replace("_", " "))
    if (
        type(value["required_valid_dates"]) is not int
        or value["required_valid_dates"] < MINIMUM_ABSOLUTE_FLOOR
        or type(value["required_connected_components"]) is not int
        or value["required_connected_components"] < MINIMUM_ABSOLUTE_FLOOR
        or type(value["fixed_capacity_disposition"]) is not str
    ):
        raise StockPowerSuccessorError("power amendment value type changed")


def _authenticate_receipt_parent(power_receipt: Any) -> str | None:
    """Return only the closed artifact identity; never retain/raise the facade."""
    # Restricted Python objects remain in this synchronous frame only.  No
    # exception may carry the frame (and therefore its locals) to a caller.
    try:
        from .power_calibration_receipt import (
            power_calibration_receipt_artifact_sha256,
            require_persisted_power_calibration_receipt,
        )

        require_persisted_power_calibration_receipt(power_receipt)
        return power_calibration_receipt_artifact_sha256(power_receipt)
    except BaseException:
        return None


def _authenticate_parents(
    stock_contract: GlobalBenchmarkContract,
    power_protocol: PowerCalibrationProtocol,
    multiplicity_overlay: FourFamilyMultiplicityOverlay,
    power_receipt: Any,
) -> Mapping[str, Any]:
    try:
        require_loaded_global_benchmark_contract(stock_contract)
        require_loaded_power_calibration_protocol(power_protocol)
        require_loaded_four_family_multiplicity_overlay(multiplicity_overlay)
    except (
        GlobalBenchmarkContractError,
        PowerCalibrationProtocolError,
        FourFamilyMultiplicityError,
    ) as exc:
        raise StockPowerSuccessorError(
            "stock-v3 direct-parent authentication failed"
        ) from exc
    receipt_artifact_sha256 = _authenticate_receipt_parent(power_receipt)
    if receipt_artifact_sha256 is None:
        raise StockPowerSuccessorError(
            "stock-v3 direct-parent authentication failed"
        )

    # Capture every value that may influence emitted bytes or loaded fields once.
    # The caller compares two complete immutable snapshots, so document building
    # never mixes parent state from different instants.
    stock_spec_id = stock_contract.successor_spec_id
    stock_spec_hash = stock_contract.successor_spec_hash
    evaluation_id = stock_contract.evaluation_id
    protocol_id = power_protocol.protocol_id
    protocol_hash = power_protocol.protocol_hash
    protocol_evaluation_id = power_protocol.evaluation_id
    protocol_stock_binding = _thaw(power_protocol.definition)["bound_ancestry"][
        "stock_successor_v2"
    ]
    overlay_id = multiplicity_overlay.overlay_id
    overlay_hash = multiplicity_overlay.overlay_hash
    receipt_id = power_receipt.receipt_id
    receipt_hash = power_receipt.receipt_hash
    receipt_protocol_id = power_receipt.protocol_id
    receipt_protocol_hash = power_receipt.protocol_hash
    manifest_artifact_sha256 = power_receipt.manifest_artifact_sha256
    raw_required_valid_dates = power_receipt.raw_required_valid_dates
    required_valid_dates = power_receipt.required_valid_dates
    q05_components_per_date = power_receipt.q05_components_per_date
    required_connected_components = power_receipt.required_connected_components
    fixed_h20_test_session_capacity = power_receipt.fixed_h20_test_session_capacity
    disposition = power_receipt.disposition

    stock_binding = dict(SUCCESSOR_BINDING)
    if (
        stock_spec_id != stock_binding["artifact_id"]
        or stock_spec_hash != stock_binding["content_sha256"]
        or protocol_id != POWER_PROTOCOL_ID
        or protocol_hash != POWER_PROTOCOL_HASH
        or overlay_id != FOUR_FAMILY_OVERLAY_ID
        or overlay_hash != FOUR_FAMILY_OVERLAY_HASH
        or receipt_protocol_id != protocol_id
        or receipt_protocol_hash != protocol_hash
        or evaluation_id != protocol_evaluation_id
    ):
        raise StockPowerSuccessorError("stock-v3 direct-parent identity changed")
    if protocol_stock_binding != stock_binding:
        raise StockPowerSuccessorError(
            "power protocol is not bound to the exact stock-v2 parent"
        )
    for value, name in (
        (receipt_artifact_sha256, "numeric receipt artifact hash"),
        (manifest_artifact_sha256, "input manifest artifact hash"),
    ):
        _require_sha256(value, name)
    if (
        type(raw_required_valid_dates) is not int
        or raw_required_valid_dates < 1
        or type(required_valid_dates) is not int
        or required_valid_dates != max(MINIMUM_ABSOLUTE_FLOOR, raw_required_valid_dates)
        or type(q05_components_per_date) is not int
        or q05_components_per_date < 0
        or type(required_connected_components) is not int
        or required_connected_components
        != max(
            MINIMUM_ABSOLUTE_FLOOR,
            required_valid_dates * q05_components_per_date,
        )
        or type(fixed_h20_test_session_capacity) is not int
        or fixed_h20_test_session_capacity != TEST_SESSION_CAPACITY
        or type(disposition) is not ProvisionalPowerDisposition
    ):
        raise StockPowerSuccessorError("numeric receipt floor contract changed")
    expected_disposition = (
        ProvisionalPowerDisposition.UNDERPOWERED_FIXED_DESIGN_NO_LAUNCH
        if required_valid_dates > TEST_SESSION_CAPACITY
        else ProvisionalPowerDisposition.FEASIBLE_PENDING_AUTHENTICATED_RECEIPT
    )
    if disposition is not expected_disposition:
        raise StockPowerSuccessorError("numeric receipt disposition changed")

    return _freeze(
        {
            "evaluation_id": evaluation_id,
            "direct_parent_bindings": {
                "stock_successor_v2": stock_binding,
                "power_calibration_protocol": _binding(
                    artifact_id=protocol_id,
                    content_sha256=protocol_hash,
                    artifact_sha256=POWER_PROTOCOL_ARTIFACT_SHA256,
                ),
                "four_family_multiplicity_overlay": _binding(
                    artifact_id=overlay_id,
                    content_sha256=overlay_hash,
                    artifact_sha256=OVERLAY_ARTIFACT_SHA256,
                ),
                "numeric_power_receipt": _binding(
                    artifact_id=receipt_id,
                    content_sha256=receipt_hash,
                    artifact_sha256=receipt_artifact_sha256,
                ),
            },
            "power_amendment": {
                "calibration_input_manifest_sha256": manifest_artifact_sha256,
                "numeric_power_receipt_sha256": receipt_artifact_sha256,
                "power_plan_sha256": receipt_hash,
                "required_valid_dates": required_valid_dates,
                "required_connected_components": required_connected_components,
                "fixed_capacity_disposition": disposition.value,
            },
            "disposition": disposition,
        }
    )


def _successor_document(authenticated: Mapping[str, Any]) -> dict[str, Any]:
    disposition = authenticated["disposition"]
    underpowered = (
        disposition
        is ProvisionalPowerDisposition.UNDERPOWERED_FIXED_DESIGN_NO_LAUNCH
    )
    raw: dict[str, Any] = {
        "schema": SCHEMA,
        "status": UNDERPOWERED_STATUS if underpowered else FEASIBLE_STATUS,
        "authority": AUTHORITY,
        "spec_id": None,
        "spec_hash": None,
        "evaluation_id": authenticated["evaluation_id"],
        "direct_parent_bindings": _thaw(
            authenticated["direct_parent_bindings"]
        ),
        "inheritance_contract": {
            "stock_successor_v2_bytes_and_semantics_changed": False,
            "power_protocol_bytes_and_semantics_changed": False,
            "four_family_overlay_bytes_and_semantics_changed": False,
            "accepted_ancestor_repin_or_reparent": "forbidden",
            "only_explicit_amendment": "power_amendment",
            "power_amendment_field_inventory": list(_POWER_AMENDMENT_FIELDS),
            "all_other_stock_v2_rules": "inherited_unchanged",
        },
        "power_amendment": _thaw(authenticated["power_amendment"]),
        "disposition_gate": {
            "fixed_capacity_disposition_is_receipt_exact": True,
            "underpowered_effect": "hard_no_launch_no_rescue_or_alternate_design",
            "feasible_effect": (
                "candidate_only_pending_independent_review_counter_review_and_"
                "separate_exact_ARV2_4_outcome_authority"
            ),
            "current_effect": (
                "hard_no_launch"
                if underpowered
                else "candidate_pending_review_and_separate_ARV2_4_authority"
            ),
            "launch_authorized": False,
        },
        "direct_parent_projection": {
            "projection_scope": (
                "stock_successor_v3_direct_edges_only_not_complete_ancestry"
            ),
            "child_node": "stock_successor_v3",
            "ordered_direct_parent_nodes": list(_DIRECT_PARENT_ROLES),
            "ordered_direct_edges": _direct_parent_edge_documents(),
            "complete_ancestry_graph": False,
            "parent_subgraphs": (
                "authenticated_by_each_parent_loader_and_deliberately_not_redeclared"
            ),
        },
        "capabilities": dict(_CAPABILITIES),
    }
    return raw


def _document_from_snapshot(authenticated: Mapping[str, Any]) -> dict[str, Any]:
    return _content_identity(_successor_document(authenticated))


@dataclasses.dataclass(frozen=True, init=False)
class StockPowerSuccessor:
    """Loader-authenticated stock-v3 power binding with no action authority."""

    spec_id: str
    spec_hash: str
    status: str
    evaluation_id: str
    predecessor_spec_id: str
    power_protocol_id: str
    multiplicity_overlay_id: str
    numeric_power_receipt_id: str
    numeric_power_receipt_content_sha256: str
    numeric_power_receipt_sha256: str
    calibration_input_manifest_sha256: str
    power_plan_sha256: str
    required_valid_dates: int
    required_connected_components: int
    disposition: ProvisionalPowerDisposition
    direct_parent_projection: Mapping[str, tuple[str, ...]]
    capabilities: Mapping[str, bool]
    definition: Mapping[str, Any]
    _authority: object = dataclasses.field(repr=False, compare=False)

    def __init__(self) -> None:
        raise TypeError("stock power successors must be loaded from exact bytes")

    @property
    def fixed_design_feasible(self) -> bool:
        require_loaded_stock_power_successor(self)
        return (
            self.disposition
            is ProvisionalPowerDisposition.FEASIBLE_PENDING_AUTHENTICATED_RECEIPT
        )

    @property
    def power_plan_bound(self) -> bool:
        require_loaded_stock_power_successor(self)
        return True

    @property
    def hard_no_launch(self) -> bool:
        require_loaded_stock_power_successor(self)
        return not self.fixed_design_feasible

    @property
    def source_access_available(self) -> bool:
        return False

    @property
    def outcome_access_available(self) -> bool:
        return False

    @property
    def qc_action_available(self) -> bool:
        return False

    @property
    def result_access_available(self) -> bool:
        return False

    @property
    def result_disposition_available(self) -> bool:
        return False

    @property
    def deployment_available(self) -> bool:
        return False

    @property
    def orders_available(self) -> bool:
        return False

    @property
    def trading_available(self) -> bool:
        return False

    @property
    def launch_authorized(self) -> bool:
        return False


_LOADED_STOCK_POWER_SUCCESSOR_AUTHORITY = object()
_STOCK_POWER_SUCCESSOR_AUTHORITIES: dict[int, tuple[Any, ...]] = {}
_STOCK_POWER_SUCCESSOR_AUTHORITIES_LOCK = threading.RLock()
_INHERITED_STOCK_POWER_SUCCESSOR_AUTHORITY_QUARANTINE: list[object] = []


def _reset_process_local_stock_power_successor_authorities_after_fork() -> None:
    """Invalidate inherited successor authorities without running finalizers."""
    global _STOCK_POWER_SUCCESSOR_AUTHORITIES
    global _STOCK_POWER_SUCCESSOR_AUTHORITIES_LOCK
    inherited = _STOCK_POWER_SUCCESSOR_AUTHORITIES
    _INHERITED_STOCK_POWER_SUCCESSOR_AUTHORITY_QUARANTINE.append(inherited)
    _STOCK_POWER_SUCCESSOR_AUTHORITIES = {}
    _STOCK_POWER_SUCCESSOR_AUTHORITIES_LOCK = threading.RLock()


_register_process_local_after_fork(
    _reset_process_local_stock_power_successor_authorities_after_fork
)
del _register_process_local_after_fork


def _successor_fingerprint(value: StockPowerSuccessor) -> tuple[object, ...]:
    string_fields = (
        "spec_id",
        "spec_hash",
        "status",
        "evaluation_id",
        "predecessor_spec_id",
        "power_protocol_id",
        "multiplicity_overlay_id",
        "numeric_power_receipt_id",
        "numeric_power_receipt_content_sha256",
        "numeric_power_receipt_sha256",
        "calibration_input_manifest_sha256",
        "power_plan_sha256",
    )
    if any(type(getattr(value, name, None)) is not str for name in string_fields):
        raise StockPowerSuccessorError("stock power successor identity type changed")
    if (
        type(value.required_valid_dates) is not int
        or type(value.required_connected_components) is not int
        or type(value.disposition) is not ProvisionalPowerDisposition
    ):
        raise StockPowerSuccessorError("stock power successor floor type changed")
    try:
        return (
            *(getattr(value, name) for name in string_fields),
            value.required_valid_dates,
            value.required_connected_components,
            value.disposition,
            _fingerprint(value.direct_parent_projection),
            _fingerprint(value.capabilities),
            _fingerprint(value.definition),
        )
    except RecursionError as exc:
        raise StockPowerSuccessorError(
            "stock power successor authority state is too deeply nested"
        ) from exc


def _forget_authority(key: int, reference: Any) -> None:
    with _STOCK_POWER_SUCCESSOR_AUTHORITIES_LOCK:
        current = _STOCK_POWER_SUCCESSOR_AUTHORITIES.get(key)
        if current is not None and current[0] is reference:
            _STOCK_POWER_SUCCESSOR_AUTHORITIES.pop(key, None)


def render_stock_power_successor(
    *,
    stock_contract: GlobalBenchmarkContract,
    power_protocol: PowerCalibrationProtocol,
    multiplicity_overlay: FourFamilyMultiplicityOverlay,
    power_receipt: Any,
) -> str:
    """Build and render the exact stock-v3 child; rendering grants no action."""
    before = _authenticate_parents(
        stock_contract, power_protocol, multiplicity_overlay, power_receipt
    )
    document = _document_from_snapshot(before)
    after = _authenticate_parents(
        stock_contract, power_protocol, multiplicity_overlay, power_receipt
    )
    if before != after:
        raise StockPowerSuccessorError("stock-v3 direct parents changed while rendering")
    return _render(document).decode("utf-8")


def load_stock_power_successor(
    successor_path: Path,
    *,
    stock_contract: GlobalBenchmarkContract,
    power_protocol: PowerCalibrationProtocol,
    multiplicity_overlay: FourFamilyMultiplicityOverlay,
    power_receipt: Any,
) -> StockPowerSuccessor:
    """Authenticate exact successor bytes and all four direct parents twice."""
    before = _authenticate_parents(
        stock_contract, power_protocol, multiplicity_overlay, power_receipt
    )
    resolved, payload = _read_stable_regular(successor_path, "stock-v3 successor")
    raw = _parse(payload)
    _validate_content_identity(raw)
    _validate_power_amendment(raw.get("power_amendment"))
    projection = _validate_direct_parent_projection(raw)
    expected = _document_from_snapshot(before)
    if raw != expected:
        raise StockPowerSuccessorError("stock-v3 successor content changed")
    _revalidate(resolved, payload, "stock-v3 successor")
    after = _authenticate_parents(
        stock_contract, power_protocol, multiplicity_overlay, power_receipt
    )
    if before != after:
        raise StockPowerSuccessorError("stock-v3 direct parents changed while loading")
    _revalidate(resolved, payload, "stock-v3 successor")

    amendment = raw["power_amendment"]
    try:
        disposition = ProvisionalPowerDisposition(
            amendment["fixed_capacity_disposition"]
        )
    except ValueError as exc:
        raise StockPowerSuccessorError(
            "stock-v3 successor disposition is invalid"
        ) from exc
    value = object.__new__(StockPowerSuccessor)
    for name, item in {
        "spec_id": raw["spec_id"],
        "spec_hash": raw["spec_hash"],
        "status": raw["status"],
        "evaluation_id": raw["evaluation_id"],
        "predecessor_spec_id": raw["direct_parent_bindings"][
            "stock_successor_v2"
        ]["artifact_id"],
        "power_protocol_id": raw["direct_parent_bindings"][
            "power_calibration_protocol"
        ]["artifact_id"],
        "multiplicity_overlay_id": raw["direct_parent_bindings"][
            "four_family_multiplicity_overlay"
        ]["artifact_id"],
        "numeric_power_receipt_id": raw["direct_parent_bindings"][
            "numeric_power_receipt"
        ]["artifact_id"],
        "numeric_power_receipt_content_sha256": raw["direct_parent_bindings"][
            "numeric_power_receipt"
        ]["content_sha256"],
        "numeric_power_receipt_sha256": raw["direct_parent_bindings"][
            "numeric_power_receipt"
        ]["artifact_sha256"],
        "calibration_input_manifest_sha256": amendment[
            "calibration_input_manifest_sha256"
        ],
        "power_plan_sha256": amendment["power_plan_sha256"],
        "required_valid_dates": amendment["required_valid_dates"],
        "required_connected_components": amendment[
            "required_connected_components"
        ],
        "disposition": disposition,
        "direct_parent_projection": _freeze(projection),
        "capabilities": _freeze(raw["capabilities"]),
        "definition": _freeze(raw),
        "_authority": _LOADED_STOCK_POWER_SUCCESSOR_AUTHORITY,
    }.items():
        object.__setattr__(value, name, item)
    fingerprint = _successor_fingerprint(value)
    key = id(value)
    reference = weakref.ref(
        value, lambda item, identity=key: _forget_authority(identity, item)
    )
    with _STOCK_POWER_SUCCESSOR_AUTHORITIES_LOCK:
        _STOCK_POWER_SUCCESSOR_AUTHORITIES[key] = (
            reference,
            resolved,
            payload,
            stock_contract,
            power_protocol,
            multiplicity_overlay,
            power_receipt,
            before,
            fingerprint,
        )
    return value


def require_loaded_stock_power_successor(
    successor: StockPowerSuccessor,
) -> StockPowerSuccessor:
    """Reauthenticate object state, successor bytes, and all direct parents."""
    if (
        type(successor) is not StockPowerSuccessor
        or getattr(successor, "_authority", None)
        is not _LOADED_STOCK_POWER_SUCCESSOR_AUTHORITY
    ):
        raise StockPowerSuccessorError(
            "stock power successor is not loader-authenticated"
        )
    with _STOCK_POWER_SUCCESSOR_AUTHORITIES_LOCK:
        record = _STOCK_POWER_SUCCESSOR_AUTHORITIES.get(id(successor))
    if record is None or record[0]() is not successor:
        raise StockPowerSuccessorError("stock power successor authority is absent")
    if _successor_fingerprint(successor) != record[8]:
        raise StockPowerSuccessorError(
            "stock power successor changed after authentication"
        )
    _revalidate(record[1], record[2], "stock-v3 successor")
    current = _authenticate_parents(record[3], record[4], record[5], record[6])
    if current != record[7]:
        raise StockPowerSuccessorError(
            "stock power successor direct parents changed after authentication"
        )
    _revalidate(record[1], record[2], "stock-v3 successor")
    return successor
