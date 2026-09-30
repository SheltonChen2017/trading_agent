"""Inert v2 continuation plan for the halted two-quarter SEC parent campaign.

This module performs no transport and creates no output root.  It consumes the
independent, read-only source-union replay and pins the ordered source classes
and first-dispatch inventory in a versioned plan.  The executable journal,
durable request-start transition, retry state machine, and completed-root
verifier are deliberately absent; this plan must not be treated as a runner.
"""
from __future__ import annotations

from pathlib import Path
import re

from data.hashing import hash_payload
from research.insider_buying_sec_acquisition import (
    SecPilotError, _plain_path, _refuse_output_overlap,
)
import research.insider_buying_sec_all_form4_parent_campaign as campaign
import research.insider_buying_sec_all_form4_parent_recovery_preflight as partial
import research.insider_buying_sec_all_form4_parent_recovery_union as union
import research.insider_buying_sec_parent_refusal_diagnostic as diagnostic


RECOVERY_CAMPAIGN_VERSION = "INSETF-SEC-ALL-FORM4-PARENTS-RECOVERY-CAMPAIGN-v2"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SOURCE_CLASSES = (
    "prior_completed", "accepted_diagnostic", "remaining_selected_reuse",
    "later_unattempted",
)
_OUTPUT_NAME = "all-form4-parents-recovery-v2"


class RecoveryCampaignPlanError(ValueError):
    """The inert v2 continuation plan refused a source or output path."""


def _refuse(reason: str) -> None:
    raise RecoveryCampaignPlanError(f"REFUSED: {reason}")


def _sha(value: object) -> bool:
    return type(value) is str and _SHA.fullmatch(value) is not None


def _new_output_path(
    output_root: str | Path, *, protected_roots: tuple[str | Path, ...],
) -> Path:
    """Check a proposed immutable destination without creating any member."""
    try:
        output = _plain_path(output_root, must_exist=False)
        if output.exists() or output.is_symlink():
            _refuse("v2 output root already exists")
        for protected in (*protected_roots, Path(__file__).resolve().parents[1]):
            _refuse_output_overlap(output, _plain_path(protected, must_exist=True))
        return output
    except SecPilotError as exc:
        raise RecoveryCampaignPlanError("REFUSED: v2 output path is unsafe") from exc


def _source_layout(
    plan: campaign.CampaignPlan, receipt: dict[str, object],
) -> tuple[list[str], list[dict[str, str]]]:
    """Recompute both union hashes from the original source order."""
    if (type(plan) is not campaign.CampaignPlan
            or type(receipt) is not dict
            or receipt.get("kind") != union.UNION_VERSION + "/read-only-preflight"):
        _refuse("source-union plan interface is malformed")
    payload = plan.to_payload()
    total = len(plan.requests)
    old_count = receipt.get("prior_completed_count")
    if (type(old_count) is not int or not 0 <= old_count < total
            or receipt.get("total_parents") != total
            or receipt.get("manifest_sha256") != plan.manifest_sha256
            or receipt.get("request_inventory_sha256")
            != payload["request_inventory_sha256"]
            or receipt.get("accepted_diagnostic_count") != 1
            or receipt.get("refused_parent_total_attempt_count") != 2
            or receipt.get("sec_dispatches") != 0
            or any(receipt.get(name) is not False for name in (
                "complete_parent_bytes_acquired", "source_authenticated",
                "canonical_evidence", "point_in_time_data",
            ))
            or receipt.get("research_looks") != 0
            or receipt.get("qc_jobs") != 0):
        _refuse("source-union denominator or authority flags changed")
    for name in (
        "prior_campaign_plan_sha256", "diagnostic_report_sha256",
        "source_assignment_sha256",
        "later_unattempted_request_inventory_sha256",
    ):
        if not _sha(receipt.get(name)):
            _refuse("source-union digest is malformed")
    for name in ("prior_capture_git_commit", "diagnostic_capture_git_commit"):
        value = receipt.get(name)
        if type(value) is not str or _COMMIT.fullmatch(value) is None:
            _refuse("source-union code commit is malformed")
    for name in ("prior_shard_report_sha256s", "prior_shard_journal_sha256s"):
        pair = receipt.get(name)
        if type(pair) is not tuple or len(pair) != 2 or not all(map(_sha, pair)):
            _refuse("source-union prior shard anchors are malformed")

    selected = {item.accession_number for item in plan.reuses}
    if plan.requests[old_count].accession_number in selected:
        _refuse("accepted diagnostic overlaps a selected reuse")
    classes = ["prior_completed"] * old_count + ["accepted_diagnostic"]
    dispatch: list[dict[str, str]] = []
    for request in plan.requests[old_count + 1:]:
        if request.accession_number in selected:
            classes.append("remaining_selected_reuse")
        else:
            classes.append("later_unattempted")
            dispatch.append(request.to_payload())
    old_selected = sum(item.accession_number in selected
                       for item in plan.requests[:old_count])
    later_selected = classes.count("remaining_selected_reuse")
    prior_reused = receipt.get("prior_selected_reused_count")
    prior_acquired = receipt.get("prior_newly_acquired_count")
    prior_attempts = receipt.get("prior_attempt_count")
    if (len(classes) != total or not set(classes) <= set(_SOURCE_CLASSES)
            or any(type(value) is not int or value < 0 for value in (
                prior_reused, prior_acquired, prior_attempts,
                receipt.get("remaining_selected_reuse_count"),
                receipt.get("later_unattempted_request_count"),
            ))
            or prior_reused + prior_acquired != old_count
            or prior_attempts < prior_acquired + 1
            or old_selected != receipt.get("prior_selected_reused_count")
            or later_selected != receipt.get("remaining_selected_reuse_count")
            or old_selected + later_selected != len(plan.reuses)
            or len(dispatch) != receipt.get("later_unattempted_request_count")
            or old_count + 1 + later_selected + len(dispatch) != total
            or hash_payload(classes) != receipt.get("source_assignment_sha256")
            or hash_payload(dispatch)
            != receipt.get("later_unattempted_request_inventory_sha256")):
        _refuse("source-union assignment or dispatch inventory changed")
    return classes, dispatch


def _inert_plan(
    plan: campaign.CampaignPlan, receipt: dict[str, object],
    output_root: str | Path, *, protected_roots: tuple[str | Path, ...],
) -> dict[str, object]:
    """Build a bounded, aggregate-only plan from a verified union receipt."""
    classes, dispatch = _source_layout(plan, receipt)
    output = _new_output_path(output_root, protected_roots=protected_roots)
    shards: list[dict[str, object]] = []
    for index, start in enumerate(range(0, len(plan.requests), plan.shard_size)):
        requests = plan.requests[start:start + plan.shard_size]
        source_classes = classes[start:start + len(requests)]
        later = [request.to_payload() for request, source in zip(
            requests, source_classes, strict=True,
        ) if source == "later_unattempted"]
        shards.append({
            "name": f"shard-{index:04d}", "start": start,
            "count": len(requests),
            "request_inventory_sha256": hash_payload(
                [request.to_payload() for request in requests]
            ),
            "source_assignment_sha256": hash_payload(source_classes),
            "later_unattempted_request_inventory_sha256": hash_payload(later),
            "prior_completed_count": source_classes.count("prior_completed"),
            "accepted_diagnostic_count": source_classes.count("accepted_diagnostic"),
            "remaining_selected_reuse_count": source_classes.count(
                "remaining_selected_reuse"
            ),
            "later_unattempted_request_count": len(later),
        })
    if (len(shards) > campaign.MAX_SHARDS
            or sum(shard["later_unattempted_request_count"] for shard in shards)
            != len(dispatch)
            or sum(shard["count"] for shard in shards) != len(plan.requests)):
        _refuse("v2 shard layout exceeds its frozen population")
    body: dict[str, object] = {
        "kind": RECOVERY_CAMPAIGN_VERSION + "/inert-preflight",
        "source_scope": plan.scope,
        "manifest_sha256": receipt["manifest_sha256"],
        "request_inventory_sha256": receipt["request_inventory_sha256"],
        "source_assignment_sha256": receipt["source_assignment_sha256"],
        "later_unattempted_request_inventory_sha256": receipt[
            "later_unattempted_request_inventory_sha256"
        ],
        "prior_capture_git_commit": receipt["prior_capture_git_commit"],
        "prior_campaign_plan_sha256": receipt["prior_campaign_plan_sha256"],
        "prior_shard_report_sha256s": list(receipt["prior_shard_report_sha256s"]),
        "prior_shard_journal_sha256s": list(receipt["prior_shard_journal_sha256s"]),
        "diagnostic_capture_git_commit": receipt["diagnostic_capture_git_commit"],
        "diagnostic_report_sha256": receipt["diagnostic_report_sha256"],
        "proposed_output_root": str(output),
        "total_parents": len(plan.requests),
        "prior_completed_count": receipt["prior_completed_count"],
        "accepted_diagnostic_count": 1,
        "remaining_selected_reuse_count": receipt["remaining_selected_reuse_count"],
        "later_unattempted_request_count": len(dispatch),
        "shard_size": plan.shard_size,
        "shards": shards,
        "required_runtime_contract_unimplemented": {
            "durable_request_start_before_transport": True,
            "unresolved_request_start": "halt_without_redispatch",
            "max_attempts_per_later_parent": 3,
            "safe_retry_http_statuses": [500, 502, 503, 504],
            "ambiguous_transport_result": "halt_without_redispatch",
            "immutable_new_root": True,
            "offline_completed_root_verifier": True,
        },
        "transport_implemented": False,
        "output_written": False,
        "completed_root_verifier_implemented": False,
        "complete_parent_bytes_acquired": False,
        "source_authenticated": False,
        "canonical_evidence": False,
        "point_in_time_data": False,
        "research_looks": 0,
        "qc_jobs": 0,
    }
    return {**body, "plan_sha256": hash_payload(body)}


def preflight_synthetic_recovery_continuation(
    plan: campaign.CampaignPlan,
    prior_campaign_root: str | Path,
    diagnostic_root: str | Path,
    selected_root: str | Path,
    output_root: str | Path,
    *, prior_expectation: partial.PartialCampaignExpectation,
    diagnostic_capture_git_commit: str,
    expected_diagnostic_report_sha256: str,
) -> dict[str, object]:
    """Offline, injected-fixture preflight; it cannot issue an SEC request."""
    if type(plan) is not campaign.CampaignPlan or plan.scope != "synthetic_test_manifest":
        _refuse("synthetic v2 preflight needs a synthetic-only source plan")
    receipt = union.preflight_source_union(
        plan, prior_campaign_root, diagnostic_root, selected_root,
        prior_expectation=prior_expectation,
        diagnostic_capture_git_commit=diagnostic_capture_git_commit,
        expected_diagnostic_report_sha256=expected_diagnostic_report_sha256,
    )
    return _inert_plan(
        plan, receipt, output_root,
        protected_roots=(prior_campaign_root, diagnostic_root, selected_root),
    )


def preflight_observed_recovery_continuation(
    raw_q4_directory: str | Path, parsed_q4_directory: str | Path,
    raw_q1_directory: str | Path, parsed_q1_directory: str | Path,
    exact16_pilot_root: str | Path, selected_root: str | Path,
    prior_campaign_root: str | Path, diagnostic_root: str | Path,
    *, diagnostic_capture_git_commit: str,
    expected_diagnostic_report_sha256: str,
) -> dict[str, object]:
    """Exact real-source planning gate; never publishes or dispatches."""
    receipt = union.preflight_observed_all_form4_parent_recovery_union(
        raw_q4_directory, parsed_q4_directory, raw_q1_directory,
        parsed_q1_directory, exact16_pilot_root, selected_root,
        prior_campaign_root, diagnostic_root,
        diagnostic_capture_git_commit=diagnostic_capture_git_commit,
        expected_diagnostic_report_sha256=expected_diagnostic_report_sha256,
    )
    plan = campaign._build_real_plan(
        raw_q4_directory, parsed_q4_directory, raw_q1_directory,
        parsed_q1_directory, exact16_pilot_root, selected_root,
    )
    prior = _plain_path(prior_campaign_root, must_exist=True)
    output = prior.parent / _OUTPUT_NAME
    result = _inert_plan(
        plan, receipt, output,
        protected_roots=(raw_q4_directory, parsed_q4_directory,
                         raw_q1_directory, parsed_q1_directory,
                         exact16_pilot_root, selected_root,
                         prior_campaign_root, diagnostic_root),
    )
    if (result["total_parents"] != 99_394
            or result["prior_completed_count"] != 9_539
            or result["accepted_diagnostic_count"] != 1
            or result["remaining_selected_reuse_count"] != 8_139
            or result["later_unattempted_request_count"] != 81_715
            or len(result["shards"]) != 13):
        _refuse("real v2 plan differs from the frozen continuation")
    return result


__all__ = [
    "RecoveryCampaignPlanError", "preflight_synthetic_recovery_continuation",
    "preflight_observed_recovery_continuation",
]
