"""Fixed 16-accession SEC master-index and complete-submission acquisition.

This is an explicit, separately launched operational boundary, not an import
side effect. It retains exact raw bytes outside Git and makes no IB-1C,
canonical, point-in-time, outcome, QC, paper, broker or trading claim.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import getpass
import gzip
import http.client
import io
import os
from pathlib import Path
import re
import stat
import subprocess
import time
from typing import Callable
import zlib

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying.sec_bulk_snapshot import _read_regular_bytes
from research.insider_buying.sec_quarter_master_index import (
    MASTER_INDEX_PARSER_VERSION,
    MAX_MASTER_INDEX_BYTES,
    SecMasterIndexExpectedRow,
    SecQuarterMasterIndexError,
    parse_sec_quarter_master_index,
    select_sec_master_index_subset,
)
from research.insider_buying.sec_complete_submission import (
    SecCompleteSubmissionError,
    SecCompleteSubmissionTarget,
    project_sec_complete_submission,
)
from research.insider_buying_sec_acquisition import (
    SecPilotCandidate,
    _EXPECTED_ACCESSIONS,
    _ascii_decimal,
    _check_output_directory,
    _open_output_directory,
    _publish_immutable,
    _safe_roots,
    _store_object,
    select_fixed_pilot,
)


COMPLETE_ACQUISITION_VERSION = "INSETF-SEC-SIXTEEN-COMPLETE-TXT-v1"
_PERIODS = (("2022Q4", 2022, 4), ("2023Q1", 2023, 1))
_MASTER_URLS = {
    "2022Q4": "https://www.sec.gov/Archives/edgar/full-index/2022/QTR4/master.gz",
    "2023Q1": "https://www.sec.gov/Archives/edgar/full-index/2023/QTR1/master.gz",
}
_QUARTER_ZIP_SHA256 = {
    "2022Q4": "6c6a909bd2eaaa0a24ccf5f0071b404670c115845d2939bc592bf3ce420dcdb9",
    "2023Q1": "0b476188f52a0862e71886eb31a81f6345fc6616403b52188484aef0438cfcfb",
}
# Reviewed pilot candidate payload fingerprint, not a committed real-row table.
_APPROVED_SIXTEEN_INVENTORY_SHA256 = (
    "4b8a4c3a233855ea2aa6cde0b2739a83aca478180ac881e1cf011943753d78db"
)
_HOST_PREFIX = "https://www.sec.gov/Archives/"
_CONTACT_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}\Z")
_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
MAX_MASTER_GZIP_BYTES = 8 * 1024 * 1024
MAX_COMPLETE_TXT_BYTES = 8 * 1024 * 1024
MAX_ATTEMPTS_PER_ARTIFACT = 3
MAX_DISTINCT_ARTIFACTS = 18
MAX_TOTAL_ATTEMPTS = 54
MIN_REQUEST_INTERVAL_NS = 500_000_000


class SecCompleteAcquisitionError(ValueError):
    """The fixed acquisition refused a source, request, or publication."""


class _GlobalStop(SecCompleteAcquisitionError):
    """No further SEC request may be made in this run."""


@dataclass(frozen=True)
class SecHttpResult:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes


Transport = Callable[[str, dict[str, str], int], SecHttpResult]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _verify_exact_committed_code(commit: str) -> None:
    """Require the exact clean lane HEAD and five directly used source files."""
    if type(commit) is not str or _SHA_RE.fullmatch(commit) is None:
        raise SecCompleteAcquisitionError("REFUSED: code commit is not a full lowercase SHA")
    root = Path(__file__).resolve().parents[1]
    paths = (
        "research/insider_buying_sec_complete_acquisition.py",
        "research/insider_buying_sec_acquisition.py",
        "research/insider_buying/sec_quarter_master_index.py",
        "research/insider_buying/sec_complete_submission.py",
        "research/insider_buying/sec_acquisition_preparation.py",
    )
    try:
        top = subprocess.check_output(("git", "rev-parse", "--show-toplevel"), cwd=root,
                                      stderr=subprocess.DEVNULL).decode().strip()
        branch = subprocess.check_output(("git", "branch", "--show-current"), cwd=root,
                                         stderr=subprocess.DEVNULL).decode().strip()
        actual = subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=root,
                                         stderr=subprocess.DEVNULL).decode().strip()
        dirty = subprocess.check_output(("git", "status", "--porcelain=v1", "--untracked-files=all"),
                                        cwd=root, stderr=subprocess.DEVNULL)
        if (top != str(root) or branch != "codex/strategy-insider-buying"
                or actual != commit or dirty):
            raise SecCompleteAcquisitionError("REFUSED: exact clean committed lane is required")
        for relative in paths:
            committed = subprocess.check_output(("git", "show", f"{commit}:{relative}"),
                                                cwd=root, stderr=subprocess.DEVNULL)
            if hash_bytes(committed) != hash_bytes((root / relative).read_bytes()):
                raise SecCompleteAcquisitionError("REFUSED: committed runner dependency differs on disk")
    except (OSError, UnicodeError, subprocess.CalledProcessError) as exc:
        raise SecCompleteAcquisitionError("REFUSED: exact code commit could not be verified") from exc


def _strict_response(result: SecHttpResult, *, max_bytes: int) -> bytes:
    if type(result) is not SecHttpResult or type(result.status) is not int:
        raise _GlobalStop("REFUSED: transport result is malformed")
    if result.status in (403, 429):
        raise _GlobalStop(f"REFUSED: SEC access stopped at HTTP {result.status}")
    if result.status != 200:
        raise SecCompleteAcquisitionError(f"REFUSED: SEC returned HTTP {result.status}")
    if (type(result.headers) is not tuple or type(result.body) is not bytes
            or not 0 < len(result.body) <= max_bytes):
        raise _GlobalStop("REFUSED: response type or body bound is invalid")
    pairs = result.headers
    if any(type(pair) is not tuple or len(pair) != 2
           or type(pair[0]) is not str or type(pair[1]) is not str for pair in pairs):
        raise _GlobalStop("REFUSED: response header shape is invalid")
    lengths = [value for name, value in pairs if name.lower() == "content-length"]
    encodings = [value for name, value in pairs if name.lower() == "content-encoding"]
    transfers = [value for name, value in pairs if name.lower() == "transfer-encoding"]
    if (len(lengths) != 1 or not _ascii_decimal(lengths[0])
            or int(lengths[0]) != len(result.body) or len(result.body) > max_bytes
            or len(encodings) > 1 or (encodings and encodings[0].lower() != "identity")
            or transfers):
        raise _GlobalStop("REFUSED: response framing is missing, duplicate, encoded, or oversized")
    return result.body


def _sec_transport(url: str, headers: dict[str, str], max_bytes: int) -> SecHttpResult:
    """No redirect following; reject framing before reading any 200 body."""
    if not url.startswith(_HOST_PREFIX) or "?" in url or "#" in url or "%" in url:
        raise _GlobalStop("REFUSED: request escaped the exact SEC Archives host")
    connection = http.client.HTTPSConnection("www.sec.gov", timeout=15)
    try:
        connection.request("GET", url.removeprefix("https://www.sec.gov"), headers=headers)
        response = connection.getresponse()
        if response.status != 200:
            return SecHttpResult(response.status, tuple(response.getheaders()), b"")
        response_headers = tuple(response.getheaders())
        lengths = [value for name, value in response_headers if name.lower() == "content-length"]
        encodings = [value for name, value in response_headers if name.lower() == "content-encoding"]
        transfers = [value for name, value in response_headers if name.lower() == "transfer-encoding"]
        if (len(lengths) != 1 or not _ascii_decimal(lengths[0])
                or not 0 < int(lengths[0]) <= max_bytes
                or len(encodings) > 1 or (encodings and encodings[0].lower() != "identity")
                or transfers):
            raise _GlobalStop("REFUSED: SEC response framing is unsafe")
        size = int(lengths[0])
        body = response.read(size)
        if len(body) != size:
            raise _GlobalStop("REFUSED: SEC response was truncated")
        return SecHttpResult(200, response_headers, body)
    finally:
        connection.close()


def _decompress_master(raw: bytes) -> bytes:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_MASTER_GZIP_BYTES:
        raise SecCompleteAcquisitionError("REFUSED: master.gz exceeds its compressed bound")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw), mode="rb") as reader:
            body = reader.read(MAX_MASTER_INDEX_BYTES + 1)
            if len(body) > MAX_MASTER_INDEX_BYTES or reader.read(1):
                raise SecCompleteAcquisitionError("REFUSED: master.gz expands beyond 64 MiB")
    # zlib.error (a corrupt deflate stream) is not an OSError; without it a
    # malformed master escaped as an untyped crash with no refusal record.
    except (OSError, EOFError, ValueError, zlib.error) as exc:
        if isinstance(exc, SecCompleteAcquisitionError):
            raise
        raise SecCompleteAcquisitionError("REFUSED: master.gz is malformed or truncated") from exc
    return body


class _Journal:
    def __init__(self, output: Path, identity: tuple[int, int]) -> None:
        self.output = output
        self.directory_fd = _open_output_directory(output, identity)
        self.identity = identity
        try:
            descriptor = os.open("attempts.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL
                                 | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=self.directory_fd)
            self.handle = os.fdopen(descriptor, "wb")
            os.fsync(self.directory_fd)
        except BaseException:
            os.close(self.directory_fd)
            raise
        self.attempts = 0
        self.paths: set[str] = set()
        self.attempts_by_url: dict[str, int] = {}
        self.last_transport_completion_ns: int | None = None

    def event(self, value: dict[str, object]) -> None:
        _check_output_directory(self.output, self.directory_fd, self.identity)
        self.handle.write((canonical_json(value) + "\n").encode("utf-8"))
        self.handle.flush()
        os.fsync(self.handle.fileno())
        _check_output_directory(self.output, self.directory_fd, self.identity)

    def request(self, url: str, *, max_bytes: int, contact_email: str,
                transport: Transport) -> bytes:
        if (url not in _MASTER_URLS.values()
                and not re.fullmatch(r"https://www\.sec\.gov/Archives/edgar/data/"
                                     r"[0-9]{1,10}/[0-9]{10}-[0-9]{2}-[0-9]{6}\.txt", url)):
            raise _GlobalStop("REFUSED: request URL is outside the fixed SEC surfaces")
        if url not in self.paths and len(self.paths) >= MAX_DISTINCT_ARTIFACTS:
            raise _GlobalStop("REFUSED: more than 18 distinct artifacts")
        used = self.attempts_by_url.get(url, 0)
        if used:
            # Retries are permitted only inside this call, never a second
            # semantic request for a previously consumed artifact.
            raise _GlobalStop("REFUSED: duplicate artifact request")
        self.paths.add(url)
        headers = {"User-Agent": f"InsiderBuyingResearch/0.1 ({contact_email})",
                   "Accept": "*/*", "Accept-Encoding": "identity", "Connection": "close"}
        for attempt in range(1, MAX_ATTEMPTS_PER_ARTIFACT + 1):
            if self.attempts >= MAX_TOTAL_ATTEMPTS:
                raise _GlobalStop("REFUSED: total SEC attempt ceiling reached")
            pacing_start_ns = time.monotonic_ns()
            pacing_start_utc = _utc_now()
            # Conservatively pace from the *completed* prior transport. DNS,
            # TLS and server time can separate Python invocation from the
            # actual request send, which this interface cannot observe.
            earliest = (self.last_transport_completion_ns + MIN_REQUEST_INTERVAL_NS
                        if self.last_transport_completion_ns is not None else pacing_start_ns)
            if attempt > 1:
                earliest = max(earliest, pacing_start_ns + (attempt - 1) * 1_000_000_000)
            sleep_ns = max(0, earliest - pacing_start_ns)
            if sleep_ns:
                time.sleep(sleep_ns / 1_000_000_000)
            pacing_end_ns = time.monotonic_ns()
            pacing_end_utc = _utc_now()
            start_ns = time.monotonic_ns()
            start_utc = _utc_now()
            self.attempts += 1
            self.attempts_by_url[url] = attempt
            ordinal = self.attempts
            self.event({"kind": "attempt-start", "ordinal": ordinal, "url": url,
                        "attempt": attempt, "max_response_bytes": max_bytes,
                        "pacing_start_utc": pacing_start_utc,
                        "pacing_start_monotonic_ns": pacing_start_ns,
                        "pacing_end_utc": pacing_end_utc,
                        "pacing_end_monotonic_ns": pacing_end_ns,
                        "pacing_sleep_ns_requested": sleep_ns,
                        "pacing_basis": "prior_transport_completion",
                        "reservation_start_utc": start_utc,
                        "reservation_start_monotonic_ns": start_ns})
            _check_output_directory(self.output, self.directory_fd, self.identity)
            dispatch_ns = time.monotonic_ns()
            dispatch_utc = _utc_now()
            if dispatch_ns < earliest:
                raise _GlobalStop("REFUSED: actual SEC dispatch pacing was too early")
            try:
                result = transport(url, headers, max_bytes)
            except (OSError, http.client.HTTPException) as exc:
                completion_ns = time.monotonic_ns()
                self.last_transport_completion_ns = completion_ns
                self.event({"kind": "attempt-finish", "ordinal": ordinal,
                            "request_end_utc": _utc_now(),
                            "request_end_monotonic_ns": completion_ns,
                            "request_start_utc": dispatch_utc,
                            "request_start_monotonic_ns": dispatch_ns,
                            "outcome": "network_error", "error_type": type(exc).__name__})
                if attempt < MAX_ATTEMPTS_PER_ARTIFACT:
                    continue
                raise _GlobalStop("REFUSED: bounded SEC transport retries exhausted") from exc
            except BaseException:
                # A crash/interruption retains the already-fsynced reservation.
                # This output root cannot be resumed or silently reused.
                self.last_transport_completion_ns = time.monotonic_ns()
                raise
            end_ns = time.monotonic_ns()
            self.last_transport_completion_ns = end_ns
            end_utc = _utc_now()
            if type(result) is not SecHttpResult or type(result.status) is not int:
                self.event({"kind": "attempt-finish", "ordinal": ordinal,
                            "request_end_utc": end_utc, "request_end_monotonic_ns": end_ns,
                            "request_start_utc": dispatch_utc,
                            "request_start_monotonic_ns": dispatch_ns,
                            "outcome": "malformed_transport"})
                raise _GlobalStop("REFUSED: transport result is malformed")
            self.event({"kind": "attempt-finish", "ordinal": ordinal,
                        "request_end_utc": end_utc, "request_end_monotonic_ns": end_ns,
                        "request_start_utc": dispatch_utc,
                        "request_start_monotonic_ns": dispatch_ns,
                        "outcome": "http_status", "status": result.status,
                        "body_size_bytes": len(result.body) if type(result.body) is bytes else None,
                        "body_sha256": hash_bytes(result.body) if type(result.body) is bytes else None})
            if result.status in (500, 502, 503, 504) and attempt < MAX_ATTEMPTS_PER_ARTIFACT:
                continue
            if result.status in (500, 502, 503, 504):
                raise _GlobalStop(f"REFUSED: SEC service remained unavailable at HTTP {result.status}")
            return _strict_response(result, max_bytes=max_bytes)
        raise AssertionError("bounded retry loop did not terminate")

    def close(self) -> None:
        try:
            self.handle.close()
        finally:
            os.close(self.directory_fd)


def _report(output: Path, identity: tuple[int, int], payload: dict[str, object]) -> Path:
    journal_path = output / "attempts.jsonl"
    if not journal_path.is_file() or journal_path.is_symlink():
        raise SecCompleteAcquisitionError("REFUSED: attempt journal is not a regular file")
    journal = _read_regular_bytes(journal_path, label="complete acquisition attempt journal",
                                  max_bytes=2 * 1024 * 1024)
    journal_object = _store_object(output, journal, identity)
    payload["attempt_journal"] = journal_object
    raw = (canonical_json(payload) + "\n").encode("utf-8")
    digest = hash_bytes(raw)
    name = f"sec-complete-report-{digest}.json"
    _publish_immutable(output, name, raw, identity)
    commit = {"kind": "sec-complete-commit", "report_name": name,
              "report_sha256": digest, "attempt_journal_sha256": journal_object["sha256"]}
    _publish_immutable(output, "commit.json", (canonical_json(commit) + "\n").encode("utf-8"), identity)
    return output / name


def run_fixed_complete_submissions(
    input_root: str | Path, prior_pilot_root: str | Path, output_root: str | Path, *,
    contact_email: str, capture_git_commit: str, transport: Transport | None = None,
) -> Path:
    """Acquire two supplied-master index images and their exact 16 TXT paths.

    A new, nonexisting output root is required. Malformed inputs or an HTTP
    denial stop all later requests; unattempted accessions stay in the report.
    """
    if (type(contact_email) is not str or len(contact_email) > 254
            or _CONTACT_RE.fullmatch(contact_email) is None):
        raise SecCompleteAcquisitionError("REFUSED: identifying SEC contact is required")
    _verify_exact_committed_code(capture_git_commit)
    source, prior, output = _safe_roots(input_root, prior_pilot_root, output_root)
    selected = select_fixed_pilot(source, prior)
    if (type(selected) is not tuple or len(selected) != 16
            or any(type(item) is not SecPilotCandidate for item in selected)
            or tuple(item.accession_number for item in selected) != _EXPECTED_ACCESSIONS
            or any(item.period != ("2022Q4" if index < 8 else "2023Q1")
                   for index, item in enumerate(selected))
            or any(item.quarterly_zip_sha256 != _QUARTER_ZIP_SHA256.get(item.period)
                   for item in selected)
            or tuple(item.form_type for item in selected)
            != ("4",) * 6 + ("4/A",) * 2 + ("4",) * 6 + ("4/A",) * 2
            or hash_payload([item.to_payload() for item in selected])
            != _APPROVED_SIXTEEN_INVENTORY_SHA256):
        raise SecCompleteAcquisitionError("REFUSED: the selected pilot is not the pinned sixteen")
    selected_payload = [item.to_payload() for item in selected]
    inventory_sha256 = hash_payload(selected_payload)
    _safe_roots(source, prior, output)
    output.mkdir(mode=0o700)
    current = output.lstat()
    if not stat.S_ISDIR(current.st_mode):
        raise SecCompleteAcquisitionError("REFUSED: output root was replaced")
    identity = (current.st_dev, current.st_ino)
    (output / "objects").mkdir(mode=0o700)
    frozen = {"kind": "sec-complete-frozen-inventory", "version": COMPLETE_ACQUISITION_VERSION,
              "code_commit": capture_git_commit, "inventory_sha256": inventory_sha256,
              "candidates": selected_payload, "quarter_master_urls": _MASTER_URLS,
              "owner_selected_sixteen": False, "source_authenticated": False,
              "canonical_evidence": False, "research_looks": 0}
    _publish_immutable(output, "inventory.json", (canonical_json(frozen) + "\n").encode("utf-8"), identity)
    journal = _Journal(output, identity)
    fetch = _sec_transport if transport is None else transport
    if not callable(fetch):
        journal.close()
        raise SecCompleteAcquisitionError("REFUSED: transport is not callable")
    index_rows: list[dict[str, object]] = []
    filing_rows: list[dict[str, object]] = [
        {"candidate": candidate.to_payload(), "status": "not_attempted", "reason": None}
        for candidate in selected
    ]
    halted_reason: str | None = None
    matched: dict[str, tuple[object, object]] = {}
    try:
        for period, year, quarter in _PERIODS:
            row: dict[str, object] = {"period": period, "source_url": _MASTER_URLS[period],
                                      "status": "not_attempted", "reason": None}
            index_rows.append(row)
            try:
                compressed = journal.request(_MASTER_URLS[period], max_bytes=MAX_MASTER_GZIP_BYTES,
                                             contact_email=contact_email, transport=fetch)
                row["raw_object"] = _store_object(output, compressed, identity)
                plain = _decompress_master(compressed)
                row["decoded_sha256"] = hash_bytes(plain)
                row["decoded_size_bytes"] = len(plain)
                receipt = parse_sec_quarter_master_index(plain, year=year, quarter=quarter)
                expected = tuple(SecMasterIndexExpectedRow(
                    accession_number=item.accession_number, form_type=item.form_type,
                    filing_date=item.filing_date, issuer_cik=item.issuer_cik,
                ) for item in selected if item.period == period)
                subset = select_sec_master_index_subset(receipt, expected)
                if len(subset) != len(expected):
                    raise SecCompleteAcquisitionError("REFUSED: fixed master subset is incomplete")
                row["receipt"] = {
                    "parser_version": MASTER_INDEX_PARSER_VERSION,
                    "year": receipt.year, "quarter": receipt.quarter,
                    "source_sha256": receipt.source_sha256,
                    "source_size_bytes": receipt.source_size_bytes,
                    "all_filing_row_count": receipt.all_filing_row_count,
                    "form4_or_4a_row_count": len(receipt.rows),
                    "receipt_sha256": receipt.receipt_sha256,
                    "subset_only_no_quarter_completeness_claim": True,
                }
                row["subset"] = [item.to_payload() for item in subset]
                row["status"] = "matched_subset_noncanonical"
                matched.update({item.accession_number: (item, receipt) for item in subset})
            except (SecCompleteAcquisitionError, SecQuarterMasterIndexError) as exc:
                row["status"] = "refused"
                row["reason"] = str(exc)
                halted_reason = str(exc)
                break
        if halted_reason is None and len(matched) != 16:
            halted_reason = "REFUSED: two master indexes did not cover the pinned sixteen"
        if halted_reason is None:
            for row, candidate in zip(filing_rows, selected, strict=True):
                source_row, receipt = matched[candidate.accession_number]
                url = _HOST_PREFIX + source_row.archive_path
                row["source_url"] = url
                row["index_receipt_sha256"] = receipt.receipt_sha256
                try:
                    target = SecCompleteSubmissionTarget(
                        period=candidate.period, accession_number=candidate.accession_number,
                        form_type=candidate.form_type, filing_date=candidate.filing_date,
                        issuer_cik=candidate.issuer_cik,
                        quarterly_index_sha256=receipt.source_sha256,
                        complete_submission_url=url,
                    )
                    complete = journal.request(url, max_bytes=MAX_COMPLETE_TXT_BYTES,
                                               contact_email=contact_email, transport=fetch)
                    row["raw_object"] = _store_object(output, complete, identity)
                    projection = project_sec_complete_submission(target, complete)
                    row["projection"] = projection.to_payload()
                    row["status"] = "acquired_noncanonical"
                except (SecCompleteAcquisitionError, SecCompleteSubmissionError) as exc:
                    row["status"] = "refused"
                    row["reason"] = str(exc)
                    halted_reason = str(exc)
                    break
    finally:
        journal.close()
    payload: dict[str, object] = {
        "kind": COMPLETE_ACQUISITION_VERSION,
        "inventory_sha256": inventory_sha256,
        "capture_git_commit_verified": capture_git_commit,
        "master_indexes": index_rows,
        "filings": filing_rows,
        "attempt_count": journal.attempts,
        "distinct_artifact_count": len(journal.paths),
        "halted_reason": halted_reason,
        "complete_sample_acquired": halted_reason is None and len(index_rows) == 2
        and all(row["status"] == "acquired_noncanonical" for row in filing_rows),
        "source_authenticated": False,
        "canonical_evidence": False,
        "point_in_time_data": False,
        "direct_ib1c_ingest_authorized": False,
        "official_sec_profile_verified": False,
        "outcome_access_authorized": False,
        "qc_job_authorized": False,
        "broker_or_trading_authorized": False,
        "research_looks": 0,
        "authorized_outcome_looks": 0,
        "consumed_outcome_looks": 0,
    }
    return _report(output, identity, payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--prior-pilot-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--capture-git-commit", required=True)
    args = parser.parse_args(argv)
    contact_email = getpass.getpass("SEC EDGAR identifying contact email: ")
    report = run_fixed_complete_submissions(
        args.input_root, args.prior_pilot_root, args.output_root,
        contact_email=contact_email, capture_git_commit=args.capture_git_commit,
    )
    print(report)
    return 0


if __name__ == "__main__":  # pragma: no cover - explicit operator launch only
    raise SystemExit(main())
