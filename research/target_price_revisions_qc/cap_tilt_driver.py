"""Explicit-action driver for two new owner-authorized cap/tilt QC candidates.

Run from the pinned lane: python -m research.target_price_revisions_qc.cap_tilt_driver
New economics are not a fourth matched retry; the fa78 starting snapshot is
unreviewed and these development runs have separate owner authorization.
No import reads source, credentials, inputs or outcomes. Fresh operation IDs,
committed source bytes, bounded manifests and immutable receipts are required.
Candidate attempt limits never reset after fixes, retries or new operations.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess

from . import cap_tilt_bundle as bundle
from . import cap_tilt_operations as ops

PACKAGE = ops.LANE / "research/target_price_revisions_qc"
REPOSITORY_SOURCES = (
    "research/target_price_revisions_qc/cap_tilt_operations.py",
    "research/target_price_revisions_qc/cap_tilt_driver.py",
    "research/target_price_revisions_qc/cap_tilt_bundle.py",
    "research/target_price_revisions_qc/cap_tilt_algorithm.py",
    "research/target_price_revisions_qc/cap_tilt_audit.py",
    "research/target_price_revisions_qc/cap_tilt_freeze.json",
    "research/target_price_revisions_qc/cap_tilt.py",
    "research/target_price_revisions_qc/cap_observer.py",
    "research/target_price_revisions_qc/cloud_algorithm_v2.py",
    "research/target_price_revisions_qc/packet.py",
    "research/target_price_revisions_qc/six_universe_freeze.json",
    "research/target_price_revisions_qc/matched_audit.py",
    "research/target_price_revisions_qc/matched_bundle.py",
    "research/target_price_revisions_development/raw_candidate.py",
    "research/target_price_revisions_development/raw_revision.py",
    "research/target_price_revisions_development/raw_backtest.py",
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
    # Pre-rendering is not an entitlement assertion. Actual fresh project
    # quota, ownership and exact uploaded bytes are independently checked.
    return bundle.build_bundle((PACKAGE / "cap_tilt_algorithm.py").read_bytes(),
        (PACKAGE / "cloud_algorithm_v2.py").read_bytes(),
        (PACKAGE / "cap_tilt_freeze.json").read_bytes(),
        cap_tilt_source=(PACKAGE / "cap_tilt.py").read_bytes(),
        cap_observer_source=(PACKAGE / "cap_observer.py").read_bytes(), max_file_size=60000)


def _operation_name(operation_id):
    if not ops._name(operation_id, 80):
        raise ops.Refusal("explicit bounded operation identity required")


def _committed_source_hashes(head):
    """Refuse uncommitted source inputs before preparing any empirical receipt."""
    if type(head) is not str or len(head) != 40 or not 2 <= len(REPOSITORY_SOURCES) <= 32:
        raise ops.Refusal("bounded committed source inventory required")
    result = {}
    for relative in REPOSITORY_SOURCES:
        path = ops.LANE / relative
        if (path.resolve() != path or path.is_symlink() or not path.is_file()
                or path.stat().st_size > 2 * 1024 * 1024 or relative in result):
            raise ops.Refusal("declared source path refused")
        raw = path.read_bytes()
        try:
            committed = subprocess.run(["git", "show", head + ":" + relative],
                cwd=ops.LANE, capture_output=True, check=True).stdout
        except subprocess.CalledProcessError:
            raise ops.Refusal("every declared source must be committed before prepare") from None
        if raw != committed:
            raise ops.Refusal("declared source differs from committed HEAD")
        result[relative] = ops.digest(raw)
    return result


def prepare(operation_id, *, prepared_packet_source=None):
    _operation_name(operation_id)
    context = preflight()
    source_hashes = _committed_source_hashes(context["head"])
    rendered = render_sources()
    now = datetime.now(timezone.utc)
    manifest = {"schema": "tpr-qc-cap-tilt-operations-manifest-v1", "study_id": bundle.STUDY,
        "operation_id": operation_id, "created_utc": now.isoformat(),
        "expires_utc": (now + timedelta(hours=48)).isoformat(),
        "baseline_git_head": context["head"], "freeze_sha256": bundle.FREEZE_SHA256,
        "repository_source_hashes": source_hashes,
        "input_hashes": {"signal-packet.json": bundle.PACKET_SHA256,
                        "original-core.py": bundle.CORE_SHA256,
                        "cap-tilt-freeze.json": bundle.FREEZE_SHA256},
        "packet_path": ops.PACKET_PATH, "packet_sha256": bundle.PACKET_SHA256,
        "prepared_packet_source": prepared_packet_source,
        "candidates": [{"candidate_id": row["candidate_id"],
                        "project_name": row["candidate_id"] + "-private",
                        "config_sha256": row["config_sha256"],
                        "source_hashes": row["source_hashes"]} for row in rendered["cases"]],
        "max_requests": 1000, "max_response_bytes": 16777216,
        "request_timeout_seconds": 30, "max_attempts_per_candidate": 3,
        "log_prefix": "MATCHED_"}
    manifest_hash = ops.digest(ops.canonical(manifest))
    controller = ops.Operations(manifest, manifest_sha256=manifest_hash)
    # Access, manifest and complete source bundle precede the one freshly
    # scoped exact derived-packet read. No D0/provider/outcome capture is read.
    controller.prepare_access()
    controller.exclusive("manifest." + operation_id + ".json", manifest)
    controller.exclusive("source-bundle." + operation_id + ".json", rendered)
    controller.prepare_packet()
    bundle.validate_packet_bytes(controller.read_private("signal-packet." + operation_id + ".json"))
    return {"operation_id": operation_id, "manifest_sha256": manifest_hash,
            "bundle_sha256": ops.digest(ops.canonical(rendered)),
            "freeze_sha256": bundle.FREEZE_SHA256, "baseline": context["head"],
            "dirty_source_binding": bool(context["status"]), "source_bytes_committed": True,
            "prepared_packet_source": prepared_packet_source, "fixture": False}


def controller_for(operation_id):
    _operation_name(operation_id)
    preflight()
    root = ops.PRIVATE_PARENT / bundle.STUDY
    raw = ops._read(root, "manifest." + operation_id + ".json", 16777216)
    manifest = ops._json(raw)
    controller = ops.Operations(manifest, manifest_sha256=ops.digest(raw))
    controller._access()
    return controller


def collect_and_audit(controller, candidate, attempt):
    from .cap_tilt_audit import audit_result
    collected = controller.collect_terminal(candidate, attempt)
    completion = collected["completion"]
    prefix = collected["receipt_prefix"]
    if completion["collection_errors"]:
        return completion
    try:
        evidence = audit_result(collected["result_response"], collected["logs_response"],
            collected["order_pages"], collected["source_receipt"], collected["candidate_config"])
    except Exception:
        controller.exclusive(prefix + ".audit-error.json", {"schema": "tpr-qc-cap-tilt-audit-error-v1",
            "candidate_id": candidate, "attempt": attempt, "status": "pure_audit_refused",
            "strategy_accepted": False, "canonical_admission": False, "automatic_retry": False})
        return {**completion, "classification": "diagnostic_or_incomplete",
                "pure_audit_errors": ["pure_audit_refused"], "strategy_accepted": False,
                "canonical_admission": False}
    evidence["attempt"] = attempt
    evidence["collection_round"] = collected["collection_round"]
    native = collected["result_response"]["backtest"]
    stats = native.get("statistics")
    performance = native.get("totalPerformance")
    trade_stats = performance.get("tradeStatistics") if type(performance) is dict else None
    evidence["qc_headline_drawdown"] = stats.get("Drawdown") if type(stats) is dict else None
    evidence["native_closed_trades"] = trade_stats.get("totalNumberOfTrades") if type(trade_stats) is dict else None
    evidence["slippage_per_side"] = collected["candidate_config"]["slippage"]
    evidence["drawdown_sampling_reconciled"] = False
    controller.exclusive(prefix + ".interpreted.json", evidence)
    return evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "authenticate", "create", "packet-upload",
        "source-upload", "reserve", "compile", "compile-status", "launch", "status", "collect"))
    parser.add_argument("--operation", required=True)
    parser.add_argument("--candidate", choices=sorted(ops.CANDIDATES))
    parser.add_argument("--attempt", type=int)
    parser.add_argument("--prepared-packet-source", help="Prepare only: explicit basename of this study's first captured packet")
    args = parser.parse_args(argv)
    preflight()
    _operation_name(args.operation)
    if args.prepared_packet_source is not None and args.action != "prepare":
        parser.error("--prepared-packet-source is valid only with prepare")
    if args.action == "prepare":
        result = prepare(args.operation, prepared_packet_source=args.prepared_packet_source)
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
    # Only identities, hashes and aggregate own-portfolio evidence are printed.
    # Never print source, credentials, member IDs, private packets or order rows.
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
