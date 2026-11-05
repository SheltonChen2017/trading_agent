"""Qualify retained ACTIONS/DESCRIPTIONS privately with zero new requests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from data.hashing import hash_bytes, hash_payload
import research.short_interest_etf.sharadar_securities_master as master
import research.short_interest_etf.sharadar_terminal_consideration as consideration
import scripts.finalize_short_interest_master_offline as finalizer
from scripts.qualify_finra_short_interest import (
    CapturePlatformRefusal, CaptureRefusal, _git, _prepare_capture_directory,
    _publish, _publish_json, _require_capture_platform,
)
from scripts.qualify_sharadar_companion import _guard, _utc_now
from scripts.qualify_short_interest_action_supplement import _clock

OUTPUT = Path("artifacts/short_interest/terminal_consideration/terminal-actions-source-20261012T055800Z")
MAXIMUM_REPORT_BYTES = 128 * 1024 * 1024
SOURCE = Path("artifacts/short_interest/sharadar_securities_master/sharadar-master-20261012T055800Z")
SOURCE_HEAD = "a5ac4c22499e13f04776a8fa145fd3dba72bc383"
SOURCE_INVENTORY_SHA256 = "af57bd5bcbfc435051946be51e6671e7de8f77b0c7739bddc23f89d0e8f48726"
SOURCE_BUDGET_SHA256 = "76170777b03b8a1e553777494ffa564c817975f5f4f0b15fffea0651066dcdbd"
_CODE_FILES = (
    "data/hashing.py", "data/exchange_calendar.py",
    "research/short_interest_etf/contracts.py",
    "research/short_interest_etf/sharadar_securities_master.py",
    "research/short_interest_etf/sharadar_terminal_consideration.py",
    "scripts/capture_short_interest_securities_master.py",
    "scripts/finalize_short_interest_master_offline.py",
    "scripts/qualify_finra_short_interest.py", "scripts/qualify_sharadar_companion.py",
    "scripts/qualify_short_interest_action_supplement.py",
    "scripts/qualify_short_interest_terminal_actions_offline.py",
)


class TerminalActionsOfflineRefusal(CaptureRefusal):
    """Fixed safe codes; no private data conclusions in CLI output."""


def _require(condition, reason):
    if not condition:
        raise TerminalActionsOfflineRefusal(reason)


def build_protocol():
    return {"schema": "si-terminal-actions-offline-protocol-v1",
            "consideration_protocol_sha256": consideration.PROTOCOL_SHA256,
            "consideration_protocol": consideration.consideration_protocol(),
            "source": str(SOURCE), "source_head": SOURCE_HEAD,
            "source_inventory_sha256": SOURCE_INVENTORY_SHA256,
            "consumed_budget_sha256": SOURCE_BUDGET_SHA256,
            "output": str(OUTPUT), "maximum_report_bytes": MAXIMUM_REPORT_BYTES,
            "reconstruction": "fixed_twelve_consumed_requests_original_raw_archives_no_master_report_materialization",
            "publication_scope": "private_only_no_source_rows_or_fitness_publication",
            "provider_requests": 0, "credential_reads": 0, "outcome_looks": 0,
            "qc_attempts": 0, "backtest_result_exists": False}


def _sources(root):
    _require_capture_platform()
    _require(finalizer.SOURCE == SOURCE and finalizer.SOURCE_HEAD == SOURCE_HEAD
             and finalizer.SOURCE_INVENTORY_SHA256 == SOURCE_INVENTORY_SHA256
             and finalizer.BUDGET_SHA256 == SOURCE_BUDGET_SHA256, "fixed_original_source_pins_changed")
    archives, anchor = finalizer._reload(root)
    _require(type(archives) is tuple and len(archives) == 3
             and all(type(value) is master.CapturedSharadarMasterArchive for value in archives)
             and tuple(value.table for value in archives) == master.TABLES,
             "original_master_archive_inventory")
    return archives[1], archives[2], anchor


def _code_identity(root, head):
    return hash_payload({"git_commit": head, "files": [
        {"path": name, "sha256": hash_bytes((root / name).read_bytes())} for name in _CODE_FILES]})


def _build(root, *, head, remote):
    _require_capture_platform()
    _guard(root, head, remote)
    protocol = build_protocol()
    actions, descriptions, anchor = _sources(root)
    started = _utc_now()
    _require(_clock(started) >= _clock(anchor), "offline_source_chronology")
    target, owned = root / OUTPUT, False
    try:
        _guard(root, head, remote)
        _require(_git(root, "check-ignore", str(target)) == str(target), "output_not_ignored")
        try:
            directory = _prepare_capture_directory(target)
        except FileExistsError:
            raise TerminalActionsOfflineRefusal("terminal_actions_output_already_exists") from None
        owned = True
        _guard(root, head, remote)
        _publish_json(directory, "protocol.json", protocol)
        code_identity = _code_identity(root, head)
        _guard(root, head, remote)
        _publish_json(directory, "started.json", {"schema": "si-terminal-actions-offline-start-v1",
            "code_head": head, "code_identity_sha256": code_identity,
            "protocol_sha256": hash_payload(protocol), "started_at": started,
            "source_reconstruction_anchor": anchor,
            "provider_requests": 0, "credential_reads": 0, "outcome_looks": 0, "qc_attempts": 0})
        report = consideration.qualify_sharadar_terminal_consideration(actions, descriptions, retrieved_at=started)
        raw = report.to_bytes()
        _require(type(raw) is bytes and len(raw) <= MAXIMUM_REPORT_BYTES, "private_consideration_report_size")
        _guard(root, head, remote)
        _publish(directory, "consideration.private.json", raw)
        completed = _utc_now()
        _require(_clock(completed) >= _clock(started), "offline_completion_chronology")
        result = {"schema": "si-terminal-actions-offline-complete-v1", "status": "terminal_actions_offline_complete",
                  "code_head": head, "code_identity_sha256": code_identity,
                  "protocol_sha256": hash_payload(protocol),
                  "consideration_protocol_sha256": consideration.PROTOCOL_SHA256,
                  "private_report_sha256": report.sha256, "private_report_bytes_sha256": hash_bytes(raw),
                  "completed_at": completed, "provider_requests": 0, "credential_reads": 0,
                  "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}
        _guard(root, head, remote)
        _publish_json(directory, "completed.json", result)
        return result
    except (CaptureRefusal, ValueError, TypeError, OSError, KeyError, UnicodeError):
        if owned:
            _guard(root, head, remote)
            _publish_json(directory, "refused.json", {"schema": "si-terminal-actions-offline-refusal-v1",
                "status": "terminal_actions_offline_refused", "refused_at": _utc_now(),
                "provider_requests": 0, "credential_reads": 0, "outcome_looks": 0,
                "qc_attempts": 0, "backtest_result_exists": False})
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-remote", required=True)
    args = parser.parse_args(argv)
    try:
        _require_capture_platform()
        result = _build(Path.cwd().resolve(), head=args.expected_head, remote=args.expected_remote)
    except (CaptureRefusal, ValueError, TypeError, OSError, KeyError, UnicodeError) as exc:
        result = {"status": "terminal_actions_offline_refused", "provider_requests": 0,
                  "credential_reads": 0, "outcome_looks": 0, "qc_attempts": 0,
                  "backtest_result_exists": False}
        if type(exc) is CapturePlatformRefusal:
            result.update(code=exc.code, ready_for_empirical_backtest=False)
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
