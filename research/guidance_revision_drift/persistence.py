"""Bounded immutable local synthetic journal; not an operator database.

The owner controls the directory and its ancestors. Hashes and a separately
retained head detect content changes/truncation, not hostile rollback when
the retained anchor is also lost. No cross-platform power-loss guarantee is
claimed: failed directory synchronization reports an ambiguous publication.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat
import tempfile

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.guidance_revision_drift.contracts import CandidateError, _decode, _read_regular_file

MAX_COMMANDS = 1024
MAX_RECORD_BYTES = 65536
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_COMMAND_FILE = re.compile(r"command-([0-9]{6})\.json\Z")


class JournalError(ValueError):
    """Invalid or unverifiable synthetic journal; do not continue blindly."""


class JournalConflict(JournalError):
    """A stale writer or conflicting immutable content was refused."""


class PublicationUncertain(JournalError):
    """Publication may exist, but synchronization/verification did not finish.

    Reload and verify the journal before retrying; this is not non-publication.
    """


def digest(value: object) -> str:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise JournalError("exact lowercase SHA-256 required")
    return value


def canonical_object(value: dict) -> bytes:
    try:
        raw = canonical_json(value).encode("utf-8")
        _decode(raw)
        return raw
    except (CandidateError, TypeError, ValueError, RecursionError) as exc:
        raise JournalError("bounded strict JSON object required") from exc


def decode_object(raw: bytes) -> dict:
    try:
        body = _decode(raw)
        if canonical_object(body) != raw:
            raise JournalError("canonical journal bytes required")
        return body
    except CandidateError as exc:
        raise JournalError("invalid journal JSON") from exc


def _read(path: Path) -> bytes:
    try:
        return _read_regular_file(path, MAX_RECORD_BYTES)
    except CandidateError as exc:
        raise JournalError("bounded regular journal file required") from exc


def _directory(path: Path) -> Path:
    try:
        if not stat.S_ISDIR(path.lstat().st_mode):
            raise JournalError("existing non-symlink owner-controlled directory required")
        return path.resolve(strict=True)
    except OSError as exc:
        raise JournalError("unavailable local journal directory") from exc


def _sync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish(directory: Path, filename: str, raw: bytes) -> None:
    """Atomic no-overwrite publication. Only our own staging file is removed."""
    directory = _directory(directory)
    decode_object(raw)
    temporary = None
    published = False
    publication_attempted = False
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=".gdr-journal-", suffix=".staging", dir=directory)
        try:
            remaining = memoryview(raw)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise OSError("incomplete journal write")
                remaining = remaining[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        destination = directory / filename
        try:
            publication_attempted = True
            os.link(temporary, destination)
            published = True
        except FileExistsError:
            if _read(destination) != raw:
                raise JournalConflict("immutable destination differs; reload competing writer")
            published = True
        _sync_directory(directory)
        if _read(destination) != raw:
            raise JournalError("published content verification failed")
    except (OSError, JournalError) as exc:
        if published or (publication_attempted and isinstance(exc, OSError)):
            raise PublicationUncertain("publication may exist; reload and verify before retry") from exc
        if isinstance(exc, JournalError):
            raise
        raise JournalError("publication failed before acknowledgment; reload before retry") from exc
    finally:
        if temporary is not None:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass  # A private staging remnant is never a committed command.


def _command_identity(command_id: object, operation: object, arguments: object) -> None:
    if (type(command_id) is not str or re.fullmatch(r"SYN-[A-Za-z0-9_.-]{1,96}", command_id) is None
            or type(operation) is not str or re.fullmatch(r"[a-z_]{1,40}", operation) is None
            or type(arguments) is not dict):
        raise JournalError("synthetic command ID, bounded operation and argument object required")


@dataclass(frozen=True, slots=True)
class JournalRecord:
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        body = decode_object(self.canonical_bytes)
        if set(body) != {"schema", "sequence", "previous_sha256", "genesis_sha256", "command_id",
                         "operation", "arguments", "result", "result_sha256", "post_state_sha256"}:
            raise JournalError("unknown or missing journal record fields")
        if (body["schema"] != "gdr.synthetic.command.v1" or type(body["sequence"]) is not int
                or not 1 <= body["sequence"] <= MAX_COMMANDS):
            raise JournalError("invalid command schema or sequence")
        for field in ("previous_sha256", "genesis_sha256", "result_sha256", "post_state_sha256"):
            digest(body[field])
        _command_identity(body["command_id"], body["operation"], body["arguments"])
        if hash_payload(body["result"]) != body["result_sha256"]:
            raise JournalError("command result hash mismatch")

    def to_dict(self) -> dict:
        self.__post_init__()
        return decode_object(self.canonical_bytes)

    @property
    def sha256(self) -> str:
        self.__post_init__()
        return hash_bytes(self.canonical_bytes)


@dataclass(frozen=True, slots=True)
class JournalView:
    genesis_bytes: bytes
    records: tuple[JournalRecord, ...]

    @property
    def head_sha256(self) -> str:
        return self.records[-1].sha256 if self.records else hash_bytes(self.genesis_bytes)


class LocalJournal:
    """A single synthetic store with optimistic no-overwrite sequence claims."""

    def __init__(self, directory: Path, genesis_bytes: bytes):
        body = decode_object(genesis_bytes)
        if body.get("schema") != "gdr.synthetic.recovery-genesis.v1":
            raise JournalError("synthetic recovery genesis required")
        self.directory = _directory(Path(directory))
        self.genesis_bytes = genesis_bytes
        self.genesis_sha256 = hash_bytes(genesis_bytes)

    @classmethod
    def create(cls, directory: Path, genesis_bytes: bytes) -> LocalJournal:
        store = cls(directory, genesis_bytes)
        # Existing same genesis is idempotent; different bytes never overwrite.
        _publish(store.directory, "genesis.json", genesis_bytes)
        store.read(expected_head=store.genesis_sha256)
        return store

    @classmethod
    def open(cls, directory: Path, *, expected_genesis_sha256: str) -> LocalJournal:
        digest(expected_genesis_sha256)
        directory = _directory(Path(directory))
        raw = _read(directory / "genesis.json")
        if hash_bytes(raw) != expected_genesis_sha256:
            raise JournalError("genesis differs from retained identity")
        store = cls(directory, raw)
        store.read(expected_head=expected_genesis_sha256)
        return store

    def read(self, *, expected_head: str) -> JournalView:
        """Require a retained ancestor; include any verified committed tail.

        This permits recovery after an uncertain append acknowledgment while
        refusing truncation behind the caller's independently retained anchor.
        """
        digest(expected_head)
        directory = _directory(self.directory)
        if _read(directory / "genesis.json") != self.genesis_bytes:
            raise JournalError("journal genesis changed")
        numbers = []
        count = 0
        try:
            for path in directory.iterdir():
                count += 1
                if count > 3 * MAX_COMMANDS + 32:
                    raise JournalError("journal directory exceeds bounded inventory")
                match = _COMMAND_FILE.fullmatch(path.name)
                if match:
                    numbers.append(int(match[1]))
                elif path.name == "genesis.json" or re.fullmatch(r"checkpoint-[0-9a-f]{64}\.json", path.name):
                    continue
                elif path.name.startswith(".gdr-journal-") and path.name.endswith(".staging"):
                    continue
                else:
                    raise JournalError("unexpected journal directory entry")
        except OSError as exc:
            raise JournalError("cannot inventory journal") from exc
        if len(numbers) > MAX_COMMANDS or sorted(numbers) != list(range(1, len(numbers) + 1)):
            raise JournalError("missing, invalid or excessive command sequence")
        prior = self.genesis_sha256
        heads = {prior}
        identities = set()
        records = []
        for sequence in range(1, len(numbers) + 1):
            record = JournalRecord(_read(directory / f"command-{sequence:06d}.json"))
            body = record.to_dict()
            if (body["sequence"] != sequence or body["previous_sha256"] != prior
                    or body["genesis_sha256"] != self.genesis_sha256 or body["command_id"] in identities):
                raise JournalError("broken command chain or reused command identity")
            records.append(record)
            identities.add(body["command_id"])
            prior = record.sha256
            heads.add(prior)
        if expected_head not in heads:
            raise JournalError("retained head missing: truncation, changed lineage or wrong store")
        return JournalView(self.genesis_bytes, tuple(records))

    def append(self, *, expected_head: str, command_id: str, operation: str, arguments: dict,
               result: object, post_state_sha256: str) -> JournalRecord:
        _command_identity(command_id, operation, arguments)
        digest(post_state_sha256)
        view = self.read(expected_head=expected_head)
        for old in view.records:
            body = old.to_dict()
            if body["command_id"] == command_id:
                fields = {"operation": operation, "arguments": arguments, "result": result,
                          "post_state_sha256": post_state_sha256}
                if canonical_json({k: body[k] for k in fields}) != canonical_json(fields):
                    raise JournalConflict("conflicting command identity replay")
                # An earlier invocation may have linked these exact bytes but
                # lost its directory-sync acknowledgment. Retry the complete
                # publication barrier rather than acknowledging a mere read.
                _publish(self.directory, f"command-{body['sequence']:06d}.json", old.canonical_bytes)
                return old
        if view.head_sha256 != expected_head:
            raise JournalConflict("stale append head; reload before retry")
        body = {"schema": "gdr.synthetic.command.v1", "sequence": len(view.records) + 1,
                "previous_sha256": expected_head, "genesis_sha256": self.genesis_sha256,
                "command_id": command_id, "operation": operation, "arguments": arguments,
                "result": result, "result_sha256": hash_payload(result),
                "post_state_sha256": post_state_sha256}
        record = JournalRecord(canonical_object(body))
        _publish(self.directory, f"command-{body['sequence']:06d}.json", record.canonical_bytes)
        return record

    def synchronize(self, *, expected_head: str) -> None:
        """Complete the directory barrier when recovering an uncertain tail."""
        view = self.read(expected_head=expected_head)
        if view.head_sha256 != expected_head:
            raise JournalConflict("history advanced during recovery; reload again")
        try:
            _sync_directory(_directory(self.directory))
        except (OSError, JournalError) as exc:
            raise PublicationUncertain("cannot acknowledge recovered publication; synchronization incomplete") from exc
        if self.read(expected_head=expected_head).head_sha256 != expected_head:
            raise JournalConflict("history advanced during synchronization; reload again")

    def checkpoint(self, *, expected_head: str, state_sha256: str) -> str:
        digest(state_sha256)
        view = self.read(expected_head=expected_head)
        if view.head_sha256 != expected_head:
            raise JournalConflict("stale checkpoint head")
        if view.records and view.records[-1].to_dict()["post_state_sha256"] != state_sha256:
            raise JournalError("checkpoint state disagrees with committed command")
        body = {"schema": "gdr.synthetic.checkpoint.v1", "genesis_sha256": self.genesis_sha256,
                "sequence": len(view.records), "head_sha256": expected_head, "state_sha256": state_sha256}
        raw = canonical_object(body)
        identity = hash_bytes(raw)
        _publish(self.directory, f"checkpoint-{identity}.json", raw)
        return identity

    def read_checkpoint(self, checkpoint_sha256: str) -> dict:
        digest(checkpoint_sha256)
        raw = _read(self.directory / f"checkpoint-{checkpoint_sha256}.json")
        body = decode_object(raw)
        if (hash_bytes(raw) != checkpoint_sha256 or set(body) != {
                "schema", "genesis_sha256", "sequence", "head_sha256", "state_sha256"}
                or body["schema"] != "gdr.synthetic.checkpoint.v1"
                or body["genesis_sha256"] != self.genesis_sha256
                or type(body["sequence"]) is not int or not 0 <= body["sequence"] <= MAX_COMMANDS):
            raise JournalError("invalid checkpoint identity or fields")
        digest(body["state_sha256"])
        view = self.read(expected_head=digest(body["head_sha256"]))
        sequence = body["sequence"]
        if (sequence > len(view.records) or (view.records[sequence - 1].sha256 if sequence else self.genesis_sha256)
                != body["head_sha256"]):
            raise JournalError("checkpoint sequence does not identify its head")
        return body
