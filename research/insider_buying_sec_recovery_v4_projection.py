"""Read-only, source-only projection of the separately captured first64 v4.

No transport, writes, legacy index/loader substitution or source-union promotion.
The CLI must be externally OS network/write/fork/exec denied; its audit hook is
additional defence, not self-attestation of OS policy. Current consumer bytes
and the older acquisition lineage are recorded separately. Only compact hashes,
counts and source-declared target/time metadata leave the process, never XML,
reporting-owner names, transaction values or economic eligibility decisions.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib
import json
from pathlib import Path
import re
import sys
import types
import weakref


VERSION = "INSETF-SEC-FRESH-FIRST64-OFFLINE-PROJECTION-v4"
SELF_PATH = "research/insider_buying_sec_recovery_v4_projection.py"
BASE_PATH = "research/insider_buying_sec_recovery_v4_historical_replay.py"
LANE_ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
CAPTURE_ID = "ib-sec-v4-first64-20261007-once"
CAPTURE_HEAD = "e900c7a90d326cd81df952684b0c583ad8ffb639"
REPORT_SHA256 = "f93c844f2866fddedb96fb4277d74089be7bfa46abbbc2421945bfc648750ff6"
SELECTION_SHA256 = "c3c4a4dd6899e2ef681937adf4a61c76f5f69a5f866e05fe515d81bd50fa12c8"
PREFIX_SHA256 = "48e5c2da08418e66d8b33c554a33048ac1b43bc66f3246304bbbc5beb1a22e70"
CAPTURE_INVENTORY_SHA256 = "79253cb7cab395bb6c03e528096c1961ac159d87c48131afef06224ec0ab35fd"
BASE_SHA256 = "dedbddf5782da30359239049d46a48fbde7a3fd64ac0da458b40f32ca2f4f725"
MAX_RECEIPT_BYTES = 1024 * 1024
MAX_ROWS = 64
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_TOKEN, _TEST_TOKEN = object(), object()
_IMAGES = weakref.WeakKeyDictionary()
_SOURCE_CONTEXT = None


class FreshV4ProjectionError(ValueError):
    pass


def _refuse(reason):
    raise FreshV4ProjectionError("REFUSED: " + reason)


def _raw(body):
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii") + b"\n"


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _authority():
    return {"source_authenticated": False, "official_acceptance_verified": False,
        "publication_time_verified": False, "point_in_time_data": False, "rights_verified": False,
        "canonical_evidence": False, "economic_attribution_verified": False,
        "amendment_linkage_verified": False, "complete_corpus": False,
        "direct_ib1c_ingest_authorized": False, "qc_authorized": False,
        "backtest_authorized": False, "execution_authorized": False, "output_written": False,
        "sec_dispatches": 0, "outcome_looks": 0, "qc_jobs": 0, "backtests": 0}


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class FreshV4ProjectionReceipt:
    _bytes: bytes
    _token: object

    def to_payload(self):
        if (type(self) is not FreshV4ProjectionReceipt or (self._token is not _TOKEN and self._token is not _TEST_TOKEN)
                or type(self._bytes) is not bytes or _IMAGES.get(self) != self._bytes):
            _refuse("exact factory-bound projection receipt required")
        body = json.loads(self._bytes)
        if body["authority"] != _authority() or _raw(body) != self._bytes:
            _refuse("projection receipt image differs")
        return body

    @property
    def raw_bytes(self):
        self.to_payload()
        return self._bytes

    @property
    def sha256(self):
        return _sha(self.raw_bytes)


def _target(request):
    from research.insider_buying.sec_complete_submission import SecCompleteSubmissionTarget
    return SecCompleteSubmissionTarget(period=request["period"], accession_number=request["accession_number"],
        form_type=request["form_type"], filing_date=request["filing_date"],
        issuer_cik=request["issuer_cik"].zfill(10), quarterly_index_sha256=request["master_source_sha256"],
        complete_submission_url=request["url"])


def _project_root(capture_id, report_sha, *, root, observed, consumer):
    from research import insider_buying_sec_recovery_v4_capture as capture
    from research import insider_buying_sec_recovery_v4_selection as selection
    from research.insider_buying.sec_complete_submission import (
        SecCompleteSubmissionError, project_sec_complete_submission)
    folders = []
    try:
        first = capture._verify_capture(capture_id, report_sha, root=root, observed=observed)
        if not first["batch_completed"] or not 1 <= first["completed_request_bound_bodies"] <= MAX_ROWS:
            _refuse("a complete bounded fresh capture is required")
        base = Path(root).joinpath(*capture.ARTIFACT_PARTS)
        run = capture._Directory(base / "runs" / capture_id); folders.append(run)
        objects = capture._Directory(run.path / "objects"); folders.append(objects)
        claims = capture._Directory(base / "claims"); folders.append(claims)
        report_raw = run.read("complete.json")
        if _sha(report_raw) != report_sha: _refuse("capture report changed before extraction")
        report = capture._decode(report_raw)
        reservation_raw = run.read("reservation.json")
        if _sha(reservation_raw) != report["reservation_sha256"]: _refuse("capture reservation changed")
        reservation = capture._decode(reservation_raw)
        selected = selection._validate_body(reservation["selection"], observed=observed)
        if observed and (capture_id != CAPTURE_ID or report_sha != REPORT_SHA256
                or reservation["capture_git_commit"] != CAPTURE_HEAD
                or report["selection_sha256"] != SELECTION_SHA256 or report["selected_prefix_sha256"] != PREFIX_SHA256
                or selected["current_source_inventory_sha256"] != CAPTURE_INVENTORY_SHA256
                or first["sec_dispatches"] != 64 or first["completed_request_bound_bodies"] != 64
                or first["retained_body_bytes"] != 504050):
            _refuse("observed first64 acquisition anchors differ")
        rows, projected, quarantined, total = [], 0, 0, 0
        for ordinal, request_row in enumerate(selected["requests"]):
            result_desc = report["results"][ordinal]
            result_raw = run.read(result_desc["result_name"])
            if _sha(result_raw) != result_desc["result_sha256"]: _refuse("capture result changed before projection")
            result = capture._decode(result_raw)
            start_raw = run.read(f"request-{ordinal:03d}-start.json")
            start = capture._decode(start_raw)
            claim_raw = claims.read(capture._claim_name(request_row))
            if _sha(start_raw) != result["start_sha256"] or _sha(claim_raw) != start["claim_sha256"]:
                _refuse("start or permanent request claim changed")
            if (result["disposition"] != "request-bound-parent-retained" or result["body_retained"] is not True
                    or result["global_index"] != request_row["global_index"]
                    or result["request_sha256"] != request_row["request_sha256"]):
                _refuse("exact retained request/result association differs")
            raw = objects.read(result["body_sha256"] + ".bin", cap=capture.MAX_PARENT_BYTES)
            if _sha(raw) != result["body_sha256"] or len(raw) != result["body_size_bytes"]:
                _refuse("retained parent changed before projection")
            target = _target(request_row["request"])
            row = {"ordinal": ordinal, "global_index": request_row["global_index"],
                "request_sha256": request_row["request_sha256"], "target": target.to_payload(),
                "claim_sha256": _sha(claim_raw), "start_sha256": _sha(start_raw),
                "result_sha256": result_desc["result_sha256"],
                "raw_parent": {"sha256": result["body_sha256"], "size_bytes": len(raw)}}
            try:
                projection = project_sec_complete_submission(target, raw)
                payload = projection.to_payload()
                if payload["raw_parent"]["sha256"] != result["body_sha256"]:
                    _refuse("pure projection parent digest differs")
                row.update({"disposition": "complete_parent_projected_noncanonical", "projection": {
                    "version": payload["version"], "payload_sha256": projection.sha256,
                    "header": {key: payload["children"]["header"][key] for key in ("sha256", "size_bytes")},
                    "primary_xml": {key: payload["children"]["primary_xml"][key] for key in ("sha256", "size_bytes")},
                    "accepted_at_raw": payload["source_fields"]["accepted_at_raw"],
                    "header_owner_cik_count": len(payload["source_fields"]["header_owner_ciks"])}})
                projected += 1
                del projection, payload
            except SecCompleteSubmissionError:
                # Header-bound acquisition remains valid. Do not fabricate an
                # ownership child/zero rows or persist potentially raw messages.
                row.update({"disposition": "complete_parent_grammar_quarantine",
                            "quarantine_code": "unsupported_complete_submission_grammar"})
                quarantined += 1
            total += len(raw)
            rows.append(row)
            del raw, target, row
        last = capture._verify_capture(capture_id, report_sha, root=root, observed=observed)
        if last != first: _refuse("capture changed during projection")
        for folder in folders: folder.check()
        if projected + quarantined != len(rows) or total != first["retained_body_bytes"]:
            _refuse("projection row/byte accounting differs")
        body = {"kind": VERSION, "scope": "observed_first64_capture" if observed else "invented_test_only",
            "capture_id": capture_id, "capture_git_commit": reservation["capture_git_commit"],
            "capture_report_sha256": report_sha, "capture_reservation_sha256": report["reservation_sha256"],
            "capture_selection_sha256": report["selection_sha256"], "capture_selected_prefix_sha256": report["selected_prefix_sha256"],
            "capture_source_inventory_sha256": selected["current_source_inventory_sha256"],
            "capture_worker_source_sha256": selected["worker_source_sha256"], "capture_replay_anchors": selected["replay_anchors"],
            "consumer": consumer(), "rows": rows, "ordered_rows_sha256": _sha(_raw(rows)),
            "counts": {"header_bound_retained": len(rows), "complete_parent_projected": projected,
                "complete_parent_grammar_quarantined": quarantined, "raw_parent_bytes": total},
            "denominator": {"frozen_total": 99394, "prior_source_bound_count": 19526 if observed else 0,
                "originally_unattempted_count": 79868, "post_capture_source_union_replayed": False,
                "source_bound_union_count_promoted": False}, "authority": _authority()}
        image = _raw(body)
        if len(image) > MAX_RECEIPT_BYTES: _refuse("compact projection receipt exceeded its cap")
        receipt = FreshV4ProjectionReceipt(image, _TOKEN if observed else _TEST_TOKEN)
        _IMAGES[receipt] = image
        return receipt
    finally:
        for folder in reversed(folders): folder.close()


def replay_observed_first64_v4_projection(*, expected_report_sha256, expected_capture_head,
        projection_repository_head, expected_projection_source_sha256):
    """Public observed factory; available only inside the source-only CLI."""
    if _SOURCE_CONTEXT is None: _refuse("source-only projection CLI execution required")
    base, sources, finder = _SOURCE_CONTEXT
    if (expected_report_sha256 != REPORT_SHA256 or expected_capture_head != CAPTURE_HEAD
            or type(projection_repository_head) is not str or _COMMIT.fullmatch(projection_repository_head) is None
            or type(expected_projection_source_sha256) is not str or _SHA.fullmatch(expected_projection_source_sha256) is None
            or _sha(dict(sources)[SELF_PATH]) != expected_projection_source_sha256):
        _refuse("external capture/consumer source anchors differ")
    def consumer():
        base._assert_sources_unchanged(sources)
        executed = [{**row, "source_kind": ("current_snapshot_matching_historical_digest"
            if row["source_kind"] == "historical_git_blob" else "current_source_snapshot")} for row in finder.executed]
        return {"declared_projection_repository_head": projection_repository_head,
            "projection_head_independently_git_verified": False,
            "projection_source_sha256": expected_projection_source_sha256,
            "current_source_inventory_sha256": base._digest([{"path": p, "sha256": _sha(r)} for p, r in sources]),
            "executed_sources": [{"path": BASE_PATH, "sha256": BASE_SHA256, "source_kind": "current_source_bootstrap"}, *executed],
            "source_only_lane_imports": True, "audit_network_write_process_denial_installed": True,
            "external_os_isolation_required_not_self_attested": True}
    base._assert_sources_unchanged(sources)
    try:
        result = _project_root(CAPTURE_ID, REPORT_SHA256, root=LANE_ROOT, observed=True, consumer=consumer)
        base._assert_sources_unchanged(sources)
        return result
    except FreshV4ProjectionError:
        raise
    except Exception:
        raise FreshV4ProjectionError("REFUSED: read-only fresh projection failed") from None


def _main():
    import argparse
    parser = argparse.ArgumentParser(description="Externally isolated, read-only first64 SEC projection")
    parser.add_argument("--expected-report-sha256", required=True)
    parser.add_argument("--expected-capture-head", required=True)
    parser.add_argument("--projection-repository-head", required=True)
    parser.add_argument("--expected-projection-source-sha256", required=True)
    args = parser.parse_args()
    if Path(__file__).resolve() != LANE_ROOT / SELF_PATH:
        _refuse("exact designated lane source path required")
    if any(name.split(".")[0] in {"research", "data", "ml"} for name in sys.modules):
        _refuse("lane imports preceded source-only bootstrap")
    base_raw = (LANE_ROOT / BASE_PATH).read_bytes()
    if _sha(base_raw) != BASE_SHA256: _refuse("accepted base bootstrap bytes differ")
    base = types.ModuleType("_fresh_v4_projection_base")
    base.__file__ = str(LANE_ROOT / BASE_PATH)
    sys.modules[base.__name__] = base
    exec(compile(base_raw, base.__file__, "exec", dont_inherit=True), base.__dict__)
    sources = base._source_snapshot()
    if _sha(dict(sources)[SELF_PATH]) != args.expected_projection_source_sha256:
        _refuse("externally bound projection source differs")
    blobs = tuple((path, dict(sources)[path]) for path, _ in base.HISTORICAL_FILES)
    # These are captured CURRENT byte images matching the historical digests;
    # no Git bytes or full historical environment are reconstructed here.
    finder = base._HistoricalBlobFinder(blobs, sources)
    sys.addaudithook(base._audit_event)
    sys.meta_path.insert(0, finder)
    worker = importlib.import_module("research.insider_buying_sec_recovery_v4_projection")
    worker._SOURCE_CONTEXT = (base, sources, finder)
    receipt = worker.replay_observed_first64_v4_projection(**vars(args))
    sys.stdout.buffer.write(receipt.raw_bytes)
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    try: _main()
    except Exception:
        sys.stderr.write("REFUSED: isolated first64 projection failed\n")
        raise SystemExit(1) from None
