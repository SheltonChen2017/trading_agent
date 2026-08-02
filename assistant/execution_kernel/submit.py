"""Broker submission sizing.

GR-1A extraction. Deliberately narrow: this module may not import
proposal-generation code (pinned by
tests/test_ml_import_boundary.py::test_execution_kernel_never_imports_proposal_generation).
The submission path executes a decision; it must never participate in making
one.
"""
from __future__ import annotations

from decimal import Decimal

from assistant.money import MoneyInput
from risk.execution_gate import TradeIntent, worst_case_fill_price_decimal


def _execution_budget_notional(
    intent: TradeIntent, reference_price: MoneyInput
) -> Decimal:
    """Gross submitted notional reserved against the persistent daily cap.

    This intentionally uses the same side-aware price as the risk gate:
    an aggressive BUY limit is priced at the higher limit, while a SELL
    remains at the reference price so a risk-reducing order is not blocked
    merely because its limit is above the quote.
    """
    return Decimal(intent.shares) * worst_case_fill_price_decimal(
        intent, reference_price
    )
