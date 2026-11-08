"""Claude review section 349: guards for two defects found in sections 345-348.

ARV2R349-001. The spent R348 result reader journals 'known-A4-status', but its
own Store accepts only lowercase markers, so D1 refused 'output' on every
status and could never have read a result. Its tests used a fake Store that
skipped the marker check. A static scan now checks every literal marker in
these callers and engines against the pattern its receiver enforces. The spent
reader is held as a strict expected failure.

ARV2R349-002. The spent v3 same-project recovery deletes research.ipynb
without checking that it is the untouched default notebook. A strict expected
failure holds that in place. Successors must refuse an edited notebook.

Public code and synthetic values only. No spent file is edited.
"""
import ast
import re
from pathlib import Path

import pytest

from scripts import arv2_r345_legacy_six_qc_v3 as v3
from tests.analyst_revisions_v2.test_r345_legacy_six_qc_v3 import fake, runner  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
READER = 'scripts/read_arv2_r348_ar100_result.py'
CALLERS = ('scripts/run_arv2_r348_remaining_six.py', 'scripts/run_arv2_r347_legacy_six_a4.py',
           'scripts/run_arv2_r345_legacy_six_v3.py')
ENGINES = ('scripts/arv2_r345_legacy_six_qc.py', 'scripts/arv2_r345_legacy_six_qc_v2.py',
           'scripts/arv2_r345_legacy_six_qc_v3.py', 'scripts/arv2_r347_legacy_six_qc.py',
           'scripts/arv2_r348_legacy_six_qc.py')
CALLER_JOURNAL = '[a-z0-9-]{1,120}'


def receiver_pattern(tree, method):
    for function in ast.walk(tree):
        if isinstance(function, ast.FunctionDef) and function.name == method:
            for node in ast.walk(function):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == 'fullmatch' and node.args
                        and isinstance(node.args[0], ast.Constant)):
                    return node.args[0].value
    return None


def sample(node):
    """Inspect static text; use '0' only for unresolved runtime expressions.

    Dynamic values and their lengths are not proved by this representative
    scan. Unsupported static formatting refuses inspection rather than being
    replaced with a value which could conceal an invalid literal marker.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return ''.join(sample(part) for part in node.values)
    if isinstance(node, ast.FormattedValue):
        if isinstance(node.value, ast.Constant):
            value = node.value.value
        else:
            value = sample(node.value)
            if value is None:
                dynamic = (ast.Name, ast.Call, ast.Attribute, ast.Subscript)
                return '0' if any(isinstance(part, dynamic) for part in ast.walk(node.value)) \
                    else '<unsupported-static>'
        if node.conversion == ord('r'):
            value = repr(value)
        elif node.conversion == ord('a'):
            value = ascii(value)
        elif node.conversion == ord('s'):
            value = str(value)
        spec = '' if node.format_spec is None else sample(node.format_spec)
        assert spec is not None and len(spec) <= 64
        assert all(int(width) <= 1024 for width in re.findall(r'\d+', spec))
        try:
            return format(value, spec)
        except (TypeError, ValueError):
            return '<unsupported-static>'
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = sample(node.left), sample(node.right)
        def component(value, expression):
            if value is not None:
                return value
            dynamic = (ast.Name, ast.Call, ast.Attribute, ast.Subscript)
            return '0' if any(isinstance(part, dynamic) for part in ast.walk(expression)) \
                else '<unsupported-static>'
        return None if left is None and right is None else component(left, node.left) + component(right, node.right)
    return None


def markers(tree, method):
    """Scan the named methods and their current free-function equivalents.

    These exact path lists and representative dynamic expressions are a
    snapshot guard, not exhaustive validation of future callers or lengths.
    """
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        position = None
        if isinstance(node.func, ast.Attribute) and node.func.attr == method:
            position = 0
        elif isinstance(node.func, ast.Name):
            if method == '_call' and node.func.id == '_read_call':
                position = 2
            elif method == '_event' and node.func.id == '_event':
                position = 1
        if position is not None and len(node.args) > position:
            value = sample(node.args[position])
            if value is not None:
                found.append(value)
    return found


def rejected(path, method, pattern=None):
    tree = ast.parse((ROOT / path).read_text(encoding='utf-8'))
    pattern = pattern or receiver_pattern(tree, method)
    assert pattern, (path, method)
    values = markers(tree, method)
    assert values, (path, method)
    return [value for value in values if re.fullmatch(pattern, value) is None]


def test_scan_reads_each_marker_form_and_flags_uppercase():
    tree = ast.parse("s.journal('ok-1', 1)\ns.journal(f'objects-{i}-intent', 1)\n"
                     "s.journal('stat-' + str(i), 1)\ns.journal('known-A4-status', 1)\n")
    assert markers(tree, 'journal') == ['ok-1', 'objects-0-intent', 'stat-0', 'known-A4-status']
    assert [value for value in markers(tree, 'journal') if not re.fullmatch(CALLER_JOURNAL, value)] \
        == ['known-A4-status']


def test_scan_includes_free_read_call_and_event_marker_positions():
    tree = ast.parse("_read_call(request, journal, 'BAD-read', 'authenticate', {})\n"
                     "_event(journal, 'BAD-event', {})\n"
                     "_read_call(request, journal, 'lower-read', 'authenticate', {})\n"
                     "_event(journal, 'lower-event', {})\n")
    assert markers(tree, '_call') == ['BAD-read', 'lower-read']
    assert markers(tree, '_event') == ['BAD-event', 'lower-event']
    assert [value for value in markers(tree, '_call') if not re.fullmatch(CALLER_JOURNAL, value)] \
        == ['BAD-read']
    assert [value for value in markers(tree, '_event') if not re.fullmatch(CALLER_JOURNAL, value)] \
        == ['BAD-event']


def test_scan_recursively_renders_static_formatted_text_instead_of_zero():
    tree = ast.parse('s.journal(f"{\'BAD\'}-status", 1)\n'
                     's.journal(f"{\'BAD\' + \'-constant\'}", 1)\n'
                     's.journal(f"{f\'BAD\'}-nested", 1)\n'
                     's.journal(f"{2:02d}-lower", 1)\n'
                     's.journal(f"{dynamic}-lower", 1)\n')
    values = markers(tree, 'journal')
    assert values == ['BAD-status', 'BAD-constant', 'BAD-nested', '02-lower', '0-lower']
    assert [value for value in values if not re.fullmatch(CALLER_JOURNAL, value)] \
        == ['BAD-status', 'BAD-constant', 'BAD-nested']


@pytest.mark.parametrize('path', CALLERS)
def test_callers_journal_only_markers_their_store_accepts(path):
    assert rejected(path, 'journal') == []


@pytest.mark.parametrize('path', ENGINES)
def test_engines_call_and_event_markers_fit_their_receivers(path):
    assert rejected(path, '_call') == []
    assert rejected(path, '_event', CALLER_JOURNAL) == []


def test_spent_reader_store_enforces_the_lowercase_pattern():
    tree = ast.parse((ROOT / READER).read_text(encoding='utf-8'))
    assert receiver_pattern(tree, 'journal') == CALLER_JOURNAL
    assert 'known-A4-status' in markers(tree, 'journal')


@pytest.mark.xfail(strict=True, raises=AssertionError,
    reason='ARV2R349-001 / I348-001: the spent D1 reader journals an uppercase marker its Store refuses')
def test_spent_reader_journals_only_markers_its_store_accepts():
    assert rejected(READER, 'journal') == []


def test_default_notebook_is_the_only_file_the_v3_recovery_deletes(fake):
    runner(fake).begin_once()
    assert [payload['name'] for name, payload in fake.calls if name == 'files/delete'] == ['research.ipynb']


@pytest.mark.xfail(strict=True, raises=AssertionError,
    reason='ARV2R349-002: v3 deletes research.ipynb without checking that it is the default notebook')
def test_edited_notebook_is_never_deleted(fake):
    fake.files['research.ipynb'] = '{"cells": [{"source": "synthetic user edit"}]}'
    try:
        runner(fake).begin_once()
    except v3.Refused:
        pass
    assert not any(name == 'files/delete' for name, _ in fake.calls)
