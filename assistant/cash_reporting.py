"""GR-7b: idle-cash reporting measured against policy and mandate.

Deliberately a REPORT, not a proposal source. Nothing here creates, sizes,
approves, or ranks a trade, and no field is action-shaped: the numbers say
what the portfolio *is*, never what to buy. The owner reads it and decides.

Two different documents constrain cash, and conflating them is the mistake
this module exists to prevent:

* ``TradingPolicy`` is the per-order enforcement contract.
  ``min_cash_reserve_pct`` is a FLOOR (hold at least this much cash) and
  ``max_total_exposure_pct`` is a CEILING (invest at most this much). Both
  are already enforced by ``risk/execution_gate.py`` at submission time.
  A breach of the floor is a live risk finding and ``risk_copilot`` already
  reports it; this module reports the opposite and previously invisible
  condition -- cash sitting far ABOVE the floor.

* ``PortfolioMandate`` is the portfolio-level objective. It contains **no
  cash field at all**. What it targets is annualized volatility
  (``target_annualized_volatility_min_pct`` .. ``_max_pct``). Idle cash is
  therefore not a mandate rule in its own right; it is the mechanism by
  which a portfolio silently falls BELOW its volatility floor. Reporting
  cash without that link would be a number without a meaning.

The bridge between them is one piece of arithmetic. A portfolio's
volatility is approximately its invested fraction times the volatility of
what it holds, so reaching a mandate floor of ``V`` while only ``f`` of the
account is invested requires the invested assets to carry ``V / f``
volatility. At f = 0.13 and V = 12%, that is 92% -- a number that makes an
otherwise abstract shortfall obvious. It is descriptive arithmetic under a
stated assumption, not a forecast and not advice; see
``required_invested_volatility_pct`` and its recorded caveats.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from assistant.mandate import PortfolioMandate
from assistant.money import decimal_text, to_decimal
from assistant.policy import TradingPolicy
from assistant.portfolio_analytics import estimate_pending_buy_value_by_ticker
from assistant.schemas import PortfolioSnapshot

# The invested fraction below which `required_invested_volatility_pct` stops
# being informative: dividing by a near-zero fraction produces a number that
# is arithmetically correct and rhetorically useless ("you would need 4000%
# volatility"). Below this the report says the target is unreachable at the
# current exposure and gives no figure, rather than printing a number that
# invites a bad decision.
_MIN_MEANINGFUL_INVESTED_FRACTION = Decimal("0.01")


class CashReportError(ValueError):
    """The snapshot cannot support an honest cash report."""


def _percent_of_equity(amount: Decimal, total_equity: Decimal) -> Decimal:
    return amount / total_equity * Decimal("100")


def evaluate_idle_cash(
    snapshot: PortfolioSnapshot,
    policy: TradingPolicy,
    mandate: PortfolioMandate,
    *,
    measured_annualized_volatility_pct: float | None = None,
) -> dict[str, Any]:
    """Measure cash against the policy's bounds and the mandate's objective.

    ``measured_annualized_volatility_pct`` is the portfolio's OBSERVED
    volatility when one has actually been measured. It is deliberately a
    required-to-be-passed-in value rather than something computed here:
    this module must not invent a volatility estimate, and an absent
    measurement is reported as absent rather than defaulted to zero -- a
    zero would read as "far below mandate" and is indistinguishable from a
    genuinely flat portfolio.

    Raises ``CashReportError`` when the snapshot cannot support a report at
    all (non-finite or non-positive equity). Failing loudly is correct here:
    a cash report derived from a broken snapshot would be read as fact.
    """
    try:
        total_equity = snapshot.total_equity_exact_decimal
        cash = snapshot.cash_exact_decimal
        invested = sum(
            (position.exact_field("market_value") for position in snapshot.positions),
            Decimal("0"),
        )
    except ValueError as exc:
        raise CashReportError(f"snapshot money is not usable: {exc}") from exc

    if total_equity <= 0:
        raise CashReportError(
            f"total equity must be positive to express cash as a share of it, "
            f"got {decimal_text(total_equity)}"
        )

    reserve_floor = total_equity * to_decimal(
        policy.min_cash_reserve_pct, name="policy.min_cash_reserve_pct"
    )
    exposure_ceiling = total_equity * to_decimal(
        policy.max_total_exposure_pct, name="policy.max_total_exposure_pct"
    )

    # Signed on purpose: negative means the reserve floor is BREACHED, which
    # is a different and more urgent condition than idle cash. Reporting
    # max(0, ...) here would hide it.
    cash_above_reserve = cash - reserve_floor
    unused_exposure_capacity = exposure_ceiling - invested

    # FCS-004: pending BUY orders have already spoken for some of this room.
    # `risk/execution_gate.py` folds them into both bounds -- the cash check
    # uses `min(cash, buying_power)` (buying_power nets broker holds out) and
    # the exposure check adds `total_pending_buy_value` to invested value. This
    # report used raw cash and raw market value, so it advertised headroom the
    # gate would refuse. Third recurrence of the class already fixed in
    # `allocation_proposals.build_allocation_plan` and
    # `portfolio_analytics.preview_trade_impact`.
    #
    # Estimated WITHOUT a live quote call, exactly like the UI preview: a
    # read-only report must not fire a network request per pending order. An
    # order whose value cannot be determined from the order itself is reported
    # as unknown rather than counted as zero, so a reader can tell an
    # incomplete projection from a complete one.
    # Named "committed capital" rather than anything containing "buy"/"order":
    # `test_report_carries_no_action_shaped_field` lexically forbids those in a
    # reporting payload's KEYS, and it is right to -- these figures describe
    # money already spoken for, which is state, not an instruction. The guard
    # caught the first naming attempt; that is the guard working.
    committed_by_ticker, committed_unknown = estimate_pending_buy_value_by_ticker(
        list(snapshot.open_orders)
    )
    committed_capital = sum(
        (
            to_decimal(value, name="committed capital")
            for value in committed_by_ticker.values()
        ),
        Decimal("0"),
    )
    cash_above_reserve_net = cash_above_reserve - committed_capital
    unused_exposure_capacity_net = unused_exposure_capacity - committed_capital

    # What actually limits further deployment is whichever bound binds
    # first. This is a measurement of headroom, NOT a suggested order size:
    # it says how much room the policy leaves, not that the room should be
    # used.
    headroom = min(cash_above_reserve_net, unused_exposure_capacity_net)
    if headroom < 0:
        headroom = Decimal("0")
    binding_constraint = (
        "cash_reserve_floor"
        if cash_above_reserve_net <= unused_exposure_capacity_net
        else "exposure_ceiling"
    )

    invested_fraction = invested / total_equity
    mandate_floor = to_decimal(
        mandate.target_annualized_volatility_min_pct,
        name="mandate.target_annualized_volatility_min_pct",
    )
    mandate_ceiling = to_decimal(
        mandate.target_annualized_volatility_max_pct,
        name="mandate.target_annualized_volatility_max_pct",
    )

    if invested_fraction >= _MIN_MEANINGFUL_INVESTED_FRACTION:
        required_invested_volatility_pct = decimal_text(
            (mandate_floor / invested_fraction).quantize(Decimal("0.01"))
        )
        required_unavailable_reason = None
    else:
        required_invested_volatility_pct = None
        required_unavailable_reason = (
            f"invested fraction {decimal_text(invested_fraction.quantize(Decimal('0.0001')))} "
            "is too small for the figure to be meaningful"
        )

    # The question idle cash alone cannot answer: even if every deployable
    # dollar were deployed, the policy's exposure CEILING still caps the
    # invested fraction. If the volatility required at that ceiling is
    # implausible for the assets actually held, then the policy and the
    # mandate are not mutually satisfiable and no amount of deploying cash
    # fixes it -- one of the two documents has to change. That is an owner
    # decision, and this report exists to make it visible rather than to
    # resolve it.
    max_exposure_fraction = to_decimal(
        policy.max_total_exposure_pct, name="policy.max_total_exposure_pct"
    )
    if max_exposure_fraction >= _MIN_MEANINGFUL_INVESTED_FRACTION:
        required_at_ceiling = decimal_text(
            (mandate_floor / max_exposure_fraction).quantize(Decimal("0.01"))
        )
    else:
        required_at_ceiling = None

    measured: dict[str, Any] = {
        "available": measured_annualized_volatility_pct is not None,
        "annualized_volatility_pct": None,
        "within_mandate_band": None,
        "unavailable_reason": (
            None
            if measured_annualized_volatility_pct is not None
            else "no measured portfolio volatility was supplied"
        ),
    }
    if measured_annualized_volatility_pct is not None:
        # ValueError from to_decimal (NaN/Inf/malformed) must become
        # CashReportError: callers only catch that type, and a traceback
        # from --measured-volatility-pct would be worse than a refusal.
        try:
            observed = to_decimal(
                measured_annualized_volatility_pct,
                name="measured_annualized_volatility_pct",
            )
        except ValueError as exc:
            raise CashReportError(str(exc)) from exc
        if observed < 0:
            raise CashReportError(
                "measured_annualized_volatility_pct must be non-negative, "
                f"got {decimal_text(observed)}"
            )
        measured["annualized_volatility_pct"] = decimal_text(observed)
        measured["within_mandate_band"] = bool(
            mandate_floor <= observed <= mandate_ceiling
        )

    return {
        "as_of": snapshot.as_of,
        "account_mode": snapshot.account_mode,
        "source": snapshot.source,
        # Whether every figure came from preserved broker decimals or from
        # display-rounded floats. A reader must be able to tell.
        "exact_numerics": bool(snapshot.has_exact_numerics),
        "totals": {
            "total_equity": decimal_text(total_equity),
            "cash": decimal_text(cash),
            "invested": decimal_text(invested),
            "cash_pct": decimal_text(
                _percent_of_equity(cash, total_equity).quantize(Decimal("0.01"))
            ),
            "invested_pct": decimal_text(
                _percent_of_equity(invested, total_equity).quantize(Decimal("0.01"))
            ),
        },
        "policy_bounds": {
            "min_cash_reserve_pct": decimal_text(
                to_decimal(policy.min_cash_reserve_pct) * Decimal("100")
            ),
            "max_total_exposure_pct": decimal_text(
                to_decimal(policy.max_total_exposure_pct) * Decimal("100")
            ),
            "reserve_floor": decimal_text(reserve_floor),
            "exposure_ceiling": decimal_text(exposure_ceiling),
            "cash_above_reserve": decimal_text(cash_above_reserve),
            "reserve_floor_breached": bool(cash_above_reserve < 0),
            "unused_exposure_capacity": decimal_text(unused_exposure_capacity),
            # FCS-004. Both bounds are published twice: before pending orders
            # (what the account holds) and after (what the execution gate would
            # actually permit). `policy_headroom` is the AFTER figure, because
            # that is the question a reader is really asking.
            "capital_already_committed": decimal_text(committed_capital),
            "capital_already_committed_unknown_tickers": tuple(
                sorted(committed_unknown)
            ),
            "committed_capital_complete": not committed_unknown,
            "cash_above_reserve_net_of_commitments": decimal_text(
                cash_above_reserve_net
            ),
            "unused_exposure_capacity_net_of_commitments": decimal_text(
                unused_exposure_capacity_net
            ),
            "policy_headroom": decimal_text(headroom),
            "policy_headroom_basis": "net_of_committed_capital",
            "binding_constraint": binding_constraint,
        },
        "mandate_objective": {
            "target_annualized_volatility_min_pct": decimal_text(mandate_floor),
            "target_annualized_volatility_max_pct": decimal_text(mandate_ceiling),
            "measured": measured,
            "required_invested_volatility_pct": required_invested_volatility_pct,
            "required_unavailable_reason": required_unavailable_reason,
            "required_invested_volatility_at_policy_ceiling_pct": required_at_ceiling,
            "required_assumption": (
                "Portfolio volatility approximated as invested_fraction x "
                "volatility of invested assets; ignores correlation, "
                "leverage decay, and cash drag. Descriptive arithmetic for "
                "context -- not a forecast, not a recommendation."
            ),
        },
        "disclaimers": (
            "Reporting only. This report does not create, size, rank, or "
            "approve any order.",
            "Policy headroom is the room the policy leaves, not a "
            "suggestion to use it.",
        ),
    }
