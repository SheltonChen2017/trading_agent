"""One protected, prospective manual continuation of exact retained identity pages.

The original failed claim and every successful prefix remain immutable. This
source-only continuation grants no economic, vintage, denominator or QC admission.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from types import MappingProxyType
from urllib.parse import urlencode
import urllib.request

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_dated_identity as identity
import scripts.capture_short_interest_native_identity as original
import scripts.load_short_interest_native_class_matrix as matrix_reader
import scripts.finalize_short_interest_master_offline as finalizer
import scripts.build_short_interest_native_master_offline as native_builder
from scripts.qualify_finra_short_interest import (CaptureRefusal, _NoRedirect, _git, _guard_lane,
        _prepare_capture_directory, _require_capture_platform)
from scripts.qualify_sharadar_companion import SharadarCaptureRefusal, _guard_remote, _http, _utc_now
from scripts.qualify_short_interest_action_supplement import _clock, _protected_bytes
from scripts.short_interest_keychain import KeychainSecret, ShortInterestKeychainError, read_named_keychain

SOURCE_CODE_FILES = original.CODE_FILES
CODE_FILES = SOURCE_CODE_FILES + ("data/exchange_calendar.py", "scripts/continue_short_interest_native_identity.py")
SOURCE = Path("artifacts/short_interest/native_dated_identity/native-identity-20261014T004245Z")
SOURCE_HEAD = "f61a40bf497747cffdda367d2a20c393383c8232"
SOURCE_REMOTE = "1f90c626328a236c51e78f57e0fe301e0412aabf"
SOURCE_CODE_IDENTITY = "d73c886ac24a625d5a56f2144e4112183e85685befa2a0e6ebb67772bfc542b2"
SOURCE_INVENTORY_SHA256 = "c3c4b6dfe08193ab0e943aea1f36ec057279139fe17af73cd79f8504908c24f8"
SOURCE_BUDGET_SHA256 = "33df02ba5722b3e80aea8daef5a6a432018a56d387272d48f8b3023c69e9c2e5"
SOURCE_STARTED_AT = "2026-10-14T00:42:45.296784Z"
SOURCE_REFUSED_AT = "2026-10-14T01:08:19.708883Z"
SOURCE_FAILED_STARTED_AT = "2026-10-14T01:07:48.090974Z"
SOURCE_FAILED_REFUSED_AT = "2026-10-14T01:08:19.284514Z"
REMAINING_DATES_SHA256 = "943fdb7c98058374c456d85f5b7d60bfc27c296dfd98846d8c8f1816ffbebc40"
SOURCE_FILE_PINS = {
    "protocol.json": "37b7047e0082fc377eade67fcae3e00c8bf9b0c97b6c286c297734468c67c782",
    "started.json": "62d4f93628ba7d6192f3f6052325eebad8fcabc17bae184401984ae3e4314ee7",
    "refused.json": "1d48ad8fe3f08b7f959f90f094f4e1447e1f8326d17f4c3bede6569fa1115afb",
    "date-045-active-page-02.started.json": "3bd2f69401562f354c34068b76df0e24fc1064f2de106661582a43d40c4b6a29",
    "date-045-active-page-02.refused.json": "f0864d819c690dc2083cac51033f9251d2d8f4a180a8bace82697a2d711a006d",
}
PARENT = Path("artifacts/short_interest/native_identity_continuation")
EXPECTED_PROTOCOL_SHA256 = "feebd180007f8c6fc07e1b5f55fc61131bfc8431ba1775d75063de6114cf045d"

SOURCE_PROTOCOL_SHA256 = "2ae2b0e1baeb0f04448bd23aa5f838b89da19d269af5ad7a0e6af4b59cb233ae"
SOURCE_DATES_SHA256 = "d6e722d910da972acfd5b91ae6147086e36cb99a522b634657d37f6a2781a7c0"


class ContinuationRefusal(CaptureRefusal):
    pass


def require(value, reason):
    if not value:
        raise ContinuationRefusal(reason)


def parsed(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate_receipt_key")
            result[key] = value
        return result
    def invalid(_):
        raise ContinuationRefusal("nonfinite_receipt_JSON")
    try:
        require(type(raw) is bytes, "receipt_bytes_required")
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=invalid)
    except (UnicodeError, json.JSONDecodeError):
        raise ContinuationRefusal("receipt_JSON_refused") from None


def initial_url(at, active):
    return identity.ENDPOINT + "?" + urlencode(identity.request_descriptor(at, active)["params"])


def descriptor(url):
    return {"method": "GET", "url": url, "authentication": "Bearer_header_not_recorded"}


def prefix(number, active, ordinal):
    return f"date-{number:03d}-{'active' if active else 'inactive'}-page-{ordinal:02d}"


def closed(receipt):
    require(type(receipt) is dict and all(type(receipt.get(key)) is int and receipt[key] == 0
            for key in ("outcome_looks", "qc_attempts"))
            and receipt.get("backtest_result_exists") is False, "closed_source_counters")


@dataclass(frozen=True, slots=True, init=False)
class ParentIdentity:
    _metadata: str = field(repr=False)
    _partial: tuple = field(repr=False)
    _index: identity.CompositeNativeIndex = field(repr=False)
    _anchor: tuple = field(repr=False)
    _anchor_identity: tuple = field(repr=False)

    def __init__(self):
        raise ContinuationRefusal("parent_identity_factory_required")

    def check(self):
        require(type(self) is ParentIdentity and self._anchor is self._anchor_identity
                and type(self._anchor) is tuple and len(self._anchor) == 3
                and all(current is original for current, original in zip(
                    (self._metadata, self._partial, self._index), self._anchor)), "parent_identity_changed")
        self._index.metadata()
        for page in self._partial:
            page._guard()

    def payload(self):
        self.check()
        return json.loads(self._metadata)


def verify_parent(files, *, byte_pins, inventory_sha256, budget_raw, budget_sha256,
                  expected_head, expected_protocol_sha256, expected_code_identity_sha256,
                  historical_code, dates, dates_sha256, index, local_guard,
                  completed_dates=44, failed_date_number=45, failed_active=True,
                  failed_ordinal=2, expected_attempts=491):
    """Rebuild supplied original evidence; no saved flag admits its contents.

    Fixture overrides must be separately frozen. The eventual real adapter
    must use the exact registered 112-date/44-report/491-attempt parent pins.
    The guarded historical_code(head, fixed_path) seam returns committed
    binary bytes, not a working-file digest or caller-supplied completion flag.
    """
    local_guard()
    require(type(files) in (dict, _ParentFiles) and type(byte_pins) is dict and set(files) == set(byte_pins),
            "exact_parent_inventory")
    require(type(dates) is tuple and dates == tuple(sorted(set(dates))) and len(dates) > completed_dates
            and hash_payload(list(dates)) == dates_sha256
            and type(completed_dates) is int and completed_dates >= 0
            and failed_date_number == completed_dates + 1 and failed_active is True
            and type(failed_ordinal) is int and 2 <= failed_ordinal <= identity.MAXIMUM_PAGES_PER_PANEL
            and type(expected_attempts) is int and expected_attempts > 0
            and type(index) is identity.CompositeNativeIndex, "exact_parent_resume_shape")
    index.metadata()
    for at in dates:
        local_guard()
        identity.request_descriptor(at, True)
    if type(files) is _ParentFiles:
        files.check()
        require(files.inventory_sha256() == inventory_sha256 and files.pins() == byte_pins,
                "registered_parent_inventory_pin")
    else:
        for name in sorted(files):
            local_guard()
            raw = files[name]
            require(type(name) is str and "/" not in name and "\\" not in name and type(raw) is bytes
                    and hash_bytes(raw) == byte_pins[name], "registered_parent_file_bytes")
        require(hash_payload([{"name": name, "sha256": byte_pins[name], "bytes": len(files[name])}
                              for name in sorted(files)]) == inventory_sha256, "registered_parent_inventory_pin")

    def read(name):
        local_guard()
        require(name in files, "missing_parent_receipt")
        return files[name]

    protocol, start, refused = (parsed(read(name)) for name in ("protocol.json", "started.json", "refused.json"))
    closed(protocol)
    closed(start)
    closed(refused)
    require(hash_payload(protocol) == expected_protocol_sha256
            and protocol.get("schema") == "si-native-dated-identity-capture-protocol-v1"
            and protocol.get("policy_sha256") == identity.POLICY_SHA256
            and protocol.get("policy") == identity.identity_policy()
            and protocol.get("settlement_dates_sha256") == dates_sha256
            and protocol.get("code_files") == list(SOURCE_CODE_FILES)
            and protocol.get("automatic_retries") == 0
            and protocol.get("proxies") is False and protocol.get("redirects") is False,
            "original_frozen_protocol")
    require(start.get("schema") == "si-native-dated-identity-start-v1"
            and start.get("code_head") == expected_head
            and start.get("protocol_sha256") == expected_protocol_sha256
            and start.get("source_pins") == protocol.get("source_pins")
            and refused.get("schema") == "si-native-dated-identity-refusal-v1"
            and refused.get("status") == "dated_identity_capture_refused", "original_enclosing_binding")
    code = []
    for name in SOURCE_CODE_FILES:
        local_guard()
        raw = historical_code(expected_head, name)
        local_guard()
        require(type(raw) is bytes, "historical_committed_binary_code_required")
        code.append({"path": name, "sha256": hash_bytes(raw)})
    require(hash_payload({"git_commit": expected_head, "files": code})
            == expected_code_identity_sha256 == start.get("code_identity_sha256"), "original_historical_code_identity")
    local_guard()
    require(type(budget_raw) is bytes and hash_bytes(budget_raw) == budget_sha256, "original_spent_budget_bytes")
    budget = parsed(budget_raw)
    require(budget.get("schema") == "si-native-dated-identity-global-budget-v1"
            and budget.get("code_head") == expected_head and budget.get("remote_head") == start.get("remote_head")
            and budget.get("protocol_sha256") == expected_protocol_sha256
            and budget.get("source_pins") == protocol.get("source_pins")
            and budget.get("started_at") == start.get("started_at")
            and budget.get("maximum_attempts") == identity.MAXIMUM_REQUESTS
            and budget.get("restart_or_resume") is False and budget.get("unused_slots_repurposable") is False,
            "original_spent_budget_binding")
    allowed = {"protocol.json", "started.json", "refused.json"}
    previous, attempt, raw_bytes, rows, reports = _clock(start["started_at"]), 0, 0, 0, []

    def page(number, active, ordinal, url):
        nonlocal previous, attempt, raw_bytes, rows
        local_guard()
        attempt += 1
        name = prefix(number, active, ordinal)
        began, receipt, raw = parsed(read(name + ".started.json")), parsed(read(name + ".received.json")), read(name + ".raw")
        at, request_sha = dates[number - 1], hash_payload(descriptor(url))
        require(began == {"schema": "si-native-identity-page-start-v1", "code_head": expected_head,
                "protocol_sha256": expected_protocol_sha256, "query_date": at, "active_panel": active,
                "ordinal": ordinal, "attempt": attempt, "request": descriptor(url),
                "request_sha256": request_sha, "started_at": began.get("started_at")}, "original_page_start_binding")
        require(receipt.get("schema") == "si-native-identity-page-received-v1"
                and receipt.get("query_date") == at and receipt.get("active_panel") is active
                and receipt.get("ordinal") == ordinal and receipt.get("request_sha256") == request_sha
                and receipt.get("raw_sha256") == hash_bytes(raw) and receipt.get("raw_bytes") == len(raw)
                and receipt.get("raw_path") == name + ".raw", "original_page_receipt_binding")
        require(previous <= _clock(began["started_at"]) <= _clock(receipt["received_at"]), "original_page_chronology")
        value = identity.CapturedDatedIdentityPage(at, active, ordinal, url, raw, began["started_at"],
                    receipt["received_at"], receipt["http_status"], receipt["content_type"])
        payload = identity.page_payload(raw)
        following = payload.get("next_url")
        if following is not None:
            following = identity.next_url(following, at, active)
        raw_bytes += len(raw)
        rows += len(payload["results"])
        require(raw_bytes <= identity.MAXIMUM_TOTAL_BYTES and rows <= identity.MAXIMUM_ROWS,
                "original_cumulative_budget")
        previous = _clock(receipt["received_at"])
        allowed.update(name + suffix for suffix in (".started.json", ".received.json", ".raw"))
        return value, following

    for number in range(1, completed_dates + 1):
        selected = []
        at = dates[number - 1]
        for active in (True, False):
            url, seen = initial_url(at, active), set()
            for ordinal in range(1, identity.MAXIMUM_PAGES_PER_PANEL + 1):
                local_guard()
                require(url not in seen, "original_panel_cycle")
                seen.add(url)
                value, url = page(number, active, ordinal, url)
                selected.append(value)
                if url is None:
                    break
            require(url is None, "original_complete_panel_required")
        name = f"date-{number:03d}.qualified.private.json"
        original = read(name)
        saved = parsed(original)
        checked = saved.get("retrieved_at")
        require(previous <= _clock(checked), "original_report_chronology")
        rebuilt = identity.qualify_dated_identity(tuple(selected), index, query_date=at,
                         started_at=start["started_at"], retrieved_at=checked)
        require(rebuilt.to_bytes() == original, "original_qualification_exact_replay")
        reports.append({"query_date": at, "report_path": name, "report_bytes_sha256": hash_bytes(original),
                        "report_bytes": len(original), "page_count": len(selected), "retrieved_at": checked})
        allowed.add(name)
        previous = _clock(checked)

    partial, url, seen = [], initial_url(dates[failed_date_number - 1], True), set()
    for ordinal in range(1, failed_ordinal):
        local_guard()
        require(url is not None and url not in seen, "original_partial_panel_chain")
        seen.add(url)
        value, url = page(failed_date_number, True, ordinal, url)
        partial.append(value)
    require(url is not None and url not in seen, "original_failed_cursor_required")
    identity.next_url(url, dates[failed_date_number - 1], True)
    name = prefix(failed_date_number, True, failed_ordinal)
    failed_start, failed_receipt = parsed(read(name + ".started.json")), parsed(read(name + ".refused.json"))
    attempt += 1
    require(failed_start == {"schema": "si-native-identity-page-start-v1", "code_head": expected_head,
            "protocol_sha256": expected_protocol_sha256, "query_date": dates[failed_date_number - 1],
            "active_panel": True, "ordinal": failed_ordinal, "attempt": attempt,
            "request": descriptor(url), "request_sha256": hash_payload(descriptor(url)),
            "started_at": failed_start.get("started_at")}, "original_failed_start_exact_cursor")
    require(failed_receipt == {"schema": "si-native-identity-page-refused-v1",
            "query_date": dates[failed_date_number - 1], "active_panel": True, "ordinal": failed_ordinal,
            "attempt": attempt, "http_status": None, "refused_at": failed_receipt.get("refused_at"),
            "code": "identity_page_refused_no_retry"}, "original_legacy_failure_unclassified")
    require(previous <= _clock(failed_start["started_at"]) <= _clock(failed_receipt["refused_at"])
            <= _clock(refused["refused_at"]), "original_failed_enclosing_chronology")
    allowed.update(name + suffix for suffix in (".started.json", ".refused.json"))
    require(set(files) == allowed and attempt == expected_attempts, "original_complete_success_and_failure_inventory")
    state = {"source_head": expected_head, "source_protocol_sha256": expected_protocol_sha256,
             "source_inventory_sha256": inventory_sha256, "source_budget_bytes_sha256": budget_sha256,
             "source_code_identity_sha256": expected_code_identity_sha256, "source_started_at": start["started_at"],
             "source_refused_at": refused["refused_at"], "source_attempts": attempt,
             "source_received_pages": attempt - 1, "source_raw_bytes": raw_bytes, "source_rows": rows,
             "source_failure_category": "legacy_failure_unclassified", "source_failure_http_status": None,
             "dates": list(dates), "dates_sha256": dates_sha256, "completed_reports": reports,
             "failed_date_number": failed_date_number, "failed_active_panel": True,
             "failed_ordinal": failed_ordinal, "failed_request": descriptor(url),
             "failed_request_sha256": hash_payload(descriptor(url)), "partial_seen_urls": sorted(seen),
             "failed_start_bytes_sha256": byte_pins[name + ".started.json"],
             "failed_refusal_bytes_sha256": byte_pins[name + ".refused.json"],
             "original_native_index": index.metadata()}
    metadata = canonical_json(state)
    result = object.__new__(ParentIdentity)
    anchor = (metadata, tuple(partial), index)
    for field_name, value in (("_metadata", metadata), ("_partial", anchor[1]), ("_index", index),
                              ("_anchor", anchor), ("_anchor_identity", anchor)):
        object.__setattr__(result, field_name, value)
    result.check()
    return result


def freeze_protocol(source):
    require(type(source) is ParentIdentity, "verified_original_parent_required")
    value = source.payload()
    remaining = value["dates"][value["failed_date_number"] - 1:]
    maximum = len(remaining) * 2 * identity.MAXIMUM_PAGES_PER_PANEL - (value["failed_ordinal"] - 1)
    return {"schema": "si-native-identity-manual-continuation-protocol-v1",
            "code_files": list(CODE_FILES), "capture_parent": str(PARENT),
            "registered_source_path": str(SOURCE), "registered_parent_file_pins": dict(SOURCE_FILE_PINS),
            "source": value, "remaining_dates": remaining, "remaining_dates_sha256": hash_payload(remaining),
            "maximum_new_attempts": maximum, "maximum_cumulative_attempts": value["source_attempts"] + maximum,
            "maximum_cumulative_rows": identity.MAXIMUM_ROWS, "maximum_cumulative_bytes": identity.MAXIMUM_TOTAL_BYTES,
            "maximum_response_bytes": identity.MAXIMUM_RESPONSE_BYTES,
            "maximum_page_rows": identity.MAXIMUM_PAGE_ROWS, "maximum_pages_per_panel": identity.MAXIMUM_PAGES_PER_PANEL,
            "authentication": "owner_named_massive_login_Keychain_fixed_Bearer_header",
            "credential_item": {"provider": "massive", "service": "trading-agent-massive", "account": "massive"},
            "parent_budget": "immutable_consumed_no_unused_slot_reuse",
            "continuation": "one_explicit_manual_resume_exact_failed_URL_once_then_remaining_panels",
            "automatic_retries": 0, "proxies": False, "redirects": False,
            "publication": "anchored_owned_directory_FDs_inode_owner0700_O_NOFOLLOW_exclusive0600_fsync_original_raw_prefix_immutable_parent_references",
            "output_checks": "before_every_publication_key_and_HTTP_same_prepared_parent_and_run_inode_no_symlink_or_mode_drift",
            "guard_schedule": "local_before_read_check_publication_remote_start_before_HTTP_final",
            "source_only": True, "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}


def failure_metadata(error, observed_status=None):
    """Only fixed categories and bounded HTTP status; no str(error) ever."""
    category, status = "source_or_guard_refused", observed_status
    if isinstance(error, SharadarCaptureRefusal):
        category = {"network_failure": "transport_unavailable", "http_not_200": "http_status_refused",
                    "response_size_limit": "response_size_refused", "content_type": "content_type_refused"}.get(
                        error.code if type(error.code) is str else None, "source_or_guard_refused")
        if type(status) is not int:
            status = error.http_status
    elif isinstance(error, ShortInterestKeychainError):
        category = "credential_access_refused"
    elif isinstance(error, identity.NativeDatedIdentityError):
        category = "dated_identity_contract_refused"
    elif type(error) is TimeoutError:
        category = "timeout_observed"
    elif isinstance(error, OSError):
        category = "transport_or_storage_refused"
    if type(status) is not int or not 100 <= status <= 599:
        status = None
    return category, status


def capture_continuation(source, *, expected_protocol_sha256, code_head, code_identity_sha256,
                      claim, publish, get_secret, request, local_guard, remote_guard, now):
    """Single manual round with protected adapters; no automatic retry.

    claim must create-exclusive; publish must enforce owned protected output.
    The future adapter supplies mandatory host/root/branch/HEAD/status guards,
    exact actual-remote equality, historical binary source loading and code pins.
    """
    local_guard()
    remote_guard()
    frozen = freeze_protocol(source)
    frozen_sha = hash_payload(frozen)
    require(frozen_sha == expected_protocol_sha256, "prospective_continuation_protocol_unregistered")
    state = source.payload()
    started_at = now()
    require(_clock(state["source_refused_at"]) <= _clock(started_at), "continuation_after_parent_refusal")
    # Claim identity deliberately excludes current clock/head. A new head must
    # not silently reset the one manual resume of this original failed cursor.
    claim_id = hash_payload({"source_inventory_sha256": state["source_inventory_sha256"],
                             "failed_request_sha256": state["failed_request_sha256"],
                             "failed_start_bytes_sha256": state["failed_start_bytes_sha256"],
                             "purpose": "single_explicit_native_identity_manual_continuation"})
    local_guard()
    claim(claim_id, {"protocol_sha256": frozen_sha, "source_budget_bytes_sha256": state["source_budget_bytes_sha256"],
                    "code_head": code_head, "started_at": started_at,
                    "maximum_new_attempts": frozen["maximum_new_attempts"],
                    "parent_attempts_consumed": state["source_attempts"], "automatic_retries": 0})
    attempts, new_bytes, new_rows = 0, 0, 0
    previous = _clock(started_at)

    def check():
        local_guard()
        source.check()
        require(hash_payload(freeze_protocol(source)) == frozen_sha, "continuation_source_or_protocol_changed")

    def save(name, value):
        check()
        publish(name, value if type(value) is bytes else canonical_json(value).encode())

    def refusal(error, at, active, ordinal, began, status):
        failed_at = now()
        require(_clock(began) <= _clock(failed_at), "continuation_failure_chronology")
        category, observed = failure_metadata(error, status)
        save(prefix(at, active, ordinal) + ".refused.json", {
            "schema": "si-native-identity-continuation-page-refused-v1", "failure_category": category,
            "http_status": observed, "new_attempt": attempts, "cumulative_attempt": state["source_attempts"] + attempts,
            "refused_at": failed_at, "automatic_retries": 0})

    try:
        save("protocol.private.json", frozen)
        save("started.json", {"schema": "si-native-identity-continuation-start-v1", "code_head": code_head,
             "code_identity_sha256": code_identity_sha256, "protocol_sha256": frozen_sha,
             "started_at": started_at, "source_attempts_consumed": state["source_attempts"],
             "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False})
        check()
        secret = get_secret("massive")
        check()
        require(type(secret) is KeychainSecret, "exact_named_keychain_secret_required")
        reports = list(state["completed_reports"])
        for number in range(state["failed_date_number"], len(state["dates"]) + 1):
            at, pages = state["dates"][number - 1], []
            for active in (True, False):
                resumed = number == state["failed_date_number"] and active is True
                url = state["failed_request"]["url"] if resumed else initial_url(at, active)
                ordinal = state["failed_ordinal"] if resumed else 1
                seen = set(state["partial_seen_urls"]) if resumed else set()
                if resumed:
                    pages.extend(source._partial)
                for ordinal in range(ordinal, identity.MAXIMUM_PAGES_PER_PANEL + 1):
                    check()
                    require(url not in seen, "continuation_panel_cycle")
                    if ordinal == 1:
                        require(url == initial_url(at, active), "continuation_initial_panel_scope")
                    else:
                        identity.next_url(url, at, active)
                    require(not secret.echoed_in(url.encode("utf-8")), "request_credential_echo_refused")
                    seen.add(url)
                    require(attempts < frozen["maximum_new_attempts"], "continuation_new_attempt_budget")
                    require(frozen["maximum_cumulative_bytes"] - state["source_raw_bytes"] - new_bytes >= identity.MAXIMUM_RESPONSE_BYTES
                            and frozen["maximum_cumulative_rows"] - state["source_rows"] - new_rows >= identity.MAXIMUM_PAGE_ROWS,
                            "continuation_cumulative_storage_or_row_budget")
                    began = now()
                    require(previous <= _clock(began), "continuation_request_chronology")
                    attempts += 1
                    name, call, status = prefix(number, active, ordinal), descriptor(url), None
                    save(name + ".started.json", {"schema": "si-native-identity-continuation-page-start-v1",
                         "query_date": at, "active_panel": active, "ordinal": ordinal, "request": call,
                         "request_sha256": hash_payload(call), "started_at": began, "new_attempt": attempts,
                         "cumulative_attempt": state["source_attempts"] + attempts, "protocol_sha256": frozen_sha})
                    try:
                        check()
                        remote_guard()
                        check()
                        raw, media, status = request(call, secret, identity.MAXIMUM_RESPONSE_BYTES)
                        require(type(raw) is bytes and len(raw) <= identity.MAXIMUM_RESPONSE_BYTES
                                and type(media) is str and len(media) <= 4096, "continuation_response_bounds")
                        require(not secret.echoed_in(raw) and not secret.echoed_in(media.encode()), "credential_echo_refused")
                        require(type(status) is int and status == 200 and media.split(";", 1)[0].strip().lower() == "application/json",
                                "continuation_HTTP_or_media_refused")
                        received_at = now()
                        require(_clock(began) <= _clock(received_at), "continuation_response_chronology")
                        save(name + ".raw", raw)
                        receipt = {"schema": "si-native-identity-continuation-page-received-v1", "query_date": at,
                             "active_panel": active, "ordinal": ordinal, "request_sha256": hash_payload(call),
                             "raw_path": name + ".raw", "raw_sha256": hash_bytes(raw), "raw_bytes": len(raw),
                             "received_at": received_at, "http_status": status, "content_type": media}
                        save(name + ".received.json", receipt)
                        new_bytes += len(raw)
                        page = identity.CapturedDatedIdentityPage(at, active, ordinal, url, raw, began, received_at, status, media)
                        value = identity.page_payload(raw)
                        new_rows += len(value["results"])
                        following = value.get("next_url")
                        if following is not None:
                            following = identity.next_url(following, at, active)
                        pages.append(page)
                        previous = _clock(received_at)
                        if following is None:
                            break
                        require(ordinal < identity.MAXIMUM_PAGES_PER_PANEL, "continuation_panel_page_budget")
                        url = following
                    except (ContinuationRefusal, identity.NativeDatedIdentityError, CaptureRefusal,
                            ShortInterestKeychainError, ValueError, TypeError, OSError, KeyError) as error:
                        refusal(error, number, active, ordinal, began, status)
                        raise
            retrieved_at = now()
            require(previous <= _clock(retrieved_at), "continuation_report_chronology")
            result = identity.qualify_dated_identity(tuple(pages), source._index, query_date=at,
                          started_at=state["source_started_at"], retrieved_at=retrieved_at)
            raw = result.to_bytes()
            name = f"date-{number:03d}.qualified.private.json"
            save(name, raw)
            reports.append({"query_date": at, "report_path": name, "report_bytes_sha256": hash_bytes(raw),
                            "report_bytes": len(raw), "page_count": len(pages), "retrieved_at": retrieved_at})
            previous = _clock(retrieved_at)
        check()
        require([report["query_date"] for report in reports] == state["dates"], "all_original_and_continued_dates_required")
        finished_at = now()
        require(previous <= _clock(finished_at), "continuation_completion_chronology")
        completion = {"schema": "si-native-identity-continuation-complete-v1", "status": "private_identity_continuation_complete",
             "protocol_sha256": frozen_sha, "code_head": code_head, "completed_at": finished_at,
             "parent_attempts_consumed": state["source_attempts"], "new_attempts_consumed": attempts,
             "cumulative_attempts_consumed": state["source_attempts"] + attempts,
             "parent_failure_category": "legacy_failure_unclassified", "parent_failure_http_status": None,
             "source_only": True, "source_admitted": False, "ready_for_empirical_backtest": False,
             "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}
        inventory = {**completion, "schema": "si-native-identity-continuation-inventory-v1", "dates": reports,
             "parent_source_inventory_sha256": state["source_inventory_sha256"], "new_raw_bytes": new_bytes,
             "new_decoded_rows": new_rows}
        inventory_raw = canonical_json(inventory).encode()
        save("inventory.private.json", inventory_raw)
        done = now()
        require(_clock(finished_at) <= _clock(done), "continuation_final_receipt_chronology")
        remote_guard()
        check()
        completion["completed_at"] = done
        completion["inventory_bytes_sha256"] = hash_bytes(inventory_raw)
        completion["inventory_payload_sha256"] = hash_payload(inventory)
        save("completed.json", completion)
        return completion
    except (ContinuationRefusal, identity.NativeDatedIdentityError, CaptureRefusal,
            ShortInterestKeychainError, ValueError, TypeError, OSError, KeyError) as error:
        failed_at = now()
        require(_clock(started_at) <= _clock(failed_at), "continuation_enclosing_failure_chronology")
        category, status = failure_metadata(error)
        save("refused.json", {"schema": "si-native-identity-continuation-refused-v1", "failure_category": category,
             "http_status": status, "refused_at": failed_at, "parent_attempts_consumed": state["source_attempts"],
             "new_attempts_consumed": attempts, "cumulative_attempts_consumed": state["source_attempts"] + attempts,
             "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False})
        raise


@dataclass(frozen=True, slots=True, init=False)
class _ParentFiles:
    """Guarded two-pass replay keeps no whole-parent raw bodies in memory."""
    _entries: MappingProxyType = field(repr=False)
    _reader: object = field(repr=False)
    _anchor: tuple = field(repr=False)
    _anchor_identity: tuple = field(repr=False)

    def __init__(self):
        raise ContinuationRefusal("protected_parent_files_factory_required")

    def check(self):
        require(type(self) is _ParentFiles and self._anchor is self._anchor_identity
                and type(self._anchor) is tuple and len(self._anchor) == 2
                and self._entries is self._anchor[0] and self._reader is self._anchor[1],
                "protected_parent_files_changed")

    def __iter__(self):
        self.check()
        return iter(self._entries)

    def __getitem__(self, name):
        self.check()
        require(name in self._entries, "missing_parent_receipt")
        raw = self._reader(name)
        expected = self._entries[name]
        require(type(raw) is bytes and hash_bytes(raw) == expected[0] and len(raw) == expected[1],
                "protected_parent_replay_bytes_changed")
        return raw

    def pins(self):
        self.check()
        return {name: value[0] for name, value in self._entries.items()}

    def inventory_sha256(self):
        self.check()
        return hash_payload([{"name": name, "sha256": self._entries[name][0], "bytes": self._entries[name][1]}
                             for name in sorted(self._entries)])


@dataclass(frozen=True, slots=True)
class _GuardedSourcePath:
    """Task-local read-only path facade guards each existing custody operation.

    Existing offline master readers accept PathLike objects. This avoids
    copying their archival validation or repeatedly querying the remote for
    every source file. It never alters another module's guard or globals.
    """
    path: Path
    guard: object = field(repr=False)
    _anchor: tuple = field(init=False, repr=False)

    def __post_init__(self):
        object.__setattr__(self, "_anchor", (self.path, self.guard))

    def _check(self):
        require(type(self) is _GuardedSourcePath and type(self._anchor) is tuple and len(self._anchor) == 2
                and self.path is self._anchor[0] and self.guard is self._anchor[1], "guarded_source_path_changed")
        self.guard()

    def __truediv__(self, child):
        self._check()
        return _GuardedSourcePath(self.path / child, self.guard)

    def __fspath__(self):
        self._check()
        return os.fspath(self.path)

    @property
    def name(self):
        self._check()
        return self.path.name

    @property
    def parent(self):
        self._check()
        return _GuardedSourcePath(self.path.parent, self.guard)

    def absolute(self):
        self._check()
        return self.path.absolute()

    def resolve(self):
        self._check()
        return self.path.resolve()

    def lstat(self):
        self._check()
        return self.path.lstat()

    def iterdir(self):
        self._check()
        for item in self.path.iterdir():
            self._check()
            yield _GuardedSourcePath(item, self.guard)


def _local(root, head):
    _require_capture_platform()
    require(root == Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest"),
            "designated_absolute_identity_worktree")
    _guard_lane(root, head)


def _read(root, path, maximum, *, head):
    _local(root, head)
    raw = _protected_bytes(path, maximum)
    _local(root, head)
    return raw


def _limit(name):
    if re.fullmatch(r"date-[0-9]{3}-(active|inactive)-page-[0-9]{2}\.raw", name):
        return identity.MAXIMUM_RESPONSE_BYTES
    if re.fullmatch(r"date-[0-9]{3}\.qualified\.private\.json", name):
        return identity.MAXIMUM_DATE_REPORT_BYTES
    require(name in {"protocol.json", "started.json", "refused.json"}
            or re.fullmatch(r"date-[0-9]{3}-(active|inactive)-page-[0-9]{2}\.(started|received|refused)\.json", name),
            "original_parent_filename_refused")
    return 65536


def _protected_parent_files(root, *, head):
    _local(root, head)
    directory = root / SOURCE
    require(directory.resolve() == directory, "original_parent_symlink_refused")
    info = directory.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o700, "original_parent_directory_protection")
    _local(root, head)
    names = tuple(sorted(item.name for item in directory.iterdir()))
    require(len(names) == 1519, "original_exact_1519_file_inventory")
    entries = {}
    for name in names:
        raw = _read(root, directory / name, _limit(name), head=head)
        digest = hash_bytes(raw)
        require(name not in SOURCE_FILE_PINS or digest == SOURCE_FILE_PINS[name], "registered_parent_anchor_bytes")
        entries[name] = (digest, len(raw))
        del raw
    value = object.__new__(_ParentFiles)
    reader = lambda name: _read(root, directory / name, _limit(name), head=head)
    anchor = (MappingProxyType(entries), reader)
    for name, item in (("_entries", anchor[0]), ("_reader", reader), ("_anchor", anchor), ("_anchor_identity", anchor)):
        object.__setattr__(value, name, item)
    require(value.inventory_sha256() == SOURCE_INVENTORY_SHA256, "registered_parent_1519_file_inventory_bytes")
    return value


def _historical_code(root, commit, name, *, head):
    _local(root, head)
    require(commit == SOURCE_HEAD and name in SOURCE_CODE_FILES, "fixed_original_commit_and_code_path")
    result = subprocess.run(["git", "show", commit + ":" + name], cwd=root, capture_output=True, check=False)
    _local(root, head)
    require(result.returncode == 0 and type(result.stdout) is bytes, "original_committed_binary_code_unavailable")
    return result.stdout


def _source_inputs(root, *, head):
    """Exact saved date header and original archive/index; no new retrieval.

    The complete compact matrix was independently rebuilt when registered.
    Its pinned header here supplies only the exact date inventory. Original
    native archive/index validation remains in its existing guarded readers.
    """
    raw = _read(root, root / matrix_reader.SOURCE / "header.private.json",
                matrix_reader.LIMITS["header.private.json"], head=head)
    require(hash_bytes(raw) == matrix_reader.FILE_PINS["header.private.json"], "registered_source_matrix_header_bytes")
    header = parsed(raw)
    dates = header.get("settlements")
    require(type(dates) is list and len(dates) == 112 and dates == sorted(set(dates))
            and hash_payload(dates) == SOURCE_DATES_SHA256
            and hash_payload(dates[44:]) == REMAINING_DATES_SHA256, "registered_original_and_remaining_dates")
    guarded_root = _GuardedSourcePath(root, lambda: _local(root, head))
    captures, anchor = finalizer._reload(guarded_root)
    _local(root, head)
    native_builder._source_index(guarded_root, anchor)
    _local(root, head)
    index = identity.build_composite_native_index(captures[0])
    _local(root, head)
    return tuple(dates), index


def load_parent(root, *, head):
    """Only the exact registered parent; local checks, no credential/HTTP path."""
    _local(root, head)
    require(_git(root, "merge-base", "--is-ancestor", SOURCE_HEAD, head) == "", "original_parent_lane_ancestry")
    dates, index = _source_inputs(root, head=head)
    files = _protected_parent_files(root, head=head)
    budget = _read(root, root / SOURCE.parent / ("budget-" + SOURCE_PROTOCOL_SHA256 + ".json"), 65536, head=head)
    start, end = parsed(files["started.json"]), parsed(files["refused.json"])
    failed_start = parsed(files["date-045-active-page-02.started.json"])
    failed_end = parsed(files["date-045-active-page-02.refused.json"])
    require(start.get("started_at") == SOURCE_STARTED_AT and start.get("remote_head") == SOURCE_REMOTE
            and end.get("refused_at") == SOURCE_REFUSED_AT
            and failed_start.get("started_at") == SOURCE_FAILED_STARTED_AT
            and failed_end.get("refused_at") == SOURCE_FAILED_REFUSED_AT, "registered_original_source_clocks")
    value = verify_parent(files, byte_pins=files.pins(), inventory_sha256=SOURCE_INVENTORY_SHA256,
             budget_raw=budget, budget_sha256=SOURCE_BUDGET_SHA256, expected_head=SOURCE_HEAD,
             expected_protocol_sha256=SOURCE_PROTOCOL_SHA256, expected_code_identity_sha256=SOURCE_CODE_IDENTITY,
             historical_code=lambda commit, name: _historical_code(root, commit, name, head=head),
             dates=dates, dates_sha256=SOURCE_DATES_SHA256, index=index, local_guard=lambda: _local(root, head))
    policy = freeze_protocol(value)
    require(policy["maximum_new_attempts"] == 8703 and policy["maximum_cumulative_attempts"] == 9194
            and len(policy["remaining_dates"]) == 68
            and policy["remaining_dates_sha256"] == REMAINING_DATES_SHA256, "registered_8703_request_continuation_scope")
    _local(root, head)
    return value


def _code_identity(root, head):
    files = []
    for name in CODE_FILES:
        _local(root, head)
        files.append({"path": name, "sha256": hash_bytes((root / name).read_bytes())})
    _local(root, head)
    return hash_payload({"git_commit": head, "files": files})


def preflight(root, *, head, remote):
    """Read-only source/code qualification for prospective protocol registration.

    PENDING is intentionally permitted here, not in capture. No directories,
    claims, credentials or provider requests are created by this route.
    """
    _require_capture_platform()
    _local(root, head)
    _guard_remote(root, remote)
    source = load_parent(root, head=head)
    digest = hash_payload(freeze_protocol(source))
    code = _code_identity(root, head)
    _local(root, head)
    _guard_remote(root, remote)
    return {"status": "identity_continuation_preflight_complete", "prospective_protocol_sha256": digest,
            "code_head": head, "code_identity_sha256": code, "source_inventory_sha256": SOURCE_INVENTORY_SHA256,
            "provider_requests": 0, "credential_reads": 0, "outcome_looks": 0, "qc_attempts": 0,
            "ready_for_empirical_backtest": False, "backtest_result_exists": False}


class _OwnedOutput:
    """Only this newly prepared inode may receive this invocation's bytes.

    Names are opened relative to retained directory FDs, never by resolving a
    mutable output pathname at publication time. Identity/mode are rechecked
    before open, before the first byte and after fsync. A race can at worst
    leave an empty/partial owned prefix; it cannot redirect payload to a
    replacement path and it never creates a completed receipt after drift.
    """
    __slots__ = ("_anchor", "_anchor_identity", "_closed")

    @staticmethod
    def _stamp(info):
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o700, "owned_output_directory_protection")
        return info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)

    def __init__(self, directory, guard):
        _require_capture_platform()
        require(os.name == "posix" and hasattr(os, "O_DIRECTORY") and hasattr(os, "O_NOFOLLOW")
                and os.open in os.supports_dir_fd, "owned_output_directory_FD_capability")
        guard()
        require(type(directory) is Path or isinstance(directory, Path), "owned_output_exact_path")
        parent = directory.parent
        require(directory.is_absolute() and directory.resolve() == directory and parent.resolve() == parent,
                "owned_output_path_symlink")
        directory_stamp, parent_stamp = self._stamp(directory.lstat()), self._stamp(parent.lstat())
        parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            directory_fd = os.open(directory.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        except BaseException:
            os.close(parent_fd)
            raise
        anchor = (directory, parent, directory_fd, parent_fd, directory_stamp, parent_stamp, guard)
        self._anchor = self._anchor_identity = anchor
        self._closed = False
        try:
            self.check()
        except BaseException:
            self.close()
            raise

    def check(self):
        require(type(self) is _OwnedOutput and self._anchor is self._anchor_identity
                and type(self._anchor) is tuple and len(self._anchor) == 7 and self._closed is False,
                "owned_output_binding_changed")
        directory, parent, directory_fd, parent_fd, expected, expected_parent, guard = self._anchor
        guard()
        require(directory.resolve() == directory and parent.resolve() == parent,
                "owned_output_path_symlink")
        require(self._stamp(directory.lstat()) == self._stamp(os.fstat(directory_fd)) == expected
                and self._stamp(parent.lstat()) == self._stamp(os.fstat(parent_fd)) == expected_parent,
                "owned_output_directory_inode_changed")

    def publish(self, name, raw, *, parent=False):
        self.check()
        require(type(name) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", name)
                and name not in {".", ".."} and type(raw) is bytes and type(parent) is bool,
                "owned_output_name_or_bytes")
        directory_fd = self._anchor[3 if parent else 2]
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory_fd)
        try:
            # Exclusive ownership permits fixing this new inode's restrictive
            # umask only; no existing file or directory is chmodded here.
            os.fchmod(fd, 0o600)
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                    and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1,
                    "owned_output_file_protection")
            def file_check():
                self.check()
                current, named = os.fstat(fd), os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                require(stat.S_ISREG(named.st_mode) and stat.S_IMODE(current.st_mode) == stat.S_IMODE(named.st_mode) == 0o600
                        and current.st_uid == named.st_uid == os.getuid() and current.st_nlink == named.st_nlink == 1
                        and (current.st_dev, current.st_ino) == (named.st_dev, named.st_ino) == (info.st_dev, info.st_ino),
                        "owned_output_file_inode_changed")
            file_check()
            offset = 0
            while offset < len(raw):
                file_check()
                written = os.write(fd, memoryview(raw)[offset:])
                require(type(written) is int and written > 0, "owned_output_short_write")
                offset += written
            os.fsync(fd)
            file_check()
            os.fsync(directory_fd)
        finally:
            os.close(fd)

    def close(self):
        if self._closed is False:
            self._closed = True
            os.close(self._anchor[2])
            os.close(self._anchor[3])

    def __enter__(self):
        self.check()
        return self

    def __exit__(self, *unused):
        self.close()


def run(root, *, head, remote):
    _require_capture_platform()
    _local(root, head)
    _guard_remote(root, remote)
    require(type(EXPECTED_PROTOCOL_SHA256) is str
            and re.fullmatch(r"[0-9a-f]{64}", EXPECTED_PROTOCOL_SHA256), "prospective_continuation_protocol_pending")
    source = load_parent(root, head=head)
    frozen = freeze_protocol(source)
    require(hash_payload(frozen) == EXPECTED_PROTOCOL_SHA256, "prospective_continuation_protocol_changed")
    _local(root, head)
    code = _code_identity(root, head)
    began = _utc_now()
    target = root / PARENT / ("native-identity-continuation-" + _clock(began).strftime("%Y%m%dT%H%M%SZ"))
    _local(root, head)
    require(_git(root, "check-ignore", str(target)) == str(target), "continuation_output_not_ignored")
    directory = _prepare_capture_directory(target)
    with _OwnedOutput(directory, lambda: _local(root, head)) as owned:
        def publish(name, raw):
            owned.publish(name, raw)

        def claim(key, value):
            receipt = {**value, "schema": "si-native-identity-manual-continuation-budget-v1",
                       "run_id": directory.name, "remote_head": remote,
                       "source_inventory_sha256": SOURCE_INVENTORY_SHA256,
                       "failed_start_bytes_sha256": SOURCE_FILE_PINS["date-045-active-page-02.started.json"],
                       "credential_item": frozen["credential_item"], "unused_parent_slots_repurposable": False}
            owned.publish("budget-" + key + ".json", canonical_json(receipt).encode(), parent=True)

        def credential(provider):
            owned.check()
            require(provider == "massive", "exact_owner_named_Massive_item")
            key = read_named_keychain("massive")
            owned.check()
            return key

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        def request(spec, secret, maximum):
            owned.check()
            require(type(spec) is dict and set(spec) == {"method", "url", "authentication"}
                    and spec.get("method") == "GET" and spec.get("authentication") == "Bearer_header_not_recorded"
                    and not secret.echoed_in(spec["url"].encode()), "fixed_echo_free_request_descriptor")
            call = urllib.request.Request(spec["url"], method="GET", headers={
                "Accept": "application/json", "Authorization": "Bearer " + secret.for_authorization_header()})
            return _http(opener, call, maximum)

        # The first guard already read actual remote before the potentially
        # long replay. Capture rechecks start, each HTTP and final publication.
        return capture_continuation(source, expected_protocol_sha256=EXPECTED_PROTOCOL_SHA256,
            code_head=head, code_identity_sha256=code, claim=claim, publish=publish,
            get_secret=credential, request=request, local_guard=owned.check,
            remote_guard=lambda: _guard_remote(root, remote), now=_utc_now)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-remote", required=True)
    parser.add_argument("--preflight", action="store_true", help="Source/code-only digest; no claim, key or provider access")
    args = parser.parse_args(argv)
    try:
        action = preflight if args.preflight else run
        result = action(Path.cwd().resolve(), head=args.expected_head, remote=args.expected_remote)
    except (CaptureRefusal, identity.NativeDatedIdentityError, ShortInterestKeychainError,
            ValueError, TypeError, OSError, KeyError):
        print(json.dumps({"status": "identity_continuation_refused", "outcome_looks": 0,
            "qc_attempts": 0, "ready_for_empirical_backtest": False, "backtest_result_exists": False}, sort_keys=True))
        return 2
    # Private cursor/row/report contents are deliberately not printed.
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
