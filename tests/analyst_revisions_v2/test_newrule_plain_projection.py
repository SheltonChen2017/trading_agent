"""Public source and synthetic data only; native denial is required externally."""
import ast
import copy
import dataclasses
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from research.analyst_revisions_v2_qc import newrule_plain_projection as m
from research.analyst_revisions_v2_qc import newrule_plain_input_runtime as loader


ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
SOURCE = ROOT / 'research/analyst_revisions_v2_qc'


def mint_synthetic(value, payloads):
    """Test-only mint: no private source authentication or actual admission."""
    value = copy.deepcopy(value)
    proof = value['parent_proof']
    proof_sha = m.sha(m.canonical(proof))
    value['parent_proof_sha256'] = proof_sha
    prefix = m.transport.KEY_PREFIX + '/' + proof_sha[:24] + '/'
    for item in value['objects']:
        item['object_store_key'] = prefix + item['relative_path']
    value.update(package_id=None, package_sha256=None)
    package_sha = m.sha(m.canonical(value))
    value.update(package_id='arv2-newrule-plain-package-' + package_sha[:24], package_sha256=package_sha)
    raw = m.canonical(value) + b'\n'
    objects = tuple(m.transport.PlainUploadObject(**item, payload=payloads[item['relative_path']])
        for item in value['objects'])
    activation = m.transport.PlainUploadObject(m.transport.OBJECT_SCHEMA, 'activation_manifest', 0,
        prefix + 'transport-manifest.json', 'transport-manifest.json', len(raw), m.sha(raw), 1, 'identity', True, raw)
    objects += (activation,)
    capability = m.transport.PlainTransport(value['package_id'], package_sha,
        proof['source_package_sha256'], proof['source_lineage_sha256'], proof_sha,
        raw, objects, sum(item.byte_count for item in objects))
    return m.transport._mint(capability)


@pytest.fixture(scope='module')
def public_parent():
    # This frozen function reads selected PUBLIC Python sources, never artifacts.
    return m.parent.reconstruct_projection()


@pytest.fixture
def case(public_parent):
    sources = {name: (SOURCE / name).read_bytes() for name in m.SOURCE_NAMES}
    expected = {name: m.sha(sources[name]) for name in m.NEW_SOURCE_NAMES}
    payloads, descriptors = {}, []
    for role in m.transport.ROLES:
        name = 'evaluator-manifest.json' if role == 'evaluator_manifest' else role + '-0000.jsonl'
        raw = m.canonical({'synthetic_role': role}) + b'\n'
        payloads[name] = raw
        descriptors.append({'schema': m.transport.OBJECT_SCHEMA, 'role': role, 'ordinal': 0,
            'object_store_key': 'pending/' + name, 'relative_path': name,
            'byte_count': len(raw), 'content_sha256': m.sha(raw), 'record_count': 1,
            'compression': 'identity', 'activation_manifest': False})
    proof = {'schema': m.transport.PROOF_SCHEMA, 'source_package_sha256': m.parent.PACKAGE,
        'source_lineage_sha256': m.parent.LINEAGE, 'source_activation_sha256': m.parent.ACTIVATION[1],
        'source_activation_byte_count': m.parent.ACTIVATION[2], 'source_inventory_sha256': 'd' * 64,
        'streams': [{name: row[name] for name in ('role', 'ordinal', 'record_count', 'byte_count', 'content_sha256')}
            for row in descriptors]}
    record = {'schema': m.transport.SCHEMA, 'package_id': None, 'package_sha256': None,
        'evaluator_manifest_id': 'synthetic', 'evaluator_manifest_sha256': 'e' * 64,
        'benchmark': {'security_id': loader.BENCHMARK_SECURITY_ID, 'ticker': 'SPY',
            'binding': 'QC_US_equity_symbol_resolved_in_process'},
        'source_disposition_sha256': m.parent.LINEAGE, 'runtime_symbol_binding_count': 1,
        'runtime_symbol_bindings_sha256': descriptors[-1]['content_sha256'],
        'contribution_census': {'accepted': 1}, 'objects': descriptors,
        'runtime': dict(loader._EXPECTED_RUNTIME), 'claims': dict(loader._EXPECTED_CLAIMS),
        'parent_proof': proof, 'parent_proof_sha256': 'f' * 64}
    return NS(parent=public_parent, sources=sources, expected=expected,
        record=record, payloads=payloads, plain=mint_synthetic(record, payloads))


def build(case):
    return m.build_plain_projection(case.parent, case.plain, sources=case.sources,
        expected_new_source_pins=case.expected)


def test_exact_public_parent_and_plain_bridge_keep_nine_modules_and_economics(case):
    value = build(case)
    record = value.to_record()
    old_profile = json.loads(case.parent.profile_bytes)
    profile = json.loads(value.profile_bytes)
    assert m._economic_profile(old_profile) == m._economic_profile(profile)
    assert profile['package_sha256'] == case.plain.package_sha256 != m.parent.PACKAGE
    assert profile['lineage_sha256'] == m.parent.LINEAGE
    assert profile['source_pins'] == {**m.parent.SOURCE_PINS, **case.expected}
    old = {entry.project_path: entry.source_bytes for entry in case.parent.source_files}
    new = {entry.project_path: entry.source_bytes for entry in value.source_files}
    changed = {name for name in old if old[name] != new[name]}
    assert changed == {'main.py', m.INPUT_NAME}
    assert len(record['bridge']['unchanged_cloud_files']) == 9
    assert new[m.INPUT_NAME] == m.frozen.normalize(case.sources[m.LOADER_NAME], m.INPUT_NAME)
    assert record['bridge']['source_mapping'] == {m.INPUT_NAME: m.LOADER_NAME}
    assert m._main_shape(old['main.py']) == m._main_shape(new['main.py'])
    assert record['activation_manifest_sha256'] == case.plain.activation_manifest_sha256
    assert record['upload_inventory_sha256'] == m.sha(m.canonical(record['upload_inventory']))
    assert record['bridge_sha256'] == m.sha(m.canonical(record['bridge']))
    assert m.require_plain_projection(value, value.projection_sha256) == record
    assert all(record[key] is False and record['bridge'][key] is False for key in m.FALSE_FLAGS)
    assert record['bridge']['historical_d15_admission_sha256'] == m.parent.ADMISSION
    assert record['candidate_id'] == 'R298'
    assert record['economic_candidate_id'] == old_profile['candidate_id']


def test_main_literal_values_match_exact_plain_activation_and_profile(case):
    value = build(case)
    main = next(item.source_bytes for item in value.source_files if item.project_path == 'main.py')
    tree = ast.parse(main)
    call, = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id == 'NewruleComparisonDriver']
    values = {kw.arg: ast.literal_eval(kw.value) for kw in call.keywords if kw.arg in m.MAIN_KEYWORDS}
    assert values == {'profile': json.loads(value.profile_bytes),
        'activation_manifest_key': case.plain.activation_manifest_key,
        'activation_manifest_sha256': case.plain.activation_manifest_sha256,
        'activation_manifest_byte_count': case.plain.activation_manifest_byte_count}


@pytest.mark.parametrize('name', m.NEW_SOURCE_NAMES)
def test_explicit_pin_required_and_changed_source_never_auto_refreshes(case, name):
    case.sources[name] += b'\n# changed\n'
    with pytest.raises(m.PlainProjectionError, match='source_pin'): build(case)


@pytest.mark.parametrize('name', m.NEW_SOURCE_NAMES)
def test_every_new_source_pin_required(case, name):
    del case.expected[name]
    with pytest.raises(m.PlainProjectionError, match='source_inventory'): build(case)


@pytest.mark.parametrize('name', sorted(m.SOURCE_NAMES))
def test_every_supplied_public_source_required(case, name):
    del case.sources[name]
    with pytest.raises(m.PlainProjectionError, match='source_inventory'): build(case)


@pytest.mark.parametrize('bad', [None, True, '', 'a' * 63, 'A' * 64, 'a' * 65])
def test_bad_pin_type_and_shape_refuse(case, bad):
    case.expected[m.LOADER_NAME] = bad
    with pytest.raises(m.PlainProjectionError): build(case)


def test_frozen_template_cannot_be_replaced_with_new_pin(case):
    case.sources[m.TEMPLATE_NAME] += b'\n# changed\n'
    with pytest.raises(m.PlainProjectionError, match='source_pin'): build(case)


@pytest.mark.parametrize('forbidden', ['import gzip\n', 'from gzip import GzipFile\n',
    'import zlib\n', 'import base64\n', 'import marshal\n', 'import pickle\n',
    'import io\n', 'exec("pass")\n', 'eval("1")\n', 'compile("pass", "x", "exec")\n',
    '__import__("gzip")\n'])
def test_plain_loader_cannot_restore_encoding_or_dynamic_execution_even_with_new_pin(case, forbidden):
    case.sources[m.LOADER_NAME] += forbidden.encode('ascii')
    case.expected[m.LOADER_NAME] = m.sha(case.sources[m.LOADER_NAME])
    with pytest.raises(m.PlainProjectionError, match='plain_loader'): build(case)


@pytest.mark.parametrize('field,value', [
    ('source_package_sha256', '1' * 64), ('source_lineage_sha256', '2' * 64),
    ('source_activation_sha256', '3' * 64), ('source_activation_byte_count', 1),
    ('source_activation_byte_count', True), ('schema', 'wrong')])
def test_parent_bridge_must_bind_old_actual_input_not_self_supplied_claim(case, field, value):
    case.record['parent_proof'][field] = value
    case.plain = mint_synthetic(case.record, case.payloads)
    with pytest.raises(m.PlainProjectionError): build(case)


@pytest.mark.parametrize('field,value', [('schema', 'wrong'), ('source_disposition_sha256', '4' * 64)])
def test_new_transport_identity_checked_even_with_registered_fixture(case, field, value):
    case.record[field] = value
    case.plain = mint_synthetic(case.record, case.payloads)
    with pytest.raises(m.PlainProjectionError, match='transport_identity'): build(case)


def test_genuine_plain_capability_required_not_frozen_dataclass_copy(case):
    case.plain = dataclasses.replace(case.plain)
    with pytest.raises(m.transport.PlainTransportError, match='authority'): build(case)


def test_projection_cannot_be_copied_or_reconstructed_from_json(case):
    value = build(case)
    with pytest.raises(m.PlainProjectionError, match='projection_authority'):
        m.require_plain_projection(dataclasses.replace(value))
    with pytest.raises(m.PlainProjectionError, match='projection_type'):
        m.require_plain_projection(value.to_record())
    with pytest.raises(dataclasses.FrozenInstanceError): value.projection_sha256 = 'a' * 64


@pytest.mark.parametrize('field', ['record_bytes', 'profile_bytes', 'projection_sha256', 'source_files', '_transport'])
def test_hostile_object_setattr_mutation_refuses(case, field):
    value = build(case)
    old = getattr(value, field)
    changed = b'{}' if field.endswith('_bytes') else '0' * 64 if field.endswith('sha256') else () if field == 'source_files' else None
    object.__setattr__(value, field, changed)
    try:
        with pytest.raises(m.PlainProjectionError): m.require_plain_projection(value)
    finally:
        object.__setattr__(value, field, old)
    m.require_plain_projection(value)


def test_wrong_external_projection_pin_refuses(case):
    value = build(case)
    with pytest.raises(m.PlainProjectionError, match='projection_pin'):
        m.require_plain_projection(value, 'f' * 64)


@pytest.mark.parametrize('field', ['source_bytes', 'project_path', 'projection_sha256'])
def test_equal_content_mutable_or_subclass_capability_fields_refuse(case, field):
    class Text(str):
        pass
    value = build(case)
    target = value if field == 'projection_sha256' else value.source_files[0]
    old = getattr(target, field)
    changed = bytearray(old) if field == 'source_bytes' else Text(old)
    assert changed == old
    object.__setattr__(target, field, changed)
    try:
        with pytest.raises(m.PlainProjectionError, match='projection_type'):
            m.require_plain_projection(value)
    finally:
        object.__setattr__(target, field, old)


def test_mutated_underlying_transport_revokes_projection(case):
    value = build(case)
    old = case.plain.record_bytes
    object.__setattr__(case.plain, 'record_bytes', b'{}\n')
    try:
        with pytest.raises(m.transport.PlainTransportError): m.require_plain_projection(value)
    finally:
        object.__setattr__(case.plain, 'record_bytes', old)


@pytest.mark.parametrize('field,value', [('fee_bps', '11'), ('slippage_model_bps', '1'),
    ('clock', 'later'), ('universe_count', 8), ('ar_percent', 100), ('whole_shares', False),
    ('formal_forward_ready', True), ('terminal', 'different')])
def test_new_profile_cannot_change_economics_or_false_gates(case, monkeypatch, field, value):
    original = m.frozen.runtime.make_profile
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if kwargs['package_sha256'] != m.parent.PACKAGE:
            result[field] = value
        return result
    monkeypatch.setattr(m.frozen.runtime, 'make_profile', changed)
    with pytest.raises(m.PlainProjectionError, match='economic_profile_changed'): build(case)


def test_main_shape_only_masks_four_literal_bindings():
    prefix = 'x = NewruleComparisonDriver(profile={}, activation_manifest_key="x", activation_manifest_sha256="a", activation_manifest_byte_count=1)\n'
    same = prefix.replace('"x"', '"y"').replace('={}', '={"fee": "10"}')
    assert m._main_shape(prefix.encode()) == m._main_shape(same.encode())
    assert m._main_shape(prefix.encode()) != m._main_shape((prefix + 'orders = 1\n').encode())
    with pytest.raises(m.PlainProjectionError): m._main_shape(b'x = 1\n')
    with pytest.raises(m.PlainProjectionError): m._main_shape(prefix.replace('profile={}', 'profile=get_profile()').encode())


def test_frozen_parent_projection_must_remain_exact(case):
    modified = dataclasses.replace(case.parent, projection_sha256='0' * 64)
    with pytest.raises(m.parent.EvidenceRefused):
        m.build_plain_projection(modified, case.plain, sources=case.sources,
            expected_new_source_pins=case.expected)
