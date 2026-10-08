"""Exact public operation metadata only; never discover/open private captures."""
import copy
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import stat

import pytest

from research.target_price_revisions_development import raw_run
from research.target_price_revisions_development import raw_source_capture as massive
from research.target_price_revisions_development import raw_sharadar_source as sharadar
from research.target_price_revisions_development import raw_sharadar_continue as continuation
from research.target_price_revisions_development import raw_candidate

PACKAGE = Path(__file__).resolve().parents[2] / "research/target_price_revisions_development"
PUBLIC = PACKAGE / "artifacts"
ARTIFACTS = {
    "waiver": "tpr-raw-owner-waiver.b813b8524890088479398a6d3c22b95d30831a08042a3ff063620fc38a32d9d3.json",
    "massive_plan": "tpr-raw-massive-source-plan.e204db30fa13fba63605820bc6e40ea66345a01db4977825905b7193ab4e3058.json",
    "massive_report": "tpr-raw-massive-source-report.1559e8c587cb1c04b3dda629b719b353ee2cf8c1e6cdc33eedd5e12256fd03b9.json",
    "sharadar_plan": "tpr-raw-sharadar-source-plan.f60affc655e237793f3f84ff33ade6f5ea263257e7feb101ba027e8246e696fa.json",
    "sharadar_report": "tpr-raw-sharadar-source-report.0530b12a24f61d4602c55d7f2f9468e57c5617624a618dab37bfea2c06b9ba0e.json",
    "continuation_plan": "tpr-raw-sharadar-continuation-plan.b21cde993fb2497e9729e1dc23d4b3719fcf169ffb308788723f949a7a7d2b41.json",
    "continuation_report": "tpr-raw-sharadar-continuation-report.3740fbe451754086736e397b0e0701d8cd73d2ead8ba0d31ebcae702e79cc115.json",
    "preparation": "tpr-raw-source-preparation.6f0e68fafcbc2d82fcb67e8f7ec704334846929b0e21c5ad25c0d487875fbee7.json",
    "market_plan": "tpr-raw-market-plan-summary.bcbb908c3cc5212931cb41402b56c15679e0441d55757e8b3c3bd890b5674750.json",
    "market_report": "tpr-raw-market-capture-report.491064c4da6ea38d194a3edac2e482d9b9bfd14657db1ca66ef5a643036e03d1.json",
    "diagnostic_plan": "tpr-raw-market-diagnostic-plan.235208047c8e23d107378744887198ddc7f60a0997c33a93840c80fc41e8bdc0.json",
    "diagnostic_report": "tpr-raw-market-diagnostic-report.0e4d4164e6df1c888dad48df02aea955f24e11f1d928e48e51b8cf5edc02bdc8.json",
}
HELPER_SHA = "9f2674a47d0d62bb09e2dd5ba1ce7f37eed3c68dce254e40e0d11d1218f46960"
OWNER_SHA = "e24fb532aea2497759f50f050c5f2653afd8d5f788cf084b68aaee378fb92508"
CODE_SHA = {"raw_source_capture.py": "95cc73d82388fcdc33c217f381877a681f19b09e1e031ce7dd1184929a3dad39",
    "raw_sharadar_source.py": "7487a0990c4d3f80d4230c7f0bc03a471579620a3bc6ea25be7951d7c47dcb03",
    "raw_sharadar_continue.py": "a6d521f6f3eb24ce99765556f691a3e0d76ab848987859f0070d0d39bc70a590"}
MARKET_CODE_SHA = {
    "raw_backtest.py": "628fd39fc467707aee3b998ec491fb66ffe59a71df7a07c65593126617aeb93f",
    "raw_candidate.py": "6232723188bedfbce5ba88ceccd460c1ce1011bffad5338e87b59b648458a6c0",
    "raw_market_capture.py": "953b427aa84d0ae8cdb774a09fe96c1acec259cf61d1049dc83deab38fda0f42",
    "raw_market_inputs.py": "6e15da5b61c757edca94ae8f033e65b35b2bf6eb91b3ecab73a73b29e485a2be",
    "raw_revision.py": "ea4efcd9b0e73ae0b5c166d820c51e054559a3ed610041a6eb2acc8abca36353",
    "raw_run.py": "fe00c1ebcda0edb9e69ec7079f648ff060e101a2d18d10c94aa1e9fbc8bd7260",
    "raw_source_prepare.py": "013433fa4baabffd37582e8a9fdcd99d99a5554c1ab953a58760d52419d41e81"}
STRUCTURE_SHA = "509047244d47ec489e5a8e1dfbf74e0d0104b51c7dfff19ae7283abba1e9ccd5"
MARKET_PLAN_SHA = "3a215f293cae4ad9c150e2bd0ff4d63b6d6cf970c6af7ea2bcf7b9ed2b58c76c"
DIAGNOSTIC_CODE_SHA = "3a4408ecaa89afb56eceadaf93763ee249c3d29871e752e422454a0a492f0a36"


def _canonical(body):
    return (json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def _unique(pairs):
    body = {}
    for key, value in pairs:
        if key in body:
            raise AssertionError("duplicate public metadata key")
        body[key] = value
    return body


def _load(label):
    # Deliberately no glob, recursive discovery or private-path opener.
    path = PUBLIC / ARTIFACTS[label]
    if not stat.S_ISREG(path.lstat().st_mode) or path.resolve().parent != PUBLIC or path.stat().st_size > 16384:
        raise AssertionError("public metadata custody or size changed")
    payload = path.read_bytes()
    digest = path.name.rsplit(".", 2)[1]
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None or hashlib.sha256(payload).hexdigest() != digest:
        raise AssertionError("public artifact filename identity mismatch")
    body = json.loads(payload.decode("ascii"), object_pairs_hook=_unique)
    if type(body) is not dict or _canonical(body) != payload:
        raise AssertionError("noncanonical public metadata")
    return body, payload, digest


def _counts(body, keys):
    if type(body) is not dict or set(body) != set(keys):
        raise AssertionError("unexpected aggregate counter fields")
    if any(type(value) is not int or not 0 <= value <= 100000000 for value in body.values()):
        raise AssertionError("invalid aggregate counter primitive")


def _false(body, *keys):
    if any(body[key] is not False for key in keys):
        raise AssertionError("public source evidence escalated authority")


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise AssertionError("invalid public identity primitive")


PREPARATION_KEYS = {"schema", "actions_retained", "calendar_sessions", "calendar_sha256", "calendar_source",
    "canonical_admission", "current_snapshot_survivorship_bias_possible", "development_looks", "earliest_market_date",
    "global_source_completeness_proven", "historical_cross_provider_identity_proven", "input_ratings",
    "invalid_or_outside_source_date", "matched_identity_rows", "outcome_reads", "point_in_time_data", "positive_frames",
    "proposed_securities", "quantconnect_attempts", "rating_tickers", "real_backtest_ready", "retained_ratings",
    "source_inventory_basis", "structure_sha256", "target_frames", "trading"}
MARKET_PLAN_KEYS = {"schema", "action_dates", "candidate_id", "candidate_policy_sha256", "canonical_admission",
    "capture_id", "code_hashes", "created_utc", "empirical_looks", "expires_utc", "git_sha", "limits",
    "market_plan_sha256", "mode", "native_ticker_list_published", "owner_instruction_sha256", "price_dates",
    "quantconnect", "rights_verified", "structure_sha256", "ticker_count", "trading", "waiver_sha256"}
MARKET_LIMITS = {"bytes_per_page": 4194304, "pages_per_dataset": 5, "redirects": 0, "request_seconds": 30,
    "requests": 10, "retries": 0, "rows_per_page": 10000, "tickers": 200, "total_bytes": 33554432}
MARKET_REPORT_KEYS = {"schema", "capture_id", "candidate_id", "market_plan_sha256", "mode", "status", "failure",
    "failure_stage", "last_http_status", "native_source_row_counts", "unique_row_counts", "exact_duplicate_rows",
    "page_counts", "response_bytes", "projection_sha256", "provider_requests", "fixture_transport_calls",
    "development_look_spent", "fixture_runs", "backtest_completed", "real_backtest_ready",
    "outcome_access_before_reservation", "rights_verified", "transactional_snapshot", "canonical_admission",
    "quantconnect_attempts", "trading"}
DIAGNOSTIC_PLAN_KEYS = {"schema", "additional_development_looks", "code_sha256", "created_utc", "diagnostic_id",
    "error_bytes", "expires_utc", "failed_capture_report_sha256", "git_sha", "lane_branch", "lane_root",
    "market_plan_sha256", "mode", "outcomes", "owner_decision", "owner_instruction_sha256", "private_root",
    "quantconnect", "raw_error_identity_retention", "raw_error_retention", "redirects", "request", "request_seconds",
    "requests", "retries", "successful_body_reads", "trading"}
DIAGNOSTIC_REPORT_KEYS = {"schema", "additional_development_looks", "diagnostic_id", "error", "error_response_bytes",
    "existing_development_look_spent", "failed_capture_report_sha256", "failure_stage", "fixture_transport_calls",
    "http_status", "market_plan_sha256", "mode", "outcome_reads", "plan_sha256", "provider_requests",
    "quantconnect_attempts", "raw_error_identity_retained", "raw_error_retained", "status", "successful_body_reads", "trading"}


def _validate_preparation(body):
    if set(body) != PREPARATION_KEYS:
        raise AssertionError("unexpected preparation fields; native payload is forbidden")
    assert body["schema"] == "tpr-raw-source-preparation-v1"
    _false(body, "canonical_admission", "global_source_completeness_proven", "historical_cross_provider_identity_proven",
        "point_in_time_data", "real_backtest_ready", "trading")
    for field in ("development_looks", "outcome_reads", "quantconnect_attempts"):
        assert type(body[field]) is int and body[field] == 0
    counters = ("actions_retained", "calendar_sessions", "input_ratings", "invalid_or_outside_source_date",
        "matched_identity_rows", "positive_frames", "proposed_securities", "rating_tickers", "retained_ratings", "target_frames")
    _counts({key: body[key] for key in counters}, counters)
    assert body["current_snapshot_survivorship_bias_possible"] is True
    assert body["calendar_source"] == "exchange_calendars-4.13.2-XNYS"
    assert body["source_inventory_basis"] == "terminated-bounded-current-snapshot-pagination"
    assert body["earliest_market_date"] == "2024-12-31"
    assert body["calendar_sha256"] == "fe5444281ec3d4715ae711ab368757e46fc474b5680cdb406e00a7410a127eae"
    assert body["structure_sha256"] == STRUCTURE_SHA
    assert body["retained_ratings"] == body["input_ratings"] - body["invalid_or_outside_source_date"]
    assert 0 < body["positive_frames"] <= body["target_frames"] <= body["calendar_sessions"]
    assert 0 < body["proposed_securities"] <= body["matched_identity_rows"] <= body["rating_tickers"]


def _validate_market_plan(body):
    if set(body) != MARKET_PLAN_KEYS:
        raise AssertionError("unexpected market plan fields; native payload is forbidden")
    assert body["schema"] == "tpr-raw-market-plan-summary-v1"
    assert body["candidate_id"] == "TPR-DEV-RAWREV-v1" and body["capture_id"] == "TPR-RAWREV-MARKET-20261007-001"
    assert body["mode"] == "production"
    _false(body, "canonical_admission", "quantconnect", "rights_verified", "trading", "native_ticker_list_published")
    assert type(body["empirical_looks"]) is int and body["empirical_looks"] == 1
    assert type(body["ticker_count"]) is int and body["ticker_count"] == 43
    assert body["price_dates"] == {"from": "2024-12-31", "to": "2025-03-31"}
    assert body["action_dates"] == {"from": "2025-01-02", "to": "2025-03-31"}
    _counts(body["limits"], MARKET_LIMITS)
    assert body["limits"] == MARKET_LIMITS
    assert body["code_hashes"] == MARKET_CODE_SHA
    for field in ("market_plan_sha256", "structure_sha256", "waiver_sha256", "candidate_policy_sha256", "owner_instruction_sha256"):
        _hash(body[field])
    assert body["market_plan_sha256"] == MARKET_PLAN_SHA and body["structure_sha256"] == STRUCTURE_SHA
    assert body["owner_instruction_sha256"] == OWNER_SHA
    assert body["git_sha"] == "331cfbb4183e56318a5c1e2b72f1f226c2ae4068"
    created, expires = datetime.fromisoformat(body["created_utc"]), datetime.fromisoformat(body["expires_utc"])
    assert created.utcoffset() == expires.utcoffset() == timedelta(0)
    assert expires - created == timedelta(hours=24)


def _validate_market_report(body):
    if set(body) != MARKET_REPORT_KEYS:
        raise AssertionError("unexpected market report fields; native payload is forbidden")
    assert body["schema"] == "tpr-raw-market-capture-report-v1"
    assert body["candidate_id"] == "TPR-DEV-RAWREV-v1" and body["capture_id"] == "TPR-RAWREV-MARKET-20261007-001"
    assert body["market_plan_sha256"] == MARKET_PLAN_SHA and body["mode"] == "production"
    _false(body, "backtest_completed", "real_backtest_ready", "outcome_access_before_reservation", "rights_verified",
        "transactional_snapshot", "canonical_admission", "trading")
    for field in ("fixture_transport_calls", "fixture_runs", "quantconnect_attempts"):
        assert type(body[field]) is int and body[field] == 0
    for field in ("development_look_spent", "provider_requests"):
        assert type(body[field]) is int and body[field] == 1
    for field in ("native_source_row_counts", "unique_row_counts", "exact_duplicate_rows", "page_counts"):
        _counts(body[field], ("stocks", "actions"))
        assert body[field] == {"stocks": 0, "actions": 0}
    assert type(body["response_bytes"]) is int and body["response_bytes"] == 0
    assert body["projection_sha256"] is None
    assert type(body["last_http_status"]) is int and body["last_http_status"] == 400
    assert body["status"] == "FAILED" and body["failure_stage"] == "response"
    assert body["failure"] == "market_capture_failed"


def _validate_diagnostic_report(body):
    if set(body) != DIAGNOSTIC_REPORT_KEYS:
        raise AssertionError("unexpected diagnostic report fields; raw error is forbidden")
    assert body["schema"] == "tpr-raw-market-diagnostic-report-v1"
    assert body["diagnostic_id"] == "TPR-RAWREV-MARKET-DIAGNOSTIC-20261007-001"
    assert body["mode"] == "production" and body["status"] == "DIAGNOSED" and body["failure_stage"] is None
    assert body["error"] == {"category": "unknown_response", "error_code": None, "parameter_names": []}
    _false(body, "raw_error_identity_retained", "raw_error_retained", "trading")
    counters = {"additional_development_looks": 0, "error_response_bytes": 181, "existing_development_look_spent": 1,
        "fixture_transport_calls": 0, "http_status": 400, "outcome_reads": 0, "provider_requests": 1,
        "quantconnect_attempts": 0, "successful_body_reads": 0}
    _counts({key: body[key] for key in counters}, counters)
    assert all(body[key] == value for key, value in counters.items())
    assert body["market_plan_sha256"] == MARKET_PLAN_SHA
    assert body["failed_capture_report_sha256"] == _load("market_report")[2]
    assert body["plan_sha256"] == _load("diagnostic_plan")[2]


def _caveats(body):
    if type(body) is not dict or set(body) != {"conflicting_projected_keys", "duplicate_projected_rows",
            "global_source_completeness_proven", "missing_identity_fields", "native_action_key_unique_proven",
            "offset_pagination_stability_proven", "rows_deduplicated"}:
        raise AssertionError("unexpected source caveat fields")
    _counts(body["conflicting_projected_keys"], ("tickers", "actions"))
    _counts(body["duplicate_projected_rows"], ("tickers", "actions"))
    _counts(body["missing_identity_fields"], ("figi", "category", "exchange"))
    _false(body, "global_source_completeness_proven", "native_action_key_unique_proven",
        "offset_pagination_stability_proven", "rows_deduplicated")


MASSIVE_REPORT_KEYS = {"schema", "candidate_id", "capture_id", "plan_sha256", "complete", "pages", "rows",
    "response_bytes", "malformed", "positive_raw_pairs", "positive_pairs_touch_by_latest_cutoff",
    "latest_cutoff_utc", "source_blocker", "failure", "transactional_inventory", "rights_verified",
    "point_in_time_data", "outcome_access", "quantconnect_attempts", "trading", "d0_renewed"}
SHARADAR_REPORT_KEYS = {"schema", "capture_id", "status", "failure", "mode", "plan_sha256", "failure_stage",
    "last_http_status", "csv_schema_failures", "source_sha256", "row_counts", "page_counts", "response_bytes",
    "action_kind_counts", "in_window_action_kind_counts", "pagination_terminated", "transactional_snapshot",
    "personal_rights", "point_in_time_identity", "history_versions_complete", "canonical_admission",
    "real_backtest_ready", "outcome_reads", "development_looks", "quantconnect_attempts", "trading",
    "provider_requests", "fixture_transport_calls", "source_caveats"}
CONTINUATION_REPORT_KEYS = {"schema", "capture_id", "mode", "plan_sha256", "status", "failure", "failure_stage",
    "last_http_status", "first_page_reused", "first_page_refetches", "source_sha256", "source_row_counts",
    "admitted_row_counts", "row_refusal_counts", "missing_optional_column_pages", "page_counts",
    "response_bytes_including_parent", "action_kind_counts", "in_window_action_kind_counts", "pagination_terminated",
    "source_caveats", "rights", "canonical_admission", "real_backtest_ready", "historical_cross_provider_identity_proven",
    "outcome_reads", "development_looks", "quantconnect_attempts", "trading", "provider_requests", "fixture_transport_calls"}


def _validate_report(label, report):
    expected = {"massive_report": MASSIVE_REPORT_KEYS, "sharadar_report": SHARADAR_REPORT_KEYS,
        "continuation_report": CONTINUATION_REPORT_KEYS}[label]
    if set(report) != expected:
        raise AssertionError("unexpected public report fields; native payload is forbidden")
    if label == "massive_report":
        _false(report, "transactional_inventory", "rights_verified", "point_in_time_data", "outcome_access", "trading", "d0_renewed")
        numeric = ("pages", "rows", "response_bytes", "malformed", "positive_raw_pairs", "positive_pairs_touch_by_latest_cutoff", "quantconnect_attempts")
    else:
        _false(report, "canonical_admission", "real_backtest_ready", "trading")
        if report["mode"] != "production":
            raise AssertionError("actual source report mislabeled fixture")
        for field in ("outcome_reads", "development_looks", "quantconnect_attempts", "fixture_transport_calls"):
            if type(report[field]) is not int or report[field] != 0:
                raise AssertionError("source operation claimed an outcome or fixture look")
        for field in ("action_kind_counts", "in_window_action_kind_counts"):
            _counts(report[field], sharadar.ACTION_KINDS + ("other",))
        _caveats(report["source_caveats"])
        _counts(report["page_counts"], ("tickers", "actions"))
        if label == "sharadar_report":
            _false(report, "transactional_snapshot", "point_in_time_identity", "history_versions_complete")
            _counts(report["row_counts"], ("tickers", "actions"))
            numeric = ("csv_schema_failures", "response_bytes", "provider_requests")
        else:
            _false(report, "historical_cross_provider_identity_proven")
            for field in ("source_row_counts", "admitted_row_counts", "missing_optional_column_pages"):
                _counts(report[field], ("tickers", "actions"))
            if report["row_refusal_counts"] != {}:
                raise AssertionError("actual refusal census changed")
            numeric = ("first_page_refetches", "response_bytes_including_parent", "provider_requests")
    for field in numeric:
        if type(report[field]) is not int or not 0 <= report[field] <= 100000000:
            raise AssertionError("invalid report numeric primitive")
    if report["quantconnect_attempts"] != 0:
        raise AssertionError("source operation gained QC authority")


@pytest.mark.parametrize("label", tuple(ARTIFACTS))
def test_exact_public_artifact_is_canonical_and_content_addressed(label):
    _load(label)


@pytest.mark.parametrize("label,module", [("massive_plan", massive), ("sharadar_plan", sharadar),
    ("continuation_plan", continuation)])
def test_plans_reproduce_exact_fixed_policy_and_executed_bytes(label, module):
    body, payload, digest = _load(label)
    assert module.CapturePlan(payload, digest).body() == body
    assert body["owner_instruction_sha256"] == OWNER_SHA
    assert body["helper_sha256"] == HELPER_SHA
    assert body["git_sha"] == "331cfbb4183e56318a5c1e2b72f1f226c2ae4068"
    assert body["lane_branch"] == "codex/strategy-target-price-revisions"
    path = PACKAGE / module.__name__.rsplit(".", 1)[1]
    expected = CODE_SHA[path.name + ".py"]
    assert hashlib.sha256(path.with_suffix(".py").read_bytes()).hexdigest() == expected == body["code_sha256"]
    assert hashlib.sha256((PACKAGE / "source_audit.py").read_bytes()).hexdigest() == HELPER_SHA


def test_owner_waiver_is_exact_non_vendor_non_qc_noncanonical_scope():
    body, _, _ = _load("waiver")
    assert raw_run._source_admission(body) == {"basis": "explicit-owner-waiver", "owner_decision": "TPR-OWN-36", "contractual_rights_verified": False}
    assert body["owner_instruction_sha256"] == hashlib.sha256(raw_run.OWNER_WAIVER_INSTRUCTION.encode()).hexdigest() == OWNER_SHA
    assert body["personal_only"] is True
    _false(body, "contractual_rights_verified", "quantconnect", "canonical_admission")


@pytest.mark.parametrize("label", ("massive_report", "sharadar_report", "continuation_report"))
def test_reports_are_closed_aggregate_only_and_bound_to_exact_plan(label):
    report, _, _ = _load(label)
    _validate_report(label, report)
    _, _, plan_hash = _load(label.replace("report", "plan"))
    assert report["plan_sha256"] == plan_hash


def test_actual_source_results_are_not_backtest_completion_or_completeness_proof():
    massive_report = _load("massive_report")[0]
    assert massive_report["schema"] == "tpr-raw-source-feasibility-v1"
    assert massive_report["complete"] is True and massive_report["source_blocker"] is False
    assert (massive_report["pages"], massive_report["rows"], massive_report["positive_pairs_touch_by_latest_cutoff"]) == (48, 47393, 41314)
    refused = _load("sharadar_report")[0]
    assert refused["status"] == "FAILED" and refused["failure_stage"] == "csv_schema"
    assert refused["row_counts"] == {"tickers": 0, "actions": 0}
    assert refused["source_sha256"] is None and refused["provider_requests"] == 1
    assert refused["response_bytes"] == 451759 and refused["pagination_terminated"] is False
    completed = _load("continuation_report")[0]
    assert completed["schema"] == "tpr-sharadar-continuation-report-v1" and completed["status"] == "COMPLETED"
    assert completed["source_row_counts"] == completed["admitted_row_counts"] == {"tickers": 21001, "actions": 27788}
    assert completed["first_page_reused"] is completed["pagination_terminated"] is True
    assert completed["first_page_refetches"] == 0 and completed["provider_requests"] == 5
    assert completed["source_caveats"]["missing_identity_fields"]["figi"] == 21001
    assert completed["source_caveats"]["duplicate_projected_rows"]["actions"] == 12
    assert sum(completed["in_window_action_kind_counts"].values()) > 0
    assert completed["real_backtest_ready"] is False


def test_continuation_parent_pins_and_no_payoff_queries():
    body = _load("continuation_plan")[0]
    assert body["parent_code_sha256"] == CODE_SHA["raw_sharadar_source.py"]
    assert body["first_page_sha256"] == "8efa0c24558feebd4f17ba636c231622e177c53ea1d7389c5f37472158d38372"
    assert body["first_page_bytes"] == 451759
    assert body["limits"]["remaining_requests"] == 19
    assert body["limits"]["total_response_bytes_including_parent"] == 32 * 1024 * 1024
    assert body["queries"]["actions"]["fields"] == "ticker,date,action,contraticker"
    _false(body, "parent_capture_renewed", "action_cash_or_terminal_payoff_fields", "d0_renewed")


def test_public_preparation_is_source_only_and_bound_to_aggregate_source_history():
    body = _load("preparation")[0]
    _validate_preparation(body)
    assert body["input_ratings"] == _load("massive_report")[0]["rows"] == 47393
    assert body["actions_retained"] == _load("continuation_report")[0]["admitted_row_counts"]["actions"] == 27788
    assert (body["calendar_sessions"], body["target_frames"], body["positive_frames"], body["proposed_securities"]) == (166, 14, 14, 43)
    assert (body["matched_identity_rows"], body["rating_tickers"]) == (3798, 4023)


def test_public_market_plan_is_closed_bound_and_fixed_before_one_look():
    body = _load("market_plan")[0]
    _validate_market_plan(body)
    assert body["waiver_sha256"] == _load("waiver")[2]
    assert body["structure_sha256"] == _load("preparation")[0]["structure_sha256"]
    assert body["ticker_count"] == _load("preparation")[0]["proposed_securities"]
    assert body["candidate_policy_sha256"] == hashlib.sha256(_canonical(raw_candidate.policy())).hexdigest()


@pytest.mark.parametrize("filename", tuple(MARKET_CODE_SHA))
def test_all_seven_frozen_market_execution_modules_match_exact_public_pins(filename):
    path = PACKAGE / filename
    assert stat.S_ISREG(path.lstat().st_mode) and path.resolve().parent == PACKAGE
    assert path.stat().st_size <= 128 * 1024
    assert hashlib.sha256(path.read_bytes()).hexdigest() == MARKET_CODE_SHA[filename]
    assert _load("market_plan")[0]["code_hashes"][filename] == MARKET_CODE_SHA[filename]


def test_actual_market_http_failure_spends_only_reserved_look_and_is_not_simulation():
    body = _load("market_report")[0]
    _validate_market_report(body)
    assert body["market_plan_sha256"] == _load("market_plan")[0]["market_plan_sha256"]
    # The absence of admitted market rows is not a zero-return simulation and
    # does not refund this spent reservation. Never inspect private custody.
    assert body["development_look_spent"] == _load("market_plan")[0]["empirical_looks"] == 1
    assert "summary" not in body and "private_report_sha256" not in body


def test_diagnostic_plan_is_one_exact_error_only_request_with_frozen_code():
    body = _load("diagnostic_plan")[0]
    assert set(body) == DIAGNOSTIC_PLAN_KEYS
    assert body["schema"] == "tpr-raw-market-diagnostic-plan-v1"
    assert body["diagnostic_id"] == "TPR-RAWREV-MARKET-DIAGNOSTIC-20261007-001"
    assert body["mode"] == "production" and body["owner_decision"] == "TPR-OWN-43"
    assert body["owner_instruction_sha256"] == OWNER_SHA
    assert body["market_plan_sha256"] == MARKET_PLAN_SHA
    assert body["failed_capture_report_sha256"] == _load("market_report")[2]
    assert body["request"] == "exact-original-stocks-page-zero"
    assert body["lane_branch"] == "codex/strategy-target-price-revisions"
    assert body["lane_root"] == "/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__target_price_revisions"
    # Check literal metadata only; never resolve or read the private root.
    assert body["private_root"] == body["lane_root"] + "/artifacts/target_price_raw_revision/TPR-DEV-RAWREV-v1"
    assert body["git_sha"] == _load("market_plan")[0]["git_sha"]
    _false(body, "outcomes", "quantconnect", "raw_error_identity_retention", "raw_error_retention", "trading")
    limits = {"additional_development_looks": 0, "error_bytes": 8192, "redirects": 0, "request_seconds": 30,
        "requests": 1, "retries": 0, "successful_body_reads": 0}
    _counts({key: body[key] for key in limits}, limits)
    assert all(body[key] == value for key, value in limits.items())
    created, expires = datetime.fromisoformat(body["created_utc"]), datetime.fromisoformat(body["expires_utc"])
    assert created.utcoffset() == expires.utcoffset() == timedelta(0)
    assert expires - created == timedelta(hours=12)
    path = PACKAGE / "raw_market_diagnostic.py"
    assert stat.S_ISREG(path.lstat().st_mode) and path.resolve().parent == PACKAGE
    assert path.stat().st_size <= 128 * 1024
    assert hashlib.sha256(path.read_bytes()).hexdigest() == body["code_sha256"] == DIAGNOSTIC_CODE_SHA


def test_diagnostic_completed_without_root_cause_or_successful_body_or_new_look():
    _validate_diagnostic_report(_load("diagnostic_report")[0])


@pytest.mark.parametrize("mutation", [lambda b: b.update(raw_error="SYNTHETIC_PRIVATE"),
    lambda b: b.update(raw_error_sha256="0" * 64), lambda b: b.update(successful_body_reads=1),
    lambda b: b.update(additional_development_looks=1), lambda b: b.update(outcome_reads=1),
    lambda b: b.update(quantconnect_attempts=1), lambda b: b.update(raw_error_retained=True),
    lambda b: b["error"].update(message="SYNTHETIC_PRIVATE"),
    lambda b: b["error"].update(category="invalid_parameter"),
    lambda b: b["error"].update(parameter_names=["SYNTHETIC_PRIVATE"]),
    lambda b: b.update(backtest_completed=True)])
def test_diagnostic_guard_rejects_error_leaks_and_false_root_cause_or_completion(mutation):
    body = copy.deepcopy(_load("diagnostic_report")[0])
    mutation(body)
    with pytest.raises(AssertionError):
        _validate_diagnostic_report(body)


@pytest.mark.parametrize("label,validator,mutation", [
    ("preparation", _validate_preparation, lambda b: b.update(tickers=["SYNTHETIC_PRIVATE"])),
    ("preparation", _validate_preparation, lambda b: b.update(proposed_securities=True)),
    ("preparation", _validate_preparation, lambda b: b.update(outcome_reads=1)),
    ("preparation", _validate_preparation, lambda b: b.update(real_backtest_ready=True)),
    ("preparation", _validate_preparation, lambda b: b.update(historical_cross_provider_identity_proven=True)),
    ("market_plan", _validate_market_plan, lambda b: b.update(tickers=["SYNTHETIC_PRIVATE"])),
    ("market_plan", _validate_market_plan, lambda b: b.update(native_ticker_list_published=True)),
    ("market_plan", _validate_market_plan, lambda b: b.update(rights_verified=True)),
    ("market_plan", _validate_market_plan, lambda b: b.update(empirical_looks=2)),
    ("market_plan", _validate_market_plan, lambda b: b["code_hashes"].update({"raw_market_inputs.py": "0" * 64})),
    ("market_plan", _validate_market_plan, lambda b: b["limits"].update(retries=1)),
    ("market_plan", _validate_market_plan, lambda b: b["price_dates"].update(to="2025-04-01")),
    ("market_report", _validate_market_report, lambda b: b.update(prices=[{"ticker": "SYNTHETIC_PRIVATE"}])),
    ("market_report", _validate_market_report, lambda b: b.update(development_look_spent=0)),
    ("market_report", _validate_market_report, lambda b: b.update(backtest_completed=True)),
    ("market_report", _validate_market_report, lambda b: b.update(real_backtest_ready=True)),
    ("market_report", _validate_market_report, lambda b: b.update(quantconnect_attempts=1)),
    ("market_report", _validate_market_report, lambda b: b.update(projection_sha256="0" * 64)),
    ("market_report", _validate_market_report, lambda b: b["native_source_row_counts"].update(stocks=True)),
    ("market_report", _validate_market_report, lambda b: b.update(summary={"return_pct": "0"})),
])
def test_preparation_and_market_guards_reject_native_leaks_rewrites_and_authority_escalation(label, validator, mutation):
    body = copy.deepcopy(_load(label)[0])
    mutation(body)
    with pytest.raises(AssertionError):
        validator(body)


@pytest.mark.parametrize("mutation", [lambda b: b.update(ratings=[{"ticker": "SYNTHETIC_PRIVATE"}]),
    lambda b: b.update(outcomes={"cash": "SYNTHETIC_PRIVATE"}),
    lambda b: b.update(real_backtest_ready=True), lambda b: b.update(development_looks=1),
    lambda b: b.update(contractual_rights_verified=True),
    lambda b: b["source_caveats"].update(global_source_completeness_proven=True),
    lambda b: b["action_kind_counts"].update(SYNTHETIC_PRIVATE_ID=1),
    lambda b: b["source_row_counts"].update(tickers=True)])
def test_closed_public_report_guard_rejects_synthetic_leak_and_authority_mutations(mutation):
    body = copy.deepcopy(_load("continuation_report")[0])
    mutation(body)
    with pytest.raises(AssertionError):
        _validate_report("continuation_report", body)
