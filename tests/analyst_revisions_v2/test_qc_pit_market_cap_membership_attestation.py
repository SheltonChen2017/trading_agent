from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc import pit_market_cap_membership_probe as core


RUNTIME_PATH = (
    Path(__file__).parents[2]
    / "research"
    / "analyst_revisions_v2_qc"
    / "pit_market_cap_membership_probe_runtime.py"
)
SAMPLED_CANARY_SESSIONS = (
    "2025-01-02",
    "2025-01-06",
    "2025-01-13",
    "2025-01-21",
    "2025-07-07",
    "2025-07-14",
    "2025-07-21",
    "2025-07-28",
    "2026-01-02",
    "2026-01-05",
    "2026-01-12",
    "2026-01-20",
    "2026-08-24",
    "2026-08-31",
    "2026-09-08",
    "2026-09-14",
)


def _plan_and_projection():
    plan = core.build_pit_market_cap_membership_probe_plan_bytes(
        decision_sessions=SAMPLED_CANARY_SESSIONS,
        calculation_session="2026-09-15",
    )
    projection = core.build_pit_market_cap_membership_probe_qc_projection(
        plan_bytes=plan,
        runtime_source_bytes=RUNTIME_PATH.read_bytes(),
    )
    return plan, projection


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _no_export_capabilities() -> dict[str, bool]:
    return {
        "price_or_return_access_performed": False,
        "outcome_or_result_access_performed": False,
        "orders_or_portfolio_actions_performed": False,
        "raw_rows_emitted": False,
        "security_identifiers_emitted": False,
        "constituent_weights_emitted": False,
        "market_cap_values_emitted": False,
        "full_receipt_or_pointer_export_performed": False,
    }


def _completed_record(plan: bytes, projection) -> dict[str, object]:
    plan_record = json.loads(plan)
    capabilities = _no_export_capabilities()
    capabilities.update(
        {
            "fundamental_history_access_performed": True,
            "etf_constituent_history_access_performed": True,
            "market_cap_field_access_performed": True,
        }
    )
    return {
        "schema": core.ATTESTATION_SCHEMA,
        "status": "completed",
        "contract_sha256": core.CONTRACT_SHA256,
        "plan_id": plan_record["plan_id"],
        "plan_sha256": plan_record["plan_sha256"],
        "project_source_set_sha256": projection.project_source_set_sha256,
        "first_session": plan_record["first_session"],
        "last_session": plan_record["last_session"],
        "decision_session_count": core.EXPECTED_CANARY_SESSION_COUNT,
        "passed_session_count": core.EXPECTED_CANARY_SESSION_COUNT,
        "history_call_count": plan_record["resource_census"][
            "history_call_count"
        ],
        "fetched_source_row_count": 12_000,
        "aggregate": {
            "fundamental_source_member_count": 16_000,
            "fundamental_exact_sid_count": 15_680,
            "fundamental_missing_or_invalid_sid_count": 160,
            "fundamental_duplicate_exact_sid_count": 80,
            "fundamental_duplicate_exact_sid_row_count": 160,
            "positive_market_cap_count": 14_840,
            "null_market_cap_count": 320,
            "nonpositive_market_cap_count": 320,
            "invalid_or_nonfinite_market_cap_count": 200,
            "union_positive_member_count": 8_800,
            "union_positive_market_cap_covered_count": 8_400,
            "union_market_cap_uncovered_count": 400,
        },
        "etf_bounds": {
            "SPY": {
                "minimum_positive_member_count": 500,
                "maximum_positive_member_count": 505,
                "minimum_market_cap_covered_count": 490,
                "maximum_market_cap_covered_count": 500,
            },
            "QQQ": {
                "minimum_positive_member_count": 100,
                "maximum_positive_member_count": 105,
                "minimum_market_cap_covered_count": 95,
                "maximum_market_cap_covered_count": 100,
            },
            "SOXX": {
                "minimum_positive_member_count": 30,
                "maximum_positive_member_count": 35,
                "minimum_market_cap_covered_count": 28,
                "maximum_market_cap_covered_count": 34,
            },
        },
        "union_bounds": {
            "minimum_positive_member_count": 550,
            "maximum_positive_member_count": 560,
            "minimum_market_cap_covered_count": 530,
            "maximum_market_cap_covered_count": 550,
        },
        "availability_extrema": {
            "fundamentals": {
                "earliest_collection_time_local": "2025-01-02T08:00:00.000000",
                "latest_collection_time_local": "2026-09-14T08:00:00.000000",
            },
            "etfs": {
                ticker: {
                    "earliest_collection_end_time_local": (
                        "2024-12-31T00:00:00.000000"
                    ),
                    "latest_collection_end_time_local": (
                        "2026-09-11T00:00:00.000000"
                    ),
                }
                for ticker in core.ETFS
            },
        },
        "receipt_id": "arv2-pit-market-cap-membership-coverage-" + "a" * 24,
        "receipt_sha256": "b" * 64,
        "receipt_byte_count": 32_000,
        "terminal_pointer_sha256": "c" * 64,
        "terminal_pointer_byte_count": 1_024,
        "full_receipt_remains_qc_internal": True,
        "capabilities": capabilities,
    }


def _refusal_record(plan: bytes, projection) -> dict[str, object]:
    plan_record = json.loads(plan)
    return {
        "schema": core.ATTESTATION_SCHEMA,
        "status": "named_refusal",
        "contract_sha256": core.CONTRACT_SHA256,
        "plan_id": plan_record["plan_id"],
        "plan_sha256": plan_record["plan_sha256"],
        "project_source_set_sha256": projection.project_source_set_sha256,
        "safe_reason": "pit_coverage_refused_ValueError_" + "d" * 16,
        "capabilities": _no_export_capabilities(),
    }


def _load(record: dict[str, object]):
    plan, projection = _plan_and_projection()
    return core.load_reviewed_pit_market_cap_membership_coverage_attestation(
        plan_bytes=plan,
        projection=projection,
        summary_bytes=_canonical(record),
    )


def test_completed_attestation_is_exactly_reviewed_and_revalidated():
    plan, projection = _plan_and_projection()
    record = _completed_record(plan, projection)
    reviewed = core.load_reviewed_pit_market_cap_membership_coverage_attestation(
        plan_bytes=plan,
        projection=projection,
        summary_bytes=_canonical(record),
    )

    assert type(reviewed) is core.ReviewedPitMarketCapMembershipCoverageAttestation
    assert reviewed.decision_session_count == 16
    assert reviewed.passed_session_count == 16
    assert reviewed.full_receipt_remains_qc_internal is True
    assert reviewed.outcome_access_performed is False
    assert reviewed.price_or_return_access_performed is False
    assert reviewed.orders_or_portfolio_actions_performed is False
    assert (
        core.require_reviewed_pit_market_cap_membership_coverage_attestation(
            reviewed
        )
        is reviewed
    )


def test_named_refusal_is_exactly_reviewed_and_revalidated():
    plan, projection = _plan_and_projection()
    refusal = core.load_reviewed_pit_market_cap_membership_coverage_attestation(
        plan_bytes=plan,
        projection=projection,
        summary_bytes=_canonical(_refusal_record(plan, projection)),
    )

    assert type(refusal) is core.PitMarketCapMembershipCoverageNamedRefusal
    assert refusal.status == "named_refusal"
    assert (
        core.require_pit_market_cap_membership_coverage_named_refusal(refusal)
        is refusal
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (
            lambda value: value.__setitem__("plan_sha256", "0" * 64),
            "lineage changed",
        ),
        (
            lambda value: value.__setitem__("passed_session_count", 15),
            "completed coverage attestation contract changed",
        ),
        (
            lambda value: value.__setitem__("fetched_source_row_count", 0),
            "fetched source row count escaped its positive bound",
        ),
        (
            lambda value: value["aggregate"].__setitem__(
                "positive_market_cap_count", 14_841
            ),
            "aggregate does not reconcile",
        ),
        (
            lambda value: value["etf_bounds"]["QQQ"].__setitem__(
                "minimum_market_cap_covered_count", 106
            ),
            "QQQ coverage bounds do not reconcile",
        ),
        (
            lambda value: value["union_bounds"].__setitem__(
                "minimum_positive_member_count", 0
            ),
            "ETF union coverage minimum member count escaped its positive bound",
        ),
        (
            lambda value: value["availability_extrema"]["fundamentals"].__setitem__(
                "earliest_collection_time_local", "2025-01-02T10:00:00.000000"
            ),
            "fundamental availability escaped the reviewed PIT bounds",
        ),
        (
            lambda value: value.__setitem__("receipt_sha256", "not-a-hash"),
            "coverage receipt SHA-256 is not SHA-256",
        ),
        (
            lambda value: value["capabilities"].__setitem__(
                "raw_rows_emitted", True
            ),
            "completed coverage attestation contract changed",
        ),
        (
            lambda value: value["capabilities"].__setitem__(
                "raw_rows_emitted", 0
            ),
            "completed coverage attestation contract changed",
        ),
    ),
)
def test_completed_attestation_refuses_load_bearing_mutations(mutation, message):
    plan, projection = _plan_and_projection()
    record = copy.deepcopy(_completed_record(plan, projection))
    mutation(record)

    with pytest.raises(core.PitMarketCapMembershipProbeError, match=message):
        core.load_reviewed_pit_market_cap_membership_coverage_attestation(
            plan_bytes=plan,
            projection=projection,
            summary_bytes=_canonical(record),
        )


@pytest.mark.parametrize(
    "branch",
    (
        "source_equation",
        "class_equation",
        "duplicate_sid_not_above_exact",
        "duplicate_sid_not_above_rows",
        "duplicate_zero_agreement",
    ),
)
def test_each_duplicate_sid_aggregate_reconciliation_guard_is_isolated(branch):
    plan, projection = _plan_and_projection()
    record = copy.deepcopy(_completed_record(plan, projection))
    aggregate = record["aggregate"]
    if branch == "source_equation":
        aggregate["fundamental_source_member_count"] = 16_001
    elif branch == "class_equation":
        aggregate["positive_market_cap_count"] = 14_841
    elif branch == "duplicate_sid_not_above_exact":
        aggregate["fundamental_source_member_count"] = 31_521
        aggregate["fundamental_duplicate_exact_sid_count"] = 15_681
        aggregate["fundamental_duplicate_exact_sid_row_count"] = 15_681
    elif branch == "duplicate_sid_not_above_rows":
        aggregate["fundamental_duplicate_exact_sid_count"] = 161
    else:
        aggregate["fundamental_duplicate_exact_sid_count"] = 0

    with pytest.raises(
        core.PitMarketCapMembershipProbeError,
        match="coverage attestation aggregate does not reconcile",
    ):
        core.load_reviewed_pit_market_cap_membership_coverage_attestation(
            plan_bytes=plan,
            projection=projection,
            summary_bytes=_canonical(record),
        )


def test_attestation_refuses_noncanonical_and_oversized_payloads():
    plan, projection = _plan_and_projection()
    payload = _canonical(_completed_record(plan, projection))
    with pytest.raises(core.PitMarketCapMembershipProbeError, match="canonical JSON"):
        core.load_reviewed_pit_market_cap_membership_coverage_attestation(
            plan_bytes=plan,
            projection=projection,
            summary_bytes=payload + b"\n",
        )
    with pytest.raises(core.PitMarketCapMembershipProbeError, match="byte bound"):
        core.load_reviewed_pit_market_cap_membership_coverage_attestation(
            plan_bytes=plan,
            projection=projection,
            summary_bytes=b" " * (core.MAX_SUMMARY_CHARACTERS + 1),
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (
            lambda value: value.__setitem__("safe_reason", "raw provider error"),
            "named-refusal attestation contract changed",
        ),
        (
            lambda value: value["capabilities"].__setitem__(
                "outcome_or_result_access_performed", True
            ),
            "named-refusal attestation contract changed",
        ),
    ),
)
def test_named_refusal_refuses_unsafe_details_or_capability_claims(
    mutation, message
):
    plan, projection = _plan_and_projection()
    record = _refusal_record(plan, projection)
    mutation(record)

    with pytest.raises(core.PitMarketCapMembershipProbeError, match=message):
        core.load_reviewed_pit_market_cap_membership_coverage_attestation(
            plan_bytes=plan,
            projection=projection,
            summary_bytes=_canonical(record),
        )
