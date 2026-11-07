"""Compile-only decimal receiving instrumentation for the SAME48 transport.

No installed CLR import occurs while producing this text. No invocation here
provides source/cloud permission or actual receiving evidence. Published QC
pythonnet converts Python Decimal outbound using its exact string; importantly,
calling CLR Decimal.Parse and bringing the decimal back into Python would enter
the documented CLR->Python float conversion path. Do not 'repair' money there.
"""
from data.hashing import hash_bytes


def receiver_source():
    return '''"""SAME48 typed receiving instrumentation; no strategy changes."""
from decimal import Decimal
from fractions import Fraction
import research.short_interest_etf.native_qc_order_representation as rep
from scripts.short_interest_compact_joint_transport import CompactLeanRuntime


class ReceivingCheckedCompactLeanRuntime(CompactLeanRuntime):
    """Check actual CLR receiving properties without replacing any economics.

    Mismatches raise, never update budgets or restore account cash. The decimal
    getter checks actual selected CLR property type and converts in CLR to an
    invariant string before Python sees it. These observations are local to
    the separately registered engine and fictional transport candidate only.
    """

    def _receiver_equal(self, value, expected, reason):
        rep._proof_decimal(expected)
        if type(value) is not Decimal or value != expected:
            raise ValueError("REFUSED: typed_outbound_" + reason)

    def source_free_decimal_probe(self):
        super().source_free_decimal_probe()
        probes = (Decimal("0.000000000000000001"),
            Decimal("1234567.890123456789012345"),
            Decimal("9999999999999999999999999999"))
        for value in probes:
            rep._proof_decimal(value, nonnegative=True)
            cash = self.qc.Cash("USD", value, Decimal(1))
            self._receiver_equal(self.decimal(cash, "Amount"), value, "Cash_constructor")
            # The return of AddAmount is deliberately discarded. It is a CLR
            # decimal and would be converted to a Python float on this bridge.
            cash.AddAmount(rep._decimal(-Fraction(value)))
            self._receiver_equal(self.decimal(cash, "Amount"), Decimal(0), "Cash_AddAmount")
            amount = self.qc.CashAmount(value, "USD")
            self._receiver_equal(self.decimal(amount, "Amount"), value, "CashAmount_constructor")
            fee = self.qc.OrderFee(amount)
            self._receiver_equal(self.decimal(fee, "Value", "Amount"), value, "OrderFee_constructor")
        quantum = rep._decimal(rep.QUANTUM)
        props = self.qc.SymbolProperties("SI receiver proof", "USD", Decimal(1),
                                        quantum, quantum, "")
        for property_name in ("MinimumPriceVariation", "LotSize"):
            self._receiver_equal(self.decimal(props, property_name), quantum,
                                 "SymbolProperties_" + property_name)
        return {"fictional_CLR_constructor_receivers_checked": True,
                "actual_input_admitted": False, "cloud_runtime_independently_qualified": False,
                "strategy_result": False, "actual_outcome_looks": 0}

    def fee(self, amount):
        result = super().fee(amount)
        self._receiver_equal(self.decimal(result, "Value", "Amount"), amount, "fee")
        return result

    def make_fill(self, order, scheduled):
        result = super().make_fill(order, scheduled)
        events = list(result)  # Public Fill IEnumerable<OrderEvent>, not a guessed property.
        if len(events) != 1:
            raise ValueError("REFUSED: typed_outbound_single_fill_required")
        event, expected = events[0], scheduled.transport_order
        self._receiver_equal(self.decimal(event, "FillQuantity"), expected.submitted_quantity,
                             "fill_quantity")
        self._receiver_equal(self.decimal(event, "FillPrice"), expected.fill_price, "fill_price")
        self._receiver_equal(self.decimal(event, "OrderFee", "Value", "Amount"),
                             expected.fee_usd, "fill_fee")
        return result

    def post_cash(self, amount):
        before = self.cash()
        super().post_cash(amount)
        self._receiver_equal(self.cash(), rep._decimal(Fraction(before) + Fraction(amount)),
                             "Cash_AddAmount_account")

    def set_holdings(self, security, *, average_price, quantity):
        super().set_holdings(security, average_price=average_price, quantity=quantity)
        self._receiver_equal(self.decimal(security, "Holdings", "Quantity"), quantity,
                             "SecurityHolding_SetHoldings_quantity")
        self._receiver_equal(self.decimal(security, "Holdings", "AveragePrice"), average_price,
                             "SecurityHolding_SetHoldings_average_price")

    def submit(self, security, quantity, tag):
        ticket = super().submit(security, quantity, tag)
        self._receiver_equal(self.decimal(ticket, "Quantity"), quantity, "MarketOrder_decimal")
        return ticket
'''


def descriptor():
    source = receiver_source().encode('utf-8')
    return {'schema': 'si-source-free-outbound-receiver-instrumentation-proposal-v1',
        'source_sha256': hash_bytes(source), 'actual_CLR_receiving_observed': False,
        'installed_engine_imported': False, 'economic_path_replaced': False,
        'money_repair_or_budget_adjustment': False,
        'published_outbound_conversion': 'Python_object_exact_string_to_CLR_Decimal_TryParse',
        'published_inbound_conversion': 'CLR_Decimal_to_Python_float_avoided_by_typed_CLR_string_getter',
        'required_real_engine_properties': ['Cash.Amount', 'CashAmount.Amount', 'OrderFee.Value.Amount',
            'SymbolProperties.LotSize', 'SymbolProperties.MinimumPriceVariation',
            'OrderEvent.FillQuantity', 'OrderEvent.FillPrice', 'OrderEvent.OrderFee.Value.Amount',
            'SecurityHolding.Quantity', 'SecurityHolding.AveragePrice', 'OrderTicket.Quantity'],
        'public_converter_evidence': 'https://raw.githubusercontent.com/QuantConnect/pythonnet/master/src/runtime/Converter.cs',
        'public_decimal_precedence_evidence': 'https://raw.githubusercontent.com/QuantConnect/pythonnet/master/src/runtime/MethodBinder.cs',
        'public_Fill_evidence': 'https://raw.githubusercontent.com/QuantConnect/Lean/master/Common/Orders/Fills/Fill.cs',
        'actual_outcome_looks': 0, 'qc_attempts': 0}
