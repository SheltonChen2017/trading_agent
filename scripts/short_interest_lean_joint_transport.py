"""Script-composed LEAN Python transport for the same independent 48 books.

No subscription reader, provider route, actual admission, QC job or positive
execution permit lives here. Plain Python callbacks use explicit LEAN wrappers.
The native portfolio model remains the default: fee first, custom notional-only
settlement second, decimal holdings last. Every transition is then reconciled
against the exact Fraction book. Native pooled cash never determines a size.

CLR monetary property reads must occur inside CLR and return invariant strings:
QuantConnect/pythonnet currently converts incoming System.Decimal to float.
Expression compilation and Python wrapper dispatch are concrete runtime
qualification requirements, NOT proven by the fabricated contract tests.
"""
from __future__ import annotations

import dataclasses
from decimal import Decimal
from fractions import Fraction

from data.hashing import hash_payload
from research.short_interest_etf import native_qc_order_representation as rep


class LeanTransportRefusal(ValueError):
    pass


def _refuse(reason):
    return LeanTransportRefusal("REFUSED: " + reason)


def transport_design():
    result = {
        "schema": "si-lean-joint-transport-unexecuted-draft-v1",
        "representation_sha256": rep.representation_requirements()["representation_sha256"],
        "cell_ids": list(rep.CELL_IDS),
        "topology": "one_candidate_48_independent_books_one_pending_order_globally",
        "native_portfolio": "default_fee_then_custom_notional_settlement_then_holdings",
        "numeric_bridge": "CLR_expression_selected_property_invariant_string_no_float_reads",
        "native_cash": "sum_mirrors_control_not_buying_power",
        "native_margin_and_statistics": "diagnostic_not_exact_48_book_results",
        "corporate_events": "explicit_split_entitlement_payment_terminal_no_native_equity_defaults",
        "runtime_qualification_required": ["exact_cloud_LEAN_and_pythonnet_version",
            "CLR_expression_compile_and_invariant_decimal_string_round_trip",
            "Python_fee_fill_buyingpower_settlement_wrapper_dispatch",
            "typed_decimal_order_quantity_no_lot_rounding",
            "default_portfolio_callback_order_and_exact_cash_holdings_fee_controls",
            "qualified_custom_source_reader_and_open_event_clock",
            "joint_alias_subscription_cardinality_and_memory"],
        "source_processing_and_look_qualification_required": True,
        "runtime_executed": False, "qc_completed": False,
        "actual_outcome_looks": 0, "qc_attempts": 0, "authority": rep._authority(),
        "primary_evidence": [
            "https://raw.githubusercontent.com/QuantConnect/Lean/master/Common/Securities/Security.cs",
            "https://raw.githubusercontent.com/QuantConnect/Lean/master/Common/Securities/SecurityPortfolioModel.cs",
            "https://raw.githubusercontent.com/QuantConnect/Lean/master/Algorithm/QCAlgorithm.Python.cs",
            "https://raw.githubusercontent.com/QuantConnect/Lean/master/Common/Python/FillModelPythonWrapper.cs",
            "https://raw.githubusercontent.com/QuantConnect/Lean/master/Common/Python/SettlementModelPythonWrapper.cs",
            "https://raw.githubusercontent.com/QuantConnect/Lean/master/Common/Python/BuyingPowerModelPythonWrapper.cs",
            "https://raw.githubusercontent.com/QuantConnect/pythonnet/master/src/runtime/Converter.cs",
        ],
    }
    result["design_sha256"] = hash_payload(result)
    return result


def require_actual_execution(*_args, **_kwargs):
    raise _refuse("unexecuted_transport_is_not_source_processing_look_or_engine_permit")


def exact_decimal_text(value):
    """Only a CLR-side invariant string may cross the monetary read boundary."""
    if type(value) is not str or not value or value != value.strip():
        raise _refuse("CLR_invariant_decimal_string_required")
    if any(c not in "0123456789-+.Ee" for c in value):
        raise _refuse("CLR_invariant_decimal_string_required")
    try:
        result = Decimal(value)
        rep._proof_decimal(result)
    except Exception:
        raise _refuse("finite_bounded_decimal_required") from None
    return rep._decimal(Fraction(result))


def _sum(values):
    return rep._decimal(sum((Fraction(v) for v in values), Fraction()))


class LeanRuntime:
    """Concrete CLR adapter, constructed only during a separately permitted run.

    Instantiating this class does not query QC, but draft callers must not use it
    as proof of admission. No opaque input booleans can open the permit above.
    The getter compiles a strongly typed CLR lambda returning string; reading a
    decimal first and then str(float) would already have lost information.
    """

    def __init__(self, algorithm):
        import clr
        import AlgorithmImports as qc
        from System import Array, Decimal as ClrDecimal, Func, IFormatProvider, Object, String, Type
        from System.Globalization import CultureInfo
        from System.Linq.Expressions import Expression, ParameterExpression
        from QuantConnect.Python import (
            BuyingPowerModelPythonWrapper, FeeModelPythonWrapper,
            FillModelPythonWrapper, SettlementModelPythonWrapper,
        )
        self.algorithm, self.qc, self.clr = algorithm, qc, clr
        self.Array, self.Func, self.Object, self.String, self.Type = Array, Func, Object, String, Type
        self.IFormatProvider, self.ClrDecimal = IFormatProvider, ClrDecimal
        self.Expression, self.ParameterExpression = Expression, ParameterExpression
        self.culture = CultureInfo.InvariantCulture
        self.wrappers = (FeeModelPythonWrapper, FillModelPythonWrapper,
                         BuyingPowerModelPythonWrapper, SettlementModelPythonWrapper)
        self.getters = {}

    def _string_getter(self, obj, path, format_string, required_type):
        root_type = obj.GetType()
        key = root_type.AssemblyQualifiedName, path, format_string, required_type
        if key not in self.getters:
            E = self.Expression
            p = E.Parameter(self.clr.GetClrType(self.Object), "instance")
            value = E.Convert(p, root_type)
            for name in path:
                value = E.PropertyOrField(value, name)
            if value.Type.FullName != required_type:
                raise _refuse("CLR_selected_property_has_wrong_numeric_or_clock_type")
            method = value.Type.GetMethod("ToString", self.Array[self.Type]([
                self.clr.GetClrType(self.String), self.clr.GetClrType(self.IFormatProvider)]))
            if method is None:
                raise _refuse("CLR_selected_property_string_method_missing")
            call = E.Call(value, method, E.Constant(format_string),
                          E.Constant(self.culture, self.clr.GetClrType(self.IFormatProvider)))
            self.getters[key] = E.Lambda[self.Func[self.Object, self.String]](
                call, self.Array[self.ParameterExpression]([p])).Compile()
        result = self.getters[key].Invoke(obj)
        if type(result) is not str:
            raise _refuse("CLR_selected_property_did_not_return_string")
        return result

    def decimal(self, obj, *path):
        return exact_decimal_text(self._string_getter(obj, tuple(path), "G29", "System.Decimal"))

    def utc(self, obj, *path):
        value = self._string_getter(obj, tuple(path), "o", "System.DateTime")
        # DateTime UTC has seven CLR fractional digits. Nonzero sub-microsecond
        # timestamps must not be silently truncated by Python datetime.
        if value.endswith("+00:00"):
            value = value[:-6] + "Z"
        if not value.endswith("Z"):
            raise _refuse("CLR_actual_UTC_required")
        stem = value[:-1]
        if "." in stem:
            whole, fraction = stem.split(".", 1)
            if len(fraction) > 6 and any(c != "0" for c in fraction[6:]):
                raise _refuse("unsupported_submicrosecond_clock")
            fraction = fraction[:6].rstrip("0")
            stem = whole + ("." + fraction if fraction else "")
        rep._stamp(stem + "Z")
        return stem + "Z"

    def now(self):
        return self.utc(self.algorithm, "UtcTime")

    def source_free_decimal_probe(self):
        """Future local CLR-only binding probe; no feed, request or job launch.

        Not executed by these contract tests. Even successful observation proves
        only this host's selected property path, not cloud wrapper dispatch,
        source admission, strategy completion or a processing/look permit.
        """
        exact = Decimal("1234567.890123456789012345")
        cash = self.qc.Cash("USD", exact, Decimal(1))
        observed = self.decimal(cash, "Amount")
        if observed != exact:
            raise _refuse("CLR_invariant_money_round_trip_failed")
        return {"host_CLR_selected_decimal_probe_passed": True,
                "cloud_runtime_qualified": False, "source_admitted": False,
                "qc_execution_authorized": False}

    def symbol(self, obj):
        value = obj.Symbol.Value
        rep._identifier(value)
        return value

    def cash(self):
        return self.decimal(self.algorithm.Portfolio.CashBook["USD"], "Amount")

    def fee(self, amount):
        rep._proof_decimal(amount, nonnegative=True)
        return self.qc.OrderFee(self.qc.CashAmount(amount, "USD"))

    def make_fill(self, order, scheduled):
        o = scheduled.transport_order
        event = self.qc.OrderEvent(order, rep._stamp(scheduled.at), self.fee(o.fee_usd))
        event.FillQuantity, event.FillPrice = o.submitted_quantity, o.fill_price
        event.FillPriceCurrency, event.Status = "USD", self.qc.OrderStatus.Filled
        return self.qc.Fill(event)

    def post_cash(self, amount):
        rep._proof_decimal(amount)
        # Ignore return value: CLR decimal return would be converted to float.
        self.algorithm.Portfolio.CashBook["USD"].AddAmount(amount)

    def set_holdings(self, security, *, average_price, quantity):
        rep._proof_decimal(average_price, nonnegative=True)
        rep._proof_decimal(quantity, nonnegative=True)
        security.Holdings.SetHoldings(average_price, quantity)

    def install(self, hub, cell_id, native_id, data_type):
        alias = rep.security_alias(cell_id, native_id)
        quantum = rep._decimal(rep.QUANTUM)
        properties = self.qc.SymbolProperties("SI independent book", "USD", Decimal(1),
                                             quantum, quantum, "")
        # This official AddData overload stores the correctly generated Base
        # database key before creating the security. A raw ticker SetEntry can
        # miss that type-dependent generated key.
        hours = self.qc.SecurityExchangeHours.AlwaysOpen(self.qc.TimeZones.Utc)
        security = self.algorithm.AddData(data_type, alias, properties, hours,
                                         self.qc.Resolution.Minute, False, Decimal(1))
        hub.register_security(cell_id, native_id, security)
        fee, fill, buying, settlement = self.wrappers
        security.SetFeeModel(fee(ExactFeeModel(hub)))
        security.SetFillModel(fill(ExactFillModel(hub)))
        security.SetBuyingPowerModel(buying(CellBuyingPowerModel(hub)))
        security.SetSettlementModel(settlement(PostedNotionalSettlement(hub)))
        return security

    def submit(self, security, quantity, tag):
        # Direct planned decimal order, never native target-percent sizing.
        return self.algorithm.MarketOrder(security.Symbol, quantity, False, tag)

    def sufficient(self, sufficient, reason=""):
        return self.qc.HasSufficientBuyingPowerForOrderResult(sufficient, reason)

    def buying_power(self, value):
        return self.qc.BuyingPower(value)

    def initial_margin(self, value):
        return self.qc.InitialMargin(value)

    def maintenance_margin(self, value):
        return self.qc.MaintenanceMargin(value)

    def sizing_refused(self):
        return self.qc.GetMaximumOrderQuantityResult(Decimal(0), "native_sizing_forbidden", True)

    def is_market(self, order):
        return order.Type == self.qc.OrderType.Market

    def is_base(self, security):
        return security.Type == self.qc.SecurityType.Base

    def is_filled(self, event):
        return event.Status == self.qc.OrderStatus.Filled

    def is_nonterminal_notice(self, event):
        return event.Status in (self.qc.OrderStatus.New, self.qc.OrderStatus.Submitted)


@dataclasses.dataclass
class _Pending:
    scheduled: rep.ScheduledCellOrder
    alias: str
    tag: str
    aggregate_cash_before: Decimal
    alias_fee_before: Decimal
    engine_order_id: int | None = None
    fill_calls: int = 0
    settlement_calls: int = 0


class JointTransport:
    """One serialized exact family with cell aliases and native controls.

    This mutable callback owner does not replace the sealed economic books.
    Any uncertain native mutation poisons the run; it never restores cash,
    silently retries an order, or changes the candidate to obtain completion.
    """

    def __init__(self, runtime):
        self.runtime, self.books = runtime, rep.new_family()
        self.securities, self.identities, self.opens = {}, {}, {}
        self.alias_fees = {}
        self.pending, self.poisoned, self.sequence = None, False, 0

    def _live(self):
        if self.poisoned:
            raise _refuse("native_mutation_failed_run_is_poisoned")

    def _stop(self, reason):
        self.poisoned = True
        raise _refuse(reason)

    def book(self, cell):
        if type(cell) is not str or cell not in rep.CELL_IDS:
            raise _refuse("unknown_cell")
        return self.books[rep.CELL_IDS.index(cell)]

    def register_security(self, cell, native, security):
        self._live()
        if self.pending is not None:
            raise _refuse("registration_during_pending_order")
        alias = rep.security_alias(cell, native)
        rt = self.runtime
        if alias in self.securities or rt.symbol(security) != alias:
            raise _refuse("duplicate_or_wrong_Base_alias")
        if not rt.is_base(security):
            raise _refuse("non_Base_security_forbidden")
        for path, expected in (("LotSize", rep.QUANTUM), ("MinimumPriceVariation", rep.QUANTUM),
                               ("ContractMultiplier", Fraction(1))):
            if Fraction(rt.decimal(security, "SymbolProperties", path)) != expected:
                raise _refuse("native_lot_tick_or_multiplier_mismatch")
        if security.QuoteCurrency.Symbol != "USD":
            raise _refuse("non_USD_quote_currency")
        if rt.decimal(security, "Holdings", "Quantity") != 0 or rt.decimal(security, "Holdings", "TotalFees") != 0:
            raise _refuse("new_alias_already_has_native_finance")
        self.securities[alias], self.identities[alias] = security, (cell, native)
        self.alias_fees[alias] = Decimal(0)

    def _snapshot(self, alias_fees=None):
        rt = self.runtime
        expected_fees = self.alias_fees if alias_fees is None else alias_fees
        if set(expected_fees) != set(self.securities):
            raise _refuse("native_alias_fee_registry_mismatch")
        holdings, fees = [], []
        for alias, security in sorted(self.securities.items()):
            quantity = rt.decimal(security, "Holdings", "Quantity")
            rep._proof_decimal(quantity, nonnegative=True)
            if quantity:
                holdings.append((alias, quantity))
            fee = rt.decimal(security, "Holdings", "TotalFees")
            rep._proof_decimal(fee, nonnegative=True)
            if fee != expected_fees[alias]:
                raise _refuse("native_alias_fee_ledger_mismatch")
            fees.append(fee)
        return rt.cash(), _sum(fees), tuple(holdings)

    def reconcile(self, books=None, *, alias_fees=None):
        self._live()
        cash, fees, holdings = self._snapshot(alias_fees)
        return rep.reconcile_native_aggregate(self.books if books is None else books,
                    native_cash=cash, native_fees=fees, native_holdings=holdings)

    def offer_raw_open(self, alias, *, at, raw_open):
        self._live()
        if alias not in self.securities or type(raw_open) is not Fraction:
            raise _refuse("registered_exact_raw_open_required")
        rep._fraction(raw_open, positive=True)
        if self.runtime.now() != at or rep._stamp(at) != rep._open_instant(at[:10]):
            raise _refuse("raw_open_not_current_registered_XNYS_open")
        old = self.opens.get(alias)
        if old is not None and old != (at, raw_open) and rep._stamp(old[0]) >= rep._stamp(at):
            raise _refuse("duplicate_or_revised_open_inside_run")
        self.opens[alias] = at, raw_open

    def arm(self, scheduled):
        self._live()
        if self.pending is not None or type(scheduled) is not rep.ScheduledCellOrder:
            raise _refuse("one_exact_pending_order_required")
        scheduled.to_payload()
        o = scheduled.transport_order
        book = self.book(o.cell_id)
        alias = rep.security_alias(o.cell_id, o.security_id)
        if alias not in self.securities or scheduled.source_book_sha256 != book.sha256:
            raise _refuse("unregistered_alias_or_stale_book")
        if self.runtime.now() != scheduled.at or self.opens.get(alias) != (scheduled.at, o.economic_price):
            raise _refuse("scheduled_order_has_no_current_matching_raw_open")
        # Recompute the proposed transition before allowing native mutation.
        regenerated = rep.prepare_cell_order(book, at=scheduled.at, security_id=o.security_id,
            event_id=o.event_id, order_id=o.order_id, side=o.side,
            economic_quantity=o.economic_quantity, economic_price=o.economic_price)
        if regenerated.to_payload() != scheduled.to_payload():
            raise _refuse("unproven_scheduled_order")
        self.reconcile()
        self.sequence += 1
        self.pending = _Pending(scheduled, alias, f"si-joint-{self.sequence:012d}",
            self.runtime.cash(), self.runtime.decimal(self.securities[alias], "Holdings", "TotalFees"))
        return self.pending.tag

    def _match(self, security, order):
        self._live()
        p, rt = self.pending, self.runtime
        if p is None or rt.symbol(security) != p.alias or rt.symbol(order) != p.alias:
            raise _refuse("unplanned_or_cross_cell_order")
        if type(order.Tag) is not str or order.Tag != p.tag or not rt.is_market(order):
            raise _refuse("wrong_registered_order_tag_or_type")
        if type(order.Id) is not int or order.Id <= 0:
            raise _refuse("invalid_native_order_identity")
        if p.engine_order_id not in (None, order.Id):
            raise _refuse("native_order_identity_changed")
        if (rt.decimal(order, "Quantity") != p.scheduled.transport_order.submitted_quantity
                or rt.utc(order, "Time") != p.scheduled.at or rt.now() != p.scheduled.at):
            raise _refuse("native_quantity_rounding_or_order_clock_mismatch")
        p.engine_order_id = order.Id
        p.scheduled.to_payload()
        if self.book(p.scheduled.transport_order.cell_id).sha256 != p.scheduled.source_book_sha256:
            raise _refuse("native_order_source_book_changed")
        return p

    def submit(self, scheduled):
        tag = self.arm(scheduled)
        try:
            ticket = self.runtime.submit(self.securities[self.pending.alias],
                            scheduled.transport_order.submitted_quantity, tag)
            # Synchronous MarketOrder must have produced and reconciled one
            # full callback before it returns; Submitted alone is not success.
            if self.pending is not None:
                self._stop("synchronous_order_did_not_reconcile_full_fill")
            return ticket
        except Exception:
            self.poisoned = True
            raise

    def settle(self, parameters):
        self._live()
        p, rt = self.pending, self.runtime
        if p is None or p.settlement_calls != 0 or p.fill_calls != 1:
            self._stop("missing_or_duplicate_native_settlement")
        event, security, o = parameters.Fill, parameters.Security, p.scheduled.transport_order
        self._validate_fill(event)
        if rt.symbol(security) != p.alias or parameters.CashAmount.Currency != "USD":
            self._stop("wrong_native_settlement_security_or_currency")
        if rt.cash() != _sum((p.aggregate_cash_before, -o.fee_usd)):
            self._stop("fee_not_posted_exactly_once_before_notional")
        if rt.decimal(security, "Holdings", "TotalFees") != _sum((p.alias_fee_before, o.fee_usd)):
            self._stop("native_fee_ledger_mismatch_before_settlement")
        fee_registry = {**self.alias_fees, p.alias: _sum((p.alias_fee_before, o.fee_usd))}
        # Even cancelling aggregate fee changes cannot move a native fee from
        # one cell alias to another without refusing the run.
        self._snapshot(fee_registry)
        position = rep._position(self.book(o.cell_id).transport, o.security_id)
        expected_quantity = Decimal(0) if position is None else position.mirror_quantity
        if rt.decimal(security, "Holdings", "Quantity") != expected_quantity:
            self._stop("native_holdings_changed_before_settlement")
        # The default CashAmount is the CLR product, which can round at its
        # own scale. Post our explicit notional instead. Fee already posted.
        signed_notional = _sum((o.posted_cash_delta_usd, o.fee_usd))
        rt.post_cash(signed_notional)
        p.settlement_calls += 1

    def _validate_fill(self, event):
        p, rt = self.pending, self.runtime
        if p is None or type(event.OrderId) is not int or event.OrderId != p.engine_order_id:
            self._stop("unregistered_native_fill_identity")
        o = p.scheduled.transport_order
        if (not rt.is_filled(event) or rt.symbol(event) != p.alias
                or rt.utc(event, "UtcTime") != p.scheduled.at or rt.now() != p.scheduled.at
                or rt.decimal(event, "FillQuantity") != o.submitted_quantity
                or rt.decimal(event, "FillPrice") != o.fill_price
                or event.FillPriceCurrency != "USD"
                or event.OrderFee.Value.Currency != "USD"
                or rt.decimal(event, "OrderFee", "Value", "Amount") != o.fee_usd):
            self._stop("partial_rounded_wrong_fee_or_wrong_clock_fill")
        return p

    def on_order_event(self, event):
        self._live()
        rt, p = self.runtime, self.pending
        if p is not None and rt.is_nonterminal_notice(event):
            if (type(event.OrderId) is not int or event.OrderId <= 0
                    or p.engine_order_id not in (None, event.OrderId) or rt.symbol(event) != p.alias
                    or rt.utc(event, "UtcTime") != p.scheduled.at):
                self._stop("unregistered_native_order_notice")
            p.engine_order_id = event.OrderId
            return
        self._validate_fill(event)
        if p.fill_calls != 1 or p.settlement_calls != 1:
            self._stop("native_fill_did_not_post_exactly_once")
        o, book = p.scheduled.transport_order, self.book(p.scheduled.transport_order.cell_id)
        security = self.securities[p.alias]
        cash_delta = rep._decimal(Fraction(rt.cash()) - Fraction(p.aggregate_cash_before))
        fee_delta = rep._decimal(Fraction(rt.decimal(security, "Holdings", "TotalFees")) - Fraction(p.alias_fee_before))
        position = rep._position(book.transport, o.security_id)
        control = rep.EngineControl(o.cell_id, p.alias, p.scheduled.at, o.event_id,
            book.transport.mirror_cash, _sum((book.transport.mirror_cash, cash_delta)),
            Decimal(0) if position is None else position.mirror_quantity,
            rt.decimal(security, "Holdings", "Quantity"),
            book.transport.mirror_fees_paid, _sum((book.transport.mirror_fees_paid, fee_delta)))
        signed_notional = rep._decimal(Fraction(cash_delta) + Fraction(fee_delta))
        proof = rep.FillProof(o.cell_id, o.security_id, o.event_id, o.order_id, o.side,
            rt.decimal(event, "FillQuantity"), rt.decimal(event, "FillPrice"), fee_delta,
            rep._decimal(abs(Fraction(signed_notional))), cash_delta)
        try:
            after = rep.accept_cell_order(book, p.scheduled, proof, at=p.scheduled.at, control=control)
            family = tuple(after if b.transport.cell_id == o.cell_id else b for b in self.books)
            fee_registry = {**self.alias_fees, p.alias: _sum((p.alias_fee_before, o.fee_usd))}
            self.reconcile(family, alias_fees=fee_registry)
        except Exception:
            self.poisoned = True
            raise
        self.books, self.pending = family, None
        self.alias_fees = fee_registry

    def corporate_action(self, cell, action):
        self._live()
        if self.pending is not None or self.runtime.now() != action.at:
            raise _refuse("corporate_action_during_order_or_wrong_clock")
        before = self.book(cell)
        control = rep.prepare_corporate_control(before, action)
        alias, rt = control.security_alias, self.runtime
        if alias not in self.securities:
            raise _refuse("corporate_alias_not_registered")
        self.reconcile()
        cash_before = rt.cash()
        security = self.securities[alias]
        try:
            if action.kind in ("split", "terminal"):
                old_average = rt.decimal(security, "Holdings", "AveragePrice")
                average = (rep._decimal(rep._lattice(Fraction(old_average) / action.split_ratio, "nearest_even"))
                           if action.kind == "split" else Decimal(0))
                rt.set_holdings(security, average_price=average, quantity=control.quantity_after)
            delta = rep._decimal(Fraction(control.cash_after) - Fraction(control.cash_before))
            if delta:
                rt.post_cash(delta)
            native = dataclasses.replace(control,
                cash_after=_sum((control.cash_before, rep._decimal(Fraction(rt.cash()) - Fraction(cash_before)))),
                quantity_after=rt.decimal(security, "Holdings", "Quantity"))
            after = rep.accept_corporate_action(before, action, native)
            family = tuple(after if b.transport.cell_id == cell else b for b in self.books)
            self.reconcile(family)
        except Exception:
            self.poisoned = True
            raise
        self.books = family


class ExactFeeModel:
    def __init__(self, hub):
        self.hub = hub

    def GetOrderFee(self, *args):
        if len(args) == 1:
            security, order = args[0].Security, args[0].Order
        elif len(args) == 2:
            security, order = args
        else:
            raise _refuse("fee_signature_not_supported")
        rt = self.hub.runtime
        # LEAN queries liquidation fees for native diagnostics using order Id0.
        # Those queries do not fill or mutate. Price/quantity extraction is still
        # exact; this estimate never changes the authoritative 48-book ledger.
        if type(order.Id) is int and order.Id == 0 and order.Tag in (None, "") and rt.is_market(order):
            alias = rt.symbol(security)
            if alias not in self.hub.identities or rt.symbol(order) != alias:
                raise _refuse("foreign_diagnostic_fee_query")
            cell = self.hub.identities[alias][0]
            rate = Fraction(int(cell.split("-C")[1].split("-")[0]), 10000)
            value = abs(Fraction(rt.decimal(order, "Quantity"))) * Fraction(rt.decimal(security, "Price")) * rate
            amount = rep._decimal(rep._lattice(value, "ceil"))
        else:
            amount = self.hub._match(security, order).scheduled.transport_order.fee_usd
        return rt.fee(amount) if len(args) == 1 else amount


class ExactFillModel:
    def __init__(self, hub):
        self.hub, self.wrapper = hub, None

    def SetPythonWrapper(self, wrapper):
        self.wrapper = wrapper

    def Fill(self, parameters):
        p = self.hub._match(parameters.Security, parameters.Order)
        if p.fill_calls != 0:
            self.hub._stop("duplicate_native_fill_callback")
        if self.hub.opens.get(p.alias) != (p.scheduled.at, p.scheduled.transport_order.economic_price):
            self.hub._stop("missing_or_changed_current_open_at_fill")
        p.fill_calls += 1
        return self.hub.runtime.make_fill(parameters.Order, p.scheduled)


class PostedNotionalSettlement:
    def __init__(self, hub):
        self.hub = hub

    def ApplyFunds(self, parameters):
        self.hub.settle(parameters)

    def Scan(self, _parameters):
        self.hub._live()

    def GetUnsettledCash(self):
        self.hub._live()
        return None  # Official wrapper maps null to default CashAmount.


class CellBuyingPowerModel:
    def __init__(self, hub):
        self.hub = hub

    def GetLeverage(self, _security):
        return Decimal(1)

    def SetLeverage(self, _security, leverage):
        # Leverage1 is exactly representable even when QC crosses this constant
        # as float. No financial decimal is admitted through this exception.
        if type(leverage) not in (int, float, Decimal) or leverage != 1:
            raise _refuse("leverage_other_than_one_forbidden")

    def HasSufficientBuyingPowerForOrder(self, parameters):
        try:
            self.hub._match(parameters.Security, parameters.Order)
            return self.hub.runtime.sufficient(True)
        except Exception:
            return self.hub.runtime.sufficient(False, "unplanned_or_unfunded_cell_order")

    def GetBuyingPower(self, parameters):
        self.hub._live()
        alias = self.hub.runtime.symbol(parameters.Security)
        if alias not in self.hub.identities:
            raise _refuse("foreign_cell_buying_power_query")
        cell = self.hub.identities[alias][0]
        amount = self.hub.book(cell).transport.mirror_cash
        if self.hub.pending is not None and self.hub.pending.scheduled.transport_order.cell_id == cell:
            amount = Decimal(0)
        return self.hub.runtime.buying_power(amount)

    def GetInitialMarginRequiredForOrder(self, parameters):
        o = self.hub._match(parameters.Security, parameters.Order).scheduled.transport_order
        return self.hub.runtime.initial_margin(_sum((o.posted_notional_usd, o.fee_usd)))

    def GetInitialMarginRequirement(self, parameters):
        rt = self.hub.runtime
        value = abs(Fraction(rt.decimal(parameters, "Quantity"))) * Fraction(rt.decimal(parameters.Security, "Price"))
        return rt.initial_margin(rep._decimal(rep._lattice(value, "ceil")))

    def GetMaintenanceMargin(self, _parameters):
        # Long-only fully paid cash holdings cannot produce margin borrowing.
        # Native margin-call target sizing is independently forbidden below.
        return self.hub.runtime.maintenance_margin(Decimal(0))

    def GetReservedBuyingPowerForPosition(self, parameters):
        return parameters.ResultInAccountCurrency(Decimal(0))

    def GetMaximumOrderQuantityForTargetBuyingPower(self, _parameters):
        return self.hub.runtime.sizing_refused()

    def GetMaximumOrderQuantityForDeltaBuyingPower(self, _parameters):
        return self.hub.runtime.sizing_refused()
