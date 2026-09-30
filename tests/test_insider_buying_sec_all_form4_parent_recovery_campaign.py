"""Invented identifiers only; the v2 continuation preflight has no transport."""
from __future__ import annotations

from dataclasses import replace

import pytest

from data.hashing import hash_bytes, hash_payload
import research.insider_buying_sec_all_form4_parent_campaign as campaign
import research.insider_buying_sec_all_form4_parent_recovery_campaign as recovery
import research.insider_buying_sec_all_form4_parent_recovery_union as union


def _request(number: int) -> campaign.CampaignRequest:
    accession = f"0000000001-23-{number:06d}"
    return campaign.CampaignRequest(
        period="2023Q1", accession_number=accession, form_type="4",
        filing_date="2023-01-03", issuer_cik="0000000001",
        archive_path=f"edgar/data/1/{accession}.txt",
        submission_row_id=hash_bytes(f"invented-{number}".encode()),
        parsed_lineage_hash="b" * 64, master_source_sha256="a" * 64,
    )


def _plan(*, total: int = 7, shard_size: int = 3) -> campaign.CampaignPlan:
    requests = tuple(_request(number) for number in range(1, total + 1))
    reuses = tuple(campaign.CampaignReuse(
        accession_number=requests[index].accession_number,
        object_sha256=hash_bytes(f"invented-parent-{index}".encode()),
        object_size_bytes=100, prior_report_sha256="e" * 64,
    ) for index in (0, 3, 5))
    return campaign.CampaignPlan(
        scope="synthetic_test_manifest", manifest_sha256="c" * 64,
        requests=requests, reuses=reuses, shard_size=shard_size,
    )


def _union_receipt(plan: campaign.CampaignPlan) -> dict[str, object]:
    selected = {item.accession_number for item in plan.reuses}
    classes = ["prior_completed"] * 4 + ["accepted_diagnostic"]
    later = []
    for request in plan.requests[5:]:
        if request.accession_number in selected:
            classes.append("remaining_selected_reuse")
        else:
            classes.append("later_unattempted")
            later.append(request.to_payload())
    return {
        "kind": union.UNION_VERSION + "/read-only-preflight",
        "manifest_sha256": plan.manifest_sha256,
        "request_inventory_sha256": plan.to_payload()["request_inventory_sha256"],
        "prior_capture_git_commit": "d" * 40,
        "prior_campaign_plan_sha256": "1" * 64,
        "prior_shard_report_sha256s": ("2" * 64, "3" * 64),
        "prior_shard_journal_sha256s": ("4" * 64, "5" * 64),
        "diagnostic_capture_git_commit": "f" * 40,
        "diagnostic_report_sha256": "6" * 64,
        "source_assignment_sha256": hash_payload(classes),
        "later_unattempted_request_inventory_sha256": hash_payload(later),
        "total_parents": len(plan.requests),
        "prior_completed_count": 4,
        "prior_selected_reused_count": 2,
        "prior_newly_acquired_count": 2,
        "prior_attempt_count": 3,
        "accepted_diagnostic_count": 1,
        "refused_parent_total_attempt_count": 2,
        "remaining_selected_reuse_count": 1,
        "later_unattempted_request_count": len(later),
        "sec_dispatches": 0,
        "complete_parent_bytes_acquired": False,
        "source_authenticated": False,
        "canonical_evidence": False,
        "point_in_time_data": False,
        "research_looks": 0,
        "qc_jobs": 0,
    }


@pytest.fixture
def source_paths(tmp_path):
    roots = tuple(tmp_path / name for name in ("prior", "diagnostic", "selected"))
    for root in roots:
        root.mkdir()
    return roots


def _preflight(monkeypatch, plan, source_paths, output, receipt):
    calls = []

    def verified_union(*args, **kwargs):
        calls.append((args, kwargs))
        return receipt

    monkeypatch.setattr(union, "preflight_source_union", verified_union)
    result = recovery.preflight_synthetic_recovery_continuation(
        plan, *source_paths, output,
        prior_expectation=object(),
        diagnostic_capture_git_commit="f" * 40,
        expected_diagnostic_report_sha256="6" * 64,
    )
    assert len(calls) == 1
    assert calls[0][0][0] is plan
    return result


def test_inert_v2_plan_pins_complete_order_and_only_new_dispatches(
    monkeypatch, tmp_path, source_paths,
):
    plan = _plan()
    output = tmp_path / "new-v2-root"
    result = _preflight(monkeypatch, plan, source_paths, output, _union_receipt(plan))
    assert result["kind"] == recovery.RECOVERY_CAMPAIGN_VERSION + "/inert-preflight"
    assert result["plan_sha256"] == hash_payload({
        key: value for key, value in result.items() if key != "plan_sha256"
    })
    assert [shard["count"] for shard in result["shards"]] == [3, 3, 1]
    assert [shard["later_unattempted_request_count"] for shard in result["shards"]] == [0, 0, 1]
    assert [shard["accepted_diagnostic_count"] for shard in result["shards"]] == [0, 1, 0]
    assert result["later_unattempted_request_count"] == 1
    assert result["transport_implemented"] is False
    assert result["completed_root_verifier_implemented"] is False
    assert result["output_written"] is False
    assert result["required_runtime_contract_unimplemented"]["unresolved_request_start"] == (
        "halt_without_redispatch"
    )
    assert not output.exists()


def test_thirteen_shard_boundary_preserves_all_dispatchable_rows(
    monkeypatch, tmp_path, source_paths,
):
    # Twenty-five invented requests at two per shard model the real 13-shard
    # boundary without claiming to have replayed any SEC data.
    plan = _plan(total=25, shard_size=2)
    result = _preflight(
        monkeypatch, plan, source_paths, tmp_path / "new-v2-root",
        _union_receipt(plan),
    )
    assert len(result["shards"]) == 13
    assert [row["start"] for row in result["shards"]] == list(range(0, 25, 2))
    assert [row["count"] for row in result["shards"]] == [2] * 12 + [1]
    assert sum(row["later_unattempted_request_count"] for row in result["shards"]) == 19
    assert result["later_unattempted_request_count"] == 19


@pytest.mark.parametrize("change", [
    {"source_assignment_sha256": "0" * 64},
    {"later_unattempted_request_inventory_sha256": "0" * 64},
    {"later_unattempted_request_count": 2},
    {"remaining_selected_reuse_count": 2},
    {"prior_selected_reused_count": 1},
    {"accepted_diagnostic_count": 0},
    {"complete_parent_bytes_acquired": True},
    {"diagnostic_report_sha256": "invalid"},
])
def test_changed_union_accounting_refuses_before_creating_output(
    monkeypatch, tmp_path, source_paths, change,
):
    plan = _plan()
    output = tmp_path / "new-v2-root"
    receipt = {**_union_receipt(plan), **change}
    monkeypatch.setattr(union, "preflight_source_union", lambda *_, **__: receipt)
    with pytest.raises(recovery.RecoveryCampaignPlanError, match="REFUSED"):
        recovery.preflight_synthetic_recovery_continuation(
            plan, *source_paths, output,
            prior_expectation=object(), diagnostic_capture_git_commit="f" * 40,
            expected_diagnostic_report_sha256="6" * 64,
        )
    assert not output.exists()


@pytest.mark.parametrize("path_kind", ["existing", "inside_prior", "inside_lane"])
def test_v2_plan_refuses_reused_or_overlapping_destination(
    monkeypatch, tmp_path, source_paths, path_kind,
):
    plan = _plan()
    if path_kind == "existing":
        output = tmp_path / "existing"
        output.mkdir()
    elif path_kind == "inside_prior":
        output = source_paths[0] / "child"
    else:
        output = recovery.Path(__file__).resolve().parents[1] / "unexpected-v2-root"
    monkeypatch.setattr(union, "preflight_source_union", lambda *_, **__: _union_receipt(plan))
    with pytest.raises(recovery.RecoveryCampaignPlanError, match="REFUSED"):
        recovery.preflight_synthetic_recovery_continuation(
            plan, *source_paths, output,
            prior_expectation=object(), diagnostic_capture_git_commit="f" * 40,
            expected_diagnostic_report_sha256="6" * 64,
        )


def test_source_union_refusal_stops_plan_without_output(monkeypatch, tmp_path, source_paths):
    plan = _plan()
    output = tmp_path / "new-v2-root"

    def refuse(*_args, **_kwargs):
        raise union.RecoveryUnionError("REFUSED: diagnostic body is not accepted")

    monkeypatch.setattr(union, "preflight_source_union", refuse)
    with pytest.raises(union.RecoveryUnionError, match="REFUSED"):
        recovery.preflight_synthetic_recovery_continuation(
            plan, *source_paths, output,
            prior_expectation=object(), diagnostic_capture_git_commit="f" * 40,
            expected_diagnostic_report_sha256="6" * 64,
        )
    assert not output.exists()


def test_unselected_diagnostic_is_required(monkeypatch, tmp_path, source_paths):
    plan = _plan()
    extra = campaign.CampaignReuse(
        accession_number=plan.requests[4].accession_number,
        object_sha256="7" * 64, object_size_bytes=100,
        prior_report_sha256="e" * 64,
    )
    altered = replace(plan, reuses=tuple(sorted(
        (*plan.reuses, extra), key=lambda item: item.accession_number,
    )))
    monkeypatch.setattr(union, "preflight_source_union", lambda *_, **__: _union_receipt(altered))
    with pytest.raises(recovery.RecoveryCampaignPlanError, match="REFUSED"):
        recovery.preflight_synthetic_recovery_continuation(
            altered, *source_paths, tmp_path / "new-v2-root",
            prior_expectation=object(), diagnostic_capture_git_commit="f" * 40,
            expected_diagnostic_report_sha256="6" * 64,
        )
