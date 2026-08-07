"""Pin every module-level SCHEMA_VERSION so format drift cannot be silent.

Two conventions coexist: dotted (``"1.0"``) and bare (``"1"``). That split is
NOT normalized here on purpose -- these versions participate in content
addressing, and renumbering ``ml/databento_source.py`` alone would orphan
already-downloaded, paid Databento snapshots on disk (their manifests carry
the current value, and the loader verifies it).

So instead of a cosmetic rename that destroys data, this pins the inventory.
A new module picking a convention by accident, or an existing one being
renumbered without the artifact consequences being considered, fails here and
has to be justified rather than noticed months later.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# module path -> its module-level SCHEMA_VERSION literal.
EXPECTED_SCHEMA_VERSIONS = {
    "assistant/execution_telemetry.py": ("SCHEMA_VERSION", "1.1"),
    "ml/availability.py": ("SCHEMA_VERSION", "1.0"),
    "ml/contracts.py": ("SCHEMA_VERSION", "1.0"),
    "ml/experiment_contracts.py": ("SCHEMA_VERSION", "1.0"),
    "ml/filings.py": ("EXTRACTION_SCHEMA_VERSION", "1.0"),
    "ml/databento_authoritative.py": ("SCHEMA_VERSION", "1"),
    "ml/databento_pit.py": ("PIT_SNAPSHOT_SCHEMA_VERSION", "1"),
    "ml/databento_source.py": ("SNAPSHOT_SCHEMA_VERSION", "2"),
    "ml/prospective.py": ("PROSPECTIVE_SCHEMA_VERSION", "1"),
    "ml/research_orchestration.py": ("ORCHESTRATION_SCHEMA_VERSION", "1"),
    "ml/shadow_runtime.py": ("RUNTIME_SCHEMA_VERSION", "1"),
}

# Renumbering any of these invalidates content-addressed artifacts that may
# already exist on disk, including licensed vendor data that costs money to
# re-download.
ARTIFACT_BEARING = frozenset({
    "ml/databento_authoritative.py",
    "ml/databento_pit.py",
    "ml/databento_source.py",
    "ml/research_orchestration.py",
})


def _module_schema_versions() -> dict[str, str]:
    found: dict[str, str] = {}
    for package in ("assistant", "ml"):
        for path in sorted((REPO_ROOT / package).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                if not isinstance(node, ast.Assign):
                    continue
                for target in node.targets:
                    if (
                        isinstance(target, ast.Name)
                        and "SCHEMA_VERSION" in target.id
                        and isinstance(node.value, ast.Constant)
                        and isinstance(node.value.value, str)
                    ):
                        key = path.relative_to(REPO_ROOT).as_posix()
                        found[key] = (target.id, node.value.value)
    return found


def test_schema_version_inventory_is_pinned():
    actual = _module_schema_versions()

    unexpected = sorted(set(actual) - set(EXPECTED_SCHEMA_VERSIONS))
    assert not unexpected, (
        "new module defines SCHEMA_VERSION without being added to the "
        f"inventory: {unexpected}. Pick a convention deliberately -- dotted "
        "for contract schemas, bare for artifact/source schemas -- then add "
        "it here."
    )

    removed = sorted(set(EXPECTED_SCHEMA_VERSIONS) - set(actual))
    assert not removed, f"module no longer defines SCHEMA_VERSION: {removed}"

    drifted = {
        module: {"expected": EXPECTED_SCHEMA_VERSIONS[module], "actual": actual[module]}
        for module in actual
        if actual[module] != EXPECTED_SCHEMA_VERSIONS[module]
    }
    artifact_drift = {m: v for m, v in drifted.items() if m in ARTIFACT_BEARING}
    assert not artifact_drift, (
        "these schema versions are bound into content-addressed artifacts; "
        "changing one orphans data already written to disk (including paid "
        f"vendor snapshots). Confirm that is intended: {artifact_drift}"
    )
    assert not drifted, f"SCHEMA_VERSION changed without updating the inventory: {drifted}"


def test_each_schema_version_is_a_recognized_format():
    for module, (_name, version) in sorted(_module_schema_versions().items()):
        parts = version.split(".")
        assert all(part.isdigit() for part in parts) and len(parts) in (1, 2), (
            f"{module}: SCHEMA_VERSION {version!r} is neither a bare integer "
            "nor a dotted major.minor"
        )
