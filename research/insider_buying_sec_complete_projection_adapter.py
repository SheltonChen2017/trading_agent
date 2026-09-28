"""Offline replay of the exact 16-submission SEC complete-text compatibility pilot.

This loader reads an already-published, content-addressed local root. It does
not request SEC data or publish an artifact. Hash agreement and journal replay
bind local bytes and recorded operations, not SEC authenticity, first public
availability, a canonical source, or permission to enter IB-1C.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import gzip
import io
import json
import os
from pathlib import Path
import re
import stat
import zlib

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying.sec_bulk_snapshot import (
    SecBulkSnapshotError,
    _require_regular_directory,
)
from research.insider_buying.sec_complete_submission import (
    MAX_COMPLETE_SUBMISSION_BYTES,
    SecCompleteSubmissionError,
    SecCompleteSubmissionProjection,
    SecCompleteSubmissionTarget,
    project_sec_complete_submission,
)
from research.insider_buying.sec_quarter_master_index import (
    MASTER_INDEX_PARSER_VERSION,
    MAX_MASTER_INDEX_BYTES,
    SecMasterIndexExpectedRow,
    SecQuarterMasterIndexError,
    parse_sec_quarter_master_index,
    select_sec_master_index_subset,
)


COMPLETE_PILOT_ADAPTER_VERSION = "INSETF-SEC-SIXTEEN-COMPLETE-OFFLINE-REPLAY-v1"
FINAL_REPORT_SHA256 = "e3f226683c7a6878f25e7efd8d87a8d81083e5a686308bd6ad20ec0298229421"
CAPTURE_CODE_COMMIT = "9ab2ed09e6a547feebb93bd5f9f8579bc7d15877"
INVENTORY_SHA256 = "4b8a4c3a233855ea2aa6cde0b2739a83aca478180ac881e1cf011943753d78db"
_ACQUISITION_VERSION = "INSETF-SEC-SIXTEEN-COMPLETE-TXT-v1"
_MASTER_URLS = {
    "2022Q4": "https://www.sec.gov/Archives/edgar/full-index/2022/QTR4/master.gz",
    "2023Q1": "https://www.sec.gov/Archives/edgar/full-index/2023/QTR1/master.gz",
}
_PERIODS = (("2022Q4", 2022, 4), ("2023Q1", 2023, 1))
FIXED_ACCESSIONS = (
    "0000002178-22-000091", "0000002178-22-000094", "0000002178-22-000095",
    "0000002178-22-000097", "0000002178-22-000099", "0000002488-22-000165",
    "0000050725-22-000079", "0000050725-22-000083",
    "0000002178-23-000019", "0000002178-23-000020", "0000002178-23-000021",
    "0000002178-23-000022", "0000002178-23-000023", "0000002178-23-000024",
    "0000016058-23-000011", "0000019745-23-000002",
)
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_CANDIDATE_KEYS = frozenset({
    "period", "accession_number", "form_type", "filing_date_raw", "filing_date",
    "issuer_cik", "quarterly_zip_sha256", "submission_row_id", "raw_snapshot_id",
    "raw_lineage_sha256",
})
_REPORT_KEYS = frozenset({
    "kind", "inventory_sha256", "capture_git_commit_verified", "master_indexes",
    "filings", "attempt_count", "distinct_artifact_count", "halted_reason",
    "complete_sample_acquired", "source_authenticated", "canonical_evidence",
    "point_in_time_data", "direct_ib1c_ingest_authorized",
    "official_sec_profile_verified", "outcome_access_authorized",
    "qc_job_authorized", "broker_or_trading_authorized", "research_looks",
    "authorized_outcome_looks", "consumed_outcome_looks", "attempt_journal",
})
_START_KEYS = frozenset({
    "kind", "ordinal", "url", "attempt", "max_response_bytes", "pacing_start_utc",
    "pacing_start_monotonic_ns", "pacing_end_utc", "pacing_end_monotonic_ns",
    "pacing_sleep_ns_requested", "pacing_basis", "reservation_start_utc",
    "reservation_start_monotonic_ns",
})
_FINISH_KEYS = frozenset({
    "kind", "ordinal", "request_end_utc", "request_end_monotonic_ns",
    "request_start_utc", "request_start_monotonic_ns", "outcome", "status",
    "body_size_bytes", "body_sha256",
})
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}\+00:00\Z")
_MAX_MASTER_GZIP = 8 * 1024 * 1024
_MAX_JOURNAL = 2 * 1024 * 1024
_LOADER_TOKEN = object()


class SecCompletePilotAdapterError(ValueError):
    """The fixed local pilot publication or replay failed closed."""


def _refuse(message: str) -> None:
    raise SecCompletePilotAdapterError(f"REFUSED: {message}")


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _refuse("JSON repeats a key")
        result[key] = value
    return result


def _non_json_constant(_: str) -> object:
    _refuse("JSON contains a non-JSON constant")


def _canonical_object(raw: bytes, *, label: str) -> dict[str, object]:
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"),
                           object_pairs_hook=_unique_pairs,
                           parse_constant=_non_json_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise SecCompletePilotAdapterError(f"REFUSED: {label} is not strict JSON") from exc
    if type(value) is not dict or (canonical_json(value) + "\n").encode("utf-8") != raw:
        _refuse(f"{label} is not canonical JSON plus one LF")
    return value


def _plain_root(value: str | Path) -> Path:
    if type(value) is not str and not isinstance(value, Path):
        _refuse("root must be an absolute path")
    root = Path(value)
    if not root.is_absolute() or ".." in root.parts:
        _refuse("root must be absolute and non-traversing")
    try:
        for component in (*reversed(root.parents), root):
            _require_regular_directory(component, label="complete pilot root or ancestor")
    except SecBulkSnapshotError as exc:
        raise SecCompletePilotAdapterError(str(exc)) from exc
    return root


class _PinnedRoot:
    """Hold directory handles so a renamed/symlinked path cannot redirect I/O."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.root_fd: int | None = None
        self.objects_fd: int | None = None

    def __enter__(self) -> _PinnedRoot:
        if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
            _refuse("directory-handle confinement is unavailable on this platform")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        current: int | None = None
        try:
            for index, component in enumerate(self.path.parts):
                opened = (os.open(component, flags) if index == 0 else
                          os.open(component, flags, dir_fd=current))
                if current is not None:
                    os.close(current)
                current = opened
            self.root_fd = current
            current = None
            if self.root_fd is None:
                _refuse("complete pilot root has no directory handle")
            self.objects_fd = os.open("objects", flags, dir_fd=self.root_fd)
            self.check()
            return self
        except (OSError, TypeError, NotImplementedError) as exc:
            self.__exit__(None, None, None)
            raise SecCompletePilotAdapterError(
                "REFUSED: complete pilot directory handle could not be pinned"
            ) from exc
        except BaseException:
            self.__exit__(None, None, None)
            raise
        finally:
            if current is not None:
                os.close(current)

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        if self.objects_fd is not None:
            os.close(self.objects_fd)
            self.objects_fd = None
        if self.root_fd is not None:
            os.close(self.root_fd)
            self.root_fd = None

    def check(self) -> None:
        if self.root_fd is None or self.objects_fd is None:
            _refuse("complete pilot directory handles are closed")
        try:
            for path, descriptor in ((self.path, self.root_fd),
                                     (self.path / "objects", self.objects_fd)):
                named = path.lstat()
                opened = os.fstat(descriptor)
                if (not stat.S_ISDIR(named.st_mode)
                        or (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino)):
                    _refuse("complete pilot directory path changed during replay")
        except OSError as exc:
            raise SecCompletePilotAdapterError(
                "REFUSED: complete pilot directory path became unreadable"
            ) from exc

    def names(self, *, objects: bool = False) -> set[str]:
        self.check()
        descriptor = self.objects_fd if objects else self.root_fd
        try:
            names = os.listdir(descriptor)
        except (OSError, TypeError, NotImplementedError) as exc:
            raise SecCompletePilotAdapterError(
                "REFUSED: pilot directory cannot be enumerated through its handle"
            ) from exc
        self.check()
        if len(names) != len(set(names)):
            _refuse("pilot directory repeats a filename")
        return set(names)

    def read(self, name: str, *, label: str, max_bytes: int) -> bytes:
        if type(name) is not str or type(max_bytes) is not int or max_bytes <= 0:
            _refuse("pilot file request is malformed")
        if name.startswith("objects/"):
            child = name[len("objects/"):]
            directory_fd = self.objects_fd
        else:
            child = name
            directory_fd = self.root_fd
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", child) is None:
            _refuse("pilot file request escapes its pinned directory")
        self.check()
        try:
            descriptor = os.open(child, os.O_RDONLY | os.O_NOFOLLOW
                                 | getattr(os, "O_NONBLOCK", 0),
                                 dir_fd=directory_fd)
            try:
                before = os.fstat(descriptor)
                if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                        or not 0 < before.st_size <= max_bytes):
                    _refuse(f"{label} is not a bounded regular single-link file")
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
            named = os.stat(child, dir_fd=directory_fd, follow_symlinks=False)
        except (OSError, TypeError, NotImplementedError) as exc:
            raise SecCompletePilotAdapterError(f"REFUSED: {label} could not be read") from exc
        self.check()
        if (not stat.S_ISREG(named.st_mode) or named.st_nlink != 1
                or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                != (named.st_dev, named.st_ino, named.st_size, named.st_mtime_ns)
                or len(raw) != after.st_size):
            _refuse(f"{label} changed while read through its pinned directory")
        return raw


def _names(root: _PinnedRoot, *, objects: bool = False) -> set[str]:
    names = root.names(objects=objects)
    if len(names) != len(set(names)):
        _refuse("pilot root repeats a filename")
    return names


def _read(root: _PinnedRoot, name: str, *, label: str, max_bytes: int) -> bytes:
    return root.read(name, label=label, max_bytes=max_bytes)


def _descriptor(root: _PinnedRoot, value: object, *, role: str, max_bytes: int) -> bytes:
    if (type(value) is not dict
            or set(value) != {"relative_path", "sha256", "size_bytes"}
            or type(value["sha256"]) is not str or _SHA.fullmatch(value["sha256"]) is None
            or type(value["size_bytes"]) is not int
            or not 0 < value["size_bytes"] <= max_bytes
            or value["relative_path"] != f'objects/{value["sha256"]}.bin'):
        _refuse(f"{role} descriptor is unsafe")
    raw = _read(root, value["relative_path"], label=f"pilot {role}", max_bytes=max_bytes)
    if len(raw) != value["size_bytes"] or hash_bytes(raw) != value["sha256"]:
        _refuse(f"{role} object differs from its content-addressed descriptor")
    return raw


def _master_plain(raw: bytes) -> bytes:
    if not 0 < len(raw) <= _MAX_MASTER_GZIP:
        _refuse("master.gz exceeds its compressed budget")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw), mode="rb") as reader:
            plain = reader.read(MAX_MASTER_INDEX_BYTES + 1)
            if len(plain) > MAX_MASTER_INDEX_BYTES or reader.read(1):
                _refuse("master.gz exceeds its decoded budget")
    # zlib.error (a corrupt deflate stream) is not an OSError; without it a
    # malformed master escaped as an untyped crash with no refusal record.
    except (OSError, EOFError, ValueError, zlib.error) as exc:
        if isinstance(exc, SecCompletePilotAdapterError):
            raise
        raise SecCompletePilotAdapterError("REFUSED: master.gz is malformed") from exc
    return plain


def _utc(value: object) -> datetime:
    if type(value) is not str or _UTC.fullmatch(value) is None:
        _refuse("journal timestamp is not canonical UTC")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SecCompletePilotAdapterError("REFUSED: journal UTC time is invalid") from exc
    if parsed.utcoffset() != timedelta(0):
        _refuse("journal timestamp is not UTC")
    return parsed


def _journal_events(raw: bytes, urls: list[str], objects: list[bytes]) -> None:
    if not raw or not raw.endswith(b"\n"):
        _refuse("attempt journal is not newline-terminated")
    lines = raw.splitlines(keepends=True)
    if len(lines) != 36 or len(urls) != 18 or len(objects) != 18 or len(set(urls)) != 18:
        _refuse("attempt journal is not an exact 18-request trace")
    events = [_canonical_object(line, label="attempt journal event") for line in lines]
    previous_end: int | None = None
    for index, (url, body) in enumerate(zip(urls, objects, strict=True), start=1):
        start, finish = events[2 * index - 2:2 * index]
        if set(start) != _START_KEYS or set(finish) != _FINISH_KEYS:
            _refuse("attempt journal event schema drifted")
        if (start["kind"] != "attempt-start" or finish["kind"] != "attempt-finish"
                or type(start["ordinal"]) is not int or start["ordinal"] != index
                or type(finish["ordinal"]) is not int or finish["ordinal"] != index
                or start["url"] != url or type(start["attempt"]) is not int
                or start["attempt"] != 1
                or start["pacing_basis"] != "prior_transport_completion"
                or finish["outcome"] != "http_status"
                or type(finish["status"]) is not int or finish["status"] != 200
                or type(finish["body_size_bytes"]) is not int
                or finish["body_size_bytes"] != len(body)
                or finish["body_sha256"] != hash_bytes(body)):
            _refuse("attempt journal response or request differs from replayed objects")
        cap = _MAX_MASTER_GZIP if index <= 2 else MAX_COMPLETE_SUBMISSION_BYTES
        if type(start["max_response_bytes"]) is not int or start["max_response_bytes"] != cap:
            _refuse("attempt journal request cap drifted")
        for name in ("pacing_start_utc", "pacing_end_utc", "reservation_start_utc"):
            _utc(start[name])
        for name in ("request_start_utc", "request_end_utc"):
            _utc(finish[name])
        clocks = [start[name] for name in (
            "pacing_start_monotonic_ns", "pacing_end_monotonic_ns",
            "reservation_start_monotonic_ns",
        )] + [finish["request_start_monotonic_ns"], finish["request_end_monotonic_ns"]]
        if (any(type(value) is not int or value < 0 for value in clocks)
                or clocks != sorted(clocks)
                or type(start["pacing_sleep_ns_requested"]) is not int
                or start["pacing_sleep_ns_requested"] < 0
                or (previous_end is not None and clocks[3] - previous_end < 500_000_000)):
            _refuse("attempt journal recorded pacing or clock order is invalid")
        previous_end = clocks[-1]


def _inventory(value: dict[str, object], *, inventory_sha: str, code_sha: str,
               accessions: tuple[str, ...]) -> list[dict[str, str]]:
    if (set(value) != {"kind", "version", "code_commit", "inventory_sha256",
                       "candidates", "quarter_master_urls", "owner_selected_sixteen",
                       "source_authenticated", "canonical_evidence", "research_looks"}
            or value["kind"] != "sec-complete-frozen-inventory"
            or value["version"] != _ACQUISITION_VERSION
            or value["code_commit"] != code_sha
            or value["inventory_sha256"] != inventory_sha
            or value["quarter_master_urls"] != _MASTER_URLS
            or any(value[name] is not False for name in (
                "owner_selected_sixteen", "source_authenticated", "canonical_evidence"))
            or type(value["research_looks"]) is not int or value["research_looks"] != 0
            or type(value["candidates"]) is not list or len(value["candidates"]) != 16
            or hash_payload(value["candidates"]) != inventory_sha):
        _refuse("frozen inventory identity or authority drifted")
    candidates = value["candidates"]
    if (any(type(item) is not dict or set(item) != _CANDIDATE_KEYS
            or any(type(field) is not str for field in item.values()) for item in candidates)
            or tuple(item["accession_number"] for item in candidates) != accessions
            or [item["period"] for item in candidates] != ["2022Q4"] * 8 + ["2023Q1"] * 8
            or [item["form_type"] for item in candidates]
            != ["4"] * 6 + ["4/A"] * 2 + ["4"] * 6 + ["4/A"] * 2):
        _refuse("frozen inventory is not the exact ordered sixteen")
    return candidates


def _report(value: dict[str, object], *, inventory_sha: str,
            code_sha: str) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if (set(value) != _REPORT_KEYS or value["kind"] != _ACQUISITION_VERSION
            or value["inventory_sha256"] != inventory_sha
            or value["capture_git_commit_verified"] != code_sha
            or value["complete_sample_acquired"] is not True
            or value["halted_reason"] is not None
            or type(value["attempt_count"]) is not int or value["attempt_count"] != 18
            or type(value["distinct_artifact_count"]) is not int
            or value["distinct_artifact_count"] != 18
            or any(value[name] is not False for name in (
                "source_authenticated", "canonical_evidence", "point_in_time_data",
                "direct_ib1c_ingest_authorized", "official_sec_profile_verified",
                "outcome_access_authorized", "qc_job_authorized",
                "broker_or_trading_authorized"))
            or any(type(value[name]) is not int or value[name] != 0 for name in (
                "research_looks", "authorized_outcome_looks", "consumed_outcome_looks"))
            or type(value["master_indexes"]) is not list
            or len(value["master_indexes"]) != 2
            or type(value["filings"]) is not list or len(value["filings"]) != 16):
        _refuse("complete report identity, counts, or authority drifted")
    return value["master_indexes"], value["filings"]


@dataclass(frozen=True)
class SecCompletePilotProjectionReceipt:
    """An exact local replay result, never a promoted evidence boundary."""

    report_sha256: str
    inventory_sha256: str
    code_commit: str
    projections: tuple[SecCompleteSubmissionProjection, ...]
    _report_bytes: bytes = field(repr=False)
    _projection_sha256s: tuple[str, ...] = field(repr=False)
    _expected_accessions: tuple[str, ...] = field(repr=False)
    _public_pilot: bool = field(repr=False)
    _loader_token: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._loader_token is not _LOADER_TOKEN:
            _refuse("complete pilot receipt must come from the verified loader")
        self._validate()

    def _validate(self) -> None:
        if (type(self._report_bytes) is not bytes
                or hash_bytes(self._report_bytes) != self.report_sha256
                or type(self.projections) is not tuple or len(self.projections) != 16
                or type(self._projection_sha256s) is not tuple
                or type(self._expected_accessions) is not tuple
                or tuple(type(item) is SecCompleteSubmissionProjection
                         and item.target.accession_number for item in self.projections)
                != self._expected_accessions
                or tuple(item.sha256 for item in self.projections) != self._projection_sha256s):
            _refuse("complete pilot receipt lost its report or projection binding")
        report = _canonical_object(self._report_bytes, label="complete pilot receipt report")
        _, filings = _report(report, inventory_sha=self.inventory_sha256,
                             code_sha=self.code_commit)
        for row, projection in zip(filings, self.projections, strict=True):
            if type(row) is not dict or row.get("projection") != projection.to_payload():
                _refuse("complete pilot receipt projection differs from report")
        if type(self._public_pilot) is not bool or self._public_pilot != (
            self.report_sha256 == FINAL_REPORT_SHA256
            and self.inventory_sha256 == INVENTORY_SHA256
            and self.code_commit == CAPTURE_CODE_COMMIT
            and self._expected_accessions == FIXED_ACCESSIONS
        ):
            _refuse("complete pilot receipt public-source pins were altered")

    def to_payload(self) -> dict[str, object]:
        self._validate()
        rows = []
        for item in self.projections:
            projection = item.to_payload()
            rows.append({
                "accession_number": item.target.accession_number,
                "period": item.target.period,
                "form_type": item.target.form_type,
                "projection_sha256": item.sha256,
                "raw_complete_submission_sha256": projection["raw_parent"]["sha256"],
                "derived_header_sha256": projection["children"]["header"]["sha256"],
                "derived_primary_xml_sha256": projection["children"]["primary_xml"]["sha256"],
            })
        return {
            "version": COMPLETE_PILOT_ADAPTER_VERSION,
            "source_report_sha256": self.report_sha256,
            "source_inventory_sha256": self.inventory_sha256,
            "source_code_commit": self.code_commit,
            "rows": rows,
            "authority": {
                "input_scope": (
                    "retained_noncanonical_complete_pilot" if self._public_pilot
                    else "synthetic_test_receipt"
                ),
                "source_authenticated": False,
                "quarter_completeness_verified": False,
                "point_in_time_data": False,
                "canonical_evidence": False,
                "direct_ib1c_ingest_authorized": False,
                "official_sec_profile_verified": False,
                "timezone_interpretation_verified": False,
                "outcome_access_authorized": False,
                "qc_job_authorized": False,
                "broker_or_trading_authorized": False,
                "research_looks": 0,
                "authorized_outcome_looks": 0,
                "consumed_outcome_looks": 0,
            },
        }


def _load_complete_pilot(
    root: str | Path, *, report_sha256: str, inventory_sha256: str,
    code_commit: str, expected_accessions: tuple[str, ...],
) -> SecCompletePilotProjectionReceipt:
    """Private synthetic-test seam; the public wrapper fixes all real pins."""
    if (any(type(value) is not str or _SHA.fullmatch(value) is None
            for value in (report_sha256, inventory_sha256))
            or type(code_commit) is not str or re.fullmatch(r"[0-9a-f]{40}", code_commit) is None
            or type(expected_accessions) is not tuple or len(expected_accessions) != 16
            or len(set(expected_accessions)) != 16):
        _refuse("complete pilot pins are malformed")
    path = _plain_root(root)
    with _PinnedRoot(path) as pinned:
        return _replay_complete_pilot(pinned, report_sha256=report_sha256,
                                      inventory_sha256=inventory_sha256,
                                      code_commit=code_commit,
                                      expected_accessions=expected_accessions)


def _replay_complete_pilot(
    path: _PinnedRoot, *, report_sha256: str, inventory_sha256: str,
    code_commit: str, expected_accessions: tuple[str, ...],
) -> SecCompletePilotProjectionReceipt:
    report_name = f"sec-complete-report-{report_sha256}.json"
    if _names(path) != {"attempts.jsonl", "commit.json", "inventory.json", "objects", report_name}:
        _refuse("complete pilot root topology drifted")
    commit = _canonical_object(_read(path, "commit.json", label="complete pilot commit",
                                     max_bytes=4096), label="complete pilot commit")
    report_bytes = _read(path, report_name, label="complete pilot report", max_bytes=2 * 1024 * 1024)
    if hash_bytes(report_bytes) != report_sha256:
        _refuse("complete pilot report differs from pinned SHA-256")
    report = _canonical_object(report_bytes, label="complete pilot report")
    journal_meta = report.get("attempt_journal")
    if type(journal_meta) is not dict:
        _refuse("complete pilot report has no journal descriptor")
    if commit != {"kind": "sec-complete-commit", "report_name": report_name,
                  "report_sha256": report_sha256,
                  "attempt_journal_sha256": journal_meta.get("sha256")}:
        _refuse("complete pilot commit does not bind report and journal")
    inventory = _canonical_object(_read(path, "inventory.json", label="complete pilot inventory",
                                        max_bytes=128 * 1024), label="complete pilot inventory")
    candidates = _inventory(inventory, inventory_sha=inventory_sha256,
                            code_sha=code_commit, accessions=expected_accessions)
    indexes, filings = _report(report, inventory_sha=inventory_sha256,
                               code_sha=code_commit)
    journal = _read(path, "attempts.jsonl", label="complete pilot journal",
                    max_bytes=_MAX_JOURNAL)
    journal_object = _descriptor(path, report["attempt_journal"], role="attempt journal",
                                 max_bytes=_MAX_JOURNAL)
    if journal != journal_object:
        _refuse("attempt journal is not the committed content-addressed object")
    objects_used: set[str] = {report["attempt_journal"]["sha256"] + ".bin"}
    request_urls: list[str] = []
    request_bodies: list[bytes] = []
    selected: dict[str, tuple[str, str, str]] = {}
    for (period, year, quarter), row in zip(_PERIODS, indexes, strict=True):
        if (type(row) is not dict
                or set(row) != {"period", "source_url", "status", "reason", "raw_object",
                               "decoded_sha256", "decoded_size_bytes", "receipt", "subset"}
                or row["period"] != period or row["source_url"] != _MASTER_URLS[period]
                or row["status"] != "matched_subset_noncanonical" or row["reason"] is not None):
            _refuse("complete pilot master index row drifted")
        raw = _descriptor(path, row["raw_object"], role="master.gz", max_bytes=_MAX_MASTER_GZIP)
        objects_used.add(row["raw_object"]["sha256"] + ".bin")
        request_urls.append(row["source_url"])
        request_bodies.append(raw)
        plain = _master_plain(raw)
        if row["decoded_sha256"] != hash_bytes(plain) or row["decoded_size_bytes"] != len(plain):
            _refuse("master.gz decoded byte identity drifted")
        try:
            receipt = parse_sec_quarter_master_index(plain, year=year, quarter=quarter)
            expected = tuple(SecMasterIndexExpectedRow(
                accession_number=item["accession_number"], form_type=item["form_type"],
                filing_date=item["filing_date"], issuer_cik=item["issuer_cik"],
            ) for item in candidates if item["period"] == period)
            subset = select_sec_master_index_subset(receipt, expected)
        except SecQuarterMasterIndexError as exc:
            raise SecCompletePilotAdapterError(str(exc)) from exc
        receipt_payload = {
            "parser_version": MASTER_INDEX_PARSER_VERSION, "year": receipt.year,
            "quarter": receipt.quarter, "source_sha256": receipt.source_sha256,
            "source_size_bytes": receipt.source_size_bytes,
            "all_filing_row_count": receipt.all_filing_row_count,
            "form4_or_4a_row_count": len(receipt.rows),
            "receipt_sha256": receipt.receipt_sha256,
            "subset_only_no_quarter_completeness_claim": True,
        }
        if row["receipt"] != receipt_payload or row["subset"] != [item.to_payload() for item in subset]:
            _refuse("master.gz receipt or fixed subset differs from replay")
        for item in subset:
            if item.accession_number in selected:
                _refuse("master indexes repeat a fixed accession")
            selected[item.accession_number] = (period, item.archive_path, receipt.receipt_sha256)
    if set(selected) != set(expected_accessions):
        _refuse("master indexes do not cover the exact sixteen")
    projections: list[SecCompleteSubmissionProjection] = []
    for candidate, row in zip(candidates, filings, strict=True):
        accession = candidate["accession_number"]
        period, archive_path, receipt_sha = selected[accession]
        url = "https://www.sec.gov/Archives/" + archive_path
        if (type(row) is not dict
                or set(row) != {"candidate", "status", "reason", "source_url",
                               "index_receipt_sha256", "raw_object", "projection"}
                or row["candidate"] != candidate or period != candidate["period"]
                or row["source_url"] != url or row["index_receipt_sha256"] != receipt_sha
                or row["status"] != "acquired_noncanonical" or row["reason"] is not None):
            _refuse("complete pilot filing row differs from fixed index join")
        raw = _descriptor(path, row["raw_object"], role="complete submission",
                          max_bytes=MAX_COMPLETE_SUBMISSION_BYTES)
        objects_used.add(row["raw_object"]["sha256"] + ".bin")
        request_urls.append(url)
        request_bodies.append(raw)
        try:
            target = SecCompleteSubmissionTarget(
                period=period, accession_number=accession,
                form_type=candidate["form_type"], filing_date=candidate["filing_date"],
                issuer_cik=candidate["issuer_cik"],
                quarterly_index_sha256=next(index["receipt"]["source_sha256"]
                                              for index in indexes if index["period"] == period),
                complete_submission_url=url,
            )
            projection = project_sec_complete_submission(target, raw)
        except SecCompleteSubmissionError as exc:
            raise SecCompletePilotAdapterError(str(exc)) from exc
        if row["projection"] != projection.to_payload():
            _refuse("complete submission projection differs from replayed raw bytes")
        projections.append(projection)
    _journal_events(journal, request_urls, request_bodies)
    if len(objects_used) != 19 or _names(path, objects=True) != objects_used:
        _refuse("complete pilot object directory is not exactly 18 raw parents and journal")
    return SecCompletePilotProjectionReceipt(
        report_sha256=report_sha256, inventory_sha256=inventory_sha256,
        code_commit=code_commit, projections=tuple(projections),
        _report_bytes=report_bytes,
        _projection_sha256s=tuple(item.sha256 for item in projections),
        _expected_accessions=expected_accessions,
        _public_pilot=(report_sha256 == FINAL_REPORT_SHA256
                       and inventory_sha256 == INVENTORY_SHA256
                       and code_commit == CAPTURE_CODE_COMMIT
                       and expected_accessions == FIXED_ACCESSIONS),
        _loader_token=_LOADER_TOKEN,
    )


def load_fixed_complete_pilot(root: str | Path) -> SecCompletePilotProjectionReceipt:
    """Replay only the pinned local pilot, with no I/O outside its root."""
    return _load_complete_pilot(
        root, report_sha256=FINAL_REPORT_SHA256,
        inventory_sha256=INVENTORY_SHA256, code_commit=CAPTURE_CODE_COMMIT,
        expected_accessions=FIXED_ACCESSIONS,
    )
