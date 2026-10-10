"""Deterministic synthetic-only SI-5 order-event accounting.

This module proves order-accounting mechanics without accepting caller market
rows, selecting a lookback, opening an outcome look, or authorizing a real
backtest.  The public entry point runs one content-addressed built-in fixture.
The private kernel exists for focused dangerous-direction tests and accepts
only the exact synthetic contracts defined here.

The empirical SI-5 protocol deliberately retains ``terminal_value_rule=None``
and ``order_cashflow_rule=None``.  Nothing in this module fills those fields or
claims that a provider can supply the canonical events exercised below.
"""
from __future__ import annotations

import dataclasses
import json
import re
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from enum import Enum
from fractions import Fraction
from typing import Any

from data.financial_primitives import (
    decimal_text,
    exact_decimal_add,
)
from data.hashing import canonical_json, hash_payload
from research.short_interest_etf.contracts import (
    SourceEntitlement,
    parse_utc_timestamp,
)
from research.short_interest_etf.si5_offline_protocol import (
    SI5_OFFLINE_PROTOCOL,
    SI5_OFFLINE_PROTOCOL_SHA256,
    require_si5_offline_protocol,
)
from research.short_interest_etf.si5_synthetic_policy import (
    SI5_SYNTHETIC_POLICY_SHA256,
    synthetic_policy_payload,
)


SI5_SYNTHETIC_ORDER_VERSION = "si5-synthetic-order-events-v1"
SI5_SYNTHETIC_ORDER_SCENARIO_ID = "si5-synthetic-order-accounting-v1"
_SYNTHETIC_SOURCE_ID = "synthetic-si5-order-events-v1"
_ALLOWED_COST_BPS = (0, 5, 10, 20)
_PRIMARY_COST_BPS = 10
_COST_SENSITIVITIES_BPS = (0, 5, 20)
_MAX_DECIMAL_TEXT = 128
_MAX_EVENTS = 256
_MAX_SECURITIES = 64
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DECIMAL_RE = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")


class SI5SyntheticOrderError(ValueError):
    """A synthetic order contract or authenticated result failed closed."""


def _refuse(detail: str) -> SI5SyntheticOrderError:
    return SI5SyntheticOrderError(f"REFUSED: {detail}")


def _checked_text(value: Any, name: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise _refuse(f"{name} must be canonical non-empty text")
    return value


def _checked_sha256(value: Any, name: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise _refuse(f"{name} must be a lowercase SHA-256 digest")
    return value


def _checked_timestamp(value: Any, name: str):
    try:
        return parse_utc_timestamp(value, name)
    except (TypeError, ValueError) as exc:
        raise _refuse(str(exc)) from exc


def _canonical_decimal(value: Any, name: str, *, positive: bool) -> Decimal:
    """Parse bounded canonical decimal text without ambient-context arithmetic."""

    if (
        type(value) is not str
        or not value
        or len(value) > _MAX_DECIMAL_TEXT
        or _DECIMAL_RE.fullmatch(value) is None
    ):
        qualifier = "positive" if positive else "nonnegative"
        raise _refuse(f"{name} must be canonical {qualifier} decimal text")
    try:
        parsed = Decimal(value)
        # The exact helper deliberately ignores a caller's Decimal context.  It
        # also bounds pathological coefficients before Fraction conversion.
        parsed = exact_decimal_add(parsed, Decimal("0"), name=name)
    except (InvalidOperation, ValueError) as exc:
        raise _refuse(f"{name} must be canonical finite decimal text") from exc
    if not parsed.is_finite() or (parsed <= 0 if positive else parsed < 0):
        qualifier = "positive" if positive else "nonnegative"
        raise _refuse(f"{name} must be {qualifier}")
    if decimal_text(parsed) != value:
        raise _refuse(f"{name} must use canonical decimal spelling")
    return parsed


def _as_fraction(value: str, name: str, *, positive: bool) -> Fraction:
    parsed = _canonical_decimal(value, name, positive=positive)
    return Fraction(parsed)


def _fraction_payload(value: Fraction) -> dict[str, int]:
    if type(value) is not Fraction:
        raise _refuse("accounting value must be an exact Fraction")
    return {"numerator": value.numerator, "denominator": value.denominator}


def _event_payload(event: "_SyntheticEvent") -> dict[str, Any]:
    return {
        "at": event.at,
        "cash_per_share_usd": event.cash_per_share_usd,
        "dividend_id": event.dividend_id,
        "event_id": event.event_id,
        "fill_denominator": event.fill_denominator,
        "fill_numerator": event.fill_numerator,
        "kind": event.kind.value,
        "raw_open_usd": event.raw_open_usd,
        "security_identity_sha256": event.security_identity_sha256,
        "split_denominator": event.split_denominator,
        "split_numerator": event.split_numerator,
    }


class _SyntheticEventKind(str, Enum):
    OPEN = "open"
    SPLIT = "split"
    DIVIDEND_ENTITLEMENT = "dividend_entitlement"
    DIVIDEND_PAYMENT = "dividend_payment"
    TERMINAL_CASH = "terminal_cash"
    SUSPENSION = "suspension"
    UNKNOWN_TERMINAL = "unknown_terminal"


@dataclasses.dataclass(frozen=True, slots=True)
class _SyntheticEvent:
    event_id: str
    security_identity_sha256: str
    at: str
    kind: _SyntheticEventKind
    raw_open_usd: str | None = None
    split_numerator: int | None = None
    split_denominator: int | None = None
    dividend_id: str | None = None
    cash_per_share_usd: str | None = None
    fill_numerator: int = 1
    fill_denominator: int = 1

    def __post_init__(self) -> None:
        if type(self) is not _SyntheticEvent:
            raise _refuse("event must be the exact _SyntheticEvent type")
        _checked_text(self.event_id, "event_id")
        _checked_sha256(
            self.security_identity_sha256, "security_identity_sha256"
        )
        _checked_timestamp(self.at, "event.at")
        if type(self.kind) is not _SyntheticEventKind:
            raise _refuse("event kind must be the exact _SyntheticEventKind type")
        if (
            type(self.fill_numerator) is not int
            or type(self.fill_denominator) is not int
            or self.fill_numerator <= 0
            or self.fill_denominator <= 0
            or self.fill_numerator > self.fill_denominator
        ):
            raise _refuse("fill fraction must be an exact value in (0, 1]")
        fill = Fraction(self.fill_numerator, self.fill_denominator)
        if (fill.numerator, fill.denominator) != (
            self.fill_numerator,
            self.fill_denominator,
        ):
            raise _refuse("fill fraction must be reduced")

        if self.kind is _SyntheticEventKind.OPEN:
            _canonical_decimal(self.raw_open_usd, "raw_open_usd", positive=True)
            if any(
                value is not None
                for value in (
                    self.split_numerator,
                    self.split_denominator,
                    self.dividend_id,
                    self.cash_per_share_usd,
                )
            ):
                raise _refuse("open event contains a non-open field")
            return

        if self.fill_numerator != 1 or self.fill_denominator != 1:
            raise _refuse("only open events may carry a fill fraction")
        if self.raw_open_usd is not None:
            raise _refuse("non-open event cannot carry raw_open_usd")

        if self.kind is _SyntheticEventKind.SPLIT:
            if (
                type(self.split_numerator) is not int
                or type(self.split_denominator) is not int
                or self.split_numerator <= 0
                or self.split_denominator <= 0
            ):
                raise _refuse("split ratio requires positive exact integers")
            split = Fraction(self.split_numerator, self.split_denominator)
            if (split.numerator, split.denominator) != (
                self.split_numerator,
                self.split_denominator,
            ):
                raise _refuse("split ratio must be reduced")
            if self.dividend_id is not None or self.cash_per_share_usd is not None:
                raise _refuse("split event contains a cashflow field")
            return

        if self.split_numerator is not None or self.split_denominator is not None:
            raise _refuse("non-split event cannot carry a split ratio")

        if self.kind is _SyntheticEventKind.DIVIDEND_ENTITLEMENT:
            _checked_text(self.dividend_id, "dividend_id")
            _canonical_decimal(
                self.cash_per_share_usd,
                "dividend cash_per_share_usd",
                positive=False,
            )
            return
        if self.kind is _SyntheticEventKind.DIVIDEND_PAYMENT:
            _checked_text(self.dividend_id, "dividend_id")
            if self.cash_per_share_usd is not None:
                _canonical_decimal(
                    self.cash_per_share_usd,
                    "dividend payment cash_per_share_usd",
                    positive=False,
                )
            return
        if self.kind is _SyntheticEventKind.TERMINAL_CASH:
            if self.dividend_id is not None:
                raise _refuse("terminal cash cannot carry a dividend ID")
            _canonical_decimal(
                self.cash_per_share_usd,
                "terminal cash_per_share_usd",
                positive=False,
            )
            return
        if self.dividend_id is not None or self.cash_per_share_usd is not None:
            raise _refuse("refusal event cannot carry a cashflow")


_EVENT_PRECEDENCE = {
    _SyntheticEventKind.DIVIDEND_ENTITLEMENT: 0,
    _SyntheticEventKind.SPLIT: 1,
    _SyntheticEventKind.TERMINAL_CASH: 2,
    _SyntheticEventKind.DIVIDEND_PAYMENT: 3,
    _SyntheticEventKind.SUSPENSION: 4,
    _SyntheticEventKind.UNKNOWN_TERMINAL: 5,
    _SyntheticEventKind.OPEN: 6,
}


def _normalized_events(
    events: tuple[_SyntheticEvent, ...],
) -> tuple[_SyntheticEvent, ...]:
    if type(events) is not tuple or len(events) > _MAX_EVENTS:
        raise _refuse(f"events must be an exact tuple of at most {_MAX_EVENTS} rows")
    by_id: dict[str, _SyntheticEvent] = {}
    for event in events:
        if type(event) is not _SyntheticEvent:
            raise _refuse("events require exact _SyntheticEvent rows")
        _SyntheticEvent.__post_init__(event)
        previous = by_id.get(event.event_id)
        if previous is not None and previous != event:
            raise _refuse(f"event ID {event.event_id!r} has conflicting payloads")
        by_id[event.event_id] = event
    return tuple(
        sorted(
            by_id.values(),
            key=lambda event: (
                _checked_timestamp(event.at, "event.at"),
                _EVENT_PRECEDENCE[event.kind],
                event.security_identity_sha256,
                event.event_id,
            ),
        )
    )


@dataclasses.dataclass(frozen=True, slots=True)
class _SyntheticScenario:
    scenario_id: str
    decision_at: str
    entry_open_at: str
    exit_open_at: str
    initial_cash_usd: str
    long_security_identity_sha256s: tuple[str, ...]
    avoided_security_identity_sha256s: tuple[str, ...]
    events: tuple[_SyntheticEvent, ...]
    source_id: str = _SYNTHETIC_SOURCE_ID
    entitlement: SourceEntitlement = SourceEntitlement.SYNTHETIC_FIXTURE_ONLY
    selected_lookback: None = None

    def __post_init__(self) -> None:
        if type(self) is not _SyntheticScenario:
            raise _refuse("scenario must be the exact _SyntheticScenario type")
        _checked_text(self.scenario_id, "scenario_id")
        if type(self.source_id) is not str or self.source_id != _SYNTHETIC_SOURCE_ID:
            raise _refuse("scenario source_id must identify the synthetic fixture")
        decision = _checked_timestamp(self.decision_at, "decision_at")
        entry = _checked_timestamp(self.entry_open_at, "entry_open_at")
        exit_at = _checked_timestamp(self.exit_open_at, "exit_open_at")
        if not decision < entry < exit_at:
            raise _refuse("scenario clocks must satisfy decision < entry < exit")
        _canonical_decimal(
            self.initial_cash_usd, "initial_cash_usd", positive=True
        )
        for name, values in (
            ("long_security_identity_sha256s", self.long_security_identity_sha256s),
            (
                "avoided_security_identity_sha256s",
                self.avoided_security_identity_sha256s,
            ),
        ):
            if type(values) is not tuple or not values or len(values) > _MAX_SECURITIES:
                raise _refuse(f"{name} must be a nonempty canonical unique tuple")
            for value in values:
                _checked_sha256(value, name)
            if tuple(sorted(values)) != values or len(set(values)) != len(values):
                raise _refuse(f"{name} must be a nonempty canonical unique tuple")
        if set(self.long_security_identity_sha256s) & set(
            self.avoided_security_identity_sha256s
        ):
            raise _refuse("long and avoided identities must be disjoint")
        if self.entitlement is not SourceEntitlement.SYNTHETIC_FIXTURE_ONLY:
            raise _refuse("scenario entitlement must remain synthetic_fixture_only")
        if self.selected_lookback is not None:
            raise _refuse("synthetic accounting cannot select a lookback")
        known = set(self.long_security_identity_sha256s) | set(
            self.avoided_security_identity_sha256s
        )
        for event in _normalized_events(self.events):
            if event.security_identity_sha256 not in known:
                raise _refuse("event references an identity outside the scenario")
            event_at = _checked_timestamp(event.at, "event.at")
            if event_at < entry:
                raise _refuse("event cannot precede the entry open")
            if event_at > exit_at and event.kind is not _SyntheticEventKind.DIVIDEND_PAYMENT:
                raise _refuse("only a locked dividend payment may follow the exit open")


def _scenario_payload(scenario: _SyntheticScenario) -> dict[str, Any]:
    if type(scenario) is not _SyntheticScenario:
        raise _refuse("scenario must be the exact _SyntheticScenario type")
    _SyntheticScenario.__post_init__(scenario)
    return {
        "avoided_security_identity_sha256s": list(
            scenario.avoided_security_identity_sha256s
        ),
        "decision_at": scenario.decision_at,
        "entitlement": scenario.entitlement.value,
        "entry_open_at": scenario.entry_open_at,
        "events": [_event_payload(event) for event in _normalized_events(scenario.events)],
        "exit_open_at": scenario.exit_open_at,
        "initial_cash_usd": scenario.initial_cash_usd,
        "long_security_identity_sha256s": list(
            scenario.long_security_identity_sha256s
        ),
        "scenario_id": scenario.scenario_id,
        "selected_lookback": scenario.selected_lookback,
        "source_id": scenario.source_id,
    }


def _zero_authority_payload() -> dict[str, Any]:
    """Return fresh, exact closed-authority flags for every result path."""

    return {
        "actual_source_admitted": False,
        "authorized_real_outcome_looks": 0,
        "consumed_real_outcome_looks": 0,
        "outcome_access_authorized": False,
        "point_in_time_data_verified": False,
        "production_authoritative": False,
        "qc_backtest_authorized": False,
        "real_backtesting_ready": False,
        "selected_lookback": None,
        "synthetic_only": True,
        "trading_authority": False,
    }


def _require_synthetic_policy() -> dict[str, Any]:
    """Authenticate the policy and bind every local execution knob to it."""

    payload = synthetic_policy_payload()
    if type(payload) is not dict or hash_payload(payload) != SI5_SYNTHETIC_POLICY_SHA256:
        raise _refuse("synthetic demonstration policy authentication failed")
    require_si5_offline_protocol(SI5_OFFLINE_PROTOCOL)
    protocol_payload = SI5_OFFLINE_PROTOCOL.to_payload()
    primary = payload.get("primary_order_cost_bps_per_side")
    sensitivities = payload.get("sensitivity_cost_bps_per_side")
    diagnostic = payload.get("diagnostic_cost_bps_per_side")
    if (
        type(primary) is not int
        or primary != _PRIMARY_COST_BPS
        or primary != protocol_payload["primary_cost_bps_per_side"]
        or type(sensitivities) is not list
        or sensitivities != list(_COST_SENSITIVITIES_BPS)
        or sensitivities != protocol_payload["cost_sensitivities_bps_per_side"]
        or any(type(value) is not int for value in sensitivities)
        or type(diagnostic) is not int
        or diagnostic != protocol_payload["diagnostic_cost_bps_per_side"]
        or type(_PRIMARY_COST_BPS) is not int
        or type(_COST_SENSITIVITIES_BPS) is not tuple
        or any(type(value) is not int for value in _COST_SENSITIVITIES_BPS)
    ):
        raise _refuse("order cost knobs differ from the synthetic policy")
    expected_allowed = tuple(sorted({primary, *sensitivities}))
    if (
        type(_ALLOWED_COST_BPS) is not tuple
        or any(type(value) is not int for value in _ALLOWED_COST_BPS)
        or _ALLOWED_COST_BPS != expected_allowed
    ):
        raise _refuse("allowed order costs differ from the synthetic policy")
    if (
        type(payload.get("offline_protocol_sha256")) is not str
        or payload["offline_protocol_sha256"] != SI5_OFFLINE_PROTOCOL_SHA256
        or payload.get("selected_lookback") is not None
        or type(payload.get("synthetic_only")) is not bool
        or payload["synthetic_only"] is not True
        or type(payload.get("source_admitted")) is not bool
        or payload["source_admitted"] is not False
        or type(payload.get("real_backtesting_ready")) is not bool
        or payload["real_backtesting_ready"] is not False
        or type(payload.get("authorized_real_outcome_looks")) is not int
        or payload["authorized_real_outcome_looks"] != 0
        or type(payload.get("consumed_real_outcome_looks")) is not int
        or payload["consumed_real_outcome_looks"] != 0
    ):
        raise _refuse("synthetic policy cannot grant empirical authority")
    return payload


def _kernel_envelope(
    scenario: _SyntheticScenario, cost_bps: int
) -> dict[str, Any]:
    _require_synthetic_policy()
    return {
        "schema": SI5_SYNTHETIC_ORDER_VERSION,
        "scenario_id": scenario.scenario_id,
        "source_id": scenario.source_id,
        "source_entitlement": scenario.entitlement.value,
        "scenario_sha256": hash_payload(_scenario_payload(scenario)),
        "demonstration_policy_sha256": SI5_SYNTHETIC_POLICY_SHA256,
        "si5_offline_protocol_sha256": SI5_OFFLINE_PROTOCOL_SHA256,
        "cost_bps_per_side": cost_bps,
        "long_security_identity_sha256s": list(
            scenario.long_security_identity_sha256s
        ),
        "avoided_security_identity_sha256s": list(
            scenario.avoided_security_identity_sha256s
        ),
        "long_only": True,
        "short_sales": False,
        "leverage": False,
        **_zero_authority_payload(),
    }


def _preflight_refusals(
    scenario: _SyntheticScenario, events: tuple[_SyntheticEvent, ...]
) -> tuple[str, ...]:
    entry_at = _checked_timestamp(scenario.entry_open_at, "entry_open_at")
    exit_at = _checked_timestamp(scenario.exit_open_at, "exit_open_at")
    event_times = {
        event.event_id: _checked_timestamp(event.at, "event.at") for event in events
    }
    reasons: set[str] = set()
    for security in scenario.long_security_identity_sha256s:
        rows = [event for event in events if event.security_identity_sha256 == security]
        entries = [
            event
            for event in rows
            if event.kind is _SyntheticEventKind.OPEN
            and event_times[event.event_id] == entry_at
        ]
        exits = [
            event
            for event in rows
            if event.kind is _SyntheticEventKind.OPEN
            and event_times[event.event_id] == exit_at
        ]
        terminals = [
            event
            for event in rows
            if event.kind is _SyntheticEventKind.TERMINAL_CASH
            and event_times[event.event_id] <= exit_at
        ]
        if not entries:
            reasons.add(f"missing_entry_open:{security}")
        elif len(entries) != 1:
            reasons.add(f"ambiguous_entry_open:{security}")
        for event in (*entries, *exits):
            if event.fill_numerator != event.fill_denominator:
                reasons.add(f"partial_fill_not_supported:{event.event_id}")
        if len(terminals) > 1:
            reasons.add(f"ambiguous_terminal_cash:{security}")
        if any(event_times[event.event_id] <= entry_at for event in terminals):
            reasons.add(f"terminal_not_after_entry:{security}")
        if terminals and exits:
            reasons.add(f"terminal_and_exit_open_conflict:{security}")
        elif not terminals and not exits:
            reasons.add(f"missing_exit_or_terminal:{security}")
        elif not terminals and len(exits) != 1:
            reasons.add(f"ambiguous_exit_open:{security}")
        for event in rows:
            if entry_at <= event_times[event.event_id] <= exit_at:
                if event.kind is _SyntheticEventKind.SUSPENSION:
                    reasons.add(f"suspension:{security}")
                elif event.kind is _SyntheticEventKind.UNKNOWN_TERMINAL:
                    reasons.add(f"unknown_terminal_cashflow:{security}")

    entitlements: dict[tuple[str, str], list[_SyntheticEvent]] = {}
    payments: dict[tuple[str, str], list[_SyntheticEvent]] = {}
    for event in events:
        if event.kind not in {
            _SyntheticEventKind.DIVIDEND_ENTITLEMENT,
            _SyntheticEventKind.DIVIDEND_PAYMENT,
        }:
            continue
        key = event.security_identity_sha256, event.dividend_id or ""
        target = (
            entitlements
            if event.kind is _SyntheticEventKind.DIVIDEND_ENTITLEMENT
            else payments
        )
        target.setdefault(key, []).append(event)
    for key, rows in entitlements.items():
        if len(rows) != 1:
            reasons.add(f"ambiguous_dividend_entitlement:{key[0]}:{key[1]}")
    for key, rows in payments.items():
        entitled = entitlements.get(key, [])
        if not entitled:
            reasons.add(f"orphan_dividend_payment:{key[0]}:{key[1]}")
        elif len(rows) != 1:
            reasons.add(f"ambiguous_dividend_payment:{key[0]}:{key[1]}")
        elif event_times[rows[0].event_id] < event_times[entitled[0].event_id]:
            reasons.add(f"dividend_payment_precedes_entitlement:{key[0]}:{key[1]}")
        elif event_times[rows[0].event_id] == event_times[entitled[0].event_id]:
            reasons.add(f"dividend_payment_not_after_entitlement:{key[0]}:{key[1]}")
        elif (
            rows[0].cash_per_share_usd is not None
            and rows[0].cash_per_share_usd != entitled[0].cash_per_share_usd
        ):
            reasons.add(f"dividend_payment_amount_mismatch:{key[0]}:{key[1]}")
    return tuple(sorted(reasons))


def _order_payload(
    *,
    scenario: _SyntheticScenario,
    event: _SyntheticEvent,
    side: str,
    quantity: Fraction,
    price: Fraction,
    notional: Fraction,
    fee: Fraction,
    position_after: Fraction,
    cash_after: Fraction,
    cost_bps: int,
) -> dict[str, Any]:
    body = {
        "cost_bps_per_side": cost_bps,
        "event_id": event.event_id,
        "fill_fraction": {"numerator": 1, "denominator": 1},
        "fill_status": "filled",
        "filled_at": event.at,
        "fee": _fraction_payload(fee),
        "notional": _fraction_payload(notional),
        "position_quantity_after": _fraction_payload(position_after),
        "quantity": _fraction_payload(quantity),
        "raw_open_usd": event.raw_open_usd,
        "security_identity_sha256": event.security_identity_sha256,
        "side": side,
        "cash_after": _fraction_payload(cash_after),
    }
    body["order_event_sha256"] = hash_payload(
        {"scenario_id": scenario.scenario_id, **body}
    )
    return body


def _incomplete_kernel_result(
    scenario: _SyntheticScenario, cost_bps: int, reasons: tuple[str, ...]
) -> dict[str, Any]:
    payload = {
        **_kernel_envelope(scenario, cost_bps),
        "complete": False,
        "refusal_reasons": list(reasons),
        "financial_result": None,
    }
    payload["kernel_result_sha256"] = hash_payload(payload)
    return payload


def _run_synthetic_order_kernel(
    scenario: _SyntheticScenario, *, cost_bps: int
) -> dict[str, Any]:
    """Run the pure synthetic accounting kernel or return an atomic refusal."""

    if type(scenario) is not _SyntheticScenario:
        raise _refuse("scenario must be the exact _SyntheticScenario type")
    _SyntheticScenario.__post_init__(scenario)
    if type(cost_bps) is not int or cost_bps not in _ALLOWED_COST_BPS:
        raise _refuse(f"cost_bps must be one of {_ALLOWED_COST_BPS}")
    protocol_payload = SI5_OFFLINE_PROTOCOL.to_payload()
    require_si5_offline_protocol(SI5_OFFLINE_PROTOCOL)
    if (
        protocol_payload["terminal_value_rule"] is not None
        or protocol_payload["order_cashflow_rule"] is not None
    ):
        raise _refuse("empirical terminal/cashflow rules must remain unset")

    events = _normalized_events(scenario.events)
    reasons = _preflight_refusals(scenario, events)
    if reasons:
        return _incomplete_kernel_result(scenario, cost_bps, reasons)

    initial_cash = _as_fraction(
        scenario.initial_cash_usd, "initial_cash_usd", positive=True
    )
    cash = initial_cash
    allocation = initial_cash / len(scenario.long_security_identity_sha256s)
    fee_rate = Fraction(cost_bps, 10_000)
    positions = {
        security: Fraction(0) for security in scenario.long_security_identity_sha256s
    }
    receivables: dict[tuple[str, str], Fraction] = {}
    total_fees = Fraction(0)
    dividends_paid = Fraction(0)
    terminal_cash_paid = Fraction(0)
    gross_entry_notional = Fraction(0)
    orders: list[dict[str, Any]] = []
    cashflows: list[dict[str, Any]] = []
    splits: list[dict[str, Any]] = []
    entry_at = _checked_timestamp(scenario.entry_open_at, "entry_open_at")
    exit_at = _checked_timestamp(scenario.exit_open_at, "exit_open_at")

    for event in events:
        security = event.security_identity_sha256
        if security not in positions:
            # Avoided securities produce no order and cannot influence the book.
            continue
        quantity_before = positions[security]
        if event.kind is _SyntheticEventKind.DIVIDEND_ENTITLEMENT:
            per_share = _as_fraction(
                event.cash_per_share_usd or "",
                "dividend cash_per_share_usd",
                positive=False,
            )
            amount = quantity_before * per_share
            key = security, event.dividend_id or ""
            receivables[key] = amount
            cashflows.append(
                {
                    "amount": _fraction_payload(amount),
                    "at": event.at,
                    "cashflow_type": "dividend_entitlement",
                    "dividend_id": event.dividend_id,
                    "event_id": event.event_id,
                    "security_identity_sha256": security,
                    "shares_entitled": _fraction_payload(quantity_before),
                }
            )
            continue
        if event.kind is _SyntheticEventKind.SPLIT:
            ratio = Fraction(event.split_numerator or 0, event.split_denominator or 1)
            quantity_after = quantity_before * ratio
            positions[security] = quantity_after
            splits.append(
                {
                    "at": event.at,
                    "event_id": event.event_id,
                    "quantity_after": _fraction_payload(quantity_after),
                    "quantity_before": _fraction_payload(quantity_before),
                    "ratio": _fraction_payload(ratio),
                    "security_identity_sha256": security,
                }
            )
            continue
        if event.kind is _SyntheticEventKind.TERMINAL_CASH:
            per_share = _as_fraction(
                event.cash_per_share_usd or "",
                "terminal cash_per_share_usd",
                positive=False,
            )
            amount = quantity_before * per_share
            cash += amount
            terminal_cash_paid += amount
            positions[security] = Fraction(0)
            cashflows.append(
                {
                    "amount": _fraction_payload(amount),
                    "at": event.at,
                    "cashflow_type": "terminal_cash",
                    "event_id": event.event_id,
                    "security_identity_sha256": security,
                    "shares_terminated": _fraction_payload(quantity_before),
                }
            )
            continue
        if event.kind is _SyntheticEventKind.DIVIDEND_PAYMENT:
            key = security, event.dividend_id or ""
            amount = receivables.pop(key)
            cash += amount
            dividends_paid += amount
            cashflows.append(
                {
                    "amount": _fraction_payload(amount),
                    "at": event.at,
                    "cashflow_type": "dividend_payment",
                    "dividend_id": event.dividend_id,
                    "event_id": event.event_id,
                    "security_identity_sha256": security,
                }
            )
            continue
        if event.kind is not _SyntheticEventKind.OPEN:
            # Preflight converts every refusal-shaped event into an atomic
            # incomplete result, so reaching one here would be an internal bug.
            raise _refuse("unhandled refusal event reached accounting")

        price = _as_fraction(event.raw_open_usd or "", "raw_open_usd", positive=True)
        event_at = _checked_timestamp(event.at, "event.at")
        if event_at == entry_at:
            # Entry cost is reserved before sizing.  The allocation therefore
            # buys quantity *and* its fee without borrowing even at 20 bps.
            quantity = allocation / (price * (1 + fee_rate))
            notional = quantity * price
            fee = notional * fee_rate
            debit = notional + fee
            cash -= debit
            if cash < 0 or positions[security] != 0:
                raise _refuse("entry would create negative cash or duplicate exposure")
            positions[security] = quantity
            total_fees += fee
            gross_entry_notional += notional
            orders.append(
                _order_payload(
                    scenario=scenario,
                    event=event,
                    side="buy",
                    quantity=quantity,
                    price=price,
                    notional=notional,
                    fee=fee,
                    position_after=quantity,
                    cash_after=cash,
                    cost_bps=cost_bps,
                )
            )
        elif event_at == exit_at:
            quantity = positions[security]
            if quantity <= 0:
                raise _refuse("exit would sell a missing or terminal position")
            notional = quantity * price
            fee = notional * fee_rate
            credit = notional - fee
            if credit < 0:
                raise _refuse("exit fee exceeds sale proceeds")
            cash += credit
            positions[security] = Fraction(0)
            total_fees += fee
            orders.append(
                _order_payload(
                    scenario=scenario,
                    event=event,
                    side="sell",
                    quantity=quantity,
                    price=price,
                    notional=notional,
                    fee=fee,
                    position_after=Fraction(0),
                    cash_after=cash,
                    cost_bps=cost_bps,
                )
            )

    unsettled_reasons = tuple(
        sorted(
            f"unsettled_dividend_receivable:{security}:{dividend_id}"
            for (security, dividend_id), amount in receivables.items()
            if amount > 0
        )
    )
    if unsettled_reasons:
        return _incomplete_kernel_result(scenario, cost_bps, unsettled_reasons)
    if any(quantity != 0 for quantity in positions.values()):
        raise _refuse("complete accounting left an open position")
    if cash < 0:
        raise _refuse("complete accounting produced negative cash")
    outstanding = sum(receivables.values(), Fraction(0))
    total_equity = cash + outstanding
    realized_pnl = total_equity - initial_cash
    net_return = realized_pnl / initial_cash
    if gross_entry_notional > initial_cash:
        raise _refuse("entry gross exposure exceeds initial equity")

    financial_result = {
        "initial_cash": _fraction_payload(initial_cash),
        "ending_cash": _fraction_payload(cash),
        "outstanding_dividend_receivables": _fraction_payload(outstanding),
        "total_equity": _fraction_payload(total_equity),
        "total_fees": _fraction_payload(total_fees),
        "dividends_paid": _fraction_payload(dividends_paid),
        "terminal_cash_paid": _fraction_payload(terminal_cash_paid),
        "gross_entry_notional": _fraction_payload(gross_entry_notional),
        "realized_pnl": _fraction_payload(realized_pnl),
        "net_return": _fraction_payload(net_return),
        "final_positions": [],
    }
    payload = {
        **_kernel_envelope(scenario, cost_bps),
        "complete": True,
        "refusal_reasons": [],
        **financial_result,
        "orders": orders,
        "cashflows": cashflows,
        "splits": splits,
    }
    payload["kernel_result_sha256"] = hash_payload(payload)
    return payload


def _identity(label: str) -> str:
    return hash_payload({"synthetic_si5_security": label})


_ORDINARY = _identity("ordinary_exit")
_SPLIT = _identity("split_then_exit")
_DIVIDEND = _identity("dividend_then_exit")
_ZERO_TERMINAL = _identity("zero_terminal_cash")
_AVOIDED = _identity("avoided_high_pressure")
_ENTRY = "2024-01-29T14:30:00Z"
_EXIT = "2024-02-12T14:30:00Z"


_BUILTIN_SCENARIO = _SyntheticScenario(
    scenario_id=SI5_SYNTHETIC_ORDER_SCENARIO_ID,
    decision_at="2024-01-26T21:00:00Z",
    entry_open_at=_ENTRY,
    exit_open_at=_EXIT,
    initial_cash_usd="4000",
    long_security_identity_sha256s=tuple(
        sorted((_ORDINARY, _SPLIT, _DIVIDEND, _ZERO_TERMINAL))
    ),
    avoided_security_identity_sha256s=(_AVOIDED,),
    events=(
        _SyntheticEvent("ordinary-entry", _ORDINARY, _ENTRY, _SyntheticEventKind.OPEN, raw_open_usd="10"),
        _SyntheticEvent("split-entry", _SPLIT, _ENTRY, _SyntheticEventKind.OPEN, raw_open_usd="20"),
        _SyntheticEvent("dividend-entry", _DIVIDEND, _ENTRY, _SyntheticEventKind.OPEN, raw_open_usd="40"),
        _SyntheticEvent("terminal-entry", _ZERO_TERMINAL, _ENTRY, _SyntheticEventKind.OPEN, raw_open_usd="5"),
        _SyntheticEvent("avoided-entry", _AVOIDED, _ENTRY, _SyntheticEventKind.OPEN, raw_open_usd="10"),
        _SyntheticEvent(
            "dividend-entitlement",
            _DIVIDEND,
            "2024-02-01T14:30:00Z",
            _SyntheticEventKind.DIVIDEND_ENTITLEMENT,
            dividend_id="synthetic-dividend-1",
            cash_per_share_usd="1",
        ),
        _SyntheticEvent(
            "two-for-one-split",
            _SPLIT,
            "2024-02-05T14:30:00Z",
            _SyntheticEventKind.SPLIT,
            split_numerator=2,
            split_denominator=1,
        ),
        _SyntheticEvent(
            "dividend-payment",
            _DIVIDEND,
            "2024-02-08T21:00:00Z",
            _SyntheticEventKind.DIVIDEND_PAYMENT,
            dividend_id="synthetic-dividend-1",
        ),
        _SyntheticEvent(
            "zero-terminal-payout",
            _ZERO_TERMINAL,
            "2024-02-09T15:00:00Z",
            _SyntheticEventKind.TERMINAL_CASH,
            cash_per_share_usd="0",
        ),
        _SyntheticEvent("ordinary-exit", _ORDINARY, _EXIT, _SyntheticEventKind.OPEN, raw_open_usd="11"),
        _SyntheticEvent("split-exit", _SPLIT, _EXIT, _SyntheticEventKind.OPEN, raw_open_usd="11"),
        _SyntheticEvent("dividend-exit", _DIVIDEND, _EXIT, _SyntheticEventKind.OPEN, raw_open_usd="40"),
        _SyntheticEvent("avoided-exit", _AVOIDED, _EXIT, _SyntheticEventKind.OPEN, raw_open_usd="20"),
    ),
)


# Pinned below after the exact fixture is defined.  A literal makes accidental
# fixture drift fail at import/run instead of silently creating a new scenario.
SI5_SYNTHETIC_ORDER_FIXTURE_SHA256 = (
    "10dfa9cd677a7c6fb5c4513f16a7c683bc57c1c93a9937c10c1472c264b8fa0e"
)


def _require_builtin_fixture() -> str:
    actual = hash_payload(_scenario_payload(_BUILTIN_SCENARIO))
    if actual != SI5_SYNTHETIC_ORDER_FIXTURE_SHA256:
        raise _refuse("built-in synthetic fixture differs from its pinned digest")
    return actual


def _public_payload() -> dict[str, Any]:
    _require_synthetic_policy()
    fixture_sha256 = _require_builtin_fixture()
    runs = [
        _run_synthetic_order_kernel(_BUILTIN_SCENARIO, cost_bps=cost)
        for cost in _ALLOWED_COST_BPS
    ]
    if any(not run["complete"] for run in runs):
        raise _refuse("built-in synthetic fixture did not complete")
    payload = {
        "schema": "si5-synthetic-order-public-result-v1",
        "scenario_id": SI5_SYNTHETIC_ORDER_SCENARIO_ID,
        "fixture_sha256": fixture_sha256,
        "demonstration_policy_sha256": SI5_SYNTHETIC_POLICY_SHA256,
        "si5_offline_protocol_sha256": SI5_OFFLINE_PROTOCOL_SHA256,
        "empirical_terminal_value_rule": None,
        "empirical_order_cashflow_rule": None,
        "primary_cost_bps_per_side": _PRIMARY_COST_BPS,
        "cost_sensitivities_bps_per_side": list(_COST_SENSITIVITIES_BPS),
        "cost_runs": runs,
        "long_avoidance_semantic": (
            "unlevered_equal_cash_long_synthetic_covering_basket_and_no_orders_"
            "for_avoided_high_pressure_identity"
        ),
        "fractional_share_semantic": (
            "exact_fraction_synthetic_accounting_not_production_lot_policy"
        ),
        **_zero_authority_payload(),
    }
    payload["result_sha256"] = hash_payload(payload)
    return payload


_RESULT_AUTHORITY = object()


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class SI5SyntheticOrderResult:
    """Authenticated result for the sole built-in synthetic scenario."""

    _payload_json: str = dataclasses.field(repr=False)
    _payload_sha256: str = dataclasses.field(repr=False)
    _authority: object = dataclasses.field(repr=False, compare=False)

    def to_payload(self) -> dict[str, Any]:
        if (
            type(self) is not SI5SyntheticOrderResult
            or getattr(self, "_authority", None) is not _RESULT_AUTHORITY
        ):
            raise _refuse("result is not an authenticated built-in run")
        expected = _public_payload()
        expected_json = canonical_json(expected)
        if (
            type(self._payload_json) is not str
            or self._payload_json != expected_json
            or type(self._payload_sha256) is not str
            or self._payload_sha256 != expected["result_sha256"]
        ):
            raise _refuse("stored result differs from the canonical built-in run")
        try:
            stored = json.loads(self._payload_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise _refuse("stored result payload is invalid") from exc
        if (
            type(stored) is not dict
            or self._payload_json != canonical_json(stored)
            or self._payload_sha256 != stored["result_sha256"]
            or hash_payload(
                {key: value for key, value in stored.items() if key != "result_sha256"}
            )
            != self._payload_sha256
        ):
            raise _refuse("stored result hash is invalid")
        return deepcopy(stored)

    @property
    def sha256(self) -> str:
        return SI5SyntheticOrderResult.to_payload(self)["result_sha256"]


def _result_from_payload(payload: dict[str, Any]) -> SI5SyntheticOrderResult:
    value = object.__new__(SI5SyntheticOrderResult)
    object.__setattr__(value, "_payload_json", canonical_json(payload))
    object.__setattr__(value, "_payload_sha256", payload["result_sha256"])
    object.__setattr__(value, "_authority", _RESULT_AUTHORITY)
    return value


def run_si5_synthetic_order_scenario(
    scenario_id: str = SI5_SYNTHETIC_ORDER_SCENARIO_ID,
) -> SI5SyntheticOrderResult:
    """Run the one pinned synthetic scenario; external rows are not accepted."""

    if type(scenario_id) is not str or scenario_id != SI5_SYNTHETIC_ORDER_SCENARIO_ID:
        raise _refuse("only the pinned built-in synthetic scenario is available")
    return _result_from_payload(_public_payload())
