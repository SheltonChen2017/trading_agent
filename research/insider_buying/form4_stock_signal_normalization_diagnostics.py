"""Synthetic-only, zero-authority IB-3B cross-sectional diagnostics.

The module evaluates the owner-approved winsorization and population-z-score
policy over an explicit caller-declared fixture cohort.  Positive signals must
replay from exact IB-3A diagnostics.  Structural-zero, ineligible, and missing
names are separate sealed states so an omitted name is never silently inferred.
The output is diagnostic evidence only: canonical scores, ranks, seeds,
outcomes, ETF construction, QC, deployment, and trading remain unavailable.
"""
from __future__ import annotations

import re
import threading
import weakref
from dataclasses import InitVar, dataclass
from decimal import (
    Context,
    Decimal,
    DecimalException,
    ROUND_CEILING,
    ROUND_HALF_EVEN,
)
from enum import Enum

from data.financial_primitives import decimal_text
from data.hashing import hash_payload
from research.insider_buying.form4_stock_signal_formula_diagnostics import (
    FORM4_STOCK_SIGNAL_FORMULA_DIAGNOSTICS_VERSION,
    FORM4_STOCK_SIGNAL_NUMERIC_POLICY_HASH,
    Form4StockSignalFormulaDiagnostics,
    Form4StockSignalFormulaDiagnosticsError,
    build_form4_stock_signal_formula_diagnostics,
)


FORM4_STOCK_SIGNAL_NORMALIZATION_DIAGNOSTICS_VERSION = (
    "INSETF-IB3B-FORM4-STOCK-SIGNAL-NORMALIZATION-DIAGNOSTICS-v1"
)
FORM4_STOCK_SIGNAL_NORMALIZATION_LOWER_QUANTILE = Decimal("0.01")
FORM4_STOCK_SIGNAL_NORMALIZATION_UPPER_QUANTILE = Decimal("0.99")
FORM4_STOCK_SIGNAL_NORMALIZATION_QUANTILE_METHOD = (
    "type-7-linear-h=(N-1)*p-value-based-ties"
)
FORM4_STOCK_SIGNAL_NORMALIZATION_VARIANCE_DENOMINATOR = "population-N"
FORM4_STOCK_SIGNAL_NORMALIZATION_MINIMUM_USABLE_NAMES = 20
FORM4_STOCK_SIGNAL_NORMALIZATION_MINIMUM_DISTINCT_VALUES = 2
FORM4_STOCK_SIGNAL_NORMALIZATION_DECIMAL_PRECISION = 50
FORM4_STOCK_SIGNAL_NORMALIZATION_DECIMAL_ROUNDING = "ROUND_HALF_EVEN"
FORM4_STOCK_SIGNAL_NORMALIZATION_ZERO_DISPERSION_POLICY = (
    "unavailable-no-epsilon-no-substituted-zero"
)
FORM4_STOCK_SIGNAL_NORMALIZATION_FINAL_QUANTIZATION = None
FORM4_STOCK_SIGNAL_NORMALIZATION_RANKING_POLICY = "deferred"
FORM4_STOCK_SIGNAL_NORMALIZATION_SEED_POLICY = "deferred"
MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_ROWS = 10_000
MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_TEXT_CHARACTERS = 128

_NORMALIZATION_INPUT_PROJECTION = (
    "context.create_decimal-each-usable-value-before-value-sort"
)
_NORMALIZATION_MOMENT_REDUCTION_ORDER = (
    "sorted-min-anchored-offset-context-sum-"
    "single-division-clamped-to-range-then-sequential-context-summed-"
    "squared-deviations"
)
_NORMALIZATION_STANDARD_DEVIATION_EVALUATION = (
    "context.sqrt-population-variance"
)

_MAX_NORMALIZATION_DECIMAL_DIGITS = 1_024
_MAX_NORMALIZATION_DECIMAL_ABS_EXPONENT = 2_048
_CIK_RE = re.compile(r"^[0-9]{10}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_UPSTREAM_DIAGNOSTICS_ID_RE = re.compile(
    r"^form4-stock-signal-formula-diagnostics-[0-9a-f]{16}$"
)
_OBSERVATION_FACTORY_TOKEN = object()
_ROW_FACTORY_TOKEN = object()
_IDENTITY_FACTORY_TOKEN = object()
_RESULT_FACTORY_TOKEN = object()


class Form4StockSignalNormalizationDiagnosticsError(ValueError):
    """A bounded synthetic IB-3B normalization contract failed closed."""


class Form4StockSignalNormalizationDisposition(str, Enum):
    """One explicit terminal state for a supplied synthetic stock name."""

    INCLUDE_SIGNAL = "include_signal"
    INCLUDE_STRUCTURAL_ZERO = "include_structural_zero"
    EXCLUDE_INELIGIBLE = "exclude_ineligible"
    EXCLUDE_MISSING = "exclude_missing"
    REFUSE_ELIGIBLE_MISSING_SCORE = "refuse_eligible_missing_score"


class Form4StockSignalNormalizationOutcome(str, Enum):
    """Computational availability of one complete declared cohort."""

    AVAILABLE = "available"
    UNAVAILABLE_INSUFFICIENT_USABLE_COHORT = (
        "unavailable_insufficient_usable_cohort"
    )
    UNAVAILABLE_ZERO_DISPERSION = "unavailable_zero_dispersion"


def _policy_payload() -> dict[str, object]:
    return {
        "diagnostics_version": FORM4_STOCK_SIGNAL_NORMALIZATION_DIAGNOSTICS_VERSION,
        "population": "complete-caller-declared-synthetically-eligible-cohort",
        "structural_zero_names": "included",
        "ineligible_names": "retained-excluded-from-numerics",
        "missing_names": "explicit-keyed-row-retained-excluded-from-numerics",
        "eligible_missing_score": "refuse-entire-cohort",
        "lower_quantile": decimal_text(
            FORM4_STOCK_SIGNAL_NORMALIZATION_LOWER_QUANTILE
        ),
        "upper_quantile": decimal_text(
            FORM4_STOCK_SIGNAL_NORMALIZATION_UPPER_QUANTILE
        ),
        "quantile_method": FORM4_STOCK_SIGNAL_NORMALIZATION_QUANTILE_METHOD,
        "variance_denominator": (
            FORM4_STOCK_SIGNAL_NORMALIZATION_VARIANCE_DENOMINATOR
        ),
        "minimum_usable_names": (
            FORM4_STOCK_SIGNAL_NORMALIZATION_MINIMUM_USABLE_NAMES
        ),
        "minimum_distinct_post_winsor_values": (
            FORM4_STOCK_SIGNAL_NORMALIZATION_MINIMUM_DISTINCT_VALUES
        ),
        "zero_dispersion": (
            FORM4_STOCK_SIGNAL_NORMALIZATION_ZERO_DISPERSION_POLICY
        ),
        "decimal_precision": FORM4_STOCK_SIGNAL_NORMALIZATION_DECIMAL_PRECISION,
        "decimal_rounding": FORM4_STOCK_SIGNAL_NORMALIZATION_DECIMAL_ROUNDING,
        "decimal_emin": -999_999,
        "decimal_emax": 999_999,
        "decimal_capitals": 1,
        "decimal_clamp": 0,
        "decimal_flags": [],
        "decimal_traps": [],
        "final_quantization": FORM4_STOCK_SIGNAL_NORMALIZATION_FINAL_QUANTIZATION,
        "input_projection": _NORMALIZATION_INPUT_PROJECTION,
        "moment_reduction_order": _NORMALIZATION_MOMENT_REDUCTION_ORDER,
        "standard_deviation_evaluation": (
            _NORMALIZATION_STANDARD_DEVIATION_EVALUATION
        ),
        "ranking": FORM4_STOCK_SIGNAL_NORMALIZATION_RANKING_POLICY,
        "seed_selection": FORM4_STOCK_SIGNAL_NORMALIZATION_SEED_POLICY,
        "upstream_diagnostics_version": (
            FORM4_STOCK_SIGNAL_FORMULA_DIAGNOSTICS_VERSION
        ),
        "upstream_numeric_policy_hash": FORM4_STOCK_SIGNAL_NUMERIC_POLICY_HASH,
        "resource_bounds": {
            "rows": MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_ROWS,
            "text_characters": MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_TEXT_CHARACTERS,
            "decimal_digits": _MAX_NORMALIZATION_DECIMAL_DIGITS,
            "decimal_abs_exponent": _MAX_NORMALIZATION_DECIMAL_ABS_EXPONENT,
        },
    }


FORM4_STOCK_SIGNAL_NORMALIZATION_POLICY_HASH = hash_payload(_policy_payload())


def _new_decimal_context() -> Context:
    return Context(
        prec=FORM4_STOCK_SIGNAL_NORMALIZATION_DECIMAL_PRECISION,
        rounding=ROUND_HALF_EVEN,
        Emin=-999_999,
        Emax=999_999,
        capitals=1,
        clamp=0,
        flags=[],
        traps=[],
    )


def _require_frozen_policy() -> None:
    if (
        FORM4_STOCK_SIGNAL_NORMALIZATION_DIAGNOSTICS_VERSION
        != "INSETF-IB3B-FORM4-STOCK-SIGNAL-NORMALIZATION-DIAGNOSTICS-v1"
        or FORM4_STOCK_SIGNAL_NORMALIZATION_LOWER_QUANTILE != Decimal("0.01")
        or FORM4_STOCK_SIGNAL_NORMALIZATION_UPPER_QUANTILE != Decimal("0.99")
        or FORM4_STOCK_SIGNAL_NORMALIZATION_QUANTILE_METHOD
        != "type-7-linear-h=(N-1)*p-value-based-ties"
        or FORM4_STOCK_SIGNAL_NORMALIZATION_VARIANCE_DENOMINATOR
        != "population-N"
        or FORM4_STOCK_SIGNAL_NORMALIZATION_MINIMUM_USABLE_NAMES != 20
        or FORM4_STOCK_SIGNAL_NORMALIZATION_MINIMUM_DISTINCT_VALUES != 2
        or FORM4_STOCK_SIGNAL_NORMALIZATION_DECIMAL_PRECISION != 50
        or FORM4_STOCK_SIGNAL_NORMALIZATION_DECIMAL_ROUNDING
        != "ROUND_HALF_EVEN"
        or FORM4_STOCK_SIGNAL_NORMALIZATION_ZERO_DISPERSION_POLICY
        != "unavailable-no-epsilon-no-substituted-zero"
        or FORM4_STOCK_SIGNAL_NORMALIZATION_FINAL_QUANTIZATION is not None
        or FORM4_STOCK_SIGNAL_NORMALIZATION_RANKING_POLICY != "deferred"
        or FORM4_STOCK_SIGNAL_NORMALIZATION_SEED_POLICY != "deferred"
        or MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_ROWS != 10_000
        or MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_TEXT_CHARACTERS != 128
        or _MAX_NORMALIZATION_DECIMAL_DIGITS != 1_024
        or _MAX_NORMALIZATION_DECIMAL_ABS_EXPONENT != 2_048
        or _NORMALIZATION_INPUT_PROJECTION
        != "context.create_decimal-each-usable-value-before-value-sort"
        or _NORMALIZATION_MOMENT_REDUCTION_ORDER
        != (
            "sorted-min-anchored-offset-context-sum-"
            "single-division-clamped-to-range-then-sequential-context-summed-"
            "squared-deviations"
        )
        or _NORMALIZATION_STANDARD_DEVIATION_EVALUATION
        != "context.sqrt-population-variance"
        or hash_payload(_policy_payload())
        != FORM4_STOCK_SIGNAL_NORMALIZATION_POLICY_HASH
    ):
        raise Form4StockSignalNormalizationDiagnosticsError(
            "REFUSED: frozen IB-3B normalization policy is inconsistent"
        )


def _text(value: object, *, label: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or not value.isprintable()
        or len(value) > MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_TEXT_CHARACTERS
    ):
        raise Form4StockSignalNormalizationDiagnosticsError(
            f"REFUSED: {label} must be bounded canonical text"
        )
    return value


def _sha256(value: object, *, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise Form4StockSignalNormalizationDiagnosticsError(
            f"REFUSED: {label} must be lowercase SHA-256"
        )
    return value


def _builder_commit(value: object) -> str:
    if type(value) is not str or _GIT_COMMIT_RE.fullmatch(value) is None:
        raise Form4StockSignalNormalizationDiagnosticsError(
            "REFUSED: builder Git commit must be lowercase full SHA-1"
        )
    return value


def _stock_key(
    issuer_cik: object,
    security_id: object,
    share_class_id: object,
) -> tuple[str, str, str]:
    if type(issuer_cik) is not str or _CIK_RE.fullmatch(issuer_cik) is None:
        raise Form4StockSignalNormalizationDiagnosticsError(
            "REFUSED: fixture issuer CIK must contain ten digits"
        )
    return (
        issuer_cik,
        _text(security_id, label="fixture security ID"),
        _text(share_class_id, label="fixture share-class ID"),
    )


def _decimal(value: object, *, label: str, allow_zero: bool) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise Form4StockSignalNormalizationDiagnosticsError(
            f"REFUSED: {label} must be an exact finite Decimal"
        )
    decimal_tuple = value.as_tuple()
    if (
        len(decimal_tuple.digits) > _MAX_NORMALIZATION_DECIMAL_DIGITS
        or abs(int(decimal_tuple.exponent))
        > _MAX_NORMALIZATION_DECIMAL_ABS_EXPONENT
    ):
        raise Form4StockSignalNormalizationDiagnosticsError(
            f"REFUSED: {label} exceeds the Decimal resource bound"
        )
    if value < 0 or (not allow_zero and value == 0):
        qualifier = "nonnegative" if allow_zero else "positive"
        raise Form4StockSignalNormalizationDiagnosticsError(
            f"REFUSED: {label} must be {qualifier}"
        )
    return value


def _derived_decimal(value: object, *, label: str, allow_zero: bool) -> Decimal:
    parsed = _decimal(value, label=label, allow_zero=allow_zero)
    try:
        projected = _new_decimal_context().create_decimal(parsed)
    except DecimalException as exc:
        raise Form4StockSignalNormalizationDiagnosticsError(
            f"REFUSED: {label} is outside the frozen 50-digit output context"
        ) from exc
    if (
        len(parsed.as_tuple().digits)
        > FORM4_STOCK_SIGNAL_NORMALIZATION_DECIMAL_PRECISION
        or projected != parsed
    ):
        raise Form4StockSignalNormalizationDiagnosticsError(
            f"REFUSED: {label} is outside the frozen 50-digit output context"
        )
    return parsed


def _type7_quantile_is_forced_zero(
    *,
    structural_zero_count: int,
    usable_count: int,
    percentile_numerator: int,
) -> bool:
    """Return whether Type-7's upper interpolation endpoint is still zero."""

    upper_index = (
        (usable_count - 1) * percentile_numerator + 99
    ) // 100
    return structural_zero_count > upper_index


def _coarse_population_variance_cap(
    lower: Decimal,
    upper: Decimal,
) -> Decimal:
    """Return range squared, a rounding-safe cap four times the exact maximum."""

    context = Context(
        prec=FORM4_STOCK_SIGNAL_NORMALIZATION_DECIMAL_PRECISION,
        rounding=ROUND_CEILING,
        Emin=-999_999,
        Emax=999_999,
        capitals=1,
        clamp=0,
        flags=[],
        traps=[],
    )
    value_range = context.subtract(upper, lower)
    return context.multiply(value_range, value_range)


def _type7_quantile_lower_index(
    *,
    usable_count: int,
    percentile_numerator: int,
) -> int:
    """Return Type-7's exact lower interpolation index for /100 percentiles."""

    return ((usable_count - 1) * percentile_numerator) // 100


def _maximum_context_mean_from_counts(
    *,
    signal_count: int,
    structural_zero_count: int,
    lower: Decimal,
    upper: Decimal,
) -> Decimal:
    """Replay the largest 50-digit mean compatible with category counts."""

    context = _new_decimal_context()
    values = (lower,) * structural_zero_count + (upper,) * signal_count
    return _context_mean(context, values)


_BOOLEAN_AUTHORITY_FIELDS = (
    "role_normalization_verified",
    "role_normalization_authorized",
    "ib2_completion_authorized",
    "official_security_master_compatibility_verified",
    "qc_symbol_id_mapping_verified",
    "authenticated_amendment_supersession_verified",
    "calendar_session_mapping_verified",
    "point_in_time_issuer_identity_verified",
    "point_in_time_reporting_owner_identity_verified",
    "point_in_time_security_identity_verified",
    "point_in_time_transaction_identity_verified",
    "ordinary_equity_classification_verified",
    "canonical_filter_authorized",
    "deduplication_authorized",
    "lot_aggregation_authorized",
    "post_aggregation_minimum_gate_authorized",
    "canonical_stock_score_authorized",
    "cross_sectional_normalization_authorized",
    "seed_signal_authorized",
    "sec_access_authorized",
    "provider_access_authorized",
    "outcomes_authorized",
    "etf_construction_authorized",
    "qc_execution_authorized",
    "broker_access_authorized",
    "deployment_authorized",
    "trading_authorized",
)


class _ZeroAuthority:
    @property
    def population_is_caller_declared(self) -> bool:
        return True

    @property
    def canonical_population_verified(self) -> bool:
        return False

    @property
    def role_ids_are_caller_declared(self) -> bool:
        return True

    @property
    def role_normalization_verified(self) -> bool:
        return False

    @property
    def role_normalization_authorized(self) -> bool:
        return False

    @property
    def ib2_completion_authorized(self) -> bool:
        return False

    @property
    def official_security_master_compatibility_verified(self) -> bool:
        return False

    @property
    def qc_symbol_id_mapping_verified(self) -> bool:
        return False

    @property
    def authenticated_amendment_supersession_verified(self) -> bool:
        return False

    @property
    def calendar_session_mapping_verified(self) -> bool:
        return False

    @property
    def point_in_time_issuer_identity_verified(self) -> bool:
        return False

    @property
    def point_in_time_reporting_owner_identity_verified(self) -> bool:
        return False

    @property
    def point_in_time_security_identity_verified(self) -> bool:
        return False

    @property
    def point_in_time_transaction_identity_verified(self) -> bool:
        return False

    @property
    def ordinary_equity_classification_verified(self) -> bool:
        return False

    @property
    def canonical_filter_authorized(self) -> bool:
        return False

    @property
    def deduplication_authorized(self) -> bool:
        return False

    @property
    def lot_aggregation_authorized(self) -> bool:
        return False

    @property
    def post_aggregation_minimum_gate_authorized(self) -> bool:
        return False

    @property
    def canonical_stock_score_authorized(self) -> bool:
        return False

    @property
    def cross_sectional_normalization_authorized(self) -> bool:
        return False

    @property
    def seed_signal_authorized(self) -> bool:
        return False

    @property
    def sec_access_authorized(self) -> bool:
        return False

    @property
    def provider_access_authorized(self) -> bool:
        return False

    @property
    def outcomes_authorized(self) -> bool:
        return False

    @property
    def etf_construction_authorized(self) -> bool:
        return False

    @property
    def qc_execution_authorized(self) -> bool:
        return False

    @property
    def broker_access_authorized(self) -> bool:
        return False

    @property
    def deployment_authorized(self) -> bool:
        return False

    @property
    def trading_authorized(self) -> bool:
        return False

    @property
    def authorized_outcome_looks(self) -> int:
        return 0

    @property
    def consumed_outcome_looks(self) -> int:
        return 0

    def authority_payload(self) -> dict[str, object]:
        return {
            "population_is_caller_declared": True,
            "canonical_population_verified": False,
            "role_ids_are_caller_declared": True,
            **{name: False for name in _BOOLEAN_AUTHORITY_FIELDS},
            "authorized_outcome_looks": 0,
            "consumed_outcome_looks": 0,
        }


def _require_zero_authority(value: object) -> None:
    if getattr(value, "population_is_caller_declared") is not True:
        raise Form4StockSignalNormalizationDiagnosticsError(
            "REFUSED: IB-3B population must remain caller-declared"
        )
    if getattr(value, "canonical_population_verified") is not False:
        raise Form4StockSignalNormalizationDiagnosticsError(
            "REFUSED: IB-3B cannot verify a canonical population"
        )
    if getattr(value, "role_ids_are_caller_declared") is not True:
        raise Form4StockSignalNormalizationDiagnosticsError(
            "REFUSED: IB-3B role IDs remain caller-declared"
        )
    if any(type(getattr(value, name)) is not bool for name in _BOOLEAN_AUTHORITY_FIELDS):
        raise Form4StockSignalNormalizationDiagnosticsError(
            "REFUSED: every IB-3B authority flag must be an exact boolean"
        )
    if any(getattr(value, name) is not False for name in _BOOLEAN_AUTHORITY_FIELDS):
        raise Form4StockSignalNormalizationDiagnosticsError(
            "REFUSED: IB-3B normalization diagnostics cannot grant authority"
        )
    for name in ("authorized_outcome_looks", "consumed_outcome_looks"):
        count = getattr(value, name)
        if type(count) is not int or count != 0:
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: IB-3B diagnostics require exactly zero outcome looks"
            )


@dataclass(frozen=True)
class Form4StockSignalNormalizationObservation(_ZeroAuthority):
    """One sealed, explicit stock-name state in a synthetic cohort."""

    synthetic_source_id: str
    issuer_cik: str
    security_id: str
    share_class_id: str
    disposition: Form4StockSignalNormalizationDisposition
    raw_stock_score_diagnostic: Decimal | None
    upstream_diagnostics_id: str | None
    upstream_payload_hash: str | None
    upstream_builder_git_commit: str | None
    upstream_diagnostics_version: str | None
    upstream_numeric_policy_hash: str | None
    observation_id: str
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _OBSERVATION_FACTORY_TOKEN:
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: normalization observation must be factory-created"
            )
        _sha256(self.synthetic_source_id, label="synthetic source ID")
        _stock_key(self.issuer_cik, self.security_id, self.share_class_id)
        if type(self.disposition) is not Form4StockSignalNormalizationDisposition:
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: normalization disposition must be an exact enum"
            )
        upstream = (
            self.upstream_diagnostics_id,
            self.upstream_payload_hash,
            self.upstream_builder_git_commit,
            self.upstream_diagnostics_version,
            self.upstream_numeric_policy_hash,
        )
        if self.disposition is Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL:
            _decimal(
                self.raw_stock_score_diagnostic,
                label="signal raw stock-score diagnostic",
                allow_zero=False,
            )
            if any(value is None for value in upstream):
                raise Form4StockSignalNormalizationDiagnosticsError(
                    "REFUSED: signal observation requires complete IB-3A lineage"
                )
            _text(self.upstream_diagnostics_id, label="upstream diagnostics ID")
            if _UPSTREAM_DIAGNOSTICS_ID_RE.fullmatch(self.upstream_diagnostics_id) is None:
                raise Form4StockSignalNormalizationDiagnosticsError(
                    "REFUSED: upstream diagnostics ID has an invalid shape"
                )
            _sha256(self.upstream_payload_hash, label="upstream payload hash")
            _builder_commit(self.upstream_builder_git_commit)
            if (
                type(self.upstream_diagnostics_version) is not str
                or self.upstream_diagnostics_version
                != FORM4_STOCK_SIGNAL_FORMULA_DIAGNOSTICS_VERSION
            ):
                raise Form4StockSignalNormalizationDiagnosticsError(
                    "REFUSED: signal observation has inconsistent IB-3A policy lineage"
                )
            _sha256(
                self.upstream_numeric_policy_hash,
                label="upstream numeric policy hash",
            )
            if (
                self.upstream_numeric_policy_hash
                != FORM4_STOCK_SIGNAL_NUMERIC_POLICY_HASH
                or self.synthetic_source_id != self.upstream_payload_hash
            ):
                raise Form4StockSignalNormalizationDiagnosticsError(
                    "REFUSED: signal observation has inconsistent IB-3A policy lineage"
                )
        elif self.disposition is Form4StockSignalNormalizationDisposition.INCLUDE_STRUCTURAL_ZERO:
            structural_zero = _decimal(
                self.raw_stock_score_diagnostic,
                label="structural-zero raw stock-score diagnostic",
                allow_zero=True,
            )
            if structural_zero != Decimal("0"):
                raise Form4StockSignalNormalizationDiagnosticsError(
                    "REFUSED: structural-zero observation must carry exact zero"
                )
            if any(value is not None for value in upstream):
                raise Form4StockSignalNormalizationDiagnosticsError(
                    "REFUSED: structural zero cannot claim IB-3A signal lineage"
                )
        else:
            if self.raw_stock_score_diagnostic is not None:
                raise Form4StockSignalNormalizationDiagnosticsError(
                    "REFUSED: excluded or eligible-missing observation cannot carry a score"
                )
            if any(value is not None for value in upstream):
                raise Form4StockSignalNormalizationDiagnosticsError(
                    "REFUSED: nonsignal observation cannot claim IB-3A lineage"
                )
        _sha256(self.observation_id, label="normalization observation ID")
        if self.observation_id != hash_payload(self.lineage_payload()):
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: normalization observation ID is inconsistent"
            )
        _require_zero_authority(self)

    @property
    def stock_key(self) -> tuple[str, str, str]:
        return (self.issuer_cik, self.security_id, self.share_class_id)

    def lineage_payload(self) -> dict[str, object]:
        return {
            "synthetic_source_id": self.synthetic_source_id,
            "issuer_cik": self.issuer_cik,
            "security_id": self.security_id,
            "share_class_id": self.share_class_id,
            "disposition": self.disposition.value,
            "raw_stock_score_diagnostic": (
                None
                if self.raw_stock_score_diagnostic is None
                else decimal_text(self.raw_stock_score_diagnostic)
            ),
            "upstream_diagnostics_id": self.upstream_diagnostics_id,
            "upstream_payload_hash": self.upstream_payload_hash,
            "upstream_builder_git_commit": self.upstream_builder_git_commit,
            "upstream_diagnostics_version": self.upstream_diagnostics_version,
            "upstream_numeric_policy_hash": self.upstream_numeric_policy_hash,
            **self.authority_payload(),
        }

    def to_payload(self) -> dict[str, object]:
        return {**self.lineage_payload(), "observation_id": self.observation_id}


def _observation_runtime_fingerprint(
    value: Form4StockSignalNormalizationObservation,
) -> str:
    raw = value.raw_stock_score_diagnostic
    return hash_payload(
        {
            **value.lineage_payload(),
            "raw_decimal_tuple": (
                None
                if raw is None
                else {
                    "sign": raw.as_tuple().sign,
                    "digits": list(raw.as_tuple().digits),
                    "exponent": int(raw.as_tuple().exponent),
                }
            ),
            "observation_id": value.observation_id,
        }
    )


_OBSERVATION_REGISTRY: dict[
    int, tuple[weakref.ReferenceType[Form4StockSignalNormalizationObservation], str]
] = {}
_OBSERVATION_REGISTRY_LOCK = threading.RLock()


def _register_observation(value: Form4StockSignalNormalizationObservation) -> None:
    identity = id(value)
    fingerprint = _observation_runtime_fingerprint(value)

    def remove(
        reference: weakref.ReferenceType[Form4StockSignalNormalizationObservation],
    ) -> None:
        with _OBSERVATION_REGISTRY_LOCK:
            current = _OBSERVATION_REGISTRY.get(identity)
            if current is not None and current[0] is reference:
                _OBSERVATION_REGISTRY.pop(identity, None)

    reference = weakref.ref(value, remove)
    with _OBSERVATION_REGISTRY_LOCK:
        _OBSERVATION_REGISTRY[identity] = (reference, fingerprint)


def _require_factory_observation(value: object) -> str:
    if type(value) is not Form4StockSignalNormalizationObservation:
        raise Form4StockSignalNormalizationDiagnosticsError(
            "REFUSED: cohort inputs must be exact normalization observations"
        )
    Form4StockSignalNormalizationObservation.__post_init__(
        value,
        _OBSERVATION_FACTORY_TOKEN,
    )
    fingerprint = _observation_runtime_fingerprint(value)
    with _OBSERVATION_REGISTRY_LOCK:
        registered = _OBSERVATION_REGISTRY.get(id(value))
        if (
            registered is None
            or registered[0]() is not value
            or registered[1] != fingerprint
        ):
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: normalization observation is unsealed or mutated"
            )
    return fingerprint


def _snapshot_observation(
    value: object,
) -> tuple[Form4StockSignalNormalizationObservation, str]:
    if type(value) is not Form4StockSignalNormalizationObservation:
        raise Form4StockSignalNormalizationDiagnosticsError(
            "REFUSED: cohort inputs must be exact normalization observations"
        )
    snapshot = Form4StockSignalNormalizationObservation(
        synthetic_source_id=value.synthetic_source_id,
        issuer_cik=value.issuer_cik,
        security_id=value.security_id,
        share_class_id=value.share_class_id,
        disposition=value.disposition,
        raw_stock_score_diagnostic=value.raw_stock_score_diagnostic,
        upstream_diagnostics_id=value.upstream_diagnostics_id,
        upstream_payload_hash=value.upstream_payload_hash,
        upstream_builder_git_commit=value.upstream_builder_git_commit,
        upstream_diagnostics_version=value.upstream_diagnostics_version,
        upstream_numeric_policy_hash=value.upstream_numeric_policy_hash,
        observation_id=value.observation_id,
        _verified_factory_token=_OBSERVATION_FACTORY_TOKEN,
    )
    fingerprint = _observation_runtime_fingerprint(snapshot)
    if _require_factory_observation(value) != fingerprint:
        raise Form4StockSignalNormalizationDiagnosticsError(
            "REFUSED: captured normalization observation is unsealed or mutated"
        )
    _register_observation(snapshot)
    return snapshot, fingerprint


def build_form4_stock_signal_normalization_observation(
    *,
    issuer_cik: str,
    security_id: str,
    share_class_id: str,
    disposition: Form4StockSignalNormalizationDisposition,
    synthetic_source_id: str | None = None,
    source_diagnostics: Form4StockSignalFormulaDiagnostics | None = None,
) -> Form4StockSignalNormalizationObservation:
    """Build one explicit synthetic cohort row without granting authority."""

    stock_key = _stock_key(issuer_cik, security_id, share_class_id)
    if type(disposition) is not Form4StockSignalNormalizationDisposition:
        raise Form4StockSignalNormalizationDiagnosticsError(
            "REFUSED: normalization disposition must be an exact enum"
        )

    raw_score: Decimal | None = None
    upstream_id: str | None = None
    upstream_hash: str | None = None
    upstream_commit: str | None = None
    upstream_version: str | None = None
    upstream_policy_hash: str | None = None

    if disposition is Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL:
        if type(source_diagnostics) is not Form4StockSignalFormulaDiagnostics:
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: signal observation requires exact IB-3A diagnostics"
            )
        if synthetic_source_id is not None:
            _sha256(synthetic_source_id, label="signal synthetic source ID")
        try:
            replayed = build_form4_stock_signal_formula_diagnostics(
                source_diagnostics.events,
                builder_git_commit=source_diagnostics.identity.builder_git_commit,
            )
        except Form4StockSignalFormulaDiagnosticsError as exc:
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: source IB-3A diagnostics do not replay"
            ) from exc
        if source_diagnostics != replayed:
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: source IB-3A diagnostics are inconsistent or changed"
            )
        replayed_hash = hash_payload(replayed.to_payload())
        before_hash = hash_payload(source_diagnostics.to_payload())
        after_hash = hash_payload(source_diagnostics.to_payload())
        if (
            before_hash != after_hash
            or before_hash != replayed_hash
        ):
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: source IB-3A diagnostics are inconsistent or changed"
            )
        if stock_key != (
            replayed.issuer_cik,
            replayed.security_id,
            replayed.share_class_id,
        ):
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: observation stock key does not match IB-3A diagnostics"
            )
        if synthetic_source_id is not None and synthetic_source_id != replayed_hash:
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: signal synthetic source ID must match its IB-3A payload"
            )
        synthetic_source_id = replayed_hash
        raw_score = replayed.raw_stock_score_diagnostic
        upstream_id = replayed.identity.diagnostics_id
        upstream_hash = replayed_hash
        upstream_commit = replayed.identity.builder_git_commit
        upstream_version = replayed.identity.diagnostics_version
        upstream_policy_hash = replayed.identity.numeric_policy_hash
    else:
        if source_diagnostics is not None:
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: nonsignal observation cannot consume IB-3A diagnostics"
            )
        synthetic_source_id = _sha256(
            synthetic_source_id,
            label="synthetic source ID",
        )
        if disposition is Form4StockSignalNormalizationDisposition.INCLUDE_STRUCTURAL_ZERO:
            raw_score = Decimal("0")

    payload = {
        "synthetic_source_id": synthetic_source_id,
        "issuer_cik": stock_key[0],
        "security_id": stock_key[1],
        "share_class_id": stock_key[2],
        "disposition": disposition.value,
        "raw_stock_score_diagnostic": (
            None if raw_score is None else decimal_text(raw_score)
        ),
        "upstream_diagnostics_id": upstream_id,
        "upstream_payload_hash": upstream_hash,
        "upstream_builder_git_commit": upstream_commit,
        "upstream_diagnostics_version": upstream_version,
        "upstream_numeric_policy_hash": upstream_policy_hash,
        **_ZeroAuthority().authority_payload(),
    }
    observation = Form4StockSignalNormalizationObservation(
        synthetic_source_id=synthetic_source_id,
        issuer_cik=stock_key[0],
        security_id=stock_key[1],
        share_class_id=stock_key[2],
        disposition=disposition,
        raw_stock_score_diagnostic=raw_score,
        upstream_diagnostics_id=upstream_id,
        upstream_payload_hash=upstream_hash,
        upstream_builder_git_commit=upstream_commit,
        upstream_diagnostics_version=upstream_version,
        upstream_numeric_policy_hash=upstream_policy_hash,
        observation_id=hash_payload(payload),
        _verified_factory_token=_OBSERVATION_FACTORY_TOKEN,
    )
    _register_observation(observation)
    return observation


@dataclass(frozen=True)
class _NormalizationComputation:
    outcome: Form4StockSignalNormalizationOutcome
    winsorized_values: tuple[Decimal | None, ...]
    normalized_values: tuple[Decimal | None, ...]
    lower_cutoff: Decimal | None
    upper_cutoff: Decimal | None
    mean: Decimal | None
    population_variance: Decimal | None
    standard_deviation: Decimal | None
    distinct_post_winsor_value_count: int


def _context_value(context: Context, value: Decimal, *, label: str) -> Decimal:
    try:
        projected = context.create_decimal(value)
    except DecimalException as exc:
        raise Form4StockSignalNormalizationDiagnosticsError(
            f"REFUSED: {label} cannot be represented under the frozen context"
        ) from exc
    if not projected.is_finite() or (value != 0 and projected == 0):
        raise Form4StockSignalNormalizationDiagnosticsError(
            f"REFUSED: {label} cannot be represented under the frozen context"
        )
    return projected


def _context_sum(context: Context, values: tuple[Decimal, ...]) -> Decimal:
    result = Decimal("0")
    for value in values:
        result = context.add(result, value)
    return result


def _context_mean(
    context: Context,
    ordered_values: tuple[Decimal, ...],
) -> Decimal:
    """Compute a stable 50-digit mean by summing offsets from the minimum."""

    anchor = ordered_values[0]
    offsets = tuple(context.subtract(value, anchor) for value in ordered_values)
    mean = context.add(
        anchor,
        context.divide(_context_sum(context, offsets), Decimal(len(offsets))),
    )
    return max(anchor, min(ordered_values[-1], mean))


def _type7_quantile(
    context: Context,
    ordered_values: tuple[Decimal, ...],
    probability: Decimal,
) -> Decimal:
    count = len(ordered_values)
    position = context.multiply(Decimal(count - 1), probability)
    lower_index = int(position)
    fraction = context.subtract(position, Decimal(lower_index))
    lower = ordered_values[lower_index]
    upper = ordered_values[min(lower_index + 1, count - 1)]
    return context.add(
        lower,
        context.multiply(context.subtract(upper, lower), fraction),
    )


def _compute_normalization(
    values: tuple[Decimal, ...],
) -> _NormalizationComputation:
    """Run the frozen pure-Decimal kernel over usable values in row order."""

    _require_frozen_policy()
    if type(values) is not tuple:
        raise Form4StockSignalNormalizationDiagnosticsError(
            "REFUSED: normalization values must be an exact tuple"
        )
    if (
        type(MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_ROWS) is not int
        or MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_ROWS < 1
        or len(values) > MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_ROWS
    ):
        raise Form4StockSignalNormalizationDiagnosticsError(
            "REFUSED: normalization values exceed the row-count bound"
        )
    checked = tuple(
        _decimal(value, label="normalization input", allow_zero=True)
        for value in values
    )
    if len(checked) < FORM4_STOCK_SIGNAL_NORMALIZATION_MINIMUM_USABLE_NAMES:
        empty = (None,) * len(checked)
        return _NormalizationComputation(
            outcome=(
                Form4StockSignalNormalizationOutcome.UNAVAILABLE_INSUFFICIENT_USABLE_COHORT
            ),
            winsorized_values=empty,
            normalized_values=empty,
            lower_cutoff=None,
            upper_cutoff=None,
            mean=None,
            population_variance=None,
            standard_deviation=None,
            distinct_post_winsor_value_count=0,
        )

    context = _new_decimal_context()
    projected = tuple(
        _context_value(context, value, label="normalization input")
        for value in checked
    )
    ordered = tuple(sorted(projected))
    lower = _type7_quantile(
        context,
        ordered,
        FORM4_STOCK_SIGNAL_NORMALIZATION_LOWER_QUANTILE,
    )
    upper = _type7_quantile(
        context,
        ordered,
        FORM4_STOCK_SIGNAL_NORMALIZATION_UPPER_QUANTILE,
    )
    winsorized = tuple(
        lower if value < lower else upper if value > upper else value
        for value in projected
    )
    ordered_winsorized = tuple(sorted(winsorized))
    distinct_count = len(set(ordered_winsorized))
    count = Decimal(len(ordered_winsorized))
    mean = _context_mean(context, ordered_winsorized)
    squared_deviations = tuple(
        context.multiply(
            context.subtract(value, mean),
            context.subtract(value, mean),
        )
        for value in ordered_winsorized
    )
    variance = context.divide(
        _context_sum(context, squared_deviations),
        count,
    )
    standard_deviation = context.sqrt(variance)
    if (
        distinct_count
        < FORM4_STOCK_SIGNAL_NORMALIZATION_MINIMUM_DISTINCT_VALUES
        or variance == 0
        or standard_deviation == 0
    ):
        return _NormalizationComputation(
            outcome=Form4StockSignalNormalizationOutcome.UNAVAILABLE_ZERO_DISPERSION,
            winsorized_values=winsorized,
            normalized_values=(None,) * len(winsorized),
            lower_cutoff=lower,
            upper_cutoff=upper,
            mean=mean,
            population_variance=variance,
            standard_deviation=standard_deviation,
            distinct_post_winsor_value_count=distinct_count,
        )
    normalized = tuple(
        context.divide(context.subtract(value, mean), standard_deviation)
        for value in winsorized
    )
    return _NormalizationComputation(
        outcome=Form4StockSignalNormalizationOutcome.AVAILABLE,
        winsorized_values=winsorized,
        normalized_values=normalized,
        lower_cutoff=lower,
        upper_cutoff=upper,
        mean=mean,
        population_variance=variance,
        standard_deviation=standard_deviation,
        distinct_post_winsor_value_count=distinct_count,
    )


@dataclass(frozen=True)
class Form4StockSignalNormalizedDiagnosticRow(_ZeroAuthority):
    """One retained nested row; its parent identity supplies cohort provenance.

    A row is not a standalone scored artifact.  The parent result binds its
    policy, evaluation session, complete row inventory, and cohort statistics;
    this object only binds the per-stock projection inside that atomic result.
    """

    observation_id: str
    issuer_cik: str
    security_id: str
    share_class_id: str
    disposition: Form4StockSignalNormalizationDisposition
    included_in_normalization: bool
    raw_stock_score_diagnostic: Decimal | None
    winsorized_stock_score_diagnostic: Decimal | None
    normalized_stock_score_diagnostic: Decimal | None
    stock_score: None
    rank: None
    seed_selected: None
    row_id: str
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _ROW_FACTORY_TOKEN:
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: normalized diagnostic row must be factory-created"
            )
        _sha256(self.observation_id, label="observation ID")
        _stock_key(self.issuer_cik, self.security_id, self.share_class_id)
        if type(self.disposition) is not Form4StockSignalNormalizationDisposition:
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: normalized row disposition must be an exact enum"
            )
        expected_included = self.disposition in (
            Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL,
            Form4StockSignalNormalizationDisposition.INCLUDE_STRUCTURAL_ZERO,
        )
        if (
            self.disposition
            is Form4StockSignalNormalizationDisposition.REFUSE_ELIGIBLE_MISSING_SCORE
        ):
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: eligible-missing disposition cannot become an output row"
            )
        if type(self.included_in_normalization) is not bool or (
            self.included_in_normalization is not expected_included
        ):
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: normalized row inclusion is inconsistent"
            )
        if expected_included:
            raw_value = _decimal(
                self.raw_stock_score_diagnostic,
                label="normalized row raw diagnostic",
                allow_zero=True,
            )
            if (
                self.disposition
                is Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL
                and raw_value <= 0
            ):
                raise Form4StockSignalNormalizationDiagnosticsError(
                    "REFUSED: signal output row requires a positive raw diagnostic"
                )
            if (
                self.disposition
                is Form4StockSignalNormalizationDisposition.INCLUDE_STRUCTURAL_ZERO
                and raw_value != 0
            ):
                raise Form4StockSignalNormalizationDiagnosticsError(
                    "REFUSED: structural-zero output row requires exact zero"
                )
            if self.winsorized_stock_score_diagnostic is not None:
                _derived_decimal(
                    self.winsorized_stock_score_diagnostic,
                    label="winsorized diagnostic",
                    allow_zero=True,
                )
            if self.normalized_stock_score_diagnostic is not None:
                if self.winsorized_stock_score_diagnostic is None:
                    raise Form4StockSignalNormalizationDiagnosticsError(
                        "REFUSED: normalized z-score requires a winsorized diagnostic"
                    )
                if type(self.normalized_stock_score_diagnostic) is not Decimal:
                    raise Form4StockSignalNormalizationDiagnosticsError(
                        "REFUSED: normalized z-score must be an exact finite Decimal"
                    )
                _derived_decimal(
                    self.normalized_stock_score_diagnostic.copy_abs(),
                    label="normalized z-score magnitude",
                    allow_zero=True,
                )
        elif any(
            value is not None
            for value in (
                self.raw_stock_score_diagnostic,
                self.winsorized_stock_score_diagnostic,
                self.normalized_stock_score_diagnostic,
            )
        ):
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: excluded normalized row cannot carry numeric diagnostics"
            )
        if (
            self.stock_score is not None
            or self.rank is not None
            or self.seed_selected is not None
        ):
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: canonical score, rank, and seed remain unavailable"
            )
        _sha256(self.row_id, label="normalized diagnostic row ID")
        if self.row_id != hash_payload(self.lineage_payload()):
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: normalized diagnostic row ID is inconsistent"
            )
        _require_zero_authority(self)

    @property
    def stock_key(self) -> tuple[str, str, str]:
        return (self.issuer_cik, self.security_id, self.share_class_id)

    def lineage_payload(self) -> dict[str, object]:
        return {
            "observation_id": self.observation_id,
            "issuer_cik": self.issuer_cik,
            "security_id": self.security_id,
            "share_class_id": self.share_class_id,
            "disposition": self.disposition.value,
            "included_in_normalization": self.included_in_normalization,
            "raw_stock_score_diagnostic": (
                None
                if self.raw_stock_score_diagnostic is None
                else decimal_text(self.raw_stock_score_diagnostic)
            ),
            "winsorized_stock_score_diagnostic": (
                None
                if self.winsorized_stock_score_diagnostic is None
                else decimal_text(self.winsorized_stock_score_diagnostic)
            ),
            "normalized_stock_score_diagnostic": (
                None
                if self.normalized_stock_score_diagnostic is None
                else decimal_text(self.normalized_stock_score_diagnostic)
            ),
            "stock_score": None,
            "rank": None,
            "seed_selected": None,
            **self.authority_payload(),
        }

    def to_payload(self) -> dict[str, object]:
        return {**self.lineage_payload(), "row_id": self.row_id}


def _build_rows(
    observations: tuple[Form4StockSignalNormalizationObservation, ...],
    computation: _NormalizationComputation,
) -> tuple[Form4StockSignalNormalizedDiagnosticRow, ...]:
    rows: list[Form4StockSignalNormalizedDiagnosticRow] = []
    usable_index = 0
    for observation in observations:
        included = observation.disposition in (
            Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL,
            Form4StockSignalNormalizationDisposition.INCLUDE_STRUCTURAL_ZERO,
        )
        winsorized: Decimal | None = None
        normalized: Decimal | None = None
        if included:
            winsorized = computation.winsorized_values[usable_index]
            normalized = computation.normalized_values[usable_index]
            usable_index += 1
        payload = {
            "observation_id": observation.observation_id,
            "issuer_cik": observation.issuer_cik,
            "security_id": observation.security_id,
            "share_class_id": observation.share_class_id,
            "disposition": observation.disposition.value,
            "included_in_normalization": included,
            "raw_stock_score_diagnostic": (
                None
                if observation.raw_stock_score_diagnostic is None
                else decimal_text(observation.raw_stock_score_diagnostic)
            ),
            "winsorized_stock_score_diagnostic": (
                None if winsorized is None else decimal_text(winsorized)
            ),
            "normalized_stock_score_diagnostic": (
                None if normalized is None else decimal_text(normalized)
            ),
            "stock_score": None,
            "rank": None,
            "seed_selected": None,
            **_ZeroAuthority().authority_payload(),
        }
        rows.append(
            Form4StockSignalNormalizedDiagnosticRow(
                observation_id=observation.observation_id,
                issuer_cik=observation.issuer_cik,
                security_id=observation.security_id,
                share_class_id=observation.share_class_id,
                disposition=observation.disposition,
                included_in_normalization=included,
                raw_stock_score_diagnostic=observation.raw_stock_score_diagnostic,
                winsorized_stock_score_diagnostic=winsorized,
                normalized_stock_score_diagnostic=normalized,
                stock_score=None,
                rank=None,
                seed_selected=None,
                row_id=hash_payload(payload),
                _verified_factory_token=_ROW_FACTORY_TOKEN,
            )
        )
    if usable_index != len(computation.winsorized_values):
        raise Form4StockSignalNormalizationDiagnosticsError(
            "REFUSED: normalization computation is not aligned to usable rows"
        )
    return tuple(rows)


def _optional_decimal_payload(value: Decimal | None) -> str | None:
    return None if value is None else decimal_text(value)


@dataclass(frozen=True)
class Form4StockSignalNormalizationIdentity(_ZeroAuthority):
    """Hash-bound identity for one complete synthetic IB-3B cohort."""

    diagnostics_version: str
    policy_hash: str
    builder_git_commit: str
    evaluation_session: str
    observation_count: int
    usable_count: int
    signal_count: int
    structural_zero_count: int
    excluded_ineligible_count: int
    excluded_missing_count: int
    observation_inventory_hash: str
    normalized_row_inventory_hash: str
    outcome: Form4StockSignalNormalizationOutcome
    lower_cutoff: Decimal | None
    upper_cutoff: Decimal | None
    mean: Decimal | None
    population_variance: Decimal | None
    standard_deviation: Decimal | None
    distinct_post_winsor_value_count: int
    normalization_id: str
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _IDENTITY_FACTORY_TOKEN:
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: normalization identity must be factory-created"
            )
        _require_frozen_policy()
        if (
            type(self.diagnostics_version) is not str
            or self.diagnostics_version
            != FORM4_STOCK_SIGNAL_NORMALIZATION_DIAGNOSTICS_VERSION
        ):
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: normalization diagnostics version is inconsistent"
            )
        _sha256(self.policy_hash, label="normalization policy hash")
        if self.policy_hash != FORM4_STOCK_SIGNAL_NORMALIZATION_POLICY_HASH:
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: normalization policy hash is inconsistent"
            )
        _builder_commit(self.builder_git_commit)
        _text(self.evaluation_session, label="evaluation session")
        counts = (
            self.observation_count,
            self.usable_count,
            self.signal_count,
            self.structural_zero_count,
            self.excluded_ineligible_count,
            self.excluded_missing_count,
            self.distinct_post_winsor_value_count,
        )
        if any(type(value) is not int or value < 0 for value in counts):
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: normalization identity counts must be nonnegative integers"
            )
        if (
            self.observation_count < 1
            or self.observation_count > MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_ROWS
            or self.usable_count > self.observation_count
            or self.usable_count != self.signal_count + self.structural_zero_count
            or self.observation_count
            != self.usable_count
            + self.excluded_ineligible_count
            + self.excluded_missing_count
            or self.distinct_post_winsor_value_count > self.usable_count
            or self.distinct_post_winsor_value_count
            > self.signal_count + int(self.structural_zero_count > 0)
        ):
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: normalization identity counts are inconsistent"
            )
        _sha256(self.observation_inventory_hash, label="observation inventory hash")
        _sha256(
            self.normalized_row_inventory_hash,
            label="normalized-row inventory hash",
        )
        if type(self.outcome) is not Form4StockSignalNormalizationOutcome:
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: normalization outcome must be an exact enum"
            )
        summary = (
            self.lower_cutoff,
            self.upper_cutoff,
            self.mean,
            self.population_variance,
            self.standard_deviation,
        )
        if self.outcome is Form4StockSignalNormalizationOutcome.UNAVAILABLE_INSUFFICIENT_USABLE_COHORT:
            if (
                self.usable_count
                >= FORM4_STOCK_SIGNAL_NORMALIZATION_MINIMUM_USABLE_NAMES
                or any(value is not None for value in summary)
                or self.distinct_post_winsor_value_count != 0
            ):
                raise Form4StockSignalNormalizationDiagnosticsError(
                    "REFUSED: insufficient cohort cannot claim normalization statistics"
                )
        else:
            if (
                self.usable_count
                < FORM4_STOCK_SIGNAL_NORMALIZATION_MINIMUM_USABLE_NAMES
                or any(value is None for value in summary)
            ):
                raise Form4StockSignalNormalizationDiagnosticsError(
                    "REFUSED: evaluated cohort requires complete statistics"
                )
            for label, value in zip(
                ("lower cutoff", "upper cutoff", "mean", "population variance", "standard deviation"),
                summary,
                strict=True,
            ):
                _derived_decimal(value, label=label, allow_zero=True)
            if self.lower_cutoff > self.upper_cutoff:
                raise Form4StockSignalNormalizationDiagnosticsError(
                    "REFUSED: normalization cutoffs are inverted"
                )
            if not self.lower_cutoff <= self.mean <= self.upper_cutoff:
                raise Form4StockSignalNormalizationDiagnosticsError(
                    "REFUSED: normalization mean lies outside its winsor cutoffs"
                )
            if self.standard_deviation != _new_decimal_context().sqrt(
                self.population_variance
            ):
                raise Form4StockSignalNormalizationDiagnosticsError(
                    "REFUSED: standard deviation is inconsistent with population variance"
                )
            if self.outcome is Form4StockSignalNormalizationOutcome.AVAILABLE:
                if (
                    self.usable_count
                    < FORM4_STOCK_SIGNAL_NORMALIZATION_MINIMUM_USABLE_NAMES
                    or self.distinct_post_winsor_value_count
                    < FORM4_STOCK_SIGNAL_NORMALIZATION_MINIMUM_DISTINCT_VALUES
                    or self.lower_cutoff >= self.upper_cutoff
                    or self.population_variance <= 0
                    or self.standard_deviation <= 0
                ):
                    raise Form4StockSignalNormalizationDiagnosticsError(
                        "REFUSED: available normalization identity violates availability gates"
                    )
            elif self.outcome is Form4StockSignalNormalizationOutcome.UNAVAILABLE_ZERO_DISPERSION:
                if (
                    self.distinct_post_winsor_value_count != 1
                    or self.population_variance != 0
                    or self.standard_deviation != 0
                    or self.lower_cutoff != self.upper_cutoff
                    or self.mean != self.lower_cutoff
                ):
                    raise Form4StockSignalNormalizationDiagnosticsError(
                        "REFUSED: zero-dispersion outcome is inconsistent"
                    )
            if self.signal_count > 0:
                lower_zero_is_forced = _type7_quantile_is_forced_zero(
                    structural_zero_count=self.structural_zero_count,
                    usable_count=self.usable_count,
                    percentile_numerator=1,
                )
                upper_zero_is_forced = _type7_quantile_is_forced_zero(
                    structural_zero_count=self.structural_zero_count,
                    usable_count=self.usable_count,
                    percentile_numerator=99,
                )
                if (self.lower_cutoff == 0) is not lower_zero_is_forced:
                    raise Form4StockSignalNormalizationDiagnosticsError(
                        "REFUSED: lower cutoff is inconsistent with Type-7 zero mass"
                    )
                if (self.upper_cutoff == 0) is not upper_zero_is_forced:
                    raise Form4StockSignalNormalizationDiagnosticsError(
                        "REFUSED: upper cutoff is inconsistent with Type-7 zero mass"
                    )
                if self.mean > _maximum_context_mean_from_counts(
                    signal_count=self.signal_count,
                    structural_zero_count=self.structural_zero_count,
                    lower=self.lower_cutoff,
                    upper=self.upper_cutoff,
                ):
                    raise Form4StockSignalNormalizationDiagnosticsError(
                        "REFUSED: normalization mean exceeds the category-count bound"
                    )
                if (
                    self.outcome
                    is Form4StockSignalNormalizationOutcome.UNAVAILABLE_ZERO_DISPERSION
                    and self.structural_zero_count > 0
                    and self.upper_cutoff > 0
                    and self.structural_zero_count
                    > _type7_quantile_lower_index(
                        usable_count=self.usable_count,
                        percentile_numerator=1,
                    )
                ):
                    raise Form4StockSignalNormalizationDiagnosticsError(
                        "REFUSED: positive zero dispersion is inconsistent with Type-7 zero mass"
                    )
            if self.signal_count == 0 and (
                self.outcome
                is not Form4StockSignalNormalizationOutcome.UNAVAILABLE_ZERO_DISPERSION
                or self.lower_cutoff != 0
                or self.upper_cutoff != 0
                or self.mean != 0
                or self.population_variance != 0
                or self.standard_deviation != 0
                or self.distinct_post_winsor_value_count != 1
            ):
                raise Form4StockSignalNormalizationDiagnosticsError(
                    "REFUSED: all-structural-zero cohort has impossible statistics"
                )
            if self.signal_count > 0 and self.upper_cutoff > 0 and self.mean <= 0:
                raise Form4StockSignalNormalizationDiagnosticsError(
                    "REFUSED: cohort with a positive upper cutoff must have a positive mean"
                )
            if self.population_variance > _coarse_population_variance_cap(
                self.lower_cutoff,
                self.upper_cutoff,
            ):
                raise Form4StockSignalNormalizationDiagnosticsError(
                    "REFUSED: population variance exceeds the coarse range-squared cap"
                )
        _text(self.normalization_id, label="normalization ID")
        expected_id = (
            "form4-stock-signal-normalization-diagnostics-"
            f"{hash_payload(self.lineage_payload())[:16]}"
        )
        if self.normalization_id != expected_id:
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: normalization ID is inconsistent"
            )
        _require_zero_authority(self)

    def lineage_payload(self) -> dict[str, object]:
        return {
            "diagnostics_version": self.diagnostics_version,
            "policy_hash": self.policy_hash,
            "builder_git_commit": self.builder_git_commit,
            "evaluation_session": self.evaluation_session,
            "observation_count": self.observation_count,
            "usable_count": self.usable_count,
            "signal_count": self.signal_count,
            "structural_zero_count": self.structural_zero_count,
            "excluded_ineligible_count": self.excluded_ineligible_count,
            "excluded_missing_count": self.excluded_missing_count,
            "observation_inventory_hash": self.observation_inventory_hash,
            "normalized_row_inventory_hash": self.normalized_row_inventory_hash,
            "outcome": self.outcome.value,
            "lower_cutoff": _optional_decimal_payload(self.lower_cutoff),
            "upper_cutoff": _optional_decimal_payload(self.upper_cutoff),
            "mean": _optional_decimal_payload(self.mean),
            "population_variance": _optional_decimal_payload(
                self.population_variance
            ),
            "standard_deviation": _optional_decimal_payload(
                self.standard_deviation
            ),
            "distinct_post_winsor_value_count": (
                self.distinct_post_winsor_value_count
            ),
            **self.authority_payload(),
        }

    def to_payload(self) -> dict[str, object]:
        return {**self.lineage_payload(), "normalization_id": self.normalization_id}


def _build_identity(
    *,
    observations: tuple[Form4StockSignalNormalizationObservation, ...],
    rows: tuple[Form4StockSignalNormalizedDiagnosticRow, ...],
    computation: _NormalizationComputation,
    evaluation_session: str,
    builder_git_commit: str,
) -> Form4StockSignalNormalizationIdentity:
    counts = {
        disposition: sum(
            observation.disposition is disposition for observation in observations
        )
        for disposition in Form4StockSignalNormalizationDisposition
    }
    if counts[
        Form4StockSignalNormalizationDisposition.REFUSE_ELIGIBLE_MISSING_SCORE
    ]:
        raise Form4StockSignalNormalizationDiagnosticsError(
            "REFUSED: eligible row is missing its synthetic score"
        )
    payload = {
        "diagnostics_version": FORM4_STOCK_SIGNAL_NORMALIZATION_DIAGNOSTICS_VERSION,
        "policy_hash": FORM4_STOCK_SIGNAL_NORMALIZATION_POLICY_HASH,
        "builder_git_commit": builder_git_commit,
        "evaluation_session": evaluation_session,
        "observation_count": len(observations),
        "usable_count": len(computation.winsorized_values),
        "signal_count": counts[
            Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL
        ],
        "structural_zero_count": counts[
            Form4StockSignalNormalizationDisposition.INCLUDE_STRUCTURAL_ZERO
        ],
        "excluded_ineligible_count": counts[
            Form4StockSignalNormalizationDisposition.EXCLUDE_INELIGIBLE
        ],
        "excluded_missing_count": counts[
            Form4StockSignalNormalizationDisposition.EXCLUDE_MISSING
        ],
        "observation_inventory_hash": hash_payload(
            [observation.to_payload() for observation in observations]
        ),
        "normalized_row_inventory_hash": hash_payload(
            [row.to_payload() for row in rows]
        ),
        "outcome": computation.outcome.value,
        "lower_cutoff": _optional_decimal_payload(computation.lower_cutoff),
        "upper_cutoff": _optional_decimal_payload(computation.upper_cutoff),
        "mean": _optional_decimal_payload(computation.mean),
        "population_variance": _optional_decimal_payload(
            computation.population_variance
        ),
        "standard_deviation": _optional_decimal_payload(
            computation.standard_deviation
        ),
        "distinct_post_winsor_value_count": (
            computation.distinct_post_winsor_value_count
        ),
        **_ZeroAuthority().authority_payload(),
    }
    return Form4StockSignalNormalizationIdentity(
        diagnostics_version=FORM4_STOCK_SIGNAL_NORMALIZATION_DIAGNOSTICS_VERSION,
        policy_hash=FORM4_STOCK_SIGNAL_NORMALIZATION_POLICY_HASH,
        builder_git_commit=builder_git_commit,
        evaluation_session=evaluation_session,
        observation_count=len(observations),
        usable_count=len(computation.winsorized_values),
        signal_count=counts[
            Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL
        ],
        structural_zero_count=counts[
            Form4StockSignalNormalizationDisposition.INCLUDE_STRUCTURAL_ZERO
        ],
        excluded_ineligible_count=counts[
            Form4StockSignalNormalizationDisposition.EXCLUDE_INELIGIBLE
        ],
        excluded_missing_count=counts[
            Form4StockSignalNormalizationDisposition.EXCLUDE_MISSING
        ],
        observation_inventory_hash=payload["observation_inventory_hash"],
        normalized_row_inventory_hash=payload["normalized_row_inventory_hash"],
        outcome=computation.outcome,
        lower_cutoff=computation.lower_cutoff,
        upper_cutoff=computation.upper_cutoff,
        mean=computation.mean,
        population_variance=computation.population_variance,
        standard_deviation=computation.standard_deviation,
        distinct_post_winsor_value_count=(
            computation.distinct_post_winsor_value_count
        ),
        normalization_id=(
            "form4-stock-signal-normalization-diagnostics-"
            f"{hash_payload(payload)[:16]}"
        ),
        _verified_factory_token=_IDENTITY_FACTORY_TOKEN,
    )


@dataclass(frozen=True)
class Form4StockSignalNormalizationDiagnostics(_ZeroAuthority):
    """Replayable, exhaustive synthetic evidence for one IB-3B cohort."""

    identity: Form4StockSignalNormalizationIdentity
    observations: tuple[Form4StockSignalNormalizationObservation, ...]
    rows: tuple[Form4StockSignalNormalizedDiagnosticRow, ...]
    outcome: Form4StockSignalNormalizationOutcome
    lower_cutoff: Decimal | None
    upper_cutoff: Decimal | None
    mean: Decimal | None
    population_variance: Decimal | None
    standard_deviation: Decimal | None
    distinct_post_winsor_value_count: int
    stock_score: None
    ranking: None
    seed_selection: None
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _RESULT_FACTORY_TOKEN:
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: normalization diagnostics must be factory-created"
            )
        if type(self.identity) is not Form4StockSignalNormalizationIdentity:
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: normalization diagnostics require an exact identity"
            )
        Form4StockSignalNormalizationIdentity.__post_init__(
            self.identity,
            _IDENTITY_FACTORY_TOKEN,
        )
        if (
            type(self.observations) is not tuple
            or not self.observations
            or len(self.observations) > MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_ROWS
            or type(self.rows) is not tuple
            or len(self.rows) != len(self.observations)
        ):
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: normalization diagnostics require aligned nonempty tuples"
            )
        stock_keys: list[tuple[str, str, str]] = []
        source_ids: list[str] = []
        observation_ids: list[str] = []
        for observation in self.observations:
            _require_factory_observation(observation)
            stock_keys.append(observation.stock_key)
            source_ids.append(observation.synthetic_source_id)
            observation_ids.append(observation.observation_id)
        if (
            stock_keys != sorted(stock_keys)
            or len(set(stock_keys)) != len(stock_keys)
            or len(set(source_ids)) != len(source_ids)
            or len(set(observation_ids)) != len(observation_ids)
        ):
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: observations require unique identities in canonical stock order"
            )
        if any(
            observation.disposition
            is Form4StockSignalNormalizationDisposition.REFUSE_ELIGIBLE_MISSING_SCORE
            for observation in self.observations
        ):
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: eligible row is missing its synthetic score"
            )
        for row in self.rows:
            if type(row) is not Form4StockSignalNormalizedDiagnosticRow:
                raise Form4StockSignalNormalizationDiagnosticsError(
                    "REFUSED: normalized rows contain an unexpected type"
                )
            Form4StockSignalNormalizedDiagnosticRow.__post_init__(
                row,
                _ROW_FACTORY_TOKEN,
            )
        usable_values = tuple(
            observation.raw_stock_score_diagnostic
            for observation in self.observations
            if observation.disposition
            in (
                Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL,
                Form4StockSignalNormalizationDisposition.INCLUDE_STRUCTURAL_ZERO,
            )
        )
        if any(type(value) is not Decimal for value in usable_values):
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: eligible row is missing its synthetic score"
            )
        computation = _compute_normalization(usable_values)
        expected_rows = _build_rows(self.observations, computation)
        if self.rows != expected_rows:
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: normalized rows do not replay from observations"
            )
        expected_identity = _build_identity(
            observations=self.observations,
            rows=expected_rows,
            computation=computation,
            evaluation_session=self.identity.evaluation_session,
            builder_git_commit=self.identity.builder_git_commit,
        )
        if self.identity != expected_identity:
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: normalization identity does not replay"
            )
        result_summary = (
            self.outcome,
            self.lower_cutoff,
            self.upper_cutoff,
            self.mean,
            self.population_variance,
            self.standard_deviation,
            self.distinct_post_winsor_value_count,
        )
        expected_summary = (
            computation.outcome,
            computation.lower_cutoff,
            computation.upper_cutoff,
            computation.mean,
            computation.population_variance,
            computation.standard_deviation,
            computation.distinct_post_winsor_value_count,
        )
        if result_summary != expected_summary:
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: normalization result summary is inconsistent"
            )
        if (
            self.stock_score is not None
            or self.ranking is not None
            or self.seed_selection is not None
        ):
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: canonical score, ranking, and seed selection remain unavailable"
            )
        _require_zero_authority(self)

    def to_payload(self) -> dict[str, object]:
        return {
            "identity": self.identity.to_payload(),
            "observations": [
                observation.to_payload() for observation in self.observations
            ],
            "rows": [row.to_payload() for row in self.rows],
            "outcome": self.outcome.value,
            "lower_cutoff": _optional_decimal_payload(self.lower_cutoff),
            "upper_cutoff": _optional_decimal_payload(self.upper_cutoff),
            "mean": _optional_decimal_payload(self.mean),
            "population_variance": _optional_decimal_payload(
                self.population_variance
            ),
            "standard_deviation": _optional_decimal_payload(
                self.standard_deviation
            ),
            "distinct_post_winsor_value_count": (
                self.distinct_post_winsor_value_count
            ),
            "stock_score": None,
            "ranking": None,
            "seed_selection": None,
            **self.authority_payload(),
        }


def build_form4_stock_signal_normalization_diagnostics(
    observations: tuple[Form4StockSignalNormalizationObservation, ...],
    *,
    evaluation_session: str,
    builder_git_commit: str,
) -> Form4StockSignalNormalizationDiagnostics:
    """Evaluate one complete declared synthetic cohort under frozen IB-3B policy."""

    if type(observations) is not tuple:
        raise Form4StockSignalNormalizationDiagnosticsError(
            "REFUSED: normalization observations must be supplied as an exact tuple"
        )
    if (
        type(MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_ROWS) is not int
        or MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_ROWS < 1
        or len(observations) > MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_ROWS
    ):
        raise Form4StockSignalNormalizationDiagnosticsError(
            "REFUSED: normalization cohort exceeds the row-count bound"
        )
    if not observations:
        raise Form4StockSignalNormalizationDiagnosticsError(
            "REFUSED: at least one explicit cohort observation is required"
        )
    evaluation_session = _text(evaluation_session, label="evaluation session")
    builder_git_commit = _builder_commit(builder_git_commit)
    _require_frozen_policy()

    fingerprints_by_identity: dict[int, str] = {}
    captured: list[Form4StockSignalNormalizationObservation] = []
    for observation in observations:
        snapshot, fingerprint = _snapshot_observation(observation)
        fingerprints_by_identity[id(observation)] = fingerprint
        captured.append(snapshot)
    ordered = tuple(sorted(captured, key=lambda value: value.stock_key))
    stock_keys = tuple(observation.stock_key for observation in ordered)
    source_ids = tuple(observation.synthetic_source_id for observation in ordered)
    observation_ids = tuple(observation.observation_id for observation in ordered)
    if (
        len(set(stock_keys)) != len(stock_keys)
        or len(set(source_ids)) != len(source_ids)
        or len(set(observation_ids)) != len(observation_ids)
    ):
        raise Form4StockSignalNormalizationDiagnosticsError(
            "REFUSED: cohort stock, source, and observation identities must be unique"
        )
    if any(
        observation.disposition
        is Form4StockSignalNormalizationDisposition.REFUSE_ELIGIBLE_MISSING_SCORE
        for observation in ordered
    ):
        raise Form4StockSignalNormalizationDiagnosticsError(
            "REFUSED: eligible row is missing its synthetic score"
        )
    usable_values = tuple(
        observation.raw_stock_score_diagnostic
        for observation in ordered
        if observation.disposition
        in (
            Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL,
            Form4StockSignalNormalizationDisposition.INCLUDE_STRUCTURAL_ZERO,
        )
    )
    if any(type(value) is not Decimal for value in usable_values):
        raise Form4StockSignalNormalizationDiagnosticsError(
            "REFUSED: eligible row is missing its synthetic score"
        )
    computation = _compute_normalization(usable_values)
    rows = _build_rows(ordered, computation)
    identity = _build_identity(
        observations=ordered,
        rows=rows,
        computation=computation,
        evaluation_session=evaluation_session,
        builder_git_commit=builder_git_commit,
    )
    result = Form4StockSignalNormalizationDiagnostics(
        identity=identity,
        observations=ordered,
        rows=rows,
        outcome=computation.outcome,
        lower_cutoff=computation.lower_cutoff,
        upper_cutoff=computation.upper_cutoff,
        mean=computation.mean,
        population_variance=computation.population_variance,
        standard_deviation=computation.standard_deviation,
        distinct_post_winsor_value_count=(
            computation.distinct_post_winsor_value_count
        ),
        stock_score=None,
        ranking=None,
        seed_selection=None,
        _verified_factory_token=_RESULT_FACTORY_TOKEN,
    )
    for observation in observations:
        if (
            _require_factory_observation(observation)
            != fingerprints_by_identity[id(observation)]
        ):
            raise Form4StockSignalNormalizationDiagnosticsError(
                "REFUSED: normalization observation changed during evaluation"
            )
    return result


__all__ = [
    "FORM4_STOCK_SIGNAL_NORMALIZATION_DECIMAL_PRECISION",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_DECIMAL_ROUNDING",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_DIAGNOSTICS_VERSION",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_FINAL_QUANTIZATION",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_LOWER_QUANTILE",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_MINIMUM_DISTINCT_VALUES",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_MINIMUM_USABLE_NAMES",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_POLICY_HASH",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_QUANTILE_METHOD",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_RANKING_POLICY",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_SEED_POLICY",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_UPPER_QUANTILE",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_VARIANCE_DENOMINATOR",
    "FORM4_STOCK_SIGNAL_NORMALIZATION_ZERO_DISPERSION_POLICY",
    "MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_ROWS",
    "MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_TEXT_CHARACTERS",
    "Form4StockSignalNormalizationDiagnostics",
    "Form4StockSignalNormalizationDiagnosticsError",
    "Form4StockSignalNormalizationDisposition",
    "Form4StockSignalNormalizationIdentity",
    "Form4StockSignalNormalizationObservation",
    "Form4StockSignalNormalizationOutcome",
    "Form4StockSignalNormalizedDiagnosticRow",
    "build_form4_stock_signal_normalization_diagnostics",
    "build_form4_stock_signal_normalization_observation",
]
