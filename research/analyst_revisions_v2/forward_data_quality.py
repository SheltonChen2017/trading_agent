"""Offline, value-free forward vendor-vintage receipts for development only.

The host-only Massive adapter owns provider I/O and immutable raw captures.
This module derives receipts from pages authenticated by that adapter. It records
when our machine received each version of a Benzinga ID; it cannot establish
when the vendor first published that version, reconstruct overwritten history,
or create the separately gated ARV2-9 prospective paper look.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable

from research.analyst_revisions_v2.accepted_risk_input_pair import MassiveSourceRole
from research.analyst_revisions_v2.canonical import (
    canonical_json_bytes,
    parse_date,
    parse_utc_timestamp,
    require_canonical_json_bytes,
    require_exact_keys,
    require_identifier,
    require_sha256,
    sha256_bytes,
    strict_json_loads,
)


SCHEMA = "arv2-forward-vendor-quality-receipt-v1"
PURPOSE = "development_data_quality_only_not_arv2_9_confirmation"
MAX_WINDOW_DAYS = 32
MAX_OBSERVATIONS = 100_000
MAX_RECEIPT_BYTES = 64 * 1024 * 1024
ROLE_ORDER = (
    MassiveSourceRole.ANALYST_RATINGS,
    MassiveSourceRole.EARNINGS,
    MassiveSourceRole.CORPORATE_GUIDANCE,
)
PRODUCTION_TRANSPORT = "massive_https_bearer_default_session"
TEST_TRANSPORT = "offline_test_double"


class ForwardDataQualityError(ValueError):
    """The development-only forward observation cannot be authenticated."""


def build_receipt_from_authenticated_pages(
    visit_authenticated_pages: Callable[[Callable[[Any], None]], Any],
    expected_manifest_sha256: str,
    *,
    first_event_date: str,
    last_event_date: str,
    expected_transport: str = PRODUCTION_TRANSPORT,
) -> tuple[bytes, str]:
    """Derive canonical receipt bytes from a host-authenticated private capture.

    A short, exact event-date query makes later same-ID recaptures comparable;
    there is no lookback fill or inference from a vendor ``last_updated`` field.
    IDs are represented only by role-scoped SHA-256 digests in the receipt.
    The host-only caller must supply the verified capture-page traversal.
    """
    require_sha256(expected_manifest_sha256, "external capture manifest pin")
    if type(expected_transport) is not str or expected_transport not in (
        PRODUCTION_TRANSPORT,
        TEST_TRANSPORT,
    ):
        raise ForwardDataQualityError("capture transport is not reviewed")
    first = parse_date(first_event_date, "first event date")
    last = parse_date(last_event_date, "last event date")
    if last < first or last - first >= timedelta(days=MAX_WINDOW_DAYS):
        raise ForwardDataQualityError("forward event-date window is invalid or too broad")

    observed: dict[str, dict[str, dict[str, Any]]] = {
        role.value: {} for role in ROLE_ORDER
    }
    row_count = 0

    def visit(page: Any) -> None:
        nonlocal row_count
        query = strict_json_loads(
            page.redacted_query_bytes.decode("utf-8"), "forward capture query"
        )
        if (
            query["requested_first_event_date"] != first_event_date
            or query["requested_last_event_date"] != last_event_date
        ):
            raise ForwardDataQualityError("capture query is not the exact forward window")
        role = page.source_role.value
        for row, raw in zip(page.parsed_rows, page.raw_rows, strict=True):
            row_count += 1
            if row_count > MAX_OBSERVATIONS:
                raise ForwardDataQualityError("forward receipt exceeds observation bound")
            if not first <= parse_date(row.get("date"), "event date") <= last:
                raise ForwardDataQualityError("provider row lies outside exact forward window")
            event_id = row.get("benzinga_id")
            if type(event_id) not in (int, str) or event_id == "":
                raise ForwardDataQualityError("provider event ID is unavailable or malformed")
            event_hash = sha256_bytes(canonical_json_bytes([role, event_id]))
            version_hash = sha256_bytes(raw)
            versions = observed[role].setdefault(event_hash, {})
            times = versions.setdefault(version_hash, [])
            times.append(page.response_received_at)

    source = visit_authenticated_pages(visit)
    if source.manifest_sha256 != expected_manifest_sha256:
        raise ForwardDataQualityError("capture manifest does not match external pin")
    if source.capture_transport != expected_transport:
        raise ForwardDataQualityError("capture transport does not match expectation")
    roles = []
    for role in ROLE_ORDER:
        events = []
        for event_hash, versions in sorted(observed[role.value].items()):
            events.append(
                {
                    "event_key_sha256": event_hash,
                    "versions": [
                        {
                            "version_sha256": version_hash,
                            "first_received_at": min(times),
                            "last_received_at": max(times),
                            "observed_row_count": len(times),
                        }
                        for version_hash, times in sorted(versions.items())
                    ],
                }
            )
        roles.append({"role": role.value, "events": events})
    body = {
        "schema": SCHEMA,
        "purpose": PURPOSE,
        "capture_id": source.capture_id,
        "capture_sha256": source.capture_sha256,
        "capture_manifest_sha256": source.manifest_sha256,
        "capture_started_at": source.capture_started_at,
        "capture_completed_at": source.capture_completed_at,
        "capture_transport": source.capture_transport,
        "first_event_date": first_event_date,
        "last_event_date": last_event_date,
        "source_row_count": source.total_row_count,
        "roles": roles,
        "point_in_time_proven": False,
        "outcome_reads": 0,
        "qc_calls": 0,
        "paper_look_committed": False,
    }
    payload = canonical_json_bytes(body)
    if len(payload) > MAX_RECEIPT_BYTES:
        raise ForwardDataQualityError("forward receipt exceeds byte bound")
    return payload, sha256_bytes(payload)


def _require_receipt(payload: bytes, expected_sha256: str) -> dict[str, Any]:
    require_sha256(expected_sha256, "forward receipt pin")
    if type(payload) is not bytes or len(payload) > MAX_RECEIPT_BYTES:
        raise ForwardDataQualityError("forward receipt bytes are invalid or too large")
    if sha256_bytes(payload) != expected_sha256:
        raise ForwardDataQualityError("forward receipt does not match external pin")
    value = require_canonical_json_bytes(payload, "forward receipt")
    require_exact_keys(value, {
        "schema", "purpose", "capture_id", "capture_sha256",
        "capture_manifest_sha256", "capture_started_at", "capture_completed_at",
        "capture_transport", "first_event_date", "last_event_date",
        "source_row_count", "roles", "point_in_time_proven", "outcome_reads",
        "qc_calls", "paper_look_committed",
    }, "forward receipt")
    if (
        value["schema"] != SCHEMA
        or value["purpose"] != PURPOSE
        or value["point_in_time_proven"] is not False
        or value["paper_look_committed"] is not False
        or type(value["outcome_reads"]) is not int
        or value["outcome_reads"] != 0
        or type(value["qc_calls"]) is not int
        or value["qc_calls"] != 0
        or type(value["source_row_count"]) is not int
        or value["source_row_count"] < 0
        or type(value["roles"]) is not list
        or len(value["roles"]) != len(ROLE_ORDER)
    ):
        raise ForwardDataQualityError("forward receipt authority or role census changed")
    for key in ("capture_sha256", "capture_manifest_sha256"):
        require_sha256(value[key], key)
    require_identifier(value["capture_id"], "capture ID")
    if value["capture_transport"] not in (
        PRODUCTION_TRANSPORT,
        TEST_TRANSPORT,
    ):
        raise ForwardDataQualityError("capture transport is not reviewed")
    started = parse_utc_timestamp(value["capture_started_at"], "capture start")
    completed = parse_utc_timestamp(value["capture_completed_at"], "capture end")
    if started > completed:
        raise ForwardDataQualityError("capture chronology is invalid")
    first = parse_date(value["first_event_date"], "first event date")
    last = parse_date(value["last_event_date"], "last event date")
    if last < first or last - first >= timedelta(days=MAX_WINDOW_DAYS):
        raise ForwardDataQualityError("receipt event window is invalid")
    total_rows = 0
    for actual, expected in zip(value["roles"], ROLE_ORDER, strict=True):
        require_exact_keys(actual, {"role", "events"}, "forward role")
        if actual["role"] != expected.value or type(actual["events"]) is not list:
            raise ForwardDataQualityError("forward role order or shape changed")
        prior_event = ""
        for event in actual["events"]:
            require_exact_keys(event, {"event_key_sha256", "versions"}, "forward event")
            event_hash = require_sha256(event["event_key_sha256"], "event key")
            if event_hash <= prior_event or type(event["versions"]) is not list or not event["versions"]:
                raise ForwardDataQualityError("forward event identity order or versions changed")
            prior_event = event_hash
            prior_version = ""
            for version in event["versions"]:
                require_exact_keys(version, {
                    "version_sha256", "first_received_at", "last_received_at",
                    "observed_row_count",
                }, "forward version")
                version_hash = require_sha256(version["version_sha256"], "version")
                first_seen = parse_utc_timestamp(version["first_received_at"], "first received")
                last_seen = parse_utc_timestamp(version["last_received_at"], "last received")
                count = version["observed_row_count"]
                if (
                    version_hash <= prior_version
                    or first_seen < started or last_seen > completed or first_seen > last_seen
                    or type(count) is not int or count < 1
                ):
                    raise ForwardDataQualityError("forward version observation is invalid")
                prior_version = version_hash
                total_rows += count
    if total_rows != value["source_row_count"] or total_rows > MAX_OBSERVATIONS:
        raise ForwardDataQualityError("forward receipt row census changed")
    return value


def compare_receipts(
    before_bytes: bytes,
    before_sha256: str,
    after_bytes: bytes,
    after_sha256: str,
) -> dict[str, Any]:
    """Count same-ID version changes without inferring revision/deletion cause."""
    before = _require_receipt(before_bytes, before_sha256)
    after = _require_receipt(after_bytes, after_sha256)
    if (
        before_sha256 == after_sha256
        or before["capture_manifest_sha256"] == after["capture_manifest_sha256"]
        or parse_utc_timestamp(before["capture_completed_at"], "before end")
        >= parse_utc_timestamp(after["capture_started_at"], "after start")
        or (before["first_event_date"], before["last_event_date"])
        != (after["first_event_date"], after["last_event_date"])
        or before["capture_transport"] != after["capture_transport"]
    ):
        raise ForwardDataQualityError("forward receipts are not distinct ordered matching captures")
    counts = {}
    for old_role, new_role in zip(before["roles"], after["roles"], strict=True):
        old = {event["event_key_sha256"]: event for event in old_role["events"]}
        new = {event["event_key_sha256"]: event for event in new_role["events"]}
        common = old.keys() & new.keys()
        stable = changed = ambiguous = 0
        for key in common:
            old_versions = old[key]["versions"]
            new_versions = new[key]["versions"]
            if len(old_versions) != 1 or len(new_versions) != 1:
                ambiguous += 1
            elif old_versions[0]["version_sha256"] == new_versions[0]["version_sha256"]:
                stable += 1
            else:
                changed += 1
        counts[old_role["role"]] = {
            "same_id_same_version": stable,
            "same_id_different_version_between_receipts": changed,
            "same_id_ambiguous_multiple_versions": ambiguous,
            "old_only_id_cause_unknown": len(old.keys() - new.keys()),
            "new_only_id_cause_unknown": len(new.keys() - old.keys()),
        }
    return {
        "schema": "arv2-forward-vendor-quality-comparison-v1",
        "purpose": PURPOSE,
        "before_receipt_sha256": before_sha256,
        "after_receipt_sha256": after_sha256,
        "roles": counts,
        "point_in_time_proven": False,
        "return_looks": 0,
        "paper_look_committed": False,
    }
