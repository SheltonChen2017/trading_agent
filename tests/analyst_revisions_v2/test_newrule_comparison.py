"""Synthetic pure-target tests; no provider, private artifacts or QC runtime."""

import dataclasses
import json
from decimal import Decimal, localcontext

import pytest

from research.analyst_revisions_v2_qc import newrule_comparison_targets as subject


D = Decimal
PIN = "a" * 64


def books(*, shared=False, score=True):
    result = []
    for universe in subject.UNIVERSES:
        members = tuple(subject.Member(
            f"SID-{index}" if shared else f"SID-{universe}-{index}",
            f"LABEL-{index}", f"LABEL-{index}", D("0.1"),
            f"ID-{index}" if shared else f"ID-{universe}-{index}",
            f"NAME-{index}", D(10000 - index), D(index + 1) if score else None)
            for index in range(10))
        result.append(subject.Book(universe, f"ETF-{universe}", members))
    return tuple(result)


def replace_row(value, book_index=0, row_index=0, **changes):
    old = value[book_index]
    rows = list(old.members)
    rows[row_index] = dataclasses.replace(rows[row_index], **changes)
    result = list(value)
    result[book_index] = dataclasses.replace(old, members=tuple(rows))
    return tuple(result)


def build(value=None, count=6, arm=0):
    return subject.build_target(books() if value is None else value,
        universe_count=count, ar_percent=arm, source_snapshot_sha256=PIN)


def total(target):
    with localcontext() as context:
        context.prec = 96
        return sum((weight for _, _, weight in target.weights), D(0))


def diagnostics(target):
    return json.loads(target.diagnostics_bytes)


@pytest.mark.parametrize("count", [6, 8])
@pytest.mark.parametrize("arm", [0, 100, 200])
@pytest.mark.parametrize("shared", [False, True])
def test_six_cells_are_exact_long_only_conserved_and_bound(count, arm, shared):
    target = build(books(shared=shared), count, arm)
    assert total(target) == D("0.98")
    assert all(0 < weight <= D("0.098") for _, kind, weight in target.weights if kind == "stock")
    record = target.record()
    assert record["universe_count"] == count and record["ar_percent"] == arm
    assert record["point_in_time_proven"] is False
    assert record["formal_identity_admitted"] is False
    assert record["formal_forward_ready"] is False
    assert len(record["sleeves"]) == count
    assert target == build(books(shared=shared), count, arm)


@pytest.mark.parametrize("count", [6, 8])
def test_equal_budget_rounding_conserves_in_last_sleeve(count):
    values = subject.sleeve_budgets(count)
    with localcontext() as context:
        context.prec = 96
        assert sum(values, D(0)) == D("0.98")
        assert len(set(values[:-1])) == 1
        assert 0 <= values[-1] - values[0] < D("1e-23")


def test_tiny_identity_mismatch_with_huge_cap_is_not_selected():
    value = books()
    value = replace_row(value, reported_weight=D("0.001"),
                        fundamental_label="MISMATCH", market_cap=D("1e90"))
    value = replace_row(value, row_index=1, reported_weight=D("0.199"))
    target = build(value)
    first = diagnostics(target)[0]
    assert D(first["qc_technical_identity_weight_ratio"]) == D("0.999")
    assert first["refusals"] == []
    assert first["selected_count"] == 9
    assert "ID-SPY-0" not in {sid for sid, _, _ in target.weights}


def test_zero_weight_phantom_cannot_manufacture_five_names():
    value = books()
    for index in range(10):
        value = replace_row(value, row_index=index,
                            reported_weight=D("0.25") if index < 4 else D(0))
    first = diagnostics(build(value))[0]
    assert first["verified_count"] == 4
    assert "verified_name_count_below_five" in first["refusals"]
    assert first["selected_count"] == 0


@pytest.mark.parametrize("weight,refused", [("0.0949", True), ("0.095", False),
                                           ("0.105", False), ("0.1051", True)])
def test_book_completeness_boundaries(weight, refused):
    value = books()
    for index in range(10):
        value = replace_row(value, row_index=index, reported_weight=D(weight))
    first = diagnostics(build(value))[0]
    assert ("reported_book_incomplete" in first["refusals"]) is refused


@pytest.mark.parametrize("reason", ["missing_or_stale_collection", "unresolved_reported_weight"])
def test_unavailable_book_allocates_only_its_own_etf(reason):
    value = list(books())
    value[0] = dataclasses.replace(value[0], unavailable_reason=reason)
    target = build(tuple(value))
    assert ("ETF-SPY", "etf", subject.sleeve_budgets(6)[0]) in target.weights
    assert not any(sid.startswith("ID-SPY-") for sid, _, _ in target.weights)
    assert reason in diagnostics(target)[0]["refusals"]


def test_non_xle_positive_floor_and_xle_only_exception():
    target = build(books(score=False), 8, 100)
    detail = diagnostics(target)
    assert detail[5]["universe"] == "XLE" and detail[5]["selected_count"] == 10
    for index in (0, 1, 2, 3, 4, 6, 7):
        assert "positive_score_count_below_five" in detail[index]["refusals"]
        assert detail[index]["selected_count"] == 0


def test_positive_count_controls_count_not_candidate_membership():
    value = books()
    for index in range(10):
        value = replace_row(value, row_index=index, score=D(-1) if index < 5 else D(1))
    target = build(value, arm=100)
    assert diagnostics(target)[0]["selected_count"] == 5
    # The top five caps are negative; they are still the cap-selected basket.
    assert {sid for sid, _, _ in target.weights if sid.startswith("ID-SPY-")} == {
        f"ID-SPY-{index}" for index in range(5)}


def test_missing_and_exact_zero_are_neutral_in_tilt():
    value = books()
    value = replace_row(value, score=None)
    value = replace_row(value, row_index=1, score=D(0))
    # Keep ten slots using XLE, which does not trim count to positive count.
    value = replace_row(value, book_index=5, score=None)
    value = replace_row(value, book_index=5, row_index=1, score=D(0))
    baseline = dict((sid, weight) for sid, _, weight in build(value).weights)
    tilted = dict((sid, weight) for sid, _, weight in build(value, arm=200).weights)
    assert tilted["ID-XLE-0"] == baseline["ID-XLE-0"]
    assert tilted["ID-XLE-1"] == baseline["ID-XLE-1"]
    assert tilted["ID-XLE-9"] > baseline["ID-XLE-9"]
    assert 0 < tilted["ID-XLE-2"] < baseline["ID-XLE-2"]


def test_tied_scores_leave_target_unchanged():
    value = books()
    for b in range(8):
        for r in range(10):
            value = replace_row(value, b, r, score=D(1))
    assert build(value).weights == build(value, arm=200).weights


def test_duplicate_stock_cap_overflow_stays_in_contributing_own_etf():
    target = build(books(shared=True), 8, 0)
    weights = dict((sid, value) for sid, _, value in target.weights)
    assert all(weights[f"ID-{index}"] == D("0.098") for index in range(10))
    assert total(target) == D("0.98")
    # Eight complete equally weighted ten-name sleeves exactly reach the cap.
    assert not any(kind == "etf" for _, kind, _ in target.weights)


def test_scaled_coverage_and_unused_slots_return_to_own_etf():
    value = books()
    for index in range(5, 10):
        value = replace_row(value, row_index=index, economic_id=None,
                            economic_name=None, market_cap=None, score=None)
    target = build(value)
    first = diagnostics(target)[0]
    assert first["selected_count"] == 5 and D(first["cap_weight_ratio"]) == D("0.5")
    budget = subject.sleeve_budgets(6)[0]
    with localcontext() as context:
        context.prec = 96
        allocated = sum((weight for sid, _, weight in target.weights if sid.startswith("ID-SPY-")), D(0))
        assert allocated <= budget / 4
        assert D(first["own_etf_weight"]) == budget - allocated


@pytest.mark.parametrize("changes,code", [
    ({"reported_weight": D(-1)}, "negative_reported_weight"),
    ({"reported_weight": D("NaN")}, "decimal"),
    ({"market_cap": D(0)}, "decimal"),
    ({"market_cap": D("Infinity")}, "decimal"),
    ({"score": D("NaN")}, "decimal"),
    ({"economic_id": None}, "unmapped_score"),
    ({"economic_id": ""}, "identity_text"),
    ({"qc_sid": " SID "}, "identity_text"),
])
def test_invalid_numbers_and_identities_refuse(changes, code):
    with pytest.raises(subject.NewruleError, match=code):
        build(replace_row(books(), **changes))


@pytest.mark.parametrize("field,value,code", [
    ("qc_sid", "SID-SPY-1", "duplicate_qc_sid"),
    ("economic_id", "ID-SPY-1", "duplicate_economic_id"),
    ("economic_id", "ETF-SPY", "stock_own_etf_collision"),
    ("economic_id", "ID-QQQ-0", "cross_book_identity_collision"),
    ("qc_sid", "SID-QQQ-0", "cross_book_identity_collision"),
])
def test_identity_collisions_refuse(field, value, code):
    with pytest.raises(subject.NewruleError, match=code):
        build(replace_row(books(), **{field: value}))


@pytest.mark.parametrize("count,arm", [(True, 0), (7, 0), (6, True), (6, 50)])
def test_invalid_cell_refuses(count, arm):
    with pytest.raises(subject.NewruleError):
        build(count=count, arm=arm)


def test_complete_eight_book_census_required_for_every_arm():
    with pytest.raises(subject.NewruleError, match="source_census"):
        build(books()[:6])
    with pytest.raises(subject.NewruleError, match="source_census"):
        build(tuple(reversed(books())))


def test_mutated_target_binding_refuses():
    target = build()
    with pytest.raises(subject.NewruleError, match="target_binding"):
        dataclasses.replace(target, source_snapshot_sha256="b" * 64).record()


def test_source_hash_must_be_explicit_sha256():
    with pytest.raises(subject.NewruleError, match="digest"):
        subject.build_target(books(), universe_count=6, ar_percent=0, source_snapshot_sha256="")


def test_unselected_book_change_changes_binding_even_with_reused_context_hash():
    original = build()
    changed = build(replace_row(books(), book_index=7, market_cap=D(12345)))
    assert original.weights == changed.weights
    assert original.source_snapshot_sha256 == changed.source_snapshot_sha256
    assert original.input_books_sha256 != changed.input_books_sha256
    assert original.target_sha256 != changed.target_sha256
    assert original.record()["source_hash_is_independent_authority"] is False


@pytest.mark.parametrize("changes", [{"market_cap": D(123)}, {"score": D(-2)},
                                    {"economic_name": "different name"}])
def test_shared_security_facts_must_agree_across_sleeves(changes):
    with pytest.raises(subject.NewruleError, match="cross_book_economic_facts_conflict"):
        build(replace_row(books(shared=True), **changes))
