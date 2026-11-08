"""Synthetic O identity preparation; no actual artifact, credential or contact."""
import ast
import copy
import time
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from scripts import arv2_r298_sharadar_reference_binding as m
from tests.analyst_revisions_v2 import test_r298_reference_ticker_evidence as evidence_cases
from tests.analyst_revisions_v2 import test_r298_reference_ticker_source_guard as source_cases
from tests.analyst_revisions_v2 import test_newrule_plain_projection as plain_cases

SOURCE_GUARD_CLASS = m.source_guard.SourceGuard


@pytest.fixture(autouse=True)
def no_operations(monkeypatch):
    def forbidden(*_, **__):
        raise AssertionError('unmocked private or operational use')
    for module, names in ((m.original, ('run', 'consume', 'main', 'observe', 'preflight', 'original_row', '_catalog')),
            (m.admission, ('admit',)), (m.original.admitted.prep, ('construct',)),
            (m.identity_join, ('join',)), (m.source_guard, ('SourceGuard',)),
            (m.original.previous, ('run', 'main', 'observe', 'worker', 'run_worker', 'join_worker')),
            (m.original.capture_source, ('capture_sharadar_history', 'load_sharadar_capture_artifact')),
            (m.source_guard.historical, ('snapshot',))):
        for name in names:
            monkeypatch.setattr(module, name, forbidden)
    for key in ('QC_USER_ID', 'QC_API_TOKEN', 'SHARADAR_API_KEY', 'MASSIVE_API_KEY',
            'POLYGON_API_KEY', 'EODHD_API_TOKEN', 'FMP_API_KEY'):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(scope='module')
def axis():
    return evidence_cases.fixtures.axis.__wrapped__()


@pytest.fixture
def packet():
    return {'permaticker': '123456', 'expected_composite_figi': 'BBG000000001',
        'exchange_mic': 'XNYS', 'original_cusips': ('012345678', '123456789')}


def synthetic_objects():
    paths = tuple(reversed(m.source_guard.CAPTURE.parents)) + (m.source_guard.CAPTURE,) + tuple(
        m.source_guard.CAPTURE / name for name in m.source_guard.LEAVES)
    result = []
    for index, path in enumerate(paths):
        ancestor = path != m.source_guard.ROOT and m.source_guard.ROOT not in path.parents
        security = None if ancestor else tuple(m.source_guard.VINTAGE_XATTR_PINS) if path == m.source_guard.CAPTURE else {
            'acl_empty': True, 'xattrs': {'com.apple.provenance': {'size': 3, 'sha256': 'c' * 64}}}
        result.append({'path': path, 'fd': index + 10, 'parent': max(10, index + 9),
            'name': '.' if index == 0 else path.name, 'metadata': tuple(range(index + 1, index + 11)),
            'leaf': path.parent == m.source_guard.CAPTURE, 'security': security})
    return result


@pytest.fixture
def prepared(monkeypatch, axis):
    case = evidence_cases.make_case(monkeypatch, axis, last='2026-09-10')
    proof, _ = m.evidence.verify(case.row, case.binding, case.context, expected_match=case.expected)
    monkeypatch.setattr(m, 'M_EVIDENCE_SHA256', m.evidence.receipt_digest(proof))
    monkeypatch.setattr(m, 'CSV_ROWS', 2)
    for name, value in (('IDENTITY_SHA256', case.expected['identity_sha256']),
            ('SOURCE_ROW_SHA256', case.expected['source_row_sha256']),
            ('BINDING_ROW_SHA256', case.expected['whole_binding_row_sha256']),
            ('CONTEXT_SHA256', m.identity_join.context_digest(case.context))):
        monkeypatch.setattr(m, name, value)
    events, guards = [], []

    class Guard:
        fail_close = False
        def __init__(self, *, deadline):
            self._active, self._objects = False, synthetic_objects()
            guards.append(self); events.append('guard-init')
        def __enter__(self):
            self._active = True; events.append('guard-enter'); return self
        def read(self, name, deadline):
            assert self._active
            events.append('read:' + name); return b'synthetic only'
        def verify(self):
            assert self._active
            events.append('guard-verify')
        def __exit__(self, kind, value, traceback):
            events.append('guard-return'); self._active = False
            if self.fail_close and kind is None:
                raise m.source_guard.Refused('close')
            return False

    snapshot = (b'plain', b'projected', b'profile',
        tuple((b'metadata' + bytes([index]), b'payload' + bytes([index])) for index in range(6)),
        tuple(('public_' + str(index) + '.py', b'public source') for index in range(11)))
    old_packet, plain, projected = {'synthetic': 'public admission only'}, object(), object()
    monkeypatch.setattr(m.source_guard, 'SourceGuard', Guard)
    monkeypatch.setattr(m.original, 'context', lambda: copy.deepcopy(case.context))
    monkeypatch.setattr(m.admission, 'admit', lambda *_: events.append('admit') or copy.deepcopy(old_packet))
    monkeypatch.setattr(m.original.admitted.prep, 'construct', lambda *_: events.append('construct') or (plain, projected))
    monkeypatch.setattr(m.original.previous, '_constructed_matches', lambda *_: events.append('snapshot') or snapshot)
    monkeypatch.setattr(m.identity_join, 'join', lambda *_: events.append('join') or {'synthetic': True})
    monkeypatch.setattr(m.original, '_catalog', lambda *_: (case.binding, case.expected))
    monkeypatch.setattr(m.original, 'original_row', lambda *_: events.append('original-row') or (copy.deepcopy(case.row), 2))
    monkeypatch.setattr(m.original.environment, 'require_safe_environment', lambda: events.append('environment'))
    return NS(case=case, proof=proof, guards=guards, Guard=Guard, events=events, snapshot=snapshot,
        packet=old_packet)


def test_profile_has_narrow_four_field_scope_no_old_operational_replay():
    profile = m.profile_record()
    assert profile['private_packet_fields'] == ['permaticker', 'expected_composite_figi', 'exchange_mic', 'original_cusips']
    assert profile['m_nested_evidence_sha256'] == '5f9f7ecff6830571bc3fd57737ac71ffab06e21c0be84ce2a2fafbbd8c303dbb'
    assert profile['m_control_read'] is profile['m_operational_entrypoint_called'] is False
    assert profile['consumer_runs_before_guard_return'] is True
    assert profile['continuous_source_guard_across_provider_contact'] is False
    tree = ast.parse(Path(m.__file__).read_bytes())
    forbidden = {'run', 'consume', 'main', 'observe', 'preflight', '_client', 'request',
        'capture_sharadar_history', 'load_sharadar_capture_artifact', 'snapshot'}
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute) and node.func.attr in forbidden]


def test_packet_digest_native_tuple_ipc_list_equal_without_private_public_fields(packet):
    assert m.validate_packet(packet) == packet
    assert m.validate_packet(m.private_record(packet)) == packet
    assert m.packet_digest(packet) == m.packet_digest(m.private_record(packet))
    assert set(m.private_record(packet)) == set(packet)


@pytest.mark.parametrize('change', ['extra', 'missing', 'bool_perma', 'space_perma', 'ticker_perma',
    'lower_figi', 'short_figi', 'mic', 'cusips_empty', 'cusips_duplicate', 'cusips_unsorted',
    'cusips_long', 'cusip_bad', 'cusips_generator'])
def test_private_packet_refuses_unbounded_or_ambiguous_values(packet, change):
    if change == 'extra': packet['ticker'] = 'SECRET'
    elif change == 'missing': packet.pop('permaticker')
    elif change == 'bool_perma': packet['permaticker'] = True
    elif change == 'space_perma': packet['permaticker'] = ' 123456'
    elif change == 'ticker_perma': packet['permaticker'] = 'SECRET'
    elif change == 'lower_figi': packet['expected_composite_figi'] = packet['expected_composite_figi'].lower()
    elif change == 'short_figi': packet['expected_composite_figi'] = 'BBG'
    elif change == 'mic': packet['exchange_mic'] = 'UNKNOWN'
    elif change == 'cusips_empty': packet['original_cusips'] = ()
    elif change == 'cusips_duplicate': packet['original_cusips'] *= 2
    elif change == 'cusips_unsorted': packet['original_cusips'] = tuple(reversed(packet['original_cusips']))
    elif change == 'cusips_long': packet['original_cusips'] = tuple(str(index).zfill(9) for index in range(17))
    elif change == 'cusip_bad': packet['original_cusips'] = ('12345X',)
    else: packet['original_cusips'] = iter(packet['original_cusips'])
    with pytest.raises(m.Refused): m.validate_packet(packet)


def test_initial_and_final_fresh_pair_fingerprints_equal_no_old_control_use(prepared):
    initial = m.prepare(time.monotonic() + 30, phase='initial')
    final = m.prepare(time.monotonic() + 30, phase='final')
    assert initial == final
    receipt, private = initial
    assert type(private['original_cusips']) is tuple
    assert m.validate_pair(receipt, private) == initial
    assert m.fingerprint(receipt) == m.fingerprint(final[0])
    assert len(prepared.guards) == 2 and all(not guard._active for guard in prepared.guards)
    for raw in ('123456', 'SYNTH', 'BBG000000001', '012345678', '2026-09-10'):
        assert raw.encode('ascii') not in m.canonical(receipt)
    assert receipt['provider_contact'] is receipt['provider_route_admitted'] is False


def test_consumer_runs_while_guard_held_and_return_escapes_only_after_close(prepared):
    events = prepared.events
    def consumer(receipt, private):
        assert prepared.guards[-1]._active
        m.validate_pair(receipt, private)
        events.append('consumer')
        return {'closed': True}
    result = m.prepare(time.monotonic() + 30, phase='initial', consumer=consumer)
    assert result == {'closed': True} and not prepared.guards[-1]._active
    index = events.index('consumer')
    assert events[index + 1:] == ['construct', 'snapshot', 'admit', 'environment', 'guard-verify', 'guard-return']
    assert events[:index].count('admit') == 2 and events[:index].count('construct') == 2
    assert len([value for value in events if value.startswith('read:')]) == 3


@pytest.mark.parametrize('change', ['source-final', 'source-consumer', 'close', 'admission', 'snapshot',
    'evidence', 'row-count', 'packet-consumer', 'receipt-consumer'])
def test_late_failure_never_returns_private_payload(prepared, monkeypatch, change):
    consumer_calls = []
    if change == 'close': prepared.Guard.fail_close = True
    elif change == 'admission':
        calls = []
        monkeypatch.setattr(m.admission, 'admit', lambda *_: calls.append(1) or {'generation': len(calls)})
    elif change == 'snapshot':
        calls = []
        monkeypatch.setattr(m.original.previous, '_constructed_matches', lambda *_: calls.append(1) or
            (prepared.snapshot if len(calls) == 1 else prepared.snapshot[:2]))
    elif change == 'evidence': monkeypatch.setattr(m, 'M_EVIDENCE_SHA256', 'f' * 64)
    elif change == 'row-count': monkeypatch.setattr(m, 'CSV_ROWS', 3)
    elif change == 'source-final':
        calls = []
        actual = m.source_fingerprint
        monkeypatch.setattr(m, 'source_fingerprint', lambda guard: calls.append(1) or
            (actual(guard) if len(calls) == 1 else 'f' * 64))
    def consumer(receipt, private):
        consumer_calls.append(1)
        if change == 'source-consumer': prepared.guards[-1]._objects[-1]['metadata'] = tuple([99] * 10)
        if change == 'packet-consumer':
            private['permaticker'] = '777777'; receipt['private_packet_sha256'] = m.packet_digest(private)
        if change == 'receipt-consumer': receipt['fresh_input_snapshot_sha256'] = 'f' * 64
        return {'private': private}
    with pytest.raises((m.Refused, m.source_guard.Refused)):
        m.prepare(time.monotonic() + 30, phase='final', consumer=consumer)
    assert not prepared.guards[-1]._active
    assert bool(consumer_calls) == (change in ('close', 'source-consumer', 'packet-consumer', 'receipt-consumer'))


@pytest.mark.parametrize('field', m.source_guard.FIELDS)
def test_every_ten_metadata_fields_participates_in_fingerprint(prepared, field):
    guard = prepared.Guard(deadline=time.monotonic() + 30)
    with guard:
        before = m.source_fingerprint(guard)
        index = m.source_guard.FIELDS.index(field)
        values = list(guard._objects[-1]['metadata']); values[index] += 1
        guard._objects[-1]['metadata'] = tuple(values)
        assert m.source_fingerprint(guard) != before


def test_descriptor_numbers_are_not_source_identity_but_security_hashes_are(prepared):
    with prepared.Guard(deadline=time.monotonic() + 30) as guard:
        before = m.source_fingerprint(guard)
        for item in guard._objects: item['fd'] += 100; item['parent'] += 100
        assert m.source_fingerprint(guard) == before
        guard._objects[-1]['security']['xattrs']['com.apple.provenance']['sha256'] = 'd' * 64
        assert m.source_fingerprint(guard) != before


def test_real_inroot_held_guard_objects_and_native_abi_doubles_interoperate(tmp_path, monkeypatch):
    case = source_cases.case.__wrapped__(tmp_path, monkeypatch)
    monkeypatch.setattr(m.source_guard, 'SourceGuard', SOURCE_GUARD_CLASS)
    with SOURCE_GUARD_CLASS(deadline=time.monotonic() + 30) as guard:
        before = m.source_fingerprint(guard)
        for item in guard._objects:
            if item['path'] == m.source_guard.CAPTURE:
                assert item['security'] == m.source_guard.VINTAGE_XATTR_PINS
            elif item['path'] == m.source_guard.ROOT or m.source_guard.ROOT in item['path'].parents:
                assert type(item['security']) is dict and set(item['security']) == {'acl_empty', 'xattrs'}
                assert item['security']['acl_empty'] is True and item['security']['xattrs'] == {}
        for name in m.source_guard.LEAVES:
            assert guard.read(name, time.monotonic() + 10) == case.payloads[name]
        guard.verify()
        assert m.source_fingerprint(guard) == before
    assert not guard._active and not guard._objects


def test_genuine_plain_capability_projection_snapshot_shape_uses_transport_bounds(monkeypatch):
    parent = plain_cases.public_parent.__wrapped__()
    case = plain_cases.case.__wrapped__(parent)
    projected = plain_cases.build(case)
    monkeypatch.setattr(m.admission.a11.remote, 'PROJECTION_SHA256', projected.projection_sha256)
    snapshot = m.admission._snapshot(case.plain, projected)
    assert len(snapshot[3]) == len(case.plain.upload_objects) <= m.admission.transport.MAX_OBJECTS
    assert len(snapshot[4]) == 11
    assert len(m._snapshot_digest(snapshot, time.monotonic() + 30)) == 64


@pytest.mark.parametrize('boundary', ['construct', 'admit'])
def test_fresh_private_postcheck_after_consumer_is_mandatory(prepared, monkeypatch, boundary):
    def consumer(receipt, private):
        if boundary == 'construct':
            monkeypatch.setattr(m.original.previous, '_constructed_matches', lambda *_: ('changed',))
        else:
            monkeypatch.setattr(m.admission, 'admit', lambda *_: {'changed': True})
        return {'private': private}
    with pytest.raises(m.Refused, match='admission_changed'):
        m.prepare(time.monotonic() + 30, phase='final', consumer=consumer)
    assert not prepared.guards[-1]._active


@pytest.mark.parametrize('change', ['object', 'metadata', 'acl', 'xattr_value', 'xattr_extra', 'vintage', 'path'])
def test_only_known_guard_shapes_can_be_fingerprinted(prepared, change):
    with prepared.Guard(deadline=time.monotonic() + 30) as guard:
        item = guard._objects[-1]
        if change == 'object': item['raw'] = object()
        elif change == 'metadata': item['metadata'] = (True,) * 10
        elif change == 'acl': item['security']['acl_empty'] = False
        elif change == 'xattr_value': item['security']['xattrs']['com.apple.provenance']['size'] = object()
        elif change == 'xattr_extra': item['security']['xattrs']['secret.raw'] = {'size': 2, 'sha256': 'a' * 64}
        elif change == 'vintage':
            target = next(value for value in guard._objects if value['path'] == m.source_guard.CAPTURE)
            target['security'] = (('raw string not bytes', 2, 'a' * 64),)
        else: item['path'] = object()
        with pytest.raises(m.Refused): m.source_fingerprint(guard)


@pytest.mark.parametrize('phase', ['', 'replay', 0, True])
def test_phase_is_closed_and_not_operational_authority(phase):
    with pytest.raises(m.Refused): m.prepare(time.monotonic() + 30, phase=phase)


def test_credentials_rejected_before_any_private_source(monkeypatch):
    monkeypatch.setenv('SHARADAR_API_KEY', 'synthetic-not-a-secret')
    with pytest.raises(m.Refused, match='credentials_present'):
        m.prepare(time.monotonic() + 30, phase='initial')


class HostileString(str):
    def __hash__(self): raise AssertionError('hostile hash evaluated')
    def __str__(self): raise AssertionError('hostile string formatted')


def test_hostile_packet_primitive_rejected_without_hash_or_render(packet):
    packet['original_cusips'] = (HostileString('012345678'),)
    with pytest.raises(m.Refused): m.validate_packet(packet)


def test_public_receipt_cannot_grant_authority_or_accept_another_packet(prepared):
    receipt, private = m.prepare(time.monotonic() + 30, phase='initial')
    changed = copy.deepcopy(receipt); changed['provider_route_admitted'] = True
    with pytest.raises(m.Refused): m.validate_receipt(changed)
    changed = copy.deepcopy(private); changed['permaticker'] = '777777'
    with pytest.raises(m.Refused): m.validate_pair(receipt, changed)
    changed = copy.deepcopy(receipt); changed['raw_ticker'] = 'SECRET'
    with pytest.raises(m.Refused): m.validate_receipt(changed)
