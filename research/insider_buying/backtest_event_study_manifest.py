"""Causal, source-bound literal-first-open event-study manifest composition.

This is NOT a backdating adapter for the separate daily-close score candidate.
Original acceptance batches update owner/security/transaction-date lots. Their
first USD 50,000 crossing schedules the next regular open; only additions known
before that open enter its immutable snapshot. Later additions do not reset or
retrade the lot. Amendments suppress an issuer only if already public at entry,
not retroactively. Same-issuer/entry lots are merged before inference.

All reference, timing, classification and registration bytes are externally
anchored. Constructor hashes do not authenticate those inputs. No realized
outcome/execution price stream, file, network, QC job or execution interface is
accessed. Supplied prior PIT close/volume references are verified for stock
eligibility; that context is prerequisite reference data, not a study result.
"""
from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal, localcontext
import heapq
from itertools import chain
import json
import weakref

from data.hashing import canonical_json, hash_bytes, hash_payload
from data.financial_primitives import exact_decimal_sum
from research.insider_buying import backtest_evidence_pipeline as base
from research.insider_buying import backtest_registered_analysis as analysis
from research.insider_buying.backtest_event_clock import (
    classify_pit_common_equity, verify_common_equity_exceptions,
    verify_pit_stock_context, verify_pit_stock_context_v3, schedule_first_open,
)
from research.insider_buying.backtest_source_stream import (
    StreamSourceEvidence, validate_stream_source_evidence,
)


VERSION = "insider-source-causal-firstopen-manifest-v1"
ZERO_WINDOW_VERSION = "insider-source-causal-firstopen-zero-window-v1"
EVENT_POPULATION_POLICY = "causal-owner-security-transaction-date-first50k-crossing-firstopen-snapshot-no-late-reset-issuer-entrydate-merge-v1"
PRIMARY_SEASONING_EXCLUSION = "primary_factor_calibration_listing_seasoning_below_253_sessions"
MAX_REFERENCE_BYTES = analysis.MAX_BYTES
MAX_REFERENCE_MANIFEST_BYTES = 512 * 1024
MAX_ENTRY_REFERENCE_BYTES = 128 * 1024 * 1024
MAX_TOTAL_REFERENCE_BYTES = 128 * 1024 * 1024 * 1024
MAX_LOTS = 500_000
MAX_EVENTS = 20_000
MAX_OUTPUT_BYTES = 128 * 1024 * 1024
_TOKEN = object()
_BUILT: dict[int, tuple[weakref.ReferenceType, bytes]] = {}


class EventStudyManifestError(ValueError):
    """A source-bound causal event or its supplied reference scope refused."""


def _need(ok: bool, why: str) -> None:
    if not ok:
        raise EventStudyManifestError("REFUSED: " + why)


@dataclass(frozen=True, slots=True)
class EventStudyManifestTrustRoots:
    """Externally established source/reference/application-code anchors."""

    trust_scope: str
    source_population_sha256: str
    security_master_sha256: str
    calendar_sha256: str
    common_equity_exceptions_sha256: str
    entry_reference_sha256: str
    registration_sha256: str
    analysis_implementation_sha256: str

    def __post_init__(self):
        self.to_payload()

    def to_payload(self) -> dict:
        _need(type(self) is EventStudyManifestTrustRoots and type(self.trust_scope) is str
              and self.trust_scope in {"fixture", "production"}, "exact source/reference roots required")
        return {"trust_scope": self.trust_scope, **{name: base._sha(getattr(self, name)) for name in (
            "source_population_sha256", "security_master_sha256", "calendar_sha256",
            "common_equity_exceptions_sha256", "entry_reference_sha256", "registration_sha256",
            "analysis_implementation_sha256")}}


@dataclass(frozen=True, slots=True, weakref_slot=True)
class EntryReferenceRecord:
    """One externally pinned complete-universe entry reference byte image."""

    raw_bytes: bytes = field(repr=False)

    def __post_init__(self):
        _need(type(self) is EntryReferenceRecord and type(self.raw_bytes) is bytes
              and 0 < len(self.raw_bytes) <= MAX_ENTRY_REFERENCE_BYTES,
              "entry reference record exceeds its individual byte bound")


@dataclass(frozen=True, slots=True, weakref_slot=True)
class SourceEventStudyManifest:
    _bytes: bytes = field(repr=False)
    _token: object = field(repr=False, compare=False)

    def _body(self) -> dict:
        registration = _BUILT.get(id(self))
        _need(type(self) is SourceEventStudyManifest and self._token is _TOKEN
              and type(self._bytes) is bytes and registration is not None
              and registration[0]() is self and registration[1] == self._bytes,
              "causal source manifest reconstructed or altered")
        return json.loads(self._bytes)

    def to_payload(self) -> dict:
        return self._body()["summary"]

    def manifest_bytes(self) -> bytes:
        return analysis.canonical_bytes(self._body()["manifest"])

    def events(self) -> list[dict]:
        return self._body()["manifest"]["events"]

    def event_lineage(self) -> list[dict]:
        return self._body()["lineage"]

    def entry_reference_facts(self) -> list[dict]:
        """Compact sealed entry prerequisites, including exact latest knowledge.

        The first-open manifest accepts facts strictly before entry. A later
        execution candidate with an earlier proposal cutoff must independently
        compare that cutoff with this timestamp, not the filing timestamp.
        """
        return self._body()["entry_references"]

    @property
    def sha256(self):
        self._body()
        return hash_bytes(self._bytes)


def validate_source_event_study_manifest(value: SourceEventStudyManifest) -> dict:
    _need(type(value) is SourceEventStudyManifest, "exact causal source manifest required")
    return value.to_payload()


def _seal_validated_manifest(body: dict, *, max_bytes: int = MAX_OUTPUT_BYTES) -> SourceEventStudyManifest:
    """Private shared terminus for fully validated source/collection factories.

    This is deliberately not a public payload construction/admission API.
    """
    raw = canonical_json(body).encode("utf-8")
    _need(type(max_bytes) is int and 0 < max_bytes <= 256 * 1024 * 1024
          and len(raw) <= max_bytes, "causal manifest envelope exceeds finite byte bound")
    result = SourceEventStudyManifest(raw, _TOKEN)
    _BUILT[id(result)] = (weakref.ref(result, lambda _, key=id(result): _BUILT.pop(key, None)), raw)
    return result


def _reference(raw: bytes, roots: EventStudyManifestTrustRoots, mappings: list[dict],
               calendar: bytes, sessions: list[str], opens: list, closes: list,
               entry_reference_records: Iterator[EntryReferenceRecord] | None) -> tuple[dict, dict, dict]:
    _need(type(raw) is bytes and 0 < len(raw) <= MAX_REFERENCE_BYTES,
          "entry reference bytes exceed finite bound")
    body = analysis._decode(raw, roots.entry_reference_sha256)
    analysis._fields(body, {"schema", "trust_scope", "calendar_sha256", "security_master_sha256",
                           "event_population_policy", "eligible_control_security_ids", "entries"}, "entry reference")
    streaming = body["schema"] == "insider-event-entry-pit-reference-stream-v2"
    _need(body["schema"] in {"insider-event-entry-pit-reference-v1", "insider-event-entry-pit-reference-stream-v2"}
          and body["trust_scope"] == roots.trust_scope
          and body["calendar_sha256"] == roots.calendar_sha256
          and body["security_master_sha256"] == roots.security_master_sha256
          and body["event_population_policy"] == EVENT_POPULATION_POLICY, "entry reference scope/root/policy differs")
    controls = body["eligible_control_security_ids"]
    _need(type(controls) is list and 3 <= len(controls) <= analysis.MAX_POOL
          and controls == sorted(set(controls)), "complete control security inventory absent/duplicate/unbounded")
    for sid in controls:
        analysis._id(sid)
    all_master_sids = tuple(item["qc_symbol_id"] for item in mappings)
    _need(set(controls) <= set(all_master_sids), "control security is outside complete supplied US universe")
    records = body["entries"]
    _need(type(records) is list and 1 <= len(records) <= 1250, "entry reference date population absent/unbounded")
    if streaming:
        _need(len(raw) <= MAX_REFERENCE_MANIFEST_BYTES and isinstance(entry_reference_records, Iterator)
              and iter(entry_reference_records) is entry_reference_records,
              "streamed references require a small manifest and one-pass record iterator")
    else:
        _need(entry_reference_records is None, "bounded nested reference cannot substitute a record iterator")
    previous = None
    verified = {}
    total_reference_bytes = 0
    for descriptor in records:
        if streaming:
            analysis._fields(descriptor, {"entry_session", "reference_sha256", "reference_bytes"}, "entry reference descriptor")
            base._sha(descriptor["reference_sha256"])
            _need(type(descriptor["reference_bytes"]) is int
                  and 0 < descriptor["reference_bytes"] <= MAX_ENTRY_REFERENCE_BYTES,
                  "entry descriptor byte count differs")
            try:
                record = next(entry_reference_records)
            except StopIteration as exc:
                raise EventStudyManifestError("REFUSED: entry reference record is missing") from exc
            _need(type(record) is EntryReferenceRecord, "entry stream contains a non-reference record")
            record.__post_init__()
            reference_blob = record.raw_bytes
            _need(len(reference_blob) == descriptor["reference_bytes"]
                  and hash_bytes(reference_blob) == descriptor["reference_sha256"],
                  "entry record differs from externally pinned descriptor")
            total_reference_bytes += len(reference_blob)
            _need(total_reference_bytes <= MAX_TOTAL_REFERENCE_BYTES, "aggregate entry reference bytes exceed their bound")
            try:
                entry = json.loads(reference_blob, object_pairs_hook=analysis._pairs,
                                   parse_constant=analysis._nonfinite)
            except (ValueError, UnicodeError, RecursionError) as exc:
                raise EventStudyManifestError("REFUSED: malformed streamed entry reference") from exc
            analysis._fields(entry, {"schema", "trust_scope", "entry_session", "knowledge_at_utc", "regime",
                                    "stock_context", "stock_context_sha256", "earnings_rows"}, "streamed entry record")
            _need(entry["schema"] == "insider-event-entry-pit-reference-record-v2"
                  and entry["trust_scope"] == roots.trust_scope
                  and entry["entry_session"] == descriptor["entry_session"]
                  and analysis.canonical_bytes(entry) == reference_blob,
                  "entry record schema, trust scope, date or canonical encoding differs")
            reference_digest = descriptor["reference_sha256"]
            entry = {key: value for key, value in entry.items() if key not in {"schema", "trust_scope"}}
        else:
            entry = descriptor
            reference_digest = hash_payload(entry)
            total_reference_bytes += len(canonical_json(entry).encode("utf-8"))
        analysis._fields(entry, {"entry_session", "knowledge_at_utc", "regime", "stock_context",
                                "stock_context_sha256", "earnings_rows"}, "entry PIT reference")
        day = entry["entry_session"]
        _need(type(day) is str and day in sessions and (previous is None or previous < day),
              "entry reference dates absent, duplicate or reordered")
        previous = day
        index = sessions.index(day)
        _need(index >= 253 and index + 60 < len(sessions), "entry reference lacks 252 prior / 60 future sessions")
        # The externally bound master may include later-known/listed securities
        # in this multi-entry scope. They cannot enter an earlier entry cohort
        # or require invented prelisting context. Derive the complete current
        # cohort from exact knowledge/interval facts, not future study rows.
        all_sids = tuple(item["qc_symbol_id"] for item in mappings
                         if base._utc(item["knowledge_at_utc"]) < opens[index]
                         and item["mapping_first_session"] <= day < item["mapping_last_session"])
        _need(all_sids, "entry cohort has no known mapped security")
        all_sid_set = set(all_sids)
        _need(base._utc(entry["knowledge_at_utc"]) < opens[index]
              and type(entry["regime"]) is str and entry["regime"] in {"bull", "bear", "sideways"},
              "regime/reference metadata not known strictly before entry")
        context_bytes = canonical_json(entry["stock_context"]).encode("utf-8")
        _need(hash_bytes(context_bytes) == entry["stock_context_sha256"], "stock context contents differ from pinned entry hash")
        v3_context = entry["stock_context"].get("schema") == "insider-stock-context-v3"
        _need(roots.trust_scope == "fixture" or v3_context,
              "production causal reference requires explicit v3 first-listing provenance")
        context_validator = verify_pit_stock_context_v3 if v3_context else verify_pit_stock_context
        context = context_validator(context_raw=context_bytes, context_sha256=entry["stock_context_sha256"],
            trust_scope=roots.trust_scope, calendar_raw=calendar, calendar_sha256=roots.calendar_sha256,
            decision_session=day, decision_cutoff_utc=base._utc_text(opens[index]), expected_security_ids=all_sids)
        # Daily-close context allows cutoff equality. This first-open candidate
        # requires every eligibility fact strictly BEFORE the opening instant.
        bar = None  # An explicit v3 first-day listing can have no preceding bar.
        for stock in entry["stock_context"]["rows"]:
            for bar in stock["history"]:
                _need(base._utc(bar["knowledge_at_utc"]) < opens[index], "context fact is simultaneous with or after entry")
        seasoning_minimum = analysis.frozen_analysis_policy()["minimum_prior_regular_listing_sessions"]
        _need(type(seasoning_minimum) is int and seasoning_minimum == 253,
              "pre-outcome primary listing seasoning policy differs")
        seasoning_exclusions = {item["qc_symbol_id"] for item in context["rows"]
            if v3_context and item["prior_listing_session_lower_bound"] < seasoning_minimum}
        context_exclusion_counts = {}
        for item in context["rows"]:
            for reason in item["exclusion_reasons"]:
                context_exclusion_counts[reason] = context_exclusion_counts.get(reason, 0) + 1
        if seasoning_exclusions:
            context_exclusion_counts[PRIMARY_SEASONING_EXCLUSION] = len(seasoning_exclusions)
        observed_eligible = {item["qc_symbol_id"] for item in context["rows"]
                             if item["eligible"] and item["qc_symbol_id"] not in seasoning_exclusions}
        # Reuse the already bounded master SID strings across dates. The
        # compact reference receipt retains no historical bar arrays.
        eligible = {sid for sid in all_sids if sid in observed_eligible}
        _need(3 <= len(eligible) <= analysis.MAX_POOL,
              "complete eligible per-entry control cohort is absent or exceeds its finite bound")
        earnings_rows = entry["earnings_rows"]
        _need(type(earnings_rows) is list and len(earnings_rows) == len(all_sids), "complete earnings reference universe differs")
        earnings = {}
        for sid, row in zip(all_sids, earnings_rows, strict=True):
            analysis._fields(row, {"qc_symbol_id", "known_earnings_sessions", "knowledge_at_utc"}, "earnings reference")
            _need(row["qc_symbol_id"] == sid and base._utc(row["knowledge_at_utc"]) < opens[index],
                  "earnings reference identity/knowledge differs")
            dates = row["known_earnings_sessions"]
            if v3_context and sid not in eligible and type(dates) is list and not dates:
                earnings[sid] = None
                reason = "known_earnings_unavailable_for_excluded_security"
                context_exclusion_counts[reason] = context_exclusion_counts.get(reason, 0) + 1
                continue
            _need(type(dates) is list and 1 <= len(dates) <= 32 and dates == sorted(set(dates))
                  and all(type(value) is str and value in sessions for value in dates),
                  "earnings calendar missing, duplicate or outside verified calendar")
            offsets = [sessions.index(value) - index for value in dates]
            distance = min(offsets, key=lambda value: (abs(value), value))
            _need(abs(distance) <= 1000, "nearest known earnings distance outside contract")
            earnings[sid] = distance
        latest_knowledge = max(chain(
            (base._utc(entry["knowledge_at_utc"]),),
            (base._utc(item["knowledge_at_utc"]) for item in mappings
             if item["qc_symbol_id"] in all_sid_set),
            (base._utc(item["knowledge_at_utc"]) for item in earnings_rows),
            (base._utc(bar["knowledge_at_utc"]) for stock in entry["stock_context"]["rows"]
             for bar in stock["history"])))
        if "latest_prerequisite_knowledge_at_utc" in context:
            latest_knowledge = max(latest_knowledge, base._utc(context["latest_prerequisite_knowledge_at_utc"]))
        verified[day] = {"eligible_security_ids": eligible, "earnings": earnings,
                         "regime": entry["regime"], "reference_sha256": reference_digest,
                         "stock_context_profile": context["kind"],
                         "eligibility_exclusion_reason_counts": dict(sorted(context_exclusion_counts.items())),
                         "primary_seasoning_excluded_security_ids": sorted(seasoning_exclusions),
                         "prior_listing_session_lower_bound_by_security_id": {
                             item["qc_symbol_id"]: item["prior_listing_session_lower_bound"]
                             for item in context["rows"]} if v3_context else None,
                         "latest_prerequisite_knowledge_at_utc": base._utc_text(latest_knowledge)}
        if streaming:
            del record, reference_blob, entry, context_bytes, context, observed_eligible
            del stock, bar, row, earnings_rows
    if streaming:
        try:
            next(entry_reference_records)
        except StopIteration:
            pass
        else:
            raise EventStudyManifestError("REFUSED: unaccounted extra entry reference record")
    eligible_union = sorted(set().union(*(row["eligible_security_ids"] for row in verified.values())))
    _need(controls == eligible_union, "reference control inventory is not the complete per-entry eligible PIT universe union")
    return body, verified, {"mode": "streaming_entry_records" if streaming else "bounded_nested_reference",
                            "entry_records_verified": len(records), "total_reference_bytes": total_reference_bytes,
                            "raw_records_retained": 0}


def build_source_event_study_manifest(
    *, source_evidence: StreamSourceEvidence, security_master: bytes, calendar: bytes,
    common_equity_exceptions: bytes, entry_reference: bytes, registration: bytes,
    trust_roots: EventStudyManifestTrustRoots, event_first_session: str, event_last_session: str,
    entry_reference_records: Iterator[EntryReferenceRecord] | None = None,
    allow_zero_event_window: bool = False,
) -> SourceEventStudyManifest:
    """Build a causal nonempty source-derived manifest before outcome access.

    The selected event window is explicit and contained in the complete source
    scope. A potentially eligible transaction preceding that scope refuses:
    earlier reports of the same economic lot cannot be manufactured or assumed
    absent. Missing context is not liquidity zero or an event exclusion.
    """
    _need(type(trust_roots) is EventStudyManifestTrustRoots, "exact event-study roots required")
    _need(type(allow_zero_event_window) is bool, "zero-window mode requires an exact explicit boolean")
    roots = trust_roots.to_payload()
    source = validate_stream_source_evidence(source_evidence)
    scope = trust_roots.trust_scope
    _need(source["trust_scope"] == scope
          and source["population_manifest_sha256"] == trust_roots.source_population_sha256
          and source["relevant_form4_identity_complete"], "source population/epoch differs or incomplete")
    master = base._artifact(security_master, trust_roots.security_master_sha256, "insider-backtest-security-master-v1", scope)
    cal = base._artifact(calendar, trust_roots.calendar_sha256, "insider-backtest-calendar-v1", scope)
    sessions, opens, closes, _ = base._calendar(cal)
    _need(len(sessions) >= 314 and event_first_session in sessions and event_last_session in sessions
          and source["source_start"] <= event_first_session <= event_last_session <= source["source_end"],
          "event study window exceeds complete source/calendar scope")
    _need(opens[0].date().isoformat() < source["source_start"], "calendar cannot bracket earliest source scope")
    source_cutoff = base._utc(source["decision_cutoff_utc"])
    _need(opens[sessions.index(event_last_session)] <= source_cutoff, "event population not yet fully public at source cutoff")
    mappings = base._mappings(master, sessions, source_cutoff, set(source["as_of_issuer_ciks"]))
    verify_common_equity_exceptions(raw=common_equity_exceptions, digest=trust_roots.common_equity_exceptions_sha256, scope=scope)
    reference, entry_contexts, reference_receipt = _reference(
        entry_reference, trust_roots, mappings, calendar, sessions, opens, closes, entry_reference_records)
    registered = analysis._decode(registration, trust_roots.registration_sha256)
    # A separately sealed zero-event coverage window cannot be passed through
    # the analysis validator's deliberately nonempty manifest contract. It
    # still requires the identical complete preregistration admission here.
    analysis._fields(registered, {"schema", "trust_scope", "registered_look_id", "candidate_id", "policy", "analysis_plan",
        "registered_at_utc", "first_outcome_access_utc", "implementation_sha256", "source_manifest_sha256",
        "security_master_sha256", "calendar_sha256", "outcome_vintage_sha256", "rights_sha256",
        "prior_variance_calibration_sha256"}, "causal registration")
    _need(registered["schema"] == "insider-stock-analysis-registration-v1"
          and registered["implementation_sha256"] == trust_roots.analysis_implementation_sha256
          and analysis.canonical_bytes(registered["analysis_plan"]) == analysis.canonical_bytes(
              analysis.analysis_plan_descriptors(implementation_sha256=trust_roots.analysis_implementation_sha256))
          and analysis.canonical_bytes(registered["policy"]) == analysis.canonical_bytes(analysis.frozen_analysis_policy())
          and analysis._utc(registered["registered_at_utc"]) < analysis._utc(registered["first_outcome_access_utc"]),
          "causal registration methods, implementation, policy or timing differs")
    for field in registered:
        if field.endswith("sha256"):
            analysis._digest(registered[field])
    analysis._id(registered["registered_look_id"])
    analysis._id(registered["candidate_id"])
    _need(registered.get("trust_scope") == scope
          and registered.get("source_manifest_sha256") == trust_roots.source_population_sha256
          and registered.get("security_master_sha256") == trust_roots.security_master_sha256
          and registered.get("calendar_sha256") == hash_bytes(analysis.canonical_bytes(cal["sessions"])),
          "registration source/master/full-calendar binding differs")
    _need(registered.get("policy", {}).get("event_population") == EVENT_POPULATION_POLICY,
          "registration does not freeze the causal first-threshold event population")
    parent_rows = {}
    for row in source_evidence.transaction_rows():
        parent_rows.setdefault(row["accession_number"], []).append(row)
    facts = sorted(source_evidence.parent_facts(), key=lambda row: (row["accepted_at_utc"], row["period"], row["source_record_ordinal"], row["accession_number"]))
    mapping_index = {}
    for mapping in mappings:
        mapping_index.setdefault((mapping["issuer_cik"], mapping["security_title"], mapping["ticker"]), []).append(mapping)
    excluded_issuers = {row["issuer_cik"] for row in master["source_exclusions"]}
    lots, pending, amended, grouped_entries, exclusion_counts = {}, [], set(), {}, {}
    late_members = ordinary_overrides = 0

    def exclude(reason, count=1):
        exclusion_counts[reason] = exclusion_counts.get(reason, 0) + count

    def finalize(until):
        while pending and pending[0][0] <= until:
            _, key = heapq.heappop(pending)
            lot = lots[key]
            lot["consumed"] = True
            entry_index = lot["entry_index"]
            day = sessions[entry_index]
            if not event_first_session <= day <= event_last_session:
                exclude("first_threshold_entry_outside_registered_event_window")
                continue
            if lot["issuer_cik"] in amended:
                exclude("amendment_already_public_before_first_entry")
                continue
            _need(day in entry_contexts, "required first-open PIT entry reference is missing")
            context = entry_contexts[day]
            mapping = lot["mapping"]
            if mapping["qc_symbol_id"] not in context["eligible_security_ids"]:
                exclude(PRIMARY_SEASONING_EXCLUSION if mapping["qc_symbol_id"] in context["primary_seasoning_excluded_security_ids"]
                        else "failed_first_open_stock_price_liquidity_context")
                continue
            _need(entry_index >= 253 and entry_index + 60 < len(sessions), "event lacks full 252 prior / 60 future context")
            _need(mapping["mapping_first_session"] <= day
                  and sessions[entry_index + 60] < mapping["mapping_last_session"], "PIT security mapping lacks full descriptive horizon")
            value = lot["total_value"]
            _need(value >= Decimal(50_000), "first threshold lot lost its exact value")
            verified_clock = schedule_first_open(available_at_utc=lot["available_at_utc"], calendar_raw=calendar,
                calendar_sha256=trust_roots.calendar_sha256, trust_scope=scope)
            _need(verified_clock["entry_session"] == day, "late member altered immutable first entry")
            payload = {"owner_cik": key[0], "qc_symbol_id": key[1], "transaction_date": key[2],
                       "issuer_cik": lot["issuer_cik"], "purchase_value_usd": str(value),
                       "available_at_utc": lot["available_at_utc"], "member_event_ids": sorted(lot["member_ids"]),
                       "entry_session": day, "first_threshold_at_utc": lot["first_threshold_at_utc"]}
            payload["lot_sha256"] = hash_payload(payload)
            grouped_entries.setdefault((lot["issuer_cik"], day), []).append(payload)
            _need(len(grouped_entries) <= MAX_EVENTS, "causal event population exceeds finite bound")

    for fact in facts:
        accepted = base._utc(fact["accepted_at_utc"])
        finalize(accepted)
        if fact["form_type"] == "4/A":
            amended.add(fact["issuer_cik"])
            exclude("known_amendment_identity_retained_eligibility_not_evaluated")
            continue
        for row in parent_rows.get(fact["accession_number"], ()):
            outcomes = row["provisional_outcomes"]
            if row["issuer_cik"] in excluded_issuers:
                exclude("noneligible_source_security")
                continue
            if len(row["reporting_owners"]) != 1:
                exclude("joint_or_missing_reporting_owner")
                continue
            if outcomes not in (["eligible_for_lot_aggregation"], ["exclude_non_common_stock"]):
                for outcome in outcomes:
                    exclude(outcome)
                continue
            _need(source["source_start"] <= row["transaction_date"], "economic lot transaction precedes complete historical source scope")
            _need(row["transaction_date"] <= accepted.astimezone(base.ZoneInfo("America/New_York")).date().isoformat(),
                  "transaction date follows public availability")
            candidates = mapping_index.get((row["issuer_cik"], row["security_title_raw"], row["issuer_symbol_raw"]), ())
            candidates = [item for item in candidates if item["mapping_first_session"] <= row["transaction_date"] < item["mapping_last_session"]
                          and base._utc(item["knowledge_at_utc"]) <= accepted]
            _need(len(candidates) == 1, "missing/future/ambiguous exact transaction security mapping")
            mapping = candidates[0]
            classification = classify_pit_common_equity(transaction={"event_id": row["event_id"], "issuer_cik": row["issuer_cik"],
                "security_title_raw": row["security_title_raw"], "transaction_date": row["transaction_date"], "outcomes": outcomes},
                mapping={key: value for key, value in mapping.items() if key != "ticker"},
                exception_dictionary_raw=common_equity_exceptions,
                exception_dictionary_sha256=trust_roots.common_equity_exceptions_sha256, trust_scope=scope,
                available_at_utc=row["accepted_at_utc"])
            if not classification["eligible_for_lot_aggregation"]:
                exclude("unresolved_ordinary_share_classification")
                continue
            ordinary_overrides += classification["ordinary_share_exception_applied"]
            key = row["reporting_owners"][0]["owner_cik"], mapping["qc_symbol_id"], row["transaction_date"]
            lot = lots.setdefault(key, {"total_value": Decimal(0), "member_ids": [], "issuer_cik": row["issuer_cik"],
                "mapping": mapping, "available_at_utc": row["accepted_at_utc"], "consumed": False, "entry_index": None})
            _need(len(lots) <= MAX_LOTS, "economic lot population exceeds finite bound")
            if lot["consumed"]:
                late_members += 1
                continue
            lot["total_value"] = exact_decimal_sum(
                (lot["total_value"], Decimal(row["purchase_value_usd"])),
                name="causal pre-entry cumulative purchase value")
            lot["member_ids"].append(row["event_id"])
            lot["available_at_utc"] = max(lot["available_at_utc"], row["accepted_at_utc"])
            value = lot["total_value"]
            if lot["entry_index"] is None and value >= Decimal(50_000):
                entry_index = bisect_right(opens, accepted)
                _need(0 < entry_index < len(sessions), "first-threshold calendar open is not bracketed")
                lot["entry_index"], lot["first_threshold_at_utc"] = entry_index, row["accepted_at_utc"]
                heapq.heappush(pending, (opens[entry_index], key))
    finalize(source_cutoff)
    if not grouped_entries:
        _need(allow_zero_event_window, "no nonempty causal first-open event population")
        expected_zero_dates = {day for day in sessions if event_first_session <= day <= event_last_session}
        _need(set(entry_contexts) == expected_zero_dates,
              "zero-event coverage requires complete per-session PIT reference admission")
    events, lineage = [], []
    base.formula._require_frozen_policy()
    for (issuer, day), member_lots in sorted(grouped_entries.items(), key=lambda item: (item[0][1], item[0][0])):
        sids = {lot["qc_symbol_id"] for lot in member_lots}
        _need(len(sids) == 1, "multiple share classes inflate one issuer/entry event")
        sid = next(iter(sids))
        context = entry_contexts[day]
        with localcontext(base.formula._new_decimal_context()):
            score = sum((base.formula._event_formula(Decimal(lot["purchase_value_usd"]), 0)[2]
                         for lot in member_lots), Decimal(0))
        available = max(lot["available_at_utc"] for lot in member_lots)
        payload = {"event_population_policy": EVENT_POPULATION_POLICY, "issuer_cik": issuer, "security_id": sid,
                   "entry_session": day, "lots": member_lots, "reference_sha256": context["reference_sha256"],
                   "source_population_sha256": trust_roots.source_population_sha256,
                   "security_master_sha256": trust_roots.security_master_sha256,
                   "common_equity_exceptions_sha256": trust_roots.common_equity_exceptions_sha256}
        digest = hash_payload(payload)
        index = sessions.index(day)
        event = {"signal_id": digest[:32], "issuer_id": issuer, "security_id": sid, "available_at_utc": available,
                 "entry_session": day, "exit_session": sessions[index + 20], "source_event_sha256": digest,
                 "buyer_ids": sorted({lot["owner_cik"] for lot in member_lots}), "score": str(score),
                 "earnings_distance_sessions": context["earnings"][sid], "regime": context["regime"]}
        events.append(event)
        lineage.append({"signal_id": event["signal_id"], "payload": payload, "source_event_sha256": digest})
    per_entry_controls = {day: sorted(entry_contexts[day]["eligible_security_ids"])
                          for day in sorted({event["entry_session"] for event in events})}
    complete_control_union = sorted(set().union(*(set(ids) for ids in per_entry_controls.values())))
    manifest = {"schema": "insider-stock-event-study-manifest-v2", "trust_scope": scope,
        "registration_sha256": trust_roots.registration_sha256,
        "source_manifest_sha256": trust_roots.source_population_sha256,
        "security_master_sha256": trust_roots.security_master_sha256,
        "calendar_sha256": registered["calendar_sha256"], "outcome_vintage_sha256": registered["outcome_vintage_sha256"],
        "sessions": cal["sessions"], "eligible_control_security_ids": complete_control_union,
        "eligible_control_security_ids_by_entry_session": per_entry_controls, "events": events}
    manifest_raw = analysis.canonical_bytes(manifest)
    if events:
        analysis.verify_registered_analysis_manifest(registration_raw=registration, manifest_raw=manifest_raw,
            expected_registration_sha256=trust_roots.registration_sha256, expected_manifest_sha256=hash_bytes(manifest_raw),
            expected_implementation_sha256=trust_roots.analysis_implementation_sha256)
    summary = {"kind": VERSION if events else ZERO_WINDOW_VERSION, **roots, "event_population_policy": EVENT_POPULATION_POLICY,
        "source_stream_sha256": source_evidence.sha256, "source_submission_count": source["source_submission_count"],
        "stream_corroborated_form4_count": source["stream_corroborated_form4_count"],
        "source_window_start": source["source_start"], "source_window_end": source["source_end"],
        "event_first_session": event_first_session, "event_last_session": event_last_session,
        "entry_reference_receipt": reference_receipt,
        "manifest_sha256": hash_bytes(manifest_raw), "event_count": len(events),
        "standalone_analysis_population_nonempty": bool(events),
        "zero_event_window_complete": not events,
        "economic_lot_count": sum(len(row["payload"]["lots"]) for row in lineage),
        "ordinary_share_exception_count": ordinary_overrides, "late_members_not_reset_or_retraded": late_members,
        "minimum_prior_regular_listing_sessions": analysis.frozen_analysis_policy()["minimum_prior_regular_listing_sessions"],
        "fixture_v2_context_compatibility_not_listing_proof": any(
            item["stock_context_profile"] == "insider-pit-stock-context-result-v2" for item in entry_contexts.values()),
        "pending_first_opens_after_source_cutoff": len(pending),
        "below_threshold_lot_count": sum(lot["entry_index"] is None for lot in lots.values()),
        "excluded_reason_counts": dict(sorted(exclusion_counts.items())), "literal_first_open_after_acceptance": True,
        "daily_close_candidate_backdated": False, "source_authentication_performed": False,
        "rights_authenticated_here": False, "look_authority": False, "backtesting_ready": False,
        "qc_jobs": 0, "research_looks": 0, "outcome_rows_read": 0, "execution_performed": False}
    compact_references = [{"entry_session": day,
        "eligible_security_ids": sorted(entry_contexts[day]["eligible_security_ids"]),
        "earnings_distance_sessions_by_security_id": entry_contexts[day]["earnings"],
        "regime": entry_contexts[day]["regime"], "reference_sha256": entry_contexts[day]["reference_sha256"],
        "stock_context_profile": entry_contexts[day]["stock_context_profile"],
        "eligibility_exclusion_reason_counts": entry_contexts[day]["eligibility_exclusion_reason_counts"],
        "primary_seasoning_excluded_security_ids": entry_contexts[day]["primary_seasoning_excluded_security_ids"],
        "prior_listing_session_lower_bound_by_security_id": entry_contexts[day]["prior_listing_session_lower_bound_by_security_id"],
        "latest_prerequisite_knowledge_at_utc": entry_contexts[day]["latest_prerequisite_knowledge_at_utc"]}
        for day in sorted(per_entry_controls if events else entry_contexts)]
    return _seal_validated_manifest({"summary": summary, "manifest": manifest, "lineage": lineage,
                                     "entry_references": compact_references})


__all__ = ["EventStudyManifestError", "EventStudyManifestTrustRoots", "SourceEventStudyManifest",
           "EntryReferenceRecord", "build_source_event_study_manifest", "validate_source_event_study_manifest", "EVENT_POPULATION_POLICY"]
