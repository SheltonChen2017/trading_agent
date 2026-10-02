"""Tiny synthetic descriptors; exact historical blobs, never historical execution."""
from dataclasses import replace
from pathlib import Path

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying import sec_recovery_v4_plan as module


@pytest.fixture(scope="module")
def blobs():
    root = Path(__file__).resolve().parents[1]
    return tuple((name, (root / name).read_bytes()) for name, _ in module.HISTORICAL_FILES)


@pytest.fixture(scope="module")
def binding(blobs):
    return module.bind_v3_historical_validator(module.HISTORICAL_COMMIT, blobs)


def _inputs():
    requests = tuple({
        "period": "2023Q1", "accession_number": f"0000123456-23-{i:06d}",
        "form_type": "4", "filing_date": "2023-01-15", "issuer_cik": "123456",
        "archive_path": f"edgar/data/888888/0000123456-23-{i:06d}.txt",
        "submission_row_id": hash_payload(i), "parsed_lineage_hash": "a" * 64,
        "master_source_sha256": "b" * 64,
        "url": f"https://www.sec.gov/Archives/edgar/data/888888/0000123456-23-{i:06d}.txt",
    } for i in range(1, 10))
    classes = ("prior_completed", "prior_completed", "offline_corrected_diagnostic",
               "remaining_selected_reuse", "later_unattempted", "later_unattempted",
               "remaining_selected_reuse", "later_unattempted", "later_unattempted")
    partial = {name: hash_payload(name) for name in module._PARTIAL_HASHES}
    partial.update(pending_request_sha256=hash_payload(requests[7]),
                   pending_global_index=7, pending_attempt_number=1,
                   completed_new_count=2, attempt_count=3,
                   source_assignment_sha256=hash_payload(list(classes)))
    diagnostic = {name: hash_payload(name) for name in module._DIAGNOSTIC_HASHES}
    diagnostic.update(
        diagnostic_capture_git_commit="f" * 40, pending_global_index=7, body_size_bytes=123,
        ambiguous_request_sha256=partial["pending_request_sha256"],
        original_pending_start_sha256=partial["pending_attempt_start_sha256"],
        v3_root_plan_sha256=partial["root_plan_sha256"],
        v3_source_plan_sha256=partial["source_plan_sha256"],
        v3_source_assignment_sha256=partial["source_assignment_sha256"],
        pending_shard_inventory_sha256=partial["pending_shard_inventory_sha256"],
        pending_shard_journal_sha256=partial["pending_shard_journal_sha256"],
    )
    return requests, classes, partial, diagnostic


def _build(binding, inputs=None):
    return module.build_recovery_v4_offline_plan(*(_inputs() if inputs is None else inputs), binding, scope="synthetic_test")


def test_exact_historical_binding_is_inert_and_copy_safe(binding):
    body = binding.to_payload()
    assert body["commit"] == module.HISTORICAL_COMMIT
    assert body["validator_sha256"] == module.HISTORICAL_VALIDATOR_SHA256
    assert body["files"] == [{"path": name, "sha256": sha} for name, sha in module.HISTORICAL_FILES]
    assert not body["historical_code_executed"] and not body["historical_root_replayed"]
    assert not body["git_provenance_verified"]
    body["historical_code_executed"] = True
    assert not binding.to_payload()["historical_code_executed"]


@pytest.mark.parametrize("case", ["commit", "reorder", "missing", "extra", "drift", "list", "wrong_name"])
def test_historical_byte_or_inventory_drift_refused(blobs, case):
    commit = module.HISTORICAL_COMMIT
    if case == "commit":
        commit = "f" * 40
    elif case == "reorder":
        blobs = tuple(reversed(blobs))
    elif case == "missing":
        blobs = blobs[:-1]
    elif case == "extra":
        blobs = (*blobs, blobs[0])
    elif case == "drift":
        blobs = ((blobs[0][0], blobs[0][1] + b"\n"), *blobs[1:])
    elif case == "list":
        blobs = list(blobs)
    else:
        blobs = (("wrong.py", blobs[0][1]), *blobs[1:])
    with pytest.raises(module.RecoveryV4PlanError):
        module.bind_v3_historical_validator(commit, blobs)


def test_partition_is_ordered_disjoint_and_excludes_all_completed_and_ambiguous(binding):
    result = _build(binding)
    body = result.to_payload()
    assert body["class_counts"] == {
        "prior_completed": 2, "offline_corrected_diagnostic": 1, "remaining_selected_reuse": 2,
        "v3_completed": 2, "accepted_ambiguous_diagnostic": 1, "originally_unattempted": 1,
    }
    assert [row["global_index"] for row in body["partition"]] == list(range(9))
    assert [row["global_index"] for row in body["proposed_unattempted_inventory"]] == [8]
    assert body["partition_sha256"] == hash_payload(body["partition"])
    assert body["stopped_v3_disposition"] == "preserved_unresolved_not_resumable"
    assert body["authority"]["caller_supplied_descriptors"] is True
    assert all(value is False or type(value) is int and value == 0
               for key, value in body["authority"].items() if key != "caller_supplied_descriptors")
    assert result.sha256 == hash_payload(body)


@pytest.mark.parametrize("name", module._DIAGNOSTIC_HASHES + ("pending_global_index",))
def test_diagnostic_linkage_drift_refused(binding, name):
    inputs = _inputs()
    # report/body hashes are independent diagnostic anchors in synthetic scope;
    # all other fields must bind the original start exactly.
    if name in {"report_sha256", "body_sha256"}:
        inputs[3][name] = "invalid"
    else:
        inputs[3][name] = 8 if name == "pending_global_index" else "0" * 64
    with pytest.raises(module.RecoveryV4PlanError):
        _build(binding, inputs)


@pytest.mark.parametrize("name,value", [
    ("completed_new_count", 1), ("completed_new_count", 4),
    ("completed_new_count", True), ("pending_attempt_number", 2),
    ("attempt_count", 4), ("pending_global_index", 8),
    ("pending_request_sha256", "0" * 64), ("source_assignment_sha256", "0" * 64),
])
def test_missing_completed_prefix_or_ambiguous_redispatch_refused(binding, name, value):
    inputs = _inputs()
    inputs[2][name] = value
    with pytest.raises(module.RecoveryV4PlanError):
        _build(binding, inputs)


@pytest.mark.parametrize("case", ["missing", "extra", "duplicate", "reordered", "class", "class_order", "wrong_date", "wrong_url", "extra_field"])
def test_inventory_mutations_refused(binding, case):
    requests, classes, p, d = _inputs()
    if case == "missing":
        requests = requests[:-1]
    elif case == "extra":
        requests = (*requests, requests[0])
    elif case == "duplicate":
        requests = (requests[1], *requests[1:])
    elif case == "reordered":
        requests = tuple(reversed(requests))
    elif case == "class":
        classes = (*classes[:-1], "accepted_ambiguous_diagnostic")
    elif case == "class_order":
        classes = tuple(reversed(classes))
    else:
        requests[0][{"wrong_date": "filing_date", "wrong_url": "url", "extra_field": "extra"}[case]] = "2022-12-31" if case == "wrong_date" else "invalid"
    with pytest.raises(module.RecoveryV4PlanError):
        _build(binding, (requests, classes, p, d))


@pytest.mark.parametrize("count", [99393, 99395, 79867, 79869])
def test_changed_observed_denominator_cannot_become_a_plan(binding, count):
    with pytest.raises(module.RecoveryV4PlanError):
        module.build_recovery_v4_offline_plan(({},) * count, ("later_unattempted",) * count, {}, {}, binding)


def test_synthetic_scope_is_not_observed_authority_and_input_changes_do_not_alter_plan(binding):
    inputs = _inputs()
    result = _build(binding, inputs)
    assert result.to_payload()["scope"] == "synthetic_test"
    inputs[0][0]["issuer_cik"] = "999"
    assert result.to_payload()["request_inventory_sha256"] != hash_payload(list(inputs[0]))
    with pytest.raises(module.RecoveryV4PlanError):
        module.build_recovery_v4_offline_plan(*inputs, binding)
    with pytest.raises(module.RecoveryV4PlanError):
        module.build_recovery_v4_offline_plan(*inputs, binding, scope="authorized")


def test_reconstructing_payload_cannot_enable_dispatch(binding):
    result = _build(binding)
    body = result.to_payload()
    body["authority"]["dispatch_enabled"] = True
    raw = canonical_json(body).encode()
    forged = replace(result, _raw=raw, _sha256=hash_bytes(raw))
    with pytest.raises(module.RecoveryV4PlanError):
        forged.to_payload()
    assert not result.to_payload()["authority"]["dispatch_enabled"]


def test_equally_drifted_observed_shard_descriptors_do_not_pass_anchor_check():
    p = dict(module.OBSERVED_PARTIAL_ANCHORS)
    d = dict(module.OBSERVED_DIAGNOSTIC_ANCHORS)
    p["pending_shard_inventory_sha256"] = d["pending_shard_inventory_sha256"] = "0" * 64
    with pytest.raises(module.RecoveryV4PlanError):
        module._require_observed_anchors(p, d)


@pytest.fixture(scope="module")
def full_denominator_inputs():
    # Invented rows at full denominator to exercise the remaining-count guard.
    # Frozen hashes are patched only inside each test; this is NOT real evidence.
    sample = _inputs()[0][0]
    requests = []
    for i in range(99394):
        accession = f"0000123456-23-{i + 1:06d}"
        path = f"edgar/data/888888/{accession}.txt"
        requests.append(dict(sample, accession_number=accession, archive_path=path,
                             url="https://www.sec.gov/Archives/" + path))
    classes = ("prior_completed",) * 9539 + ("offline_corrected_diagnostic",) + ("remaining_selected_reuse",) * 8139 + ("later_unattempted",) * 81715
    p = {name: hash_payload(name) for name in module._PARTIAL_HASHES}
    p.update(module.OBSERVED_PARTIAL_ANCHORS)
    p.update(pending_request_sha256=hash_payload(requests[19525]), pending_global_index=19525,
             pending_attempt_number=1, completed_new_count=1846, attempt_count=1847,
             source_assignment_sha256=hash_payload(list(classes)))
    d = {name: hash_payload(name) for name in module._DIAGNOSTIC_HASHES}
    d.update(module.OBSERVED_DIAGNOSTIC_ANCHORS)
    for dk, pk in (
        ("ambiguous_request_sha256", "pending_request_sha256"),
        ("original_pending_start_sha256", "pending_attempt_start_sha256"),
        ("v3_root_plan_sha256", "root_plan_sha256"), ("v3_source_plan_sha256", "source_plan_sha256"),
        ("v3_source_assignment_sha256", "source_assignment_sha256"),
        ("pending_shard_inventory_sha256", "pending_shard_inventory_sha256"),
        ("pending_shard_journal_sha256", "pending_shard_journal_sha256"), ("pending_global_index", "pending_global_index"),
    ):
        d[dk] = p[pk]
    return tuple(requests), classes, p, d


@pytest.mark.parametrize("completed,expected_remaining", [(1846, 79868), (1845, 79869), (1847, 79867)])
def test_remaining_count_guard_with_total_fixed_at_99394(binding, full_denominator_inputs, monkeypatch, completed, expected_remaining):
    requests, classes, partial, diagnostic = full_denominator_inputs
    monkeypatch.setattr(module, "OBSERVED_REQUEST_INVENTORY", hash_payload(list(requests)))
    monkeypatch.setattr(module, "OBSERVED_SOURCE_ASSIGNMENT", hash_payload(list(classes)))
    later = [i for i, name in enumerate(classes) if name == "later_unattempted"]
    monkeypatch.setattr(module, "OBSERVED_LATER_INVENTORY", hash_payload([requests[i] for i in later]))
    p, d = dict(partial), dict(diagnostic)
    p.update(completed_new_count=completed, attempt_count=completed + 1,
             pending_global_index=later[completed], pending_request_sha256=hash_payload(requests[later[completed]]))
    d.update(pending_global_index=p["pending_global_index"], ambiguous_request_sha256=p["pending_request_sha256"])
    assert len(requests) == 99394 and len(later[completed + 1:]) == expected_remaining
    if completed != 1846:
        with pytest.raises(module.RecoveryV4PlanError):
            module.build_recovery_v4_offline_plan(requests, classes, p, d, binding)
    else:
        body = module.build_recovery_v4_offline_plan(requests, classes, p, d, binding).to_payload()
        assert body["class_counts"]["originally_unattempted"] == 79868
        assert sum(body["class_counts"].values()) == 99394
