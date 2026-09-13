"""Pure, fail-closed composition boundary for the first formal ARV2 run.

This module is intentionally split at two trust boundaries.  Caller-supplied
terminal bytes can be parsed and content-addressed here, but they cannot claim
to be complete production truth.  Likewise, builder-authenticated production
scores can be projected into a runtime plan, but that fact alone does not
authenticate the complete eligible-security/control census from which they
were derived.  The public pre-run composer therefore also requires the opaque,
builder-authenticated ``ProductionTruthArtifact`` minted by the reviewed
physical acquisition/assembly boundary.  No public content-only mint exists
here.

There is no filesystem, environment, credential, provider, QuantConnect,
Object Store, result, order, deployment, or trading call in this module.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import threading
import weakref
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from collections.abc import Mapping, Sequence

from research.analyst_revisions_v2.preopen_control_acquisition import (
    PreopenControlAcquisitionError,
    acquisition_receipt_artifact_binding_record,
    require_reviewed_preopen_control_acquisition_receipt,
)
from research.analyst_revisions_v2.production_scoring import (
    BINARY_COLUMNS,
    CONTINUOUS_COLUMNS,
    HALF_LIFE_SESSIONS,
    SCORING_CONTRACT_ID,
    SCORING_CONTRACT_SHA256,
    ProductionScoringResult,
)
from research.analyst_revisions_v2.production_truth_gate import (
    ProductionTruthArtifact,
    ProductionTruthError,
    TruthSourceKind,
    require_production_truth_artifact,
)

from .event_study import _reviewed_session_axis
from .formal_input_bundle import (
    FormalInputBundleError,
    FormalPowerCalibrationBinding,
    FormalProductionScoringCensus,
    ProductionScoredDecisionLineage,
    ProductionScoringCensusRefusal,
    build_formal_production_scoring_census,
    require_formal_power_calibration_binding,
    require_formal_production_scoring_census,
)
from .formal_run_protocol import (
    EVALUATION_ID,
    FORMAL_PRIMARY_FOLD_IDS,
    DESCRIPTIVE_SENSITIVITY_FOLD_IDS,
    HORIZONS,
    SOURCE_VIEW_IDS,
    TERMINAL_POLICY_ID,
    AcceptedRiskPairBinding,
    ArtifactBinding,
    FormalRunCandidate,
    FormalRunProtocolError,
    PowerFloorBinding,
    TerminalCensusBinding,
    build_formal_run_candidate,
    require_accepted_risk_pair_binding,
    require_artifact_binding,
    require_power_floor_binding,
    require_terminal_census_binding,
)
from .formal_runtime_projection import (
    ABSOLUTE_MAX_SUMMARY_CHUNKS,
    ABSOLUTE_MAX_SUMMARY_PAYLOAD_BYTES,
    CONTRIBUTION_SEED_SCHEMA,
    DAILY_REQUIREMENT_SCHEMA,
    DECISION_JOIN_SCHEMA,
    ECONOMIC_JOIN_SCHEMA,
    FORMAL_CONTRACT_SCHEMA,
    FORMAL_INPUT_PREFIX,
    INPUT_MANIFEST_SCHEMA,
    MINUTE_REQUIREMENT_SCHEMA,
    SHARD_ROLE_ORDER,
    TERMINAL_OBJECT_SCHEMA,
    FormalQcCompressedShard,
    QcObjectPayloadBinding,
    FormalQcRuntimeCapacityBinding,
    FormalQcRuntimeProjection,
    FormalQcRuntimeResourceCensus,
    build_daily_market_requirement_id,
    build_formal_qc_compressed_shard,
    build_formal_qc_input_manifest_bytes,
    build_formal_qc_runtime_projection,
    build_minute_market_requirement_id,
    build_qc_object_payload_binding,
    canonical_json_bytes,
    derive_formal_qc_runtime_resource_census,
    formal_cloud_evaluator_binding,
    formal_code_projection_binding,
    require_formal_qc_compressed_shard,
    render_formal_qc_capacity_review_candidate,
    require_formal_qc_runtime_capacity_binding,
    require_formal_qc_runtime_projection,
)
from .formal_submission_adapter import (
    FormalQcSubmissionError,
    FormalQcUploadBundle,
    build_formal_qc_upload_bundle,
    require_formal_qc_upload_bundle,
)


class FormalInputComposerError(ValueError):
    """Formal inputs cannot be composed without exact authenticated parents."""


# This is the exact object consumed by the projected runtime; the local
# loader adds authentication state around these unchanged wire bytes.
TERMINAL_PACKAGE_SCHEMA = "arv2-formal-qc-terminal-dispositions-v2"
STATUS = "offline_compact_candidate_capacity_review_required"
AUTHORITY = (
    "pure_content_composition_only_no_provider_qc_result_order_deployment_or_"
    "trading_authority"
)

_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,511}\Z")
_DECIMAL_TEXT = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
_TERMINAL_DISPOSITIONS = (
    "terminal_payoff",
    "benchmark_splice_continuation",
    "named_terminal_refusal",
)
_TERMINAL_KEY_CENSUS_DOMAIN = "arv2-formal-terminal-key-census-v2"
STREAM_LAYOUT_ID = "arv2-formal-qc-fold-session-stream-layout-v1"
STREAM_ROLE_SORT_KEYS = {
    "formal_contract": ("singleton",),
    "contribution_seeds": (
        "first_active_session_position", "source_view_id", "fold_id",
        "security_id", "seed_id",
    ),
    "decision_joins": (
        "fold_id", "session_position", "source_view_id", "security_id",
    ),
    "economic_joins": (
        "fold_id", "session_position", "source_view_id",
    ),
    "daily_requirements": ("session", "security_id", "requirement_id"),
    "minute_requirements": (
        "first_active_session_position", "publication_at_utc", "security_id",
        "requirement_id",
    ),
    "terminal_dispositions": ("slot_kind", "slot_id", "horizon"),
}
_CAPABILITIES = (
    "filesystem_read",
    "environment_read",
    "credential_access",
    "provider_access",
    "production_input_read",
    "real_outcome_access",
    "qc_account_access",
    "qc_object_store_read",
    "qc_object_store_write",
    "qc_project_create",
    "qc_upload",
    "qc_compile",
    "qc_launch",
    "result_access",
    "result_disposition",
    "deployment",
    "orders",
    "trading",
)


def _canonical_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise FormalInputComposerError("value is not canonical JSON") from exc


def _reject_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise FormalInputComposerError("JSON object contains a duplicate key")
        result[key] = value
    return result


def _reject_number(_value: str) -> object:
    raise FormalInputComposerError("JSON floats and non-finite values are forbidden")


def _canonical_object(payload: bytes, name: str) -> dict[str, object]:
    if type(payload) is not bytes or not payload:
        raise FormalInputComposerError(f"{name} must be nonempty exact bytes")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_pairs,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        if isinstance(exc, FormalInputComposerError):
            raise
        raise FormalInputComposerError(f"{name} is not strict UTF-8 JSON") from exc
    if type(value) is not dict or _canonical_bytes(value) != payload:
        raise FormalInputComposerError(f"{name} is not one canonical JSON object")
    return value


def _exact_object(
    value: object, fields: tuple[str, ...], name: str
) -> dict[str, object]:
    if type(value) is not dict or set(value) != set(fields):
        raise FormalInputComposerError(f"{name} fields changed")
    return value


def _safe_id(value: object, name: str) -> str:
    if type(value) is not str or _SAFE_ID.fullmatch(value) is None:
        raise FormalInputComposerError(f"{name} is not a safe identifier")
    return value


def _sha(value: object, name: str) -> str:
    if type(value) is not str or _HEX_64.fullmatch(value) is None:
        raise FormalInputComposerError(f"{name} is not a lowercase SHA-256")
    return value


def _count(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise FormalInputComposerError(f"{name} is not an exact nonnegative count")
    return value


def _utc(value: object, name: str) -> str:
    if type(value) is not str or not value.endswith("Z"):
        raise FormalInputComposerError(f"{name} is not a UTC instant")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise FormalInputComposerError(f"{name} is not a UTC instant") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise FormalInputComposerError(f"{name} is not a UTC instant")
    return value


def _decimal(value: object, name: str) -> Decimal:
    if (
        type(value) is not str
        or len(value) > 1024
        or _DECIMAL_TEXT.fullmatch(value) is None
    ):
        raise FormalInputComposerError(f"{name} is not canonical Decimal text")
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise FormalInputComposerError(f"{name} is not canonical Decimal text") from exc
    if not result.is_finite() or format(result, "f") != value:
        raise FormalInputComposerError(f"{name} is not canonical Decimal text")
    return result


@dataclasses.dataclass(frozen=True, slots=True)
class FormalTerminalDispositionRow:
    slot_kind: str
    slot_id: str
    horizon_sessions: int | None
    disposition: str
    stock_return: Decimal | None
    reason: str | None
    terminal_lineage_sha256: str
    available_at_utc: str

    def to_record(self) -> dict[str, object]:
        return {
            "schema": TERMINAL_OBJECT_SCHEMA,
            "slot_kind": self.slot_kind,
            "slot_id": self.slot_id,
            "horizon": self.horizon_sessions,
            "disposition": self.disposition,
            "stock_return": (
                None if self.stock_return is None else format(self.stock_return, "f")
            ),
            "reason": self.reason,
            "terminal_lineage_sha256": self.terminal_lineage_sha256,
            "available_at_utc": self.available_at_utc,
        }


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class FormalTerminalDispositionPackage:
    package_id: str
    package_sha256: str
    schema: str
    status: str
    authority: str
    terminal_census: TerminalCensusBinding
    rows: tuple[FormalTerminalDispositionRow, ...]
    terminal_payoff_count: int
    benchmark_splice_continuation_count: int
    named_terminal_refusal_count: int
    silently_omitted_count: int
    production_truth_authenticated: bool
    capabilities: tuple[tuple[str, bool], ...]
    _canonical_document: bytes = dataclasses.field(repr=False)


_TERMINAL_PACKAGES: dict[
    int,
    tuple[
        weakref.ReferenceType[FormalTerminalDispositionPackage],
        TerminalCensusBinding,
        bytes,
        tuple[object, ...],
    ],
] = {}
_TERMINAL_PACKAGES_LOCK = threading.RLock()


def _terminal_topology(
    value: FormalTerminalDispositionPackage,
) -> tuple[object, ...]:
    return (
        id(value.terminal_census),
        id(value.terminal_census.census),
        id(value.rows),
        tuple(id(item) for item in value.rows),
        id(value.capabilities),
        id(value._canonical_document),
    )


def _forget_terminal_package(
    identity: int,
    reference: weakref.ReferenceType[FormalTerminalDispositionPackage],
) -> None:
    with _TERMINAL_PACKAGES_LOCK:
        current = _TERMINAL_PACKAGES.get(identity)
        if current is not None and current[0] is reference:
            _TERMINAL_PACKAGES.pop(identity, None)


def _terminal_row(value: object) -> FormalTerminalDispositionRow:
    row = _exact_object(
        value,
        (
            "schema",
            "slot_kind",
            "slot_id",
            "horizon",
            "disposition",
            "stock_return",
            "reason",
            "terminal_lineage_sha256",
            "available_at_utc",
        ),
        "terminal disposition row",
    )
    if row["schema"] != TERMINAL_OBJECT_SCHEMA:
        raise FormalInputComposerError("terminal disposition row schema changed")
    slot_kind = _safe_id(row["slot_kind"], "terminal slot kind")
    if slot_kind not in {"decision_horizon", "economic_daily"}:
        raise FormalInputComposerError("terminal slot kind changed")
    horizon = row["horizon"]
    if slot_kind == "decision_horizon":
        if type(horizon) is not int or horizon not in HORIZONS:
            raise FormalInputComposerError("decision terminal horizon changed")
    elif horizon is not None:
        raise FormalInputComposerError("economic terminal gained a horizon")
    disposition = _safe_id(row["disposition"], "terminal disposition")
    if disposition not in _TERMINAL_DISPOSITIONS:
        raise FormalInputComposerError("terminal disposition changed")
    stock_return = (
        None
        if row["stock_return"] is None
        else _decimal(row["stock_return"], "terminal stock return")
    )
    reason = row["reason"]
    if reason is not None:
        reason = _safe_id(reason, "terminal refusal reason")
    if disposition == "terminal_payoff":
        if stock_return is None or stock_return < Decimal("-1") or reason is not None:
            raise FormalInputComposerError("terminal payoff is not an exact value XOR")
    elif disposition == "benchmark_splice_continuation":
        if slot_kind != "economic_daily" or stock_return is not None or reason is not None:
            raise FormalInputComposerError("benchmark-splice continuation changed")
    elif stock_return is not None or reason is None:
        raise FormalInputComposerError("named terminal refusal is not an exact XOR")
    return FormalTerminalDispositionRow(
        slot_kind=slot_kind,
        slot_id=_safe_id(row["slot_id"], "terminal slot id"),
        horizon_sessions=horizon,
        disposition=disposition,
        stock_return=stock_return,
        reason=reason,
        terminal_lineage_sha256=_sha(
            row["terminal_lineage_sha256"], "terminal lineage"
        ),
        available_at_utc=_utc(row["available_at_utc"], "terminal availability"),
    )


def _parse_terminal_package(
    payload: bytes, terminal_census: TerminalCensusBinding
) -> tuple[tuple[FormalTerminalDispositionRow, ...], Counter[str]]:
    try:
        require_terminal_census_binding(terminal_census)
        require_artifact_binding(terminal_census.census)
    except (FormalRunProtocolError, AttributeError, TypeError, ValueError) as exc:
        raise FormalInputComposerError("terminal census binding changed") from exc
    document = _exact_object(
        _canonical_object(payload, "terminal disposition package"),
        ("schema", "terminal_policy_id", "row_count", "rows"),
        "terminal disposition package",
    )
    if (
        document["schema"] != TERMINAL_PACKAGE_SCHEMA
        or document["terminal_policy_id"] != TERMINAL_POLICY_ID
        or type(document["rows"]) is not list
        or _count(document["row_count"], "terminal row count")
        != len(document["rows"])
    ):
        raise FormalInputComposerError("terminal package schema or census changed")
    rows = tuple(_terminal_row(item) for item in document["rows"])
    keys = tuple(
        (item.slot_kind, item.slot_id, item.horizon_sessions) for item in rows
    )
    if len(keys) != len(set(keys)) or keys != tuple(sorted(keys)):
        raise FormalInputComposerError("terminal rows are duplicated or reordered")
    counts = Counter(item.disposition for item in rows)
    if (
        len(rows) != terminal_census.terminal_requirement_count
        or counts["terminal_payoff"] != terminal_census.terminal_payoff_count
        or counts["benchmark_splice_continuation"]
        != terminal_census.benchmark_splice_continuation_count
        or counts["named_terminal_refusal"]
        != terminal_census.named_terminal_refusal_count
        or terminal_census.silently_omitted_count != 0
        or terminal_census.census.content_sha256
        != hashlib.sha256(payload).hexdigest()
        or terminal_census.census.byte_count != len(payload)
    ):
        raise FormalInputComposerError(
            "terminal package disagrees with its exhaustive census binding"
        )
    return rows, counts


def load_formal_terminal_disposition_package(
    *, payload: bytes, terminal_census: TerminalCensusBinding
) -> FormalTerminalDispositionPackage:
    """Authenticate exact terminal bytes without claiming production truth."""

    rows, counts = _parse_terminal_package(payload, terminal_census)
    digest = hashlib.sha256(payload).hexdigest()
    value = object.__new__(FormalTerminalDispositionPackage)
    fields: dict[str, object] = {
        "package_id": f"arv2-formal-terminal-package-{digest[:24]}",
        "package_sha256": digest,
        "schema": TERMINAL_PACKAGE_SCHEMA,
        "status": STATUS,
        "authority": AUTHORITY,
        "terminal_census": terminal_census,
        "rows": rows,
        "terminal_payoff_count": counts["terminal_payoff"],
        "benchmark_splice_continuation_count": counts[
            "benchmark_splice_continuation"
        ],
        "named_terminal_refusal_count": counts["named_terminal_refusal"],
        "silently_omitted_count": 0,
        "production_truth_authenticated": False,
        "capabilities": tuple((name, False) for name in _CAPABILITIES),
        "_canonical_document": bytes(payload),
    }
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_terminal_package(key, ref)
    )
    with _TERMINAL_PACKAGES_LOCK:
        _TERMINAL_PACKAGES[identity] = (
            reference,
            terminal_census,
            bytes(payload),
            _terminal_topology(value),
        )
    return require_formal_terminal_disposition_package(value)


def require_formal_terminal_disposition_package(
    value: FormalTerminalDispositionPackage,
) -> FormalTerminalDispositionPackage:
    if type(value) is not FormalTerminalDispositionPackage:
        raise FormalInputComposerError("terminal package changed type")
    with _TERMINAL_PACKAGES_LOCK:
        registered = _TERMINAL_PACKAGES.get(id(value))
    if registered is None or registered[0]() is not value:
        raise FormalInputComposerError("terminal package is not loader-authenticated")
    if (
        registered[1] is not value.terminal_census
        or registered[2] != value._canonical_document
        or registered[3] != _terminal_topology(value)
    ):
        raise FormalInputComposerError("terminal package topology changed")
    rows, counts = _parse_terminal_package(
        value._canonical_document, value.terminal_census
    )
    expected = {
        "package_id": (
            "arv2-formal-terminal-package-"
            + hashlib.sha256(value._canonical_document).hexdigest()[:24]
        ),
        "package_sha256": hashlib.sha256(value._canonical_document).hexdigest(),
        "schema": TERMINAL_PACKAGE_SCHEMA,
        "status": STATUS,
        "authority": AUTHORITY,
        "rows": rows,
        "terminal_payoff_count": counts["terminal_payoff"],
        "benchmark_splice_continuation_count": counts[
            "benchmark_splice_continuation"
        ],
        "named_terminal_refusal_count": counts["named_terminal_refusal"],
        "silently_omitted_count": 0,
        "production_truth_authenticated": False,
        "capabilities": tuple((name, False) for name in _CAPABILITIES),
    }
    if any(getattr(value, name) != item for name, item in expected.items()):
        raise FormalInputComposerError("terminal package content changed")
    return value


def render_formal_terminal_disposition_package_bytes(
    value: FormalTerminalDispositionPackage,
) -> bytes:
    require_formal_terminal_disposition_package(value)
    return bytes(value._canonical_document)



_COMPACT_CANDIDATE_SCHEMA = "arv2-formal-compact-composition-candidate-v1"
_COMPACT_PLAN_SCHEMA = "arv2-formal-compact-run-plan-v1"
_PRODUCTION_INPUT_SCHEMA = "arv2-formal-production-input-package-v1"
_PARTITION_SCHEMA = "arv2-formal-source-view-partition-set-v1"
_CONTRIBUTION_STATE_DOMAIN = "arv2-formal-qc-contribution-state-v1"
# Inclusive logical observation interval.  It starts with the earliest H1
# formal decision and extends through the exact H60 exit of the final eligible
# 2025 decision (2025-12-31), while the QC engine itself runs later at the
# separately authenticated calculation-as-of date.
_RUNTIME_START = date(2020, 1, 3)
_RUNTIME_END = date(2026, 3, 30)
_MAX_ROWS_PER_SHARD = 250_000
_MAX_RAW_BYTES_PER_SHARD = 64 * 1024 * 1024
_FOLD_TEST_INTERVALS = {
    "arv2-wf-test-2020": (date(2020, 3, 30), date(2021, 1, 4)),
    "arv2-wf-test-2021": (date(2021, 3, 31), date(2022, 1, 3)),
    "arv2-wf-test-2022": (date(2022, 3, 30), date(2023, 1, 3)),
    "arv2-wf-test-2023": (date(2023, 3, 30), date(2024, 1, 2)),
    "arv2-wf-test-2024": (date(2024, 3, 28), date(2025, 1, 2)),
    "arv2-wf-test-2025": (date(2025, 4, 1), date(2026, 1, 2)),
}


def _identified(prefix: str, schema: str, record: Mapping[str, object]) -> tuple[str, str]:
    digest = hashlib.sha256(
        canonical_json_bytes({"schema": schema, **record})
    ).hexdigest()
    return prefix + digest[:24], digest


def _artifact(
    *, prefix: str, schema: str, record: Mapping[str, object]
) -> tuple[ArtifactBinding, bytes]:
    payload = canonical_json_bytes({"schema": schema, **record})
    digest = hashlib.sha256(payload).hexdigest()
    return (
        ArtifactBinding(
            artifact_id=prefix + digest[:24],
            content_sha256=digest,
            artifact_sha256=hashlib.sha256(
                (schema + "\n").encode("ascii") + payload
            ).hexdigest(),
            byte_count=len(payload),
        ),
        payload,
    )


def _decimal_text(value: Decimal) -> str:
    return "0" if value == 0 else format(value, "f")


def _context() -> Context:
    return Context(prec=50, rounding=ROUND_HALF_EVEN)


def _decay(age: int) -> Decimal:
    if type(age) is not int or age < 0:
        raise FormalInputComposerError("contribution age changed")
    with localcontext(_context()):
        whole, remainder = divmod(age, HALF_LIFE_SESSIONS)
        value = Decimal("0.5") ** whole
        if remainder:
            exponent = -Decimal(remainder) / Decimal(HALF_LIFE_SESSIONS)
            value *= (exponent * Decimal(2).ln()).exp()
        return +value


def _axis() -> tuple[tuple[date, ...], dict[date, int]]:
    try:
        values = _reviewed_session_axis()
    except (AttributeError, TypeError, ValueError) as exc:
        raise FormalInputComposerError("reviewed exchange session axis changed") from exc
    if type(values) is not tuple or not values:
        raise FormalInputComposerError("reviewed exchange session axis changed")
    return values, {value: index for index, value in enumerate(values)}


def _decision_terminal_slot_id(*, decision_id: str, horizon: int) -> str:
    digest = hashlib.sha256(
        canonical_json_bytes(
            {
                "domain": "arv2-decision-terminal-slot-v1",
                "decision_id": decision_id,
                "horizon": horizon,
            }
        )
    ).hexdigest()
    return "arv2-decision-terminal-slot-" + digest


def _economic_terminal_slot_id(
    *, view_id: str, fold_id: str, session_position: int, security_id: str
) -> str:
    digest = hashlib.sha256(
        canonical_json_bytes(
            {
                "domain": "arv2-economic-terminal-slot-v1",
                "fold_id": fold_id,
                "security_id": security_id,
                "session_position": session_position,
                "view_id": view_id,
            }
        )
    ).hexdigest()
    return "arv2-economic-terminal-slot-" + digest


def _source_views(
    census: FormalProductionScoringCensus,
) -> tuple[tuple[str, tuple[object, ...], tuple[object, ...]], ...]:
    return (
        (
            SOURCE_VIEW_IDS[0],
            census.current_view.accepted,
            census.current_view.refused,
        ),
        (
            SOURCE_VIEW_IDS[1],
            census.censored_view.accepted,
            census.censored_view.refused,
        ),
    )


def _truth_and_parent_bindings(
    *,
    census: FormalProductionScoringCensus,
    truth: ProductionTruthArtifact,
    accepted_risk: AcceptedRiskPairBinding,
    formal_power: FormalPowerCalibrationBinding,
    power_floor: PowerFloorBinding,
) -> ArtifactBinding:
    try:
        require_formal_production_scoring_census(census)
        require_production_truth_artifact(truth)
        require_accepted_risk_pair_binding(accepted_risk)
        require_formal_power_calibration_binding(formal_power)
        require_power_floor_binding(power_floor)
        acquisition = require_reviewed_preopen_control_acquisition_receipt(
            truth.preopen_acquisition_receipt
        )
    except (
        FormalInputBundleError,
        ProductionTruthError,
        PreopenControlAcquisitionError,
        FormalRunProtocolError,
        AttributeError,
        TypeError,
        ValueError,
    ) as exc:
        raise FormalInputComposerError(
            "formal compact composition lacks an authenticated parent"
        ) from exc
    results = census._results
    if any(
        result.precontrol_batch.authority.truth_artifact is not truth
        for result in results
    ):
        raise FormalInputComposerError(
            "production scores do not share the supplied production truth artifact"
        )
    authority = results[0].precontrol_batch.authority
    current = authority.current_batch
    censored = authority.censored_batch
    if (
        current.pair_id != censored.pair_id
        or current.pair_sha256 != censored.pair_sha256
        or accepted_risk.pair.artifact_id != current.pair_id
        or accepted_risk.pair.content_sha256 != current.pair_sha256
        or accepted_risk.pristine_point_in_time is not False
        or accepted_risk.views_share_one_capture is not True
    ):
        raise FormalInputComposerError("accepted-risk pair is not the scorer parent")
    capture = tuple(
        item for item in truth.source_bindings
        if item.kind is TruthSourceKind.ACCEPTED_RISK_CAPTURE
    )
    if (
        len(capture) != 1
        or accepted_risk.capture_id != capture[0].artifact_id
        or accepted_risk.capture_sha256 != capture[0].artifact_sha256
    ):
        raise FormalInputComposerError("accepted-risk capture is not the truth parent")
    if (
        formal_power.receipt_id != power_floor.numeric_receipt.artifact_id
        or formal_power.receipt_sha256
        != power_floor.numeric_receipt.content_sha256
        or formal_power.disposition != power_floor.disposition
        or formal_power.required_valid_dates != power_floor.required_valid_dates
        or formal_power.required_connected_components
        != power_floor.required_connected_components
    ):
        raise FormalInputComposerError("formal numeric power bindings diverged")
    record = acquisition_receipt_artifact_binding_record(acquisition)
    binding = ArtifactBinding(**record)
    require_artifact_binding(binding)
    return binding


def _partition_binding(
    source_view_id: str,
    accepted: Sequence[ProductionScoredDecisionLineage],
    refused: Sequence[ProductionScoringCensusRefusal],
) -> ArtifactBinding:
    binding, _ = _artifact(
        prefix="arv2-formal-partition-",
        schema=_PARTITION_SCHEMA,
        record={
            "source_view_id": source_view_id,
            "accepted": [item.to_binding_record() for item in accepted],
            "refused": [item.to_record() for item in refused],
            "accepted_count": len(accepted),
            "named_preoutcome_refusal_count": len(refused),
            "terminal_count": len(accepted) + len(refused),
        },
    )
    return binding


def _compress_positions(values: Sequence[int]) -> list[list[int]]:
    positions = tuple(sorted(set(values)))
    if not positions:
        raise FormalInputComposerError("contribution seed has no active position")
    output: list[list[int]] = []
    start = positions[0]
    prior = start
    for position in positions[1:]:
        if position != prior + 1:
            output.append([start, prior + 1])
            start = position
        prior = position
    output.append([start, prior + 1])
    return output


def _build_contribution_rows(
    census: FormalProductionScoringCensus,
    positions: Mapping[date, int],
) -> tuple[
    list[dict[str, object]],
    dict[tuple[str, str], tuple[str, str | None]],
    dict[tuple[str, str], dict[str, object]],
]:
    groups: dict[tuple[object, ...], list[tuple[ProductionScoredDecisionLineage, object]]] = {}
    for view, accepted, _ in _source_views(census):
        for decision in accepted:
            for item in decision.contributions:
                key = (
                    view,
                    decision.fold_id,
                    decision.security_id,
                    item.representative_c2_row_sha256,
                    item.linked_c2_row_sha256s,
                    item.representative_provider_event_id,
                    item.institution_id,
                    item.common_event_id,
                    item.publication_at_utc,
                    item.eligible_session,
                )
                groups.setdefault(key, []).append((decision, item))
    seed_rows: list[dict[str, object]] = []
    decision_seed: dict[tuple[str, str], tuple[str, str | None]] = {}
    minute_rows: dict[tuple[str, str], dict[str, object]] = {}
    for key, appearances in groups.items():
        (
            view, fold, security, representative, linked, provider_event,
            institution, common_event, publication, eligible_text,
        ) = key
        eligible = date.fromisoformat(str(eligible_text))
        if eligible not in positions:
            raise FormalInputComposerError(
                "contribution eligible session is outside the reviewed axis"
            )
        eligible_position = positions[eligible]
        bases: set[Decimal] = set()
        active_positions: list[int] = []
        for decision, item in appearances:
            position = positions.get(decision.decision_session)
            if position is None or item.age_sessions != position - eligible_position:
                raise FormalInputComposerError(
                    "contribution age does not match the reviewed session axis"
                )
            decay = _decay(item.age_sessions)
            if item.decay_weight != decay:
                raise FormalInputComposerError(
                    "contribution decay differs from the cloud evaluator"
                )
            with localcontext(_context()):
                bases.add(+(item.firm_absolute_decayed_weight / decay))
            active_positions.append(position)
        if len(bases) != 1:
            raise FormalInputComposerError(
                "one sparse contribution seed has inconsistent base weight"
            )
        minute_id: str | None = None
        if publication is not None:
            minute_id = build_minute_market_requirement_id(
                security_id=str(security), publication_at_utc=str(publication)
            )
            minute_key = (str(security), str(publication))
            prior_minute = minute_rows.get(minute_key)
            first_active = min(active_positions)
            last_active = max(active_positions)
            if prior_minute is not None:
                first_active = min(
                    first_active,
                    int(prior_minute["first_active_session_position"]),
                )
                last_active = max(
                    last_active,
                    int(prior_minute["last_active_session_position"]),
                )
            minute_rows[minute_key] = {
                "schema": MINUTE_REQUIREMENT_SCHEMA,
                "requirement_id": minute_id,
                "security_id": security,
                "publication_at_utc": publication,
                "first_active_session_position": first_active,
                "last_active_session_position": last_active,
            }
        record: dict[str, object] = {
            "source_view_id": view,
            "fold_id": fold,
            "security_id": security,
            "representative_c2_row_sha256": representative,
            "linked_c2_row_sha256s": list(linked),
            "representative_provider_event_id": provider_event,
            "institution_id": institution,
            "common_event_id": common_event,
            "publication_at_utc": publication,
            "minute_requirement_id": minute_id,
            "eligible_session": eligible_text,
            "eligible_session_position": eligible_position,
            "base_absolute_firm_weight": _decimal_text(next(iter(bases))),
            "active_intervals": _compress_positions(active_positions),
        }
        seed_id, seed_hash = _identified(
            "arv2-formal-contribution-seed-",
            CONTRIBUTION_SEED_SCHEMA,
            record,
        )
        row = {
            "schema": CONTRIBUTION_SEED_SCHEMA,
            "seed_id": seed_id,
            "seed_sha256": seed_hash,
            **record,
        }
        seed_rows.append(row)
        for decision, item in appearances:
            map_key = (decision.decision_id, item.lineage_sha256)
            if map_key in decision_seed:
                raise FormalInputComposerError(
                    "one contribution lineage maps to multiple sparse seeds"
                )
            decision_seed[map_key] = (seed_id, minute_id)
    return seed_rows, decision_seed, minute_rows


def _daily_requirement(
    rows: dict[tuple[str, str], dict[str, object]],
    security_id: str,
    session: date,
) -> str:
    text = session.isoformat()
    requirement_id = build_daily_market_requirement_id(
        security_id=security_id, session=text
    )
    rows[(security_id, text)] = {
        "schema": DAILY_REQUIREMENT_SCHEMA,
        "requirement_id": requirement_id,
        "security_id": security_id,
        "session": text,
    }
    return requirement_id


def _contribution_state(
    decision: ProductionScoredDecisionLineage,
    decision_seed: Mapping[tuple[str, str], tuple[str, str | None]],
) -> str:
    values: list[dict[str, object]] = []
    for item in decision.contributions:
        try:
            seed_id, minute_id = decision_seed[
                (decision.decision_id, item.lineage_sha256)
            ]
        except KeyError as exc:
            raise FormalInputComposerError(
                "scored contribution is absent from the sparse seed census"
            ) from exc
        values.append(
            {
                "contribution_seed_id": seed_id,
                "contribution_lineage_sha256": item.lineage_sha256,
                "publication_at_utc": item.publication_at_utc,
                "minute_requirement_id": minute_id,
                "firm_absolute_decayed_weight": _decimal_text(
                    item.firm_absolute_decayed_weight
                ),
            }
        )
    values.sort(key=lambda item: item["contribution_lineage_sha256"])
    return hashlib.sha256(
        canonical_json_bytes(
            {"domain": _CONTRIBUTION_STATE_DOMAIN, "contributions": values}
        )
    ).hexdigest()


def _scored_decision_row(
    *,
    decision: ProductionScoredDecisionLineage,
    position: int,
    axis: Sequence[date],
    benchmark_security_id: str,
    daily_rows: dict[tuple[str, str], dict[str, object]],
    decision_seed: Mapping[tuple[str, str], tuple[str, str | None]],
) -> dict[str, object]:
    entry = _daily_requirement(
        daily_rows, decision.security_id, decision.decision_session
    )
    benchmark_entry = _daily_requirement(
        daily_rows, benchmark_security_id, decision.decision_session
    )
    exits = []
    for horizon in HORIZONS:
        exit_position = position + horizon
        if exit_position >= len(axis):
            raise FormalInputComposerError("formal decision lacks its horizon exit")
        exit_session = axis[exit_position]
        exits.append(
            {
                "horizon": horizon,
                "exit_session": exit_session.isoformat(),
                "exit_session_position": exit_position,
                "stock_daily_requirement_id": _daily_requirement(
                    daily_rows, decision.security_id, exit_session
                ),
                "benchmark_daily_requirement_id": _daily_requirement(
                    daily_rows, benchmark_security_id, exit_session
                ),
            }
        )
    continuous = decision.transformed_controls[: len(CONTINUOUS_COLUMNS)]
    binary = decision.transformed_controls[len(CONTINUOUS_COLUMNS) :]
    if len(continuous) != 19 or len(binary) != len(BINARY_COLUMNS) or any(
        item not in (Decimal(0), Decimal(1)) for item in binary
    ):
        raise FormalInputComposerError("scored decision does not carry exact 19+6 controls")
    return {
        "schema": DECISION_JOIN_SCHEMA,
        "decision_id": decision.decision_id,
        "decision_lineage_sha256": decision.lineage_sha256,
        "source_view_id": decision.source_view_id,
        "fold_id": decision.fold_id,
        "decision_session": decision.decision_session.isoformat(),
        "session_position": position,
        "security_id": decision.security_id,
        "disposition": "scored_decision",
        "scoring_disposition": (
            "included_structural_zero"
            if decision.structural_zero else "included_active"
        ),
        "source_row_sha256": decision.final_scoring_row_sha256,
        "scoring_result_id": decision.scoring_result_id,
        "scoring_result_sha256": decision.scoring_result_sha256,
        "scoring_contract_id": decision.scoring_contract_id,
        "scoring_contract_sha256": decision.scoring_contract_sha256,
        "industry_id": decision.industry_id,
        "common_event_component_id": decision.common_event_component_id,
        "structural_zero": decision.structural_zero,
        "firm_specific_score": _decimal_text(decision.firm_specific_score),
        "global_score": _decimal_text(decision.global_score),
        "continuous_controls": [_decimal_text(item) for item in continuous],
        "binary_controls": [int(item) for item in binary],
        "contribution_count": len(decision.contributions),
        "contribution_state_sha256": _contribution_state(
            decision, decision_seed
        ),
        "entry_daily_requirement_id": entry,
        "benchmark_entry_daily_requirement_id": benchmark_entry,
        "horizon_exits": exits,
    }


def _refusal_decision_row(
    refusal: ProductionScoringCensusRefusal, position: int
) -> dict[str, object]:
    return {
        "schema": DECISION_JOIN_SCHEMA,
        "decision_id": refusal.refusal_id,
        "decision_lineage_sha256": refusal.refusal_sha256,
        "source_view_id": refusal.source_view_id,
        "fold_id": refusal.fold_id,
        "decision_session": refusal.decision_session.isoformat(),
        "session_position": position,
        "security_id": refusal.security_id,
        "disposition": "named_preoutcome_refusal",
        "scoring_disposition": refusal.disposition,
        "source_row_sha256": refusal.source_refusal_sha256,
        "scoring_result_id": refusal.scoring_result_id,
        "scoring_result_sha256": refusal.scoring_result_sha256,
        "scoring_contract_id": SCORING_CONTRACT_ID,
        "scoring_contract_sha256": SCORING_CONTRACT_SHA256,
        "industry_id": None,
        "common_event_component_id": None,
        "structural_zero": None,
        "firm_specific_score": None,
        "global_score": None,
        "continuous_controls": None,
        "binary_controls": None,
        "contribution_count": 0,
        "contribution_state_sha256": None,
        "entry_daily_requirement_id": None,
        "benchmark_entry_daily_requirement_id": None,
        "horizon_exits": [],
    }


def _selected_sleeve(
    decisions: Sequence[ProductionScoredDecisionLineage],
) -> tuple[str, ...]:
    positive = tuple(
        sorted(
            (
                (item.firm_specific_score, item.security_id)
                for item in decisions if item.firm_specific_score > 0
            ),
            key=lambda item: (-item[0], item[1]),
        )
    )
    count = (len(positive) + 4) // 5
    if count < 5:
        return ()
    return tuple(item[1] for item in positive[:count])


def _economic_and_terminal_requirements(
    *,
    census: FormalProductionScoringCensus,
    axis: Sequence[date],
    positions: Mapping[date, int],
    benchmark_security_id: str,
    daily_rows: dict[tuple[str, str], dict[str, object]],
    actual_terminal_keys: set[tuple[str, str, int | None]],
) -> tuple[list[dict[str, object]], set[tuple[str, str, int | None]]]:
    joins: list[dict[str, object]] = []
    unmatched_terminal = set(actual_terminal_keys)
    for _, accepted, _ in _source_views(census):
        for decision in accepted:
            for horizon in HORIZONS:
                unmatched_terminal.discard(
                    (
                        "decision_horizon",
                        _decision_terminal_slot_id(
                            decision_id=decision.decision_id, horizon=horizon
                        ),
                        horizon,
                    )
                )
    for view, accepted, _ in _source_views(census):
        by_fold_session: dict[tuple[str, date], list[ProductionScoredDecisionLineage]] = {}
        for decision in accepted:
            by_fold_session.setdefault(
                (decision.fold_id, decision.decision_session), []
            ).append(decision)
        for fold in FORMAL_PRIMARY_FOLD_IDS:
            start, end = _FOLD_TEST_INTERVALS[fold]
            sessions = tuple(item for item in axis if start <= item < end)
            if len(sessions) < 20:
                raise FormalInputComposerError("formal economic fold axis is incomplete")
            active: list[tuple[int, tuple[str, ...]]] = []
            for session in sessions:
                position = positions[session]
                if position + 1 >= len(axis):
                    raise FormalInputComposerError("economic session lacks a next session")
                next_session = axis[position + 1]
                record = {
                    "source_view_id": view,
                    "fold_id": fold,
                    "session": session.isoformat(),
                    "session_position": position,
                    "next_session": next_session.isoformat(),
                    "next_session_position": position + 1,
                }
                lineage = hashlib.sha256(
                    canonical_json_bytes(
                        {"schema": ECONOMIC_JOIN_SCHEMA, **record}
                    )
                ).hexdigest()
                joins.append(
                    {
                        "schema": ECONOMIC_JOIN_SCHEMA,
                        **record,
                        "source_lineage_sha256": lineage,
                    }
                )
                sleeve = _selected_sleeve(
                    by_fold_session.get((fold, session), ())
                )
                active.append((20, sleeve))
                held = tuple(
                    sorted(
                        {
                            security
                            for _, active_sleeve in active
                            for security in active_sleeve
                        }
                    )
                )
                _daily_requirement(daily_rows, benchmark_security_id, session)
                _daily_requirement(daily_rows, benchmark_security_id, next_session)
                for security in held:
                    _daily_requirement(daily_rows, security, session)
                    _daily_requirement(daily_rows, security, next_session)
                    unmatched_terminal.discard(
                        (
                            "economic_daily",
                            _economic_terminal_slot_id(
                                view_id=view,
                                fold_id=fold,
                                session_position=position,
                                security_id=security,
                            ),
                            None,
                        )
                    )
                active = [
                    (remaining - 1, active_sleeve)
                    for remaining, active_sleeve in active if remaining > 1
                ]
    return joins, unmatched_terminal


def _terminal_rows(
    package: FormalTerminalDispositionPackage,
    security_count: int,
) -> list[dict[str, object]]:
    require_formal_terminal_disposition_package(package)
    if (
        package.terminal_census.security_count != security_count
        or package.terminal_census.lifecycle_coverage_count != security_count
    ):
        raise FormalInputComposerError(
            "terminal lifecycle census differs from the scoring security census"
        )
    return [item.to_record() for item in package.rows]


def _shards(
    rows_by_role: Mapping[str, list[dict[str, object]]],
) -> tuple[FormalQcCompressedShard, ...]:
    def row_key(role: str, row: Mapping[str, object]) -> tuple[object, ...]:
        if role == "formal_contract":
            return (0,)
        if role == "contribution_seeds":
            intervals = row["active_intervals"]
            return (
                min(item[0] for item in intervals),
                SOURCE_VIEW_IDS.index(row["source_view_id"]),
                FORMAL_PRIMARY_FOLD_IDS.index(row["fold_id"]),
                row["security_id"], row["seed_id"],
            )
        if role == "decision_joins":
            return (
                FORMAL_PRIMARY_FOLD_IDS.index(row["fold_id"]),
                row["session_position"],
                SOURCE_VIEW_IDS.index(row["source_view_id"]),
                row["security_id"],
            )
        if role == "economic_joins":
            return (
                FORMAL_PRIMARY_FOLD_IDS.index(row["fold_id"]),
                row["session_position"],
                SOURCE_VIEW_IDS.index(row["source_view_id"]),
            )
        if role == "daily_requirements":
            return (row["session"], row["security_id"], row["requirement_id"])
        if role == "minute_requirements":
            return (
                row["first_active_session_position"],
                row["publication_at_utc"], row["security_id"],
                row["requirement_id"],
            )
        return (
            row["slot_kind"], row["slot_id"],
            -1 if row["horizon"] is None else row["horizon"],
        )

    def block_key(role: str, row: Mapping[str, object]) -> tuple[object, ...]:
        if role == "contribution_seeds":
            return (
                FORMAL_PRIMARY_FOLD_IDS.index(row["fold_id"]),
                min(item[0] for item in row["active_intervals"]),
            )
        if role == "decision_joins":
            return (
                FORMAL_PRIMARY_FOLD_IDS.index(row["fold_id"]),
                row["session_position"],
            )
        if role == "daily_requirements":
            return (row["session"],)
        if role == "minute_requirements":
            return (row["first_active_session_position"],)
        # The contract, complete economic axis, and actual terminal subset are
        # bounded headers read before/at finalization rather than row streams.
        return (role,)

    result: list[FormalQcCompressedShard] = []
    for role in SHARD_ROLE_ORDER:
        values = tuple(sorted(rows_by_role[role], key=lambda row: row_key(role, row)))
        groups: list[list[dict[str, object]]] = []
        for row in values:
            key = block_key(role, row)
            if not groups or block_key(role, groups[-1][0]) != key:
                groups.append([])
            groups[-1].append(row)
        chunks: list[list[dict[str, object]]] = []
        current: list[dict[str, object]] = []
        current_bytes = 0
        for group in groups:
            encoded_count = sum(len(canonical_json_bytes(row)) for row in group)
            if (
                len(group) > _MAX_ROWS_PER_SHARD
                or encoded_count > _MAX_RAW_BYTES_PER_SHARD
            ):
                raise FormalInputComposerError(
                    f"one {role} stream block exceeds the shard bound"
                )
            if current and (
                len(current) + len(group) > _MAX_ROWS_PER_SHARD
                or current_bytes + encoded_count > _MAX_RAW_BYTES_PER_SHARD
            ):
                chunks.append(current)
                current = []
                current_bytes = 0
            current.extend(group)
            current_bytes += encoded_count
        if current or not chunks:
            chunks.append(current)
        for ordinal, chunk in enumerate(chunks):
            try:
                result.append(
                    build_formal_qc_compressed_shard(
                        role=role, ordinal=ordinal, rows=chunk
                    )
                )
            except (TypeError, ValueError) as exc:
                raise FormalInputComposerError(
                    f"compact {role} shard could not be built"
                ) from exc
    return tuple(result)


def _source_partition_record(
    *, view: str, decision_rows: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    selected = tuple(
        item for item in decision_rows if item["source_view_id"] == view
    )
    scored = sum(item["disposition"] == "scored_decision" for item in selected)
    terminal_keys = sorted((
        {
            "fold_id": item["fold_id"],
            "session_position": item["session_position"],
            "security_id": item["security_id"],
        }
        for item in selected
    ), key=lambda item: (
        FORMAL_PRIMARY_FOLD_IDS.index(item["fold_id"]),
        item["session_position"], item["security_id"],
    ))
    terminal_digest = hashlib.sha256()
    terminal_digest.update(_TERMINAL_KEY_CENSUS_DOMAIN.encode("ascii") + b"\0")
    for item in terminal_keys:
        payload = canonical_json_bytes(item)
        terminal_digest.update(len(payload).to_bytes(8, "big"))
        terminal_digest.update(payload)
    return {
        "view_id": view,
        "decision_count": len(selected),
        "scored_decision_count": scored,
        "named_preoutcome_refusal_count": len(selected) - scored,
        "terminal_key_sha256": terminal_digest.hexdigest(),
    }


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class FormalCompactInputCandidate:
    candidate_id: str
    candidate_sha256: str
    schema: str
    status: str
    scoring_census: FormalProductionScoringCensus
    production_truth: ProductionTruthArtifact
    accepted_risk: AcceptedRiskPairBinding
    formal_power: FormalPowerCalibrationBinding
    power_floor: PowerFloorBinding
    terminal_package: FormalTerminalDispositionPackage
    preopen_control_stage_output: ArtifactBinding
    benchmark_security_id: str
    runtime_start: date
    runtime_end: date
    calculation_as_of_date: date
    production_input_package: ArtifactBinding
    current_view_partition_set: ArtifactBinding
    censored_view_partition_set: ArtifactBinding
    evaluator_source_closure: ArtifactBinding
    formal_evaluator_source_sha256: str
    cloud_evaluator_source_sha256: str
    shards: tuple[FormalQcCompressedShard, ...]
    resource_census: FormalQcRuntimeResourceCensus
    capacity_candidate_bytes: bytes = dataclasses.field(repr=False)
    formal_evaluator_source: bytes = dataclasses.field(repr=False)
    cloud_evaluator_source: bytes = dataclasses.field(repr=False)

    @property
    def qc_launch_available(self) -> bool:
        return False


_COMPACT_CANDIDATES: dict[
    int,
    tuple[
        weakref.ReferenceType[FormalCompactInputCandidate],
        tuple[object, ...],
        bytes,
        tuple[object, ...],
    ],
] = {}
_COMPACT_CANDIDATES_LOCK = threading.RLock()


def _candidate_topology(value: FormalCompactInputCandidate) -> tuple[object, ...]:
    return (
        id(value.scoring_census),
        id(value.production_truth),
        id(value.accepted_risk),
        id(value.formal_power),
        id(value.power_floor),
        id(value.terminal_package),
        id(value.preopen_control_stage_output),
        id(value.production_input_package),
        id(value.current_view_partition_set),
        id(value.censored_view_partition_set),
        id(value.evaluator_source_closure),
        id(value.shards),
        tuple(id(item) for item in value.shards),
        id(value.capacity_candidate_bytes),
        id(value.formal_evaluator_source),
        id(value.cloud_evaluator_source),
    )


def _candidate_fingerprint(value: FormalCompactInputCandidate) -> tuple[object, ...]:
    return (
        value.candidate_id,
        value.candidate_sha256,
        value.schema,
        value.status,
        value.benchmark_security_id,
        value.runtime_start,
        value.runtime_end,
        value.calculation_as_of_date,
        value.production_input_package,
        value.current_view_partition_set,
        value.censored_view_partition_set,
        value.evaluator_source_closure,
        value.formal_evaluator_source_sha256,
        value.cloud_evaluator_source_sha256,
        value.resource_census,
        hashlib.sha256(value.capacity_candidate_bytes).hexdigest(),
        hashlib.sha256(value.formal_evaluator_source).hexdigest(),
        hashlib.sha256(value.cloud_evaluator_source).hexdigest(),
        value.qc_launch_available,
    )


def _forget_candidate(
    identity: int, reference: weakref.ReferenceType[FormalCompactInputCandidate]
) -> None:
    with _COMPACT_CANDIDATES_LOCK:
        current = _COMPACT_CANDIDATES.get(identity)
        if current is not None and current[0] is reference:
            _COMPACT_CANDIDATES.pop(identity, None)


def build_formal_compact_input_candidate(
    *,
    scoring_results: tuple[ProductionScoringResult, ...],
    production_truth: ProductionTruthArtifact,
    accepted_risk: AcceptedRiskPairBinding,
    formal_power: FormalPowerCalibrationBinding,
    power_floor: PowerFloorBinding,
    terminal_package: FormalTerminalDispositionPackage,
    benchmark_security_id: str,
    calculation_as_of_date: date,
    formal_evaluator_source: bytes,
    cloud_evaluator_source: bytes,
    proposed_capacity_limits: Mapping[str, int],
) -> FormalCompactInputCandidate:
    """Build the exact pre-capacity compact plan; it has no launch authority."""

    if (
        type(calculation_as_of_date) is not date
        or calculation_as_of_date <= _RUNTIME_END
    ):
        raise FormalInputComposerError(
            "calculation_as_of_date must be an exact date after the sealed runtime"
        )
    try:
        scoring_census = build_formal_production_scoring_census(scoring_results)
        preopen = _truth_and_parent_bindings(
            census=scoring_census,
            truth=production_truth,
            accepted_risk=accepted_risk,
            formal_power=formal_power,
            power_floor=power_floor,
        )
        require_formal_terminal_disposition_package(terminal_package)
        evaluator = formal_cloud_evaluator_binding(
            formal_evaluator_source=formal_evaluator_source,
            cloud_evaluator_source=cloud_evaluator_source,
        )
    except (TypeError, ValueError) as exc:
        if isinstance(exc, FormalInputComposerError):
            raise
        raise FormalInputComposerError(
            "formal compact input parents could not be authenticated"
        ) from exc
    axis, positions = _axis()
    contribution_rows, decision_seed, minute_rows = _build_contribution_rows(
        scoring_census, positions
    )
    if not contribution_rows:
        raise FormalInputComposerError(
            "formal scoring census contains no contribution seed"
        )
    daily_rows: dict[tuple[str, str], dict[str, object]] = {}
    decision_rows: list[dict[str, object]] = []
    for _, accepted, refused in _source_views(scoring_census):
        for item in accepted:
            position = positions.get(item.decision_session)
            start, end = _FOLD_TEST_INTERVALS[item.fold_id]
            if position is None or not start <= item.decision_session < end:
                raise FormalInputComposerError(
                    "scored TEST decision escaped its exact fold/session axis"
                )
            decision_rows.append(
                _scored_decision_row(
                    decision=item,
                    position=position,
                    axis=axis,
                    benchmark_security_id=benchmark_security_id,
                    daily_rows=daily_rows,
                    decision_seed=decision_seed,
                )
            )
        for item in refused:
            position = positions.get(item.decision_session)
            start, end = _FOLD_TEST_INTERVALS[item.fold_id]
            if position is None or not start <= item.decision_session < end:
                raise FormalInputComposerError(
                    "refused TEST decision escaped its exact fold/session axis"
                )
            decision_rows.append(_refusal_decision_row(item, position))
    decision_rows.sort(key=canonical_json_bytes)
    actual_terminal_keys = {
        (item.slot_kind, item.slot_id, item.horizon_sessions)
        for item in terminal_package.rows
    }
    economic_rows, unmatched_terminal = _economic_and_terminal_requirements(
        census=scoring_census,
        axis=axis,
        positions=positions,
        benchmark_security_id=benchmark_security_id,
        daily_rows=daily_rows,
        actual_terminal_keys=actual_terminal_keys,
    )
    securities = {
        item.security_id
        for _, accepted, refused in _source_views(scoring_census)
        for item in (*accepted, *refused)
    }
    if unmatched_terminal:
        raise FormalInputComposerError(
            "actual lifecycle terminal row does not map to a possible formal slot"
        )
    terminal_rows = _terminal_rows(terminal_package, len(securities))
    current_partition = _partition_binding(
        SOURCE_VIEW_IDS[0],
        scoring_census.current_view.accepted,
        scoring_census.current_view.refused,
    )
    censored_partition = _partition_binding(
        SOURCE_VIEW_IDS[1],
        scoring_census.censored_view.accepted,
        scoring_census.censored_view.refused,
    )
    input_record = {
        "production_scoring_census": {
            "census_id": scoring_census.census_id,
            "census_sha256": scoring_census.census_sha256,
            "scoring_contract_id": scoring_census.scoring_contract_id,
            "scoring_contract_sha256": scoring_census.scoring_contract_sha256,
            "result_bindings": [
                item.to_record() for item in scoring_census.result_bindings
            ],
        },
        "production_truth": {
            "artifact_id": production_truth.artifact_id,
            "artifact_sha256": production_truth.artifact_sha256,
            "terminal_projection_sha256": production_truth.terminal_projection_sha256,
        },
        "preopen_control_stage_output": preopen.to_record(),
        "accepted_risk": accepted_risk.to_record(),
        "formal_power": formal_power.to_record(),
        "power_floor": power_floor.to_record(),
        "terminal_package": {
            "package_id": terminal_package.package_id,
            "package_sha256": terminal_package.package_sha256,
            "terminal_census": terminal_package.terminal_census.to_record(),
        },
        "source_view_partition_sets": {
            SOURCE_VIEW_IDS[0]: current_partition.to_record(),
            SOURCE_VIEW_IDS[1]: censored_partition.to_record(),
        },
        "decision_join_count": len(decision_rows),
        "contribution_seed_count": len(contribution_rows),
        "economic_join_count": len(economic_rows),
        "daily_requirement_count": len(daily_rows),
        "minute_requirement_count": len(minute_rows),
    }
    production_input, input_payload = _artifact(
        prefix="arv2-formal-production-input-",
        schema=_PRODUCTION_INPUT_SCHEMA,
        record=input_record,
    )
    contract = {
        "schema": FORMAL_CONTRACT_SCHEMA,
        "evaluation_id": EVALUATION_ID,
        "evaluation_input_bundle_id": production_input.artifact_id,
        "evaluation_input_bundle_sha256": production_input.content_sha256,
        "production_scoring_census_id": scoring_census.census_id,
        "production_scoring_census_sha256": scoring_census.census_sha256,
        "scoring_contract_id": scoring_census.scoring_contract_id,
        "scoring_contract_sha256": scoring_census.scoring_contract_sha256,
        "scoring_result_bindings": [
            item.to_record() for item in scoring_census.result_bindings
        ],
        "production_truth_artifact_id": production_truth.artifact_id,
        "production_truth_artifact_sha256": production_truth.artifact_sha256,
        "preopen_control_stage_output": preopen.to_record(),
        "formal_evaluator_source_sha256": hashlib.sha256(
            formal_evaluator_source
        ).hexdigest(),
        "accepted_risk": accepted_risk.to_record(),
        "power_floor": {
            "receipt_id": formal_power.receipt_id,
            "receipt_sha256": formal_power.receipt_sha256,
            "required_valid_dates": formal_power.required_valid_dates,
            "required_connected_components": (
                formal_power.required_connected_components
            ),
        },
        "terminal_package_id": terminal_package.package_id,
        "terminal_package_sha256": terminal_package.package_sha256,
        "terminal_census": {
            "terminal_policy_id": TERMINAL_POLICY_ID,
            "terminal_requirement_count": (
                terminal_package.terminal_census.terminal_requirement_count
            ),
            "terminal_payoff_count": (
                terminal_package.terminal_census.terminal_payoff_count
            ),
            "benchmark_splice_continuation_count": (
                terminal_package.terminal_census.benchmark_splice_continuation_count
            ),
            "named_terminal_refusal_count": (
                terminal_package.terminal_census.named_terminal_refusal_count
            ),
            "silently_omitted_count": 0,
        },
        "source_view_partitions": [
            _source_partition_record(view=view, decision_rows=decision_rows)
            for view in SOURCE_VIEW_IDS
        ],
        "stream_layout": {
            "layout_id": STREAM_LAYOUT_ID,
            "role_sort_keys": {
                role: list(STREAM_ROLE_SORT_KEYS[role])
                for role in SHARD_ROLE_ORDER
            },
            "session_or_market_day_blocks_never_split_across_shards": True,
            "formal_contract_and_economic_axis_are_bounded_headers": True,
            "terminal_dispositions_are_the_actual_lifecycle_subset": True,
            "market_observation_collection_passes": 2,
            "maximum_horizon_session_lookahead": 60,
            "second_pass_rederives_observations": True,
            "terminal_subset_is_capacity_bounded_header": True,
        },
    }
    rows_by_role = {
        "formal_contract": [contract],
        "contribution_seeds": contribution_rows,
        "decision_joins": decision_rows,
        "economic_joins": economic_rows,
        "daily_requirements": list(daily_rows.values()),
        "minute_requirements": list(minute_rows.values()),
        "terminal_dispositions": terminal_rows,
    }
    shards = _shards(rows_by_role)
    daily_security = {item[0] for item in daily_rows}
    daily_blocks: dict[int, set[str]] = {}
    for security, session_text in daily_rows:
        block = date.fromisoformat(session_text).toordinal() // 32
        daily_blocks.setdefault(block, set()).add(security)
    minute_activation_days: dict[tuple[int, str], set[str]] = {}
    for (security, instant), row in minute_rows.items():
        key = (int(row["first_active_session_position"]), instant[:10])
        minute_activation_days.setdefault(key, set()).add(security)
    resource_census = derive_formal_qc_runtime_resource_census(
        shards=shards,
        distinct_security_count=len(
            daily_security | {item[0] for item in minute_rows}
        ),
        daily_history_batch_count=2 * sum(
            len(securities) for securities in daily_blocks.values()
        ),
        minute_history_batch_count=2 * sum(
            len(securities) for securities in minute_activation_days.values()
        ),
        maximum_dynamic_subscription_count=1,
        projected_summary_payload_byte_count=ABSOLUTE_MAX_SUMMARY_PAYLOAD_BYTES,
        projected_summary_chunk_count=ABSOLUTE_MAX_SUMMARY_CHUNKS,
    )
    capacity_candidate = render_formal_qc_capacity_review_candidate(
        census=resource_census, limits=proposed_capacity_limits
    )
    record = {
        "schema": _COMPACT_CANDIDATE_SCHEMA,
        "status": STATUS,
        "production_input_package": production_input.to_record(),
        "production_input_payload_sha256": hashlib.sha256(
            input_payload
        ).hexdigest(),
        "scoring_census_id": scoring_census.census_id,
        "scoring_census_sha256": scoring_census.census_sha256,
        "production_truth_artifact_id": production_truth.artifact_id,
        "production_truth_artifact_sha256": production_truth.artifact_sha256,
        "preopen_control_stage_output": preopen.to_record(),
        "current_view_partition_set": current_partition.to_record(),
        "censored_view_partition_set": censored_partition.to_record(),
        "terminal_package_id": terminal_package.package_id,
        "terminal_package_sha256": terminal_package.package_sha256,
        "evaluator_source_closure": evaluator.to_record(),
        "formal_evaluator_source_sha256": hashlib.sha256(
            formal_evaluator_source
        ).hexdigest(),
        "cloud_evaluator_source_sha256": hashlib.sha256(
            cloud_evaluator_source
        ).hexdigest(),
        "runtime_start": _RUNTIME_START.isoformat(),
        "runtime_end": _RUNTIME_END.isoformat(),
        "calculation_as_of_date": calculation_as_of_date.isoformat(),
        "benchmark_security_id": benchmark_security_id,
        "shards": [item.descriptor() for item in shards],
        "resource_census": resource_census.to_record(),
        "capacity_candidate_sha256": hashlib.sha256(
            capacity_candidate
        ).hexdigest(),
        "qc_launch_available": False,
    }
    digest = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    value = object.__new__(FormalCompactInputCandidate)
    values = {
        "candidate_id": "arv2-formal-compact-input-" + digest[:24],
        "candidate_sha256": digest,
        "schema": _COMPACT_CANDIDATE_SCHEMA,
        "status": STATUS,
        "scoring_census": scoring_census,
        "production_truth": production_truth,
        "accepted_risk": accepted_risk,
        "formal_power": formal_power,
        "power_floor": power_floor,
        "terminal_package": terminal_package,
        "preopen_control_stage_output": preopen,
        "benchmark_security_id": benchmark_security_id,
        "runtime_start": _RUNTIME_START,
        "runtime_end": _RUNTIME_END,
        "calculation_as_of_date": calculation_as_of_date,
        "production_input_package": production_input,
        "current_view_partition_set": current_partition,
        "censored_view_partition_set": censored_partition,
        "evaluator_source_closure": evaluator,
        "formal_evaluator_source_sha256": hashlib.sha256(
            formal_evaluator_source
        ).hexdigest(),
        "cloud_evaluator_source_sha256": hashlib.sha256(
            cloud_evaluator_source
        ).hexdigest(),
        "shards": shards,
        "resource_census": resource_census,
        "capacity_candidate_bytes": capacity_candidate,
        "formal_evaluator_source": bytes(formal_evaluator_source),
        "cloud_evaluator_source": bytes(cloud_evaluator_source),
    }
    for name, item in values.items():
        object.__setattr__(value, name, item)
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_candidate(key, ref)
    )
    with _COMPACT_CANDIDATES_LOCK:
        _COMPACT_CANDIDATES[identity] = (
            reference,
            _candidate_topology(value),
            canonical_json_bytes(record),
            _candidate_fingerprint(value),
        )
    return require_formal_compact_input_candidate(value)


def require_formal_compact_input_candidate(
    value: FormalCompactInputCandidate,
) -> FormalCompactInputCandidate:
    if type(value) is not FormalCompactInputCandidate:
        raise FormalInputComposerError("compact input candidate changed type")
    with _COMPACT_CANDIDATES_LOCK:
        registered = _COMPACT_CANDIDATES.get(id(value))
    if registered is None or registered[0]() is not value:
        raise FormalInputComposerError(
            "compact input candidate is not builder-authenticated"
        )
    try:
        require_formal_production_scoring_census(value.scoring_census)
        require_production_truth_artifact(value.production_truth)
        require_accepted_risk_pair_binding(value.accepted_risk)
        require_formal_power_calibration_binding(value.formal_power)
        require_power_floor_binding(value.power_floor)
        require_formal_terminal_disposition_package(value.terminal_package)
        require_artifact_binding(value.preopen_control_stage_output)
        require_artifact_binding(value.production_input_package)
        require_artifact_binding(value.current_view_partition_set)
        require_artifact_binding(value.censored_view_partition_set)
        for shard in value.shards:
            require_formal_qc_compressed_shard(shard)
    except (TypeError, ValueError) as exc:
        raise FormalInputComposerError("compact input candidate parent changed") from exc
    if (
        registered[1] != _candidate_topology(value)
        or registered[3] != _candidate_fingerprint(value)
        or value.schema != _COMPACT_CANDIDATE_SCHEMA
        or value.status != STATUS
        or value.qc_launch_available is not False
        or value.runtime_start != _RUNTIME_START
        or value.runtime_end != _RUNTIME_END
        or type(value.calculation_as_of_date) is not date
        or value.calculation_as_of_date <= value.runtime_end
        or hashlib.sha256(value.formal_evaluator_source).hexdigest()
        != value.formal_evaluator_source_sha256
        or hashlib.sha256(value.cloud_evaluator_source).hexdigest()
        != value.cloud_evaluator_source_sha256
    ):
        raise FormalInputComposerError("compact input candidate content/topology changed")
    return value


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class FormalCompactRunPlan:
    plan_id: str
    plan_sha256: str
    schema: str
    status: str
    candidate: FormalCompactInputCandidate
    capacity: FormalQcRuntimeCapacityBinding
    input_manifest_payload: bytes
    input_manifest: QcObjectPayloadBinding
    runtime_projection: FormalQcRuntimeProjection
    upload_bundle: FormalQcUploadBundle
    formal_run_candidate: FormalRunCandidate
    downstream_runtime_resource_census_capacity_verified: bool
    upstream_truth_and_six_result_materialization_capacity_authenticated: bool
    qc_action_authority: bool

    @property
    def launch_available(self) -> bool:
        return False


_COMPACT_PLANS: dict[
    int,
    tuple[
        weakref.ReferenceType[FormalCompactRunPlan],
        tuple[object, ...],
        bytes,
        tuple[object, ...],
    ],
] = {}
_COMPACT_PLANS_LOCK = threading.RLock()


def _plan_topology(value: FormalCompactRunPlan) -> tuple[object, ...]:
    return (
        id(value.candidate),
        id(value.capacity),
        id(value.input_manifest_payload),
        id(value.input_manifest),
        id(value.runtime_projection),
        id(value.upload_bundle),
        id(value.formal_run_candidate),
    )


def _plan_fingerprint(value: FormalCompactRunPlan) -> tuple[object, ...]:
    return (
        value.plan_id,
        value.plan_sha256,
        value.schema,
        value.status,
        value.input_manifest.content_sha256,
        hashlib.sha256(value.input_manifest_payload).hexdigest(),
        value.runtime_projection.projection_id,
        value.runtime_projection.projection_sha256,
        value.upload_bundle.bundle_id,
        value.upload_bundle.bundle_sha256,
        value.formal_run_candidate.candidate_id,
        value.formal_run_candidate.candidate_sha256,
        value.downstream_runtime_resource_census_capacity_verified,
        value.upstream_truth_and_six_result_materialization_capacity_authenticated,
        value.qc_action_authority,
        value.launch_available,
    )


def _forget_plan(
    identity: int, reference: weakref.ReferenceType[FormalCompactRunPlan]
) -> None:
    with _COMPACT_PLANS_LOCK:
        current = _COMPACT_PLANS.get(identity)
        if current is not None and current[0] is reference:
            _COMPACT_PLANS.pop(identity, None)


def finalize_formal_compact_run_plan(
    *,
    candidate: FormalCompactInputCandidate,
    capacity: FormalQcRuntimeCapacityBinding,
) -> FormalCompactRunPlan:
    """Refuse the legacy six-result materialization path before any QC plan.

    ``candidate`` exists for fixture compatibility and for auditing the old
    source-chain projection.  Its capacity candidate describes downstream QC
    runtime resources only; it cannot authenticate the host-side materializing
    of one complete ``ProductionTruthArtifact`` plus six simultaneous
    ``ProductionScoringResult`` objects.  The sequential scoring-projection
    successor remains separately blocked until that upstream one-fold
    materialization capacity is authenticated.
    """

    require_formal_compact_input_candidate(candidate)
    raise FormalInputComposerError(
        "legacy six-result compact candidate cannot be finalized: upstream "
        "truth and scoring materialization capacity is not authenticated"
    )


def require_formal_compact_run_plan(
    value: FormalCompactRunPlan,
) -> FormalCompactRunPlan:
    if type(value) is not FormalCompactRunPlan:
        raise FormalInputComposerError("compact run plan changed type")
    with _COMPACT_PLANS_LOCK:
        registered = _COMPACT_PLANS.get(id(value))
    if registered is None or registered[0]() is not value:
        raise FormalInputComposerError("compact run plan is not builder-authenticated")
    try:
        require_formal_compact_input_candidate(value.candidate)
        require_formal_qc_runtime_capacity_binding(value.capacity)
        require_formal_qc_runtime_projection(value.runtime_projection)
        require_formal_qc_upload_bundle(value.upload_bundle)
    except (TypeError, ValueError, FormalQcSubmissionError) as exc:
        raise FormalInputComposerError("compact run plan parent changed") from exc
    if (
        registered[1] != _plan_topology(value)
        or registered[3] != _plan_fingerprint(value)
        or value.schema != _COMPACT_PLAN_SCHEMA
        or value.status != "reviewable_exact_source_chain_no_qc_action_authority"
        or value.downstream_runtime_resource_census_capacity_verified is not True
        or value.upstream_truth_and_six_result_materialization_capacity_authenticated
        is not False
        or value.qc_action_authority is not False
        or value.launch_available is not False
        or hashlib.sha256(value.input_manifest_payload).hexdigest()
        != value.input_manifest.content_sha256
    ):
        raise FormalInputComposerError("compact run plan content/topology changed")
    return value


__all__ = (
    "AUTHORITY",
    "FormalCompactInputCandidate",
    "FormalCompactRunPlan",
    "FormalInputComposerError",
    "FormalTerminalDispositionPackage",
    "FormalTerminalDispositionRow",
    "STATUS",
    "TERMINAL_PACKAGE_SCHEMA",
    "build_formal_compact_input_candidate",
    "finalize_formal_compact_run_plan",
    "load_formal_terminal_disposition_package",
    "render_formal_terminal_disposition_package_bytes",
    "require_formal_compact_input_candidate",
    "require_formal_compact_run_plan",
    "require_formal_terminal_disposition_package",
)
