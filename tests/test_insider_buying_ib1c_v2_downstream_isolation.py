"""Invented scalar/source protocols only; no real worker or retained roots."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from research import insider_buying_affected_quarter_isolation as isolation
from research.insider_buying import sec_ib1c_v2_downstream as coverage
from research.insider_buying import backtest_evidence_pipeline as pipeline
from research.insider_buying.sec_ib1c_identity_v2 import (
    IDENTITY_V2_VERSION, IDENTITY_V2_EVIDENCE_EPOCH,
)


_CONSUMER_COMMIT = "d" * 40


def _copy(value):
    return json.loads(isolation._canonical(value))


def _receipt():
    """Fabricated complete protocol metadata, not an actual assessment proof."""
    forms = dict(zip(("3", "3/A", "4", "4/A", "5", "5/A"),
                     (5694, 534, 68520, 3159, 5539, 211), strict=True))
    reasons = {"complete_parent_corroboration_missing": 71679,
               "complete_parent_identity_conflict": 0,
               "unsupported_parent_corroboration_form": 11978}
    counts = {"submission_count": 83657, "corroborated_count": 0,
              "quarantined_count": 83657, "short_cik_count": 0,
              "accession_year_mismatch_count": 1}
    quarter = {
        "kind": coverage.QUARTER_COVERAGE_VERSION,
        "evidence_epoch": coverage.COVERAGE_EVIDENCE_EPOCH,
        "policy_version": IDENTITY_V2_VERSION,
        "policy_epoch": IDENTITY_V2_EVIDENCE_EPOCH,
        "period": "2006Q1",
        "preparation_binding": {
            "period": "2006Q1", "producer_commit": isolation._PRODUCER_COMMIT,
            "producer_source_inventory_sha256": isolation._PRODUCER_INVENTORY_SHA256,
            "completion_envelope_sha256": "d05e0345124b96599fbbd82a81828452ea63d39a90b3be28b599ef1e462bbfd0",
            "assessment_envelope_sha256": "402fa1860bd9549f6d0eadcf7dc9a956cc0dc006d91f038290c294c102083ad5",
            "assessment_envelope_bytes": 63409968,
            "raw_snapshot_id": "sec-insider-bulk-2006q1-afe9a4b0bd20acce",
            "raw_lineage_sha256": "afe9a4b0bd20acce459c2f0fe7989b20c5422f333395ec03e0a737feac357f23",
            "parsed_snapshot_id": "sec-insider-parsed-2006q1-777136638dc6a1e5",
            "parsed_lineage_sha256": "777136638dc6a1e5794bdd7878672ac9c08e33226b09306ccd262c6511c6de84",
            "profile_sha256": "ee2f201362d4002a70819e4d7123eea300aafddb8820c6a0ab9761b0ed8cdd41",
            "census_quarter_sha256": "047b92bdcd8fe82b21d76cddc05c8cca1ec31d7dec6e9c5186a1312e4cd4c5a2",
        },
        "assessment_sha256": "3000a184944aa1718854dba90842ec774032c269fc36740dc46ddbe90c1f1525",
        "rows_sha256": "a" * 64,
        **counts, "form_counts": forms, "quarantine_reason_counts": reasons,
        "source_identity_complete": False, "source_identity_sha256": None,
        "artifact_loading_verified_here": False,
        "binding_is_external_attestation": False,
        "authority": dict(isolation._AUTHORITY),
    }

    def scope(expected):
        return {
            "kind": coverage.SCOPE_COVERAGE_VERSION,
            "evidence_epoch": coverage.COVERAGE_EVIDENCE_EPOCH,
            "policy_version": IDENTITY_V2_VERSION,
            "policy_epoch": IDENTITY_V2_EVIDENCE_EPOCH,
            "expected_periods": list(expected), "loaded_periods": ["2006Q1"],
            "missing_periods": list(expected[1:]),
            "loaded_scope_complete": len(expected) == 1,
            "source_identity_complete": False, "source_identity_sha256": None,
            "quarter_bindings": [{"period": "2006Q1", "coverage_sha256": isolation._digest(quarter),
                                  "source_identity_sha256": None}],
            **counts, "form_counts": dict(forms), "quarantine_reason_counts": dict(reasons),
            "artifact_loading_verified_here": False,
            "authority": dict(isolation._AUTHORITY),
        }

    return {
        "kind": "INSETF-IB1C-V2-RETAINED-DOWNSTREAM-READBACK-v1", "quarter": quarter,
        "selected_scope": scope(("2006Q1",)),
        "retained_82_partial_scope": scope(coverage.EXPECTED_PERIODS),
        "pilot": {"row_count": 83657, "ledger_sha256": quarter["rows_sha256"],
                  "source_only_admitted_count": 0, "quarantined_count": 83657,
                  "event_eligibility": "not_evaluated", "candidate_signal_count": None},
        "backtest_pipeline": {
            "kind": pipeline.PIPELINE_VERSION + "-coverage-handoff",
            "coverage_sha256": isolation._digest(quarter), "period": "2006Q1",
            "submission_count": 83657, "corroborated_count": 0, "quarantined_count": 83657,
            "form_counts": dict(forms), "quarantine_reason_counts": dict(reasons),
            "source_identity_complete": False, "source_identity_sha256": None,
            "relevant_form4_count": 71679, "relevant_form4_identity_complete": False,
            "eligible_events_evaluated": False, "admitted_event_count": 0,
            "backtesting_ready": False, "missing_evidence": list(pipeline._MISSING),
            "source_authenticated": False, "qc_jobs": 0, "research_looks": 0,
        },
        "artifact_validation": {
            "public_raw_bound_parsed_reload": True, "complete_assessment_rederived": True,
            "complete_completion_rederived": True, "producer_lineage_preserved": True,
            "source_only": True, "publisher_or_recovery_called": False,
        },
        "authority": dict(isolation._AUTHORITY),
    }


def test_exact_fabricated_scalar_protocol_is_accepted_without_admitting_events():
    receipt = _receipt()
    assert isolation._consumer_receipt(receipt) == receipt
    assert receipt["selected_scope"]["loaded_scope_complete"] is True
    assert receipt["selected_scope"]["source_identity_complete"] is False
    assert receipt["pilot"]["event_eligibility"] == "not_evaluated"
    assert receipt["backtest_pipeline"]["eligible_events_evaluated"] is False


@pytest.mark.parametrize("change", [
    "quarter_unknown_promotion", "pilot_unknown_promotion", "selected_row_drop",
    "partial_wrong_missing_periods", "partial_empty_expected_periods",
    "form_count_boolean", "short_cik_boolean", "wrong_assessment_hash",
    "missing_binding_identity", "wrong_binding_lineage", "external_attestation",
    "scope_loading_claim", "wrong_scope_coverage_hash", "wrong_pilot_ledger_hash",
    "wrong_quarter_rows_hash_shape", "wrong_partial_cross_count",
])
def test_substituted_worker_cannot_promote_or_drop_nested_protocol_metadata(change):
    """Worker-substitution defense in depth, not a captured-code exploit."""
    receipt = _receipt()
    quarter, selected, partial = (receipt[key] for key in (
        "quarter", "selected_scope", "retained_82_partial_scope"))
    if change == "quarter_unknown_promotion":
        quarter["signal_authorized"] = True
    elif change == "pilot_unknown_promotion":
        receipt["pilot"]["execution_authorized"] = True
    elif change == "selected_row_drop":
        selected["submission_count"] = selected["quarantined_count"] = 0
    elif change == "partial_wrong_missing_periods":
        partial["missing_periods"] = ["2006Q1"] * 81
    elif change == "partial_empty_expected_periods":
        partial["expected_periods"] = []
    elif change == "form_count_boolean":
        quarter["form_counts"]["3"] = True
    elif change == "short_cik_boolean":
        quarter["short_cik_count"] = False
    elif change == "wrong_assessment_hash":
        quarter["assessment_sha256"] = "d" * 64
    elif change == "missing_binding_identity":
        quarter["preparation_binding"].pop("raw_snapshot_id")
    elif change == "wrong_binding_lineage":
        quarter["preparation_binding"]["parsed_lineage_sha256"] = "d" * 64
    elif change == "external_attestation":
        quarter["binding_is_external_attestation"] = True
    elif change == "scope_loading_claim":
        selected["artifact_loading_verified_here"] = True
    elif change == "wrong_scope_coverage_hash":
        selected["quarter_bindings"][0]["coverage_sha256"] = "f" * 64
    elif change == "wrong_pilot_ledger_hash":
        receipt["pilot"]["ledger_sha256"] = "f" * 64
    elif change == "wrong_quarter_rows_hash_shape":
        quarter["rows_sha256"] = "not-a-hash"
    else:
        partial["submission_count"] = partial["quarantined_count"] = 0
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED"):
        isolation._consumer_receipt(receipt)


@pytest.mark.parametrize("change", [
    "missing", "unknown_promotion", "submission_drop", "relevant_drop",
    "eligible_claim", "admitted_claim", "backtesting_ready", "identity_complete",
    "missing_evidence_drop", "wrong_coverage_hash", "authority_integer_false",
    "look_boolean",
])
def test_negative_backtest_pipeline_protocol_cannot_be_dropped_or_promoted(change):
    receipt = _receipt()
    body = receipt["backtest_pipeline"]
    if change == "missing":
        receipt.pop("backtest_pipeline")
    elif change == "unknown_promotion":
        body["execution_authorized"] = True
    elif change == "submission_drop":
        body["submission_count"] = body["quarantined_count"] = 0
    elif change == "relevant_drop":
        body["relevant_form4_count"] = 0
    elif change == "eligible_claim":
        body["eligible_events_evaluated"] = True
    elif change == "admitted_claim":
        body["admitted_event_count"] = 1
    elif change == "backtesting_ready":
        body["backtesting_ready"] = True
    elif change == "identity_complete":
        body["relevant_form4_identity_complete"] = True
    elif change == "missing_evidence_drop":
        body["missing_evidence"].pop()
    elif change == "wrong_coverage_hash":
        body["coverage_sha256"] = "f" * 64
    elif change == "authority_integer_false":
        body["source_authenticated"] = 0
    else:
        body["research_looks"] = False
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED"):
        isolation._consumer_receipt(receipt)


def _producer_fixture(monkeypatch: pytest.MonkeyPatch):
    old = {path: b"# original dependency\n" for path in (
        isolation._WORKER_PATH, isolation._CORE_PATH,
        *(f"research/insider_buying_fixture_{index:03d}.py" for index in range(94)),
    )}
    inventory = isolation._inventory(tuple(sorted(old.items())))
    monkeypatch.setattr(isolation, "_PRODUCER_INVENTORY_SHA256", isolation._digest(inventory))
    current = dict(old)
    current[isolation._WORKER_PATH] = b"# new read-only launcher\n"
    current[isolation._CONSUMER_PATH] = b"# new consumer\n"
    current["research/insider_buying/sec_ib1c_v2_downstream.py"] = b"# new coverage\n"
    return tuple(sorted(current.items())), inventory, old


def test_original_96_source_compatibility_excludes_only_changed_launcher(
    monkeypatch: pytest.MonkeyPatch,
):
    current, inventory, old = _producer_fixture(monkeypatch)
    assert len(inventory) == 96 and len(current) == 98
    assert dict(current)[isolation._WORKER_PATH] != old[isolation._WORKER_PATH]
    isolation._compatible_producer_sources(current, inventory)


@pytest.mark.parametrize("change", ["missing_dependency", "changed_dependency", "missing_launcher"])
def test_original_dependency_missing_or_drift_refuses_even_with_new_consumer_sources(
    monkeypatch: pytest.MonkeyPatch, change: str,
):
    current, inventory, _ = _producer_fixture(monkeypatch)
    changed = dict(current)
    if change == "changed_dependency":
        changed[isolation._CORE_PATH] = b"# drifted original parser\n"
    else:
        changed.pop(isolation._WORKER_PATH if change == "missing_launcher" else isolation._CORE_PATH)
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED"):
        isolation._compatible_producer_sources(tuple(sorted(changed.items())), inventory)


@pytest.mark.parametrize("change", ["missing", "extra", "unknown", "reordered", "duplicate", "extra_wrapper", "wrong_hash"])
def test_producer_inventory_requires_exact_original_96_source_identity(
    monkeypatch: pytest.MonkeyPatch, change: str,
):
    current, inventory, _ = _producer_fixture(monkeypatch)
    if change == "missing":
        inventory.pop()
    elif change == "extra":
        inventory.append({"path": isolation._CONSUMER_PATH, "sha256": "a" * 64})
    elif change == "unknown":
        inventory[0]["path"] = "research/unknown.py"
    elif change == "reordered":
        inventory.reverse()
    elif change == "duplicate":
        inventory[1] = inventory[0]
    elif change == "extra_wrapper":
        inventory[0]["unbound"] = None
    else:
        inventory[0]["sha256"] = "f" * 64
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED"):
        isolation._compatible_producer_sources(current, inventory)


def test_original_inventory_is_reconstructed_from_producer_git_not_current_glob(
    monkeypatch: pytest.MonkeyPatch,
):
    current, expected, old = _producer_fixture(monkeypatch)
    calls = []

    def git(*args):
        calls.append(args)
        if args == ("ls-tree", "-r", "--name-only", isolation._PRODUCER_COMMIT):
            return ("\n".join((*old, "tests/new_test.py", "docs/not-source.md")) + "\n").encode()
        assert args[:2] == ("cat-file", "blob")
        commit, path = args[2].split(":", 1)
        assert commit == isolation._PRODUCER_COMMIT
        return old[path]

    monkeypatch.setattr(isolation, "_git", git)
    assert isolation._producer_inventory(current) == expected
    assert len(calls) == 97
    assert all(isolation._CONSUMER_PATH not in str(call) for call in calls)


def test_readonly_policy_has_no_write_allowance_and_keeps_network_process_denial(tmp_path: Path):
    policy = isolation._worker_policy(tmp_path, readonly=True)
    assert "(deny file-write*)" in policy
    assert "(allow file-write" not in policy
    assert "(deny network*)" in policy
    assert "(deny process-fork)" in policy
    assert "(deny process-exec)" in policy
    assert "(allow process-exec (literal " in policy
    writer = isolation._worker_policy(tmp_path, readonly=False)
    assert f'(allow file-write* (subpath "{tmp_path}"))' in writer


@pytest.mark.parametrize("mode", [None, 0, 1, "true", [], {}])
def test_readonly_policy_mode_requires_exact_boolean(tmp_path: Path, mode):
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED"):
        isolation._worker_policy(tmp_path, readonly=mode)


def test_readonly_bootstrap_calls_only_readonly_entry():
    assert "m._readonly_worker_main(b)" in isolation._READONLY_BOOTSTRAP
    assert "m._worker_main(b)" not in isolation._READONLY_BOOTSTRAP
    assert "m._worker_main(b)" in isolation._BOOTSTRAP
    assert isolation._READONLY_BOOTSTRAP != isolation._BOOTSTRAP


@pytest.mark.parametrize("body", ["top", "quarter", "selected_scope", "retained_82_partial_scope"])
@pytest.mark.parametrize("change", ["missing", "integer_false", "true", "boolean_counter"])
def test_each_financial_authority_boundary_is_literal_false_and_int_zero(body, change):
    receipt = _receipt()
    authority = receipt["authority"] if body == "top" else receipt[body]["authority"]
    if change == "missing":
        authority.pop("source_authenticated")
    elif change == "integer_false":
        authority["source_authenticated"] = 0
    elif change == "true":
        authority["source_authenticated"] = True
    else:
        authority["research_looks"] = False
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED"):
        isolation._consumer_receipt(receipt)


def _mock_parent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Mock capture/child protocols only; there are no source-data files."""
    source, preparation = tmp_path / "source", tmp_path / "preparation"
    source.mkdir()
    preparation.mkdir()
    current, inventory, _ = _producer_fixture(monkeypatch)
    image = dict(current)
    receipt = _receipt()
    trace = isolation._inventory(tuple((path, image[path]) for path in (
        isolation._WORKER_PATH, isolation._CORE_PATH, isolation._CONSUMER_PATH)))
    payload = {"receipt": receipt, "executed_modules": trace}
    context = (str(isolation.LANE_ROOT), isolation.LANE_BRANCH, _CONSUMER_COMMIT)
    monkeypatch.setattr(isolation, "_repository_snapshot", lambda _: context)
    monkeypatch.setattr(isolation, "_source_snapshot", lambda: current)
    monkeypatch.setattr(isolation, "_verify_committed_sources", lambda *args: None)

    def producer(sources):
        isolation._compatible_producer_sources(sources, inventory)
        return inventory

    monkeypatch.setattr(isolation, "_producer_inventory", producer)
    calls = []

    def worker(raw, output, *, readonly):
        assert readonly is True and output == preparation
        bundle = json.loads(raw)
        assert bundle["input_root"] == str(source)
        assert bundle["preparation_root"] == str(preparation)
        assert "output_root" not in bundle
        assert bundle["expected_commit"] == _CONSUMER_COMMIT
        assert bundle["producer_inventory"] == inventory
        assert bundle["source_inventory_sha256"] == isolation._digest(isolation._inventory(current))
        calls.append(bundle)
        return subprocess.CompletedProcess((), 0, isolation._canonical(payload) + b"\n", b"")

    monkeypatch.setattr(isolation, "_run_worker", worker)
    return source, preparation, current, payload, calls


def test_mocked_readonly_parent_preserves_old_producer_and_new_consumer_lineages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    source, preparation, current, payload, calls = _mock_parent(tmp_path, monkeypatch)
    before = (source.stat().st_mtime_ns, preparation.stat().st_mtime_ns)
    result = isolation.run_readonly_consumer(source, preparation, _CONSUMER_COMMIT)
    assert len(calls) == 1 and result["receipt"] == payload["receipt"]
    assert result["consumer_commit"] == _CONSUMER_COMMIT
    assert result["consumer_source_count"] == 98
    assert result["consumer_source_inventory_sha256"] == isolation._digest(isolation._inventory(current))
    assert result["producer_inventory_sha256"] == isolation._PRODUCER_INVENTORY_SHA256
    assert result["producer_dependency_compatibility_count"] == 95
    assert result["receipt"]["quarter"]["preparation_binding"]["producer_commit"] == isolation._PRODUCER_COMMIT
    assert result["worker_source_sha256"] == isolation._sha(dict(current)[isolation._WORKER_PATH])
    assert result["worker_bootstrap_sha256"] == isolation._sha(isolation._READONLY_BOOTSTRAP.encode("utf-8"))
    assert result["executed_source_inventory_sha256"] == isolation._digest(payload["executed_modules"])
    assert result["executed_source_count"] == 3
    for key in ("os_network_denied", "os_all_file_writes_denied", "os_process_fork_denied",
                "audit_additional_processes_denied", "source_only_lane_imports"):
        assert result[key] is True
    assert list(source.iterdir()) == list(preparation.iterdir()) == []
    assert (source.stat().st_mtime_ns, preparation.stat().st_mtime_ns) == before


@pytest.mark.parametrize("change", [
    "missing_wrapper", "extra_wrapper", "missing_trace", "empty_trace",
    "missing_core", "missing_consumer", "missing_launcher", "duplicate_trace",
    "unknown_source", "wrong_source_hash", "extra_trace_wrapper", "nested_promotion",
])
def test_mocked_readonly_parent_refuses_unbound_worker_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change,
):
    source, preparation, current, payload, _ = _mock_parent(tmp_path, monkeypatch)
    trace = payload["executed_modules"]
    replacement = next(isolation._inventory(((path, raw),))[0] for path, raw in current
                       if "fixture_" in path)
    if change == "missing_wrapper":
        payload.pop("receipt")
    elif change == "extra_wrapper":
        payload["unbound"] = None
    elif change == "missing_trace":
        payload.pop("executed_modules")
    elif change == "empty_trace":
        trace.clear()
    elif change in {"missing_core", "missing_consumer", "missing_launcher"}:
        index = {"missing_core": 1, "missing_consumer": 2, "missing_launcher": 0}[change]
        trace[index] = replacement
    elif change == "duplicate_trace":
        trace[1] = trace[0]
    elif change == "unknown_source":
        trace[1]["path"] = "research/unknown.py"
    elif change == "wrong_source_hash":
        trace[1]["sha256"] = "f" * 64
    elif change == "extra_trace_wrapper":
        trace[1]["unbound"] = None
    else:
        payload["receipt"]["pilot"]["signal_authorized"] = True
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED"):
        isolation.run_readonly_consumer(source, preparation, _CONSUMER_COMMIT)
    assert list(source.iterdir()) == list(preparation.iterdir()) == []


@pytest.mark.parametrize("kind", ["refused", "stderr", "empty", "oversized", "invalid_json", "noncanonical"])
def test_readonly_process_failure_cannot_return_or_leak_raw_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind,
):
    source, preparation, _, payload, _ = _mock_parent(tmp_path, monkeypatch)
    raw, errors, returncode = isolation._canonical(payload) + b"\n", b"", 0
    if kind == "refused":
        returncode = 1
        errors = b"PRIVATE_ISSUER synthetic failure\n"
    elif kind == "stderr":
        errors = b"PRIVATE_ISSUER warning\n"
    elif kind == "empty":
        raw = b""
    elif kind == "oversized":
        raw = b"x" * (isolation._MAX_OUTPUT_BYTES + 1)
    elif kind == "invalid_json":
        raw = b"{broken}\n"
    else:
        raw = b" " + raw
    monkeypatch.setattr(isolation, "_run_worker", lambda *args, **kwargs:
                        subprocess.CompletedProcess((), returncode, raw, errors))
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED") as caught:
        isolation.run_readonly_consumer(source, preparation, _CONSUMER_COMMIT)
    assert "PRIVATE_ISSUER" not in str(caught.value)
    assert list(source.iterdir()) == list(preparation.iterdir()) == []


@pytest.mark.parametrize("phase", ["before_worker", "after_worker"])
def test_readonly_context_advance_is_not_the_verified_consumer_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase,
):
    source, preparation, _, _, launches = _mock_parent(tmp_path, monkeypatch)
    calls = 0

    def context(_):
        nonlocal calls
        calls += 1
        changed = calls >= (2 if phase == "before_worker" else 3)
        return (str(isolation.LANE_ROOT), isolation.LANE_BRANCH,
                "e" * 40 if changed else _CONSUMER_COMMIT)

    monkeypatch.setattr(isolation, "_repository_snapshot", context)
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED"):
        isolation.run_readonly_consumer(source, preparation, _CONSUMER_COMMIT)
    assert len(launches) == (0 if phase == "before_worker" else 1)


def test_readonly_source_capture_drift_refuses_before_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    source, preparation, current, _, launches = _mock_parent(tmp_path, monkeypatch)
    calls = 0

    def snapshot():
        nonlocal calls
        calls += 1
        return current if calls == 1 else ((current[0][0], b"changed\n"), *current[1:])

    monkeypatch.setattr(isolation, "_source_snapshot", snapshot)
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED.*source inventory changed"):
        isolation.run_readonly_consumer(source, preparation, _CONSUMER_COMMIT)
    assert launches == []


def test_readonly_directory_identity_change_refuses_without_artifact_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    source, preparation, _, _, _ = _mock_parent(tmp_path, monkeypatch)
    original = isolation._readonly_paths
    calls = 0

    def paths(*args):
        nonlocal calls
        calls += 1
        identities = original(*args)
        if calls == 1:
            return identities
        return identities[0], (identities[1][0], identities[1][1] + 1)

    monkeypatch.setattr(isolation, "_readonly_paths", paths)
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED.*directory identity changed"):
        isolation.run_readonly_consumer(source, preparation, _CONSUMER_COMMIT)


def test_readonly_missing_sandbox_refuses_before_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    source, preparation, _, _, launches = _mock_parent(tmp_path, monkeypatch)
    original = Path.is_file
    monkeypatch.setattr(Path, "is_file", lambda path:
                        False if str(path) == "/usr/bin/sandbox-exec" else original(path))
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED.*sandbox is unavailable"):
        isolation.run_readonly_consumer(source, preparation, _CONSUMER_COMMIT)
    assert launches == []


@pytest.mark.parametrize("mode", [None, 0, 1, "true"])
def test_readonly_run_worker_bad_mode_never_launches_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode,
):
    calls = []
    monkeypatch.setattr(isolation.subprocess, "Popen", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED"):
        isolation._run_worker(b"{}", tmp_path, readonly=mode)
    assert calls == []
