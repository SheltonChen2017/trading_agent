"""Synthetic fresh allocations for six remaining arms; no operations or DATA."""
import ast
import copy
import hashlib
from pathlib import Path

import pytest

from scripts import arv2_r348_legacy_six_qc as m

ORG, USER = 'a' * 32, 71
OWNER = {'uid': USER, 'owner': True, 'name': 'synthetic owner', 'publicId': 'owner-public-id',
    'permission': 'write', 'liveControl': True, 'profileImage': '', 'email': '', 'bio': ''}


def cell(percent=80):
    profile = {'candidate_id': f'R343-AR{percent:03d}', 'research_epoch_id': m.base.EPOCH,
               'source_package_sha256': m.base.PACKAGE_SHA256}
    raw = (Path(__file__).resolve().parents[2] /
           'research/analyst_revisions_v2_qc/newrule_plain_input_runtime.py').read_bytes()
    runtime = ast.unparse(ast.parse(raw)) + '\n'
    sources = {f'module_{index:02d}.py': '# synthetic\n' for index in range(15)}
    sources['legacy_six_october_reporting.py'] = '# reporting fixture\n'
    sources['accepted_risk_order_level_input_runtime.py'] = runtime
    sources['main.py'] = 'Driver(None, ' + ', '.join(key + '=' + repr(m.ACTUAL_ACTIVATION[field])
        for key, field in (('activation_manifest_key', 'object_store_key'),
            ('activation_manifest_sha256', 'content_sha256'), ('activation_manifest_byte_count', 'byte_count'))) + ')\n'
    pairs = [[name, raw] for name, raw in sorted(sources.items())]
    return {'candidate_id': profile['candidate_id'], 'ar_percent': percent, 'profile': profile,
        'profile_pin': m.pin(m.canonical(profile)), 'original_profile_sha256': 'b' * 64,
        'sources': [{'project_path': name, **m.pin(raw.encode('ascii'))} for name, raw in pairs],
        'source_pairs': pairs}


class Fake:
    def __init__(self, data):
        self.uploads, self.calls, self.events, self.now = data, [], {}, 100.0
        self.project_id, self.name, self.source_id = 39990000, None, None
        self.files = {'main.py': m.plain.previous.DEFAULT_MAIN, 'research.ipynb': '{"cells":[],"nbformat":4}'}
        self.available, self.override = True, None
        self.compile_state, self.created_status, self.status = 'BuildSuccess', 'In Progress...', 'Completed.'

    def project(self, reference=False):
        rows = [copy.deepcopy(OWNER)]
        if self.source_id and not reference:
            rows.append({'uid': None, 'owner': False, 'name': self.source_id,
                'publicId': 'opaque-current-context', 'permission': 'write', 'liveControl': True,
                'profileImage': '', 'email': '', 'bio': ''})
        return {'projectId': m.REFERENCE_PROJECT if reference else self.project_id,
            'name': m.REFERENCE_NAME if reference else self.name, 'language': 'Py',
            'organizationId': ORG, 'owner': True, 'ownerId': USER, 'codeRunning': False,
            'collaborators': rows, 'libraries': [], 'lastLiveDeployment': None, 'leanEnvironment': 0}

    def journal(self, marker, value):
        assert marker not in self.events
        self.events[marker] = copy.deepcopy(value)

    def run(self, status):
        return {'projectId': self.project_id, 'compileId': 'synthetic-compile',
            'backtestId': 'synthetic-run', 'name': self.name + ' A1', 'status': status}

    def request(self, endpoint, payload):
        assert endpoint not in ('object/get', 'object/set', 'backtests/read', 'projects/collaboration/lock/release')
        self.calls.append((endpoint, copy.deepcopy(payload)))
        if self.override:
            result = self.override(endpoint, payload)
            if result is not None: return result
        result = {'success': True}
        if endpoint == 'authenticate': pass
        elif endpoint == 'projects/read':
            if not payload:
                result['projects'] = [{'projectId': m.REFERENCE_PROJECT, 'name': m.REFERENCE_NAME},
                    {'projectId': m.plain.PROJECT, 'name': 'ARV2 LEGACY SIX R343-AR100 OCT2026'}]
            else: result['projects'] = [self.project(payload['projectId'] == m.REFERENCE_PROJECT)]
        elif endpoint == 'projects/create':
            assert self.name is None; self.name = payload['name']
            result['projects'] = [{'projectId': self.project_id, 'name': self.name,
                'language': 'Py', 'organizationId': ORG}]
        elif endpoint == 'projects/collaboration/read':
            result.update(collaborators=[copy.deepcopy(OWNER)], userPermissions='write', userLiveControl=True)
        elif endpoint == 'projects/collaboration/lock/acquire':
            assert self.source_id is None; self.source_id = payload['codeSourceId']
        elif endpoint == 'projects/nodes/read':
            result.update(nodes={'backtest': [{'busy': not self.available, 'active': True}]}, autoSelectNode=False)
        elif endpoint == 'files/read':
            result['files'] = [{'projectId': self.project_id, 'name': name, 'content': raw}
                for name, raw in sorted(self.files.items())]
        elif endpoint in ('files/create', 'files/update'):
            assert payload['codeSourceId'] == self.source_id
            assert (payload['name'] in self.files) is (endpoint == 'files/update')
            self.files[payload['name']] = payload['content']
        elif endpoint == 'files/delete':
            assert payload['name'] == 'research.ipynb'; del self.files[payload['name']]
        elif endpoint == 'object/properties':
            row, raw = next(item for item in self.uploads if item[0]['object_store_key'] == payload['key'])
            result['metadata'] = {'key': row['object_store_key'], 'size': len(raw),
                'md5': hashlib.md5(raw, usedforsecurity=False).hexdigest()}
        elif endpoint in ('compile/create', 'compile/read'):
            result.update(compileId='synthetic-compile', projectId=self.project_id)
            if endpoint == 'compile/read': result['state'] = self.compile_state
        elif endpoint == 'backtests/list':
            launched = any(name == 'backtests/create' for name, _ in self.calls)
            result['backtests'] = [self.run(self.status)] if launched else []
            result['count'] = len(result['backtests'])
        elif endpoint == 'backtests/create': result['backtest'] = self.run(self.created_status)
        else: raise AssertionError(endpoint)
        return result


@pytest.fixture
def fake(monkeypatch):
    uploads = []
    prefix = m.ACTUAL_ACTIVATION['object_store_key'].rsplit('/', 1)[0] + '/'
    for index, (role, name) in enumerate(zip(m.plain.OBJECT_ROLES, m.plain.OBJECT_NAMES, strict=True)):
        raw = f'synthetic object {index}\n'.encode('ascii')
        uploads.append(({'schema': 'arv2-newrule-plain-upload-object-v1', 'role': role,
            'ordinal': 0, 'relative_path': name, 'object_store_key': prefix + name,
            'byte_count': len(raw), 'content_sha256': m.sha(raw), 'record_count': 1,
            'compression': 'identity', 'activation_manifest': index == 5}, raw))
    monkeypatch.setattr(m, 'ACTUAL_ACTIVATION', {key: uploads[-1][0][key]
        for key in ('object_store_key', 'content_sha256', 'byte_count')})
    monkeypatch.setattr(m, 'ORGANIZATION_SHA256', m.sha(ORG.encode('ascii')))
    return Fake(tuple(uploads))


def runner(fake, percent=80, **kwargs):
    values = dict(organization_id=ORG, user_id=USER, attempt=1, request=fake.request,
                  journal=fake.journal, clock=lambda: fake.now)
    values.update(kwargs)
    return m.LegacySixQc(cell(percent), fake.uploads, **values)


def compiled(fake, percent=80):
    result = runner(fake, percent); assert result.begin_once()['state'] == 'compiling'
    assert result.poll_compile(0)['state'] == 'BuildSuccess'
    return result


def writes(fake):
    return [(name, payload) for name, payload in fake.calls if name in ('files/create', 'files/update')]


@pytest.mark.parametrize('percent', m.AR_PERCENTS)
def test_six_remaining_arms_each_fresh_allocation_exact_eighteen_sources_main_last(fake, percent):
    operation = runner(fake, percent); operation.begin_once()
    assert operation.candidate == f'R343-AR{percent:03d}'
    assert operation.attempt == 1 and operation.code_source == f'Codex R348 R343-AR{percent:03d} A1'
    assert len(writes(fake)) == 18 and writes(fake)[-1][1]['name'] == 'main.py'
    assert fake.files == operation.sources and len(operation.source_progress) == 18
    assert sum(name == 'projects/create' for name, _ in fake.calls) == 1
    assert sum(name == 'files/delete' for name, _ in fake.calls) == 1
    assert sum(name == 'compile/create' for name, _ in fake.calls) == 1
    assert all(payload['projectId'] != m.plain.PROJECT for _, payload in fake.calls if 'projectId' in payload)
    assert operation.last_access_observation['field_types']['isLibrary'] == 'absent'
    assert operation.input_admission[0]['remote_payload_sha256_attested'] is False


@pytest.mark.parametrize('percent', [50, 100, 220])
def test_other_arms_and_ar100_cannot_allocate(fake, percent):
    with pytest.raises(m.Refused): runner(fake, percent)
    assert not fake.calls


@pytest.mark.parametrize('attempt', [0, 2, 3, 4, True, '1'])
def test_first_attempt_only_no_automatic_new_budget(fake, attempt):
    with pytest.raises(m.Refused, match='arguments'): runner(fake, attempt=attempt)
    assert not fake.calls


def test_candidate_name_collision_refuses_before_allocation(fake):
    fake.override = lambda endpoint, payload: {'success': True,
        'projects': [{'projectId': 123, 'name': 'ARV2 LEGACY SIX R343-AR080 OCT2026'}]} \
        if endpoint == 'projects/read' and not payload else None
    with pytest.raises(m.Refused, match='project_name'): runner(fake).begin_once()
    assert not any(name == 'projects/create' for name, _ in fake.calls)


def test_allocation_identity_retained_even_when_creation_refused(fake):
    fake.override = lambda endpoint, payload: {'success': False, 'projects': [{'projectId': 39990001}]} \
        if endpoint == 'projects/create' else None
    operation = runner(fake)
    with pytest.raises(m.Refused, match='response'): operation.begin_once()
    assert operation.project_id == 39990001 and fake.events['project-created']['project_id'] == 39990001
    assert operation._allocation is None and not writes(fake)


def test_returned_existing_project_id_is_not_adopted_or_edited(fake):
    fake.project_id = m.plain.PROJECT
    operation = runner(fake)
    with pytest.raises(m.Refused, match='scope'): operation.begin_once()
    assert not writes(fake) and not any(name.endswith('/acquire') for name, _ in fake.calls)


@pytest.mark.parametrize('field,value,code', [('isLibrary', True, 'libraries'),
    ('isLibrary', None, 'libraries'), ('libraryIds', ['other'], 'libraries'),
    ('libraryIds', None, 'libraries'), ('libraries', None, 'libraries'),
    ('public', True, 'private'), ('public', None, 'private'), ('codeRunning', True, 'idle'),
    ('lastLiveDeployment', 'active', 'live'), ('leanEnvironment', True, 'live'),
    ('ownerId', USER + 1, 'owner'), ('organizationId', 'b' * 32, 'organization')])
def test_fresh_allocation_does_not_override_current_access_contradictions(fake, field, value, code):
    original = fake.project
    def project(reference=False):
        row = original(reference)
        if not reference: row[field] = value
        return row
    fake.project = project
    with pytest.raises(m.Refused, match=code): runner(fake).begin_once()
    assert not writes(fake) and not any(name.endswith('/acquire') for name, _ in fake.calls)


@pytest.mark.parametrize('field,value', [('uid', USER), ('name', 'Mia'), ('owner', True),
                                      ('publicId', ''), ('permission', 'read'), ('unexpected', '')])
def test_only_our_ack_followed_by_single_controlled_technical_row_is_admitted(fake, field, value):
    original = fake.project
    def project(reference=False):
        row = original(reference)
        if not reference and fake.source_id: row['collaborators'][1][field] = value
        return row
    fake.project = project
    with pytest.raises(m.Refused): runner(fake).begin_once()
    assert not writes(fake)


@pytest.mark.parametrize('change', ['unknown', 'main', 'missingmain'])
def test_unknown_or_edited_new_allocation_files_never_overwritten(fake, change):
    if change == 'unknown': fake.files['user.py'] = '# owner work\n'
    elif change == 'main': fake.files['main.py'] += '# owner edit\n'
    else: fake.files.pop('main.py')
    with pytest.raises(m.Refused, match='initial_source'): runner(fake).begin_once()
    assert not writes(fake) and not any(name == 'files/delete' for name, _ in fake.calls)


def test_optional_notebook_absent_never_causes_delete(fake):
    fake.files.pop('research.ipynb'); runner(fake).begin_once()
    assert not any(name == 'files/delete' for name, _ in fake.calls)


def test_notebook_edit_after_lock_is_preserved_not_deleted(fake):
    reads = 0
    def override(endpoint, payload):
        nonlocal reads
        if endpoint == 'files/read':
            reads += 1
            if reads == 2: fake.files['research.ipynb'] += ' '
        return None
    fake.override = override
    with pytest.raises(m.Refused, match='source_changed'): runner(fake).begin_once()
    assert not any(name == 'files/delete' for name, _ in fake.calls)


def test_bad_properties_refuse_before_new_project_or_lock(fake):
    fake.override = lambda endpoint, payload: {'success': True, 'metadata': None} \
        if endpoint == 'object/properties' else None
    with pytest.raises(m.Refused, match='input_objects'): runner(fake).begin_once()
    assert not any(name in ('projects/create', 'projects/collaboration/lock/acquire') for name, _ in fake.calls)


def test_metadata_is_fresh_before_launch_and_remains_qualified(fake):
    operation = compiled(fake)
    operation.launch_once()
    assert len(operation.metadata_admissions) == 2
    assert sum(name == 'object/properties' for name, _ in fake.calls) == 12
    assert operation.input_admission[0]['remote_payload_sha256_attested'] is False
    with pytest.raises(m.Refused): operation.launch_once()


def test_changed_object_after_compile_prevents_launch(fake):
    operation = compiled(fake)
    fake.override = lambda endpoint, payload: {'success': True, 'metadata': {'key': payload['key'],
        'size': 1, 'md5': '0' * 32}} if endpoint == 'object/properties' else None
    with pytest.raises(m.Refused, match='input_objects'): operation.launch_once()
    assert not any(name == 'backtests/create' for name, _ in fake.calls)


@pytest.mark.parametrize('status', ['In Queue...', 'In Progress...', 'Completed.', 'Runtime Error'])
def test_actual_launch_status_and_identity_are_retained_not_result_acceptance(fake, status):
    operation = compiled(fake); fake.created_status = status
    result = operation.launch_once()
    assert result['launch_status'] == status and result['launch_receipt']['attempt'] == 1
    assert result['launch_receipt']['backtest_id'] == 'synthetic-run'
    with pytest.raises(m.Refused, match='scope'): operation.read_statistics_once()


def test_upload_failure_is_terminal_and_no_silent_retry(fake):
    fake.override = lambda endpoint, payload: {'success': False} if endpoint == 'files/create' else None
    operation = runner(fake)
    with pytest.raises(m.Refused, match='response'): operation.begin_once()
    with pytest.raises(m.Refused, match='state'): operation.begin_once()
    assert len(writes(fake)) == 1 and not any(name == 'compile/create' for name, _ in fake.calls)


def test_full_row_or_source_drift_between_writes_stops(fake):
    original = fake.project
    def project(reference=False):
        row = original(reference)
        if not reference and fake.source_id and len(writes(fake)):
            row['collaborators'][1]['publicId'] += '-changed'
        return row
    fake.project = project
    with pytest.raises(m.Refused, match='collaborators'): runner(fake).begin_once()
    assert len(writes(fake)) == 1


@pytest.mark.parametrize('endpoint', ['object/get', 'object/set', 'backtests/read',
                                    'projects/collaboration/lock/release'])
def test_forbidden_endpoints_never_reach_transport(fake, endpoint):
    operation = runner(fake)
    with pytest.raises(m.Refused, match='request'): operation._call('bad', endpoint, {})
    assert not fake.calls


def test_profile_is_six_first_attempts_with_three_maximum_not_six_retries():
    value = m.profile_record()
    assert value['candidate_ids'] == ['R343-AR080', 'R343-AR120', 'R343-AR140',
                                      'R343-AR160', 'R343-AR180', 'R343-AR200']
    assert value['attempt'] == 1 and value['maximum_attempts_per_candidate'] == 3
    assert value['automatic_retry_permitted'] is value['AR100_and_A4_replay_permitted'] is False
    assert value['prior_A4_result_acceptance_external_required'] is True
