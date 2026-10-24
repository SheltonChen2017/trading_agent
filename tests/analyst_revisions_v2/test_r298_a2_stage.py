"""Synthetic-only stage reconciliation; native launcher denies production artifacts."""
from contextlib import ExitStack
import copy
import os
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace

import pytest

from scripts import read_arv2_r298_a2_stage as m


@pytest.fixture(autouse=True)
def no_operational_helpers(monkeypatch):
    def stop(*args, **kwargs):
        raise AssertionError('production helper forbidden in synthetic tests')
    monkeypatch.setattr(m.evidence, 'collect_documents', stop)
    monkeypatch.setattr(m.frozen, '_execute', stop)
    monkeypatch.setattr(m.frozen, '_recover', stop)


@pytest.fixture
def sources():
    return {name: ('# synthetic ' + name + '\n').encode('ascii') for name in sorted(m.remote.SOURCE_NAMES)}


def base_documents():
    binding = m.old_binding()
    return {
        'claim.json': dict(binding), 'evidence-start.json': dict(binding),
        'evidence-parent-completed.json': {**binding, 'evidence': dict(m.EVIDENCE_PIN)},
        'evidence-report.json': {**binding, 'operation_completed': True, **m.FALSE_FLAGS, 'result': {
            'evidence': dict(m.EVIDENCE_PIN), 'attempt_claim_authenticated': True,
            'project_id': m.remote.PROJECT_ID, 'provider_request_count': None}},
        'recover-claim.json': {**binding, 'evidence_sha256': m.EVIDENCE_PIN['sha256'],
            'attempt_id': 2, 'shared_look': 1, 'development_look': 1},
        'evidence-check-start.json': {**binding, 'evidence_sha256': m.EVIDENCE_PIN['sha256']},
        'evidence-check-completed.json': {**binding, 'evidence_sha256': m.EVIDENCE_PIN['sha256'],
            'evidence_bytes': m.EVIDENCE_PIN['byte_count'], 'report_sha256': 'a' * 64,
            'organization_id_sha256': m.evidence.ORGANIZATION},
    }


def names(documents):
    return frozenset(documents) | {'evidence.json'}


def report(summary):
    binding = {'expected_head': 'c' * 40, 'reader_sha256': 'd' * 64,
        'profile_sha256': m.sha(m.canonical(m.profile_record())), 'old_binding': m.old_binding()}
    raw = m.canonical({'schema': m.SCHEMA, **binding, 'attempt_consumed': True})
    return {**summary, **binding, 'claim_sha256': m.sha(raw), 'claim_bytes': len(raw)}


def full_documents(sources, *, wait=False, runtime_error=False):
    documents = base_documents()
    binding = m.old_binding()
    cloud = {'main.py': m.remote.DEFAULT_MAIN, 'accepted_risk_order_level_input_runtime.py': b'#'}
    rows = tuple(SimpleNamespace(project_path=name, source_bytes=raw) for name, raw in sorted(sources.items()))
    manifest = [{'project_path': row.project_path, 'byte_count': len(row.source_bytes),
        'content_sha256': m.sha(row.source_bytes)} for row in rows]
    projection = SimpleNamespace(projection_sha256=m.remote.PROJECTION_SHA256,
        source_files=rows, to_record=lambda: {'candidate_id': 'R298', 'source_files': manifest})
    organization = '0' * 32
    launch_name = f'{m.remote.PROJECT_NAME} A2 {m.remote.PROJECTION_SHA256[:8]}'
    def request(endpoint, payload):
        if endpoint == 'projects/read':
            return {'success': True, 'projects': [{'projectId': m.remote.PROJECT_ID,
                'organizationId': organization, 'name': m.remote.PROJECT_NAME,
                'language': 'Py', 'owner': True, 'codeRunning': False, 'collaborators': []}]}
        if endpoint == 'backtests/list':
            if 'launch-receipt.json' in documents:
                return {'success': True, 'backtests': [{'backtestId': 'bt-1', 'name': launch_name,
                    'status': 'Runtime Error' if runtime_error else 'In Progress...'}]}
            return {'success': True, 'backtests': []}
        if endpoint == 'files/read':
            return {'success': True, 'files': [{'projectId': m.remote.PROJECT_ID, 'name': name,
                'content': raw.decode('ascii')} for name, raw in sorted(cloud.items())]}
        if endpoint in ('files/update', 'files/create'):
            cloud[payload['name']] = payload['content'].encode('ascii')
            return {'success': True}
        if endpoint == 'compile/create':
            return {'success': True, 'compileId': 'compile-1'}
        if endpoint == 'compile/read':
            return {'success': True, 'compileId': 'compile-1', 'state': 'BuildSuccess'}
        if endpoint == 'projects/nodes/read':
            return {'success': True, 'autoSelectNode': True, 'nodes': {'backtest': [
                {'busy': wait, 'active': True}]}}
        assert endpoint == 'backtests/create'
        return {'success': True, 'backtest': {'projectId': m.remote.PROJECT_ID, 'backtestId': 'bt-1',
            'name': launch_name, 'status': 'In Queue...'}}
    def journal(marker, event):
        documents['rpc-' + marker + '-' + event['event'] + '.json'] = {**binding, **event}
    runner = m.remote.RemoteRecovery(projection, organization, request, journal)
    initial = runner.inspect()
    documents['initial-inventory.json'] = initial
    completed = runner.complete(initial)
    documents['completed-inventory.json'] = completed
    compiled = runner.compile_once(completed)
    documents['compile-receipt.json'] = compiled
    state = runner.poll_compile(compiled['compile_id'], 0)
    documents['compile-status-00.json'] = state
    launched = runner.launch_once(compiled['compile_id'])
    documents['launch-receipt.json'] = launched
    if wait:
        result = {'terminal': 'capacity_wait', 'project_id': m.remote.PROJECT_ID, 'compile_id': compiled['compile_id']}
    else:
        status = runner.read_status(launched, 0)
        documents['own-status.json'] = status
        if runtime_error:
            return documents
        result = {'terminal': 'own_status_observed', 'launch': launched, 'status': status}
    count = sum(name.endswith('-intent.json') for name in documents)
    documents['recover-report.json'] = {**binding, 'operation_completed': True, **m.FALSE_FLAGS,
        'result': {**result, 'application_dispatch_count': count, 'provider_request_count': None}}
    return documents


def test_base_actual_fixed_report_pin(sources):
    documents = base_documents()
    value = m.validate_documents(documents, names(documents), sources)
    assert value['rpc_intent_count'] == value['rpc_observed_count'] == 0
    assert value['last_recorded_marker'] is None
    assert value['provider_request_count'] is None
    assert m.validate_report(report(value)) == report(value)


@pytest.mark.parametrize('wait,runtime_error', [(False, False), (True, False), (False, True)])
def test_complete_synthetic_prefixes(sources, wait, runtime_error):
    documents = full_documents(sources, wait=wait, runtime_error=runtime_error)
    value = m.validate_documents(documents, names(documents), sources)
    assert value['completed_inventory_recorded'] and value['compile_id'] == 'compile-1'
    assert value['backtest_id'] == (None if wait else 'bt-1')
    assert value['recorded_status'] == ('capacity_wait' if wait else 'Runtime Error' if runtime_error else 'In Progress...')
    assert m.validate_report(report(value)) == report(value)


def test_every_success_path_interrupted_prefix(sources):
    documents = full_documents(sources)
    entries = list(documents.items())
    for length in range(len(base_documents()), len(entries) + 1):
        prefix = dict(entries[:length])
        value = m.validate_documents(prefix, names(prefix), sources)
        assert value['control_file_count'] == len(prefix) + 1
        m.validate_report(report(value))


@pytest.mark.parametrize('mutation', ['extra', 'gap', 'wrong_event', 'endpoint', 'request_hash',
    'head', 'caller', 'profile', 'project_bool', 'extra_binding', 'response_hash', 'unknown_marker'])
def test_marker_mutations_refuse(sources, mutation):
    documents = full_documents(sources)
    key = 'rpc-inspect-project-intent.json'
    if mutation == 'extra':
        documents['unrelated.json'] = {}
    elif mutation == 'gap':
        del documents[key]
    elif mutation == 'unknown_marker':
        documents['rpc-unknown-intent.json'] = documents.pop(key)
    else:
        row = documents['rpc-inspect-project-observed.json'] if mutation == 'response_hash' else documents[key]
        field, value = {'wrong_event': ('event', 'observed'), 'endpoint': ('endpoint', 'files/read'),
            'request_hash': ('sha256', 'b' * 64), 'head': ('expected_head', 'b' * 40),
            'caller': ('caller_sha256', 'b' * 64), 'profile': ('profile_sha256', 'b' * 64),
            'project_bool': ('project_id', True), 'extra_binding': ('secret', 'no'),
            'response_hash': ('sha256', 'oops')}[mutation]
        row[field] = value
    with pytest.raises(m.Refused):
        m.validate_documents(documents, names(documents), sources)


@pytest.mark.parametrize('filename', list(base_documents()))
def test_base_documents_exact(sources, filename):
    documents = base_documents()
    documents[filename]['extra'] = 'SECRET'
    with pytest.raises(m.Refused):
        m.validate_documents(documents, names(documents), sources)


@pytest.mark.parametrize('filename', ['initial-inventory.json', 'completed-inventory.json',
    'compile-receipt.json', 'compile-status-00.json', 'launch-receipt.json', 'own-status.json', 'recover-report.json'])
def test_receipt_extra_fields_refuse(sources, filename):
    documents = full_documents(sources)
    documents[filename]['extra'] = 1
    with pytest.raises(m.Refused):
        m.validate_documents(documents, names(documents), sources)


@pytest.mark.parametrize('category,status', [('unknown', None), ('status_or_bound_refusal', None),
    ('http_failure', 403), ('http_non_json', 502)])
def test_exact_failure_metadata(sources, category, status):
    documents = base_documents()
    binding = m.old_binding()
    documents['rpc-inspect-project-intent.json'] = {**binding, 'event': 'intent',
        'endpoint': 'projects/read', 'sha256': m.sha(m.canonical({'projectId': m.remote.PROJECT_ID}))}
    documents['rpc-inspect-project-failure.json'] = {**binding, 'intent_marker': 'inspect-project',
        'endpoint': 'projects/read', 'application_dispatch_count': 1, 'category': category,
        'http_status': status, 'provider_request_count': None}
    value = m.validate_documents(documents, names(documents), sources)
    assert value['rpc_failure_count'] == 1 and value['recorded_application_dispatch_count'] == 1
    assert value['provider_request_count'] is None and value['lost_cause_recovered'] is False
    m.validate_report(report(value))
    documents['rpc-inspect-project-failure.json']['application_dispatch_count'] = 2
    with pytest.raises(m.Refused):
        m.validate_documents(documents, names(documents), sources)


@pytest.mark.parametrize('field,value', [('provider_request_count', 0), ('stage_authenticated', 1),
    ('old_attempt_id', True), ('project_id', True), ('rpc_intent_count', True), ('rpc_markers', ['invented']),
    ('last_recorded_event', 'observed'), ('receipts_present', ['claim.json']),
    ('control_file_count', 1), ('compile_id', 'x'), ('recorded_status', 'SUCCESS'),
    ('reader_sha256', 'bad'), ('expected_head', 'bad'), ('operational_retry_authority', True),
    ('no_unjournaled_effects_proven', True), ('lost_cause_recovered', True)])
def test_report_schema_dangerous_mutations(sources, field, value):
    documents = base_documents()
    output = report(m.validate_documents(documents, names(documents), sources))
    output[field] = value
    with pytest.raises(m.Refused):
        m.validate_report(output)


@pytest.mark.parametrize('raw', [b'{}', b'{}\n\n', b'{ "x":1}\n', b'{"x":1,"x":2}\n',
    b'{"x":NaN}\n', b'[]\n', b'{"x":"\xff"}\n'])
def test_noncanonical_json_refused(raw):
    with pytest.raises(m.Refused):
        m.parse(raw)


@pytest.fixture
def control(tmp_path, monkeypatch):
    path = tmp_path / 'fixed'
    path.mkdir(mode=0o700)
    for name, value in base_documents().items():
        (path / name).write_bytes(m.canonical(value))
        (path / name).chmod(0o600)
    (path / 'evidence.json').write_bytes(b'SECRET MUST NOT BE OPENED')
    (path / 'evidence.json').chmod(0)
    monkeypatch.setattr(m, 'CONTROL', path)
    return path


def test_selected_reader_never_opens_evidence(control, monkeypatch):
    original = os.open
    seen = []
    def tracked(path, *args, **kwargs):
        assert path != 'evidence.json'
        seen.append(path)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(os, 'open', tracked)
    documents, inventory = m._read_documents(time.monotonic() + 10)
    assert set(documents) == m.BASE_NAMES - {'evidence.json'}
    assert inventory == m.BASE_NAMES and 'evidence.json' not in seen


@pytest.mark.parametrize('mutation', ['extra', 'unknown_rpc', 'partial', 'mode', 'symlink', 'hardlink', 'directory', 'noncanonical'])
def test_filesystem_refusals(control, mutation):
    path = control / 'claim.json'
    if mutation == 'extra':
        (control / 'unexpected.json').write_bytes(b'{}\n')
    elif mutation == 'unknown_rpc':
        (control / 'rpc-unknown-intent.json').write_bytes(b'NO PARSING THIS')
    elif mutation == 'partial':
        path.write_bytes(b'')
    elif mutation == 'mode':
        path.chmod(0o644)
    elif mutation == 'symlink':
        path.unlink()
        path.symlink_to('evidence.json')
    elif mutation == 'hardlink':
        os.link(path, control / 'compile-receipt.json')
    elif mutation == 'directory':
        path.unlink()
        path.mkdir()
    else:
        path.write_bytes(b'{ }\n')
    with pytest.raises((m.Refused, OSError)):
        m._read_documents(time.monotonic() + 10)


@pytest.mark.parametrize('mutation', ['replace', 'modify', 'append_name'])
def test_held_metadata_rechecked_after_validation(control, mutation):
    def validator(documents, inventory):
        path = control / 'claim.json'
        if mutation == 'replace':
            raw = path.read_bytes()
            path.unlink()
            path.write_bytes(raw)
            path.chmod(0o600)
        elif mutation == 'modify':
            path.write_bytes(b'{}\n')
        else:
            (control / 'rpc-inspect-project-intent.json').write_bytes(b'{}\n')
        return None
    with pytest.raises(m.Refused, match='changed'):
        m._read_documents(time.monotonic() + 10, validator)


def test_search_ancestor_descriptor_cannot_census(tmp_path):
    leaf = tmp_path / 'a' / 'b'
    leaf.mkdir(parents=True)
    with ExitStack() as stack:
        fd, chain = m._open_directory(leaf, stack)
        assert os.listdir(fd) == []
        for parent, _, _, _ in chain:
            with pytest.raises(OSError):
                os.listdir(parent)
        m._verify_chain(chain)


def test_opaque_error_never_stringified():
    class Hostile(Exception):
        def __str__(self):
            pytest.fail('opaque error stringified')
    assert m.finite_failure(Hostile(object())) == 'unclassified_refusal'
    assert m.finite_failure(m.Refused(object())) == 'unclassified_refusal'
    assert m.finite_failure(m.Refused('SECRET')) == 'unclassified_refusal'
    assert m.finite_failure(m.Refused('changed')) == 'changed'


def test_new_claim_exclusive_no_old_read_on_duplicate(tmp_path, monkeypatch, sources):
    root = tmp_path / 'root'
    parent = root / 'artifacts' / 'analyst_revisions_v2'
    parent.mkdir(parents=True)
    monkeypatch.setattr(m, 'ROOT', root)
    monkeypatch.setattr(m, 'OUTPUT', parent / 'newrule_reconciliation' / 'fixed')
    monkeypatch.setattr(m, '_preflight', lambda *args: None)
    projected = SimpleNamespace(source_files=tuple(SimpleNamespace(project_path=name,
        source_bytes=raw) for name, raw in sources.items()))
    monkeypatch.setattr(m.evidence, 'reconstruct_projection', lambda: projected)
    calls = []
    def reader(deadline, validator):
        assert (m.OUTPUT / 'claim.json').is_file()
        calls.append(1)
        docs = base_documents()
        return validator(docs, names(docs))
    monkeypatch.setattr(m, '_read_documents', reader)
    value = m._claim_and_read('a' * 40, 'b' * 64, time.monotonic() + 10)
    assert value['stage_authenticated'] is True and calls == [1]
    assert value['report']['sha256'] == m.sha((m.OUTPUT / 'report.json').read_bytes())
    with pytest.raises(FileExistsError):
        m._claim_and_read('a' * 40, 'b' * 64, time.monotonic() + 10)
    assert calls == [1]


def test_deadline_before_old_read_and_main_finite_failure(monkeypatch, capsys):
    monkeypatch.setattr(m, '_preflight', lambda *args: (_ for _ in ()).throw(m.Refused('deadline')))
    assert m.main(['--expected-head', 'a' * 40, '--reader-sha256', 'b' * 64]) == 2
    value = m.parse(capsys.readouterr().out.encode('ascii'))
    assert value['failure_code'] == 'deadline' and value['stage_authenticated'] is False
    assert value['provider_request_count'] is None


def test_profile_sandbox_and_non_authority():
    value = m.profile_record()
    assert value['deadline_seconds'] == 30 and value['evidence_payload_read'] is False
    assert value['operational_retry_authority'] is False
    assert '(deny network*)' in m.SANDBOX
    assert 'file-read-data' in m.SANDBOX and 'file-read-metadata' in m.SANDBOX
    assert str(m.CONTROL / 'evidence.json') in m.SANDBOX


@pytest.mark.parametrize('mutation', ['reader_pin', 'blob', 'profile', 'credential', 'head'])
def test_preflight_binding_checks(monkeypatch, mutation):
    raw = b'synthetic-reader'
    expected = m.sha(raw)
    monkeypatch.setattr(m.frozen, '_preflight', lambda *args: None)
    monkeypatch.setattr(m.frozen.helpers, '_source_digest', lambda path: '0' * 64 if mutation == 'reader_pin' else expected)
    monkeypatch.setattr(m.frozen.v5, '_git', lambda *args: b'wrong' if mutation == 'blob' else raw)
    if mutation == 'profile':
        monkeypatch.setattr(m.frozen, 'profile_record', lambda: {})
    if mutation == 'credential':
        monkeypatch.setenv('QC_API_TOKEN', 'SYNTHETIC')
    with pytest.raises(m.Refused):
        m._preflight('bad' if mutation == 'head' else 'a' * 40, expected, time.monotonic() + 10)


def native_profile_smoke(path):
    """Standalone synthetic child, not invoked from nested native pytest sandbox.

    This helper is deliberately not a pytest test: Darwin rejects nested
    sandbox application. Its caller must retain the actual standalone result.
    """
    root = path / 'root'
    base = root / 'artifacts' / 'analyst_revisions_v2'
    control = base / 'newrule_recovery' / 'fixed'
    control.mkdir(parents=True, mode=0o700)
    output = base / 'newrule_reconciliation' / 'fixed'
    for name, value in base_documents().items():
        (control / name).write_bytes(m.canonical(value))
        (control / name).chmod(0o600)
    (control / 'evidence.json').write_bytes(b'SYNTHETIC PRIVATE BUNDLE')
    sibling = base / 'sibling'
    sibling.mkdir()
    (sibling / 'private.json').write_bytes(b'NO READ')
    policy = m.sandbox_profile(root, control, output)
    policy += '(deny file-read* file-write* (subpath "' + str(m.ROOT / 'artifacts') + '"))'
    program = r'''
import os, socket, sys, time
from pathlib import Path
from scripts import read_arv2_r298_a2_stage as m
m.ROOT, m.CONTROL, m.OUTPUT = map(Path, sys.argv[1:4])
result = m._read_documents(time.monotonic() + 10)
assert result[1] == m.BASE_NAMES
for path in (m.CONTROL / 'evidence.json', m.OUTPUT.parent.parent / 'sibling/private.json'):
    try:
        path.read_bytes()
    except PermissionError:
        pass
    else:
        raise AssertionError('private read allowed')
for path in (m.CONTROL.parent, m.OUTPUT.parent.parent):
    try:
        os.listdir(path)
    except PermissionError:
        pass
    else:
        raise AssertionError('ancestor census allowed')
try:
    socket.socket().bind(('127.0.0.1', 0))
except PermissionError:
    pass
else:
    raise AssertionError('network allowed')
m._preflight = lambda *args: None
m.evidence.reconstruct_projection = lambda: type('Projection', (), {'source_files': tuple(
    type('Entry', (), {'project_path': name, 'source_bytes': b'# synthetic\n'})()
    for name in sorted(m.remote.SOURCE_NAMES))})()
result = m._claim_and_read('a' * 40, 'b' * 64, time.monotonic() + 10)
assert result['stage_authenticated'] is True
assert set(os.listdir(m.OUTPUT)) == {'claim.json', 'report.json'}
print('native-profile-smoke-ok')
'''
    result = subprocess.run(['/usr/bin/sandbox-exec', '-p', policy,
        str(m.frozen.frozen.PYTHON), '-B', '-c', program, str(root), str(control), str(output)],
        cwd=m.ROOT, env=dict(os.environ), stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    assert result.returncode == 0, (result.returncode, result.stderr.decode('utf-8', 'replace'))
    assert result.stdout == b'native-profile-smoke-ok\n' and result.stderr == b''
