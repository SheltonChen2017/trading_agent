"""Detect same-named validators drifting apart inside ml/.

Audit finding, 2026-08-02: eleven private helpers were defined 3-4 times
across ``ml/``, and NONE of the families were structurally identical.
``_sha256`` is the clearest case -- three implementations with three
different accept-sets:

    ml/databento_authoritative.py   isinstance(value, str) required
    ml/research_orchestration.py    routed through _text()
    ml/shadow_runtime.py            routed through _required_text()

That is not copy-paste duplication, which is merely untidy. It is one
safety rule -- "this must be a SHA-256 digest", the guard on artifact
identity -- enforced at three different strictnesses. CLAUDE.md section 8
asks for such a rule to be consolidated "so the rule cannot drift"; it
already drifted.

Resolving each family means deciding which strictness is correct, and that
decision changes what evidence is accepted, so it is deliberately NOT done
mechanically here. This test pins the known families instead: a new copy,
or a new divergent family, fails and has to be justified.
"""
from __future__ import annotations

import ast
import collections
import hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Families that already exist and are accepted for now, with the number of
# distinct implementations each currently has. Shrinking a count is always
# fine; growing one, or adding a family, must be deliberate.
KNOWN_DIVERGENT_FAMILIES = {
    # >=3 copies
    "_timestamp": 4,
    "_parse_session": 4,
    "_parse_instant": 3,
    "_sha256": 3,
    "_check_schema_version": 3,
    "_canonical_session": 3,
    "_required_text": 3,
    # 2 copies, each with 2 distinct implementations
    "_atomic_write_bytes": 2,   # artifacts.py sanitizes the filename; datasets.py does not
    "_check_required_str": 2,
    "_check_sha256": 2,
    "_parse_timestamp": 2,
    "_aware_timestamp": 2,
    "_slice_metrics": 2,
    "_instant": 2,
    "_plain": 2,
    "_finite": 2,
    "_text": 2,
}


def _families() -> dict[str, dict[str, list[str]]]:
    """name -> {body-hash: [modules]} for every top-level ml/ helper."""
    seen: dict[str, dict[str, list[str]]] = collections.defaultdict(
        lambda: collections.defaultdict(list)
    )
    for path in sorted((REPO_ROOT / "ml").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            body = ast.dump(ast.Module(body=node.body, type_ignores=[]))
            digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]
            seen[node.name][digest].append(path.relative_to(REPO_ROOT).as_posix())
    return {name: dict(variants) for name, variants in seen.items()}


def test_no_new_helper_family_is_duplicated_across_ml_modules():
    families = _families()
    offenders = {}
    for name, variants in families.items():
        copies = sum(len(modules) for modules in variants.values())
        if copies < 2:
            continue
        allowed = KNOWN_DIVERGENT_FAMILIES.get(name, 1)
        if copies > allowed:
            offenders[name] = {
                "copies": copies,
                "allowed": allowed,
                "distinct_implementations": len(variants),
                "modules": sorted(m for ms in variants.values() for m in ms),
            }
    assert not offenders, (
        "a helper is now defined in more modules than the audit recorded. "
        "Import the existing one instead of adding a copy -- every family "
        "that was duplicated in this codebase also diverged: " + repr(offenders)
    )


def test_recorded_families_have_not_grown_more_variants():
    families = _families()
    grown = {}
    for name, allowed in KNOWN_DIVERGENT_FAMILIES.items():
        variants = families.get(name)
        if not variants:
            continue
        copies = sum(len(modules) for modules in variants.values())
        if copies > allowed:
            grown[name] = {"copies": copies, "allowed": allowed}
    assert not grown, f"known divergent families grew: {grown}"
