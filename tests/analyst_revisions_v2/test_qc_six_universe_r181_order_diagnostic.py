"""Offline, synthetic checks for R181 A2's one-use redacted order diagnosis."""

from __future__ import annotations

import json
import hashlib
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc import six_universe_r181_order_diagnostic as d


def _record(directory: Path, name: str, value: dict) -> None:
    raw = d._canonical(value)
    fd = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, raw)
    finally:
        os.close(fd)


@pytest.fixture
def controls(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    _record(directory, "R181-A2-claim.json", {
        "candidate_id": "R181", "attempt": 2, "role": "signal",
        "project_id": d._PROJECT_ID,
        "projection_sha256": d._PROJECTION_SHA256,
        "profile_sha256": d._PROFILE_SHA256,
        "profile_id": "pinned-profile",
        "source_files": [[f"module_{index}.py", "0" * 64, 1] for index in range(13)],
    })
    _record(directory, "R181-A2-launch.json", {
        "candidate_id": "R181", "attempt": 2, "role": "signal",
        "project_id": d._PROJECT_ID, "project_name": d._PROJECT_NAME,
        "backtest_id": d._BACKTEST_ID, "backtest_name": d._BACKTEST_NAME,
        "projection_sha256": d._PROJECTION_SHA256,
        "profile_sha256": d._PROFILE_SHA256, "profile_id": "pinned-profile",
    })
    _record(directory, "R181-A2-terminal.json", {
        "candidate_id": "R181", "status": "Completed.",
        "project_id": d._PROJECT_ID, "backtest_id": d._BACKTEST_ID,
    })
    _record(directory, "R181-A2-result-read-claim.json", {
        "candidate_id": "R181", "project_id": d._PROJECT_ID,
        "backtest_id": d._BACKTEST_ID,
    })
    return directory


def _orders(*, message="Insufficient buying power for SECRET_SYMBOL at $987.65"):
    return [
        {
            "id": index, "status": 7 if index < 22 else 3,
            "events": [{"status": "Invalid", "message": message}] if index < 22 else [],
            "symbol": "SECRET_SYMBOL", "price": 987.65,
        }
        for index in range(d._EXPECTED_ORDER_COUNT)
    ]


class _OfflineQc:
    def __init__(self, rows, *, inclusive=False):
        self.rows = rows
        self.inclusive = inclusive
        self.calls = []

    def request(self, path, payload):
        assert path == "backtests/orders/read"
        assert payload["projectId"] == d._PROJECT_ID
        assert payload["backtestId"] == d._BACKTEST_ID
        assert payload["end"] - payload["start"] < 100
        self.calls.append(payload.copy())
        end = payload["end"] + int(self.inclusive)
        page = self.rows[payload["start"]:end]
        return {"success": True, "orders": page, "length": len(page)}


@pytest.mark.parametrize("inclusive", [False, True])
def test_redacts_all_order_fields_and_handles_either_page_boundary(
    monkeypatch, controls, inclusive,
):
    client = _OfflineQc(_orders(), inclusive=inclusive)
    monkeypatch.setattr(d, "production_client", lambda: client)
    result = d.diagnose_r181_a2_rejections(
        owner_authorized=True, control_directory=controls,
    )
    assert len(client.calls) == (63 if inclusive else 64)
    assert result["filled_order_count"] == 6267
    assert result["invalid_order_count"] == 22
    assert result["reason_counts"]["INSUFFICIENT_BUYING_POWER"] == 22
    raw = (controls / d._RESULT_NAME).read_text("ascii")
    assert json.loads(raw) == result
    for forbidden in ("SECRET_SYMBOL", "987.65", "a74626d4", "36891750"):
        assert forbidden not in raw
    assert (controls / d._CLAIM_NAME).is_file()
    assert json.loads((controls / d._CLAIM_NAME).read_text("ascii"))["maximum_endpoint_calls"] == 64


def test_explicit_owner_authority_refuses_before_claim_or_client(monkeypatch, controls):
    monkeypatch.setattr(d, "production_client", lambda: pytest.fail("unexpected client"))
    with pytest.raises(d.R181OrderDiagnosticError):
        d.diagnose_r181_a2_rejections(owner_authorized=False, control_directory=controls)
    assert not (controls / d._CLAIM_NAME).exists()


def test_changed_launch_receipt_refuses_before_claim_or_client(monkeypatch, controls):
    path = controls / "R181-A2-launch.json"
    content = json.loads(path.read_text("ascii"))
    content["backtest_id"] = "wrong"
    path.write_bytes(d._canonical(content))
    monkeypatch.setattr(d, "production_client", lambda: pytest.fail("unexpected client"))
    with pytest.raises(d.R181OrderDiagnosticError):
        d.diagnose_r181_a2_rejections(owner_authorized=True, control_directory=controls)
    assert not (controls / d._CLAIM_NAME).exists()


def test_unknown_order_message_stays_redacted_and_spends_claim(monkeypatch, controls):
    marker = "SECRET_SYMBOL-PRIVATE-ERROR-123"
    rows = _orders(message=marker)
    client = _OfflineQc(rows)
    monkeypatch.setattr(d, "production_client", lambda: client)
    result = d.diagnose_r181_a2_rejections(owner_authorized=True, control_directory=controls)
    assert result["reason_counts"]["OTHER_REDACTED"] == 22
    assert marker not in repr(result)
    assert marker not in (controls / d._RESULT_NAME).read_text("ascii")
    with pytest.raises(d.R181OrderDiagnosticError):
        d.diagnose_r181_a2_rejections(owner_authorized=True, control_directory=controls)
    assert len(client.calls) == 64


def test_missing_invalid_event_message_fails_closed_after_claim(monkeypatch, controls):
    rows = _orders()
    rows[0]["events"] = [{"status": "Invalid"}]
    client = _OfflineQc(rows)
    monkeypatch.setattr(d, "production_client", lambda: client)
    with pytest.raises(d.R181OrderDiagnosticError) as exc:
        d.diagnose_r181_a2_rejections(owner_authorized=True, control_directory=controls)
    assert "SECRET_SYMBOL" not in str(exc.value)
    assert (controls / d._CLAIM_NAME).exists()
    assert not (controls / d._RESULT_NAME).exists()
    assert len(client.calls) == 1


def test_hostile_qc_exception_is_absent_from_formatted_traceback(monkeypatch, controls):
    marker = "PRIVATE_QC_ORDER_MESSAGE_SECRET_98765"

    class _HostileQc:
        def request(self, _path, _payload):
            raise RuntimeError(marker)

    monkeypatch.setattr(d, "production_client", _HostileQc)
    with pytest.raises(d.R181OrderDiagnosticError) as exc:
        d.diagnose_r181_a2_rejections(owner_authorized=True, control_directory=controls)
    assert marker not in "".join(traceback.format_exception(exc.value))
    assert (controls / d._CLAIM_NAME).exists()


def test_census_mismatch_fails_closed_after_claim(monkeypatch, controls):
    rows = _orders()
    rows[22]["status"] = 7
    rows[22]["events"] = [{"status": "Invalid", "message": "Insufficient buying power"}]
    client = _OfflineQc(rows)
    monkeypatch.setattr(d, "production_client", lambda: client)
    with pytest.raises(d.R181OrderDiagnosticError):
        d.diagnose_r181_a2_rejections(owner_authorized=True, control_directory=controls)
    assert (controls / d._CLAIM_NAME).exists()
    assert not (controls / d._RESULT_NAME).exists()


def test_versioned_schema_probe_retains_only_shape_after_spent_v1_claim(
    monkeypatch, controls,
):
    directory_fd = d._open_private_directory(controls)
    try:
        receipt_digests = d._verify_a2_receipts(directory_fd)
    finally:
        os.close(directory_fd)
    _record(controls, d._CLAIM_NAME, {
        "schema": "arv2-r181-a2-order-diagnostic-claim-v1",
        "project_id": d._PROJECT_ID,
        "backtest_id": d._BACKTEST_ID,
        "receipt_sha256": receipt_digests,
    })
    marker = "PRIVATE_ORDER_SECRET_98765"
    calls = []

    class _ShapeOnlyQc:
        def request(self, path, payload):
            calls.append((path, payload.copy()))
            return {
                "success": True,
                "orders": {"private-order-id": {"symbol": marker}},
                "length": 6289,
            }

    monkeypatch.setattr(d, "production_client", _ShapeOnlyQc)
    result = d.probe_r181_a2_order_page_schema(
        owner_authorized=True, control_directory=controls,
    )
    assert result == {
        "schema": "arv2-r181-a2-order-page-shape-v2",
        "orders_container": "dict",
        "orders_count": 1,
        "first_order_value_is_object": True,
        "length_is_integer": True,
        "length_value": 6289,
    }
    assert len(calls) == 1
    assert calls[0][0] == "backtests/orders/read"
    assert calls[0][1]["end"] - calls[0][1]["start"] < 100
    stored = (controls / d._SCHEMA_PROBE_RESULT_NAME).read_text("ascii")
    assert marker not in stored
    assert "private-order-id" not in stored
    with pytest.raises(d.R181OrderDiagnosticError):
        d.probe_r181_a2_order_page_schema(
            owner_authorized=True, control_directory=controls,
        )
    assert len(calls) == 1


def test_final_shape_tree_probe_hashes_keys_and_discards_values(
    monkeypatch, controls,
):
    _record(controls, d._SCHEMA_PROBE_RESULT_NAME, {
        "schema": "arv2-r181-a2-order-page-shape-v2",
        "orders_container": "missing_or_null",
    })
    marker = "PRIVATE_SYMBOL_AND_ORDER_VALUE"
    calls = []

    class _WrappedQc:
        def request(self, path, payload):
            calls.append((path, payload.copy()))
            return {"success": True, "payload": {
                "backtestOrders": [{"symbol": marker, "message": marker}],
                "orderCount": 6289,
            }}

    monkeypatch.setattr(d, "production_client", _WrappedQc)
    result = d.probe_r181_a2_order_shape_tree(
        owner_authorized=True, control_directory=controls,
    )
    stored = (controls / d._SHAPE_TREE_RESULT_NAME).read_text("ascii")
    assert marker not in stored
    assert "payload" not in stored
    assert "backtestOrders" not in stored
    root_hashes = {
        item["key_sha256"] for item in result["response_shape"]["members"]
    }
    assert hashlib.sha256(b"payload").hexdigest() in root_hashes
    assert len(calls) == 1
    with pytest.raises(d.R181OrderDiagnosticError):
        d.probe_r181_a2_order_shape_tree(
            owner_authorized=True, control_directory=controls,
        )
    assert len(calls) == 1


def test_v4_diagnosis_recovers_one_missing_shape_and_reconciles_all_orders(
    monkeypatch, controls,
):
    _record(controls, d._SHAPE_TREE_RESULT_NAME, {
        "schema": "arv2-r181-a2-order-shape-tree-v3",
        "response_shape": d._shape_tree({
            "success": True,
            "orders": [{"id": 1}],
            "length": 99,
        }),
    })

    class _TransientQc(_OfflineQc):
        def request(self, path, payload):
            if not self.calls:
                self.calls.append(payload.copy())
                return {"success": True}
            result = super().request(path, payload)
            result["length"] = d._EXPECTED_ORDER_COUNT
            return result

    client = _TransientQc(_orders())
    monkeypatch.setattr(d, "production_client", lambda: client)
    result = d.diagnose_r181_a2_rejections_v4(
        owner_authorized=True, control_directory=controls,
    )
    assert result["invalid_order_count"] == 22
    assert result["reason_counts"]["INSUFFICIENT_BUYING_POWER"] == 22
    assert result["transient_shape_retry_count"] == 1
    assert result["length_mode"] == "total"
    assert result["endpoint_call_count"] == 65
    assert len(client.calls) == 65
    stored = (controls / d._RECOVERY_RESULT_NAME).read_text("ascii")
    assert "SECRET_SYMBOL" not in stored
    assert "987.65" not in stored
    with pytest.raises(d.R181OrderDiagnosticError):
        d.diagnose_r181_a2_rejections_v4(
            owner_authorized=True, control_directory=controls,
        )
    assert len(client.calls) == 65


def _seed_successful_v4(controls):
    directory_fd = d._open_private_directory(controls)
    try:
        receipts = d._verify_a2_receipts(directory_fd)
    finally:
        os.close(directory_fd)
    shape = {
        "schema": "arv2-r181-a2-order-shape-tree-v3",
        "response_shape": d._shape_tree({
            "success": True, "orders": [{"id": 1}], "length": 99,
        }),
    }
    _record(controls, d._SHAPE_TREE_RESULT_NAME, shape)
    _record(controls, d._RECOVERY_CLAIM_NAME, {
        "schema": "arv2-r181-a2-redacted-order-recovery-v4-claim-v1",
        "project_id": d._PROJECT_ID, "backtest_id": d._BACKTEST_ID,
        "profile_sha256": d._PROFILE_SHA256,
        "aggregate_sha256": d._AGGREGATE_SHA256,
        "previous_shape_sha256": hashlib.sha256(d._canonical(shape)).hexdigest(),
        "receipt_sha256": receipts,
        "maximum_endpoint_calls": d._MAXIMUM_PAGE_COUNT + 2,
        "maximum_missing_shape_retries": 2,
        "raw_order_values_retained": False,
    })
    result = {
        "schema": "arv2-r181-a2-redacted-order-reasons-v4",
        "filled_order_count": d._EXPECTED_FILLED_COUNT,
        "invalid_order_count": d._EXPECTED_INVALID_COUNT,
        "reason_counts": {
            name: d._EXPECTED_INVALID_COUNT
            if name == "INSUFFICIENT_BUYING_POWER" else 0
            for name in d._REASONS
        },
        "transient_shape_retry_count": 1,
        "length_mode": "total", "endpoint_call_count": 65,
    }
    _record(controls, d._RECOVERY_RESULT_NAME, result)


def _timed_orders():
    rows = _orders()
    for index in range(d._EXPECTED_INVALID_COUNT):
        rows[index]["direction"] = 0
        rows[index]["events"][0]["direction"] = "buy"
        rows[index]["events"][0]["time"] = (
            "2025-01-03T14:20:00Z" if index < 11
            else "2025-01-03T14:31:00Z"
        )
    rows[0]["events"][0]["time"] = float(datetime(
        2025, 1, 3, 14, 20, tzinfo=timezone.utc,
    ).timestamp())
    rows[11]["events"][0]["time"] = float(datetime(
        2025, 1, 3, 14, 31, tzinfo=timezone.utc,
    ).timestamp() * 1000)
    return rows


def test_v5_retains_only_buying_power_side_and_open_time_bins(
    monkeypatch, controls,
):
    _seed_successful_v4(controls)
    client = _OfflineQc(_timed_orders())
    monkeypatch.setattr(d, "production_client", lambda: client)
    result = d.diagnose_r181_a2_buying_power_timing_v5(
        owner_authorized=True, control_directory=controls,
    )
    assert result == {
        "schema": "arv2-r181-a2-buying-power-timing-v5",
        "filled_order_count": 6267, "invalid_order_count": 22,
        "direction_counts": {"BUY": 22, "SELL": 0, "UNKNOWN": 0},
        "time_bin_counts": {
            "PRE_OPEN": 11, "AT_OR_AFTER_OPEN": 11, "UNKNOWN": 0,
        },
        "transient_shape_retry_count": 0,
        "length_mode": "page", "endpoint_call_count": 64,
    }
    stored = (controls / d._TIMING_RESULT_NAME).read_text("ascii")
    assert json.loads(stored) == result
    for forbidden in (
        "SECRET_SYMBOL", "987.65", "2025-01-03", d._BACKTEST_ID,
        str(d._PROJECT_ID), '"symbol"', '"message"', '"order_id"',
    ):
        assert forbidden not in stored
    claim = json.loads((controls / d._TIMING_CLAIM_NAME).read_text("ascii"))
    assert claim["maximum_pages"] == 64
    assert claim["v4_result_sha256"] == hashlib.sha256(
        (controls / d._RECOVERY_RESULT_NAME).read_bytes()
    ).hexdigest()
    assert claim["numeric_shortfall_parsed"] is False
    with pytest.raises(d.R181OrderDiagnosticError):
        d.diagnose_r181_a2_buying_power_timing_v5(
            owner_authorized=True, control_directory=controls,
        )
    assert len(client.calls) == 64


def test_v5_unpinned_time_is_unknown_and_direction_can_be_sell(
    monkeypatch, controls,
):
    _seed_successful_v4(controls)
    rows = _timed_orders()
    rows[0]["direction"] = 1
    rows[0]["events"][0]["direction"] = "sell"
    rows[0]["events"][0]["time"] = "UNTRUSTED_TIME_SECRET"
    rows[1]["events"][0]["time"] = 1_735_911_600  # UTC epoch seconds.
    client = _OfflineQc(rows, inclusive=True)
    monkeypatch.setattr(d, "production_client", lambda: client)
    result = d.diagnose_r181_a2_buying_power_timing_v5(
        owner_authorized=True, control_directory=controls,
    )
    assert result["direction_counts"] == {"BUY": 21, "SELL": 1, "UNKNOWN": 0}
    assert result["time_bin_counts"]["UNKNOWN"] == 1
    assert "UNTRUSTED_TIME_SECRET" not in repr(result)
    assert len(client.calls) == 63


def test_v5_numeric_event_time_never_labels_nonfinite_or_out_of_window():
    assert d._time_bin(float("nan")) == "UNKNOWN"
    assert d._time_bin(float("inf")) == "UNKNOWN"
    assert d._time_bin(True) == "UNKNOWN"
    assert d._time_bin(0) == "UNKNOWN"
    assert d._time_bin("PRIVATE_TIMESTAMP") == "UNKNOWN"


def test_v5_changed_v4_result_refuses_before_claim_or_network(
    monkeypatch, controls,
):
    _seed_successful_v4(controls)
    path = controls / d._RECOVERY_RESULT_NAME
    result = json.loads(path.read_text("ascii"))
    result["reason_counts"]["INSUFFICIENT_BUYING_POWER"] = 21
    path.write_bytes(d._canonical(result))
    monkeypatch.setattr(d, "production_client", lambda: pytest.fail("unexpected client"))
    with pytest.raises(d.R181OrderDiagnosticError):
        d.diagnose_r181_a2_buying_power_timing_v5(
            owner_authorized=True, control_directory=controls,
        )
    assert not (controls / d._TIMING_CLAIM_NAME).exists()


def test_v5_conflicting_direction_refuses_without_raw_traceback(
    monkeypatch, controls,
):
    _seed_successful_v4(controls)
    rows = _timed_orders()
    rows[0]["events"][0]["direction"] = "sell"
    marker = "PRIVATE_QC_ORDER_MESSAGE_SECRET_98765"
    rows[0]["events"][0]["message"] = marker
    client = _OfflineQc(rows)
    monkeypatch.setattr(d, "production_client", lambda: client)
    with pytest.raises(d.R181OrderDiagnosticError) as exc:
        d.diagnose_r181_a2_buying_power_timing_v5(
            owner_authorized=True, control_directory=controls,
        )
    assert marker not in "".join(traceback.format_exception(exc.value))
    assert (controls / d._TIMING_CLAIM_NAME).exists()
    assert not (controls / d._TIMING_RESULT_NAME).exists()
    assert len(client.calls) == 1
