"""Exact refused-parent daily recovery, never a completed-parent substitute.

The factory replays original private evidence through the existing qualifier.
It has no filesystem, credential or network access. Saved flags cannot create
a scope; the original failed claim, incomplete chains and debits remain bound.
"""
from __future__ import annotations

import json
import re
from types import MappingProxyType

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_daily_active_reference as daily

SOURCE_HEAD = "f67bbf2fc5ab4c7ce822c7e52b57b560cd670682"
SOURCE_CODE_SHA256 = "8c1ff8c4db5e4dd63cd6a553883777467cf04ea347db93d68daedf3b6b7c41b4"
SOURCE_PINS = {
    "inventory.private.json": "4b2fd1cb404516724da494fd8b34a59f2444b6b43b39be57fef631efcad883e8",
    "round.closed.json": "e0f1031919a15ed66a15702902dd7d2dfb6a9259a7c36a6599004e24c9a1711c",
    "claim": "1d5857437edbf2cd48510b01c7e2ccc8674621dcc509892552b9d5f08aef2c64",
}
SOURCE_PROTOCOL = "dc25d57e5b181c7028385ea689805e72b62a09c6e687cd11ac1eb6b7c5e139ce"
SOURCE_OPERATIONAL = "d9bfd50ae4f9ad44c939832482066683b98304c160893b1b914bfcb138156126"
# The separately pinned spent claim is a sibling in the parent directory:
# 12,553 run members plus that one claim are 12,554 protected source files.
SOURCE_COUNTS = {"files": 12553, "attempts_claimed": 3586, "http_invocations": 3585,
    "days_started": 601, "days_returned": 601, "complete_days": 593,
    "charged_bytes": 966979249, "charged_rows": 3347428, "rows": 3346428}
ROOT = "/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest/"


class DailyRecoveryRefusal(ValueError):
    pass


def require(value, reason):
    if not value:
        raise DailyRecoveryRefusal("REFUSED: " + reason)


def parsed(raw):
    require(type(raw) is bytes, "original_control_bytes_required")
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, "duplicate_control_key")
            value[key] = item
        return value
    try:
        return json.loads(raw, object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError):
        raise DailyRecoveryRefusal("REFUSED: malformed_control_JSON") from None


def manifest_index(raw):
    entries = parsed(raw)
    require(type(entries) is list and bool(entries), "complete_file_manifest_required")
    pins = {}
    for row in entries:
        require(type(row) is dict and set(row) == {"name", "sha256", "bytes"}
            and type(row["name"]) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,150}", row["name"])
            and row["name"] not in {".", ".."} and row["name"] not in pins
            and type(row["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
            and type(row["bytes"]) is int and 0 <= row["bytes"] <= 256 * 1024**2,
            "bounded_unique_manifest_member_required")
        pins[row["name"]] = (row["sha256"], row["bytes"])
    require(list(pins) == sorted(pins), "sorted_exact_manifest_required")
    return MappingProxyType(pins)


def checked_reader(pins, read, boundary):
    require(type(pins) is MappingProxyType, "sealed_manifest_required")
    def get(name):
        boundary()
        require(name in pins, "unregistered_original_member")
        raw = read(name, max(1, pins[name][1]))
        require(type(raw) is bytes and len(raw) == pins[name][1]
            and hash_bytes(raw) == pins[name][0], "original_member_bytes_changed")
        boundary()
        return raw
    return get


def strip_marker(value, marker):
    require(type(value) is dict and value.get("runtime_registration") == marker
        and value.get("stable_budget_protocol_sha256") == SOURCE_OPERATIONAL,
        "original_runtime_marker_changed")
    return {key: item for key, item in value.items()
        if key not in {"runtime_registration", "stable_budget_protocol_sha256"}}


def rebuild_day(plan, index, day, result, receipts, get, strip):
    """One whole chain, one origin, existing exact typed factory; no saved True."""
    start = strip(parsed(get(f"day-{day:04d}.started.json")))
    require(start == {"schema": "si-daily-active-day-start-v1", "day_ordinal": day,
        "query_date": plan.sessions()[day - 1], "started_at": result["started_at"],
        "plan_sha256": plan.sha256}, "original_day_start_changed")
    require(strip(parsed(get(f"day-{day:04d}.completed.json"))) == result,
        "original_day_completion_changed")
    pages = []
    for receipt in receipts:
        prefix = f"day-{day:04d}-page-{receipt['page_ordinal']:02d}"
        began = strip(parsed(get(prefix + ".started.json")))
        require(strip(parsed(get(prefix + ".received.json"))) == receipt
            and began.get("attempt") == receipt.get("attempt")
            and began.get("global_attempts_claimed") == receipt.get("attempt")
            and began.get("day_ordinal") == day and began.get("page_ordinal") == receipt["page_ordinal"]
            and began.get("query_date") == receipt.get("query_date") == plan.sessions()[day - 1]
            and began.get("plan_sha256") == plan.sha256
            and began.get("request_started_at") == receipt.get("request_started_at")
            and began.get("request_sha256") == receipt.get("request_sha256")
            and daily.page_request_sha256(began.get("request", {}).get("url")) == receipt.get("request_sha256"),
            "whole_day_start_received_binding_changed")
        raw = get(prefix + ".raw")
        require(hash_bytes(raw) == receipt["raw_sha256"] and len(raw) == receipt["raw_bytes"],
            "original_page_raw_changed")
        pages.append(daily.CapturedDailyActiveReferencePage(plan.sessions()[day - 1],
            receipt["page_ordinal"], began["request"]["url"], raw, receipt["request_started_at"],
            receipt["received_at"], receipt["http_status"], receipt["content_type"]))
    report = daily.qualify_daily_active_reference(plan, day, tuple(pages), index,
        started_at=result["started_at"], retrieved_at=result["retrieved_at"])
    require(result.get("qualification_path") == f"day-{day:04d}.qualified.private.json"
        and report.sha256 == result.get("qualification_sha256")
        and report.to_bytes() == get(result["qualification_path"]), "typed_day_replay_changed")
    return report


class DailyRecoveryScope:
    """Factory-only scope anchored to exhausted original evidence and plan/index."""
    __slots__ = ("_anchor", "_identity")
    def __init__(self):
        raise DailyRecoveryRefusal("REFUSED: audited_refused_parent_factory_required")
    def check(self, plan=None, index=None):
        require(type(self) is DailyRecoveryScope and self._anchor is self._identity
            and type(self._anchor) is tuple and len(self._anchor) == 8, "recovery_scope_changed")
        p, i, _, _, _, _, _, boundary = self._anchor
        require((plan is None or plan is p) and (index is None or index is i), "same_original_plan_index_required")
        p._guard(); i._guard(); boundary()
    def payload(self):
        self.check(); return parsed(self._anchor[2])
    @property
    def sha256(self):
        self.check(); return hash_bytes(self._anchor[2])
    def days(self, plan, index):
        self.check(plan, index); return self._anchor[3]
    def page_limit(self, day):
        self.check(); return dict(self._anchor[4])[day]
    def limits(self):
        value = self.payload(); return value["maximum_attempts"], value["maximum_total_bytes"], value["maximum_total_rows"]
    def original_reports(self):
        self.check()
        plan, index, _, _, _, originals, get, _ = self._anchor
        marker_raw, items = originals
        marker = parsed(marker_raw)
        for day, result_raw, receipt_raw in items:
            self.check()
            yield rebuild_day(plan, index, day, parsed(result_raw), parsed(receipt_raw), get,
                lambda value: strip_marker(value, marker))


def audit_refused_parent(plan, index, *, manifest_raw, read, claim_raw, historical_code, boundary):
    require(type(plan) is daily.DailyActiveReferencePlan and type(index) is daily.CompositeNativeIndex,
        "original_daily_plan_and_index_required")
    plan._guard(); index._guard(); boundary()
    pins = manifest_index(manifest_raw)
    require(len(pins) == SOURCE_COUNTS["files"], "complete_original_file_count_required")
    get = checked_reader(pins, read, boundary)
    raw_inventory, raw_closed = get("inventory.private.json"), get("round.closed.json")
    require(all(hash_bytes(raw) == SOURCE_PINS[name] for name, raw in
        (("inventory.private.json", raw_inventory), ("round.closed.json", raw_closed), ("claim", claim_raw))),
        "registered_refused_parent_pins_changed")
    claim = parsed(claim_raw); registration = claim.get("runtime_registration", {})
    require(type(registration) is dict and set(registration) == {"registered_head", "registered_remote",
        "complete_current_code_manifest_sha256", "complete_current_code_manifest"}
        and registration["registered_head"] == registration["registered_remote"] == SOURCE_HEAD
        and registration["complete_current_code_manifest_sha256"] == SOURCE_CODE_SHA256,
        "original_runtime_registration_required")
    code = registration["complete_current_code_manifest"]
    require(type(code) is dict and len(code) == 42 and hash_payload(code) == SOURCE_CODE_SHA256,
        "original_historical_42_file_manifest_required")
    for path, digest in sorted(code.items()):
        require(type(path) is str and path.startswith(ROOT) and ".." not in path.split("/")
            and hash_bytes(historical_code(SOURCE_HEAD, path[len(ROOT):])) == digest,
            "original_committed_code_changed")
    marker = {key: value for key, value in registration.items() if key != "complete_current_code_manifest"}
    strip = lambda value: strip_marker(value, marker)
    require(claim.get("schema") == "si-daily-active-spent-whole-round-prototype-v1"
        and claim.get("plan_sha256") == plan.sha256 and claim.get("protocol_sha256") == SOURCE_PROTOCOL
        and claim.get("stable_budget_protocol_sha256") == SOURCE_OPERATIONAL
        and claim.get("restart_or_resumption_allowed") is False
        and claim.get("maximum_attempts") == daily.MAXIMUM_REQUESTS
        and claim.get("maximum_total_bytes") == daily.MAXIMUM_TOTAL_BYTES
        and claim.get("maximum_total_rows") == daily.MAXIMUM_ROWS, "original_spent_claim_changed")
    inventory, closed = strip(parsed(raw_inventory)), strip(parsed(raw_closed))
    require(inventory.get("halted") is True and inventory.get("publication_failed") is False
        and inventory.get("complete_frozen_sequence") is False
        and inventory.get("source_sequence_reported_complete") is False
        and inventory.get("planned_days") == daily.EXPECTED_SESSIONS
        and inventory.get("plan_sha256") == plan.sha256
        and inventory.get("protocol_sha256") == SOURCE_PROTOCOL
        and closed.get("round_closure_status") == "refused"
        and closed.get("complete_frozen_sequence") is False
        and closed.get("plan_sha256") == plan.sha256, "refused_parent_must_remain_refused")
    for value in (inventory, closed):
        require(value.get("source_admitted") is False and value.get("outcome_looks") == value.get("qc_attempts") == 0,
            "source_only_original_authority_required")
        observation = value.get("final_remote_observation", {})
        require(observation.get("pending_receipt_slots") == 0 and observation.get("round_complete") is False,
            "original_attempts_must_be_drained")
    for key, expected in SOURCE_COUNTS.items():
        if key not in {"files", "complete_days"}:
            require(type(inventory.get(key)) is int and inventory[key] == expected, "original_accounting_changed")
    attempts, results = inventory.get("attempts"), inventory.get("days")
    require(type(attempts) is list and len(attempts) == inventory["attempts_claimed"]
        and type(results) is list and len(results) == inventory["days_returned"], "complete_attempt_day_inventory_required")
    expected_names = {"inventory.private.json", "round.closed.json"}
    per_day = {}; total_bytes = total_rows = observed_rows = invoked_count = 0
    previous_start = daily._clock(claim["started_at"])
    for number, receipt in enumerate(attempts, 1):
        require(type(receipt) is dict and type(receipt.get("attempt")) is int and receipt["attempt"] == number,
            "every_original_START_debit_required")
        day, page = receipt.get("day_ordinal"), receipt.get("page_ordinal")
        require(type(day) is int and 1 <= day <= daily.EXPECTED_SESSIONS and type(page) is int
            and page == len(per_day.setdefault(day, [])) + 1 and page <= daily.MAXIMUM_PAGES_PER_DAY,
            "serial_original_page_sequence_required")
        prefix = f"day-{day:04d}-page-{page:02d}"
        began = strip(parsed(get(prefix + ".started.json")))
        expected_names.add(prefix + ".started.json")
        require(began.get("attempt") == number and began.get("global_attempts_claimed") == number
            and began.get("day_ordinal") == day and began.get("page_ordinal") == page
            and began.get("query_date") == receipt.get("query_date") == plan.sessions()[day - 1]
            and began.get("request_started_at") == receipt.get("request_started_at")
            and began.get("request_sha256") == receipt.get("request_sha256")
            and began.get("plan_sha256") == plan.sha256 and began.get("code_head") == SOURCE_HEAD,
            "original_start_receipt_binding_changed")
        request = began.get("request", {}); url = request.get("url")
        require(set(request) == {"method", "url", "authentication"} and request["method"] == "GET"
            and request["authentication"] == "Bearer_header_not_recorded"
            and daily.page_request_sha256(url) == receipt["request_sha256"]
            and (url == daily.first_url(plan, day) if page == 1 else daily.next_url(url, plan.sessions()[day - 1]) == url),
            "original_request_descriptor_changed")
        start, end = daily._clock(receipt["request_started_at"]), daily._clock(receipt["received_at"])
        require(previous_start <= start <= end <= daily._clock(inventory["retrieved_at"]), "original_clock_changed")
        previous_start = start
        for axis, maximum, ceiling in (("bytes", daily.MAXIMUM_RESPONSE_BYTES, daily.MAXIMUM_TOTAL_BYTES),
                ("rows", daily.MAXIMUM_PAGE_ROWS, daily.MAXIMUM_ROWS)):
            before, inflight = began.get(f"cumulative_{axis}_charged_before"), began.get(f"inflight_{axis}_reserved_after")
            require(type(before) is int and type(inflight) is int and before >= 0 and 0 < inflight <= 8 * maximum
                and before + inflight <= ceiling and began.get(f"whole_page_{axis}_reserved") == maximum,
                "original_whole_page_reservations_changed")
        terminal = ".received.json" if receipt.get("schema") == "si-daily-active-page-received-v1" else ".refused.json"
        saved = strip(parsed(get(prefix + terminal))); expected_names.add(prefix + terminal)
        require(all(receipt.get(key) == value for key, value in saved.items())
            and set(receipt) - set(saved) <= {"raw_path", "raw_sha256", "raw_bytes", "content_type"},
            "original_terminal_receipt_changed")
        extra = prefix + ".refused.json"
        if terminal == ".received.json" and extra in pins:
            refused = strip(parsed(get(extra))); expected_names.add(extra)
            require(refused.get("attempt") == number and refused.get("day_ordinal") == day
                and refused.get("page_ordinal") == page and refused.get("request_sha256") == receipt["request_sha256"]
                and refused.get("code") == "daily_active_page_or_chain_refused", "post_receipt_refusal_changed")
        invoked = receipt.get("http_invoked")
        require(type(invoked) is bool, "actual_invocation_bit_required")
        invoked_count += int(invoked)
        if receipt.get("raw_path") is not None:
            require(invoked and receipt.get("http_status") == 200 and receipt["raw_path"] == prefix + ".raw",
                "raw_requires_actual_received_request")
            raw = get(receipt["raw_path"]); expected_names.add(receipt["raw_path"])
            require(hash_bytes(raw) == receipt.get("raw_sha256") and len(raw) == receipt.get("raw_bytes")
                and len(raw) <= daily.MAXIMUM_RESPONSE_BYTES, "original_raw_receipt_changed")
            count = len(daily.page_payload(raw)["results"])
            total_bytes += len(raw); total_rows += count; observed_rows += count
        elif invoked:
            total_bytes += daily.MAXIMUM_RESPONSE_BYTES; total_rows += daily.MAXIMUM_PAGE_ROWS
        per_day[day].append(receipt)
    require((invoked_count, total_bytes, total_rows, observed_rows) == tuple(inventory[key] for key in
        ("http_invocations", "charged_bytes", "charged_rows", "rows")), "replayed_original_debits_changed")
    originals = []; day_ordinals = []
    for result in results:
        day = result.get("day_ordinal"); day_ordinals.append(day)
        require(type(day) is int and 1 <= day <= daily.EXPECTED_SESSIONS and result.get("query_date") == plan.sessions()[day - 1]
            and type(result.get("complete_advertised_chain")) is bool and result.get("source_admitted") is False,
            "bound_original_day_result_required")
        expected_names.add(f"day-{day:04d}.started.json")
        if result["complete_advertised_chain"]:
            require(day in per_day and result.get("pages_received") == len(per_day[day]), "whole_completed_day_required")
            rebuild_day(plan, index, day, result, per_day[day], get, strip)
            expected_names.update((f"day-{day:04d}.completed.json", f"day-{day:04d}.qualified.private.json"))
            originals.append((day, canonical_json(result).encode(), canonical_json(per_day[day]).encode()))
        else:
            name = f"day-{day:04d}.refused.json"; expected_names.add(name)
            require(strip(parsed(get(name))) == result and result.get("qualification_path") is None
                and result.get("qualification_sha256") is None, "incomplete_original_day_must_stay_negative")
            start = strip(parsed(get(f"day-{day:04d}.started.json")))
            require(start.get("day_ordinal") == day and start.get("started_at") == result.get("started_at")
                and start.get("plan_sha256") == plan.sha256, "incomplete_day_start_changed")
    require(day_ordinals == sorted(set(day_ordinals)) and set(per_day) <= set(day_ordinals)
        and len(originals) == SOURCE_COUNTS["complete_days"] and set(pins) == expected_names,
        "exact_original_complete_set_and_all_files_required")
    complete = tuple(item[0] for item in originals)
    missing = tuple(day for day in range(1, daily.EXPECTED_SESSIONS + 1) if day not in complete)
    caps = tuple((day, daily.MAXIMUM_PAGES_PER_DAY - len(per_day.get(day, ()))) for day in missing)
    require(all(cap > 0 for _, cap in caps), "original_day_budget_exhausted_no_recovery")
    payload = {"schema": "si-refused-daily-parent-recovery-scope-v1", "parent_pins": dict(SOURCE_PINS),
        "parent_manifest_sha256": hash_bytes(manifest_raw), "parent_code_sha256": SOURCE_CODE_SHA256,
        "parent_retrieved_at": inventory["retrieved_at"],
        "plan_sha256": plan.sha256, "completed_days": list(complete), "selected_days": list(missing),
        "per_day_page_limits": [list(item) for item in caps], "original_debits": dict(SOURCE_COUNTS),
        "maximum_attempts": min(sum(cap for _, cap in caps), daily.MAXIMUM_REQUESTS - len(attempts)),
        "maximum_total_bytes": daily.MAXIMUM_TOTAL_BYTES - total_bytes,
        "maximum_total_rows": daily.MAXIMUM_ROWS - total_rows,
        "parent_status": "refused_original_claim_stays_spent", "chain_policy": "whole_fresh_chains_no_cursor_stitching",
        "source_admitted": False, "ready_for_empirical_backtest": False, "outcome_looks": 0, "qc_attempts": 0}
    require(payload["maximum_attempts"] > 0 and payload["maximum_total_bytes"] >= daily.MAXIMUM_RESPONSE_BYTES
        and payload["maximum_total_rows"] >= daily.MAXIMUM_PAGE_ROWS, "residual_budget_unavailable")
    result = object.__new__(DailyRecoveryScope)
    result._anchor = result._identity = (plan, index, canonical_json(payload).encode(), missing, caps,
        (canonical_json(marker).encode(), tuple(originals)), get, boundary)
    result.check(); return result


def combined_reports(scope, *, child_manifest_raw, child_manifest_sha256, read, child_claim_raw,
        expected_registration, historical_code, boundary):
    """Exhausted whole-chain union only; no partial parent or page stitching.

The caller registers the child manifest and exact runtime marker from the
actual child receipt. This replays source evidence, never price/outcome data.
    """
    require(type(scope) is DailyRecoveryScope and hash_bytes(child_manifest_raw) == child_manifest_sha256,
        "registered_complete_child_manifest_required")
    scope.check(); plan, index = scope._anchor[:2]
    pins = manifest_index(child_manifest_raw); get = checked_reader(pins, read, boundary)
    require("round.post-publication-refused.json" not in pins, "post_publication_negative_overrides_child_success")
    claim, inventory, closed = parsed(child_claim_raw), parsed(get("inventory.private.json")), parsed(get("round.closed.json"))
    after = parsed(get("round.post-publication-audit.json"))
    require(type(expected_registration) is dict and expected_registration.get("scope_sha256") == scope.sha256
        and all(value.get("recovery_registration") == expected_registration for value in (claim, inventory, closed, after)),
        "exact_child_runtime_registration_required")
    require(after.get("schema") == "si-daily-recovery-post-publication-audit-v1"
        and after.get("matching_remote_equal") is True and after.get("complete_recovery_scope") is True
        and after.get("closure_sha256") == hash_payload(closed)
        and daily._clock(closed["audit_received_at"]) <= daily._clock(after["audit_started_at"])
        <= daily._clock(after["audit_received_at"]), "fresh_postpublication_child_audit_required")
    require(daily._clock(scope.payload()["parent_retrieved_at"]) <= daily._clock(claim["started_at"])
        <= daily._clock(inventory["retrieved_at"]) <= daily._clock(closed["audit_started_at"])
        <= daily._clock(closed["audit_received_at"]), "parent_child_closure_chronology")
    code = expected_registration.get("code_manifest")
    require(type(code) is dict and bool(code) and hash_payload(code) == expected_registration.get("code_manifest_sha256"),
        "child_complete_code_manifest_required")
    for path, digest in sorted(code.items()):
        require(type(path) is str and path.startswith(ROOT) and ".." not in path.split("/")
            and hash_bytes(historical_code(expected_registration["head"], path[len(ROOT):])) == digest,
            "child_committed_code_changed")
    a, b, r = scope.limits()
    require(claim.get("schema") == "si-daily-recovery-spent-whole-round-v1"
        and claim.get("recovery_scope_sha256") == scope.sha256
        and (claim.get("maximum_attempts"), claim.get("maximum_total_bytes"), claim.get("maximum_total_rows")) == (a, b, r)
        and claim.get("restart_or_resumption_allowed") is False
        and inventory.get("schema") == "si-daily-recovery-capture-inventory-v1"
        and inventory.get("recovery_scope_sha256") == scope.sha256
        and inventory.get("complete_recovery_scope") is True and inventory.get("halted") is False
        and inventory.get("publication_failed") is False and inventory.get("complete_frozen_sequence") is False
        and closed.get("schema") == "si-daily-recovery-authoritative-close-v1"
        and closed.get("round_closure_status") == "completed_child_scope"
        and closed.get("complete_recovery_scope") is True and closed.get("complete_frozen_sequence") is False
        and closed.get("matching_remote_equal") is True and closed.get("pending_slots") == 0,
        "authoritatively_closed_child_scope_required")
    require(all(value.get("source_admitted") is False and value.get("outcome_looks") == value.get("qc_attempts") == 0
        for value in (inventory, closed)), "child_source_only_authority_required")
    attempts, results = inventory.get("attempts"), inventory.get("days")
    selected = scope.days(plan, index)
    require(type(attempts) is list and type(results) is list
        and len(attempts) == inventory.get("attempts_claimed") == inventory.get("http_invocations") == closed.get("http_invocations")
        and 0 < len(attempts) <= a and len(results) == len(selected)
        and [row.get("day_ordinal") for row in results] == list(selected)
        and inventory.get("planned_days") == inventory.get("days_started") == inventory.get("days_returned") == len(selected),
        "every_child_attempt_and_selected_day_required")
    marker = {"registered_head": expected_registration["head"], "registered_remote": expected_registration["remote"],
        "complete_current_code_manifest_sha256": hash_payload({key: value for key, value in code.items()
            if key != ROOT + "scripts/capture_short_interest_daily_recovery.py"})}
    strip = lambda value: strip_marker(value, marker)
    expected_names = {"inventory.private.json", "round.closed.json", "round.post-publication-audit.json"}; per_day = {}
    previous = daily._clock(claim["started_at"])
    for number, receipt in enumerate(attempts, 1):
        day, page = receipt.get("day_ordinal"), receipt.get("page_ordinal")
        require(receipt.get("attempt") == number and type(receipt.get("attempt")) is int
            and day in selected and type(page) is int and page == len(per_day.setdefault(day, [])) + 1
            and page <= scope.page_limit(day) and receipt.get("schema") == "si-daily-active-page-received-v1"
            and receipt.get("code") == "received" and receipt.get("http_invoked") is True
            and receipt.get("http_status") == 200 and receipt.get("body_observed") is True,
            "whole_new_child_chain_only")
        start, end = daily._clock(receipt["request_started_at"]), daily._clock(receipt["received_at"])
        require(previous <= start <= end <= daily._clock(inventory["retrieved_at"]), "child_attempt_clock_changed")
        previous = start
        prefix = f"day-{day:04d}-page-{page:02d}"
        require(receipt.get("raw_path") == prefix + ".raw", "child_raw_locator_changed")
        expected_names.update(prefix + suffix for suffix in (".started.json", ".received.json", ".raw"))
        began = strip(parsed(get(prefix + ".started.json")))
        require(began.get("code_head") == expected_registration["head"], "child_code_head_changed")
        for axis, maximum, ceiling in (("bytes", daily.MAXIMUM_RESPONSE_BYTES, b), ("rows", daily.MAXIMUM_PAGE_ROWS, r)):
            before, inflight = began.get(f"cumulative_{axis}_charged_before"), began.get(f"inflight_{axis}_reserved_after")
            require(type(before) is int and type(inflight) is int and before >= 0 and 0 < inflight <= 8 * maximum
                and before + inflight <= ceiling and began.get(f"whole_page_{axis}_reserved") == maximum,
                "child_cumulative_reservation_changed")
        per_day[day].append(receipt)
    for row in results:
        day = row["day_ordinal"]
        require(row.get("complete_advertised_chain") is True and row.get("pages_received") == len(per_day.get(day, ()))
            and row.get("source_admitted") is False, "complete_child_day_required")
        expected_names.update(f"day-{day:04d}." + suffix for suffix in ("started.json", "completed.json", "qualified.private.json"))
    require(set(pins) == expected_names, "exact_complete_child_member_set_required")
    by_day = {row["day_ordinal"]: canonical_json(row).encode() for row in results}
    original = iter(scope.original_reports()); old = next(original, None)
    bytes_used = rows_used = 0
    for day in range(1, daily.EXPECTED_SESSIONS + 1):
        boundary(); scope.check()
        if day in by_day:
            report = rebuild_day(plan, index, day, parsed(by_day[day]), per_day[day], get, strip)
            value = report.to_payload(); rows_used += len(value["rows"])
            bytes_used += sum(page["raw_bytes"] for page in value["page_origins"])
        else:
            require(old is not None and old.to_payload()["day_ordinal"] == day, "original_child_union_missing_day")
            report = old; old = next(original, None)
        if day == daily.EXPECTED_SESSIONS:
            require(old is None and bytes_used == inventory.get("charged_bytes") <= b
                and rows_used == inventory.get("charged_rows") == inventory.get("rows") <= r,
                "exhausted_all1169_union_and_cumulative_budget_required")
            boundary(); scope.check()
        yield report
