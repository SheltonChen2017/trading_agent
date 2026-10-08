"""Synthetic-only audit proofs; no licensed rows, cloud calls or new outcomes."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path

import pytest

from research.target_price_revisions_qc import matched_audit as audit, matched_bundle as bundle

ROOT = Path(__file__).resolve().parents[2]


def config(arm="tpr_on", cost="baseline"):
    candidate = next(row for row in bundle.CANDIDATES if row[1:3] == (arm, cost))
    return {"schema": "tpr-qc-matched-config-v1", "study_id": bundle.STUDY,
            "freeze_sha256": bundle.FREEZE_SHA256, "candidate_id": candidate[0],
            "arm": arm, "cost": cost, "slippage": candidate[3]}


def digest(value):
    return hashlib.sha256(bundle.canonical(value)).hexdigest()


def rebind(args):
    result, logs, pages, receipt, _ = args
    receipt["evidence_hashes"] = {"result": digest(result), "logs": digest(logs), "order_pages": [digest(page) for page in pages]}
    return args


def fixture(arm="tpr_on", cost="baseline", *, empty=False):
    policy = config(arm, cost)
    selected = {etf: 14 for etf in audit.ETFS}
    n = 0 if empty else 6 if arm == "etf_basket" else 1
    summary = {"study_id": bundle.STUDY, "candidate_id": policy["candidate_id"], "arm": arm, "cost": cost,
        "config_sha256": digest(policy), "freeze_sha256": bundle.FREEZE_SHA256,
        "packet_sha256": bundle.PACKET_SHA256 if arm == "tpr_on" else None,
        "decisions": 14, "refused_decisions": 0, "submitted_orders": n,
        "fill_events": n, "requested_shares": n * 12,
        "submitted_shares": n * 10, "filled_shares": n * 10,
        "fees": audit._text(Fraction(n, 10)), "valuation_days": 60, "last_valuation_session": "2025-03-31",
        "reason_counts": {}, "max_cash_ledger_residual": "0", "max_nav_ledger_residual": "0",
        "position_ledger_mismatches": 0, "risk_breaches": 0, "sleeve_selected_decisions": selected,
        "zero_selection_sleeve_diagnostics": [], "meaningful_execution": not empty,
        "canonical_admission": False, "independent_sleeve_pnl_observed": False}
    lines = []
    for index, day in enumerate(audit.VALUATIONS):
        nav = Fraction(100000 + (0 if empty else index * 10))
        cash = nav if empty else Fraction(90000)
        row = {"session": day, "nav": str(int(nav)), "cash": str(int(cash)),
            "gross_exposure": audit._text((nav - cash) / nav), "risk_within_unlevered_account": True,
            "max_name_exposure": "0" if empty else "0.01", "name_cap_is_prior_close_soft_target": True,
            "position_ledger_mismatches": 0, "cash_ledger_residual": "0", "nav_ledger_residual": "0"}
        lines.append("2025 synthetic MATCHED_NAV " + json.dumps(row))
    cats = ({"scored", "no_admissible_event", "unknown_input", "missing_identity", "ineligible", "unknown_weight", "zero_weight"}
            if arm == "tpr_on" else {"known_weight", "unknown_weight", "zero_weight"})
    for day in audit.DECISIONS:
        prior = date.fromisoformat(day) - timedelta(days=1)
        while prior.weekday() >= 5 or prior in audit.HOLIDAYS or prior == date(2025, 1, 1):
            prior -= timedelta(days=1)
        cutoff = datetime(prior.year, prior.month, prior.day, 18, tzinfo=audit.NY).astimezone(timezone.utc)
        reports = {}
        for etf in audit.ETFS:
            category = "scored" if arm == "tpr_on" else "known_weight"
            report = {key: {"count": int(key == category), "weight": "1" if key == category else "0"} for key in cats}
            report.update(membership_available=True, snapshot_hash="b" * 64, member_count=1, selected_count=1,
                effective_utc=(cutoff - timedelta(days=8)).isoformat(), received_utc=(cutoff - timedelta(days=1)).isoformat(), etf_fallback=False)
            reports[etf] = report
        lines.append("MATCHED_COVERAGE " + json.dumps({"session": day, "arm": arm, "sleeves": reports,
            "consolidated_selected_count": 6, "target_gross": "1" if arm == "etf_basket" else "0.1",
            "unallocated_target_cash": "0" if arm == "etf_basket" else "0.9"}))
    lines.append("MATCHED_SUMMARY " + json.dumps(summary))
    result = {"success": True, "backtest": {"backtestId": "c" * 32, "projectId": 123,
        "completed": True, "progress": 1, "status": "Completed", "error": None,
        "statistics": {"Total Orders": str(n), "Total Fees": "$" + audit._text(Fraction(n, 10)),
            "Start Equity": "100000", "End Equity": "100000" if empty else "100590"}}}
    filled = datetime(2025, 1, 2, 9, 30, tzinfo=audit.NY)
    order = {"id": 1, "status": 3, "type": 4, "priceAdjustmentMode": 0,
        "priceCurrency": "USD", "quantity": 10, "createdTime": "2025-01-02T14:20:00Z",
        "events": [{"orderId": 1, "orderEventId": 1, "status": "filled", "fillQuantity": 10,
            "fillPrice": "100", "fillPriceCurrency": "USD", "orderFeeAmount": "0.10",
            "orderFeeCurrency": "USD", "time": int(filled.timestamp())}]}
    orders = []
    for index in range(n):
        native = deepcopy(order)
        native["id"] = native["events"][0]["orderId"] = index + 1
        if arm == "etf_basket":
            native["events"][0]["symbolValue"] = audit.ETFS[index]
        orders.append(native)
    pages = [{"success": True, "start": 0, "end": 99, "length": n, "orders": orders}]
    receipt = {"candidate_id": policy["candidate_id"], "project_id": 123, "backtest_id": "c" * 32,
        "compile_id": "d" * 32, "config_sha256": digest(policy), "freeze_sha256": bundle.FREEZE_SHA256,
        "packet_sha256": bundle.PACKET_SHA256 if arm == "tpr_on" else None,
        "source_hashes": {name: "a" * 64 for name in audit.SOURCE_FILES}, "exact_cloud_readback": True, "build_success": True}
    return rebind([result, {"success": True, "logs": lines, "length": len(lines)}, pages, receipt, policy])


def change_log(args, prefix, change, *, occurrence=0):
    rows = args[1]["logs"]
    index = [i for i, line in enumerate(rows) if prefix in line][occurrence]
    row = json.loads(rows[index].split(prefix, 1)[1])
    change(row)
    rows[index] = prefix + json.dumps(row)
    return rebind(args)


def test_config_hash_matches_the_actual_bundle():
    package = ROOT / "research/target_price_revisions_qc"
    rendered = bundle.build_bundle((package / "matched_algorithm.py").read_bytes(),
        (package / "cloud_algorithm_v2.py").read_bytes(), (package / "matched_freeze.json").read_bytes(), max_file_size=64000)
    for case in rendered["cases"]:
        body = config(case["arm"], case["cost"])
        assert audit._config(body) == case["config_sha256"]


@pytest.mark.parametrize("arm,cost", [(arm, cost) for arm in ("tpr_on", "tpr_off", "etf_basket") for cost in ("baseline", "adverse")])
def test_meaningful_run_reconciles_without_echoing_native_identifiers(arm, cost):
    args = fixture(arm, cost)
    args[2][0]["orders"][0]["debug_private_field"] = "SYNTHETIC_PRIVATE_TICKER"
    rebind(args)
    result = audit.audit_result(*args)
    assert result["meaningful_execution"] is True and result["diagnostic_reasons"] == []
    n = 6 if arm == "etf_basket" else 1
    assert {key: value for key, value in result["orders"].items() if key != "etf_instrument_execution"} == {
        "orders": n, "filled_orders": n, "fill_events": n, "filled_shares": str(n * 10),
        "fees": audit._text(Fraction(n, 10)), "fill_notional": str(n * 1000), "order_failures": 0}
    assert result["requested_minus_submitted_shares"] == n * 2
    assert result["metrics"]["return_pct"] == "0.59"
    assert result["metrics"]["daily_return_observations"] == 60
    assert result["metrics"]["cagr_elapsed_calendar_days"] == 88
    assert result["metrics"]["annual_result_is_partial"] is True
    assert "SYNTHETIC_PRIVATE_TICKER" not in json.dumps(result)
    assert "orderEventId" not in json.dumps(result) and "independent_sleeve_pnl_observed" in result


def test_membership_snapshot_series_hash_matches_across_arms_and_detects_drift():
    first = audit.audit_result(*fixture("tpr_on"))
    control = audit.audit_result(*fixture("tpr_off"))
    assert all(first["coverage_by_sleeve"][etf]["membership_snapshot_sequence_sha256"] ==
        control["coverage_by_sleeve"][etf]["membership_snapshot_sequence_sha256"] for etf in audit.ETFS)
    changed = change_log(fixture("tpr_off"), "MATCHED_COVERAGE ",
        lambda row: row["sleeves"]["REMX"].update(snapshot_hash="f" * 64))
    drifted = audit.audit_result(*changed)
    assert drifted["meaningful_execution"] is True  # Valid run, unmatched input vintage.
    assert first["coverage_by_sleeve"]["REMX"]["membership_snapshot_sequence_sha256"] != \
        drifted["coverage_by_sleeve"]["REMX"]["membership_snapshot_sequence_sha256"]


def test_zero_orders_are_a_diagnostic_even_when_adapter_claims_success():
    args = change_log(fixture(empty=True), "MATCHED_SUMMARY ", lambda row: row.update(meaningful_execution=True))
    result = audit.audit_result(*args)
    assert result["meaningful_execution"] is False
    assert "zero_trade_diagnostic" in result["diagnostic_reasons"]
    assert result["metrics"]["sharpe_risk_free_zero"] is None


def test_fee_rule_survives_consistent_but_wrong_native_summary_statistics():
    args = fixture()
    assert audit.audit_result(*args)["meaningful_execution"] is True
    args[2][0]["orders"][0]["events"][0]["orderFeeAmount"] = "0"
    args[0]["backtest"]["statistics"]["Total Fees"] = "$0"
    change_log(args, "MATCHED_SUMMARY ", lambda row: row.update(fees="0"))
    rebind(args)
    result = audit.audit_result(*args)
    assert result["diagnostic_reasons"] == ["native_fee_schedule_mismatch"]
    assert result["meaningful_execution"] is False


def test_etf_account_fills_do_not_prove_all_six_instruments_traded():
    args = fixture("etf_basket")
    assert audit.audit_result(*args)["meaningful_execution"] is True
    args[2][0]["orders"].pop()
    args[2][0]["length"] = 5
    args[0]["backtest"]["statistics"].update({"Total Orders": "5", "Total Fees": "$0.50"})
    change_log(args, "MATCHED_SUMMARY ", lambda row: row.update(submitted_orders=5,
        fill_events=5, filled_shares=50, submitted_shares=50, requested_shares=60, fees="0.50"))
    rebind(args)
    result = audit.audit_result(*args)
    assert result["diagnostic_reasons"] == ["etf_basket_instrument_execution_incomplete"]
    assert result["orders"]["etf_instrument_execution"]["REMX"]["filled_orders"] == 0


def test_driver_consumes_structured_collection_and_persists_only_aggregate_audit():
    from research.target_price_revisions_qc import matched_driver
    args = fixture()
    class Controller:
        def __init__(self):
            self.saved = []
        def collect_terminal(self, candidate, attempt):
            assert candidate == args[4]["candidate_id"] and attempt == 1
            return {"completion": {"collection_errors": []}, "collection_round": 1,
                "receipt_prefix": candidate + ".attempt.1.collection.0001",
                **dict(zip(("result_response", "logs_response", "order_pages", "source_receipt", "candidate_config"), args))}
        def exclusive(self, name, body):
            self.saved.append((name, deepcopy(body)))
    controller = Controller()
    result = matched_driver.collect_and_audit(controller, args[4]["candidate_id"], 1)
    assert result["meaningful_execution"] is True
    assert controller.saved == [(args[4]["candidate_id"] + ".attempt.1.collection.0001.interpreted.json", result)]
    assert '"events":' not in json.dumps(result) and "fillPrice" not in json.dumps(result)


@pytest.mark.parametrize("mutate", [
    lambda args: args[0]["backtest"].update(backtestId="e" * 32),
    lambda args: args[3].update(candidate_id="TPR-MATCHED-OFF-BASE-v1"),
    lambda args: args[3].update(config_sha256="0" * 64),
    lambda args: args[3].update(packet_sha256=None),
    lambda args: args[4].update(slippage="0.0015"),
    lambda args: args[2][0].update(backtestId="e" * 32),
])
def test_foreign_run_arm_cost_or_hash_is_refused(mutate):
    args = fixture()
    mutate(args)
    rebind(args)
    with pytest.raises(audit.AuditError):
        audit.audit_result(*args)


def test_response_content_is_bound_before_parsing():
    args = fixture()
    args[0]["backtest"]["statistics"]["End Equity"] = "99999"
    with pytest.raises(audit.AuditError, match="mixed result"):
        audit.audit_result(*args)


@pytest.mark.parametrize("target", ["order", "event", "page", "missing_fee", "fractional_shares", "overflow_fill", "unknown_source"])
def test_duplicate_missing_or_unaccountable_native_evidence(target):
    args = fixture()
    order = args[2][0]["orders"][0]
    if target == "order":
        args[2][0]["orders"].append(deepcopy(order))
        args[2][0]["length"] = 2
    elif target == "event":
        order["events"].append(deepcopy(order["events"][0]))
    elif target == "page":
        args[2].append(deepcopy(args[2][0]))
    elif target == "missing_fee":
        del order["events"][0]["orderFeeAmount"]
    elif target == "fractional_shares":
        order["events"][0]["fillQuantity"] = "0.5"
    elif target == "overflow_fill":
        order["events"][0]["fillQuantity"] = 11
    else:
        args[3] = {}
    rebind(args)
    if target == "unknown_source":
        result = audit.audit_result(*args)
        assert result["meaningful_execution"] is False
        assert "source_verification_missing" in result["diagnostic_reasons"]
    else:
        with pytest.raises(audit.AuditError):
            audit.audit_result(*args)


@pytest.mark.parametrize("target", ["membership_clock", "partition", "summary_selected", "summary_cost", "wrong_day", "accounting", "gross", "equity", "fees_stats", "orders_stats"])
def test_time_membership_and_native_statistics_reconcile(target):
    args = fixture()
    if target == "membership_clock":
        change_log(args, "MATCHED_COVERAGE ", lambda row: row["sleeves"]["SPY"].update(received_utc="2025-01-02T14:30:00Z"))
    elif target == "partition":
        change_log(args, "MATCHED_COVERAGE ", lambda row: row["sleeves"]["SPY"].update(member_count=2))
    elif target == "summary_selected":
        change_log(args, "MATCHED_SUMMARY ", lambda row: row["sleeve_selected_decisions"].update(SPY=13))
    elif target == "summary_cost":
        change_log(args, "MATCHED_SUMMARY ", lambda row: row.update(cost="adverse"))
    elif target == "wrong_day":
        change_log(args, "MATCHED_NAV ", lambda row: row.update(session="2025-01-09"))
    elif target == "accounting":
        change_log(args, "MATCHED_NAV ", lambda row: row.update(cash_ledger_residual="0.02"))
    elif target == "gross":
        change_log(args, "MATCHED_NAV ", lambda row: row.update(gross_exposure="1.1"))
    elif target == "equity":
        args[0]["backtest"]["statistics"]["End Equity"] = "99999"
    elif target == "fees_stats":
        args[0]["backtest"]["statistics"]["Total Fees"] = "$1"
    else:
        args[0]["backtest"]["statistics"]["Total Orders"] = "2"
    rebind(args)
    if target == "summary_cost":
        with pytest.raises(audit.AuditError, match="summary identity"):
            audit.audit_result(*args)
    else:
        result = audit.audit_result(*args)
        assert result["meaningful_execution"] is False and result["diagnostic_reasons"]


@pytest.mark.parametrize("target", ["nav_duplicate", "coverage_duplicate", "summary_duplicate", "json_duplicate"])
def test_duplicate_log_evidence_is_refused(target):
    args = fixture()
    prefix = {"nav_duplicate": "MATCHED_NAV ", "coverage_duplicate": "MATCHED_COVERAGE ", "summary_duplicate": "MATCHED_SUMMARY "}.get(target)
    if prefix:
        args[1]["logs"].append(next(line for line in args[1]["logs"] if prefix in line))
    else:
        args[1]["logs"].append('MATCHED_SUMMARY {"study_id":"x","study_id":"y"}')
    args[1]["length"] = len(args[1]["logs"])
    rebind(args)
    with pytest.raises(audit.AuditError):
        audit.audit_result(*args)


@pytest.mark.parametrize("target", ["native_nan", "summary_count", "fees", "currency", "type", "mode", "late_fill", "canceled", "loading", "missing_nav", "missing_coverage", "failed_terminal", "unknown_source"])
def test_meaningful_flag_cannot_hide_bad_or_missing_evidence(target):
    args = fixture()
    order = args[2][0]["orders"][0]
    event = order["events"][0]
    if target == "native_nan":
        event["fillPrice"] = "NaN"
    elif target == "summary_count":
        change_log(args, "MATCHED_SUMMARY ", lambda row: row.update(submitted_orders=2))
    elif target == "fees":
        event["orderFeeAmount"] = "0"
    elif target == "currency":
        event["orderFeeCurrency"] = "EUR"
    elif target == "type":
        order["type"] = 0
    elif target == "mode":
        order["priceAdjustmentMode"] = 1
    elif target == "late_fill":
        event["time"] += 300
    elif target == "canceled":
        order["status"] = 5
    elif target == "loading":
        args[2][0]["loading"] = True
    elif target in ("missing_nav", "missing_coverage"):
        prefix = "MATCHED_NAV " if target == "missing_nav" else "MATCHED_COVERAGE "
        index = next(i for i, line in enumerate(args[1]["logs"]) if prefix in line)
        args[1]["logs"].pop(index)
        args[1]["length"] -= 1
    elif target == "failed_terminal":
        args[0]["backtest"].update(completed=False, error="Synthetic runtime error", status="Runtime Error")
    else:
        args[3]["source_hashes"] = {"main.py": "SYNTHETIC_PRIVATE_SOURCE"}
    rebind(args)
    if target == "native_nan":
        with pytest.raises(audit.AuditError, match="nonfinite"):
            audit.audit_result(*args)
    else:
        result = audit.audit_result(*args)
        assert result["meaningful_execution"] is False and result["diagnostic_reasons"]
        assert "SYNTHETIC_PRIVATE_SOURCE" not in json.dumps(result)


def test_missing_etf_membership_context_is_not_fabricated_or_a_trade_blocker():
    args = fixture("etf_basket")
    def unavailable(row):
        row["sleeves"]["REMX"] = {"membership_available": False, "snapshot_hash": None,
            "member_count": None, "selected_count": 1, "effective_utc": None, "received_utc": None, "etf_fallback": False}
    for index in range(14):
        change_log(args, "MATCHED_COVERAGE ", unavailable, occurrence=index)
    result = audit.audit_result(*args)
    remx = result["coverage_by_sleeve"]["REMX"]
    assert result["meaningful_execution"] is True
    assert remx["unavailable_membership_decisions"] == 14 and remx["members_min_max"] is None
    assert remx["state_counts"] == {} and remx["state_weights"] == {}


def test_empty_inputs_do_not_manufacture_zero_coverage_or_success():
    policy = config()
    result = audit.audit_result({"success": False}, {"success": False}, [], {}, policy)
    assert result["meaningful_execution"] is False and result["metrics"] is None
    assert result["orders"]["orders"] is None
    assert all(value is None for value in result["coverage_by_sleeve"].values())


def test_audit_has_no_io(monkeypatch):
    args = fixture()
    import builtins
    import socket
    def forbidden(*_args, **_kwargs):
        pytest.fail("pure audit performed I/O")
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    assert audit.audit_result(*args)["meaningful_execution"] is True
