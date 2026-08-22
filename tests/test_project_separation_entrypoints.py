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
    verify_research_report as neutral_verify_research_report,
)
from backtest.research_report import verify_research_report as legacy_verify_research_report
from assistant.runtime_identity import (
    RuntimeIdentityError as AssistantRuntimeIdentityError,
    current_commit as assistant_current_commit,
)
from assistant.operations import append_alerts_jsonl as assistant_append_alerts_jsonl
from assistant.storage import AssistantStore
from assistant.storage_contracts import StrategyOperationalStore
from data.operational_alerts import append_alerts_jsonl
from data.runtime_identity import RuntimeIdentityError, current_commit


ROOT = Path(__file__).resolve().parents[1]
ENTRY_POINT_MANIFEST = ROOT / "architecture" / "entry_points.json"
BOUNDARY_MANIFEST = ROOT / "architecture" / "project_boundaries.json"
OPERATOR_DATABASE_MANIFEST = ROOT / "architecture" / "operator_database_access.json"


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


def _public_methods(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                child.name
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not child.name.startswith("_")
            }
    raise AssertionError(f"{class_name} is absent from {path}")


def _store_surface(path: Path, public_methods: set[str]) -> tuple[set[str], set[str]]:
    """Methods/attributes reached through a local ``store`` or constructor."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    methods: set[str] = set()
    attributes: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        receiver_is_store = isinstance(node.value, ast.Name) and node.value.id == "store"
        receiver_is_constructor = (
            isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "AssistantStore"
        )
        if not (receiver_is_store or receiver_is_constructor):
            continue
        if node.attr in public_methods:
            methods.add(node.attr)
        else:
            attributes.add(node.attr)
    return methods, attributes


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


def test_operator_database_access_is_an_exact_shrinking_debt_ledger():
    entry_points = _json(ENTRY_POINT_MANIFEST)
    manifest = _json(OPERATOR_DATABASE_MANIFEST)
    declared = manifest["direct_non_assistant_importers"]
    hosts = {
        relative: category
        for category in ("trading_assistant", "strategy_research")
        for relative in entry_points["script_ownership"][category]
    }
    hosts.update(entry_points["composition_hosts"])

    actual = {
        relative
        for relative, host in hosts.items()
        if host != "trading_assistant"
        and relative.endswith(".py")
        and "assistant.storage" in _imported_modules(ROOT / relative)
    }
    assert actual == set(declared), (
        "direct operator-database crossings changed; remove the crossing or "
        f"review the exact debt. actual={sorted(actual)!r}, "
        f"declared={sorted(declared)!r}"
    )
    assert manifest["database_owner"] == "trading_assistant"
    assert manifest["physical_split_authorized"] is False

    public_methods = _public_methods(ROOT / "assistant" / "storage.py", "AssistantStore")
    for relative, contract in declared.items():
        assert hosts[relative] == contract["host"] == "strategy_research"
        methods, attributes = _store_surface(ROOT / relative, public_methods)
        assert methods == set(contract["allowed_methods"]), (
            f"{relative} changed its operator-store method surface. "
            f"actual={sorted(methods)!r}, "
            f"declared={sorted(contract['allowed_methods'])!r}"
        )
        assert attributes == set(contract["allowed_attributes"]), (
            f"{relative} changed its operator-store attribute surface. "
            f"actual={sorted(attributes)!r}, "
            f"declared={sorted(contract['allowed_attributes'])!r}"
        )


def _literal_key_prefix(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr) and node.values:
        head = node.values[0]
        if isinstance(head, ast.Constant) and isinstance(head.value, str):
            return head.value
    return None


def _system_state_accesses(
    path: Path,
) -> tuple[dict[str, list[tuple[int, str | None]]], list[tuple[int, str]]]:
    """Bound direct state calls and expose aliases/reflection as escapes.

    ``None`` means the key could not be bounded statically, which must fail:
    an unbounded key is indistinguishable from a reserved one.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    methods = {"get_system_state", "set_system_state"}
    found = {method: [] for method in methods}
    direct_functions: set[int] = set()
    escapes: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if not (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Name)
            and function.value.id == "store"
            and function.attr in methods
        ):
            if (
                isinstance(function, ast.Name)
                and function.id in {"getattr", "setattr"}
                and node.args
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == "store"
            ):
                escapes.append((node.lineno, function.id))
            continue
        direct_functions.add(id(function))
        if not node.args:
            found[function.attr].append((node.lineno, None))
        else:
            found[function.attr].append(
                (node.lineno, _literal_key_prefix(node.args[0]))
            )
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "store"
            and node.attr in methods
            and id(node) not in direct_functions
        ):
            escapes.append((node.lineno, node.attr))
    return found, escapes


def test_granted_state_access_is_bounded_by_keys_and_direct_calls():
    """SEP2D-001. An allowed method name is not an allowed capability.

    `AssistantStore.set_kill_switch` is literally
    `set_system_state("kill_switch", ...)`, so granting the generic
    `set_system_state` in the operator-database ledger silently subsumes the
    kill-switch writer that the ledger deliberately does not grant --
    and `ledger_bootstrap`, `last_order_reconciliation` and the rest with it.
    Mutation-proved: a research-hosted script disarming the persistent kill
    switch through the granted method passed all 35 separation guards.

    The method ledger is therefore bounded by the state keys each grantee may
    write. A key that cannot be resolved to a literal prefix fails, because an
    unbounded key is indistinguishable from a reserved one.
    """
    manifest = _json(OPERATOR_DATABASE_MANIFEST)
    reserved = manifest["assistant_reserved_state_keys"]
    assert "kill_switch" in reserved, "the execution gate's terminal check must be reserved"

    for relative, contract in manifest["direct_non_assistant_importers"].items():
        accesses, escapes = _system_state_accesses(ROOT / relative)
        assert escapes == [], (
            f"{relative} aliases or reflects generic system-state capability: {escapes!r}"
        )

        for method, field in (
            ("get_system_state", "allowed_state_key_read_prefixes"),
            ("set_system_state", "allowed_state_key_write_prefixes"),
        ):
            prefixes = contract[field]
            calls = accesses[method]
            if method not in contract["allowed_methods"]:
                assert prefixes == [] and calls == [], (
                    f"{relative} uses {method} without being granted the method"
                )
                continue
            for lineno, prefix in calls:
                assert prefix is not None, (
                    f"{relative}:{lineno} uses a system-state key the guard cannot "
                    "bound to a literal prefix"
                )
                assert any(prefix.startswith(allowed) for allowed in prefixes), (
                    f"{relative}:{lineno} uses system-state key prefix {prefix!r}, "
                    f"which is outside its declared prefixes {prefixes!r}"
                )
            unused = [
                allowed
                for allowed in prefixes
                if not any(
                    prefix is not None and prefix.startswith(allowed)
                    for _, prefix in calls
                )
            ]
            assert unused == [], (
                f"{relative} declares unused {method} prefixes {unused!r}"
            )

        prefixes = contract["allowed_state_key_write_prefixes"]
        # No granted prefix may be able to produce a reserved key.
        reachable = sorted(
            key
            for key in reserved
            for prefix in prefixes
            if key.startswith(prefix)
        )
        assert not reachable, (
            f"{relative}'s declared prefixes {prefixes!r} can write "
            f"assistant-reserved state keys {reachable!r}"
        )



def test_strategy_composition_uses_a_narrow_store_contract():
    manifest = _json(OPERATOR_DATABASE_MANIFEST)
    assert manifest["removed_type_only_importers"] == [
        "scripts/product_composition.py"
    ]
    imports = _imported_modules(ROOT / "scripts" / "product_composition.py")
    assert "assistant.storage" not in imports
    assert "assistant.storage_contracts" in imports
    assert isinstance(object.__new__(AssistantStore), StrategyOperationalStore)


def test_research_report_verifier_facade_preserves_object_identity():
    assert legacy_verify_research_report is neutral_verify_research_report


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
