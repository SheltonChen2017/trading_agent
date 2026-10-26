"""Pure, outcome-inert metadata plan for a SEPARATE exploratory 2021–2025 pilot.

This does not edit, replace or complete the frozen 82-quarter study. Its dates
overlap that study's confirmation period: future pilot outcome use therefore
cannot be represented as leaving canonical confirmation untouched. No look,
alpha, source authentication, rights, QC or backtesting authority is created.
Only caller-supplied, externally hash-bound calendar/context metadata is read.
There is no business-file loader, credential, provider, numerical-outcome or QC
surface. Standard-library ZoneInfo uses the local timezone runtime dependency
only; it does not authenticate the supplied exchange calendar or its holidays.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import json
import re
import weakref
from zoneinfo import ZoneInfo

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying import backtest_registered_analysis as analysis
from research.insider_buying.contracts import CANONICAL_SPEC


SCHEMA = "insider-exploratory-pilot-2021-2025-v1"
CALENDAR_SCHEMA = SCHEMA + "/supplied-calendar"
ENTRY_SCHEMA = SCHEMA + "/supplied-entry-context"
ENTRY_REPORT_SCHEMA = SCHEMA + "/entry-metadata-assessment"
EPOCH = "IB-2021-2025-EXPLORATORY-PILOT-v1"
FROZEN_PARENT_POLICY_SHA256 = "b9fc167c21734b8c7c981ff53486e009554c4cd4f0f57c3f924dbd8c8e97c056"
ENTRY_FIRST = "2021-01-01"
ENTRY_LAST = "2025-12-31"
CONTEXT_FIRST = "2019-10-01"
CONTEXT_LAST = "2026-06-30"
PHASES = (("development", "2021-01-01", "2023-12-31"),
          ("validation", "2024-01-01", "2024-12-31"),
          ("sealed_pilot_test", "2025-01-01", "2025-12-31"))
MAX_BYTES = 2 * 1024 * 1024
MAX_SESSIONS = 2000
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,100}\Z")
_SEAL = object()
_BUILT = {}


class PilotMetadataError(ValueError):
    """Fixed classifications; no supplied payload or exception interpolation."""


def _need(value, code):
    if not value:raise PilotMetadataError(code)


def _raw(value):return canonical_json(value).encode("utf-8")


def _digest(value):
    _need(type(value) is str and _SHA.fullmatch(value) is not None, "external_sha256_required")
    return value


def _day(value):
    _need(type(value) is str, "canonical_session_date_required")
    try:day = date.fromisoformat(value)
    except ValueError:raise PilotMetadataError("canonical_session_date_required") from None
    _need(day.isoformat() == value, "canonical_session_date_required")
    return day


def _utc(value):
    _need(type(value) is str and _UTC.fullmatch(value) is not None, "canonical_utc_instant_required")
    try:instant = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:raise PilotMetadataError("canonical_utc_instant_required") from None
    return instant


def _pairs(items):
    result = {}
    for key,value in items:
        _need(key not in result, "duplicate_json_key_refused");result[key] = value
    return result


def _nonfinite(_):raise PilotMetadataError("nonfinite_json_refused")
def _input_number(_):raise PilotMetadataError("numeric_json_input_refused")


def _decode(raw, expected):
    _digest(expected)
    _need(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES and hash_bytes(raw) == expected,
        "bounded_external_metadata_bytes_required")
    try:return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_nonfinite,
        parse_int=_input_number,parse_float=_input_number)
    except (UnicodeError, json.JSONDecodeError, RecursionError):raise PilotMetadataError("strict_metadata_json_refused") from None


def _authority():
    return {"calendar_authenticity_verified": False, "source_coverage_verified": False, "historical_identity_verified": False,
        "pit_verified": False, "rights_verified": False, "canonical_study_complete": False, "look_registered": False,
        "outcome_access_authorized": False, "qc_access_authorized": False, "qc_upload_authorized": False,
        "qc_job_authorized": False, "backtesting_ready": False, "trading_authority": False,
        "outcome_values_processed": 0, "research_looks_consumed": 0, "qc_jobs": 0, "backtests": 0}


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class PilotMetadataResult:
    _bytes: bytes = field(repr=False)
    _token: object = field(repr=False)

    def canonical_bytes(self):
        held = _BUILT.get(id(self))
        _need(type(self) is PilotMetadataResult and self._token is _SEAL and held is not None
            and held[0]() is self and type(self._bytes) is bytes and self._bytes == held[1],
            "genuine_unchanged_pilot_metadata_required")
        return self._bytes

    def to_payload(self):return json.loads(self.canonical_bytes())

    @property
    def sha256(self):return hash_bytes(self.canonical_bytes())


def _factory(body):
    raw = _raw(body);_need(len(raw) <= MAX_BYTES, "pilot_metadata_output_bound_refused")
    result = PilotMetadataResult(raw,_SEAL);key = id(result)
    _BUILT[key] = (weakref.ref(result,lambda _,key=key:_BUILT.pop(key,None)),raw)
    return result


def _calendar(body):
    _need(type(body) is dict and set(body) == {"schema","sessions"} and body["schema"] == CALENDAR_SCHEMA,
        "pilot_calendar_schema_refused")
    rows = body["sessions"]
    _need(type(rows) is list and 314 <= len(rows) <= MAX_SESSIONS, "pilot_calendar_count_refused")
    dates, opens, closes = [], [], []
    eastern = ZoneInfo("America/New_York")
    for row in rows:
        _need(type(row) is dict and set(row) == {"session","open_utc","close_utc"}, "pilot_calendar_record_schema_refused")
        day, opened, closed = _day(row["session"]), _utc(row["open_utc"]), _utc(row["close_utc"])
        _need(CONTEXT_FIRST <= row["session"] <= CONTEXT_LAST and day.weekday() < 5,
            "pilot_calendar_scope_or_weekday_refused")
        local_open, local_close = opened.astimezone(eastern), closed.astimezone(eastern)
        _need(local_open.date() == local_close.date() == day and (local_open.hour,local_open.minute,local_open.second) == (9,30,0)
            and (local_close.hour,local_close.minute,local_close.second) in {(16,0,0),(13,0,0)} and opened < closed,
            "pilot_calendar_regular_open_close_refused")
        _need(not dates or row["session"] > dates[-1] and opened > closes[-1], "pilot_calendar_order_or_duplicate_refused")
        dates.append(row["session"]);opens.append(opened);closes.append(closed)
    # Full padded declared scope is required, but completeness is never inferred
    # from weekdays or endpoints: factual exchange-calendar qualification is later.
    _need(dates[0] == CONTEXT_FIRST and dates[-1] == CONTEXT_LAST, "full_padded_calendar_scope_required")
    return rows,dates,opens,closes


def _parent_policy():
    policy = analysis.frozen_analysis_policy_v2()
    _need(hash_payload(policy) == FROZEN_PARENT_POLICY_SHA256
        and policy["split"] == {"development":["2006-01-01","2014-12-31"],
        "validation":["2015-01-01","2020-12-31"],"confirmation":["2021-01-01","2027-08-31"]}
        and policy["primary_horizon_sessions"] == CANONICAL_SPEC.decay_half_life_trading_days == 20
        and policy["descriptive_horizons"] == [5,60] and policy["minimum_prior_regular_listing_sessions"] == 253
        and CANONICAL_SPEC.minimum_purchase_value_usd == 50000 and CANONICAL_SPEC.lookback_trading_days == 30
        and CANONICAL_SPEC.score_formula == "ln(1 + purchase_value_usd / 50000)"
        and CANONICAL_SPEC.allowed_forms == ("4","4/A") and CANONICAL_SPEC.transaction_code == "P"
        and CANONICAL_SPEC.acquired_disposed_code == "A" and CANONICAL_SPEC.ownership_nature == "D"
        and CANONICAL_SPEC.primary_horizons_trading_days == (5,20,60)
        and CANONICAL_SPEC.cost_grid_bps_per_side == (0,5,10,20)
        and CANONICAL_SPEC.outcomes_authorized is False and type(CANONICAL_SPEC.authorized_outcome_looks) is int
        and CANONICAL_SPEC.authorized_outcome_looks == 0
        and policy["stock_alpha"] == policy["etf_alpha_reserve"] == [1,160], "frozen_parent_economics_drifted")
    return policy


def freeze_pilot_2021_2025(*, calendar_raw, expected_calendar_sha256):
    """Freeze one metadata-only pilot plan from supplied, externally pinned bytes."""
    calendar = _decode(calendar_raw,expected_calendar_sha256)
    rows,dates,opens,closes = _calendar(calendar)
    policy = _parent_policy()
    entries = [i for i,day in enumerate(dates) if ENTRY_FIRST <= day <= ENTRY_LAST]
    _need(entries and entries[0] >= 253 and entries[-1]+60 < len(dates), "pilot_warmup_or_outcome_tail_missing")
    first,last = entries[0],entries[-1]
    phases = {label:[i for i in entries if start <= dates[i] <= end] for label,start,end in PHASES}
    _need(all(phases.values()), "pilot_phase_calendar_missing")
    boundaries = {"development":phases["validation"][0],"validation":phases["sealed_pilot_test"][0]}
    entry_rows = []
    for i in entries:
        phase = next(label for label,start,end in PHASES if start <= dates[i] <= end)
        reasons = []
        if phase in boundaries and i+60 >= boundaries[phase]:reasons.append("purged_label_crosses_next_phase")
        if phase != "development" and i < phases[phase][0]+60:reasons.append("embargo_first60_phase_sessions")
        entry_rows.append({"entry_session":dates[i],"phase":phase,"schedule_disposition":"EXCLUDED" if reasons else "INCLUDED",
            "schedule_exclusion_reasons":reasons,"latest_descriptive_exit_session":dates[i+60]})
    counts = {label:{"declared_entry_sessions":len(phases[label]),"included_entry_sessions":sum(
        row["phase"] == label and row["schedule_disposition"] == "INCLUDED" for row in entry_rows),
        "excluded_entry_sessions":sum(row["phase"] == label and row["schedule_disposition"] == "EXCLUDED" for row in entry_rows)}
        for label,_,_ in PHASES}
    return _factory({"schema":SCHEMA,"evidence_epoch":EPOCH,"interpretation":"EXPLORATORY_METADATA_PLAN_ONLY",
        "entry_window":[ENTRY_FIRST,ENTRY_LAST],"padded_calendar_price_request_window":[CONTEXT_FIRST,CONTEXT_LAST],
        "sec_quarter_context_window":["2020-01-01","2026-03-31"],
        "source_quarters":[f"{year}Q{quarter}" for year in range(2020,2027) for quarter in range(1,5)
            if (year,quarter) <= (2026,1)],
        "sec_context_only_quarters":["2020Q1","2020Q2","2020Q3","2020Q4","2026Q1"],
        "source_accounting_policy":{"all_six_forms":["3","3/A","4","4/A","5","5/A"],
            "complete_quarter_census_required":True,"original_parent_and_refusal_inventory_required":True,
            "context_only_filings_not_pilot_events":True,"missing_invalid_or_underfilled_rows_silently_dropped":False},
        "calendar_sha256":expected_calendar_sha256,"calendar_sessions_sha256":hash_payload(rows),"calendar_sessions":rows,
        "context":{"first_entry_session":dates[first],"last_entry_session":dates[last],
            "required_first_preentry_open_session":dates[first-253],"required_last_outcome_open_session":dates[last+60],
            "signal_max_age_sessions":30,"signal_window_inclusive_session_labels":31,"liquidity_prior_sessions":60,
            "minimum_prior_regular_listing_sessions":253,"factor_prior_actual_open_intervals":252,
            "moo_prerequisite_cutoff_minutes_before_open":2,"moo_prerequisite_cutoff_inclusive":True,
            "outcome_tail_sessions":60,"earnings_windows_sessions":[2,5],"earnings_windows_inclusive":True,
            "required_earnings_first_close_utc":rows[first-6]["close_utc"],
            "required_earnings_last_close_utc":rows[last+5]["close_utc"],
            "required_earnings_first_civil_date":dates[first-6],"required_earnings_last_civil_date":dates[last+5],
            "earnings_used_for_primary_selection_or_clock":False},
        "phases":[{"phase":label,"start":start,"end":end} for label,start,end in PHASES],
        "split_policy":{"max_label_horizon_sessions":60,"purge":"exclude-entry-if-plus60-exit-is-at-or-after-next-phase-first-session",
            "embargo":"exclude-first60-regular-entry-sessions-of-validation-and-pilot-test",
            "purged_or_embargoed_sources_retained":True,"future_returns_read_for_split":False},
        "scheduled_entries":entry_rows,"schedule_counts":counts,"frozen_parent_policy":policy,
        "frozen_parent_policy_sha256":hash_payload(policy),
        "original_study":{"source_window":["2006-01-01","2026-06-30"],"quarter_count":82,
            "original_policy_or_artifacts_modified":False,"pilot_replaces_or_completes_original_study":False,
            "canonical_confirmation_overlap":[ENTRY_FIRST,ENTRY_LAST],
            "canonical_confirmation_remains_untouched_after_future_pilot_outcome_use":False,
            "prior_outcome_exposure_verified":False},
        "multiplicity":{"new_confirmatory_family":False,"alpha_allocated_this_pilot":[0,1],"alpha_spent":[0,1],
            "existing_stock_alpha_ceiling":[1,160],"existing_etf_reserve":[1,160],"reserve_transferable":False,
            "registered_look_id":None,"authorized_outcome_looks":0,"consumed_outcome_looks":0,
            "future_outcome_join_requires_prior_permanent_registration":True},
        "readiness":_authority()})


def _plan(value):
    _need(type(value) is PilotMetadataResult, "genuine_pilot_plan_required")
    body = value.to_payload()
    _need(body.get("schema") == SCHEMA and body.get("evidence_epoch") == EPOCH
        and body.get("frozen_parent_policy_sha256") == hash_payload(_parent_policy())
        and body.get("readiness") == _authority(), "genuine_pilot_plan_required")
    return body


def assess_entry_context(*, plan, metadata_raw, expected_metadata_sha256):
    """Check context metadata, never prices/returns or factual source entitlement.

    Younger listings are explicitly excluded with all existing prior context;
    missing/reordered mature metadata refuses rather than becoming zeros. A
    positive metadata shape cannot promote real eligibility or readiness.
    """
    parent = _plan(plan)
    body = _decode(metadata_raw,expected_metadata_sha256)
    keys = {"schema","pilot_plan_sha256","entry_session","security_id","first_listing_session","listing_known_at_utc",
        "listing_evidence_sha256","prior_listed_sessions","open_intervals","stock_context_sessions","signal_context_sessions",
        "context_known_at_utc"}
    _need(type(body) is dict and set(body) == keys and body["schema"] == ENTRY_SCHEMA and body["pilot_plan_sha256"] == plan.sha256,
        "pilot_entry_metadata_schema_refused")
    _need(type(body["security_id"]) is str and _ID.fullmatch(body["security_id"]) is not None, "bounded_security_metadata_id_required")
    _digest(body["listing_evidence_sha256"])
    rows = parent["calendar_sessions"];dates = [row["session"] for row in rows]
    _need(type(body["entry_session"]) is str and ENTRY_FIRST <= body["entry_session"] <= ENTRY_LAST
        and body["entry_session"] in dates, "entry_outside_fixed_pilot_refused")
    i = dates.index(body["entry_session"]);opened = _utc(rows[i]["open_utc"]);cutoff = opened-timedelta(minutes=2)
    first = _day(body["first_listing_session"]);known = _utc(body["listing_known_at_utc"])
    _need(first <= _day(body["entry_session"]) and known <= cutoff, "future_listing_or_knowledge_refused")
    if body["first_listing_session"] >= dates[0]:
        _need(body["first_listing_session"] in dates,"listing_date_not_in_supplied_regular_calendar")
        listing = dates.index(body["first_listing_session"])
    else:listing = 0
    lower = max(listing,i-253)
    prior = dates[lower:i]
    _need(type(body["prior_listed_sessions"]) is list and body["prior_listed_sessions"] == prior,
        "actual_prior_listing_metadata_gap_or_order_refused")
    intervals = body["open_intervals"]
    _need(type(intervals) is list and len(intervals) == max(0,len(prior)-1), "actual_prior_interval_metadata_count_refused")
    for row,j in zip(intervals,range(lower+1,i),strict=True):
        _need(type(row) is dict and set(row) == {"start_session","end_session","knowledge_at_utc","source_record_sha256"}
            and row["start_session"] == dates[j-1] and row["end_session"] == dates[j],
            "actual_prior_interval_metadata_gap_or_clock_refused")
        _digest(row["source_record_sha256"])
        _need(_utc(rows[j]["open_utc"]) <= _utc(row["knowledge_at_utc"]) <= cutoff,
            "future_or_unavailable_interval_metadata_refused")
    stock_start = max(listing,i-60)
    _need(type(body["stock_context_sessions"]) is list and body["stock_context_sessions"] == dates[stock_start:i],
        "complete_liquidity_context_metadata_required")
    _need(type(body["signal_context_sessions"]) is list and body["signal_context_sessions"] == dates[i-30:i+1],
        "inclusive_age0_through30_signal_context_required")
    context_known = _utc(body["context_known_at_utc"])
    _need(context_known <= cutoff and (stock_start == i or _utc(rows[i-1]["close_utc"]) <= context_known),
        "future_or_unavailable_preentry_context_refused")
    scheduled = next(row for row in parent["scheduled_entries"] if row["entry_session"] == body["entry_session"])
    reasons = list(scheduled["schedule_exclusion_reasons"])
    if len(prior) < 253:reasons.append("primary_factor_calibration_listing_seasoning_below_253_sessions")
    return _factory({"schema":ENTRY_REPORT_SCHEMA,"evidence_epoch":EPOCH,"pilot_plan_sha256":plan.sha256,
        "entry_metadata_sha256":expected_metadata_sha256,"entry_session":body["entry_session"],"security_id":body["security_id"],
        "phase":scheduled["phase"],"metadata_disposition":"EXCLUDED_METADATA" if reasons else "CONTEXT_METADATA_COMPLETE",
        "exclusion_reasons":reasons,"declared_prior_listing_sessions":len(prior),"declared_prior_open_intervals":len(intervals),
        "declared_liquidity_context_sessions":i-stock_start,"declared_signal_context_session_labels":31,
        "moo_prerequisite_cutoff_utc":cutoff.isoformat().replace("+00:00","Z"),
        "metadata_is_not_actual_price_or_listing_evidence":True,"source_row_must_remain_in_accounting":True,
        "real_primary_eligibility_established":False,"readiness":_authority()})
