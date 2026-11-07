"""Synthetic A4 input gates; operational constructor deliberately unreachable."""
import ast
import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import arv2_r347_legacy_six_qc as m


@pytest.fixture
def uploads(monkeypatch):
    values = []
    prefix = m.ACTUAL_ACTIVATION['object_store_key'].rsplit('/', 1)[0] + '/'
    for index, (role, name) in enumerate(zip(m.OBJECT_ROLES, m.OBJECT_NAMES, strict=True)):
        raw = ('synthetic-private-fixture-' + str(index)).encode('ascii')
        descriptor = {'schema': 'arv2-newrule-plain-upload-object-v1', 'role': role, 'ordinal': 0,
            'object_store_key': prefix + name, 'relative_path': name, 'byte_count': len(raw),
            'content_sha256': m.sha(raw), 'record_count': 1, 'compression': 'identity',
            'activation_manifest': index == 5}
        values.append((descriptor, raw))
    monkeypatch.setattr(m, 'ACTUAL_ACTIVATION', {key: values[-1][0][key]
        for key in ('object_store_key', 'content_sha256', 'byte_count')})
    return tuple(values)


def metadata(item):
    descriptor, raw = item
    return {'success': True, 'metadata': {'key': descriptor['object_store_key'], 'size': len(raw),
        'md5': hashlib.md5(raw, usedforsecurity=False).hexdigest()}}


def test_six_plain_buffers_have_fixed_role_order_and_activation_last(uploads):
    descriptors = m.input_inventory(uploads)
    assert [row['role'] for row in descriptors] == list(m.OBJECT_ROLES)
    assert [row['activation_manifest'] for row in descriptors] == [False] * 5 + [True]
    assert descriptors[0] is not uploads[0][0]


@pytest.mark.parametrize('change', ['count', 'order', 'rawtype', 'rawhash', 'wrongkey', 'extra',
    'gzip', 'earlyactivation', 'boolsize', 'boolcount', 'wrong_schema'])
def test_input_inventory_does_not_accept_relabelled_or_malformed_data(uploads, change):
    selected = copy.deepcopy(uploads)
    if change == 'count': selected = selected[:-1]
    elif change == 'order': selected = (selected[1], selected[0], *selected[2:])
    elif change == 'rawtype': selected = ((selected[0][0], bytearray(selected[0][1])), *selected[1:])
    else:
        descriptor = selected[0][0]
        if change == 'rawhash': descriptor['content_sha256'] = '0' * 64
        if change == 'wrongkey': descriptor['object_store_key'] = 'unrelated/key.json'
        if change == 'extra': descriptor['authorization'] = True
        if change == 'gzip': descriptor['compression'] = 'gzip'
        if change == 'earlyactivation': descriptor['activation_manifest'] = True
        if change == 'boolsize': descriptor['byte_count'] = True
        if change == 'boolcount': descriptor['record_count'] = True
        if change == 'wrong_schema': descriptor['schema'] = 'other'
    with pytest.raises(m.Refused, match='input_objects'): m.input_inventory(selected)


def test_fresh_properties_are_metadata_only_even_when_md5_matches(uploads):
    for index, item in enumerate(uploads):
        result = m.check_object_metadata(metadata(item), *item, index)
        assert result['remote_payload_sha256_attested'] is False
        assert result['exclusive_resource_lease'] is False
        assert result['local_payload_sha256'] == m.sha(item[1])
        assert result['verification'].endswith('runtime_SHA256_required')
        assert 'synthetic-private-fixture' not in json.dumps(result)


def test_uppercase_metadata_md5_is_compared_case_insensitively(uploads):
    response = metadata(uploads[0]); response['metadata']['md5'] = response['metadata']['md5'].upper()
    m.check_object_metadata(response, *uploads[0], 0)


@pytest.mark.parametrize('change', ['missing', 'refused', 'wrongkey', 'wrongsize', 'boolsize', 'wrongmd5', 'badmd5'])
def test_metadata_mismatch_refuses_without_any_get_or_overwrite(uploads, change):
    response = metadata(uploads[0])
    if change == 'missing': response.pop('metadata')
    elif change == 'refused': response['success'] = False
    elif change == 'wrongkey': response['metadata']['key'] = 'unrelated'
    elif change == 'wrongsize': response['metadata']['size'] += 1
    elif change == 'boolsize': response['metadata']['size'] = True
    elif change == 'wrongmd5': response['metadata']['md5'] = '0' * 32
    else: response['metadata']['md5'] = 'not-a-digest'
    with pytest.raises(m.Refused): m.check_object_metadata(response, *uploads[0], 0)


def candidate():
    root = Path(__file__).resolve().parents[2]
    raw = (root / 'research/analyst_revisions_v2_qc/newrule_plain_input_runtime.py').read_bytes()
    runtime = (ast.unparse(ast.parse(raw)) + '\n').encode('ascii')
    assert m.pin(runtime) == m.PLAIN_LOADER_PIN
    profile = {'candidate_id': m.CANDIDATE, 'research_epoch_id': m.previous.EPOCH,
               'source_package_sha256': m.previous.PACKAGE_SHA256}
    sources = {f'module_{index:02d}.py': '# synthetic\n' for index in range(15)}
    sources['accepted_risk_order_level_input_runtime.py'] = runtime.decode('ascii')
    sources['legacy_six_october_reporting.py'] = '# reporting fixture\n'
    sources['main.py'] = 'Driver(None, ' + ', '.join(name + '=' + repr(m.ACTUAL_ACTIVATION[field])
        for name, field in (('activation_manifest_key', 'object_store_key'),
            ('activation_manifest_sha256', 'content_sha256'), ('activation_manifest_byte_count', 'byte_count'))) + ')\n'
    pairs = [[name, value] for name, value in sorted(sources.items())]
    return {'candidate_id': m.CANDIDATE, 'ar_percent': 100, 'profile': profile,
        'profile_pin': m.pin(m.canonical(profile)), 'original_profile_sha256': 'b' * 64,
        'sources': [{'project_path': name, **m.pin(value.encode('ascii'))} for name, value in pairs],
        'source_pairs': pairs}


def test_exact_plain_loader_and_activation_bind_runtime_sha_gate():
    value, sources = m._plain_source(candidate())
    assert value['candidate_id'] == m.CANDIDATE
    assert m.pin(sources['accepted_risk_order_level_input_runtime.py'].encode('ascii')) == m.PLAIN_LOADER_PIN
    assert 'hashlib.sha256(payload).hexdigest() != expected_sha256' in sources[
        'accepted_risk_order_level_input_runtime.py']


@pytest.mark.parametrize('change', ['runtime', 'activation_key', 'activation_sha', 'activation_size'])
def test_source_cannot_bypass_cloud_plain_input_identity(change):
    value = candidate()
    for pair in value['source_pairs']:
        if change == 'runtime' and pair[0] == 'accepted_risk_order_level_input_runtime.py': pair[1] += '# edit\n'
        if pair[0] == 'main.py':
            if change == 'activation_key': pair[1] = pair[1].replace(m.ACTUAL_ACTIVATION['object_store_key'], 'other/key.json')
            if change == 'activation_sha': pair[1] = pair[1].replace(m.ACTUAL_ACTIVATION['content_sha256'], '0' * 64)
            if change == 'activation_size': pair[1] = pair[1].replace(str(m.ACTUAL_ACTIVATION['byte_count']), '5902')
    value['sources'] = [{'project_path': name, **m.pin(raw.encode('ascii'))} for name, raw in value['source_pairs']]
    with pytest.raises(m.Refused, match='source'): m._plain_source(value)


def test_unselected_reconciliation_never_inherits_old_attempt_authority():
    called = []
    with pytest.raises(m.Refused, match='reconciliation'):
        m.LegacySixQc(request=lambda *args: called.append(args))
    assert called == []
    assert m.RECONCILIATION_PIN is None and m.CONTEXT_MODE == 'unselected'
    assert m.profile_record()['attempt'] == 4
    assert m.profile_record()['attempt_budget_reset'] is False
