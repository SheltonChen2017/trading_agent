"""Deterministic portfolio-level metrics used by briefings and proposals."""
from __future__ import annotations

import math
from decimal import Decimal

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
from assistant.portfolio_snapshot import (
    PortfolioSnapshotIntegrityError,
    validate_long_only_portfolio_snapshot,
)
from assistant.schemas import PortfolioSnapshot


_TWO_PLACES = Decimal("0.01")
_ONE_HUNDRED = Decimal("100")


def _finite_float(
    value: Decimal,
    *,
    name: str,
    quantum: Decimal | None = None,
) -> float:
    """Project exact evidence to this module's legacy float schema safely."""
    try:
        projected = (
            deterministic_decimal_quantize(value, quantum, name=name)
            if quantum is not None
            else exact_decimal_add(Decimal("0"), value, name=name)
        )
        display = float(projected)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} cannot be represented for display") from exc
    if not math.isfinite(display):
        raise ValueError(f"{name} cannot be represented for display")
    return display


def _percentage(value: Decimal, total: Decimal, *, name: str) -> Decimal:
    if total == 0:
        return Decimal("0")
    ratio = deterministic_decimal_divide(value, total, name=f"{name} ratio")
    return exact_decimal_multiply(ratio, _ONE_HUNDRED, name=name)


def _estimate_pending_buy_value_decimals(
    open_orders: list[dict],
) -> tuple[dict[str, Decimal], set[str]]:
    """Exact internal form of pending-buy estimation.

    Malformed progress/value evidence remains explicit in ``unknown``. Known
    sibling orders are retained, while no invalid operand is converted to a
    plausible zero and included in the aggregate.
    """
    totals: dict[str, Decimal] = {}
    unknown: set[str] = set()
    for order in open_orders:
        if str(order.get("side", "")).lower() != "buy":
            continue
        raw_ticker = order.get("ticker")
        if not isinstance(raw_ticker, str) or not raw_ticker.strip():
            continue
        ticker = raw_ticker.strip().upper()
        raw_filled = order.get("filled_qty")
        try:
            filled_qty = (
                to_decimal(raw_filled, name=f"{ticker} pending filled_qty")
                if raw_filled is not None
                else Decimal("0")
            )
            # Force the shared exact-arithmetic bound even when this value is
            # not subsequently multiplied (for example, no fill price).
            filled_qty = exact_decimal_add(
                Decimal("0"),
                filled_qty,
                name=f"{ticker} pending filled_qty normalization",
            )
        except ValueError:
            filled_qty = Decimal("0")
            unknown.add(ticker)
        if filled_qty < 0:
            filled_qty = Decimal("0")
            unknown.add(ticker)

        notional = order.get("notional")
        if notional is not None:
            try:
                value = exact_decimal_add(
                    Decimal("0"),
                    to_decimal(notional, name=f"{ticker} pending notional"),
                    name=f"{ticker} pending notional normalization",
                )
            except ValueError:
                unknown.add(ticker)
                continue
            if value <= 0:
                unknown.add(ticker)
                continue
            raw_fill_price = order.get("filled_avg_price")
            if filled_qty > 0 and raw_fill_price is not None:
                try:
                    fill_price = exact_decimal_add(
                        Decimal("0"),
                        to_decimal(
                            raw_fill_price,
                            name=f"{ticker} pending filled_avg_price",
                        ),
                        name=f"{ticker} pending fill-price normalization",
                    )
                except ValueError:
                    fill_price = Decimal("0")
                    unknown.add(ticker)
                if fill_price > 0:
                    try:
                        filled_value = exact_decimal_multiply(
                            filled_qty,
                            fill_price,
                            name=f"{ticker} pending filled value",
                        )
                        value = exact_decimal_subtract(
                            value,
                            filled_value,
                            name=f"{ticker} pending remaining notional",
                        )
                    except ValueError:
                        unknown.add(ticker)
                        continue
                    if value < 0:
                        value = Decimal("0")
                else:
                    unknown.add(ticker)
            try:
                totals[ticker] = exact_decimal_add(
                    totals.get(ticker, Decimal("0")),
                    value,
                    name=f"{ticker} total pending buy value",
                )
            except ValueError:
                unknown.add(ticker)
            continue

        raw_shares = order.get("shares")
        if raw_shares is None:
            unknown.add(ticker)
            continue
        try:
            shares = exact_decimal_add(
                Decimal("0"),
                to_decimal(raw_shares, name=f"{ticker} pending shares"),
                name=f"{ticker} pending shares normalization",
            )
            remaining_shares = exact_decimal_subtract(
                shares,
                filled_qty,
                name=f"{ticker} pending remaining shares",
            )
        except ValueError:
            unknown.add(ticker)
            continue
        if shares <= 0:
            unknown.add(ticker)
            continue
        if remaining_shares <= 0:
            continue

        raw_limit_price = order.get("limit_price")
        if raw_limit_price is None:
            unknown.add(ticker)
            continue
        try:
            limit_price = exact_decimal_add(
                Decimal("0"),
                to_decimal(
                    raw_limit_price,
                    name=f"{ticker} pending limit_price",
                ),
                name=f"{ticker} pending limit-price normalization",
            )
        except ValueError:
            unknown.add(ticker)
            continue
        if limit_price <= 0:
            unknown.add(ticker)
            continue
        try:
            remaining_value = exact_decimal_multiply(
                remaining_shares,
                limit_price,
                name=f"{ticker} pending remaining value",
            )
            totals[ticker] = exact_decimal_add(
                totals.get(ticker, Decimal("0")),
                remaining_value,
                name=f"{ticker} total pending buy value",
            )
        except ValueError:
            unknown.add(ticker)
    return totals, unknown


def estimate_pending_buy_value_by_ticker(open_orders: list[dict]) -> tuple[dict[str, float], set[str]]:
    """
    Estimated dollar value of currently pending (not-yet-filled) BUY
    orders, keyed by ticker -- deliberately does NOT make a live quote call
    (unlike assistant.execution_service._pending_buy_value_by_ticker(),
    which is allowed to since it gates real order submission). A UI
    preview refreshing on every rerun shouldn't fire a network call per
    pending order; instead, a pending order whose value can't be
    determined from the order itself (a plain market order with no
    notional or limit price) is reported back in the second return value
    so the caller can show the projection as incomplete rather than
    silently treating it as zero (GPT review, 2026-07-28).

    Originally lived in assistant/allocation_proposals.py (still
    re-exported there for backward compatibility); moved here so
    preview_trade_impact() below can share it without a circular import,
    since allocation_proposals.py itself imports from this module
    (independent review, 2026-07-31).
    """
    totals_decimal, unknown = _estimate_pending_buy_value_decimals(open_orders)
    totals: dict[str, float] = {}
    for ticker, value in totals_decimal.items():
        try:
            totals[ticker] = _finite_float(
                value,
                name=f"{ticker} pending buy display",
            )
        except ValueError:
            # The exact amount exists but cannot cross the legacy float
            # boundary safely. Keep it unavailable rather than publishing an
            # infinity or a rounded placeholder.
            unknown.add(ticker)
    return totals, unknown


def compute_portfolio_analytics(snapshot: PortfolioSnapshot) -> dict:
    # Analytics is a presentation projection over the same canonical
    # long-only evidence used by risk and execution. Revalidate here so a
    # caller cannot compute risk, mutate the packet, and still receive a
    # confident analytics payload from the stale earlier result.
    validate_long_only_portfolio_snapshot(snapshot)
    try:
        return _compute_validated_portfolio_analytics(snapshot)
    except PortfolioSnapshotIntegrityError:
        raise
    except ValueError as exc:
        raise PortfolioSnapshotIntegrityError(
            f"Portfolio analytics unavailable: {exc}"
        ) from exc


def _compute_validated_portfolio_analytics(snapshot: PortfolioSnapshot) -> dict:
    invested = exact_decimal_sum(
        (position.exact_field("market_value") for position in snapshot.positions),
        name="portfolio invested value",
    )
    cost_basis = exact_decimal_sum(
        (
            exact_decimal_multiply(
                position.exact_field("shares"),
                position.exact_field("entry_price"),
                name=f"{position.ticker} cost basis",
            )
            for position in snapshot.positions
        ),
        name="portfolio cost basis",
    )
    unrealized_pnl = exact_decimal_subtract(
        invested,
        cost_basis,
        name="portfolio unrealized P&L",
    )
    unrealized_pnl_pct = _percentage(
        unrealized_pnl,
        cost_basis,
        name="portfolio unrealized P&L percentage",
    )
    total_equity = snapshot.total_equity_exact_decimal
    weights = {
        position.ticker: _finite_float(
            _percentage(
                position.exact_field("market_value"),
                total_equity,
                name=f"{position.ticker} position weight",
            ),
            name=f"{position.ticker} position-weight display",
            quantum=_TWO_PLACES,
        )
        for position in snapshot.positions
    }
    return {
        "available": True,
        "unavailable_reason": None,
        "position_count": len(snapshot.positions),
        "invested_value": _finite_float(
            invested,
            name="portfolio invested-value display",
            quantum=_TWO_PLACES,
        ),
        "invested_pct": _finite_float(
            _percentage(
                invested,
                total_equity,
                name="portfolio invested percentage",
            ),
            name="portfolio invested-percentage display",
            quantum=_TWO_PLACES,
        ),
        "cash_value": _finite_float(
            snapshot.cash_exact_decimal,
            name="portfolio cash display",
            quantum=_TWO_PLACES,
        ),
        "unrealized_pnl": _finite_float(
            unrealized_pnl,
            name="portfolio unrealized-P&L display",
            quantum=_TWO_PLACES,
        ),
        "unrealized_pnl_pct": _finite_float(
            unrealized_pnl_pct,
            name="portfolio unrealized-P&L-percentage display",
            quantum=_TWO_PLACES,
        ),
        "position_weights_pct": weights,
        # An empty list is a proven zero only when the broker observation was
        # available. Read-only briefing degradation deliberately clears an
        # unusable order payload to [], so preserving None here prevents every
        # downstream presentation surface from turning unknown into zero.
        "open_order_count": (
            len(snapshot.open_orders)
            if snapshot.open_orders_available is True
            else None
        ),
    }


def preview_trade_impact(
    snapshot: PortfolioSnapshot,
    ticker: str,
    side: str,
    shares: int | str,
    reference_price: float,
) -> dict:
    normalized_side = str(side).strip().lower()
    if normalized_side not in {"buy", "sell"}:
        raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
    # Do not trust a risk result computed before a caller mutated this mutable
    # dataclass graph. The canonical validator is the one source of truth for
    # the long-only snapshot contract and exact/display companion agreement.
    validate_long_only_portfolio_snapshot(snapshot)
    if (
        normalized_side == "buy"
        and snapshot.open_orders_available is not True
    ):
        raise ValueError(
            "Cannot preview a buy while active-order data is unavailable; "
            "pending buy exposure is unknown."
        )
    ticker_upper = ticker.upper()
    quantity = to_decimal(shares, name="trade quantity")
    price_decimal = to_decimal(reference_price, name="reference price")
    trade_value = exact_decimal_multiply(
        quantity,
        price_decimal,
        name="preview trade value",
    )
    held_value = exact_decimal_sum(
        (
            p.exact_field("market_value")
            for p in snapshot.positions
            if p.ticker.upper() == ticker_upper
        ),
        name=f"{ticker_upper} held value",
    )
    held_shares = exact_decimal_sum(
        (
            p.exact_field("shares")
            for p in snapshot.positions
            if p.ticker.upper() == ticker_upper
        ),
        name=f"{ticker_upper} held shares",
    )
    # Independent review, 2026-07-31: this used to compute existing_value
    # purely from snapshot.positions, with no adjustment for this ticker's
    # own pending (not-yet-filled) buy orders -- unlike
    # risk/execution_gate.py, which explicitly folds pending_buy_value_by_ticker
    # into every exposure check specifically so two proposals approved
    # back-to-back can't each look individually fine while together
    # exceeding a cap. Folding the same same-ticker pending value in here
    # makes this per-proposal preview match what the execution gate (and
    # allocation_proposals.py's own build_allocation_plan()) actually see.
    pending_buy_value_by_ticker, pending_unknown_tickers = (
        _estimate_pending_buy_value_decimals(snapshot.open_orders)
    )
    pending_value = pending_buy_value_by_ticker.get(ticker_upper, Decimal("0"))
    total_pending_value = exact_decimal_sum(
        pending_buy_value_by_ticker.values(),
        name="total pending buy value",
    )
    existing_value = exact_decimal_add(
        held_value,
        pending_value,
        name=f"{ticker_upper} existing plus pending value",
    )
    signed_value = (
        trade_value
        if normalized_side == "buy"
        else exact_decimal_subtract(
            Decimal("0"), trade_value, name="signed sell trade value"
        )
    )
    post_position_value = exact_decimal_add(
        existing_value,
        signed_value,
        name=f"{ticker_upper} post-trade position value",
    )
    if post_position_value < 0:
        post_position_value = Decimal("0")
    post_cash = exact_decimal_subtract(
        exact_decimal_subtract(
            snapshot.cash_exact_decimal,
            total_pending_value,
            name="cash after pending buys",
        ),
        signed_value,
        name="cash after preview trade",
    )
    # Independent review, 2026-07-31 (P2 #3): this used to back out current
    # invested value as (total_equity - cash) -- a different formula from
    # compute_portfolio_analytics()'s direct sum(position.market_value).
    # Both are mathematically equal by the snapshot's own construction
    # invariant (see context_builder.py), but as two independently-rounded
    # float computations they can drift by a cent of float epsilon. Reusing
    # the exact same direct-sum formula here removes the drift instead of
    # merely making it rare.
    current_invested = exact_decimal_sum(
        (p.exact_field("market_value") for p in snapshot.positions),
        name="current invested value",
    )
    post_invested = exact_decimal_add(
        exact_decimal_add(
            current_invested,
            total_pending_value,
            name="invested value after pending buys",
        ),
        signed_value,
        name="invested value after preview trade",
    )
    total = snapshot.total_equity_exact_decimal
    return {
        "trade_value": _finite_float(
            trade_value,
            name="preview trade-value display",
            quantum=_TWO_PLACES,
        ),
        # Proposal-time share identity lets execution detect a split-shaped
        # broker snapshot change even in the fail-open direction where a
        # forward split leaves MORE than enough shares to submit the old
        # quantity. Stored as decimal text, never reconstructed from display
        # rounding.
        "position_shares_before": decimal_text(held_shares),
        "position_weight_before_pct": _finite_float(
            _percentage(
                existing_value,
                total,
                name=f"{ticker_upper} pre-trade position weight",
            ),
            name=f"{ticker_upper} pre-trade position-weight display",
            quantum=_TWO_PLACES,
        ),
        "position_weight_after_pct": _finite_float(
            _percentage(
                post_position_value,
                total,
                name=f"{ticker_upper} post-trade position weight",
            ),
            name=f"{ticker_upper} post-trade position-weight display",
            quantum=_TWO_PLACES,
        ),
        "cash_before": _finite_float(
            snapshot.cash_exact_decimal,
            name="preview cash-before display",
            quantum=_TWO_PLACES,
        ),
        "cash_after": _finite_float(
            post_cash,
            name="preview cash-after display",
            quantum=_TWO_PLACES,
        ),
        "invested_pct_after": _finite_float(
            _percentage(
                post_invested,
                total,
                name="post-trade invested percentage",
            ),
            name="post-trade invested-percentage display",
            quantum=_TWO_PLACES,
        ),
        "pending_buy_value": _finite_float(
            pending_value,
            name=f"{ticker_upper} pending-buy display",
            quantum=_TWO_PLACES,
        ),
        "pending_buy_total_value": _finite_float(
            total_pending_value,
            name="total pending-buy display",
            quantum=_TWO_PLACES,
        ),
        "pending_buy_unknown_tickers": sorted(pending_unknown_tickers),
        "open_orders_available": snapshot.open_orders_available is True,
        "projection_complete": (
            snapshot.open_orders_available is True
            and not pending_unknown_tickers
        ),
    }
