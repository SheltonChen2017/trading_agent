"""Synthetic fresh DATA joins and real held-FD behavior, no production reads."""
import base64
import copy
from dataclasses import FrozenInstanceError
import os
from pathlib import Path
import time

import pytest

from scripts import arv2_r345_legacy_six_submission_data as m


def refused(code, operation):
    with pytest.raises(m.Refused) as caught:
        operation()
    assert caught.value.args == (code,)


@pytest.fixture
def example(monkeypatch):
    # Public source only. Source fixtures obey the actual closed bundle schema;
    # no real security identifiers, price rows or genuine package are loaded.
    reporting = (Path(__file__).resolve().parents[2] / 'research/analyst_revisions_v2_qc/legacy_six_october_reporting.py').read_bytes()
    sources = sorted((name, reporting if name == 'legacy_six_october_reporting.py' else b'pass\n')
        for name in (*m.projection.source_names(), 'main.py', 'legacy_six_october_reporting.py'))
    public, cells, candidates = [], [], []
    for percent, old in zip(m.projection.AR_PERCENTS, m.projection.HISTORICAL_MANIFEST['candidates'], strict=True):
        profile = {'candidate_id': f'R343-AR{percent:03d}', 'research_epoch_id': m.projection.EPOCH}
        row = {'ar_percent': percent, 'candidate_id': profile['candidate_id'],
            'profile_pin': m.pin(m.canonical(profile)),
            'sources': [{'project_path': name, **m.pin(raw)} for name, raw in sources],
            'original_profile_sha256': old['profile_sha256']}
        public.append(row)
        cells.append({**row, 'profile': profile, 'source_pairs': [[name, raw.decode('ascii')] for name, raw in sources]})
        candidates.append({'candidate_id': profile['candidate_id'], 'ar_percent': percent,
            'project_name': f'ARV2 R343 LEGACY SIX AR{percent} 2021 2026 OCT13',
            'backtest_name': f'ARV2 R343 AR{percent} old-rules through 2026-10-13 A1',
            'maximum_launch_attempts': 3, 'launch_attempts_consumed': 0, 'submission_permitted': False})
    activation = {'object_store_key': 'arv2/preliminary-rating/27645603c1a6e0fc9fa81655/transport-manifest.json',
        'content_sha256': m.ACTIVATION['sha256'], 'byte_count': m.ACTIVATION['byte_count']}
    summary = {'schema': m.projection.SCHEMA, 'research_epoch_id': m.projection.EPOCH,
        'cell_count': 7, 'evaluation_start': '2021-01-04', 'evaluation_end': '2026-10-13',
        'evaluation_count': 1451, 'decision_count': 302, 'last_decision': '2026-10-12',
        'package_sha256': m.projection.OCTOBER_PACKAGE, 'lineage_sha256': m.projection.OCTOBER_LINEAGE,
        'activation': activation, 'cells': public, **m.projection.FALSE_FLAGS}
    inputs = m.genuine_input
    input_binding = inputs.expected_input_binding()
    truths = ('genuine_October_package_and_plain_process_authority_authenticated',
        'full_original_binding_stream_authenticated', 'full_original_axis_authenticated',
        'full_membership_stream_authenticated', 'all_source_payloads_reauthenticated',
        'contributions_validated_by_genuine_compact_evaluator', 'normal_return_required_before_use')
    receipt = {'schema': inputs.SCHEMA + '-receipt', 'input_binding': input_binding,
        'input_binding_sha256': m.pin(m.canonical(input_binding))['sha256'],
        'parsed_role_streams_sha256': 'd' * 64, 'role_row_counts': dict(zip(inputs.ROLES, (1, 3466, 2, 3, 6151), strict=True)),
        'parsed_roles': list(inputs.PARSED_ROLES), 'source_package_object_count': 6,
        'plain_upload_object_count': 6, 'plain_payload_byte_count': 7,
        'lineage_byte_count': 7, 'contributions_reparsed_by_this_helper': False,
        **dict.fromkeys(truths, True), **inputs.FALSE_FLAGS,
        'source_guard': {'schema': inputs.SCHEMA + '-source', 'source_leaf_count': 7,
            'source_payload_byte_count': inputs.SOURCE_TOTAL_BYTES + 7, 'current_endpoint_sha256': 'e' * 64,
            'full_current_native_security_checked': True, 'full_current_metadata_checked': True,
            'fixed_leaf_bytes_authenticated': True, 'normal_return_required_before_use': True,
            'historical_continuity_proven': False, 'continuous_integrity_proven': False}}
    uploads, descriptors, payloads = [], [], []
    prefix = 'arv2/preliminary-rating/27645603c1a6e0fc9fa81655/'
    for role in m.compact._UPLOAD_ROLE_ORDER[:-1]:
        name = 'evaluator-manifest.json' if role == 'evaluator_manifest' else role.replace('_', '-') + '-jsonl.gz'
        raw = ('synthetic-opaque-' + role).encode('ascii')
        descriptor = {'schema': m.compact.UPLOAD_OBJECT_SCHEMA, 'role': role, 'ordinal': 0,
            'object_store_key': prefix + name, 'relative_path': name, 'byte_count': len(raw),
            'content_sha256': m.pin(raw)['sha256'], 'record_count': 1,
            'compression': 'identity' if role == 'evaluator_manifest' else 'gzip', 'activation_manifest': False}
        descriptors.append(descriptor)
        payloads.append(raw)
    raw = m.canonical({'schema': m.compact.TRANSPORT_MANIFEST_SCHEMA,
        'package_sha256': m.projection.OCTOBER_PACKAGE, 'source_disposition_sha256': m.projection.OCTOBER_LINEAGE,
        'objects': descriptors}) + b'\n'
    payloads.append(raw)
    descriptors.append({'schema': m.compact.UPLOAD_OBJECT_SCHEMA, 'role': 'activation_manifest', 'ordinal': 0,
        'object_store_key': prefix + 'transport-manifest.json', 'relative_path': 'transport-manifest.json',
        'byte_count': len(raw), 'content_sha256': m.pin(raw)['sha256'], 'record_count': 1,
        'compression': 'identity', 'activation_manifest': True})
    for descriptor, raw in zip(descriptors, payloads, strict=True):
        uploads.append({'descriptor': descriptor, 'payload_base64': base64.b64encode(raw).decode('ascii')})
    # Explicit synthetic opaque-upload seams. Real execution keeps both fixed
    # public production pins, and no source/dependency pin is overwritten.
    monkeypatch.setattr(m, 'ACTIVATION', m.pin(payloads[-1]))
    monkeypatch.setattr(m, 'UPLOAD_TOTAL', sum(map(len, payloads)))
    binding = {'expected_head': 'a' * 40, 'caller_sha256': 'b' * 64, 'profile_sha256': 'c' * 64}
    value = {'schema': m.SCHEMA, 'binding': binding, 'claim_pin': {'byte_count': 500, 'sha256': 'f' * 64},
        'private_transport_nonce': '0' * 64, 'input_receipt': receipt,
        'prepared': {'schema': m.projection.SCHEMA + '-private', 'summary': summary, 'cells': cells, 'activation': activation},
        'upload_objects': uploads, 'submission_candidates': candidates,
        'upload_policy': 'exact_payloads_first_readback_activation_last_no_upload_authority', **dict.fromkeys(m.FLAGS, False)}
    return value, m.canonical(summary), m.canonical(binding)


def validated(example):
    value, summary, binding = example
    return m.validate_submission(value, expected_summary=summary, expected_binding=binding)


def test_real_closed_validators_join_source_profiles_receipt_uploads_and_detach_buffers(example):
    result = validated(example)
    assert len(result.candidates) == 7 and len(result.uploads) == 6
    assert result.candidates[0].candidate_id == 'R343-AR080'
    assert [row.activation_manifest for row in result.uploads] == [False] * 5 + [True]
    original = result.candidates[0].cell_record()
    example[0]['prepared']['cells'][0]['source_pairs'][0][1] = 'changed'
    assert result.candidates[0].cell_record() == original
    original['source_pairs'][0][1] = 'changed-again'
    assert result.candidates[0].cell_record() != original
    with pytest.raises(FrozenInstanceError):
        result.candidates = ()


@pytest.mark.parametrize('key', sorted(m.FLAGS))
def test_no_preparation_flag_can_supply_contact_or_readiness_authority(example, key):
    example[0][key] = True
    refused('binding', lambda: validated(example))


@pytest.mark.parametrize('fault,code', [('summary', 'summary'), ('binding', 'binding'), ('source', 'bundle'),
    ('profile', 'bundle'), ('receipt', 'input_receipt'), ('candidate', 'candidate'), ('count', 'candidate'),
    ('nonce', 'binding'), ('extra', 'binding'), ('claim', 'binding')])
def test_external_and_internal_joins_refuse_at_reached_predicate(example, fault, code):
    value, summary, binding = example
    if fault == 'summary':
        public = m.loads(summary, m.MAX_SUMMARY)
        public['cells'][0]['sources'][0]['sha256'] = 'd' * 64
        example = value, m.canonical(public), binding
    elif fault == 'binding': value['binding']['expected_head'] = 'b' * 40
    elif fault == 'source': value['prepared']['cells'][0]['source_pairs'][0][1] = 'changed'
    elif fault == 'profile': value['prepared']['cells'][0]['profile']['candidate_id'] = 'other'
    elif fault == 'receipt': value['input_receipt']['full_original_axis_authenticated'] = False
    elif fault == 'candidate': value['submission_candidates'][0]['submission_permitted'] = True
    elif fault == 'count': value['submission_candidates'].pop()
    elif fault == 'nonce': value['private_transport_nonce'] = 'g' * 64
    elif fault == 'extra': value['new_authority'] = True
    else: value['claim_pin']['byte_count'] = True
    refused(code, lambda: validated(example))


@pytest.mark.parametrize('fault', ['payload', 'descriptor', 'base64', 'order', 'activation', 'count', 'key'])
def test_upload_buffers_require_exact_descriptors_payloads_and_activation_last(example, fault):
    uploads = example[0]['upload_objects']
    if fault == 'payload': uploads[0]['payload_base64'] = base64.b64encode(b'changed').decode()
    elif fault == 'descriptor': uploads[0]['descriptor']['byte_count'] = True
    elif fault == 'base64': uploads[0]['payload_base64'] += '\n'
    elif fault == 'order': uploads[0], uploads[1] = uploads[1], uploads[0]
    elif fault == 'activation': uploads[-1]['descriptor']['activation_manifest'] = False
    elif fault == 'count': uploads.pop()
    else: uploads[0]['descriptor']['object_store_key'] = uploads[1]['descriptor']['object_store_key']
    refused('upload', lambda: validated(example))


@pytest.mark.parametrize('raw', [b'{"x":1,"x":1}', b'{"x":NaN}', b'{}\n', b' { }', b'\xff'])
def test_canonical_json_refuses_ambiguity_and_trailing_bytes(raw):
    refused('json', lambda: m.loads(raw, 100))


@pytest.fixture
def data_location(tmp_path, monkeypatch, example):
    root = tmp_path / 'synthetic-repository'
    root.mkdir(mode=0o755)
    data = root / 'artifacts/analyst_revisions_v2/legacy_six_extension/R343-20261105-B/submission-private.json'
    current = root
    for name in data.relative_to(root).parts[:-1]:
        current /= name
        current.mkdir(mode=0o700)
    raw = m.canonical(example[0])
    data.write_bytes(raw)
    data.chmod(0o600)
    monkeypatch.chdir(root)
    monkeypatch.setattr(m, 'ROOT', root)
    monkeypatch.setattr(m, 'DATA', data)
    monkeypatch.setattr(m.security, 'snapshot', lambda fd: ('synthetic-native-security', os.fstat(fd).st_uid))
    return data, raw


def context(example, data_location):
    _, raw = data_location
    return m.FreshSubmission(expected_pin=m.pin(raw), expected_summary=example[1],
        expected_binding=example[2], deadline=time.monotonic() + 899)


def test_original_fd_survives_consumption_and_only_new_B_data_is_opened(example, data_location, monkeypatch):
    opened = []
    real_open = os.open
    def observed(name, *args, **kwargs):
        opened.append(str(name))
        return real_open(name, *args, **kwargs)
    monkeypatch.setattr(m.os, 'open', observed)
    hold = context(example, data_location)
    with hold as fresh:
        assert fresh.fd is not None and len(fresh.value.candidates) == 7
        fresh.verify()
        assert 'submission-private.json' in opened
        assert not any(name in opened for name in ('claim.json', 'report.json', 'preparation-started.json'))
    assert hold.fd is None and not hold.rows
    refused('state', hold.__enter__)


@pytest.mark.parametrize('fault,code', [('pin', 'pin'), ('mode', 'metadata'), ('symlink', 'path')])
def test_invalid_pin_mode_or_symlink_refuses_before_private_parse(example, data_location, fault, code):
    path, raw = data_location
    hold = context(example, data_location)
    if fault == 'pin': hold.expected_pin['sha256'] = '0' * 64
    elif fault == 'mode': path.chmod(0o644)
    else:
        saved = path.with_name('retained-synthetic-original')
        path.rename(saved)
        path.symlink_to(saved)
    refused(code, hold.__enter__)
    assert hold.fd is None and not hold.rows


def test_named_swap_is_detected_with_held_original_fd(example, data_location):
    path, raw = data_location
    with pytest.raises(m.Refused, match='metadata'):
        with context(example, data_location) as hold:
            original_fd = hold.fd
            path.rename(path.with_name('retained-synthetic-original'))
            path.write_bytes(raw)
            path.chmod(0o600)
            assert os.pread(original_fd, len(raw), 0) == raw
    assert hold.fd is None and not hold.rows


def test_native_security_change_is_detected_even_with_unchanged_bytes(example, data_location, monkeypatch):
    with pytest.raises(m.Refused, match='security'):
        with context(example, data_location) as hold:
            monkeypatch.setattr(m.security, 'snapshot', lambda fd: ('synthetic-changed-native-security',))
    assert hold.fd is None and not hold.rows


def test_A_or_arbitrary_path_never_becomes_a_data_capability(example, data_location, monkeypatch):
    hold = context(example, data_location)
    monkeypatch.setattr(m, 'DATA', m.ROOT / 'artifacts/analyst_revisions_v2/legacy_six_extension/R343-20261105-A/submission-private.json')
    refused('scope', hold.__enter__)
    assert not hold.rows
