"""Invented metadata-only probes; caller must deny the whole process-tree network."""
import hashlib
import json
import io
import zipfile
from pathlib import Path

import pytest

import research.insider_buying_provider_metadata_audit as audit
from research.insider_buying_provider_metadata_transport import parse_provider_metadata


HEAD = "a" * 40
IDENTITY = {"root": "invented", "branch": audit.LANE_BRANCH, "head": HEAD,
            "source_sha256": {"invented.py": "b" * 64}, "status_sha256": "c" * 64}


def Receipt(provider):
    body = {"quantconnect": {"success": True}, "massive": {"market": "open"},
            "sharadar": {"table": "tickers", "name": "tickers.csv.zip", "size": 1,
                         "sizeLabel": "1 B", "modified": "2026-10-06T00:00:00Z"}}[provider]
    return parse_provider_metadata(provider, 200, json.dumps(body).encode())


def run(tmp_path, providers=("quantconnect", "massive"), probe=None, identity=None):
    return audit.run_metadata_audit(
        "ib-provider-metadata-invented", providers, HEAD, root=tmp_path,
        identity=identity or (lambda head, root: dict(IDENTITY)),
        probe=probe or (lambda provider, environ: Receipt(provider)),
        environ={"QC_API_TOKEN": "invented-only-secret"},
        clock=lambda: "2026-10-06T00:00:00Z")


def artifact(tmp_path):
    return tmp_path.joinpath(*audit.ARTIFACT_PARTS, "ib-provider-metadata-invented")


def test_started_journal_precedes_probe_and_credentials(tmp_path):
    calls = []
    def probe(provider, environ):
        directory = artifact(tmp_path)
        index = len(calls) + 1
        start = directory / f"{index:02d}-{provider}-started.json"
        assert start.is_file()
        assert (directory / "reservation.json").is_file()
        assert not (directory / f"{index:02d}-{provider}-completed.json").exists()
        calls.append(provider)
        return Receipt(provider)
    result = run(tmp_path, probe=probe)
    assert calls == ["quantconnect", "massive"]
    assert result["rights_entitlement_pit_research_readiness_established"] is False
    complete = artifact(tmp_path) / "complete.json"
    assert hashlib.sha256(complete.read_bytes()).hexdigest() == result["complete_sha256"]
    assert b"invented-only-secret" not in b"".join(p.read_bytes() for p in artifact(tmp_path).iterdir())
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in artifact(tmp_path).iterdir())
    assert artifact(tmp_path).stat().st_mode & 0o777 == 0o700


def test_completed_audit_cannot_resume_or_duplicate(tmp_path):
    run(tmp_path)
    calls = []
    with pytest.raises(audit.ProviderMetadataAuditError, match="existing_completed_or_ambiguous"):
        run(tmp_path, probe=lambda provider, environ: calls.append(provider))
    assert not calls


def test_ambiguous_failure_is_retained_and_sanitized(tmp_path):
    def fail(provider, environ):
        raise RuntimeError("invented-only-secret https://evil.invalid/?api_key=secret")
    with pytest.raises(audit.ProviderMetadataAuditError, match="started_reservation_preserved") as exc:
        run(tmp_path, probe=fail)
    assert "secret" not in str(exc.value)
    assert (artifact(tmp_path) / "01-quantconnect-started.json").is_file()
    assert not (artifact(tmp_path) / "complete.json").exists()
    with pytest.raises(audit.ProviderMetadataAuditError, match="existing_completed_or_ambiguous"):
        run(tmp_path)


def test_keyboard_interrupt_retains_no_retry_boundary(tmp_path):
    def stop(provider, environ):
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        run(tmp_path, probe=stop)
    assert (artifact(tmp_path) / "01-quantconnect-started.json").is_file()
    with pytest.raises(audit.ProviderMetadataAuditError, match="existing_completed_or_ambiguous"):
        run(tmp_path)


@pytest.mark.parametrize("providers", [(), [], ("massive", "massive"), ("sec",),
                                      ("quantconnect", "massive", "sharadar", "massive")])
def test_only_fixed_unique_profiles_before_any_files(tmp_path, providers):
    with pytest.raises(audit.ProviderMetadataAuditError, match="fixed_unique_provider"):
        run(tmp_path, providers=providers)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("name", ["../private", "IB-provider-metadata-x", "ib-provider-metadata-",
                                 "ib-provider-metadata-/x", "ib-provider-metadata-" + "x" * 81])
def test_audit_identifier_cannot_escape_root(tmp_path, name):
    with pytest.raises(audit.ProviderMetadataAuditError, match="audit_id_format"):
        audit.run_metadata_audit(name, ("massive",), HEAD, root=tmp_path,
                                 identity=lambda h, root: IDENTITY)
    assert not list(tmp_path.iterdir())


def test_wrong_identity_stops_before_journal_or_probe(tmp_path):
    def identity(head, root):
        raise audit.ProviderMetadataAuditError("worktree_branch_head_mismatch")
    with pytest.raises(audit.ProviderMetadataAuditError, match="worktree_branch_head_mismatch"):
        run(tmp_path, identity=identity)
    assert not list(tmp_path.iterdir())


def test_concurrent_change_before_probe_preserves_reservation_only(tmp_path):
    calls = []
    identities = iter([IDENTITY, {**IDENTITY, "head": "d" * 40}])
    with pytest.raises(audit.ProviderMetadataAuditError, match="changed_before_probe"):
        run(tmp_path, identity=lambda head, root: next(identities),
            probe=lambda provider, environ: calls.append(provider))
    assert not calls
    assert [p.name for p in artifact(tmp_path).iterdir()] == ["reservation.json"]


def test_concurrent_change_after_probe_stops_second_provider(tmp_path):
    calls = []
    identities = iter([IDENTITY, IDENTITY, {**IDENTITY, "source_sha256": {"x": "e" * 64}}])
    def probe(provider, environ):
        calls.append(provider)
        return Receipt(provider)
    with pytest.raises(audit.ProviderMetadataAuditError, match="changed_after_probe"):
        run(tmp_path, identity=lambda head, root: next(identities), probe=probe)
    assert calls == ["quantconnect"]
    assert (artifact(tmp_path) / "01-quantconnect-completed.json").is_file()
    assert not (artifact(tmp_path) / "02-massive-started.json").exists()


@pytest.mark.parametrize("depth", [0, 1, 2])
def test_symlink_parent_refused_without_external_writes(tmp_path, depth):
    outside = tmp_path / "outside"
    outside.mkdir()
    path = tmp_path
    for name in audit.ARTIFACT_PARTS[:depth]:
        path /= name
        path.mkdir()
    (path / audit.ARTIFACT_PARTS[depth]).symlink_to(outside, target_is_directory=True)
    with pytest.raises(audit.ProviderMetadataAuditError, match="journal_operation_refused"):
        run(tmp_path)
    assert not list(outside.iterdir())


def test_existing_leaf_file_not_overwritten(tmp_path):
    directory = tmp_path.joinpath(*audit.ARTIFACT_PARTS)
    directory.mkdir(parents=True)
    target = directory / "ib-provider-metadata-invented"
    target.write_bytes(b"preserve-user-data")
    with pytest.raises(audit.ProviderMetadataAuditError, match="existing_completed_or_ambiguous"):
        run(tmp_path)
    assert target.read_bytes() == b"preserve-user-data"


def test_exact_wrong_worktree_refused_before_git(tmp_path):
    with pytest.raises(audit.ProviderMetadataAuditError, match="designated_worktree_required"):
        audit._identity(HEAD, root=tmp_path)


@pytest.mark.parametrize("head", ["a" * 39, "A" * 40, "secret", "a" * 40 + "\n"])
def test_expected_head_strict(head):
    with pytest.raises(audit.ProviderMetadataAuditError, match="expected_head_format"):
        audit._identity(head)


def test_exclusive_journal_never_replaces(tmp_path):
    fd = audit.os.open(tmp_path, audit.os.O_RDONLY | audit.os.O_DIRECTORY)
    try:
        first = {"value": "original"}
        digest = audit._exclusive_json(fd, "x.json", first)
        with pytest.raises(FileExistsError):
            audit._exclusive_json(fd, "x.json", {"value": "changed"})
        assert hashlib.sha256((tmp_path / "x.json").read_bytes()).hexdigest() == digest
        assert json.loads((tmp_path / "x.json").read_bytes()) == first
    finally:
        audit.os.close(fd)


def supplied_capture(tmp_path, **updates):
    stream = io.BytesIO()
    csv = b"table,ticker\nnot-interpreted,secret-like-invented-row\n"
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as envelope:
        envelope.writestr("tickers.csv", csv)
    archive = stream.getvalue()
    (tmp_path / "01-tickers-years-full.zip").write_bytes(archive)
    manifest = {"schema": "arv2-sharadar-source-capture-artifact-v2", "api_key_persisted": False,
                "redirect_url_persisted": False,
                "tickers_availability_semantics": "capture_time_current_snapshot_active_and_delisted_not_point_in_time",
                "archives": [{"dataset": "tickers", "archive_file": "01-tickers-years-full.zip",
                              "archive_sha256": hashlib.sha256(archive).hexdigest(),
                              "archive_byte_count": len(archive), "uncompressed_byte_count": len(csv)}],
                **updates}
    raw = json.dumps(manifest).encode()
    (tmp_path / "manifest.json").write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def test_supplied_capture_only_header_and_no_credentials_outcomes_or_pit(tmp_path):
    digest = supplied_capture(tmp_path)
    # Unrelated licensed outcome files must remain unopened.
    (tmp_path / "02-actions-years-full.zip").write_bytes(b"refuse-if-opened")
    (tmp_path / "03-fundamentals-years-full.zip").write_bytes(b"refuse-if-opened")
    result = audit.inspect_supplied_sharadar_capture_metadata(tmp_path, digest)
    assert result["tickers_columns"] == ["table", "ticker"]
    assert result["tickers_rows_interpreted"] == 0
    assert result["actions_fundamentals_bodies_read"] == 0
    assert result["current_snapshot_only"] is True
    assert result["rights_verified"] is result["historical_pit_listing_identity_verified"] is False
    assert "secret-like" not in json.dumps(result)


def test_supplied_capture_changed_manifest_or_zip_refuses(tmp_path):
    digest = supplied_capture(tmp_path)
    with pytest.raises(audit.ProviderMetadataAuditError, match="manifest_anchor_mismatch"):
        audit.inspect_supplied_sharadar_capture_metadata(tmp_path, "c" * 64)
    target = tmp_path / "01-tickers-years-full.zip"
    target.write_bytes(target.read_bytes() + b"changed")
    with pytest.raises(audit.ProviderMetadataAuditError, match="archive_mismatch"):
        audit.inspect_supplied_sharadar_capture_metadata(tmp_path, digest)


@pytest.mark.parametrize("updates", [{"api_key_persisted": True}, {"redirect_url_persisted": True},
                                    {"tickers_availability_semantics": "pretend-historical-PIT"},
                                    {"archives": []}])
def test_supplied_capture_profile_cannot_silently_upgrade(tmp_path, updates):
    digest = supplied_capture(tmp_path, **updates)
    with pytest.raises(audit.ProviderMetadataAuditError):
        audit.inspect_supplied_sharadar_capture_metadata(tmp_path, digest)


def test_supplied_capture_symlink_and_hardlink_leaves_refuse(tmp_path):
    digest = supplied_capture(tmp_path)
    source = tmp_path / "manifest.json"
    kept = tmp_path / "kept.json"
    audit.os.link(source, kept)
    with pytest.raises(audit.ProviderMetadataAuditError, match="leaf_refused"):
        audit.inspect_supplied_sharadar_capture_metadata(tmp_path, digest)
    source.unlink()
    source.symlink_to(kept)
    with pytest.raises(audit.ProviderMetadataAuditError, match="inspection_refused"):
        audit.inspect_supplied_sharadar_capture_metadata(tmp_path, digest)


def test_supplied_capture_duplicate_manifest_keys_refuse(tmp_path):
    supplied_capture(tmp_path)
    raw = b'{"schema":"x","schema":"y"}'
    (tmp_path / "manifest.json").write_bytes(raw)
    with pytest.raises(audit.ProviderMetadataAuditError, match="duplicate_json_key"):
        audit.inspect_supplied_sharadar_capture_metadata(tmp_path, hashlib.sha256(raw).hexdigest())


@pytest.mark.parametrize("leaf", ["reservation.json", "01-quantconnect-started.json"])
@pytest.mark.parametrize("mutation", ["bytes", "symlink", "hardlink", "mode", "missing"])
def test_journal_is_rechecked_after_probe_before_any_completion(tmp_path, leaf, mutation):
    def probe(provider, environ):
        path = artifact(tmp_path) / leaf
        if mutation == "bytes":
            path.write_bytes(b"changed-concurrently")
        elif mutation == "mode":
            path.chmod(0o644)
        elif mutation == "missing":
            path.unlink()
        else:
            other = tmp_path / "other"
            other.write_bytes(path.read_bytes())
            path.unlink()
            if mutation == "symlink":
                path.symlink_to(other)
            else:
                audit.os.link(other, path)
        return Receipt(provider)
    with pytest.raises(audit.ProviderMetadataAuditError, match="journal_custody"):
        run(tmp_path, providers=("quantconnect",), probe=probe)
    assert not (artifact(tmp_path) / "complete.json").exists()
    assert not (artifact(tmp_path) / "01-quantconnect-completed.json").exists()


def test_extra_journal_leaf_and_replaced_directory_refuse(tmp_path):
    def probe(provider, environ):
        (artifact(tmp_path) / "extra.json").write_bytes(b"invented")
        return Receipt(provider)
    with pytest.raises(audit.ProviderMetadataAuditError, match="journal_custody"):
        run(tmp_path, providers=("quantconnect",), probe=probe)


@pytest.mark.parametrize("field,value", [("raw_body", "invented-private-sentinel"),
                                       ("research_ready", True), ("provider", "sharadar"),
                                       ("body_size_bytes", True), ("facts", {"raw_body": "invented-private-sentinel"})])
def test_unvalidated_receipt_cannot_publish_private_or_false_grant(tmp_path, field, value):
    receipt = Receipt("quantconnect").to_dict()
    receipt[field] = value
    class Unsafe:
        def to_dict(self):
            return receipt
    with pytest.raises(audit.ProviderMetadataAuditError, match="receipt_profile"):
        run(tmp_path, providers=("quantconnect",), probe=lambda provider, environ: Unsafe())
    assert not (artifact(tmp_path) / "01-quantconnect-completed.json").exists()
    assert b"invented-private-sentinel" not in b"".join(p.read_bytes() for p in artifact(tmp_path).iterdir())


def test_mutated_genuine_receipt_facts_refuse(tmp_path):
    value = Receipt("quantconnect")
    object.__setattr__(value, "_facts", b'{"raw_body":"invented-private-sentinel"}')
    with pytest.raises(audit.ProviderMetadataAuditError, match="receipt_profile"):
        run(tmp_path, providers=("quantconnect",), probe=lambda provider, environ: value)
    assert not (artifact(tmp_path) / "01-quantconnect-completed.json").exists()


def test_known_qc_negative_authentication_is_complete_not_ambiguous(tmp_path):
    value = parse_provider_metadata("quantconnect", 200, b'{"success":false}')
    result = run(tmp_path, providers=("quantconnect",), probe=lambda provider, environ: value)
    receipt = result["receipts"][0]["receipt"]
    assert receipt["disposition"] == "authentication-refused"
    assert receipt["facts"] == {"success": False}
    assert receipt["authentication_observed"] is False
    assert (artifact(tmp_path) / "complete.json").is_file()


@pytest.mark.parametrize("depth", [1, 2, 3])
def test_replaced_journal_ancestor_refuses_completion_in_moved_tree(tmp_path, depth):
    moved = tmp_path / "moved-existing-journal"
    def probe(provider, environ):
        ancestor = tmp_path.joinpath(*audit.ARTIFACT_PARTS[:depth])
        ancestor.rename(moved)
        ancestor.mkdir()
        return Receipt(provider)
    with pytest.raises(audit.ProviderMetadataAuditError, match="journal_custody"):
        run(tmp_path, providers=("quantconnect",), probe=probe)
    assert not tuple(moved.rglob("complete.json"))
    assert tuple(moved.rglob("01-quantconnect-started.json"))
