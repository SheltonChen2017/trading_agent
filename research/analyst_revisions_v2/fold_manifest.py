"""Content-addressed, outcome-free walk-forward folds for ARV2-4.

The checked-in child manifest binds exact calendar partitions to the reviewed
QC-first plan and stock-evaluation definition.  It does not admit data, load
outcomes, launch QuantConnect, publish a result, deploy, or trade.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import threading
import weakref
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from data.exchange_calendar import (
    ExchangeCalendarError,
    resolve_nth_session_after,
    trading_sessions,
)

from .qc_first_plan import (
    QcFirstPlanError,
    QcFirstStudyPlan,
    load_qc_first_study_plan,
)
from .stock_controls import StructuralFoldBoundary, StockControlError
from .stock_evaluation_contract import (
    StockEvaluationContract,
    StockEvaluationContractError,
    load_stock_evaluation_contract,
)


class StockFoldManifestError(ValueError):
    """The structural fold manifest is malformed, weakened, or unauthentic."""


SCHEMA = "arv2-stock-walk-forward-fold-manifest-structural-v1"
STATUS = "implementation_frozen_outcome_free_pending_independent_review"
AUTHORITY = "structural_folds_only_no_data_outcome_qc_or_deployment_authority"
STRATEGY_PDF_SHA256 = (
    "eae7b9954aaf94212108505c52e31a558facd744967fd2526040d5147c616193"
)
PARENT_PLAN_ID = "arv2-qc-first-plan-36e455e72b8750fe"
PARENT_PLAN_HASH = (
    "36e455e72b8750fe3f34773382870e10e62f3f40b5392ae587690bda081b85dc"
)
PARENT_PLAN_ARTIFACT_SHA256 = (
    "8339238dd5ce32ed7b351aab2662fb408cc7d9a3c62ff89bf8b1d14f20acd081"
)
PARENT_STOCK_SPEC_ID = "arv2-stock-historical-c5ff2a6a0dcf341e"
PARENT_STOCK_SPEC_HASH = (
    "c5ff2a6a0dcf341e3c7bad4ea56e4a3c00f20faab5896c0fcd3bd7c291835a0b"
)
PARENT_STOCK_SPEC_ARTIFACT_SHA256 = (
    "34d1e71548bc6850a02590596594944dad3fadb38954067f2cc2d00dcaa86bc8"
)
PARENT_HISTORY_SECTION_SHA256 = (
    "5db2a1bc09d7ecd2e8cb7e5044f0abc7f97b3eefb71803002d00f6b33cf984ca"
)
EVALUATION_ID = "arv2-eval-stock-historical-qc-001"
HORIZONS = (1, 5, 20, 60)
TEST_YEARS = tuple(range(2020, 2026))

EXTERNAL_BINDINGS = {
    "review_commit": None,
    "counter_review_commit": None,
    "source_rights_receipt_id": None,
    "dataset_id": None,
    "common_event_component_inventory_sha256": None,
    "qc_project_id": None,
    "qc_run_id": None,
    "evaluation_receipt_id": None,
}

CAPABILITIES = {
    "source_access": False,
    "outcome_access": False,
    "qc_upload": False,
    "qc_compile": False,
    "qc_launch": False,
    "result_disposition": False,
    "paper_deployment": False,
    "funded_deployment": False,
    "orders": False,
}

_LOADED_FOLD_MANIFEST_AUTHORITY = object()
_FOLD_MANIFEST_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType["StockFoldManifest"],
        Path,
        Path,
        Path,
        bytes,
        bytes,
        tuple[object, ...],
    ],
] = {}
_FOLD_MANIFEST_AUTHORITIES_LOCK = threading.RLock()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


EXTERNAL_BINDINGS = _freeze(EXTERNAL_BINDINGS)
CAPABILITIES = _freeze(CAPABILITIES)


def _first_nyse_session(year: int) -> str:
    try:
        sessions = trading_sessions(date(year, 1, 1), date(year, 1, 15))
    except ExchangeCalendarError as exc:
        raise StockFoldManifestError(
            f"first NYSE session for {year} cannot be resolved"
        ) from exc
    if not sessions:
        raise StockFoldManifestError(f"first NYSE session for {year} is absent")
    return sessions[0].isoformat()


def _calendar_contract() -> dict[str, object]:
    try:
        sessions = tuple(
            item.isoformat()
            for item in trading_sessions(date(2013, 1, 2), date(2026, 8, 28))
        )
    except ExchangeCalendarError as exc:
        raise StockFoldManifestError("NYSE session axis cannot be resolved") from exc
    return {
        "exchange": "XNYS",
        "calendar_implementation": "pandas_market_calendars.NYSE",
        "axis_start_inclusive": "2013-01-02",
        "axis_end_inclusive": "2026-08-28",
        "axis_encoding": "canonical_json_ordered_iso_session_array_no_terminator",
        "axis_session_count": len(sessions),
        "axis_sha256": hashlib.sha256(_canonical(sessions)).hexdigest(),
    }


def _fold_record(test_year: int) -> dict[str, object]:
    fold_id = f"arv2-wf-test-{test_year}"
    train_start = _first_nyse_session(test_year - 7)
    train_end = _first_nyse_session(test_year - 2)
    validation_end = _first_nyse_session(test_year)
    test_end = _first_nyse_session(test_year + 1)
    boundaries: list[dict[str, object]] = []
    for horizon in HORIZONS:
        try:
            boundary = StructuralFoldBoundary.create(
                fold_id=f"{fold_id}-h{horizon}",
                horizon_sessions=horizon,
                purge_sessions=horizon,
                embargo_sessions=horizon,
                train_start=train_start,
                train_end_exclusive=train_end,
                validation_start=resolve_nth_session_after(train_end, horizon),
                validation_end_exclusive=validation_end,
                test_start=resolve_nth_session_after(validation_end, horizon),
                test_end_exclusive=test_end,
            )
        except (ExchangeCalendarError, StockControlError) as exc:
            raise StockFoldManifestError(
                f"{fold_id} horizon {horizon} cannot be resolved"
            ) from exc
        boundaries.append(
            {
                **boundary.to_record(),
                "structural_fold_sha256": boundary.structural_fold_sha256,
            }
        )
    content: dict[str, object] = {
        "fold_id": fold_id,
        "fold_sha256": None,
        "test_year": test_year,
        "nominal_train_interval": {
            "start_inclusive": train_start,
            "end_exclusive": train_end,
        },
        "nominal_validation_interval": {
            "start_inclusive": train_end,
            "end_exclusive": validation_end,
        },
        "nominal_test_interval": {
            "start_inclusive": validation_end,
            "end_exclusive": test_end,
        },
        "ordered_horizons_sessions": list(HORIZONS),
        "horizon_boundaries": boundaries,
    }
    digest = hashlib.sha256(_canonical(content)).hexdigest()
    content["fold_sha256"] = digest
    return content


def _walk_forward_contract() -> dict[str, object]:
    folds = [_fold_record(year) for year in TEST_YEARS]
    return {
        "rolling_or_expanding_rule": "rolling",
        "train_years": 5,
        "validation_years": 2,
        "test_years": 1,
        "step_years": 1,
        "calendar_anchor": "first_nyse_session_of_calendar_year",
        "interval_semantics": "half_open_nyse_session_intervals",
        "half_open_train_validation_test_session_intervals": (
            "materialized_in_each_fold_and_horizon_boundary"
        ),
        "gap_semantics": (
            "purge_is_train_end_exclusive_to_effective_validation_start_and_"
            "embargo_is_validation_end_exclusive_to_effective_test_start"
        ),
        "partial_2026_disposition": (
            "excluded_from_fixed_cutoff_evaluation_locked_no_blind_extension"
        ),
        "per_horizon_purge_and_embargo_intervals": (
            "materialized_for_1_5_20_60_sessions_each_equal_to_horizon"
        ),
        "cross_boundary_common_event_component_refusals": (
            "defined_in_cross_boundary_common_event_contract"
        ),
        "current_execution_authorized": False,
        "ordered_fold_ids": [fold["fold_id"] for fold in folds],
        "folds": folds,
    }


def _common_event_contract() -> dict[str, object]:
    return {
        "membership": (
            "deterministic_connected_components_of_security_decision_rows_and_"
            "all_admitted_common_event_ids"
        ),
        "cross_date_component_disposition": (
            "refuse_every_row_in_component_before_fold_assignment"
        ),
        "cross_boundary_component_disposition": (
            "refuse_entire_component_from_all_adjacent_samples"
        ),
        "outcome_duplication": False,
        "component_inventory_sha256": None,
        "component_count": None,
        "current_data_access_authorized": False,
    }


def _content_payload(raw: Mapping[str, Any]) -> bytes:
    payload = dict(raw)
    payload["manifest_id"] = None
    payload["manifest_hash"] = None
    return _canonical(payload)


def _expected_document() -> dict[str, object]:
    sections = {
        "calendar_contract": _calendar_contract(),
        "walk_forward_contract": _walk_forward_contract(),
        "cross_boundary_common_event_contract": _common_event_contract(),
    }
    raw: dict[str, object] = {
        "schema": SCHEMA,
        "status": STATUS,
        "authority": AUTHORITY,
        "manifest_id": None,
        "manifest_hash": None,
        "strategy_pdf_sha256": STRATEGY_PDF_SHA256,
        "parent_plan_id": PARENT_PLAN_ID,
        "parent_plan_hash": PARENT_PLAN_HASH,
        "parent_plan_artifact_sha256": PARENT_PLAN_ARTIFACT_SHA256,
        "parent_stock_spec_id": PARENT_STOCK_SPEC_ID,
        "parent_stock_spec_hash": PARENT_STOCK_SPEC_HASH,
        "parent_stock_spec_artifact_sha256": PARENT_STOCK_SPEC_ARTIFACT_SHA256,
        "parent_history_section_sha256": PARENT_HISTORY_SECTION_SHA256,
        "evaluation_id": EVALUATION_ID,
        **sections,
        "section_hashes": {
            name: hashlib.sha256(_canonical(value)).hexdigest()
            for name, value in sections.items()
        },
        "external_bindings": dict(EXTERNAL_BINDINGS),
        "capabilities": dict(CAPABILITIES),
    }
    digest = hashlib.sha256(_content_payload(raw)).hexdigest()
    raw["manifest_hash"] = digest
    raw["manifest_id"] = f"arv2-stock-folds-{digest[:16]}"
    return raw


_SECTION_NAMES = (
    "calendar_contract",
    "walk_forward_contract",
    "cross_boundary_common_event_contract",
)
_EXPECTED_DOCUMENT = _freeze(_expected_document())
_ROOT_KEYS = frozenset(_EXPECTED_DOCUMENT)


def _reject_float(value: str) -> None:
    raise StockFoldManifestError(f"binary floating-point is forbidden: {value}")


def _reject_constant(value: str) -> None:
    raise StockFoldManifestError(f"non-finite JSON is forbidden: {value}")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StockFoldManifestError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_stable_regular(path: Path, name: str) -> tuple[Path, bytes]:
    candidate = Path(path)
    absolute = candidate.absolute()
    if any(item.is_symlink() for item in (absolute, *absolute.parents)):
        raise StockFoldManifestError(f"{name} must not traverse a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise StockFoldManifestError(f"{name} is unavailable") from exc
    if resolved.is_symlink() or not resolved.is_file():
        raise StockFoldManifestError(f"{name} must be a regular file")
    try:
        before = resolved.stat()
        first = resolved.read_bytes()
        second = resolved.read_bytes()
        after = resolved.stat()
    except OSError as exc:
        raise StockFoldManifestError(f"{name} is unreadable") from exc
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if before_identity != after_identity or first != second:
        raise StockFoldManifestError(f"{name} changed while being read")
    return resolved, first


def _revalidate(path: Path, payload: bytes, name: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise StockFoldManifestError(f"{name} changed or disappeared")
    try:
        current = path.read_bytes()
    except OSError as exc:
        raise StockFoldManifestError(f"{name} changed or disappeared") from exc
    if current != payload:
        raise StockFoldManifestError(f"{name} changed after authentication")


def _require_exact(actual: object, expected: object, name: str) -> None:
    if isinstance(expected, Mapping):
        if type(actual) is not dict or set(actual) != set(expected):
            raise StockFoldManifestError(f"{name} changed from the frozen definition")
        for key, value in expected.items():
            _require_exact(actual[key], value, f"{name}.{key}")
        return
    if type(expected) is tuple:
        if type(actual) is not list or len(actual) != len(expected):
            raise StockFoldManifestError(f"{name} changed from the frozen definition")
        for index, (item, value) in enumerate(zip(actual, expected, strict=True)):
            _require_exact(item, value, f"{name}[{index}]")
        return
    if type(actual) is not type(expected) or actual != expected:
        raise StockFoldManifestError(f"{name} changed from the frozen definition")


def _validate_fold_structure(raw: Mapping[str, Any]) -> None:
    walk_forward = raw["walk_forward_contract"]
    folds = walk_forward["folds"]
    if walk_forward["ordered_fold_ids"] != [item["fold_id"] for item in folds]:
        raise StockFoldManifestError("ordered fold identities changed")
    prior_test_end: str | None = None
    for fold in folds:
        fold_payload = dict(fold)
        declared_fold_hash = fold_payload["fold_sha256"]
        fold_payload["fold_sha256"] = None
        if hashlib.sha256(_canonical(fold_payload)).hexdigest() != declared_fold_hash:
            raise StockFoldManifestError("fold content hash mismatch")
        if fold["ordered_horizons_sessions"] != [
            item["horizon_sessions"] for item in fold["horizon_boundaries"]
        ]:
            raise StockFoldManifestError("ordered fold horizons changed")
        nominal_test = fold["nominal_test_interval"]
        if (
            prior_test_end is not None
            and prior_test_end > nominal_test["start_inclusive"]
        ):
            raise StockFoldManifestError("nominal test intervals overlap")
        prior_test_end = nominal_test["end_exclusive"]
        for item in fold["horizon_boundaries"]:
            try:
                boundary = StructuralFoldBoundary(**item)
            except (TypeError, StockControlError) as exc:
                raise StockFoldManifestError(
                    "horizon boundary is not structurally authentic"
                ) from exc
            if boundary.fold_id != (
                f"{fold['fold_id']}-h{boundary.horizon_sessions}"
            ):
                raise StockFoldManifestError("horizon boundary identity changed")


def _fingerprint_value(value: object) -> object:
    if isinstance(value, Mapping):
        return tuple(
            (key, _fingerprint_value(item))
            for key, item in sorted(value.items())
        )
    if isinstance(value, tuple):
        return tuple(_fingerprint_value(item) for item in value)
    return value


@dataclasses.dataclass(frozen=True, init=False)
class StockFoldManifest:
    """Immutable reviewed-candidate folds with literal zero action authority."""

    manifest_id: str
    manifest_hash: str
    strategy_pdf_sha256: str
    parent_plan_id: str
    parent_plan_hash: str
    parent_plan_artifact_sha256: str
    parent_stock_spec_id: str
    parent_stock_spec_hash: str
    parent_stock_spec_artifact_sha256: str
    parent_history_section_sha256: str
    evaluation_id: str
    calendar_contract: Mapping[str, Any]
    walk_forward_contract: Mapping[str, Any]
    cross_boundary_common_event_contract: Mapping[str, Any]
    section_hashes: Mapping[str, str]
    external_bindings: Mapping[str, Any]
    capabilities: Mapping[str, bool]
    _authority: object = dataclasses.field(repr=False, compare=False)

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
    def result_disposition_available(self) -> bool:
        return False

    @property
    def deployment_available(self) -> bool:
        return False

    @property
    def orders_available(self) -> bool:
        return False


def _manifest_fingerprint(manifest: StockFoldManifest) -> tuple[object, ...]:
    return (
        manifest.manifest_id,
        manifest.manifest_hash,
        manifest.strategy_pdf_sha256,
        manifest.parent_plan_id,
        manifest.parent_plan_hash,
        manifest.parent_plan_artifact_sha256,
        manifest.parent_stock_spec_id,
        manifest.parent_stock_spec_hash,
        manifest.parent_stock_spec_artifact_sha256,
        manifest.parent_history_section_sha256,
        manifest.evaluation_id,
        _fingerprint_value(manifest.calendar_contract),
        _fingerprint_value(manifest.walk_forward_contract),
        _fingerprint_value(manifest.cross_boundary_common_event_contract),
        _fingerprint_value(manifest.section_hashes),
        _fingerprint_value(manifest.external_bindings),
        _fingerprint_value(manifest.capabilities),
    )


def _forget_loaded_manifest(
    identity: int,
    reference: weakref.ReferenceType[StockFoldManifest],
) -> None:
    with _FOLD_MANIFEST_AUTHORITIES_LOCK:
        current = _FOLD_MANIFEST_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _FOLD_MANIFEST_AUTHORITIES.pop(identity, None)


def _loaded_manifest(
    raw: Mapping[str, Any],
    *,
    source_path: Path,
    stock_evaluation_path: Path,
    qc_first_plan_path: Path,
    stock_evaluation_payload: bytes,
    qc_first_plan_payload: bytes,
) -> StockFoldManifest:
    value = object.__new__(StockFoldManifest)
    fields = {
        "manifest_id": raw["manifest_id"],
        "manifest_hash": raw["manifest_hash"],
        "strategy_pdf_sha256": raw["strategy_pdf_sha256"],
        "parent_plan_id": raw["parent_plan_id"],
        "parent_plan_hash": raw["parent_plan_hash"],
        "parent_plan_artifact_sha256": raw["parent_plan_artifact_sha256"],
        "parent_stock_spec_id": raw["parent_stock_spec_id"],
        "parent_stock_spec_hash": raw["parent_stock_spec_hash"],
        "parent_stock_spec_artifact_sha256": raw[
            "parent_stock_spec_artifact_sha256"
        ],
        "parent_history_section_sha256": raw["parent_history_section_sha256"],
        "evaluation_id": raw["evaluation_id"],
        "calendar_contract": _freeze(raw["calendar_contract"]),
        "walk_forward_contract": _freeze(raw["walk_forward_contract"]),
        "cross_boundary_common_event_contract": _freeze(
            raw["cross_boundary_common_event_contract"]
        ),
        "section_hashes": _freeze(raw["section_hashes"]),
        "external_bindings": _freeze(raw["external_bindings"]),
        "capabilities": _freeze(raw["capabilities"]),
        "_authority": _LOADED_FOLD_MANIFEST_AUTHORITY,
    }
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    fingerprint = _manifest_fingerprint(value)
    identity = id(value)
    reference = weakref.ref(
        value,
        lambda ref, key=identity: _forget_loaded_manifest(key, ref),
    )
    with _FOLD_MANIFEST_AUTHORITIES_LOCK:
        _FOLD_MANIFEST_AUTHORITIES[identity] = (
            reference,
            source_path,
            stock_evaluation_path,
            qc_first_plan_path,
            stock_evaluation_payload,
            qc_first_plan_payload,
            fingerprint,
        )
    return value


def require_loaded_stock_fold_manifest(
    manifest: StockFoldManifest,
) -> StockFoldManifest:
    """Reauthenticate loader identity, immutable fields, lineage, and bytes."""
    if (
        type(manifest) is not StockFoldManifest
        or getattr(manifest, "_authority", None)
        is not _LOADED_FOLD_MANIFEST_AUTHORITY
    ):
        raise StockFoldManifestError("fold manifest is not loader-authenticated")
    with _FOLD_MANIFEST_AUTHORITIES_LOCK:
        authority = _FOLD_MANIFEST_AUTHORITIES.get(id(manifest))
    if authority is None or authority[0]() is not manifest:
        raise StockFoldManifestError("fold manifest loader authority is absent")
    (
        _,
        source_path,
        stock_path,
        qc_plan_path,
        stock_payload,
        qc_plan_payload,
        fingerprint,
    ) = authority
    if _manifest_fingerprint(manifest) != fingerprint:
        raise StockFoldManifestError("fold manifest changed after authentication")
    _revalidate(qc_plan_path, qc_plan_payload, "QC-first parent")
    _revalidate(stock_path, stock_payload, "stock-evaluation parent")
    reloaded = load_stock_fold_manifest(
        source_path,
        stock_evaluation_path=stock_path,
        qc_first_plan_path=qc_plan_path,
    )
    if _manifest_fingerprint(reloaded) != fingerprint:
        raise StockFoldManifestError(
            "fold manifest source changed after authentication"
        )
    return manifest


def load_stock_fold_manifest(
    path: Path,
    *,
    stock_evaluation_path: Path,
    qc_first_plan_path: Path,
) -> StockFoldManifest:
    """Authenticate the exact outcome-free folds and both parent artifacts."""
    resolved, payload = _read_stable_regular(path, "stock fold manifest")
    if payload.startswith(
        (
            b"\xef\xbb\xbf",
            b"\xff\xfe",
            b"\xfe\xff",
            b"\xff\xfe\x00\x00",
            b"\x00\x00\xfe\xff",
        )
    ):
        raise StockFoldManifestError("stock fold manifest must not contain a BOM")
    try:
        text = payload.decode("utf-8", errors="strict")
        raw = json.loads(
            text,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_object,
        )
    except UnicodeDecodeError as exc:
        raise StockFoldManifestError(
            "stock fold manifest is not strict UTF-8"
        ) from exc
    except json.JSONDecodeError as exc:
        raise StockFoldManifestError("stock fold manifest is invalid JSON") from exc
    if type(raw) is not dict or set(raw) != _ROOT_KEYS:
        raise StockFoldManifestError("stock fold manifest root fields are not exact")
    try:
        canonical_file = (
            json.dumps(
                raw,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise StockFoldManifestError(
            "stock fold manifest contains a noncanonical JSON value"
        ) from exc
    if payload != canonical_file:
        raise StockFoldManifestError(
            "stock fold manifest bytes are not canonical UTF-8 JSON"
        )

    declared_hash = raw["manifest_hash"]
    if (
        type(declared_hash) is not str
        or len(declared_hash) != 64
        or any(character not in "0123456789abcdef" for character in declared_hash)
    ):
        raise StockFoldManifestError("manifest_hash must be a lowercase SHA-256")
    actual_hash = hashlib.sha256(_content_payload(raw)).hexdigest()
    if actual_hash != declared_hash:
        raise StockFoldManifestError("stock fold manifest content hash mismatch")
    if raw["manifest_id"] != f"arv2-stock-folds-{actual_hash[:16]}":
        raise StockFoldManifestError("manifest_id is not content-derived")

    _require_exact(raw, _EXPECTED_DOCUMENT, "manifest")
    for name in _SECTION_NAMES:
        actual_section_hash = hashlib.sha256(_canonical(raw[name])).hexdigest()
        if actual_section_hash != raw["section_hashes"][name]:
            raise StockFoldManifestError(f"{name} section hash mismatch")
    _validate_fold_structure(raw)

    resolved_stock, stock_payload = _read_stable_regular(
        stock_evaluation_path,
        "stock-evaluation parent",
    )
    resolved_plan, plan_payload = _read_stable_regular(
        qc_first_plan_path,
        "QC-first parent",
    )
    if hashlib.sha256(plan_payload).hexdigest() != PARENT_PLAN_ARTIFACT_SHA256:
        raise StockFoldManifestError("QC-first parent artifact bytes changed")
    if (
        hashlib.sha256(stock_payload).hexdigest()
        != PARENT_STOCK_SPEC_ARTIFACT_SHA256
    ):
        raise StockFoldManifestError(
            "stock-evaluation parent artifact bytes changed"
        )
    try:
        plan: QcFirstStudyPlan = load_qc_first_study_plan(resolved_plan)
    except QcFirstPlanError as exc:
        raise StockFoldManifestError(
            "QC-first parent authentication failed"
        ) from exc
    if plan.plan_id != PARENT_PLAN_ID or plan.plan_hash != PARENT_PLAN_HASH:
        raise StockFoldManifestError("QC-first parent identity changed")
    try:
        stock: StockEvaluationContract = load_stock_evaluation_contract(
            resolved_stock,
            qc_first_plan_path=resolved_plan,
        )
    except (QcFirstPlanError, StockEvaluationContractError) as exc:
        raise StockFoldManifestError(
            "stock-evaluation parent authentication failed"
        ) from exc
    if (
        stock.spec_id != PARENT_STOCK_SPEC_ID
        or stock.spec_hash != PARENT_STOCK_SPEC_HASH
        or stock.parent_plan_id != PARENT_PLAN_ID
        or stock.parent_plan_hash != PARENT_PLAN_HASH
        or stock.section_hashes["history_definition"]
        != PARENT_HISTORY_SECTION_SHA256
        or stock.sections["history_definition"]["walk_forward"][
            "fold_manifest_sha256"
        ]
        is not None
    ):
        raise StockFoldManifestError("stock-evaluation parent lineage changed")

    _revalidate(resolved_plan, plan_payload, "QC-first parent")
    _revalidate(resolved_stock, stock_payload, "stock-evaluation parent")
    _revalidate(resolved, payload, "stock fold manifest")
    return _loaded_manifest(
        raw,
        source_path=resolved,
        stock_evaluation_path=resolved_stock,
        qc_first_plan_path=resolved_plan,
        stock_evaluation_payload=stock_payload,
        qc_first_plan_payload=plan_payload,
    )


def _render_expected_document() -> str:
    """Render review bytes; intentionally grants no persistence authority."""
    return json.dumps(
        _thaw(_EXPECTED_DOCUMENT),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


if __name__ == "__main__":  # pragma: no cover - review-artifact renderer
    print(_render_expected_document(), end="")
