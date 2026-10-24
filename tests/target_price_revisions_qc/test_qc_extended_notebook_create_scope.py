"""AST-only synthetic permission-coherence regression; no holder execution."""
import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "research/target_price_revisions_qc/extended_refusal_witness_notebook_create_scope_successor.py"


def contract(source):
    assignments = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "plan" for t in n.targets)]
    assert len(assignments) == 1 and isinstance(assignments[0].value, ast.Dict)
    pairs = assignments[0].value
    keys = [ast.literal_eval(k) for k in pairs.keys]
    assert len(keys) == len(set(keys))
    constants = {k: v.value for k, v in zip(keys, pairs.values) if isinstance(v, ast.Constant)}
    assert "notebook_creation_or_execution" not in keys
    for key in ("notebook_creations", "max_new_notebook_creations", "messages", "new_own_chats"):
        assert type(constants[key]) is int and constants[key] == 1
    for key in ("notebook_executions", "max_native_contains", "max_native_reads", "source_edits", "mode_changes", "compiles", "jobs"):
        assert type(constants[key]) is int and constants[key] == 0
    return constants


def test_permission_manifest_is_coherent_before_any_actual_scope():
    contract(SOURCE.read_text())


def test_spent_predecessor_manifest_is_rejected_by_the_new_coherence_guard():
    old = ROOT / "research/target_price_revisions_qc/extended_refusal_witness_notebook_create_scope.py"
    with pytest.raises(AssertionError):
        contract(old.read_text())


@pytest.mark.parametrize("before,after", [
    ('"notebook_creations": 1', '"notebook_creation_or_execution": 0'),
    ('"notebook_creations": 1', '"notebook_creations": 0'),
    ('"notebook_executions": 0', '"notebook_executions": 1'),
    ('"max_native_reads": 0', '"max_native_reads": 2'),
    ('"compiles": 0', '"compiles": 1'),
    ('"jobs": 0', '"jobs": 1'),
])
def test_in_memory_permission_mutants_refuse_without_holder_or_private_effects(before, after):
    original = SOURCE.read_text()
    contract(original)
    assert before in original
    with pytest.raises(AssertionError):
        contract(original.replace(before, after))
    contract(original)
