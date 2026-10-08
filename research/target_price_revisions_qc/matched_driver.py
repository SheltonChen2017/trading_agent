"""Committed explicit-action driver for the matched exploratory QC study.

Run from the pinned lane: python -m research.target_price_revisions_qc.matched_driver
Actions do not retry silently. No import reads a source, credential or result.
A source fix requires a new bounded operation manifest, never new candidate IDs
or reset attempt counts. All evidence remains in the private matched-study root.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess

from . import matched_bundle as bundle
from . import operations_v2 as ops

PACKAGE = ops.LANE / "research/target_price_revisions_qc"
REPOSITORY_SOURCES = (
    "research/target_price_revisions_qc/operations_v2.py",
    "research/target_price_revisions_qc/matched_driver.py",
    "research/target_price_revisions_qc/matched_bundle.py",
    "research/target_price_revisions_qc/matched_algorithm.py",
    "research/target_price_revisions_qc/matched_algorithm_v2.py",
    "research/target_price_revisions_qc/matched_audit.py",
    "research/target_price_revisions_qc/matched_audit_v2.py",
    "research/target_price_revisions_qc/matched_freeze.json",
    "research/target_price_revisions_qc/cloud_algorithm_v2.py",
    "research/target_price_revisions_qc/packet.py",
    "research/target_price_revisions_qc/six_universe_freeze.json",
    "research/target_price_revisions_development/raw_candidate.py",
    "research/target_price_revisions_development/raw_revision.py",
)


def preflight():
    if Path.cwd() != ops.LANE or Path.cwd().resolve() != ops.LANE:
        raise ops.Refusal("driver must run in exact physical lane")
    def git(*args):
        return subprocess.run(["git", *args], cwd=ops.LANE, capture_output=True,
                              text=True, check=True).stdout.strip()
    if git("rev-parse", "--show-toplevel") != str(ops.LANE) or git("branch", "--show-current") != ops.BRANCH:
        raise ops.Refusal("driver Git lane mismatch")
    return {"head": git("rev-parse", "HEAD"), "status": git("status", "--short")}


def render_sources():
    preflight()
    # This is conservative pre-rendering, NOT an entitlement assertion. The
    # controller independently checks each actual newly created project quota.
    return bundle.build_bundle((PACKAGE / "matched_algorithm_v2.py").read_bytes(),
        (PACKAGE / "cloud_algorithm_v2.py").read_bytes(),
        (PACKAGE / "matched_freeze.json").read_bytes(), max_file_size=60000)


def prepare(operation_id):
    context = preflight()
    rendered = render_sources()
    now = datetime.now(timezone.utc)
    source_hashes = {path: ops.digest((ops.LANE / path).read_bytes()) for path in REPOSITORY_SOURCES}
    manifest = {"schema": "tpr-qc-operations-manifest-v2", "study_id": bundle.STUDY,
        "operation_id": operation_id, "created_utc": now.isoformat(),
        "expires_utc": (now + timedelta(hours=48)).isoformat(),
        "baseline_git_head": context["head"], "freeze_sha256": bundle.FREEZE_SHA256,
        "repository_source_hashes": source_hashes,
        "input_hashes": {"signal-packet.json": bundle.PACKET_SHA256,
                        "original-core.py": bundle.CORE_SHA256,
                        "matched-freeze.json": bundle.FREEZE_SHA256},
        "packet_path": ops.PACKET_PATH, "packet_sha256": bundle.PACKET_SHA256,
        "candidates": [{"candidate_id": row["candidate_id"],
                        "project_name": row["candidate_id"] + "-private",
                        "config_sha256": row["config_sha256"],
                        "source_hashes": row["source_hashes"]} for row in rendered["cases"]],
        "max_requests": 1000, "max_response_bytes": 16777216,
        "request_timeout_seconds": 30, "max_attempts_per_candidate": 3,
        "log_prefix": "MATCHED_"}
    manifest_hash = ops.digest(ops.canonical(manifest))
    controller = ops.Operations(manifest, manifest_sha256=manifest_hash)
    controller.prepare_access()
    controller.exclusive("manifest." + operation_id + ".json", manifest)
    controller.exclusive("source-bundle." + operation_id + ".json", rendered)
    controller.prepare_packet()
    bundle.validate_packet_bytes(controller.read_private("signal-packet." + operation_id + ".json"))
    return {"operation_id": operation_id, "manifest_sha256": manifest_hash,
            "bundle_sha256": ops.digest(ops.canonical(rendered)),
            "freeze_sha256": bundle.FREEZE_SHA256, "baseline": context["head"],
            "dirty_source_binding": bool(context["status"]), "fixture": False}


def controller_for(operation_id):
    preflight()
    root = ops.PRIVATE_PARENT / bundle.STUDY
    raw = ops._read(root, "manifest." + operation_id + ".json", 16777216)
    manifest = ops._json(raw)
    controller = ops.Operations(manifest, manifest_sha256=ops.digest(raw))
    controller._access()
    return controller


def collect_and_audit(controller, candidate, attempt):
    from .matched_audit_v2 import audit_result
    collected = controller.collect_terminal(candidate, attempt)
    completion = collected["completion"]
    prefix = collected["receipt_prefix"]
    if completion["collection_errors"]:
        return completion
    evidence = audit_result(collected["result_response"], collected["logs_response"],
        collected["order_pages"], collected["source_receipt"], collected["candidate_config"])
    evidence["attempt"] = attempt
    evidence["collection_round"] = collected["collection_round"]
    native = collected["result_response"]["backtest"]
    evidence["qc_headline_drawdown"] = native.get("statistics", {}).get("Drawdown")
    evidence["native_closed_trades"] = native.get("totalPerformance", {}).get("tradeStatistics", {}).get("totalNumberOfTrades")
    evidence["slippage_per_side"] = collected["candidate_config"]["slippage"]
    evidence["drawdown_sampling_reconciled"] = False
    controller.exclusive(prefix + ".interpreted.json", evidence)
    return evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "authenticate", "create", "packet-upload",
        "source-upload", "reserve", "compile", "compile-status", "launch", "status", "collect"))
    parser.add_argument("--operation", default="TPR-MATCHED-ACCESS-20261008-001")
    parser.add_argument("--candidate", choices=sorted(ops.CANDIDATES))
    parser.add_argument("--attempt", type=int)
    args = parser.parse_args(argv)
    preflight()
    if args.action == "prepare":
        result = prepare(args.operation)
    else:
        c = controller_for(args.operation)
        if args.action == "authenticate":
            value = c.authenticate()
            result = {"authenticated": value.get("success") is True}
        else:
            if args.candidate is None:
                parser.error("--candidate required")
            if args.action == "create":
                result = c.create_project(args.candidate)
            elif args.action == "packet-upload":
                result = c.upload_packet(args.candidate)
            elif args.action == "source-upload":
                rendered = c._value("source-bundle." + args.operation + ".json")
                case = next(row for row in rendered["cases"] if row["candidate_id"] == args.candidate)
                result = c.upload_sources(args.candidate, case["files"])
            elif args.action == "reserve":
                value = c.reserve_attempt(args.candidate)
                result = {"candidate_id": args.candidate, "attempt": value["attempt"], "status": value["status"]}
            else:
                if args.attempt is None:
                    parser.error("--attempt required")
                if args.action == "compile":
                    result = c.compile_candidate(args.candidate, args.attempt)
                elif args.action == "compile-status":
                    result = c.poll_compile(args.candidate, args.attempt)
                elif args.action == "launch":
                    result = c.launch_backtest(args.candidate, args.attempt)
                elif args.action == "status":
                    result = c.poll_backtest(args.candidate, args.attempt)
                else:
                    result = collect_and_audit(c, args.candidate, args.attempt)
    # Only IDs, hashes and own aggregate portfolio evidence. Never print file
    # sources, credentials, membership identifiers, private packet or order rows.
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
