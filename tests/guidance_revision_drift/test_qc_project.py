"""Offline QC project preparation and SDK-shim loader checks, not LEAN evidence."""
from __future__ import annotations

import ast
from copy import deepcopy
from importlib.util import MAGIC_NUMBER, cache_from_source
from io import BytesIO
import json
import marshal
import os
from pathlib import Path
import subprocess
import struct
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from data.hashing import hash_bytes, hash_payload
from research.guidance_revision_drift import bundle, native_bundle, qc_project
from research.guidance_revision_drift.contracts import CANDIDATE_SHA256
from research.guidance_revision_drift.lean_bridge import fixture_stream


ROOT = Path(__file__).resolve().parents[2]
SHIM_SOURCE = ROOT / "tests/guidance_revision_drift/test_lean_source.py"
_UNSET = object()


def project_anchor(files):
    """Independent canonical file-map anchor; not a verifier's self-assertion."""
    return hash_payload({name: {"bytes": len(raw), "sha256": hash_bytes(raw)}
                         for name, raw in sorted(files.items())})


def asset_literals(raw):
    """Independently inspect transparent data text without executing its module."""
    tree = ast.parse(raw.decode("utf-8"))
    if len(tree.body) != 2:
        raise AssertionError("assets must be exactly two literal assignments")
    assets = {}
    for node in tree.body:
        if (type(node) is not ast.Assign or len(node.targets) != 1
                or type(node.targets[0]) is not ast.Name
                or type(node.value) is not ast.Constant
                or type(node.value.value) is not str):
            raise AssertionError("assets must be direct literal text, not executable or encoded data")
        name = node.targets[0].id
        if name in assets:
            raise AssertionError("asset names must be unique")
        assets[name] = node.value.value.encode("utf-8")
    if set(assets) != {"_GDR_CANDIDATE_JSON", "_GDR_FIXTURE_JSONL"}:
        raise AssertionError("assets must contain only the frozen draft and invented fixture")
    return assets


class QCProjectTests(unittest.TestCase):
    def setUp(self):
        self.files = qc_project.build_qc_project()
        self.anchor = project_anchor(self.files)

    def assert_refused(self, files, *, anchor=_UNSET):
        if anchor is _UNSET:
            anchor = project_anchor(files)
        with self.assertRaises(qc_project.QCProjectError):
            qc_project.verify_qc_project(files, expected_sha256=anchor)

    def test_current_source_roundtrip_is_deterministic_and_bounded_python_only(self):
        self.assertEqual(qc_project.build_qc_project(), self.files)
        self.assertIn("main.py", self.files)
        self.assertEqual(len(self.files), 21)
        self.assertLessEqual(len(self.files) + qc_project.RESERVED_PROJECT_FILES,
                             qc_project.MAX_PROJECT_FILES)
        self.assertTrue(all(name.endswith(".py") and "\\" not in name for name in self.files))
        self.assertTrue(all(type(raw) is bytes and len(raw) < qc_project.MAX_PROJECT_FILE_BYTES
                            and (raw or name.endswith("/__init__.py"))
                            for name, raw in self.files.items()))
        receipt = qc_project.verify_qc_project(self.files, expected_sha256=self.anchor)
        self.assertEqual({key: value for key, value in receipt.items() if key != "status"},
                         qc_project.qc_project_manifest())
        self.assertEqual(receipt["status"], "verified_offline_content_only")
        manifest = receipt
        self.assertEqual(manifest["project_sha256"], self.anchor)
        self.assertEqual(manifest["project_files"], {
            name: {"bytes": len(raw), "sha256": hash_bytes(raw)}
            for name, raw in self.files.items()})
        self.assertEqual(manifest["entrypoint"], "main.py")
        self.assertEqual(manifest["candidate_sha256"], CANDIDATE_SHA256)
        self.assertEqual(manifest["fixture_sha256"], hash_bytes(fixture_stream()))
        self.assertEqual(manifest["fixture_bytes"], len(fixture_stream()))
        self.assertEqual(manifest["fixture_frames"], 372)
        self.assertEqual(manifest["schema"], "gdr.synthetic.python-project.v3")
        self.assertIs(manifest["fresh_review_required"], True)
        self.assertIs(manifest["native_runtime_verified"], False)
        self.assertIs(manifest["market_evidence"], False)

    def test_readable_native_files_and_literal_assets_preserve_exact_bytes(self):
        native_paths = native_bundle.SOURCE_PATHS - {bundle._CANDIDATE_PATH}
        self.assertEqual(set(self.files), native_paths | {"main.py", "gdr_assets.py"})
        for name in sorted(native_paths):
            self.assertEqual(self.files[name], (ROOT / name).read_bytes(), name)
        assets = asset_literals(self.files["gdr_assets.py"])
        self.assertEqual(assets["_GDR_CANDIDATE_JSON"], (ROOT / bundle._CANDIDATE_PATH).read_bytes())
        self.assertEqual(assets["_GDR_FIXTURE_JSONL"], fixture_stream())
        # The native ZIP is still an offline audit reference. It is neither
        # shipped as code nor decoded/materialized by the generated root.
        raw = native_bundle.build_native_bundle()
        manifest = qc_project.qc_project_manifest()
        self.assertEqual(hash_bytes(raw), manifest["bundle_sha256"])
        self.assertEqual(len(raw), manifest["bundle_bytes"])
        with ZipFile(BytesIO(raw)) as archive:
            self.assertEqual(archive.read(bundle.SIDECAR_PATH), fixture_stream())
            for name in sorted(native_bundle.SOURCE_PATHS):
                self.assertEqual(archive.read(name), (ROOT / name).read_bytes(), name)
            inner = json.loads(archive.read(bundle.MANIFEST_PATH))
        self.assertEqual(manifest["runtime_source_sha256"], inner["source_manifest_sha256"])
        self.assertNotEqual(manifest["source_manifest_sha256"], inner["source_manifest_sha256"])
        self.assertIs(inner["native_runtime_verified"], False)
        self.assertIs(inner["market_evidence"], False)
        candidate = json.loads((ROOT / "research/guidance_revision_drift/specs/gdr0a.draft.json").read_bytes())
        self.assertTrue(all(value is None for value in candidate["unresolved"].values()))
        self.assertEqual(candidate["authority"]["research_looks"], 0)

    def test_wrong_or_aliased_anchor_refuses_before_reconstruction(self):
        with patch.object(qc_project, "_prepare_project", side_effect=AssertionError("must not reconstruct")):
            for anchor in ("0" * 64, "A" * 64, "", None, 123, True):
                with self.subTest(anchor=anchor):
                    self.assert_refused(self.files, anchor=anchor)

    def test_invalid_map_keys_and_value_types_refuse(self):
        class DictAlias(dict):
            pass

        for files in (None, [], (), {}, list(self.files.items()), DictAlias(self.files),
                      self.files | {"main.py": bytearray(self.files["main.py"])},
                      self.files | {"main.py": self.files["main.py"].decode()},
                      self.files | {"main.py": None}):
            with self.subTest(kind=type(files)):
                self.assert_refused(files, anchor=self.anchor)
        for name in (False, 1, "../outside.py", "/outside.py", "C:/outside.py",
                     "x\\outside.py", "x//outside.py", "x/./outside.py", "payload.jsonl", ""):
            with self.subTest(name=name):
                self.assert_refused(self.files | {name: b"pass\n"}, anchor=self.anchor)

    def test_missing_extra_modified_and_reanchored_content_refuse(self):
        source = "research/guidance_revision_drift/lean/main.py"
        for name in ("main.py", source, "gdr_assets.py"):
            with self.subTest(missing=name):
                self.assert_refused({key: raw for key, raw in self.files.items() if key != name})
            with self.subTest(altered=name):
                self.assert_refused(self.files | {name: self.files[name] + b"\n# changed\n"})
        self.assert_refused(self.files | {"extra.py": b"pass\n"})

    def test_byte_and_file_quotas_refuse_even_with_consistent_anchor(self):
        for size in (qc_project.MAX_PROJECT_FILE_BYTES, qc_project.MAX_PROJECT_FILE_BYTES + 1):
            with self.subTest(size=size):
                self.assert_refused(self.files | {"main.py": b"x" * size})
        many = dict(self.files)
        for index in range(qc_project.MAX_PROJECT_FILES + 1):
            many[f"extra_{index:03d}.py"] = b"pass\n"
        self.assert_refused(many)

    def test_reordered_input_is_not_an_alternate_source_identity(self):
        reordered = dict(reversed(list(self.files.items())))
        self.assertEqual(project_anchor(reordered), self.anchor)
        receipt = qc_project.verify_qc_project(reordered, expected_sha256=self.anchor)
        self.assertEqual(receipt["project_sha256"], self.anchor)

    def test_caller_mutation_during_reconstruction_cannot_replace_the_retained_map(self):
        manifest = qc_project.qc_project_manifest()
        changed = self.files | {"main.py": self.files["main.py"] + b"\n# invented changed caller bytes\n"}
        supplied = dict(changed)
        changed_anchor = project_anchor(supplied)

        def restore_caller():
            supplied.clear()
            supplied.update(self.files)
            return dict(self.files), deepcopy(manifest)

        with patch.object(qc_project, "_prepare_project", side_effect=restore_caller):
            self.assert_refused(supplied, anchor=changed_anchor)
        self.assertEqual(supplied, self.files)
        supplied = dict(self.files)

        def corrupt_caller():
            supplied.clear()
            supplied.update(changed)
            return dict(self.files), deepcopy(manifest)

        with patch.object(qc_project, "_prepare_project", side_effect=corrupt_caller):
            receipt = qc_project.verify_qc_project(supplied, expected_sha256=self.anchor)
        self.assertEqual(supplied, changed)
        self.assertEqual(receipt["project_sha256"], self.anchor)
        self.assertEqual(receipt["project_files"], manifest["project_files"])
        self.assertNotEqual(project_anchor(supplied), receipt["project_sha256"])
        self.assertIs(receipt["qc_upload_allowed"], False)

    def test_manifest_is_detached_and_retains_closed_authority(self):
        first = qc_project.qc_project_manifest()
        first["project_files"]["main.py"]["sha256"] = "0" * 64
        first["native_runtime_verified"] = True
        second = qc_project.qc_project_manifest()
        self.assertEqual(second["project_files"]["main.py"]["sha256"], hash_bytes(self.files["main.py"]))
        self.assertIs(second["native_runtime_verified"], False)
        for key in ("qc_upload_allowed", "qc_launch_allowed", "QC_completed", "market_evidence",
                    "provider_access_allowed", "paper_live_allowed", "point_in_time_evidence"):
            self.assertIs(second[key], False)

    def test_preparation_has_no_extraction_install_sdk_process_or_network_side_effect(self):
        original_open = os.open
        reads = []

        def read_only_open(path, flags, *args, **kwargs):
            self.assertEqual(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND), 0)
            reads.append(str(path))
            return original_open(path, flags, *args, **kwargs)

        with patch.object(os, "open", read_only_open), \
             patch("tempfile.mkdtemp", side_effect=AssertionError("no extraction")), \
             patch("socket.create_connection", side_effect=AssertionError("no network")), \
             patch("socket.socket.connect", side_effect=AssertionError("no network")), \
             patch("subprocess.run", side_effect=AssertionError("no process")), \
             patch.dict(sys.modules, {"AlgorithmImports": None}):
            files = qc_project.build_qc_project()
            qc_project.verify_qc_project(files, expected_sha256=project_anchor(files))
        self.assertEqual(files, self.files)
        self.assertTrue(reads)

    def test_generated_loader_has_static_native_import_no_dynamic_execution_or_provider_edge(self):
        tree = ast.parse(self.files["main.py"].decode())
        calls = {node.func.id if isinstance(node.func, ast.Name) else node.func.attr
                 for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, (ast.Name, ast.Attribute))}
        self.assertFalse(calls & {"eval", "exec", "__import__", "import_module"})
        native_imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                          and node.module == "research.guidance_revision_drift.lean.main"]
        self.assertEqual(len(native_imports), 1)
        imports = [alias.name.split(".")[0] for node in ast.walk(tree)
                   if isinstance(node, ast.Import) for alias in node.names]
        imports += [node.module.split(".")[0] for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom) and node.module]
        self.assertFalse(set(imports) & {"assistant", "risk", "execution", "ml", "requests", "httpx", "alpaca"})
        self.assertFalse(set(imports) & {"base64", "zipfile", "importlib", "runpy"})
        self.assertNotIn(b"_GDR_B64", self.files["main.py"])
        self.assertNotIn(b"_GDR_B64", self.files["gdr_assets.py"])
        self.assertFalse(any(name.startswith("gdr_payload_") for name in self.files))

    def generated_helpers(self):
        """Execute only inert helper definitions, never generated preparation."""
        tree = ast.parse(self.files["main.py"].decode())
        selected = []
        for node in tree.body:
            if isinstance(node, ast.Import):
                if all(alias.name.split(".")[0] in sys.stdlib_module_names for alias in node.names):
                    selected.append(node)
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in sys.stdlib_module_names:
                    selected.append(node)
            elif isinstance(node, ast.Assign) and all(isinstance(target, ast.Name)
                    and target.id.startswith("_GDR_") for target in node.targets):
                try:
                    ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    continue
                selected.append(node)
            elif isinstance(node, ast.FunctionDef):
                selected.append(node)
        namespace = {"__name__": "isolated_generated_readable_helpers"}
        exec(compile(ast.Module(body=selected, type_ignores=[]), "<generated-helper-test>", "exec"), namespace)
        return namespace

    def test_generated_asset_parser_refuses_nonliteral_or_modified_text_without_execution(self):
        namespace = self.generated_helpers()
        parser = namespace["_gdr_assets"]
        raw = self.files["gdr_assets.py"]
        with patch("tempfile.TemporaryDirectory", side_effect=AssertionError("must not materialize data")):
            parsed = parser(raw)
            assets = asset_literals(raw)
            self.assertEqual(parsed, {"gdr0a.draft.json": assets["_GDR_CANDIDATE_JSON"],
                                      "gdr-synthetic.jsonl": assets["_GDR_FIXTURE_JSONL"]})
            for hostile in (
                    raw + b"\nraise AssertionError('asset text must not execute')\n",
                    b"_GDR_CANDIDATE_JSON = str('x')\n_GDR_FIXTURE_JSONL = 'y'\n",
                    b"_GDR_CANDIDATE_JSON = b'x'\n_GDR_FIXTURE_JSONL = 'y'\n",
                    b"_GDR_CANDIDATE_JSON = 'x'\n_GDR_CANDIDATE_JSON = 'y'\n",
                    b"_GDR_CANDIDATE_JSON = 'x'\n_GDR_FIXTURE_JSONL = 'y'\n",
                    b"not valid Python\xff",
                    raw.replace(assets["_GDR_FIXTURE_JSONL"][:20],
                                b"x" + assets["_GDR_FIXTURE_JSONL"][1:20], 1)):
                with self.subTest(sha=hash_bytes(hostile)), \
                     self.assertRaisesRegex(RuntimeError, "GDR .*refused"):
                    parser(hostile)

    def test_generated_inventory_rejects_changed_named_source_without_materialization(self):
        namespace = self.generated_helpers()
        source = "research/guidance_revision_drift/lean/main.py"
        with TemporaryDirectory(prefix="gdr-readable-inventory-test-") as temporary:
            directory = Path(temporary).resolve()
            self.write_project(directory)
            with patch("tempfile.TemporaryDirectory", side_effect=AssertionError("must not materialize data")):
                namespace["_gdr_inventory"](directory)
                path = directory / source
                raw = path.read_bytes()
                changed = bytes([raw[0] ^ 1]) + raw[1:]
                self.assertEqual(len(changed), len(raw))
                path.write_bytes(changed)
                with self.assertRaisesRegex(RuntimeError, "retained identity"):
                    namespace["_gdr_inventory"](directory)

    def test_generated_inventory_refuses_unlisted_importable_package_before_reading_source(self):
        # Otherwise a new json/__init__.py can shadow the standard library
        # when the visible project root is prepended to sys.path. Never
        # execute the harmless marker; inventory must refuse it first.
        for package in ("json", "research/unlisted"):
            with self.subTest(package=package), TemporaryDirectory(prefix="gdr-qc-unlisted-package-") as temporary:
                directory = Path(temporary).resolve()
                self.write_project(directory)
                path = directory / package
                path.mkdir()
                (path / "__init__.py").write_bytes(b"raise AssertionError('must not import unlisted package')\n")
                namespace = self.generated_helpers()
                with patch.object(namespace["os"], "open", side_effect=AssertionError("refuse before source reads")), \
                     self.assertRaises(RuntimeError):
                    namespace["_gdr_inventory"](directory)

    def test_generated_inventory_refuses_unlisted_importable_symlink_directory_without_following_it(self):
        with TemporaryDirectory(prefix="gdr-qc-unlisted-symlink-") as temporary, \
             TemporaryDirectory(prefix="gdr-qc-unlisted-target-") as outside:
            directory = Path(temporary).resolve()
            self.write_project(directory)
            target = Path(outside) / "outside_package"
            target.mkdir()
            (target / "__init__.py").write_bytes(b"raise AssertionError('must not import redirected package')\n")
            (directory / "json").symlink_to(target, target_is_directory=True)
            namespace = self.generated_helpers()
            with patch.object(namespace["os"], "open", side_effect=AssertionError("must not read redirected source")), \
                 self.assertRaises(RuntimeError):
                namespace["_gdr_inventory"](directory)

    def test_generated_inventory_refuses_unlisted_compiled_importable_files_before_source_reads(self):
        for name in ("json.pyc", "json.so", "json.pyd", "research/unlisted.pyc"):
            with self.subTest(name=name), TemporaryDirectory(prefix="gdr-qc-unlisted-compiled-") as temporary:
                directory = Path(temporary).resolve()
                self.write_project(directory)
                (directory / name).write_bytes(b"invented not executable compiled bytes")
                namespace = self.generated_helpers()
                with patch.object(namespace["os"], "open", side_effect=AssertionError("refuse before source reads")), \
                     self.assertRaises(RuntimeError):
                    namespace["_gdr_inventory"](directory)

    def test_stale_audit_bundle_and_source_change_during_readable_preparation_refuse(self):
        members, manifest = native_bundle._snapshot()
        changed_members, changed_manifest = dict(members), deepcopy(manifest)
        path = "research/guidance_revision_drift/lean/main.py"
        changed_members[path] += b"\n# invented changed source epoch\n"
        changed_manifest["source_manifest"][path] = hash_bytes(changed_members[path])
        changed_manifest["source_manifest_sha256"] = hash_payload(changed_manifest["source_manifest"])
        changed_manifest["members"][path] = {"bytes": len(changed_members[path]),
                                             "sha256": hash_bytes(changed_members[path])}
        raw = native_bundle.build_native_bundle()
        with patch.object(qc_project, "build_native_bundle", return_value=raw), \
             patch.object(native_bundle, "_snapshot", return_value=(changed_members, changed_manifest)), \
             self.assertRaisesRegex(qc_project.QCProjectError, "current-source"):
            qc_project.build_qc_project()
        with patch.object(qc_project, "build_native_bundle", return_value=raw), \
             patch.object(native_bundle, "_snapshot", side_effect=[(members, manifest),
                 (changed_members, changed_manifest)]) as snapshot, \
             self.assertRaisesRegex(qc_project.QCProjectError, "source changed while preparing"):
            qc_project.build_qc_project()
        self.assertEqual(snapshot.call_count, 2)

    def runtime(self, directory, *, preloaded=None):
        # The child remains in the designated lane ROOT. -I prevents this
        # checkout's packages from silently satisfying the generated loader.
        # The SDK stub is assembled from existing test definitions only; no
        # production source or provider module is evaluated by that assembly.
        script = r'''
import ast, hashlib, json, pathlib, runpy, sys, types
from decimal import Decimal
from types import ModuleType, SimpleNamespace as NS
directory, shim_path, preloaded = sys.argv[1:]
shim_tree = ast.parse(pathlib.Path(shim_path).read_text())
names = {'CashAmount', 'OrderFee', 'OrderEvent', 'Portfolio', 'Slice', 'QCAlgorithm', 'sdk_shim'}
definitions = [node for node in shim_tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names]
assert {node.name for node in definitions} == names
namespace = {'Decimal': Decimal, 'ModuleType': ModuleType, 'NS': NS}
exec(compile(ast.Module(body=definitions, type_ignores=[]), '<existing-test-sdk-shim>', 'exec'), namespace)
sys.modules['AlgorithmImports'] = namespace['sdk_shim']()
if preloaded:
    sys.modules[preloaded] = types.ModuleType(preloaded)
try:
    loaded = runpy.run_path(str(pathlib.Path(directory) / 'main.py'))
except Exception as exc:
    print(json.dumps({'error_type': type(exc).__name__, 'error': str(exc),
        'loaded_lane': sorted(name for name in sys.modules if name in {'data','research','gdr_assets'} or name.startswith(('data.','research.')))}))
else:
    handle = loaded['_GDR_RUNTIME_DIRECTORY']
    private = pathlib.Path(handle.name)
    files = {str(path.relative_to(private)): {'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
             for path in private.rglob('*') if path.is_file()}
    root_classes = [name for name, value in loaded.items() if isinstance(value, type)
                    and value.__module__ == '<run_path>' and issubclass(value, namespace['QCAlgorithm'])]
    root_class = loaded['GuidanceRevisionDriftAlgorithm']
    overrides = sorted(name for name in root_class.__dict__ if not name.startswith('__'))
    algorithm = root_class()
    algorithm.initialize()
    native = sys.modules[root_class.__bases__[0].__module__]
    initialized = {'symbol': algorithm.symbol, 'cash': str(algorithm.portfolio.cash),
                   'native_orders': len(algorithm.native_orders),
                   'account_checkpoints': algorithm.bridge._account_checkpoints,
                   'sidecar_sha256': hashlib.sha256(native.DATA_PATH.read_bytes()).hexdigest()}
    contracts = sys.modules['research.guidance_revision_drift.contracts']
    lane_files = [str(getattr(module, '__file__', '')) for name, module in sys.modules.items()
                  if name in {'data','research'} or name.startswith(('data.','research.'))]
    print(json.dumps({'files': files, 'root_classes': root_classes, 'callback_overrides': overrides,
                      'initialized': initialized,
                      'private': str(private), 'lane_files': lane_files,
                      'asset_module_imported': 'gdr_assets' in sys.modules,
                      'candidate_path': str(contracts._SPEC_PATH), 'sidecar_path': str(native.DATA_PATH),
                      'pycache_prefix': sys.pycache_prefix, 'dont_write_bytecode': sys.dont_write_bytecode,
                      'sdk_is_shim': sys.modules['AlgorithmImports'].__file__ if hasattr(sys.modules['AlgorithmImports'], '__file__') else True}))
    handle.cleanup()
'''
        environment = dict(os.environ)
        temporary = directory / "private-temp"
        temporary.mkdir()
        environment["TMPDIR"] = str(temporary)
        completed = subprocess.run([sys.executable, "-I", "-B", "-c", script,
                                    str(directory), str(SHIM_SOURCE), preloaded or ""],
                                   cwd=ROOT, env=environment, capture_output=True,
                                   text=True, timeout=30, check=True)
        self.assertEqual(completed.stderr, "")
        self.assertEqual(list(temporary.iterdir()), [], "refusal must precede data preparation; success cleans only its private data root")
        return json.loads(completed.stdout)

    def write_project(self, directory):
        for name, raw in self.files.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)

    def test_fresh_isolated_root_keeps_native_source_visible_and_materializes_only_exact_data_shim_only(self):
        with TemporaryDirectory(prefix="gdr-qc-project-test-") as temporary:
            directory = Path(temporary).resolve()
            self.write_project(directory)
            result = self.runtime(directory)
        self.assertNotIn("error", result)
        self.assertEqual(result["root_classes"], ["GuidanceRevisionDriftAlgorithm"])
        self.assertEqual(result["callback_overrides"], ["_gdr_runtime_context"])
        self.assertEqual(result["initialized"], {"symbol": "SYN-GDR", "cash": "100000", "native_orders": 0,
            "account_checkpoints": 0, "sidecar_sha256": hash_bytes(fixture_stream())})
        self.assertIs(result["sdk_is_shim"], True)
        assets = asset_literals(self.files["gdr_assets.py"])
        expected = {name: {"bytes": len(raw), "sha256": hash_bytes(raw)} for name, raw in (
            ("gdr0a.draft.json", assets["_GDR_CANDIDATE_JSON"]),
            ("gdr-synthetic.jsonl", assets["_GDR_FIXTURE_JSONL"]))}
        self.assertEqual(result["files"], expected)
        self.assertIs(result["asset_module_imported"], False)
        self.assertEqual(result["candidate_path"], result["private"] + "/gdr0a.draft.json")
        self.assertEqual(result["sidecar_path"], result["private"] + "/gdr-synthetic.jsonl")
        self.assertTrue(result["lane_files"])
        self.assertTrue(all(path.startswith(str(directory) + "/") for path in result["lane_files"]))
        self.assertFalse(any(path.startswith(result["private"] + "/") for path in result["lane_files"]))

    def test_loader_altered_missing_extra_and_symlink_source_refuse_before_import_or_data_preparation(self):
        source = "research/guidance_revision_drift/lean/main.py"
        for mode in ("altered", "missing", "extra", "nested_extra", "symlink", "asset_symlink", "root_symlink"):
            with self.subTest(mode=mode), TemporaryDirectory(prefix="gdr-qc-refusal-test-") as temporary:
                directory = Path(temporary).resolve()
                self.write_project(directory)
                path = directory / source
                if mode == "altered":
                    path.write_bytes(path.read_bytes() + b"\nraise AssertionError('must not execute changed source')\n")
                elif mode == "missing":
                    path.unlink()
                elif mode == "extra":
                    (directory / "extra.py").write_bytes(b"raise AssertionError('must not import')\n")
                elif mode == "nested_extra":
                    (directory / "research/guidance_revision_drift/extra.py").write_bytes(
                        b"raise AssertionError('must not import')\n")
                else:
                    if mode == "root_symlink":
                        path = directory / "main.py"
                    elif mode == "asset_symlink":
                        path = directory / "gdr_assets.py"
                    # A non-Python neighbor avoids exercising the earlier
                    # unexpected-.py inventory guard instead of leaf refusal.
                    target = directory / "target.bin"
                    target.write_bytes(path.read_bytes())
                    path.unlink()
                    path.symlink_to(target)
                result = self.runtime(directory)
                self.assertIn("error", result)
                if mode in {"symlink", "asset_symlink", "root_symlink"}:
                    self.assertIn("regular file", result["error"])
                self.assertEqual(result["loaded_lane"], [])

    def test_loader_refuses_same_size_source_and_asset_mutations_by_retained_hash(self):
        for source in ("research/guidance_revision_drift/lean/main.py", "gdr_assets.py"):
            original = self.files[source]
            changed = bytes([original[0] ^ 1]) + original[1:]
            self.assertEqual(len(changed), len(original))
            with self.subTest(source=source), TemporaryDirectory(prefix="gdr-qc-same-size-test-") as temporary:
                directory = Path(temporary).resolve()
                self.write_project(directory)
                (directory / source).write_bytes(changed)
                result = self.runtime(directory)
                self.assertIn("project file differs from retained identity", result.get("error", ""))
                self.assertEqual(result.get("loaded_lane"), [])

    def test_loader_refuses_symlink_parent_directories_before_reading_or_importing_source(self):
        for source in ("data", "research", "research/guidance_revision_drift/lean"):
            with self.subTest(parent=source), \
                 TemporaryDirectory(prefix="gdr-qc-parent-link-test-") as temporary, \
                 TemporaryDirectory(prefix="gdr-qc-parent-target-test-") as outside:
                directory = Path(temporary).resolve()
                self.write_project(directory)
                path = directory / source
                redirected = Path(outside) / "redirected"
                path.rename(redirected)
                path.symlink_to(redirected, target_is_directory=True)
                result = self.runtime(directory)
                self.assertIn("error", result)
                self.assertEqual(result.get("loaded_lane"), [])

    def test_loader_bypasses_timestamp_valid_cached_substitute_without_executing_it(self):
        # -B stops writes, not reads. A timestamp/size-valid cache can execute
        # code unrelated to the hash-verified .py source while __file__ still
        # names that source. The marker raises only if private cache isolation
        # fails; the production wrapper must load the readable source.
        with TemporaryDirectory(prefix="gdr-qc-cached-substitute-") as temporary:
            directory = Path(temporary).resolve()
            self.write_project(directory)
            source = directory / "research/guidance_revision_drift/lean/main.py"
            metadata = source.stat()
            cache = Path(cache_from_source(str(source)))
            cache.parent.mkdir()
            marker = "must not execute cached substitute"
            code = compile("raise RuntimeError(" + repr(marker) + ")\n", str(source), "exec")
            cache.write_bytes(MAGIC_NUMBER + struct.pack("<III", 0,
                int(metadata.st_mtime) & 0xffffffff, metadata.st_size & 0xffffffff) + marshal.dumps(code))
            result = self.runtime(directory)
        self.assertNotIn("error", result)
        self.assertEqual(result["initialized"]["symbol"], "SYN-GDR")
        self.assertEqual(result["pycache_prefix"], result["private"] + "/unused-bytecode-cache")
        self.assertIs(result["dont_write_bytecode"], True)
        self.assertEqual(set(result["files"]), {"gdr0a.draft.json", "gdr-synthetic.jsonl"})
        self.assertTrue(all(path.startswith(str(directory) + "/") for path in result["lane_files"]))

    def test_loader_preloaded_root_or_descendant_collision_refuses_before_data_preparation(self):
        for name in ("data", "research", "gdr_assets", "data.hashing", "research.guidance_revision_drift"):
            with self.subTest(name=name), TemporaryDirectory(prefix="gdr-qc-collision-test-") as temporary:
                directory = Path(temporary).resolve()
                self.write_project(directory)
                result = self.runtime(directory, preloaded=name)
                self.assertIn("error", result)
                self.assertEqual(result["loaded_lane"], [name])


if __name__ == "__main__":
    unittest.main()
