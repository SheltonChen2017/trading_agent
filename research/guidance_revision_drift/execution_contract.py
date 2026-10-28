"""Pinned offline execution assumptions and a supplied U.S. equity settlement calendar.

This is an engineering contract for regular-way common-stock and secondary-market
SPY share trades. It authenticates neither the caller's settlement-day inventory
nor a brokerage model. It creates no orders, fills, provider access or approval.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from data.hashing import hash_bytes
from research.guidance_revision_drift.input_contracts import (
    InputError, canonical_bytes, day, decode_object, digest, keys,
)
from research.guidance_revision_drift.research_reference import CalendarInput, PROTECTED_FROM
from research.guidance_revision_drift.simulation import commission_total


class ExecutionContractError(InputError):
    """Invalid fixed contract or unsupported dated execution question."""


_NY = ZoneInfo("America/New_York")
_SCHEMA = "gdr.offline-execution-contract.v1"
_MAX_BYTES = 262_144
_MAX_DAYS = 10_000
_FIRST_TRADE = date(2013, 1, 1)
_KEYS = frozenset({
    "schema", "scope", "settlement_calendar_source_sha256", "settlement_business_days",
    "settlement_coverage_from", "settlement_coverage_through", "regular_way_rules",
    "rule_sources", "execution_costs", "terminal_spy_policy", "evidence_status",
})
_SCOPE = "us_common_stock_and_spy_secondary_market_regular_way_offline"
_RULES = [
    {"from_trade_date": "2013-01-01", "settlement_business_day_lag": 3},
    {"from_trade_date": "2017-09-05", "settlement_business_day_lag": 2},
    {"from_trade_date": "2024-05-28", "settlement_business_day_lag": 1},
]
_SOURCES = {
    "sec_2017_t2": "https://www.sec.gov/resources-small-businesses/small-business-compliance-guides/amendment-securities-transaction-settlement-cycle-small-entity-compliance-guide",
    "sec_2024_t1": "https://www.sec.gov/files/rules/final/2023/34-96930.pdf",
    "dtcc_2024_cutover": "https://www.dtcc.com/Globals/PDFs/2024/April/25/20083-24",
}
_COSTS = {
    "base_impact_fraction": "0.0005",
    "stress_impact_fraction": "0.0015",
    "per_share_commission": "0.005",
    "base_minimum_commission": "1",
    "stress_minimum_commission": "2",
    "historical_additional_fees_verified": False,
}
_TERMINAL = {
    "trigger": "verified_cash_terminal_entitlement",
    "unwind": "first_regular_session_10_ny_strictly_after_entitlement",
    "fabricate_source_fill": False,
    "spend_unpaid_terminal_proceeds": False,
    "economic_policy_frozen_by_owner": False,
}
_EVIDENCE = {
    "settlement_calendar_verified": False,
    "source_rights_verified": False,
    "point_in_time_data": False,
    "native_execution_verified": False,
    "empirical_evaluation_allowed": False,
    "qc_access_allowed": False,
    "real_orders_allowed": False,
}
_FIXED_FIELDS = ("regular_way_rules", "rule_sources", "execution_costs", "terminal_spy_policy", "evidence_status")
_FIXED_BYTES = canonical_bytes({
    "regular_way_rules": _RULES,
    "rule_sources": _SOURCES,
    "execution_costs": _COSTS,
    "terminal_spy_policy": _TERMINAL,
    "evidence_status": _EVIDENCE,
})


def _refuse(code: str) -> None:
    raise ExecutionContractError(code)


def _settlement_days(rows: object) -> tuple[date, ...]:
    if type(rows) is not list or not 1 <= len(rows) <= _MAX_DAYS:
        _refuse("bounded_explicit_settlement_day_inventory_required")
    result = tuple(day(value) for value in rows)
    if any(value.weekday() >= 5 for value in result):
        _refuse("weekend_cannot_be_regular_settlement_business_day")
    if any(left >= right for left, right in zip(result, result[1:])):
        _refuse("settlement_days_must_be_strictly_ordered_and_unique")
    return result


def _decode(raw: bytes) -> tuple[dict, tuple[date, ...]]:
    try:
        body = keys(decode_object(raw, _MAX_BYTES), _KEYS)
        if body["schema"] != _SCHEMA or canonical_bytes(body) != raw or body["scope"] != _SCOPE:
            _refuse("canonical_fixed_execution_contract_required")
        digest(body["settlement_calendar_source_sha256"])
        days = _settlement_days(body["settlement_business_days"])
        if (body["settlement_coverage_from"] != days[0].isoformat()
                or body["settlement_coverage_through"] != days[-1].isoformat()):
            _refuse("settlement_inventory_coverage_mismatch")
        if canonical_bytes({key: body[key] for key in _FIXED_FIELDS}) != _FIXED_BYTES:
            _refuse("fixed_facts_assumptions_or_authority_changed")
        return body, days
    except ExecutionContractError:
        raise
    except (InputError, ValueError, TypeError, RecursionError) as exc:
        raise ExecutionContractError("invalid_execution_contract") from exc


@dataclass(frozen=True, slots=True)
class ExecutionContract:
    """Byte-pinned dated rule and explicitly supplied settlement service dates."""

    canonical_bytes: bytes

    def __post_init__(self) -> None:
        _decode(self.canonical_bytes)

    @classmethod
    def from_dict(cls, body: dict) -> ExecutionContract:
        try:
            return cls(canonical_bytes(body))
        except ExecutionContractError:
            raise
        except (InputError, ValueError, TypeError, RecursionError) as exc:
            raise ExecutionContractError("invalid_execution_contract") from exc

    @classmethod
    def from_bytes(cls, raw: bytes) -> ExecutionContract:
        return cls(raw)

    def to_dict(self) -> dict:
        return _decode(self.canonical_bytes)[0]

    @property
    def sha256(self) -> str:
        _decode(self.canonical_bytes)
        return hash_bytes(self.canonical_bytes)

    def settlement_on(self, calendar: CalendarInput, trade_date: date) -> date:
        """Return the supplied service date after T+3/T+2/T+1 regular-way lag.

        T is an explicit market session. The settlement-day inventory is separate:
        a market-open bank holiday may not itself provide settlement service.
        Inventory completeness and cash arrival remain external audit questions.
        """
        if type(calendar) is not CalendarInput or type(trade_date) is not date:
            _refuse("exact_calendar_and_trade_date_required")
        calendar = CalendarInput(calendar.canonical_bytes)
        calendar.index(trade_date)
        if not _FIRST_TRADE <= trade_date < PROTECTED_FROM:
            _refuse("trade_date_outside_unprotected_rule_scope")
        _, business_days = _decode(self.canonical_bytes)
        if not business_days[0] <= trade_date <= business_days[-1]:
            _refuse("trade_date_outside_explicit_settlement_inventory")
        lag = 3 if trade_date < date(2017, 9, 5) else 2 if trade_date < date(2024, 5, 28) else 1
        index = bisect_right(business_days, trade_date) + lag - 1
        if index >= len(business_days):
            _refuse("settlement_date_not_supplied")
        return business_days[index]

    def commission(self, quantity: int, mode: str) -> Decimal:
        """Cumulative per-order fee; charge each partial fill by the delta."""
        _decode(self.canonical_bytes)
        if type(quantity) is not int or not 0 <= quantity <= 10**12:
            _refuse("bounded_cumulative_whole_share_quantity_required")
        if type(mode) is not str or mode not in ("base", "stress"):
            _refuse("exact_execution_cost_mode_required")
        if quantity == 0:
            return Decimal(0)
        return commission_total(quantity, mode)

    def terminal_spy_unwind_at(self, calendar: CalendarInput, effective_at: datetime) -> datetime:
        """Proposed 10:00 comparator intent after verified cash entitlement.

        The returned instant is a decision time, not a fill or an approval.
        A known preopen entitlement may use 10:00 on the same declared session.
        The caller must supply the later of effective and validated-known times;
        this contract cannot authenticate either timestamp.
        """
        if (type(calendar) is not CalendarInput or type(effective_at) is not datetime
                or effective_at.tzinfo is None or effective_at.utcoffset() != timedelta(0)):
            _refuse("exact_calendar_and_aware_utc_terminal_instant_required")
        calendar = CalendarInput(calendar.canonical_bytes)
        local_day = effective_at.astimezone(_NY).date()
        coverage = calendar.to_dict()
        if not (_FIRST_TRADE <= local_day < PROTECTED_FROM
                and day(coverage["covered_from"]) <= local_day <= day(coverage["covered_through"])):
            _refuse("terminal_entitlement_outside_unprotected_calendar_coverage")
        for session in calendar.sessions:
            if session.session_date < local_day:
                continue
            if session.session_date >= PROTECTED_FROM:
                break
            decision = datetime.combine(session.session_date, time(10), _NY).astimezone(timezone.utc)
            if effective_at < decision:
                if not session.open_utc < decision < session.close_utc:
                    _refuse("terminal_unwind_outside_regular_session")
                return decision
        _refuse("terminal_unwind_session_not_supplied")


def default_contract(settlement_business_days: tuple[date, ...], *, calendar_source_sha256: str) -> ExecutionContract:
    """Build fixed proposed terms around a caller-supplied settlement inventory.

    The SHA-256 is a byte identity assertion for that external calendar source,
    not proof that the dates are complete, authentic, licensed or usable.
    """
    if type(settlement_business_days) is not tuple or not 1 <= len(settlement_business_days) <= _MAX_DAYS:
        _refuse("bounded_explicit_settlement_day_tuple_required")
    if any(type(value) is not date for value in settlement_business_days):
        _refuse("exact_settlement_date_required")
    try:
        digest(calendar_source_sha256)
    except InputError as exc:
        raise ExecutionContractError("settlement_calendar_source_hash_required") from exc
    dates = [value.isoformat() for value in settlement_business_days]
    body = {
        "schema": _SCHEMA,
        "scope": _SCOPE,
        "settlement_calendar_source_sha256": calendar_source_sha256,
        "settlement_business_days": dates,
        "settlement_coverage_from": dates[0],
        "settlement_coverage_through": dates[-1],
        "regular_way_rules": _RULES,
        "rule_sources": _SOURCES,
        "execution_costs": _COSTS,
        "terminal_spy_policy": _TERMINAL,
        "evidence_status": _EVIDENCE,
    }
    return ExecutionContract.from_dict(body)
