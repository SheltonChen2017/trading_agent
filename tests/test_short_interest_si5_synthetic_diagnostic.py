"""R(20) rehearsal is gross, common-cohort, exact and never empirical."""
from copy import deepcopy
from dataclasses import replace
from decimal import localcontext
from fractions import Fraction

import pytest

from data.hashing import hash_payload
import research.short_interest_etf.si5_synthetic_diagnostic as diagnostic
from research.short_interest_etf.si5_offline_protocol import SI5_OFFLINE_PROTOCOL


def _fraction(payload):
    return Fraction(payload["numerator"], payload["denominator"])


def _release():
    return diagnostic._fixture()[0]


def test_public_rehearsal_runs_all_four_without_winner_looks_or_authority():
    result = diagnostic.run_si5_synthetic_diagnostic_scenario()
    payload = result.to_payload()
    assert result.sha256 == hash_payload({key: value for key, value in payload.items() if key != "result_sha256"})
    assert payload["diagnostic_cost_bps_per_side"] == 0
    assert payload["synthetic_only"] is True
    for flag in ("source_ranking_linked", "source_admitted", "actual_pit_coverage_verified",
                 "outcome_access_authorized", "qc_backtest_authorized", "trading_authority", "real_backtesting_ready"):
        assert payload[flag] is False
    assert payload["authorized_real_outcome_looks"] == payload["consumed_real_outcome_looks"] == 0
    output = payload["diagnostic"]
    assert output["selected_lookback"] is None
    assert output["effective_independent_sample_count"] is None
    assert output["power_verified"] is output["market_edge_evidence"] is False
    assert output["aggregate_comparable"] is True
    assert [row["lookback_sessions"] for row in output["candidate_aggregates"]] == [20, 60, 120, 252]
    assert all(_fraction(row["mean_release_contrast"]) == Fraction(1, 5) for row in output["candidate_aggregates"])
    assert SI5_OFFLINE_PROTOCOL.terminal_value_rule is SI5_OFFLINE_PROTOCOL.order_cashflow_rule is None


def test_calendar_horizon_is_twentieth_later_open_across_holiday_and_dst():
    release = _release()
    price = release.prices[0].to_payload()
    assert price["entry_at"] == "2024-02-13T14:30:00Z"
    assert price["exit_session"] == "2024-03-13"
    assert price["exit_at"] == "2024-03-13T13:30:00Z"
    with pytest.raises(diagnostic.SI5SyntheticDiagnosticError, match="20th later"):
        replace(release.prices[0], exit_session="2024-03-12").to_payload()


def test_split_adjusted_price_return_excludes_dividends_and_order_costs():
    release = _release()
    first = replace(release.prices[0], exit_open_usd="55", cumulative_split_ratio=Fraction(2))
    output = diagnostic._evaluate_release(replace(release, prices=(first, *release.prices[1:])))
    assert output["comparable"] is True
    assert _fraction(output["windows"][0]["low_mean_R20"]) == Fraction(1, 10)
    assert _fraction(output["windows"][0]["low_minus_high_R20"]) == Fraction(1, 5)


def test_equal_weight_releases_not_pooled_ticker_rows():
    one, two = diagnostic._fixture()
    # Later release has two stocks in each tail vs one: make its low tail +30%.
    changed = tuple(replace(row, exit_open_usd="130") if row.security_id in two.windows[0].low_pressure_ids else row for row in two.prices)
    output = diagnostic._evaluate_synthetic_kernel((one, replace(two, prices=changed)))
    # Release contrasts .20 and .40 -> .30, NOT ticker pooled .3333...
    assert all(_fraction(row["mean_release_contrast"]) == Fraction(3, 10) for row in output["candidate_aggregates"])


@pytest.mark.parametrize("missing_kind", ["omitted", "entry", "exit", "terminal"])
def test_missing_common_outcome_never_drops_even_a_nontail_stock(missing_kind):
    release = _release()
    target = release.prices[8]
    rows = []
    for row in release.prices:
        if row is not target:
            rows.append(row)
        elif missing_kind == "entry":
            rows.append(replace(row, entry_open_usd=None))
        elif missing_kind == "exit":
            rows.append(replace(row, exit_open_usd=None))
        elif missing_kind == "terminal":
            rows.append(replace(row, terminal_before_horizon=True))
    changed = replace(release, prices=tuple(rows))
    output = diagnostic._evaluate_synthetic_kernel((changed, diagnostic._fixture()[1]))
    first = output["releases"][0]
    assert target.security_id in first["common_security_ids"]
    assert first["comparable"] is False
    assert first["refusals"][0]["security_id"] == target.security_id
    assert "incomplete_common_outcomes" in first["no_comparison_reasons"]
    assert all(row["low_minus_high_R20"] is None for row in first["windows"])
    assert output["aggregate_comparable"] is False
    assert all(row["mean_release_contrast"] is None for row in output["candidate_aggregates"])
    assert all(row["comparable_release_count"] == 1 and row["expected_release_count"] == 2 for row in output["candidate_aggregates"])


def test_common_subset_preserves_original_tails_without_reranking():
    release = _release()
    first = release.windows[0]
    removed = first.low_pressure_ids[0]
    reduced = replace(first, full_security_ids=first.full_security_ids[1:], low_pressure_ids=())
    output = diagnostic._evaluate_release(replace(release, windows=(reduced, *release.windows[1:])))
    assert removed not in output["common_security_ids"]
    assert output["comparable"] is False
    assert "missing_common_low_pressure_tail" in output["no_comparison_reasons"]
    assert all(row["low_pressure_ids"] == [] for row in output["windows"])
    assert all(row["low_minus_high_R20"] is None for row in output["windows"])


def test_underfilled_common_population_is_reported_not_replenished():
    release = _release()
    first = release.windows[0]
    reduced = replace(first, full_security_ids=first.full_security_ids[:9], high_pressure_ids=())
    output = diagnostic._evaluate_release(replace(release, windows=(reduced, *release.windows[1:])))
    assert len(output["common_security_ids"]) == 9
    assert "underfilled_common_intersection" in output["no_comparison_reasons"]
    assert "underfilled_full_cohort" in output["no_comparison_reasons"]


@pytest.mark.parametrize("change", ["window_duplicate", "window_missing", "price_duplicate", "release_duplicate", "date_duplicate", "tail_overlap", "tail_outside", "unknown_price"])
def test_structural_errors_refuse_instead_of_fabricating_output(change):
    one, two = diagnostic._fixture()
    first = one.windows[0]
    if change == "window_duplicate":
        one = replace(one, windows=(first, first, *one.windows[2:]))
    elif change == "window_missing":
        one = replace(one, windows=one.windows[:3])
    elif change == "price_duplicate":
        one = replace(one, prices=(*one.prices, one.prices[0]))
    elif change == "release_duplicate":
        two = replace(two, release_id=one.release_id)
    elif change == "date_duplicate":
        two = replace(one, release_id=two.release_id)
    elif change == "tail_overlap":
        one = replace(one, windows=(replace(first, low_pressure_ids=first.high_pressure_ids), *one.windows[1:]))
    elif change == "tail_outside":
        one = replace(one, windows=(replace(first, low_pressure_ids=("NOT-IN-COHORT",)), *one.windows[1:]))
    else:
        one = replace(one, prices=(*one.prices, replace(one.prices[0], security_id="NOT-IN-COHORT")))
    with pytest.raises(diagnostic.SI5SyntheticDiagnosticError, match="REFUSED"):
        diagnostic._evaluate_synthetic_kernel((one, two))


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "1e2", "100.0", 100, 100.0, True])
def test_invalid_prices_refuse_before_arithmetic(value):
    release = _release()
    first = replace(release.prices[0], entry_open_usd=value)
    with pytest.raises(diagnostic.SI5SyntheticDiagnosticError, match="decimal"):
        diagnostic._evaluate_release(replace(release, prices=(first, *release.prices[1:])))


@pytest.mark.parametrize("value", [0, -1, 1.0, True, Fraction(0), Fraction(-1)])
def test_split_ratio_is_exact_positive_rational(value):
    row = replace(_release().prices[0], cumulative_split_ratio=value)
    with pytest.raises(diagnostic.SI5SyntheticDiagnosticError, match="split ratio"):
        row.to_payload()


def test_public_runner_refuses_external_rows_and_caller_authority_flags():
    with pytest.raises(diagnostic.SI5SyntheticDiagnosticError, match="fixed built-in"):
        diagnostic.run_si5_synthetic_diagnostic_scenario({"synthetic_only": True, "prices": []})
    with pytest.raises(TypeError):
        diagnostic.run_si5_synthetic_diagnostic_scenario(source_admitted=True)


def test_digest_bound_fixture_and_tamper_resistant_detached_receipt(monkeypatch):
    result = diagnostic.run_si5_synthetic_diagnostic_scenario()
    payload = result.to_payload()
    original = deepcopy(payload)
    payload["diagnostic"]["releases"].clear()
    assert result.to_payload() == original
    result._payload["real_backtesting_ready"] = True
    with pytest.raises(diagnostic.SI5SyntheticDiagnosticError, match="provenance changed"):
        result.to_payload()
    monkeypatch.setattr(diagnostic, "SI5_SYNTHETIC_DIAGNOSTIC_FIXTURE_SHA256", "0" * 64)
    with pytest.raises(diagnostic.SI5SyntheticDiagnosticError, match="fixture changed"):
        diagnostic.run_si5_synthetic_diagnostic_scenario()


def test_decimal_context_does_not_change_exact_rehearsal():
    expected = diagnostic.run_si5_synthetic_diagnostic_scenario().to_payload()
    with localcontext() as context:
        context.prec = 2
        assert diagnostic.run_si5_synthetic_diagnostic_scenario().to_payload() == expected


def test_equal_but_noncanonical_retained_payload_is_not_silently_repaired():
    result = diagnostic.run_si5_synthetic_diagnostic_scenario()
    result._payload["source_admitted"] = 0
    with pytest.raises(diagnostic.SI5SyntheticDiagnosticError, match="provenance changed"):
        result.to_payload()
