from __future__ import annotations

import ast
import dataclasses
import json
import subprocess
from pathlib import Path

import pytest

from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    sha256_bytes,
)
from research.analyst_revisions_v2.dataset import (
    DATASET_MANIFEST_FILENAME,
    EVENTS_FILENAME,
    REFUSALS_FILENAME,
    DatasetVerificationError,
    capture_clean_git_lineage,
    compute_package_source_sha256,
    load_normalized_dataset,
    publish_normalized_dataset,
    revalidate_normalized_dataset,
)
from research.analyst_revisions_v2.contracts import EventState, RevisionKind
from research.analyst_revisions_v2.import_firewall import (
    ImportBoundaryError,
    validate_transitive_import_closure,
)
from research.analyst_revisions_v2.normalization import (
    NormalizationContractError,
    NormalizationProvenance,
    NormalizationResult,
    RefusalReason,
)

from ._helpers import (
    clean_source_repository,
    event_for,
    historical_event_for,
    refusal_for,
    result_for,
    verified_snapshot,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


def _derive_dataset_id(manifest: dict) -> str:
    payload = dict(manifest)
    payload.pop("dataset_id", None)
    return "arv2_ds_" + sha256_bytes(canonical_json_bytes(payload))


def _rewrite_manifest(dataset_root: Path, manifest: dict) -> None:
    manifest["dataset_id"] = _derive_dataset_id(manifest)
    (dataset_root / DATASET_MANIFEST_FILENAME).write_bytes(
        canonical_json_bytes(manifest)
    )


def _published_fixture(tmp_path: Path, *, event_count: int = 2):
    repository, lineage, code_hash = clean_source_repository(tmp_path, WORKSPACE_ROOT)
    snapshot = verified_snapshot(
        tmp_path / "snapshot",
        row_count=event_count,
        refusal_row_indices=frozenset(range(event_count)),
    )
    refusals = tuple(
        refusal_for(
            locator,
            code_hash=code_hash,
            producing_commit=lineage.producing_commit,
        )
        for locator in snapshot.source_locators
    )
    result = result_for(
        snapshot,
        events=(),
        refusals=refusals,
        code_hash=code_hash,
        producing_commit=lineage.producing_commit,
    )
    dataset_root = tmp_path / "dataset"
    manifest = publish_normalized_dataset(
        dataset_root, result=result, lineage=lineage
    )
    return repository, lineage, snapshot, result, dataset_root, manifest


def test_dataset_publication_and_typed_round_trip(tmp_path):
    _, lineage, snapshot, result, dataset_root, manifest = _published_fixture(tmp_path)
    loaded = load_normalized_dataset(dataset_root, snapshot=snapshot)

    assert loaded.manifest == manifest
    assert loaded.events == result.events
    assert loaded.refusals == result.refusals
    assert loaded.manifest.producing_commit == lineage.producing_commit
    assert loaded.manifest.producing_tree == lineage.producing_tree
    with pytest.raises(dataclasses.FrozenInstanceError):
        loaded.manifest.event_count = 0


def test_refusal_only_dataset_is_complete_and_round_trips(tmp_path):
    repository, lineage, code_hash = clean_source_repository(tmp_path, WORKSPACE_ROOT)
    snapshot = verified_snapshot(
        tmp_path / "snapshot", refusal_row_indices=frozenset({0})
    )
    refusal = refusal_for(
        snapshot.source_locators[0],
        code_hash=code_hash,
        producing_commit=lineage.producing_commit,
    )
    result = result_for(
        snapshot,
        events=(),
        refusals=(refusal,),
        code_hash=code_hash,
        producing_commit=lineage.producing_commit,
    )
    dataset_root = tmp_path / "refusal-dataset"
    publish_normalized_dataset(dataset_root, result=result, lineage=lineage)
    loaded = load_normalized_dataset(dataset_root, snapshot=snapshot)
    assert loaded.events == ()
    assert loaded.refusals == (refusal,)
    assert repository.is_dir()


@pytest.mark.parametrize(
    "mutation",
    ("ids", "times", "mapping", "rating", "analyst", "revision"),
)
def test_publication_rejects_arbitrary_canonical_event_substitution(
    tmp_path, mutation
):
    _, lineage, code_hash = clean_source_repository(tmp_path, WORKSPACE_ROOT)
    snapshot = verified_snapshot(tmp_path / "snapshot")
    locator = snapshot.source_locators[0]
    common = {
        "code_hash": code_hash,
        "producing_commit": lineage.producing_commit,
    }
    if mutation == "ids":
        event = event_for(
            locator, provider_event_id="caller-selected-event", **common
        )
    elif mutation == "times":
        event = event_for(
            locator, effective_at="2020-01-01T14:00:00.000000Z", **common
        )
    elif mutation == "mapping":
        event = event_for(locator, issuer_id="caller-selected-issuer", **common)
    elif mutation == "rating":
        event = event_for(locator, raw_rating="Caller Selected Rating", **common)
    elif mutation == "analyst":
        event = dataclasses.replace(
            event_for(locator, **common),
            provider_analyst_id="caller-provider-analyst",
            analyst_id="caller-analyst",
        )
    else:
        event = event_for(
            locator,
            event_version_id="caller-version-1",
            revision_sequence=1,
            supersedes_event_version_id="caller-version-0",
            revision_kind=RevisionKind.CORRECTION,
            event_state=EventState.ACTIVE_CORRECTED,
            **common,
        )
    provenance = NormalizationProvenance.create(
        snapshot=snapshot,
        normalizer_config_sha256="1" * 64,
        normalizer_code_sha256=code_hash,
        evidence_epoch_id="evidence-epoch-1",
        build_recipe_id="normalizer-recipe-1",
        producing_commit=lineage.producing_commit,
    )
    forged = object.__new__(NormalizationResult)
    object.__setattr__(forged, "snapshot", snapshot)
    object.__setattr__(forged, "events", (event,))
    object.__setattr__(forged, "refusals", ())
    object.__setattr__(forged, "provenance", provenance)
    target = tmp_path / f"forged-{mutation}"
    with pytest.raises(NormalizationContractError, match="zero-access"):
        publish_normalized_dataset(target, result=forged, lineage=lineage)
    assert not target.exists()


def test_pre_2013_named_refusal_round_trips_but_event_artifact_is_rejected(
    tmp_path,
):
    _, lineage, code_hash = clean_source_repository(tmp_path, WORKSPACE_ROOT)
    snapshot = verified_snapshot(
        tmp_path / "pre-2013-snapshot", event_year=2012
    )
    refusal = refusal_for(
        snapshot.source_locators[0],
        reason=(
            RefusalReason.PROVIDER_BACKFILL_SEMANTICS_UNVERIFIED_PRE_2013
        ),
        code_hash=code_hash,
        producing_commit=lineage.producing_commit,
    )
    result = result_for(
        snapshot,
        events=(),
        refusals=(refusal,),
        code_hash=code_hash,
        producing_commit=lineage.producing_commit,
    )
    dataset_root = tmp_path / "pre-2013-dataset"
    publish_normalized_dataset(dataset_root, result=result, lineage=lineage)
    assert load_normalized_dataset(
        dataset_root, snapshot=snapshot
    ).refusals == (refusal,)

    forbidden_event = historical_event_for(
        snapshot.source_locators[0],
        event_year=2012,
        code_hash=code_hash,
        producing_commit=lineage.producing_commit,
    )
    event_payload = canonical_json_bytes(forbidden_event.to_record())
    refusal_payload = b""
    (dataset_root / EVENTS_FILENAME).write_bytes(event_payload)
    (dataset_root / REFUSALS_FILENAME).write_bytes(refusal_payload)
    manifest = json.loads(
        (dataset_root / DATASET_MANIFEST_FILENAME).read_text(encoding="utf-8")
    )
    manifest["events_sha256"] = sha256_bytes(event_payload)
    manifest["event_count"] = 1
    manifest["refusals_sha256"] = sha256_bytes(refusal_payload)
    manifest["refusal_count"] = 0
    _rewrite_manifest(dataset_root, manifest)

    with pytest.raises(NormalizationContractError, match="zero-access"):
        load_normalized_dataset(dataset_root, snapshot=snapshot)


def test_publication_refuses_dirty_or_changed_git_lineage(tmp_path):
    repository, lineage, snapshot, result, _, _ = _published_fixture(tmp_path)
    (repository / "untracked-after-capture.txt").write_text("dirty", encoding="utf-8")

    with pytest.raises(DatasetVerificationError, match="not clean"):
        publish_normalized_dataset(
            tmp_path / "second-dataset", result=result, lineage=lineage
        )
    assert not (tmp_path / "second-dataset").exists()
    assert snapshot.source_row_count == 2


def test_ignored_python_source_cannot_hide_outside_the_producing_commit(tmp_path):
    repository, _, _ = clean_source_repository(tmp_path, WORKSPACE_ROOT)
    info_exclude = repository / ".git" / "info" / "exclude"
    info_exclude.write_text(
        info_exclude.read_text(encoding="utf-8") + "\nignored_source.py\n",
        encoding="utf-8",
    )
    ignored = repository / "research" / "analyst_revisions_v2" / "ignored_source.py"
    ignored.write_text("VALUE = 1\n", encoding="utf-8")
    capture_clean_git_lineage(repository)
    with pytest.raises(DatasetVerificationError, match="untracked_or_ignored"):
        compute_package_source_sha256(repository)


def test_publication_refuses_code_hash_or_commit_not_bound_to_clean_source(tmp_path):
    _, lineage, code_hash = clean_source_repository(tmp_path, WORKSPACE_ROOT)
    wrong_code = "9" * 64
    snapshot = verified_snapshot(
        tmp_path / "snapshot",
        refusal_row_indices=frozenset({0}),
    )
    refusal = refusal_for(
        snapshot.source_locators[0],
        code_hash=wrong_code,
        producing_commit=lineage.producing_commit,
    )
    result = result_for(
        snapshot,
        events=(),
        refusals=(refusal,),
        code_hash=wrong_code,
        producing_commit=lineage.producing_commit,
    )
    assert code_hash != wrong_code
    with pytest.raises(DatasetVerificationError, match="package source"):
        publish_normalized_dataset(tmp_path / "dataset", result=result, lineage=lineage)

    wrong_commit = "b" * 40
    refusal = refusal_for(
        snapshot.source_locators[0],
        code_hash=code_hash,
        producing_commit=wrong_commit,
    )
    result = result_for(
        snapshot,
        events=(),
        refusals=(refusal,),
        code_hash=code_hash,
        producing_commit=wrong_commit,
    )
    with pytest.raises(DatasetVerificationError, match="commit"):
        publish_normalized_dataset(tmp_path / "dataset", result=result, lineage=lineage)


def test_publication_never_overwrites_an_existing_dataset(tmp_path):
    _, lineage, _, result, dataset_root, _ = _published_fixture(tmp_path)
    original_manifest = (dataset_root / DATASET_MANIFEST_FILENAME).read_bytes()
    with pytest.raises(DatasetVerificationError, match="already exists"):
        publish_normalized_dataset(dataset_root, result=result, lineage=lineage)
    assert (dataset_root / DATASET_MANIFEST_FILENAME).read_bytes() == original_manifest


def test_config_hash_changes_build_recipe_result_and_dataset_identity(tmp_path):
    _, lineage, snapshot, result, _, first_manifest = _published_fixture(tmp_path)
    changed_config = "8" * 64
    changed_refusals = tuple(
        refusal_for(
            locator,
            config_hash=changed_config,
            code_hash=result.provenance.normalizer_code_sha256,
            producing_commit=lineage.producing_commit,
        )
        for locator in snapshot.source_locators
    )
    changed_result = result_for(
        snapshot,
        events=(),
        refusals=changed_refusals,
        config_hash=changed_config,
        code_hash=result.provenance.normalizer_code_sha256,
        producing_commit=lineage.producing_commit,
    )
    second_manifest = publish_normalized_dataset(
        tmp_path / "changed-config-dataset",
        result=changed_result,
        lineage=lineage,
    )
    assert changed_result.provenance.build_recipe_sha256 != result.provenance.build_recipe_sha256
    assert changed_result.result_sha256 != result.result_sha256
    assert second_manifest.dataset_id != first_manifest.dataset_id


def test_failed_publication_has_no_visible_partial_dataset(tmp_path, monkeypatch):
    import research.analyst_revisions_v2.dataset as dataset_module

    _, lineage, code_hash = clean_source_repository(tmp_path, WORKSPACE_ROOT)
    snapshot = verified_snapshot(
        tmp_path / "snapshot", refusal_row_indices=frozenset({0})
    )
    refusal = refusal_for(
        snapshot.source_locators[0],
        code_hash=code_hash,
        producing_commit=lineage.producing_commit,
    )
    result = result_for(
        snapshot,
        events=(),
        refusals=(refusal,),
        code_hash=code_hash,
        producing_commit=lineage.producing_commit,
    )
    real_write = dataset_module._write_new_file
    calls = 0

    def fail_second_write(path, payload):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated persistence failure")
        return real_write(path, payload)

    monkeypatch.setattr(dataset_module, "_write_new_file", fail_second_write)
    target = tmp_path / "atomic-dataset"
    with pytest.raises(OSError, match="simulated"):
        publish_normalized_dataset(target, result=result, lineage=lineage)
    assert not target.exists()
    assert list(tmp_path.glob(".atomic-dataset.tmp-*")) == []


@pytest.mark.parametrize(
    "mutation,match",
    [
        ("unknown_manifest_key", "keys are not exact"),
        ("wrong_snapshot", "supplied snapshot"),
        ("wrong_result_hash", "result hash"),
        ("old_schema", "unsupported"),
    ],
)
def test_manifest_schema_snapshot_and_result_bindings_are_strict(
    tmp_path, mutation, match
):
    _, _, snapshot, _, dataset_root, _ = _published_fixture(tmp_path)
    manifest = json.loads(
        (dataset_root / DATASET_MANIFEST_FILENAME).read_text(encoding="utf-8")
    )
    if mutation == "unknown_manifest_key":
        manifest["legacy_field"] = "forbidden"
    elif mutation == "wrong_snapshot":
        manifest["snapshot_id"] = "another-snapshot"
    elif mutation == "wrong_result_hash":
        manifest["normalization_result_sha256"] = "f" * 64
    else:
        manifest["schema"] = "arv2-event-dataset-v0"
    _rewrite_manifest(dataset_root, manifest)

    with pytest.raises(CanonicalEvidenceError, match=match):
        load_normalized_dataset(dataset_root, snapshot=snapshot)


@pytest.mark.parametrize(
    "mutation,match",
    [
        ("unknown_refusal_key", "keys are not exact"),
        ("noncanonical_json", "canonical"),
        ("out_of_order", "source-sorted"),
        ("duplicate_refusal", "more than one terminal disposition"),
    ],
)
def test_jsonl_rows_are_exact_canonical_sorted_and_unique(tmp_path, mutation, match):
    _, _, snapshot, _, dataset_root, _ = _published_fixture(tmp_path)
    event_path = dataset_root / REFUSALS_FILENAME
    rows = [
        json.loads(line)
        for line in event_path.read_text(encoding="utf-8").splitlines()
    ]
    if mutation == "unknown_refusal_key":
        rows[0]["legacy_reason"] = rows[0]["reason"]
        payload = b"".join(canonical_json_bytes(row) for row in rows)
    elif mutation == "noncanonical_json":
        payload = b"".join(
            (json.dumps(row, sort_keys=True) + "\n").encode("utf-8") for row in rows
        )
    elif mutation == "out_of_order":
        payload = b"".join(canonical_json_bytes(row) for row in reversed(rows))
    else:
        payload = canonical_json_bytes(rows[0]) + canonical_json_bytes(rows[0])
    event_path.write_bytes(payload)
    manifest = json.loads(
        (dataset_root / DATASET_MANIFEST_FILENAME).read_text(encoding="utf-8")
    )
    manifest["refusals_sha256"] = sha256_bytes(payload)
    _rewrite_manifest(dataset_root, manifest)

    with pytest.raises(CanonicalEvidenceError, match=match):
        load_normalized_dataset(dataset_root, snapshot=snapshot)


def test_loader_hashes_before_parsing_and_rejects_unreferenced_files(tmp_path):
    _, _, snapshot, _, dataset_root, _ = _published_fixture(tmp_path)
    event_path = dataset_root / EVENTS_FILENAME
    event_path.write_bytes(b"not-json\n")
    with pytest.raises(DatasetVerificationError, match="hash mismatch"):
        load_normalized_dataset(dataset_root, snapshot=snapshot)

    _, _, snapshot, _, dataset_root, _ = _published_fixture(
        tmp_path / "second"
    )
    (dataset_root / "unreferenced.jsonl").write_bytes(b"")
    with pytest.raises(DatasetVerificationError, match="inventory"):
        load_normalized_dataset(dataset_root, snapshot=snapshot)


def test_normalized_dataset_is_loader_only_and_revalidates_all_content(tmp_path):
    _, _, snapshot, _, dataset_root, _ = _published_fixture(tmp_path)
    dataset = load_normalized_dataset(dataset_root, snapshot=snapshot)
    with pytest.raises(TypeError):
        dataclasses.replace(dataset, events=())

    clone = object.__new__(type(dataset))
    for field in dataclasses.fields(dataset):
        object.__setattr__(clone, field.name, getattr(dataset, field.name))
    with pytest.raises(DatasetVerificationError, match="loader-authenticated"):
        revalidate_normalized_dataset(clone)

    event_path = dataset_root / EVENTS_FILENAME
    event_path.write_bytes(event_path.read_bytes() + b"{}\n")
    with pytest.raises(DatasetVerificationError, match="hash mismatch|changed"):
        revalidate_normalized_dataset(dataset)


def test_publication_revalidates_result_instead_of_trusting_frozen_shell(tmp_path):
    _, lineage, _, result, _, _ = _published_fixture(tmp_path)
    object.__setattr__(result, "refusals", ())
    with pytest.raises(NormalizationContractError, match="exactly cover"):
        _ = result.result_sha256
    with pytest.raises(NormalizationContractError, match="exactly cover"):
        publish_normalized_dataset(
            tmp_path / "forged-erasure-dataset", result=result, lineage=lineage
        )


def test_current_v2_package_transitive_import_closure_is_outcome_free():
    reached = validate_transitive_import_closure(WORKSPACE_ROOT)
    assert "research.analyst_revisions_v2.dataset" in reached
    assert "research.analyst_revisions_v2.stock_signal" in reached
    assert "data.exchange_calendar" in reached
    assert "execution" not in reached
    assert "research.acer" not in reached


def test_safe_looking_facade_cannot_hide_a_forbidden_transitive_import(tmp_path):
    package = tmp_path / "guarded"
    package.mkdir()
    (package / "__init__.py").write_text("from . import facade\n", encoding="utf-8")
    (package / "facade.py").write_text("from . import safe_helper\n", encoding="utf-8")
    (package / "safe_helper.py").write_text("import execution.orders\n", encoding="utf-8")

    with pytest.raises(ImportBoundaryError) as captured:
        validate_transitive_import_closure(tmp_path, package_name="guarded")
    message = str(captured.value)
    assert "guarded.facade" in message
    assert "guarded.safe_helper" in message
    assert "execution.orders" in message


def test_imported_parent_package_initializer_is_part_of_the_closure(tmp_path):
    guarded = tmp_path / "guarded"
    guarded.mkdir()
    (guarded / "__init__.py").write_text(
        "import facade_package.safe\n", encoding="utf-8"
    )
    facade = tmp_path / "facade_package"
    facade.mkdir()
    (facade / "__init__.py").write_text("import http.client\n", encoding="utf-8")
    (facade / "safe.py").write_text("VALUE = 1\n", encoding="utf-8")

    with pytest.raises(ImportBoundaryError) as captured:
        validate_transitive_import_closure(tmp_path, package_name="guarded")
    assert "facade_package" in str(captured.value)
    assert "http.client" in str(captured.value)


@pytest.mark.parametrize(
    "source",
    [
        "import importlib\nimportlib.import_module('requests.sessions')\n",
        "from importlib import import_module\nname = 'requests'\nimport_module(name)\n",
    ],
)
def test_dynamic_imports_cannot_bypass_the_firewall(tmp_path, source):
    package = tmp_path / "guarded"
    package.mkdir()
    (package / "__init__.py").write_text(source, encoding="utf-8")
    with pytest.raises(ImportBoundaryError):
        validate_transitive_import_closure(tmp_path, package_name="guarded")


def _authority_registry_names(tree: ast.Module) -> set[str]:
    """Module-level names bound to an out-of-band authority registry dict."""
    names: set[str] = set()
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if (
                isinstance(target, ast.Name)
                and target.id.endswith("_AUTHORITIES")
                and isinstance(node.value, ast.Dict)
            ):
                names.add(target.id)
    return names


def _module_assignment_value(tree: ast.Module, name: str) -> ast.expr | None:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                return node.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                return node.value
    return None


def _unguarded_registry_access_lines(tree: ast.Module, registry: str) -> list[int]:
    """Return non-declaration registry accesses outside its matching lock."""
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    declaration_targets = {
        target
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in (
            node.targets if isinstance(node, ast.Assign) else [node.target]
        )
        if isinstance(target, ast.Name) and target.id == registry
    }
    lock_name = f"{registry}_LOCK"
    violations: list[int] = []
    for access in ast.walk(tree):
        if (
            not isinstance(access, ast.Name)
            or access.id != registry
            or access in declaration_targets
        ):
            continue
        ancestor = parents.get(access)
        guarded = False
        while ancestor is not None:
            if isinstance(ancestor, (ast.With, ast.AsyncWith)) and any(
                isinstance(item.context_expr, ast.Name)
                and item.context_expr.id == lock_name
                for item in ancestor.items
            ):
                guarded = True
                break
            ancestor = parents.get(ancestor)
        if not guarded:
            violations.append(access.lineno)
    return sorted(violations)


def test_every_authority_registry_is_guarded_by_its_own_lock():
    """Authority registries are the mechanism that defeats forged objects.

    Their concurrency discipline must be uniform rather than accidental: a
    weakref callback can fire on any thread during collection, and identity
    keys are reused memory addresses. CPython's GIL makes the individual dict
    operations atomic, so no runtime test can observe a missing lock; the
    invariant is therefore pinned at the source level.
    """
    package = Path(__file__).resolve().parents[2] / "research" / "analyst_revisions_v2"
    expected = {
        "dataset.py": {"_DATASET_AUTHORITIES"},
        "firm_ontology.py": {"_ONTOLOGY_AUTHORITIES"},
        "formulas.py": {"_POLICY_AUTHORITIES"},
        "holdings.py": {"_STOCK_SCORE_AUTHORITIES"},
        "preregistration.py": {"_REVIEWED_AUTHORITIES"},
        "security_master.py": {"_SECURITY_MASTER_AUTHORITIES"},
        "snapshot.py": {"_SNAPSHOT_AUTHORITIES"},
    }
    checked: dict[str, set[str]] = {}
    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        registries = _authority_registry_names(tree)
        if not registries:
            continue
        checked[path.name] = registries
        for registry in registries:
            lock_name = f"{registry}_LOCK"
            lock_value = _module_assignment_value(tree, lock_name)
            assert (
                isinstance(lock_value, ast.Call)
                and isinstance(lock_value.func, ast.Attribute)
                and isinstance(lock_value.func.value, ast.Name)
                and lock_value.func.value.id == "threading"
                and lock_value.func.attr == "RLock"
                and not lock_value.args
                and not lock_value.keywords
            ), (
                f"{path.name} must define {lock_name} as threading.RLock()"
            )
            assert not _unguarded_registry_access_lines(tree, registry), (
                f"{path.name} accesses {registry} outside with {lock_name}: "
                f"lines {_unguarded_registry_access_lines(tree, registry)}"
            )
    # Pin the inventory so a renamed/deleted registry cannot make the audit
    # silently cover less authority than it did before.
    assert checked == expected


@pytest.mark.parametrize(
    "body",
    [
        "return _TEST_AUTHORITIES.get(1)",
        "_TEST_AUTHORITIES[1] = object()",
        "_TEST_AUTHORITIES.pop(1, None)",
        "with _OTHER_LOCK:\n        return _TEST_AUTHORITIES.get(1)",
    ],
)
def test_authority_registry_guard_audit_rejects_unguarded_mutations(body):
    indented = "\n".join(f"    {line}" for line in body.splitlines())
    tree = ast.parse(
        "import threading\n"
        "_TEST_AUTHORITIES = {}\n"
        "_TEST_AUTHORITIES_LOCK = threading.RLock()\n"
        "_OTHER_LOCK = threading.RLock()\n"
        "def mutate():\n"
        f"{indented}\n"
    )
    assert _unguarded_registry_access_lines(tree, "_TEST_AUTHORITIES")


def test_authority_registry_guard_audit_accepts_the_matching_lock():
    tree = ast.parse(
        "import threading\n"
        "_TEST_AUTHORITIES = {}\n"
        "_TEST_AUTHORITIES_LOCK = threading.RLock()\n"
        "def read():\n"
        "    with _TEST_AUTHORITIES_LOCK:\n"
        "        return _TEST_AUTHORITIES.get(1)\n"
    )
    assert _unguarded_registry_access_lines(tree, "_TEST_AUTHORITIES") == []


def test_canonical_production_artifacts_survive_checkout_as_exact_bytes():
    """Production artifacts must stay LF-only and unconverted on checkout.

    All seven artifacts participate in committed-and-clean review boundaries;
    three are additionally consumed by exact-byte canonical JSON loaders. A
    Windows checkout with core.autocrlf=true can rewrite LF bytes to CRLF,
    leaving a stale clean stat cache even though the next review-anchor check
    will refuse. The directory-level ``-text`` rule and the checked-out bytes
    are therefore both part of this regression.
    """
    from research.analyst_revisions_v2.canonical import require_canonical_json_bytes

    CRLF = bytes((13, 10))  # carriage return + line feed

    specs = (
        Path(__file__).resolve().parents[2]
        / "research"
        / "analyst_revisions_v2"
        / "specs"
    )
    artifacts = {path.name: path for path in specs.glob("*.json")}
    assert artifacts, "the ARV2 spec directory must contain committed artifacts"
    repository = Path(__file__).resolve().parents[2]
    relative_artifacts = tuple(
        path.relative_to(repository).as_posix()
        for path in sorted(artifacts.values())
    )
    attributes = subprocess.run(
        ["git", "check-attr", "text", "--", *relative_artifacts],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    assert set(attributes.stdout.splitlines()) == {
        f"{path}: text: unset" for path in relative_artifacts
    }, attributes.stdout
    # `*.json -text` covers this whole directory, so CRLF is not only a
    # loader problem: Git then reports the file as permanently modified. That
    # breaks the reviewed-spec anchor's committed-and-clean precondition and
    # risks committing CRLF bytes into a content-addressed artifact, even for
    # the files whose loaders parse tolerantly.
    for name, path in sorted(artifacts.items()):
        assert CRLF not in path.read_bytes(), (
            f"{name} differs from its committed LF blob. A checkout made "
            "before `*.json -text` existed keeps its CRLF bytes, and the stat "
            "cache can hide that from `git status`. Preserve any intended "
            "edits, then restore only this named artifact's unintended EOL "
            "conversion from its committed blob; never delete the directory "
            "or commit CRLF bytes."
        )
    # Only these production-bound artifacts are additionally consumed through
    # require_canonical_json_bytes. Other JSON in this directory is parsed
    # tolerantly or compared after semantic canonicalization, so calling every
    # artifact byte-canonical would overstate its real loader contract.
    canonical_required = {
        "firm_ontology_registry.json",
        "research_source_authority.json",
        "security_master_registry.json",
    }
    present = set(artifacts)
    assert canonical_required <= present, sorted(canonical_required - present)
    for name in sorted(canonical_required):
        payload = artifacts[name].read_bytes()
        assert CRLF not in payload, (
            f"{name} was checked out with CRLF; its content identity depends "
            "on exact bytes"
        )
        raw = require_canonical_json_bytes(payload, name)
        assert raw["schema"].endswith("-v2")


def test_zero_access_declarations_are_actually_verified_not_merely_unreadable():
    """A refusal must come from the declaration, not from a parse failure.

    Both authorities refuse either way, so corruption can hide behind the same
    'refused' outcome. Assert each positive zero-access declaration directly;
    the source authority additionally exercises the byte-canonical loader.
    """
    from research.analyst_revisions_v2.formulas import (
        ZERO_ACCESS_SOURCE_AUTHORITY_ID,
        _require_zero_access_source_authority,
    )
    from research.analyst_revisions_v2.preregistration import (
        ZERO_ACCESS_AUTHORITY_ID,
        _require_zero_access_authority,
    )

    assert _require_zero_access_source_authority() == ZERO_ACCESS_SOURCE_AUTHORITY_ID
    assert _require_zero_access_authority() == ZERO_ACCESS_AUTHORITY_ID
