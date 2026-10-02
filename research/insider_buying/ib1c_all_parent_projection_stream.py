"""Pure, bounded all-parent projection accounting for the two IB-1B pilot quarters.

The caller supplies the exact complete-submission bytes (or an explicit
missing marker) in the order of an independently rebuilt all-Form-4 locator
manifest. This module does no I/O. It retains neither a parent byte image nor
an XML/header image, acceptance-time string, or reporting-owner identities;
each accession contributes one small, hash-bound outcome to a streaming
digest. A caller may observe those small outcomes, but any
observer side effect is outside this zero-I/O boundary and an observer failure
aborts the aggregate rather than returning a partial receipt.

Complete *accounting* is not complete *projection*: a receipt can cover every
locator while naming refusals. Even an all-projected receipt verifies neither
SEC origin, acceptance timezone, amendment linkage, point-in-time availability,
canonical source eligibility, outcomes, nor QC/backtest authority. This is
accounting only: the hashes cannot reconstruct the acceptance string or owner
identities needed by a later actual IB-1C source processor. The typed
locator manifest alone is not source proof; a consumer must rebuild it from
the exact raw-bound IB-1B snapshots and master receipts.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying.ib1b_all_form4_parent_locators import (
    AllForm4ParentLocator,
    AllForm4ParentLocatorError,
    AllForm4ParentLocatorManifest,
)
from research.insider_buying.sec_complete_submission import (
    MAX_COMPLETE_SUBMISSION_BYTES,
    SecCompleteSubmissionError,
    SecCompleteSubmissionTarget,
    project_sec_complete_submission,
)


ALL_PARENT_PROJECTION_KIND = "insider-buying-ib1c-all-parent-projection-accounting"
ALL_PARENT_PROJECTION_VERSION = 1
MAX_PARENT_BYTES = MAX_COMPLETE_SUBMISSION_BYTES
MAX_REFUSAL_EXAMPLES = 32
MAX_ROW_JSON_BYTES = 2048
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_STATUSES = (
    "PROJECTED", "MISSING_RAW", "MALFORMED_RAW", "UNBOUNDED_RAW",
    "PROJECTION_REFUSED",
)
_REFUSALS = _STATUSES[1:]
_FACTORY_TOKEN = object()


class AllParentProjectionError(ValueError):
    """Exact stream alignment or complete accounting failed closed."""


def _refuse(message: str) -> None:
    raise AllParentProjectionError(f"REFUSED: {message}")


def _hash(value: object, *, label: str) -> str:
    if type(value) is not str or _HASH.fullmatch(value) is None:
        _refuse(f"{label} is not lowercase SHA-256")
    return value


def _row_line(row: "AllParentProjectionRow") -> bytes:
    raw = (canonical_json(row.to_payload()) + "\n").encode("utf-8")
    if len(raw) > MAX_ROW_JSON_BYTES:
        _refuse("projection row exceeds its fixed byte budget")
    return raw


@dataclass(frozen=True, slots=True)
class RawParentProjectionInput:
    accession_number: str
    raw_bytes: object  # Exactly bytes or None; invalid types become named refusals.


@dataclass(frozen=True, slots=True)
class AllParentProjectionRow:
    """Small per-accession accounting event, never a reusable IB-1C source."""

    period: str
    accession_number: str
    locator_sha256: str
    status: str
    raw_parent_sha256: str | None
    projection_sha256: str | None
    header_sha256: str | None
    xml_sha256: str | None
    accepted_at_raw_sha256: str | None
    ordered_owner_ciks_sha256: str | None
    owner_count: int

    def to_payload(self) -> dict[str, object]:
        if (
            type(self) is not AllParentProjectionRow
            or type(self.period) is not str
            or self.period not in {"2022Q4", "2023Q1"}
            or type(self.accession_number) is not str
            or _ACCESSION.fullmatch(self.accession_number) is None
            or type(self.status) is not str
            or self.status not in _STATUSES
            or type(self.owner_count) is not int
            or not 0 <= self.owner_count <= 256
        ):
            _refuse("projection row identity or status is malformed")
        _hash(self.locator_sha256, label="row locator")
        hashes = (
            self.raw_parent_sha256, self.projection_sha256,
            self.header_sha256, self.xml_sha256,
            self.accepted_at_raw_sha256, self.ordered_owner_ciks_sha256,
        )
        for value in hashes:
            if value is not None:
                _hash(value, label="row evidence")
        if self.status == "PROJECTED":
            if any(value is None for value in hashes) or self.owner_count == 0:
                _refuse("successful projection is missing an evidence hash")
        elif (
            any(value is not None for value in hashes[1:])
            or self.owner_count != 0
            or (self.status in {"MISSING_RAW", "MALFORMED_RAW", "UNBOUNDED_RAW"}
                and self.raw_parent_sha256 is not None)
            or (self.status == "PROJECTION_REFUSED"
                and self.raw_parent_sha256 is None)
        ):
            _refuse("refused projection claims successful evidence")
        return {
            "period": self.period,
            "accession_number": self.accession_number,
            "locator_sha256": self.locator_sha256,
            "status": self.status,
            "raw_parent_sha256": self.raw_parent_sha256,
            "projection_sha256": self.projection_sha256,
            "header_sha256": self.header_sha256,
            "xml_sha256": self.xml_sha256,
            "accepted_at_raw_sha256": self.accepted_at_raw_sha256,
            "ordered_owner_ciks_sha256": self.ordered_owner_ciks_sha256,
            "owner_count": self.owner_count,
        }


@dataclass(frozen=True, slots=True)
class AllParentProjectionReceipt:
    """Complete accounting digest; contains no reconstructible source fields."""

    locator_manifest_sha256: str
    expected_count: int
    accounted_count: int
    projected_count: int
    refused_count: int
    row_inventory_sha256: str
    refusal_inventory_sha256: str
    refusal_counts: tuple[tuple[str, int], ...]
    refusal_examples: tuple[tuple[str, str], ...]
    content_sha256: str
    _factory_token: object = field(repr=False, compare=False, default=None)

    @property
    def all_projected(self) -> bool:
        return self.refused_count == 0

    @property
    def canonical(self) -> bool:
        return False

    @property
    def source_authenticated(self) -> bool:
        return False

    @property
    def acceptance_timezone_verified(self) -> bool:
        return False

    @property
    def point_in_time_data(self) -> bool:
        return False

    @property
    def amendment_lineage_verified(self) -> bool:
        return False

    @property
    def outcome_looks(self) -> int:
        return 0

    @property
    def qc_jobs(self) -> int:
        return 0

    def _payload(self) -> dict[str, object]:
        return {
            "kind": ALL_PARENT_PROJECTION_KIND,
            "version": ALL_PARENT_PROJECTION_VERSION,
            "source_scope": "TWO_QUARTER_ALL_FORM4_PARENT_NONCANONICAL",
            "locator_manifest_sha256": self.locator_manifest_sha256,
            "expected_count": self.expected_count,
            "accounted_count": self.accounted_count,
            "projected_count": self.projected_count,
            "refused_count": self.refused_count,
            "all_rows_accounted": True,
            "all_projected": self.all_projected,
            "row_inventory_sha256": self.row_inventory_sha256,
            "refusal_inventory_sha256": self.refusal_inventory_sha256,
            "refusal_counts": [
                {"status": status, "count": count}
                for status, count in self.refusal_counts
            ],
            "refusal_examples": [
                {"accession_number": accession, "status": status}
                for accession, status in self.refusal_examples
            ],
            "raw_parent_bytes_retained": False,
            "complete_parent_corpus_projected": False,
            "source_authenticated": False,
            "acceptance_timezone_verified": False,
            "acceptance_metadata_verified": False,
            "amendment_lineage_verified": False,
            "point_in_time_data": False,
            "canonical": False,
            "direct_ib1c_authority": False,
            "outcome_looks": 0,
            "qc_jobs": 0,
        }

    def verify_digest(self) -> None:
        if (
            type(self) is not AllParentProjectionReceipt
            or self._factory_token is not _FACTORY_TOKEN
            or any(
                type(value) is not int or value < 0
                for value in (
                    self.expected_count, self.accounted_count,
                    self.projected_count, self.refused_count,
                )
            )
            or self.expected_count != self.accounted_count
            or self.expected_count == 0
            or self.projected_count + self.refused_count != self.expected_count
            or type(self.refusal_counts) is not tuple
            or any(
                type(item) is not tuple or len(item) != 2
                or type(item[0]) is not str
                or item[0] not in _REFUSALS
                or type(item[1]) is not int or item[1] <= 0
                for item in self.refusal_counts
            )
            or tuple(item[0] for item in self.refusal_counts)
            != tuple(status for status in _REFUSALS
                     if status in {item[0] for item in self.refusal_counts})
            or sum(item[1] for item in self.refusal_counts) != self.refused_count
            or type(self.refusal_examples) is not tuple
            or len(self.refusal_examples) != min(self.refused_count, MAX_REFUSAL_EXAMPLES)
            or any(
                type(item) is not tuple or len(item) != 2
                or type(item[0]) is not str or _ACCESSION.fullmatch(item[0]) is None
                or type(item[1]) is not str
                or item[1] not in _REFUSALS
                or item[1] not in {status for status, _ in self.refusal_counts}
                for item in self.refusal_examples
            )
            or len({item[0] for item in self.refusal_examples})
            != len(self.refusal_examples)
        ):
            _refuse("receipt counts, refusal inventory, or construction changed")
        for value in (
            self.locator_manifest_sha256, self.row_inventory_sha256,
            self.refusal_inventory_sha256, self.content_sha256,
        ):
            _hash(value, label="receipt hash")
        if hash_payload(self._payload()) != self.content_sha256:
            _refuse("receipt digest changed")

    def to_payload(self) -> dict[str, object]:
        self.verify_digest()
        return {**self._payload(), "content_sha256": self.content_sha256}


def _row(locator: AllForm4ParentLocator, raw: object, index_sha: str) -> AllParentProjectionRow:
    locator_sha = hash_payload(locator.to_payload())
    fixed = {
        "period": locator.period,
        "accession_number": locator.accession_number,
        "locator_sha256": locator_sha,
    }
    empty = {
        "projection_sha256": None,
        "header_sha256": None,
        "xml_sha256": None,
        "accepted_at_raw_sha256": None,
        "ordered_owner_ciks_sha256": None,
        "owner_count": 0,
    }
    if raw is None:
        return AllParentProjectionRow(**fixed, status="MISSING_RAW",
                                      raw_parent_sha256=None, **empty)
    if type(raw) is not bytes:
        return AllParentProjectionRow(**fixed, status="MALFORMED_RAW",
                                      raw_parent_sha256=None, **empty)
    if not 0 < len(raw) <= MAX_PARENT_BYTES:
        return AllParentProjectionRow(**fixed, status="UNBOUNDED_RAW",
                                      raw_parent_sha256=None, **empty)
    raw_sha = hash_bytes(raw)
    target = SecCompleteSubmissionTarget(
        period=locator.period,
        accession_number=locator.accession_number,
        form_type=locator.form_type,
        filing_date=locator.filing_date,
        issuer_cik=locator.issuer_cik.zfill(10),
        quarterly_index_sha256=index_sha,
        complete_submission_url=(
            "https://www.sec.gov/Archives/" + locator.archive_path
        ),
    )
    try:
        projection = project_sec_complete_submission(target, raw)
        payload = projection.to_payload()
    except SecCompleteSubmissionError:
        return AllParentProjectionRow(**fixed, status="PROJECTION_REFUSED",
                                      raw_parent_sha256=raw_sha, **empty)
    result = AllParentProjectionRow(
        **fixed,
        status="PROJECTED",
        raw_parent_sha256=raw_sha,
        projection_sha256=hash_payload(payload),
        header_sha256=payload["children"]["header"]["sha256"],
        xml_sha256=payload["children"]["primary_xml"]["sha256"],
        accepted_at_raw_sha256=hash_bytes(
            projection.accepted_at_raw.encode("ascii")
        ),
        ordered_owner_ciks_sha256=hash_payload(list(projection.header_owner_ciks)),
        owner_count=len(projection.header_owner_ciks),
    )
    result.to_payload()
    return result


def build_all_parent_projection_receipt(
    manifest: AllForm4ParentLocatorManifest,
    raw_parents: Iterable[RawParentProjectionInput],
    *,
    on_row: Callable[[AllParentProjectionRow], object] | None = None,
) -> AllParentProjectionReceipt:
    """Account one aligned input per locator; retain no IB-1C source fields.

    This returns no receipt until stream exhaustion and does not preserve the
    acceptance string or ordered owner CIKs needed for downstream IB-1C work.
    A downstream processor must replay exact parent bytes under its own gate.
    """
    if type(manifest) is not AllForm4ParentLocatorManifest:
        _refuse("locator manifest type is not exact")
    try:
        manifest.verify_digest()
    except AllForm4ParentLocatorError as exc:
        raise AllParentProjectionError("REFUSED: locator manifest changed") from exc
    if on_row is not None and not callable(on_row):
        _refuse("row observer is not callable")
    try:
        stream = iter(raw_parents)
    except TypeError as exc:
        raise AllParentProjectionError("REFUSED: raw-parent stream is absent") from exc
    row_digest = hashlib.sha256((ALL_PARENT_PROJECTION_KIND + "/rows-v1\n").encode())
    refusal_digest = hashlib.sha256((ALL_PARENT_PROJECTION_KIND + "/refusals-v1\n").encode())
    counts = {status: 0 for status in _STATUSES}
    examples: list[tuple[str, str]] = []
    accounted = 0
    for quarter in manifest.quarters:
        for locator in quarter.locators:
            try:
                item = next(stream)
            except StopIteration:
                _refuse("raw-parent stream is missing a manifest locator")
            except Exception as exc:
                raise AllParentProjectionError("REFUSED: raw-parent stream failed") from exc
            if (type(item) is not RawParentProjectionInput
                    or type(item.accession_number) is not str
                    or item.accession_number != locator.accession_number):
                _refuse("raw-parent stream is out of manifest order")
            row = _row(locator, item.raw_bytes, quarter.master_source_sha256)
            raw_line = _row_line(row)
            row_digest.update(raw_line)
            counts[row.status] += 1
            if row.status != "PROJECTED":
                refusal_digest.update(raw_line)
                if len(examples) < MAX_REFUSAL_EXAMPLES:
                    examples.append((row.accession_number, row.status))
            accounted += 1
            if on_row is not None:
                try:
                    on_row(row)
                except Exception as exc:
                    raise AllParentProjectionError("REFUSED: row observer failed") from exc
            del item
    try:
        next(stream)
    except StopIteration:
        pass
    except Exception as exc:
        raise AllParentProjectionError("REFUSED: raw-parent stream failed") from exc
    else:
        _refuse("raw-parent stream has an extra item")
    try:
        manifest.verify_digest()
    except AllForm4ParentLocatorError as exc:
        raise AllParentProjectionError("REFUSED: locator manifest changed during stream") from exc
    if accounted != manifest.total_accessions:
        _refuse("raw-parent accounting is incomplete")
    refusal_counts = tuple(
        (status, counts[status]) for status in _REFUSALS if counts[status]
    )
    provisional = AllParentProjectionReceipt(
        locator_manifest_sha256=manifest.content_sha256,
        expected_count=manifest.total_accessions,
        accounted_count=accounted,
        projected_count=counts["PROJECTED"],
        refused_count=accounted - counts["PROJECTED"],
        row_inventory_sha256=row_digest.hexdigest(),
        refusal_inventory_sha256=refusal_digest.hexdigest(),
        refusal_counts=refusal_counts,
        refusal_examples=tuple(examples),
        content_sha256="",
        _factory_token=_FACTORY_TOKEN,
    )
    result = replace(provisional, content_sha256=hash_payload(provisional._payload()))
    result.verify_digest()
    return result


__all__ = [
    "ALL_PARENT_PROJECTION_KIND",
    "ALL_PARENT_PROJECTION_VERSION",
    "MAX_PARENT_BYTES",
    "MAX_REFUSAL_EXAMPLES",
    "AllParentProjectionError",
    "RawParentProjectionInput",
    "AllParentProjectionRow",
    "AllParentProjectionReceipt",
    "build_all_parent_projection_receipt",
]
