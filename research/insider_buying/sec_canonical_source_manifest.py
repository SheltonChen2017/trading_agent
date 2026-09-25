"""Pure, synthetic-first candidate for the 82-quarter IB-2 source boundary.

This module consumes caller-provided identities and byte iterables. It has no
filesystem, SEC, network, provider, outcome, QC, broker, or trading surface.
It neither authenticates the caller's provenance nor verifies that arbitrary
bytes really are acceptance metadata or a complete primary ownership XML.
Those are separate evidence gates. A successful candidate is not a canonical
IB-2 result or permission to read real artifacts.

The two IB-1 identities must come from their independently verified loaders
when real artifacts are eventually authorized. Rechecking their content
identities here binds the candidate but cannot substitute for those loaders.
Only 82 quarter summaries, rather than accession or artifact bytes, are kept.
"""
from __future__ import annotations

import hashlib
import heapq
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying.sec_bulk_parsed_snapshot import (
    MAX_ACCESSIONS_ARTIFACT_BYTES,
    MAX_TOTAL_ROWS,
    PARSED_SNAPSHOT_CONTRACT_VERSION,
    SEC_TSV_PARSER_VERSION,
    ParsedSecBulkAccession,
    ParsedSecBulkArtifactIdentity,
    SecBulkParsedSnapshotIdentity,
    SecTsvSchemaProfile,
)
from research.insider_buying.sec_bulk_snapshot import (
    MAX_ARCHIVE_BYTES,
    RAW_SNAPSHOT_CONTRACT_VERSION,
    SecBulkSnapshotIdentity,
)
from research.insider_buying.sec_owner_supplied_source_policy import (
    CanonicalIb2SourcePolicy,
)


CANONICAL_IB2_SOURCE_MANIFEST_KIND = "insider-buying-ib2-source-manifest-candidate"
CANONICAL_IB2_SOURCE_MANIFEST_VERSION = 1
# Independent literal from the reviewed policy freeze, not a mutable alias to
# the policy module's computed public constant.
_FROZEN_POLICY_SHA256 = (
    "eec42a1e34b6200e0e195a6702307a5c716c10c40dbfd8e9e8095846c79e7dbe"
)
MAX_ARTIFACT_CHUNK_BYTES = 1024 * 1024
MAX_SOURCE_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_SOURCE_URL_CHARACTERS = 8 * 1024
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_ACCESSION_RE = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_COMPACT_ACCESSION_RE = re.compile(r"[0-9]{18}\Z")
# Exact literal scheme and host plus the bounded path charset used by the
# earlier IB-1C boundary. The charset excludes "?", "#", "%", and whitespace,
# so a matching URL has no query, fragment, userinfo, port, or escape and
# needs no library parser. The lane package must not import `urllib`.
_SOURCE_URL_RE = re.compile(
    r"https://(?P<host>www\.sec\.gov|data\.sec\.gov)"
    r"(?P<path>/[A-Za-z0-9._~!$&'()*+,;=:@/-]+)\Z"
)
_SEC_PRIMARY_URL_RE = re.compile(
    r"https://www\.sec\.gov/Archives/edgar/data/[0-9]{1,10}/"
    r"(?P<accession>[0-9]{18})/[A-Za-z0-9._-]{1,255}\Z"
)
_EXPECTED_PERIODS = tuple(
    f"{year}Q{quarter}"
    for year in range(2006, 2027)
    for quarter in range(1, 5)
    if (year, quarter) <= (2026, 2)
)
_REQUIRED_FORMS = frozenset(("4", "4/A"))
_CONTEXT_FORMS = frozenset(("3", "5"))
_SENTINEL = object()


class CanonicalIb2SourceManifestError(ValueError):
    """The proposed source inventory failed its exact synthetic boundary."""


@dataclass(frozen=True)
class CanonicalIb2ArtifactStream:
    """Caller-declared provenance/digest/size and single-pass raw bytes."""

    sha256: str
    size_bytes: int
    chunks: Iterable[bytes]
    source_url: str
    retrieved_at_utc: str


@dataclass(frozen=True)
class CanonicalIb2ArtifactReceipt:
    """A hash/size pair returned after consuming every supplied byte chunk."""

    sha256: str
    size_bytes: int

    def to_payload(self) -> dict[str, object]:
        return {"sha256": self.sha256, "size_bytes": self.size_bytes}


@dataclass(frozen=True)
class CanonicalIb2AccessionSource:
    """One caller-declared metadata/XML pair for one Form 4 or 4/A accession."""

    accession_number: str
    acceptance_metadata: CanonicalIb2ArtifactStream
    primary_ownership_xml: CanonicalIb2ArtifactStream


@dataclass(frozen=True)
class CanonicalIb2QuarterInput:
    """One quarter of upstream identities and ordered, single-pass streams."""

    raw: SecBulkSnapshotIdentity
    parsed: SecBulkParsedSnapshotIdentity
    accessions: Iterable[ParsedSecBulkAccession]
    sources: Iterable[CanonicalIb2AccessionSource]


@dataclass(frozen=True)
class CanonicalIb2QuarterSummary:
    period: str
    raw_snapshot_id: str
    raw_lineage_hash: str
    raw_archive_sha256: str
    raw_archive_size_bytes: int
    raw_manifest_sha256: str
    parsed_snapshot_id: str
    parsed_lineage_hash: str
    accessions_artifact_sha256: str
    accessions_artifact_size_bytes: int
    accessions_record_count: int
    form4_accession_count: int
    context_accession_count: int
    accession_sources_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.period) is not str
            or type(self.raw_snapshot_id) is not str
            or type(self.parsed_snapshot_id) is not str
            or any(
                type(value) is not str or _SHA256_RE.fullmatch(value) is None
                for value in (
                    self.raw_lineage_hash,
                    self.raw_archive_sha256,
                    self.raw_manifest_sha256,
                    self.parsed_lineage_hash,
                    self.accessions_artifact_sha256,
                    self.accession_sources_sha256,
                )
            )
            or type(self.raw_archive_size_bytes) is not int
            or not 0 < self.raw_archive_size_bytes <= MAX_ARCHIVE_BYTES
            or type(self.accessions_artifact_size_bytes) is not int
            or not 0
            <= self.accessions_artifact_size_bytes
            <= MAX_ACCESSIONS_ARTIFACT_BYTES
            or any(
                type(value) is not int or not 0 <= value <= MAX_TOTAL_ROWS
                for value in (
                    self.accessions_record_count,
                    self.form4_accession_count,
                    self.context_accession_count,
                )
            )
            or self.accessions_record_count
            != self.form4_accession_count + self.context_accession_count
        ):
            raise CanonicalIb2SourceManifestError(
                "REFUSED: quarter summary has invalid immutable scalars or counts"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "period": self.period,
            "raw_snapshot_id": self.raw_snapshot_id,
            "raw_lineage_hash": self.raw_lineage_hash,
            "raw_archive_sha256": self.raw_archive_sha256,
            "raw_archive_size_bytes": self.raw_archive_size_bytes,
            "raw_manifest_sha256": self.raw_manifest_sha256,
            "parsed_snapshot_id": self.parsed_snapshot_id,
            "parsed_lineage_hash": self.parsed_lineage_hash,
            "accessions_artifact_sha256": self.accessions_artifact_sha256,
            "accessions_artifact_size_bytes": self.accessions_artifact_size_bytes,
            "accessions_record_count": self.accessions_record_count,
            "form4_accession_count": self.form4_accession_count,
            "context_accession_count": self.context_accession_count,
            "accession_sources_sha256": self.accession_sources_sha256,
        }


@dataclass(frozen=True)
class CanonicalIb2SourceManifest:
    """Content-addressed candidate, not an authenticated production manifest."""

    policy_sha256: str
    quarters: tuple[CanonicalIb2QuarterSummary, ...]
    manifest_sha256: str

    def __post_init__(self) -> None:
        if (
            self.policy_sha256 != _FROZEN_POLICY_SHA256
            or type(self.quarters) is not tuple
            or len(self.quarters) != len(_EXPECTED_PERIODS)
            or any(
                type(item) is not CanonicalIb2QuarterSummary
                or item.period != expected
                for item, expected in zip(self.quarters, _EXPECTED_PERIODS)
            )
        ):
            raise CanonicalIb2SourceManifestError(
                "REFUSED: source manifest policy or quarter inventory is invalid"
            )
        try:
            expected_hash = hash_payload(self.lineage_payload())
        except (AttributeError, TypeError, ValueError) as exc:
            raise CanonicalIb2SourceManifestError(
                "REFUSED: source manifest payload is invalid"
            ) from exc
        if self.manifest_sha256 != expected_hash:
            raise CanonicalIb2SourceManifestError(
                "REFUSED: source manifest content hash is invalid"
            )

    def lineage_payload(self) -> dict[str, object]:
        return {
            "kind": CANONICAL_IB2_SOURCE_MANIFEST_KIND,
            "version": CANONICAL_IB2_SOURCE_MANIFEST_VERSION,
            "policy_sha256": self.policy_sha256,
            "quarters": [quarter.to_payload() for quarter in self.quarters],
        }

    def to_payload(self) -> dict[str, object]:
        return {**self.lineage_payload(), "manifest_sha256": self.manifest_sha256}


def _require_sha256(value: object, *, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise CanonicalIb2SourceManifestError(f"REFUSED: {label} is not a SHA-256")
    return value


def _json_line(payload: object, *, label: str) -> bytes:
    try:
        return (canonical_json(payload) + "\n").encode("utf-8")
    except (TypeError, UnicodeError, ValueError) as exc:
        raise CanonicalIb2SourceManifestError(
            f"REFUSED: {label} is not canonical JSON"
        ) from exc


def verify_artifact_chunks(
    chunks: Iterable[bytes], *, sha256: str, size_bytes: int
) -> CanonicalIb2ArtifactReceipt:
    """Hash the complete stream with at most one bounded input chunk held.

    This checks raw bytes and a caller-declared receipt only. It does not
    inspect XML or metadata semantics, source provenance, or file identity.
    """

    expected_hash = _require_sha256(sha256, label="artifact digest")
    if (
        type(size_bytes) is not int
        or not 0 < size_bytes <= MAX_SOURCE_ARTIFACT_BYTES
    ):
        raise CanonicalIb2SourceManifestError(
            "REFUSED: artifact byte size must be a bounded positive exact integer"
        )
    try:
        iterator = iter(chunks)
    except TypeError as exc:
        raise CanonicalIb2SourceManifestError(
            "REFUSED: artifact chunks must be iterable"
        ) from exc
    digest = hashlib.sha256()
    observed_size = 0
    for chunk in iterator:
        if (
            type(chunk) is not bytes
            or not 0 < len(chunk) <= MAX_ARTIFACT_CHUNK_BYTES
        ):
            raise CanonicalIb2SourceManifestError(
                "REFUSED: artifact chunks must be bounded exact bytes"
            )
        observed_size += len(chunk)
        if observed_size > size_bytes:
            raise CanonicalIb2SourceManifestError(
                "REFUSED: artifact stream exceeds its declared byte size"
            )
        digest.update(chunk)
    if observed_size != size_bytes or digest.hexdigest() != expected_hash:
        raise CanonicalIb2SourceManifestError(
            "REFUSED: artifact stream digest or byte size disagrees with receipt"
        )
    return CanonicalIb2ArtifactReceipt(
        sha256=expected_hash, size_bytes=observed_size
    )


def _validate_declared_provenance(
    *,
    source_url: str,
    retrieved_at_utc: str,
    accession_number: str,
    primary_xml: bool,
) -> None:
    url = source_url
    if (
        type(url) is not str
        or url != url.strip()
        or len(url) > MAX_SOURCE_URL_CHARACTERS
    ):
        raise CanonicalIb2SourceManifestError(
            "REFUSED: source URL is not canonical"
        )
    match = _SOURCE_URL_RE.fullmatch(url)
    if match is None or any(
        segment in {"", ".", ".."} for segment in match.group("path")[1:].split("/")
    ):
        raise CanonicalIb2SourceManifestError(
            "REFUSED: source URL must be canonical HTTPS sec.gov"
        )
    components = match.group("path").split("/")[1:]
    accession_digits = accession_number.replace("-", "")
    expected_segments = {accession_number, accession_digits}
    accession_segments = tuple(
        component
        for component in components
        if _ACCESSION_RE.fullmatch(component) is not None
        or _COMPACT_ACCESSION_RE.fullmatch(component) is not None
    )
    if (
        not any(component in expected_segments for component in accession_segments)
        or any(component not in expected_segments for component in accession_segments)
    ):
        raise CanonicalIb2SourceManifestError(
            "REFUSED: source URL must bind only its exact accession segment"
        )
    if primary_xml:
        primary_match = _SEC_PRIMARY_URL_RE.fullmatch(url)
        if (
            primary_match is None
            or primary_match.group("accession") != accession_digits
        ):
            raise CanonicalIb2SourceManifestError(
                "REFUSED: primary XML URL does not bind its SEC Archives accession"
            )
    retrieved = retrieved_at_utc
    if type(retrieved) is not str or len(retrieved) != 25:
        raise CanonicalIb2SourceManifestError(
            "REFUSED: retrieval instant is not canonical UTC"
        )
    try:
        instant = datetime.fromisoformat(retrieved)
    except ValueError as exc:
        raise CanonicalIb2SourceManifestError(
            "REFUSED: retrieval instant is not canonical UTC"
        ) from exc
    if (
        instant.utcoffset() != timedelta(0)
        or instant.isoformat(timespec="seconds") != retrieved
        or not retrieved.endswith("+00:00")
    ):
        raise CanonicalIb2SourceManifestError(
            "REFUSED: retrieval instant is not canonical UTC"
        )


def _verify_identity_pair(
    raw: SecBulkSnapshotIdentity,
    parsed: SecBulkParsedSnapshotIdentity,
    *,
    expected_period: str,
) -> tuple[str, object]:
    if (
        type(raw) is not SecBulkSnapshotIdentity
        or type(parsed) is not SecBulkParsedSnapshotIdentity
        or RAW_SNAPSHOT_CONTRACT_VERSION != 2
        or PARSED_SNAPSHOT_CONTRACT_VERSION != 1
        or SEC_TSV_PARSER_VERSION != "INSETF-IB1B-TSV-v1"
    ):
        raise CanonicalIb2SourceManifestError(
            "REFUSED: exact IB-1A v2 and IB-1B identities are required"
        )
    if (
        type(raw.year) is not int
        or type(raw.quarter) is not int
        or type(parsed.year) is not int
        or type(parsed.quarter) is not int
        or f"{raw.year}Q{raw.quarter}" != expected_period
        or parsed.year != raw.year
        or parsed.quarter != raw.quarter
    ):
        raise CanonicalIb2SourceManifestError(
            "REFUSED: raw and parsed quarter order or identity disagrees with policy"
        )
    _require_sha256(raw.archive_sha256, label="raw archive digest")
    if (
        type(raw.archive_size_bytes) is not int
        or not 0 < raw.archive_size_bytes <= MAX_ARCHIVE_BYTES
    ):
        raise CanonicalIb2SourceManifestError(
            "REFUSED: raw archive byte size is invalid"
        )
    try:
        raw_lineage_hash = hash_payload(raw.lineage_payload())
        raw_manifest_sha256 = hash_bytes(
            _json_line(raw.to_payload(), label="raw manifest")
        )
        parsed_lineage_hash = hash_payload(parsed.lineage_payload())
        profile_hash = hash_payload(parsed.schema_profile.to_payload())
    except CanonicalIb2SourceManifestError:
        raise
    except (AttributeError, TypeError, ValueError) as exc:
        raise CanonicalIb2SourceManifestError(
            "REFUSED: raw or parsed identity payload is invalid"
        ) from exc
    if (
        raw.lineage_hash != raw_lineage_hash
        or raw.snapshot_id
        != f"sec-insider-bulk-{raw.year:04d}q{raw.quarter}-{raw_lineage_hash[:16]}"
    ):
        raise CanonicalIb2SourceManifestError(
            "REFUSED: raw snapshot lineage or ID is invalid"
        )
    if (
        parsed.lineage_hash != parsed_lineage_hash
        or parsed.snapshot_id
        != (
            f"sec-insider-parsed-{parsed.year:04d}q{parsed.quarter}-"
            f"{parsed_lineage_hash[:16]}"
        )
    ):
        raise CanonicalIb2SourceManifestError(
            "REFUSED: parsed snapshot lineage or ID is invalid"
        )
    if (
        parsed.raw_snapshot_id != raw.snapshot_id
        or parsed.raw_lineage_hash != raw.lineage_hash
        or parsed.raw_archive_sha256 != raw.archive_sha256
        or parsed.raw_manifest_sha256 != raw_manifest_sha256
    ):
        raise CanonicalIb2SourceManifestError(
            "REFUSED: parsed snapshot has a different raw parent"
        )
    if (
        type(parsed.schema_profile) is not SecTsvSchemaProfile
        or parsed.schema_profile_hash != profile_hash
    ):
        raise CanonicalIb2SourceManifestError(
            "REFUSED: parsed schema profile hash is invalid"
        )
    if type(parsed.artifacts) is not tuple or any(
        type(item) is not ParsedSecBulkArtifactIdentity
        for item in parsed.artifacts
    ):
        raise CanonicalIb2SourceManifestError(
            "REFUSED: parsed artifact inventory is invalid"
        )
    matching = tuple(
        item for item in parsed.artifacts if item.name == "accessions.jsonl"
    )
    if len(matching) != 1:
        raise CanonicalIb2SourceManifestError(
            "REFUSED: parsed accessions artifact identity must be unique"
        )
    artifact = matching[0]
    _require_sha256(artifact.sha256, label="accessions artifact digest")
    if (
        type(artifact.size_bytes) is not int
        or not 0 <= artifact.size_bytes <= MAX_ACCESSIONS_ARTIFACT_BYTES
        or type(artifact.record_count) is not int
        or not 0 <= artifact.record_count <= MAX_TOTAL_ROWS
    ):
        raise CanonicalIb2SourceManifestError(
            "REFUSED: parsed accessions artifact counts are invalid"
        )
    return raw_manifest_sha256, artifact


@dataclass(frozen=True)
class _ArtifactDeclaration:
    """Scalars captured before either caller-owned byte generator can run."""

    stream: CanonicalIb2ArtifactStream
    sha256: str
    size_bytes: int
    chunks: Iterable[bytes]
    source_url: str
    retrieved_at_utc: str

    def to_payload(self) -> dict[str, object]:
        return {
            "source_url": self.source_url,
            "retrieved_at_utc": self.retrieved_at_utc,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }

    def require_unchanged(self) -> None:
        if (
            self.stream.sha256 != self.sha256
            or self.stream.size_bytes != self.size_bytes
            or self.stream.chunks is not self.chunks
            or self.stream.source_url != self.source_url
            or self.stream.retrieved_at_utc != self.retrieved_at_utc
        ):
            raise CanonicalIb2SourceManifestError(
                "REFUSED: source artifact declaration changed while streaming"
            )


def _snapshot_source_artifact(
    stream: CanonicalIb2ArtifactStream,
    *,
    label: str,
    accession_number: str,
    primary_xml: bool,
) -> _ArtifactDeclaration:
    if (
        type(stream) is not CanonicalIb2ArtifactStream
        or type(stream.size_bytes) is not int
        or not 0 < stream.size_bytes <= MAX_SOURCE_ARTIFACT_BYTES
    ):
        raise CanonicalIb2SourceManifestError(
            f"REFUSED: {label} requires a nonempty caller-declared byte stream"
        )
    sha256 = _require_sha256(stream.sha256, label=f"{label} digest")
    size_bytes = stream.size_bytes
    chunks = stream.chunks
    source_url = stream.source_url
    retrieved_at_utc = stream.retrieved_at_utc
    _validate_declared_provenance(
        source_url=source_url,
        retrieved_at_utc=retrieved_at_utc,
        accession_number=accession_number,
        primary_xml=primary_xml,
    )
    return _ArtifactDeclaration(
        stream=stream,
        sha256=sha256,
        size_bytes=size_bytes,
        chunks=chunks,
        source_url=source_url,
        retrieved_at_utc=retrieved_at_utc,
    )


@dataclass(frozen=True)
class _QuarterIdentitySnapshot:
    """Validated scalars captured before any caller-owned stream is consumed."""

    raw_snapshot_id: str
    raw_lineage_hash: str
    raw_archive_sha256: str
    raw_archive_size_bytes: int
    raw_manifest_sha256: str
    parsed_snapshot_id: str
    parsed_lineage_hash: str
    parsed_payload_sha256: str
    accessions_artifact_sha256: str
    accessions_artifact_size_bytes: int
    accessions_record_count: int


@dataclass
class _QuarterCursor:
    """One quarter's incremental state, with no retained accession row."""

    period: str
    raw: SecBulkSnapshotIdentity
    parsed: SecBulkParsedSnapshotIdentity
    snapshot: _QuarterIdentitySnapshot
    accessions_iter: Iterator[ParsedSecBulkAccession]
    sources_iter: Iterator[CanonicalIb2AccessionSource]
    accessions_digest: Any = field(default_factory=hashlib.sha256)
    source_digest: Any = field(default_factory=hashlib.sha256)
    accessions_size: int = 0
    accessions_count: int = 0
    form4_count: int = 0
    context_count: int = 0
    previous_accession: str = ""


def _quarter_cursor(
    quarter: CanonicalIb2QuarterInput, *, expected_period: str
) -> _QuarterCursor:
    if type(quarter) is not CanonicalIb2QuarterInput:
        raise CanonicalIb2SourceManifestError(
            "REFUSED: quarter input is not the exact frozen contract"
        )
    raw = quarter.raw
    parsed = quarter.parsed
    raw_manifest_sha256, artifact = _verify_identity_pair(
        raw, parsed, expected_period=expected_period
    )
    try:
        parsed_payload_sha256 = hash_payload(parsed.to_payload())
    except (AttributeError, TypeError, ValueError) as exc:
        raise CanonicalIb2SourceManifestError(
            "REFUSED: parsed identity payload is invalid"
        ) from exc
    snapshot = _QuarterIdentitySnapshot(
        raw_snapshot_id=raw.snapshot_id,
        raw_lineage_hash=raw.lineage_hash,
        raw_archive_sha256=raw.archive_sha256,
        raw_archive_size_bytes=raw.archive_size_bytes,
        raw_manifest_sha256=raw_manifest_sha256,
        parsed_snapshot_id=parsed.snapshot_id,
        parsed_lineage_hash=parsed.lineage_hash,
        parsed_payload_sha256=parsed_payload_sha256,
        accessions_artifact_sha256=artifact.sha256,
        accessions_artifact_size_bytes=artifact.size_bytes,
        accessions_record_count=artifact.record_count,
    )
    try:
        accessions_iter = iter(quarter.accessions)
        sources_iter = iter(quarter.sources)
    except TypeError as exc:
        raise CanonicalIb2SourceManifestError(
            "REFUSED: accession and source inventories must be iterable"
        ) from exc
    return _QuarterCursor(
        period=expected_period,
        raw=raw,
        parsed=parsed,
        snapshot=snapshot,
        accessions_iter=accessions_iter,
        sources_iter=sources_iter,
    )


def _advance_cursor(cursor: _QuarterCursor) -> str | None:
    """Consume one complete accession, returning only its sortable key."""

    accession = next(cursor.accessions_iter, _SENTINEL)
    if accession is _SENTINEL:
        return None
    if type(accession) is not ParsedSecBulkAccession:
        raise CanonicalIb2SourceManifestError(
            "REFUSED: parsed accession row has the wrong contract"
        )
    number = accession.accession_number
    if (
        type(number) is not str
        or _ACCESSION_RE.fullmatch(number) is None
        or number <= cursor.previous_accession
    ):
        raise CanonicalIb2SourceManifestError(
            "REFUSED: parsed accession inventory is malformed or unordered"
        )
    document_type = accession.document_type
    if type(document_type) is not str or document_type not in (
        _REQUIRED_FORMS | _CONTEXT_FORMS
    ):
        raise CanonicalIb2SourceManifestError(
            "REFUSED: parsed accession has an unapproved document type"
        )
    line = _canonical_accession_line(accession)
    line_sha256 = hash_bytes(line)
    line_size_bytes = len(line)
    cursor.accessions_digest.update(line)
    del line
    cursor.accessions_size += line_size_bytes
    cursor.accessions_count += 1
    if (
        cursor.accessions_size > cursor.snapshot.accessions_artifact_size_bytes
        or cursor.accessions_count > cursor.snapshot.accessions_record_count
    ):
        raise CanonicalIb2SourceManifestError(
            "REFUSED: parsed accession stream exceeds its declared artifact"
        )
    if document_type in _CONTEXT_FORMS:
        cursor.context_count += 1
        cursor.previous_accession = number
        return number
    source = next(cursor.sources_iter, _SENTINEL)
    if (
        type(source) is not CanonicalIb2AccessionSource
        or source.accession_number != number
    ):
        raise CanonicalIb2SourceManifestError(
            "REFUSED: Form 4/4-A metadata/XML coverage is not one-to-one"
        )
    metadata_stream = source.acceptance_metadata
    primary_stream = source.primary_ownership_xml
    metadata = _snapshot_source_artifact(
        metadata_stream,
        label="acceptance metadata",
        accession_number=number,
        primary_xml=False,
    )
    primary_xml = _snapshot_source_artifact(
        primary_stream,
        label="primary ownership XML",
        accession_number=number,
        primary_xml=True,
    )
    verify_artifact_chunks(
        metadata.chunks, sha256=metadata.sha256, size_bytes=metadata.size_bytes
    )
    verify_artifact_chunks(
        primary_xml.chunks,
        sha256=primary_xml.sha256,
        size_bytes=primary_xml.size_bytes,
    )
    if (
        source.accession_number != number
        or source.acceptance_metadata is not metadata_stream
        or source.primary_ownership_xml is not primary_stream
    ):
        raise CanonicalIb2SourceManifestError(
            "REFUSED: accession source declaration changed while streaming"
        )
    metadata.require_unchanged()
    primary_xml.require_unchanged()
    if (
        accession.accession_number != number
        or accession.document_type != document_type
    ):
        raise CanonicalIb2SourceManifestError(
            "REFUSED: parsed accession changed while streaming"
        )
    checked_line = _canonical_accession_line(accession)
    if (
        len(checked_line) != line_size_bytes
        or hash_bytes(checked_line) != line_sha256
    ):
        raise CanonicalIb2SourceManifestError(
            "REFUSED: parsed accession changed while streaming"
        )
    del checked_line
    cursor.source_digest.update(
        _json_line(
            {
                "accession_number": number,
                "acceptance_metadata": metadata.to_payload(),
                "primary_ownership_xml": primary_xml.to_payload(),
            },
            label="accession source receipt",
        )
    )
    cursor.form4_count += 1
    cursor.previous_accession = number
    return number


def _canonical_accession_line(accession: ParsedSecBulkAccession) -> bytes:
    try:
        accession_payload = accession.to_payload()
    except (AttributeError, TypeError, ValueError) as exc:
        raise CanonicalIb2SourceManifestError(
            "REFUSED: parsed accession payload is invalid"
        ) from exc
    return _json_line(accession_payload, label="parsed accession")


def _finish_cursor(cursor: _QuarterCursor) -> CanonicalIb2QuarterSummary:
    if next(cursor.sources_iter, _SENTINEL) is not _SENTINEL:
        raise CanonicalIb2SourceManifestError(
            "REFUSED: Form 4/4-A metadata/XML inventory has an extra source"
        )
    if (
        cursor.accessions_digest.hexdigest()
        != cursor.snapshot.accessions_artifact_sha256
        or cursor.accessions_size
        != cursor.snapshot.accessions_artifact_size_bytes
        or cursor.accessions_count != cursor.snapshot.accessions_record_count
    ):
        raise CanonicalIb2SourceManifestError(
            "REFUSED: complete parsed accessions artifact digest, size, or count differs"
        )
    snapshot = cursor.snapshot
    return CanonicalIb2QuarterSummary(
        period=cursor.period,
        raw_snapshot_id=snapshot.raw_snapshot_id,
        raw_lineage_hash=snapshot.raw_lineage_hash,
        raw_archive_sha256=snapshot.raw_archive_sha256,
        raw_archive_size_bytes=snapshot.raw_archive_size_bytes,
        raw_manifest_sha256=snapshot.raw_manifest_sha256,
        parsed_snapshot_id=snapshot.parsed_snapshot_id,
        parsed_lineage_hash=snapshot.parsed_lineage_hash,
        accessions_artifact_sha256=snapshot.accessions_artifact_sha256,
        accessions_artifact_size_bytes=snapshot.accessions_artifact_size_bytes,
        accessions_record_count=cursor.accessions_count,
        form4_accession_count=cursor.form4_count,
        context_accession_count=cursor.context_count,
        accession_sources_sha256=cursor.source_digest.hexdigest(),
    )


def _require_identity_unchanged(cursor: _QuarterCursor) -> None:
    """Recheck every caller-held identity after every stream has completed."""

    try:
        raw_manifest_sha256 = hash_bytes(
            _json_line(cursor.raw.to_payload(), label="raw manifest")
        )
        parsed_payload_sha256 = hash_payload(cursor.parsed.to_payload())
    except CanonicalIb2SourceManifestError:
        raise
    except (AttributeError, TypeError, ValueError) as exc:
        raise CanonicalIb2SourceManifestError(
            "REFUSED: raw or parsed identity changed while streaming"
        ) from exc
    if (
        raw_manifest_sha256 != cursor.snapshot.raw_manifest_sha256
        or parsed_payload_sha256 != cursor.snapshot.parsed_payload_sha256
    ):
        raise CanonicalIb2SourceManifestError(
            "REFUSED: raw or parsed identity changed while streaming"
        )


def build_canonical_ib2_source_manifest(
    quarters: Iterable[CanonicalIb2QuarterInput],
    *,
    policy: CanonicalIb2SourcePolicy,
) -> CanonicalIb2SourceManifest:
    """Consume exactly the frozen 82 quarters and return a pure candidate.

    One accession lookahead per quarter is heap-merged so a repeated accession
    in different quarters cannot hide behind bounded-memory validation. The
    result holds summaries only and makes no claim of SEC authentication,
    semantic XML completeness, canonical filtering, or outcome authority.
    """

    if type(policy) is not CanonicalIb2SourcePolicy:
        raise CanonicalIb2SourceManifestError(
            "REFUSED: canonical IB-2 owner source policy is not the frozen version"
        )
    try:
        policy_sha256 = policy.semantic_sha256
    except (AttributeError, TypeError, ValueError) as exc:
        raise CanonicalIb2SourceManifestError(
            "REFUSED: canonical IB-2 owner source policy is malformed"
        ) from exc
    if policy_sha256 != _FROZEN_POLICY_SHA256:
        raise CanonicalIb2SourceManifestError(
            "REFUSED: canonical IB-2 owner source policy is not the frozen version"
        )
    try:
        quarter_iter = iter(quarters)
    except TypeError as exc:
        raise CanonicalIb2SourceManifestError(
            "REFUSED: quarter inventory must be iterable"
        ) from exc
    cursors: list[_QuarterCursor] = []
    for expected_period in _EXPECTED_PERIODS:
        quarter = next(quarter_iter, _SENTINEL)
        if quarter is _SENTINEL:
            raise CanonicalIb2SourceManifestError(
                "REFUSED: canonical source inventory is missing a required quarter"
            )
        cursors.append(
            _quarter_cursor(quarter, expected_period=expected_period)
        )
    if next(quarter_iter, _SENTINEL) is not _SENTINEL:
        raise CanonicalIb2SourceManifestError(
            "REFUSED: canonical source inventory has an extra quarter"
        )
    pending: list[tuple[str, int]] = []
    for index, cursor in enumerate(cursors):
        number = _advance_cursor(cursor)
        if number is not None:
            heapq.heappush(pending, (number, index))
    last_global_accession: str | None = None
    while pending:
        number, index = heapq.heappop(pending)
        if number == last_global_accession:
            raise CanonicalIb2SourceManifestError(
                "REFUSED: duplicate accession number across canonical quarters"
            )
        if last_global_accession is not None and number < last_global_accession:
            raise CanonicalIb2SourceManifestError(
                "REFUSED: global accession inventory is unordered"
            )
        cursor = cursors[index]
        last_global_accession = number
        following = _advance_cursor(cursor)
        if following is not None:
            heapq.heappush(pending, (following, index))
    summary_tuple = tuple(_finish_cursor(cursor) for cursor in cursors)
    for cursor in cursors:
        _require_identity_unchanged(cursor)
    try:
        final_policy_sha256 = policy.semantic_sha256
    except (AttributeError, TypeError, ValueError) as exc:
        raise CanonicalIb2SourceManifestError(
            "REFUSED: canonical IB-2 owner source policy changed while streaming"
        ) from exc
    if final_policy_sha256 != _FROZEN_POLICY_SHA256:
        raise CanonicalIb2SourceManifestError(
            "REFUSED: canonical IB-2 owner source policy changed while streaming"
        )
    lineage_payload = {
        "kind": CANONICAL_IB2_SOURCE_MANIFEST_KIND,
        "version": CANONICAL_IB2_SOURCE_MANIFEST_VERSION,
        "policy_sha256": _FROZEN_POLICY_SHA256,
        "quarters": [quarter.to_payload() for quarter in summary_tuple],
    }
    return CanonicalIb2SourceManifest(
        policy_sha256=_FROZEN_POLICY_SHA256,
        quarters=summary_tuple,
        manifest_sha256=hash_payload(lineage_payload),
    )


__all__ = [
    "CANONICAL_IB2_SOURCE_MANIFEST_KIND",
    "CANONICAL_IB2_SOURCE_MANIFEST_VERSION",
    "MAX_ARTIFACT_CHUNK_BYTES",
    "MAX_SOURCE_ARTIFACT_BYTES",
    "MAX_SOURCE_URL_CHARACTERS",
    "CanonicalIb2AccessionSource",
    "CanonicalIb2ArtifactReceipt",
    "CanonicalIb2ArtifactStream",
    "CanonicalIb2QuarterInput",
    "CanonicalIb2QuarterSummary",
    "CanonicalIb2SourceManifest",
    "CanonicalIb2SourceManifestError",
    "build_canonical_ib2_source_manifest",
    "verify_artifact_chunks",
]
