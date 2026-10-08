"""Invented supplied actual dates only; no provider rows or extra outcome look."""
import copy
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import localcontext
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from research.insider_buying import backtest_registered_analysis as analysis
from research.insider_buying import backtest_realized_earnings_interval_diagnostic as module
from test_insider_buying_backtest_realized_earnings_diagnostic import (
    actual_source, assess as assess_exact, enc, evaluate_v2, fixture_v2, sha,
    stream_result_v2, successor_stream_inputs,
)


def semantics():
    return {"schema": module.SEMANTICS_SCHEMA, "trust_scope": "fixture",
        "provider_id": "invented-provider", "product_id": "actual-releases", "dataset_id": "invented-history",
        "source_document_sha256": "1" * 64, "qualification_receipt_sha256": "2" * 64,
        "actual_status_rule": "explicit-source-confirmation-of-published-results-never-date-status-only",
        "report_date_meaning": "exchange-local-civil-date-of-actual-public-release",
        "market_timezone": "America/New_York",
        "before_market_meaning": "actual-public-release-before-that-regular-session-open",
        "after_market_meaning": "actual-public-release-at-or-after-that-regular-session-close",
        "null_meaning": "actual-public-release-time-unknown-within-entire-reported-civil-date"}


def supplemental(result, semantic, *, digest="8" * 64):
    body = result._body()
    parent, manifest = body["registration"], body["manifest"]
    return {"schema": module.REGISTRATION_SCHEMA, "trust_scope": "fixture",
        "registered_look_id": parent["registered_look_id"], "candidate_id": parent["candidate_id"],
        "parent_registration_sha256": body["report"]["artifact_sha256s"]["registration"],
        "manifest_sha256": body["report"]["artifact_sha256s"]["manifest"],
        "event_inventory_sha256": sha(enc(manifest["events"])),
        "parent_exact_utc_diagnostic_implementation_sha256": parent["realized_earnings_implementation_sha256"],
        "diagnostic_implementation_sha256": digest, "source_semantics_sha256": sha(enc(semantic)),
        "registered_at_utc": parent["registered_at_utc"],
        "first_outcome_access_utc": parent["first_outcome_access_utc"],
        "policy": module.frozen_interval_policy(),
        "analysis_plan": module.interval_analysis_plan_descriptor(implementation_sha256=digest)}


def source(result, supplemental_registration, semantic, *, offset=None, category="BeforeMarket", unavailable=False):
    sealed = result._body(); manifest = sealed["manifest"]; sessions = manifest["sessions"]
    rows = []
    for event in manifest["events"]:
        index = next(i for i, row in enumerate(sessions) if row["session"] == event["entry_session"])
        releases = []
        if offset is not None and not unavailable:
            releases = [{"release_id": "release-" + event["signal_id"], "release_type": "ACTUAL_PUBLIC_EARNINGS_RELEASE",
                "lineage": [{"version_id": "actual-v1", "supersedes_version_id": None,
                    "recorded_at_utc": sessions[index + 10]["close_utc"],
                    "actual_report_date": sessions[index + offset]["session"], "timing_category": category,
                    "actual_release_confirmed": True, "status": "ACTIVE",
                    "source_document_sha256": "3" * 64, "source_record_sha256": "4" * 64}]}]
        rows.append({**{key: event[key] for key in ("signal_id", "issuer_id", "security_id", "source_event_sha256")},
            "coverage_start_date": sessions[index - 6]["session"], "coverage_end_date": sessions[index + 5]["session"],
            "coverage_disposition": "UNAVAILABLE" if unavailable else "COMPLETE",
            "unavailable_reason": "actual-history-unavailable" if unavailable else None, "releases": releases})
    return {"schema": module.SOURCE_SCHEMA, "trust_scope": "fixture",
        "interval_registration_sha256": sha(enc(supplemental_registration)),
        "parent_registration_sha256": supplemental_registration["parent_registration_sha256"],
        "manifest_sha256": supplemental_registration["manifest_sha256"],
        "event_inventory_sha256": supplemental_registration["event_inventory_sha256"],
        "calendar_sha256": sealed["registration"]["calendar_sha256"],
        "source_semantics_sha256": sha(enc(semantic)), "source_receipt_sha256": "5" * 64,
        "rights_sha256": "6" * 64, "source_as_of_utc": sessions[-1]["close_utc"], "events": rows}


def inputs(result=None, *, offset=None, category="BeforeMarket", unavailable=False, digest="8" * 64):
    result = result or evaluate_v2()
    semantic = semantics(); registration = supplemental(result, semantic, digest=digest)
    actual = source(result, registration, semantic, offset=offset, category=category, unavailable=unavailable)
    return result, registration, semantic, actual


def assess(result, registration, semantic, actual, *, digest="8" * 64, roots_edit=None):
    # External application reanchors each supplied byte artifact independently.
    registration = copy.deepcopy(registration); actual = copy.deepcopy(actual)
    registration["source_semantics_sha256"] = sha(enc(semantic))
    actual.update(interval_registration_sha256=sha(enc(registration)), source_semantics_sha256=sha(enc(semantic)))
    roots = module.EarningsIntervalDiagnosticTrustRoots("fixture", registration["parent_registration_sha256"],
        registration["manifest_sha256"], result.sha256, sha(enc(registration)), sha(enc(semantic)),
        semantic["qualification_receipt_sha256"], sha(enc(actual)), actual["source_receipt_sha256"], actual["rights_sha256"], digest)
    if roots_edit: roots = replace(roots, **roots_edit)
    return module.assess_realized_earnings_interval_sensitivity(primary_result=result,
        interval_registration_raw=enc(registration), source_semantics_raw=enc(semantic), actual_earnings_raw=enc(actual),
        trust_roots=roots, expected_implementation_sha256=digest)


@pytest.mark.parametrize("offset,category,retained2,retained5", [
    (0, "BeforeMarket", 0, 0), (2, "BeforeMarket", 0, 0), (2, "AfterMarket", 1, 0),
    (-3, "AfterMarket", 0, 0), (5, "BeforeMarket", 1, 0), (5, "AfterMarket", 1, 1),
    (-6, "BeforeMarket", 1, 1), (-6, "AfterMarket", 1, 0),
    (0, None, 0, 0), (3, None, 1, 0),
])
def test_qualified_actual_categories_preserve_strict_close_and_both_windows(offset, category, retained2, retained5):
    result = assess(*inputs(offset=offset, category=category))
    assert result["disposition"] == "FIXTURE_COMPLETE"
    assert result["earnings_exclusion_diagnostics"]["2"]["retained"] == retained2
    assert result["earnings_exclusion_diagnostics"]["5"]["retained"] == retained5


@pytest.mark.parametrize("offset", [-6, -3, 2, 5])
def test_null_timing_boundary_ambiguity_is_whole_unavailable_not_guessed_or_clamped(offset):
    report = assess(*inputs(offset=offset, category=None))
    assert report["disposition"] == "UNAVAILABLE" and report["earnings_exclusion_diagnostics"] is None
    assert report["unavailable_events"] == [{"signal_id": "event-1", "reason": "actual-release-reaction-window-ambiguous"}]


def test_supplemental_policy_and_identity_do_not_relabel_parent_exact_utc_or_activate_anything():
    values = inputs(offset=3, category=None)
    before = values[0].to_payload()
    report = assess(*values)
    assert values[0].to_payload() == before
    assert report["parent_exact_utc_diagnostic_implementation_sha256"] == "9" * 64
    assert report["effective_diagnostic_implementation_sha256"] == "8" * 64
    assert report["parent_exact_utc_diagnostic_satisfied"] is False
    assert report["primary_selection_or_orders_changed"] is report["release_instant_invented"] is False
    for key in ("required_diagnostic_verified_for_production", "ib5_pass", "backtesting_ready", "look_authority",
                "source_semantics_authenticated_here", "rights_authenticated_here", "source_authentication_performed"):
        assert report[key] is False
    assert report["alpha_spent"] == [0, 1] and report["registered_looks_consumed"] == report["qc_jobs"] == 0
    assert "matched_net10_20s" not in enc(report).decode()
    # The new source/registration do NOT enter or loosen the exact-UTC API.
    old_shape_attempt = {**values[3], "registration_sha256": values[1]["parent_registration_sha256"]}
    with pytest.raises(ValueError): assess_exact(values[0], old_shape_attempt)
    old = assess_exact(values[0], actual_source(values[0], offset=3))
    assert old["earnings_exclusion_diagnostics"] == report["earnings_exclusion_diagnostics"]


@pytest.mark.parametrize("field,value", [
    ("report_date_meaning", "fiscal-period-end"), ("actual_status_rule", "confirmed-forecast-date"),
    ("market_timezone", "UTC"), ("before_market_meaning", "scheduled-before-market"),
    ("after_market_meaning", "after-1600-regardless-of-early-close"), ("null_meaning", "assume-before-market"),
    ("provider_id", []), ("schema", "upcoming-calendar"),
])
def test_missing_or_changed_provider_semantics_cannot_be_reanchored_into_qualification(field, value):
    values = inputs(offset=0); values[2][field] = value
    with pytest.raises(ValueError): assess(*values)


@pytest.mark.parametrize("field", ["before_market_meaning", "report_date_meaning", "actual_status_rule", "source_document_sha256"])
def test_missing_semantics_refuses(field):
    values = inputs(); values[2].pop(field)
    with pytest.raises(ValueError): assess(*values)


@pytest.mark.parametrize("edit", [
    lambda r: r.update(schema="insider-stock-analysis-registration-v2"),
    lambda r: r.update(registered_look_id="different-look"), lambda r: r.update(candidate_id="different-candidate"),
    lambda r: r.update(parent_registration_sha256="f" * 64), lambda r: r.update(manifest_sha256="f" * 64),
    lambda r: r.update(event_inventory_sha256="f" * 64),
    lambda r: r.update(parent_exact_utc_diagnostic_implementation_sha256="8" * 64),
    lambda r: r.update(diagnostic_implementation_sha256="7" * 64),
    lambda r: r.update(registered_at_utc=r["first_outcome_access_utc"]),
    lambda r: r.update(first_outcome_access_utc="2024-01-01T00:00:00Z"),
    lambda r: r["policy"].update(unknown_timing="assume-before-market"),
    lambda r: r["policy"].update(windows_sessions=[2]),
    lambda r: r["analysis_plan"].update(definition="some-equivalent-method"),
])
def test_exact_supplemental_preregistration_cannot_silently_replace_or_backdate_parent(edit):
    values = inputs(); edit(values[1])
    with pytest.raises(ValueError): assess(*values)


@pytest.mark.parametrize("edit", [
    lambda b: b["events"].clear(), lambda b: b["events"].append(copy.deepcopy(b["events"][0])),
    lambda b: b["events"][0].update(signal_id="foreign"), lambda b: b["events"][0].update(issuer_id="foreign"),
    lambda b: b["events"][0].update(coverage_start_date=b["events"][0]["coverage_end_date"]),
    lambda b: b["events"][0].update(coverage_end_date=b["events"][0]["coverage_start_date"]),
    lambda b: b["events"][0].update(coverage_disposition=True),
    lambda b: b["events"][0].update(unavailable_reason="missing"),
    lambda b: b.update(calendar_sha256="f" * 64), lambda b: b.update(event_inventory_sha256="f" * 64),
    lambda b: b.update(source_as_of_utc="2020-01-01T00:00:00Z"),
    lambda b: b["events"][0]["releases"][0].update(release_type="CONFIRMED_PROJECTED_DATE"),
    lambda b: b["events"][0]["releases"][0]["lineage"].clear(),
    lambda b: b["events"][0]["releases"][0]["lineage"][0].update(actual_release_confirmed=1),
    lambda b: b["events"][0]["releases"][0]["lineage"][0].update(timing_category="BMO"),
    lambda b: b["events"][0]["releases"][0]["lineage"][0].update(actual_report_date="not-date"),
    lambda b: b["events"][0]["releases"][0]["lineage"][0].update(source_record_sha256="bad"),
    lambda b: b["events"][0]["releases"][0]["lineage"][0].update(supersedes_version_id="foreign"),
])
def test_reanchored_missing_incomplete_forecast_or_mixed_coverage_refuses(edit):
    values = inputs(offset=2); edit(values[3])
    with pytest.raises(ValueError): assess(*values)


@pytest.mark.parametrize("field", [name for name in module.EarningsIntervalDiagnosticTrustRoots.__dataclass_fields__ if name.endswith("sha256")])
def test_every_external_anchor_is_independently_checked(field):
    with pytest.raises(ValueError): assess(*inputs(offset=0), roots_edit={field: "f" * 64})


def test_unavailable_coverage_is_not_empty_complete_and_partial_population_never_accepted():
    values = inputs(unavailable=True)
    assert assess(*values)["disposition"] == "UNAVAILABLE"
    assert assess(*inputs())["earnings_exclusion_diagnostics"]["5"]["retained"] == 1
    values[3]["events"][0]["releases"] = inputs(offset=0)[3]["events"][0]["releases"]
    with pytest.raises(ValueError): assess(*values)
    raws, record = successor_stream_inputs(); primary = stream_result_v2(raws, record)
    values = inputs(primary)
    values[3]["events"][1].update(coverage_disposition="UNAVAILABLE", unavailable_reason="missing-history")
    report = assess(*values)
    assert report["event_count"] == 3 and report["earnings_exclusion_diagnostics"] is None


def test_corrections_and_retractions_are_replayed_in_exact_order():
    values = inputs(offset=0)
    lineage = values[3]["events"][0]["releases"][0]["lineage"]
    sessions = values[0]._body()["manifest"]["sessions"]
    entry = next(i for i, s in enumerate(sessions) if s["session"] == values[0]._body()["manifest"]["events"][0]["entry_session"])
    lineage.append({**lineage[0], "version_id": "actual-v2", "supersedes_version_id": "actual-v1",
        "recorded_at_utc": sessions[entry + 11]["close_utc"], "actual_report_date": sessions[entry + 3]["session"], "timing_category": None})
    assert assess(*values)["earnings_exclusion_diagnostics"]["2"]["retained"] == 1
    lineage[-1]["status"] = "RETRACTED"
    assert assess(*values)["active_release_count"] == 0
    lineage[-1]["supersedes_version_id"] = None
    with pytest.raises(ValueError): assess(*values)


def test_weekend_null_uses_all_civil_instants_and_nonregular_category_does_not_guess():
    values = inputs(offset=0, category=None)
    sessions = values[0]._body()["manifest"]["sessions"]
    entry = next(i for i, s in enumerate(sessions) if s["session"] == values[0]._body()["manifest"]["events"][0]["entry_session"])
    friday = next(i for i in range(entry-5, entry+4) if analysis._date(sessions[i]["session"]).weekday() == 4)
    saturday = analysis._date(sessions[friday]["session"]) + timedelta(days=1)
    revision = values[3]["events"][0]["releases"][0]["lineage"][0]
    revision["actual_report_date"] = saturday.isoformat()
    report = assess(*values)
    assert report["earnings_exclusion_diagnostics"]["2"]["retained"] == int(abs(friday+1-entry) > 2)
    revision["timing_category"] = "AfterMarket"
    with pytest.raises(ValueError, match="nonregular"): assess(*values)


def test_bound_calendar_holiday_and_early_close_not_fixed_1600():
    # Direct clock tests use invented independently supplied calendar rows;
    # arbitrary noon is never manufactured as an actual release instant.
    zone = ZoneInfo("America/New_York")
    dates = ["2023-11-22", "2023-11-24", "2023-11-27"]
    closes = [analysis._utc(s) for s in ["2023-11-22T21:00:00Z", "2023-11-24T18:00:00Z", "2023-11-27T21:00:00Z"]]
    assert module._possible_reactions(analysis._date("2023-11-23"), None, dates, closes, zone) == (1,)
    assert module._possible_reactions(analysis._date("2023-11-24"), "BeforeMarket", dates, closes, zone) == (1,)
    assert module._possible_reactions(analysis._date("2023-11-24"), "AfterMarket", dates, closes, zone) == (2,)
    assert module._possible_reactions(analysis._date("2023-11-24"), None, dates, closes, zone) == (1, 2)


def test_actual_after_market_cannot_be_confirmed_before_bound_regular_close():
    values = inputs(offset=2, category="AfterMarket")
    revision = values[3]["events"][0]["releases"][0]["lineage"][0]
    closing = next(analysis._utc(row["close_utc"]) for row in values[0]._body()["manifest"]["sessions"]
                   if row["session"] == revision["actual_report_date"])
    revision["recorded_at_utc"] = (closing - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    with pytest.raises(ValueError, match="before.*close"):
        assess(*values)


@pytest.mark.parametrize("day,hours", [("2023-03-12", 23), ("2023-11-05", 25)])
def test_full_local_civil_date_preserves_dst_length(day, hours):
    lower, upper = module._civil_bounds(analysis._date(day), ZoneInfo("America/New_York"))
    assert (upper.astimezone(ZoneInfo("UTC")) - lower.astimezone(ZoneInfo("UTC"))).total_seconds() == hours * 3600


def test_production_refuses_before_any_primary_or_supplied_bytes_are_touched():
    roots = module.EarningsIntervalDiagnosticTrustRoots("production", *("a" * 64 for _ in range(10)))
    with pytest.raises(module.EarningsIntervalDiagnosticError, match="zero-look"):
        module.assess_realized_earnings_interval_sensitivity(primary_result=None,
            interval_registration_raw=object(), source_semantics_raw=object(), actual_earnings_raw=object(),
            trust_roots=roots, expected_implementation_sha256=object())


def test_sealed_primary_result_cannot_be_reconstructed_or_changed():
    values = inputs()
    with pytest.raises(ValueError): assess(replace(values[0]), *values[1:])
    sealed = values[0]._body(); sealed["event_results"][0]["matched_net10_20s"] = "100"
    object.__setattr__(values[0], "_raw", enc(sealed))
    with pytest.raises(ValueError): assess(*values)


def test_effective_source_identity_is_externally_captured_and_precise_not_self_authenticated():
    digest = sha((Path(__file__).resolve().parents[1] / "research/insider_buying/backtest_realized_earnings_interval_diagnostic.py").read_bytes())
    values = inputs(offset=3, category=None, digest=digest)
    precise = assess(*values, digest=digest)
    with localcontext() as arithmetic:
        arithmetic.prec = 3
        assert assess(*values, digest=digest) == precise
    assert precise["effective_diagnostic_implementation_sha256"] == digest
    assert precise["implementation_execution_identity_verified_here"] is False


def test_conservative_per_release_ambiguity_is_not_hidden_by_another_excluding_release():
    values = inputs(offset=0)
    release = copy.deepcopy(values[3]["events"][0]["releases"][0])
    other = inputs(offset=2, category=None)[3]["events"][0]["releases"][0]
    other["release_id"] += "-ambiguous"
    values[3]["events"][0]["releases"] = [release, other]
    assert assess(*values)["disposition"] == "UNAVAILABLE"
