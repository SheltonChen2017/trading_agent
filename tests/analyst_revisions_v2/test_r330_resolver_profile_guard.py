"""Every Analyst outbound-network sandbox profile carries the resolver literal.

Section 330 (ARV2R328-002). Sections 326.35-326.38 showed that on this host a
sandboxed network child cannot resolve names unless its outbound exception also
admits (literal "/private/var/run/mDNSResponder"). A profile string that opens
outbound exceptions must contain that literal. Only the closed set of spent or
deliberate-control files below may omit it, each bound to its exact bytes, so a
new caller or an edited exempt file fails. Source text only; nothing is run.
"""
import ast
import hashlib
from pathlib import Path

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
FOLDERS = ('scripts', 'research/analyst_revisions_v2_qc')
OUTBOUND = '(deny network-outbound (require-all'
RESOLVER = '(require-not (literal "/private/var/run/mDNSResponder"))'
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
    """Each string expression; adjacent literals are already one constant."""
    for node in ast.walk(ast.parse(raw)):
        if isinstance(node, ast.Constant) and type(node.value) is str:
            yield node.value
        elif isinstance(node, ast.JoinedStr):
            yield ''.join(item.value if isinstance(item, ast.Constant) else '{}' for item in node.values)


def violations(sources):
    """Paths with an outbound exception string lacking the resolver literal."""
    found = []
    for path, raw in sorted(sources.items()):
        if EXEMPT.get(path) == hashlib.sha256(raw).hexdigest():
            continue
        if any(OUTBOUND in text and RESOLVER not in text for text in _strings(raw)):
            found.append(path)
    return found


def lane_sources():
    return {str(path.relative_to(ROOT)): path.read_bytes() for folder in FOLDERS
        for path in sorted((ROOT / folder).glob('*.py')) if 'arv2' in path.name or folder != 'scripts'}


def test_every_current_outbound_profile_carries_the_resolver_literal():
    sources = lane_sources()
    assert violations(sources) == []
    covered = [path for path, raw in sources.items() if path not in EXEMPT
        and any(OUTBOUND in text for text in _strings(raw))]
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
        assert any(OUTBOUND in text and RESOLVER not in text for text in _strings(raw))
        assert violations({path: raw + b'\n'}) == [path]
