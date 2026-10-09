"""Synthetic cap-selection and exact within-selected TPR tilt contracts."""
import ast
from copy import deepcopy
from decimal import Decimal, Inexact, localcontext
from fractions import Fraction
from itertools import product
from pathlib import Path

import pytest

from research.target_price_revisions_qc import cap_tilt as c


def members(*sids):
    return [{"sid": sid, "ticker": "T-" + sid, "weight": None} for sid in sids]


def sleeves(**selected):
    return {etf: selected.get(etf, []) for etf in c.ETFS}


def moved(rank=Fraction(1)):
    amount = Fraction(1, 60) * Fraction(1, 5) * abs(rank)
    return (amount // Fraction(1, 10**30)) * Fraction(1, 10**30)


def test_cap_ranks_descending_exact_not_decimal_context_or_ticker_order():
    rows = [{"sid": "B", "ticker": "AAA"}, {"sid": "A", "ticker": "ZZZ"},
            {"sid": "C", "ticker": "CCC"}]
    with localcontext() as context:
        context.prec = 3
        context.traps[Inexact] = True
        selected, coverage = c.rank_cap_members(rows, {
            "B": "100000000000000000000000.01",
            "A": "100000000000000000000000.02", "C": "1"})
    assert selected == ["A", "B", "C"]
    assert coverage["represented_positive_cap_sum"] == Fraction(
        "200000000000000000000001.03")
    assert coverage["cap_state_counts"] == {
        "available": 3, "missing": 0, "unknown": 0, "invalid": 0, "nonpositive": 0}


def test_equal_caps_tie_by_sid_not_member_order():
    rows = members("Z", "B", "A")
    caps = {sid: "100" for sid in ("Z", "B", "A")}
    assert c.rank_cap_members(rows, caps)[0] == ["A", "B", "Z"]
    assert c.rank_cap_members(list(reversed(rows)), caps)[0] == ["A", "B", "Z"]


def test_cap_selection_never_uses_tpr_presence_sign_or_weight():
    first = members("A", "B", "C")
    for row, score in zip(first, ("-9", None, "9000000")):
        row.update(score=score, tpr_state="missing", weight="NaN")
    second = deepcopy(first)
    for row in second:
        row.update(score="0", tpr_state="eligible", weight="1")
    caps = {"A": "10", "B": "30", "C": "20"}
    assert c.rank_cap_members(first, caps) == c.rank_cap_members(second, caps)
    assert c.rank_cap_members(first, caps)[0] == ["B", "C", "A"]


def test_cap_states_partition_all_members_not_missing_to_zero():
    rows = members("A", "B", "C", "D", "E", "F", "G", "H", "I")
    selected, coverage = c.rank_cap_members(rows, {
        "A": {"state": "available", "value": "100"},
        "B": {"state": "missing", "value": None},
        "C": {"state": "unknown", "value": "9999999999"},
        "D": {"state": "invalid", "value": "100000"},
        "E": {"state": "nonpositive", "value": "0"},
        "F": "-1", "G": None,
        "H": {"state": "available", "value": "NaN"},
        "EXTRA": "99999999999999"})
    assert selected == ["A"]
    assert coverage["member_count"] == 9
    assert coverage["cap_state_counts"] == {
        "available": 1, "missing": 3, "unknown": 1, "invalid": 2, "nonpositive": 2}
    assert sum(coverage["cap_state_counts"].values()) == coverage["member_count"]
    assert coverage["eligible_count"] == 1
    assert coverage["selected_count"] == 1
    assert coverage["unfilled_slots"] == 9
    assert coverage["represented_positive_cap_sum"] == 100
    assert coverage["ignored_nonmember_cap_rows"] == 1


@pytest.mark.parametrize("value", [True, False, 1.0, float("nan"), float("inf"),
    Decimal("NaN"), Decimal("Infinity"), "NaN", "Infinity", "1_000", " 1", "1 ",
    "1/3", "", [], {}, {"state": "available"}, {"state": "bogus", "value": "2"},
    {"state": "available", "value": "2", "future": True},
    {"state": "nonpositive", "value": "2"}])
def test_invalid_cap_is_excluded_with_explicit_count(value):
    selected, coverage = c.rank_cap_members(members("A"), {"A": value})
    assert selected == []
    assert coverage["cap_state_counts"]["invalid"] == 1
    assert coverage["cap_state_counts"]["missing"] == 0
    assert coverage["cap_state_counts"]["nonpositive"] == 0


@pytest.mark.parametrize("value", ["0", "-0", "-2", 0, -3, Decimal("0"), Fraction(-1, 3),
                                   {"state": "nonpositive", "value": None}])
def test_nonpositive_cap_has_separate_state(value):
    selected, coverage = c.rank_cap_members(members("A"), {"A": value})
    assert selected == []
    assert coverage["cap_state_counts"]["nonpositive"] == 1
    assert coverage["cap_state_counts"]["invalid"] == 0


@pytest.mark.parametrize("value", ["1e2", "+.25", "2.", 2, Decimal("2.000"), Fraction(2, 7)])
def test_positive_exact_numeric_representations_are_supported(value):
    selected, coverage = c.rank_cap_members(members("A"), {"A": value})
    assert selected == ["A"]
    assert coverage["cap_state_counts"]["available"] == 1


def test_cap_selection_stops_at_ten_without_renormalizing_coverage():
    rows = members(*(f"S{i:02d}" for i in range(12)))
    caps = {row["sid"]: str(i + 1) for i, row in enumerate(rows)}
    selected, coverage = c.rank_cap_members(rows, caps)
    assert selected == [f"S{i:02d}" for i in reversed(range(2, 12))]
    assert coverage["member_count"] == coverage["eligible_count"] == 12
    assert coverage["eligible_unselected_count"] == 2
    assert coverage["unfilled_slots"] == 0


@pytest.mark.parametrize("rows", [[{"sid": "", "ticker": "T"}],
    [{"sid": " A", "ticker": "T"}], [{"sid": 1, "ticker": "T"}],
    [{"sid": "A", "ticker": None}], [{"sid": "A", "ticker": " T"}],
    [{"sid": "A", "ticker": "TA"}, {"sid": "A", "ticker": "TB"}],
    [{"sid": "A", "ticker": "TA"}, {"sid": "B", "ticker": "TA"}], [None]])
def test_ambiguous_member_identity_refuses(rows):
    with pytest.raises(c.CapTiltError):
        c.rank_cap_members(rows, {})


def test_cap_input_and_empty_inventory_are_pure():
    rows, caps = members("A"), {"A": {"state": "unknown", "value": "10"}}
    original = deepcopy((rows, caps))
    c.rank_cap_members(rows, caps)
    assert (rows, caps) == original
    selected, coverage = c.rank_cap_members([], {"OUTSIDE": object()})
    assert selected == []
    assert coverage["member_count"] == 0
    assert coverage["unfilled_slots"] == 10
    assert coverage["represented_positive_cap_sum"] == 0


def test_two_selected_scores_make_exact_budget_conserving_transfer():
    targets, diagnostic = c.tilt_sleeves(sleeves(SPY=["A", "B"]), {"A": "-4", "B": "9"})
    amount = moved()
    assert targets == {"A": Fraction(1, 60) - amount, "B": Fraction(1, 60) + amount}
    assert sum(targets.values()) == Fraction(1, 30)
    assert diagnostic["cash_weight"] == Fraction(29, 30)
    assert diagnostic["transferred_weight"] == amount
    assert diagnostic["selected_slot_count"] == 2
    row = diagnostic["per_sleeve"]["SPY"]
    assert row["rank_tilts"] == {"A": -1, "B": 1}
    assert row["baseline_weight"] == row["target_weight"] == Fraction(1, 30)
    assert row["cash_weight"] == Fraction(2, 15)
    assert row["maximum_absolute_relative_change"] <= Fraction(1, 5)
    assert row["recipient_underfill"] == row["aggregate_cap_blocked_capacity"] == 0


def test_exact_zero_stays_neutral_and_does_not_enter_rank_group():
    targets, diagnostic = c.tilt_sleeves(sleeves(SPY=["Z", "L", "H"]),
                                         {"Z": "0", "L": "1", "H": "2"})
    assert targets["Z"] == Fraction(1, 60)
    assert targets["L"] == Fraction(1, 60) - moved()
    assert targets["H"] == Fraction(1, 60) + moved()
    row = diagnostic["per_sleeve"]["SPY"]
    assert row["score_state_counts"]["zero"] == 1
    assert row["ranked_score_count"] == 2
    assert "Z" not in row["rank_tilts"]


def test_missing_unknown_invalid_and_zero_scores_are_separately_neutral():
    selected = sleeves(SPY=["M", "N", "U", "I", "Z", "F", "L", "H"])
    targets, diagnostic = c.tilt_sleeves(selected, {"N": None,
        "U": {"state": "unknown", "value": "999999"},
        "I": {"state": "invalid", "value": "-10000"},
        "Z": {"state": "zero", "value": "0"}, "F": float("nan"), "L": "1", "H": "2"})
    assert all(targets[sid] == Fraction(1, 60) for sid in ("M", "N", "U", "I", "Z", "F"))
    assert diagnostic["per_sleeve"]["SPY"]["score_state_counts"] == {
        "nonzero": 2, "zero": 1, "missing": 2, "unknown": 1, "invalid": 2}
    assert set(targets) == set(selected["SPY"])


@pytest.mark.parametrize("value", [True, 1.0, Decimal("NaN"), "Infinity",
    {"state": "zero", "value": "3"}, {"state": "nonzero", "value": "0"},
    {"state": "available", "value": "1", "future": True}])
def test_invalid_score_does_not_relabel_zero_or_change_eligibility(value):
    target, diagnostic = c.tilt_sleeves(sleeves(SPY=["A", "B"]), {"A": value, "B": "2"})
    assert target == {"A": Fraction(1, 60), "B": Fraction(1, 60)}
    row = diagnostic["per_sleeve"]["SPY"]
    assert row["score_state_counts"]["invalid"] == 1
    assert row["score_state_counts"]["zero"] == 0
    assert row["ranked_score_count"] == 1


def test_all_negative_scores_are_relative_rank_not_short_or_selection_rule():
    target, _ = c.tilt_sleeves(sleeves(SPY=["A", "B"]), {"A": "-9", "B": "-2"})
    assert target == {"A": Fraction(1, 60) - moved(), "B": Fraction(1, 60) + moved()}


@pytest.mark.parametrize("scores", [{}, {"A": "7"}, {"A": "7", "B": "7"},
                                      {"A": "0", "B": "0"}])
def test_no_rank_comparison_or_tied_only_sleeve_is_neutral(scores):
    target, diagnostic = c.tilt_sleeves(sleeves(SPY=["A", "B"]), scores)
    assert target == {"A": Fraction(1, 60), "B": Fraction(1, 60)}
    assert diagnostic["transferred_weight"] == 0


def test_tied_midrank_capacity_and_tie_transfer_order_are_exact():
    scores = {"A": "1", "B": "1", "C": "2", "D": "4", "E": "4"}
    target, diagnostic = c.tilt_sleeves(sleeves(SPY=list(reversed(scores))), scores)
    row = diagnostic["per_sleeve"]["SPY"]
    assert row["rank_tilts"] == {
        "A": Fraction(-3, 4), "B": Fraction(-3, 4), "C": 0,
        "D": Fraction(3, 4), "E": Fraction(3, 4)}
    amount = Fraction(1, 400)
    assert target == {"A": Fraction(1, 60) - amount, "B": Fraction(1, 60) - amount,
                      "C": Fraction(1, 60), "D": Fraction(1, 60) + amount,
                      "E": Fraction(1, 60) + amount}
    assert row["transfer_count"] == 2
    assert row["transferred_weight"] == Fraction(1, 200)


def test_rank_transfer_quantum_is_floored_not_context_rounded():
    scores = {"A": "1", "B": "1", "C": "3", "D": "9"}
    with localcontext() as context:
        context.prec = 2
        context.traps[Inexact] = True
        target, diagnostic = c.tilt_sleeves(sleeves(SPY=list(scores)), scores)
    row = diagnostic["per_sleeve"]["SPY"]
    assert row["rank_tilts"] == {
        "A": Fraction(-2, 3), "B": Fraction(-2, 3), "C": Fraction(1, 3), "D": 1}
    assert target["D"] == Fraction(1, 60) + moved()
    assert target["A"] == Fraction(1, 60) - moved(Fraction(2, 3))
    assert sum(target.values()) == Fraction(1, 15)
    assert row["recipient_underfill"] >= 0
    assert all((abs(weight - Fraction(1, 60)) / c.TRANSFER_QUANTUM).denominator == 1
               for weight in target.values())


def test_aggregate_name_at_six_sleeve_cap_cannot_receive():
    selected = {etf: ["X", "D-" + etf] for etf in c.ETFS}
    scores = {"X": "9", **{"D-" + etf: "1" for etf in c.ETFS}}
    target, diagnostic = c.tilt_sleeves(selected, scores)
    assert target["X"] == Fraction(1, 10)
    assert target == diagnostic["baseline_weights"]
    assert diagnostic["transferred_weight"] == 0
    assert all(row["cap_binding_recipient_count"] == 1
               and row["recipient_underfill"] == moved()
               and row["aggregate_cap_blocked_capacity"] == moved()
               for row in diagnostic["per_sleeve"].values())


def test_prior_sleeve_donation_creates_only_actual_aggregate_headroom():
    selected = {etf: ["X"] for etf in c.ETFS}
    selected["SPY"].append("Y")
    selected["XLV"].append("Z")
    scores = {"X": "1", "Y": "9", "Z": "-9"}
    target, diagnostic = c.tilt_sleeves(selected, scores)
    assert target["X"] == Fraction(1, 10)
    assert target["Y"] == Fraction(1, 60) + moved()
    assert target["Z"] == Fraction(1, 60) - moved()
    assert diagnostic["per_sleeve"]["SPY"]["target_weights"]["X"] == Fraction(1, 60) - moved()
    assert diagnostic["per_sleeve"]["XLV"]["target_weights"]["X"] == Fraction(1, 60) + moved()
    assert diagnostic["transferred_weight"] == 2 * moved()
    assert c.tilt_sleeves(dict(reversed(tuple(selected.items()))), scores) == (target, diagnostic)


def test_zero_capacity_is_exact_matched_neutral_control_without_slot_growth():
    target, diagnostic = c.tilt_sleeves(sleeves(SPY=["A", "B"], REMX=["R"]),
                                      {"A": "-1", "B": "2", "R": "100000"}, capacity="0")
    assert target == diagnostic["baseline_weights"] == {
        "A": Fraction(1, 60), "B": Fraction(1, 60), "R": Fraction(1, 60)}
    assert diagnostic["target_gross_weight"] == Fraction(1, 20)
    assert diagnostic["cash_weight"] == Fraction(19, 20)
    assert diagnostic["transferred_weight"] == 0
    assert all(row["target_weight"] == row["baseline_weight"]
               for row in diagnostic["per_sleeve"].values())


@pytest.mark.parametrize("capacity", ["-0.0001", "1.0001", "NaN", float("nan"), 0.20, True])
def test_invalid_capacity_refuses(capacity):
    with pytest.raises(c.CapTiltError):
        c.tilt_sleeves(sleeves(), {}, capacity)


@pytest.mark.parametrize("selected", [{}, {"SPY": []},
    {**sleeves(), "OTHER": []}, sleeves(SPY="A"), sleeves(SPY=["A", "A"]),
    sleeves(SPY=[" A"]), sleeves(SPY=list(map(str, range(11))))])
def test_invalid_selected_inventory_refuses(selected):
    with pytest.raises(c.CapTiltError):
        c.tilt_sleeves(selected, {})


def test_nonselected_scores_never_enter_tilt_and_inputs_are_not_mutated():
    selected, scores = sleeves(SPY={"A": object(), "B": object()}), {
        "A": Decimal("1"), "B": Fraction(2), "UNSELECTED": object()}
    before_selected = {etf: tuple(rows) for etf, rows in selected.items()}
    before_scores = dict(scores)
    targets, diagnostic = c.tilt_sleeves(selected, scores)
    assert set(targets) == {"A", "B"}
    assert diagnostic["per_sleeve"]["SPY"]["ranked_score_count"] == 2
    assert {etf: tuple(rows) for etf, rows in selected.items()} == before_selected
    assert scores == before_scores


def test_all_synthetic_three_name_score_states_conserve_budget_and_identity():
    selected = sleeves(SPY=["A", "B", "C"])
    for values in product((None, "-2", "-1", "0", "1", "2"), repeat=3):
        target, diagnostic = c.tilt_sleeves(selected, dict(zip(("A", "B", "C"), values)))
        assert set(target) == {"A", "B", "C"}
        assert sum(target.values()) == Fraction(1, 20)
        assert diagnostic["cash_weight"] == Fraction(19, 20)
        assert all(Fraction(1, 60) * Fraction(4, 5) <= weight
                   <= Fraction(1, 60) * Fraction(6, 5) for weight in target.values())
        assert diagnostic["per_sleeve"]["SPY"]["target_weight"] == Fraction(1, 20)


def test_pure_module_has_no_runtime_provider_or_sibling_imports():
    source = Path(c.__file__).read_text()
    tree = ast.parse(source)
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imports |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names}
    assert imports == {"__future__", "collections.abc", "decimal", "fractions", "re"}
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                   and node.func.id in {"open", "eval", "exec", "__import__"}
                   for node in ast.walk(tree))
