"""Explicit fabricated volume/kernel/code seams; never create or mount an image."""
from contextlib import contextmanager
from pathlib import Path

import pytest

from data.hashing import hash_bytes, hash_payload
pytest.importorskip("resource", reason="original protected runtime imports POSIX resource; SI-CR18-001")
pytest.importorskip("fcntl", reason="original immutable runtime imports POSIX fcntl; SI-CR18-001")
from scripts import diagnose_short_interest_isolated_immutable_metadata as proof
from test_short_interest_immutable_metadata import kernel
from test_short_interest_immutable_metadata_diagnostic import Harness, deny_external


class Volume:
    def __init__(self, h):
        self.h, self.phase, self.events = h, "LIVE", []
        self.mountpoint = h.root / "proof-parent" / "isolated-volume"
        self.mountpoint.mkdir(mode=0o700)
        self.after = lambda: None

    def check(self):
        self.events.append("check")
        assert self.phase == "LIVE"

    def check_after_close(self):
        self.events.append("after_close")
        assert self.phase == "CLOSED"
        self.after()

    def closed_summary(self):
        self.check_after_close()
        return {"status": "fabricated_original_volume_closed", "source_admitted": False}


@pytest.fixture
def h(monkeypatch, tmp_path, kernel):
    value = Harness(monkeypatch, tmp_path)
    value.volume, value.volume_entries, value.volume_close_hook = None, [], lambda: None
    value.volume_close_error = False
    monkeypatch.setattr(proof, "__file__", str(tmp_path / proof.DRIVER))
    for name in (proof.DRIVER, proof.STORAGE, proof.WRAPPER):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
        path.chmod(0o600)
        value.mapping[name] = hash_bytes(name.encode())
    monkeypatch.setattr(proof.base, "OUTPUT", Path("proof-parent/isolated-volume/proof"))
    @contextmanager
    def prepared(root, *, boundary):
        assert root == value.root and value.volume is None
        value.volume_entries.append(1)
        boundary(); value.volume = Volume(value)
        yield value.volume
        value.volume.check(); value.volume_close_hook()
        if value.volume_close_error: raise RuntimeError("fabricated original volume close failure")
        value.volume.phase = "CLOSED"
    monkeypatch.setattr(proof.storage, "prepare_registered_volume", prepared)
    monkeypatch.setattr(proof, "PROTOCOL_SHA256", hash_payload(proof.protocol()))
    value.run = lambda: proof.run_registered(value.root, runtime_head="c" * 40,
        actual_remote="b" * 40, complete_code_manifest=value.mapping)
    return value


def test_complete_original_composition_closes_before_false_authority_result(h, kernel):
    result = h.run()
    assert result["status"] == "closed_offline_isolated_new_inode_only"
    assert result["original_code_and_metadata_contexts_closed"] is True
    assert result["isolated_storage_closed_summary_sha256"] == hash_payload(h.volume.closed_summary())
    assert h.volume.phase == "CLOSED" and h.volume.events.count("after_close") >= 3
    assert h.metadata.closed_summary()["seal_stamp_sha256"] == result["seal_stamp_sha256"]
    assert len(kernel[1]) == len(h.volume_entries) == 1
    assert h.path.read_bytes() == proof.base.previous.metadata_bytes()
    assert result["authority"]["persistent_storage_qualified"] is False
    assert result["authority"]["maximum_body_custody_proved"] is False
    assert result["authority"]["ready_for_backtest"] is False
    assert result["authority"]["provider_HTTP"] == result["authority"]["source_STARTs"] == 0
    assert result["native_transition"]["diagnostic"]["observer_complete"] is True


def test_unchanged_original_observer_catalogue_is_accepted_and_tracks_lost_flag(h, kernel, monkeypatch):
    prior = proof.base._challenge
    def remove_flag(fd, owned):
        value = prior(fd, owned)
        info = h.path.stat()
        kernel[0][(info.st_dev, info.st_ino)] = 0
        return value
    monkeypatch.setattr(proof.base, "_challenge", remove_flag)
    with pytest.raises(proof.base.immutable.ImmutableMetadataRefusal, match="flags_changed"):
        h.run()
    result = proof.failure_summary(proof.base.immutable.ImmutableMetadataRefusal("immutable_flags_changed"))
    assert result["native_transition"]["diagnostic"]["classification"] == "required_flags_observed_then_lost"
    assert len(kernel[1]) == 1


def test_volume_context_close_failure_vetoes_completed_metadata(h):
    h.volume_close_error = True
    with pytest.raises(RuntimeError, match="volume close failure"): h.run()
    assert h.metadata.closed_summary()["phase"] == "CLOSED"


def test_volume_postclose_failure_vetoes_result(h):
    def hook():
        def refuse(): raise proof.storage.IsolatedVolumeRefusal("isolated_mount_filesystem_refused")
        h.volume.after = refuse
    h.volume_close_hook = hook
    with pytest.raises(proof.storage.IsolatedVolumeRefusal, match="mount_filesystem"): h.run()


@pytest.mark.parametrize("kind", ["metadata", "code"])
def test_after_volume_context_exit_original_seal_and_final_code_are_still_checked(h, kind):
    def late_change():
        if kind == "metadata": h.path.chmod(0o600)
        else: (h.root / proof.STORAGE).write_bytes(b"fabricated code mutation after native context close")
    h.volume_close_hook = late_change
    with pytest.raises((proof.IsolatedProofRefusal, proof.base.ImmutableProofRefusal,
            proof.base.immutable.creator.cache.contract.AnchorCacheRefusal)):
        h.run()


@pytest.mark.parametrize("clock", [float("nan"), float("inf"), -1, 421])
def test_changed_clock_cannot_bypass_checked_hold_or_deadline(h, monkeypatch, clock):
    def challenge(*args):
        h.tick = clock if clock != 421 else h.tick + clock
        return []
    monkeypatch.setattr(proof.base, "_challenge", challenge)
    with pytest.raises(proof.IsolatedProofRefusal, match="deadline"): h.run()


def test_unregistered_policy_stops_before_volume_or_file(h, monkeypatch):
    monkeypatch.setattr(proof, "PROTOCOL_SHA256", "PENDING")
    with pytest.raises(proof.IsolatedProofRefusal, match="registration_changed"): h.run()
    assert h.volume is None and h.volume_entries == []


def test_missing_code_manifest_stops_before_volume(h):
    del h.mapping[proof.STORAGE]
    with pytest.raises(proof.IsolatedProofRefusal, match="manifest_changed"): h.run()
    assert h.volume is None


def test_native_challenge_is_not_substituted_with_synthetic_success(h, monkeypatch):
    from test_short_interest_immutable_metadata_diagnostic import REAL_CHALLENGE
    monkeypatch.setattr(proof.base, "_challenge", REAL_CHALLENGE)
    with pytest.raises(proof.base.ImmutableProofRefusal, match="challenge_not_denied"): h.run()
    assert proof.failure_summary(proof.base.ImmutableProofRefusal(
        "REFUSED: immutable_proof_challenge_not_denied"))["contract_code"] == "immutable_proof_challenge_not_denied"


def test_policy_stays_synthetic_only_with_no_retry_or_old_evidence():
    value = proof.protocol()
    assert len(proof.code_paths()) == len(set(proof.code_paths())) == 64
    assert value["new_probe_inodes"] == value["native_set_calls"] == 1
    assert value["retries"] == 0 and value["old_evidence_reopened"] is False
    assert value["original_seal_checks_unchanged"] is True
    assert value["minimum_hold_seconds"] == 5 and value["required_errno"] == "EPERM"
