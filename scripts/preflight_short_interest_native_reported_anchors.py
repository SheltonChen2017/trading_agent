"""Offline source-only anchor plan: no provider/key/QC or artifact publication.

Root must freeze the eventual tracked code and prospective request protocol
before using this plan to launch any count capture. This preflight consumes
the historical evidence once and returns no raw or reconstructible rows.
"""
from data.hashing import hash_bytes, hash_payload
import scripts.continue_short_interest_native_identity as capture
import scripts.load_short_interest_native_class_matrix as matrix_reader
import scripts.finalize_short_interest_master_offline as finalizer
import scripts.build_short_interest_native_master_offline as native_builder
import research.short_interest_etf.native_reported_anchor_plan as anchors
import scripts.stream_short_interest_native_identity_continuation as stream
from scripts.read_short_interest_native_identity_continuation import load_batched_for_current_runtime


def preflight(root, *, runtime_head, actual_remote):
    """Return exact sealed plan + safe metadata; never issue a count request."""
    capture._require_capture_platform()
    local = lambda: capture._local(root, runtime_head)
    local()
    with load_batched_for_current_runtime(root, runtime_head=runtime_head, actual_remote=actual_remote) as (replayed, dates):
        matrix = matrix_reader.load_matrix(root, head=runtime_head, remote=actual_remote)  # Exactly once.
        local()
        guarded_root = capture._GuardedSourcePath(root, local)
        originals, original_anchor = finalizer._reload(guarded_root)
        local()
        native_builder._source_index(guarded_root, original_anchor)
        local()
        by_table = {source.table: source for source in originals}
        stream.require(set(by_table) == {"tickers", "actions", "descriptions"}
                and len(originals) == 3, "exact_original_archives_only")
        plan = anchors.build_native_reported_anchor_plan(matrix, dates, by_table["actions"], by_table["descriptions"])
        local()
        header, evidence = plan.header(), replayed.payload()
        stream.require(hash_bytes(by_table["tickers"].raw)
                == evidence["parent_source"]["original_native_index"]["archive_sha256"],
                "original_TICKERS_matches_replayed_identity_index")
        entries = evidence["old_reports"] + evidence["new_reports"]
        observed = header["identity_source_pins"]
        stream.require([pin["query_date"] for pin in observed] == evidence["parent_source"]["dates"]
                and len(observed) == len(entries)
                and all(pin["query_date"] == entry["query_date"]
                    and pin["source_sha256"] == entry["report_bytes_sha256"]
                    for pin, entry in zip(observed, entries)), "all_112_exact_source_report_pins_consumed")
        query_spec = plan.query_plan.to_payload()
        stream.require(query_spec["mode"] == "explicit_anchors"
                and type(query_spec["selected_query_ordinals"]) is list
                and header["exact_request_budget"] == len(query_spec["selected_query_ordinals"]),
                "plan_request_budget_consistency")
        # Source table pins are independent of empirical eligibility/fitness.
        source_pins = {"original_archive_sha256": {table: hash_bytes(source.raw) for table, source in by_table.items()},
                "matrix_sha256": matrix.sha256, "parent_inventory_sha256": evidence["parent_source"]["source_inventory_sha256"],
                "child_inventory_sha256": evidence["child_inventory_sha256"],
                "child_budget_bytes_sha256": evidence["child_budget_bytes_sha256"],
                "report_inventory_sha256": hash_payload(entries)}
        summary = {"schema": "si-native-full-identity-anchor-preflight-v1", "status": "source_only_plan_preflight",
                "plan_sha256": plan.sha256, "request_budget": header["exact_request_budget"],
                "source_pins": source_pins, "capture_code_and_request_protocol": "pending_prospective_freeze",
                "source_admitted": False, "ready_for_empirical_backtest": False,
                "provider_requests": 0, "credential_reads": 0, "outcome_looks": 0, "qc_attempts": 0,
                "backtest_result_exists": False}
        local()
        return plan, summary
