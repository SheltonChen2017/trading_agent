"""Offline, noncanonical accession census of the 82 retained SEC quarterly ZIPs.

The public entry point accepts only the exact retained CSV manifest bytes and
its 82 hash-named archive files. It reads one bounded ZIP at a time, validates
every member using the existing IB-1A integrity boundary, and streams only
SUBMISSION.tsv logical records to measure Form 4/4-A accession counts. No row
content, CIK, XML, or acceptance clock is returned or persisted. The CSV's
seven-digit time is a *local filesystem last-write observation*, never a SEC
retrieval or publication time. ZIP/CSV byte agreement does not authenticate
SEC origin or prove the quarterly population complete.

The capacity section is a planning bound based on measured ZIP counts and
the separate caller-declaration-only preflight's arithmetic. It is not a
complete-text/metadata source manifest, a crawler, a forecast, canonical or
point-in-time evidence, an outcome look, or QuantConnect/trading authority.
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import stat
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from data.hashing import hash_bytes, hash_payload
from research.insider_buying.sec_bulk_parsed_snapshot import (
    MAX_FIELD_CHARACTERS,
    MAX_HEADER_COLUMNS,
    MAX_ROWS_PER_TABLE,
)
from research.insider_buying.sec_bulk_snapshot import (
    MAX_ARCHIVE_BYTES,
    SecBulkSnapshotError,
    SecBulkSource,
    inspect_sec_bulk_archive,
)
from research.insider_buying.sec_corpus_scale_preflight import (
    SecCorpusScalePreflightError,
    SecQuarterScaleDescriptor,
    build_sec_corpus_scale_preflight,
)


SEC_ZIP_CORPUS_CENSUS_KIND = "insider-buying-sec-zip-corpus-census"
SEC_ZIP_CORPUS_CENSUS_VERSION = 1
RETAINED_ZIP_MANIFEST_SHA256 = (
    "dc254e4e023bf9990028e085450fc4a5c1c2ae22e1d562f2efc4ada532f9f76d"
)
RETAINED_ZIP_MANIFEST_SIZE_BYTES = 34_381
_MANIFEST_NAME = "insider_quarterly_zip_manifest_2006q1_2026q2.csv"
_MANIFEST_HEADER = (
    "Period", "FileName", "SourceUrl", "SizeBytes", "SHA256",
    "LocalLastWriteUtc", "TimestampBasis", "CaptureCommit", "SourceIndexUrl",
)
_TIMESTAMP_BASIS = "local filesystem last-write time; not SEC-attested"
_CAPTURE_COMMIT = "a4192546b168470ff1e9c421d8bd53531a1b3c05"
_SOURCE_INDEX_URL = (
    "https://www.sec.gov/data-research/sec-markets-data/"
    "insider-transactions-data-sets"
)
_SOURCE_PREFIX = "https://www.sec.gov/files/"
_SOURCE_SUFFIX = "/data/insider-transactions-data-sets/"
_FORM_TYPES = ("3", "3/A", "4", "4/A", "5", "5/A")
_REQUIRED_SUBMISSION_HEADERS = frozenset({
    "ACCESSION_NUMBER", "FILING_DATE", "PERIOD_OF_REPORT",
    "DOCUMENT_TYPE", "ISSUERCIK", "ISSUERNAME", "ISSUERTRADINGSYMBOL",
})
_PERIODS = tuple(
    f"{year}Q{quarter}"
    for year in range(2006, 2027)
    for quarter in range(1, 5)
    if (year, quarter) <= (2026, 2)
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_LOCAL_STAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{7}Z\Z"
)
_ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_HEADER = re.compile(r"[A-Z][A-Z0-9_]*\Z")
_MAX_MANIFEST_BYTES = 128 * 1024
_MAX_SUBMISSION_HEADER_BYTES = 16 * 1024
_RETAINED_CONSTRUCTION_TOKEN = object()
_SYNTHETIC_CONSTRUCTION_TOKEN = object()


class SecZipCorpusCensusError(ValueError):
    """The source-bound, read-only census refused its inputs."""


def _refuse(message: str) -> None:
    raise SecZipCorpusCensusError(f"REFUSED: {message}")


@dataclass(frozen=True)
class _ManifestBinding:
    period: str
    filename: str
    source_url: str
    size_bytes: int
    sha256: str
    local_last_write_utc: str


@dataclass(frozen=True)
class SecZipCensusQuarter:
    """Measured scalars and header identity, with no filing row contents."""

    period: str
    zip_sha256: str
    zip_size_bytes: int
    source_url_from_retained_manifest: str
    local_last_write_utc_unverified: str
    submission_member_sha256: str
    submission_member_size_bytes: int
    submission_header_line_sha256: str
    submission_headers: tuple[str, ...]
    form_counts: tuple[int, int, int, int, int, int]

    def __post_init__(self) -> None:
        if (
            type(self) is not SecZipCensusQuarter
            or type(self.period) is not str
            or self.period not in _PERIODS
        ):
            _refuse("quarter receipt period or type is invalid")
        if any(
            type(value) is not str or _SHA256.fullmatch(value) is None
            for value in (
                self.zip_sha256, self.submission_member_sha256,
                self.submission_header_line_sha256,
            )
        ):
            _refuse("quarter receipt fingerprint is invalid")
        if (
            type(self.zip_size_bytes) is not int
            or not 0 < self.zip_size_bytes <= MAX_ARCHIVE_BYTES
            or type(self.submission_member_size_bytes) is not int
            or self.submission_member_size_bytes <= 0
        ):
            _refuse("quarter receipt size is invalid")
        if (
            type(self.source_url_from_retained_manifest) is not str
            or self.source_url_from_retained_manifest != _expected_url(self.period)
            or type(self.local_last_write_utc_unverified) is not str
            or _LOCAL_STAMP.fullmatch(self.local_last_write_utc_unverified) is None
        ):
            _refuse("quarter receipt source observation is invalid")
        if (
            type(self.submission_headers) is not tuple
            or not _valid_submission_headers(self.submission_headers)
            or type(self.form_counts) is not tuple
            or len(self.form_counts) != len(_FORM_TYPES)
            or any(type(count) is not int or count < 0 for count in self.form_counts)
            or sum(self.form_counts) > MAX_ROWS_PER_TABLE
        ):
            _refuse("quarter receipt SUBMISSION census is invalid")

    @property
    def submission_accessions(self) -> int:
        return sum(self.form_counts)

    @property
    def form4_accessions(self) -> int:
        return self.form_counts[2]

    @property
    def form4a_accessions(self) -> int:
        return self.form_counts[3]

    def to_payload(self) -> dict[str, object]:
        self.__post_init__()
        return {
            "period": self.period,
            "zip_sha256": self.zip_sha256,
            "zip_size_bytes": self.zip_size_bytes,
            "source_url_from_retained_manifest": self.source_url_from_retained_manifest,
            "local_last_write_utc_unverified": self.local_last_write_utc_unverified,
            "submission_member_sha256": self.submission_member_sha256,
            "submission_member_size_bytes": self.submission_member_size_bytes,
            "submission_header_line_sha256": self.submission_header_line_sha256,
            "submission_headers": list(self.submission_headers),
            "submission_accessions": self.submission_accessions,
            "document_type_counts": dict(zip(_FORM_TYPES, self.form_counts, strict=True)),
            "form4_or_4a_target_accessions": (
                self.form4_accessions + self.form4a_accessions
            ),
            "multi_owner_target_count": None,
        }


@dataclass(frozen=True)
class SecZipCorpusCensus:
    """Versioned 82-quarter aggregate with false promotion authority."""

    scope: str
    source_manifest_sha256: str
    source_manifest_size_bytes: int
    quarters: tuple[SecZipCensusQuarter, ...]
    existing_zip_bytes: int
    submission_accessions: int
    form4_accessions: int
    form4a_accessions: int
    target_accessions: int
    multi_owner_unknown_quarters: int
    planned_distinct_artifacts_without_cache: int
    maximum_attempts_at_three_per_artifact: int
    ideal_minimum_dispatch_span_ms: int
    successful_raw_parent_cap_bytes: int
    existing_zip_plus_successful_parent_cap_bytes: int
    acceptance_metadata_records_required_without_cache: int
    _validated_quarters_sha256: str = field(repr=False, compare=False)
    _construction_token: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.scope) is not str:
            _refuse("82-quarter census scope is malformed")
        if self.scope == "retained_noncanonical_zip_census":
            if self._construction_token is not _RETAINED_CONSTRUCTION_TOKEN:
                _refuse("retained census scope is loader-only")
        elif self.scope == "synthetic_test_census":
            if self._construction_token is not _SYNTHETIC_CONSTRUCTION_TOKEN:
                _refuse("synthetic census scope is loader-only")
        if (
            type(self) is not SecZipCorpusCensus
            or self.scope not in {"retained_noncanonical_zip_census", "synthetic_test_census"}
            or type(self.source_manifest_sha256) is not str
            or _SHA256.fullmatch(self.source_manifest_sha256) is None
            or type(self.source_manifest_size_bytes) is not int
            or not 0 < self.source_manifest_size_bytes <= _MAX_MANIFEST_BYTES
            or type(self.quarters) is not tuple
            or len(self.quarters) != 82
            or any(type(item) is not SecZipCensusQuarter for item in self.quarters)
            or tuple(item.period for item in self.quarters) != _PERIODS
        ):
            _refuse("82-quarter census receipt is malformed")
        if self.scope == "retained_noncanonical_zip_census" and (
            self.source_manifest_sha256 != RETAINED_ZIP_MANIFEST_SHA256
            or self.source_manifest_size_bytes != RETAINED_ZIP_MANIFEST_SIZE_BYTES
        ):
            _refuse("retained census scope lacks the literal manifest fingerprint")
        for quarter in self.quarters:
            quarter.__post_init__()
        if (
            type(self._validated_quarters_sha256) is not str
            or _SHA256.fullmatch(self._validated_quarters_sha256) is None
            or self._validated_quarters_sha256 != hash_payload(
                [quarter.to_payload() for quarter in self.quarters]
            )
        ):
            _refuse("validated quarter identity changed after the source read")
        try:
            preflight = build_sec_corpus_scale_preflight(
                SecQuarterScaleDescriptor(
                    period=item.period,
                    zip_sha256=item.zip_sha256,
                    zip_size_bytes=item.zip_size_bytes,
                    submission_accession_count=item.submission_accessions,
                    form4_accession_count=item.form4_accessions,
                    form4a_accession_count=item.form4a_accessions,
                    multi_owner_target_count=None,
                )
                for item in self.quarters
            )
        except SecCorpusScalePreflightError as exc:
            raise SecZipCorpusCensusError(
                "REFUSED: quarter receipt cannot enter the bounded planning model"
            ) from exc
        expected = (
            preflight.existing_zip_bytes,
            preflight.declared_submission_accessions,
            preflight.declared_form4_accessions,
            preflight.declared_form4a_accessions,
            preflight.declared_target_accessions,
            preflight.multi_owner_unknown_quarters,
            preflight.planned_distinct_artifacts_without_cache,
            preflight.maximum_attempts_at_three_per_artifact,
            preflight.ideal_minimum_dispatch_span_ms,
            preflight.successful_raw_parent_cap_bytes,
            preflight.existing_zip_plus_successful_parent_cap_bytes,
            preflight.declared_target_accessions,
        )
        actual = (
            self.existing_zip_bytes, self.submission_accessions,
            self.form4_accessions, self.form4a_accessions, self.target_accessions,
            self.multi_owner_unknown_quarters,
            self.planned_distinct_artifacts_without_cache,
            self.maximum_attempts_at_three_per_artifact,
            self.ideal_minimum_dispatch_span_ms,
            self.successful_raw_parent_cap_bytes,
            self.existing_zip_plus_successful_parent_cap_bytes,
            self.acceptance_metadata_records_required_without_cache,
        )
        if any(type(value) is not int for value in actual) or actual != expected:
            _refuse("census resource arithmetic is inconsistent")

    def to_payload(self) -> dict[str, object]:
        self.__post_init__()
        return {
            "kind": SEC_ZIP_CORPUS_CENSUS_KIND,
            "version": SEC_ZIP_CORPUS_CENSUS_VERSION,
            "scope": self.scope,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_manifest_size_bytes": self.source_manifest_size_bytes,
            "source_manifest_timestamp_basis": _TIMESTAMP_BASIS,
            "quarters": [item.to_payload() for item in self.quarters],
            "capacity_plan": {
                "basis": "measured_retained_ZIP_submission_counts_only",
                "one_master_gzip_request_per_quarter_without_cache": 82,
                "one_complete_txt_parent_per_form4_or_4a_without_cache": (
                    self.target_accessions
                ),
                "one_accession_specific_acceptance_metadata_record_per_target": (
                    self.acceptance_metadata_records_required_without_cache
                ),
                "acceptance_metadata_is_not_an_extra_request_when_extracted_from_parent": True,
                "existing_zip_bytes": self.existing_zip_bytes,
                "submission_accessions": self.submission_accessions,
                "form4_accessions": self.form4_accessions,
                "form4a_accessions": self.form4a_accessions,
                "target_accessions": self.target_accessions,
                "multi_owner_unknown_quarters": self.multi_owner_unknown_quarters,
                "planned_distinct_artifacts_without_cache": (
                    self.planned_distinct_artifacts_without_cache
                ),
                "maximum_attempts_at_three_per_artifact": (
                    self.maximum_attempts_at_three_per_artifact
                ),
                "ideal_minimum_dispatch_span_ms_excluding_work_and_backoff": (
                    self.ideal_minimum_dispatch_span_ms
                ),
                "successful_raw_parent_cap_bytes_excluding_overhead": (
                    self.successful_raw_parent_cap_bytes
                ),
                "existing_zip_plus_successful_parent_cap_bytes": (
                    self.existing_zip_plus_successful_parent_cap_bytes
                ),
                "planning_assumptions_are_not_a_crawl_permission_or_forecast": True,
            },
            "authority": {
                "zip_bytes_verified_against_source_manifest": True,
                "sec_origin_authenticated": False,
                "quarter_population_complete": False,
                "complete_text_coverage_verified": False,
                "acceptance_metadata_coverage_verified": False,
                "canonical_evidence": False,
                "point_in_time_data": False,
                "outcome_access_authorized": False,
                "qc_job_authorized": False,
                "broker_or_trading_authorized": False,
                "research_looks": 0,
                "authorized_outcome_looks": 0,
                "consumed_outcome_looks": 0,
            },
        }

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


def _expected_url(period: str) -> str:
    route = "datastandardsinnovation" if period == "2026Q2" else "structureddata"
    return _SOURCE_PREFIX + route + _SOURCE_SUFFIX + period.lower() + "_form345.zip"


def _valid_submission_headers(headers: tuple[str, ...]) -> bool:
    return (
        0 < len(headers) <= MAX_HEADER_COLUMNS
        # Exact-text check first: set() on a forged unhashable header
        # would escape as TypeError instead of a typed refusal.
        and all(type(value) is str and _HEADER.fullmatch(value) for value in headers)
        and len(headers) == len(set(headers))
        and _REQUIRED_SUBMISSION_HEADERS <= set(headers)
    )


def _plain_root(value: str | Path) -> Path:
    if not isinstance(value, (str, Path)):
        _refuse("census root must be an absolute local path")
    path = Path(value)
    if not path.is_absolute():
        _refuse("census root must be an absolute local path")
    try:
        if path != path.resolve(strict=True):
            _refuse("census root must not redirect through symlinks")
        status = path.lstat()
    except (OSError, RuntimeError) as exc:
        raise SecZipCorpusCensusError("REFUSED: census root is unavailable") from exc
    if not stat.S_ISDIR(status.st_mode):
        _refuse("census root must be a regular directory")
    return path


class _PinnedZipRoot:
    """Pin every directory component and read leaves relative to the root fd."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.root_fd: int | None = None

    def __enter__(self) -> _PinnedZipRoot:
        if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
            _refuse("directory-handle confinement is unavailable")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        current: int | None = None
        try:
            for index, component in enumerate(self.path.parts):
                opened = (
                    os.open(component, flags) if index == 0 else
                    os.open(component, flags, dir_fd=current)
                )
                if current is not None:
                    os.close(current)
                current = opened
            self.root_fd = current
            current = None
            self.check()
            return self
        except SecZipCorpusCensusError:
            self.__exit__(None, None, None)
            raise
        except (OSError, TypeError, NotImplementedError) as exc:
            self.__exit__(None, None, None)
            raise SecZipCorpusCensusError(
                "REFUSED: ZIP corpus directory handle could not be pinned"
            ) from exc
        finally:
            if current is not None:
                os.close(current)

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        if self.root_fd is not None:
            os.close(self.root_fd)
            self.root_fd = None

    def check(self) -> None:
        if self.root_fd is None:
            _refuse("ZIP corpus directory handle is closed")
        try:
            named = self.path.lstat()
            opened = os.fstat(self.root_fd)
        except OSError as exc:
            raise SecZipCorpusCensusError(
                "REFUSED: ZIP corpus directory path became unreadable"
            ) from exc
        if (
            not stat.S_ISDIR(named.st_mode)
            or (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            _refuse("ZIP corpus directory path changed during census")

    def names(self) -> set[str]:
        self.check()
        try:
            names = os.listdir(self.root_fd)
        except (OSError, TypeError, NotImplementedError) as exc:
            raise SecZipCorpusCensusError(
                "REFUSED: ZIP inventory cannot be listed through its pinned handle"
            ) from exc
        self.check()
        if len(names) != len(set(names)):
            _refuse("ZIP inventory repeats a filename")
        return set(names)

    def read(self, name: str, *, max_bytes: int) -> bytes:
        if (
            type(name) is not str
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name) is None
            or type(max_bytes) is not int
            or max_bytes <= 0
        ):
            _refuse("source file request escapes the pinned ZIP directory")
        self.check()
        try:
            named_before = os.stat(name, dir_fd=self.root_fd, follow_symlinks=False)
            if (
                not stat.S_ISREG(named_before.st_mode)
                or named_before.st_nlink != 1
                or not 0 < named_before.st_size <= max_bytes
            ):
                _refuse("source file must be a bounded regular single-link file")
            descriptor = os.open(
                name,
                os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
                dir_fd=self.root_fd,
            )
            try:
                before = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(before.st_mode)
                    or before.st_nlink != 1
                    or (before.st_dev, before.st_ino, before.st_size)
                    != (named_before.st_dev, named_before.st_ino, named_before.st_size)
                ):
                    _refuse("source file changed before bounded read")
                chunks: list[bytes] = []
                remaining = max_bytes + 1
                while remaining:
                    part = os.read(descriptor, min(1024 * 1024, remaining))
                    if not part:
                        break
                    chunks.append(part)
                    remaining -= len(part)
                raw = b"".join(chunks)
                after = os.fstat(descriptor)
            finally:
                os.close(descriptor)
            named_after = os.stat(name, dir_fd=self.root_fd, follow_symlinks=False)
        except SecZipCorpusCensusError:
            raise
        except (OSError, TypeError, NotImplementedError) as exc:
            raise SecZipCorpusCensusError(
                "REFUSED: source file could not be read through pinned directory"
            ) from exc
        self.check()
        identities = (
            (state.st_dev, state.st_ino, state.st_size, state.st_mtime_ns)
            for state in (named_before, before, after, named_after)
        )
        first = next(identities)
        if (
            any(identity != first for identity in identities)
            or not stat.S_ISREG(named_after.st_mode)
            or named_after.st_nlink != 1
            or len(raw) != after.st_size
            or len(raw) > max_bytes
        ):
            _refuse("source file changed during its pinned bounded read")
        return raw


def _manifest_bindings(raw: bytes) -> tuple[_ManifestBinding, ...]:
    try:
        text = raw.decode("utf-8", errors="strict")
        rows = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise SecZipCorpusCensusError("REFUSED: source manifest CSV is malformed") from exc
    if (
        len(rows) != 83
        or tuple(rows[0]) != _MANIFEST_HEADER
        or any(len(row) != len(_MANIFEST_HEADER) for row in rows[1:])
    ):
        _refuse("source manifest must contain the exact 82-quarter schema")
    bindings = []
    for period, row in zip(_PERIODS, rows[1:], strict=True):
        listed_period, filename, url, size, digest, stamp, basis, commit, index = row
        if listed_period != period or filename != period.lower() + "_form345.zip":
            _refuse("source manifest period or filename is not the exact contiguous set")
        if (
            url != _expected_url(period)
            or len(size) > len(str(MAX_ARCHIVE_BYTES))
            or not size.isascii()
            or re.fullmatch(r"[1-9][0-9]*", size) is None
            or int(size) > MAX_ARCHIVE_BYTES
            or _SHA256.fullmatch(digest) is None
            or _LOCAL_STAMP.fullmatch(stamp) is None
            or basis != _TIMESTAMP_BASIS
            or commit != _CAPTURE_COMMIT
            or index != _SOURCE_INDEX_URL
        ):
            _refuse("source manifest URL, fingerprint or provenance field is invalid")
        try:
            datetime.fromisoformat(stamp[:-1] + "+00:00")
        except ValueError as exc:
            raise SecZipCorpusCensusError(
                "REFUSED: source manifest local timestamp is invalid"
            ) from exc
        bindings.append(_ManifestBinding(period, filename, url, int(size), digest, stamp))
    return tuple(bindings)


def _submission_census(
    zip_bytes: bytes,
) -> tuple[str, int, str, tuple[str, ...], tuple[int, int, int, int, int, int]]:
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as archive:
            info = archive.getinfo("SUBMISSION.tsv")
            with archive.open(info, "r") as member:
                header_line = member.readline(_MAX_SUBMISSION_HEADER_BYTES + 1)
            if (
                not header_line.endswith(b"\n")
                or len(header_line) > _MAX_SUBMISSION_HEADER_BYTES
                or b"\x00" in header_line
            ):
                _refuse("SUBMISSION header line is malformed or over budget")
            try:
                physical_header = tuple(
                    header_line.decode("utf-8-sig", errors="strict")
                    .rstrip("\r\n").split("\t")
                )
            except UnicodeDecodeError as exc:
                raise SecZipCorpusCensusError(
                    "REFUSED: SUBMISSION header is not UTF-8"
                ) from exc
            if not _valid_submission_headers(physical_header):
                _refuse("SUBMISSION header lacks exact required columns")
            with archive.open(info, "r") as member:
                reader = csv.reader(
                    io.TextIOWrapper(member, encoding="utf-8-sig", newline=""),
                    delimiter="\t", quotechar='"', doublequote=True,
                    escapechar=None, skipinitialspace=False, strict=True,
                )
                parsed_header = tuple(next(reader))
                if parsed_header != physical_header:
                    _refuse("SUBMISSION logical and physical headers disagree")
                accession_column = parsed_header.index("ACCESSION_NUMBER")
                form_column = parsed_header.index("DOCUMENT_TYPE")
                counts = {form: 0 for form in _FORM_TYPES}
                seen: set[str] = set()
                for number, row in enumerate(reader, start=1):
                    if number > MAX_ROWS_PER_TABLE:
                        _refuse("SUBMISSION row count exceeds the bounded table cap")
                    if (
                        len(row) != len(parsed_header)
                        or any(len(value) > MAX_FIELD_CHARACTERS for value in row)
                    ):
                        _refuse("SUBMISSION contains a blank, ragged or oversized row")
                    accession = row[accession_column]
                    if _ACCESSION.fullmatch(accession) is None:
                        _refuse("SUBMISSION accession is malformed")
                    if accession in seen:
                        _refuse("SUBMISSION contains a duplicate accession")
                    seen.add(accession)
                    form = row[form_column]
                    if form not in counts:
                        _refuse("SUBMISSION document type is outside the six-form context")
                    counts[form] += 1
    except SecZipCorpusCensusError:
        raise
    except (zipfile.BadZipFile, RuntimeError, EOFError, OSError, csv.Error,
            UnicodeDecodeError, StopIteration) as exc:
        raise SecZipCorpusCensusError(
            "REFUSED: SUBMISSION stream failed strict bounded decoding"
        ) from exc
    return (
        hash_bytes(header_line), len(header_line), info.filename,
        physical_header, tuple(counts[form] for form in _FORM_TYPES),
    )


def _census_quarter(raw: bytes, binding: _ManifestBinding) -> SecZipCensusQuarter:
    year, quarter = int(binding.period[:4]), int(binding.period[-1])
    # The CSV clock is only an unverified local file observation. Feeding it
    # into IB-1A's validator does not turn its returned identity into evidence
    # of SEC retrieval time; this census never publishes an IB-1A snapshot.
    try:
        observed_at = datetime.fromisoformat(
            binding.local_last_write_utc[:-1] + "+00:00"
        )
    except ValueError as exc:
        raise SecZipCorpusCensusError(
            "REFUSED: source manifest local timestamp is invalid"
        ) from exc
    try:
        inspected = inspect_sec_bulk_archive(
            raw,
            SecBulkSource(
                year=year, quarter=quarter, source_url=binding.source_url,
                git_commit=_CAPTURE_COMMIT, retrieved_at=observed_at,
            ),
        )
    except SecBulkSnapshotError as exc:
        raise SecZipCorpusCensusError(
            "REFUSED: ZIP member integrity or inventory failed"
        ) from exc
    if (
        inspected.archive_sha256 != binding.sha256
        or inspected.archive_size_bytes != binding.size_bytes
    ):
        _refuse("ZIP fingerprint disagrees with the bound source manifest")
    members = {item.name: item for item in inspected.members}
    member = members["SUBMISSION.tsv"]
    header_sha, header_size, _, headers, counts = _submission_census(raw)
    if header_size > member.size_bytes:
        _refuse("SUBMISSION header exceeds its integrity-checked member")
    return SecZipCensusQuarter(
        period=binding.period,
        zip_sha256=inspected.archive_sha256,
        zip_size_bytes=inspected.archive_size_bytes,
        source_url_from_retained_manifest=binding.source_url,
        local_last_write_utc_unverified=binding.local_last_write_utc,
        submission_member_sha256=member.sha256,
        submission_member_size_bytes=member.size_bytes,
        submission_header_line_sha256=header_sha,
        submission_headers=headers,
        form_counts=counts,
    )


def _census_zip_corpus(
    root: str | Path,
    *,
    expected_manifest_sha256: str,
    scope: str,
) -> SecZipCorpusCensus:
    """Private synthetic seam; only the public wrapper grants retained scope."""
    if (
        type(expected_manifest_sha256) is not str
        or _SHA256.fullmatch(expected_manifest_sha256) is None
        or type(scope) is not str
        or scope not in {"retained_noncanonical_zip_census", "synthetic_test_census"}
        or (scope == "retained_noncanonical_zip_census"
            and expected_manifest_sha256 != RETAINED_ZIP_MANIFEST_SHA256)
    ):
        _refuse("census source scope or expected manifest fingerprint is invalid")
    directory = _plain_root(root)
    with _PinnedZipRoot(directory) as pinned:
        manifest = pinned.read(_MANIFEST_NAME, max_bytes=_MAX_MANIFEST_BYTES)
        if (
            hash_bytes(manifest) != expected_manifest_sha256
            or (scope == "retained_noncanonical_zip_census"
                and len(manifest) != RETAINED_ZIP_MANIFEST_SIZE_BYTES)
        ):
            _refuse("source manifest fingerprint differs from the pinned bytes")
        bindings = _manifest_bindings(manifest)
        expected_zip_names = {item.filename for item in bindings}
        observed_zip_names = {name for name in pinned.names() if name.endswith(".zip")}
        if observed_zip_names != expected_zip_names:
            _refuse("ZIP inventory differs from the exact 82 bound names")
        quarters: list[SecZipCensusQuarter] = []
        for binding in bindings:
            raw = pinned.read(binding.filename, max_bytes=MAX_ARCHIVE_BYTES)
            if (
                len(raw) != binding.size_bytes
                or hashlib.sha256(raw).hexdigest() != binding.sha256
            ):
                _refuse("ZIP fingerprint disagrees with the bound source manifest")
            quarters.append(_census_quarter(raw, binding))
            del raw  # Only one compressed quarter can be held by the loop.
    frozen = tuple(quarters)
    try:
        preflight = build_sec_corpus_scale_preflight(
            SecQuarterScaleDescriptor(
                period=item.period,
                zip_sha256=item.zip_sha256,
                zip_size_bytes=item.zip_size_bytes,
                submission_accession_count=item.submission_accessions,
                form4_accession_count=item.form4_accessions,
                form4a_accession_count=item.form4a_accessions,
                multi_owner_target_count=None,
            )
            for item in frozen
        )
    except SecCorpusScalePreflightError as exc:
        raise SecZipCorpusCensusError(
            "REFUSED: measured ZIP counts exceed the bounded planning model"
        ) from exc
    return SecZipCorpusCensus(
        scope=scope,
        source_manifest_sha256=hash_bytes(manifest),
        source_manifest_size_bytes=len(manifest),
        quarters=frozen,
        existing_zip_bytes=preflight.existing_zip_bytes,
        submission_accessions=preflight.declared_submission_accessions,
        form4_accessions=preflight.declared_form4_accessions,
        form4a_accessions=preflight.declared_form4a_accessions,
        target_accessions=preflight.declared_target_accessions,
        multi_owner_unknown_quarters=preflight.multi_owner_unknown_quarters,
        planned_distinct_artifacts_without_cache=(
            preflight.planned_distinct_artifacts_without_cache
        ),
        maximum_attempts_at_three_per_artifact=(
            preflight.maximum_attempts_at_three_per_artifact
        ),
        ideal_minimum_dispatch_span_ms=preflight.ideal_minimum_dispatch_span_ms,
        successful_raw_parent_cap_bytes=preflight.successful_raw_parent_cap_bytes,
        existing_zip_plus_successful_parent_cap_bytes=(
            preflight.existing_zip_plus_successful_parent_cap_bytes
        ),
        acceptance_metadata_records_required_without_cache=(
            preflight.declared_target_accessions
        ),
        _validated_quarters_sha256=hash_payload(
            [quarter.to_payload() for quarter in frozen]
        ),
        _construction_token=(
            _RETAINED_CONSTRUCTION_TOKEN if scope == "retained_noncanonical_zip_census"
            else _SYNTHETIC_CONSTRUCTION_TOKEN
        ),
    )


def census_retained_sec_zip_corpus(root: str | Path) -> SecZipCorpusCensus:
    """Read the exact 82 retained ZIPs offline and return a zero-authority census."""
    return _census_zip_corpus(
        root,
        expected_manifest_sha256=RETAINED_ZIP_MANIFEST_SHA256,
        scope="retained_noncanonical_zip_census",
    )


__all__ = [
    "RETAINED_ZIP_MANIFEST_SHA256",
    "SEC_ZIP_CORPUS_CENSUS_KIND",
    "SEC_ZIP_CORPUS_CENSUS_VERSION",
    "SecZipCensusQuarter",
    "SecZipCorpusCensus",
    "SecZipCorpusCensusError",
    "census_retained_sec_zip_corpus",
]
