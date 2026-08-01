"""ML-LR-0: shared experiment contracts (live-readiness plan section 6).

Every later milestone's runner needs the same three things: a stable identity
for an experiment, a frozen statement of what would count as success BEFORE
results are seen, and an immutable record of what a run actually produced.
Without a shared contract each runner would invent its own, and the
preregistration discipline the whole plan rests on would decay into
per-script convention.

The single most important property here is that `ResearchGateSpec` and
`ConfirmationSpec` are part of the HASHED spec. A gate chosen after seeing
results is not a gate; binding it into `spec_hash` means moving the goalposts
produces a different experiment identity, which `--mode confirmation` then
refuses (plan section 8.3).

Deliberately reuses `ml/contracts.py`'s existing `_freeze_json`,
`_check_sha256`, and `_parse_timestamp` rather than adding a third copy of
each -- the repository already carries two (contracts.py and
evaluation.py's `_freeze_report_json`), and a third would be one more place
for the NaN/naive-timestamp rules to drift apart.
"""
from __future__ import annotations

import contextlib
import dataclasses
import re
from typing import Any, Mapping, Sequence

from ml.contracts import (
    ContractError,
    _check_required_str,
    _check_sha256,
    _freeze_json,
    _parse_timestamp,
)
from ml.hashing import hash_payload

SCHEMA_VERSION = "1.0"
_SUPPORTED_SCHEMA_VERSIONS = frozenset({SCHEMA_VERSION})

MODES = ("discovery", "confirmation")

# Plan section 6.2: the spec must contain no field that could be read as
# trade authority. Enforced on the FROZEN, SERIALIZED payload rather than
# only on declared dataclass fields, so a forbidden key smuggled inside a
# nested mapping (e.g. cost_tax_liquidity_assumptions={"side": "buy"}) is
# caught too.
_FORBIDDEN_KEYS = frozenset(
    {
        "production", "production_authoritative", "approved", "approval",
        "authority", "authorization", "authorized", "side", "quantity",
        "shares", "target_weight", "target_weights", "order_type",
        "limit_price", "stop_price", "execute", "promote", "promoted",
    }
)

_FORBIDDEN_KEY_TOKENS = frozenset(
    {
        "production", "approved", "approval", "authority", "authorization",
        "authorized", "side", "quantity", "shares", "execute", "promote",
        "promoted",
    }
)
_MODEL_DIMENSION_KEYS = frozenset({"models", "candidate_models", "model_variants"})


class ExperimentContractError(ContractError):
    """An experiment spec or run record failed its contract check."""


@contextlib.contextmanager
def _as_experiment_error():
    """Translate reused ml/contracts.py failures into this module's type.

    The helpers below (`_check_sha256`, `_parse_timestamp`, `_freeze_json`,
    `_check_required_str`) are deliberately shared rather than duplicated,
    but they raise the parent `ContractError`. Since
    `ExperimentContractError` is a SUBCLASS, a caller writing
    `except ExperimentContractError` would NOT catch them -- silently
    missing exactly the validation failures this module promises to
    surface. Translating at the boundary keeps one set of rules while
    making the module's advertised error type actually true.
    """
    try:
        yield
    except ExperimentContractError:
        raise
    except ContractError as exc:
        raise ExperimentContractError(str(exc)) from exc


def _check_schema_version(schema_version: str) -> None:
    if schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
        raise ExperimentContractError(
            f"unknown schema_version {schema_version!r}; "
            f"supported: {sorted(_SUPPORTED_SCHEMA_VERSIONS)}"
        )


def _normalize_key(key: Any) -> str:
    key_text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(key).strip())
    return re.sub(r"[^a-zA-Z0-9]+", "_", key_text).strip("_").lower()


def _reject_forbidden_keys(payload: Any, *, path: str = "spec") -> None:
    """Walk a serialized payload rejecting any execution-shaped key."""
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            # Normalize snake_case, kebab-case, spaces, and camelCase so an
            # execution-shaped field cannot bypass the boundary merely by
            # changing its spelling (for example targetWeight or trade-side).
            normalized = _normalize_key(key)
            tokens = frozenset(part for part in normalized.split("_") if part)
            padded = f"_{normalized}_"
            contains_forbidden_phrase = any(
                f"_{forbidden}_" in padded for forbidden in _FORBIDDEN_KEYS
            )
            if contains_forbidden_phrase or tokens & _FORBIDDEN_KEY_TOKENS:
                raise ExperimentContractError(
                    f"{path}.{key} is an execution-shaped field; an experiment "
                    "spec describes research, never trade authority"
                )
            _reject_forbidden_keys(value, path=f"{path}.{key}")
        return
    if isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            _reject_forbidden_keys(value, path=f"{path}[{index}]")


def _unique_string_tuple(value: Any, name: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ExperimentContractError(f"{name} must be a list or tuple of strings")
    result = tuple(value)
    if not result and not allow_empty:
        raise ExperimentContractError(f"{name} must contain at least one entry")
    for index, item in enumerate(result):
        _check_required_str(item, f"{name}[{index}]")
    if len(set(result)) != len(result):
        # Plan section 6.2: "reject ... duplicate variants". A duplicate is
        # not harmless -- research-look counting derives from these tuples,
        # so a repeated model name would understate the multiplicity
        # correction relative to the variants actually examined.
        raise ExperimentContractError(f"{name} must not contain duplicates")
    return result


def _strict_payload_kwargs(
    contract_type: type[Any],
    payload: Mapping[str, Any],
    *,
    read_only_fields: Sequence[str] = (),
) -> dict[str, Any]:
    """Return constructor kwargs from a strict JSON-object payload.

    Dataclass construction already rejects unknown keyword arguments, but it
    does so with a raw ``TypeError`` and provides no loading path for nested
    contracts.  Every persisted experiment contract uses this helper so
    schema drift fails closed and is reported through the module's advertised
    error type.
    """
    name = contract_type.__name__
    if not isinstance(payload, Mapping):
        raise ExperimentContractError(f"{name} payload must be a JSON object")
    fields = {field.name for field in dataclasses.fields(contract_type)}
    unknown = set(payload) - fields - set(read_only_fields)
    if unknown:
        raise ExperimentContractError(
            f"{name} payload has unknown fields: {sorted(unknown, key=str)}"
        )
    return {key: value for key, value in payload.items() if key in fields}


@dataclasses.dataclass(frozen=True)
class ResearchGateSpec:
    """What would count as success, fixed BEFORE any result is seen.

    Every threshold here is preregistered. Plan section 8.4 forbids changing
    any of them after inspecting confirmation output, and binding this into
    the parent spec's hash is the mechanism that makes the prohibition
    checkable rather than merely stated.
    """

    minimum_folds_won: int
    minimum_coverage_fraction: float
    maximum_alpha: float
    block_lengths: tuple[int, ...]
    required_calibration_bins: int
    failure_slices: tuple[str, ...]

    def __post_init__(self) -> None:
        with _as_experiment_error():
            self._validate()

    def _validate(self) -> None:
        if (
            isinstance(self.minimum_folds_won, bool)
            or not isinstance(self.minimum_folds_won, int)
            or self.minimum_folds_won < 2
        ):
            # Doc 14.1 requires beating the baseline in MORE THAN ONE
            # untouched fold; a gate permitting 1 would contradict it.
            raise ExperimentContractError("minimum_folds_won must be an integer >= 2")
        for name in ("minimum_coverage_fraction", "maximum_alpha"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0 < float(value) <= 1
            ):
                raise ExperimentContractError(f"{name} must be within (0, 1]")
        if not isinstance(self.block_lengths, tuple) or not self.block_lengths:
            raise ExperimentContractError("block_lengths must be a non-empty tuple")
        for length in self.block_lengths:
            if isinstance(length, bool) or not isinstance(length, int) or length < 1:
                raise ExperimentContractError("block_lengths must be positive integers")
        if len(set(self.block_lengths)) != len(self.block_lengths):
            raise ExperimentContractError("block_lengths must not contain duplicates")
        if (
            isinstance(self.required_calibration_bins, bool)
            or not isinstance(self.required_calibration_bins, int)
            or self.required_calibration_bins < 2
        ):
            raise ExperimentContractError("required_calibration_bins must be an integer >= 2")
        object.__setattr__(
            self, "failure_slices", _unique_string_tuple(self.failure_slices, "failure_slices")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "minimum_folds_won": self.minimum_folds_won,
            "minimum_coverage_fraction": self.minimum_coverage_fraction,
            "maximum_alpha": self.maximum_alpha,
            "block_lengths": list(self.block_lengths),
            "required_calibration_bins": self.required_calibration_bins,
            "failure_slices": list(self.failure_slices),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ResearchGateSpec":
        kwargs = _strict_payload_kwargs(cls, payload)
        if isinstance(kwargs.get("block_lengths"), (list, tuple)):
            kwargs["block_lengths"] = tuple(kwargs["block_lengths"])
        try:
            return cls(**kwargs)
        except TypeError as exc:
            raise ExperimentContractError(
                f"ResearchGateSpec payload missing required field(s): {exc}"
            ) from exc


@dataclasses.dataclass(frozen=True)
class ConfirmationSpec:
    """Binds a confirmation run to the immutable discovery run it tests.

    Plan section 8.4: discovery and confirmation must have different
    immutable experiment IDs, and confirmation may not retune anything. The
    parent hashes here make "this confirmation tests exactly that
    discovery" a verifiable claim instead of a naming convention.
    """

    parent_experiment_id: str
    parent_spec_hash: str
    parent_report_hash: str

    def __post_init__(self) -> None:
        with _as_experiment_error():
            self._validate()

    def _validate(self) -> None:
        _check_required_str(self.parent_experiment_id, "parent_experiment_id")
        _check_sha256(self.parent_spec_hash, "parent_spec_hash")
        _check_sha256(self.parent_report_hash, "parent_report_hash")

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_experiment_id": self.parent_experiment_id,
            "parent_spec_hash": self.parent_spec_hash,
            "parent_report_hash": self.parent_report_hash,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConfirmationSpec":
        kwargs = _strict_payload_kwargs(cls, payload)
        try:
            return cls(**kwargs)
        except TypeError as exc:
            raise ExperimentContractError(
                f"ConfirmationSpec payload missing required field(s): {exc}"
            ) from exc


@dataclasses.dataclass(frozen=True)
class ExperimentSpec:
    """The complete, hashable description of one experiment."""

    experiment_id: str
    task: str
    mode: str
    created_at: str
    primary_outcome: str
    candidate_models: tuple[str, ...]
    frozen_baselines: tuple[str, ...]
    feature_set_version: str
    label_version: str
    benchmark: str
    horizon_sessions: int
    universe_definition: str
    research_look_dimensions: Mapping[str, Sequence[str]]
    split_configuration: Mapping[str, Any]
    cost_tax_liquidity_assumptions: Mapping[str, Any]
    research_gate: ResearchGateSpec
    random_seed: int
    ordered_feature_names: tuple[str, ...] = ()
    target_column: str = "label_value"
    baseline_columns: Mapping[str, str] = dataclasses.field(default_factory=dict)
    confirmation: ConfirmationSpec | None = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        with _as_experiment_error():
            self._validate()

    def _validate(self) -> None:
        _check_schema_version(self.schema_version)
        for name in (
            "experiment_id", "task", "primary_outcome", "feature_set_version",
            "label_version", "benchmark", "universe_definition", "target_column",
        ):
            _check_required_str(getattr(self, name), name)
        if self.mode not in MODES:
            raise ExperimentContractError(f"mode must be one of {MODES}, got {self.mode!r}")
        _parse_timestamp(self.created_at, "created_at")
        if (
            isinstance(self.horizon_sessions, bool)
            or not isinstance(self.horizon_sessions, int)
            or self.horizon_sessions < 1
        ):
            raise ExperimentContractError("horizon_sessions must be a positive integer")
        if (
            isinstance(self.random_seed, bool)
            or not isinstance(self.random_seed, int)
            or self.random_seed < 0
        ):
            # Matches the existing ModelManifest contract and the sklearn
            # random_state consumers these experiment specs will drive.
            raise ExperimentContractError("random_seed must be a non-negative integer")
        if not isinstance(self.research_gate, ResearchGateSpec):
            raise ExperimentContractError("research_gate must be a ResearchGateSpec")

        candidates = _unique_string_tuple(self.candidate_models, "candidate_models")
        baselines = _unique_string_tuple(self.frozen_baselines, "frozen_baselines")
        ordered_features = _unique_string_tuple(
            self.ordered_feature_names,
            "ordered_feature_names",
            allow_empty=True,
        )
        overlap = set(candidates) & set(baselines)
        if overlap:
            # A model cannot be its own control. If the same name appears on
            # both sides, "beat the baseline" becomes a comparison against
            # itself and the gate is vacuous.
            raise ExperimentContractError(
                f"a model cannot be both candidate and frozen baseline: {sorted(overlap)}"
            )

        if not isinstance(self.research_look_dimensions, Mapping) or not self.research_look_dimensions:
            raise ExperimentContractError(
                "research_look_dimensions must be a non-empty mapping"
            )
        frozen_dimensions: dict[str, tuple[str, ...]] = {}
        for key, values in self.research_look_dimensions.items():
            _check_required_str(key, "research_look_dimensions key")
            frozen_dimensions[key] = _unique_string_tuple(
                values, f"research_look_dimensions[{key}]"
            )
        model_dimensions = (
            values
            for key, values in frozen_dimensions.items()
            if _normalize_key(key) in _MODEL_DIMENSION_KEYS
        )
        if len(candidates) > 1 and not any(
            set(values) == set(candidates) for values in model_dimensions
        ):
            raise ExperimentContractError(
                "research_look_dimensions must include the complete candidate_models "
                "variant set so total_research_looks cannot undercount tested models"
            )

        # Mode/confirmation consistency, both directions (plan 6.2: "reject
        # ... inconsistent discovery/confirmation fields").
        if self.mode == "confirmation" and self.confirmation is None:
            raise ExperimentContractError(
                "confirmation mode requires an immutable parent discovery "
                "spec/report hash"
            )
        if self.mode == "discovery" and self.confirmation is not None:
            raise ExperimentContractError(
                "discovery mode must not carry a confirmation parent"
            )
        if self.confirmation is not None and not isinstance(self.confirmation, ConfirmationSpec):
            raise ExperimentContractError("confirmation must be a ConfirmationSpec")
        if (
            self.confirmation is not None
            and self.confirmation.parent_experiment_id == self.experiment_id
        ):
            raise ExperimentContractError(
                "a confirmation experiment must have a different experiment_id "
                "than the discovery run it confirms"
            )

        split_configuration = _freeze_json(
            self.split_configuration, path="split_configuration"
        )
        assumptions = _freeze_json(
            self.cost_tax_liquidity_assumptions, path="cost_tax_liquidity_assumptions"
        )
        baseline_columns = _freeze_json(
            self.baseline_columns, path="baseline_columns"
        )
        if not isinstance(split_configuration, Mapping):
            raise ExperimentContractError("split_configuration must be a JSON object")
        if not isinstance(assumptions, Mapping):
            raise ExperimentContractError(
                "cost_tax_liquidity_assumptions must be a JSON object"
            )
        if not isinstance(baseline_columns, Mapping):
            raise ExperimentContractError("baseline_columns must be a JSON object")
        for name, column in baseline_columns.items():
            _check_required_str(name, "baseline_columns key")
            _check_required_str(column, f"baseline_columns[{name}]")
        if len(set(baseline_columns.values())) != len(baseline_columns):
            raise ExperimentContractError(
                "baseline_columns must not map multiple baselines to one column"
            )

        object.__setattr__(self, "candidate_models", candidates)
        object.__setattr__(self, "frozen_baselines", baselines)
        object.__setattr__(self, "ordered_feature_names", ordered_features)
        object.__setattr__(
            self, "research_look_dimensions",
            _freeze_json(frozen_dimensions, path="research_look_dimensions"),
        )
        object.__setattr__(self, "split_configuration", split_configuration)
        object.__setattr__(self, "cost_tax_liquidity_assumptions", assumptions)
        object.__setattr__(self, "baseline_columns", baseline_columns)

        _reject_forbidden_keys(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "experiment_id": self.experiment_id,
            "task": self.task,
            "mode": self.mode,
            "created_at": self.created_at,
            "primary_outcome": self.primary_outcome,
            "candidate_models": list(self.candidate_models),
            "frozen_baselines": list(self.frozen_baselines),
            "feature_set_version": self.feature_set_version,
            "label_version": self.label_version,
            "benchmark": self.benchmark,
            "horizon_sessions": self.horizon_sessions,
            "universe_definition": self.universe_definition,
            "research_look_dimensions": {
                key: list(values) for key, values in self.research_look_dimensions.items()
            },
            "split_configuration": _plain(self.split_configuration),
            "cost_tax_liquidity_assumptions": _plain(self.cost_tax_liquidity_assumptions),
            "research_gate": self.research_gate.to_dict(),
            "random_seed": self.random_seed,
            "ordered_feature_names": list(self.ordered_feature_names),
            "target_column": self.target_column,
            "baseline_columns": dict(self.baseline_columns),
            "confirmation": (
                self.confirmation.to_dict() if self.confirmation is not None else None
            ),
        }
        return payload

    @property
    def spec_hash(self) -> str:
        """Identity derived from canonical JSON of the whole spec.

        Includes the research gate and confirmation parent, so changing a
        threshold or re-pointing a confirmation at a different discovery run
        yields a DIFFERENT experiment rather than silently mutating one.
        """
        return hash_payload(self.to_dict())

    def total_research_looks(self) -> int:
        """Derived from the variants actually present in the spec.

        Plan 6.2: "make research-look count derive from the variants
        actually present in the spec". A hand-entered integer would drift
        from reality the moment a variant is added, and every multiplicity
        correction downstream would silently become too lenient.
        """
        total = 1
        for values in self.research_look_dimensions.values():
            total *= len(values)
        return total

    def identity(self) -> "ExperimentIdentity":
        return ExperimentIdentity(
            experiment_id=self.experiment_id,
            task=self.task,
            mode=self.mode,
            spec_hash=self.spec_hash,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExperimentSpec":
        kwargs = _strict_payload_kwargs(cls, payload)
        gate_payload = kwargs.get("research_gate")
        if isinstance(gate_payload, Mapping):
            kwargs["research_gate"] = ResearchGateSpec.from_dict(gate_payload)
        elif gate_payload is not None:
            raise ExperimentContractError(
                "ExperimentSpec research_gate must be a JSON object"
            )
        confirmation_payload = kwargs.get("confirmation")
        if isinstance(confirmation_payload, Mapping):
            kwargs["confirmation"] = ConfirmationSpec.from_dict(confirmation_payload)
        elif confirmation_payload is not None:
            raise ExperimentContractError(
                "ExperimentSpec confirmation must be a JSON object or null"
            )
        try:
            return cls(**kwargs)
        except TypeError as exc:
            raise ExperimentContractError(
                f"ExperimentSpec payload missing required field(s): {exc}"
            ) from exc


def _plain(value: Any) -> Any:
    """Convert frozen MappingProxyType/tuple structures back to plain JSON
    types for serialization."""
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


@dataclasses.dataclass(frozen=True)
class ExperimentIdentity:
    """The minimal tuple that identifies one experiment run."""

    experiment_id: str
    task: str
    mode: str
    spec_hash: str

    def __post_init__(self) -> None:
        with _as_experiment_error():
            self._validate()

    def _validate(self) -> None:
        _check_required_str(self.experiment_id, "experiment_id")
        _check_required_str(self.task, "task")
        if self.mode not in MODES:
            raise ExperimentContractError(f"mode must be one of {MODES}")
        _check_sha256(self.spec_hash, "spec_hash")

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "task": self.task,
            "mode": self.mode,
            "spec_hash": self.spec_hash,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExperimentIdentity":
        kwargs = _strict_payload_kwargs(cls, payload)
        try:
            return cls(**kwargs)
        except TypeError as exc:
            raise ExperimentContractError(
                f"ExperimentIdentity payload missing required field(s): {exc}"
            ) from exc


@dataclasses.dataclass(frozen=True)
class ExperimentRunRecord:
    """Immutable record of what one run actually produced.

    Carries hashes rather than payloads: the point is to make a run
    reproducible and tamper-evident, not to duplicate the artifacts it
    already wrote atomically via ml/artifacts.py.
    """

    identity: ExperimentIdentity
    dataset_id: str
    dataset_hash: str
    code_commit: str
    started_at: str
    completed_at: str
    report_hash: str
    artifact_hashes: Mapping[str, str]
    total_research_looks: int
    verdict: str
    promotion_blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        with _as_experiment_error():
            self._validate()

    def _validate(self) -> None:
        if not isinstance(self.identity, ExperimentIdentity):
            raise ExperimentContractError("identity must be an ExperimentIdentity")
        _check_required_str(self.dataset_id, "dataset_id")
        _check_sha256(self.dataset_hash, "dataset_hash")
        _check_required_str(self.code_commit, "code_commit")
        started = _parse_timestamp(self.started_at, "started_at")
        completed = _parse_timestamp(self.completed_at, "completed_at")
        if completed < started:
            raise ExperimentContractError("completed_at must not precede started_at")
        _check_sha256(self.report_hash, "report_hash")
        if (
            isinstance(self.total_research_looks, bool)
            or not isinstance(self.total_research_looks, int)
            or self.total_research_looks < 1
        ):
            raise ExperimentContractError("total_research_looks must be a positive integer")

        from ml.evaluation import EvaluationReport

        if self.verdict not in EvaluationReport.VERDICTS:
            # Reuse the evaluation module's vocabulary rather than defining a
            # second, drifting one -- and note it contains no "promoted"
            # value by design.
            raise ExperimentContractError(
                f"verdict must be one of {EvaluationReport.VERDICTS}"
            )
        if not isinstance(self.artifact_hashes, Mapping):
            raise ExperimentContractError("artifact_hashes must be a mapping")
        for key, digest in self.artifact_hashes.items():
            _check_required_str(key, "artifact_hashes key")
            _check_sha256(digest, f"artifact_hashes[{key}]")
        object.__setattr__(
            self, "artifact_hashes",
            _freeze_json(dict(self.artifact_hashes), path="artifact_hashes"),
        )
        object.__setattr__(
            self, "promotion_blockers",
            _unique_string_tuple(
                self.promotion_blockers, "promotion_blockers", allow_empty=True
            ),
        )

    @property
    def production_authoritative(self) -> bool:
        """Always False. A run record describes research output; authority
        requires the separate human promotion decision of ML-LR-9."""
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "dataset_id": self.dataset_id,
            "dataset_hash": self.dataset_hash,
            "code_commit": self.code_commit,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "report_hash": self.report_hash,
            "artifact_hashes": dict(self.artifact_hashes),
            "total_research_looks": self.total_research_looks,
            "verdict": self.verdict,
            "promotion_blockers": list(self.promotion_blockers),
            "production_authoritative": self.production_authoritative,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExperimentRunRecord":
        kwargs = _strict_payload_kwargs(
            cls, payload, read_only_fields=("production_authoritative",)
        )
        if payload.get("production_authoritative", False) is not False:
            raise ExperimentContractError(
                "ExperimentRunRecord production_authoritative must be false"
            )
        identity_payload = kwargs.get("identity")
        if isinstance(identity_payload, Mapping):
            kwargs["identity"] = ExperimentIdentity.from_dict(identity_payload)
        elif identity_payload is not None:
            raise ExperimentContractError(
                "ExperimentRunRecord identity must be a JSON object"
            )
        try:
            return cls(**kwargs)
        except TypeError as exc:
            raise ExperimentContractError(
                f"ExperimentRunRecord payload missing required field(s): {exc}"
            ) from exc

    @property
    def run_hash(self) -> str:
        return hash_payload(self.to_dict())
