"""Synthetic extended construction/basis proofs; no native/provider/QC I/O."""
import ast
from collections.abc import Mapping
from copy import deepcopy
from decimal import Decimal, Inexact, localcontext
from fractions import Fraction
import hashlib
import inspect
from pathlib import Path

import pytest

from research.target_price_revisions_qc import cap_tilt, extended_construction as c

MARK = "2025-01-03T21:00:00+00:00"
CUTOFF = "2025-01-03T23:00:00+00:00"
DECISION = "2025-01-06T14:20:00+00:00"
SOURCE = "a" * 64


def basis(**changes):
    value = {"schema": c.BASIS_SCHEMA, "scope": c.BASIS_SCOPE, "state": "known",
        "security_id": "A", "mark_utc": MARK, "cutoff_utc": CUTOFF,
        "decision_utc": DECISION, "received_utc": DECISION,
        "price_multiplier": "1", "prior_factor": "1", "current_factor": "1",
        "direction": c.BASIS_DIRECTION, "source_sha256": SOURCE,
        "provenance": "native-factor-file-ratio"}
    return {**value, **changes}


def factor(value, **changes):
    expected = {"security_id": "A", "mark_utc": MARK, "cutoff_utc": CUTOFF,
                "decision_utc": DECISION, "source_sha256": SOURCE}
    return c.known_basis_factor(value, **{**expected, **changes})


def members_by_sleeve(**sleeves):
    return {etf: [{"sid": sid, "ticker": "T-" + sid, "weight": None}
                  for sid in sleeves.get(etf, ())] for etf in cap_tilt.ETFS}


def check_conservation(weights, report):
    total = Fraction(0)
    for etf in cap_tilt.ETFS:
        row = report["per_sleeve"][etf]
        base = Fraction(len(row["executable_ids"]), 60)
        assert row["selected_count"] == row["executable_count"] == len(row["executable_ids"])
        assert row["baseline_weight"] == row["target_weight"] == base
        assert sum(row["target_weights"].values()) == base
        assert row["cash_weight"] + base == Fraction(1, 6)
        assert row["unfilled_slots"] == 10 - len(row["executable_ids"])
        assert set(row["target_weights"]) == set(row["executable_ids"])
        assert len(row["cap_ranked_ids"]) == len(row["executable_ids"]) + len(row["removed_unusable"])
        total += base
    assert total == sum(weights.values()) == report["target_gross_weight"]
    assert total + report["cash_weight"] == 1
    assert all(0 <= value <= Fraction(1, 10) for value in weights.values())
    assert list(report["per_sleeve"]) == list(cap_tilt.ETFS)
    assert report["canonical_admission"] is False
    assert report["native_basis_authenticated"] is False
    assert report["runtime_integration_complete"] is False


def test_known_one_requires_affirmative_closed_bound_evidence():
    original = basis()
    before = deepcopy(original)
    assert factor(original) == Fraction(1)
    assert original == before
    assert factor(basis(provenance="complete-native-action-interval")) == 1
    # Equivalent represented clocks do not change the exact instant.
    assert factor(basis(received_utc="2025-01-06T09:20:00-05:00")) == 1


@pytest.mark.parametrize("prior,current,multiplier", [
    ("0.5", "1", "0.5"), ("1", "0.5", "2"),
    (Decimal("0.25"), Fraction(1, 2), Fraction(1, 2)), (2, 4, "0.5")])
def test_known_ratio_is_prior_over_current_with_exact_price_volume_orientation(prior, current, multiplier):
    with localcontext() as context:
        context.prec = 2
        context.traps[Inexact] = True
        value = factor(basis(prior_factor=prior, current_factor=current, price_multiplier=multiplier))
    assert value == Fraction(prior) / Fraction(current)
    assert Fraction(100) * value == Fraction(100) * Fraction(multiplier)
    assert Fraction(1000) / value == Fraction(1000) / Fraction(multiplier)
    assert (Fraction(100) * value) * (Fraction(1000) / value) == 100000


@pytest.mark.parametrize("value", [None, {}, {"no_split_events": True},
    basis(state="unknown"), basis(state="missing"), basis(state="no_event"),
    basis(price_multiplier=None)])
def test_missing_unknown_or_no_event_is_not_known_one(value):
    with pytest.raises(c.ConstructionError):
        factor(value)


@pytest.mark.parametrize("field", ["prior_factor", "current_factor", "price_multiplier"])
@pytest.mark.parametrize("value", [None, 0, -1, "0", "-1", True, 1.0, float("nan"),
    float("inf"), Decimal("NaN"), Decimal("Infinity"), "NaN", "Infinity",
    "1e1000000", "1" * 129, 10**100, Fraction(1, 2**513), "1_000", []])
def test_nonpositive_nonfinite_nonexact_or_resource_unbounded_basis_refuses(field, value):
    with pytest.raises(c.ConstructionError):
        factor(basis(**{field: value}))


@pytest.mark.parametrize("changes", [
    {"security_id": "B"}, {"mark_utc": "2025-01-02T21:00:00+00:00"},
    {"cutoff_utc": "2025-01-02T23:00:00+00:00"},
    {"decision_utc": "2025-01-06T14:19:59+00:00"},
    {"decision_utc": "2025-01-06T14:20:01+00:00"},
    {"received_utc": "2025-01-03T22:59:59+00:00"},
    {"received_utc": "2025-01-06T14:20:01+00:00"},
    {"mark_utc": "2025-01-03T21:00:00"}, {"source_sha256": "b" * 64},
    {"source_sha256": "A" * 64}, {"provenance": "subscription-with-no-events"},
    {"provenance": []}, {"scope": "analyst-target-basis"},
    {"direction": "decision-raw-price-times-factor-to-prior-share-units"},
    {"schema": "future"}, {"future": True}])
def test_basis_wrong_identity_stale_future_clock_hash_or_scope_refuses(changes):
    with pytest.raises(c.ConstructionError):
        factor(basis(**changes))


@pytest.mark.parametrize("changes", [{"security_id": ""}, {"security_id": "A\nB"},
    {"source_sha256": None}, {"decision_utc": CUTOFF}, {"mark_utc": DECISION},
    {"mark_utc": "invalid"}, {"cutoff_utc": "2025-01-03T23:00:00"}])
def test_expected_basis_contract_must_itself_be_known_and_ordered(changes):
    with pytest.raises(c.ConstructionError):
        factor(basis(), **changes)


def test_reverse_or_mismatched_ratio_does_not_pass_known_factor_label():
    assert factor(basis(prior_factor="0.5", current_factor="1", price_multiplier="0.5")) == Fraction(1, 2)
    with pytest.raises(c.ConstructionError):
        factor(basis(prior_factor="0.5", current_factor="1", price_multiplier="2"))
    with pytest.raises(c.ConstructionError):
        factor(basis(prior_factor="1", current_factor="0.5", price_multiplier="0.5"))


def test_on_retains_unchanged_twenty_percent_quantized_transfer_not_neutral_weights():
    members = members_by_sleeve(SPY=["LOW", "HIGH"])
    weights, report = c.construct_on(members, {"LOW": "2", "HIGH": "1"},
                                     {"LOW": "-9", "HIGH": "9"})
    amount = Fraction(1, 300) // cap_tilt.TRANSFER_QUANTUM * cap_tilt.TRANSFER_QUANTUM
    assert weights == {"LOW": Fraction(1, 60) - amount, "HIGH": Fraction(1, 60) + amount}
    assert report["transferred_weight"] == amount > 0
    assert report["per_sleeve"]["SPY"]["rank_tilts"] == {"LOW": -1, "HIGH": 1}
    check_conservation(weights, report)


@pytest.mark.parametrize("unusable", ["warning", "final"])
@pytest.mark.parametrize("sid", ["LOW", "HIGH"])
def test_unusable_donor_or_recipient_removed_before_scores_and_conservation(unusable, sid):
    members = members_by_sleeve(SPY=["LOW", "MID", "HIGH"])
    caps = {"LOW": "30", "MID": "20", "HIGH": "10"}
    class Scores(dict):
        def get(self, key, default=None):
            assert key != sid, "removed score was queried"
            return super().get(key, default)
    scores = Scores(LOW="-9", MID="1", HIGH="9")
    weights, report = c.construct_on(members, caps, scores, **{unusable + "_ids": [sid]})
    row = report["per_sleeve"]["SPY"]
    assert row["cap_ranked_ids"] == ("LOW", "MID", "HIGH")
    assert sid not in weights and sid not in row["rank_tilts"]
    assert row["removed_unusable"] == ({"security_id": sid, "state": unusable},)
    assert row["score_state_counts"]["nonzero"] == 2
    assert row["target_weight"] == Fraction(1, 30)
    assert row["transferred_weight"] > 0
    assert report["removed_unusable_slot_count"] == 1
    check_conservation(weights, report)


def test_cap_top10_ranks_first_then_unusable_slot_remains_cash_without_rank11():
    names = [f"S{i:02d}" for i in range(12)]
    members = members_by_sleeve(SPY=names)
    caps = {sid: str(12 - i) for i, sid in enumerate(names)}
    weights, report = c.construct_on(members, caps, {sid: str(i) for i, sid in enumerate(names)},
                                     final_ids=["S00"])
    row = report["per_sleeve"]["SPY"]
    assert row["cap_ranked_ids"] == tuple(names[:10])
    assert row["executable_ids"] == tuple(names[1:10])
    assert "S10" not in weights and "S11" not in weights
    assert row["cap_coverage"]["selected_count"] == 10
    assert row["selected_count"] == 9 and row["unfilled_slots"] == 1
    assert row["cash_weight"] == Fraction(1, 60)
    check_conservation(weights, report)


def test_removed_overlapping_name_releases_each_sleeve_slot_not_other_weights():
    members = members_by_sleeve(**{etf: ["X", "D-" + etf] for etf in cap_tilt.ETFS})
    caps = {"X": "100", **{"D-" + etf: "50" for etf in cap_tilt.ETFS}}
    weights, report = c.construct_on(members, caps, {}, warning_ids=["X"], final_ids=["X"])
    assert "X" not in weights
    assert report["removed_unusable_slot_count"] == 6
    assert report["cap_ranked_slot_count"] == 12 and report["executable_slot_count"] == 6
    assert set(weights.values()) == {Fraction(1, 60)}
    assert all(row["removed_unusable"] == ({"security_id": "X", "state": "final"},)
               for row in report["per_sleeve"].values())
    check_conservation(weights, report)


def test_cap_selection_identity_parity_independent_of_signal_and_input_order():
    members = members_by_sleeve(SPY=["A", "B", "C"], XLV=["A", "D"], REMX=["R"])
    caps = {"A": "10", "B": "20", "C": "30", "D": "40", "R": None}
    first = c.construct_on(members, caps, {"A": "-1", "B": "0", "C": "3", "D": "9"})
    second = c.construct_on(dict(reversed(tuple(members.items()))), caps,
        {"A": {"state": "unknown", "value": "999"}, "B": "1000", "C": "-9"})
    neutral = c.construct_off(members, caps)
    for _, report in (first, second, neutral):
        assert report["per_sleeve"]["SPY"]["cap_ranked_ids"] == ("C", "B", "A")
        assert report["per_sleeve"]["XLV"]["executable_ids"] == ("D", "A")
    assert first[1]["baseline_weights"] == second[1]["baseline_weights"] == neutral[1]["baseline_weights"]
    assert set(first[0]) == set(second[0]) == set(neutral[0])
    assert neutral[0] == neutral[1]["baseline_weights"]
    for weights, report in (first, second, neutral):
        check_conservation(weights, report)


def test_off_no_signal_parameter_and_no_signal_mapping_queries_even_at_internal_branch():
    class Forbidden(Mapping):
        def __len__(self):
            raise AssertionError("OFF measured signal input")
        def __iter__(self):
            raise AssertionError("OFF iterated signal input")
        def __getitem__(self, key):
            raise AssertionError("OFF queried signal input")
        def get(self, key, default=None):
            raise AssertionError("OFF queried signal input")
    members, caps = members_by_sleeve(SPY=["A", "B"]), {"A": "2", "B": "1"}
    assert "scores_by_sid" not in inspect.signature(c.construct_off).parameters
    expected = c.construct_off(members, caps)
    actual = c._construct(members, caps, Forbidden(), arm="tpr_off", warning_ids=(), final_ids=())
    assert actual == expected
    assert all(row["score_state_counts"] == {"not_used": row["executable_count"]}
               and row["ranked_score_count"] == 0 and row["transfer_count"] == 0
               for row in actual[1]["per_sleeve"].values())
    check_conservation(*actual)


def test_missing_caps_and_slots_are_explicit_cash_not_measured_zero():
    members = members_by_sleeve(SPY=["A", "B", "C", "D", "E"])
    caps = {"A": {"state": "available", "value": "10"},
        "B": {"state": "unknown", "value": "999999"},
        "C": {"state": "missing", "value": None}, "D": "NaN", "E": "0"}
    weights, report = c.construct_on(members, caps, {})
    row = report["per_sleeve"]["SPY"]
    assert weights == {"A": Fraction(1, 60)}
    assert row["cap_coverage"]["cap_state_counts"] == {
        "available": 1, "missing": 1, "unknown": 1, "invalid": 1, "nonpositive": 1}
    assert row["score_state_counts"]["missing"] == 1 and row["score_state_counts"]["zero"] == 0
    assert row["unfilled_slots"] == 9
    check_conservation(weights, report)


def test_inputs_stay_unmodified_and_foreign_unusable_names_are_reported_not_members():
    members, caps, scores = members_by_sleeve(SPY=["A", "B"]), {"A": "2", "B": "1"}, {"A": "1"}
    before = deepcopy((members, caps, scores))
    weights, report = c.construct_on(members, caps, scores, final_ids=["OUTSIDE"])
    assert (members, caps, scores) == before
    assert report["nonmember_unusable_id_count"] == 1
    assert report["removed_unusable_slot_count"] == 0
    check_conservation(weights, report)
    _, repeated = c.construct_on(members, caps, scores, final_ids=["OUTSIDE"])
    report["per_sleeve"]["SPY"]["target_weights"].clear()
    assert repeated["per_sleeve"]["SPY"]["target_weights"]


@pytest.mark.parametrize("change", ["missing_sleeve", "extra_sleeve", "bad_member",
    "duplicate_member", "bad_warning", "duplicate_final", "too_many_members", "too_many_caps"])
def test_malformed_or_unbounded_construction_refuses(change):
    members, caps, kwargs = members_by_sleeve(SPY=["A", "B"]), {"A": "2", "B": "1"}, {}
    if change == "missing_sleeve": del members["XLE"]
    elif change == "extra_sleeve": members["OTHER"] = []
    elif change == "bad_member": members["SPY"] = [None]
    elif change == "duplicate_member": members["SPY"].append(members["SPY"][0])
    elif change == "bad_warning": kwargs["warning_ids"] = [None]
    elif change == "duplicate_final": kwargs["final_ids"] = ["A", "A"]
    elif change == "too_many_members": members["SPY"] = [{}] * (c.MAX_IDENTITIES + 1)
    elif change == "too_many_caps": caps = {str(i): "1" for i in range(c.MAX_IDENTITIES + 1)}
    with pytest.raises(c.ConstructionError):
        c.construct_off(members, caps, **kwargs)


def test_source_is_pure_and_original_tilt_bytes_remain_exact():
    source = Path(c.__file__).read_text()
    tree = ast.parse(source)
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imports |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert imports == {"__future__", "collections.abc", "datetime", "decimal", "fractions", "re", None}
    relative = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.level]
    assert len(relative) == 1 and [alias.name for alias in relative[0].names] == ["cap_tilt"]
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id in {"open", "exec", "eval", "__import__"} for node in ast.walk(tree))
    assert hashlib.sha256(Path(cap_tilt.__file__).read_bytes()).hexdigest() == \
        "262f568b7c0fe0b08af8a26896431465c17746bcd32e9addc568f58631e11a5c"
