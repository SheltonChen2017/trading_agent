"""Immutable invented provider receipt lineage, never verified PIT capture.

Receipt order is caller-supplied validation order, with sequence breaking ties.
Versions/kinds are explicit synthetic context, not inferred from last_updated.
The existing EventBook remains the sole correction/predecessor economic model.
Every raw receipt survives, including exact redelivery and conflicting content.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re

from data.hashing import canonical_json, hash_bytes
from research.guidance_revision_drift.archive import FixtureArchive
from research.guidance_revision_drift.events import EventBook, EventError, decode_fixture_object
from research.guidance_revision_drift.vendor_payloads import (
    SyntheticGuidanceContext, VendorObservation, VendorPayloadError,
)

MAX_RECEIPTS = 128
MAX_LINEAGE_BYTES = 12_582_912
_SCHEMA = "gdr.synthetic.provider-lineage.v1"
_GENESIS = hash_bytes(b"gdr.synthetic.provider-lineage.v1:empty")
_HASH = re.compile(r"[0-9a-f]{64}\Z")


class LineageError(ValueError):
    """Invalid or conflicting research-only receipt history."""


def _digest(value: object) -> str:
    if type(value) is not str or not _HASH.fullmatch(value):
        raise LineageError("lowercase_sha256_required")
    return value


def _checked(observation: object) -> VendorObservation:
    if type(observation) is not VendorObservation:
        raise LineageError("exact_vendor_observation_required")
    try:
        return VendorObservation(observation.raw_bytes, observation.context)
    except VendorPayloadError as exc:
        raise LineageError("invalid_vendor_observation") from exc


@dataclass(frozen=True, slots=True)
class LineageReplay:
    archive: FixtureArchive
    receipt_statuses: tuple[str, ...]
    observation_sha256s: tuple[str, ...]
    lineage_head_sha256: str

    def __post_init__(self) -> None:
        if type(self.archive) is not FixtureArchive:
            raise LineageError("exact_fixture_archive_required")
        object.__setattr__(self, "archive", FixtureArchive(self.archive.entries))
        if (type(self.receipt_statuses) is not tuple or type(self.observation_sha256s) is not tuple
                or len(self.receipt_statuses) != len(self.observation_sha256s)
                or len(self.receipt_statuses) > MAX_RECEIPTS):
            raise LineageError("bounded_replay_receipt_inventory_required")
        expected = iter(self.archive.book.decisions)
        for status, digest in zip(self.receipt_statuses, self.observation_sha256s):
            _digest(digest)
            if type(status) is not str:
                raise LineageError("replay_status_must_be_text")
            if status != "duplicate_delivery" and status != getattr(next(expected, None), "disposition", None):
                raise LineageError("replay_status_inventory_mismatch")
        if next(expected, None) is not None:
            raise LineageError("replay_status_inventory_incomplete")
        _digest(self.lineage_head_sha256)

    @property
    def book(self) -> EventBook:
        return self.archive.book


@dataclass(frozen=True, slots=True)
class ProviderLineage:
    """Pure bounded receipt journal; no file, provider, database or clock reads."""

    receipts: tuple[tuple[VendorObservation, bool], ...] = ()

    def __post_init__(self) -> None:
        if type(self.receipts) is not tuple or len(self.receipts) > MAX_RECEIPTS:
            raise LineageError("bounded_receipt_tuple_required")
        copied = []
        last = datetime(2024, 1, 1, tzinfo=timezone.utc)
        started = False
        for receipt in self.receipts:
            if type(receipt) is not tuple or len(receipt) != 2 or type(receipt[1]) is not bool:
                raise LineageError("observation_and_strict_bootstrap_required")
            observation, bootstrap = _checked(receipt[0]), receipt[1]
            if observation.validated_at < last:
                raise LineageError("validation_receipt_order_required")
            last = observation.validated_at
            if bootstrap and started:
                raise LineageError("bootstrap_only_initial_contiguous_receipts")
            started |= not bootstrap
            copied.append((observation, bootstrap))
        object.__setattr__(self, "receipts", tuple(copied))

    def append(self, observation: VendorObservation, *, bootstrap: bool = False) -> ProviderLineage:
        checked = ProviderLineage(self.receipts)
        return ProviderLineage(checked.receipts + ((_checked(observation), bootstrap),))

    def to_dict(self) -> dict:
        checked = ProviderLineage(self.receipts)
        previous, rows = _GENESIS, []
        for sequence, (observation, bootstrap) in enumerate(checked.receipts, 1):
            content = {"sequence": sequence, "previous_sha256": previous,
                       "raw_hex": observation.raw_bytes.hex(), "raw_sha256": observation.raw_sha256,
                       "context": observation.context.to_dict(), "observation_sha256": observation.sha256,
                       "bootstrap": bootstrap}
            previous = hash_bytes(canonical_json(content).encode())
            rows.append({**content, "receipt_sha256": previous})
        return {"schema": _SCHEMA, "point_in_time_data": False, "receipts": rows,
                "head_sha256": previous}

    @property
    def head_sha256(self) -> str:
        return self.to_dict()["head_sha256"]

    def to_bytes(self) -> bytes:
        raw = canonical_json(self.to_dict()).encode()
        if len(raw) > MAX_LINEAGE_BYTES:
            raise LineageError("lineage_byte_limit")
        return raw

    @classmethod
    def from_bytes(cls, raw: bytes, *, expected_head: str) -> ProviderLineage:
        _digest(expected_head)
        try:
            values = decode_fixture_object(raw, MAX_LINEAGE_BYTES)
            if (set(values) != {"schema", "point_in_time_data", "receipts", "head_sha256"}
                    or values["schema"] != _SCHEMA or values["point_in_time_data"] is not False
                    or type(values["receipts"]) is not list or len(values["receipts"]) > MAX_RECEIPTS):
                raise LineageError("lineage_envelope_invalid")
            observations = []
            for item in values["receipts"]:
                if type(item) is not dict or set(item) != {
                    "sequence", "previous_sha256", "raw_hex", "raw_sha256", "context",
                    "observation_sha256", "bootstrap", "receipt_sha256",
                }:
                    raise LineageError("lineage_receipt_fields_invalid")
                if (type(item["sequence"]) is not int or type(item["bootstrap"]) is not bool
                        or type(item["raw_hex"]) is not str):
                    raise LineageError("lineage_receipt_types_invalid")
                observation = VendorObservation(bytes.fromhex(item["raw_hex"]),
                    SyntheticGuidanceContext.from_dict(item["context"]))
                observations.append((observation, item["bootstrap"]))
            result = cls(tuple(observations))
            if result.to_dict() != values or result.head_sha256 != expected_head:
                raise LineageError("lineage_content_or_checkpoint_mismatch")
            return result
        except (EventError, VendorPayloadError, TypeError, ValueError) as exc:
            if isinstance(exc, LineageError):
                raise
            raise LineageError("lineage_malformed") from exc

    def as_of(self, cutoff: datetime) -> LineageReplay:
        """Replay only receipts validated by cutoff, preserving first capture.

        Permanent-ID remaps are retained in the journal but block replay. They
        cannot be inferred from a ticker or silently repaired by an adapter.
        Exact same-ID/version content redelivered later uses its first receipt;
        other same-version content is passed to EventBook for quarantine.
        """
        if (type(cutoff) is not datetime or cutoff.tzinfo is not timezone.utc
                or cutoff.year not in (2024, 2025)):
            raise LineageError("bounded_utc_cutoff_required")
        checked = ProviderLineage(self.receipts)
        selected = tuple(receipt for receipt in checked.receipts if receipt[0].validated_at <= cutoff)
        archive, statuses, hashes = FixtureArchive(), [], []
        identities, delivered = {}, {}
        for observation, bootstrap in selected:
            context = observation.context.to_dict()
            identity = context["provider_id"]
            mapping = (context["issuer_id"], context["security_id"])
            if identity in identities and identities[identity] != mapping:
                raise LineageError("provider_permanent_identity_remap")
            identities[identity] = mapping
            content = observation.delivery_content_sha256
            if content in delivered:
                if delivered[content] != bootstrap:
                    raise LineageError("duplicate_bootstrap_changed")
                statuses.append("duplicate_delivery")
            else:
                delivered[content] = bootstrap
                archive = archive.append(observation.disclosure, bootstrap=bootstrap)
                statuses.append(archive.book.decisions[-1].disposition)
            hashes.append(observation.sha256)
        return LineageReplay(archive, tuple(statuses), tuple(hashes), ProviderLineage(selected).head_sha256)

    def archive_as_of(self, cutoff: datetime) -> FixtureArchive:
        return self.as_of(cutoff).archive
