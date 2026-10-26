"""Synthetic plain-data fixtures; native network/artifact/Keychain denial required."""
import ast
import copy
import dataclasses
import gzip
import hashlib
import inspect
import json
import sys
from types import SimpleNamespace as NS

import pytest

from research.analyst_revisions_v2_qc import newrule_plain_input_runtime as m
from research.analyst_revisions_v2_qc import accepted_risk_order_level_input_runtime as old


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def repin(value):
    parent = value['parent_proof']
    parent_sha = sha(m._canonical(parent))
    value['parent_proof_sha256'] = parent_sha
    prefix = 'arv2/newrule-plain-v1/' + parent_sha[:24] + '/'
    for item in value['objects']:
        item['object_store_key'] = prefix + item['relative_path']
    value['package_id'] = None
    value['package_sha256'] = None
    digest = sha(m._canonical(value))
    value['package_id'] = 'arv2-newrule-plain-package-' + digest[:24]
    value['package_sha256'] = digest
    return prefix + 'transport-manifest.json'


class Store:
    def __init__(self, values):
        self.values, self.events = values, []

    def contains_key(self, key):
        self.events.append(('contains', key))
        return key in self.values

    def read_bytes(self, key):
        self.events.append(('read', key))
        return self.values[key]


@pytest.fixture
def fixture(monkeypatch):
    roles = {
        'evaluator_manifest': {'manifest_id': 'synthetic-manifest', 'manifest_sha256': 'c' * 64},
        'session_axis': {'session': '2026-10-12'},
        'memberships': {'security_id': 'synthetic-A'},
        'contributions': {'revision': '1.25'},
        'runtime_symbol_bindings': {'security_id': 'synthetic-A', 'composite_figi': 'synthetic-figi'},
    }
    payloads, descriptors = {}, []
    for role, value in roles.items():
        name = 'evaluator-manifest.json' if role == 'evaluator_manifest' else role + '-0000.jsonl'
        raw = m._canonical(value) + b'\n'
        payloads[name] = raw
        descriptors.append({'schema': m.UPLOAD_OBJECT_SCHEMA, 'role': role, 'ordinal': 0,
            'object_store_key': 'pending/' + name, 'relative_path': name, 'byte_count': len(raw),
            'content_sha256': sha(raw), 'record_count': 1, 'compression': 'identity', 'activation_manifest': False})
    parent = {'schema': m.PARENT_PROOF_SCHEMA, 'source_package_sha256': 'a' * 64,
        'source_lineage_sha256': 'b' * 64, 'source_activation_sha256': 'd' * 64,
        'source_activation_byte_count': 1234, 'source_inventory_sha256': 'e' * 64,
        'streams': [{key: row[key] for key in m._STREAM_FIELDS} for row in descriptors]}
    value = {'schema': m.TRANSPORT_MANIFEST_SCHEMA, 'package_id': None, 'package_sha256': None,
        'evaluator_manifest_id': 'synthetic-manifest', 'evaluator_manifest_sha256': 'c' * 64,
        'benchmark': {'security_id': m.BENCHMARK_SECURITY_ID, 'ticker': m.BENCHMARK_TICKER,
            'binding': 'QC_US_equity_symbol_resolved_in_process'},
        'source_disposition_sha256': 'b' * 64, 'runtime_symbol_binding_count': 1,
        'runtime_symbol_bindings_sha256': m._stream_hash((roles['runtime_symbol_bindings'],)),
        'contribution_census': {'accepted': 1}, 'objects': descriptors,
        'runtime': dict(m._EXPECTED_RUNTIME), 'claims': dict(m._EXPECTED_CLAIMS),
        'parent_proof': parent, 'parent_proof_sha256': 'f' * 64}
    repin(value)
    calls, loaded = [], NS(marker='authenticated evaluator input')
    def evaluator(*args):
        calls.append(copy.deepcopy(args))
        return loaded
    monkeypatch.setattr(m.evaluator, 'load_preliminary_rating_input', evaluator)
    return NS(value=value, payloads=payloads, roles=roles, calls=calls, loaded=loaded)


def materialize(fixture, *, value=None, payload=None, key=None):
    value = fixture.value if value is None else value
    key = key or 'arv2/newrule-plain-v1/' + value['parent_proof_sha256'][:24] + '/transport-manifest.json'
    payload = m._canonical(value) + b'\n' if payload is None else payload
    values = {item['object_store_key']: fixture.payloads[item['relative_path']] for item in value['objects']}
    values[key] = payload
    return Store(values), {'activation_manifest_key': key,
        'activation_manifest_sha256': sha(payload), 'activation_manifest_byte_count': len(payload)}


def load(fixture):
    store, kwargs = materialize(fixture)
    return m.load_accepted_risk_preliminary_package(NS(object_store=store), **kwargs), store


def test_plain_loader_authenticates_every_object_and_returns_new_identity(fixture):
    value, store = load(fixture)
    assert value.package_sha256 == fixture.value['package_sha256']
    assert value.package_sha256 != fixture.value['parent_proof']['source_package_sha256']
    assert value.package_id.startswith('arv2-newrule-plain-package-')
    assert value.activation_manifest_sha256 == sha(m._canonical(fixture.value) + b'\n')
    assert value.evaluator_input is fixture.loaded
    assert value.runtime_symbol_bindings == (fixture.roles['runtime_symbol_bindings'],)
    assert fixture.calls == [(fixture.roles['evaluator_manifest'], (fixture.roles['session_axis'],),
        (fixture.roles['memberships'],), (fixture.roles['contributions'],))]
    expected = [store.events[0][1]] + [item['object_store_key'] for item in fixture.value['objects']]
    assert store.events == [event for key in expected for event in [('contains', key), ('read', key)]]
    with pytest.raises(dataclasses.FrozenInstanceError): value.package_id = 'changed'


def test_contract_preserves_claims_bounds_and_has_no_compressed_or_dynamic_source():
    assert m._EXPECTED_CLAIMS == old._EXPECTED_CLAIMS
    assert m._EXPECTED_RUNTIME == old._EXPECTED_RUNTIME
    assert m.MAX_UPLOAD_OBJECT_BYTES == old.MAX_UPLOAD_OBJECT_BYTES == 32 * 1024 * 1024
    assert m.MAX_TOTAL_UPLOAD_BYTES == old.MAX_TOTAL_UPLOAD_BYTES == 44 * 1024 * 1024
    assert m.MAX_TRANSPORT_OBJECT_COUNT == old.MAX_TRANSPORT_OBJECT_COUNT == 95
    assert m.MAX_PLAIN_SHARD_BYTES == 16 * 1024 * 1024
    assert tuple(field.name for field in dataclasses.fields(m.LoadedAcceptedRiskPreliminaryPackage)) == tuple(
        field.name for field in dataclasses.fields(old.LoadedAcceptedRiskPreliminaryPackage))
    source = inspect.getsource(m)
    tree = ast.parse(source)
    imports = {alias.name.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert not imports & {'gzip', 'io', 'base64', 'zlib', 'marshal', 'pickle', 'os', 'socket', 'requests', 'subprocess'}
    calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not calls & {'eval', 'exec', 'compile', '__import__', 'open', 'getattr'}
    assert 'assistant.dispatch_fence' not in sys.modules
    compile(source, 'synthetic-plain-loader.py', 'exec')


@pytest.mark.parametrize('value', [None, [], {}, {'schema': 'wrong'}])
def test_transport_schema_refuses(value):
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError): m._validate_transport(value, 'x', 1)


@pytest.mark.parametrize('field', sorted(m._TRANSPORT_FIELDS))
def test_every_transport_field_required(fixture, field):
    fixture.value.pop(field)
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError):
        m._validate_transport(fixture.value, 'x', 1)


@pytest.mark.parametrize('field', sorted(m._OBJECT_FIELDS))
def test_every_descriptor_field_required(fixture, field):
    fixture.value['objects'][1].pop(field)
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError):
        m._validate_transport(fixture.value, 'x', 1)


@pytest.mark.parametrize('field', sorted(m._PARENT_FIELDS))
def test_every_parent_field_required(fixture, field):
    fixture.value['parent_proof'].pop(field)
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError):
        m._validate_transport(fixture.value, 'x', 1)


@pytest.mark.parametrize('field,bad', [
    ('schema', old.UPLOAD_OBJECT_SCHEMA), ('role', 'unknown'), ('role', None), ('ordinal', True),
    ('ordinal', -1), ('byte_count', True), ('byte_count', 0), ('byte_count', m.MAX_PLAIN_SHARD_BYTES + 1),
    ('record_count', True), ('record_count', 0), ('relative_path', 'session_axis-0001.jsonl'),
    ('object_store_key', 'x/../escape.jsonl'), ('compression', 'gzip'), ('compression', None),
    ('activation_manifest', True), ('activation_manifest', 0), ('content_sha256', 'A' * 64),
])
def test_descriptor_corruption_refuses(fixture, field, bad):
    row = dict(fixture.value['objects'][1])
    row[field] = bad
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError): m._descriptor(row)


@pytest.mark.parametrize('field,bad', [('ordinal', 1), ('record_count', 2), ('relative_path', 'manifest.json'),
    ('byte_count', m.MAX_UPLOAD_OBJECT_BYTES + 1)])
def test_evaluator_descriptor_requires_single_exact_manifest(fixture, field, bad):
    row = dict(fixture.value['objects'][0]); row[field] = bad
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError): m._descriptor(row)


@pytest.mark.parametrize('field,bad', [
    ('source_package_sha256', None), ('source_lineage_sha256', 'f' * 64),
    ('source_activation_sha256', 'A' * 64), ('source_activation_byte_count', True),
    ('source_activation_byte_count', 0), ('source_activation_byte_count', m.MAX_UPLOAD_OBJECT_BYTES + 1),
    ('source_inventory_sha256', 'bad'), ('streams', []), ('schema', 'wrong'),
])
def test_parent_corruption_refuses_even_with_repin(fixture, field, bad):
    fixture.value['parent_proof'][field] = bad
    repin(fixture.value)
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError): load(fixture)


@pytest.mark.parametrize('field', sorted(m._STREAM_FIELDS))
def test_parent_stream_must_match_exact_descriptor(fixture, field):
    fixture.value['parent_proof']['streams'][1][field] = None
    repin(fixture.value)
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError): load(fixture)


@pytest.mark.parametrize('field,bad', [('package_id', 'old-package'), ('package_sha256', 'a' * 64),
    ('parent_proof_sha256', 'f' * 64), ('runtime_symbol_binding_count', True),
    ('runtime_symbol_binding_count', 0), ('runtime_symbol_binding_count', 100001),
    ('evaluator_manifest_id', '../bad'), ('benchmark', {}), ('contribution_census', {'accepted': True}),
    ('runtime', {}), ('claims', {}), ('objects', [])])
def test_top_level_corruption_refuses(fixture, field, bad):
    fixture.value[field] = bad
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError):
        m._validate_transport(fixture.value, 'x', 1)


@pytest.mark.parametrize('flag', sorted(m._EXPECTED_CLAIMS))
def test_claim_booleans_are_exact_and_do_not_accept_integers(fixture, flag):
    fixture.value['claims'][flag] = int(fixture.value['claims'][flag])
    repin(fixture.value)
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError, match='claims'): load(fixture)


def test_missing_role_duplicate_key_and_wrong_ordinal_refuse(fixture):
    for mutate in (lambda v: v['objects'].pop(),
            lambda v: v['objects'].append(dict(v['objects'][1])),
            lambda v: v['objects'][1].update(ordinal=2, relative_path='session_axis-0002.jsonl')):
        value = copy.deepcopy(fixture.value); mutate(value)
        with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError): m._validate_transport(value, 'x', 1)


def test_exact_prefix_and_activation_filename_required(fixture):
    store, kwargs = materialize(fixture, key='synthetic/transport-manifest.json')
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError, match='prefix'):
        m.load_accepted_risk_preliminary_package(NS(object_store=store), **kwargs)


def test_aggregate_bound_includes_activation(fixture, monkeypatch):
    store, kwargs = materialize(fixture)
    total = sum(row['byte_count'] for row in fixture.value['objects']) + kwargs['activation_manifest_byte_count']
    monkeypatch.setattr(m, 'MAX_TOTAL_UPLOAD_BYTES', total)
    m.load_accepted_risk_preliminary_package(NS(object_store=store), **kwargs)
    monkeypatch.setattr(m, 'MAX_TOTAL_UPLOAD_BYTES', total - 1)
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError, match='total byte budget'):
        m.load_accepted_risk_preliminary_package(NS(object_store=store), **kwargs)


@pytest.mark.parametrize('raw,count', [(b'', 1), (b'{}', 1), (b'{}\n', 2), (b'{}\r\n', 1),
    (b'{ "a":1}\n', 1), (b'{"a":1,"a":2}\n', 1), (b'[]\n', 1), (b'null\n', 1),
    (b'{"a":NaN}\n', 1), (b'{"a":Infinity}\n', 1), (b'{}\n\n', 1), (b'{"a":"\xff"}\n', 1),
    (b'{}\n', True), (gzip.compress(b'{}\n'), 1)])
def test_rows_are_genuinely_plain_strict_canonical_objects(raw, count):
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError): m._plain_rows(raw, count, 'session_axis')


def test_plain_rows_exact_shard_boundary(monkeypatch):
    raw = b'{"a":1}\n'
    monkeypatch.setattr(m, 'MAX_PLAIN_SHARD_BYTES', len(raw))
    assert m._plain_rows(raw, 1, 'session_axis') == ({'a': 1},)
    monkeypatch.setattr(m, 'MAX_PLAIN_SHARD_BYTES', len(raw) - 1)
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError): m._plain_rows(raw, 1, 'session_axis')


@pytest.mark.parametrize('failure', ['missing', 'hash', 'count', 'contains_shape', 'contains_raises', 'read_raises'])
def test_object_identity_and_access_fail_closed(fixture, failure):
    store, kwargs = materialize(fixture)
    first = fixture.value['objects'][0]['object_store_key']
    if failure == 'missing': del store.values[first]
    elif failure == 'hash': store.values[first] = b'X' * len(store.values[first])
    elif failure == 'count': store.values[first] += b'\n'
    elif failure == 'contains_shape': store.contains_key = lambda _key: 1
    elif failure == 'contains_raises': store.contains_key = lambda _key: (_ for _ in ()).throw(ValueError('synthetic'))
    else: store.read_bytes = lambda _key: (_ for _ in ()).throw(ValueError('synthetic'))
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError):
        m.load_accepted_risk_preliminary_package(NS(object_store=store), **kwargs)
    assert fixture.calls == []


def test_evaluator_failure_does_not_return_package(fixture, monkeypatch):
    monkeypatch.setattr(m.evaluator, 'load_preliminary_rating_input', lambda *_: (_ for _ in ()).throw(ValueError('synthetic')))
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError, match='did not authenticate'): load(fixture)


@pytest.mark.parametrize('field', ['evaluator_manifest_id', 'evaluator_manifest_sha256',
    'runtime_symbol_binding_count', 'runtime_symbol_bindings_sha256'])
def test_authenticated_payload_must_match_transport_semantics(fixture, field):
    fixture.value[field] = ('other-id' if field.endswith('_id') else
        2 if field == 'runtime_symbol_binding_count' else 'f' * 64)
    repin(fixture.value)
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError): load(fixture)


@pytest.mark.parametrize('raw', [b'{}\n\n', b' {"x":1}\n', b'{"x":1,"x":2}\n', b'[]\n'])
def test_activation_malformed_or_noncanonical_refuses(fixture, raw):
    store, kwargs = materialize(fixture, payload=raw)
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError):
        m.load_accepted_risk_preliminary_package(NS(object_store=store), **kwargs)


def test_collection_rows_preserves_frozen_behavior_and_bound(monkeypatch):
    assert m.collection_rows(iter([1, 2]), 'synthetic') == old.collection_rows(iter([1, 2]), 'synthetic') == (1, 2)
    monkeypatch.setattr(m, 'MAX_COLLECTION_ROWS', 2)
    touched = []
    def rows():
        for index in range(10): touched.append(index); yield index
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError, match='row bound'): m.collection_rows(rows(), 'synthetic')
    assert touched == [0, 1, 2]
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError, match='unreadable'): m.collection_rows(None, 'synthetic')


def test_plain_row_contents_match_frozen_loader_data_semantics(fixture):
    for role in m._ROLE_ORDER[1:]:
        raw = fixture.payloads[role + '-0000.jsonl']
        compressed_rows, size = old._gzip_rows(gzip.compress(raw), 1, role)
        assert m._plain_rows(raw, 1, role) == compressed_rows
        assert size == len(raw)


@pytest.mark.parametrize('index', [0, 1, 4])
def test_each_canonical_payload_still_requires_its_external_content_pin(fixture, index):
    fixture.value['objects'][index]['content_sha256'] = 'f' * 64
    fixture.value['parent_proof']['streams'][index]['content_sha256'] = 'f' * 64
    repin(fixture.value)
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError, match='object identity changed'):
        load(fixture)
    assert fixture.calls == []


def test_plain_finite_float_canonical_bytes_stay_compatible():
    raw = b'{"x":1.25}\n'
    assert m._plain_rows(raw, 1, 'session_axis') == old._gzip_rows(gzip.compress(raw), 1, 'session_axis')[0]


@pytest.mark.parametrize('value', [(1,), {1: 'bad'}, b'bytes', object(), float('nan'), float('inf')])
def test_canonical_rejects_non_json_types_and_nonfinite_values(value):
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError): m._canonical(value)


def test_canonical_structure_bounds(monkeypatch):
    monkeypatch.setattr(m, 'MAX_JSON_DEPTH', 2)
    assert m._canonical({'x': [1]}) == b'{"x":[1]}'
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError): m._canonical({'x': [[1]]})
    monkeypatch.setattr(m, 'MAX_JSON_NODES', 2)
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError): m._canonical({'x': [1]})


def test_global_role_order_refuses_even_when_parent_and_manifest_repin(fixture):
    fixture.value['objects'][1:3] = reversed(fixture.value['objects'][1:3])
    fixture.value['parent_proof']['streams'][1:3] = reversed(fixture.value['parent_proof']['streams'][1:3])
    repin(fixture.value)
    with pytest.raises(m.AcceptedRiskOrderLevelInputRuntimeError, match='role group order'): load(fixture)


def test_pure_host_conversion_roundtrips_into_cloud_without_private_input(fixture):
    from research.analyst_revisions_v2_qc import newrule_plain_transport as host
    pairs = []
    for role in m._ROLE_ORDER:
        name = 'evaluator-manifest.json' if role == 'evaluator_manifest' else role + '-0000-jsonl.gz'
        plain = m._canonical(fixture.roles[role]) + b'\n'
        raw = plain if role == 'evaluator_manifest' else gzip.compress(plain, mtime=0)
        item = host.compact.PreliminaryUploadObject(host.compact.UPLOAD_OBJECT_SCHEMA, role, 0,
            'synthetic/source/' + name, name, len(raw), sha(raw), 1,
            'identity' if role == 'evaluator_manifest' else 'gzip', False)
        pairs.append((item, raw))
    record = {key: copy.deepcopy(value) for key, value in fixture.value.items()
        if key not in ('parent_proof', 'parent_proof_sha256')}
    record.update(schema=old.TRANSPORT_MANIFEST_SCHEMA, package_id=None, package_sha256=None,
        objects=[item.to_record() for item, _ in pairs])
    original_hash = sha(old._canonical(record))
    record.update(package_id='arv2-preliminary-qc-package-' + original_hash[:24], package_sha256=original_hash)
    activation = old._canonical(record) + b'\n'
    pairs.append((host.compact.PreliminaryUploadObject(host.compact.UPLOAD_OBJECT_SCHEMA,
        'activation_manifest', 0, 'synthetic/source/transport-manifest.json', 'transport-manifest.json',
        len(activation), sha(activation), 1, 'identity', True), activation))
    package = NS(package_id=record['package_id'], package_sha256=original_hash,
        source_disposition_sha256=record['source_disposition_sha256'],
        upload_objects=tuple(item for item, _ in pairs), total_upload_byte_count=sum(len(raw) for _, raw in pairs))
    # Explicitly use the unminted pure byte seam, never build_plain_transport or private readers.
    converted = host._convert_payloads(package, tuple(pairs))
    with pytest.raises(host.PlainTransportError, match='authority'): host.require_plain_transport(converted)
    store = Store({item.object_store_key: item.payload for item in converted.upload_objects})
    actual = m.load_accepted_risk_preliminary_package(NS(object_store=store),
        activation_manifest_key=converted.activation_manifest_key,
        activation_manifest_sha256=converted.activation_manifest_sha256,
        activation_manifest_byte_count=converted.activation_manifest_byte_count)
    assert actual.package_sha256 == converted.package_sha256 != original_hash
    assert actual.evaluator_input is fixture.loaded
    assert actual.runtime_symbol_bindings == (fixture.roles['runtime_symbol_bindings'],)
    assert fixture.calls == [(fixture.roles['evaluator_manifest'], (fixture.roles['session_axis'],),
        (fixture.roles['memberships'],), (fixture.roles['contributions'],))]
    assert all(item.compression == 'identity' for item in converted.upload_objects)
