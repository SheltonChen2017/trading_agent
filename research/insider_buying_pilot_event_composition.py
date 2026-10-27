"""Pilot causal lots/events with honest 09:28 versus first-open corroboration.

This outer, pure orchestrator consumes genuinely parsed source objects. It
does not forge an old full-study manifest/registration seal or enable a QC
candidate. The as-of-MOO source and same-original-population first-open source
are DIFFERENT evidence: later facts never become tradeable 09:28 features.
Both diagnostic replays use the same canonical reference, without pretending
its prerequisites were known at 09:28. Instead the whole target window is
refused when its canonical first-open event population
or required reference was not fully known at MOO. No affected event is silently
dropped, delayed or replaced. All canonical lineage remains in the private
assessment even on temporal refusal.

The clock is the frozen SEC acceptance MODEL. These mathematical cutoff
checks do not authenticate historical public availability at either cutoff;
separately qualified filing/version known-by evidence remains required.

The economic replay matches the frozen first50k, pre-open additions, consumed
lot, known-amendment and issuer/entry merge policy. Existing pure Decimal,
classification, first-open and v3 reference validators remain unchanged.
Pre-source economic-lot facts are projected only when their acceptance cannot
have this target as its literal first open. They stay in the genuine complete
source inventory and ordered row accounting. A target-interval member of any
pre-source lot still refuses the whole window: missing historical threshold
or consumed state is never supplied as zero or as an invented carry-in.
No files, artifacts, transport, credentials, QC, outcomes or orders are read
or executed. Actual source/reference authenticity, 252-open factor history,
both retrospective earnings diagnostics, final population/look registration
and order-based engine parity remain separate prerequisites.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass, field, fields
from decimal import Decimal, localcontext
import hashlib
import heapq
import json
import weakref

from data.financial_primitives import exact_decimal_sum
from data.hashing import canonical_json, hash_bytes, hash_payload
from research import insider_buying_pilot_production_composition as pilot
from research.insider_buying import backtest_evidence_pipeline as base
from research.insider_buying import backtest_event_clock as clock
from research.insider_buying import backtest_event_study_manifest as causal
from research.insider_buying import backtest_registered_analysis as analysis
from research.insider_buying import backtest_source_stream as source_factory


SCHEMA = "insider-pilot-firstopen-two-cutoff-composition-v1"
REFERENCE_SCHEMA = SCHEMA + "/entry-reference"
PRE_SOURCE_TARGET_RELEVANCE_POLICY = "literal-first-open-interval-no-historical-carryin-v1"
MAX_REFERENCE_BYTES = clock.MAX_BYTES
MAX_OUTPUT_BYTES = 128 * 1024 * 1024
_TOKEN = object()
_BUILT = {}


class PilotEventCompositionError(ValueError):
    """Fixed refusal classifications, never source/private exception text."""


def _need(ok, code):
    if not ok:
        raise PilotEventCompositionError(code)


def _raw(value):
    return canonical_json(value).encode("utf-8")


def _same(left, right, code):
    _need(_raw(left) == _raw(right), code)


@dataclass(frozen=True, slots=True)
class PilotEventTrustRoots:
    trust_scope: str
    entry_source_composition_sha256: str
    first_open_source_sha256: str
    security_master_sha256: str
    calendar_sha256: str
    common_equity_exceptions_sha256: str
    entry_reference_sha256: str
    implementation_sha256: str

    def hashes(self):
        _need(type(self) is PilotEventTrustRoots and type(self.trust_scope) is str
              and self.trust_scope in {"fixture", "production"}, "exact_pilot_event_roots_required")
        return {item.name: pilot._sha(getattr(self, item.name)) for item in fields(self)
                if item.name != "trust_scope"}


def _reference(*, raw, roots, calendar_raw, sessions, opens, target, mappings):
    reference = analysis._decode(raw, roots.entry_reference_sha256, max_bytes=MAX_REFERENCE_BYTES)
    analysis._fields(reference, {"schema", "trust_scope", "calendar_sha256", "security_master_sha256",
        "entry_session", "knowledge_at_utc", "regime", "eligible_control_security_ids", "stock_context",
        "stock_context_sha256"}, "pilot entry reference")
    _need(reference["schema"] == REFERENCE_SCHEMA and reference["trust_scope"] == roots.trust_scope
          and reference["calendar_sha256"] == roots.calendar_sha256
          and reference["security_master_sha256"] == roots.security_master_sha256
          and reference["entry_session"] == target, "pilot_entry_reference_root_or_scope_differs")
    index = sessions.index(target)
    opening = opens[index]
    _need(index >= 253 and index + 60 < len(sessions), "complete_preentry_and_horizon_calendar_required")
    known = base._utc(reference["knowledge_at_utc"])
    _need(known < opening and reference["regime"] in {"bull", "bear", "sideways"},
          "preopen_reference_knowledge_and_regime_required")
    active = tuple(item["qc_symbol_id"] for item in mappings
                   if base._utc(item["knowledge_at_utc"]) < opening
                   and item["mapping_first_session"] <= target < item["mapping_last_session"])
    _need(active, "complete_active_security_cohort_required")
    context_raw = _raw(reference["stock_context"])
    _need(hash_bytes(context_raw) == reference["stock_context_sha256"], "stock_context_root_differs")
    # The unchanged v3 validator accepts an opening-time validation cutoff and
    # requires every actual prerequisite strictly before it. We independently
    # compare its latest knowledge with the EARLIER MOO cutoff below; no date
    # is backdated to make the validator accept.
    checked = clock.verify_pit_stock_context_v3(context_raw=context_raw,
        context_sha256=reference["stock_context_sha256"], trust_scope=roots.trust_scope,
        calendar_raw=calendar_raw, calendar_sha256=roots.calendar_sha256,
        decision_session=target, decision_cutoff_utc=base._utc_text(opening), expected_security_ids=active)
    seasoning = {row["qc_symbol_id"] for row in checked["rows"]
                 if row["prior_listing_session_lower_bound"] < 253}
    eligible = sorted(row["qc_symbol_id"] for row in checked["rows"]
                      if row["eligible"] and row["qc_symbol_id"] not in seasoning)
    _same(reference["eligible_control_security_ids"], eligible, "complete_eligible_cohort_differs")
    _need(len(eligible) >= 3, "complete_control_cohort_underfilled")
    latest = max(known, base._utc(checked["latest_prerequisite_knowledge_at_utc"]),
                 *(base._utc(item["knowledge_at_utc"]) for item in mappings if item["qc_symbol_id"] in active))
    return {"eligible_security_ids": eligible, "seasoning_excluded_security_ids": sorted(seasoning),
        "regime": reference["regime"], "reference_sha256": roots.entry_reference_sha256,
        "stock_context_sha256": reference["stock_context_sha256"],
        "latest_prerequisite_knowledge_at_utc": base._utc_text(latest),
        "context_reason_counts": dict(Counter(reason for row in checked["rows"] for reason in row["exclusion_reasons"]))}


def _replay(*, source, mappings, calendar_raw, calendar_sha256, exceptions_raw, exceptions_sha256,
            context, sessions, opens, target, trust_scope, pilot_registration_sha256):
    """One causal replay; no source fact after this source's OWN cutoff exists."""
    metadata = source_factory.validate_stream_source_evidence(source)
    parent_rows = defaultdict(list)
    for row in source.transaction_rows():
        parent_rows[row["accession_number"]].append(row)
    facts = sorted(source.parent_facts(), key=lambda row:(row["accepted_at_utc"], row["period"],
        row["source_record_ordinal"], row["accession_number"]))
    mapping_index = defaultdict(list)
    for item in mappings:
        mapping_index[(item["issuer_cik"], item["security_title"], item["ticker"])].append(item)
    excluded_issuers = set(context["source_excluded_issuers"])
    lots, pending, amended, grouped = {}, [], set(), defaultdict(list)
    reasons = Counter()
    late_members = ordinary_overrides = 0
    target_index = sessions.index(target)
    _need(target_index > 0, "previous_regular_open_for_target_relevance_required")
    previous_open, target_open = opens[target_index - 1], opens[target_index]
    pre_source_outside_target_count = 0
    pre_source_outside_target_digest = hashlib.sha256()

    def finalize(until):
        while pending and pending[0][0] <= until:
            _, key = heapq.heappop(pending)
            lot = lots[key]
            lot["consumed"] = True
            day = sessions[lot["entry_index"]]
            if day != target:
                reasons["first_threshold_outside_target_entry"] += 1
                continue
            if lot["issuer_cik"] in amended:
                reasons["amendment_already_public_before_first_entry"] += 1
                continue
            mapping = lot["mapping"]
            sid = mapping["qc_symbol_id"]
            if sid not in context["eligible_security_ids"]:
                reasons[causal.PRIMARY_SEASONING_EXCLUSION if sid in context["seasoning_excluded_security_ids"]
                        else "failed_first_open_stock_price_liquidity_context"] += 1
                continue
            _need(mapping["mapping_first_session"] <= day
                  and sessions[target_index + 60] < mapping["mapping_last_session"], "mapping_horizon_incomplete")
            scheduled = clock.schedule_first_open(available_at_utc=lot["available_at_utc"], calendar_raw=calendar_raw,
                calendar_sha256=calendar_sha256, trust_scope=trust_scope)
            _need(scheduled["entry_session"] == target, "late_member_changed_literal_first_open")
            _need(lot["total_value"] >= Decimal(50000), "exact_first_threshold_value_lost")
            payload = {"owner_cik": key[0], "qc_symbol_id": key[1], "transaction_date": key[2],
                "issuer_cik": lot["issuer_cik"], "purchase_value_usd": str(lot["total_value"]),
                "available_at_utc": lot["available_at_utc"], "member_event_ids": sorted(lot["member_ids"]),
                "entry_session": target, "first_threshold_at_utc": lot["first_threshold_at_utc"]}
            payload["lot_sha256"] = hash_payload(payload)
            grouped[lot["issuer_cik"]].append(payload)
            _need(len(grouped) <= causal.MAX_EVENTS, "target_event_population_bound_refused")

    for fact in facts:
        accepted = base._utc(fact["accepted_at_utc"])
        _need(accepted <= base._utc(metadata["decision_cutoff_utc"]), "future_fact_in_asof_source_refused")
        # Equal-open additions/amendments MUST NOT rewrite the just-finalized
        # event. This ordering is identical to the canonical causal policy.
        finalize(accepted)
        if fact["form_type"] == "4/A":
            amended.add(fact["issuer_cik"])
            reasons["known_amendment_identity_retained_eligibility_not_evaluated"] += 1
            continue
        for row in parent_rows.get(fact["accession_number"], ()):
            outcomes = row["provisional_outcomes"]
            if row["issuer_cik"] in excluded_issuers:
                reasons["noneligible_source_security"] += 1
                continue
            if len(row["reporting_owners"]) != 1:
                reasons["joint_or_missing_reporting_owner"] += 1
                continue
            if outcomes not in (["eligible_for_lot_aggregation"], ["exclude_non_common_stock"]):
                reasons.update(outcomes)
                continue
            if row["transaction_date"] < metadata["source_start"]:
                # A threshold can cross only upon a lot member's acceptance.
                # Any unseen pre-source member predates this complete source
                # scope. An outside-interval row could affect this target only
                # through an inside-interval member of the SAME old lot; that
                # member still refuses below, regardless of its visible value.
                # Thus no old lot is initialized, reset, replayed or carried in.
                _need(not previous_open <= accepted < target_open,
                      "economic_lot_precedes_complete_source_scope")
                pre_source_outside_target_count += 1
                # The genuine source still owns the full row and its original
                # parent inventory. Bind this small projection through that
                # row's full-content digest without copying footnotes/output.
                descriptor = {name:row[name] for name in
                              ("event_id", "transaction_sha256", "accepted_at_utc", "transaction_date")}
                pre_source_outside_target_digest.update(_raw(descriptor) + b"\n")
                continue
            _need(row["transaction_date"] <= accepted.astimezone(base.ZoneInfo("America/New_York")).date().isoformat(),
                  "transaction_date_after_availability")
            candidates = [item for item in mapping_index.get(
                (row["issuer_cik"], row["security_title_raw"], row["issuer_symbol_raw"]), ())
                if item["mapping_first_session"] <= row["transaction_date"] < item["mapping_last_session"]
                and base._utc(item["knowledge_at_utc"]) <= accepted]
            _need(len(candidates) == 1, "exact_asof_transaction_security_mapping_required")
            mapping = candidates[0]
            classified = clock.classify_pit_common_equity(transaction={key:row[key] for key in
                ("event_id", "issuer_cik", "security_title_raw", "transaction_date")}
                | {"outcomes": outcomes}, mapping={key:value for key,value in mapping.items() if key != "ticker"},
                exception_dictionary_raw=exceptions_raw, exception_dictionary_sha256=exceptions_sha256,
                trust_scope=trust_scope, available_at_utc=row["accepted_at_utc"])
            if not classified["eligible_for_lot_aggregation"]:
                reasons["unresolved_ordinary_share_classification"] += 1
                continue
            ordinary_overrides += classified["ordinary_share_exception_applied"]
            key = row["reporting_owners"][0]["owner_cik"], mapping["qc_symbol_id"], row["transaction_date"]
            lot = lots.setdefault(key, {"total_value": Decimal(0), "member_ids": [], "issuer_cik": row["issuer_cik"],
                "mapping": mapping, "available_at_utc": row["accepted_at_utc"], "consumed": False, "entry_index": None})
            _need(len(lots) <= causal.MAX_LOTS, "economic_lot_population_bound_refused")
            if lot["consumed"]:
                late_members += 1
                continue
            value = Decimal(row["purchase_value_usd"])
            _need(value.is_finite() and value > 0, "finite_positive_exact_purchase_required")
            lot["total_value"] = exact_decimal_sum((lot["total_value"], value), name="pilot causal cumulative purchase")
            lot["member_ids"].append(row["event_id"])
            lot["available_at_utc"] = max(lot["available_at_utc"], row["accepted_at_utc"])
            if lot["entry_index"] is None and lot["total_value"] >= Decimal(50000):
                entry_index = bisect_right(opens, accepted)
                _need(0 < entry_index < len(sessions), "first_threshold_calendar_bracket_required")
                lot["entry_index"], lot["first_threshold_at_utc"] = entry_index, row["accepted_at_utc"]
                heapq.heappush(pending, (opens[entry_index], key))
    # This is a PROJECTION of the upcoming first open for the 09:28 source,
    # never a claim that later facts were already known. The second genuine
    # source independently corroborates it; disagreement refuses the WHOLE
    # target window below, not just an affected event.
    finalize(opens[target_index])
    events, lineage = [], []
    base.formula._require_frozen_policy()
    for issuer, member_lots in sorted(grouped.items()):
        sids = {lot["qc_symbol_id"] for lot in member_lots}
        _need(len(sids) == 1, "multiple_share_classes_cannot_inflate_issuer_entry")
        with localcontext(base.formula._new_decimal_context()):
            score = sum((base.formula._event_formula(Decimal(lot["purchase_value_usd"]), 0)[2]
                         for lot in member_lots), Decimal(0))
        payload = {"event_population_policy": causal.EVENT_POPULATION_POLICY, "issuer_cik": issuer,
            "security_id": next(iter(sids)), "entry_session": target, "lots": member_lots,
            "reference_sha256": context["reference_sha256"],
            "source_population_sha256": metadata["population_manifest_sha256"],
            "security_master_sha256": context["security_master_sha256"],
            "common_equity_exceptions_sha256": exceptions_sha256,
            "pilot_registration_sha256": pilot_registration_sha256}
        digest = hash_payload(payload)
        event = {"signal_id": digest[:32], "issuer_id": issuer, "security_id": payload["security_id"],
            "available_at_utc": max(lot["available_at_utc"] for lot in member_lots),
            "entry_session": target, "exit_session": sessions[target_index + 20],
            "source_event_sha256": digest, "buyer_ids": sorted({lot["owner_cik"] for lot in member_lots}),
            "score": str(score), "regime": context["regime"]}
        events.append(event)
        lineage.append({"signal_id": event["signal_id"], "payload": payload, "source_event_sha256": digest})
    return {"events": events, "lineage": lineage,
        "counts": {"economic_lots_at_target": sum(len(row["payload"]["lots"]) for row in lineage),
            "below_threshold_lots": sum(lot["entry_index"] is None for lot in lots.values()),
            "late_members_not_reset_or_retraded": late_members, "ordinary_share_exception_count": ordinary_overrides,
            "pending_first_opens_after_target": len(pending),
            "pre_source_facts_outside_target_first_open": pre_source_outside_target_count},
        "pre_source_outside_target_rows_sha256": pre_source_outside_target_digest.hexdigest(),
        "reason_counts": dict(sorted(reasons.items()))}


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class PilotEventComposition:
    _bytes: bytes = field(repr=False)
    _entry_source: object = field(repr=False)
    _first_open_source: object = field(repr=False)
    _token: object = field(repr=False)

    def canonical_bytes(self):
        record = _BUILT.get(id(self))
        _need(type(self) is PilotEventComposition and self._token is _TOKEN and record is not None
              and record[0]() is self and record[1] == self._bytes, "genuine_pilot_event_composition_required")
        body = json.loads(self._bytes)
        _need(self._entry_source.sha256 == body["summary"]["entry_source_composition_sha256"]
              and self._first_open_source.sha256 == body["summary"]["first_open_source_sha256"], "event_source_seals_changed")
        return self._bytes

    def to_payload(self):
        """Summary only; source-derived event/lot values stay in private bytes."""
        return json.loads(self.canonical_bytes())["summary"]

    def canonical_events(self):
        """All canonical source events, including a REFUSED window, not orders."""
        return json.loads(self.canonical_bytes())["canonical"]["events"]

    def event_lineage(self):
        return json.loads(self.canonical_bytes())["canonical"]["lineage"]

    def compatible_events(self):
        body = json.loads(self.canonical_bytes())
        _need(body["summary"]["disposition"] == "SOURCE_EVENTS_MOO_COMPATIBLE", "whole_window_moo_compatibility_required")
        return body["canonical"]["events"]

    @property
    def sha256(self):
        return hash_bytes(self.canonical_bytes())


def compose_pilot_entry_events(*, entry_source, first_open_source, security_master_raw, calendar_raw,
                               common_equity_exceptions_raw, entry_reference_raw, trust_roots):
    """Compose source events; temporal incompatibility is a whole-window result."""
    try:
        return _compose(entry_source, first_open_source, security_master_raw, calendar_raw,
                        common_equity_exceptions_raw, entry_reference_raw, trust_roots)
    except PilotEventCompositionError:
        raise
    except (ValueError, TypeError, AttributeError, KeyError, IndexError, RecursionError):
        raise PilotEventCompositionError("pilot_source_reference_or_financial_contract_refused") from None


def _compose(entry_source, first_open_source, security_master_raw, calendar_raw, exceptions_raw, reference_raw, roots):
    _need(type(roots) is PilotEventTrustRoots, "exact_pilot_event_roots_required")
    hashes = roots.hashes()
    _need(type(entry_source) is pilot.PilotEntrySourceComposition, "genuine_pilot_entry_source_required")
    entry = entry_source.to_payload()
    before_source = entry_source.source_evidence()
    before = source_factory.validate_stream_source_evidence(before_source)
    after = source_factory.validate_stream_source_evidence(first_open_source)
    _need(entry_source.sha256 == roots.entry_source_composition_sha256
          and first_open_source.sha256 == roots.first_open_source_sha256
          and entry["trust_scope"] == before["trust_scope"] == after["trust_scope"] == roots.trust_scope,
          "genuine_two_source_roots_and_scope_required")
    for key in ("population_manifest_sha256", "preceding_scope_sha256", "expected_periods", "loaded_periods",
                "lookback_start_session", "decision_session", "source_submission_count", "source_form_counts",
                "relevant_form4_count", "stream_corroborated_form4_count", "all_source_row_accounting_sha256"):
        _same(before[key], after[key], "same_full_original_population_required")
    _same(before_source.quarter_receipts(), first_open_source.quarter_receipts(), "same_original_quarter_receipts_required")
    calendar = base._artifact(calendar_raw, roots.calendar_sha256, "insider-backtest-calendar-v1", roots.trust_scope)
    plan = entry_source._registration._plan.to_payload()
    _same(calendar["sessions"], plan["calendar_sessions"], "exact_pilot_calendar_sessions_required")
    sessions, opens, _, _ = base._calendar(calendar)
    target = entry["entry_session"]
    opening = opens[sessions.index(target)]
    _need(after["decision_cutoff_utc"] == base._utc_text(opening)
          and before["decision_cutoff_utc"] == entry["moo_cutoff_utc"], "genuine_exact_distinct_cutoffs_required")
    cutoff = base._utc(before["decision_cutoff_utc"])
    _same([row for row in first_open_source.parent_facts() if base._utc(row["accepted_at_utc"]) <= cutoff],
          before_source.parent_facts(), "same_exact_asof_parent_prefix_required")
    _same([row for row in first_open_source.transaction_rows() if base._utc(row["accepted_at_utc"]) <= cutoff],
          before_source.transaction_rows(), "same_exact_asof_transaction_prefix_required")
    master = base._artifact(security_master_raw, roots.security_master_sha256,
                           "insider-backtest-security-master-v1", roots.trust_scope)
    mappings = base._mappings(master, sessions, opening, set(after["as_of_issuer_ciks"]))
    clock.verify_common_equity_exceptions(raw=exceptions_raw, digest=roots.common_equity_exceptions_sha256, scope=roots.trust_scope)
    context = _reference(raw=reference_raw, roots=roots, calendar_raw=calendar_raw,
                         sessions=sessions, opens=opens, target=target, mappings=mappings)
    context.update(source_excluded_issuers=[row["issuer_cik"] for row in master["source_exclusions"]],
                   security_master_sha256=roots.security_master_sha256)
    arguments = dict(mappings=mappings, calendar_raw=calendar_raw, calendar_sha256=roots.calendar_sha256,
        exceptions_raw=exceptions_raw, exceptions_sha256=roots.common_equity_exceptions_sha256,
        context=context, sessions=sessions, opens=opens, target=target, trust_scope=roots.trust_scope,
        pilot_registration_sha256=entry["pilot_registration_sha256"])
    provisional = _replay(source=before_source, **arguments)
    canonical = _replay(source=first_open_source, **arguments)
    reasons = []
    if _raw(provisional["events"]) != _raw(canonical["events"]) or _raw(provisional["lineage"]) != _raw(canonical["lineage"]):
        reasons.append("canonical_lot_or_entry_changed_after_moo_cutoff")
    if base._utc(context["latest_prerequisite_knowledge_at_utc"]) > cutoff:
        reasons.append("required_prerequisite_after_moo_cutoff")
    # Window exclusions belong to the genuine plan's fixed phase schedule.
    # The separately retained entry-context assessment describes ONE security;
    # its listing age cannot exclude every other event in this window. Actual
    # per-security seasoning remains enforced by _reference and _replay above.
    schedule = next(row for row in plan["scheduled_entries"] if row["entry_session"] == target)
    disposition = ("REFUSED_TEMPORAL_INCOMPATIBILITY" if reasons else "PILOT_SCHEDULE_EXCLUDED"
                   if schedule["schedule_disposition"] == "EXCLUDED" else "SOURCE_EVENTS_MOO_COMPATIBLE")
    summary = {"schema": SCHEMA, "trust_scope": roots.trust_scope, **hashes,
        "event_clock_basis": "SEC_ACCEPTANCE_MODEL", "historical_public_known_by_verified_here": False,
        "pilot_registration_sha256": entry["pilot_registration_sha256"], "entry_session": target,
        "asof_moo_cutoff_utc": before["decision_cutoff_utc"], "canonical_corroboration_cutoff_utc": after["decision_cutoff_utc"],
        "disposition": disposition, "whole_window_refusal_reasons": reasons,
        "pilot_schedule_exclusion_reasons": schedule["schedule_exclusion_reasons"],
        "provisional_event_count": len(provisional["events"]), "canonical_event_count": len(canonical["events"]),
        "canonical_event_inventory_sha256": hash_payload(canonical["events"]),
        "canonical_lineage_sha256": hash_payload(canonical["lineage"]),
        "provisional_counts": provisional["counts"], "canonical_counts": canonical["counts"],
        "pre_source_target_relevance_policy": PRE_SOURCE_TARGET_RELEVANCE_POLICY,
        "provisional_pre_source_outside_target_rows_sha256": provisional["pre_source_outside_target_rows_sha256"],
        "canonical_pre_source_outside_target_rows_sha256": canonical["pre_source_outside_target_rows_sha256"],
        "historical_pre_source_lot_replay_or_carryin_used": False,
        "provisional_exclusion_reason_counts": provisional["reason_counts"], "canonical_exclusion_reason_counts": canonical["reason_counts"],
        "all_six_form_source_counts": before["source_form_counts"], "source_submission_count": before["source_submission_count"],
        "relevant_original_count": before["stream_corroborated_form4_count"],
        "asof_parent_count": before["as_of_parent_count"], "canonical_parent_count": after["as_of_parent_count"],
        "asof_future_parent_count": before["future_parent_count"], "canonical_future_parent_count": after["future_parent_count"],
        "asof_amendment_eligibility_not_evaluated_count": before["as_of_amendment_eligibility_not_evaluated_count"],
        "canonical_amendment_eligibility_not_evaluated_count": after["as_of_amendment_eligibility_not_evaluated_count"],
        "latest_prerequisite_knowledge_at_utc": context["latest_prerequisite_knowledge_at_utc"],
        "events_silently_dropped_or_delayed": False,
        "provisional_uses_same_canonical_reference_for_diagnostic_comparison": True,
        "later_facts_admitted_as_tradeable_moo_features": False,
        "old_full_study_manifest_seal_created": False, "full_pilot_original_admission_complete": False,
        "final_parent_and_event_inventory_registered": False, "actual_252_open_factor_intervals_verified": False,
        "both_earnings_diagnostics_evaluated": False, "order_engine_parity_verified": False,
        "source_or_reference_authenticity_verified_here": False, "rights_verified": False,
        "backtesting_ready": False, "outcome_access_authorized_here": False,
        "research_looks_consumed": 0, "qc_jobs": 0, "backtests": 0}
    raw = _raw({"summary": summary, "provisional": provisional, "canonical": canonical})
    _need(len(raw) <= MAX_OUTPUT_BYTES, "bounded_pilot_event_output_required")
    result = PilotEventComposition(raw, entry_source, first_open_source, _TOKEN)
    _BUILT[id(result)] = (weakref.ref(result, lambda _, key=id(result): _BUILT.pop(key, None)), raw)
    return result
