"""Q fixed metadata-only access observer; synthetic fixtures, native denial."""
import copy
import re
import sys
import time
from types import SimpleNamespace as NS

import pytest

from scripts import observe_arv2_r298_post_phase_access as m
from scripts import observe_arv2_r298_post_mia_access_a17 as old
from tests.analyst_revisions_v2 import test_post_mia_access as pure_fixtures
from tests.analyst_revisions_v2 import test_r298_post_mia_access_a17_caller as old_tests


@pytest.fixture(autouse=True)
def no_old_operation(monkeypatch):
    def deny(*args, **kwargs): raise AssertionError('private or spent operation')
    for module, names in ((old, ('main', 'run', 'observe')),
        (m.a17, ('main', 'run', 'observe', 'worker', 'run_worker')),
        (m.prior, ('main', 'run', 'observe', 'worker', 'run_worker')),
        (m.prior.admitted, ('main', '_execute', '_recover', '_worker', 'authenticate_storage')),
        (m.prior.admission, ('admit',)), (m.prior.admitted.prep, ('main', 'construct'))):
        for name in names: monkeypatch.setattr(module, name, deny)


@pytest.fixture
def args():
    return NS(expected_head='a' * 40, caller_sha256='b' * 64, actual_exit=None)


@pytest.fixture
def control(tmp_path, monkeypatch):
    parent = tmp_path / 'parent'; parent.mkdir(mode=0o700)
    value = parent / 'q'; monkeypatch.setattr(m, 'CONTROL', value)
    return value


@pytest.fixture
def supplied(monkeypatch):
    value = pure_fixtures.supplied.__wrapped__(monkeypatch)
    # Q intentionally permits only safe identifier field names. The frozen H
    # fixture's hyphenated synthetic extra key belongs to its wider old scope.
    for row in (value.extra, value.project['projects'][0]['collaborators'][1]):
        row['hidden_private_field'] = row.pop('hidden-private-field')
    monkeypatch.setattr(m.access, 'A5_ROW_SHA256', m.sha(m.access._canonical(value.extra)))
    monkeypatch.setattr(m.current_access, 'OWNER_ROW_SHA256', m.access.OWNER_ROW_SHA256)
    monkeypatch.setattr(m.current_access, 'A5_ROW_SHA256', m.access.A5_ROW_SHA256)
    value.calls = []
    class API:
        def request(self, endpoint, payload):
            value.calls.append((endpoint, payload))
            assert payload == {'projectId': 38364439} and endpoint in m.ENDPOINTS
            return copy.deepcopy(value.project if endpoint == m.ENDPOINTS[0] else value.dedicated)
    monkeypatch.setattr(m, '_client', API)
    monkeypatch.setattr(m, 'credential_shape', lambda: {})
    monkeypatch.setattr(m, 'preflight', lambda *args: None)
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: None)
    return value


def execute(args):
    outcome = m.run(args, time.monotonic() + 30)
    raw = m.canonical({'binding': m.binding(args), 'outcome': outcome})
    code = 2 if 'failure' in outcome else 0
    assert m.validate_output(raw, code, args)
    return outcome


def mia_row(supplied, monkeypatch, *, fixed=False):
    row = {'owner': False, 'uid': None, 'name': 'Mia', 'publicId': 'PRIVATE MIA ID',
        'permission': 'write', 'liveControl': True, 'email': 'PRIVATE EMAIL',
        'lastActivity': 'PRIVATE TIME'}
    if fixed:
        monkeypatch.setattr(m.current_access, 'MIA_ROW_SHA256', m.sha(m.access._canonical(row)))
        monkeypatch.setattr(m.current_access, 'MIA_PUBLIC_ID_SHA256', m.sha(m.access._canonical(row['publicId'])))
    supplied.project['projects'][0]['collaborators'].append(row)
    return row


def test_distinct_bounded_protocol_and_p_documentary_facts():
    profile = m.profile_record()
    assert m.SCHEMA == 'arv2-r298-post-phase-access-q-v1' and m.CONTROL.name == 'R323-20261025-Q'
    assert m.ENDPOINTS == ('projects/read', 'projects/collaboration/read')
    assert m.DEADLINE_SECONDS == 120 and m.MAX_OUTPUT == 128 * 1024 and m.MAX_ROW_KEYS == 32
    assert profile['p_spent'] is True and profile['p_actual_exit'] == 2
    assert profile['p_parent_stdout_bytes'] == 791 and profile['p_failure_code'] == 'access_general_row_pin'
    assert profile['p_facts_documentary_only'] is True and profile['p_source_writes'] == profile['p_jobs'] == 0
    assert profile['p_freeze_head'] == 'd2abfec65f0b45fa783fd65abf5080ba734098dd'
    assert all(profile[name] == 0 for name in ('lock_changes', 'uploads', 'capacity_calls', 'compiles', 'backtests'))
    assert profile['old_control_reads'] is profile['access_policy_changed'] is False
    assert 'assistant.dispatch_fence' not in sys.modules


def test_selected_public_pins_current_and_no_conflicting_union(monkeypatch):
    pins = m.pins()
    assert len(pins) > 115
    for name, pin in pins.items():
        assert re.fullmatch('[0-9a-f]{64}', pin) and m.sha((m.ROOT / name).read_bytes()) == pin
    assert m.NEW_PINS['scripts/observe_arv2_r298_post_mia_access_a17.py'] == '21c1f99db2b0ab3029ad3a1957eaf9cb122c76465ae22445c2ad2c6f6621580c'
    name = next(iter(m.a17.pins()))
    monkeypatch.setitem(m.NEW_PINS, name, '0' * 64)
    with pytest.raises(ValueError): m.pins()


def test_exact_two_calls_claim_precedes_client_no_private_values(control, args, supplied, monkeypatch):
    original = m._client
    def client():
        assert (control / 'claim.json').is_file()
        return original()
    monkeypatch.setattr(m, '_client', client)
    result = execute(args)['result']
    assert supplied.calls == [(endpoint, {'projectId': 38364439}) for endpoint in m.ENDPOINTS]
    assert result['legacy_access_failure_code'] is result['current_failure_code'] is None
    assert result['current_policy_check'] == 'passed' and all(result[key] is False for key in m.FALSE_FLAGS)
    assert len(list(control.iterdir())) == 6
    assert b'SYNTHETIC' not in b''.join(path.read_bytes() for path in control.iterdir())


def test_changed_third_row_retains_current_predicate_and_all_field_hashes(control, args, supplied, monkeypatch):
    row = mia_row(supplied, monkeypatch)
    result = execute(args)['result']
    assert result['legacy_access_failure_code'] == 'general_collaborators'
    assert result['current_policy_check'] == 'refused' and result['current_failure_code'] == 'general_row_pin'
    detail = result['row_details']['general'][-1]
    assert detail['row_sha256'] == m.sha(m.access._canonical(row))
    assert {field['name'] for field in detail['fields']} == set(row)
    for field in detail['fields']:
        assert field['value_sha256'] == m.sha(m.access._canonical(row[field['name']]))
    assert set(detail['known_field_sha256']) == set(m.helper().ROW_FIELDS)
    assert detail['h_known_field_matches']['email'] is None
    assert detail['matches_h_known_mia_row'] is False
    assert b'PRIVATE' not in m.canonical(result)
    assert all(result[key] is False for key in m.FALSE_FLAGS)


def test_exact_existing_current_shape_not_a_new_policy_or_authority(control, args, supplied, monkeypatch):
    mia_row(supplied, monkeypatch, fixed=True)
    result = execute(args)['result']
    assert result['legacy_access_failure_code'] == 'general_collaborators'
    assert result['current_failure_code'] is None and result['current_policy_check'] == 'passed'
    assert result['row_details']['general'][-1]['matches_h_known_mia_row'] is True
    assert all(result[key] is False for key in m.FALSE_FLAGS)


def test_forged_current_pass_with_unknown_row_is_refused(control, args, supplied, monkeypatch):
    mia_row(supplied, monkeypatch)
    result = execute(args)['result']
    result['current_failure_code'], result['current_policy_check'] = None, 'passed'
    with pytest.raises(ValueError): m.validate_result(result)


@pytest.mark.parametrize('name', ['owner', 'uid', 'name', 'publicId', 'codeSourceId', 'permission', 'liveControl', 'email'])
def test_every_known_field_value_hash_is_bound_to_inventory(control, args, supplied, name):
    result = execute(args)['result']
    row = result['row_details']['general'][0]
    row['known_field_sha256'][name] = '0' * 64
    with pytest.raises(ValueError): m.validate_result(result)


@pytest.mark.parametrize('change', ['extra', 'name', 'type', 'hash', 'duplicate', 'order', 'overbound', 'hflag', 'wholepin'])
def test_closed_inventory_and_h_comparison_tamper_refused(control, args, supplied, change):
    result = execute(args)['result']; row = result['row_details']['general'][0]
    if change == 'extra': row['raw_value'] = 'PRIVATE'
    elif change == 'name': row['fields'][0]['name'] = 'invalid-key'
    elif change == 'type': row['fields'][0]['type'] = 'unknown'
    elif change == 'hash': row['fields'][0]['value_sha256'] = '0' * 64
    elif change == 'duplicate': row['fields'].append(row['fields'][0])
    elif change == 'order': row['fields'].reverse()
    elif change == 'overbound': row['fields'] *= 33
    elif change == 'hflag': row['h_known_field_matches']['email'] = True
    else: row['matches_h_known_mia_row'] = True
    with pytest.raises(ValueError): m.validate_result(result)


@pytest.mark.parametrize('key', ['bad-key', 'email@example', 'x' * 65, '1invalid'])
def test_unsafe_field_names_refuse_without_printing_key(control, args, supplied, key):
    supplied.project['projects'][0]['collaborators'][0][key] = 'PRIVATE VALUE'
    outcome = execute(args)
    assert outcome['failure']['failure_code'] == 'row_fields'
    assert key.encode() not in m.canonical(outcome) and b'PRIVATE' not in m.canonical(outcome)


def test_more_than32_fields_refuse_no_truncation(control, args, supplied):
    supplied.project['projects'][0]['collaborators'][0].update({'extra' + str(i): None for i in range(33)})
    outcome = execute(args)
    assert outcome['failure']['failure_code'] == 'row_fields'


@pytest.mark.parametrize('code', sorted(m.current_access.FINITE_CODES))
def test_all_current_policy_categories_remain_closed_not_old_unknown(code):
    assert m.finite(m.current_access.AccessRefused(code)) == 'current_access_' + code
    assert m._finite_code('current_access_' + code)


@pytest.mark.parametrize('which', [0, 1])
def test_transport_failure_retains_intent_response_counts_without_retry(control, args, supplied, monkeypatch, which):
    class API:
        def request(self, endpoint, payload):
            supplied.calls.append(endpoint)
            if len(supplied.calls) == which + 1: raise RuntimeError('PRIVATE ERROR')
            return copy.deepcopy(supplied.project)
    monkeypatch.setattr(m, '_client', API)
    failed = execute(args)['failure']
    assert failed['state']['application_dispatch_count'] == which + 1
    assert failed['state']['response_count'] == which and failed['failure_code'] == 'unknown_exception'
    assert b'PRIVATE' not in m.canonical(failed)


@pytest.mark.parametrize('actual', [2, False, None])
def test_even_valid_observation_requires_actual_parent_zero(control, args, supplied, actual):
    outcome = execute(args)
    with pytest.raises(ValueError):
        m.validate_output(m.canonical({'binding': m.binding(args), 'outcome': outcome}), actual, args)


def test_report_publication_failure_does_not_become_success(control, args, supplied, monkeypatch):
    original = m.Store.write
    def write(self, name, value):
        if name == 'report.json': raise OSError('PRIVATE FAILURE')
        return original(self, name, value)
    monkeypatch.setattr(m.Store, 'write', write)
    failed = execute(args)['failure']
    assert failed['failure_code'] == 'os_error' and failed['state']['stage'] == 'report'


@pytest.mark.parametrize('change', ['mode', 'new', 'replacement', 'inplace'])
def test_own_store_endpoint_integrity_and_no_old_control(control, monkeypatch, change):
    monkeypatch.setattr(old_tests, 'm', m)
    old_tests.test_store_held_named_metadata_and_census(control, change)


@pytest.mark.parametrize('name', ['../bad.json', '/tmp/a.json', 'bad_name.json', 'report.txt'])
def test_store_paths_exclusive(control, monkeypatch, name):
    monkeypatch.setattr(old_tests, 'm', m)
    old_tests.test_store_no_path_escape(control, name)


def test_parent_claim_is_never_reused(control, args, supplied):
    execute(args)
    with pytest.raises(ValueError): m.run(args, time.monotonic() + 30)
    assert len(supplied.calls) == 2


def test_foreign_exception_redaction_never_stringifies():
    class Hostile(m.current_access.AccessRefused):
        def __str__(self): raise AssertionError('stringified')
    assert m.finite(Hostile('owner')) == 'unknown_exception'
    assert m.finite(m.current_access.AccessRefused('PRIVATE ERROR')) == 'current_access_unknown'
