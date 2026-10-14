"""Ignored compact DAILY issuer context, not signal/outcome/admission.

One ordered pass builds source-bound CIK offsets and request-target tickets.
No caller dictionaries or settlement snapshots substitute for the exact typed
active-only daily reports. Existing FMP V1 context and runtime stay unchanged.
"""
from __future__ import annotations

import json
import struct
from types import MappingProxyType

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_daily_active_reference as daily
import research.short_interest_etf.fmp_company_context as context

MAXIMUM_TOTAL_RESPONSE_BYTES = 3 * 1024 ** 3
MAXIMUM_INDEX_BYTES = 512 * 1024 ** 2
_CELL = struct.Struct("<HHHIIII")
_ORDINAL = struct.Struct("<I")


def policy():
    return {"schema": "si-indexed-daily-FMP-company-cap-draft-v2",
        "daily_policy_sha256": hash_payload(daily.daily_active_policy()),
        "context_policy_sha256": hash_payload(context.policy()),
        "source_pass": "one_exact_ordered_1169_typed_active_only_reports_same_original_master_index",
        "index": "packed_cells_per_CIK_u32_offsets_and_per_target_observed_date_bits_no_N_times_rows_scan",
        "maximum_index_bytes": MAXIMUM_INDEX_BYTES,
        "selection": "latest_observed_dated_source_then_lexical_ticker_class_native_one_exact_target_per_CIK",
        "selection_not_primary_class_or_current_identity_proof": True,
        "requests": "at_most_one_CIK_lookup_then_one_cap_GET_per_selected_CIK_no_alternate_target_or_retries",
        "maximum_total_response_bytes": MAXIMUM_TOTAL_RESPONSE_BYTES,
        "budget": "new_exclusive_claim_reserve_1MiB50rows_lookup_or8MiB5000rows_cap_before_START_no_reuse_of_old_claims",
        "account_trailing_bandwidth_remaining_not_verified_by_factory": True,
        "currency": "same_exact_day_target_CIK_usd_source_assertion_required_old_alias_CIK_alone_is_not_USD",
        "source_refusals": "all_rows_remain_in_each_pinned_complete_daily_source_report_no_outcome_pruning",
        "authority": context._authority()}


class DailyIssuerIndex:
    __slots__ = ("_header", "_cells", "_pool", "_offsets", "_target_bits", "_selected", "_selected_map", "_plan", "_index", "_anchor", "_identity")

    def __init__(self):
        raise context.FmpContextError("REFUSED: complete_daily_index_factory_required")

    def _guard(self):
        names = ("_header", "_cells", "_pool", "_offsets", "_target_bits", "_selected", "_selected_map", "_plan", "_index")
        context._require(type(self) is DailyIssuerIndex and type(self._anchor) is tuple and len(self._anchor) == len(names)
            and self._anchor is self._identity and all(getattr(self, name) is old for name, old in zip(names, self._anchor)),
            "sealed_daily_issuer_index_changed")
        self._plan._guard(); self._index._guard()

    @property
    def sha256(self):
        self._guard()
        return hash_bytes(len(self._header).to_bytes(8, "big") + self._header + self._cells)

    def header(self):
        self._guard()
        return json.loads(self._header)

    def selected(self):
        self._guard()
        return self._selected

    def iter_cik_rows(self, cik):
        self._guard()
        canonical = context._cik(cik)
        offsets = self._offsets.get(canonical, b"")
        for at in range(0, len(offsets), _ORDINAL.size):
            self._guard()
            ordinal, = _ORDINAL.unpack_from(offsets, at)
            day, page, row, native, cls, ticker, company = _CELL.unpack_from(self._cells, ordinal * _CELL.size)
            yield (day, page, row, self._pool[native], self._pool[cls], self._pool[ticker], self._pool[company])

    def target_observed(self, cik, symbol, day_ordinal):
        self._guard()
        context._require(type(day_ordinal) is int and 1 <= day_ordinal <= daily.EXPECTED_SESSIONS, "exact_source_day_required")
        return bool(self._target_bits.get((context._cik(cik), symbol), 0) & (1 << (day_ordinal - 1)))

    def private_parts(self):
        self._guard()
        yield "header.private.json", self._header
        self._guard()
        yield "cells.private.bin", self._cells


def build_daily_issuer_index(plan, reports):
    context._require(type(plan) is daily.DailyActiveReferencePlan, "exact_daily_active_plan_required")
    pool, token_ids, cells, offsets, target_bits, selected, source_days = [], {}, bytearray(), {}, {}, {}, []
    original = None
    def token(value):
        if value not in token_ids:
            context._require(len(pool) < 2 ** 32, "bounded_native_token_pool")
            token_ids[value] = len(pool)
            pool.append(value)
        return token_ids[value]
    count, indexed_bytes = 0, 0
    for count, report in enumerate(reports, 1):
        context._require(count <= daily.EXPECTED_SESSIONS and type(report) is daily.DailyActiveReferenceQualification,
                         "only_exact_daily_active_reports_allowed")
        report._guard()
        context._require(report._plan is plan, "same_exact_daily_source_plan_required")
        if original is None:
            original = report._index
        context._require(report._index is original, "same_exact_original_native_index_required")
        metadata = report.to_payload()
        context._require(metadata["day_ordinal"] == count and metadata["query_date"] == plan.sessions()[count - 1]
                         and metadata["active_panel_only"] is True and metadata["inactive_panel_captured"] is False,
                         "complete_ordered_daily_source_inventory_required")
        source_days.append({"day_ordinal": count, "query_date": metadata["query_date"], "report_sha256": report.sha256,
                            "all_source_rows": len(report._rows)})
        for record in report.iter_rows():
            # Literal requirements were established by the distinct typed
            # qualifier; refusals stay in its authenticated source report.
            if record[-1] or record[5] is None:
                continue
            page, row, ticker, cls, native, cik = record[0], record[1], record[2], record[4], record[5], record[12]
            context._require(cik == context._cik(cik) and record[9] is True and record[11] == "usd", "typed_daily_source_assertion_changed")
            company_offsets = offsets.setdefault(cik, bytearray())
            context._require(indexed_bytes + _CELL.size + _ORDINAL.size <= MAXIMUM_INDEX_BYTES,
                             "bounded_compact_daily_index")
            ordinal = len(cells) // _CELL.size
            cells.extend(_CELL.pack(count, page, row, token(native), token(cls), token(ticker), token(cik)))
            company_offsets.extend(_ORDINAL.pack(ordinal))
            indexed_bytes += _CELL.size + _ORDINAL.size
            target_bits[(cik, ticker)] = target_bits.get((cik, ticker), 0) | (1 << (count - 1))
            candidate = (count, ticker, cls, native, page, row)
            previous = selected.get(cik)
            if previous is None or count > previous[0] or (count == previous[0] and candidate[1:4] < previous[1:4]):
                selected[cik] = candidate
    context._require(count == daily.EXPECTED_SESSIONS and original is not None, "all_1169_source_days_required")
    packed, strings = bytes(cells), tuple(pool)
    chosen = tuple((cik, *selected[cik]) for cik in sorted(selected))
    header = canonical_json({"schema": "si-indexed-daily-company-source-v2", "policy_sha256": hash_payload(policy()),
        "plan_sha256": plan.sha256, "source_days": source_days, "native_master": original.metadata(),
        "tokens": strings, "cell_record_format": _CELL.format, "cell_count": len(packed) // _CELL.size,
        "cells_sha256": hash_bytes(packed), "selected_targets": chosen, "authority": context._authority()}).encode()
    result = object.__new__(DailyIssuerIndex)
    values = (header, packed, strings, MappingProxyType({cik: bytes(value) for cik, value in offsets.items()}),
              MappingProxyType(target_bits), chosen, MappingProxyType(dict(selected)), plan, original)
    for name, value in zip(("_header", "_cells", "_pool", "_offsets", "_target_bits", "_selected", "_selected_map", "_plan", "_index"), values):
        object.__setattr__(result, name, value)
    object.__setattr__(result, "_anchor", values); object.__setattr__(result, "_identity", values)
    return result


class IndexedCompanyCapPlan:
    __slots__ = ("_bytes", "_index", "_base", "_anchor", "_identity")

    def __init__(self):
        raise context.FmpContextError("REFUSED: indexed_plan_factory_required")

    def _guard(self):
        context._require(type(self) is IndexedCompanyCapPlan and type(self._anchor) is tuple and len(self._anchor) == 3
            and self._anchor is self._identity and self._bytes is self._anchor[0]
            and self._index is self._anchor[1] and self._base is self._anchor[2], "sealed_indexed_company_plan_changed")
        self._index._guard(); self._base.to_bytes()

    def to_payload(self):
        self._guard()
        return json.loads(self._bytes)

    @property
    def sha256(self):
        self._guard()
        return hash_bytes(self._bytes)

    def base_context_plan(self):
        self._guard()
        return self._base


def freeze_indexed_company_plan(index):
    context._require(type(index) is DailyIssuerIndex and bool(index.selected()), "nonempty_source_bound_daily_company_index_required")
    tickets, header = [], index.header()
    source_sha = index.sha256
    for cik, day, ticker, cls, native, page, row in index.selected():
        body = canonical_json({"schema": context.SCHEMA + "-target-proposal", "symbol": ticker, "cik": cik,
            "source_origins": [{"artifact_sha256": source_sha, "locator": f"/selected/{cik}"},
                {"artifact_sha256": header["source_days"][day - 1]["report_sha256"], "locator": f"/page/{page}/row/{row}"}]}).encode()
        tickets.append(context.seal_target_ticket(body, expected_sha256=hash_bytes(body)))
    base = context.freeze_context_plan(tuple(tickets))
    value = {"schema": "si-indexed-company-context-plan-v2", "policy_sha256": hash_payload(policy()),
        "daily_index_sha256": source_sha, "base_context_plan_sha256": base.sha256,
        "selected_company_count": len(tickets), "maximum_requests": 2 * len(tickets),
        "maximum_total_bytes": MAXIMUM_TOTAL_RESPONSE_BYTES,
        "maximum_rows": len(tickets) * (context.MAXIMUM_LOOKUP_ROWS + context.cap.LIMIT),
        "old_runtime_cannot_use_this_type_or_budget": True, "authority": context._authority()}
    raw = canonical_json(value).encode()
    result = object.__new__(IndexedCompanyCapPlan)
    anchor = (raw, index, base)
    for name, item in (("_bytes", raw), ("_index", index), ("_base", base), ("_anchor", anchor), ("_identity", anchor)):
        object.__setattr__(result, name, item)
    return result


def iter_indexed_company_cap_bindings(index, cap_report):
    """O(company rows + cap dates), exact daily type provenance, no signals."""
    context._require(type(index) is DailyIssuerIndex and type(cap_report) is context.CompanyCapQualification,
                     "exact_daily_index_and_company_cap_required")
    index._guard()
    cap = cap_report.to_payload()
    target = index._selected_map.get(cap["issuer_cik"])
    context._require(target is not None and target[1] == cap["symbol"], "exact_preselected_request_target_required")
    cap_sha256 = cap_report.sha256
    dates = {row["date"]: row for row in cap["rows"] if row["status"] == "issuer_size_series_candidate"}
    for day, page, row, native, cls, ticker, cik in index.iter_cik_rows(cap["issuer_cik"]):
        index._guard(); cap_report.to_bytes()
        at = index._plan.sessions()[day - 1]
        reasons = []
        observed = dates.get(at)
        if observed is None:
            reasons.append("same_date_company_cap_missing_or_ambiguous")
        if not index.target_observed(cik, cap["symbol"], day):
            reasons.append("same_date_request_target_USD_not_independently_observed")
        yield {"query_date": at, "native_id": native, "share_class_figi": cls,
            "daily_source_origin": [day, page, row], "cap_report_sha256": cap_sha256,
            "cap_row_index": observed["row_index"] if observed else None,
            "status": "dated_issuer_USD_cap_source_candidate" if not reasons else "refused",
            "refusal_reasons": reasons, "same_class_shares": None, "authority": context._authority()}
