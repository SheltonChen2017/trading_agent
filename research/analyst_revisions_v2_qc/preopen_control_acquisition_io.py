"""Physical trust boundary for completed ARV2 pre-open control construction.

Canonical ``verified=true`` JSON is not authority.  This loader verifies every
persisted output shard, a hash/count-only QC summary, an exact completed-run
receipt, and a mode-restricted external pin carrying the owner's detached
signature authority before the pure core receipt can be minted.  It performs
no provider, price, outcome, result, deployment, order, or trading action.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import stat
import sys
import heapq
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2 import preopen_control_acquisition as core
from research.analyst_revisions_v2_qc.preopen_quality_worker import (
    validate_q_data_measurement,
)
from research.analyst_revisions_v2_qc.owner_signature_authority import (
    OwnerSignatureAuthority,
    OwnerSignatureAuthorityError,
    require_preopen_acquisition_review_owner_signature,
)


class PreopenControlAcquisitionIoError(ValueError):
    pass


QC_EXECUTION_RECEIPT_SCHEMA = "arv2-preopen-control-qc-execution-receipt-v1"
EXTERNAL_REVIEW_PIN_SCHEMA = "arv2-preopen-control-external-review-pin-v1"
SUMMARY_SCHEMA = "arv2-preopen-control-summary-receipt-v1"
MAX_PRIVATE_RECEIPT_BYTES = 256 * 1024
MAX_OUTPUT_SHARD_COMPRESSED_BYTES = 32 * 1024 * 1024
MAX_OUTPUT_SHARD_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
_TERMINAL_FIELDS = {
    "schema", "decision_session", "security_id", "qc_security_id", "issuer_id",
    "share_class_id", "listing_id", "security_master_row_sha256",
    "disposition", "detail_reason", "eligible_security_session",
    "q_data_measurement", "census_refusal", "input_roots", "terminal_sha256",
}
_ELIGIBLE_FIELDS = {
    "decision_session", "security_id", "issuer_id", "share_class_id",
    "listing_id", "historical_ticker", "sector_id", "industry_id", "q_data",
    "controls", "source_id", "source_sha256", "identity_evidence_sha256",
    "identity_available_at", "classification_evidence_sha256",
    "classification_available_at", "q_data_evidence_sha256",
    "q_data_available_at", "control_evidence_sha256", "control_available_at",
    "control_vector_sha256", "point_in_time", "evidence_sha256",
    "earnings_anchor_signed_session_distance",
}
_REFUSAL_FIELDS = {
    "decision_session", "security_id", "issuer_id", "share_class_id",
    "listing_id", "historical_ticker", "reason", "source_id", "source_sha256",
    "available_at", "refusal_sha256",
}


def _strict(payload: bytes, name: str) -> dict[str, object]:
    if type(payload) is not bytes or not payload:
        raise PreopenControlAcquisitionIoError(f"{name} must be nonempty bytes")

    def pairs(items):
        result = {}
        for key, value in items:
            if type(key) is not str or key in result:
                raise PreopenControlAcquisitionIoError(
                    f"{name} has duplicate/non-string keys"
                )
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"), object_pairs_hook=pairs,
            parse_float=lambda _value: (_ for _ in ()).throw(
                PreopenControlAcquisitionIoError(f"{name} contains float")
            ),
            parse_constant=lambda _value: (_ for _ in ()).throw(
                PreopenControlAcquisitionIoError(f"{name} contains nonfinite")
            ),
        )
    except PreopenControlAcquisitionIoError:
        raise
    except (UnicodeError, ValueError, TypeError) as exc:
        raise PreopenControlAcquisitionIoError(f"{name} is not strict JSON") from exc
    if type(value) is not dict or canonical_json_bytes(value) != payload:
        raise PreopenControlAcquisitionIoError(f"{name} is not canonical JSON")
    return value


def _merkle(records: list[dict[str, object]]) -> str:
    if not records:
        return hashlib.sha256(canonical_json_bytes({
            "domain": "arv2-empty-terminal-set-v1"
        })).hexdigest()
    level = [hashlib.sha256(canonical_json_bytes({
        "domain": "arv2-terminal-leaf-v1", "record": row,
    })).hexdigest() for row in records]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [hashlib.sha256(canonical_json_bytes({
            "domain": "arv2-terminal-node-v1",
            "left": level[index], "right": level[index + 1],
        })).hexdigest() for index in range(0, len(level), 2)]
    return level[0]


def _utc(value: object, name: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise PreopenControlAcquisitionIoError(f"{name} is not exact UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise PreopenControlAcquisitionIoError(f"{name} is not exact UTC") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value:
        raise PreopenControlAcquisitionIoError(f"{name} is not canonical UTC")
    return parsed


def _before_open(value: object, session: str, name: str) -> None:
    try:
        opened = datetime.fromisoformat(session).replace(
            hour=9, minute=30, tzinfo=ZoneInfo("America/New_York")
        ).astimezone(timezone.utc)
    except (TypeError, ValueError) as exc:
        raise PreopenControlAcquisitionIoError(
            "terminal decision session changed"
        ) from exc
    if _utc(value, name) >= opened:
        raise PreopenControlAcquisitionIoError(
            f"{name} is not strictly before decision open"
        )


def _sha(value: object, name: str) -> None:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PreopenControlAcquisitionIoError(f"{name} is not SHA-256")


def _validate_terminal(row: dict[str, object]) -> None:
    if set(row) != _TERMINAL_FIELDS:
        raise PreopenControlAcquisitionIoError("output terminal fields changed")
    for name in (
        "decision_session", "security_id", "issuer_id", "share_class_id",
        "listing_id",
    ):
        if type(row[name]) is not str or not row[name]:
            raise PreopenControlAcquisitionIoError(
                f"output terminal {name} changed"
            )
    try:
        session = date.fromisoformat(row["decision_session"])
    except ValueError as exc:
        raise PreopenControlAcquisitionIoError(
            "output terminal decision session changed"
        ) from exc
    if session.isoformat() != row["decision_session"]:
        raise PreopenControlAcquisitionIoError(
            "output terminal decision session changed"
        )
    if row["disposition"] == "accepted":
        if type(row["qc_security_id"]) is not str or not row["qc_security_id"]:
            raise PreopenControlAcquisitionIoError(
                "accepted output lacks its QC permanent identity"
            )
    elif row["qc_security_id"] is not None:
        if type(row["qc_security_id"]) is not str or not row["qc_security_id"]:
            raise PreopenControlAcquisitionIoError(
                "refused output QC permanent identity changed"
            )
    _sha(row["security_master_row_sha256"], "security master row")
    roots = row["input_roots"]
    if type(roots) is not dict or set(roots) != {
        "universe", "sid_mapping", "fundamentals", "earnings", "guidance", "ratings",
        "market_observations",
    }:
        raise PreopenControlAcquisitionIoError("terminal input roots changed")
    for name, digest in roots.items():
        _sha(digest, name + " input root")
    identity = (
        row["decision_session"], row["security_id"], row["issuer_id"],
        row["share_class_id"], row["listing_id"],
    )
    if row["disposition"] == "accepted":
        eligible = row["eligible_security_session"]
        if (
            row["detail_reason"] is not None
            or row["census_refusal"] is not None
            or type(row["q_data_measurement"]) is not dict
            or type(eligible) is not dict
            or set(eligible) != _ELIGIBLE_FIELDS
            or tuple(eligible[name] for name in (
                "decision_session", "security_id", "issuer_id",
                "share_class_id", "listing_id",
            )) != identity
            or eligible["point_in_time"] is not True
            or any(
                type(eligible[name]) is not str or not eligible[name]
                for name in (
                    "historical_ticker", "sector_id", "industry_id", "source_id"
                )
            )
            or type(eligible["q_data"]) is not str
            or (
                eligible["earnings_anchor_signed_session_distance"] is not None
                and type(
                    eligible["earnings_anchor_signed_session_distance"]
                ) is not int
            )
        ):
            raise PreopenControlAcquisitionIoError(
                "accepted output terminal shape changed"
            )
        controls = eligible["controls"]
        if (
            type(controls) is not list
            or len(controls) != len(core.CONTROL_NAMES)
            or [item[0] for item in controls if type(item) is list and len(item) == 2]
            != list(core.CONTROL_NAMES)
        ):
            raise PreopenControlAcquisitionIoError("control vector shape changed")
        for index, item in enumerate(controls):
            value = item[1]
            if index < len(core.CONTINUOUS_CONTROL_NAMES):
                if type(value) is not str:
                    raise PreopenControlAcquisitionIoError(
                        "continuous control encoding changed"
                    )
                try:
                    parsed = Decimal(value)
                except InvalidOperation as exc:
                    raise PreopenControlAcquisitionIoError(
                        "continuous control is not decimal"
                    ) from exc
                if not parsed.is_finite():
                    raise PreopenControlAcquisitionIoError(
                        "continuous control is not finite"
                    )
            elif type(value) is not int or value not in (0, 1):
                raise PreopenControlAcquisitionIoError(
                    "binary control encoding changed"
                )
        try:
            quality = Decimal(eligible["q_data"])
        except (InvalidOperation, TypeError) as exc:
            raise PreopenControlAcquisitionIoError("q_data changed") from exc
        if not quality.is_finite() or not Decimal(0) <= quality <= Decimal(1):
            raise PreopenControlAcquisitionIoError("q_data changed")
        for name in (
            "source_sha256", "identity_evidence_sha256",
            "classification_evidence_sha256", "q_data_evidence_sha256",
            "control_evidence_sha256", "control_vector_sha256",
            "evidence_sha256",
        ):
            _sha(eligible[name], name)
        for name in (
            "identity_available_at", "classification_available_at",
            "q_data_available_at", "control_available_at",
        ):
            _before_open(eligible[name], row["decision_session"], name)
        opened = datetime.fromisoformat(row["decision_session"]).replace(
            hour=9, minute=30, tzinfo=ZoneInfo("America/New_York")
        ).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        try:
            validate_q_data_measurement(
                row["q_data_measurement"], row["security_id"],
                row["decision_session"], opened,
            )
        except ValueError as exc:
            raise PreopenControlAcquisitionIoError(
                "q_data measurement changed"
            ) from exc
        if (
            row["q_data_measurement"]["q_data"] != eligible["q_data"]
            or row["q_data_measurement"]["evidence_sha256"]
            != eligible["q_data_evidence_sha256"]
            or row["q_data_measurement"]["available_at"]
            != eligible["q_data_available_at"]
        ):
            raise PreopenControlAcquisitionIoError(
                "q_data measurement differs from eligible evidence"
            )
        if eligible["control_vector_sha256"] != hashlib.sha256(
            canonical_json_bytes(controls)
        ).hexdigest():
            raise PreopenControlAcquisitionIoError("control vector hash changed")
        semantic = dict(eligible)
        evidence_hash = semantic.pop("evidence_sha256")
        if evidence_hash != hashlib.sha256(
            canonical_json_bytes(semantic)
        ).hexdigest():
            raise PreopenControlAcquisitionIoError(
                "eligible evidence hash changed"
            )
    elif row["disposition"] == "named_refusal":
        refusal = row["census_refusal"]
        if (
            type(row["detail_reason"]) is not str
            or not row["detail_reason"]
            or row["eligible_security_session"] is not None
            or row["q_data_measurement"] is not None
            or type(refusal) is not dict
            or set(refusal) != _REFUSAL_FIELDS
            or tuple(refusal[name] for name in (
                "decision_session", "security_id", "issuer_id",
                "share_class_id", "listing_id",
            )) != identity
            or any(
                type(refusal[name]) is not str or not refusal[name]
                for name in ("historical_ticker", "reason", "source_id")
            )
        ):
            raise PreopenControlAcquisitionIoError(
                "refused output terminal shape changed"
            )
        _sha(refusal["source_sha256"], "refusal source")
        _sha(refusal["refusal_sha256"], "refusal hash")
        if refusal["available_at"] is not None:
            _before_open(
                refusal["available_at"], row["decision_session"],
                "refusal available_at",
            )
        semantic = dict(refusal)
        refusal_hash = semantic.pop("refusal_sha256")
        if refusal_hash != hashlib.sha256(
            canonical_json_bytes(semantic)
        ).hexdigest():
            raise PreopenControlAcquisitionIoError("refusal hash changed")
    else:
        raise PreopenControlAcquisitionIoError(
            "output terminal disposition changed"
        )


def _validated_output_payloads(
    manifest: dict[str, object], payloads: Iterable[bytes],
) -> tuple[str, dict[str, int]]:
    descriptors = manifest["output_shards"]
    try:
        payload_iterator = iter(payloads)
    except TypeError as exc:
        raise PreopenControlAcquisitionIoError(
            "output shard payloads are not iterable"
        ) from exc
    physical = []
    last_key: tuple[object, object] | None = None
    current_session: object | None = None
    current_rows: list[dict[str, object]] = []
    actual: dict[str, tuple[int, int, int, str, str | None, str]] = {}
    totals = {"terminal_count": 0, "accepted_count": 0, "refusal_count": 0}

    def finish_session() -> None:
        nonlocal current_rows, current_session
        if current_session is None:
            return
        accepted = sum(row["disposition"] == "accepted" for row in current_rows)
        refused = sum(
            row["disposition"] == "named_refusal" for row in current_rows
        )
        market_roots = {
            row["input_roots"]["market_observations"] for row in current_rows
        }
        if len(market_roots) != 1:
            raise PreopenControlAcquisitionIoError("session market roots differ")
        universe_rows = [{
            "terminal": "accepted" if row["disposition"] == "accepted" else "refused",
            "value": row["eligible_security_session"] if
            row["disposition"] == "accepted" else row["census_refusal"],
        } for row in current_rows]
        actual[str(current_session)] = (
            accepted, refused, len(current_rows), _merkle(current_rows),
            next(iter(market_roots)), _merkle(universe_rows),
        )
        totals["terminal_count"] += len(current_rows)
        totals["accepted_count"] += accepted
        totals["refusal_count"] += refused
        current_rows = []
    try:
        paired = zip(descriptors, payload_iterator, strict=True)
        for descriptor, payload in paired:
            if (
                type(descriptor) is not dict
                or type(payload) is not bytes
                or len(payload) != descriptor.get("compressed_byte_count")
                or len(payload) > MAX_OUTPUT_SHARD_COMPRESSED_BYTES
                or hashlib.sha256(payload).hexdigest()
                != descriptor.get("compressed_sha256")
            ):
                raise PreopenControlAcquisitionIoError("output shard identity changed")
            expected = descriptor.get("uncompressed_byte_count")
            if type(expected) is not int or not 0 <= expected <= MAX_OUTPUT_SHARD_UNCOMPRESSED_BYTES:
                raise PreopenControlAcquisitionIoError("output shard raw bound changed")
            try:
                with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as stream:
                    raw = stream.read(expected + 1)
                    extra = stream.read(1)
            except (OSError, EOFError) as exc:
                raise PreopenControlAcquisitionIoError("output shard gzip changed") from exc
            if (
                len(raw) != expected or extra
                or hashlib.sha256(raw).hexdigest()
                != descriptor.get("uncompressed_sha256")
            ):
                raise PreopenControlAcquisitionIoError("output shard raw identity changed")
            rows = []
            for line in raw.splitlines(keepends=True):
                row = _strict(line, "output terminal")
                if row.get("schema") != core.OUTPUT_TERMINAL_SCHEMA:
                    raise PreopenControlAcquisitionIoError("output terminal schema changed")
                _validate_terminal(row)
                semantic = dict(row)
                digest = semantic.pop("terminal_sha256", None)
                if digest != hashlib.sha256(canonical_json_bytes(semantic)).hexdigest():
                    raise PreopenControlAcquisitionIoError("terminal hash changed")
                key = (row.get("decision_session"), row.get("security_id"))
                if (
                    type(key[0]) is not str
                    or type(key[1]) is not str
                    or (last_key is not None and key <= last_key)
                ):
                    raise PreopenControlAcquisitionIoError(
                        "output terminals repeat or are not globally ordered"
                    )
                if current_session is not None and key[0] != current_session:
                    finish_session()
                current_session = key[0]
                current_rows.append(row)
                last_key = key
                rows.append(row)
            if len(rows) != descriptor.get("row_count"):
                raise PreopenControlAcquisitionIoError("output shard row census changed")
            physical.append({
                "ordinal": descriptor.get("ordinal"),
                "object_store_key": descriptor.get("object_store_key"),
                "payload_sha256": hashlib.sha256(payload).hexdigest(),
                "payload_byte_count": len(payload),
            })
            del raw, rows, payload
    except ValueError as exc:
        if type(exc) is not ValueError:
            raise
        raise PreopenControlAcquisitionIoError(
            "output shard payload census changed"
        ) from exc
    finish_session()
    commitments = {item.decision_session: item for item in core._parse_control_sessions(
        manifest["control_sessions"]
    )}
    universe_commitments = {
        item.decision_session: item for item in core._parse_universe_sessions(
            manifest["universe_sessions"]
        )
    }
    if (
        not set(actual).issubset(commitments)
        or set(commitments) != set(universe_commitments)
    ):
        raise PreopenControlAcquisitionIoError("output session census changed")
    for session in sorted(commitments):
        accepted, refused, terminal_count, control_root, market_root, universe_root = (
            actual.get(session, (0, 0, 0, _merkle([]), None, _merkle([])))
        )
        control = commitments[session]
        if (
            (accepted, refused, terminal_count, control_root)
            != (control.accepted_count, control.refusal_count,
                control.terminal_count, control.terminal_merkle_root)
            or (terminal_count and control.market_observation_sha256 != market_root)
        ):
            raise PreopenControlAcquisitionIoError("control commitment changed")
        universe = universe_commitments[session]
        if (
            (accepted, refused, terminal_count, universe_root)
            != (universe.accepted_count, universe.refusal_count,
                universe.terminal_count, universe.terminal_merkle_root)
        ):
            raise PreopenControlAcquisitionIoError("universe commitment changed")
    return hashlib.sha256(canonical_json_bytes(physical)).hexdigest(), totals


class _PhysicalShardCursor:
    """Bounded one-line cursor over one authenticated physical output shard."""

    def __init__(self, descriptor: dict[str, object], payload: bytes):
        if (
            type(payload) is not bytes
            or len(payload) != descriptor["compressed_byte_count"]
            or len(payload) > MAX_OUTPUT_SHARD_COMPRESSED_BYTES
            or hashlib.sha256(payload).hexdigest()
            != descriptor["compressed_sha256"]
        ):
            raise PreopenControlAcquisitionIoError(
                "output shard identity changed"
            )
        self.descriptor = descriptor
        self.stream = gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb")
        self.raw_sha256 = hashlib.sha256()
        self.raw_byte_count = 0
        self.row_count = 0
        self.last_key: tuple[str, str] | None = None
        self.first_session: str | None = None
        self.last_session: str | None = None
        self.first_security_id: str | None = None
        self.last_security_id: str | None = None

    def next(self) -> dict[str, object] | None:
        try:
            line = self.stream.readline(64 * 1024 + 1)
        except (OSError, EOFError) as exc:
            raise PreopenControlAcquisitionIoError(
                "output shard gzip changed"
            ) from exc
        if not line:
            self.stream.close()
            if (
                self.raw_byte_count != self.descriptor["uncompressed_byte_count"]
                or self.raw_sha256.hexdigest()
                != self.descriptor["uncompressed_sha256"]
                or self.row_count != self.descriptor["row_count"]
                or self.first_session
                != self.descriptor["partition_first_session"]
                or self.last_session != self.descriptor["partition_last_session"]
                or self.first_security_id != self.descriptor["first_security_id"]
                or self.last_security_id != self.descriptor["last_security_id"]
            ):
                raise PreopenControlAcquisitionIoError(
                    "output shard physical census changed"
                )
            return None
        if len(line) > 64 * 1024 or not line.endswith(b"\n"):
            raise PreopenControlAcquisitionIoError(
                "output terminal line exceeds bound or is unterminated"
            )
        self.raw_sha256.update(line)
        self.raw_byte_count += len(line)
        if self.raw_byte_count > MAX_OUTPUT_SHARD_UNCOMPRESSED_BYTES:
            raise PreopenControlAcquisitionIoError(
                "output shard raw bound exceeded"
            )
        row = _strict(line, "output terminal")
        if row.get("schema") != core.OUTPUT_TERMINAL_SCHEMA:
            raise PreopenControlAcquisitionIoError(
                "output terminal schema changed"
            )
        _validate_terminal(row)
        semantic = dict(row)
        digest = semantic.pop("terminal_sha256", None)
        if digest != hashlib.sha256(canonical_json_bytes(semantic)).hexdigest():
            raise PreopenControlAcquisitionIoError("terminal hash changed")
        key = (row["decision_session"], row["security_id"])
        if self.last_key is not None and key <= self.last_key:
            raise PreopenControlAcquisitionIoError(
                "physical output rows repeat or reorder"
            )
        self.last_key = key
        self.row_count += 1
        self.first_session = self.first_session or key[0]
        self.last_session = key[0]
        self.first_security_id = (
            key[1] if self.first_security_id is None
            else min(self.first_security_id, key[1])
        )
        self.last_security_id = (
            key[1] if self.last_security_id is None
            else max(self.last_security_id, key[1])
        )
        return row


def _validated_batch_major_output_payloads(
    manifest: dict[str, object], payloads: Iterable[bytes],
) -> tuple[str, dict[str, int]]:
    """Verify batch-major shards through a bounded logical k-way merge."""

    descriptors = manifest["output_shards"]
    try:
        iterator = iter(payloads)
    except TypeError as exc:
        raise PreopenControlAcquisitionIoError(
            "output shard payloads are not iterable"
        ) from exc
    physical: list[dict[str, object]] = []
    actual: dict[str, tuple[int, int, int, str, str | None, str]] = {}
    totals = {"terminal_count": 0, "accepted_count": 0, "refusal_count": 0}
    quality_sha256 = hashlib.sha256()
    quality_sha256.update(b'{"measurements":[')
    quality_first = True
    quality_count = 0
    last_global_key: tuple[str, str] | None = None
    current_session: str | None = None
    current_rows: list[dict[str, object]] = []

    def finish_session() -> None:
        nonlocal current_session, current_rows
        if current_session is None:
            return
        accepted = sum(row["disposition"] == "accepted" for row in current_rows)
        refused = len(current_rows) - accepted
        roots = {row["input_roots"]["market_observations"] for row in current_rows}
        if len(roots) != 1:
            raise PreopenControlAcquisitionIoError("session market roots differ")
        universe = [{
            "terminal": "accepted" if row["disposition"] == "accepted" else "refused",
            "value": row["eligible_security_session"] if
            row["disposition"] == "accepted" else row["census_refusal"],
        } for row in current_rows]
        actual[current_session] = (
            accepted, refused, len(current_rows), _merkle(current_rows),
            next(iter(roots)), _merkle(universe),
        )
        totals["terminal_count"] += len(current_rows)
        totals["accepted_count"] += accepted
        totals["refusal_count"] += refused
        current_rows = []

    maximum_group_bytes = manifest["construction_resource_census"].get(
        "maximum_logical_merge_compressed_bytes"
    )
    if type(maximum_group_bytes) is not int or maximum_group_bytes <= 0:
        raise PreopenControlAcquisitionIoError(
            "logical merge compressed-byte authority is missing"
        )
    offset = 0
    while offset < len(descriptors):
        chunk = descriptors[offset]["decision_chunk_ordinal"]
        group: list[dict[str, object]] = []
        while (
            offset < len(descriptors)
            and descriptors[offset]["decision_chunk_ordinal"] == chunk
        ):
            group.append(descriptors[offset])
            offset += 1
        group_payloads: list[bytes] = []
        for descriptor in group:
            try:
                payload = next(iterator)
            except StopIteration as exc:
                raise PreopenControlAcquisitionIoError(
                    "output shard payload census changed"
                ) from exc
            group_payloads.append(payload)
            physical.append({
                "ordinal": descriptor["ordinal"],
                "object_store_key": descriptor["object_store_key"],
                "payload_sha256": hashlib.sha256(payload).hexdigest(),
                "payload_byte_count": len(payload),
            })
        if sum(map(len, group_payloads)) > maximum_group_bytes:
            raise PreopenControlAcquisitionIoError(
                "logical merge compressed working set exceeded"
            )
        cursors = [
            _PhysicalShardCursor(descriptor, payload)
            for descriptor, payload in zip(group, group_payloads, strict=True)
        ]
        heap: list[tuple[str, str, int, dict[str, object]]] = []
        for cursor_index, cursor in enumerate(cursors):
            row = cursor.next()
            if row is not None:
                heapq.heappush(heap, (
                    row["decision_session"], row["security_id"],
                    cursor_index, row,
                ))
        while heap:
            session, security_id, cursor_index, row = heapq.heappop(heap)
            key = (session, security_id)
            if last_global_key is not None and key <= last_global_key:
                raise PreopenControlAcquisitionIoError(
                    "logical output terminals repeat or reorder"
                )
            if current_session is not None and session != current_session:
                finish_session()
            current_session = session
            current_rows.append(row)
            if row["disposition"] == "accepted":
                measurement = row["q_data_measurement"]
                if not quality_first:
                    quality_sha256.update(b",")
                quality_sha256.update(canonical_json_bytes(measurement)[:-1])
                quality_first = False
                quality_count += 1
            last_global_key = key
            following = cursors[cursor_index].next()
            if following is not None:
                heapq.heappush(heap, (
                    following["decision_session"], following["security_id"],
                    cursor_index, following,
                ))
        del cursors, group_payloads
    try:
        next(iterator)
    except StopIteration:
        pass
    else:
        raise PreopenControlAcquisitionIoError(
            "output shard payload census changed"
        )
    finish_session()
    quality_sha256.update(
        b'],"schema":"arv2-qdata-physical-measurement-projection-v1"}\n'
    )
    intermediate = manifest["construction_intermediates"]
    if (
        quality_count != intermediate["q_data_measurement_count"]
        or quality_sha256.hexdigest()
        != intermediate["q_data_measurement_projection_sha256"]
    ):
        raise PreopenControlAcquisitionIoError(
            "q_data measurement projection changed"
        )
    commitments = {
        item.decision_session: item for item in core._parse_control_sessions(
            manifest["control_sessions"]
        )
    }
    universe_commitments = {
        item.decision_session: item for item in core._parse_universe_sessions(
            manifest["universe_sessions"]
        )
    }
    if (
        not set(actual).issubset(commitments)
        or set(commitments) != set(universe_commitments)
    ):
        raise PreopenControlAcquisitionIoError("output session census changed")
    for session in sorted(commitments):
        accepted, refused, count, control_root, market_root, universe_root = (
            actual.get(session, (0, 0, 0, _merkle([]), None, _merkle([])))
        )
        control = commitments[session]
        universe = universe_commitments[session]
        if (
            (accepted, refused, count, control_root)
            != (control.accepted_count, control.refusal_count,
                control.terminal_count, control.terminal_merkle_root)
            or (count and market_root != control.market_observation_sha256)
            or (accepted, refused, count, universe_root)
            != (universe.accepted_count, universe.refusal_count,
                universe.terminal_count, universe.terminal_merkle_root)
        ):
            raise PreopenControlAcquisitionIoError(
                "logical output commitment changed"
            )
    return hashlib.sha256(canonical_json_bytes(physical)).hexdigest(), totals


def render_preopen_qc_execution_receipt(
    *, project_id: str, compile_id: str, backtest_id: str,
    input_manifest_sha256: str, project_source_set_sha256: str,
    output_manifest_sha256: str, summary_receipt_sha256: str,
) -> bytes:
    raw = {
        "schema": QC_EXECUTION_RECEIPT_SCHEMA,
        "receipt_id": None, "receipt_sha256": None,
        "terminal_status": "Completed", "project_id": project_id,
        "compile_id": compile_id, "backtest_id": backtest_id,
        "input_manifest_sha256": input_manifest_sha256,
        "project_source_set_sha256": project_source_set_sha256,
        "output_manifest_sha256": output_manifest_sha256,
        "summary_receipt_sha256": summary_receipt_sha256,
        "outcome_result_order_accessed": False,
    }
    digest = hashlib.sha256(canonical_json_bytes(raw)).hexdigest()
    raw["receipt_id"] = f"arv2-preopen-qc-execution-{digest[:24]}"
    raw["receipt_sha256"] = digest
    return canonical_json_bytes(raw)


def _execution_digest(value: dict[str, object]) -> str:
    seed = dict(value)
    seed["receipt_id"] = None
    seed["receipt_sha256"] = None
    return hashlib.sha256(canonical_json_bytes(seed)).hexdigest()


def _pin_seed(
    *, output_manifest_bytes: bytes, output_payload_projection_sha256: str,
    independent_review_receipt_bytes: bytes, qc_execution_receipt_bytes: bytes,
    summary_receipt_bytes: bytes,
) -> dict[str, object]:
    raw = {
        "schema": EXTERNAL_REVIEW_PIN_SCHEMA,
        "status": "owner_private_physical_preopen_acquisition_pin",
        "pin_id": None, "pin_sha256": None,
        "output_manifest_sha256": hashlib.sha256(output_manifest_bytes).hexdigest(),
        "output_shard_payload_projection_sha256": output_payload_projection_sha256,
        "independent_review_receipt_sha256": hashlib.sha256(
            independent_review_receipt_bytes
        ).hexdigest(),
        "qc_execution_receipt_sha256": hashlib.sha256(
            qc_execution_receipt_bytes
        ).hexdigest(),
        "summary_receipt_sha256": hashlib.sha256(summary_receipt_bytes).hexdigest(),
        "maximum_loads": 1,
    }
    digest = hashlib.sha256(canonical_json_bytes(raw)).hexdigest()
    raw["pin_id"] = f"arv2-preopen-acquisition-pin-{digest[:24]}"
    raw["pin_sha256"] = digest
    return raw


def render_preopen_control_external_review_pin_candidate(
    *, output_manifest_bytes: bytes, output_shard_payloads: Iterable[bytes],
    independent_review_receipt_bytes: bytes, qc_execution_receipt_bytes: bytes,
    summary_receipt_bytes: bytes,
) -> bytes:
    """Render exact review bytes; the unsigned candidate grants no authority."""

    manifest, _, _ = core._validate_manifest(output_manifest_bytes)
    projection, _ = _validated_batch_major_output_payloads(
        manifest, output_shard_payloads
    )
    return canonical_json_bytes(_pin_seed(
        output_manifest_bytes=output_manifest_bytes,
        output_payload_projection_sha256=projection,
        independent_review_receipt_bytes=independent_review_receipt_bytes,
        qc_execution_receipt_bytes=qc_execution_receipt_bytes,
        summary_receipt_bytes=summary_receipt_bytes,
    ))


def _read_private(path: Path) -> bytes:
    if type(path) is not type(Path()) or path.is_symlink():
        raise PreopenControlAcquisitionIoError("external pin must be nonsymlink Path")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or stat.S_IMODE(before.st_mode) & 0o077
                or not 0 < before.st_size <= MAX_PRIVATE_RECEIPT_BYTES):
            raise PreopenControlAcquisitionIoError("external pin is not private regular file")
        chunks = []
        remaining = MAX_PRIVATE_RECEIPT_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        if (len(payload) > MAX_PRIVATE_RECEIPT_BYTES or before.st_dev != after.st_dev
                or before.st_ino != after.st_ino or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ctime_ns != after.st_ctime_ns):
            raise PreopenControlAcquisitionIoError("external pin changed while read")
    finally:
        os.close(descriptor)
    return payload


def _load_physically_reviewed_preopen_control_acquisition_receipt_implementation(
    *, output_manifest_bytes: bytes, output_shard_payloads: Iterable[bytes],
    independent_review_receipt_bytes: bytes, qc_execution_receipt_bytes: bytes,
    summary_receipt_bytes: bytes, external_review_pin_path: Path,
    owner_signature: OwnerSignatureAuthority,
    require_owner_signature,
):
    manifest, _, _ = core._validate_manifest(output_manifest_bytes)
    projection, totals = _validated_batch_major_output_payloads(
        manifest, output_shard_payloads
    )
    summary = _strict(summary_receipt_bytes, "summary receipt")
    expected_summary = {
        "schema": SUMMARY_SCHEMA,
        "manifest_sha256": hashlib.sha256(output_manifest_bytes).hexdigest(),
        "manifest_byte_count": len(output_manifest_bytes),
        "source_set_sha256": manifest["project_source_set_sha256"],
        "terminal_count": totals["terminal_count"],
        "accepted_count": totals["accepted_count"],
        "refusal_count": totals["refusal_count"],
        "shard_count": len(manifest["output_shards"]),
    }
    if summary != expected_summary:
        raise PreopenControlAcquisitionIoError("QC summary receipt changed")
    execution = _strict(qc_execution_receipt_bytes, "QC execution receipt")
    digest = _execution_digest(execution)
    if (
        execution.get("schema") != QC_EXECUTION_RECEIPT_SCHEMA
        or execution.get("terminal_status") != "Completed"
        or execution.get("receipt_sha256") != digest
        or execution.get("receipt_id") != f"arv2-preopen-qc-execution-{digest[:24]}"
        or execution.get("input_manifest_sha256")
        != manifest["input_manifest"]["artifact_sha256"]
        or execution.get("project_source_set_sha256")
        != manifest["project_source_set_sha256"]
        or execution.get("output_manifest_sha256")
        != hashlib.sha256(output_manifest_bytes).hexdigest()
        or execution.get("summary_receipt_sha256")
        != hashlib.sha256(summary_receipt_bytes).hexdigest()
        or execution.get("outcome_result_order_accessed") is not False
    ):
        raise PreopenControlAcquisitionIoError("QC execution receipt changed")
    pin_bytes = _read_private(external_review_pin_path)
    pin = _strict(pin_bytes, "external review pin")
    expected_pin = _pin_seed(
        output_manifest_bytes=output_manifest_bytes,
        output_payload_projection_sha256=projection,
        independent_review_receipt_bytes=independent_review_receipt_bytes,
        qc_execution_receipt_bytes=qc_execution_receipt_bytes,
        summary_receipt_bytes=summary_receipt_bytes,
    )
    if pin != expected_pin:
        raise PreopenControlAcquisitionIoError("external review pin changed")
    try:
        require_owner_signature(owner_signature, authority_payload=pin_bytes)
    except OwnerSignatureAuthorityError as exc:
        raise PreopenControlAcquisitionIoError(
            "external review pin lacks exact owner-signature authority"
        ) from exc
    if _read_private(external_review_pin_path) != pin_bytes:
        raise PreopenControlAcquisitionIoError(
            "external review pin changed after owner authentication"
        )
    return (
        output_manifest_bytes,
        independent_review_receipt_bytes,
        execution["receipt_id"],
        execution["receipt_sha256"],
        pin["pin_id"],
        pin["pin_sha256"],
        projection,
    )


def _make_physical_acquisition_loader(
    implementation,
    owner_signature_requirer,
):
    receipt_minter = None
    loader_guard = None
    module_globals = globals()
    system_module = sys
    module_registry = system_module.modules
    module_name = __name__
    registered_module = module_registry.get(module_name)
    getpid = os.getpid
    authority_pid = getpid()
    exact_type = type
    exact_tuple = tuple
    any_true = any
    length = len
    read_vars = vars
    zip_strict = zip
    string_type = str
    missing = object()
    error_type = PreopenControlAcquisitionIoError
    import inspect

    currentframe = inspect.currentframe
    function_type = exact_type(lambda: None)
    module_type = exact_type(system_module)
    static_method_type = staticmethod
    class_method_type = classmethod
    property_type = property
    guarded_classes = (json.JSONDecoder, json.JSONEncoder)
    excluded_names = ("_seal_preopen_physical_loader",)

    def non_dunder_names() -> tuple[str, ...]:
        keys = exact_tuple(module_globals)
        if any_true(exact_type(name) is not string_type for name in keys):
            raise error_type("pre-open physical loader global census changed")
        return exact_tuple(
            name
            for name in keys
            if not name.startswith("__") and name not in excluded_names
        )

    def dependency_snapshot(roots):
        pending = list(roots)
        pending_classes = []
        seen: tuple[object, ...] = ()
        seen_classes: tuple[object, ...] = ()
        functions = []
        classes = []
        module_attributes = []
        while pending or pending_classes:
            if not pending:
                value_class = pending_classes.pop()
                if any_true(value_class is item for item in seen_classes):
                    continue
                seen_classes = (*seen_classes, value_class)
                class_namespace = read_vars(value_class)
                class_names = exact_tuple(class_namespace)
                class_bindings = exact_tuple(
                    (name, class_namespace[name]) for name in class_names
                )
                classes.append((value_class, class_names, class_bindings))
                for _name, attribute in class_bindings:
                    if exact_type(attribute) is function_type:
                        pending.append(attribute)
                    elif exact_type(attribute) in (
                        static_method_type,
                        class_method_type,
                    ):
                        pending.append(attribute.__func__)
                    elif exact_type(attribute) is property_type:
                        pending.extend(
                            item
                            for item in (
                                attribute.fget,
                                attribute.fset,
                                attribute.fdel,
                            )
                            if exact_type(item) is function_type
                        )
                continue
            function = pending.pop()
            if (
                function
                is load_physically_reviewed_preopen_control_acquisition_receipt
                or exact_type(function) is not function_type
                or any_true(
                function is item for item in seen
                )
            ):
                continue
            seen = (*seen, function)
            code = function.__code__
            function_globals = function.__globals__
            names = exact_tuple(code.co_names)
            closure = function.__closure__ or ()
            closure_values = exact_tuple(cell.cell_contents for cell in closure)
            builtin_namespace = function.__builtins__
            builtin_mapping = (
                builtin_namespace
                if exact_type(builtin_namespace) is dict
                else read_vars(builtin_namespace)
            )
            global_bindings = exact_tuple(
                (name, function_globals.get(name, missing)) for name in names
            )
            builtin_bindings = exact_tuple(
                (name, builtin_mapping.get(name, missing))
                for name, value in global_bindings
                if value is missing
            )
            functions.append((
                function,
                code,
                function_globals,
                exact_tuple(code.co_freevars),
                closure_values,
                builtin_namespace,
                builtin_mapping,
                global_bindings,
                builtin_bindings,
            ))
            for _name, value in global_bindings:
                if exact_type(value) is function_type:
                    pending.append(value)
                elif exact_type(value) is module_type:
                    namespace = read_vars(value)
                    for name in names:
                        if name not in namespace:
                            continue
                        attribute = namespace[name]
                        module_attributes.append(
                            (value, namespace, name, attribute)
                        )
                        if exact_type(attribute) is function_type:
                            pending.append(attribute)
                        elif any_true(
                            attribute is item for item in guarded_classes
                        ):
                            pending_classes.append(attribute)
                elif any_true(value is item for item in guarded_classes):
                    pending_classes.append(value)
            pending.extend(
                value
                for value in closure_values
                if exact_type(value) is function_type
            )
            pending_classes.extend(
                value
                for value in closure_values
                if any_true(value is item for item in guarded_classes)
            )
        return (
            exact_tuple(functions),
            exact_tuple(classes),
            exact_tuple(module_attributes),
        )

    def load_physically_reviewed_preopen_control_acquisition_receipt(
        *, output_manifest_bytes: bytes, output_shard_payloads: Iterable[bytes],
        independent_review_receipt_bytes: bytes,
        qc_execution_receipt_bytes: bytes, summary_receipt_bytes: bytes,
        external_review_pin_path: Path,
        owner_signature: OwnerSignatureAuthority,
    ):
        if loader_guard is None:
            raise error_type("pre-open physical loader authority is not sealed")
        loader_guard()
        verified = implementation(
            output_manifest_bytes=output_manifest_bytes,
            output_shard_payloads=output_shard_payloads,
            independent_review_receipt_bytes=independent_review_receipt_bytes,
            qc_execution_receipt_bytes=qc_execution_receipt_bytes,
            summary_receipt_bytes=summary_receipt_bytes,
            external_review_pin_path=external_review_pin_path,
            owner_signature=owner_signature,
            require_owner_signature=owner_signature_requirer,
        )
        if receipt_minter is None:
            raise error_type(
                "pre-open acquisition receipt authority is not installed"
            )
        return receipt_minter(
            output_manifest_bytes=verified[0],
            independent_review_receipt_bytes=verified[1],
            qc_execution_receipt_id=verified[2],
            qc_execution_receipt_sha256=verified[3],
            external_review_pin_id=verified[4],
            external_review_pin_sha256=verified[5],
            output_shard_payload_projection_sha256=verified[6],
        )

    def bind_receipt_minter(value) -> None:
        nonlocal receipt_minter
        if receipt_minter is not None or exact_type(value) is not exact_type(
            load_physically_reviewed_preopen_control_acquisition_receipt
        ):
            raise error_type(
                "pre-open acquisition receipt authority binding changed"
            )
        receipt_minter = value

    def seal_loader() -> None:
        nonlocal loader_guard
        if loader_guard is not None or receipt_minter is None:
            raise error_type("pre-open physical loader seal changed")
        if (
            system_module.modules is not module_registry
            or module_registry.get(module_name) is not registered_module
            or registered_module is None
            or read_vars(registered_module) is not module_globals
        ):
            raise error_type("pre-open physical loader module changed")
        expected_names = non_dunder_names()
        expected_globals = exact_tuple(
            (name, exact_type(module_globals[name]), module_globals[name])
            for name in expected_names
        )
        expected_code = (
            load_physically_reviewed_preopen_control_acquisition_receipt.__code__
        )
        (
            expected_dependencies,
            expected_classes,
            expected_module_attributes,
        ) = dependency_snapshot((
                implementation,
                owner_signature_requirer,
                receipt_minter,
            ))
        expected_freevars: tuple[str, ...] = ()
        expected_bindings: tuple[tuple[str, object], ...] = ()

        def require_loader_authority() -> None:
            frame = currentframe()
            caller = None if frame is None else frame.f_back
            caller_globals = None if caller is None else caller.f_globals
            caller_code = None if caller is None else caller.f_code
            caller_locals = {} if caller is None else caller.f_locals
            if (
                getpid() != authority_pid
                or system_module.modules is not module_registry
                or module_registry.get(module_name) is not registered_module
                or read_vars(registered_module) is not module_globals
                or caller_globals is not module_globals
                or caller_code is not expected_code
                or module_globals.get(
                    "load_physically_reviewed_preopen_control_acquisition_receipt",
                    missing,
                )
                is not load_physically_reviewed_preopen_control_acquisition_receipt
                or exact_tuple(caller_code.co_freevars) != expected_freevars
                or any_true(
                    caller_locals.get(name, missing) is not expected
                    for name, expected in expected_bindings
                )
                or non_dunder_names() != expected_names
                or any_true(
                    exact_type(module_globals.get(name, missing))
                    is not expected_type
                    or module_globals.get(name, missing) is not expected
                    for name, expected_type, expected in expected_globals
                )
                or any_true(
                    exact_type(function) is not function_type
                    or function.__code__ is not code
                    or function.__globals__ is not function_globals
                    or exact_tuple(code.co_freevars) != freevars
                    or length(function.__closure__ or ())
                    != length(closure_values)
                    or any_true(
                        cell.cell_contents is not expected
                        for cell, expected in zip_strict(
                            function.__closure__ or (),
                            closure_values,
                            strict=True,
                        )
                    )
                    or function.__builtins__ is not builtin_namespace
                    or (
                        builtin_mapping is not builtin_namespace
                        and read_vars(builtin_namespace) is not builtin_mapping
                    )
                    or any_true(
                        function_globals.get(name, missing) is not expected
                        for name, expected in global_bindings
                    )
                    or any_true(
                        builtin_mapping.get(name, missing) is not expected
                        for name, expected in builtin_bindings
                    )
                    for (
                        function,
                        code,
                        function_globals,
                        freevars,
                        closure_values,
                        builtin_namespace,
                        builtin_mapping,
                        global_bindings,
                        builtin_bindings,
                    ) in expected_dependencies
                )
                or any_true(
                    read_vars(namespace) is not mapping
                    or mapping.get(name, missing) is not expected
                    for namespace, mapping, name, expected
                    in expected_module_attributes
                )
                or any_true(
                    exact_tuple(read_vars(value_class)) != class_names
                    or any_true(
                        read_vars(value_class).get(name, missing) is not expected
                        for name, expected in class_bindings
                    )
                    for value_class, class_names, class_bindings
                    in expected_classes
                )
            ):
                raise error_type("pre-open physical loader authority changed")
            del caller
            del frame

        loader_guard = require_loader_authority
        expected_freevars = exact_tuple(expected_code.co_freevars)
        expected_bindings = exact_tuple(
            (name, cell.cell_contents)
            for name, cell in zip_strict(
                expected_freevars,
                load_physically_reviewed_preopen_control_acquisition_receipt.__closure__
                or (),
                strict=True,
            )
        )

    return (
        load_physically_reviewed_preopen_control_acquisition_receipt,
        bind_receipt_minter,
        seal_loader,
    )


(
    load_physically_reviewed_preopen_control_acquisition_receipt,
    _bind_preopen_receipt_minter,
    _seal_preopen_physical_loader,
) = _make_physical_acquisition_loader(
    _load_physically_reviewed_preopen_control_acquisition_receipt_implementation,
    require_preopen_acquisition_review_owner_signature,
)
_preopen_receipt_minter = core._claim_preopen_acquisition_receipt_minter(
    load_physically_reviewed_preopen_control_acquisition_receipt
)
_bind_preopen_receipt_minter(_preopen_receipt_minter)
del _make_physical_acquisition_loader
del _bind_preopen_receipt_minter
del _load_physically_reviewed_preopen_control_acquisition_receipt_implementation
del _preopen_receipt_minter
del require_preopen_acquisition_review_owner_signature


__all__ = [
    "EXTERNAL_REVIEW_PIN_SCHEMA", "PreopenControlAcquisitionIoError",
    "QC_EXECUTION_RECEIPT_SCHEMA",
    "load_physically_reviewed_preopen_control_acquisition_receipt",
    "render_preopen_control_external_review_pin_candidate",
    "render_preopen_qc_execution_receipt",
]
_seal_preopen_physical_loader()
del _seal_preopen_physical_loader
