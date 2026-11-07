"""Synthetic final recovery; public original facts, no private artifacts."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import arv2_r345_legacy_six_qc_v3 as module


ORG, USER = 'a' * 32, 71
FACT_RAW = (Path(__file__).resolve().parents[2] / 'scripts/arv2_r345_ar100_a1_failure_fact.json').read_bytes()
FACT = json.loads(FACT_RAW)
A2_RAW = (Path(__file__).resolve().parents[2] / 'scripts/arv2_r345_ar100_a2_failure_fact.json').read_bytes()
DIAG_RAW = (Path(__file__).resolve().parents[2] / 'scripts/arv2_r345_lock_diagnostic_fact.json').read_bytes()
OWNER = {'owner': True, 'uid': USER, 'permission': 'write', 'liveControl': True,
         'name': 'synthetic owner', 'publicId': 'synthetic-owner', 'profileImage': '', 'email': '', 'bio': ''}
EXTRA = {'owner': False, 'uid': None, 'permission': 'write', 'liveControl': True,
         'name': module.A2_CODE_SOURCE_ID, 'publicId': 'synthetic-opaque-id',
         'profileImage': '', 'email': '', 'bio': ''}


def cell():
    profile = {'candidate_id': 'R343-AR100', 'research_epoch_id': module.EPOCH,
               'source_package_sha256': module.PACKAGE_SHA256}
    pairs = [[name, '# synthetic source\n'] for name in sorted(
        ['main.py', 'legacy_six_october_reporting.py'] + [f'module_{i:02d}.py' for i in range(16)])]
    return {'candidate_id': profile['candidate_id'], 'ar_percent': 100,
        'profile': profile, 'profile_pin': {'byte_count': len(module.canonical(profile)),
                                          'sha256': module.sha(module.canonical(profile))},
        'original_profile_sha256': 'b' * 64, 'source_pairs': pairs,
        'sources': [{'project_path': name, 'byte_count': len(text),
                     'sha256': module.sha(text.encode('ascii'))} for name, text in pairs]}


class Fake:
    def __init__(self):
        self.events, self.calls, self.now = {}, [], 100.0
        self.project_id = module.RECOVERY_PROJECT
        self.project_name = 'ARV2 LEGACY SIX R343-AR100 OCT2026'
        self.files = {'main.py': module.DEFAULT_MAIN, 'research.ipynb': '{}'}
        self.source_id = module.A2_CODE_SOURCE_ID
        self.compile_state, self.status, self.created_status = 'BuildSuccess', 'Completed.', 'In Progress...'
        self.available, self.override = True, None
        self.statistics = {name: '{}' for name in (*module.LEGACY_STATISTICS, module.PERIOD_STATISTIC)}

    def project(self, reference=False):
        collaborators = [copy.deepcopy(OWNER)]
        if self.source_id is not None and not reference:
            collaborators.append(copy.deepcopy(EXTRA))
        # Current model omits isLibrary/public; never fabricate False fields.
        return {'projectId': module.REFERENCE_PROJECT if reference else self.project_id,
            'name': module.REFERENCE_NAME if reference else self.project_name,
            'organizationId': ORG, 'language': 'Py', 'owner': True, 'ownerId': USER,
            'codeRunning': False, 'collaborators': collaborators,
            'libraries': [], 'lastLiveDeployment': None, 'leanEnvironment': 0}

    def journal(self, marker, value):
        assert marker not in self.events
        self.events[marker] = copy.deepcopy(value)

    def request(self, endpoint, payload):
        assert endpoint != 'projects/create'
        assert endpoint not in ('projects/collaboration/lock/acquire', 'projects/collaboration/lock/release')
        assert endpoint != 'projects/read' or payload
        self.calls.append((endpoint, copy.deepcopy(payload)))
        if self.override:
            result = self.override(endpoint, payload)
            if result is not None: return result
        result = {'success': True}
        if endpoint == 'authenticate': return result
        if endpoint == 'projects/read':
            result['projects'] = [self.project(payload['projectId'] == module.REFERENCE_PROJECT)]
        elif endpoint == 'projects/collaboration/read':
            result.update(collaborators=[copy.deepcopy(OWNER)], userPermissions='write', userLiveControl=True)
        elif endpoint == 'projects/nodes/read':
            result.update(nodes={'backtest': [{'busy': not self.available, 'active': True}]}, autoSelectNode=False)
        elif endpoint == 'files/read':
            result['files'] = [{'projectId': self.project_id, 'name': name, 'content': text}
                               for name, text in sorted(self.files.items())]
        elif endpoint in ('files/create', 'files/update'):
            assert (payload['name'] in self.files) is (endpoint == 'files/update')
            self.files[payload['name']] = payload['content']
        elif endpoint == 'files/delete': del self.files[payload['name']]
        elif endpoint in ('compile/create', 'compile/read'):
            result.update(compileId='synthetic-compile', projectId=self.project_id)
            if endpoint == 'compile/read': result['state'] = self.compile_state
        elif endpoint == 'backtests/list':
            launched = any(name == 'backtests/create' for name, _ in self.calls)
            result['backtests'] = [self.run(self.status)] if launched else []
            result['count'] = len(result['backtests'])
        elif endpoint == 'backtests/create': result['backtest'] = self.run(self.created_status)
        elif endpoint == 'backtests/read':
            result['backtest'] = {**self.run('Completed.'), 'statistics': copy.deepcopy(self.statistics)}
        else: raise AssertionError(endpoint)
        return result

    def run(self, status):
        return {'projectId': self.project_id, 'compileId': 'synthetic-compile',
            'backtestId': 'synthetic-backtest', 'name': f'{self.project_name} A3', 'status': status}


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(module, 'ORGANIZATION_SHA256', hashlib.sha256(ORG.encode('ascii')).hexdigest())
    owner = module.canonical(OWNER); extra = module.canonical(EXTRA)
    monkeypatch.setattr(module, 'GENERAL_OWNER_PIN', (len(owner), module.sha(owner)))
    monkeypatch.setattr(module, 'DEDICATED_OWNER_PIN', (len(owner) + 1, module.sha(owner + b'\n')))
    monkeypatch.setattr(module, 'A2_TECHNICAL_ROW_PIN', (len(extra), module.sha(extra)))
    return Fake()


def runner(fake, **kwargs):
    values = dict(organization_id=ORG, user_id=USER, attempt=3, a1_failure_fact=FACT_RAW,
        a2_failure_fact=A2_RAW, lock_diagnostic_fact=DIAG_RAW,
        request=fake.request, journal=fake.journal, clock=lambda: fake.now)
    values.update(kwargs)
    return module.LegacySixQc(cell(), **values)


def compiled(fake):
    result = runner(fake)
    assert result.begin_once()['state'] == 'compiling'
    assert result.poll_compile(0)['state'] == 'BuildSuccess'
    return result


def completed(fake):
    result = compiled(fake); result.launch_once(); result.poll_status(0)
    return result


def test_public_fact_hash_and_scope():
    assert module.sha(FACT_RAW) == module.A1_FAILURE_FACT_SHA256
    assert module.validate_recovery_fact(FACT_RAW) == FACT
    assert module.failure_fact(FACT) == FACT_RAW


def test_actual_public_diagnostic_row_pin_conventions():
    result = json.loads(DIAG_RAW)['output']['result']
    general, extra = result['general_rows']
    assert general['canonical_row_pin'] == dict(zip(('byte_count', 'sha256'), module.GENERAL_OWNER_PIN))
    assert extra['canonical_row_pin'] == dict(zip(('byte_count', 'sha256'), module.A2_TECHNICAL_ROW_PIN))
    assert result['dedicated_owner_row_pin'] == dict(zip(('byte_count', 'sha256'), module.DEDICATED_OWNER_PIN))
    assert module.validate_a2_failure_fact(A2_RAW) == json.loads(A2_RAW)
    assert module.validate_lock_diagnostic_fact(DIAG_RAW) == json.loads(DIAG_RAW)
    assert extra['known_A2_code_source_matches']['name'] is True
    assert extra['known_A2_code_source_matches']['publicId'] is False


@pytest.mark.parametrize('which', ['a2', 'diagnostic'])
@pytest.mark.parametrize('corruption', ['missing', 'edited', 'wrongtype', 'changedvalue'])
def test_new_facts_are_exact_before_contact(fake, which, corruption):
    name, original = ('a2_failure_fact', A2_RAW) if which == 'a2' else ('lock_diagnostic_fact', DIAG_RAW)
    if corruption == 'missing': changed = None
    elif corruption == 'edited': changed = original + b' '
    elif corruption == 'wrongtype': changed = original.decode('ascii')
    else:
        changed = json.loads(original); changed['observation']['actual_exit'] = 99
    with pytest.raises(module.Refused, match='recovery_fact'): runner(fake, **{name: changed})
    assert fake.calls == []


@pytest.mark.parametrize('change', ['empty', 'type', 'edited', 'exit', 'project', 'head', 'cause'])
def test_refused_frozen_witness_before_contact(fake, change):
    changed = copy.deepcopy(FACT)
    if change == 'empty': raw = b''
    elif change == 'type': raw = FACT_RAW.decode('ascii')
    elif change == 'edited': raw = FACT_RAW + b' '
    else:
        if change == 'exit': changed['observation']['actual_exit'] = 0
        if change == 'project': changed['failure']['evidence']['allocated_identities']['project_id'] += 1
        if change == 'head': changed['binding']['expected_head'] = 'a' * 40
        if change == 'cause': changed['failure']['evidence']['module_error']['code'] = 'private'
        raw = changed
    with pytest.raises(module.Refused, match='recovery_fact'): runner(fake, a1_failure_fact=raw)
    assert fake.calls == []


@pytest.mark.parametrize('attempt', [1, 2, True, '3'])
def test_attempt_exactly_three(fake, attempt):
    with pytest.raises(module.Refused, match='arguments'): runner(fake, attempt=attempt)
    assert fake.calls == []


def test_dict_fact_is_defensively_bound(fake):
    fact = copy.deepcopy(FACT); result = runner(fake, a1_failure_fact=fact)
    fact['observation']['actual_exit'] = 0
    assert result.begin_once()['state'] == 'compiling'
    assert type(result._recovery_fact) is bytes


def test_same_project_never_creates_or_lists_account(fake):
    result = runner(fake)
    assert result.begin_once()['project_id'] == module.RECOVERY_PROJECT
    assert result.backtest_name.endswith(' A3') and result.code_source == module.A2_CODE_SOURCE_ID
    assert not any(name == 'projects/create' or (name == 'projects/read' and not payload)
                   for name, payload in fake.calls)
    assert all(payload['projectId'] in (module.RECOVERY_PROJECT, module.REFERENCE_PROJECT)
               for _, payload in fake.calls if 'projectId' in payload)
    assert not any(name.endswith('/acquire') or name.endswith('/release') for name, _ in fake.calls)
    assert 'source-context-adopted' in fake.events
    assert all(payload['codeSourceId'] == module.A2_CODE_SOURCE_ID for name, payload in fake.calls
               if name.startswith('files/'))


def test_exact_opaque_technical_public_id_not_assumed_to_be_name(fake):
    result = runner(fake); result.begin_once()
    assert EXTRA['name'] == module.A2_CODE_SOURCE_ID
    assert EXTRA['publicId'] != module.A2_CODE_SOURCE_ID
    assert result._source_context is True


@pytest.mark.parametrize('change', ['missing', 'third', 'publicId', 'name', 'uid', 'owner',
    'permission', 'liveControl', 'extraKey', 'email'])
def test_only_exact_authenticated_a2_technical_row_is_adopted(fake, change):
    original = fake.project
    def project(reference=False):
        row = original(reference)
        if reference: return row
        rows = row['collaborators']
        if change == 'missing': rows.pop()
        elif change == 'third': rows.append({'owner': False, 'uid': 99, 'name': 'other user'})
        else:
            values = {'publicId': 'arbitrary-id', 'name': 'arbitrary-name', 'uid': 99,
                'owner': True, 'permission': 'read', 'liveControl': False,
                'extraKey': 'unrecognized', 'email': 'changed'}
            rows[1][change] = values[change]
        return row
    fake.project = project
    result = runner(fake)
    with pytest.raises(module.Refused, match='collaborators'): result.begin_once()
    assert result._source_context is False
    assert not any(name.startswith('files/') for name, _ in fake.calls)


def test_source_context_cannot_switch_to_an_unobserved_a3_identifier(fake):
    result = runner(fake); result.code_source = 'Codex R345 R343-AR100 A3'
    with pytest.raises(module.Refused, match='recovery_fact'): result.begin_once()
    assert fake.calls == []


def test_missing_is_library_success_preserves_unknown_observation(fake):
    runner(fake).begin_once()
    observation = fake.events['recovery-owned-access-metadata']
    assert observation['field_types']['isLibrary'] == observation['flags']['isLibrary'] == 'absent'
    assert observation['library_count'] == 0
    assert observation['field_types']['public'] == 'absent'


@pytest.mark.parametrize('field,value,code', [('isLibrary', True, 'libraries'),
    ('isLibrary', None, 'libraries'), ('isLibrary', 0, 'libraries'),
    ('libraries', None, 'libraries'), ('libraries', [5], 'libraries'),
    ('public', True, 'private'), ('public', None, 'private'),
    ('codeRunning', True, 'idle'), ('lastLiveDeployment', '2026-01-01', 'live'),
    ('leanEnvironment', True, 'live'), ('ownerId', USER + 1, 'owner'),
    ('organizationId', 'b' * 32, 'organization'), ('name', 'other', 'project_identity')])
def test_metadata_journal_before_validation_and_mutation(fake, field, value, code):
    original = fake.project
    def project(reference=False):
        row = original(reference)
        if not reference: row[field] = value
        return row
    fake.project = project
    result = runner(fake)
    with pytest.raises(module.Refused, match=code): result.begin_once()
    assert 'recovery-owned-access-metadata' in fake.events
    assert module.validate_metadata_observation(result.last_access_observation) == \
        fake.events['recovery-owned-access-metadata']
    assert not any(name in ('files/create', 'files/update', 'files/delete',
        'projects/collaboration/lock/acquire', 'compile/create', 'backtests/create') for name, _ in fake.calls)


@pytest.mark.parametrize('field,code', [('libraries', 'libraries'),
    ('lastLiveDeployment', 'live'), ('leanEnvironment', 'live')])
def test_other_required_model_fields_remain_required(fake, field, code):
    original = fake.project
    def project(reference=False):
        row = original(reference)
        if not reference: row.pop(field)
        return row
    fake.project = project
    with pytest.raises(module.Refused, match=code): runner(fake).begin_once()


def test_explicit_is_library_false_is_supported(fake):
    original = fake.project
    def project(reference=False):
        row = original(reference)
        if not reference: row['isLibrary'] = False
        return row
    fake.project = project
    runner(fake).begin_once()
    assert fake.events['recovery-owned-access-metadata']['flags']['isLibrary'] == 'false'


def test_other_collaborator_blocks_before_initial_source(fake):
    fake.override = lambda endpoint, payload: {'success': True, 'collaborators': [OWNER, {'owner': False}],
        'userPermissions': 'write', 'userLiveControl': True} if endpoint == 'projects/collaboration/read' else None
    with pytest.raises(module.Refused, match='collaborators'): runner(fake).begin_once()
    assert not any(name.startswith('files/') or name.endswith('/acquire') for name, _ in fake.calls)


def test_existing_job_blocks_before_initial_source(fake):
    fake.override = lambda endpoint, payload: {'success': True, 'backtests': [fake.run('Completed.')], 'count': 1} \
        if endpoint == 'backtests/list' else None
    with pytest.raises(module.Refused, match='history'): runner(fake).begin_once()
    assert not any(name.startswith('files/') or name.endswith('/acquire') for name, _ in fake.calls)


@pytest.mark.parametrize('change', ['main', 'extra', 'missing', 'wrongproject', 'duplicate', 'wrongtype'])
def test_edited_or_unknown_initial_source_never_overwritten(fake, change):
    if change == 'main': fake.files['main.py'] += '# user edit\n'
    if change == 'extra': fake.files['other.py'] = '# user source\n'
    if change == 'missing': fake.files.pop('main.py')
    if change in ('wrongproject', 'duplicate', 'wrongtype'):
        rows = [{'projectId': fake.project_id, 'name': name, 'content': text}
                for name, text in fake.files.items()]
        if change == 'wrongproject': rows[0]['projectId'] += 1
        if change == 'duplicate': rows[1]['name'] = rows[0]['name']
        if change == 'wrongtype': rows[0]['content'] = []
        fake.override = lambda endpoint, payload: {'success': True, 'files': rows} \
            if endpoint == 'files/read' else None
    with pytest.raises(module.Refused, match='initial_source'): runner(fake).begin_once()
    assert not any(name in ('files/create', 'files/update', 'files/delete',
                           'projects/collaboration/lock/acquire') for name, _ in fake.calls)


@pytest.mark.parametrize('initial', [module.DEFAULT_MAIN, '#', '#\n'])
def test_exact_default_or_empty_stub_only_main_last(fake, initial):
    fake.files['main.py'] = initial; result = runner(fake); result.begin_once()
    writes = [payload for name, payload in fake.calls if name in ('files/create', 'files/update')]
    assert len(writes) == 18 and writes[-1]['name'] == 'main.py'
    assert next(payload for name, payload in fake.calls if name == 'files/read') == {
        'projectId': module.RECOVERY_PROJECT, 'codeSourceId': module.A2_CODE_SOURCE_ID}
    assert set(fake.files) == set(result.sources)


def test_edit_between_initial_and_adopted_inventory_refuses(fake):
    reads = 0
    def override(endpoint, payload):
        nonlocal reads
        if endpoint == 'files/read':
            reads += 1
            if reads == 2: fake.files['main.py'] += '# concurrent edit\n'
        return None
    fake.override = override
    with pytest.raises(module.Refused, match='source_changed'): runner(fake).begin_once()
    assert not any(name in ('files/create', 'files/update', 'files/delete', 'compile/create')
                   for name, _ in fake.calls)


@pytest.mark.parametrize('after_writes', [1, 8, 17])
def test_job_appearing_between_writes_stops(fake, after_writes):
    def override(endpoint, payload):
        writes = sum(name in ('files/create', 'files/update') for name, _ in fake.calls)
        if endpoint == 'backtests/list' and writes == after_writes:
            return {'success': True, 'backtests': [fake.run('Completed.')], 'count': 1}
        return None
    fake.override = override
    with pytest.raises(module.Refused, match='history'): runner(fake).begin_once()
    assert sum(name in ('files/create', 'files/update') for name, _ in fake.calls) == after_writes
    assert not any(name in ('compile/create', 'backtests/create') for name, _ in fake.calls)


def test_upload_refusal_terminal_and_finite(fake):
    fake.override = lambda endpoint, payload: {'success': False, 'errors': ['unretained private reason']} \
        if endpoint == 'files/create' else None
    result = runner(fake)
    with pytest.raises(module.Refused, match='response') as caught: result.begin_once()
    assert 'private reason' not in str(caught.value)
    assert result.last_failure['endpoint'] == 'files/create'
    with pytest.raises(module.Refused, match='state'): result.begin_once()
    assert sum(name == 'files/create' for name, _ in fake.calls) == 1
    assert not any(name in ('compile/create', 'backtests/create') for name, _ in fake.calls)


def test_compile_error_and_poll_interval(fake):
    result = runner(fake); result.begin_once(); fake.compile_state = 'Building'; result.poll_compile(0)
    with pytest.raises(module.Refused, match='wait'): result.poll_compile(1)
    fake.now += 2; fake.compile_state = 'BuildError'
    assert result.poll_compile(1)['state'] == 'BuildError'
    with pytest.raises(module.Refused): result.launch_once()


def test_capacity_wait_never_duplicates_launch(fake):
    result = compiled(fake); fake.available = False
    assert result.launch_once()['state'] == 'wait'
    with pytest.raises(module.Refused, match='wait'): result.launch_once()
    fake.now += 60; fake.available = True
    assert result.launch_once()['state'] == 'launched'
    with pytest.raises(module.Refused): result.launch_once()
    assert sum(name == 'backtests/create' for name, _ in fake.calls) == 1


@pytest.mark.parametrize('status', ['Completed.', 'Runtime Error'])
def test_fast_terminal_identity_retained(fake, status):
    result = compiled(fake); fake.created_status = status
    assert result.launch_once()['terminal_receipt']['status'] == status
    assert result.launch_receipt['backtest_id'] == 'synthetic-backtest'


def test_bad_create_response_retains_observed_id(fake):
    result = compiled(fake)
    fake.override = lambda endpoint, payload: {'success': False, 'backtest': {'backtestId': 'observed-run'}} \
        if endpoint == 'backtests/create' else None
    with pytest.raises(module.Refused, match='response'): result.launch_once()
    assert result.launch_receipt['backtest_id'] == 'observed-run'
    with pytest.raises(module.Refused): result.launch_once()


def test_post_launch_unknown_privacy_blocks_result_read(fake):
    result = completed(fake)
    with pytest.raises(module.Refused, match='private'): result.read_statistics_once()
    assert not any(name == 'backtests/read' for name, _ in fake.calls)


def test_explicit_private_result_once_selected_strings_only(fake):
    result = completed(fake); original = fake.project
    def project(reference=False):
        row = original(reference)
        if not reference: row['public'] = False
        return row
    fake.project = project; fake.statistics['other'] = 'unretained content'
    output = result.read_statistics_once()
    assert output['semantic_validation'] == 'required'
    assert set(output['statistics']) == set(module.LEGACY_STATISTICS) | {module.PERIOD_STATISTIC}
    assert 'unretained content' not in json.dumps(fake.events)
    with pytest.raises(module.Refused): result.read_statistics_once()


def test_no_private_rpc_project_create_or_account_listing(fake):
    result = runner(fake)
    with pytest.raises(module.Refused, match='request'): result._call('bad', 'projects/create', {})
    with pytest.raises(module.Refused, match='request'): result._call('bad-list', 'projects/read', {})
    for endpoint in ('projects/collaboration/lock/acquire', 'projects/collaboration/lock/release'):
        with pytest.raises(module.Refused, match='request'):
            result._call('bad-lock', endpoint, {'projectId': module.RECOVERY_PROJECT,
                                              'codeSourceId': module.A2_CODE_SOURCE_ID})
    assert fake.calls == []


def test_metadata_observation_closed_without_values():
    value = module.owned_access_observation({'projects': [{'libraries': ['private library'],
        'organizationId': ORG, 'ownerId': USER, 'lastLiveDeployment': 'private deployment'}]})
    assert set(value) == {'schema', 'project_count', 'field_types', 'flags', 'library_count',
        'collaborator_count', 'last_live_empty', 'lean_environment_nonnegative_integer'}
    assert value['library_count'] == 1
    assert 'private library' not in json.dumps(value) and 'private deployment' not in json.dumps(value)
    assert ORG not in json.dumps(value)
    assert module.validate_metadata_observation(value) == value


def test_metadata_retained_before_journal_failure(fake):
    result = runner(fake)
    def journal(marker, value):
        if marker == 'recovery-owned-access-metadata': raise RuntimeError('synthetic sink failure')
        return fake.journal(marker, value)
    result.journal = journal
    with pytest.raises(RuntimeError): result.begin_once()
    assert result.last_access_observation['field_types']['isLibrary'] == 'absent'
    module.validate_metadata_observation(result.last_access_observation)


@pytest.mark.parametrize('change', ['extra', 'raw', 'countbool', 'countlarge', 'typevalue',
    'flagvalue', 'flagtype', 'livevalue', 'leanvalue', 'inconsistent'])
def test_metadata_validator_does_not_allow_raw_or_malformed_values(change):
    value = module.owned_access_observation({'projects': [{'libraries': []}]})
    if change == 'extra': value['raw_project'] = 'private data'
    if change == 'raw': value['field_types']['organizationId'] = ORG
    if change == 'countbool': value['project_count'] = True
    if change == 'countlarge': value['library_count'] = 1001
    if change == 'typevalue': value['field_types']['ownerId'] = 77
    if change == 'flagvalue': value['flags']['public'] = 'private provider text'
    if change == 'flagtype': value['flags']['public'] = False
    if change == 'livevalue': value['last_live_empty'] = 'private deployment'
    if change == 'leanvalue': value['lean_environment_nonnegative_integer'] = 1
    if change == 'inconsistent': value['flags']['public'] = 'false'
    with pytest.raises(module.Refused, match='shape'): module.validate_metadata_observation(value)


def test_profile_same_ar100_final_recovery_only():
    value = module.profile_record()
    assert value['attempt'] == 3 and value['candidate_ids'] == ['R343-AR100']
    assert value['project_create_calls'] == 0
    assert value['a1_failure_fact_sha256'] == module.A1_FAILURE_FACT_SHA256
    assert value['privacy_continuously_proven'] is False
    assert value['final_attempt'] is True and value['lock_acquire_calls'] == value['lock_release_calls'] == 0
