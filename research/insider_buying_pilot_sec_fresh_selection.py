"""Pure completed-stream selection of 64 fresh 2021Q1 original-parent requests.

This is a new pilot contract, not a 2006 selection, a loaded source snapshot,
or a dispatch grant. Every emitted source/disposition row is bound to genuine
completed 25-quarter roster and audit factories before a selection is sealed.
The serialized validator checks metadata, not source authenticity or custody.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import weakref

from research import insider_buying_pilot_sec_parent_audit as audit
from research import insider_buying_pilot_sec_roster as roster
from research.insider_buying.sec_quarter_master_index import SecMasterIndexRow


SCHEMA = "insider-pilot-sec-fresh-parent-selection-v1"
PERIOD = "2021Q1"
LIMIT = 64
POLICY = "first_64_source_order_2021Q1_fresh_locatable_requests_after_full_25quarter_consumption_and_repeat_suppression"
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_ELIGIBLE_METADATA_BYTES = 512 * 1024 * 1024
_TOKEN = object()
_SEALS = weakref.WeakKeyDictionary()
_REQUEST_KEYS = frozenset({"period", "accession_number", "form_type", "filing_date", "issuer_cik", "archive_path", "url",
    "source_record_ordinal", "filing_metadata_sha256", "quarterly_zip_sha256", "submission_member_sha256",
    "submission_header_line_sha256", "schema_profile_sha256", "master_decoded_sha256", "master_receipt_sha256"})
_RECORD_KEYS = frozenset({"selection_ordinal", "source", "source_record_sha256", "request", "request_sha256",
    "pre_normalization_target", "selected_locator", "compiler_disposition_sha256", "dispatch_authorized", "canonical_admitted"})
_DISPOSITION_KEYS = frozenset({"schema", "source", "source_record_sha256", "relevant_parent_target", "prior_consumed",
    "prior_exposure_evidence", "prior_source_occurrence", "cross_quarter_accession_repeat", "cross_quarter_source_identity_conflict",
    "historical_ambiguous_start_preserved", "candidate_identity_conflicts", "retained_candidate_body_identity_conflict",
    "matching_retained_candidates", "body_candidate_is_not_parent_admission", "complete_parent_parsed_here", "disposition",
    "master_aliases", "selected_locator", "locator_quarantine_reasons", "pre_normalization_target", "request", "request_sha256",
    "fresh_locatable_candidate", "dispatch_authorized", "canonical_admitted"})
_RESULT_KEYS = frozenset({"schema", "fixture_only", "selection_period", "selection_limit", "selected_count", "selection_policy",
    "requests", "source_roster_sha256", "parent_audit_sha256", "exposure_inventory_sha256", "retained_candidate_inventory_sha256",
    "source_roster_counts", "parent_context_counts", "parent_pilot_counts", "quarter_bindings",
    "full_source_row_jsonl_sha256", "full_source_row_jsonl_bytes", "full_disposition_jsonl_sha256", "full_disposition_jsonl_bytes",
    "full_fresh_request_jsonl_sha256", "full_fresh_request_jsonl_bytes", "selected_request_jsonl_sha256", "selected_request_jsonl_bytes",
    "selected_metadata_jsonl_sha256", "selected_metadata_jsonl_bytes", "selection_period_observed_fresh_count",
    "selection_period_suppressed_late_repeat_count", "selection_period_eligible_after_global_suppression_count",
    "global_consumed_accessions", "global_repeat_accessions_observed", "all_25_quarters_finished",
    "complete_source_population_is_not_complete_parent_corpus", "no_earlier_or_later_quarter_substitution",
    "separate_diagnostic_does_not_resolve_original_ambiguous_start", "authority", "dispatch_authorized", "canonical_admitted",
    "backtesting_ready", "new_provider_requests", "credential_reads", "qc_jobs", "outcome_looks", "backtests"})


class PilotSecFreshSelectionError(ValueError):
    """Fixed source-independent refusals only."""


def _need(condition, code):
    if not condition:
        raise PilotSecFreshSelectionError(code)


_raw, _sha = audit._raw, audit._sha


def _digest(value):
    _need(type(value) is str and audit._SHA.fullmatch(value) is not None, "selection_digest_required")
    return value


def _integer(value, *, maximum=25 * audit.MAX_QUARTER_ROWS):
    _need(type(value) is int and 0 <= value <= maximum, "selection_typed_count_required")
    return value


def _request_record(value, expected_ordinal):
    _need(type(value) is dict and set(value) == _RECORD_KEYS and type(value["selection_ordinal"]) is int
        and value["selection_ordinal"] == expected_ordinal and value["dispatch_authorized"] is False
        and value["canonical_admitted"] is False, "selection_request_record_schema")
    source, _ = audit._source(value["source"])
    _need(source["period"] == PERIOD and source["form_type"] in {"4", "4/A"}
        and value["source_record_sha256"] == source["filing_metadata_sha256"], "selection_source_scope_or_hash")
    request = value["request"]
    _need(type(request) is dict and set(request) == _REQUEST_KEYS
        and value["request_sha256"] == _sha(_raw(request)), "selection_exact_request_hash")
    for key in _REQUEST_KEYS - {"source_record_ordinal"}:
        _need(type(request[key]) is str and 0 < len(request[key]) <= 2048
            and not any(ord(character) < 32 for character in request[key]), "selection_request_scalar")
    mapping = {"issuer_cik": "raw_issuer_cik", "period": "period", "accession_number": "accession_number",
        "form_type": "form_type", "filing_date": "filing_date", "source_record_ordinal": "source_record_ordinal",
        "filing_metadata_sha256": "filing_metadata_sha256", "quarterly_zip_sha256": "quarterly_zip_sha256",
        "submission_member_sha256": "submission_member_sha256", "submission_header_line_sha256": "submission_header_line_sha256",
        "schema_profile_sha256": "schema_profile_sha256"}
    _need(type(request["source_record_ordinal"]) is int and all(request[key] == source[field] for key, field in mapping.items()),
        "selection_request_source_binding")
    for key in ("master_decoded_sha256", "master_receipt_sha256"):
        _digest(request[key])
    locator = value["selected_locator"]
    _need(type(locator) is dict and set(locator) == {"accession_number", "form_type", "filing_date", "archive_path"},
        "selection_master_locator_schema")
    try:
        alias = SecMasterIndexRow(**locator).to_payload()
    except (TypeError, ValueError):
        raise PilotSecFreshSelectionError("selection_master_locator_refused") from None
    _need(all(request[key] == alias[key] for key in alias)
        and request["url"] == "https://www.sec.gov/Archives/" + alias["archive_path"], "selection_master_locator_binding")
    target = {key: request[key] for key in ("period", "accession_number", "form_type", "filing_date", "issuer_cik")}
    target.update(quarterly_index_sha256=request["master_decoded_sha256"], complete_submission_url=request["url"])
    _need(type(value["pre_normalization_target"]) is dict and value["pre_normalization_target"] == target,
        "selection_pre_normalization_target_binding")
    _digest(value["compiler_disposition_sha256"])
    return source


def validate_selection_payload(value):
    """Strict detached IPC metadata; NEVER creates a factory/custody seal.

    Production consumers must additionally hold externally pinned completed
    protected-runner controls and source/operational inputs. A shaped dict or
    passing contract does not prove genuine execution, freshness, or rights.
    """
    try:
        _need(type(value) is dict and set(value) == _RESULT_KEYS and value["schema"] == SCHEMA
            and type(value["fixture_only"]) is bool and value["selection_period"] == PERIOD
            and type(value["selection_limit"]) is int and value["selection_limit"] == LIMIT
            and type(value["selected_count"]) is int and value["selected_count"] == LIMIT
            and value["selection_policy"] == POLICY, "selection_payload_schema")
        audit._authority(value["authority"])
        for key in ("dispatch_authorized", "canonical_admitted", "backtesting_ready"):
            _need(value[key] is False, "selection_authority_required_false")
        for key in ("new_provider_requests", "credential_reads", "qc_jobs", "outcome_looks", "backtests"):
            _need(type(value[key]) is int and value[key] == 0, "selection_access_required_zero")
        for key in ("all_25_quarters_finished", "complete_source_population_is_not_complete_parent_corpus",
                "no_earlier_or_later_quarter_substitution", "separate_diagnostic_does_not_resolve_original_ambiguous_start"):
            _need(value[key] is True, "selection_scope_qualification_missing")
        for key in ("source_roster_sha256", "parent_audit_sha256", "exposure_inventory_sha256", "retained_candidate_inventory_sha256",
                "full_source_row_jsonl_sha256", "full_disposition_jsonl_sha256", "full_fresh_request_jsonl_sha256",
                "selected_request_jsonl_sha256", "selected_metadata_jsonl_sha256"):
            _digest(value[key])
        for key in ("selection_period_observed_fresh_count", "selection_period_suppressed_late_repeat_count",
                "selection_period_eligible_after_global_suppression_count", "global_consumed_accessions", "global_repeat_accessions_observed"):
            _integer(value[key])
        _need(value["selection_period_observed_fresh_count"] - value["selection_period_suppressed_late_repeat_count"]
            == value["selection_period_eligible_after_global_suppression_count"] >= LIMIT, "selection_full_eligibility_conservation")
        quarters = value["quarter_bindings"]
        _need(type(quarters) is list and [quarter["period"] for quarter in quarters] == list(audit.PERIODS),
            "selection_complete_25quarter_bindings")
        quarter_keys = {"period", "counts", "source_form_counts", "source_row_jsonl_sha256", "source_row_jsonl_bytes",
            "disposition_jsonl_sha256", "disposition_jsonl_bytes", "fresh_request_jsonl_sha256", "fresh_request_jsonl_bytes"}
        for quarter in quarters:
            _need(type(quarter) is dict and set(quarter) == quarter_keys
                and type(quarter["counts"]) is dict and set(quarter["counts"]) == set(audit._COUNTS)
                and type(quarter["source_form_counts"]) is dict and set(quarter["source_form_counts"]) == set(audit.FORMS),
                "selection_quarter_schema")
            for count in (*quarter["counts"].values(), *quarter["source_form_counts"].values()): _integer(count, maximum=audit.MAX_QUARTER_ROWS)
            counts = quarter["counts"]
            _need(sum(quarter["source_form_counts"].values()) == counts["source_filings"]
                == counts["target_filings"] + counts["context_filings"]
                and counts["target_filings"] == counts["prior_consumed_targets"] + counts["no_prior_dispatch_observed_targets"]
                and counts["target_filings"] == counts["locator_qualified_targets"] + counts["locator_quarantined_targets"],
                "selection_quarter_conservation")
            for stem in ("source_row", "disposition", "fresh_request"):
                _digest(quarter[stem + "_jsonl_sha256"])
                _integer(quarter[stem + "_jsonl_bytes"], maximum=2**40)
        aggregate = lambda selected: {key: sum(row["counts"][key] for row in selected) for key in audit._COUNTS}
        for key, selected in (("parent_context_counts", quarters), ("parent_pilot_counts", [q for q in quarters if q["period"] in audit.PILOT_PERIODS])):
            _need(type(value[key]) is dict and value[key] == aggregate(selected)
                and all(type(count) is int for count in value[key].values()), "selection_full_parent_count_binding")
        source_counts = value["source_roster_counts"]
        expected_source = {"context_quarters": 25, "pilot_quarters": 20,
            "context_submission_rows": value["parent_context_counts"]["source_filings"],
            "context_form4_or_4a_rows": value["parent_context_counts"]["target_filings"],
            "pilot_submission_rows": value["parent_pilot_counts"]["source_filings"],
            "pilot_form4_or_4a_rows": value["parent_pilot_counts"]["target_filings"]}
        _need(type(source_counts) is dict and source_counts == expected_source
            and all(type(count) is int for count in source_counts.values()), "selection_full_roster_count_binding")
        if value["fixture_only"] is False:
            _need(source_counts == {"context_quarters": 25, "pilot_quarters": 20, "context_submission_rows": 1281147,
                "context_form4_or_4a_rows": 1163648, "pilot_submission_rows": 1008318, "pilot_form4_or_4a_rows": 921570},
                "selection_recorded_actual_population_counts")
        period_counts = next(q["counts"] for q in quarters if q["period"] == PERIOD)
        _need(value["selection_period_observed_fresh_count"] == period_counts["fresh_locatable_candidate_requests"],
            "selection_period_fresh_count_binding")
        for stem in ("source_row", "disposition", "fresh_request"):
            key = "full_" + stem + "_jsonl_bytes"
            _need(type(value[key]) is int and value[key] == sum(q[stem + "_jsonl_bytes"] for q in quarters),
                "selection_full_stream_byte_binding")
        records = value["requests"]
        _need(type(records) is list and len(records) == LIMIT, "selection_exact_64_requests")
        seen, previous, request_hash, metadata_hash, request_bytes, metadata_bytes = set(), 0, hashlib.sha256(), hashlib.sha256(), 0, 0
        for ordinal, item in enumerate(records, 1):
            source = _request_record(item, ordinal)
            _need(source["source_record_ordinal"] > previous and source["accession_number"] not in seen,
                "selection_source_order_or_repeat")
            seen.add(source["accession_number"]);previous = source["source_record_ordinal"]
            encoded_request, encoded_metadata = _raw(item["request"]) + b"\n", _raw(item) + b"\n"
            request_hash.update(encoded_request);metadata_hash.update(encoded_metadata)
            request_bytes += len(encoded_request);metadata_bytes += len(encoded_metadata)
        _need(value["selected_request_jsonl_sha256"] == request_hash.hexdigest()
            and type(value["selected_request_jsonl_bytes"]) is int and value["selected_request_jsonl_bytes"] == request_bytes
            and value["selected_metadata_jsonl_sha256"] == metadata_hash.hexdigest()
            and type(value["selected_metadata_jsonl_bytes"]) is int and value["selected_metadata_jsonl_bytes"] == metadata_bytes,
            "selection_prefix_stream_binding")
        raw = _raw(value)
        _need(len(raw) <= MAX_OUTPUT_BYTES, "selection_output_byte_bound")
        return json.loads(raw)
    except PilotSecFreshSelectionError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError, StopIteration):
        raise PilotSecFreshSelectionError("selection_metadata_refused") from None


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class PilotSecFreshSelection:
    _bytes: bytes = field(repr=False)
    _token: object = field(repr=False)

    def canonical_bytes(self):
        _need(type(self) is PilotSecFreshSelection and self._token is _TOKEN and _SEALS.get(self) == self._bytes,
            "genuine_unchanged_fresh_selection_required")
        return self._bytes

    def to_payload(self): return json.loads(self.canonical_bytes())
    @property
    def sha256(self): return _sha(self.canonical_bytes())


def validate_pilot_sec_fresh_selection(value):
    _need(type(value) is PilotSecFreshSelection, "exact_fresh_selection_factory_required")
    value.canonical_bytes()
    return value


class PilotSecFreshSelectionBuilder:
    """Receive the compiler's detached emissions, never source paths/transport.

    Eligible 2021Q1 metadata is provisional until every later source occurrence
    has been checked. Retain that bounded quarter to refill the first64 after
    suppressing late repeats; an early prefix or another quarter is no substitute.
    """
    def __init__(self):
        self._failed = self._closed = self._busy = False
        self._source_hash, self._ledger_hash, self._queue_hash = (hashlib.sha256() for _ in range(3))
        self._source_bytes = self._ledger_bytes = self._queue_bytes = self._eligible_bytes = 0
        self._quarters, self._eligible, self._blocked, self._repeated = {}, [], set(), set()
        self._period = None

    def _active(self):
        _need(not self._failed and not self._closed and not self._busy, "fresh_selection_builder_not_active")

    def consume(self, disposition):
        self._active();self._busy = True
        try:
            _need(type(disposition) is dict and set(disposition) == _DISPOSITION_KEYS
                and disposition["schema"] == audit.SCHEMA + "/filing", "fresh_disposition_schema")
            source, source_line = audit._source(disposition["source"])
            _need(disposition["source_record_sha256"] == source["filing_metadata_sha256"], "fresh_disposition_source_hash")
            for key in ("relevant_parent_target", "prior_consumed", "cross_quarter_accession_repeat",
                    "cross_quarter_source_identity_conflict", "historical_ambiguous_start_preserved", "retained_candidate_body_identity_conflict",
                    "body_candidate_is_not_parent_admission", "complete_parent_parsed_here", "fresh_locatable_candidate",
                    "dispatch_authorized", "canonical_admitted"):
                _need(type(disposition[key]) is bool, "fresh_disposition_boolean_required")
            _need(disposition["dispatch_authorized"] is False and disposition["canonical_admitted"] is False
                and disposition["complete_parent_parsed_here"] is False and disposition["body_candidate_is_not_parent_admission"] is True,
                "fresh_disposition_authority_refused")
            period, accession = source["period"], source["accession_number"]
            if period != self._period:
                _need(self._period is None or audit.PERIODS.index(period) > audit.PERIODS.index(self._period), "fresh_source_quarter_order")
                self._period = period
                self._quarters[period] = {"rows": 0, "source_hash": hashlib.sha256(), "source_bytes": 0,
                    "ledger_hash": hashlib.sha256(), "ledger_bytes": 0, "queue_hash": hashlib.sha256(), "queue_bytes": 0}
            quarter = self._quarters[period]
            _need(source["source_record_ordinal"] == quarter["rows"] + 1, "fresh_source_ordinal_gap")
            if disposition["prior_consumed"] or disposition["historical_ambiguous_start_preserved"]:
                self._blocked.add(accession)
            if disposition["cross_quarter_accession_repeat"]:
                self._blocked.add(accession);self._repeated.add(accession)
            ledger_line = _raw(disposition) + b"\n"
            _need(len(ledger_line) <= audit.MAX_ROW_BYTES * (audit.MAX_EVIDENCE_PER_ACCESSION + 2), "fresh_ledger_byte_bound")
            self._source_hash.update(source_line);self._source_bytes += len(source_line)
            self._ledger_hash.update(ledger_line);self._ledger_bytes += len(ledger_line)
            quarter["source_hash"].update(source_line);quarter["source_bytes"] += len(source_line)
            quarter["ledger_hash"].update(ledger_line);quarter["ledger_bytes"] += len(ledger_line);quarter["rows"] += 1
            if disposition["fresh_locatable_candidate"]:
                request_line = _raw(disposition["request"]) + b"\n"
                self._queue_hash.update(request_line);self._queue_bytes += len(request_line)
                quarter["queue_hash"].update(request_line);quarter["queue_bytes"] += len(request_line)
                if period == PERIOD:
                    _need(disposition["relevant_parent_target"] is True and source["form_type"] in {"4", "4/A"}
                        and disposition["prior_consumed"] is False and disposition["prior_exposure_evidence"] == []
                        and disposition["historical_ambiguous_start_preserved"] is False
                        and disposition["cross_quarter_accession_repeat"] is False
                        and disposition["cross_quarter_source_identity_conflict"] is False
                        and disposition["prior_source_occurrence"] is None
                        and disposition["matching_retained_candidates"] == [] and disposition["candidate_identity_conflicts"] == []
                        and disposition["retained_candidate_body_identity_conflict"] is False
                        and disposition["disposition"] == "no_prior_dispatch_observed_locatable_candidate"
                        and disposition["locator_quarantine_reasons"] == [], "fresh_candidate_consumption_or_locator_conflict")
                    value = {"selection_ordinal": 1, "source": source, "source_record_sha256": source["filing_metadata_sha256"],
                        "request": disposition["request"], "request_sha256": disposition["request_sha256"],
                        "pre_normalization_target": disposition["pre_normalization_target"], "selected_locator": disposition["selected_locator"],
                        "compiler_disposition_sha256": _sha(ledger_line[:-1]), "dispatch_authorized": False, "canonical_admitted": False}
                    _request_record(value, 1)
                    encoded = _raw(value)
                    self._eligible_bytes += len(encoded)
                    _need(len(self._eligible) < audit.MAX_QUARTER_ROWS and self._eligible_bytes <= MAX_ELIGIBLE_METADATA_BYTES,
                        "fresh_quarter_metadata_bound")
                    self._eligible.append(encoded)
        except BaseException:
            self._failed = True
            raise
        finally:
            self._busy = False

    def finish(self, *, roster, audit, expected_roster_sha256, expected_audit_sha256):
        self._active();self._busy = True
        try:
            # Names shadow only caller objects; validation uses the fixed pure modules.
            source = globals()["roster"].validate_pilot_sec_roster(roster)
            completed = globals()["audit"].validate_pilot_sec_parent_audit(audit)
            _need(source.sha256 == _digest(expected_roster_sha256) and audit.sha256 == _digest(expected_audit_sha256),
                "fresh_external_completed_factory_pins")
            body = source.to_payload()
            _need(completed["source_roster_sha256"] == source.sha256 and body["fixture_only"] is completed["fixture_only"]
                and list(self._quarters) == list(globals()["audit"].PERIODS), "fresh_complete_25quarter_factories")
            for stem, observed_hash, observed_bytes in (("source_row", self._source_hash, self._source_bytes),
                    ("disposition", self._ledger_hash, self._ledger_bytes), ("fresh_request", self._queue_hash, self._queue_bytes)):
                _need(completed[stem + "_jsonl_sha256"] == observed_hash.hexdigest()
                    and completed[stem + "_jsonl_bytes"] == observed_bytes, "fresh_full_completed_stream_binding")
            _need(body["source_row_jsonl_sha256"] == self._source_hash.hexdigest()
                and body["source_row_jsonl_bytes"] == self._source_bytes, "fresh_full_roster_stream_binding")
            for expected in completed["quarters"]:
                quarter = self._quarters[expected["period"]]
                _need(quarter["rows"] == expected["counts"]["source_filings"], "fresh_quarter_row_conservation")
                for stem, field in (("source_row", "source"), ("disposition", "ledger"), ("fresh_request", "queue")):
                    _need(quarter[field + "_hash"].hexdigest() == expected[stem + "_jsonl_sha256"]
                        and quarter[field + "_bytes"] == expected[stem + "_jsonl_bytes"], "fresh_quarter_stream_binding")
            selected, eligible_count = [], 0
            for raw in self._eligible:
                candidate = json.loads(raw)
                if candidate["source"]["accession_number"] in self._blocked:
                    continue
                eligible_count += 1
                if len(selected) < LIMIT:
                    selected.append(candidate)
            _need(eligible_count >= LIMIT, "fresh_2021Q1_prefix_underfilled")
            request_bytes, metadata_bytes = bytearray(), bytearray()
            for ordinal, row in enumerate(selected, 1):
                row["selection_ordinal"] = ordinal
                request_bytes.extend(_raw(row["request"]) + b"\n");metadata_bytes.extend(_raw(row) + b"\n")
            result = {"schema": SCHEMA, "fixture_only": body["fixture_only"], "selection_period": PERIOD,
                "selection_limit": LIMIT, "selected_count": LIMIT, "selection_policy": POLICY, "requests": selected,
                "source_roster_sha256": source.sha256, "parent_audit_sha256": audit.sha256,
                "exposure_inventory_sha256": completed["exposure_inventory_sha256"],
                "retained_candidate_inventory_sha256": completed["retained_candidate_inventory_sha256"],
                "source_roster_counts": body["counts"], "parent_context_counts": completed["context_counts"],
                "parent_pilot_counts": completed["pilot_counts"], "quarter_bindings": completed["quarters"],
                "full_source_row_jsonl_sha256": self._source_hash.hexdigest(), "full_source_row_jsonl_bytes": self._source_bytes,
                "full_disposition_jsonl_sha256": self._ledger_hash.hexdigest(), "full_disposition_jsonl_bytes": self._ledger_bytes,
                "full_fresh_request_jsonl_sha256": self._queue_hash.hexdigest(), "full_fresh_request_jsonl_bytes": self._queue_bytes,
                "selected_request_jsonl_sha256": _sha(bytes(request_bytes)), "selected_request_jsonl_bytes": len(request_bytes),
                "selected_metadata_jsonl_sha256": _sha(bytes(metadata_bytes)), "selected_metadata_jsonl_bytes": len(metadata_bytes),
                "selection_period_observed_fresh_count": len(self._eligible),
                "selection_period_suppressed_late_repeat_count": len(self._eligible) - eligible_count,
                "selection_period_eligible_after_global_suppression_count": eligible_count,
                "global_consumed_accessions": completed["global_consumed_accessions"], "global_repeat_accessions_observed": len(self._repeated),
                "all_25_quarters_finished": True, "complete_source_population_is_not_complete_parent_corpus": True,
                "no_earlier_or_later_quarter_substitution": True, "separate_diagnostic_does_not_resolve_original_ambiguous_start": True,
                "authority": dict(globals()["audit"]._AUTHORITY), "dispatch_authorized": False, "canonical_admitted": False,
                "backtesting_ready": False, "new_provider_requests": 0, "credential_reads": 0, "qc_jobs": 0,
                "outcome_looks": 0, "backtests": 0}
            raw = _raw(validate_selection_payload(result))
            value = PilotSecFreshSelection(raw, _TOKEN);_SEALS[value] = raw
            self._closed = True
            return validate_pilot_sec_fresh_selection(value)
        except PilotSecFreshSelectionError:
            self._failed = True
            raise
        except Exception:
            self._failed = True
            raise PilotSecFreshSelectionError("fresh_completed_selection_refused") from None
        finally:
            self._busy = False
