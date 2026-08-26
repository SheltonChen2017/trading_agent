"""Assistant-owned portfolio snapshot construction.

This module deliberately contains no signal, strategy, backtest, ML, or
research imports. Execution preflight may obtain a fresh broker snapshot here
without acquiring the broad research dependencies of ``context_builder``.
The legacy context-builder imports remain compatibility aliases.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from config import LEVERAGED_ETF_TICKERS
from assistant.money import decimal_text, to_decimal
from assistant.schemas import PortfolioPosition, PortfolioSnapshot


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
            else shares_decimal * current_price_decimal
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
        grouped[ticker]["shares"] += shares_decimal
        grouped[ticker]["cost"] += shares_decimal * entry_price_decimal
        grouped[ticker]["market_value"] += market_value_decimal

    built: list[PortfolioPosition] = []
    for ticker in order:
        aggregate = grouped[ticker]
        shares = aggregate["shares"]
        current_price = aggregate["current_price"]
        cost = aggregate["cost"]
        market_value = aggregate["market_value"]
        entry_price = cost / shares if shares else Decimal("0")
        unrealized_pnl_pct = (
            (market_value - cost) / cost * Decimal("100")
            if cost
            else Decimal("0")
        )
        built.append(
            PortfolioPosition(
                ticker=ticker,
                shares=float(shares),
                entry_price=float(entry_price),
                current_price=float(current_price),
                market_value=float(round(market_value, 2)),
                unrealized_pnl_pct=float(round(unrealized_pnl_pct, 2)),
                is_leveraged_etf=_classify_leveraged(ticker),
                shares_exact=decimal_text(shares),
                entry_price_exact=decimal_text(entry_price),
                current_price_exact=decimal_text(current_price),
                market_value_exact=decimal_text(market_value),
            )
        )

    total_equity = cash_decimal + sum(
        (to_decimal(position.market_value) for position in built), Decimal("0")
    )
    exact_total_equity = cash_decimal + sum(
        (position.exact_field("market_value") for position in built), Decimal("0")
    )
    return PortfolioSnapshot(
        positions=built,
        cash=float(round(cash_decimal, 2)),
        total_equity=float(round(total_equity, 2)),
        cash_exact=decimal_text(cash_decimal),
        total_equity_exact=decimal_text(exact_total_equity),
        buying_power_exact=(
            decimal_text(buying_power_decimal)
            if buying_power_decimal is not None
            else None
        ),
        as_of=datetime.now(timezone.utc).date().isoformat(),
        buying_power=(
            float(round(buying_power_decimal, 2))
            if buying_power_decimal is not None
            else None
        ),
        source=source,
        account_mode=account_mode,
        open_orders=open_orders or [],
        open_orders_available=open_orders_available,
        account_id=account_id,
    )


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
        "cash": _required_exact_decimal(account, "cash_decimal"),
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
        ticker = position.get("ticker")
        if not isinstance(ticker, str) or not ticker.strip():
            raise BrokerSnapshotCoherenceError(
                f"broker position row {index} has no usable ticker"
            )
        ticker = ticker.strip().upper()
        if ticker in seen:
            raise BrokerSnapshotCoherenceError(
                f"broker returned duplicate position rows for {ticker}"
            )
        seen.add(ticker)
        shares = _required_exact_decimal(position, "shares_decimal")
        if shares == 0:
            raise BrokerSnapshotCoherenceError(
                f"broker position {ticker} has a zero share quantity"
            )
        entry_price = _required_exact_decimal(
            position, "avg_entry_price_decimal", nonnegative=True
        )
        current_price = _required_exact_decimal(
            position, "current_price_decimal", positive=True
        )
        market_value = _required_exact_decimal(position, "market_value_decimal")
        if (shares > 0 and market_value < 0) or (
            shares < 0 and market_value > 0
        ):
            raise BrokerSnapshotCoherenceError(
                f"broker position {ticker} has inconsistent quantity/value signs"
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


def _canonical_snapshot_id(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
    component_delta = component_equity - broker_equity
    if abs(component_delta) > EXECUTION_COMPONENT_EQUITY_TOLERANCE:
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
    snapshot_id = _canonical_snapshot_id(
        {
            "schema": "alpaca-execution-portfolio-v1",
            "captured_at": captured_at,
            "account": account_material,
            "positions": material_positions,
            "active_order_fingerprint": orders_b_fingerprint,
            "component_equity": component_text,
            "component_equity_delta": delta_text,
        }
    )

    # The broker's account equity is authoritative; the component sum and
    # signed delta remain explicit evidence instead of silently replacing it.
    snapshot.total_equity = float(round(broker_equity, 2))
    snapshot.total_equity_exact = decimal_text(broker_equity)
    snapshot.captured_at = captured_at
    snapshot.broker_snapshot_id = snapshot_id
    snapshot.component_equity_exact = component_text
    snapshot.component_equity_delta_exact = delta_text
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
        open_orders = get_open_orders()
        open_orders_available = True
    except Exception:
        # A read-only briefing can still expose positions and cash, but order
        # availability must remain explicitly unknown so execution fails closed.
        open_orders = []
        open_orders_available = False
    positions = [
        {
            "ticker": position["ticker"],
            "shares": position.get("shares_decimal", position["shares"]),
            "entry_price": position.get(
                "avg_entry_price_decimal", position["avg_entry_price"]
            ),
            "current_price": position.get(
                "current_price_decimal", position["current_price"]
            ),
        }
        for position in get_open_positions()
    ]
    return build_portfolio_snapshot(
        positions,
        cash=account.get("cash_decimal", account["cash"]),
        buying_power=account.get(
            "buying_power_decimal", account["buying_power"]
        ),
        source="alpaca",
        account_mode="paper" if account["paper"] else "live",
        account_id=account["account_id"],
        open_orders=open_orders,
        open_orders_available=open_orders_available,
    )
