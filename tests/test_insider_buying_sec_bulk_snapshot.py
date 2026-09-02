"""IB-1A tests for offline SEC quarterly ZIP integrity and publication."""
from __future__ import annotations

import hashlib
import os
import io
import json
import stat
import struct
import threading
import warnings
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from data.hashing import canonical_json, hash_bytes
from research.insider_buying import (
    ALLOWED_SEC_TABLES,
    REQUIRED_SEC_TABLES,
    SecBulkSnapshotError,
    SecBulkSource,
    inspect_sec_bulk_archive,
    load_sec_bulk_snapshot,
    write_sec_bulk_snapshot,
)
from research.insider_buying import sec_bulk_snapshot as snapshot_module


RETRIEVED = datetime(2026, 8, 20, 18, 0, tzinfo=timezone.utc)
GIT_COMMIT = "a" * 40
SOURCE_URL = (
    "https://www.sec.gov/files/dera/data/insider-transactions-data-sets/"
    "2026q2_form345.zip"
)


def _source(**overrides) -> SecBulkSource:
    values = {
        "year": 2026,
        "quarter": 2,
        "source_url": SOURCE_URL,
        "git_commit": GIT_COMMIT,
        "retrieved_at": RETRIEVED,
    }
    values.update(overrides)
    return SecBulkSource(**values)


def _table_bytes(name: str, *, suffix: bytes = b"") -> bytes:
    return (
        b"ACCESSION_NUMBER\tSYNTHETIC_VALUE\n"
        + f"0000123456-26-000001\t{name}\n".encode("utf-8")
        + suffix
    )


def _archive(
    *,
    names: tuple[str, ...] = ALLOWED_SEC_TABLES,
    payload_overrides: dict[str, bytes] | None = None,
    symlink_name: str | None = None,
    compression: int = zipfile.ZIP_DEFLATED,
    member_timestamp: tuple[int, int, int, int, int, int] = (
        2026,
        8,
        20,
        18,
        0,
        0,
    ),
) -> bytes:
    payload_overrides = payload_overrides or {}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name in names:
            info = zipfile.ZipInfo(name, date_time=member_timestamp)
            info.compress_type = compression
            info.create_system = 3
            info.external_attr = (
                ((stat.S_IFLNK | 0o777) if name == symlink_name else 0o100600)
                << 16
            )
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Duplicate name")
                archive.writestr(
                    info, payload_overrides.get(name, _table_bytes(name))
                )
    return stream.getvalue()


def _expected_raw_publication(archive: bytes):
    identity = inspect_sec_bulk_archive(archive, _source())
    manifest_bytes = (canonical_json(identity.to_payload()) + "\n").encode("utf-8")
    payloads = {
        "archive.zip": archive,
        "manifest.json": manifest_bytes,
    }
    commit_bytes = (
        canonical_json(
            {
                "kind": f"{snapshot_module.SNAPSHOT_KIND}-commit",
                "snapshot_id": identity.snapshot_id,
                "members": {
                    name: hash_bytes(data) for name, data in sorted(payloads.items())
                },
            }
        )
        + "\n"
    ).encode("utf-8")
    return identity, {**payloads, "snapshot.commit.json": commit_bytes}


def _set_first_member_encrypted(payload: bytes) -> bytes:
    mutated = bytearray(payload)
    local = mutated.find(b"PK\x03\x04")
    central = mutated.find(b"PK\x01\x02")
    assert local >= 0 and central >= 0
    local_flags = struct.unpack_from("<H", mutated, local + 6)[0] | 0x1
    central_flags = struct.unpack_from("<H", mutated, central + 8)[0] | 0x1
    struct.pack_into("<H", mutated, local + 6, local_flags)
    struct.pack_into("<H", mutated, central + 8, central_flags)
    return bytes(mutated)


def _corrupt_first_stored_member(payload: bytes) -> bytes:
    mutated = bytearray(payload)
    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
        info = archive.infolist()[0]
    name_length = struct.unpack_from("<H", mutated, info.header_offset + 26)[0]
    extra_length = struct.unpack_from("<H", mutated, info.header_offset + 28)[0]
    data_offset = info.header_offset + 30 + name_length + extra_length
    assert info.file_size > 0
    mutated[data_offset] ^= 0x01
    return bytes(mutated)


def _rewrite_manifest_and_commit(
    snapshot_dir: Path, mutate
) -> None:
    manifest_path = snapshot_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(manifest)
    manifest_bytes = (canonical_json(manifest) + "\n").encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)

    commit_path = snapshot_dir / "snapshot.commit.json"
    commit = json.loads(commit_path.read_text(encoding="utf-8"))
    commit["members"]["manifest.json"] = hash_bytes(manifest_bytes)
    commit_path.write_bytes((canonical_json(commit) + "\n").encode("utf-8"))


def _symlink_or_skip(link: Path, target: Path, *, is_directory: bool) -> None:
    try:
        link.symlink_to(target.resolve(), target_is_directory=is_directory)
    except OSError as exc:
        pytest.skip(f"filesystem symlinks unavailable: {exc}")


def _stat_like(status, **overrides):
    values = {
        "st_dev": status.st_dev,
        "st_ino": status.st_ino,
        "st_mode": status.st_mode,
        "st_size": status.st_size,
        "st_mtime_ns": status.st_mtime_ns,
        "st_file_attributes": getattr(status, "st_file_attributes", 0),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_valid_archive_round_trips_exact_bytes_and_member_lineage(tmp_path):
    archive = _archive()
    identity = inspect_sec_bulk_archive(archive, _source())
    assert identity.archive_sha256 == hash_bytes(archive)
    assert tuple(member.name for member in identity.members) == ALLOWED_SEC_TABLES
    assert all(member.size_bytes > 0 for member in identity.members)
    with zipfile.ZipFile(io.BytesIO(archive), "r") as source_zip:
        for member in identity.members:
            info = source_zip.getinfo(member.name)
            payload = source_zip.read(info)
            assert member.sha256 == hashlib.sha256(payload).hexdigest()
            assert member.size_bytes == len(payload) == info.file_size
            assert member.compressed_size_bytes == info.compress_size
            assert member.crc32 == f"{zlib.crc32(payload) & 0xFFFFFFFF:08x}"
            assert member.compression == "deflated"

    written = write_sec_bulk_snapshot(archive, _source(), tmp_path)
    loaded = load_sec_bulk_snapshot(tmp_path / written.snapshot_id)
    assert loaded.identity == identity
    assert loaded.archive_bytes == archive
    assert {
        path.name for path in (tmp_path / written.snapshot_id).iterdir()
    } == {"archive.zip", "manifest.json", "snapshot.commit.json"}
    assert (tmp_path / f".{written.snapshot_id}.publication.lock").is_file()


@pytest.mark.parametrize(
    "names",
    [
        REQUIRED_SEC_TABLES,
        REQUIRED_SEC_TABLES + ("FOOTNOTES.tsv", "OWNER_SIGNATURE.tsv"),
    ],
)
def test_allowed_optional_table_subsets_round_trip_in_canonical_order(
    tmp_path, names
):
    archive = _archive(names=names)
    identity = write_sec_bulk_snapshot(archive, _source(), tmp_path)
    assert tuple(member.name for member in identity.members) == names
    loaded = load_sec_bulk_snapshot(tmp_path / identity.snapshot_id)
    assert loaded.identity == identity
    assert loaded.archive_bytes == archive


def test_scrambled_zip_inventory_is_manifested_in_frozen_table_order(tmp_path):
    archive = _archive(
        names=(
            "FOOTNOTES.tsv",
            "NONDERIV_TRANS.tsv",
            "SUBMISSION.tsv",
            "REPORTINGOWNER.tsv",
        )
    )
    identity = write_sec_bulk_snapshot(archive, _source(), tmp_path)
    assert tuple(member.name for member in identity.members) == (
        "SUBMISSION.tsv",
        "REPORTINGOWNER.tsv",
        "NONDERIV_TRANS.tsv",
        "FOOTNOTES.tsv",
    )
    loaded = load_sec_bulk_snapshot(tmp_path / identity.snapshot_id)
    assert loaded.identity == identity
    assert loaded.archive_bytes == archive


def test_raw_boundary_preserves_empty_allowed_members_for_later_schema_refusal(
    tmp_path,
):
    archive = _archive(payload_overrides={"SUBMISSION.tsv": b""})
    identity = write_sec_bulk_snapshot(archive, _source(), tmp_path)
    submission = identity.members[0]
    assert submission.name == "SUBMISSION.tsv"
    assert submission.size_bytes == 0
    assert submission.sha256 == hashlib.sha256(b"").hexdigest()
    loaded = load_sec_bulk_snapshot(tmp_path / identity.snapshot_id)
    assert loaded.identity == identity
    assert loaded.archive_bytes == archive


def test_exact_retry_is_idempotent_and_different_provenance_changes_identity(tmp_path):
    archive = _archive()
    first = write_sec_bulk_snapshot(archive, _source(), tmp_path)
    member_paths = sorted((tmp_path / first.snapshot_id).iterdir())
    before = {path.name: path.stat().st_mtime_ns for path in member_paths}
    second = write_sec_bulk_snapshot(archive, _source(), tmp_path)
    after = {path.name: path.stat().st_mtime_ns for path in member_paths}
    assert second == first
    assert after == before

    later = inspect_sec_bulk_archive(
        archive, _source(retrieved_at=RETRIEVED + timedelta(seconds=1))
    )
    assert later.snapshot_id != first.snapshot_id

    other_code = inspect_sec_bulk_archive(
        archive, _source(git_commit="b" * 40)
    )
    assert other_code.lineage_hash != first.lineage_hash
    assert other_code.snapshot_id != first.snapshot_id


def test_archive_content_changes_both_lineage_hash_and_snapshot_identity():
    original = inspect_sec_bulk_archive(_archive(), _source())
    changed_archive = _archive(
        payload_overrides={
            ALLOWED_SEC_TABLES[0]: _table_bytes(ALLOWED_SEC_TABLES[0], suffix=b"x")
        }
    )
    changed = inspect_sec_bulk_archive(changed_archive, _source())
    assert changed.archive_sha256 != original.archive_sha256
    assert changed.lineage_hash != original.lineage_hash
    assert changed.snapshot_id != original.snapshot_id


def test_exact_zip_container_bytes_participate_in_lineage_identity():
    first_archive = _archive(member_timestamp=(2026, 8, 20, 18, 0, 0))
    second_archive = _archive(member_timestamp=(2026, 8, 21, 18, 0, 0))
    first = inspect_sec_bulk_archive(first_archive, _source())
    second = inspect_sec_bulk_archive(second_archive, _source())
    assert first.members == second.members
    assert first.archive_sha256 != second.archive_sha256
    assert first.lineage_hash != second.lineage_hash
    assert first.snapshot_id != second.snapshot_id


def test_full_source_url_participates_in_lineage_identity():
    archive = _archive()
    first = inspect_sec_bulk_archive(archive, _source())
    second = inspect_sec_bulk_archive(
        archive,
        _source(source_url="https://sec.gov/data/insider/2026q2_form345.zip"),
    )
    assert first.lineage_hash != second.lineage_hash
    assert first.snapshot_id != second.snapshot_id


def test_concurrent_exact_writers_publish_one_coherent_snapshot(tmp_path):
    archive = _archive()
    barrier = threading.Barrier(2)

    def publish():
        barrier.wait()
        return write_sec_bulk_snapshot(archive, _source(), tmp_path)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(publish)
        second_future = pool.submit(publish)
        first = first_future.result(timeout=10)
        second = second_future.result(timeout=10)
    assert first == second
    loaded = load_sec_bulk_snapshot(tmp_path / first.snapshot_id)
    assert loaded.identity == first
    assert loaded.archive_bytes == archive


def test_commit_marker_is_the_final_publication_call(monkeypatch, tmp_path):
    real_publish = snapshot_module.publish_immutable_bytes
    published_names: list[str] = []

    def record_publish(path, data):
        published_names.append(Path(path).name)
        return real_publish(path, data)

    monkeypatch.setattr(snapshot_module, "publish_immutable_bytes", record_publish)
    write_sec_bulk_snapshot(_archive(), _source(), tmp_path)
    assert published_names == ["archive.zip", "manifest.json", "snapshot.commit.json"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"year": True},
        {"year": 2005},
        {"year": 2025},
        {"quarter": 0},
        {"quarter": True},
        {"quarter": 1},
        {"source_url": "http://www.sec.gov/file.zip"},
        {"source_url": "https://example.com/file.zip"},
        {"source_url": "https://user@sec.gov/data/2026q2_form345.zip"},
        {"source_url": "https://www.sec.gov/../file.zip"},
        {"source_url": "https://www.sec.gov/../2026q2_form345.zip"},
        {"source_url": "https://www.sec.gov//2026q2_form345.zip"},
        {"source_url": SOURCE_URL + "?token=secret"},
        {"source_url": SOURCE_URL + "#fragment"},
        {"git_commit": "A" * 40},
        {"git_commit": "a" * 39},
        {"retrieved_at": datetime(2026, 8, 20, 18, 0)},
        {"retrieved_at": RETRIEVED.date()},
    ],
)
def test_source_contract_refuses_ambiguous_or_untrusted_lineage(overrides):
    with pytest.raises(SecBulkSnapshotError, match="REFUSED"):
        _source(**overrides)


def test_source_contract_does_not_invent_one_unverified_sec_directory_route():
    alternate = _source(
        source_url="https://sec.gov/data/insider/2026q2_form345.zip"
    )
    assert alternate.year == 2026
    assert alternate.quarter == 2


def test_source_retrieval_instant_is_serialized_in_canonical_utc():
    source = _source(
        retrieved_at=datetime(
            2026,
            8,
            20,
            11,
            0,
            tzinfo=timezone(-timedelta(hours=7)),
        )
    )
    assert source.retrieved_at_utc == "2026-08-20T18:00:00+00:00"
    identity = inspect_sec_bulk_archive(_archive(), source)
    assert identity.retrieved_at_utc == "2026-08-20T18:00:00+00:00"


@pytest.mark.parametrize(
    "retrieved_at",
    [
        datetime.max.replace(tzinfo=timezone(-timedelta(hours=23))),
        datetime.min.replace(tzinfo=timezone(timedelta(hours=23))),
    ],
)
def test_source_contract_refuses_instants_that_overflow_during_utc_conversion(
    retrieved_at,
):
    with pytest.raises(SecBulkSnapshotError, match="represented in UTC"):
        _source(retrieved_at=retrieved_at)


@pytest.mark.parametrize(
    "names,match",
    [
        (ALLOWED_SEC_TABLES[1:], "inventory mismatch"),
        (ALLOWED_SEC_TABLES + ("EXTRA.tsv",), "more than eight"),
        (ALLOWED_SEC_TABLES[:-1] + (ALLOWED_SEC_TABLES[0],), "duplicate"),
        (ALLOWED_SEC_TABLES[:-1] + ("submission.tsv",), "case-colliding"),
        (("../SUBMISSION.tsv",) + ALLOWED_SEC_TABLES[1:], "unsafe"),
        (("/SUBMISSION.tsv",) + ALLOWED_SEC_TABLES[1:], "unsafe"),
        (("nested/SUBMISSION.tsv",) + ALLOWED_SEC_TABLES[1:], "unsafe"),
        (("nested\\SUBMISSION.tsv",) + ALLOWED_SEC_TABLES[1:], "unsafe"),
    ],
)
def test_member_inventory_and_paths_fail_closed(names, match):
    with pytest.raises(SecBulkSnapshotError, match=match):
        inspect_sec_bulk_archive(_archive(names=names), _source())


def test_nul_suffixed_zip_name_cannot_masquerade_as_an_allowed_table():
    raw_name = b"SUBMISSION.tsvXevil"
    nul_name = b"SUBMISSION.tsv\x00evil"
    archive = _archive(
        names=(
            raw_name.decode("ascii"),
            "REPORTINGOWNER.tsv",
            "NONDERIV_TRANS.tsv",
        )
    )
    assert archive.count(raw_name) == 2
    archive = archive.replace(raw_name, nul_name)

    with pytest.raises(SecBulkSnapshotError, match="unsafe"):
        inspect_sec_bulk_archive(archive, _source())


def test_symlink_and_encrypted_members_are_refused():
    with pytest.raises(SecBulkSnapshotError, match="symlink"):
        inspect_sec_bulk_archive(
            _archive(symlink_name=ALLOWED_SEC_TABLES[0]), _source()
        )
    with pytest.raises(SecBulkSnapshotError, match="encrypted"):
        inspect_sec_bulk_archive(_set_first_member_encrypted(_archive()), _source())

    with pytest.raises(SecBulkSnapshotError, match="unsupported compression"):
        inspect_sec_bulk_archive(
            _archive(compression=zipfile.ZIP_BZIP2), _source()
        )


def test_corrupt_truncated_and_non_zip_inputs_are_refused():
    archive = _archive()
    with pytest.raises(SecBulkSnapshotError, match="malformed|corrupt"):
        inspect_sec_bulk_archive(archive[:-40], _source())
    with pytest.raises(SecBulkSnapshotError, match="malformed|corrupt"):
        inspect_sec_bulk_archive(b"not a zip", _source())

    corrupt_crc = _corrupt_first_stored_member(
        _archive(compression=zipfile.ZIP_STORED)
    )
    with pytest.raises(SecBulkSnapshotError, match="integrity|CRC|corrupt"):
        inspect_sec_bulk_archive(corrupt_crc, _source())


@pytest.mark.parametrize("bad", [b"\xff\xfe", b"valid\x00text"])
def test_member_text_must_be_utf8_without_nuls(bad):
    archive = _archive(payload_overrides={ALLOWED_SEC_TABLES[0]: bad})
    with pytest.raises(SecBulkSnapshotError, match="UTF-8"):
        inspect_sec_bulk_archive(archive, _source())


def test_resource_limits_refuse_before_publication(monkeypatch, tmp_path):
    real_hash_text_member = snapshot_module._hash_text_member
    archive = _archive(
        payload_overrides={ALLOWED_SEC_TABLES[0]: b"x" * 4096},
    )
    monkeypatch.setattr(snapshot_module, "MAX_ARCHIVE_BYTES", len(archive) - 1)
    with pytest.raises(SecBulkSnapshotError, match="compressed-size"):
        write_sec_bulk_snapshot(archive, _source(), tmp_path)
    assert not tmp_path.exists() or not any(tmp_path.iterdir())

    monkeypatch.setattr(snapshot_module, "MAX_ARCHIVE_BYTES", len(archive) + 1)
    monkeypatch.setattr(snapshot_module, "MAX_MEMBER_UNCOMPRESSED_BYTES", 1000)
    with pytest.raises(SecBulkSnapshotError, match="expanded-size"):
        inspect_sec_bulk_archive(archive, _source())

    monkeypatch.setattr(snapshot_module, "MAX_MEMBER_UNCOMPRESSED_BYTES", 10_000)
    monkeypatch.setattr(snapshot_module, "MAX_ARCHIVE_BYTES", 10_000)
    monkeypatch.setattr(
        snapshot_module,
        "MAX_TOTAL_UNCOMPRESSED_BYTES",
        sum(len(_table_bytes(name)) for name in ALLOWED_SEC_TABLES) - 1,
    )
    monkeypatch.setattr(
        snapshot_module,
        "_hash_text_member",
        lambda *args: pytest.fail("member bytes were read before metadata preflight"),
    )
    with pytest.raises(SecBulkSnapshotError, match="total expanded-size"):
        inspect_sec_bulk_archive(_archive(), _source())

    monkeypatch.setattr(snapshot_module, "_hash_text_member", real_hash_text_member)
    monkeypatch.setattr(snapshot_module, "MAX_TOTAL_UNCOMPRESSED_BYTES", 10_000)
    monkeypatch.setattr(snapshot_module, "MAX_COMPRESSION_RATIO", 1)
    with pytest.raises(SecBulkSnapshotError, match="compression-ratio"):
        inspect_sec_bulk_archive(archive, _source())


@pytest.mark.parametrize(
    "residue",
    [
        ("archive.zip",),
        ("archive.zip", "manifest.json"),
        ("archive.zip", ".manifest.json.hard-stop.tmp"),
    ],
)
def test_hard_restart_recovers_only_byte_exact_uncommitted_residue(
    tmp_path, residue
):
    archive = _archive()
    identity = inspect_sec_bulk_archive(archive, _source())
    target = tmp_path / identity.snapshot_id
    target.mkdir()
    manifest = (canonical_json(identity.to_payload()) + "\n").encode("utf-8")
    exact = {
        "archive.zip": archive,
        "manifest.json": manifest,
        ".manifest.json.hard-stop.tmp": manifest,
    }
    for name in residue:
        (target / name).write_bytes(exact[name])

    with pytest.raises(SecBulkSnapshotError, match="commit marker"):
        load_sec_bulk_snapshot(target)

    recovered = write_sec_bulk_snapshot(archive, _source(), tmp_path)
    assert recovered == identity
    assert {path.name for path in target.iterdir()} == {
        "archive.zip",
        "manifest.json",
        "snapshot.commit.json",
    }
    assert load_sec_bulk_snapshot(target).archive_bytes == archive


@pytest.mark.parametrize(
    "member_name", ("archive.zip", "manifest.json", "snapshot.commit.json")
)
@pytest.mark.parametrize("prefix_case", ("empty", "one-byte", "all-but-last"))
def test_hard_restart_recovers_interrupted_temp_prefix_for_every_member(
    tmp_path, member_name, prefix_case
):
    archive = _archive()
    identity, expected = _expected_raw_publication(archive)
    target = tmp_path / identity.snapshot_id
    target.mkdir()
    member_bytes = expected[member_name]
    prefix_length = {
        "empty": 0,
        "one-byte": 1,
        "all-but-last": len(member_bytes) - 1,
    }[prefix_case]
    abandoned = target / f".{member_name}.{prefix_case}.tmp"
    abandoned.write_bytes(member_bytes[:prefix_length])

    recovered = write_sec_bulk_snapshot(archive, _source(), tmp_path)

    assert recovered == identity
    assert not abandoned.exists()
    assert load_sec_bulk_snapshot(target).archive_bytes == archive
    assert write_sec_bulk_snapshot(archive, _source(), tmp_path) == identity


@pytest.mark.parametrize(
    "member_name", ("archive.zip", "manifest.json", "snapshot.commit.json")
)
def test_committed_retry_refuses_interrupted_temp_prefix_for_every_member(
    tmp_path, member_name
):
    archive = _archive()
    identity, expected = _expected_raw_publication(archive)
    assert write_sec_bulk_snapshot(archive, _source(), tmp_path) == identity
    target = tmp_path / identity.snapshot_id
    abandoned = target / f".{member_name}.committed-crash.tmp"
    partial = expected[member_name][:-1]
    abandoned.write_bytes(partial)

    with pytest.raises(SecBulkSnapshotError, match="unverified files"):
        write_sec_bulk_snapshot(archive, _source(), tmp_path)
    assert abandoned.read_bytes() == partial
    with pytest.raises(SecBulkSnapshotError, match="unexpected files"):
        load_sec_bulk_snapshot(target)
    assert (target / "archive.zip").read_bytes() == archive


@pytest.mark.parametrize(
    "member_name", ("archive.zip", "manifest.json", "snapshot.commit.json")
)
def test_hard_restart_refuses_and_preserves_nonprefix_member_temp(
    tmp_path, member_name
):
    archive = _archive()
    identity, _ = _expected_raw_publication(archive)
    target = tmp_path / identity.snapshot_id
    target.mkdir()
    abandoned = target / f".{member_name}.wrong-prefix.tmp"
    abandoned.write_bytes(b"\xff")

    with pytest.raises(SecBulkSnapshotError, match="unverified files"):
        write_sec_bulk_snapshot(archive, _source(), tmp_path)
    assert abandoned.read_bytes() == b"\xff"


def test_hard_restart_never_treats_a_truncated_final_member_as_a_temp(tmp_path):
    archive = _archive()
    identity, expected = _expected_raw_publication(archive)
    target = tmp_path / identity.snapshot_id
    target.mkdir()
    partial = expected["archive.zip"][:-1]
    (target / "archive.zip").write_bytes(partial)

    with pytest.raises(SecBulkSnapshotError, match="unverified files"):
        write_sec_bulk_snapshot(archive, _source(), tmp_path)
    assert (target / "archive.zip").read_bytes() == partial


def test_hard_restart_preserves_valid_prefix_when_any_residue_is_unverified(
    tmp_path,
):
    archive = _archive()
    identity, expected = _expected_raw_publication(archive)
    target = tmp_path / identity.snapshot_id
    target.mkdir()
    prefix = target / ".manifest.json.interrupted.tmp"
    foreign = target / "foreign.bin"
    prefix.write_bytes(expected["manifest.json"][:-1])
    foreign.write_bytes(b"foreign")
    before = {path.name: path.read_bytes() for path in target.iterdir()}

    with pytest.raises(SecBulkSnapshotError, match="unverified files"):
        write_sec_bulk_snapshot(archive, _source(), tmp_path)
    assert {path.name: path.read_bytes() for path in target.iterdir()} == before


@pytest.mark.parametrize("bad_name", ["manifest.json", "foreign.bin"])
def test_hard_restart_refuses_and_preserves_entire_unverified_residue(
    tmp_path, bad_name
):
    archive = _archive()
    identity = inspect_sec_bulk_archive(archive, _source())
    target = tmp_path / identity.snapshot_id
    target.mkdir()
    (target / "archive.zip").write_bytes(archive)
    (target / bad_name).write_bytes(b"unverified")

    before = {path.name: path.read_bytes() for path in target.iterdir()}
    with pytest.raises(SecBulkSnapshotError, match="unverified files"):
        write_sec_bulk_snapshot(archive, _source(), tmp_path)
    assert {path.name: path.read_bytes() for path in target.iterdir()} == before


def test_corrupt_committed_member_is_never_overwritten_by_retry(tmp_path):
    archive = _archive()
    identity = write_sec_bulk_snapshot(archive, _source(), tmp_path)
    target = tmp_path / identity.snapshot_id
    corrupt = b"corrupt"
    (target / "archive.zip").write_bytes(corrupt)
    with pytest.raises(SecBulkSnapshotError, match="hash mismatch"):
        load_sec_bulk_snapshot(target)
    with pytest.raises(SecBulkSnapshotError, match="hash mismatch"):
        write_sec_bulk_snapshot(archive, _source(), tmp_path)
    assert (target / "archive.zip").read_bytes() == corrupt


@pytest.mark.parametrize("mode", ["extra", "missing"])
def test_manifest_unknown_or_missing_fields_refuse_even_with_updated_commit(
    tmp_path, mode
):
    identity = write_sec_bulk_snapshot(_archive(), _source(), tmp_path)
    target = tmp_path / identity.snapshot_id

    def mutate(manifest):
        if mode == "extra":
            manifest["unexpected"] = True
        else:
            manifest.pop("source_url")

    _rewrite_manifest_and_commit(target, mutate)
    with pytest.raises(SecBulkSnapshotError, match="fields are not exact"):
        load_sec_bulk_snapshot(target)


def test_manifest_raw_contract_version_requires_an_exact_integer(tmp_path):
    identity = write_sec_bulk_snapshot(_archive(), _source(), tmp_path)
    target = tmp_path / identity.snapshot_id

    def mutate(manifest):
        manifest["raw_contract_version"] = True

    _rewrite_manifest_and_commit(target, mutate)
    with pytest.raises(SecBulkSnapshotError, match="contract version"):
        load_sec_bulk_snapshot(target)


def test_noncanonical_manifest_and_commit_json_are_refused(tmp_path):
    first = write_sec_bulk_snapshot(_archive(), _source(), tmp_path / "manifest")
    first_target = tmp_path / "manifest" / first.snapshot_id
    manifest_path = first_target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    noncanonical_manifest = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    manifest_path.write_bytes(noncanonical_manifest)
    commit_path = first_target / "snapshot.commit.json"
    commit = json.loads(commit_path.read_text(encoding="utf-8"))
    commit["members"]["manifest.json"] = hash_bytes(noncanonical_manifest)
    commit_path.write_bytes((canonical_json(commit) + "\n").encode("utf-8"))
    with pytest.raises(SecBulkSnapshotError, match="canonical JSON"):
        load_sec_bulk_snapshot(first_target)

    second = write_sec_bulk_snapshot(_archive(), _source(), tmp_path / "commit")
    second_target = tmp_path / "commit" / second.snapshot_id
    commit_path = second_target / "snapshot.commit.json"
    commit = json.loads(commit_path.read_text(encoding="utf-8"))
    commit_path.write_text(json.dumps(commit, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(SecBulkSnapshotError, match="canonical JSON"):
        load_sec_bulk_snapshot(second_target)


def test_json_lone_surrogate_is_mapped_to_snapshot_contract_error():
    with pytest.raises(SecBulkSnapshotError, match="missing or invalid"):
        snapshot_module._parse_canonical_object(
            b'{"x":"\\ud800"}\n',
            label="synthetic manifest",
        )


def test_loaded_snapshot_files_are_read_through_bounded_byte_images(
    monkeypatch, tmp_path
):
    identity = write_sec_bulk_snapshot(_archive(), _source(), tmp_path)
    target = tmp_path / identity.snapshot_id

    archive_size = (target / "archive.zip").stat().st_size
    monkeypatch.setattr(snapshot_module, "MAX_ARCHIVE_BYTES", archive_size - 1)
    with pytest.raises(SecBulkSnapshotError, match="byte-size"):
        load_sec_bulk_snapshot(target)

    monkeypatch.setattr(snapshot_module, "MAX_ARCHIVE_BYTES", archive_size + 1)
    manifest_size = (target / "manifest.json").stat().st_size
    monkeypatch.setattr(snapshot_module, "MAX_MANIFEST_BYTES", manifest_size - 1)
    with pytest.raises(SecBulkSnapshotError, match="byte-size"):
        load_sec_bulk_snapshot(target)

    monkeypatch.setattr(snapshot_module, "MAX_MANIFEST_BYTES", manifest_size + 1)
    commit_size = (target / "snapshot.commit.json").stat().st_size
    monkeypatch.setattr(snapshot_module, "MAX_COMMIT_BYTES", commit_size - 1)
    with pytest.raises(SecBulkSnapshotError, match="byte-size"):
        load_sec_bulk_snapshot(target)


def test_loader_parses_the_same_manifest_byte_image_verified_by_commit(
    monkeypatch, tmp_path
):
    identity = write_sec_bulk_snapshot(_archive(), _source(), tmp_path)
    target = tmp_path / identity.snapshot_id
    real_read = snapshot_module._read_regular_bytes
    manifest_reads = 0

    def count_reads(path, **kwargs):
        nonlocal manifest_reads
        if Path(path).name == "manifest.json":
            manifest_reads += 1
        return real_read(path, **kwargs)

    monkeypatch.setattr(snapshot_module, "_read_regular_bytes", count_reads)
    assert load_sec_bulk_snapshot(target).identity == identity
    assert manifest_reads == 1


def test_regular_file_reader_refuses_an_inode_swap_while_opening(
    monkeypatch, tmp_path
):
    path = tmp_path / "member.bin"
    path.write_bytes(b"bounded bytes")
    real_fstat = snapshot_module.os.fstat
    calls = 0

    def changed_identity(descriptor):
        nonlocal calls
        calls += 1
        status = real_fstat(descriptor)
        if calls == 1:
            return _stat_like(status, st_ino=status.st_ino + 1)
        return status

    monkeypatch.setattr(snapshot_module.os, "fstat", changed_identity)
    with pytest.raises(SecBulkSnapshotError, match="changed while it was opened"):
        snapshot_module._read_regular_bytes(
            path, label="synthetic member", max_bytes=100
        )


def test_regular_file_reader_refuses_a_version_change_during_read(
    monkeypatch, tmp_path
):
    path = tmp_path / "member.bin"
    path.write_bytes(b"bounded bytes")
    real_fstat = snapshot_module.os.fstat
    calls = 0

    def changed_version(descriptor):
        nonlocal calls
        calls += 1
        status = real_fstat(descriptor)
        if calls == 2:
            return _stat_like(status, st_mtime_ns=status.st_mtime_ns + 1)
        return status

    monkeypatch.setattr(snapshot_module.os, "fstat", changed_version)
    with pytest.raises(SecBulkSnapshotError, match="changed while it was read"):
        snapshot_module._read_regular_bytes(
            path, label="synthetic member", max_bytes=100
        )


def test_hash_valid_but_false_member_manifest_cannot_relabel_raw_bytes(tmp_path):
    identity = write_sec_bulk_snapshot(_archive(), _source(), tmp_path)
    target = tmp_path / identity.snapshot_id

    def mutate(manifest):
        manifest["members"][0]["sha256"] = "0" * 64

    _rewrite_manifest_and_commit(target, mutate)
    with pytest.raises(SecBulkSnapshotError, match="does not integrity-check"):
        load_sec_bulk_snapshot(target)


def test_directory_identity_and_unexpected_files_are_refused(tmp_path):
    identity = write_sec_bulk_snapshot(_archive(), _source(), tmp_path)
    target = tmp_path / identity.snapshot_id
    (target / "unexpected.txt").write_text("not part of snapshot", encoding="utf-8")
    with pytest.raises(SecBulkSnapshotError, match="unexpected files"):
        load_sec_bulk_snapshot(target)

    (target / "unexpected.txt").unlink()
    moved = tmp_path / "sec-insider-bulk-2026q2-0000000000000000"
    target.rename(moved)
    with pytest.raises(SecBulkSnapshotError, match="commit marker identity"):
        load_sec_bulk_snapshot(moved)


@pytest.mark.parametrize(
    "member_name", ["archive.zip", "manifest.json", "snapshot.commit.json"]
)
def test_loaded_snapshot_refuses_filesystem_symlink_members(tmp_path, member_name):
    identity = write_sec_bulk_snapshot(_archive(), _source(), tmp_path)
    target = tmp_path / identity.snapshot_id
    member = target / member_name
    outside = tmp_path / f"outside-{member_name}"
    member.replace(outside)
    _symlink_or_skip(member, outside, is_directory=False)
    with pytest.raises(SecBulkSnapshotError, match="regular immutable file"):
        load_sec_bulk_snapshot(target)


def test_snapshot_directory_redirects_are_refused_for_write_and_load(tmp_path):
    archive = _archive()
    identity = inspect_sec_bulk_archive(archive, _source())
    write_root = tmp_path / "write-root"
    write_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    _symlink_or_skip(
        write_root / identity.snapshot_id, outside, is_directory=True
    )
    with pytest.raises(SecBulkSnapshotError, match="non-redirected directory"):
        write_sec_bulk_snapshot(archive, _source(), write_root)
    assert not any(outside.iterdir())

    real_root = tmp_path / "real-root"
    written = write_sec_bulk_snapshot(archive, _source(), real_root)
    alias_root = tmp_path / "alias-root"
    alias_root.mkdir()
    alias = alias_root / written.snapshot_id
    _symlink_or_skip(alias, real_root / written.snapshot_id, is_directory=True)
    with pytest.raises(SecBulkSnapshotError, match="non-redirected directory"):
        load_sec_bulk_snapshot(alias)


def test_reparse_point_refusals_are_exercised_without_symlink_privileges(
    monkeypatch, tmp_path
):
    archive = _archive()
    source = _source()
    real_redirect_check = snapshot_module._status_is_redirect
    redirected: set[tuple[int, int]] = set()

    def identity(status):
        return status.st_dev, status.st_ino

    def simulated_redirect(status):
        return identity(status) in redirected or real_redirect_check(status)

    monkeypatch.setattr(snapshot_module, "_status_is_redirect", simulated_redirect)

    load_root = tmp_path / "load"
    written = write_sec_bulk_snapshot(archive, source, load_root)
    target = load_root / written.snapshot_id
    redirected.add(identity((target / "archive.zip").lstat()))
    with pytest.raises(SecBulkSnapshotError, match="regular immutable file"):
        load_sec_bulk_snapshot(target)

    redirected.clear()
    redirected.add(identity(target.lstat()))
    with pytest.raises(SecBulkSnapshotError, match="non-redirected directory"):
        load_sec_bulk_snapshot(target)

    redirected.clear()
    write_root = tmp_path / "write"
    write_root.mkdir()
    write_target = write_root / written.snapshot_id
    write_target.mkdir()
    redirected.add(identity(write_target.lstat()))
    with pytest.raises(SecBulkSnapshotError, match="non-redirected directory"):
        write_sec_bulk_snapshot(archive, source, write_root)

    redirected.clear()
    lock_root = tmp_path / "lock"
    lock_root.mkdir()
    lock_path = lock_root / f".{written.snapshot_id}.publication.lock"
    lock_path.write_bytes(b"\0")
    redirected.add(identity(lock_path.lstat()))
    with pytest.raises(SecBulkSnapshotError, match="lock must be a regular file"):
        write_sec_bulk_snapshot(archive, source, lock_root)


def test_windows_reparse_attribute_is_recognized_without_link_privileges(
    monkeypatch,
):
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024) or 1024
    monkeypatch.setattr(
        snapshot_module.stat,
        "FILE_ATTRIBUTE_REPARSE_POINT",
        reparse_flag,
        raising=False,
    )
    normal = SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0)
    redirected = SimpleNamespace(
        st_mode=stat.S_IFREG,
        st_file_attributes=reparse_flag,
    )
    symlink = SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0)
    assert not snapshot_module._status_is_redirect(normal)
    assert snapshot_module._status_is_redirect(redirected)
    assert snapshot_module._status_is_redirect(symlink)


def test_publication_lock_acquisition_failure_maps_to_snapshot_error(
    monkeypatch, tmp_path
):
    @contextmanager
    def fail_lock(_path):
        raise OSError("synthetic lock denial")
        yield

    monkeypatch.setattr(snapshot_module, "exclusive_file_lock", fail_lock)
    with pytest.raises(SecBulkSnapshotError, match="lock could not be acquired"):
        write_sec_bulk_snapshot(_archive(), _source(), tmp_path)


@pytest.mark.parametrize("fail_call", [1, 2, 3])
@pytest.mark.parametrize("failure_phase", ["before", "after"])
def test_publication_failure_rolls_back_new_members_and_retry_can_complete(
    monkeypatch, tmp_path, fail_call, failure_phase
):
    archive = _archive()
    identity = inspect_sec_bulk_archive(archive, _source())
    real_publish = snapshot_module.publish_immutable_bytes
    calls = 0

    def fail_selected(path, data):
        nonlocal calls
        calls += 1
        if calls == fail_call and failure_phase == "before":
            raise OSError("synthetic disk failure")
        result = real_publish(path, data)
        if calls == fail_call and failure_phase == "after":
            raise OSError("synthetic post-link failure")
        return result

    monkeypatch.setattr(snapshot_module, "publish_immutable_bytes", fail_selected)
    target = tmp_path / identity.snapshot_id
    if fail_call == 3 and failure_phase == "after":
        completed = write_sec_bulk_snapshot(archive, _source(), tmp_path)
        assert completed == identity
        assert load_sec_bulk_snapshot(target).archive_bytes == archive
        return

    with pytest.raises(SecBulkSnapshotError, match="publication"):
        write_sec_bulk_snapshot(archive, _source(), tmp_path)
    assert not any(target.iterdir())

    monkeypatch.setattr(snapshot_module, "publish_immutable_bytes", real_publish)
    completed = write_sec_bulk_snapshot(archive, _source(), tmp_path)
    assert completed == identity
    assert load_sec_bulk_snapshot(target).archive_bytes == archive


def test_abrupt_interruption_before_commit_rolls_back_and_retry_can_complete(
    monkeypatch,
    tmp_path,
):
    archive = _archive()
    identity = inspect_sec_bulk_archive(archive, _source())
    target = tmp_path / identity.snapshot_id
    real_publish = snapshot_module.publish_immutable_bytes

    def interrupt_after_manifest_link(path, data):
        result = real_publish(path, data)
        if Path(path).name == "manifest.json":
            raise KeyboardInterrupt("synthetic abrupt interruption")
        return result

    monkeypatch.setattr(
        snapshot_module,
        "publish_immutable_bytes",
        interrupt_after_manifest_link,
    )
    with pytest.raises(KeyboardInterrupt, match="abrupt interruption"):
        write_sec_bulk_snapshot(archive, _source(), tmp_path)
    assert target.is_dir()
    assert not any(target.iterdir())

    monkeypatch.setattr(snapshot_module, "publish_immutable_bytes", real_publish)
    completed = write_sec_bulk_snapshot(archive, _source(), tmp_path)
    assert completed == identity
    assert load_sec_bulk_snapshot(target).archive_bytes == archive


def test_temp_cleanup_failure_after_link_does_not_poison_retry(monkeypatch, tmp_path):
    archive = _archive()
    identity = inspect_sec_bulk_archive(archive, _source())
    target = tmp_path / identity.snapshot_id
    real_unlink = Path.unlink
    injected = False

    def fail_first_publisher_temp_cleanup(path, *args, **kwargs):
        nonlocal injected
        if (
            not injected
            and path.parent == target
            and path.name.startswith(".archive.zip.")
            and path.name.endswith(".tmp")
        ):
            injected = True
            raise OSError("synthetic temp cleanup failure")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_first_publisher_temp_cleanup)
    with pytest.raises(SecBulkSnapshotError, match="publication"):
        write_sec_bulk_snapshot(archive, _source(), tmp_path)
    assert injected
    assert target.is_dir()
    assert not any(target.iterdir())

    monkeypatch.setattr(Path, "unlink", real_unlink)
    completed = write_sec_bulk_snapshot(archive, _source(), tmp_path)
    assert completed == identity
    assert load_sec_bulk_snapshot(target).archive_bytes == archive


def test_observed_committed_snapshot_is_never_rolled_back(monkeypatch, tmp_path):
    archive = _archive()
    identity = inspect_sec_bulk_archive(archive, _source())
    target = tmp_path / identity.snapshot_id
    real_publish = snapshot_module.publish_immutable_bytes
    observed = []

    def observe_then_fail(path, data):
        result = real_publish(path, data)
        if Path(path).name == "snapshot.commit.json":
            observed.append(load_sec_bulk_snapshot(target))
            raise OSError("synthetic failure after another reader observed commit")
        return result

    monkeypatch.setattr(snapshot_module, "publish_immutable_bytes", observe_then_fail)
    completed = write_sec_bulk_snapshot(archive, _source(), tmp_path)
    assert completed == identity
    assert observed[0].identity == identity
    assert load_sec_bulk_snapshot(target).archive_bytes == archive


def test_post_commit_snapshot_contract_failure_recovers_and_returns_identity(
    monkeypatch,
    tmp_path,
):
    archive = _archive()
    identity = inspect_sec_bulk_archive(archive, _source())
    target = tmp_path / identity.snapshot_id
    real_load = snapshot_module.load_sec_bulk_snapshot
    calls = 0

    def fail_first_post_commit_check(path):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise SecBulkSnapshotError("REFUSED: synthetic post-commit check failure")
        return real_load(path)

    monkeypatch.setattr(
        snapshot_module,
        "load_sec_bulk_snapshot",
        fail_first_post_commit_check,
    )
    completed = write_sec_bulk_snapshot(archive, _source(), tmp_path)
    assert calls == 2
    assert completed == identity
    assert real_load(target).archive_bytes == archive


def test_commit_temp_cleanup_failure_recovers_the_committed_set(
    monkeypatch, tmp_path
):
    archive = _archive()
    identity = inspect_sec_bulk_archive(archive, _source())
    target = tmp_path / identity.snapshot_id
    real_unlink = Path.unlink
    injected = False

    def fail_commit_temp_cleanup(path, *args, **kwargs):
        nonlocal injected
        if (
            not injected
            and path.parent == target
            and path.name.startswith(".snapshot.commit.json.")
            and path.name.endswith(".tmp")
        ):
            injected = True
            raise OSError("synthetic committed-temp cleanup failure")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_commit_temp_cleanup)
    completed = write_sec_bulk_snapshot(archive, _source(), tmp_path)
    assert injected
    assert completed == identity
    assert {path.name for path in target.iterdir()} == {
        "archive.zip",
        "manifest.json",
        "snapshot.commit.json",
    }
    assert load_sec_bulk_snapshot(target).archive_bytes == archive


def test_retry_recovers_verified_commit_temp_left_by_abrupt_exit(tmp_path):
    archive = _archive()
    identity = write_sec_bulk_snapshot(archive, _source(), tmp_path)
    target = tmp_path / identity.snapshot_id
    commit_bytes = (target / "snapshot.commit.json").read_bytes()
    abandoned = target / ".snapshot.commit.json.abrupt.tmp"
    abandoned.write_bytes(commit_bytes)

    recovered = write_sec_bulk_snapshot(archive, _source(), tmp_path)
    assert recovered == identity
    assert not abandoned.exists()
    assert load_sec_bulk_snapshot(target).archive_bytes == archive


def test_retry_preserves_and_refuses_unverified_commit_temp(tmp_path):
    archive = _archive()
    identity = write_sec_bulk_snapshot(archive, _source(), tmp_path)
    target = tmp_path / identity.snapshot_id
    abandoned = target / ".snapshot.commit.json.unverified.tmp"
    abandoned.write_bytes(b"different bytes")

    with pytest.raises(SecBulkSnapshotError, match="unverified files"):
        write_sec_bulk_snapshot(archive, _source(), tmp_path)
    assert abandoned.read_bytes() == b"different bytes"


def test_committed_archive_with_a_hard_link_alias_refuses_load(tmp_path):
    """A second name for a committed artifact means it is not uniquely owned.

    IB-1C and IB-1H already refuse this; IB-1A did not, so the hardening that
    later milestones adopted had not propagated back to the raw boundary.
    """
    archive = _archive()
    identity = write_sec_bulk_snapshot(archive, _source(), tmp_path)
    directory = tmp_path / identity.snapshot_id

    alias = tmp_path / "alias-archive"
    try:
        os.link(directory / "archive.zip", alias)
    except (OSError, NotImplementedError, AttributeError):  # pragma: no cover
        pytest.skip("hard links are unavailable on this filesystem")

    with pytest.raises(
        SecBulkSnapshotError, match="regular immutable file"
    ):
        load_sec_bulk_snapshot(directory)


def test_committed_manifest_with_a_hard_link_alias_refuses_load(tmp_path):
    archive = _archive()
    identity = write_sec_bulk_snapshot(archive, _source(), tmp_path)
    directory = tmp_path / identity.snapshot_id

    alias = tmp_path / "alias-manifest"
    try:
        os.link(directory / "manifest.json", alias)
    except (OSError, NotImplementedError, AttributeError):  # pragma: no cover
        pytest.skip("hard links are unavailable on this filesystem")

    with pytest.raises(
        SecBulkSnapshotError, match="regular immutable file"
    ):
        load_sec_bulk_snapshot(directory)


def test_single_link_committed_snapshot_still_loads(tmp_path):
    """The guard must refuse aliased artifacts without refusing ordinary ones."""
    archive = _archive()
    identity = write_sec_bulk_snapshot(archive, _source(), tmp_path)
    loaded = load_sec_bulk_snapshot(tmp_path / identity.snapshot_id)
    assert loaded.identity == identity
