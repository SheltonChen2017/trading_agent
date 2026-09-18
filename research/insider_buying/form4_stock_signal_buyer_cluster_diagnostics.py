"""Synthetic-only, zero-authority IB-3D buyer-cluster diagnostics.

This module consumes one exact, replayable, AVAILABLE IB-3C seed artifact and
one exact, replayable IB-3A formula artifact for every IB-3B signal row.  It
preserves IB-3C's selection without recomputing its denominator, cutoff, ties,
or positivity rules, then applies the separately approved buyer-breadth gate.
A stock is cluster-qualified only when IB-3C selected it and its replayed
IB-3A buyer breadth is at least two.  Fewer than two qualified stocks makes
the whole diagnostic selection unavailable, with no partial selection.

Buyer identifiers remain caller-declared and unverified.  This is fixture
evidence, not a canonical score, rank, seed signal, or identity conclusion.
It grants no SEC, provider, outcome, ETF, QC, broker, deployment, or trading
authority and consumes no research outcome look.
"""
from __future__ import annotations

import re
from dataclasses import InitVar, dataclass, fields as dataclass_fields, is_dataclass
from decimal import Decimal
from enum import Enum

from data.financial_primitives import decimal_text
from data.hashing import hash_payload
import research.insider_buying.form4_stock_signal_formula_diagnostics as formula_contract
import research.insider_buying.form4_stock_signal_normalization_diagnostics as normalization_contract
import research.insider_buying.form4_stock_signal_seed_diagnostics as seed_contract


FORM4_STOCK_SIGNAL_BUYER_CLUSTER_DIAGNOSTICS_VERSION = (
    "INSETF-IB3D-FORM4-STOCK-SIGNAL-BUYER-CLUSTER-DIAGNOSTICS-v1"
)
FORM4_STOCK_SIGNAL_BUYER_CLUSTER_SOURCE_POLICY = (
    "exact-available-ib3c-parent-and-one-exact-ib3a-source-per-signal-row"
)
FORM4_STOCK_SIGNAL_BUYER_CLUSTER_SELECTION_POLICY = (
    "preserve-ib3c-selection-and-require-buyer-breadth-at-least-two"
)
FORM4_STOCK_SIGNAL_BUYER_CLUSTER_BUYER_ID_POLICY = (
    "caller-declared-unverified"
)
FORM4_STOCK_SIGNAL_BUYER_CLUSTER_MINIMUM_BUYER_BREADTH = 2
FORM4_STOCK_SIGNAL_BUYER_CLUSTER_MINIMUM_QUALIFIED_SEEDS = 2
MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_ROWS = 10_000
MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_SOURCE_EVENTS = 10_000
MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_TEXT_CHARACTERS = 128

_MAX_CLUSTER_DECIMAL_DIGITS = 50
_MAX_CLUSTER_DECIMAL_ABS_EXPONENT = 2_048

_CIK_RE = re.compile(r"^[0-9]{10}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SEED_ID_RE = re.compile(
    r"^form4-stock-signal-seed-diagnostics-[0-9a-f]{16}$"
)
_FORMULA_ID_RE = re.compile(
    r"^form4-stock-signal-formula-diagnostics-[0-9a-f]{16}$"
)
_ROW_FACTORY_TOKEN = object()
_IDENTITY_FACTORY_TOKEN = object()
_RESULT_FACTORY_TOKEN = object()


class Form4StockSignalBuyerClusterDiagnosticsError(ValueError):
    """A bounded synthetic IB-3D diagnostic contract failed closed."""


class Form4StockSignalBuyerClusterOutcome(str, Enum):
    """Availability of the complete buyer-cluster diagnostic selection."""

    AVAILABLE = "available"
    UNAVAILABLE_INSUFFICIENT_BUYER_CLUSTER_SEEDS = (
        "unavailable_insufficient_buyer_cluster_seeds"
    )


def _policy_payload() -> dict[str, object]:
    return {
        "diagnostics_version": (
            FORM4_STOCK_SIGNAL_BUYER_CLUSTER_DIAGNOSTICS_VERSION
        ),
        "source_policy": FORM4_STOCK_SIGNAL_BUYER_CLUSTER_SOURCE_POLICY,
        "selection_policy": FORM4_STOCK_SIGNAL_BUYER_CLUSTER_SELECTION_POLICY,
        "buyer_id_policy": FORM4_STOCK_SIGNAL_BUYER_CLUSTER_BUYER_ID_POLICY,
        "minimum_buyer_breadth": (
            FORM4_STOCK_SIGNAL_BUYER_CLUSTER_MINIMUM_BUYER_BREADTH
        ),
        "minimum_qualified_seeds": (
            FORM4_STOCK_SIGNAL_BUYER_CLUSTER_MINIMUM_QUALIFIED_SEEDS
        ),
        "outcomes": {
            "available": Form4StockSignalBuyerClusterOutcome.AVAILABLE.value,
            "insufficient_buyer_cluster_seeds": (
                Form4StockSignalBuyerClusterOutcome.UNAVAILABLE_INSUFFICIENT_BUYER_CLUSTER_SEEDS.value
            ),
        },
        "insufficient_qualified_seeds": (
            "named-unavailable-no-aggregate-or-row-selection"
        ),
        "row_retention": "retain-every-ib3c-row-in-parent-order",
        "ordinal_rank": "unavailable",
        "canonical_stock_score": "unavailable",
        "canonical_seed_selection": "unavailable",
        "upstream_seed_diagnostics_version": (
            seed_contract.FORM4_STOCK_SIGNAL_SEED_DIAGNOSTICS_VERSION
        ),
        "upstream_seed_policy_hash": (
            seed_contract.FORM4_STOCK_SIGNAL_SEED_POLICY_HASH
        ),
        "upstream_seed_outcome": seed_contract.Form4StockSignalSeedOutcome.AVAILABLE.value,
        "source_formula_diagnostics_version": (
            formula_contract.FORM4_STOCK_SIGNAL_FORMULA_DIAGNOSTICS_VERSION
        ),
        "source_formula_numeric_policy_hash": (
            formula_contract.FORM4_STOCK_SIGNAL_NUMERIC_POLICY_HASH
        ),
        "resource_bounds": {
            "rows": MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_ROWS,
            "source_events": (
                MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_SOURCE_EVENTS
            ),
            "text_characters": (
                MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_TEXT_CHARACTERS
            ),
            "decimal_digits": _MAX_CLUSTER_DECIMAL_DIGITS,
            "decimal_abs_exponent": _MAX_CLUSTER_DECIMAL_ABS_EXPONENT,
        },
    }


FORM4_STOCK_SIGNAL_BUYER_CLUSTER_POLICY_HASH = hash_payload(_policy_payload())


def _require_frozen_policy() -> None:
    if (
        FORM4_STOCK_SIGNAL_BUYER_CLUSTER_DIAGNOSTICS_VERSION
        != "INSETF-IB3D-FORM4-STOCK-SIGNAL-BUYER-CLUSTER-DIAGNOSTICS-v1"
        or FORM4_STOCK_SIGNAL_BUYER_CLUSTER_SOURCE_POLICY
        != "exact-available-ib3c-parent-and-one-exact-ib3a-source-per-signal-row"
        or FORM4_STOCK_SIGNAL_BUYER_CLUSTER_SELECTION_POLICY
        != "preserve-ib3c-selection-and-require-buyer-breadth-at-least-two"
        or FORM4_STOCK_SIGNAL_BUYER_CLUSTER_BUYER_ID_POLICY
        != "caller-declared-unverified"
        or FORM4_STOCK_SIGNAL_BUYER_CLUSTER_MINIMUM_BUYER_BREADTH != 2
        or FORM4_STOCK_SIGNAL_BUYER_CLUSTER_MINIMUM_QUALIFIED_SEEDS != 2
        or Form4StockSignalBuyerClusterOutcome.AVAILABLE.value != "available"
        or Form4StockSignalBuyerClusterOutcome.UNAVAILABLE_INSUFFICIENT_BUYER_CLUSTER_SEEDS.value
        != "unavailable_insufficient_buyer_cluster_seeds"
        or MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_ROWS != 10_000
        or MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_SOURCE_EVENTS != 10_000
        or MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_TEXT_CHARACTERS != 128
        or _MAX_CLUSTER_DECIMAL_DIGITS != 50
        or _MAX_CLUSTER_DECIMAL_ABS_EXPONENT != 2_048
        or seed_contract.MAX_FORM4_STOCK_SIGNAL_SEED_ROWS != 10_000
        or formula_contract.MAX_FORM4_STOCK_SIGNAL_EVENTS != 10_000
        or seed_contract.FORM4_STOCK_SIGNAL_SEED_DIAGNOSTICS_VERSION
        != "INSETF-IB3C-FORM4-STOCK-SIGNAL-SEED-DIAGNOSTICS-v1"
        or seed_contract.FORM4_STOCK_SIGNAL_SEED_POLICY_HASH
        != (
            "809a0072a1976463545674733305b8f4"
            "0b6e606da9e8da3b29c6ca6950f371f4"
        )
        or formula_contract.FORM4_STOCK_SIGNAL_FORMULA_DIAGNOSTICS_VERSION
        != "INSETF-IB3A-FORM4-STOCK-SIGNAL-FORMULA-DIAGNOSTICS-v1"
        or formula_contract.FORM4_STOCK_SIGNAL_NUMERIC_POLICY_HASH
        != (
            "a514e5d9548fe4b7a9cc010767ff06e5"
            "0ee3831b5225fd4ddc38d95ec4c1f11d"
        )
        or FORM4_STOCK_SIGNAL_BUYER_CLUSTER_POLICY_HASH
        != (
            "452a875f354530d5db1a55c1ea0d8cd9"
            "3fecca4f39904c26e616c09cb9050273"
        )
        or hash_payload(_policy_payload())
        != FORM4_STOCK_SIGNAL_BUYER_CLUSTER_POLICY_HASH
    ):
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: frozen IB-3D buyer-cluster policy is inconsistent"
        )


def _text(value: object, *, label: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or not value.isprintable()
        or len(value) > MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_TEXT_CHARACTERS
    ):
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            f"REFUSED: {label} must be bounded nonempty printable text"
        )
    return value


def _sha256(value: object, *, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            f"REFUSED: {label} must be a lowercase SHA-256 digest"
        )
    return value


def _builder_commit(value: object) -> str:
    if type(value) is not str or _GIT_COMMIT_RE.fullmatch(value) is None:
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: builder Git commit must be a lowercase 40-hex identity"
        )
    return value


def _stock_key(
    issuer_cik: object,
    security_id: object,
    share_class_id: object,
) -> tuple[str, str, str]:
    if type(issuer_cik) is not str or _CIK_RE.fullmatch(issuer_cik) is None:
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: issuer CIK must be exactly ten digits"
        )
    return (
        issuer_cik,
        _text(security_id, label="security ID"),
        _text(share_class_id, label="share-class ID"),
    )


def _decimal(value: object, *, label: str, allow_zero: bool) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            f"REFUSED: {label} must be an exact finite Decimal"
        )
    decimal_tuple = value.as_tuple()
    if (
        len(decimal_tuple.digits) > _MAX_CLUSTER_DECIMAL_DIGITS
        or abs(int(decimal_tuple.exponent)) > _MAX_CLUSTER_DECIMAL_ABS_EXPONENT
    ):
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            f"REFUSED: {label} exceeds the Decimal resource bound"
        )
    if value < 0 or (not allow_zero and value == 0):
        comparator = "nonnegative" if allow_zero else "positive"
        raise Form4StockSignalBuyerClusterDiagnosticsError(
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
    def buyer_ids_are_caller_declared(self) -> bool:
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
            "buyer_ids_are_caller_declared": True,
            **{name: False for name in _BOOLEAN_AUTHORITY_FIELDS},
            "authorized_outcome_looks": 0,
            "consumed_outcome_looks": 0,
        }


def _require_zero_authority(value: object) -> None:
    if getattr(value, "population_is_caller_declared") is not True:
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: IB-3D population must remain caller-declared"
        )
    if getattr(value, "canonical_population_verified") is not False:
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: IB-3D cannot verify a canonical population"
        )
    if getattr(value, "role_ids_are_caller_declared") is not True:
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: IB-3D role IDs remain caller-declared"
        )
    if getattr(value, "buyer_ids_are_caller_declared") is not True:
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: IB-3D buyer IDs must remain caller-declared"
        )
    if any(type(getattr(value, name)) is not bool for name in _BOOLEAN_AUTHORITY_FIELDS):
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: every IB-3D authority flag must be an exact boolean"
        )
    if any(getattr(value, name) is not False for name in _BOOLEAN_AUTHORITY_FIELDS):
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: IB-3D buyer-cluster diagnostics cannot grant authority"
        )
    for name in ("authorized_outcome_looks", "consumed_outcome_looks"):
        count = getattr(value, name)
        if type(count) is not int or count != 0:
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: IB-3D diagnostics require exactly zero outcome looks"
            )


def _exact_replay_equal(value: object, replayed: object) -> bool:
    """Compare bounded artifacts without Python's cross-type equality."""

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


def _replay_available_seed_parent(
    value: object,
) -> tuple[seed_contract.Form4StockSignalSeedDiagnostics, str]:
    if type(value) is not seed_contract.Form4StockSignalSeedDiagnostics:
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: IB-3D requires exact IB-3C seed diagnostics"
        )
    try:
        if (
            type(value.rows) is not tuple
            or not value.rows
            or len(value.rows) > MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_ROWS
        ):
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: source IB-3C row inventory is out of bounds"
            )
        replayed = seed_contract.build_form4_stock_signal_seed_diagnostics(
            value.source_normalization,
            builder_git_commit=value.identity.builder_git_commit,
        )
        replayed_hash = hash_payload(
            seed_contract.Form4StockSignalSeedDiagnostics.to_payload(replayed)
        )
    except (
        AttributeError,
        TypeError,
        seed_contract.Form4StockSignalSeedDiagnosticsError,
    ) as exc:
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: source IB-3C diagnostics do not replay"
        ) from exc
    if not _exact_replay_equal(value, replayed):
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: source IB-3C diagnostics are inconsistent or changed"
        )
    if replayed.outcome is not seed_contract.Form4StockSignalSeedOutcome.AVAILABLE:
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: IB-3D requires an AVAILABLE IB-3C parent"
        )
    return replayed, replayed_hash


@dataclass(frozen=True)
class _FormulaReplay:
    diagnostics: formula_contract.Form4StockSignalFormulaDiagnostics
    payload_hash: str

    @property
    def stock_key(self) -> tuple[str, str, str]:
        return (
            self.diagnostics.issuer_cik,
            self.diagnostics.security_id,
            self.diagnostics.share_class_id,
        )


def _replay_formula_source(value: object) -> _FormulaReplay:
    if type(value) is not formula_contract.Form4StockSignalFormulaDiagnostics:
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: IB-3D formula sources must be exact IB-3A diagnostics"
        )
    try:
        if (
            type(value.events) is not tuple
            or not value.events
            or len(value.events) > formula_contract.MAX_FORM4_STOCK_SIGNAL_EVENTS
        ):
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: source IB-3A event inventory is out of bounds"
            )
        replayed = formula_contract.build_form4_stock_signal_formula_diagnostics(
            value.events,
            builder_git_commit=value.identity.builder_git_commit,
        )
        replayed_hash = hash_payload(
            formula_contract.Form4StockSignalFormulaDiagnostics.to_payload(replayed)
        )
    except (
        AttributeError,
        TypeError,
        formula_contract.Form4StockSignalFormulaDiagnosticsError,
    ) as exc:
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: source IB-3A diagnostics do not replay"
        ) from exc
    if not _exact_replay_equal(value, replayed):
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: source IB-3A diagnostics are inconsistent or changed"
        )
    return _FormulaReplay(diagnostics=replayed, payload_hash=replayed_hash)


def _replay_formula_sources(
    values: object,
) -> tuple[tuple[_FormulaReplay, ...], int, str]:
    if type(values) is not tuple:
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: IB-3A diagnostics must be supplied as an exact tuple"
        )
    if (
        not values
        or len(values) > MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_ROWS
    ):
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: IB-3A source inventory is out of bounds"
        )
    preflight_event_count = 0
    for value in values:
        if type(value) is not formula_contract.Form4StockSignalFormulaDiagnostics:
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: IB-3D formula sources must be exact IB-3A diagnostics"
            )
        try:
            events = value.events
        except AttributeError as exc:
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: source IB-3A event inventory is unavailable"
            ) from exc
        if (
            type(events) is not tuple
            or not events
            or len(events) > formula_contract.MAX_FORM4_STOCK_SIGNAL_EVENTS
        ):
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: source IB-3A event inventory is out of bounds"
            )
        preflight_event_count += len(events)
        if (
            preflight_event_count
            > MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_SOURCE_EVENTS
        ):
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: aggregate IB-3A source events exceed the IB-3D bound"
            )
    replayed = tuple(_replay_formula_source(value) for value in values)
    event_count = sum(len(source.diagnostics.events) for source in replayed)
    if (
        event_count != preflight_event_count
        or event_count > MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_SOURCE_EVENTS
    ):
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: replayed IB-3A source event inventory is inconsistent"
        )
    stock_keys = tuple(source.stock_key for source in replayed)
    diagnostics_ids = tuple(
        source.diagnostics.identity.diagnostics_id for source in replayed
    )
    payload_hashes = tuple(source.payload_hash for source in replayed)
    if (
        len(set(stock_keys)) != len(stock_keys)
        or len(set(diagnostics_ids)) != len(diagnostics_ids)
        or len(set(payload_hashes)) != len(payload_hashes)
    ):
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: IB-3A sources require unique stock, diagnostic, and payload identities"
        )
    canonical = tuple(sorted(replayed, key=lambda source: source.stock_key))
    inventory_hash = hash_payload(
        [
            formula_contract.Form4StockSignalFormulaDiagnostics.to_payload(
                source.diagnostics
            )
            for source in canonical
        ]
    )
    return canonical, event_count, inventory_hash


@dataclass(frozen=True)
class Form4StockSignalBuyerClusterDiagnosticRow(_ZeroAuthority):
    """One retained IB-3D row inside an atomic buyer-cluster result."""

    parent_seed_row_id: str
    issuer_cik: str
    security_id: str
    share_class_id: str
    disposition: normalization_contract.Form4StockSignalNormalizationDisposition
    included_in_percentile_denominator: bool
    exact_ranking_value: Decimal | None
    meets_top_decile_cutoff: bool
    positive_signal_candidate: bool
    base_diagnostic_seed_selected: bool
    source_formula_diagnostics_id: str | None
    source_formula_payload_hash: str | None
    source_breadth_id: str | None
    source_breadth_hash: str | None
    buyer_breadth: int | None
    meets_minimum_buyer_breadth: bool | None
    cluster_qualified_candidate: bool
    diagnostic_cluster_seed_selected: bool | None
    stock_score: None
    rank: None
    seed_selected: None
    row_id: str
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _ROW_FACTORY_TOKEN:
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: buyer-cluster diagnostic row must be factory-created"
            )
        _sha256(self.parent_seed_row_id, label="parent seed-row ID")
        _stock_key(self.issuer_cik, self.security_id, self.share_class_id)
        if (
            type(self.disposition)
            is not normalization_contract.Form4StockSignalNormalizationDisposition
        ):
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: buyer-cluster row disposition must be an exact enum"
            )
        included = self.disposition in (
            normalization_contract.Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL,
            normalization_contract.Form4StockSignalNormalizationDisposition.INCLUDE_STRUCTURAL_ZERO,
        )
        if (
            type(self.included_in_percentile_denominator) is not bool
            or self.included_in_percentile_denominator is not included
        ):
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: buyer-cluster denominator inclusion is inconsistent"
            )
        for name in (
            "meets_top_decile_cutoff",
            "positive_signal_candidate",
            "base_diagnostic_seed_selected",
            "cluster_qualified_candidate",
        ):
            if type(getattr(self, name)) is not bool:
                raise Form4StockSignalBuyerClusterDiagnosticsError(
                    "REFUSED: buyer-cluster diagnostic flags must be exact booleans"
                )
        if self.diagnostic_cluster_seed_selected is not None and type(
            self.diagnostic_cluster_seed_selected
        ) is not bool:
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: cluster selection must be a boolean or unavailable"
            )
        if included:
            ranking_value = _decimal(
                self.exact_ranking_value,
                label="exact retained ranking value",
                allow_zero=True,
            )
            if (
                self.disposition
                is normalization_contract.Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL
                and ranking_value <= 0
            ):
                raise Form4StockSignalBuyerClusterDiagnosticsError(
                    "REFUSED: retained signal ranking value must be positive"
                )
        elif (
            self.exact_ranking_value is not None
            or self.meets_top_decile_cutoff
            or self.positive_signal_candidate
            or self.base_diagnostic_seed_selected
        ):
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: excluded buyer-cluster row cannot carry seed diagnostics"
            )
        signal_row = (
            self.disposition
            is normalization_contract.Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL
        )
        source_values = (
            self.source_formula_diagnostics_id,
            self.source_formula_payload_hash,
            self.source_breadth_id,
            self.source_breadth_hash,
            self.buyer_breadth,
            self.meets_minimum_buyer_breadth,
        )
        if signal_row:
            if any(value is None for value in source_values):
                raise Form4StockSignalBuyerClusterDiagnosticsError(
                    "REFUSED: signal row requires complete IB-3A breadth lineage"
                )
            if (
                type(self.source_formula_diagnostics_id) is not str
                or _FORMULA_ID_RE.fullmatch(self.source_formula_diagnostics_id)
                is None
            ):
                raise Form4StockSignalBuyerClusterDiagnosticsError(
                    "REFUSED: source formula diagnostics ID has an invalid shape"
                )
            _sha256(self.source_formula_payload_hash, label="source formula payload hash")
            _sha256(self.source_breadth_id, label="source breadth ID")
            _sha256(self.source_breadth_hash, label="source breadth hash")
            if type(self.buyer_breadth) is not int or self.buyer_breadth < 1:
                raise Form4StockSignalBuyerClusterDiagnosticsError(
                    "REFUSED: buyer breadth must be a positive exact integer"
                )
            if type(self.meets_minimum_buyer_breadth) is not bool or (
                self.meets_minimum_buyer_breadth
                is not (
                    self.buyer_breadth
                    >= FORM4_STOCK_SIGNAL_BUYER_CLUSTER_MINIMUM_BUYER_BREADTH
                )
            ):
                raise Form4StockSignalBuyerClusterDiagnosticsError(
                    "REFUSED: buyer-breadth gate is inconsistent"
                )
        elif any(value is not None for value in source_values):
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: nonsignal row cannot claim IB-3A breadth lineage"
            )
        expected_cluster_candidate = bool(
            self.base_diagnostic_seed_selected
            and self.meets_minimum_buyer_breadth is True
        )
        if self.cluster_qualified_candidate is not expected_cluster_candidate:
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: buyer-cluster candidacy is inconsistent"
            )
        if (
            self.diagnostic_cluster_seed_selected is True
            and not expected_cluster_candidate
        ):
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: selected buyer-cluster seed is not qualified"
            )
        if (
            self.stock_score is not None
            or self.rank is not None
            or self.seed_selected is not None
        ):
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: canonical score, rank, and seed selection remain unavailable"
            )
        _sha256(self.row_id, label="buyer-cluster diagnostic row ID")
        if self.row_id != hash_payload(
            Form4StockSignalBuyerClusterDiagnosticRow.lineage_payload(self)
        ):
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: buyer-cluster diagnostic row ID is inconsistent"
            )
        _require_zero_authority(self)

    @property
    def stock_key(self) -> tuple[str, str, str]:
        return (self.issuer_cik, self.security_id, self.share_class_id)

    def lineage_payload(self) -> dict[str, object]:
        return {
            "parent_seed_row_id": self.parent_seed_row_id,
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
            "base_diagnostic_seed_selected": (
                self.base_diagnostic_seed_selected
            ),
            "source_formula_diagnostics_id": (
                self.source_formula_diagnostics_id
            ),
            "source_formula_payload_hash": self.source_formula_payload_hash,
            "source_breadth_id": self.source_breadth_id,
            "source_breadth_hash": self.source_breadth_hash,
            "buyer_breadth": self.buyer_breadth,
            "meets_minimum_buyer_breadth": (
                self.meets_minimum_buyer_breadth
            ),
            "cluster_qualified_candidate": self.cluster_qualified_candidate,
            "diagnostic_cluster_seed_selected": (
                self.diagnostic_cluster_seed_selected
            ),
            "stock_score": None,
            "rank": None,
            "seed_selected": None,
            **_ZeroAuthority.authority_payload(self),
        }

    def to_payload(self) -> dict[str, object]:
        Form4StockSignalBuyerClusterDiagnosticRow.__post_init__(
            self,
            _ROW_FACTORY_TOKEN,
        )
        return {
            **Form4StockSignalBuyerClusterDiagnosticRow.lineage_payload(self),
            "row_id": self.row_id,
        }


@dataclass(frozen=True)
class _RowInput:
    seed_row: seed_contract.Form4StockSignalSeedDiagnosticRow
    source: _FormulaReplay | None
    buyer_breadth: int | None
    meets_minimum: bool | None
    candidate: bool


@dataclass(frozen=True)
class _BuyerClusterComputation:
    base_selected_seed_count: int
    buyer_breadth_gate_member_count: int
    cluster_qualified_seed_count: int
    selected_cluster_seed_count: int | None
    outcome: Form4StockSignalBuyerClusterOutcome
    rows: tuple[Form4StockSignalBuyerClusterDiagnosticRow, ...]


def _validate_signal_join(
    observation: normalization_contract.Form4StockSignalNormalizationObservation,
    source: _FormulaReplay,
) -> None:
    diagnostics = source.diagnostics
    if (
        observation.stock_key != source.stock_key
        or diagnostics.identity.diagnostics_id
        != observation.upstream_diagnostics_id
        or source.payload_hash != observation.upstream_payload_hash
        or source.payload_hash != observation.synthetic_source_id
        or diagnostics.identity.builder_git_commit
        != observation.upstream_builder_git_commit
        or diagnostics.identity.diagnostics_version
        != observation.upstream_diagnostics_version
        or diagnostics.identity.numeric_policy_hash
        != observation.upstream_numeric_policy_hash
        or not _exact_replay_equal(
            diagnostics.raw_stock_score_diagnostic,
            observation.raw_stock_score_diagnostic,
        )
    ):
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: IB-3A source does not exactly match IB-3B signal lineage"
        )


def _row_payload(
    *,
    seed_row: seed_contract.Form4StockSignalSeedDiagnosticRow,
    source: _FormulaReplay | None,
    buyer_breadth: int | None,
    meets_minimum: bool | None,
    candidate: bool,
    selected: bool | None,
) -> dict[str, object]:
    diagnostics = None if source is None else source.diagnostics
    return {
        "parent_seed_row_id": seed_row.row_id,
        "issuer_cik": seed_row.issuer_cik,
        "security_id": seed_row.security_id,
        "share_class_id": seed_row.share_class_id,
        "disposition": seed_row.disposition.value,
        "included_in_percentile_denominator": (
            seed_row.included_in_percentile_denominator
        ),
        "exact_ranking_value": (
            None
            if seed_row.exact_ranking_value is None
            else decimal_text(seed_row.exact_ranking_value)
        ),
        "meets_top_decile_cutoff": seed_row.meets_top_decile_cutoff,
        "positive_signal_candidate": seed_row.positive_signal_candidate,
        "base_diagnostic_seed_selected": seed_row.diagnostic_seed_selected,
        "source_formula_diagnostics_id": (
            None if diagnostics is None else diagnostics.identity.diagnostics_id
        ),
        "source_formula_payload_hash": (
            None if source is None else source.payload_hash
        ),
        "source_breadth_id": (
            None if diagnostics is None else diagnostics.breadth.breadth_id
        ),
        "source_breadth_hash": (
            None if diagnostics is None else diagnostics.identity.breadth_hash
        ),
        "buyer_breadth": buyer_breadth,
        "meets_minimum_buyer_breadth": meets_minimum,
        "cluster_qualified_candidate": candidate,
        "diagnostic_cluster_seed_selected": selected,
        "stock_score": None,
        "rank": None,
        "seed_selected": None,
        **_ZeroAuthority().authority_payload(),
    }


def _compute_buyer_cluster_diagnostics(
    seed_parent: seed_contract.Form4StockSignalSeedDiagnostics,
    formula_sources: tuple[_FormulaReplay, ...],
) -> _BuyerClusterComputation:
    _require_frozen_policy()
    normalization = seed_parent.source_normalization
    if (
        type(seed_parent.rows) is not tuple
        or not seed_parent.rows
        or len(seed_parent.rows) > MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_ROWS
        or type(normalization.rows) is not tuple
        or type(normalization.observations) is not tuple
        or len(normalization.rows) != len(seed_parent.rows)
        or len(normalization.observations) != len(seed_parent.rows)
    ):
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: IB-3C parent inventories are inconsistent"
        )
    normalized_by_id = {row.row_id: row for row in normalization.rows}
    observations_by_id = {
        observation.observation_id: observation
        for observation in normalization.observations
    }
    formulas_by_key = {source.stock_key: source for source in formula_sources}
    if (
        len(normalized_by_id) != len(normalization.rows)
        or len(observations_by_id) != len(normalization.observations)
        or len(formulas_by_key) != len(formula_sources)
    ):
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: parent or formula identities are not unique"
        )

    row_inputs: list[_RowInput] = []
    consumed_formula_keys: set[tuple[str, str, str]] = set()
    base_selected_count = 0
    breadth_gate_count = 0
    candidate_count = 0
    for seed_row in seed_parent.rows:
        normalized_row = normalized_by_id.get(seed_row.parent_row_id)
        if normalized_row is None:
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: seed row does not resolve to its normalized parent"
            )
        observation = observations_by_id.get(normalized_row.observation_id)
        if observation is None:
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: normalized row does not resolve to its observation"
            )
        if (
            seed_row.stock_key != normalized_row.stock_key
            or seed_row.stock_key != observation.stock_key
            or seed_row.disposition is not normalized_row.disposition
            or seed_row.disposition is not observation.disposition
        ):
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: IB-3C to IB-3B row lineage is inconsistent"
            )
        if type(seed_row.diagnostic_seed_selected) is not bool:
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: AVAILABLE IB-3C parent requires complete row selection"
            )
        if seed_row.diagnostic_seed_selected:
            base_selected_count += 1

        source: _FormulaReplay | None = None
        buyer_breadth: int | None = None
        meets_minimum: bool | None = None
        if (
            observation.disposition
            is normalization_contract.Form4StockSignalNormalizationDisposition.INCLUDE_SIGNAL
        ):
            source = formulas_by_key.get(observation.stock_key)
            if source is None:
                raise Form4StockSignalBuyerClusterDiagnosticsError(
                    "REFUSED: every IB-3B signal row requires one IB-3A source"
                )
            _validate_signal_join(observation, source)
            consumed_formula_keys.add(source.stock_key)
            buyer_breadth = source.diagnostics.breadth.buyer_breadth
            if type(buyer_breadth) is not int or buyer_breadth < 1:
                raise Form4StockSignalBuyerClusterDiagnosticsError(
                    "REFUSED: replayed IB-3A buyer breadth is invalid"
                )
            meets_minimum = (
                buyer_breadth
                >= FORM4_STOCK_SIGNAL_BUYER_CLUSTER_MINIMUM_BUYER_BREADTH
            )
            if meets_minimum:
                breadth_gate_count += 1
        candidate = bool(
            seed_row.diagnostic_seed_selected and meets_minimum is True
        )
        if candidate:
            candidate_count += 1
        row_inputs.append(
            _RowInput(
                seed_row=seed_row,
                source=source,
                buyer_breadth=buyer_breadth,
                meets_minimum=meets_minimum,
                candidate=candidate,
            )
        )

    if consumed_formula_keys != set(formulas_by_key):
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: IB-3A source inventory contains missing or extra stocks"
        )
    if len(formula_sources) != normalization.identity.signal_count:
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: IB-3A source count does not match every signal row"
        )
    if base_selected_count != seed_parent.selected_seed_count:
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: retained IB-3C selection count is inconsistent"
        )

    if (
        candidate_count
        >= FORM4_STOCK_SIGNAL_BUYER_CLUSTER_MINIMUM_QUALIFIED_SEEDS
    ):
        outcome = Form4StockSignalBuyerClusterOutcome.AVAILABLE
        selected_count: int | None = candidate_count
    else:
        outcome = (
            Form4StockSignalBuyerClusterOutcome.UNAVAILABLE_INSUFFICIENT_BUYER_CLUSTER_SEEDS
        )
        selected_count = None

    rows: list[Form4StockSignalBuyerClusterDiagnosticRow] = []
    for row_input in row_inputs:
        selected = (
            row_input.candidate
            if outcome is Form4StockSignalBuyerClusterOutcome.AVAILABLE
            else None
        )
        payload = _row_payload(
            seed_row=row_input.seed_row,
            source=row_input.source,
            buyer_breadth=row_input.buyer_breadth,
            meets_minimum=row_input.meets_minimum,
            candidate=row_input.candidate,
            selected=selected,
        )
        diagnostics = (
            None if row_input.source is None else row_input.source.diagnostics
        )
        rows.append(
            Form4StockSignalBuyerClusterDiagnosticRow(
                parent_seed_row_id=row_input.seed_row.row_id,
                issuer_cik=row_input.seed_row.issuer_cik,
                security_id=row_input.seed_row.security_id,
                share_class_id=row_input.seed_row.share_class_id,
                disposition=row_input.seed_row.disposition,
                included_in_percentile_denominator=(
                    row_input.seed_row.included_in_percentile_denominator
                ),
                exact_ranking_value=row_input.seed_row.exact_ranking_value,
                meets_top_decile_cutoff=(
                    row_input.seed_row.meets_top_decile_cutoff
                ),
                positive_signal_candidate=(
                    row_input.seed_row.positive_signal_candidate
                ),
                base_diagnostic_seed_selected=(
                    row_input.seed_row.diagnostic_seed_selected
                ),
                source_formula_diagnostics_id=(
                    None
                    if diagnostics is None
                    else diagnostics.identity.diagnostics_id
                ),
                source_formula_payload_hash=(
                    None
                    if row_input.source is None
                    else row_input.source.payload_hash
                ),
                source_breadth_id=(
                    None if diagnostics is None else diagnostics.breadth.breadth_id
                ),
                source_breadth_hash=(
                    None if diagnostics is None else diagnostics.identity.breadth_hash
                ),
                buyer_breadth=row_input.buyer_breadth,
                meets_minimum_buyer_breadth=row_input.meets_minimum,
                cluster_qualified_candidate=row_input.candidate,
                diagnostic_cluster_seed_selected=selected,
                stock_score=None,
                rank=None,
                seed_selected=None,
                row_id=hash_payload(payload),
                _verified_factory_token=_ROW_FACTORY_TOKEN,
            )
        )
    return _BuyerClusterComputation(
        base_selected_seed_count=base_selected_count,
        buyer_breadth_gate_member_count=breadth_gate_count,
        cluster_qualified_seed_count=candidate_count,
        selected_cluster_seed_count=selected_count,
        outcome=outcome,
        rows=tuple(rows),
    )


@dataclass(frozen=True)
class Form4StockSignalBuyerClusterIdentity(_ZeroAuthority):
    """Hash-bound identity for one complete synthetic IB-3D result."""

    diagnostics_version: str
    policy_hash: str
    builder_git_commit: str
    evaluation_session: str
    upstream_seed_diagnostics_id: str
    upstream_seed_payload_hash: str
    upstream_seed_diagnostics_version: str
    upstream_seed_policy_hash: str
    upstream_seed_builder_git_commit: str
    upstream_seed_row_inventory_hash: str
    row_count: int
    signal_source_count: int
    source_event_count: int
    source_formula_inventory_hash: str
    base_selected_seed_count: int
    buyer_breadth_gate_member_count: int
    cluster_qualified_seed_count: int
    selected_cluster_seed_count: int | None
    row_inventory_hash: str
    outcome: Form4StockSignalBuyerClusterOutcome
    buyer_cluster_diagnostics_id: str
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _IDENTITY_FACTORY_TOKEN:
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: buyer-cluster identity must be factory-created"
            )
        _require_frozen_policy()
        if (
            type(self.diagnostics_version) is not str
            or self.diagnostics_version
            != FORM4_STOCK_SIGNAL_BUYER_CLUSTER_DIAGNOSTICS_VERSION
        ):
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: buyer-cluster diagnostics version is inconsistent"
            )
        _sha256(self.policy_hash, label="buyer-cluster policy hash")
        if self.policy_hash != FORM4_STOCK_SIGNAL_BUYER_CLUSTER_POLICY_HASH:
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: buyer-cluster policy hash is inconsistent"
            )
        _builder_commit(self.builder_git_commit)
        _text(self.evaluation_session, label="evaluation session")
        if (
            type(self.upstream_seed_diagnostics_id) is not str
            or _SEED_ID_RE.fullmatch(self.upstream_seed_diagnostics_id) is None
        ):
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: upstream seed diagnostics ID has an invalid shape"
            )
        _sha256(self.upstream_seed_payload_hash, label="upstream seed payload hash")
        _sha256(self.upstream_seed_policy_hash, label="upstream seed policy hash")
        _builder_commit(self.upstream_seed_builder_git_commit)
        _sha256(
            self.upstream_seed_row_inventory_hash,
            label="upstream seed-row inventory hash",
        )
        if (
            type(self.upstream_seed_diagnostics_version) is not str
            or self.upstream_seed_diagnostics_version
            != seed_contract.FORM4_STOCK_SIGNAL_SEED_DIAGNOSTICS_VERSION
            or self.upstream_seed_policy_hash
            != seed_contract.FORM4_STOCK_SIGNAL_SEED_POLICY_HASH
        ):
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: upstream IB-3C policy lineage is inconsistent"
            )
        counts = (
            self.row_count,
            self.signal_source_count,
            self.source_event_count,
            self.base_selected_seed_count,
            self.buyer_breadth_gate_member_count,
            self.cluster_qualified_seed_count,
        )
        if any(type(value) is not int or value < 0 for value in counts):
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: buyer-cluster identity counts must be nonnegative integers"
            )
        if (
            self.row_count < 1
            or self.row_count > MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_ROWS
            or self.signal_source_count < 1
            or self.signal_source_count > self.row_count
            or self.source_event_count < self.signal_source_count
            or self.source_event_count
            > MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_SOURCE_EVENTS
            or self.base_selected_seed_count
            < seed_contract.FORM4_STOCK_SIGNAL_SEED_MINIMUM_POSITIVE_SEEDS
            or self.base_selected_seed_count > self.signal_source_count
            or self.buyer_breadth_gate_member_count > self.signal_source_count
            or self.cluster_qualified_seed_count
            > min(
                self.base_selected_seed_count,
                self.buyer_breadth_gate_member_count,
            )
        ):
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: buyer-cluster identity counts are inconsistent"
            )
        _sha256(
            self.source_formula_inventory_hash,
            label="source formula inventory hash",
        )
        _sha256(self.row_inventory_hash, label="buyer-cluster row inventory hash")
        if type(self.outcome) is not Form4StockSignalBuyerClusterOutcome:
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: buyer-cluster outcome must be an exact enum"
            )
        if self.outcome is Form4StockSignalBuyerClusterOutcome.AVAILABLE:
            if (
                self.cluster_qualified_seed_count
                < FORM4_STOCK_SIGNAL_BUYER_CLUSTER_MINIMUM_QUALIFIED_SEEDS
                or type(self.selected_cluster_seed_count) is not int
                or self.selected_cluster_seed_count
                != self.cluster_qualified_seed_count
            ):
                raise Form4StockSignalBuyerClusterDiagnosticsError(
                    "REFUSED: available buyer-cluster selection violates its minimum"
                )
        elif (
            self.cluster_qualified_seed_count
            >= FORM4_STOCK_SIGNAL_BUYER_CLUSTER_MINIMUM_QUALIFIED_SEEDS
            or self.selected_cluster_seed_count is not None
        ):
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: unavailable buyer-cluster selection is inconsistent"
            )
        _text(self.buyer_cluster_diagnostics_id, label="buyer-cluster diagnostics ID")
        expected_id = (
            "form4-stock-signal-buyer-cluster-diagnostics-"
            f"{hash_payload(Form4StockSignalBuyerClusterIdentity.lineage_payload(self))[:16]}"
        )
        if self.buyer_cluster_diagnostics_id != expected_id:
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: buyer-cluster diagnostics ID is inconsistent"
            )
        _require_zero_authority(self)

    def lineage_payload(self) -> dict[str, object]:
        return {
            "diagnostics_version": self.diagnostics_version,
            "policy_hash": self.policy_hash,
            "builder_git_commit": self.builder_git_commit,
            "evaluation_session": self.evaluation_session,
            "upstream_seed_diagnostics_id": self.upstream_seed_diagnostics_id,
            "upstream_seed_payload_hash": self.upstream_seed_payload_hash,
            "upstream_seed_diagnostics_version": (
                self.upstream_seed_diagnostics_version
            ),
            "upstream_seed_policy_hash": self.upstream_seed_policy_hash,
            "upstream_seed_builder_git_commit": (
                self.upstream_seed_builder_git_commit
            ),
            "upstream_seed_row_inventory_hash": (
                self.upstream_seed_row_inventory_hash
            ),
            "row_count": self.row_count,
            "signal_source_count": self.signal_source_count,
            "source_event_count": self.source_event_count,
            "source_formula_inventory_hash": (
                self.source_formula_inventory_hash
            ),
            "base_selected_seed_count": self.base_selected_seed_count,
            "buyer_breadth_gate_member_count": (
                self.buyer_breadth_gate_member_count
            ),
            "cluster_qualified_seed_count": self.cluster_qualified_seed_count,
            "selected_cluster_seed_count": self.selected_cluster_seed_count,
            "row_inventory_hash": self.row_inventory_hash,
            "outcome": self.outcome.value,
            **_ZeroAuthority.authority_payload(self),
        }

    def to_payload(self) -> dict[str, object]:
        Form4StockSignalBuyerClusterIdentity.__post_init__(
            self,
            _IDENTITY_FACTORY_TOKEN,
        )
        return {
            **Form4StockSignalBuyerClusterIdentity.lineage_payload(self),
            "buyer_cluster_diagnostics_id": self.buyer_cluster_diagnostics_id,
        }


def _build_identity(
    *,
    seed_parent: seed_contract.Form4StockSignalSeedDiagnostics,
    seed_payload_hash: str,
    formula_sources: tuple[_FormulaReplay, ...],
    source_event_count: int,
    source_formula_inventory_hash: str,
    computation: _BuyerClusterComputation,
    builder_git_commit: str,
) -> Form4StockSignalBuyerClusterIdentity:
    row_inventory_hash = hash_payload(
        [
            Form4StockSignalBuyerClusterDiagnosticRow.to_payload(row)
            for row in computation.rows
        ]
    )
    payload = {
        "diagnostics_version": (
            FORM4_STOCK_SIGNAL_BUYER_CLUSTER_DIAGNOSTICS_VERSION
        ),
        "policy_hash": FORM4_STOCK_SIGNAL_BUYER_CLUSTER_POLICY_HASH,
        "builder_git_commit": builder_git_commit,
        "evaluation_session": seed_parent.identity.evaluation_session,
        "upstream_seed_diagnostics_id": (
            seed_parent.identity.seed_diagnostics_id
        ),
        "upstream_seed_payload_hash": seed_payload_hash,
        "upstream_seed_diagnostics_version": (
            seed_parent.identity.diagnostics_version
        ),
        "upstream_seed_policy_hash": seed_parent.identity.policy_hash,
        "upstream_seed_builder_git_commit": (
            seed_parent.identity.builder_git_commit
        ),
        "upstream_seed_row_inventory_hash": (
            seed_parent.identity.row_inventory_hash
        ),
        "row_count": len(computation.rows),
        "signal_source_count": len(formula_sources),
        "source_event_count": source_event_count,
        "source_formula_inventory_hash": source_formula_inventory_hash,
        "base_selected_seed_count": computation.base_selected_seed_count,
        "buyer_breadth_gate_member_count": (
            computation.buyer_breadth_gate_member_count
        ),
        "cluster_qualified_seed_count": (
            computation.cluster_qualified_seed_count
        ),
        "selected_cluster_seed_count": (
            computation.selected_cluster_seed_count
        ),
        "row_inventory_hash": row_inventory_hash,
        "outcome": computation.outcome.value,
        **_ZeroAuthority().authority_payload(),
    }
    return Form4StockSignalBuyerClusterIdentity(
        diagnostics_version=(
            FORM4_STOCK_SIGNAL_BUYER_CLUSTER_DIAGNOSTICS_VERSION
        ),
        policy_hash=FORM4_STOCK_SIGNAL_BUYER_CLUSTER_POLICY_HASH,
        builder_git_commit=builder_git_commit,
        evaluation_session=seed_parent.identity.evaluation_session,
        upstream_seed_diagnostics_id=seed_parent.identity.seed_diagnostics_id,
        upstream_seed_payload_hash=seed_payload_hash,
        upstream_seed_diagnostics_version=(
            seed_parent.identity.diagnostics_version
        ),
        upstream_seed_policy_hash=seed_parent.identity.policy_hash,
        upstream_seed_builder_git_commit=(
            seed_parent.identity.builder_git_commit
        ),
        upstream_seed_row_inventory_hash=(
            seed_parent.identity.row_inventory_hash
        ),
        row_count=len(computation.rows),
        signal_source_count=len(formula_sources),
        source_event_count=source_event_count,
        source_formula_inventory_hash=source_formula_inventory_hash,
        base_selected_seed_count=computation.base_selected_seed_count,
        buyer_breadth_gate_member_count=(
            computation.buyer_breadth_gate_member_count
        ),
        cluster_qualified_seed_count=(
            computation.cluster_qualified_seed_count
        ),
        selected_cluster_seed_count=(
            computation.selected_cluster_seed_count
        ),
        row_inventory_hash=row_inventory_hash,
        outcome=computation.outcome,
        buyer_cluster_diagnostics_id=(
            "form4-stock-signal-buyer-cluster-diagnostics-"
            f"{hash_payload(payload)[:16]}"
        ),
        _verified_factory_token=_IDENTITY_FACTORY_TOKEN,
    )


@dataclass(frozen=True)
class Form4StockSignalBuyerClusterDiagnostics(_ZeroAuthority):
    """Replayable, exhaustive synthetic IB-3D diagnostic evidence."""

    identity: Form4StockSignalBuyerClusterIdentity
    source_seed_diagnostics: seed_contract.Form4StockSignalSeedDiagnostics
    source_formula_diagnostics: tuple[
        formula_contract.Form4StockSignalFormulaDiagnostics, ...
    ]
    rows: tuple[Form4StockSignalBuyerClusterDiagnosticRow, ...]
    outcome: Form4StockSignalBuyerClusterOutcome
    base_selected_seed_count: int
    buyer_breadth_gate_member_count: int
    cluster_qualified_seed_count: int
    selected_cluster_seed_count: int | None
    stock_score: None
    ranking: None
    seed_selection: None
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _RESULT_FACTORY_TOKEN:
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: buyer-cluster diagnostics must be factory-created"
            )
        if type(self.identity) is not Form4StockSignalBuyerClusterIdentity:
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: buyer-cluster diagnostics require an exact identity"
            )
        Form4StockSignalBuyerClusterIdentity.__post_init__(
            self.identity,
            _IDENTITY_FACTORY_TOKEN,
        )
        seed_parent, seed_hash = _replay_available_seed_parent(
            self.source_seed_diagnostics
        )
        formula_replays, source_event_count, formula_inventory_hash = (
            _replay_formula_sources(self.source_formula_diagnostics)
        )
        canonical_sources = tuple(
            source.diagnostics for source in formula_replays
        )
        if not _exact_replay_equal(
            self.source_formula_diagnostics,
            canonical_sources,
        ):
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: stored IB-3A sources are not in canonical stock order"
            )
        computation = _compute_buyer_cluster_diagnostics(
            seed_parent,
            formula_replays,
        )
        if not _exact_replay_equal(self.rows, computation.rows):
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: buyer-cluster rows do not replay from their sources"
            )
        for row in self.rows:
            if type(row) is not Form4StockSignalBuyerClusterDiagnosticRow:
                raise Form4StockSignalBuyerClusterDiagnosticsError(
                    "REFUSED: buyer-cluster rows contain an unexpected type"
                )
            Form4StockSignalBuyerClusterDiagnosticRow.__post_init__(
                row,
                _ROW_FACTORY_TOKEN,
            )
        expected_identity = _build_identity(
            seed_parent=seed_parent,
            seed_payload_hash=seed_hash,
            formula_sources=formula_replays,
            source_event_count=source_event_count,
            source_formula_inventory_hash=formula_inventory_hash,
            computation=computation,
            builder_git_commit=self.identity.builder_git_commit,
        )
        if not _exact_replay_equal(self.identity, expected_identity):
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: buyer-cluster identity does not replay"
            )
        if type(self.outcome) is not Form4StockSignalBuyerClusterOutcome:
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: buyer-cluster outcome must be an exact enum"
            )
        counts = (
            self.base_selected_seed_count,
            self.buyer_breadth_gate_member_count,
            self.cluster_qualified_seed_count,
        )
        if any(type(value) is not int for value in counts):
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: buyer-cluster summary counts must be exact integers"
            )
        if self.selected_cluster_seed_count is not None and type(
            self.selected_cluster_seed_count
        ) is not int:
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: selected cluster count must be an exact integer or unavailable"
            )
        summary = (
            self.outcome,
            self.base_selected_seed_count,
            self.buyer_breadth_gate_member_count,
            self.cluster_qualified_seed_count,
            self.selected_cluster_seed_count,
        )
        expected_summary = (
            computation.outcome,
            computation.base_selected_seed_count,
            computation.buyer_breadth_gate_member_count,
            computation.cluster_qualified_seed_count,
            computation.selected_cluster_seed_count,
        )
        if not _exact_replay_equal(summary, expected_summary):
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: buyer-cluster diagnostics summary is inconsistent"
            )
        if (
            self.stock_score is not None
            or self.ranking is not None
            or self.seed_selection is not None
        ):
            raise Form4StockSignalBuyerClusterDiagnosticsError(
                "REFUSED: canonical score, rank, and seed selection remain unavailable"
            )
        _require_zero_authority(self)

    def to_payload(self) -> dict[str, object]:
        Form4StockSignalBuyerClusterDiagnostics.__post_init__(
            self,
            _RESULT_FACTORY_TOKEN,
        )
        seed_parent, _ = _replay_available_seed_parent(
            self.source_seed_diagnostics
        )
        formula_replays, _, _ = _replay_formula_sources(
            self.source_formula_diagnostics
        )
        return {
            "identity": Form4StockSignalBuyerClusterIdentity.to_payload(
                self.identity
            ),
            "source_seed_diagnostics": (
                seed_contract.Form4StockSignalSeedDiagnostics.to_payload(
                    seed_parent
                )
            ),
            "source_formula_diagnostics": [
                formula_contract.Form4StockSignalFormulaDiagnostics.to_payload(
                    source.diagnostics
                )
                for source in formula_replays
            ],
            "rows": [
                Form4StockSignalBuyerClusterDiagnosticRow.to_payload(row)
                for row in self.rows
            ],
            "outcome": self.outcome.value,
            "base_selected_seed_count": self.base_selected_seed_count,
            "buyer_breadth_gate_member_count": (
                self.buyer_breadth_gate_member_count
            ),
            "cluster_qualified_seed_count": (
                self.cluster_qualified_seed_count
            ),
            "selected_cluster_seed_count": self.selected_cluster_seed_count,
            "stock_score": None,
            "ranking": None,
            "seed_selection": None,
            **_ZeroAuthority.authority_payload(self),
        }


def build_form4_stock_signal_buyer_cluster_diagnostics(
    source_seed_diagnostics: seed_contract.Form4StockSignalSeedDiagnostics,
    source_formula_diagnostics: tuple[
        formula_contract.Form4StockSignalFormulaDiagnostics, ...
    ],
    *,
    builder_git_commit: str,
) -> Form4StockSignalBuyerClusterDiagnostics:
    """Build one bounded synthetic IB-3D diagnostic from exact IB-3C/IB-3A sources."""

    builder_git_commit = _builder_commit(builder_git_commit)
    _require_frozen_policy()
    seed_parent, seed_hash = _replay_available_seed_parent(
        source_seed_diagnostics
    )
    formula_replays, source_event_count, formula_inventory_hash = (
        _replay_formula_sources(source_formula_diagnostics)
    )
    computation = _compute_buyer_cluster_diagnostics(
        seed_parent,
        formula_replays,
    )
    identity = _build_identity(
        seed_parent=seed_parent,
        seed_payload_hash=seed_hash,
        formula_sources=formula_replays,
        source_event_count=source_event_count,
        source_formula_inventory_hash=formula_inventory_hash,
        computation=computation,
        builder_git_commit=builder_git_commit,
    )
    canonical_sources = tuple(source.diagnostics for source in formula_replays)
    result = Form4StockSignalBuyerClusterDiagnostics(
        identity=identity,
        source_seed_diagnostics=seed_parent,
        source_formula_diagnostics=canonical_sources,
        rows=computation.rows,
        outcome=computation.outcome,
        base_selected_seed_count=computation.base_selected_seed_count,
        buyer_breadth_gate_member_count=(
            computation.buyer_breadth_gate_member_count
        ),
        cluster_qualified_seed_count=(
            computation.cluster_qualified_seed_count
        ),
        selected_cluster_seed_count=(
            computation.selected_cluster_seed_count
        ),
        stock_score=None,
        ranking=None,
        seed_selection=None,
        _verified_factory_token=_RESULT_FACTORY_TOKEN,
    )

    final_seed, final_seed_hash = _replay_available_seed_parent(
        source_seed_diagnostics
    )
    final_formulas, final_event_count, final_inventory_hash = (
        _replay_formula_sources(source_formula_diagnostics)
    )
    if (
        not _exact_replay_equal(final_seed, seed_parent)
        or final_seed_hash != seed_hash
        or not _exact_replay_equal(final_formulas, formula_replays)
        or final_event_count != source_event_count
        or final_inventory_hash != formula_inventory_hash
    ):
        raise Form4StockSignalBuyerClusterDiagnosticsError(
            "REFUSED: an IB-3C or IB-3A source changed during evaluation"
        )
    return result


__all__ = [
    "FORM4_STOCK_SIGNAL_BUYER_CLUSTER_BUYER_ID_POLICY",
    "FORM4_STOCK_SIGNAL_BUYER_CLUSTER_DIAGNOSTICS_VERSION",
    "FORM4_STOCK_SIGNAL_BUYER_CLUSTER_MINIMUM_BUYER_BREADTH",
    "FORM4_STOCK_SIGNAL_BUYER_CLUSTER_MINIMUM_QUALIFIED_SEEDS",
    "FORM4_STOCK_SIGNAL_BUYER_CLUSTER_POLICY_HASH",
    "FORM4_STOCK_SIGNAL_BUYER_CLUSTER_SELECTION_POLICY",
    "FORM4_STOCK_SIGNAL_BUYER_CLUSTER_SOURCE_POLICY",
    "MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_ROWS",
    "MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_SOURCE_EVENTS",
    "MAX_FORM4_STOCK_SIGNAL_BUYER_CLUSTER_TEXT_CHARACTERS",
    "Form4StockSignalBuyerClusterDiagnosticRow",
    "Form4StockSignalBuyerClusterDiagnostics",
    "Form4StockSignalBuyerClusterDiagnosticsError",
    "Form4StockSignalBuyerClusterIdentity",
    "Form4StockSignalBuyerClusterOutcome",
    "build_form4_stock_signal_buyer_cluster_diagnostics",
]
