"""Separate retrospective actual-release sensitivity; no causal calendar gate.

Blueprint 15.3 requires earnings-confounder exclusions +/-2 and +/-5 trading
days. It does not make a future forecast calendar an entry prerequisite.
This pure successor uses exact supplied actual PUBLIC RELEASE lineage and
complete issuer/event-window coverage, never projected dates, earnings calls,
SEC filing timestamps or an empty response inferred to mean no event.

No file, credentials, provider, outcome query, QC job or new look is accessed.
The only return inputs are a genuine sealed fixture result from the fixed v2
primary calculation, kept in memory; no per-event return export is exposed.
Externally pinned document/receipt/rights bytes are bindings, not authenticated
source, coverage or license facts. Production remains blocked before decoding.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import localcontext

from research.insider_buying import backtest_registered_analysis as analysis


SCHEMA = "insider-realized-earnings-sensitivity-v1"
SOURCE_SCHEMA = "insider-source-event-actual-earnings-coverage-v1"
MAX_BYTES = 16 * 1024 * 1024
MAX_RELEASES_PER_EVENT = 32
MAX_REVISIONS_PER_RELEASE = 16


class RealizedEarningsDiagnosticError(ValueError):
    """A missing, incomplete or cross-epoch retrospective diagnostic refused."""


def _need(condition, reason):
    if not condition:
        raise RealizedEarningsDiagnosticError("REFUSED: " + reason)


@dataclass(frozen=True, slots=True)
class RealizedEarningsDiagnosticTrustRoots:
    trust_scope: str
    registration_sha256: str
    manifest_sha256: str
    primary_report_sha256: str
    actual_earnings_sha256: str
    source_receipt_sha256: str
    rights_sha256: str
    diagnostic_implementation_sha256: str

    def __post_init__(self):
        _need(type(self) is RealizedEarningsDiagnosticTrustRoots
              and type(self.trust_scope) is str and self.trust_scope in {"fixture", "production"},
              "exact external diagnostic trust roots required")
        for name in self.__dataclass_fields__:
            if name.endswith("sha256"):
                analysis._digest(getattr(self, name))


def assess_realized_earnings_sensitivity(*, primary_result: analysis.RegisteredStudyV2Result,
        actual_earnings_raw: bytes, trust_roots: RealizedEarningsDiagnosticTrustRoots,
        expected_implementation_sha256: str) -> dict:
    """Fixed-window descriptive comparison under the SAME parent registration.

    Reaction session is the first regular close strictly after actual release:
    pre-open/intraday releases map to that day; at/after-close/weekend releases
    map to the next session. Source coverage must encompass the corresponding
    exact half-open UTC interval for every frozen source-event issuer. Missing
    coverage is explicit UNAVAILABLE, with no partial diagnostic acceptance.
    """
    _need(type(trust_roots) is RealizedEarningsDiagnosticTrustRoots, "exact diagnostic roots required")
    trust_roots.__post_init__()
    _need(trust_roots.trust_scope == "fixture", "production diagnostic blocked by unchanged zero-look gate")
    _need(type(primary_result) is analysis.RegisteredStudyV2Result, "genuine sealed v2 primary result required")
    sealed = primary_result._body()
    report, registration, manifest = (sealed[key] for key in ("report", "registration", "manifest"))
    _need(report["schema"] == analysis.SCHEMA_V2 and report["trust_scope"] == "fixture"
          and registration["schema"] == "insider-stock-analysis-registration-v2"
          and manifest["schema"] == "insider-stock-event-study-manifest-v3", "primary result epoch differs")
    _need(primary_result.sha256 == trust_roots.primary_report_sha256
          and report["artifact_sha256s"]["registration"] == trust_roots.registration_sha256
          and report["artifact_sha256s"]["manifest"] == trust_roots.manifest_sha256,
          "primary/registration/manifest external binding differs")
    analysis._digest(expected_implementation_sha256)
    _need(trust_roots.diagnostic_implementation_sha256 == expected_implementation_sha256
          == registration["realized_earnings_implementation_sha256"],
          "diagnostic executable identity differs")
    _need(analysis.canonical_bytes(registration["policy"]) == analysis.canonical_bytes(analysis.frozen_analysis_policy_v2()),
          "fixed pre-outcome actual-release policy differs")
    body = analysis._decode(actual_earnings_raw, trust_roots.actual_earnings_sha256, max_bytes=MAX_BYTES)
    analysis._fields(body, {"schema", "trust_scope", "registration_sha256", "manifest_sha256",
        "event_inventory_sha256", "calendar_sha256", "source_receipt_sha256", "rights_sha256",
        "source_as_of_utc", "release_session_policy", "events"}, "actual earnings coverage")
    _need(body["schema"] == SOURCE_SCHEMA and body["trust_scope"] == "fixture"
          and body["registration_sha256"] == trust_roots.registration_sha256
          and body["manifest_sha256"] == trust_roots.manifest_sha256
          and body["calendar_sha256"] == registration["calendar_sha256"]
          and body["source_receipt_sha256"] == trust_roots.source_receipt_sha256
          and body["rights_sha256"] == trust_roots.rights_sha256
          and body["release_session_policy"] == registration["policy"]["earnings_release_session"],
          "actual-release source/rights/calendar/policy epoch differs")
    for key in ("event_inventory_sha256", "calendar_sha256", "source_receipt_sha256", "rights_sha256"):
        analysis._digest(body[key])
    asof = analysis._utc(body["source_as_of_utc"])
    events = manifest["events"]
    _need(body["event_inventory_sha256"] == analysis._sha(analysis.canonical_bytes(events)),
          "complete frozen source event inventory differs")
    rows = body["events"]
    _need(type(rows) is list and len(rows) == len(events), "actual-release event coverage missing/extra")
    sessions = manifest["sessions"]
    dates = [row["session"] for row in sessions]
    closes = [analysis._utc(row["close_utc"]) for row in sessions]
    values = sealed["event_results"]
    _need([row["signal_id"] for row in values] == [row["signal_id"] for row in events],
          "sealed primary result order differs from frozen manifest")
    offsets, unavailable, active_releases = {}, [], 0
    for row, event in zip(rows, events, strict=True):
        analysis._fields(row, {"signal_id", "issuer_id", "security_id", "source_event_sha256",
            "coverage_start_utc", "coverage_end_utc", "coverage_disposition", "unavailable_reason", "releases"},
            "actual release event coverage")
        _need(all(row[key] == event[key] for key in ("signal_id", "issuer_id", "security_id", "source_event_sha256")),
              "actual-release event/issuer/security identity missing/extra/reordered")
        entry = dates.index(event["entry_session"])
        lower, upper = closes[entry - 6], closes[entry + 5]
        _need(analysis._utc(row["coverage_start_utc"]) == lower
              and analysis._utc(row["coverage_end_utc"]) == upper and asof >= upper,
              "exact +/-5 reaction-session coverage interval is incomplete")
        _need(type(row["coverage_disposition"]) is str and row["coverage_disposition"] in {"COMPLETE", "UNAVAILABLE"},
              "coverage disposition invalid")
        releases = row["releases"]
        _need(type(releases) is list and len(releases) <= MAX_RELEASES_PER_EVENT, "actual releases unbounded")
        if row["coverage_disposition"] == "UNAVAILABLE":
            analysis._id(row["unavailable_reason"])
            _need(not releases, "unavailable coverage cannot carry selectively observed releases")
            unavailable.append({"signal_id": event["signal_id"], "reason": row["unavailable_reason"]})
            offsets[event["signal_id"]] = None
            continue
        _need(row["unavailable_reason"] is None, "complete coverage carries an unavailable reason")
        seen, times, distances = set(), [], []
        for release in releases:
            analysis._fields(release, {"release_id", "release_type", "lineage"}, "actual public release")
            identity = analysis._id(release["release_id"])
            _need(identity not in seen and release["release_type"] == "ACTUAL_PUBLIC_EARNINGS_RELEASE",
                  "duplicate release or forecast/call/filing substituted for actual release")
            seen.add(identity)
            lineage = release["lineage"]
            _need(type(lineage) is list and 1 <= len(lineage) <= MAX_REVISIONS_PER_RELEASE,
                  "actual release lineage missing/unbounded")
            prior, previous_time, version_ids = None, None, set()
            for revision in lineage:
                analysis._fields(revision, {"version_id", "supersedes_version_id", "recorded_at_utc",
                    "actual_public_release_at_utc", "status", "source_document_sha256", "source_record_sha256"}, "release revision")
                version = analysis._id(revision["version_id"])
                recorded = analysis._utc(revision["recorded_at_utc"])
                released = analysis._utc(revision["actual_public_release_at_utc"])
                analysis._digest(revision["source_document_sha256"]); analysis._digest(revision["source_record_sha256"])
                _need(version not in version_ids and revision["supersedes_version_id"] == prior
                      and (previous_time is None or previous_time < recorded) and released <= recorded <= asof
                      and type(revision["status"]) is str and revision["status"] in {"ACTIVE", "RETRACTED"},
                      "actual-release correction lineage/time/status differs")
                version_ids.add(version); prior, previous_time = version, recorded
            final = lineage[-1]
            if final["status"] == "RETRACTED":
                continue
            released = analysis._utc(final["actual_public_release_at_utc"])
            _need(lower <= released < upper, "actual release lies outside the exactly bound event coverage interval")
            reaction = next((index for index, closing in enumerate(closes) if closing > released), None)
            _need(reaction is not None and abs(reaction - entry) <= 5, "actual release reaction session unbracketed")
            times.append((released, identity)); distances.append(reaction - entry); active_releases += 1
        _need(times == sorted(times), "actual releases reordered")
        offsets[event["signal_id"]] = distances
    available = not unavailable
    diagnostics = None
    if available:
        with localcontext() as arithmetic:
            arithmetic.prec = 50
            diagnostics = {}
            for window in (2, 5):
                excluded = [event["signal_id"] for event in events
                    if any(abs(offset) <= window for offset in offsets[event["signal_id"]])]
                retained = [analysis._decimal(row["matched_net10_20s"]) for row in values if row["signal_id"] not in excluded]
                diagnostics[str(window)] = {"excluded_signal_ids": excluded, "retained": len(retained),
                    "mean_matched_net10": analysis._text(analysis._mean(retained)) if retained else None}
    result = {"schema": SCHEMA, "trust_scope": "fixture", "registered_look_id": registration["registered_look_id"],
        "candidate_id": registration["candidate_id"], "registration_sha256": trust_roots.registration_sha256,
        "manifest_sha256": trust_roots.manifest_sha256, "primary_report_sha256": primary_result.sha256,
        "actual_earnings_sha256": trust_roots.actual_earnings_sha256,
        "source_receipt_sha256": trust_roots.source_receipt_sha256, "rights_sha256": trust_roots.rights_sha256,
        "diagnostic_implementation_sha256": expected_implementation_sha256,
        "disposition": "FIXTURE_COMPLETE" if available else "UNAVAILABLE", "coverage_complete": available,
        "event_count": len(events), "active_release_count": active_releases, "unavailable_events": unavailable,
        "earnings_exclusion_diagnostics": diagnostics, "windows_sessions": [2, 5],
        "retrospective_descriptive_only": True, "primary_selection_or_orders_changed": False,
        "new_outcome_query_performed": False, "raw_or_per_event_returns_exported": False,
        "source_authentication_performed": False, "rights_authenticated_here": False,
        "required_diagnostic_verified_for_production": False, "implementation_execution_identity_verified_here": False,
        "ib5_pass": False, "backtesting_ready": False, "look_authority": False,
        "alpha_spent": [0, 1], "registered_looks_consumed": 0, "qc_jobs": 0}
    result["diagnostic_sha256"] = analysis._sha(analysis.canonical_bytes(result))
    return result
