"""First-key continuation fixtures; actual roots, API, credentials are denied."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import os
import subprocess

import pytest
from research.target_price_revisions_qc import extended_input_probe_successor as d
from tests.target_price_revisions_qc import test_qc_extended_operations_compressed as lifecycle

e = d.e


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    def deny(*_args, **_kw): raise AssertionError('actual private, credential, API or Git forbidden')
    monkeypatch.setattr(d.ops, 'credential', deny)
    monkeypatch.setattr(d.http.client, 'HTTPSConnection', deny)
    monkeypatch.setattr(subprocess, 'run', deny)
    monkeypatch.setattr(d, '_transport', deny)
    opening = d._open_directory
    def isolated(path):
        assert not path.is_relative_to(d.LANE)
        return opening(path)
    monkeypatch.setattr(d, '_open_directory', isolated)


def fixture(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    manifest, mapping, store, _ = lifecycle.body()
    manifest['operation_id'] = d.census.QC_OPERATION
    manifest['created_utc'] = (now - timedelta(hours=1)).isoformat()
    manifest['expires_utc'] = (now + timedelta(hours=1)).isoformat()
    manifest_raw = e.canonical(manifest)
    monkeypatch.setattr(d.census, 'MANIFEST_SHA256', d._sha(manifest_raw))
    first = mapping['payloads'][0]; encoded = store.values[first['stored_key']]
    monkeypatch.setattr(d.probe, 'FIRST_GZIP_SHA256', first['gzip_sha256'])
    monkeypatch.setattr(d.probe, 'FIRST_GZIP_BYTES', len(encoded))
    bundle = {'schema': 'tpr-ext26-source-bundle-v1', 'candidates': manifest['candidates'],
        'inputs': manifest['inputs'], 'preparation_sha256': manifest['preparation_sha256'], 'repository_sources': []}
    bundle_raw = e.canonical(bundle)
    monkeypatch.setattr(d.census, 'BUNDLE_SHA256', d._sha(bundle_raw))
    sources = {name: b'# synthetic committed source\n' for name in d.SOURCE_PATHS}
    sources[d.BUNDLE] = bundle_raw
    root, inputs = tmp_path / 'metadata', tmp_path / 'inputs'
    root.mkdir(mode=0o700); inputs.mkdir(mode=0o700)
    def save(name, body, directory=root):
        raw = body if type(body) is bytes else e.canonical(body)
        path = directory / name; path.write_bytes(raw); path.chmod(0o600); return raw
    organization = 'SYNTHETIC-SECRET-OWN-ORG'
    for module in (d, d.probe): monkeypatch.setattr(module, 'ORGANIZATION_SHA256', d._sha(organization.encode()))
    project = {'candidate_id': d.ON, 'project_id': d.PROJECT_ID,
        'name': d.ON + '-private', 'organization_id': organization, 'owner': True}
    project_raw = save(d.ON + '.project.json', project)
    save(first['stored_name'], encoded, inputs)
    stamp = (now - timedelta(minutes=30)).isoformat()
    failed = e.project_wire(e.canonical({'success': False, 'errors': ['storage quota exceeded']}), credential='synthetic-token')
    monkeypatch.setattr(d, 'ORIGIN_WIRE_SHA256', failed['original_wire_sha256'])
    monkeypatch.setattr(d, 'ORIGIN_PROJECTION_SHA256', failed['projection_sha256'])
    prefix = 'compressed-input.' + first['gzip_sha256']
    original_payload_sha = d._sha(d._multipart(organization, first, encoded)[0])
    _, _, mapping_hash = d.census._inventory(bundle_raw)
    origin = {
        'manifest.' + d.census.QC_OPERATION + '.json': manifest_raw,
        prefix + '.read.spent.json': {'at': stamp, 'name': first['stored_name'], 'gzip_sha256': first['gzip_sha256'],
            'mapping_sha256': mapping_hash, 'manifest_sha256': d.census.MANIFEST_SHA256},
        prefix + '.upload.spent.json': {'at': stamp, 'manifest_sha256': d.census.MANIFEST_SHA256, 'payload_sha256': original_payload_sha},
        prefix + '.upload.transport.json': {'at': stamp, 'endpoint': 'object/set'},
        'request.0061.spent.json': {'at': stamp, 'endpoint': 'object/set', 'payload_sha256': original_payload_sha,
            'manifest_sha256': d.census.MANIFEST_SHA256},
        'request.0061.terminal.json': {'at': stamp, 'status': 'failed_or_unknown', 'automatic_retry': False},
        'request.0061.projection.json': failed}
    origin_raw = {name: save(name, body) for name, body in origin.items()}
    target, _, _ = d._first(bundle_raw)
    receipt = {'schema': 'tpr-ext26-store-probe-receipt-v1', 'study_id': e.STUDY_ID,
        'operation_id': d.PROBE_OPERATION, 'status': 'COMPLETED', 'scope_spent': True,
        'bundle_sha256': d._sha(bundle_raw), 'mapping_sha256': mapping_hash,
        'target_gzip_sha256': first['gzip_sha256'], 'target_gzip_bytes': len(encoded),
        'target_directory_sha256': d._sha(target['directory'].encode()), 'target_key_sha256': d._sha(target['key'].encode()),
        'project_id': d.PROJECT_ID, 'organization_sha256': d.ORGANIZATION_SHA256,
        'failed_origin_preserved': d._origin(), 'ended_utc': (now - timedelta(seconds=1)).isoformat(),
        'source_hashes': {name: d._sha(sources[name]) for name in d.probe.SOURCE_PATHS},
        'input_body_reads': False, 'mutations': False, 'automatic_retry': False, 'old_claims_renewed': False,
        'new_looks': 0, 'quantconnect_attempts': 0, 'requests': [{}, {}],
        'project_receipt_sha256': d._sha(project_raw), 'project_receipt_bytes': len(project_raw)}
    receipt_raw = save(d.PROBE_OPERATION + '.result.json', receipt)
    monkeypatch.setattr(d, 'PROBE_RECEIPT_SHA256', d._sha(receipt_raw))
    monkeypatch.setattr(d, 'PROBE_RECEIPT_BYTES', len(receipt_raw))
    plan = d._plan(source_hashes={name: d._sha(raw) for name, raw in sources.items()}, git_head='a' * 40,
        owner_instruction_sha256='b' * 64, created_utc=(now - timedelta(seconds=1)).isoformat(),
        expires_utc=(now + timedelta(hours=1)).isoformat(), operation_id='TPR-EXT26-INPUT-PROBE-SYNTHETIC-001',
        bundle_raw=bundle_raw, mode='offline-fixture')
    before = {'success': False, 'errors': ['key not found']}
    after = {'success': True, 'errors': [], 'metadata': {'key': first['stored_key'],
        'size': len(encoded), 'md5': hashlib.md5(encoded).hexdigest()}}
    mutation = {'success': True, 'errors': []}
    calls = []
    def transport(endpoint, raw, content_type):
        assert (root / (plan['operation_id'] + '.claim.spent.json')).is_file()
        number = len(calls) + 1
        assert (root / (plan['operation_id'] + '.request.' + str(number) + '.spent.json')).is_file()
        calls.append((endpoint, raw, content_type))
        if endpoint == 'object/set':
            assert (root / (plan['operation_id'] + '.input-read.spent.json')).is_file()
            expected_raw, expected_content = d._multipart(organization, first, encoded)
            assert raw == expected_raw and content_type == expected_content
            return e.canonical(mutation), 200
        assert e.parse_json(raw) == {'organizationId': organization, 'key': first['stored_key']}
        return e.canonical(before if number == 1 else after), 200
    return {'now': now, 'plan': plan, 'sources': sources, 'root': root, 'inputs': inputs, 'save': save,
        'calls': calls, 'transport': transport, 'first': first, 'encoded': encoded, 'before': before,
        'after': after, 'mutation': mutation, 'origin': origin, 'origin_raw': origin_raw, 'receipt': receipt,
        'receipt_raw': receipt_raw, 'organization': organization, 'project': project}


def execute(f, **kwargs):
    return e.parse_json(d._execute(f['plan'], f['sources'], f['root'], f['inputs'], clock=lambda: f['now'],
        guard=kwargs.pop('guard', lambda *_: None), transport=kwargs.pop('transport', f['transport']), **kwargs))


def test_fresh_first_upload_matches_native_properties_preserves_failed_origin_and_no_attempt(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); answer = execute(f)
    assert answer['status'] == 'COMPLETED_FIRST_KEY_UPLOAD'
    assert [call[0] for call in f['calls']] == ['object/properties', 'object/set', 'object/properties']
    assert answer['input_read_bytes'].fraction() == len(f['encoded'])
    assert answer['object_set_succeeded'] is answer['native_md5_matched'] is answer['global_completion_created'] is True
    assert answer['new_looks'].fraction() == answer['quantconnect_attempts'].fraction() == 0
    assert answer['native_absence_attested'] is answer['full_capacity_proved'] is answer['native_content_sha256_verified'] is False
    assert answer['quota_headroom_unknown'] is True
    assert all((f['root'] / name).read_bytes() == raw for name, raw in f['origin_raw'].items())
    assert (f['root'] / (f['plan']['operation_id'] + '.native-hash-proof.json')).is_file()
    completion = f['root'] / ('compressed-input.' + f['first']['gzip_sha256'] + '.completed.json')
    assert d._sha(completion.read_bytes()) == answer['global_completion_sha256']
    assert f['organization'].encode() not in e.canonical(answer)
    assert f['first']['stored_key'].encode() not in e.canonical(answer)
    with pytest.raises(FileExistsError): execute(f)
    assert len(f['calls']) == 3


def test_present_matching_metadata_no_overwrite_or_invented_global_upload(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); f['before'].update(f['after'])
    answer = execute(f)
    assert answer['status'] == 'PRESENT_MATCHED_NO_UPLOAD' and len(f['calls']) == 1
    assert answer['present_matching_metadata_only'] is answer['native_md5_matched'] is True
    assert answer['object_set_succeeded'] is answer['global_completion_created'] is False
    assert not list(f['root'].glob('compressed-input.*.completed.json'))


@pytest.mark.parametrize('kind', ['md5', 'size', 'key', 'unauthorized', 'quota', 'unknown', 'mixed_notfound'])
def test_preflight_mismatch_or_unknown_never_overwrites(tmp_path, monkeypatch, kind):
    f = fixture(tmp_path, monkeypatch)
    f['before'].update(deepcopy(f['after']))
    if kind == 'md5': f['before']['metadata']['md5'] = 'a' * 32
    if kind == 'size': f['before']['metadata']['size'] += 1
    if kind == 'key': f['before']['metadata']['key'] = 'foreign/key'
    if kind in {'unauthorized', 'quota', 'unknown', 'mixed_notfound'}:
        f['before'].update(success=False, errors=[{'unauthorized': 'not authorized', 'quota': 'storage quota exceeded',
            'unknown': 'unrecognized', 'mixed_notfound': 'not found; storage quota exceeded'}[kind]])
    answer = execute(f)
    assert answer['status'] == 'FAILED_OR_UNCERTAIN' and len(f['calls']) == 1
    assert not answer['object_set_succeeded'] and not answer['global_completion_created']
    assert not list(f['root'].glob('compressed-input.*.completed.json'))


@pytest.mark.parametrize('kind', ['quota', 'unknown', 'post_md5', 'post_size', 'post_missing', 'transport'])
def test_effect_or_postproof_failure_stays_spent_without_completion(tmp_path, monkeypatch, kind):
    f = fixture(tmp_path, monkeypatch)
    if kind in {'quota', 'unknown'}: f['mutation'].update(success=False, errors=['storage quota exceeded' if kind == 'quota' else 'unrecognized'])
    if kind == 'post_md5': f['after']['metadata']['md5'] = 'a' * 32
    if kind == 'post_size': f['after']['metadata']['size'] -= 1
    if kind == 'post_missing': f['after'].update(success=False, errors=['key not found'])
    transport = f['transport']
    def chosen(endpoint, raw, content_type):
        if kind == 'transport' and endpoint == 'object/set':
            f['calls'].append((endpoint, raw, content_type)); raise OSError('SECRET-PRIVATE-ERROR')
        return transport(endpoint, raw, content_type)
    answer = execute(f, transport=chosen)
    assert answer['status'] == 'FAILED_OR_UNCERTAIN' and answer['scope_spent'] is True
    assert len(f['calls']) == (2 if kind in {'quota', 'unknown', 'transport'} else 3)
    assert not answer['global_completion_created'] and not list(f['root'].glob('compressed-input.*.completed.json'))
    assert b'SECRET-PRIVATE' not in e.canonical(answer)


@pytest.mark.parametrize('kind', ['receipt_hash', 'receipt_stale', 'project', 'origin', 'origin_payload', 'prior_completed', 'encoded_hash', 'encoded_size'])
def test_bad_lineage_or_input_refuses_before_api(tmp_path, monkeypatch, kind):
    f = fixture(tmp_path, monkeypatch)
    if kind == 'receipt_hash': f['save'](d.PROBE_OPERATION + '.result.json', f['receipt_raw'][:-1] + b' ')
    if kind == 'receipt_stale': f['now'] += timedelta(hours=5)
    if kind == 'project': f['project']['organization_id'] = 'FOREIGN'; f['save'](d.ON + '.project.json', f['project'])
    if kind == 'origin': f['origin']['request.0061.spent.json']['endpoint'] = 'object/get'; f['save']('request.0061.spent.json', f['origin']['request.0061.spent.json'])
    if kind == 'origin_payload':
        for name in ('request.0061.spent.json', 'compressed-input.' + f['first']['gzip_sha256'] + '.upload.spent.json'):
            f['origin'][name]['payload_sha256'] = 'f' * 64; f['save'](name, f['origin'][name])
    if kind == 'prior_completed': f['save']('compressed-input.' + f['first']['gzip_sha256'] + '.completed.json', {'preserve': True})
    if kind == 'encoded_hash': f['save'](f['first']['stored_name'], b'X' * len(f['encoded']), f['inputs'])
    if kind == 'encoded_size': f['save'](f['first']['stored_name'], f['encoded'] + b'X', f['inputs'])
    if kind == 'receipt_stale':
        with pytest.raises(d.Refusal): execute(f)
    else:
        answer = execute(f); assert answer['status'] == 'FAILED_OR_UNCERTAIN'
    assert not f['calls']


def test_read_claims_precede_opened_exact_size_body_and_input_no_other_keys(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); reading, seen = d._read_exact, []
    def observed(fd, name, **kwargs):
        assert (f['root'] / (f['plan']['operation_id'] + '.claim.spent.json')).is_file()
        if name == f['first']['stored_name']:
            assert (f['root'] / (f['plan']['operation_id'] + '.input-read.spent.json')).is_file()
            assert kwargs['expected_size'] == len(f['encoded']) and kwargs['maximum'] == d.MAX_INPUT_BYTES
        seen.append(name); return reading(fd, name, **kwargs)
    monkeypatch.setattr(d, '_read_exact', observed)
    assert execute(f)['status'] == 'COMPLETED_FIRST_KEY_UPLOAD'
    assert seen.count(f['first']['stored_name']) == 1
    assert all('D0' not in name for name in seen)


def test_exact_opened_descriptor_size_and_maximum_before_body(tmp_path, monkeypatch):
    directory = tmp_path / 'bounded'; directory.mkdir(mode=0o700)
    path = directory / 'too-large.json'; path.write_bytes(b'X' * 20); path.chmod(0o600)
    fd = d._open_directory(directory)
    try:
        monkeypatch.setattr(os, 'read', lambda *_args: pytest.fail('oversized body read'))
        with pytest.raises(d.Refusal): d._read_exact(fd, path.name, maximum=10)
        with pytest.raises(d.Refusal): d._read_exact(fd, path.name, maximum=30, expected_size=10)
    finally: os.close(fd)


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'mode', 'input_directory'])
def test_input_custody_refuses_before_api(tmp_path, monkeypatch, kind):
    f = fixture(tmp_path, monkeypatch); path = f['inputs'] / f['first']['stored_name']
    if kind == 'symlink':
        original = f['inputs'] / 'old'; path.rename(original); path.symlink_to(original)
    if kind == 'hardlink': os.link(path, f['inputs'] / 'copy')
    if kind == 'mode': path.chmod(0o644)
    if kind == 'input_directory': f['inputs'].chmod(0o755)
    assert execute(f)['status'] == 'FAILED_OR_UNCERTAIN' and not f['calls']


@pytest.mark.parametrize('kind', ['expired', 'source', 'plan', 'duration', 'identifier'])
def test_invalid_scope_refuses_before_private_open(tmp_path, monkeypatch, kind):
    f = fixture(tmp_path, monkeypatch)
    if kind == 'expired': f['now'] += timedelta(hours=2)
    if kind == 'source': f['sources'][d.SOURCE_RELATIVE] += b'# changed'
    if kind == 'plan': f['plan']['first_key_only'] = False
    if kind == 'duration': f['plan']['expires_utc'] = (f['now'] + timedelta(hours=5)).isoformat()
    if kind == 'identifier': f['plan']['operation_id'] = 'OLD-SPENT-OPERATION'
    monkeypatch.setattr(d, '_open_directory', lambda *_args: pytest.fail('invalid scope opened private root'))
    with pytest.raises(d.Refusal): execute(f)


def test_fixture_cannot_target_real_operations_or_input_root(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    with pytest.raises(d.Refusal):
        d._execute(f['plan'], f['sources'], d.PRIVATE_ROOT, f['inputs'], clock=lambda: f['now'], guard=lambda *_: None, transport=f['transport'])
    with pytest.raises(d.Refusal):
        d._execute(f['plan'], f['sources'], f['root'], d.INPUT_ROOT, clock=lambda: f['now'], guard=lambda *_: None, transport=f['transport'])


@pytest.mark.parametrize('name', ['probe', 'storage', 'e', 'ops', 'census', 'old'])
def test_foreign_loaded_module_refuses_before_git_source_private_or_network(monkeypatch, name):
    module = {'probe': d.probe, 'storage': d.storage, 'e': d.e, 'ops': d.ops,
              'census': d.census, 'old': d.probe.old}[name]
    monkeypatch.setattr(module, '__file__', '/unrelated/foreign-loaded-module.py')
    for boundary in ('_guard', '_sources', '_open_directory', '_transport'):
        monkeypatch.setattr(d, boundary, lambda *_args, **_kw: pytest.fail('foreign module crossed custody boundary'))
    with pytest.raises(d.Refusal): d.run()
