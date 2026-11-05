"""Generated quarantine source audit of direct AST forms and exact capabilities.

Claude review section 342 (ARV2R342-001). Section 340's guard read only the 19
shared files and only the import clause. This file reads all 20 files of all six
cells, including each generated Main, and the direct AST predicates of
`newrule_comparison_projection.audit`. It uses only public code and invented
identifiers. It is not cloud evidence and does not clear ARV2R340-002. A new
freeze cannot call `audit` unchanged, because `audit` pins the order capability
to file names this closure does not use.

These lexical checks are not a general dynamic-call or reachability proof.
Computed attribute names, reflection and aliases require separate assessment.
"""
import ast
from collections import Counter

import pytest

from research.analyst_revisions_v2_qc import newrule_comparison_projection as frozen
from tests.analyst_revisions_v2.test_r337_quarantine_projection import prepared  # noqa: F401

PUBLICATION = 'newrule_native_price_book_publication.py'
COMMON_PRICE = 'newrule_five_case_quarantine_common_price.py'
KNOWN_VIOLATIONS = {
    (COMMON_PRICE, 'import', 'subprocess'),  # the open ARV2R340-002 blocker
    (PUBLICATION, 'call', 'save_bytes'),  # no direct static caller found below
}
EXPECTED_CAPABILITIES = {
    'market_order': {'newrule_available_history_comparison_runtime.py': 1,
        'newrule_five_case_quarantine_runtime.py': 1},
    'remove_security': {'newrule_legacy_primitives.py': 1},
    'market_on_open_order': {},
}


def violations(name, raw):
    found = set()
    for node in ast.walk(ast.parse(raw)):
        if isinstance(node, ast.Import):
            found.update((name, 'import', alias.name.split('.')[0]) for alias in node.names
                if alias.name.split('.')[0] in frozen.FORBIDDEN_IMPORTS)
        elif isinstance(node, ast.ImportFrom):
            module = (node.module or '').split('.')[0]
            if module in frozen.FORBIDDEN_IMPORTS:
                found.add((name, 'import', module))
        elif isinstance(node, ast.Call):
            called = node.func.attr if isinstance(node.func, ast.Attribute) else (
                node.func.id if isinstance(node.func, ast.Name) else None)
            if called in frozen.FORBIDDEN_CALLS:
                found.add((name, 'call', called))
        elif isinstance(node, ast.Constant) and node.value in EXPECTED_CAPABILITIES:
            found.add((name, 'dynamic', node.value))
    return found


def capabilities(name, raw):
    attributes = Counter(node.attr for node in ast.walk(ast.parse(raw)) if isinstance(node, ast.Attribute))
    return {(capability, name): attributes[capability] for capability in EXPECTED_CAPABILITIES
        if attributes[capability]}


def assert_capability_inventory(cell):
    seen = Counter()
    for name, raw in cell.items():
        seen.update(capabilities(name, raw))
    expected = {(capability, name): count for capability, files in EXPECTED_CAPABILITIES.items()
        for name, count in files.items()}
    assert dict(seen) == expected


def closures(batch):
    return [dict(cell.source_pairs) for cell in batch.cells]


def test_scan_reports_each_forbidden_form():
    cases = {
        b'import os\n': ('import', 'os'),
        b'import urllib.request\n': ('import', 'urllib'),
        b'from subprocess import run\n': ('import', 'subprocess'),
        b'open("x")\n': ('call', 'open'),
        b'store.save_bytes(1)\n': ('call', 'save_bytes'),
        b'algo.market_on_open_order(1)\n': ('call', 'market_on_open_order'),
        b'getattr(algo, "market_order")\n': ('dynamic', 'market_order'),
    }
    for raw, (kind, what) in cases.items():
        assert violations('x.py', raw) == {('x.py', kind, what)}
    assert violations('x.py', b'import json\nprint(json.dumps({}))\n') == set()
    assert capabilities('x.py', b'algo.market_order(1)\n') == {('market_order', 'x.py'): 1}
    assert capabilities('x.py', b'algo.market_order(1)\nalgo.market_order(2)\n') == {('market_order', 'x.py'): 2}


def test_all_six_cells_hold_twenty_files_with_only_main_differing(prepared):
    cells = closures(prepared[2])
    assert len(cells) == 6 and all(len(cell) == 20 and 'main.py' in cell for cell in cells)
    shared = [{name: raw for name, raw in cell.items() if name != 'main.py'} for cell in cells]
    assert all(files == shared[0] for files in shared)


def test_all_twenty_files_hold_only_the_two_named_violations(prepared):
    found = set()
    for cell in closures(prepared[2]):
        for name, raw in cell.items():
            found |= violations(name, raw)
    assert found == KNOWN_VIOLATIONS


def test_generated_main_of_every_cell_is_clean(prepared):
    for cell in closures(prepared[2]):
        assert violations('main.py', cell['main.py']) == set()


def test_order_capabilities_have_exact_counts_in_the_named_files(prepared):
    for cell in closures(prepared[2]):
        assert_capability_inventory(cell)


@pytest.mark.parametrize('capability,name', [(capability, name)
    for capability, files in EXPECTED_CAPABILITIES.items() for name in files])
def test_duplicate_capability_in_an_already_allowed_file_refuses(prepared, capability, name):
    cell = closures(prepared[2])[0]
    assert_capability_inventory(cell)
    changed = dict(cell)
    changed[name] += ('\nalgorithm.' + capability + '(None)\n').encode('ascii')
    assert capabilities(name, changed[name])[(capability, name)] == 2
    with pytest.raises(AssertionError):
        assert_capability_inventory(changed)


def test_no_direct_static_reference_to_the_object_store_publisher(prepared):
    # `save_bytes` sits in SpecificSourceBookNamespace.publish. No direct name,
    # attribute, import alias or matching literal is found by this scanner.
    # This is not proof against computed names, reflection or dynamic aliases.
    cell = closures(prepared[2])[0]
    tree = ast.parse(cell[PUBLICATION])
    owners = [node.name for node in tree.body if isinstance(node, ast.ClassDef)
        and any(isinstance(item, ast.FunctionDef) and item.name == 'publish' for item in node.body)]
    assert owners == ['SpecificSourceBookNamespace']
    assert reachable_publisher_references(PUBLICATION, cell[PUBLICATION], owners[0], own_module=True) == []
    for current in closures(prepared[2]):
        for name, raw in current.items():
            if name != PUBLICATION:
                assert reachable_publisher_references(name, raw, owners[0]) == [], name


def reachable_publisher_references(name, raw, owner, own_module=False):
    words = {'publish'} if own_module else {'publish', owner}
    found = []
    for node in ast.walk(ast.parse(raw)):
        if ((isinstance(node, ast.Attribute) and node.attr in words)
                or (isinstance(node, ast.Name) and node.id in words)
                or (isinstance(node, ast.alias) and node.name in words)
                or (isinstance(node, ast.Constant) and node.value in words)):
            found.append(name)
    return found
