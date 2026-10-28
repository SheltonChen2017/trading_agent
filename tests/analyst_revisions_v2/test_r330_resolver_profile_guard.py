"""Guard direct Analyst outbound-profile expressions for a resolver exception.

Sections 326.35-326.38 support a scoped host resolver requirement, not proof of
every earlier transport failure's cause. This source-template check covers
literal strings (including implicit adjacent concatenation) and f-strings with
opaque interpolated positions. It checks each deny/outbound/require-all clause,
ignoring sandbox comments and treating quoted values as opaque tokens. Six
spent/deliberate-control files are exempt only at exact bytes.

This does not resolve dynamically assembled strings, execute interpolation,
interpret the complete policy, or prove runtime DNS. Source text only.
"""
import ast
import hashlib
import json
from pathlib import Path
import re
import pytest

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
FOLDERS = ('scripts', 'research/analyst_revisions_v2_qc')
OUTBOUND = '(deny network-outbound (require-all'
RESOLVER = '(require-not (literal "/private/var/run/mDNSResponder"))'
_TOKENS = re.compile(r'"(?:\\.|[^"\\])*"|;[^\n]*|[()]|[^\s();"]+')
_OUTBOUND_TOKENS = ['(', 'deny', 'network-outbound', '(', 'require-all']
_RESOLVER_TOKENS = ['(', 'require-not', '(', 'literal',
    '"/private/var/run/mDNSResponder"', ')', ')']
EXEMPT = {
    # Spent R298 transport diagnostics; v2's resolver-free profile is its control arm.
    'scripts/diagnose_arv2_r298_public_transport.py':
        'ccaf46bfabcd7a4f0598bd04cd5d27126467ab5aea18cea5a6c2c919e989194c',
    'scripts/diagnose_arv2_r298_public_transport_v2.py':
        'cd7fe6608ba4b56a748efe8fc1f738d94d6dbfd02da6f724b57644118db4d57d',
    # Spent AD OpenFIGI producer and AF QC rights observer.
    'scripts/inspect_arv2_r298_public_figi_lineage.py':
        '0e1328c07fa82690625a49dbc043cc9facdf125516bfff8a411dd0eb5bfa2ab4',
    'scripts/observe_arv2_r298_native_qc_rights.py':
        'b3a9d74363018e0a2064ae3dd5ab1bbfb4914d0f772363d07eb3be86221e8443',
    # Spent raw-price acquisitions superseded by v3, which carries the literal.
    'scripts/run_arv2_r298_raw_price_acquisition.py':
        '4a3f51135a4ecfe9cf5b7242a95bc4bf89ca332ba3d88bd73b07e93c9a790169',
    'scripts/run_arv2_r298_raw_price_acquisition_v2.py':
        '88a1c9df85f29655d8069826ad3b22453023776299306f6ed192bbf64c427334',
}


def _strings(raw):
    """One view per expression; never re-check f-string constant fragments."""
    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) is str:
            yield node.value
        elif isinstance(node, ast.JoinedStr):
            yield ''.join(item.value if isinstance(item, ast.Constant) else '{}' for item in node.values)
        else:
            for child in ast.iter_child_nodes(node):
                yield from visit(child)
    yield from visit(ast.parse(raw))


def _outbound_states(text):
    """Whether each recognized clause has the exact direct resolver exception."""
    tokens = [token for token in _TOKENS.findall(text) if not token.startswith(';')]
    for index in range(len(tokens)):
        if tokens[index:index + len(_OUTBOUND_TOKENS)] != _OUTBOUND_TOKENS:
            continue
        depth, found, closed = 0, False, False
        for position in range(index + 3, len(tokens)):
            if depth == 1 and tokens[position:position + len(_RESOLVER_TOKENS)] == _RESOLVER_TOKENS:
                found = True
            token = tokens[position]
            depth += (token == '(') - (token == ')')
            if depth == 0:
                closed = True
                break
        yield closed and found


def violations(sources):
    """Paths with an outbound exception string lacking the resolver literal."""
    found = []
    for path, raw in sorted(sources.items()):
        if EXEMPT.get(path) == hashlib.sha256(raw).hexdigest():
            continue
        if any(not present for text in _strings(raw) for present in _outbound_states(text)):
            found.append(path)
    return found


def lane_sources():
    return {str(path.relative_to(ROOT)): path.read_bytes() for folder in FOLDERS
        for path in sorted((ROOT / folder).glob('*.py')) if 'arv2' in path.name or folder != 'scripts'}


def test_every_current_outbound_profile_carries_the_resolver_literal():
    sources = lane_sources()
    assert violations(sources) == []
    covered = [path for path, raw in sources.items() if path not in EXEMPT
        and any(list(_outbound_states(text)) for text in _strings(raw))]
    assert {'scripts/run_arv2_r298_raw_price_acquisition_v3.py',
        'scripts/create_arv2_r298_common_price_project.py',
        'scripts/verify_arv2_r329_qc_source_readback.py'} <= set(covered)


def test_removing_the_literal_from_a_forward_caller_is_refused():
    path = 'scripts/run_arv2_r298_raw_price_acquisition_v3.py'
    raw = (ROOT / path).read_bytes()
    stripped = raw.replace((' ' + RESOLVER).encode(), b'')
    assert stripped != raw and violations({path: stripped}) == [path]


def test_exemptions_are_exact_spent_bytes_that_really_lack_the_literal():
    for path, pin in EXEMPT.items():
        raw = (ROOT / path).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == pin
        assert any(not present for text in _strings(raw) for present in _outbound_states(text))
        assert violations({path: raw + b'\n'}) == [path]


@pytest.mark.parametrize('spacing', ['  ', '\t', '\n'])
def test_semantic_whitespace_does_not_hide_missing_resolver(spacing):
    path = 'scripts/arv2_synthetic_profile.py'
    profile = '(deny' + spacing + 'network-outbound (require-all (require-not (remote tcp "*:443"))))'
    assert violations({path: ('profile = ' + repr(profile)).encode()}) == [path]


def test_fstring_is_checked_as_one_expression_without_child_fragment_false_positive():
    path = 'scripts/arv2_synthetic_profile.py'
    raw = ('profile = f\'(deny network-outbound (require-all '
        '(require-not (remote tcp "*:{port}")) ' + RESOLVER + '))\'').encode()
    assert violations({path: raw}) == []
    assert violations({path: raw.replace(RESOLVER.encode(), b'')}) == [path]


def test_equivalent_resolver_whitespace_is_accepted():
    path = 'scripts/arv2_synthetic_profile.py'
    resolver = '( require-not\n( literal\t"/private/var/run/mDNSResponder" ) )'
    profile = '(deny network-outbound (require-all ' + resolver + '))'
    assert violations({path: ('profile = ' + repr(profile)).encode()}) == []


@pytest.mark.parametrize('decoy', ['; ' + RESOLVER + '\n', json.dumps(RESOLVER)])
def test_comment_or_quoted_resolver_is_not_an_exception(decoy):
    path = 'scripts/arv2_synthetic_profile.py'
    profile = '(deny network-outbound (require-all ' + decoy + '))'
    assert violations({path: ('profile = ' + repr(profile)).encode()}) == [path]


def test_each_outbound_clause_requires_its_own_resolver():
    path = 'scripts/arv2_synthetic_profile.py'
    profile = '(deny network-outbound (require-all ' + RESOLVER + '))' + OUTBOUND + '))'
    assert violations({path: ('profile = ' + repr(profile)).encode()}) == [path]
