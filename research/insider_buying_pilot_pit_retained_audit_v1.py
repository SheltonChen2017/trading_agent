"""Pure retained-control/current-reference audit; no historical identity promotion.

The isolated caller authenticates complete receipts and their derived input
pins before supplying any records. This module never opens a file, contacts a
provider or interprets financial values. Current CIK/permaticker relations and
dated corporate-action labels are discovery evidence only. Neither an action
date nor a current reference date becomes a historical knowledge interval.
"""
from __future__ import annotations

from collections import Counter, OrderedDict, defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
import re

from research import insider_buying_pilot_fmp_eod_projection_v1 as projection
from research.insider_buying_provider_reference_identity import _sec_cik_url
from research.insider_buying_sharadar_reference_cohort import TICKER_COLUMNS, ACTION_COLUMNS

SCHEMA = "insider-pilot-pit-retained-control-audit-v1"
CASE_KEYS = frozenset({"case_id", "cik", "accession", "form_type", "filing_date",
    "acceptance_digits", "source_symbol", "body_sha256"})
PROVIDER_SCHEMA = "insider-pilot-fmp-eod-stable-qualification-v2/complete"
MAX_CASES, MAX_ROWS, MAX_PINS, CHECK_EVERY = 12, 2_000_000, 128, 256
MAX_PIN_BYTES = 256 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-^/=]{0,63}\Z")
_SECURITY_TABLES = frozenset({"stocks", "fundamentals", "funds", "insiders", "SEP", "SF1", "SFP", "SF2"})
_FMP_FIELDS = ("candidate_rows", "exact_accession_rows", "cik_equal_rows", "joint_cik_accession_rows",
    "filing_date_equal_rows", "form_type_equal_rows", "source_symbol_present_rows", "source_symbol_equal_rows",
    "naive_acceptance_comparable_rows", "naive_acceptance_lexical_equal_rows", "filing_filter_equal_rows",
    "transaction_filter_equal_rows")
_FMP_FLAGS = ("acceptance_timezone_verified", "public_known_by_verified", "source_body_equivalence_verified")
_PROJECTION_KEYS = frozenset({"schema", "family", "scoped", "metadata_clean", "response_rows_retained",
    "response_body_retained", "metadata_evidence_can_independently_reparse_response",
    "credential_screening_is_external_required_control", "body_pin", "counts", "case_checks",
    "filing_date_bounds", "pagination", "all_six_form_coverage_verified",
    "current_label_agreement_is_historical_identity", "naive_acceptance_is_publication_or_timezone_evidence",
    "latest_date_filter_semantics_verified", "financial_values_interpreted", "authority"})
_CATEGORIES = ("listed", "delisted", "ticker_change", "merger", "acquisition", "spinoff", "other")
# Sharadar's action vocabulary is directional and subtyped: a family named only
# by its bare word would count mergerto/acquisitionby/spunofffrom as "other".
_ACTION_CATEGORIES = {
    "listed": "listed",
    "delisted": "delisted", "regulatorydelisting": "delisted", "voluntarydelisting": "delisted",
    "bankruptcyliquidation": "delisted",
    "tickerchange": "ticker_change", "tickerchangefrom": "ticker_change", "tickerchangeto": "ticker_change",
    "ticker_change": "ticker_change",
    "merger": "merger", "mergerfrom": "merger", "mergerto": "merger",
    "acquisition": "acquisition", "acquisitionby": "acquisition", "acquisitionof": "acquisition",
    "spinoff": "spinoff", "spinoffdividend": "spinoff", "spunofffrom": "spinoff",
}
MISSING_EVIDENCE = (
    "exact_version_historical_public_available_by_not_established",
    "historical_clock_and_correction_lineage_not_established",
    "historical_share_class_and_listing_intervals_not_established",
    "historical_symbol_reuse_and_predecessor_lineage_not_established",
    "exact_sec_security_title_not_bound",
    "whole_pilot_original_admission_not_complete",
    "qc_sid_not_bound",
    "processing_rights_not_established_by_this_audit",
)
_RESULTS = OrderedDict()


class PitRetainedAuditError(ValueError):
    """Finite own refusal codes, never supplied rows, labels or exception text."""


def _need(ok, code="input_refused"):
    if not ok:
        raise PitRetainedAuditError(code)


def _raw(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        raise PitRetainedAuditError("input_refused") from None


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def authority():
    return {"source_authenticated": False, "historical_public_known_by_verified": False,
        "historical_identity_verified": False, "point_in_time_data": False, "rights_verified": False,
        "canonical_admitted": False, "full_population_complete": False, "backtesting_ready": False,
        "qc_jobs": 0, "outcome_looks": 0, "backtests": 0}


def _false_authority(value):
    _need(type(value) is dict and _raw(value) == _raw(authority()), "authority_refused")


def _count(value, maximum=1_000_000_000):
    _need(type(value) is int and 0 <= value <= maximum, "count_refused")
    return value


def _day(value):
    if type(value) is not str or len(value) != 10:
        return None
    try:
        return value if date.fromisoformat(value).isoformat() == value else None
    except ValueError:
        return None


def _utc(value):
    _need(type(value) is str and value.endswith("Z") and len(value) <= 40, "provider_refused")
    try:
        instant = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise PitRetainedAuditError("provider_refused") from None
    _need(instant.tzinfo == timezone.utc, "provider_refused")


def _pins(value):
    _need(type(value) is dict and 0 < len(value) <= MAX_PINS, "pin_refused")
    result = {}
    for name, pin in value.items():
        _need(type(name) is str and _NAME.fullmatch(name) and name not in {".", ".."}
            and type(pin) is dict and set(pin) == {"sha256", "bytes"}
            and type(pin["sha256"]) is str and _SHA.fullmatch(pin["sha256"])
            and type(pin["bytes"]) is int and 0 < pin["bytes"] <= MAX_PIN_BYTES, "pin_refused")
        result[name] = dict(pin)
    return result


def _counter_tree(value, depth=0):
    _need(type(value) is dict and len(value) <= 128 and depth <= 4, "provider_refused")
    for name, child in value.items():
        _need(type(name) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", name), "provider_refused")
        if type(child) is dict:
            _counter_tree(child, depth + 1)
        else:
            _count(child)


def _projection(value, family, case_ids):
    _need(type(value) is dict and set(value) == _PROJECTION_KEYS
        and value["schema"] == projection.SCHEMA
        and value["family"] == {"fmp_sec": "fmp_sec_search", "fmp_insider": "fmp_insider_latest",
            "eod_mapping": "eod_current_mapping"}[family]
        and type(value["scoped"]) is type(value["metadata_clean"]) is bool, "provider_refused")
    _false_authority(value["authority"])
    for key in ("response_rows_retained", "response_body_retained",
            "metadata_evidence_can_independently_reparse_response", "all_six_form_coverage_verified",
            "current_label_agreement_is_historical_identity", "naive_acceptance_is_publication_or_timezone_evidence",
            "latest_date_filter_semantics_verified", "financial_values_interpreted"):
        _need(value[key] is False, "provider_refused")
    _need(value["credential_screening_is_external_required_control"] is True, "provider_refused")
    if value["scoped"] and value["metadata_clean"]:
        _pins({"body.json": value["body_pin"]})
    else:
        _need(value["body_pin"] is None, "provider_refused")
    _counter_tree(value["counts"])
    _need(type(value["case_checks"]) is dict and set(value["case_checks"]) <= case_ids
        and (value["scoped"] or not value["case_checks"]), "provider_refused")
    for check in value["case_checks"].values():
        if family in {"fmp_sec", "fmp_insider"}:
            _need(type(check) is dict and set(check) == set(_FMP_FIELDS) | set(_FMP_FLAGS), "provider_refused")
            for key in _FMP_FIELDS:
                _count(check[key])
            for key in _FMP_FLAGS:
                _need(check[key] is False, "provider_refused")
            c, j = check["candidate_rows"], check["joint_cik_accession_rows"]
            _need(all(check[key] <= c for key in _FMP_FIELDS)
                and j <= min(check["exact_accession_rows"], check["cik_equal_rows"]), "provider_refused")
        else:
            fields = {"cik_rows", "current_symbol_present_rows", "current_symbol_equal_rows",
                "current_symbol_us_namespace_equal_rows", "identifier_presence_counts", "historical_identity_verified"}
            _need(type(check) is dict and set(check) == fields and check["historical_identity_verified"] is False,
                "provider_refused")
            for key in fields - {"historical_identity_verified", "identifier_presence_counts"}:
                _count(check[key])
            _need(type(check["identifier_presence_counts"]) is dict
                and set(check["identifier_presence_counts"]) == {"isin", "cusip", "figi", "lei"}, "provider_refused")
            _counter_tree(check["identifier_presence_counts"])
    dates = value["filing_date_bounds"]
    _need(dates is None or type(dates) is list and len(dates) == 2 and all(_day(v) for v in dates)
        and dates[0] <= dates[1], "provider_refused")
    pagination = value["pagination"]
    pagination_flags = {"limit_reached", "all_pages_read", "next_present", "more_rows_indicated"}
    pagination_keys = {"requested_offset", "requested_limit", "response_total", "response_limit", "response_offset",
        "limit_reached", "next_present", "more_rows_indicated", "all_pages_read"}
    if family != "eod_mapping":
        pagination_keys = {"requested_page", "requested_limit", "limit_reached", "additional_pages_unknown", "all_pages_read"}
        pagination_flags = {"limit_reached", "additional_pages_unknown", "all_pages_read"}
    _need(type(pagination) is dict and set(pagination) == pagination_keys, "provider_refused")
    for key, child in pagination.items():
        if key in pagination_flags:
            _need(type(child) is bool, "provider_refused")
        else:
            _count(child)
    return value


def _provider(value, cases):
    required = {"schema", "fixture_only", "receipts", "authority", "planned_requests",
        "transport_invocation_count", "unattempted_requests", "projected_responses", "scoped_responses",
        "clean_scoped_responses"}
    optional = {"execution_head", "completed_utc", "credential_reads_observed", "credential_read_attempts",
        "raw_response_retained", "remote_request_count_measured", "published_leaf_pins", "control_evidence_sha256",
        "failed_snapshot_sha256", "input_bindings_sha256", "scope_reservation_sha256", "storage_receipt_sha256"}
    _need(type(value) is dict and required <= set(value) <= required | optional
        and value["schema"] == PROVIDER_SCHEMA and type(value["fixture_only"]) is bool, "provider_refused")
    _false_authority(value["authority"])
    for key in ("raw_response_retained", "remote_request_count_measured"):
        if key in value:
            _need(value[key] is False, "provider_refused")
    for key in optional & set(value):
        if key.endswith("sha256"):
            _need(type(value[key]) is str and _SHA.fullmatch(value[key]), "provider_refused")
    if "published_leaf_pins" in value:
        _pins(value["published_leaf_pins"])
    for key in ("credential_reads_observed", "credential_read_attempts"):
        if key in value:
            _count(value[key], 2)
    if "execution_head" in value:
        _need(type(value["execution_head"]) is str and re.fullmatch(r"[0-9a-f]{40}", value["execution_head"]),
            "provider_refused")
    if "completed_utc" in value:
        _utc(value["completed_utc"])
    receipts = value["receipts"]
    _need(type(receipts) is list and 0 < len(receipts) <= 36, "provider_refused")
    totals = Counter(planned_requests=len(receipts))
    cases_by_id = {c["case_id"]: c for c in cases}
    combined = {key: Counter() for key in cases_by_id}
    eod = set()
    for index, receipt in enumerate(receipts):
        mandatory = {"request_index", "family", "attempted", "code"}
        allowed = mandatory | {"projection", "schema", "fingerprint", "http_status", "raw_response_retained",
            "error_or_refused_body_hashed_or_retained", "finished_utc"}
        _need(type(receipt) is dict and mandatory <= set(receipt) <= allowed
            and type(receipt["request_index"]) is int and receipt["request_index"] == index
            and type(receipt["family"]) is str and receipt["family"] in {"fmp_sec", "fmp_insider", "eod_mapping"}
            and type(receipt["attempted"]) is bool and type(receipt["code"]) is str
            and re.fullmatch(r"[a-z][a-z0-9_]{0,79}", receipt["code"]), "provider_refused")
        for key in ("raw_response_retained", "error_or_refused_body_hashed_or_retained"):
            if key in receipt:
                _need(receipt[key] is False, "provider_refused")
        if "fingerprint" in receipt:
            _need(type(receipt["fingerprint"]) is str and _SHA.fullmatch(receipt["fingerprint"]), "provider_refused")
        if "schema" in receipt:
            _need(receipt["schema"] == PROVIDER_SCHEMA.removesuffix("/complete") + "/request-completed",
                "provider_refused")
        if "finished_utc" in receipt:
            _utc(receipt["finished_utc"])
        p = receipt.get("projection")
        if not receipt["attempted"]:
            _need(p is None and receipt["code"] in {"prior_provider_or_family_refusal", "credential_refused"},
                "provider_refused")
            totals["unattempted_requests"] += 1
            continue
        totals["transport_invocation_count"] += 1
        totals[receipt["family"] + "_attempts"] += 1
        totals["refused_attempts"] += int(receipt["code"] != "metadata_projected")
        if "http_status" in receipt:
            _need(receipt["http_status"] is None or type(receipt["http_status"]) is int
                and 100 <= receipt["http_status"] <= 599, "provider_refused")
        if p is None:
            _need(receipt["code"] != "metadata_projected", "provider_refused")
            continue
        _need(receipt.get("http_status", 200) == 200, "provider_refused")
        p = _projection(p, receipt["family"], set(cases_by_id))
        _need(receipt["code"] == ("metadata_projected" if p["scoped"] else "provider_scope_refused"),
            "provider_refused")
        totals["projected_responses"] += 1
        totals["scoped_responses"] += int(p["scoped"])
        totals["clean_scoped_responses"] += int(p["scoped"] and p["metadata_clean"])
        if not (p["scoped"] and p["metadata_clean"]):
            continue
        if receipt["family"] == "fmp_sec":
            for key, check in p["case_checks"].items():
                combined[key].update({k: check[k] for k in _FMP_FIELDS})
        elif receipt["family"] == "eod_mapping":
            eod.update(key for key, check in p["case_checks"].items()
                if check["cik_rows"] > 0 and check["current_symbol_us_namespace_equal_rows"] > 0)
    for key in ("planned_requests", "transport_invocation_count", "unattempted_requests", "projected_responses",
            "scoped_responses", "clean_scoped_responses"):
        _need(_count(value[key], 36) == totals[key], "provider_refused")
    _need(all(v["joint_cik_accession_rows"] > 0 for v in combined.values()), "control_evidence_missing")
    return combined, totals, eod


def _row(value, columns, ordinal):
    _need(type(value) is dict and set(value) == {"source_row_ordinal", *columns}
        and type(value["source_row_ordinal"]) is int and value["source_row_ordinal"] == ordinal,
        "row_schema_refused")
    for key in columns:
        child = value[key]
        _need(type(child) is str and len(child) <= 16384, "row_schema_refused")
        try:
            _need(len(child.encode("utf-8")) <= 16384, "row_schema_refused")
        except UnicodeError:
            raise PitRetainedAuditError("row_schema_refused") from None
        _need(not any(ord(c) < 32 and not (key in {"name", "contraname"} and c in "\r\n\t")
            for c in child), "row_schema_refused")
    return value


def _rows(value):
    try:
        return iter(value)
    except TypeError:
        raise PitRetainedAuditError("row_schema_refused") from None


def _category(value):
    # Exact codes only: an unrecognized action stays counted as "other", so this
    # table can only under-classify, never invent a corporate-action family.
    return _ACTION_CATEGORIES.get(value.lower(), "other")


def build_audit(cases, provider_complete, ticker_rows, action_rows, source_pins, *, check=None, fixture_only=True):
    """Account for supplied metadata, with every historical gate still false.

    Structural corruption refuses; ordinary absent/ambiguous reference fields
    remain counted. The callback supports a caller-owned real memory/custody
    guard and runs before inputs, every256 rows and at both table boundaries.
    """
    _need(type(fixture_only) is bool and (check is None or callable(check)), "arguments_refused")
    pulse = check if check is not None else lambda: None
    pulse()
    _need(type(cases) in {list, tuple} and 0 < len(cases) <= MAX_CASES
        and all(type(c) is dict and set(c) == CASE_KEYS for c in cases)
        and (fixture_only or len(cases) == MAX_CASES), "control_refused")
    try:
        cases = projection._cases(cases)
    except ValueError:
        raise PitRetainedAuditError("control_refused") from None
    pins = _pins(source_pins)
    provider, provider_counts, eod = _provider(provider_complete, cases)
    _need(fixture_only or provider_complete["fixture_only"] is False, "provider_refused")
    counts = Counter({key: 0 for key in ("ticker_rows", "ticker_quarantined_rows", "ticker_exact_duplicate_rows",
        "ticker_primary_key_conflict_groups", "ticker_candidate_rows", "global_permaticker_cik_conflicts",
        "global_label_reuse_groups", "controls_no_current_candidate", "controls_one_current_candidate",
        "controls_multiple_current_candidates", "controls_conflicting_current_candidates",
        "controls_source_symbol_agreement", "action_rows", "action_quarantined_rows", "action_exact_duplicate_rows",
        "action_candidate_rows", "action_candidate_relations", "action_rows_before_filing_relations",
        "action_primary_label_relations", "action_counterparty_label_relations")})
    counts.update(controls=len(cases), issuers=len({c["cik"] for c in cases}),
        eod_current_mapping_agreement_controls=len(eod))
    for key in ("planned_requests", "transport_invocation_count", "projected_responses", "scoped_responses",
            "clean_scoped_responses", "unattempted_requests", "refused_attempts"):
        counts["provider_" + ("transport_invocations" if key == "transport_invocation_count" else key)] = provider_counts[key]
    for family in ("fmp_sec", "fmp_insider", "eod_mapping"):
        counts[family + "_attempts"] = provider_counts[family + "_attempts"]
    by_cik = defaultdict(list)
    for index, case in enumerate(cases):
        by_cik[case["cik"]].append(index)
    matched = [dict(rows=0, quarantined=0, symbol=0, permas=set(), labels=set(), ordinals=[],
                    actions=[], before=0, primary_actions=0, counterparty_actions=0) for _ in cases]
    perma_ciks, label_permas = defaultdict(set), defaultdict(set)
    primary, conflicting_primary, exact = {}, set(), set()
    for ordinal, row in enumerate(_rows(ticker_rows), 1):
        _need(ordinal <= MAX_ROWS, "row_limit_refused")
        row = _row(row, TICKER_COLUMNS, ordinal)
        if ordinal % CHECK_EVERY == 0:
            pulse()
        counts["ticker_rows"] += 1
        digest = _sha(_raw({k: row[k] for k in TICKER_COLUMNS}))
        counts["ticker_exact_duplicate_rows"] += int(digest in exact)
        exact.add(digest)
        pk = (row["table"], row["permaticker"], row["ticker"])
        if pk in primary and primary[pk] != digest:
            conflicting_primary.add(pk)
        primary.setdefault(pk, digest)
        cik, _disposition = _sec_cik_url(row["secfilings"])
        perma_ok, label_ok = bool(_LABEL.fullmatch(row["permaticker"])), bool(_LABEL.fullmatch(row["ticker"]))
        security = row["table"] in _SECURITY_TABLES
        if perma_ok and cik is not None:
            perma_ciks[row["permaticker"]].add(cik)
        if security and perma_ok and label_ok:
            label_permas[row["ticker"]].add(row["permaticker"])
        quarantined = (not security or not perma_ok or not label_ok or cik is None
            or row["isdelisted"] not in {"Y", "N"} or any(c in "\r\n\t" for c in row["name"])
            or any(row[key] and _day(row[key]) is None
                for key in ("firstpricedate", "lastpricedate", "firstadded", "lastupdated")))
        counts["ticker_quarantined_rows"] += int(quarantined)
        if security and perma_ok and label_ok and cik in by_cik:
            counts["ticker_candidate_rows"] += 1
            for index in by_cik[cik]:
                item = matched[index]
                item["rows"] += 1; item["quarantined"] += int(quarantined)
                item["symbol"] += int(cases[index]["source_symbol"] is not None
                    and row["ticker"] == cases[index]["source_symbol"])
                item["permas"].add(row["permaticker"]); item["labels"].add(row["ticker"])
                item["ordinals"].append(ordinal)
    pulse()
    counts["ticker_primary_key_conflict_groups"] = len(conflicting_primary)
    counts["global_permaticker_cik_conflicts"] = sum(len(v) > 1 for v in perma_ciks.values())
    counts["global_label_reuse_groups"] = sum(len(v) > 1 for v in label_permas.values())
    label_cases = defaultdict(set)
    for index, item in enumerate(matched):
        # Preserve the genuine retained filing's own label even if today's
        # CIK candidates use a renamed symbol or no current row is present.
        # These labels select action CONTEXT, never a security identity join.
        labels = set(item["labels"])
        source_symbol = cases[index]["source_symbol"]
        if source_symbol is not None and _LABEL.fullmatch(source_symbol):
            labels.add(source_symbol)
        for label in labels:
            label_cases[label].add(index)
    action_seen, categories = set(), Counter(dict.fromkeys(_CATEGORIES, 0))
    for ordinal, row in enumerate(_rows(action_rows), 1):
        _need(ordinal <= MAX_ROWS, "row_limit_refused")
        row = _row(row, ACTION_COLUMNS, ordinal)
        if ordinal % CHECK_EVERY == 0:
            pulse()
        counts["action_rows"] += 1
        digest = _sha(_raw({k: row[k] for k in ACTION_COLUMNS}))
        counts["action_exact_duplicate_rows"] += int(digest in action_seen)
        action_seen.add(digest)
        categories[_category(row["action"])] += 1
        day = _day(row["date"])
        quarantined = (day is None or not row["action"] or not _LABEL.fullmatch(row["ticker"])
            or bool(row["contraticker"]) and not _LABEL.fullmatch(row["contraticker"])
            or any(c in "\r\n\t" for k in ("name", "contraname") for c in row[k]))
        counts["action_quarantined_rows"] += int(bool(quarantined))
        primary_indices = label_cases.get(row["ticker"], set())
        counterparty_indices = label_cases.get(row["contraticker"], set())
        # Both sides can expose relevant history. An exact label on either
        # side remains a discovery relation, not proof that two securities
        # are aliases. Count a case only once when both sides match it.
        indices = sorted(primary_indices | counterparty_indices)
        counts["action_candidate_rows"] += int(bool(indices))
        counts["action_candidate_relations"] += len(indices)
        counts["action_primary_label_relations"] += len(primary_indices)
        counts["action_counterparty_label_relations"] += len(counterparty_indices)
        for index in indices:
            matched[index]["actions"].append(ordinal)
            matched[index]["primary_actions"] += int(index in primary_indices)
            matched[index]["counterparty_actions"] += int(index in counterparty_indices)
            before = day is not None and day < cases[index]["filing_date"]
            matched[index]["before"] += int(before)
            counts["action_rows_before_filing_relations"] += int(before)
    pulse()
    controls = []
    for index, (case, item) in enumerate(zip(cases, matched)):
        observed = provider[case["case_id"]]
        c, j = observed["candidate_rows"], observed["joint_cik_accession_rows"]
        form = observed["form_type_equal_rows"] > c - j
        acceptance = observed["naive_acceptance_lexical_equal_rows"] > c - j
        conflicts = sum(len(perma_ciks[p]) > 1 for p in item["permas"])
        reused = sum(len(label_permas[label]) > 1 for label in item["labels"])
        n = len(item["permas"])
        counts["controls_no_current_candidate" if n == 0 else "controls_one_current_candidate"
            if n == 1 else "controls_multiple_current_candidates"] += 1
        counts["controls_conflicting_current_candidates"] += int(conflicts > 0)
        counts["controls_source_symbol_agreement"] += int(item["symbol"] > 0)
        controls.append({"control_sha256": _sha(_raw(case)), "counts": {
            "fmp_candidate_rows": c, "fmp_joint_rows": j,
            "fmp_form_agreeing_rows": observed["form_type_equal_rows"],
            "fmp_naive_acceptance_agreeing_rows": observed["naive_acceptance_lexical_equal_rows"],
            "current_candidate_rows": item["rows"], "current_candidate_permatickers": n,
            "current_quarantined_candidate_rows": item["quarantined"], "source_symbol_equal_rows": item["symbol"],
            "conflicting_permatickers": conflicts, "reused_labels": reused,
            "action_candidate_rows": len(item["actions"]), "action_rows_before_filing": item["before"],
            "action_primary_label_rows": item["primary_actions"],
            "action_counterparty_label_rows": item["counterparty_actions"]},
            "candidate_permatickers_sha256": _sha(_raw(sorted(item["permas"]))),
            "candidate_source_ordinals_sha256": _sha(_raw(item["ordinals"])),
            "action_source_ordinals_sha256": _sha(_raw(item["actions"])),
            "fmp_form_exact_row_guaranteed": form, "fmp_naive_acceptance_exact_row_guaranteed": acceptance,
            "effective_interval": None, "public_known_by": None, "authority": authority()})
    counts["fmp_joint_controls"] = sum(c["counts"]["fmp_joint_rows"] > 0 for c in controls)
    counts["fmp_form_guaranteed_controls"] = sum(c["fmp_form_exact_row_guaranteed"] for c in controls)
    counts["fmp_naive_acceptance_guaranteed_controls"] = sum(c["fmp_naive_acceptance_exact_row_guaranteed"] for c in controls)
    _need(counts["controls"] == sum(counts[k] for k in ("controls_no_current_candidate",
        "controls_one_current_candidate", "controls_multiple_current_candidates")), "accounting_refused")
    result = {"schema": SCHEMA, "fixture_only": fixture_only, "source_pins": pins,
        "counts": {**dict(counts), "action_categories": dict(categories)}, "controls": controls,
        "missing_evidence": list(MISSING_EVIDENCE), "authority": authority()}
    raw = _raw(result)
    _need(len(raw) <= 128 * 1024, "output_refused")
    _RESULTS[id(result)] = (result, raw)
    while len(_RESULTS) > 64:
        _RESULTS.popitem(last=False)
    pulse()
    return result


def public_summary(result):
    """Return only safe counts/pins; refuse forged or mutated factory results."""
    registered = _RESULTS.get(id(result))
    _need(type(result) is dict and registered is not None and registered[0] is result
        and registered[1] == _raw(result), "genuine_result_required")
    _false_authority(result["authority"])
    return json.loads(_raw({"schema": SCHEMA, "fixture_only": result["fixture_only"],
        "counts": result["counts"], "authority": result["authority"], "source_pins": result["source_pins"],
        "result_sha256": _sha(registered[1])}))
