"""Fabricated custody metadata only; every provider/key/capture seam forbidden."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import diagnose_short_interest_count_custody as diagnostic


def stamp(second=0):
    return (datetime(2026, 10, 25, tzinfo=timezone.utc) + timedelta(seconds=second)).isoformat().replace("+00:00", "Z")


def write(path, raw):
    path.write_bytes(raw); path.chmod(0o600)


@pytest.fixture(autouse=True)
def forbid_external_seams(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("diagnostic must not reach capture/key/HTTP/network")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    for module, name in ((diagnostic.count, "run_registered"), (diagnostic.count, "capture_chunk"),
        (diagnostic.count.old, "run_registered"), (diagnostic.count.old, "capture_child"),
        (diagnostic.count, "read_named_keychain"), (diagnostic.count.old, "read_named_keychain"),
        (diagnostic.count.transport, "http"), (diagnostic.count.old.original.transport, "_http")):
        monkeypatch.setattr(module, name, denied)


class Harness:
    def __init__(self, monkeypatch, tmp_path):
        monkeypatch.setattr(diagnostic, "PROTOCOL_SHA256", hash_payload(diagnostic.protocol()))
        self.root = tmp_path; self.directory = tmp_path / "run"
        self.directory.mkdir(mode=0o700)
        self.owned = diagnostic._OwnedOutput(self.directory, lambda: None)
        self.tick, self.seconds, self.normal_count, self.full_count = 0, 0, 0, 0
        self.full_failure = None
        self.invalidate_source = False
        self.materials = []
    def normal(self):
        self.normal_count += 1
        if self.invalidate_source:
            raise diagnostic.snapshot.RefusedSnapshotError("REFUSED: snapshot_full_member_stamp_changed")
    def full(self):
        self.full_count += 1
        if self.full_failure == self.full_count:
            self.invalidate_source = True
            raise diagnostic.snapshot.RefusedSnapshotError("REFUSED: snapshot_full_member_stamp_changed")
    def clock(self):
        self.seconds += 1
        return stamp(self.seconds)
    def run(self, *, close=True, **changes):
        try:
            return diagnostic.run_probe_sequence(owned=self.owned, normal_check=self.normal,
                refusal_check=lambda: None, source_full_check=self.full, components=(),
                registration=changes.pop("registration", {"fabricated": True}),
                closure_sink=self.materials.append,
                clock=changes.pop("clock", self.clock), monotonic=changes.pop("monotonic", lambda: self.tick), **changes)
        finally:
            if close: self.owned.close()


def test_fixed_sixteen_nonclaims_preserve_zero_source_budgets_and_are_sealed(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    report = h.run()
    value = report.to_payload()
    assert value["probes_published"] == value["probes_opened"] == value["probes_read"] == 16
    assert value["failure"] is None and value["status"] == "local_observations_passed_cause_unreproduced"
    assert h.full_count == 3 and value["authority"]["historical_022_cause"] == "UNKNOWN"
    assert value["authority"]["provider_HTTP"] == value["authority"]["credential_reads"] == 0
    assert value["authority"]["source_START_debits"] == value["authority"]["source_charged_bytes"] == 0
    for ordinal, (size, extra) in enumerate(diagnostic.PROBE_SPECS, 1):
        path = tmp_path / diagnostic.probe_name(ordinal)
        raw = path.read_bytes(); body = json.loads(raw)
        assert len(raw) == size <= 1024 and body["is_capture_claim"] is False
        assert body["provider_HTTP"] == body["credential_reads"] == body["source_START_debits"] == 0
        assert path.stat().st_mode & 0o777 == 0o600
        assert value["observations"][ordinal - 1]["additional_preopen_check"] is extra
    assert set(path.name for path in h.directory.iterdir()) == {"run.completed.json"}
    value["authority"]["source_admitted"] = True
    assert report.to_payload()["authority"]["source_admitted"] is False
    assert report.sha256 == hash_bytes(report.to_bytes())
    with pytest.raises(diagnostic.CustodyDiagnosticRefusal):
        diagnostic.CustodyDiagnosticReport()


def test_pending_protocol_precedes_any_publication(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    monkeypatch.setattr(diagnostic, "PROTOCOL_SHA256", "PENDING")
    with pytest.raises(diagnostic.CustodyDiagnosticRefusal, match="pending"):
        h.run()
    assert not tuple(h.directory.iterdir())


def test_existing_nonclaim_collision_is_immutable_no_retry(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    path = tmp_path / diagnostic.probe_name(1); write(path, b"retained old local evidence")
    before = path.read_bytes()
    value = h.run().to_payload()
    assert value["status"] == "local_diagnostic_refused" and value["probes_published"] == 0
    assert value["metadata_publication_attempts"] == 1 and path.read_bytes() == before
    assert not (tmp_path / diagnostic.probe_name(2)).exists()


def test_absence_preflight_refuses_any_existing_fixed_member_without_writes(tmp_path):
    path = tmp_path / diagnostic.probe_name(16); write(path, b"retained")
    with pytest.raises(diagnostic.CustodyDiagnosticRefusal, match="already_exists"):
        diagnostic._preflight_absent_metadata(tmp_path, lambda: None)
    assert path.read_bytes() == b"retained"


@pytest.mark.parametrize("full_failure", [1, 2, 3])
def test_source_failure_stops_and_retains_dominant_negative(monkeypatch, tmp_path, full_failure):
    h = Harness(monkeypatch, tmp_path); h.full_failure = full_failure
    value = h.run().to_payload()
    assert value["status"] == "local_diagnostic_refused" and (h.directory / "run.refused.json").exists()
    if full_failure == 1:
        assert value["probes_published"] == 0
    else:
        assert value["probes_published"] == 16
    if full_failure == 3:
        assert (h.directory / "run.completed.json").exists()
        assert value["failure"]["stage"] == "postpublication_source_audit"


@pytest.mark.parametrize("phase", ["initial", "during", "closing"])
def test_deadline_never_allows_late_success_or_more_metadata(monkeypatch, tmp_path, phase):
    h = Harness(monkeypatch, tmp_path)
    calls = [0]
    def ticking():
        calls[0] += 1
        limit = 1 if phase == "initial" else 15 if phase == "during" else 10000
        return 1800 if calls[0] >= limit else 0
    if phase == "closing":
        original = h.full
        def full():
            original()
            if h.full_count == 2: h.tick = 1800
        h.full = full
        value = h.run().to_payload()
    else:
        value = h.run(monotonic=ticking, began_tick=0).to_payload()
    assert value["status"] == "local_diagnostic_refused"
    assert value["probes_published"] <= 16


@pytest.mark.parametrize("clock", [lambda: "SECRET_INVALID_CLOCK", lambda: None])
def test_invalid_clock_is_not_serialized_as_private_or_invented_clock(monkeypatch, tmp_path, clock):
    h = Harness(monkeypatch, tmp_path)
    value = h.run(clock=clock).to_payload()
    assert value["status"] == "local_diagnostic_refused" and value["completed_at"] is None
    assert value["started_at"] is None and "SECRET" not in canonical_json(value)


@pytest.mark.parametrize("mutation", ["size", "mode", "nlink"])
def test_projector_inspects_only_real_failed_frame_and_field_names(tmp_path, mutation):
    path = tmp_path / "not-public-SECRET-file"; write(path, b"original")
    with diagnostic.count.old.cache.HeldFiles((path,), protected=True, boundary=lambda: None) as held:
        if mutation == "size": path.write_bytes(b"changed private content")
        elif mutation == "mode": path.chmod(0o644)
        else: os.link(path, tmp_path / "another-private-name")
        try: held.check()
        except diagnostic.count.old.cache.contract.AnchorCacheRefusal as error:
            value = diagnostic.project_held_file_mismatch(error, components=((held, "cache_source"),))
        assert value["component"] == "cache_source" and mutation in value["mismatch_fields"]
        assert "SECRET" not in canonical_json(value) and "private content" not in canonical_json(value)
        assert set(value) == {"component", "mismatch_fields", "observation"}


def test_hostile_exception_properties_and_arguments_are_never_touched():
    class Hostile:
        def __eq__(self, other): pytest.fail("hostile comparison executed")
        def __str__(self): pytest.fail("hostile formatting executed")
    class Error(Exception):
        def __getattribute__(self, name): pytest.fail("external exception property inspected")
    assert diagnostic.project_held_file_mismatch(Error()) is None
    error = diagnostic.count.old.cache.contract.AnchorCacheRefusal(Hostile())
    assert diagnostic.project_held_file_mismatch(error) is None


def test_forged_same_named_frame_cannot_supply_stat_fields():
    def _entry_check():
        entry, value = (None, 0, 0, (1, 2, 3, 4, 5), 1, 0o600), object()
        raise diagnostic.count.old.cache.contract.AnchorCacheRefusal("held_custody_file_changed")
    try: _entry_check()
    except diagnostic.count.old.cache.contract.AnchorCacheRefusal as error:
        assert diagnostic.project_held_file_mismatch(error) is None


def test_traceback_walk_has_a_fixed_small_bound(tmp_path):
    path = tmp_path / "fake"; write(path, b"original")
    with diagnostic.count.old.cache.HeldFiles((path,), protected=True, boundary=lambda: None) as held:
        path.write_bytes(b"changed")
        def recurse(depth):
            if depth: recurse(depth - 1)
            else: held.check()
        try: recurse(140)
        except diagnostic.count.old.cache.contract.AnchorCacheRefusal as error:
            assert diagnostic.project_held_file_mismatch(error) is None


def test_new_probe_held_failure_has_fixed_new_probe_label(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    original = diagnostic.count.old.cache.HeldFiles.__enter__
    def entering(held):
        # Fabricated regression only: mutate a just-published nonclaim before
        # the real, unmodified _entry_check evaluates its retained stamp.
        path = held._anchor[1][0][0]
        if path.name == diagnostic.probe_name(1):
            path.write_bytes(b"changed fake metadata")
        return original(held)
    monkeypatch.setattr(diagnostic.count.old.cache.HeldFiles, "__enter__", entering)
    value = h.run().to_payload()
    assert value["failure"]["stage"] == "held_custody_open"
    assert value["failure"]["held_field_observation"]["component"] == "new_probe"
    assert "size" in value["failure"]["held_field_observation"]["mismatch_fields"]
    assert value["probes_published"] == 1 and value["probes_opened"] == 0


def test_v3_wrapper_uses_its_own_literal_paths_and_negative_membership(tmp_path):
    directory = tmp_path / "v3"; directory.mkdir(mode=0o700)
    claim_path, negative_path = tmp_path / "v3-only.spent.json", directory / "run.refused.json"
    write(claim_path, b'{"fake":"spent"}'); write(negative_path, b'{"fake":"negative"}')
    class Queries:
        def _guard(self): pass
    with diagnostic.count.old.cache.HeldFiles((claim_path, negative_path), protected=True, boundary=lambda: None) as held:
        proof = diagnostic._V3ZeroProof(directory, held, Queries(), (claim_path, negative_path),
            claim_path.read_bytes(), negative_path.read_bytes())
        proof.full_check()
        write(directory / "chunk.closed.json", b"{}")
        with pytest.raises(diagnostic.CustodyDiagnosticRefusal): proof.full_check()


def test_unknown_original_boundary_failure_is_not_misattributed_to_new_probe(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    private = tmp_path / "unidentified-original"; write(private, b"original fake evidence")
    with diagnostic.count.old.cache.HeldFiles((private,), protected=True, boundary=lambda: None) as original_held:
        private.write_bytes(b"mutated fake evidence with different size")
        original_init = diagnostic.count.old.cache.HeldFiles.__init__
        in_constructor = [False]
        def init(held, *args, **kwargs):
            in_constructor[0] = True
            try: original_init(held, *args, **kwargs)
            finally: in_constructor[0] = False
        original_normal = h.normal
        def normal():
            original_normal()
            if in_constructor[0]: original_held.check()
        h.normal = normal
        monkeypatch.setattr(diagnostic.count.old.cache.HeldFiles, "__init__", init)
        value = h.run().to_payload()
    assert value["failure"]["stage"] == "held_custody_open"
    assert value["probes_published"] == 1 and value["probes_opened"] == 0
    assert value["failure"]["held_field_observation"]["component"] == "unidentified"


def test_runtime_registration_is_detached_and_preserved_in_original_controls(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    registration = {"head": "a" * 40, "remote": "b" * 40,
        "code_files": [{"path": "fabricated.py", "sha256": "c" * 64}],
        "code_identity_sha256": "d" * 64,
        "historical_sources": {"v2_zero": {"head": "e" * 40}, "v3_zero": {"head": "f" * 40}}}
    report = h.run(registration=registration)
    registration["historical_sources"]["v3_zero"]["head"] = "mutated"
    assert report.to_payload()["registration"]["historical_sources"]["v3_zero"]["head"] == "f" * 40
    assert json.loads((h.directory / "run.completed.json").read_bytes())["registration"] == report.to_payload()["registration"]


def test_successful_context_closure_is_a_separate_terminal_marker(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    try:
        provisional = h.run(close=False)
        assert not (h.directory / "run.closed.json").exists()
        closed_contexts = []
        with diagnostic.ExitStack() as stack:
            stack.callback(closed_contexts.append, "source and code contexts closed")
        def final_check(): assert closed_contexts == ["source and code contexts closed"]
        result = diagnostic._after_contexts(h.owned, provisional, context_error=None,
            final_check=final_check, began_tick=0, monotonic=lambda: 0, clock=h.clock,
            closure_material=h.materials[-1])
        value = result.to_payload()
        assert value["context_closure"] == "all_source_and_code_contexts_closed"
        assert value["status"] == "local_observations_closed_cause_unreproduced"
        assert value["provisional_report_sha256"] == provisional.sha256
        assert set(path.name for path in h.directory.iterdir()) == {"run.completed.json", "run.closed.json"}
    finally: h.owned.close()


def test_source_context_exit_failure_appends_dominating_negative(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    try:
        provisional = h.run(close=False)
        def closing():
            raise diagnostic.snapshot.RefusedSnapshotError("REFUSED: snapshot_full_member_stamp_changed")
        error = None
        try:
            with diagnostic.ExitStack() as stack: stack.callback(closing)
        except diagnostic.snapshot.RefusedSnapshotError as caught: error = caught
        value = diagnostic._after_contexts(h.owned, provisional, context_error=error,
            final_check=lambda: None, began_tick=0, monotonic=lambda: 0,
            closure_material=h.materials[-1]).to_payload()
        assert value["status"] == "local_diagnostic_refused"
        assert value["failure"]["stage"] == "source_or_code_context_exit"
        assert (h.directory / "run.completed.json").exists() and (h.directory / "run.refused.json").exists()
        assert not (h.directory / "run.closed.json").exists()
    finally: h.owned.close()


def test_previous_negative_is_not_overwritten_by_another_context_failure(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path); h.full_failure = 1
    try:
        refused = h.run(close=False)
        original = (h.directory / "run.refused.json").read_bytes()
        result = diagnostic._after_contexts(h.owned, refused, context_error=ValueError("SECRET"),
            final_check=lambda: None, began_tick=0, monotonic=lambda: 0,
            closure_material=h.materials[-1])
        assert result.to_bytes() == original == (h.directory / "run.refused.json").read_bytes()
        assert not (h.directory / "run.closed.json").exists()
    finally: h.owned.close()


def test_postclosure_validation_failure_dominates_provisional_and_closed_markers(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    try:
        provisional = h.run(close=False); calls = []
        def final_check():
            calls.append(None)
            if len(calls) == 2:
                raise diagnostic.CustodyDiagnosticRefusal("REFUSED: fabricated_changed")
        value = diagnostic._after_contexts(h.owned, provisional, context_error=None,
            final_check=final_check, began_tick=0, monotonic=lambda: 0, clock=h.clock,
            closure_material=h.materials[-1]).to_payload()
        assert value["failure"]["stage"] == "post_context_closure"
        assert (h.directory / "run.closed.json").exists() and (h.directory / "run.refused.json").exists()
    finally: h.owned.close()


@pytest.mark.parametrize("member", ["metadata", "provisional_control"])
def test_post_context_original_byte_or_stamp_change_cannot_close(monkeypatch, tmp_path, member):
    h = Harness(monkeypatch, tmp_path)
    try:
        provisional = h.run(close=False)
        path = tmp_path / diagnostic.probe_name(1) if member == "metadata" else h.directory / "run.completed.json"
        before = path.read_bytes()
        changed = before.replace(b"ppp", b"qqq", 1) if member == "metadata" else before.replace(b"false", b"False", 1)
        assert changed != before and len(changed) == len(before)
        path.write_bytes(changed)
        value = diagnostic._after_contexts(h.owned, provisional, context_error=None,
            final_check=lambda: None, began_tick=0, monotonic=lambda: 0, clock=h.clock,
            closure_material=h.materials[-1]).to_payload()
        assert value["failure"]["stage"] == "post_context_closure"
        assert (h.directory / "run.refused.json").exists() and not (h.directory / "run.closed.json").exists()
    finally: h.owned.close()


def test_original_owned_output_inode_replacement_cannot_close(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    try:
        provisional = h.run(close=False)
        h.directory.rename(tmp_path / "retained-run")
        h.directory.mkdir(mode=0o700)
        with pytest.raises(ValueError, match="owned_output_directory_inode_changed"):
            diagnostic._after_contexts(h.owned, provisional, context_error=None,
                final_check=lambda: None, began_tick=0, monotonic=lambda: 0, clock=h.clock,
                closure_material=h.materials[-1])
        assert not (h.directory / "run.closed.json").exists()
        assert (tmp_path / "retained-run" / "run.completed.json").exists()
    finally: h.owned.close()


def test_final_closure_deadline_is_rechecked_after_terminal_audits(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    try:
        provisional = h.run(close=False); calls = []
        def final_check():
            calls.append(None)
            if len(calls) == 2: h.tick = 1800
        value = diagnostic._after_contexts(h.owned, provisional, context_error=None,
            final_check=final_check, began_tick=0, monotonic=lambda: h.tick, clock=h.clock,
            closure_material=h.materials[-1]).to_payload()
        assert value["status"] == "local_diagnostic_refused"
        assert value["failure"]["stage"] == "post_context_closure"
        assert (h.directory / "run.refused.json").exists()
    finally: h.owned.close()


@pytest.mark.parametrize("member", ["metadata", "provisional_control"])
def test_final_code_audit_cannot_race_earlier_original_metadata_audit(monkeypatch, tmp_path, member):
    h = Harness(monkeypatch, tmp_path)
    try:
        provisional = h.run(close=False); calls = []
        path = tmp_path / diagnostic.probe_name(1) if member == "metadata" else h.directory / "run.completed.json"
        def final_check():
            calls.append(None)
            if len(calls) == 2:
                raw = path.read_bytes()
                changed = raw.replace(b"ppp", b"qqq", 1) if member == "metadata" else raw.replace(b"false", b"False", 1)
                assert changed != raw and len(changed) == len(raw)
                path.write_bytes(changed)
        value = diagnostic._after_contexts(h.owned, provisional, context_error=None,
            final_check=final_check, began_tick=0, monotonic=lambda: 0, clock=h.clock,
            closure_material=h.materials[-1]).to_payload()
        assert value["status"] == "local_diagnostic_refused"
        assert (h.directory / "run.refused.json").exists()
    finally: h.owned.close()


def test_existing_negative_sibling_blocks_and_is_never_overwritten(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    try:
        provisional = h.run(close=False)
        negative = b'{"retained_fixed_negative":true}'
        write(h.directory / "run.refused.json", negative)
        with pytest.raises(FileExistsError):
            diagnostic._after_contexts(h.owned, provisional, context_error=None,
                final_check=lambda: None, began_tick=0, monotonic=lambda: 0, clock=h.clock,
                closure_material=h.materials[-1])
        assert (h.directory / "run.refused.json").read_bytes() == negative
        assert not (h.directory / "run.closed.json").exists()
    finally: h.owned.close()


def _v3_fixture(monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostic.count, "OUTPUT", Path("v3"))
    directory = tmp_path / "v3"; directory.mkdir(mode=0o700)
    class Queries:
        sha256 = "a" * 64
        def _guard(self): pass
    class Guard:
        def check(self): pass
        def binding(self): return tmp_path, "c" * 40
    entries = [{"path": name, "sha256": hash_bytes(name.encode())} for name in diagnostic.count.code_paths()]
    registration = {"head": diagnostic.V3_HEAD, "remote": diagnostic.V3_REMOTE,
        "code_identity_sha256": hash_payload({"git_commit": diagnostic.V3_HEAD, "files": entries})}
    claim = {"schema": "si-bounded-count-spent-claim-v3", "protocol_sha256": diagnostic.count.PROTOCOL_SHA256,
        "registration": registration, "started_at": stamp(), "query_plan_sha256": Queries.sha256,
        "predecessor_manifest_sha256": diagnostic.count.PREDECESSOR_MANIFEST_SHA256,
        "maximum_attempts": 528, "maximum_extra_attempts": 16, "prior_STARTs": 13992,
        "prior_charged_bytes": 23452681, "maximum_cumulative_bytes": 4 * 1024 ** 3, "restart_allowed": False}
    claim_raw = canonical_json(claim).encode()
    monkeypatch.setattr(diagnostic, "V3_CLAIM_SHA256", hash_bytes(claim_raw))
    refused = {"schema": "si-bounded-count-refused-v3", "code": "initialization_refused_after_spent_claim",
        "protocol_sha256": diagnostic.count.PROTOCOL_SHA256, "started_at": stamp(), "refused_at": stamp(1),
        "START_debits": 0, "known_HTTP_invocations": 0, "HTTP_count_exact": True, "unreceipted_attempts": [],
        "receipt_not_persisted_attempts": [], "unpublished_observed_diagnostics": [], "charged_bytes": 0,
        "cumulative_STARTs": 13992, "cumulative_charged_bytes": 23452681, "resolved_descriptors": 0,
        "new_claim_sha256": diagnostic.V3_CLAIM_SHA256, "authority": diagnostic.count.authority(),
        "failure_detail": {"stage": "claim_custody_open", "category": "local_contract_refusal",
            "errno_name": None, "contract_code": "held_custody_file_changed"}}
    refused_raw = canonical_json(refused).encode()
    monkeypatch.setattr(diagnostic, "V3_REFUSAL_SHA256", hash_bytes(refused_raw))
    write(tmp_path / diagnostic.count.CLAIM, claim_raw)
    write(directory / "run.refused.json", refused_raw)
    def git(root, arguments, guard):
        assert root == tmp_path
        return b"" if arguments[0] == "merge-base" else arguments[1].partition(":")[2].encode()
    monkeypatch.setattr(diagnostic.count.old.cache, "_git", git)
    return Guard(), Queries(), directory


def test_full_v3_constructor_and_historical_composition_uses_v3_not_v2(monkeypatch, tmp_path):
    guard, queries, directory = _v3_fixture(monkeypatch, tmp_path)
    with diagnostic._v3_zero(tmp_path, guard, queries) as (held, proof):
        assert type(proof) is diagnostic._V3ZeroProof
        proof.full_check()
        assert held.read(tmp_path / diagnostic.count.CLAIM, 65536) != b"v2"
    assert {path.name for path in directory.iterdir()} == {"run.refused.json"}


def test_full_v3_composition_rejects_positive_sibling(monkeypatch, tmp_path):
    guard, queries, directory = _v3_fixture(monkeypatch, tmp_path)
    write(directory / "chunk.closed.json", b'{}')
    with pytest.raises(diagnostic.CustodyDiagnosticRefusal, match="exact_negative_membership"):
        with diagnostic._v3_zero(tmp_path, guard, queries): pytest.fail("negative dominated namespace yielded")


def test_full_v3_composition_rejects_changed_historical_code(monkeypatch, tmp_path):
    guard, queries, unused = _v3_fixture(monkeypatch, tmp_path)
    original = diagnostic.count.old.cache._git
    def git(root, arguments, checked):
        raw = original(root, arguments, checked)
        return raw + b"changed" if arguments[0] == "show" else raw
    monkeypatch.setattr(diagnostic.count.old.cache, "_git", git)
    with pytest.raises(diagnostic.CustodyDiagnosticRefusal, match="exact_historical_code"):
        with diagnostic._v3_zero(tmp_path, guard, queries): pytest.fail("changed original code yielded")


@pytest.mark.parametrize("changed", ["working", "committed", "earlier_during_later_read"])
def test_final_code_only_custody_binds_all_committed_bytes_and_final_stamps(monkeypatch, tmp_path, changed):
    monkeypatch.setattr(diagnostic, "PROTOCOL_SHA256", hash_payload(diagnostic.protocol()))
    names = tuple(f"code-{number:02d}.py" for number in range(56))
    monkeypatch.setattr(diagnostic, "code_paths", lambda: names)
    originals = {name: ("# original " + name).encode() for name in names}
    for name, raw in originals.items(): write(tmp_path / name, raw)
    entries = [{"path": name, "sha256": hash_bytes(originals[name])} for name in names]
    registration = {"head": "a" * 40, "remote": "b" * 40, "code_files": entries,
        "code_manifest_sha256": hash_payload({row["path"]: row["sha256"] for row in entries}),
        "code_identity_sha256": hash_payload({"git_commit": "a" * 40, "files": entries})}
    class Guard:
        def check(self): pass
        def refresh(self): pass
        def binding(self): return tmp_path, "a" * 40, "b" * 40
    def git(root, arguments, guard):
        assert arguments[0] == "show"
        name = arguments[1].partition(":")[2]
        if changed == "earlier_during_later_read" and name == names[-1]:
            (tmp_path / names[0]).write_bytes(b"changed after earlier read")
        return b"different committed code" if changed == "committed" else originals[name]
    monkeypatch.setattr(diagnostic.count.old.cache, "_git", git)
    if changed == "working": (tmp_path / names[0]).write_bytes(b"changed working code")
    with pytest.raises(diagnostic.CustodyDiagnosticRefusal):
        diagnostic._current_code_after_contexts(tmp_path, Guard(), registration)
