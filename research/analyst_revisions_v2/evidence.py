"""Immutable raw-source locators shared by snapshot and normalization types."""
from __future__ import annotations

import dataclasses
from typing import Any, Mapping

from .canonical import (
    canonical_json_bytes,
    require_exact_keys,
    require_identifier,
    require_int,
    require_relative_page_path,
    require_sha256,
    sha256_bytes,
)


SOURCE_LOCATOR_KEYS = frozenset(
    {
        "snapshot_id",
        "snapshot_manifest_sha256",
        "partition_year",
        "page_number",
        "page_filename",
        "page_sha256",
        "row_offset",
        "raw_row_sha256",
    }
)


@dataclasses.dataclass(frozen=True, order=True)
class SourceRowLocator:
    """Content-addressed position of one source row inside one snapshot."""

    snapshot_id: str
    snapshot_manifest_sha256: str
    partition_year: int
    page_number: int
    page_filename: str
    page_sha256: str
    row_offset: int
    raw_row_sha256: str

    def __post_init__(self) -> None:
        require_identifier(self.snapshot_id, "snapshot_id")
        require_sha256(self.snapshot_manifest_sha256, "snapshot_manifest_sha256")
        require_int(self.partition_year, "partition_year", minimum=1900, maximum=2200)
        require_int(self.page_number, "page_number", minimum=1)
        require_relative_page_path(self.page_filename, "page_filename")
        require_sha256(self.page_sha256, "page_sha256")
        require_int(self.row_offset, "row_offset", minimum=0)
        require_sha256(self.raw_row_sha256, "raw_row_sha256")

    def to_record(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "snapshot_manifest_sha256": self.snapshot_manifest_sha256,
            "partition_year": self.partition_year,
            "page_number": self.page_number,
            "page_filename": self.page_filename,
            "page_sha256": self.page_sha256,
            "row_offset": self.row_offset,
            "raw_row_sha256": self.raw_row_sha256,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "SourceRowLocator":
        require_exact_keys(record, SOURCE_LOCATOR_KEYS, "source_locator")
        return cls(**dict(record))

    @property
    def locator_sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self.to_record()))

    @property
    def sort_key(self) -> tuple[int, int, int, str]:
        return (
            self.partition_year,
            self.page_number,
            self.row_offset,
            self.raw_row_sha256,
        )


def derive_event_id(locator: SourceRowLocator, event_version_id: str) -> str:
    require_identifier(event_version_id, "event_version_id")
    digest = sha256_bytes(
        canonical_json_bytes(
            {
                "event_version_id": event_version_id,
                "source_locator": locator.to_record(),
                "type": "arv2-canonical-event-id-v1",
            }
        )
    )
    return f"arv2_evt_{digest}"


def derive_refusal_id(locator: SourceRowLocator, reason: str) -> str:
    require_identifier(reason, "refusal_reason")
    digest = sha256_bytes(
        canonical_json_bytes(
            {
                "reason": reason,
                "source_locator": locator.to_record(),
                "type": "arv2-normalization-refusal-id-v1",
            }
        )
    )
    return f"arv2_ref_{digest}"
