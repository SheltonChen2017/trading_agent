"""Exact narrow runtime boundary diff; no native engine or private I/O."""
import ast
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / 'research/target_price_revisions_qc'


def test_only_identity_and_lossless_store_boundaries_change():
    original = (ROOT / 'extended_algorithm.py').read_text()
    successor = (ROOT / 'extended_algorithm_successor.py').read_text()
    changes = (
        ('import extended_core as core\n', 'import extended_core as core\nfrom extended_runtime_successor import DeferredPrivateEvidence\nfrom extended_compressed_store import CompressedInputStore, CompressedAuditStore\n'),
        ('            self._signal_store = core.SignalStore(self.object_store, SIGNAL_MANIFEST_JSON,\n', '            from compressed_packet import COMPRESSION_JSON\n            self._signal_store = core.SignalStore(CompressedInputStore(self.object_store, COMPRESSION_JSON), SIGNAL_MANIFEST_JSON,\n'),
        ('        self._evidence = core.PrivateEvidence({', '        self._evidence = DeferredPrivateEvidence({'),
        ('            "input_hashes": self._config["input_hashes"], "attempt": EXPECTED_ATTEMPT,\n            "project_id": self.project_id, "job_id": self.algorithm_id})', '            "input_hashes": self._config["input_hashes"], "attempt": EXPECTED_ATTEMPT},\n            lambda: (self.project_id, self.algorithm_id, self.get_locked()))'),
        ('    def _rebalance(self):\n', '    def _rebalance(self):\n        self._evidence.require_binding()\n'),
        ('    def on_data(self, data):\n', '    def on_data(self, data):\n        self._evidence.require_binding()\n'),
        ('    def on_order_event(self, event):\n', '    def on_order_event(self, event):\n        self._evidence.require_binding()\n'),
        ('        pointer = self._evidence.export(self.object_store)\n', '        self._evidence.require_binding()\n        pointer = self._evidence.export(CompressedAuditStore(self.object_store, self._evidence.binding))\n'),
    )
    expected = original
    for old, new in changes:
        assert expected.count(old) == 1
        expected = expected.replace(old, new)
    assert successor == expected


def test_executed_runtime_core_remain_byte_identical():
    for name, identity in (
        ('extended_algorithm.py', '0c5f72659d52525d16993d60c675d0949f4e0509956c620d5f195d26a41698b9'),
        ('extended_core.py', '706ed5efdcb3999400c5349dc8b5200be1d48c4bb01cbfc7fb080608a679d5da'),
    ):
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == identity


def test_rendered_attempts_fit_cloud_file_bound_and_compile():
    source = (ROOT / 'extended_algorithm_successor.py').read_text()
    for attempt in (1, 2, 3):
        rendered = source.replace('__EXTENDED_CONFIG_SHA256__', 'a' * 64).replace('__ATTEMPT_NUMBER__', str(attempt))
        assert len(rendered.encode()) <= 60000
        compile(ast.parse(rendered), 'main.py', 'exec')


def test_native_binding_gates_precede_strategy_and_accounting_events():
    tree = ast.parse((ROOT / 'extended_algorithm_successor.py').read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'TargetPriceExtendedAlgorithm')
    methods = {node.name: node for node in cls.body if isinstance(node, ast.FunctionDef)}
    for name in ('_rebalance', 'on_data', 'on_order_event'):
        call = methods[name].body[0]
        assert isinstance(call, ast.Expr) and isinstance(call.value, ast.Call)
        assert ast.unparse(call.value) == 'self._evidence.require_binding()'
    branch = next(node for node in methods['initialize'].body if isinstance(node, ast.If) and ast.unparse(node.test) == "self._config['arm'] == 'tpr_on'")
    assert any(isinstance(node, ast.ImportFrom) and node.module == 'compressed_packet' for node in branch.body)
    assert not any(isinstance(node, ast.ImportFrom) and node.module == 'compressed_packet' for node in tree.body)
