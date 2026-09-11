"""Offline contract tests for the ARV2-4F-B5B LEAN source scaffold."""
from __future__ import annotations

import ast
import hashlib
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "research" / "lean" / "analyst_revisions_v2_scaffold.py"
B4_SOURCE = (
    ROOT
    / "research"
    / "analyst_revisions_v2_qc"
    / "object_store_read_contract.py"
)
RUN_CONTRACT_SOURCE = (
    ROOT / "research" / "analyst_revisions_v2_qc" / "run_contract.py"
)

EXPECTED_CONSTANTS = {
    "SCAFFOLD_SCHEMA": "arv2-qc-lean-entry-scaffold-v2",
    "SOURCE_ASSEMBLY_SCHEMA": "arv2-qc-lean-source-assembly-schema-v1",
    "STATUS": "offline_source_inventory_authenticated_runtime_refuses",
    "AUTHORITY": (
        "source_structure_only_no_credential_account_project_configuration_"
        "object_store_provider_input_outcome_upload_compile_launch_result_"
        "deployment_order_or_trading_authority"
    ),
    "QC_CLOUD_ENTRY_NAME": "main.py",
    "SCAFFOLD_ONLY_MARKER": (
        "ARV2-4F-B5B SOURCE_ASSEMBLY_ONLY: QC execution is not authorized"
    ),
    "PHYSICAL_ADAPTER_PRESENT": False,
    "REAL_QC_OBJECT_STORE_ACCESS_PERFORMED": False,
    "CLOUD_COMPILE_PERFORMED": False,
    "BACKTEST_PERFORMED": False,
    "EVALUATION_ID": "arv2-eval-stock-historical-qc-001",
    "ALGORITHM_ID": "arv2-qc-stock-event-study-core-v2",
    "RUN_CONTRACT_SCHEMA": "arv2-qc-stock-event-study-run-candidate-v2",
    "RUN_CONTRACT_SOURCE_SHA256": (
        "a72aa500a5c2d2fe68cfe9a00e6531a8c1a241e212cb8df8e2a7a56dba3d77d5"
    ),
    "B4_SCHEMA_ID": "arv2-qc-object-store-read-contract-5dcb6cffb8f9688b",
    "B4_SCHEMA_SHA256": (
        "5dcb6cffb8f9688b1a63a0ea452fd7f4c3e706df7941691ede58c95e0f055dd2"
    ),
    "B4_SCHEMA_ARTIFACT_SHA256": (
        "95c3242405dddaaec40af01113a6823235fa74fcf405ab7b30ab5c6a45a8e987"
    ),
    "B4_SOURCE_SHA256": (
        "bf370a894986cec8ac341ef8f43bce91aeab4568295ab94c281ce5defaa4d2e3"
    ),
    "B4_SOURCE_CANONICAL_LF_BYTE_COUNT": 57_361,
    "FORMAL_PRIMARY_FOLD_IDS": tuple(
        f"arv2-wf-test-{year}" for year in range(2020, 2026)
    ),
    "DESCRIPTIVE_SENSITIVITY_FOLD_IDS": tuple(
        f"arv2-wf-test-{year}" for year in range(2021, 2026)
    ),
    "CAPABILITY_FLAGS": (
        ("credential_access", False),
        ("qc_account_access", False),
        ("project_creation", False),
        ("project_configuration", False),
        ("object_store_read", False),
        ("object_store_write", False),
        ("provider_access", False),
        ("production_input_read", False),
        ("outcome_access", False),
        ("upload", False),
        ("cloud_compile", False),
        ("backtest_launch", False),
        ("result_access", False),
        ("result_disposition", False),
        ("deployment", False),
        ("orders", False),
        ("trading", False),
    ),
}


def _source_text() -> str:
    return SOURCE.read_text(encoding="utf-8")


def _canonical_lf_bytes(path: Path) -> bytes:
    raw = path.read_bytes()
    without_crlf = raw.replace(b"\r\n", b"\n")
    assert b"\r" not in without_crlf
    return without_crlf


def _tree(text: str | None = None) -> ast.Module:
    return ast.parse(_source_text() if text is None else text)


def _literal_constants(tree: ast.Module) -> dict[str, object]:
    constants: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name):
            constants[target.id] = ast.literal_eval(node.value)
    return constants


def _algorithm_class(tree: ast.Module) -> ast.ClassDef:
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and any(isinstance(base, ast.Name) and base.id == "QCAlgorithm" for base in node.bases)
    ]
    assert len(classes) == 1
    return classes[0]


def _assert_static_contract(text: str) -> None:
    tree = _tree(text)
    assert isinstance(tree.body[0], ast.Expr)
    assert isinstance(tree.body[0].value, ast.Constant)
    assert isinstance(tree.body[0].value.value, str)
    imports = [
        node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    assert len(imports) == 1
    imported = imports[0]
    assert isinstance(imported, ast.ImportFrom)
    assert imported.module == "AlgorithmImports"
    assert [(alias.name, alias.asname) for alias in imported.names] == [("*", None)]

    assignments = [node for node in tree.body if isinstance(node, ast.Assign)]
    assert all(
        len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
        for node in assignments
    )
    assert [node.targets[0].id for node in assignments] == list(EXPECTED_CONSTANTS)
    assert not any(isinstance(node, ast.AnnAssign) for node in tree.body)

    constants = _literal_constants(tree)
    assert constants == EXPECTED_CONSTANTS
    assert all(flag is False for _name, flag in constants["CAPABILITY_FLAGS"])

    algorithm = _algorithm_class(tree)
    assert algorithm.name == "AnalystRevisionsV2StockEventStudyScaffold"
    assert len(algorithm.bases) == 1
    assert isinstance(algorithm.bases[0], ast.Name)
    assert algorithm.bases[0].id == "QCAlgorithm"
    assert isinstance(algorithm.bases[0].ctx, ast.Load)
    assert not getattr(algorithm, "type_params", ())
    assert tree.body[-1] is algorithm
    assert len(tree.body) == 2 + len(assignments) + 1
    assert all(
        isinstance(node, (ast.Expr, ast.FunctionDef)) for node in algorithm.body
    )
    assert isinstance(algorithm.body[0], ast.Expr)
    assert isinstance(algorithm.body[0].value, ast.Constant)
    assert isinstance(algorithm.body[0].value.value, str)
    assert not algorithm.decorator_list
    assert not algorithm.keywords
    methods = {
        node.name: node for node in algorithm.body if isinstance(node, ast.FunctionDef)
    }
    assert set(methods) == {"initialize", "on_end_of_algorithm"}
    assert len(algorithm.body) == 1 + len(methods)
    for method in methods.values():
        assert not method.decorator_list
        assert not getattr(method, "type_params", ())
        assert method.returns is None
        assert method.type_comment is None
        assert len(method.args.args) == 1
        assert method.args.args[0].arg == "self"
        assert method.args.args[0].annotation is None
        assert not method.args.posonlyargs
        assert not method.args.kwonlyargs
        assert method.args.vararg is None
        assert method.args.kwarg is None
        assert not method.args.defaults
        assert not method.args.kw_defaults

    initialize = methods["initialize"]
    assert len(initialize.body) == 1
    refusal = initialize.body[0]
    assert isinstance(refusal, ast.Raise)
    assert isinstance(refusal.exc, ast.Call)
    assert isinstance(refusal.exc.func, ast.Name)
    assert refusal.exc.func.id == "RuntimeError"
    assert len(refusal.exc.args) == 1
    assert isinstance(refusal.exc.args[0], ast.Name)
    assert refusal.exc.args[0].id == "SCAFFOLD_ONLY_MARKER"
    assert not refusal.exc.keywords
    assert refusal.cause is None

    on_end = methods["on_end_of_algorithm"]
    assert len(on_end.body) == 1
    assert isinstance(on_end.body[0], ast.Return)
    assert isinstance(on_end.body[0].value, ast.Constant)
    assert on_end.body[0].value.value is None

    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert len(calls) == 1
    assert not any(isinstance(node, ast.Attribute) for node in ast.walk(tree))
    assert not any(isinstance(node, (ast.With, ast.AsyncWith)) for node in ast.walk(tree))


def _load_with_stub() -> dict[str, object]:
    class StubQCAlgorithm:
        def __getattr__(self, name: str) -> object:
            raise AssertionError(f"scaffold touched a LEAN service: {name}")

    fake = types.ModuleType("AlgorithmImports")
    fake.QCAlgorithm = StubQCAlgorithm
    previous = sys.modules.get("AlgorithmImports")
    sys.modules["AlgorithmImports"] = fake
    try:
        namespace: dict[str, object] = {"__name__": "arv2_b5b_test"}
        source = _source_text()
        exec(compile(source, str(SOURCE), "exec"), namespace)
        return namespace
    finally:
        if previous is None:
            sys.modules.pop("AlgorithmImports", None)
        else:
            sys.modules["AlgorithmImports"] = previous


def test_scaffold_has_one_exact_source_only_lean_entry_shape() -> None:
    _assert_static_contract(_source_text())


def test_scaffold_refuses_before_touching_any_lean_service() -> None:
    namespace = _load_with_stub()
    algorithm_type = namespace["AnalystRevisionsV2StockEventStudyScaffold"]
    algorithm = algorithm_type()

    with pytest.raises(RuntimeError, match="^ARV2-4F-B5B SOURCE_ASSEMBLY_ONLY"):
        algorithm.initialize()
    assert algorithm.on_end_of_algorithm() is None


def test_scaffold_pins_the_accepted_b4_and_run_contract_sources() -> None:
    constants = _literal_constants(_tree())
    b4_bytes = _canonical_lf_bytes(B4_SOURCE)
    run_bytes = _canonical_lf_bytes(RUN_CONTRACT_SOURCE)

    assert len(b4_bytes) == constants["B4_SOURCE_CANONICAL_LF_BYTE_COUNT"]
    assert hashlib.sha256(b4_bytes).hexdigest() == constants["B4_SOURCE_SHA256"]
    assert (
        hashlib.sha256(run_bytes).hexdigest()
        == constants["RUN_CONTRACT_SOURCE_SHA256"]
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.replace(
            '("credential_access", False)', '("credential_access", True)', 1
        ),
        lambda value: value.replace(
            'DESCRIPTIVE_SENSITIVITY_FOLD_IDS = (\n    "arv2-wf-test-2021",',
            'DESCRIPTIVE_SENSITIVITY_FOLD_IDS = (\n    "arv2-wf-test-2020",',
            1,
        ),
        lambda value: value.replace(
            "raise RuntimeError(SCAFFOLD_ONLY_MARKER)", "return None", 1
        ),
        lambda value: value.replace(
            "def initialize(self):",
            "def initialize(self):\n        self.object_store.read_bytes('x')",
            1,
        ),
        lambda value: value.replace(
            "bf370a894986cec8ac341ef8f43bce91aeab4568295ab94c281ce5defaa4d2e3",
            "0f370a894986cec8ac341ef8f43bce91aeab4568295ab94c281ce5defaa4d2e3",
            1,
        ),
        lambda value: value + "\ndef launch_backtest(client):\n    return client\n",
        lambda value: value.replace(
            '    """Refuses before a LEAN service and cannot compute an evaluation."""',
            '    """Refuses before a LEAN service and cannot compute an evaluation."""\n\n'
            "    trading = True",
            1,
        ),
        lambda value: value.replace(
            "SCAFFOLD_SCHEMA = \"arv2-qc-lean-entry-scaffold-v2\"",
            "PROJECT_CREATION = DEPLOYMENT = True\n"
            "SCAFFOLD_SCHEMA = \"arv2-qc-lean-entry-scaffold-v2\"",
            1,
        ),
        lambda value: value.replace(
            "Scaffold(QCAlgorithm):", "Scaffold(QCAlgorithm, object):", 1
        ),
        lambda value: value.replace(
            "raise RuntimeError(SCAFFOLD_ONLY_MARKER)",
            "raise RuntimeError(SCAFFOLD_ONLY_MARKER) from SystemExit",
            1,
        ),
        lambda value: value.replace(
            "def initialize(self):", "def initialize(self) -> object:", 1
        ),
        lambda value: value.replace(
            "RuntimeError(SCAFFOLD_ONLY_MARKER)",
            "RuntimeError(SCAFFOLD_ONLY_MARKER, unsafe=True)",
            1,
        ),
        lambda value: value.replace(
            "Scaffold(QCAlgorithm):", "Scaffold[T](QCAlgorithm):", 1
        ),
    ],
    ids=(
        "grant-capability",
        "replace-descriptive-fold",
        "remove-refusal",
        "touch-object-store",
        "change-b4-source-pin",
        "add-top-level-launch-callable",
        "add-class-level-trading-flag",
        "add-multi-target-authority",
        "add-extra-base",
        "add-exception-cause",
        "add-method-annotation",
        "add-refusal-keyword",
        "add-class-type-parameter",
    ),
)
def test_scaffold_contract_rejects_single_invariant_mutations(mutate) -> None:
    source = _source_text()
    mutated = mutate(source)
    assert mutated != source
    with pytest.raises(AssertionError):
        _assert_static_contract(mutated)
