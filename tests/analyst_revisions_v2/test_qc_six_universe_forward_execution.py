"""Synthetic source-byte and calendar matching; no provider/QC/order outcomes."""

import copy
import hashlib
import inspect
import json
import sys
from dataclasses import FrozenInstanceError, fields
from datetime import datetime, time, timedelta, timezone
from types import MappingProxyType
from zoneinfo import ZoneInfo

import pytest

from data.exchange_calendar import session_close_instant, session_open_instant, trading_sessions
from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2_qc import six_universe_forward_execution as subject
from research.analyst_revisions_v2_qc import six_universe_forward_predecision as predecision
from research.analyst_revisions_v2_qc import six_universe_forward_stock_selection_policy as selection
from tests.analyst_revisions_v2 import test_qc_six_universe_forward_predecision as input_tests


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _inputs(session="2026-09-28"):
    qc, vendor, crosswalk, identity, prices = input_tests._documents()
    date = datetime.fromisoformat(session).date()
    ny = ZoneInfo("America/New_York")
    cutoff = datetime.combine(date, time(9, 20), ny)
    callback = datetime.combine(date, time(9), ny)
    previous = trading_sessions(date - timedelta(days=31), date - timedelta(days=1))[-1]
    previous_close = session_close_instant(previous.isoformat())
    for document in (qc, crosswalk, identity, prices):
        document["decision_session"] = session
    qc["qc_decision_time_ny"] = cutoff.isoformat()
    for source in qc["sources"].values():
        source["qc_callback_time_ny"] = callback.isoformat()
        source["qc_source_end_time_ny"] = previous_close.astimezone(ny).isoformat()
        source["diagnostic_raw_end_time_calendar_lag_days"] = (date - previous).days
    vendor["first_event_date"] = vendor["last_event_date"] = session
    vendor["capture_started_at"] = callback.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    vendor["capture_completed_at"] = (callback + timedelta(minutes=5)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    identity["acquired_at_utc"] = (callback + timedelta(minutes=10)).astimezone(timezone.utc).isoformat()
    for document in (crosswalk, identity):
        for row in document["rows"]:
            row["available_at_utc"] = previous_close.isoformat()
    prices["source_time_utc"] = previous_close.isoformat()
    qc_bytes = input_tests._ascii_bytes(qc)
    vendor_bytes = canonical_json_bytes(vendor)
    crosswalk["qc_snapshot_sha256"] = identity["qc_snapshot_sha256"] = prices["qc_snapshot_sha256"] = _sha(qc_bytes)
    crosswalk["vendor_receipt_sha256"] = _sha(vendor_bytes)
    payloads = {
        "qc_snapshot": qc_bytes, "vendor_receipt": vendor_bytes,
        "crosswalk": input_tests._ascii_bytes(crosswalk),
        "holdings_identity": input_tests._ascii_bytes(identity),
        "reference_price": input_tests._ascii_bytes(prices),
    }
    result = {"decision_session": session}
    for name, raw in payloads.items():
        result[name + "_bytes"] = raw
        result[name + "_sha256"] = _sha(raw)
    return result


def _configuration(inputs):
    common = predecision.build_predecision_diagnostic(**inputs)
    date = datetime.fromisoformat(inputs["decision_session"]).date()
    cutoff = datetime.combine(date, time(9, 20), ZoneInfo("America/New_York")).astimezone(timezone.utc).isoformat()
    execution = (session_open_instant(date.isoformat()) + timedelta(minutes=1)).isoformat()
    return {
        "schema": subject.CONFIGURATION_SCHEMA,
        "arms": [{
            "candidate_id": candidate, "decision_session": date.isoformat(),
            "common_input_sha256": common.common_input_sha256,
            "execution_policy_sha256": subject.FROZEN_POLICY_SHA256,
            "decision_cutoff_utc": cutoff,
            "planned_execution_session": date.isoformat(),
            "planned_execution_time_utc": execution,
            "starting_cash_usd": "1000000", "initial_positions": [],
        } for candidate in subject.CANDIDATE_IDS],
    }


def _run(inputs=None, configuration=None, *, raw=None, pin=None):
    inputs = _inputs() if inputs is None else inputs
    configuration = _configuration(inputs) if configuration is None else configuration
    raw = canonical_json_bytes(configuration) if raw is None else raw
    return subject.build_matched_execution_diagnostic(
        predecision_inputs=inputs, arm_configuration_bytes=raw,
        arm_configuration_sha256=_sha(raw) if pin is None else pin,
    )


def test_exact_policy_retains_declarations_null_bindings_and_false_capabilities():
    raw = subject.POLICY_PATH.read_bytes()
    policy = subject.load_policy()
    assert _sha(raw) == subject.FROZEN_POLICY_SHA256
    assert raw == (json.dumps(json.loads(raw), sort_keys=True, indent=2) + "\n").encode("ascii")
    assert type(policy) is MappingProxyType
    assert policy["construction_policy_sha256"] == subject.CONSTRUCTION_POLICY_SHA256
    assert policy["stock_selection_policy_sha256"] == selection.FROZEN_POLICY_SHA256
    assert policy["candidate_ids"] == subject.CANDIDATE_IDS
    assert policy["reference_price"]["normalization"] == "RAW"
    assert policy["reference_price"]["independent_origin_proven"] is False
    assert policy["schedule"]["planned_start_is_actual_fill_claim"] is False
    assert policy["initial_simulated_account"] == {"currency": "USD", "nav_usd": "1000000", "cash_usd": "1000000", "positions": ()}
    assert policy["declared_economics"]["fee_bps_per_side"] == "10"
    assert policy["declared_economics"]["baseline_adverse_slippage_bps"] == "0"
    assert policy["declared_adapter_requirements"]["target_gross_exposure"] == "0.98"
    assert policy["declared_adapter_requirements"]["policy_text_enforces_adapter_rules"] is False
    assert all(value is None for value in policy["pending_bindings"].values())
    assert all(value is False for value in policy["capabilities"].values())
    assert policy["decision_ready"] is policy["execution_adapter_implemented"] is False
    with pytest.raises(TypeError):
        policy["schedule"]["rebalance_frequency"] = "daily"


@pytest.mark.parametrize("path,value", (
    (("schedule", "rebalance_frequency"), "daily"),
    (("schedule", "decision_cutoff"), "after_close"),
    (("schedule", "planned_market_order_start"), "next_open"),
    (("schedule", "planned_start_is_actual_fill_claim"), True),
    (("reference_price", "normalization"), "ADJUSTED"),
    (("reference_price", "clock"), "any_predecision_price"),
    (("reference_price", "identical_source_bytes_for_all_arms"), False),
    (("initial_simulated_account", "cash_usd"), 1000000),
    (("declared_economics", "fee_bps_per_side"), "0"),
    (("declared_economics", "baseline_adverse_slippage_bps"), "5"),
    (("declared_adapter_requirements", "sequence"), "buys_first"),
    (("declared_adapter_requirements", "target_gross_exposure"), "1.98"),
    (("declared_adapter_requirements", "leverage_allowed"), True),
    (("declared_adapter_requirements", "policy_text_enforces_adapter_rules"), 0),
    (("pending_bindings", "paper_epoch_sha256"), "a" * 64),
    (("capabilities", "orders"), 0),
    (("decision_ready",), True),
))
def test_changed_policy_semantics_types_and_authority_refuse(path, value):
    policy = json.loads(subject.POLICY_PATH.read_bytes())
    target = policy
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(subject.ForwardExecutionError, match="EXECUTION_POLICY_CHANGED"):
        subject.validate_policy(policy)


def test_policy_unknown_fields_and_corrupt_noncanonical_bytes_refuse(tmp_path, monkeypatch):
    policy = json.loads(subject.POLICY_PATH.read_bytes())
    policy["authority"] = True
    with pytest.raises(subject.ForwardExecutionError, match="EXECUTION_POLICY_CHANGED"):
        subject.validate_policy(policy)
    raw = subject.POLICY_PATH.read_bytes() + b" "
    path = tmp_path / "child.json"
    path.write_bytes(raw)
    monkeypatch.setattr(subject, "POLICY_PATH", path)
    with pytest.raises(subject.ForwardExecutionError, match="EXECUTION_POLICY_SHA256_MISMATCH"):
        subject.load_policy()
    monkeypatch.setattr(subject, "FROZEN_POLICY_SHA256", _sha(raw))
    with pytest.raises(subject.ForwardExecutionError, match="EXECUTION_POLICY_NONCANONICAL"):
        subject.load_policy()


@pytest.mark.parametrize("raw", (b'{"schema":1,"schema":2}', b'{"schema":NaN}', b'\xff'))
def test_policy_duplicate_nonfinite_and_nonascii_refuse(tmp_path, monkeypatch, raw):
    path = tmp_path / "child.json"
    path.write_bytes(raw)
    monkeypatch.setattr(subject, "POLICY_PATH", path)
    monkeypatch.setattr(subject, "FROZEN_POLICY_SHA256", _sha(raw))
    with pytest.raises(subject.ForwardExecutionError, match="EXECUTION_POLICY_JSON_INVALID"):
        subject.load_policy()


@pytest.mark.parametrize("parent", (subject.construction, selection))
def test_parent_pin_change_refuses(monkeypatch, parent):
    monkeypatch.setattr(parent, "FROZEN_POLICY_SHA256", "f" * 64)
    with pytest.raises(subject.ForwardExecutionError, match="EXECUTION_PARENT_IDENTITY_CHANGED"):
        subject.load_policy()


def test_parent_loader_unavailable_refuses(monkeypatch):
    def refuse():
        raise selection.ForwardStockSelectionPolicyError("unavailable")
    monkeypatch.setattr(selection, "load_policy", refuse)
    with pytest.raises(subject.ForwardExecutionError, match="EXECUTION_PARENT_AUTHENTICATION_FAILED"):
        subject.load_policy()


@pytest.mark.parametrize("key,value", (
    ("parent_construction_policy_sha256", "f" * 64),
    ("decision_ready", True), ("stock_selection_executable", True),
    ("capabilities", {"orders": True}),
))
def test_parent_authority_check_refuses_each_drift(monkeypatch, key, value):
    policy = json.loads(selection.POLICY_PATH.read_bytes())
    policy[key] = value
    monkeypatch.setattr(selection, "load_policy", lambda: policy)
    with pytest.raises(subject.ForwardExecutionError, match="EXECUTION_PARENT_AUTHORITY_CHANGED"):
        subject.load_policy()


@pytest.mark.parametrize("session,cutoff,start,prior,close", (
    ("2026-09-28", "2026-09-28T13:20:00+00:00", "2026-09-28T13:31:00+00:00", "2026-09-25", "2026-09-25T20:00:00+00:00"),
    ("2026-09-08", "2026-09-08T13:20:00+00:00", "2026-09-08T13:31:00+00:00", "2026-09-04", "2026-09-04T20:00:00+00:00"),
    ("2026-03-09", "2026-03-09T13:20:00+00:00", "2026-03-09T13:31:00+00:00", "2026-03-06", "2026-03-06T21:00:00+00:00"),
    ("2026-11-02", "2026-11-02T14:20:00+00:00", "2026-11-02T14:31:00+00:00", "2026-10-30", "2026-10-30T20:00:00+00:00"),
    ("2026-11-30", "2026-11-30T14:20:00+00:00", "2026-11-30T14:31:00+00:00", "2026-11-27", "2026-11-27T18:00:00+00:00"),
))
def test_calendar_true_weekly_holiday_dst_and_prior_early_close(session, cutoff, start, prior, close):
    inputs = _inputs(session)
    report = _run(inputs)
    assert report.decision_session == report.planned_execution_session == session
    assert report.decision_cutoff_utc == cutoff
    assert report.planned_execution_time_utc == start
    assert report.reference_price_session == prior
    assert report.reference_price_source_time_utc == close
    assert report.reference_price_sha256 == inputs["reference_price_sha256"]
    assert report.decision_ready is report.order_or_outcome_access is False
    assert report.refusal_codes[:5] == predecision.build_predecision_diagnostic(**inputs).refusal_codes
    assert report.refusal_codes[5:] == (
        "RAW_PREVIOUS_CLOSE_PRICE_PROVENANCE_UNPROVEN", "AUTHENTICATED_AR_SCORE_INPUT_UNBOUND",
        "OWN_ETF_SECURITY_IDENTITY_UNPROVEN", "EXECUTION_ADAPTER_AND_PARITY_UNPROVEN",
        "FORWARD_EVIDENCE_EPOCH_UNBOUND",
    )
    assert tuple(arm.candidate_id for arm in report.arms) == subject.CANDIDATE_IDS
    assert {arm.matched_configuration_sha256 for arm in report.arms} == {report.matched_configuration_sha256}
    assert {arm.common_input_sha256 for arm in report.arms} == {report.common_input_sha256}
    assert {arm.execution_policy_sha256 for arm in report.arms} == {subject.FROZEN_POLICY_SHA256}


@pytest.mark.parametrize("session,reason", (
    ("2026-09-07", "DECISION_NOT_NYSE_SESSION"),
    ("2026-09-26", "DECISION_NOT_NYSE_SESSION"),
    ("2026-09-29", "DECISION_NOT_FIRST_WEEKLY_NYSE_SESSION"),
    ("20260928", "DECISION_CALENDAR_INVALID"),
    ("2026-9-28", "DECISION_CALENDAR_INVALID"),
    ("2036-01-01", "DECISION_CALENDAR_INVALID"),
))
def test_holiday_weekend_nonweekly_and_noncanonical_date_refuse(session, reason):
    inputs = _inputs()
    inputs["decision_session"] = session
    with pytest.raises(subject.ForwardExecutionError, match=reason):
        _run(inputs, _configuration(_inputs()))


@pytest.mark.parametrize("arm", (0, 1, 2))
@pytest.mark.parametrize("field,value", (
    ("candidate_id", "ARV2_WRONG"), ("decision_session", "2026-09-29"),
    ("common_input_sha256", "f" * 64), ("execution_policy_sha256", "f" * 64),
    ("decision_cutoff_utc", "2026-09-28T13:20:01+00:00"),
    ("decision_cutoff_utc", "2026-09-28T13:20:00Z"),
    ("planned_execution_session", "2026-09-29"),
    ("planned_execution_time_utc", "2026-09-28T13:31:01+00:00"),
    ("planned_execution_time_utc", "2026-09-28T09:31:00-04:00"),
    ("starting_cash_usd", "999999"), ("starting_cash_usd", 1000000),
    ("initial_positions", [{"security_id": "SEC-A", "shares": 1}]),
    ("initial_positions", None),
))
def test_each_arm_field_drift_refuses(arm, field, value):
    inputs = _inputs()
    config = _configuration(inputs)
    config["arms"][arm][field] = value
    with pytest.raises(subject.ForwardExecutionError, match="MATCHED_ARM_CONFIGURATION_CHANGED"):
        _run(inputs, config)


@pytest.mark.parametrize("mutate", (
    lambda c: c["arms"].pop(), lambda c: c["arms"].append(copy.deepcopy(c["arms"][0])),
    lambda c: c["arms"].reverse(), lambda c: c["arms"].__setitem__(1, copy.deepcopy(c["arms"][0])),
    lambda c: c.update(orders_allowed=True), lambda c: c["arms"][0].update(nav_usd="1000000"),
    lambda c: c["arms"][0].pop("starting_cash_usd"), lambda c: c.update(schema="other"),
))
def test_arm_census_unknown_missing_fields_and_schema_refuse(mutate):
    inputs = _inputs()
    config = _configuration(inputs)
    mutate(config)
    with pytest.raises(subject.ForwardExecutionError, match="MATCHED_ARM_CONFIGURATION_CHANGED"):
        _run(inputs, config)


@pytest.mark.parametrize("timestamp", ("2026-09-24T20:00:00+00:00", "2026-09-25T20:00:01+00:00", "2026-09-25T19:59:59+00:00"))
def test_old_or_just_wrong_prior_price_clock_refuses(timestamp):
    inputs = _inputs()
    prices = json.loads(inputs["reference_price_bytes"])
    prices["source_time_utc"] = timestamp
    inputs["reference_price_bytes"] = input_tests._ascii_bytes(prices)
    inputs["reference_price_sha256"] = _sha(inputs["reference_price_bytes"])
    with pytest.raises(subject.ForwardExecutionError, match="REFERENCE_PRICE_NOT_IMMEDIATE_PRIOR_NYSE_CLOSE"):
        _run(inputs)


def test_missing_prior_price_clock_refuses_through_recomputed_source():
    inputs = _inputs()
    config = _configuration(inputs)
    prices = json.loads(inputs["reference_price_bytes"])
    del prices["source_time_utc"]
    inputs["reference_price_bytes"] = input_tests._ascii_bytes(prices)
    inputs["reference_price_sha256"] = _sha(inputs["reference_price_bytes"])
    with pytest.raises(subject.ForwardExecutionError, match="PREDECISION_SOURCE_REFUSED: PRICE_SHAPE_CHANGED"):
        _run(inputs, config)


@pytest.mark.parametrize("name", ("qc_snapshot", "vendor_receipt", "crosswalk", "holdings_identity", "reference_price"))
def test_each_source_pin_corruption_refuses(name):
    inputs = _inputs()
    config = _configuration(inputs)
    inputs[name + "_sha256"] = "f" * 64
    with pytest.raises(subject.ForwardExecutionError, match="PREDECISION_SOURCE_REFUSED"):
        _run(inputs, config)


def test_forged_report_unknown_input_and_numeric_alias_refuse():
    inputs = _inputs()
    config = _configuration(inputs)
    forged = predecision.build_predecision_diagnostic(**inputs)
    for value, reason in (
        (forged, "PREDECISION_INPUT_KWARGS_INVALID"),
        ({**inputs, "trusted_report": forged}, "PREDECISION_INPUT_KWARGS_INVALID"),
        ({**inputs, "qc_snapshot_bytes": bytearray(inputs["qc_snapshot_bytes"])}, "PREDECISION_INPUT_TYPES_INVALID"),
        ({**inputs, "decision_session": 20260928}, "PREDECISION_INPUT_TYPES_INVALID"),
    ):
        with pytest.raises(subject.ForwardExecutionError, match=reason):
            _run(value, config)


@pytest.mark.parametrize("raw,pin,reason", (
    (b"{}\n", "f" * 64, "ARM_CONFIGURATION_SHA256_MISMATCH"),
    (b"{}\n", "bad", "ARM_CONFIGURATION_SHA256_INVALID"),
    (b"{}\n", 1, "ARM_CONFIGURATION_SHA256_INVALID"),
    (bytearray(b"{}\n"), None, "ARM_CONFIGURATION_BYTES_INVALID"),
    (b"", None, "ARM_CONFIGURATION_BYTES_INVALID"),
    (b'{"schema":1,"schema":2}\n', None, "ARM_CONFIGURATION_NONCANONICAL_OR_INVALID"),
    (b'{"schema":NaN}\n', None, "ARM_CONFIGURATION_NONCANONICAL_OR_INVALID"),
))
def test_config_byte_pin_type_duplicate_nonfinite_refusals(raw, pin, reason):
    with pytest.raises(subject.ForwardExecutionError, match=reason):
        _run(raw=raw, pin=pin)


def test_rehashed_noncanonical_configuration_refuses():
    config = _configuration(_inputs())
    for raw in (json.dumps(config, indent=2).encode("ascii"), canonical_json_bytes(config) + b" "):
        with pytest.raises(subject.ForwardExecutionError, match="ARM_CONFIGURATION_NONCANONICAL_OR_INVALID"):
            _run(raw=raw)


def test_output_is_deep_immutable_and_contains_no_target_or_order_fields():
    inputs = _inputs()
    config = _configuration(inputs)
    report = _run(inputs, config)
    original = repr(report)
    config["arms"][0]["initial_positions"].append({"injected": True})
    inputs["reference_price_bytes"] = b"bad"
    assert repr(report) == original
    assert type(report.arms) is type(report.refusal_codes) is tuple
    with pytest.raises(FrozenInstanceError):
        report.decision_ready = True
    with pytest.raises(FrozenInstanceError):
        report.arms[0].candidate_id = "other"
    assert not {"targets", "orders", "quantity", "shares", "side"} & {field.name for field in fields(report)}


def test_changed_but_valid_price_source_bytes_change_common_matched_digest():
    inputs = _inputs()
    first = _run(inputs)
    prices = json.loads(inputs["reference_price_bytes"])
    prices["positive_reference_prices"][0][1] = "11"
    inputs["reference_price_bytes"] = input_tests._ascii_bytes(prices)
    inputs["reference_price_sha256"] = _sha(inputs["reference_price_bytes"])
    second = _run(inputs)
    assert first.common_input_sha256 != second.common_input_sha256
    assert first.arm_configuration_sha256 != second.arm_configuration_sha256
    assert first.matched_configuration_sha256 != second.matched_configuration_sha256
    assert first.refusal_codes == second.refusal_codes
    assert second.decision_ready is second.order_or_outcome_access is False


def test_mutation_of_caller_input_after_source_validation_cannot_rebind_report(monkeypatch):
    inputs = _inputs()
    config = _configuration(inputs)
    expected = _run(inputs, config)
    real_builder = predecision.build_predecision_diagnostic

    def mutate_caller_after_validation(**kwargs):
        result = real_builder(**kwargs)
        inputs["reference_price_bytes"] = b"unvalidated caller replacement"
        inputs["reference_price_sha256"] = "f" * 64
        return result

    monkeypatch.setattr(predecision, "build_predecision_diagnostic", mutate_caller_after_validation)
    observed = _run(inputs, config)
    assert observed == expected
    assert observed.reference_price_sha256 != inputs["reference_price_sha256"]


def test_mutation_at_copy_boundary_has_named_refusal_instead_of_raw_keyerror():
    inputs = _inputs()
    config = _configuration(inputs)
    function = subject.build_matched_execution_diagnostic
    lines, first_line = inspect.getsourcelines(function)
    copy_line = first_line + next(
        index for index, line in enumerate(lines)
        if "predecision_inputs = predecision_inputs.copy()" in line
    )
    mutated = False

    def mutate_at_copy(frame, event, arg):
        nonlocal mutated
        if not mutated and event == "line" and frame.f_code is function.__code__ and frame.f_lineno == copy_line:
            inputs.pop("decision_session")
            mutated = True
        return mutate_at_copy

    previous_trace = sys.gettrace()
    try:
        sys.settrace(mutate_at_copy)
        with pytest.raises(subject.ForwardExecutionError, match="PREDECISION_INPUT_KWARGS_INVALID"):
            _run(inputs, config)
    finally:
        sys.settrace(previous_trace)
    assert mutated is True
