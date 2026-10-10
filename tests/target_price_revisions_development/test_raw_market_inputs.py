"""Pure invented market rows; no provider or private artifact access."""
from copy import deepcopy
from datetime import date, datetime, time, timezone
from decimal import Inexact, ROUND_UP, localcontext
import hashlib
import importlib
import json
from zoneinfo import ZoneInfo

import pytest


def module():
    return importlib.import_module("research.target_price_revisions_development.raw_market_inputs")


def inputs():
    days = ("2024-12-27", "2024-12-30", "2024-12-31", "2025-01-02", "2025-01-06",
            "2025-01-13", "2025-01-21", "2025-03-31")
    eastern = ZoneInfo("America/New_York")
    axis = [{"session_date": day,
        "open_utc": datetime.combine(date.fromisoformat(day), time(9, 30), eastern).astimezone(timezone.utc).isoformat(),
        "close_utc": datetime.combine(date.fromisoformat(day), time(16), eastern).astimezone(timezone.utc).isoformat()} for day in days]
    structure = {"schema": "tpr-raw-structure-v1", "capture_utc": "2026-10-07T10:00:00Z",
        "calendar": axis, "ratings": [{"benzinga_id": "fixture-event", "benzinga_firm_id": 12,
            "ticker": "ZZTEST", "date": "2024-12-27", "last_updated": "2024-12-27T15:00:00Z",
            "currency": "USD", "price_target_action": "raises", "price_target": "110", "previous_price_target": "100"}],
        "identities": [{"ticker": "ZZTEST", "security_id": "SHARADAR:1000", "permaticker": 1000,
            "figi": None, "category": "Domestic Common Stock", "exchange": "NYSE", "isdelisted": False}],
        "actions": [], "action_inventory_complete": True}
    stocks = [{"ticker": "ZZTEST", "date": day, "open": "3", "close": "2", "closeunadj": "5", "volume": "10001"}
              for day in days if day >= "2024-12-31"]
    return structure, stocks, []


def attach(structure, actions, kind="dividend", day="2025-01-13", value="0.4", contra=None):
    actions.append({"ticker": "ZZTEST", "date": day, "action": kind, "value": value, "contraticker": contra})
    structure["actions"].append({key: actions[-1][key] for key in ("ticker", "date", "action")})


def bar(report, day):
    return next(s for s in report["outcomes"]["sessions"] if s["session_id"] == day)["bars"][0]


def test_exact_imputation_reciprocal_volume_and_assumed_clocks_not_provider_proof():
    structure, stocks, actions = inputs()
    report = module().convert(structure, stocks, actions)
    assert report["schema"] == "tpr-raw-market-inputs-v1"
    canonical_private_bytes = (json.dumps(structure, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")
    assert report["structure_sha256"] == hashlib.sha256(canonical_private_bytes).hexdigest()
    assert report["structure_sha256"] != hashlib.sha256(canonical_private_bytes[:-1]).hexdigest()
    assert report["outcomes"]["sessions"][0]["bars"] == []
    assert report["outcomes"]["sessions"][1]["bars"] == []
    first = bar(report, "2025-01-02")
    assert first["open"] == "7.5" and first["close"] == "5"
    assert first["lagged_volume"] == 4000  # floor(10001 * 2 / 5), NOT * 5 / 2
    assert first["volume_available_at_utc"] == structure["calendar"][2]["close_utc"]
    assert first["open_available_at_utc"] == structure["calendar"][3]["open_utc"]
    evidence = report["evidence"]
    assert evidence["clock_model"] == "assumed_historical_daily_bar_clock"
    assert evidence["current_vintage_imputation"] is True
    assert evidence["point_in_time_data"] is False
    assert evidence["observed_provider_availability"] is False
    assert evidence["canonical_admission"] is False and evidence["real_backtest_ready"] is False
    assert evidence["action_inventory_reconciled"] is True
    assert "ZZTEST" not in json.dumps(evidence) and "SHARADAR:1000" not in json.dumps(evidence)


def test_fractional_raw_close_is_exact_canonical_decimal_and_engine_compatible():
    structure, stocks, actions = inputs()
    for row in stocks:
        row.update(open="0.5", close="0.5", closeunadj="00.5000", volume="100000000")
    report = module().convert(structure, stocks, actions)
    assert bar(report, "2025-01-02")["close"] == "0.5"
    from research.target_price_revisions_development.raw_candidate import run_raw_candidate
    result = run_raw_candidate(structure, report["outcomes"])
    assert result["backtest"]["fills"] and result["backtest"]["complete"] is True


def test_native_slash_symbol_is_preserved_exactly_not_aliased_to_dot():
    structure, stocks, actions = inputs()
    for row in structure["ratings"] + structure["identities"] + stocks:
        row["ticker"] = "ZZTEST/A"
    report = module().convert(structure, stocks, actions)
    assert bar(report, "2025-01-02")["security_id"] == "SHARADAR:1000"
    stocks[0]["ticker"] = "ZZTEST.A"
    with pytest.raises(ValueError, match="outside selected"):
        module().convert(structure, stocks, actions)


@pytest.mark.parametrize("opening,expected", [("1.000000005", "1"), ("1.000000015", "1.00000002"), ("1", "0.33333333")])
def test_eight_decimal_round_half_even_is_exact_and_context_independent(opening, expected):
    structure, stocks, actions = inputs()
    stocks[0].update(open=opening, close="3" if opening == "1" else "1", closeunadj="1")
    normal = module().convert(structure, stocks, actions)
    assert bar(normal, "2024-12-31")["open"] == expected
    with localcontext() as context:
        context.prec = 3; context.rounding = ROUND_UP; context.traps[Inexact] = True
        assert module().convert(structure, stocks, actions) == normal


@pytest.mark.parametrize("field,value", [("open", "0"), ("close", "0"), ("closeunadj", "0"),
    ("open", "-1"), ("open", "NaN"), ("close", "Infinity"), ("volume", "-1"),
    ("volume", 100), ("open", 1.5), ("open", True), ("open", "1e3"), ("volume", None),
    ("close", "1" * 97), ("open", "0.00000000000000001"),
    ("closeunadj", "1.000000000000000000000000001"), ("volume", "1000000000000")])
def test_malformed_or_out_of_engine_bound_numerics_refuse_sanitized(field, value):
    structure, stocks, actions = inputs()
    stocks[0][field] = value
    with pytest.raises(ValueError, match="market numeric"):
        module().convert(structure, stocks, actions)


def test_missing_bar_is_explicit_and_lagged_volume_is_never_carried_forward():
    structure, stocks, actions = inputs()
    stocks = [row for row in stocks if row["date"] != "2025-01-02"]
    report = module().convert(structure, stocks, actions)
    missing = bar(report, "2025-01-02")
    assert missing["open"] is missing["close"] is None and missing["tradable"] is False
    following = bar(report, "2025-01-06")
    assert following["lagged_volume"] == 0 and following["volume_available_at_utc"] is None
    assert report["evidence"]["missing_bar_count"] == 1


@pytest.mark.parametrize("missing_day,affected_session", [("2024-12-31", "2025-01-02"), ("2025-01-06", "2025-01-13")])
def test_accounted_missing_prior_quote_is_incomplete_not_validation_abort(missing_day, affected_session):
    structure, stocks, actions = inputs()
    for row in stocks:
        row["volume"] = "100000000"
    stocks = [row for row in stocks if row["date"] != missing_day]
    prepared = module().convert(structure, stocks, actions)
    assert bar(prepared, missing_day)["close"] is None
    assert bar(prepared, missing_day)["close_available_at_utc"] is None
    from research.target_price_revisions_development.raw_candidate import run_accounted_raw_candidate
    report = run_accounted_raw_candidate(structure, prepared)["backtest"]
    assert report["complete"] is False
    assert any(item["session_id"] == affected_session and item["reason"] == "decision_mark_missing"
               for item in report["exclusions"])
    assert not any(fill["session_id"] == affected_session for fill in report["fills"])


def test_duplicates_are_counted_not_doubled_and_conflicting_key_refuses():
    structure, stocks, actions = inputs()
    attach(structure, actions)
    report = module().convert(structure, stocks + [dict(stocks[0])], actions + [dict(actions[0])])
    assert report["evidence"]["duplicate_stock_rows"] == report["evidence"]["duplicate_action_rows"] == 1
    assert len(report["corporate_actions"]) == 1
    with pytest.raises(ValueError, match="conflicting market row"):
        module().convert(structure, stocks + [dict(stocks[0], open="4")], actions)
    with pytest.raises(ValueError, match="conflicting action row"):
        module().convert(structure, stocks, actions + [dict(actions[0], value="0.5")])
    with pytest.raises(ValueError, match="conflicting action row"):
        module().convert(structure, stocks, actions + [dict(actions[0], contraticker="")])


def test_cash_dividend_raw_entitlement_uses_exact_exdate_factor_not_spendable_cash():
    structure, stocks, actions = inputs()
    attach(structure, actions)
    report = module().convert(structure, stocks, actions)
    action = report["corporate_actions"][0]
    assert action["kind"] == "cash_dividend" and action["value"] == "1"
    assert action["session_id"] == "2025-01-13" and action["security_id"] == "SHARADAR:1000"
    native = json.dumps(actions[0], sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    assert action["action_id"] == hashlib.sha256(native).hexdigest()
    assert report["evidence"]["dividend_model"] == "ex-date-receivable-nonspendable-no-payment-date"
    assert len(module().convert(structure, list(reversed(stocks)), actions)["corporate_actions"]) == 1


@pytest.mark.parametrize("kind", ["split", "stockdividend", "spinoff", "acquisitioncash", "delisted", "exchangefrom", "exchangeto", "namechange", "mystery"])
def test_unproven_or_unimplemented_economics_remain_unresolved(kind):
    structure, stocks, actions = inputs()
    attach(structure, actions, kind=kind, value="2")
    report = module().convert(structure, stocks, actions)
    assert report["corporate_actions"][0]["kind"] == "unresolved"
    assert report["corporate_actions"][0]["value"] is None
    assert report["evidence"]["unresolved_action_count"] == 1


def test_holiday_action_uses_next_session_but_no_wrong_date_dividend_factor():
    structure, stocks, actions = inputs()
    attach(structure, actions, day="2025-01-20")
    action = module().convert(structure, stocks, actions)["corporate_actions"][0]
    assert action["session_id"] == "2025-01-21"
    assert action["kind"] == "unresolved" and action["value"] is None


@pytest.mark.parametrize("kind", ["sicchangefrom", "sicchangeto"])
def test_only_reviewed_sic_metadata_omitted_from_accounting(kind):
    structure, stocks, actions = inputs()
    attach(structure, actions, kind=kind, value="1234")
    report = module().convert(structure, stocks, actions)
    assert report["corporate_actions"] == ()
    assert report["evidence"]["metadata_only_action_count"] == 1


def test_unresolved_dividend_with_missing_native_value_or_factor_or_counterparty():
    for problem in ("missing_value", "missing_factor", "counterparty"):
        structure, stocks, actions = inputs()
        attach(structure, actions)
        if problem == "missing_value": actions[0]["value"] = None
        elif problem == "missing_factor": stocks = [r for r in stocks if r["date"] != "2025-01-13"]
        else: actions[0]["contraticker"] = "ZZOTHER"
        assert module().convert(structure, stocks, actions)["corporate_actions"][0]["kind"] == "unresolved"


def test_detailed_actions_must_match_frozen_structure_without_omission_or_extra():
    structure, stocks, actions = inputs()
    attach(structure, actions)
    with pytest.raises(ValueError, match="action inventory mismatch"):
        module().convert(structure, stocks, [])
    structure["actions"] = []
    with pytest.raises(ValueError, match="action inventory mismatch"):
        module().convert(structure, stocks, actions)


@pytest.mark.parametrize("change", ["unselected_ticker", "outside_window", "nonsession", "extra_field", "ambiguous_identity"])
def test_scope_and_identity_are_not_widened(change):
    structure, stocks, actions = inputs()
    if change == "unselected_ticker": stocks[0]["ticker"] = "ZZOTHER"
    elif change == "outside_window": stocks[0]["date"] = "2024-12-30"
    elif change == "nonsession": stocks[0]["date"] = "2025-01-01"
    elif change == "extra_field": stocks[0]["extra"] = "private"
    else: structure["identities"].append(dict(structure["identities"][0], security_id="SHARADAR:2000", permaticker=2000))
    before = deepcopy((structure, stocks, actions))
    with pytest.raises(ValueError): module().convert(structure, stocks, actions)
    assert before == (structure, stocks, actions)
