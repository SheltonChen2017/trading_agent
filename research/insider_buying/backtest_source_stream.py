"""Separately versioned, pure streaming corroboration of complete Form-4 scope.

The caller supplies an already sealed all-six-form v2 census and a one-pass
iterator of original parent records. Each relevant original is reparsed, not
trusted as a precomputed projection. An EXTERNAL population trust root binds
the ordered per-quarter inventory of every raw image, target and timestamp.
The old assessor's 256-parent limit is not changed: missing corroboration in
its bookkeeping is established anew here and remains distinct in the receipt.

All parents, including future parents, are content-verified for population
accounting. Future parents never appear in as-of issuer, amendment or event
facts. Only compact known-at-cutoff facts survive iteration; original images
are not stored by this module. Coverage itself is a bounded in-memory v2
artifact, not a claim of streaming ZIP ingestion or historical SEC identity.
There is no file, network, outcome, QC or execution interface here.
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import re
import weakref
from zoneinfo import ZoneInfo

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying.form4_xml import parse_form4_xml
from research.insider_buying.sec_complete_submission import (
    MAX_COMPLETE_SUBMISSION_BYTES, SecCompleteSubmissionTarget,
    project_sec_complete_submission,
)
from research.insider_buying.sec_ib1c_v2_downstream import (
    EXPECTED_PERIODS, V2QuarterCoverage, compose_v2_scope_coverage,
)


STREAM_VERSION = "INSETF-IB-BACKTEST-SOURCE-STREAM-v2"
STREAM_EVIDENCE_EPOCH = STREAM_VERSION + "-source-only-candidate"
MAX_POPULATION_MANIFEST_BYTES = 128 * 1024
MAX_ENTRY_BYTES = 8192
MAX_TOTAL_PARENT_BYTES = 128 * 1024 * 1024 * 1024
MAX_COMPACT_BYTES = 512 * 1024 * 1024
MAX_TRANSACTIONS = 2_000_000
MAX_PARENT_TRANSACTIONS = 20_000
MAX_PARENT_COMPACT_BYTES = 16 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_FORMS = ("3", "3/A", "4", "4/A", "5", "5/A")
_TOKEN = object()
_BUILT: dict[int, tuple[weakref.ReferenceType, bytes]] = {}


class StreamSourceError(ValueError):
    """The complete original source stream failed its fixed evidence contract."""


def _refuse(reason: str) -> None:
    raise StreamSourceError("REFUSED: " + reason)


def _sha(value: object) -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        _refuse("an exact lowercase SHA-256 is required")
    return value


def _keys(value: object, keys: set[str], label: str) -> dict:
    if type(value) is not dict or set(value) != keys:
        _refuse(label + " fields differ from the exact schema")
    return value


def _pairs(pairs) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            _refuse("duplicate JSON member")
        result[key] = value
    return result


def _json(raw: bytes, cap: int, label: str) -> dict:
    if type(raw) is not bytes or not 0 < len(raw) <= cap:
        _refuse(label + " bytes exceed their bound")
    try:
        result = json.loads(raw, object_pairs_hook=_pairs,
                            parse_constant=lambda _: _refuse("nonfinite JSON"))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StreamSourceError("REFUSED: " + label + " JSON is malformed") from exc
    if type(result) is not dict or canonical_json(result).encode("utf-8") != raw:
        _refuse(label + " is not exact canonical JSON")
    return result


def _day(value: object) -> date:
    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        _refuse("session is not an exact ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise StreamSourceError("REFUSED: invalid session date") from exc


def _utc(value: object) -> datetime:
    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value) is None:
        _refuse("timestamp is not exact whole-second UTC")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StreamSourceError("REFUSED: invalid UTC timestamp") from exc


def _acceptance(raw: str, official: object) -> datetime:
    if type(raw) is not str or re.fullmatch(r"[0-9]{14}", raw) is None:
        _refuse("official timestamp precision is required")
    try:
        local = datetime.strptime(raw, "%Y%m%d%H%M%S")
    except ValueError as exc:
        raise StreamSourceError("REFUSED: invalid original header acceptance") from exc
    eastern = ZoneInfo("America/New_York")
    instants = set()
    for fold in (0, 1):
        instant = local.replace(tzinfo=eastern, fold=fold).astimezone(timezone.utc)
        if instant.astimezone(eastern).replace(tzinfo=None) == local:
            instants.add(instant)
    if len(instants) != 1:
        _refuse("ambiguous or nonexistent Eastern acceptance timestamp")
    actual = instants.pop()
    if actual != _utc(official):
        _refuse("official acceptance evidence disagrees with original header")
    return actual


def _period(day: date) -> str:
    return f"{day.year}Q{(day.month - 1) // 3 + 1}"


def _period_interval(period: str) -> tuple[date, date]:
    year, quarter = int(period[:4]), int(period[-1])
    start = date(year, quarter * 3 - 2, 1)
    next_start = date(year + 1, 1, 1) if quarter == 4 else date(year, quarter * 3 + 1, 1)
    return start, next_start - timedelta(days=1)


@dataclass(frozen=True, slots=True, weakref_slot=True)
class StreamParentRecord:
    """One raw image and its separately anchored canonical inventory entry."""

    entry_bytes: bytes = field(repr=False)
    raw_bytes: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if (type(self) is not StreamParentRecord or type(self.entry_bytes) is not bytes
                or not 0 < len(self.entry_bytes) <= MAX_ENTRY_BYTES
                or type(self.raw_bytes) is not bytes
                or not 0 < len(self.raw_bytes) <= MAX_COMPLETE_SUBMISSION_BYTES):
            _refuse("one original record exceeds its individual byte bound")


@dataclass(frozen=True, slots=True, weakref_slot=True)
class StreamSourceEvidence:
    """Factory-registered compact as-of facts, not financial admission."""

    _bytes: bytes = field(repr=False)
    _token: object = field(repr=False, compare=False)
    _factory_bytes: bytes | None = field(default=None, init=False, repr=False, compare=False)

    def _body(self) -> dict:
        registration = _BUILT.get(id(self))
        if (type(self) is not StreamSourceEvidence or self._token is not _TOKEN
                or type(self._bytes) is not bytes or self._bytes != self._factory_bytes
                or registration is None or registration[0]() is not self
                or registration[1] != self._bytes):
            _refuse("source stream evidence was reconstructed or altered")
        return json.loads(self._bytes)

    def to_payload(self) -> dict:
        return self._body()["summary"]

    def parent_facts(self) -> list[dict]:
        return self._body()["parent_facts"]

    def transaction_rows(self) -> list[dict]:
        return self._body()["transaction_rows"]

    def quarter_receipts(self) -> list[dict]:
        """Detached complete-quarter counts and original inventory bindings."""
        return self._body()["summary"]["quarter_inventories"]

    @property
    def sha256(self) -> str:
        self._body()
        return hash_bytes(self._bytes)


def validate_stream_source_evidence(value: StreamSourceEvidence) -> dict:
    if type(value) is not StreamSourceEvidence:
        _refuse("an exact sealed streaming source evidence is required")
    return value.to_payload()


def _transaction_payload(transaction, parent: dict, owners: list[dict]) -> dict:
    decimal_fields = ("shares", "price_per_share", "purchase_value_usd", "shares_owned_after")
    result = {
        "period": parent["period"], "source_record_ordinal": parent["source_record_ordinal"],
        "accession_number": parent["accession_number"], "issuer_cik": parent["issuer_cik"],
        "form_type": parent["form_type"], "accepted_at_utc": parent["accepted_at_utc"],
        "source_parent_sha256": parent["parent_sha256"], "xml_sha256": parent["xml_sha256"],
        "issuer_symbol_raw": parent["issuer_symbol_raw"], "reporting_owners": owners,
        "event_id": transaction.event_id, "row_index": transaction.row_index,
        "derivative": transaction.derivative, "security_title_raw": transaction.security_title_raw,
        "transaction_date": None if transaction.transaction_date is None else transaction.transaction_date.isoformat(),
        "transaction_code": transaction.transaction_code, "acquired_disposed_code": transaction.acquired_disposed_code,
        **{name: None if getattr(transaction, name) is None else str(getattr(transaction, name)) for name in decimal_fields},
        "direct_indirect": transaction.direct_indirect, "aff10b5_one": transaction.aff10b5_one,
        "footnote_ids": list(transaction.footnote_ids), "footnote_texts": list(transaction.footnote_texts),
        "provisional_outcomes": [outcome.value for outcome in transaction.outcomes],
        "provisional_diagnostics": [outcome.value for outcome in transaction.diagnostics],
        "provisional_eligible_for_lot_aggregation": transaction.eligible_for_lot_aggregation,
    }
    result["transaction_sha256"] = hash_payload(result)
    return result


def _owner_payload(owner) -> dict:
    return {name: getattr(owner, name) for name in (
        "owner_cik", "owner_name", "is_director", "is_officer", "is_ten_percent_owner",
        "is_other", "officer_title")}


def _stream_parent(row: dict, record: StreamParentRecord, cutoff: datetime) -> tuple[dict, list[dict], bool]:
    if type(record) is not StreamParentRecord:
        _refuse("stream contains a non-original record")
    record.__post_init__()
    entry = _json(record.entry_bytes, MAX_ENTRY_BYTES, "parent inventory entry")
    _keys(entry, {"target", "projection_sha256", "parent_sha256", "header_sha256", "xml_sha256",
                  "official_acceptance_utc"}, "parent inventory entry")
    for name in ("projection_sha256", "parent_sha256", "header_sha256", "xml_sha256"):
        _sha(entry[name])
    try:
        if type(entry["target"]) is not dict:
            _refuse("source target is not an exact mapping")
        target = SecCompleteSubmissionTarget(**entry["target"])
        projection = project_sec_complete_submission(target, record.raw_bytes)
        projection.to_payload()  # Public raw reparse; not private projection reuse.
    except (ValueError, TypeError) as exc:
        raise StreamSourceError("REFUSED: original parent projection failed") from exc
    if any(getattr(target, name) != row[field] for name, field in (
            ("period", "period"), ("accession_number", "accession_number"), ("form_type", "form_type"),
            ("filing_date", "filing_date"), ("issuer_cik", "issuer_comparison_key"))):
        _refuse("source target identity disagrees with complete source population")
    actual = {"projection_sha256": projection.sha256, "parent_sha256": hash_bytes(record.raw_bytes),
              "header_sha256": hash_bytes(projection.header_bytes), "xml_sha256": hash_bytes(projection.xml_bytes)}
    if any(entry[name] != value for name, value in actual.items()):
        _refuse("original parent, header, XML or projection differs from anchored inventory")
    previous = row["corroboration"]
    if previous is not None and (any(previous[name] != value for name, value in actual.items())
                                 or previous["declared_index_sha256"] != target.quarterly_index_sha256):
        _refuse("stream originals conflict with preceding v2 corroboration")
    if row["quarantine_reasons"] == ["complete_parent_identity_conflict"]:
        _refuse("preceding identity conflict is retained, not overwritten")
    accepted = _acceptance(projection.accepted_at_raw, entry["official_acceptance_utc"])
    if accepted.astimezone(ZoneInfo("America/New_York")).date().isoformat() != target.filing_date:
        _refuse("official acceptance date disagrees with source filing date")
    filing = None
    # The frozen financial parser requires established amendment linkage. The
    # stream does not invent that linkage just to force financial parsing. The
    # public complete-parent parser still verifies every amendment's complete
    # SGML/header/XML identity. Its issuer is conservatively excluded as-of;
    # amendment transaction eligibility is explicitly NOT evaluated, not zero.
    if target.form_type == "4":
        try:
            filing = parse_form4_xml(projection.xml_bytes, accession_number=target.accession_number,
                                     acceptance=accepted, source_name=target.complete_submission_url)
        except ValueError as exc:
            raise StreamSourceError("REFUSED: original ownership XML parsing failed") from exc
        if (tuple(owner.owner_cik for owner in filing.reporting_owners) != projection.header_owner_ciks
                or filing.envelope.issuer_cik != target.issuer_cik
                or filing.envelope.form_type != target.form_type
                or len(filing.transactions) > MAX_PARENT_TRANSACTIONS):
            _refuse("original owners, issuer, form or transaction bound disagrees")
    # Public parsing of later contents verifies scope identity only. No future
    # facts are returned to the financial/PIT consumer, even an amendment family.
    future = accepted > cutoff
    fact = {
        "period": row["period"], "source_record_ordinal": row["source_record_ordinal"],
        "submission_row_id": row["submission_row_id"], "accession_number": target.accession_number,
        "issuer_cik": target.issuer_cik, "form_type": target.form_type, "filing_date": target.filing_date,
        "accepted_at_utc": entry["official_acceptance_utc"], "amends_accession": None,
        "amendment_linkage_evaluated": False,
        "issuer_symbol_raw": None if filing is None else filing.envelope.issuer_symbol_raw,
        "header_owner_ciks": list(projection.header_owner_ciks),
        "reporting_owners": None if filing is None else [_owner_payload(owner) for owner in filing.reporting_owners],
        "quarterly_index_sha256": target.quarterly_index_sha256,
        **actual, "transaction_count": None if filing is None else len(filing.transactions),
        "transaction_accounting_evaluated": filing is not None,
        "provisional_eligibility_evaluated": filing is not None,
    }
    if future:
        return fact, [], True
    transactions = []
    parent_compact_bytes = len(canonical_json(fact).encode("utf-8"))
    if parent_compact_bytes > MAX_PARENT_COMPACT_BYTES:
        _refuse("per-parent compact facts exceed their bound")
    if filing is not None:
        # A long common footnote may be referenced by many XML rows. Bound
        # repeated compact serialization before allocating the whole parent
        # population; the XML byte cap alone does not bound that expansion.
        for transaction in filing.transactions:
            payload = _transaction_payload(transaction, fact, fact["reporting_owners"])
            parent_compact_bytes += len(canonical_json(payload).encode("utf-8"))
            if parent_compact_bytes > MAX_PARENT_COMPACT_BYTES:
                _refuse("per-parent compact transaction expansion exceeds its bound")
            transactions.append(payload)
    return fact, transactions, False


def build_stream_source_evidence(
    *, coverages: tuple[V2QuarterCoverage, ...], expected_periods: tuple[str, ...],
    parent_records: Iterable[StreamParentRecord], population_manifest: bytes,
    population_sha256: str, trust_scope: str, lookback_start_session: str,
    decision_session: str, decision_cutoff_utc: str,
) -> StreamSourceEvidence:
    """Verify every relevant original in one pass and retain compact as-of facts.

    The ordered inventory hash is SHA256 of each exact canonical entry followed
    by one LF byte, concatenated in quarter/source-ordinal order. Its digest is
    fixed in the externally anchored manifest *before* this stream runs. Scope
    must be the exact contiguous source quarters touched by the verified
    financial consumer's inclusive 30-session window; this module checks dates,
    while calendar verification and the 30-session count remain that consumer's
    independent responsibility. No zero financial signal is inferred here.
    """
    if type(trust_scope) is not str or trust_scope not in {"fixture", "production"}:
        _refuse("exact distinct fixture/production trust scope is required")
    _sha(population_sha256)
    manifest = _json(population_manifest, MAX_POPULATION_MANIFEST_BYTES, "population manifest")
    if hash_bytes(population_manifest) != population_sha256:
        _refuse("population manifest differs from external trust root")
    _keys(manifest, {"schema", "trust_scope", "origin", "scope_sha256", "expected_periods", "quarters"}, "population manifest")
    if (manifest["schema"] != "insider-backtest-source-population-v2"
            or manifest["trust_scope"] != trust_scope or manifest["origin"] != {
                "fixture": "invented-complete-submission", "production": "sec-original-complete-submission"}[trust_scope]):
        _refuse("source population origin, schema or trust scope differs")
    start, decision, cutoff = _day(lookback_start_session), _day(decision_session), _utc(decision_cutoff_utc)
    if (start > decision or not date(2006, 1, 1) <= start <= decision <= date(2026, 6, 30)
            or cutoff.astimezone(ZoneInfo("America/New_York")).date() != decision):
        _refuse("source lookback, frozen source window or cutoff session differs")
    first_period, last_period = _period(start), _period(decision)
    required = EXPECTED_PERIODS[EXPECTED_PERIODS.index(first_period):EXPECTED_PERIODS.index(last_period) + 1]
    if (type(expected_periods) is not tuple or expected_periods != required
            or manifest["expected_periods"] != list(required)):
        _refuse("scope is not the complete contiguous source lookback quarters")
    try:
        scope = compose_v2_scope_coverage(coverages, expected_periods)
        scope_body = scope.to_payload()
    except (ValueError, TypeError, AttributeError) as exc:
        raise StreamSourceError("REFUSED: preceding v2 scope cannot be verified") from exc
    if not scope_body["loaded_scope_complete"] or scope_body["missing_periods"]:
        _refuse("source lookback quarters are missing")
    if manifest["scope_sha256"] != scope.sha256:
        _refuse("population scope differs from exact preceding producer lineage")
    quarters = manifest["quarters"]
    if type(quarters) is not list or len(quarters) != len(coverages):
        _refuse("population quarter inventory is missing or reordered")
    # Enforce one-pass semantics. A caller may supply a generator or a custom
    # iterator; reusable tuple/list collections are deliberately not this API.
    if not isinstance(parent_records, Iterator) or iter(parent_records) is not parent_records:
        _refuse("original parents require an exact one-pass iterator")
    parent_facts, transactions, inventories = [], [], []
    total_parent_bytes = compact_bytes = total_parents = future_parents = future_transactions = 0
    future_amendment_parents = 0
    accounting_digest = hashlib.sha256()
    all_accessions = set()
    known_events = set()
    for quarter, declaration in zip(coverages, quarters, strict=True):
        context = quarter.to_payload()
        _keys(declaration, {"period", "coverage_sha256", "parent_count", "ordered_parent_inventory_sha256"}, "population quarter")
        _sha(declaration["ordered_parent_inventory_sha256"])
        if (declaration["period"] != context["period"] or declaration["coverage_sha256"] != quarter.sha256
                or type(declaration["parent_count"]) is not int
                or declaration["parent_count"] != context["form_counts"]["4"] + context["form_counts"]["4/A"]):
            _refuse("population quarter coverage, count or order differs")
        inventory_digest = hashlib.sha256()
        quarter_accounting_digest = hashlib.sha256()
        quarter_accessions = []
        observed = 0
        rows = quarter.pilot_rows()
        for row in rows:
            accession = row["accession_number"]
            if accession in all_accessions:
                _refuse("an accession repeats across complete scope")
            all_accessions.add(accession)
            quarter_accessions.append(accession)
            accounting_bytes = canonical_json(row).encode("utf-8") + b"\n"
            accounting_digest.update(accounting_bytes)
            quarter_accounting_digest.update(accounting_bytes)
            if row["form_type"] not in {"4", "4/A"}:
                if row["quarantine_reasons"] != ["unsupported_parent_corroboration_form"]:
                    _refuse("unsupported source form has an unexpected identity refusal")
                continue
            try:
                record = next(parent_records)
            except StopIteration as exc:
                raise StreamSourceError("REFUSED: relevant original parent is missing") from exc
            fact, parsed_transactions, future = _stream_parent(row, record, cutoff)
            inventory_digest.update(record.entry_bytes + b"\n")
            total_parent_bytes += len(record.raw_bytes)
            if total_parent_bytes > MAX_TOTAL_PARENT_BYTES:
                _refuse("aggregate source stream exceeds total byte bound")
            observed += 1
            total_parents += 1
            if future:
                future_parents += 1
                if fact["transaction_count"] is None:
                    future_amendment_parents += 1
                else:
                    future_transactions += fact["transaction_count"]
            else:
                compact_bytes += len(canonical_json(fact).encode("utf-8"))
                parent_facts.append(fact)
                for transaction in parsed_transactions:
                    if transaction["event_id"] in known_events:
                        _refuse("a parsed event repeats across original source population")
                    known_events.add(transaction["event_id"])
                    compact_bytes += len(canonical_json(transaction).encode("utf-8"))
                    if len(transactions) >= MAX_TRANSACTIONS:
                        _refuse("compact transaction population exceeds its bound")
                    transactions.append(transaction)
                if compact_bytes > MAX_COMPACT_BYTES:
                    _refuse("compact as-of source facts exceed their byte bound")
            # Crucially, do not retain record/projection/raw images on advancing
            # the generator. Only copied compact facts and hashes survive.
            del record, fact, parsed_transactions
        del rows
        if (observed != declaration["parent_count"]
                or inventory_digest.hexdigest() != declaration["ordered_parent_inventory_sha256"]):
            _refuse("ordered original inventory count or digest differs")
        inventories.append({**declaration, "observed_parent_count": observed,
            "preparation_binding": context["preparation_binding"],
            "source_submission_count": context["submission_count"],
            "source_form_counts": context["form_counts"],
            "preceding_corroborated_count": context["corroborated_count"],
            "preceding_quarantined_count": context["quarantined_count"],
            "preceding_quarantine_reason_counts": context["quarantine_reason_counts"],
            "accession_numbers": quarter_accessions,
            "accession_numbers_sha256": hash_payload(quarter_accessions),
            "all_source_row_accounting_sha256": quarter_accounting_digest.hexdigest()})
    try:
        next(parent_records)
    except StopIteration:
        pass
    else:
        _refuse("original source stream contains an unaccounted extra parent")
    relevant = scope_body["form_counts"]["4"] + scope_body["form_counts"]["4/A"]
    if relevant <= 0 or total_parents != relevant:
        _refuse("source requires a complete nonempty relevant Form4 population")
    source_start, _ = _period_interval(required[0])
    _, source_end = _period_interval(required[-1])
    summary = {
        "kind": STREAM_VERSION, "evidence_epoch": STREAM_EVIDENCE_EPOCH,
        "trust_scope": trust_scope, "production_evidence_scope": trust_scope == "production",
        "population_manifest_sha256": population_sha256, "preceding_scope_sha256": scope.sha256,
        "expected_periods": list(required), "loaded_periods": scope_body["loaded_periods"],
        "source_start": source_start.isoformat(), "source_end": source_end.isoformat(),
        "lookback_start_session": lookback_start_session, "decision_session": decision_session,
        "decision_cutoff_utc": decision_cutoff_utc, "quarter_inventories": inventories,
        "preceding_quarter_bindings": [quarter.to_payload()["preparation_binding"] for quarter in coverages],
        "source_submission_count": scope_body["submission_count"],
        "source_form_counts": scope_body["form_counts"],
        "preceding_corroborated_count": scope_body["corroborated_count"],
        "preceding_quarantined_count": scope_body["quarantined_count"],
        "preceding_quarantine_reason_counts": scope_body["quarantine_reason_counts"],
        "all_source_row_accounting_sha256": accounting_digest.hexdigest(),
        "relevant_form4_count": relevant, "stream_corroborated_form4_count": total_parents,
        "relevant_form4_identity_complete": True,
        "as_of_parent_count": len(parent_facts), "future_parent_count": future_parents,
        "as_of_transaction_count": len(transactions),
        "future_transaction_count": None if future_amendment_parents else future_transactions,
        "future_original_transaction_count": future_transactions,
        "future_amendment_eligibility_not_evaluated_count": future_amendment_parents,
        "as_of_amendment_eligibility_not_evaluated_count": sum(fact["form_type"] == "4/A" for fact in parent_facts),
        "as_of_amended_issuers": sorted({fact["issuer_cik"] for fact in parent_facts if fact["form_type"] == "4/A"}),
        "as_of_issuer_ciks": sorted({fact["issuer_cik"] for fact in parent_facts}),
        "total_original_parent_bytes": total_parent_bytes, "raw_parent_images_retained": 0,
        "compact_content_bytes": compact_bytes, "as_of_parent_facts_sha256": hash_payload(parent_facts),
        "as_of_transactions_sha256": hash_payload(transactions),
        "source_identity_sha256": hash_payload({"population": population_sha256, "scope": scope.sha256,
                                                  "inventories": inventories}),
        "whole_six_form_identity_complete": scope_body["submission_count"] == relevant,
        "whole_six_form_identity_sha256": (hash_payload({"population": population_sha256,
                                                        "scope": scope.sha256, "inventories": inventories})
                                               if scope_body["submission_count"] == relevant else None),
        "unsupported_form_count": scope_body["submission_count"] - relevant,
        "eligible_events_evaluated": False, "candidate_signal_count": None,
        "source_authenticated": False, "official_acceptance_provenance_authenticated_here": False,
        "artifact_loading_verified_here": False, "point_in_time_data": False,
        "rights_verified": False, "qc_authorized": False, "backtest_authorized": False,
        "execution_authorized": False, "sec_dispatches": 0, "qc_jobs": 0, "research_looks": 0,
    }
    raw = canonical_json({"summary": summary, "parent_facts": parent_facts,
                          "transaction_rows": transactions}).encode("utf-8")
    if len(raw) > MAX_COMPACT_BYTES:
        _refuse("complete compact evidence envelope exceeds its byte bound")
    result = StreamSourceEvidence(raw, _TOKEN)
    object.__setattr__(result, "_factory_bytes", raw)
    _BUILT[id(result)] = (weakref.ref(result, lambda _, key=id(result): _BUILT.pop(key, None)), raw)
    return result


__all__ = ["StreamSourceError", "StreamParentRecord", "StreamSourceEvidence",
           "build_stream_source_evidence", "validate_stream_source_evidence"]
