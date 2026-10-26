"""Synthetic pure read reconciliation; native denial required for execution."""
import copy
import hashlib
from types import SimpleNamespace

import pytest

from scripts import arv2_r298_file_effect as m


@pytest.fixture
def supplied(monkeypatch):
    expected = b'print("synthetic expected source")\n'
    monkeypatch.setattr(m, 'EXPECTED_SOURCE_BYTES', len(expected))
    monkeypatch.setattr(m, 'EXPECTED_SOURCE_SHA256', hashlib.sha256(expected).hexdigest())
    monkeypatch.setattr(m.access, 'ORGANIZATION_SHA256', hashlib.sha256(b'a' * 32).hexdigest())
    owner = {'owner': True, 'uid': 123, 'permission': 'write', 'liveControl': False,
        'name': 'PRIVATE OWNER', 'private_metadata': {'not-output': 1}}
    other = {'owner': False, 'uid': None, 'name': 'Mia', 'permission': 'write', 'liveControl': True}
    project = {'projectId': m.PROJECT_ID, 'organizationId': 'a' * 32,
        'name': m.access.PROJECT_NAME, 'language': 'Py', 'owner': True, 'ownerId': 123,
        'codeRunning': True, 'collaborators': [copy.deepcopy(owner), copy.deepcopy(other)]}
    packets = [{'success': True, 'projects': [project]},
        {'success': True, 'collaborators': [copy.deepcopy(owner), copy.deepcopy(other)],
            'userPermissions': 'read', 'userLiveControl': False},
        {'success': True, 'files': [{'projectId': m.PROJECT_ID,
            'name': m.TARGET_NAME, 'content': expected.decode('ascii')}]}]
    return SimpleNamespace(expected=expected, packets=packets, owner=owner, other=other)


def run(supplied, request=None, journal=None):
    calls, events = [], []
    def ask(endpoint, payload):
        calls.append((endpoint, copy.deepcopy(payload)))
        return copy.deepcopy(supplied.packets[len(calls) - 1])
    def write(marker, event):
        events.append((marker, copy.deepcopy(event)))
    result = m.FileEffectObserver(supplied.expected).observe(request or ask, journal or write)
    return result, calls, events


def test_exact_three_reads_and_bounded_result(supplied):
    result, calls, events = run(supplied)
    assert calls == [(m.ENDPOINTS[0], {'projectId': m.PROJECT_ID}),
        (m.ENDPOINTS[1], {'projectId': m.PROJECT_ID}),
        (m.ENDPOINTS[2], {'projectId': m.PROJECT_ID, 'name': m.TARGET_NAME})]
    assert [(marker, event['event']) for marker, event in events] == [
        ('read-project', 'intent'), ('read-project', 'observed'),
        ('read-collaborators', 'intent'), ('read-collaborators', 'observed'),
        ('read-files', 'intent'), ('read-files', 'observed')]
    for (endpoint, payload), pair in zip(calls, (events[:2], events[2:4], events[4:])):
        assert pair[0][1] == {'event': 'intent', 'endpoint': endpoint,
            'payload_sha256': m._sha(m._canonical(payload))}
        assert set(pair[1][1]) == {'event', 'endpoint', 'response_sha256'}
    assert result['observation_complete'] is True and result['application_dispatch_count'] == 3
    assert result['read_context']['dedicated_count'] == 2
    assert result['read_context']['code_running']['boolean_value'] is True
    assert result['read_context']['owner_live_control']['boolean_value'] is False
    assert result['provider_request_count'] is result['failure_code'] is None
    assert all(result[key] is False and result['read_context'][key] is False for key in m.FALSE_FLAGS)
    assert m.validate_observation(result) is None
    raw = m._canonical(result)
    assert b'PRIVATE OWNER' not in raw and b'not-output' not in raw and b'Mia' not in raw
    assert supplied.expected not in raw and b'a' * 32 not in raw


@pytest.mark.parametrize('content,classification', [('expected', 'desired_source'),
    ('#', 'permitted_placeholder'), ('#\n', 'permitted_placeholder'),
    ('#\r\n', 'different_source'), ('', 'different_source'), ('different', 'different_source')])
def test_exact_content_classifications(supplied, content, classification):
    content = supplied.expected.decode('ascii') if content == 'expected' else content
    supplied.packets[2]['files'][0]['content'] = content
    result, calls, events = run(supplied)
    assert result['file_observation'] == {'byte_count': len(content),
        'sha256': m._sha(content.encode('ascii')), 'classification': classification}
    assert m.reconcile(*supplied.packets, supplied.expected) == result['file_observation']
    assert m.validate_observation(result) is None
    assert len(calls) == 3 and len(events) == 6


@pytest.mark.parametrize('expected', [None, '', b'', bytearray(b'abc'), b'\xff', b'#', b'#\n',
    b'x' * 64001, b'x' * 33])
def test_bad_expected_source_never_creates_observer(supplied, expected):
    with pytest.raises(m.EffectRefused, match='^expected_source$'):
        m.FileEffectObserver(expected)


def test_same_size_wrong_expected_hash_refuses(supplied):
    with pytest.raises(m.EffectRefused, match='^expected_source$'):
        m.FileEffectObserver(b'x' * len(supplied.expected))


@pytest.mark.parametrize('wrong', [0, True, '23055', 64001])
def test_expected_size_pin_is_not_shape_only(supplied, monkeypatch, wrong):
    monkeypatch.setattr(m, 'EXPECTED_SOURCE_BYTES', wrong)
    with pytest.raises(m.EffectRefused, match='^expected_source$'):
        m.FileEffectObserver(supplied.expected)


@pytest.mark.parametrize('field,value,code', [('projectId', True, 'file_project'),
    ('projectId', 1, 'file_project'), ('projectId', '38364439', 'file_project'),
    ('name', 'main.py', 'file_name'), ('name', None, 'file_name'),
    ('content', None, 'file_content'), ('content', True, 'file_content'),
    ('content', 'é', 'file_content'), ('content', 'x' * 64001, 'file_content')])
def test_file_required_values(supplied, field, value, code):
    supplied.packets[2]['files'][0][field] = value
    with pytest.raises(m.EffectRefused, match='^' + code + '$'):
        m.validate_file_response(supplied.packets[2], supplied.expected)


@pytest.mark.parametrize('field', ['name', 'content'])
def test_file_required_keys(supplied, field):
    supplied.packets[2]['files'][0].pop(field)
    with pytest.raises(m.EffectRefused):
        m.validate_file_response(supplied.packets[2], supplied.expected)


@pytest.mark.parametrize('rows', [None, {}, [], [None], [{}, {}]])
def test_exactly_one_file_required(supplied, rows):
    supplied.packets[2]['files'] = rows
    with pytest.raises(m.EffectRefused, match='^file_inventory$'):
        m.validate_file_response(supplied.packets[2], supplied.expected)


@pytest.mark.parametrize('field,value,code', [('projectId', True, 'file_project'),
    ('projectId', 1, 'file_project'), ('projectId', None, 'file_project'),
    ('count', True, 'file_count'), ('count', 0, 'file_count'), ('count', 2, 'file_count'),
    ('count', '1', 'file_count'), ('count', None, 'file_count')])
def test_file_optional_scope_cannot_contradict(supplied, field, value, code):
    supplied.packets[2][field] = value
    with pytest.raises(m.EffectRefused, match='^' + code + '$'):
        m.validate_file_response(supplied.packets[2], supplied.expected)


def test_matching_file_optional_scope_and_nonoutput_metadata(supplied):
    supplied.packets[2].update(projectId=m.PROJECT_ID, count=1, other={'private': ['not returned']})
    supplied.packets[2]['files'][0].update(id=10, modified='synthetic', open=True, isLibrary=False)
    result = m.validate_file_response(supplied.packets[2], supplied.expected)
    assert set(result) == {'byte_count', 'sha256', 'classification'}


def test_absent_file_project_id_is_not_invented_as_response_identity(supplied):
    supplied.packets[2]['files'][0].pop('projectId')
    result = m.validate_file_response(supplied.packets[2], supplied.expected)
    assert set(result) == {'byte_count', 'sha256', 'classification'}
    assert result['classification'] == 'desired_source'


@pytest.mark.parametrize('index', [0, 1, 2])
@pytest.mark.parametrize('change,code', [('missing_success', 'response_refused'),
    ('false', 'response_refused'), ('integer', 'response_refused'),
    ('null_errors', 'response_refused'), ('string_errors', 'response_refused'),
    ('nonempty_errors', 'response_refused'), ('too_big', 'response_bound'),
    ('tuple', 'access_json_shape'), ('nonstring_key', 'access_json_shape'),
    ('nan', 'access_json_shape')])
def test_each_response_strict_before_next_dispatch(supplied, index, change, code):
    packet = supplied.packets[index]
    if change == 'missing_success': packet.pop('success')
    elif change == 'false': packet['success'] = False
    elif change == 'integer': packet['success'] = 1
    elif change == 'null_errors': packet['errors'] = None
    elif change == 'string_errors': packet['errors'] = ''
    elif change == 'nonempty_errors': packet['errors'] = ['SECRET PROVIDER REASON']
    elif change == 'too_big': packet['hidden'] = 'x' * m.MAX_RESPONSE_BYTES
    elif change == 'tuple': packet['hidden'] = ('not', 'json')
    elif change == 'nonstring_key': packet['hidden'] = {1: 'not json'}
    else: packet['hidden'] = float('nan')
    result, calls, events = run(supplied)
    assert result['failure_code'] == code and result['application_dispatch_count'] == index + 1
    assert len(calls) == index + 1 and result['file_observation'] is None
    assert result['last_event'] == 'response_received'
    assert m.validate_observation(result) is None
    assert b'SECRET PROVIDER REASON' not in m._canonical(result)


@pytest.mark.parametrize('index', [0, 1, 2])
@pytest.mark.parametrize('packet', [None, [], 'SECRET', 1, True])
def test_nonobject_packet_stops_immediately(supplied, index, packet):
    supplied.packets[index] = packet
    result, calls, events = run(supplied)
    assert result['failure_code'] == 'response_shape'
    assert len(calls) == index + 1 and m.validate_observation(result) is None


@pytest.mark.parametrize('key,value,code', [('projectId', True, 'project_id'),
    ('projectId', 1, 'project_id'), ('organizationId', 'b' * 32, 'organization'),
    ('organizationId', None, 'organization'), ('name', 'another project', 'project_name'),
    ('language', 'C#', 'language'), ('owner', 1, 'owner'), ('owner', False, 'owner'),
    ('ownerId', None, 'owner_id'), ('ownerId', True, 'owner_id'), ('ownerId', 0, 'owner_id'),
    ('ownerId', 2 ** 63, 'owner_id')])
def test_read_owner_context_before_file_dispatch(supplied, key, value, code):
    supplied.packets[0]['projects'][0][key] = value
    result, calls, events = run(supplied)
    assert result['failure_code'] == code and len(calls) == 2
    assert result['read_context'] is result['file_observation'] is None
    assert m.validate_observation(result) is None


@pytest.mark.parametrize('rows', [None, [], {}, [None], [{}, {}]])
def test_project_exactly_one_object(supplied, rows):
    supplied.packets[0]['projects'] = rows
    result, calls, events = run(supplied)
    assert result['failure_code'] == 'project_shape' and len(calls) == 2


@pytest.mark.parametrize('index', [0, 1])
@pytest.mark.parametrize('key,value,code', [('projectId', True, 'project_id'),
    ('projectId', 1, 'project_id'), ('organizationId', 'b' * 32, 'organization'),
    ('organizationId', None, 'organization')])
def test_outer_read_scope_cannot_contradict(supplied, index, key, value, code):
    supplied.packets[index][key] = value
    result, calls, events = run(supplied)
    assert result['failure_code'] == code and len(calls) == 2


@pytest.mark.parametrize('key,value,code', [('owner', None, 'dedicated_rows'),
    ('owner', 1, 'dedicated_rows'), ('owner', False, 'dedicated_owner'),
    ('uid', True, 'dedicated_owner'), ('uid', 124, 'dedicated_owner'),
    ('uid', None, 'dedicated_owner'), ('permission', None, 'permissions'),
    ('permission', 'admin', 'permissions'), ('permission', True, 'permissions')])
def test_dedicated_positive_owner_is_unambiguous(supplied, key, value, code):
    supplied.packets[1]['collaborators'][0][key] = value
    result, calls, events = run(supplied)
    assert result['failure_code'] == code and len(calls) == 2


@pytest.mark.parametrize('value', [None, True, '', 'admin'])
def test_requester_must_have_explicit_read_permission(supplied, value):
    supplied.packets[1]['userPermissions'] = value
    result, calls, events = run(supplied)
    assert result['failure_code'] == 'permissions' and len(calls) == 2


@pytest.mark.parametrize('kind', ['empty', 'nonlist', 'nonobject', 'missingflag', 'badflag',
    'noowner', 'twoowners', 'nine'])
def test_dedicated_inventory_is_bounded_not_write_exclusive(supplied, kind):
    packet = supplied.packets[1]
    if kind == 'empty': packet['collaborators'] = []
    elif kind == 'nonlist': packet['collaborators'] = {}
    elif kind == 'nonobject': packet['collaborators'] = [supplied.owner, None]
    elif kind == 'missingflag': packet['collaborators'][1].pop('owner')
    elif kind == 'badflag': packet['collaborators'][1]['owner'] = 0
    elif kind == 'noowner': packet['collaborators'] = [copy.deepcopy(supplied.other)]
    elif kind == 'twoowners': packet['collaborators'] = [supplied.owner, copy.deepcopy(supplied.owner)]
    else: packet['collaborators'] = [supplied.owner] + [copy.deepcopy(supplied.other) for _ in range(8)]
    result, calls, events = run(supplied)
    assert result['failure_code'] in ('dedicated_rows', 'dedicated_owner') and len(calls) == 2


@pytest.mark.parametrize('owner_permission', ['read', 'write'])
@pytest.mark.parametrize('requester_permission', ['read', 'write'])
@pytest.mark.parametrize('count', [1, 8])
def test_owner_read_does_not_require_exclusive_write_or_live_control(supplied,
        monkeypatch, owner_permission, requester_permission, count):
    supplied.packets[1]['collaborators'] = [copy.deepcopy(supplied.owner)] + [
        copy.deepcopy(supplied.other) for _ in range(count - 1)]
    supplied.packets[1]['collaborators'][0]['permission'] = owner_permission
    supplied.packets[1]['userPermissions'] = requester_permission
    def forbidden(*args): raise AssertionError('Frozen A6 write verifier must not be used')
    monkeypatch.setattr(m.access, 'verify_access', forbidden)
    result, calls, events = run(supplied)
    assert result['observation_complete'] is True and len(calls) == 3
    assert result['read_context']['whole_owner_row_continuity_proven'] is False
    assert result['read_context']['write_access_policy_accepted'] is False
    assert m.validate_observation(result) is None


@pytest.mark.parametrize('value', [None, False, True, 0, '', [], {'diagnostic': 1}])
def test_unused_live_and_running_values_are_typed_diagnostics_only(supplied, value):
    supplied.packets[0]['projects'][0]['codeRunning'] = copy.deepcopy(value)
    supplied.packets[1]['collaborators'][0]['liveControl'] = copy.deepcopy(value)
    supplied.packets[1]['userLiveControl'] = copy.deepcopy(value)
    result, calls, events = run(supplied)
    assert result['observation_complete'] is True and m.validate_observation(result) is None
    assert result['read_context']['code_running']['sha256'] == m._sha(m._canonical(value))


def test_missing_diagnostic_fields_do_not_assert_false(supplied):
    for packet, key in ((supplied.packets[0]['projects'][0], 'collaborators'),
            (supplied.packets[0]['projects'][0], 'codeRunning'),
            (supplied.packets[1]['collaborators'][0], 'liveControl'),
            (supplied.packets[1], 'userLiveControl')):
        packet.pop(key)
    result, calls, events = run(supplied)
    for key in ('general_collaborators', 'code_running', 'owner_live_control', 'requester_live_control'):
        assert result['read_context'][key] == {'present': False, 'kind': 'absent', 'count': None,
            'boolean_value': None, 'sha256': None}
    assert m.validate_observation(result) is None


def test_general_metadata_is_bounded(supplied):
    supplied.packets[0]['projects'][0]['collaborators'] = [None] * 9
    result, calls, events = run(supplied)
    assert result['failure_code'] == 'metadata_bound' and len(calls) == 2


def test_snapshots_precede_subsequent_callback_mutation(supplied):
    calls = []
    def request(endpoint, payload):
        index = len(calls)
        calls.append(endpoint)
        if index == 1:
            supplied.packets[0]['projects'][0]['owner'] = False
        if index == 2:
            supplied.packets[1]['collaborators'][0]['uid'] = 999
        return supplied.packets[index]
    result, _, _ = run(supplied, request=request)
    assert result['observation_complete'] is True and len(calls) == 3
    assert m.validate_observation(result) is None


@pytest.mark.parametrize('failed_index', [0, 1, 2])
def test_request_failure_is_consumed_finite_and_not_retried(supplied, failed_index):
    calls = []
    def request(endpoint, payload):
        index = len(calls)
        calls.append(endpoint)
        if index == failed_index: raise RuntimeError('SECRET PROVIDER REASON')
        return supplied.packets[index]
    observer = m.FileEffectObserver(supplied.expected)
    result = observer.observe(request, lambda *args: None)
    assert result['failure_code'] == 'request_ambiguous' and len(calls) == failed_index + 1
    assert result['application_dispatch_count'] == len(calls) and result['last_event'] == 'intent'
    assert m.validate_observation(result) is None
    with pytest.raises(m.EffectRefused, match='^observer_used$'):
        observer.observe(request, lambda *args: None)
    assert len(calls) == failed_index + 1 and b'SECRET' not in m._canonical(result)


@pytest.mark.parametrize('fail_event', range(6))
@pytest.mark.parametrize('kind', ['raise', 'return'])
def test_journal_refusal_stops_dispatch_and_preserves_count(supplied, fail_event, kind):
    events = []
    def journal(marker, event):
        events.append((marker, event))
        if len(events) - 1 == fail_event:
            if kind == 'raise': raise RuntimeError('SECRET JOURNAL')
            return False
    result, calls, _ = run(supplied, journal=journal)
    assert result['failure_code'] == ('journal_failed' if kind == 'raise' else 'journal_result')
    assert result['application_dispatch_count'] == len(calls) == (fail_event + 1) // 2
    assert m.validate_observation(result) is None
    assert b'SECRET' not in m._canonical(result)


@pytest.mark.parametrize('request_callback,journal', [(None, lambda *args: None), (lambda *args: None, None), (1, 1)])
def test_invalid_callbacks_consume_only_instance(supplied, request_callback, journal):
    observer = m.FileEffectObserver(supplied.expected)
    result = observer.observe(request_callback, journal)
    assert result['failure_code'] == 'callbacks' and result['application_dispatch_count'] == 0
    assert m.validate_observation(result) is None
    with pytest.raises(m.EffectRefused, match='^observer_used$'):
        observer.observe(lambda *args: None, lambda *args: None)


def test_reentrant_observe_cannot_duplicate_reads(supplied):
    observer = m.FileEffectObserver(supplied.expected)
    calls = []
    def request(endpoint, payload):
        with pytest.raises(m.EffectRefused, match='^observer_used$'):
            observer.observe(request, lambda *args: None)
        calls.append(endpoint)
        return supplied.packets[len(calls) - 1]
    result = observer.observe(request, lambda *args: None)
    assert result['observation_complete'] is True and len(calls) == 3


@pytest.mark.parametrize('hidden', [lambda: (1, 2), lambda: {1: 'x'}, lambda: float('inf')])
def test_hidden_nonjson_metadata_is_never_normalized(supplied, hidden):
    supplied.packets[2]['files'][0]['hidden'] = hidden()
    with pytest.raises(m.EffectRefused, match='^access_json_shape$'):
        m.validate_file_response(supplied.packets[2], supplied.expected)


def test_hostile_subclass_hooks_are_not_called(supplied):
    class HostileDict(dict):
        def items(self): raise AssertionError('must not iterate subclass')
    supplied.packets[2]['hidden'] = HostileDict(secret='hidden')
    with pytest.raises(m.EffectRefused, match='^access_json_shape$'):
        m.validate_file_response(supplied.packets[2], supplied.expected)


@pytest.mark.parametrize('error', [RuntimeError('SECRET'), m.EffectRefused('SECRET'),
    m.EffectRefused(), m.EffectRefused('expected_source', 'SECRET')])
def test_unknown_errors_never_echo_arguments(error):
    assert m.finite_error(error) == {'code': 'unknown'}


def test_profile_is_nonauthorizing_and_fixed():
    result = m.profile_record()
    assert result['endpoints'] == list(m.ENDPOINTS)
    assert result['max_application_dispatches'] == 3 and result['code_source_id_supplied'] is False
    assert result['expected_projection_binding_required_from_caller'] is True
    assert all(result[key] is False for key in m.FALSE_FLAGS)
    result['endpoints'].append('files/update')
    assert m.profile_record()['endpoints'] == list(m.ENDPOINTS)


@pytest.mark.parametrize('field', ['schema', 'project_id', 'target_name', 'projection_sha256',
    'expected_source', 'observation_complete', 'file_observation', 'failure_code', 'read_context',
    'stage', 'last_endpoint', 'last_event', 'application_dispatch_count', 'provider_request_count',
    *m.FALSE_FLAGS])
def test_output_requires_each_exact_key(supplied, field):
    result, _, _ = run(supplied)
    result.pop(field)
    with pytest.raises(m.EffectRefused, match='^observation_shape$'): m.validate_observation(result)


@pytest.mark.parametrize('field', list(m.FALSE_FLAGS))
def test_no_output_authority_flag_can_become_true(supplied, field):
    result, _, _ = run(supplied)
    result[field] = True
    with pytest.raises(m.EffectRefused, match='^observation_shape$'): m.validate_observation(result)


@pytest.mark.parametrize('field,value', [('schema', 'other'), ('project_id', True),
    ('target_name', 'main.py'), ('projection_sha256', '0' * 64), ('expected_source', {}),
    ('observation_complete', 1), ('stage', 'files'), ('last_endpoint', 'files/update'),
    ('last_event', 'intent'), ('application_dispatch_count', 2), ('provider_request_count', 0),
    ('failure_code', 'unknown'), ('read_context', None), ('file_observation', None)])
def test_success_output_coherence(supplied, field, value):
    result, _, _ = run(supplied)
    result[field] = value
    with pytest.raises(m.EffectRefused, match='^observation_shape$'): m.validate_observation(result)


@pytest.mark.parametrize('field,value', [('classification', 'permitted_placeholder'),
    ('classification', 'different_source'), ('classification', 'unknown'), ('byte_count', True),
    ('byte_count', -1), ('byte_count', 64001), ('sha256', 'x'), ('extra', 'secret')])
def test_file_output_classification_is_hash_and_size_consistent(supplied, field, value):
    result, _, _ = run(supplied)
    result['file_observation'][field] = value
    with pytest.raises(m.EffectRefused, match='^observation_shape$'): m.validate_observation(result)


@pytest.mark.parametrize('field,value', [('stage', 'complete'), ('stage', 'files'),
    ('last_endpoint', 'files/update'), ('last_event', 'observed'),
    ('application_dispatch_count', 0), ('failure_code', None), ('provider_request_count', 0)])
def test_failure_output_coherence(supplied, field, value):
    def failed(*args): raise RuntimeError('secret')
    result, _, _ = run(supplied, request=failed)
    result[field] = value
    with pytest.raises(m.EffectRefused, match='^observation_shape$'): m.validate_observation(result)


@pytest.mark.parametrize('field,value', [('present', False), ('kind', 'absent'),
    ('count', 0), ('boolean_value', None), ('sha256', '0' * 64), ('extra', None)])
def test_diagnostic_boolean_output_is_hash_consistent(supplied, field, value):
    result, _, _ = run(supplied)
    result['read_context']['code_running'][field] = value
    with pytest.raises(m.EffectRefused, match='^observation_shape$'): m.validate_observation(result)


@pytest.mark.parametrize('known', [None, True, False])
@pytest.mark.parametrize('kind', ['number', 'string', 'array', 'object'])
def test_known_scalar_hash_cannot_be_retyped_in_output(supplied, known, kind):
    result, _, _ = run(supplied)
    result['read_context']['code_running'] = {'present': True, 'kind': kind,
        'count': 1 if kind in ('array', 'object') else None,
        'boolean_value': None, 'sha256': m._sha(m._canonical(known))}
    with pytest.raises(m.EffectRefused, match='^observation_shape$'): m.validate_observation(result)


def test_unknown_output_key_and_hidden_subclass_refuse(supplied):
    result, _, _ = run(supplied)
    result['unknown'] = 'secret'
    with pytest.raises(m.EffectRefused, match='^observation_shape$'): m.validate_observation(result)
    class String(str): pass
    result.pop('unknown')
    result['target_name'] = String(m.TARGET_NAME)
    with pytest.raises(m.EffectRefused, match='^access_json_shape$'): m.validate_observation(result)
