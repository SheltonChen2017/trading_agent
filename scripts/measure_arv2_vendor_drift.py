"""Count vendor snapshot changes; no prices, QC, returns or input replacement.

This measures between-capture drift, not original event-time truth or the
effect of corrections on performance. IDs and provider values stay private.
Capture itself uses the existing capture_arv2_massive CLI, separately.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from decimal import Decimal, localcontext
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).absolute().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import capture_arv2_massive as capture
from research.analyst_revisions_v2.canonical import (
    canonical_json_bytes, parse_date, require_sha256, sha256_bytes,
    strict_json_loads,
)

FIRST = "2026-08-01"
LAST = "2026-09-16"
OLD_PATH = capture.DEFAULT_ARTIFACT_ROOT / "arv2-massive-three-role-20260917T051836493365Z"
OLD_SHA = "3384e9745c3093eb203997d4a98057ae2d066180add5e0367c4c3687a50d83ea"
RATING_FIELDS = frozenset({"rating", "previous_rating", "rating_action",
                         "price_target", "previous_price_target", "price_target_action"})
CLOCK_IDENTITY_FIELDS = frozenset({"date", "time", "ticker", "benzinga_analyst_id", "benzinga_firm_id"})


def _provider_bytes(value):
    # Reuse the capture's exact JSON-number/Decimal representation. Never
    # convert provider decimals to binary floats or stringify their values.
    return capture._canonical_json_value(value).encode("utf-8")


def _index(rows, first=FIRST, last=LAST):
    """Retain exact variants per ID; never pick a winner for a reused ID."""
    start, end = parse_date(first, "first"), parse_date(last, "last")
    if start > end:
        raise ValueError("drift date window is reversed")
    index = {}
    row_count = 0
    for row in rows:
        if type(row) is not dict:
            raise ValueError("drift row must be an object")
        day = parse_date(row.get("date"), "drift event date")
        if not start <= day <= end:
            continue
        identity = row.get("benzinga_id")
        if type(identity) not in (int, str) or identity == "" or identity is None:
            raise ValueError("drift ID is unavailable or malformed")
        key = _provider_bytes(identity)  # int/string collisions remain separate.
        index.setdefault(key, set()).add(_provider_bytes(row))
        row_count += 1
    return index, row_count


def _percent(count, denominator):
    if denominator == 0:
        return None
    with localcontext() as context:
        context.prec = 40
        return str((Decimal(count) * 100 / Decimal(denominator)).quantize(Decimal("0.000001")))


def compare_role(old, new, old_row_count, new_row_count):
    """Compare only single-variant common IDs; disclose all other census."""
    common = old.keys() & new.keys()
    comparable = {key for key in common if len(old[key]) == len(new[key]) == 1}
    fields = Counter()
    unchanged = semantic = timestamp_only = any_changed = rating_changed = clock_changed = 0
    for key in sorted(comparable):
        before = strict_json_loads(next(iter(old[key])).decode("utf-8"), "old drift row")
        after = strict_json_loads(next(iter(new[key])).decode("utf-8"), "new drift row")
        changed = {field for field in before.keys() | after.keys()
                   if (field in before) != (field in after)
                   or (field in before and field in after
                       and _provider_bytes(before[field]) != _provider_bytes(after[field]))}
        fields.update(changed)
        if not changed:
            unchanged += 1
            continue
        any_changed += 1
        if changed - {"last_updated"}:
            semantic += 1
        else:
            timestamp_only += 1
        rating_changed += bool(changed & RATING_FIELDS)
        clock_changed += bool(changed & CLOCK_IDENTITY_FIELDS)
    return {
        "old_rows_in_window": old_row_count, "new_rows_in_window": new_row_count,
        "old_distinct_ids": len(old), "new_distinct_ids": len(new),
        "common_ids": len(common), "comparable_single_variant_common_ids": len(comparable),
        "ambiguous_common_ids_excluded": len(common - comparable),
        "old_ambiguous_ids": sum(len(value) > 1 for value in old.values()),
        "new_ambiguous_ids": sum(len(value) > 1 for value in new.values()),
        "old_repeated_identical_rows": old_row_count - sum(map(len, old.values())),
        "new_repeated_identical_rows": new_row_count - sum(map(len, new.values())),
        "old_only_ids": len(old.keys() - new.keys()), "new_only_ids": len(new.keys() - old.keys()),
        "unchanged_common_ids": unchanged, "any_changed_common_ids": any_changed,
        "semantic_changed_common_ids": semantic, "last_updated_only_changed_common_ids": timestamp_only,
        "rating_or_target_changed_common_ids": rating_changed,
        "clock_or_identity_changed_common_ids": clock_changed,
        "semantic_change_percent_of_comparable_ids": _percent(semantic, len(comparable)),
        "changed_field_counts": dict(sorted(fields.items())),
    }


def read_capture(path, expected_sha, *, expected_transport=capture.PRODUCTION_TRANSPORT):
    require_sha256(expected_sha, "drift expected source manifest")
    indexes = {role.value: {} for role in capture.ROLE_ORDER}
    row_counts = Counter()

    def visit(page):
        query = strict_json_loads(page.redacted_query_bytes.decode("utf-8"), "drift query")
        if query["requested_first_event_date"] > FIRST or query["requested_last_event_date"] < LAST:
            raise ValueError("capture query does not cover the complete drift window")
        index, count = _index(page.parsed_rows)
        role = page.source_role.value
        for key, variants in index.items():
            indexes[role].setdefault(key, set()).update(variants)
        row_counts[role] += count

    summary = capture._visit_authenticated_massive_capture_pages_for_bridge(
        Path(path).absolute(), expected_transport=expected_transport, visit_page=visit)
    if summary.manifest_sha256 != expected_sha:
        raise ValueError("drift source manifest does not match external pin")
    return summary, indexes, row_counts


def compare_captures(old_path, old_sha, new_path, new_sha, *, expected_transport=capture.PRODUCTION_TRANSPORT):
    old, before, old_counts = read_capture(old_path, old_sha, expected_transport=expected_transport)
    new, after, new_counts = read_capture(new_path, new_sha, expected_transport=expected_transport)
    start = datetime.fromisoformat(old.capture_completed_at.replace("Z", "+00:00"))
    end = datetime.fromisoformat(new.capture_started_at.replace("Z", "+00:00"))
    if end <= start or old.manifest_sha256 == new.manifest_sha256:
        raise ValueError("drift requires distinct, chronological nonoverlapping captures")
    report = {
        "schema": "arv2-vendor-between-capture-drift-counts-v1",
        "first_event_date": FIRST, "last_event_date": LAST,
        "old_capture_id": old.capture_id, "new_capture_id": new.capture_id,
        "old_manifest_sha256": old.manifest_sha256, "new_manifest_sha256": new.manifest_sha256,
        "old_capture_completed_at": old.capture_completed_at, "new_capture_started_at": new.capture_started_at,
        "minimum_between_capture_interval": str(end - start),
        "roles": {role.value: compare_role(before[role.value], after[role.value],
                  old_counts[role.value], new_counts[role.value]) for role in capture.ROLE_ORDER},
        "point_in_time_proven": False, "performance_effect_measured": False,
        "qc_calls": 0, "return_looks": 0,
        "limitations": [
            "Same event-date queries can lose records whose dates move outside the window.",
            "Old-only/new-only IDs do not identify deletion, backfill or creation without vendor evidence.",
            "Only changes between capture dates are observed, not corrections before the old snapshot.",
            "Field comparisons preserve JSON scalar kind and exact decimal representation; not all edits are economic changes.",
            "A low short-interval rate cannot bound years of historical overwrites or prove PIT.",
            "No return direction, bias magnitude, causal mechanism or regime diagnosis follows.",
        ],
    }
    return report


def publish_report(report, output_root):
    """Private immutable count-only report, using the existing artifact writer."""
    root = Path(output_root).absolute()
    capture._require_operational_artifact_scope(root)
    payload = canonical_json_bytes(report)
    digest = sha256_bytes(payload)
    name = f"drift-counts-{digest}.json"
    _, descriptor = capture._open_directory_path(root, create=True, name="drift report root")
    try:
        capture._exclusive_private_write_at(descriptor, name, payload, "drift count report")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return root / name, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-path", type=Path, default=OLD_PATH)
    parser.add_argument("--old-manifest-sha256", default=OLD_SHA)
    parser.add_argument("--new-path", type=Path, required=True)
    parser.add_argument("--new-manifest-sha256", required=True)
    parser.add_argument("--output-root", type=Path,
                        default=ROOT / "artifacts/analyst_revisions_v2/vendor_vintage_drift_20260926")
    args = parser.parse_args()
    report = compare_captures(args.old_path, args.old_manifest_sha256, args.new_path, args.new_manifest_sha256)
    path, digest = publish_report(report, args.output_root)
    print(json.dumps({"report_path": str(path), "report_sha256": digest, "report": report}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
