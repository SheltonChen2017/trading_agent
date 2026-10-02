"""Pure ARV2-4F-B5D exact-source runtime sharding projection.

This module performs no filesystem, environment, credential, provider,
QuantConnect, Object Store, compile, launch, result, order, or trading action.
It accepts only an already-built B5B value and returns generated project-file
bytes.  The generated facades reconstruct the exact reviewed canonical module
bytes before executing them in their canonical module namespace.
"""
from __future__ import annotations

import ast
import base64
import dataclasses
import hashlib
import json
import re
import textwrap

from research.analyst_revisions_v2_qc import lean_source_assembly as _b5b_module
from research.analyst_revisions_v2_qc.lean_source_assembly import (
    CAPABILITIES as B5B_CAPABILITIES,
    EXTERNAL_BINDINGS as B5B_EXTERNAL_BINDINGS,
    SCHEMA_ARTIFACT_SHA256 as B5B_SCHEMA_ARTIFACT_SHA256,
    SCHEMA_ID as B5B_SCHEMA_ID,
    SCHEMA_SHA256 as B5B_SCHEMA_SHA256,
    SyntheticLeanProjectAssembly,
    require_synthetic_qc_lean_source_assembly,
)

_PINNED_REQUIRE_PARENT = require_synthetic_qc_lean_source_assembly
_PINNED_PARENT_CLASS = SyntheticLeanProjectAssembly


SCHEMA = "arv2-qc-runtime-shard-projection-schema-v1"
STATUS = "offline_exact_source_sharding_only_no_physical_qc_action"
AUTHORITY = (
    "pure_values_only_no_filesystem_environment_credential_provider_input_"
    "outcome_object_store_project_upload_compile_launch_result_deployment_"
    "order_or_trading_authority"
)
HASH_DOMAIN = "arv2-qc-runtime-shard-projection-v1"
QC_OBSERVED_SOURCE_CHARACTER_LIMIT = 64_000
MAX_PROJECTED_SOURCE_CHARACTERS = 60_000
BASE64_CHUNK_CHARACTERS = 50_000
BASE64_LITERAL_WIDTH = 100
EXPECTED_PROJECT_FILE_COUNT = 23
EXPECTED_CARRIER_FILE_COUNT = 12

EXPECTED_PARENT_ASSEMBLY_ID = "arv2-qc-lean-source-assembly-8303f3323ff16ab7"
EXPECTED_PARENT_ASSEMBLY_SHA256 = (
    "8303f3323ff16ab7da6c03c587bfbbf4a8d8ecb356eb8912307c2c78a75c1266"
)
EXPECTED_PARENT_ASSEMBLY_ARTIFACT_SHA256 = (
    "56d3f77e731f6a13b5dbfb9bcbfcd8e89261a226400b744cf2c0fa3d3b400bdd"
)
EXPECTED_PARENT_SCHEMA_ID = "arv2-qc-lean-source-assembly-ae4c1324f36cc6fc"
EXPECTED_PARENT_SCHEMA_SHA256 = (
    "ae4c1324f36cc6fca0218f474bdc091bf82862e8f21ada35e01a09b022bb77a5"
)
EXPECTED_PARENT_SCHEMA_ARTIFACT_SHA256 = (
    "532aeb471fed96c525f8be9db84694c546c1cccc6008347a43efadfac678ac20"
)
EXPECTED_PARENT_IDENTITY = (
    EXPECTED_PARENT_ASSEMBLY_ID,
    EXPECTED_PARENT_ASSEMBLY_SHA256,
    EXPECTED_PARENT_ASSEMBLY_ARTIFACT_SHA256,
)

EXPECTED_PARENT_FILES = (
    (
        "lean_entry",
        "main.py",
        3_328,
        "327f126311c12e9f37297f229a3946a6cb1f2bbe26ed6c746cf140b26c2e6bf9",
    ),
    (
        "research_package_marker",
        "research/__init__.py",
        0,
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    ),
    (
        "qc_package_marker",
        "research/analyst_revisions_v2_qc/__init__.py",
        487,
        "ce8f07aeab0358f5eb3241190169d4f967a5423dc88719f0783a83d010d43dcc",
    ),
    (
        "event_study_core",
        "research/analyst_revisions_v2_qc/event_study.py",
        109_226,
        "0f1e6f69c4bde56bb42a49d24d42b0a27cb2417d3c7bf8f1ea196e15fa0628fe",
    ),
    (
        "global_input_bundle",
        "research/analyst_revisions_v2_qc/global_input_bundle.py",
        140_983,
        "cdf24e6bdf3bf63e4635d7524e213f9db25abe308c3973999c1215fb5a4cec18",
    ),
    (
        "global_input_schema",
        "research/analyst_revisions_v2_qc/global_input_schema.py",
        94_959,
        "f0da3f016cdd794514146a7811d3606b3c8be9d94ffca80e1c28790af519016a",
    ),
    (
        "object_store_read_contract",
        "research/analyst_revisions_v2_qc/object_store_read_contract.py",
        57_361,
        "bf370a894986cec8ac341ef8f43bce91aeab4568295ab94c281ce5defaa4d2e3",
    ),
    (
        "run_contract",
        "research/analyst_revisions_v2_qc/run_contract.py",
        28_825,
        "a72aa500a5c2d2fe68cfe9a00e6531a8c1a241e212cb8df8e2a7a56dba3d77d5",
    ),
    (
        "synthetic_input_transport",
        "research/analyst_revisions_v2_qc/synthetic_input_transport.py",
        65_144,
        "c473bf91a99fd5207ab10407ea85971db9e24e75f7d29ccf64b38c628538ebe9",
    ),
    (
        "data_package_marker",
        "data/__init__.py",
        0,
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    ),
    (
        "exchange_calendar",
        "data/exchange_calendar.py",
        8_796,
        "174a032efce4082b8661eabe84b0cf6094048e937722bdf1659c8cb6c7decb89",
    ),
)

SHARDED_MODULES = (
    (
        "event_study_core",
        "research/analyst_revisions_v2_qc/event_study.py",
        109_226,
        "0f1e6f69c4bde56bb42a49d24d42b0a27cb2417d3c7bf8f1ea196e15fa0628fe",
        3,
    ),
    (
        "global_input_bundle",
        "research/analyst_revisions_v2_qc/global_input_bundle.py",
        140_983,
        "cdf24e6bdf3bf63e4635d7524e213f9db25abe308c3973999c1215fb5a4cec18",
        4,
    ),
    (
        "global_input_schema",
        "research/analyst_revisions_v2_qc/global_input_schema.py",
        94_959,
        "f0da3f016cdd794514146a7811d3606b3c8be9d94ffca80e1c28790af519016a",
        3,
    ),
    (
        "synthetic_input_transport",
        "research/analyst_revisions_v2_qc/synthetic_input_transport.py",
        65_144,
        "c473bf91a99fd5207ab10407ea85971db9e24e75f7d29ccf64b38c628538ebe9",
        2,
    ),
)

CAPABILITIES = (*B5B_CAPABILITIES, ("credential_access", False))
EXTERNAL_BINDINGS = (
    *B5B_EXTERNAL_BINDINGS,
    ("runtime_shard_review_commit", None),
    ("runtime_shard_counter_review_commit", None),
    ("cloud_project_inventory_receipt_id", None),
    ("cloud_compile_receipt_id", None),
    ("cloud_runtime_import_receipt_id", None),
)

__all__ = (
    "AUTHORITY",
    "BASE64_CHUNK_CHARACTERS",
    "BASE64_LITERAL_WIDTH",
    "CAPABILITIES",
    "EXPECTED_CARRIER_FILE_COUNT",
    "EXPECTED_PARENT_ASSEMBLY_ARTIFACT_SHA256",
    "EXPECTED_PARENT_ASSEMBLY_ID",
    "EXPECTED_PARENT_ASSEMBLY_SHA256",
    "EXPECTED_PARENT_SCHEMA_ARTIFACT_SHA256",
    "EXPECTED_PARENT_SCHEMA_ID",
    "EXPECTED_PARENT_SCHEMA_SHA256",
    "EXPECTED_PARENT_FILES",
    "EXPECTED_PROJECT_FILE_COUNT",
    "EXTERNAL_BINDINGS",
    "HASH_DOMAIN",
    "MAX_PROJECTED_SOURCE_CHARACTERS",
    "QC_OBSERVED_SOURCE_CHARACTER_LIMIT",
    "QcRuntimeModuleShardBinding",
    "QcRuntimeProjectedFile",
    "QcRuntimeShardProjectionError",
    "SCHEMA",
    "SCHEMA_ARTIFACT_SHA256",
    "SCHEMA_ID",
    "SCHEMA_SHA256",
    "SHARDED_MODULES",
    "STATUS",
    "SyntheticQcRuntimeShardProjection",
    "build_synthetic_qc_runtime_shard_projection",
    "reconstruct_canonical_module_bytes",
    "render_qc_runtime_shard_projection_schema_bytes",
    "require_synthetic_qc_runtime_shard_projection",
)

_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_PATH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*\Z")
_SHARDED_BY_PATH = {item[1]: item for item in SHARDED_MODULES}


class QcRuntimeShardProjectionError(ValueError):
    """The B5D parent, generated source, or projection is not authentic."""


@dataclasses.dataclass(frozen=True, slots=True)
class QcRuntimeProjectedFile:
    role: str
    project_path: str
    source_kind: str
    source_bytes: bytes = dataclasses.field(repr=False)
    byte_count: int
    character_count: int
    sha256: str


@dataclasses.dataclass(frozen=True, slots=True)
class QcRuntimeModuleShardBinding:
    role: str
    canonical_project_path: str
    canonical_byte_count: int
    canonical_character_count: int
    canonical_sha256: str
    facade_project_path: str
    carrier_project_paths: tuple[str, ...]
    carrier_file_count: int


@dataclasses.dataclass(frozen=True, slots=True)
class SyntheticQcRuntimeShardProjection:
    projection_id: str
    projection_sha256: str
    projection_artifact_sha256: str
    parent_assembly_id: str
    parent_assembly_sha256: str
    parent_assembly_artifact_sha256: str
    files: tuple[QcRuntimeProjectedFile, ...]
    module_bindings: tuple[QcRuntimeModuleShardBinding, ...]
    project_file_count: int
    carrier_file_count: int
    total_projected_source_byte_count: int
    largest_projected_source_character_count: int
    canonical_runtime_source_reconstruction_authenticated: bool
    cloud_runtime_execution_authenticated: bool
    physical_adapter_present: bool
    cloud_compile_performed: bool
    backtest_performed: bool
    external_bindings: tuple[tuple[str, None], ...]
    capabilities: tuple[tuple[str, bool], ...]
    _canonical_document: bytes = dataclasses.field(repr=False)

    @property
    def filesystem_read_available(self) -> bool:
        return False

    @property
    def provider_access_available(self) -> bool:
        return False

    @property
    def production_input_read_available(self) -> bool:
        return False

    @property
    def real_outcome_access_available(self) -> bool:
        return False

    @property
    def qc_object_store_read_available(self) -> bool:
        return False

    @property
    def qc_object_store_write_available(self) -> bool:
        return False

    @property
    def upload_available(self) -> bool:
        return False

    @property
    def compile_available(self) -> bool:
        return False

    @property
    def launch_available(self) -> bool:
        return False

    @property
    def result_access_available(self) -> bool:
        return False

    @property
    def deployment_available(self) -> bool:
        return False

    @property
    def orders_available(self) -> bool:
        return False

    @property
    def trading_available(self) -> bool:
        return False


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


def _schema_seed_document() -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "authority": AUTHORITY,
        "hash_domain": HASH_DOMAIN,
        "schema_id": None,
        "schema_sha256": None,
        "parent": {
            "schema_id": EXPECTED_PARENT_SCHEMA_ID,
            "schema_sha256": EXPECTED_PARENT_SCHEMA_SHA256,
            "schema_artifact_sha256": EXPECTED_PARENT_SCHEMA_ARTIFACT_SHA256,
            "assembly_id": EXPECTED_PARENT_ASSEMBLY_ID,
            "assembly_sha256": EXPECTED_PARENT_ASSEMBLY_SHA256,
            "assembly_artifact_sha256": EXPECTED_PARENT_ASSEMBLY_ARTIFACT_SHA256,
            "source_files": [
                {
                    "role": role,
                    "project_path": path,
                    "byte_count": byte_count,
                    "sha256": digest,
                }
                for role, path, byte_count, digest in EXPECTED_PARENT_FILES
            ],
        },
        "sharded_modules": [
            {
                "role": role,
                "project_path": path,
                "canonical_byte_count": byte_count,
                "canonical_sha256": digest,
                "carrier_file_count": carrier_count,
            }
            for role, path, byte_count, digest, carrier_count in SHARDED_MODULES
        ],
        "limits": {
            "observed_qc_characters": QC_OBSERVED_SOURCE_CHARACTER_LIMIT,
            "projected_max_characters": MAX_PROJECTED_SOURCE_CHARACTERS,
            "base64_chunk_characters": BASE64_CHUNK_CHARACTERS,
            "base64_literal_width": BASE64_LITERAL_WIDTH,
            "project_file_count": EXPECTED_PROJECT_FILE_COUNT,
            "carrier_file_count": EXPECTED_CARRIER_FILE_COUNT,
        },
        "truth": {
            "canonical_runtime_source_reconstruction_authenticated": True,
            "cloud_runtime_execution_authenticated": False,
            "physical_adapter_present": False,
            "cloud_compile_performed": False,
            "backtest_performed": False,
        },
        "external_bindings": {name: value for name, value in EXTERNAL_BINDINGS},
        "capabilities": {name: value for name, value in CAPABILITIES},
    }


SCHEMA_SHA256 = (
    "2909a08c686f8015d89f82eab0d3ad6e2b9f72be0498213ac949f47841c446f4"
)
SCHEMA_ID = "arv2-qc-runtime-shard-projection-schema-2909a08c686f8015"


def _schema_document() -> dict[str, object]:
    document = _schema_seed_document()
    document["schema_id"] = SCHEMA_ID
    document["schema_sha256"] = SCHEMA_SHA256
    return document


SCHEMA_ARTIFACT_SHA256 = (
    "3cbafe2272af9dc07d5931ef25b20d23133093c9ad7900d15891108a426143f1"
)


def render_qc_runtime_shard_projection_schema_bytes() -> bytes:
    payload = _canonical_bytes(_schema_document())
    if (
        hashlib.sha256(_canonical_bytes(_schema_seed_document())).hexdigest()
        != SCHEMA_SHA256
        or hashlib.sha256(payload).hexdigest() != SCHEMA_ARTIFACT_SHA256
    ):
        raise QcRuntimeShardProjectionError("B5D schema identity changed")
    return payload


def _character_count(source_bytes: bytes) -> int:
    if type(source_bytes) is not bytes:
        raise QcRuntimeShardProjectionError("source must be exact bytes")
    if source_bytes.startswith(b"\xef\xbb\xbf") or b"\r" in source_bytes:
        raise QcRuntimeShardProjectionError("source must be canonical UTF-8/LF")
    try:
        source = source_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise QcRuntimeShardProjectionError("source is not strict UTF-8") from exc
    if source and not source.endswith("\n"):
        raise QcRuntimeShardProjectionError("nonempty source needs final LF")
    return len(source)


def _carrier_stem(canonical_project_path: str) -> str:
    stem = canonical_project_path.rsplit("/", 1)[-1]
    if not stem.endswith(".py"):
        raise QcRuntimeShardProjectionError("canonical module is not Python")
    stem = stem[:-3]
    if re.fullmatch(r"[a-z][a-z0-9_]*", stem) is None:
        raise QcRuntimeShardProjectionError("canonical module stem is unsafe")
    return stem


def _carrier_path(canonical_project_path: str, ordinal: int) -> str:
    directory = canonical_project_path.rsplit("/", 1)[0]
    stem = _carrier_stem(canonical_project_path)
    return f"{directory}/_arv2_b5d_{stem}_source_{ordinal:02d}.py"


def _carrier_module_name(canonical_project_path: str, ordinal: int) -> str:
    stem = _carrier_stem(canonical_project_path)
    return f"_arv2_b5d_{stem}_source_{ordinal:02d}"


def _render_carrier(
    *, role: str, canonical_project_path: str, ordinal: int, payload: bytes
) -> bytes:
    if type(payload) is not bytes or not payload:
        raise QcRuntimeShardProjectionError("carrier payload must be bytes")
    try:
        encoded = payload.decode("ascii")
    except UnicodeDecodeError as exc:
        raise QcRuntimeShardProjectionError("base64 carrier is not ASCII") from exc
    if len(encoded) > BASE64_CHUNK_CHARACTERS:
        raise QcRuntimeShardProjectionError("base64 carrier chunk is too large")
    lines = "\n".join(
        f'    b"{part}"'
        for part in textwrap.wrap(encoded, BASE64_LITERAL_WIDTH)
    )
    source = (
        f'"""ARV2-4F-B5D generated source carrier: {role} {ordinal:02d}."""\n'
        "CHUNK_B64 = (\n"
        f"{lines}\n"
        ")\n"
    ).encode("ascii")
    return source


def _render_facade(
    *,
    canonical_project_path: str,
    canonical_source: bytes,
    carrier_count: int,
) -> bytes:
    stem = _carrier_stem(canonical_project_path)
    aliases = tuple(f"_arv2_b5d_chunk_{index:02d}" for index in range(carrier_count))
    imports = tuple(
        "from ."
        f"{_carrier_module_name(canonical_project_path, index)} "
        f"import CHUNK_B64 as {aliases[index]}"
        for index in range(carrier_count)
    )
    joined_aliases = ", ".join(aliases)
    digest = hashlib.sha256(canonical_source).hexdigest()
    cleanup = ", ".join(
        (
            "_arv2_b5d_base64",
            "_arv2_b5d_hashlib",
            *aliases,
            "_arv2_b5d_encoded",
            "_arv2_b5d_source",
            "_arv2_b5d_code",
        )
    )
    lines = (
        f'"""ARV2-4F-B5D exact-source facade for {stem}."""',
        "import base64 as _arv2_b5d_base64",
        "import hashlib as _arv2_b5d_hashlib",
        *imports,
        f'_arv2_b5d_encoded = b"".join(({joined_aliases},))',
        (
            "_arv2_b5d_source = _arv2_b5d_base64.b64decode("
            "_arv2_b5d_encoded, validate=True)"
        ),
        (
            "if type(_arv2_b5d_source) is not bytes "
            f"or len(_arv2_b5d_source) != {len(canonical_source)} "
            "or _arv2_b5d_hashlib.sha256(_arv2_b5d_source).hexdigest() "
            f'!= "{digest}":'
        ),
        '    raise RuntimeError("ARV2-4F-B5D canonical source identity changed")',
        (
            "_arv2_b5d_code = compile(_arv2_b5d_source, "
            f'"{canonical_project_path}", "exec", dont_inherit=True)'
        ),
        "exec(_arv2_b5d_code, globals(), globals())",
        f"del {cleanup}",
        "",
    )
    return "\n".join(lines).encode("ascii")


def _projected_file(
    *, role: str, project_path: str, source_kind: str, source_bytes: bytes
) -> QcRuntimeProjectedFile:
    if (
        type(role) is not str
        or not role
        or type(project_path) is not str
        or _SAFE_PATH.fullmatch(project_path) is None
        or type(source_kind) is not str
        or source_kind not in {"retained", "facade", "carrier"}
    ):
        raise QcRuntimeShardProjectionError("projected file metadata is invalid")
    character_count = _character_count(source_bytes)
    if character_count > MAX_PROJECTED_SOURCE_CHARACTERS:
        raise QcRuntimeShardProjectionError("projected file exceeds B5D limit")
    try:
        ast.parse(source_bytes, filename=project_path)
    except (SyntaxError, ValueError, TypeError) as exc:
        raise QcRuntimeShardProjectionError("projected source is not Python") from exc
    return QcRuntimeProjectedFile(
        role=role,
        project_path=project_path,
        source_kind=source_kind,
        source_bytes=bytes(source_bytes),
        byte_count=len(source_bytes),
        character_count=character_count,
        sha256=hashlib.sha256(source_bytes).hexdigest(),
    )


def _file_document(value: QcRuntimeProjectedFile) -> dict[str, object]:
    return {
        "role": value.role,
        "project_path": value.project_path,
        "source_kind": value.source_kind,
        "byte_count": value.byte_count,
        "character_count": value.character_count,
        "sha256": value.sha256,
    }


def _binding_document(value: QcRuntimeModuleShardBinding) -> dict[str, object]:
    return {
        "role": value.role,
        "canonical_project_path": value.canonical_project_path,
        "canonical_byte_count": value.canonical_byte_count,
        "canonical_character_count": value.canonical_character_count,
        "canonical_sha256": value.canonical_sha256,
        "facade_project_path": value.facade_project_path,
        "carrier_project_paths": list(value.carrier_project_paths),
        "carrier_file_count": value.carrier_file_count,
    }


def _projection_document(
    *,
    projection_id: str | None,
    projection_sha256: str | None,
    files: tuple[QcRuntimeProjectedFile, ...],
    bindings: tuple[QcRuntimeModuleShardBinding, ...],
) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "authority": AUTHORITY,
        "hash_domain": HASH_DOMAIN,
        "schema_id": SCHEMA_ID,
        "schema_sha256": SCHEMA_SHA256,
        "schema_artifact_sha256": SCHEMA_ARTIFACT_SHA256,
        "projection_id": projection_id,
        "projection_sha256": projection_sha256,
        "parent": {
            "schema_id": EXPECTED_PARENT_SCHEMA_ID,
            "schema_sha256": EXPECTED_PARENT_SCHEMA_SHA256,
            "schema_artifact_sha256": EXPECTED_PARENT_SCHEMA_ARTIFACT_SHA256,
            "assembly_id": EXPECTED_PARENT_ASSEMBLY_ID,
            "assembly_sha256": EXPECTED_PARENT_ASSEMBLY_SHA256,
            "assembly_artifact_sha256": EXPECTED_PARENT_ASSEMBLY_ARTIFACT_SHA256,
        },
        "limits": {
            "observed_qc_characters": QC_OBSERVED_SOURCE_CHARACTER_LIMIT,
            "projected_max_characters": MAX_PROJECTED_SOURCE_CHARACTERS,
            "base64_chunk_characters": BASE64_CHUNK_CHARACTERS,
            "base64_literal_width": BASE64_LITERAL_WIDTH,
        },
        "files": [_file_document(item) for item in files],
        "module_bindings": [_binding_document(item) for item in bindings],
        "truth": {
            "canonical_runtime_source_reconstruction_authenticated": True,
            "cloud_runtime_execution_authenticated": False,
            "physical_adapter_present": False,
            "cloud_compile_performed": False,
            "backtest_performed": False,
        },
        "external_bindings": {name: value for name, value in EXTERNAL_BINDINGS},
        "capabilities": {name: value for name, value in CAPABILITIES},
    }


def _extract_parent_files(
    source_assembly: SyntheticLeanProjectAssembly,
) -> tuple[tuple[str, str, bytes, int, str], ...]:
    if type(source_assembly) is not _PINNED_PARENT_CLASS:
        raise QcRuntimeShardProjectionError("B5B parent type changed")
    _PINNED_REQUIRE_PARENT(source_assembly)
    identity = (
        source_assembly.assembly_id,
        source_assembly.assembly_hash,
        source_assembly.assembly_artifact_sha256,
    )
    if identity != EXPECTED_PARENT_IDENTITY:
        raise QcRuntimeShardProjectionError("B5B parent identity changed")
    if type(source_assembly.files) is not tuple:
        raise QcRuntimeShardProjectionError("B5B source inventory changed")
    parent_file_objects = tuple(source_assembly.files)
    snapshot = tuple(
        (
            item.role,
            item.project_path,
            bytes(item.source_bytes),
            item.byte_count,
            item.sha256,
        )
        for item in source_assembly.files
    )
    if any(
        type(role) is not str
        or type(project_path) is not str
        or type(source) is not bytes
        or type(byte_count) is not int
        or type(digest) is not str
        for role, project_path, source, byte_count, digest in snapshot
    ):
        raise QcRuntimeShardProjectionError("B5B source snapshot topology changed")
    _PINNED_REQUIRE_PARENT(source_assembly)
    second_identity = (
        source_assembly.assembly_id,
        source_assembly.assembly_hash,
        source_assembly.assembly_artifact_sha256,
    )
    second_files = source_assembly.files
    if (
        any(type(value) is not str for value in second_identity)
        or type(second_files) is not tuple
        or len(second_files) != len(parent_file_objects)
        or any(
            current is not expected
            for current, expected in zip(
                second_files,
                parent_file_objects,
                strict=True,
            )
        )
    ):
        raise QcRuntimeShardProjectionError("B5B source changed during extraction")
    second = tuple(
        (
            item.role,
            item.project_path,
            bytes(item.source_bytes),
            item.byte_count,
            item.sha256,
        )
        for item in second_files
    )
    if any(
        type(role) is not str
        or type(project_path) is not str
        or type(source) is not bytes
        or type(byte_count) is not int
        or type(digest) is not str
        for role, project_path, source, byte_count, digest in second
    ):
        raise QcRuntimeShardProjectionError("B5B source changed during extraction")
    descriptors = tuple(
        (role, project_path, byte_count, digest)
        for role, project_path, _source, byte_count, digest in snapshot
    )
    if (
        identity != second_identity
        or second_identity != EXPECTED_PARENT_IDENTITY
        or snapshot != second
        or descriptors != EXPECTED_PARENT_FILES
    ):
        raise QcRuntimeShardProjectionError("B5B source changed during extraction")
    return snapshot


def build_synthetic_qc_runtime_shard_projection(
    *, source_assembly: SyntheticLeanProjectAssembly
) -> SyntheticQcRuntimeShardProjection:
    """Return a detached, deterministic, no-I/O B5D project projection."""

    source_snapshot = _extract_parent_files(source_assembly)
    projected: list[QcRuntimeProjectedFile] = []
    bindings: list[QcRuntimeModuleShardBinding] = []
    seen_sharded_paths: set[str] = set()
    for role, project_path, source_bytes, byte_count, digest in source_snapshot:
        if (
            type(role) is not str
            or type(project_path) is not str
            or type(source_bytes) is not bytes
            or type(byte_count) is not int
            or type(digest) is not str
            or len(source_bytes) != byte_count
            or hashlib.sha256(source_bytes).hexdigest() != digest
        ):
            raise QcRuntimeShardProjectionError("B5B source snapshot is invalid")
        expected = _SHARDED_BY_PATH.get(project_path)
        if expected is None:
            projected.append(
                _projected_file(
                    role=role,
                    project_path=project_path,
                    source_kind="retained",
                    source_bytes=source_bytes,
                )
            )
            continue
        expected_role, _, expected_bytes, expected_hash, expected_carriers = expected
        if (
            role != expected_role
            or byte_count != expected_bytes
            or digest != expected_hash
            or _character_count(source_bytes) != expected_bytes
        ):
            raise QcRuntimeShardProjectionError("sharded canonical source changed")
        encoded = base64.b64encode(source_bytes)
        chunks = tuple(
            encoded[index : index + BASE64_CHUNK_CHARACTERS]
            for index in range(0, len(encoded), BASE64_CHUNK_CHARACTERS)
        )
        if len(chunks) != expected_carriers:
            raise QcRuntimeShardProjectionError("carrier census changed")
        carrier_paths = tuple(
            _carrier_path(project_path, index) for index in range(len(chunks))
        )
        facade = _render_facade(
            canonical_project_path=project_path,
            canonical_source=source_bytes,
            carrier_count=len(chunks),
        )
        projected.append(
            _projected_file(
                role=f"{role}_runtime_facade",
                project_path=project_path,
                source_kind="facade",
                source_bytes=facade,
            )
        )
        for index, (path, chunk) in enumerate(zip(carrier_paths, chunks, strict=True)):
            projected.append(
                _projected_file(
                    role=f"{role}_source_carrier_{index:02d}",
                    project_path=path,
                    source_kind="carrier",
                    source_bytes=_render_carrier(
                        role=role,
                        canonical_project_path=project_path,
                        ordinal=index,
                        payload=chunk,
                    ),
                )
            )
        bindings.append(
            QcRuntimeModuleShardBinding(
                role=role,
                canonical_project_path=project_path,
                canonical_byte_count=byte_count,
                canonical_character_count=expected_bytes,
                canonical_sha256=digest,
                facade_project_path=project_path,
                carrier_project_paths=carrier_paths,
                carrier_file_count=len(carrier_paths),
            )
        )
        seen_sharded_paths.add(project_path)

    files = tuple(projected)
    module_bindings = tuple(bindings)
    paths = tuple(item.project_path for item in files)
    if (
        seen_sharded_paths != set(_SHARDED_BY_PATH)
        or len(files) != EXPECTED_PROJECT_FILE_COUNT
        or len([item for item in files if item.source_kind == "carrier"])
        != EXPECTED_CARRIER_FILE_COUNT
        or len(paths) != len(set(paths))
        or len(paths) != len({path.casefold() for path in paths})
        or any(item.character_count > MAX_PROJECTED_SOURCE_CHARACTERS for item in files)
    ):
        raise QcRuntimeShardProjectionError("projected inventory is not exact")
    seed = _projection_document(
        projection_id=None,
        projection_sha256=None,
        files=files,
        bindings=module_bindings,
    )
    projection_sha256 = hashlib.sha256(_canonical_bytes(seed)).hexdigest()
    projection_id = f"arv2-qc-runtime-shard-projection-{projection_sha256[:16]}"
    document = _projection_document(
        projection_id=projection_id,
        projection_sha256=projection_sha256,
        files=files,
        bindings=module_bindings,
    )
    canonical_document = _canonical_bytes(document)
    return SyntheticQcRuntimeShardProjection(
        projection_id=projection_id,
        projection_sha256=projection_sha256,
        projection_artifact_sha256=hashlib.sha256(canonical_document).hexdigest(),
        parent_assembly_id=EXPECTED_PARENT_ASSEMBLY_ID,
        parent_assembly_sha256=EXPECTED_PARENT_ASSEMBLY_SHA256,
        parent_assembly_artifact_sha256=EXPECTED_PARENT_ASSEMBLY_ARTIFACT_SHA256,
        files=files,
        module_bindings=module_bindings,
        project_file_count=len(files),
        carrier_file_count=EXPECTED_CARRIER_FILE_COUNT,
        total_projected_source_byte_count=sum(item.byte_count for item in files),
        largest_projected_source_character_count=max(
            item.character_count for item in files
        ),
        canonical_runtime_source_reconstruction_authenticated=True,
        cloud_runtime_execution_authenticated=False,
        physical_adapter_present=False,
        cloud_compile_performed=False,
        backtest_performed=False,
        external_bindings=EXTERNAL_BINDINGS,
        capabilities=CAPABILITIES,
        _canonical_document=canonical_document,
    )


def _carrier_payload(source: bytes, *, expected_path: str) -> bytes:
    try:
        tree = ast.parse(source, filename=expected_path)
    except (SyntaxError, ValueError, TypeError) as exc:
        raise QcRuntimeShardProjectionError("carrier source is invalid") from exc
    if len(tree.body) != 2 or not (
        isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and type(tree.body[0].value.value) is str
        and isinstance(tree.body[1], ast.Assign)
        and len(tree.body[1].targets) == 1
        and isinstance(tree.body[1].targets[0], ast.Name)
        and tree.body[1].targets[0].id == "CHUNK_B64"
        and isinstance(tree.body[1].value, ast.Constant)
        and type(tree.body[1].value.value) is bytes
    ):
        raise QcRuntimeShardProjectionError("carrier grammar changed")
    return tree.body[1].value.value


def reconstruct_canonical_module_bytes(
    projection: SyntheticQcRuntimeShardProjection,
    binding: QcRuntimeModuleShardBinding,
) -> bytes:
    """Reconstruct and authenticate one canonical source without executing it."""

    if type(projection) is not SyntheticQcRuntimeShardProjection:
        raise QcRuntimeShardProjectionError("projection type changed")
    if type(binding) is not QcRuntimeModuleShardBinding:
        raise QcRuntimeShardProjectionError("binding type changed")
    if (
        type(projection.files) is not tuple
        or type(projection.module_bindings) is not tuple
    ):
        raise QcRuntimeShardProjectionError("projection containers changed")
    for item in projection.files:
        if (
            type(item) is not QcRuntimeProjectedFile
            or type(item.role) is not str
            or type(item.project_path) is not str
            or type(item.source_kind) is not str
            or type(item.source_bytes) is not bytes
            or type(item.byte_count) is not int
            or type(item.character_count) is not int
            or type(item.sha256) is not str
            or item.byte_count != len(item.source_bytes)
            or item.character_count != _character_count(item.source_bytes)
            or item.sha256 != hashlib.sha256(item.source_bytes).hexdigest()
        ):
            raise QcRuntimeShardProjectionError("projected file topology changed")
    if (
        type(binding.role) is not str
        or type(binding.canonical_project_path) is not str
        or type(binding.canonical_byte_count) is not int
        or type(binding.canonical_character_count) is not int
        or type(binding.canonical_sha256) is not str
        or type(binding.facade_project_path) is not str
        or type(binding.carrier_project_paths) is not tuple
        or any(type(path) is not str for path in binding.carrier_project_paths)
        or type(binding.carrier_file_count) is not int
        or binding.carrier_file_count != len(binding.carrier_project_paths)
    ):
        raise QcRuntimeShardProjectionError("binding scalar or container changed")
    for current in projection.module_bindings:
        if (
            type(current) is not QcRuntimeModuleShardBinding
            or type(current.role) is not str
            or type(current.canonical_project_path) is not str
            or type(current.canonical_byte_count) is not int
            or type(current.canonical_character_count) is not int
            or type(current.canonical_sha256) is not str
            or type(current.facade_project_path) is not str
            or type(current.carrier_project_paths) is not tuple
            or any(
                type(path) is not str for path in current.carrier_project_paths
            )
            or type(current.carrier_file_count) is not int
        ):
            raise QcRuntimeShardProjectionError("binding inventory topology changed")
    expected_spec = _SHARDED_BY_PATH.get(binding.canonical_project_path)
    if (
        not any(current == binding for current in projection.module_bindings)
        or expected_spec is None
        or binding != _expected_binding(expected_spec)
    ):
        raise QcRuntimeShardProjectionError("binding is not canonical")
    paths = tuple(item.project_path for item in projection.files)
    if (
        any(type(path) is not str for path in paths)
        or len(paths) != len(set(paths))
        or len(paths) != len({path.casefold() for path in paths})
    ):
        raise QcRuntimeShardProjectionError("projection paths or binding changed")
    by_path = {item.project_path: item for item in projection.files}
    try:
        carrier_files = tuple(by_path[path] for path in binding.carrier_project_paths)
    except KeyError as exc:
        raise QcRuntimeShardProjectionError("binding carrier is absent") from exc
    if any(item.source_kind != "carrier" for item in carrier_files):
        raise QcRuntimeShardProjectionError("binding path is not a carrier")
    encoded = b"".join(
        _carrier_payload(item.source_bytes, expected_path=item.project_path)
        for item in carrier_files
    )
    try:
        source = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise QcRuntimeShardProjectionError("carrier base64 is invalid") from exc
    if (
        len(source) != binding.canonical_byte_count
        or _character_count(source) != binding.canonical_character_count
        or hashlib.sha256(source).hexdigest() != binding.canonical_sha256
    ):
        raise QcRuntimeShardProjectionError("reconstructed canonical source changed")
    return source


def _expected_binding(spec: tuple[str, str, int, str, int]) -> QcRuntimeModuleShardBinding:
    role, project_path, byte_count, digest, carrier_count = spec
    carrier_paths = tuple(
        _carrier_path(project_path, index) for index in range(carrier_count)
    )
    return QcRuntimeModuleShardBinding(
        role=role,
        canonical_project_path=project_path,
        canonical_byte_count=byte_count,
        canonical_character_count=byte_count,
        canonical_sha256=digest,
        facade_project_path=project_path,
        carrier_project_paths=carrier_paths,
        carrier_file_count=carrier_count,
    )


def _require_generated_module_files(
    projection: SyntheticQcRuntimeShardProjection,
    binding: QcRuntimeModuleShardBinding,
) -> None:
    source = reconstruct_canonical_module_bytes(projection, binding)
    encoded = base64.b64encode(source)
    chunks = tuple(
        encoded[index : index + BASE64_CHUNK_CHARACTERS]
        for index in range(0, len(encoded), BASE64_CHUNK_CHARACTERS)
    )
    by_path = {item.project_path: item for item in projection.files}
    facade = by_path.get(binding.facade_project_path)
    expected_facade_source = _render_facade(
        canonical_project_path=binding.canonical_project_path,
        canonical_source=source,
        carrier_count=binding.carrier_file_count,
    )
    expected_facade = _projected_file(
        role=f"{binding.role}_runtime_facade",
        project_path=binding.canonical_project_path,
        source_kind="facade",
        source_bytes=expected_facade_source,
    )
    if facade != expected_facade:
        raise QcRuntimeShardProjectionError("runtime facade changed")
    for index, (path, chunk) in enumerate(
        zip(binding.carrier_project_paths, chunks, strict=True)
    ):
        item = by_path.get(path)
        expected_carrier_source = _render_carrier(
            role=binding.role,
            canonical_project_path=binding.canonical_project_path,
            ordinal=index,
            payload=chunk,
        )
        expected_carrier = _projected_file(
            role=f"{binding.role}_source_carrier_{index:02d}",
            project_path=path,
            source_kind="carrier",
            source_bytes=expected_carrier_source,
        )
        if item != expected_carrier:
            raise QcRuntimeShardProjectionError("runtime carrier changed")


def require_synthetic_qc_runtime_shard_projection(
    projection: SyntheticQcRuntimeShardProjection,
) -> SyntheticQcRuntimeShardProjection:
    """Validate census, hashes, reconstruction, and all false authority values."""

    if type(projection) is not SyntheticQcRuntimeShardProjection:
        raise QcRuntimeShardProjectionError("projection type changed")
    string_fields = (
        projection.projection_id,
        projection.projection_sha256,
        projection.projection_artifact_sha256,
        projection.parent_assembly_id,
        projection.parent_assembly_sha256,
        projection.parent_assembly_artifact_sha256,
    )
    integer_fields = (
        projection.project_file_count,
        projection.carrier_file_count,
        projection.total_projected_source_byte_count,
        projection.largest_projected_source_character_count,
    )
    if (
        any(type(item) is not str for item in string_fields)
        or any(type(item) is not int for item in integer_fields)
        or type(projection.files) is not tuple
        or type(projection.module_bindings) is not tuple
        or type(projection.external_bindings) is not tuple
        or type(projection.capabilities) is not tuple
        or type(projection._canonical_document) is not bytes
        or type(projection.canonical_runtime_source_reconstruction_authenticated)
        is not bool
        or type(projection.cloud_runtime_execution_authenticated) is not bool
        or type(projection.physical_adapter_present) is not bool
        or type(projection.cloud_compile_performed) is not bool
        or type(projection.backtest_performed) is not bool
    ):
        raise QcRuntimeShardProjectionError("projection scalar type changed")
    if (
        projection.project_file_count != EXPECTED_PROJECT_FILE_COUNT
        or projection.carrier_file_count != EXPECTED_CARRIER_FILE_COUNT
        or len(projection.files) != EXPECTED_PROJECT_FILE_COUNT
        or len(projection.module_bindings) != len(SHARDED_MODULES)
        or projection.parent_assembly_id != EXPECTED_PARENT_ASSEMBLY_ID
        or projection.parent_assembly_sha256 != EXPECTED_PARENT_ASSEMBLY_SHA256
        or projection.parent_assembly_artifact_sha256
        != EXPECTED_PARENT_ASSEMBLY_ARTIFACT_SHA256
        or projection.canonical_runtime_source_reconstruction_authenticated is not True
        or projection.cloud_runtime_execution_authenticated is not False
        or projection.physical_adapter_present is not False
        or projection.cloud_compile_performed is not False
        or projection.backtest_performed is not False
        or projection.external_bindings is not EXTERNAL_BINDINGS
        or projection.capabilities is not CAPABILITIES
    ):
        raise QcRuntimeShardProjectionError("projection truth or census changed")
    if (
        any(
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or item[1] is not None
            for item in projection.external_bindings
        )
        or any(
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or item[1] is not False
            for item in projection.capabilities
        )
    ):
        raise QcRuntimeShardProjectionError("authority registry changed")
    paths: list[str] = []
    for item in projection.files:
        if (
            type(item) is not QcRuntimeProjectedFile
            or type(item.role) is not str
            or type(item.project_path) is not str
            or type(item.source_kind) is not str
            or type(item.source_bytes) is not bytes
            or type(item.byte_count) is not int
            or type(item.character_count) is not int
            or type(item.sha256) is not str
            or _SAFE_PATH.fullmatch(item.project_path) is None
            or item.source_kind not in {"retained", "facade", "carrier"}
            or item.byte_count != len(item.source_bytes)
            or item.character_count != _character_count(item.source_bytes)
            or item.sha256 != hashlib.sha256(item.source_bytes).hexdigest()
            or _HEX_64.fullmatch(item.sha256) is None
            or item.character_count > MAX_PROJECTED_SOURCE_CHARACTERS
        ):
            raise QcRuntimeShardProjectionError("projected file changed")
        paths.append(item.project_path)
    expected_paths: list[str] = []
    for _role, parent_path, _byte_count, _digest in EXPECTED_PARENT_FILES:
        expected_paths.append(parent_path)
        sharded = _SHARDED_BY_PATH.get(parent_path)
        if sharded is not None:
            expected_paths.extend(
                _carrier_path(parent_path, index)
                for index in range(sharded[4])
            )
    if (
        tuple(paths) != tuple(expected_paths)
        or len(paths) != len(set(paths))
        or len(paths) != len({path.casefold() for path in paths})
        or sum(item.source_kind == "carrier" for item in projection.files)
        != EXPECTED_CARRIER_FILE_COUNT
        or sum(item.source_kind == "facade" for item in projection.files)
        != len(SHARDED_MODULES)
        or sum(item.source_kind == "retained" for item in projection.files) != 7
        or projection.total_projected_source_byte_count
        != sum(item.byte_count for item in projection.files)
        or projection.largest_projected_source_character_count
        != max(item.character_count for item in projection.files)
    ):
        raise QcRuntimeShardProjectionError("projected inventory changed")

    expected_bindings = tuple(_expected_binding(item) for item in SHARDED_MODULES)
    if any(type(item) is not QcRuntimeModuleShardBinding for item in projection.module_bindings):
        raise QcRuntimeShardProjectionError("module binding type changed")
    for item in projection.module_bindings:
        if (
            type(item.role) is not str
            or type(item.canonical_project_path) is not str
            or type(item.canonical_byte_count) is not int
            or type(item.canonical_character_count) is not int
            or type(item.canonical_sha256) is not str
            or type(item.facade_project_path) is not str
            or type(item.carrier_project_paths) is not tuple
            or any(type(path) is not str for path in item.carrier_project_paths)
            or type(item.carrier_file_count) is not int
        ):
            raise QcRuntimeShardProjectionError("module binding scalar changed")
    if projection.module_bindings != expected_bindings:
        raise QcRuntimeShardProjectionError("module binding inventory changed")
    by_path = {item.project_path: item for item in projection.files}
    for role, project_path, byte_count, digest in EXPECTED_PARENT_FILES:
        if project_path in _SHARDED_BY_PATH:
            continue
        item = by_path.get(project_path)
        if (
            item is None
            or item.role != role
            or item.source_kind != "retained"
            or item.byte_count != byte_count
            or item.character_count != byte_count
            or item.sha256 != digest
        ):
            raise QcRuntimeShardProjectionError("retained B5B source changed")
    for binding in projection.module_bindings:
        _require_generated_module_files(projection, binding)

    seed = _projection_document(
        projection_id=None,
        projection_sha256=None,
        files=projection.files,
        bindings=projection.module_bindings,
    )
    expected_sha256 = hashlib.sha256(_canonical_bytes(seed)).hexdigest()
    expected_id = f"arv2-qc-runtime-shard-projection-{expected_sha256[:16]}"
    expected_document = _projection_document(
        projection_id=expected_id,
        projection_sha256=expected_sha256,
        files=projection.files,
        bindings=projection.module_bindings,
    )
    canonical = _canonical_bytes(expected_document)
    if (
        projection.projection_id != expected_id
        or projection.projection_sha256 != expected_sha256
        or projection._canonical_document != canonical
        or hashlib.sha256(canonical).hexdigest()
        != projection.projection_artifact_sha256
        or _HEX_64.fullmatch(projection.projection_sha256) is None
        or _HEX_64.fullmatch(projection.projection_artifact_sha256) is None
    ):
        raise QcRuntimeShardProjectionError("projection identity changed")
    return projection


# Closure-rooted bootstrap.  Public wrappers capture these exact implementation
# objects and this checker; changing a public/global/helper binding refuses
# before the implementation receives caller data.
_PINNED_RENDER_IMPL = render_qc_runtime_shard_projection_schema_bytes
_PINNED_BUILD_IMPL = build_synthetic_qc_runtime_shard_projection
_PINNED_RECONSTRUCT_IMPL = reconstruct_canonical_module_bytes
_PINNED_REQUIRE_IMPL = require_synthetic_qc_runtime_shard_projection
_MODULE_GLOBALS = globals()

_DEPENDENCY_MODULE_BINDINGS = (
    ("ast", ast),
    ("base64", base64),
    ("dataclasses", dataclasses),
    ("hashlib", hashlib),
    ("json", json),
    ("re", re),
    ("textwrap", textwrap),
    ("_b5b_module", _b5b_module),
)
_DEPENDENCY_CALLABLE_BINDINGS = (
    (ast, "parse", ast.parse),
    (base64, "b64encode", base64.b64encode),
    (base64, "b64decode", base64.b64decode),
    (dataclasses, "dataclass", dataclasses.dataclass),
    (dataclasses, "field", dataclasses.field),
    (dataclasses, "fields", dataclasses.fields),
    (hashlib, "sha256", hashlib.sha256),
    (json, "dumps", json.dumps),
    (re, "compile", re.compile),
    (re, "fullmatch", re.fullmatch),
    (textwrap, "wrap", textwrap.wrap),
    (
        _b5b_module,
        "require_synthetic_qc_lean_source_assembly",
        _PINNED_REQUIRE_PARENT,
    ),
)
_IMPORTED_BINDINGS = (
    ("B5B_CAPABILITIES", B5B_CAPABILITIES),
    ("B5B_EXTERNAL_BINDINGS", B5B_EXTERNAL_BINDINGS),
    ("B5B_SCHEMA_ARTIFACT_SHA256", B5B_SCHEMA_ARTIFACT_SHA256),
    ("B5B_SCHEMA_ID", B5B_SCHEMA_ID),
    ("B5B_SCHEMA_SHA256", B5B_SCHEMA_SHA256),
    ("SyntheticLeanProjectAssembly", _PINNED_PARENT_CLASS),
    ("require_synthetic_qc_lean_source_assembly", _PINNED_REQUIRE_PARENT),
    ("_PINNED_REQUIRE_PARENT", _PINNED_REQUIRE_PARENT),
    ("_PINNED_PARENT_CLASS", _PINNED_PARENT_CLASS),
)

_SCALAR_EXPECTATIONS = (
    ("SCHEMA", str, "arv2-qc-runtime-shard-projection-schema-v1"),
    ("STATUS", str, "offline_exact_source_sharding_only_no_physical_qc_action"),
    ("AUTHORITY", str, AUTHORITY),
    ("HASH_DOMAIN", str, "arv2-qc-runtime-shard-projection-v1"),
    ("SCHEMA_ID", str, "arv2-qc-runtime-shard-projection-schema-2909a08c686f8015"),
    (
        "SCHEMA_SHA256",
        str,
        "2909a08c686f8015d89f82eab0d3ad6e2b9f72be0498213ac949f47841c446f4",
    ),
    (
        "SCHEMA_ARTIFACT_SHA256",
        str,
        "3cbafe2272af9dc07d5931ef25b20d23133093c9ad7900d15891108a426143f1",
    ),
    ("QC_OBSERVED_SOURCE_CHARACTER_LIMIT", int, 64_000),
    ("MAX_PROJECTED_SOURCE_CHARACTERS", int, 60_000),
    ("BASE64_CHUNK_CHARACTERS", int, 50_000),
    ("BASE64_LITERAL_WIDTH", int, 100),
    ("EXPECTED_PROJECT_FILE_COUNT", int, 23),
    ("EXPECTED_CARRIER_FILE_COUNT", int, 12),
    ("EXPECTED_PARENT_ASSEMBLY_ID", str, EXPECTED_PARENT_ASSEMBLY_ID),
    ("EXPECTED_PARENT_ASSEMBLY_SHA256", str, EXPECTED_PARENT_ASSEMBLY_SHA256),
    (
        "EXPECTED_PARENT_ASSEMBLY_ARTIFACT_SHA256",
        str,
        EXPECTED_PARENT_ASSEMBLY_ARTIFACT_SHA256,
    ),
    ("EXPECTED_PARENT_SCHEMA_ID", str, EXPECTED_PARENT_SCHEMA_ID),
    ("EXPECTED_PARENT_SCHEMA_SHA256", str, EXPECTED_PARENT_SCHEMA_SHA256),
    (
        "EXPECTED_PARENT_SCHEMA_ARTIFACT_SHA256",
        str,
        EXPECTED_PARENT_SCHEMA_ARTIFACT_SHA256,
    ),
    ("B5B_SCHEMA_ID", str, EXPECTED_PARENT_SCHEMA_ID),
    ("B5B_SCHEMA_SHA256", str, EXPECTED_PARENT_SCHEMA_SHA256),
    (
        "B5B_SCHEMA_ARTIFACT_SHA256",
        str,
        EXPECTED_PARENT_SCHEMA_ARTIFACT_SHA256,
    ),
)
_CONTAINER_EXPECTATIONS = (
    ("EXPECTED_PARENT_IDENTITY", EXPECTED_PARENT_IDENTITY),
    ("EXPECTED_PARENT_FILES", EXPECTED_PARENT_FILES),
    ("SHARDED_MODULES", SHARDED_MODULES),
    ("CAPABILITIES", CAPABILITIES),
    ("EXTERNAL_BINDINGS", EXTERNAL_BINDINGS),
    ("__all__", __all__),
)
_SHARDED_MAP_ITEMS = tuple(_SHARDED_BY_PATH.items())

_CLASS_BINDINGS = (
    ("QcRuntimeShardProjectionError", QcRuntimeShardProjectionError),
    ("QcRuntimeProjectedFile", QcRuntimeProjectedFile),
    ("QcRuntimeModuleShardBinding", QcRuntimeModuleShardBinding),
    ("SyntheticQcRuntimeShardProjection", SyntheticQcRuntimeShardProjection),
)
for _class_binding_name, _class_binding_value in _CLASS_BINDINGS:
    getattr(_class_binding_value, "__annotations__", {})
del _class_binding_name
del _class_binding_value
_CLASS_TOPOLOGIES = tuple(
    (
        accepted_class,
        accepted_class.__mro__,
        tuple(vars(accepted_class).items()),
        tuple(getattr(accepted_class, "__annotations__", {}).items()),
        tuple(
            (
                field,
                field.name,
                field.type,
                field.default,
                field.default_factory,
                field.init,
                field.repr,
                field.hash,
                field.compare,
            )
            for field in (
                dataclasses.fields(accepted_class)
                if dataclasses.is_dataclass(accepted_class)
                else ()
            )
        ),
    )
    for _, accepted_class in _CLASS_BINDINGS
)
_CLASS_CALLABLE_STATES = tuple(
    (
        accepted_class,
        name,
        value,
        value.__code__,
        value.__defaults__,
        value.__kwdefaults__,
        value.__closure__,
    )
    for _, accepted_class in _CLASS_BINDINGS
    for name, member in vars(accepted_class).items()
    for value in (
        member.fget if type(member) is property else member,
    )
    if type(value) is type(lambda: None)
)

_CORE_FUNCTION_NAMES = (
    "_canonical_bytes",
    "_schema_seed_document",
    "_schema_document",
    "_character_count",
    "_carrier_stem",
    "_carrier_path",
    "_carrier_module_name",
    "_render_carrier",
    "_render_facade",
    "_projected_file",
    "_file_document",
    "_binding_document",
    "_projection_document",
    "_extract_parent_files",
    "_carrier_payload",
    "_expected_binding",
    "_require_generated_module_files",
    "_PINNED_RENDER_IMPL",
    "_PINNED_BUILD_IMPL",
    "_PINNED_RECONSTRUCT_IMPL",
    "_PINNED_REQUIRE_IMPL",
)
_CORE_FUNCTION_STATES = tuple(
    (
        name,
        _MODULE_GLOBALS[name],
        _MODULE_GLOBALS[name].__code__,
        _MODULE_GLOBALS[name].__defaults__,
        _MODULE_GLOBALS[name].__kwdefaults__,
        _MODULE_GLOBALS[name].__closure__,
        tuple(
            (cell, type(cell.cell_contents), cell.cell_contents)
            for cell in (_MODULE_GLOBALS[name].__closure__ or ())
        ),
    )
    for name in _CORE_FUNCTION_NAMES
)

_BUILTIN_GLOBALS = __builtins__
if type(_BUILTIN_GLOBALS) is not dict:
    raise RuntimeError("ARV2-4F-B5D expected exact builtins dictionary")
_BUILTIN_ENTRIES = tuple(_BUILTIN_GLOBALS.items())
_BUILTIN_NAMES = (
    "Exception",
    "KeyError",
    "RuntimeError",
    "SyntaxError",
    "TypeError",
    "UnicodeDecodeError",
    "ValueError",
    "any",
    "bool",
    "bytes",
    "dict",
    "enumerate",
    "getattr",
    "globals",
    "int",
    "isinstance",
    "len",
    "list",
    "max",
    "property",
    "range",
    "set",
    "str",
    "sum",
    "tuple",
    "type",
    "vars",
    "zip",
)
_BUILTIN_BINDINGS = tuple(
    (name, _BUILTIN_GLOBALS[name]) for name in _BUILTIN_NAMES
)
_BOOTSTRAP_ALIAS_BINDINGS = (
    ("_MODULE_GLOBALS", _MODULE_GLOBALS),
    ("_DEPENDENCY_MODULE_BINDINGS", _DEPENDENCY_MODULE_BINDINGS),
    ("_DEPENDENCY_CALLABLE_BINDINGS", _DEPENDENCY_CALLABLE_BINDINGS),
    ("_IMPORTED_BINDINGS", _IMPORTED_BINDINGS),
    ("_SCALAR_EXPECTATIONS", _SCALAR_EXPECTATIONS),
    ("_CONTAINER_EXPECTATIONS", _CONTAINER_EXPECTATIONS),
    ("_SHARDED_MAP_ITEMS", _SHARDED_MAP_ITEMS),
    ("_CLASS_BINDINGS", _CLASS_BINDINGS),
    ("_CLASS_TOPOLOGIES", _CLASS_TOPOLOGIES),
    ("_CLASS_CALLABLE_STATES", _CLASS_CALLABLE_STATES),
    ("_CORE_FUNCTION_NAMES", _CORE_FUNCTION_NAMES),
    ("_CORE_FUNCTION_STATES", _CORE_FUNCTION_STATES),
    ("_BUILTIN_GLOBALS", _BUILTIN_GLOBALS),
    ("_BUILTIN_ENTRIES", _BUILTIN_ENTRIES),
    ("_BUILTIN_NAMES", _BUILTIN_NAMES),
    ("_BUILTIN_BINDINGS", _BUILTIN_BINDINGS),
    ("_HEX_64", _HEX_64),
    ("_SAFE_PATH", _SAFE_PATH),
)


def _make_static_checker(
    *,
    module_globals,
    dependency_modules,
    dependency_callables,
    imported_bindings,
    scalar_expectations,
    container_expectations,
    map_object,
    map_items,
    class_bindings,
    class_topologies,
    class_callable_states,
    core_function_states,
    builtin_globals,
    builtin_entries,
    builtin_bindings,
    alias_bindings,
    error_class,
):
    pinned_type = type
    pinned_tuple = tuple
    pinned_len = len
    pinned_any = any
    pinned_zip = zip
    pinned_vars = vars
    pinned_getattr = getattr
    pinned_globals = globals
    pinned_dict = dict
    pinned_str = str
    pinned_int = int
    pinned_bool = bool
    pinned_bytes = bytes
    pinned_property = property
    pinned_function_type = type(lambda: None)
    public_bindings = None
    public_states = None

    def bind_publics(values):
        nonlocal public_bindings, public_states
        if public_bindings is not None or pinned_type(values) is not pinned_tuple:
            raise error_class("B5D public binding installation changed")
        public_bindings = values
        public_states = pinned_tuple(
            (
                implementation,
                implementation.__code__,
                implementation.__defaults__,
                implementation.__kwdefaults__,
                implementation.__closure__,
                pinned_tuple(
                    (cell, pinned_type(cell.cell_contents), cell.cell_contents)
                    for cell in (implementation.__closure__ or ())
                ),
                implementation.__name__,
                implementation.__qualname__,
                implementation.__doc__,
            )
            for _name, implementation in values
        )

    def check():
        if (
            public_bindings is None
            or public_states is None
            or pinned_globals() is not module_globals
            or module_globals.get("_BOOTSTRAP_ALIAS_BINDINGS")
            is not alias_bindings
            or module_globals.get("_PUBLIC_BINDINGS") is not public_bindings
        ):
            raise error_class("B5D module topology changed")
        for name, expected in alias_bindings:
            if module_globals.get(name) is not expected:
                raise error_class("B5D bootstrap alias changed")
        for name, expected in dependency_modules:
            if module_globals.get(name) is not expected:
                raise error_class("B5D dependency module binding changed")
        for module, name, expected in dependency_callables:
            if pinned_getattr(module, name, None) is not expected:
                raise error_class("B5D dependency callable changed")
        for name, expected in imported_bindings:
            if module_globals.get(name) is not expected:
                raise error_class("B5D imported binding changed")
        for name, expected_type, expected_value in scalar_expectations:
            value = module_globals.get(name)
            if pinned_type(value) is not expected_type or value != expected_value:
                raise error_class("B5D scalar contract changed")
        for name, expected in container_expectations:
            value = module_globals.get(name)
            if value is not expected or pinned_type(value) is not pinned_tuple:
                raise error_class("B5D registry identity changed")
        if (
            module_globals.get("_SHARDED_BY_PATH") is not map_object
            or pinned_type(map_object) is not pinned_dict
            or pinned_any(
                pinned_type(key) is not pinned_str
                or pinned_type(value) is not pinned_tuple
                or pinned_len(value) != 5
                or pinned_type(value[0]) is not pinned_str
                or pinned_type(value[1]) is not pinned_str
                or pinned_type(value[2]) is not pinned_int
                or pinned_type(value[3]) is not pinned_str
                or pinned_type(value[4]) is not pinned_int
                for key, value in map_object.items()
            )
            or pinned_tuple(map_object.items()) != map_items
        ):
            raise error_class("B5D sharded-module map changed")
        for name, accepted_class in class_bindings:
            if module_globals.get(name) is not accepted_class:
                raise error_class("B5D class binding changed")
        for (
            accepted_class,
            expected_mro,
            expected_members,
            expected_annotations,
            expected_fields,
        ) in class_topologies:
            members = pinned_vars(accepted_class)
            live_annotations = pinned_tuple(
                pinned_getattr(accepted_class, "__annotations__", {}).items()
            )
            if (
                accepted_class.__mro__ is not expected_mro
                or pinned_len(members) != pinned_len(expected_members)
                or pinned_any(
                    members.get(name) is not expected
                    for name, expected in expected_members
                )
                or pinned_len(live_annotations) != pinned_len(expected_annotations)
                or pinned_any(
                    live_key is not expected_key
                    or live_value is not expected_value
                    for (live_key, live_value), (expected_key, expected_value)
                    in pinned_zip(
                        live_annotations,
                        expected_annotations,
                        strict=True,
                    )
                )
            ):
                raise error_class("B5D class topology changed")
            live_fields = dataclasses.fields(accepted_class) if expected_fields else ()
            if pinned_len(live_fields) != pinned_len(expected_fields):
                raise error_class("B5D dataclass field inventory changed")
            for live, expected in pinned_zip(live_fields, expected_fields, strict=True):
                if (
                    live is not expected[0]
                    or pinned_type(live.name) is not pinned_str
                    or live.name is not expected[1]
                    or live.type is not expected[2]
                    or live.default is not expected[3]
                    or live.default_factory is not expected[4]
                    or pinned_type(live.init) is not pinned_bool
                    or live.init is not expected[5]
                    or pinned_type(live.repr) is not pinned_bool
                    or live.repr is not expected[6]
                    or live.hash is not expected[7]
                    or pinned_type(live.compare) is not pinned_bool
                    or live.compare is not expected[8]
                ):
                    raise error_class("B5D dataclass field changed")
        for (
            accepted_class,
            name,
            expected_function,
            expected_code,
            expected_defaults,
            expected_kwdefaults,
            expected_closure,
        ) in class_callable_states:
            member = pinned_vars(accepted_class).get(name)
            actual = member.fget if pinned_type(member) is pinned_property else member
            if (
                actual is not expected_function
                or actual.__code__ is not expected_code
                or actual.__defaults__ is not expected_defaults
                or actual.__kwdefaults__ is not expected_kwdefaults
                or actual.__closure__ is not expected_closure
            ):
                raise error_class("B5D class callable changed")
        for (
            name,
            expected_function,
            expected_code,
            expected_defaults,
            expected_kwdefaults,
            expected_closure,
            expected_closure_state,
        ) in core_function_states:
            actual = module_globals.get(name)
            if (
                actual is not expected_function
                or actual.__code__ is not expected_code
                or actual.__defaults__ is not expected_defaults
                or actual.__kwdefaults__ is not expected_kwdefaults
                or actual.__closure__ is not expected_closure
                or pinned_len(actual.__closure__ or ())
                != pinned_len(expected_closure_state)
                or pinned_any(
                    live_cell is not expected_cell
                    or pinned_type(live_cell.cell_contents) is not expected_type
                    or live_cell.cell_contents is not expected_contents
                    for live_cell, (expected_cell, expected_type, expected_contents)
                    in pinned_zip(
                        actual.__closure__ or (),
                        expected_closure_state,
                        strict=True,
                    )
                )
            ):
                raise error_class("B5D local callable changed")
        if (
            module_globals.get("__builtins__") is not builtin_globals
            or pinned_len(builtin_globals) != pinned_len(builtin_entries)
        ):
            raise error_class("B5D builtins topology changed")
        for name, expected in builtin_bindings:
            if builtin_globals.get(name) is not expected or name in module_globals:
                raise error_class("B5D builtin resolution changed")
        for name, expected in public_bindings:
            if module_globals.get(name) is not expected:
                raise error_class("B5D public binding changed")
        for (
            implementation,
            expected_code,
            expected_defaults,
            expected_kwdefaults,
            expected_closure,
            expected_cells,
            expected_name,
            expected_qualname,
            expected_doc,
        ) in public_states:
            if (
                implementation.__code__ is not expected_code
                or implementation.__defaults__ is not expected_defaults
                or implementation.__kwdefaults__ is not expected_kwdefaults
                or implementation.__closure__ is not expected_closure
                or implementation.__name__ is not expected_name
                or implementation.__qualname__ is not expected_qualname
                or implementation.__doc__ is not expected_doc
                or pinned_len(implementation.__closure__ or ())
                != pinned_len(expected_cells)
                or pinned_any(
                    live is not expected_cell
                    or pinned_type(live.cell_contents) is not expected_type
                    or live.cell_contents is not expected_value
                    for live, (expected_cell, expected_type, expected_value)
                    in pinned_zip(
                        implementation.__closure__ or (),
                        expected_cells,
                        strict=True,
                    )
                )
            ):
                raise error_class("B5D public wrapper changed")
        if (
            hashlib.sha256(_canonical_bytes(_schema_seed_document())).hexdigest()
            != SCHEMA_SHA256
            or hashlib.sha256(_canonical_bytes(_schema_document())).hexdigest()
            != SCHEMA_ARTIFACT_SHA256
        ):
            raise error_class("B5D schema identity changed")

    return check, bind_publics


_STATIC_CHECK, _bind_publics_once = _make_static_checker(
    module_globals=_MODULE_GLOBALS,
    dependency_modules=_DEPENDENCY_MODULE_BINDINGS,
    dependency_callables=_DEPENDENCY_CALLABLE_BINDINGS,
    imported_bindings=_IMPORTED_BINDINGS,
    scalar_expectations=_SCALAR_EXPECTATIONS,
    container_expectations=_CONTAINER_EXPECTATIONS,
    map_object=_SHARDED_BY_PATH,
    map_items=_SHARDED_MAP_ITEMS,
    class_bindings=_CLASS_BINDINGS,
    class_topologies=_CLASS_TOPOLOGIES,
    class_callable_states=_CLASS_CALLABLE_STATES,
    core_function_states=_CORE_FUNCTION_STATES,
    builtin_globals=_BUILTIN_GLOBALS,
    builtin_entries=_BUILTIN_ENTRIES,
    builtin_bindings=_BUILTIN_BINDINGS,
    alias_bindings=_BOOTSTRAP_ALIAS_BINDINGS,
    error_class=QcRuntimeShardProjectionError,
)


def _sealed_render(implementation, static_check, module_globals, error_class):
    implementation_code = implementation.__code__
    static_code = static_check.__code__

    def render_qc_runtime_shard_projection_schema_bytes() -> bytes:
        if (
            implementation.__code__ is not implementation_code
            or static_check.__code__ is not static_code
            or module_globals.get("_STATIC_CHECK") is not static_check
            or module_globals.get(
                "render_qc_runtime_shard_projection_schema_bytes"
            )
            is not render_qc_runtime_shard_projection_schema_bytes
        ):
            raise error_class("B5D render wrapper changed")
        static_check()
        result = implementation()
        static_check()
        return result

    render_qc_runtime_shard_projection_schema_bytes.__qualname__ = (
        "render_qc_runtime_shard_projection_schema_bytes"
    )
    render_qc_runtime_shard_projection_schema_bytes.__doc__ = implementation.__doc__
    return render_qc_runtime_shard_projection_schema_bytes


def _sealed_build(
    implementation, validator, static_check, module_globals, error_class
):
    implementation_code = implementation.__code__
    validator_code = validator.__code__
    static_code = static_check.__code__

    def build_synthetic_qc_runtime_shard_projection(
        *, source_assembly: SyntheticLeanProjectAssembly
    ) -> SyntheticQcRuntimeShardProjection:
        if (
            implementation.__code__ is not implementation_code
            or validator.__code__ is not validator_code
            or static_check.__code__ is not static_code
            or module_globals.get("_STATIC_CHECK") is not static_check
            or module_globals.get("build_synthetic_qc_runtime_shard_projection")
            is not build_synthetic_qc_runtime_shard_projection
        ):
            raise error_class("B5D build wrapper changed")
        static_check()
        result = implementation(source_assembly=source_assembly)
        result = validator(result)
        static_check()
        return result

    build_synthetic_qc_runtime_shard_projection.__qualname__ = (
        "build_synthetic_qc_runtime_shard_projection"
    )
    build_synthetic_qc_runtime_shard_projection.__doc__ = implementation.__doc__
    return build_synthetic_qc_runtime_shard_projection


def _sealed_reconstruct(implementation, static_check, module_globals, error_class):
    implementation_code = implementation.__code__
    static_code = static_check.__code__

    def reconstruct_canonical_module_bytes(
        projection: SyntheticQcRuntimeShardProjection,
        binding: QcRuntimeModuleShardBinding,
    ) -> bytes:
        if (
            implementation.__code__ is not implementation_code
            or static_check.__code__ is not static_code
            or module_globals.get("_STATIC_CHECK") is not static_check
            or module_globals.get("reconstruct_canonical_module_bytes")
            is not reconstruct_canonical_module_bytes
        ):
            raise error_class("B5D reconstruct wrapper changed")
        static_check()
        result = implementation(projection, binding)
        static_check()
        return result

    reconstruct_canonical_module_bytes.__qualname__ = (
        "reconstruct_canonical_module_bytes"
    )
    reconstruct_canonical_module_bytes.__doc__ = implementation.__doc__
    return reconstruct_canonical_module_bytes


def _sealed_require(implementation, static_check, module_globals, error_class):
    implementation_code = implementation.__code__
    static_code = static_check.__code__

    def require_synthetic_qc_runtime_shard_projection(
        projection: SyntheticQcRuntimeShardProjection,
    ) -> SyntheticQcRuntimeShardProjection:
        if (
            implementation.__code__ is not implementation_code
            or static_check.__code__ is not static_code
            or module_globals.get("_STATIC_CHECK") is not static_check
            or module_globals.get("require_synthetic_qc_runtime_shard_projection")
            is not require_synthetic_qc_runtime_shard_projection
        ):
            raise error_class("B5D require wrapper changed")
        static_check()
        result = implementation(projection)
        static_check()
        return result

    require_synthetic_qc_runtime_shard_projection.__qualname__ = (
        "require_synthetic_qc_runtime_shard_projection"
    )
    require_synthetic_qc_runtime_shard_projection.__doc__ = implementation.__doc__
    return require_synthetic_qc_runtime_shard_projection


render_qc_runtime_shard_projection_schema_bytes = _sealed_render(
    _PINNED_RENDER_IMPL,
    _STATIC_CHECK,
    _MODULE_GLOBALS,
    QcRuntimeShardProjectionError,
)
build_synthetic_qc_runtime_shard_projection = _sealed_build(
    _PINNED_BUILD_IMPL,
    _PINNED_REQUIRE_IMPL,
    _STATIC_CHECK,
    _MODULE_GLOBALS,
    QcRuntimeShardProjectionError,
)
reconstruct_canonical_module_bytes = _sealed_reconstruct(
    _PINNED_RECONSTRUCT_IMPL,
    _STATIC_CHECK,
    _MODULE_GLOBALS,
    QcRuntimeShardProjectionError,
)
require_synthetic_qc_runtime_shard_projection = _sealed_require(
    _PINNED_REQUIRE_IMPL,
    _STATIC_CHECK,
    _MODULE_GLOBALS,
    QcRuntimeShardProjectionError,
)

_PUBLIC_BINDINGS = (
    (
        "render_qc_runtime_shard_projection_schema_bytes",
        render_qc_runtime_shard_projection_schema_bytes,
    ),
    (
        "build_synthetic_qc_runtime_shard_projection",
        build_synthetic_qc_runtime_shard_projection,
    ),
    ("reconstruct_canonical_module_bytes", reconstruct_canonical_module_bytes),
    (
        "require_synthetic_qc_runtime_shard_projection",
        require_synthetic_qc_runtime_shard_projection,
    ),
)
_bind_publics_once(_PUBLIC_BINDINGS)
del _bind_publics_once
del _make_static_checker
del _sealed_render
del _sealed_build
del _sealed_reconstruct
del _sealed_require
