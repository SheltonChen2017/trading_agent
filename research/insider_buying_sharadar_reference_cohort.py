"""Pure retrospective reference discovery, never historical security admission.

Every nonfinancial projected row and every source issuer is accounted for.
The actual observer must independently prove archive/member bytes and custody;
these supplied projections alone prove neither that nor original availability.
Names are retained privately as source metadata, never used as join keys.
CSV CR/LF/TAB in names remain exact JSON-escaped metadata with a quarantine
reason; identity/date/URL controls and invalid UTF-8 text still refuse.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import re
import weakref

from research.insider_buying_earnings_archive_cohort_assessment import (
    EarningsArchiveAssessmentError, _inventory,
)
from research.insider_buying_provider_reference_identity import _sec_cik_url


SCHEMA = "insider-sharadar-reference-cohort-assessment-v2"
TICKERS_SCHEMA = "insider-sharadar-tickers-cohort-projection-v1"
ACTIONS_SCHEMA = "insider-sharadar-actions-cohort-projection-v1"
TICKER_COLUMNS = ("table", "permaticker", "ticker", "name", "exchange", "isdelisted", "category",
                  "relatedtickers", "firstpricedate", "lastpricedate", "firstadded", "lastupdated", "secfilings")
ACTION_COLUMNS = ("date", "action", "ticker", "name", "contraticker", "contraname")
MAX_PROJECTION_BYTES = 256 * 1024 * 1024
MAX_REPORT_BYTES = 256 * 1024 * 1024
MAX_ROWS = 2_000_000
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-^/=]{0,63}\Z")
_SECURITY_TABLES = frozenset({"stocks", "fundamentals", "funds", "insiders", "SEP", "SF1", "SFP", "SF2"})
FALSE_FLAGS = ("actual_file_custody_verified", "source_authenticated", "historical_identity_verified",
               "point_in_time_verified", "original_parent_corroborated", "exact_security_title_verified",
               "first_listing_verified", "qc_symbol_id_bound", "rights_authenticated", "canonical_released",
               "backtest_ready", "qc_authorized", "execution_authorized")
_REGISTRY = {}


class SharadarReferenceCohortError(ValueError):
    """Fixed refusal codes, without input rows, names or filesystem details."""


def _need(condition, code):
    if not condition:
        raise SharadarReferenceCohortError(code)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(value):
    _need(type(value) is str and _SHA.fullmatch(value), "external_digest_required")
    return value


def _json(raw, expected, *, limit, canonical=True):
    _need(type(raw) is bytes and 0 < len(raw) <= limit and _sha(raw) == _digest(expected), "metadata_hash_or_size")
    def pairs(items):
        result = {}
        for key, value in items:
            _need(key not in result, "duplicate_metadata_key")
            result[key] = value
        return result
    try:
        body = json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: _need(False, "nonfinite_metadata"))
        _need(type(body) is dict and (not canonical or _canonical(body) == raw), "canonical_metadata_required")
        return body
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, OverflowError):
        raise SharadarReferenceCohortError("metadata_decode_refused") from None


def _keys(body, keys):
    _need(type(body) is dict and set(body) == set(keys), "projection_schema")


def _count(value):
    _need(type(value) is int and 0 <= value <= MAX_ROWS, "source_count")
    return value


def _safe_text(value, *, allow_name_controls=False):
    if type(value) is not str or any(ord(char) < 32 and not (
            allow_name_controls and char in "\r\n\t") for char in value):
        return False
    try:
        return len(value.encode()) <= 16 * 1024
    except UnicodeError:
        return False


def _day(value):
    if not value or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _utc(value):
    _need(type(value) is str and len(value) <= 64, "capture_timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise SharadarReferenceCohortError("capture_timestamp") from None
    _need(result.tzinfo is not None and result.utcoffset() == timezone.utc.utcoffset(result), "capture_timestamp")
    return result


def _manifest(raw, digest):
    body = _json(raw, digest, limit=1024 * 1024, canonical=False)
    _need(body.get("schema") == "arv2-sharadar-source-capture-artifact-v2", "capture_schema")
    _need(_utc(body.get("capture_started_at")) <= _utc(body.get("capture_completed_at")), "capture_order")
    for flag in ("api_key_persisted", "redirect_url_persisted", "outcome_access_performed", "quantconnect_io_performed",
                 "pit_security_master_constructed", "backtest_input_constructed", "terminal_payoff_constructed"):
        _need(body.get(flag) is False, "capture_exclusion_flags")
    entries = body.get("archives")
    _need(type(entries) is list and len(entries) == 3 and all(type(item) is dict for item in entries)
          and [item.get("dataset") for item in entries] == ["tickers", "actions", "fundamentals"], "capture_inventory")
    result = {}
    for item in entries:
        dataset = item["dataset"]
        _digest(item.get("archive_sha256"))
        _need(item.get("archive_file") == {"tickers": "01-tickers-years-full.zip", "actions": "02-actions-years-full.zip",
                                         "fundamentals": "03-fundamentals-years-full.zip"}[dataset], "capture_archive_name")
        members = item.get("members")
        _need(type(members) is list and len(members) == 1 and type(members[0]) is dict, "capture_member_inventory")
        member = members[0]
        _digest(member.get("content_sha256"))
        _need(member.get("name") == dataset + ".csv", "capture_member_name")
        columns = member.get("columns")
        _need(type(columns) is list and all(type(field) is str for field in columns)
              and len(set(columns)) == len(columns), "capture_columns")
        _need(type(item.get("row_count")) is int and item["row_count"] > 0
              and type(member.get("row_count")) is int and member["row_count"] == item["row_count"], "capture_row_count")
        if dataset != "fundamentals":
            _count(item["row_count"])
            _need(set(TICKER_COLUMNS if dataset == "tickers" else ACTION_COLUMNS) <= set(columns), "capture_columns")
        result[dataset] = item
    return body, result


def _projection(raw, digest, *, schema, columns, manifest_digest, entry):
    body = _json(raw, digest, limit=MAX_PROJECTION_BYTES)
    _keys(body, {"schema", "capture_manifest_sha256", "archive_sha256", "member_sha256", "columns", "rows"})
    _need(body["schema"] == schema and body["columns"] == list(columns), "projection_schema")
    _need(body["capture_manifest_sha256"] == manifest_digest and body["archive_sha256"] == entry["archive_sha256"]
          and body["member_sha256"] == entry["members"][0]["content_sha256"], "projection_source_binding")
    rows = body["rows"]
    _need(type(rows) is list and len(rows) == entry["row_count"], "projection_row_accounting")
    for ordinal, row in enumerate(rows, 1):
        _keys(row, {"source_row_ordinal", *columns})
        _need(type(row["source_row_ordinal"]) is int and row["source_row_ordinal"] == ordinal, "projection_ordinals")
        _need(all(_safe_text(row[field], allow_name_controls=field in {"name", "contraname"})
                  for field in columns), "projection_field_shape")
    return rows


@dataclass(frozen=True, slots=True, weakref_slot=True)
class SharadarReferenceCohortAssessment:
    _raw: bytes

    def canonical_bytes(self):
        registered = _REGISTRY.get(id(self))
        _need(type(self) is SharadarReferenceCohortAssessment and registered is not None
              and registered[0]() is self and registered[1] == self._raw, "genuine_unchanged_assessment_required")
        return self._raw

    def to_payload(self):
        return json.loads(self.canonical_bytes())

    def candidate_action_ordinals(self, issuer_cik):
        """Losslessly expand one private discovery relation, never an alias.

        Label-index unions replace repeated whole action lists in v2. This
        accessor requires a genuine unchanged factory object, not supplied
        mutable JSON. It does not grant identity or historical admission.
        """
        body = self.to_payload()
        _need(type(issuer_cik) is str and re.fullmatch(r"[0-9]{10}", issuer_cik), "issuer_relation_required")
        matches = [item for item in body["issuer_relations"] if item["issuer_cik"] == issuer_cik]
        _need(len(matches) == 1, "issuer_relation_required")
        index = {item["folded_source_label"]: item["source_row_ordinals"] for item in body["candidate_action_label_index"]}
        row = matches[0]
        result = sorted({ordinal for label in row["candidate_action_source_labels"] for ordinal in index[label]})
        _need(len(result) == row["candidate_action_source_row_count"], "lossless_action_relation_count")
        return result

    @property
    def sha256(self):
        return _sha(self.canonical_bytes())


def assess_sharadar_cohort(*, inventory_raw: bytes, inventory_sha256: str, capture_manifest_raw: bytes,
                          capture_manifest_sha256: str, tickers_projection_raw: bytes, tickers_projection_sha256: str,
                          actions_projection_raw: bytes, actions_projection_sha256: str) -> SharadarReferenceCohortAssessment:
    """Discover current-CIK/label/action candidates for every 2006Q1 issuer.

    No source label, permaticker, corporate-action counterparty or name is
    promoted to historical identity. Future action context is retrospective.
    """
    try:
        inventory, issuers = _inventory(inventory_raw, inventory_sha256)
    except (EarningsArchiveAssessmentError, UnicodeError):
        raise SharadarReferenceCohortError("source_inventory_refused") from None
    manifest, entries = _manifest(capture_manifest_raw, capture_manifest_sha256)
    tickers = _projection(tickers_projection_raw, tickers_projection_sha256, schema=TICKERS_SCHEMA,
        columns=TICKER_COLUMNS, manifest_digest=capture_manifest_sha256, entry=entries["tickers"])
    actions = _projection(actions_projection_raw, actions_projection_sha256, schema=ACTIONS_SCHEMA,
        columns=ACTION_COLUMNS, manifest_digest=capture_manifest_sha256, entry=entries["actions"])
    ticker_reports, groups, ticker_keys = [], {}, defaultdict(list)
    ticker_reason_counts, flags = Counter(), Counter()
    cik_groups, label_groups, exact_label_groups = defaultdict(set), defaultdict(set), defaultdict(set)
    for row in tickers:
        reasons = []
        if any(char in "\r\n\t" for char in row["name"]):
            reasons.append("nonessential_name_control_characters")
        security_table = row["table"] in _SECURITY_TABLES
        if not security_table:
            reasons.append("source_table_not_security_candidate")
        valid_perma = bool(_LABEL.fullmatch(row["permaticker"]))
        valid_ticker = bool(_LABEL.fullmatch(row["ticker"]))
        if not valid_perma:
            reasons.append("provider_permaticker_unknown")
        if not valid_ticker:
            reasons.append("provider_ticker_unknown")
        cik, disposition = _sec_cik_url(row["secfilings"])
        if cik is None:
            reasons.append(disposition)
        flag = row["isdelisted"] if row["isdelisted"] in {"Y", "N"} else "unknown"
        flags[flag] += 1
        if flag == "unknown":
            reasons.append("current_delisting_flag_unknown")
        for field in ("firstpricedate", "lastpricedate", "firstadded", "lastupdated"):
            if row[field] and _day(row[field]) is None:
                reasons.append("current_metadata_date_invalid")
        reasons = sorted(set(reasons)); ticker_reason_counts.update(reasons)
        ticker_reports.append({"source_row_ordinal": row["source_row_ordinal"], "quarantine_reasons": reasons,
                               "issuer_cik_candidate": cik, "sec_url_disposition": disposition})
        ticker_keys[(row["table"], row["permaticker"], row["ticker"])].append(row)
        if security_table and valid_perma and valid_ticker:
            group = groups.setdefault(row["permaticker"], {"permaticker": row["permaticker"], "source_ordinals": [],
                                                          "tickers": set(), "issuer_cik_candidates": set()})
            group["source_ordinals"].append(row["source_row_ordinal"]); group["tickers"].add(row["ticker"])
            label_groups[row["ticker"].casefold()].add(row["permaticker"])
            exact_label_groups[row["ticker"]].add(row["permaticker"])
            if cik is not None:
                group["issuer_cik_candidates"].add(cik); cik_groups[cik].add(row["permaticker"])
    for group in groups.values():
        group["tickers"] = sorted(group["tickers"])
        group["issuer_cik_candidates"] = sorted(group["issuer_cik_candidates"])
        group["competing_cik_candidates"] = len(group["issuer_cik_candidates"]) > 1
        group["historical_mapping_admitted"] = False
    action_reports, action_keys, action_by_label = [], defaultdict(list), defaultdict(list)
    action_reason_counts, action_labels = Counter(), Counter()
    for row in actions:
        reasons = []
        if any(char in "\r\n\t" for field in ("name", "contraname") for char in row[field]):
            reasons.append("nonessential_name_control_characters")
        day = _day(row["date"])
        if day is None:
            reasons.append("action_date_unknown")
        if not row["action"]:
            reasons.append("action_label_unknown")
        if not _LABEL.fullmatch(row["ticker"]):
            reasons.append("action_ticker_unknown")
        if row["contraticker"] and not _LABEL.fullmatch(row["contraticker"]):
            reasons.append("action_counterticker_invalid")
        reasons = sorted(set(reasons)); action_reason_counts.update(reasons); action_labels[row["action"]] += 1
        item = {"source_row_ordinal": row["source_row_ordinal"], "date": row["date"], "action": row["action"],
                "ticker": row["ticker"], "contraticker": row["contraticker"], "quarantine_reasons": reasons,
                "same_security_alias_admitted": False, "effective_interval_admitted": False}
        action_reports.append(item)
        action_keys[tuple(row[column] for column in ACTION_COLUMNS)].append(row["source_row_ordinal"])
        for label in {row["ticker"], row["contraticker"]}:
            if _LABEL.fullmatch(label):
                action_by_label[label.casefold()].append(row["source_row_ordinal"])
    relations, dispositions, referenced_actions = [], Counter(), set()
    label_ciks = defaultdict(set)
    for issuer in issuers:
        for label in issuer["symbol_labels"]:
            label_ciks[label.casefold()].add(issuer["issuer_cik"])
    for issuer in issuers:
        direct = sorted(cik_groups[issuer["issuer_cik"]])
        label_candidates, labels = set(), []
        source_labels = set()
        for label in issuer["symbol_labels"]:
            candidate = sorted(label_groups[label.casefold()])
            exact_candidates = sorted(exact_label_groups[label])
            label_candidates.update(candidate); source_labels.add(label.casefold())
            labels.append({"source_label": label, "candidate_permatickers": candidate,
                           "exact_candidate_permatickers": exact_candidates,
                           "casefold_only_candidate_permatickers": sorted(set(candidate) - set(exact_candidates)),
                           "source_label_issuer_ciks": sorted(label_ciks[label.casefold()]),
                           "historical_mapping_admitted": False})
        for perma in set(direct) | label_candidates:
            source_labels.update(label.casefold() for label in groups[perma]["tickers"])
        indexed_labels = sorted(label for label in source_labels if action_by_label.get(label))
        action_ordinals = {ordinal for label in indexed_labels for ordinal in action_by_label[label]}
        referenced_actions.update(action_ordinals)
        competing = any(groups[perma]["competing_cik_candidates"] for perma in set(direct) | label_candidates)
        disposition = ("conflicting_current_cik_candidates" if competing else "multiple_current_share_class_candidates"
                       if len(direct) > 1 else "one_current_cik_candidate" if direct else
                       "label_only_candidates" if label_candidates else "no_current_reference_candidate")
        dispositions[disposition] += 1
        relations.append({**issuer, "current_cik_candidate_permatickers": direct,
            "candidate_label_relations": labels, "label_candidate_permatickers": sorted(label_candidates),
            "candidate_action_source_labels": indexed_labels, "candidate_action_source_row_count": len(action_ordinals),
            "candidate_disposition": disposition,
            "historical_mapping_admitted": False, "original_parent_corroborated": False})
    duplicate_tickers = [{"source_ordinals": [row["source_row_ordinal"] for row in rows],
                          "conflicting_nonfinancial_projection": len({_canonical({key: value for key, value in row.items()
                              if key != "source_row_ordinal"}) for row in rows}) > 1}
                         for _, rows in sorted(ticker_keys.items()) if len(rows) > 1]
    output = {"schema": SCHEMA, "scope": "all_form_2006q1_current_reference_and_retrospective_action_candidates_only",
        "inventory_sha256": inventory_sha256, "capture_manifest_sha256": capture_manifest_sha256,
        "tickers_projection_sha256": tickers_projection_sha256, "actions_projection_sha256": actions_projection_sha256,
        "capture_started_at": manifest["capture_started_at"], "capture_completed_at": manifest["capture_completed_at"],
        "source_filings": inventory["accounting"]["filings"], "source_form_counts": inventory["accounting"]["form_counts"],
        "all_form_issuer_count": len(issuers), "relevant_issuer_count": sum(item["form_counts"]["4"] + item["form_counts"]["4/A"] > 0 for item in issuers),
        "full_source_issuer_accounting_verified": True, "source_ticker_rows": len(tickers), "source_action_rows": len(actions),
        "ticker_rows_accounted": len(ticker_reports), "action_rows_accounted": len(action_reports),
        "ticker_quarantined_rows": sum(bool(item["quarantine_reasons"]) for item in ticker_reports),
        "action_quarantined_rows": sum(bool(item["quarantine_reasons"]) for item in action_reports),
        "ticker_quarantine_reason_counts": dict(sorted(ticker_reason_counts.items())), "action_quarantine_reason_counts": dict(sorted(action_reason_counts.items())),
        "current_delisting_flag_counts": dict(sorted(flags.items())), "action_label_counts": dict(sorted(action_labels.items())),
        "cohort_candidate_disposition_counts": dict(sorted(dispositions.items())), "issuer_relations": relations,
        "provider_share_class_candidate_groups": [groups[key] for key in sorted(groups)], "ticker_row_accounting": ticker_reports,
        "retrospective_action_rows": action_reports, "duplicate_ticker_primary_keys": duplicate_tickers,
        "duplicate_action_nonfinancial_keys": [ordinals for _, ordinals in sorted(action_keys.items()) if len(ordinals) > 1],
        "cohort_referenced_unique_action_rows": len(referenced_actions), "unreferenced_action_rows": len(actions) - len(referenced_actions),
        "cohort_action_relation_count": sum(item["candidate_action_source_row_count"] for item in relations),
        "action_relation_representation": "folded_source_label_index_union_v1",
        "candidate_action_label_index": [{"folded_source_label": label, "source_row_ordinals": sorted(set(ordinals))}
            for label, ordinals in sorted(action_by_label.items()) if ordinals],
        "action_source_rows_or_relations_dropped": False,
        "financial_fields_projected_or_evaluated": False, "names_used_as_join_keys": False,
        "future_action_context_is_historical_selection_information": False, "qc_identifier_observation_is_economic_knowledge": False,
        "provider_requests": 0, "qc_jobs": 0, "outcome_looks": 0, "backtests": 0,
        **dict.fromkeys(FALSE_FLAGS, False)}
    raw = _canonical(output)
    _need(len(raw) <= MAX_REPORT_BYTES, "assessment_byte_limit")
    result = SharadarReferenceCohortAssessment(raw)
    identity = id(result)
    _REGISTRY[identity] = (weakref.ref(result, lambda _: _REGISTRY.pop(identity, None)), raw)
    return result
