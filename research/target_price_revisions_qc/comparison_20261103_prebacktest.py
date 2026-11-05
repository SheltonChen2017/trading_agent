"""Claimed local prebacktest capsule; no QC, Safari, provider or run effects.

Both frozen and INLINE recovery source epochs are regenerated, never activated.
The fixed REMX exports stay immutable diagnostic evidence. No market observation
is copied into either five-arm source tree, and no input admission is minted.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import stat
import time

from . import comparison_20261103_preflight as preflight
from . import remx_prepare_20261103 as io

ROOT = io.ROOT
BRANCH = io.BRANCH
RECORD = io.RECORD
MODULE = "research/target_price_revisions_qc/comparison_20261103_prebacktest.py"
HOLD_MODULE = "research/target_price_revisions_qc/comparison_20261103_project_actions.py"
REQUIRED_SOURCES = frozenset(preflight.RECOVERY_REQUIRED_SOURCES |
    preflight.bundle.projects.REQUIRED_SOURCES | io.REQUIRED_SOURCES |
    {MODULE, preflight.MODULE, HOLD_MODULE})
HELPER_PINS = {
    preflight.MODULE: "e16d50cd8bb3fa0716b9e1994552f07b2dcf02554493c6bbf1b41661de847082",
    io.MODULE: "f92e8f9a623d24c4158e00f676e36c3a816f79b72e143f8bdc82251fe2d4768d",
}
REGISTRY = ("artifacts/target_price_qc_recovery_20261028/"
            "TPR-CMP28-R107-PROJECT-BINDINGS-001.json")
REMX_ROOT = "artifacts/target_price_remx_20261103/REMX-20261103-EXPORT-001"
REMX_INPUTS = {
    "manifest.json": (2296, "c4e319cf9003a8cfeddfaa688988e62ce1ddf45bcbeea1046e7fa5afddd25932"),
    "receipt.json": (2008, "437a13cda9f1dd406feb95e63654eeca7dd1d3e8210f5d5a1793a3b1eeedfc36"),
    "source_original.csv": (181222, "b8c54990689501ddc55183e6bb28c8eb7cd47a8817c04153480a6ef613b1de5e"),
    "candidate_post_inception.csv": (166663, "454a35c07dec8ddbf236f868968cc457eaac20317be69ec8d9dab1eae5b2f731"),
    "quarantine_pre_inception.csv": (11849, "75a8cc311cac1c4e84bb426078dcdf9f25fc5b6c84f7cb83fc10b936d2262861"),
    "quarantine_fractional_volume.csv": (990, "9a750e174545179f65b97401c1ca4d95f820f0c1623c4fb3f4e350abce708783"),
}
REMX_CREATION_HEAD = "c06657742a5fe7ef2355894116fd2250e2ba4f89"
REMX_CREATION_OWNER = "feaed725a68dabae6283578d21e55dddd70bb78ace7a6cedfc40b2b5665dfeb0"
DESTINATION = "artifacts/target_price_prebacktest_20261103"
OWNER_INSTRUCTION = ("leave the 20 REMX rows quarantined and continue building locally up to the "
    "backtesting step. keep QC and Safari untouched, skip Claude review, and push only once when done.")
OWNER_SHA256 = hashlib.sha256(OWNER_INSTRUCTION.encode()).hexdigest()
MAX_LIFETIME_SECONDS = 300
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_HISTORY_BYTES = 8 * 1024 * 1024
EXPECTED_ARM_FILES = {arm: 11 if arm == "cap_off" else 15 for arm in preflight.ARMS}
FALSE_REMX_FLAGS = ("source_origin_authenticated", "permanent_sid_bound", "point_in_time_data",
    "source_rights_verified", "native_qc_mark", "source_inputs_admitted",
    "full_coverage_verified", "backtesting_ready", "financial_acceptance",
    "canonical_admission", "trading_authority", "fractional_volumes_rounded_or_truncated",
    "gap_fill_performed")


class PreparationRefusal(ValueError):
    """Fixed body only; no private observation or exception text is echoed."""


def _fail():
    raise PreparationRefusal("local prebacktest preparation refused") from None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _wire(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def _pairs(rows):
    value = {}
    for key, cell in rows:
        if key in value:
            _fail()
        value[key] = cell
    return value


def _parse(raw):
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_float=lambda _: _fail(),
            parse_constant=lambda _: _fail())
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _fail()


def _context():
    if ROOT != io.ROOT or Path.cwd() != ROOT:
        _fail()
    return io._context()


def _sources(head):
    result = {}
    for name in sorted(REQUIRED_SOURCES):
        raw = io._regular(ROOT / name, preflight.MAX_SOURCE_BYTES)
        if io._git("show", head + ":" + name) != raw:
            _fail()
        if name in HELPER_PINS and _sha(raw) != HELPER_PINS[name]:
            _fail()
        result[name] = raw
    return result


def _private_inputs():
    return {REGISTRY: (preflight.REGISTRY_BYTES, preflight.REGISTRY_SHA256),
        **{REMX_ROOT + "/" + name: pin for name, pin in REMX_INPUTS.items()}}


def _private_read(path, pin):
    # Validate and read the SAME opened inode. A second path open would drop
    # the approved private-mode/owner custody check between stat and read.
    parent, leaf = io._parent(ROOT / path)
    fd = None
    try:
        try:
            named = io.os.stat(leaf, dir_fd=parent, follow_symlinks=False)
            if (not stat.S_ISREG(named.st_mode) or named.st_uid != io.os.getuid()
                    or stat.S_IMODE(named.st_mode) != 0o600 or named.st_size != pin[0]):
                _fail()
            fd = io.os.open(leaf, io.os.O_RDONLY | io.os.O_NOFOLLOW | io.os.O_NONBLOCK,
                dir_fd=parent)
        finally:
            io.os.close(parent)
    except BaseException:
        if fd is not None:
            io.os.close(fd)
        raise
    try:
        before = io.os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != io.os.getuid()
                or stat.S_IMODE(before.st_mode) != 0o600 or before.st_size != pin[0]
                or io._snapshot(named) != io._snapshot(before)):
            _fail()
        raw = io.os.read(fd, pin[0])
        after = io.os.fstat(fd)
        if (not stat.S_ISREG(after.st_mode) or after.st_uid != io.os.getuid()
                or stat.S_IMODE(after.st_mode) != 0o600 or after.st_size != pin[0]
                or io._snapshot(before) != io._snapshot(after)
                or len(raw) != pin[0] or _sha(raw) != pin[1]):
            _fail()
        return raw
    finally:
        io.os.close(fd)


def _dates(raw, count):
    rows = raw.splitlines()
    if len(rows) != count:
        _fail()
    try:
        days = [line.split(b",", 1)[0][:10].decode("ascii") for line in rows]
    except UnicodeError:
        _fail()
    if (days != sorted(days) or len(set(days)) != len(days)
            or any(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day) is None for day in days)):
        _fail()
    return days


def _remx_report(inputs):
    files = {name: inputs[REMX_ROOT + "/" + name] for name in REMX_INPUTS}
    manifest, receipt = _parse(files["manifest.json"]), _parse(files["receipt.json"])
    counts = {"post_inception_unchanged": 3136, "post_inception_integral_volume_normalized": 860,
        "pre_inception_identity_quarantine": 323, "fractional_volume_quarantine": 20}
    if (manifest["source_rows"] != 4339 or manifest["candidate_rows"] != 3996
            or manifest["disposition_counts"] != counts
            or manifest["source_sha256"] != REMX_INPUTS["source_original.csv"][1]
            or manifest["identity_boundary"] != "2010-10-27"
            or any(manifest[key] is not False for key in FALSE_REMX_FLAGS)
            or any(manifest[key] is not True for key in
                ("full_source_preserved", "all_rows_accounted_for", "candidate_strict_parser_valid"))
            or receipt["status"] != "prepared_partial_local_candidate"
            or receipt["git_head"] != REMX_CREATION_HEAD
            or receipt["owner_instruction_sha256"] != REMX_CREATION_OWNER
            or receipt["source_original_modified"] is not False):
        _fail()
    for name in ("source_original.csv", "candidate_post_inception.csv",
            "quarantine_pre_inception.csv", "quarantine_fractional_volume.csv"):
        expected = {"bytes": REMX_INPUTS[name][0], "sha256": REMX_INPUTS[name][1]}
        if manifest["outputs"][name] != expected or receipt["outputs"][name] != {"name": name, **expected}:
            _fail()
    original = _dates(files["source_original.csv"], 4339)
    candidate = _dates(files["candidate_post_inception.csv"], 3996)
    identity = _dates(files["quarantine_pre_inception.csv"], 323)
    fractional = _dates(files["quarantine_fractional_volume.csv"], 20)
    post = {day for day in original if day >= "2010-10-27"}
    if (identity != [day for day in original if day < "2010-10-27"]
            or set(candidate) | set(fractional) != post or set(candidate) & set(fractional)
            or sorted(post - set(candidate)) != fractional
            or manifest["missing_post_inception_source_dates"] != fractional
            or (fractional[0], fractional[-1]) != ("2026-02-23", "2026-03-20")):
        _fail()
    study = lambda day: "2021-01-04" <= day <= "2026-10-09"
    if sum(map(study, original)) != 1449 or sum(map(study, candidate)) != 1429:
        _fail()
    return {"use": "INDEPENDENT_DIAGNOSTIC_ONLY_NOT_FROZEN_FINANCIAL_INPUT",
        "existing_files_unchanged": True, "source_rows": 4339, "candidate_rows": 3996,
        "pre_inception_identity_quarantine_rows": 323, "fractional_volume_quarantine_rows": 20,
        "study_source_dates": 1449, "study_candidate_dates": 1429, "study_gap_dates": fractional,
        "historical_creation_head": receipt["git_head"],
        "historical_creation_owner_sha256": receipt["owner_instruction_sha256"],
        "source_descriptors": {name: {"bytes": size, "sha256": digest}
            for name, (size, digest) in REMX_INPUTS.items()},
        "raw_rows_copied_into_source_exports": False,
        "source_inputs_admitted": False, "financial_acceptance": False,
        "full_coverage_verified": False, "native_qc_mark": False,
        "quarantine_is_not_a_financial_sample_exclusion": True,
        "diagnostic_gap_blocks_frozen_source_assembly": False}


def _generation(packets, manifest_raw, expected_epoch):
    manifest = _parse(manifest_raw)
    if (manifest["source_epoch"] != expected_epoch or manifest["mode"] != "offline-preparation"
            or manifest["owner_instruction_sha256"] != OWNER_SHA256
            or manifest["source_inputs_admitted"] is not False
            or manifest["backtesting_ready"] is not False
            or manifest["native_origin_authenticated"] is not False
            or manifest["accepted_performance"] is not None
            or any(manifest[key] != 0 for key in ("qc_requests", "qc_compiles",
                "backtests_launched", "new_attempts", "new_observed_financial_looks"))
            or type(packets) is not dict or set(packets) != set(preflight.ARMS)
            or set(manifest["arms"]) != set(preflight.ARMS)):
        _fail()
    inventory = {}
    for arm in preflight.ARMS:
        files = packets[arm]
        row = manifest["arms"][arm]
        if (type(files) is not dict or len(files) != EXPECTED_ARM_FILES[arm]
                or row["native_compilation"] != "NOT_RUN" or row["backtest"] != "NOT_RUN"
                or row["financial_metrics"] is not None or row["native_accounting_accepted"] is not False
                or row["financial_function_bodies_unchanged"] is not True):
            _fail()
        inventory[arm] = {}
        for name, raw in sorted(files.items()):
            if (type(name) is not str or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*\.py", name) is None
                    or type(raw) is not bytes or not 0 < len(raw) <= 60000):
                _fail()
            compile(ast.parse(raw, filename=name), name, "exec")
            inventory[arm][name] = {"bytes": len(raw), "sha256": _sha(raw)}
        if inventory[arm] != row["source_inventory"]:
            _fail()
    if sum(map(len, inventory.values())) != 71 or manifest["local_syntax_units_checked"] != 71:
        _fail()
    return manifest, inventory


def prepare_workspace(operation_id):
    """Build a fixed local capsule; no automatic retry or native effect exists."""
    if (type(operation_id) is not str or
            re.fullmatch(r"TPR-PREBACKTEST-20261103-[A-Z0-9-]{1,40}", operation_id) is None):
        _fail()
    head = _context()
    sources = _sources(head)
    history = io._regular(ROOT / RECORD, MAX_HISTORY_BYTES)
    if not history:
        _fail()
    history_sha = _sha(history)
    io._directory(ROOT / "artifacts")
    io._directory(ROOT / DESTINATION)
    operation = ROOT / DESTINATION / operation_id
    io._directory(operation, exclusive=True)
    now = datetime.now(timezone.utc)
    expires, monotonic_limit = now + timedelta(seconds=MAX_LIFETIME_SECONDS), time.monotonic() + MAX_LIFETIME_SECONDS
    private_inputs = _private_inputs()
    claim = {"schema": "tpr-prebacktest-local-claim-v1", "operation_id": operation_id,
        "worktree": str(ROOT), "branch": BRANCH, "git_head": head,
        "created_utc": now.isoformat(), "expires_utc": expires.isoformat(),
        "latest_owner_instruction_sha256": OWNER_SHA256,
        "owner_authority": "LOCAL_BUILD_UP_TO_BACKTEST_ONLY_NO_QC_OR_SAFARI",
        "source_hashes": {name: _sha(raw) for name, raw in sorted(sources.items())},
        "prior_history_record_sha256": history_sha,
        "private_inputs": {name: {"bytes": size, "sha256": digest}
            for name, (size, digest) in sorted(private_inputs.items())},
        "private_reads_max": len(private_inputs), "private_bytes_max": sum(x[0] for x in private_inputs.values()),
        "reserved_attempt": None, "financial_outcome_look": None,
        "local_preparation_look": operation_id, "signal_packet_open_authorized": False,
        "max_source_and_readiness_export_bytes": MAX_OUTPUT_BYTES,
        "max_audit_json_bytes_each": 65536, "max_audit_json_bytes_total": 131072,
        "source_epochs": [preflight.FROZEN_EPOCH, preflight.RECOVERY_EPOCH],
        "source_tree_count": 2, "source_files_max": 142,
        "qc_requests": 0, "safari_requests": 0, "provider_requests": 0, "backtests": 0}
    claim_raw = _wire(claim)
    if len(claim_raw) > 65536:
        _fail()
    claimed = io._retain(operation / "claim.json", claim_raw)
    io._note("Fresh local prebacktest claim " + operation_id + "; HEAD" + head +
        "; claimSHA" + claimed["sha256"] +
        " fsynced BEFORE the seven fixed private registry/REMX reads. "
        "REMX20 stay quarantined; QC0/Safari0/provider0/nativeCompiles0/backtests0.")

    def live():
        if (_context() != head or datetime.now(timezone.utc) >= expires
                or time.monotonic() >= monotonic_limit):
            _fail()
        for name, raw in sources.items():
            if _sha(io._regular(ROOT / name, preflight.MAX_SOURCE_BYTES)) != _sha(raw):
                _fail()

    status, exports, readiness_descriptor, failure = "refused", {}, None, None
    remx_verified = False
    written = 0
    def retain(path, raw):
        nonlocal written
        live()
        if written + len(raw) > MAX_OUTPUT_BYTES:
            _fail()
        descriptor = io._retain(path, raw)
        written += len(raw)
        return descriptor

    try:
        inputs = {}
        for path, pin in sorted(private_inputs.items()):
            live()
            inputs[path] = _private_read(path, pin)
        live()
        remx = _remx_report(inputs)
        remx_verified = True
        requests = {arm: {"operation_id": "TPR-CMP28-" +
            ("OFF-" if arm == "cap_off" else "") + "OFFLINE-" + operation_id + "-" + arm.upper().replace("_", "-"),
            "attempt": 1, "prior_attempts_looks_sha256": history_sha} for arm in preflight.ARMS}
        manifests = {}
        for label, builder, required, epoch in (
                ("frozen", preflight.prepare_offline, preflight.REQUIRED_SOURCES, preflight.FROZEN_EPOCH),
                ("recovery_candidate", preflight.prepare_recovery_candidate,
                    preflight.RECOVERY_REQUIRED_SOURCES, preflight.RECOVERY_EPOCH)):
            live()
            packets, raw = builder(public_sources={name: sources[name] for name in required},
                project_bindings_raw=inputs[REGISTRY], requests=requests,
                git_head=head, owner_instruction_sha256=OWNER_SHA256)
            live()
            manifest, inventory = _generation(packets, raw, epoch)
            live()
            manifests[label] = manifest
            target = operation / label
            io._directory(target, exclusive=True)
            exports[label] = {}
            for arm in preflight.ARMS:
                live()
                io._directory(target / arm, exclusive=True)
                exports[label][arm] = {}
                for name, content in sorted(packets[arm].items()):
                    exports[label][arm][name] = retain(target / arm / name, content)
            exports[label]["manifest"] = retain(target / "manifest.json", raw)
        live()
        arms = {arm: {"project_id": manifests["frozen"]["arms"][arm]["project_id"],
            "frozen_source_files": EXPECTED_ARM_FILES[arm],
            "recovery_source_files": EXPECTED_ARM_FILES[arm],
            "local_syntax_checked": True, "cloud_source_custody_verified": False,
            "native_upload": "NOT_RUN", "native_compilation": "NOT_RUN", "backtest": "NOT_RUN",
            "financial_metrics": None, "native_accounting_accepted": False} for arm in preflight.ARMS}
        readiness = {"schema": "tpr-prebacktest-local-readiness-v1",
            "operation_id": operation_id, "git_head": head, "latest_owner_instruction_sha256": OWNER_SHA256,
            "claim_sha256": claimed["sha256"], "source_hashes": claim["source_hashes"],
            "prior_history_record_sha256": history_sha, "local_preparation_complete": True,
            "local_syntax_units_checked": 142, "source_builder_epochs_separate": True,
            "source_epoch_manifests": {label: exports[label]["manifest"] for label in manifests},
            "historical_registry_creation_owner_sha256": manifests["frozen"]["registry_creation_owner_instruction_sha256"],
            "historical_registry_creation_head": manifests["frozen"]["registry_creation_git_head"],
            "arm_order": list(preflight.ARMS), "arms": arms, "remx": remx,
            "signal_packet_body_opened": False, "attempt_previews_are_reservations": False,
            "fresh_native_attempt_assignment_required": True, "history_counts_consolidated": False,
            "history_attempts_looks_reset": False, "automatic_retry": False,
            "qc_requests": 0, "safari_requests": 0, "provider_requests": 0,
            "native_compiles": 0, "backtests": 0, "new_financial_looks": 0,
            "backtesting_ready": False, "source_inputs_admitted": False,
            "native_origin_authenticated": False, "financial_acceptance": False,
            "point_in_time_data": False, "source_rights_admitted": False,
            "canonical_admission": False, "trading_authority": False,
            "blocking_reasons": list(preflight.BLOCKERS) + ["owner_holds_safari_access_until_further_notice"],
            "next_step": "STOP_BEFORE_QC_SAFARI_NATIVE_COMPILE_OR_BACKTEST",
            "future_prerequisites": [
                "Fresh explicit owner notice covering the intended QC/Safari access; no automatic resume.",
                "Refresh committed HEAD/source/owner/project custody and claims; assign actual fresh attempts/looks.",
                "Verify current cloud source, recovery epoch/capacity, exact native RAW/SID/input facts.",
                "Only after prerequisites, use genuine source-bound producer; OFF then remaining arms serially.",
                "Accept only independent full native orders/fills/fees/cash/actions/NAV/exposure/clock accounting."]}
        readiness_descriptor = retain(operation / "readiness.json", _wire(readiness))
        live()
        status = "prepared_prebacktest_local"
    except BaseException as error:
        failure = error
        status = "cancelled" if isinstance(error, KeyboardInterrupt) else "refused"
    receipt = {"schema": "tpr-prebacktest-local-receipt-v1", "operation_id": operation_id,
        "status": status, "git_head": head, "latest_owner_instruction_sha256": OWNER_SHA256,
        "claim_sha256": claimed["sha256"], "exports": exports,
        "readiness": readiness_descriptor, "export_bytes": written,
        "local_preparation_complete": status == "prepared_prebacktest_local",
        "original_remx_files_written": False, "quarantines_retained": remx_verified,
        "quarantine_hashes_verified": remx_verified,
        "qc_requests": 0, "safari_requests": 0, "provider_requests": 0,
        "native_compiles": 0, "backtests": 0, "new_attempts": 0, "new_financial_looks": 0,
        "backtesting_ready": False, "source_inputs_admitted": False,
        "financial_acceptance": False, "actual_native_results": None, "automatic_retry": False}
    receipt_raw = _wire(receipt)
    if len(receipt_raw) > 65536:
        _fail()
    descriptor = io._retain(operation / "receipt.json", receipt_raw)
    io._note("Local prebacktest capsule " + operation_id + " status" + status +
        "; receiptSHA" + descriptor["sha256"] +
        "; REMX20 retained, local preparation is not native/input/financial acceptance. "
        "QC0/Safari0/provider0/nativeCompiles0/backtests0.")
    if isinstance(failure, (KeyboardInterrupt, SystemExit)):
        raise failure
    return {"status": status, "operation_id": operation_id, "receipt": descriptor,
        "local_preparation_complete": receipt["local_preparation_complete"],
        "qc_requests": 0, "safari_requests": 0, "backtests": 0, "backtesting_ready": False}


class _BodyFreeParser(argparse.ArgumentParser):
    def error(self, message):
        _fail()


def main(argv=None):
    parser = _BodyFreeParser(description="Local prebacktest preparation; QC and Safari remain untouched.")
    parser.add_argument("operation_id")
    try:
        result = prepare_workspace(parser.parse_args(argv).operation_id)
    except KeyboardInterrupt:
        raise
    except Exception:
        result = {"status": "refused", "local_preparation_complete": False,
            "qc_requests": 0, "safari_requests": 0, "backtests": 0, "backtesting_ready": False}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "prepared_prebacktest_local" else 1


if __name__ == "__main__":
    raise SystemExit(main())
