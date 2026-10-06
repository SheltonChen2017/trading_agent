"""Invented source views only; never an observed custody-root replay."""
from __future__ import annotations

from dataclasses import replace
import copy
import json
from pathlib import Path
import re
import sys
from types import FunctionType, ModuleType, SimpleNamespace

import pytest

from data.hashing import hash_bytes, hash_payload
from research import insider_buying_sec_recovery_v4_historical_replay as base
from research import insider_buying_sec_recovery_v4_source_view as module


# The genuine historical four-read call shape, compiled only into fabricated
# modules. Test-local pins cannot enter the observed replay entrypoint.
_UNION_SOURCE = b'''from __future__ import annotations
def _validator_source_sha256() -> str:
    sources = (
        (sys.modules[__name__],
         "research/insider_buying_sec_all_form4_parent_recovery_union.py"),
        (campaign, "research/insider_buying_sec_all_form4_parent_campaign.py"),
        (complete_submission, "research/insider_buying/sec_complete_submission.py"),
        (raw_projection, "research/insider_buying/sec_raw_parent_projection.py"),
    )
    rows: list[dict[str, str]] = []
    for module, relative in sources:
        path = (diagnostic._LANE_ROOT / relative).resolve()
        if Path(module.__file__).resolve() != path:
            _refuse("offline validator module is not from the designated lane")
        rows.append({"path": relative, "sha256": hash_bytes(path.read_bytes())})
    return hash_payload(rows)
'''


@pytest.fixture
def invented_view(monkeypatch, tmp_path):
    root = tmp_path.resolve()
    paths = tuple(path for path, _ in base.HISTORICAL_FILES)
    blobs = tuple((path, _UNION_SOURCE if index == 0 else
                   f"MARKER = 'invented-captured-{index}'\n".encode())
                  for index, path in enumerate(paths))
    modules = []
    for relative, raw in blobs:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        name, _ = base._module_name(relative)
        loaded = ModuleType(name)
        loaded.__file__ = str(path)
        monkeypatch.setitem(sys.modules, name, loaded)
        modules.append(loaded)
    union, campaign, complete_submission, raw_projection = modules
    diagnostic = ModuleType("research.invented_diagnostic")
    diagnostic._LANE_ROOT = root
    diagnostic.invented_marker = object()

    def refuse(reason):
        raise ValueError(reason)

    union.__dict__.update(sys=sys, Path=Path, hash_bytes=hash_bytes,
                          hash_payload=hash_payload, _refuse=refuse,
                          diagnostic=diagnostic, campaign=campaign,
                          complete_submission=complete_submission,
                          raw_projection=raw_projection)
    for loaded, (_, raw) in zip(modules, blobs, strict=True):
        exec(compile(raw, loaded.__file__, "exec", dont_inherit=True), loaded.__dict__)
    files = [{"path": relative, "sha256": hash_bytes(raw)} for relative, raw in blobs]
    monkeypatch.setattr(base, "LANE_ROOT", root)
    monkeypatch.setattr(base, "HISTORICAL_FILES", tuple((row["path"], row["sha256"]) for row in files))
    monkeypatch.setattr(base, "HISTORICAL_VALIDATOR_SHA256", hash_payload(files))
    return SimpleNamespace(root=root, blobs=blobs, modules=tuple(modules),
                           union=union, diagnostic=diagnostic, files=files,
                           validator_sha256=hash_payload(files))


def test_source_view_reads_a_complete_ordered_cycle_and_restores_only_its_facade(invented_view):
    fixture = invented_view
    view = module.HistoricalSourceView(fixture.blobs, fixture.union)
    original_function = fixture.union._validator_source_sha256
    original_members = fixture.union.__dict__.copy()
    with view:
        assert fixture.union.diagnostic is not fixture.diagnostic
        assert fixture.union.diagnostic.invented_marker is fixture.diagnostic.invented_marker
        assert fixture.union._validator_source_sha256 is original_function
        assert fixture.union._validator_source_sha256() == fixture.validator_sha256
        proof = view.proof()
        assert proof == {
            "kind": module.SOURCE_VIEW_VERSION,
            "historical_commit": base.HISTORICAL_COMMIT,
            "historical_validator_sha256": fixture.validator_sha256,
            "files": fixture.files,
            "validator_function_name": "_validator_source_sha256",
            "ordered_read_cycles": 1, "source_read_count": 4,
            "source_read_trace_sha256": proof["source_read_trace_sha256"],
            "callsite_bound": True,
        }
        assert re.fullmatch(r"[0-9a-f]{64}", proof["source_read_trace_sha256"])
    assert fixture.union.__dict__ == original_members
    assert view.proof() == proof


def test_current_source_drift_is_read_normally_but_not_substituted_for_captured_bytes(invented_view):
    fixture = invented_view
    for relative, _ in fixture.blobs:
        (fixture.root / relative).write_bytes(b"MARKER = 'invented current drift'\n")
    assert fixture.union._validator_source_sha256() != fixture.validator_sha256
    with module.HistoricalSourceView(fixture.blobs, fixture.union) as view:
        assert (fixture.union.diagnostic._LANE_ROOT / fixture.blobs[0][0]).read_bytes() == (
            b"MARKER = 'invented current drift'\n")
        assert fixture.union._validator_source_sha256() == fixture.validator_sha256
        assert view.proof()["source_read_count"] == 4
    assert fixture.union._validator_source_sha256() != fixture.validator_sha256


def test_unrelated_reads_are_real_paths_and_do_not_count_as_source_proof(invented_view):
    fixture = invented_view
    path = fixture.root / "ordinary.txt"
    path.write_bytes(b"invented ordinary read")
    with module.HistoricalSourceView(fixture.blobs, fixture.union) as view:
        ordinary = fixture.union.diagnostic._LANE_ROOT / "ordinary.txt"
        assert isinstance(ordinary, Path)
        assert ordinary.read_bytes() == b"invented ordinary read"
        with pytest.raises(module.HistoricalSourceViewError):
            view.proof()
        fixture.union._validator_source_sha256()
        assert view.proof()["source_read_count"] == 4


def test_multiple_ordered_cycles_have_distinct_detached_trace_proofs(invented_view):
    fixture = invented_view
    with module.HistoricalSourceView(fixture.blobs, fixture.union) as view:
        fixture.union._validator_source_sha256()
        first = view.proof()
        fixture.union._validator_source_sha256()
        second = view.proof()
        assert second["ordered_read_cycles"] == 2
        assert second["source_read_count"] == 8
        assert first["source_read_trace_sha256"] != second["source_read_trace_sha256"]
        second["files"][0]["sha256"] = "0" * 64
        assert view.proof()["files"] == fixture.files


@pytest.mark.parametrize("case", ("missing", "extra", "reordered", "corrupt", "wrong_path", "list",
                                  "mutable_item", "text_bytes", "empty"))
def test_source_view_refuses_non_exact_historical_blob_inventory(invented_view, case):
    fixture = invented_view
    blobs = fixture.blobs
    if case == "missing":
        blobs = blobs[:-1]
    elif case == "extra":
        blobs = (*blobs, blobs[0])
    elif case == "reordered":
        blobs = tuple(reversed(blobs))
    elif case == "corrupt":
        blobs = ((blobs[0][0], blobs[0][1] + b"\n"), *blobs[1:])
    elif case == "wrong_path":
        blobs = (("research/invented.py", blobs[0][1]), *blobs[1:])
    elif case == "list":
        blobs = list(blobs)
    elif case == "mutable_item":
        blobs = ([blobs[0][0], blobs[0][1]], *blobs[1:])
    elif case == "text_bytes":
        blobs = ((blobs[0][0], blobs[0][1].decode()), *blobs[1:])
    else:
        blobs = ((blobs[0][0], b""), *blobs[1:])
    with pytest.raises(module.HistoricalSourceViewError):
        module.HistoricalSourceView(blobs, fixture.union)
    assert fixture.union.diagnostic is fixture.diagnostic


@pytest.mark.parametrize("case", ("missing", "extra", "reordered", "list", "foreign_identity"))
def test_source_view_requires_exact_ordered_module_identities(invented_view, case):
    fixture = invented_view
    modules = fixture.modules
    if case == "missing":
        modules = modules[:-1]
    elif case == "extra":
        modules = (*modules, modules[0])
    elif case == "reordered":
        modules = tuple(reversed(modules))
    elif case == "list":
        modules = list(modules)
    else:
        foreign = ModuleType(modules[1].__name__)
        foreign.__dict__.update(modules[1].__dict__)
        modules = (modules[0], foreign, *modules[2:])
    with pytest.raises(module.HistoricalSourceViewError):
        module.HistoricalSourceView(fixture.blobs, fixture.union, modules=modules)


@pytest.mark.parametrize("case", ("foreign_code", "foreign_globals", "filename", "name"))
def test_source_view_rejects_a_validator_not_bound_to_its_captured_code_and_globals(invented_view, case):
    fixture = invented_view
    fn = fixture.union._validator_source_sha256
    if case == "foreign_code":
        fixture.union._validator_source_sha256 = lambda: fixture.validator_sha256
    elif case == "foreign_globals":
        fixture.union._validator_source_sha256 = FunctionType(fn.__code__, fixture.union.__dict__.copy())
    elif case == "filename":
        fixture.union._validator_source_sha256 = FunctionType(
            fn.__code__.replace(co_filename="/invented/foreign.py"), fixture.union.__dict__)
    else:
        fixture.union._validator_source_sha256 = FunctionType(
            fn.__code__.replace(co_name="invented_alternate"), fixture.union.__dict__)
    with pytest.raises(module.HistoricalSourceViewError):
        module.HistoricalSourceView(fixture.blobs, fixture.union)


@pytest.mark.parametrize("index", range(4))
@pytest.mark.parametrize("case", ("path", "registry", "name"))
def test_source_view_refuses_current_module_path_name_or_registry_drift(invented_view, monkeypatch, index, case):
    fixture = invented_view
    loaded = fixture.modules[index]
    if case == "path":
        monkeypatch.setattr(loaded, "__file__", str(fixture.root / "outside.py"))
    elif case == "registry":
        monkeypatch.setitem(sys.modules, loaded.__name__, ModuleType(loaded.__name__))
    else:
        monkeypatch.setattr(loaded, "__name__", "research.invented_alternate")
    with pytest.raises(module.HistoricalSourceViewError):
        module.HistoricalSourceView(fixture.blobs, fixture.union)


def test_source_view_rechecks_validator_identity_after_construction(invented_view):
    fixture = invented_view
    view = module.HistoricalSourceView(fixture.blobs, fixture.union)
    fixture.union._validator_source_sha256 = lambda: fixture.validator_sha256
    with pytest.raises(module.HistoricalSourceViewError):
        with view:
            fixture.union._validator_source_sha256()
    assert fixture.union.diagnostic is fixture.diagnostic


@pytest.mark.parametrize("operation", ("resolve", "read_bytes"))
def test_source_path_cannot_escape_the_bound_validator_frame(invented_view, operation):
    fixture = invented_view
    captured = []

    def capture_path(frame, event, arg):
        if (event == "return" and frame.f_globals is module.__dict__
                and frame.f_code.co_name == "read_bytes"):
            captured.append(frame.f_locals["self"])

    with module.HistoricalSourceView(fixture.blobs, fixture.union) as view:
        previous = sys.getprofile()
        try:
            sys.setprofile(capture_path)
            fixture.union._validator_source_sha256()
        finally:
            sys.setprofile(previous)
        assert len(captured) == 4
        with pytest.raises(module.HistoricalSourceViewError):
            getattr(captured[0], operation)()
        assert view.proof()["source_read_count"] == 4


@pytest.mark.parametrize("complete_first", (False, True))
def test_aborted_read_cycle_cannot_issue_proof_and_restores_the_facade(invented_view, complete_first):
    fixture = invented_view
    view = module.HistoricalSourceView(fixture.blobs, fixture.union)

    def abort_after_read(frame, event, arg):
        if (event == "return" and frame.f_globals is module.__dict__
                and frame.f_code.co_name == "read_bytes"):
            raise RuntimeError("invented read interruption")

    with pytest.raises(RuntimeError, match="invented read interruption"):
        with view:
            if complete_first:
                fixture.union._validator_source_sha256()
            previous = sys.getprofile()
            try:
                sys.setprofile(abort_after_read)
                fixture.union._validator_source_sha256()
            finally:
                sys.setprofile(previous)
    assert fixture.union.diagnostic is fixture.diagnostic
    with pytest.raises(module.HistoricalSourceViewError):
        view.proof()


def test_source_view_is_single_use_and_restores_after_an_unrelated_exception(invented_view):
    fixture = invented_view
    view = module.HistoricalSourceView(fixture.blobs, fixture.union)
    with pytest.raises(RuntimeError, match="invented interruption"):
        with view:
            fixture.union._validator_source_sha256()
            raise RuntimeError("invented interruption")
    assert fixture.union.diagnostic is fixture.diagnostic
    with pytest.raises(module.HistoricalSourceViewError):
        with view:
            pass


@pytest.mark.parametrize("binding", ("Path", "sys", "hash_bytes", "hash_payload", "defaults", "kwdefaults"))
def test_source_view_requires_the_captured_validator_critical_globals_and_call_defaults(invented_view, binding):
    fixture = invented_view
    if binding == "Path":
        fixture.union.Path = lambda value: Path(value)
    elif binding == "sys":
        fixture.union.sys = SimpleNamespace(modules=sys.modules)
    elif binding == "hash_bytes":
        fixture.union.hash_bytes = lambda raw: hash_bytes(raw)
    elif binding == "hash_payload":
        fixture.union.hash_payload = lambda payload: hash_payload(payload)
    elif binding == "defaults":
        fixture.union._validator_source_sha256.__defaults__ = (None,)
    else:
        fixture.union._validator_source_sha256.__kwdefaults__ = {"invented": None}
    with pytest.raises(module.HistoricalSourceViewError):
        module.HistoricalSourceView(fixture.blobs, fixture.union)


@pytest.mark.parametrize("binding", ("function", "campaign", "Path", "module_path", "registry"))
def test_source_view_rechecks_live_bindings_during_each_captured_read(invented_view, monkeypatch, binding):
    fixture = invented_view
    bound_function = fixture.union._validator_source_sha256
    with pytest.raises(module.HistoricalSourceViewError):
        with module.HistoricalSourceView(fixture.blobs, fixture.union):
            if binding == "function":
                fixture.union._validator_source_sha256 = lambda: fixture.validator_sha256
            elif binding == "campaign":
                fake = ModuleType(fixture.modules[1].__name__)
                fake.__dict__.update(fixture.modules[1].__dict__)
                fixture.union.campaign = fake
            elif binding == "Path":
                fixture.union.Path = lambda value: Path(value)
            elif binding == "module_path":
                monkeypatch.setattr(fixture.modules[1], "__file__", str(fixture.root / "elsewhere.py"))
            else:
                monkeypatch.setitem(sys.modules, fixture.modules[1].__name__, ModuleType("research.foreign"))
            bound_function()
    assert fixture.union.diagnostic is fixture.diagnostic


def test_private_read_cannot_count_an_arbitrary_non_validator_frame_as_bound_source_reads(invented_view):
    fixture = invented_view
    with module.HistoricalSourceView(fixture.blobs, fixture.union) as view:
        fixture.union._validator_source_sha256()
        original = view.proof()
        with pytest.raises(module.HistoricalSourceViewError):
            view._read(sys._getframe(), fixture.blobs[0][0])
        assert view.proof() == original


@pytest.fixture
def aggregate():
    # Fabricated worker envelope for strict contract tests; not an observed
    # receipt and never an invocation of the retained-root worker.
    root = Path(__file__).resolve().parents[1]
    files = [{"path": path, "sha256": sha} for path, sha in base.HISTORICAL_FILES]
    worker_sha = hash_bytes((root / module._WORKER_PATH).read_bytes())
    base_sha = hash_bytes((root / module._BASE_PATH).read_bytes())
    cycles = 2
    trace_bytes = b"".join(base._canonical({
        "cycle": cycle, "path": path, "sha256": sha, "source_kind": "historical_git_blob",
    }) + b"\n" for cycle in range(cycles) for path, sha in base.HISTORICAL_FILES)
    payload = {
        "kind": module.VERSION, "scope": "observed_offline_historical_source_view_replay",
        "repository_head": "f" * 40, "historical_commit": base.HISTORICAL_COMMIT,
        "historical_validator_sha256": base.HISTORICAL_VALIDATOR_SHA256,
        "historical_files": files,
        "worker_bootstrap_sha256": hash_bytes(module._BOOTSTRAP.encode()),
        "worker_source_sha256": worker_sha, "base_source_sha256": base_sha,
        "current_source_inventory_sha256": "1" * 64,
        "executed_modules": [{**row, "source_kind": "historical_git_blob"} for row in files] + [
            {"path": module._WORKER_PATH, "sha256": worker_sha, "source_kind": "current_source_snapshot"},
            {"path": module._BASE_PATH, "sha256": base_sha, "source_kind": "current_source_snapshot"},
        ],
        "historical_function_paths": [path for path, _ in base.HISTORICAL_FILES],
        "source_view": {
            "kind": module.SOURCE_VIEW_VERSION, "historical_commit": base.HISTORICAL_COMMIT,
            "historical_validator_sha256": base.HISTORICAL_VALIDATOR_SHA256,
            "files": copy.deepcopy(files), "validator_function_name": "_validator_source_sha256",
            "ordered_read_cycles": cycles, "source_read_count": cycles * 4,
            "source_read_trace_sha256": hash_bytes(trace_bytes), "callsite_bound": True,
        },
        "counts": dict(base._COUNTS), "total_parents": 99394, "source_bound_count": 19526,
        "v3_attempt_count": 1847, "v3_completed_count": 1846,
        "stopped_v3_disposition": "preserved_unresolved_not_resumable",
        "diagnostic_report_sha256": base.DIAGNOSTIC_REPORT_SHA256,
        "diagnostic_body_sha256": base.DIAGNOSTIC_BODY_SHA256, "diagnostic_body_size_bytes": 7373,
        "current_validator_equality_required": False,
        "historical_environment_recreated": False, "frozen_files_may_be_thawed": False,
        "isolation": {"os_network_denied": True, "os_file_writes_denied": True,
                      "os_process_fork_denied": True, "audit_additional_processes_denied": True,
                      "source_only_lane_imports": True},
        "authority": dict(base._AUTHORITY),
    }
    payload.update(module._REPLAY_HASHES)
    return payload


def test_source_view_receipt_accepts_only_complete_hash_bound_false_authority_contract(aggregate):
    assert module._validate_receipt(aggregate) == aggregate
    assert sum(aggregate["counts"].values()) == 99394
    assert aggregate["source_view"]["source_read_count"] == 8
    assert aggregate["current_validator_equality_required"] is False


@pytest.mark.parametrize("field", ("offline_corrected_diagnostic", "accepted_ambiguous_diagnostic"))
def test_receipt_rejects_boolean_one_for_integer_counts(aggregate, field):
    aggregate["counts"][field] = True
    with pytest.raises(module.HistoricalSourceViewError):
        module._validate_receipt(aggregate)


@pytest.mark.parametrize("field", tuple(base._COUNTS))
def test_receipt_rejects_float_values_in_each_integer_count_bucket(aggregate, field):
    aggregate["counts"][field] = float(aggregate["counts"][field])
    with pytest.raises(module.HistoricalSourceViewError):
        module._validate_receipt(aggregate)


@pytest.mark.parametrize("field", tuple(base._AUTHORITY))
def test_receipt_refuses_equal_valued_wrong_authority_scalar_types(aggregate, field):
    original = aggregate["authority"][field]
    aggregate["authority"][field] = 0 if type(original) is bool else False
    with pytest.raises(module.HistoricalSourceViewError):
        module._validate_receipt(aggregate)


@pytest.mark.parametrize("field", ("current_validator_equality_required", "historical_environment_recreated",
                                   "frozen_files_may_be_thawed"))
def test_receipt_requires_boolean_false_limitation_flags(aggregate, field):
    aggregate[field] = 0
    with pytest.raises(module.HistoricalSourceViewError):
        module._validate_receipt(aggregate)


@pytest.mark.parametrize("field", ("os_network_denied", "os_file_writes_denied", "os_process_fork_denied",
                                   "audit_additional_processes_denied", "source_only_lane_imports"))
def test_receipt_requires_boolean_true_isolation_flags(aggregate, field):
    aggregate["isolation"][field] = 1
    with pytest.raises(module.HistoricalSourceViewError):
        module._validate_receipt(aggregate)


@pytest.mark.parametrize("field", ("source_union_sha256", "partial_descriptor_sha256", "diagnostic_descriptor_sha256",
                                   "v4_plan_sha256", "partition_sha256", "proposed_unattempted_inventory_sha256"))
def test_receipt_refuses_changed_frozen_retained_digest_anchors(aggregate, field):
    aggregate[field] = "0" * 64
    with pytest.raises(module.HistoricalSourceViewError):
        module._validate_receipt(aggregate)


@pytest.mark.parametrize("field,value", (
    ("ordered_read_cycles", True), ("ordered_read_cycles", 0), ("ordered_read_cycles", 513),
    ("source_read_count", True), ("source_read_count", 7), ("source_read_count", 8.0),
    ("source_read_trace_sha256", "0" * 64), ("callsite_bound", False), ("callsite_bound", 1),
    ("validator_function_name", "invented_function"), ("historical_commit", "0" * 40),
    ("historical_validator_sha256", "0" * 64),
))
def test_receipt_refuses_incomplete_or_changed_source_read_binding(aggregate, field, value):
    aggregate["source_view"][field] = value
    with pytest.raises(module.HistoricalSourceViewError):
        module._validate_receipt(aggregate)


@pytest.mark.parametrize("case", ("missing", "extra", "reordered", "wrong_sha", "wrong_path"))
def test_receipt_source_view_requires_exact_four_file_proof_schema(aggregate, case):
    proof = aggregate["source_view"]
    if case == "missing":
        del proof["source_read_count"]
    elif case == "extra":
        proof["invented_raw_source"] = "must not serialize"
    elif case == "reordered":
        proof["files"].reverse()
    elif case == "wrong_sha":
        proof["files"][0]["sha256"] = "0" * 64
    else:
        proof["files"][0]["path"] = "research/invented.py"
    with pytest.raises(module.HistoricalSourceViewError):
        module._validate_receipt(aggregate)


@pytest.mark.parametrize("case", ("worker_missing", "base_missing", "worker_hash", "base_hash", "worker_kind",
                                  "base_kind", "historical_missing", "historical_kind", "historical_hash",
                                  "repeated", "extra_field"))
def test_receipt_requires_executed_historical_modules_and_both_current_wrapper_bindings(aggregate, case):
    trace = aggregate["executed_modules"]
    worker = next(row for row in trace if row["path"] == module._WORKER_PATH)
    previous = next(row for row in trace if row["path"] == module._BASE_PATH)
    if case == "worker_missing":
        trace.remove(worker)
    elif case == "base_missing":
        trace.remove(previous)
    elif case == "worker_hash":
        worker["sha256"] = "0" * 64
    elif case == "base_hash":
        previous["sha256"] = "0" * 64
    elif case == "worker_kind":
        worker["source_kind"] = "historical_git_blob"
    elif case == "base_kind":
        previous["source_kind"] = "historical_git_blob"
    elif case == "historical_missing":
        trace.pop(0)
    elif case == "historical_kind":
        trace[0]["source_kind"] = "current_source_snapshot"
    elif case == "historical_hash":
        trace[0]["sha256"] = "0" * 64
    elif case == "repeated":
        trace.append(dict(trace[0]))
    else:
        trace[0]["raw_locator"] = "/invented/private/source.py"
    with pytest.raises(module.HistoricalSourceViewError):
        module._validate_receipt(aggregate)


@pytest.mark.parametrize("field,value", (
    ("total_parents", 99393), ("source_bound_count", 19527), ("v3_attempt_count", 1846),
    ("v3_completed_count", 1847), ("diagnostic_body_size_bytes", True),
    ("repository_head", "not a commit"), ("worker_bootstrap_sha256", "0" * 64),
    ("historical_function_paths", []), ("worker_source_sha256", "not a hash"),
    ("historical_commit", "0" * 40), ("historical_validator_sha256", "0" * 64),
    ("diagnostic_report_sha256", "0" * 64), ("diagnostic_body_sha256", "0" * 64),
    ("raw_parent_locator", "/invented/private/retained-root"),
))
def test_receipt_rejects_changed_schema_scalar_and_lineage_anchors(aggregate, field, value):
    aggregate[field] = value
    with pytest.raises(module.HistoricalSourceViewError):
        module._validate_receipt(aggregate)


def test_sealed_receipt_copies_payload_and_refuses_reconstruction_or_changed_factory_bytes(aggregate):
    original = copy.deepcopy(aggregate)
    receipt = module._seal(aggregate)
    aggregate["counts"]["v3_completed"] = 0
    detached = receipt.to_payload()
    assert detached == original
    assert receipt.sha256 == hash_bytes(base._canonical(original))
    detached["authority"]["dispatch_enabled"] = True
    detached["source_view"]["files"][0]["sha256"] = "0" * 64
    assert receipt.to_payload() == original
    with pytest.raises(module.HistoricalSourceViewError):
        replace(receipt).to_payload()
    mutated = base._canonical(detached)
    with pytest.raises(module.HistoricalSourceViewError):
        replace(receipt, _raw=mutated, _sha256=hash_bytes(mutated)).to_payload()
    object.__setattr__(receipt, "_factory_raw", mutated)
    with pytest.raises(module.HistoricalSourceViewError):
        receipt.to_payload()


@pytest.fixture
def mock_entrypoint(monkeypatch, aggregate):
    """Patch all root/worker seams; exercise only the public parent stages."""
    root = Path(__file__).resolve().parents[1]
    blobs = tuple((path, (root / path).read_bytes()) for path, _ in base.HISTORICAL_FILES)
    executor = b"invented executor capture; never executed"
    diagnostic = b"invented diagnostic capture; never executed"
    state = SimpleNamespace(head=aggregate["repository_head"], aggregate=aggregate,
                            blobs=blobs, calls=[], unchanged_calls=[], retained_calls=[])
    state.sources = (*blobs, (base.DIAGNOSTIC_CAPTURE_PATH, diagnostic),
                     (module._WORKER_PATH, (root / module._WORKER_PATH).read_bytes()),
                     (module._BASE_PATH, (root / module._BASE_PATH).read_bytes()))

    def update_sources(sources):
        state.sources = sources
        aggregate["current_source_inventory_sha256"] = base._digest([
            {"path": path, "sha256": hash_bytes(raw)} for path, raw in sources])

    update_sources(state.sources)
    state.update_sources = update_sources
    monkeypatch.setattr(base, "EXECUTOR_SHA256", hash_bytes(executor))

    def fake_git(*args):
        assert args[:2] == ("cat-file", "blob")
        commit, path = args[2].split(":", 1)
        if path == base.EXECUTOR_PATH:
            assert commit == base.HISTORICAL_COMMIT
            return executor
        if path == base.DIAGNOSTIC_CAPTURE_PATH:
            assert commit == base.DIAGNOSTIC_CAPTURE_COMMIT
            return diagnostic
        assert commit == base.HISTORICAL_COMMIT
        return dict(blobs)[path]

    def fake_worker(raw, timeout_seconds):
        assert type(timeout_seconds) is int and 1 <= timeout_seconds <= 600
        bundle = json.loads(raw)
        assert bundle["repository_head"] == state.head
        assert base._decode_sources(bundle["historical_sources"]) == blobs
        assert base._decode_sources(bundle["current_sources"]) == state.sources
        state.calls.append((raw, timeout_seconds))
        return SimpleNamespace(returncode=0, stdout=base._canonical(aggregate))

    def never_retained_worker(*args, **kwargs):
        state.retained_calls.append(True)
        pytest.fail("mock entrypoint reached retained-root worker")

    monkeypatch.setattr(base, "_git", fake_git)
    monkeypatch.setattr(base, "_source_snapshot", lambda: state.sources)
    monkeypatch.setattr(base, "_repository_snapshot", lambda: (state.head, ""))
    monkeypatch.setattr(base, "_assert_sources_unchanged", lambda rows: state.unchanged_calls.append(rows))
    monkeypatch.setattr(module, "_worker_main", never_retained_worker)
    monkeypatch.setattr(module, "_run_isolated_worker", fake_worker)
    yield state
    assert not state.retained_calls


def test_public_entrypoint_seals_only_the_validated_mocked_worker_payload(mock_entrypoint):
    state = mock_entrypoint
    receipt = module.run_observed_historical_source_view_replay(expected_head=state.head)
    assert receipt.to_payload() == state.aggregate
    assert len(state.calls) == 1
    assert state.unchanged_calls == [state.sources, state.sources]


@pytest.mark.parametrize("path", [path for path, _ in base.HISTORICAL_FILES])
def test_current_validator_drift_is_not_an_equality_gate_but_historical_execution_stays_pinned(mock_entrypoint, path):
    state = mock_entrypoint
    changed = tuple((relative, raw + b"\n# invented live drift\n" if relative == path else raw)
                    for relative, raw in state.sources)
    state.update_sources(changed)
    receipt = module.run_observed_historical_source_view_replay(expected_head=state.head)
    assert len(state.calls) == 1
    payload = receipt.to_payload()
    assert payload["current_validator_equality_required"] is False
    assert {row["path"]: row["sha256"] for row in payload["executed_modules"]
            if row["source_kind"] == "historical_git_blob"} == dict(base.HISTORICAL_FILES)
    bundle = json.loads(state.calls[0][0])
    assert dict(base._decode_sources(bundle["historical_sources"]))[path] != dict(
        base._decode_sources(bundle["current_sources"]))[path]


@pytest.mark.parametrize("timeout", (True, 0, -1, 601, 1.0, "1", None))
def test_public_entrypoint_timeout_refuses_before_any_mocked_worker(mock_entrypoint, timeout):
    with pytest.raises(module.HistoricalSourceViewError, match="timeout"):
        module.run_observed_historical_source_view_replay(expected_head=mock_entrypoint.head,
                                                         timeout_seconds=timeout)
    assert not mock_entrypoint.calls


@pytest.mark.parametrize("case", ("missing", "not_executable"))
def test_public_entrypoint_has_no_unsandboxed_fallback(mock_entrypoint, monkeypatch, case):
    sandbox = Path("/usr/bin/sandbox-exec")
    if case == "missing":
        original = Path.is_file
        monkeypatch.setattr(Path, "is_file", lambda path: False if path == sandbox else original(path))
    else:
        original = module.os.access
        monkeypatch.setattr(module.os, "access", lambda path, mode: False if path == sandbox else original(path, mode))
    with pytest.raises(module.HistoricalSourceViewError, match="sandbox"):
        module.run_observed_historical_source_view_replay(expected_head=mock_entrypoint.head)
    assert not mock_entrypoint.calls


@pytest.mark.parametrize("expected", ("0" * 40, "f" * 39, b"f" * 40, None))
def test_public_entrypoint_requires_exact_reviewed_head(mock_entrypoint, expected):
    with pytest.raises(module.HistoricalSourceViewError, match="HEAD"):
        module.run_observed_historical_source_view_replay(expected_head=expected)
    assert not mock_entrypoint.calls


@pytest.mark.parametrize("status", (
    "", " M research/insider_buying_sec_recovery_v4_source_view.py\n",
    "?? tests/test_insider_buying_sec_recovery_v4_source_view.py\n",
    " M tests/test_insider_buying_sec_recovery_v4_historical_replay.py\n",
    ' M "docs/Strategy Description/INSIDER_BUYING_IMPLEMENTATION_RECORD.md"\n',
))
def test_new_context_accepts_only_the_bounded_round_dirty_paths(status):
    module._validate_context(("f" * 40, status), "f" * 40)


@pytest.mark.parametrize("status", (
    "R  research/a.py -> research/insider_buying_sec_recovery_v4_source_view.py\n",
    "C  research/a.py -> tests/test_insider_buying_sec_recovery_v4_source_view.py\n",
    "?? tests/test_insider_buying_sec_recovery_v4_source_view.py.orig\n",
    " M research/insider_buying_sec_recovery_v4_historical_replay.py\n",
    " M research/insider_buying_sec_all_form4_parent_campaign.py\n", "M\n",
))
def test_new_context_refuses_old_wrapper_frozen_files_and_unrelated_changes(status):
    with pytest.raises(module.HistoricalSourceViewError):
        module._validate_context(("f" * 40, status), "f" * 40)


@pytest.mark.parametrize("phase,field", ((2, "head"), (2, "status"), (3, "head"), (3, "status")))
def test_public_entrypoint_rechecks_exact_context_before_and_after_worker(mock_entrypoint, monkeypatch, phase, field):
    seen = 0

    def snapshot():
        nonlocal seen
        seen += 1
        if seen == phase:
            return ("0" * 40, "") if field == "head" else (mock_entrypoint.head, " M unrelated.py\n")
        return mock_entrypoint.head, ""

    monkeypatch.setattr(base, "_repository_snapshot", snapshot)
    with pytest.raises(module.HistoricalSourceViewError, match="context"):
        module.run_observed_historical_source_view_replay(expected_head=mock_entrypoint.head)
    assert len(mock_entrypoint.calls) == int(phase == 3)


def test_public_entrypoint_rechecks_captured_current_sources_after_worker(mock_entrypoint, monkeypatch):
    seen = 0

    def unchanged(rows):
        nonlocal seen
        seen += 1
        assert rows == mock_entrypoint.sources
        if seen == 2:
            raise base.HistoricalReplayError("invented post-worker source drift")

    monkeypatch.setattr(base, "_assert_sources_unchanged", unchanged)
    with pytest.raises(module.HistoricalSourceViewError):
        module.run_observed_historical_source_view_replay(expected_head=mock_entrypoint.head)
    assert len(mock_entrypoint.calls) == 1


@pytest.mark.parametrize("case", ("worker_missing", "base_missing", "worker_outside", "base_outside", "diagnostic_drift"))
def test_public_entrypoint_requires_both_wrapper_origins_and_frozen_diagnostic_capture(mock_entrypoint, monkeypatch, case):
    state = mock_entrypoint
    if case == "worker_missing":
        state.update_sources(tuple(row for row in state.sources if row[0] != module._WORKER_PATH))
    elif case == "base_missing":
        state.update_sources(tuple(row for row in state.sources if row[0] != module._BASE_PATH))
    elif case == "worker_outside":
        monkeypatch.setattr(module, "__file__", "/invented/elsewhere/source_view.py")
    elif case == "base_outside":
        monkeypatch.setattr(base, "__file__", "/invented/elsewhere/historical_replay.py")
    else:
        state.update_sources(tuple((path, raw + b"\n" if path == base.DIAGNOSTIC_CAPTURE_PATH else raw)
                                   for path, raw in state.sources))
    with pytest.raises(module.HistoricalSourceViewError):
        module.run_observed_historical_source_view_replay(expected_head=state.head)
    assert not state.calls


@pytest.mark.parametrize("case", ("wrong_head", "unknown_source", "wrong_current_hash", "wrong_inventory",
                                  "wrong_worker", "wrong_base", "wrong_bootstrap", "failed", "oversized", "invalid_json"))
def test_public_entrypoint_refuses_changed_mocked_worker_envelopes(mock_entrypoint, monkeypatch, case):
    state = mock_entrypoint
    payload = copy.deepcopy(state.aggregate)
    if case == "wrong_head":
        payload["repository_head"] = "0" * 40
    elif case == "unknown_source":
        payload["executed_modules"].append({"path": "research/invented.py", "sha256": "0" * 64,
                                             "source_kind": "current_source_snapshot"})
    elif case == "wrong_current_hash":
        payload["executed_modules"].append({"path": base.DIAGNOSTIC_CAPTURE_PATH, "sha256": "0" * 64,
                                             "source_kind": "current_source_snapshot"})
    elif case == "wrong_inventory":
        payload["current_source_inventory_sha256"] = "0" * 64
    elif case in ("wrong_worker", "wrong_base"):
        path, key = ((module._WORKER_PATH, "worker_source_sha256") if case == "wrong_worker" else
                     (module._BASE_PATH, "base_source_sha256"))
        payload[key] = "0" * 64
        next(row for row in payload["executed_modules"] if row["path"] == path)["sha256"] = "0" * 64
    elif case == "wrong_bootstrap":
        payload["worker_bootstrap_sha256"] = "0" * 64
    raw = (b"x" * (base._MAX_OUTPUT_BYTES + 1) if case == "oversized" else
           b"not json" if case == "invalid_json" else base._canonical(payload))
    monkeypatch.setattr(module, "_run_isolated_worker", lambda *args, **kwargs: SimpleNamespace(
        returncode=1 if case == "failed" else 0, stdout=raw))
    with pytest.raises(module.HistoricalSourceViewError):
        module.run_observed_historical_source_view_replay(expected_head=state.head)


@pytest.mark.parametrize("raw", (b"", "text", bytearray(b"invented"), b"12345"))
def test_child_runner_invalid_input_refuses_before_launch(raw, monkeypatch):
    monkeypatch.setattr(base, "_MAX_INPUT_BYTES", 4)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("launched"))
    with pytest.raises(module.HistoricalSourceViewError, match="input"):
        module._run_isolated_worker(raw, 30)


@pytest.mark.parametrize("timeout", (True, 0, -1, 601, 1.0, "1", None))
def test_child_runner_invalid_timeout_refuses_before_launch(timeout, monkeypatch):
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("launched"))
    with pytest.raises(module.HistoricalSourceViewError, match="timeout"):
        module._run_isolated_worker(b"invented", timeout)


def test_public_entrypoint_refuses_an_oversized_source_bundle_before_mocked_worker(mock_entrypoint, monkeypatch):
    monkeypatch.setattr(base, "_MAX_INPUT_BYTES", 1)
    with pytest.raises(module.HistoricalSourceViewError, match="cap"):
        module.run_observed_historical_source_view_replay(expected_head=mock_entrypoint.head)
    assert not mock_entrypoint.calls
