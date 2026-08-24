"""Validate the reviewed SEP-3 extraction dry run without moving a file.

The validator reads one exact Git commit, classifies every tracked path once,
and fails closed on inventory drift, shared-package expansion, authority or
licensed-data leakage, unsafe import forms, path collisions, or stale residual
counts. It never writes another repository and never reads provider data.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "architecture" / "sep3_extraction_manifest.json"
DESTINATIONS = {"trading_assistant", "strategy_research", "shared_contracts"}


class ExtractionValidationError(RuntimeError):
    """The dry-run extraction contract is incomplete or unsafe."""


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=False
    )
    if result.returncode:
        raise ExtractionValidationError(result.stderr.strip() or "git command failed")
    return result.stdout


def _commit_text(commit: str, path: str) -> str:
    return _git("show", f"{commit}:{path}")


def _commit_json(commit: str, path: str) -> dict[str, Any]:
    return json.loads(_commit_text(commit, path))


def _module_roots(source: str, path: str, *, enforce_static: bool = True) -> set[str]:
    tree = ast.parse(source, filename=path)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level and enforce_static:
                raise ExtractionValidationError(
                    f"relative import is not extraction-safe: {path}:{node.lineno}"
                )
            if node.module:
                roots.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            function = node.func
            if enforce_static and isinstance(function, ast.Name) and function.id in {"__import__", "exec"}:
                raise ExtractionValidationError(
                    f"dynamic code/import is not extraction-safe: {path}:{node.lineno}"
                )
            if (
                enforce_static
                and isinstance(function, ast.Attribute)
                and isinstance(function.value, ast.Name)
                and function.value.id == "importlib"
                and function.attr == "import_module"
            ):
                raise ExtractionValidationError(
                    f"dynamic import is not extraction-safe: {path}:{node.lineno}"
                )
    return roots


def _imported_modules(source: str, path: str) -> set[str]:
    """Return full static import names, expanding ``from parent import child``.

    Root-only scanning cannot distinguish the three shared ``data`` contracts
    from product-owned ``data`` implementations. The support partition needs
    the full names so research provider tests cannot leak into the tiny shared
    package merely because both begin with ``data``.
    """
    tree = ast.parse(source, filename=path)
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


def _inventory(commit: str) -> list[str]:
    paths = _git("ls-tree", "-r", "--name-only", commit).splitlines()
    if paths != sorted(paths):
        raise ExtractionValidationError("Git tree inventory is not stably ordered")
    return paths


def _inventory_sha256(paths: list[str]) -> str:
    return hashlib.sha256(("\n".join(paths) + "\n").encode("utf-8")).hexdigest()


def _starts_with_root(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def _classify(
    path: str,
    manifest: dict[str, Any],
    entry_points: dict[str, Any],
    test_destinations: dict[str, str],
) -> tuple[str, str]:
    matches: list[tuple[str, str]] = []
    shared = manifest["shared_contracts"]["source_to_package"]
    if path in shared:
        matches.append(("shared_contracts", "shared allowlist"))

    for destination, roots in manifest["product_roots"].items():
        for root in roots:
            if _starts_with_root(path, root):
                matches.append((destination, f"owned root {root}"))
    for destination, files in manifest["product_top_level_files"].items():
        if path in files:
            matches.append((destination, "owned top-level file"))
    for destination, files in manifest["data_destination"].items():
        if path in files:
            matches.append((destination, "data ownership decision"))

    scripts = entry_points["script_ownership"]
    if path in scripts["trading_assistant"]:
        matches.append(("trading_assistant", "entry-point ownership"))
    elif path in scripts["strategy_research"]:
        matches.append(("strategy_research", "entry-point ownership"))
    elif path in scripts["cross_product_composition"]:
        host = entry_points["composition_hosts"][path]
        destination = (
            "strategy_research" if host == "strategy_research" else "trading_assistant"
        )
        matches.append((destination, f"composition host {host}"))

    support = manifest["support_paths"]
    if path in test_destinations:
        matches.append((test_destinations[path], "pinned test partition"))
    elif path in support["exact_files"] or any(
        path.startswith(prefix) for prefix in support["prefixes"]
    ):
        matches.append((support["destination"], "migration support"))
    if path == "data/__init__.py":
        matches.append((support["destination"], "source package marker"))

    if len(matches) != 1:
        raise ExtractionValidationError(
            f"{path} must have exactly one destination, got {matches!r}"
        )
    return matches[0]


def _partition_tests(
    paths: list[str],
    commit: str,
    manifest: dict[str, Any],
    entry_points: dict[str, Any],
) -> dict[str, list[str]]:
    """Classify Python tests by the product roots they exercise.

    Product-pure tests follow their product. Tests that exercise both products
    stay with the source/trading-assistant repository as explicit integration
    debt until the physical extraction is separately authorized. A test that
    exercises only the tiny shared contracts follows that package. Tests that
    load source dynamically or inspect repository text may receive an exact
    reviewed ownership override only while their static product-import set is
    empty; a later product import makes the override fail closed.
    """
    surfaces = {
        "trading_assistant": [],
        "strategy_research": [],
        "shared_contracts": [],
        "integration": [],
    }
    explicit = manifest["support_partition"].get("explicit_test_ownership")
    explicit_by_path: dict[str, str] = {}
    if explicit is not None:
        expected_buckets = {
            "trading_assistant",
            "strategy_research",
            "governance",
        }
        if set(explicit) != expected_buckets:
            raise ExtractionValidationError(
                "explicit test ownership must declare assistant, research, "
                "and governance buckets"
            )
        surfaces["governance"] = []
        for bucket, declared in explicit.items():
            for path in declared:
                if path in explicit_by_path:
                    raise ExtractionValidationError(
                        f"duplicate explicit test ownership: {path}"
                    )
                if not path.startswith("tests/") or not path.endswith(".py"):
                    raise ExtractionValidationError(
                        f"explicit test ownership is not a Python test: {path}"
                    )
                explicit_by_path[path] = bucket
    owned_modules: dict[str, set[str]] = {}

    def own(module: str, *destinations: str) -> None:
        owned_modules.setdefault(module, set()).update(destinations)

    for destination, roots in manifest["product_roots"].items():
        for root in roots:
            own(root.replace("/", "."), destination)
    for destination, files in manifest["product_top_level_files"].items():
        for path in files:
            own(path.removesuffix(".py").replace("/", "."), destination)
    for destination, files in manifest["data_destination"].items():
        for path in files:
            own(path.removesuffix(".py").replace("/", "."), destination)
    for path in manifest["shared_contracts"]["source_to_package"]:
        own(path.removesuffix(".py").replace("/", "."), "shared_contracts")
    ownership = entry_points["script_ownership"]
    for path in ownership["trading_assistant"]:
        own(path.removesuffix(".py").replace("/", "."), "trading_assistant")
    for path in ownership["strategy_research"]:
        own(path.removesuffix(".py").replace("/", "."), "strategy_research")
    for path in ownership["cross_product_composition"]:
        own(
            path.removesuffix(".py").replace("/", "."),
            "trading_assistant",
            "strategy_research",
        )

    for path in paths:
        if not path.startswith("tests/") or not path.endswith(".py"):
            continue
        modules = _imported_modules(_commit_text(commit, path), path)
        destinations: set[str] = set()
        for module in modules:
            for owned_module, owners in owned_modules.items():
                if module == owned_module or module.startswith(owned_module + "."):
                    destinations.update(owners)
        explicit_bucket = explicit_by_path.get(path)
        if explicit_bucket is not None:
            if destinations:
                raise ExtractionValidationError(
                    "explicit test ownership cannot override statically measured "
                    f"product imports: {path} -> {sorted(destinations)!r}"
                )
            bucket = explicit_bucket
        elif destinations == {"trading_assistant"}:
            bucket = "trading_assistant"
        elif destinations == {"strategy_research"}:
            bucket = "strategy_research"
        elif destinations == {"shared_contracts"}:
            bucket = "shared_contracts"
        else:
            bucket = "integration"
        surfaces[bucket].append(path)
    missing = sorted(set(explicit_by_path) - set(paths))
    if missing:
        raise ExtractionValidationError(
            f"stale explicit test ownership paths: {missing!r}"
        )
    return surfaces


def _data_module_importers(
    paths: list[str],
    commit: str,
    manifest: dict[str, Any],
    entry_points: dict[str, Any],
) -> dict[str, dict[str, list[str]]]:
    """Return exact product-side importers for every assigned data module.

    CRSEP3R2-001: the independent review correctly found the stranded module
    set, but its supporting claim mixed two importer scopes. Pinning both
    sides prevents a future partition decision from treating a dual-use
    module as a simple ownership reassignment. Later tranches may shrink this
    set only by changing the measured import graph or product destination.
    """
    assigned_modules = {
        path.removesuffix(".py").replace("/", ".")
        for files in manifest["data_destination"].values()
        for path in files
    }
    ownership = entry_points["script_ownership"]
    side_prefixes = {
        side: list(manifest["product_roots"][side])
        + list(manifest["product_top_level_files"][side])
        + [path for path in ownership[side] if path.endswith(".py")]
        for side in ("trading_assistant", "strategy_research")
    }

    importers: dict[str, dict[str, set[str]]] = {}
    for side, prefixes in side_prefixes.items():
        for path in paths:
            if not path.endswith(".py"):
                continue
            if not any(_starts_with_root(path, prefix) for prefix in prefixes):
                continue
            for imported in _imported_modules(_commit_text(commit, path), path):
                module = ".".join(imported.split(".")[:2])
                if module in assigned_modules:
                    importers.setdefault(module, {}).setdefault(side, set()).add(path)
    return {
        module: {
            side: sorted(files) for side, files in sorted(sides.items())
        }
        for module, sides in sorted(importers.items())
    }


def _stranded_data_modules(
    manifest: dict[str, Any],
    importers: dict[str, dict[str, list[str]]],
) -> dict[str, list[str]]:
    """Data modules destined to one product while the other still imports them.

    SEP3R-001 found ten such modules in the first two dry runs. Subsequent
    bounded tranches resolve only ownership decisions proven by the candidate
    graph. A dry run exists to surface the remaining set, so it is measured
    from the candidate commit, must match the declared blocker exactly, and
    keeps the run non-extraction-ready while non-empty.
    """
    destination: dict[str, str] = {}
    for product, files in manifest["data_destination"].items():
        for path in files:
            destination[path.removesuffix(".py").replace("/", ".")] = product
    stranded: dict[str, list[str]] = {}
    for module, sides in importers.items():
        wrong_side_files = sorted(
            path
            for side, files in sides.items()
            if side != destination[module]
            for path in files
        )
        if wrong_side_files:
            stranded[module] = wrong_side_files
    return stranded


def validate(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["schema_version"] != 2:
        raise ExtractionValidationError("unsupported extraction schema")
    if manifest["physical_extraction_authorized"] is not False:
        raise ExtractionValidationError("this tranche cannot authorize a physical move")
    if manifest["owner_topology_decision"]["git_submodules"] is not False:
        raise ExtractionValidationError("Git submodules are not an approved topology")

    source = manifest["source"]
    if source["independent_review_status"] != "pending":
        raise ExtractionValidationError(
            "this implementation tranche must remain pending independent review"
        )
    commit = source["candidate_commit"]
    if _git("cat-file", "-t", commit).strip() != "commit":
        raise ExtractionValidationError("reviewed source is not a commit")
    paths = _inventory(commit)
    if len(paths) != manifest["source"]["tracked_path_count"]:
        raise ExtractionValidationError("reviewed source path count changed")
    if _inventory_sha256(paths) != manifest["source"]["tracked_path_inventory_sha256"]:
        raise ExtractionValidationError("reviewed source inventory hash changed")

    entry_points = _commit_json(commit, manifest["script_ownership_source"])
    boundaries = _commit_json(commit, "architecture/project_boundaries.json")
    operator = _commit_json(commit, "architecture/operator_database_access.json")
    test_surfaces = _partition_tests(paths, commit, manifest, entry_points)
    support_partition = manifest["support_partition"]
    expected_counts = support_partition["test_counts"]
    actual_counts = {name: len(items) for name, items in test_surfaces.items()}
    expected_hashes = support_partition["test_inventory_sha256"]
    actual_hashes = {
        name: _inventory_sha256(items) for name, items in test_surfaces.items()
    }
    integration = test_surfaces["integration"]
    if support_partition["integration_destination"] != "trading_assistant":
        raise ExtractionValidationError(
            "integration tests must remain in the source repository until extraction"
        )
    bucket_destinations = {
        "trading_assistant": "trading_assistant",
        "strategy_research": "strategy_research",
        "shared_contracts": "shared_contracts",
        "integration": support_partition["integration_destination"],
    }
    governance = test_surfaces.get("governance", [])
    if governance:
        if support_partition.get("governance_destination") != manifest[
            "support_paths"
        ]["destination"]:
            raise ExtractionValidationError(
                "governance tests must remain with migration support in the "
                "source repository"
            )
        bucket_destinations["governance"] = support_partition[
            "governance_destination"
        ]
    test_destinations = {
        path: bucket_destinations[bucket]
        for bucket, items in test_surfaces.items()
        for path in items
    }
    assignments: dict[str, str] = {}
    reasons: dict[str, str] = {}
    targets: dict[tuple[str, str], str] = {}
    shared_map = manifest["shared_contracts"]["source_to_package"]
    for path in paths:
        destination, reason = _classify(
            path, manifest, entry_points, test_destinations
        )
        if destination not in DESTINATIONS:
            raise ExtractionValidationError(f"unknown destination for {path}")
        target = shared_map[path] if path in shared_map else path
        key = (destination, target.casefold())
        if key in targets:
            raise ExtractionValidationError(
                f"target collision: {targets[key]} and {path} -> {destination}/{target}"
            )
        targets[key] = path
        assignments[path] = destination
        reasons[path] = reason

    shared = manifest["shared_contracts"]
    if set(shared["source_blob_ids"]) != set(shared_map):
        raise ExtractionValidationError("every shared source needs an exact blob pin")
    forbidden = set(shared["forbidden_import_roots"])
    allowed_third_party = set(shared["allowed_third_party_imports"])
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    for path, expected_blob in shared["source_blob_ids"].items():
        actual_blob = _git("rev-parse", f"{commit}:{path}").strip()
        if actual_blob != expected_blob:
            raise ExtractionValidationError(f"shared contract blob drift: {path}")
        roots = _module_roots(_commit_text(commit, path), path)
        unsafe = roots & forbidden
        unknown = roots - stdlib - allowed_third_party
        if unsafe or unknown:
            raise ExtractionValidationError(
                f"shared contract import leakage in {path}: "
                f"forbidden={sorted(unsafe)!r}, unknown={sorted(unknown)!r}"
            )

    for root in boundaries["authority_roots"]:
        path = root.replace(".", "/") + ".py"
        package = root.replace(".", "/")
        candidates = [p for p in paths if p == path or _starts_with_root(p, package)]
        if not candidates or any(assignments[p] != "trading_assistant" for p in candidates):
            raise ExtractionValidationError(f"authority root escaped assistant: {root}")
    for surface in entry_points["licensed_research_surfaces"]:
        candidates = [p for p in paths if _starts_with_root(p, surface)]
        if not candidates or any(assignments[p] != "strategy_research" for p in candidates):
            raise ExtractionValidationError(f"licensed surface escaped research: {surface}")

    # Check the support partition after the primary authority/licensed-data
    # invariants so their dangerous-direction tests continue to prove the
    # intended boundary rather than failing incidentally on a derived test
    # bucket. Partition drift remains fail-closed on an otherwise valid tree.
    if actual_counts != expected_counts or actual_hashes != expected_hashes:
        raise ExtractionValidationError(
            "test support partition drifted: "
            f"counts={actual_counts!r}, hashes={actual_hashes!r}"
        )
    if support_partition["integration_test_files"] != len(integration):
        raise ExtractionValidationError("stale integration-test blocker count")
    if support_partition.get("governance_test_files", 0) != len(governance):
        raise ExtractionValidationError("stale governance-test partition count")
    shared_contract_tests = test_surfaces["shared_contracts"]
    if support_partition["shared_contract_test_files"] != len(shared_contract_tests):
        raise ExtractionValidationError("stale shared-contract test count")
    if (
        not shared_contract_tests
        or support_partition["shared_contract_test_status"]
        != "pinned-dedicated-package-tests"
    ):
        raise ExtractionValidationError(
            "the shared package requires a pinned dedicated test surface"
        )

    blockers = manifest["known_blockers"]
    measured = {
        "composition_files": len(entry_points["script_ownership"]["cross_product_composition"]),
        "python_crossing_roots": len(entry_points["declared_python_cross_product_roots"]),
        "operator_database_importers": len(operator["direct_non_assistant_importers"]),
    }
    for name, value in measured.items():
        if blockers[name] != value:
            raise ExtractionValidationError(
                f"stale extraction blocker {name}: declared={blockers[name]}, measured={value}"
            )

    data_importers = _data_module_importers(paths, commit, manifest, entry_points)
    stranded = _stranded_data_modules(manifest, data_importers)
    declared_stranded = blockers["stranded_data_modules"]
    if sorted(declared_stranded) != sorted(stranded):
        raise ExtractionValidationError(
            "stale extraction blocker stranded_data_modules: "
            f"declared={sorted(declared_stranded)}, measured={sorted(stranded)}"
        )

    declared_importer_sides = blockers["stranded_data_module_importer_sides"]
    measured_importer_sides = {
        module: sorted(sides)
        for module, sides in data_importers.items()
        if module in stranded
    }
    if declared_importer_sides != measured_importer_sides:
        raise ExtractionValidationError(
            "stale extraction blocker stranded_data_module_importer_sides: "
            f"declared={declared_importer_sides}, measured={measured_importer_sides}"
        )

    ownership_counts = {
        name: len(entry_points["script_ownership"][name])
        for name in ("trading_assistant", "strategy_research", "cross_product_composition")
    }
    helpers = set(entry_points["non_launch_helpers"])
    launch_counts = {
        name: len(set(entry_points["script_ownership"][name]) - helpers)
        for name in ("trading_assistant", "strategy_research", "cross_product_composition")
    }
    destination_counts = {
        destination: sum(value == destination for value in assignments.values())
        for destination in sorted(DESTINATIONS)
    }
    return {
        "schema_version": 2,
        "status": f"valid-{manifest['status']}",
        "source_commit": commit,
        "inventory": {
            "tracked_paths": len(paths),
            "sha256": _inventory_sha256(paths),
            "assigned_exactly_once": True,
            "destination_counts": destination_counts,
        },
        "surfaces": {
            "script_ownership_counts": ownership_counts,
            "launch_counts": launch_counts,
            "dependency_manifests": manifest["dependency_surfaces"],
            "test_counts": actual_counts,
            "test_inventory_sha256": actual_hashes,
            "shared_contract_test_files": len(shared_contract_tests),
            "governance_test_files": len(governance),
        },
        "blockers": measured | {
            "support_surface_partition": blockers["support_surface_partition"],
            "integration_test_files": len(integration),
            "governance_support_partition": blockers[
                "governance_support_partition"
            ],
            "stranded_data_modules": sorted(stranded),
            "stranded_data_module_importer_sides": measured_importer_sides,
        },
        "physical_extraction_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    try:
        result = validate(args.manifest)
    except (ExtractionValidationError, json.JSONDecodeError, OSError) as exc:
        print(f"REFUSED|{exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
