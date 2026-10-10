"""Explicit pure import graph: no canonical, provider, operator or secret path."""
import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "research.target_price_revisions_qc"
EDGES = {
    PACKAGE + ".packet": {"research.target_price_revisions_development.raw_candidate",
                          "research.target_price_revisions_development.raw_revision"},
    "research.target_price_revisions_development.raw_candidate": {
        "research.target_price_revisions_development.raw_revision",
        "research.target_price_revisions_development.raw_backtest"},
    "research.target_price_revisions_development.raw_revision": set(),
    "research.target_price_revisions_development.raw_backtest": set(),
}
STDLIB = {"__future__", "collections", "dataclasses", "datetime", "decimal",
          "fractions", "hashlib", "json", "re", "zoneinfo"}


def check_module(module, source):
    tree = ast.parse(source)
    observed = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] in STDLIB for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                assert node.level == 1
                edge = module.rsplit(".", 1)[0] + "." + node.module
                observed.add(edge)
            elif node.module.startswith("research."):
                observed.update(node.module + "." + alias.name for alias in node.names)
            else:
                assert node.module.split(".")[0] in STDLIB
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "__import__", "eval", "exec", "compile", "input"}
    assert observed == EDGES[module]


def test_packet_transitive_import_graph_is_exactly_pure():
    for module in EDGES:
        check_module(module, (ROOT / (module.replace(".", "/") + ".py")).read_text())
    for module in ("research", PACKAGE, "research.target_price_revisions_development"):
        initializer = ast.parse((ROOT / module.replace(".", "/") / "__init__.py").read_text())
        assert all(isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                   and type(node.value.value) is str for node in initializer.body)


@pytest.mark.parametrize("edge", ["assistant", "execution", "risk", "requests", "socket",
                                  "research.target_price_revisions", "research.analyst_revisions_v2"])
def test_injected_authority_or_provider_dependency_is_detected(edge):
    source = (ROOT / "research/target_price_revisions_qc/packet.py").read_text()
    check_module(PACKAGE + ".packet", source)
    with pytest.raises(AssertionError):
        check_module(PACKAGE + ".packet", source + "\nimport " + edge + "\n")
