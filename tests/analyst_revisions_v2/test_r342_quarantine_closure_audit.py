"""Every generated quarantine source against every clause of the lane's cloud audit.

Claude review section 342 (ARV2R342-001). Section 340's guard read only the 19
shared files and only the import clause. This file reads all 20 files of all six
cells, including each generated Main, and every clause of
`newrule_comparison_projection.audit`. It uses only public code and invented
identifiers. It is not cloud evidence and does not clear ARV2R340-002. A new
freeze cannot call `audit` unchanged, because `audit` pins the order capability
to file names this closure does not use.
"""
import ast

import pytest

from research.analyst_revisions_v2_qc import newrule_comparison_projection as frozen
from tests.analyst_revisions_v2.test_r337_quarantine_projection import prepared  # noqa: F401

PUBLICATION = 'newrule_native_price_book_publication.py'
COMMON_PRICE = 'newrule_five_case_quarantine_common_price.py'
KNOWN_VIOLATIONS = {
    (COMMON_PRICE, 'import', 'subprocess'),  # the open ARV2R340-002 blocker
    (PUBLICATION, 'call', 'save_bytes'),  # no caller: see the publisher test below
}
EXPECTED_CAPABILITIES = {
    'market_order': {'newrule_available_history_comparison_runtime.py', 'newrule_five_case_quarantine_runtime.py'},
    'remove_security': {'newrule_legacy_primitives.py'},
    'market_on_open_order': set(),
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
    attributes = {node.attr for node in ast.walk(ast.parse(raw)) if isinstance(node, ast.Attribute)}
    return {(capability, name) for capability in EXPECTED_CAPABILITIES if capability in attributes}


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
    assert capabilities('x.py', b'algo.market_order(1)\n') == {('market_order', 'x.py')}


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


def test_order_capabilities_sit_only_in_the_named_files(prepared):
    for cell in closures(prepared[2]):
        seen = set()
        for name, raw in cell.items():
            seen |= capabilities(name, raw)
        assert seen == {(capability, name) for capability, names in EXPECTED_CAPABILITIES.items() for name in names}


def test_no_generated_file_reaches_the_object_store_publisher(prepared):
    # `save_bytes` sits in SpecificSourceBookNamespace.publish. A closure with no
    # reference to that class or to `publish` in any form cannot call it.
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
