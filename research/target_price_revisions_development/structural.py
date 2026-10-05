"""Bounded, hash-first retained ratings audit; persists only aggregate counts."""
from __future__ import annotations

import json
import re
import time
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

from .plan import (DevelopmentError, DevelopmentPlan, bounded_read, canonical,
                   check_plan, digest, safe_path, unique_object)

TARGET_FIELDS = ("price_target", "previous_price_target", "adjusted_price_target", "previous_adjusted_price_target")
ACTIONS = ("raises", "lowers", "maintains", "announces", "sets")
VALUE_STATES = ("missing", "null", "invalid", "nonfinite", "zero", "negative", "positive")
CURRENCIES = ("USD", "CAD", "EUR", "GBP", "CHF", "JPY", "AUD", "CNY", "HKD")


def _auditor_inventory(repository: Path) -> dict[str, str]:
    folder = Path("research/target_price_revisions_development")
    return {str(folder / name).replace("\\", "/"): digest(bounded_read(repository / folder / name, 131072))
            for name in ("__init__.py", "plan.py", "structural.py", "__main__.py")}


def _refuse_constant(_token: str) -> None:
    raise DevelopmentError("invalid nonfinite JSON token in retained input")


def _source_json(payload: bytes) -> dict[str, Any]:
    try:
        result = json.loads(payload.decode("utf-8"), parse_float=Decimal,
                            parse_constant=_refuse_constant, object_pairs_hook=unique_object)
    except DevelopmentError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise DevelopmentError("invalid retained-input JSON") from exc
    if type(result) is not dict:
        raise DevelopmentError("retained input must be an object")
    return result


def _utc_instant(value: Any) -> datetime | None:
    if type(value) is not str or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    try:
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def _date(value: Any) -> date | None:
    if type(value) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _target(row: dict[str, Any], field: str) -> tuple[str, Decimal | None]:
    if field not in row:
        return "missing", None
    value = row[field]
    if value is None:
        return "null", None
    if type(value) not in (str, int, Decimal) or (type(value) is str and (not value or len(value) > 128 or value != value.strip())):
        return "invalid", None
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError):
        return "invalid", None
    if not number.is_finite():
        return "nonfinite", None
    if number.is_zero():
        return "zero", number
    return ("negative" if number < 0 else "positive"), number


def _bucket() -> dict[str, Any]:
    return {
        "rows": 0,
        "targets": {field: dict.fromkeys(VALUE_STATES, 0) for field in TARGET_FIELDS},
        "actions": dict.fromkeys((*ACTIONS, "missing", "invalid", "unknown"), 0),
        "currencies": dict.fromkeys((*CURRENCIES, "other_code", "missing", "invalid"), 0),
        "pairs": dict.fromkeys(("positive_raw", "positive_adjusted", "both_positive", "direction_agrees", "direction_disagrees", "raise_action_conflict", "lower_action_conflict", "maintain_action_conflict"), 0),
        "clocks": dict.fromkeys(("event_date_invalid", "event_time_missing", "event_time_invalid", "event_time_valid", "update_missing", "update_invalid", "update_before_event_day", "update_same_event_day", "update_later_event_day", "update_after_capture", "event_date_partition_mismatch"), 0),
        "horizon_probes": dict.fromkeys(("price_target_horizon_present", "previous_price_target_horizon_present"), 0),
    }


def _count_row(bucket: dict[str, Any], row: dict[str, Any], year: int, captured: datetime) -> None:
    bucket["rows"] += 1
    targets: dict[str, Decimal | None] = {}
    for field in TARGET_FIELDS:
        state, number = _target(row, field)
        bucket["targets"][field][state] += 1
        targets[field] = number if state == "positive" else None
    action = row.get("price_target_action")
    action_bucket = action if type(action) is str and action in ACTIONS else (
        "missing" if action is None else "unknown" if type(action) is str else "invalid")
    bucket["actions"][action_bucket] += 1
    currency = row.get("currency")
    currency_bucket = currency if type(currency) is str and currency in CURRENCIES else (
        "missing" if currency is None else "other_code" if type(currency) is str and re.fullmatch(r"[A-Z]{3}", currency) else "invalid")
    bucket["currencies"][currency_bucket] += 1
    new, prior, adjusted, previous_adjusted = (targets[field] for field in TARGET_FIELDS)
    raw_pair = new is not None and prior is not None
    adjusted_pair = adjusted is not None and previous_adjusted is not None
    bucket["pairs"]["positive_raw"] += int(raw_pair)
    bucket["pairs"]["positive_adjusted"] += int(adjusted_pair)
    if raw_pair:
        direction = (new > prior) - (new < prior)
        bucket["pairs"]["raise_action_conflict"] += int(action == "raises" and direction != 1)
        bucket["pairs"]["lower_action_conflict"] += int(action == "lowers" and direction != -1)
        bucket["pairs"]["maintain_action_conflict"] += int(action == "maintains" and direction != 0)
        if adjusted_pair:
            adjusted_direction = (adjusted > previous_adjusted) - (adjusted < previous_adjusted)
            bucket["pairs"]["both_positive"] += 1
            bucket["pairs"]["direction_agrees" if direction == adjusted_direction else "direction_disagrees"] += 1
    event_day = _date(row.get("date"))
    if event_day is None:
        bucket["clocks"]["event_date_invalid"] += 1
    elif event_day.year != year:
        bucket["clocks"]["event_date_partition_mismatch"] += 1
    event_time = row.get("time")
    valid_time = False
    if type(event_time) is str and re.fullmatch(r"\d{2}:\d{2}:\d{2}", event_time):
        hours, minutes, seconds = map(int, event_time.split(":"))
        valid_time = hours < 24 and minutes < 60 and seconds < 60
    bucket["clocks"]["event_time_missing" if event_time is None else "event_time_valid" if valid_time else "event_time_invalid"] += 1
    update = _utc_instant(row.get("last_updated"))
    if row.get("last_updated") is None:
        bucket["clocks"]["update_missing"] += 1
    elif update is None:
        bucket["clocks"]["update_invalid"] += 1
    else:
        bucket["clocks"]["update_after_capture"] += int(update > captured)
        if event_day is not None:
            bucket["clocks"]["update_before_event_day" if update.date() < event_day else "update_same_event_day" if update.date() == event_day else "update_later_event_day"] += 1
    for field in ("price_target_horizon", "previous_price_target_horizon"):
        bucket["horizon_probes"][field + "_present"] += int(row.get(field) is not None)


def audit_retained(plan: DevelopmentPlan, capture_root: Path, repository: Path, *,
                   now: datetime, monotonic: Callable[[], float] = time.monotonic) -> bytes:
    started = monotonic()
    body = check_plan(plan, repository, now)
    auditor_inventory = _auditor_inventory(repository)
    source, limits = body["source"], body["limits"]
    root = safe_path(capture_root)
    manifest_bytes = bounded_read(root / "manifest.json", limits["max_manifest_bytes"])
    if digest(manifest_bytes) != source["manifest_sha256"]:
        raise DevelopmentError("retained manifest digest mismatch")
    manifest = _source_json(manifest_bytes)
    if set(manifest) != {"complete", "endpoint", "finished_utc", "page_limit", "partitions", "snapshot_id", "started_utc"}:
        raise DevelopmentError("retained manifest schema mismatch")
    if manifest["complete"] is not True or manifest["endpoint"] != source["endpoint"] or manifest["snapshot_id"] != source["snapshot_id"]:
        raise DevelopmentError("retained manifest is incomplete or out of scope")
    captured_start, captured_end = (_utc_instant(manifest[key]) for key in ("started_utc", "finished_utc"))
    if captured_start is None or captured_end is None or captured_start > captured_end or captured_end > now.astimezone(timezone.utc):
        raise DevelopmentError("invalid retained capture clocks")
    if type(manifest["page_limit"]) is not int or not 1 <= manifest["page_limit"] <= 1000:
        raise DevelopmentError("invalid retained page limit")
    partitions = manifest["partitions"]
    if type(partitions) is not list or any(type(p) is not dict for p in partitions) or [p.get("year") for p in partitions] != source["years"]:
        raise DevelopmentError("retained year inventory mismatch")
    pages: list[tuple[int, dict[str, Any], Path, int]] = []
    row_total = byte_total = 0
    names: set[str] = set()
    for partition in partitions:
        if set(partition) != {"pages", "rows", "terminated_naturally", "year"} or partition["terminated_naturally"] is not True:
            raise DevelopmentError("partition is incomplete or malformed")
        year, inventory = partition["year"], partition["pages"]
        if type(year) is not int or not 2010 <= year <= 2026 or type(inventory) is not list or not inventory:
            raise DevelopmentError("invalid partition inventory")
        declared_rows = 0
        for index, page in enumerate(inventory):
            if type(page) is not dict or set(page) != {"file", "retrieved_utc", "rows", "sha256", "url"}:
                raise DevelopmentError("invalid page inventory schema")
            name = page["file"]
            if name != f"{year}-p{index:04d}.json" or name in names:
                raise DevelopmentError("unsafe, duplicate or noncontiguous page path")
            if type(page["rows"]) is not int or not 0 <= page["rows"] <= manifest["page_limit"] or type(page["sha256"]) is not str or re.fullmatch(r"[0-9a-f]{64}", page["sha256"]) is None:
                raise DevelopmentError("invalid page count or digest")
            if type(page["url"]) is not str or not page["url"].startswith(source["endpoint"] + "?"):
                raise DevelopmentError("out-of-scope page endpoint")
            clock = _utc_instant(page["retrieved_utc"])
            if clock is None or not captured_start <= clock <= captured_end:
                raise DevelopmentError("invalid page capture clock")
            names.add(name)
            path = safe_path(root / "raw" / name)
            try:
                size = path.stat().st_size
            except OSError as exc:
                raise DevelopmentError("required retained page is unavailable") from exc
            if size > limits["max_page_bytes"]:
                raise DevelopmentError("retained page exceeds byte budget")
            pages.append((year, page, path, size))
            declared_rows += page["rows"]
            byte_total += size
        if type(partition["rows"]) is not int or declared_rows != partition["rows"]:
            raise DevelopmentError("partition row-count mismatch")
        row_total += declared_rows
    if len(pages) != source["pages"] or row_total != source["rows"] or byte_total != source["bytes"]:
        raise DevelopmentError("retained scope inventory mismatch")
    if len(pages) > limits["max_pages"] or row_total > limits["max_rows"] or byte_total > limits["max_bytes"]:
        raise DevelopmentError("retained scope exceeds resource budget")
    try:
        if {entry.name for entry in (root / "raw").iterdir()} != names:
            raise DevelopmentError("retained directory inventory mismatch")
    except OSError as exc:
        raise DevelopmentError("retained directory is unavailable") from exc

    years = {str(year): _bucket() for year in source["years"]}
    ids: Counter[str] = Counter()
    missing_ids = observed_bytes = observed_rows = 0
    for year, page, path, size in pages:
        if monotonic() - started > limits["max_seconds"]:
            raise DevelopmentError("retained audit exceeded time budget")
        payload = bounded_read(path, limits["max_page_bytes"])
        if len(payload) != size or digest(payload) != page["sha256"]:
            raise DevelopmentError("retained page size or digest mismatch")
        response = _source_json(payload)
        rows = response.get("results")
        if type(rows) is not list or len(rows) != page["rows"]:
            raise DevelopmentError("retained response row-count mismatch")
        if response.get("status") != "OK":
            raise DevelopmentError("retained response status is not OK")
        terminal = page["file"] == next(p for p in partitions if p["year"] == year)["pages"][-1]["file"]
        if bool(response.get("next_url")) == terminal:
            raise DevelopmentError("retained pagination termination mismatch")
        captured = _utc_instant(page["retrieved_utc"])
        for row in rows:
            if type(row) is not dict:
                raise DevelopmentError("retained result is not an object")
            _count_row(years[str(year)], row, year, captured)
            identifier = row.get("benzinga_id", row.get("id"))
            if type(identifier) in (str, int) and 0 < len(str(identifier)) <= 128:
                ids[digest(str(identifier).encode("utf-8"))] += 1
            else:
                missing_ids += 1
            observed_rows += 1
            if observed_rows % 1000 == 0 and monotonic() - started > limits["max_seconds"]:
                raise DevelopmentError("retained audit exceeded time budget")
        observed_bytes += len(payload)
    if monotonic() - started > limits["max_seconds"]:
        raise DevelopmentError("retained audit exceeded time budget")
    check_plan(plan, repository, now)  # Frozen canonical files must still match.
    if _auditor_inventory(repository) != auditor_inventory:
        raise DevelopmentError("auditor code changed during retained processing")
    return canonical({
        "schema": "tpr-d0-structural-report-v1", "plan_sha256": plan.sha256,
        "audit_as_of_utc": now.astimezone(timezone.utc).isoformat(),
        "auditor_code_sha256": auditor_inventory,
        "source_manifest_sha256": source["manifest_sha256"],
        "input": {"pages": len(pages), "rows": observed_rows, "bytes": observed_bytes},
        "years": years,
        "identifiers": {"missing_or_invalid": missing_ids, "unique": len(ids),
                        "repeated_groups": sum(n > 1 for n in ids.values()),
                        "extra_occurrences": sum(n - 1 for n in ids.values())},
        "accepted_risks": body["accepted_risks"],
        "point_in_time_data": False, "canonical_admission": False,
        "confirmatory_alpha": "0", "outcome_reads": 0, "provider_requests": 0,
        "qc_attempts": 0, "development_looks": 0, "trading_authority": False,
        "interpretation": {
            "targets": "field states and positive-pair directions only; no price or return joins",
            "adjustment": "direction agreement does not prove adjustment-vintage or split consistency",
            "clocks": "nominal unzoned event day versus UTC last-touch day; not public availability",
            "horizon": "presence probes do not prove explicit comparable prior/new horizons",
            "identifiers": "repeated captured IDs do not reconstruct overwritten correction history",
            "next": "independent review and later exact TPR-D1 scope; no automatic promotion",
        },
    })
