"""Exact public operation metadata only; never discover/open private captures."""
import copy
from datetime import datetime, timedelta
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
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
from research.target_price_revisions_development import raw_market_request_probe as probe

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
    "detail_plan": "tpr-raw-market-error-detail-plan.a0aad1a15337e3ad13117890abb27a0bccf6f50905e57c2d05537a4e97e35c27.json",
    "detail_report": "tpr-raw-market-error-detail-report.fd3f3699c653dadc754f585100332e5e639c9271b2f987d5802719493aadc063.json",
    "probe_plan": "tpr-raw-market-request-probe-plan.1cfa0d7909de07fff0de7c54a6af70294029650b13b8289f6b82f52a31259996.json",
    "probe_report": "tpr-raw-market-request-probe-report.ad8382777e8821a2b094ccc48dfa0f17e33e18046bbc65d8340b130248e3133d.json",
    "resume_plan": "tpr-raw-market-resume-plan-summary.a6a0073ed13d6eec6908da2bdf744d185587db6a18d45c6748582548355ecfb8.json",
    "resume_capture": "tpr-raw-market-resume-capture-report.725a9ed6aaebf7f230147faf4fe301f9705f0874c55aaade26337e26b7fb18a3.json",
    "resume_simulation": "tpr-raw-resume-simulation-report.68518f0438ff8f14a3d63fcdbaf890018c5213dc6978fa2c732cc2bcbd186877.json",
    "existing_audit": "tpr-raw-existing-result-audit.8a06bbc8a5f76aac641b07cf8ec9ed35d6bb5affc9d47416e9a3de7e53d0256f.json",
    "correction_plan": "tpr-raw-dividend-correction-plan-summary.9b6f16dc05b5a52c7da1978977eede3ee05aac9f51aaee6187b9fe45e682f882.json",
    "correction_report": "tpr-raw-dividend-correction-report.c72e77aa4b8dd54930bca36bf08251a7be8740c862da97b40bc44e2f6d34fe53.json",
    "corrected_audit": "tpr-raw-corrected-result-audit.d1e38c0f6d002e805140b15f954cfd35ca43d4034ce457b105ad8905ed8d8a06.json",
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
DETAIL_CODE_SHA = "6e2dc2a882368bb9f056f96ae9c31131be4adebe82f175bfe984ad784e039522"
DETAIL_OWNER_SHA = "ccbed6d35074806ca4ac9fe9a6eb6224fc1a5f717a88e3605511ba51152ba782"
PROBE_CODE_SHA = "3b81176c47fd8ce5c6dd4d6c00dac5c23a8396b6d8a08c7b501fc32ab81752fb"
RESUME_CODE_SHA = "0379c5d958f1cc0b75e8b02e807dc1b2e7074a2aafd9b25db8ff32b4594eba0f"
RESUME_PLAN_SHA = "8bb23041fa5809315b158d333c61d94cad37547865a0f4fdc61215f1d41b3422"
RESUME_PROJECTION_SHA = "9db40559cf2d9e400eb8329556fed4cf000edbd24456d6e11037ef7ba29790c4"
RESUME_PRIVATE_REPORT_SHA = "bb8bc27fe7a02d36bccabb4895b72f31843578063bfa62bfe5dba0a15fe9de56"
CORRECTION_CODE_SHA = "9090048cd8f001632441898e552c9d4a636420ef411cdecbd29bb36f4256d54e"
CORRECTION_PLAN_SHA = "5f88c00c8a335567daa12ed3e591501725cca5333f29e07d6e797d8c8dd0769b"
CORRECTION_PRIVATE_RESULT_SHA = "f5edf50e928d3d406ecd7ff2542db9632fd85a4f96468c0147aa9805546f7428"
DIVIDEND_INTERPRETATION = "owner-inference-exact-dividend-N/A-means-no-counterparty-not-universal-vendor-null"


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
DETAIL_PLAN_KEYS = {"schema", "additional_development_looks", "code_sha256", "created_utc", "detail_id", "error_bytes",
    "expires_utc", "failed_capture_report_sha256", "git_sha", "market_plan_sha256", "mode", "outcomes", "owner_decision",
    "owner_instruction_sha256", "prior_code_sha256", "prior_report_sha256", "quantconnect", "raw_error_identity_retention",
    "raw_error_retention", "redirects", "request", "request_seconds", "requests", "retries", "successful_body_reads", "trading"}
DETAIL_REPORT_KEYS = {"schema", "additional_development_looks", "detail_id", "error_detail", "error_response_bytes",
    "existing_development_look_spent", "failure_stage", "fixture_transport_calls", "http_status", "market_plan_sha256",
    "mode", "outcome_reads", "plan_sha256", "prior_report_sha256", "provider_requests", "quantconnect_attempts",
    "raw_error_identity_retained", "raw_error_retained", "status", "successful_body_reads", "trading"}
PROBE_PLAN_KEYS = {"schema", "additional_development_looks", "code_sha256", "created_utc", "detail_code_sha256",
    "detail_report_sha256", "error_bytes_per_request", "expires_utc", "git_sha", "market_plan_sha256", "mode",
    "original_other_query_fields_unchanged", "outcomes", "owner_decision", "owner_instruction_sha256", "probe_id",
    "quantconnect", "raw_error_identity_retention", "raw_error_retention", "redirects", "request_seconds", "requests",
    "retries", "second_variant_only_after_http_400", "successful_body_reads", "trading", "variants"}
PROBE_REPORT_KEYS = {"schema", "additional_development_looks", "detail_report_sha256", "existing_development_look_spent",
    "failure_stage", "fixture_transport_calls", "market_plan_sha256", "maximum_ticker_limit_established", "mode",
    "outcome_reads", "plan_sha256", "probe_id", "provider_requests", "quantconnect_attempts", "raw_error_identity_retained",
    "raw_error_retained", "status", "successful_body_reads", "trading", "variants"}
RESUME_PLAN_KEYS = {"action_dates", "additional_development_looks", "candidate_id", "candidate_policy_sha256",
    "canonical_admission", "code_hashes", "code_sha256", "created_utc", "detail_code_sha256", "detail_report_sha256",
    "entire_original_inventory_required", "expires_utc", "failed_capture_report_sha256", "git_sha", "lane_branch",
    "lane_root", "limits", "mode", "native_ticker_list_published", "original_look_renewed", "original_plan_sha256",
    "original_spent_file", "owner_decision", "owner_instruction_sha256", "price_dates", "probe_code_sha256",
    "probe_report_sha256", "quantconnect", "request_mode", "resume_id", "resume_plan_sha256", "resume_spent_file",
    "rights_verified", "schema", "simulation_spent_file", "structure_sha256", "ticker_count", "ticker_wire_encoding",
    "trading", "waiver_sha256"}
RESUME_CAPTURE_KEYS = {"additional_development_looks", "backtest_completed", "canonical_admission", "exact_duplicate_rows",
    "existing_development_look_spent", "failure", "failure_stage", "fixture_transport_calls", "last_http_status", "mode",
    "native_source_row_counts", "original_plan_sha256", "original_ticker_count", "page_counts", "probe_report_sha256",
    "projection_sha256", "provider_requests", "quantconnect_attempts", "real_backtest_ready", "request_mode", "response_bytes",
    "resume_id", "resume_plan_sha256", "rights_verified", "schema", "status", "trading", "unique_price_ticker_count", "unique_row_counts"}
RESUME_SIMULATION_KEYS = {"additional_development_looks", "canonical_admission", "capture_report_sha256",
    "existing_development_look_spent", "failure", "failure_stage", "mode", "original_plan_sha256", "private_report_sha256",
    "projection_sha256", "quantconnect_attempts", "resume_id", "resume_plan_sha256", "schema", "simulation_runs", "status", "summary", "trading"}
RESUME_SUMMARY_KEYS = {"canonical_admission", "confirmatory_alpha", "corporate_action_accounting_complete", "costs_calibrated",
    "dividend_cash_policy", "engine_complete", "expected_study_sessions", "fills", "final_cash", "final_dividend_receivable",
    "final_nav", "frozen_window_complete", "market_edge_proven", "max_drawdown_pct", "orders", "pending_order_count",
    "pending_quantity", "pending_quantity_scope", "point_in_time_data", "quantconnect_attempts", "return_pct", "study_sessions",
    "summary_rounding", "total_commissions", "total_slippage", "trading", "valuation_complete", "window_end", "window_start"}
EXISTING_AUDIT_KEYS = {"additional_candidate_computations", "additional_development_looks", "all_exclusion_reasons",
    "canonical_readiness", "corporate_action_interpretation_resolved", "counterpart_fixed_sentinel_counts", "engine_complete",
    "existing_result_only", "fill_cost_sums_verified", "max_drawdown_pct", "order_fill_pending_counts_verified",
    "pending_order_reasons", "pending_quantity_by_reason", "private_report_sha256", "provider_requests", "quantconnect_attempts",
    "return_and_drawdown_independently_verified", "return_pct", "schema", "sessions_with_unpriced_positions", "shape_detail",
    "simulation_report_sha256", "trading", "unresolved_action_securities"}
CORRECTION_PLAN_KEYS = {"accounting_interpretation_changed", "action_dates", "additional_development_looks", "base_candidate_id",
    "candidate_policy_sha256", "canonical_admission", "capture_report_sha256", "code_hashes", "code_sha256",
    "contractual_rights_verified", "correction_id", "correction_plan_sha256", "created_utc", "cumulative_development_looks",
    "expires_utc", "first_private_result_sha256", "first_simulation_report_sha256", "git_sha", "interpretation", "lane_branch",
    "lane_root", "mode", "native_action_ids_preserved", "native_ticker_list_published", "original_plan_sha256", "original_spent_file",
    "owner_decision", "owner_instruction_sha256", "price_dates", "prior_look_or_simulation_rearmed", "prior_simulation_spent_file",
    "projection_sha256", "provider_requests", "quantconnect", "reservation_file", "resume_code_sha256", "resume_plan_sha256",
    "schema", "source_refresh", "strategy_policy_unchanged", "structure_sha256", "ticker_count", "trading",
    "universal_vendor_null_semantics_verified", "waiver_sha256"}
CORRECTION_REPORT_KEYS = {"accounting_evidence", "additional_development_looks", "base_candidate_id", "canonical_admission",
    "capture_report_sha256", "contractual_rights_verified", "correction_id", "correction_plan_sha256", "cumulative_development_looks",
    "failure", "failure_stage", "first_private_result_sha256", "first_simulation_report_sha256", "fixture_runs", "interpretation",
    "mode", "owner_decision", "prior_look_or_simulation_rearmed", "private_result_sha256", "projection_sha256", "provider_requests",
    "quantconnect_attempts", "resume_plan_sha256", "schema", "source_refresh", "status", "summary", "trading"}
CORRECTED_AUDIT_KEYS = {"additional_candidate_computations", "additional_development_looks", "all_exclusion_reasons", "canonical_readiness",
    "corporate_action_interpretation_resolved", "corporate_action_status_counts", "cumulative_recorded_development_looks", "engine_complete",
    "existing_result_only", "fill_cost_sums_verified", "first_result_and_projection_hashes_unchanged", "held_corporate_actions",
    "max_drawdown_pct", "native_action_ids_independently_verified", "nonselected_missing_decision_marks", "order_fill_pending_counts_verified",
    "pending_order_reasons", "pending_quantity_by_reason", "positive_target_corporate_action_blocks", "prior_and_new_spent_receipts_verified",
    "private_report_sha256", "provider_requests", "quantconnect_attempts", "return_and_drawdown_independently_verified", "return_pct",
    "schema", "selected_target_missing_decision_marks", "sessions_with_unpriced_positions", "simulation_report_sha256",
    "target_evidence_identical_to_first_result", "trading", "unresolved_action_securities"}


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


def _validate_detail_report(body):
    if set(body) != DETAIL_REPORT_KEYS:
        raise AssertionError("unexpected detail report fields; raw response is forbidden")
    assert body["schema"] == "tpr-raw-market-error-detail-report-v1"
    assert body["detail_id"] == "TPR-RAWREV-MARKET-ERRORDETAIL-20261007-001"
    assert body["mode"] == "production" and body["status"] == "EXPLAINED" and body["failure_stage"] is None
    assert body["error_detail"] == {"message_paths": [{"path": "$.error", "type": "string"}],
        "parameter_names": ["ticker"], "provider_text_is_data_only": True,
        "sanitized_error_detail": "Invalid ticker parameter", "suppression": None}
    assert body["error_detail"]["provider_text_is_data_only"] is True
    _false(body, "raw_error_identity_retained", "raw_error_retained", "trading")
    counters = {"additional_development_looks": 0, "error_response_bytes": 181, "existing_development_look_spent": 1,
        "fixture_transport_calls": 0, "http_status": 400, "outcome_reads": 0, "provider_requests": 1,
        "quantconnect_attempts": 0, "successful_body_reads": 0}
    _counts({key: body[key] for key in counters}, counters)
    assert all(body[key] == value for key, value in counters.items())
    assert body["market_plan_sha256"] == MARKET_PLAN_SHA
    assert body["prior_report_sha256"] == _load("diagnostic_report")[2]
    assert body["plan_sha256"] == _load("detail_plan")[2]


def _validate_probe_report(body):
    if set(body) != PROBE_REPORT_KEYS:
        raise AssertionError("unexpected probe report fields; native response is forbidden")
    assert body["schema"] == "tpr-raw-market-request-probe-report-v1"
    assert body["probe_id"] == "TPR-RAWREV-MARKET-REQUESTPROBE-20261007-001"
    assert body["mode"] == "production" and body["status"] == "PROBED" and body["failure_stage"] is None
    _false(body, "maximum_ticker_limit_established", "raw_error_identity_retained", "raw_error_retained", "trading")
    counters = {"additional_development_looks": 0, "existing_development_look_spent": 1,
        "fixture_transport_calls": 0, "outcome_reads": 0, "provider_requests": 2,
        "quantconnect_attempts": 0, "successful_body_reads": 0}
    _counts({key: body[key] for key in counters}, counters)
    assert all(body[key] == value for key, value in counters.items())
    assert body["market_plan_sha256"] == MARKET_PLAN_SHA
    assert body["detail_report_sha256"] == _load("detail_report")[2]
    assert body["plan_sha256"] == _load("probe_plan")[2]
    assert type(body["variants"]) is list and len(body["variants"]) == 2
    for row, variant, count, status, error_bytes in zip(body["variants"],
            ("full-frozen-inventory-literal-comma", "first-three-frozen-lexical-tickers-literal-comma"),
            (43, 3), (400, 200), (181, 0)):
        assert type(row) is dict and set(row) == {"variant", "ticker_count", "http_status", "error_response_bytes", "error_detail"}
        assert row["variant"] == variant
        expected = {"ticker_count": count, "http_status": status, "error_response_bytes": error_bytes}
        _counts({key: row[key] for key in expected}, expected)
        assert all(row[key] == value for key, value in expected.items())
        assert row["error_detail"] == (_load("detail_report")[0]["error_detail"] if status == 400 else None)
        if status == 400:
            assert row["error_detail"]["provider_text_is_data_only"] is True


def _validate_resume_plan(body):
    assert set(body) == RESUME_PLAN_KEYS
    assert body["schema"] == "tpr-raw-market-resume-plan-summary-v1"
    assert body["candidate_id"] == "TPR-DEV-RAWREV-v1" and body["resume_id"] == "TPR-RAWREV-MARKET-RESUME-20261007-001"
    assert body["resume_plan_sha256"] == RESUME_PLAN_SHA and body["original_plan_sha256"] == MARKET_PLAN_SHA
    assert body["owner_decision"] == "TPR-OWN-46" and body["owner_instruction_sha256"] == DETAIL_OWNER_SHA
    assert body["code_sha256"] == RESUME_CODE_SHA and body["code_hashes"] == MARKET_CODE_SHA
    assert body["detail_code_sha256"] == DETAIL_CODE_SHA and body["detail_report_sha256"] == _load("detail_report")[2]
    assert body["probe_code_sha256"] == PROBE_CODE_SHA and body["probe_report_sha256"] == _load("probe_report")[2]
    assert body["failed_capture_report_sha256"] == _load("market_report")[2]
    assert body["mode"] == "production" and body["request_mode"] == "three"
    assert body["git_sha"] == "30341bbb853ab82d03f088d0273e412424910265"
    assert body["lane_branch"] == "codex/strategy-target-price-revisions"
    assert body["lane_root"] == "/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__target_price_revisions"
    assert body["original_spent_file"] == "TPR-DEV-RAWREV-v1.spent.json"
    assert body["resume_spent_file"] == "TPR-RAWREV-MARKET-RESUME-20261007-001.spent.json"
    assert body["simulation_spent_file"] == "TPR-DEV-RAWREV-v1.simulation.spent.json"
    assert body["ticker_wire_encoding"] == "literal-comma-ticker-value-only-other-query-pairs-unchanged"
    assert body["entire_original_inventory_required"] is True
    _false(body, "canonical_admission", "native_ticker_list_published", "original_look_renewed", "quantconnect", "rights_verified", "trading")
    assert type(body["additional_development_looks"]) is int and body["additional_development_looks"] == 0
    assert type(body["ticker_count"]) is int and body["ticker_count"] == 43
    limits = {"batches": 15, "bytes_per_page": 4194304, "pages_per_batch_dataset": 1, "redirects": 0,
        "request_seconds": 30, "requests": 30, "retries": 0, "rows_per_page": 10000, "total_bytes": 33554432}
    _counts(body["limits"], limits)
    assert body["limits"] == limits
    original = _load("market_plan")[0]
    for key in ("price_dates", "action_dates", "candidate_policy_sha256", "structure_sha256", "waiver_sha256"):
        assert body[key] == original[key]
    created, expires = datetime.fromisoformat(body["created_utc"]), datetime.fromisoformat(body["expires_utc"])
    assert created.utcoffset() == expires.utcoffset() == timedelta(0) and expires - created == timedelta(hours=12)


def _validate_resume_capture(body):
    assert set(body) == RESUME_CAPTURE_KEYS
    assert body["schema"] == "tpr-raw-market-resume-capture-report-v1"
    assert body["resume_id"] == "TPR-RAWREV-MARKET-RESUME-20261007-001" and body["resume_plan_sha256"] == RESUME_PLAN_SHA
    assert body["original_plan_sha256"] == MARKET_PLAN_SHA and body["probe_report_sha256"] == _load("probe_report")[2]
    assert body["mode"] == "production" and body["request_mode"] == "three"
    assert body["status"] == "CAPTURED" and body["failure"] is body["failure_stage"] is None
    _false(body, "backtest_completed", "canonical_admission", "real_backtest_ready", "rights_verified", "trading")
    counters = {"additional_development_looks": 0, "existing_development_look_spent": 1, "fixture_transport_calls": 0,
        "last_http_status": 200, "original_ticker_count": 43, "provider_requests": 30, "quantconnect_attempts": 0,
        "response_bytes": 104560, "unique_price_ticker_count": 43}
    _counts({key: body[key] for key in counters}, counters)
    assert all(body[key] == value for key, value in counters.items())
    for key, expected in (("page_counts", {"stocks": 15, "actions": 15}),
            ("native_source_row_counts", {"stocks": 2623, "actions": 3}),
            ("unique_row_counts", {"stocks": 2623, "actions": 3}), ("exact_duplicate_rows", {"stocks": 0, "actions": 0})):
        _counts(body[key], expected)
        assert body[key] == expected
    assert body["projection_sha256"] == RESUME_PROJECTION_SHA


def _validate_resume_simulation(body):
    assert set(body) == RESUME_SIMULATION_KEYS
    assert body["schema"] == "tpr-raw-resume-simulation-report-v1"
    assert body["resume_id"] == "TPR-RAWREV-MARKET-RESUME-20261007-001" and body["resume_plan_sha256"] == RESUME_PLAN_SHA
    assert body["original_plan_sha256"] == MARKET_PLAN_SHA
    assert body["capture_report_sha256"] == _load("resume_capture")[2]
    assert body["projection_sha256"] == RESUME_PROJECTION_SHA and body["private_report_sha256"] == RESUME_PRIVATE_REPORT_SHA
    assert body["mode"] == "production" and body["status"] == "SIMULATED" and body["failure"] is body["failure_stage"] is None
    _false(body, "canonical_admission", "trading")
    counters = {"additional_development_looks": 0, "existing_development_look_spent": 1, "quantconnect_attempts": 0, "simulation_runs": 1}
    _counts({key: body[key] for key in counters}, counters)
    assert all(body[key] == value for key, value in counters.items())
    summary = body["summary"]
    assert type(summary) is dict and set(summary) == RESUME_SUMMARY_KEYS
    for key in ("valuation_complete", "frozen_window_complete", "corporate_action_accounting_complete"):
        assert summary[key] is True
    _false(summary, "engine_complete", "canonical_admission", "costs_calibrated", "market_edge_proven", "point_in_time_data", "trading")
    counts = {"study_sessions": 60, "expected_study_sessions": 60, "orders": 173, "fills": 167,
        "pending_order_count": 52, "pending_quantity": 15073, "quantconnect_attempts": 0}
    _counts({key: summary[key] for key in counts}, counts)
    assert all(summary[key] == value for key, value in counts.items())
    numbers = {"final_cash": "428.75998500", "final_dividend_receivable": "0.00000000", "final_nav": "60409.40998500",
        "max_drawdown_pct": "39.83219962", "return_pct": "-39.59059002", "total_commissions": "1269.40000000", "total_slippage": "678.80501500"}
    for key, expected in numbers.items():
        assert type(summary[key]) is str and re.fullmatch(r"-?[0-9]+\.[0-9]{8}", summary[key]) and summary[key] == expected
    assert summary["window_start"] == "2025-01-02" and summary["window_end"] == "2025-03-31"
    assert summary["pending_quantity_scope"] == "sum-of-day-only-unfilled-quantities-not-live-orders"
    assert summary["summary_rounding"] == "exact-rational-8-decimal-half-even"
    assert summary["dividend_cash_policy"] == "exdate-receivable-never-spendable-no-assumed-payment-date"
    assert summary["confirmatory_alpha"] == "0"


def _validate_existing_audit(body):
    assert set(body) == EXISTING_AUDIT_KEYS
    assert body["schema"] == "tpr-raw-existing-result-audit-v1"
    assert body["simulation_report_sha256"] == _load("resume_simulation")[2]
    assert body["private_report_sha256"] == RESUME_PRIVATE_REPORT_SHA
    _false(body, "engine_complete", "canonical_readiness", "corporate_action_interpretation_resolved", "trading")
    for key in ("existing_result_only", "fill_cost_sums_verified", "order_fill_pending_counts_verified", "return_and_drawdown_independently_verified"):
        assert body[key] is True
    counters = {"additional_candidate_computations": 0, "additional_development_looks": 0, "provider_requests": 0,
        "quantconnect_attempts": 0, "sessions_with_unpriced_positions": 0, "unresolved_action_securities": 3}
    _counts({key: body[key] for key in counters}, counters)
    assert all(body[key] == value for key, value in counters.items())
    summary = _load("resume_simulation")[0]["summary"]
    assert body["return_pct"] == summary["return_pct"] and body["max_drawdown_pct"] == summary["max_drawdown_pct"]
    expected_reasons = {"execution_name_cap": 37, "insufficient_cash": 2, "lagged_volume_capacity": 13}
    expected_quantities = {"execution_name_cap": 1454, "insufficient_cash": 494, "lagged_volume_capacity": 13125}
    for key, expected in (("pending_order_reasons", expected_reasons), ("pending_quantity_by_reason", expected_quantities),
            ("all_exclusion_reasons", dict(expected_reasons, corporate_action_unresolved=2, decision_mark_missing=52570)),
            ("counterpart_fixed_sentinel_counts", {"sentinel_N/A": 3})):
        _counts(body[key], expected)
        assert body[key] == expected
    assert sum(body["pending_order_reasons"].values()) == summary["pending_order_count"] == 52
    assert sum(body["pending_quantity_by_reason"].values()) == summary["pending_quantity"] == 15073
    shape = body["shape_detail"]
    shape_keys = {"accounting_counts", "additional_candidate_computations", "corporate_action_status_counts", "held_corporate_actions",
        "native_action_shape_counts", "new_provider_requests", "nonselected_missing_decision_marks",
        "positive_target_corporate_action_blocks", "selected_target_missing_decision_marks"}
    assert type(shape) is dict and set(shape) == shape_keys
    counts = {"additional_candidate_computations": 0, "held_corporate_actions": 0, "new_provider_requests": 0,
        "nonselected_missing_decision_marks": 52570, "positive_target_corporate_action_blocks": 2, "selected_target_missing_decision_marks": 0}
    _counts({key: shape[key] for key in counts}, counts)
    assert all(shape[key] == value for key, value in counts.items())
    for key, expected in (("native_action_shape_counts", {"counterpart_other_nonempty": 3, "exact_date_price_present": 3,
            "kind_dividend": 3, "value_positive": 3}), ("corporate_action_status_counts", {"unheld-new-entry-blocked": 3})):
        _counts(shape[key], expected)
        assert shape[key] == expected
    accounting = shape["accounting_counts"]
    numeric = {"action_row_count": 3, "cash_dividend_count": 0, "missing_bar_count": 0,
        "selected_security_count": 43, "unresolved_action_count": 3}
    assert type(accounting) is dict and set(accounting) == set(numeric) | {"action_inventory_reconciled"}
    assert accounting["action_inventory_reconciled"] is True
    _counts({key: accounting[key] for key in numeric}, numeric)
    assert all(accounting[key] == value for key, value in numeric.items())


def _validate_correction_plan(body):
    assert set(body) == CORRECTION_PLAN_KEYS
    assert body["schema"] == "tpr-raw-dividend-correction-plan-summary-v1"
    assert body["correction_id"] == "TPR-RAWREV-DIVIDEND-CORRECTION-20261008-001"
    assert body["base_candidate_id"] == "TPR-DEV-RAWREV-v1" and body["correction_plan_sha256"] == CORRECTION_PLAN_SHA
    assert body["mode"] == "production" and body["owner_decision"] == "TPR-OWN-47"
    assert body["owner_instruction_sha256"] == DETAIL_OWNER_SHA and body["git_sha"] == "30341bbb853ab82d03f088d0273e412424910265"
    assert body["code_sha256"] == CORRECTION_CODE_SHA and body["code_hashes"] == MARKET_CODE_SHA
    assert body["resume_code_sha256"] == RESUME_CODE_SHA and body["resume_plan_sha256"] == RESUME_PLAN_SHA
    assert body["original_plan_sha256"] == MARKET_PLAN_SHA and body["projection_sha256"] == RESUME_PROJECTION_SHA
    assert body["capture_report_sha256"] == _load("resume_capture")[2]
    assert body["first_simulation_report_sha256"] == _load("resume_simulation")[2]
    assert body["first_private_result_sha256"] == RESUME_PRIVATE_REPORT_SHA
    assert body["interpretation"] == DIVIDEND_INTERPRETATION
    for key in ("native_action_ids_preserved", "strategy_policy_unchanged", "accounting_interpretation_changed"):
        assert body[key] is True
    _false(body, "canonical_admission", "contractual_rights_verified", "native_ticker_list_published", "prior_look_or_simulation_rearmed",
        "source_refresh", "quantconnect", "trading", "universal_vendor_null_semantics_verified")
    counters = {"additional_development_looks": 1, "cumulative_development_looks": 2, "provider_requests": 0, "ticker_count": 43}
    _counts({key: body[key] for key in counters}, counters)
    assert all(body[key] == value for key, value in counters.items())
    assert body["reservation_file"] == "TPR-RAWREV-DIVIDEND-CORRECTION-20261008-001.spent.json"
    assert body["original_spent_file"] == "TPR-DEV-RAWREV-v1.spent.json"
    assert body["prior_simulation_spent_file"] == "TPR-DEV-RAWREV-v1.simulation.spent.json"
    parent = _load("resume_plan")[0]
    for key in ("price_dates", "action_dates", "candidate_policy_sha256", "structure_sha256", "waiver_sha256", "lane_root", "lane_branch"):
        assert body[key] == parent[key]
    created, expires = datetime.fromisoformat(body["created_utc"]), datetime.fromisoformat(body["expires_utc"])
    assert created.utcoffset() == expires.utcoffset() == timedelta(0) and timedelta(0) < expires - created <= timedelta(hours=12)
    assert datetime.fromisoformat(parent["created_utc"]) <= created < expires == datetime.fromisoformat(parent["expires_utc"])


def _validate_correction_report(body):
    assert set(body) == CORRECTION_REPORT_KEYS
    assert body["schema"] == "tpr-raw-dividend-correction-report-v1"
    assert body["correction_id"] == "TPR-RAWREV-DIVIDEND-CORRECTION-20261008-001" and body["base_candidate_id"] == "TPR-DEV-RAWREV-v1"
    assert body["mode"] == "production" and body["status"] == "SIMULATED" and body["failure"] is body["failure_stage"] is None
    assert body["owner_decision"] == "TPR-OWN-47" and body["interpretation"] == DIVIDEND_INTERPRETATION
    assert body["correction_plan_sha256"] == CORRECTION_PLAN_SHA and body["resume_plan_sha256"] == RESUME_PLAN_SHA
    assert body["capture_report_sha256"] == _load("resume_capture")[2] and body["projection_sha256"] == RESUME_PROJECTION_SHA
    assert body["first_simulation_report_sha256"] == _load("resume_simulation")[2] and body["first_private_result_sha256"] == RESUME_PRIVATE_REPORT_SHA
    assert body["private_result_sha256"] == CORRECTION_PRIVATE_RESULT_SHA
    _false(body, "canonical_admission", "contractual_rights_verified", "prior_look_or_simulation_rearmed", "source_refresh", "trading")
    counters = {"additional_development_looks": 1, "cumulative_development_looks": 2, "fixture_runs": 0, "provider_requests": 0, "quantconnect_attempts": 0}
    _counts({key: body[key] for key in counters}, counters)
    assert all(body[key] == value for key, value in counters.items())
    summary = body["summary"]
    counts = {"study_sessions": 60, "expected_study_sessions": 60, "orders": 176, "fills": 170,
        "pending_order_count": 53, "pending_quantity": 15100, "quantconnect_attempts": 0}
    numbers = {"final_cash": "464.69106500", "final_dividend_receivable": "0.00000000", "final_nav": "60641.81106500",
        "max_drawdown_pct": "39.60072803", "return_pct": "-39.35818894", "total_commissions": "1273.22000000", "total_slippage": "693.31393500"}
    expected = copy.deepcopy(_load("resume_simulation")[0]["summary"])
    expected.update(counts, **numbers)
    assert type(summary) is dict and set(summary) == RESUME_SUMMARY_KEYS and summary == expected
    for key in ("valuation_complete", "frozen_window_complete", "corporate_action_accounting_complete"):
        assert summary[key] is True
    _false(summary, "engine_complete", "canonical_admission", "costs_calibrated", "market_edge_proven", "point_in_time_data", "trading")
    _counts({key: summary[key] for key in counts}, counts)
    for key in numbers:
        assert type(summary[key]) is str and re.fullmatch(r"-?[0-9]+\.[0-9]{8}", summary[key])
    evidence = body["accounting_evidence"]
    numeric = {"action_row_count": 3, "calendar_session_count": 166, "cash_dividend_count": 3, "duplicate_action_rows": 0,
        "duplicate_stock_rows": 0, "interpreted_native_action_count": 3, "metadata_only_action_count": 0, "missing_bar_count": 0,
        "prewindow_action_count": 0, "selected_security_count": 43, "stock_row_count": 2623, "stock_split_count": 0, "unresolved_action_count": 0}
    true = ("accounting_interpretation_changed", "action_inventory_reconciled", "additional_development_look_required",
        "current_snapshot_survivorship_bias_possible", "current_vintage_imputation", "missing_or_unresolved_must_propagate_to_engine",
        "native_action_ids_preserved", "strategy_policy_unchanged")
    false = ("canonical_admission", "cross_table_adjustment_vintage_verified", "historical_symbol_match_verified", "native_split_value_direction_verified",
        "observed_provider_availability", "point_in_time_data", "quantconnect_authority", "real_backtest_ready", "trading_authority", "universal_vendor_null_semantics_verified")
    text = {"clock_model": "assumed_historical_daily_bar_clock", "correction_id": "TPR-RAWREV-DIVIDEND-CORRECTION-20261008-001",
        "dividend_basis": "same-ex-date-stock-factor-imputed-not-observed", "dividend_counterparty_interpretation": DIVIDEND_INTERPRETATION,
        "dividend_model": "ex-date-receivable-nonspendable-no-payment-date", "dividend_rounding": "exact-rational-8-decimal-half-even",
        "model": "sharadar-current-vintage-raw-imputation-v1", "owner_decision": "TPR-OWN-47", "raw_open_rounding": "exact-rational-8-decimal-half-even",
        "raw_volume_rounding": "exact-reciprocal-floor"}
    assert type(evidence) is dict and set(evidence) == set(numeric) | set(true) | set(false) | set(text)
    _counts({key: evidence[key] for key in numeric}, numeric)
    assert all(evidence[key] == value for key, value in numeric.items())
    for key in true:
        assert evidence[key] is True
    _false(evidence, *false)
    assert all(evidence[key] == value for key, value in text.items())


def _validate_corrected_audit(body):
    assert set(body) == CORRECTED_AUDIT_KEYS
    assert body["schema"] == "tpr-raw-corrected-result-audit-v1"
    assert body["simulation_report_sha256"] == _load("correction_report")[2] and body["private_report_sha256"] == CORRECTION_PRIVATE_RESULT_SHA
    _false(body, "canonical_readiness", "engine_complete", "trading")
    for key in ("corporate_action_interpretation_resolved", "existing_result_only", "fill_cost_sums_verified",
            "first_result_and_projection_hashes_unchanged", "native_action_ids_independently_verified", "order_fill_pending_counts_verified",
            "prior_and_new_spent_receipts_verified", "return_and_drawdown_independently_verified", "target_evidence_identical_to_first_result"):
        assert body[key] is True
    counts = {"additional_candidate_computations": 0, "additional_development_looks": 0, "cumulative_recorded_development_looks": 2,
        "held_corporate_actions": 0, "nonselected_missing_decision_marks": 52570, "positive_target_corporate_action_blocks": 0,
        "provider_requests": 0, "quantconnect_attempts": 0, "selected_target_missing_decision_marks": 0,
        "sessions_with_unpriced_positions": 0, "unresolved_action_securities": 0}
    _counts({key: body[key] for key in counts}, counts)
    assert all(body[key] == value for key, value in counts.items())
    reasons = {"execution_name_cap": 38, "insufficient_cash": 2, "lagged_volume_capacity": 13}
    quantities = {"execution_name_cap": 1462, "insufficient_cash": 494, "lagged_volume_capacity": 13144}
    for key, expected in (("pending_order_reasons", reasons), ("pending_quantity_by_reason", quantities),
            ("all_exclusion_reasons", dict(reasons, decision_mark_missing=52570)),
            ("corporate_action_status_counts", {"gross-exdate-receivable-not-cash": 3})):
        _counts(body[key], expected)
        assert body[key] == expected
    summary = _load("correction_report")[0]["summary"]
    assert body["return_pct"] == summary["return_pct"] and body["max_drawdown_pct"] == summary["max_drawdown_pct"]
    assert sum(body["pending_order_reasons"].values()) == summary["pending_order_count"] == 53
    assert sum(body["pending_quantity_by_reason"].values()) == summary["pending_quantity"] == 15100


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


def test_error_detail_plan_preserves_original_failure_and_prior_diagnostic_history():
    body = _load("detail_plan")[0]
    assert set(body) == DETAIL_PLAN_KEYS
    assert body["schema"] == "tpr-raw-market-error-detail-plan-v1"
    assert body["detail_id"] == "TPR-RAWREV-MARKET-ERRORDETAIL-20261007-001"
    assert body["mode"] == "production" and body["owner_decision"] == "TPR-OWN-44"
    assert body["owner_instruction_sha256"] == DETAIL_OWNER_SHA
    assert body["git_sha"] == "30341bbb853ab82d03f088d0273e412424910265"
    assert body["market_plan_sha256"] == MARKET_PLAN_SHA
    assert body["failed_capture_report_sha256"] == _load("market_report")[2]
    assert body["prior_report_sha256"] == _load("diagnostic_report")[2]
    assert body["prior_code_sha256"] == DIAGNOSTIC_CODE_SHA
    assert body["request"] == "exact-original-stocks-page-zero-error-only"
    _false(body, "outcomes", "quantconnect", "raw_error_identity_retention", "raw_error_retention", "trading")
    limits = {"additional_development_looks": 0, "error_bytes": 8192, "redirects": 0, "request_seconds": 30,
        "requests": 1, "retries": 0, "successful_body_reads": 0}
    _counts({key: body[key] for key in limits}, limits)
    assert all(body[key] == value for key, value in limits.items())
    created, expires = datetime.fromisoformat(body["created_utc"]), datetime.fromisoformat(body["expires_utc"])
    assert created.utcoffset() == expires.utcoffset() == timedelta(0)
    assert expires - created == timedelta(hours=12)
    path = PACKAGE / "raw_market_error_detail.py"
    assert stat.S_ISREG(path.lstat().st_mode) and path.resolve().parent == PACKAGE
    assert path.stat().st_size <= 128 * 1024
    assert hashlib.sha256(path.read_bytes()).hexdigest() == body["code_sha256"] == DETAIL_CODE_SHA


def test_error_detail_only_reports_fixed_sanitized_provider_explanation_without_new_look():
    _validate_detail_report(_load("detail_report")[0])
    # This later bounded disclosure cannot rewrite the prior unknown-response
    # privacy policy or turn the original capture failure into a simulation.
    _validate_diagnostic_report(_load("diagnostic_report")[0])
    _validate_market_report(_load("market_report")[0])


def test_probe_plan_is_exact_frozen_two_variant_ticker_only_error_operation():
    body, payload, digest = _load("probe_plan")
    assert set(body) == PROBE_PLAN_KEYS
    assert probe.ProbePlan(payload, digest).body() == body
    assert body["schema"] == "tpr-raw-market-request-probe-plan-v1"
    assert body["probe_id"] == "TPR-RAWREV-MARKET-REQUESTPROBE-20261007-001"
    assert body["mode"] == "production" and body["owner_decision"] == "TPR-OWN-45"
    assert body["owner_instruction_sha256"] == DETAIL_OWNER_SHA
    assert body["git_sha"] == "30341bbb853ab82d03f088d0273e412424910265"
    assert body["market_plan_sha256"] == MARKET_PLAN_SHA
    assert body["detail_report_sha256"] == _load("detail_report")[2]
    assert body["detail_code_sha256"] == DETAIL_CODE_SHA
    assert body["variants"] == ["full-frozen-inventory-literal-comma", "first-three-frozen-lexical-tickers-literal-comma"]
    assert body["original_other_query_fields_unchanged"] is body["second_variant_only_after_http_400"] is True
    _false(body, "outcomes", "quantconnect", "raw_error_identity_retention", "raw_error_retention", "trading")
    limits = {"additional_development_looks": 0, "error_bytes_per_request": 8192, "redirects": 0, "request_seconds": 30,
        "requests": 2, "retries": 0, "successful_body_reads": 0}
    _counts({key: body[key] for key in limits}, limits)
    assert all(body[key] == value for key, value in limits.items())
    created, expires = datetime.fromisoformat(body["created_utc"]), datetime.fromisoformat(body["expires_utc"])
    assert created.utcoffset() == expires.utcoffset() == timedelta(0) and expires - created == timedelta(hours=12)
    path = PACKAGE / "raw_market_request_probe.py"
    assert stat.S_ISREG(path.lstat().st_mode) and path.resolve().parent == PACKAGE and path.stat().st_size <= 128 * 1024
    assert hashlib.sha256(path.read_bytes()).hexdigest() == body["code_sha256"] == PROBE_CODE_SHA


def test_probe_observes_batch_specific_behavior_without_proving_exact_limit_or_backtest_completion():
    _validate_probe_report(_load("probe_report")[0])
    # A three-member success does not identify count, length or a bad member
    # in the other forty. Neither successful body was consumed or simulated.
    _validate_detail_report(_load("detail_report")[0])
    _validate_market_report(_load("market_report")[0])


def test_resume_plan_preserves_whole_candidate_and_existing_look_with_frozen_source():
    body = _load("resume_plan")[0]
    _validate_resume_plan(body)
    path = PACKAGE / "raw_market_resume.py"
    assert stat.S_ISREG(path.lstat().st_mode) and path.resolve().parent == PACKAGE and path.stat().st_size <= 128 * 1024
    assert hashlib.sha256(path.read_bytes()).hexdigest() == body["code_sha256"] == RESUME_CODE_SHA
    # This is public aggregate metadata, not a private plan/ticker-list opener.
    assert "original_plan" not in body and "private_root" not in body


def test_resume_capture_has_all_43_tickers_but_is_not_completed_backtest_or_new_look():
    _validate_resume_capture(_load("resume_capture")[0])
    _validate_market_report(_load("market_report")[0])
    _validate_probe_report(_load("probe_report")[0])
    assert _load("resume_capture")[0]["unique_price_ticker_count"] == _load("market_plan")[0]["ticker_count"]


def test_one_resume_simulation_preserves_partial_day_orders_and_negative_nonconfirmatory_return():
    body = _load("resume_simulation")[0]
    _validate_resume_simulation(body)
    _validate_resume_capture(_load("resume_capture")[0])
    # Independently check aggregate return arithmetic, not the private trade
    # path or maximum drawdown, which this public-only test does not reproduce.
    with localcontext(Context(prec=48, rounding=ROUND_HALF_EVEN)):
        returned = (Decimal(body["summary"]["final_nav"]) / Decimal("100000") - 1) * 100
        assert format(returned.quantize(Decimal("0.00000001")), "f") == body["summary"]["return_pct"]
    assert body["summary"]["engine_complete"] is False and body["summary"]["pending_order_count"] > 0
    _validate_market_report(_load("market_report")[0])


def test_existing_result_audit_preserves_unresolved_dividends_and_exact_partial_fill_reasons_without_rerun():
    _validate_existing_audit(_load("existing_audit")[0])
    _validate_resume_simulation(_load("resume_simulation")[0])
    # These public flags attribute the owner's recorded private-result audit;
    # this public-only regression does not reopen/reproduce the private result.
    assert _load("existing_audit")[0]["corporate_action_interpretation_resolved"] is False


def test_dividend_correction_plan_records_new_second_look_without_old_receipt_or_parameters_rearm():
    _validate_correction_plan(_load("correction_plan")[0])
    path = PACKAGE / "raw_market_dividend_correction.py"
    assert stat.S_ISREG(path.lstat().st_mode) and path.resolve().parent == PACKAGE and path.stat().st_size <= 128 * 1024
    assert hashlib.sha256(path.read_bytes()).hexdigest() == CORRECTION_CODE_SHA
    _validate_existing_audit(_load("existing_audit")[0])
    _validate_resume_simulation(_load("resume_simulation")[0])


def test_corrected_dividend_result_binds_same_inputs_three_accounted_events_and_second_negative_look():
    body = _load("correction_report")[0]
    _validate_correction_report(body)
    _validate_correction_plan(_load("correction_plan")[0])
    _validate_resume_simulation(_load("resume_simulation")[0])
    with localcontext(Context(prec=48, rounding=ROUND_HALF_EVEN)):
        returned = (Decimal(body["summary"]["final_nav"]) / Decimal("100000") - 1) * 100
        assert format(returned.quantize(Decimal("0.00000001")), "f") == body["summary"]["return_pct"]
    assert body["summary"]["engine_complete"] is False and body["summary"]["pending_order_count"] == 53
    assert body["accounting_evidence"]["cash_dividend_count"] == 3 and body["accounting_evidence"]["unresolved_action_count"] == 0
    # Zero receivables can be legitimate for unheld ex-date events. A converted
    # event count alone is not evidence of a held entitlement or cash payment.
    assert body["summary"]["final_dividend_receivable"] == "0.00000000"


def test_corrected_existing_result_audit_preserves_native_chain_target_evidence_and_unfilled_day_orders():
    _validate_corrected_audit(_load("corrected_audit")[0])
    _validate_existing_audit(_load("existing_audit")[0])
    _validate_correction_report(_load("correction_report")[0])
    # Native identity/target/receipt verification flags attribute the recorded
    # private-result audit. No native inputs or result are opened by this test.
    assert _load("corrected_audit")[0]["unresolved_action_securities"] == 0
    assert _load("existing_audit")[0]["unresolved_action_securities"] == 3


@pytest.mark.parametrize("mutation", [lambda b: b.update(native_actions=["SYNTHETIC_PRIVATE"]),
    lambda b: b.update(additional_candidate_computations=1), lambda b: b.update(additional_development_looks=True),
    lambda b: b.update(cumulative_recorded_development_looks=1), lambda b: b.update(engine_complete=True),
    lambda b: b.update(canonical_readiness=True), lambda b: b.update(corporate_action_interpretation_resolved=1),
    lambda b: b.update(first_result_and_projection_hashes_unchanged=False),
    lambda b: b.update(native_action_ids_independently_verified=False), lambda b: b.update(prior_and_new_spent_receipts_verified=False),
    lambda b: b.update(target_evidence_identical_to_first_result=False), lambda b: b.update(held_corporate_actions=3),
    lambda b: b.update(unresolved_action_securities=3), lambda b: b.update(positive_target_corporate_action_blocks=2),
    lambda b: b.update(selected_target_missing_decision_marks=1), lambda b: b.update(provider_requests=1),
    lambda b: b.update(quantconnect_attempts=1), lambda b: b.update(private_report_sha256=RESUME_PRIVATE_REPORT_SHA),
    lambda b: b["pending_order_reasons"].update(execution_name_cap=37),
    lambda b: b["pending_quantity_by_reason"].update(lagged_volume_capacity=13125),
    lambda b: b["corporate_action_status_counts"].update(SYNTHETIC_PRIVATE_ID=1),
])
def test_corrected_existing_result_audit_guard_rejects_false_chain_or_completion_and_more_work(mutation):
    body = copy.deepcopy(_load("corrected_audit")[0])
    mutation(body)
    with pytest.raises(AssertionError):
        _validate_corrected_audit(body)


@pytest.mark.parametrize("mutation", [lambda b: b.update(prices=["SYNTHETIC_PRIVATE"]),
    lambda b: b.update(additional_development_looks=0), lambda b: b.update(cumulative_development_looks=1),
    lambda b: b.update(provider_requests=True), lambda b: b.update(prior_look_or_simulation_rearmed=True),
    lambda b: b.update(projection_sha256="0" * 64), lambda b: b.update(private_result_sha256=RESUME_PRIVATE_REPORT_SHA),
    lambda b: b["summary"].update(engine_complete=True), lambda b: b["summary"].update(valuation_complete=1),
    lambda b: b["summary"].update(pending_quantity=0), lambda b: b["summary"].update(return_pct="39.35818894"),
    lambda b: b["summary"].update(confirmatory_alpha="1"), lambda b: b["summary"].update(costs_calibrated=True),
    lambda b: b["accounting_evidence"].update(cash_dividend_count=True),
    lambda b: b["accounting_evidence"].update(unresolved_action_count=3),
    lambda b: b["accounting_evidence"].update(native_action_ids_preserved=1),
    lambda b: b["accounting_evidence"].update(universal_vendor_null_semantics_verified=True),
    lambda b: b["accounting_evidence"].update(cross_table_adjustment_vintage_verified=True),
    lambda b: b["accounting_evidence"].update(observed_provider_availability=True),
    lambda b: b["accounting_evidence"].update(point_in_time_data=True),
    lambda b: b["accounting_evidence"].update(strategy_policy_unchanged=False),
    lambda b: b["accounting_evidence"].update(accounting_interpretation_changed=False),
    lambda b: b["accounting_evidence"].update(dividend_basis="observed-raw-entitlement"),
    lambda b: b["accounting_evidence"].update(tickers=["SYNTHETIC_PRIVATE"]),
])
def test_corrected_result_guard_rejects_native_leaks_hidden_second_look_and_false_pit_or_fill_completion(mutation):
    body = copy.deepcopy(_load("correction_report")[0])
    mutation(body)
    with pytest.raises(AssertionError):
        _validate_correction_report(body)


@pytest.mark.parametrize("mutation", [lambda b: b.update(native_actions=["SYNTHETIC_PRIVATE"]),
    lambda b: b.update(original_plan={"tickers": ["SYNTHETIC_PRIVATE"]}),
    lambda b: b.update(additional_development_looks=0), lambda b: b.update(additional_development_looks=True),
    lambda b: b.update(cumulative_development_looks=1), lambda b: b.update(prior_look_or_simulation_rearmed=True),
    lambda b: b.update(universal_vendor_null_semantics_verified=True), lambda b: b.update(source_refresh=True),
    lambda b: b.update(accounting_interpretation_changed=False), lambda b: b.update(strategy_policy_unchanged=1),
    lambda b: b.update(native_action_ids_preserved=False), lambda b: b.update(ticker_count=3),
    lambda b: b.update(provider_requests=1), lambda b: b.update(quantconnect=True),
    lambda b: b.update(contractual_rights_verified=True), lambda b: b.update(interpretation="universal-N/A-null"),
    lambda b: b["code_hashes"].update({"raw_market_inputs.py": "0" * 64}),
    lambda b: b.update(reservation_file="TPR-DEV-RAWREV-v1.simulation.spent.json"),
])
def test_dividend_correction_plan_guard_rejects_universal_null_native_data_unrecorded_look_or_old_rearm(mutation):
    body = copy.deepcopy(_load("correction_plan")[0])
    mutation(body)
    with pytest.raises(AssertionError):
        _validate_correction_plan(body)


@pytest.mark.parametrize("mutation", [lambda b: b.update(private_rows=["SYNTHETIC_PRIVATE"]),
    lambda b: b.update(provider_requests=1), lambda b: b.update(additional_candidate_computations=1),
    lambda b: b.update(additional_development_looks=True), lambda b: b.update(existing_result_only=1),
    lambda b: b.update(engine_complete=True), lambda b: b.update(corporate_action_interpretation_resolved=True),
    lambda b: b.update(canonical_readiness=True), lambda b: b.update(unresolved_action_securities=0),
    lambda b: b.update(sessions_with_unpriced_positions=1), lambda b: b.update(private_report_sha256="0" * 64),
    lambda b: b["pending_order_reasons"].update(execution_name_cap=36),
    lambda b: b["pending_quantity_by_reason"].update(lagged_volume_capacity=13126),
    lambda b: b["pending_order_reasons"].update(SYNTHETIC_PRIVATE_REASON=1),
    lambda b: b["counterpart_fixed_sentinel_counts"].update(SYNTHETIC_PRIVATE_NATIVE_VALUE=1),
    lambda b: b["shape_detail"].update(selected_target_missing_decision_marks=1),
    lambda b: b["shape_detail"].update(positive_target_corporate_action_blocks=0),
    lambda b: b["shape_detail"].update(new_provider_requests=True),
    lambda b: b["shape_detail"]["accounting_counts"].update(cash_dividend_count=3),
    lambda b: b["shape_detail"]["accounting_counts"].update(action_inventory_reconciled=1),
    lambda b: b["shape_detail"]["native_action_shape_counts"].update(ticker="SYNTHETIC_PRIVATE"),
])
def test_existing_result_audit_guard_rejects_false_resolution_native_leaks_or_additional_work(mutation):
    body = copy.deepcopy(_load("existing_audit")[0])
    mutation(body)
    with pytest.raises(AssertionError):
        _validate_existing_audit(body)


@pytest.mark.parametrize("mutation", [lambda b: b.update(trades=[{"ticker": "SYNTHETIC_PRIVATE"}]),
    lambda b: b.update(additional_development_looks=1), lambda b: b.update(simulation_runs=2),
    lambda b: b.update(simulation_runs=True), lambda b: b.update(existing_development_look_spent=0),
    lambda b: b.update(quantconnect_attempts=1), lambda b: b.update(capture_report_sha256="0" * 64),
    lambda b: b.update(private_report_sha256="0" * 64), lambda b: b["summary"].update(engine_complete=True),
    lambda b: b["summary"].update(engine_complete=0), lambda b: b["summary"].update(valuation_complete=1),
    lambda b: b["summary"].update(study_sessions=59), lambda b: b["summary"].update(pending_order_count=0),
    lambda b: b["summary"].update(pending_quantity_scope="live-orders"),
    lambda b: b["summary"].update(return_pct="39.59059002"), lambda b: b["summary"].update(final_nav=60409.409985),
    lambda b: b["summary"].update(costs_calibrated=True), lambda b: b["summary"].update(point_in_time_data=True),
    lambda b: b["summary"].update(canonical_admission=True), lambda b: b["summary"].update(confirmatory_alpha="1"),
    lambda b: b["summary"].update(positions=["SYNTHETIC_PRIVATE"]),
])
def test_resume_simulation_guard_rejects_native_values_false_completion_rearm_and_alpha(mutation):
    body = copy.deepcopy(_load("resume_simulation")[0])
    mutation(body)
    with pytest.raises(AssertionError):
        _validate_resume_simulation(body)


@pytest.mark.parametrize("label,validator,mutate", [
    ("resume_plan", _validate_resume_plan, lambda b: b.update(tickers=["SYNTHETIC_PRIVATE"])),
    ("resume_plan", _validate_resume_plan, lambda b: b.update(original_look_renewed=True)),
    ("resume_plan", _validate_resume_plan, lambda b: b.update(original_look_renewed=0)),
    ("resume_plan", _validate_resume_plan, lambda b: b.update(additional_development_looks=1)),
    ("resume_plan", _validate_resume_plan, lambda b: b.update(entire_original_inventory_required=1)),
    ("resume_plan", _validate_resume_plan, lambda b: b.update(request_mode="all")),
    ("resume_plan", _validate_resume_plan, lambda b: b["limits"].update(requests=True)),
    ("resume_plan", _validate_resume_plan, lambda b: b["code_hashes"].update({"raw_run.py": "0" * 64})),
    ("resume_plan", _validate_resume_plan, lambda b: b.update(original_spent_file="SYNTHETIC_REARM.spent.json")),
    ("resume_capture", _validate_resume_capture, lambda b: b.update(prices=[{"ticker": "SYNTHETIC_PRIVATE"}])),
    ("resume_capture", _validate_resume_capture, lambda b: b.update(backtest_completed=True)),
    ("resume_capture", _validate_resume_capture, lambda b: b.update(backtest_completed=0)),
    ("resume_capture", _validate_resume_capture, lambda b: b.update(real_backtest_ready=True)),
    ("resume_capture", _validate_resume_capture, lambda b: b.update(existing_development_look_spent=0)),
    ("resume_capture", _validate_resume_capture, lambda b: b.update(additional_development_looks=True)),
    ("resume_capture", _validate_resume_capture, lambda b: b.update(unique_price_ticker_count=3)),
    ("resume_capture", _validate_resume_capture, lambda b: b.update(provider_requests=31)),
    ("resume_capture", _validate_resume_capture, lambda b: b.update(quantconnect_attempts=1)),
    ("resume_capture", _validate_resume_capture, lambda b: b.update(projection_sha256="0" * 64)),
    ("resume_capture", _validate_resume_capture, lambda b: b["page_counts"].update(stocks=16)),
    ("resume_capture", _validate_resume_capture, lambda b: b["unique_row_counts"].update(actions=True)),
    ("resume_capture", _validate_resume_capture, lambda b: b.update(summary={"return_pct": "0"})),
])
def test_resume_guards_reject_partial_candidate_native_leaks_rearm_or_capture_completion(label, validator, mutate):
    body = copy.deepcopy(_load(label)[0])
    mutate(body)
    with pytest.raises(AssertionError):
        validator(body)


@pytest.mark.parametrize("mutation", [lambda b: b.update(raw_error="SYNTHETIC_PRIVATE"),
    lambda b: b.update(raw_error_sha256="0" * 64), lambda b: b.update(successful_body_reads=1),
    lambda b: b.update(additional_development_looks=1), lambda b: b.update(existing_development_look_spent=0),
    lambda b: b.update(outcome_reads=1), lambda b: b.update(quantconnect_attempts=1),
    lambda b: b.update(raw_error_retained=True), lambda b: b.update(maximum_ticker_limit_established=True),
    lambda b: b.update(maximum_ticker_limit_established=0), lambda b: b.update(maximum_ticker_count=3),
    lambda b: b.update(backtest_completed=True), lambda b: b.update(provider_requests=True),
    lambda b: b["variants"][0].update(ticker_count=3), lambda b: b["variants"][1].update(http_status=400),
    lambda b: b["variants"][1].update(error_response_bytes=True),
    lambda b: b["variants"][1].update(error_detail={"prices": "SYNTHETIC_PRIVATE"}),
    lambda b: b["variants"][0]["error_detail"].update(provider_text_is_data_only=1),
    lambda b: b["variants"][0]["error_detail"].update(sanitized_error_detail="SYNTHETIC_PRIVATE"),
    lambda b: b["variants"].reverse()])
def test_probe_public_guard_rejects_native_values_false_limits_and_spent_look_rewrites(mutation):
    body = copy.deepcopy(_load("probe_report")[0])
    mutation(body)
    with pytest.raises(AssertionError):
        _validate_probe_report(body)


@pytest.mark.parametrize("mutation", [lambda b: b.update(raw_error="SYNTHETIC_PRIVATE"),
    lambda b: b.update(raw_error_sha256="0" * 64), lambda b: b.update(successful_body_reads=1),
    lambda b: b.update(additional_development_looks=1), lambda b: b.update(outcome_reads=1),
    lambda b: b.update(quantconnect_attempts=1), lambda b: b.update(raw_error_retained=True),
    lambda b: b["error_detail"].update(sanitized_error_detail="SYNTHETIC_PRIVATE_TICKER"),
    lambda b: b["error_detail"].update(parameter_names=["SYNTHETIC_PRIVATE"]),
    lambda b: b["error_detail"].update(provider_text_is_data_only=1),
    lambda b: b["error_detail"].update(raw="SYNTHETIC_PRIVATE"),
    lambda b: b.update(backtest_completed=True)])
def test_error_detail_guard_does_not_generalize_permission_to_raw_errors_or_outcomes(mutation):
    body = copy.deepcopy(_load("detail_report")[0])
    mutation(body)
    with pytest.raises(AssertionError):
        _validate_detail_report(body)


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
