"""A11 synthetic caller/admission tests; native denial is required externally.

No private artifact, provider, credential, frozen entrypoint or real QC operation.
Fresh plain capabilities below are minted only from public synthetic fixtures.
"""
import copy
import os
from pathlib import Path
import time
from types import SimpleNamespace as NS

import pytest

from scripts import run_arv2_r298_plain_readiness as m
from scripts import arv2_newrule_execution_environment as environment
from tests.analyst_revisions_v2 import test_r298_plain_readiness_remote as cloud_fixtures
from tests.analyst_revisions_v2 import test_newrule_plain_projection as projection_fixtures
from tests.analyst_revisions_v2 import test_newrule_plain_storage as storage_fixtures


@pytest.fixture(autouse=True)
def no_operational_entrypoints(monkeypatch):
    from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
    hits = []
    def refuse(*args, **kwargs):
        hits.append(True)
        raise AssertionError('synthetic test reached an operational seam')
    for module, names in ((m.a3, ('main', '_execute', '_recover', '_worker', '_child', '_workflow')),
        (m.a6, ('main', '_execute', '_recover', '_worker', '_child', '_workflow')),
        (m.prep, ('main', 'assess', 'construct')),
        (m._storage_module(), ('main', 'publish', 'worker')),
        (m.previous, ('_admission',)), (old, ('_client',))):
        for name in names:
            if hasattr(module, name):
                monkeypatch.setattr(module, name, refuse)
    yield
    assert not hits


@pytest.fixture
def args():
    return NS(operation='recover', expected_head='a' * 40, caller_sha256='b' * 64,
        control_fd=None, deadline=None)


class MemoryStore:
    def __init__(self, cloud=None):
        self.values, self.events, self.cloud = {}, [], cloud
        self.fail = None
        self.fd = 123
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def write(self, name, value):
        self.events.append(('write', name))
        if name == self.fail: raise RuntimeError('synthetic journal refusal')
        assert name not in self.values
        self.values[name] = m.canonical(value)
        if self.cloud and name.startswith('rpc-') and value.get('event') in ('intent', 'observed'):
            marker = name[4:].removesuffix('-' + value['event'] + '.json')
            self.cloud.events.append((marker, {key: value[key] for key in ('event', 'endpoint', 'sha256')}))
        return {'sha256': m.sha(self.values[name]), 'byte_count': len(self.values[name])}
    def read(self, name): return self.values[name], m.parse(self.values[name])
    def verify(self): self.events.append(('verify', None))


@pytest.fixture
def cloud(monkeypatch):
    value = cloud_fixtures.cloud.__wrapped__(monkeypatch)
    manifest = {'project_id': m.PROJECT, 'projection_sha256': m.remote.PROJECTION_SHA256,
        'files': [{'name': name, 'byte_count': len(raw), 'sha256': m.sha(raw)} for name, raw in value.pairs]}
    frozen = copy.deepcopy(m.STORAGE_FREEZE)
    frozen['source_manifest_sha256'] = m.sha(m.canonical(manifest))
    monkeypatch.setattr(m, 'STORAGE_FREEZE', frozen)
    value.packet = {'admission_authenticated': True, 'storage_receipt': m._storage_receipt(),
        'projection_record': value.record_bytes.decode('ascii'),
        'source_pairs': [[name, raw.decode('ascii')] for name, raw in value.pairs]}
    value.store = MemoryStore(value)
    value.children, value.order = [], []
    def child(args, store, deadline, operation):
        assert 'claim.json' in store.values
        value.children.append(operation)
        value.order.append(operation)
        return copy.deepcopy(value.packet)
    class Client:
        boundary_code = None
        def __init__(self, sink):
            value.order.append('credentials')
            assert value.children == ['admission-initial-worker']
        def request(self, endpoint, payload):
            m._validate_request(endpoint, payload)
            return value.request(endpoint, payload)
    monkeypatch.setattr(m, '_child', child)
    monkeypatch.setattr(m, 'OwnerClient', Client)
    monkeypatch.setattr(environment, 'require_safe_environment', lambda: None)
    monkeypatch.setattr(m.time, 'sleep', lambda _: None)
    return value


def state():
    return {**m.a3._new_state(), 'code_running': None, 'response_observation': None,
        'response_boundary_code': None, 'access_observation': None}


def recover(cloud, args):
    current = state()
    result = m._recover(args, cloud.store, time.monotonic() + 800, current)
    m._validate_result(result)
    return result, current


def test_actual_d2_freeze_is_exact_and_separate_from_old_storage():
    frozen = m._storage_freeze()
    assert frozen['actual_exit'] == 0 and type(frozen['actual_exit']) is int
    assert frozen['expected_head'] == '8feb75dbda9d174e95dc5f49d3c8d29c12ff459c'
    assert frozen['files'][m.storage.ADMISSION] == {'byte_count': 1037,
        'sha256': '5e97a7b3987994f32663fd0f019b53be7767f4a3d71d2eef627b68ba3c4d7202'}
    assert m.CONTROL.name == 'R322-20261025-C' and m.STORAGE_CONTROL.name == 'R322-20261025-B'
    assert m.profile_record()['old_d15_admits_new_objects'] is False
    frozen['files'].clear()
    assert len(m._storage_freeze()['files']) == 5


@pytest.mark.parametrize('field,value', [('actual_exit', 2), ('actual_exit', None), ('actual_exit', False),
    ('expected_head', 'a' * 39), ('caller_sha256', '0' * 64), ('profile_sha256', 'x' * 64),
    ('source_manifest_sha256', None), ('files', {})])
def test_external_storage_freeze_refuses_bad_or_ambiguous_pins(monkeypatch, field, value):
    frozen = copy.deepcopy(m.STORAGE_FREEZE)
    frozen[field] = value
    monkeypatch.setattr(m, 'STORAGE_FREEZE', frozen)
    with pytest.raises(m.Refused, match='storage_binding'): m._storage_freeze()


def test_full_caller_preserves_admission_before_credentials_and_at_ready(cloud, args):
    result, current = recover(cloud, args)
    assert result['terminal'] == 'ready_for_backtest'
    assert result['application_dispatch_count'] == len(cloud.calls) == 38
    assert result['provider_request_count'] is None
    assert cloud.order == ['admission-initial-worker', 'credentials', 'admission-final-worker']
    assert current['last_stage'] == 'admission_final'
    assert cloud.files == {name: raw.decode('ascii') for name, raw in cloud.pairs}
    assert sum(ep == 'compile/create' for ep, _ in cloud.calls) == 1
    assert sum(ep == 'files/update' for ep, _ in cloud.calls) == 2
    assert sum(ep == 'files/create' for ep, _ in cloud.calls) == 7
    assert not {'projects/nodes/read', 'backtests/create', 'backtests/read'} & {ep for ep, _ in cloud.calls}
    assert result['access_observation']['marker'] == 'ready-access'
    assert all(result['ready_receipt'][name] is False for name in m.remote.FALSE_FLAGS)


@pytest.mark.parametrize('mutation', ['manifest', 'compile', 'attempt', 'source', 'storage', 'idle', 'count', 'provider'])
def test_result_rejects_false_ready_even_after_real_synthetic_flow(cloud, args, mutation):
    result, _ = recover(cloud, args)
    if mutation == 'manifest': result['ready_receipt']['source_manifest_sha256'] = 'f' * 64
    elif mutation == 'compile': result['ready_receipt']['compile_id'] = ''
    elif mutation == 'attempt': result['ready_receipt']['attempt'] = 10
    elif mutation == 'source': result['ready_receipt']['projection_sha256'] = 'f' * 64
    elif mutation == 'storage': result['storage_receipt']['actual_storage_exit'] = 2
    elif mutation == 'idle': result['code_running']['boolean_value'] = True
    elif mutation == 'count': result['application_dispatch_count'] = True
    else: result['provider_request_count'] = 0
    with pytest.raises((m.Refused, m.remote.Refused)): m._validate_result(result)


@pytest.mark.parametrize('failure_at', ['initial', 'final', 'compile_error', 'compile_budget', 'readback', 'access'])
def test_failure_stops_without_retry_launch_or_alternate_source(cloud, args, monkeypatch, failure_at):
    if failure_at in ('initial', 'final'):
        original = m._child
        def child(a, s, d, op):
            if op == 'admission-' + failure_at + '-worker':
                cloud.order.append('refused-' + op)
                raise m.Refused('input_admission')
            return original(a, s, d, op)
        monkeypatch.setattr(m, '_child', child)
    elif failure_at == 'compile_error': cloud.compile_state = 'BuildError'
    elif failure_at == 'compile_budget': cloud.compile_state = 'InQueue'
    elif failure_at == 'readback':
        def mutate(endpoint, payload, result):
            if endpoint == 'files/update': cloud.files[payload['name']] = '# changed\n'
        cloud.mutation = mutate
    else: cloud.project['collaborators'].append(copy.deepcopy(cloud.extra) | {'publicId': 'unknown'})
    with pytest.raises((m.Refused, m.remote.Refused, m.remote.access.AccessRefused)):
        m._recover(args, cloud.store, time.monotonic() + 800, state())
    assert not {'backtests/create', 'projects/nodes/read'} & {ep for ep, _ in cloud.calls}
    assert sum(ep == 'compile/create' for ep, _ in cloud.calls) <= 1
    if failure_at == 'initial': assert not cloud.calls and 'credentials' not in cloud.order
    if failure_at == 'readback': assert sum(ep in ('files/create', 'files/update') for ep, _ in cloud.calls) == 1
    if failure_at == 'compile_budget': assert sum(ep == 'compile/read' for ep, _ in cloud.calls) == 20
    if failure_at == 'access': assert len(cloud.calls) == 2 and 'inspect-access.json' in cloud.store.values


def test_access_journal_failure_keeps_finite_in_memory_snapshot(cloud, args):
    cloud.store.fail = 'inspect-access.json'
    current = state()
    with pytest.raises(RuntimeError): m._recover(args, cloud.store, time.monotonic() + 800, current)
    assert current['access_observation']['journal_pin'] is None
    failure = m._failure(RuntimeError(), current)
    assert failure['access_observation']['observation']['stage'] == 'inspect'
    assert len(cloud.calls) == 2 and not any(ep.endswith('/acquire') for ep, _ in cloud.calls)


@pytest.mark.parametrize('code', sorted(m.remote.access.FINITE_CODES))
def test_exact_known_access_exception_retains_only_finite_predicate(code):
    error = m.remote.access.AccessRefused(code)
    assert m.finite_code(error) == 'remote_refused'
    assert m.helper_failure(error) == {'helper_code': code,
        'predicate': m.remote.predecessor.OWNERSHIP_PREDICATES.get(code)}


def test_unknown_exception_cannot_render_secrets():
    class Hostile(Exception):
        def __str__(self): raise AssertionError('must not render')
        def __repr__(self): raise AssertionError('must not render')
    error = Hostile('synthetic secret')
    assert m.finite_code(error) == 'unknown_exception'
    assert m.helper_failure(error) == {'helper_code': 'unknown', 'predicate': None}
    assert m.helper_failure(m.remote.access.AccessRefused('synthetic secret'))['helper_code'] == 'unknown'


@pytest.mark.parametrize('endpoint', ['projects/nodes/read', 'backtests/create', 'backtests/read',
    'backtests/orders/read', 'projects/create', 'files/delete', 'projects/collaboration/delete', 'live/create'])
def test_parent_request_boundary_never_accepts_prohibited_endpoint(endpoint):
    with pytest.raises(m.Refused, match='client'): m._validate_request(endpoint, {'projectId': m.PROJECT})


@pytest.mark.parametrize('credentials', [{}, {'QC_USER_ID': 'x'}, {'QC_API_TOKEN': 'x'},
    {'QC_USER_ID': ' ', 'QC_API_TOKEN': 'x'}, {'QC_USER_ID': 'x', 'QC_API_TOKEN': ''}])
def test_missing_credentials_refuse_before_claim_or_source_worker(monkeypatch, args, credentials):
    for name in ('QC_USER_ID', 'QC_API_TOKEN'): monkeypatch.delenv(name, raising=False)
    for name, value in credentials.items(): monkeypatch.setenv(name, value)
    monkeypatch.setattr(m, '_preflight', lambda *_: None)
    monkeypatch.setattr(environment, 'require_safe_environment', lambda: None)
    monkeypatch.setattr(m, 'Store', lambda **_: pytest.fail('claim must not be allocated'))
    with pytest.raises(m.Refused, match='credential_handoff'): m._execute(args, time.monotonic() + 800)


def test_worker_postauth_rechecks_source_and_control(cloud, args, monkeypatch):
    args.operation, args.control_fd = m.WORKERS[0], 123
    store = MemoryStore()
    store.write('claim.json', m.claim(args))
    projected = NS(record_bytes=cloud.record_bytes, source_files=tuple(NS(project_path=n, source_bytes=b) for n, b in cloud.pairs))
    order = []
    monkeypatch.setattr(m, 'Store', lambda **_: store)
    monkeypatch.setattr(m.prep, 'construct', lambda _: (order.append('source') or 'plain', projected))
    monkeypatch.setattr(m, 'authenticate_storage', lambda *_: order.append('admission') or m._storage_receipt())
    monkeypatch.setattr(m, '_preflight', lambda *_: order.append('postflight'))
    packet = m._worker(args, time.monotonic() + 800)
    assert order == ['source', 'admission', 'postflight'] and store.events[-1] == ('verify', None)
    assert packet == cloud.packet and args.operation + '-start.json' in store.values


def test_worker_postauth_source_change_refuses_packet(cloud, args, monkeypatch):
    args.operation, args.control_fd = m.WORKERS[0], 123
    store = MemoryStore(); store.write('claim.json', m.claim(args))
    projected = NS(record_bytes=cloud.record_bytes, source_files=tuple(NS(project_path=n, source_bytes=b) for n, b in cloud.pairs))
    monkeypatch.setattr(m, 'Store', lambda **_: store)
    monkeypatch.setattr(m.prep, 'construct', lambda _: ('plain', projected))
    monkeypatch.setattr(m, 'authenticate_storage', lambda *_: m._storage_receipt())
    def refuse(*_): raise m.Refused('source')
    monkeypatch.setattr(m, '_preflight', refuse)
    with pytest.raises(m.Refused, match='source'): m._worker(args, time.monotonic() + 800)


@pytest.fixture(scope='module')
def plain_data():
    case = projection_fixtures.case.__wrapped__(projection_fixtures.public_parent.__wrapped__())
    projected = projection_fixtures.build(case)
    record = {'schema': m.storage.PREPARATION_SCHEMA, 'expected_head': 'a' * 40,
        'caller_sha256': 'b' * 64, 'profile_sha256': 'c' * 64,
        'complete': True, 'failure_code': None, 'transport': case.plain.to_record(),
        'projection': projected.to_record(), 'attempt_consumed': True,
        **{name: False for name in m.storage.PREPARATION_FALSE}}
    return NS(plain=case.plain, projected=projected, record=record)


@pytest.fixture
def admission(plain_data, monkeypatch):
    publication = m._storage_module()
    organization = storage_fixtures.ORGANIZATION
    orgsha = m.sha(organization.encode('ascii'))
    monkeypatch.setattr(m.remote.access, 'ORGANIZATION_SHA256', orgsha)
    synthetic = storage_fixtures.case.__wrapped__(plain_data, monkeypatch)
    monkeypatch.setattr(m.storage, 'access', NS(ORGANIZATION_SHA256=orgsha,
        _organization=m.remote.access._organization))
    result = storage_fixtures.run(synthetic)
    assert result['complete'] is True
    projected, plain = plain_data.projected, plain_data.plain
    for name, value in {'PACKAGE_SHA256': plain.package_sha256,
        'ACTIVATION_SHA256': plain.activation_manifest_sha256,
        'PROJECTION_SHA256': projected.projection_sha256,
        'PROFILE_SHA256': projected.to_record()['profile_sha256']}.items():
        monkeypatch.setattr(m.remote, name, value)
    monkeypatch.setattr(publication, 'EXPECTED', m.prep.summary(plain, projected))
    monkeypatch.setattr(publication, 'PREPARATION_SHA256', synthetic.kwargs['expected_preparation_sha256'])
    storage_args = NS(expected_head='a' * 40, caller_sha256='b' * 64)
    bound = publication.binding(storage_args)
    source_manifest = {'project_id': m.PROJECT, 'projection_sha256': projected.projection_sha256,
        'files': [{'name': item.project_path, 'byte_count': len(item.source_bytes), 'sha256': m.sha(item.source_bytes)}
            for item in sorted(projected.source_files, key=lambda item: item.project_path)]}
    summary = {**publication.EXPECTED, 'activation_manifest_key': plain.activation_manifest_key,
        'activation_manifest_byte_count': plain.activation_manifest_byte_count,
        'project_source_manifest_sha256': m.sha(m.canonical(source_manifest))}
    values = synthetic.directory.values
    values['organization-binding.json'] = {**bound, 'organization_id': organization, 'organization_sha256': orgsha}
    def pin(name):
        raw = m.canonical(values[name]); return {'sha256': m.sha(raw), 'byte_count': len(raw)}
    values['worker-result.json'] = {**bound, 'result': result}
    values['parent-claim.json'] = {**bound, 'parent_pid': 123, 'attempt_consumed': True}
    values['worker-start.json'] = {**bound, 'worker_pid': 124}
    for index, project in enumerate((publication.REFERENCE, m.PROJECT)):
        values[f'organization-{index}-intent.json'] = {'endpoint': 'projects/read', 'project_id': project}
        values[f'organization-{index}-observed.json'] = {'project_id': project, 'organization_sha256': orgsha,
            'response_sha256': 'c' * 64, 'scope_accepted': True}
    for entry in values[m.storage.REPORT]['requests']:
        ordinal = entry['ordinal']
        values[f'broker-{ordinal:02d}-intent.json'] = {key: entry[key] for key in
            ('ordinal', 'phase', 'endpoint', 'index', 'request_sha256')}
        values[f'broker-{ordinal:02d}-observed.json'] = {'ordinal': ordinal,
            'packet': {key: entry[key] for key in m.storage.PACKET_FIELDS}}
    values['broker-report.json'] = {**bound, 'worker_result': result, 'worker_result_file': pin('worker-result.json'),
        'worker_failure_code': None, 'summary': summary, 'organization_binding': pin('organization-binding.json'),
        'attempt_consumed': True, 'organization_dispatches': 2, 'storage_dispatches': 24,
        'worker_exit': 0, **publication.FALSE_FLAGS}
    frozen = {'actual_exit': 0, **{key: bound[key] for key in ('expected_head', 'caller_sha256', 'profile_sha256')},
        'source_manifest_sha256': summary['project_source_manifest_sha256'],
        'files': {name: pin(name) for name in m.STORAGE_FREEZE['files']}}
    monkeypatch.setattr(m, 'STORAGE_FREEZE', frozen)
    class Reader:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read_raw(self, name): synthetic.directory.events.append(('read_raw', name)); return m.canonical(values[name])
        def read(self, name): return copy.deepcopy(values[name])
        def names(self): return tuple(values)
        def verify(self): synthetic.directory.verify()
    monkeypatch.setattr(m, 'AdmissionStore', Reader)
    return NS(plain=plain, projected=projected, values=values, frozen=frozen, pin=pin,
        publication=publication, directory=synthetic.directory)


def authenticate(case):
    return m.authenticate_storage(case.plain, case.projected, time.monotonic() + 800)


def test_complete_synthetic_storage_admission_rechecks_every_new_record(admission):
    receipt = authenticate(admission)
    assert len(admission.values) == 108
    assert receipt == m._storage_receipt() and receipt['historical_d15_reused'] is False
    assert receipt['fresh_source_authenticated'] is receipt['new_storage_authenticated'] is True
    assert receipt['continuous_source_integrity_proven'] is False


@pytest.mark.parametrize('name', ['broker-report.json', 'worker-result.json', 'organization-binding.json',
    m.storage.REPORT, m.storage.ADMISSION])
def test_each_external_storage_pin_required_before_parse(admission, name):
    admission.values[name]['synthetic_extra'] = True
    with pytest.raises(m.Refused, match='input_admission'): authenticate(admission)


@pytest.mark.parametrize('name', ['parent-claim.json', 'worker-start.json', m.storage.CLAIM,
    'organization-0-intent.json', 'organization-1-observed.json', 'broker-00-intent.json',
    'broker-23-observed.json', 'plain-storage-00-intent.json', 'plain-storage-23-observed.json'])
def test_unpinned_census_records_are_not_accepted_by_name_alone(admission, name):
    # Exercise semantic census behind the five exact external file pins.
    if name.startswith('plain-storage-') and name not in admission.values:
        ordinal, kind = (0, 'intent') if '00-' in name else (23, 'observed')
        name = m.storage._stem(ordinal) + '-' + kind + '.json'
    admission.values[name]['synthetic_extra'] = True
    with pytest.raises((m.Refused, m.storage.PlainStorageError, admission.publication.Refused)): authenticate(admission)


@pytest.mark.parametrize('change', ['extra', 'missing', 'failed_verify', 'source_manifest', 'actual_exit'])
def test_whole_census_and_actual_exit_source_binding_are_mandatory(admission, change):
    if change == 'extra': admission.values['unrelated.json'] = {}
    elif change == 'missing': del admission.values['organization-0-intent.json']
    elif change == 'failed_verify': admission.directory.verify_failure = True
    elif change == 'source_manifest': admission.frozen['source_manifest_sha256'] = 'e' * 64
    else: admission.frozen['actual_exit'] = 2
    with pytest.raises((m.Refused, m.storage.PlainStorageError, admission.publication.Refused, RuntimeError, KeyError)):
        authenticate(admission)


@pytest.fixture
def leaf(tmp_path, monkeypatch):
    root = tmp_path / 'root'
    (root / 'artifacts').mkdir(parents=True)
    monkeypatch.setattr(m, 'ROOT', root)
    monkeypatch.setattr(m, 'CONTROL', root / 'artifacts' / 'plain-readiness' / 'fixed')
    return m.CONTROL


def test_new_store_exclusive_not_old_entrypoint(leaf):
    old = m.a3.CONTROL
    with m.Store(create=True) as store:
        pin = store.write('claim.json', {'synthetic': True})
        raw, record = store.read('claim.json')
        assert pin == {'sha256': m.sha(raw), 'byte_count': len(raw)} and record == {'synthetic': True}
        with m.Store(inherited=store.fd) as child: child.write('child.json', {})
        with pytest.raises(FileExistsError): store.write('claim.json', {})
    with pytest.raises(m.Refused): m.Store(create=True)
    assert m.a3.CONTROL == old


@pytest.fixture
def admission_leaf(tmp_path, monkeypatch):
    leaf = tmp_path / 'read-only'
    leaf.mkdir(mode=0o700)
    monkeypatch.setattr(m, 'STORAGE_CONTROL', leaf)
    monkeypatch.setattr(m._storage_module(), 'CONTROL', leaf)
    path = leaf / 'claim.json'
    path.write_bytes(b'{"synthetic":true}\n'); path.chmod(0o600)
    return leaf


def test_admission_store_holds_descriptors_and_exact_canonical_bytes(admission_leaf):
    with m.AdmissionStore() as store:
        assert store.read('claim.json') == {'synthetic': True}
        assert len(store.leaves) == 1 and store.names() == ('claim.json',)
        assert store.read_raw('claim.json') is store.leaves['claim.json'][2]
        store.verify()


@pytest.mark.parametrize('change', ['mode', 'hardlink', 'symlink', 'replace', 'inplace', 'directory', 'new_name'])
def test_admission_store_refuses_postopen_drift(admission_leaf, change):
    path = admission_leaf / 'claim.json'
    with m.AdmissionStore() as store:
        store.read('claim.json')
        if change == 'mode': path.chmod(0o644)
        elif change == 'hardlink': os.link(path, admission_leaf / 'second.json')
        elif change == 'symlink': path.rename(admission_leaf / 'old.json'); path.symlink_to('old.json')
        elif change == 'replace': path.rename(admission_leaf / 'old.json'); path.write_bytes(b'{}\n'); path.chmod(0o600)
        elif change == 'inplace': path.write_bytes(b'{"synthetic":false}\n')
        elif change == 'directory': path.unlink(); path.mkdir()
        else: (admission_leaf / 'extra.json').write_bytes(b'{}\n')
        with pytest.raises((m.Refused, OSError)): store.verify()


def test_native_policy_has_no_network_keychain_or_old_control_authority():
    assert '(deny network*)' in m.SANDBOX and '/usr/bin/security' in m.SANDBOX
    assert '/Library/Keychains' in m.SANDBOX and '/Users/sheltonchen/Library/Keychains' in m.SANDBOX
    assert all(str(path) in m.SANDBOX for path in m.OLD_CONTROLS)
    assert m.profile_record()['capacity_backtest_status_or_result_allowed'] is False


def test_new_selected_source_pins_match_public_bytes():
    pins = m.selected_pins()
    assert len(pins) >= 90
    for relative, digest in pins.items():
        assert m.sha((m.ROOT / relative).read_bytes()) == digest, relative


@pytest.fixture
def preflight(args, monkeypatch):
    raw = m.SOURCE.read_bytes()
    args.caller_sha256 = m.sha(raw)
    calls, changes = [], {}
    monkeypatch.setattr(m.v5, '_under_test', lambda: False)
    monkeypatch.setattr(environment, '_require_environment', lambda: None)
    monkeypatch.setattr(m, 'selected_pins', lambda: {'scripts/synthetic-source.py': 'd' * 64})
    def source(path):
        if path == m.SOURCE: return changes.get('caller_source', args.caller_sha256)
        if path.name == 'arv2_newrule_execution_environment.py':
            return m.v5.NEW_PINS['scripts/arv2_newrule_execution_environment.py']
        return changes.get('dependency', 'd' * 64)
    monkeypatch.setattr(m.helpers, '_source_digest', source)
    def git(command, deadline, limit=None):
        calls.append(command)
        if command == ['rev-parse', '--show-toplevel']: value = str(m.ROOT)
        elif command == ['branch', '--show-current']: value = m.frozen.BRANCH
        elif command == ['rev-parse', 'HEAD']: value = args.expected_head
        elif command == ['status', '--porcelain']: value = ''
        elif command[:2] == ['cat-file', '-s']: value = str(len(raw))
        elif command[:2] == ['cat-file', 'blob']: return changes.get('blob', raw)
        else: pytest.fail('unexpected git command')
        return changes.get(' '.join(command), value).encode('ascii')
    monkeypatch.setattr(m.v5, '_git', git)
    return NS(args=args, calls=calls, changes=changes)


def test_preflight_binds_exact_host_clean_head_and_source_blob(preflight):
    m._preflight(preflight.args, time.monotonic() + 800)
    assert preflight.calls[:4] == [['rev-parse', '--show-toplevel'], ['branch', '--show-current'],
        ['rev-parse', 'HEAD'], ['status', '--porcelain']]
    assert preflight.calls[-2:] == [['rev-parse', 'HEAD'], ['status', '--porcelain']]


@pytest.mark.parametrize('field,value', [('rev-parse --show-toplevel', '/wrong'),
    ('branch --show-current', 'main'), ('rev-parse HEAD', 'c' * 40),
    ('status --porcelain', ' M concurrent.py'), ('dependency', 'f' * 64),
    ('caller_source', 'f' * 64), ('blob', b'wrong source')])
def test_preflight_refuses_concurrent_context_or_source_change(preflight, field, value):
    preflight.changes[field] = value
    with pytest.raises(m.Refused): m._preflight(preflight.args, time.monotonic() + 800)


@pytest.mark.parametrize('field,value', [('expected_head', 'a' * 39), ('caller_sha256', False),
    ('control_fd', 3), ('deadline', 12.0), ('operation', 'launch')])
def test_preflight_refuses_unscoped_parent_arguments(preflight, field, value):
    setattr(preflight.args, field, value)
    with pytest.raises(m.Refused): m._preflight(preflight.args, time.monotonic() + 800)


@pytest.mark.parametrize('change', ['credential', 'fd', 'deadline', 'environment'])
def test_worker_preflight_never_accepts_credentials_or_unbound_context(preflight, monkeypatch, change):
    for name in tuple(os.environ): monkeypatch.delenv(name, raising=False)
    deadline = time.monotonic() + 800
    preflight.args.operation, preflight.args.control_fd, preflight.args.deadline = m.WORKERS[0], 3, deadline
    if change == 'credential': monkeypatch.setenv('QC_API_TOKEN', 'synthetic')
    elif change == 'environment': monkeypatch.setenv('UNEXPECTED', 'synthetic')
    elif change == 'fd': preflight.args.control_fd = True
    else: preflight.args.deadline -= 1
    with pytest.raises(m.Refused): m._preflight(preflight.args, deadline)
