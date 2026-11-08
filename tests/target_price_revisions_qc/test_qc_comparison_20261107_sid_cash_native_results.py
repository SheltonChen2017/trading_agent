"""Fixed child verifier framing, retained native proof custody and synthetic I/O."""
from datetime import datetime, timedelta, timezone
import ast
import json
from pathlib import Path
import sys
import types

import pytest

from research.target_price_revisions_qc import comparison_20261107_sid_cash_native_results as m

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 7, 12, tzinfo=timezone.utc)
PARENT = 'a'*32
CHILD = 'c'*32
COMPILE = 'synthetic-native-reader-compile'


@pytest.fixture(autouse=True)
def deny_native(monkeypatch):
    def deny(*_, **__):
        raise AssertionError('real native credential/network/subprocess forbidden')
    monkeypatch.setattr(m.ops, 'credential', deny)
    monkeypatch.setattr(m.api.http.client, 'HTTPSConnection', deny)
    monkeypatch.setattr(m.api.subprocess, 'run', deny)
    if sys.platform != 'darwin':
        def custody(*_, **__):
            pytest.skip('Owner-selected Mac-only native filesystem custody')
        monkeypatch.setattr(m.ops, '_custody', custody)


def sources():
    required = m.financial.REQUIRED_SOURCES | m.results.REQUIRED_SOURCES | {m.MODULE, m.results.MODULE, m.status.MODULE}
    return {name: (ROOT/name).read_bytes() for name in required}


def registry():
    return {'schema': 'tpr-cmp28-five-project-bindings-v1', 'round_id': 'TPR-CMP28-R107-20261029A',
        'owner_instruction_sha256': m.financial.REGISTRY_CREATION_OWNER_SHA256,
        'git_head': 'a'*40, 'adapter_source_sha256': m.cash_bundle.bundle.PROJECTS_SHA256,
        'organization_id': 'a'*32, 'owner_id': 123, 'baseline_receipt_sha256': 'd'*64,
        'privacy_basis': 'documented_private_default_and_observed_collaborators',
        'explicit_privacy_flag_observed': False, 'independent_native_origin_attested': False,
        'projects': {key: {'project_id': project, 'name': 'TPR-CMP28-R107-20261029A-'+key,
            'organization_id': 'a'*32, 'owner_id': 123, 'language': 'Py',
            'create_receipt_sha256': m._sha(('create-'+key).encode()),
            'read_receipt_sha256': m._sha(('read-'+key).encode()),
            'collaboration_receipt_sha256': m._sha(('collaborators-'+key).encode()),
            'collaborator_count': 1, 'nonowner_collaborator_count': 0,
            'collaborators_sha256': '9'*64} for key, project in m.api.REGISTERED_PROJECTS.items()}}


def terminal_wire(project):
    return m._wire({'success': True, 'projectId': project,
        'backtest': {'backtestId': PARENT, 'projectId': project, 'completed': True, 'status': 'Completed'}})


def terminal_projection(project):
    return m._wire(m.status.project_status(terminal_wire(project), credential='SYNTHETIC-TOKEN',
        project_id=project, backtest_id=PARENT))


def common(arm='cap_off', operation='TPR-SID-CASH-NATIVE-20261107-SYNTHETIC-COMPILE'):
    public = sources()
    raw = m._wire(registry())
    spec = {'arm': arm, 'operation_id': ('TPR-CMP28-OFF-' if arm == 'cap_off' else 'TPR-CMP28-')+
        'SID-CASH-20261107-SYNTHETIC', 'attempt': 1, 'prior_attempts_looks_sha256': 'e'*64,
        'latest_owner_instruction_sha256': m.cash_bundle.OWNER_SHA256}
    project = m.api.REGISTERED_PROJECTS[m.api.PROJECT_KEYS[arm]]
    terminal = terminal_projection(project)
    native_spec = {'financial_spec': spec, 'parent_job_id': PARENT,
        'terminal_evidence_sha256': m._sha(terminal), 'index_descriptor': {'bytes': 100, 'sha256': 'f'*64},
        'operation_id': 'TPR-SID-CASH-RESULTS-20261107-SYNTHETIC', 'git_head': 'a'*40}
    files, report_raw = m.build_native_candidate(public_sources=public,
        project_bindings_raw=raw, expected_project_bindings_sha256=m._sha(raw), **native_spec)
    parent_files, _ = m.cash_bundle.build_cash_candidate(
        public_sources={name: public[name] for name in m.cash_bundle.REQUIRED_SOURCES},
        project_bindings_raw=raw, expected_project_bindings_sha256=m._sha(raw), **spec)
    inventory = {name: {'bytes': len(value), 'sha256': m._sha(value)}
        for name, value in {**parent_files, **files}.items()}
    inventory['research.ipynb'] = {'bytes': 3, 'sha256': m._sha(b'{}\n')}
    args = dict(public_sources=public, project_bindings_raw=raw,
        expected_project_bindings_sha256=m._sha(raw), native_spec=native_spec,
        parent_terminal_evidence={'name': 'synthetic-parent-terminal.response.raw',
            'bytes': len(terminal), 'sha256': m._sha(terminal)},
        operation_id=operation, created_utc=(NOW-timedelta(seconds=1)).isoformat(),
        expires_utc=(NOW+timedelta(seconds=599)).isoformat(),
        source_inventory=inventory, attempt_id='synthetic-reader-attempt-1',
        reserved_look_id='synthetic-reader-look-1', mode='offline-fixture')
    return args, files, parent_files, terminal, json.loads(report_raw)


def fixture(action, args, files, root, native_root, parent_root, *, mutate=None, calls=None, clock=lambda: NOW, log_lines=None):
    parent_root.mkdir(mode=0o700, exist_ok=True)
    descriptor = action['parent_terminal_evidence']
    path = parent_root/descriptor['name']
    if not path.exists():
        project = action['api_plan']['project_id']
        path.write_bytes(terminal_projection(project))
        path.chmod(0o600)
    plan = action['api_plan']
    binding = json.loads(plan['project_bindings_json'])
    project, owner = plan['project_id'], binding['owner_id']
    actor = {'uid': owner, 'owner': True, 'permission': 'write', 'liveControl': True}
    def transport(endpoint, request_raw, *_):
        payload = json.loads(request_raw)
        if calls is not None:
            calls.append(endpoint)
        if endpoint == 'projects/read':
            body = {'success': True, 'projects': [{'projectId': project, 'ownerId': owner,
                'owner': True, 'organizationId': binding['organization_id'], 'language': 'Py',
                'name': binding['projects'][plan['project_registration_key']]['name'], 'collaborators': [actor]}]}
        elif endpoint == 'projects/collaboration/read':
            body = {'success': True, 'userPermissions': 'write', 'collaborators': [actor]}
        elif endpoint == 'backtests/list':
            body = {'success': True, 'backtests': [], 'count': 0}
        elif endpoint == 'backtests/read':
            body = json.loads(terminal_wire(project))
            body['backtest']['backtestId'] = payload['backtestId']
        elif endpoint == 'backtests/read/log':
            body = {'success': True, 'projectId': project, 'backtestId': CHILD,
                'logs': log_lines, 'length': len(log_lines)}
        elif endpoint == 'files/read':
            body = {'success': True, 'projectId': project, 'files': [
                {'name': name, 'projectId': project, 'content': raw.decode('ascii')} for name, raw in files.items()]+[
                {'name': 'research.ipynb', 'projectId': project, 'content': '{}\n'}]}
        elif endpoint == 'backtests/create':
            body = {'success': True, 'backtest': {'backtestId': CHILD, 'projectId': project}}
        else:
            body = {'success': True, 'projectId': project, 'compileId': COMPILE, 'state': 'BuildSuccess'}
        if mutate is not None:
            body = mutate(endpoint, body)
        return body if type(body) is bytes else m._wire(body), 200, 'SYNTHETIC-TOKEN', owner
    return m._execute_fixture(action, root, native_root, parent_root,
        public_sources=args['public_sources'], transport=transport, clock=clock)


def evidence(tmp_path):
    args, child, parent, _, _ = common()
    deployed = {**parent, **child}
    compiled_action = m.prepare_compile(**args)
    native_root, parent_root = tmp_path/'native', tmp_path/'parent'
    compiled = fixture(compiled_action, args, deployed, tmp_path/'compile', native_root, parent_root)
    assert compiled['status'] == 'completed'
    build_args = dict(args, operation_id='TPR-SID-CASH-NATIVE-20261107-SYNTHETIC-BUILD',
        attempt_id=None, reserved_look_id=None)
    built_action = m.prepare_build(**build_args, compile_id=COMPILE)
    built = fixture(built_action, build_args, deployed, tmp_path/'build', native_root, parent_root)
    assert built['status'] == 'completed'
    names = {'compile_plan': args['operation_id']+'.operation.spent.json',
        'compile_result': args['operation_id']+'.result.json',
        'source_before': compiled['requests'][4]['raw_response']['name'],
        'compile_response': compiled['requests'][5]['raw_response']['name'],
        'source_after': compiled['requests'][6]['raw_response']['name'],
        'build_plan': build_args['operation_id']+'.operation.spent.json',
        'build_result': build_args['operation_id']+'.result.json',
        'build_response': built['requests'][4]['raw_response']['name']}
    raws = {key: (native_root/name).read_bytes() for key, name in names.items()}
    deps = {key: {'name': names[key], 'bytes': len(raw), 'sha256': m._sha(raw)} for key, raw in raws.items()}
    args.update(operation_id='TPR-SID-CASH-NATIVE-20261107-SYNTHETIC-LAUNCH')
    launch = m.prepare_launch(**args, compile_evidence=deps, compile_id=COMPILE)
    return launch, args, deployed, native_root, parent_root, raws


@pytest.mark.parametrize('arm', tuple(m.api.PROJECT_KEYS))
def test_five_arm_exact_reader_generation_keeps_journal_and_sid_out_of_sources(arm):
    args, files, _, _, report = common(arm)
    assert set(files) == {'main.py', m.REPLAY_MODULE, m.PREFIX+'_primitives.py', m.PREFIX+'_metadata.py'}
    assert all(0 < len(raw) <= 60000 and b'\r' not in raw and raw.endswith(b'\n') for raw in files.values())
    assert report['one_of_five_economic_arms'] is report['strategy_accepted'] is False
    assert report['parent_job_id'] == PARENT
    assert report['project_id'] == m.api.REGISTERED_PROJECTS[m.api.PROJECT_KEYS[arm]]
    assert report['raw_journal_or_sid_exported'] is False
    assert b'getattr(self' not in files['main.py']
    assert m._validate(m.prepare_compile(**args), args['public_sources'])['source_epoch'] == m.SOURCE_EPOCH


def test_upload_retains_all_financial_files_notebooks_and_exact_known_helper():
    args, child, parent, _, _ = common()
    helper, descriptor = next(iter(m.financial.KNOWN_PUBLIC_EXTRAS.items()))
    before = {name: {'bytes': len(raw), 'sha256': m._sha(raw)} for name, raw in parent.items()}
    before.update({'research.ipynb': args['source_inventory']['research.ipynb'], helper: dict(descriptor)})
    args['source_inventory'][helper] = dict(descriptor)
    action = m.prepare_upload(**args, before_inventory=before)
    writes = action['api_plan']['requests'][1:-1]
    assert {row['payload']['name']: row['payload']['content'].encode('ascii') for row in writes} == child
    assert helper not in {row['payload']['name'] for row in writes}
    assert 'research.ipynb' not in {row['payload']['name'] for row in writes}
    assert action['source_inventory'][helper] == before[helper]


@pytest.mark.parametrize('fault', ('owner', 'old_study', 'parent_job', 'terminal', 'source', 'unknown_extra', 'helper', 'deadline'))
def test_wrong_source_parent_owner_epoch_and_unreviewed_extras_refuse(fault):
    args, _, _, _, _ = common()
    if fault == 'owner':
        args['native_spec']['financial_spec']['latest_owner_instruction_sha256'] = '1'*64
    elif fault == 'old_study':
        args['native_spec']['financial_spec']['operation_id'] = 'TPR-CMP28-OFF-FROZEN'
    elif fault == 'parent_job':
        args['native_spec']['parent_job_id'] = 'not-a-native-job'
    elif fault == 'terminal':
        args['native_spec']['terminal_evidence_sha256'] = '1'*64
    elif fault == 'source':
        args['public_sources'][m.results.MODULE] += b'#unreviewed'
    elif fault == 'unknown_extra':
        args['source_inventory']['unknown.py'] = {'bytes': 1, 'sha256': '1'*64}
    elif fault == 'helper':
        name, row = next(iter(m.financial.KNOWN_PUBLIC_EXTRAS.items()))
        args['source_inventory'][name] = {**row, 'sha256': '1'*64}
    else:
        args['expires_utc'] = (NOW+timedelta(seconds=60)).isoformat()
    with pytest.raises(m.ActionRefusal):
        m.prepare_compile(**args)


def test_native_compile_has_fresh_private_owner_jobs_parent_and_source_checks(tmp_path):
    args, child, parent, _, _ = common()
    action = m.prepare_compile(**args)
    calls = []
    result = fixture(action, args, {**parent, **child}, tmp_path/'actions', tmp_path/'native',
        tmp_path/'parent', calls=calls)
    assert result['status'] == 'completed'
    assert result['private_reads_attempted'] == 1 and result['preflight_complete']
    assert calls == ['projects/read', 'projects/collaboration/read', 'backtests/list',
        'backtests/read', 'files/read', 'compile/create', 'files/read']
    assert result['one_of_five_economic_arms'] is result['financial_outcome_look'] is False


@pytest.mark.parametrize('fault', ('private_parent', 'running_parent', 'wrong_owner', 'active_job', 'credential_echo'))
def test_parent_or_native_preflight_failure_refuses_before_compile(tmp_path, fault):
    args, child, parent, _, _ = common()
    action = m.prepare_compile(**args)
    parent_root = tmp_path/'parent'
    parent_root.mkdir(mode=0o700)
    if fault == 'private_parent':
        path = parent_root/action['parent_terminal_evidence']['name']
        path.write_bytes(b'FOREIGN-PRIVATE-RAW')
        path.chmod(0o600)
    def mutate(endpoint, body):
        if fault == 'running_parent' and endpoint == 'backtests/read':
            body['backtest']['completed'] = False
            body['backtest']['status'] = 'Running'
        elif fault == 'wrong_owner' and endpoint == 'projects/read':
            body['projects'][0]['ownerId'] += 1
        elif fault == 'active_job' and endpoint == 'backtests/list':
            body.update(count=1, backtests=[{'backtestId': 'b'*32, 'completed': False, 'status': 'Running'}])
        elif fault == 'credential_echo' and endpoint == 'projects/read':
            body['private'] = 'SYNTHETIC-TOKEN'
        return body
    calls = []
    result = fixture(action, args, {**parent, **child}, tmp_path/'actions', tmp_path/'native',
        parent_root, mutate=mutate, calls=calls)
    assert result['status'] == 'failed_or_uncertain' and result['receipt_published']
    assert 'compile/create' not in calls and 'backtests/create' not in calls
    assert 'FOREIGN-PRIVATE' not in json.dumps(result) and 'SYNTHETIC-TOKEN' not in json.dumps(result)


def test_all_eight_fixed_compile_proofs_are_required_before_child_launch(tmp_path, monkeypatch):
    action, args, deployed, native_root, parent_root, raws = evidence(tmp_path)
    assert m._proof(action, raws)
    original = m._read_proof
    reads = []
    root = tmp_path/'launch'
    def read(directory, descriptor):
        if directory == native_root:
            key = m.PROOF_KEYS[len(reads)]
            assert (root/(action['api_plan']['operation_id']+'.'+key+'.read.spent.json')).exists()
            reads.append(key)
        return original(directory, descriptor)
    monkeypatch.setattr(m, '_read_proof', read)
    def mutate(endpoint, body):
        assert reads == list(m.PROOF_KEYS)
        return body
    result = fixture(action, args, deployed, root, native_root, parent_root, mutate=mutate)
    assert result['status'] == 'completed' and result['private_reads_attempted'] == 9
    assert result['actual_new_backtests'] == 1 and result['observed_new_backtest_ids'] == [CHILD]
    assert len(result['launch_reservations']) == 3


@pytest.mark.parametrize('key', ('compile_plan', 'compile_result', 'source_before', 'compile_response',
    'source_after', 'build_plan', 'build_result', 'build_response'))
def test_each_retained_proof_hash_corruption_refuses(tmp_path, key):
    action, _, _, _, _, raws = evidence(tmp_path)
    raws[key] += b'\n'
    with pytest.raises(m.ActionRefusal):
        m._proof(action, raws)


def test_foreign_lock_survives_and_spent_action_never_retries(tmp_path):
    args, child, parent, _, _ = common()
    action = m.prepare_compile(**args)
    root = tmp_path/'actions'
    root.mkdir(mode=0o700)
    lock = root/'comparison-api.lock'
    lock.write_bytes(b'foreign-lock')
    lock.chmod(0o600)
    calls = []
    result = fixture(action, args, {**parent, **child}, root, tmp_path/'native', tmp_path/'parent', calls=calls)
    assert result['status'] == 'failed_or_uncertain' and calls == [] and lock.read_bytes() == b'foreign-lock'
    with pytest.raises(m.ActionRefusal):
        fixture(action, args, {**parent, **child}, root, tmp_path/'native', tmp_path/'parent', calls=calls)
    assert calls == []


def test_no_dynamic_execution_broker_private_packet_or_credential_path_in_cloud_source():
    args, files, _, _, _ = common()
    for raw in files.values():
        tree = ast.parse(raw)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {'exec', 'eval', 'compile', '__import__', 'open'}
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                assert not any(alias.name.split('.')[0] in {'alpaca', 'execution', 'broker', 'ml', 'requests', 'socket', 'subprocess'}
                    for alias in node.names)
    assert b'object_store.read_bytes' in files['main.py']
    assert b'object_store.save_bytes' in files['main.py']
    assert b'backtests/orders/read' not in files['main.py']


def test_runtime_claims_before_reads_and_sanitizes_all_private_rows(monkeypatch):
    args, _, _, _, _ = common()
    native = args['native_spec']
    _, parent_files, parent, _ = m.financial._candidate(
        {name: args['public_sources'][name] for name in m.financial.REQUIRED_SOURCES},
        args['project_bindings_raw'], args['expected_project_bindings_sha256'], native['financial_spec'])
    prefix = ('tpr-cmp28/evidence/'+m.cash_bundle.STUDY_ID+'/'+native['financial_spec']['operation_id']+
        '/'+parent['config_sha256']+'/attempt-1/'+str(parent['project_id'])+'/'+PARENT+'/')
    chunk = m._wire({'ordinal': 1, 'kind': 'SUMMARY', 'payload': {'private': 'RAW_PRIVATE_SYNTHETIC_SID'}})+b'\n'
    descriptor = {'key': prefix+'chunk-0000.jsonl', 'bytes': len(chunk), 'sha256': m._sha(chunk)}
    index = m._wire({'chunks': [descriptor]})
    native['index_descriptor'] = {'bytes': len(index), 'sha256': m._sha(index)}
    files, _ = m.build_native_candidate(public_sources=args['public_sources'],
        project_bindings_raw=args['project_bindings_raw'],
        expected_project_bindings_sha256=args['expected_project_bindings_sha256'], **native)
    fake = types.ModuleType('AlgorithmImports')
    class ClockRules:
        def every_day(self, *_): return None
        def at(self, *_): return None
        def on(self, *_): return None
    class Algorithm:
        def __init__(self):
            self.live_mode = False
            self.project_id = parent['project_id']
            self.algorithm_id = CHILD
            self.locked = False
            self.date_rules = self.time_rules = self.schedule = ClockRules()
            self.logged = []
        def get_locked(self): return self.locked
        def set_time_zone(self, *_): pass
        def set_start_date(self, *_): pass
        def set_end_date(self, *_): pass
        def add_equity(self, *_args, **_kwargs): return types.SimpleNamespace(symbol=object())
        def set_benchmark(self, *_): pass
        def log(self, value): self.logged.append(value)
    fake.QCAlgorithm = Algorithm
    fake.Resolution = types.SimpleNamespace(MINUTE=object())
    fake.DataNormalizationMode = types.SimpleNamespace(RAW=object())
    helper = types.ModuleType(m.REPLAY_MODULE[:-3])
    helper.canonical_summary = lambda row: m._wire(row)
    helper.make_binding = lambda *_: {}
    config_raw = m.cash_bundle._wire(m.cash_bundle.preflight._config(parent_files['comparison_20261028_config.py']))
    source_raw = args['public_sources'][m.cash_bundle.PREFIX+'extended_calendar.json']
    calendar = m.cash_bundle.bundle.off._calendar(source_raw, parent['policy_sha256'])
    calendar['study_id'] = m.cash_bundle.STUDY_ID
    helper.get_public_envelopes = lambda: (config_raw, m.cash_bundle._wire(calendar), source_raw)
    helper.validate_completion = lambda *_args, **_kwargs: {'safe': True}
    helper.chunk_replay_plan = lambda *_args, **_kwargs: [{'ordinal': 0, **descriptor}]
    helper.replay_chunks = lambda *_args, **_kwargs: {'replayed': True}
    helper.audit_evidence = lambda *_args, **_kwargs: {'native_accounting': True, 'strategy_accepted': False,
        'safe_aggregate_note': 'bounded aggregate '*750}
    monkeypatch.setitem(sys.modules, 'AlgorithmImports', fake)
    monkeypatch.setitem(sys.modules, m.REPLAY_MODULE[:-3], helper)
    scope = {}
    exec(compile(files['main.py'], 'synthetic-main.py', 'exec'), scope)
    algorithm = scope['Main']()
    algorithm.initialize()
    private = {prefix+'index.json': index, descriptor['key']: chunk}
    events = []
    class Store:
        def contains_key(self, key):
            events.append(('contains', key))
            return key in private
        def save_bytes(self, key, raw):
            events.append(('save', key))
            private[key] = raw
            return True
        def read_bytes(self, key):
            events.append(('read', key))
            if key in (prefix+'index.json', descriptor['key']):
                assert events[-3][0] == 'save'
                assert events[-2][0] == 'read'
            return private[key]
    algorithm.object_store = Store()
    algorithm.locked = True
    algorithm._audit()
    algorithm.on_end_of_algorithm()
    assert algorithm._report['status'] == 'completed_private_native_accounting_replay'
    assert algorithm._report['private_reads'] == 2
    assert algorithm._report['claims_same_node_verified'] == 4
    assert len(algorithm.logged) > 8
    assert all(len(line.encode('ascii')) <= 3000 for line in algorithm.logged)
    assert all('RAW_PRIVATE_SYNTHETIC_SID' not in line for line in algorithm.logged)
    assembled = m.reassemble_result_frames(algorithm.logged,
        expected_operation_id=native['operation_id'], expected_reader_config_sha256=algorithm._frozen_hash,
        expected_parent_job_id=PARENT, expected_child_job_id=CHILD)
    assert assembled['status'] == 'completed_private_native_accounting_replay'
    assert len(m._wire(assembled)) > 8192
    assert assembled['strategy_accepted'] is False

def test_large_terminal_wire_is_fully_validated_but_only_metadata_is_retained(tmp_path):
    args, child, parent, _, _ = common()
    action = m.prepare_compile(**args)
    marker = 'RAW-SYNTHETIC-NATIVE-SID-DO-NOT-RETAIN'
    def mutate(endpoint, body):
        if endpoint == 'backtests/read':
            body['discardedOrders'] = [0]*5000
            body['discardedPrivateRows'] = marker*30000
        return body
    result = fixture(action, args, {**parent, **child}, tmp_path/'actions', tmp_path/'native',
        tmp_path/'parent', mutate=mutate)
    assert result['status'] == 'completed'
    row = next(row for row in result['requests'] if row['id'] == 'parent_terminal')
    assert row['projection']['original_wire_bytes'] > 1024*1024
    assert row['projection']['raw_wire_retained'] is False
    assert row['raw_response']['name'].endswith('.parent_terminal.projection.json')
    assert row['raw_response']['bytes'] < 4096
    for path in (tmp_path/'native').iterdir():
        assert marker.encode() not in path.read_bytes()


def test_discarded_terminal_field_decoded_credential_echo_is_refused_before_any_retention(tmp_path):
    args, child, parent, _, _ = common()
    action = m.prepare_compile(**args)
    def mutate(endpoint, body):
        if endpoint == 'backtests/read':
            raw = m._wire(body)[:-1]
            return raw + br',"discarded":"\u0053YNTHETIC-TOKEN"}'
        return body
    calls = []
    result = fixture(action, args, {**parent, **child}, tmp_path/'actions', tmp_path/'native',
        tmp_path/'parent', mutate=mutate, calls=calls)
    assert result['status'] == 'failed_or_uncertain'
    assert 'compile/create' not in calls
    assert not list((tmp_path/'native').glob('*.parent_terminal.projection.json'))
    assert 'SYNTHETIC-TOKEN' not in json.dumps(result)

def frames_for_raw(raw, *, reader_config_sha256='f'*64,
        operation_id='TPR-SID-CASH-RESULTS-20261107-SYNTHETIC'):
    count = (len(raw)+999)//1000
    result = []
    for number in range(count):
        frame = {'schema': 'tpr-sid-cash-native-results-chunk-v1', 'source_epoch': m.SOURCE_EPOCH,
            'operation_id': operation_id, 'reader_config_sha256': reader_config_sha256,
            'parent_job_id': PARENT, 'actual_child_job_id': CHILD, 'ordinal': number, 'count': count,
            'report_bytes': len(raw), 'report_sha256': m._sha(raw),
            'payload': raw[number*1000:(number+1)*1000].decode('ascii')}
        result.append(m.RESULT_PREFIX+m._wire(frame).decode('ascii'))
    return result


def frames(target_bytes=12000):
    report = {'schema': 'tpr-sid-cash-native-results-report-v1', 'source_epoch': m.SOURCE_EPOCH,
        'operation_id': 'TPR-SID-CASH-RESULTS-20261107-SYNTHETIC', 'reader_config_sha256': 'f'*64,
        'parent_job_id': PARENT, 'actual_child_job_id': CHILD, 'status': 'completed_private_native_accounting_replay',
        'root_head': 'a'*40, 'parent_config_sha256': '1'*64,
        'parent_terminal_evidence_sha256': '2'*64, 'completion_report': {'padding': ''},
        'accounting_report': None, 'completed_read_replay': True, 'completed_accounting_processing': True,
        'end_runtime_custody': True, 'claims_same_node_verified': 4,
        'private_reads': 2, 'private_bytes': 500, 'clock_bars': 900,
        'source_inputs_admitted': False, 'strategy_accepted': False, 'canonical_admission': False,
        'one_of_five_economic_arms': False, 'financial_outcome_look': False,
        'raw_journal_or_sid_exported': False, 'native_origin_authenticated': False,
        'backend_durability_proven': False, 'accepted_performance': None,
        'independent_engine_equity_chart_observed': False, 'external_parent_terminal_binding_only': True,
        'atomic_parent_child_snapshot_proven': False, 'sdk_hard_timeout_proven': False,
        'sdk_preallocation_byte_bound_proven': False}
    assert set(report) == m.NORMAL_REPORT_KEYS
    report['completion_report']['padding'] = 'x'*(target_bytes-len(m._wire(report)))
    raw = m._wire(report)
    assert len(raw) == target_bytes
    return frames_for_raw(raw), report


def assemble(lines):
    return m.reassemble_result_frames(lines,
        expected_operation_id='TPR-SID-CASH-RESULTS-20261107-SYNTHETIC',
        expected_reader_config_sha256='f'*64, expected_parent_job_id=PARENT, expected_child_job_id=CHILD)


@pytest.mark.parametrize('target_bytes', (1600, 2000, 2001, 8193, 12000, 32768))
def test_plain_ascii_result_frames_reassemble_exactly_and_keep_each_line_bounded(target_bytes):
    lines, report = frames(target_bytes)
    assert len(lines) <= 33 and all(len(line.encode('ascii')) <= 3000 for line in lines)
    assert assemble(lines) == report
    assert assemble([line.encode('ascii') for line in reversed(lines)]) == report
    assert report['strategy_accepted'] is False


@pytest.mark.parametrize('fault', ('missing', 'duplicate', 'truncated_json', 'payload', 'whole_hash',
    'count', 'ordinal', 'length', 'operation', 'config', 'parent', 'child', 'epoch',
    'extra', 'non_ascii', 'oversize_line', 'single_unframed'))
def test_incomplete_forged_or_mixed_result_frames_never_reassemble(fault):
    lines, _ = frames()
    frame = json.loads(lines[0][len(m.RESULT_PREFIX):])
    if fault == 'missing':
        lines.pop()
    elif fault == 'duplicate':
        lines[-1] = lines[0]
    elif fault == 'truncated_json':
        lines[-1] = lines[-1][:-1]
    elif fault == 'oversize_line':
        lines[0] += ' '*3000
    elif fault == 'single_unframed':
        lines = ['TPR_SID_CASH_NATIVE_RESULTS '+m._wire({'strategy_accepted': False}).decode('ascii')]
    else:
        if fault == 'payload': frame['payload'] = 'y'+frame['payload'][1:]
        elif fault == 'whole_hash': frame['report_sha256'] = '1'*64
        elif fault == 'count': frame['count'] += 1
        elif fault == 'ordinal': frame['ordinal'] = True
        elif fault == 'length': frame['report_bytes'] += 1
        elif fault == 'operation': frame['operation_id'] += '-FOREIGN'
        elif fault == 'config': frame['reader_config_sha256'] = '1'*64
        elif fault == 'parent': frame['parent_job_id'] = 'b'*32
        elif fault == 'child': frame['actual_child_job_id'] = 'b'*32
        elif fault == 'epoch': frame['source_epoch'] = 'original-frozen-study'
        elif fault == 'extra': frame['unreviewed'] = True
        elif fault == 'non_ascii': frame['payload'] = chr(233)+frame['payload'][1:]
        lines[0] = m.RESULT_PREFIX+m._wire(frame).decode('ascii')
    with pytest.raises(m.ActionRefusal):
        assemble(lines)


@pytest.mark.parametrize('where', ('key', 'value'))
@pytest.mark.parametrize('escaped', (False, True))
def test_native_sid_data_cannot_be_hidden_by_coherent_whole_frame_hash_rebinding(where, escaped):
    _, report = frames(1600)
    if where == 'key':
        report['completion_report'] = {'FAKE R1234567890123456789': 0}
    else:
        report['completion_report'] = {'value': 'FAKE R1234567890123456789'}
    raw = m._wire(report)
    if escaped:
        raw = raw.replace(b'FAKE R1234567890123456789', br'\u0046AKE R1234567890123456789')
    with pytest.raises(m.ActionRefusal):
        assemble(frames_for_raw(raw))


@pytest.mark.parametrize('token', (b'NaN', b'Infinity', b'-Infinity', b'1e999', b'1.0'))
def test_nonfinite_or_binary_float_report_values_refuse_after_coherent_hashes(token):
    _, report = frames(1600)
    report['completion_report'] = {'probe': '__NATIVE_NUMBER__'}
    raw = m._wire(report).replace(b'"__NATIVE_NUMBER__"', token)
    with pytest.raises(m.ActionRefusal):
        assemble(frames_for_raw(raw))


@pytest.mark.parametrize('fault', ('depth', 'nodes', 'extra_top', 'missing_top', 'wrong_derived_authority'))
def test_decoded_report_bounds_and_exact_generated_schemas_refuse(fault):
    _, report = frames(1600)
    if fault == 'depth':
        nested = 0
        for _ in range(m.MAX_REPORT_DEPTH+1):
            nested = [nested]
        report['completion_report'] = {'nested': nested}
    elif fault == 'nodes':
        report['completion_report'] = {'rows': [0]*m.MAX_REPORT_NODES}
    elif fault == 'extra_top':
        report['arbitrary_top_level_payload'] = True
    elif fault == 'missing_top':
        report.pop('root_head')
    else:
        report['sdk_hard_timeout_proven'] = True
    raw = m._wire(report)
    assert len(raw) <= 32768
    with pytest.raises(m.ActionRefusal):
        assemble(frames_for_raw(raw))


def test_exact_safe_error_report_schema_remains_non_authoritative():
    _, normal = frames(1600)
    report = {key: value for key, value in normal.items() if key in m.SAFE_ERROR_REPORT_KEYS}
    report['status'] = 'safe_report_bound_refused'
    assert set(report) == m.SAFE_ERROR_REPORT_KEYS
    assert assemble(frames_for_raw(m._wire(report))) == report

def bind_observe_fixture(action, report):
    """Synthetic own aggregates use the fixed producer's complete field contracts."""
    plan, expected = action['api_plan'], action['api_plan']['parent_expected']
    padding = report['completion_report'].get('padding', '')
    report.update(root_head=plan['git_head'], parent_config_sha256=expected['config_sha256'],
        parent_terminal_evidence_sha256=plan['terminal_evidence_sha256'])
    common = {key: expected[key] for key in ('study_id', 'candidate_id', 'arm',
        'operation_id', 'attempt', 'project_id', 'config_sha256')}
    common.update(job_id=plan['parent_job_id'], accepted_performance=None)
    false_common = ('native_origin_authenticated', 'backend_durability_proven',
        'source_inputs_admitted', 'historical_pit_authenticated', 'data_rights_authenticated',
        'native_permission', 'strategy_accepted', 'canonical_admission', 'full_evidence_retrieval_verified',
        'frozen_constructor_inputs_independently_reconstructed', 'runtime_census_is_native_authentication')
    common.update({key: False for key in false_common})
    completion = {key: None for key in m.COMPLETION_REPORT_KEYS}
    completion.update(common, schema='tpr-sid-cash-completion-framing-report-v1',
        terminal_completed_as_supplied=True, terminal_evidence_sha256=plan['terminal_evidence_sha256'],
        index_sha256=action['native_spec']['index_descriptor']['sha256'],
        source_template_closure_sha256=expected['source_template_closure_sha256'],
        rendered_source_closure_sha256=expected['rendered_source_closure_sha256'],
        warmup_proof_independently_replayed=False, independent_order_fill_action_cash_reconciliation=False,
        summary_sha256='d'*64, reported_nav_metrics={'synthetic_aggregate_padding': padding})
    accounting = {key: None for key in m.ACCOUNTING_REPORT_KEYS}
    accounting.update(common, schema='tpr-sid-cash-supplied-accounting-report-v1',
        journal_index_sha256=action['native_spec']['index_descriptor']['sha256'],
        api_input_binding_sha256=None, ordered_api_envelopes_sha256=None,
        engine_chart_agreement_pending=True, strategy_economics_changed=True,
        terminal_history_source='typed native parent OrderTicket snapshots retained in private journal')
    for key in ('engine_chart_observed', 'native_chart_rounding_agreement',
            'native_order_current_quantity_used_for_replay', 'native_order_price_used_for_replay',
            'share_basis_authenticated', 'raw_api_pages_revalidated_in_child',
            'exact_journal_to_event_id_mapping_proven', 'original_strategy_intent_verified',
            'moo_order_type_verified', 'cancellation_policy_verified', 'slippage_model_verified',
            'native_execution_timing_verified', 'normalizer_source_custody_verified',
            'original_frozen_study_resolved', 'external_native_api_crosscheck_performed',
            'native_ticket_average_price_recomputed', 'native_ticket_average_price_used_for_cash_or_nav'):
        accounting[key] = False
    report['completion_report'], report['accounting_report'] = completion, accounting
    return report


def observe_common():
    args, child, parent, _, _ = common(operation='TPR-SID-CASH-NATIVE-20261107-SYNTHETIC-OBSERVE')
    args.update(attempt_id=None, reserved_look_id='synthetic-outcome-processing-look-1')
    action = m.prepare_observe(**args, child_job_id=CHILD)
    _, report = frames(12000)
    report['reader_config_sha256'] = action['api_plan']['candidate_config_sha256']
    report['operation_id'] = action['native_spec']['operation_id']
    report = bind_observe_fixture(action, report)
    lines = frames_for_raw(m._wire(report), reader_config_sha256=report['reader_config_sha256'],
        operation_id=report['operation_id'])
    return args, action, {**parent, **child}, lines, report


def test_fixed_observe_reads_exact_child_once_and_retains_only_reassembled_aggregate(tmp_path):
    args, action, deployed, lines, report = observe_common()
    prefixed = ['2021-01-04 16:01:00 : '+line for line in lines]
    prefixed.append('DISCARDED-UNMATCHED-SYNTHETIC-NOISE')
    calls = []
    result = fixture(action, args, deployed, tmp_path/'observe', tmp_path/'native',
        tmp_path/'parent', calls=calls, log_lines=prefixed)
    assert result['status'] == 'completed'
    assert calls.count('backtests/read/log') == 1 and 'backtests/create' not in calls
    assert calls == ['projects/read', 'projects/collaboration/read', 'backtests/list',
        'backtests/read', 'files/read', 'backtests/read', 'backtests/read/log', 'files/read']
    log_request = next(row for row in action['api_plan']['requests'] if row['id'] == 'result_log')
    assert log_request['payload'] == {'projectId': action['api_plan']['project_id'],
        'backtestId': CHILD, 'start': 0, 'end': 34, 'query': 'TPR_SID_CASH_NATIVE_RESULTS_CHUNK'}
    assert result['aggregate_report'] == report
    assert result['outcome_processing_looks_completed'] == 1 and result['financial_outcome_looks_count'] == 1
    assert result['outcome_processing_look_claim'] is not None
    assert result['aggregate_report']['strategy_accepted'] is False
    native = tmp_path/'native'
    assert json.loads((native/result['observed_result_report']['name']).read_bytes()) == report
    assert json.loads((native/result['observed_result_frames']['name']).read_bytes()) == lines
    for path in native.iterdir():
        assert b'DISCARDED-UNMATCHED-SYNTHETIC-NOISE' not in path.read_bytes()
        assert b'2021-01-04 16:01:00 :' not in path.read_bytes()
    assert not list(native.glob('*.result_log.response.raw'))
    with pytest.raises(m.ActionRefusal):
        fixture(action, args, deployed, tmp_path/'observe', native, tmp_path/'parent', log_lines=prefixed)


@pytest.mark.parametrize('fault', ('missing', 'duplicate', 'count_mismatch', 'overflow', 'wrong_child',
    'foreign_config', 'long_prefix', 'control_prefix', 'twice_marker', 'non_ascii', 'raw_credential',
    'double_escaped_credential', 'decoded_sid', 'source_after'))
def test_observe_failure_never_retains_frames_report_or_raw_log_body(tmp_path, fault):
    args, action, deployed, lines, report = observe_common()
    if fault == 'missing':
        lines.pop()
    elif fault == 'duplicate':
        lines[-1] = lines[0]
    elif fault == 'overflow':
        lines = lines+[lines[0]]*(34-len(lines))
    elif fault == 'foreign_config':
        report['reader_config_sha256'] = '1'*64
        lines = frames_for_raw(m._wire(report))
    elif fault == 'long_prefix':
        lines[0] = 'x'*513+lines[0]
    elif fault == 'control_prefix':
        lines[0] = '\t'+lines[0]
    elif fault == 'twice_marker':
        lines[0] = m.RESULT_PREFIX+lines[0]
    elif fault == 'non_ascii':
        lines[0] = chr(233)+lines[0]
    elif fault in ('raw_credential', 'double_escaped_credential', 'decoded_sid'):
        value = 'FAKE R1234567890123456789' if fault == 'decoded_sid' else 'SYNTHETIC-TOKEN'
        report['completion_report']['reported_nav_metrics'] = {'value': value}
        raw = m._wire(report)
        if fault == 'double_escaped_credential':
            raw = raw.replace(b'SYNTHETIC-TOKEN', br'\u0053YNTHETIC-TOKEN')
        if fault == 'decoded_sid':
            raw = raw.replace(b'FAKE R1234567890123456789', br'\u0046AKE R1234567890123456789')
        lines = frames_for_raw(raw, reader_config_sha256=action['api_plan']['candidate_config_sha256'])
    seen_files = [0]
    def mutate(endpoint, body):
        if fault == 'count_mismatch' and endpoint == 'backtests/read/log':
            body['length'] += 1
        if fault == 'wrong_child' and endpoint == 'backtests/read/log':
            body['backtestId'] = 'b'*32
        if fault == 'source_after' and endpoint == 'files/read':
            seen_files[0] += 1
            if seen_files[0] == 2:
                body['files'][0]['content'] += '#foreign'
        return body
    calls = []
    result = fixture(action, args, deployed, tmp_path/'observe', tmp_path/'native',
        tmp_path/'parent', mutate=mutate, calls=calls, log_lines=lines)
    assert result['status'] == 'failed_or_uncertain'
    assert result['observed_result_frames'] is result['observed_result_report'] is result['aggregate_report'] is None
    assert result['outcome_processing_looks_completed'] == 0
    assert calls.count('backtests/read/log') <= 1 and 'backtests/create' not in calls
    assert not list((tmp_path/'native').glob('*.aggregate-*.json'))
    assert not list((tmp_path/'native').glob('*.result_log.response.raw'))
    assert 'SYNTHETIC-TOKEN' not in json.dumps(result)


@pytest.mark.parametrize('fault', ('query', 'range', 'child', 'source_hash', 'payload_override'))
def test_observe_is_fixed_and_cannot_become_generic_log_export(fault):
    args, action, _, _, _ = observe_common()
    row = next(row for row in action['api_plan']['requests'] if row['id'] == 'result_log')
    if fault == 'query':
        row['payload']['query'] = ''
    elif fault == 'range':
        row['payload']['end'] = 200
    elif fault == 'child':
        row['payload']['backtestId'] = PARENT
    elif fault == 'source_hash':
        action['api_plan']['source_hashes'][m.MODULE] = '1'*64
    else:
        action['native_spec']['upload_body'] = 'CALLER-SOURCE'
    with pytest.raises(m.ActionRefusal):
        m._validate(action, args['public_sources'])


def test_observe_processing_look_is_spent_before_native_request_and_preserved_on_uncertainty(tmp_path):
    args, action, deployed, lines, _ = observe_common()
    native = tmp_path/'native'
    native.mkdir(mode=0o700)
    name = 'observe-look-'+m._sha(action['api_plan']['reserved_look_id'].encode('ascii'))+'.spent.json'
    (native/name).write_bytes(b'prior-uncertain-outcome-look')
    (native/name).chmod(0o600)
    calls = []
    result = fixture(action, args, deployed, tmp_path/'observe', native, tmp_path/'parent',
        calls=calls, log_lines=lines)
    assert result['status'] == 'failed_or_uncertain' and calls == []
    assert (native/name).read_bytes() == b'prior-uncertain-outcome-look'

@pytest.fixture(scope='module')
def observed_lineage_case():
    args, action, _, _, report = observe_common()
    return args, action, report


@pytest.mark.parametrize('field', ('root_head', 'parent_config_sha256', 'parent_terminal_evidence_sha256'))
def test_coherently_rehashed_wrong_root_parent_metadata_refuses(observed_lineage_case, field):
    _, action, original = observed_lineage_case
    report = json.loads(m._wire(original))
    report[field] = 'b'*40 if field == 'root_head' else '1'*64
    lines = frames_for_raw(m._wire(report), reader_config_sha256=action['api_plan']['candidate_config_sha256'])
    raw = m._wire({'success': True, 'logs': lines, 'length': len(lines)})
    with pytest.raises(m.ActionRefusal):
        m._capture_result_log(raw, credential='SYNTHETIC-TOKEN', action=action)


@pytest.mark.parametrize('nested', ('completion_report', 'accounting_report'))
@pytest.mark.parametrize('field', ('schema', 'study_id', 'candidate_id', 'arm', 'operation_id',
    'attempt', 'project_id', 'job_id', 'config_sha256', 'native_origin_authenticated',
    'strategy_accepted', 'accepted_performance', 'unknown_field'))
def test_coherent_foreign_nested_report_or_authority_never_captures(observed_lineage_case, nested, field):
    _, action, original = observed_lineage_case
    report = json.loads(m._wire(original))
    if field in ('native_origin_authenticated', 'strategy_accepted'):
        report[nested][field] = True
    elif field in ('attempt', 'project_id'):
        report[nested][field] += 1
    elif field == 'accepted_performance':
        report[nested][field] = {'CAGR': '999'}
    else:
        report[nested][field] = 'foreign-or-original-study'
    lines = frames_for_raw(m._wire(report), reader_config_sha256=action['api_plan']['candidate_config_sha256'])
    raw = m._wire({'success': True, 'logs': lines, 'length': len(lines)})
    with pytest.raises(m.ActionRefusal):
        m._capture_result_log(raw, credential='SYNTHETIC-TOKEN', action=action)


@pytest.mark.parametrize('nested,field,value', (
    ('completion_report', 'terminal_evidence_sha256', '1'*64),
    ('completion_report', 'index_sha256', '1'*64),
    ('completion_report', 'source_template_closure_sha256', '1'*64),
    ('completion_report', 'rendered_source_closure_sha256', '1'*64),
    ('completion_report', 'summary_sha256', 'not-a-hash'),
    ('accounting_report', 'journal_index_sha256', '1'*64),
    ('accounting_report', 'api_input_binding_sha256', '1'*64),
    ('accounting_report', 'ordered_api_envelopes_sha256', '1'*64),
    ('accounting_report', 'engine_chart_observed', True),
    ('accounting_report', 'engine_chart_agreement_pending', False),
    ('accounting_report', 'moo_order_type_verified', True),
    ('accounting_report', 'external_native_api_crosscheck_performed', True)))
def test_coherent_stale_nested_closure_or_unproved_crosscheck_refuses(observed_lineage_case, nested, field, value):
    _, action, original = observed_lineage_case
    report = json.loads(m._wire(original))
    report[nested][field] = value
    lines = frames_for_raw(m._wire(report), reader_config_sha256=action['api_plan']['candidate_config_sha256'])
    raw = m._wire({'success': True, 'logs': lines, 'length': len(lines)})
    with pytest.raises(m.ActionRefusal):
        m._capture_result_log(raw, credential='SYNTHETIC-TOKEN', action=action)


def test_observe_expected_parent_context_is_regenerated_not_caller_selected(observed_lineage_case):
    args, original, _ = observed_lineage_case
    action = json.loads(m._wire(original))
    action['api_plan']['parent_expected']['config_sha256'] = '1'*64
    with pytest.raises(m.ActionRefusal):
        m._validate(action, args['public_sources'])

@pytest.mark.parametrize('fault', ('read_false', 'account_false', 'both_false_present', 'both_false_none_success',
    'read_false_none', 'non_bool', 'true_missing', 'unknown_status', 'safe_error_success'))
def test_observed_success_and_report_presence_are_exactly_consistent(observed_lineage_case, fault):
    _, action, original = observed_lineage_case
    report = json.loads(m._wire(original))
    if fault == 'read_false':
        report['completed_read_replay'] = False
    elif fault == 'account_false':
        report['completed_accounting_processing'] = False
    elif fault == 'both_false_present':
        report.update(completed_read_replay=False, completed_accounting_processing=False)
    elif fault == 'both_false_none_success':
        report.update(completed_read_replay=False, completed_accounting_processing=False,
            completion_report=None, accounting_report=None)
    elif fault == 'read_false_none':
        report.update(completed_read_replay=False, completion_report=None)
    elif fault == 'non_bool':
        report['completed_read_replay'] = 1
    elif fault == 'true_missing':
        report['accounting_report'] = None
    elif fault == 'unknown_status':
        report['status'] = 'unreviewed_success'
    else:
        report = {key: value for key, value in report.items() if key in m.SAFE_ERROR_REPORT_KEYS}
        report['status'] = 'completed_private_native_accounting_replay'
    lines = frames_for_raw(m._wire(report), reader_config_sha256=action['api_plan']['candidate_config_sha256'])
    raw = m._wire({'success': True, 'logs': lines, 'length': len(lines)})
    with pytest.raises(m.ActionRefusal):
        m._capture_result_log(raw, credential='SYNTHETIC-TOKEN', action=action)


@pytest.mark.parametrize('mode', ('negative_empty', 'negative_retained', 'end_custody_false', 'safe_error'))
def test_observed_legitimate_negative_or_final_custody_failure_remains_non_authoritative(observed_lineage_case, mode):
    _, action, original = observed_lineage_case
    report = json.loads(m._wire(original))
    if mode == 'negative_empty':
        report.update(status='private_read_or_native_replay_refused',
            completed_read_replay=False, completed_accounting_processing=False,
            completion_report=None, accounting_report=None, end_runtime_custody=False)
    elif mode == 'negative_retained':
        report['status'] = 'clock_bar_bound_refused'
    elif mode == 'end_custody_false':
        report['end_runtime_custody'] = False
    else:
        report = {key: value for key, value in report.items() if key in m.SAFE_ERROR_REPORT_KEYS}
        report['status'] = 'safe_report_bound_refused'
    lines = frames_for_raw(m._wire(report), reader_config_sha256=action['api_plan']['candidate_config_sha256'])
    raw = m._wire({'success': True, 'logs': lines, 'length': len(lines)})
    captured = m._capture_result_log(raw, credential='SYNTHETIC-TOKEN', action=action)
    assert captured['report'] == report
    assert captured['report']['strategy_accepted'] is False and captured['report']['accepted_performance'] is None
