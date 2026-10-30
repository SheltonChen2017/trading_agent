"""M one-use offline source/caller tests; no production/private source access."""
import ast
import copy
import csv
import io
import json
import time
import zipfile
from types import SimpleNamespace as NS

import pytest

from scripts import observe_arv2_r298_reference_ticker as m
from tests.analyst_revisions_v2 import test_r298_quote_diagnostic_caller as base
from tests.analyst_revisions_v2._post_merge_pins import current_pin

args, control = base.args, base.control


@pytest.fixture(autouse=True)
def no_old_operations(monkeypatch):
    monkeypatch.setattr(base, 'm', m)
    def forbidden(*_, **__): raise AssertionError('unmocked private or operational entrypoint')
    for module, names in ((m.previous, ('main', 'run', 'observe', 'worker', 'run_worker', 'join_worker')),
        (m.admission, ('admit',)), (m.admitted.prep, ('construct',)),
        (m.capture_source, ('capture_sharadar_history', 'load_sharadar_capture_artifact',
            '_visit_authenticated_sharadar_capture_rows_for_bridge')),
        (m.source_guard.historical, ('snapshot',))):
        for name in names: monkeypatch.setattr(module, name, forbidden)


def test_exact_public_source_pins_context_and_no_operation_protocol():
    assert m.SCHEMA == 'arv2-r298-reference-ticker-authentication-v1'
    assert m.CONTROL.name == 'R323-20261025-M' and m.CONTROL != m.previous.CONTROL
    assert m.DEADLINE_SECONDS == 300 and m.MAX_ROWS == 250000
    assert m.identity_join.context_digest(m.context()) == m.CONTEXT_SHA256
    for name, pin in m.pins().items():
        assert len(pin) == 64 and m.sha((m.ROOT / name).read_bytes()) == current_pin(name, pin)
    record = m.profile_record()
    assert record['l_control_read'] is False and record['l_actual_exit'] == 0
    assert record['new_strategy_looks'] == record['result_cell'] == 0
    assert record['historical_security_continuity_proven'] is False
    assert record['opaque_route_serialized_or_persisted'] is False
    assert record['only_original_TICKERS_archive_opened'] is True
    tree = ast.parse(m.SOURCE.read_bytes())
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute) and node.func.attr in ('_client', 'request', '_api_key',
            'capture_sharadar_history', 'load_sharadar_capture_artifact',
            '_visit_authenticated_sharadar_capture_rows_for_bridge', 'snapshot')]


def test_native_profile_denies_old_controls_original_other_archives_credentials_and_network():
    value = m.native_profile()
    assert '(deny network*)' in value and '/usr/bin/security' in value
    assert str(m.previous.CONTROL) in value
    assert str(m.VINTAGE_PATH / '02-actions-years-full.zip') in value
    assert str(m.VINTAGE_PATH / '03-fundamentals-years-full.zip') in value
    assert '(require-not (literal "' + str(m.CONTROL.parent) + '"))' in value
    assert '(require-not (subpath "' + str(m.CONTROL) + '"))' in value
    assert str(m.ROOT / 'artifacts') in m.native_profile(artifacts=True)


def test_claim_exclusive_before_consumer(control, args, monkeypatch):
    called = []
    def consume(*_):
        assert (control / 'claim.json').is_file()
        called.append('consume')
        raise m.Refused('row_match')
    monkeypatch.setattr(m, 'consume', consume)
    result = m.run(args, time.monotonic() + 10)
    assert called == ['consume'] and result['failure']['failure_code'] == 'row_match'
    assert result['failure']['claim_consumed'] is True
    assert m.validate_output(m.canonical({'binding': m.binding(args), 'outcome': result}), 2, args)
    with pytest.raises(m.Refused): m.run(args, time.monotonic() + 10)
    assert called == ['consume']


@pytest.mark.parametrize('mutation', ['mode', 'new', 'replacement', 'inplace'])
def test_store_metadata_change_refuses(control, mutation):
    base.test_store_detects_endpoint_change(control, mutation)


@pytest.fixture
def archive(monkeypatch):
    header = ['table', 'ticker', 'permaticker', 'isdelisted', 'category', 'exchange', 'sector',
        'industry', 'figi', 'firstpricedate', 'lastpricedate'] + ['f' + str(i) for i in range(17)]
    rows = [{key: 'x' for key in header}, {key: 'y' for key in header}]
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n')
    writer.writerow(header)
    writer.writerows([list(row.values()) for row in rows])
    payload = stream.getvalue().encode('utf-8')
    raw_header = payload.partition(b'\n')[0] + b'\n'
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr('tickers.csv', payload)
    compressed = data.getvalue()
    with zipfile.ZipFile(io.BytesIO(compressed), 'r') as zipped: info = zipped.infolist()[0]
    manifest = b'{"synthetic":true}\n'
    monkeypatch.setattr(m, 'MANIFEST_SHA256', m.sha(manifest))
    monkeypatch.setattr(m, 'ARCHIVE_BYTES', len(compressed)); monkeypatch.setattr(m, 'ARCHIVE_SHA256', m.sha(compressed))
    monkeypatch.setattr(m, 'MEMBER_BYTES', len(payload)); monkeypatch.setattr(m, 'MEMBER_SHA256', m.sha(payload))
    monkeypatch.setattr(m, 'HEADER_BYTES', len(raw_header)); monkeypatch.setattr(m, 'HEADER_SHA256', m.sha(raw_header))
    monkeypatch.setattr(m, 'SOURCE_ROW_SHA256', m.evidence.source_row_digest(rows[1]))
    member = NS(name='tickers.csv', compressed_byte_count=info.compress_size,
        uncompressed_byte_count=len(payload), crc32=info.CRC, content_sha256=m.sha(payload),
        row_count=2, columns=tuple(header))
    declared = NS(dataset=m.capture_source.SharadarDataset.TICKERS, archive_file=m.ARCHIVE_NAME,
        archive_byte_count=len(compressed), archive_sha256=m.sha(compressed), members=[member])
    monkeypatch.setattr(m.capture_source, '_parse_manifest', lambda *_: (
        {'capture_transport': m.capture_source.PRODUCTION_TRANSPORT}, [declared]))
    return NS(manifest=manifest, marker=(m.MANIFEST_SHA256 + '\n').encode('ascii'),
        compressed=compressed, payload=payload, rows=rows, member=member, declared=declared)


def test_full_zip_member_header_then_unique_original_row_hash(archive):
    row, count = m.original_row(archive.manifest, archive.marker, archive.compressed, time.monotonic() + 30)
    assert row == archive.rows[1] and count == 2


@pytest.mark.parametrize('change', ['manifest', 'marker', 'archive', 'archive-size', 'member-sha', 'member-size',
    'header-sha', 'header-size', 'declared-name', 'declared-crc', 'declared-count', 'target'])
def test_exact_authentication_or_census_change_refuses(archive, monkeypatch, change):
    manifest, marker, compressed = archive.manifest, archive.marker, archive.compressed
    if change == 'manifest': manifest += b' '
    elif change == 'marker': marker = b'0' * 64 + b'\n'
    elif change == 'archive': compressed += b'x'
    elif change == 'archive-size': monkeypatch.setattr(m, 'ARCHIVE_BYTES', m.ARCHIVE_BYTES + 1)
    elif change == 'member-sha': monkeypatch.setattr(m, 'MEMBER_SHA256', 'f' * 64)
    elif change == 'member-size': monkeypatch.setattr(m, 'MEMBER_BYTES', m.MEMBER_BYTES + 1)
    elif change == 'header-sha': monkeypatch.setattr(m, 'HEADER_SHA256', 'f' * 64)
    elif change == 'header-size': monkeypatch.setattr(m, 'HEADER_BYTES', m.HEADER_BYTES + 1)
    elif change == 'declared-name': archive.member.name = 'wrong.csv'
    elif change == 'declared-crc': archive.member.crc32 += 1
    elif change == 'declared-count': archive.member.row_count += 1
    else: monkeypatch.setattr(m, 'SOURCE_ROW_SHA256', 'f' * 64)
    with pytest.raises(m.Refused): m.original_row(manifest, marker, compressed, time.monotonic() + 30)


def test_no_row_interpretation_precedes_archive_member_authentication(archive, monkeypatch):
    calls = []
    monkeypatch.setattr(m.evidence, 'source_row_digest', lambda *_: calls.append('ROW'))
    monkeypatch.setattr(m, 'MEMBER_SHA256', 'f' * 64)
    with pytest.raises(m.Refused): m.original_row(archive.manifest, archive.marker, archive.compressed, time.monotonic() + 30)
    assert calls == []


@pytest.fixture
def consumer(args, monkeypatch):
    events = []
    old_packet, plain, projected = {'synthetic': True}, object(), object()
    row, binding, match = {'synthetic': 'row'}, {'synthetic': 'binding'}, {'synthetic': 'match'}
    proof = {'context_sha256': m.CONTEXT_SHA256, 'source_row_sha256': m.SOURCE_ROW_SHA256,
        'whole_binding_row_sha256': m.BINDING_ROW_SHA256, **m.CONTEXT['witnesses'][0]}
    class OpaqueRoute:
        def __str__(self): raise AssertionError('route formatted')
        def __repr__(self): raise AssertionError('route formatted')
        def __iter__(self): raise AssertionError('route serialized')
    class Guard:
        fail = False
        def __init__(self, *, deadline): events.append('guard-init')
        def __enter__(self): events.append('guard-enter'); return self
        def read(self, name, deadline): events.append('read:' + name); return b'synthetic'
        def verify(self): events.append('guard-verify')
        def __exit__(self, *args):
            events.append('guard-return')
            if self.fail: raise m.source_guard.Refused('metadata_changed')
    for key in ('QC_USER_ID', 'QC_API_TOKEN', 'SHARADAR_API_KEY', 'MASSIVE_API_KEY', 'POLYGON_API_KEY',
        'EODHD_API_TOKEN', 'FMP_API_KEY'): monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(m.source_guard, 'SourceGuard', Guard)
    monkeypatch.setattr(m.admission, 'admit', lambda *_: events.append('admit') or old_packet)
    monkeypatch.setattr(m.admitted.prep, 'construct', lambda *_: events.append('construct') or (plain, projected))
    monkeypatch.setattr(m.previous, '_constructed_matches', lambda *_: events.append('snapshot') or ('same',))
    monkeypatch.setattr(m.identity_join, 'join', lambda *_: events.append('join') or {'synthetic': 'joined'})
    monkeypatch.setattr(m, '_catalog', lambda *_: (binding, match))
    monkeypatch.setattr(m, 'original_row', lambda *_: events.append('row') or (row, 2))
    def verify(left, right, context, *, expected_match):
        assert left is row and right is binding and expected_match is match and context == m.context()
        events.append('evidence')
        return proof, OpaqueRoute()
    monkeypatch.setattr(m.evidence, 'verify', verify)
    monkeypatch.setattr(m.evidence, 'validate_receipt', lambda value: copy.deepcopy(value))
    monkeypatch.setattr(m, 'preflight', lambda *_: events.append('preflight'))
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: events.append('environment'))
    return NS(events=events, Guard=Guard, proof=proof)


def test_guard_holds_through_evidence_and_both_private_postchecks_no_route_output(args, consumer):
    result = m.consume(args, time.monotonic() + 30)
    assert consumer.events == ['guard-init', 'guard-enter', 'admit', 'construct', 'snapshot', 'join',
        'read:manifest.json', 'read:manifest.sha256', 'read:' + m.ARCHIVE_NAME, 'row', 'evidence',
        'construct', 'snapshot', 'admit', 'preflight', 'environment', 'guard-verify', 'guard-return']
    assert result['receipt'] == consumer.proof and b'"route":' not in m.canonical(result)
    assert result['result_cell'] == 0 and result['qc_contact'] is result['provider_contact'] is False


@pytest.mark.parametrize('change', ['guard-return', 'construct', 'admission'])
def test_late_guard_or_private_admission_drift_never_publishes_success(control, args, consumer, monkeypatch, change):
    if change == 'guard-return': consumer.Guard.fail = True
    elif change == 'construct':
        count = []
        monkeypatch.setattr(m.previous, '_constructed_matches', lambda *_: count.append(1) or len(count))
    else:
        count = []
        monkeypatch.setattr(m.admission, 'admit', lambda *_: count.append(1) or {'generation': len(count)})
    outcome = m.run(args, time.monotonic() + 30)
    assert set(outcome) == {'failure'} and not (control / 'report.json').exists()
    assert outcome['failure']['failure_code'] in ('security_metadata_changed', 'admission_changed')
    assert m.validate_output(m.canonical({'binding': m.binding(args), 'outcome': outcome}), 2, args)


@pytest.mark.parametrize('key', ['QC_USER_ID', 'QC_API_TOKEN', 'SHARADAR_API_KEY', 'MASSIVE_API_KEY', 'EODHD_API_TOKEN'])
def test_credentials_refuse_before_private_source_guard(args, consumer, monkeypatch, key):
    monkeypatch.setenv(key, 'synthetic-only')
    with pytest.raises(m.Refused, match='credentials_present'): m.consume(args, time.monotonic() + 30)
    assert consumer.events == []


@pytest.mark.parametrize('change', ['exit', 'pin', 'source', 'context', 'flags', 'count', 'route', 'extra'])
def test_success_requires_actual_zero_exact_bindings_and_no_opaque_output(control, args, consumer, change):
    outcome = m.run(args, time.monotonic() + 30)
    assert m.validate_output(m.canonical({'binding': m.binding(args), 'outcome': outcome}), 0, args)
    actual = 0
    if change == 'exit': actual = 2
    elif change == 'pin': outcome['report']['sha256'] = 'f' * 64
    elif change == 'source': outcome['result']['receipt']['source_row_sha256'] = 'f' * 64
    elif change == 'context': outcome['result']['context_sha256'] = 'f' * 64
    elif change == 'flags': outcome['result']['paper_or_live_ready'] = True
    elif change == 'count': outcome['result']['csv_row_count'] = True
    elif change == 'route': outcome['result']['route'] = 'PRIVATE'
    else: outcome['result']['extra'] = False
    with pytest.raises((m.Refused, m.evidence.Refused)):
        m.validate_output(m.canonical({'binding': m.binding(args), 'outcome': outcome}), actual, args)


@pytest.mark.parametrize('code', sorted(m.source_guard.FINITE))
def test_native_guard_closed_failures_remain_finite(args, code):
    result = m.finite(m.source_guard.Refused(code))
    assert result == 'security_' + code and m._finite_code(result)
    assert m.validate_output(m.canonical({'binding': m.binding(args), 'preflight_failure': result}), 2, args)


@pytest.mark.parametrize('code', sorted(m.evidence.FINITE))
def test_pure_evidence_closed_failures_remain_finite(args, code):
    result = m.finite(m.evidence.Refused(code))
    assert result == 'evidence_' + code and m._finite_code(result)


def test_inert_capture_child_inherits_the_test_runners_native_denial(tmp_path):
    raw, stderr, observed = m.capture([str(m.PYTHON), '-B', '-c', 'print("synthetic-native-profile")'],
        m.capture_support._environment(tmp_path), 5)
    assert observed['actual_exit'] == 0 and observed['bound'] is None and not stderr
    assert raw == b'synthetic-native-profile\n'


def test_observer_uses_native_denial_no_credentials_and_authenticated_actual_failure(args, monkeypatch):
    monkeypatch.setenv('QC_API_TOKEN', 'synthetic-token')
    monkeypatch.setenv('SHARADAR_API_KEY', 'synthetic-token')
    expected = {'binding': m.binding(args), 'preflight_failure': 'source_binding'}
    calls = []
    def capture(command, env, timeout, **kwargs):
        calls.append(command)
        assert command[0] == '/usr/bin/sandbox-exec' and '(deny network*)' in command[2]
        assert not {'QC_API_TOKEN', 'SHARADAR_API_KEY'} & set(env)
        assert kwargs['stdout_limit'] == m.MAX_OUTPUT
        actual = 2 if len(calls) == 1 else 0
        return m.canonical(expected), b'', {'actual_exit': actual, 'bound': None}
    monkeypatch.setattr(m, 'capture', capture)
    observed, code = m.observe(args)
    assert code == 2 and observed['output_authenticated'] is True and observed['output'] == expected
    assert len(calls) == 2 and 'run' in calls[0] and 'validate' in calls[1]
    assert b'synthetic-token' not in m.canonical(observed)
