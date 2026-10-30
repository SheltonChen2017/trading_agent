"""Guard the three redacted passages without keeping identifier fingerprints.

Double hashing a low-entropy value still permits dictionary comparison. These
checks instead bind public replacement text within the three relevant passages.
They are not a whole-record privacy scanner; Git history remains unchanged.
"""
import ast
from pathlib import Path

import pytest


RECORD = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2/docs/Strategy Description/'
    'ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md')

# All anchors and replacements are public prose, not fingerprints or recovered
# values. Keep each start/end pair scoped to its original historical section.
PASSAGES = (
    (
        '323.25', '323.26',
        'Current authenticated Safari project38364439 panel separately showed exactly\n',
        ' This is label evidence,\n',
        "the owner's account(Owner; display name withheld in section330), "
        'Codex ARV2 R298 A5 20261024 andMia.',
    ),
    (
        '323.41', '323.42',
        'one CUSIP candidate, clipped reference/decision interval relations INSIDE.\n',
        '\nNo raw dates,',
        'Raw-date hashes (first, last) are withheld in section330: a plain SHA-256 of\n'
        'a calendar date is reversible by dictionary (ARV2R328-006).',
    ),
    (
        '323.60', '323.61',
        'matched and SID.Date related before_reference. ',
        '\nInitial metadata SHA',
        'SID, display and\n'
        'SID.Date SHA values are withheld in section330 as reversible low-entropy\n'
        'fingerprints (ARV2R328-006).',
    ),
)


def _assert_redacted_passage(text, spec):
    first, next_section, start, end, replacement = spec
    heading = '### ' + first + ' '
    following = '### ' + next_section + ' '
    assert text.count(heading) == text.count(following) == 1
    section = text.split(heading, 1)[1].split(following, 1)[0]
    assert section.count(start) == section.count(end) == 1
    passage = section.split(start, 1)[1].split(end, 1)[0]
    # Avoid pytest assertion introspection of a reintroduced value.
    if passage != replacement:
        raise AssertionError('redacted passage differs from public replacement')


def _synthetic_record(spec, passage):
    first, next_section, start, end, _ = spec
    return ('### ' + first + ' synthetic\n' + start + passage + end + '\n'
            '### ' + next_section + ' synthetic\n')


@pytest.mark.parametrize('spec', PASSAGES, ids=('owner-role', 'raw-date', 'sid'))
def test_historical_passage_contains_only_its_public_replacement(spec):
    _assert_redacted_passage(RECORD.read_text(encoding='utf-8'), spec)


@pytest.mark.parametrize('spec', PASSAGES, ids=('owner-role', 'raw-date', 'sid'))
def test_public_replacement_is_accepted_without_secret_fingerprints(spec):
    _assert_redacted_passage(_synthetic_record(spec, spec[-1]), spec)


@pytest.mark.parametrize('spec', PASSAGES, ids=('owner-role', 'raw-date', 'sid'))
@pytest.mark.parametrize('shape', ('prepend', 'append', 'replace'))
def test_synthetic_reintroduction_refuses_even_when_marker_survives(spec, shape):
    replacement = spec[-1]
    # Deliberately invented data; never a withheld value or its fingerprint.
    injected = 'Synthetic Person ' + 'A' * 64
    mutated = {
        'prepend': injected + replacement,
        'append': replacement + injected,
        'replace': injected,
    }[shape]
    with pytest.raises(AssertionError, match='redacted passage differs') as exc:
        _assert_redacted_passage(_synthetic_record(spec, mutated), spec)
    assert exc.value.args == ('redacted passage differs from public replacement',)


def test_this_regression_keeps_no_64hex_literal_or_hashing_import():
    tree = ast.parse(Path(__file__).read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            is_digest = (len(node.value) == 64
                         and all(c in '0123456789abcdefABCDEF' for c in node.value))
            assert not is_digest, 'redaction regression must not retain fingerprints'
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = ([node.module or ''] if isinstance(node, ast.ImportFrom)
                     else [alias.name for alias in node.names])
            assert not any(name.split('.')[0] in ('hashlib', 'hmac') for name in names)
