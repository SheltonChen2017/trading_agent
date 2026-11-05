"""Supplied synthetic data only; no package/source/credential/provider reads."""
import ast
import copy
import hashlib
import inspect
import sys
import time
import types

import pytest

from scripts import arv2_r298_all_route_worker as m
from tests.analyst_revisions_v2 import test_r298_sharadar_all_routes as supplied


def refused(code, callback):
    with pytest.raises(m.Refused) as caught:
        callback()
    assert m.finite(caught.value) == code


@pytest.fixture
def environment(monkeypatch):
    """Explicit test substitution; production exposes no authority bypass."""
    data = supplied.case(2)
    bindings, originals, stocks, funds = data
    monkeypatch.setattr(m, 'EXPECTED_BINDINGS', 2)
    axis = ('2013-01-02', '2026-10-13')
    sessions = [{'schema': 'synthetic-session', 'session_index': i, 'session': session}
        for i, session in enumerate(axis)]
    manifest = {'session_axis_count': 2, 'session_axis_sha256': m.identity.evaluator._stream_sha256(tuple(sessions))}
    selected = {'evaluator_manifest': [manifest], 'session_axis': sessions,
        'runtime_symbol_bindings': bindings}
    record = {'runtime_symbol_binding_count': 2,
        'runtime_symbol_bindings_sha256': supplied.contract(bindings)['binding_stream_sha256'],
        'evaluator_manifest_sha256': 'd' * 64}
    class Plain:
        source_package_sha256 = m.PACKAGE_SHA256
        source_lineage_sha256 = m.LINEAGE_SHA256
        package_sha256 = '1' * 64
        activation_manifest_sha256 = '2' * 64
        parent_proof_sha256 = '3' * 64
        changed = False
        def to_record(self):
            return copy.deepcopy(record)
    plain = Plain()
    events = []
    monkeypatch.setattr(m.october, '_sessions', lambda: axis)
    monkeypatch.setattr(m.identity.evaluator, '_parse_sessions', lambda rows: tuple(row['session'] for row in rows))
    monkeypatch.setattr(m.identity, '_plain', lambda value: ('original', copy.deepcopy(record), []))
    monkeypatch.setattr(m.identity, '_streams', lambda value, rec: copy.deepcopy(selected))
    monkeypatch.setattr(m.identity, '_manifest', lambda value, rec: 'a' * 64)
    monkeypatch.setattr(m.transport, 'require_plain_transport', lambda value: events.append('plain_require'))
    monkeypatch.setattr(m.transport, '_fingerprint', lambda value: 'changed' if value.changed else 'original')
    monkeypatch.setattr(m, '_load_plain', lambda deadline: plain)
    leafs = (b'synthetic manifest', (m.source_guard.MANIFEST_SHA256 + '\n').encode(), b'synthetic archive')
    monkeypatch.setattr(m.source_guard, 'MANIFEST_SHA256', m.sha(leafs[0]))
    leafs = (leafs[0], (m.source_guard.MANIFEST_SHA256 + '\n').encode(), leafs[2])
    monkeypatch.setattr(m.source_guard, 'ARCHIVE_SHA256', m.sha(leafs[2]))
    monkeypatch.setattr(m.source_guard, 'ARCHIVE_BYTES', len(leafs[2]))
    class Guard:
        fail_exit = False
        change = False
        last = None
        def __init__(self, *, deadline):
            self.reads = []
            Guard.last = self
        def __enter__(self):
            events.append('guard_enter')
            return self
        def read(self, name, deadline):
            assert name not in self.reads
            self.reads.append(name)
            events.append('read_' + name)
            return leafs[m.source_guard.LEAVES.index(name)]
        def verify(self):
            events.append('guard_verify')
        def __exit__(self, kind, value, traceback):
            events.append('guard_exit')
            if self.fail_exit:
                raise m.source_guard.Refused('close')
            return False
    monkeypatch.setattr(m.source_guard, 'SourceGuard', Guard)
    monkeypatch.setattr(m, '_guard_fingerprint', lambda guard: ('e' if guard.change else 'f') * 64)
    class Catalog:
        columns = tuple(sorted(m.routes.ORIGINAL_FIELDS))
        def mapping_rows(self):
            events.append('mapping_rows')
            return tuple(copy.deepcopy(originals))
    receipt = {'csv_row_count': len(originals), 'manifest_sha256': m.source_guard.MANIFEST_SHA256,
        'archive_sha256': m.source_guard.ARCHIVE_SHA256, 'archive_byte_count': m.source_guard.ARCHIVE_BYTES,
        'ordered_source_row_digests_sha256': m.sha(m.canonical([
            m.routes.original.source_row_digest(row) for row in originals]) + b'\n')}
    def decode(*raws, deadline):
        assert raws == leafs
        events.append('decode_original')
        return dict(receipt), Catalog()
    def validate(value):
        if value != receipt or set(value) != set(receipt):
            raise ValueError('synthetic receipt changed')
        return dict(value)
    decoder = types.ModuleType('scripts.arv2_r298_original_ticker_catalog')
    decoder.decode_original_catalog, decoder.validate_receipt = decode, validate
    decoder.PrivateOriginalTickerCatalog = Catalog
    decoder.canonical = lambda value: m.canonical(value) + b'\n'
    monkeypatch.setitem(sys.modules, decoder.__name__, decoder)
    import scripts
    monkeypatch.setattr(scripts, 'arv2_r298_original_ticker_catalog', decoder, raising=False)
    stocks_raw, funds_raw = b'synthetic stocks', b'synthetic funds'
    real_join = m.routes.join
    def join(bindings_arg, original_arg, stock_arg, fund_arg, *, binding_contract):
        assert stock_arg == stocks_raw and fund_arg == funds_raw
        events.append('join')
        return real_join(bindings_arg, original_arg, stocks, funds, binding_contract=binding_contract)
    monkeypatch.setattr(m.routes, 'join', join)
    return types.SimpleNamespace(data=data, selected=selected, record=record, plain=plain,
        events=events, guard=Guard, catalog=Catalog, decoder=decoder, receipts=receipt,
        stocks_raw=stocks_raw, funds_raw=funds_raw,
        run=lambda: m.prepare(stocks_raw, funds_raw, deadline=time.monotonic() + 60))


def test_prepare_all_rows_preserves_private_frame_and_returns_only_after_guard_close(environment):
    e = environment
    summary, private = e.run()
    assert summary == m.validate_summary(summary)
    assert len(private['stocks']) == 2 and len(private['funds']) == 8
    assert [row['binding'] for row in private['stocks']] == e.data[0]
    assert summary['private_frame_sha256'] == m.sha(m.canonical(private))
    assert summary['private_frame_byte_count'] == len(m.canonical(private))
    assert summary['source_guard_receipt']['guard_normal_return'] is True
    assert e.events.index('decode_original') < e.events.index('join') < e.events.index('guard_exit')
    assert e.guard.last.reads == list(m.source_guard.LEAVES)
    assert 'plain_require' in e.events
    assert summary['input_binding']['session_axis_count'] == 2
    assert summary['input_binding']['binding_contract'] == supplied.contract(e.data[0])
    assert summary['current_metadata'] == {'stocks': {'byte_count': len(e.stocks_raw), 'sha256': m.sha(e.stocks_raw)},
        'funds': {'byte_count': len(e.funds_raw), 'sha256': m.sha(e.funds_raw)}}
    encoded = m.canonical(summary)
    for needle in (b'SYN1', b'BBG000000001', b'NASDAQ', b'Synthetic issuer', b'"original_row":', b'"route_key":'):
        assert needle not in encoded
    assert all(summary[field] is False for field in m.FALSE_FLAGS)


def test_normal_guard_exit_failure_cannot_return_success(environment):
    environment.guard.fail_exit = True
    refused('source_guard_close', environment.run)


def test_named_route_refusal_is_retained_diagnostic_not_readiness(environment):
    environment.data[2][0]['lastpricedate'] = '2020-12-30'
    summary, private = environment.run()
    assert summary['routing_summary']['refusal_counts']['stocks'] == {'current_interval': 1}
    assert private['stocks'][0]['disposition'] == 'refused'
    assert len(private['stocks']) == 2 and len(private['funds']) == 8
    assert summary['price_coverage_proven'] is False


def test_last_original_mapping_copy_must_match_complete_decoded_digest(environment):
    environment.data[1][-1]['name'] = 'changed synthetic row'
    refused('original_catalog', environment.run)
    assert 'join' not in environment.events


def test_empty_current_catalogs_retain_all_named_refusals(environment):
    environment.data[2].clear(); environment.data[3].clear()
    summary, private = environment.run()
    assert summary['routing_summary']['metadata_row_counts'] == {'stocks': 0, 'funds': 0}
    assert summary['routing_summary']['refusal_counts'] == {
        'stocks': {'current_identity_missing': 2}, 'funds': {'current_identity_missing': 8}}
    assert len(private['stocks']) == 2 and len(private['funds']) == 8


@pytest.mark.parametrize('value', [None, True, bytearray(b'x'), b'', b'x' * (m.MAX_METADATA_BYTES + 1)])
def test_metadata_bounds_before_guard(environment, value):
    refused('metadata_bound', lambda: m._prepare_bound(environment.plain, value,
        environment.funds_raw, deadline=time.monotonic() + 60))
    assert 'guard_enter' not in environment.events


@pytest.mark.parametrize('value', [None, True, float('inf'), float('nan'), -1])
def test_deadline_is_finite_and_not_boolean(value):
    refused('deadline', lambda: m.remaining(value))


def test_plain_authority_is_checked_after_consumers(environment):
    e = environment
    old = e.decoder.decode_original_catalog
    def decode(*args, **kwargs):
        e.plain.changed = True
        return old(*args, **kwargs)
    e.decoder.decode_original_catalog = decode
    refused('plain_changed', e.run)
    assert 'guard_exit' in e.events


def test_selected_stream_change_refuses_after_join(environment, monkeypatch):
    e = environment
    calls = 0
    def streams(plain, record):
        nonlocal calls
        calls += 1
        result = copy.deepcopy(e.selected)
        if calls > 1:
            result['session_axis'][0]['session'] = '2013-01-03'
        return result
    monkeypatch.setattr(m.identity, '_streams', streams)
    refused('plain_changed', e.run)


def test_guard_endpoint_change_refuses(environment):
    e = environment
    old = e.decoder.decode_original_catalog
    def decode(*args, **kwargs):
        e.guard.last.change = True
        return old(*args, **kwargs)
    e.decoder.decode_original_catalog = decode
    refused('source_guard', e.run)


@pytest.mark.parametrize('fault', ['count', 'last_hash', 'last_admission', 'duplicate_figi', 'duplicate_row',
    'last_inventory', 'last_mapping_count', 'reverse', 'stream_hash', 'axis', 'axis_hash', 'source_package'])
def test_full_catalog_and_axis_checks_include_last_row(environment, fault):
    e = environment
    rows = e.selected['runtime_symbol_bindings']
    if fault == 'count':
        rows.pop()
    elif fault == 'last_hash':
        rows[-1]['row_sha256'] = '0' * 64
    elif fault == 'last_admission':
        rows[-1]['security_master_admission_sha256'] = '0' * 64
    elif fault == 'duplicate_figi':
        rows[-1] = copy.deepcopy(rows[0])
    elif fault == 'duplicate_row':
        rows[-1]['row_sha256'] = rows[0]['row_sha256']
    elif fault in ('last_inventory', 'last_mapping_count'):
        row = rows[-1]
        row['admitted_mapping_inventory_sha256' if fault == 'last_inventory' else 'admitted_mapping_count'] = (
            '0' * 64 if fault == 'last_inventory' else 1)
        semantic = dict(row); semantic.pop('row_sha256')
        row['row_sha256'] = hashlib.sha256(m.identity.figi._canonical(semantic)).hexdigest()
        e.record['runtime_symbol_bindings_sha256'] = m.sha(b''.join(
            m.identity.figi._canonical(item) for item in rows))
    elif fault == 'reverse':
        rows.reverse()
    elif fault == 'stream_hash':
        e.record['runtime_symbol_bindings_sha256'] = '0' * 64
    elif fault == 'axis':
        e.selected['session_axis'][-1]['session'] = '2026-10-12'
    elif fault == 'axis_hash':
        e.selected['evaluator_manifest'][0]['session_axis_sha256'] = '0' * 64
    else:
        e.plain.source_package_sha256 = '0' * 64
    with pytest.raises(ValueError):
        e.run()
    assert 'guard_enter' not in e.events


def test_private_payload_hash_or_count_mismatch_cannot_return(environment, monkeypatch):
    real = m.routes.join
    def join(*args, **kwargs):
        summary, private = real(*args, **kwargs)
        summary['private_payload_sha256'] = '0' * 64
        return summary, private
    monkeypatch.setattr(m.routes, 'join', join)
    refused('private_frame', environment.run)


@pytest.mark.parametrize('path,value', [
    (('schema',), 'other'), (('provider_contact',), True), (('qc_contact',), 0),
    (('private_frame_sha256',), '0' * 64), (('private_frame_byte_count',), True),
    (('input_binding', 'source_package_sha256'), '0' * 64),
    (('input_binding', 'session_axis_count'), True),
    (('input_binding', 'ordered_session_values_sha256'), '0' * 64),
    (('input_binding', 'last_session'), '2026-10-12'),
    (('input_binding', 'binding_contract', 'binding_count'), 1),
    (('source_guard_receipt', 'guard_normal_return'), False),
    (('source_guard_receipt', 'metadata_fields'), ['st_ino']),
    (('source_guard_receipt', 'continuous_integrity_proven'), True),
    (('source_guard_receipt', 'original_leaf_pins'), []),
    (('current_metadata', 'stocks', 'byte_count'), True),
    (('routing_summary', 'binding_contract', 'security_master_admission_sha256'), '0' * 64),
    (('routing_summary', 'private_payload_byte_count'), 0),
    (('routing_summary', 'metadata_row_counts', 'stocks'), 100000),
    (('routing_summary', 'disposition_counts', 'stocks'), {'routed': 1}),
    (('routing_summary', 'refusal_counts', 'stocks'), {'current_interval': 1}),
    (('routing_summary', 'catalog_unknown_vocabulary_row_count'), 1000000),
    (('routing_summary', 'catalog_collision_group_counts', 'figi_collision_groups'), -1),
])
def test_summary_rejects_forged_drift_and_false_clearance(environment, path, value):
    summary, _ = environment.run()
    parent = summary
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    with pytest.raises(ValueError):
        m.validate_summary(summary)


@pytest.mark.parametrize('path', [(), ('input_binding',), ('current_metadata', 'stocks'),
    ('source_guard_receipt',), ('routing_summary',), ('routing_summary', 'catalog_collision_group_counts')])
def test_summary_rejects_unknown_secret_looking_fields(environment, path):
    summary, _ = environment.run()
    target = summary
    for key in path:
        target = target[key]
    target['secret-do-not-output'] = 'private-value'
    with pytest.raises(ValueError):
        m.validate_summary(summary)


def test_direct_loader_binds_exact_inputs_and_calls_no_old_operations(monkeypatch):
    events, wrapper, package, plain = [], object(), object(), object()
    def load(path, **kwargs):
        events.append(('load', path, kwargs))
        return wrapper
    def old_input(value):
        assert value is wrapper
        events.append('input')
        return package
    def build(value, **kwargs):
        assert value is package
        events.append(('build', kwargs))
        return plain
    monkeypatch.setattr(m.october, 'load_october_order_input_package', load)
    monkeypatch.setattr(m.original, '_input', old_input)
    monkeypatch.setattr(m.transport, 'build_plain_transport', build)
    assert m._load_plain(time.monotonic() + 60) is plain
    assert events[0] == ('load', m.PACKAGE, {'expected_package_sha256': m.PACKAGE_SHA256,
        'lineage_path': m.LINEAGE, 'expected_lineage_sha256': m.LINEAGE_SHA256})
    assert events[1] == 'input'
    assert events[2] == ('build', {'expected_package_sha256': m.PACKAGE_SHA256,
        'expected_lineage_sha256': m.LINEAGE_SHA256})
    source = inspect.getsource(m)
    for forbidden in ('.admit(', '.construct(', '.reconstruct_projection(', 'subprocess.',
        'os.environ', 'read_bytes(', 'write_bytes(', 'argparse'):
        assert forbidden not in source
    tree = ast.parse(source)
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id in ('open', 'print', 'eval', 'exec', '__import__') for node in ast.walk(tree))
    assert 'if __name__' not in source


def test_finite_codes_never_forward_raw_exception_values():
    for error in (ValueError('credential'), m.Refused('credential'), m.Refused(['credential']),
                  m.Refused('catalog', 'credential')):
        assert m.finite(error) == 'unknown'
    assert m.finite(m.Refused('catalog')) == 'catalog'


@pytest.mark.parametrize('error,expected', [
    (m.source_guard.Refused('path_open'), 'source_guard_path_open'),
    (m.source_guard.Refused('metadata_changed'), 'source_guard_metadata_changed'),
    (m.source_guard.Refused('secret-value'), 'source_guard_refused'),
    (m.original_decoder.Refused('row_census'), 'original_decoder_row_census'),
    (m.original_decoder.Refused('member_content'), 'original_decoder_member_content'),
    (m.original_decoder.Refused('secret-value'), 'original_decoder_refused'),
    (m.routes.Refused('original_rows'), 'routes_original_rows'),
    (m.identity.Refused('catalog_row'), 'identity_catalog_row'),
    (m.october.OctoberOrderInputPackageError('october_lineage_inventory'), 'october_lineage_inventory'),
    (m.october.OctoberOrderInputPackageError('secret-value'), 'october_refused'),
    (m.transport.PlainTransportError('source_binding_stream'), 'transport_source_binding_stream'),
    (m.original.compact.AcceptedRiskPreliminaryPackageError('secret-value'), 'compact_reload_refused'),
    (m.identity.figi.PreliminaryQcFigiError('secret-value'), 'binding_validation_refused'),
    (m.identity.evaluator.PreliminaryRatingEvaluationError('secret-value'), 'calendar_validation_refused'),
    (OSError('secret-value'), 'os_error'), (ValueError('secret-value'), 'unknown'),
])
def test_prepare_maps_only_owned_known_finite_failures(environment, monkeypatch, error, expected):
    def fail(deadline):
        raise error
    monkeypatch.setattr(m, '_load_plain', fail)
    refused(expected, environment.run)


def test_failure_mapper_does_not_format_or_inspect_hostile_error():
    class Hostile(ValueError):
        def __str__(self):
            raise AssertionError('formatted raw exception')
        @property
        def args(self):
            raise AssertionError('inspected arbitrary exception descriptor')
    assert m._failure_code(Hostile()) == 'unknown'


def guard_fixture():
    guard = m.source_guard.SourceGuard(deadline=time.monotonic() + 60)
    guard._active = True
    paths = tuple(reversed(m.source_guard.CAPTURE.parents)) + (m.source_guard.CAPTURE,) + tuple(
        m.source_guard.CAPTURE / name for name in m.source_guard.LEAVES)
    for i, path in enumerate(paths):
        ancestor = path != m.source_guard.ROOT and m.source_guard.ROOT not in path.parents
        security = None if ancestor else m.source_guard.VINTAGE_XATTR_PINS if path == m.source_guard.CAPTURE else {
            'acl_empty': True, 'xattrs': {}}
        guard._objects.append({'path': path, 'fd': i, 'parent': max(0, i - 1),
            'name': '.' if i == 0 else path.name, 'metadata': tuple(range(10)),
            'leaf': path.parent == m.source_guard.CAPTURE, 'security': security})
    return guard


@pytest.mark.parametrize('field', range(10))
def test_source_endpoint_fingerprint_binds_every_metadata_field(field):
    guard = guard_fixture()
    before = m._guard_fingerprint(guard)
    values = list(guard._objects[-1]['metadata']); values[field] += 1
    guard._objects[-1]['metadata'] = tuple(values)
    assert m._guard_fingerprint(guard) != before


@pytest.mark.parametrize('fault', ['metadata_missing', 'metadata_bool', 'name', 'leaf', 'fd',
    'ancestor_security', 'vintage_security', 'acl', 'xattr_name', 'xattr_hash', 'inventory'])
def test_source_endpoint_rejects_schema_security_and_last_leaf_drift(fault):
    guard = guard_fixture()
    row = guard._objects[-1]
    if fault == 'metadata_missing': row['metadata'] = row['metadata'][:-1]
    elif fault == 'metadata_bool': row['metadata'] = (*row['metadata'][:-1], True)
    elif fault == 'name': row['name'] = 'other'
    elif fault == 'leaf': row['leaf'] = False
    elif fault == 'fd': row['fd'] = -1
    elif fault == 'ancestor_security': guard._objects[0]['security'] = {}
    elif fault == 'vintage_security':
        next(item for item in guard._objects if item['path'] == m.source_guard.CAPTURE)['security'] = ()
    elif fault == 'acl': row['security']['acl_empty'] = False
    elif fault == 'xattr_name': row['security']['xattrs']['secret'] = {'size': 1, 'sha256': 'a' * 64}
    elif fault == 'xattr_hash': row['security']['xattrs']['com.apple.provenance'] = {'size': 1, 'sha256': 'secret'}
    else: guard._objects.pop()
    refused('source_guard', lambda: m._guard_fingerprint(guard))


def test_invalid_metadata_is_rejected_before_package_loader(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('invalid metadata triggered private input load')
    monkeypatch.setattr(m, '_load_plain', deny)
    refused('metadata_bound', lambda: m.prepare(b'', b'x', deadline=time.monotonic() + 60))
