"""Toy lifecycle + genuine producer-backed zero proof; never actual closure.

The source fixture is the genuine 49-ticket/48-original/2-child test domain.
Only the explicitly named prior cumulative linkage is replaced for successful
toy lifecycle tests: unchanged v2/v3 controls record the actual-sized prior
13992/23452681. A separate test proves the production linkage rejects that
cross-domain mismatch. No test claims full actual-domain operational closure.
"""
from contextlib import contextmanager
import errno
import json
import os
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import load_short_interest_count_epoch_ledger as loader
import test_short_interest_refused_count_snapshot as snapshots
import test_short_interest_count_custody_diagnostic as previous


@pytest.fixture(autouse=True)
def forbid_external_or_capture_seams(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("offline ledger cannot access capture/key/provider/network")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    for module, name in ((loader.prior, "run_registered"),
        (loader.count, "run_registered"), (loader.count, "capture_chunk"),
        (loader.count.old, "run_registered"), (loader.count.old, "capture_child"),
        (loader.count, "read_named_keychain"), (loader.count.old, "read_named_keychain"),
        (loader.count.transport, "http"), (loader.count.old.original.transport, "_http")):
        monkeypatch.setattr(module, name, denied)


class Harness:
    """Real small source/parent/child/zero proofs and current-code HeldFiles.

    Only the expensive original cache reconstruction and actual Git command
    runner are fabricated. The existing original parent and child replay,
    original external claims, v2 proof and unmodified v3 consumer all run.
    """
    def __init__(self, monkeypatch, tmp_path, *, toy_linkage=True, wrong_v3_key=False):
        self.root, self.events, self.tick = tmp_path, [], 100.0
        self.exit_hook = lambda: None
        parent_loader = loader.snapshot._load_parent_prefix
        source, unused_guard, self.child_directory, child_files, manifest = snapshots._fixture(monkeypatch, tmp_path)
        self.source, self.manifest_raw = source, manifest
        unused, unused_plan, parent_files, parent_claim, self.parent_code, unused_prefix, unused_binding = snapshots.fabricated.small_domain(monkeypatch)
        parent_directory = tmp_path / loader.count.old.PARENT
        parent_directory.mkdir(mode=0o700)
        for name, raw in parent_files.items(): previous.write(parent_directory / name, raw)
        previous.write(parent_directory.parent / ("budget-" + loader.count.old.original.PROTOCOL_SHA256 + ".json"), parent_claim)
        monkeypatch.setattr(loader.snapshot, "_load_parent_prefix", parent_loader)
        monkeypatch.setattr(loader.count, "PREDECESSOR_MANIFEST_SHA256", hash_bytes(manifest))
        monkeypatch.setattr(loader.count, "FIRST_POSITION", 1)
        monkeypatch.setattr(loader.count, "DESCRIPTORS", 2)
        self.queries = loader.count.freeze_queries(source)
        self.binding = loader.count.old.freeze_recovery(source)
        for name in loader.code_paths():
            path = tmp_path / name; path.parent.mkdir(parents=True, exist_ok=True)
            previous.write(path, name.encode())
        monkeypatch.setattr(loader, "__file__", str(tmp_path / loader.DRIVER))
        monkeypatch.setattr(loader.time, "monotonic", lambda: self.tick)
        monkeypatch.setattr(loader.prior, "_utc_now", previous.stamp)
        real_guard_init = loader.lane.LaneGuard.__init__
        def runner(root, args):
            assert root == tmp_path
            if args[1] == "rev-parse": return (str(tmp_path) + "\n").encode()
            if args[1] == "ls-remote":
                self.events.append("matching_remote")
                return ("b" * 40 + "\t" + loader.lane.REF + "\n").encode()
            assert args[1] == "status"
            return ("# branch.oid " + "c" * 40 + "\n# branch.head " + loader.lane.BRANCH + "\n").encode()
        def guard_init(guard, root, *, expected_head, expected_remote, **kwargs):
            real_guard_init(guard, root, expected_head=expected_head, expected_remote=expected_remote,
                runner=runner, physical=lambda unused: None)
        monkeypatch.setattr(loader.lane.LaneGuard, "__init__", guard_init)
        def git(root, args, guard):
            assert root == tmp_path; guard.check()
            if args[0] == "merge-base": return b""
            assert args[0] == "show"
            head, unused, name = args[1].partition(":")
            if head == loader.count.old.PARENT_HEAD: return self.parent_code
            if head == loader.snapshot.SOURCE_HEAD: return b"fabricated committed historical code"
            return name.encode()
        monkeypatch.setattr(loader.count.old.cache, "_git", git)
        self._write_zero_controls(monkeypatch, wrong_v3_key)
        self.source_path = tmp_path / "fabricated-cache-source.private.json"
        previous.write(self.source_path, b'{"fabricated_cache_source":true}')
        @contextmanager
        def saved_cache(root, **kwargs):
            assert root == tmp_path and kwargs == {"runtime_head": "c" * 40, "actual_remote": "b" * 40, "for_counts": True}
            guard = loader.lane.LaneGuard(root, expected_head="c" * 40, expected_remote="b" * 40)
            with loader.count.old.cache.HeldFiles(tuple(root / name for name in loader.count.old.cache.COUNT_CODE_FILES),
                    protected=False, boundary=guard.check) as code, loader.count.old.cache.HeldFiles(
                    (self.source_path,), protected=True, boundary=guard.check) as held:
                def source_custody(): self.events.append("saved_source_audit"); held.check()
                saved = SimpleNamespace(plan=source, _anchor=(source, (held,), code),
                    source_custody=source_custody, code_custody=code.check)
                try: yield saved
                finally:
                    self.events.append("saved_context_exiting"); code.check()
            self.events.append("saved_context_exited")
        monkeypatch.setattr(loader.count.old.cache, "load_registered_cache", saved_cache)
        original_refused = loader.snapshot.load_refused_child
        @contextmanager
        def refused(*args, **kwargs):
            assert kwargs["expected_manifest_sha256"] == hash_bytes(manifest)
            with original_refused(*args, **kwargs) as proof:
                self.refused = proof
                yield proof
                self.events.append("refused_context_exiting"); self.exit_hook()
            self.events.append("refused_context_exited")
        monkeypatch.setattr(loader.snapshot, "load_refused_child", refused)
        # Adapt only the model's prospectively frozen fabricated test profile.
        m, old = loader.model, loader.count.old
        for name, value in {"ORIGINAL_COUNT": 49, "MAXIMUM_CUMULATIVE_STARTS": 50,
            "MAXIMUM_CUMULATIVE_BYTES": old.MAXIMUM_CUMULATIVE_BYTES,
            "PARENT_STARTED": 48, "PARENT_HTTP": 47, "PARENT_RAW": 47,
            "PARENT_CHARGED_BYTES": old.PARENT_CHARGED_BYTES,
            "RECOVERY_STARTED": 2, "RECOVERY_HTTP": 2, "RECOVERY_RAW": 1,
            "RECOVERY_CHARGED_BYTES": loader.snapshot.SOURCE_CHARGED_BYTES,
            "FAILED_PARENT_POSITION": 47, "ANCHOR_PLAN_SHA256": source.sha256}.items():
            monkeypatch.setattr(m, name, value)
        pins = (
            (("full_manifest", old.PARENT_MANIFEST_SHA256), ("external_claim", old.PARENT_CLAIM_SHA256),
                ("protocol", old.original.PROTOCOL_SHA256), ("historical_code", old.PARENT_CODE_SHA256)),
            (("full_manifest", hash_bytes(manifest)), ("external_claim", loader.snapshot.SOURCE_CLAIM_SHA256),
                ("terminal_refusal", loader.snapshot.SOURCE_REFUSAL_SHA256), ("protocol", old.PROTOCOL_SHA256),
                ("historical_code", loader.snapshot.SOURCE_CODE_SHA256)),
            (("external_claim", loader.snapshot.ZERO_CLAIM_SHA256), ("terminal_refusal", loader.snapshot.ZERO_REFUSAL_SHA256),
                ("protocol", loader.snapshot.ZERO_PROTOCOL), ("historical_code_manifest", loader.snapshot.ZERO_CODE_MANIFEST_SHA256)),
            (("external_claim", loader.prior.V3_CLAIM_SHA256), ("terminal_refusal", loader.prior.V3_REFUSAL_SHA256),
                ("protocol", loader.count.PROTOCOL_SHA256), ("historical_code", None)))
        monkeypatch.setattr(m, "_PROOF_PINS", pins)
        if toy_linkage:
            monkeypatch.setattr(loader, "_require_prior_cumulative", lambda *args: self.events.append("EXPLICIT_toy_prior_cumulative_linkage_seam"))
        monkeypatch.setattr(loader, "PROTOCOL_SHA256", hash_payload(loader.protocol()))
        self.code_manifest = {name: hash_bytes(name.encode()) for name in loader.code_paths()}

    def _write_zero_controls(self, monkeypatch, wrong_v3_key):
        s, old = loader.snapshot, loader.count.old
        names = tuple(sorted(set((*old.expected_code_paths(),
            "scripts/capture_short_interest_bounded_count_chunk.py", "scripts/short_interest_recovery_transport.py",
            "scripts/short_interest_refused_count_snapshot.py"))))
        entries = [{"path": name, "sha256": hash_bytes(name.encode())} for name in names]
        monkeypatch.setattr(s, "ZERO_CODE_MANIFEST_SHA256", hash_payload({row["path"]: row["sha256"] for row in entries}))
        claim = {"schema": "si-bounded-count-spent-claim-v2", "protocol_sha256": s.ZERO_PROTOCOL,
            "query_plan_sha256": self.queries.sha256, "restart_allowed": False, "started_at": previous.stamp(),
            "maximum_attempts": 528, "maximum_extra_attempts": 16, "prior_STARTs": 13992,
            "prior_charged_bytes": 23452681, "maximum_cumulative_bytes": 4 * 1024 ** 3,
            "registration": {"head": s.ZERO_HEAD, "remote": s.ZERO_REMOTE,
                "code_identity_sha256": hash_payload({"git_commit": s.ZERO_HEAD, "files": entries})}}
        raw = canonical_json(claim).encode(); monkeypatch.setattr(s, "ZERO_CLAIM_SHA256", hash_bytes(raw))
        negative = {"schema": "si-bounded-count-refused-v2", "protocol_sha256": s.ZERO_PROTOCOL,
            "code": "key_or_initial_publication_refused_after_claim", "START_debits": 0,
            "known_HTTP_invocations": 0, "charged_bytes": 0, "resolved_descriptors": 0,
            "HTTP_count_exact": True, "cumulative_STARTs": 13992, "cumulative_charged_bytes": 23452681,
            "started_at": previous.stamp(), "refused_at": previous.stamp(1), "new_claim_sha256": hash_bytes(raw),
            "unreceipted_attempts": [], "receipt_not_persisted_attempts": [],
            "unpublished_observed_diagnostics": [], "authority": loader.count.authority()}
        refused = canonical_json(negative).encode(); monkeypatch.setattr(s, "ZERO_REFUSAL_SHA256", hash_bytes(refused))
        directory = self.root / s.ZERO_DIRECTORY; directory.mkdir(mode=0o700)
        previous.write(directory.parent / s.ZERO_CLAIM, raw); previous.write(directory / "run.refused.json", refused)
        entries = [{"path": name, "sha256": hash_bytes(name.encode())} for name in loader.count.code_paths()]
        claim = {"schema": "si-bounded-count-spent-claim-v3", "protocol_sha256": loader.count.PROTOCOL_SHA256,
            "registration": {"head": loader.prior.V3_HEAD, "remote": loader.prior.V3_REMOTE,
                "code_identity_sha256": hash_payload({"git_commit": loader.prior.V3_HEAD, "files": entries})},
            "started_at": previous.stamp(), "query_plan_sha256": self.queries.sha256,
            "predecessor_manifest_sha256": loader.count.PREDECESSOR_MANIFEST_SHA256,
            "maximum_attempts": 528, "maximum_extra_attempts": 16, "prior_STARTs": 13992,
            "prior_charged_bytes": 23452681, "maximum_cumulative_bytes": 4 * 1024 ** 3, "restart_allowed": False}
        raw = canonical_json(claim).encode(); monkeypatch.setattr(loader.prior, "V3_CLAIM_SHA256", hash_bytes(raw))
        negative = previous._producer_negative(previous.stamp(), hash_bytes(raw))
        if wrong_v3_key: negative["failure_detail"] = negative.pop("fixed_diagnostic")
        refused = canonical_json(negative).encode(); monkeypatch.setattr(loader.prior, "V3_REFUSAL_SHA256", hash_bytes(refused))
        directory = self.root / loader.count.OUTPUT; directory.mkdir(mode=0o700)
        previous.write(directory.parent / loader.count.CLAIM, raw); previous.write(directory / "run.refused.json", refused)

    def load(self):
        return loader.load_registered_count_epoch_ledger(self.root, runtime_head="c" * 40,
            actual_remote="b" * 40, complete_code_manifest=self.code_manifest)


def test_toy_original_source_held_ledger_then_separate_closed_witness(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    before = set(tmp_path.rglob("*"))
    with h.load() as context:
        value, summary = context.private_payload(), context.public_summary()
        assert type(context) is loader.RegisteredCountEpochLedger
        assert value["registration"]["code_file_count"] == len(value["registration"]["code_files"]) == 58
        assert context.sha256 == hash_bytes(canonical_json(value).encode())
        assert summary["START_debits"] == 50 and summary["known_HTTP_invocations"] == 49
        assert summary["retained_transport_observation_positions"] == 48
        assert summary["missing_transport_observation_positions"] == 1
        assert summary["minimum_additional_START_allowance_lower_bound"] == 1
        assert summary["custody_status"] == "source_held_provisional" and summary["authority"]["source_admitted"] is False
        assert "registration" not in summary and str(tmp_path) not in canonical_json(summary)
    closed = context.closed_summary()
    assert closed["status"] == "closed_offline_source_only_slice" and closed["authority"]["ready_for_backtest"] is False
    assert closed["provisional_ledger_sha256"] == hash_bytes(canonical_json(value).encode())
    assert "EXPLICIT_toy_prior_cumulative_linkage_seam" in h.events
    assert "saved_context_exited" in h.events and set(tmp_path.rglob("*")) == before
    assert context.closure_receipt() == closed
    with pytest.raises(loader.CountEpochLoaderRefusal, match="source_not_live"): context.private_payload()


def test_production_prior_linkage_rejects_toy_totals_against_genuine_actual_sized_controls(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path, toy_linkage=False)
    with pytest.raises(loader._StageFailure) as caught:
        with h.load(): pytest.fail("actual-sized prior controls cannot close a toy ledger")
    assert loader.failure_summary(caught.value)["contract_code"] == "epoch_loader_prior_cumulative_changed"
    assert "EXPLICIT_toy_prior_cumulative_linkage_seam" not in h.events


def test_genuine_producer_backed_v3_schema_regression_refuses_before_model(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path, wrong_v3_key=True)
    with pytest.raises(loader._StageFailure) as caught:
        with h.load(): pytest.fail("wrong old producer schema cannot yield")
    assert loader.failure_summary(caught.value)["contract_code"] == "v3_zero_negative_or_budget_changed"
    assert "EXPLICIT_toy_prior_cumulative_linkage_seam" not in h.events


@pytest.mark.parametrize("epoch", ["v2", "v3"])
def test_positive_sibling_never_promotes_negative_epoch(monkeypatch, tmp_path, epoch):
    h = Harness(monkeypatch, tmp_path)
    directory = tmp_path / (loader.snapshot.ZERO_DIRECTORY if epoch == "v2" else loader.count.OUTPUT)
    previous.write(directory / "chunk.closed.json", b'{}')
    with pytest.raises(loader._StageFailure):
        with h.load(): pytest.fail("positive sibling must dominate to refusal")


@pytest.mark.parametrize("entry", ["child_raw", "external_claim", "v3_negative", "working_code"])
def test_live_original_mutation_and_exit_checks_prevent_any_closed_witness(monkeypatch, tmp_path, entry):
    h = Harness(monkeypatch, tmp_path)
    context = None
    with pytest.raises(loader._StageFailure):
        with h.load() as context:
            path = {"child_raw": h.child_directory / "query-00000001.raw",
                "external_claim": h.child_directory.parent / loader.count.old.CLAIM_NAME,
                "v3_negative": tmp_path / loader.count.OUTPUT / "run.refused.json",
                "working_code": tmp_path / loader.MODEL}[entry]
            os.chmod(path, 0o640)
    assert context is not None
    with pytest.raises(loader.CountEpochLoaderRefusal, match="latched_failure"): context.closed_summary()


def test_consumer_exception_still_finally_audits_and_permanently_refuses_closure(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    with pytest.raises(loader._StageFailure) as caught:
        with h.load() as context: raise ValueError("SECRET body failure")
    summary = loader.failure_summary(caught.value)
    assert summary["stage"] == "consumer_body" and "SECRET" not in canonical_json(summary)
    assert "saved_context_exiting" in h.events and "saved_source_audit" in h.events
    with pytest.raises(loader.CountEpochLoaderRefusal): context.closed_summary()


def test_late_source_exit_failure_after_provisional_payload_has_no_closed_witness(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    def failure(): raise OSError(errno.EIO, "SECRET source exit")
    h.exit_hook = failure
    with pytest.raises(loader._StageFailure) as caught:
        with h.load() as context: assert context.public_summary()["START_debits"] == 50
    assert loader.failure_summary(caught.value)["errno_name"] == "EIO"
    with pytest.raises(loader.CountEpochLoaderRefusal): context.closed_summary()


def test_last_saved_source_audit_detects_mutation_during_earlier_context_exit(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    h.exit_hook = lambda: os.chmod(h.source_path, 0o640)
    with pytest.raises(loader._StageFailure) as caught:
        with h.load() as context: assert context.private_payload()["status"] == "source_held_provisional"
    assert loader.failure_summary(caught.value)["contract_code"] in {"held_custody_file_changed", "held_source_file_protection"}
    with pytest.raises(loader.CountEpochLoaderRefusal): context.closed_summary()


@pytest.mark.parametrize("change", ["working", "committed", "deadline", "clock"])
def test_after_all_contexts_final_audit_or_clock_failure_prevents_closed_summary(monkeypatch, tmp_path, change):
    h = Harness(monkeypatch, tmp_path)
    original = loader._final_code
    def audit(root, guard, registration, boundary):
        assert "saved_context_exited" in h.events
        if change == "working": (tmp_path / loader.DRIVER).write_bytes(b"changed working code")
        if change == "committed":
            base = loader.count.old.cache._git
            def git(root, args, guard): return b"changed committed code" if args[0] == "show" else base(root, args, guard)
            monkeypatch.setattr(loader.count.old.cache, "_git", git)
        original(root, guard, registration, boundary)
        if change == "deadline": h.tick += 1800
        if change == "clock": monkeypatch.setattr(loader.prior, "_utc_now", lambda: previous.stamp(-1))
    monkeypatch.setattr(loader, "_final_code", audit)
    with pytest.raises(loader._StageFailure):
        with h.load() as context: context.public_summary()
    with pytest.raises(loader.CountEpochLoaderRefusal): context.closed_summary()


def test_state_flag_and_valid_looking_raw_cannot_forge_closed_summary_inside_live_context(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    with pytest.raises(loader._StageFailure):
        with h.load() as context:
            context._state_identity.update(phase="CLOSED", closure_raw=canonical_json({
                "status": "closed_offline_source_only_slice", "authority": loader.authority()}).encode())
            with pytest.raises(loader.CountEpochLoaderRefusal): context.closed_summary()
            context._state_identity.clear(); context._state_identity["phase"] = "LIVE"
            assert context._failed is True
    with pytest.raises(loader.CountEpochLoaderRefusal): context.closed_summary()


@pytest.mark.parametrize("phase", ["CLOSING", "CLOSED"])
def test_mutated_consumer_return_phase_without_public_access_is_never_silently_repaired(monkeypatch, tmp_path, phase):
    h = Harness(monkeypatch, tmp_path)
    with pytest.raises(loader._StageFailure) as caught:
        with h.load() as context: context._state_identity["phase"] = phase
    assert loader.failure_summary(caught.value)["stage"] == "consumer_return"
    context._state_identity["phase"] = "LIVE"
    with pytest.raises(loader.CountEpochLoaderRefusal, match="latched_failure"): context.closed_summary()


def test_closed_witness_bytes_replacement_refuses_and_restoration_does_not_reset_failure(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    with h.load() as context: context.public_summary()
    witness, parts = context._closure, context._closure._parts
    witness._parts = (parts[0], b'{"ready_for_backtest":true}', *parts[2:])
    with pytest.raises(loader.CountEpochLoaderRefusal): context.closed_summary()
    witness._parts = parts
    with pytest.raises(loader.CountEpochLoaderRefusal, match="latched_failure"): context.closed_summary()


def test_closed_witness_self_reanchoring_and_reconstruction_are_refused(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    with h.load() as context: context.public_summary()
    witness, original = context._closure, context._closure._parts
    copied = tuple(item for item in original)
    assert copied is not original
    witness._parts = witness._identity = copied
    with pytest.raises(loader.CountEpochLoaderRefusal, match="closure_binding_changed"): context.closed_summary()
    witness._parts = witness._identity = original
    with pytest.raises(loader.CountEpochLoaderRefusal): context.closed_summary()
    with pytest.raises(loader.CountEpochLoaderRefusal, match="factory_required"):
        witness.__init__(context._anchor, original[1], seal=loader._SEAL)


def test_closed_witness_exact_fieldset_and_clock_binding_reject_authority_like_extras(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    with h.load() as context: context.public_summary()
    value = context.closed_summary(); value["actual_input_execution_admitted"] = True
    witness = loader._ClosureWitness(context._anchor, canonical_json(value).encode(), seal=loader._SEAL)
    with pytest.raises(loader.CountEpochLoaderRefusal, match="closure_binding_changed"): witness.payload(context._anchor)


def test_constructor_minted_live_witness_cannot_escape_before_original_terminal_issuance(monkeypatch, tmp_path):
    h, escaped = Harness(monkeypatch, tmp_path), []
    with pytest.raises(loader._StageFailure):
        with h.load() as context:
            original = context.private_payload(); registration = original["registration"]
            value = {**context._anchor[0].public_summary(), "schema": "si-count-epoch-ledger-context-closed-v1",
                "status": "closed_offline_source_only_slice", "started_at": registration["started_at"],
                "closed_at": registration["started_at"], "loader_protocol_sha256": loader.PROTOCOL_SHA256,
                "head": registration["head"], "remote": registration["remote"],
                "code_identity_sha256": registration["code_identity_sha256"],
                "code_manifest_sha256": registration["code_manifest_sha256"],
                "model_ledger_sha256": context._anchor[0].sha256,
                "provisional_ledger_sha256": context.sha256, "authority": loader.authority()}
            forged = loader._ClosureWitness(context._anchor, canonical_json(value).encode(), seal=loader._SEAL)
            context._closure = context._closure_identity = forged
            context._state_identity["phase"] = "CLOSED"
            try: escaped.append(context.closed_summary())
            except loader.CountEpochLoaderRefusal: pass
            context._closure = context._closure_identity = None
            context._state_identity["phase"] = "LIVE"
    assert escaped == []
    with pytest.raises(loader.CountEpochLoaderRefusal, match="latched_failure"): context.closed_summary()


def test_prior_cumulative_gate_rejects_boolean_negative_counters_even_when_equal_zero():
    inventory = SimpleNamespace(to_payload=lambda: {"attempts_started": 0, "charged_response_bytes": 0})
    claim = canonical_json({"prior_STARTs": 0, "prior_charged_bytes": 0}).encode()
    negative = canonical_json({"cumulative_STARTs": False, "cumulative_charged_bytes": False}).encode()
    zero = SimpleNamespace(_anchor=(None, None, None, claim, negative))
    v3 = SimpleNamespace(_anchor=(None, None, None, None, claim, negative))
    with pytest.raises(loader.CountEpochLoaderRefusal, match="prior_cumulative_changed"):
        loader._require_prior_cumulative(inventory, inventory, zero, v3)


@pytest.mark.parametrize("field", ["_anchor", "_state", "_closure"])
def test_reflected_live_binding_changes_latch_even_if_restored(monkeypatch, tmp_path, field):
    h = Harness(monkeypatch, tmp_path)
    with pytest.raises(loader._StageFailure):
        with h.load() as context:
            original = getattr(context, field); setattr(context, field, object() if field == "_closure" else None)
            with pytest.raises(loader.CountEpochLoaderRefusal): context.public_summary()
            setattr(context, field, original)
    with pytest.raises(loader.CountEpochLoaderRefusal): context.closed_summary()


def test_self_reanchored_live_wrapper_cannot_replace_original_source_guard(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    with pytest.raises(loader._StageFailure):
        with h.load() as context:
            original = context._anchor
            context._anchor = context._identity = (original[0], original[1], lambda: None, original[3])
            with pytest.raises(loader.CountEpochLoaderRefusal, match="binding_changed"): context.public_summary()
            context._anchor = context._identity = original
    with pytest.raises(loader.CountEpochLoaderRefusal, match="latched_failure"): context.closed_summary()


@pytest.mark.parametrize("change", ["cap", "pin"])
def test_mutated_model_profile_refuses_preflight_before_any_source_load(monkeypatch, tmp_path, change):
    monkeypatch.setattr(loader, "PROTOCOL_SHA256", hash_payload(loader.protocol()))
    if change == "cap": monkeypatch.setattr(loader.model, "MAXIMUM_CUMULATIVE_STARTS", loader.model.MAXIMUM_CUMULATIVE_STARTS + 1)
    else: monkeypatch.setattr(loader.model, "_PROOF_PINS", ())
    def denied(*args, **kwargs): pytest.fail("profile refusal must precede source access")
    monkeypatch.setattr(loader.count.old.cache, "load_registered_cache", denied)
    with pytest.raises(loader._StageFailure) as caught:
        with loader.load_registered_count_epoch_ledger(tmp_path, runtime_head="c" * 40,
                actual_remote="b" * 40, complete_code_manifest={}): pytest.fail("must not yield")
    assert loader.failure_summary(caught.value)["contract_code"] == "epoch_loader_protocol_pending_or_changed"
    assert not tuple(tmp_path.iterdir())


def test_pending_protocol_and_exact58_closure_exclude_metadata_probe_pair(monkeypatch, tmp_path):
    assert len(loader.code_paths()) == len(set(loader.code_paths())) == 58
    assert not any("new_metadata" in name for name in loader.code_paths())
    monkeypatch.setattr(loader, "PROTOCOL_SHA256", "PENDING")
    with pytest.raises(loader._StageFailure) as caught:
        with loader.load_registered_count_epoch_ledger(tmp_path, runtime_head="c" * 40,
                actual_remote="b" * 40, complete_code_manifest={}): pytest.fail("must not yield")
    assert loader.failure_summary(caught.value)["stage"] == "protocol_registration"
    assert not tuple(tmp_path.iterdir())


def test_uninitialized_and_hostile_wrapper_failures_do_not_mask_or_format():
    context = object.__new__(loader.RegisteredCountEpochLedger)
    with pytest.raises(loader.CountEpochLoaderRefusal, match="binding_changed"): context.public_summary()
    assert context._failed is True
    class Error(Exception):
        def __getattribute__(self, name): pytest.fail("hostile exception property")
        def __str__(self): pytest.fail("hostile exception formatting")
    for error in (Error(), loader._StageFailure.__new__(loader._StageFailure)):
        value = loader.failure_summary(error)
        assert value["contract_code"] is None and value["held_field_observation"] is None


def test_model_contract_failure_has_fixed_specific_projection(monkeypatch):
    error = loader.model.CountEpochLedgerRefusal("REFUSED: exact_registered_epoch_roster_required")
    wrapped = loader._StageFailure("epoch_sealing", error, seal=loader._SEAL)
    value = loader.failure_summary(wrapped)
    assert value["contract_code"] == "exact_registered_epoch_roster_required" and value["stage"] == "epoch_sealing"
    assert loader.failure_summary(loader.model.CountEpochLedgerRefusal("REFUSED: SECRET"))["contract_code"] is None
