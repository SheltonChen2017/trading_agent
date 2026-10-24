"""Fabricated receiving refusal contracts; not real CLR binding evidence."""
import ast
from decimal import Decimal
from fractions import Fraction
import sys
from types import SimpleNamespace

import pytest

from data.hashing import hash_bytes
import research.short_interest_etf.native_qc_order_representation as rep
import scripts.short_interest_qc_receiver_proposal as p


def receiver_class():
    namespace = {}
    exec(compile(p.receiver_source(), '<unexecuted-real-engine receiver class>', 'exec'), namespace)
    return namespace['ReceivingCheckedCompactLeanRuntime']


def test_receiver_source_compiles_without_importing_installed_engine():
    source = p.receiver_source()
    compile(source, 'proposed_receiving.py', 'exec')
    tree = ast.parse(source)
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id == 'float' for n in ast.walk(tree))
    assert 'Decimal.Parse' not in source
    assert 'clr' not in sys.modules and 'AlgorithmImports' not in sys.modules
    assert p.descriptor()['source_sha256'] == hash_bytes(source.encode())
    assert p.descriptor()['actual_CLR_receiving_observed'] is False


def test_typed_receiver_mismatch_refuses_without_any_mutation_or_repair():
    obj = object.__new__(receiver_class())
    obj._receiver_equal(Decimal('0.000000000000000001'), Decimal('0.000000000000000001'), 'test')
    for observed in (1e-18, Decimal(0), '0.000000000000000001'):
        with pytest.raises(ValueError, match='typed_outbound_test'):
            obj._receiver_equal(observed, Decimal('0.000000000000000001'), 'test')


def test_detached_fake_constructor_probe_preserves_values_but_claims_no_CLR_fact():
    class Cash:
        def __init__(self, currency, amount, rate):
            assert type(amount) is type(rate) is Decimal
            self.Amount = amount
        def AddAmount(self, amount):
            assert type(amount) is Decimal
            self.Amount = rep._decimal(Fraction(self.Amount) + Fraction(amount))
            return float(self.Amount)  # Return discarded, never used in proof.
    class CashAmount:
        def __init__(self, amount, currency):
            assert type(amount) is Decimal
            self.Amount = amount
    class OrderFee:
        def __init__(self, value):
            self.Value = value
    class SymbolProperties:
        def __init__(self, text, currency, multiplier, tick, lot, symbol):
            self.MinimumPriceVariation, self.LotSize = tick, lot
    obj = object.__new__(receiver_class())
    obj.qc = SimpleNamespace(Cash=Cash, CashAmount=CashAmount, OrderFee=OrderFee, SymbolProperties=SymbolProperties)
    def fake_decimal(value, *path):
        for name in path:
            value = getattr(value, name)
        return value
    obj.decimal = fake_decimal
    result = obj.source_free_decimal_probe()
    assert result['actual_input_admitted'] is result['cloud_runtime_independently_qualified'] is False
    assert result['actual_outcome_looks'] == 0
    assert 'clr' not in sys.modules


def test_actual_candidate_receiving_checks_cover_fee_fill_cash_holdings_and_order():
    source = p.receiver_source()
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    expected = {'fee', 'make_fill', 'post_cash', 'set_holdings', 'submit'}
    methods = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
    assert expected <= set(methods)
    for name in expected:
        assert '_receiver_equal' in ast.unparse(methods[name])
        assert 'super().' + name in ast.unparse(methods[name])
    assert 'events = list(result)' in source
    assert 'OrderFee", "Value", "Amount' in source
    assert 'cash.AddAmount(' in source and 'return cash.AddAmount' not in source
