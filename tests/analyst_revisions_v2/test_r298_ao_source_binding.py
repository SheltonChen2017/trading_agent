"""Exactly four public AO fact tests; no operational or artifact access."""
import ast
import builtins
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess

from scripts import arv2_r298_ao_source_binding as m
from scripts import diagnose_arv2_r298_public_transport_v2 as ao


def test_AO_three_actual_zero_exits_and_external_channel_joins():
    fact = m.observed_fact()
    assert fact['expected_head'] == 'bccc394a3478aa260bb0948c8dc67d4f3051c366'
    assert fact['caller_sha256'] == 'cd7fe6608ba4b56a748efe8fc1f738d94d6dbfd02da6f724b57644118db4d57d'
    for role in ('producer', 'validator', 'child'):
        actual = fact[role]
        assert actual['actual_exit'] == 0 and actual['bound'] is None and actual['spawn_observed'] is True
        assert actual['stderr_bytes'] == 0
        assert actual['stderr_sha256'] == hashlib.sha256(b'').hexdigest()
        assert datetime.fromisoformat(actual['dispatched_at']) <= datetime.fromisoformat(actual['completion_observed_at'])
    assert fact['producer']['stdout_bytes'] == fact['validator']['stdout_bytes'] == 2776
    assert fact['producer']['stdout_sha256'] == fact['validator']['stdout_sha256'] == 'ff790b98087a57c321841a08550d3cd4f50343260d512446d39dd16ec8ff6789'
    assert fact['child']['stdout_bytes'] == 1191
    assert fact['child']['stdout_sha256'] == '665a0c7b63768be8abec681117bf66901e52c18dc533997a8d9a05778aea7aad'
    assert fact['producer']['dispatched_at'] <= fact['child']['dispatched_at'] < fact['child']['completion_observed_at'] <= fact['producer']['completion_observed_at']
    assert fact['producer']['completion_observed_at'] < fact['validator']['dispatched_at']


def test_AO_report_stage_and_exact_frozen_policy_binding_preserves_closed_gates():
    fact = m.observed_fact()
    assert fact['profile_sha256'] == hashlib.sha256(ao.canonical(ao.profile_record())).hexdigest()
    assert fact['verified_policy_sha256'] == hashlib.sha256(ao.native_profile('child').encode('ascii')).hexdigest()
    assert fact['report'] == {'byte_count': 2360, 'sha256': 'a769ed73c93ea4a18d1882aef19dad7af0fd0d901df22be88725a252ca410e75'}
    assert fact['journal'] == {'byte_count': 1265, 'sha256': 'fd89d3d877740c546ee3d1a3012f96f9cc02a9035a797320b5c9547438ec14e4'}
    assert fact['stages'] == list(ao.STAGES) == ['dns', 'tcp', 'tls', 'http']
    assert fact['DNS']['selected_ordinal'] == 0 and fact['DNS']['selected_family'] == 'AF_INET6'
    assert fact['DNS']['families'] == {'AF_INET': 2, 'AF_INET6': 2, 'unsupported': 0}
    assert fact['DNS']['count'] == 4 and fact['HEAD_send_attempts'] == 1
    assert fact['TLS']['version'] == 'TLSv1.3' and fact['first_HTTP_status'] == 404
    assert fact['status_line_byte_count'] == 24 and fact['physical_packets'] is None
    assert fact['only_policy_exception'] == '/private/var/run/mDNSResponder'
    assert ao.profile_record()['egress_is_not_domain_fence'] is True
    assert all(value is False for key, value in fact.items() if key in (
        'credential_access', 'provider_data_endpoint_called', 'price_input_admitted',
        'historical_failure_cause_proven', 'fresh_operation_granted', 'point_in_time_proven',
        'formal_forward_ready', 'paper_or_live_ready'))
    profile = m.profile_record()
    raw = json.dumps(fact, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')
    assert profile['observed_fact_sha256'] == hashlib.sha256(raw).hexdigest() == 'f0c5db3f65451a93a82384b16603fb8f349980433566146af1b338d7b533dca8'
    assert all(value is False for key, value in profile.items() if key not in ('schema', 'observed_fact_sha256'))


def test_AO_accessors_return_independent_nested_copies():
    fact, profile = m.observed_fact(), m.profile_record()
    before_fact, before_profile = m.observed_fact(), m.profile_record()
    fact['producer']['actual_exit'] = 2
    fact['DNS']['families']['AF_INET'] = 999
    fact['stages'].append('retry')
    profile['new_operation_or_read_granted'] = True
    assert m.observed_fact() == before_fact and m.profile_record() == before_profile


def test_AO_source_is_pinned_inert_and_contains_no_sensitive_or_operation_payload(monkeypatch):
    raw = Path(m.__file__).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == '908d4b8143d2d981f638df93fb6f1f3956a6d0902ab104388b2dd6b5dfc0de2c'
    tree = ast.parse(raw)
    imports = [alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names]
    assert imports == ['hashlib', 'json']
    forbidden_keys = {'address', 'addresses', 'sockaddr', 'api_key', 'api_token', 'password',
        'authorization', 'cookie', 'price', 'prices', 'raw_response', 'raw_exception', 'message', 'traceback'}
    def inspect(value):
        if type(value) is dict:
            assert not (set(value) & forbidden_keys)
            for child in value.values(): inspect(child)
        elif type(value) is list:
            for child in value: inspect(child)
    inspect(m.observed_fact())
    def deny(*args, **kwargs): raise AssertionError('inert public anchor attempted I/O')
    namespace = {'__name__': 'synthetic_AO_inert_import'}
    with monkeypatch.context() as patch:
        for obj, name in ((builtins, 'open'), (os, 'open'), (Path, 'read_bytes'), (Path, 'read_text'),
                (socket, 'socket'), (socket, 'getaddrinfo'), (socket, 'create_connection'), (subprocess, 'Popen')):
            patch.setattr(obj, name, deny)
        exec(compile(raw, '<public-AO-anchor>', 'exec'), namespace)
        assert namespace['observed_fact']() == m.observed_fact()
        assert namespace['profile_record']() == m.profile_record()
        assert namespace['observed_fact']()['fresh_operation_granted'] is False
