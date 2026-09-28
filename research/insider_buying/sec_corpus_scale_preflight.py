"""Pure, synthetic-first resource preflight for an 82-quarter SEC source plan.

This accepts *caller-declared* ZIP descriptors and accession counts, not ZIP
bytes or independently loaded snapshots. It performs no filesystem, SEC,
provider, network, outcome, QC, broker, or trading operation. Even exact
arithmetic on 82 plausible descriptors does not authenticate a source,
establish quarter/index completeness, provide point-in-time availability, or
authorize a crawl or backtest.

The one-master-plus-one-complete-submission request model mirrors a proposed
acquisition route. Its 8 MiB successful-parent cap, three-attempt ceiling and
two request starts per second are *planning assumptions*, not observations or
permissions. The dispatch span excludes transfer/parse time, denial, retries,
backoff and scheduler pauses. The byte cap excludes derived children, report,
journal, decompressed indexes and any retained failed response. Neither value
is a storage or calendar-time forecast.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from data.hashing import hash_payload


SEC_CORPUS_SCALE_PREFLIGHT_VERSION = "INSETF-SEC-CORPUS-SCALE-PREFLIGHT-v1"
MAX_DECLARED_ZIP_BYTES = 512 * 1024 * 1024
MAX_DECLARED_SUBMISSION_ACCESSIONS = 5_000_000
SUCCESSFUL_RAW_PARENT_CAP_BYTES = 8 * 1024 * 1024
REQUEST_STARTS_PER_SECOND = 2
MAX_ATTEMPTS_PER_ARTIFACT = 3
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PERIOD = re.compile(r"[0-9]{4}Q[1-4]\Z")
_EXPECTED_PERIODS = tuple(
    f"{year}Q{quarter}"
    for year in range(2006, 2027)
    for quarter in range(1, 5)
    if (year, quarter) <= (2026, 2)
)


class SecCorpusScalePreflightError(ValueError):
    """The prospective, caller-declared 82-quarter plan is malformed."""


def _refuse(reason: str) -> None:
    raise SecCorpusScalePreflightError(f"REFUSED: {reason}")


def _count(value: object, *, label: str) -> int:
    if (type(value) is not int or value < 0
            or value > MAX_DECLARED_SUBMISSION_ACCESSIONS):
        _refuse(f"{label} is not a bounded exact nonnegative count")
    return value


@dataclass(frozen=True)
class SecQuarterScaleDescriptor:
    """Caller declarations only; the SHA-256 is not verified against ZIP bytes."""

    period: str
    zip_sha256: str
    zip_size_bytes: int
    submission_accession_count: int
    form4_accession_count: int
    form4a_accession_count: int
    multi_owner_target_count: int | None

    def __post_init__(self) -> None:
        if type(self) is not SecQuarterScaleDescriptor:
            _refuse("an exact quarter descriptor type is required")
        if type(self.period) is not str or _PERIOD.fullmatch(self.period) is None:
            _refuse("quarter descriptor period is malformed")
        if type(self.zip_sha256) is not str or _SHA256.fullmatch(self.zip_sha256) is None:
            _refuse("quarter ZIP digest is not a lowercase SHA-256")
        if (type(self.zip_size_bytes) is not int
                or not 0 < self.zip_size_bytes <= MAX_DECLARED_ZIP_BYTES):
            _refuse("quarter ZIP size is not a bounded positive exact integer")
        submissions = _count(self.submission_accession_count, label="submission count")
        form4 = _count(self.form4_accession_count, label="Form 4 count")
        form4a = _count(self.form4a_accession_count, label="Form 4/A count")
        targets = form4 + form4a
        if targets > submissions:
            _refuse("Form 4/4-A counts exceed declared submissions")
        if self.multi_owner_target_count is not None:
            multi = _count(self.multi_owner_target_count, label="multi-owner count")
            if multi > targets:
                _refuse("multi-owner count exceeds Form 4/4-A targets")

    def to_payload(self) -> dict[str, object]:
        self.__post_init__()
        return {
            "period": self.period,
            "zip_sha256": self.zip_sha256,
            "zip_size_bytes": self.zip_size_bytes,
            "submission_accession_count": self.submission_accession_count,
            "form4_accession_count": self.form4_accession_count,
            "form4a_accession_count": self.form4a_accession_count,
            "multi_owner_target_count": self.multi_owner_target_count,
        }


@dataclass(frozen=True)
class SecCorpusScalePreflight:
    """Bounded arithmetic from 82 copied declarations, with no evidence claim."""

    quarters: tuple[SecQuarterScaleDescriptor, ...]
    existing_zip_bytes: int
    declared_submission_accessions: int
    declared_form4_accessions: int
    declared_form4a_accessions: int
    declared_target_accessions: int
    declared_multi_owner_targets: int | None
    multi_owner_unknown_quarters: int
    planned_distinct_artifacts_without_cache: int
    maximum_attempts_at_three_per_artifact: int
    ideal_minimum_dispatch_span_ms: int
    successful_raw_parent_cap_bytes: int
    existing_zip_plus_successful_parent_cap_bytes: int

    def __post_init__(self) -> None:
        if type(self) is not SecCorpusScalePreflight:
            _refuse("an exact scale-preflight result type is required")
        if (type(self.quarters) is not tuple or len(self.quarters) != 82
                or any(type(item) is not SecQuarterScaleDescriptor
                       for item in self.quarters)
                or tuple(item.period for item in self.quarters) != _EXPECTED_PERIODS):
            _refuse("exactly 82 contiguous quarter descriptors are required")
        for descriptor in self.quarters:
            descriptor.__post_init__()
        zip_bytes = sum(item.zip_size_bytes for item in self.quarters)
        submissions = sum(item.submission_accession_count for item in self.quarters)
        form4 = sum(item.form4_accession_count for item in self.quarters)
        form4a = sum(item.form4a_accession_count for item in self.quarters)
        targets = form4 + form4a
        missing_owner_counts = sum(
            item.multi_owner_target_count is None for item in self.quarters
        )
        multi_owners = (
            None if missing_owner_counts else
            sum(item.multi_owner_target_count for item in self.quarters)
        )
        requests = len(self.quarters) + targets
        expected = (
            zip_bytes, submissions, form4, form4a, targets, multi_owners,
            missing_owner_counts, requests, requests * MAX_ATTEMPTS_PER_ARTIFACT,
            (requests - 1) * (1000 // REQUEST_STARTS_PER_SECOND),
            requests * SUCCESSFUL_RAW_PARENT_CAP_BYTES,
            zip_bytes + requests * SUCCESSFUL_RAW_PARENT_CAP_BYTES,
        )
        observed = (
            self.existing_zip_bytes, self.declared_submission_accessions,
            self.declared_form4_accessions, self.declared_form4a_accessions,
            self.declared_target_accessions, self.declared_multi_owner_targets,
            self.multi_owner_unknown_quarters,
            self.planned_distinct_artifacts_without_cache,
            self.maximum_attempts_at_three_per_artifact,
            self.ideal_minimum_dispatch_span_ms,
            self.successful_raw_parent_cap_bytes,
            self.existing_zip_plus_successful_parent_cap_bytes,
        )
        if observed != expected or any(
            type(value) is not int for value in observed if value is not None
        ):
            _refuse("scale-preflight resource arithmetic is inconsistent")

    def to_payload(self) -> dict[str, object]:
        self.__post_init__()
        return {
            "version": SEC_CORPUS_SCALE_PREFLIGHT_VERSION,
            "scope": "caller_declared_unverified_82_quarter_plan",
            "quarters": [item.to_payload() for item in self.quarters],
            "assumptions": {
                "master_gzip_per_quarter": 1,
                "complete_submission_per_form4_or_4a": 1,
                "internal_request_starts_per_second": REQUEST_STARTS_PER_SECOND,
                "maximum_attempts_per_artifact": MAX_ATTEMPTS_PER_ARTIFACT,
                "successful_raw_parent_cap_bytes_per_artifact": (
                    SUCCESSFUL_RAW_PARENT_CAP_BYTES
                ),
            },
            "resource_arithmetic": {
                "existing_zip_bytes_caller_declared": self.existing_zip_bytes,
                "submission_accessions_caller_declared": (
                    self.declared_submission_accessions
                ),
                "form4_accessions_caller_declared": self.declared_form4_accessions,
                "form4a_accessions_caller_declared": self.declared_form4a_accessions,
                "target_accessions_caller_declared": self.declared_target_accessions,
                "multi_owner_targets_caller_declared_if_all_known": (
                    self.declared_multi_owner_targets
                ),
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
                "successful_raw_parent_cap_bytes_excluding_derived_and_overhead": (
                    self.successful_raw_parent_cap_bytes
                ),
                "declared_existing_zip_plus_successful_parent_cap_bytes": (
                    self.existing_zip_plus_successful_parent_cap_bytes
                ),
            },
            "authority": {
                "zip_bytes_verified": False,
                "accession_counts_verified": False,
                "master_index_membership_verified": False,
                "source_authenticated": False,
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


def build_sec_corpus_scale_preflight(
    quarters: Iterable[SecQuarterScaleDescriptor],
) -> SecCorpusScalePreflight:
    """Consume exactly 82 descriptors once; copy scalars before arithmetic.

    An input's declared count, hash or size is never upgraded to an observed
    source fact by this function. Missing quarters, duplicates, reordering,
    extras, incoherent counts or budget-cap violations refuse the plan.
    """
    try:
        iterator = iter(quarters)
    except TypeError as exc:
        raise SecCorpusScalePreflightError(
            "REFUSED: quarter descriptors must be iterable"
        ) from exc
    copied: list[SecQuarterScaleDescriptor] = []
    sentinel = object()
    for expected_period in _EXPECTED_PERIODS:
        item = next(iterator, sentinel)
        if type(item) is not SecQuarterScaleDescriptor:
            _refuse("exactly 82 contiguous quarter descriptors are required")
        payload = item.to_payload()
        copy = SecQuarterScaleDescriptor(**payload)
        if copy.period != expected_period:
            _refuse("exactly 82 contiguous quarter descriptors are required")
        copied.append(copy)
    if next(iterator, sentinel) is not sentinel:
        _refuse("exactly 82 contiguous quarter descriptors are required")
    frozen = tuple(copied)
    zip_bytes = sum(item.zip_size_bytes for item in frozen)
    submissions = sum(item.submission_accession_count for item in frozen)
    form4 = sum(item.form4_accession_count for item in frozen)
    form4a = sum(item.form4a_accession_count for item in frozen)
    targets = form4 + form4a
    missing_owner_counts = sum(item.multi_owner_target_count is None for item in frozen)
    multi_owners = (
        None if missing_owner_counts else sum(item.multi_owner_target_count for item in frozen)
    )
    requests = len(frozen) + targets
    successful_cap = requests * SUCCESSFUL_RAW_PARENT_CAP_BYTES
    return SecCorpusScalePreflight(
        quarters=frozen,
        existing_zip_bytes=zip_bytes,
        declared_submission_accessions=submissions,
        declared_form4_accessions=form4,
        declared_form4a_accessions=form4a,
        declared_target_accessions=targets,
        declared_multi_owner_targets=multi_owners,
        multi_owner_unknown_quarters=missing_owner_counts,
        planned_distinct_artifacts_without_cache=requests,
        maximum_attempts_at_three_per_artifact=requests * MAX_ATTEMPTS_PER_ARTIFACT,
        ideal_minimum_dispatch_span_ms=(requests - 1) * (
            1000 // REQUEST_STARTS_PER_SECOND
        ),
        successful_raw_parent_cap_bytes=successful_cap,
        existing_zip_plus_successful_parent_cap_bytes=zip_bytes + successful_cap,
    )


__all__ = [
    "SEC_CORPUS_SCALE_PREFLIGHT_VERSION",
    "SecCorpusScalePreflight",
    "SecCorpusScalePreflightError",
    "SecQuarterScaleDescriptor",
    "build_sec_corpus_scale_preflight",
]
