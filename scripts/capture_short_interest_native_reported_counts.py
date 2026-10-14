"""Ignored operational seam for a later sealed selected-anchor count capture.

No filesystem, Keychain, HTTP or QC implementation/default is supplied here.
Integration must bind the completed dated source and compact anchor producer,
register this exact code/protocol and wire the existing protected readers and
owned directory-FD publisher. A completed capture is still source-only.
"""
from __future__ import annotations

import json

import re

from urllib.parse import quote, urlencode

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_dated_class_reference as refs
import research.short_interest_etf.massive_class_denominator as lexical
import research.short_interest_etf.sharadar_securities_master as master
from scripts.continue_short_interest_native_identity import failure_metadata
from scripts.qualify_finra_short_interest import CaptureRefusal
from scripts.qualify_sharadar_companion import SharadarCaptureRefusal
from scripts.qualify_short_interest_action_supplement import _clock
from scripts.short_interest_keychain import KeychainSecret, ShortInterestKeychainError

EXPECTED_PROTOCOL_SHA256 = "PENDING"
import research.short_interest_etf.native_reported_anchor_plan as reported


class CountCaptureRefusal(ValueError):
    pass


def require(value, code):
    if not value:
        raise CountCaptureRefusal(code)


def freeze_count_protocol(compact, *, completed_source_receipt_sha256,
                          source_completed_at, maximum_total_bytes):
    require(type(compact) is reported.NativeReportedAnchorPlan, "exact_sealed_chronological_anchor_plan_required")
    plan = compact.query_plan
    require(type(plan) is refs.NativeClassQueryPlan, "exact_selected_source_plan_required")
    spec = plan.to_payload()
    require(spec["mode"] == "explicit_anchors" and spec["selected_query_ordinals"] is not None
            and spec["anchor_dates"] is None and type(spec["query_count"]) is int and spec["query_count"] > 0,
            "only_concrete_source_selected_anchors_no_full_population_or_cross_product")
    require(all(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value)
                for value in (compact.sha256, completed_source_receipt_sha256)), "registered_compact_source_pins")
    _clock(source_completed_at)
    require(type(maximum_total_bytes) is int and maximum_total_bytes >= lexical.MAXIMUM_RESPONSE_BYTES,
            "prospective_cumulative_byte_limit_required")
    return {"schema": "si-native-selected-anchor-count-capture-prototype-v1", "plan_sha256": plan.sha256,
            "plan": spec, "compact_plan_sha256": compact.sha256,
            "compact_anchor_policy_sha256": compact.header()["policy_sha256"],
            "completed_source_receipt_sha256": completed_source_receipt_sha256,
            "source_completed_at": source_completed_at, "maximum_requests": spec["query_count"],
            "maximum_response_bytes": lexical.MAXIMUM_RESPONSE_BYTES,
            "maximum_total_raw_bytes": maximum_total_bytes,
            "endpoint": "https://api.massive.com/v3/reference/tickers/{escaped_exact_source_ticker}",
            "query": "date=exact_source_selected_anchor_no_extra_fields",
            "authentication": "existing_owner_named_massive_Keychain_fixed_Bearer_header",
            "publication": "reuse_owned_directory_FDs_inode_owner0700_exclusive0600_no_follow_fsync",
            "claim": "source_compact_plan_and_query_plan_not_head_or_clock_no_restart_or_unused_slot_reuse",
            "failure": "404_status_only_negative_continue_auth_transport_media_stop_no_retry",
            "qualification": "chronology_specific_compact_registry_own_dated_class_no_future_retrorefusal_no_primary_or_issuer_transfer",
            "receipt": "body_unobserved_has_no_source_raw_digest_empty_placeholder_bound_separately",
            "automatic_retries": 0, "redirects": False, "proxies": False,
            "source_admitted": False, "point_in_time_data": False, "denominator_admitted": False,
            "ready_for_empirical_backtest": False, "outcome_looks": 0, "qc_attempts": 0,
            "backtest_result_exists": False}


def _descriptor(ticket):
    expected = {"method": "GET", "url": "https://api.massive.com/v3/reference/tickers/" + quote(ticket["ticker"], safe=""),
                "params": {"date": lexical._date(ticket["query_asof_date"])}, "authentication": "Bearer_header_not_recorded"}
    require(ticket["query_asof_date"] <= "2026-08-31" and canonical_json(ticket["request"]) == canonical_json(expected),
            "exact_source_ticket_route_date_and_fields")
    return expected, expected["url"] + "?" + urlencode(expected["params"])


def capture_count_plan(compact, tickers, *, protocol, expected_protocol_sha256, code_head, code_identity_sha256,
                       claim, publish, reload_received, get_secret, request, local_guard, remote_guard, now):
    """Injected capture + authenticated offline replay, not an empirical permit.

    reload_received(ordinal) must use protected owned files. It returns the
    originally published receipt bytes and body bytes/None; this seam never
    guesses a private path, fetches a lost page, resets a claim or retries.
    """
    local_guard()
    remote_guard()
    require(type(compact) is reported.NativeReportedAnchorPlan, "exact_sealed_chronological_anchor_plan_required")
    plan = compact.query_plan
    require(type(plan) is refs.NativeClassQueryPlan and type(tickers) is master.CapturedSharadarMasterArchive
            and tickers.table == "tickers", "exact_source_plan_and_original_master_required")
    require(all(pin["master_archive_sha256"] == hash_bytes(tickers.raw)
                for pin in compact.header()["identity_source_pins"]), "compact_identity_original_master_archive_binding")
    require(type(protocol) is dict, "prospective_source_protocol_required")
    frozen_json = canonical_json(protocol)
    frozen_sha = hash_bytes(frozen_json.encode())
    require(frozen_sha == expected_protocol_sha256, "source_count_protocol_pending_or_changed")
    require(freeze_count_protocol(compact,
            completed_source_receipt_sha256=protocol["completed_source_receipt_sha256"],
            source_completed_at=protocol["source_completed_at"], maximum_total_bytes=protocol["maximum_total_raw_bytes"]) == protocol,
            "source_count_protocol_binding")
    archive_snapshot = (tickers.raw, tickers.table, tickers.request_sha256)
    started_at = now()
    require(_clock(protocol["source_completed_at"]) <= _clock(started_at), "count_capture_after_completed_source")
    claim_id = hash_payload({"purpose": "one_source_selected_anchor_class_count_capture",
                             "compact_plan_sha256": protocol["compact_plan_sha256"], "plan_sha256": plan.sha256,
                             "completed_source_receipt_sha256": protocol["completed_source_receipt_sha256"]})
    local_guard()
    claim(claim_id, {"protocol_sha256": frozen_sha, "code_head": code_head, "started_at": started_at,
                    "maximum_attempts": protocol["maximum_requests"], "automatic_retries": 0,
                    "restart_or_resume": False, "unused_slots_repurposable": False})
    attempts, raw_bytes, previous, expected_receipts = 0, 0, _clock(started_at), []

    def check():
        local_guard()
        require(canonical_json(protocol) == frozen_json and plan.sha256 == protocol["plan_sha256"], "frozen_count_scope_changed")
        require(compact.sha256 == protocol["compact_plan_sha256"], "sealed_chronological_anchor_plan_changed")
        require(tickers.raw is archive_snapshot[0] and tickers.table == archive_snapshot[1]
                and tickers.request_sha256 == archive_snapshot[2], "original_master_changed")

    def save(name, value):
        check()
        publish(name, value if type(value) is bytes else canonical_json(value).encode())

    try:
        save("protocol.private.json", frozen_json.encode())
        save("started.json", {"schema": "si-source-anchor-count-start-v1", "protocol_sha256": frozen_sha,
             "code_head": code_head, "code_identity_sha256": code_identity_sha256,
             "started_at": started_at, "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False})
        check()
        secret = get_secret("massive")
        check()
        require(type(secret) is KeychainSecret, "exact_named_Keychain_secret_required")
        for ordinal, query in enumerate(plan.iter_queries(), 1):
            check()
            ticket = query.to_payload()
            require(ticket["query_ordinal"] == ordinal and ordinal == attempts + 1
                    and ordinal <= protocol["maximum_requests"] and ticket["plan_sha256"] == plan.sha256,
                    "exact_selected_query_cardinality_and_order")
            spec, url = _descriptor(ticket)
            require(not secret.echoed_in(url.encode()), "request_credential_echo_refused")
            require(hash_payload(spec) == ticket["request_sha256"], "exact_source_request_digest")
            require(protocol["maximum_total_raw_bytes"] - raw_bytes >= protocol["maximum_response_bytes"],
                    "count_cumulative_byte_reservation")
            began = now()
            require(previous <= _clock(began), "count_request_chronology")
            attempts += 1
            name = f"attempt-{ordinal:06d}"
            save(name + ".started.json", {"schema": "si-source-anchor-count-request-start-v1", "attempt": attempts,
                 "query_ordinal": ordinal, "request": spec, "request_sha256": ticket["request_sha256"],
                 "plan_sha256": plan.sha256, "protocol_sha256": frozen_sha, "started_at": began})
            status = None
            try:
                check()
                remote_guard()
                check()
                observed = True
                try:
                    raw, media, status = request(spec, secret, protocol["maximum_response_bytes"])
                except SharadarCaptureRefusal as error:
                    if type(error.code) is str and error.code == "http_not_200" and error.http_status == 404:
                        raw, media, status, observed = b"", "", 404, False
                    else:
                        raise
                require(type(raw) is bytes and len(raw) <= protocol["maximum_response_bytes"]
                        and type(media) is str and len(media) <= 4096, "count_response_shape_or_size")
                require(not secret.echoed_in(raw) and not secret.echoed_in(media.encode()), "response_credential_echo_refused")
                require(type(status) is int and (status == 200 or (status == 404 and observed is False)),
                        "count_HTTP_status_refused")
                require(not observed or media.split(";", 1)[0].strip().lower() == "application/json", "count_response_media_refused")
                received = now()
                require(_clock(began) <= _clock(received), "count_response_chronology")
                if observed:
                    save(name + ".raw", raw)
                    raw_bytes += len(raw)
                receipt = {"schema": "si-source-anchor-count-response-v1", "query_ordinal": ordinal,
                    "request_sha256": ticket["request_sha256"], "received_at": received,
                    "http_status": status, "content_type": media, "body_observed": observed,
                    "raw_path": name + ".raw" if observed else None,
                    "raw_sha256": hash_bytes(raw) if observed else None, "raw_bytes": len(raw) if observed else None,
                    "placeholder_raw_sha256": None if observed else hash_bytes(b"")}
                encoded_receipt = canonical_json(receipt).encode()
                save(name + ".received.json", encoded_receipt)
                # Validate the exact raw/media/query/time binding immediately;
                # the semantic parser later retains all negative source facts.
                refs.capture_native_dated_class_response(query, raw=raw, raw_sha256=hash_bytes(raw),
                    request_sha256=ticket["request_sha256"], received_at=received, http_status=status,
                    content_type=media, body_observed=observed)
                expected_receipts.append(hash_bytes(encoded_receipt))
                previous = _clock(received)
            except (CountCaptureRefusal, refs.NativeDatedClassError, lexical.MassiveClassDenominatorError,
                    CaptureRefusal, ShortInterestKeychainError, ValueError, TypeError, OSError, KeyError) as error:
                failed_at = now()
                require(_clock(began) <= _clock(failed_at), "count_failure_chronology")
                category, observed_status = failure_metadata(error, status)
                save(name + ".refused.json", {"schema": "si-source-anchor-count-request-refused-v1",
                    "attempt": attempts, "failure_category": category, "http_status": observed_status,
                    "refused_at": failed_at, "automatic_retries": 0})
                raise
        require(attempts == protocol["maximum_requests"] == len(expected_receipts), "complete_selected_query_inventory_required")
        retrieved_at = now()
        require(previous <= _clock(retrieved_at), "count_report_chronology")

        def replay():
            for ordinal, query in enumerate(plan.iter_queries(), 1):
                check()
                receipt_raw, observed_raw = reload_received(ordinal)
                check()
                require(type(receipt_raw) is bytes and hash_bytes(receipt_raw) == expected_receipts[ordinal - 1],
                        "owned_original_received_receipt_bytes_changed")
                receipt = json.loads(receipt_raw)
                ticket = query.to_payload()
                require(receipt["query_ordinal"] == ordinal and receipt["request_sha256"] == ticket["request_sha256"],
                        "owned_received_query_binding")
                if receipt["body_observed"]:
                    require(type(observed_raw) is bytes and hash_bytes(observed_raw) == receipt["raw_sha256"]
                            and len(observed_raw) == receipt["raw_bytes"], "owned_source_body_bytes_changed")
                    raw = observed_raw
                else:
                    require(observed_raw is None and receipt["http_status"] == 404 and receipt["raw_path"] is None
                            and receipt["raw_sha256"] is None and receipt["raw_bytes"] is None
                            and receipt["placeholder_raw_sha256"] == hash_bytes(b""), "unobserved_404_placeholder_only")
                    raw = b""
                yield refs.capture_native_dated_class_response(query, raw=raw, raw_sha256=hash_bytes(raw),
                    request_sha256=ticket["request_sha256"], received_at=receipt["received_at"],
                    http_status=receipt["http_status"], content_type=receipt["content_type"], body_observed=receipt["body_observed"])
        qualified = reported.qualify_native_reported_counts(compact, replay())
        header = qualified.to_payload()
        require(header["captured_anchor_count"] == header["planned_anchor_count"] == attempts
                and header["anchor_plan_sha256"] == compact.sha256, "complete_private_qualification_required")
        part_pins = []
        for ordinal, part in enumerate(qualified.iter_parts()):
            name = f"qualification-{ordinal:06d}.private"
            save(name, part)
            part_pins.append({"path": name, "bytes": len(part), "sha256": hash_bytes(part)})
        save("inventory.private.json", {"schema": "si-source-anchor-count-inventory-v1", "protocol_sha256": frozen_sha,
             "plan_sha256": plan.sha256, "received_receipt_sha256": expected_receipts,
             "qualification_sha256": qualified.sha256, "qualification_parts": part_pins,
             "retrieved_at": retrieved_at, "http_attempts": attempts, "raw_bytes": raw_bytes,
             "source_admitted": False, "denominator_admitted": False, "outcome_looks": 0, "qc_attempts": 0})
        finished = now()
        require(_clock(retrieved_at) <= _clock(finished), "count_completion_chronology")
        remote_guard()
        check()
        result = {"schema": "si-source-anchor-count-complete-v1", "status": "private_source_count_capture_complete",
                  "protocol_sha256": frozen_sha, "plan_sha256": plan.sha256, "code_head": code_head,
                  "completed_at": finished, "http_attempts": attempts, "private_qualification_sha256": qualified.sha256,
                  "source_admitted": False, "denominator_admitted": False, "point_in_time_data": False,
                  "ready_for_empirical_backtest": False, "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}
        save("completed.json", result)
        return result
    except (CountCaptureRefusal, refs.NativeDatedClassError, lexical.MassiveClassDenominatorError,
            CaptureRefusal, ShortInterestKeychainError, ValueError, TypeError, OSError, KeyError) as error:
        refused = now()
        require(_clock(started_at) <= _clock(refused), "count_enclosing_refusal_chronology")
        category, status = failure_metadata(error)
        save("refused.json", {"schema": "si-source-anchor-count-refused-v1", "failure_category": category,
             "http_status": status, "http_attempts": attempts, "refused_at": refused,
             "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False})
        raise
