"""Fabricated public composition only: no real source, key, capture or network."""
from contextlib import contextmanager
import errno
import json
import os
from pathlib import Path
import socket

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload

# The runtime under test imports POSIX-only stdlib modules at import time, so
# this module cannot even be collected on the supported Windows host; see the
# lane record SI-CR18-001. Portable contract logic stays covered on POSIX.
pytest.importorskip(
    "resource",
    reason=(
        "the protected-capture runtime imports the POSIX-only module "
        "resource at import time; it cannot execute on this host, see the "
        "lane record SI-CR18-001"
    ),
)

from scripts import diagnose_short_interest_new_metadata_custody as diagnostic
import test_short_interest_count_custody_diagnostic as previous


@pytest.fixture(autouse=True)
def deny_external_seams(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("new metadata diagnostic must never reach external or capture seams")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    for module, name in ((diagnostic.prior, "run_registered"),
        (diagnostic.count, "run_registered"), (diagnostic.count, "capture_chunk"),
        (diagnostic.count.old, "run_registered"), (diagnostic.count.old, "capture_child"),
        (diagnostic.count, "read_named_keychain"), (diagnostic.count.old, "read_named_keychain"),
        (diagnostic.count.transport, "http"), (diagnostic.count.old.original.transport, "_http")):
        monkeypatch.setattr(module, name, denied)


class Clock:
    def __init__(self): self.value = 100.0
    def now(self): return self.value
    def sleep(self, seconds): self.value += seconds


class Harness:
    def __init__(self, monkeypatch, tmp_path, **changes):
        self.events, old_manifest = previous._registered_fixture(monkeypatch, tmp_path, **changes)
        self.root, self.clock, self.capabilities = tmp_path, Clock(), []
        monkeypatch.setattr(diagnostic, "__file__", str(tmp_path / diagnostic.DRIVER))
        monkeypatch.setattr(diagnostic, "OUTPUT", Path(diagnostic.NAMESPACE))
        for name in (diagnostic.HELPER, diagnostic.DRIVER):
            previous.write(tmp_path / name, name.encode())
        self.manifest = {**old_manifest, **{name: hash_bytes(name.encode())
            for name in (diagnostic.HELPER, diagnostic.DRIVER)}}
        monkeypatch.setattr(diagnostic.time, "monotonic", self.clock.now)
        monkeypatch.setattr(diagnostic.prior, "_utc_now", previous.stamp)
        original = diagnostic.creator.prepare_owned_metadata
        self.before_yield = lambda capability: None
        @contextmanager
        def prepare(owned, name, raw, **kwargs):
            with original(owned, name, raw, **kwargs, monotonic=self.clock.now,
                          sleep=self.clock.sleep) as capability:
                self.capabilities.append(capability)
                self.before_yield(capability)
                yield capability
        monkeypatch.setattr(diagnostic.creator, "prepare_owned_metadata", prepare)
        monkeypatch.setattr(diagnostic, "PROTOCOL_SHA256", hash_payload(diagnostic.protocol()))

    @property
    def output(self): return self.root / diagnostic.OUTPUT
    @property
    def metadata(self): return self.output.parent / diagnostic.METADATA_NAME
    def run(self):
        return diagnostic.run_registered(self.root, runtime_head="c" * 40,
            actual_remote="b" * 40, complete_code_manifest=self.manifest)
    def controls(self): return {path.name for path in self.output.iterdir()}


def test_complete_public_composition_real_creator_heldfiles_and_producer_negative_close(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    result = h.run(); value = result.to_payload()
    assert value["status"] == "new_metadata_handshake_closed" and value["failure"] is None
    assert value["context_closure"] == "all_source_and_code_contexts_closed"
    assert value["closed_at"] == value["completed_at"] == previous.stamp()
    assert value["registration"]["code_manifest_sha256"] == hash_payload(h.manifest)
    assert len(value["registration"]["code_files"]) == value["registration"]["code_file_count"] == 58
    assert value["registration"]["historical_sources"]["v3_zero"]["claim_sha256"] == diagnostic.prior.V3_CLAIM_SHA256
    assert value["registration"]["historical_sources"]["v3_zero"]["refusal_sha256"] == diagnostic.prior.V3_REFUSAL_SHA256
    assert value["probes_published"] == value["probes_opened"] == value["probes_read"] == 1
    assert value["metadata_publication_attempts"] == 1
    assert value["original_creation_outcome"] == "accepted_original_creator_capability"
    assert h.controls() == {diagnostic.PROVISIONAL, diagnostic.CLOSED}
    original = (h.output / diagnostic.PROVISIONAL).read_bytes()
    assert value["original_provisional_report_sha256"] == hash_bytes(original)
    provisional = json.loads(original)
    assert provisional["context_closure"] == "provisional_source_and_code_contexts_not_successfully_closed"
    assert provisional["closed_at"] is provisional["original_provisional_report_sha256"] is None
    assert "source_context_exited" in h.events
    assert h.metadata.read_bytes() == diagnostic.metadata_bytes() and len(h.metadata.read_bytes()) == 186
    assert h.capabilities[0].observation()["closed"] is True
    assert value["observations"]["unsealed"]["original_HeldFiles_attempted"] is False
    assert value["observations"]["sealed"]["original_HeldFiles_attempted"] is True
    assert value["observations"]["sealed"]["samples"][-1]["quiet_milliseconds"] >= 1000
    assert result.sha256 == hash_bytes(result.to_bytes())
    assert "registration" not in result.public_summary() and str(tmp_path) not in canonical_json(result.public_summary())
    assert "_raw=" not in repr(result)
    value["authority"]["ready_for_backtest"] = True
    assert result.to_payload()["authority"]["ready_for_backtest"] is False


def test_protocol_fixed_prospective_policy_and_historical_antecedent_scope():
    value = diagnostic.protocol()
    assert value["maximum_samples"] == 16 and value["sample_seconds"] == .25
    assert value["minimum_quiet_seconds"] == 1 and value["maximum_seal_seconds"] == 8
    assert value["maximum_seconds"] == 1800 and value["maximum_metadata_bytes"] == 1024
    assert len(value["code_paths"]) == len(set(value["code_paths"])) == 58
    assert value["decision"] == "SI-DEC-20261025-01"
    antecedent = value["Main_previously_authenticated_antecedent_not_reopened"]
    assert antecedent["current_driver_reauthentication"] is False and antecedent["reopened_or_repaired"] is False
    assert "old_NONCLAIM" in antecedent["scope"] and value["restart_retry_reconstruction_allowed"] is False
    assert value["v3_refusal_sha256"] != antecedent["negative_sha256"]
    authority = value["authority"]
    for key in ("provider_HTTP", "credential_reads", "new_capture_claims", "source_START_debits",
                "source_charged_bytes", "outcome_looks", "qc_attempts"):
        assert authority[key] == 0
    for key in ("is_capture_claim", "source_admitted", "ready_for_backtest", "trading_authority",
                "historical_repair_established"):
        assert authority[key] is False
    assert authority["historical_022_cause"] == authority["historical_ctime_actor"] == "UNKNOWN"


def test_preseal_ctime_change_only_allowed_then_one_original_seal(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    original, constructions = diagnostic.count.old.cache.HeldFiles.__init__, []
    def held_init(held, paths, *args, **kwargs):
        if tuple(paths) == (h.metadata,): constructions.append(1)
        original(held, paths, *args, **kwargs)
    monkeypatch.setattr(diagnostic.count.old.cache.HeldFiles, "__init__", held_init)
    h.before_yield = lambda unused: os.chmod(h.metadata, 0o600)
    result = h.run().to_payload()
    assert result["status"] == "new_metadata_handshake_closed"
    observation = result["observations"]["sealed"]
    assert observation["preseal_ctime_changes"] >= 1
    assert observation["creation_stamp_sha256"] != observation["seal_stamp_sha256"]
    assert observation["original_HeldFiles_attempted"] is True and observation["seal_attempted"] is True
    assert constructions == [1]


def test_original_capability_retained_across_all_source_exits_and_both_final_code_audits(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    original, observations = diagnostic._final_code, []
    def audit(*args):
        assert "source_context_exited" in h.events
        capability = h.capabilities[0]
        assert capability.observation()["closed"] is False
        original_held = capability._state["held"]
        original_identity = original_held._anchor
        capability.check()
        original(*args)
        assert capability._state["held"] is original_held and original_held._anchor is original_identity
        assert os.fstat(capability._anchor[7]).st_size == 186
        observations.append(1)
    monkeypatch.setattr(diagnostic, "_final_code", audit)
    assert h.run().to_payload()["status"] == "new_metadata_handshake_closed"
    assert observations == [1, 1]


@pytest.mark.parametrize("change", ["ctime", "mtime", "mode", "bytes", "inode", "hardlink"])
def test_postseal_any_original_metadata_change_refuses_without_reseal(monkeypatch, tmp_path, change):
    h = Harness(monkeypatch, tmp_path)
    original = diagnostic.creator.NewMetadataCustody.seal_once
    calls = []
    def seal(capability):
        calls.append(1); result = original(capability)
        if change == "ctime": os.chmod(h.metadata, 0o600)
        elif change == "mtime":
            current = h.metadata.stat(); os.utime(h.metadata, ns=(current.st_atime_ns, current.st_mtime_ns + 1))
        elif change == "mode": h.metadata.chmod(0o640)
        elif change == "bytes": h.metadata.write_bytes(b"x" * 186)
        elif change == "inode":
            replacement = h.metadata.with_name("fabricated-replacement")
            previous.write(replacement, diagnostic.metadata_bytes()); os.replace(replacement, h.metadata)
        else: os.link(h.metadata, h.metadata.with_name("fabricated-extra-link"))
        return result
    monkeypatch.setattr(diagnostic.creator.NewMetadataCustody, "seal_once", seal)
    value = h.run().to_payload()
    assert value["status"] == "new_metadata_handshake_refused" and len(calls) == 1
    assert value["failure"]["stage"] == "metadata_original_read"
    assert value["failure"]["contract_code"] in diagnostic.creator._CODES
    assert h.controls() == {diagnostic.REFUSED}
    assert h.capabilities[0].observation()["phase"] == "REFUSED"


@pytest.mark.parametrize("change", ["mtime", "mode", "bytes", "inode"])
def test_preseal_nonctime_change_refuses_and_does_not_construct_heldfiles(monkeypatch, tmp_path, change):
    h = Harness(monkeypatch, tmp_path)
    def mutate(unused):
        if change == "mtime":
            current = h.metadata.stat(); os.utime(h.metadata, ns=(current.st_atime_ns, current.st_mtime_ns + 1))
        elif change == "mode": h.metadata.chmod(0o640)
        elif change == "bytes": h.metadata.write_bytes(b"not original")
        else:
            replacement = h.metadata.with_name("fabricated-replacement")
            previous.write(replacement, diagnostic.metadata_bytes()); os.replace(replacement, h.metadata)
    h.before_yield = mutate
    value = h.run().to_payload()
    assert value["status"] == "new_metadata_handshake_refused"
    assert value["failure"]["stage"] == "metadata_seal_once"
    assert value["observations"]["terminal"]["original_HeldFiles_attempted"] is False
    assert h.controls() == {diagnostic.REFUSED}


def test_source_context_exit_failure_never_switches_callback_or_positive_closes(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path, fail_context_exit=True)
    value = h.run().to_payload()
    assert value["status"] == "new_metadata_handshake_refused"
    assert value["failure"]["stage"] == "source_code_context_exit"
    assert value["failure"]["contract_code"] == "v3_zero_original_control_bytes_changed"
    assert value["context_closure"] == "provisional_source_and_code_contexts_not_successfully_closed"
    assert h.controls() == {diagnostic.PROVISIONAL, diagnostic.REFUSED}
    assert h.capabilities[0].observation()["phase"] == "REFUSED"


@pytest.mark.parametrize("audit_number,member", [(1, "metadata"), (2, "metadata"),
    (1, "provisional"), (2, "provisional"), (2, "closed")])
def test_original_metadata_and_controls_audited_after_each_terminal_code_audit(monkeypatch, tmp_path, audit_number, member):
    h = Harness(monkeypatch, tmp_path)
    original, calls = diagnostic._final_code, []
    def audit(*args):
        original(*args); calls.append(1)
        if len(calls) == audit_number:
            path = h.metadata if member == "metadata" else h.output / (
                diagnostic.PROVISIONAL if member == "provisional" else diagnostic.CLOSED)
            os.chmod(path, 0o600)
    monkeypatch.setattr(diagnostic, "_final_code", audit)
    value = h.run().to_payload()
    assert value["status"] == "new_metadata_handshake_refused"
    assert value["failure"]["stage"] == ("terminal_original_audit" if audit_number == 1
        else "terminal_final_original_audit")
    assert diagnostic.REFUSED in h.controls()
    assert (diagnostic.CLOSED in h.controls()) is (audit_number == 2)


@pytest.mark.parametrize("error,expected", [(OSError(errno.ENOSPC, "SECRET path"), "ENOSPC"),
    (OSError(987654, "SECRET path"), None), (TypeError("SECRET request"), None)])
def test_preoutput_actual_setup_cause_and_allowlisted_errno_are_not_replaced(monkeypatch, tmp_path, error, expected):
    h = Harness(monkeypatch, tmp_path)
    @contextmanager
    def fail(*args, **kwargs):
        raise error
        yield
    monkeypatch.setattr(diagnostic.count.old.cache, "load_registered_cache", fail)
    with pytest.raises(diagnostic._StageFailure) as caught: h.run()
    summary = diagnostic.failure_summary(caught.value)
    assert caught.value._anchor[1] is error
    assert summary["stage"] == "saved_cache_loading" and summary["errno_name"] == expected
    assert summary["contract_code"] is None and "SECRET" not in canonical_json(summary)
    assert not h.output.exists() and not h.metadata.exists()


def test_actual_producer_negative_wrong_schema_fails_before_any_new_metadata(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path, wrong_key=True)
    with pytest.raises(diagnostic._StageFailure) as caught: h.run()
    summary = diagnostic.failure_summary(caught.value)
    assert summary["stage"] == "v3_zero_loading" and summary["contract_code"] == "v3_zero_negative_or_budget_changed"
    assert not h.output.exists() and not h.metadata.exists()


def test_pending_protocol_fails_before_any_source_or_output(monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostic, "PROTOCOL_SHA256", "PENDING")
    with pytest.raises(diagnostic._StageFailure) as caught:
        diagnostic.run_registered(tmp_path, runtime_head="c" * 40, actual_remote="b" * 40, complete_code_manifest={})
    assert diagnostic.failure_summary(caught.value)["contract_code"] == "new_metadata_protocol_pending_or_changed"
    assert diagnostic.failure_summary(caught.value)["stage"] == "protocol_registration"
    assert not tuple(tmp_path.iterdir())


def test_existing_metadata_is_never_reused_repaired_or_unlinked(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    previous.write(h.metadata, b"retained failed old metadata")
    before = h.metadata.read_bytes(), h.metadata.stat()
    with pytest.raises(diagnostic._StageFailure) as caught: h.run()
    assert diagnostic.failure_summary(caught.value)["contract_code"] == "new_metadata_already_exists"
    assert h.metadata.read_bytes() == before[0] and h.metadata.stat() == before[1]
    assert not h.output.exists() and not h.capabilities


@pytest.mark.parametrize("entry", ["dangling_symlink", "directory"])
def test_any_existing_metadata_entry_refuses_nofollow_before_output_creation(monkeypatch, tmp_path, entry):
    h = Harness(monkeypatch, tmp_path)
    if entry == "dangling_symlink": h.metadata.symlink_to(tmp_path / "not-an-existing-file")
    else: h.metadata.mkdir(mode=0o700)
    before = h.metadata.lstat()
    with pytest.raises(diagnostic._StageFailure) as caught: h.run()
    assert diagnostic.failure_summary(caught.value)["contract_code"] == "new_metadata_already_exists"
    assert h.metadata.lstat() == before and not h.output.exists() and not h.capabilities


def test_same_output_cannot_be_restarted_and_old_controls_stay_byte_exact(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    h.run(); before = {path.name: path.read_bytes() for path in h.output.iterdir()}
    with pytest.raises(diagnostic._StageFailure): h.run()
    assert {path.name: path.read_bytes() for path in h.output.iterdir()} == before
    assert len(h.capabilities) == 1


def test_guard_cost_exhausting_eight_second_creation_window_is_terminal(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    original = diagnostic.creator.prepare_owned_metadata
    @contextmanager
    def delayed(*args, **kwargs):
        boundary = kwargs["boundary"]
        def expensive_guard(): boundary(); h.clock.value += 1.0
        kwargs["boundary"] = expensive_guard
        with original(*args, **kwargs) as capability: yield capability
    monkeypatch.setattr(diagnostic.creator, "prepare_owned_metadata", delayed)
    value = h.run().to_payload()
    assert value["status"] == "new_metadata_handshake_refused"
    assert value["failure"]["contract_code"] == "new_metadata_window_exhausted"
    assert diagnostic.CLOSED not in h.controls() and diagnostic.REFUSED in h.controls()
    assert len(h.capabilities) <= 1


def test_postwrite_pre_yield_failure_preserves_metadata_and_unknown_creation_accounting(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    original, changed = os.fsync, []
    def fsync(fd):
        original(fd)
        if not changed and os.fstat(fd).st_size == 186:
            changed.append(1); h.clock.value += 8.01
    monkeypatch.setattr(os, "fsync", fsync)
    value = h.run().to_payload()
    assert changed and value["status"] == "new_metadata_handshake_refused"
    assert value["failure"]["stage"] == "metadata_creation"
    assert value["failure"]["contract_code"] == "new_metadata_window_exhausted"
    assert value["metadata_publication_attempts"] == 1 and value["probes_published"] is None
    assert value["original_creation_outcome"] == "unknown_partial_creation_possible"
    assert not h.capabilities and h.metadata.read_bytes() == diagnostic.metadata_bytes()
    assert h.controls() == {diagnostic.REFUSED}


@pytest.mark.parametrize("change", ["deadline", "backdated_monotonic", "backdated_utc"])
def test_final_deadline_and_clock_regressions_dominate_positive_marker(monkeypatch, tmp_path, change):
    h = Harness(monkeypatch, tmp_path)
    original, calls = diagnostic._final_code, []
    def audit(*args):
        original(*args); calls.append(1)
        if len(calls) == 2:
            if change == "deadline": h.clock.value += 1800
            elif change == "backdated_monotonic": h.clock.value = 0
            else: monkeypatch.setattr(diagnostic.prior, "_utc_now", lambda: previous.stamp(-1))
    monkeypatch.setattr(diagnostic, "_final_code", audit)
    value = h.run().to_payload()
    assert value["status"] == "new_metadata_handshake_refused"
    assert h.controls() == {diagnostic.PROVISIONAL, diagnostic.CLOSED, diagnostic.REFUSED}
    assert value["failure"]["contract_code"] == ("new_metadata_clock_backdated" if change == "backdated_utc"
        else "new_metadata_deadline_exhausted")


def test_metadata_normal_close_failure_after_closed_marker_gets_dominating_negative(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    original = diagnostic.creator.NewMetadataCustody._close
    def close(capability, *, validate):
        if validate: raise OSError(errno.EIO, "SECRET close")
        return original(capability, validate=validate)
    monkeypatch.setattr(diagnostic.creator.NewMetadataCustody, "_close", close)
    value = h.run().to_payload()
    assert value["status"] == "new_metadata_handshake_refused" and value["failure"]["stage"] == "metadata_context_close"
    assert value["failure"]["errno_name"] == "EIO" and "SECRET" not in canonical_json(value)
    assert h.controls() == {diagnostic.PROVISIONAL, diagnostic.CLOSED, diagnostic.REFUSED}


def test_output_close_failure_propagates_non_success_even_with_closed_marker(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    original = diagnostic.prior._OwnedOutput.close
    def close(owned):
        original(owned); raise OSError(errno.EIO, "SECRET output close")
    monkeypatch.setattr(diagnostic.prior._OwnedOutput, "close", close)
    with pytest.raises(diagnostic._StageFailure) as caught: h.run()
    summary = diagnostic.failure_summary(caught.value)
    assert summary["stage"] == "output_close" and summary["errno_name"] == "EIO"
    assert "SECRET" not in canonical_json(summary) and diagnostic.CLOSED in h.controls()


@pytest.mark.parametrize("change", ["metadata", "provisional", "closed", "deadline", "backdated_utc"])
def test_successful_metadata_close_cannot_hide_late_original_change_or_timeout(monkeypatch, tmp_path, change):
    h = Harness(monkeypatch, tmp_path)
    original = diagnostic.creator.NewMetadataCustody._close
    def close(capability, *, validate):
        original(capability, validate=validate)
        if validate:
            if change == "deadline": h.clock.value += 1800
            elif change == "backdated_utc": monkeypatch.setattr(diagnostic.prior, "_utc_now", lambda: previous.stamp(-1))
            else:
                path = h.metadata if change == "metadata" else h.output / (
                    diagnostic.PROVISIONAL if change == "provisional" else diagnostic.CLOSED)
                os.chmod(path, 0o600)
    monkeypatch.setattr(diagnostic.creator.NewMetadataCustody, "_close", close)
    value = h.run().to_payload()
    assert value["status"] == "new_metadata_handshake_refused"
    assert value["failure"]["stage"] == "metadata_closed_final_audit"
    assert value["failure"]["contract_code"] in {
        "new_metadata_closed_original_stamp_changed", "new_metadata_control_original_stamp_changed",
        "new_metadata_deadline_exhausted", "new_metadata_clock_backdated"}
    assert h.controls() == {diagnostic.PROVISIONAL, diagnostic.CLOSED, diagnostic.REFUSED}
    assert h.capabilities[0].observation()["closed"] is True


def test_existing_negative_during_lifecycle_cannot_be_overwritten_or_ignored(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    original = diagnostic._final_code
    retained = b"fabricated dominant existing negative"
    def audit(*args):
        original(*args)
        path = h.output / diagnostic.REFUSED
        if not path.exists(): previous.write(path, retained)
    monkeypatch.setattr(diagnostic, "_final_code", audit)
    with pytest.raises(diagnostic._StageFailure): h.run()
    assert (h.output / diagnostic.REFUSED).read_bytes() == retained
    assert diagnostic.CLOSED not in h.controls()


def test_exceptional_metadata_cleanup_failure_still_closes_original_output(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path, fail_context_exit=True)
    original_close, closed = diagnostic.prior._OwnedOutput.close, []
    def output_close(owned):
        closed.append(1); original_close(owned)
    monkeypatch.setattr(diagnostic.prior._OwnedOutput, "close", output_close)
    original = diagnostic.creator.NewMetadataCustody._close
    def capability_close(capability, *, validate):
        original(capability, validate=validate)
        if not validate: raise OSError(errno.EIO, "SECRET cap cleanup")
    monkeypatch.setattr(diagnostic.creator.NewMetadataCustody, "_close", capability_close)
    with pytest.raises(diagnostic._StageFailure) as caught: h.run()
    summary = diagnostic.failure_summary(caught.value)
    assert summary["stage"] == "metadata_context_close" and summary["errno_name"] == "EIO"
    assert closed == [1] and diagnostic.REFUSED in h.controls()
    assert "SECRET" not in canonical_json(summary)


@pytest.mark.parametrize("error", [ValueError("SECRET path"), diagnostic.NewMetadataDiagnosticRefusal("REFUSED: SECRET"),
    diagnostic.creator.NewMetadataRefusal("REFUSED: SECRET")])
def test_safe_error_projection_never_formats_unknown_details(error):
    summary = diagnostic.failure_summary(error)
    assert summary["contract_code"] is None and summary["held_field_observation"] is None
    assert "SECRET" not in canonical_json(summary)


def test_hostile_error_objects_and_uninitialized_wrapper_are_safe():
    class Hostile:
        def __eq__(self, other): pytest.fail("hostile equality")
        def __str__(self): pytest.fail("hostile formatting")
    class Error(Exception):
        def __getattribute__(self, name): pytest.fail("hostile property")
    class Text(str):
        def __eq__(self, other): pytest.fail("hostile string equality")
    for error in (Error(), diagnostic.NewMetadataDiagnosticRefusal(Hostile()),
                  diagnostic.NewMetadataDiagnosticRefusal(Text("REFUSED: SECRET"))):
        assert diagnostic.failure_summary(error)["contract_code"] is None
    summary = diagnostic.failure_summary(diagnostic._StageFailure.__new__(diagnostic._StageFailure))
    assert summary["stage"] == "unclassified_new_metadata_failure"


@pytest.mark.parametrize("change", ["working", "committed", "earlier_during_later_read", "unbounded_committed"])
def test_final_code_audit_uses_exact58_committed_bytes_and_all_original_stamps(monkeypatch, tmp_path, change):
    h = Harness(monkeypatch, tmp_path)
    entries = [{"path": name, "sha256": h.manifest[name]} for name in diagnostic.code_paths()]
    registration = {"head": "c" * 40, "remote": "b" * 40, "code_files": entries,
        "code_manifest_sha256": hash_payload(h.manifest),
        "code_identity_sha256": hash_payload({"git_commit": "c" * 40, "files": entries})}
    class Guard:
        def check(self): pass
        def refresh(self): pass
        def binding(self): return tmp_path, "c" * 40, "b" * 40
    first, last = diagnostic.code_paths()[0], diagnostic.code_paths()[-1]
    def git(root, arguments, guard):
        name = arguments[1].partition(":")[2]
        if change == "earlier_during_later_read" and name == last: os.chmod(tmp_path / first, 0o600)
        if change == "committed": return b"changed committed bytes"
        if change == "unbounded_committed": return b"x" * (8 * 1024 ** 2 + 1)
        return name.encode()
    monkeypatch.setattr(diagnostic.count.old.cache, "_git", git)
    if change == "working": (tmp_path / first).write_bytes(b"changed working bytes")
    with pytest.raises(diagnostic.NewMetadataDiagnosticRefusal):
        diagnostic._final_code(tmp_path, Guard(), registration)
