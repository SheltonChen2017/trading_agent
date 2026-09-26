"""Synthetic-only, zero-authority IB-3C ranking and seed diagnostics.

The module consumes one exact, replayable, AVAILABLE IB-3B normalization
artifact.  It orders every usable eligible name by the exact winsorized
diagnostic value, uses ``ceil(N / 10)`` as the untied top-decile count,
includes every exact cutoff tie, and permits only positive INCLUDE_SIGNAL
rows to become diagnostic seed candidates.  Fewer than two candidates makes
the whole diagnostic selection unavailable.

This is fixture evidence, not a canonical score, rank, or seed signal.  It
does not grant data, outcome, ETF, QC, broker, deployment, or trading
authority, and it does not change IB-3B's deferred canonical fields.  The
blueprint's separate cluster-gated buyer comparison remains deferred and is
not implemented or authorized here.
"""
from __future__ import annotations

import re
from dataclasses import InitVar, dataclass, fields as dataclass_fields, is_dataclass
from decimal import Decimal
from enum import Enum

from data.financial_primitives import decimal_text
from data.hashing import hash_payload
from research.insider_buying.form4_stock_signal_normalization_diagnostics import (
    FORM4_STOCK_SIGNAL_NORMALIZATION_DIAGNOSTICS_VERSION,
    FORM4_STOCK_SIGNAL_NORMALIZATION_POLICY_HASH,
    MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_ROWS,
    Form4StockSignalNormalizationDiagnostics,
    Form4StockSignalNormalizationDiagnosticsError,
    Form4StockSignalNormalizationDisposition,
    Form4StockSignalNormalizationOutcome,
    build_form4_stock_signal_normalization_diagnostics,
)


FORM4_STOCK_SIGNAL_SEED_DIAGNOSTICS_VERSION = (
    "INSETF-IB3C-FORM4-STOCK-SIGNAL-SEED-DIAGNOSTICS-v1"
)
FORM4_STOCK_SIGNAL_SEED_RANKING_VALUE = (
    "exact-ib3b-winsorized-stock-score-diagnostic"
)
FORM4_STOCK_SIGNAL_SEED_RANKING_METHOD = (
    "descending-exact-value-kth-cutoff-no-ordinal-rank"
)
FORM4_STOCK_SIGNAL_SEED_DENOMINATOR_POLICY = (
    "all-usable-eligible-names-including-structural-zero"
)
FORM4_STOCK_SIGNAL_SEED_TOP_FRACTION_NUMERATOR = 1
FORM4_STOCK_SIGNAL_SEED_TOP_FRACTION_DENOMINATOR = 10
FORM4_STOCK_SIGNAL_SEED_COUNT_POLICY = "ceil(N/10)"
FORM4_STOCK_SIGNAL_SEED_TIE_POLICY = (
    "include-all-exact-cutoff-ties-never-split-by-stock-identity"
)
FORM4_STOCK_SIGNAL_SEED_ELIGIBILITY_POLICY = (
    "positive-include-signal-rows-only"
)
FORM4_STOCK_SIGNAL_SEED_CLUSTER_COMPARISON_POLICY = (
    "deferred-separate-not-implemented"
)
FORM4_STOCK_SIGNAL_SEED_MINIMUM_POSITIVE_SEEDS = 2
MAX_FORM4_STOCK_SIGNAL_SEED_ROWS = 10_000
MAX_FORM4_STOCK_SIGNAL_SEED_TEXT_CHARACTERS = 128

_MAX_SEED_DECIMAL_DIGITS = 50
_MAX_SEED_DECIMAL_ABS_EXPONENT = 2_048

_CIK_RE = re.compile(r"^[0-9]{10}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_NORMALIZATION_ID_RE = re.compile(
    r"^form4-stock-signal-normalization-diagnostics-[0-9a-f]{16}$"
)
_ROW_FACTORY_TOKEN = object()
_IDENTITY_FACTORY_TOKEN = object()
_RESULT_FACTORY_TOKEN = object()


class Form4StockSignalSeedDiagnosticsError(ValueError):
    """A bounded synthetic IB-3C diagnostic contract failed closed."""


class Form4StockSignalSeedOutcome(str, Enum):
    """Availability of the complete diagnostic seed selection."""

    AVAILABLE = "available"
    UNAVAILABLE_INSUFFICIENT_POSITIVE_SEEDS = (
        "unavailable_insufficient_positive_seeds"
    )


def _policy_payload() -> dict[str, object]:
    return {
        "diagnostics_version": FORM4_STOCK_SIGNAL_SEED_DIAGNOSTICS_VERSION,
        "ranking_value": FORM4_STOCK_SIGNAL_SEED_RANKING_VALUE,
        "ranking_method": FORM4_STOCK_SIGNAL_SEED_RANKING_METHOD,
        "denominator": FORM4_STOCK_SIGNAL_SEED_DENOMINATOR_POLICY,
        "top_fraction_numerator": (
            FORM4_STOCK_SIGNAL_SEED_TOP_FRACTION_NUMERATOR
        ),
        "top_fraction_denominator": (
            FORM4_STOCK_SIGNAL_SEED_TOP_FRACTION_DENOMINATOR
        ),
        "untied_count": FORM4_STOCK_SIGNAL_SEED_COUNT_POLICY,
        "cutoff_ties": FORM4_STOCK_SIGNAL_SEED_TIE_POLICY,
        "seed_eligibility": FORM4_STOCK_SIGNAL_SEED_ELIGIBILITY_POLICY,
        "cluster_gated_comparison": (
            FORM4_STOCK_SIGNAL_SEED_CLUSTER_COMPARISON_POLICY
        ),
        "minimum_positive_seeds": (
            FORM4_STOCK_SIGNAL_SEED_MINIMUM_POSITIVE_SEEDS
        ),
        "insufficient_positive_seeds": (
            "named-unavailable-no-diagnostic-selection"
        ),
        "canonical_stock_score": "unavailable",
        "canonical_rank": "unavailable",
        "canonical_seed_selection": "unavailable",
        "upstream_diagnostics_version": (
            FORM4_STOCK_SIGNAL_NORMALIZATION_DIAGNOSTICS_VERSION
        ),
        "upstream_policy_hash": (
            FORM4_STOCK_SIGNAL_NORMALIZATION_POLICY_HASH
        ),
        "upstream_outcome": Form4StockSignalNormalizationOutcome.AVAILABLE.value,
        "resource_bounds": {
            "rows": MAX_FORM4_STOCK_SIGNAL_SEED_ROWS,
            "text_characters": MAX_FORM4_STOCK_SIGNAL_SEED_TEXT_CHARACTERS,
            "decimal_digits": _MAX_SEED_DECIMAL_DIGITS,
            "decimal_abs_exponent": _MAX_SEED_DECIMAL_ABS_EXPONENT,
        },
    }


FORM4_STOCK_SIGNAL_SEED_POLICY_HASH = hash_payload(_policy_payload())


def _require_frozen_policy() -> None:
    if (
        FORM4_STOCK_SIGNAL_SEED_DIAGNOSTICS_VERSION
        != "INSETF-IB3C-FORM4-STOCK-SIGNAL-SEED-DIAGNOSTICS-v1"
        or FORM4_STOCK_SIGNAL_SEED_RANKING_VALUE
        != "exact-ib3b-winsorized-stock-score-diagnostic"
        or FORM4_STOCK_SIGNAL_SEED_RANKING_METHOD
        != "descending-exact-value-kth-cutoff-no-ordinal-rank"
        or FORM4_STOCK_SIGNAL_SEED_DENOMINATOR_POLICY
        != "all-usable-eligible-names-including-structural-zero"
        or FORM4_STOCK_SIGNAL_SEED_TOP_FRACTION_NUMERATOR != 1
        or FORM4_STOCK_SIGNAL_SEED_TOP_FRACTION_DENOMINATOR != 10
        or FORM4_STOCK_SIGNAL_SEED_COUNT_POLICY != "ceil(N/10)"
        or FORM4_STOCK_SIGNAL_SEED_TIE_POLICY
        != "include-all-exact-cutoff-ties-never-split-by-stock-identity"
        or FORM4_STOCK_SIGNAL_SEED_ELIGIBILITY_POLICY
        != "positive-include-signal-rows-only"
        or FORM4_STOCK_SIGNAL_SEED_CLUSTER_COMPARISON_POLICY
        != "deferred-separate-not-implemented"
        or FORM4_STOCK_SIGNAL_SEED_MINIMUM_POSITIVE_SEEDS != 2
        or MAX_FORM4_STOCK_SIGNAL_SEED_ROWS != 10_000
        or MAX_FORM4_STOCK_SIGNAL_SEED_TEXT_CHARACTERS != 128
        or _MAX_SEED_DECIMAL_DIGITS != 50
        or _MAX_SEED_DECIMAL_ABS_EXPONENT != 2_048
        or MAX_FORM4_STOCK_SIGNAL_NORMALIZATION_ROWS != 10_000
        or FORM4_STOCK_SIGNAL_NORMALIZATION_DIAGNOSTICS_VERSION
        != "INSETF-IB3B-FORM4-STOCK-SIGNAL-NORMALIZATION-DIAGNOSTICS-v1"
        or FORM4_STOCK_SIGNAL_NORMALIZATION_POLICY_HASH
        != (
            "6705744ca9df421f4f96f955a3a4e850"
            "570806ac5b1059ad79488f36d14ffd04"
        )
        or FORM4_STOCK_SIGNAL_SEED_POLICY_HASH
        != (
            "809a0072a1976463545674733305b8f4"
            "0b6e606da9e8da3b29c6ca6950f371f4"
        )
        or hash_payload(_policy_payload()) != FORM4_STOCK_SIGNAL_SEED_POLICY_HASH
    ):
        raise Form4StockSignalSeedDiagnosticsError(
            "REFUSED: frozen IB-3C seed policy is inconsistent"
        )


def _text(value: object, *, label: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or not value.isprintable()
        or len(value) > MAX_FORM4_STOCK_SIGNAL_SEED_TEXT_CHARACTERS
    ):
        raise Form4StockSignalSeedDiagnosticsError(
            f"REFUSED: {label} must be bounded nonempty printable text"
        )
    return value


def _sha256(value: object, *, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise Form4StockSignalSeedDiagnosticsError(
            f"REFUSED: {label} must be a lowercase SHA-256 digest"
        )
    return value


def _builder_commit(value: object) -> str:
    if type(value) is not str or _GIT_COMMIT_RE.fullmatch(value) is None:
        raise Form4StockSignalSeedDiagnosticsError(
            "REFUSED: builder Git commit must be a lowercase 40-hex identity"
        )
    return value


def _stock_key(
    issuer_cik: object,
    security_id: object,
    share_class_id: object,
) -> tuple[str, str, str]:
    if type(issuer_cik) is not str or _CIK_RE.fullmatch(issuer_cik) is None:
        raise Form4StockSignalSeedDiagnosticsError(
            "REFUSED: issuer CIK must be exactly ten digits"
        )
    return (
        issuer_cik,
        _text(security_id, label="security ID"),
        _text(share_class_id, label="share-class ID"),
    )


def _decimal(value: object, *, label: str, allow_zero: bool) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise Form4StockSignalSeedDiagnosticsError(
            f"REFUSED: {label} must be an exact finite Decimal"
        )
    decimal_tuple = value.as_tuple()
    if (
        len(decimal_tuple.digits) > _MAX_SEED_DECIMAL_DIGITS
        or abs(int(decimal_tuple.exponent)) > _MAX_SEED_DECIMAL_ABS_EXPONENT
    ):
        raise Form4StockSignalSeedDiagnosticsError(
            f"REFUSED: {label} exceeds the Decimal resource bound"
        )
    if value < 0 or (not allow_zero and value == 0):
        comparator = "nonnegative" if allow_zero else "positive"
        raise Form4StockSignalSeedDiagnosticsError(
            f"REFUSED: {label} must be {comparator}"
        )
    return value


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
        raise Form4StockSignalSeedDiagnosticsError(
            "REFUSED: IB-3C population must remain caller-declared"
        )
    if getattr(value, "canonical_population_verified") is not False:
        raise Form4StockSignalSeedDiagnosticsError(
            "REFUSED: IB-3C cannot verify a canonical population"
        )
    if getattr(value, "role_ids_are_caller_declared") is not True:
        raise Form4StockSignalSeedDiagnosticsError(
            "REFUSED: IB-3C role IDs remain caller-declared"
        )
    if any(
        type(getattr(value, name)) is not bool
        for name in _BOOLEAN_AUTHORITY_FIELDS
    ):
        raise Form4StockSignalSeedDiagnosticsError(
            "REFUSED: every IB-3C authority flag must be an exact boolean"
        )
    if any(getattr(value, name) is not False for name in _BOOLEAN_AUTHORITY_FIELDS):
        raise Form4StockSignalSeedDiagnosticsError(
            "REFUSED: IB-3C seed diagnostics cannot grant authority"
        )
    for name in ("authorized_outcome_looks", "consumed_outcome_looks"):
        count = getattr(value, name)
        if type(count) is not int or count != 0:
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: IB-3C diagnostics require exactly zero outcome looks"
            )


def _replay_available_parent(
    value: object,
) -> tuple[Form4StockSignalNormalizationDiagnostics, str]:
    if type(value) is not Form4StockSignalNormalizationDiagnostics:
        raise Form4StockSignalSeedDiagnosticsError(
            "REFUSED: IB-3C requires exact IB-3B normalization diagnostics"
        )
    try:
        if (
            type(value.observations) is not tuple
            or not value.observations
            or len(value.observations) > MAX_FORM4_STOCK_SIGNAL_SEED_ROWS
        ):
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: source IB-3B observation inventory is out of bounds"
            )
        replayed = build_form4_stock_signal_normalization_diagnostics(
            value.observations,
            evaluation_session=value.identity.evaluation_session,
            builder_git_commit=value.identity.builder_git_commit,
        )
        replayed_hash = hash_payload(
            Form4StockSignalNormalizationDiagnostics.to_payload(replayed)
        )
    except (
        AttributeError,
        TypeError,
        Form4StockSignalNormalizationDiagnosticsError,
    ) as exc:
        raise Form4StockSignalSeedDiagnosticsError(
            "REFUSED: source IB-3B diagnostics do not replay"
        ) from exc
    if not _exact_replay_equal(value, replayed):
        raise Form4StockSignalSeedDiagnosticsError(
            "REFUSED: source IB-3B diagnostics are inconsistent or changed"
        )
    if replayed.outcome is not Form4StockSignalNormalizationOutcome.AVAILABLE:
        raise Form4StockSignalSeedDiagnosticsError(
            "REFUSED: IB-3C requires an AVAILABLE IB-3B parent"
        )
    return replayed, replayed_hash


def _exact_replay_equal(value: object, replayed: object) -> bool:
    """Compare a bounded artifact without Python's cross-type equality."""

    if type(value) is not type(replayed):
        return False
    if type(value) is tuple:
        return len(value) == len(replayed) and all(
            _exact_replay_equal(left, right)
            for left, right in zip(value, replayed, strict=True)
        )
    if is_dataclass(value) and not isinstance(value, type):
        return all(
            _exact_replay_equal(
                getattr(value, field.name),
                getattr(replayed, field.name),
            )
            for field in dataclass_fields(value)
        )
    return value == replayed


@dataclass(frozen=True)
class Form4StockSignalSeedDiagnosticRow(_ZeroAuthority):
    """One retained IB-3C row inside an atomic parent result."""

    parent_row_id: str
    issuer_cik: str
    security_id: str
    share_class_id: str
    disposition: Form4StockSignalNormalizationDisposition
    included_in_percentile_denominator: bool
    exact_ranking_value: Decimal | None
    meets_top_decile_cutoff: bool
    positive_signal_candidate: bool
    diagnostic_seed_selected: bool | None
    stock_score: None
    rank: None
    seed_selected: None
    row_id: str
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _ROW_FACTORY_TOKEN:
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: seed diagnostic row must be factory-created"
            )
        _sha256(self.parent_row_id, label="parent normalized-row ID")
        _stock_key(self.issuer_cik, self.security_id, self.share_class_id)
        if type(self.disposition) is not Form4StockSignalNormalizationDisposition:
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: seed-row disposition must be an exact enum"
            )
        included = self.disposition in (
            Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL,
            Form4StockSignalNormalizationDisposition.INCLUDE_STRUCTURAL_ZERO,
        )
        if (
            type(self.included_in_percentile_denominator) is not bool
            or self.included_in_percentile_denominator is not included
        ):
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: seed-row denominator inclusion is inconsistent"
            )
        for name in ("meets_top_decile_cutoff", "positive_signal_candidate"):
            if type(getattr(self, name)) is not bool:
                raise Form4StockSignalSeedDiagnosticsError(
                    "REFUSED: seed-row diagnostic flags must be exact booleans"
                )
        if self.diagnostic_seed_selected is not None and type(
            self.diagnostic_seed_selected
        ) is not bool:
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: diagnostic seed selection must be a boolean or unavailable"
            )
        if included:
            ranking_value = _decimal(
                self.exact_ranking_value,
                label="exact seed-ranking value",
                allow_zero=True,
            )
            if (
                self.disposition
                is Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL
                and ranking_value <= 0
            ):
                raise Form4StockSignalSeedDiagnosticsError(
                    "REFUSED: signal seed candidate requires a positive ranking value"
                )
        elif (
            self.exact_ranking_value is not None
            or self.meets_top_decile_cutoff
            or self.positive_signal_candidate
        ):
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: excluded seed row cannot carry ranking diagnostics"
            )
        expected_candidate = (
            included
            and self.disposition
            is Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL
            and self.exact_ranking_value > 0
            and self.meets_top_decile_cutoff
        )
        if self.positive_signal_candidate is not expected_candidate:
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: positive seed candidacy is inconsistent"
            )
        if self.diagnostic_seed_selected is True and not expected_candidate:
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: selected diagnostic seed is not an eligible candidate"
            )
        if (
            self.stock_score is not None
            or self.rank is not None
            or self.seed_selected is not None
        ):
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: canonical score, rank, and seed selection remain unavailable"
            )
        _sha256(self.row_id, label="seed diagnostic row ID")
        if self.row_id != hash_payload(
            Form4StockSignalSeedDiagnosticRow.lineage_payload(self)
        ):
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: seed diagnostic row ID is inconsistent"
            )
        _require_zero_authority(self)

    @property
    def stock_key(self) -> tuple[str, str, str]:
        return (self.issuer_cik, self.security_id, self.share_class_id)

    def lineage_payload(self) -> dict[str, object]:
        return {
            "parent_row_id": self.parent_row_id,
            "issuer_cik": self.issuer_cik,
            "security_id": self.security_id,
            "share_class_id": self.share_class_id,
            "disposition": self.disposition.value,
            "included_in_percentile_denominator": (
                self.included_in_percentile_denominator
            ),
            "exact_ranking_value": (
                None
                if self.exact_ranking_value is None
                else decimal_text(self.exact_ranking_value)
            ),
            "meets_top_decile_cutoff": self.meets_top_decile_cutoff,
            "positive_signal_candidate": self.positive_signal_candidate,
            "diagnostic_seed_selected": self.diagnostic_seed_selected,
            "stock_score": None,
            "rank": None,
            "seed_selected": None,
            **_ZeroAuthority.authority_payload(self),
        }

    def to_payload(self) -> dict[str, object]:
        Form4StockSignalSeedDiagnosticRow.__post_init__(
            self,
            _ROW_FACTORY_TOKEN,
        )
        return {
            **Form4StockSignalSeedDiagnosticRow.lineage_payload(self),
            "row_id": self.row_id,
        }


@dataclass(frozen=True)
class _SeedComputation:
    target_count: int
    cutoff_value: Decimal
    cutoff_tie_count: int
    top_decile_member_count: int
    positive_candidate_count: int
    selected_seed_count: int | None
    outcome: Form4StockSignalSeedOutcome
    rows: tuple[Form4StockSignalSeedDiagnosticRow, ...]


def _row_payload(
    *,
    parent_row_id: str,
    issuer_cik: str,
    security_id: str,
    share_class_id: str,
    disposition: Form4StockSignalNormalizationDisposition,
    included: bool,
    ranking_value: Decimal | None,
    meets_cutoff: bool,
    candidate: bool,
    selected: bool | None,
) -> dict[str, object]:
    return {
        "parent_row_id": parent_row_id,
        "issuer_cik": issuer_cik,
        "security_id": security_id,
        "share_class_id": share_class_id,
        "disposition": disposition.value,
        "included_in_percentile_denominator": included,
        "exact_ranking_value": (
            None if ranking_value is None else decimal_text(ranking_value)
        ),
        "meets_top_decile_cutoff": meets_cutoff,
        "positive_signal_candidate": candidate,
        "diagnostic_seed_selected": selected,
        "stock_score": None,
        "rank": None,
        "seed_selected": None,
        **_ZeroAuthority().authority_payload(),
    }


def _compute_seed_diagnostics(
    source: Form4StockSignalNormalizationDiagnostics,
) -> _SeedComputation:
    _require_frozen_policy()
    if (
        type(source.rows) is not tuple
        or len(source.rows) > MAX_FORM4_STOCK_SIGNAL_SEED_ROWS
    ):
        raise Form4StockSignalSeedDiagnosticsError(
            "REFUSED: source IB-3B rows exceed the IB-3C bound"
        )
    usable_values = tuple(
        row.winsorized_stock_score_diagnostic
        for row in source.rows
        if row.disposition
        in (
            Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL,
            Form4StockSignalNormalizationDisposition.INCLUDE_STRUCTURAL_ZERO,
        )
    )
    if (
        len(usable_values) != source.identity.usable_count
        or not usable_values
        or any(type(value) is not Decimal for value in usable_values)
    ):
        raise Form4StockSignalSeedDiagnosticsError(
            "REFUSED: source IB-3B usable rows are inconsistent"
        )
    ordered_descending = tuple(sorted(usable_values, reverse=True))
    target_count = (
        len(ordered_descending)
        + FORM4_STOCK_SIGNAL_SEED_TOP_FRACTION_DENOMINATOR
        - 1
    ) // FORM4_STOCK_SIGNAL_SEED_TOP_FRACTION_DENOMINATOR
    cutoff = ordered_descending[target_count - 1]
    cutoff_tie_count = sum(value == cutoff for value in usable_values)
    top_count = sum(value >= cutoff for value in usable_values)
    candidate_count = sum(
        row.disposition is Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL
        and row.winsorized_stock_score_diagnostic > 0
        and row.winsorized_stock_score_diagnostic >= cutoff
        for row in source.rows
    )
    if candidate_count >= FORM4_STOCK_SIGNAL_SEED_MINIMUM_POSITIVE_SEEDS:
        outcome = Form4StockSignalSeedOutcome.AVAILABLE
        selected_count: int | None = candidate_count
    else:
        outcome = (
            Form4StockSignalSeedOutcome.UNAVAILABLE_INSUFFICIENT_POSITIVE_SEEDS
        )
        selected_count = None

    rows: list[Form4StockSignalSeedDiagnosticRow] = []
    for parent_row in source.rows:
        included = parent_row.disposition in (
            Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL,
            Form4StockSignalNormalizationDisposition.INCLUDE_STRUCTURAL_ZERO,
        )
        ranking_value = (
            parent_row.winsorized_stock_score_diagnostic if included else None
        )
        meets_cutoff = bool(included and ranking_value >= cutoff)
        candidate = bool(
            meets_cutoff
            and parent_row.disposition
            is Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL
            and ranking_value > 0
        )
        selected = (
            candidate
            if outcome is Form4StockSignalSeedOutcome.AVAILABLE
            else None
        )
        payload = _row_payload(
            parent_row_id=parent_row.row_id,
            issuer_cik=parent_row.issuer_cik,
            security_id=parent_row.security_id,
            share_class_id=parent_row.share_class_id,
            disposition=parent_row.disposition,
            included=included,
            ranking_value=ranking_value,
            meets_cutoff=meets_cutoff,
            candidate=candidate,
            selected=selected,
        )
        rows.append(
            Form4StockSignalSeedDiagnosticRow(
                parent_row_id=parent_row.row_id,
                issuer_cik=parent_row.issuer_cik,
                security_id=parent_row.security_id,
                share_class_id=parent_row.share_class_id,
                disposition=parent_row.disposition,
                included_in_percentile_denominator=included,
                exact_ranking_value=ranking_value,
                meets_top_decile_cutoff=meets_cutoff,
                positive_signal_candidate=candidate,
                diagnostic_seed_selected=selected,
                stock_score=None,
                rank=None,
                seed_selected=None,
                row_id=hash_payload(payload),
                _verified_factory_token=_ROW_FACTORY_TOKEN,
            )
        )
    return _SeedComputation(
        target_count=target_count,
        cutoff_value=cutoff,
        cutoff_tie_count=cutoff_tie_count,
        top_decile_member_count=top_count,
        positive_candidate_count=candidate_count,
        selected_seed_count=selected_count,
        outcome=outcome,
        rows=tuple(rows),
    )


@dataclass(frozen=True)
class Form4StockSignalSeedIdentity(_ZeroAuthority):
    """Hash-bound identity for one complete synthetic IB-3C result."""

    diagnostics_version: str
    policy_hash: str
    builder_git_commit: str
    evaluation_session: str
    upstream_normalization_id: str
    upstream_payload_hash: str
    upstream_diagnostics_version: str
    upstream_policy_hash: str
    upstream_builder_git_commit: str
    upstream_observation_inventory_hash: str
    upstream_normalized_row_inventory_hash: str
    observation_count: int
    usable_count: int
    signal_count: int
    structural_zero_count: int
    excluded_ineligible_count: int
    excluded_missing_count: int
    target_count: int
    cutoff_tie_count: int
    top_decile_member_count: int
    positive_candidate_count: int
    selected_seed_count: int | None
    cutoff_value: Decimal
    row_inventory_hash: str
    outcome: Form4StockSignalSeedOutcome
    seed_diagnostics_id: str
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _IDENTITY_FACTORY_TOKEN:
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: seed diagnostics identity must be factory-created"
            )
        _require_frozen_policy()
        if (
            type(self.diagnostics_version) is not str
            or self.diagnostics_version != FORM4_STOCK_SIGNAL_SEED_DIAGNOSTICS_VERSION
        ):
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: seed diagnostics version is inconsistent"
            )
        _sha256(self.policy_hash, label="seed policy hash")
        if self.policy_hash != FORM4_STOCK_SIGNAL_SEED_POLICY_HASH:
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: seed policy hash is inconsistent"
            )
        _builder_commit(self.builder_git_commit)
        _text(self.evaluation_session, label="evaluation session")
        if (
            type(self.upstream_normalization_id) is not str
            or _NORMALIZATION_ID_RE.fullmatch(self.upstream_normalization_id) is None
        ):
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: upstream normalization ID has an invalid shape"
            )
        _sha256(self.upstream_payload_hash, label="upstream payload hash")
        _sha256(self.upstream_policy_hash, label="upstream policy hash")
        _builder_commit(self.upstream_builder_git_commit)
        _sha256(
            self.upstream_observation_inventory_hash,
            label="upstream observation inventory hash",
        )
        _sha256(
            self.upstream_normalized_row_inventory_hash,
            label="upstream normalized-row inventory hash",
        )
        if (
            type(self.upstream_diagnostics_version) is not str
            or self.upstream_diagnostics_version
            != FORM4_STOCK_SIGNAL_NORMALIZATION_DIAGNOSTICS_VERSION
            or self.upstream_policy_hash
            != FORM4_STOCK_SIGNAL_NORMALIZATION_POLICY_HASH
        ):
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: upstream IB-3B policy lineage is inconsistent"
            )
        counts = (
            self.observation_count,
            self.usable_count,
            self.signal_count,
            self.structural_zero_count,
            self.excluded_ineligible_count,
            self.excluded_missing_count,
            self.target_count,
            self.cutoff_tie_count,
            self.top_decile_member_count,
            self.positive_candidate_count,
        )
        if any(type(value) is not int or value < 0 for value in counts):
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: seed identity counts must be nonnegative integers"
            )
        if (
            self.observation_count < 1
            or self.observation_count > MAX_FORM4_STOCK_SIGNAL_SEED_ROWS
            or self.usable_count < 20
            or self.usable_count != self.signal_count + self.structural_zero_count
            or self.observation_count
            != self.usable_count
            + self.excluded_ineligible_count
            + self.excluded_missing_count
            or self.target_count
            != (
                self.usable_count
                + FORM4_STOCK_SIGNAL_SEED_TOP_FRACTION_DENOMINATOR
                - 1
            )
            // FORM4_STOCK_SIGNAL_SEED_TOP_FRACTION_DENOMINATOR
            or self.top_decile_member_count < self.target_count
            or self.top_decile_member_count > self.usable_count
            or self.cutoff_tie_count < 1
            or self.cutoff_tie_count > self.top_decile_member_count
            or self.top_decile_member_count - self.target_count
            >= self.cutoff_tie_count
            or self.positive_candidate_count > self.signal_count
            or self.positive_candidate_count > self.top_decile_member_count
        ):
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: seed identity counts are inconsistent"
            )
        _decimal(self.cutoff_value, label="seed cutoff value", allow_zero=True)
        _sha256(self.row_inventory_hash, label="seed-row inventory hash")
        if type(self.outcome) is not Form4StockSignalSeedOutcome:
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: seed outcome must be an exact enum"
            )
        if self.outcome is Form4StockSignalSeedOutcome.AVAILABLE:
            if (
                self.positive_candidate_count
                < FORM4_STOCK_SIGNAL_SEED_MINIMUM_POSITIVE_SEEDS
                or type(self.selected_seed_count) is not int
                or self.selected_seed_count != self.positive_candidate_count
            ):
                raise Form4StockSignalSeedDiagnosticsError(
                    "REFUSED: available seed selection violates its minimum"
                )
        elif (
            self.positive_candidate_count
            >= FORM4_STOCK_SIGNAL_SEED_MINIMUM_POSITIVE_SEEDS
            or self.selected_seed_count is not None
        ):
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: unavailable seed selection is inconsistent"
            )
        _text(self.seed_diagnostics_id, label="seed diagnostics ID")
        expected_id = (
            "form4-stock-signal-seed-diagnostics-"
            f"{hash_payload(Form4StockSignalSeedIdentity.lineage_payload(self))[:16]}"
        )
        if self.seed_diagnostics_id != expected_id:
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: seed diagnostics ID is inconsistent"
            )
        _require_zero_authority(self)

    def lineage_payload(self) -> dict[str, object]:
        return {
            "diagnostics_version": self.diagnostics_version,
            "policy_hash": self.policy_hash,
            "builder_git_commit": self.builder_git_commit,
            "evaluation_session": self.evaluation_session,
            "upstream_normalization_id": self.upstream_normalization_id,
            "upstream_payload_hash": self.upstream_payload_hash,
            "upstream_diagnostics_version": self.upstream_diagnostics_version,
            "upstream_policy_hash": self.upstream_policy_hash,
            "upstream_builder_git_commit": self.upstream_builder_git_commit,
            "upstream_observation_inventory_hash": (
                self.upstream_observation_inventory_hash
            ),
            "upstream_normalized_row_inventory_hash": (
                self.upstream_normalized_row_inventory_hash
            ),
            "observation_count": self.observation_count,
            "usable_count": self.usable_count,
            "signal_count": self.signal_count,
            "structural_zero_count": self.structural_zero_count,
            "excluded_ineligible_count": self.excluded_ineligible_count,
            "excluded_missing_count": self.excluded_missing_count,
            "target_count": self.target_count,
            "cutoff_tie_count": self.cutoff_tie_count,
            "top_decile_member_count": self.top_decile_member_count,
            "positive_candidate_count": self.positive_candidate_count,
            "selected_seed_count": self.selected_seed_count,
            "cutoff_value": decimal_text(self.cutoff_value),
            "row_inventory_hash": self.row_inventory_hash,
            "outcome": self.outcome.value,
            **_ZeroAuthority.authority_payload(self),
        }

    def to_payload(self) -> dict[str, object]:
        Form4StockSignalSeedIdentity.__post_init__(
            self,
            _IDENTITY_FACTORY_TOKEN,
        )
        return {
            **Form4StockSignalSeedIdentity.lineage_payload(self),
            "seed_diagnostics_id": self.seed_diagnostics_id,
        }


def _build_identity(
    *,
    source: Form4StockSignalNormalizationDiagnostics,
    source_payload_hash: str,
    computation: _SeedComputation,
    builder_git_commit: str,
) -> Form4StockSignalSeedIdentity:
    parent = source.identity
    row_inventory_hash = hash_payload(
        [row.to_payload() for row in computation.rows]
    )
    payload = {
        "diagnostics_version": FORM4_STOCK_SIGNAL_SEED_DIAGNOSTICS_VERSION,
        "policy_hash": FORM4_STOCK_SIGNAL_SEED_POLICY_HASH,
        "builder_git_commit": builder_git_commit,
        "evaluation_session": parent.evaluation_session,
        "upstream_normalization_id": parent.normalization_id,
        "upstream_payload_hash": source_payload_hash,
        "upstream_diagnostics_version": parent.diagnostics_version,
        "upstream_policy_hash": parent.policy_hash,
        "upstream_builder_git_commit": parent.builder_git_commit,
        "upstream_observation_inventory_hash": parent.observation_inventory_hash,
        "upstream_normalized_row_inventory_hash": (
            parent.normalized_row_inventory_hash
        ),
        "observation_count": parent.observation_count,
        "usable_count": parent.usable_count,
        "signal_count": parent.signal_count,
        "structural_zero_count": parent.structural_zero_count,
        "excluded_ineligible_count": parent.excluded_ineligible_count,
        "excluded_missing_count": parent.excluded_missing_count,
        "target_count": computation.target_count,
        "cutoff_tie_count": computation.cutoff_tie_count,
        "top_decile_member_count": computation.top_decile_member_count,
        "positive_candidate_count": computation.positive_candidate_count,
        "selected_seed_count": computation.selected_seed_count,
        "cutoff_value": decimal_text(computation.cutoff_value),
        "row_inventory_hash": row_inventory_hash,
        "outcome": computation.outcome.value,
        **_ZeroAuthority().authority_payload(),
    }
    return Form4StockSignalSeedIdentity(
        diagnostics_version=FORM4_STOCK_SIGNAL_SEED_DIAGNOSTICS_VERSION,
        policy_hash=FORM4_STOCK_SIGNAL_SEED_POLICY_HASH,
        builder_git_commit=builder_git_commit,
        evaluation_session=parent.evaluation_session,
        upstream_normalization_id=parent.normalization_id,
        upstream_payload_hash=source_payload_hash,
        upstream_diagnostics_version=parent.diagnostics_version,
        upstream_policy_hash=parent.policy_hash,
        upstream_builder_git_commit=parent.builder_git_commit,
        upstream_observation_inventory_hash=parent.observation_inventory_hash,
        upstream_normalized_row_inventory_hash=(
            parent.normalized_row_inventory_hash
        ),
        observation_count=parent.observation_count,
        usable_count=parent.usable_count,
        signal_count=parent.signal_count,
        structural_zero_count=parent.structural_zero_count,
        excluded_ineligible_count=parent.excluded_ineligible_count,
        excluded_missing_count=parent.excluded_missing_count,
        target_count=computation.target_count,
        cutoff_tie_count=computation.cutoff_tie_count,
        top_decile_member_count=computation.top_decile_member_count,
        positive_candidate_count=computation.positive_candidate_count,
        selected_seed_count=computation.selected_seed_count,
        cutoff_value=computation.cutoff_value,
        row_inventory_hash=row_inventory_hash,
        outcome=computation.outcome,
        seed_diagnostics_id=(
            "form4-stock-signal-seed-diagnostics-"
            f"{hash_payload(payload)[:16]}"
        ),
        _verified_factory_token=_IDENTITY_FACTORY_TOKEN,
    )


@dataclass(frozen=True)
class Form4StockSignalSeedDiagnostics(_ZeroAuthority):
    """Replayable, exhaustive synthetic IB-3C diagnostic evidence."""

    identity: Form4StockSignalSeedIdentity
    source_normalization: Form4StockSignalNormalizationDiagnostics
    rows: tuple[Form4StockSignalSeedDiagnosticRow, ...]
    outcome: Form4StockSignalSeedOutcome
    target_count: int
    cutoff_value: Decimal
    cutoff_tie_count: int
    top_decile_member_count: int
    positive_candidate_count: int
    selected_seed_count: int | None
    stock_score: None
    ranking: None
    seed_selection: None
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _RESULT_FACTORY_TOKEN:
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: seed diagnostics must be factory-created"
            )
        if type(self.identity) is not Form4StockSignalSeedIdentity:
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: seed diagnostics require an exact identity"
            )
        Form4StockSignalSeedIdentity.__post_init__(
            self.identity,
            _IDENTITY_FACTORY_TOKEN,
        )
        replayed_source, source_hash = _replay_available_parent(
            self.source_normalization
        )
        computation = _compute_seed_diagnostics(replayed_source)
        if type(self.rows) is not tuple or self.rows != computation.rows:
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: seed rows do not replay from the IB-3B parent"
            )
        for row in self.rows:
            if type(row) is not Form4StockSignalSeedDiagnosticRow:
                raise Form4StockSignalSeedDiagnosticsError(
                    "REFUSED: seed rows contain an unexpected type"
                )
            Form4StockSignalSeedDiagnosticRow.__post_init__(
                row,
                _ROW_FACTORY_TOKEN,
            )
        expected_identity = _build_identity(
            source=replayed_source,
            source_payload_hash=source_hash,
            computation=computation,
            builder_git_commit=self.identity.builder_git_commit,
        )
        if self.identity != expected_identity:
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: seed diagnostics identity does not replay"
            )
        if type(self.outcome) is not Form4StockSignalSeedOutcome:
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: seed diagnostics outcome must be an exact enum"
            )
        counts = (
            self.target_count,
            self.cutoff_tie_count,
            self.top_decile_member_count,
            self.positive_candidate_count,
        )
        if any(type(value) is not int for value in counts):
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: seed diagnostics counts must be exact integers"
            )
        if self.selected_seed_count is not None and type(
            self.selected_seed_count
        ) is not int:
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: selected seed count must be an exact integer or unavailable"
            )
        _decimal(
            self.cutoff_value,
            label="seed diagnostics cutoff value",
            allow_zero=True,
        )
        summary = (
            self.outcome,
            self.target_count,
            self.cutoff_value,
            self.cutoff_tie_count,
            self.top_decile_member_count,
            self.positive_candidate_count,
            self.selected_seed_count,
        )
        expected_summary = (
            computation.outcome,
            computation.target_count,
            computation.cutoff_value,
            computation.cutoff_tie_count,
            computation.top_decile_member_count,
            computation.positive_candidate_count,
            computation.selected_seed_count,
        )
        if summary != expected_summary:
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: seed diagnostics summary is inconsistent"
            )
        if (
            self.stock_score is not None
            or self.ranking is not None
            or self.seed_selection is not None
        ):
            raise Form4StockSignalSeedDiagnosticsError(
                "REFUSED: canonical score, rank, and seed selection remain unavailable"
            )
        _require_zero_authority(self)

    def to_payload(self) -> dict[str, object]:
        Form4StockSignalSeedDiagnostics.__post_init__(
            self,
            _RESULT_FACTORY_TOKEN,
        )
        replayed_source, _ = _replay_available_parent(self.source_normalization)
        return {
            "identity": Form4StockSignalSeedIdentity.to_payload(self.identity),
            "source_normalization": (
                Form4StockSignalNormalizationDiagnostics.to_payload(
                    replayed_source
                )
            ),
            "rows": [
                Form4StockSignalSeedDiagnosticRow.to_payload(row)
                for row in self.rows
            ],
            "outcome": self.outcome.value,
            "target_count": self.target_count,
            "cutoff_value": decimal_text(self.cutoff_value),
            "cutoff_tie_count": self.cutoff_tie_count,
            "top_decile_member_count": self.top_decile_member_count,
            "positive_candidate_count": self.positive_candidate_count,
            "selected_seed_count": self.selected_seed_count,
            "stock_score": None,
            "ranking": None,
            "seed_selection": None,
            **_ZeroAuthority.authority_payload(self),
        }


def build_form4_stock_signal_seed_diagnostics(
    source_normalization: Form4StockSignalNormalizationDiagnostics,
    *,
    builder_git_commit: str,
) -> Form4StockSignalSeedDiagnostics:
    """Build one bounded synthetic IB-3C diagnostic from an exact IB-3B parent."""

    builder_git_commit = _builder_commit(builder_git_commit)
    _require_frozen_policy()
    source, source_hash = _replay_available_parent(source_normalization)
    computation = _compute_seed_diagnostics(source)
    identity = _build_identity(
        source=source,
        source_payload_hash=source_hash,
        computation=computation,
        builder_git_commit=builder_git_commit,
    )
    result = Form4StockSignalSeedDiagnostics(
        identity=identity,
        source_normalization=source,
        rows=computation.rows,
        outcome=computation.outcome,
        target_count=computation.target_count,
        cutoff_value=computation.cutoff_value,
        cutoff_tie_count=computation.cutoff_tie_count,
        top_decile_member_count=computation.top_decile_member_count,
        positive_candidate_count=computation.positive_candidate_count,
        selected_seed_count=computation.selected_seed_count,
        stock_score=None,
        ranking=None,
        seed_selection=None,
        _verified_factory_token=_RESULT_FACTORY_TOKEN,
    )
    final_source, final_hash = _replay_available_parent(source_normalization)
    if final_source != source or final_hash != source_hash:
        raise Form4StockSignalSeedDiagnosticsError(
            "REFUSED: source IB-3B diagnostics changed during evaluation"
        )
    return result


__all__ = [
    "FORM4_STOCK_SIGNAL_SEED_CLUSTER_COMPARISON_POLICY",
    "FORM4_STOCK_SIGNAL_SEED_COUNT_POLICY",
    "FORM4_STOCK_SIGNAL_SEED_DENOMINATOR_POLICY",
    "FORM4_STOCK_SIGNAL_SEED_DIAGNOSTICS_VERSION",
    "FORM4_STOCK_SIGNAL_SEED_ELIGIBILITY_POLICY",
    "FORM4_STOCK_SIGNAL_SEED_MINIMUM_POSITIVE_SEEDS",
    "FORM4_STOCK_SIGNAL_SEED_POLICY_HASH",
    "FORM4_STOCK_SIGNAL_SEED_RANKING_METHOD",
    "FORM4_STOCK_SIGNAL_SEED_RANKING_VALUE",
    "FORM4_STOCK_SIGNAL_SEED_TIE_POLICY",
    "FORM4_STOCK_SIGNAL_SEED_TOP_FRACTION_DENOMINATOR",
    "FORM4_STOCK_SIGNAL_SEED_TOP_FRACTION_NUMERATOR",
    "MAX_FORM4_STOCK_SIGNAL_SEED_ROWS",
    "MAX_FORM4_STOCK_SIGNAL_SEED_TEXT_CHARACTERS",
    "Form4StockSignalSeedDiagnosticRow",
    "Form4StockSignalSeedDiagnostics",
    "Form4StockSignalSeedDiagnosticsError",
    "Form4StockSignalSeedIdentity",
    "Form4StockSignalSeedOutcome",
    "build_form4_stock_signal_seed_diagnostics",
]
