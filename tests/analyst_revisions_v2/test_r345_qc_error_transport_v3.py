"""Synthetic fixed-host exchange seams and pure redaction; no remote contact."""
import base64
from contextlib import nullcontext
import hashlib
import time
from types import SimpleNamespace as NS

import pytest

from scripts import arv2_r345_qc_error_transport_v3 as m


def refused(code, operation):
    with pytest.raises(m.Refused) as caught:
        operation()
    assert caught.value.args == (code,)


def transport(monkeypatch, *, status=200, raw=b'{"success":true}', headers=None, journal_failure=False):
    events, retained = [], []
    class Response:
        def __init__(self): self.status = status
        def getheader(self, key, default=None): return (headers or {}).get(key, default)
        def read(self, maximum): events.append(('read', maximum)); return raw
    class Stream:
        def settimeout(self, value): events.append(('timeout', value))
        def connect(self, address): events.append(('connect', address))
        def version(self): return 'TLSv1.3'
        def close(self): events.append(('stream-close',))
    class Context:
        def wrap_socket(self, stream, server_hostname):
            events.append(('TLS-hostname', server_hostname)); return stream
    class Connection:
        debuglevel = 0
        def __init__(self, host, port, timeout): events.append(('connection', host, port))
        def request(self, method, path, body, headers): events.append(('request', method, path, body, headers))
        def getresponse(self): return Response()
        def close(self): events.append(('connection-close',))
    def journal(marker, value):
        retained.append((marker, value))
        if journal_failure: raise RuntimeError('SENSITIVE-SINK-ERROR')
    monkeypatch.setattr(m.base.socket, 'socket', lambda *args: Stream())
    monkeypatch.setattr(m.base.http.client, 'HTTPConnection', Connection)
    monkeypatch.setattr(m.base, 'alarm', lambda *args: nullcontext())
    api = m.API.__new__(m.API)
    api.secret = {'QC_USER_ID': '12345678', 'QC_API_TOKEN': 'SYNTHETIC-SECRET-TOKEN'}
    api.store = NS(intent=lambda *args: events.append(('intent', *args)),
        attempt=lambda *args: events.append(('dispatch', *args)), journal=journal)
    api.context, api.family, api.address = Context(), 2, ('8.8.8.8', 443)
    api.deadline = time.monotonic() + 89
    api._ca_verify = lambda: events.append(('CA-verified',))
    api.last_http_status = api.last_diagnostic = None
    api.statuses, api.responses = [], []
    return api, events, retained


def test_success_preserves_base_contract_fixed_TLS_host_and_no_error_capture(monkeypatch):
    api, events, retained = transport(monkeypatch)
    assert api._exchange('authenticate', {}) == {'success': True}
    request = next(item for item in events if item[0] == 'request')
    assert request[1:3] == ('POST', '/api/v2/authenticate')
    assert ('TLS-hostname', 'www.quantconnect.com') in events
    assert ('connection', 'www.quantconnect.com', 443) in events
    assert api.last_http_status == 200 and len(api.responses) == 1
    assert api.last_diagnostic is None and retained == []
    assert events[-1] == ('connection-close',)


def test_false_success_error_is_retained_before_discard_with_actual_secret_source_context(monkeypatch):
    secret, source, name = 'SYNTHETIC-SECRET-TOKEN', 'PRIVATE_SOURCE_FRAGMENT_ABC', 'PRIVATE_MODULE_NAME'
    raw = m.base.canonical({'success': False, 'errors': [f'File upload rejected: {secret} {source} {name} suspicious code.']})
    api, events, retained = transport(monkeypatch, raw=raw)
    refused('response', lambda: api._exchange('files/create', {'projectId': 39054561,
        'name': name, 'content': source, 'codeSourceId': 'Codex R345 R343-AR100 A2'}))
    value = api.last_diagnostic
    assert m.validate_diagnostic(value) == value and retained[0][1] == value
    rendered = m.base.canonical(value).decode()
    assert all(private not in rendered for private in (secret, source, name))
    assert value['response']['fields']['success']['boolean_value'] is False
    assert value['error_text']['diagnostic_terms']
    assert value['error_text']['cause_authenticated'] is False
    request = next(item for item in events if item[0] == 'request')
    assert request[4]['Authorization'] not in rendered


@pytest.mark.parametrize('status', [400, 401, 403, 429, 500])
def test_only_bounded_JSON_failure_body_is_read_then_projected(status, monkeypatch):
    raw = b'{"success":false,"errors":["File upload rejected by source policy."]}'
    api, events, retained = transport(monkeypatch, status=status, raw=raw,
        headers={'Content-Type': 'application/json; charset=utf-8', 'Content-Length': str(len(raw))})
    refused('http_status', lambda: api._exchange('files/create', {'projectId': 39054561, 'content': 'pass'}))
    assert api.last_http_status == status
    assert api.last_diagnostic['response']['http_status'] == status
    assert ('read', m.MAX_FAILURE_BODY + 1) in events
    assert len(retained) == 1


@pytest.mark.parametrize('headers,code', [({'Content-Type': 'text/html'}, 'http_status'),
    ({}, 'http_status'), ({'Content-Type': 'application/json', 'Content-Encoding': 'gzip'}, 'response'),
    ({'Content-Type': 'application/json', 'Content-Length': str(m.MAX_FAILURE_BODY + 1)}, 'bound')])
def test_nonJSON_encoded_or_declared_oversized_failed_body_is_not_read(monkeypatch, headers, code):
    api, events, retained = transport(monkeypatch, status=403, raw=b'PRIVATE-UNREAD-BODY', headers=headers)
    refused(code, lambda: api._exchange('files/create', {}))
    assert api.last_http_status == 403 and api.last_diagnostic is None
    assert not any(item[0] == 'read' for item in events) and retained == []


def test_malformed_success_body_keeps_finite_parser_projection(monkeypatch):
    api, _, retained = transport(monkeypatch, raw=b'{invalid JSON PRIVATE}')
    refused('response', lambda: api._exchange('files/create', {}))
    assert api.last_diagnostic['response']['outcome'] == 'invalid_json'
    assert 'PRIVATE' not in m.base.canonical(retained).decode()


def test_journal_failure_does_not_erase_already_projected_diagnostic(monkeypatch):
    api, _, _ = transport(monkeypatch, raw=b'{"success":false,"errors":["File rejected."]}', journal_failure=True)
    refused('transport', lambda: api._exchange('files/create', {}))
    assert m.validate_diagnostic(api.last_diagnostic)['response']['fields']['success']['boolean_value'] is False


@pytest.mark.parametrize('fault', ['extra', 'endpoint', 'status', 'body_pin', 'raw_error_text'])
def test_diagnostic_validator_rejects_unchecked_values(fault):
    raw = b'{"success":false,"errors":["Upload rejected."]}'
    value = m.project_diagnostic(200, raw, 'files/create', sensitive_values=('SYNTHETIC-SECRET',), source_text=None)
    if fault == 'extra': value['raw'] = 'SENSITIVE'
    elif fault == 'endpoint': value['endpoint'] = 'https://SENSITIVE'
    elif fault == 'status': value['response']['http_status'] = True
    elif fault == 'body_pin': value['error_text']['body_sha256'] = '0' * 64
    else: value['error_text']['redacted_text'] = 'SENSITIVE-UNKNOWN-TEXT'
    refused('response', lambda: m.validate_diagnostic(value))


def test_profiles_keep_false_cause_and_secret_detection_flags_and_frozen_base_bytes():
    record = m.profile_record()
    assert record['cause_authenticated'] is record['universal_secret_detection'] is record['retry_authority'] is False
    assert record['max_non200_JSON_body'] == 65536
    assert m.API.__mro__[1] is m.base.API
