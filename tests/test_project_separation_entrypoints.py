"""SEP-2 guards for entry points, dependencies, and data ownership.

The manifest is an exact inventory, not an allowlist for silent growth. A new
script, a new cross-product import, or a new shared provider module must fail
until it is deliberately owned or removed in a reviewed change.
"""
from __future__ import annotations

import ast
import dataclasses
import json
from pathlib import Path

from data.research_results import (
    LeveragedPairResearchResult,
    SignalTriggerResult,
)


ROOT = Path(__file__).resolve().parents[1]
ENTRY_POINT_MANIFEST = ROOT / "architecture" / "entry_points.json"
BOUNDARY_MANIFEST = ROOT / "architecture" / "project_boundaries.json"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _import_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _requirements(path: Path, seen: set[Path] | None = None) -> set[str]:
    resolved = path.resolve()
    visited = seen or set()
    if resolved in visited:
        raise AssertionError(f"recursive requirements include: {resolved}")
    visited.add(resolved)
    result: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r "):
            result |= _requirements(path.parent / line[3:].strip(), visited)
            continue
        result.add(line)
    visited.remove(resolved)
    return result


def test_every_script_is_classified_exactly_once():
    manifest = _json(ENTRY_POINT_MANIFEST)
    surfaces = manifest["script_ownership"]
    declared = [
        path
        for category in (
            "trading_assistant",
            "strategy_research",
            "cross_product_composition",
        )
        for path in surfaces[category]
    ]
    actual = sorted(_relative(path) for path in (ROOT / "scripts").iterdir() if path.is_file())
    assert len(declared) == len(set(declared)), "a script has more than one owner"
    assert sorted(declared) == actual, (
        "scripts/ classification changed; classify the new entry point or "
        "remove the stale manifest entry"
    )
    assert set(manifest["composition_hosts"]) == set(
        surfaces["cross_product_composition"]
    )


def test_launch_surface_is_every_executable_script_and_no_helper():
    manifest = _json(ENTRY_POINT_MANIFEST)
    ownership = manifest["script_ownership"]
    classified = {
        path for paths in ownership.values() for path in paths
    }
    helpers = set(manifest["non_launch_helpers"])
    expected_helpers = {
        "scripts/candidate_screen_2026_08_03_new_signals.py",
        "scripts/candidate_screen_20260803.py",
        "scripts/product_composition.py",
        "scripts/ui_theme.py",
    }
    assert helpers == expected_helpers
    assert helpers <= classified
    for relative in sorted(classified - helpers):
        path = ROOT / relative
        if path.suffix == ".ps1" or relative == "scripts/personal_assistant_ui.py":
            continue
        source = path.read_text(encoding="utf-8")
        assert '__name__ == "__main__"' in source, (
            f"{relative} is classified as a launch surface but has no direct runner"
        )


def test_product_entry_points_do_not_gain_cross_product_imports():
    manifest = _json(ENTRY_POINT_MANIFEST)
    boundaries = _json(BOUNDARY_MANIFEST)
    products = boundaries["products"]
    assistant_roots = set(products["trading_assistant"]["owned_roots"])
    research_roots = {
        Path(root).stem for root in products["strategy_research"]["owned_roots"]
    }
    surfaces = manifest["script_ownership"]

    for relative in surfaces["trading_assistant"]:
        if relative.endswith(".py"):
            assert not (_import_roots(ROOT / relative) & research_roots), relative
    for relative in surfaces["strategy_research"]:
        if relative.endswith(".py"):
            assert not (_import_roots(ROOT / relative) & assistant_roots), relative


def test_composition_crossings_are_an_exact_debt_ledger():
    manifest = _json(ENTRY_POINT_MANIFEST)
    boundaries = _json(BOUNDARY_MANIFEST)
    products = boundaries["products"]
    assistant_roots = set(products["trading_assistant"]["owned_roots"])
    research_roots = {
        Path(root).stem for root in products["strategy_research"]["owned_roots"]
    }
    declared = {
        path: set(roots)
        for path, roots in manifest["declared_python_cross_product_roots"].items()
    }
    actual: dict[str, set[str]] = {}
    for relative in manifest["script_ownership"]["cross_product_composition"]:
        if not relative.endswith(".py"):
            continue
        host = manifest["composition_hosts"][relative]
        roots = _import_roots(ROOT / relative)
        if host == "trading_assistant":
            crossings = roots & research_roots
        elif host == "strategy_research":
            crossings = roots & assistant_roots
        elif host == "shared_composition":
            crossings = roots & (assistant_roots | research_roots)
        else:
            raise AssertionError(f"unknown composition host for {relative}: {host}")
        if crossings:
            actual[relative] = crossings
    assert actual == declared, (
        "composition imports changed; remove the crossing or update the exact "
        f"reviewed ledger. actual={actual!r}, declared={declared!r}"
    )


def test_product_dependency_declarations_reconstruct_the_legacy_environment():
    common = _requirements(ROOT / "requirements" / "common.txt")
    assistant = _requirements(ROOT / "requirements" / "trading-assistant.txt")
    research = _requirements(ROOT / "requirements" / "strategy-research.txt")
    development = _requirements(ROOT / "requirements" / "development.txt")
    legacy = _requirements(ROOT / "requirements.txt")

    assert development == legacy
    assert common <= assistant and common <= research
    assert "alpaca-py==0.43.5" in assistant
    assert "streamlit==1.60.0" in assistant
    assert "anthropic==0.120.0" in assistant
    assert not {"scikit-learn==1.9.0", "joblib==1.5.3", "databento==0.81.0"} & assistant
    assert {"scikit-learn==1.9.0", "joblib==1.5.3", "databento==0.81.0"} <= research
    assert not {"alpaca-py==0.43.5", "streamlit==1.60.0", "anthropic==0.120.0"} & research
    assert "pytest==9.1.1" not in assistant | research


def test_data_ownership_is_exhaustive_and_shared_provider_debt_cannot_grow():
    manifest = _json(ENTRY_POINT_MANIFEST)
    ownership = manifest["data_ownership"]
    categories = (
        ownership["package_markers"]
        + ownership["neutral_contracts"]
        + ownership["shared_provider_debt"]
    )
    actual = sorted(_relative(path) for path in (ROOT / "data").glob("*.py"))
    assert len(categories) == len(set(categories))
    assert sorted(categories) == actual, (
        "data/ ownership changed; provider access must receive explicit product "
        "ownership rather than silently enlarging shared debt"
    )
    assert ownership["shared_provider_debt"] == [
        "data/analyst_data.py",
        "data/corporate_actions.py",
        "data/earnings_data.py",
        "data/event_data.py",
        "data/macro_data.py",
        "data/market_data.py",
        "data/pit_universe.py",
        "data/price_source.py",
        "data/price_target_data.py",
    ]


def test_licensed_research_surfaces_cannot_enter_execution_products():
    manifest = _json(ENTRY_POINT_MANIFEST)
    licensed_modules = {
        path.removesuffix(".py").replace("/", ".")
        for path in manifest["licensed_research_surfaces"]
    }
    for root_name in ("assistant", "execution", "risk"):
        for path in (ROOT / root_name).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
            forbidden = {
                module
                for module in imported
                if any(
                    module == licensed or module.startswith(licensed + ".")
                    for licensed in licensed_modules
                )
            }
            assert not forbidden, f"{_relative(path)} imports licensed research: {forbidden}"


def test_only_immutable_approved_results_cross_the_product_boundary():
    manifest = _json(ENTRY_POINT_MANIFEST)
    assert manifest["approved_cross_product_result_contracts"] == [
        "data/research_results.py"
    ]
    for contract in (SignalTriggerResult, LeveragedPairResearchResult):
        assert dataclasses.is_dataclass(contract)
        assert contract.__dataclass_params__.frozen
