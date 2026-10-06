"""Versioned full-parent/cross-quarter source to daily-close stock pipeline.

Original images are verified incrementally by the source-stream factory. This
consumer admits compact as-of transactions, independently verifies the actual
30-session calendar window, PIT security exceptions and complete price context,
and derives the frozen stock mathematics. It does not change the old bounded
candidate or mislabel daily-close signals as first-open event-study signals.
No files, outcome rows, QC jobs or external services are accessed here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, localcontext
import json
import weakref

from data.financial_primitives import exact_decimal_sum
from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying import backtest_evidence_pipeline as base
from research.insider_buying.backtest_event_clock import classify_pit_common_equity, verify_pit_stock_context, verify_common_equity_exceptions
from research.insider_buying.backtest_source_stream import StreamSourceEvidence, validate_stream_source_evidence


VERSION = "insider-stock-stream-pipeline-v2"
MAX_GROUPS = 500_000
_TOKEN = object()
_BUILT: dict[int, tuple[weakref.ReferenceType, bytes]] = {}


@dataclass(frozen=True, slots=True)
class StreamEvidenceTrustRoots:
    """Externally established roots; never self-authentication by artifact hash."""

    trust_scope: str
    source_manifest_sha256: str
    security_master_sha256: str
    calendar_sha256: str
    authorization_sha256: str
    common_equity_exceptions_sha256: str
    stock_context_sha256: str

    def __post_init__(self):
        self.to_payload()

    def to_payload(self) -> dict:
        if type(self) is not StreamEvidenceTrustRoots:
            base._refuse("exact streaming roots required")
        base.EvidenceTrustRoots(self.trust_scope, self.source_manifest_sha256, self.security_master_sha256,
                               self.calendar_sha256, self.authorization_sha256).to_payload()
        return {"trust_scope": self.trust_scope, **{name: base._sha(getattr(self, name)) for name in (
            "source_manifest_sha256", "security_master_sha256", "calendar_sha256", "authorization_sha256",
            "common_equity_exceptions_sha256", "stock_context_sha256")}}


@dataclass(frozen=True, slots=True, weakref_slot=True)
class StreamStockPipeline:
    _bytes: bytes = field(repr=False)
    _token: object = field(repr=False, compare=False)

    def _body(self):
        registration = _BUILT.get(id(self))
        if (type(self) is not StreamStockPipeline or type(self._bytes) is not bytes
                or self._token is not _TOKEN or registration is None
                or registration[0]() is not self or registration[1] != self._bytes):
            base._refuse("stream pipeline reconstructed or altered")
        return json.loads(self._bytes)

    def to_payload(self):
        return self._body()["summary"]

    def scored_rows(self):
        return self._body()["scored_rows"]

    def admitted_events(self):
        return self._body()["events"]

    def signals(self):
        return self._body()["manifest"]["signals"]

    def signal_manifest_bytes(self):
        return canonical_json(self._body()["manifest"]).encode("utf-8")

    @property
    def sha256(self):
        self._body()
        return hash_bytes(self._bytes)


def validate_stream_stock_pipeline(value: StreamStockPipeline):
    if type(value) is not StreamStockPipeline:
        base._refuse("exact sealed stream stock pipeline required")
    return value.to_payload()


def build_stream_stock_pipeline(*, source_evidence: StreamSourceEvidence, source_manifest: bytes,
                                security_master: bytes, calendar: bytes, authorization: bytes,
                                common_equity_exceptions: bytes, stock_context: bytes,
                                trust_roots: StreamEvidenceTrustRoots) -> StreamStockPipeline:
    """Complete as-of universe, original lot lineage, named economic exclusions.

    The source population receipt must be factory-sealed. An externally anchored
    manifest commits every parent (including future identity-only records), not
    selected positive stocks. Only already-public facts are used economically.
    Actual source origin/PIT/rights authenticity remains the external caller's
    factual evidence responsibility, never supplied by this pure verifier.
    """
    if type(trust_roots) is not StreamEvidenceTrustRoots:
        base._refuse("exact streaming roots required")
    trust_roots.to_payload()
    source = validate_stream_source_evidence(source_evidence)
    scope = trust_roots.trust_scope
    population = base._artifact(source_manifest, trust_roots.source_manifest_sha256,
                                "insider-backtest-source-population-v2", scope)
    if (source["trust_scope"] != scope or source["population_manifest_sha256"] != trust_roots.source_manifest_sha256
            or not source["relevant_form4_identity_complete"]):
        base._refuse("source stream/population binding differs or incomplete")
    master = base._artifact(security_master, trust_roots.security_master_sha256,
                            "insider-backtest-security-master-v1", scope)
    cal = base._artifact(calendar, trust_roots.calendar_sha256, "insider-backtest-calendar-v1", scope)
    auth = base._artifact(authorization, trust_roots.authorization_sha256, "insider-backtest-authorization-v1", scope)
    sessions, opens, closes, calendar_hash = base._calendar(cal)
    old_roots = base.EvidenceTrustRoots(scope, trust_roots.source_manifest_sha256, trust_roots.security_master_sha256,
                                       trust_roots.calendar_sha256, trust_roots.authorization_sha256)
    auth = base._authorization(auth, old_roots, calendar_hash, sessions)
    decision_index = sessions.index(auth["decision_session"])
    if decision_index < 60:
        base._refuse("60-session verified stock context is unavailable")
    cutoff = closes[decision_index]
    lookback = sessions[decision_index - 30]
    if (source["decision_session"] != sessions[decision_index] or source["decision_cutoff_utc"] != base._utc_text(cutoff)
            or source["lookback_start_session"] != lookback
            or not source["source_start"] <= lookback <= sessions[decision_index] <= source["source_end"]):
        base._refuse("stream window does not equal the verified complete 30-session calendar window")
    mappings = base._mappings(master, sessions, cutoff, set(source["as_of_issuer_ciks"]))
    context = verify_pit_stock_context(context_raw=stock_context, context_sha256=trust_roots.stock_context_sha256,
                                      trust_scope=scope, calendar_raw=calendar, calendar_sha256=trust_roots.calendar_sha256,
                                      decision_session=sessions[decision_index], decision_cutoff_utc=base._utc_text(cutoff),
                                      expected_security_ids=tuple(item["qc_symbol_id"] for item in mappings))
    eligible_ids = {row["qc_symbol_id"] for row in context["rows"] if row["eligible"]}
    # Even with zero ordinary-share exceptions, verify the exact dictionary now;
    # a never-used invalid artifact cannot be represented as verified content.
    verify_common_equity_exceptions(raw=common_equity_exceptions, digest=trust_roots.common_equity_exceptions_sha256, scope=scope)
    entry, exit_day = sessions[decision_index + 1], sessions[decision_index + 21]
    for mapping in mappings:
        if not mapping["mapping_first_session"] <= sessions[decision_index] < entry < exit_day < mapping["mapping_last_session"]:
            base._refuse("PIT mapping does not cover complete frozen horizon")
    index = {}
    for item in mappings:
        index.setdefault((item["issuer_cik"], item["security_title"], item["ticker"]), []).append(item)
    excluded = {reason: sum(reason in row["exclusion_reasons"] for row in context["rows"])
                for reason in sorted({reason for row in context["rows"] for reason in row["exclusion_reasons"]})}
    amended = set(source["as_of_amended_issuers"])
    excluded_issuers = {item["issuer_cik"] for item in master["source_exclusions"]}
    grouped, decisions = {}, []
    for row in source_evidence.transaction_rows():
        outcomes = row["provisional_outcomes"]
        reason = None
        if row["issuer_cik"] in amended:
            reason = "known_unresolved_amended_issuer_family"
        elif row["issuer_cik"] in excluded_issuers:
            reason = "noneligible_source_security"
        elif len(row["reporting_owners"]) != 1:
            reason = "joint_or_missing_reporting_owner"
        elif outcomes not in (["eligible_for_lot_aggregation"], ["exclude_non_common_stock"]):
            for name in outcomes:
                excluded[name] = excluded.get(name, 0) + 1
            continue
        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1
            continue
        if row["transaction_date"] is None or row["transaction_date"] < source["source_start"]:
            base._refuse("complete economic lot requires the earlier source transaction context")
        candidates = index.get((row["issuer_cik"], row["security_title_raw"], row["issuer_symbol_raw"]), ())
        candidates = [item for item in candidates if item["mapping_first_session"] <= row["transaction_date"] < item["mapping_last_session"]
                      and base._utc(item["knowledge_at_utc"]) <= base._utc(row["accepted_at_utc"])]
        if len(candidates) != 1:
            base._refuse("missing, future or ambiguous exact transaction security mapping")
        mapping = candidates[0]
        decision = classify_pit_common_equity(transaction={"event_id": row["event_id"], "issuer_cik": row["issuer_cik"],
            "security_title_raw": row["security_title_raw"], "transaction_date": row["transaction_date"], "outcomes": outcomes},
            mapping={k: v for k, v in mapping.items() if k != "ticker"},
            exception_dictionary_raw=common_equity_exceptions,
            exception_dictionary_sha256=trust_roots.common_equity_exceptions_sha256,
            trust_scope=scope, available_at_utc=row["accepted_at_utc"])
        decisions.append(decision)
        if not decision["eligible_for_lot_aggregation"]:
            excluded["unresolved_ordinary_share_classification"] = excluded.get("unresolved_ordinary_share_classification", 0) + 1
            continue
        if mapping["qc_symbol_id"] not in eligible_ids:
            excluded["failed_stock_price_liquidity_context"] = excluded.get("failed_stock_price_liquidity_context", 0) + 1
            continue
        if row["transaction_date"] > base._utc(row["accepted_at_utc"]).astimezone(base.ZoneInfo("America/New_York")).date().isoformat():
            base._refuse("transaction date follows public availability")
        owner = row["reporting_owners"][0]["owner_cik"]
        key = owner, mapping["qc_symbol_id"], row["transaction_date"]
        group = grouped.setdefault(key, {"owner_cik": owner, "qc_symbol_id": key[1], "transaction_date": key[2],
                                         "values": [], "member_ids": [], "available": row["accepted_at_utc"]})
        group["values"].append(Decimal(row["purchase_value_usd"]))
        group["member_ids"].append(row["event_id"])
        group["available"] = max(group["available"], row["accepted_at_utc"])
        if len(grouped) > MAX_GROUPS:
            base._refuse("economic lot population exceeds its finite streaming bound")
    mappings = [item for item in mappings if item["qc_symbol_id"] in eligible_ids]
    if not mappings:
        base._refuse("no eligible full-context stock universe")
    by_sid = {item["qc_symbol_id"]: [] for item in mappings}
    events = []
    base.formula._require_frozen_policy(); base.normalization._require_frozen_policy()
    base.seed._require_frozen_policy(); base.cluster._require_frozen_policy()
    for key in sorted(grouped):
        group = grouped[key]
        value = exact_decimal_sum(group["values"], name="stream post-aggregation purchase value")
        instant = base._utc(group["available"])
        activation = next((n for n, closed in enumerate(closes) if closed >= instant), None)
        if activation is None or activation > decision_index:
            base._refuse("future lot at decision")
        age = decision_index - activation
        if value < Decimal(50_000) or age > 30:
            reason = "below_post_aggregation_threshold" if value < Decimal(50_000) else "outside_30_session_lookback"
            excluded[reason] = excluded.get(reason, 0) + 1
            continue
        size, fresh, score = base.formula._event_formula(value, age)
        event = {"owner_cik": key[0], "qc_symbol_id": key[1], "transaction_date": key[2], "purchase_value_usd": str(value),
                 "available_at_utc": group["available"], "activation_session": sessions[activation], "age_trading_days": age,
                 "member_event_ids": sorted(group["member_ids"]), "event_size": str(size), "freshness": str(fresh), "event_score": str(score)}
        event["event_sha256"] = hash_payload(event)
        events.append(event); by_sid[key[1]].append(event)
    with localcontext(base.formula._new_decimal_context()):
        scores = tuple(sum((Decimal(e["event_score"]) for e in by_sid[item["qc_symbol_id"]]), Decimal(0)) for item in mappings)
    computation = base.normalization._compute_normalization(scores)
    available = computation.outcome.value == "available"
    target_count = (len(mappings) + 9) // 10
    cutoff_score = sorted(computation.winsorized_values, reverse=True)[target_count - 1] if available else None
    seeds = [n for n, score in enumerate(scores) if cutoff_score is not None and score > 0
             and computation.winsorized_values[n] > 0 and computation.winsorized_values[n] >= cutoff_score]
    seed_available = len(seeds) >= 2
    clusters = [n for n in seeds if len({e["owner_cik"] for e in by_sid[mappings[n]["qc_symbol_id"]]}) >= 2] if seed_available else []
    cluster_available = len(clusters) >= 2
    selected = [n for n, score in enumerate(scores) if score > 0]
    if not 1 <= len(selected) <= 20:
        base._refuse("nonempty stock primary or fixed QC capacity unavailable")
    rows, signals = [], []
    for n, mapping in enumerate(mappings):
        stock_events = by_sid[mapping["qc_symbol_id"]]
        rows.append({"issuer_cik": mapping["issuer_cik"], "qc_symbol_id": mapping["qc_symbol_id"], "ticker": mapping["ticker"],
                     "raw_stock_score": str(scores[n]), "winsorized_stock_score": None if not available else str(computation.winsorized_values[n]),
                     "normalized_stock_score": None if not available else str(computation.normalized_values[n]),
                     "buyer_breadth": len({e["owner_cik"] for e in stock_events}), "structural_zero": not stock_events,
                     "seed_selected": n in seeds if seed_available else None, "buyer_cluster_selected": n in clusters if cluster_available else None,
                     "stock_primary_selected": n in selected})
        if n in selected:
            event_digest = hash_payload(stock_events)
            signals.append({"signal_id": event_digest[:32], "ticker": mapping["ticker"], "qc_symbol_id": mapping["qc_symbol_id"],
                            "source_event_sha256": event_digest, "mapping_first_session": mapping["mapping_first_session"],
                            "mapping_last_session": mapping["mapping_last_session"],
                            "available_at_utc": max(e["available_at_utc"] for e in stock_events)[:-1] + "+00:00",
                            "decision_session": sessions[decision_index], "entry_session": entry, "exit_session": exit_day})
    manifest = {"schema": "insider-qc-stock-order-study-v1", "source_manifest_sha256": trust_roots.source_manifest_sha256,
                "security_master_sha256": trust_roots.security_master_sha256, "calendar_sha256": calendar_hash,
                "outcome_vintage_sha256": auth["outcome_vintage_sha256"], "sessions": sessions,
                "signals": sorted(signals, key=lambda s: (s["decision_session"], s["signal_id"]))}
    summary = {"kind": VERSION, **trust_roots.to_payload(), "source_stream_sha256": source_evidence.sha256,
               "artifact_calendar_sha256": trust_roots.calendar_sha256, "calendar_sha256": calendar_hash,
               "registered_look_id": auth["registered_look_id"], "rights_record_sha256": auth["rights_record_sha256"],
               "outcome_vintage_sha256": auth["outcome_vintage_sha256"], "source_window_start": source["source_start"],
               "source_window_end": source["source_end"], "score_lookback_start_session": lookback,
               "decision_session": sessions[decision_index], "decision_cutoff_utc": base._utc_text(cutoff), "sessions": sessions,
               "source_submission_count": source["source_submission_count"], "source_form_counts": source["source_form_counts"],
               "stream_corroborated_form4_count": source["stream_corroborated_form4_count"],
               "preceding_quarantined_count": source["preceding_quarantined_count"],
               "future_parent_count": source["future_parent_count"], "amendment_linkage_evaluated": False,
               "source_window_policy": "exact_contiguous_quarters_cover_complete_calendar_30_session_window",
               "timing_policy": "daily_regular_close_score_snapshot_then_next_session_open",
               "literal_first_open_after_each_acceptance": False, "context_eligibility_verified": True,
               "ordinary_share_exception_count": sum(d["ordinary_share_exception_applied"] for d in decisions),
               "admitted_event_count": len(events), "scored_stock_count": len(rows), "signal_count": len(signals),
               "excluded_reason_counts": dict(sorted(excluded.items())), "normalization_outcome": computation.outcome.value,
               "seed_diagnostic_available": seed_available, "buyer_cluster_diagnostic_available": cluster_available,
               "primary_sample_policy": "all_positive_eligible_stock_event_scores_no_seed_or_buyer_filter",
               "complete_project_backtesting_readiness": False, "source_authenticated_here": False,
               "execution_performed": False, "qc_jobs": 0, "research_looks": 0}
    raw = canonical_json({"summary": summary, "events": events, "scored_rows": rows, "manifest": manifest,
                          "classification": decisions, "context": context}).encode("utf-8")
    result = StreamStockPipeline(raw, _TOKEN)
    _BUILT[id(result)] = (weakref.ref(result, lambda _, key=id(result): _BUILT.pop(key, None)), raw)
    return result
