"""Synthetic AO broker review: one child, clean environment, exact journal.

No real DNS, socket, TLS, credentials, provider, artifact or QC is used.
"""
import copy
import os
from pathlib import Path
import time
from types import SimpleNamespace as NS

import pytest

from scripts import diagnose_arv2_r298_public_transport_v2 as m


@pytest.fixture
def broker(monkeypatch, tmp_path):
    args = NS(expected_head='a' * 40, caller_sha256='b' * 64)
    monkeypatch.setattr(m, 'CONTROL', tmp_path / 'protocol' / 'AO')
    monkeypatch.setattr(m, 'binding', lambda value: {'schema': 'synthetic-AO',
        'expected_head': value.expected_head, 'caller_sha256': value.caller_sha256})
    monkeypatch.setattr(m.security, 'snapshot', lambda fd: ('synthetic-security',))
    monkeypatch.setattr(m, 'preflight', lambda *args: None)
    calls = []
    def complete_state():
        state = m.initial_state()
        state.update(DNS={'count': 1, 'families': {'AF_INET': 1, 'AF_INET6': 0, 'unsupported': 0},
            'ordered_inventory_sha256': 'c' * 64, 'selected_ordinal': 0, 'selected_family': 'AF_INET'},
            TCP_connected=True, TLS={'version': 'TLSv1.3', 'peer_DER_sha256': 'd' * 64},
            HEAD_send_attempts=1, http_status=200, status_line_byte_count=17, diagnostic_complete=True)
        return state
    def actual(raw, code=0):
        return {'actual_exit': code, 'bound': None, 'spawn_observed': True,
            'dispatched_at': '2026-10-27T12:00:00.000001Z',
            'completion_observed_at': '2026-10-27T12:00:00.000002Z',
            'stdout_bytes': len(raw), 'stdout_sha256': m.sha(raw),
            'stderr_bytes': 0, 'stderr_sha256': m.sha(b'')}
    def capture(command, safe, timeout, **kwargs):
        calls.append((command, safe, timeout, kwargs))
        assert len(calls) == 1 and command[:2] == ['/usr/bin/sandbox-exec', '-p']
        assert command[2] == m.native_profile('child')
        assert command[3:7] == [str(m.PYTHON), '-B', str(m.SOURCE), 'child']
        assert '--actual-exit' not in command and '--credential-fd' not in command
        assert kwargs['stdout_limit'] == m.MAX_OUTPUT and set(kwargs) == {'stdout_limit', 'pass_fds'}
        assert 0 < timeout <= m.OUTER_SECONDS
        expected_names = {'PATH', 'LANG', 'PYTHONDONTWRITEBYTECODE', 'TMPDIR', 'TMP', 'TEMP',
            'XDG_CACHE_HOME', 'PYTHONPYCACHEPREFIX'}
        assert set(safe) == expected_names
        assert safe['PATH'] == '/usr/bin:/bin:/usr/sbin:/sbin' and safe['LANG'] == 'C'
        assert all(Path(safe[key]).is_relative_to(m.ROOT / '.pytest_cache')
            for key in ('TMPDIR', 'TMP', 'TEMP', 'XDG_CACHE_HOME', 'PYTHONPYCACHEPREFIX'))
        assert not {'QC_USER_ID', 'QC_API_TOKEN', 'SHARADAR_API_KEY', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY'} & set(safe)
        fds = kwargs['pass_fds']; assert len(fds) == len(set(fds)) == 4
        child_args = NS(**vars(args), control_fd=fds[0], claim_fd=fds[1], intent_fd=fds[2], journal_fd=fds[3])
        assert os.fstat(child_args.journal_fd).st_size == 0
        assert os.pread(child_args.claim_fd, m.MAX_OUTPUT, 0) == m.canonical({**m.binding(args), 'attempt_consumed': True})
        assert os.pread(child_args.intent_fd, m.MAX_OUTPUT, 0) == m.canonical({**m.binding(args), 'one_child': True})
        assert (m.CONTROL / 'claim.json').exists() and (m.CONTROL / 'intent.json').exists()
        state = complete_state()
        for stage in m.STAGES: m._stage(child_args, state, stage)
        raw = m.canonical({'binding': m.binding(args), 'state': state})
        return raw, b'', actual(raw)
    monkeypatch.setattr(m, 'capture', capture)
    return NS(args=args, calls=calls, capture=capture, actual=actual, complete=complete_state,
        deadline=time.monotonic() + 40)


def external(outcome, args):
    return m.canonical({'binding': m.binding(args), 'outcome': outcome})


def test_parent_claims_before_one_native_child_and_passes_only_clean_literal_environment(broker):
    outcome, code = m.run(broker.args, broker.deadline)
    assert code == 0 and outcome['result']['parent_failure'] is None
    assert len(broker.calls) == 1 and outcome['result']['claim_consumed']
    assert outcome['result']['child']['state']['stage_intents'] == list(m.STAGES)
    assert m.validate_output(external(outcome, broker.args), code, broker.args)['outcome'] == outcome


@pytest.mark.parametrize('tamper', ('unrecorded_stage', 'extra_journal', 'wrong_child_pin', 'wrong_binding', 'stderr'))
def test_parent_never_accepts_child_journal_binding_or_channel_disagreement(broker, monkeypatch, tamper):
    original = broker.capture
    def capture(command, safe, timeout, **kwargs):
        raw, errors, actual = original(command, safe, timeout, **kwargs)
        if tamper == 'unrecorded_stage':
            parsed = m.parse(raw); parsed['state']['stage_intents'] = ['dns']
            parsed['state'].update(DNS=None, TCP_connected=False, TLS=None, HEAD_send_attempts=0,
                http_status=None, status_line_byte_count=0, diagnostic_complete=False,
                failure_code='transport', error=m.error_record(OSError(1, 'synthetic-only')))
            raw = m.canonical(parsed); actual = broker.actual(raw, 2)
        elif tamper == 'extra_journal':
            os.lseek(kwargs['pass_fds'][3], 0, os.SEEK_END)
            os.write(kwargs['pass_fds'][3], b'{}\n'); os.fsync(kwargs['pass_fds'][3])
        elif tamper == 'wrong_child_pin': actual['stdout_sha256'] = 'f' * 64
        elif tamper == 'wrong_binding':
            parsed = m.parse(raw); parsed['binding']['expected_head'] = 'e' * 40
            raw = m.canonical(parsed); actual = broker.actual(raw)
        else:
            errors = b'synthetic child noise'; actual.update(stderr_bytes=len(errors), stderr_sha256=m.sha(errors))
        return raw, errors, actual
    monkeypatch.setattr(m, 'capture', capture)
    outcome, code = m.run(broker.args, broker.deadline)
    assert code == 2 and outcome['result']['parent_failure'] in m.FINITE
    assert outcome['result']['child'] is None and len(broker.calls) == 1
    assert m.validate_output(external(outcome, broker.args), 2, broker.args)['outcome'] == outcome


@pytest.mark.parametrize('bound', ('deadline', 'channel_bound', 'capture_failed', 'reap_unknown'))
def test_parent_preserves_nonaccepted_actual_capture_bound_without_retry(broker, monkeypatch, bound):
    def capture(command, safe, timeout, **kwargs):
        broker.calls.append((command, safe, timeout, kwargs))
        actual = broker.actual(b'', None if bound == 'reap_unknown' else -9)
        actual['bound'] = bound
        return b'', b'', actual
    monkeypatch.setattr(m, 'capture', capture)
    outcome, code = m.run(broker.args, broker.deadline)
    assert code == 2 and len(broker.calls) == 1
    result = outcome['result']
    assert result['child'] is None and result['child_actual']['bound'] == bound
    assert result['child_actual']['actual_exit'] is None if bound == 'reap_unknown' else result['child_actual']['actual_exit'] == -9
    assert m.validate_output(external(outcome, broker.args), 2, broker.args)['outcome'] == outcome
    with pytest.raises(m.Refused): m.validate_output(external(outcome, broker.args), 0, broker.args)


def test_late_parent_postflight_failure_preserves_valid_closed_child_but_not_success(broker, monkeypatch):
    monkeypatch.setattr(m, 'preflight', lambda *args: (_ for _ in ()).throw(m.Refused('source_pin')))
    outcome, code = m.run(broker.args, broker.deadline)
    assert code == 2 and outcome['result']['child']['state']['diagnostic_complete']
    assert outcome['result']['parent_failure'] == 'source_pin' and len(broker.calls) == 1
    assert m.validate_output(external(outcome, broker.args), 2, broker.args)['outcome'] == outcome
    with pytest.raises(m.Refused): m.validate_output(external(outcome, broker.args), 0, broker.args)


def test_bad_report_pin_does_not_clear_parent_actual_or_child_state(broker):
    outcome, code = m.run(broker.args, broker.deadline)
    outcome['report']['sha256'] = 'e' * 64
    with pytest.raises(m.Refused): m.validate_output(external(outcome, broker.args), code, broker.args)


def test_second_parent_call_refuses_before_a_second_capture(broker):
    assert m.run(broker.args, broker.deadline)[1] == 0
    with pytest.raises(m.Refused) as caught: m.run(broker.args, broker.deadline)
    assert m.finite(caught.value) == 'claim_spent' and len(broker.calls) == 1


def test_child_stderr_never_enters_closed_parent_result(broker, monkeypatch):
    def capture(command, safe, timeout, **kwargs):
        broker.calls.append((command, safe, timeout, kwargs))
        noise = b'synthetic-sensitive-looking-data'
        actual = broker.actual(b'', 2); actual.update(stderr_bytes=len(noise), stderr_sha256=m.sha(noise))
        return b'', noise, actual
    monkeypatch.setattr(m, 'capture', capture)
    outcome, code = m.run(broker.args, broker.deadline)
    assert code == 2 and b'sensitive-looking-data' not in m.canonical(outcome)
    assert outcome['result']['child_actual']['stderr_bytes'] > 0
    assert m.validate_output(external(outcome, broker.args), 2, broker.args)['outcome'] == outcome
