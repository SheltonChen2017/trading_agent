"""Synthetic injected QC protocol; no operational client or private DATA."""
import copy
import hashlib
import json

import pytest

from scripts import arv2_r345_legacy_six_qc as module


ORG = 'a' * 32
USER = 71
OWNER = {'owner': True, 'uid': USER, 'permission': 'write', 'liveControl': True,
         'name': 'synthetic owner', 'publicId': 'synthetic-owner'}


def cell(percent=100):
    profile = {'candidate_id': f'R343-AR{percent:03d}', 'research_epoch_id': module.EPOCH,
               'source_package_sha256': module.PACKAGE_SHA256}
    pairs = [[name, '# synthetic source\n'] for name in sorted(
        ['main.py', 'legacy_six_october_reporting.py'] + [f'module_{i:02d}.py' for i in range(16)])]
    return {'candidate_id': profile['candidate_id'], 'ar_percent': percent,
        'profile': profile, 'profile_pin': {'byte_count': len(module.canonical(profile)),
                                          'sha256': module.sha(module.canonical(profile))},
        'original_profile_sha256': 'b' * 64, 'source_pairs': pairs,
        'sources': [{'project_path': name, 'byte_count': len(text),
                     'sha256': module.sha(text.encode('ascii'))} for name, text in pairs]}


class Fake:
    def __init__(self):
        self.events, self.calls, self.now = {}, [], 100.0
        self.project_id = 701
        self.files = {'main.py': '# default\n', 'research.ipynb': '{}'}
        self.source_id = None
        self.project_name = None
        self.compile_state = 'BuildSuccess'
        self.status = 'Completed.'
        self.created_status = 'In Progress...'
        self.available = True
        self.override = None
        self.statistics = {name: '{}' for name in (*module.LEGACY_STATISTICS, module.PERIOD_STATISTIC)}

    def project(self, reference=False):
        collaborators = [copy.deepcopy(OWNER)]
        if self.source_id is not None and not reference:
            collaborators.append({'owner': False, 'uid': None, 'permission': 'write',
                'liveControl': True, 'name': self.source_id, 'publicId': self.source_id})
        return {'projectId': module.REFERENCE_PROJECT if reference else self.project_id,
            'name': module.REFERENCE_NAME if reference else self.project_name,
            'organizationId': ORG, 'language': 'Py', 'owner': True, 'ownerId': USER,
            'public': False, 'codeRunning': False, 'collaborators': collaborators,
            'libraries': [], 'isLibrary': False, 'liveMode': False,
            'lastLiveDeployment': None, 'leanEnvironment': 0}

    def journal(self, marker, value):
        assert marker not in self.events
        self.events[marker] = copy.deepcopy(value)

    def request(self, endpoint, payload):
        self.calls.append((endpoint, copy.deepcopy(payload)))
        if self.override:
            result = self.override(endpoint, payload)
            if result is not None:
                return result
        result = {'success': True}
        if endpoint == 'authenticate':
            return result
        if endpoint == 'projects/read':
            result['projects'] = ([self.project(payload.get('projectId') == module.REFERENCE_PROJECT)]
                                  if payload else [])
        elif endpoint == 'projects/collaboration/read':
            result.update(collaborators=[copy.deepcopy(OWNER)], userPermissions='write', userLiveControl=True)
        elif endpoint == 'projects/nodes/read':
            result.update(nodes={'backtest': [{'busy': not self.available, 'active': True}]}, autoSelectNode=False)
        elif endpoint == 'projects/create':
            self.project_name = payload['name']
            result['projects'] = [{'projectId': self.project_id}]
        elif endpoint == 'projects/collaboration/lock/acquire':
            self.source_id = payload['codeSourceId']
        elif endpoint == 'files/read':
            result['files'] = [{'projectId': self.project_id, 'name': name, 'content': text}
                               for name, text in sorted(self.files.items())]
        elif endpoint in ('files/create', 'files/update'):
            if endpoint == 'files/create':
                assert payload['name'] not in self.files
            else:
                assert payload['name'] in self.files
            self.files[payload['name']] = payload['content']
        elif endpoint == 'files/delete':
            del self.files[payload['name']]
        elif endpoint in ('compile/create', 'compile/read'):
            result.update(compileId='synthetic-compile', projectId=self.project_id)
            if endpoint == 'compile/read':
                result['state'] = self.compile_state
        elif endpoint == 'backtests/list':
            launched = any(name == 'backtests/create' for name, _ in self.calls)
            result['backtests'] = [self.run(self.status)] if launched else []
            result['count'] = len(result['backtests'])
        elif endpoint == 'backtests/create':
            result['backtest'] = self.run(self.created_status)
        elif endpoint == 'backtests/read':
            result['backtest'] = {**self.run('Completed.'), 'statistics': copy.deepcopy(self.statistics)}
        else:
            raise AssertionError(endpoint)
        return result

    def run(self, status):
        return {'projectId': self.project_id, 'compileId': 'synthetic-compile',
            'backtestId': 'synthetic-backtest', 'name': f'{self.project_name} A1', 'status': status}


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(module, 'ORGANIZATION_SHA256', hashlib.sha256(ORG.encode('ascii')).hexdigest())
    return Fake()


def runner(fake, percent=100):
    return module.LegacySixQc(cell(percent), organization_id=ORG, user_id=USER,
        attempt=1, request=fake.request, journal=fake.journal, clock=lambda: fake.now)


def compiled(fake):
    result = runner(fake)
    assert result.begin_once()['state'] == 'compiling'
    assert result.poll_compile(0)['state'] == 'BuildSuccess'
    return result


def completed(fake):
    result = compiled(fake)
    assert result.launch_once()['state'] == 'launched'
    assert result.poll_status(0)['status'] == 'Completed.'
    return result


def test_access_capacity_read_only_fixed_scope(fake):
    result = module.access_capacity(fake.request, user_id=USER, journal=fake.journal)
    assert result['organization_id'] == ORG
    assert result['public']['capacity']['available_count'] == 1
    assert [name for name, _ in fake.calls] == ['authenticate', 'projects/read',
        'projects/collaboration/read', 'projects/nodes/read']
    assert ORG not in json.dumps(result['public'])


def test_active_reference_editor_allowed_for_read_only(fake):
    original = fake.project
    def project(reference=False):
        row = original(reference)
        if reference:
            row['codeRunning'] = True
        return row
    fake.project = project
    assert module.access_capacity(fake.request, user_id=USER,
        journal=fake.journal)['public']['reference_code_running'] is True


@pytest.mark.parametrize('field,value,code', [('public', True, 'private'),
    ('ownerId', USER + 1, 'owner'), ('owner', False, 'owner'), ('language', 'C#', 'project_identity'),
    ('libraries', [5], 'libraries'), ('liveMode', True, 'live'), ('codeRunning', None, 'idle')])
def test_reference_access_refusals(fake, field, value, code):
    original = fake.project
    def project(reference=False):
        row = original(reference); row[field] = value
        return row
    fake.project = project
    with pytest.raises(module.Refused, match=code):
        module.access_capacity(fake.request, user_id=USER, journal=fake.journal)
    assert not any(name == 'projects/create' for name, _ in fake.calls)


def test_reference_missing_public_only_observes_capacity(fake):
    original = fake.project
    def project(reference=False):
        row = original(reference); row.pop('public')
        return row
    fake.project = project
    result = module.access_capacity(fake.request, user_id=USER, journal=fake.journal)
    assert result['public']['reference_privacy'] == 'unproven'
    assert result['public']['capacity']['available_count'] == 1
    assert all(name in ('authenticate', 'projects/read', 'projects/collaboration/read',
                        'projects/nodes/read') for name, _ in fake.calls)


@pytest.mark.parametrize('field,value,code', [('public', None, 'private'), ('public', True, 'private'),
    ('lastLiveDeployment', '2026-01-01', 'live'), ('lastLiveDeployment', False, 'live'),
    ('leanEnvironment', True, 'live'), ('leanEnvironment', -1, 'live'),
    ('isLibrary', True, 'libraries'), ('libraries', None, 'libraries')])
def test_new_project_mutation_gates(fake, field, value, code):
    original = fake.project
    def project(reference=False):
        row = original(reference)
        if not reference:
            row[field] = value
        return row
    fake.project = project
    result = runner(fake)
    with pytest.raises(module.Refused, match=code): result.begin_once()
    assert not any(name in ('files/create', 'files/update', 'files/delete', 'compile/create')
                   for name, _ in fake.calls)


@pytest.mark.parametrize('field,code', [('lastLiveDeployment', 'live'),
    ('leanEnvironment', 'live'), ('isLibrary', 'libraries'), ('libraries', 'libraries')])
def test_new_project_missing_required_evidence(fake, field, code):
    original = fake.project
    def project(reference=False):
        row = original(reference)
        if not reference:
            row.pop(field)
        return row
    fake.project = project
    result = runner(fake)
    with pytest.raises(module.Refused, match=code): result.begin_once()
    assert not any(name in ('files/create', 'files/update', 'files/delete', 'compile/create')
                   for name, _ in fake.calls)


def test_new_missing_public_uses_actual_allocation_owner_and_empty_history(fake):
    original = fake.project
    def project(reference=False):
        row = original(reference)
        if not reference:
            row.pop('public')
        return row
    fake.project = project
    result = runner(fake)
    assert result.begin_once()['state'] == 'compiling'
    assert result._allocation is not None
    assert fake.events['project-allocation']['project_id'] == result.project_id
    for name in ('created', 'locked', 'compiled-preflight', *(f'write-{i:02d}' for i in range(18))):
        assert name + '-privacy-history-observed' in fake.events
    assert result.poll_compile(0)['state'] == 'BuildSuccess'
    assert result.launch_once()['state'] == 'launched'
    assert 'launch-000-privacy-history-observed' in fake.events


@pytest.mark.parametrize('corruption', ['absent', 'foreign_id', 'foreign_request', 'refused_response'])
def test_allocation_origin_cannot_be_asserted_or_reused(fake, corruption):
    result = runner(fake)
    def journal(marker, value):
        fake.journal(marker, value)
        if marker != 'project-allocation':
            return
        if corruption == 'absent':
            result._allocation = None
        elif corruption == 'foreign_id':
            result._allocation = (result._allocation[0], module.canonical(
                {'success': True, 'projects': [{'projectId': fake.project_id + 1}]}))
        elif corruption == 'foreign_request':
            result._allocation = (module.canonical({'name': 'unrelated project', 'language': 'Py',
                                                    'organizationId': ORG}), result._allocation[1])
        else:
            result._allocation = (result._allocation[0], module.canonical(
                {'success': False, 'projects': [{'projectId': fake.project_id}]}))
    result.journal = journal
    with pytest.raises(module.Refused): result.begin_once()
    assert not any(name in ('files/create', 'files/update', 'files/delete', 'compile/create',
                           'backtests/create') for name, _ in fake.calls)


@pytest.mark.parametrize('stage', ['before_write', 'before_compile', 'before_launch'])
def test_appearing_job_stops_new_project_mutation(fake, stage):
    result = runner(fake)
    def override(endpoint, payload):
        writes = sum(name in ('files/create', 'files/update') for name, _ in fake.calls)
        compiles = sum(name == 'compile/create' for name, _ in fake.calls)
        target = ((stage == 'before_write' and writes == 0 and fake.source_id is not None)
            or (stage == 'before_compile' and writes == 18 and compiles == 0)
            or (stage == 'before_launch' and compiles == 1))
        if endpoint == 'backtests/list' and target:
            return {'success': True, 'backtests': [{'backtestId': 'foreign-run',
                'projectId': fake.project_id, 'name': 'other run', 'status': 'Completed.'}], 'count': 1}
        return None
    fake.override = override
    if stage == 'before_launch':
        result.begin_once(); result.poll_compile(0)
        with pytest.raises(module.Refused, match='history'): result.launch_once()
        assert sum(name == 'compile/create' for name, _ in fake.calls) == 1
    else:
        with pytest.raises(module.Refused, match='history'): result.begin_once()
        assert not any(name == 'compile/create' for name, _ in fake.calls)
        expected = 0 if stage == 'before_write' else 18
        assert sum(name in ('files/create', 'files/update') for name, _ in fake.calls) == expected
    assert not any(name == 'backtests/create' for name, _ in fake.calls)


def test_missing_public_after_launch_does_not_admit_result_read(fake):
    result = completed(fake)
    original = fake.project
    def project(reference=False):
        row = original(reference)
        if not reference:
            row.pop('public')
        return row
    fake.project = project
    with pytest.raises(module.Refused, match='private'): result.read_statistics_once()
    assert not any(name == 'backtests/read' for name, _ in fake.calls)


@pytest.mark.parametrize('percent', module.AR_PERCENTS)
def test_each_cell_source_compiles_and_main_is_last(fake, percent):
    result = runner(fake, percent)
    assert result.begin_once()['state'] == 'compiling'
    writes = [payload for name, payload in fake.calls if name in ('files/create', 'files/update')]
    assert len(writes) == 18 and writes[-1]['name'] == 'main.py'
    assert set(fake.files) == {name for name, _ in cell(percent)['source_pairs']}
    assert sum(name == 'compile/create' for name, _ in fake.calls) == 1
    assert all(payload['codeSourceId'] == result.code_source for name, payload in fake.calls
               if name.startswith('files/'))


def test_default_notebook_only_deleted_from_new_own_project(fake):
    result = runner(fake); result.begin_once()
    deleted = [payload for name, payload in fake.calls if name == 'files/delete']
    assert deleted == [{'projectId': fake.project_id, 'name': 'research.ipynb',
                        'codeSourceId': result.code_source}]


def test_unrelated_initial_file_stops_without_writes(fake):
    fake.files['other.py'] = '# user source\n'
    result = runner(fake)
    with pytest.raises(module.Refused, match='source_inventory'):
        result.begin_once()
    assert not any(name in ('files/create', 'files/update', 'files/delete') for name, _ in fake.calls)


def test_name_collision_stops_before_create(fake):
    result = runner(fake)
    fake.override = lambda name, payload: {'success': True, 'projects': [{'name': result.name}]} \
        if name == 'projects/read' and payload == {} else None
    with pytest.raises(module.Refused, match='project_name'):
        result.begin_once()
    assert not any(name == 'projects/create' for name, _ in fake.calls)


def test_initial_capacity_wait_has_no_mutation(fake):
    fake.available = False
    result = runner(fake)
    assert result.begin_once()['state'] == 'wait'
    assert result.project_id is None
    with pytest.raises(module.Refused, match='state'):
        result.begin_once()
    assert not any(name == 'projects/create' for name, _ in fake.calls)


def test_source_refusal_terminal_no_compile_no_retry(fake):
    fake.override = lambda endpoint, payload: {'success': False, 'errors': ['private provider reason']} \
        if endpoint == 'files/create' else None
    result = runner(fake)
    with pytest.raises(module.Refused, match='response') as caught:
        result.begin_once()
    assert 'private provider reason' not in str(caught.value)
    assert sum(name == 'files/create' for name, _ in fake.calls) == 1
    assert result.last_failure['endpoint'] == 'files/create'
    assert result.last_failure['stage'] == 'response_unaccepted'
    assert 'private provider reason' not in json.dumps(result.last_failure)
    assert not any(name in ('compile/create', 'backtests/create') for name, _ in fake.calls)
    with pytest.raises(module.Refused, match='state'):
        result.begin_once()


def test_source_drift_before_write_refuses(fake):
    result = runner(fake)
    calls = 0
    def override(endpoint, payload):
        nonlocal calls
        if endpoint == 'files/read':
            calls += 1
            if calls == 2:
                fake.files['main.py'] += '# concurrent edit\n'
        return None
    fake.override = override
    with pytest.raises(module.Refused, match='source_changed'):
        result.begin_once()
    assert not any(name in ('files/create', 'files/update') for name, _ in fake.calls)


def test_project_id_retained_before_bad_response(fake):
    fake.override = lambda endpoint, payload: {'success': False, 'projects': [{'projectId': 812}]} \
        if endpoint == 'projects/create' else None
    result = runner(fake)
    with pytest.raises(module.Refused, match='response'):
        result.begin_once()
    assert result.project_id == 812
    assert result._allocation is None
    assert fake.events['project-created']['project_id'] == 812


def test_project_id_retained_if_journal_later_fails(fake):
    result = runner(fake)
    def fail(marker, value):
        if marker == 'project-created':
            raise RuntimeError('synthetic sink failure')
        return fake.journal(marker, value)
    result.journal = fail
    with pytest.raises(RuntimeError):
        result.begin_once()
    assert result.project_id == fake.project_id


def test_compile_error_spends_and_prevents_launch(fake):
    result = runner(fake); result.begin_once(); fake.compile_state = 'BuildError'
    assert result.poll_compile(0)['state'] == 'BuildError'
    assert result.terminal_receipt['status'] == 'BuildError'
    with pytest.raises(module.Refused): result.poll_compile(1)
    with pytest.raises(module.Refused): result.launch_once()
    assert not any(name == 'backtests/create' for name, _ in fake.calls)


def test_compile_poll_interval_and_index(fake):
    result = runner(fake); result.begin_once(); fake.compile_state = 'Building'
    assert result.poll_compile(0)['state'] == 'Building'
    with pytest.raises(module.Refused, match='wait'): result.poll_compile(1)
    fake.now += 2
    with pytest.raises(module.Refused, match='compile_budget'): result.poll_compile(2)
    assert result.poll_compile(1)['state'] == 'Building'


def test_launch_wait_interval_and_single_create(fake):
    result = compiled(fake); fake.available = False
    assert result.launch_once()['state'] == 'wait'
    with pytest.raises(module.Refused, match='wait'): result.launch_once()
    fake.now += 60; fake.available = True
    assert result.launch_once()['state'] == 'launched'
    with pytest.raises(module.Refused, match='state'): result.launch_once()
    assert sum(name == 'backtests/create' for name, _ in fake.calls) == 1


def test_launch_rechecks_current_sources(fake):
    result = compiled(fake); fake.files['main.py'] += '# concurrent edit\n'
    with pytest.raises(module.Refused, match='source_changed'): result.launch_once()
    assert not any(name == 'backtests/create' for name, _ in fake.calls)


@pytest.mark.parametrize('terminal', ['Completed.', 'Runtime Error'])
def test_fast_terminal_create_is_retained(fake, terminal):
    result = compiled(fake); fake.created_status = terminal
    output = result.launch_once()
    assert output['terminal_receipt']['status'] == terminal
    assert fake.events['backtest-created']['backtest_id'] == 'synthetic-backtest'
    assert result.launch_receipt['backtest_id'] == 'synthetic-backtest'


def test_backtest_identity_retained_before_bad_response(fake):
    result = compiled(fake)
    fake.override = lambda endpoint, payload: {'success': False, 'backtest': {'backtestId': 'observed-id'}} \
        if endpoint == 'backtests/create' else None
    with pytest.raises(module.Refused, match='response'): result.launch_once()
    assert result.launch_receipt['backtest_id'] == 'observed-id'
    with pytest.raises(module.Refused): result.launch_once()
    assert sum(name == 'backtests/create' for name, _ in fake.calls) == 1


def test_status_requires_matching_own_run_and_no_statistics(fake):
    result = compiled(fake); result.launch_once()
    fake.override = lambda endpoint, payload: {'success': True, 'backtests': [
        {**fake.run('Completed.'), 'backtestId': 'other-run'}]} if endpoint == 'backtests/list' else None
    with pytest.raises(module.Refused, match='status'): result.poll_status(0)
    assert all(payload['includeStatistics'] is False for name, payload in fake.calls if name == 'backtests/list')


def test_status_interval(fake):
    result = compiled(fake); result.launch_once(); fake.status = 'In Progress...'
    result.poll_status(0)
    with pytest.raises(module.Refused, match='wait'): result.poll_status(1)
    fake.now += 60; fake.status = 'Completed.'
    assert result.poll_status(1)['terminal'] is True


def test_result_once_retains_only_allowlisted_original_text(fake):
    result = completed(fake)
    fake.statistics['unrelated statistic'] = 'private unrelated data'
    output = result.read_statistics_once()
    assert set(output['statistics']) == set(module.LEGACY_STATISTICS) | {module.PERIOD_STATISTIC}
    assert output['semantic_validation'] == 'required'
    assert fake.events['result-statistics']['statistics'] == output['statistics']
    assert 'private unrelated data' not in json.dumps(fake.events)
    with pytest.raises(module.Refused): result.read_statistics_once()
    assert sum(name == 'backtests/read' for name, _ in fake.calls) == 1


def test_invalid_completed_three_statistics_allowed_for_semantic_parser(fake):
    result = completed(fake); fake.statistics.pop(module.PERIOD_STATISTIC)
    assert set(result.read_statistics_once()['statistics']) == set(module.LEGACY_STATISTICS)


@pytest.mark.parametrize('change', ['extra', 'missing', 'oversize', 'nonascii', 'wrongtype'])
def test_result_statistic_refusal_spends_read(fake, change):
    result = completed(fake)
    if change == 'extra': fake.statistics['ARV2_OTHER'] = '{}'
    if change == 'missing': fake.statistics.pop(module.LEGACY_STATISTICS[0])
    if change == 'oversize': fake.statistics[module.PERIOD_STATISTIC] = 'x' * 8193
    if change == 'nonascii': fake.statistics[module.PERIOD_STATISTIC] = '\N{SNOWMAN}'
    if change == 'wrongtype': fake.statistics[module.PERIOD_STATISTIC] = {}
    with pytest.raises(module.Refused, match='statistics'): result.read_statistics_once()
    with pytest.raises(module.Refused): result.read_statistics_once()
    assert sum(name == 'backtests/read' for name, _ in fake.calls) == 1


def test_runtime_error_never_reads_results(fake):
    result = compiled(fake); fake.created_status = 'Runtime Error'; result.launch_once()
    with pytest.raises(module.Refused, match='not_completed'): result.read_statistics_once()
    assert not any(name == 'backtests/read' for name, _ in fake.calls)


@pytest.mark.parametrize('change', ['text', 'hash', 'duplicate', 'profile', 'candidate', 'subclass'])
def test_cell_source_boundary(fake, change):
    value = cell()
    if change == 'text': value['source_pairs'][0][1] += '# drift\n'
    if change == 'hash': value['sources'][0]['sha256'] = '0' * 64
    if change == 'duplicate': value['source_pairs'][-1] = value['source_pairs'][0]
    if change == 'profile': value['profile']['source_package_sha256'] = '0' * 64
    if change == 'candidate': value['candidate_id'] = 'R261'
    if change == 'subclass':
        class Text(str): pass
        value['source_pairs'][0][1] = Text(value['source_pairs'][0][1])
    with pytest.raises(module.Refused):
        module.LegacySixQc(value, organization_id=ORG, user_id=USER, attempt=1,
            request=fake.request, journal=fake.journal)
    assert fake.calls == []


def test_cell_is_defensively_copied(fake):
    value = cell()
    result = module.LegacySixQc(value, organization_id=ORG, user_id=USER, attempt=1,
                              request=fake.request, journal=fake.journal)
    value['source_pairs'][0][1] += '# caller drift\n'
    result.begin_once()
    assert fake.files[value['source_pairs'][0][0]] == '# synthetic source\n'


@pytest.mark.parametrize('payload', [{'busy': 0, 'active': True}, {'busy': False, 'active': 1}, {}])
def test_capacity_rejects_non_boolean_or_missing_nodes(payload):
    with pytest.raises(module.Refused, match='capacity'):
        module.capacity({'success': True, 'nodes': {'backtest': [payload]}, 'autoSelectNode': True})


def test_private_rpc_cannot_contact_unrelated_endpoint_or_project(fake):
    result = runner(fake)
    with pytest.raises(module.Refused, match='request'): result._call('bad', 'live/create', {})
    with pytest.raises(module.Refused, match='scope'):
        result._call('bad-project', 'projects/read', {'projectId': 9})
    assert fake.calls == []


def test_profile_exposes_no_operational_entrypoint_or_false_success():
    profile = module.profile_record()
    assert profile['pilot'] == 'R343-AR100'
    assert profile['result_reads'] == 1
    assert profile['privacy_prelaunch'] == 'actual_new_allocation_current_owner_only_and_empty_history'
    assert profile['privacy_after_launch_requires_explicit_false'] is True
    assert profile['privacy_continuously_proven'] is False
    assert all(profile[name] is False for name in module.FALSE_FLAGS)
    assert not hasattr(module, 'main')
