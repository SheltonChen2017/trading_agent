"""Public synthetic context only; no private/cloud/native strategy execution."""
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.target_price_revisions_qc import extended_refusal_witness_context_successor as w


class Evidence:
    def __init__(self):
        self.binding = {"candidate_id": w.CANDIDATE, "config_sha256": w.CONFIG_SHA256,
            "freeze_sha256": w.FREEZE_SHA256, "attempt": 3, "project_id": w.PROJECT,
            "job_id": "synthetic_context_31", "input_hashes": {"calendar.json": w.CALENDAR_SHA256}}
    def require_binding(self): pass


class Store:
    def __init__(self): self.data, self.calls = {}, []
    def contains_key(self, key):
        self.calls.append(("contains", key)); return key in self.data
    def save_bytes(self, key, raw):
        self.calls.append(("save", key)); assert key not in self.data
        self.data[key] = raw; return True
    def read_bytes(self, key): self.calls.append(("read", key)); return self.data[key]
    def clear(self): raise AssertionError("no shared clearing")
    def keys(self): raise AssertionError("no global enumeration")


class Numeric:
    @staticmethod
    def _number(value):
        assert type(value) is str
        return Fraction(Decimal(value))
    @staticmethod
    def native_fraction(value): return Fraction(value)
    @staticmethod
    def _text(value): return format(Decimal(value.numerator) / Decimal(value.denominator), "f")


class Row:
    def __init__(self, sid, raw, failure=None):
        self.symbol, self.raw, self.failure = SimpleNamespace(id=sid), raw, failure
        self.end_time, self.reads = datetime(2024, 7, 12), 0
    @property
    def weight(self):
        self.reads += 1
        if self.failure is not None: raise self.failure
        return self.raw


class NativeIdentifier:
    def __init__(self, text): self.text, self.calls = text, 0
    def GetType(self): return SimpleNamespace(FullName="QuantConnect.SecurityIdentifier")
    def ToString(self): self.calls += 1; return self.text
    def __str__(self): raise AssertionError("no arbitrary str")
    def __repr__(self): raise AssertionError("no arbitrary repr")


class Bar:
    def __init__(self):
        self.end_time, self.time = datetime(2024, 7, 12, 16, 2), datetime(2024, 7, 12, 16, 1)
        self.period, self.is_fill_forward, self.price = None, False, Decimal("10.00")


class PartialBar(Bar):
    def __init__(self): self.end_time = datetime(2024, 7, 12, 16, 2)
    @property
    def time(self): raise ValueError("unavailable synthetic clock")
    @property
    def price(self): raise ValueError("unavailable synthetic scalar")


class BadAlgo:
    def __init__(self, error): self.error, self.reads = error, 0
    @property
    def _warning_ids(self):
        self.reads += 1
        raise self.error


@pytest.fixture
def case():
    evidence, store = Evidence(), Store()
    witness = w.ContextRefusalWitness(evidence, store, Numeric, Bar)
    return witness, evidence, store


def members_and_rows(weights):
    rows, members = [], []
    for index, value in enumerate(weights):
        sid = f"SYNTHETIC_{index}"
        rows.append(Row(sid, value))
        members.append({"symbol": SimpleNamespace(id=sid), "ticker": f"FAKE_{index}",
            "weight": None if value is None else Numeric._text(Numeric.native_fraction(value))})
    return members, rows


def membership(witness, members, rows, error=None):
    return witness.membership_context(ValueError("membership weight outside bounds") if error is None else error,
        "REMX", members, rows, datetime(2024, 7, 12, 9, 20))


def mark(witness, *, algo=None, last=None, error=None):
    sid = "SYNTHETIC_0"
    algo = SimpleNamespace(_warning_ids={sid}, _delisted_ids={sid}, _quantity_ledger={sid: Fraction(3)}) if algo is None else algo
    return witness.mark_context(ValueError("held RAW closing mark stale/future") if error is None else error,
        algo, SimpleNamespace(symbol=SimpleNamespace(id=sid), quantity=Decimal("3")), object(), last,
        datetime(2024, 7, 12, 20, 2, tzinfo=timezone.utc), Fraction(10), "2024-07-12",
        datetime(2024, 7, 12, 20, 1, tzinfo=timezone.utc))


def details(store, kind):
    raw = next(value for key, value in store.data.items() if key.endswith("/" + kind + "_json.gz"))
    return json.loads(gzip.decompress(raw))["details"]


def test_exact_immutable_prefix_no_new_imports():
    source = Path(w.__file__).read_bytes()
    prefix = Path("research/target_price_revisions_qc/extended_refusal_witness.py").read_bytes()
    assert len(prefix) == 11770
    assert hashlib.sha256(prefix).hexdigest() == "82e7298046ab1642fb54adea98f2341b311ee6be955e16dfb345f2ea335856ba"
    assert source[:11770] == prefix
    assert b"import " not in source[11770:]


def test_constructor_no_getters_or_effects():
    dependency = object()
    witness = w.ContextRefusalWitness(dependency, dependency, dependency, dependency)
    assert witness.outcomes == {} and witness._context_attempted == set()


def test_first_out_of_bounds_original_order_exact_index_raw_once(case, capsys):
    witness, _, store = case
    members, rows = members_and_rows([None, Decimal("0"), Decimal("0.5"), Decimal("1.25"), Decimal("2.5")])
    assert membership(witness, members, rows)
    row = details(store, "membership")
    assert row["member_sid"] == "SYNTHETIC_3" and row["raw_weight"]["text"] == "1.25"
    assert row["guard_weight"]["text"] == "1.25" and row["no_unit_scaling_applied"] is True
    assert [item.reads for item in rows] == [0, 0, 0, 1, 0]
    assert not membership(witness, members, rows) and rows[3].reads == 1
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("weights", [[None, 0, Decimal("0.5"), 1], [None], [0]])
def test_no_invalid_member_never_fabricated(case, weights):
    witness, _, store = case
    members, rows = members_and_rows(weights)
    assert not membership(witness, members, rows) and not store.calls
    assert not membership(witness, *members_and_rows([Decimal("1.25")]))


@pytest.mark.parametrize("alter", ["reorder", "duplicate_row", "duplicate_member", "duplicate_ticker", "mismatch", "length"])
def test_ambiguous_or_unmatched_identity_never_guessed(case, alter):
    witness, _, store = case
    members, rows = members_and_rows([Decimal("1.25"), Decimal("2.5")])
    if alter == "reorder": rows.reverse()
    elif alter == "duplicate_row": rows[1].symbol = rows[0].symbol
    elif alter == "duplicate_member": members[1]["symbol"] = members[0]["symbol"]
    elif alter == "duplicate_ticker": members[1]["ticker"] = members[0]["ticker"]
    elif alter == "mismatch": rows[0].symbol = SimpleNamespace(id="FOREIGN_SYNTHETIC")
    else: rows.pop()
    assert not membership(witness, members, rows) and not store.calls
    assert all(item.reads == 0 for item in rows)


@pytest.mark.parametrize("raw", [None, Decimal("0.25"), Decimal("2.50")])
def test_raw_canonical_parity_is_required(case, raw):
    witness, _, store = case
    members, rows = members_and_rows([Decimal("1.25")])
    rows[0].raw = raw
    assert not membership(witness, members, rows) and not store.calls
    assert rows[0].reads == 1


def test_native_identifier_adapter_is_exact_not_generic_repr(case):
    witness, _, store = case
    members, rows = members_and_rows([Decimal("1.25")])
    native = NativeIdentifier("SYNTHETIC_NATIVE_SID")
    members[0]["symbol"].id = rows[0].symbol.id = native
    assert membership(witness, members, rows)
    assert details(store, "membership")["member_sid"] == "SYNTHETIC_NATIVE_SID" and native.calls == 2


@pytest.mark.parametrize("native_id", [1, object()])
def test_unknown_identity_type_refused_without_guessing(case, native_id):
    witness, _, store = case
    members, rows = members_and_rows([Decimal("1.25")])
    rows[0].symbol.id = native_id
    assert not membership(witness, members, rows) and not store.calls and not rows[0].reads


@pytest.mark.parametrize("error", [ValueError("SYNTHETIC SECRET"), ValueError("ambiguous native membership identity"), RuntimeError("membership weight outside bounds")])
def test_only_exact_original_weight_error_can_build_context(case, error):
    witness, _, store = case
    members, rows = members_and_rows([Decimal("1.25")])
    assert not membership(witness, members, rows, error) and not store.calls and not rows[0].reads


def test_membership_context_failure_consumed_and_original_error_preserved(case):
    witness, _, store = case
    members, rows = members_and_rows([Decimal("1.25")])
    rows[0].failure = ValueError("SYNTHETIC PRIVATE GETTER FAILURE")
    original = ValueError("membership weight outside bounds")
    with pytest.raises(ValueError) as caught:
        try: raise original
        except ValueError:
            assert not membership(witness, members, rows, original)
            raise
    rows[0].failure = None
    assert not membership(witness, members, rows) and rows[0].reads == 1 and not store.calls
    assert caught.value is original


@pytest.mark.parametrize("cancellation", [KeyboardInterrupt, SystemExit])
def test_membership_cancellation_propagates_without_retry(case, cancellation):
    witness, _, store = case
    members, rows = members_and_rows([Decimal("1.25")])
    rows[0].failure = cancellation()
    with pytest.raises(cancellation): membership(witness, members, rows)
    assert not membership(witness, members, rows) and rows[0].reads == 1 and not store.calls


def test_mark_observes_warning_delisted_without_current_action_authority(case):
    witness, _, store = case
    assert mark(witness, last=Bar())
    row = details(store, "mark")
    assert row["warning_id_observed"] and row["delisted_id_observed"]
    assert all(value is None for value in row["action_flags"].values())
    assert not row["settlement_authority_proven"] and not row["freshness_exception_granted"]
    assert row["native_quantity"]["text"] == "3" and row["ledger_quantity"]["numerator"] == "3"
    assert row["cache_price"]["numerator"] == "10" and row["raw_price"]["text"] == "10.00"
    assert not mark(witness, last=Bar()) and len(store.data) == 1


def test_optional_mark_getter_failure_retained_as_unverified_null(case):
    witness, _, store = case
    assert mark(witness, last=PartialBar())
    row = details(store, "mark")
    assert row["bar_time"]["text"] is None and row["raw_price"]["text"] is None
    assert row["fill_forward"] is None and row["period"]["text"] is None


def test_missing_mark_context_records_no_invented_bar_fields(case):
    witness, _, store = case
    assert mark(witness, error=ValueError("held RAW native closing mark missing"))
    row = details(store, "mark")
    assert row["end_time"]["text"] is None and row["bar_time"]["text"] is None


def test_flag_getter_failure_contained_and_not_retried(case):
    witness, _, store = case
    algo = BadAlgo(ValueError("SYNTHETIC FLAG UNAVAILABLE"))
    assert not mark(witness, algo=algo, last=Bar())
    assert not mark(witness, algo=algo, last=Bar()) and algo.reads == 1 and not store.calls


@pytest.mark.parametrize("cancellation", [KeyboardInterrupt, SystemExit])
def test_mark_flag_cancellation_propagates_without_retry(case, cancellation):
    witness, _, store = case
    algo = BadAlgo(cancellation())
    with pytest.raises(cancellation): mark(witness, algo=algo, last=Bar())
    assert not mark(witness, algo=algo, last=Bar()) and algo.reads == 1 and not store.calls


def test_failed_native_binding_does_not_fallback_or_retry_context(case):
    witness, evidence, store = case
    evidence.binding["attempt"] = 4
    members, rows = members_and_rows([Decimal("1.25")])
    assert not membership(witness, members, rows) and not store.calls
    evidence.binding["attempt"] = 3
    assert not membership(witness, members, rows) and rows[0].reads == 1
