"""Synthetic pre-backtest contracts; no admitted source or outcome is read."""
from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError

import pytest

from research.target_price_revisions_development import readiness as ready


def raw_spec(**changes):
    body = {
        "schema": "tpr-synthetic-run-spec-v1",
        "run_id": "SYNTHETIC-RUN-A",
        "target": "synthetic-local-order-based",
        "created_at_utc": "2026-10-06T00:00:00+00:00",
        "expires_at_utc": "2026-10-12T00:00:00+00:00",
        "lineage": {key: str(index) * 64 for index, key in enumerate(
            ("candidate_sha256", "code_sha256", "data_sha256", "config_sha256", "fold_sha256"), 1)},
        "plan_sha256": ready.D0_PLAN_SHA256,
        "d0_report_sha256": ready.D0_REPORT_SHA256,
        "synthetic_outcome_window": {"start": "2020-01-01", "end": "2020-12-31"},
        "accepted_risks": list(ready.REQUIRED_RISKS),
        "authority": {key: False for key in ready.AUTHORITY_KEYS},
        "d0_audit": "spent-not-renewable",
        "evaluation_policy": {"mode": "order-based", "max_qc_attempts": 3,
                              "after_three_unsuccessful": "mia-recovery-required"},
    }
    body.update(changes)
    return body


def spec(**changes):
    return ready.freeze_fixture_run_spec(raw_spec(**changes))


def reserve(run, ledger=(), number=1, clock=None):
    return ready.reserve_fixture_attempt(
        run, ledger, attempt_id=f"SYNTHETIC-ATTEMPT-{number}",
        at_utc=clock or f"2026-10-06T00:{number:02}:00+00:00",
        expected_head_sha256=ready.ledger_head(ledger),
    )


def close(ledger, number=1, status="failed", clock=None):
    return ready.close_fixture_attempt(
        ledger, attempt_id=f"SYNTHETIC-ATTEMPT-{number}", status=status,
        at_utc=clock or f"2026-10-06T00:{number:02}:01+00:00",
        expected_head_sha256=ready.ledger_head(ledger),
    )


def rehashed_receipt(receipt, edit):
    body = json.loads(receipt.payload)
    edit(body)
    payload = (json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n").encode()
    return ready.FixtureReceipt(payload, hashlib.sha256(payload).hexdigest())


def test_run_spec_is_detached_content_addressed_and_zero_authority():
    raw = raw_spec()
    frozen = ready.freeze_fixture_run_spec(raw)
    assert frozen.sha256 == hashlib.sha256(frozen.payload).hexdigest()
    assert frozen.payload.endswith(b"\n") and frozen.payload.count(b"\n") == 1
    raw["authority"]["qc"] = True
    raw["lineage"]["code_sha256"] = "9" * 64
    assert json.loads(frozen.payload)["authority"]["qc"] is False
    with pytest.raises(FrozenInstanceError):
        frozen.payload = b"modified"


@pytest.mark.parametrize("edit", [
    lambda b: b.update(extra=True), lambda b: b.update(run_id="REAL-RUN"),
    lambda b: b["authority"].update(qc=True), lambda b: b["authority"].update(outcomes=0),
    lambda b: b.update(d0_audit="renewed"), lambda b: b.update(plan_sha256="9" * 64),
    lambda b: b.update(d0_report_sha256="9" * 64),
    lambda b: b["evaluation_policy"].update(max_qc_attempts=True),
    lambda b: b["evaluation_policy"].update(max_qc_attempts=4),
    lambda b: b["evaluation_policy"].update(mode="vectorized-return-study"),
    lambda b: b["lineage"].update(entitled=True),
    lambda b: b["lineage"].update(code_sha256="A" * 64),
    lambda b: b["accepted_risks"].pop(),
    lambda b: b.update(created_at_utc="2026-10-06T00:00:00"),
    lambda b: b.update(expires_at_utc="2026-10-05T00:00:00Z"),
    lambda b: b["synthetic_outcome_window"].update(end="2029-09-01"),
])
def test_rehashing_spec_cannot_widen_contract(edit):
    raw = raw_spec()
    edit(raw)
    with pytest.raises(ready.ReadinessError):
        ready.freeze_fixture_run_spec(raw)


def test_forged_all_true_inventory_never_grants_real_readiness():
    inventory = tuple({"requirement_id": requirement, "fixture_id": "SYNTHETIC-EVIDENCE",
                       "fixture_sha256": "7" * 64} for requirement in ready.REQUIREMENTS)
    report = ready.evaluate_fixture_readiness(spec(), inventory,
                                             as_of_utc="2026-10-06T00:00:00Z")
    assert report.real_backtest_ready is False and report.independent_review_required is True
    assert len(report.requirements) == len(ready.REQUIREMENTS)
    assert all(item.status == "synthetic-not-admission" for item in report.requirements)
    assert all("synthetic_not_admitted:" + item in report.blockers for item in ready.REQUIREMENTS)
    assert "owner_scope_for_data_outcomes_qc_missing" in report.blockers
    assert report.authority == tuple((key, False) for key in ready.AUTHORITY_KEYS)
    forged = dict(inventory[0], entitled=True, reviewed=True, point_in_time_data=True)
    with pytest.raises(ready.ReadinessError, match="inventory"):
        ready.evaluate_fixture_readiness(spec(), (forged,), as_of_utc="2026-10-06T00:00:00Z")


def test_empty_inventory_reports_every_named_missing_requirement():
    report = ready.evaluate_fixture_readiness(spec(), (), as_of_utc="2026-10-06T00:00:00Z")
    assert tuple(item.requirement_id for item in report.requirements) == ready.REQUIREMENTS
    assert all(item.status == "missing" for item in report.requirements)
    assert all("missing:" + item in report.blockers for item in ready.REQUIREMENTS)
    assert "spent_d0_audit_not_renewable" in report.blockers


@pytest.mark.parametrize("inventory", [
    ({"requirement_id": "unknown", "fixture_id": "SYNTHETIC-X", "fixture_sha256": "a" * 64},),
    ({"requirement_id": "reviewed_candidate", "fixture_id": "actual-agreement", "fixture_sha256": "a" * 64},),
    ({"requirement_id": "reviewed_candidate", "fixture_id": "SYNTHETIC-X", "fixture_sha256": True},),
])
def test_non_fixture_or_unbounded_inventory_is_refused(inventory):
    with pytest.raises(ready.ReadinessError):
        ready.evaluate_fixture_readiness(spec(), inventory, as_of_utc="2026-10-06T00:00:00Z")


def test_expired_spec_has_named_blocker_and_cannot_reserve():
    run = spec()
    report = ready.evaluate_fixture_readiness(run, (), as_of_utc="2026-10-13T00:00:00Z")
    assert "run_spec_not_current" in report.blockers
    with pytest.raises(ready.ReadinessError, match="current"):
        reserve(run, clock="2026-10-13T00:00:00Z")


def test_reservation_and_terminal_append_without_overwriting_prefix():
    run = spec()
    initial = reserve(run)
    finished = close(initial)
    retry = reserve(run, finished, 2)
    assert finished[:-1] == initial and retry[:-1] == finished
    assert sum(json.loads(item.payload)["kind"] == "reservation" for item in retry) == 2
    assert ready.load_fixture_ledger(retry, expected_head_sha256=ready.ledger_head(retry)) == retry
    assert json.loads(initial[0].payload)["run_spec"] == json.loads(run.payload)
    assert json.loads(initial[0].payload)["run_spec_sha256"] == run.sha256
    assert json.loads(finished[-1].payload)["reservation_sha256"] == initial[0].sha256


@pytest.mark.parametrize("status", ["completed", "failed", "interrupted"])
def test_every_terminal_kind_retains_consumed_reservation(status):
    initial = reserve(spec())
    finished = close(initial, status=status)
    assert finished[0] == initial[0] and len(finished) == 2
    assert json.loads(finished[-1].payload)["status"] == status


def test_retry_requires_new_attempt_and_terminal_cannot_be_replaced():
    initial = reserve(spec())
    with pytest.raises(ready.ReadinessError, match="pending"):
        reserve(spec(), initial, 2)
    finished = close(initial)
    with pytest.raises(ready.ReadinessError, match="attempt"):
        reserve(spec(), finished, clock="2026-10-06T00:02:00Z")
    with pytest.raises(ready.ReadinessError, match="terminal"):
        close(finished, status="completed", clock="2026-10-06T00:02:01Z")
    with pytest.raises(ready.ReadinessError, match="reservation"):
        close((), number=7)


def test_dropping_history_or_using_stale_head_refuses():
    history = close(reserve(spec()))
    head = ready.ledger_head(history)
    with pytest.raises(ready.ReadinessError, match="checkpoint"):
        ready.load_fixture_ledger(history[:-1], expected_head_sha256=head)
    with pytest.raises(ready.ReadinessError, match="checkpoint"):
        ready.reserve_fixture_attempt(spec(), (), attempt_id="SYNTHETIC-RETRY", at_utc="2026-10-06T00:02:00Z",
                                      expected_head_sha256=head)


@pytest.mark.parametrize("edit", [
    lambda b: b.update(sequence=True), lambda b: b.update(sequence=2),
    lambda b: b.update(previous_sha256="9" * 64),
    lambda b: b.update(attempt_ordinal=2),
    lambda b: b.update(run_spec_sha256="9" * 64),
    lambda b: b.update(extra="replacement"),
    lambda b: b["run_spec"]["authority"].update(outcomes=True),
])
def test_rehashed_receipt_cannot_forge_history_or_lineage(edit):
    original = reserve(spec())[0]
    mutated = rehashed_receipt(original, edit)
    with pytest.raises(ready.ReadinessError):
        ready.load_fixture_ledger((mutated,), expected_head_sha256=mutated.sha256)


def test_changed_terminal_parent_and_backward_clocks_refuse():
    initial = reserve(spec())
    terminal = close(initial)[-1]
    wrong = rehashed_receipt(terminal, lambda b: b.update(reservation_sha256="9" * 64))
    with pytest.raises(ready.ReadinessError, match="reservation"):
        ready.load_fixture_ledger(initial + (wrong,), expected_head_sha256=wrong.sha256)
    with pytest.raises(ready.ReadinessError, match="clock"):
        close(initial, clock="2026-10-06T00:00:00Z")


def test_qc_attempt_cap_survives_run_spec_changes_and_mia_is_metadata_only():
    run = spec(target="synthetic-qc-order-based")
    ledger = ()
    for number in range(1, 4):
        candidate = spec(target="synthetic-qc-order-based", run_id=f"SYNTHETIC-RUN-{number}")
        ledger = close(reserve(candidate, ledger, number), number, status="interrupted")
    report = ready.evaluate_fixture_readiness(run, (), ledger, as_of_utc="2026-10-06T00:04:00Z")
    assert report.mia_recovery_required is True
    assert report.real_backtest_ready is False
    with pytest.raises(ready.ReadinessError, match="three"):
        reserve(run, ledger, 4)


def test_local_fixture_attempts_do_not_count_as_actual_qc_or_outcome_access():
    ledger = ()
    run = spec()
    for number in range(1, 5):
        ledger = close(reserve(run, ledger, number), number)
    report = ready.evaluate_fixture_readiness(run, (), ledger, as_of_utc="2026-10-06T00:05:00Z")
    assert report.mia_recovery_required is False
    assert report.actual_qc_attempts == report.actual_outcome_reads == 0


def test_hash_mismatch_is_checked_before_json_parse(monkeypatch):
    run = ready.FrozenFixtureRunSpec(b"not-json", "0" * 64)
    monkeypatch.setattr(ready, "_parse", lambda _: pytest.fail("unverified bytes parsed"))
    with pytest.raises(ready.ReadinessError, match="digest"):
        ready.evaluate_fixture_readiness(run, (), as_of_utc="2026-10-06T00:00:00Z")


def test_future_terminal_cannot_inform_an_earlier_readiness_assessment():
    history = close(reserve(spec()))
    with pytest.raises(ready.ReadinessError, match="assessment clock"):
        ready.evaluate_fixture_readiness(spec(), (), history, as_of_utc="2026-10-06T00:00:00Z")


def test_dossier_content_address_binds_exact_inventory_and_ledger_context():
    inventory = ({"requirement_id": "reviewed_candidate", "fixture_id": "SYNTHETIC-EVIDENCE",
                  "fixture_sha256": "6" * 64},)
    run = spec()
    history = close(reserve(run))
    report = ready.evaluate_fixture_readiness(run, inventory, history, as_of_utc="2026-10-06T00:02:00Z")
    assert report.sha256 == hashlib.sha256(report.payload).hexdigest()
    body = json.loads(report.payload)
    assert body["ledger_head_sha256"] == ready.ledger_head(history)
    assert body["run_spec_sha256"] == run.sha256
    assert body["inventory"][0]["fixture_sha256"] == "6" * 64
    assert body["real_backtest_ready"] is False and all(v is False for v in body["authority"].values())
    changed = (dict(inventory[0], fixture_sha256="7" * 64),)
    another = ready.evaluate_fixture_readiness(run, changed, history, as_of_utc="2026-10-06T00:02:00Z")
    assert another.sha256 != report.sha256 and another.real_backtest_ready is False


def test_qc_requirements_are_additional_not_silently_assumed_for_local_target():
    local = ready.evaluate_fixture_readiness(spec(), (), as_of_utc="2026-10-06T00:00:00Z")
    qc = ready.evaluate_fixture_readiness(spec(target="synthetic-qc-order-based"), (),
                                         as_of_utc="2026-10-06T00:00:00Z")
    assert tuple(item.requirement_id for item in qc.requirements) == ready.REQUIREMENTS + ready.QC_REQUIREMENTS
    assert not any(item.requirement_id in ready.QC_REQUIREMENTS for item in local.requirements)


@pytest.mark.parametrize("payload", [b'{"a":1,"a":1}\n', b'{"a":NaN}\n', b'{"a":1.0}\n',
                                   b'{"a":Infinity}\n', b'{}', b'[]\n', b'\xff'])
def test_rehashed_malformed_artifact_refuses_before_any_admission(payload):
    forged = ready.FrozenFixtureRunSpec(payload, hashlib.sha256(payload).hexdigest())
    with pytest.raises(ready.ReadinessError):
        ready.evaluate_fixture_readiness(forged, (), as_of_utc="2026-10-06T00:00:00Z")


def test_inventory_duplicates_and_ledger_resource_bounds_refuse():
    item = {"requirement_id": "reviewed_candidate", "fixture_id": "SYNTHETIC-EVIDENCE", "fixture_sha256": "7" * 64}
    with pytest.raises(ready.ReadinessError, match="inventory"):
        ready.evaluate_fixture_readiness(spec(), (item, item), as_of_utc="2026-10-06T00:00:00Z")
    receipt = reserve(spec())[0]
    with pytest.raises(ready.ReadinessError, match="bounded"):
        ready.load_fixture_ledger((receipt,) * 129, expected_head_sha256=receipt.sha256)


def test_every_reservation_preserves_capacity_for_all_terminal_receipts():
    def at(second):
        return f"2026-10-06T00:{second // 60:02}:{second % 60:02}+00:00"
    run, ledger = spec(), ()
    for number in range(1, 64):
        ledger = close(reserve(run, ledger, number, at(2 * number - 1)), number, clock=at(2 * number))
    assert len(ledger) == 126
    pending = reserve(run, ledger, 64, at(127))
    raw = raw_spec()
    raw["lineage"]["candidate_sha256"] = "6" * 64
    other = ready.freeze_fixture_run_spec(raw)
    with pytest.raises(ready.ReadinessError, match="terminal capacity"):
        reserve(other, pending, 65, at(128))
    closed = close(pending, 64, clock=at(128))
    assert len(closed) == 128 and ready.ledger_head(closed) == closed[-1].sha256

    # Rehashing a fabricated reservation must not evade the same prefix rule.
    def invent(body):
        body.update(sequence=128, previous_sha256=pending[-1].sha256,
                    attempt_id="SYNTHETIC-ATTEMPT-65", at_utc=at(128),
                    run_spec=json.loads(other.payload), run_spec_sha256=other.sha256,
                    attempt_ordinal=1)
    extra = rehashed_receipt(pending[-1], invent)
    with pytest.raises(ready.ReadinessError, match="terminal capacity"):
        ready.load_fixture_ledger(pending + (extra,), expected_head_sha256=extra.sha256)


def test_custom_keys_do_not_execute_callbacks():
    class Evil(str):
        def __eq__(self, other):
            pytest.fail("custom equality executed")
        __hash__ = str.__hash__
    raw = raw_spec()
    raw[Evil("surprise")] = None
    with pytest.raises(ready.ReadinessError):
        ready.freeze_fixture_run_spec(raw)


def test_readiness_dossier_and_ledger_are_inert_without_io(monkeypatch):
    def refuse(*args, **kwargs):
        pytest.fail("I/O attempted")
    import builtins
    import io
    import os
    import socket
    for module, name in ((builtins, "open"), (io, "open"), (os, "open"), (socket, "socket")):
        monkeypatch.setattr(module, name, refuse)
    run = spec()
    ledger = close(reserve(run))
    report = ready.evaluate_fixture_readiness(run, (), ledger, as_of_utc="2026-10-06T00:02:00Z")
    assert report.real_backtest_ready is False
