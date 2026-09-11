"""Synthetic-only, zero-authority IB-3A stock-signal formula diagnostics.

This module pins the blueprint's event-size, freshness, event-score, raw-score,
and four breadth equations against factory-created synthetic fixtures.  It is
not a consumer of IB-2D and cannot promote provisional Form 4 groups into
canonical events.  Cross-sectional winsorization, z-scoring, seed selection,
outcomes, ETF construction, QC, deployment, and trading remain unavailable.
"""
from __future__ import annotations

import re
import threading
import weakref
from collections import defaultdict
from dataclasses import InitVar, dataclass, fields
from datetime import date
from decimal import Context, Decimal, DecimalException, ROUND_HALF_EVEN, localcontext

from data.financial_primitives import (
    decimal_text,
    exact_decimal_add,
    exact_decimal_multiply,
    exact_decimal_subtract,
    exact_decimal_sum,
)
from data.hashing import hash_payload
from research.insider_buying.contracts import CANONICAL_SPEC
from research.insider_buying.form4_provisional_lot_diagnostics import (
    Form4ProvisionalLotDiagnostics,
)


FORM4_STOCK_SIGNAL_FORMULA_DIAGNOSTICS_VERSION = (
    "INSETF-IB3A-FORM4-STOCK-SIGNAL-FORMULA-DIAGNOSTICS-v1"
)
FORM4_STOCK_SIGNAL_MINIMUM_PURCHASE_VALUE_USD = Decimal("50000")
FORM4_STOCK_SIGNAL_HALF_LIFE_TRADING_DAYS = 20
FORM4_STOCK_SIGNAL_LOOKBACK_TRADING_DAYS = 30
FORM4_STOCK_SIGNAL_DECIMAL_PRECISION = 50
FORM4_STOCK_SIGNAL_DECIMAL_ROUNDING = "ROUND_HALF_EVEN"
FORM4_STOCK_SIGNAL_SIZE_FORMULA = "ln(1 + purchase_value_usd / 50000)"
FORM4_STOCK_SIGNAL_FRESHNESS_FORMULA = (
    "exp(-ln(2) * age_trading_days / 20)"
)
FORM4_STOCK_SIGNAL_FRESHNESS_EVALUATION = (
    "exact whole half-lives times a 50-digit fractional-half-life projection"
)
FORM4_STOCK_SIGNAL_EVENT_SCORE_FORMULA = "event_size * freshness"
FORM4_STOCK_SIGNAL_RAW_SCORE_FORMULA = (
    "sum(event_score for value >= 50000 and 0 <= age_trading_days <= 30)"
)
FORM4_STOCK_SIGNAL_DOLLAR_BREADTH_FORMULA = (
    "(total_purchase_value - largest_buyer_purchase_value) / total_purchase_value"
)
MAX_FORM4_STOCK_SIGNAL_EVENTS = 10_000
MAX_FORM4_STOCK_SIGNAL_ROLES_PER_EVENT = 16
MAX_FORM4_STOCK_SIGNAL_TEXT_CHARACTERS = 128
MAX_FORM4_STOCK_SIGNAL_AGE_TRADING_DAYS = 10_000
MAX_FORM4_STOCK_SIGNAL_PROJECTION_NODES = 4_000_000
MAX_FORM4_STOCK_SIGNAL_PROJECTION_DEPTH = 32

_MAX_FORM4_STOCK_SIGNAL_DECIMAL_DIGITS = 256
_MAX_FORM4_STOCK_SIGNAL_DECIMAL_ABS_EXPONENT = 256
_MAX_FORM4_STOCK_SIGNAL_AGGREGATE_DECIMAL_DIGITS = (
    _MAX_FORM4_STOCK_SIGNAL_DECIMAL_DIGITS
    + (2 * _MAX_FORM4_STOCK_SIGNAL_DECIMAL_ABS_EXPONENT)
    + len(str(MAX_FORM4_STOCK_SIGNAL_EVENTS))
    + 1
)
_MAX_FORM4_STOCK_SIGNAL_DERIVED_DECIMAL_ABS_EXPONENT = 1_024
_MAX_FORM4_STOCK_SIGNAL_DECIMAL_TEXT_CHARACTERS = 2_048
_CIK_RE = re.compile(r"^[0-9]{10}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_ROLE_RE = re.compile(r"^[a-z][a-z0-9._:-]{0,63}$")
_FIXTURE_EVENT_FACTORY_TOKEN = object()
_CONTRIBUTION_FACTORY_TOKEN = object()
_BREADTH_FACTORY_TOKEN = object()
_IDENTITY_FACTORY_TOKEN = object()
_RESULT_FACTORY_TOKEN = object()


class Form4StockSignalFormulaDiagnosticsError(ValueError):
    """A bounded synthetic IB-3A formula contract failed closed."""


def _numeric_policy_payload() -> dict[str, object]:
    return {
        "decimal_precision": FORM4_STOCK_SIGNAL_DECIMAL_PRECISION,
        "decimal_rounding": FORM4_STOCK_SIGNAL_DECIMAL_ROUNDING,
        "decimal_emin": -999_999,
        "decimal_emax": 999_999,
        "decimal_capitals": 1,
        "decimal_clamp": 0,
        "decimal_traps": [],
        "size_formula": FORM4_STOCK_SIGNAL_SIZE_FORMULA,
        "freshness_formula": FORM4_STOCK_SIGNAL_FRESHNESS_FORMULA,
        "freshness_evaluation": FORM4_STOCK_SIGNAL_FRESHNESS_EVALUATION,
        "event_score_formula": FORM4_STOCK_SIGNAL_EVENT_SCORE_FORMULA,
        "raw_score_formula": FORM4_STOCK_SIGNAL_RAW_SCORE_FORMULA,
        "dollar_breadth_formula": FORM4_STOCK_SIGNAL_DOLLAR_BREADTH_FORMULA,
        "minimum_purchase_value_usd": decimal_text(
            FORM4_STOCK_SIGNAL_MINIMUM_PURCHASE_VALUE_USD
        ),
        "lot_aggregation_key": list(CANONICAL_SPEC.lot_aggregation_key),
        "minimum_purchase_value_applies_after_aggregation": (
            CANONICAL_SPEC.minimum_purchase_value_applies_after_aggregation
        ),
        "half_life_trading_days": FORM4_STOCK_SIGNAL_HALF_LIFE_TRADING_DAYS,
        "lookback_max_age_trading_days": (
            FORM4_STOCK_SIGNAL_LOOKBACK_TRADING_DAYS
        ),
        "resource_bounds": {
            "events": MAX_FORM4_STOCK_SIGNAL_EVENTS,
            "roles_per_event": MAX_FORM4_STOCK_SIGNAL_ROLES_PER_EVENT,
            "text_characters": MAX_FORM4_STOCK_SIGNAL_TEXT_CHARACTERS,
            "age_trading_days": MAX_FORM4_STOCK_SIGNAL_AGE_TRADING_DAYS,
            "projection_nodes": MAX_FORM4_STOCK_SIGNAL_PROJECTION_NODES,
            "projection_depth": MAX_FORM4_STOCK_SIGNAL_PROJECTION_DEPTH,
            "input_decimal_digits": _MAX_FORM4_STOCK_SIGNAL_DECIMAL_DIGITS,
            "aggregate_decimal_digits": (
                _MAX_FORM4_STOCK_SIGNAL_AGGREGATE_DECIMAL_DIGITS
            ),
            "input_decimal_abs_exponent": (
                _MAX_FORM4_STOCK_SIGNAL_DECIMAL_ABS_EXPONENT
            ),
            "derived_decimal_abs_exponent": (
                _MAX_FORM4_STOCK_SIGNAL_DERIVED_DECIMAL_ABS_EXPONENT
            ),
            "decimal_text_characters": (
                _MAX_FORM4_STOCK_SIGNAL_DECIMAL_TEXT_CHARACTERS
            ),
        },
    }


FORM4_STOCK_SIGNAL_NUMERIC_POLICY_HASH = hash_payload(_numeric_policy_payload())


def _new_decimal_context() -> Context:
    return Context(
        prec=FORM4_STOCK_SIGNAL_DECIMAL_PRECISION,
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
        CANONICAL_SPEC.minimum_purchase_value_usd
        != FORM4_STOCK_SIGNAL_MINIMUM_PURCHASE_VALUE_USD
        or CANONICAL_SPEC.decay_half_life_trading_days
        != FORM4_STOCK_SIGNAL_HALF_LIFE_TRADING_DAYS
        or CANONICAL_SPEC.lookback_trading_days
        != FORM4_STOCK_SIGNAL_LOOKBACK_TRADING_DAYS
        or CANONICAL_SPEC.lot_aggregation_key
        != (
            "reporting_owner_identity",
            "security_identity",
            "transaction_date",
        )
        or CANONICAL_SPEC.minimum_purchase_value_applies_after_aggregation
        is not True
        or CANONICAL_SPEC.score_formula != FORM4_STOCK_SIGNAL_SIZE_FORMULA
        or CANONICAL_SPEC.outcomes_authorized is not False
        or CANONICAL_SPEC.authorized_outcome_looks != 0
        or hash_payload(_numeric_policy_payload())
        != FORM4_STOCK_SIGNAL_NUMERIC_POLICY_HASH
    ):
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: frozen IB-3A numeric policy is inconsistent"
        )


def _text(value: object, *, label: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or not value.isprintable()
        or len(value) > MAX_FORM4_STOCK_SIGNAL_TEXT_CHARACTERS
    ):
        raise Form4StockSignalFormulaDiagnosticsError(
            f"REFUSED: {label} must be bounded canonical text"
        )
    return value


def _sha256(value: object, *, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise Form4StockSignalFormulaDiagnosticsError(
            f"REFUSED: {label} must be lowercase SHA-256"
        )
    return value


def _decimal(
    value: object,
    *,
    label: str,
    max_digits: int = _MAX_FORM4_STOCK_SIGNAL_DECIMAL_DIGITS,
    max_abs_exponent: int = _MAX_FORM4_STOCK_SIGNAL_DECIMAL_ABS_EXPONENT,
) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise Form4StockSignalFormulaDiagnosticsError(
            f"REFUSED: {label} must be an exact finite Decimal"
        )
    decimal_tuple = value.as_tuple()
    if (
        len(decimal_tuple.digits) > max_digits
        or abs(int(decimal_tuple.exponent))
        > max_abs_exponent
    ):
        raise Form4StockSignalFormulaDiagnosticsError(
            f"REFUSED: {label} exceeds the Decimal resource bound"
        )
    return value


def _age(value: object) -> int:
    if (
        type(value) is not int
        or value < 0
        or value > MAX_FORM4_STOCK_SIGNAL_AGE_TRADING_DAYS
    ):
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: age_trading_days must be a bounded nonnegative exact integer"
        )
    return value


def _role_inventory(value: object) -> tuple[str, ...]:
    if (
        type(value) is not tuple
        or not value
        or len(value) > MAX_FORM4_STOCK_SIGNAL_ROLES_PER_EVENT
        or any(
            type(item) is not str or _ROLE_RE.fullmatch(item) is None
            for item in value
        )
        or value != tuple(sorted(set(value)))
    ):
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: normalized role IDs must be a sorted unique bounded tuple"
        )
    return value


def _runtime_value(value: object) -> object:
    if type(value) is Decimal:
        decimal_tuple = value.as_tuple()
        return {
            "type": "Decimal",
            "sign": decimal_tuple.sign,
            "digits": list(decimal_tuple.digits),
            "exponent": int(decimal_tuple.exponent),
        }
    if type(value) is date:
        return {"type": "date", "value": value.isoformat()}
    if type(value) is tuple:
        return {
            "type": "tuple",
            "items": [_runtime_value(item) for item in value],
        }
    if value is None:
        return {"type": "NoneType", "value": None}
    if type(value) in {str, bool, int}:
        return {"type": type(value).__name__, "value": value}
    return {"type": type(value).__name__, "representation": repr(value)}


def _runtime_fingerprint(value: object) -> str:
    return hash_payload(
        {
            "type": f"{type(value).__module__}.{type(value).__qualname__}",
            "fields": {
                item.name: _runtime_value(getattr(value, item.name))
                for item in fields(type(value))
            },
        }
    )


@dataclass
class _ProjectionBudget:
    nodes: int = 0


def _project_output(
    value: object,
    *,
    budget: _ProjectionBudget | None = None,
    depth: int = 0,
    active: set[int] | None = None,
) -> object:
    """Project diagnostic payloads into a bounded hash-safe representation."""

    if budget is None:
        budget = _ProjectionBudget()
    if active is None:
        active = set()
    if depth > MAX_FORM4_STOCK_SIGNAL_PROJECTION_DEPTH:
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: output projection exceeds the depth bound"
        )
    budget.nodes += 1
    if budget.nodes > MAX_FORM4_STOCK_SIGNAL_PROJECTION_NODES:
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: output projection exceeds the node bound"
        )
    if value is None or type(value) in {bool, int}:
        return value
    if type(value) is str:
        return _text(value, label="projected text")
    if type(value) is Decimal:
        projected = decimal_text(
            _decimal(
                value,
                label="projected Decimal",
                max_digits=_MAX_FORM4_STOCK_SIGNAL_AGGREGATE_DECIMAL_DIGITS,
                max_abs_exponent=(
                    _MAX_FORM4_STOCK_SIGNAL_DERIVED_DECIMAL_ABS_EXPONENT
                ),
            )
        )
        if len(projected) > _MAX_FORM4_STOCK_SIGNAL_DECIMAL_TEXT_CHARACTERS:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: projected Decimal text exceeds the numeric bound"
            )
        return projected
    if type(value) is date:
        return value.isoformat()

    identity = id(value)
    if identity in active:
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: output projection contains a cycle"
        )
    if type(value) in {tuple, list}:
        active.add(identity)
        try:
            return [
                _project_output(
                    item,
                    budget=budget,
                    depth=depth + 1,
                    active=active,
                )
                for item in value
            ]
        finally:
            active.remove(identity)
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: output projection contains a non-text key"
            )
        active.add(identity)
        try:
            return {
                _text(key, label="projected mapping key"): _project_output(
                    value[key],
                    budget=budget,
                    depth=depth + 1,
                    active=active,
                )
                for key in sorted(value)
            }
        finally:
            active.remove(identity)
    raise Form4StockSignalFormulaDiagnosticsError(
        f"REFUSED: unsupported output projection type {type(value).__name__}"
    )


class _ZeroAuthority:
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
            "role_ids_are_caller_declared": True,
            "role_normalization_verified": False,
            "role_normalization_authorized": False,
            "ib2_completion_authorized": False,
            "official_security_master_compatibility_verified": False,
            "qc_symbol_id_mapping_verified": False,
            "authenticated_amendment_supersession_verified": False,
            "calendar_session_mapping_verified": False,
            "point_in_time_issuer_identity_verified": False,
            "point_in_time_reporting_owner_identity_verified": False,
            "point_in_time_security_identity_verified": False,
            "point_in_time_transaction_identity_verified": False,
            "ordinary_equity_classification_verified": False,
            "canonical_filter_authorized": False,
            "deduplication_authorized": False,
            "lot_aggregation_authorized": False,
            "post_aggregation_minimum_gate_authorized": False,
            "canonical_stock_score_authorized": False,
            "cross_sectional_normalization_authorized": False,
            "seed_signal_authorized": False,
            "sec_access_authorized": False,
            "provider_access_authorized": False,
            "outcomes_authorized": False,
            "etf_construction_authorized": False,
            "qc_execution_authorized": False,
            "broker_access_authorized": False,
            "deployment_authorized": False,
            "trading_authorized": False,
            "authorized_outcome_looks": 0,
            "consumed_outcome_looks": 0,
        }


@dataclass(frozen=True)
class Form4StockSignalFixtureEvent(_ZeroAuthority):
    """One caller-declared synthetic event used only to test IB-3A equations."""

    source_event_id: str
    issuer_cik: str
    security_id: str
    share_class_id: str
    buyer_id: str
    transaction_date: date
    purchase_value_usd: Decimal
    age_trading_days: int
    normalized_role_ids: tuple[str, ...]
    fixture_event_id: str
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _FIXTURE_EVENT_FACTORY_TOKEN:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: stock-signal fixture event must be factory-created"
            )
        _sha256(self.source_event_id, label="source event ID")
        if type(self.issuer_cik) is not str or _CIK_RE.fullmatch(self.issuer_cik) is None:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: fixture issuer CIK must contain ten digits"
            )
        _text(self.security_id, label="fixture security ID")
        _text(self.share_class_id, label="fixture share-class ID")
        _text(self.buyer_id, label="fixture buyer ID")
        if type(self.transaction_date) is not date:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: fixture transaction date must be an exact date"
            )
        purchase_value = _decimal(
            self.purchase_value_usd,
            label="fixture purchase value",
        )
        if purchase_value <= 0:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: fixture purchase value must be positive"
            )
        _age(self.age_trading_days)
        _role_inventory(self.normalized_role_ids)
        _sha256(self.fixture_event_id, label="fixture event ID")
        if self.fixture_event_id != hash_payload(
            _project_output(self.lineage_payload())
        ):
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: fixture event ID is inconsistent"
            )

    def lineage_payload(self) -> dict[str, object]:
        return {
            "source_kind": "synthetic_offline_fixture",
            "source_event_id": self.source_event_id,
            "issuer_cik": self.issuer_cik,
            "security_id": self.security_id,
            "share_class_id": self.share_class_id,
            "buyer_id": self.buyer_id,
            "transaction_date": self.transaction_date.isoformat(),
            "purchase_value_usd": self.purchase_value_usd,
            "age_trading_days": self.age_trading_days,
            "normalized_role_ids": list(self.normalized_role_ids),
            **self.authority_payload(),
        }

    def to_payload(self) -> dict[str, object]:
        projected = _project_output(
            {**self.lineage_payload(), "fixture_event_id": self.fixture_event_id}
        )
        if type(projected) is not dict:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: fixture-event payload projection is invalid"
            )
        return projected


_EVENT_REGISTRY: dict[
    int, tuple[weakref.ReferenceType[Form4StockSignalFixtureEvent], str]
] = {}
_EVENT_REGISTRY_LOCK = threading.RLock()


def _register_fixture_event(value: Form4StockSignalFixtureEvent) -> None:
    identity = id(value)
    fingerprint = _runtime_fingerprint(value)

    def remove(reference: weakref.ReferenceType[Form4StockSignalFixtureEvent]) -> None:
        with _EVENT_REGISTRY_LOCK:
            current = _EVENT_REGISTRY.get(identity)
            if current is not None and current[0] is reference:
                _EVENT_REGISTRY.pop(identity, None)

    reference = weakref.ref(value, remove)
    with _EVENT_REGISTRY_LOCK:
        _EVENT_REGISTRY[identity] = (reference, fingerprint)


def _require_factory_fixture_event(value: object) -> str:
    if type(value) is not Form4StockSignalFixtureEvent:
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: inputs must contain exact synthetic fixture events"
        )
    Form4StockSignalFixtureEvent.__post_init__(
        value,
        _FIXTURE_EVENT_FACTORY_TOKEN,
    )
    actual = _runtime_fingerprint(value)
    with _EVENT_REGISTRY_LOCK:
        registered = _EVENT_REGISTRY.get(id(value))
        if (
            registered is None
            or registered[0]() is not value
            or registered[1] != actual
        ):
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: synthetic fixture event is unsealed or mutated"
            )
    return actual


def _post_lot_aggregation_key(
    event: Form4StockSignalFixtureEvent,
) -> tuple[str, str, str, str, date]:
    return (
        event.issuer_cik,
        event.security_id,
        event.share_class_id,
        event.buyer_id,
        event.transaction_date,
    )


def build_form4_stock_signal_fixture_event(
    *,
    source_event_id: str,
    issuer_cik: str,
    security_id: str,
    share_class_id: str,
    buyer_id: str,
    transaction_date: date,
    purchase_value_usd: Decimal,
    age_trading_days: int,
    normalized_role_ids: tuple[str, ...],
) -> Form4StockSignalFixtureEvent:
    """Build one sealed synthetic event without granting input authority."""

    _sha256(source_event_id, label="source event ID")
    if type(issuer_cik) is not str or _CIK_RE.fullmatch(issuer_cik) is None:
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: fixture issuer CIK must contain ten digits"
        )
    _text(security_id, label="fixture security ID")
    _text(share_class_id, label="fixture share-class ID")
    _text(buyer_id, label="fixture buyer ID")
    if type(transaction_date) is not date:
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: fixture transaction date must be an exact date"
        )
    purchase_value = _decimal(
        purchase_value_usd,
        label="fixture purchase value",
    )
    if purchase_value <= 0:
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: fixture purchase value must be positive"
        )
    _age(age_trading_days)
    roles = _role_inventory(normalized_role_ids)
    payload = {
        "source_kind": "synthetic_offline_fixture",
        "source_event_id": source_event_id,
        "issuer_cik": issuer_cik,
        "security_id": security_id,
        "share_class_id": share_class_id,
        "buyer_id": buyer_id,
        "transaction_date": transaction_date.isoformat(),
        "purchase_value_usd": purchase_value,
        "age_trading_days": age_trading_days,
        "normalized_role_ids": list(roles),
        **_ZeroAuthority().authority_payload(),
    }
    value = Form4StockSignalFixtureEvent(
        source_event_id=source_event_id,
        issuer_cik=issuer_cik,
        security_id=security_id,
        share_class_id=share_class_id,
        buyer_id=buyer_id,
        transaction_date=transaction_date,
        purchase_value_usd=purchase_value_usd,
        age_trading_days=age_trading_days,
        normalized_role_ids=normalized_role_ids,
        fixture_event_id=hash_payload(_project_output(payload)),
        _verified_factory_token=_FIXTURE_EVENT_FACTORY_TOKEN,
    )
    _register_fixture_event(value)
    return value


def _event_formula(
    purchase_value_usd: Decimal,
    age_trading_days: int,
) -> tuple[Decimal, Decimal, Decimal]:
    """Evaluate the three blueprint equations under the frozen policy."""

    _require_frozen_policy()
    purchase_value = _decimal(
        purchase_value_usd,
        label="formula purchase value",
    )
    if purchase_value <= 0:
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: formula purchase value must be positive"
        )
    age = _age(age_trading_days)
    try:
        scaled_purchase = exact_decimal_multiply(
            purchase_value,
            Decimal("0.00002"),
            name="IB-3A scaled purchase value",
        )
        size_argument = exact_decimal_add(
            Decimal("1"),
            scaled_purchase,
            name="IB-3A size logarithm argument",
        )
        whole_half_lives, remainder_days = divmod(
            age,
            FORM4_STOCK_SIGNAL_HALF_LIFE_TRADING_DAYS,
        )
        with localcontext(_new_decimal_context()):
            event_size = size_argument.ln()
            exact_half_lives = Decimal("0.5") ** whole_half_lives
            if remainder_days:
                fractional_half_life = (
                    -Decimal("2").ln()
                    * Decimal(remainder_days)
                    / Decimal(FORM4_STOCK_SIGNAL_HALF_LIFE_TRADING_DAYS)
                ).exp()
            else:
                fractional_half_life = Decimal("1")
            freshness = exact_half_lives * fractional_half_life
            event_score = event_size * freshness
    except (DecimalException, ValueError) as exc:
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: IB-3A event formula cannot be evaluated deterministically"
        ) from exc
    if not all(
        value.is_finite() and value >= 0
        for value in (event_size, freshness, event_score)
    ):
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: IB-3A event formula produced an invalid value"
        )
    return event_size, freshness, event_score


@dataclass(frozen=True)
class Form4StockSignalEventContribution(_ZeroAuthority):
    """One retained synthetic event and its formula-only contribution."""

    source_event_id: str
    fixture_event_id: str
    purchase_value_usd: Decimal
    age_trading_days: int
    event_size: Decimal
    freshness: Decimal
    event_score: Decimal
    meets_minimum_purchase_value: bool
    inside_lookback: bool
    included_in_raw_score: bool
    contribution_id: str
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _CONTRIBUTION_FACTORY_TOKEN:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: event contribution must be factory-created"
            )
        _sha256(self.source_event_id, label="contribution source event ID")
        _sha256(self.fixture_event_id, label="contribution fixture event ID")
        purchase_value = _decimal(
            self.purchase_value_usd,
            label="contribution purchase value",
        )
        if purchase_value <= 0:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: contribution purchase value must be positive"
            )
        age = _age(self.age_trading_days)
        expected_size, expected_freshness, expected_score = _event_formula(
            purchase_value,
            age,
        )
        for name, actual, expected in (
            ("event size", self.event_size, expected_size),
            ("freshness", self.freshness, expected_freshness),
            ("event score", self.event_score, expected_score),
        ):
            if _decimal(
                actual,
                label=name,
                max_abs_exponent=(
                    _MAX_FORM4_STOCK_SIGNAL_DERIVED_DECIMAL_ABS_EXPONENT
                ),
            ) != expected:
                raise Form4StockSignalFormulaDiagnosticsError(
                    f"REFUSED: contribution {name} is inconsistent"
                )
        expected_minimum = (
            purchase_value >= FORM4_STOCK_SIGNAL_MINIMUM_PURCHASE_VALUE_USD
        )
        expected_lookback = age <= FORM4_STOCK_SIGNAL_LOOKBACK_TRADING_DAYS
        expected_included = expected_minimum and expected_lookback
        if (
            type(self.meets_minimum_purchase_value) is not bool
            or self.meets_minimum_purchase_value is not expected_minimum
            or type(self.inside_lookback) is not bool
            or self.inside_lookback is not expected_lookback
            or type(self.included_in_raw_score) is not bool
            or self.included_in_raw_score is not expected_included
        ):
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: contribution threshold or lookback routing is inconsistent"
            )
        _sha256(self.contribution_id, label="contribution ID")
        if self.contribution_id != hash_payload(_project_output(self.lineage_payload())):
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: contribution ID is inconsistent"
            )

    def lineage_payload(self) -> dict[str, object]:
        return {
            "source_event_id": self.source_event_id,
            "fixture_event_id": self.fixture_event_id,
            "purchase_value_usd": self.purchase_value_usd,
            "age_trading_days": self.age_trading_days,
            "event_size": self.event_size,
            "freshness": self.freshness,
            "event_score": self.event_score,
            "meets_minimum_purchase_value": self.meets_minimum_purchase_value,
            "inside_lookback": self.inside_lookback,
            "included_in_raw_score": self.included_in_raw_score,
            **self.authority_payload(),
        }

    def to_payload(self) -> dict[str, object]:
        projected = _project_output(
            {**self.lineage_payload(), "contribution_id": self.contribution_id}
        )
        if type(projected) is not dict:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: contribution payload projection is invalid"
            )
        return projected


def _build_contribution(
    event: Form4StockSignalFixtureEvent,
) -> Form4StockSignalEventContribution:
    event_size, freshness, event_score = _event_formula(
        event.purchase_value_usd,
        event.age_trading_days,
    )
    meets_minimum = (
        event.purchase_value_usd
        >= FORM4_STOCK_SIGNAL_MINIMUM_PURCHASE_VALUE_USD
    )
    inside_lookback = (
        event.age_trading_days <= FORM4_STOCK_SIGNAL_LOOKBACK_TRADING_DAYS
    )
    payload = {
        "source_event_id": event.source_event_id,
        "fixture_event_id": event.fixture_event_id,
        "purchase_value_usd": event.purchase_value_usd,
        "age_trading_days": event.age_trading_days,
        "event_size": event_size,
        "freshness": freshness,
        "event_score": event_score,
        "meets_minimum_purchase_value": meets_minimum,
        "inside_lookback": inside_lookback,
        "included_in_raw_score": meets_minimum and inside_lookback,
        **event.authority_payload(),
    }
    return Form4StockSignalEventContribution(
        source_event_id=event.source_event_id,
        fixture_event_id=event.fixture_event_id,
        purchase_value_usd=event.purchase_value_usd,
        age_trading_days=event.age_trading_days,
        event_size=event_size,
        freshness=freshness,
        event_score=event_score,
        meets_minimum_purchase_value=meets_minimum,
        inside_lookback=inside_lookback,
        included_in_raw_score=meets_minimum and inside_lookback,
        contribution_id=hash_payload(_project_output(payload)),
        _verified_factory_token=_CONTRIBUTION_FACTORY_TOKEN,
    )


def _dollar_breadth(
    total_purchase_value_usd: Decimal,
    largest_buyer_purchase_value_usd: Decimal,
) -> Decimal:
    total = _decimal(
        total_purchase_value_usd,
        label="breadth total purchase value",
        max_digits=_MAX_FORM4_STOCK_SIGNAL_AGGREGATE_DECIMAL_DIGITS,
    )
    largest = _decimal(
        largest_buyer_purchase_value_usd,
        label="breadth largest-buyer purchase value",
        max_digits=_MAX_FORM4_STOCK_SIGNAL_AGGREGATE_DECIMAL_DIGITS,
    )
    if total <= 0 or largest <= 0 or largest > total:
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: breadth purchase-value totals are inconsistent"
        )
    try:
        numerator = exact_decimal_subtract(
            total,
            largest,
            name="IB-3A dollar-breadth numerator",
        )
        with localcontext(_new_decimal_context()):
            result = numerator / total
    except (DecimalException, ValueError) as exc:
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: dollar breadth cannot be evaluated deterministically"
        ) from exc
    if not result.is_finite() or result < 0 or result >= 1:
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: dollar breadth is outside the expected interval"
        )
    return result


@dataclass(frozen=True)
class Form4StockSignalBreadthDiagnostics(_ZeroAuthority):
    """Separate non-scoring breadth diagnostics for qualifying events."""

    included_event_count: int
    unique_buyer_ids: tuple[str, ...]
    buyer_breadth: int
    normalized_role_ids: tuple[str, ...]
    role_breadth: int
    transaction_dates: tuple[date, ...]
    date_breadth: int
    total_purchase_value_usd: Decimal
    largest_buyer_purchase_value_usd: Decimal
    dollar_breadth: Decimal
    breadth_id: str
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _BREADTH_FACTORY_TOKEN:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: breadth diagnostics must be factory-created"
            )
        if (
            type(self.included_event_count) is not int
            or self.included_event_count < 1
            or self.included_event_count > MAX_FORM4_STOCK_SIGNAL_EVENTS
        ):
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: breadth requires at least one included event"
            )
        if (
            type(self.unique_buyer_ids) is not tuple
            or not self.unique_buyer_ids
            or self.unique_buyer_ids
            != tuple(sorted(set(self.unique_buyer_ids)))
            or any(
                _text(value, label="breadth buyer ID") != value
                for value in self.unique_buyer_ids
            )
        ):
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: breadth buyer inventory must be sorted and unique"
            )
        if (
            type(self.normalized_role_ids) is not tuple
            or not self.normalized_role_ids
            or self.normalized_role_ids
            != tuple(sorted(set(self.normalized_role_ids)))
            or any(
                type(value) is not str or _ROLE_RE.fullmatch(value) is None
                for value in self.normalized_role_ids
            )
        ):
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: breadth role inventory must be sorted and unique"
            )
        if (
            type(self.transaction_dates) is not tuple
            or not self.transaction_dates
            or self.transaction_dates
            != tuple(sorted(set(self.transaction_dates)))
            or any(type(value) is not date for value in self.transaction_dates)
        ):
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: breadth date inventory must be sorted and unique"
            )
        for name, actual, expected in (
            ("buyer", self.buyer_breadth, len(self.unique_buyer_ids)),
            ("role", self.role_breadth, len(self.normalized_role_ids)),
            ("date", self.date_breadth, len(self.transaction_dates)),
        ):
            if type(actual) is not int or actual != expected:
                raise Form4StockSignalFormulaDiagnosticsError(
                    f"REFUSED: {name} breadth count is inconsistent"
                )
        if self.buyer_breadth > self.included_event_count:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: buyer breadth exceeds included event count"
            )
        if (
            self.role_breadth
            > self.included_event_count * MAX_FORM4_STOCK_SIGNAL_ROLES_PER_EVENT
            or self.date_breadth > self.included_event_count
        ):
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: breadth role or date cardinality exceeds per-event bounds"
            )
        expected_dollar_breadth = _dollar_breadth(
            self.total_purchase_value_usd,
            self.largest_buyer_purchase_value_usd,
        )
        minimum_total_purchase_value = exact_decimal_multiply(
            FORM4_STOCK_SIGNAL_MINIMUM_PURCHASE_VALUE_USD,
            self.included_event_count,
            name="IB-3A minimum breadth total purchase value",
        )
        if (
            self.total_purchase_value_usd < minimum_total_purchase_value
            or self.largest_buyer_purchase_value_usd
            < FORM4_STOCK_SIGNAL_MINIMUM_PURCHASE_VALUE_USD
            or (
                self.buyer_breadth == 1
                and self.largest_buyer_purchase_value_usd
                != self.total_purchase_value_usd
            )
            or (
                self.buyer_breadth > 1
                and self.largest_buyer_purchase_value_usd
                >= self.total_purchase_value_usd
            )
        ):
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: breadth values cannot arise from qualifying buyers"
            )
        if (
            _decimal(
                self.dollar_breadth,
                label="dollar breadth",
                max_abs_exponent=(
                    _MAX_FORM4_STOCK_SIGNAL_DERIVED_DECIMAL_ABS_EXPONENT
                ),
            )
            != expected_dollar_breadth
        ):
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: dollar breadth is inconsistent"
            )
        _sha256(self.breadth_id, label="breadth ID")
        if self.breadth_id != hash_payload(_project_output(self.lineage_payload())):
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: breadth ID is inconsistent"
            )

    def lineage_payload(self) -> dict[str, object]:
        return {
            "included_event_count": self.included_event_count,
            "unique_buyer_ids": list(self.unique_buyer_ids),
            "buyer_breadth": self.buyer_breadth,
            "normalized_role_ids": list(self.normalized_role_ids),
            "role_breadth": self.role_breadth,
            "transaction_dates": [value.isoformat() for value in self.transaction_dates],
            "date_breadth": self.date_breadth,
            "total_purchase_value_usd": self.total_purchase_value_usd,
            "largest_buyer_purchase_value_usd": (
                self.largest_buyer_purchase_value_usd
            ),
            "dollar_breadth": self.dollar_breadth,
            **self.authority_payload(),
        }

    def to_payload(self) -> dict[str, object]:
        projected = _project_output(
            {**self.lineage_payload(), "breadth_id": self.breadth_id}
        )
        if type(projected) is not dict:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: breadth payload projection is invalid"
            )
        return projected


def _build_breadth(
    events: tuple[Form4StockSignalFixtureEvent, ...],
    contributions: tuple[Form4StockSignalEventContribution, ...],
) -> Form4StockSignalBreadthDiagnostics:
    included_events = tuple(
        event
        for event, contribution in zip(events, contributions, strict=True)
        if contribution.included_in_raw_score
    )
    if not included_events:
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: at least one qualifying event must be included in the raw score"
        )
    unique_buyers = tuple(sorted({event.buyer_id for event in included_events}))
    normalized_roles = tuple(
        sorted(
            {
                role
                for event in included_events
                for role in event.normalized_role_ids
            }
        )
    )
    transaction_dates = tuple(
        sorted({event.transaction_date for event in included_events})
    )
    total_purchase_value = exact_decimal_sum(
        (event.purchase_value_usd for event in included_events),
        name="IB-3A breadth total purchase value",
    )
    purchase_value_by_buyer: dict[str, list[Decimal]] = defaultdict(list)
    for event in included_events:
        purchase_value_by_buyer[event.buyer_id].append(event.purchase_value_usd)
    buyer_totals = tuple(
        exact_decimal_sum(
            purchase_value_by_buyer[buyer_id],
            name=f"IB-3A purchase value for buyer {buyer_id}",
        )
        for buyer_id in sorted(purchase_value_by_buyer)
    )
    largest_buyer_purchase_value = max(buyer_totals)
    dollar_breadth = _dollar_breadth(
        total_purchase_value,
        largest_buyer_purchase_value,
    )
    payload = {
        "included_event_count": len(included_events),
        "unique_buyer_ids": list(unique_buyers),
        "buyer_breadth": len(unique_buyers),
        "normalized_role_ids": list(normalized_roles),
        "role_breadth": len(normalized_roles),
        "transaction_dates": [value.isoformat() for value in transaction_dates],
        "date_breadth": len(transaction_dates),
        "total_purchase_value_usd": total_purchase_value,
        "largest_buyer_purchase_value_usd": largest_buyer_purchase_value,
        "dollar_breadth": dollar_breadth,
        **_ZeroAuthority().authority_payload(),
    }
    return Form4StockSignalBreadthDiagnostics(
        included_event_count=len(included_events),
        unique_buyer_ids=unique_buyers,
        buyer_breadth=len(unique_buyers),
        normalized_role_ids=normalized_roles,
        role_breadth=len(normalized_roles),
        transaction_dates=transaction_dates,
        date_breadth=len(transaction_dates),
        total_purchase_value_usd=total_purchase_value,
        largest_buyer_purchase_value_usd=largest_buyer_purchase_value,
        dollar_breadth=dollar_breadth,
        breadth_id=hash_payload(_project_output(payload)),
        _verified_factory_token=_BREADTH_FACTORY_TOKEN,
    )


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


def _authority_payload_from(value: object) -> dict[str, object]:
    return {
        "role_ids_are_caller_declared": getattr(
            value,
            "role_ids_are_caller_declared",
        ),
        **{name: getattr(value, name) for name in _BOOLEAN_AUTHORITY_FIELDS},
        "authorized_outcome_looks": getattr(value, "authorized_outcome_looks"),
        "consumed_outcome_looks": getattr(value, "consumed_outcome_looks"),
    }


def _require_zero_authority(value: object) -> None:
    if getattr(value, "role_ids_are_caller_declared") is not True:
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: IB-3A role IDs must remain explicitly caller-declared"
        )
    if any(type(getattr(value, name)) is not bool for name in _BOOLEAN_AUTHORITY_FIELDS):
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: every IB-3A authority flag must be an exact boolean"
        )
    if any(getattr(value, name) is not False for name in _BOOLEAN_AUTHORITY_FIELDS):
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: IB-3A formula diagnostics cannot grant authority"
        )
    for name in ("authorized_outcome_looks", "consumed_outcome_looks"):
        look_count = getattr(value, name)
        if type(look_count) is not int or look_count != 0:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: IB-3A formula diagnostics require exactly zero outcome looks"
            )


@dataclass(frozen=True)
class Form4StockSignalFormulaIdentity:
    """Hash-bound identity for one synthetic IB-3A diagnostic batch."""

    diagnostics_version: str
    numeric_policy_hash: str
    builder_git_commit: str
    issuer_cik: str
    security_id: str
    share_class_id: str
    fixture_event_count: int
    contribution_count: int
    included_event_count: int
    fixture_event_inventory_hash: str
    contribution_inventory_hash: str
    breadth_hash: str
    raw_stock_score_diagnostic: Decimal
    role_ids_are_caller_declared: bool
    role_normalization_verified: bool
    role_normalization_authorized: bool
    ib2_completion_authorized: bool
    official_security_master_compatibility_verified: bool
    qc_symbol_id_mapping_verified: bool
    authenticated_amendment_supersession_verified: bool
    calendar_session_mapping_verified: bool
    point_in_time_issuer_identity_verified: bool
    point_in_time_reporting_owner_identity_verified: bool
    point_in_time_security_identity_verified: bool
    point_in_time_transaction_identity_verified: bool
    ordinary_equity_classification_verified: bool
    canonical_filter_authorized: bool
    deduplication_authorized: bool
    lot_aggregation_authorized: bool
    post_aggregation_minimum_gate_authorized: bool
    canonical_stock_score_authorized: bool
    cross_sectional_normalization_authorized: bool
    seed_signal_authorized: bool
    sec_access_authorized: bool
    provider_access_authorized: bool
    outcomes_authorized: bool
    etf_construction_authorized: bool
    qc_execution_authorized: bool
    broker_access_authorized: bool
    deployment_authorized: bool
    trading_authorized: bool
    authorized_outcome_looks: int
    consumed_outcome_looks: int
    diagnostics_id: str
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _IDENTITY_FACTORY_TOKEN:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: formula identity must be factory-created"
            )
        if (
            type(self.diagnostics_version) is not str
            or self.diagnostics_version
            != FORM4_STOCK_SIGNAL_FORMULA_DIAGNOSTICS_VERSION
        ):
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: formula identity version is inconsistent"
            )
        _sha256(self.numeric_policy_hash, label="formula numeric-policy hash")
        if self.numeric_policy_hash != FORM4_STOCK_SIGNAL_NUMERIC_POLICY_HASH:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: formula identity numeric policy is inconsistent"
            )
        if (
            type(self.builder_git_commit) is not str
            or _GIT_COMMIT_RE.fullmatch(self.builder_git_commit) is None
        ):
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: builder Git commit must be lowercase full SHA-1"
            )
        if type(self.issuer_cik) is not str or _CIK_RE.fullmatch(self.issuer_cik) is None:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: formula identity issuer CIK must contain ten digits"
            )
        _text(self.security_id, label="formula identity security ID")
        _text(self.share_class_id, label="formula identity share-class ID")
        if (
            type(self.fixture_event_count) is not int
            or type(self.contribution_count) is not int
            or type(self.included_event_count) is not int
            or self.fixture_event_count < 1
            or self.fixture_event_count > MAX_FORM4_STOCK_SIGNAL_EVENTS
            or self.contribution_count != self.fixture_event_count
            or not 1 <= self.included_event_count <= self.fixture_event_count
        ):
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: formula identity counts are inconsistent"
            )
        _sha256(
            self.fixture_event_inventory_hash,
            label="fixture event inventory hash",
        )
        _sha256(
            self.contribution_inventory_hash,
            label="contribution inventory hash",
        )
        _sha256(self.breadth_hash, label="breadth hash")
        raw_score = _decimal(
            self.raw_stock_score_diagnostic,
            label="raw stock-score diagnostic",
            max_digits=_MAX_FORM4_STOCK_SIGNAL_AGGREGATE_DECIMAL_DIGITS,
        )
        if raw_score <= 0:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: raw stock-score diagnostic must be positive"
            )
        _require_zero_authority(self)
        expected_id = (
            "form4-stock-signal-formula-diagnostics-"
            f"{hash_payload(_project_output(self.lineage_payload()))[:16]}"
        )
        if type(self.diagnostics_id) is not str or self.diagnostics_id != expected_id:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: formula diagnostics ID is inconsistent"
            )

    def authority_payload(self) -> dict[str, object]:
        return _authority_payload_from(self)

    def lineage_payload(self) -> dict[str, object]:
        return {
            "diagnostics_version": self.diagnostics_version,
            "numeric_policy_hash": self.numeric_policy_hash,
            "builder_git_commit": self.builder_git_commit,
            "issuer_cik": self.issuer_cik,
            "security_id": self.security_id,
            "share_class_id": self.share_class_id,
            "fixture_event_count": self.fixture_event_count,
            "contribution_count": self.contribution_count,
            "included_event_count": self.included_event_count,
            "fixture_event_inventory_hash": self.fixture_event_inventory_hash,
            "contribution_inventory_hash": self.contribution_inventory_hash,
            "breadth_hash": self.breadth_hash,
            "raw_stock_score_diagnostic": self.raw_stock_score_diagnostic,
            **self.authority_payload(),
        }

    def to_payload(self) -> dict[str, object]:
        projected = _project_output(
            {**self.lineage_payload(), "diagnostics_id": self.diagnostics_id}
        )
        if type(projected) is not dict:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: identity payload projection is invalid"
            )
        return projected


def _build_identity(
    *,
    events: tuple[Form4StockSignalFixtureEvent, ...],
    contributions: tuple[Form4StockSignalEventContribution, ...],
    breadth: Form4StockSignalBreadthDiagnostics,
    raw_stock_score_diagnostic: Decimal,
    builder_git_commit: str,
) -> Form4StockSignalFormulaIdentity:
    authority = _ZeroAuthority().authority_payload()
    fixture_event_inventory_hash = hash_payload(
        _project_output(
            [
                {
                    **event.lineage_payload(),
                    "fixture_event_id": event.fixture_event_id,
                }
                for event in events
            ]
        )
    )
    contribution_inventory_hash = hash_payload(
        _project_output(
            [
                {
                    **contribution.lineage_payload(),
                    "contribution_id": contribution.contribution_id,
                }
                for contribution in contributions
            ]
        )
    )
    breadth_hash = hash_payload(
        _project_output(
            {**breadth.lineage_payload(), "breadth_id": breadth.breadth_id}
        )
    )
    payload = {
        "diagnostics_version": FORM4_STOCK_SIGNAL_FORMULA_DIAGNOSTICS_VERSION,
        "numeric_policy_hash": FORM4_STOCK_SIGNAL_NUMERIC_POLICY_HASH,
        "builder_git_commit": builder_git_commit,
        "issuer_cik": events[0].issuer_cik,
        "security_id": events[0].security_id,
        "share_class_id": events[0].share_class_id,
        "fixture_event_count": len(events),
        "contribution_count": len(contributions),
        "included_event_count": breadth.included_event_count,
        "fixture_event_inventory_hash": fixture_event_inventory_hash,
        "contribution_inventory_hash": contribution_inventory_hash,
        "breadth_hash": breadth_hash,
        "raw_stock_score_diagnostic": raw_stock_score_diagnostic,
        **authority,
    }
    return Form4StockSignalFormulaIdentity(
        diagnostics_version=FORM4_STOCK_SIGNAL_FORMULA_DIAGNOSTICS_VERSION,
        numeric_policy_hash=FORM4_STOCK_SIGNAL_NUMERIC_POLICY_HASH,
        builder_git_commit=builder_git_commit,
        issuer_cik=events[0].issuer_cik,
        security_id=events[0].security_id,
        share_class_id=events[0].share_class_id,
        fixture_event_count=len(events),
        contribution_count=len(contributions),
        included_event_count=breadth.included_event_count,
        fixture_event_inventory_hash=fixture_event_inventory_hash,
        contribution_inventory_hash=contribution_inventory_hash,
        breadth_hash=breadth_hash,
        raw_stock_score_diagnostic=raw_stock_score_diagnostic,
        **authority,
        diagnostics_id=(
            "form4-stock-signal-formula-diagnostics-"
            f"{hash_payload(_project_output(payload))[:16]}"
        ),
        _verified_factory_token=_IDENTITY_FACTORY_TOKEN,
    )


@dataclass(frozen=True)
class Form4StockSignalFormulaDiagnostics(_ZeroAuthority):
    """Replayable synthetic evidence for the bounded IB-3A equations."""

    identity: Form4StockSignalFormulaIdentity
    events: tuple[Form4StockSignalFixtureEvent, ...]
    contributions: tuple[Form4StockSignalEventContribution, ...]
    breadth: Form4StockSignalBreadthDiagnostics
    issuer_cik: str
    raw_stock_score_diagnostic: Decimal
    security_id: str
    share_class_id: str
    stock_score: None
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _RESULT_FACTORY_TOKEN:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: formula diagnostics must be factory-created"
            )
        if type(self.identity) is not Form4StockSignalFormulaIdentity:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: formula diagnostics require an exact identity"
            )
        Form4StockSignalFormulaIdentity.__post_init__(
            self.identity,
            _IDENTITY_FACTORY_TOKEN,
        )
        if (
            type(self.events) is not tuple
            or not self.events
            or len(self.events) > MAX_FORM4_STOCK_SIGNAL_EVENTS
            or type(self.contributions) is not tuple
            or len(self.contributions) != len(self.events)
        ):
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: formula diagnostics require aligned nonempty tuples"
            )
        event_source_ids: list[str] = []
        fixture_event_ids: list[str] = []
        for event in self.events:
            _require_factory_fixture_event(event)
            event_source_ids.append(event.source_event_id)
            fixture_event_ids.append(event.fixture_event_id)
        if (
            event_source_ids != sorted(event_source_ids)
            or len(set(event_source_ids)) != len(event_source_ids)
            or len(set(fixture_event_ids)) != len(fixture_event_ids)
        ):
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: events must have unique IDs in canonical order"
            )
        aggregation_keys = tuple(
            _post_lot_aggregation_key(event) for event in self.events
        )
        if len(set(aggregation_keys)) != len(aggregation_keys):
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: duplicate post-lot aggregation key must be combined before formulas"
            )
        contribution_source_ids: list[str] = []
        contribution_ids: list[str] = []
        for contribution in self.contributions:
            if type(contribution) is not Form4StockSignalEventContribution:
                raise Form4StockSignalFormulaDiagnosticsError(
                    "REFUSED: contribution tuple contains an unexpected type"
                )
            Form4StockSignalEventContribution.__post_init__(
                contribution,
                _CONTRIBUTION_FACTORY_TOKEN,
            )
            contribution_source_ids.append(contribution.source_event_id)
            contribution_ids.append(contribution.contribution_id)
        if (
            contribution_source_ids != event_source_ids
            or len(set(contribution_ids)) != len(contribution_ids)
        ):
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: contributions are not uniquely aligned with events"
            )
        expected_contributions = tuple(
            _build_contribution(event) for event in self.events
        )
        if self.contributions != expected_contributions:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: contributions do not replay from their fixture events"
            )
        stock_keys = {
            (event.issuer_cik, event.security_id, event.share_class_id)
            for event in self.events
        }
        if len(stock_keys) != 1:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: one diagnostic batch must contain one issuer, security, and share class"
            )
        stock_key = next(iter(stock_keys))
        _text(self.security_id, label="result security ID")
        _text(self.share_class_id, label="result share-class ID")
        if (
            type(self.issuer_cik) is not str
            or self.issuer_cik != stock_key[0]
            or self.security_id != stock_key[1]
            or self.share_class_id != stock_key[2]
        ):
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: result stock key is inconsistent"
            )
        expected_raw_score = exact_decimal_sum(
            (
                contribution.event_score
                for contribution in self.contributions
                if contribution.included_in_raw_score
            ),
            name="IB-3A raw stock-score diagnostic",
        )
        if expected_raw_score <= 0:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: at least one qualifying event must enter the raw score"
            )
        if (
            _decimal(
                self.raw_stock_score_diagnostic,
                label="result raw stock-score diagnostic",
                max_digits=_MAX_FORM4_STOCK_SIGNAL_AGGREGATE_DECIMAL_DIGITS,
            )
            != expected_raw_score
        ):
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: result raw stock-score diagnostic is inconsistent"
            )
        if type(self.breadth) is not Form4StockSignalBreadthDiagnostics:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: formula diagnostics require exact breadth diagnostics"
            )
        Form4StockSignalBreadthDiagnostics.__post_init__(
            self.breadth,
            _BREADTH_FACTORY_TOKEN,
        )
        expected_breadth = _build_breadth(self.events, self.contributions)
        if self.breadth != expected_breadth:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: breadth diagnostics do not replay from included events"
            )
        expected_identity = _build_identity(
            events=self.events,
            contributions=self.contributions,
            breadth=self.breadth,
            raw_stock_score_diagnostic=expected_raw_score,
            builder_git_commit=self.identity.builder_git_commit,
        )
        if self.identity != expected_identity:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: formula diagnostics identity does not replay"
            )
        if self.stock_score is not None:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: canonical stock score remains unavailable"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "identity": self.identity.to_payload(),
            "events": [event.to_payload() for event in self.events],
            "contributions": [
                contribution.to_payload() for contribution in self.contributions
            ],
            "breadth": self.breadth.to_payload(),
            "issuer_cik": self.issuer_cik,
            "raw_stock_score_diagnostic": decimal_text(
                self.raw_stock_score_diagnostic
            ),
            "security_id": self.security_id,
            "share_class_id": self.share_class_id,
            "stock_score": None,
            **self.authority_payload(),
        }


def build_form4_stock_signal_formula_diagnostics(
    events: tuple[Form4StockSignalFixtureEvent, ...] | Form4ProvisionalLotDiagnostics,
    *,
    builder_git_commit: str,
) -> Form4StockSignalFormulaDiagnostics:
    """Build synthetic formula evidence without consuming or promoting IB-2D."""

    if type(events) is Form4ProvisionalLotDiagnostics:
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: provisional IB-2D diagnostics cannot enter synthetic IB-3A formulas"
        )
    if type(events) is not tuple:
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: synthetic fixture events must be supplied as an exact tuple"
        )
    if (
        type(MAX_FORM4_STOCK_SIGNAL_EVENTS) is not int
        or MAX_FORM4_STOCK_SIGNAL_EVENTS < 1
        or len(events) > MAX_FORM4_STOCK_SIGNAL_EVENTS
    ):
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: synthetic event count exceeds the event-count bound"
        )
    if not events:
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: at least one synthetic fixture event is required"
        )
    if (
        type(builder_git_commit) is not str
        or _GIT_COMMIT_RE.fullmatch(builder_git_commit) is None
    ):
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: builder Git commit must be lowercase full SHA-1"
        )
    _require_frozen_policy()

    fingerprints_by_identity: dict[int, str] = {}
    for event in events:
        fingerprint = _require_factory_fixture_event(event)
        fingerprints_by_identity[id(event)] = fingerprint
    ordered_events = tuple(sorted(events, key=lambda event: event.source_event_id))
    source_event_ids = tuple(event.source_event_id for event in ordered_events)
    fixture_event_ids = tuple(event.fixture_event_id for event in ordered_events)
    if (
        len(set(source_event_ids)) != len(source_event_ids)
        or len(set(fixture_event_ids)) != len(fixture_event_ids)
    ):
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: synthetic event source and fixture IDs must be unique"
        )
    aggregation_keys = tuple(
        _post_lot_aggregation_key(event) for event in ordered_events
    )
    if len(set(aggregation_keys)) != len(aggregation_keys):
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: duplicate post-lot aggregation key must be combined before formulas"
        )
    stock_keys = {
        (event.issuer_cik, event.security_id, event.share_class_id)
        for event in ordered_events
    }
    if len(stock_keys) != 1:
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: one diagnostic batch must contain one issuer, security, and share class"
        )

    contributions = tuple(_build_contribution(event) for event in ordered_events)
    if not any(
        contribution.included_in_raw_score for contribution in contributions
    ):
        raise Form4StockSignalFormulaDiagnosticsError(
            "REFUSED: at least one qualifying event must be included in the raw score"
        )
    raw_stock_score_diagnostic = exact_decimal_sum(
        (
            contribution.event_score
            for contribution in contributions
            if contribution.included_in_raw_score
        ),
        name="IB-3A raw stock-score diagnostic",
    )
    breadth = _build_breadth(ordered_events, contributions)
    identity = _build_identity(
        events=ordered_events,
        contributions=contributions,
        breadth=breadth,
        raw_stock_score_diagnostic=raw_stock_score_diagnostic,
        builder_git_commit=builder_git_commit,
    )
    stock_key = next(iter(stock_keys))
    result = Form4StockSignalFormulaDiagnostics(
        identity=identity,
        events=ordered_events,
        contributions=contributions,
        breadth=breadth,
        issuer_cik=stock_key[0],
        raw_stock_score_diagnostic=raw_stock_score_diagnostic,
        security_id=stock_key[1],
        share_class_id=stock_key[2],
        stock_score=None,
        _verified_factory_token=_RESULT_FACTORY_TOKEN,
    )
    for event in ordered_events:
        if _require_factory_fixture_event(event) != fingerprints_by_identity[id(event)]:
            raise Form4StockSignalFormulaDiagnosticsError(
                "REFUSED: synthetic fixture event changed during formula evaluation"
            )
    return result


__all__ = [
    "FORM4_STOCK_SIGNAL_DECIMAL_PRECISION",
    "FORM4_STOCK_SIGNAL_DECIMAL_ROUNDING",
    "FORM4_STOCK_SIGNAL_DOLLAR_BREADTH_FORMULA",
    "FORM4_STOCK_SIGNAL_EVENT_SCORE_FORMULA",
    "FORM4_STOCK_SIGNAL_FORMULA_DIAGNOSTICS_VERSION",
    "FORM4_STOCK_SIGNAL_FRESHNESS_EVALUATION",
    "FORM4_STOCK_SIGNAL_FRESHNESS_FORMULA",
    "FORM4_STOCK_SIGNAL_HALF_LIFE_TRADING_DAYS",
    "FORM4_STOCK_SIGNAL_LOOKBACK_TRADING_DAYS",
    "FORM4_STOCK_SIGNAL_MINIMUM_PURCHASE_VALUE_USD",
    "FORM4_STOCK_SIGNAL_NUMERIC_POLICY_HASH",
    "FORM4_STOCK_SIGNAL_RAW_SCORE_FORMULA",
    "FORM4_STOCK_SIGNAL_SIZE_FORMULA",
    "MAX_FORM4_STOCK_SIGNAL_AGE_TRADING_DAYS",
    "MAX_FORM4_STOCK_SIGNAL_EVENTS",
    "MAX_FORM4_STOCK_SIGNAL_PROJECTION_DEPTH",
    "MAX_FORM4_STOCK_SIGNAL_PROJECTION_NODES",
    "MAX_FORM4_STOCK_SIGNAL_ROLES_PER_EVENT",
    "MAX_FORM4_STOCK_SIGNAL_TEXT_CHARACTERS",
    "Form4StockSignalBreadthDiagnostics",
    "Form4StockSignalEventContribution",
    "Form4StockSignalFixtureEvent",
    "Form4StockSignalFormulaDiagnostics",
    "Form4StockSignalFormulaDiagnosticsError",
    "Form4StockSignalFormulaIdentity",
    "build_form4_stock_signal_fixture_event",
    "build_form4_stock_signal_formula_diagnostics",
]
