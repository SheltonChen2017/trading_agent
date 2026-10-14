"""Synthetic only: no private files, provider, operator state or native jobs."""
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
import gzip
import hashlib
import json
import sys
from types import SimpleNamespace

import pytest

from research.target_price_revisions_qc import extended_refusal_witness as w


class Unknown:
    def __str__(self): raise AssertionError("no str")
    def __repr__(self): raise AssertionError("no repr")


class Evidence:
    def __init__(self):
        self.binding = {"candidate_id": w.CANDIDATE, "config_sha256": w.CONFIG_SHA256,
            "freeze_sha256": w.FREEZE_SHA256, "attempt": 3, "project_id": w.PROJECT,
            "job_id": "synthetic_job_31", "input_hashes": {"calendar.json": w.CALENDAR_SHA256, "synthetic.json": "a" * 64}}
        self.calls, self.change_at, self.change = 0, None, None

    def require_binding(self):
        self.calls += 1
        if self.calls == self.change_at: self.change(self.binding)


class Store:
    def __init__(self):
        self.data, self.calls = {}, []
        self.save_result, self.contains_result, self.read_result = True, None, None

    def contains_key(self, key):
        self.calls.append(("contains", key))
        return key in self.data if self.contains_result is None else self.contains_result

    def save_bytes(self, key, value):
        self.calls.append(("save", key))
        assert key not in self.data, "no overwritten fixture object"
        self.data[key] = value
        return self.save_result

    def read_bytes(self, key):
        self.calls.append(("read", key))
        return self.data[key] if self.read_result is None else self.read_result

    def keys(self): raise AssertionError("no global enumeration")
    def clear(self): raise AssertionError("no shared cache clearing")
    def delete(self, key): raise AssertionError("no delete")


@pytest.fixture
def case():
    evidence, store = Evidence(), Store()
    return w.FirstRefusalWitness(evidence, store), evidence, store


def membership(witness, error=None, **changes):
    args = {"etf": "REMX", "member_sid": "SYNTHETIC SID", "raw_weight": Decimal("1.25"),
        "guard_weight": "1.25", "end_time": datetime(2024, 7, 12), "now": datetime(2024, 7, 12, 9, 20)}
    args.update(changes)
    return witness.membership(ValueError("membership weight outside bounds") if error is None else error, **args)


def mark(witness, error=None, **changes):
    args = {"member_sid": "SYNTHETIC SID", "mark_object": object(),
        "end_time": datetime(2024, 7, 12, 16, 2), "mark_utc": datetime(2024, 7, 12, 20, 2, tzinfo=timezone.utc),
        "now": datetime(2024, 7, 12, 20, 1, tzinfo=timezone.utc), "session": "2024-07-12",
        "warning": True, "delisted": True, "action_flags": {key: None for key in w.ACTION_KEYS}}
    args.update(changes)
    return witness.mark(ValueError("held RAW closing mark stale/future") if error is None else error, **args)


def payload(store, kind):
    values = [raw for key, raw in store.data.items() if key.endswith("/" + kind + "_json.gz")]
    assert len(values) == 1
    return json.loads(gzip.decompress(values[0]))


def test_private_binding_descriptor_and_two_object_limit(case, capsys):
    witness, evidence, store = case
    assert not store.calls
    assert membership(witness) and mark(witness)
    before = list(store.calls)
    assert not membership(witness) and not mark(witness)
    assert store.calls == before and len(store.data) == 2
    for kind, outcome in witness.outcomes.items():
        row = payload(store, kind)
        descriptor = outcome["descriptor"]
        assert row["job_id"] == "synthetic_job_31" and row["look_ordinal"] == 31
        assert row["input_bound_scope"] == w.OPERATION and row["attempt"] == 3
        assert row["units_inferred"] is False and row["economics_accepted"] is False and row["new_codex_attempts"] == 0
        assert descriptor["plain_bytes"] <= 4096 and descriptor["gzip_bytes"] <= 4096
        assert hashlib.sha256(store.data[descriptor["key"]]).hexdigest() == descriptor["gzip_sha256"]
        assert outcome["status"] == "verified_private_witness" and "details" not in descriptor
        assert store.data[descriptor["key"]][4:8] == b"\0\0\0\0"
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("raw, state, text", [(None, "none", None), (0, "numeric_text", "0"),
    (Decimal("-0.05"), "numeric_text", "-0.05"), ("125", "numeric_text", "125"),
    (float("nan"), "nonfinite", "nan"), (True, "boolean", "true")])
def test_raw_value_types_preserved_without_unit_inference(case, raw, state, text):
    witness, _, store = case
    assert membership(witness, raw_weight=raw)
    details = payload(store, "membership")["details"]
    assert details["raw_weight"]["state"] == state and details["raw_weight"]["text"] == text
    assert details["guard_weight"]["text"] == "1.25"
    assert details["source_version"] is None and details["unit_expected"] is None and details["source_date"] is None
    assert details["no_unit_scaling_applied"] is True


def test_rational_and_clr_scalar_adapter_are_exact(case, monkeypatch):
    culture = object()
    monkeypatch.setitem(sys.modules, "System.Globalization", SimpleNamespace(CultureInfo=SimpleNamespace(InvariantCulture=culture)))
    class NativeDecimal:
        def GetType(self): return SimpleNamespace(FullName="System.Decimal")
        def ToString(self, passed):
            assert passed is culture
            return "1.2500"
        def __str__(self): raise AssertionError("no arbitrary str")
        def __repr__(self): raise AssertionError("no arbitrary repr")
    witness, _, store = case
    assert membership(witness, raw_weight=NativeDecimal(), guard_weight=Fraction(5, 4))
    details = payload(store, "membership")["details"]
    assert details["raw_weight"] == {"type": "System.Decimal", "state": "numeric_text", "text": "1.2500"}
    assert details["guard_weight"] == {"type": "fractions.Fraction", "state": "rational", "numerator": "5", "denominator": "4"}


def test_unknown_value_withheld_without_repr_or_secret_text(case):
    witness, _, store = case
    assert membership(witness, raw_weight=Unknown(), guard_weight="SYNTHETIC_PRIVATE_TOKEN_NOT_A_NUMBER")
    raw = gzip.decompress(next(iter(store.data.values())))
    assert b"SYNTHETIC_PRIVATE_TOKEN" not in raw
    row = json.loads(raw)["details"]
    assert row["raw_weight"]["state"] == "unsupported" and row["guard_weight"]["text"] is None


def test_mark_clocks_and_optional_typed_details_do_not_waive_freshness(case):
    witness, _, store = case
    assert mark(witness, bar_time=datetime(2024, 7, 11), period=86400, fill_forward=True,
        native_quantity=Decimal("3"), ledger_quantity="3", raw_price="12.5", cache_price="12.4")
    details = payload(store, "mark")["details"]
    assert details["end_time"]["text"] == "2024-07-12T16:02:00" and not details["end_time"]["offset_observed"]
    assert details["mark_utc"]["text"] == "2024-07-12T20:02:00+00:00"
    assert details["bar_time"]["text"] == "2024-07-11T00:00:00"
    assert details["raw_price"]["text"] == "12.5" and details["cache_price"]["text"] == "12.4"
    assert details["warning_id_observed"] and details["delisted_id_observed"]
    assert all(value is None for value in details["action_flags"].values())
    assert not details["freshness_exception_granted"] and not details["settlement_authority_proven"]
    assert details["full_price_bar_rows_retained"] is False


@pytest.mark.parametrize("field, value", [("candidate_id", "OTHER"), ("project_id", 1), ("project_id", True),
    ("job_id", ""), ("job_id", "a/b"), ("attempt", 4), ("attempt", True), ("freeze_sha256", "0" * 64),
    ("config_sha256", "0" * 64), ("input_hashes", {"calendar.json": "0" * 64})])
def test_wrong_or_missing_binding_refuses_before_store(case, field, value):
    witness, evidence, store = case
    evidence.binding[field] = value
    assert not membership(witness) and not store.calls


@pytest.mark.parametrize("at", [2, 3, 4, 5, 6])
def test_input_hash_identity_change_is_refused_at_each_effect_boundary(case, at):
    witness, evidence, store = case
    evidence.change_at = at
    evidence.change = lambda row: row["input_hashes"].update({"synthetic.json": "b" * 64})
    assert not membership(witness)
    assert witness.outcomes["membership"] == {"status": "failed_or_uncertain", "descriptor": None}
    assert sum(kind == "save" for kind, _ in store.calls) <= 1


def test_collision_refused_and_existing_object_not_overwritten(case):
    witness, _, store = case
    key = f"tpr-ext26/refusal-witness/{w.OPERATION}/{w.PROJECT}/synthetic_job_31/membership_json.gz"
    store.data[key] = b"synthetic prior immutable object"
    assert not membership(witness)
    assert store.data[key] == b"synthetic prior immutable object" and not any(kind == "save" for kind, _ in store.calls)


@pytest.mark.parametrize("result", [False, 1, None])
def test_save_requires_exact_true_and_never_retries(case, result):
    witness, _, store = case
    store.save_result = result
    assert not membership(witness)
    before = list(store.calls)
    assert not membership(witness) and store.calls == before


@pytest.mark.parametrize("result", [b"corrupted", b"x" * 4097, "not bytes"])
def test_readback_refusal_retains_uncertainty(case, result):
    witness, _, store = case
    store.read_result = result
    assert not membership(witness) and witness.outcomes["membership"]["descriptor"] is None


def test_non_boolean_contains_refused_before_write(case):
    witness, _, store = case
    store.contains_result = 0
    assert not membership(witness) and not any(kind == "save" for kind, _ in store.calls)


def test_original_value_error_preserved_when_witness_binding_fails(case):
    witness, evidence, _ = case
    evidence.change_at = 3
    evidence.change = lambda row: row["input_hashes"].update({"synthetic.json": "b" * 64})
    original = ValueError("membership weight outside bounds")
    with pytest.raises(ValueError) as caught:
        try:
            raise original
        except ValueError:
            assert not membership(witness, original)
            raise
    assert caught.value is original


def test_ordinary_diagnostic_failure_cannot_mask_original_value_error(case):
    witness, _, store = case
    def interrupted(key): raise MemoryError()
    store.contains_key = interrupted
    original = ValueError("membership weight outside bounds")
    with pytest.raises(ValueError) as caught:
        try:
            raise original
        except ValueError:
            assert not membership(witness, original)
            raise
    assert caught.value is original
    assert witness.outcomes["membership"]["status"] == "failed_or_uncertain"


@pytest.mark.parametrize("cancellation", [KeyboardInterrupt, SystemExit])
def test_genuine_cancellation_propagates_and_does_not_retry(case, cancellation):
    witness, _, store = case
    def interrupted(key): raise cancellation()
    store.contains_key = interrupted
    with pytest.raises(cancellation): membership(witness)
    assert not membership(witness)
    assert witness.outcomes["membership"]["status"] == "failed_or_uncertain"


def test_foreign_error_and_bad_context_contained(case):
    witness, _, store = case
    assert not membership(witness, ValueError("SYNTHETIC SECRET")) and not store.calls
    assert not mark(witness, session="2024-02-30") and not store.calls
    assert all(row["descriptor"] is None for row in witness.outcomes.values())


def test_outcome_projection_does_not_alias_custody_descriptor(case):
    witness, _, _ = case
    assert membership(witness)
    projected = witness.outcomes
    projected["membership"]["descriptor"]["plain_sha256"] = "tampered"
    assert witness.outcomes["membership"]["descriptor"]["plain_sha256"] != "tampered"
