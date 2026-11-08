"""Synthetic A4 state-machine checks; no private artifacts or provider calls."""
import ast
import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import arv2_r347_legacy_six_qc as m


@pytest.fixture
def uploads(monkeypatch):
    values = []
    prefix = m.ACTUAL_ACTIVATION['object_store_key'].rsplit('/', 1)[0] + '/'
    for index, (role, name) in enumerate(zip(m.OBJECT_ROLES, m.OBJECT_NAMES, strict=True)):
        raw = ('synthetic-private-fixture-' + str(index)).encode('ascii')
        descriptor = {'schema': 'arv2-newrule-plain-upload-object-v1', 'role': role, 'ordinal': 0,
            'object_store_key': prefix + name, 'relative_path': name, 'byte_count': len(raw),
            'content_sha256': m.sha(raw), 'record_count': 1, 'compression': 'identity',
            'activation_manifest': index == 5}
        values.append((descriptor, raw))
    monkeypatch.setattr(m, 'ACTUAL_ACTIVATION', {key: values[-1][0][key]
        for key in ('object_store_key', 'content_sha256', 'byte_count')})
    return tuple(values)


def metadata(item):
    descriptor, raw = item
    return {'success': True, 'metadata': {'key': descriptor['object_store_key'], 'size': len(raw),
        'md5': hashlib.md5(raw, usedforsecurity=False).hexdigest()}}


def test_six_plain_buffers_have_fixed_role_order_and_activation_last(uploads):
    descriptors = m.input_inventory(uploads)
    assert [row['role'] for row in descriptors] == list(m.OBJECT_ROLES)
    assert [row['activation_manifest'] for row in descriptors] == [False] * 5 + [True]
    assert descriptors[0] is not uploads[0][0]


@pytest.mark.parametrize('change', ['count', 'order', 'rawtype', 'rawhash', 'wrongkey', 'extra',
    'gzip', 'earlyactivation', 'boolsize', 'boolcount', 'wrong_schema'])
def test_input_inventory_does_not_accept_relabelled_or_malformed_data(uploads, change):
    selected = copy.deepcopy(uploads)
    if change == 'count': selected = selected[:-1]
    elif change == 'order': selected = (selected[1], selected[0], *selected[2:])
    elif change == 'rawtype': selected = ((selected[0][0], bytearray(selected[0][1])), *selected[1:])
    else:
        descriptor = selected[0][0]
        if change == 'rawhash': descriptor['content_sha256'] = '0' * 64
        if change == 'wrongkey': descriptor['object_store_key'] = 'unrelated/key.json'
        if change == 'extra': descriptor['authorization'] = True
        if change == 'gzip': descriptor['compression'] = 'gzip'
        if change == 'earlyactivation': descriptor['activation_manifest'] = True
        if change == 'boolsize': descriptor['byte_count'] = True
        if change == 'boolcount': descriptor['record_count'] = True
        if change == 'wrong_schema': descriptor['schema'] = 'other'
    with pytest.raises(m.Refused, match='input_objects'): m.input_inventory(selected)


def test_fresh_properties_are_metadata_only_even_when_md5_matches(uploads):
    for index, item in enumerate(uploads):
        result = m.check_object_metadata(metadata(item), *item, index)
        assert result['remote_payload_sha256_attested'] is False
        assert result['exclusive_resource_lease'] is False
        assert result['local_payload_sha256'] == m.sha(item[1])
        assert result['verification'].endswith('runtime_SHA256_required')
        assert 'synthetic-private-fixture' not in json.dumps(result)


def test_uppercase_metadata_md5_is_compared_case_insensitively(uploads):
    response = metadata(uploads[0]); response['metadata']['md5'] = response['metadata']['md5'].upper()
    m.check_object_metadata(response, *uploads[0], 0)


@pytest.mark.parametrize('change', ['missing', 'refused', 'wrongkey', 'wrongsize', 'boolsize', 'wrongmd5', 'badmd5'])
def test_metadata_mismatch_refuses_without_any_get_or_overwrite(uploads, change):
    response = metadata(uploads[0])
    if change == 'missing': response.pop('metadata')
    elif change == 'refused': response['success'] = False
    elif change == 'wrongkey': response['metadata']['key'] = 'unrelated'
    elif change == 'wrongsize': response['metadata']['size'] += 1
    elif change == 'boolsize': response['metadata']['size'] = True
    elif change == 'wrongmd5': response['metadata']['md5'] = '0' * 32
    else: response['metadata']['md5'] = 'not-a-digest'
    with pytest.raises(m.Refused): m.check_object_metadata(response, *uploads[0], 0)


def candidate():
    root = Path(__file__).resolve().parents[2]
    raw = (root / 'research/analyst_revisions_v2_qc/newrule_plain_input_runtime.py').read_bytes()
    runtime = (ast.unparse(ast.parse(raw)) + '\n').encode('ascii')
    assert m.pin(runtime) == m.PLAIN_LOADER_PIN
    profile = {'candidate_id': m.CANDIDATE, 'research_epoch_id': m.previous.EPOCH,
               'source_package_sha256': m.previous.PACKAGE_SHA256}
    sources = {f'module_{index:02d}.py': '# synthetic\n' for index in range(12)}
    for name in ('accepted_risk_matched_diagnostics.py', 'accepted_risk_order_level_core.py',
                 'accepted_risk_order_level_forced_exit.py'):
        sources[name] = '# synthetic accepted module\n'
    sources['accepted_risk_order_level_input_runtime.py'] = runtime.decode('ascii')
    sources['legacy_six_october_reporting.py'] = '# reporting fixture\n'
    sources['main.py'] = 'Driver(None, ' + ', '.join(name + '=' + repr(m.ACTUAL_ACTIVATION[field])
        for name, field in (('activation_manifest_key', 'object_store_key'),
            ('activation_manifest_sha256', 'content_sha256'), ('activation_manifest_byte_count', 'byte_count'))) + ')\n'
    pairs = [[name, value] for name, value in sorted(sources.items())]
    return {'candidate_id': m.CANDIDATE, 'ar_percent': 100, 'profile': profile,
        'profile_pin': m.pin(m.canonical(profile)), 'original_profile_sha256': 'b' * 64,
        'sources': [{'project_path': name, **m.pin(value.encode('ascii'))} for name, value in pairs],
        'source_pairs': pairs}


def test_exact_plain_loader_and_activation_bind_runtime_sha_gate():
    value, sources = m._plain_source(candidate())
    assert value['candidate_id'] == m.CANDIDATE
    assert m.pin(sources['accepted_risk_order_level_input_runtime.py'].encode('ascii')) == m.PLAIN_LOADER_PIN
    assert 'hashlib.sha256(payload).hexdigest() != expected_sha256' in sources[
        'accepted_risk_order_level_input_runtime.py']


@pytest.mark.parametrize('change', ['runtime', 'activation_key', 'activation_sha', 'activation_size'])
def test_source_cannot_bypass_cloud_plain_input_identity(change):
    value = candidate()
    for pair in value['source_pairs']:
        if change == 'runtime' and pair[0] == 'accepted_risk_order_level_input_runtime.py': pair[1] += '# edit\n'
        if pair[0] == 'main.py':
            if change == 'activation_key': pair[1] = pair[1].replace(m.ACTUAL_ACTIVATION['object_store_key'], 'other/key.json')
            if change == 'activation_sha': pair[1] = pair[1].replace(m.ACTUAL_ACTIVATION['content_sha256'], '0' * 64)
            if change == 'activation_size': pair[1] = pair[1].replace(str(m.ACTUAL_ACTIVATION['byte_count']), '5902')
    value['sources'] = [{'project_path': name, **m.pin(raw.encode('ascii'))} for name, raw in value['source_pairs']]
    with pytest.raises(m.Refused, match='source'): m._plain_source(value)


def test_actual_public_fact_and_fourth_attempt_are_distinct_from_old_budget():
    raw = (Path(__file__).resolve().parents[2] / 'scripts/arv2_r347_current_project_fact.json').read_bytes()
    assert m.pin(raw) == m.RECONCILIATION_PIN
    selected, observation = m.current_fact(raw)
    assert selected == raw and observation['source_file_count'] == 5
    assert observation['general_rows_pin'] == observation['dedicated_rows_pin'] == m.OWNER_ROWS_PIN
    assert observation['source_inventory_pin'] == m.INITIAL_INVENTORY_PIN
    assert m.profile_record()['attempt'] == 4
    assert m.profile_record()['attempt_budget_reset'] is False
    assert m.profile_record()['A1_A2_A3_remain_spent'] is True


ORG, USER = 'a' * 32, 71
OWNER = {'uid': USER, 'owner': True, 'name': 'synthetic owner', 'publicId': 'synthetic-owner',
    'permission': 'write', 'liveControl': True, 'profileImage': '', 'email': '', 'bio': ''}
EXTRA = {'uid': None, 'owner': False, 'name': m.CODE_SOURCE_ID, 'publicId': 'opaque-synthetic-lock-id',
    'permission': 'write', 'liveControl': True, 'profileImage': '', 'email': '', 'bio': ''}
ACCEPTED = ('accepted_risk_matched_diagnostics.py', 'accepted_risk_order_level_core.py',
            'accepted_risk_order_level_forced_exit.py')


class Fake:
    def __init__(self, cell, data):
        self.cell, self.uploads = cell, data
        sources = dict(cell['source_pairs'])
        self.files = {name: sources[name] for name in ACCEPTED}
        self.files.update({'main.py': m.previous.DEFAULT_MAIN,
                          'accepted_risk_order_level_input_runtime.py': '#'})
        self.calls, self.events, self.now = [], {}, 100.0
        self.locked = False
        self.available = True
        self.override = None
        self.compile_state, self.created_status, self.status = 'BuildSuccess', 'In Progress...', 'Completed.'

    def project(self):
        rows = [copy.deepcopy(OWNER)]
        if self.locked: rows.append(copy.deepcopy(EXTRA))
        return {'projectId': m.PROJECT, 'name': 'ARV2 LEGACY SIX R343-AR100 OCT2026',
            'organizationId': ORG, 'language': 'Py', 'owner': True, 'ownerId': USER,
            'codeRunning': False, 'collaborators': rows, 'libraries': [],
            'lastLiveDeployment': None, 'leanEnvironment': 0}

    def journal(self, marker, value):
        assert marker not in self.events
        self.events[marker] = copy.deepcopy(value)

    def run(self, status):
        return {'projectId': m.PROJECT, 'compileId': 'synthetic-compile',
            'backtestId': 'synthetic-backtest', 'name': 'ARV2 LEGACY SIX R343-AR100 OCT2026 A4',
            'status': status}

    def request(self, endpoint, payload):
        assert endpoint not in ('projects/create', 'projects/collaboration/lock/release',
                                'files/delete', 'backtests/read', 'object/get', 'object/set')
        self.calls.append((endpoint, copy.deepcopy(payload)))
        if self.override:
            value = self.override(endpoint, payload)
            if value is not None: return value
        result = {'success': True}
        if endpoint == 'authenticate': pass
        elif endpoint == 'projects/read': result['projects'] = [self.project()]
        elif endpoint == 'projects/collaboration/read':
            result.update(collaborators=[copy.deepcopy(OWNER)], userPermissions='write', userLiveControl=True)
        elif endpoint == 'backtests/list':
            launched = any(name == 'backtests/create' for name, _ in self.calls)
            result['backtests'] = [self.run(self.status)] if launched else []
            result['count'] = len(result['backtests'])
        elif endpoint == 'files/read':
            if 'codeSourceId' in payload:
                assert self.locked and payload['codeSourceId'] == m.CODE_SOURCE_ID
            result['files'] = [{'projectId': m.PROJECT, 'name': name, 'content': text}
                for name, text in sorted(self.files.items())]
        elif endpoint == 'object/properties':
            item = next(item for item in self.uploads if item[0]['object_store_key'] == payload['key'])
            result = metadata(item)
        elif endpoint == 'projects/nodes/read':
            result.update(nodes={'backtest': [{'busy': not self.available, 'active': True}]}, autoSelectNode=False)
        elif endpoint == 'projects/collaboration/lock/acquire':
            assert not self.locked and payload['codeSourceId'] == m.CODE_SOURCE_ID
            self.locked = True
        elif endpoint in ('files/create', 'files/update'):
            assert self.locked and payload['codeSourceId'] == m.CODE_SOURCE_ID
            assert (payload['name'] in self.files) is (endpoint == 'files/update')
            self.files[payload['name']] = payload['content']
        elif endpoint in ('compile/create', 'compile/read'):
            result.update(compileId='synthetic-compile', projectId=m.PROJECT)
            if endpoint == 'compile/read': result['state'] = self.compile_state
        elif endpoint == 'backtests/create': result['backtest'] = self.run(self.created_status)
        else: raise AssertionError(endpoint)
        return result


@pytest.fixture
def fake(monkeypatch, uploads):
    result = Fake(candidate(), uploads)
    original = (Path(__file__).resolve().parents[2] / 'scripts/arv2_r347_current_project_fact.json').read_bytes()
    fact = json.loads(original)
    observed = fact['original_envelope']['result']
    owner_pin = m.pin(m.canonical([OWNER]))
    vector = [{'project_path': name, **m.pin(text.encode('ascii'))}
              for name, text in sorted(result.files.items())]
    inventory_pin = m.pin(m.canonical(vector))
    observed.update(general_rows_pin=owner_pin, dedicated_rows_pin=owner_pin,
                    source_inventory_pin=inventory_pin, source_inventory=vector)
    result.fact = m.canonical(fact)
    monkeypatch.setattr(m, 'RECONCILIATION_PIN', m.pin(result.fact))
    monkeypatch.setattr(m, 'OWNER_ROWS_PIN', owner_pin)
    monkeypatch.setattr(m, 'INITIAL_INVENTORY_PIN', inventory_pin)
    monkeypatch.setattr(m, 'ORGANIZATION_SHA256', m.sha(ORG.encode('ascii')))
    return result


def runner(fake, **kwargs):
    values = dict(organization_id=ORG, user_id=USER, attempt=4, reconciliation_fact=fake.fact,
                  request=fake.request, journal=fake.journal, clock=lambda: fake.now)
    values.update(kwargs)
    return m.LegacySixQc(fake.cell, fake.uploads, **values)


def compiled(fake):
    value = runner(fake)
    assert value.begin_once()['state'] == 'compiling'
    assert value.poll_compile(0)['state'] == 'BuildSuccess'
    return value


def writes(fake):
    return [(endpoint, payload) for endpoint, payload in fake.calls if endpoint in ('files/create', 'files/update')]


@pytest.mark.parametrize('attempt', [1, 2, 3, 5, True, '4'])
def test_exact_additional_attempt_only_before_contact(fake, attempt):
    with pytest.raises(m.Refused, match='arguments'): runner(fake, attempt=attempt)
    assert fake.calls == []


@pytest.mark.parametrize('fact', [None, b'', 'not-bytes', b'{}'])
def test_reconciliation_must_match_before_contact(fake, fact):
    with pytest.raises(m.Refused, match='reconciliation'): runner(fake, reconciliation_fact=fact)
    assert fake.calls == []


def test_three_exact_sources_skip_and_fifteen_writes_main_last(fake):
    operation = runner(fake)
    assert operation.begin_once()['state'] == 'compiling'
    assert len(writes(fake)) == 15 and writes(fake)[-1][1]['name'] == 'main.py'
    assert len(operation.source_progress) == 18
    assert [row['project_path'] for row in operation.source_progress
        if row['action'] == 'already_exact_skip'] == list(ACCEPTED)
    assert fake.files == operation.sources
    assert sum(endpoint == 'compile/create' for endpoint, _ in fake.calls) == 1
    assert sum(endpoint.endswith('/acquire') for endpoint, _ in fake.calls) == 1
    assert len(operation.input_admission) == 6
    operation.input_admission[0]['remote_payload_sha256_attested'] = True
    assert operation.input_admission[0]['remote_payload_sha256_attested'] is False
    assert operation.last_access_observation['field_types']['isLibrary'] == 'absent'
    assert operation.last_access_observation['field_types']['public'] == 'absent'


@pytest.mark.parametrize('field,value,code', [('libraryIds', ['foreign'], 'libraries'),
    ('libraryIds', None, 'libraries'), ('libraryIds', '', 'libraries'),
    ('libraries', None, 'libraries'), ('libraries', ['foreign'], 'libraries'),
    ('isLibrary', True, 'libraries'), ('isLibrary', None, 'libraries'),
    ('public', True, 'private'), ('public', None, 'private'), ('codeRunning', True, 'idle'),
    ('lastLiveDeployment', 'deployment', 'live'), ('leanEnvironment', True, 'live'),
    ('organizationId', 'b' * 32, 'organization'), ('ownerId', USER + 1, 'owner')])
def test_required_access_contradictions_stop_before_lock_or_writes(fake, field, value, code):
    original = fake.project
    def project():
        row = original(); row[field] = value; return row
    fake.project = project
    operation = runner(fake)
    with pytest.raises(m.Refused, match=code): operation.begin_once()
    assert operation.last_access_observation is not None
    assert not writes(fake) and not any(endpoint.endswith('/acquire') for endpoint, _ in fake.calls)


def test_explicit_empty_library_ids_does_not_add_library_authority(fake):
    original = fake.project
    def project():
        row = original(); row['libraryIds'] = []; return row
    fake.project = project
    runner(fake).begin_once()


@pytest.mark.parametrize('kind', ['job', 'other_collaborator', 'changed_main', 'extra_source'])
def test_current_or_initial_drift_prevents_mutation(fake, kind):
    if kind == 'changed_main': fake.files['main.py'] += '# changed\n'
    elif kind == 'extra_source': fake.files['foreign.py'] = '# do not overwrite\n'
    elif kind == 'job':
        fake.override = lambda endpoint, payload: {'success': True, 'backtests': [fake.run('Completed.')], 'count': 1} \
            if endpoint == 'backtests/list' else None
    else:
        original = fake.project
        def project():
            row = original(); row['collaborators'].append(copy.deepcopy(EXTRA)); return row
        fake.project = project
    with pytest.raises(m.Refused): runner(fake).begin_once()
    assert not writes(fake) and not any(endpoint.endswith('/acquire') for endpoint, _ in fake.calls)


@pytest.mark.parametrize('change', ['uid', 'name', 'owner', 'permission', 'publicId', 'third', 'extraKey'])
def test_own_ack_is_not_permission_to_adopt_arbitrary_context(fake, change):
    original = fake.project
    def project():
        row = original()
        if fake.locked:
            if change == 'third': row['collaborators'].append(copy.deepcopy(EXTRA))
            else:
                row['collaborators'][1][change] = {'uid': USER, 'name': 'Mia', 'owner': True,
                    'permission': 'read', 'publicId': '', 'extraKey': 'unknown'}[change]
        return row
    fake.project = project
    operation = runner(fake)
    with pytest.raises(m.Refused): operation.begin_once()
    assert not operation._source_context and not writes(fake)
    assert sum(endpoint.endswith('/acquire') for endpoint, _ in fake.calls) == 1


def test_own_acquire_refusal_is_terminal_without_source_or_compile(fake):
    fake.override = lambda endpoint, payload: {'success': False} if endpoint.endswith('/acquire') else None
    operation = runner(fake)
    with pytest.raises(m.Refused, match='response'): operation.begin_once()
    with pytest.raises(m.Refused, match='state'): operation.begin_once()
    assert not writes(fake) and not any(endpoint == 'compile/create' for endpoint, _ in fake.calls)


@pytest.mark.parametrize('kind', ['row', 'source', 'job'])
def test_drift_between_source_writes_stops_before_second_write(fake, kind):
    original = fake.project
    def project():
        row = original()
        if kind == 'row' and len(writes(fake)):
            row['collaborators'][1]['publicId'] += '-changed'
        return row
    fake.project = project
    def override(endpoint, payload):
        if len(writes(fake)) == 1:
            if kind == 'source' and endpoint == 'files/read': fake.files['main.py'] += '# changed\n'
            if kind == 'job' and endpoint == 'backtests/list':
                return {'success': True, 'backtests': [fake.run('Completed.')], 'count': 1}
        return None
    fake.override = override
    with pytest.raises(m.Refused): runner(fake).begin_once()
    assert len(writes(fake)) == 1
    assert not any(endpoint == 'compile/create' for endpoint, _ in fake.calls)


def test_refused_upload_is_dispatched_once_and_never_silently_retried(fake):
    fake.override = lambda endpoint, payload: {'success': False, 'errors': ['private reason']} \
        if endpoint in ('files/create', 'files/update') else None
    operation = runner(fake)
    with pytest.raises(m.Refused, match='response') as caught: operation.begin_once()
    assert 'private reason' not in str(caught.value)
    with pytest.raises(m.Refused, match='state'): operation.begin_once()
    assert len(writes(fake)) == 1
    assert operation.last_failure['endpoint'] in ('files/create', 'files/update')
    assert not any(endpoint == 'compile/create' for endpoint, _ in fake.calls)


def test_missing_or_mismatched_object_prevents_source_writes(fake):
    fake.override = lambda endpoint, payload: {'success': True, 'metadata': None} \
        if endpoint == 'object/properties' else None
    operation = runner(fake)
    with pytest.raises(m.Refused, match='input_objects'): operation.begin_once()
    assert operation.input_admission is None and not writes(fake)
    assert not any(endpoint.endswith('/acquire') for endpoint, _ in fake.calls)


def test_inputs_checked_again_after_compile_before_launch(fake):
    operation = compiled(fake)
    fake.override = lambda endpoint, payload: {'success': True, 'metadata': {'key': payload['key'],
        'size': 1, 'md5': '0' * 32}} if endpoint == 'object/properties' else None
    with pytest.raises(m.Refused, match='input_objects'): operation.launch_once()
    assert not any(endpoint == 'backtests/create' for endpoint, _ in fake.calls)


def test_capacity_unavailable_before_lock_returns_wait_without_writes(fake):
    fake.available = False
    assert runner(fake).begin_once()['state'] == 'wait'
    assert not fake.locked and not writes(fake)


def test_compile_failure_and_interval_are_terminal_before_launch(fake):
    operation = runner(fake); operation.begin_once(); fake.compile_state = 'Building'
    assert operation.poll_compile(0)['state'] == 'Building'
    with pytest.raises(m.Refused, match='wait'): operation.poll_compile(1)
    fake.now += m.COMPILE_INTERVAL; fake.compile_state = 'BuildError'
    assert operation.poll_compile(1)['state'] == 'BuildError'
    with pytest.raises(m.Refused): operation.launch_once()
    assert not any(endpoint == 'backtests/create' for endpoint, _ in fake.calls)


@pytest.mark.parametrize('status', ['In Queue...', 'In Progress...', 'Completed.', 'Runtime Error'])
def test_actual_launch_status_is_returned_without_claiming_queue_is_running(fake, status):
    operation = compiled(fake); fake.created_status = status
    output = operation.launch_once()
    assert output['launch_status'] == status
    assert operation.launch_receipt['attempt'] == 4
    assert operation.launch_receipt['backtest_id'] == 'synthetic-backtest'
    assert len(operation.metadata_admissions) == 2
    assert sum(endpoint == 'object/properties' for endpoint, _ in fake.calls) == 12
    with pytest.raises(m.Refused): operation.launch_once()
    assert sum(endpoint == 'backtests/create' for endpoint, _ in fake.calls) == 1


def test_launch_refusal_retains_observed_run_id_without_success(fake):
    operation = compiled(fake)
    fake.override = lambda endpoint, payload: {'success': False,
        'backtest': {'backtestId': 'observed-run'}} if endpoint == 'backtests/create' else None
    with pytest.raises(m.Refused, match='response'): operation.launch_once()
    assert operation.launch_receipt['backtest_id'] == 'observed-run'
    assert operation.launch_status is None
    with pytest.raises(m.Refused): operation.launch_once()


def test_queued_status_polls_are_bounded_statistics_off_and_keep_receipt(fake):
    operation = compiled(fake); fake.created_status = fake.status = 'In Queue...'
    operation.launch_once()
    assert operation.poll_status(0)['status'] == 'In Queue...'
    with pytest.raises(m.Refused, match='wait'): operation.poll_status(1)
    fake.now += m.STATUS_INTERVAL; fake.status = 'In Progress...'
    assert operation.poll_status(1)['status'] == 'In Progress...'
    operation._status_count = 30
    with pytest.raises(m.Refused, match='status_budget'): operation.poll_status(30)
    assert all(payload['includeStatistics'] is False for endpoint, payload in fake.calls if endpoint == 'backtests/list')
    with pytest.raises(m.Refused, match='scope'): operation.read_statistics_once()


@pytest.mark.parametrize('endpoint', ['projects/create', 'projects/collaboration/lock/release',
                                    'files/delete', 'backtests/read', 'object/get', 'object/set'])
def test_forbidden_endpoints_never_reach_transport(fake, endpoint):
    operation = runner(fake)
    with pytest.raises(m.Refused, match='request'): operation._call('not-permitted', endpoint, {})
    assert fake.calls == []
