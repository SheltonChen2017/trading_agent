"""Fixed single-base SID-CASH completion, exclusion and account replay.

Pure source/supplied-byte processing only: no file/network/native opener,
credential, claim, upload, order or authority. Licensed journal/native symbols
must stay in their authorized QC environment; fixtures prove software only.
The new identity is fixed and regenerated, never a caller-selected override.
Historical completion/accounting modules remain unchanged.
"""
from __future__ import annotations
import ast
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, localcontext
from fractions import Fraction
import hashlib
import json
import re
from zoneinfo import ZoneInfo

from . import cap_observer
from . import comparison_20261028_accounting as account
from . import comparison_20261107_sid_cash_single_base_bundle as cash_bundle
from . import sid_cash_exclusion_20261107 as mask
from . import extended_evidence as evidence
from . import extended_metrics as metrics

MODULE = "research/target_price_revisions_qc/comparison_20261107_sid_cash_single_base_results.py"
SOURCE_EPOCH = "TPR-SID-CASH-SINGLE-BASE-20261107-v2"
SINGLE_BASE_BUNDLE_MODULE = "research/target_price_revisions_qc/comparison_20261107_sid_cash_single_base_bundle.py"
SINGLE_BASE_BUNDLE_SHA256 = "fb75e8cde2f99b1ace170e42d74d00b77714b3611a1dc7c117f5ec3f614e0dd1"
RESULT_SCHEMA = "tpr-sid-cash-completion-binding-v1"
ACCOUNTING_SOURCE = "research/target_price_revisions_qc/comparison_20261028_accounting.py"
ACCOUNTING_SOURCE_SHA256 = "9ff8df1cf142308d8cd73e2950ddfe02d64bbe88c02b5316b424f50cc49b1bc6"
COMPLETION_SOURCE = "research/target_price_revisions_qc/comparison_20261028_completion.py"
COMPLETION_SOURCE_SHA256 = "d0489d7c4e1c33207870f4c66e9bf0569145ba1be28f76edd4040685317e5467"
HELPER_PREFIX = "tpr_sid_cash_results_20261107"
NY, UTC = ZoneInfo("America/New_York"), timezone.utc
MAX_ORDERS, MAX_EVENTS = account.MAX_ORDERS, account.MAX_EVENTS
FILL_KEYS = account.FILL_KEYS
STUDY = cash_bundle.STUDY_ID
PREFIX = "research/target_price_revisions_qc/"
RAW_HELPER_PATH = "research/target_price_revisions_development/raw_revision.py"
RAW_HELPER_SHA256 = "ea4efcd9b0e73ae0b5c166d820c51e054559a3ed610041a6eb2acc8abca36353"
CANDIDATES = {"cap_off": STUDY + "-OFF", "cap_tilt_50": STUDY + "-CAP-TILT-50",
    "cap_tilt_100": STUDY + "-CAP-TILT-100", "cap_tilt_200": STUDY + "-CAP-TILT-200",
    "pure_tpr": STUDY + "-PURE-TPR"}
KINDS = frozenset(("SUBSCRIPTION", "MEMBERSHIP", "CAPS", "COVERAGE", "FACTOR",
    "ORDER", "FILL", "ACTION", "NAV", "SUMMARY"))
MAX_CHUNKS, MAX_CHUNK_BYTES = 1024, 512 * 1024
MAX_JOURNAL_BYTES, MAX_RECORDS = 256 * 1024 * 1024, 300000
ENVELOPES = {"summary": 512 * 1024, "index": 2 * 1024 * 1024,
    "config": 64 * 1024, "calendar": 512 * 1024, "source_calendar": 512 * 1024}
BINDING_KEYS = frozenset(("schema", "study_id", "candidate_id", "arm", "project_id", "job_id",
    "operation_id", "attempt", "terminal_status", "terminal_evidence_sha256",
    "config_sha256", "policy_sha256", "calendar_sha256", "source_template_closure_sha256",
    "prior_attempts_looks_sha256", "template_source_hashes", "rendered_source_hashes",
    "rendered_source_closure_sha256", "envelopes"))
CONFIG_KEYS = frozenset(("schema", "study_id", "candidate_id", "arm", "operation_id", "attempt",
    "project_id", "policy_sha256", "calendar_sha256", "source_template_closure_sha256",
    "prior_attempts_looks_sha256", "source_inputs_admitted", "canonical_admission"))
SUMMARY_KEYS = frozenset(("schema", "study_id", "candidate_id", "arm", "operation_id", "attempt",
    "config_sha256", "policy_sha256", "calendar_sha256", "source_template_closure_sha256",
    "project_id", "job_id", "decisions", "refused_decisions", "valuation_days", "coverage_complete",
    "calendar_complete", "internally_useful_order_run", "accounting_parity_within_cent",
    "submitted_orders", "fill_events", "requested_shares", "submitted_shares", "filled_shares", "fees",
    "last_observed_nav", "last_valuation_session", "final_nav", "max_cash_residual", "max_nav_residual",
    "position_ledger_mismatches", "risk_breaches", "max_name_exposure", "name_soft_cap_breaches",
    "clock_assertions", "reason_counts", "delisting_audit", "mark_verification",
    "source_inputs_admitted", "native_basis_authenticated", "full_evidence_retrieval_verified",
    "strategy_accepted", "canonical_admission", "accepted_performance"))
INDEX_KEYS = frozenset(("schema", "study_id", "candidate_id", "config_sha256", "project_id", "job_id",
    "config", "records", "plain_bytes", "kind_counts", "chunks", "encoding", "source_inputs_admitted",
    "strategy_accepted", "canonical_admission"))
DAILY_NAV_KEYS = frozenset(("session", "nav", "cash", "gross_exposure", "risk_within_unlevered_account",
    "max_name_exposure", "name_cap_is_prior_close_soft_target", "position_ledger_mismatches",
    "cash_ledger_residual", "nav_ledger_residual", "holdings", "cash_ledger", "fees",
    "independent_holdings_value", "holdings_value_residual", "raw_marks"))
PROOF_KEYS = frozenset(("record_type", "schema", "session", "security_id", "mode", "decision_id",
    "project_id", "job_id", "config_sha256", "source_template_closure_sha256", "policy_sha256",
    "calendar_sha256", "request", "original_minute_end_utc", "daily_end_utc", "daily_time_utc",
    "daily_close", "daily_volume", "native_snapshot", "daily_access_claim", "minute_endpoint_equals_close",
    "daily_price_equals_unchanged_cache", "native_snapshot_unchanged", "source_inputs_admitted", "canonical_admission"))
BAD_REASONS = frozenset(("missing_mark", "missing_action_custody", "unknown_share_basis",
    "basis_native_action_mismatch", "unpriced_held_nav", "missing_prior_close_nav", "qc_invalid_order",
    "qc_canceled_order"))
_FALSE_FIELDS = ("source_inputs_admitted", "native_basis_authenticated", "full_evidence_retrieval_verified",
    "strategy_accepted", "canonical_admission")


class CompletionRefusal(ValueError):
    """Closed refusal; private bodies and values never appear in the message."""


def _fail():
    raise CompletionRefusal("SID-CASH supplied completion evidence refused") from None


def _closed(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        _fail()


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None or value == "0" * 64:
        _fail()
    return value


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _integer(value, maximum=2**63 - 1, minimum=0):
    if type(value) is evidence.JsonNumber:
        if re.fullmatch(r"0|[1-9][0-9]*", value.lexeme) is None:
            _fail()
        value = int(value.lexeme)
    if type(value) is not int or not minimum <= value <= maximum:
        _fail()
    return value


def _fraction(value, *, text=False):
    if type(value) is dict:
        _closed(value, ("numerator", "denominator"))
        n, d = value["numerator"], value["denominator"]
        if (type(n) is not str or type(d) is not str or max(len(n), len(d)) > 1024
                or re.fullmatch(r"-?(?:0|[1-9][0-9]*)", n) is None
                or re.fullmatch(r"[1-9][0-9]*", d) is None):
            _fail()
        result = Fraction(int(n), int(d))
        if str(result.numerator) != n or str(result.denominator) != d:
            _fail()
    elif type(value) is evidence.JsonNumber:
        result = metrics._exact(value)
    elif text and type(value) is str:
        result = metrics._exact(evidence.JsonNumber(value))
    else:
        _fail()
    if max(result.numerator.bit_length(), result.denominator.bit_length()) > 4096:
        _fail()
    return result


def _same(left, right):
    return evidence.canonical(left) == evidence.canonical(right)


def _native_wire(value):
    # Renderers hash compact sorted ASCII JSON without a trailing newline.
    return evidence.canonical(value)[:-1]


def _sources(values, *, template):
    if type(values) is not dict or not 1 <= len(values) <= 48:
        _fail()
    for path, digest in values.items():
        if (type(path) is not str or len(path) > 256 or ".." in path.split("/")
                or re.fullmatch(r"[A-Za-z0-9_./-]+", path) is None
                or (template and not path.startswith(PREFIX)
                    and not (path == RAW_HELPER_PATH and digest == RAW_HELPER_SHA256))
                or (not template and "/" in path)):
            _fail()
        _hash(digest)
    return dict(values)


def _load(raw, descriptor, maximum):
    _closed(descriptor, ("sha256", "bytes"))
    if (type(raw) is not bytes or not 0 < len(raw) <= maximum
            or _integer(descriptor["bytes"], maximum, 1) != len(raw)
            or _hash(descriptor["sha256"]) != _sha(raw)):
        _fail()
    return evidence.parse_json(raw)


def _safe_report(summary, index, binding, observable_useful):
    return {"schema": "tpr-sid-cash-completion-framing-report-v1", "study_id": STUDY,
        "candidate_id": binding["candidate_id"], "arm": binding["arm"], "project_id": binding["project_id"],
        "job_id": binding["job_id"], "operation_id": binding["operation_id"], "attempt": binding["attempt"],
        "terminal_completed_as_supplied": True, "terminal_evidence_sha256": binding["terminal_evidence_sha256"],
        "summary_sha256": binding["envelopes"]["summary"]["sha256"],
        "index_sha256": binding["envelopes"]["index"]["sha256"], "config_sha256": binding["config_sha256"],
        "source_template_closure_sha256": binding["source_template_closure_sha256"],
        "rendered_source_closure_sha256": binding["rendered_source_closure_sha256"],
        "producer_useful_run_claim": summary["internally_useful_order_run"],
        "observable_summary_useful_conditions": observable_useful,
        "warmup_proof_independently_replayed": False, "summary_index_binding_checked": True,
        "journal_chunks_planned": len(index["chunks"]), "journal_records_planned": _integer(index["records"]),
        "journal_bytes_planned": _integer(index["plain_bytes"]), "journal_framing_replayed": False,
        "daily_nav_observations": None, "daily_nav_axis_complete": False, "reported_nav_metrics": None,
        "independent_order_fill_action_cash_reconciliation": False, "full_evidence_retrieval_verified": False,
        "native_origin_authenticated": False, "backend_durability_proven": False,
        "source_inputs_admitted": False, "historical_pit_authenticated": False, "data_rights_authenticated": False,
        "native_permission": False, "strategy_accepted": False, "canonical_admission": False,
        "accepted_performance": None,
        "summary_aggregates": {key: _integer(summary[key]) for key in
            ("decisions", "refused_decisions", "valuation_days", "submitted_orders", "fill_events",
             "position_ledger_mismatches", "risk_breaches")},
        "reported_fees": metrics._out(_fraction(summary["fees"]))}


def _validate(raws, binding, expected):
    _identity(binding, expected)
    _closed(binding["envelopes"], ENVELOPES)
    bodies = {name: _load(raws[name], binding["envelopes"][name], maximum) for name, maximum in ENVELOPES.items()}
    config, summary, index, calendar, source = (bodies[name] for name in ("config", "summary", "index", "calendar", "source_calendar"))
    if (_sha(raws["config"]) != binding["config_sha256"] or _sha(raws["calendar"]) != binding["calendar_sha256"]):
        _fail()
    sessions = metrics._calendar(raws["source_calendar"])
    expected_calendar = {"schema": "tpr-cmp28-calendar-candidate-v1", "study_id": STUDY,
        "policy_sha256": binding["policy_sha256"], "source_calendar_sha256": metrics.CALENDAR_SHA256,
        "timezone": "America/New_York", "start": "2021-01-04", "end": "2026-10-09", "warmup_start": "2020-09-01",
        "valuation_count": 1449, "decision_count": 301, "valuation_sessions": list(sessions),
        "warmup_sessions": source["warmup_sessions"], "decisions": source["decisions"], "no_market_outcomes": True}
    if not _same(calendar, expected_calendar) or len(source["decisions"]) != 301:
        _fail()
    multi = binding["arm"] != "cap_off"
    _closed(config, CONFIG_KEYS | ({"signal_packet"} if multi else set()))
    if config["schema"] != ("tpr-cmp28-multi-native-config-v1" if multi else "tpr-cmp28-off-native-config-v1"):
        _fail()
    for key in ("study_id", "candidate_id", "arm", "operation_id", "attempt", "project_id", "policy_sha256",
                "calendar_sha256", "source_template_closure_sha256", "prior_attempts_looks_sha256"):
        if not _same(config[key], binding[key]):
            _fail()
    if config["source_inputs_admitted"] is not False or config["canonical_admission"] is not False:
        _fail()
    if multi:
        packet = config["signal_packet"]
        _closed(packet, ("key", "sha256", "bytes", "encoding", "source_inventory_sha256"))
        if (type(packet["key"]) is not str or len(packet["key"]) > 512
                or not packet["key"].startswith("tpr-cmp28/inputs/")
                or re.fullmatch(r"[A-Za-z0-9_./-]+", packet["key"]) is None
                or any(part in ("", ".", "..") for part in packet["key"].split("/"))
                or packet["encoding"] != "utf-8-json"):
            _fail()
        _hash(packet["sha256"]); _hash(packet["source_inventory_sha256"])
        _integer(packet["bytes"], 512 * 1024 * 1024, 1)
    _closed(summary, SUMMARY_KEYS | ({"signal_runtime_access"} if multi else set()))
    if summary["schema"] != ("tpr-cmp28-multi-native-summary-v1" if multi else "tpr-cmp28-off-native-summary-v1"):
        _fail()
    for key in ("study_id", "candidate_id", "arm", "operation_id", "attempt", "project_id", "job_id",
                "config_sha256", "policy_sha256", "calendar_sha256", "source_template_closure_sha256"):
        if not _same(summary[key], binding[key]):
            _fail()
    if any(summary[key] is not False for key in _FALSE_FIELDS) or summary["accepted_performance"] is not None:
        _fail()
    for key in ("coverage_complete", "calendar_complete", "internally_useful_order_run", "accounting_parity_within_cent"):
        if type(summary[key]) is not bool:
            _fail()
    counts = {key: _integer(summary[key]) for key in ("decisions", "refused_decisions", "valuation_days",
        "submitted_orders", "fill_events", "position_ledger_mismatches", "risk_breaches", "name_soft_cap_breaches", "clock_assertions")}
    if counts["decisions"] > 301 or counts["refused_decisions"] > 301 or counts["valuation_days"] > 1449:
        _fail()
    for key in ("requested_shares", "submitted_shares", "filled_shares", "fees", "max_cash_residual", "max_nav_residual", "max_name_exposure"):
        if _fraction(summary[key]) < 0:
            _fail()
    if type(summary["reason_counts"]) is not dict or len(summary["reason_counts"]) > 256:
        _fail()
    reasons = {}
    for key, value in summary["reason_counts"].items():
        if type(key) is not str or re.fullmatch(r"[A-Za-z0-9_]{1,100}", key) is None:
            _fail()
        reasons[key] = _integer(value)
    cap_observer.validate_audit({key: _integer(value, cap_observer.MAX_EVENTS)
        for key, value in summary["delisting_audit"].items()}, reasons.get("delisting_event", 0))
    mark = summary["mark_verification"]
    _closed(mark, ("mode", "decision_id", "strict_minute_marks", "daily_requests", "daily_claims_attempted",
        "daily_claims_verified", "daily_corroborated_marks", "refused_marks", "minute_endpoints_rewritten", "prices_substituted"))
    if mark["mode"] != "strict_minute_or_raw_daily_equal_close_v1" or mark["decision_id"] != "TPR-CMP104-D009":
        _fail()
    mark_counts = {key: _integer(value, 86940 if key.startswith("daily_") else 2**63 - 1)
        for key, value in mark.items() if key not in ("mode", "decision_id")}
    if (mark_counts["minute_endpoints_rewritten"] or mark_counts["prices_substituted"]
            or not mark_counts["daily_corroborated_marks"] <= mark_counts["daily_requests"] <= mark_counts["daily_claims_verified"] <= mark_counts["daily_claims_attempted"]):
        _fail()
    if multi:
        runtime = summary["signal_runtime_access"]
        _closed(runtime, ("claim_attempts", "claim_same_node_verified", "backend_durability_proven", "claim_key", "claim_sha256",
            "claim_bytes", "packet_reads", "provider_ready", "scores_calls", "drain_calls", "faulted", "packet_scope_spent", "actual_job_bound"))
        for key in ("claim_same_node_verified", "backend_durability_proven", "provider_ready", "faulted", "packet_scope_spent", "actual_job_bound"):
            if type(runtime[key]) is not bool:
                _fail()
        if runtime["backend_durability_proven"] is not False:
            _fail()
        for key, maximum in (("claim_attempts", 1), ("packet_reads", 1), ("scores_calls", 301), ("drain_calls", 1000000)):
            _integer(runtime[key], maximum)
        if runtime["claim_key"] is not None and (type(runtime["claim_key"]) is not str or len(runtime["claim_key"]) > 1024):
            _fail()
        expected_claim = ("tpr-cmp28/evidence/" + STUDY + "/" + binding["operation_id"] + "/" + binding["config_sha256"]
            + "/attempt-" + str(binding["attempt"]) + "/" + str(binding["project_id"]) + "/" + binding["job_id"] + "/signal-packet-access.json")
        if runtime["claim_key"] is not None and runtime["claim_key"] != expected_claim:
            _fail()
        if runtime["claim_sha256"] is not None:
            _hash(runtime["claim_sha256"])
        if runtime["claim_bytes"] is not None:
            _integer(runtime["claim_bytes"], 4096, 1)
    parity = (counts["position_ledger_mismatches"] == counts["risk_breaches"] == 0
        and _fraction(summary["max_cash_residual"]) <= Fraction(1, 100)
        and _fraction(summary["max_nav_residual"]) <= Fraction(1, 100))
    if summary["accounting_parity_within_cent"] != parity:
        _fail()
    if summary["calendar_complete"] and (counts["decisions"] != 301 or counts["valuation_days"] != 1449
            or summary["last_valuation_session"] != sessions[-1]):
        _fail()
    if summary["last_valuation_session"] is not None and summary["last_valuation_session"] not in sessions:
        _fail()
    if summary["last_observed_nav"] is None:
        if summary["last_valuation_session"] is not None or counts["valuation_days"]:
            _fail()
    elif _fraction(summary["last_observed_nav"]) <= 0 or summary["last_valuation_session"] is None:
        _fail()
    final_required = summary["calendar_complete"] and summary["last_valuation_session"] == sessions[-1]
    if final_required:
        if summary["final_nav"] is None or _fraction(summary["final_nav"]) != _fraction(summary["last_observed_nav"]):
            _fail()
    elif summary["final_nav"] is not None:
        _fail()
    useful = (summary["calendar_complete"] and summary["coverage_complete"] and parity
        and counts["decisions"] == 301 and not counts["refused_decisions"] and counts["fill_events"] > 0
        and not any(reasons.get(key, 0) for key in BAD_REASONS))
    if summary["internally_useful_order_run"] and not useful:
        _fail()
    if multi and summary["internally_useful_order_run"]:
        if (runtime["provider_ready"] is not True or runtime["faulted"] is not False
                or runtime["actual_job_bound"] is not True or runtime["packet_scope_spent"] is not True
                or runtime["claim_same_node_verified"] is not True or runtime["claim_key"] is None
                or runtime["claim_sha256"] is None or runtime["claim_bytes"] is None
                or _integer(runtime["packet_reads"]) != 1 or _integer(runtime["scores_calls"]) != 301):
            _fail()
    _closed(index, INDEX_KEYS)
    if (index["schema"] != "tpr-cmp28-private-journal-index-v2-plain" or index["encoding"] != "utf-8-jsonl"
            or any(index[key] is not False for key in ("source_inputs_admitted", "strategy_accepted", "canonical_admission"))
            or not _same(index["config"], config)):
        _fail()
    for key in ("study_id", "candidate_id", "config_sha256", "project_id", "job_id"):
        if not _same(index[key], binding[key]):
            _fail()
    records, plain = _integer(index["records"], MAX_RECORDS, 1), _integer(index["plain_bytes"], MAX_JOURNAL_BYTES, 1)
    if records < 1 + counts["valuation_days"] + mark_counts["daily_corroborated_marks"]:
        _fail()
    kinds = index["kind_counts"]
    if type(kinds) is not dict or not set(kinds) <= KINDS or not kinds:
        _fail()
    kind_counts = {key: _integer(value, MAX_RECORDS, 1) for key, value in kinds.items()}
    if (sum(kind_counts.values()) != records or kind_counts.get("SUMMARY") != 1
            or kind_counts.get("NAV", 0) != counts["valuation_days"] + mark_counts["daily_corroborated_marks"]):
        _fail()
    chunks = index["chunks"]
    if type(chunks) is not list or not 1 <= len(chunks) <= MAX_CHUNKS:
        _fail()
    prefix = ("tpr-cmp28/evidence/" + STUDY + "/" + binding["operation_id"] + "/" + binding["config_sha256"]
        + "/attempt-" + str(binding["attempt"]) + "/" + str(binding["project_id"]) + "/" + binding["job_id"] + "/")
    total = 0
    for number, chunk in enumerate(chunks):
        _closed(chunk, ("key", "bytes", "sha256"))
        if chunk["key"] != prefix + f"chunk-{number:04d}.jsonl":
            _fail()
        total += _integer(chunk["bytes"], MAX_CHUNK_BYTES, 1)
        _hash(chunk["sha256"])
    if total != plain:
        _fail()
    return bodies, sessions, _safe_report(summary, index, binding, useful)


def _call(raws, binding, expected):
    try:
        return _validate(raws, binding, expected)
    except CompletionRefusal:
        raise
    except Exception:
        _fail()


def _validate_completion(summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw, *, binding, expected):
    """Safe supplied-byte framing report; never a native or retrieval authority."""
    return _call(dict(zip(ENVELOPES, (summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw))), binding, expected)[2]


def _chunk_replay_plan(summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw, *, binding, expected):
    """PRIVATE exact-key plan only; caller must reserve each actual retrieval."""
    bodies, _, _ = _call(dict(zip(ENVELOPES, (summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw))), binding, expected)
    return [{"ordinal": number, "key": chunk["key"], "bytes": _integer(chunk["bytes"]), "sha256": chunk["sha256"]}
        for number, chunk in enumerate(bodies["index"]["chunks"])]


def _replay_chunks(summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw, *, binding, chunks, expected):
    """Replay supplied bytes only. Independent fills/actions/cash remain pending."""
    try:
        bodies, sessions, report = _call(dict(zip(ENVELOPES, (summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw))), binding, expected)
        index, summary = bodies["index"], bodies["summary"]
        if type(chunks) is not list or len(chunks) != len(index["chunks"]):
            _fail()
        ordinal, kinds, daily, proofs = 0, {}, {}, 0
        for raw, descriptor in zip(chunks, index["chunks"]):
            if (type(raw) is not bytes or len(raw) != _integer(descriptor["bytes"])
                    or len(raw) > MAX_CHUNK_BYTES or _sha(raw) != descriptor["sha256"] or not raw.endswith(b"\n")):
                _fail()
            for line in raw.splitlines(keepends=True):
                ordinal += 1
                if ordinal > MAX_RECORDS or not line.endswith(b"\n") or line == b"\n":
                    _fail()
                record = evidence.parse_json(line)
                _closed(record, ("ordinal", "kind", "payload"))
                if _integer(record["ordinal"], MAX_RECORDS, 1) != ordinal or record["kind"] not in KINDS:
                    _fail()
                kind, payload = record["kind"], record["payload"]
                if type(payload) is not dict:
                    _fail()
                kinds[kind] = kinds.get(kind, 0) + 1
                if kind == "SUMMARY":
                    if ordinal != _integer(index["records"]) or not _same(payload, summary):
                        _fail()
                if kind != "NAV":
                    continue
                if "record_type" in payload:
                    _closed(payload, PROOF_KEYS)
                    if (payload["record_type"] != "raw_daily_equal_close_corroboration"
                            or payload["schema"] != "tpr-cmp28-raw-daily-close-proof-v1"
                            or payload["session"] not in sessions
                            or payload["mode"] != "strict_minute_or_raw_daily_equal_close_v1"
                            or payload["decision_id"] != "TPR-CMP104-D009"
                            or payload["minute_endpoint_equals_close"] is not False
                            or any(payload[key] is not True for key in ("daily_price_equals_unchanged_cache", "native_snapshot_unchanged"))
                            or any(payload[key] is not False for key in ("source_inputs_admitted", "canonical_admission"))):
                        _fail()
                    for key in ("project_id", "job_id", "config_sha256", "policy_sha256", "calendar_sha256", "source_template_closure_sha256"):
                        if not _same(payload[key], binding[key]):
                            _fail()
                    proofs += 1
                    continue
                _closed(payload, DAILY_NAV_KEYS)
                day = payload["session"]
                if day not in sessions or day in daily:
                    _fail()
                if type(payload["nav"]) is not str:
                    _fail()
                nav = _fraction(payload["nav"], text=True)
                if nav <= 0:
                    _fail()
                if type(payload["risk_within_unlevered_account"]) is not bool or payload["name_cap_is_prior_close_soft_target"] is not True:
                    _fail()
                _integer(payload["position_ledger_mismatches"])
                for key in ("cash", "gross_exposure", "max_name_exposure", "cash_ledger_residual", "nav_ledger_residual"):
                    _fraction(payload[key], text=True)
                for key in ("cash_ledger", "fees", "independent_holdings_value", "holdings_value_residual"):
                    _fraction(payload[key])
                if type(payload["holdings"]) is not list or type(payload["raw_marks"]) is not list:
                    _fail()
                daily[day] = nav
        if ordinal != _integer(index["records"]) or kinds != {key: _integer(value) for key, value in index["kind_counts"].items()}:
            _fail()
        if len(daily) != _integer(summary["valuation_days"]):
            _fail()
        ordered = tuple(daily)
        if ordered != tuple(day for day in sessions if day in daily):
            _fail()
        if daily:
            if summary["last_valuation_session"] != ordered[-1] or _fraction(summary["last_observed_nav"]) != daily[ordered[-1]]:
                _fail()
        if proofs != _integer(summary["mark_verification"]["daily_corroborated_marks"]):
            _fail()
        full_axis = ordered == sessions
        if summary["calendar_complete"] and not full_axis:
            _fail()
        report.update({"journal_framing_replayed": True, "daily_nav_observations": len(daily),
            "nav_kind_records": kinds.get("NAV", 0), "daily_close_corroboration_proofs": proofs,
            "daily_nav_axis_complete": full_axis,
            "reported_nav_metrics": metrics._nav(tuple(daily[day] for day in sessions), sessions) if full_axis else None,
            "reported_nav_metrics_basis": "supplied journal decimal NAV observations; native authenticity and account reconciliation pending"})
        return report
    except CompletionRefusal:
        raise
    except Exception:
        _fail()


def _identity(binding, expected):
    """Closed new identity compared with a freshly regenerated fixed candidate."""
    _closed(binding, BINDING_KEYS)
    if (binding["schema"] != RESULT_SCHEMA or binding["study_id"] != STUDY
            or type(binding["arm"]) is not str or binding["arm"] not in CANDIDATES
            or binding["candidate_id"] != CANDIDATES[binding["arm"]]
            or type(binding["project_id"]) is not int
            or binding["project_id"] != expected["project_id"]
            or type(binding["job_id"]) is not str
            or re.fullmatch("[0-9a-f]{32}", binding["job_id"]) is None
            or type(binding["attempt"]) is not int or not 1 <= binding["attempt"] <= 3
            or binding["terminal_status"] != "Completed"):
        _fail()
    prefix = ("TPR-CMP28-OFF-SID-CASH-20261107-" if binding["arm"] == "cap_off"
        else "TPR-CMP28-SID-CASH-20261107-")
    if (type(binding["operation_id"]) is not str or len(binding["operation_id"]) > 160
            or re.fullmatch(re.escape(prefix) + "[A-Za-z0-9][A-Za-z0-9_.-]*", binding["operation_id"]) is None):
        _fail()
    for key in ("terminal_evidence_sha256", "config_sha256", "policy_sha256",
            "calendar_sha256", "source_template_closure_sha256",
            "prior_attempts_looks_sha256", "rendered_source_closure_sha256"):
        _hash(binding[key])
    for key in ("study_id", "candidate_id", "arm", "operation_id", "attempt", "project_id",
            "config_sha256", "policy_sha256", "calendar_sha256",
            "source_template_closure_sha256", "prior_attempts_looks_sha256",
            "template_source_hashes", "rendered_source_hashes", "rendered_source_closure_sha256"):
        if not _same(binding[key], expected[key]):
            _fail()
    for key in ("job_id", "terminal_evidence_sha256"):
        if key in expected and binding[key] != expected[key]:
            _fail()


def _expected(binding, public_sources, project_bindings_raw, registry_sha256):
    """No input/packet opener; regenerate all candidate output identities."""
    files, report_raw = cash_bundle.build_cash_candidate(public_sources=public_sources,
        project_bindings_raw=project_bindings_raw,
        expected_project_bindings_sha256=registry_sha256, arm=binding["arm"],
        operation_id=binding["operation_id"], attempt=binding["attempt"],
        prior_attempts_looks_sha256=binding["prior_attempts_looks_sha256"],
        latest_owner_instruction_sha256=cash_bundle.OWNER_SHA256)
    report = json.loads(report_raw)
    if (report.get("schema") != "tpr-cmp1107-sid-cash-single-base-project-bundle-v2"
            or report.get("source_epoch") != SOURCE_EPOCH):
        _fail()
    config = cash_bundle.preflight._config(files["comparison_20261028_config.py"])
    return {**{key: config[key] for key in ("study_id", "candidate_id", "arm",
        "operation_id", "attempt", "project_id", "policy_sha256", "calendar_sha256",
        "source_template_closure_sha256", "prior_attempts_looks_sha256")},
        "config_sha256": report["config_sha256"],
        "template_source_hashes": report["template_source_hashes"],
        "rendered_source_hashes": report["cloud_source_hashes"],
        "rendered_source_closure_sha256": report["rendered_source_closure_sha256"]}


def _plain(value):
    if type(value) is dict:
        if set(value) == {"numerator", "denominator"}:
            return _fraction(value)
        return {key: _plain(item) for key, item in value.items()}
    if type(value) is list:
        return [_plain(item) for item in value]
    if type(value) is evidence.JsonNumber:
        if re.fullmatch("-?(?:0|[1-9][0-9]*)", value.lexeme) is None:
            _fail()
        return int(value.lexeme)
    return value


def _encoded(value):
    if type(value) is Fraction:
        return {"numerator": str(value.numerator), "denominator": str(value.denominator)}
    if type(value) is dict:
        return {key: _encoded(item) for key, item in value.items()}
    if type(value) in (list, tuple):
        return [_encoded(item) for item in value]
    return value


def _excluded(sid):
    if (type(sid) is not str or not 1 <= len(sid) <= 128 or not sid.isascii()
            or sid.strip() != sid or any(ord(char) < 32 or ord(char) == 127 for char in sid)):
        _fail()
    return _sha(sid.encode("ascii")) == mask.EXCLUDED_SID_SHA256


def _mask_replay(chunks, source_calendar_raw, binding):
    """Independent journal exclusion/cash/decision and submitted-clock replay."""
    source = evidence.parse_json(source_calendar_raw)
    decisions = tuple(row["session"] for row in source["decisions"])
    expected_days, coverage, audits = set(decisions), {}, {}
    census = None
    submitted, masks, slots = 0, 0, 0
    for raw in chunks:
        for line in raw.splitlines():
            record = evidence.parse_json(line)
            kind, row = record["kind"], record["payload"]
            if kind == "COVERAGE" and row.get("kind") == "sid_cash_exclusion_execution_mask":
                day = row.get("session")
                if day not in expected_days or day in audits:
                    _fail()
                audits[day] = row
            elif kind == "COVERAGE" and row.get("kind") == "sid_cash_exclusion_census":
                if census is not None:
                    _fail()
                census = row
            elif kind == "COVERAGE" and "construction" in row:
                day = row.get("session")
                if day not in expected_days or day in coverage or day not in audits or row.get("arm") != binding["arm"]:
                    _fail()
                construction = _plain(row["construction"])
                if (construction.get("schema") != "tpr-five-arm-construction-candidate-v1"
                        or construction.get("study_id") != STUDY
                        or construction.get("arm") != binding["arm"]):
                    _fail()
                weights = {}
                for sleeve in mask._SID_CASH_SLEEVES:
                    for sid, weight in construction["per_sleeve"][sleeve]["target_weights"].items():
                        weights[sid] = weights.get(sid, Fraction(0)) + weight
                digests = {sid: _sha(sid.encode("ascii")) for sid in weights if type(sid) is str and sid.isascii()}
                after, audit = mask.plan_cash_exclusion(weights, construction, digests)
                if not _same(row.get("execution_mask"), _encoded(audit)):
                    _fail()
                expected_audit = {"kind": "sid_cash_exclusion_execution_mask", "session": day, **_encoded(audit)}
                if not _same(audits[day], expected_audit):
                    _fail()
                semantics = row.get("coverage_semantics")
                if (type(semantics) is not dict
                        or semantics.get("execution_mask") != "post_construction_fixed_sid_to_cash"
                        or row.get("source_inputs_admitted") is not False
                        or any(_excluded(sid) for sid in after)):
                    _fail()
                coverage[day] = audit
                masks += int(audit["masked_unique_target_count"] > 0)
                slots += audit["masked_selected_slot_occurrences"]
            elif kind == "ORDER":
                if "security_id" in row and _excluded(row["security_id"]):
                    _fail()
                if "planned" in row:
                    if type(row["planned"]) is not list:
                        _fail()
                    if any(_excluded(plan["security_id"]) for plan in row["planned"]):
                        _fail()
                    marks = row.get("marks")
                    if type(marks) is not dict or any(_excluded(sid) for sid in marks):
                        _fail()
                else:
                    day = row.get("session")
                    stamp = account._clock(row.get("utc"))
                    local = stamp.astimezone(NY)
                    if (day not in expected_days or local.date().isoformat() != day
                            or (local.hour, local.minute, local.second, local.microsecond) != (9, 20, 0, 0)
                            or _integer(row.get("order_id"), minimum=1) < 1
                            or not _fraction(row.get("submitted"))):
                        _fail()
                    expected_intent = hashlib.sha256((binding["candidate_id"] + ":" + day + ":" + row["security_id"]).encode()).hexdigest()[:20]
                    if row.get("intent") != expected_intent:
                        _fail()
                    submitted += 1
            elif kind == "FILL" and _excluded(row.get("security_id")):
                _fail()
            elif kind == "NAV" and "record_type" not in row:
                if any(_excluded(item.get("security_id")) for item in row.get("holdings", [])):
                    _fail()
                if any(_excluded(item.get("security_id")) for item in row.get("raw_marks", [])):
                    _fail()
    if set(coverage) != expected_days or set(audits) != expected_days or census is None:
        _fail()
    expected_keys = {"kind", "schema", "study_id", "parent_study_id", "excluded_security_id_sha256",
        "guard_calls", "masked_decisions", "masked_slot_occurrences", "blocked_submission_attempts",
        "excluded_submitted_orders", "excluded_fill_events", "initializing", "excluded_native_quantity",
        "excluded_independent_quantity", "excluded_open_orders", "checked_native_order_history",
        "source_inputs_admitted", "strategy_accepted"}
    _closed(census, expected_keys)
    if (census["schema"] != mask.SID_CASH_SCHEMA or census["study_id"] != STUDY
            or census["parent_study_id"] != mask.PARENT_STUDY_ID
            or census["excluded_security_id_sha256"] != mask.EXCLUDED_SID_SHA256
            or census["checked_native_order_history"] is not True
            or any(census[key] is not False for key in ("initializing", "source_inputs_admitted", "strategy_accepted"))
            or _integer(census["masked_decisions"]) != masks
            or _integer(census["masked_slot_occurrences"]) != slots
            or _integer(census["guard_calls"]) < 2 * 1449 + 2 * 301 + 1
            or any(_integer(census[key]) for key in ("blocked_submission_attempts", "excluded_submitted_orders",
                "excluded_fill_events", "excluded_native_quantity", "excluded_independent_quantity", "excluded_open_orders"))):
        _fail()
    return {"execution_masks_replayed": len(coverage), "execution_cash_reconciliation_complete": True,
        "all_other_exact_weights_preserved_against_recorded_construction": True,
        "frozen_constructor_inputs_independently_reconstructed": False,
        "excluded_journal_holdings_orders_and_fills_zero": True,
        "excluded_runtime_final_census_zero": True, "submitted_clock_and_intent_count": submitted,
        "masked_decisions": masks, "masked_selected_slot_occurrences": slots,
        "runtime_census_is_native_authentication": False}


def validate_completion(summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw, *,
        binding, public_sources, project_bindings_raw, expected_project_bindings_sha256):
    try:
        expected = _expected(binding, public_sources, project_bindings_raw, expected_project_bindings_sha256)
        return _validate_completion(summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw,
            binding=binding, expected=expected)
    except CompletionRefusal:
        raise
    except Exception:
        _fail()


def chunk_replay_plan(summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw, *,
        binding, public_sources, project_bindings_raw, expected_project_bindings_sha256):
    try:
        expected = _expected(binding, public_sources, project_bindings_raw, expected_project_bindings_sha256)
        return _chunk_replay_plan(summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw,
            binding=binding, expected=expected)
    except CompletionRefusal:
        raise
    except Exception:
        _fail()


def replay_chunks(summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw, *,
        binding, chunks, public_sources, project_bindings_raw, expected_project_bindings_sha256):
    try:
        expected = _expected(binding, public_sources, project_bindings_raw, expected_project_bindings_sha256)
        report = _replay_chunks(summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw,
            binding=binding, chunks=chunks, expected=expected)
        report.update(_mask_replay(chunks, source_calendar_raw, binding))
        report.update(strategy_economics_changed=True, original_frozen_study_resolved=False,
            financial_accounting_pending=True, accepted_performance=None)
        return report
    except CompletionRefusal:
        raise
    except Exception:
        _fail()


def _audit_accounting(summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw, *,
        binding, chunks, expected):
    """Replay original exact account arithmetic against independent terminal history."""
    try:
        framing = _replay_chunks(summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw,
            binding=binding, chunks=chunks, expected=expected)
        exclusion = _mask_replay(chunks, source_calendar_raw, binding)
        observation, sessions = _native_history(chunks, source_calendar_raw, binding)
        reasons, census = observation["unknown_reasons"], observation["native_order_census"]
        records = iter(evidence.parse_json(line) for raw in chunks for line in raw.splitlines())
        quantities, seen_actions, matched = {}, set(), Counter()
        cash, fees, max_cash, max_nav = Fraction(100000), Fraction(0), Fraction(0), Fraction(0)
        max_name, name_breaches, fills, absolute_shares, remainders = Fraction(0), 0, 0, Fraction(0), 0
        mismatches_total = risk_breaches = 0
        final_audit = datetime.fromisoformat(sessions[-1]).replace(hour=16, minute=1, tzinfo=NY).astimezone(UTC)
        quantity_ok = ledger_ok = cash_ok = nav_ok = chart_ok = True
        daily, nav_vector, prior_time, pending = [], [], None, None
        while True:
            record = pending if pending is not None else next(records, None)
            pending = None
            if record is None:
                break
            kind, row = record["kind"], record["payload"]
            if kind == "ACTION":
                instant = account._clock(row.get("utc"), warmup=True)
                if instant > final_audit or prior_time is not None and instant < prior_time:
                    _fail()
                group = [row]
                while True:
                    candidate = next(records, None)
                    if candidate is None:
                        break
                    if candidate["kind"] != "ACTION" or account._clock(candidate["payload"].get("utc"), warmup=True) != instant:
                        pending = candidate; break
                    group.append(candidate["payload"])
                cash, missing = account._actions(group, quantities, cash, seen_actions, sessions)
                remainders += missing
                if missing:
                    reasons["unobserved_fractional_split_cash_in_lieu"] += missing
                prior_time = instant
            elif kind == "FILL":
                _closed(row, FILL_KEYS)
                sid, instant = account._sid(row["security_id"]), account._clock(row["utc"])
                if (instant > final_audit or instant.astimezone(NY).date().isoformat() not in sessions
                        or prior_time is not None and instant < prior_time):
                    _fail()
                prior_time = instant
                oid, status = _integer(row["order_id"], 2**63 - 1, 1), row["status"]
                if status not in metrics.STATUSES or type(row["native_final_exception"]) is not bool:
                    _fail()
                quantity, price, fee = (_fraction(row[key]) for key in ("quantity", "price", "fee"))
                if quantity.denominator != 1 or fee < 0 or price < 0 or quantity and (price <= 0 or status not in ("Filled", "PartiallyFilled")):
                    _fail()
                currency = row["fee_currency"]
                if currency != "USD" and not (currency in (None, "", "QCC") and fee == 0):
                    _fail()
                matched[(oid, sid, instant, status, quantity, price, fee, currency)] += 1
                if quantity:
                    fills += 1; absolute_shares += abs(quantity)
                    quantities[sid] = quantities.get(sid, Fraction(0)) + quantity
                    if quantities[sid] < 0:
                        _fail()
                fees += fee
                if cash is not None:
                    cash -= quantity * price + fee
                    ledger_ok &= _fraction(row["cash_ledger"]) == cash
                recorded = None if row["quantity_ledger"] is None else _fraction(row["quantity_ledger"])
                quantity_ok &= recorded == quantities.get(sid)
            elif kind == "NAV" and "record_type" not in row:
                day = row["session"]
                audit_time = datetime.fromisoformat(day).replace(hour=16, minute=1, tzinfo=NY).astimezone(UTC)
                if prior_time is not None and audit_time < prior_time:
                    _fail()
                prior_time = audit_time
                held, marks = {}, {}
                for item in row["holdings"]:
                    _closed(item, ("security_id", "quantity", "value")); sid = account._sid(item["security_id"])
                    q, value = _fraction(item["quantity"]), _fraction(item["value"])
                    if sid in held or q <= 0 or q.denominator != 1 or value <= 0:
                        _fail()
                    held[sid] = (q, value)
                for item in row["raw_marks"]:
                    _closed(item, ("security_id", "price", "mark_utc")); sid = account._sid(item["security_id"])
                    price, stamp = _fraction(item["price"]), account._clock(item["mark_utc"])
                    if sid in marks or price <= 0 or stamp > audit_time or stamp.astimezone(NY).date().isoformat() != day:
                        _fail()
                    marks[sid] = price
                if set(marks) != set(held):
                    _fail()
                replayed = {sid: q for sid, q in quantities.items() if q}
                native_quantities = {sid: value[0] for sid, value in held.items()}
                mismatches = sum(replayed.get(sid, 0) != native_quantities.get(sid, 0)
                    for sid in set(replayed) | set(native_quantities))
                mismatches_total += mismatches
                quantity_ok &= mismatches == 0 and _integer(row["position_ledger_mismatches"]) == mismatches
                if set(replayed) - set(marks):
                    _fail()
                independent = sum((q * marks[sid] for sid, q in replayed.items()), Fraction(0))
                native_held = sum((value for _, value in held.values()), Fraction(0))
                native_nav, native_cash = _fraction(row["nav"], text=True), _fraction(row["cash"], text=True)
                exposure = max((value / native_nav for _, value in held.values()), default=Fraction(0))
                max_name = max(max_name, exposure)
                name_breaches += sum(value / native_nav > Fraction(1, 10) for _, value in held.values())
                holding_residual = abs(native_held - independent)
                risk = native_cash >= -Fraction(1, 100) and 0 <= native_held <= native_nav + Fraction(1, 100)
                risk_breaches += not risk
                nav_ok &= all(abs(value - quantities.get(sid, Fraction(0)) * marks[sid]) <= Fraction(1, 100)
                    for sid, (_, value) in held.items())
                nav_ok &= (_fraction(row["independent_holdings_value"]) == independent
                    and _fraction(row["holdings_value_residual"]) == holding_residual
                    and row["gross_exposure"] == account._text(native_held / native_nav)
                    and row["max_name_exposure"] == account._text(exposure)
                    and _fraction(row["fees"]) == fees
                    and row["risk_within_unlevered_account"] == risk)
                if cash is not None:
                    cr, nr = abs(native_cash - cash), max(abs(native_nav - cash - independent), holding_residual)
                    max_cash, max_nav = max(max_cash, cr), max(max_nav, nr)
                    ledger_ok &= _fraction(row["cash_ledger"]) == cash
                    cash_ok &= cr <= Fraction(1, 100) and row["cash_ledger_residual"] == account._text(cr)
                    nav_ok &= nr <= Fraction(1, 100) and row["nav_ledger_residual"] == account._text(nr)
                daily.append(day)
                nav_vector.append((day, account._smart_round(native_nav)))
        summary = evidence.parse_json(summary_raw)
        event_agreement = (_history_fingerprint(matched) == observation["event_multiset_sha256"]
            and sum(matched.values()) == observation["known_event_count"])
        native_agreement = (event_agreement and census["events"] == sum(matched.values())
            and census["orders"] == len({key[0] for key in matched})
            and census["nonzero_fills"] == fills
            and census["absolute_filled_shares"] is not None and _fraction(census["absolute_filled_shares"]) == absolute_shares
            and census["reported_fees"] is not None and _fraction(census["reported_fees"]) == fees)
        native_agreement = native_agreement and not any(reasons[key] for key in reasons if key not in ("native_daily_nav_chart_unavailable", "unobserved_fractional_split_cash_in_lieu", "native_zero_fee_currency_unobserved"))
        nonzero = Counter({key: count for key, count in matched.items() if key[4]})
        zero_skeleton = Counter()
        for key, count in matched.items():
            if not key[4]:
                zero_skeleton[key[:6]] += count
        nonzero_fee_agreement = (census["nonzero_fills"] is not None and observation["observed_nonzero_fees"] is not None
            and census["nonzero_fills"] == sum(nonzero.values()) == observation["known_nonzero_fill_count"]
            and _fraction(census["absolute_filled_shares"]) == absolute_shares
            and _history_fingerprint(nonzero, domain="nonzero") == observation["nonzero_fill_multiset_sha256"]
            and sum((key[6] * count for key, count in nonzero.items()), Fraction(0)) == _fraction(observation["observed_nonzero_fees"]))
        zero_observation_agreement = (census["nonzero_fills"] is not None
            and census["events"] - census["nonzero_fills"] == sum(zero_skeleton.values()) == observation["known_zero_fill_skeleton_count"]
            and account._zero_fingerprint(zero_skeleton) == observation["zero_fill_skeleton_sha256"])
        zero_fee_complete = (census["nonzero_fills"] is not None
            and observation["known_event_count"] - observation["known_nonzero_fill_count"] == census["events"] - census["nonzero_fills"])
        if not event_agreement:
            reasons["native_journal_event_multiplicity_mismatch"] += 1
        full_axis = tuple(daily) == sessions
        chart_ok = False  # No engine chart is inferred from producer journal NAV.
        summary_ok = (fills == _integer(summary["fill_events"]) and absolute_shares == _fraction(summary["filled_shares"])
            and fees == _fraction(summary["fees"]) and max_name == _fraction(summary["max_name_exposure"])
            and name_breaches == _integer(summary["name_soft_cap_breaches"])
            and mismatches_total == _integer(summary["position_ledger_mismatches"])
            and risk_breaches == _integer(summary["risk_breaches"]))
        if cash is not None:
            summary_ok &= max_cash == _fraction(summary["max_cash_residual"]) and max_nav == _fraction(summary["max_nav_residual"])
        else:
            cash_ok = nav_ok = ledger_ok = False
        quantity_ok = bool(quantity_ok)
        ledger_ok, cash_ok, nav_ok, chart_ok = bool(ledger_ok), bool(cash_ok), bool(nav_ok), bool(chart_ok)
        reconciled = native_agreement and quantity_ok and ledger_ok and cash_ok and nav_ok and full_axis and summary_ok
        return {"schema": "tpr-sid-cash-supplied-accounting-report-v1", "study_id": STUDY,
            "candidate_id": binding["candidate_id"], "arm": binding["arm"], "project_id": binding["project_id"],
            "job_id": binding["job_id"], "operation_id": binding["operation_id"], "attempt": binding["attempt"],
            "config_sha256": binding["config_sha256"], "journal_index_sha256": binding["envelopes"]["index"]["sha256"],
            "api_input_binding_sha256": observation["api_input_binding_sha256"], "native_order_census": census,
            "terminal_history_source": "typed native parent OrderTicket snapshots retained in private journal",
            "ordered_api_envelopes_sha256": observation["ordered_api_envelopes_sha256"],
            "native_journal_fill_fee_agreement": native_agreement,
            "native_nonzero_fill_fee_agreement": nonzero_fee_agreement,
            "native_zero_fill_event_observation_agreement": zero_observation_agreement,
            "native_zero_fill_fee_observation_complete": zero_fee_complete,
            "native_observed_nonzero_fees": observation["observed_nonzero_fees"],
            "quantity_replay_matches_journal": quantity_ok,
            "cash_replay_within_cent": ledger_ok and cash_ok, "daily_nav_replay_within_cent": nav_ok,
            "daily_nav_axis_complete": full_axis, "daily_nav_observations": len(daily),
            "native_chart_rounding_agreement": chart_ok, "summary_replayed_aggregates_agree": bool(summary_ok),
            "fractional_held_splits_with_unobserved_cash_in_lieu": remainders,
            "max_cash_residual": metrics._out(max_cash) if cash is not None else None,
            "max_nav_residual": metrics._out(max_nav) if cash is not None else None,
            "replayed_fees": metrics._out(fees), "replayed_position_mismatches": mismatches_total,
            "replayed_risk_breaches": risk_breaches, "supplied_evidence_accounting_reconciled": bool(reconciled),
            "unknown_reasons": dict(sorted(reasons.items())),
            "engine_chart_observed": False, "engine_chart_agreement_pending": True,
            "journal_framing_replayed": framing["journal_framing_replayed"],
            "native_order_current_quantity_used_for_replay": False, "native_order_price_used_for_replay": False,
            "native_origin_authenticated": False, "backend_durability_proven": False,
            "historical_pit_authenticated": False, "data_rights_authenticated": False,
            "share_basis_authenticated": False, "full_evidence_retrieval_verified": False,
            "source_inputs_admitted": False, "strategy_accepted": False, "canonical_admission": False,
            "native_permission": False, "accepted_performance": None, "raw_api_pages_revalidated_in_child": False,
            "exact_journal_to_event_id_mapping_proven": False, "original_strategy_intent_verified": False,
            "moo_order_type_verified": False, "cancellation_policy_verified": False, "slippage_model_verified": False,
            "native_execution_timing_verified": False, "normalizer_source_custody_verified": False, **exclusion,
            "strategy_economics_changed": True, "original_frozen_study_resolved": False,
            "external_native_api_crosscheck_performed": False,
            "native_ticket_average_price_recomputed": False,
            "native_ticket_average_price_used_for_cash_or_nav": False}
    except CompletionRefusal:
        raise
    except Exception:
        _fail()


def _native_history(chunks, source_calendar_raw, binding):
    """Consume genuine terminal ticket-history observations, never fake API pages."""
    sessions = metrics._calendar(source_calendar_raw)
    orders, events, final, submitted, final_fill_ids = {}, {}, None, {}, set()
    claim = None
    order_chain = hashlib.sha256(b"tpr-sid-cash-native-orders-v1\n")
    event_chain = hashlib.sha256(b"tpr-sid-cash-native-events-v1\n")
    schema = "tpr-sid-cash-native-order-history-v1"
    order_fields = {"kind", "schema", "study_id", "order_id", "security_id", "order_type",
        "status", "quantity", "time_utc", "price_currency", "tag", "ticket_quantity",
        "ticket_quantity_filled", "ticket_average_fill_price", "ticket_status", "ticket_event_count"}
    event_fields = {"kind", "schema", "study_id", "order_id", "event_id", "security_id",
        "utc", "status", "fill_quantity", "fill_price", "fill_currency", "fee", "fee_currency", "is_assignment"}
    final_fields = {"kind", "schema", "study_id", "orders", "events", "nonzero_fills",
        "open_orders", "absolute_filled_shares", "reported_fees", "order_rows_sha256",
        "event_rows_sha256", "known_history", "stable_second_capture", "capture_utc",
        "claim_key", "claim_bytes", "claim_sha256", "claim_same_node_verified",
        "backend_durability_proven", "source_inputs_admitted", "strategy_accepted"}
    counts, fees, absolute, previous_oid = Counter(), Fraction(0), Fraction(0), 0
    native_events, zero_skeleton = Counter(), Counter()
    for raw in chunks:
        for line in raw.splitlines():
            record = evidence.parse_json(line)
            kind, row = record["kind"], record["payload"]
            if kind == "ORDER" and "order_id" in row:
                oid = _integer(row["order_id"], minimum=1)
                if oid in submitted:
                    _fail()
                submitted[oid] = row
            if kind == "FILL" and row.get("native_final_exception") is True:
                final_fill_ids.add(_integer(row["order_id"], minimum=1))
            if kind != "COVERAGE":
                continue
            role = row.get("kind")
            if role == "sid_cash_native_history_claim":
                if claim is not None or orders or final is not None:
                    _fail()
                _closed(row, {"kind", "schema", "study_id", "claim_key", "claim_bytes",
                    "claim_sha256", "claim_same_node_verified", "backend_durability_proven", "capture_utc"})
                claim = row
                continue
            if role not in ("sid_cash_native_order", "sid_cash_native_order_event", "sid_cash_native_history_census"):
                continue
            if final is not None or row.get("schema") != schema or row.get("study_id") != STUDY:
                _fail()
            if role == "sid_cash_native_order":
                _closed(row, order_fields)
                oid = _integer(row["order_id"], minimum=1)
                sid, instant = account._sid(row["security_id"]), account._clock(row["time_utc"])
                if (oid <= previous_oid or len(orders) >= MAX_ORDERS or _excluded(sid)
                        or row["price_currency"] != "USD" or type(row["tag"]) is not str
                        or len(row["tag"]) > 1024 or row["status"] not in ("Filled", "Canceled", "Invalid")
                        or row["ticket_status"] != row["status"]
                        or row["order_type"] not in ("MarketOnOpen", "Market")):
                    _fail()
                quantity = _fraction(row["quantity"])
                if (not quantity or quantity.denominator != 1
                        or _fraction(row["ticket_quantity"]) != quantity
                        or _fraction(row["ticket_quantity_filled"]).denominator != 1
                        or _fraction(row["ticket_average_fill_price"]) < 0):
                    _fail()
                _integer(row["ticket_event_count"], MAX_EVENTS)
                if oid in submitted:
                    source = submitted[oid]
                    if (row["order_type"] != "MarketOnOpen" or row["security_id"] != source["security_id"]
                            or quantity != _fraction(source["submitted"]) or row["time_utc"] != source["utc"]
                            or row["tag"] != "TPRE:" + source["intent"]):
                        _fail()
                elif row["order_type"] != "Market" or oid not in final_fill_ids:
                    _fail()
                previous_oid = oid
                orders[oid] = row
                events[oid] = []
                order_chain.update(_native_wire(row) + b"\n")
            elif role == "sid_cash_native_order_event":
                _closed(row, event_fields)
                oid = _integer(row["order_id"], minimum=1)
                eid = _integer(row["event_id"])
                if (oid not in orders or oid != previous_oid or counts["events"] >= MAX_EVENTS
                        or row["is_assignment"] is not False or row["status"] not in metrics.STATUSES
                        or row["security_id"] != orders[oid]["security_id"] or _excluded(row["security_id"])):
                    _fail()
                instant = account._clock(row["utc"])
                prior = events[oid][-1] if events[oid] else None
                if (instant < account._clock(orders[oid]["time_utc"])
                        or instant.astimezone(NY).date().isoformat() not in sessions
                        or prior is not None and (eid <= _integer(prior["event_id"])
                            or instant < account._clock(prior["utc"]))):
                    _fail()
                q, price, fee = (_fraction(row[key]) for key in ("fill_quantity", "fill_price", "fee"))
                if (q.denominator != 1 or q * _fraction(orders[oid]["quantity"]) < 0 or price < 0 or fee < 0
                        or q and (price <= 0 or row["status"] not in ("Filled", "PartiallyFilled")
                            or row["fill_currency"] != "USD")
                        or row["fill_currency"] not in (None, "", "USD") and not q
                        or row["fee_currency"] != "USD" and not (row["fee_currency"] in (None, "", "QCC") and fee == 0)):
                    _fail()
                key = (oid, row["security_id"], instant, row["status"], q, price, fee, row["fee_currency"])
                native_events[key] += 1
                if not q:
                    zero_skeleton[key[:6]] += 1
                events[oid].append(row)
                counts["events"] += 1
                counts["nonzero_fills"] += int(bool(q))
                absolute += abs(q)
                fees += fee
                event_chain.update(_native_wire(row) + b"\n")
            else:
                _closed(row, final_fields)
                final = row
    if final is None or claim is None or set(submitted) - set(orders):
        _fail()
    if (claim["schema"] != schema or claim["study_id"] != STUDY
            or claim["capture_utc"] != final["capture_utc"]
            or claim["claim_same_node_verified"] is not True or claim["backend_durability_proven"] is not False
            or any(not _same(claim[key], final[key]) for key in ("claim_key", "claim_bytes", "claim_sha256"))):
        _fail()
    capture = account._clock(final["capture_utc"])
    last_audit = datetime.fromisoformat(sessions[-1]).replace(hour=16, minute=1, tzinfo=NY).astimezone(UTC)
    if capture < last_audit:
        _fail()
    prefix = ("tpr-cmp28/evidence/" + STUDY + "/" + binding["operation_id"] + "/" + binding["config_sha256"]
        + "/attempt-" + str(binding["attempt"]) + "/" + str(binding["project_id"]) + "/" + binding["job_id"] + "/")
    if (type(final["claim_key"]) is not str or final["claim_key"] != prefix + "native-order-history-access.json"
            or len(final["claim_key"]) > 1024 or ".." in final["claim_key"].split("/")
            or any(final[key] is not True for key in ("known_history", "stable_second_capture", "claim_same_node_verified"))
            or any(final[key] is not False for key in ("backend_durability_proven", "source_inputs_admitted", "strategy_accepted"))
            or _integer(final["orders"], MAX_ORDERS) != len(orders)
            or _integer(final["events"], MAX_EVENTS) != counts["events"]
            or _integer(final["nonzero_fills"], MAX_EVENTS) != counts["nonzero_fills"]
            or _integer(final["open_orders"]) != 0
            or _fraction(final["absolute_filled_shares"]) != absolute
            or _fraction(final["reported_fees"]) != fees
            or final["order_rows_sha256"] != order_chain.hexdigest()
            or final["event_rows_sha256"] != event_chain.hexdigest()):
        _fail()
    _integer(final["claim_bytes"], 4096, 1)
    _hash(final["claim_sha256"])
    for oid, order in orders.items():
        rows = events[oid]
        quantity = sum((_fraction(row["fill_quantity"]) for row in rows), Fraction(0))
        notional = sum((_fraction(row["fill_quantity"]) * _fraction(row["fill_price"]) for row in rows), Fraction(0))
        prices = [_fraction(row["fill_price"]) for row in rows if _fraction(row["fill_quantity"])]
        observed_average = _fraction(order["ticket_average_fill_price"])
        if (len(rows) != _integer(order["ticket_event_count"], MAX_EVENTS)
                or quantity != _fraction(order["ticket_quantity_filled"])
                or abs(quantity) > abs(_fraction(order["quantity"]))
                or quantity * _fraction(order["quantity"]) < 0
                or order["status"] == "Filled" and quantity != _fraction(order["quantity"])
                or (not min(prices) <= observed_average <= max(prices) if quantity else observed_average != 0)
                or rows and rows[-1]["status"] != order["status"]
                or account._clock(order["time_utc"]) > capture
                or any(account._clock(row["utc"]) > capture for row in rows)):
            _fail()
    nonzero = Counter({key: count for key, count in native_events.items() if key[4]})
    census = {"orders": len(orders), "events": counts["events"], "nonzero_fills": counts["nonzero_fills"],
        "absolute_filled_shares": metrics._out(absolute), "reported_fees": metrics._out(fees),
        "currency_fields_complete": all(key[7] == "USD" for key in native_events),
        "currency_inference_performed": False}
    return {"unknown_reasons": Counter(), "native_order_census": census,
        "event_multiset_sha256": _history_fingerprint(native_events), "known_event_count": counts["events"],
        "nonzero_fill_multiset_sha256": _history_fingerprint(nonzero, domain="nonzero"),
        "known_nonzero_fill_count": sum(nonzero.values()),
        "observed_nonzero_fees": metrics._out(sum((key[6] * count for key, count in nonzero.items()), Fraction(0))),
        "zero_fill_skeleton_sha256": account._zero_fingerprint(zero_skeleton),
        "known_zero_fill_skeleton_count": sum(zero_skeleton.values()),
        "ordered_api_envelopes_sha256": None, "api_input_binding_sha256": None}, sessions


def audit_evidence(summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw, *,
        binding, chunks, public_sources, project_bindings_raw, expected_project_bindings_sha256):
    """Actual private processing belongs in QC under a separately claimed wrapper."""
    try:
        expected = _expected(binding, public_sources, project_bindings_raw, expected_project_bindings_sha256)
        return _audit_accounting(summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw,
            binding=binding, chunks=chunks, expected=expected)
    except CompletionRefusal:
        raise
    except Exception:
        _fail()


REPLAY_HELPER = HELPER_PREFIX + "_replay.py"
PRIMITIVES_HELPER = HELPER_PREFIX + "_primitives.py"
METADATA_HELPER = HELPER_PREFIX + "_metadata.py"
PINS = {**cash_bundle.PINS,
    SINGLE_BASE_BUNDLE_MODULE: SINGLE_BASE_BUNDLE_SHA256,
    ACCOUNTING_SOURCE: ACCOUNTING_SOURCE_SHA256,
    COMPLETION_SOURCE: COMPLETION_SOURCE_SHA256,
    PREFIX + "extended_evidence.py": "a816b1ddca5a8428f07e9029bc3a7f7db3c5e1a1f50521664992dabf556aa2d7",
    PREFIX + "extended_metrics.py": "a8cfa235c7a54e8f33366570400dbe1bac0a0e900597e94427e5d0c5b7470414",
    PREFIX + "cap_observer.py": "cad8a3306f6b459bc8bf187c8fd8b8bb980c7b1dc0d85465fba11dd318b70c4d"}
REQUIRED_SOURCES = frozenset(PINS) | {MODULE}
RUNTIME_AST_SHA256 = "49664b7041afaeb416f3dcb35704d07f914838e7a9f6da4af6206a9e84376ff5"
_RUNTIME_ROOTS = frozenset(("_validate_completion", "_chunk_replay_plan",
    "_replay_chunks", "_mask_replay", "_audit_accounting", "_identity", "_native_history"))
_GROUP_PATHS = {"r": MODULE, "e": PREFIX + "extended_evidence.py",
    "m": PREFIX + "extended_metrics.py", "a": ACCOUNTING_SOURCE,
    "p": cash_bundle.RUNTIME_PATH, "v": PREFIX + "cap_observer.py"}
_ALIASES = {"r": {"evidence": "e", "metrics": "m", "account": "a", "mask": "p", "cap_observer": "v"},
    "e": {}, "m": {"e": "e"}, "a": {"c": "r", "e": "e", "metrics": "m"},
    "p": {}, "v": {}}


def _declared(node):
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
        return {node.name}
    if isinstance(node, ast.Assign):
        return {child.id for target in node.targets for child in ast.walk(target) if isinstance(child, ast.Name)}
    return set()


def _runtime_nodes(public_sources):
    """Finite dependency closure over exact fixed public modules only."""
    tables, lists = {}, {}
    for group, path in _GROUP_PATHS.items():
        nodes = [node for node in ast.parse(public_sources[path]).body if _declared(node)]
        if group == "r":
            for number, node in enumerate(nodes):
                if _declared(node) == {"STUDY"}:
                    nodes[number] = ast.Assign(targets=[ast.Name(id="STUDY", ctx=ast.Store())],
                        value=ast.Constant(cash_bundle.STUDY_ID))
        tables[group] = {name: node for node in nodes for name in _declared(node)}
        lists[group] = nodes
    needed = {"r": set(_RUNTIME_ROOTS), **{group: set() for group in tables if group != "r"}}
    while True:
        previous = {group: set(names) for group, names in needed.items()}
        for group, names in previous.items():
            for name in names:
                node = tables[group][name]
                for child in ast.walk(node):
                    if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load) and child.id in tables[group]:
                        needed[group].add(child.id)
                    elif isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name):
                        alias = _ALIASES[group].get(child.value.id)
                        if alias:
                            if child.attr not in tables[alias]:
                                _fail()
                            needed[alias].add(child.attr)
        if needed == previous:
            break
    selected = {group: [node for node in lists[group] if _declared(node) & needed[group]] for group in tables}
    # Every declaration in a multi-name assignment belongs to the closure.
    for group, nodes in selected.items():
        needed[group] = set().union(*(_declared(node) for node in nodes)) if nodes else set()
    return selected, needed


def _semantic_ast(value):
    """Version-independent AST identity; no meaningful field/value is omitted.

    CPython3.13 ast.dump omits empty fields by default, unlike3.9. We encode
    every ordered _fields entry directly. Only the known added type_params
    field is normalized, and only when empty; generic declarations refuse.
    Source positions/other _attributes are non-executable metadata.
    """
    if isinstance(value, ast.AST):
        fields = []
        for name in value._fields:
            child = getattr(value, name, None)
            if name == "type_params":
                if child is not None and (type(child) is not list or child):
                    _fail()
                continue
            fields.append([name, _semantic_ast(child)])
        return {"node": type(value).__name__, "fields": fields}
    if type(value) in (list, tuple):
        return {"sequence": type(value).__name__, "items": [_semantic_ast(child) for child in value]}
    if value is None or type(value) in (str, bool, int):
        return {"type": type(value).__name__, "value": value}
    if type(value) is bytes:
        return {"type": "bytes", "hex": value.hex()}
    if type(value) is float:
        if value != value or value in (float("inf"), float("-inf")):
            _fail()
        return {"type": "float", "hex": value.hex()}
    _fail()


def _runtime_ast_digest(selected):
    material = {group: [_semantic_ast(node) for node in nodes]
        for group, nodes in sorted(selected.items())}
    return _sha(json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii"))


def _render_runtime(selected, needed):
    """Readable namespaced functions; no function is evaluated by this renderer."""
    prefixes = {group: group.upper() + "_" for group in selected}

    class Names(ast.NodeTransformer):
        def __init__(self, group):
            self.group = group
            self.depth = 0

        def visit_Name(self, node):
            if node.id in needed[self.group]:
                node.id = prefixes[self.group] + node.id
            return node

        def visit_FunctionDef(self, node):
            if self.depth == 0:
                node.name = prefixes[self.group] + node.name
            self.depth += 1
            try:
                return self.generic_visit(node)
            finally:
                self.depth -= 1

        def visit_ClassDef(self, node):
            if self.depth == 0:
                node.name = prefixes[self.group] + node.name
            self.depth += 1
            try:
                return self.generic_visit(node)
            finally:
                self.depth -= 1

        def visit_Attribute(self, node):
            if isinstance(node.value, ast.Name) and node.value.id in _ALIASES[self.group]:
                group = _ALIASES[self.group][node.value.id]
                if node.attr not in needed[group]:
                    _fail()
                return ast.copy_location(ast.Name(id=prefixes[group] + node.attr, ctx=node.ctx), node)
            return self.generic_visit(node)

    # Non-result primitives can reference result number/schema helpers. Put
    # their entire transitive result dependency closure in the primitives file
    # to prevent an import cycle; result replay imports that completed module.
    foundation = set()
    for group, nodes in selected.items():
        if group == "r":
            continue
        for node in nodes:
            for child in ast.walk(node):
                if (isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name)
                        and _ALIASES[group].get(child.value.id) == "r"):
                    foundation.add(child.attr)
    result_table = {name: node for node in selected["r"] for name in _declared(node)}
    while True:
        old = set(foundation)
        for name in old:
            node = result_table[name]
            foundation |= {child.id for child in ast.walk(node)
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load) and child.id in result_table}
        if foundation == old:
            break
    primitives, replay = [], []
    for group, nodes in selected.items():
        for original in nodes:
            node = Names(group).visit(deepcopy(original))
            destination = replay if group == "r" and not (_declared(original) & foundation) else primitives
            destination.append(node)
    header = """from __future__ import annotations
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Context, Decimal, InvalidOperation, localcontext
from fractions import Fraction
import hashlib
import json
import math
import re
from zoneinfo import ZoneInfo
"""
    # Docstrings change no executable AST; ordinary source remains readable.
    class Documentation(ast.NodeTransformer):
        def generic_visit(self, node):
            node = super().generic_visit(node)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)) and node.body:
                first = node.body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and type(first.value.value) is str:
                    node.body.pop(0)
                    if not node.body:
                        node.body = [ast.Pass()]
            return node
    def body(nodes):
        tree = ast.Module(body=nodes, type_ignores=[])
        tree = Documentation().visit(tree)
        ast.fix_missing_locations(tree)
        return ast.unparse(tree) + "\n"
    return header + body(primitives), header + "from " + PRIMITIVES_HELPER[:-3] + " import *\n" + body(replay)


def build_runtime_helpers(*, public_sources, project_bindings_raw,
        expected_project_bindings_sha256, financial_spec, parent_job_id,
        terminal_evidence_sha256):
    """Fixed readable helper files only; no native custody or processing authority.

    The external wrapper must bind these exact bytes to committed source and
    actual terminal evidence, claim all private reads/processes before effects,
    and retain every journal/native identity inside QC. This pure renderer
    accepts no caller-selected policy, exclusion, expected context or code.
    """
    try:
        if type(public_sources) is not dict or set(public_sources) != REQUIRED_SOURCES:
            _fail()
        for path, pin in PINS.items():
            raw = public_sources[path]
            if type(raw) is not bytes or not 0 < len(raw) <= 131072 or _sha(raw) != pin:
                _fail()
        raw = public_sources[MODULE]
        if type(raw) is not bytes or not 0 < len(raw) <= 131072:
            _fail()
        selected, needed = _runtime_nodes(public_sources)
        if _runtime_ast_digest(selected) != RUNTIME_AST_SHA256:
            _fail()
        _closed(financial_spec, ("arm", "operation_id", "attempt",
            "prior_attempts_looks_sha256", "latest_owner_instruction_sha256"))
        if (financial_spec["latest_owner_instruction_sha256"] != cash_bundle.OWNER_SHA256
                or type(parent_job_id) is not str or re.fullmatch("[0-9a-f]{32}", parent_job_id) is None):
            _fail()
        _hash(terminal_evidence_sha256)
        stub = {**financial_spec}
        expected = _expected(stub, {name: public_sources[name] for name in cash_bundle.REQUIRED_SOURCES},
            project_bindings_raw, expected_project_bindings_sha256)
        expected.update(job_id=parent_job_id, terminal_evidence_sha256=terminal_evidence_sha256)
        files, _ = cash_bundle.build_cash_candidate(
            public_sources={name: public_sources[name] for name in cash_bundle.REQUIRED_SOURCES},
            project_bindings_raw=project_bindings_raw,
            expected_project_bindings_sha256=expected_project_bindings_sha256,
            **financial_spec)
        config_raw = cash_bundle._wire(cash_bundle.preflight._config(files["comparison_20261028_config.py"]))
        source_raw = public_sources[PREFIX + "extended_calendar.json"]
        calendar = cash_bundle.bundle.off._calendar(source_raw, expected["policy_sha256"])
        calendar["study_id"] = STUDY
        calendar_raw = cash_bundle._wire(calendar)
        primitives, replay = _render_runtime(selected, needed)
        bridge = '''
from tpr_sid_cash_results_20261107_metadata import CONFIG_RAW, CALENDAR_RAW, SOURCE_CALENDAR_RAW, EXPECTED_CONTEXT

def get_public_envelopes():
    return CONFIG_RAW, CALENDAR_RAW, SOURCE_CALENDAR_RAW

def canonical_summary(row):
    return E_canonical(row)[:-1]

def make_binding(summary_raw, index_raw):
    bodies = {"summary": summary_raw, "index": index_raw, "config": CONFIG_RAW,
        "calendar": CALENDAR_RAW, "source_calendar": SOURCE_CALENDAR_RAW}
    binding = {**EXPECTED_CONTEXT, "schema": R_RESULT_SCHEMA, "terminal_status": "Completed",
        "envelopes": {key: {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
            for key, value in bodies.items()}}
    R__validate(bodies, binding, EXPECTED_CONTEXT)
    return binding

def validate_completion(summary, index, config, calendar, source, *, binding):
    return R__validate_completion(summary, index, config, calendar, source, binding=binding, expected=EXPECTED_CONTEXT)

def chunk_replay_plan(summary, index, config, calendar, source, *, binding):
    return R__chunk_replay_plan(summary, index, config, calendar, source, binding=binding, expected=EXPECTED_CONTEXT)

def replay_chunks(summary, index, config, calendar, source, *, binding, chunks):
    report = R__replay_chunks(summary, index, config, calendar, source, binding=binding, chunks=chunks, expected=EXPECTED_CONTEXT)
    report.update(R__mask_replay(chunks, source, binding))
    return report

def audit_evidence(summary, index, config, calendar, source, *, binding, chunks):
    return R__audit_accounting(summary, index, config, calendar, source, binding=binding, chunks=chunks, expected=EXPECTED_CONTEXT)
'''
        public_calendar = {"schema": "tpr-cmp28-calendar-candidate-v1", "study_id": STUDY,
            "policy_sha256": expected["policy_sha256"], "source_calendar_sha256": metrics.CALENDAR_SHA256,
            "timezone": "America/New_York", "start": "2021-01-04", "end": "2026-10-09",
            "warmup_start": "2020-09-01", "valuation_count": 1449, "decision_count": 301,
            "no_market_outcomes": True}
        metadata = ("import json\nCONFIG_RAW = " + repr(config_raw)
            + "\nSOURCE_CALENDAR_RAW = " + repr(source_raw)
            + "\nEXPECTED_CONTEXT = " + repr(expected)
            + "\n_public = json.loads(SOURCE_CALENDAR_RAW)\n_calendar = " + repr(public_calendar)
            + "\n_calendar.update({key: _public[key] for key in ('valuation_sessions', 'warmup_sessions', 'decisions')})"
            + "\nCALENDAR_RAW = json.dumps(_calendar, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')\n")
        output = {PRIMITIVES_HELPER: primitives.encode("utf-8"),
            REPLAY_HELPER: (replay + bridge).encode("utf-8"), METADATA_HELPER: metadata.encode("utf-8")}
        for name, body in output.items():
            if not 0 < len(body) <= 60000:
                _fail()
            tree = ast.parse(body, filename=name)
            if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in ("exec", "eval", "compile", "open", "__import__") for node in ast.walk(tree)):
                _fail()
        report = {"schema": "tpr-sid-cash-fixed-result-helpers-v1", "study_id": STUDY,
            "source_epoch": SOURCE_EPOCH,
            "parent_job_id": parent_job_id, "project_id": expected["project_id"],
            "parent_config_sha256": expected["config_sha256"],
            "terminal_evidence_sha256": terminal_evidence_sha256,
            "runtime_ast_sha256": RUNTIME_AST_SHA256,
            "source_hashes": {name: _sha(value) for name, value in sorted(public_sources.items())},
            "files": {name: {"bytes": len(value), "sha256": _sha(value)} for name, value in output.items()},
            "helper_files": 3, "native_effects": 0, "private_reads": 0,
            "external_committed_source_and_terminal_custody_required": True,
            "private_journal_and_native_identities_must_remain_in_qc": True,
            "independent_native_ticket_history_required": True, "engine_chart_agreement_pending": True,
            "native_origin_authenticated": False, "source_inputs_admitted": False,
            "data_rights_authenticated": False, "historical_pit_authenticated": False,
            "strategy_accepted": False, "canonical_admission": False, "accepted_performance": None}
        return output, json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii") + b"\n"
    except CompletionRefusal:
        raise
    except Exception:
        _fail()


def _history_fingerprint(events, *, domain="all"):
    """Typed canonical sort preserves native None/empty/NullCurrency distinctions."""
    if (domain not in ("all", "nonzero") or type(events) is not Counter
            or len(events) > MAX_EVENTS or sum(events.values()) > MAX_EVENTS):
        _fail()
    digest = hashlib.sha256(("tpr-sid-cash-" + domain + "-event-multiset-v1\n").encode("ascii"))
    rows = []
    for (oid, sid, instant, status, quantity, price, fee, currency), count in events.items():
        rows.append(evidence.canonical({"order_id": oid, "security_id": sid, "utc": instant.isoformat(),
            "status": status, "quantity": metrics._out(quantity), "price": metrics._out(price),
            "fee": metrics._out(fee), "fee_currency": currency, "multiplicity": _integer(count, MAX_EVENTS, 1)}))
    for row in sorted(rows):
        digest.update(row)
    return digest.hexdigest()
