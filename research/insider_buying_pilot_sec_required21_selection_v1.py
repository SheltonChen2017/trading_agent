"""Pure first-eight required-window selection after complete context accounting.

All 25 supplied source quarters pass through the existing genuine roster/audit
factories. Only 2020Q4--2025Q4 may enter this bounded request prefix. Every
known consumed/reserved/ambiguous accession is excluded, and a later repeat
of a selected prefix row refuses the whole selection instead of silently
refilling it. This module performs no file, contact, network or source reads.
An application must independently authenticate the supplied consumption root;
neither a factory seal nor a source census grants dispatch or admission.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import weakref

from research import insider_buying_pilot_sec_parent_campaign_v2 as baseline


audit, roster, fresh = baseline.audit, baseline.roster, baseline.fresh
SCHEMA = "insider-pilot-sec-required21-selection-v1"
CONTEXT_PERIODS = tuple(audit.PERIODS)
REQUIRED_PERIODS = tuple(period for period in CONTEXT_PERIODS if "2020Q4" <= period <= "2025Q4")
MAX_SELECTED = 8
MAX_CONSUMED = audit.MAX_EXPOSURES
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
POLICY = {"context_periods": list(CONTEXT_PERIODS), "required_periods": list(REQUIRED_PERIODS),
    "order": "quarter_then_original_source_ordinal_not_financial_values", "maximum_selected": MAX_SELECTED,
    "known_consumed_reserved_ambiguous_excluded": True, "late_selected_repeat": "whole_selection_refusal_no_refill",
    "source_census_is_not_original_admission": True, "historical_lot_context_supplied": False}
_raw, _sha = audit._raw, audit._sha
_TOKEN = object()
_SEALS = weakref.WeakKeyDictionary()
_STEMS = ("source_row", "disposition", "fresh_request")


class Required21SelectionError(ValueError):
    """Fixed finite metadata refusals, never supplied source text."""


def _need(ok, code):
    if not ok:
        raise Required21SelectionError(code)


def _digest(value):
    _need(type(value) is str and audit._SHA.fullmatch(value) is not None, "exact_digest_required")
    return value


def _copy(value):
    return json.loads(_raw(value))


def _count(value, maximum=25 * audit.MAX_QUARTER_ROWS):
    _need(type(value) is int and 0 <= value <= maximum, "exact_bounded_count_required")
    return value


def _consumed(values):
    _need(type(values) is tuple and len(values) <= MAX_CONSUMED
          and all(type(value) is str and audit._ACCESSION.fullmatch(value) for value in values)
          and values == tuple(sorted(set(values))), "exact_ordered_consumed_accessions_required")
    return values


def _totals(quarters):
    return {key: sum(row["counts"][key] for row in quarters) for key in audit._COUNTS}


def validate_selection_payload(value):
    """Validate detached IPC metadata without minting a genuine factory seal."""
    try:
        expected = {"schema", "fixture_only", "limit", "selected_count", "underfilled", "requests", "policy", "authority",
            "source_roster_sha256", "parent_audit_sha256", "consumption_sha256", "consumed_accessions_sha256",
            "consumed_accessions", "source_roster_counts", "parent_context_counts", "required21_counts", "quarter_bindings",
            "required21_provisional_fresh_count", "selected_request_jsonl_sha256", "selected_request_jsonl_bytes",
            "consumption_authenticity_verified_here", "dispatch_authorized", "canonical_admitted"}
        expected.update(stem + suffix for stem in _STEMS for suffix in ("_jsonl_sha256", "_jsonl_bytes"))
        _need(type(value) is dict and set(value) == expected and value["schema"] == SCHEMA,
              "selection_exact_schema_required")
        _need(type(value["fixture_only"]) is bool and type(value["limit"]) is int and 1 <= value["limit"] <= MAX_SELECTED,
              "selection_scope_or_limit_refused")
        _need(_raw(value["policy"]) == _raw(POLICY) and _raw(value["authority"]) == _raw(audit._AUTHORITY)
              and value["consumption_authenticity_verified_here"] is value["dispatch_authorized"] is value["canonical_admitted"] is False,
              "selection_authority_or_policy_refused")
        consumed = _consumed(tuple(value["consumed_accessions"])) if type(value["consumed_accessions"]) is list else None
        _need(consumed is not None and value["consumed_accessions_sha256"] == _sha(_raw(list(consumed))), "selection_consumed_index_refused")
        for name, field_value in value.items():
            if name.endswith("sha256"):
                _digest(field_value)
            elif name.endswith("_bytes"):
                _count(field_value, 128 * 1024 ** 3)
        quarters = value["quarter_bindings"]
        _need(type(quarters) is list and len(quarters) == 25 and [row["period"] for row in quarters] == list(CONTEXT_PERIODS),
              "complete_25quarter_bindings_required")
        quarter_keys = {"period", "counts", "source_form_counts"} | {stem + suffix for stem in _STEMS for suffix in ("_jsonl_sha256", "_jsonl_bytes")}
        for row in quarters:
            _need(type(row) is dict and set(row) == quarter_keys and set(row["counts"]) == set(audit._COUNTS)
                  and set(row["source_form_counts"]) == set(audit.FORMS), "quarter_conservation_schema_refused")
            for number in (*row["counts"].values(), *row["source_form_counts"].values()):
                _count(number)
            counts, forms = row["counts"], row["source_form_counts"]
            _need(sum(forms.values()) == counts["source_filings"]
                  and forms["4"] + forms["4/A"] == counts["target_filings"]
                  and counts["source_filings"] == counts["context_filings"] + counts["target_filings"]
                  and counts["target_filings"] == counts["prior_consumed_targets"] + counts["no_prior_dispatch_observed_targets"]
                  and counts["target_filings"] == counts["locator_qualified_targets"] + counts["locator_quarantined_targets"],
                  "quarter_source_form_conservation_refused")
            for stem in _STEMS:
                _digest(row[stem + "_jsonl_sha256"]); _count(row[stem + "_jsonl_bytes"], 128 * 1024 ** 3)
        _need(_raw(value["parent_context_counts"]) == _raw(_totals(quarters))
              and _raw(value["required21_counts"]) == _raw(_totals([row for row in quarters if row["period"] in REQUIRED_PERIODS])),
              "required_context_count_conservation_refused")
        source_counts = value["source_roster_counts"]
        _need(type(source_counts) is dict and set(source_counts) == {"context_quarters", "pilot_quarters", "context_submission_rows",
            "context_form4_or_4a_rows", "pilot_submission_rows", "pilot_form4_or_4a_rows"}, "source_roster_count_schema_refused")
        _need(_raw(source_counts) == _raw({"context_quarters": 25, "pilot_quarters": 20,
            "context_submission_rows": sum(row["counts"]["source_filings"] for row in quarters),
            "context_form4_or_4a_rows": sum(row["counts"]["target_filings"] for row in quarters),
            "pilot_submission_rows": sum(row["counts"]["source_filings"] for row in quarters if row["period"] in audit.PILOT_PERIODS),
            "pilot_form4_or_4a_rows": sum(row["counts"]["target_filings"] for row in quarters if row["period"] in audit.PILOT_PERIODS)}),
            "source_roster_counts_differ")
        rows = value["requests"]
        _need(type(rows) is list and type(value["selected_count"]) is int and len(rows) == value["selected_count"] <= value["limit"]
              and type(value["underfilled"]) is bool and value["underfilled"] is (len(rows) < value["limit"]), "selection_underfill_or_count_refused")
        _count(value["required21_provisional_fresh_count"])
        _need(value["required21_provisional_fresh_count"] <= value["required21_counts"]["fresh_locatable_candidate_requests"]
              and len(rows) == min(value["limit"], value["required21_provisional_fresh_count"]), "bounded_prefix_count_refused")
        previous, seen = (-1, 0), set()
        for ordinal, row in enumerate(rows, 1):
            original = baseline._record(row, ordinal)
            order = CONTEXT_PERIODS.index(original["period"]), original["source_record_ordinal"]
            _need(original["period"] in REQUIRED_PERIODS and order > previous and original["accession_number"] not in seen
                  and original["accession_number"] not in consumed, "required21_source_order_or_freshness_refused")
            previous = order; seen.add(original["accession_number"])
        lines = b"".join(_raw(row["request"]) + b"\n" for row in rows)
        _need(value["selected_request_jsonl_sha256"] == _sha(lines) and value["selected_request_jsonl_bytes"] == len(lines),
              "selected_request_stream_root_refused")
        _need(len(_raw(value)) <= MAX_OUTPUT_BYTES, "selection_output_byte_bound_refused")
        return _copy(value)
    except Required21SelectionError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise Required21SelectionError("selection_payload_refused") from None


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class Required21Selection:
    _bytes: bytes = field(repr=False)
    _token: object = field(repr=False)

    def canonical_bytes(self):
        _need(type(self) is Required21Selection and self._token is _TOKEN and _SEALS.get(self) == self._bytes,
              "genuine_unchanged_required21_selection_required")
        return self._bytes

    def to_payload(self):
        return json.loads(self.canonical_bytes())

    @property
    def sha256(self):
        return _sha(self.canonical_bytes())


def validate_required21_selection(value):
    _need(type(value) is Required21Selection, "exact_required21_selection_required")
    return value.to_payload()


class Required21SelectionBuilder:
    """Bounded prefix over a complete compiler stream, never partial success."""
    def __init__(self, *, consumed_accessions, consumption_sha256, limit=MAX_SELECTED):
        self.consumed = _consumed(consumed_accessions)
        self.consumption_sha256 = _digest(consumption_sha256)
        _need(type(limit) is int and 1 <= limit <= MAX_SELECTED, "selection_limit_refused")
        self.limit, self.closed = limit, False
        self.hashes = {stem: hashlib.sha256() for stem in _STEMS}
        self.sizes = {stem: 0 for stem in _STEMS}
        self.quarters, self.selected, self.blocked = {}, [], set(self.consumed)
        self.period, self.eligible = None, 0

    def consume(self, supplied):
        _need(not self.closed, "selection_builder_closed")
        self.closed = True
        try:
            _need(type(supplied) is dict and set(supplied) == fresh._DISPOSITION_KEYS, "exact_compiler_disposition_required")
            row = _copy(supplied)
            original, source_line = audit._source(row["source"])
            period, accession = original["period"], original["accession_number"]
            _need(row["schema"] == audit.SCHEMA + "/filing" and row["source_record_sha256"] == original["filing_metadata_sha256"]
                  and row["dispatch_authorized"] is row["canonical_admitted"] is False, "source_disposition_binding_refused")
            for key in ("prior_consumed", "historical_ambiguous_start_preserved", "cross_quarter_accession_repeat",
                        "cross_quarter_source_identity_conflict", "fresh_locatable_candidate"):
                _need(type(row[key]) is bool, "typed_compiler_flags_required")
            _need(self.period is None or period == self.period or CONTEXT_PERIODS.index(period) > CONTEXT_PERIODS.index(self.period),
                  "source_quarter_rollback_refused")
            self.period = period
            quarter = self.quarters.setdefault(period, {"count": 0, **{stem: hashlib.sha256() for stem in _STEMS}, **{stem + "_bytes": 0 for stem in _STEMS}})
            _need(list(self.quarters) == list(CONTEXT_PERIODS[:len(self.quarters)])
                  and original["source_record_ordinal"] == quarter["count"] + 1, "complete_source_order_required")
            quarter["count"] += 1
            if any(row[key] for key in ("prior_consumed", "historical_ambiguous_start_preserved", "cross_quarter_accession_repeat", "cross_quarter_source_identity_conflict")):
                self.blocked.add(accession)
            lines = {"source_row": source_line, "disposition": _raw(row) + b"\n",
                     "fresh_request": _raw(row["request"]) + b"\n" if row["fresh_locatable_candidate"] else b""}
            for stem, line in lines.items():
                self.hashes[stem].update(line); self.sizes[stem] += len(line)
                quarter[stem].update(line); quarter[stem + "_bytes"] += len(line)
            if period in REQUIRED_PERIODS and row["fresh_locatable_candidate"] and accession not in self.blocked:
                _need(row["relevant_parent_target"] is True and original["form_type"] in {"4", "4/A"}
                      and row["prior_exposure_evidence"] == row["matching_retained_candidates"] == row["candidate_identity_conflicts"] == []
                      and row["prior_source_occurrence"] is None and row["retained_candidate_body_identity_conflict"] is False
                      and row["locator_quarantine_reasons"] == [] and row["disposition"] == "no_prior_dispatch_observed_locatable_candidate",
                      "fresh_candidate_full_disposition_required")
                self.eligible += 1
                if len(self.selected) < self.limit:
                    item = {"selection_ordinal": len(self.selected) + 1, "source": original,
                        "source_record_sha256": row["source_record_sha256"], **{key: row[key] for key in
                            ("request", "request_sha256", "pre_normalization_target", "selected_locator")},
                        "compiler_disposition_sha256": _sha(lines["disposition"][:-1]), "dispatch_authorized": False, "canonical_admitted": False}
                    baseline._record(item, len(self.selected) + 1)
                    self.selected.append(_copy(item))
            self.closed = False
        except Required21SelectionError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
            raise Required21SelectionError("compiler_stream_refused") from None

    def finish(self, *, source_roster, parent_audit, expected_roster_sha256, expected_audit_sha256):
        _need(not self.closed, "selection_builder_closed"); self.closed = True
        try:
            genuine = roster.validate_pilot_sec_roster(source_roster)
            completed = audit.validate_pilot_sec_parent_audit(parent_audit)
            source = genuine.to_payload()
            _need(genuine.sha256 == _digest(expected_roster_sha256) and parent_audit.sha256 == _digest(expected_audit_sha256)
                  and completed["source_roster_sha256"] == genuine.sha256 and completed["fixture_only"] is source["fixture_only"]
                  and list(self.quarters) == list(CONTEXT_PERIODS), "complete_genuine_source_factories_required")
            for stem in _STEMS:
                _need(completed[stem + "_jsonl_sha256"] == self.hashes[stem].hexdigest()
                      and completed[stem + "_jsonl_bytes"] == self.sizes[stem], "complete_compiler_stream_binding_required")
            _need(source["source_row_jsonl_sha256"] == self.hashes["source_row"].hexdigest()
                  and source["source_row_jsonl_bytes"] == self.sizes["source_row"], "complete_roster_stream_binding_required")
            for expected in completed["quarters"]:
                quarter = self.quarters[expected["period"]]
                _need(quarter["count"] == expected["counts"]["source_filings"] and all(
                    quarter[stem].hexdigest() == expected[stem + "_jsonl_sha256"] and quarter[stem + "_bytes"] == expected[stem + "_jsonl_bytes"]
                    for stem in _STEMS), "quarter_stream_conservation_required")
            _need(not any(item["request"]["accession_number"] in self.blocked for item in self.selected), "late_selected_repeat_requires_reconciliation")
            lines = b"".join(_raw(row["request"]) + b"\n" for row in self.selected)
            payload = {"schema": SCHEMA, "fixture_only": source["fixture_only"], "limit": self.limit,
                "selected_count": len(self.selected), "underfilled": len(self.selected) < self.limit, "requests": self.selected,
                "policy": POLICY, "authority": dict(audit._AUTHORITY), "source_roster_sha256": genuine.sha256,
                "parent_audit_sha256": parent_audit.sha256, "consumption_sha256": self.consumption_sha256,
                "consumed_accessions_sha256": _sha(_raw(list(self.consumed))), "consumed_accessions": list(self.consumed),
                "source_roster_counts": source["counts"], "parent_context_counts": completed["context_counts"],
                "required21_counts": _totals([row for row in completed["quarters"] if row["period"] in REQUIRED_PERIODS]),
                "quarter_bindings": completed["quarters"], "required21_provisional_fresh_count": self.eligible,
                "selected_request_jsonl_sha256": _sha(lines), "selected_request_jsonl_bytes": len(lines),
                "consumption_authenticity_verified_here": False, "dispatch_authorized": False, "canonical_admitted": False,
                **{stem + suffix: self.hashes[stem].hexdigest() if suffix == "_jsonl_sha256" else self.sizes[stem]
                   for stem in _STEMS for suffix in ("_jsonl_sha256", "_jsonl_bytes")}}
            validated = validate_selection_payload(payload)
            result = Required21Selection(_raw(validated), _TOKEN); _SEALS[result] = result._bytes
            return result
        except Required21SelectionError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
            raise Required21SelectionError("selection_finish_refused") from None
