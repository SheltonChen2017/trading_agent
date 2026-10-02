from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Callable

import pytest

import research.analyst_revisions_v2.preregistration as preregistration
from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2.preregistration import PreregistrationError


def _artifact_path() -> Path:
    return preregistration.INFRASTRUCTURE_LOOK_LEDGER_PATH


def _install_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
) -> Path:
    path = tmp_path / preregistration.INFRASTRUCTURE_LOOK_LEDGER_FILENAME
    path.write_bytes(payload)
    monkeypatch.setattr(preregistration, "INFRASTRUCTURE_LOOK_LEDGER_PATH", path)
    monkeypatch.setattr(
        preregistration,
        "INFRASTRUCTURE_LOOK_LEDGER_ARTIFACT_SHA256",
        hashlib.sha256(payload).hexdigest(),
    )
    return path


def _reidentify(raw: dict[str, object]) -> None:
    raw["ledger_id"] = None
    raw["ledger_hash"] = None
    digest = hashlib.sha256(canonical_json_bytes(raw)).hexdigest()
    raw["ledger_hash"] = digest
    raw["ledger_id"] = (
        preregistration.INFRASTRUCTURE_LOOK_LEDGER_ID_PREFIX + digest[:24]
    )


def test_committed_infrastructure_looks_are_exact_accounting_without_authority() -> None:
    binding = preregistration.load_infrastructure_look_ledger()
    payload = binding.payload
    raw = json.loads(payload)
    entry = raw["entries"][0]
    discovery_entries = raw["entries"][1:23]
    r079, r080, r081, r082 = raw["entries"][23:]

    assert binding.path == _artifact_path().resolve(strict=True)
    assert binding.artifact_sha256 == hashlib.sha256(payload).hexdigest()
    assert binding.ledger_id == raw["ledger_id"]
    assert binding.ledger_hash == raw["ledger_hash"]
    assert raw["totals"] == {
        "confirmatory_alpha_spent": False,
        "development_evaluations_spent": 0,
        "infrastructure_research_looks_spent": 27,
        "permanent_family_looks_spent": 0,
        "prospective_permanent_looks_remaining": 1,
    }
    assert entry["operation_id"] == "arv2-qc-b5c-refusal-smoke-002"
    assert entry["conservative_research_look_count"] == 1
    assert entry["ambiguous_submission_consumes_look"] is True
    assert entry["retry_authorized"] is False
    assert entry["development_evaluation_consumed"] is False
    assert entry["permanent_family_look_consumed"] is False
    assert entry["confirmatory_alpha_consumed"] is False
    assert entry["receipt_artifact_sha256"] == (
        "6cef656b40ac988afb1d81cf81784fcfad3ca7381ccfea0baabe4e14a6740fb3"
    )
    assert entry["driver_artifact_sha256"] == (
        "b19a489aca60394a2605363be5a1963a9401c37164c5f0da41ea2d45f39b70c0"
    )
    assert entry["receipt_byte_count"] == 3639
    assert entry["driver_byte_count"] == 34882
    assert raw["ledger_sequence"] == 6
    assert raw["append_only_contract"] == {
        "entry_count": 27,
        "predecessor_entry_count": 26,
        "predecessor_ledger_artifact_sha256": (
            "d268f6e678c6d506fbccf5b675d0c8ca99e4484c059479bc159febe0733c240c"
        ),
        "successor_must_retain_every_prior_entry": True,
    }
    predecessor = _artifact_path().with_name(
        "arv2_infrastructure_look_ledger."
        "9b93934f14b79e2c4397a42303a74600dcf457dc66fe743a06633a11410a30c2.json"
    )
    assert hashlib.sha256(predecessor.read_bytes()).hexdigest() == (
        raw["append_only_contract"]["predecessor_ledger_artifact_sha256"]
    )
    predecessor_raw = json.loads(predecessor.read_bytes())
    assert len(predecessor_raw["entries"]) == 26
    assert [canonical_json_bytes(item) for item in raw["entries"][:-1]] == [
        canonical_json_bytes(item) for item in predecessor_raw["entries"]
    ]
    chain = (
        (
            2,
            "11987a12b72d06ea612b442e342ce0b1d2f28c503f0a3b1ca2cf721d8aaa7810",
            "b1018c54128b9cea5ff0c960e0c6adeab803b085b9dde359f323246d0f82e802",
        ),
        (
            3,
            "3b3264a07cbd6687db60be805279c74954669252e71a967b946e66d4e716a937",
            "61e859f775625bd4f88a74e8d3a10943bbe61dfa464bb2d10439cfdf562dcf17",
        ),
        (
            4,
            "f0bf95804153cc15d1f86a8ca7cc6f5912780c36bab8dfb5145add0b8d8853b6",
            "f8b86b17e788b2706edaabcf83a7c51f23ff4688a346f1b4e798f8243d4dd182",
        ),
        (
            5,
            "9b93934f14b79e2c4397a42303a74600dcf457dc66fe743a06633a11410a30c2",
            "d268f6e678c6d506fbccf5b675d0c8ca99e4484c059479bc159febe0733c240c",
        ),
        (
            6,
            "4a726bcdd9b7232f34a1eaf891f7b8f83334002396aa48720b19abd22391305e",
            "e837946d6fe9d31f16d4a901f878e965036f6931f8ed5bb1806fdb5a1c83cdd9",
        ),
    )
    previous = None
    for sequence, ledger_hash, artifact_sha256 in chain:
        path = _artifact_path().with_name(
            f"arv2_infrastructure_look_ledger.{ledger_hash}.json"
        )
        item_payload = path.read_bytes()
        item = json.loads(item_payload)
        assert item["ledger_sequence"] == sequence
        assert item["ledger_hash"] == ledger_hash
        assert hashlib.sha256(item_payload).hexdigest() == artifact_sha256
        if previous is not None:
            previous_payload, previous_raw, previous_artifact = previous
            assert item["append_only_contract"][
                "predecessor_ledger_artifact_sha256"
            ] == previous_artifact
            assert item["append_only_contract"]["predecessor_entry_count"] == len(
                previous_raw["entries"]
            )
            assert [
                canonical_json_bytes(value) for value in item["entries"][:-1]
            ] == [
                canonical_json_bytes(value) for value in previous_raw["entries"]
            ]
        previous = item_payload, item, artifact_sha256
    assert len(discovery_entries) == 22
    assert [item["shared_look_ledger_entry_id"] for item in discovery_entries] == [
        f"R-{ordinal:03d}" for ordinal in range(31, 53)
    ]
    assert [item["attempt_ordinal"] for item in discovery_entries] == [
        7,
        8,
        9,
        10,
        12,
        14,
        15,
        *range(18, 33),
    ]
    assert [item["status"] for item in discovery_entries[:-1]] == [
        "Runtime Error"
    ] * 21
    assert discovery_entries[-1]["status"] == "Completed."
    assert all(item["conservative_research_look_count"] == 1 for item in discovery_entries)
    assert all(item["spent_before_submission"] is True for item in discovery_entries)
    assert all(item["same_entry_retry_permitted"] is False for item in discovery_entries)
    assert all(item["development_evaluation_consumed"] is False for item in discovery_entries)
    assert all(item["permanent_family_look_consumed"] is False for item in discovery_entries)
    assert all(item["confirmatory_alpha_consumed"] is False for item in discovery_entries)
    assert all(item["performance_statistics_inspected"] is False for item in discovery_entries)
    assert all(item["result_values_inspected"] is False for item in discovery_entries)
    assert all(item["outcomes_accessed"] is False for item in discovery_entries)
    assert r079["shared_look_ledger_entry_id"] == "R-079"
    assert r079["project_id"] == 36643367
    assert r079["backtest_id"] == "a2b58090c188fd040217af6c302751b8"
    assert r079["status"] == "Completed."
    assert r079["phase"] == "LOCKED_OUTPUT_READ_AMBIGUITY_NO_VALUES_INSPECTED"
    assert r079["conservative_research_look_count"] == 1
    assert r079["spent_before_submission"] is True
    assert r079["same_entry_retry_permitted"] is False
    assert r079["backtest_terminal_status_accessed"] is True
    assert r079["include_statistics"] is False
    assert r079["backtest_detail_endpoint_called"] is False
    assert r079["output_read_permit_spent"] is True
    assert r079["output_read_outcome_ambiguous"] is True
    assert r079["terminal_pointer_value_inspected"] is False
    assert r079["content_addressed_output_value_inspected"] is False
    assert r079["aggregate_output_values_inspected"] is False
    assert r079["performance_statistics_inspected"] is False
    assert r079["result_values_inspected"] is False
    assert r079["price_or_return_values_accessed"] is False
    assert r079["outcomes_accessed"] is False
    assert r079["orders_permitted"] is False
    assert r079["development_evaluation_consumed"] is False
    assert r079["permanent_family_look_consumed"] is False
    assert r079["confirmatory_alpha_consumed"] is False
    assert r080["shared_look_ledger_entry_id"] == "R-080"
    assert r080["project_id"] == 36644379
    assert r080["backtest_id"] == "3a9dbca993f41ac41177d2c15bb84450"
    assert r080["attestation_schema"].endswith("attestation-v1")
    assert r080["attestation_status"] == "named_refusal"
    assert r080["attestation_safe_reason"] == (
        "pit_coverage_refused_ValueError_1b17331bb939b176"
    )
    assert r081["shared_look_ledger_entry_id"] == "R-081"
    assert r081["project_id"] == 36644829
    assert r081["backtest_id"] == "1cdc40ccd41877743ad907020a6e2e31"
    assert r081["attestation_schema"].endswith("attestation-v1")
    assert r081["attestation_status"] == "named_refusal"
    assert r081["attestation_safe_reason"] == (
        "pit_coverage_refused_ValueError_bef7b6927d4aa871"
    )
    assert r082["shared_look_ledger_entry_id"] == "R-082"
    assert r082["project_id"] == 36645473
    assert r082["backtest_id"] == "c90394212ee91c89f0428b3533de45d9"
    assert r082["status"] == "Completed."
    assert r082["attestation_schema"].endswith("attestation-v2")
    assert r082["attestation_status"] == "completed"
    assert r082["decision_session_count"] == 16
    assert r082["passed_session_count"] == 16
    assert r082["fetched_source_row_count"] == 1_944_801
    assert r082["fundamental_duplicate_exact_sid_count"] == 2
    assert r082["fundamental_duplicate_exact_sid_row_count"] == 2
    assert r082["aggregate_coverage_counts_inspected"] is True
    for appended in (r080, r081, r082):
        assert appended["conservative_research_look_count"] == 1
        assert appended["spent_before_submission"] is True
        assert appended["same_entry_retry_permitted"] is False
        assert appended["performance_statistics_inspected"] is False
        assert appended["price_or_return_values_accessed"] is False
        assert appended["outcomes_accessed"] is False
        assert appended["raw_input_values_retained_or_disclosed"] is False
        assert appended["security_identifiers_retained_or_disclosed"] is False
        assert appended["constituent_weights_retained_or_disclosed"] is False
        assert appended["market_cap_values_retained_or_disclosed"] is False
        assert appended["orders_permitted"] is False
        assert appended["development_evaluation_consumed"] is False
        assert appended["permanent_family_look_consumed"] is False
        assert appended["confirmatory_alpha_consumed"] is False
    assert raw["owner_decision"][
        "external_arv2_development_evaluation_total_remains_21"
    ] is True
    assert raw["owner_decision"]["r082_counted_after_backtest_launch"] is True
    assert raw["owner_decision"][
        "r082_bounded_success_read_did_not_change_look_class"
    ] is True
    assert raw["capabilities"] and all(
        value is False for value in raw["capabilities"].values()
    )


@pytest.mark.parametrize(
    "mutate",
    (
        lambda raw: raw["totals"].__setitem__(
            "infrastructure_research_looks_spent", 0
        ),
        lambda raw: raw["totals"].__setitem__(
            "development_evaluations_spent", 1
        ),
        lambda raw: raw["totals"].__setitem__(
            "permanent_family_looks_spent", 1
        ),
        lambda raw: raw["totals"].__setitem__("confirmatory_alpha_spent", True),
        lambda raw: raw["entries"][0].__setitem__("retry_authorized", True),
        lambda raw: raw["entries"][0].__setitem__(
            "ambiguous_submission_consumes_look", False
        ),
        lambda raw: raw["entries"][0].__setitem__(
            "development_evaluation_consumed", True
        ),
        lambda raw: raw["entries"][0].__setitem__(
            "permanent_family_look_consumed", True
        ),
        lambda raw: raw["entries"][0].__setitem__(
            "confirmatory_alpha_consumed", True
        ),
        lambda raw: raw["append_only_contract"].__setitem__("entry_count", 26),
        lambda raw: raw["append_only_contract"].__setitem__(
            "predecessor_ledger_artifact_sha256", "0" * 64
        ),
        lambda raw: raw["owner_decision"].__setitem__(
            "discovery_backtests_counted_conservatively", 21
        ),
        lambda raw: raw["entries"][1].__setitem__(
            "shared_look_ledger_entry_id", "R-999"
        ),
        lambda raw: raw["entries"][1].__setitem__("outcomes_accessed", True),
        lambda raw: raw["entries"][23].__setitem__(
            "aggregate_output_values_inspected", True
        ),
        lambda raw: raw["entries"][24].__setitem__(
            "attestation_safe_reason", "pit_coverage_refused_changed_deadbeef"
        ),
        lambda raw: raw["entries"][25].__setitem__(
            "attestation_schema",
            "arv2-qc-pit-market-cap-membership-coverage-attestation-v2",
        ),
        lambda raw: raw["entries"][26].__setitem__("status", "Runtime Error"),
        lambda raw: raw["entries"][26].__setitem__(
            "passed_session_count", 15
        ),
        lambda raw: raw["entries"][26].__setitem__(
            "price_or_return_values_accessed", True
        ),
        lambda raw: raw["capabilities"].__setitem__(
            "grants_provider_access", True
        ),
        lambda raw: raw["entries"].append(copy.deepcopy(raw["entries"][0])),
        lambda raw: raw.__setitem__("unexpected", False),
    ),
)
def test_self_consistent_accounting_or_authority_mutations_refuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate: Callable[[dict[str, object]], None],
) -> None:
    raw = json.loads(_artifact_path().read_bytes())
    mutate(raw)
    _reidentify(raw)
    payload = canonical_json_bytes(raw)
    _install_payload(tmp_path, monkeypatch, payload)

    with pytest.raises(PreregistrationError, match="infrastructure-look ledger"):
        preregistration.load_infrastructure_look_ledger()


@pytest.mark.parametrize("encoding", ("pretty", "bom", "duplicate"))
def test_noncanonical_or_ambiguous_ledger_bytes_refuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    encoding: str,
) -> None:
    raw = json.loads(_artifact_path().read_bytes())
    if encoding == "pretty":
        payload = (json.dumps(raw, indent=2, ensure_ascii=False) + "\n").encode()
    elif encoding == "bom":
        payload = b"\xef\xbb\xbf" + canonical_json_bytes(raw)
    else:
        payload = canonical_json_bytes(raw).replace(
            b"{", b'{"schema":"duplicate",', 1
        )
    _install_payload(tmp_path, monkeypatch, payload)

    with pytest.raises(PreregistrationError, match="infrastructure-look ledger"):
        preregistration.load_infrastructure_look_ledger()


def test_missing_or_linked_ledger_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / preregistration.INFRASTRUCTURE_LOOK_LEDGER_FILENAME
    monkeypatch.setattr(
        preregistration, "INFRASTRUCTURE_LOOK_LEDGER_PATH", missing
    )
    with pytest.raises(PreregistrationError, match="infrastructure-look ledger"):
        preregistration.load_infrastructure_look_ledger()

    link = tmp_path / "linked" / preregistration.INFRASTRUCTURE_LOOK_LEDGER_FILENAME
    link.parent.symlink_to(_artifact_path().parent, target_is_directory=True)
    monkeypatch.setattr(preregistration, "INFRASTRUCTURE_LOOK_LEDGER_PATH", link)
    with pytest.raises(PreregistrationError, match="infrastructure-look ledger"):
        preregistration.load_infrastructure_look_ledger()
