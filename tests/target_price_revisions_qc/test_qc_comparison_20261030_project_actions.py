"""Frozen financial bytes and exact retained compile custody; synthetic I/O only."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sys
from pathlib import Path

import pytest

from research.target_price_revisions_qc import comparison_20261030_project_actions as m

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
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
        'round_id': 'TPR-CMP28-R107-20261029A', 'owner_instruction_sha256': 'b'*64,
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
    spec = {'arm': arm, 'operation_id': 'TPR-CMP28-OFF-CR33-SYNTHETIC' if arm == 'cap_off'
        else 'TPR-CMP28-CR33-SYNTHETIC', 'attempt': 5,
        'prior_attempts_looks_sha256': 'e'*64}
    _, files, report, _ = m._candidate(sources, raw, m._sha(raw), spec)
    inventory = {name: {'bytes': len(value), 'sha256': m._sha(value)}
        for name, value in files.items()}
    inventory['research.ipynb'] = {'bytes': 3, 'sha256': m._sha(b'{}\n')}
    return dict(public_sources=sources, project_bindings_raw=raw,
        expected_project_bindings_sha256=m._sha(raw), financial_spec=spec,
        operation_id=operation, git_head='a'*40, owner_instruction_sha256='b'*64,
        created_utc=(NOW-timedelta(seconds=1)).isoformat(),
        expires_utc=(NOW+timedelta(seconds=599)).isoformat(),
        attempt_id='synthetic-attempt-5', reserved_look_id='synthetic-look-5',
        source_inventory=inventory, mode='offline-fixture'), files, report


def clone(value):
    return json.loads(m._wire(value))


def raw_sources(files, project):
    rows = [{'name': name, 'content': value.decode(), 'projectId': project}
        for name, value in files.items()]
    rows.append({'name': 'research.ipynb', 'content': '{}\n', 'projectId': project})
    return {'success': True, 'projectId': project, 'files': rows}


def native_fixture(plan, native_root, files, *, build=False):
    project = plan['project_id']
    def transport(endpoint, *_):
        if endpoint == 'files/read':
            body = raw_sources(files, project)
        else:
            body = {'success': True, 'projectId': project,
                'compileId': COMPILE_ID, 'state': 'BuildSuccess'}
        return m.api._canonical(body), 200, 'SYNTHETIC-TOKEN'
    return m.api._execute_fixture(plan, native_root,
        transport=transport, clock=lambda: NOW)


def native_evidence(tmp_path):
    args, files, report = common(operation='TPR-CMP29-API-SYNTHETIC-COMPILE')
    compile_action = m.prepare_compile(**args)
    native_root = tmp_path/'native'
    compiled = native_fixture(compile_action['api_plan'], native_root, files)
    assert compiled['status'] == 'completed'
    build_plan = m.api.prepare_plan(
        project_bindings_raw=args['project_bindings_raw'],
        expected_project_bindings_sha256=args['expected_project_bindings_sha256'],
        arm=args['financial_spec']['arm'], candidate_config_sha256=report['config_sha256'],
        candidate_attempt=args['financial_spec']['attempt'],
        operation_id='TPR-CMP29-API-SYNTHETIC-BUILD',
        git_head=args['git_head'],
        source_hashes=compile_action['api_plan']['source_hashes'],
        owner_instruction_sha256=args['owner_instruction_sha256'],
        created_utc=args['created_utc'], expires_utc=args['expires_utc'],
        requests=[m._request('build', 'compile/read', {'projectId': report['project_id'],
            'compileId': COMPILE_ID})], mode='offline-fixture',
        max_total_response_bytes=131072)
    built = native_fixture(build_plan, native_root, files, build=True)
    assert built['status'] == 'completed'
    names = {
        'compile_plan': compile_action['api_plan']['operation_id']+'.operation.spent.json',
        'compile_result': compile_action['api_plan']['operation_id']+'.result.json',
        'source_before': compiled['requests'][0]['raw_response']['name'],
        'compile_response': compiled['requests'][1]['raw_response']['name'],
        'source_after': compiled['requests'][2]['raw_response']['name'],
        'build_plan': build_plan['operation_id']+'.operation.spent.json',
        'build_result': build_plan['operation_id']+'.result.json',
        'build_response': built['requests'][0]['raw_response']['name']}
    raws = {key: (native_root/name).read_bytes() for key, name in names.items()}
    deps = {key: {'name': names[key], 'bytes': len(raw), 'sha256': m._sha(raw)}
        for key, raw in raws.items()}
    args.update(operation_id='TPR-CMP29-API-SYNTHETIC-LAUNCH')
    action = m.prepare_launch(**args, compile_evidence=deps, compile_id=COMPILE_ID)
    return action, args['public_sources'], native_root, raws


@pytest.mark.parametrize('arm', tuple(m.api.PROJECT_KEYS))
def test_each_arm_regenerates_only_frozen_config_files_and_project(arm):
    args, files, report = common(arm)
    action = m.prepare_compile(**args)
    packet = None if arm == 'cap_off' else {'key': m.bundle.PACKET_KEY,
        'sha256': m.bundle.PACKET_SHA256, 'bytes': m.bundle.PACKET_BYTES,
        'encoding': 'utf-8-json', 'source_inventory_sha256': m.bundle.INVENTORY_SHA256}
    expected_files, expected_report = m.bundle.build_project_candidate(
        public_sources={name: args['public_sources'][name] for name in m.bundle.SOURCE_PATHS},
        project_binding_raw=args['project_bindings_raw'],
        expected_project_binding_sha256=args['expected_project_bindings_sha256'],
        arm=arm, operation_id=args['financial_spec']['operation_id'],
        attempt=args['financial_spec']['attempt'],
        prior_attempts_looks_sha256=args['financial_spec']['prior_attempts_looks_sha256'], signal_packet=packet)
    assert files == expected_files and m._sha(expected_report) == action['candidate_report_sha256']
    assert action['api_plan']['project_id'] == m.api.REGISTERED_PROJECTS[m.api.PROJECT_KEYS[arm]]
    assert action['api_plan']['candidate_config_sha256'] == report['config_sha256']
    assert action['generated_source_hashes'] == report['cloud_source_hashes']
    assert action['generated_source_bytes'] == report['cloud_source_bytes']
    assert action['native_origin_authenticated'] is action['economics_accepted'] is False
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
        elif fault == 'wrong_receipt_link':body['requests'][0]['raw_response']['sha256'] = 'f'*64
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
    with pytest.raises(Exception):
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
