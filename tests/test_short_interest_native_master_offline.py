"""Fabricated offline artifacts only: no private source or provider access."""
from __future__ import annotations

import json

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
import scripts.build_short_interest_native_master_offline as build
from scripts.qualify_finra_short_interest import _prepare_capture_directory, _publish, _publish_json
from test_short_interest_sharadar_securities_master import archives
from test_short_interest_sharadar_companion_qualification import report as companion_report
import os

pytestmark = pytest.mark.skipif(
    not hasattr(os, "getuid"),
    reason=(
        "the protected-capture runtime requires POSIX ownership and mode "
        "semantics (os.getuid, O_NOFOLLOW, 0o600/0o700, symlinks); it cannot "
        "execute on this host, see the lane record SI-CR17-002"
    ),
)

ANCHOR = "2026-10-12T06:01:39Z"
STARTED = "2026-10-12T06:30:00Z"
COMPLETED = "2026-10-12T06:31:00Z"
HEAD, REMOTE = "a" * 40, "b" * 40


@pytest.fixture
def source(tmp_path, monkeypatch):
    qualification = build.master.qualify_sharadar_securities_master(archives(), retrieved_at=ANCHOR)
    captures = qualification.captures
    provenance = build.segments.MasterReportProvenance(
        source_capture_receipt_sha256=build.finalizer.SOURCE_INVENTORY_SHA256,
        source_code_identity_sha256=hash_payload({"git_commit": build.finalizer.SOURCE_HEAD,
                                                 "protocol_sha256": build.master.PROTOCOL_SHA256}),
        finalizer_code_identity_sha256="c" * 64, reconstruction_anchor_utc=ANCHOR)
    segmented = build.segments.encode_report(canonical_json(qualification.to_payload()).encode(),
                                             provenance=provenance)
    monkeypatch.setattr(build, "SOURCE_INDEX_SHA256", segmented.index.to_payload()["index_sha256"])
    monkeypatch.setattr(build.finalizer, "_code_identity", lambda *args: "c" * 64)
    monkeypatch.setattr(build.finalizer, "_reload", lambda root: (captures, ANCHOR))
    monkeypatch.setattr(build.companion_reader, "_rebuild_sharadar", lambda root: companion_report())
    source_dir = _prepare_capture_directory(tmp_path / build.finalizer.SOURCE)
    directory = _prepare_capture_directory(source_dir / build.finalizer.OUTPUT_NAME)
    _publish(directory, "index.private.json", segmented.index.to_bytes())
    for part in segmented.index.parts:
        _publish(directory, f"part-{part.position + 1:03d}.private", segmented.parts[part.position])
    start = {"schema": "si-master-offline-finalization-start-v1", "code_head": build.SOURCE_FINALIZER_HEAD,
        "source_code_head": build.finalizer.SOURCE_HEAD,
        "source_inventory_sha256": build.finalizer.SOURCE_INVENTORY_SHA256,
        "source_reconstruction_anchor": ANCHOR, "started_at": "2026-10-12T06:10:00Z",
        "provider_requests": 0, "credential_reads": 0, "qc_attempts": 0, "outcome_looks": 0}
    end = {"schema": "si-master-offline-finalization-complete-v1", "status": "offline_finalization_complete",
        "code_head": build.SOURCE_FINALIZER_HEAD, "source_code_head": build.finalizer.SOURCE_HEAD,
        "private_index_sha256": build.SOURCE_INDEX_SHA256, "completed_at": build.SOURCE_COMPLETED_AT,
        "provider_requests": 0, "credential_reads": 0, "qc_attempts": 0, "outcome_looks": 0,
        "backtest_result_exists": False}
    _publish_json(directory, "started.json", start)
    _publish_json(directory, "completed.json", end)
    guards = []
    monkeypatch.setattr(build, "_guard", lambda *args: guards.append(args))
    monkeypatch.setattr(build, "_git", lambda *args: str(build.OUTPUT))
    monkeypatch.setattr(build, "_code_identity", lambda *args: "d" * 64)
    clocks = iter([STARTED, COMPLETED, "2026-10-12T06:32:00Z"])
    monkeypatch.setattr(build, "_utc_now", lambda: next(clocks))
    return directory, captures, segmented, guards


def replace(path, value):
    path.write_bytes((canonical_json(value) + "\n").encode())


def test_actual_codec_shape_reloads_and_builds_one_private_native_index(tmp_path, source):
    directory, captures, segmented, guards = source
    before = {item.name: item.read_bytes() for item in directory.iterdir()}
    result = build._build(tmp_path, head=HEAD, remote=REMOTE)
    output = tmp_path / build.OUTPUT
    saved = json.loads((output / "native.index.private.json").read_bytes())
    observations = json.loads((output / "observations.private.json").read_bytes())
    completed = json.loads((output / "completed.json").read_bytes())
    started = json.loads((output / "started.json").read_bytes())
    assert result["status"] == "native_master_offline_complete"
    assert saved["source_report_sha256"] == segmented.index.report_payload_sha256
    assert saved["source_capture_identity_sha256"] == segmented.index.capture_identity_sha256
    assert completed["native_index_sha256"] == saved["index_sha256"] == result["native_index_sha256"]
    assert completed["native_index_bytes_sha256"] == hash_bytes((output / "native.index.private.json").read_bytes())
    assert completed["source_index_bytes_sha256"] == hash_bytes(segmented.index.to_bytes())
    assert observations["native_index_sha256"] == saved["index_sha256"]
    assert completed["native_observation_binding_sha256"] == observations["binding_sha256"]
    assert completed["native_observation_bytes_sha256"] == hash_bytes((output / "observations.private.json").read_bytes())
    assert completed["native_observation_source_pins"]["source_protocol_sha256"] == build.observations.COMPANION_PROTOCOL_SHA256
    stock = next(row for row in observations["observations"] if row["table"] == "stocks")
    assert stock["source_observation"]["normalized"]["raw_volume"] == {"numerator": 21, "denominator": 2}
    assert all(row["same_share_class_denominator"] is None for row in observations["observations"])
    assert started["source_archive_pins"] == build._archives(captures)
    assert started["source_index_sha256"] == segmented.index.to_payload()["index_sha256"]
    assert {item.name for item in output.iterdir()} == {
        "started.json", "completed.json", "native.index.private.json", "observations.private.json"}
    assert all(item.stat().st_mode & 0o777 == 0o600 for item in output.iterdir())
    assert output.stat().st_mode & 0o777 == 0o700
    assert {item.name: item.read_bytes() for item in directory.iterdir()} == before
    assert guards == [(tmp_path, HEAD, REMOTE)] * 6
    assert all(result[key] == 0 for key in ("provider_requests", "credential_reads", "outcome_looks", "qc_attempts"))
    assert result["backtest_result_exists"] is False
    assert "rows" not in result and "source_archive_pins" not in result
    assert all(not saved["authority"][key] for key in (
        "source_admitted", "point_in_time_data", "historical_raw_ticker_alias_admitted", "denominator_admitted",
        "ready_for_empirical_backtest", "outcome_access_authorized", "qc_authorized", "trading_authority"))


@pytest.mark.parametrize("change", ["pin", "bytes", "missing_part", "extra", "permission", "symlink"])
def test_stored_source_integrity_or_protection_refuses_before_any_new_output(tmp_path, source, monkeypatch, change):
    directory, _, _, _ = source
    part = directory / "part-001.private"
    if change == "pin":
        monkeypatch.setattr(build, "SOURCE_INDEX_SHA256", "e" * 64)
    elif change == "bytes":
        part.write_bytes(part.read_bytes() + b" ")
    elif change == "missing_part":
        part.unlink()
    elif change == "extra":
        _publish_json(directory, "refused.json", {"fixture": True})
    elif change == "permission":
        part.chmod(0o644)
    else:
        moved = tmp_path / "fixture-part"
        part.rename(moved)
        part.symlink_to(moved)
    with pytest.raises(build.CaptureRefusal):
        build._build(tmp_path, head=HEAD, remote=REMOTE)
    assert not (tmp_path / build.OUTPUT).exists()


@pytest.mark.parametrize("file,field,value", [
    ("started.json", "code_head", "e" * 40),
    ("started.json", "source_inventory_sha256", "e" * 64),
    ("started.json", "source_reconstruction_anchor", "2026-10-12T06:01:40Z"),
    ("started.json", "started_at", "2026-10-12T06:01:38Z"),
    ("started.json", "started_at", "2026-10-12T07:00:00Z"),
    ("started.json", "credential_reads", False),
    ("completed.json", "code_head", "e" * 40),
    ("completed.json", "private_index_sha256", "e" * 64),
    ("completed.json", "completed_at", "2026-10-12T06:27:48Z"),
    ("completed.json", "backtest_result_exists", 0),
    ("completed.json", "outcome_looks", False),
    ("completed.json", "qc_attempts", 1),
])
def test_old_completion_and_clocks_must_bind_exact_committed_reconstruction(tmp_path, source, file, field, value):
    directory, _, _, _ = source
    path = directory / file
    record = json.loads(path.read_bytes())
    record[field] = value
    replace(path, record)
    with pytest.raises(build.CaptureRefusal):
        build._build(tmp_path, head=HEAD, remote=REMOTE)
    assert not (tmp_path / build.OUTPUT).exists()


def test_source_provenance_has_old_finalizer_code_and_observed_refusal_anchor(tmp_path, source, monkeypatch):
    monkeypatch.setattr(build.finalizer, "_code_identity", lambda *args: "e" * 64)
    with pytest.raises(build.CaptureRefusal, match="provenance"):
        build._build(tmp_path, head=HEAD, remote=REMOTE)
    assert not (tmp_path / build.OUTPUT).exists()


def test_parts_read_once_at_codec_bound_without_whole_report_decode(tmp_path, source, monkeypatch):
    directory, _, _, _ = source
    original, reads = build._protected_bytes, []
    def protected(path, maximum):
        reads.append((path, maximum))
        return original(path, maximum)
    monkeypatch.setattr(build, "_protected_bytes", protected)
    monkeypatch.setattr(build.segments, "decode_report", lambda *args, **kwargs: pytest.fail("whole report decode"))
    index, digest = build._source_index(tmp_path, ANCHOR)
    assert digest == hash_bytes((directory / "index.private.json").read_bytes())
    assert [(path.name, maximum) for path, maximum in reads if path.suffix == ".private"] == [
        ("part-001.private", build.segments.MAXIMUM_PART_BYTES)]
    assert index.report_payload_sha256


def test_aggregate_digest_refusal_even_when_part_and_typed_index_seals_match(tmp_path, source, monkeypatch):
    directory, _, segmented, _ = source
    old = segmented.index
    changed = build.segments.MasterReportIndex(old.provenance, old.report_byte_length, "e" * 64,
        old.report_payload_sha256, old.capture_identity_sha256, old.parts)
    (directory / "index.private.json").write_bytes(changed.to_bytes())
    monkeypatch.setattr(build, "SOURCE_INDEX_SHA256", changed.to_payload()["index_sha256"])
    end = json.loads((directory / "completed.json").read_bytes())
    end["private_index_sha256"] = build.SOURCE_INDEX_SHA256
    replace(directory / "completed.json", end)
    with pytest.raises(build.CaptureRefusal, match="source_report_bytes_identity"):
        build._build(tmp_path, head=HEAD, remote=REMOTE)
    assert not (tmp_path / build.OUTPUT).exists()


@pytest.mark.parametrize("field", ["report_payload_sha256", "capture_identity_sha256"])
def test_rebuilt_native_index_must_match_stored_typed_report_binding(tmp_path, source, field):
    _, captures, segmented, _ = source
    old = segmented.index
    changed = build.segments.MasterReportIndex(old.provenance, old.report_byte_length,
        old.report_bytes_sha256, "e" * 64 if field == "report_payload_sha256" else old.report_payload_sha256,
        "e" * 64 if field == "capture_identity_sha256" else old.capture_identity_sha256, old.parts)
    with pytest.raises(build.CaptureRefusal, match="native_reconstruction_binding"):
        build._native_bytes(captures, ANCHOR, changed)


def test_native_output_size_bound_refuses_without_partial_large_private_file(tmp_path, source, monkeypatch):
    monkeypatch.setattr(build, "MAXIMUM_NATIVE_INDEX_BYTES", 1)
    with pytest.raises(build.CaptureRefusal, match="native_owned_output_refused"):
        build._build(tmp_path, head=HEAD, remote=REMOTE)
    output = tmp_path / build.OUTPUT
    assert (output / "started.json").exists() and (output / "refused.json").exists()
    assert not (output / "completed.json").exists() and not (output / "native.index.private.json").exists()


@pytest.mark.parametrize("field", ["native_index_sha256", "protocol_sha256", "source_protocol_sha256",
                                   "source_report_sha256", "source_capture_identity_sha256", "binding_sha256"])
def test_observation_source_protocol_index_and_seal_bindings_refuse_changed_payload(tmp_path, source, monkeypatch, field):
    original = build.observations.SharadarNativeObservations.to_payload
    def changed(self):
        payload = original(self)
        payload[field] = "e" * 64
        return payload
    monkeypatch.setattr(build.observations.SharadarNativeObservations, "to_payload", changed)
    with pytest.raises(build.CaptureRefusal):
        build._build(tmp_path, head=HEAD, remote=REMOTE)
    output = tmp_path / build.OUTPUT
    assert (output / "refused.json").exists() and not (output / "observations.private.json").exists()
    assert not (output / "completed.json").exists()


def test_every_retained_native_resolution_uses_the_same_sealed_master_index(tmp_path, source, monkeypatch):
    original = build.observations.SharadarNativeObservations.to_payload
    def changed(self):
        payload = original(self)
        row = next(item for item in payload["observations"] if item["native_resolution"] is not None)
        row["native_resolution"]["index_sha256"] = "e" * 64
        payload["binding_sha256"] = hash_payload({key: value for key, value in payload.items() if key != "binding_sha256"})
        return payload
    monkeypatch.setattr(build.observations.SharadarNativeObservations, "to_payload", changed)
    with pytest.raises(build.CaptureRefusal):
        build._build(tmp_path, head=HEAD, remote=REMOTE)
    assert not (tmp_path / build.OUTPUT / "observations.private.json").exists()


def test_observation_type_and_size_bounds_cannot_be_bypassed_by_adapter(tmp_path, source, monkeypatch):
    monkeypatch.setattr(build, "MAXIMUM_OBSERVATION_BYTES", 1)
    with pytest.raises(build.CaptureRefusal):
        build._build(tmp_path, head=HEAD, remote=REMOTE)
    output = tmp_path / build.OUTPUT
    assert (output / "refused.json").exists() and not (output / "observations.private.json").exists()
    assert not (output / "completed.json").exists()


def test_wrong_companion_binding_type_refuses_without_invoking_duck_typed_methods(tmp_path, source, monkeypatch):
    class WrongBinding:
        def to_payload(self):
            pytest.fail("must not invoke non-contract binding")
    monkeypatch.setattr(build.observations, "bind_sharadar_native_observations", lambda *args: WrongBinding())
    with pytest.raises(build.CaptureRefusal):
        build._build(tmp_path, head=HEAD, remote=REMOTE)
    assert not (tmp_path / build.OUTPUT / "observations.private.json").exists()


def test_old_companion_reload_failure_does_not_create_or_mutate_other_output(tmp_path, source, monkeypatch):
    directory, _, _, _ = source
    before = {item.name: item.read_bytes() for item in directory.iterdir()}
    monkeypatch.setattr(build.companion_reader, "_rebuild_sharadar",
                        lambda *args: (_ for _ in ()).throw(build.CaptureRefusal("source_changed")))
    with pytest.raises(build.CaptureRefusal):
        build._build(tmp_path, head=HEAD, remote=REMOTE)
    assert not (tmp_path / build.OUTPUT).exists()
    assert {item.name: item.read_bytes() for item in directory.iterdir()} == before


def test_noncanonical_master_archive_inventory_refuses_without_attribute_error():
    for captures in ([object()], (object(),), (), None):
        with pytest.raises(build.CaptureRefusal, match="source_archive_inventory"):
            build._archives(captures)


@pytest.mark.parametrize("early_guard_failure", [False, True])
def test_rerun_or_early_guard_cannot_append_refusal_to_prior_output(tmp_path, source, monkeypatch, early_guard_failure):
    output = _prepare_capture_directory(tmp_path / build.OUTPUT)
    _publish_json(output, "started.json", {"fixture_old": True})
    _publish_json(output, "completed.json", {"fixture_complete": True})
    before = {item.name: item.read_bytes() for item in output.iterdir()}
    if early_guard_failure:
        monkeypatch.setattr(build, "_guard", lambda *args: (_ for _ in ()).throw(build.CaptureRefusal("changed")))
    monkeypatch.chdir(tmp_path)
    assert build.main(["--expected-head", HEAD, "--expected-remote", REMOTE]) == 2
    assert {item.name: item.read_bytes() for item in output.iterdir()} == before


@pytest.mark.parametrize("position", [1, 2, 3, 4, 5, 6])
def test_every_create_and_success_publication_rechecks_exact_head_and_remote(tmp_path, source, monkeypatch, position):
    calls = []
    def guard(root, head, remote):
        calls.append((root, head, remote))
        if len(calls) == position:
            raise build.CaptureRefusal("guard_changed")
    monkeypatch.setattr(build, "_guard", guard)
    with pytest.raises(build.CaptureRefusal):
        build._build(tmp_path, head=HEAD, remote=REMOTE)
    assert calls[-1] == (tmp_path, HEAD, REMOTE)
    output = tmp_path / build.OUTPUT
    assert not (output / "completed.json").exists()
    if position <= 2:
        assert not output.exists()
    else:
        assert (output / "refused.json").exists()


@pytest.mark.parametrize("clock", ["2026-10-12T06:27:48Z", "2026-10-12T06:29:00Z"])
def test_start_and_completion_chronology_refuse_without_false_success(tmp_path, source, monkeypatch, clock):
    clocks = iter([clock, COMPLETED, "2026-10-12T06:32:00Z"] if clock < build.SOURCE_COMPLETED_AT else
                  [STARTED, clock, "2026-10-12T06:32:00Z"])
    monkeypatch.setattr(build, "_utc_now", lambda: next(clocks))
    with pytest.raises(build.CaptureRefusal):
        build._build(tmp_path, head=HEAD, remote=REMOTE)
    assert not (tmp_path / build.OUTPUT / "completed.json").exists()


def test_nonignored_destination_never_creates_private_output(tmp_path, source, monkeypatch):
    monkeypatch.setattr(build, "_git", lambda *args: "")
    with pytest.raises(build.CaptureRefusal, match="not_ignored"):
        build._build(tmp_path, head=HEAD, remote=REMOTE)
    assert not (tmp_path / build.OUTPUT).exists()


def test_cli_only_emits_generic_status_code_clocks_and_hashes(tmp_path, source, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert build.main(["--expected-head", HEAD, "--expected-remote", REMOTE]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "native_master_offline_complete"
    assert "FAKE" not in canonical_json(payload) and "rows" not in payload and "source_archive_pins" not in payload
    assert not hasattr(build, "_read_key") and not hasattr(build, "_http")


def test_cli_external_error_text_never_becomes_public_diagnostic(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(build, "_build", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("private-fixture")))
    assert build.main(["--expected-head", HEAD, "--expected-remote", REMOTE]) == 2
    payload = capsys.readouterr().out
    assert "private-fixture" not in payload and json.loads(payload)["credential_reads"] == 0
