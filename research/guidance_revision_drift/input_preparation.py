"""Named local structural preparation; no data fetching or simulation dispatch.

The report exposes hashes/counts/refusals, never retained raw payloads or full
licensed rows. References and supplied calendars are not verified approvals,
rights, PIT evidence or proof of complete history. No positive launch path.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

from data.hashing import hash_bytes
from research.guidance_revision_drift.contracts import (
    Candidate, CandidateError, _read_regular_file, load_candidate,
)
from research.guidance_revision_drift.guidance_inputs import (
    GuidanceDocument, GuidanceLedger, GuidanceReceipt,
)
from research.guidance_revision_drift.historical_market import HistoricalMarketBatch
from research.guidance_revision_drift.input_contracts import (
    InputError, canonical_bytes, decode_object, digest, keys, utc,
)

MAX_FILES = 16
MAX_FILE_BYTES = 1_048_576
MAX_TOTAL_BYTES = 4_194_304
_ROOT_KEYS = {"schema", "candidate_sha256", "data_class", "owner_scope_reference",
              "source_rights_reference", "calendar_sha256", "files", "guidance_receipts",
              "stock_market_file", "benchmark_market_file", "decision_at", "submitted_at", "callback_at"}
_RECEIPT_KEYS = {"raw_file", "document_file", "received_at", "validated_at"}


def _name(value: object) -> str:
    # Basenames only: no redirecting parent-directory or URL interpretation.
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", value) is None:
        raise InputError("explicit bounded local basename required")
    return value


def _manifest(raw: bytes, expected: str, candidate: Candidate) -> dict:
    if type(candidate) is not Candidate:
        raise InputError("exact pinned preparation candidate required")
    checked = Candidate(candidate.canonical_bytes)
    digest(expected)
    if type(raw) is not bytes or hash_bytes(raw) != expected:
        raise InputError("retained input manifest hash mismatch")
    body = keys(decode_object(raw), _ROOT_KEYS)
    if (body["schema"] != "gdr.local-input-manifest.v1"
            or body["candidate_sha256"] != checked.sha256
            or body["data_class"] not in ("invented_fixture", "historical_reconstruction")):
        raise InputError("input manifest schema or scope mismatch")
    for field in ("owner_scope_reference", "source_rights_reference"):
        if body[field] is not None:
            digest(body[field])
        elif body["data_class"] != "invented_fixture":
            raise InputError("historical input scope and rights references are missing")
    digest(body["calendar_sha256"])
    files = body["files"]
    if type(files) is not dict or not 1 <= len(files) <= MAX_FILES:
        raise InputError("bounded exact named input inventory required")
    for name, anchor in files.items():
        _name(name)
        digest(anchor)
    receipts = body["guidance_receipts"]
    if type(receipts) is not list or not 1 <= len(receipts) <= 6:
        raise InputError("bounded nonempty guidance receipt inventory required")
    used = []
    for row in receipts:
        row = keys(row, _RECEIPT_KEYS)
        used.extend((_name(row["raw_file"]), _name(row["document_file"])))
        if utc(row["received_at"]) > utc(row["validated_at"]):
            raise InputError("invalid declared receipt order")
    used.extend((_name(body["stock_market_file"]), _name(body["benchmark_market_file"])))
    if set(used) != set(files) or len(used) != len(set(used)):
        raise InputError("input roles must use the exact disjoint file inventory")
    decision, submitted, callback = (utc(body[key]) for key in ("decision_at", "submitted_at", "callback_at"))
    if not decision <= submitted < callback:
        raise InputError("decision submission callback order required")
    # A caller's fixture label is not proof of invention and must not bypass
    # this date fence. This seam has no need for protected-date fixtures.
    quarantine = checked.to_dict()["evidence"]["outcome_quarantine_from"]
    if callback.date().isoformat() >= quarantine:
        raise InputError("protected-date input requires a different explicit scope")
    return body


def prepare_inputs(candidate: Candidate, manifest_bytes: bytes, supplied_files: dict[str, bytes], *,
                   expected_manifest_sha256: str) -> dict:
    """Pure inspection of explicitly supplied bytes. Never authorize their use.

    This is one security/session structural seam, not a dataset-coverage audit,
    research look, full backtest, approval registry or frozen economic model.
    """
    if type(candidate) is not Candidate:
        raise InputError("exact pinned preparation candidate required")
    candidate = Candidate(candidate.canonical_bytes)
    body = _manifest(manifest_bytes, expected_manifest_sha256, candidate)
    if type(supplied_files) is not dict:
        raise InputError("supplied bytes differ from exact named inventory")
    # Freeze the caller-owned mapping before both anchoring and parsing. Its
    # values must be immutable bytes below; later caller replacements cannot
    # make a report describe hashes of different bytes than it inspected.
    supplied_files = dict(supplied_files)
    if set(supplied_files) != set(body["files"]):
        raise InputError("supplied bytes differ from exact named inventory")
    total = 0
    for name, raw in supplied_files.items():
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_FILE_BYTES:
            raise InputError("bounded immutable named input bytes required")
        total += len(raw)
        if total > MAX_TOTAL_BYTES or hash_bytes(raw) != body["files"][name]:
            raise InputError("input file anchor or aggregate byte bound mismatch")
    ledger, documents = GuidanceLedger(), []
    for row in body["guidance_receipts"]:
        document = GuidanceDocument.from_bytes(supplied_files[row["document_file"]])
        ledger = ledger.append(GuidanceReceipt(supplied_files[row["raw_file"]], document,
                                               row["received_at"], row["validated_at"]))
        documents.append(document)
    projection = ledger.as_of(body["decision_at"])
    market = {}
    for role, field in (("stock", "stock_market_file"), ("benchmark", "benchmark_market_file")):
        batch = HistoricalMarketBatch.from_bytes(supplied_files[body[field]])
        if batch.role != role:
            raise InputError("market file has the wrong declared role")
        market[role] = batch
    stock, benchmark = market["stock"], market["benchmark"]
    if stock.security_id == benchmark.security_id or stock.symbol == benchmark.symbol:
        raise InputError("strategy and SPY must have distinct dated identities")
    if (stock.session_date, stock.session_open_utc, stock.session_close_utc) != (
            benchmark.session_date, benchmark.session_open_utc, benchmark.session_close_utc):
        raise InputError("stock and SPY session bounds differ")
    if stock.session_date.isoformat() >= candidate.to_dict()["evidence"]["outcome_quarantine_from"]:
        raise InputError("market file contains protected-date input")
    if any(document.to_dict()["security_id"] != stock.security_id for document in documents):
        raise InputError("guidance and dated stock identity differ")
    if len({(document.to_dict()["provider"], document.to_dict()["issuer_id"])
            for document in documents}) != 1:
        raise InputError("single issuer and provider input epoch required")
    decisions = []
    for role, batch in market.items():
        try:
            quote = batch.decision_quote(utc(body["decision_at"]))
            minute = batch.subsequent_minute(submitted_at=utc(body["submitted_at"]),
                callback_at=utc(body["callback_at"]), decision_quote=quote)
            decisions.append({"role": role, "source_sha256": batch.sha256, "status": "structurally_prepared",
                "decision_quote_sip_ns": quote.sip_timestamp_ns,
                "minute_start_ns": minute.minute.start_timestamp_ns,
                "minute_end_ns": minute.minute.end_timestamp_ns,
                "source_projection_sha256": hash_bytes(batch.canonical_projection())})
        except InputError:
            # Retain both legs and a fixed refusal, without leaking source rows.
            decisions.append({"role": role, "source_sha256": batch.sha256,
                              "status": "refused", "reason": "market_decision_or_subsequent_minute_refused"})
    refused = [row for row in projection.decisions if row.disposition in ("refused", "quarantined")]
    prepared = not refused and all(row["status"] == "structurally_prepared" for row in decisions)
    return {"schema": "gdr.local-input-preparation.v1",
        "status": "structurally_prepared" if prepared else "structurally_blocked",
        "scope": "local_structural_inputs_only_no_simulation",
        "data_class": body["data_class"], "candidate_sha256": candidate.sha256,
        "manifest_sha256": expected_manifest_sha256, "file_sha256s": dict(body["files"]),
        "source_rights_reference": body["source_rights_reference"],
        "owner_scope_reference": body["owner_scope_reference"], "calendar_sha256": body["calendar_sha256"],
        "guidance": {"receipt_count": len(ledger.receipts), "as_of_receipt_count": len(projection.decisions),
            "head_sha256": ledger.head_sha256, "as_of_head_sha256": projection.head_sha256,
            "qualifying_arithmetic_comparisons": len(projection.active_comparisons),
            "observations": [{"document_sha256": row.document_sha256, "status": row.disposition,
                              "reasons": list(row.refusal_reasons)} for row in projection.decisions],
            "refusals": [{"document_sha256": row.document_sha256, "status": row.disposition,
                          "reasons": list(row.refusal_reasons)} for row in refused]},
        "market": decisions, "source_rights_verified": False, "source_completeness_verified": False,
        "calendar_and_mapping_verified": False, "common_history_verified": False, "data_class_verified": False,
        "point_in_time_data": False, "backtest_ready": False, "orders_allowed": False,
        "qc_access_allowed": False, "outcome_evaluation_allowed": False,
        "note": "Supplied references and consistent rows are not verified rights, scope, PIT or native parity."}


def inspect_local_inputs(candidate: Candidate, manifest_path: Path, *, expected_manifest_sha256: str) -> dict:
    """Inspect named regular files beside an explicitly selected local manifest.

    No directory discovery, subdirectory resolution, fetching, writes, source
    execution or automatic data acquisition. The containing folder must be
    owner controlled; hashes and file references are not access grants.
    """
    if not isinstance(manifest_path, Path):
        raise InputError("explicit local manifest Path required")
    try:
        raw = _read_regular_file(manifest_path, 65536)
        body = _manifest(raw, expected_manifest_sha256, candidate)
        supplied, total = {}, 0
        for name in sorted(body["files"]):
            if name == manifest_path.name:
                raise InputError("manifest cannot be its own data file")
            content = _read_regular_file(manifest_path.parent / _name(name), MAX_FILE_BYTES)
            total += len(content)
            if total > MAX_TOTAL_BYTES:
                raise InputError("local preparation aggregate byte bound exceeded")
            supplied[name] = content
        return prepare_inputs(candidate, raw, supplied, expected_manifest_sha256=expected_manifest_sha256)
    except CandidateError as exc:
        raise InputError("local preparation regular-file read refused") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect explicit local GDR input files; never run a backtest.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args(argv)
    try:
        report = inspect_local_inputs(load_candidate(), Path(args.manifest), expected_manifest_sha256=args.sha256)
    except (InputError, CandidateError):
        print('{"status":"input_preparation_refused","backtest_ready":false}')
        return 2
    print(canonical_bytes(report).decode())
    return 0 if report["status"] == "structurally_prepared" else 2


if __name__ == "__main__":
    raise SystemExit(main())
