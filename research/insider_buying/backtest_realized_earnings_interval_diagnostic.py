"""Pre-outcome civil-date/timing successor; never invent a release instant.

This is a separate descriptive policy epoch supplementing an exact bound v2
primary registration. It does NOT satisfy, rewrite or backdate that parent's
old exact-UTC diagnostic implementation identity. Primary economics, source
population and permanent look are unchanged. Every source semantics, coverage
and actual-release assertion needs separately supplied, externally bound
evidence; public documentation, an upcoming date or a confirmed forecast date
is not actual-release proof. No provider-specific semantics are inferred here.

For example EODHD documents actual report_date and nullable BeforeMarket /
AfterMarket labels at https://eodhd.com/financial-apis/calendar-upcoming-earnings-ipos-and-splits .
That alone neither qualifies an account/source nor proves complete coverage.
No file, credential, provider, QC or outcome query is performed. All execution
remains fixture-only, refusing production BEFORE any supplied source decode.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import localcontext
from zoneinfo import ZoneInfo

from research.insider_buying import backtest_registered_analysis as analysis


SCHEMA = "insider-realized-earnings-interval-sensitivity-v1"
REGISTRATION_SCHEMA = "insider-realized-earnings-interval-registration-v1"
SOURCE_SCHEMA = "insider-source-event-actual-earnings-civil-date-coverage-v1"
SEMANTICS_SCHEMA = "insider-actual-earnings-civil-date-semantics-v1"
MAX_BYTES = 16 * 1024 * 1024
MAX_RELEASES_PER_EVENT = 32
MAX_REVISIONS_PER_RELEASE = 16


class EarningsIntervalDiagnosticError(ValueError):
    """Missing, ambiguous or cross-epoch release evidence refused."""


def _need(condition, reason):
    if not condition:
        raise EarningsIntervalDiagnosticError("REFUSED: " + reason)


def frozen_interval_policy() -> dict:
    """Explicit delegated pre-outcome choice, not empirical registration proof."""
    return {"version": SCHEMA,
        "supersession_scope": "required-descriptive-earnings-diagnostic-only-not-parent-primary-economics",
        "reaction_session": "first-regular-session-close-strictly-after-every-evidence-consistent-release-instant",
        "report_date_timezone": "America/New_York",
        "before_market": "actual-release-before-that-regular-session-open",
        "after_market": "actual-release-at-or-after-that-regular-session-close",
        "unknown_timing": "entire-exchange-local-civil-date-without-invented-instant",
        "recorded_time": "source-version-observation-not-release-time-null-envelope-conservatively-retains-entire-date",
        "nonregular_report_date": "null-timing-only-entire-civil-date",
        "windows_sessions": [2, 5], "windows_inclusive": True,
        "ambiguity_rule": "each-active-release-membership-invariant-in-both-windows-else-entire-diagnostic-unavailable",
        "coverage": "complete-inclusive-civil-dates-from-entry-minus6-close-date-through-entry-plus5-close-date",
        "population": "every-exact-frozen-source-event-not-confirmation-subset",
        "earnings_used_for_primary_event_selection": False,
        "earnings_used_for_execution_clock": False,
        "missing_coverage": "explicit-unavailable-no-empty-as-none-no-partial-acceptance",
        "new_look": False, "alpha_spent": [0, 1]}


def interval_analysis_plan_descriptor(*, implementation_sha256: str) -> dict:
    analysis._digest(implementation_sha256)
    return {"method_id": "ib-stock-actual-release-civil-date-invariant-plusminus2and5-v1",
        "definition": "Required descriptive full-source-event comparison: actual public report date in qualified exchange timezone; BeforeMarket before regular open, AfterMarket at/after regular close, null entire civil date; all possible first-strictly-later-close reaction sessions must have identical inclusive +/-2 and +/-5 membership. Missing/ambiguous is whole-diagnostic unavailable. No guessed instant, primary change, additional alpha or new look.",
        "implementation_sha256": implementation_sha256}


@dataclass(frozen=True, slots=True)
class EarningsIntervalDiagnosticTrustRoots:
    trust_scope: str
    parent_registration_sha256: str
    manifest_sha256: str
    primary_report_sha256: str
    interval_registration_sha256: str
    source_semantics_sha256: str
    semantics_qualification_receipt_sha256: str
    actual_earnings_sha256: str
    source_receipt_sha256: str
    rights_sha256: str
    diagnostic_implementation_sha256: str

    def __post_init__(self):
        _need(type(self) is EarningsIntervalDiagnosticTrustRoots and type(self.trust_scope) is str
              and self.trust_scope in {"fixture", "production"}, "exact external interval roots required")
        for name in self.__dataclass_fields__:
            if name.endswith("sha256"):
                analysis._digest(getattr(self, name))


def _civil_bounds(day, zone):
    # Construct EACH midnight separately: adding 24 hours in UTC is wrong on
    # DST transitions. These boundaries are not invented release timestamps.
    return (datetime.combine(day, time.min, zone),
            datetime.combine(day + timedelta(days=1), time.min, zone))


def _possible_reactions(day, category, dates, closes, zone):
    if category is not None:
        _need(type(category) is str and category in {"BeforeMarket", "AfterMarket"},
              "unqualified timing category")
        _need(day.isoformat() in dates, "market timing category on nonregular report date")
        index = dates.index(day.isoformat())
        possible = (index,) if category == "BeforeMarket" else (index + 1,)
    else:
        lower, upper = _civil_bounds(day, zone)
        # Reaction intervals are [previous_close, close), because a release AT
        # a close maps to the next. A civil date is [midnight, next_midnight).
        first, last = bisect_right(closes, lower), bisect_left(closes, upper)
        possible = tuple(range(first, last + 1))
    _need(bool(possible) and possible[-1] < len(closes), "possible reaction sessions not fully bracketed")
    return possible


def assess_realized_earnings_interval_sensitivity(*, primary_result: analysis.RegisteredStudyV2Result,
        interval_registration_raw: bytes, source_semantics_raw: bytes, actual_earnings_raw: bytes,
        trust_roots: EarningsIntervalDiagnosticTrustRoots, expected_implementation_sha256: str) -> dict:
    """Evaluate the separately frozen descriptive successor on supplied fixtures.

    A COMPLETE empty list means source-derived complete issuer/date coverage,
    not that an unbound query returned nothing. Every active release, including
    prior-close-date and last-coverage-date releases, is checked. Null timing
    admits all instants of that local date, not a convenient BMO/AMC default.
    """
    _need(type(trust_roots) is EarningsIntervalDiagnosticTrustRoots, "exact interval roots required")
    trust_roots.__post_init__()
    _need(trust_roots.trust_scope == "fixture", "production interval diagnostic blocked by unchanged zero-look gate")
    _need(type(primary_result) is analysis.RegisteredStudyV2Result, "genuine sealed v2 primary result required")
    sealed = primary_result._body()
    report, parent, manifest = (sealed[key] for key in ("report", "registration", "manifest"))
    _need(report["schema"] == analysis.SCHEMA_V2 and report["trust_scope"] == "fixture"
          and parent["schema"] == "insider-stock-analysis-registration-v2"
          and manifest["schema"] == "insider-stock-event-study-manifest-v3", "parent primary epoch differs")
    _need(primary_result.sha256 == trust_roots.primary_report_sha256
          and report["artifact_sha256s"]["registration"] == trust_roots.parent_registration_sha256
          and report["artifact_sha256s"]["manifest"] == trust_roots.manifest_sha256,
          "parent primary/registration/manifest binding differs")
    analysis._digest(expected_implementation_sha256)
    _need(expected_implementation_sha256 == trust_roots.diagnostic_implementation_sha256,
          "interval executable identity differs")
    registration = analysis._decode(interval_registration_raw, trust_roots.interval_registration_sha256, max_bytes=MAX_BYTES)
    analysis._fields(registration, {"schema", "trust_scope", "registered_look_id", "candidate_id",
        "parent_registration_sha256", "manifest_sha256", "event_inventory_sha256",
        "parent_exact_utc_diagnostic_implementation_sha256", "diagnostic_implementation_sha256",
        "source_semantics_sha256", "registered_at_utc", "first_outcome_access_utc", "policy", "analysis_plan"},
        "supplemental interval registration")
    events = manifest["events"]
    event_hash = analysis._sha(analysis.canonical_bytes(events))
    _need(registration["schema"] == REGISTRATION_SCHEMA and registration["trust_scope"] == "fixture"
          and registration["parent_registration_sha256"] == trust_roots.parent_registration_sha256
          and registration["manifest_sha256"] == trust_roots.manifest_sha256
          and registration["event_inventory_sha256"] == event_hash
          and registration["registered_look_id"] == parent["registered_look_id"]
          and registration["candidate_id"] == parent["candidate_id"]
          and registration["parent_exact_utc_diagnostic_implementation_sha256"] == parent["realized_earnings_implementation_sha256"]
          and registration["diagnostic_implementation_sha256"] == expected_implementation_sha256
          and registration["source_semantics_sha256"] == trust_roots.source_semantics_sha256,
          "supplemental parent/look/population/implementation epoch differs")
    for key in registration:
        if key.endswith("sha256"): analysis._digest(registration[key])
    _need(analysis.canonical_bytes(registration["policy"]) == analysis.canonical_bytes(frozen_interval_policy())
          and analysis.canonical_bytes(registration["analysis_plan"]) == analysis.canonical_bytes(
              interval_analysis_plan_descriptor(implementation_sha256=expected_implementation_sha256)),
          "fixed supplemental interval policy/method differs")
    _need(registration["first_outcome_access_utc"] == parent["first_outcome_access_utc"]
          and analysis._utc(parent["registered_at_utc"]) <= analysis._utc(registration["registered_at_utc"])
          < analysis._utc(parent["first_outcome_access_utc"]), "supplemental policy not frozen before same first outcome")
    semantics = analysis._decode(source_semantics_raw, trust_roots.source_semantics_sha256, max_bytes=MAX_BYTES)
    analysis._fields(semantics, {"schema", "trust_scope", "provider_id", "product_id", "dataset_id",
        "source_document_sha256", "qualification_receipt_sha256", "actual_status_rule", "report_date_meaning",
        "market_timezone", "before_market_meaning", "after_market_meaning", "null_meaning"}, "qualified source semantics")
    _need(semantics["schema"] == SEMANTICS_SCHEMA and semantics["trust_scope"] == "fixture"
          and semantics["qualification_receipt_sha256"] == trust_roots.semantics_qualification_receipt_sha256,
          "source semantics qualification epoch differs")
    for key in ("provider_id", "product_id", "dataset_id"): analysis._id(semantics[key])
    for key in ("source_document_sha256", "qualification_receipt_sha256"): analysis._digest(semantics[key])
    expected_semantics = {"actual_status_rule": "explicit-source-confirmation-of-published-results-never-date-status-only",
        "report_date_meaning": "exchange-local-civil-date-of-actual-public-release",
        "market_timezone": "America/New_York",
        "before_market_meaning": "actual-public-release-before-that-regular-session-open",
        "after_market_meaning": "actual-public-release-at-or-after-that-regular-session-close",
        "null_meaning": "actual-public-release-time-unknown-within-entire-reported-civil-date"}
    _need(all(semantics[key] == value for key, value in expected_semantics.items()),
          "actual release/date/timing semantics absent or unqualified")
    zone = ZoneInfo("America/New_York")
    sessions = manifest["sessions"]
    dates = [row["session"] for row in sessions]
    closes = [analysis._utc(row["close_utc"]) for row in sessions]
    _need(all(analysis._utc(row["open_utc"]).astimezone(zone).date().isoformat() == row["session"]
              == closing.astimezone(zone).date().isoformat() for row, closing in zip(sessions, closes, strict=True)),
          "bound US regular calendar civil-date identity differs")
    source = analysis._decode(actual_earnings_raw, trust_roots.actual_earnings_sha256, max_bytes=MAX_BYTES)
    analysis._fields(source, {"schema", "trust_scope", "interval_registration_sha256", "parent_registration_sha256",
        "manifest_sha256", "event_inventory_sha256", "calendar_sha256", "source_semantics_sha256",
        "source_receipt_sha256", "rights_sha256", "source_as_of_utc", "events"}, "civil-date actual coverage")
    _need(source["schema"] == SOURCE_SCHEMA and source["trust_scope"] == "fixture"
          and source["interval_registration_sha256"] == trust_roots.interval_registration_sha256
          and source["parent_registration_sha256"] == trust_roots.parent_registration_sha256
          and source["manifest_sha256"] == trust_roots.manifest_sha256
          and source["event_inventory_sha256"] == event_hash
          and source["calendar_sha256"] == parent["calendar_sha256"]
          and source["source_semantics_sha256"] == trust_roots.source_semantics_sha256
          and source["source_receipt_sha256"] == trust_roots.source_receipt_sha256
          and source["rights_sha256"] == trust_roots.rights_sha256, "civil-date source/rights/calendar epoch differs")
    asof = analysis._utc(source["source_as_of_utc"])
    rows = source["events"]
    _need(type(rows) is list and len(rows) == len(events), "full source-event coverage missing/extra")
    values = sealed["event_results"]
    _need([row["signal_id"] for row in values] == [row["signal_id"] for row in events], "sealed primary population order differs")
    memberships, unavailable, active_count = {}, [], 0
    for row, event in zip(rows, events, strict=True):
        analysis._fields(row, {"signal_id", "issuer_id", "security_id", "source_event_sha256",
            "coverage_start_date", "coverage_end_date", "coverage_disposition", "unavailable_reason", "releases"}, "civil-date event coverage")
        _need(all(row[key] == event[key] for key in ("signal_id", "issuer_id", "security_id", "source_event_sha256")),
              "civil-date event identity missing/foreign/reordered")
        entry = dates.index(event["entry_session"])
        lower, upper = closes[entry - 6].astimezone(zone).date(), closes[entry + 5].astimezone(zone).date()
        _need(analysis._date(row["coverage_start_date"]) == lower and analysis._date(row["coverage_end_date"]) == upper
              and asof >= _civil_bounds(upper, zone)[1], "inclusive prior-close through plus5 civil-date coverage incomplete")
        _need(type(row["coverage_disposition"]) is str and row["coverage_disposition"] in {"COMPLETE", "UNAVAILABLE"},
              "coverage disposition invalid")
        releases = row["releases"]
        _need(type(releases) is list and len(releases) <= MAX_RELEASES_PER_EVENT, "actual releases absent/unbounded")
        if row["coverage_disposition"] == "UNAVAILABLE":
            analysis._id(row["unavailable_reason"])
            _need(not releases, "unavailable coverage cannot select observed releases")
            unavailable.append({"signal_id": event["signal_id"], "reason": row["unavailable_reason"]})
            memberships[event["signal_id"]] = None
            continue
        _need(row["unavailable_reason"] is None, "complete coverage carries missing reason")
        seen, order, excluded, ambiguous = set(), [], {2: False, 5: False}, False
        for release in releases:
            analysis._fields(release, {"release_id", "release_type", "lineage"}, "actual civil-date release")
            identity = analysis._id(release["release_id"])
            _need(identity not in seen and release["release_type"] == "ACTUAL_PUBLIC_EARNINGS_RELEASE", "duplicate or forecast/call/filing release")
            seen.add(identity)
            lineage = release["lineage"]
            _need(type(lineage) is list and 1 <= len(lineage) <= MAX_REVISIONS_PER_RELEASE, "release lineage absent/unbounded")
            prior, previous_time, versions = None, None, set()
            for revision in lineage:
                analysis._fields(revision, {"version_id", "supersedes_version_id", "recorded_at_utc", "actual_report_date",
                    "timing_category", "actual_release_confirmed", "status", "source_document_sha256", "source_record_sha256"}, "civil-date release revision")
                version, recorded, day = analysis._id(revision["version_id"]), analysis._utc(revision["recorded_at_utc"]), analysis._date(revision["actual_report_date"])
                category = revision["timing_category"]
                _need(category is None or type(category) is str and category in {"BeforeMarket", "AfterMarket"}, "unqualified timing category")
                if category == "AfterMarket":
                    _need(day.isoformat() in dates, "market timing category on nonregular report date")
                    _need(recorded >= closes[dates.index(day.isoformat())],
                          "actual AfterMarket confirmation recorded before regular close")
                for key in ("source_document_sha256", "source_record_sha256"): analysis._digest(revision[key])
                _need(version not in versions and revision["supersedes_version_id"] == prior
                      and (previous_time is None or previous_time < recorded)
                      and _civil_bounds(day, zone)[0] <= recorded <= asof
                      and revision["actual_release_confirmed"] is True
                      and type(revision["status"]) is str and revision["status"] in {"ACTIVE", "RETRACTED"},
                      "actual-release confirmation/correction lineage differs")
                versions.add(version); prior, previous_time = version, recorded
            final = lineage[-1]
            if final["status"] == "RETRACTED": continue
            day = analysis._date(final["actual_report_date"])
            _need(lower <= day <= upper, "actual report date outside complete bound coverage")
            possible = _possible_reactions(day, final["timing_category"], dates, closes, zone)
            order.append((day, identity)); active_count += 1
            for window in (2, 5):
                choices = {abs(index - entry) <= window for index in possible}
                if len(choices) != 1: ambiguous = True
                else: excluded[window] |= next(iter(choices))
        _need(order == sorted(order), "active actual releases reordered")
        if ambiguous:
            unavailable.append({"signal_id": event["signal_id"], "reason": "actual-release-reaction-window-ambiguous"})
            memberships[event["signal_id"]] = None
        else: memberships[event["signal_id"]] = excluded
    available, diagnostics = not unavailable, None
    if available:
        with localcontext() as arithmetic:
            arithmetic.prec = 50
            diagnostics = {}
            for window in (2, 5):
                excluded = [event["signal_id"] for event in events if memberships[event["signal_id"]][window]]
                retained = [analysis._decimal(row["matched_net10_20s"]) for row in values if row["signal_id"] not in excluded]
                diagnostics[str(window)] = {"excluded_signal_ids": excluded, "retained": len(retained),
                    "mean_matched_net10": analysis._text(analysis._mean(retained)) if retained else None}
    result = {"schema": SCHEMA, "trust_scope": "fixture", "registered_look_id": parent["registered_look_id"],
        "candidate_id": parent["candidate_id"], "parent_registration_sha256": trust_roots.parent_registration_sha256,
        "interval_registration_sha256": trust_roots.interval_registration_sha256, "manifest_sha256": trust_roots.manifest_sha256,
        "primary_report_sha256": primary_result.sha256, "actual_earnings_sha256": trust_roots.actual_earnings_sha256,
        "source_semantics_sha256": trust_roots.source_semantics_sha256,
        "semantics_qualification_receipt_sha256": trust_roots.semantics_qualification_receipt_sha256,
        "source_receipt_sha256": trust_roots.source_receipt_sha256, "rights_sha256": trust_roots.rights_sha256,
        "parent_exact_utc_diagnostic_implementation_sha256": parent["realized_earnings_implementation_sha256"],
        "effective_diagnostic_implementation_sha256": expected_implementation_sha256,
        "parent_exact_utc_diagnostic_satisfied": False, "supplemental_policy_epoch": REGISTRATION_SCHEMA,
        "disposition": "FIXTURE_COMPLETE" if available else "UNAVAILABLE", "coverage_complete": available,
        "event_count": len(events), "active_release_count": active_count, "unavailable_events": unavailable,
        "earnings_exclusion_diagnostics": diagnostics, "windows_sessions": [2, 5],
        "retrospective_descriptive_only": True, "primary_selection_or_orders_changed": False,
        "release_instant_invented": False, "new_outcome_query_performed": False, "raw_or_per_event_returns_exported": False,
        "source_authentication_performed": False, "rights_authenticated_here": False,
        "source_semantics_authenticated_here": False, "implementation_execution_identity_verified_here": False,
        "source_semantics_qualification_performed": False,
        "required_diagnostic_verified_for_production": False, "ib5_pass": False, "backtesting_ready": False,
        "look_authority": False, "alpha_spent": [0, 1], "registered_looks_consumed": 0, "qc_jobs": 0}
    result["diagnostic_sha256"] = analysis._sha(analysis.canonical_bytes(result))
    return result
