"""Pure CMP28 completion framing and bounded supplied-journal replay.

There is no I/O, native import, retrieval callback, permission or trading effect.
Caller-supplied bytes/hashes describe a snapshot, not native authenticity,
backend durability, data rights or PIT. A producer's useful-run claim and
reported-NAV metrics remain distinct from independent account reconciliation.
The explicit chunk plan contains private object keys; keep it in the private
claim workflow. Reports contain only status, hashes, counts and aggregates.
"""
from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import re

from . import cap_observer
from . import comparison_20261028 as comparison
from . import extended_evidence as evidence
from . import extended_metrics as metrics

STUDY = comparison.STUDY_ID
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
    raise CompletionRefusal("CMP28 supplied completion evidence refused") from None


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
    return {"schema": "tpr-cmp28-completion-framing-report-v1", "study_id": STUDY,
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


def _validate(raws, binding):
    _closed(binding, BINDING_KEYS)
    if (binding["schema"] != "tpr-cmp28-completion-binding-v1" or binding["study_id"] != STUDY
            or type(binding["arm"]) is not str or binding["arm"] not in CANDIDATES
            or binding["candidate_id"] != CANDIDATES[binding["arm"]]
            or type(binding["project_id"]) is not int or binding["project_id"] not in (37650980, 37650453)
            or (binding["arm"] == "cap_off" and binding["project_id"] != 37650980)
            or type(binding["job_id"]) is not str or re.fullmatch(r"[0-9a-f]{32}", binding["job_id"]) is None
            or type(binding["operation_id"]) is not str
            or re.fullmatch(r"TPR-CMP28-[A-Za-z0-9_.-]{1,150}", binding["operation_id"]) is None
            or binding["terminal_status"] != "Completed"):
        _fail()
    if type(binding["attempt"]) is not int:
        _fail()
    _integer(binding["attempt"], 2**31 - 1, 1)
    for key in ("terminal_evidence_sha256", "config_sha256", "policy_sha256", "calendar_sha256",
                "source_template_closure_sha256", "prior_attempts_looks_sha256", "rendered_source_closure_sha256"):
        _hash(binding[key])
    template = _sources(binding["template_source_hashes"], template=True)
    rendered = _sources(binding["rendered_source_hashes"], template=False)
    if (binding["source_template_closure_sha256"] != _sha(_native_wire(
            {"schema": "tpr-cmp28-public-template-closure-v1", "source_hashes": template}))
            or binding["rendered_source_closure_sha256"] != _sha(_native_wire(rendered))
            or binding["policy_sha256"] != _sha(comparison.policy_bytes())
            or template.get(PREFIX + "comparison_20261028_policy.json") != binding["policy_sha256"]
            or template.get(PREFIX + "extended_calendar.json") != metrics.CALENDAR_SHA256):
        _fail()
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


def _call(raws, binding):
    try:
        return _validate(raws, binding)
    except CompletionRefusal:
        raise
    except Exception:
        _fail()


def validate_completion(summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw, *, binding):
    """Safe supplied-byte framing report; never a native or retrieval authority."""
    return _call(dict(zip(ENVELOPES, (summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw))), binding)[2]


def chunk_replay_plan(summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw, *, binding):
    """PRIVATE exact-key plan only; caller must reserve each actual retrieval."""
    bodies, _, _ = _call(dict(zip(ENVELOPES, (summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw))), binding)
    return [{"ordinal": number, "key": chunk["key"], "bytes": _integer(chunk["bytes"]), "sha256": chunk["sha256"]}
        for number, chunk in enumerate(bodies["index"]["chunks"])]


def replay_chunks(summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw, *, binding, chunks):
    """Replay supplied bytes only. Independent fills/actions/cash remain pending."""
    try:
        bodies, sessions, report = _call(dict(zip(ENVELOPES, (summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw))), binding)
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
