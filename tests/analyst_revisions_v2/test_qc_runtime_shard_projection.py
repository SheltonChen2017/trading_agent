from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from research.analyst_revisions_v2_qc import lean_source_assembly as b5b
from research.analyst_revisions_v2_qc import runtime_shard_projection as shard
from tests.analyst_revisions_v2.test_qc_lean_source_assembly import _assembly
from tests.analyst_revisions_v2.test_qc_object_store_read_contract import (
    _no_io_violations,
)


EXPECTED_PROJECT_SNAPSHOT = (
    ("lean_entry", "main.py", "retained", 3_328, "327f126311c12e9f37297f229a3946a6cb1f2bbe26ed6c746cf140b26c2e6bf9"),
    ("research_package_marker", "research/__init__.py", "retained", 0, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    ("qc_package_marker", "research/analyst_revisions_v2_qc/__init__.py", "retained", 487, "ce8f07aeab0358f5eb3241190169d4f967a5423dc88719f0783a83d010d43dcc"),
    ("event_study_core_runtime_facade", "research/analyst_revisions_v2_qc/event_study.py", "facade", 1_120, "2952dce00f60c8877093259e7b17494f1878bbabca1a3d80d888c3e290f1e1a7"),
    ("event_study_core_source_carrier_00", "research/analyst_revisions_v2_qc/_arv2_b5d_event_study_source_00.py", "carrier", 54_081, "309f44510d70217d668eb9734b4a2ea5a4ef76fd701aad53180731141073dba0"),
    ("event_study_core_source_carrier_01", "research/analyst_revisions_v2_qc/_arv2_b5d_event_study_source_01.py", "carrier", 54_081, "16f3a039275fd3f5e7995432896305dd50530f173658d1e24fbac34dd245a143"),
    ("event_study_core_source_carrier_02", "research/analyst_revisions_v2_qc/_arv2_b5d_event_study_source_02.py", "carrier", 49_373, "054d86bd7cc907d6a79fc4211582313bf9748f8a5d4a294066078593a9fee21c"),
    ("global_input_bundle_runtime_facade", "research/analyst_revisions_v2_qc/global_input_bundle.py", "facade", 1_285, "712c9e398dbc1841b811e1eea44dec85a788796764a4bd7efa375ef93bb2a356"),
    ("global_input_bundle_source_carrier_00", "research/analyst_revisions_v2_qc/_arv2_b5d_global_input_bundle_source_00.py", "carrier", 54_084, "85a9029ec0828e7b58f5e80bf9d416409baaf7cb8cdc05a0af5e1f6168275962"),
    ("global_input_bundle_source_carrier_01", "research/analyst_revisions_v2_qc/_arv2_b5d_global_input_bundle_source_01.py", "carrier", 54_084, "ccdd5a8b9b4d6b036200c92ffe33f4580debfe91006135b13d8a32b9717e4623"),
    ("global_input_bundle_source_carrier_02", "research/analyst_revisions_v2_qc/_arv2_b5d_global_input_bundle_source_02.py", "carrier", 54_084, "9ed3981eba0135ae498744d3f3a599ae70e372939e05258f4eb6765c9e738f2c"),
    ("global_input_bundle_source_carrier_03", "research/analyst_revisions_v2_qc/_arv2_b5d_global_input_bundle_source_03.py", "carrier", 41_104, "9c48111df03d44e56d4c403fdd9259c8686f51a5ebb006c40862e8665bb41cdb"),
    ("global_input_schema_runtime_facade", "research/analyst_revisions_v2_qc/global_input_schema.py", "facade", 1_159, "10ae524ba394133784856060c5f095b49dbb2699b91445fbe763b9ba221a2919"),
    ("global_input_schema_source_carrier_00", "research/analyst_revisions_v2_qc/_arv2_b5d_global_input_schema_source_00.py", "carrier", 54_084, "85d6448f0087769899d4392a95ada719052cf00f0fe6897432bfdfe13ea16c2c"),
    ("global_input_schema_source_carrier_01", "research/analyst_revisions_v2_qc/_arv2_b5d_global_input_schema_source_01.py", "carrier", 54_084, "43d45f33b0077bb5a10b595d776a6136cdbbd097c1575ea839e1b5b954bcfd8f"),
    ("global_input_schema_source_carrier_02", "research/analyst_revisions_v2_qc/_arv2_b5d_global_input_schema_source_02.py", "carrier", 28_832, "b2245f0c114c8fa4360f1797a2514ceb2389d1799489af6a9098a92b6f523049"),
    ("object_store_read_contract", "research/analyst_revisions_v2_qc/object_store_read_contract.py", "retained", 57_361, "bf370a894986cec8ac341ef8f43bce91aeab4568295ab94c281ce5defaa4d2e3"),
    ("run_contract", "research/analyst_revisions_v2_qc/run_contract.py", "retained", 28_825, "a72aa500a5c2d2fe68cfe9a00e6531a8c1a241e212cb8df8e2a7a56dba3d77d5"),
    ("synthetic_input_transport_runtime_facade", "research/analyst_revisions_v2_qc/synthetic_input_transport.py", "facade", 1_058, "9527cb4c5095631376138ba74fcef3ee58d3666bb58210da4f52a0f5d85d9412"),
    ("synthetic_input_transport_source_carrier_00", "research/analyst_revisions_v2_qc/_arv2_b5d_synthetic_input_transport_source_00.py", "carrier", 54_090, "3c7ce08b2d20cd4d334f64a3767ea34d09ad614b268c94f3842b804ca0fcfab8"),
    ("synthetic_input_transport_source_carrier_01", "research/analyst_revisions_v2_qc/_arv2_b5d_synthetic_input_transport_source_01.py", "carrier", 39_902, "38e68a1a7e5ef6ddded7a12167c4f0df367dcaf3ede53dd9b3b3e5cab30f8252"),
    ("data_package_marker", "data/__init__.py", "retained", 0, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    ("exchange_calendar", "data/exchange_calendar.py", "retained", 8_796, "174a032efce4082b8661eabe84b0cf6094048e937722bdf1659c8cb6c7decb89"),
)


@pytest.fixture(scope="module")
def projection():
    _candidate, _fixture, _plan, parent = _assembly()
    value = shard.build_synthetic_qc_runtime_shard_projection(
        source_assembly=parent
    )
    return shard.require_synthetic_qc_runtime_shard_projection(value), parent


def test_exact_inventory_limits_and_parent_lineage(projection):
    value, _parent = projection
    assert value.project_file_count == len(value.files) == 23
    assert value.carrier_file_count == 12
    assert len(value.module_bindings) == 4
    assert value.parent_assembly_id == shard.EXPECTED_PARENT_ASSEMBLY_ID
    assert value.parent_assembly_sha256 == shard.EXPECTED_PARENT_ASSEMBLY_SHA256
    assert (
        value.parent_assembly_artifact_sha256
        == shard.EXPECTED_PARENT_ASSEMBLY_ARTIFACT_SHA256
    )
    assert value.largest_projected_source_character_count == 57_361
    assert max(item.character_count for item in value.files) == 57_361
    assert all(
        item.character_count <= shard.MAX_PROJECTED_SOURCE_CHARACTERS < 64_000
        for item in value.files
    )
    assert len({item.project_path for item in value.files}) == len(value.files)
    assert len({item.project_path.casefold() for item in value.files}) == len(
        value.files
    )
    assert [item.carrier_file_count for item in value.module_bindings] == [
        3,
        4,
        3,
        2,
    ]
    assert tuple(
        (
            item.role,
            item.project_path,
            item.source_kind,
            item.character_count,
            item.sha256,
        )
        for item in value.files
    ) == EXPECTED_PROJECT_SNAPSHOT


def test_every_sharded_module_reconstructs_the_exact_reviewed_bytes(projection):
    value, parent = projection
    original = {item.project_path: item for item in parent.files}
    for binding in value.module_bindings:
        reconstructed = shard.reconstruct_canonical_module_bytes(value, binding)
        expected = original[binding.canonical_project_path].source_bytes
        assert reconstructed == expected
        assert len(reconstructed) == binding.canonical_byte_count
        assert hashlib.sha256(reconstructed).hexdigest() == binding.canonical_sha256


def test_compliant_parent_files_are_retained_byte_for_byte(projection):
    value, parent = projection
    projected = {item.project_path: item for item in value.files}
    sharded_paths = {item[1] for item in shard.SHARDED_MODULES}
    for item in parent.files:
        if item.project_path not in sharded_paths:
            actual = projected[item.project_path]
            assert actual.source_kind == "retained"
            assert actual.source_bytes == item.source_bytes
            assert actual.sha256 == item.sha256


def _direct_call_names(tree: ast.AST) -> list[str]:
    return [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]


def test_facades_have_the_controlled_straight_line_loader_grammar(projection):
    value, _parent = projection
    for source_file in value.files:
        if source_file.source_kind != "facade":
            continue
        tree = ast.parse(source_file.source_bytes)
        assert not any(
            isinstance(
                node,
                (
                    ast.AsyncFunctionDef,
                    ast.ClassDef,
                    ast.For,
                    ast.FunctionDef,
                    ast.Lambda,
                    ast.Try,
                    ast.While,
                    ast.With,
                ),
            )
            for node in ast.walk(tree)
        )
        imports = [
            node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        assert isinstance(imports[0], ast.Import)
        assert imports[0].names[0].name == "base64"
        assert imports[0].names[0].asname == "_arv2_b5d_base64"
        assert isinstance(imports[1], ast.Import)
        assert imports[1].names[0].name == "hashlib"
        assert imports[1].names[0].asname == "_arv2_b5d_hashlib"
        carrier_imports = imports[2:]
        assert carrier_imports
        assert all(
            isinstance(node, ast.ImportFrom)
            and node.level == 1
            and node.module is not None
            and node.module.startswith("_arv2_b5d_")
            and len(node.names) == 1
            and node.names[0].name == "CHUNK_B64"
            and node.names[0].asname is not None
            and node.names[0].asname.startswith("_arv2_b5d_chunk_")
            for node in carrier_imports
        )
        direct_calls = _direct_call_names(tree)
        assert direct_calls.count("compile") == 1
        assert direct_calls.count("exec") == 1
        assert direct_calls.count("globals") == 2
        assert direct_calls.count("RuntimeError") == 1
        assert direct_calls.count("type") == 1
        assert direct_calls.count("len") == 1
        assert not ({"eval", "open", "input", "__import__"} & set(direct_calls))
        assert isinstance(tree.body[-1], ast.Delete)
        deleted = {
            target.id
            for target in tree.body[-1].targets
            if isinstance(target, ast.Name)
        }
        assert {
            "_arv2_b5d_base64",
            "_arv2_b5d_hashlib",
            "_arv2_b5d_encoded",
            "_arv2_b5d_source",
            "_arv2_b5d_code",
        } <= deleted


def test_carriers_are_data_only_and_have_no_import_or_call(projection):
    value, _parent = projection
    carrier_sizes = []
    for source_file in value.files:
        if source_file.source_kind != "carrier":
            continue
        carrier_sizes.append(source_file.character_count)
        tree = ast.parse(source_file.source_bytes)
        assert len(tree.body) == 2
        assert isinstance(tree.body[0], ast.Expr)
        assert isinstance(tree.body[1], ast.Assign)
        assert not any(
            isinstance(
                node,
                (
                    ast.Call,
                    ast.Import,
                    ast.ImportFrom,
                    ast.FunctionDef,
                    ast.ClassDef,
                ),
            )
            for node in ast.walk(tree)
        )
    assert len(carrier_sizes) == 12
    assert max(carrier_sizes) == 54_090


def test_projection_is_deterministic_and_detached(projection):
    first, parent = projection
    second = shard.build_synthetic_qc_runtime_shard_projection(
        source_assembly=parent
    )
    assert second == first
    assert second.projection_sha256 == first.projection_sha256
    assert second.projection_artifact_sha256 == first.projection_artifact_sha256
    assert tuple(item.source_bytes for item in second.files) == tuple(
        item.source_bytes for item in first.files
    )


def test_parent_or_carrier_mutation_refuses(projection):
    value, parent = projection
    with pytest.raises(Exception):
        shard.build_synthetic_qc_runtime_shard_projection(
            source_assembly=dataclasses.replace(parent, assembly_id="changed")
        )

    carrier_index = next(
        index
        for index, item in enumerate(value.files)
        if item.source_kind == "carrier"
    )
    carrier = value.files[carrier_index]
    changed_source = carrier.source_bytes.replace(b"A", b"B", 1)
    changed_file = dataclasses.replace(
        carrier,
        source_bytes=changed_source,
        sha256=hashlib.sha256(changed_source).hexdigest(),
    )
    changed_files = list(value.files)
    changed_files[carrier_index] = changed_file
    changed = dataclasses.replace(value, files=tuple(changed_files))
    with pytest.raises(shard.QcRuntimeShardProjectionError):
        shard.require_synthetic_qc_runtime_shard_projection(changed)


def test_every_action_authority_is_false_or_null(projection):
    value, _parent = projection
    assert value.canonical_runtime_source_reconstruction_authenticated is True
    assert value.cloud_runtime_execution_authenticated is False
    assert value.physical_adapter_present is False
    assert value.cloud_compile_performed is False
    assert value.backtest_performed is False
    assert value.external_bindings[: len(b5b.EXTERNAL_BINDINGS)] == (
        b5b.EXTERNAL_BINDINGS
    )
    assert value.external_bindings[len(b5b.EXTERNAL_BINDINGS) :] == (
        ("runtime_shard_review_commit", None),
        ("runtime_shard_counter_review_commit", None),
        ("cloud_project_inventory_receipt_id", None),
        ("cloud_compile_receipt_id", None),
        ("cloud_runtime_import_receipt_id", None),
    )
    assert value.capabilities[:-1] == b5b.CAPABILITIES
    assert value.capabilities[-1] == ("credential_access", False)
    assert len(value.external_bindings) == 42
    assert len(value.capabilities) == 18
    assert all(item[1] is False for item in value.capabilities)
    assert all(item[1] is None for item in value.external_bindings)
    for name in (
        "filesystem_read_available",
        "provider_access_available",
        "production_input_read_available",
        "real_outcome_access_available",
        "qc_object_store_read_available",
        "qc_object_store_write_available",
        "upload_available",
        "compile_available",
        "launch_available",
        "result_access_available",
        "deployment_available",
        "orders_available",
        "trading_available",
    ):
        assert getattr(value, name) is False


def test_materialized_projection_imports_full_dependency_chain_offline(
    projection, tmp_path: Path
):
    value, _parent = projection
    for item in value.files:
        target = tmp_path / item.project_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.source_bytes)
    script = """
import json
from research.analyst_revisions_v2_qc import event_study
from research.analyst_revisions_v2_qc import global_input_schema
from research.analyst_revisions_v2_qc import global_input_bundle
from research.analyst_revisions_v2_qc import synthetic_input_transport
values = {
    "axis": len(event_study._reviewed_session_axis()),
    "schema": len(global_input_schema.render_qc_global_input_schema_bytes()),
    "bundle": len(global_input_bundle.render_qc_global_input_bundle_schema_bytes()),
    "transport": len(synthetic_input_transport.render_qc_synthetic_input_transport_schema_bytes()),
    "residuals": {
        name: sorted(key for key in module.__dict__ if key.startswith("_arv2_b5d_"))
        for name, module in (
            ("event", event_study),
            ("schema", global_input_schema),
            ("bundle", global_input_bundle),
            ("transport", synthetic_input_transport),
        )
    },
}
print(json.dumps(values, sort_keys=True))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result == {
        "axis": 3_435,
        "schema": 24_440,
        "bundle": 9_369,
        "transport": 3_517,
        "residuals": {
            "event": [],
            "schema": [],
            "bundle": [],
            "transport": [],
        },
    }


def test_schema_identity_and_exact_public_export_surface():
    payload = shard.render_qc_runtime_shard_projection_schema_bytes()
    assert payload.endswith(b"\n")
    assert len(payload) == 6_479
    assert shard.SCHEMA_ID == (
        "arv2-qc-runtime-shard-projection-schema-2909a08c686f8015"
    )
    assert shard.SCHEMA_SHA256 == (
        "2909a08c686f8015d89f82eab0d3ad6e2b9f72be0498213ac949f47841c446f4"
    )
    assert shard.SCHEMA_ARTIFACT_SHA256 == (
        "3cbafe2272af9dc07d5931ef25b20d23133093c9ad7900d15891108a426143f1"
    )
    assert hashlib.sha256(payload).hexdigest() == shard.SCHEMA_ARTIFACT_SHA256
    schema_document = json.loads(payload)
    assert schema_document["parent"] == {
        "assembly_artifact_sha256": shard.EXPECTED_PARENT_ASSEMBLY_ARTIFACT_SHA256,
        "assembly_id": shard.EXPECTED_PARENT_ASSEMBLY_ID,
        "assembly_sha256": shard.EXPECTED_PARENT_ASSEMBLY_SHA256,
        "schema_artifact_sha256": b5b.SCHEMA_ARTIFACT_SHA256,
        "schema_id": b5b.SCHEMA_ID,
        "schema_sha256": b5b.SCHEMA_SHA256,
        "source_files": [
            {
                "byte_count": byte_count,
                "project_path": project_path,
                "role": role,
                "sha256": digest,
            }
            for role, project_path, byte_count, digest in shard.EXPECTED_PARENT_FILES
        ],
    }
    assert schema_document["external_bindings"] == dict(shard.EXTERNAL_BINDINGS)
    assert schema_document["capabilities"] == dict(shard.CAPABILITIES)
    namespace: dict[str, object] = {}
    exec(
        "from research.analyst_revisions_v2_qc.runtime_shard_projection import *",
        namespace,
        namespace,
    )
    assert set(namespace) - {"__builtins__"} == set(shard.__all__)


def test_projection_document_independently_binds_schema_parent_and_identity(projection):
    value, _parent = projection
    document = json.loads(value._canonical_document)
    independently_rendered = (
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")
    assert independently_rendered == value._canonical_document
    assert document["schema_id"] == shard.SCHEMA_ID
    assert document["schema_sha256"] == shard.SCHEMA_SHA256
    assert document["schema_artifact_sha256"] == shard.SCHEMA_ARTIFACT_SHA256
    assert document["parent"] == {
        "assembly_artifact_sha256": shard.EXPECTED_PARENT_ASSEMBLY_ARTIFACT_SHA256,
        "assembly_id": shard.EXPECTED_PARENT_ASSEMBLY_ID,
        "assembly_sha256": shard.EXPECTED_PARENT_ASSEMBLY_SHA256,
        "schema_artifact_sha256": b5b.SCHEMA_ARTIFACT_SHA256,
        "schema_id": b5b.SCHEMA_ID,
        "schema_sha256": b5b.SCHEMA_SHA256,
    }
    assert document["external_bindings"] == dict(shard.EXTERNAL_BINDINGS)
    assert document["capabilities"] == dict(shard.CAPABILITIES)
    seed = dict(document)
    seed["projection_id"] = None
    seed["projection_sha256"] = None
    seed_bytes = (
        json.dumps(
            seed,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")
    semantic_sha256 = hashlib.sha256(seed_bytes).hexdigest()
    assert semantic_sha256 == value.projection_sha256 == (
        "ab0f9f546675909780ba4fa2032c0d5f317bd15503b97c6a4a6e475105f7b313"
    )
    assert value.projection_id == (
        "arv2-qc-runtime-shard-projection-ab0f9f5466759097"
    )
    assert (
        hashlib.sha256(independently_rendered).hexdigest()
        == value.projection_artifact_sha256
    )
    assert value.projection_artifact_sha256 == (
        "b109548c6b78d24cf909ea3947b36a2812f2ab251f2650f798cfe03928733fe7"
    )


def _rehash_projection(value, *, files=None, bindings=None):
    files = value.files if files is None else tuple(files)
    bindings = value.module_bindings if bindings is None else tuple(bindings)
    seed = shard._projection_document(
        projection_id=None,
        projection_sha256=None,
        files=files,
        bindings=bindings,
    )
    digest = hashlib.sha256(shard._canonical_bytes(seed)).hexdigest()
    projection_id = f"arv2-qc-runtime-shard-projection-{digest[:16]}"
    document = shard._projection_document(
        projection_id=projection_id,
        projection_sha256=digest,
        files=files,
        bindings=bindings,
    )
    canonical = shard._canonical_bytes(document)
    return dataclasses.replace(
        value,
        projection_id=projection_id,
        projection_sha256=digest,
        projection_artifact_sha256=hashlib.sha256(canonical).hexdigest(),
        files=files,
        module_bindings=bindings,
        total_projected_source_byte_count=sum(item.byte_count for item in files),
        largest_projected_source_character_count=max(
            item.character_count for item in files
        ),
        _canonical_document=canonical,
    )


@pytest.mark.parametrize(
    ("field", "factory"),
    (
        ("projection_id", lambda value: HostileStr(value)),
        ("project_file_count", lambda value: HostileInt(value)),
    ),
)
def test_projection_scalar_subclasses_refuse_without_comparison_callbacks(
    projection, field, factory
):
    value, _parent = projection
    HostileStr.calls = 0
    HostileInt.calls = 0
    changed = dataclasses.replace(value, **{field: factory(getattr(value, field))})
    with pytest.raises(shard.QcRuntimeShardProjectionError):
        shard.require_synthetic_qc_runtime_shard_projection(changed)
    assert HostileStr.calls == 0
    assert HostileInt.calls == 0


class HostileStr(str):
    calls = 0

    def __eq__(self, other):
        type(self).calls += 1
        return super().__eq__(other)


class HostileInt(int):
    calls = 0

    def __eq__(self, other):
        type(self).calls += 1
        return super().__eq__(other)


def test_nested_file_and_binding_scalar_subclasses_refuse_without_callbacks(
    projection,
):
    value, _parent = projection
    HostileStr.calls = 0
    first_file = dataclasses.replace(
        value.files[0], role=HostileStr(value.files[0].role)
    )
    with pytest.raises(shard.QcRuntimeShardProjectionError):
        shard.require_synthetic_qc_runtime_shard_projection(
            dataclasses.replace(value, files=(first_file, *value.files[1:]))
        )
    assert HostileStr.calls == 0

    first_binding = dataclasses.replace(
        value.module_bindings[0],
        canonical_project_path=HostileStr(
            value.module_bindings[0].canonical_project_path
        ),
    )
    with pytest.raises(shard.QcRuntimeShardProjectionError):
        shard.require_synthetic_qc_runtime_shard_projection(
            dataclasses.replace(
                value,
                module_bindings=(first_binding, *value.module_bindings[1:]),
            )
        )
    assert HostileStr.calls == 0


@pytest.mark.parametrize("container_field", ("files", "module_bindings"))
def test_top_level_list_substitution_refuses(projection, container_field):
    value, _parent = projection
    changed = dataclasses.replace(
        value, **{container_field: list(getattr(value, container_field))}
    )
    with pytest.raises(shard.QcRuntimeShardProjectionError):
        shard.require_synthetic_qc_runtime_shard_projection(changed)


def test_nested_carrier_path_list_and_authority_tuple_substitution_refuse(projection):
    value, _parent = projection
    changed_binding = dataclasses.replace(
        value.module_bindings[0],
        carrier_project_paths=list(
            value.module_bindings[0].carrier_project_paths
        ),
    )
    with pytest.raises(shard.QcRuntimeShardProjectionError):
        shard.require_synthetic_qc_runtime_shard_projection(
            dataclasses.replace(
                value,
                module_bindings=(changed_binding, *value.module_bindings[1:]),
            )
        )
    equal_but_new_capabilities = tuple(list(value.capabilities))
    assert equal_but_new_capabilities == value.capabilities
    assert equal_but_new_capabilities is not value.capabilities
    with pytest.raises(shard.QcRuntimeShardProjectionError):
        shard.require_synthetic_qc_runtime_shard_projection(
            dataclasses.replace(value, capabilities=equal_but_new_capabilities)
        )


@pytest.mark.parametrize("source_kind", ("facade", "carrier"))
def test_self_consistently_rehashed_generated_source_tampering_refuses(
    projection, source_kind
):
    value, _parent = projection
    index = next(
        index
        for index, item in enumerate(value.files)
        if item.source_kind == source_kind
    )
    item = value.files[index]
    changed_source = item.source_bytes + b"# hostile but valid trailing comment\n"
    changed_item = dataclasses.replace(
        item,
        source_bytes=changed_source,
        byte_count=len(changed_source),
        character_count=len(changed_source.decode("utf-8")),
        sha256=hashlib.sha256(changed_source).hexdigest(),
    )
    changed_files = list(value.files)
    changed_files[index] = changed_item
    changed = _rehash_projection(value, files=changed_files)
    with pytest.raises(shard.QcRuntimeShardProjectionError):
        shard.require_synthetic_qc_runtime_shard_projection(changed)


@pytest.mark.parametrize("mode", ("duplicate", "casefold"))
def test_duplicate_or_casefold_colliding_project_paths_refuse(projection, mode):
    value, _parent = projection
    files = list(value.files)
    source = files[4]
    target_path = files[3].project_path
    if mode == "casefold":
        target_path = target_path.upper()
    files[4] = dataclasses.replace(source, project_path=target_path)
    changed = _rehash_projection(value, files=files)
    with pytest.raises(shard.QcRuntimeShardProjectionError):
        shard.require_synthetic_qc_runtime_shard_projection(changed)


@pytest.mark.parametrize(
    "global_name",
    (
        "SCHEMA",
        "SHARDED_MODULES",
        "__all__",
        "_render_facade",
        "QcRuntimeProjectedFile",
        "require_synthetic_qc_lean_source_assembly",
        "_STATIC_CHECK",
    ),
)
def test_global_scalar_registry_helper_class_import_and_checker_rebinding_refuse(
    monkeypatch, global_name
):
    held = shard.render_qc_runtime_shard_projection_schema_bytes
    original = getattr(shard, global_name)
    if global_name == "SCHEMA":
        replacement = HostileStr(original)
    elif global_name in {"SHARDED_MODULES", "__all__"}:
        replacement = tuple(list(original))
    else:
        replacement = lambda *args, **kwargs: None
    with monkeypatch.context() as scoped:
        scoped.setattr(shard, global_name, replacement)
        with pytest.raises(shard.QcRuntimeShardProjectionError):
            held()


def test_parent_module_callable_rebinding_refuses_before_hostile_call(monkeypatch):
    held = shard.render_qc_runtime_shard_projection_schema_bytes
    calls = 0

    def hostile(*args, **kwargs):
        nonlocal calls
        calls += 1

    with monkeypatch.context() as scoped:
        scoped.setattr(
            shard._b5b_module,
            "require_synthetic_qc_lean_source_assembly",
            hostile,
        )
        with pytest.raises(shard.QcRuntimeShardProjectionError):
            held()
    assert calls == 0


def test_class_property_annotation_and_dataclass_field_mutations_refuse(monkeypatch):
    held = shard.render_qc_runtime_shard_projection_schema_bytes
    calls = 0

    def hostile_property(_self):
        nonlocal calls
        calls += 1
        return True

    with monkeypatch.context() as scoped:
        scoped.setattr(
            shard.SyntheticQcRuntimeShardProjection,
            "trading_available",
            property(hostile_property),
        )
        with pytest.raises(shard.QcRuntimeShardProjectionError):
            held()
    assert calls == 0

    annotations = shard.QcRuntimeProjectedFile.__annotations__
    original_annotation = annotations["role"]
    try:
        annotations["role"] = "hostile"
        with pytest.raises(shard.QcRuntimeShardProjectionError):
            held()
    finally:
        annotations["role"] = original_annotation

    field = dataclasses.fields(shard.QcRuntimeProjectedFile)[0]
    original_name = field.name
    HostileStr.calls = 0
    try:
        field.name = HostileStr("hostile")
        with pytest.raises(shard.QcRuntimeShardProjectionError):
            held()
    finally:
        field.name = original_name
    assert HostileStr.calls == 0


def test_public_wrapper_and_builtin_shadow_rebinding_refuse(monkeypatch):
    held = shard.render_qc_runtime_shard_projection_schema_bytes
    with monkeypatch.context() as scoped:
        scoped.setattr(
            shard,
            "render_qc_runtime_shard_projection_schema_bytes",
            lambda: b"hostile",
        )
        with pytest.raises(shard.QcRuntimeShardProjectionError):
            held()
    with monkeypatch.context() as scoped:
        scoped.setattr(shard, "len", lambda _value: 0, raising=False)
        with pytest.raises(shard.QcRuntimeShardProjectionError):
            held()


def test_globals_builtin_shadow_refuses_without_hostile_call(monkeypatch):
    held = shard.render_qc_runtime_shard_projection_schema_bytes
    calls = 0

    def hostile_globals():
        nonlocal calls
        calls += 1
        return {}

    with monkeypatch.context() as scoped:
        scoped.setattr(shard, "globals", hostile_globals, raising=False)
        with pytest.raises(shard.QcRuntimeShardProjectionError):
            held()
    assert calls == 0


@pytest.mark.parametrize(
    "global_name",
    (
        "_DEPENDENCY_CALLABLE_BINDINGS",
        "_CLASS_TOPOLOGIES",
        "_CORE_FUNCTION_STATES",
        "_BUILTIN_BINDINGS",
        "_SAFE_PATH",
    ),
)
def test_bootstrap_registry_and_alias_rebinding_refuses(monkeypatch, global_name):
    held = shard.render_qc_runtime_shard_projection_schema_bytes
    original = getattr(shard, global_name)
    replacement = tuple(list(original)) if type(original) is tuple else object()
    with monkeypatch.context() as scoped:
        scoped.setattr(shard, global_name, replacement)
        with pytest.raises(shard.QcRuntimeShardProjectionError):
            held()


def test_public_wrapper_metadata_mutation_is_seen_by_an_independent_wrapper():
    held = shard.require_synthetic_qc_runtime_shard_projection
    target = shard.render_qc_runtime_shard_projection_schema_bytes
    original = target.__qualname__
    try:
        target.__qualname__ = "hostile_render"
        with pytest.raises(shard.QcRuntimeShardProjectionError):
            held(object())
    finally:
        target.__qualname__ = original


def test_direct_reconstruct_refuses_hostile_binding_inventory_without_callback(
    projection,
):
    value, _parent = projection

    class HostileBinding:
        calls = 0

        def __eq__(self, _other):
            type(self).calls += 1
            return True

    changed = dataclasses.replace(
        value,
        module_bindings=(HostileBinding(), *value.module_bindings[1:]),
    )
    with pytest.raises(shard.QcRuntimeShardProjectionError):
        shard.reconstruct_canonical_module_bytes(changed, value.module_bindings[2])
    assert HostileBinding.calls == 0

    equal_clone = dataclasses.replace(value.module_bindings[0])
    assert equal_clone == value.module_bindings[0]
    assert equal_clone is not value.module_bindings[0]
    assert (
        shard.reconstruct_canonical_module_bytes(value, equal_clone)
        == shard.reconstruct_canonical_module_bytes(
            value,
            value.module_bindings[0],
        )
    )


def test_parent_mutation_after_second_authentication_is_refused(monkeypatch):
    _candidate, _fixture, _plan, parent = _assembly()
    target = parent.files[0]
    original_source = target.source_bytes
    real_validator = shard._PINNED_REQUIRE_PARENT
    calls = 0

    def racing_validator(value):
        nonlocal calls
        result = real_validator(value)
        calls += 1
        if calls == 2:
            object.__setattr__(target, "source_bytes", original_source + b"# race\n")
        return result

    try:
        with monkeypatch.context() as scoped:
            scoped.setattr(shard, "_PINNED_REQUIRE_PARENT", racing_validator)
            with pytest.raises(
                shard.QcRuntimeShardProjectionError,
                match="changed during extraction",
            ):
                shard._extract_parent_files(parent)
    finally:
        object.__setattr__(target, "source_bytes", original_source)
    assert calls == 2


@pytest.mark.parametrize("mutation", ("identity", "container"))
def test_parent_identity_or_container_race_after_second_authentication_refuses(
    monkeypatch, mutation
):
    _candidate, _fixture, _plan, parent = _assembly()
    original_id = parent.assembly_id
    original_files = parent.files
    real_validator = shard._PINNED_REQUIRE_PARENT
    calls = 0

    def racing_validator(value):
        nonlocal calls
        result = real_validator(value)
        calls += 1
        if calls == 2:
            if mutation == "identity":
                object.__setattr__(value, "assembly_id", HostileStr(original_id))
            else:
                object.__setattr__(value, "files", list(original_files))
        return result

    HostileStr.calls = 0
    try:
        with monkeypatch.context() as scoped:
            scoped.setattr(shard, "_PINNED_REQUIRE_PARENT", racing_validator)
            with pytest.raises(
                shard.QcRuntimeShardProjectionError,
                match="changed during extraction",
            ):
                shard._extract_parent_files(parent)
    finally:
        object.__setattr__(parent, "assembly_id", original_id)
        object.__setattr__(parent, "files", original_files)
    assert calls == 2
    assert HostileStr.calls == 0


def test_projection_module_remains_compatible_with_lane_no_io_closure():
    source = Path(shard.__file__).read_text(encoding="utf-8")
    assert _no_io_violations(source) == ()
