"""Offline shared-parser integration: no QC/credentials/environment access.

Run under native remote-network, production-artifact and Keychain denial;
all fixtures/support paths must be rooted in the designated lane.
"""
import ast
import hashlib
import json
from pathlib import Path

import pytest

from scripts import arv2_r298_qc_diagnostic_boundary as module

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')


@pytest.fixture(autouse=True)
def forbid_environment_credentials(monkeypatch, tmp_path):
    assert tmp_path.is_relative_to(ROOT / '.pytest_cache')
    def forbidden(*_, **__): pytest.fail('environment credentials must not be read')
    monkeypatch.setattr(module.shared.QuantConnectCredentials, 'from_env', forbidden)


@pytest.fixture(scope='module')
def content():
    from research.analyst_revisions_v2_qc.newrule_comparison_projection import normalize
    path = ROOT / 'research/analyst_revisions_v2_qc' / module.TARGET_NAME
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == 'a08098648d98a95736471113d48a3e1183f04969d2c2561b1a4f5d6bfc80d7ee'
    normalized = normalize(raw, module.TARGET_NAME)
    assert len(normalized) == module.SOURCE_BYTES == 23055
    assert hashlib.sha256(normalized).hexdigest() == module.SOURCE_SHA256
    return normalized.decode('ascii')


@pytest.fixture
def payload(content):
    return {'projectId': module.PROJECT_ID, 'name': module.TARGET_NAME,
        'content': content, 'codeSourceId': module.CODE_SOURCE_ID}


def setup_boundary(raw=b'{"success":true}', status=200, sink=None, transport=None):
    calls, observations = [], []
    reply = (status, raw)
    def delegate(url, body, headers, timeout):
        calls.append((url, body, timeout))
        assert set(headers) == {'Authorization', 'Timestamp', 'Content-Type'}
        return reply
    def save(value):
        assert type(value) is bytes
        observations.append(value)
    boundary = module.OneResponseBoundary(transport or delegate, sink or save)
    credentials = module.shared.QuantConnectCredentials(user_id='offline-test-user',
        api_token='offline-test-token-not-a-secret')
    client = module.shared.QuantConnectClient(credentials, transport=boundary,
        clock=lambda: 1234567890, timeout=30)
    return boundary, client, calls, observations, reply


def clean_error(error, code):
    assert type(error) is module.BoundaryError
    assert error.args == (code,)
    assert error.__cause__ is None and error.__context__ is None
    assert module.finite_error(error) == {'code': code}


def test_exact_real_shared_parser_success_tuple_identity_and_no_payload_mutation(payload, monkeypatch):
    boundary, client, calls, observations, reply = setup_boundary()
    original = dict(payload)
    original_call = module.OneResponseBoundary.__call__
    seen = []
    def traced(self, *args):
        result = original_call(self, *args)
        seen.append(result)
        return result
    monkeypatch.setattr(module.OneResponseBoundary, '__call__', traced)
    assert boundary.observed_request(client, payload) == {'success': True}
    assert seen == [reply] and seen[0] is reply
    assert payload == original
    assert len(calls) == len(observations) == boundary.application_dispatch_count == 1
    assert calls[0] == (module.shared.API_BASE + '/files/update', json.dumps(payload).encode('utf-8'), 30)
    assert boundary.entry_consumed is True and boundary.snapshot is observations[0]
    evidence = json.loads(observations[0])['evidence']
    module.evidence.validate_evidence(evidence)
    assert evidence['outcome'] == 'object' and evidence['fields']['success']['boolean_value'] is True
    assert all(evidence[key] is False for key in module.evidence.FALSE_FLAGS)
    assert evidence['provider_request_count'] is None
    assert repr(boundary) == '<R298QcDiagnosticBoundary>'


@pytest.mark.parametrize('raw,expected', [
    (b'{"success":false,"errors":["PRIVATE_VENDOR_REASON"]}', False),
    (b'{"errors":["PRIVATE_VENDOR_REASON"]}', None),
    (b'{"success":1,"messages":["PRIVATE_VENDOR_REASON"]}', None),
    (b'{"success":"true","Message":"PRIVATE_VENDOR_REASON"}', None),
    (b'{"success":null,"errors":["PRIVATE_VENDOR_REASON"]}', None),
])
def test_http200_inband_failure_journaled_before_shared_refusal_without_raw_error(payload, raw, expected):
    boundary, client, calls, observations, _ = setup_boundary(raw)
    with pytest.raises(module.BoundaryError) as caught: boundary.observed_request(client, payload)
    clean_error(caught.value, 'shared_request_refused')
    assert len(calls) == len(observations) == 1
    recorded = json.loads(observations[0])['evidence']
    assert recorded['http_status'] == 200
    assert recorded['fields']['success']['boolean_value'] is expected
    assert b'PRIVATE_VENDOR_REASON' not in observations[0]
    assert b'offline-test-token' not in observations[0] and b'Authorization' not in observations[0]
    assert recorded['body_sha256'] == hashlib.sha256(raw).hexdigest()


def test_known_literal_only_classifies_observed_text_not_root_cause(payload):
    raw = b'{"success":false,"errors":["Hash doesn\'t match."]}'
    boundary, client, _, observations, _ = setup_boundary(raw)
    with pytest.raises(module.BoundaryError): boundary.observed_request(client, payload)
    record = json.loads(observations[0])['evidence']
    assert record['fields']['errors']['items'][0]['observed_text_pattern'] == 'hash_does_not_match_exact_literal'
    assert record['provider_reason_is_root_cause'] is False
    assert b"Hash doesn't match." not in observations[0]


@pytest.mark.parametrize('raw,outcome', [
    (b'', 'empty_body'), (b'bad', 'invalid_json'), (b'\xff', 'invalid_utf8'),
    (b'{"success":false,"success":true}', 'duplicate_keys'),
    (b'{"success":true,"x":NaN}', 'nonfinite_number'),
    (b'{"success":true,"x":Infinity}', 'nonfinite_number'),
    (b'{"success":true,"x":"\\ud800"}', 'invalid_unicode'),
    (b'{"success":true,"x":' + b'[' * 40 + b'0' + b']' * 40 + b'}', 'depth_bound'),
    (b'{"success":true,"x":[' + b'0,' * 4100 + b'0]}', 'node_bound'),
    (b'{"success":true,"x":"' + b'a' * 65536 + b'"}', 'parse_bound'),
    (b'[]', 'non_object'), (b'true', 'non_object'),
])
def test_invalid_or_ambiguous_json_journaled_then_blocked_before_shared_parse(payload, raw, outcome):
    boundary, client, calls, observations, _ = setup_boundary(raw)
    with pytest.raises(module.BoundaryError) as caught: boundary.observed_request(client, payload)
    clean_error(caught.value, 'response_not_object')
    assert len(calls) == len(observations) == 1
    assert json.loads(observations[0])['evidence']['outcome'] == outcome


def test_success_true_nonempty_errors_preserves_parser_not_effect_acceptance(payload):
    raw = b'{"success":true,"errors":["PRIVATE_CONTRADICTORY_MESSAGE"]}'
    boundary, client, _, observations, _ = setup_boundary(raw)
    result = boundary.observed_request(client, payload)
    assert result == json.loads(raw)
    record = json.loads(observations[0])['evidence']
    assert record['fields']['errors']['count'] == 1 and record['remote_effect_known'] is False
    assert b'PRIVATE_CONTRADICTORY_MESSAGE' not in observations[0]


@pytest.mark.parametrize('kind', ['raises', 'returns'])
def test_sink_failure_stops_before_success_and_retains_snapshot(payload, kind):
    def sink(_):
        if kind == 'raises': raise ValueError('PRIVATE_SINK_REASON')
        return True
    boundary, client, calls, _, _ = setup_boundary(sink=sink)
    with pytest.raises(module.BoundaryError) as caught: boundary.observed_request(client, payload)
    clean_error(caught.value, 'sink_refused' if kind == 'raises' else 'sink_result')
    assert len(calls) == 1 and type(boundary.snapshot) is bytes
    assert b'PRIVATE_SINK_REASON' not in boundary.snapshot


def test_snapshot_immutable_and_sink_cannot_change_retained_evidence(payload):
    snapshots = []
    def sink(raw):
        snapshots.append(raw)
        mutated = json.loads(raw)['evidence']
        mutated['retry_authority'] = True
    boundary, client, _, _, _ = setup_boundary(sink=sink)
    assert boundary.observed_request(client, payload)['success'] is True
    assert boundary.snapshot is snapshots[0]
    assert json.loads(boundary.snapshot)['evidence']['retry_authority'] is False
    with pytest.raises(AttributeError): boundary.snapshot = b'bad'


@pytest.mark.parametrize('kind', ['transport', 'shared'])
def test_failure_no_retry_and_no_raw_exception_chain(payload, kind):
    count = []
    def transport(*_):
        count.append(1)
        raise module.shared.QuantConnectError('PRIVATE_RESPONSE_TOKEN')
    boundary, client, calls, _, _ = setup_boundary(
        b'{"success":false,"errors":["PRIVATE_RESPONSE_TOKEN"]}',
        transport=transport if kind == 'transport' else None)
    with pytest.raises(module.BoundaryError) as caught: boundary.observed_request(client, payload)
    clean_error(caught.value, 'transport_refused' if kind == 'transport' else 'shared_request_refused')
    with pytest.raises(module.BoundaryError) as second: boundary.observed_request(client, payload)
    clean_error(second.value, 'entry_used')
    assert boundary.application_dispatch_count == 1
    assert len(count if kind == 'transport' else calls) == 1


@pytest.mark.parametrize('reply', [
    (403, b'{"success":false}'), (302, b'{}'), (True, b'{}'),
    (200, bytearray(b'{}')), [200, b'{}'], (200,), (200, b'x' * (16 * 1024 * 1024 + 1)),
])
def test_delegate_contract_breach_has_no_response_evidence_or_acceptance(payload, reply):
    calls = []
    def transport(*_):
        calls.append(1)
        return reply
    boundary, client, _, observations, _ = setup_boundary(transport=transport)
    with pytest.raises(module.BoundaryError) as caught: boundary.observed_request(client, payload)
    clean_error(caught.value, 'transport_contract')
    assert len(calls) == 1 and observations == [] and boundary.snapshot is None


def test_direct_shared_client_request_cannot_dispatch(payload):
    boundary, client, calls, observations, _ = setup_boundary()
    with pytest.raises(module.BoundaryError) as caught: client.request(module.ENDPOINT, payload)
    clean_error(caught.value, 'safe_entry_required')
    assert calls == observations == [] and boundary.application_dispatch_count == 0


def test_direct_wrapper_cannot_dispatch(payload):
    boundary, _, calls, _, _ = setup_boundary()
    with pytest.raises(module.BoundaryError) as caught:
        boundary(module.shared.API_BASE + '/files/update', b'{}', {}, 30)
    clean_error(caught.value, 'safe_entry_required')
    assert calls == []


def test_synchronous_reentry_cannot_dispatch_twice(payload):
    calls = []
    boundary = client = None
    def delegate(*_):
        calls.append(1)
        with pytest.raises(module.BoundaryError) as caught:
            boundary.observed_request(client, payload)
        clean_error(caught.value, 'entry_used')
        return (200, b'{"success":true}')
    boundary, client, _, _, _ = setup_boundary(transport=delegate)
    assert boundary.observed_request(client, payload) == {'success': True}
    assert calls == [1] and boundary.application_dispatch_count == 1


@pytest.mark.parametrize('change', ['project_bool', 'project', 'name', 'content', 'source_id', 'extra', 'missing'])
def test_fixed_payload_before_dispatch_and_failed_entry_consumed(payload, change):
    boundary, client, calls, _, _ = setup_boundary()
    if change == 'project_bool': payload['projectId'] = True
    elif change == 'project': payload['projectId'] += 1
    elif change == 'name': payload['name'] = 'main.py'
    elif change == 'content': payload['content'] = '#'
    elif change == 'source_id': payload['codeSourceId'] = 'unreviewed replacement'
    elif change == 'extra': payload['extra'] = 1
    else: del payload['codeSourceId']
    with pytest.raises(module.BoundaryError) as caught: boundary.observed_request(client, payload)
    clean_error(caught.value, 'payload')
    assert calls == [] and boundary.entry_consumed is True and boundary.application_dispatch_count == 0


@pytest.mark.parametrize('field,value', [('_base_url', 'https://example.invalid'),
    ('_timeout', True), ('_timeout', 31), ('_transport', lambda *_: None), ('request', lambda *_: {})])
def test_supplied_client_binding(payload, field, value):
    boundary, client, calls, _, _ = setup_boundary()
    setattr(client, field, value)
    with pytest.raises(module.BoundaryError) as caught: boundary.observed_request(client, payload)
    clean_error(caught.value, 'client')
    assert calls == []


def test_exact_client_subclass_refused(payload):
    boundary, client, calls, _, _ = setup_boundary()
    class Subclass(module.shared.QuantConnectClient): pass
    client.__class__ = Subclass
    with pytest.raises(module.BoundaryError) as caught: boundary.observed_request(client, payload)
    clean_error(caught.value, 'client')
    assert calls == []


def test_hostile_string_key_and_url_never_invoke_equality(payload):
    events = []
    class Evil(str):
        def __eq__(self, other):
            events.append('equality')
            raise RuntimeError('PRIVATE_EQUALITY_REASON')
        __hash__ = str.__hash__
    boundary, client, calls, _, _ = setup_boundary()
    client._base_url = Evil(module.shared.API_BASE)
    with pytest.raises(module.BoundaryError): boundary.observed_request(client, payload)
    assert events == calls == []
    boundary, client, calls, _, _ = setup_boundary()
    changed = {Evil('projectId'): module.PROJECT_ID,
        'name': module.TARGET_NAME, 'content': payload['content'], 'codeSourceId': module.CODE_SOURCE_ID}
    with pytest.raises(module.BoundaryError): boundary.observed_request(client, changed)
    assert events == calls == []


def test_projection_failure_is_finite_and_blocks_sharedparser(payload, monkeypatch):
    def fail(*_): raise ValueError('PRIVATE_PROJECTOR_ERROR')
    monkeypatch.setattr(module.evidence, 'project_response', fail)
    boundary, client, calls, observations, _ = setup_boundary()
    with pytest.raises(module.BoundaryError) as caught: boundary.observed_request(client, payload)
    clean_error(caught.value, 'projection_refused')
    assert len(calls) == 1 and observations == []


def test_profile_no_operational_authority_and_selected_sources_unchanged():
    profile = module.profile_record()
    assert profile['endpoint'] == 'files/update'
    assert profile['max_entry_calls'] == profile['max_delegate_dispatches'] == 1
    assert profile['request_timeout_seconds'] == 30
    assert all(profile[key] is False for key in ('source_authentication_implemented',
        'durable_claim_implemented', 'credentials_reader_implemented', 'operational_caller_implemented',
        'deadline_implemented', 'current_access_accepted', 'a8_authorized', 'retry_authority', 'remote_effect_known'))
    for name, expected in module.SOURCE_PINS.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    tree = ast.parse((ROOT / 'scripts/arv2_r298_qc_diagnostic_boundary.py').read_bytes())
    assert not any(isinstance(node, ast.Attribute) and node.attr in (
        'from_env', 'getenv', 'environ', 'urlopen') for node in ast.walk(tree))


def test_module_body_reexecution_has_no_io_or_credential_construction(monkeypatch):
    # Dependencies are already imported. This proves the new module body is
    # inert, not that Python's source-loading/import machinery does no I/O.
    import builtins
    import os
    import socket
    import subprocess
    raw = (ROOT / 'scripts/arv2_r298_qc_diagnostic_boundary.py').read_bytes()
    code = compile(raw, '<offline-import-body>', 'exec')
    def forbidden(*_, **__): pytest.fail('new module body attempted I/O or credential construction')
    monkeypatch.setattr(builtins, 'open', forbidden)
    monkeypatch.setattr(os, 'open', forbidden)
    monkeypatch.setattr(Path, 'open', forbidden)
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(module.shared.QuantConnectClient, '__init__', forbidden)
    namespace = {'__name__': '_offline_r298_boundary_import'}
    exec(code, namespace)
    assert namespace['SCHEMA'] == module.SCHEMA
    assert namespace['OneResponseBoundary'].__name__ == 'OneResponseBoundary'


@pytest.mark.parametrize('error', [ValueError('PRIVATE'), RuntimeError('PRIVATE'), KeyboardInterrupt('PRIVATE'),
    module.BoundaryError('PRIVATE')])
def test_finite_error_never_returns_unknown_text(error):
    assert module.finite_error(error) == {'code': 'shared_request_refused'}


def test_diagnostic_context_includes_exact_credentials_header_and_source(payload, monkeypatch):
    seen = []
    real = module.error_text.project_error_text
    credentials = module.shared.QuantConnectCredentials('offline-test-user',
        'offline-test-token-not-a-secret')
    headers = module.shared.build_auth_headers(credentials, 1234567890)
    stamped = credentials.api_token + ':1234567890'
    digest = hashlib.sha256(stamped.encode()).hexdigest()
    expected = {credentials.user_id, credentials.api_token, '1234567890', stamped,
        digest, credentials.user_id + ':' + digest, headers['Authorization'],
        headers['Authorization'].removeprefix('Basic ')}
    def inspect(status, raw, *, sensitive_values=(), source_text=None):
        assert expected <= set(sensitive_values)
        assert source_text == payload['content']
        seen.append(True)
        return real(status, raw, sensitive_values=sensitive_values, source_text=source_text)
    monkeypatch.setattr(module.error_text, 'project_error_text', inspect)
    raw = json.dumps({'success': False, 'errors': ['Cannot update the file: ' +
        credentials.api_token + ' ' + headers['Authorization']]}).encode()
    boundary, client, calls, observations, _ = setup_boundary(raw)
    with pytest.raises(module.BoundaryError):
        boundary.observed_request(client, payload)
    assert seen == [True] and len(calls) == len(observations) == 1
    pair = json.loads(observations[0])
    assert set(pair) == {'evidence', 'error_text'}
    module.error_text.validate_error_text(pair['error_text'])
    assert pair['evidence']['body_sha256'] == pair['error_text']['body_sha256']
    assert pair['error_text']['cause_authenticated'] is False
    for value in expected:
        assert value.encode() not in observations[0]
    assert boundary._OneResponseBoundary__credential_values is None
    assert boundary._OneResponseBoundary__source_text is None


@pytest.mark.parametrize('credentials', [None, object(), {'user_id': 'x', 'api_token': 'y'}])
def test_diagnostic_refuses_missing_or_nonexact_credentials_before_dispatch(payload, credentials):
    boundary, client, calls, observations, _ = setup_boundary()
    client._credentials = credentials
    with pytest.raises(module.BoundaryError) as caught:
        boundary.observed_request(client, payload)
    clean_error(caught.value, 'client')
    assert calls == observations == [] and boundary.entry_consumed


def test_error_text_projector_failure_is_finite_no_unredacted_sink(payload, monkeypatch):
    def fail(*_, **__):
        raise RuntimeError('SYNTHETIC_SECRET_PROJECTOR_FAILURE')
    monkeypatch.setattr(module.error_text, 'project_error_text', fail)
    boundary, client, calls, observations, _ = setup_boundary(b'{"success":false,"errors":["Cannot update file"]}')
    with pytest.raises(module.BoundaryError) as caught:
        boundary.observed_request(client, payload)
    clean_error(caught.value, 'projection_refused')
    assert len(calls) == 1 and observations == []


@pytest.mark.parametrize('raw', [b'{"success":true}', b'{"success":false,"errors":["Cannot update file"]}'])
def test_sensitive_context_cleared_after_success_and_refusal(payload, raw):
    boundary, client, _, _, _ = setup_boundary(raw)
    try:
        boundary.observed_request(client, payload)
    except module.BoundaryError:
        assert b'false' in raw
    assert boundary._OneResponseBoundary__credential_values is None
    assert boundary._OneResponseBoundary__source_text is None
    assert boundary._OneResponseBoundary__request_body is None


def test_diagnostic_body_binding_refuses_mismatched_projector_before_sink(payload, monkeypatch):
    real = module.error_text.project_error_text
    def wrong(status, raw, **context):
        value = real(status, raw, **context)
        value['body_sha256'] = 'f' * 64
        return value
    monkeypatch.setattr(module.error_text, 'project_error_text', wrong)
    boundary, client, calls, observations, _ = setup_boundary()
    with pytest.raises(module.BoundaryError) as caught:
        boundary.observed_request(client, payload)
    clean_error(caught.value, 'projection_refused')
    assert len(calls) == 1 and observations == []
