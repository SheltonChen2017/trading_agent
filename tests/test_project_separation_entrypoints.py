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
import sys

from data.research_results import (
    LeveragedPairResearchResult,
    SignalTriggerResult,
)
from assistant.runtime_identity import (
    RuntimeIdentityError as AssistantRuntimeIdentityError,
    current_commit as assistant_current_commit,
)
from assistant.operations import append_alerts_jsonl as assistant_append_alerts_jsonl
from data.operational_alerts import append_alerts_jsonl
from data.runtime_identity import RuntimeIdentityError, current_commit


ROOT = Path(__file__).resolve().parents[1]
ENTRY_POINT_MANIFEST = ROOT / "architecture" / "entry_points.json"
BOUNDARY_MANIFEST = ROOT / "architecture" / "project_boundaries.json"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _imported_modules(path: Path) -> set[str]:
    """Every absolute module name a file imports, not only its root package."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
            modules.update(
                f"{node.module}.{alias.name}"
                for alias in node.names
                if alias.name != "*"
            )
    return modules


def _import_roots(path: Path) -> set[str]:
    return {module.split(".", 1)[0] for module in _imported_modules(path)}


def _source_files(root: Path, pattern: str = "*"):
    """Every source file under ``root``, including files in subdirectories.

    SEP2-002: the inventories originally used ``iterdir()``/``glob()``, which
    see only the top level. A file added under a new ``scripts/`` or ``data/``
    subdirectory was therefore neither classified nor scanned for crossings --
    the exact silent growth this module's docstring forbids. Mutation-proved:
    a rogue ``scripts/<pkg>/rogue.py`` importing both products passed 8/8.
    """
    return (
        path
        for path in root.rglob(pattern)
        if path.is_file() and "__pycache__" not in path.parts
    )


def _product_import_roots(products: dict, product: str) -> set[str]:
    """Import roots a product owns, normalized identically for both products.

    SEP2-003: ``strategy_research`` owns ``baskets.py``, whose import root is
    ``baskets``, so the research side applied ``Path.stem`` while the assistant
    side used the raw manifest value. Adding any top-level ``.py`` module to
    ``trading_assistant`` would have silently blinded that half of the guard,
    because ``"module.py"`` can never equal an import root.
    """
    return {Path(root).stem for root in products[product]["owned_roots"]}


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
    actual = sorted(_relative(path) for path in _source_files(ROOT / "scripts"))
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
    assistant_roots = _product_import_roots(products, "trading_assistant")
    research_roots = _product_import_roots(products, "strategy_research")
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
    assistant_roots = _product_import_roots(products, "trading_assistant")
    research_roots = _product_import_roots(products, "strategy_research")
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
    assert "anthropic==0.120.0" in research
    assert not {"alpaca-py==0.43.5", "streamlit==1.60.0"} & research
    assert "pytest==9.1.1" not in assistant | research


def test_product_dependency_manifests_cover_actual_imports():
    manifest = _json(ENTRY_POINT_MANIFEST)
    boundaries = _json(BOUNDARY_MANIFEST)
    distribution_for_import = {
        "alpaca": "alpaca-py==0.43.5",
        "anthropic": "anthropic==0.120.0",
        "databento": "databento==0.81.0",
        "joblib": "joblib==1.5.3",
        "lxml": "lxml==6.1.1",
        "numpy": "numpy==2.5.1",
        "pandas": "pandas==3.0.5",
        "pandas_market_calendars": "pandas_market_calendars==5.4.0",
        "requests": "requests==2.34.2",
        "sklearn": "scikit-learn==1.9.0",
        "streamlit": "streamlit==1.60.0",
        "yfinance": "yfinance==1.5.2",
    }
    first_party = {
        Path(root).stem
        for product in boundaries["products"].values()
        for root in product["owned_roots"]
    } | {"data", "scripts", "config", "market_analytics"}
    standard = set(sys.stdlib_module_names) | {"__future__"}

    for product in ("trading_assistant", "strategy_research"):
        paths = {
            path
            for root in boundaries["products"][product]["owned_roots"]
            for path in (
                [ROOT / root]
                if (ROOT / root).is_file()
                else _source_files(ROOT / root, "*.py")
            )
        }
        paths.update(
            ROOT / relative
            for relative in manifest["script_ownership"][product]
            if relative.endswith(".py")
        )
        paths.update(
            ROOT / relative
            for relative, host in manifest["composition_hosts"].items()
            if host == product and relative.endswith(".py")
        )
        imported = {root for path in paths for root in _import_roots(path)}
        third_party = (
            imported
            - first_party
            - standard
            - set(manifest["platform_provided_imports"][product])
        )
        assert third_party <= set(distribution_for_import), (
            f"{product} imports undeclared third-party roots: "
            f"{sorted(third_party - set(distribution_for_import))}"
        )
        declared = _requirements(
            ROOT / manifest["dependency_manifests"][product]
        )
        missing = {
            distribution_for_import[root]
            for root in third_party
            if distribution_for_import[root] not in declared
        }
        assert missing == set(), (
            f"{product} dependency manifest misses imports: {sorted(missing)}"
        )


def test_data_ownership_is_exhaustive_and_shared_provider_debt_cannot_grow():
    manifest = _json(ENTRY_POINT_MANIFEST)
    ownership = manifest["data_ownership"]
    categories = (
        ownership["package_markers"]
        + ownership["neutral_contracts"]
        + ownership["provider_neutral_services"]
        + ownership["product_owned_provider_implementations"]["trading_assistant"]
        + ownership["product_owned_provider_implementations"]["strategy_research"]
        + ownership["shared_provider_debt"]
    )
    actual = sorted(_relative(path) for path in _source_files(ROOT / "data", "*.py"))
    assert len(categories) == len(set(categories))
    assert sorted(categories) == actual, (
        "data/ ownership changed; provider access must receive explicit product "
        "ownership rather than silently enlarging shared debt"
    )
    assert ownership["product_owned_provider_implementations"] == {
        "trading_assistant": [
            "data/corporate_actions.py",
            "data/event_data.py",
            "data/price_source.py",
        ],
        "strategy_research": [
            "data/analyst_data.py",
            "data/earnings_data.py",
            "data/pit_universe.py",
        ],
    }
    assert ownership["provider_neutral_services"] == [
        "data/macro_data.py",
        "data/market_data.py",
        "data/price_target_data.py",
    ]
    assert set(ownership["provider_neutral_rationales"]) == set(
        ownership["provider_neutral_services"]
    )
    assert all(ownership["provider_neutral_rationales"].values())
    assert ownership["shared_provider_debt"] == []


def test_product_owned_provider_implementations_do_not_cross_products():
    manifest = _json(ENTRY_POINT_MANIFEST)
    boundaries = _json(BOUNDARY_MANIFEST)
    products = boundaries["products"]
    owned = manifest["data_ownership"]["product_owned_provider_implementations"]
    provider_modules = {
        product: {
            path.removesuffix(".py").replace("/", ".") for path in paths
        }
        for product, paths in owned.items()
    }

    scan_paths: dict[str, set[Path]] = {}
    for product in ("trading_assistant", "strategy_research"):
        paths = {
            path
            for root in products[product]["owned_roots"]
            for path in (
                [ROOT / root]
                if (ROOT / root).is_file()
                else _source_files(ROOT / root, "*.py")
            )
        }
        paths.update(
            ROOT / relative
            for relative in manifest["script_ownership"][product]
            if relative.endswith(".py")
        )
        paths.update(
            ROOT / relative
            for relative, host in manifest["composition_hosts"].items()
            if host == product and relative.endswith(".py")
        )
        scan_paths[product] = paths

    for product, paths in scan_paths.items():
        other = (
            "strategy_research"
            if product == "trading_assistant"
            else "trading_assistant"
        )
        forbidden = provider_modules[other]
        offenders = {
            _relative(path): sorted(_imported_modules(path) & forbidden)
            for path in paths
            if _imported_modules(path) & forbidden
        }
        assert offenders == {}, (
            f"{product} imports {other}-owned provider implementations: "
            f"{offenders!r}"
        )


def test_runtime_identity_facade_preserves_object_identity():
    assert assistant_current_commit is current_commit
    assert AssistantRuntimeIdentityError is RuntimeIdentityError


def test_operational_alert_facade_preserves_object_identity():
    assert assistant_append_alerts_jsonl is append_alerts_jsonl


def test_no_entry_point_outside_the_trading_assistant_reaches_broad_operations():
    """SEP2P-001, driven to zero by the launch-surface tranche.

    `assistant.operations` reaches the broker lazily through
    `assistant.readiness`, so every entry point outside the trading assistant
    that imports it carries the reach recorded as SEP2-006. Repointing the ML
    evidence supervisor removed one instance and the ML shadow runner now uses
    the same neutral alert writer. This repository's standing "a guard added
    to one generator is not added to its sibling" failure therefore becomes a
    zero-tolerance invariant rather than a retained exception.

    SEP2L-001: named for what it asserts. It began as an exact *shrinking
    ledger* holding `scripts/run_ml_shadow.py`; that entry is gone and the
    assertion is now emptiness, so the old name would invite a future change to
    re-add an entry as though a retained exception were the sanctioned form. It
    is not — the way to satisfy this guard is to remove the import, never to
    record it here.

    A new importer must fail regardless of which research-hosted composition
    surface introduces it.
    """
    manifest = _json(ENTRY_POINT_MANIFEST)
    hosts = {
        relative: category
        for category in ("trading_assistant", "strategy_research")
        for relative in manifest["script_ownership"][category]
    }
    hosts.update(manifest["composition_hosts"])

    actual = {
        relative
        for relative, host in hosts.items()
        if host != "trading_assistant"
        and relative.endswith(".py")
        and "assistant.operations" in _imported_modules(ROOT / relative)
    }
    assert actual == set(), (
        "research and shared-composition entry points may not import broad "
        f"assistant operations authority. actual={sorted(actual)!r}"
    )

    supervisor = _imported_modules(ROOT / "scripts" / "run_ml_evidence_supervisor.py")
    assert "data.operational_alerts" in supervisor
    assert "assistant.operations" not in supervisor
    shadow = _imported_modules(ROOT / "scripts" / "run_ml_shadow.py")
    assert "data.operational_alerts" in shadow
    assert "assistant.operations" not in shadow


def test_licensed_research_surfaces_cannot_enter_execution_products():
    manifest = _json(ENTRY_POINT_MANIFEST)
    licensed_modules = {
        path.removesuffix(".py").replace("/", ".")
        for path in manifest["licensed_research_surfaces"]
    }
    for root_name in ("assistant", "execution", "risk"):
        for path in _source_files(ROOT / root_name, "*.py"):
            imported = _imported_modules(path)
            forbidden = {
                module
                for module in imported
                if any(
                    module == licensed or module.startswith(licensed + ".")
                    for licensed in licensed_modules
                )
            }
            assert not forbidden, f"{_relative(path)} imports licensed research: {forbidden}"


def test_entry_points_outside_the_trading_assistant_cannot_import_authority():
    """SEP2-001. The crossing ledger records root packages, not modules.

    ``declared_python_cross_product_roots`` records that a research-hosted
    composition script imports ``assistant``; it cannot distinguish
    ``assistant.runtime_identity`` from ``assistant.execution_service``. So the
    single most dangerous edit to an existing crossing -- repointing it at
    broker submission, the execution kernel, or the risk gate -- changes no
    declared root and fails no guard. Mutation-proved: adding
    ``from assistant.execution_service import execute_approved_paper_proposal``
    to a research-hosted composition script left all 16 separation guards and
    all 8 ML import-boundary guards green.

    The separation plan's target boundary says strategy research does not own
    broker submission, approvals, reconciliation, or operational authority, and
    that no adapter may expose a broker, approval token, or execution gate to
    research code. Only trading-assistant-hosted launchers may import the
    authority roots. This is a direct-import guard; the pre-existing transitive
    operational chain recorded in the review report is separate debt.
    """
    manifest = _json(ENTRY_POINT_MANIFEST)
    authority = _json(BOUNDARY_MANIFEST)["authority_roots"]
    assert authority, "the boundary manifest declares no execution-authority roots"

    hosts = {
        relative: category
        for category in ("trading_assistant", "strategy_research")
        for relative in manifest["script_ownership"][category]
    }
    hosts.update(manifest["composition_hosts"])

    offenders: dict[str, list[str]] = {}
    for relative, host in sorted(hosts.items()):
        if host == "trading_assistant" or not relative.endswith(".py"):
            continue
        forbidden = sorted(
            module
            for module in _imported_modules(ROOT / relative)
            if any(module == root or module.startswith(root + ".") for root in authority)
        )
        if forbidden:
            offenders[relative] = forbidden

    assert offenders == {}, (
        "an entry point that is not hosted by the trading assistant imports "
        f"execution authority: {offenders!r}"
    )


def test_import_scanner_expands_parent_module_from_imports(tmp_path: Path):
    """An authority or licensed child module cannot hide behind its parent."""
    source = tmp_path / "parent_import.py"
    source.write_text(
        "from assistant import execution_service\n"
        "from research import acer\n",
        encoding="utf-8",
    )

    assert _imported_modules(source) >= {
        "assistant.execution_service",
        "research.acer",
    }


def test_script_import_graph_rejects_dynamic_and_relative_bypasses():
    offenders: list[str] = []
    for path in _source_files(ROOT / "scripts", "*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level:
                offenders.append(f"{_relative(path)}:{node.lineno}:relative-import")
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            if isinstance(function, ast.Name) and function.id in {"__import__", "exec"}:
                offenders.append(f"{_relative(path)}:{node.lineno}:{function.id}")
            if (
                isinstance(function, ast.Attribute)
                and isinstance(function.value, ast.Name)
                and function.value.id == "importlib"
                and function.attr == "import_module"
            ):
                offenders.append(
                    f"{_relative(path)}:{node.lineno}:importlib.import_module"
                )
    assert offenders == [], (
        "scripts use imports the static ownership graph cannot resolve: "
        f"{offenders!r}"
    )


def test_only_immutable_approved_results_cross_the_product_boundary():
    manifest = _json(ENTRY_POINT_MANIFEST)
    assert manifest["approved_cross_product_result_contracts"] == [
        "data/research_results.py"
    ]
    for contract in (SignalTriggerResult, LeveragedPairResearchResult):
        assert dataclasses.is_dataclass(contract)
        assert contract.__dataclass_params__.frozen
