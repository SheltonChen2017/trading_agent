"""Synthetic AN phases and public-control protocol under native ALL-network denial."""
import copy
import errno
import os
from pathlib import Path
import socket
import ssl
import subprocess
import time
from types import SimpleNamespace as NS

import pytest

from scripts import diagnose_arv2_r298_public_transport as m

ARGS = NS(expected_head='a' * 40, caller_sha256='b' * 64)


def refused(code, function):
    with pytest.raises(m.Refused) as caught: function()
    assert m.finite(caught.value) == code


@pytest.fixture(autouse=True)
def no_old_operations(monkeypatch):
    def deny(*args, **kwargs): raise AssertionError('spent/provider/credential operation forbidden')
    for module, name in ((m.frozen, 'run'), (m.frozen.previous, 'run'),
            (m.frozen.keychain, 'load_key'), (m.frozen.worker, '_load_plain')):
        monkeypatch.setattr(module, name, deny)


@pytest.fixture
def transport(monkeypatch):
    state = NS(events=[], dns_calls=0, socket_calls=0, connections=[], sends=[], reads=[], closes=0,
        phase_error=None, line=b'HTTP/1.1 200 OK\r\n', tail=b'PRIVATE-HEADER: VALUE\r\n\r\nPRIVATE-BODY',
        tls_version='TLSv1.3', alpn='http/1.1', peer=b'SYNTHETIC-PUBLIC-DER')
    state.rows = [(socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('2001:db8::1', 443, 0, 0)),
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('192.0.2.1', 443))]
    def stage(args, observed, name):
        assert name == m.STAGES[len(observed['stage_intents'])]
        state.events.append('intent:' + name); observed['stage_intents'].append(name)
    monkeypatch.setattr(m, '_stage', stage)
    monkeypatch.setattr(m, '_ca_bytes', lambda: b'synthetic-public-CA')
    def dns(*args):
        assert args == (m.HOST, m.PORT, socket.AF_UNSPEC, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        assert state.events[-1] == 'intent:dns'
        state.dns_calls += 1
        if state.phase_error == 'dns': raise socket.gaierror(socket.EAI_NONAME, 'PRIVATE DNS MESSAGE')
        return state.rows
    monkeypatch.setattr(m.socket, 'getaddrinfo', dns)
    class TCP:
        def __init__(self, family, kind, protocol):
            assert state.events[-1] == 'intent:tcp'
            assert (family, kind, protocol) == (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP)
            state.socket_calls += 1
        def settimeout(self, seconds): assert 0 < seconds <= 5
        def connect(self, address):
            assert state.events[-1] == 'intent:tcp'; state.connections.append(address)
            if state.phase_error == 'tcp': raise PermissionError(errno.EPERM, 'PRIVATE TCP MESSAGE')
        def close(self): state.closes += 1
    monkeypatch.setattr(m.socket, 'socket', TCP)
    class Stream:
        def __init__(self): self.offset = 0
        def version(self): return state.tls_version
        def selected_alpn_protocol(self): return state.alpn
        def getpeercert(self, binary_form):
            assert binary_form is True
            return state.peer
        def settimeout(self, seconds): assert 0 < seconds <= 5
        def sendall(self, raw):
            assert state.events[-1] == 'intent:http' and raw == m.REQUEST
            state.sends.append(raw)
            if state.phase_error == 'http': raise ConnectionResetError(errno.ECONNRESET, 'PRIVATE SEND MESSAGE')
        def recv(self, count):
            assert count == 1
            state.reads.append(count)
            raw = state.line + state.tail
            value = raw[self.offset:self.offset + count]; self.offset += len(value)
            return value
        def close(self):
            state.closes += 1
            if state.phase_error == 'close': raise OSError(errno.EIO, 'PRIVATE CLOSE MESSAGE')
    class Context:
        def wrap_socket(self, tcp, *, server_hostname):
            assert server_hostname == m.HOST and state.events[-1] == 'intent:tls'
            if state.phase_error == 'tls': raise ssl.SSLCertVerificationError(1, 'PRIVATE TLS MESSAGE')
            state.stream = Stream(); return state.stream
    monkeypatch.setattr(m, '_context', lambda raw: Context())
    return state


def run_protocol(): return m.protocol(ARGS, time.monotonic() + m.SECONDS)


def actual(raw=b'', exit=0, bound=None):
    return {'actual_exit': exit, 'bound': bound, 'spawn_observed': True,
        'dispatched_at': '2026-10-27T12:00:00.000001Z', 'completion_observed_at': '2026-10-27T12:00:01.000001Z',
        'stdout_bytes': len(raw), 'stdout_sha256': m.sha(raw), 'stderr_bytes': 0, 'stderr_sha256': m.sha(b'')}


def envelope(state, *, parent_failure=None, no_child=False):
    child = None if no_child else {'binding': m.binding(ARGS), 'state': state}
    raw = b'' if child is None else m.canonical(child)
    child_actual = actual(raw, exit=None if no_child else 0 if state['diagnostic_complete'] else 2,
        bound='deadline' if no_child else None)
    journal = b''.join(m.canonical({'binding': m.binding(ARGS), 'ordinal': i, 'stage': name})
        for i, name in enumerate(state['stage_intents']))
    result = {'binding': m.binding(ARGS), 'claim_consumed': True, 'child_actual': child_actual,
        'child': child, 'journal_pin': None if no_child else {'byte_count': len(journal), 'sha256': m.sha(journal)},
        'parent_failure': parent_failure, **m.FALSE_FLAGS}
    report = m.canonical(result)
    return {'binding': m.binding(ARGS), 'outcome': {'result': result,
        'report': {'byte_count': len(report), 'sha256': m.sha(report)}}}


def test_exact_single_phase_order_first_address_verified_TLS_HEAD_status_only_no_header_or_body(transport):
    state = run_protocol(); m.validate_state(state)
    assert state['diagnostic_complete'] is True and state['http_status'] == 200
    assert state['stage_intents'] == list(m.STAGES)
    assert transport.events == ['intent:' + name for name in m.STAGES]
    assert transport.dns_calls == transport.socket_calls == len(transport.connections) == len(transport.sends) == 1
    assert transport.connections == [transport.rows[0][4]]
    assert transport.stream.offset == len(transport.line) == state['status_line_byte_count']
    assert state['DNS']['count'] == 2 and state['DNS']['selected_ordinal'] == 0
    assert state['TLS'] == {'version': 'TLSv1.3', 'peer_DER_sha256': m.sha(transport.peer)}
    assert state['physical_packets'] is None and all(state[key] is False for key in m.FALSE_FLAGS)
    assert b'PRIVATE' not in m.canonical(state) and b'192.0.2' not in m.canonical(state)
    assert b'2001:db8' not in m.canonical(state)


@pytest.mark.parametrize('status', [101, 200, 301, 401, 403, 429, 500, 599])
def test_any_valid_first_numeric_status_is_observed_without_redirect_or_failed_body(transport, status):
    transport.line = ('HTTP/1.1 ' + str(status) + ' PRIVATE-REASON\r\n').encode()
    state = run_protocol()
    assert state['diagnostic_complete'] is True and state['http_status'] == status
    assert len(transport.sends) == 1 and transport.stream.offset == len(transport.line)
    assert b'PRIVATE' not in m.canonical(state)


def test_late_owned_socket_closure_failure_keeps_status_but_is_not_success(transport):
    transport.phase_error = 'close'
    state = run_protocol(); m.validate_state(state)
    assert state['http_status'] == 200 and state['diagnostic_complete'] is False
    assert state['failure_code'] == 'transport' and state['error']['nodes'][0]['errno'] == errno.EIO
    value = envelope(state)
    assert m.validate_output(m.canonical(value), 2, ARGS) == value
    refused('output', lambda: m.validate_output(m.canonical(value), 0, ARGS))


@pytest.mark.parametrize('phase,label,number', [('dns', 'dns_gaierror', socket.EAI_NONAME),
    ('tcp', 'permission', errno.EPERM), ('tls', 'ssl_certificate', 1), ('http', 'connection_reset', errno.ECONNRESET)])
def test_failed_phases_keep_finite_numeric_evidence_without_retry_or_alternate_address(transport, phase, label, number):
    transport.phase_error = phase
    state = run_protocol(); m.validate_state(state)
    assert state['diagnostic_complete'] is False and state['failure_code'] == 'transport'
    assert state['stage_intents'] == list(m.STAGES[:m.STAGES.index(phase) + 1])
    assert state['error']['nodes'][0]['label'] == label and state['error']['nodes'][0]['errno'] == number
    assert state['http_status'] is None and transport.dns_calls == 1
    assert len(transport.connections) <= 1 and len(transport.sends) <= 1
    assert b'PRIVATE' not in m.canonical(state)
    value = envelope(state)
    assert m.validate_output(m.canonical(value), 2, ARGS) == value
    refused('output', lambda: m.validate_output(m.canonical(value), 0, ARGS))


@pytest.mark.parametrize('line', [b'HTTP/2 200 OK\r\n', b'HTTP/1.1 099 NO\r\n', b'HTTP/1.1 600 NO\r\n',
    b'HTTP/1.1 20X NO\r\n', b'HTTP/1.1 200 \x00\r\n', b'x' * 513, b''])
def test_malformed_or_overlong_status_never_reads_more_than_fixed_bound_or_becomes_success(transport, line):
    transport.line, transport.tail = line, b''
    state = run_protocol(); m.validate_state(state)
    assert state['failure_code'] == 'http_status_line' and state['diagnostic_complete'] is False
    assert state['http_status'] is None and len(transport.reads) <= m.MAX_STATUS
    assert len(transport.sends) == 1


@pytest.mark.parametrize('mode', ['empty', 'unsupported', 'wrong_port', 'wrong_address', 'too_many'])
def test_DNS_inventory_is_bounded_and_never_substitutes_or_reresolves(transport, mode):
    if mode == 'empty': transport.rows = []
    elif mode == 'unsupported': transport.rows = [(socket.AF_UNIX, socket.SOCK_STREAM, 0, '', '/synthetic/address')]
    elif mode == 'wrong_port': transport.rows[0] = (*transport.rows[0][:4], ('2001:db8::1', 80, 0, 0))
    elif mode == 'wrong_address': transport.rows[0] = (*transport.rows[0][:4], ('invalid-address', 443, 0, 0))
    else: transport.rows *= 33
    state = run_protocol()
    assert state['diagnostic_complete'] is False and state['stage_intents'] == ['dns']
    assert transport.dns_calls == 1 and transport.socket_calls == 0


def test_inventory_hash_commits_order_and_all_rows_not_only_selected_address(transport):
    first, *_ = m._inventory(transport.rows)
    changed = list(transport.rows); changed[-1] = (*changed[-1][:4], ('192.0.2.2', 443))
    second, *_ = m._inventory(changed)
    reversed_inventory, *_ = m._inventory(list(reversed(transport.rows)))
    assert first['ordered_inventory_sha256'] != second['ordered_inventory_sha256']
    assert first['ordered_inventory_sha256'] != reversed_inventory['ordered_inventory_sha256']


def test_safe_exception_graph_preserves_numeric_DNS_TLS_errno_cycles_unknowns_without_getattr_or_text():
    class Unknown(RuntimeError):
        def __str__(self): raise AssertionError('raw exception string forbidden')
        def __repr__(self): raise AssertionError('raw exception repr forbidden')
        def __getattribute__(self, name):
            if name in ('args', '__cause__', '__context__', '__dict__'): raise AssertionError('dynamic field access forbidden')
            return super().__getattribute__(name)
    root = Unknown('PRIVATE-RAW-ERROR'); cause = socket.gaierror(socket.EAI_AGAIN, 'PRIVATE DNS')
    root.__cause__ = cause; cause.__context__ = root
    record = m.error_record(root)
    assert record['cycle_observed'] is True
    assert record['nodes'][0]['label'] == 'unknown' and record['nodes'][0]['errno'] is None
    assert any(row['label'] == 'dns_gaierror' and row['errno'] == socket.EAI_AGAIN for row in record['nodes'])
    assert b'PRIVATE' not in m.canonical(record)
    certificate = ssl.SSLCertVerificationError(1, 'PRIVATE TLS'); certificate.verify_code = 62
    assert m.error_record(certificate)['nodes'][0]['verify_code'] == 62
    head = RuntimeError('PRIVATE'); cursor = head
    for _ in range(12):
        following = RuntimeError('PRIVATE'); cursor.__cause__ = following; cursor = following
    bounded = m.error_record(head)
    assert len(bounded['nodes']) == 8 and bounded['truncated'] is True
    shared = OSError(errno.EACCES, 'PRIVATE'); diamond = RuntimeError('PRIVATE')
    diamond.__cause__ = shared; diamond.__context__ = shared
    assert m.error_record(diamond)['cycle_observed'] is False


def test_CA_reader_refuses_oversize_before_read_and_loads_same_pinned_bytes_without_default_CA(tmp_path, monkeypatch):
    path = tmp_path / 'public-ca.pem'; path.write_bytes(b'PUBLIC-CA')
    monkeypatch.setattr(m, 'CA_PATH', path); monkeypatch.setattr(m, 'CA_BYTES', 9)
    monkeypatch.setattr(m, 'CA_SHA256', m.sha(b'PUBLIC-CA'))
    assert m._ca_bytes() == b'PUBLIC-CA'
    path.write_bytes(b'PUBLIC-CA-LARGER')
    with monkeypatch.context() as patch:
        patch.setattr(m.os, 'read', lambda *args: (_ for _ in ()).throw(AssertionError('unbounded read')))
        refused('ca_pin', m._ca_bytes)
    captured = {}
    class Context:
        def __init__(self, protocol): self.protocol = protocol
        def set_alpn_protocols(self, value): captured['alpn'] = value
        def load_verify_locations(self, **kwargs): captured.update(kwargs)
    monkeypatch.setattr(m.ssl, 'SSLContext', Context)
    context = m._context(b'PUBLIC-CA')
    assert captured == {'alpn': ['http/1.1'], 'cadata': 'PUBLIC-CA'}
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname is True
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2


def test_disabled_verification_cannot_satisfy_TLS_context_policy(monkeypatch):
    raw = b'PUBLIC-CA'; monkeypatch.setattr(m, 'CA_BYTES', len(raw)); monkeypatch.setattr(m, 'CA_SHA256', m.sha(raw))
    class Unverified:
        check_hostname, verify_mode = False, ssl.CERT_NONE
        def __init__(self, protocol): self.protocol = protocol
        def __setattr__(self, name, value):
            if name not in ('check_hostname', 'verify_mode'): object.__setattr__(self, name, value)
        def set_alpn_protocols(self, value): pass
        def load_verify_locations(self, **kwargs): pass
    monkeypatch.setattr(m.ssl, 'SSLContext', Unverified)
    refused('tls_configuration', lambda: m._context(raw))


def test_exclusive_control_inherited_original_FDs_and_stage_fsync_prefix(tmp_path, monkeypatch):
    monkeypatch.setattr(m, 'CONTROL', tmp_path / 'public-transport' / 'AN')
    with m.Store() as directory:
        directory.write('claim.json', m.canonical({**m.binding(ARGS), 'attempt_consumed': True}))
        directory.write('intent.json', m.canonical({**m.binding(ARGS), 'one_child': True}))
        directory.write('stages.jsonl', b'')
        args = NS(**vars(ARGS), control_fd=directory.fd, claim_fd=directory.files['claim.json'][0],
            intent_fd=directory.files['intent.json'][0], journal_fd=directory.files['stages.jsonl'][0])
        m._inherited(args)
        state = m.initial_state()
        m._stage(args, state, 'dns'); directory.verify()
        refused('inherited', lambda: m._inherited(args))
        refused('journal', lambda: m._stage(args, state, 'dns'))
        for name in ('tcp', 'tls', 'http'): m._stage(args, state, name)
        refused('journal', lambda: m._stage(args, state, 'http'))
        expected = b''.join(m.canonical({'binding': m.binding(args), 'ordinal': i, 'stage': name})
            for i, name in enumerate(m.STAGES))
        assert m._read(args.journal_fd, m.MAX_JOURNAL) == expected
        directory.verify()
    refused('claim_spent', m.Store)


@pytest.mark.parametrize('mutation', ['extra', 'missing', 'count_bool', 'count_string', 'timestamp', 'zero_hash', 'bound'])
def test_actual_record_is_closed_even_for_parent_failure_with_no_child(transport, mutation):
    state = run_protocol()
    value = envelope(state, parent_failure='child_failed', no_child=True)
    observed = value['outcome']['result']['child_actual']
    if mutation == 'extra': observed['raw_error'] = 'PRIVATE-ERROR'
    elif mutation == 'missing': del observed['bound']
    elif mutation == 'count_bool': observed['stdout_bytes'] = False
    elif mutation == 'count_string': observed['stdout_bytes'] = '0'
    elif mutation == 'timestamp': observed['dispatched_at'] = '2026-99-27T12:00:00Z'
    elif mutation == 'zero_hash': observed['stdout_sha256'] = 'f' * 64
    else: observed['bound'] = 'raw unknown bound'
    result = value['outcome']['result']; value['outcome']['report'] = {'byte_count': len(m.canonical(result)), 'sha256': m.sha(m.canonical(result))}
    refused('output', lambda: m.validate_output(m.canonical(value), 2, ARGS))


def test_external_parent_actual_exit_and_child_packet_hash_are_required_even_when_report_pin_matches(transport):
    state = run_protocol(); value = envelope(state)
    assert m.validate_output(m.canonical(value), 0, ARGS) == value
    refused('output', lambda: m.validate_output(m.canonical(value), 2, ARGS))
    changed = copy.deepcopy(value)
    changed['outcome']['result']['child_actual']['stdout_sha256'] = 'f' * 64
    result = changed['outcome']['result']; changed['outcome']['report'] = {'byte_count': len(m.canonical(result)), 'sha256': m.sha(m.canonical(result))}
    refused('child_failed', lambda: m.validate_output(m.canonical(changed), 0, ARGS))


@pytest.mark.parametrize('field,value', [('stage_intents', ['dns', 'tcp']), ('HEAD_send_attempts', 0),
    ('status_line_byte_count', 0), ('physical_packets', 0), ('response_body_read', True), ('TLS', None)])
def test_closed_phase_relationships_cannot_claim_complete_from_missing_stages(transport, field, value):
    state = run_protocol(); state[field] = value
    refused('output', lambda: m.validate_state(state))


def test_exact_frozen_AM_native_egress_and_no_other_artifact_or_keychain_or_credential_bypass():
    profile = m.native_profile('child')
    assert m.EGRESS in profile and m.EGRESS in m.frozen.native_profile('provider')
    assert 'remote tcp "*:443"' in profile and 'remote udp "*:53"' in profile
    assert 'mdns' not in profile.lower() and 'unix-socket' not in profile
    assert '/Library/Keychains' in profile and '/usr/bin/security' in profile
    assert '(deny network*)' in m.native_profile('validator')
    assert 'newrule_raw_price_acquisition' not in profile
    assert m.profile_record()['CA'] == {'path': str(m.CA_PATH), 'byte_count': m.CA_BYTES, 'sha256': m.CA_SHA256}
    assert all(m.profile_record()[key] is False for key in m.FALSE_FLAGS)


def test_real_plain_child_accepts_actual_automatic_locale_with_literal_C_environment_under_inherited_native_denial(tmp_path):
    safe = {key: str(tmp_path) for key in ('TMPDIR', 'TMP', 'TEMP', 'XDG_CACHE_HOME', 'PYTHONPYCACHEPREFIX')}
    safe.update(PATH='/usr/bin:/bin:/usr/sbin:/sbin', LANG='C', PYTHONDONTWRITEBYTECODE='1')
    # This plain child inherits the test runner's native ALL-network/artifact/
    # Keychain/security denial. No second sandbox-exec policy is applied.
    code = "from scripts import diagnose_arv2_r298_public_transport as m; m.environment(); print('compatible')"
    result = subprocess.run([str(m.PYTHON), '-B', '-c', code], cwd=m.ROOT, env=safe,
        capture_output=True, timeout=15)
    assert result.returncode == 0 and result.stdout == b'compatible\n' and result.stderr == b''


@pytest.mark.parametrize('locale', ['en_US.UTF-8', 'UTF-8', 'C', 'PRIVATE-UNRECOGNIZED'])
def test_unfrozen_automatic_locale_values_are_not_accepted_as_a_blanket_waiver(tmp_path, monkeypatch, locale):
    safe = {key: str(tmp_path) for key in ('TMPDIR', 'TMP', 'TEMP', 'XDG_CACHE_HOME', 'PYTHONPYCACHEPREFIX')}
    safe.update(PATH='/usr/bin:/bin:/usr/sbin:/sbin', LANG='C', LC_CTYPE=locale)
    with monkeypatch.context() as patch:
        patch.setattr(m.os, 'environ', safe)
        refused('environment', m.environment)
