"""Fabricated CLR callback contracts only; NOT a LEAN/QC execution proof."""
from __future__ import annotations

import dataclasses
from decimal import Decimal, localcontext
from fractions import Fraction
from types import SimpleNamespace as NS

import pytest

from scripts import short_interest_lean_joint_transport as bridge
from research.short_interest_etf import native_qc_order_representation as rep


class FabricatedRuntime:
    """Same public default portfolio callback sequence, no CLR assembly/data."""
    def __init__(self):
        self.at, self.native_cash = "2023-01-03T14:30:00Z", Decimal(4800000)
        self.next_id, self.fault, self.hub = 0, None, None
        self.operations = []

    def decimal(self, obj, *path):
        for name in path:
            obj = getattr(obj, name)
        # Fabricated native values are typed exact Decimal, not repaired float.
        if type(obj) is not Decimal:
            raise bridge._refuse("fabricated_native_property_not_Decimal")
        return bridge.exact_decimal_text(format(obj, "f"))

    def utc(self, obj, name):
        at = getattr(obj, name)
        rep._stamp(at)
        return at

    def now(self):
        return self.at

    def symbol(self, obj):
        return obj.Symbol.Value

    def cash(self):
        return self.decimal(NS(Amount=self.native_cash), "Amount")

    def fee(self, amount):
        return NS(Value=NS(Amount=amount, Currency="USD"))

    def make_fill(self, order, scheduled):
        o = scheduled.transport_order
        return NS(OrderId=order.Id, Symbol=order.Symbol, UtcTime=scheduled.at,
                  FillQuantity=o.submitted_quantity, FillPrice=o.fill_price,
                  FillPriceCurrency="USD", OrderFee=self.fee(o.fee_usd), Status="Filled")

    def is_market(self, order):
        return order.Type == "Market"

    def is_base(self, security):
        return security.Type == "Base"

    def is_filled(self, event):
        return event.Status == "Filled"

    def is_nonterminal_notice(self, event):
        return event.Status in ("New", "Submitted")

    def post_cash(self, amount):
        self.operations.append(("notional_or_corporate_cash", amount))
        if self.fault == "double_post":
            amount = bridge._sum((amount, amount))
        self.native_cash = bridge._sum((self.native_cash, amount))

    def set_holdings(self, security, *, average_price, quantity):
        self.operations.append(("explicit_corporate_holdings", quantity))
        security.Holdings.Quantity, security.Holdings.AveragePrice = quantity, average_price

    def sufficient(self, enough, reason=""):
        return NS(IsSufficient=enough, Reason=reason)

    def buying_power(self, amount):
        return NS(Value=amount)

    def initial_margin(self, amount):
        return NS(Value=amount)

    def maintenance_margin(self, amount):
        return NS(Value=amount)

    def sizing_refused(self):
        return NS(Quantity=Decimal(0), IsError=True, Reason="native_sizing_forbidden")

    def submit(self, security, quantity, tag):
        self.next_id += 1
        if self.fault == "whole_share_round":
            quantity = Decimal(int(quantity))
        order = NS(Id=self.next_id, Symbol=security.Symbol, Quantity=quantity,
                   Tag=tag, Type="Market", Time=self.at)
        # Submitted can precede model calls; the eventual full order still must
        # match its tag, type, exact decimal quantity and source book.
        self.hub.on_order_event(NS(OrderId=order.Id, Symbol=order.Symbol,
                                  UtcTime=self.at, Status="Submitted"))
        params = NS(Security=security, Order=order)
        if not security.BuyingPowerModel.HasSufficientBuyingPowerForOrder(params).IsSufficient:
            raise bridge._refuse("fabricated_native_buying_power_rejected")
        fee = security.FeeModel.GetOrderFee(params)
        event = security.FillModel.Fill(params)
        assert event.OrderFee.Value.Amount == fee.Value.Amount
        if self.fault == "partial":
            event.FillQuantity = rep._decimal(Fraction(event.FillQuantity) / 2)
        # Public default SecurityPortfolioModel applies fee before settlement.
        if self.fault != "missing_fee":
            self.native_cash = bridge._sum((self.native_cash, -fee.Value.Amount))
            security.Holdings.TotalFees = bridge._sum((security.Holdings.TotalFees, fee.Value.Amount))
        self.operations.append(("native_default_fee", fee.Value.Amount))
        with localcontext() as ctx:
            ctx.prec = 28
            default_product = -(event.FillQuantity * event.FillPrice)
        security.SettlementModel.ApplyFunds(NS(Security=security, Fill=event,
                    CashAmount=NS(Amount=default_product, Currency="USD")))
        if self.fault == "duplicate_settlement":
            security.SettlementModel.ApplyFunds(NS(Security=security, Fill=event,
                    CashAmount=NS(Amount=default_product, Currency="USD")))
        security.Holdings.Quantity = bridge._sum((security.Holdings.Quantity, event.FillQuantity))
        security.Holdings.AveragePrice = event.FillPrice if security.Holdings.Quantity else Decimal(0)
        self.operations.append(("native_default_holdings", security.Holdings.Quantity))
        if self.fault == "extra_cash":
            self.native_cash = bridge._sum((self.native_cash, Decimal("0.000000000000000001")))
        if self.fault == "submitted_only":
            return order
        self.hub.on_order_event(event)
        if self.fault == "duplicate_fill":
            self.hub.on_order_event(event)
        return order


def setup(cells=rep.CELL_IDS):
    runtime = FabricatedRuntime()
    hub = bridge.JointTransport(runtime)
    runtime.hub = hub
    for cell in cells:
        alias = rep.security_alias(cell, "native:fabricated-class")
        security = NS(Symbol=NS(Value=alias), Type="Base", QuoteCurrency=NS(Symbol="USD"),
            SymbolProperties=NS(LotSize=Decimal("1e-18"), MinimumPriceVariation=Decimal("1e-18"),
                                ContractMultiplier=Decimal(1)),
            Holdings=NS(Quantity=Decimal(0), AveragePrice=Decimal(0), TotalFees=Decimal(0)),
            Price=Decimal(5))
        hub.register_security(cell, "native:fabricated-class", security)
        security.FeeModel, security.FillModel = bridge.ExactFeeModel(hub), bridge.ExactFillModel(hub)
        security.BuyingPowerModel = bridge.CellBuyingPowerModel(hub)
        security.SettlementModel = bridge.PostedNotionalSettlement(hub)
    return runtime, hub


def proposed(hub, cell, *, side="buy", price=Fraction(13, 3), quantity=None,
             at="2023-01-03T14:30:00Z", event="entry", order_id="entry-order"):
    hub.runtime.at = at
    if quantity is None:
        rate = Fraction(int(cell.split("-C")[1].split("-")[0]), 10000)
        quantity = hub.book(cell).transport.economic_cash / (price * (1 + rate))
    result = rep.prepare_cell_order(hub.book(cell), at=at, security_id="native:fabricated-class",
        event_id=event, order_id=order_id, side=side, economic_quantity=quantity, economic_price=price)
    hub.offer_raw_open(rep.security_alias(cell, "native:fabricated-class"), at=at, raw_open=price)
    return result


def test_no_actual_or_QC_authority_or_runtime_claim_from_draft():
    design = bridge.transport_design()
    assert len(design["cell_ids"]) == 48
    assert not design["runtime_executed"] and not design["qc_completed"]
    assert all(not x for x in design["authority"].values())
    with pytest.raises(bridge.LeanTransportRefusal, match="not_source_processing"):
        bridge.require_actual_execution(owner_preauthorized=True, engine=True, source=True)


@pytest.mark.parametrize("bad", [1.0, Decimal(1), 1, None, "NaN", "Infinity", "1,000", " 1", "1 ", "1e-29", "1e29"])
def test_decimal_boundary_never_repairs_float_or_unbounded_native_money(bad):
    with pytest.raises(bridge.LeanTransportRefusal):
        bridge.exact_decimal_text(bad)


def test_invariant_selected_property_string_retains_fractional_scale():
    assert bridge.exact_decimal_text("1234567.890123456789012345") == Decimal("1234567.890123456789012345")
    assert bridge.exact_decimal_text("1E-18") == Decimal("1e-18")


def test_one_joint_family_48_full_fee_reserved_round_trips_reconcile_exact_economics():
    rt, hub = setup()
    expected = {}
    for cell in rep.CELL_IDS:
        scheduled = proposed(hub, cell)
        expected[cell] = scheduled.transport_order.economic_quantity
        hub.submit(scheduled)
        assert hub.book(cell).transport.economic_cash == 0
        assert hub.book(cell).transport.positions[0].economic_quantity == expected[cell]
        assert hub.book(cell).transport.positions[0].mirror_quantity % Decimal(1) != 0
    assert len(hub.reconcile()) > 0
    for cell in rep.CELL_IDS:
        scheduled = proposed(hub, cell, side="sell", price=Fraction(14, 3), quantity=expected[cell],
                   at="2023-01-17T14:30:00Z", event="exit", order_id="exit-order")
        hub.submit(scheduled)
        rate = Fraction(int(cell.split("-C")[1].split("-")[0]), 10000)
        book = hub.book(cell)
        assert book.transport.economic_cash == expected[cell] * Fraction(14, 3) * (1 - rate)
        assert book.transport.positions == ()
    hub.reconcile()
    assert rep.finish_family(hub.books)["software_accounting_complete"]
    assert rt.next_id == 96
    assert len(rt.operations) == 96 * 3


@pytest.mark.parametrize("fault", ["whole_share_round", "partial", "double_post", "missing_fee", "duplicate_settlement", "extra_cash", "submitted_only", "duplicate_fill"])
def test_material_native_rounding_partial_fee_cash_or_callback_failure_poison_run(fault):
    cell = next(c for c in rep.CELL_IDS if "-C20-" in c)
    rt, hub = setup((cell,))
    scheduled = proposed(hub, cell)
    rt.fault = fault
    with pytest.raises(ValueError):
        hub.submit(scheduled)
    assert hub.poisoned
    with pytest.raises(bridge.LeanTransportRefusal, match="poisoned"):
        hub.reconcile()


def test_submitted_notice_alone_is_never_an_accepted_fill():
    rt, hub = setup((rep.CELL_IDS[0],))
    scheduled = proposed(hub, rep.CELL_IDS[0])
    hub.arm(scheduled)
    hub.on_order_event(NS(OrderId=42, Symbol=NS(Value=hub.pending.alias), Status="Submitted", UtcTime=rt.at))
    assert hub.pending is not None
    assert hub.book(rep.CELL_IDS[0]).transport.positions == ()


def test_cell_buying_power_never_borrows_other_47_books_and_native_targets_refuse():
    rt, hub = setup()
    cell = rep.CELL_IDS[0]
    security = hub.securities[rep.security_alias(cell, "native:fabricated-class")]
    model = security.BuyingPowerModel
    hub.submit(proposed(hub, cell))
    assert model.GetBuyingPower(NS(Security=security)).Value < Decimal("1e-12")
    assert rt.native_cash >= Decimal(4700000)
    with pytest.raises(ValueError, match="budget"):
        proposed(hub, cell, quantity=Fraction(1), at="2023-01-04T14:30:00Z",
                 event="extra-entry", order_id="extra-entry-order")
    for method in (model.GetMaximumOrderQuantityForTargetBuyingPower, model.GetMaximumOrderQuantityForDeltaBuyingPower):
        result = method(None)
        assert result.Quantity == 0 and result.IsError


def test_second_pending_cross_alias_stale_price_tag_and_order_clock_are_not_substitutes():
    rt, hub = setup()
    scheduled = proposed(hub, rep.CELL_IDS[0], quantity=Fraction(1, 3))
    tag = hub.arm(scheduled)
    with pytest.raises(ValueError, match="one_exact_pending"):
        hub.arm(scheduled)
    security = hub.securities[hub.pending.alias]
    order = NS(Id=1, Symbol=security.Symbol, Quantity=scheduled.transport_order.submitted_quantity,
               Time=rt.at, Tag=tag, Type="Market")
    assert security.BuyingPowerModel.HasSufficientBuyingPowerForOrder(NS(Security=security, Order=order)).IsSufficient
    for changed in (NS(**{**order.__dict__, "Tag": "other"}),
                    NS(**{**order.__dict__, "Time": "2023-01-03T14:31:00Z"}),
                    NS(**{**order.__dict__, "Symbol": NS(Value="other-cell")}),
                    NS(**{**order.__dict__, "Quantity": Decimal(1)})):
        assert not security.BuyingPowerModel.HasSufficientBuyingPowerForOrder(NS(Security=security, Order=changed)).IsSufficient


def test_native_default_fee_then_custom_notional_then_holdings_sequence():
    cell = next(c for c in rep.CELL_IDS if "-C20-" in c)
    rt, hub = setup((cell,))
    scheduled = proposed(hub, cell)
    o = scheduled.transport_order
    hub.submit(scheduled)
    assert [name for name, _ in rt.operations] == ["native_default_fee", "notional_or_corporate_cash", "native_default_holdings"]
    assert rt.operations[1][1] == bridge._sum((o.posted_cash_delta_usd, o.fee_usd))
    assert Fraction(rt.native_cash) == Fraction(4800000) + Fraction(o.posted_cash_delta_usd)


def action(hub, cell, kind, at, event, cash=None, dividend=None, ratio=None, price=None):
    hub.runtime.at = at
    a = rep.CorporateAction(event, "native:fabricated-class", at, kind, cash, dividend, ratio, price)
    hub.corporate_action(cell, a)


def test_explicit_split_entitlement_sale_and_payment_use_frozen_receivable_not_current_quantity():
    cell = rep.CELL_IDS[0]
    rt, hub = setup((cell,))
    hub.submit(proposed(hub, cell, quantity=Fraction(1, 3), price=Fraction(30)))
    action(hub, cell, "split", "2023-01-04T14:30:00Z", "split", ratio=Fraction(3, 2), price=Fraction(20))
    action(hub, cell, "dividend_entitlement", "2023-01-04T14:30:00Z", "entitle",
           cash=Fraction(2, 3), dividend="ordinary-1")
    entitled = hub.book(cell)
    assert entitled.transport.positions[0].economic_quantity == Fraction(1, 2)
    assert entitled.receivables[0].economic_amount == Fraction(1, 3)
    cash_before = rt.cash()
    hub.submit(proposed(hub, cell, side="sell", quantity=Fraction(1, 2), price=Fraction(20),
                       at="2023-01-17T14:30:00Z", event="exit", order_id="exit-order"))
    paid_before = rt.cash()
    action(hub, cell, "dividend_payment", "2023-01-20T14:30:00Z", "payment", cash=Fraction(2, 3), dividend="ordinary-1")
    assert hub.book(cell).receivables == ()
    assert hub.book(cell).transport.economic_cash == Fraction(100000) + Fraction(1, 3)
    assert Fraction(rt.cash()) - Fraction(paid_before) == Fraction(entitled.receivables[0].mirror_amount)
    assert abs(Fraction(paid_before) - Fraction(cash_before) - Fraction(10)) < rep.MAXIMUM_COMBINED_DRIFT_USD
    hub.reconcile()


@pytest.mark.parametrize("cash", [Fraction(0), Fraction(9, 2)])
def test_verified_terminal_cash_posts_and_closes_explicitly_without_fake_zero_price_trade(cash):
    cell = rep.CELL_IDS[0]
    rt, hub = setup((cell,))
    hub.submit(proposed(hub, cell, quantity=Fraction(1, 3), price=Fraction(30)))
    action(hub, cell, "terminal", "2023-01-04T14:30:00Z", "terminal", cash=cash)
    assert hub.book(cell).transport.positions == ()
    assert hub.book(cell).transport.economic_cash == Fraction(99990) + cash / 3
    assert rt.next_id == 1
    assert not any(name == "native_default_fee" for name, _ in rt.operations[3:])
    hub.reconcile()


def test_known_future_receivable_still_does_not_enable_spending_or_old_v1_completion():
    cell = rep.CELL_IDS[0]
    rt, hub = setup((cell,))
    hub.submit(proposed(hub, cell, quantity=Fraction(1, 3), price=Fraction(30)))
    action(hub, cell, "dividend_entitlement", "2023-01-04T14:30:00Z", "entitle", cash=Fraction(3), dividend="future")
    assert hub.book(cell).transport.economic_cash == 99990
    assert hub.book(cell).receivables[0].economic_amount == 1
    hub.submit(proposed(hub, cell, side="sell", quantity=Fraction(1, 3), price=Fraction(30),
                       at="2023-01-17T14:30:00Z", event="exit", order_id="exit-order"))
    with pytest.raises(ValueError, match="positive_unpaid"):
        rep.finish_family(hub.books)


def test_diagnostic_fee_query_cannot_authorize_order_or_post_any_cash():
    cell = next(c for c in rep.CELL_IDS if "-C20-" in c)
    rt, hub = setup((cell,))
    security = hub.securities[rep.security_alias(cell, "native:fabricated-class")]
    diagnostic = NS(Id=0, Tag="", Type="Market", Symbol=security.Symbol, Quantity=Decimal("-0.333333333333333333"))
    fee = security.FeeModel.GetOrderFee(NS(Security=security, Order=diagnostic))
    assert fee.Value.Amount == Decimal("0.003333333333333334")
    assert security.FeeModel.GetOrderFee(security, diagnostic) == fee.Value.Amount
    assert not security.BuyingPowerModel.HasSufficientBuyingPowerForOrder(NS(Security=security, Order=diagnostic)).IsSufficient
    assert rt.operations == [] and rt.native_cash == 4800000


def test_registering_default_whole_share_symbol_properties_refuses_before_order():
    rt, hub = setup((rep.CELL_IDS[0],))
    old = hub.securities[rep.security_alias(rep.CELL_IDS[0], "native:fabricated-class")]
    other_alias = rep.security_alias(rep.CELL_IDS[1], "native:fabricated-class")
    other = NS(**{**old.__dict__, "Symbol": NS(Value=other_alias),
        "SymbolProperties": NS(LotSize=Decimal(1), MinimumPriceVariation=Decimal("0.01"), ContractMultiplier=Decimal(1))})
    with pytest.raises(ValueError, match="native_lot_tick"):
        hub.register_security(rep.CELL_IDS[1], "native:fabricated-class", other)


def test_official_settlement_wrapper_invokes_get_unsettled_cash_with_no_parameters():
    _, hub = setup((rep.CELL_IDS[0],))
    model = bridge.PostedNotionalSettlement(hub)
    assert model.GetUnsettledCash() is None
    model.Scan(None)


def test_equal_and_opposite_native_fee_reallocation_between_cell_aliases_refuses():
    cells = tuple(c for c in rep.CELL_IDS if "-C20-" in c)[:2]
    rt, hub = setup(cells)
    for cell in cells:
        hub.submit(proposed(hub, cell, quantity=Fraction(1), price=Fraction(10)))
    a, b = [hub.securities[rep.security_alias(c, "native:fabricated-class")] for c in cells]
    a.Holdings.TotalFees = bridge._sum((a.Holdings.TotalFees, Decimal("1e-18")))
    b.Holdings.TotalFees = bridge._sum((b.Holdings.TotalFees, Decimal("-1e-18")))
    with pytest.raises(ValueError, match="alias_fee"):
        hub.reconcile()
