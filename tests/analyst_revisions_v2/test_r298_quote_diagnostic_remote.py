"""Synthetic injected A13 protocol; projection receiver has its own tests."""
import copy
import json
from types import SimpleNamespace
from pathlib import Path

import pytest

from scripts import arv2_r298_quote_diagnostic_remote as m


@pytest.fixture
def cloud(monkeypatch):
    old = {name: ('# exact old ' + name + '\n').encode('ascii') for name in m.previous.ready.SOURCE_NAMES}
    sources = dict(old)
    for name in m.EDIT_NAMES: sources[name] += b'# three labels only\n'
    pairs = tuple(sorted(sources.items()))
    profile = {'schema': m.previous.frozen.runtime.SCHEMA, 'package_sha256': m.previous.ready.PACKAGE_SHA256,
               'universe_count': 6, 'ar_percent': 0, 'candidate_id': 'arv2-newrule-6-ar0-2026-v1'}
    profile['profile_sha256'] = m.previous.frozen.runtime.targets.digest(profile)
    monkeypatch.setattr(m, 'PROFILE_SHA256', profile['profile_sha256'])
    raw = b'{"synthetic":"public diagnostic projection"}'
    monkeypatch.setattr(m, 'PROJECTION_SHA256', m.sha(raw))
    monkeypatch.setattr(m, 'SOURCE_MANIFEST_SHA256', m.sha(m.canonical(m.QuoteDiagnostic._manifest(sources, m.PROJECTION_SHA256))))
    monkeypatch.setattr(m.previous, 'SOURCE_MANIFEST_SHA256',
        m.sha(m.canonical(m.QuoteDiagnostic._manifest(old, m.previous.ready.PROJECTION_SHA256))))
    def receiver(record_bytes, supplied_pairs, *, expected_projection_sha256, expected_profile_sha256):
        assert record_bytes == raw and supplied_pairs == pairs
        assert expected_projection_sha256 == m.PROJECTION_SHA256
        assert expected_profile_sha256 == m.PROFILE_SHA256
        return {}, copy.deepcopy(profile), tuple(pairs)
    monkeypatch.setattr(m.projection, 'validate_public_projection', receiver)
    organization = 'a' * 32
    monkeypatch.setattr(m.previous.ready.access, 'ORGANIZATION_SHA256', m.sha(organization.encode('ascii')))
    owner = {'owner': True, 'uid': 123, 'publicId': 'synthetic', 'name': 'Synthetic', 'permission': 'write', 'liveControl': True}
    monkeypatch.setattr(m.previous.ready.access, 'OWNER_ROW_SHA256', m.sha(m.canonical(owner)))
    project = {'projectId': m.PROJECT_ID, 'organizationId': organization, 'ownerId': 123,
        'name': m.previous.ready.access.PROJECT_NAME, 'language': 'Py', 'owner': True,
        'codeRunning': False, 'collaborators': [copy.deepcopy(owner)]}
    manual = {'projectId': m.PROJECT_ID, 'backtestId': m.previous.ready.predecessor.MANUAL_BACKTEST_ID,
              'name': m.previous.ready.predecessor.MANUAL_BACKTEST_NAME, 'status': 'Completed.'}
    a12 = {'projectId': m.PROJECT_ID, 'backtestId': m.A12_ID,
           'name': m.previous.BACKTEST_NAME, 'status': 'Runtime Error', 'compileId': m.previous.COMPILE_ID}
    s = SimpleNamespace(raw=raw, pairs=pairs, old=old, sources=sources, profile=profile, project=project,
        dedicated={'collaborators': [copy.deepcopy(owner)], 'userPermissions': 'write', 'userLiveControl': True},
        manual=manual, a12=a12, files=copy.deepcopy(old), calls=[], events=[], mutation=None, time=0.,
        compile_id='compile-new-a13', compile_state='BuildSuccess', compile_error='', busy=False,
        create_state='In Queue...', own=None, stats={m.previous.frozen.runtime.META_STATISTIC: '{}',
            m.previous.frozen.runtime.MONTHLY_STATISTIC: '{}'}, validation=[], detail_error=None)
    def journal(marker, event): s.events.append((marker, copy.deepcopy(event)))
    def request(endpoint, payload):
        assert s.events[-1][1] == {'event': 'intent', 'endpoint': endpoint, 'sha256': m.sha(m.canonical(payload))}
        s.calls.append((endpoint, copy.deepcopy(payload)))
        if endpoint == 'projects/read': value = {'projects': [copy.deepcopy(s.project)]}
        elif endpoint == 'projects/collaboration/read': value = copy.deepcopy(s.dedicated)
        elif endpoint == 'projects/collaboration/lock/acquire': value = {}
        elif endpoint == 'backtests/list':
            rows = [copy.deepcopy(s.manual), copy.deepcopy(s.a12)] + ([copy.deepcopy(s.own)] if s.own else [])
            value = {'projectId': m.PROJECT_ID, 'backtests': rows, 'count': len(rows)}
        elif endpoint == 'files/read':
            value = {'files': [{'projectId': m.PROJECT_ID, 'name': name, 'content': data.decode('ascii')}
                               for name, data in s.files.items()]}
        elif endpoint == 'files/update':
            s.files[payload['name']] = payload['content'].encode('ascii')
            value = {}
        elif endpoint == 'compile/create': value = {'projectId': m.PROJECT_ID, 'compileId': s.compile_id}
        elif endpoint == 'compile/read':
            value = {'projectId': m.PROJECT_ID, 'compileId': s.compile_id, 'state': s.compile_state, 'error': s.compile_error}
        elif endpoint == 'projects/nodes/read':
            value = {'nodes': {'backtest': [{'busy': s.busy, 'active': True}]}, 'autoSelectNode': False}
        elif endpoint == 'backtests/create':
            s.own = {'projectId': m.PROJECT_ID, 'backtestId': 'a13-new-job',
                'name': m.BACKTEST_NAME, 'compileId': s.compile_id, 'status': s.create_state}
            value = {'backtest': copy.deepcopy(s.own)}
        elif endpoint == 'backtests/read':
            value = {'backtest': dict(copy.deepcopy(s.own), statistics=copy.deepcopy(s.stats))}
            if s.detail_error is not None: value['backtest']['error'] = s.detail_error
        else: pytest.fail('forbidden injected endpoint')
        value['success'] = True
        if s.mutation: s.mutation(endpoint, payload, value)
        return value
    def validator(stats, *, expected_profile):
        s.validation.append((copy.deepcopy(stats), copy.deepcopy(expected_profile)))
        return {'meta': {'bound': True}, 'monthly': {'bound': True}}
    monkeypatch.setattr(m.previous.frozen.runtime, 'validate_result_statistics', validator)
    s.request, s.journal = request, journal
    s.runner = m.QuoteDiagnostic(raw, pairs, request=request, journal=journal, clock=lambda: s.time)
    return s


def prepared(s):
    value = s.runner.prepare_once()
    assert value['compile_id'] == s.compile_id
    return s.runner.poll_compile(0)


def launched(s):
    prepared(s)
    value = s.runner.launch_once()
    assert value['state'] == 'launched'
    return value


def completed(s):
    launched(s)
    s.own['status'] = 'Completed.'
    return s.runner.poll_status(0)


def test_fixed_diagnostic_contract():
    assert m.ATTEMPT == 13 and m.PROJECT_ID == 38364439
    assert m.PROJECTION_SHA256 == '1f366e402b3754e9f1f8ba89d08f250df771431b2ae98d19da953cfb722db293'
    assert m.PROFILE_SHA256 == '1133de6d18fb8d8b5355fb906d5a2f38f97e1f97460b80bd1f4c9014e901ad70'
    assert m.SOURCE_MANIFEST_SHA256 == 'ed8bd6c988d6d9fc31586b9dd8df058e8235a79702f52d78a172c31a1e64b190'
    assert m.EDIT_NAMES == ('newrule_comparison_qc_runtime.py', 'main.py')
    assert (m.COMPILE_POLLS, m.COMPILE_INTERVAL, m.STATUS_POLLS, m.STATUS_INTERVAL) == (120, 1, 240, 60)
    assert m.profile_record()['diagnostic_only'] is True


def test_prepare_edits_only_two_exact_sources_then_creates_one_compile(cloud):
    receipt = cloud.runner.prepare_once()
    assert cloud.files == cloud.sources
    writes = [body for endpoint, body in cloud.calls if endpoint == 'files/update']
    assert [body['name'] for body in writes] == list(m.EDIT_NAMES)
    for body in writes: assert body['content'].encode('ascii') == cloud.sources[body['name']]
    assert sum(endpoint == 'compile/create' for endpoint, _ in cloud.calls) == 1
    assert sum(endpoint == 'projects/collaboration/lock/acquire' for endpoint, _ in cloud.calls) == 1
    assert len(cloud.calls) == 18
    assert receipt['diagnostic_only'] is True and receipt['compile_id'] == cloud.compile_id
    count = len(cloud.calls)
    with pytest.raises(m.Refused, match='^prepare_once$'): cloud.runner.prepare_once()
    assert len(cloud.calls) == count


@pytest.mark.parametrize('change', ['stub', 'oldmain', 'unknown_file', 'missing', 'duplicate', 'nonascii', 'project'])
def test_preexisting_cloud_must_equal_exact_a11_manifest_before_any_edit(cloud, change):
    def mutate(endpoint, body, value):
        if endpoint != 'files/read': return
        rows = value['files']
        if change == 'stub': rows[0]['content'] = '#'
        if change == 'oldmain': next(row for row in rows if row['name'] == 'main.py')['content'] += '# changed'
        if change == 'unknown_file': rows[0]['name'] = 'unknown.py'
        if change == 'missing': rows.pop()
        if change == 'duplicate': rows[-1] = dict(rows[0])
        if change == 'nonascii': rows[0]['content'] = '\u00e9'
        if change == 'project': rows[0]['projectId'] = True
    cloud.mutation = mutate
    with pytest.raises(m.Refused): cloud.runner.prepare_once()
    assert len(cloud.calls) == 4


@pytest.mark.parametrize('target', ['manual_id', 'manual_status', 'a12_id', 'a12_name', 'a12_status', 'a12_compile', 'extra', 'count'])
def test_exact_manual_and_failed_a12_history_required(cloud, target):
    def mutate(endpoint, body, value):
        if endpoint != 'backtests/list': return
        rows = value['backtests']
        if target == 'manual_id': rows[0]['backtestId'] = 'unknown'
        if target == 'manual_status': rows[0]['status'] = 'Runtime Error'
        if target == 'a12_id': rows[1]['backtestId'] = 'unknown'
        if target == 'a12_name': rows[1]['name'] = 'unknown'
        if target == 'a12_status': rows[1]['status'] = 'Completed.'
        if target == 'a12_compile': rows[1]['compileId'] = 'other'
        if target == 'extra': rows.append(dict(rows[1]))
        if target == 'count': value['count'] = True
    cloud.mutation = mutate
    with pytest.raises(ValueError): cloud.runner.prepare_once()
    assert len(cloud.calls) == 3


@pytest.mark.parametrize('change', ['running', 'owner', 'public', 'dedicated', 'extra'])
def test_access_refuses_before_edit_lock_or_source_reads(cloud, change):
    if change == 'running': cloud.project['codeRunning'] = True
    if change == 'owner': cloud.project['owner'] = False
    if change == 'public': cloud.project['public'] = True
    if change == 'dedicated': cloud.dedicated['userPermissions'] = 'read'
    if change == 'extra': cloud.project['collaborators'].append({'owner': False})
    with pytest.raises(m.previous.ready.access.AccessRefused): cloud.runner.prepare_once()
    assert len(cloud.calls) == 2


def test_concurrent_source_change_after_lock_stops_before_writes(cloud):
    def mutate(endpoint, body, value):
        if endpoint == 'projects/collaboration/lock/acquire': cloud.files['main.py'] += b'# concurrent'
    cloud.mutation = mutate
    with pytest.raises(m.Refused, match='^old_source$'): cloud.runner.prepare_once()
    assert not any(endpoint == 'files/update' for endpoint, _ in cloud.calls)


@pytest.mark.parametrize('field,bad', [('compileId', ''), ('compileId', m.previous.COMPILE_ID), ('projectId', True)])
def test_compile_create_identity_refusal_spends_prepare(cloud, field, bad):
    def mutate(endpoint, body, value):
        if endpoint == 'compile/create': value[field] = bad
    cloud.mutation = mutate
    with pytest.raises(m.Refused): cloud.runner.prepare_once()
    with pytest.raises(m.Refused, match='^prepare_once$'): cloud.runner.prepare_once()


def test_compile_identity_survives_later_journal_failure(cloud):
    def journal(marker, event):
        if marker == 'compile-receipt': raise RuntimeError('synthetic fsync failure')
        cloud.events.append((marker, copy.deepcopy(event)))
    cloud.runner._journal = journal
    with pytest.raises(RuntimeError): cloud.runner.prepare_once()
    assert cloud.runner.compile_receipt['compile_id'] == cloud.compile_id


def test_compile_polls_strict_interval_sequential_budget(cloud):
    cloud.runner.prepare_once()
    cloud.compile_state = 'Building'
    cloud.runner.poll_compile(0)
    with pytest.raises(m.Refused, match='^wait$'): cloud.runner.poll_compile(1)
    with pytest.raises(m.Refused, match='^compile_budget$'): cloud.runner.poll_compile(0)
    for index in range(1, 120):
        cloud.time = index
        cloud.runner.poll_compile(index)
    cloud.time += 1
    with pytest.raises(m.Refused, match='^compile_budget$'): cloud.runner.poll_compile(120)


def test_compile_error_is_finite_terminal_and_blocks_launch(cloud):
    cloud.runner.prepare_once()
    cloud.compile_state = 'BuildError'
    cloud.compile_error = 'TypeError: private source details never retained'
    assert cloud.runner.poll_compile(0)['state'] == 'BuildError'
    receipt = cloud.runner.terminal_receipt
    assert receipt['status'] == 'BuildError' and receipt['failure_evidence']['python_error_category'] == 'TypeError'
    assert 'private source' not in json.dumps(receipt)
    m.validate_terminal_receipt(receipt)
    with pytest.raises(m.Refused, match='^launch_once$'): cloud.runner.launch_once()


@pytest.mark.parametrize('field,bad', [('compileId', 'other'), ('state', 'Completed.'), ('projectId', True)])
def test_compile_poll_bound_to_new_compile_and_enum(cloud, field, bad):
    cloud.runner.prepare_once()
    def mutate(endpoint, body, value):
        if endpoint == 'compile/read': value[field] = bad
    cloud.mutation = mutate
    with pytest.raises(m.Refused, match='^compile$'): cloud.runner.poll_compile(0)


def test_busy_capacity_and_new_attempt_never_cancel_other_job(cloud):
    prepared(cloud)
    cloud.busy = True
    for index in range(3):
        cloud.time = index * 60
        assert cloud.runner.launch_once()['state'] == 'wait'
    cloud.time += 60
    with pytest.raises(m.Refused, match='^capacity_budget$'): cloud.runner.launch_once()
    assert not any(endpoint == 'backtests/create' for endpoint, _ in cloud.calls)


@pytest.mark.parametrize('status', ['In Queue...', 'In Progress...', 'Completed.', 'Runtime Error'])
def test_launch_once_accepts_real_pending_and_fastterminal(cloud, status):
    cloud.create_state = status
    result = launched(cloud)
    assert (result['terminal_receipt'] is not None) is (status in m.TERMINAL)
    assert result['launch_receipt']['compile_id'] == cloud.compile_id
    assert result['launch_receipt']['attempt'] == 13
    with pytest.raises(m.Refused, match='^launch_once$'): cloud.runner.launch_once()


@pytest.mark.parametrize('code', list(m.projection.FAILURE_CODES))
@pytest.mark.parametrize('field', ['error', 'errorMessage', 'errors'])
def test_new_failure_codes_projected_from_bounded_stacks_without_raw_retention(code, field):
    text = 'Runtime Error: NewruleError: ' + code + '\n at _current_execution_price in runtime.py:line 17\nprivate payload'
    row = {field: [text] if field == 'errors' else text}
    evidence = m.failure_evidence(row, 'runtime_error')
    assert evidence['known_runtime_code'] == code
    assert evidence['known_runtime_code_sha256'] == m.sha(code.encode('ascii'))
    assert evidence['raw_error_retained'] is False and evidence['cause_authenticated'] is False
    assert 'private payload' not in json.dumps(evidence)


@pytest.mark.parametrize('text', ['prefixexecution_price_missing', 'execution_price_missing_suffix',
    'NewruleError: execution_price_missing_suffix', 'source = "execution_price_missing"',
    'execution_price_missing and other private text', 'BadNewruleError: execution_price_missing',
    '\ud800', 'x' * (m.MAX_ERROR_BYTES + 1)])
def test_partial_arbitrary_or_unbounded_failure_text_remains_unknown(text):
    assert m.failure_evidence({'error': text}, 'runtime_error')['known_runtime_code'] is None


def test_conflicting_known_error_codes_remain_unknown():
    text = 'NewruleError: execution_price_missing\nNewruleError: execution_price_fill_forward'
    evidence = m.failure_evidence({'error': text}, 'runtime_error')
    assert evidence['known_runtime_code'] is None and evidence['known_runtime_code_sha256'] is None


def test_own_error_from_status_is_new_finite_evidence(cloud):
    launched(cloud)
    cloud.own['status'] = 'Runtime Error'
    cloud.own['error'] = 'NewruleError: execution_price_end_not_current\n at runtime frame private payload'
    result = cloud.runner.poll_status(0)
    assert result['failure_evidence']['known_runtime_code'] == 'execution_price_end_not_current'
    assert cloud.runner.terminal_receipt['status'] == 'Runtime Error'
    with pytest.raises(m.Refused, match='^not_completed$'): cloud.runner.read_once()


@pytest.mark.parametrize('change', ['a12_status', 'own_id', 'own_name', 'own_compile', 'extra'])
def test_status_requires_manual_a12_and_own_exact_census(cloud, change):
    launched(cloud)
    def mutate(endpoint, body, value):
        if endpoint != 'backtests/list': return
        if change == 'a12_status': value['backtests'][1]['status'] = 'Completed.'
        if change == 'own_id': value['backtests'][2]['backtestId'] = 'unknown'
        if change == 'own_name': value['backtests'][2]['name'] = 'unknown'
        if change == 'own_compile': value['backtests'][2]['compileId'] = 'unknown'
        if change == 'extra': value['backtests'].append(dict(value['backtests'][2]))
    cloud.mutation = mutate
    with pytest.raises(ValueError): cloud.runner.poll_status(0)


def test_result_uses_new_profile_one_aggregate_and_validates_again_without_files(cloud):
    completed(cloud)
    cloud.stats['private extra not forwarded'] = 'not retained'
    result = cloud.runner.read_once()
    assert result['profile_sha256'] == m.PROFILE_SHA256
    assert result['expected_profile'] == cloud.profile
    assert result['cell_completed'] is True and result['family_comparable'] is False
    assert set(cloud.validation[0][0]) == {m.previous.frozen.runtime.META_STATISTIC, m.previous.frozen.runtime.MONTHLY_STATISTIC}
    count = len(cloud.calls)
    m.validate_result_receipt(result)
    assert len(cloud.calls) == count
    with pytest.raises(m.Refused, match='^result_once$'): cloud.runner.read_once()


@pytest.mark.parametrize('field,bad', [('status', 'In Progress...'), ('projectId', True),
    ('backtestId', 'unknown'), ('compileId', 'unknown'), ('name', 'unknown')])
def test_result_identity_refusal_never_admits_cell_or_retries(cloud, field, bad):
    completed(cloud)
    def mutate(endpoint, body, value):
        if endpoint == 'backtests/read': value['backtest'][field] = bad
    cloud.mutation = mutate
    with pytest.raises(m.Refused, match='^result_identity$'): cloud.runner.read_once()
    assert cloud.validation == []
    with pytest.raises(m.Refused, match='^result_once$'): cloud.runner.read_once()


@pytest.mark.parametrize('endpoint', ['projects/create', 'files/create', 'files/delete', 'backtests/delete',
    'projects/collaboration/delete', 'live/create'])
def test_forbidden_endpoints_stop_before_any_intent(cloud, endpoint):
    with pytest.raises(m.Refused, match='^endpoint$'):
        cloud.runner._rpc('forged', endpoint, {'projectId': m.PROJECT_ID})
    assert cloud.calls == cloud.events == []


def test_direct_write_cannot_bypass_prepare_or_hash_binding(cloud):
    with pytest.raises(m.Refused, match='^payload$'):
        cloud.runner._rpc('forged', 'files/update', {'projectId': m.PROJECT_ID, 'codeSourceId': m.CODE_SOURCE_ID,
            'name': 'main.py', 'content': 'unreviewed'})
    assert cloud.calls == []


@pytest.mark.parametrize('field,bad', [('attempt', True), ('attempt', 12), ('project_id', True),
    ('compile_id', m.previous.COMPILE_ID), ('profile_sha256', '0' * 64), ('diagnostic_only', False),
    ('paper_or_live_ready', 0), ('source_manifest_sha256', '0' * 64)])
def test_compile_receipt_pure_binding_rejects_aliases_and_old_identity(cloud, field, bad):
    receipt = cloud.runner.prepare_once()
    receipt[field] = bad
    with pytest.raises(m.Refused, match='^compile_receipt$'): m.validate_compile_receipt(receipt)


def test_genuine_public_projection_receiver_and_fixed_source_manifest_interoperate():
    research = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2/research/analyst_revisions_v2_qc')
    comparison = m.projection.comparison
    names = set(comparison.bridge.parent.SOURCE_PINS) | set(comparison.NEW_SOURCE_PINS) | {comparison.HOST_SOURCE_NAME}
    sources = {name: (research / name).read_bytes() for name in names}
    spec = comparison.public_specification(sources=sources,
        expected_host_source_pins={comparison.HOST_SOURCE_NAME: m.sha(sources[comparison.HOST_SOURCE_NAME])})
    pairs = tuple((item.project_path, item.source_bytes) for item in spec.cells[0].source_files)
    patcher = (research.parent.parent / 'scripts' / m.projection.PATCHER_NAME).read_bytes()
    projected = m.projection.public_specification(pairs, patcher_source_bytes=patcher,
        expected_patcher_sha256=m.sha(patcher))
    def unexpected(*args): pytest.fail('constructor must not dispatch or journal')
    runner = m.QuoteDiagnostic(projected.record_bytes, projected.source_pairs,
        request=unexpected, journal=unexpected)
    assert runner.compile_receipt is runner.launch_receipt is runner.terminal_receipt is None
    assert runner._profile['profile_sha256'] == m.PROFILE_SHA256


@pytest.mark.parametrize('code', list(m.projection.FAILURE_CODES))
@pytest.mark.parametrize('prefix', ['', 'Runtime Error: NewruleError: '])
def test_closed_failure_context_is_retained_without_raw_source_or_prices(code, prefix):
    text = prefix + code + '|cache=quote_bar|trade=fresh_non_fill_forward|quote=stale|price_trade=equal'
    evidence = m.failure_evidence({'error': text + '\n private source frame and price123'}, 'runtime_error')
    assert evidence['known_runtime_code'] == code
    assert evidence['diagnostic_context'] == {'schema': 'arv2-quote-freshness-context-v1', 'predicate': code,
        'cache_class': 'quote_bar', 'trade_bar': 'fresh_non_fill_forward', 'quote_bar': 'stale', 'price_trade': 'equal'}
    assert 'price123' not in json.dumps(evidence)
    m._validate_failure(evidence, 'runtime_error')


def test_conflicting_closed_contexts_preserve_code_but_not_ambiguous_context():
    first = 'execution_price_end_not_current|cache=quote_bar|trade=fresh_non_fill_forward|quote=stale|price_trade=equal'
    second = 'execution_price_end_not_current|cache=trade_bar|trade=stale|quote=stale|price_trade=different'
    result = m.failure_evidence({'error': first + '\n' + second}, 'runtime_error')
    assert result['known_runtime_code'] == 'execution_price_end_not_current'
    assert result['diagnostic_context'] is None


@pytest.mark.parametrize('field,bad', [('cache_class', 'private cached object'), ('trade_bar', 1),
    ('quote_bar', 'unrecognized'), ('price_trade', '123.45'), ('predicate', 'execution_price_fill_forward'),
    ('schema', 'wrong'), ('extra', 'secret')])
def test_terminal_context_validator_rejects_unrecognized_values_or_predicate_mismatch(field, bad):
    evidence = m.failure_evidence({'error': 'execution_price_end_not_current|cache=quote_bar|trade=missing|quote=stale|price_trade=unknown'}, 'runtime_error')
    evidence['diagnostic_context'][field] = bad
    with pytest.raises(ValueError): m._validate_failure(evidence, 'runtime_error')


def failed(s):
    launched(s)
    s.own['status'] = 'Runtime Error'
    return s.runner.poll_status(0)


def test_runtime_error_detail_supplies_context_when_list_omits_it(cloud):
    failed(cloud)
    assert cloud.runner.terminal_receipt['failure_evidence']['diagnostic_context'] is None
    cloud.detail_error = ('Runtime Error: NewruleError: execution_price_end_not_current'
        '|cache=quote_bar|trade=fresh_non_fill_forward|quote=stale|price_trade=equal\n'
        ' private source, symbol ABC and price123.45')
    cloud.stats['licensed-extra'] = 'private statistic never retained'
    result = cloud.runner.read_failure_once()
    assert result['status'] == 'Runtime Error'
    assert result['failure_evidence']['known_runtime_code'] == 'execution_price_end_not_current'
    assert result['failure_evidence']['diagnostic_context']['cache_class'] == 'quote_bar'
    assert result == cloud.runner.terminal_receipt
    assert cloud.validation == []
    assert 'private statistic' not in json.dumps(cloud.events)
    assert 'price123.45' not in json.dumps(result)
    assert 'licensed-extra' not in json.dumps(result)
    assert sum(endpoint == 'backtests/read' for endpoint, _ in cloud.calls) == 1
    assert cloud.events[-1][0] == 'diagnostic-failure-receipt'
    count = len(cloud.calls)
    with pytest.raises(m.Refused, match='^result_once$'): cloud.runner.read_failure_once()
    with pytest.raises(m.Refused, match='^result_once$'): cloud.runner.read_once()
    assert len(cloud.calls) == count


@pytest.mark.parametrize('field,bad', [('projectId', True), ('backtestId', 'other'),
    ('name', 'other'), ('status', 'Completed.'), ('compileId', 'other')])
def test_failure_detail_mismatch_keeps_prior_terminal_and_consumes_single_read(cloud, field, bad):
    failed(cloud)
    before = cloud.runner.terminal_receipt
    def mutate(endpoint, body, value):
        if endpoint == 'backtests/read': value['backtest'][field] = bad
    cloud.mutation = mutate
    with pytest.raises(m.Refused, match='^result_identity$'): cloud.runner.read_failure_once()
    assert cloud.runner.terminal_receipt == before
    assert cloud.validation == []
    with pytest.raises(m.Refused, match='^result_once$'): cloud.runner.read_failure_once()
    assert sum(endpoint == 'backtests/read' for endpoint, _ in cloud.calls) == 1


@pytest.mark.parametrize('stage', ['before_prepare', 'compiled', 'pending', 'completed', 'compile_error'])
def test_error_detail_needs_exact_runtime_error_terminal_before_any_new_contact(cloud, stage):
    if stage == 'compiled': prepared(cloud)
    elif stage == 'pending': launched(cloud)
    elif stage == 'completed': completed(cloud)
    elif stage == 'compile_error':
        cloud.runner.prepare_once()
        cloud.compile_state = 'BuildError'
        cloud.runner.poll_compile(0)
    count = len(cloud.calls)
    with pytest.raises(m.Refused, match='^status$'): cloud.runner.read_failure_once()
    assert len(cloud.calls) == count


def test_error_detail_refuses_source_drift_before_detail_request(cloud):
    failed(cloud)
    cloud.files['main.py'] += b'# concurrent drift'
    with pytest.raises(m.Refused, match='^source_hash$'): cloud.runner.read_failure_once()
    assert not any(endpoint == 'backtests/read' for endpoint, _ in cloud.calls)
    with pytest.raises(m.Refused, match='^result_once$'): cloud.runner.read_failure_once()


def test_error_detail_missing_or_unrecognized_error_is_authenticated_unknown(cloud):
    failed(cloud)
    cloud.detail_error = 'Unrecognized private response; not an invented cause'
    result = cloud.runner.read_failure_once()
    assert result['failure_evidence']['known_runtime_code'] is None
    assert result['failure_evidence']['diagnostic_context'] is None
    assert result['failure_evidence']['raw_error_retained'] is False
    assert cloud.validation == []


def test_detail_conflicting_known_code_preserves_original_terminal_and_spends_read(cloud):
    launched(cloud)
    cloud.own['status'] = 'Runtime Error'
    cloud.own['error'] = 'NewruleError: execution_price_missing'
    cloud.runner.poll_status(0)
    before = cloud.runner.terminal_receipt
    cloud.detail_error = 'NewruleError: execution_price_fill_forward'
    with pytest.raises(m.Refused, match='^response$'): cloud.runner.read_failure_once()
    assert cloud.runner.terminal_receipt == before
    with pytest.raises(m.Refused, match='^result_once$'): cloud.runner.read_failure_once()
    assert sum(endpoint == 'backtests/read' for endpoint, _ in cloud.calls) == 1


def test_detail_conflicting_closed_context_preserves_original_terminal_and_spends_read(cloud):
    launched(cloud)
    cloud.own['status'] = 'Runtime Error'
    cloud.own['error'] = ('NewruleError: execution_price_end_not_current'
        '|cache=quote_bar|trade=fresh_non_fill_forward|quote=stale|price_trade=equal')
    cloud.runner.poll_status(0)
    before = cloud.runner.terminal_receipt
    cloud.detail_error = ('NewruleError: execution_price_end_not_current'
        '|cache=trade_bar|trade=stale|quote=stale|price_trade=different')
    with pytest.raises(m.Refused, match='^response$'): cloud.runner.read_failure_once()
    assert cloud.runner.terminal_receipt == before
    with pytest.raises(m.Refused, match='^result_once$'): cloud.runner.read_failure_once()
    assert sum(endpoint == 'backtests/read' for endpoint, _ in cloud.calls) == 1


def test_unknown_detail_does_not_erase_known_list_code_or_context(cloud):
    launched(cloud)
    cloud.own['status'] = 'Runtime Error'
    cloud.own['error'] = ('NewruleError: execution_price_end_not_current'
        '|cache=quote_bar|trade=fresh_non_fill_forward|quote=stale|price_trade=equal')
    cloud.runner.poll_status(0)
    before = cloud.runner.terminal_receipt
    cloud.detail_error = 'Unrecognized bounded detail observation'
    result = cloud.runner.read_failure_once()
    assert result == before
    assert result['failure_evidence']['diagnostic_context']['cache_class'] == 'quote_bar'
    assert result['failure_evidence']['cause_authenticated'] is False
