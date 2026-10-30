"""Entire-wire status validation and readonly custody; all I/O is synthetic."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

import pytest

from research.target_price_revisions_qc import comparison_20261030_job_status as m

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
JOB = 'a' * 32
PROJECT = 38609836
TOKEN = 'SYNTHETIC-STATUS-TOKEN'


def wire(value):
    return json.dumps(value, separators=(',', ':'), allow_nan=False).encode()


def response(**extra):
    return wire({'success': True, 'projectId': PROJECT,
        'backtest': {'backtestId': JOB, 'projectId': PROJECT,
            'status': 'Completed', 'completed': True, **extra}})


def project(raw):
    return m.project_status(raw, credential=TOKEN, project_id=PROJECT, backtest_id=JOB)


@pytest.fixture(autouse=True)
def deny_native(monkeypatch):
    def deny(*_, **__):
        raise AssertionError('real credential/network/subprocess forbidden')
    monkeypatch.setattr(m.api.ops, 'credential', deny)
    monkeypatch.setattr(m.api.http.client, 'HTTPSConnection', deny)
    monkeypatch.setattr(m.api.subprocess, 'run', deny)
    if sys.platform != 'darwin':
        def custody(*_, **__):
            pytest.skip('POSIX Mac custody fixture is not Windows custody proof')
        monkeypatch.setattr(m.api.ops, '_custody', custody)


def registry():
    return {'schema': 'tpr-cmp28-five-project-bindings-v1',
        'round_id': 'TPR-CMP28-R107-20261029A', 'owner_instruction_sha256': 'b'*64,
        'git_head': 'a'*40,
        'adapter_source_sha256': m.api.projects.ADAPTER_SOURCE_SHA256
            if hasattr(m.api.projects, 'ADAPTER_SOURCE_SHA256') else 'c'*64,
        'organization_id': 'a'*32, 'owner_id': 123,
        'baseline_receipt_sha256': 'd'*64,
        'privacy_basis': 'documented_private_default_and_observed_collaborators',
        'explicit_privacy_flag_observed': False, 'independent_native_origin_attested': False,
        'projects': {key: {'project_id': project,
            'name': 'TPR-CMP28-R107-20261029A-'+key,
            'organization_id': 'a'*32, 'owner_id': 123, 'language': 'Py',
            'create_receipt_sha256': m.api._sha(('create-'+key).encode()),
            'read_receipt_sha256': m.api._sha(('read-'+key).encode()),
            'collaboration_receipt_sha256': m.api._sha(('collaborators-'+key).encode()),
            'collaborator_count': 1, 'nonowner_collaborator_count': 0,
            'collaborators_sha256': '9'*64}
            for key, project in m.api.REGISTERED_PROJECTS.items()}}


def common(operation='TPR-CMP29-API-STATUS-SYNTHETIC'):
    sources = {name: m.api._sha((ROOT/name).read_bytes()) for name in m.REQUIRED_SOURCES}
    body = registry()
    body['adapter_source_sha256'] = sources[m.api.PROJECTS_MODULE]
    raw = wire(body)
    return dict(project_bindings_raw=raw,
        expected_project_bindings_sha256=m.api._sha(raw), arm='cap_tilt_100',
        candidate_config_sha256='c'*64, candidate_attempt=2,
        operation_id=operation, git_head='a'*40, source_hashes=sources,
        owner_instruction_sha256='b'*64,
        created_utc=(NOW-timedelta(seconds=1)).isoformat(),
        expires_utc=(NOW+timedelta(seconds=59)).isoformat(),
        backtest_id=JOB, mode='offline-fixture')


def plan():
    return m.prepare_plan(**common())


def run(tmp_path, *, raw=None, transport=None, clock=lambda: NOW, guard=lambda _: None):
    calls = []
    def native(endpoint, payload, seconds, maximum):
        calls.append((endpoint, json.loads(payload), seconds, maximum))
        return response() if raw is None else raw, 200, TOKEN
    result = m._execute_fixture(plan(), tmp_path/'native',
        transport=native if transport is None else transport, clock=clock, guard=guard)
    return result, calls


def test_projects_only_status_after_validating_large_discarded_tree():
    raw = response(charts=[{'x': index, 'y': '012345678901234567890123'} for index in range(75000)])
    assert 3000000 < len(raw) < m.MAX_BYTES
    with pytest.raises(m.api.e.EvidenceError):
        m.api.e.project_wire(raw, credential=TOKEN)
    result = project(raw)
    assert result['json_value_nodes'] > 100000
    assert result['entire_wire_validated'] is True
    assert result['backtest_id'] == JOB and result['backtest_completed'] is True
    assert result['backtest_status'] == 'Completed'
    assert result['original_wire_sha256'] == hashlib.sha256(raw).hexdigest()
    assert 'charts' not in result and result['financial_fields_projected'] is False
    assert result['economics_accepted'] is False


@pytest.mark.parametrize('raw', [
    b'{"success":true,"success":true}',
    b'{"success":true,"succ\\u0065ss":true}',
    response()+b'x',
    response()[:-1],
    response(charts='ignored').replace(b'"ignored"', b'NaN'),
    response(charts='ignored').replace(b'"ignored"', b'Infinity'),
    response(charts='ignored').replace(b'"ignored"', b'01'),
    response(charts='ignored').replace(b'"ignored"', b'1e129'),
    response(charts='ignored').replace(b'"ignored"', b'1e-129'),
    response(charts='ignored').replace(b'"ignored"', b'1'*129),
    response(charts='ignored').replace(b'"ignored"', b'"bad\x01"'),
    response(charts='ignored').replace(b'"ignored"', b'"\xff"'),
    response(charts='ignored').replace(b'"ignored"', b'[1,]'),
    response(charts='ignored').replace(b'"ignored"', b'{"x":1,}'),
    response(charts='ignored').replace(b'"ignored"', b'{"x":1,"x":2}'),
])
def test_rejects_invalid_discarded_values_entire_wire(raw):
    with pytest.raises(m.StatusRefusal):
        project(raw)


@pytest.mark.parametrize('raw', [
    response(charts=TOKEN),
    response(charts={TOKEN: 'x'}),
    response(charts=TOKEN).replace(TOKEN.encode(), b'\\u0053YNTHETIC-STATUS-TOKEN'),
    response(charts={TOKEN: 'x'}).replace(TOKEN.encode(), b'\\u0053YNTHETIC-STATUS-TOKEN'),
])
def test_credential_echo_in_discarded_value_or_key_refuses(raw):
    with pytest.raises(m.StatusRefusal):
        project(raw)


@pytest.mark.parametrize('change', [
    lambda body: body.update(success=False),
    lambda body: body.update(projectId=True),
    lambda body: body.update(projectId=38609822),
    lambda body: body['backtest'].update(projectId=38609822),
    lambda body: body['backtest'].update(backtestId='b'*32),
    lambda body: body['backtest'].pop('backtestId'),
    lambda body: body['backtest'].update(completed=1),
    lambda body: body['backtest'].update(status='invented'),
    lambda body: body.update(backtest=[]),
])
def test_exact_identity_types_and_known_status_required(change):
    body = json.loads(response())
    change(body)
    with pytest.raises(m.StatusRefusal):
        project(wire(body))


def test_depth_boundary_matches_historical_evidence():
    # Root/backtest/charts = depths0/1/2; scalar after30arrays reaches32.
    raw = response(charts='x').replace(b'"x"', b'['*30+b'0'+b']'*30)
    assert project(raw)['entire_wire_validated'] is True
    deep = response(charts='x').replace(b'"x"', b'['*31+b'0'+b']'*31)
    with pytest.raises(m.StatusRefusal):
        project(deep)


def test_wire_and_node_budget_are_separate_and_bounded():
    assert m.MAX_NODES == m.MAX_BYTES == 4*1024*1024
    with pytest.raises(m.StatusRefusal):
        project(b' '*m.MAX_BYTES+b'0')


def test_production_registry_and_source_closure_are_not_fixture_claims():
    args = common()
    args['mode'] = 'production'
    with pytest.raises(m.StatusRefusal):
        m.prepare_plan(**args)
    args = common()
    args['source_hashes'].pop(m.MODULE)
    with pytest.raises(m.StatusRefusal):
        m.prepare_plan(**args)
    args = common()
    args['source_hashes']['research/target_price_revisions_qc/unknown.py'] = 'f'*64
    with pytest.raises(m.StatusRefusal):
        m.prepare_plan(**args)


def test_plan_is_exactly_one_readonly_request_and_caller_mutation_cannot_change_it():
    args = common()
    prepared = m.prepare_plan(**args)
    args['source_hashes'][m.MODULE] = 'f'*64
    assert prepared['api_plan']['source_hashes'][m.MODULE] != 'f'*64
    requests = prepared['api_plan']['requests']
    assert len(requests) == 1
    assert requests[0]['endpoint'] == 'backtests/read'
    assert requests[0]['payload'] == {'projectId': PROJECT, 'backtestId': JOB}
    assert requests[0]['max_response_bytes'] == m.MAX_BYTES
    assert prepared['api_plan']['attempt_id'] is prepared['api_plan']['reserved_look_id'] is None


def test_native_fixture_claims_before_effect_and_retains_whole_valid_wire(tmp_path):
    result, calls = run(tmp_path)
    assert result['status'] == 'completed'
    assert calls == [('backtests/read', {'projectId': PROJECT, 'backtestId': JOB}, 30, m.MAX_BYTES)]
    assert result['metadata']['backtest_status'] == 'Completed'
    assert result['receipt_published'] is result['lock_cleanup_complete'] is True
    assert (tmp_path/'native'/result['raw_response']['name']).read_bytes() == response()
    assert len(list((tmp_path/'native').glob('*.request.spent.json'))) == 1
    assert result['actual_new_backtests'] == 0 and result['financial_outcome_looks_count'] is None


def test_echo_refusal_precedes_raw_retention(tmp_path):
    result, calls = run(tmp_path, raw=response(charts=TOKEN))
    assert result['status'] == 'failed_or_uncertain' and len(calls) == 1
    assert result['raw_response'] is result['metadata'] is None
    assert not list((tmp_path/'native').glob('*.response.raw'))


def test_spent_operation_cannot_repeat_effect(tmp_path):
    first, calls = run(tmp_path)
    assert first['status'] == 'completed'
    with pytest.raises(m.StatusRefusal):
        run(tmp_path)
    assert len(calls) == 1


def test_claim_expiry_prevents_native_effect(tmp_path, monkeypatch):
    clock = [NOW]
    original = m.api._publish
    def publish(root, name, raw):
        descriptor = original(root, name, raw)
        if name.endswith('.request.spent.json'):
            clock[0] = NOW+timedelta(seconds=90)
        return descriptor
    monkeypatch.setattr(m.api, '_publish', publish)
    result, calls = run(tmp_path, clock=lambda: clock[0])
    assert result['status'] == 'failed_or_uncertain' and calls == []
    assert result['request_claim'] is not None


def test_source_change_after_claim_prevents_native_effect(tmp_path, monkeypatch):
    changed = [False]
    original = m.api._publish
    def publish(root, name, raw):
        result = original(root, name, raw)
        if name.endswith('.request.spent.json'):
            changed[0] = True
        return result
    def guard(_):
        if changed[0]:
            raise m.StatusRefusal('synthetic source refusal')
    monkeypatch.setattr(m.api, '_publish', publish)
    result, calls = run(tmp_path, guard=guard)
    assert result['status'] == 'failed_or_uncertain' and calls == []


def test_fixture_cannot_use_actual_native_transport_or_lane_root(tmp_path):
    with pytest.raises(m.StatusRefusal):
        m._execute_fixture(plan(), tmp_path/'native', transport=m.api._native_request, clock=lambda: NOW)
    with pytest.raises(m.StatusRefusal):
        m._execute_fixture(plan(), m.api.LANE/'artifacts'/'fixture', transport=lambda *_: None, clock=lambda: NOW)
    with pytest.raises(m.StatusRefusal):
        m.execute_plan(plan())


@pytest.mark.parametrize('fatal', [KeyboardInterrupt, SystemExit])
def test_fatal_and_cancellation_have_body_free_receipts(tmp_path, fatal):
    def transport(*_):
        raise fatal(TOKEN)
    expected = m.StatusCancelled if fatal is KeyboardInterrupt else m.StatusFatal
    with pytest.raises(expected) as caught:
        run(tmp_path, transport=transport)
    report = caught.value.report
    assert report['receipt_published'] and report['lock_cleanup_complete']
    encoded = m.api._canonical(report)
    assert TOKEN.encode() not in encoded and TOKEN not in str(caught.value)


def test_receipt_publication_failure_is_honest(tmp_path, monkeypatch):
    original = m.api._publish
    def publish(root, name, raw):
        if name.endswith('.result.json'):
            raise OSError(TOKEN)
        return original(root, name, raw)
    monkeypatch.setattr(m.api, '_publish', publish)
    result, calls = run(tmp_path)
    assert len(calls) == 1 and result['status'] == 'failed_or_uncertain'
    assert result['receipt_published'] is False
    assert TOKEN.encode() not in m.api._canonical(result)


@pytest.mark.parametrize('fatal', [KeyboardInterrupt, SystemExit])
def test_preclaim_fatal_is_body_free_and_does_not_claim_receipt(tmp_path, monkeypatch, fatal):
    original = m.api._publish
    def publish(root, name, raw):
        if name.endswith('.operation.spent.json'):
            raise fatal(TOKEN)
        return original(root, name, raw)
    monkeypatch.setattr(m.api, '_publish', publish)
    expected = m.StatusCancelled if fatal is KeyboardInterrupt else m.StatusFatal
    with pytest.raises(expected) as caught:
        run(tmp_path)
    assert caught.value.report['receipt_published'] is False
    assert TOKEN not in str(caught.value)
    assert not list((tmp_path/'native').glob('*.request.spent.json'))


@pytest.mark.parametrize('first,last,expected', [
    (SystemExit, KeyboardInterrupt, m.StatusCancelled),
    (OSError, SystemExit, m.StatusFatal),
])
def test_receipt_failure_retains_cancellation_or_fatal_priority(tmp_path, monkeypatch, first, last, expected):
    original = m.api._publish
    def publish(root, name, raw):
        if name.endswith('.result.json'):
            raise last(TOKEN)
        return original(root, name, raw)
    def transport(*_):
        raise first(TOKEN)
    monkeypatch.setattr(m.api, '_publish', publish)
    with pytest.raises(expected) as caught:
        run(tmp_path, transport=transport)
    assert caught.value.report['receipt_published'] is False
    assert TOKEN not in str(caught.value)
    assert TOKEN.encode() not in m.api._canonical(caught.value.report)


def test_actual_source_guard_refuses_uncommitted_successor(monkeypatch):
    from types import SimpleNamespace
    import subprocess
    old = plan()['api_plan']
    commands = []
    def git(command, **_):
        commands.append(command)
        args = command[1:]
        if args == ['rev-parse', '--show-toplevel']:
            output = str(m.api.LANE).encode()
        elif args == ['branch', '--show-current']:
            output = m.api.BRANCH.encode()
        elif args == ['rev-parse', 'HEAD']:
            output = old['git_head'].encode()
        elif args[0] == 'show':
            name = args[1].split(':', 1)[1]
            if name == m.MODULE:
                raise subprocess.CalledProcessError(128, ['git', 'show'])
            output = (ROOT/name).read_bytes()
        else:
            output = b''
        return SimpleNamespace(stdout=output, returncode=0)
    monkeypatch.setattr(m.api.subprocess, 'run', git)
    with pytest.raises(subprocess.CalledProcessError):
        m._guard(old)
    assert ['git', 'show', old['git_head']+':'+m.MODULE] in commands


def test_late_invalid_discarded_data_and_escaped_echo_are_not_filtered(tmp_path):
    raw = response(charts=['x']*140000, tail='harmless')
    bad = raw.replace(b'"harmless"', b'{"x":0,"x":1}')
    result, calls = run(tmp_path, raw=bad)
    assert len(calls) == 1 and result['raw_response'] is None
    assert result['status'] == 'failed_or_uncertain'
    echo = raw.replace(b'"harmless"', b'"\\u0053YNTHETIC-STATUS-TOKEN"')
    with pytest.raises(m.StatusRefusal):
        project(echo)
