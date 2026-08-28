"""
Discrete (single-ticker, owner-chosen) trade sizing.

Owner request 2026-08-14: the Buying and Selling tabs are budget-driven and
policy-driven respectively; the owner also wants to buy or sell ONE named
ticker on their own judgement, sized either by share count or by dollar
amount.

This module owns exactly one thing: converting a dollar amount into the exact
policy-permitted share quantity, and back. It deliberately does not create proposals — those go
through the already-reviewed generators (`assistant.allocation_proposals` for
buys, `assistant.user_directed_sell` for sells) so a discrete trade inherits
every check those paths already passed rather than growing a parallel one.

**A dollar amount is a BUDGET, not a broker-notional order.** In strict mode,
$500 at $301.51 buys 1 share and leaves $198.49. In fractional mode the same
budget is converted down to an exact quantity with at most nine decimal
places, and only the sub-cent rounding remainder is left. The caller must show
the resulting quantity and remainder in either mode.

Every calculation here is exact `Decimal`. That is not stylistic: the
2026-08-13 independent review (SELREV-002) found `shares * price` in binary
float refusing a valid 3-share order at $0.10 against a $0.30 cap, because
`3 * 0.10` is `0.30000000000000004`. Money arithmetic in this project goes
through `assistant.money`.
"""
from __future__ import annotations

import dataclasses
from decimal import Context, ROUND_FLOOR, Decimal, DecimalException, localcontext

from assistant.money import (
    decimal_or_none,
    decimal_text,
    exact_decimal_add,
    exact_decimal_multiply,
    exact_decimal_subtract,
)
from risk.execution_gate import (
    MAX_ORDER_QUANTITY,
    canonical_order_quantity,
    order_quantity_decimal,
)


# Keep the conversion bounded before Decimal is converted to a Python int.
# A finite value such as ``1e999999999`` is valid Decimal syntax but would
# otherwise overflow during division or attempt an enormous integer
# allocation. This is far beyond a broker-representable whole-share order;
# the UI must refuse it as input, not lose the entire page.
#
# SET1CR-002: the bound itself now lives with the quantity authority in
# `risk.execution_gate`, because sizing something the gate would then refuse
# (or vice versa) is exactly the drift this project consolidates away. The
# alias is kept so this module's existing call sites and their tests keep
# reading in local terms.
_MAX_SIZABLE_SHARES = MAX_ORDER_QUANTITY
_FRACTIONAL_QUANTUM = Decimal("0.000000001")
_FLOOR_CONTEXT_PRECISION = 64


def _floor_budget_quantity(
    amount: Decimal,
    price: Decimal,
    *,
    whole_shares_only: bool,
) -> Decimal | None:
    """Return the greatest permitted quantity that cannot exceed ``amount``.

    Division is a projection, so it uses an explicit floor-rounded context.
    Exact cross-products on both sides then prove that the result neither
    overspends nor leaves one additional share quantum affordable.
    """
    quantum = Decimal("1") if whole_shares_only else _FRACTIONAL_QUANTUM
    try:
        maximum_notional = exact_decimal_multiply(
            price,
            _MAX_SIZABLE_SHARES,
            name="maximum discrete-trade notional",
        )
    except ValueError:
        return None
    if amount > maximum_notional:
        return None

    try:
        with localcontext(
            Context(prec=_FLOOR_CONTEXT_PRECISION, rounding=ROUND_FLOOR)
        ):
            quotient = amount / price
            sized = (
                quotient.to_integral_value(rounding=ROUND_FLOOR)
                if whole_shares_only
                else quotient.quantize(quantum, rounding=ROUND_FLOOR)
            )
        notional = exact_decimal_multiply(
            sized,
            price,
            name="floored discrete-trade notional",
        )
        if notional > amount:
            # Defensive correction if a future Decimal implementation ever
            # violates the floor-context assumption. Never return an
            # overspending quantity.
            sized = exact_decimal_subtract(
                sized,
                quantum,
                name="discrete-trade floor correction",
            )
            if sized < 0:
                return None
            notional = exact_decimal_multiply(
                sized,
                price,
                name="corrected discrete-trade notional",
            )
            if notional > amount:
                return None

        if sized < _MAX_SIZABLE_SHARES:
            next_quantity = exact_decimal_add(
                sized,
                quantum,
                name="next discrete-trade quantity",
            )
            next_notional = exact_decimal_multiply(
                next_quantity,
                price,
                name="next discrete-trade notional",
            )
            if next_notional <= amount:
                # A fixed projection that undersized by a whole quantum is
                # not the exact budget conversion this API promises.
                return None
    except (DecimalException, ValueError):
        return None
    return sized


@dataclasses.dataclass(frozen=True)
class DollarSizing:
    """What a dollar budget actually buys, and what it cannot."""

    shares: int | str
    notional_text: str
    unallocated_text: str
    reference_price_text: str

    @property
    def affordable(self) -> bool:
        quantity = order_quantity_decimal(self.shares, whole_shares_only=False)
        return quantity is not None and quantity > 0


def size_by_dollar_amount(
    dollar_amount: object, price: object, *, whole_shares_only: bool = True
) -> dict:
    """Policy-permitted shares a budget affords, floored, with remainder.

    Returns ``{"ok": True, "sizing": DollarSizing}`` or
    ``{"ok": False, "reason": str}``. Never raises for ordinary bad input:
    a refusal is a sentence the caller can show verbatim.

    Floors deliberately. Rounding up would spend money the owner did not
    budget, and — on the sell side — could propose disposing of more shares
    than are held, which this project never does.
    """
    amount = decimal_or_none(dollar_amount)
    if amount is None:
        return {
            "ok": False,
            "reason": f"The dollar amount {dollar_amount!r} is not a usable number.",
        }
    if amount <= 0:
        return {"ok": False, "reason": "The dollar amount must be greater than zero."}

    price_decimal = decimal_or_none(price)
    if price_decimal is None or price_decimal <= 0:
        return {
            "ok": False,
            "reason": (
                f"There is no usable reference price ({price!r}), so a dollar "
                "amount cannot be converted into shares."
            ),
        }

    sized_quantity = _floor_budget_quantity(
        amount,
        price_decimal,
        whole_shares_only=whole_shares_only,
    )
    if sized_quantity is None:
        return {
            "ok": False,
            "reason": "The resulting share quantity is too large to size safely.",
        }
    if sized_quantity > _MAX_SIZABLE_SHARES:
        return {
            "ok": False,
            "reason": "The resulting share quantity is too large to size safely.",
        }
    shares = canonical_order_quantity(
        int(sized_quantity) if whole_shares_only else sized_quantity,
        whole_shares_only=whole_shares_only,
    )
    if shares is None:
        return {
            "ok": False,
            "reason": (
                (
                    f"{decimal_text(amount)} does not cover one share at "
                    f"{decimal_text(price_decimal)}."
                    if whole_shares_only
                    else f"{decimal_text(amount)} does not cover the minimum "
                    f"0.000000001-share quantity at {decimal_text(price_decimal)}."
                )
            ),
        }
    try:
        quantity_decimal = order_quantity_decimal(
            shares, whole_shares_only=whole_shares_only
        )
        if quantity_decimal is None:
            raise ValueError("canonical quantity has no exact representation")
        notional = exact_decimal_multiply(
            price_decimal,
            quantity_decimal,
            name="discrete-trade notional",
        )
        unallocated = exact_decimal_subtract(
            amount,
            notional,
            name="discrete-trade unallocated budget",
        )
        if unallocated < 0:
            raise ValueError("sized quantity exceeds the owner budget")
    except (DecimalException, ValueError):
        return {
            "ok": False,
            "reason": "The resulting dollar calculation is too large to size safely.",
        }
    return {
        "ok": True,
        "sizing": DollarSizing(
            shares=shares,
            notional_text=decimal_text(notional),
            unallocated_text=decimal_text(unallocated),
            reference_price_text=decimal_text(price_decimal),
        ),
    }


def notional_for_shares(
    shares: object, price: object, *, whole_shares_only: bool = True
) -> dict:
    """The exact cost of a policy-permitted share quantity at `price`.

    The share-mode counterpart of `size_by_dollar_amount`, so both modes of
    both discrete tabs report money the same way instead of one of them
    formatting a float.
    """
    price_decimal = decimal_or_none(price)
    if price_decimal is None or price_decimal <= 0:
        return {
            "ok": False,
            "reason": f"There is no usable reference price ({price!r}).",
        }
    quantity = order_quantity_decimal(
        shares, whole_shares_only=whole_shares_only
    )
    if quantity is None:
        return {
            "ok": False,
            "reason": (
                "Shares must be a whole number greater than zero."
                if whole_shares_only
                else "Shares must be a positive exact number with at most 9 decimal places."
            ),
        }
    try:
        notional = exact_decimal_multiply(
            price_decimal,
            quantity,
            name="share-mode discrete-trade notional",
        )
    except ValueError:
        return {
            "ok": False,
            "reason": "The resulting dollar calculation is too large to size safely.",
        }
    return {
        "ok": True,
        "notional_text": decimal_text(notional),
        "reference_price_text": decimal_text(price_decimal),
    }
