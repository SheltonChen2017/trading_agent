"""Evidence-bound, offline IB v2 event admission and frozen stock mathematics.

Trust roots are an EXTERNAL trusted-configuration boundary: the caller must
establish the provenance and authorization of those fixed byte hashes outside
this module. Artifact self-hashes, names, caller booleans, and an untrusted v2
assessment cannot establish that boundary. This verifier independently checks
the anchored contents, reparses the original parents, and derives events and
scores. Fixture roots/artifacts remain visibly distinct from production roots.
No files, providers, outcomes, QC jobs, or execution interfaces are accessed.

The source manifest commits the complete supplied quarter coverage, not an
arbitrary selection of qualifying filings. Raw/parsed ZIP loading is still the
coverage producer's duty. Official acceptance values are independently pinned
in that manifest and must equal the exact SEC-header timestamp after Eastern
timezone conversion. Date-only, ambiguous/nonexistent local times fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, localcontext
import hashlib
import json
import re
import weakref
from zoneinfo import ZoneInfo

from data.hashing import canonical_json, hash_bytes, hash_payload
from data.financial_primitives import exact_decimal_sum
from research.insider_buying.form4_xml import parse_form4_xml
from research.insider_buying.sec_complete_submission import (
    SecCompleteSubmissionTarget, project_sec_complete_submission,
)
from research.insider_buying.sec_ib1c_v2_downstream import V2QuarterCoverage
from research.insider_buying import form4_stock_signal_formula_diagnostics as formula
from research.insider_buying import form4_stock_signal_normalization_diagnostics as normalization
from research.insider_buying import form4_stock_signal_seed_diagnostics as seed
from research.insider_buying import form4_stock_signal_buyer_cluster_diagnostics as cluster


PIPELINE_VERSION = "INSETF-IB-BACKTEST-EVIDENCE-PIPELINE-v1"
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
MAX_PARENTS = 256
MAX_PARENT_BYTES = 64 * 1024 * 1024
MAX_EVENTS = 10_000
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_TEXT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z")
_TICKER = re.compile(r"[A-Z][A-Z0-9.]{0,9}\Z")
_LOOK = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,79}\Z")
_CIK = re.compile(r"[0-9]{10}\Z")
_TOKEN = object()
_BUILT: dict[int, tuple[weakref.ReferenceType, bytes]] = {}
_MISSING = (
    "externally_anchored_complete_source_manifest_and_original_parents",
    "externally_anchored_point_in_time_security_master",
    "externally_anchored_regular_session_open_close_calendar",
    "externally_anchored_single_study_authorization_and_rights",
)


class EvidencePipelineError(ValueError):
    """An anchored artifact or derived event failed the bounded contract."""


def _refuse(reason: str) -> None:
    raise EvidencePipelineError("REFUSED: " + reason)


def _sha(value: object) -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        _refuse("an exact lowercase SHA-256 is required")
    return value


def _keys(value: object, keys: set[str], label: str) -> dict:
    if type(value) is not dict or set(value) != keys:
        _refuse(label + " fields differ from the exact schema")
    return value


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            _refuse("duplicate JSON member")
        result[key] = value
    return result


def _artifact(raw: bytes, digest: str, schema: str, scope: str) -> dict:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_ARTIFACT_BYTES:
        _refuse("artifact bytes exceed their bound")
    if hash_bytes(raw) != digest:
        _refuse("artifact does not match the external trust root")
    try:
        result = json.loads(raw, object_pairs_hook=_pairs,
                            parse_constant=lambda _: _refuse("nonfinite JSON"))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise EvidencePipelineError("REFUSED: artifact JSON is malformed") from exc
    if type(result) is not dict or result.get("schema") != schema or result.get("trust_scope") != scope:
        _refuse("artifact schema or trust scope mismatch")
    return result


def _day(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        _refuse("session is not an exact ISO date")
    try:
        checked = date.fromisoformat(value)
    except ValueError as exc:
        raise EvidencePipelineError("REFUSED: invalid session date") from exc
    return value


def _utc(value: object) -> datetime:
    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value) is None:
        _refuse("timestamp is not exact whole-second UTC")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidencePipelineError("REFUSED: invalid UTC timestamp") from exc


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True, slots=True)
class EvidenceTrustRoots:
    """Externally established anchors, never an artifact's self-declaration."""

    trust_scope: str
    source_manifest_sha256: str
    security_master_sha256: str
    calendar_sha256: str
    authorization_sha256: str

    def __post_init__(self) -> None:
        self.to_payload()

    def to_payload(self) -> dict:
        if type(self) is not EvidenceTrustRoots or type(self.trust_scope) is not str or self.trust_scope not in {"fixture", "production"}:
            _refuse("exact distinct fixture/production trust roots are required")
        return {"trust_scope": self.trust_scope, **{
            name: _sha(getattr(self, name)) for name in (
                "source_manifest_sha256", "security_master_sha256", "calendar_sha256", "authorization_sha256")}}


def analyze_v2_coverage(coverage: V2QuarterCoverage) -> dict:
    """Bookkeeping handoff, not an evaluation of actual financial eligibility."""
    if type(coverage) is not V2QuarterCoverage:
        _refuse("an exact sealed v2 quarter coverage is required")
    body = coverage.to_payload()
    relevant = [row for row in coverage.pilot_rows() if row["form_type"] in {"4", "4/A"}]
    return {
        "kind": PIPELINE_VERSION + "-coverage-handoff", "coverage_sha256": coverage.sha256,
        "period": body["period"], "submission_count": body["submission_count"],
        "corroborated_count": body["corroborated_count"], "quarantined_count": body["quarantined_count"],
        "form_counts": body["form_counts"], "quarantine_reason_counts": body["quarantine_reason_counts"],
        "source_identity_complete": body["source_identity_complete"],
        "source_identity_sha256": body["source_identity_sha256"],
        "relevant_form4_count": len(relevant),
        "relevant_form4_identity_complete": bool(relevant) and all(row["disposition"] == "corroborated_noncanonical" for row in relevant),
        "eligible_events_evaluated": False, "admitted_event_count": 0,
        "backtesting_ready": False, "missing_evidence": list(_MISSING),
        "source_authenticated": False, "qc_jobs": 0, "research_looks": 0,
    }


@dataclass(frozen=True, slots=True, weakref_slot=True)
class EvidencePipeline:
    """Immutable derived bytes; copies expose no mutable internal dictionaries."""

    _bytes: bytes = field(repr=False)
    _token: object = field(repr=False, compare=False)
    _factory_bytes: bytes | None = field(default=None, init=False, repr=False, compare=False)

    def _body(self) -> dict:
        registered = _BUILT.get(id(self))
        if (type(self) is not EvidencePipeline or self._token is not _TOKEN or type(self._bytes) is not bytes
                or self._bytes != self._factory_bytes or registered is None
                or registered[0]() is not self or registered[1] != self._bytes):
            _refuse("pipeline output was reconstructed or altered")
        return json.loads(self._bytes)

    def to_payload(self) -> dict:
        return self._body()["summary"]

    def scored_rows(self) -> list[dict]:
        return self._body()["scored_rows"]

    def admitted_events(self) -> list[dict]:
        return self._body()["events"]

    def signals(self) -> list[dict]:
        return self._body()["manifest"]["signals"]

    def signal_manifest_bytes(self) -> bytes:
        return canonical_json(self._body()["manifest"]).encode("ascii")

    @property
    def sha256(self) -> str:
        self._body()
        return hash_bytes(self._bytes)


def validate_evidence_pipeline(value: EvidencePipeline) -> dict:
    """Require the exact sealed output at the package-builder boundary."""
    if type(value) is not EvidencePipeline:
        _refuse("an exact sealed evidence pipeline is required")
    return value.to_payload()


def _calendar(body: dict) -> tuple[list[str], list[datetime], list[datetime], str]:
    _keys(body, {"schema", "trust_scope", "sessions"}, "calendar")
    records = body["sessions"]
    if type(records) is not list or not 22 <= len(records) <= 6000:
        _refuse("calendar session count exceeds the frozen QC contract")
    sessions, opens, closes = [], [], []
    eastern = ZoneInfo("America/New_York")
    for record in records:
        _keys(record, {"session", "open_utc", "close_utc"}, "calendar record")
        session, opened, closed = _day(record["session"]), _utc(record["open_utc"]), _utc(record["close_utc"])
        if not "1900-01-01" <= session <= "2027-08-31":
            _refuse("calendar context intersects holdout or exceeds its bound")
        local_open, local_close = opened.astimezone(eastern), closed.astimezone(eastern)
        # Anchored calendars may include verified early closes; never pre/post-market.
        if (not opened < closed or local_open.date().isoformat() != session
                or local_close.date().isoformat() != session or local_open.weekday() >= 5
                or (local_open.hour, local_open.minute, local_open.second) != (9, 30, 0)
                or (local_close.hour, local_close.minute, local_close.second) not in {(16, 0, 0), (13, 0, 0)}):
            _refuse("calendar is not a verified regular US session")
        if sessions and (session <= sessions[-1] or opened <= closes[-1]):
            _refuse("calendar sessions are duplicated or reordered")
        sessions.append(session); opens.append(opened); closes.append(closed)
    digest = hashlib.sha256(json.dumps(sessions, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    return sessions, opens, closes, digest


def _acceptance(raw: str, official: object) -> datetime:
    if type(raw) is not str or re.fullmatch(r"[0-9]{14}", raw) is None:
        _refuse("official timestamp precision is required")
    try:
        local = datetime.strptime(raw, "%Y%m%d%H%M%S")
    except ValueError as exc:
        raise EvidencePipelineError("REFUSED: invalid header acceptance") from exc
    eastern = ZoneInfo("America/New_York")
    instants = set()
    for fold in (0, 1):
        aware = local.replace(tzinfo=eastern, fold=fold)
        instant = aware.astimezone(timezone.utc)
        if instant.astimezone(eastern).replace(tzinfo=None) == local:
            instants.add(instant)
    if len(instants) != 1:
        _refuse("ambiguous or nonexistent Eastern acceptance timestamp")
    actual = instants.pop()
    if actual != _utc(official):
        _refuse("official acceptance evidence disagrees with original header")
    return actual


def _mappings(body: dict, sessions: list[str], cutoff: datetime, issuers: set[str]) -> list[dict]:
    _keys(body, {"schema", "trust_scope", "mappings", "source_exclusions"}, "security master")
    records = body["mappings"]
    if type(records) is not list or not 1 <= len(records) <= MAX_EVENTS:
        _refuse("security master mapping count exceeds the cohort bound")
    keys = {"issuer_cik", "qc_symbol_id", "ticker", "security_title", "share_class", "security_class", "country", "venue", "mapping_first_session", "mapping_last_session", "knowledge_at_utc"}
    seen_sid, seen_ticker, result = set(), set(), []
    for item in records:
        _keys(item, keys, "security mapping")
        if (type(item["issuer_cik"]) is not str or _CIK.fullmatch(item["issuer_cik"]) is None
                or int(item["issuer_cik"]) == 0
                or type(item["qc_symbol_id"]) is not str or len(item["qc_symbol_id"]) > 100 or _TEXT.fullmatch(item["qc_symbol_id"]) is None
                or type(item["ticker"]) is not str or _TICKER.fullmatch(item["ticker"]) is None
                or type(item["share_class"]) is not str or _TEXT.fullmatch(item["share_class"]) is None
                or type(item["security_title"]) is not str or not 0 < len(item["security_title"]) <= 128
                or not item["security_title"].isascii() or not item["security_title"].isprintable()
                or item["security_title"] != item["security_title"].strip()
                or item["security_class"] != "common_stock" or item["country"] != "US"
                or type(item["venue"]) is not str or item["venue"] not in {"XNYS", "XNAS", "XASE"}):
            _refuse("mapping is not a bound ordinary US stock")
        first, last = _day(item["mapping_first_session"]), _day(item["mapping_last_session"])
        if first >= last or _utc(item["knowledge_at_utc"]) > cutoff:
            _refuse("mapping interval or point-in-time knowledge is invalid")
        if item["qc_symbol_id"] in seen_sid or item["ticker"] in seen_ticker:
            _refuse("ambiguous SID, ticker reuse, or share-class mapping")
        seen_sid.add(item["qc_symbol_id"]); seen_ticker.add(item["ticker"])
        result.append(dict(item))
    exclusions = body["source_exclusions"]
    if type(exclusions) is not list or len(exclusions) > MAX_PARENTS:
        _refuse("source security exclusions exceed their bound")
    excluded_issuers = set()
    for item in exclusions:
        _keys(item, {"issuer_cik", "security_class", "country", "reason"}, "source security exclusion")
        if (type(item["issuer_cik"]) is not str or _CIK.fullmatch(item["issuer_cik"]) is None
                or item["issuer_cik"] not in issuers or item["issuer_cik"] in excluded_issuers
                or item["issuer_cik"] in {record["issuer_cik"] for record in result}
                or type(item["country"]) is not str or re.fullmatch(r"[A-Z]{2}", item["country"]) is None
                or type(item["security_class"]) is not str or item["security_class"] not in {"common_stock", "preferred_stock", "other"}
                or type(item["reason"]) is not str
                or item["reason"] != ("non_us_security" if item["country"] != "US" else "non_common_stock" if item["security_class"] != "common_stock" else None)):
            _refuse("source noneligible security exclusion is ambiguous or ordinary US stock")
        excluded_issuers.add(item["issuer_cik"])
    if not issuers <= {item["issuer_cik"] for item in result} | excluded_issuers:
        _refuse("source issuer lacks a mapping or explicit noneligible exclusion")
    if result != sorted(result, key=lambda item: item["qc_symbol_id"]):
        _refuse("security cohort must be in deterministic SID order")
    return result


def _authorization(body: dict, roots: EvidenceTrustRoots, calendar_hash: str, sessions: list[str]) -> dict:
    keys = {"schema", "trust_scope", "scope", "registered_look_id", "source_manifest_sha256", "security_master_sha256", "calendar_sha256", "outcome_vintage_sha256", "rights_record_sha256", "rights_representation", "decision_session", "qc_entitlement_sha256", "delisting_sha256", "adjustments_sha256", "protocol_sha256"}
    _keys(body, keys, "authorization")
    if (body["scope"] != "single-research-backtest-only" or body["rights_representation"] != "local-and-quantconnect"
            or type(body["registered_look_id"]) is not str or _LOOK.fullmatch(body["registered_look_id"]) is None
            or body["source_manifest_sha256"] != roots.source_manifest_sha256
            or body["security_master_sha256"] != roots.security_master_sha256
            or body["calendar_sha256"] != calendar_hash):
        _refuse("authorization scope or evidence cross-binding differs")
    for name in ("outcome_vintage_sha256", "rights_record_sha256", "qc_entitlement_sha256", "delisting_sha256", "adjustments_sha256", "protocol_sha256"):
        _sha(body[name])
    if (type(body["decision_session"]) is not str or not "2006-01-01" <= body["decision_session"] <= "2027-08-31"
            or body["decision_session"] not in sessions or sessions.index(body["decision_session"]) + 21 >= len(sessions)):
        _refuse("decision lacks its complete frozen entry/exit horizon")
    return body


def build_evidence_pipeline(
    *, coverage: V2QuarterCoverage, parent_images: tuple[bytes, ...],
    source_manifest: bytes, security_master: bytes, calendar: bytes,
    authorization: bytes, trust_roots: EvidenceTrustRoots,
) -> EvidencePipeline:
    """Reparse externally anchored evidence and compute a nonempty QC manifest.

    The daily universe is the complete anchored eligible security inventory,
    INCLUDING stocks with no source filing. Every supplied source issuer must
    map into it or have an explicit content-bound noneligible exclusion. Zero scores exist
only after every corresponding source filing has been parsed and excluded or
lies outside the lookback; missing source/mapping data never becomes a zero.
    For conservative amendment lineage, an issuer with ANY Form4/A is excluded as
    an entire related family, even when the amendment has no transactions.
    A one-quarter source cannot prove a cross-quarter lookback: the inclusive
    30-session window and decision must lie within that exact supplied quarter.
"""
    if type(trust_roots) is not EvidenceTrustRoots:
        _refuse("exact external trust roots are required")
    trust_roots.to_payload()
    handoff = analyze_v2_coverage(coverage)
    if not handoff["relevant_form4_identity_complete"]:
        _refuse("complete nonempty Form4 identity is required; quarantine is retained")
    all_rows = coverage.pilot_rows()
    rows = [row for row in all_rows if row["form_type"] in {"4", "4/A"}]
    unsupported = [row for row in all_rows if row["form_type"] not in {"4", "4/A"}]
    if any(row["quarantine_reasons"] != ["unsupported_parent_corroboration_form"] for row in unsupported):
        _refuse("unsupported source forms have unexpected unresolved identities")
    if (type(parent_images) is not tuple or not 0 < len(parent_images) <= MAX_PARENTS
            or any(type(raw) is not bytes or not raw for raw in parent_images)
            or sum(len(raw) for raw in parent_images) > MAX_PARENT_BYTES):
        _refuse("original parents exceed the bounded exact tuple")
    scope = trust_roots.trust_scope
    source = _artifact(source_manifest, trust_roots.source_manifest_sha256, "insider-backtest-source-manifest-v1", scope)
    security = _artifact(security_master, trust_roots.security_master_sha256, "insider-backtest-security-master-v1", scope)
    calendar_body = _artifact(calendar, trust_roots.calendar_sha256, "insider-backtest-calendar-v1", scope)
    auth = _artifact(authorization, trust_roots.authorization_sha256, "insider-backtest-authorization-v1", scope)
    _keys(source, {"schema", "trust_scope", "coverage_sha256", "origin", "parents"}, "source manifest")
    if source["coverage_sha256"] != coverage.sha256 or source["origin"] != {
            "fixture": "invented-complete-submission", "production": "sec-original-complete-submission"}[scope]:
        _refuse("source origin or complete coverage binding differs")
    entries = source["parents"]
    if type(entries) is not list or len(entries) != len(rows) or len(entries) != len(parent_images):
        _refuse("source parent inventory is not the exact complete coverage")
    sessions, opens, closes, calendar_hash = _calendar(calendar_body)
    auth = _authorization(auth, trust_roots, calendar_hash, sessions)
    decision_index = sessions.index(auth["decision_session"])
    if decision_index < 31:
        _refuse("calendar lacks verified pre-decision lookback context")
    year, quarter = int(handoff["period"][:4]), int(handoff["period"][-1])
    source_start = date(year, 3 * quarter - 2, 1)
    next_start = date(year + 1, 1, 1) if quarter == 4 else date(year, 3 * quarter + 1, 1)
    source_end = next_start - timedelta(days=1)
    lookback_start = date.fromisoformat(sessions[decision_index - 30])
    if lookback_start < source_start or date.fromisoformat(sessions[decision_index]) > source_end:
        _refuse("complete 30-session source window is not inside the supplied quarter")
    cutoff = closes[decision_index]
    mappings = _mappings(security, sessions, cutoff, {row["issuer_comparison_key"] for row in rows})
    entry_session, exit_session = sessions[decision_index + 1], sessions[decision_index + 21]
    for mapping in mappings:
        if not mapping["mapping_first_session"] <= sessions[decision_index] < entry_session < exit_session < mapping["mapping_last_session"]:
            _refuse("mapping does not cover the frozen trade horizon")
    amended_issuers = {row["issuer_comparison_key"] for row in rows if row["form_type"] == "4/A"}
    parsed = []
    for row, entry, raw in zip(rows, entries, parent_images, strict=True):
        _keys(entry, {"target", "projection_sha256", "parent_sha256", "header_sha256", "xml_sha256", "official_acceptance_utc"}, "source parent")
        if type(entry["target"]) is not dict:
            _refuse("source target is not a mapping")
        try:
            target = SecCompleteSubmissionTarget(**entry["target"])
            projection = project_sec_complete_submission(target, raw)
            payload = projection.to_payload()
        except (ValueError, TypeError) as exc:
            raise EvidencePipelineError("REFUSED: original parent projection failed") from exc
        if (target.accession_number != row["accession_number"] or target.period != row["period"]
                or target.form_type != row["form_type"] or target.filing_date != row["filing_date"]
                or target.issuer_cik != row["issuer_comparison_key"]):
            _refuse("source target identity disagrees with complete coverage")
        actual = {"projection_sha256": projection.sha256, "parent_sha256": hash_bytes(raw),
                  "header_sha256": hash_bytes(projection.header_bytes), "xml_sha256": hash_bytes(projection.xml_bytes)}
        if any(entry[name] != value or row["corroboration"][name] != value for name, value in actual.items()) or row["corroboration"]["declared_index_sha256"] != target.quarterly_index_sha256:
            _refuse("original parent, header, XML or projection bytes differ")
        accepted = _acceptance(projection.accepted_at_raw, entry["official_acceptance_utc"])
        if accepted > cutoff:
            _refuse("future acceptance cannot enter the decision source inventory")
        if accepted.astimezone(ZoneInfo("America/New_York")).date().isoformat() != target.filing_date:
            _refuse("official acceptance date disagrees with source filing date")
        # An amendment excludes its issuer family without relying on presence of XML rows.
        if target.issuer_cik in amended_issuers:
            parsed.append((row, None, accepted, projection))
            continue
        try:
            filing = parse_form4_xml(projection.xml_bytes, accession_number=target.accession_number,
                                     acceptance=accepted, source_name=target.complete_submission_url)
        except ValueError as exc:
            raise EvidencePipelineError("REFUSED: original ownership XML parsing failed") from exc
        if tuple(owner.owner_cik for owner in filing.reporting_owners) != projection.header_owner_ciks:
            _refuse("SEC header and XML reporting owners disagree")
        parsed.append((row, filing, accepted, projection))
    grouped: dict[tuple, dict] = {}
    excluded: dict[str, int] = {}
    member_count = 0
    excluded_security = {item["issuer_cik"] for item in security["source_exclusions"]}
    for row, filing, accepted, projection in parsed:
        if filing is None:
            excluded["amended_issuer_family"] = excluded.get("amended_issuer_family", 0) + 1
            continue
        if row["issuer_comparison_key"] in excluded_security:
            excluded["noneligible_source_security"] = excluded.get("noneligible_source_security", 0) + len(filing.transactions)
            continue
        if len(filing.reporting_owners) != 1:
            excluded["joint_or_missing_reporting_owner"] = excluded.get("joint_or_missing_reporting_owner", 0) + len(filing.transactions)
            continue
        owner = filing.reporting_owners[0]
        for transaction in filing.transactions:
            if not transaction.eligible_for_lot_aggregation:
                for outcome in transaction.outcomes:
                    excluded[outcome.value] = excluded.get(outcome.value, 0) + 1
                continue
            if transaction.transaction_date > accepted.astimezone(ZoneInfo("America/New_York")).date():
                _refuse("transaction date is after public filing availability")
            candidates = [item for item in mappings if item["issuer_cik"] == row["issuer_comparison_key"]
                          and item["security_title"] == transaction.security_title_raw
                          and item["ticker"] == filing.envelope.issuer_symbol_raw
                          and item["mapping_first_session"] <= transaction.transaction_date.isoformat() < item["mapping_last_session"]
                          and _utc(item["knowledge_at_utc"]) <= accepted]
            if len(candidates) != 1:
                _refuse("exact title/share-class/ticker mapping is missing, future or ambiguous")
            mapping = candidates[0]
            key = (owner.owner_cik, mapping["qc_symbol_id"], transaction.transaction_date.isoformat())
            group = grouped.setdefault(key, {"owner_cik": owner.owner_cik, "qc_symbol_id": mapping["qc_symbol_id"],
                "transaction_date": key[2], "values": [], "member_ids": [], "available": accepted})
            group["values"].append(transaction.purchase_value_usd)
            group["member_ids"].append(transaction.event_id)
            group["available"] = max(group["available"], accepted)
            member_count += 1
            if member_count > MAX_EVENTS:
                _refuse("eligible event member count exceeds the frozen bound")
    events = []
    by_sid = {mapping["qc_symbol_id"]: [] for mapping in mappings}
    formula._require_frozen_policy(); normalization._require_frozen_policy()
    seed._require_frozen_policy(); cluster._require_frozen_policy()
    for key in sorted(grouped):
        group = grouped[key]
        value = exact_decimal_sum(group["values"], name="evidence-bound post-aggregation purchase value")
        if group["available"] < closes[0]:
            # Any first decision close for this availability is <= index zero;
            # the >=31 measured prior sessions prove it is outside the 30-day lookback.
            excluded["outside_30_session_lookback"] = excluded.get("outside_30_session_lookback", 0) + 1
            continue
        activation = next((index for index, closed in enumerate(closes) if closed >= group["available"]), None)
        if activation is None or activation > decision_index:
            _refuse("lot activation is after the verified decision close")
        age = decision_index - activation
        if value < Decimal(50000) or age > 30:
            reason = "below_post_aggregation_threshold" if value < Decimal(50000) else "outside_30_session_lookback"
            excluded[reason] = excluded.get(reason, 0) + 1
            continue
        size, freshness, score = formula._event_formula(value, age)
        event = {"owner_cik": group["owner_cik"], "qc_symbol_id": group["qc_symbol_id"],
                 "transaction_date": group["transaction_date"], "purchase_value_usd": str(value),
                 "available_at_utc": _utc_text(group["available"]), "activation_session": sessions[activation],
                 "age_trading_days": age, "member_event_ids": sorted(group["member_ids"]),
                 "event_size": str(size), "freshness": str(freshness), "event_score": str(score)}
        event["event_sha256"] = hash_payload(event)
        events.append(event); by_sid[group["qc_symbol_id"]].append(event)
    with localcontext(formula._new_decimal_context()):
        scores = tuple(sum((Decimal(event["event_score"]) for event in by_sid[item["qc_symbol_id"]]), Decimal(0)) for item in mappings)
    computation = normalization._compute_normalization(scores)
    target_count = (len(mappings) + 9) // 10
    normalized_available = computation.outcome.value == "available"
    cutoff_score = sorted(computation.winsorized_values, reverse=True)[target_count - 1] if normalized_available else None
    candidates = [index for index, value in enumerate(computation.winsorized_values)
                  if cutoff_score is not None and scores[index] > 0 and value > 0 and value >= cutoff_score]
    seed_available = len(candidates) >= 2
    cluster_candidates = [index for index in candidates if len({event["owner_cik"] for event in by_sid[mappings[index]["qc_symbol_id"]]}) >= 2] if seed_available else []
    cluster_available = len(cluster_candidates) >= 2
    # The stock primary is NOT the separate ETF seed/buyer-cluster comparison.
    selected = [index for index, score in enumerate(scores) if score > 0]
    if not 1 <= len(selected) <= 20:
        _refuse("nonempty stock primary or QC capacity unavailable")
    scored_rows, signals = [], []
    for index, mapping in enumerate(mappings):
        stock_events = by_sid[mapping["qc_symbol_id"]]
        scored_rows.append({"issuer_cik": mapping["issuer_cik"], "qc_symbol_id": mapping["qc_symbol_id"],
            "ticker": mapping["ticker"], "raw_stock_score": str(scores[index]),
            "winsorized_stock_score": None if computation.winsorized_values[index] is None else str(computation.winsorized_values[index]),
            "normalized_stock_score": None if computation.normalized_values[index] is None else str(computation.normalized_values[index]),
            "buyer_breadth": len({event["owner_cik"] for event in stock_events}),
            "structural_zero": not stock_events, "seed_selected": index in candidates if seed_available else None,
            "buyer_cluster_selected": index in cluster_candidates if cluster_available else None,
            "stock_primary_selected": index in selected})
        if index in selected:
            source_event = hash_payload(stock_events)
            signals.append({"signal_id": source_event[:32], "ticker": mapping["ticker"],
                "qc_symbol_id": mapping["qc_symbol_id"], "source_event_sha256": source_event,
                "mapping_first_session": mapping["mapping_first_session"], "mapping_last_session": mapping["mapping_last_session"],
                "available_at_utc": max(event["available_at_utc"] for event in stock_events).removesuffix("Z") + "+00:00",
                "decision_session": sessions[decision_index], "entry_session": entry_session, "exit_session": exit_session})
    manifest = {"schema": "insider-qc-stock-order-study-v1", "source_manifest_sha256": trust_roots.source_manifest_sha256,
        "security_master_sha256": trust_roots.security_master_sha256, "calendar_sha256": calendar_hash,
        "outcome_vintage_sha256": auth["outcome_vintage_sha256"], "sessions": sessions,
        "signals": sorted(signals, key=lambda item: (item["decision_session"], item["signal_id"]))}
    summary = {"kind": PIPELINE_VERSION, "trust_scope": scope, "coverage_sha256": coverage.sha256,
        "source_manifest_sha256": trust_roots.source_manifest_sha256, "security_master_sha256": trust_roots.security_master_sha256,
        "artifact_calendar_sha256": trust_roots.calendar_sha256, "calendar_sha256": calendar_hash,
        "authorization_sha256": trust_roots.authorization_sha256, "outcome_vintage_sha256": auth["outcome_vintage_sha256"],
        "rights_record_sha256": auth["rights_record_sha256"], "registered_look_id": auth["registered_look_id"],
        "sessions": sessions, "decision_session": sessions[decision_index], "decision_cutoff_utc": _utc_text(cutoff),
        "source_window_start": source_start.isoformat(), "source_window_end": source_end.isoformat(),
        "score_lookback_start_session": lookback_start.isoformat(),
        "source_window_policy": "complete_30_session_window_and_decision_inside_single_supplied_quarter",
        "timing_policy": "daily_regular_close_score_snapshot_then_next_session_open",
        "literal_first_open_after_each_acceptance": False,
        "after_close_filings_wait_for_following_decision_close": True,
        "source_submission_count": len(all_rows), "source_quarantined_count": len(unsupported),
        "source_form_counts": handoff["form_counts"], "source_quarantine_reason_counts": handoff["quarantine_reason_counts"],
        "relevant_form4_count": len(rows), "relevant_form4_identity_complete": True,
        "whole_quarter_source_identity_complete": handoff["source_identity_complete"],
        "whole_quarter_source_identity_sha256": handoff["source_identity_sha256"],
        "admitted_event_count": len(events), "scored_stock_count": len(scored_rows), "signal_count": len(signals),
        "excluded_reason_counts": dict(sorted(excluded.items())), "bounded_pipeline_complete": True,
        "candidate_scope": "bounded_256_parent_one_quarter_integration_candidate",
        "streaming_fullquarter_limit": "fullquarter_successor_required_above_256_parents_or_64MiB",
        "complete_project_backtesting_readiness": False,
        "primary_sample_policy": "all_positive_eligible_stock_event_scores_no_seed_or_buyer_filter",
        "normalization_outcome": computation.outcome.value, "seed_diagnostic_available": seed_available,
        "buyer_cluster_diagnostic_available": cluster_available,
        "production_evidence_scope": scope == "production", "single_study_authorization_verified": True,
        "execution_performed": False, "qc_jobs": 0, "research_looks": 0,
        "math_policy_hashes": [formula.FORM4_STOCK_SIGNAL_NUMERIC_POLICY_HASH, normalization.FORM4_STOCK_SIGNAL_NORMALIZATION_POLICY_HASH,
            seed.FORM4_STOCK_SIGNAL_SEED_POLICY_HASH, cluster.FORM4_STOCK_SIGNAL_BUYER_CLUSTER_POLICY_HASH]}
    result = EvidencePipeline(canonical_json({"summary": summary, "events": events, "scored_rows": scored_rows, "manifest": manifest}).encode(), _TOKEN)
    object.__setattr__(result, "_factory_bytes", result._bytes)
    identity = id(result)
    reference = weakref.ref(result, lambda _: _BUILT.pop(identity, None))
    _BUILT[identity] = (reference, result._bytes)
    return result
