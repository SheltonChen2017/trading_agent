"""Offline contract tests for the QC refusal-smoke source projection."""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import inspect
import json
import sys
from functools import lru_cache
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc import (
    refusal_smoke_projection as projection_module,
)
from research.analyst_revisions_v2_qc.refusal_smoke_projection import (
    AUTHORITY,
    CAPABILITIES,
    ENTRY_CLASS_NAME,
    ENTRY_PROJECT_PATH,
    EXTERNAL_BINDINGS,
    HASH_DOMAIN,
    MAX_QC_SOURCE_CHARACTERS,
    OVER_LIMIT_B5B_SOURCE_FILES,
    QUOTA_OBSERVATION_ID,
    QUOTA_RECEIPT_SHA256,
    QcRefusalSmokeProjectFile,
    QcRefusalSmokeProjectionError,
    SCAFFOLD_ONLY_MARKER,
    SCHEMA,
    SCHEMA_ARTIFACT_SHA256,
    SCHEMA_ID,
    SCHEMA_SHA256,
    STATUS,
    SyntheticQcRefusalSmokeProjection,
    _require_qc_source_character_count,
    _require_refusal_entry_shape,
    build_synthetic_qc_refusal_smoke_projection,
    render_qc_refusal_smoke_projection_schema_bytes,
    require_synthetic_qc_refusal_smoke_projection,
)
from research.analyst_revisions_v2_qc.synthetic_input_transport import (
    FALSE_PROPERTY_NAMES,
)
from tests.analyst_revisions_v2.test_qc_lean_source_assembly import _assembly


ROOT = Path(__file__).resolve().parents[2]
MODULE = (
    ROOT
    / "research"
    / "analyst_revisions_v2_qc"
    / "refusal_smoke_projection.py"
)

EXPECTED_PUBLIC_API = (
    "AUTHORITY",
    "CAPABILITIES",
    "DESCRIPTIVE_SENSITIVITY_FOLD_IDS",
    "ENTRY_CLASS_NAME",
    "ENTRY_PROJECT_PATH",
    "EXPECTED_PROJECT_FILE_COUNT",
    "EXTERNAL_BINDINGS",
    "FORMAL_PRIMARY_FOLD_IDS",
    "HASH_DOMAIN",
    "MAX_QC_SOURCE_CHARACTERS",
    "OVER_LIMIT_B5B_SOURCE_FILES",
    "QUOTA_OBSERVATION",
    "QUOTA_OBSERVATION_ID",
    "QUOTA_RECEIPT_SHA256",
    "QcRefusalSmokeProjectFile",
    "QcRefusalSmokeProjectionError",
    "SCAFFOLD_ONLY_MARKER",
    "SCHEMA",
    "SCHEMA_ARTIFACT_SHA256",
    "SCHEMA_ID",
    "SCHEMA_SHA256",
    "STATUS",
    "SyntheticQcRefusalSmokeProjection",
    "build_synthetic_qc_refusal_smoke_projection",
    "render_qc_refusal_smoke_projection_schema_bytes",
    "require_synthetic_qc_refusal_smoke_projection",
)


@lru_cache(maxsize=1)
def _projection():
    _candidate, _fixture, _plan, source_assembly = _assembly()
    value = build_synthetic_qc_refusal_smoke_projection(
        source_assembly=source_assembly
    )
    return source_assembly, value


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def test_schema_is_canonical_content_addressed_and_refusal_only() -> None:
    payload = render_qc_refusal_smoke_projection_schema_bytes()
    document = json.loads(payload)

    assert payload == _canonical_json_bytes(document)
    assert hashlib.sha256(payload).hexdigest() == SCHEMA_ARTIFACT_SHA256
    assert document["schema"] == SCHEMA
    assert document["status"] == STATUS
    assert document["authority"] == AUTHORITY
    assert document["schema_id"] == SCHEMA_ID
    assert document["schema_sha256"] == SCHEMA_SHA256
    assert SCHEMA_ID == "arv2-qc-refusal-smoke-projection-1fe0201a3ccb8478"
    assert SCHEMA_SHA256 == (
        "1fe0201a3ccb847896e14afd20a3729d14811ad2f0b472db08cd319c87ac2deb"
    )
    assert SCHEMA_ARTIFACT_SHA256 == (
        "ddb152f64aec2a382ded9009b0dab5c0485d31b03f6eb293af23789a99a3de10"
    )
    assert document["parent"] == {
        "b5b_schema_id": "arv2-qc-lean-source-assembly-ae4c1324f36cc6fc",
        "b5b_schema_sha256": (
            "ae4c1324f36cc6fca0218f474bdc091bf82862e8f21ada35e01a09b022bb77a5"
        ),
        "b5b_schema_artifact_sha256": (
            "532aeb471fed96c525f8be9db84694c546c1cccc6008347a43efadfac678ac20"
        ),
        "b5b_assembly_id": "arv2-qc-lean-source-assembly-8303f3323ff16ab7",
        "b5b_assembly_sha256": (
            "8303f3323ff16ab7da6c03c587bfbbf4a8d8ecb356eb8912307c2c78a75c1266"
        ),
        "b5b_assembly_artifact_sha256": (
            "56d3f77e731f6a13b5dbfb9bcbfcd8e89261a226400b744cf2c0fa3d3b400bdd"
        ),
    }
    assert document["entry"] == {
        "project_path": "main.py",
        "class_name": "AnalystRevisionsV2StockEventStudyScaffold",
        "initialize_refuses_before_service_access": True,
    }
    assert document["source_projection"] == {
        "file_count": 1,
        "maximum_file_characters": 64_000,
        "character_count_includes_terminal_lf": True,
        "utf8_byte_count_is_not_the_character_count": True,
        "complete_b5b_inventory_projected": False,
        "runtime_dependency_closure_claimed": False,
    }
    assert document["quota_observation"]["observation_id"] == (
        QUOTA_OBSERVATION_ID
    )
    assert QUOTA_OBSERVATION_ID == (
        "arv2-qc-file-character-limit-observation-20260911"
    )
    assert document["quota_observation"]["receipt_sha256"] == (
        QUOTA_RECEIPT_SHA256
    )
    assert QUOTA_RECEIPT_SHA256 == (
        "f2c3fd7536100bb4a1e1e9a8f5e4b349ff73196d286de7916c8bed5d9930a7ae"
    )
    assert tuple(
        (
            item["role"],
            item["project_path"],
            item["character_count"],
        )
        for item in document["over_limit_b5b_source_files"]
    ) == OVER_LIMIT_B5B_SOURCE_FILES
    assert len(OVER_LIMIT_B5B_SOURCE_FILES) == 4
    assert all(
        character_count > MAX_QC_SOURCE_CHARACTERS
        for _role, _path, character_count in OVER_LIMIT_B5B_SOURCE_FILES
    )
    assert document["residuals"] == {
        "full_b5b_source_set_fits_qc_file_limit": False,
        "full_runtime_dependency_closure_authenticated": False,
        "cloud_residual_file_reconciled": False,
        "production_input_package_built": False,
        "strategy_backtest_ready": False,
    }
    assert document["truth"] == {
        "source_only": True,
        "immediate_refusal": True,
        "strategy_execution_capable": False,
        "evaluation_window_applied": False,
        "runtime_code_authenticated": False,
        "physical_adapter_present": False,
        "project_created": False,
        "cloud_compile_performed": False,
        "backtest_performed": False,
        "result_access_performed": False,
    }
    assert document["external_bindings"] == dict(EXTERNAL_BINDINGS)
    assert all(value is None for value in document["external_bindings"].values())
    assert document["capabilities"] == dict(CAPABILITIES)
    assert all(value is False for value in document["capabilities"].values())


def test_projection_contains_only_the_authenticated_b5b_entry() -> None:
    source_assembly, value = _projection()
    assert require_synthetic_qc_refusal_smoke_projection(value) is value

    assert value.parent_assembly_id == source_assembly.assembly_id
    assert value.parent_assembly_hash == source_assembly.assembly_hash
    assert (
        value.parent_assembly_artifact_sha256
        == source_assembly.assembly_artifact_sha256
    )
    assert value.entry_project_path == ENTRY_PROJECT_PATH == "main.py"
    assert (
        value.entry_class_name
        == ENTRY_CLASS_NAME
        == "AnalystRevisionsV2StockEventStudyScaffold"
    )
    assert len(value.files) == 1
    projected = value.files[0]
    parent_entry = source_assembly.files[0]
    assert type(projected) is QcRefusalSmokeProjectFile
    assert (
        projected.role,
        projected.repository_path,
        projected.project_path,
        projected.source_bytes,
        projected.byte_count,
        projected.sha256,
    ) == (
        parent_entry.role,
        parent_entry.repository_path,
        parent_entry.project_path,
        parent_entry.source_bytes,
        parent_entry.byte_count,
        parent_entry.sha256,
    )
    assert projected.character_count == len(
        projected.source_bytes.decode("utf-8")
    ) == 3_328
    assert value.total_source_byte_count == projected.byte_count
    assert value.total_source_character_count == projected.character_count
    assert value.largest_project_file_character_count == projected.character_count
    assert value.largest_project_file_character_count <= MAX_QC_SOURCE_CHARACTERS
    assert value.source_only is True
    assert value.immediate_refusal is True
    assert value.strategy_execution_capable is False
    assert value.evaluation_window_applied is False
    assert value.runtime_code_authenticated is False
    assert value.physical_adapter_present is False
    assert value.project_created is False
    assert value.cloud_compile_performed is False
    assert value.backtest_performed is False
    assert value.result_access_performed is False
    assert all(binding is None for _name, binding in value.external_bindings)
    assert all(enabled is False for _name, enabled in value.capabilities)
    assert all(getattr(value, name) is False for name in FALSE_PROPERTY_NAMES)


def test_projection_identity_is_deterministic_and_binds_exact_file_bytes() -> None:
    source_assembly, first = _projection()
    second = build_synthetic_qc_refusal_smoke_projection(
        source_assembly=source_assembly
    )
    assert first.projection_id == second.projection_id
    assert first.projection_hash == second.projection_hash
    assert first.projection_artifact_sha256 == second.projection_artifact_sha256
    assert first._canonical_document == second._canonical_document
    assert hashlib.sha256(first._canonical_document).hexdigest() == (
        first.projection_artifact_sha256
    )
    document = json.loads(first._canonical_document)
    assert document["projection_id"] == first.projection_id
    assert document["projection_hash"] == first.projection_hash
    assert document["files"] == [
        {
            "role": first.files[0].role,
            "repository_path": first.files[0].repository_path,
            "project_path": first.files[0].project_path,
            "byte_count": first.files[0].byte_count,
            "character_count": first.files[0].character_count,
            "sha256": first.files[0].sha256,
        }
    ]


def test_qc_character_limit_is_inclusive_and_is_not_a_byte_limit() -> None:
    assert MAX_QC_SOURCE_CHARACTERS == 64_000
    assert _require_qc_source_character_count(b"a" * 64_000) == 64_000
    with pytest.raises(QcRefusalSmokeProjectionError, match="character"):
        _require_qc_source_character_count(b"a" * 64_001)

    multibyte_at_limit = ("\N{LATIN SMALL LETTER E WITH ACUTE}" * 64_000).encode(
        "utf-8"
    )
    assert len(multibyte_at_limit) == 128_000
    assert _require_qc_source_character_count(multibyte_at_limit) == 64_000
    with pytest.raises(QcRefusalSmokeProjectionError, match="character"):
        _require_qc_source_character_count(
            multibyte_at_limit
            + "\N{LATIN SMALL LETTER E WITH ACUTE}".encode("utf-8")
        )
    with pytest.raises(QcRefusalSmokeProjectionError, match="UTF-8"):
        _require_qc_source_character_count(b"\xff")


def test_refusal_entry_shape_authenticates_fold_marker_and_import_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source_assembly, value = _projection()
    source = value.files[0].source_bytes
    assert _require_refusal_entry_shape(source) is None

    mutants = (
        source.replace(
            b'class AnalystRevisionsV2StockEventStudyScaffold(QCAlgorithm):',
            b'class OtherScaffold(QCAlgorithm):',
            1,
        ),
        source.replace(
            b'    "arv2-wf-test-2020",\n',
            b"",
            1,
        ),
        source.replace(
            b'DESCRIPTIVE_SENSITIVITY_FOLD_IDS = (\n',
            b'DESCRIPTIVE_SENSITIVITY_FOLD_IDS = (\n    "arv2-wf-test-2020",\n',
            1,
        ),
        source.replace(
            SCAFFOLD_ONLY_MARKER.encode("utf-8"),
            b"changed refusal marker",
            1,
        ),
        source.replace(
            (
                b"from AlgorithmImports import *  # noqa: F403  "
                b"(LEAN's documented entry point)\n"
            ),
            (
                b"from AlgorithmImports import *  # noqa: F403\n"
                b"from research.analyst_revisions_v2_qc import event_study\n"
            ),
            1,
        ),
        source.replace(
            (
                b"    def initialize(self):\n"
                b"        raise RuntimeError(SCAFFOLD_ONLY_MARKER)\n"
            ),
            (
                b"    def initialize(self):\n"
                b"        self.debug('service touched')\n"
                b"        raise RuntimeError(SCAFFOLD_ONLY_MARKER)\n"
            ),
            1,
        ),
        source.replace(
            b"        raise RuntimeError(SCAFFOLD_ONLY_MARKER)\n",
            b"        return None\n",
            1,
        ),
        source.replace(
            b"class AnalystRevisionsV2StockEventStudyScaffold(QCAlgorithm):",
            (
                b"@decorator\n"
                b"class AnalystRevisionsV2StockEventStudyScaffold(QCAlgorithm):"
            ),
            1,
        ),
        source.replace(
            b"    def on_end_of_algorithm(self):\n",
            b"    def extra_method(self):\n        return None\n\n"
            b"    def on_end_of_algorithm(self):\n",
            1,
        ),
        source.replace(
            b"        raise RuntimeError(SCAFFOLD_ONLY_MARKER)\n",
            (
                b"        raise RuntimeError(SCAFFOLD_ONLY_MARKER)\n"
                b"        self.debug('dead service call')\n"
            ),
            1,
        ),
        source.replace(
            b"SCAFFOLD_SCHEMA = ",
            b"print('module call')\nSCAFFOLD_SCHEMA = ",
            1,
        ),
    )
    assert all(mutant != source for mutant in mutants)
    for mutant in mutants:
        # Make the independent byte-identity check accept each mutant so the
        # structural validator, rather than the final hash check, must refuse.
        monkeypatch.setattr(
            projection_module,
            "B5B_ENTRY_SOURCE_SHA256",
            hashlib.sha256(mutant).hexdigest(),
        )
        monkeypatch.setattr(
            projection_module,
            "B5B_ENTRY_SOURCE_BYTE_COUNT",
            len(mutant),
        )
        with pytest.raises(QcRefusalSmokeProjectionError):
            _require_refusal_entry_shape(mutant)

    for invalid_encoding_or_newline in (
        b"\xef\xbb\xbf" + source,
        source.replace(b"\n", b"\r\n"),
        source + b"\x00",
    ):
        with pytest.raises(QcRefusalSmokeProjectionError):
            _require_refusal_entry_shape(invalid_encoding_or_newline)


@pytest.mark.parametrize(
    "parent_mutator",
    (
        lambda parent: dataclasses.replace(parent, assembly_hash="0" * 64),
        lambda parent: dataclasses.replace(
            parent,
            entry_project_path="other.py",
        ),
        lambda parent: dataclasses.replace(
            parent,
            files=(
                dataclasses.replace(
                    parent.files[0],
                    source_bytes=parent.files[0].source_bytes + b"# changed\n",
                ),
                *parent.files[1:],
            ),
        ),
        lambda parent: dataclasses.replace(parent, files=parent.files[1:]),
    ),
)
def test_changed_parent_or_entry_is_refused(parent_mutator) -> None:
    source_assembly, _value = _projection()
    changed = parent_mutator(source_assembly)
    with pytest.raises(QcRefusalSmokeProjectionError):
        build_synthetic_qc_refusal_smoke_projection(source_assembly=changed)


def test_builder_reauthenticates_parent_around_detached_snapshot() -> None:
    source_assembly, _value = _projection()
    parent_validator_code = projection_module._PINNED_REQUIRE_PARENT.__code__
    calls: list[object] = []

    def profile(frame, event, _arg):
        if frame.f_code is parent_validator_code and event == "call":
            calls.append(frame.f_locals.get("value"))
        return profile

    sys.setprofile(profile)
    try:
        built = build_synthetic_qc_refusal_smoke_projection(
            source_assembly=source_assembly
        )
    finally:
        sys.setprofile(None)
    assert len(calls) == 2
    assert calls[0] is calls[1] is source_assembly
    assert require_synthetic_qc_refusal_smoke_projection(built) is built


def test_builder_refuses_parent_mutation_after_second_authentication() -> None:
    source_assembly, _value = _projection()
    parent_validator_code = projection_module._PINNED_REQUIRE_PARENT.__code__
    original_hash = source_assembly.assembly_hash
    calls = 0

    def profile(frame, event, _arg):
        nonlocal calls
        if frame.f_code is parent_validator_code and event == "return":
            calls += 1
            if calls == 2:
                object.__setattr__(source_assembly, "assembly_hash", "0" * 64)
        return profile

    sys.setprofile(profile)
    try:
        with pytest.raises(QcRefusalSmokeProjectionError, match="changed"):
            build_synthetic_qc_refusal_smoke_projection(
                source_assembly=source_assembly
            )
    finally:
        sys.setprofile(None)
        object.__setattr__(source_assembly, "assembly_hash", original_hash)
    assert calls == 2


@pytest.mark.parametrize(
    "projection_mutator",
    (
        lambda value: dataclasses.replace(value, projection_hash="0" * 64),
        lambda value: dataclasses.replace(
            value, projection_artifact_sha256="0" * 64
        ),
        lambda value: dataclasses.replace(value, entry_project_path="other.py"),
        lambda value: dataclasses.replace(value, files=()),
        lambda value: dataclasses.replace(
            value,
            files=(
                dataclasses.replace(value.files[0], sha256="0" * 64),
            ),
        ),
        lambda value: dataclasses.replace(
            value,
            files=(
                dataclasses.replace(
                    value.files[0],
                    character_count=value.files[0].character_count + 1,
                ),
            ),
        ),
        lambda value: dataclasses.replace(value, strategy_execution_capable=True),
        lambda value: dataclasses.replace(value, backtest_performed=True),
        lambda value: dataclasses.replace(
            value,
            capabilities=(
                (value.capabilities[0][0], True),
                *value.capabilities[1:],
            ),
        ),
    ),
)
def test_changed_projection_hash_shape_or_capability_is_refused(
    projection_mutator,
) -> None:
    _source_assembly, value = _projection()
    with pytest.raises(QcRefusalSmokeProjectionError):
        require_synthetic_qc_refusal_smoke_projection(projection_mutator(value))


def test_self_consistent_projection_with_forged_parent_lineage_is_refused() -> None:
    _source_assembly, value = _projection()
    forged_parent_hash = "0" * 64
    forged_parent_artifact_hash = "1" * 64
    forged_parent_id = (
        f"arv2-qc-lean-source-assembly-{forged_parent_hash[:16]}"
    )
    document = json.loads(value._canonical_document)
    document["parent"]["assembly_id"] = forged_parent_id
    document["parent"]["assembly_hash"] = forged_parent_hash
    document["parent"]["assembly_artifact_sha256"] = (
        forged_parent_artifact_hash
    )
    document["projection_id"] = None
    document["projection_hash"] = None
    identity_seed = _canonical_json_bytes(document)
    projection_hash = hashlib.sha256(
        HASH_DOMAIN.encode("ascii") + b"\0" + identity_seed
    ).hexdigest()
    document["projection_id"] = (
        f"arv2-qc-refusal-smoke-projection-{projection_hash[:16]}"
    )
    document["projection_hash"] = projection_hash
    canonical_document = _canonical_json_bytes(document)
    forged = dataclasses.replace(
        value,
        parent_assembly_id=forged_parent_id,
        parent_assembly_hash=forged_parent_hash,
        parent_assembly_artifact_sha256=forged_parent_artifact_hash,
        projection_id=document["projection_id"],
        projection_hash=projection_hash,
        projection_artifact_sha256=(
            hashlib.sha256(canonical_document).hexdigest()
        ),
        _canonical_document=canonical_document,
    )

    with pytest.raises(
        QcRefusalSmokeProjectionError,
        match="parent|lineage|authority|construction",
    ):
        require_synthetic_qc_refusal_smoke_projection(forged)


def test_projection_values_are_frozen_and_detached_from_caller_mutation() -> None:
    source_assembly, value = _projection()
    with pytest.raises(dataclasses.FrozenInstanceError):
        value.files = ()  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        value.files[0].sha256 = "0" * 64  # type: ignore[misc]

    original_hash = source_assembly.assembly_hash
    object.__setattr__(source_assembly, "assembly_hash", "0" * 64)
    try:
        assert value.parent_assembly_hash == original_hash
        assert require_synthetic_qc_refusal_smoke_projection(value) is value
    finally:
        object.__setattr__(source_assembly, "assembly_hash", original_hash)
    assert require_synthetic_qc_refusal_smoke_projection(value) is value
    assert not any(
        field.name in {"_source_assembly", "_parent", "object_store_calls"}
        for field in dataclasses.fields(type(value))
    )


def test_public_builder_refuses_coordinated_active_source_oracle_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_assembly, _value = _projection()
    active_source = (
        b"from AlgorithmImports import *\n"
        b"class AnalystRevisionsV2StockEventStudyScaffold(QCAlgorithm):\n"
        b"    def initialize(self):\n"
        b"        self.set_cash(100000)\n"
    )
    active_file = dataclasses.replace(
        source_assembly.files[0],
        source_bytes=active_source,
        byte_count=len(active_source),
        sha256=hashlib.sha256(active_source).hexdigest(),
    )
    forged_parent = dataclasses.replace(
        source_assembly,
        files=(active_file, *source_assembly.files[1:]),
    )

    class HostileParentValidator:
        calls = 0

        def __call__(self, value):
            type(self).calls += 1
            return value

    class HostileShapeValidator:
        calls = 0

        def __call__(self, _source_bytes):
            type(self).calls += 1
            return None

    hostile_parent = HostileParentValidator()
    hostile_shape = HostileShapeValidator()
    monkeypatch.setattr(
        projection_module,
        "_PINNED_REQUIRE_PARENT",
        hostile_parent,
    )
    monkeypatch.setattr(
        projection_module,
        "B5B_ENTRY_SOURCE_BYTE_COUNT",
        len(active_source),
    )
    monkeypatch.setattr(
        projection_module,
        "B5B_ENTRY_SOURCE_SHA256",
        hashlib.sha256(active_source).hexdigest(),
    )
    monkeypatch.setattr(
        projection_module,
        "_require_refusal_entry_shape",
        hostile_shape,
    )

    with pytest.raises(
        QcRefusalSmokeProjectionError,
        match="bootstrap|binding|function|alias|scalar",
    ):
        build_synthetic_qc_refusal_smoke_projection(
            source_assembly=forged_parent
        )
    assert HostileParentValidator.calls == 0
    assert HostileShapeValidator.calls == 0


@pytest.mark.parametrize(
    ("binding_name", "operation"),
    (
        ("_PINNED_RENDER_PARENT_SCHEMA", "render"),
        ("_PINNED_REQUIRE_PARENT", "build"),
        ("_require_refusal_entry_shape", "build"),
        ("_PINNED_SHA256", "require"),
    ),
)
def test_public_entrypoints_refuse_hostile_alias_before_callback(
    monkeypatch: pytest.MonkeyPatch,
    binding_name: str,
    operation: str,
) -> None:
    source_assembly, value = _projection()

    class Hostile:
        calls = 0

        def __call__(self, *_args, **_kwargs):
            type(self).calls += 1
            raise AssertionError("hostile alias callback ran")

    monkeypatch.setattr(projection_module, binding_name, Hostile())
    with pytest.raises(
        QcRefusalSmokeProjectionError,
        match="bootstrap|binding|function|alias|snapshot",
    ):
        if operation == "render":
            render_qc_refusal_smoke_projection_schema_bytes()
        elif operation == "build":
            build_synthetic_qc_refusal_smoke_projection(
                source_assembly=source_assembly
            )
        else:
            require_synthetic_qc_refusal_smoke_projection(value)
    assert Hostile.calls == 0


@pytest.mark.parametrize(
    "public_name",
    (
        "render_qc_refusal_smoke_projection_schema_bytes",
        "build_synthetic_qc_refusal_smoke_projection",
        "require_synthetic_qc_refusal_smoke_projection",
    ),
)
def test_public_entrypoint_binding_is_bootstrap_sealed(
    monkeypatch: pytest.MonkeyPatch,
    public_name: str,
) -> None:
    source_assembly, value = _projection()

    class Hostile:
        calls = 0

        def __call__(self, *_args, **_kwargs):
            type(self).calls += 1
            raise AssertionError("hostile public entry point ran")

    monkeypatch.setattr(projection_module, public_name, Hostile())
    with pytest.raises(
        QcRefusalSmokeProjectionError,
        match="public binding|bootstrap",
    ):
        if public_name.startswith("render_"):
            render_qc_refusal_smoke_projection_schema_bytes()
        elif public_name.startswith("build_"):
            build_synthetic_qc_refusal_smoke_projection(
                source_assembly=source_assembly
            )
        else:
            require_synthetic_qc_refusal_smoke_projection(value)
    assert Hostile.calls == 0


@pytest.mark.parametrize(
    ("name", "replacement"),
    (
        ("_PINNED_STATIC_SNAPSHOT_BINDINGS", ()),
        ("_PINNED_ALIAS_BINDINGS", ()),
        ("_PINNED_REQUIRE_STATIC_CONTRACT", lambda: None),
    ),
)
def test_public_bootstrap_refuses_registry_rebinding(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    replacement,
) -> None:
    monkeypatch.setattr(projection_module, name, replacement)
    with pytest.raises(
        QcRefusalSmokeProjectionError,
        match="bootstrap registry",
    ):
        render_qc_refusal_smoke_projection_schema_bytes()


def test_public_bootstrap_refuses_hostile_globals_alias_before_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class HostileGlobals:
        calls = 0

        def __call__(self):
            type(self).calls += 1
            raise AssertionError("hostile globals callback ran")

    monkeypatch.setattr(projection_module, "_PINNED_GLOBALS", HostileGlobals())
    with pytest.raises(
        QcRefusalSmokeProjectionError,
        match="bootstrap alias|binding",
    ):
        render_qc_refusal_smoke_projection_schema_bytes()
    assert HostileGlobals.calls == 0


def test_static_contract_refuses_hostile_quota_observation_subclass_before_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class HostileQuotaObservation(str):
        calls = 0

        def __eq__(self, _other):
            type(self).calls += 1
            raise AssertionError("hostile quota-observation comparison ran")

        __hash__ = str.__hash__

    replacement = HostileQuotaObservation(projection_module.QUOTA_OBSERVATION)
    monkeypatch.setattr(projection_module, "QUOTA_OBSERVATION", replacement)
    with pytest.raises(QcRefusalSmokeProjectionError, match="scalar"):
        render_qc_refusal_smoke_projection_schema_bytes()
    assert HostileQuotaObservation.calls == 0


def test_static_contract_refuses_class_property_before_hostile_getter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source_assembly, value = _projection()

    class HostileGetter:
        calls = 0

        def __call__(self, _value):
            type(self).calls += 1
            return False

    monkeypatch.setattr(
        SyntheticQcRefusalSmokeProjection,
        "orders_available",
        property(HostileGetter()),
    )
    with pytest.raises(
        QcRefusalSmokeProjectionError,
        match="class topology|class function|binding",
    ):
        require_synthetic_qc_refusal_smoke_projection(value)
    assert HostileGetter.calls == 0


def test_static_contract_refuses_in_place_property_code_mutation() -> None:
    authority_property = vars(SyntheticQcRefusalSmokeProjection)[
        "orders_available"
    ]
    implementation = authority_property.fget
    assert implementation is not None
    original_code = implementation.__code__

    def replacement(_self):
        return True

    implementation.__code__ = replacement.__code__
    try:
        with pytest.raises(
            QcRefusalSmokeProjectionError,
            match="class function|class topology",
        ):
            render_qc_refusal_smoke_projection_schema_bytes()
    finally:
        implementation.__code__ = original_code
    assert render_qc_refusal_smoke_projection_schema_bytes()


def test_static_contract_refuses_in_place_helper_code_mutation() -> None:
    implementation = projection_module._require_refusal_entry_shape
    original_code = implementation.__code__

    def replacement(_source_bytes):
        return None

    implementation.__code__ = replacement.__code__
    try:
        with pytest.raises(
            QcRefusalSmokeProjectionError,
            match="function",
        ):
            render_qc_refusal_smoke_projection_schema_bytes()
    finally:
        implementation.__code__ = original_code
    assert render_qc_refusal_smoke_projection_schema_bytes()


@pytest.mark.parametrize("attribute", ("__defaults__", "__kwdefaults__"))
def test_static_contract_refuses_in_place_helper_default_mutation(
    attribute: str,
) -> None:
    implementation = projection_module._identity_document
    original = getattr(implementation, attribute)
    replacement = (None,) if attribute == "__defaults__" else {"id_key": None}
    setattr(implementation, attribute, replacement)
    try:
        with pytest.raises(
            QcRefusalSmokeProjectionError,
            match="function",
        ):
            render_qc_refusal_smoke_projection_schema_bytes()
    finally:
        setattr(implementation, attribute, original)
    assert render_qc_refusal_smoke_projection_schema_bytes()


def test_public_wrapper_refuses_closure_mutation_before_hostile_callback() -> None:
    wrapper = render_qc_refusal_smoke_projection_schema_bytes
    assert wrapper.__closure__ is not None
    closure = dict(zip(wrapper.__code__.co_freevars, wrapper.__closure__, strict=True))
    assert set(closure) == {"check", "render_impl"}
    cell = closure["render_impl"]
    original = cell.cell_contents

    class Hostile:
        calls = 0

        def __call__(self):
            type(self).calls += 1
            raise AssertionError("hostile closure callback ran")

    cell.cell_contents = Hostile()
    try:
        with pytest.raises(QcRefusalSmokeProjectionError, match="function"):
            wrapper()
    finally:
        cell.cell_contents = original
    assert Hostile.calls == 0
    assert wrapper()


@pytest.mark.parametrize(
    "changes",
    (
        {"B5B_ENTRY_PROJECT_PATH": "evil.py"},
        {"B5B_ENTRY_CLASS_NAME": "Evil"},
        {
            "B5B_ENTRY_PROJECT_PATH": "evil.py",
            "ENTRY_PROJECT_PATH": "evil.py",
        },
        {
            "B5B_ENTRY_CLASS_NAME": "Evil",
            "ENTRY_CLASS_NAME": "Evil",
        },
    ),
    ids=(
        "parent-path",
        "parent-class",
        "coordinated-path",
        "coordinated-class",
    ),
)
def test_static_contract_refuses_parent_or_child_entry_scalar_drift(
    monkeypatch: pytest.MonkeyPatch,
    changes: dict[str, str],
) -> None:
    for name, value in changes.items():
        monkeypatch.setattr(projection_module, name, value)
    with pytest.raises(QcRefusalSmokeProjectionError):
        render_qc_refusal_smoke_projection_schema_bytes()


def test_production_module_has_no_io_or_action_surface() -> None:
    source = MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_import_roots = {
        "http",
        "os",
        "pathlib",
        "requests",
        "socket",
        "subprocess",
        "urllib",
    }
    forbidden_calls = {
        "__import__",
        "compile",
        "eval",
        "exec",
        "input",
        "open",
    }
    forbidden_attribute_calls = {
        "create_backtest",
        "create_compile",
        "create_file",
        "delete_file",
        "read",
        "read_backtest",
        "read_bytes",
        "read_text",
        "request",
        "update_file",
        "write",
        "write_bytes",
        "write_text",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(
                alias.name.split(".", 1)[0] not in forbidden_import_roots
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            assert (node.module or "").split(".", 1)[0] not in forbidden_import_roots
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_calls
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden_attribute_calls

    public_functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    }
    assert set(public_functions) == {
        "build_synthetic_qc_refusal_smoke_projection",
        "render_qc_refusal_smoke_projection_schema_bytes",
        "require_synthetic_qc_refusal_smoke_projection",
    }
    for name, node in public_functions.items():
        parameters = {
            argument.arg
            for argument in (
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            )
        }
        assert parameters.isdisjoint(
            {
                "account",
                "algorithm",
                "client",
                "credentials",
                "object_store",
                "path",
                "project",
                "result",
            }
        ), name


def test_public_api_is_narrow_and_exactly_typed() -> None:
    assert projection_module.__all__ == EXPECTED_PUBLIC_API
    assert all(hasattr(projection_module, name) for name in EXPECTED_PUBLIC_API)
    exported_namespace: dict[str, object] = {}
    exec(
        "from research.analyst_revisions_v2_qc.refusal_smoke_projection import *",
        exported_namespace,
    )
    assert {
        name for name in exported_namespace if name != "__builtins__"
    } == set(EXPECTED_PUBLIC_API)
    assert QcRefusalSmokeProjectionError.__bases__ == (ValueError,)
    assert dataclasses.is_dataclass(QcRefusalSmokeProjectFile)
    assert dataclasses.is_dataclass(SyntheticQcRefusalSmokeProjection)
    assert tuple(
        inspect.signature(
            render_qc_refusal_smoke_projection_schema_bytes
        ).parameters
    ) == ()
    build_signature = inspect.signature(build_synthetic_qc_refusal_smoke_projection)
    assert tuple(build_signature.parameters) == ("source_assembly",)
    assert build_signature.parameters["source_assembly"].kind is (
        inspect.Parameter.KEYWORD_ONLY
    )
    assert tuple(
        inspect.signature(require_synthetic_qc_refusal_smoke_projection).parameters
    ) == ("value",)


def test_projection_does_not_claim_a_qc_strategy_or_evaluation() -> None:
    _source_assembly, value = _projection()
    assert "refusal" in STATUS
    assert "strategy" not in value.projection_id
    assert value.entry_project_path == "main.py"
    assert value.immediate_refusal is True
    assert value.strategy_execution_capable is False
    assert value.evaluation_window_applied is False
    assert value.runtime_code_authenticated is False
    assert value.backtest_performed is False
    assert value.result_access_performed is False
    assert all(flag is False for _name, flag in value.capabilities)
    assert not any(
        field.name in {"start_date", "end_date", "cash", "benchmark"}
        for field in dataclasses.fields(type(value))
    )


def test_entry_source_identity_pin_rejects_an_ast_invisible_byte_change() -> None:
    """The grammar cannot see a comment; only the pinned identity rejects one."""

    _parent, value = _projection()
    source = value.files[0].source_bytes

    _require_refusal_entry_shape(source)

    with pytest.raises(QcRefusalSmokeProjectionError) as excinfo:
        _require_refusal_entry_shape(source + b"# AST-invisible trailing comment\n")

    assert "entry source identity changed" in str(excinfo.value)
