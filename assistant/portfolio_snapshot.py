"""Assistant-owned portfolio snapshot construction.

This module deliberately contains no signal, strategy, backtest, ML, or
research imports. Execution preflight may obtain a fresh broker snapshot here
without acquiring the broad research dependencies of ``context_builder``.
The legacy context-builder imports remain compatibility aliases.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal, DecimalException, InvalidOperation
from typing import Any

from config import LEVERAGED_ETF_TICKERS
from assistant.money import (
    decimal_text,
    deterministic_decimal_divide,
    deterministic_decimal_quantize,
    exact_decimal_add,
    exact_decimal_multiply,
    exact_decimal_subtract,
    exact_decimal_sum,
    to_decimal,
)
from assistant.schemas import PortfolioPosition, PortfolioSnapshot
from data.security_identity import (
    canonical_equity_ticker,
    is_canonical_equity_ticker,
)


POSITION_VALUE_TOLERANCE = Decimal("0.01")


class PortfolioSnapshotIntegrityError(ValueError):
    """A snapshot cannot represent this project's long-only cash account."""


def _portfolio_exact_add(name: str, left: Decimal, right: Decimal) -> Decimal:
    try:
        return exact_decimal_add(left, right, name=name)
    except ValueError as exc:
        raise PortfolioSnapshotIntegrityError(
            f"{name} exact decimal arithmetic is not representable"
        ) from exc


def _portfolio_exact_subtract(name: str, left: Decimal, right: Decimal) -> Decimal:
    try:
        return exact_decimal_subtract(left, right, name=name)
    except ValueError as exc:
        raise PortfolioSnapshotIntegrityError(
            f"{name} exact decimal arithmetic is not representable"
        ) from exc


def _portfolio_exact_multiply(name: str, left: Decimal, right: Decimal) -> Decimal:
    try:
        return exact_decimal_multiply(left, right, name=name)
    except ValueError as exc:
        raise PortfolioSnapshotIntegrityError(
            f"{name} exact decimal arithmetic is not representable"
        ) from exc


def _portfolio_exact_sum(name: str, values: Sequence[Decimal]) -> Decimal:
    try:
        return exact_decimal_sum(values, name=name)
    except ValueError as exc:
        raise PortfolioSnapshotIntegrityError(
            f"{name} exact decimal arithmetic is not representable"
        ) from exc


def _portfolio_deterministic_divide(
    name: str, numerator: Decimal, denominator: Decimal
) -> Decimal:
    try:
        return deterministic_decimal_divide(numerator, denominator, name=name)
    except ValueError as exc:
        raise PortfolioSnapshotIntegrityError(
            f"{name} decimal division is not representable"
        ) from exc


def _display_float(
    value: Decimal,
    *,
    name: str,
    rounded: bool,
) -> float:
    """Project exact evidence into a finite display float or fail closed.

    ``round(Decimal, 2)`` can raise ``decimal.InvalidOperation`` for a finite
    value whose exponent exceeds the active Decimal context.  InvalidOperation
    is an ArithmeticError, not a ValueError, so every display/evidence guard
    must normalize it explicitly instead of leaking an unhandled traceback.
    """
    try:
        projected = (
            deterministic_decimal_quantize(
                value,
                Decimal("0.01"),
                name=f"{name} display",
            )
            if rounded
            else value
        )
        display = float(projected)
    except (DecimalException, OverflowError, ValueError) as exc:
        raise PortfolioSnapshotIntegrityError(
            f"{name} exact evidence cannot be represented for display"
        ) from exc
    if not math.isfinite(display):
        raise PortfolioSnapshotIntegrityError(
            f"{name} exact evidence cannot be represented for display"
        )
    return display


def _evidence_decimal(
    *,
    exact_text: str | None,
    display_value: Any,
    name: str,
    rounded_display: bool,
) -> Decimal:
    try:
        display = to_decimal(display_value, name=f"{name} display")
        exact = (
            to_decimal(exact_text, name=f"{name} exact")
            if exact_text is not None
            else display
        )
    except ValueError as exc:
        raise PortfolioSnapshotIntegrityError(str(exc)) from exc
    if exact_text is not None:
        expected_display = _display_float(
            exact,
            name=name,
            rounded=rounded_display,
        )
        if display_value != expected_display:
            raise PortfolioSnapshotIntegrityError(
                f"{name} display value {display_value!r} disagrees with exact "
                f"evidence {exact_text!r}"
            )
    return exact


def validate_long_only_portfolio_snapshot(snapshot: PortfolioSnapshot) -> None:
    """Validate the canonical no-short/no-margin portfolio contract.

    Canonical snapshots contain holdings only: the builder normalizes a
    zero-share, zero-value source row away as not held. Every retained row must
    have positive quantity and prices, positive value consistent with quantity
    times current price to within one cent, and a unique canonical ticker.
    Exact decimal evidence outranks display floats, but the two must agree so
    no consumer sees a different portfolio than the risk engine.
    """
    if not isinstance(snapshot, PortfolioSnapshot):
        raise PortfolioSnapshotIntegrityError("snapshot must be a PortfolioSnapshot")

    cash = _evidence_decimal(
        exact_text=snapshot.cash_exact,
        display_value=snapshot.cash,
        name="portfolio.cash",
        rounded_display=True,
    )
    equity = _evidence_decimal(
        exact_text=snapshot.total_equity_exact,
        display_value=snapshot.total_equity,
        name="portfolio.total_equity",
        rounded_display=True,
    )
    if snapshot.buying_power is None and snapshot.buying_power_exact is not None:
        raise PortfolioSnapshotIntegrityError(
            "portfolio.buying_power_exact cannot exist without "
            "portfolio.buying_power"
        )
    buying_power = None
    if snapshot.buying_power is not None:
        buying_power = _evidence_decimal(
            exact_text=snapshot.buying_power_exact,
            display_value=snapshot.buying_power,
            name="portfolio.buying_power",
            rounded_display=True,
        )
    if cash < 0:
        raise PortfolioSnapshotIntegrityError(
            "portfolio.cash must be non-negative; margin cash is unsupported"
        )
    if equity < 0:
        raise PortfolioSnapshotIntegrityError(
            "portfolio.total_equity must be non-negative"
        )
    if buying_power is not None and buying_power < 0:
        raise PortfolioSnapshotIntegrityError(
            "portfolio.buying_power must be non-negative; margin debt is unsupported"
        )

    seen: set[str] = set()
    component_value = cash
    for position in snapshot.positions:
        ticker = position.ticker
        if not is_canonical_equity_ticker(ticker):
            raise PortfolioSnapshotIntegrityError(
                f"position ticker {ticker!r} is not canonical"
            )
        if ticker in seen:
            raise PortfolioSnapshotIntegrityError(
                f"duplicate position row for canonical ticker {ticker}"
            )
        seen.add(ticker)
        shares = _evidence_decimal(
            exact_text=position.shares_exact,
            display_value=position.shares,
            name=f"{ticker}.shares",
            rounded_display=False,
        )
        entry_price = _evidence_decimal(
            exact_text=position.entry_price_exact,
            display_value=position.entry_price,
            name=f"{ticker}.entry_price",
            rounded_display=False,
        )
        current_price = _evidence_decimal(
            exact_text=position.current_price_exact,
            display_value=position.current_price,
            name=f"{ticker}.current_price",
            rounded_display=False,
        )
        market_value = _evidence_decimal(
            exact_text=position.market_value_exact,
            display_value=position.market_value,
            name=f"{ticker}.market_value",
            rounded_display=True,
        )
        if shares <= 0:
            raise PortfolioSnapshotIntegrityError(
                f"{ticker}.shares must be positive; remove zero-share rows and short positions"
            )
        if entry_price <= 0 or current_price <= 0:
            raise PortfolioSnapshotIntegrityError(
                f"{ticker} entry_price and current_price must be positive"
            )
        if market_value <= 0:
            raise PortfolioSnapshotIntegrityError(
                f"{ticker}.market_value must be positive for a nonzero holding"
            )
        expected_value = _portfolio_exact_multiply(
            f"{ticker}.market_value",
            shares,
            current_price,
        )
        value_delta = _portfolio_exact_subtract(
            f"{ticker}.market_value delta",
            market_value,
            expected_value,
        ).copy_abs()
        if value_delta > POSITION_VALUE_TOLERANCE:
            raise PortfolioSnapshotIntegrityError(
                f"{ticker}.market_value {decimal_text(market_value)} disagrees with "
                f"shares*current_price {decimal_text(expected_value)} by more than "
                f"{decimal_text(POSITION_VALUE_TOLERANCE)}"
            )
        component_value = _portfolio_exact_add(
            "portfolio component equity",
            component_value,
            market_value,
        )

    component_delta = _portfolio_exact_subtract(
        "portfolio component equity delta",
        component_value,
        equity,
    ).copy_abs()
    if component_delta > POSITION_VALUE_TOLERANCE:
        raise PortfolioSnapshotIntegrityError(
            "portfolio.total_equity disagrees with exact cash plus position values "
            f"by {decimal_text(component_delta)}"
        )


def _classify_leveraged(ticker: str) -> bool:
    return ticker.upper() in LEVERAGED_ETF_TICKERS


def build_portfolio_snapshot(
    positions: list[dict],
    cash: float,
    *,
    buying_power: float | None = None,
    source: str = "manual",
    account_mode: str = "manual",
    account_id: str | None = None,
    open_orders: list[dict] | None = None,
    open_orders_available: bool = True,
) -> PortfolioSnapshot:
    """Build a validated, canonical portfolio snapshot.

    ``positions`` is a list of dicts: {ticker, shares, entry_price,
    current_price}. See ``build_portfolio_snapshot_from_alpaca()`` for pulling
    this shape from a live account instead of supplying it manually.

    SEP1R-003 restored the reasons below. The SEP-1 extraction moved this
    function unchanged but reduced its docstring to a summary of behaviour,
    which dropped the record of *which* defect each rule closed. Each one was
    found by an independent review, and each is invisible from the code alone:

    * **Ticker identity is canonicalized here** (whitespace-stripped,
      uppercased) so a manually supplied ``"aapl"`` is recognized identically
      to ``"AAPL"`` by every downstream basket/exposure check. A lowercase
      ticker was silently invisible to case-sensitive basket membership.
    * **Multiple rows for one canonical ticker are aggregated** into one
      ``PortfolioPosition`` — shares and market value sum, ``entry_price``
      becomes the share-weighted average cost basis. Left as separate rows,
      downstream per-ticker lookups (``{p.ticker: p for p in positions}``)
      silently keep only one of them, so two AAPL lots each under a
      per-position cap could jointly exceed it undetected.
    * **Rows for one ticker must report the same ``current_price``** — they
      describe the same instant. Inconsistent prices raise ``ValueError``
      rather than being combined, because there is no principled way to pick.
    * **``cash``, ``buying_power`` and every position number must be finite.**
      ``total_equity = cash + sum(market_value)``, so a NaN in *either* makes
      ``total_equity`` NaN and silently defeats every downstream ``>``/``<=``
      exposure comparison. The first version of this guard covered only the
      position rows, which left NaN cash producing exactly the failure it was
      meant to stop: ``check_policy_compliance()`` reported zero violations
      for a corrupt portfolio (independent review, 2026-07-29).
    """
    try:
        cash_decimal = to_decimal(cash, name="portfolio.cash")
    except ValueError:
        raise ValueError(
            f"Portfolio cash must be a finite number, got {cash!r}. Refusing to build a snapshot whose "
            "total_equity would be NaN -- every exposure check downstream would silently pass."
        ) from None
    try:
        buying_power_decimal = (
            to_decimal(buying_power, name="portfolio.buying_power")
            if buying_power is not None
            else None
        )
    except ValueError:
        raise ValueError(
            f"Portfolio buying_power must be a finite number or None, got {buying_power!r}."
        ) from None
    if cash_decimal < 0:
        raise PortfolioSnapshotIntegrityError(
            "Portfolio cash must be non-negative; margin cash is unsupported."
        )
    if buying_power_decimal is not None and buying_power_decimal < 0:
        raise PortfolioSnapshotIntegrityError(
            "Portfolio buying_power must be non-negative; margin debt is unsupported."
        )

    grouped: dict[str, dict] = {}
    order: list[str] = []
    for position in positions:
        ticker = position["ticker"].strip().upper()
        numeric_fields = ["shares", "entry_price", "current_price"]
        if "market_value" in position:
            numeric_fields.append("market_value")
        for field in numeric_fields:
            value = position[field]
            try:
                to_decimal(value, name=f"{ticker}.{field}")
            except ValueError:
                raise ValueError(
                    f"Position {ticker!r} has a non-finite/invalid {field}: {value!r}. Refusing to build "
                    "a portfolio snapshot from unusable data -- every exposure and proposal check "
                    "downstream would silently evaluate to False against NaN."
                ) from None
        shares_decimal = to_decimal(position["shares"], name=f"{ticker}.shares")
        entry_price_decimal = to_decimal(
            position["entry_price"], name=f"{ticker}.entry_price"
        )
        current_price_decimal = to_decimal(
            position["current_price"], name=f"{ticker}.current_price"
        )
        market_value_decimal = (
            to_decimal(position["market_value"], name=f"{ticker}.market_value")
            if "market_value" in position
            else _portfolio_exact_multiply(
                f"{ticker}.market_value",
                shares_decimal,
                current_price_decimal,
            )
        )
        if shares_decimal < 0:
            raise PortfolioSnapshotIntegrityError(
                f"Position {ticker!r} must have non-negative shares; short positions "
                "are unsupported."
            )
        if entry_price_decimal < 0 or current_price_decimal < 0:
            raise PortfolioSnapshotIntegrityError(
                f"Position {ticker!r} must have non-negative entry_price and current_price."
            )
        if shares_decimal == 0:
            if market_value_decimal != 0:
                raise PortfolioSnapshotIntegrityError(
                    f"Position {ticker!r} must have zero market_value when shares are zero."
                )
            # A closed lot is not a holding. Keeping the row would let consumers
            # that key on ticker presence treat it as sellable/current exposure.
            continue
        if entry_price_decimal == 0 or current_price_decimal == 0:
            raise PortfolioSnapshotIntegrityError(
                f"Position {ticker!r} must have positive entry_price and current_price."
            )
        if market_value_decimal <= 0:
            raise PortfolioSnapshotIntegrityError(
                f"Position {ticker!r} must have positive market_value."
            )
        expected_market_value = _portfolio_exact_multiply(
            f"{ticker}.market_value",
            shares_decimal,
            current_price_decimal,
        )
        market_value_delta = _portfolio_exact_subtract(
            f"{ticker}.market_value delta",
            market_value_decimal,
            expected_market_value,
        ).copy_abs()
        if market_value_delta > POSITION_VALUE_TOLERANCE:
            raise PortfolioSnapshotIntegrityError(
                f"Position {ticker!r} market_value disagrees with shares*current_price "
                f"by more than {decimal_text(POSITION_VALUE_TOLERANCE)}."
            )
        if ticker not in grouped:
            grouped[ticker] = {
                "shares": Decimal("0"),
                "cost": Decimal("0"),
                "current_price": current_price_decimal,
                "market_value": Decimal("0"),
            }
            order.append(ticker)
        elif grouped[ticker]["current_price"] != current_price_decimal:
            raise ValueError(
                f"Duplicate position rows for {ticker!r} report different current_price "
                f"values ({grouped[ticker]['current_price']} vs {position['current_price']}) -- "
                "refusing to silently aggregate inconsistent prices."
            )
        grouped[ticker]["shares"] = _portfolio_exact_add(
            f"{ticker}.aggregate shares",
            grouped[ticker]["shares"],
            shares_decimal,
        )
        row_cost = _portfolio_exact_multiply(
            f"{ticker}.row cost",
            shares_decimal,
            entry_price_decimal,
        )
        grouped[ticker]["cost"] = _portfolio_exact_add(
            f"{ticker}.aggregate cost",
            grouped[ticker]["cost"],
            row_cost,
        )
        grouped[ticker]["market_value"] = _portfolio_exact_add(
            f"{ticker}.aggregate market value",
            grouped[ticker]["market_value"],
            market_value_decimal,
        )

    built: list[PortfolioPosition] = []
    for ticker in order:
        aggregate = grouped[ticker]
        shares = aggregate["shares"]
        current_price = aggregate["current_price"]
        cost = aggregate["cost"]
        market_value = aggregate["market_value"]
        entry_price = (
            _portfolio_deterministic_divide(
                f"{ticker}.entry_price",
                cost,
                shares,
            )
            if shares
            else Decimal("0")
        )
        unrealized_pnl_pct = (
            _portfolio_exact_multiply(
                f"{ticker}.unrealized_pnl_pct",
                _portfolio_deterministic_divide(
                    f"{ticker}.unrealized_pnl_ratio",
                    _portfolio_exact_subtract(
                        f"{ticker}.unrealized_pnl",
                        market_value,
                        cost,
                    ),
                    cost,
                ),
                Decimal("100"),
            )
            if cost
            else Decimal("0")
        )
        built.append(
            PortfolioPosition(
                ticker=ticker,
                shares=_display_float(
                    shares,
                    name=f"{ticker}.shares",
                    rounded=False,
                ),
                entry_price=_display_float(
                    entry_price,
                    name=f"{ticker}.entry_price",
                    rounded=False,
                ),
                current_price=_display_float(
                    current_price,
                    name=f"{ticker}.current_price",
                    rounded=False,
                ),
                market_value=_display_float(
                    market_value,
                    name=f"{ticker}.market_value",
                    rounded=True,
                ),
                unrealized_pnl_pct=_display_float(
                    unrealized_pnl_pct,
                    name=f"{ticker}.unrealized_pnl_pct",
                    rounded=True,
                ),
                is_leveraged_etf=_classify_leveraged(ticker),
                shares_exact=decimal_text(shares),
                entry_price_exact=decimal_text(entry_price),
                current_price_exact=decimal_text(current_price),
                market_value_exact=decimal_text(market_value),
            )
        )

    exact_total_equity = _portfolio_exact_sum(
        "portfolio.total_equity",
        [cash_decimal]
        + [position.exact_field("market_value") for position in built],
    )
    snapshot = PortfolioSnapshot(
        positions=built,
        cash=_display_float(cash_decimal, name="portfolio.cash", rounded=True),
        # Aggregate authoritative values before rounding. Summing each
        # position's already-rounded display value can accumulate multiple
        # cents of drift and create a display/exact pair that fails its own
        # integrity contract.
        total_equity=_display_float(
            exact_total_equity,
            name="portfolio.total_equity",
            rounded=True,
        ),
        cash_exact=decimal_text(cash_decimal),
        total_equity_exact=decimal_text(exact_total_equity),
        buying_power_exact=(
            decimal_text(buying_power_decimal)
            if buying_power_decimal is not None
            else None
        ),
        as_of=datetime.now(timezone.utc).date().isoformat(),
        buying_power=(
            _display_float(
                buying_power_decimal,
                name="portfolio.buying_power",
                rounded=True,
            )
            if buying_power_decimal is not None
            else None
        ),
        source=source,
        account_mode=account_mode,
        open_orders=open_orders or [],
        open_orders_available=open_orders_available,
        account_id=account_id,
    )
    validate_long_only_portfolio_snapshot(snapshot)
    return snapshot


EXECUTION_COMPONENT_EQUITY_TOLERANCE = Decimal("0.01")
"""Maximum absolute account/component disagreement for execution evidence.

One cent is the smallest material USD ledger unit.  A larger discrepancy is
not rounded away: it means the account total and the exact cash-plus-position
components do not describe the same portfolio observation.
"""

_DEFAULT_COHERENCE_ATTEMPTS = 3
_MAX_COHERENCE_ATTEMPTS = 5
_UNUSABLE_ACCOUNT_IDS = frozenset({"", "none", "null", "unknown"})


class BrokerSnapshotCoherenceError(RuntimeError):
    """Broker observations cannot form one account-bound execution snapshot."""


def _broker_exact_add(name: str, left: Decimal, right: Decimal) -> Decimal:
    try:
        return exact_decimal_add(left, right, name=name)
    except ValueError as exc:
        raise BrokerSnapshotCoherenceError(
            f"{name} exact decimal arithmetic is not representable"
        ) from exc


def _broker_exact_subtract(name: str, left: Decimal, right: Decimal) -> Decimal:
    try:
        return exact_decimal_subtract(left, right, name=name)
    except ValueError as exc:
        raise BrokerSnapshotCoherenceError(
            f"{name} exact decimal arithmetic is not representable"
        ) from exc


def _broker_exact_multiply(name: str, left: Decimal, right: Decimal) -> Decimal:
    try:
        return exact_decimal_multiply(left, right, name=name)
    except ValueError as exc:
        raise BrokerSnapshotCoherenceError(
            f"{name} exact decimal arithmetic is not representable"
        ) from exc


def _broker_exact_sum(name: str, values: Sequence[Decimal]) -> Decimal:
    try:
        return exact_decimal_sum(values, name=name)
    except ValueError as exc:
        raise BrokerSnapshotCoherenceError(
            f"{name} exact decimal arithmetic is not representable"
        ) from exc


class _TransientBrokerSnapshotMutation(BrokerSnapshotCoherenceError):
    """A bounded retry may resolve a broker mutation observed mid-capture."""


def _required_exact_decimal(
    row: Mapping[str, Any],
    field: str,
    *,
    positive: bool = False,
    nonnegative: bool = False,
) -> Decimal:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise BrokerSnapshotCoherenceError(
            f"{field} must be present as broker-preserved decimal text"
        )
    try:
        parsed = Decimal(value.strip())
    except (InvalidOperation, ValueError) as exc:
        raise BrokerSnapshotCoherenceError(
            f"{field} is not valid exact decimal evidence: {value!r}"
        ) from exc
    if not parsed.is_finite():
        raise BrokerSnapshotCoherenceError(
            f"{field} is not finite exact decimal evidence: {value!r}"
        )
    if positive and parsed <= 0:
        raise BrokerSnapshotCoherenceError(f"{field} must be positive")
    if nonnegative and parsed < 0:
        raise BrokerSnapshotCoherenceError(f"{field} must be nonnegative")
    return parsed


def _strict_account_record(
    account: object,
    *,
    expected_account_id: str | None,
) -> dict[str, Any]:
    if not isinstance(account, Mapping):
        raise BrokerSnapshotCoherenceError(
            f"broker account must be a mapping, got {type(account).__name__}"
        )
    account_id = account.get("account_id")
    if not isinstance(account_id, str):
        raise BrokerSnapshotCoherenceError(
            "broker account_id must be a non-empty string"
        )
    account_id = account_id.strip()
    if account_id.lower() in _UNUSABLE_ACCOUNT_IDS:
        raise BrokerSnapshotCoherenceError(
            "broker account_id does not identify a real account"
        )
    if expected_account_id is not None and account_id != expected_account_id:
        raise BrokerSnapshotCoherenceError(
            "connected Alpaca account does not match the expected account"
        )
    if account.get("paper") is not True:
        raise BrokerSnapshotCoherenceError(
            "execution snapshots require broker-confirmed paper mode"
        )

    status = account.get("status")
    if not isinstance(status, str) or status.strip().upper() != "ACTIVE":
        raise BrokerSnapshotCoherenceError(
            f"broker account is not ACTIVE: {status!r}"
        )
    flags: dict[str, bool] = {}
    for field in (
        "trading_blocked",
        "account_blocked",
        "trade_suspended_by_user",
        "transfers_blocked",
    ):
        value = account.get(field)
        if type(value) is not bool:
            raise BrokerSnapshotCoherenceError(
                f"broker account {field} must be an actual bool"
            )
        flags[field] = value
    blocked = [
        field
        for field in (
            "trading_blocked",
            "account_blocked",
            "trade_suspended_by_user",
        )
        if flags[field]
    ]
    if blocked:
        raise BrokerSnapshotCoherenceError(
            "broker account is not trading-ready: " + ", ".join(blocked)
        )

    return {
        "account_id": account_id,
        "account_mode": "paper",
        "status": "ACTIVE",
        "equity": _required_exact_decimal(
            account, "equity_decimal", positive=True
        ),
        "cash": _required_exact_decimal(
            account, "cash_decimal", nonnegative=True
        ),
        "buying_power": _required_exact_decimal(
            account, "buying_power_decimal", nonnegative=True
        ),
        **flags,
    }


def _strict_position_records(
    positions: object,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    if isinstance(positions, (str, bytes)) or not isinstance(positions, Sequence):
        raise BrokerSnapshotCoherenceError(
            f"broker positions must be a sequence, got {type(positions).__name__}"
        )
    snapshot_rows: list[dict[str, str]] = []
    material_rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, position in enumerate(positions):
        if not isinstance(position, Mapping):
            raise BrokerSnapshotCoherenceError(
                f"broker position row {index} must be a mapping"
            )
        try:
            ticker = canonical_equity_ticker(
                position.get("ticker"),
                name=f"broker position row {index} ticker",
            )
        except ValueError as exc:
            raise BrokerSnapshotCoherenceError(str(exc)) from exc
        if ticker in seen:
            raise BrokerSnapshotCoherenceError(
                f"broker returned duplicate position rows for {ticker}"
            )
        seen.add(ticker)
        shares = _required_exact_decimal(position, "shares_decimal")
        if shares <= 0:
            raise BrokerSnapshotCoherenceError(
                f"broker position {ticker} must have a positive share quantity"
            )
        entry_price = _required_exact_decimal(
            position, "avg_entry_price_decimal", positive=True
        )
        current_price = _required_exact_decimal(
            position, "current_price_decimal", positive=True
        )
        market_value = _required_exact_decimal(position, "market_value_decimal")
        if market_value <= 0:
            raise BrokerSnapshotCoherenceError(
                f"broker position {ticker} must have a positive market value"
            )
        expected_market_value = _broker_exact_multiply(
            f"broker position {ticker} market value",
            shares,
            current_price,
        )
        market_value_delta = _broker_exact_subtract(
            f"broker position {ticker} market value delta",
            market_value,
            expected_market_value,
        ).copy_abs()
        if market_value_delta > POSITION_VALUE_TOLERANCE:
            # Alpaca's component fields are not atomically bracketed.  Unlike
            # a negative account balance or non-positive holding input, an
            # internally mismatched position can be a transient observation;
            # authorize only this precise condition for the bounded recapture.
            raise _TransientBrokerSnapshotMutation(
                f"broker position {ticker} market value changed during capture"
            )
        row = {
            "ticker": ticker,
            "shares": decimal_text(shares),
            "entry_price": decimal_text(entry_price),
            "current_price": decimal_text(current_price),
            "market_value": decimal_text(market_value),
        }
        snapshot_rows.append(row)
        material_rows.append(dict(row))
    material_rows.sort(key=lambda row: row["ticker"])
    return snapshot_rows, material_rows


def _require_exact_active_order_numerics(
    raw_orders: Sequence[Mapping[str, Any]], validated_orders: Sequence[Any]
) -> None:
    """Reject a strict book that only has rounded legacy float companions."""
    from execution.broker_contract import BrokerOrderIntegrityError

    for index, (raw, validated) in enumerate(zip(raw_orders, validated_orders)):
        required = ["filled_qty_decimal"]
        required.append(
            "shares_decimal" if validated.quantity is not None else "notional_decimal"
        )
        if validated.limit_price is not None:
            required.append("limit_price_decimal")
        if validated.filled_average_price is not None:
            required.append("filled_avg_price_decimal")
        for field in required:
            value = raw.get(field)
            if not isinstance(value, str) or not value.strip():
                raise BrokerOrderIntegrityError(
                    "missing_exact_order_numeric",
                    f"active order row {index} lacks exact {field} evidence",
                    field=field,
                )


def _has_preserved_decimal_text(value: object) -> bool:
    """Return whether a broker companion is preserved exact decimal text."""
    return isinstance(value, str) and bool(value.strip())


def _validated_read_only_open_orders(
    account: Mapping[str, Any],
    raw_orders: object,
) -> list[dict[str, Any]]:
    """Accept only one complete order list bound to the observed account."""
    if not isinstance(raw_orders, list):
        raise BrokerSnapshotCoherenceError(
            "read-only active-order observation must be a concrete list"
        )
    paper = account.get("paper")
    if type(paper) is not bool:
        raise BrokerSnapshotCoherenceError(
            "read-only broker account mode must be an actual bool"
        )
    from execution.broker_contract import (
        BrokerAccountIdentity,
        validate_active_order_set,
    )

    identity = BrokerAccountIdentity(
        account_id=account.get("account_id"),
        account_mode="paper" if paper else "live",
    )
    validated = validate_active_order_set(
        raw_orders,
        expected_account=identity,
        observed_account=identity,
    )
    _require_exact_active_order_numerics(raw_orders, validated)
    return [dict(order) for order in raw_orders]


def _canonical_snapshot_material_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _canonical_snapshot_id(payload: Mapping[str, Any]) -> str:
    encoded = _canonical_snapshot_material_json(payload).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verify_execution_portfolio_snapshot(snapshot: PortfolioSnapshot) -> None:
    """Recompute strict snapshot evidence and reject any post-capture mutation.

    ``broker_snapshot_id`` is not trusted as an opaque label.  The canonical
    material bytes captured from the broker are retained with the snapshot;
    this verifier hashes those bytes and independently compares every field
    that downstream risk math can read (including the active-order book) with
    the current object.
    """
    if not isinstance(snapshot, PortfolioSnapshot):
        raise BrokerSnapshotCoherenceError("execution snapshot has the wrong type")
    validate_long_only_portfolio_snapshot(snapshot)
    material_json = snapshot.broker_snapshot_material_json
    if not isinstance(material_json, str) or not material_json:
        raise BrokerSnapshotCoherenceError(
            "execution snapshot lacks canonical broker material"
        )
    try:
        material = json.loads(
            material_json,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {value}")
            ),
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise BrokerSnapshotCoherenceError(
            f"execution snapshot material is not canonical JSON: {exc}"
        ) from exc
    if not isinstance(material, Mapping) or material.get("schema") != (
        "alpaca-execution-portfolio-v1"
    ):
        raise BrokerSnapshotCoherenceError(
            "execution snapshot material has an unsupported schema"
        )
    if _canonical_snapshot_material_json(material) != material_json:
        raise BrokerSnapshotCoherenceError(
            "execution snapshot material is not in canonical byte form"
        )
    expected_id = hashlib.sha256(material_json.encode("utf-8")).hexdigest()
    if snapshot.broker_snapshot_id != expected_id:
        raise BrokerSnapshotCoherenceError(
            "execution snapshot ID does not match its canonical material"
        )
    if snapshot.source != "alpaca" or snapshot.account_mode != "paper":
        raise BrokerSnapshotCoherenceError(
            "execution snapshot must remain an Alpaca paper observation"
        )
    if snapshot.captured_at != material.get("captured_at"):
        raise BrokerSnapshotCoherenceError(
            "execution snapshot capture time changed after capture"
        )

    account = material.get("account")
    if not isinstance(account, Mapping):
        raise BrokerSnapshotCoherenceError(
            "execution snapshot material lacks an account record"
        )
    if (
        account.get("account_id") != snapshot.account_id
        or account.get("account_mode") != "paper"
        or account.get("status") != "ACTIVE"
    ):
        raise BrokerSnapshotCoherenceError(
            "execution snapshot account identity/state changed after capture"
        )
    for flag in (
        "trading_blocked",
        "account_blocked",
        "trade_suspended_by_user",
        "transfers_blocked",
    ):
        if type(account.get(flag)) is not bool:
            raise BrokerSnapshotCoherenceError(
                f"execution snapshot account material has invalid {flag}"
            )
    if any(
        account.get(flag)
        for flag in (
            "trading_blocked",
            "account_blocked",
            "trade_suspended_by_user",
        )
    ):
        raise BrokerSnapshotCoherenceError(
            "execution snapshot account material is trading-blocked"
        )

    cash = snapshot.cash_exact_decimal
    equity = snapshot.total_equity_exact_decimal
    buying_power = snapshot.buying_power_exact_decimal
    if buying_power is None:
        raise BrokerSnapshotCoherenceError(
            "execution snapshot lacks exact buying power"
        )
    if (
        account.get("cash") != decimal_text(cash)
        or account.get("equity") != decimal_text(equity)
        or account.get("buying_power") != decimal_text(buying_power)
    ):
        raise BrokerSnapshotCoherenceError(
            "execution snapshot account numerics changed after capture"
        )
    if (
        snapshot.cash
        != _display_float(cash, name="portfolio.cash", rounded=True)
        or snapshot.total_equity
        != _display_float(equity, name="portfolio.total_equity", rounded=True)
        or snapshot.buying_power
        != _display_float(
            buying_power,
            name="portfolio.buying_power",
            rounded=True,
        )
    ):
        raise BrokerSnapshotCoherenceError(
            "execution snapshot rounded account fields disagree with exact evidence"
        )

    current_positions: list[dict[str, str]] = []
    for position in snapshot.positions:
        row = {
            "ticker": position.ticker,
            "shares": decimal_text(position.exact_field("shares")),
            "entry_price": decimal_text(position.exact_field("entry_price")),
            "current_price": decimal_text(position.exact_field("current_price")),
            "market_value": decimal_text(position.exact_field("market_value")),
        }
        if (
            position.shares
            != _display_float(
                position.exact_field("shares"),
                name=f"{position.ticker}.shares",
                rounded=False,
            )
            or position.entry_price
            != _display_float(
                position.exact_field("entry_price"),
                name=f"{position.ticker}.entry_price",
                rounded=False,
            )
            or position.current_price
            != _display_float(
                position.exact_field("current_price"),
                name=f"{position.ticker}.current_price",
                rounded=False,
            )
            or position.market_value
            != _display_float(
                position.exact_field("market_value"),
                name=f"{position.ticker}.market_value",
                rounded=True,
            )
            or position.is_leveraged_etf != _classify_leveraged(position.ticker)
        ):
            raise BrokerSnapshotCoherenceError(
                f"execution snapshot position {position.ticker!r} changed after capture"
            )
        current_positions.append(row)
    current_positions.sort(key=lambda row: row["ticker"])
    if material.get("positions") != current_positions:
        raise BrokerSnapshotCoherenceError(
            "execution snapshot positions changed after capture"
        )

    if snapshot.open_orders_available is not True:
        raise BrokerSnapshotCoherenceError(
            "execution snapshot active-order book is unavailable"
        )
    from execution.broker_contract import (
        BrokerAccountIdentity,
        active_order_material_fingerprint,
        validate_active_order_set,
    )

    identity = BrokerAccountIdentity(snapshot.account_id or "", "paper")
    validated_orders = validate_active_order_set(
        snapshot.open_orders,
        expected_account=identity,
        observed_account=identity,
    )
    _require_exact_active_order_numerics(snapshot.open_orders, validated_orders)
    if material.get("active_order_fingerprint") != (
        active_order_material_fingerprint(validated_orders)
    ):
        raise BrokerSnapshotCoherenceError(
            "execution snapshot active orders changed after capture"
        )

    component_equity = _broker_exact_sum(
        "execution snapshot component equity",
        [cash]
        + [
            position.exact_field("market_value")
            for position in snapshot.positions
        ],
    )
    component_delta = _broker_exact_subtract(
        "execution snapshot component equity delta",
        component_equity,
        equity,
    )
    if component_delta.copy_abs() > EXECUTION_COMPONENT_EQUITY_TOLERANCE:
        raise BrokerSnapshotCoherenceError(
            "execution snapshot component equity exceeds the allowed tolerance"
        )
    if (
        snapshot.component_equity_exact != decimal_text(component_equity)
        or snapshot.component_equity_delta_exact != decimal_text(component_delta)
        or material.get("component_equity") != decimal_text(component_equity)
        or material.get("component_equity_delta") != decimal_text(component_delta)
    ):
        raise BrokerSnapshotCoherenceError(
            "execution snapshot component evidence changed after capture"
        )


def verify_execution_portfolio_snapshot(snapshot: PortfolioSnapshot) -> None:
    """Verify strict evidence while preserving one public coherence contract."""
    try:
        _verify_execution_portfolio_snapshot(snapshot)
    except BrokerSnapshotCoherenceError:
        raise
    except (
        PortfolioSnapshotIntegrityError,
        DecimalException,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise BrokerSnapshotCoherenceError(
            f"execution snapshot integrity verification failed: {exc}"
        ) from exc


def _capture_strict_alpaca_snapshot_once(
    broker_session: Any,
    *,
    expected_account_id: str | None,
) -> PortfolioSnapshot:
    """Capture one account/order-bracketed observation in the required order."""
    # Do not move validation calls between these reads.  Positions are valid
    # only while the same exact account totals and active-order material book
    # are observed on both sides of this sequence.
    account_a_raw = broker_session.get_account()
    orders_a_raw = broker_session.get_open_orders()
    positions_raw = broker_session.get_open_positions()
    orders_b_raw = broker_session.get_open_orders()
    account_b_raw = broker_session.get_account()

    account_a = _strict_account_record(
        account_a_raw, expected_account_id=expected_account_id
    )
    account_b = _strict_account_record(
        account_b_raw, expected_account_id=expected_account_id
    )
    if account_a != account_b:
        raise _TransientBrokerSnapshotMutation(
            "broker account identity or material balances changed during capture"
        )

    if not isinstance(orders_a_raw, list) or not isinstance(orders_b_raw, list):
        raise BrokerSnapshotCoherenceError(
            "broker active-order observations must be concrete lists"
        )
    from execution.broker_contract import (
        BrokerAccountIdentity,
        active_order_material_fingerprint,
        validate_active_order_set,
    )

    identity = BrokerAccountIdentity(
        account_id=account_a["account_id"], account_mode="paper"
    )
    orders_a = validate_active_order_set(
        orders_a_raw,
        expected_account=identity,
        observed_account=identity,
    )
    orders_b = validate_active_order_set(
        orders_b_raw,
        expected_account=identity,
        observed_account=identity,
    )
    _require_exact_active_order_numerics(orders_a_raw, orders_a)
    _require_exact_active_order_numerics(orders_b_raw, orders_b)
    orders_a_fingerprint = active_order_material_fingerprint(orders_a)
    orders_b_fingerprint = active_order_material_fingerprint(orders_b)
    if orders_a_fingerprint != orders_b_fingerprint:
        raise _TransientBrokerSnapshotMutation(
            "active broker orders changed during portfolio capture"
        )

    position_rows, material_positions = _strict_position_records(positions_raw)
    snapshot = build_portfolio_snapshot(
        position_rows,
        cash=decimal_text(account_a["cash"]),
        buying_power=decimal_text(account_a["buying_power"]),
        source="alpaca",
        account_mode="paper",
        account_id=account_a["account_id"],
        open_orders=[dict(order) for order in orders_b_raw],
        open_orders_available=True,
    )
    component_equity = snapshot.total_equity_exact_decimal
    broker_equity = account_a["equity"]
    component_delta = _broker_exact_subtract(
        "broker component equity delta",
        component_equity,
        broker_equity,
    )
    if component_delta.copy_abs() > EXECUTION_COMPONENT_EQUITY_TOLERANCE:
        raise _TransientBrokerSnapshotMutation(
            "broker equity disagrees with exact cash-plus-position components "
            f"by {component_delta} (tolerance "
            f"{EXECUTION_COMPONENT_EQUITY_TOLERANCE})"
        )

    captured_at = datetime.now(timezone.utc).isoformat()
    account_material = {
        key: (decimal_text(value) if isinstance(value, Decimal) else value)
        for key, value in account_a.items()
    }
    component_text = decimal_text(component_equity)
    delta_text = decimal_text(component_delta)
    snapshot_material = {
        "schema": "alpaca-execution-portfolio-v1",
        "captured_at": captured_at,
        "account": account_material,
        "positions": material_positions,
        "active_order_fingerprint": orders_b_fingerprint,
        "component_equity": component_text,
        "component_equity_delta": delta_text,
    }
    snapshot_material_json = _canonical_snapshot_material_json(snapshot_material)
    snapshot_id = hashlib.sha256(
        snapshot_material_json.encode("utf-8")
    ).hexdigest()

    # The broker's account equity is authoritative; the component sum and
    # signed delta remain explicit evidence instead of silently replacing it.
    snapshot.total_equity = _display_float(
        broker_equity,
        name="portfolio.total_equity",
        rounded=True,
    )
    snapshot.total_equity_exact = decimal_text(broker_equity)
    snapshot.captured_at = captured_at
    snapshot.broker_snapshot_id = snapshot_id
    snapshot.component_equity_exact = component_text
    snapshot.component_equity_delta_exact = delta_text
    snapshot.broker_snapshot_material_json = snapshot_material_json
    verify_execution_portfolio_snapshot(snapshot)
    return snapshot


def build_portfolio_snapshot_from_alpaca(
    *,
    broker_session: Any | None = None,
    require_execution_coherence: bool = False,
    max_coherence_attempts: int = _DEFAULT_COHERENCE_ATTEMPTS,
    expected_account_id: str | None = None,
) -> PortfolioSnapshot:
    """Pull broker state and build the same validated snapshot shape.

    Pulls live positions and cash from the connected Alpaca account (paper or
    live, per ``config.PAPER_TRADING``) and builds the same
    ``PortfolioSnapshot`` shape as the manual path.

    Raises ``execution.alpaca_broker.AlpacaNotConfigured`` when the API
    credentials are absent. **Callers should check
    ``execution.alpaca_broker.is_configured()`` first** — see
    ``build_decision_packet()``'s ``use_live_alpaca`` handling — rather than
    relying on this exception for control flow (SEP1R-003: this caller
    guidance was dropped when the function moved).
    """
    if require_execution_coherence:
        if (
            isinstance(max_coherence_attempts, bool)
            or not isinstance(max_coherence_attempts, int)
            or not 1 <= max_coherence_attempts <= _MAX_COHERENCE_ATTEMPTS
        ):
            raise ValueError(
                f"max_coherence_attempts must be an integer from 1 to "
                f"{_MAX_COHERENCE_ATTEMPTS}"
            )
        if expected_account_id is not None:
            if (
                not isinstance(expected_account_id, str)
                or expected_account_id.strip().lower() in _UNUSABLE_ACCOUNT_IDS
            ):
                raise ValueError("expected_account_id must be a usable string")
            expected_account_id = expected_account_id.strip()
        if broker_session is None:
            from execution.alpaca_broker import open_alpaca_broker_session

            broker_session = open_alpaca_broker_session()
        if (
            getattr(broker_session, "PAPER_TRADING", None) is not True
            or getattr(broker_session, "account_mode", None) != "paper"
        ):
            raise BrokerSnapshotCoherenceError(
                "strict execution capture requires one account-scoped paper broker session"
            )
        last_mutation: _TransientBrokerSnapshotMutation | None = None
        for _attempt in range(max_coherence_attempts):
            try:
                snapshot = _capture_strict_alpaca_snapshot_once(
                    broker_session,
                    expected_account_id=expected_account_id,
                )
            except _TransientBrokerSnapshotMutation as exc:
                last_mutation = exc
                continue
            except PortfolioSnapshotIntegrityError as exc:
                # Only an explicit _TransientBrokerSnapshotMutation authorizes
                # retry: account/order bracket changes, internally inconsistent
                # position components, or account/component disagreement.
                # Deterministic contract and display failures refuse now.
                raise BrokerSnapshotCoherenceError(
                    f"broker snapshot violates the long-only portfolio contract: {exc}"
                ) from exc
            if (
                snapshot.source != "alpaca"
                or snapshot.account_mode != "paper"
                or not snapshot.account_id
                or not snapshot.captured_at
                or not snapshot.broker_snapshot_id
            ):
                raise BrokerSnapshotCoherenceError(
                    "strict capture did not produce complete Alpaca paper evidence"
                )
            return snapshot
        assert last_mutation is not None
        raise BrokerSnapshotCoherenceError(
            f"broker state did not stabilize after {max_coherence_attempts} "
            f"attempt(s): {last_mutation}"
        ) from last_mutation

    if broker_session is None:
        from execution.alpaca_broker import (
            get_account,
            get_open_orders,
            get_open_positions,
        )
    else:
        get_account = broker_session.get_account
        get_open_orders = broker_session.get_open_orders
        get_open_positions = broker_session.get_open_positions

    account = get_account()
    try:
        open_orders = _validated_read_only_open_orders(
            account,
            get_open_orders(),
        )
        open_orders_available = True
    except Exception:
        # A read-only briefing can still expose positions and cash, but order
        # availability must remain explicitly unknown so execution fails closed.
        open_orders = []
        open_orders_available = False
    positions: list[dict[str, Any]] = []
    position_exactness: dict[str, dict[str, bool]] = {}
    for position in get_open_positions():
        try:
            ticker = canonical_equity_ticker(
                position["ticker"],
                name="position ticker",
            )
        except ValueError as exc:
            raise PortfolioSnapshotIntegrityError(str(exc)) from exc
        shares_exact = _has_preserved_decimal_text(
            position.get("shares_decimal")
        )
        entry_exact = _has_preserved_decimal_text(
            position.get("avg_entry_price_decimal")
        )
        current_exact = _has_preserved_decimal_text(
            position.get("current_price_decimal")
        )
        exactness = position_exactness.setdefault(
            ticker,
            {
                "shares": True,
                "entry_price": True,
                "current_price": True,
                "market_value": True,
            },
        )
        exactness["shares"] &= shares_exact
        # Duplicate rows are share-weighted by the builder, so a preserved
        # aggregate entry price requires exact quantity and entry companions.
        exactness["entry_price"] &= shares_exact and entry_exact
        exactness["current_price"] &= current_exact
        exactness["market_value"] &= shares_exact and current_exact
        positions.append(
            {
                "ticker": position["ticker"],
                "shares": (
                    position["shares_decimal"]
                    if position.get("shares_decimal") is not None
                    else position["shares"]
                ),
                "entry_price": (
                    position["avg_entry_price_decimal"]
                    if position.get("avg_entry_price_decimal") is not None
                    else position["avg_entry_price"]
                ),
                "current_price": (
                    position["current_price_decimal"]
                    if position.get("current_price_decimal") is not None
                    else position["current_price"]
                ),
            }
        )

    cash_exact = _has_preserved_decimal_text(account.get("cash_decimal"))
    buying_power_exact = _has_preserved_decimal_text(
        account.get("buying_power_decimal")
    )
    snapshot = build_portfolio_snapshot(
        positions,
        cash=(
            account["cash_decimal"]
            if account.get("cash_decimal") is not None
            else account["cash"]
        ),
        buying_power=(
            account["buying_power_decimal"]
            if account.get("buying_power_decimal") is not None
            else account["buying_power"]
        ),
        source="alpaca",
        account_mode="paper" if account["paper"] else "live",
        account_id=account["account_id"],
        open_orders=open_orders,
        open_orders_available=open_orders_available,
    )
    all_market_components_exact = True
    for position in snapshot.positions:
        exactness = position_exactness[position.ticker]
        if not exactness["shares"]:
            position.shares_exact = None
        if not exactness["entry_price"]:
            position.entry_price_exact = None
        if not exactness["current_price"]:
            position.current_price_exact = None
        if not exactness["market_value"]:
            position.market_value_exact = None
            all_market_components_exact = False
    if not cash_exact:
        snapshot.cash_exact = None
    if snapshot.buying_power is not None and not buying_power_exact:
        snapshot.buying_power_exact = None
    if not cash_exact or not all_market_components_exact:
        snapshot.total_equity_exact = None
    return snapshot
