"""
Discrete (single-ticker, owner-chosen) trade sizing.

Owner request 2026-08-14: the Buying and Selling tabs are budget-driven and
policy-driven respectively; the owner also wants to buy or sell ONE named
ticker on their own judgement, sized either by share count or by dollar
amount.

This module owns exactly one thing: converting a dollar amount into a whole
share count, and back. It deliberately does not create proposals — those go
through the already-reviewed generators (`assistant.allocation_proposals` for
buys, `assistant.user_directed_sell` for sells) so a discrete trade inherits
every check those paths already passed rather than growing a parallel one.

**A dollar amount is a BUDGET, not a notional order** (owner decision,
2026-08-14). $500 at $301.51 buys 1 share and leaves $198.49 unspent, and the
caller must show that remainder. This project submits whole-share orders only,
enforced independently by `risk.execution_gate.is_valid_share_quantity`, by
`execution.alpaca_broker`'s own copy of that check, and by the sell
generator's floor. True fractional/notional orders would break all three plus
tax-lot accounting and the never-short guard, and are out of scope.

Every calculation here is exact `Decimal`. That is not stylistic: the
2026-08-13 independent review (SELREV-002) found `shares * price` in binary
float refusing a valid 3-share order at $0.10 against a $0.30 cap, because
`3 * 0.10` is `0.30000000000000004`. Money arithmetic in this project goes
through `assistant.money`.
"""
from __future__ import annotations

import dataclasses
from decimal import ROUND_FLOOR, Decimal, DecimalException

from assistant.money import decimal_or_none, decimal_text


# Keep the conversion bounded before Decimal is converted to a Python int.
# A finite value such as ``1e999999999`` is valid Decimal syntax but would
# otherwise overflow during division or attempt an enormous integer
# allocation. This is far beyond a broker-representable whole-share order;
# the UI must refuse it as input, not lose the entire page.
_MAX_SIZABLE_SHARES = Decimal(2**63 - 1)


@dataclasses.dataclass(frozen=True)
class DollarSizing:
    """What a dollar budget actually buys, and what it cannot."""

    shares: int
    notional_text: str
    unallocated_text: str
    reference_price_text: str

    @property
    def affordable(self) -> bool:
        return self.shares > 0


def size_by_dollar_amount(dollar_amount: object, price: object) -> dict:
    """Whole shares a budget affords at `price`, floored, with the remainder.

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

    try:
        whole_shares = (amount / price_decimal).to_integral_value(
            rounding=ROUND_FLOOR
        )
    except DecimalException:
        return {
            "ok": False,
            "reason": "The resulting whole-share quantity is too large to size safely.",
        }
    if whole_shares > _MAX_SIZABLE_SHARES:
        return {
            "ok": False,
            "reason": "The resulting whole-share quantity is too large to size safely.",
        }
    shares = int(whole_shares)
    if shares <= 0:
        return {
            "ok": False,
            "reason": (
                f"{decimal_text(amount)} does not cover one share at "
                f"{decimal_text(price_decimal)}."
            ),
        }
    try:
        notional = price_decimal * shares
        unallocated = amount - notional
    except DecimalException:
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


def notional_for_shares(shares: object, price: object) -> dict:
    """The exact cost of a whole-share quantity at `price`.

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
    if not isinstance(shares, int) or isinstance(shares, bool) or shares <= 0:
        return {
            "ok": False,
            "reason": f"Shares must be a whole number greater than zero, got {shares!r}.",
        }
    return {
        "ok": True,
        "notional_text": decimal_text(price_decimal * shares),
        "reference_price_text": decimal_text(price_decimal),
    }
