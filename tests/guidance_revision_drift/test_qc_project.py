"""Offline QC project preparation and SDK-shim loader checks, not LEAN evidence."""
from __future__ import annotations

import ast
import base64
from copy import deepcopy
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import stat
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import warnings
from zipfile import ZIP_DEFLATED, ZipFile

from data.hashing import hash_bytes, hash_payload
from research.guidance_revision_drift import bundle, qc_project
from research.guidance_revision_drift.contracts import CANDIDATE_SHA256
from research.guidance_revision_drift.lean_bridge import fixture_stream
from tests.guidance_revision_drift.test_bundle import repack


ROOT = Path(__file__).resolve().parents[2]
SHIM_SOURCE = ROOT / "tests/guidance_revision_drift/test_lean_source.py"
_UNSET = object()


def project_anchor(files):
    """Independent canonical file-map anchor; not a verifier's self-assertion."""
    return hash_payload({name: {"bytes": len(raw), "sha256": hash_bytes(raw)}
                         for name, raw in sorted(files.items())})


def encoded_bundle(files):
    chunks = []
    for name, raw in sorted(files.items()):
        if name == "main.py":
            continue
        tree = ast.parse(raw.decode("ascii"))
        if (len(tree.body) != 1 or not isinstance(tree.body[0], ast.Assign)
                or len(tree.body[0].targets) != 1
                or not isinstance(tree.body[0].targets[0], ast.Name)
                or tree.body[0].targets[0].id != "_GDR_B64"):
            raise AssertionError("payload must be exactly one literal assignment")
        chunk = ast.literal_eval(tree.body[0].value)
        if type(chunk) is not str:
            raise AssertionError("payload chunk must be an exact string")
        chunks.append(chunk)
    encoded = "".join(chunks).encode("ascii")
    raw = base64.b64decode(encoded, validate=True)
    if base64.b64encode(raw) != encoded:
        raise AssertionError("canonical base64 required")
    return raw


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
        self.assertLessEqual(len(self.files), qc_project.MAX_PROJECT_FILES)
        self.assertTrue(all(name.endswith(".py") and "/" not in name and "\\" not in name
                            for name in self.files))
        self.assertTrue(all(type(raw) is bytes and 0 < len(raw) < qc_project.MAX_PROJECT_FILE_BYTES
                            for raw in self.files.values()))
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
        self.assertIs(manifest["fresh_review_required"], True)
        self.assertIs(manifest["native_runtime_verified"], False)
        self.assertIs(manifest["market_evidence"], False)

    def test_literal_chunks_reconstruct_exact_source_bundle_and_invented_jsonl(self):
        raw = encoded_bundle(self.files)
        self.assertEqual(raw, bundle.build_bundle())
        manifest = qc_project.qc_project_manifest()
        self.assertEqual(hash_bytes(raw), manifest["bundle_sha256"])
        self.assertEqual(len(raw), manifest["bundle_bytes"])
        with ZipFile(BytesIO(raw)) as archive:
            self.assertEqual(archive.read(bundle.SIDECAR_PATH), fixture_stream())
            for name in sorted(bundle._SOURCE_PATHS):
                self.assertEqual(archive.read(name), (ROOT / name).read_bytes(), name)
            inner = json.loads(archive.read(bundle.MANIFEST_PATH))
        self.assertEqual(manifest["source_manifest_sha256"], inner["source_manifest_sha256"])
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
        payload = next(name for name in self.files if name != "main.py")
        for name in ("main.py", payload):
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
        for key in ("qc_upload_allowed", "qc_launch_allowed", "QC_completed", "market_evidence"):
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

    def test_generated_inner_archive_guard_rejects_noncanonical_and_unsafe_zip_without_materialization(self):
        # Execute only the generated parser's standard-library imports,
        # retained constants and two pure functions in a test namespace. The
        # loader's preparation, native import and runtime class are excluded.
        tree = ast.parse(self.files["main.py"].decode())
        selected = [node for node in tree.body if (
            isinstance(node, (ast.Import, ast.ImportFrom))
            and not (isinstance(node, ast.ImportFrom) and node.module.startswith("research.")))
            or (isinstance(node, ast.Assign) and all(isinstance(target, ast.Name)
                and target.id.startswith("_GDR_") for target in node.targets)
                and isinstance(node.value, (ast.Constant, ast.Tuple, ast.BinOp)))
            or (isinstance(node, ast.FunctionDef) and node.name in {"_gdr_refuse", "_gdr_members"})]
        namespace = {"__name__": "isolated_generated_archive_parser"}
        exec(compile(ast.Module(body=selected, type_ignores=[]), "<generated-parser-test>", "exec"), namespace)
        parser = namespace["_gdr_members"]
        raw = encoded_bundle(self.files)
        with patch("tempfile.TemporaryDirectory", side_effect=AssertionError("must not extract")):
            with ZipFile(BytesIO(raw)) as archive:
                expected = {name: archive.read(name) for name in archive.namelist()}
            self.assertEqual(parser(raw), expected)
            before_read = [repack(raw, omit=(bundle.SIDECAR_PATH,)),
                           repack(raw, reverse=True),
                           repack(raw, extra=(("../outside.py", b"unsafe"),)),
                           repack(raw, compression=ZIP_DEFLATED)]
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                before_read.append(repack(raw, extra=((bundle.SIDECAR_PATH, b"duplicate"),)))
            for attribute, value in (("external_attr", (stat.S_IFLNK | 0o777) << 16),
                                     ("date_time", (2025, 1, 1, 0, 0, 0)),
                                     ("comment", b"hidden"), ("extra", b"\x01\x00\x00\x00"),
                                     ("create_system", 0), ("internal_attr", 1)):
                def alter(info, content):
                    if info.filename == bundle.SIDECAR_PATH:
                        setattr(info, attribute, value)
                    return info, content
                before_read.append(repack(raw, change=alter))
            for hostile in before_read:
                with self.subTest(sha=hash_bytes(hostile)), \
                     patch.object(ZipFile, "read", side_effect=AssertionError("validate before reading")), \
                     self.assertRaisesRegex(RuntimeError, "GDR carrier refused"):
                    parser(hostile)
            for hostile in (b"not a zip", b"prefix" + raw, raw + b"suffix"):
                with self.subTest(sha=hash_bytes(hostile)), self.assertRaisesRegex(RuntimeError, "GDR carrier refused"):
                    parser(hostile)
            def changed(info, content):
                return info, content + b"x" if info.filename == bundle.SIDECAR_PATH else content
            with self.assertRaisesRegex(RuntimeError, "GDR carrier refused"):
                parser(repack(raw, change=changed))
            for name in ("../outside.py", "/outside.py", "C:/outside.py", "x\\outside.py", "x//outside.py", "x/./outside.py"):
                namespace["_GDR_EXPECTED_MEMBERS"] = ((name, 1, hash_bytes(b"x")),)
                with self.subTest(expected_path=name), self.assertRaisesRegex(RuntimeError, "unsafe archive member path"):
                    parser(raw)

    def test_stale_bundle_and_source_change_during_carrier_preparation_refuse(self):
        members, manifest = bundle._snapshot()
        changed_members, changed_manifest = dict(members), deepcopy(manifest)
        path = "research/guidance_revision_drift/lean/main.py"
        changed_members[path] += b"\n# invented changed source epoch\n"
        changed_manifest["source_manifest"][path] = hash_bytes(changed_members[path])
        changed_manifest["source_manifest_sha256"] = hash_payload(changed_manifest["source_manifest"])
        changed_manifest["members"][path] = {"bytes": len(changed_members[path]),
                                             "sha256": hash_bytes(changed_members[path])}
        raw = encoded_bundle(self.files)
        with patch.object(qc_project, "build_bundle", return_value=raw), \
             patch.object(bundle, "_snapshot", return_value=(changed_members, changed_manifest)), \
             self.assertRaisesRegex(qc_project.QCProjectError, "current-source"):
            qc_project.build_qc_project()
        with patch.object(qc_project, "build_bundle", return_value=raw), \
             patch.object(bundle, "_snapshot", side_effect=[(members, manifest),
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
        'loaded_lane': sorted(name for name in sys.modules if name in {'data','research'} or name.startswith(('data.','research.')))}))
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
    lane_files = [str(getattr(module, '__file__', '')) for name, module in sys.modules.items()
                  if name in {'data','research'} or name.startswith(('data.','research.'))]
    print(json.dumps({'files': files, 'root_classes': root_classes, 'callback_overrides': overrides,
                      'initialized': initialized,
                      'private': str(private), 'lane_files': lane_files,
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
        self.assertEqual(list(temporary.iterdir()), [], "refusal must precede extraction; success cleans only its private root")
        return json.loads(completed.stdout)

    def write_project(self, directory):
        for name, raw in self.files.items():
            (directory / name).write_bytes(raw)

    def test_fresh_isolated_root_materializes_exact_bundle_and_root_algorithm_shim_only(self):
        with TemporaryDirectory(prefix="gdr-qc-project-test-") as temporary:
            directory = Path(temporary).resolve()
            self.write_project(directory)
            result = self.runtime(directory)
        self.assertNotIn("error", result)
        self.assertEqual(result["root_classes"], ["GuidanceRevisionDriftAlgorithm"])
        self.assertEqual(result["callback_overrides"], [])
        self.assertEqual(result["initialized"], {"symbol": "SYN-GDR", "cash": "100000", "native_orders": 0,
            "account_checkpoints": 0, "sidecar_sha256": hash_bytes(fixture_stream())})
        self.assertIs(result["sdk_is_shim"], True)
        with ZipFile(BytesIO(encoded_bundle(self.files))) as archive:
            expected = {name: {"bytes": len(archive.read(name)), "sha256": hash_bytes(archive.read(name))}
                        for name in archive.namelist()}
        self.assertEqual(result["files"], expected)
        self.assertTrue(result["lane_files"])
        self.assertTrue(all(path.startswith(result["private"] + "/") for path in result["lane_files"]))

    def test_loader_altered_missing_extra_and_symlink_payload_refuse_before_import_or_extraction(self):
        payload = next(name for name in self.files if name != "main.py")
        for mode in ("altered", "missing", "extra", "unexpected_python", "symlink", "root_symlink"):
            with self.subTest(mode=mode), TemporaryDirectory(prefix="gdr-qc-refusal-test-") as temporary:
                directory = Path(temporary).resolve()
                self.write_project(directory)
                path = directory / payload
                if mode == "altered":
                    path.write_bytes(path.read_bytes() + b"\nraise AssertionError('must not execute payload')\n")
                elif mode == "missing":
                    path.unlink()
                elif mode == "extra":
                    (directory / "gdr_payload_999.py").write_bytes(b"raise AssertionError('must not import')\n")
                elif mode == "unexpected_python":
                    (directory / "other.py").write_bytes(b"raise AssertionError('must not import')\n")
                else:
                    if mode == "root_symlink":
                        path = directory / "main.py"
                    # A non-Python neighbor avoids exercising the earlier
                    # unexpected-.py inventory guard instead of leaf refusal.
                    target = directory / "target.bin"
                    target.write_bytes(path.read_bytes())
                    path.unlink()
                    path.symlink_to(target)
                result = self.runtime(directory)
                self.assertIn("error", result)
                if mode in {"symlink", "root_symlink"}:
                    self.assertIn("regular file", result["error"])
                self.assertEqual(result["loaded_lane"], [])

    def test_loader_preloaded_root_or_descendant_collision_refuses_before_extraction(self):
        for name in ("data", "research", "data.hashing", "research.guidance_revision_drift"):
            with self.subTest(name=name), TemporaryDirectory(prefix="gdr-qc-collision-test-") as temporary:
                directory = Path(temporary).resolve()
                self.write_project(directory)
                result = self.runtime(directory, preloaded=name)
                self.assertIn("error", result)
                self.assertEqual(result["loaded_lane"], [name])


if __name__ == "__main__":
    unittest.main()
