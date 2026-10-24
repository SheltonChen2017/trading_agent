"""Injected-only offline replay of one completed identity continuation.

No filesystem, credentials, provider requests or QC operations are implemented.
The protected adapter must supply registered original byte pins and committed
binary code. Replaying current-source assertions does not admit them for PIT,
share-count economics, prices, outcomes, or platform processing.
"""
from dataclasses import dataclass, field
import json
import re

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_dated_identity as identity
import scripts.continue_short_interest_native_identity as capture
from scripts.qualify_short_interest_action_supplement import _clock


class CompletedIdentityRefusal(ValueError):
    pass


def require(value, reason):
    if not value:
        raise CompletedIdentityRefusal(reason)


def digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def exact(value, expected):
    # Python dict equality equates True/1 and 0/False. Canonical JSON retains
    # those source types, so malformed counters or authority never normalize.
    return canonical_json(value) == canonical_json(expected)


@dataclass(frozen=True, slots=True, init=False)
class CompletedIdentityReplay:
    _metadata: str = field(repr=False)
    _source: object = field(repr=False)
    _read: object = field(repr=False)
    _anchor: tuple = field(repr=False)
    _identity: tuple = field(repr=False)

    def __init__(self):
        raise CompletedIdentityRefusal("completed_replay_factory_required")

    def check(self):
        require(type(self) is CompletedIdentityReplay and self._anchor is self._identity
                and type(self._anchor) is tuple and len(self._anchor) == 3
                and all(current is anchored for current, anchored in zip(
                    (self._metadata, self._source, self._read), self._anchor)), "completed_replay_changed")
        self._source.check()

    def payload(self):
        self.check()
        return json.loads(self._metadata)

    def iter_new_reports(self):
        """Yield protected, byte-bound child reports; retain original receipt clocks."""
        self.check()
        for entry in self.payload()["new_reports"]:
            self.check()
            raw = self._read(entry["report_path"])
            require(hash_bytes(raw) == entry["report_bytes_sha256"] and len(raw) == entry["report_bytes"],
                    "completed_report_bytes_changed")
            yield dict(entry), raw


def verify_completed_continuation(source, files, *, byte_pins, inventory_sha256,
        budget_raw, budget_sha256, expected_head, expected_protocol_sha256,
        expected_code_identity_sha256, historical_code, local_guard,
        expected_run_id, expected_remote_head):
    """Authenticate supplied custody then independently replay every new date.

    Fixed source/head/run/remote/budget/inventory pins are mandatory inputs to a
    future protected adapter, not discoveries from an untrusted completion flag.
    The production parent is 44 old reports + 68 new reports; separately frozen
    fabricated parents can be smaller. Memory is bounded to one date's pages.
    """
    local_guard()
    require(type(source) is capture.ParentIdentity, "verified_original_parent_required")
    source.check()
    state, frozen = source.payload(), capture.freeze_protocol(source)
    require(type(expected_head) is str and re.fullmatch(r"[0-9a-f]{40}", expected_head)
            and type(expected_remote_head) is str and re.fullmatch(r"[0-9a-f]{40}", expected_remote_head)
            and type(expected_run_id) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", expected_run_id)
            and all(digest(value) for value in (inventory_sha256, budget_sha256,
                expected_protocol_sha256, expected_code_identity_sha256)), "registered_completion_pins")
    require(type(files) in (dict, capture._ParentFiles) and type(byte_pins) is dict
            and set(files) == set(byte_pins) and all(digest(pin) for pin in byte_pins.values()),
            "complete_child_byte_inventory")

    # Recheck every raw byte pin when read, including after construction. The
    # streaming adapter validates length/digest on each source read as well.
    def read(name):
        local_guard()
        source.check()
        require(name in byte_pins and name in files, "missing_child_receipt")
        raw = files[name]
        require(type(raw) is bytes and hash_bytes(raw) == byte_pins[name], "child_bytes_changed")
        return raw

    def receipt(name):
        raw = read(name)
        value = capture.parsed(raw)
        require(type(value) is dict and canonical_json(value).encode() == raw, "canonical_child_receipt")
        return value

    def inventory_pin():
        local_guard()
        require(set(files) == set(byte_pins), "child_inventory_changed")
        if type(files) is capture._ParentFiles:
            files.check()
            require(files.pins() == byte_pins and files.inventory_sha256() == inventory_sha256,
                    "registered_child_inventory")
        else:
            require(hash_payload([{"name": name, "sha256": hash_bytes(read(name)), "bytes": len(files[name])}
                    for name in sorted(files)]) == inventory_sha256, "registered_child_inventory")

    inventory_pin()
    protocol, start, complete, inventory = (receipt(name) for name in
            ("protocol.private.json", "started.json", "completed.json", "inventory.private.json"))
    require(exact(protocol, frozen) and hash_payload(protocol) == expected_protocol_sha256,
            "original_child_protocol")
    code = []
    for name in capture.CODE_FILES:
        local_guard()
        raw = historical_code(expected_head, name)
        local_guard()
        require(type(raw) is bytes, "historical_committed_binary_code_required")
        code.append({"path": name, "sha256": hash_bytes(raw)})
    require(hash_payload({"git_commit": expected_head, "files": code}) == expected_code_identity_sha256,
            "child_historical_code_identity")
    require(exact(start, {"schema": "si-native-identity-continuation-start-v1", "code_head": expected_head,
            "code_identity_sha256": expected_code_identity_sha256, "protocol_sha256": expected_protocol_sha256,
            "started_at": start.get("started_at"), "source_attempts_consumed": state["source_attempts"],
            "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}), "child_start_binding")
    previous = _clock(start["started_at"])
    require(_clock(state["source_refused_at"]) <= previous, "child_after_original_refusal")
    local_guard()
    require(type(budget_raw) is bytes and hash_bytes(budget_raw) == budget_sha256, "child_spent_budget_bytes")
    budget = capture.parsed(budget_raw)
    require(type(budget) is dict and canonical_json(budget).encode() == budget_raw, "canonical_child_budget")
    expected_budget = {"schema": "si-native-identity-manual-continuation-budget-v1",
            "protocol_sha256": expected_protocol_sha256, "code_head": expected_head,
            "source_budget_bytes_sha256": state["source_budget_bytes_sha256"],
            "started_at": start["started_at"], "maximum_new_attempts": frozen["maximum_new_attempts"],
            "parent_attempts_consumed": state["source_attempts"], "automatic_retries": 0,
            "run_id": expected_run_id, "remote_head": expected_remote_head,
            "source_inventory_sha256": state["source_inventory_sha256"],
            "failed_start_bytes_sha256": state["failed_start_bytes_sha256"],
            "credential_item": frozen["credential_item"], "unused_parent_slots_repurposable": False}
    require(exact(budget, expected_budget), "child_manual_spent_budget_binding")
    allowed = {"protocol.private.json", "started.json", "completed.json", "inventory.private.json"}
    reports, new_reports, attempts, new_bytes, new_rows = list(state["completed_reports"]), [], 0, 0, 0

    for number in range(state["failed_date_number"], len(state["dates"]) + 1):
        local_guard()
        at, pages = state["dates"][number - 1], []
        for active in (True, False):
            resumed = number == state["failed_date_number"] and active is True
            url = state["failed_request"]["url"] if resumed else capture.initial_url(at, active)
            first = state["failed_ordinal"] if resumed else 1
            seen = set(state["partial_seen_urls"]) if resumed else set()
            if resumed:
                pages.extend(source._partial)
            for ordinal in range(first, identity.MAXIMUM_PAGES_PER_PANEL + 1):
                local_guard()
                require(url not in seen, "child_panel_cycle")
                require(url == capture.initial_url(at, active) if ordinal == 1
                        else identity.next_url(url, at, active) == url, "child_exact_panel_scope")
                seen.add(url)
                require(attempts < frozen["maximum_new_attempts"]
                        and frozen["maximum_cumulative_bytes"] - state["source_raw_bytes"] - new_bytes
                            >= identity.MAXIMUM_RESPONSE_BYTES
                        and frozen["maximum_cumulative_rows"] - state["source_rows"] - new_rows
                            >= identity.MAXIMUM_PAGE_ROWS, "child_full_page_budget_reservation")
                attempts += 1
                name, spec = capture.prefix(number, active, ordinal), capture.descriptor(url)
                began, received = receipt(name + ".started.json"), receipt(name + ".received.json")
                raw = read(name + ".raw")
                require(exact(began, {"schema": "si-native-identity-continuation-page-start-v1", "query_date": at,
                        "active_panel": active, "ordinal": ordinal, "request": spec,
                        "request_sha256": hash_payload(spec), "started_at": began.get("started_at"),
                        "new_attempt": attempts, "cumulative_attempt": state["source_attempts"] + attempts,
                        "protocol_sha256": expected_protocol_sha256}), "child_page_start_binding")
                require(exact(received, {"schema": "si-native-identity-continuation-page-received-v1", "query_date": at,
                        "active_panel": active, "ordinal": ordinal, "request_sha256": hash_payload(spec),
                        "raw_path": name + ".raw", "raw_sha256": hash_bytes(raw), "raw_bytes": len(raw),
                        "received_at": received.get("received_at"), "http_status": 200,
                        "content_type": received.get("content_type")}), "child_page_receipt_binding")
                require(previous <= _clock(began["started_at"]) <= _clock(received["received_at"]),
                        "child_page_chronology")
                page = identity.CapturedDatedIdentityPage(at, active, ordinal, url, raw, began["started_at"],
                        received["received_at"], received["http_status"], received["content_type"])
                decoded = identity.page_payload(raw)
                new_bytes += len(raw)
                new_rows += len(decoded["results"])
                pages.append(page)
                previous = _clock(received["received_at"])
                allowed.update(name + suffix for suffix in (".raw", ".started.json", ".received.json"))
                following = decoded.get("next_url")
                if following is None:
                    url = None
                    break
                url = identity.next_url(following, at, active)
            require(url is None, "child_complete_both_panels_required")
        name = f"date-{number:03d}.qualified.private.json"
        raw, saved = read(name), receipt(name)
        retrieved_at = saved.get("retrieved_at")
        require(previous <= _clock(retrieved_at), "child_report_chronology")
        rebuilt = identity.qualify_dated_identity(tuple(pages), source._index, query_date=at,
                    started_at=state["source_started_at"], retrieved_at=retrieved_at)
        require(rebuilt.to_bytes() == raw, "child_qualification_exact_original_replay")
        entry = {"query_date": at, "report_path": name, "report_bytes_sha256": hash_bytes(raw),
                 "report_bytes": len(raw), "page_count": len(pages), "retrieved_at": retrieved_at}
        reports.append(entry)
        new_reports.append(entry)
        allowed.add(name)
        previous = _clock(retrieved_at)

    require(set(files) == allowed, "child_exact_closed_success_inventory")
    finished = inventory.get("completed_at")
    require(previous <= _clock(finished) <= _clock(complete.get("completed_at")), "child_final_receipt_chronology")
    base = {"schema": "si-native-identity-continuation-complete-v1", "status": "private_identity_continuation_complete",
            "protocol_sha256": expected_protocol_sha256, "code_head": expected_head, "completed_at": finished,
            "parent_attempts_consumed": state["source_attempts"], "new_attempts_consumed": attempts,
            "cumulative_attempts_consumed": state["source_attempts"] + attempts,
            "parent_failure_category": "legacy_failure_unclassified", "parent_failure_http_status": None,
            "source_only": True, "source_admitted": False, "ready_for_empirical_backtest": False,
            "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}
    require(exact(inventory, {**base, "schema": "si-native-identity-continuation-inventory-v1", "dates": reports,
            "parent_source_inventory_sha256": state["source_inventory_sha256"], "new_raw_bytes": new_bytes,
            "new_decoded_rows": new_rows}), "child_inventory_reconstructed_not_flag_accepted")
    require(exact(complete, {**base, "completed_at": complete["completed_at"],
            "inventory_bytes_sha256": hash_bytes(read("inventory.private.json")),
            "inventory_payload_sha256": hash_payload(inventory)}), "child_completion_binding")
    inventory_pin()
    metadata = canonical_json({"schema": "si-native-completed-identity-replay-v1", "parent_source": state,
            "child_head": expected_head, "child_code_identity_sha256": expected_code_identity_sha256,
            "child_protocol_sha256": expected_protocol_sha256, "child_inventory_sha256": inventory_sha256,
            "child_budget_bytes_sha256": budget_sha256, "child_completed_bytes_sha256": byte_pins["completed.json"],
            "child_started_at": start["started_at"], "child_completed_at": complete["completed_at"],
            "old_reports": state["completed_reports"], "new_reports": new_reports,
            "new_attempts": attempts, "cumulative_attempts": state["source_attempts"] + attempts,
            "new_raw_bytes": new_bytes, "new_rows": new_rows, "source_admitted": False,
            "ready_for_empirical_backtest": False, "outcome_looks": 0, "qc_attempts": 0,
            "backtest_result_exists": False})
    result = object.__new__(CompletedIdentityReplay)
    anchor = (metadata, source, read)
    for name, value in (("_metadata", metadata), ("_source", source), ("_read", read),
                        ("_anchor", anchor), ("_identity", anchor)):
        object.__setattr__(result, name, value)
    result.check()
    return result
