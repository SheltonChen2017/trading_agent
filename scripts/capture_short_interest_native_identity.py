"""One frozen full dated-identity capture; no price/count/outcome arithmetic."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import urllib.parse
import urllib.request

from data.hashing import hash_bytes, hash_payload
import research.short_interest_etf.native_dated_identity as contract
import scripts.load_short_interest_native_class_matrix as matrix_reader
import scripts.finalize_short_interest_master_offline as finalizer
import scripts.build_short_interest_native_master_offline as native_builder
import scripts.capture_short_interest_native_population as credential_reader
from scripts.qualify_finra_short_interest import (
    CaptureRefusal, _NoRedirect, _git, _prepare_capture_directory, _publish,
    _publish_json, _require_capture_platform,
)
from scripts.qualify_sharadar_companion import SharadarCaptureRefusal, _guard, _http, _utc_now
from scripts.qualify_short_interest_action_supplement import _clock
from scripts.short_interest_keychain import KeychainSecret, ShortInterestKeychainError

PARENT = Path("artifacts/short_interest/native_dated_identity")
PROTOCOL_SHA256 = "2ae2b0e1baeb0f04448bd23aa5f838b89da19d269af5ad7a0e6af4b59cb233ae"
SETTLEMENT_DATES_SHA256 = "d6e722d910da972acfd5b91ae6147086e36cb99a522b634657d37f6a2781a7c0"
CODE_FILES = (
    "data/hashing.py", "ml/immutable_io.py", "research/short_interest_etf/contracts.py",
    "research/short_interest_etf/native_population_class_matrix.py",
    "research/short_interest_etf/native_dated_identity.py",
    "research/short_interest_etf/sharadar_securities_master.py",
    "research/short_interest_etf/sharadar_master_segments.py",
    "scripts/qualify_finra_short_interest.py", "scripts/qualify_sharadar_companion.py",
    "scripts/qualify_short_interest_action_supplement.py", "scripts/short_interest_keychain.py",
    "scripts/capture_short_interest_securities_master.py",
    "scripts/finalize_short_interest_master_offline.py", "scripts/build_short_interest_native_master_offline.py",
    "scripts/capture_short_interest_native_population.py", "scripts/load_short_interest_native_class_matrix.py",
    "scripts/capture_short_interest_native_identity.py",
)


class NativeIdentityCaptureError(CaptureRefusal):
    pass


def _require(value, reason):
    if not value:
        raise NativeIdentityCaptureError(reason)


def _failure_metadata(error, status):
    """Retain fixed transport diagnostics, never arbitrary exception text."""
    category = "source_or_guard_refused"
    observed = status
    if isinstance(error, SharadarCaptureRefusal):
        if type(error.code) is str and error.code in {
                "network_failure", "http_not_200", "response_size_limit", "content_type"}:
            category = error.code
        if type(observed) is not int:
            observed = error.http_status
    if type(observed) is not int or not 100 <= observed <= 599:
        observed = None
    return category, observed


def source_pins():
    return {"matrix_path": str(matrix_reader.SOURCE), "matrix_sha256": matrix_reader.MATRIX_SHA256,
            "matrix_files": dict(matrix_reader.FILE_PINS), "matrix_completed_at": matrix_reader.SOURCE_COMPLETED,
            "master_path": str(finalizer.SOURCE), "master_inventory_sha256": finalizer.SOURCE_INVENTORY_SHA256,
            "master_budget_bytes_sha256": finalizer.BUDGET_SHA256,
            "master_offline_index_sha256": native_builder.SOURCE_INDEX_SHA256}


def protocol():
    return {"schema": "si-native-dated-identity-capture-protocol-v1", "policy": contract.identity_policy(),
            "policy_sha256": hash_payload(contract.identity_policy()), "source_pins": source_pins(),
            "settlement_dates_sha256": SETTLEMENT_DATES_SHA256,
            "capture_parent": str(PARENT), "authentication": "existing_named_MASSIVE_API_KEY_fixed_Bearer_header",
            "credential_reader": "verify_registered_zero_HTTP_Keychain_refusal_no_new_secret_search",
            "storage": "exclusive_protected_ignored_original_pages_and_one_compact_qualification_per_date",
            "budget": "one_global_protocol_and_source_claim_before_credential_no_restart_or_unused_slot_reuse",
            "chronology": "enclosing_start_request_start_response_report_completion_non_decreasing",
            "code_files": list(CODE_FILES), "proxies": False, "redirects": False,
            "automatic_retries": 0, "source_only": True, "outcome_looks": 0,
            "qc_attempts": 0, "backtest_result_exists": False}


def _validated_protocol():
    value = protocol()
    _require(hash_payload(value) == PROTOCOL_SHA256
             and hash_payload(contract.identity_policy()) == contract.POLICY_SHA256,
             "prospective_identity_protocol_pending_or_changed")
    return value


def _source(root, *, head, remote):
    _require_capture_platform()
    _guard(root, head, remote)
    matrix = matrix_reader.load_matrix(root, head=head, remote=remote)
    header = matrix.header()
    dates = header["settlements"]
    _require(type(dates) is list and len(dates) == contract.EXPECTED_DATES
             and dates == sorted(set(dates)) and matrix.sha256 == matrix_reader.MATRIX_SHA256,
             "exact_frozen_settlement_inventory")
    _require(hash_payload(dates) == SETTLEMENT_DATES_SHA256, "prospectively_frozen_settlement_dates")
    _require(hash_bytes(matrix.parts()[0]) == matrix_reader.FILE_PINS["header.private.json"],
             "source_matrix_header_bytes")
    _guard(root, head, remote)
    captures, anchor = finalizer._reload(root)
    _guard(root, head, remote)
    native_builder._source_index(root, anchor)
    _guard(root, head, remote)
    index = contract.build_composite_native_index(captures[0])
    _guard(root, head, remote)
    return tuple(dates), index


def capture_dates(root, directory, opener, secret, dates, index, *, head, remote, started_at):
    _require_capture_platform()
    frozen = _validated_protocol()
    _require(type(secret) is KeychainSecret and type(index) is contract.CompositeNativeIndex
             and type(dates) is tuple and len(dates) == contract.EXPECTED_DATES
             and dates == tuple(sorted(set(dates))), "exact_capture_source_and_credential_types")
    _require(hash_payload(list(dates)) == SETTLEMENT_DATES_SHA256, "prospectively_frozen_settlement_dates")
    for at in dates:
        contract.request_descriptor(at, True)
    previous = _clock(started_at)
    _require(previous >= _clock(matrix_reader.SOURCE_COMPLETED), "capture_after_source_completion")
    attempts, total_bytes, total_rows, manifest = 0, 0, 0, []

    def publish(name, value, raw=False):
        _guard(root, head, remote)
        (_publish if raw else _publish_json)(directory, name, value)

    for date_number, at in enumerate(dates, 1):
        pages = []
        for active in (True, False):
            url = contract.ENDPOINT + "?" + urllib.parse.urlencode(contract.request_descriptor(at, active)["params"])
            seen = set()
            for ordinal in range(1, contract.MAXIMUM_PAGES_PER_PANEL + 1):
                _require(hash_payload(protocol()) == hash_payload(frozen) == PROTOCOL_SHA256,
                         "prospective_identity_protocol_changed")
                _require(url not in seen, "identity_pagination_cycle")
                seen.add(url)
                _require(attempts < contract.MAXIMUM_REQUESTS, "identity_whole_round_request_budget")
                _require(contract.MAXIMUM_TOTAL_BYTES - total_bytes >= contract.MAXIMUM_RESPONSE_BYTES
                         and contract.MAXIMUM_ROWS - total_rows >= contract.MAXIMUM_PAGE_ROWS,
                         "identity_cumulative_storage_or_row_budget")
                attempts += 1
                prefix = f"date-{date_number:03d}-{'active' if active else 'inactive'}-page-{ordinal:02d}"
                descriptor = {"method": "GET", "url": url, "authentication": "Bearer_header_not_recorded"}
                request_sha = hash_payload(descriptor)
                began = _utc_now()
                _require(previous <= _clock(began), "identity_request_chronology")
                publish(prefix + ".started.json", {"schema": "si-native-identity-page-start-v1",
                        "code_head": head, "protocol_sha256": PROTOCOL_SHA256, "query_date": at,
                        "active_panel": active, "ordinal": ordinal, "attempt": attempts,
                        "request": descriptor, "request_sha256": request_sha, "started_at": began})
                status = None
                try:
                    _guard(root, head, remote)
                    request = urllib.request.Request(url, method="GET", headers={
                        "Accept": "application/json", "Authorization": "Bearer " + secret.for_authorization_header()})
                    raw, media, status = _http(opener, request, contract.MAXIMUM_RESPONSE_BYTES)
                    _require(type(raw) is bytes and len(raw) <= contract.MAXIMUM_RESPONSE_BYTES
                             and type(media) is str and len(media) <= 4096, "identity_response_shape_or_size")
                    _require(not secret.echoed_in(raw) and not secret.echoed_in(media.encode()), "identity_credential_echo_refused")
                    received = _utc_now()
                    _require(_clock(began) <= _clock(received), "identity_response_chronology")
                    publish(prefix + ".raw", raw, raw=True)
                    receipt = {"schema": "si-native-identity-page-received-v1", "query_date": at,
                               "active_panel": active, "ordinal": ordinal, "request_sha256": request_sha,
                               "http_status": status, "content_type": media, "raw_path": prefix + ".raw",
                               "raw_sha256": hash_bytes(raw), "raw_bytes": len(raw), "received_at": received}
                    publish(prefix + ".received.json", receipt)
                    total_bytes += len(raw)
                    _require(total_bytes <= contract.MAXIMUM_TOTAL_BYTES, "identity_cumulative_byte_budget_exhausted")
                    page = contract.CapturedDatedIdentityPage(at, active, ordinal, url, raw, began, received, status, media)
                    payload = contract.page_payload(raw)
                    total_rows += len(payload["results"])
                    _require(total_rows <= contract.MAXIMUM_ROWS, "identity_cumulative_row_budget_exhausted")
                    following = payload.get("next_url")
                    if following is not None:
                        following = contract.next_url(following, at, active)
                    pages.append(page)
                    previous = _clock(received)
                    if following is None:
                        break
                    _require(ordinal < contract.MAXIMUM_PAGES_PER_PANEL, "identity_panel_page_budget_exhausted")
                    url = following
                except (CaptureRefusal, contract.NativeDatedIdentityError, ShortInterestKeychainError,
                        ValueError, TypeError, OSError, KeyError) as error:
                    failed = _utc_now()
                    _require(_clock(began) <= _clock(failed), "identity_failure_chronology")
                    category, failure_status = _failure_metadata(error, status)
                    publish(prefix + ".refused.json", {"schema": "si-native-identity-page-refused-v2",
                            "query_date": at, "active_panel": active, "ordinal": ordinal,
                            "attempt": attempts, "http_status": failure_status,
                            "failure_category": category,
                            "refused_at": failed, "code": "identity_page_refused_no_retry"})
                    raise
        checked = _utc_now()
        _require(previous <= _clock(checked), "identity_date_qualification_chronology")
        result = contract.qualify_dated_identity(tuple(pages), index, query_date=at,
                   started_at=started_at, retrieved_at=checked)
        raw = result.to_bytes()
        name = f"date-{date_number:03d}.qualified.private.json"
        publish(name, raw, raw=True)
        manifest.append({"query_date": at, "report_path": name, "report_bytes_sha256": hash_bytes(raw),
                         "report_bytes": len(raw), "page_count": len(pages), "retrieved_at": checked})
        previous = _clock(checked)
        del pages, result, raw
    _require(hash_payload(protocol()) == PROTOCOL_SHA256, "prospective_identity_protocol_changed")
    finished = _utc_now()
    _require(previous <= _clock(finished), "identity_completion_chronology")
    inventory = {"schema": "si-native-dated-identity-inventory-v1", "code_head": head,
                 "protocol_sha256": PROTOCOL_SHA256, "source_pins": source_pins(),
                 "started_at": started_at, "completed_at": finished, "dates": manifest,
                 "http_attempts": attempts, "raw_bytes": total_bytes, "decoded_rows": total_rows,
                 "complete_advertised_panel_chains": True, "source_only": True,
                 "source_admitted": False, "denominator_admitted": False,
                 "point_in_time_data": False, "outcome_looks": 0, "qc_attempts": 0,
                 "ready_for_empirical_backtest": False, "backtest_result_exists": False}
    digest = hash_payload(inventory)
    inventory["inventory_sha256"] = digest
    publish("inventory.private.json", inventory)
    done = _utc_now()
    _require(_clock(finished) <= _clock(done), "identity_final_receipt_chronology")
    completion = {"schema": "si-native-dated-identity-completion-v1", "status": "dated_identity_capture_complete",
                  "code_head": head, "protocol_sha256": PROTOCOL_SHA256,
                  "inventory_sha256": digest, "completed_at": done, "http_attempts": attempts,
                  "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}
    publish("completed.json", completion)
    return completion


def run(root, *, head, remote):
    _require_capture_platform()
    _guard(root, head, remote)
    frozen = _validated_protocol()
    dates, index = _source(root, head=head, remote=remote)
    began = _utc_now()
    _require(_clock(began) >= _clock(matrix_reader.SOURCE_COMPLETED), "identity_enclosing_source_chronology")
    target = root / PARENT / ("native-identity-" + _clock(began).strftime("%Y%m%dT%H%M%SZ"))
    _guard(root, head, remote)
    _require(_git(root, "check-ignore", str(target)) == str(target), "identity_output_not_ignored")
    directory = _prepare_capture_directory(target)

    def publish(where, name, value):
        _guard(root, head, remote)
        _publish_json(where, name, value)

    try:
        publish(directory.parent, "budget-" + PROTOCOL_SHA256 + ".json", {
            "schema": "si-native-dated-identity-global-budget-v1", "code_head": head, "remote_head": remote,
            "protocol_sha256": PROTOCOL_SHA256, "source_pins": source_pins(), "started_at": began,
            "maximum_attempts": contract.MAXIMUM_REQUESTS, "run_id": directory.name,
            "restart_or_resume": False, "unused_slots_repurposable": False})
        publish(directory, "protocol.json", frozen)
        files = []
        for name in CODE_FILES:
            _guard(root, head, remote)
            files.append({"path": name, "sha256": hash_bytes((root / name).read_bytes())})
        identity = hash_payload({"git_commit": head, "files": files})
        publish(directory, "started.json", {"schema": "si-native-dated-identity-start-v1", "code_head": head,
                 "remote_head": remote, "protocol_sha256": PROTOCOL_SHA256,
                 "code_identity_sha256": identity, "started_at": began, "source_pins": source_pins(),
                 "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False})
        _guard(root, head, remote)
        secret = credential_reader._credential(root, head=head, remote=remote)
        _guard(root, head, remote)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        return capture_dates(root, directory, opener, secret, dates, index,
                             head=head, remote=remote, started_at=began)
    except (CaptureRefusal, contract.NativeDatedIdentityError, ShortInterestKeychainError,
            ValueError, TypeError, OSError, KeyError):
        failed = _utc_now()
        _require(_clock(began) <= _clock(failed), "identity_enclosing_failure_chronology")
        publish(directory, "refused.json", {"schema": "si-native-dated-identity-refusal-v1",
                "status": "dated_identity_capture_refused", "refused_at": failed,
                "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False})
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-remote", required=True)
    args = parser.parse_args(argv)
    try:
        result = run(Path.cwd().resolve(), head=args.expected_head, remote=args.expected_remote)
    except (CaptureRefusal, contract.NativeDatedIdentityError, ShortInterestKeychainError,
            ValueError, TypeError, OSError, KeyError):
        print(json.dumps({"status": "dated_identity_capture_refused", "outcome_looks": 0,
                          "qc_attempts": 0, "backtest_result_exists": False}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
