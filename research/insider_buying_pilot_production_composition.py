"""Pilot-only pre-outcome registration and genuine per-decision source bridge.

This outer research orchestrator deliberately lives OUTSIDE the provider-free
insider_buying package: its existing full-census contract depends on protected
source runners. Importing it performs no source or provider operation.
This additive path does not call or modify the frozen full-study registration,
event, analysis, earnings or QC factories. A complete 25-quarter census binds
ONE pilot registration; each entry separately consumes an already genuinely
parsed, cutoff-filtered source stream for its exact 31-label signal context.
Neither a census nor a registration hash substitutes for original admission.

The registration is a source-prerequisite claim, NOT the final admitted-parent
and event-inventory production look registration. That final root is still
required before outcomes; a complete census cannot substitute for it.
The bridge intentionally stops BEFORE causal lot/event/reference composition,
earnings evaluation, outcomes and QC. It does not authenticate an external
permanent-look claim, calendar, rights or historical identity. In particular,
the old fixture-only interval diagnostic is NOT enabled by this module.
There is no file, network, credential, artifact loader or execution surface.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
import hashlib
import json
import re
import weakref

from data.hashing import canonical_json, hash_bytes, hash_payload
from research import insider_buying_pilot_2021_2025 as pilot
from research import insider_buying_pilot_sec_roster as roster
from research.insider_buying import backtest_source_stream as stream
from research.insider_buying import backtest_realized_earnings_interval_diagnostic as interval
from research.insider_buying.sec_ib1c_v2_downstream import V2QuarterCoverage, compose_v2_scope_coverage


SCHEMA = "insider-pilot-source-composition-2021-2025-v1"
REGISTRATION_SCHEMA = SCHEMA + "/registration"
LOOK_SCHEMA = SCHEMA + "/permanent-look-claim"
EARNINGS_SCHEMA = SCHEMA + "/earnings-contract"
MAX_CONTROL_BYTES = 2 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,79}\Z")
_TOKEN = object()
_REGISTRATIONS = {}
_ENTRIES = {}


class PilotCompositionError(ValueError):
    """Fixed sanitized classifications; never supplied values or OS text."""


def _need(ok, code):
    if not ok:
        raise PilotCompositionError(code)


def _raw(value):
    return canonical_json(value).encode("utf-8")


def _sha(value):
    _need(type(value) is str and _SHA.fullmatch(value) is not None, "external_digest_required")
    return value


def _keys(value, expected):
    _need(type(value) is dict and set(value) == set(expected), "exact_control_schema_required")


def _decode(raw, digest):
    _need(type(raw) is bytes and 0 < len(raw) <= MAX_CONTROL_BYTES
          and hash_bytes(raw) == _sha(digest), "bounded_hash_bound_control_required")
    def pairs(items):
        result = {}
        for key, value in items:
            _need(key not in result, "duplicate_control_key_refused")
            result[key] = value
        return result
    def nonfinite(_):
        raise PilotCompositionError("nonfinite_control_refused")
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)
        _need(type(value) is dict and _raw(value) == raw, "canonical_control_required")
    except (ValueError, UnicodeError, RecursionError) as exc:
        if type(exc) is PilotCompositionError:
            raise
        raise PilotCompositionError("strict_control_json_required") from None
    return value


def _same(left, right, code):
    _need(_raw(left) == _raw(right), code)  # Also rejects bool/int equality.


@dataclass(frozen=True, slots=True)
class PilotProductionTrustRoots:
    """Application-supplied byte roots, not authenticated factual assertions."""
    trust_scope: str
    pilot_plan_sha256: str
    full_census_sha256: str
    calendar_sha256: str
    earnings_contract_sha256: str
    registration_sha256: str
    permanent_look_claim_sha256: str
    implementation_sha256: str
    outcome_vintage_sha256: str
    rights_evidence_sha256: str

    def hashes(self):
        _need(type(self) is PilotProductionTrustRoots and type(self.trust_scope) is str
              and self.trust_scope in {"fixture", "production"}, "exact_pilot_trust_roots_required")
        return {item.name: _sha(getattr(self, item.name)) for item in fields(self)
                if item.name != "trust_scope"}


def pilot_earnings_contract(*, trust_scope, archive_inventory_sha256, source_semantics_sha256,
                           exact_utc_implementation_sha256, interval_implementation_sha256):
    """Detached required methods; this does NOT qualify source-event coverage."""
    _need(type(trust_scope) is str and trust_scope in {"fixture", "production"}, "exact_pilot_scope_required")
    return {"schema": EARNINGS_SCHEMA, "trust_scope": trust_scope,
        "archive_inventory_sha256": _sha(archive_inventory_sha256),
        "source_semantics_sha256": _sha(source_semantics_sha256),
        "exact_utc_implementation_sha256": _sha(exact_utc_implementation_sha256),
        "interval_implementation_sha256": _sha(interval_implementation_sha256),
        "windows_sessions": [2, 5], "windows_inclusive": True,
        "processing_scope": "local-retrospective-only-not-qc-primary-input",
        "source_version_policy": "single-truthful-present-version-not-required-as-known-forecast-archive",
        "coverage_policy": "every-pilot-source-event-issuer-inclusive-date-window-no-empty-as-none",
        "missing_coverage": "whole-diagnostic-unavailable-no-partial-acceptance",
        "earnings_used_for_primary_selection": False, "earnings_used_for_execution_clock": False,
        "civil_date_policy": interval.frozen_interval_policy()}


def _prerequisites(plan, census, calendar_raw, earnings_raw, roots):
    _need(type(roots) is PilotProductionTrustRoots, "exact_pilot_trust_roots_required")
    hashes = roots.hashes()
    try:
        parent = pilot._plan(plan)
        roster.validate_pilot_sec_roster(census)
        population = census.to_payload()
    except (ValueError, TypeError, AttributeError):
        raise PilotCompositionError("genuine_pilot_plan_and_full_census_required") from None
    _need(plan.sha256 == hashes["pilot_plan_sha256"] and census.sha256 == hashes["full_census_sha256"],
          "pilot_or_census_root_differs")
    _need(type(population["fixture_only"]) is bool
          and population["fixture_only"] == (roots.trust_scope == "fixture"), "fixture_production_scope_mismatch")
    _need(tuple(parent["source_quarters"]) == roster.CONTEXT_PERIODS
          and tuple(item["period"] for item in population["quarters"]) == roster.CONTEXT_PERIODS,
          "complete_pilot_context_census_required")
    calendar = _decode(calendar_raw, hashes["calendar_sha256"])
    _same(calendar, {"schema": pilot.CALENDAR_SCHEMA, "sessions": parent["calendar_sessions"]},
          "pilot_calendar_bytes_differ")
    _need(parent["calendar_sha256"] == hashes["calendar_sha256"], "pilot_calendar_root_differs")
    earnings = _decode(earnings_raw, hashes["earnings_contract_sha256"])
    _keys(earnings, pilot_earnings_contract(trust_scope=roots.trust_scope,
        archive_inventory_sha256="0" * 64, source_semantics_sha256="0" * 64,
        exact_utc_implementation_sha256="0" * 64, interval_implementation_sha256="0" * 64))
    expected = pilot_earnings_contract(trust_scope=roots.trust_scope,
        **{name: earnings[name] for name in ("archive_inventory_sha256", "source_semantics_sha256",
            "exact_utc_implementation_sha256", "interval_implementation_sha256")})
    _same(earnings, expected, "fixed_both_earnings_contracts_required")
    policy = {"evidence_epoch": pilot.EPOCH, "interpretation": "EXPLORATORY_NO_NEW_CONFIRMATORY_ALPHA",
        "frozen_parent_economics": parent["frozen_parent_policy"],
        "parent_policy_sha256": parent["frozen_parent_policy_sha256"],
        "superseded_parent_fields_for_this_pilot_only": ["split", "confirmation_only_primary", "stock_alpha", "etf_alpha_reserve"],
        "pilot_phases": parent["phases"], "pilot_split_policy": parent["split_policy"],
        "alpha_allocated_this_pilot": [0, 1], "alpha_spent": [0, 1],
        "canonical_confirmation_overlap": parent["original_study"]["canonical_confirmation_overlap"],
        "original_study_replaced_or_completed": False}
    subject = {"schema": SCHEMA + "/whole-pilot-subject", "trust_scope": roots.trust_scope,
        "evidence_epoch": pilot.EPOCH, **{name: hashes[name] for name in (
            "pilot_plan_sha256", "full_census_sha256", "calendar_sha256", "earnings_contract_sha256",
            "implementation_sha256", "outcome_vintage_sha256", "rights_evidence_sha256")},
        "entry_window": parent["entry_window"], "source_context_periods": parent["source_quarters"],
        "pilot_periods": list(roster.PILOT_PERIODS), "policy": policy}
    return parent, population, earnings, subject


def describe_pilot_registration_subject(*, pilot_plan, full_census, calendar_raw, earnings_contract_raw, trust_roots):
    """Derive the complete subject BEFORE external registration; not a look."""
    return _prerequisites(pilot_plan, full_census, calendar_raw, earnings_contract_raw, trust_roots)[3]


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class PilotProductionRegistration:
    _bytes: bytes = field(repr=False)
    _plan: object = field(repr=False)
    _census: object = field(repr=False)
    _token: object = field(repr=False)

    def canonical_bytes(self):
        record = _REGISTRATIONS.get(id(self))
        _need(type(self) is PilotProductionRegistration and self._token is _TOKEN and record is not None
              and record[0]() is self and record[1] == self._bytes, "genuine_pilot_registration_required")
        body = json.loads(self._bytes)
        _need(self._plan.sha256 == body["subject"]["pilot_plan_sha256"]
              and self._census.sha256 == body["subject"]["full_census_sha256"], "registration_sources_changed")
        return self._bytes

    def to_payload(self):
        return json.loads(self.canonical_bytes())

    @property
    def sha256(self):
        return hash_bytes(self.canonical_bytes())


def bind_pilot_production_registration(*, pilot_plan, full_census, calendar_raw, earnings_contract_raw,
                                     registration_raw, permanent_look_claim_raw, trust_roots):
    """Validate a separately anchored whole-pilot claim without spending it.

    Both scopes use identical validation. Production additionally requires the
    genuine nonfixture census; no asserted dictionary can replace that object.
    External permanent registration, rights and calendar authenticity remain
    the application's responsibility, never a consequence of these hashes.
    """
    parent, census, earnings, subject = _prerequisites(
        pilot_plan, full_census, calendar_raw, earnings_contract_raw, trust_roots)
    registration = _decode(registration_raw, trust_roots.registration_sha256)
    claim = _decode(permanent_look_claim_raw, trust_roots.permanent_look_claim_sha256)
    _keys(registration, {"schema", "trust_scope", "candidate_id", "registered_look_id", "subject_sha256",
        "permanent_look_claim_sha256", "registered_at_utc", "first_outcome_access_utc"})
    _keys(claim, {"schema", "trust_scope", "origin", "candidate_id", "registered_look_id", "subject_sha256",
        "reserved_at_utc", "first_outcome_access_utc", "maximum_outcome_looks", "consumed_outcome_looks",
        "all_pilot_entries_share_this_look"})
    scope = trust_roots.trust_scope
    _need(registration["schema"] == REGISTRATION_SCHEMA and claim["schema"] == LOOK_SCHEMA
          and registration["trust_scope"] == claim["trust_scope"] == scope, "pilot_registration_scope_differs")
    _need(claim["origin"] == {"fixture": "invented-permanent-pilot-look", "production": "externally-anchored-permanent-pilot-look"}[scope],
          "permanent_pilot_claim_origin_required")
    for name in ("candidate_id", "registered_look_id"):
        _need(type(registration[name]) is str and _ID.fullmatch(registration[name]) is not None
              and claim[name] == registration[name], "whole_pilot_identity_differs")
    _need(registration["subject_sha256"] == claim["subject_sha256"] == hash_payload(subject)
          and registration["permanent_look_claim_sha256"] == trust_roots.permanent_look_claim_sha256,
          "whole_pilot_subject_or_look_root_differs")
    _same({key: claim[key] for key in ("maximum_outcome_looks", "consumed_outcome_looks", "all_pilot_entries_share_this_look")},
          {"maximum_outcome_looks": 1, "consumed_outcome_looks": 0, "all_pilot_entries_share_this_look": True},
          "single_unspent_whole_pilot_look_required")
    try:
        reserved = pilot._utc(claim["reserved_at_utc"])
        registered = pilot._utc(registration["registered_at_utc"])
        first = pilot._utc(registration["first_outcome_access_utc"])
        _need(reserved <= registered < first
              and registration["first_outcome_access_utc"] == claim["first_outcome_access_utc"],
              "pre_outcome_pilot_registration_required")
    except ValueError as exc:
        if type(exc) is PilotCompositionError:
            raise
        raise PilotCompositionError("canonical_registration_clock_required") from None
    body = {"schema": SCHEMA + "/bound-registration", "trust_scope": scope, "subject": subject,
        "registration": registration, "permanent_look_claim": claim, "earnings_contract": earnings,
        "registration_sha256": trust_roots.registration_sha256,
        "permanent_look_claim_sha256": trust_roots.permanent_look_claim_sha256,
        "full_census_counts": census["counts"], "pilot_schedule_counts": parent["schedule_counts"],
        "permanent_look_authenticated_here": False, "permanent_look_authority_granted_here": False,
        "full_admitted_parent_inventory_bound": False, "final_event_population_registration_required": True,
        "actual_earnings_coverage_verified": False,
        "source_authenticity_verified": False, "rights_verified": False, "backtesting_ready": False,
        "research_looks_consumed": 0, "qc_jobs": 0, "backtests": 0}
    raw = _raw(body)
    _need(len(raw) <= MAX_CONTROL_BYTES, "pilot_registration_output_bound_refused")
    result = PilotProductionRegistration(raw, pilot_plan, full_census, _TOKEN)
    _REGISTRATIONS[id(result)] = (weakref.ref(result, lambda _, key=id(result): _REGISTRATIONS.pop(key, None)), raw)
    return result


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class PilotEntrySourceComposition:
    _bytes: bytes = field(repr=False)
    _source: object = field(repr=False)
    _registration: object = field(repr=False)
    _token: object = field(repr=False)

    def canonical_bytes(self):
        record = _ENTRIES.get(id(self))
        _need(type(self) is PilotEntrySourceComposition and self._token is _TOKEN and record is not None
              and record[0]() is self and record[1] == self._bytes, "genuine_pilot_entry_composition_required")
        body = json.loads(self._bytes)
        _need(self._source.sha256 == body["source_stream_sha256"]
              and self._registration.sha256 == body["pilot_registration_sha256"], "composition_inputs_changed")
        return self._bytes

    def to_payload(self):
        return json.loads(self.canonical_bytes())

    @property
    def sha256(self):
        return hash_bytes(self.canonical_bytes())

    def source_evidence(self):
        """The SAME genuine, cutoff-filtered source object; not a reminted seal."""
        self.canonical_bytes()
        return self._source


def compose_pilot_entry_source(*, registration, source_evidence, window_coverages,
                              entry_context_raw, expected_entry_context_sha256):
    """Bind actual source admission to the exact pilot decision/MOO cutoff.

    Complete quarter originals are verified by the upstream source factory;
    only as-of facts survive there. Full-pilot census completeness is distinct
    from this window's admission and from still-unbuilt full-pilot assembly.
    Listing/open-interval context here is validated METADATA, not price proof.
    """
    _need(type(registration) is PilotProductionRegistration, "genuine_pilot_registration_required")
    bound = registration.to_payload()
    context = _decode(entry_context_raw, expected_entry_context_sha256)
    try:
        assessed = pilot.assess_entry_context(plan=registration._plan, metadata_raw=entry_context_raw,
                                             expected_metadata_sha256=expected_entry_context_sha256).to_payload()
        source = stream.validate_stream_source_evidence(source_evidence)
    except (ValueError, TypeError, AttributeError):
        raise PilotCompositionError("genuine_source_and_complete_entry_context_required") from None
    parent = registration._plan.to_payload()
    dates = [row["session"] for row in parent["calendar_sessions"]]
    day = context["entry_session"]
    index = dates.index(day)
    lower = dates[index - 30]
    periods = tuple(period for period in parent["source_quarters"]
                    if f"{lower[:4]}Q{(int(lower[5:7]) - 1) // 3 + 1}" <= period
                    <= f"{day[:4]}Q{(int(day[5:7]) - 1) // 3 + 1}")
    _need(source["trust_scope"] == bound["trust_scope"]
          and source["lookback_start_session"] == lower and source["decision_session"] == day
          and source["decision_cutoff_utc"] == assessed["moo_prerequisite_cutoff_utc"]
          and source["expected_periods"] == source["loaded_periods"] == list(periods)
          and source["relevant_form4_identity_complete"] is True, "exact_causal_window_and_moo_cutoff_required")
    _need(type(window_coverages) is tuple and all(type(item) is V2QuarterCoverage for item in window_coverages),
          "genuine_window_coverages_required")
    try:
        scope = compose_v2_scope_coverage(window_coverages, periods)
    except (ValueError, TypeError, AttributeError):
        raise PilotCompositionError("complete_genuine_window_scope_required") from None
    _need(scope.sha256 == source["preceding_scope_sha256"], "source_window_scope_root_differs")
    full = {row["period"]: row for row in registration._census.to_payload()["quarters"]}
    receipts = source["quarter_inventories"]
    _need(len(receipts) == len(window_coverages), "source_window_inventory_count_differs")
    for coverage, receipt in zip(window_coverages, receipts, strict=True):
        quarter = coverage.to_payload()
        census = full[quarter["period"]]
        _need(receipt["coverage_sha256"] == coverage.sha256 and receipt["period"] == quarter["period"],
              "source_window_coverage_root_differs")
        _same(quarter["form_counts"], census["source_form_counts"], "window_full_census_forms_differ")
        _need(quarter["submission_count"] == census["submission_rows"], "window_full_census_count_differs")
        accounting = hashlib.sha256()
        for row in coverage.pilot_rows():
            _need(row["raw_archive_sha256"] == census["zip_sha256"]
                  and row["raw_submission_member_sha256"] == census["submission_member_sha256"],
                  "window_full_census_raw_source_differs")
            accounting.update(_raw(row) + b"\n")
        _need(accounting.hexdigest() == receipt["all_source_row_accounting_sha256"], "window_all_row_accounting_differs")
    body = {"schema": SCHEMA + "/entry-source", "trust_scope": bound["trust_scope"], "evidence_epoch": pilot.EPOCH,
        "pilot_registration_sha256": registration.sha256, "source_stream_sha256": source_evidence.sha256,
        "source_population_manifest_sha256": source["population_manifest_sha256"],
        "full_census_sha256": registration._census.sha256, "entry_session": day,
        "entry_context_sha256": expected_entry_context_sha256, "entry_context_assessment": assessed,
        "source_lookback_first_session": lower, "source_periods": list(periods),
        "moo_cutoff_utc": assessed["moo_prerequisite_cutoff_utc"],
        "window_source_submission_count": source["source_submission_count"],
        "window_relevant_originals_verified": source["stream_corroborated_form4_count"],
        "as_of_parent_count": source["as_of_parent_count"], "future_parent_count": source["future_parent_count"],
        "as_of_transaction_count": source["as_of_transaction_count"],
        "as_of_amendment_eligibility_not_evaluated_count": source["as_of_amendment_eligibility_not_evaluated_count"],
        "genuine_window_original_source_bound": True, "full_pilot_original_admission_complete": False,
        "causal_lots_and_events_composed": False, "actual_price_listing_context_verified": False,
        "earnings_evaluated": False, "interval_production_analyzer_enabled": False,
        "source_authenticity_verified": False, "rights_verified": False, "backtesting_ready": False,
        "outcome_access_authorized_here": False, "research_looks_consumed": 0, "qc_jobs": 0, "backtests": 0}
    raw = _raw(body)
    _need(len(raw) <= MAX_CONTROL_BYTES, "pilot_entry_output_bound_refused")
    result = PilotEntrySourceComposition(raw, source_evidence, registration, _TOKEN)
    _ENTRIES[id(result)] = (weakref.ref(result, lambda _, key=id(result): _ENTRIES.pop(key, None)), raw)
    return result
