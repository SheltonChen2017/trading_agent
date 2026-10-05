"""Shared aggregate-only contract for TPR-D0 structural reports (TPR-CR16-001).

The report is committed and pushed, so it may carry counts, lineage hashes and
fixed labels only.  Checking that raw provider values are absent is not
enough: the auditor holds per-row identifier digests in memory, and a digest
is derived row-level data that anyone holding the dataset can join back.
This contract closes the report's whole key tree and leaf types instead, and
both the synthetic behavioral test and the committed real artifact must pass
it.
"""
from __future__ import annotations

import re
from typing import Any, Callable

import pytest

from research.target_price_revisions_development import plan as plans

REPORT_TOP_LEVEL_KEYS = frozenset({
    "accepted_risks", "audit_as_of_utc", "auditor_code_sha256", "canonical_admission",
    "confirmatory_alpha", "development_looks", "identifiers", "input", "interpretation",
    "outcome_reads", "plan_sha256", "point_in_time_data", "provider_requests", "qc_attempts",
    "schema", "source_manifest_sha256", "trading_authority", "years",
})
_EXACT_KEYS = {
    "input": frozenset({"pages", "rows", "bytes"}),
    "identifiers": frozenset({"missing_or_invalid", "unique", "repeated_groups", "extra_occurrences"}),
    "interpretation": frozenset({"targets", "adjustment", "clocks", "horizon", "identifiers", "next"}),
}
_AUDITOR_MODULES = frozenset(
    "research/target_price_revisions_development/" + name
    for name in ("__init__.py", "plan.py", "structural.py", "__main__.py")
)
_SHA256 = re.compile(r"[0-9a-f]{64}")
# Frozen literal, deliberately NOT derived from ``structural._bucket()``: a
# shape derived from the code would follow any production change, including a
# new key that smuggles data.  ``test_frozen_bucket_shape_matches_the_auditor``
# fails if the auditor's bucket ever diverges, forcing a visible contract edit.
_TARGET_STATES = frozenset({"missing", "null", "invalid", "nonfinite", "zero", "negative", "positive"})
FROZEN_BUCKET_SHAPE = {
    "rows": None,
    "targets": {field: dict.fromkeys(_TARGET_STATES) for field in (
        "price_target", "previous_price_target",
        "adjusted_price_target", "previous_adjusted_price_target")},
    "actions": dict.fromkeys(("raises", "lowers", "maintains", "announces", "sets",
                              "missing", "invalid", "unknown")),
    "currencies": dict.fromkeys(("USD", "CAD", "EUR", "GBP", "CHF", "JPY", "AUD", "CNY", "HKD",
                                 "other_code", "missing", "invalid")),
    "pairs": dict.fromkeys(("positive_raw", "positive_adjusted", "both_positive",
                            "direction_agrees", "direction_disagrees", "raise_action_conflict",
                            "lower_action_conflict", "maintain_action_conflict")),
    "clocks": dict.fromkeys(("event_date_invalid", "event_time_missing", "event_time_invalid",
                             "event_time_valid", "update_missing", "update_invalid",
                             "update_before_event_day", "update_same_event_day",
                             "update_later_event_day", "update_after_capture",
                             "event_date_partition_mismatch")),
    "horizon_probes": dict.fromkeys(("price_target_horizon_present",
                                     "previous_price_target_horizon_present")),
}


def _key_tree(value: Any) -> Any:
    return {key: _key_tree(child) for key, child in value.items()} if type(value) is dict else None


def _assert_counts(value: Any, path: tuple[str, ...]) -> None:
    if type(value) is dict:
        for key, child in value.items():
            _assert_counts(child, (*path, key))
        return
    # ``type`` rather than ``isinstance``: a bool must not pass as a count.
    assert type(value) is int and value >= 0, f"non-count leaf at {'.'.join(path)}"


def assert_aggregate_only(report: dict[str, Any]) -> None:
    """Refuse any report shape that could carry row-level or derived row data."""
    assert set(report) == REPORT_TOP_LEVEL_KEYS, sorted(set(report) ^ REPORT_TOP_LEVEL_KEYS)
    for key, expected in _EXACT_KEYS.items():
        assert set(report[key]) == expected, key
    # Every year bucket must have exactly the frozen key tree, so a new key
    # cannot smuggle data even as an integer.
    for year, bucket in report["years"].items():
        assert re.fullmatch(r"20[0-9]{2}", year), year
        assert _key_tree(bucket) == FROZEN_BUCKET_SHAPE, f"year {year} bucket shape changed"
    for key in ("input", "identifiers", "years"):
        _assert_counts(report[key], (key,))
    for key in ("outcome_reads", "provider_requests", "qc_attempts", "development_looks"):
        assert type(report[key]) is int, key
    for key in ("canonical_admission", "point_in_time_data", "trading_authority"):
        assert type(report[key]) is bool, key
    # The only strings are lineage digests, fixed labels and fixed prose.
    for key in ("plan_sha256", "source_manifest_sha256"):
        assert type(report[key]) is str and _SHA256.fullmatch(report[key]), key
    assert set(report["auditor_code_sha256"]) == _AUDITOR_MODULES
    assert all(type(v) is str and _SHA256.fullmatch(v) for v in report["auditor_code_sha256"].values())
    assert report["accepted_risks"] == plans.ACCEPTED_RISKS
    assert all(type(text) is str for text in report["interpretation"].values())
    for key in ("schema", "audit_as_of_utc", "confirmatory_alpha"):
        assert type(report[key]) is str, key


@pytest.fixture
def aggregate_only() -> Callable[[dict[str, Any]], None]:
    return assert_aggregate_only


@pytest.fixture
def frozen_bucket_contract() -> tuple[Any, Callable[[Any], Any]]:
    return FROZEN_BUCKET_SHAPE, _key_tree
