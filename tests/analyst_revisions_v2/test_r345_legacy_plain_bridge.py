"""Offline public-code and supplied synthetic DATA tests; no private B read."""
import ast
import copy
import dataclasses
import json
from pathlib import Path
import time

import pytest

from scripts import arv2_r345_legacy_plain_bridge as m
from scripts import arv2_r343_legacy_six_projection as projection


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def no_capability_or_private_iterator(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('private iterator or authority mint reached')
    for name in ('_REQUIRE_SOURCE', '_ITER_SOURCE', '_mint'):
        monkeypatch.setattr(m.transport, name, deny)
    monkeypatch.setattr(m.compact, 'require_accepted_risk_preliminary_package', deny)
    monkeypatch.setattr(m.compact, 'iter_accepted_risk_preliminary_upload_objects', deny)


@pytest.fixture(scope='module')
def data():
    manifest = {'manifest_id': 'synthetic-manifest', 'manifest_sha256': 'c' * 64}
    groups = {'session_axis': [{'session': '2026-10-12'}], 'memberships': [{'security_id': 'synthetic'}],
        'contributions': [{'score': '1.25'}], 'runtime_symbol_bindings': [{'security_id': 'synthetic', 'figi': 'test'}]}
    pairs = []
    for role in m.transport.ROLES:
        raw = m.canonical(manifest) + b'\n' if role == 'evaluator_manifest' else m.compact._gzip_records(groups[role])
        name = 'evaluator-manifest.json' if role == 'evaluator_manifest' else f'{role}-0000-jsonl.gz'
        descriptor = m.compact.PreliminaryUploadObject(m.compact.UPLOAD_OBJECT_SCHEMA, role, 0,
            'arv2/synthetic/' + name, name, len(raw), m.sha(raw), 1,
            'identity' if role == 'evaluator_manifest' else 'gzip', False)
        pairs.append((descriptor, raw))
    seed = m.compact._transport_seed(package_id=None, package_sha256=None, evaluator_manifest=manifest,
        objects=[item for item, _ in pairs], source_disposition_sha256='b' * 64,
        runtime_symbol_binding_count=1,
        runtime_symbol_bindings_sha256=m.compact._stream_hash(groups['runtime_symbol_bindings']),
        contribution_census={'accepted': 1})
    digest = m.sha(m.canonical(seed)); seed.update(package_id='arv2-preliminary-qc-package-' + digest[:24],
                                                 package_sha256=digest)
    raw = m.canonical(seed) + b'\n'
    activation = m.compact.PreliminaryUploadObject(m.compact.UPLOAD_OBJECT_SCHEMA, 'activation_manifest', 0,
        'arv2/synthetic/transport-manifest.json', 'transport-manifest.json', len(raw), m.sha(raw), 1, 'identity', True)
    pairs.append((activation, raw))
    supplied = tuple((descriptor.to_record(), payload) for descriptor, payload in pairs)
    inventory = m.pin(m.canonical([descriptor for descriptor, _ in supplied]))
    plain = m.convert_supplied_inputs(supplied, expected_package_sha256=digest,
        expected_lineage_sha256='b' * 64, expected_inventory_pin=inventory)
    return supplied, digest, inventory, plain


@pytest.fixture(scope='module')
def family(data):
    """Real seven-arm public source with explicitly synthetic ancestry metadata.

    No genuine package wrapper is constructed. The test changes only the public
    fixture's source-origin metadata to join its synthetic DATA, then computes
    the real flat driver's profile. Production must use external actual B pins.
    """
    _, _, _, plain = data
    pairs = tuple((name, (ROOT / 'research/analyst_revisions_v2_qc' / name).read_bytes())
                  for name in projection.source_names())
    logical = 'PUBLIC-SYNTHETIC-QCOM-PLACEHOLDER'
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(projection.matched, 'QCOM_EXCLUSION_SECURITY_ID_SHA256', projection.sha(logical.encode('ascii')))
        historical = projection.reconstruct_historical(pairs, qcom_security_id=logical,
            manifest=projection.HISTORICAL_MANIFEST, deadline=time.monotonic() + 599)
    activation = json.loads(plain.source_activation_json)
    reporting = (ROOT / 'research/analyst_revisions_v2_qc/legacy_six_october_reporting.py').read_bytes()
    cells = []
    for percent, sources, old_profile in historical:
        extended, _ = projection._extend_cell(percent, sources, old_profile,
            activation=activation, reporting_source=reporting)
        buffers = dict(extended)
        tilt = buffers[projection.TILT]
        assert tilt.count(projection.OCTOBER_PACKAGE.encode('ascii')) == 1
        assert tilt.count(projection.OCTOBER_LINEAGE.encode('ascii')) == 1
        buffers[projection.TILT] = tilt.replace(projection.OCTOBER_PACKAGE.encode('ascii'),
            plain.source_package_sha256.encode('ascii')).replace(projection.OCTOBER_LINEAGE.encode('ascii'),
            plain.source_lineage_sha256.encode('ascii'))
        profile, _ = projection._profile({name: raw.decode('ascii') for name, raw in buffers.items()})
        cells.append(m.ParentCell(f'R343-AR{percent:03d}', percent, m.canonical(profile), tuple(sorted(buffers.items()))))
    loader = (ROOT / 'research/analyst_revisions_v2_qc/newrule_plain_input_runtime.py').read_bytes()
    return tuple(cells), loader


def build(family, data, *, cells=None, loader=None):
    parents, selected = family
    parents = parents if cells is None else cells
    selected = selected if loader is None else loader
    return m.build_source_bridge(parents, data[3], expected_parent_vector_pin=m.pin(m.parent_vector(parents)),
        plain_loader_source=selected, expected_plain_loader_pin=m.pin(selected))


def test_conversion_preserves_streams_and_never_mints_authority(data):
    source, digest, inventory, plain = data
    # Convert again inside the test body: the function-scoped denial fixture is
    # now active regardless of when the module-scoped DATA fixture was built.
    reached = m.convert_supplied_inputs(source, expected_package_sha256=digest,
        expected_lineage_sha256='b' * 64, expected_inventory_pin=inventory)
    assert reached == plain
    record, _, activation = m.validate_plain_data(plain)
    assert record['package_sha256'] != digest
    assert activation['content_sha256'] != source[-1][0]['content_sha256']
    assert plain.record_bytes.endswith(b'\n') and not plain.record_bytes.endswith(b'\\n')
    for (old, raw), (new_json, payload) in zip(source[:-1], plain.uploads[:-1], strict=True):
        new = json.loads(new_json)
        assert new['compression'] == 'identity'
        if old['role'] == 'evaluator_manifest': assert payload == raw
        else:
            descriptor = m.compact.PreliminaryUploadObject(**old)
            rows, _ = m.compact._load_canonical_gzip_records(raw, descriptor)
            assert payload == b''.join(m.canonical(row) + b'\n' for row in rows)
    clone = dataclasses.replace(plain)
    m.validate_plain_data(clone)  # Value clones remain DATA, not capabilities.
    with pytest.raises(m.transport.PlainTransportError): m.transport.require_plain_transport(clone)


@pytest.mark.parametrize('fault', ['payload', 'descriptor', 'inventory', 'parent'])
def test_bad_supplied_input_refuses_without_fallback(data, fault):
    source, digest, inventory, _ = data
    selected = copy.deepcopy(source)
    if fault == 'payload': selected = (*selected[:-1], (selected[-1][0], selected[-1][1] + b' '))
    if fault == 'descriptor': selected[0][0]['unknown_field'] = False
    if fault == 'inventory': inventory = {'byte_count': inventory['byte_count'], 'sha256': 'a' * 64}
    if fault == 'parent': digest = 'a' * 64
    with pytest.raises(m.Refused):
        m.convert_supplied_inputs(selected, expected_package_sha256=digest,
            expected_lineage_sha256='b' * 64, expected_inventory_pin=inventory)


def test_actual_plain_runtime_reports_actual_transport_not_ancestral_profile(data, monkeypatch):
    plain = data[3]; record, _, activation = m.validate_plain_data(plain)
    payloads = {json.loads(meta)['object_store_key']: raw for meta, raw in plain.uploads}
    class Store:
        def contains_key(self, key): return key in payloads
        def read_bytes(self, key): return payloads[key]
    class Algorithm:
        object_store = Store()
    marker = object()
    monkeypatch.setattr(m.plain_runtime.evaluator, 'load_preliminary_rating_input', lambda *args: marker)
    loaded = m.plain_runtime.load_accepted_risk_preliminary_package(Algorithm(),
        activation_manifest_key=activation['object_store_key'], activation_manifest_sha256=activation['content_sha256'],
        activation_manifest_byte_count=activation['byte_count'])
    assert loaded.package_sha256 == record['package_sha256'] != plain.source_package_sha256
    assert loaded.activation_manifest_sha256 == activation['content_sha256']
    assert loaded.evaluator_input is marker


def test_all_seven_cells_preserve_sixteen_files_profile_money_and_344_guard(family, data):
    prepared = build(family, data)
    assert len(prepared) == 7
    for parent, result in zip(family[0], prepared, strict=True):
        old, new = dict(parent.sources), dict(result.sources)
        assert result.profile_bytes == parent.profile_bytes
        assert [name for name in old if old[name] != new[name]] == [m.INPUT_NAME, 'main.py']
        assert all(old[name] == new[name] for name in old if name not in (m.INPUT_NAME, 'main.py'))
        assert all(raw.endswith(b'\n') and not raw.endswith(b'\\n') for _, raw in result.sources)
        assert sum(len(raw) for _, raw in result.sources) + 32768 <= 448 * 1024
        a, b = ast.parse(old['main.py']), ast.parse(new['main.py'])
        for tree in (a, b):
            for node in ast.walk(tree):
                if isinstance(node, ast.keyword) and node.arg in m.ACTIVATION_KEYWORDS: node.value = ast.Constant('MASKED')
        assert ast.dump(a, include_attributes=False) == ast.dump(b, include_attributes=False)
        record = json.loads(result.record_bytes)
        assert record['prepared_only'] is True and all(record[key] is False for key in m.FALSE_FLAGS)
        assert record['actual_plain_package_sha256'] != record['ancestral_source_package_sha256']
        assert m.input_surface(result.sources) == tuple(sorted(m.USED_INPUT_EXPORTS))


@pytest.mark.parametrize('value', ['24999', '25001', '25000.0'])
def test_selected_loader_bound_ast_is_load_bearing(family, data, value):
    loader = family[1].replace(b'MAX_COLLECTION_ROWS = 25_000', ('MAX_COLLECTION_ROWS = ' + value).encode('ascii'))
    assert loader != family[1]
    with pytest.raises(m.Refused, match='collection_semantics'): build(family, data, loader=loader)


@pytest.mark.parametrize('mutation', [
    'def _input():\n    pass\n', 'class _input:\n    pass\n',
    'f = _input\n', "x = getattr(_input, 'collection_rows')\n", 'x = _input.collection_rows.__globals__\n',
    'from unknown import *\n', 'import builtins as b\nf = b.__import__\n',
    "import importlib as i\nf = i.import_module\n", "f = __import__\n"])
def test_alias_binding_and_reflection_proof_is_load_bearing(mutation):
    raw = ('import accepted_risk_order_level_input_runtime as _input\n' + mutation +
        '_input.load_accepted_risk_preliminary_package(None)\n_input.collection_rows([], "x")\n').encode('ascii')
    with pytest.raises(m.Refused, match='loader_surface'): m.input_surface((('consumer.py', raw),))


def test_344_guard_cannot_disappear_even_with_reselected_fixture_pin(family, data):
    parents = list(family[0]); cell = parents[0]; sources = dict(cell.sources)
    tree = ast.parse(sources['main.py'])
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and ast.unparse(node.test) == "aggregate['run_valid'] is True": node.test = ast.Constant(True)
    sources['main.py'] = (ast.unparse(tree) + '\n').encode('ascii')
    parents[0] = dataclasses.replace(cell, sources=tuple(sorted(sources.items())))
    with pytest.raises(m.Refused, match='validity_guard'): build(family, data, cells=tuple(parents))


def test_external_parent_pin_is_not_automatically_refreshed(family, data):
    cells, loader = family
    with pytest.raises(m.Refused, match='pin'):
        m.build_source_bridge(cells, data[3], expected_parent_vector_pin={'byte_count': 1, 'sha256': '0' * 64},
            plain_loader_source=loader, expected_plain_loader_pin=m.pin(loader))
