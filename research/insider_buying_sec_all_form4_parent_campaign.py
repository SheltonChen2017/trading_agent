"""Bounded, source-bound acquisition of the exact two-quarter Form 4 parent set.

The real entry rebuilds both IB-1B snapshots, both pilot master indexes, the
99,394-locator manifest, and the completed 9,337-parent replay before any SEC
dispatch.  Output is noncanonical raw source, never a signal or QC authority.
The synthetic entry has a separate scope and cannot use the real transport.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Mapping
import http.client
import json
import os
import re
import stat
import subprocess
import time

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying.ib1b_all_form4_parent_locators import (
    AllForm4ParentQuarterInput, build_ib1b_all_form4_parent_locator_manifest,
)
from research.insider_buying.ib1b_observed_candidate_inventory import (
    build_ib1b_observed_candidate_inventory,
)
from research.insider_buying.ib1b_observed_master_locators import (
    ObservedMasterLocatorQuarterInput, build_ib1b_observed_master_locator_manifest,
)
from research.insider_buying.sec_bulk_parsed_snapshot import load_sec_bulk_parsed_snapshot
from research.insider_buying.sec_complete_submission import (
    MAX_COMPLETE_HEADER_BYTES, SecCompleteSubmissionError,
    SecCompleteSubmissionTarget, _date_digits, _header_identity,
)
from research.insider_buying.sec_quarter_master_index import parse_sec_quarter_master_index
from research.insider_buying_sec_acquisition import (
    _open_output_directory, _check_output_directory, _plain_path,
    _publish_immutable, _refuse_output_overlap, _store_object,
)
from research.insider_buying_sec_complete_acquisition import (
    MAX_COMPLETE_TXT_BYTES, SecCompleteAcquisitionError, SecHttpResult,
)
from research.insider_buying_sec_complete_projection_adapter import (
    FINAL_REPORT_SHA256, _PinnedRoot, _canonical_object, _descriptor,
    _master_plain, load_fixed_complete_pilot,
)
from research.insider_buying_sec_master82_runner import _RootLock, _read_recoverable
from research.insider_buying_sec_selected_parent_projection_adapter import (
    load_observed_selected_parent_root,
)
from research.insider_buying_sec_selected_parent_runner import (
    SecSelectedParentRunnerError, _Events, _MAX_EVENT_BYTES, _MAX_EVENTS,
    _selected_sec_transport, _strict_selected_response, _utc,
)


CAMPAIGN_VERSION = "INSETF-SEC-ALL-FORM4-PARENTS-CAMPAIGN-v1"
REAL_MANIFEST_SHA256 = "3e9a0f3d1e7abe6865a70228e05b58300093211c712e980d5f146a8e3cc3d355"
SELECTED_REPORT_SHA256 = "97300d31e1bdf7fd4c44ae04bf6f94415dd7599ef5048c84b011697bdcf58f0a"
SELECTED_RECEIPT_LINEAGE_SHA256 = "959208ebce46e0a5583d151b9bd233e17bacbe5403a22b1b4e53d716a7cefd1c"
REAL_REQUEST_COUNT = 99_394
REAL_REUSE_COUNT = 9_337
SHARD_SIZE = 8_192
MAX_SHARDS = 13
MAX_RUN_OBJECT_BYTES = 48 * 1024**3
MIN_FREE_BYTES = 8 * 1024**3
MIN_REQUEST_INTERVAL_NS = 500_000_000
MAX_ATTEMPTS = 3
MAX_SHARD_INVENTORY_BYTES = 8 * 1024**2
MAX_SHARD_JOURNAL_BYTES = 256 * 1024**2
MAX_SHARD_REPORT_BYTES = 32 * 1024**2
MAX_CAMPAIGN_PLAN_BYTES = 256 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_CIK = re.compile(r"[0-9]{1,10}\Z")
_ARCHIVE = re.compile(r"edgar/data/[0-9]{1,10}/[0-9]{10}-[0-9]{2}-[0-9]{6}\.txt\Z")
_CONTACT = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}\Z")
_RETRY_HTTP = {500, 502, 503, 504}
_REAL_TOKEN = object()


class CampaignError(ValueError):
    """A source binding, run transition, or durable replay refused."""


def _refuse(reason: str) -> None:
    raise CampaignError(f"REFUSED: {reason}")


def _bytes(value: object) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def _json(raw: bytes, *, label: str) -> dict[str, object]:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                _refuse(f"{label} repeats a key")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=unique,
                           parse_constant=lambda _: _refuse(f"{label} is nonfinite"))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise CampaignError(f"REFUSED: {label} is not strict JSON") from exc
    if type(value) is not dict or _bytes(value) != raw:
        _refuse(f"{label} is not canonical JSON plus LF")
    return value


@dataclass(frozen=True, slots=True)
class CampaignRequest:
    period: str
    accession_number: str
    form_type: str
    filing_date: str
    issuer_cik: str
    archive_path: str
    submission_row_id: str
    parsed_lineage_hash: str
    master_source_sha256: str

    @property
    def url(self) -> str:
        return "https://www.sec.gov/Archives/" + self.archive_path

    def to_payload(self) -> dict[str, str]:
        if (type(self) is not CampaignRequest
                or type(self.period) is not str
                or self.period not in {"2022Q4", "2023Q1"}
                or type(self.accession_number) is not str
                or _ACCESSION.fullmatch(self.accession_number) is None
                or type(self.form_type) is not str
                or self.form_type not in {"4", "4/A"}
                or type(self.filing_date) is not str
                or type(self.issuer_cik) is not str
                or _CIK.fullmatch(self.issuer_cik) is None
                or int(self.issuer_cik) == 0
                or type(self.archive_path) is not str
                or _ARCHIVE.fullmatch(self.archive_path) is None
                or not self.archive_path.endswith(self.accession_number + ".txt")
                or any(type(value) is not str or _SHA.fullmatch(value) is None
                       for value in (self.submission_row_id, self.parsed_lineage_hash,
                                     self.master_source_sha256))):
            _refuse("campaign request is malformed")
        return {"period": self.period, "accession_number": self.accession_number,
                "form_type": self.form_type, "filing_date": self.filing_date,
                "issuer_cik": self.issuer_cik, "archive_path": self.archive_path,
                "submission_row_id": self.submission_row_id,
                "parsed_lineage_hash": self.parsed_lineage_hash,
                "master_source_sha256": self.master_source_sha256,
                "url": self.url}


@dataclass(frozen=True, slots=True)
class CampaignReuse:
    accession_number: str
    object_sha256: str
    object_size_bytes: int
    prior_report_sha256: str

    def to_payload(self) -> dict[str, object]:
        if (type(self) is not CampaignReuse or type(self.accession_number) is not str
                or _ACCESSION.fullmatch(self.accession_number) is None
                or any(type(value) is not str or _SHA.fullmatch(value) is None
                       for value in (self.object_sha256, self.prior_report_sha256))
                or type(self.object_size_bytes) is not int
                or not 0 < self.object_size_bytes <= MAX_COMPLETE_TXT_BYTES):
            _refuse("campaign reuse descriptor is malformed")
        return {"accession_number": self.accession_number,
                "object_sha256": self.object_sha256,
                "object_size_bytes": self.object_size_bytes,
                "prior_report_sha256": self.prior_report_sha256}


@dataclass(frozen=True, slots=True)
class CampaignPlan:
    scope: str
    manifest_sha256: str
    requests: tuple[CampaignRequest, ...]
    reuses: tuple[CampaignReuse, ...] = ()
    shard_size: int = SHARD_SIZE
    selected_report_sha256: str | None = None
    selected_receipt_lineage_sha256: str | None = None
    _real_token: object | None = field(default=None, repr=False, compare=False)

    def to_payload(self) -> dict[str, object]:
        if (type(self) is not CampaignPlan
                or type(self.scope) is not str
                or self.scope not in {"synthetic_test_manifest", "ib1b_observed_full_form4_noncanonical"}
                or type(self.manifest_sha256) is not str or _SHA.fullmatch(self.manifest_sha256) is None
                or type(self.requests) is not tuple or not self.requests
                or len(self.requests) > REAL_REQUEST_COUNT
                or any(type(item) is not CampaignRequest for item in self.requests)
                or type(self.reuses) is not tuple
                or any(type(item) is not CampaignReuse for item in self.reuses)
                or type(self.shard_size) is not int
                or not 1 <= self.shard_size <= SHARD_SIZE):
            _refuse("campaign plan identity or size is invalid")
        requests = [item.to_payload() for item in self.requests]
        reuses = [item.to_payload() for item in self.reuses]
        keys = [(item["period"], item["accession_number"]) for item in requests]
        if (keys != sorted(set(keys))
                or len({item["accession_number"] for item in requests}) != len(requests)
                or [item["accession_number"] for item in reuses]
                != sorted({item["accession_number"] for item in reuses})
                or not {item["accession_number"] for item in reuses}
                <= {item["accession_number"] for item in requests}):
            _refuse("campaign request or reuse order/uniqueness changed")
        if self.scope == "ib1b_observed_full_form4_noncanonical":
            if (self._real_token is not _REAL_TOKEN
                    or self.manifest_sha256 != REAL_MANIFEST_SHA256
                    or self.selected_report_sha256 != SELECTED_REPORT_SHA256
                    or self.selected_receipt_lineage_sha256 != SELECTED_RECEIPT_LINEAGE_SHA256
                    or len(requests) != REAL_REQUEST_COUNT
                    or len(reuses) != REAL_REUSE_COUNT
                    or self.shard_size != SHARD_SIZE
                    or sum(row["period"] == "2022Q4" for row in requests) != 35_550
                    or sum(row["period"] == "2023Q1" for row in requests) != 63_844
                    or any(row["prior_report_sha256"] != SELECTED_REPORT_SHA256 for row in reuses)):
                _refuse("real campaign is not the exact observed two-quarter cohort")
        elif (self._real_token is not None or self.selected_report_sha256 is not None
              or self.selected_receipt_lineage_sha256 is not None):
            _refuse("synthetic campaign carries real-source identity")
        return {"kind": CAMPAIGN_VERSION, "source_scope": self.scope,
                "manifest_sha256": self.manifest_sha256,
                "request_inventory_sha256": hash_payload(requests),
                "requests": requests, "reuses": reuses,
                "shard_size": self.shard_size,
                "selected_report_sha256": self.selected_report_sha256,
                "selected_receipt_lineage_sha256": self.selected_receipt_lineage_sha256,
                "source_authenticated": False, "quarter_population_complete": False,
                "canonical_evidence": False, "point_in_time_data": False,
                "outcome_looks": 0, "qc_jobs": 0}


def _verify_exact_committed_code(commit: str) -> None:
    if type(commit) is not str or _COMMIT.fullmatch(commit) is None:
        _refuse("capture code commit must be a full Git SHA")
    root = Path(__file__).resolve().parents[1]
    paths = (
        "research/insider_buying_sec_all_form4_parent_campaign.py",
        "research/insider_buying/ib1b_all_form4_parent_locators.py",
        "research/insider_buying_sec_selected_parent_projection_adapter.py",
        "research/insider_buying_sec_selected_parent_runner.py",
        "research/insider_buying_sec_complete_projection_adapter.py",
        "research/insider_buying/sec_bulk_parsed_snapshot.py",
        "research/insider_buying/sec_quarter_master_index.py",
        "research/insider_buying/sec_complete_submission.py",
        "data/hashing.py",
    )
    try:
        command = lambda *args: subprocess.check_output(args, cwd=root, stderr=subprocess.DEVNULL)
        if (command("git", "rev-parse", "--show-toplevel").decode().strip() != str(root)
                or command("git", "branch", "--show-current").decode().strip()
                != "codex/strategy-insider-buying"
                or command("git", "rev-parse", "HEAD").decode().strip() != commit
                or command("git", "status", "--porcelain=v1", "--untracked-files=all")):
            _refuse("exact clean committed Insider lane is required")
        for relative in paths:
            if hash_bytes(command("git", "show", f"{commit}:{relative}")) != hash_bytes((root / relative).read_bytes()):
                _refuse("committed campaign dependency differs on disk")
    except (OSError, UnicodeError, subprocess.CalledProcessError) as exc:
        raise CampaignError("REFUSED: exact campaign code commit could not be verified") from exc


def _build_real_plan(
    raw_q4_directory: str | Path, parsed_q4_directory: str | Path,
    raw_q1_directory: str | Path, parsed_q1_directory: str | Path,
    exact16_pilot_root: str | Path, selected_root: str | Path,
) -> CampaignPlan:
    """Rebind the exact retained bytes through public loaders before a request.

    The fixed-pilot loader verifies the whole prior acquisition; pinned reads
    below extract its two already-verified master objects as fresh parser
    receipts. Neither a caller receipt nor an internally coherent hash alone
    can provide the real run's source authority.
    """
    try:
        pilot_root = _plain_path(exact16_pilot_root, must_exist=True)
        selected = _plain_path(selected_root, must_exist=True)
        load_fixed_complete_pilot(pilot_root).to_payload()
        with _PinnedRoot(pilot_root) as pinned:
            report_raw = pinned.read(
                f"sec-complete-report-{FINAL_REPORT_SHA256}.json",
                label="fixed pilot report", max_bytes=2 * 1024**2,
            )
            if hash_bytes(report_raw) != FINAL_REPORT_SHA256:
                _refuse("fixed pilot report content changed")
            report = _canonical_object(report_raw, label="fixed pilot report")
            masters = []
            for (period, year, quarter), row in zip(
                (("2022Q4", 2022, 4), ("2023Q1", 2023, 1)),
                report["master_indexes"], strict=True,
            ):
                if row["period"] != period:
                    _refuse("fixed pilot master period changed")
                compressed = _descriptor(pinned, row["raw_object"],
                                         role="master.gz", max_bytes=8 * 1024**2)
                master = parse_sec_quarter_master_index(
                    _master_plain(compressed), year=year, quarter=quarter,
                )
                if (master.source_sha256 != row["receipt"]["source_sha256"]
                        or master.receipt_sha256 != row["receipt"]["receipt_sha256"]):
                    _refuse("fixed pilot master receipt changed")
                masters.append(master)
        loaded = (
            load_sec_bulk_parsed_snapshot(
                parsed_q4_directory, raw_snapshot_directory=raw_q4_directory,
            ),
            load_sec_bulk_parsed_snapshot(
                parsed_q1_directory, raw_snapshot_directory=raw_q1_directory,
            ),
        )
        full_inputs = tuple(AllForm4ParentQuarterInput(parsed, master)
                            for parsed, master in zip(loaded, masters, strict=True))
        full = build_ib1b_all_form4_parent_locator_manifest(full_inputs)
        full.verify_digest()
        if (full.content_sha256 != REAL_MANIFEST_SHA256
                or full.total_accessions != REAL_REQUEST_COUNT
                or tuple(quarter.total_accessions for quarter in full.quarters)
                != (35_550, 63_844)):
            _refuse("full Form 4 source manifest is not the pinned two-quarter set")
        observed_inputs = tuple(
            ObservedMasterLocatorQuarterInput(
                build_ib1b_observed_candidate_inventory(parsed), parsed, master,
            ) for parsed, master in zip(loaded, masters, strict=True)
        )
        priority = build_ib1b_observed_master_locator_manifest(observed_inputs)
        priority.verify_digest()
        receipt = load_observed_selected_parent_root(selected, observed_inputs)
        receipt.to_payload()
        if (receipt.report_sha256 != SELECTED_REPORT_SHA256
                or receipt.lineage_sha256 != SELECTED_RECEIPT_LINEAGE_SHA256
                or len(receipt.rows) != REAL_REUSE_COUNT
                or not receipt.projections_verified):
            _refuse("selected parent root is not the pinned replay")
        full_by_accession = {
            locator.accession_number: (quarter, locator)
            for quarter in full.quarters for locator in quarter.locators
        }
        selected_locators = tuple(
            (quarter, locator)
            for quarter in priority.quarters for locator in quarter.locators
        )
        if len(selected_locators) != REAL_REUSE_COUNT:
            _refuse("selected root is not the exact priority subset")
        with _PinnedRoot(selected) as pinned:
            inventory = _canonical_object(
                pinned.read("inventory.json", label="selected inventory",
                            max_bytes=8 * 1024**2), label="selected inventory",
            )
            selected_requests = inventory["requests"]
            if len(selected_requests) != REAL_REUSE_COUNT:
                _refuse("selected source inventory count changed")
            reuses: list[CampaignReuse] = []
            for (quarter, locator), row, request in zip(
                selected_locators, receipt.rows, selected_requests, strict=True,
            ):
                full_row = full_by_accession.get(locator.accession_number)
                # Priority locator carries selection reasons, while the full
                # locator carries a candidate hash. Their common source and
                # archive identity must match field for field.
                if (full_row is None or full_row[0].period != quarter.period
                        or any(
                            getattr(full_row[1], name) != getattr(locator, name)
                            for name in ("accession_number", "form_type",
                                         "filing_date", "issuer_cik", "archive_path",
                                         "submission_row_id")
                        )):
                    _refuse("selected priority is not an exact full-source subset")
                if (row.period != quarter.period
                        or row.accession_number != locator.accession_number
                        or row.form_type != locator.form_type
                        or row.submission_row_id != locator.submission_row_id
                        or request != {
                            "period": quarter.period,
                            "accession_number": locator.accession_number,
                            "form_type": locator.form_type,
                            "filing_date": locator.filing_date,
                            "issuer_cik": locator.issuer_cik,
                            "master_source_sha256": quarter.master_source_sha256,
                            "parsed_lineage_hash": quarter.parsed_lineage_hash,
                            "url": "https://www.sec.gov/Archives/" + locator.archive_path,
                        }):
                    _refuse("selected replay request differs from full-source locator")
                reuses.append(CampaignReuse(
                    accession_number=row.accession_number,
                    object_sha256=row.raw_parent_sha256,
                    object_size_bytes=row.raw_parent_size_bytes,
                    prior_report_sha256=receipt.report_sha256,
                ))
        requests = tuple(
            CampaignRequest(
                period=quarter.period,
                accession_number=locator.accession_number,
                form_type=locator.form_type, filing_date=locator.filing_date,
                issuer_cik=locator.issuer_cik, archive_path=locator.archive_path,
                submission_row_id=locator.submission_row_id,
                parsed_lineage_hash=quarter.parsed_lineage_hash,
                master_source_sha256=quarter.master_source_sha256,
            ) for quarter in full.quarters for locator in quarter.locators
        )
        plan = CampaignPlan(
            scope="ib1b_observed_full_form4_noncanonical",
            manifest_sha256=full.content_sha256, requests=requests,
            reuses=tuple(sorted(reuses, key=lambda item: item.accession_number)),
            selected_report_sha256=receipt.report_sha256,
            selected_receipt_lineage_sha256=receipt.lineage_sha256,
            _real_token=_REAL_TOKEN,
        )
        plan.to_payload()
        return plan
    except CampaignError:
        raise
    except (OSError, TypeError, ValueError, KeyError, IndexError) as exc:
        raise CampaignError(
            "REFUSED: exact source bytes or replay could not build the campaign"
        ) from exc


def _shards(plan: CampaignPlan, capture_git_commit: str) -> tuple[tuple[dict[str, object], bytes], ...]:
    payload = plan.to_payload()
    rows = payload["requests"]
    reuse_by_accession = {row["accession_number"]: row for row in payload["reuses"]}
    shards: list[tuple[dict[str, object], bytes]] = []
    for index, start in enumerate(range(0, len(rows), plan.shard_size)):
        requests = rows[start:start + plan.shard_size]
        reuses = [reuse_by_accession[row["accession_number"]] for row in requests
                  if row["accession_number"] in reuse_by_accession]
        name = f"shard-{index:04d}"
        inventory = {
            "kind": CAMPAIGN_VERSION + "/shard-inventory", "source_scope": plan.scope,
            "manifest_sha256": plan.manifest_sha256,
            "request_inventory_sha256": payload["request_inventory_sha256"],
            "selected_report_sha256": plan.selected_report_sha256,
            "selected_receipt_lineage_sha256": plan.selected_receipt_lineage_sha256,
            "capture_git_commit": capture_git_commit,
            "name": name, "start": start, "count": len(requests),
            "requests": requests, "reuses": reuses,
            "max_attempts_per_artifact": MAX_ATTEMPTS,
            "max_success_bytes": MAX_COMPLETE_TXT_BYTES,
            "minimum_transport_completion_spacing_ns": MIN_REQUEST_INTERVAL_NS,
            "source_authenticated": False, "canonical_evidence": False,
            "point_in_time_data": False, "outcome_looks": 0, "qc_jobs": 0,
        }
        raw = _bytes(inventory)
        if len(raw) > MAX_SHARD_INVENTORY_BYTES:
            _refuse("shard inventory exceeds its byte budget")
        shards.append((inventory, raw))
    if not shards or len(shards) > MAX_SHARDS or (
        plan.scope == "ib1b_observed_full_form4_noncanonical"
        and len(shards) != MAX_SHARDS
    ):
        _refuse("campaign shard count is outside the bounded plan")
    return tuple(shards)


def _campaign_plan(plan: CampaignPlan, capture_git_commit: str,
                   shards: tuple[tuple[dict[str, object], bytes], ...]) -> bytes:
    payload = plan.to_payload()
    body = {
        "kind": CAMPAIGN_VERSION + "/plan", "source_scope": plan.scope,
        "manifest_sha256": plan.manifest_sha256,
        "request_inventory_sha256": payload["request_inventory_sha256"],
        "selected_report_sha256": plan.selected_report_sha256,
        "selected_receipt_lineage_sha256": plan.selected_receipt_lineage_sha256,
        "capture_git_commit": capture_git_commit,
        "total_accessions": len(plan.requests), "reuse_count": len(plan.reuses),
        "new_request_count": len(plan.requests) - len(plan.reuses),
        "shard_size": plan.shard_size, "max_run_object_bytes": MAX_RUN_OBJECT_BYTES,
        "minimum_free_bytes": MIN_FREE_BYTES,
        "shards": [
            {"name": inventory["name"], "start": inventory["start"],
             "count": inventory["count"], "inventory_sha256": hash_bytes(raw)}
            for inventory, raw in shards
        ],
        "complete_parent_bytes_acquired": False,
        "source_authenticated": False, "canonical_evidence": False,
        "point_in_time_data": False, "outcome_looks": 0, "qc_jobs": 0,
    }
    raw = _bytes(body)
    if len(raw) > MAX_CAMPAIGN_PLAN_BYTES:
        _refuse("campaign plan exceeds its byte budget")
    return raw


def preflight_observed_all_form4_parent_campaign(
    raw_q4_directory: str | Path, parsed_q4_directory: str | Path,
    raw_q1_directory: str | Path, parsed_q1_directory: str | Path,
    exact16_pilot_root: str | Path, selected_root: str | Path,
) -> dict[str, object]:
    """Read-only exact-source preflight; neither a launch plan nor authority.

    The placeholder commit has the exact SHA width solely for serialized-size
    measurement. Per-shard *request* hashes are stable; operational inventory
    hashes are code-bound and are deliberately not returned before launch.
    """
    plan = _build_real_plan(
        raw_q4_directory, parsed_q4_directory,
        raw_q1_directory, parsed_q1_directory,
        exact16_pilot_root, selected_root,
    )
    payload = plan.to_payload()
    shards = _shards(plan, "0" * 40)
    return {
        "kind": CAMPAIGN_VERSION + "/read-only-preflight",
        "manifest_sha256": plan.manifest_sha256,
        "request_inventory_sha256": payload["request_inventory_sha256"],
        "selected_report_sha256": plan.selected_report_sha256,
        "selected_receipt_lineage_sha256": plan.selected_receipt_lineage_sha256,
        "total_accessions": len(plan.requests),
        "reused_selected_parents": len(plan.reuses),
        "new_requests": len(plan.requests) - len(plan.reuses),
        "shard_count": len(shards),
        "shards": [
            {"name": inventory["name"], "start": inventory["start"],
             "count": inventory["count"], "reuse_count": len(inventory["reuses"]),
             "new_request_count": inventory["count"] - len(inventory["reuses"]),
             "request_sha256": hash_payload(inventory["requests"]),
             "serialized_inventory_size_bytes": len(raw),
             "under_inventory_cap": len(raw) <= MAX_SHARD_INVENTORY_BYTES}
            for inventory, raw in shards
        ],
        "preflight_code_commit_unbound": True,
        "source_authenticated": False, "complete_parent_bytes_acquired": False,
        "canonical_evidence": False, "point_in_time_data": False,
        "outcome_looks": 0, "qc_jobs": 0,
    }


def _capacity_ok(output: Path, identity: tuple[int, int], used_bytes: int) -> bool:
    descriptor = _open_output_directory(output, identity)
    try:
        info = os.statvfs(descriptor)
        available = info.f_bavail * info.f_frsize
        _check_output_directory(output, descriptor, identity)
        return (available >= MIN_FREE_BYTES + MAX_COMPLETE_TXT_BYTES + 4096
                and used_bytes + MAX_COMPLETE_TXT_BYTES <= MAX_RUN_OBJECT_BYTES)
    finally:
        os.close(descriptor)


def _recover(path: Path, *, label: str, max_bytes: int,
             expected_raw: bytes | None = None) -> bytes:
    try:
        return _read_recoverable(path, label=label, max_bytes=max_bytes,
                                 expected_raw=expected_raw)
    except (OSError, ValueError) as exc:
        raise CampaignError(f"REFUSED: {label} changed or is unreadable") from exc


def _publish_same_or_new(root: Path, name: str, raw: bytes,
                         identity: tuple[int, int], *, cap: int) -> Path:
    if len(raw) > cap:
        _refuse("immutable campaign publication exceeds its byte budget")
    try:
        return _publish_immutable(root, name, raw, identity)
    except FileExistsError:
        if _recover(root / name, label="campaign publication",
                    max_bytes=cap, expected_raw=raw) != raw:
            _refuse("immutable campaign publication changed")
        return root / name


def _check_utc(value: object) -> None:
    if type(value) is not str or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}\+00:00", value
    ):
        _refuse("event clock is not canonical UTC")
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError as exc:
        raise CampaignError("REFUSED: event clock is invalid") from exc
    if stamp.utcoffset() != timedelta(0):
        _refuse("event clock is not UTC")


def _read_object(output: Path, digest: object, size: object) -> bytes:
    if (type(digest) is not str or _SHA.fullmatch(digest) is None
            or type(size) is not int or not 0 < size <= MAX_COMPLETE_TXT_BYTES):
        _refuse("campaign object descriptor is malformed")
    raw = _recover(output / "objects" / f"{digest}.bin",
                   label="campaign parent object", max_bytes=MAX_COMPLETE_TXT_BYTES)
    if len(raw) != size or hash_bytes(raw) != digest:
        _refuse("campaign parent object hash or size changed")
    return raw


def _validate_parent_header(raw: bytes, request: dict[str, object]) -> None:
    """Bind a bounded parent envelope and reviewed header to its exact locator.

    Acquisition does not parse the document bodies or claim XML projection.
    The existing complete-submission header parser checks its supported
    SGML dialects, including accession, form, filing date and issuer identity.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_COMPLETE_TXT_BYTES:
        _refuse("campaign parent bytes are not bounded")
    try:
        target = SecCompleteSubmissionTarget(
            period=request["period"], accession_number=request["accession_number"],
            form_type=request["form_type"], filing_date=request["filing_date"],
            # The quarter-index locator permits 1–10 digits; the complete-
            # submission target compares the ten-digit header representation.
            # Preserve the raw locator in its request and lineage hashes.
            issuer_cik=request["issuer_cik"].zfill(10),
            quarterly_index_sha256=request["master_source_sha256"],
            complete_submission_url=request["url"],
        )
    except SecCompleteSubmissionError as exc:
        raise CampaignError(str(exc)) from exc
    opener_end = raw.find(b"\n", 0, 128)
    if opener_end < 0:
        _refuse("campaign parent has no bounded SEC-DOCUMENT opener")
    opener = re.fullmatch(
        rb"<SEC-DOCUMENT>([0-9]{10}-[0-9]{2}-[0-9]{6})\.txt : ([0-9]{8})",
        raw[:opener_end].removesuffix(b"\r"),
    )
    if opener is None or opener.group(1).decode("ascii") != target.accession_number:
        _refuse("campaign parent opener disagrees with accession")
    header_start = opener_end + 1
    if not raw.startswith(b"<SEC-HEADER>", header_start):
        _refuse("campaign parent has no leading SEC-HEADER")
    closer = b"</SEC-HEADER>"
    closer_start = raw.find(closer, header_start,
                            header_start + MAX_COMPLETE_HEADER_BYTES)
    if closer_start < 0:
        _refuse("campaign parent has no bounded SEC-HEADER close")
    header_end = closer_start + len(closer)
    if raw[header_end:header_end + 2] == b"\r\n":
        header_end += 2
    elif raw[header_end:header_end + 1] == b"\n":
        header_end += 1
    elif header_end != len(raw):
        _refuse("campaign parent SEC-HEADER close is not line terminated")
    try:
        _date_digits(opener.group(2), label="SEC-DOCUMENT opener date")
        _header_identity(raw[header_start:header_end], target)
    except SecCompleteSubmissionError as exc:
        raise CampaignError(str(exc)) from exc


def _state(inventory: dict[str, object], events: list[dict[str, object]],
           output: Path, *, object_reader: Callable[[str, int], bytes] | None = None
           ) -> tuple[list[dict[str, object]], dict[str, int],
                                  dict[str, object] | None, dict[str, object] | None,
                                  str | None]:
    requests = inventory["requests"]
    reuses = {row["accession_number"]: row for row in inventory["reuses"]}
    completed: list[dict[str, object]] = []
    attempts: dict[str, int] = {}
    pending_start: dict[str, object] | None = None
    pending_valid: dict[str, object] | None = None
    terminal: str | None = None
    ordinal = 0
    for event in events:
        if (type(event) is not dict or terminal is not None
                or len(completed) >= len(requests)):
            _refuse("event follows terminal or complete shard")
        request = requests[len(completed)]
        accession = request["accession_number"]
        if event.get("accession_number") != accession:
            _refuse("event differs from ordered campaign request")
        kind = event.get("kind")
        if kind == "attempt-start":
            ordinal += 1
            count = attempts.get(accession, 0) + 1
            if (pending_start is not None or pending_valid is not None
                    or accession in reuses or count > MAX_ATTEMPTS
                    or ordinal > len(requests) * MAX_ATTEMPTS
                    or set(event) != {"kind", "prev_sha256", "accession_number",
                                      "ordinal", "attempt", "url", "started_utc"}
                    or event["ordinal"] != ordinal or event["attempt"] != count
                    or event["url"] != request["url"]):
                _refuse("attempt reservation differs from campaign plan or cap")
            _check_utc(event["started_utc"])
            attempts[accession] = count
            pending_start = event
        elif kind == "attempt-finish":
            if (pending_start is None or pending_valid is not None
                    or set(event) != {"kind", "prev_sha256", "accession_number",
                                      "ordinal", "outcome", "status", "body_sha256",
                                      "body_size_bytes", "finished_utc"}
                    or event["ordinal"] != pending_start["ordinal"]):
                _refuse("attempt finish lacks exact reservation")
            _check_utc(event["finished_utc"])
            outcome = event["outcome"]
            if outcome == "valid_response":
                if (event["status"] != 200 or type(event["body_sha256"]) is not str
                        or _SHA.fullmatch(event["body_sha256"]) is None
                        or type(event["body_size_bytes"]) is not int
                        or not 0 < event["body_size_bytes"] <= MAX_COMPLETE_TXT_BYTES):
                    _refuse("valid response descriptor changed")
                pending_valid = event
            elif outcome == "network_error":
                if any(event[name] is not None for name in
                       ("status", "body_sha256", "body_size_bytes")):
                    _refuse("network error carries response bytes")
            elif outcome == "http_error":
                status = event["status"]
                if (type(status) is not int or status == 200
                        or event["body_sha256"] is not None
                        or event["body_size_bytes"] is not None):
                    _refuse("HTTP error descriptor changed")
                if status not in _RETRY_HTTP:
                    terminal = "REFUSED: SEC returned a terminal HTTP status"
            elif outcome in {"transport_refusal", "source_envelope_refusal"}:
                if (event["status"] != (200 if outcome == "source_envelope_refusal" else None)
                        or event["body_sha256"] is not None
                        or event["body_size_bytes"] is not None):
                    _refuse("transport or source-envelope refusal changed")
                terminal = "REFUSED: SEC response is not a valid bounded parent"
            else:
                _refuse("unknown attempt outcome")
            pending_start = None
        elif kind == "attempt-abandoned":
            if (pending_start is None or pending_valid is not None
                    or set(event) != {"kind", "prev_sha256", "accession_number", "ordinal"}
                    or event["ordinal"] != pending_start["ordinal"]):
                _refuse("abandoned attempt lacks exact reservation")
            pending_start = None
        elif kind == "response-object-missing":
            if (pending_valid is None or pending_start is not None
                    or set(event) != {"kind", "prev_sha256", "accession_number", "ordinal"}
                    or event["ordinal"] != pending_valid["ordinal"]):
                _refuse("missing response object lacks valid response")
            pending_valid = None
        elif kind == "item-complete":
            if (pending_start is not None
                    or set(event) != {"kind", "prev_sha256", "accession_number",
                                      "source", "object_sha256", "object_size_bytes",
                                      "prior_report_sha256"}):
                _refuse("completed item event is malformed")
            if event["source"] == "acquired":
                if (pending_valid is None
                        or event["object_sha256"] != pending_valid["body_sha256"]
                        or event["object_size_bytes"] != pending_valid["body_size_bytes"]
                        or event["prior_report_sha256"] is not None):
                    _refuse("acquired object differs from valid response")
            elif event["source"] == "reused":
                prior = reuses.get(accession)
                if (pending_valid is not None or prior is None
                        or event["object_sha256"] != prior["object_sha256"]
                        or event["object_size_bytes"] != prior["object_size_bytes"]
                        or event["prior_report_sha256"] != prior["prior_report_sha256"]):
                    _refuse("reused object differs from pinned prior root")
            else:
                _refuse("completed item has unknown source")
            if object_reader is None:
                raw = _read_object(output, event["object_sha256"], event["object_size_bytes"])
            else:
                raw = object_reader(event["object_sha256"], event["object_size_bytes"])
            _validate_parent_header(raw, request)
            completed.append(event)
            pending_valid = None
        else:
            _refuse("event kind is unknown")
    return completed, attempts, pending_start, pending_valid, terminal


def _shard_report(inventory: dict[str, object], events: _Events,
                  completed: list[dict[str, object]], attempts: dict[str, int],
                  reason: str | None) -> dict[str, object]:
    rows = []
    for index, request in enumerate(inventory["requests"]):
        event = completed[index] if index < len(completed) else None
        row: dict[str, object] = {
            "accession_number": request["accession_number"],
            "period": request["period"],
            "attempts": attempts.get(request["accession_number"], 0),
            "status": "not_attempted",
        }
        if event is not None:
            row.update({
                "status": "raw_acquired_noncanonical", "source": event["source"],
                "raw_object": {
                    "relative_path": f'objects/{event["object_sha256"]}.bin',
                    "sha256": event["object_sha256"],
                    "size_bytes": event["object_size_bytes"],
                },
                "prior_report_sha256": event["prior_report_sha256"],
            })
        elif index == len(completed) and reason is not None:
            row.update({"status": "refused", "reason": reason})
        rows.append(row)
    journal = b"".join(events.raw)
    return {
        "kind": CAMPAIGN_VERSION + "/shard-report",
        "source_scope": inventory["source_scope"],
        "manifest_sha256": inventory["manifest_sha256"],
        "request_inventory_sha256": hash_payload(inventory["requests"]),
        "inventory_sha256": hash_bytes(_bytes(inventory)),
        "capture_git_commit_verified": inventory["capture_git_commit"],
        "name": inventory["name"], "start": inventory["start"],
        "attempt_journal_sha256": hash_bytes(journal),
        "attempt_event_count": len(events.raw),
        "attempt_count": sum(attempts.values()),
        "distinct_requested": len(attempts),
        "complete_count": len(completed),
        "reused_count": sum(item["source"] == "reused" for item in completed),
        "rows": rows, "halted_reason": reason,
        "complete_shard_raw_set_acquired": reason is None
        and len(completed) == len(inventory["requests"]),
        "source_authenticated": False, "quarter_population_complete": False,
        "canonical_evidence": False, "point_in_time_data": False,
        "outcome_looks": 0, "qc_jobs": 0,
    }


def _expected_shard_names(events: _Events, completed: list[dict[str, object]],
                          report_name: str | None = None,
                          committed: bool = False) -> tuple[set[str], set[str]]:
    expected = {"run.lock", "objects", "inventory.json"}
    expected.update(
        f"event-{index:06d}-{hash_bytes(raw)}.json"
        for index, raw in enumerate(events.raw, 1)
    )
    if report_name is not None:
        expected.update({"attempts.jsonl", report_name})
    if committed:
        expected.add("commit.json")
    objects = {event["object_sha256"] + ".bin" for event in completed}
    return expected, objects


def _check_shard_names(output: Path, events: _Events,
                       completed: list[dict[str, object]],
                       *, report_name: str | None = None,
                       committed: bool = False) -> None:
    expected, objects = _expected_shard_names(
        events, completed, report_name=report_name, committed=committed,
    )
    if set(os.listdir(output)) != expected or set(os.listdir(output / "objects")) != objects:
        _refuse("shard has missing or extra immutable members")


def _finalize_shard(output: Path, identity: tuple[int, int],
                    inventory: dict[str, object], events: _Events,
                    completed: list[dict[str, object]], attempts: dict[str, int],
                    reason: str | None) -> tuple[dict[str, object], str]:
    report = _shard_report(inventory, events, completed, attempts, reason)
    journal = b"".join(events.raw)
    _publish_same_or_new(output, "attempts.jsonl", journal, identity,
                         cap=MAX_SHARD_JOURNAL_BYTES)
    raw = _bytes(report)
    digest = hash_bytes(raw)
    report_name = f"shard-report-{digest}.json"
    _publish_same_or_new(output, report_name, raw, identity,
                         cap=MAX_SHARD_REPORT_BYTES)
    commit = {"kind": CAMPAIGN_VERSION + "/shard-commit",
              "report_name": report_name, "report_sha256": digest,
              "inventory_sha256": report["inventory_sha256"],
              "attempt_journal_sha256": report["attempt_journal_sha256"]}
    _publish_same_or_new(output, "commit.json", _bytes(commit), identity, cap=4096)
    _check_shard_names(output, events, completed,
                       report_name=report_name, committed=True)
    return report, digest


def _verify_committed_shard(output: Path, inventory: dict[str, object],
                            events: _Events, completed: list[dict[str, object]],
                            attempts: dict[str, int], terminal: str | None
                            ) -> tuple[dict[str, object], str]:
    report = _shard_report(inventory, events, completed, attempts, terminal)
    raw = _bytes(report)
    digest = hash_bytes(raw)
    report_name = f"shard-report-{digest}.json"
    expected_commit = {"kind": CAMPAIGN_VERSION + "/shard-commit",
                       "report_name": report_name, "report_sha256": digest,
                       "inventory_sha256": report["inventory_sha256"],
                       "attempt_journal_sha256": report["attempt_journal_sha256"]}
    commit = _json(_recover(output / "commit.json", label="shard commit",
                            max_bytes=4096), label="shard commit")
    if commit != expected_commit:
        _refuse("shard commit differs from replayed source")
    _recover(output / "attempts.jsonl", label="shard journal",
             max_bytes=MAX_SHARD_JOURNAL_BYTES, expected_raw=b"".join(events.raw))
    _recover(output / report_name, label="shard report",
             max_bytes=MAX_SHARD_REPORT_BYTES, expected_raw=raw)
    _check_shard_names(output, events, completed,
                       report_name=report_name, committed=True)
    return report, digest


def _run_shard(
    campaign_root: Path, campaign_identity: tuple[int, int],
    inventory: dict[str, object], inventory_raw: bytes,
    transport: Callable[[str, dict[str, str], int], SecHttpResult],
    reuse_reader: Callable[[dict[str, object]], bytes],
    *, contact_email: str, resume: bool, used_bytes: int,
    last_completion_ns: int | None,
) -> tuple[dict[str, object], str, int, int | None]:
    output = campaign_root / inventory["name"]
    exists = output.exists() or output.is_symlink()
    if exists and not resume:
        _refuse("new campaign shard already exists")
    if not exists:
        output.mkdir(mode=0o700)
    current = output.lstat()
    if not stat.S_ISDIR(current.st_mode):
        _refuse("campaign shard root is not a directory")
    identity = (current.st_dev, current.st_ino)
    prior_names = set(os.listdir(output)) if exists else set()
    populated = bool(prior_names)
    lock = _RootLock(output, identity, resume=populated)
    try:
        if "inventory.json" in prior_names:
            _recover(output / "inventory.json", label="shard inventory",
                     max_bytes=MAX_SHARD_INVENTORY_BYTES, expected_raw=inventory_raw)
            _plain_path(output / "objects", must_exist=True)
        else:
            if prior_names not in (set(), {"run.lock"}, {"run.lock", "objects"}):
                _refuse("pre-inventory shard has unexpected members")
            if "objects" in prior_names:
                _plain_path(output / "objects", must_exist=True)
                if os.listdir(output / "objects"):
                    _refuse("pre-inventory shard object directory is not empty")
            else:
                (output / "objects").mkdir(mode=0o700)
            _publish_immutable(output, "inventory.json", inventory_raw, identity)
        events = _Events(output, identity, hash_bytes(inventory_raw))
        try:
            prior = events.load() if "inventory.json" in prior_names else []
        except SecSelectedParentRunnerError as exc:
            raise CampaignError("REFUSED: shard event replay changed") from exc
        completed, attempts, pending_start, pending_valid, terminal = _state(
            inventory, prior, output,
        )
        if (output / "commit.json").exists():
            if pending_start is not None or pending_valid is not None:
                _refuse("committed shard has unfinished attempt")
            report, digest = _verify_committed_shard(
                output, inventory, events, completed, attempts, terminal,
            )
            if not report["complete_shard_raw_set_acquired"]:
                _refuse("terminal incomplete shard cannot be resumed")
            return report, digest, used_bytes + sum(
                item["object_size_bytes"] for item in completed
            ), last_completion_ns
        if pending_start is not None:
            events.append({"kind": "attempt-abandoned",
                           "accession_number": pending_start["accession_number"],
                           "ordinal": pending_start["ordinal"]})
        if pending_valid is not None:
            digest = pending_valid["body_sha256"]
            object_path = output / "objects" / f"{digest}.bin"
            if object_path.exists() or object_path.is_symlink():
                _read_object(output, digest, pending_valid["body_size_bytes"])
                events.append({"kind": "item-complete",
                               "accession_number": pending_valid["accession_number"],
                               "source": "acquired", "object_sha256": digest,
                               "object_size_bytes": pending_valid["body_size_bytes"],
                               "prior_report_sha256": None})
            else:
                events.append({"kind": "response-object-missing",
                               "accession_number": pending_valid["accession_number"],
                               "ordinal": pending_valid["ordinal"]})
        replay = [_json(raw, label="campaign event") for raw in events.raw]
        completed, attempts, _, _, terminal = _state(inventory, replay, output)
        if populated and terminal is None and len(completed) < len(inventory["requests"]):
            # A new process has no comparable monotonic clock. This wait is
            # deliberately longer than the cross-process pacing requirement.
            time.sleep(1.5)
        used_bytes += sum(item["object_size_bytes"] for item in completed)
        reason = terminal
        reuses = {item["accession_number"]: item for item in inventory["reuses"]}
        while reason is None and len(completed) < len(inventory["requests"]):
            request = inventory["requests"][len(completed)]
            accession = request["accession_number"]
            reuse = reuses.get(accession)
            if not _capacity_ok(campaign_root, campaign_identity, used_bytes):
                _refuse("capacity pause before parent publication or SEC dispatch")
            if reuse is not None:
                raw = reuse_reader(reuse)
                if (type(raw) is not bytes or len(raw) != reuse["object_size_bytes"]
                        or hash_bytes(raw) != reuse["object_sha256"]):
                    _refuse("prior selected object changed before reuse")
                _validate_parent_header(raw, request)
                descriptor = _store_object(output, raw, identity)
                events.append({"kind": "item-complete", "accession_number": accession,
                               "source": "reused", "object_sha256": descriptor["sha256"],
                               "object_size_bytes": descriptor["size_bytes"],
                               "prior_report_sha256": reuse["prior_report_sha256"]})
                completed.append(_json(events.raw[-1], label="campaign event"))
                used_bytes += len(raw)
                continue
            attempt = attempts.get(accession, 0) + 1
            if attempt > MAX_ATTEMPTS:
                reason = "REFUSED: parent attempt ceiling consumed"
                break
            now = time.monotonic_ns()
            earliest = max(now, last_completion_ns + MIN_REQUEST_INTERVAL_NS
                           if last_completion_ns is not None else now)
            if attempt > 1:
                earliest = max(earliest, now + (attempt - 1) * 1_000_000_000)
            remaining = earliest - time.monotonic_ns()
            if remaining > 0:
                time.sleep(remaining / 1_000_000_000)
            ordinal = sum(attempts.values()) + 1
            events.append({"kind": "attempt-start", "accession_number": accession,
                           "ordinal": ordinal, "attempt": attempt,
                           "url": request["url"], "started_utc": _utc()})
            if time.monotonic_ns() < earliest:
                _refuse("actual SEC dispatch pacing was too early")
            headers = {"User-Agent": f"InsiderBuyingResearch/0.1 ({contact_email})",
                       "Accept": "*/*", "Accept-Encoding": "identity",
                       "Connection": "close"}
            try:
                result = transport(request["url"], headers, MAX_COMPLETE_TXT_BYTES)
            except (OSError, http.client.HTTPException):
                last_completion_ns = time.monotonic_ns()
                events.append({"kind": "attempt-finish", "accession_number": accession,
                               "ordinal": ordinal, "outcome": "network_error",
                               "status": None, "body_sha256": None,
                               "body_size_bytes": None, "finished_utc": _utc()})
                attempts[accession] = attempt
                continue
            except SecCompleteAcquisitionError:
                last_completion_ns = time.monotonic_ns()
                events.append({"kind": "attempt-finish", "accession_number": accession,
                               "ordinal": ordinal, "outcome": "transport_refusal",
                               "status": None, "body_sha256": None,
                               "body_size_bytes": None, "finished_utc": _utc()})
                attempts[accession] = attempt
                reason = "REFUSED: SEC transport rejected response framing"
                break
            last_completion_ns = time.monotonic_ns()
            if type(result) is not SecHttpResult or type(result.status) is not int:
                events.append({"kind": "attempt-finish", "accession_number": accession,
                               "ordinal": ordinal, "outcome": "transport_refusal",
                               "status": None, "body_sha256": None,
                               "body_size_bytes": None, "finished_utc": _utc()})
                attempts[accession] = attempt
                reason = "REFUSED: SEC transport rejected response framing"
                break
            if result.status != 200:
                events.append({"kind": "attempt-finish", "accession_number": accession,
                               "ordinal": ordinal, "outcome": "http_error",
                               "status": result.status, "body_sha256": None,
                               "body_size_bytes": None, "finished_utc": _utc()})
                attempts[accession] = attempt
                if result.status not in _RETRY_HTTP:
                    reason = "REFUSED: SEC returned a terminal HTTP status"
                continue
            try:
                raw = _strict_selected_response(result, max_bytes=MAX_COMPLETE_TXT_BYTES)
            except SecCompleteAcquisitionError:
                events.append({"kind": "attempt-finish", "accession_number": accession,
                               "ordinal": ordinal, "outcome": "transport_refusal",
                               "status": None, "body_sha256": None,
                               "body_size_bytes": None, "finished_utc": _utc()})
                attempts[accession] = attempt
                reason = "REFUSED: SEC transport rejected response framing"
                break
            try:
                _validate_parent_header(raw, request)
            except CampaignError:
                events.append({"kind": "attempt-finish", "accession_number": accession,
                               "ordinal": ordinal, "outcome": "source_envelope_refusal",
                               "status": 200, "body_sha256": None,
                               "body_size_bytes": None, "finished_utc": _utc()})
                attempts[accession] = attempt
                reason = "REFUSED: SEC response is not a valid bounded parent"
                break
            digest = hash_bytes(raw)
            events.append({"kind": "attempt-finish", "accession_number": accession,
                           "ordinal": ordinal, "outcome": "valid_response",
                           "status": 200, "body_sha256": digest,
                           "body_size_bytes": len(raw), "finished_utc": _utc()})
            attempts[accession] = attempt
            descriptor = _store_object(output, raw, identity)
            events.append({"kind": "item-complete", "accession_number": accession,
                           "source": "acquired", "object_sha256": descriptor["sha256"],
                           "object_size_bytes": descriptor["size_bytes"],
                           "prior_report_sha256": None})
            completed.append(_json(events.raw[-1], label="campaign event"))
            used_bytes += len(raw)
        replay = [_json(raw, label="campaign event") for raw in events.raw]
        checked, final_attempts, pending_start, pending_valid, terminal = _state(
            inventory, replay, output,
        )
        if (checked != completed or pending_start is not None or pending_valid is not None
                or (reason is not None and terminal not in {None, reason})):
            _refuse("final shard journal differs from in-memory state")
        if inventory["source_scope"] == "ib1b_observed_full_form4_noncanonical":
            _verify_exact_committed_code(inventory["capture_git_commit"])
        report, digest = _finalize_shard(output, identity, inventory, events,
                                         checked, final_attempts, reason)
        if not report["complete_shard_raw_set_acquired"]:
            _refuse("shard ended incomplete; campaign cannot advance")
        return report, digest, used_bytes, last_completion_ns
    finally:
        lock.close()


def _campaign_report(
    plan: CampaignPlan, plan_raw: bytes, capture_git_commit: str,
    shard_summaries: list[dict[str, object]], used_bytes: int,
) -> dict[str, object]:
    complete = sum(row["count"] for row in shard_summaries)
    reused = sum(row["reused_count"] for row in shard_summaries)
    attempts = sum(row["attempt_count"] for row in shard_summaries)
    if (complete != len(plan.requests) or reused != len(plan.reuses)
            or used_bytes > MAX_RUN_OBJECT_BYTES
            or attempts > MAX_ATTEMPTS * (complete - reused)):
        _refuse("final shard union or global budget differs from campaign plan")
    return {
        "kind": CAMPAIGN_VERSION + "/campaign-report",
        "source_scope": plan.scope,
        "manifest_sha256": plan.manifest_sha256,
        "request_inventory_sha256": plan.to_payload()["request_inventory_sha256"],
        "campaign_plan_sha256": hash_bytes(plan_raw),
        "selected_report_sha256": plan.selected_report_sha256,
        "selected_receipt_lineage_sha256": plan.selected_receipt_lineage_sha256,
        "capture_git_commit_verified": capture_git_commit,
        "total_accessions": len(plan.requests),
        "complete_count": complete,
        "reused_count": reused,
        "newly_acquired_count": complete - reused,
        "attempt_count": attempts,
        "shard_count": len(shard_summaries), "shards": shard_summaries,
        "stored_parent_bytes": used_bytes,
        "complete_all_form4_parent_raw_set_acquired": True,
        "source_authenticated": False,
        "quarter_population_complete": False,
        "acceptance_metadata_verified": False,
        "canonical_evidence": False,
        "point_in_time_data": False,
        "qc_job_authorized": False,
        "outcome_access_authorized": False,
        "broker_or_trading_authorized": False,
        "research_looks": 0, "consumed_outcome_looks": 0,
        "qc_jobs": 0,
    }


class _ReadOnlyDirectory:
    """Pinned, single-link-only reads; unlike resume recovery, never unlinks."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.descriptor: int | None = None

    def __enter__(self) -> _ReadOnlyDirectory:
        try:
            self.descriptor = os.open(
                self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
            self.check()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, _type: object, _value: object, _trace: object) -> None:
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None

    def check(self) -> None:
        if self.descriptor is None:
            _refuse("read-only campaign directory handle is closed")
        named = self.path.lstat()
        opened = os.fstat(self.descriptor)
        if (not stat.S_ISDIR(named.st_mode)
                or (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino)):
            _refuse("read-only campaign directory path changed")

    def names(self) -> set[str]:
        self.check()
        names = os.listdir(self.descriptor)
        self.check()
        if len(names) != len(set(names)):
            _refuse("campaign directory repeats a filename")
        return set(names)

    def read(self, name: str, *, max_bytes: int) -> bytes:
        if (type(name) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name) is None
                or type(max_bytes) is not int or max_bytes <= 0):
            _refuse("read-only campaign file request is malformed")
        self.check()
        try:
            descriptor = os.open(
                name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
                dir_fd=self.descriptor,
            )
            try:
                before = os.fstat(descriptor)
                if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                        or not 0 < before.st_size <= max_bytes):
                    _refuse("read-only campaign file is not bounded and single-link")
                chunks: list[bytes] = []
                remaining = max_bytes + 1
                while remaining:
                    part = os.read(descriptor, remaining)
                    if not part:
                        break
                    chunks.append(part)
                    remaining -= len(part)
                raw = b"".join(chunks)
                after = os.fstat(descriptor)
            finally:
                os.close(descriptor)
            named = os.stat(name, dir_fd=self.descriptor, follow_symlinks=False)
        except OSError as exc:
            raise CampaignError("REFUSED: read-only campaign file could not be read") from exc
        self.check()
        fields = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if (not stat.S_ISREG(named.st_mode) or named.st_nlink != 1
                or fields(before) != fields(after) or fields(after) != fields(named)
                or len(raw) != after.st_size):
            _refuse("read-only campaign file changed during replay")
        return raw


def _run_campaign(
    plan: CampaignPlan, output_root: str | Path,
    transport: Callable[[str, dict[str, str], int], SecHttpResult],
    reuse_reader: Callable[[dict[str, object]], bytes],
    *, contact_email: str, capture_git_commit: str, resume: bool,
) -> Path:
    if (type(contact_email) is not str or _CONTACT.fullmatch(contact_email) is None
            or len(contact_email) > 254 or any(ord(char) > 127 for char in contact_email)):
        _refuse("SEC contact email is malformed")
    if type(capture_git_commit) is not str or _COMMIT.fullmatch(capture_git_commit) is None:
        _refuse("campaign capture commit is malformed")
    if type(resume) is not bool or not callable(transport) or not callable(reuse_reader):
        _refuse("campaign execution interface is malformed")
    if plan.scope == "ib1b_observed_full_form4_noncanonical":
        if transport is not _selected_sec_transport:
            _refuse("real campaign transport differs from the reviewed SEC client")
        _verify_exact_committed_code(capture_git_commit)
    elif transport is _selected_sec_transport:
        _refuse("synthetic campaign cannot use the SEC transport")
    shards = _shards(plan, capture_git_commit)
    plan_raw = _campaign_plan(plan, capture_git_commit, shards)
    output = _plain_path(output_root, must_exist=resume)
    lane_root = Path(__file__).resolve().parents[1]
    _refuse_output_overlap(output, lane_root)
    if resume:
        info = output.lstat()
    else:
        if output.exists() or output.is_symlink():
            _refuse("new campaign output root already exists")
        output.mkdir(mode=0o700)
        info = output.lstat()
    if not stat.S_ISDIR(info.st_mode):
        _refuse("campaign output root is not a directory")
    identity = (info.st_dev, info.st_ino)
    prior_names = set(os.listdir(output)) if resume else set()
    populated = bool(prior_names)
    lock = _RootLock(output, identity, resume=populated)
    try:
        if "campaign-plan.json" in prior_names:
            _recover(output / "campaign-plan.json", label="campaign plan",
                     max_bytes=MAX_CAMPAIGN_PLAN_BYTES, expected_raw=plan_raw)
        else:
            if prior_names not in (set(), {"run.lock"}):
                _refuse("pre-plan campaign root has unexpected members")
            _publish_immutable(output, "campaign-plan.json", plan_raw, identity)
        if (output / "commit.json").exists():
            _refuse("completed campaign cannot be relaunched")
        expected_shard_names = {inventory["name"] for inventory, _ in shards}
        current_names = set(os.listdir(output))
        if (not current_names <= {"run.lock", "campaign-plan.json"}
                | expected_shard_names | {
                    name for name in current_names
                    if re.fullmatch(r"campaign-report-[0-9a-f]{64}\.json", name)
                }
                or sum(name.startswith("campaign-report-") for name in current_names) > 1):
            _refuse("campaign root has unexpected members")
        used_bytes = 0
        last_completion_ns: int | None = None
        shard_summaries: list[dict[str, object]] = []
        total_completed = total_reused = total_attempts = 0
        if resume:
            # A new process has no clock comparable with the last process's
            # monotonic completion time, including across shard boundaries.
            time.sleep(1.5)
        for inventory, raw in shards:
            report, digest, used_bytes, last_completion_ns = _run_shard(
                output, identity, inventory, raw, transport, reuse_reader,
                contact_email=contact_email, resume=resume,
                used_bytes=used_bytes, last_completion_ns=last_completion_ns,
            )
            if not report["complete_shard_raw_set_acquired"]:
                _refuse("campaign shard is incomplete")
            total_completed += report["complete_count"]
            total_reused += report["reused_count"]
            total_attempts += report["attempt_count"]
            shard_summaries.append({
                "name": inventory["name"], "start": inventory["start"],
                "count": inventory["count"], "reused_count": report["reused_count"],
                "attempt_count": report["attempt_count"],
                "report_sha256": digest,
                "inventory_sha256": hash_bytes(raw),
            })
        if plan.scope == "ib1b_observed_full_form4_noncanonical":
            _verify_exact_committed_code(capture_git_commit)
        report = _campaign_report(
            plan, plan_raw, capture_git_commit, shard_summaries, used_bytes,
        )
        report_raw = _bytes(report)
        report_sha = hash_bytes(report_raw)
        report_name = f"campaign-report-{report_sha}.json"
        _publish_same_or_new(output, report_name, report_raw, identity,
                             cap=MAX_CAMPAIGN_PLAN_BYTES)
        commit = {"kind": CAMPAIGN_VERSION + "/campaign-commit",
                  "report_name": report_name, "report_sha256": report_sha,
                  "plan_sha256": hash_bytes(plan_raw)}
        _publish_same_or_new(output, "commit.json", _bytes(commit), identity, cap=4096)
        if set(os.listdir(output)) != (
            {"run.lock", "campaign-plan.json", report_name, "commit.json"}
            | expected_shard_names
        ):
            _refuse("final campaign root has unexpected members")
        return output / report_name
    finally:
        lock.close()


def run_synthetic_campaign(
    plan: CampaignPlan, output_root: str | Path,
    *, transport: Callable[[str, dict[str, str], int], SecHttpResult],
    reused_bytes: Mapping[str, bytes] | None = None,
    contact_email: str, capture_git_commit: str, resume: bool = False,
) -> Path:
    """Synthetic injected-transport verification; never an SEC source run."""
    if type(plan) is not CampaignPlan or plan.scope != "synthetic_test_manifest":
        _refuse("synthetic entry requires a synthetic-only plan")
    if type(reused_bytes) is not dict and reused_bytes is not None:
        _refuse("synthetic reused bytes must be an exact mapping")
    supplied = dict(reused_bytes or {})
    if set(supplied) != {item.accession_number for item in plan.reuses}:
        _refuse("synthetic reused object set differs from plan")

    def read_reused(descriptor: dict[str, object]) -> bytes:
        return supplied[descriptor["accession_number"]]

    return _run_campaign(
        plan, output_root, transport, read_reused,
        contact_email=contact_email, capture_git_commit=capture_git_commit,
        resume=resume,
    )


def run_observed_all_form4_parent_campaign(
    raw_q4_directory: str | Path, parsed_q4_directory: str | Path,
    raw_q1_directory: str | Path, parsed_q1_directory: str | Path,
    exact16_pilot_root: str | Path, selected_root: str | Path,
    output_root: str | Path,
    *, contact_email: str, capture_git_commit: str, resume: bool = False,
) -> Path:
    """Explicit real SEC entry; no module import or preflight can dispatch."""
    _verify_exact_committed_code(capture_git_commit)
    plan = _build_real_plan(
        raw_q4_directory, parsed_q4_directory, raw_q1_directory,
        parsed_q1_directory, exact16_pilot_root, selected_root,
    )
    selected = _plain_path(selected_root, must_exist=True)
    output = _plain_path(output_root, must_exist=resume)
    for protected in (
        _plain_path(raw_q4_directory, must_exist=True),
        _plain_path(parsed_q4_directory, must_exist=True),
        _plain_path(raw_q1_directory, must_exist=True),
        _plain_path(parsed_q1_directory, must_exist=True),
        _plain_path(exact16_pilot_root, must_exist=True), selected,
    ):
        _refuse_output_overlap(output, protected)
    with _PinnedRoot(selected) as pinned:
        def read_reused(descriptor: dict[str, object]) -> bytes:
            raw = pinned.read(
                f'objects/{descriptor["object_sha256"]}.bin',
                label="selected reusable object", max_bytes=MAX_COMPLETE_TXT_BYTES,
            )
            if (len(raw) != descriptor["object_size_bytes"]
                    or hash_bytes(raw) != descriptor["object_sha256"]):
                _refuse("selected reusable object changed")
            return raw

        return _run_campaign(
            plan, output, _selected_sec_transport, read_reused,
            contact_email=contact_email, capture_git_commit=capture_git_commit,
            resume=resume,
        )


def _verify_completed_campaign(
    plan: CampaignPlan, output_root: str | Path,
    *, capture_git_commit: str,
) -> dict[str, object]:
    """Independently replay every immutable byte without recovery or network."""
    if type(capture_git_commit) is not str or _COMMIT.fullmatch(capture_git_commit) is None:
        _refuse("replay capture commit is malformed")
    shards = _shards(plan, capture_git_commit)
    plan_raw = _campaign_plan(plan, capture_git_commit, shards)
    output = _plain_path(output_root, must_exist=True)
    summaries: list[dict[str, object]] = []
    used_bytes = 0
    with _ReadOnlyDirectory(output) as top:
        if top.read("campaign-plan.json", max_bytes=MAX_CAMPAIGN_PLAN_BYTES) != plan_raw:
            _refuse("read-only campaign plan differs from source-bound replay")
        for inventory, inventory_raw in shards:
            shard_path = _plain_path(output / inventory["name"], must_exist=True)
            with _PinnedRoot(shard_path) as pinned:
                if pinned.read("inventory.json", label="shard inventory",
                               max_bytes=MAX_SHARD_INVENTORY_BYTES) != inventory_raw:
                    _refuse("read-only shard inventory differs from source-bound plan")
                names = pinned.names()
                numbered: list[tuple[int, str]] = []
                for name in names:
                    if not name.startswith("event-"):
                        continue
                    match = re.fullmatch(r"event-([0-9]{6})-([0-9a-f]{64})\.json", name)
                    if match is None:
                        _refuse("read-only shard event name is malformed")
                    numbered.append((int(match.group(1)), name))
                numbered.sort()
                if (len(numbered) > _MAX_EVENTS
                        or [number for number, _ in numbered]
                        != list(range(1, len(numbered) + 1))):
                    _refuse("read-only shard event sequence is incomplete")
                chain = hash_bytes(inventory_raw)
                event_raw: list[bytes] = []
                parsed: list[dict[str, object]] = []
                for _, name in numbered:
                    raw = pinned.read(name, label="campaign event",
                                      max_bytes=_MAX_EVENT_BYTES)
                    if hash_bytes(raw) != name[-69:-5]:
                        _refuse("read-only shard event digest changed")
                    event = _json(raw, label="campaign event")
                    if event.get("prev_sha256") != chain:
                        _refuse("read-only shard event hash chain changed")
                    event_raw.append(raw)
                    parsed.append(event)
                    chain = hash_bytes(raw)
                def object_reader(digest: str, size: int) -> bytes:
                    if (type(digest) is not str or _SHA.fullmatch(digest) is None
                            or type(size) is not int
                            or not 0 < size <= MAX_COMPLETE_TXT_BYTES):
                        _refuse("read-only object descriptor is malformed")
                    raw = pinned.read(
                        f"objects/{digest}.bin", label="campaign parent object",
                        max_bytes=MAX_COMPLETE_TXT_BYTES,
                    )
                    if (len(raw) != size or hash_bytes(raw) != digest
                            or not raw.startswith(b"<SEC-DOCUMENT>")):
                        _refuse("read-only parent bytes differ from journal")
                    return raw
                completed, attempts, pending_start, pending_valid, terminal = _state(
                    inventory, parsed, shard_path, object_reader=object_reader,
                )
                if (pending_start is not None or pending_valid is not None
                        or terminal is not None
                        or len(completed) != inventory["count"]):
                    _refuse("read-only shard replay is incomplete")
                events = _Events(shard_path, (0, 0), hash_bytes(inventory_raw))
                events.raw = event_raw
                report = _shard_report(inventory, events, completed, attempts, None)
                report_raw = _bytes(report)
                report_sha = hash_bytes(report_raw)
                report_name = f"shard-report-{report_sha}.json"
                if (pinned.read("attempts.jsonl", label="shard journal",
                                max_bytes=MAX_SHARD_JOURNAL_BYTES) != b"".join(event_raw)
                        or pinned.read(report_name, label="shard report",
                                       max_bytes=MAX_SHARD_REPORT_BYTES) != report_raw):
                    _refuse("read-only shard journal or report differs from replay")
                expected_commit = {
                    "kind": CAMPAIGN_VERSION + "/shard-commit",
                    "report_name": report_name, "report_sha256": report_sha,
                    "inventory_sha256": hash_bytes(inventory_raw),
                    "attempt_journal_sha256": hash_bytes(b"".join(event_raw)),
                }
                if _json(pinned.read("commit.json", label="shard commit",
                                     max_bytes=4096), label="shard commit") != expected_commit:
                    _refuse("read-only shard commit differs from replay")
                expected_names, expected_objects = _expected_shard_names(
                    events, completed, report_name=report_name, committed=True,
                )
                if names != expected_names or pinned.names(objects=True) != expected_objects:
                    _refuse("read-only shard has missing or extra members")
                used_bytes += sum(item["object_size_bytes"] for item in completed)
                summaries.append({
                    "name": inventory["name"], "start": inventory["start"],
                    "count": inventory["count"],
                    "reused_count": report["reused_count"],
                    "attempt_count": report["attempt_count"],
                    "report_sha256": report_sha,
                    "inventory_sha256": hash_bytes(inventory_raw),
                })
        report = _campaign_report(
            plan, plan_raw, capture_git_commit, summaries, used_bytes,
        )
        report_raw = _bytes(report)
        report_sha = hash_bytes(report_raw)
        report_name = f"campaign-report-{report_sha}.json"
        if top.read(report_name, max_bytes=MAX_CAMPAIGN_PLAN_BYTES) != report_raw:
            _refuse("read-only campaign report differs from shard union")
        commit = _json(top.read("commit.json", max_bytes=4096), label="campaign commit")
        if commit != {
            "kind": CAMPAIGN_VERSION + "/campaign-commit",
            "report_name": report_name, "report_sha256": report_sha,
            "plan_sha256": hash_bytes(plan_raw),
        }:
            _refuse("read-only campaign commit differs from shard union")
        if top.names() != (
            {"run.lock", "campaign-plan.json", report_name, "commit.json"}
            | {inventory["name"] for inventory, _ in shards}
        ):
            _refuse("read-only campaign root has missing or extra members")
    return {
        "manifest_sha256": plan.manifest_sha256, "report_sha256": report_sha,
        "total_accessions": report["total_accessions"],
        "complete_count": report["complete_count"],
        "reused_count": report["reused_count"],
        "newly_acquired_count": report["newly_acquired_count"],
        "attempt_count": report["attempt_count"],
        "shard_count": report["shard_count"],
        "source_authenticated": False, "quarter_population_complete": False,
        "canonical_evidence": False, "point_in_time_data": False,
        "research_looks": 0, "qc_jobs": 0,
    }


def verify_completed_synthetic_campaign(
    plan: CampaignPlan, output_root: str | Path,
    *, capture_git_commit: str,
) -> dict[str, object]:
    """Read-only replay for the invented-source test boundary."""
    if type(plan) is not CampaignPlan or plan.scope != "synthetic_test_manifest":
        _refuse("synthetic replay requires a synthetic-only plan")
    return _verify_completed_campaign(
        plan, output_root, capture_git_commit=capture_git_commit,
    )


def load_observed_all_form4_parent_campaign(
    raw_q4_directory: str | Path, parsed_q4_directory: str | Path,
    raw_q1_directory: str | Path, parsed_q1_directory: str | Path,
    exact16_pilot_root: str | Path, selected_root: str | Path,
    output_root: str | Path, *, capture_git_commit: str,
) -> dict[str, object]:
    """Real-source, read-only completed-root replay; never dispatches SEC."""
    plan = _build_real_plan(
        raw_q4_directory, parsed_q4_directory, raw_q1_directory,
        parsed_q1_directory, exact16_pilot_root, selected_root,
    )
    return _verify_completed_campaign(
        plan, output_root, capture_git_commit=capture_git_commit,
    )


__all__ = [
    "CampaignError", "CampaignRequest", "CampaignReuse", "CampaignPlan",
    "preflight_observed_all_form4_parent_campaign",
    "run_synthetic_campaign", "run_observed_all_form4_parent_campaign",
    "verify_completed_synthetic_campaign", "load_observed_all_form4_parent_campaign",
]
