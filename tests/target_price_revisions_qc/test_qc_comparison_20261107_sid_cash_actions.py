"""Prospective SID cash bytes and exact retained compile custody; synthetic I/O only."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sys
from pathlib import Path

import pytest

from research.target_price_revisions_qc import comparison_20261107_sid_cash_actions as m

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 7, 12, tzinfo=timezone.utc)
COMPILE_ID = 'synthetic-compile-frozen-arm'
KEYS = ('OFF', 'TPR050', 'TPR100', 'TPR200LONG', 'PURE')


@pytest.fixture(autouse=True)
def mac_only_native_custody(monkeypatch):
    # Same owner-selected boundary as the historical API fixtures: portable
    # pure checks remain active; POSIX custody is not Windows custody proof.
    if sys.platform != 'darwin':
        def custody(*_, **__):
            pytest.skip('Owner-selected Mac-only custody; POSIX no-follow/UID/mode/fsync is not Windows evidence')
        monkeypatch.setattr(m.api.ops, '_custody', custody)


@pytest.fixture(autouse=True)
def deny_native(monkeypatch):
    def deny(*_, **__):
        raise AssertionError('real credential/network/subprocess forbidden')
    monkeypatch.setattr(m.api.ops, 'credential', deny)
    monkeypatch.setattr(m.api.http.client, 'HTTPSConnection', deny)
    monkeypatch.setattr(m.api.subprocess, 'run', deny)


def public_sources():
    return {name: (ROOT/name).read_bytes() for name in m.REQUIRED_SOURCES}


def registry():
    return {'schema': 'tpr-cmp28-five-project-bindings-v1',
        'round_id': 'TPR-CMP28-R107-20261029A', 'owner_instruction_sha256': m.REGISTRY_CREATION_OWNER_SHA256,
        'git_head': 'a'*40, 'adapter_source_sha256': m.bundle.PROJECTS_SHA256,
        'organization_id': 'a'*32, 'owner_id': 123,
        'baseline_receipt_sha256': 'd'*64,
        'privacy_basis': 'documented_private_default_and_observed_collaborators',
        'explicit_privacy_flag_observed': False, 'independent_native_origin_attested': False,
        'projects': {key: {'project_id': m.api.REGISTERED_PROJECTS[key],
            'name': 'TPR-CMP28-R107-20261029A-'+key,
            'organization_id': 'a'*32, 'owner_id': 123, 'language': 'Py',
            'create_receipt_sha256': m._sha(('create-'+key).encode()),
            'read_receipt_sha256': m._sha(('read-'+key).encode()),
            'collaboration_receipt_sha256': m._sha(('collaborators-'+key).encode()),
            'collaborator_count': 1, 'nonowner_collaborator_count': 0,
            'collaborators_sha256': '9'*64} for key in KEYS}}


def common(arm='cap_off', operation='TPR-CMP29-API-SYNTHETIC-ACTION'):
    sources = public_sources()
    raw = m._wire(registry())
    spec = {'arm': arm, 'operation_id': 'TPR-CMP28-OFF-SID-CASH-20261107-SYNTHETIC' if arm == 'cap_off'
        else 'TPR-CMP28-SID-CASH-20261107-SYNTHETIC', 'attempt': 1,
        'prior_attempts_looks_sha256': 'e'*64, 'latest_owner_instruction_sha256': m.CURRENT_OWNER_SHA256}
    _, files, report, _ = m._candidate(sources, raw, m._sha(raw), spec)
    inventory = {name: {'bytes': len(value), 'sha256': m._sha(value)}
        for name, value in files.items()}
    inventory['research.ipynb'] = {'bytes': 3, 'sha256': m._sha(b'{}\n')}
    return dict(public_sources=sources, project_bindings_raw=raw,
        expected_project_bindings_sha256=m._sha(raw), financial_spec=spec,
        operation_id=operation, git_head='a'*40, owner_instruction_sha256=m.REGISTRY_CREATION_OWNER_SHA256,
        created_utc=(NOW-timedelta(seconds=1)).isoformat(),
        expires_utc=(NOW+timedelta(seconds=599)).isoformat(),
        attempt_id='synthetic-attempt-1', reserved_look_id='synthetic-look-1',
        source_inventory=inventory, mode='offline-fixture'), files, report


def clone(value):
    return json.loads(m._wire(value))


def raw_sources(files, project):
    rows = [{'name': name, 'content': value.decode(), 'projectId': project}
        for name, value in files.items()]
    rows.append({'name': 'research.ipynb', 'content': '{}\n', 'projectId': project})
    return {'success': True, 'projectId': project, 'files': rows}


def native_fixture(action, action_root, native_root, files, *, mutate=None, calls=None, clock=lambda: NOW):
    plan = action['api_plan']
    project = plan['project_id']
    binding = json.loads(plan['project_bindings_json'])
    owner = binding['owner_id']
    owner_actor = {'uid': owner, 'owner': True, 'permission': 'write', 'liveControl': True}
    def transport(endpoint, *_):
        if calls is not None:
            calls.append(endpoint)
        if endpoint == 'projects/read':
            body = {'success': True, 'projects': [{'projectId': project, 'ownerId': owner,
                'owner': True, 'organizationId': binding['organization_id'],
                'name': binding['projects'][plan['project_registration_key']]['name'],
                'language': 'Py', 'collaborators': [owner_actor]}]}
        elif endpoint == 'projects/collaboration/read':
            body = {'success': True, 'projectId': project, 'userPermissions': 'write',
                'collaborators': [owner_actor]}
        elif endpoint == 'backtests/list':
            body = {'success': True, 'backtests': [], 'count': 0}
        elif endpoint == 'files/read':
            body = raw_sources(files, project)
        elif endpoint == 'backtests/create':
            body = {'success': True, 'projectId': project, 'backtest': {'backtestId': '1'*32,
                'projectId': project}}
        else:
            body = {'success': True, 'projectId': project,
                'compileId': COMPILE_ID, 'state': 'BuildSuccess'}
        if mutate is not None:
            body = mutate(endpoint, body)
        return m.api._canonical(body), 200, 'SYNTHETIC-TOKEN', owner
    return m._dispatch_fixture(action, action_root, native_root,
        public_sources=public_sources(), transport=transport, clock=clock)


def native_evidence(tmp_path, opaque_mia=False):
    args, files, report = common(operation='TPR-CMP29-API-SYNTHETIC-COMPILE')
    backend_files = dict(files)
    if opaque_mia:
        backend_files['mia.ipynb'] = b'{"cells":[]}'
        args['source_inventory']['mia.ipynb'] = {
            'bytes': len(backend_files['mia.ipynb']), 'sha256': m._sha(backend_files['mia.ipynb'])}
    compile_action = m.prepare_compile(**args)
    native_root = tmp_path/'native'
    compiled = native_fixture(compile_action, tmp_path/'compile-actions', native_root, backend_files)
    assert compiled['status'] == 'completed'
    build_args = dict(args, operation_id='TPR-CMP29-API-SYNTHETIC-BUILD')
    build_action = m.prepare_build(**build_args, compile_id=COMPILE_ID)
    build_plan = build_action['api_plan']
    built = native_fixture(build_action, tmp_path/'build-actions', native_root, backend_files)
    assert built['status'] == 'completed'
    names = {
        'compile_plan': compile_action['api_plan']['operation_id']+'.operation.spent.json',
        'compile_result': compile_action['api_plan']['operation_id']+'.result.json',
        'source_before': compiled['requests'][3]['raw_response']['name'],
        'compile_response': compiled['requests'][4]['raw_response']['name'],
        'source_after': compiled['requests'][5]['raw_response']['name'],
        'build_plan': build_plan['operation_id']+'.operation.spent.json',
        'build_result': build_plan['operation_id']+'.result.json',
        'build_response': built['requests'][3]['raw_response']['name']}
    raws = {key: (native_root/name).read_bytes() for key, name in names.items()}
    deps = {key: {'name': names[key], 'bytes': len(raw), 'sha256': m._sha(raw)}
        for key, raw in raws.items()}
    args.update(operation_id='TPR-CMP29-API-SYNTHETIC-LAUNCH')
    action = m.prepare_launch(**args, compile_evidence=deps, compile_id=COMPILE_ID)
    return action, args['public_sources'], native_root, raws


@pytest.mark.parametrize('arm', tuple(m.api.PROJECT_KEYS))
def test_each_arm_regenerates_only_fixed_cash_config_files_and_project(arm):
    args, files, report = common(arm)
    action = m.prepare_compile(**args)
    expected_files, expected_report = m.cash_bundle.build_cash_candidate(
        public_sources={name: args['public_sources'][name] for name in m.cash_bundle.REQUIRED_SOURCES},
        project_bindings_raw=args['project_bindings_raw'],
        expected_project_bindings_sha256=args['expected_project_bindings_sha256'],
        **args['financial_spec'])
    assert files == expected_files
    assert report == json.loads(expected_report)
    assert report['source_epoch'] == m.cash_bundle.SOURCE_EPOCH
    assert report['study_id'] == m.STUDY_ID
    assert m._sha(expected_report) == action['candidate_report_sha256']
    assert files['main.py'].startswith(args['public_sources'][m.preflight.RECOVERY_PATH])
    assert b'class Main(CashExclusionMixin, ResourceRecoveryMixin,' in files['main.py']
    assert all(0 < len(raw) <= 60000 and raw.endswith(b'\n') and b'\r' not in raw
        for raw in files.values())
    assert action['api_plan']['project_id'] == m.api.REGISTERED_PROJECTS[m.api.PROJECT_KEYS[arm]]
    assert action['api_plan']['candidate_config_sha256'] == report['config_sha256']
    assert action['generated_source_hashes'] == report['cloud_source_hashes']
    assert action['generated_source_bytes'] == report['cloud_source_bytes']
    assert action['native_origin_authenticated'] is action['economics_accepted'] is False
    assert action['strategy_economics_changed'] is True
    assert m._validate(action, args['public_sources']) == action


def test_upload_is_generated_and_preserves_notebook_without_accepting_caller_hashes():
    args, files, _ = common()
    before = {'main.py': {'bytes': 4, 'sha256': m._sha(b'#old')},
        'research.ipynb': args['source_inventory']['research.ipynb']}
    action = m.prepare_upload(**args, before_inventory=before)
    writes = action['api_plan']['requests'][1:-1]
    assert len(writes) == len(files)
    assert {row['payload']['name']: row['payload']['content'].encode() for row in writes} == files
    assert all(row['payload']['name'] != 'research.ipynb' for row in writes)
    assert action['source_inventory']['research.ipynb'] == before['research.ipynb']
    assert action['private_reads_max'] == 0


@pytest.mark.parametrize('fault', ['fees0', 'arm', 'project', 'config_hash', 'allowed_hash',
    'noneconomic_flag', 'read_budget', 'unknown_phase'])
def test_changed_plan_cannot_relabel_frozen_economics_or_bypass_binding(fault):
    args, _, _ = common()
    before = {'main.py': {'bytes': 4, 'sha256': m._sha(b'#old')}}
    args['source_inventory'].pop('research.ipynb')
    action = m.prepare_upload(**args, before_inventory=before)
    if fault == 'fees0':
        row = next(row for row in action['api_plan']['requests']
            if row['endpoint'].startswith('files/') and row.get('payload', {}).get('name') == 'comparison_20261028_config.py')
        row['payload']['content'] = "CONFIG_JSON = '{\"fee_bps\":0}'\n"
        row['payload_sha256'] = m._sha(m._wire(row['payload']))
        action['api_plan']['allowed_source_hashes']['comparison_20261028_config.py'] = m._sha(row['payload']['content'].encode())
    elif fault == 'arm':
        action['financial_spec']['arm'] = 'cap_tilt_50'
    elif fault == 'project':
        action['api_plan']['project_id'] = m.api.REGISTERED_PROJECTS['TPR050']
    elif fault == 'config_hash':
        action['api_plan']['candidate_config_sha256'] = 'f'*64
    elif fault == 'allowed_hash':
        action['api_plan']['allowed_source_hashes']['main.py'] = 'f'*64
    elif fault == 'noneconomic_flag':
        action['financial_spec']['noneconomic_diagnostic'] = True
    elif fault == 'read_budget':
        action['private_reads_max'] = 1
    else:
        action['phase'] = 'noneconomic'
    with pytest.raises((m.ActionRefusal, m.api.APIRefusal)):
        m._validate(action, args['public_sources'])


@pytest.mark.parametrize('fault', ['unknown_extra', 'wrong_source', 'incomplete', 'bad_registry', 'bad_public_source'])
def test_unreviewed_extra_source_or_forged_binding_refuses(fault):
    args, _, _ = common()
    if fault == 'unknown_extra':
        args['source_inventory']['AlgorithmImports.py'] = {'bytes': 1, 'sha256': '1'*64}
    elif fault == 'wrong_source':
        args['source_inventory']['main.py']['sha256'] = '1'*64
    elif fault == 'incomplete':
        args['source_inventory'].pop('main.py')
    elif fault == 'bad_registry':
        body = registry();body['projects']['OFF']['project_id'] = 38000001
        args.update(project_bindings_raw=m._wire(body), expected_project_bindings_sha256=m._sha(m._wire(body)))
    else:
        args['public_sources'][m.BUNDLE_MODULE] += b'#unreviewed'
    with pytest.raises((m.ActionRefusal, m.api.APIRefusal)):
        m.prepare_compile(**args)


def test_compile_proof_binds_actual_generated_sources_and_successful_compile(tmp_path):
    action, _, _, raws = native_evidence(tmp_path)
    assert m._proof(action, raws)
    assert action['private_reads_max'] == 8
    assert action['private_bytes_max'] == sum(len(raw) for raw in raws.values())


def changed_raw(action, raws, key, body):
    raw = m._wire(body) if not isinstance(body, bytes) else body
    raws[key] = raw
    action['compile_evidence'][key].update(bytes=len(raw), sha256=m._sha(raw))
    return action, raws


@pytest.mark.parametrize('fault', ['foreign_compile', 'wrong_source', 'wrong_arm', 'wrong_project',
    'wrong_config', 'no_build_success', 'failed_compile', 'wrong_receipt_link',
    'wrong_descriptor_name', 'duplicate_json', 'changed_plan_sha', 'newer_compile_time'])
def test_foreign_stale_or_forged_compile_evidence_never_admits_launch(tmp_path, fault):
    action, _, _, raws = native_evidence(tmp_path)
    if fault == 'foreign_compile':
        action['compile_id'] = 'unrelated-old-compile'
    elif fault == 'wrong_source':
        body = json.loads(raws['source_after']);body['files'][0]['content'] = '#foreign'
        changed_raw(action, raws, 'source_after', body)
    elif fault in ('wrong_arm', 'wrong_project', 'wrong_config', 'newer_compile_time'):
        body = json.loads(raws['compile_plan'])
        if fault == 'wrong_arm':body['arm'] = 'pure_tpr'
        elif fault == 'wrong_project':body['project_id'] = m.api.REGISTERED_PROJECTS['PURE']
        elif fault == 'wrong_config':body['candidate_config_sha256'] = 'f'*64
        else:body['created_utc'] = (NOW+timedelta(seconds=1)).isoformat()
        changed_raw(action, raws, 'compile_plan', body)
    elif fault == 'no_build_success':
        body = json.loads(raws['build_response']);body['state'] = 'InQueue'
        changed_raw(action, raws, 'build_response', body)
    elif fault in ('failed_compile', 'wrong_receipt_link', 'changed_plan_sha'):
        body = json.loads(raws['compile_result'])
        if fault == 'failed_compile':body['status'] = 'failed_or_uncertain'
        elif fault == 'wrong_receipt_link':body['requests'][3]['raw_response']['sha256'] = 'f'*64
        else:body['plan_sha256'] = 'f'*64
        changed_raw(action, raws, 'compile_result', body)
    elif fault == 'wrong_descriptor_name':
        action['compile_evidence']['compile_plan']['name'] = 'another.operation.spent.json'
    else:
        changed_raw(action, raws, 'compile_response',
            b'{"success":true,"compileId":"one","compileId":"two","state":"BuildSuccess"}')
    with pytest.raises((m.ActionRefusal, m.api.APIRefusal)):
        m._proof(action, raws)


def test_production_requires_real_guard_native_api_and_committed_own_module(monkeypatch):
    args, _, _ = common()
    action = m.prepare_compile(**args)
    calls = []
    monkeypatch.setattr(m, '_load_sources', lambda _: calls.append('source') or args['public_sources'])
    with pytest.raises(m.ActionRefusal):
        m.execute_action(action)  # offline-fixture is never admitted by production
    assert calls == ['source']


def test_claim_precedes_each_compile_proof_read_and_only_then_dispatches(tmp_path, monkeypatch):
    action, sources, native_root, _ = native_evidence(tmp_path)
    root = tmp_path/'actions'
    original = m.api.ops.read_private
    reads = []
    def read(directory, name, maximum):
        assert directory == native_root
        assert (root/(action['api_plan']['operation_id']+'.action.spent.json')).exists()
        claims = list(root.glob('*.read.spent.json'))
        assert len(claims) == len(reads)+1
        reads.append(name)
        return original(directory, name, maximum)
    monkeypatch.setattr(m.api.ops, 'read_private', read)
    calls = []
    def execute(plan):
        assert len(reads) == 8
        calls.append(plan)
        return {'plan_sha256': m._sha(m.api._canonical(plan)), 'status': 'completed'}
    result = m._execute_fixture(action, root, native_root, public_sources=sources,
        api_execute=execute, clock=lambda: NOW)
    assert result['status'] == 'completed' and result['private_reads_attempted'] == 8
    assert result['private_bytes_read'] == action['private_bytes_max']
    assert len(result['dependency_claims']) == 8 and len(calls) == 1
    assert result['native_origin_authenticated'] is result['economics_accepted'] is False
    with pytest.raises(m.ActionRefusal):
        m._execute_fixture(action, root, native_root, public_sources=sources,
            api_execute=execute, clock=lambda: NOW)
    assert len(reads) == 8 and len(calls) == 1  # spent action never reopens proof


@pytest.mark.parametrize('fault', ['missing', 'same_name', 'oversize', 'traversal', 'under_budget'])
def test_closed_dependency_bounds_before_private_read(fault):
    args, _, _ = common()
    deps = {key: {'name': key+'.raw', 'bytes': 1, 'sha256': 'f'*64} for key in m.PROOF_KEYS}
    if fault == 'missing':deps.pop('compile_plan')
    elif fault == 'same_name':deps['build_result']['name'] = deps['compile_plan']['name']
    elif fault == 'oversize':deps['compile_plan']['bytes'] = m.MAX_INPUT_BYTES+1
    elif fault == 'traversal':deps['compile_plan']['name'] = '../foreign'
    else:
        action = m.prepare_launch(**args, compile_evidence=deps, compile_id=COMPILE_ID)
        action['private_reads_max'] -= 1
        with pytest.raises(m.ActionRefusal):m._validate(action, args['public_sources'])
        return
    with pytest.raises(m.ActionRefusal):
        m.prepare_launch(**args, compile_evidence=deps, compile_id=COMPILE_ID)


@pytest.mark.parametrize('kind', ['ordinary', 'cancel', 'fatal'])
def test_native_failure_or_cancellation_retains_body_free_honest_receipt(tmp_path, kind):
    args, _, _ = common()
    action = m.prepare_compile(**args)
    def execute(plan):
        if kind == 'ordinary':raise ValueError('PRIVATE-SECRET')
        report = {'status': 'cancelled' if kind == 'cancel' else 'failed_or_uncertain',
            'plan_sha256': m._sha(m.api._canonical(plan))}
        raise m.api.APICancelled(report) if kind == 'cancel' else m.api.APIFatal(report)
    if kind == 'ordinary':
        result = m._execute_fixture(action, tmp_path/'actions', tmp_path/'native',
            public_sources=args['public_sources'], api_execute=execute, clock=lambda: NOW)
    else:
        expected = m.ActionCancelled if kind == 'cancel' else m.ActionFatal
        with pytest.raises(expected) as stopped:
            m._execute_fixture(action, tmp_path/'actions', tmp_path/'native',
                public_sources=args['public_sources'], api_execute=execute, clock=lambda: NOW)
        result = stopped.value.report
    assert result['receipt_published'] is True
    assert result['status'] == ('cancelled' if kind == 'cancel' else 'failed_or_uncertain')
    assert 'PRIVATE-SECRET' not in json.dumps(result)


def test_final_receipt_failure_does_not_replace_first_cancellation(tmp_path, monkeypatch):
    args, _, _ = common();action = m.prepare_compile(**args)
    original = m.api._publish
    def publish(root, name, raw):
        if name.endswith('.result.json'):
            raise SystemExit('PRIVATE-RECEIPT-FAILURE')
        return original(root, name, raw)
    monkeypatch.setattr(m.api, '_publish', publish)
    def execute(plan):
        raise m.api.APICancelled({'status': 'cancelled',
            'plan_sha256': m._sha(m.api._canonical(plan))})
    with pytest.raises(m.ActionCancelled) as stopped:
        m._execute_fixture(action, tmp_path/'actions', tmp_path/'native',
            public_sources=args['public_sources'], api_execute=execute, clock=lambda: NOW)
    assert stopped.value.report['receipt_published'] is False
    assert stopped.value.report['status'] == 'cancelled'
    assert 'PRIVATE' not in json.dumps(stopped.value.report)


@pytest.mark.parametrize('kind', ['cancel', 'fatal'])
def test_uncertain_initial_claim_publication_exposes_no_private_body(tmp_path, monkeypatch, kind):
    args, _, _ = common();action = m.prepare_compile(**args)
    def publish(*_):
        raise KeyboardInterrupt('PRIVATE-CLAIM-ERROR') if kind == 'cancel' else SystemExit('PRIVATE-CLAIM-ERROR')
    monkeypatch.setattr(m.api, '_publish', publish)
    expected = m.ActionCancelled if kind == 'cancel' else m.ActionFatal
    calls = []
    with pytest.raises(expected) as stopped:
        m._execute_fixture(action, tmp_path/'actions', tmp_path/'native',
            public_sources=args['public_sources'], api_execute=lambda _: calls.append(True), clock=lambda: NOW)
    assert stopped.value.report['action_claim_published'] is None
    assert stopped.value.report['receipt_published'] is False
    assert stopped.value.report['status'] == ('cancelled' if kind == 'cancel' else 'failed_or_uncertain')
    assert stopped.value.report['private_reads_attempted'] == 0 and calls == []
    assert 'PRIVATE' not in str(stopped.value) and 'PRIVATE' not in json.dumps(stopped.value.report)


def test_expiry_during_claim_fsync_refuses_before_private_read(tmp_path, monkeypatch):
    action, sources, native_root, _ = native_evidence(tmp_path)
    original = m.api._publish;now = [NOW]
    def publish(root, name, raw):
        descriptor = original(root, name, raw)
        if name.endswith('.compile_plan.read.spent.json'):
            now[0] = NOW+timedelta(seconds=601)
        return descriptor
    monkeypatch.setattr(m.api, '_publish', publish)
    calls = []
    result = m._execute_fixture(action, tmp_path/'actions', native_root, public_sources=sources,
        api_execute=lambda _: calls.append('native'), clock=lambda: now[0])
    assert result['status'] == 'failed_or_uncertain'
    assert len(result['dependency_claims']) == 1
    assert result['private_reads_attempted'] == 0 and calls == []


def test_build_success_reader_must_keep_the_same_source_closure(tmp_path):
    action, _, _, raws = native_evidence(tmp_path)
    plan = json.loads(raws['build_plan'])
    plan['source_hashes'].pop(m.MODULE)  # remains valid for the legacy read-only API
    updated = m.api._validated(plan)
    result = json.loads(raws['build_result'])
    result['plan_sha256'] = m._sha(m.api._canonical(updated))
    changed_raw(action, raws, 'build_plan', updated)
    changed_raw(action, raws, 'build_result', result)
    with pytest.raises(m.ActionRefusal):m._proof(action, raws)


@pytest.mark.parametrize('filename', ('research.ipynb', 'mia.ipynb'))
def test_both_named_notebooks_are_preserved_opaque_and_never_written(filename):
    args, files, _ = common()
    opaque = {'bytes': 11, 'sha256': m._sha(b'{"cells":1}')}
    args['source_inventory'][filename] = opaque
    before = {'main.py': {'bytes': 4, 'sha256': m._sha(b'#old')},
        'research.ipynb': args['source_inventory']['research.ipynb'], filename: opaque}
    action = m.prepare_upload(**args, before_inventory=before)
    writes = action['api_plan']['requests'][1:-1]
    assert not ({row['payload']['name'] for row in writes} & m.OPAQUE_NOTEBOOKS)
    assert action['source_inventory'][filename] == before[filename]
    assert set(files).isdisjoint(m.OPAQUE_NOTEBOOKS)


@pytest.mark.parametrize('fault', ('changed', 'dropped', 'unknown.py', 'AlgorithmImports.py'))
def test_opaque_source_closure_drift_or_executable_extra_refuses(fault):
    args, _, _ = common()
    before = {'main.py': {'bytes': 4, 'sha256': m._sha(b'#old')},
        'research.ipynb': args['source_inventory']['research.ipynb'],
        'mia.ipynb': {'bytes': 2, 'sha256': m._sha(b'{}')}}
    args['source_inventory']['mia.ipynb'] = dict(before['mia.ipynb'])
    if fault == 'changed': args['source_inventory']['mia.ipynb']['sha256'] = '9'*64
    elif fault == 'dropped': args['source_inventory'].pop('mia.ipynb')
    else: args['source_inventory'][fault] = {'bytes': 1, 'sha256': 'a'*64}
    with pytest.raises(m.ActionRefusal):
        m.prepare_upload(**args, before_inventory=before)


@pytest.mark.parametrize('fault', ('none', 'changed', 'removed'))
def test_all_eight_compile_proofs_preserve_opaque_notebook_hashes(tmp_path, fault):
    action, _, _, raws = native_evidence(tmp_path, opaque_mia=True)
    assert action['private_reads_max'] == 8
    assert m._proof(action, raws)
    if fault == 'none':
        return
    body = json.loads(raws['source_after'])
    if fault == 'changed':
        next(row for row in body['files'] if row['name'] == 'mia.ipynb')['content'] = '{"cells":[1]}'
    else:
        body['files'] = [row for row in body['files'] if row['name'] != 'mia.ipynb']
    changed_raw(action, raws, 'source_after', body)
    with pytest.raises(m.ActionRefusal):
        m._proof(action, raws)


@pytest.mark.parametrize('field', ('operation_id', 'api_operation_id'))
@pytest.mark.parametrize('marker', ('OFFLINE', 'PREVIEW', 'offline', 'preview'))
def test_offline_preview_identities_never_become_actual_effect_plans(field, marker):
    args, _, _ = common()
    if field == 'operation_id':
        args['financial_spec']['operation_id'] = 'TPR-CMP28-OFF-' + marker + '-ONLY'
    else:
        args['operation_id'] = 'TPR-CMP29-API-' + marker + '-ONLY'
    assert args['financial_spec']['latest_owner_instruction_sha256'] != m.CURRENT_NO_QC_OWNER_SHA256
    with pytest.raises(m.ActionRefusal):
        m.prepare_compile(**args)


HOLD_DIRECTIVES = (
    ('when you are done, proceed to build until the last step of backtesing. do not access qc yet as another lane is using it. skip claude review. push only once',
     m.CURRENT_NO_QC_OWNER_SHA256),
    ('do not access qc/safari until further notice. continue to build',
     m.CURRENT_NO_QC_OR_SAFARI_OWNER_SHA256),
    ('investigate and fix the REMX data issues locally. keep QC and Safari untouched, skip Claude review, and push only once when done.',
     m.CURRENT_REMX_LOCAL_REPAIR_OWNER_SHA256),
    ('continue investigating and fix the remaining 20 REMX volume issues locally if possible. keep QC and Safari untouched, skip Claude review, and push only once when done.',
     m.CURRENT_REMX_FOLLOWUP_OWNER_SHA256),
    ('leave the 20 REMX rows quarantined and continue building locally up to the backtesting step. keep QC and Safari untouched, skip Claude review, and push only once when done.',
     m.CURRENT_LOCAL_PREBACKTEST_OWNER_SHA256),
)


@pytest.mark.parametrize('instruction,owner_sha256', HOLD_DIRECTIVES)
def test_current_explicit_no_qc_directive_is_denied_before_source_private_or_native_effect(
        tmp_path, monkeypatch, instruction, owner_sha256):
    args, _, _ = common()
    action = m.prepare_compile(**args)
    assert hashlib.sha256(instruction.encode('utf-8')).hexdigest() == owner_sha256
    assert owner_sha256 in m.BLOCKED_OWNER_INSTRUCTION_SHA256S
    action['financial_spec']['latest_owner_instruction_sha256'] = owner_sha256
    effects = []
    monkeypatch.setattr(m, '_load_sources', lambda *_: effects.append('public-source-load'))
    monkeypatch.setattr(m.api.ops, 'read_private', lambda *_: effects.append('private'))
    with pytest.raises(m.ActionRefusal):
        m.execute_action(action)
    assert effects == []
    with pytest.raises(m.ActionRefusal):
        m._execute_fixture(action, tmp_path/'actions', tmp_path/'native',
            public_sources=args['public_sources'], api_execute=lambda _: effects.append('native'),
            clock=lambda: NOW)
    assert effects == [] and not (tmp_path/'actions').exists()


@pytest.mark.parametrize('fault', ('missing', 'same_as_creation', 'invalid', 'current_no_qc', 'current_no_qc_or_safari'))
def test_latest_authority_is_separate_required_valid_and_cannot_be_current_deferral(fault):
    args, _, _ = common()
    if fault == 'missing': args['financial_spec'].pop('latest_owner_instruction_sha256')
    elif fault == 'same_as_creation':
        args['financial_spec']['latest_owner_instruction_sha256'] = args['owner_instruction_sha256']
    elif fault == 'invalid': args['financial_spec']['latest_owner_instruction_sha256'] = 'not-a-hash'
    elif fault == 'current_no_qc':
        args['financial_spec']['latest_owner_instruction_sha256'] = m.CURRENT_NO_QC_OWNER_SHA256
    else:
        args['financial_spec']['latest_owner_instruction_sha256'] = m.CURRENT_NO_QC_OR_SAFARI_OWNER_SHA256
    with pytest.raises(m.ActionRefusal):
        m.prepare_compile(**args)


def test_separate_owner_lineages_are_in_action_claim_and_result(tmp_path):
    args, _, _ = common()
    action = m.prepare_compile(**args)
    assert action['financial_spec']['latest_owner_instruction_sha256'] == m.CURRENT_OWNER_SHA256
    assert action['api_plan']['owner_instruction_sha256'] == m.REGISTRY_CREATION_OWNER_SHA256
    result = m._execute_fixture(action, tmp_path/'actions', tmp_path/'native',
        public_sources=args['public_sources'],
        api_execute=lambda plan: {'plan_sha256': m._sha(m.api._canonical(plan)), 'status': 'completed'},
        clock=lambda: NOW)
    assert result['latest_owner_instruction_sha256'] == m.CURRENT_OWNER_SHA256
    assert result['registry_creation_owner_instruction_sha256'] == m.REGISTRY_CREATION_OWNER_SHA256


def test_production_registry_is_exact_and_fixture_cannot_bypass_production_guard(monkeypatch):
    args, _, _ = common()
    args['mode'] = 'production'
    args['owner_instruction_sha256'] = m.REGISTRY_CREATION_OWNER_SHA256
    effects = []
    monkeypatch.setattr(m.api, 'prepare_plan', lambda **_: effects.append('api'))
    with pytest.raises(m.ActionRefusal):
        m.prepare_compile(**args)
    assert effects == []


@pytest.mark.parametrize('path', (m.PREFLIGHT_MODULE, m.preflight.RECOVERY_PATH))
def test_parent_source_producer_and_inline_helper_bytes_are_fixed(path):
    args, _, _ = common()
    args['public_sources'][path] += b'\n#unreviewed'
    with pytest.raises(m.ActionRefusal):
        m.prepare_compile(**args)


def test_frozen_legacy_epoch_cannot_be_relabelled_as_cash_variant():
    args, _, _ = common()
    packet = None
    frozen, _ = m.bundle.build_project_candidate(
        public_sources={name: args['public_sources'][name] for name in m.bundle.SOURCE_PATHS},
        project_binding_raw=args['project_bindings_raw'],
        expected_project_binding_sha256=args['expected_project_bindings_sha256'],
        arm='cap_off', operation_id=args['financial_spec']['operation_id'],
        attempt=args['financial_spec']['attempt'],
        prior_attempts_looks_sha256=args['financial_spec']['prior_attempts_looks_sha256'],
        signal_packet=packet)
    args['source_inventory'] = {
        name: {'bytes': len(raw), 'sha256': m._sha(raw)} for name, raw in frozen.items()}
    with pytest.raises(m.ActionRefusal):
        m.prepare_compile(**args)


@pytest.mark.parametrize('instruction,owner_sha256', HOLD_DIRECTIVES)
def test_all_local_hold_specs_refuse_before_operational_identity_processing(
        monkeypatch, instruction, owner_sha256):
    spec = {'arm': 'cap_off', 'operation_id': 'TPR-CMP28-OFF-SYNTHETIC-HOLD',
        'attempt': 1, 'prior_attempts_looks_sha256': 'e'*64,
        'latest_owner_instruction_sha256': owner_sha256}
    assert hashlib.sha256(instruction.encode('utf-8')).hexdigest() == owner_sha256
    reached = []
    monkeypatch.setattr(m, '_operational_id', lambda value: reached.append(value))
    with pytest.raises(m.ActionRefusal):
        m._spec(spec)
    assert reached == []


@pytest.mark.parametrize('instruction,owner_sha256', HOLD_DIRECTIVES)
@pytest.mark.parametrize('phase', ('upload', 'compile', 'launch'))
def test_all_local_holds_refuse_production_preparation_before_source_registry_or_api(
        monkeypatch, phase, instruction, owner_sha256):
    args, _, _ = common()
    # Satisfy the earlier metadata-only production envelope. These synthetic
    # bytes must never be parsed or used as a real registry under any hold.
    args.update(mode='production', owner_instruction_sha256=m.REGISTRY_CREATION_OWNER_SHA256,
        project_bindings_raw=b'x'*m.preflight.REGISTRY_BYTES,
        expected_project_bindings_sha256=m.preflight.REGISTRY_SHA256)
    args['financial_spec']['latest_owner_instruction_sha256'] = owner_sha256
    assert hashlib.sha256(instruction.encode('utf-8')).hexdigest() == owner_sha256
    effects = []
    sha = m._sha
    def source_hash(raw):
        effects.append('source-validation')
        return sha(raw)
    monkeypatch.setattr(m, '_sha', source_hash)
    monkeypatch.setattr(m.api.projects, 'validate_bindings',
        lambda *a, **k: effects.append('registry'))
    monkeypatch.setattr(m.api, 'prepare_plan', lambda **k: effects.append('api-plan'))
    monkeypatch.setattr(m, '_load_sources', lambda *a: effects.append('source-read'))
    monkeypatch.setattr(m.api.ops, 'read_private', lambda *a: effects.append('private'))
    monkeypatch.setattr(m.api, 'execute_plan', lambda *a: effects.append('native'))
    with pytest.raises(m.ActionRefusal):
        getattr(m, 'prepare_' + phase)(**args)
    assert effects == []

@pytest.mark.parametrize('fault', ('wrong', 'old', 'attempt4', 'old_id'))
def test_only_current_owner_variant_and_max_three_attempts_are_admitted(fault):
    args, _, _ = common()
    if fault == 'wrong':
        args['financial_spec']['latest_owner_instruction_sha256'] = '1'*64
    elif fault == 'old':
        args['financial_spec']['latest_owner_instruction_sha256'] = m.REGISTRY_CREATION_OWNER_SHA256
    elif fault == 'attempt4':
        args['financial_spec']['attempt'] = 4
    else:
        args['financial_spec']['operation_id'] = 'TPR-CMP28-OFF-FROZEN-OLD'
    with pytest.raises(m.ActionRefusal):
        m.prepare_compile(**args)


def test_known_public_helper_is_closed_exact_preserved_and_never_written():
    args, files, _ = common()
    name, descriptor = next(iter(m.KNOWN_PUBLIC_EXTRAS.items()))
    args['source_inventory'][name] = dict(descriptor)
    before = {'main.py': {'bytes': 4, 'sha256': m._sha(b'#old')},
        'research.ipynb': args['source_inventory']['research.ipynb'], name: dict(descriptor)}
    action = m.prepare_upload(**args, before_inventory=before)
    assert action['source_inventory'][name] == descriptor
    assert name not in {row['payload'].get('name') for row in action['api_plan']['requests']}
    assert name not in files


@pytest.mark.parametrize('where', ('before', 'after'))
@pytest.mark.parametrize('fault', ('bytes', 'sha256', 'unknown_name'))
def test_changed_or_unknown_public_helper_refuses_without_deleting(where, fault):
    args, _, _ = common()
    name, descriptor = next(iter(m.KNOWN_PUBLIC_EXTRAS.items()))
    args['source_inventory'][name] = dict(descriptor)
    before = {'main.py': {'bytes': 4, 'sha256': m._sha(b'#old')},
        'research.ipynb': args['source_inventory']['research.ipynb'], name: dict(descriptor)}
    target = before if where == 'before' else args['source_inventory']
    if fault == 'unknown_name':
        target['arbitrary_helper.py'] = target.pop(name)
    elif fault == 'bytes':
        target[name]['bytes'] += 1
    else:
        target[name]['sha256'] = '1'*64
    with pytest.raises(m.ActionRefusal):
        m.prepare_upload(**args, before_inventory=before)


@pytest.mark.parametrize('key', ('study_id', 'source_epoch', 'strategy_economics_changed'))
def test_action_variant_metadata_cannot_be_relabelled(key):
    args, _, _ = common()
    action = m.prepare_compile(**args)
    action[key] = False if key == 'strategy_economics_changed' else 'original-frozen-epoch'
    with pytest.raises(m.ActionRefusal):
        m._validate(action, args['public_sources'])


def test_source_has_no_broker_ml_or_dynamic_execution_boundary():
    import ast
    tree = ast.parse((ROOT/m.MODULE).read_bytes())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names]
            assert not any(name.split('.')[0] in {'assistant', 'execution', 'alpaca', 'ml', 'broker'}
                for name in names)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {'exec', 'eval', '__import__'}

def test_fixed_native_dispatch_has_fresh_preflight_then_exact_compile_sources(tmp_path):
    args, files, _ = common()
    action = m.prepare_compile(**args)
    calls = []
    result = native_fixture(action, tmp_path/'actions', tmp_path/'native', files, calls=calls)
    assert result['status'] == 'completed'
    assert result['schema'] == 'tpr-cmp1107-sid-cash-native-result-v1'
    assert calls == ['projects/read', 'projects/collaboration/read', 'backtests/list',
        'files/read', 'compile/create', 'files/read']
    assert result['preflight_complete'] and result['compile_requests_attempted'] == 1
    assert result['actual_new_backtests'] == 0
    assert result['native_origin_authenticated'] is result['economics_accepted'] is False
    assert result['strategy_economics_changed'] is True
    assert action['native_requests_max'] == len(calls)
    assert result['response_bytes'] <= action['native_response_bytes_max']


@pytest.mark.parametrize('fault', ('owner', 'org', 'public', 'foreign_actor', 'mia_unknown',
    'active', 'count', 'credential_echo'))
def test_fresh_private_owner_and_zero_active_jobs_refuse_before_mutation(tmp_path, fault):
    args, files, _ = common()
    action = m.prepare_compile(**args)
    calls = []
    def mutate(endpoint, body):
        if endpoint == 'projects/read':
            row = body['projects'][0]
            if fault == 'owner': row['ownerId'] += 1
            elif fault == 'org': row['organizationId'] = 'f'*32
            elif fault == 'public': row['isPublic'] = True
            elif fault == 'credential_echo': body['unsafe'] = 'SYNTHETIC-TOKEN'
        if endpoint == 'projects/collaboration/read':
            if fault == 'foreign_actor':
                body['collaborators'][0]['uid'] += 1
            elif fault == 'mia_unknown':
                body['collaborators'].append({'uid': None, 'owner': False, 'permission': 'write',
                    'liveControl': True, 'name': 'Mia', 'publicId': 'A-'+'1'*32})
        if endpoint == 'backtests/list':
            if fault == 'active':
                body.update(count=1, backtests=[{'backtestId': 'a'*32, 'completed': False,
                    'status': 'Running'}])
            elif fault == 'count':
                body['count'] = 1
        return body
    result = native_fixture(action, tmp_path/'actions', tmp_path/'native', files,
        calls=calls, mutate=mutate)
    assert result['status'] == 'failed_or_uncertain' and result['receipt_published']
    assert 'compile/create' not in calls and 'backtests/create' not in calls
    assert 'SYNTHETIC-TOKEN' not in json.dumps(result)
    if fault == 'credential_echo':
        assert not (tmp_path/'native'/(action['api_plan']['operation_id']+'.metadata.response.raw')).exists()


def test_fixed_dispatch_preserves_foreign_lock_and_spends_without_request(tmp_path):
    args, files, _ = common()
    action = m.prepare_compile(**args)
    root = tmp_path/'actions'
    root.mkdir(mode=0o700)
    lock = root/'comparison-api.lock'
    lock.write_bytes(b'foreign-operation')
    lock.chmod(0o600)
    calls = []
    result = native_fixture(action, root, tmp_path/'native', files, calls=calls)
    assert result['status'] == 'failed_or_uncertain'
    assert lock.read_bytes() == b'foreign-operation' and calls == []
    assert result['lock_cleanup_complete'] is False and result['receipt_published']
    with pytest.raises(m.ActionRefusal):
        native_fixture(action, root, tmp_path/'native', files, calls=calls)
    assert calls == [] and lock.read_bytes() == b'foreign-operation'


def test_fixed_dispatch_claim_is_exclusive_and_uncertainty_never_retries(tmp_path, monkeypatch):
    args, files, _ = common()
    action = m.prepare_compile(**args)
    original = m.api._publish
    def publish(root, name, raw):
        descriptor = original(root, name, raw)
        if name.endswith('.action.spent.json'):
            raise KeyboardInterrupt('PRIVATE-INTERRUPTION')
        return descriptor
    monkeypatch.setattr(m.api, '_publish', publish)
    calls = []
    with pytest.raises(m.ActionCancelled) as stopped:
        native_fixture(action, tmp_path/'actions', tmp_path/'native', files, calls=calls)
    assert calls == [] and stopped.value.report['private_reads_attempted'] == 0
    assert stopped.value.report['status'] == 'cancelled'
    assert 'PRIVATE' not in json.dumps(stopped.value.report)
    monkeypatch.setattr(m.api, '_publish', original)
    with pytest.raises(m.ActionRefusal):
        native_fixture(action, tmp_path/'actions', tmp_path/'native', files, calls=calls)
    assert calls == []


def test_fixed_launch_claims_all_eight_inputs_before_first_native_request_and_reserves(tmp_path, monkeypatch):
    action, _, native_root, raws = native_evidence(tmp_path)
    args, files, _ = common()
    root = tmp_path/'launch-actions'
    original = m._read_proof
    reads = []
    def read(directory, descriptor):
        assert directory == native_root
        claim = root/(action['api_plan']['operation_id']+'.'+m.PROOF_KEYS[len(reads)]+'.read.spent.json')
        assert claim.exists()
        reads.append(descriptor['name'])
        return original(directory, descriptor)
    monkeypatch.setattr(m, '_read_proof', read)
    calls = []
    def check_claims(endpoint, body):
        assert len(reads) == 8
        assert len(list(native_root.glob('*.launch.spent.json'))) == 3
        return body
    result = native_fixture(action, root, native_root, files, calls=calls, mutate=check_claims)
    assert result['status'] == 'completed' and result['private_reads_attempted'] == 8
    assert result['private_bytes_read'] == sum(map(len, raws.values()))
    assert result['actual_new_backtests'] == 1 and result['observed_new_backtest_ids'] == ['1'*32]
    assert len(result['launch_reservations']) == 3
    assert next(row for row in action['api_plan']['requests'] if row['id'] == 'launch')['payload']['backtestName'] == 'SID-CASH-20261107-OFF-A1'


def test_fixed_launch_conflicting_reservation_refuses_before_credentials(tmp_path):
    action, _, native_root, _ = native_evidence(tmp_path)
    args, files, _ = common()
    name = m._reservation_names(action)[1]
    (native_root/name).write_bytes(b'prior-reservation')
    (native_root/name).chmod(0o600)
    calls = []
    result = native_fixture(action, tmp_path/'launch-actions', native_root, files, calls=calls)
    assert result['status'] == 'failed_or_uncertain'
    assert result['private_reads_attempted'] == 8 and calls == []
    assert (native_root/name).read_bytes() == b'prior-reservation'
    assert len(result['launch_reservations']) == 1


def test_fixed_dispatch_rechecks_deadline_after_claim_fsync_before_credentials(tmp_path, monkeypatch):
    args, files, _ = common()
    action = m.prepare_compile(**args)
    original = m.api._publish
    now = [NOW]
    def publish(root, name, raw):
        descriptor = original(root, name, raw)
        if name.endswith('.metadata.request.spent.json'):
            now[0] = NOW+timedelta(seconds=590)
        return descriptor
    monkeypatch.setattr(m.api, '_publish', publish)
    calls = []
    result = native_fixture(action, tmp_path/'actions', tmp_path/'native', files,
        calls=calls, clock=lambda: now[0])
    assert result['status'] == 'failed_or_uncertain' and calls == []
    assert result['transport_calls_attempted'] == 0


def test_phase_duration_includes_three_embedded_preflight_requests():
    args, _, _ = common()
    args['expires_utc'] = (NOW+timedelta(seconds=65)).isoformat()
    with pytest.raises(m.ActionRefusal):
        m.prepare_compile(**args)


@pytest.mark.parametrize('fault', ('sources', 'requests', 'bytes'))
def test_native_bounds_and_sources_cannot_be_caller_expanded(fault):
    args, _, _ = common()
    action = m.prepare_compile(**args)
    if fault == 'sources':
        args['public_sources'][m.CASH_BUNDLE_MODULE] += b'#unreviewed'
    elif fault == 'requests':
        action['native_requests_max'] += 1
    else:
        action['native_response_bytes_max'] += 1
    with pytest.raises(m.ActionRefusal):
        m._validate(action, args['public_sources'])
