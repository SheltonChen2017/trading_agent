"""Synthetic fresh cleanup controls: no actual repository/private/QC routes."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import os
import subprocess

import pytest
from research.target_price_revisions_qc import extended_cleanup as d

e = d.e


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    def deny(*_a, **_kw): raise AssertionError('actual network/private/credential/repository route forbidden')
    monkeypatch.setattr(d.http.client, 'HTTPSConnection', deny)
    monkeypatch.setattr(d.ops, 'credential', deny)
    monkeypatch.setattr(subprocess, 'run', deny)
    real = d._open_directory
    def opening(path):
        assert not path.is_relative_to(d.LANE)
        return real(path)
    monkeypatch.setattr(d, '_open_directory', opening)


def fixture(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc); prep = 'b' * 64
    prefix = 'tpr-ext26/inputs/' + e.STUDY_ID + '/' + prep + '/'
    values, inventory = {}, []
    for index in range(72):
        raw = ('{"synthetic":"PRIVATE-LICENSED-SENTINEL","n":' + str(index) + '}').encode()
        sha = d._sha(raw); name = sha + '.json'; values[name] = raw
        inventory.append({'name': name, 'sha256': sha, 'bytes': len(raw), 'key': prefix + name})
    inventory.sort(key=lambda row: row['name']); targets = inventory[:22]
    monkeypatch.setattr(d, 'TARGET_SHA256', tuple(row['sha256'] for row in targets))
    monkeypatch.setattr(d, 'TARGET_BYTES', sum(row['bytes'] for row in targets))
    monkeypatch.setattr(d.compression, 'ORIGINAL_BYTES', sum(row['bytes'] for row in inventory))
    bundle_raw = e.canonical({'schema': 'tpr-ext26-source-bundle-v1', 'candidates': [], 'inputs': inventory,
        'preparation_sha256': prep, 'repository_sources': []})
    monkeypatch.setattr(d, 'BUNDLE_SHA256', d._sha(bundle_raw)); monkeypatch.setattr(d.compression, 'BUNDLE_SHA256', d._sha(bundle_raw))
    sources = {name: b'# synthetic source\n' for name in d.SOURCE_PATHS}; sources[d.BUNDLE] = bundle_raw
    source_hashes = {name: d._sha(raw) for name, raw in sources.items()}
    manifest = {'operation_id': d.QC_OPERATION, 'candidates': [], 'inputs': inventory, 'preparation_sha256': prep}
    manifest_raw = e.canonical(manifest); monkeypatch.setattr(d, 'MANIFEST_SHA256', d._sha(manifest_raw))
    monkeypatch.setattr(d.ops, 'validate_manifest', lambda body: None)
    pins = deepcopy(d.SOURCE_PINS); pins[d.PREFIX + 'extended_upload_diagnostic.py'] = source_hashes[d.PREFIX + 'extended_upload_diagnostic.py']
    monkeypatch.setattr(d, 'SOURCE_PINS', pins)
    diag = {'schema': 'tpr-ext26-upload-diagnostic-receipt-v1', 'status': 'COMPLETED', 'scope_spent': True,
        'study_id': e.STUDY_ID, 'candidate_id': d.ON, 'qc_operation_id': d.QC_OPERATION,
        'read_operation_id': d.DIAGNOSTIC.removesuffix('.result.json'), 'source_hashes': source_hashes,
        'read_inventory': {'manifest.' + d.QC_OPERATION + '.json': {'sha256': d.MANIFEST_SHA256}},
        'census': {'inputs': [{'input_sha256': row['sha256'], 'status': 'completed' if row in targets else 'unattempted',
            'terminal_status': 'succeeded' if row in targets else None, 'error_classification': None,
            'original_wire_sha256': 'c' * 64, 'projection_sha256': 'd' * 64, 'request_sequence': index + 1}
            for index, row in enumerate(inventory)]}}
    for key in ('automatic_retry', 'upload_repeated', 'old_receipts_renewed', 'licensed_payload_reads', 'off_response_reads', 'canonical_admission', 'trading'):
        diag[key] = False
    diag_raw = e.canonical(diag); monkeypatch.setattr(d, 'DIAGNOSTIC_SHA256', d._sha(diag_raw)); monkeypatch.setattr(d, 'DIAGNOSTIC_BYTES', len(diag_raw))
    payloads = [{'plain_name': row['name'], 'logical_key': row['key'], 'plain_sha256': row['sha256'], 'plain_bytes': row['bytes'],
        'stored_name': 'gzip.' + d._sha(b'gzip' + values[row['name']]) + '.json',
        'stored_key': prefix + 'gzip.' + d._sha(b'gzip' + values[row['name']]) + '.json',
        'gzip_sha256': d._sha(b'gzip' + values[row['name']]), 'gzip_bytes': 10} for row in inventory]
    mapping = {'schema': 'tpr-ext26-gzip-input-map-v1', 'study_id': e.STUDY_ID, 'freeze_sha256': e.FREEZE_SHA256,
        'preparation_sha256': prep, 'bundle_sha256': d.BUNDLE_SHA256, 'processing_operation_id': d.COMP_OPERATION,
        'processing_plan_sha256': d.COMP_PLAN_SHA256, 'encoding': 'gzip', 'gzip_level': 9, 'gzip_mtime': 0, 'payloads': payloads}
    map_raw = e.canonical(mapping); monkeypatch.setattr(d, 'MAPPING_SHA256', d._sha(map_raw)); monkeypatch.setattr(d, 'MAPPING_BYTES', len(map_raw))
    receipt = {'schema': 'tpr-ext26-compression-receipt-v1', 'study_id': e.STUDY_ID, 'freeze_sha256': e.FREEZE_SHA256,
        'operation_id': d.COMP_OPERATION, 'plan_sha256': d.COMP_PLAN_SHA256, 'git_head': 'a' * 40,
        'source_hashes': {name: source_hashes[name] for name in d.compression.SOURCE_PATHS}, 'owner_instruction_sha256': 'c' * 64,
        'bundle_sha256': d.BUNDLE_SHA256, 'preparation_sha256': prep, 'status': 'COMPLETED', 'scope_spent': True,
        'failure': None, 'input_count': 72, 'processed_count': 72, 'original_bytes': d.compression.ORIGINAL_BYTES,
        'gzip_bytes': 720, 'ratio': {'numerator': 720, 'denominator': d.compression.ORIGINAL_BYTES}, 'payloads': payloads,
        'original_read_bytes': 2 * d.compression.ORIGINAL_BYTES, 'derived_read_bytes': 720 + len(map_raw), 'stored_derived_bytes': 720 + len(map_raw),
        'mapping_name': d.COMP_OPERATION + '.mapping.json', 'mapping_sha256': d.MAPPING_SHA256, 'mapping_bytes': len(map_raw),
        'encoding': 'gzip', 'gzip_level': 9, 'gzip_mtime': 0, 'gzip_filename': '', 'python_version': '3.13',
        'zlib_compile_version': '1.2', 'zlib_runtime_version': '1.2', 'originals_retained_unchanged': True,
        'decompressed_bytes_exact': True, 'cloud_uploads': 0, 'cloud_deletes': 0, 'quantconnect_attempts': 0,
        'development_looks': 0, 'ended_utc': now.isoformat()}
    for key in ('source_reaccess', 'outcome_reads', 'automatic_retry', 'old_receipts_renewed', 'canonical_admission', 'trading'): receipt[key] = False
    receipt_raw = e.canonical(receipt); monkeypatch.setattr(d, 'COMP_SHA256', d._sha(receipt_raw)); monkeypatch.setattr(d, 'COMP_BYTES', len(receipt_raw))
    project = {'candidate_id': d.ON, 'project_id': d.PROJECT_ID, 'name': d.ON + '-private', 'organization_id': 'synthetic-own-org',
        'owner': True, 'lean_version_id': 1, 'max_file_size': 60000, 'at': now.isoformat(),
        'privacy_provenance': {'is_public_field_returned': False, 'returned_is_public': None, 'documented_default_private': True,
            'documented_default_reference': 'https://www.quantconnect.com/docs/v2/cloud-platform/security-and-ip',
            'privacy_attested': False, 'provider_privacy_attestation': False, 'collaborators_field_returned': True,
            'origin_operation_id': 'TPR-EXT26-QC-20261010-001', 'origin_kind': 'immutable_original_create_response_recovery'},
        'recovery_provenance': {'discovery_receipt_sha256': d.DISCOVERY_RECEIPT_SHA256,
            'discovery_admission_sha256': d.DISCOVERY_ADMISSION_SHA256,
            'original_six_file_hashes': {key: 'c' * 64 for key in ('operations_manifest', 'stage_spent', 'stage_transport', 'request_spent', 'request_terminal', 'request_projection')},
            'original_wire_sha256': 'd' * 64, 'original_projection_sha256': 'e' * 64,
            'network_creates': 0, 'new_looks': 0, 'quantconnect_attempts': 0, 'arbitrary_project_adoption': False}}
    monkeypatch.setattr(d, 'ORGANIZATION_SHA256', d._sha(project['organization_id'].encode('utf-8')))
    operations, inputs = tmp_path / 'operations', tmp_path / 'inputs'
    for root in (operations, inputs): root.mkdir(mode=0o700)
    def save(root, name, raw): (root / name).write_bytes(raw); (root / name).chmod(0o600)
    for name, raw in values.items(): save(inputs, name, raw)
    save(inputs, d.COMP_OPERATION + '.result.json', receipt_raw); save(inputs, d.COMP_OPERATION + '.mapping.json', map_raw)
    admission = {'schema': 'tpr-ext26-project-discovery-admission-v1', 'study_id': e.STUDY_ID, 'candidate_id': d.ON,
        'origin_operation_id': 'TPR-EXT26-QC-20261010-001', 'discovery_read_operation_id': d.DISCOVERY_ADMISSION.removesuffix('.project-admission.json'),
        'discovery_plan_sha256': 'a' * 64, 'field_census_sha256': 'b' * 64,
        'six_file_hashes': project['recovery_provenance']['original_six_file_hashes'],
        'response_wire_sha256': project['recovery_provenance']['original_wire_sha256'],
        'response_projection_sha256': project['recovery_provenance']['original_projection_sha256'], 'request_payload_sha256': 'c' * 64,
        'project': {key: project[key] for key in ('project_id', 'name', 'organization_id', 'owner', 'lean_version_id', 'max_file_size')},
        'privacy': {'is_public_returned': False, 'is_public': None, 'documented_default_private': False,
            'returned_private_field_false': False, 'privacy_attested': False}, 'admitted': False}
    admission_raw = e.canonical(admission)
    monkeypatch.setattr(d, 'DISCOVERY_ADMISSION_SHA256', d._sha(admission_raw)); monkeypatch.setattr(d, 'DISCOVERY_ADMISSION_BYTES', len(admission_raw))
    project['recovery_provenance']['discovery_admission_sha256'] = d.DISCOVERY_ADMISSION_SHA256
    save(operations, d.DISCOVERY_ADMISSION, admission_raw)
    save(operations, d.ON + '.project.json', e.canonical(project)); save(operations, 'manifest.' + d.QC_OPERATION + '.json', manifest_raw)
    save(operations, d.DIAGNOSTIC, diag_raw)
    plan = d._plan(source_hashes=source_hashes, git_head='a' * 40, owner_instruction_sha256='e' * 64,
        created_utc=(now - timedelta(seconds=1)).isoformat(), expires_utc=(now + timedelta(hours=1)).isoformat(),
        operation_id=d.OPERATION_ID, bundle_raw=bundle_raw, mode='offline-fixture')
    calls = []
    def transport(endpoint, payload):
        body = e.parse_json(payload)
        assert body['organizationId'] == 'synthetic-own-org'
        row = next(row for row in targets if row['key'] == body['key'])
        kind = endpoint.split('/')[-1]
        assert (operations / ('ext26.cleanup.' + kind + '.' + row['sha256'] + '.spent.json')).is_file()
        calls.append((endpoint, row['sha256']))
        if endpoint == 'object/delete':
            assert len([item for item in calls if item[0] == 'object/properties']) == 22
            return e.canonical({'success': True, 'errors': []}), 200, ''
        return e.canonical({'success': True, 'errors': [], 'metadata': {'key': row['key'], 'size': row['bytes'],
            'md5': hashlib.md5(values[row['name']]).hexdigest(), 'preview': 'PRIVATE-LICENSED-SENTINEL'}}), 200, ''
    return {'plan': plan, 'sources': sources, 'operations': operations, 'inputs': inputs, 'values': values,
        'now': now, 'calls': calls, 'transport': transport, 'receipt': receipt, 'mapping': mapping, 'diag': diag, 'project': project, 'admission': admission, 'save': save}


def execute(f):
    return e.parse_json(d._execute(f['plan'], f['sources'], f['operations'], f['inputs'], clock=lambda: f['now'], guard=lambda *_: None, transport=f['transport']))


def repin_receipt(f, monkeypatch):
    raw = e.canonical(f['receipt']); monkeypatch.setattr(d, 'COMP_SHA256', d._sha(raw)); monkeypatch.setattr(d, 'COMP_BYTES', len(raw))
    f['plan']['compression_sha256'] = d.COMP_SHA256; f['save'](f['inputs'], d.COMP_OPERATION + '.result.json', raw)


def test_all_proofs_local_originals_and22_properties_precede_any_delete(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); real = d._read; names = []
    def read(directory, name, **kw):
        assert (f['operations'] / (d.OPERATION_ID + '.claim.spent.json')).is_file()
        names.append(name); return real(directory, name, **kw)
    monkeypatch.setattr(d, '_read', read); result = execute(f)
    assert result['status'] == 'COMPLETED' and result['all_22_prechecks_verified'] is result['all_72_processing_proof_verified'] is True
    assert len(result['deleted']) == 22 and len(result['requests']) == 44
    assert f['calls'][:22] == [('object/properties', sha) for sha in d.TARGET_SHA256]
    assert f['calls'][22:] == [('object/delete', sha) for sha in d.TARGET_SHA256]
    assert len([name for name in names if name in f['values']]) == 22
    for name, raw in f['values'].items(): assert (f['inputs'] / name).read_bytes() == raw
    assert b'PRIVATE-LICENSED-SENTINEL' not in e.canonical(result)
    for path in f['operations'].glob('ext26.cleanup.*.json'): assert b'PRIVATE-LICENSED-SENTINEL' not in path.read_bytes()
    with pytest.raises(FileExistsError): execute(f)


@pytest.mark.parametrize('field,value', [('status', 'FAILED_OR_UNCERTAIN'), ('processed_count', 71), ('originals_retained_unchanged', False),
    ('decompressed_bytes_exact', False), ('original_read_bytes', 1), ('cloud_deletes', 1), ('source_reaccess', True), ('plan_sha256', 'f' * 64)])
def test_invalid_compression_proof_never_calls_network(tmp_path, monkeypatch, field, value):
    f = fixture(tmp_path, monkeypatch); f['receipt'][field] = value; repin_receipt(f, monkeypatch)
    answer = execute(f)
    assert answer['status'] == 'FAILED_OR_UNCERTAIN' and answer['deleted'] == [] and f['calls'] == []
    assert (f['operations'] / (d.OPERATION_ID + '.claim.spent.json')).is_file()


@pytest.mark.parametrize('kind', ['changed', 'missing', 'size', 'symlink', 'hardlink', 'mode'])
def test_unrecoverable_originals_refuse_before_properties(tmp_path, monkeypatch, kind):
    f = fixture(tmp_path, monkeypatch); path = f['inputs'] / (d.TARGET_SHA256[-1] + '.json')
    if kind == 'changed': path.write_bytes(b'x' * path.stat().st_size)
    if kind == 'missing': path.unlink()
    if kind == 'size': path.write_bytes(path.read_bytes() + b'x')
    if kind == 'mode': path.chmod(0o644)
    if kind == 'hardlink': os.link(path, f['inputs'] / 'other')
    if kind == 'symlink':
        target = f['inputs'] / 'other'; target.write_bytes(path.read_bytes()); target.chmod(0o600); path.unlink(); path.symlink_to(target)
    result = execute(f)
    assert result['status'] == 'FAILED_OR_UNCERTAIN' and f['calls'] == [] and result['deleted'] == []


@pytest.mark.parametrize('kind', ['key', 'size', 'md5', 'missing_md5', 'wrong_container', 'unknown_shape', 'denied', 'boolsize', 'redirect', 'token_echo', 'malformed'])
def test_bad_final_property_prevents_all_deletion_and_retains_spent_request(tmp_path, monkeypatch, kind):
    f = fixture(tmp_path, monkeypatch); real = f['transport']
    def transport(endpoint, payload):
        raw, status, token = real(endpoint, payload)
        if len(f['calls']) != 22: return raw, status, token
        body = e.parse_json(raw)
        if kind in {'key', 'size', 'md5', 'boolsize'}: body['metadata'][{'boolsize': 'size'}.get(kind, kind)] = {'key': 'foreign', 'size': 1, 'md5': '0' * 32, 'boolsize': True}[kind]
        if kind == 'missing_md5': del body['metadata']['md5']
        if kind == 'wrong_container': body['object'] = body.pop('metadata')
        if kind == 'unknown_shape': body['metadata']['unexpected'] = 'private'
        if kind == 'denied': body['success'] = False; body['errors'] = ['PRIVATE-LICENSED-SENTINEL']
        if kind == 'redirect': status = 302
        if kind == 'token_echo': token = 'SENSITIVE-TOKEN'; body['metadata']['preview'] = token
        return (b'bad JSON' if kind == 'malformed' else e.canonical(body)), status, token
    f['transport'] = transport; result = execute(f)
    assert result['status'] == 'FAILED_OR_UNCERTAIN' and len(result['requests']) == 22 and result['deleted'] == []
    assert not any(endpoint == 'object/delete' for endpoint, _ in f['calls'])
    final = result['requests'][-1]
    assert final['original_wire_sha256'] is None if kind in {'token_echo', 'malformed'} else final['original_wire_sha256'] is not None
    assert b'SENSITIVE-TOKEN' not in e.canonical(result) and b'PRIVATE-LICENSED-SENTINEL' not in e.canonical(result)


def test_unknown_delete_stops_immediately_no_repeat_no_refund(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); real = f['transport']
    def transport(endpoint, payload):
        response = real(endpoint, payload)
        if endpoint == 'object/delete' and len(f['calls']) == 25: raise TimeoutError('private error')
        return response
    f['transport'] = transport; result = execute(f)
    assert result['all_22_prechecks_verified'] is True and result['status'] == 'FAILED_OR_UNCERTAIN'
    assert len(result['deleted']) == 2 and len(result['requests']) == len(f['calls']) == 25
    assert (f['operations'] / ('ext26.cleanup.delete.' + d.TARGET_SHA256[2] + '.spent.json')).is_file()
    with pytest.raises(FileExistsError): execute(f)


@pytest.mark.parametrize('value', ['0' * 32, 'A' * 32, base64.b64encode(bytes(range(16))).decode()])
def test_strict_hex_or_canonical_base64_md5(value):
    assert len(d._md5(value)) == 32


@pytest.mark.parametrize('value', ['', 'sha256:' + 'a' * 64, 'a' * 31, 'a' * 33, '====', True, 1])
def test_unsupported_md5_refused(value):
    with pytest.raises(ValueError): d._md5(value)


def test_fd_exact_size_and_remaining_are_checked_before_body(tmp_path, monkeypatch):
    root = tmp_path / 'owned'; root.mkdir(mode=0o700); path = root / 'payload.json'; path.write_bytes(b'01234567890'); path.chmod(0o600)
    fd = d._open_directory(root); calls = []
    monkeypatch.setattr(d.os, 'read', lambda *_: calls.append(True) or b'')
    try:
        with pytest.raises(ValueError): d._read(fd, path.name, expected=10, maximum=11)
        with pytest.raises(ValueError): d._read(fd, path.name, expected=11, maximum=10)
    finally: os.close(fd)
    assert calls == []


def test_cli_closed_error_no_private_echo(monkeypatch, capsys):
    def bad(**_kw): raise ValueError('PRIVATE-LICENSED-SENTINEL SENSITIVE-TOKEN')
    monkeypatch.setattr(d, 'run', bad)
    assert d.main(['--operation-id', d.OPERATION_ID, '--owner-instruction-sha256', 'a' * 64,
        '--created-utc', '2026-10-10T00:00:00+00:00', '--expires-utc', '2026-10-10T01:00:00+00:00']) == 1
    assert 'PRIVATE-LICENSED-SENTINEL' not in capsys.readouterr().out


def test_tls_host_keylog_no_redirect_retry_and_30s_bound(monkeypatch):
    seen = {}
    class Context:
        def __init__(self, protocol): seen['protocol'] = protocol
        def load_default_certs(self): seen['certs'] = True
    class Response:
        status = 200
        def read(self, maximum): seen['bound'] = maximum; return b'{"success":true,"errors":[]}'
    class Connection:
        def __init__(self, host, **kw): seen.update(host=host, **kw)
        def request(self, method, path, **kw): seen.update(method=method, path=path, body=kw['body'])
        def getresponse(self): return Response()
        def close(self): seen['closed'] = True
    monkeypatch.setattr(d.ssl, 'SSLContext', Context); monkeypatch.setattr(d.http.client, 'HTTPSConnection', Connection)
    monkeypatch.setattr(d.ops, 'credential', lambda: ('123', 'synthetic-token'))
    raw, status, token = d._transport('object/delete', b'{}')
    assert seen['host'] == 'www.quantconnect.com' and seen['timeout'] == 30 and seen['method'] == 'POST'
    assert seen['path'] == '/api/v2/object/delete' and seen['bound'] == d.MAX_RESPONSE + 1 and seen['closed'] is True
    assert seen['context'].keylog_filename is None and seen['context'].check_hostname is True and seen['context'].verify_mode == d.ssl.CERT_REQUIRED
    assert raw and status == 200 and token == 'synthetic-token'
    with pytest.raises(ValueError): d._transport('object/get', b'{}')


def test_nested_request_deadline_preserves_outer_budget():
    with d._deadline():
        before = d.signal.getitimer(d.signal.ITIMER_REAL)[0]
        with d._request_deadline(): assert 0 < d.signal.getitimer(d.signal.ITIMER_REAL)[0] <= 30
        after = d.signal.getitimer(d.signal.ITIMER_REAL)[0]
        assert 0 < after <= before <= d.MAX_SECONDS


@pytest.mark.parametrize('kind', ['foreign', 'boolean_id', 'owner', 'missing_provenance', 'privacy_attested', 'wrong_origin', 'wrong_discovery', 'adopted', 'creates'])
def test_actual_successor_project_shape_and_provenance_refuse_unbound(tmp_path, monkeypatch, kind):
    f = fixture(tmp_path, monkeypatch); project = f['project']
    if kind == 'foreign': project['project_id'] = d.PROJECT_ID + 1
    if kind == 'boolean_id': project['project_id'] = True
    if kind == 'owner': project['owner'] = False
    if kind == 'missing_provenance': del project['recovery_provenance']
    if kind == 'privacy_attested': project['privacy_provenance']['privacy_attested'] = True
    if kind == 'wrong_origin': project['privacy_provenance']['origin_operation_id'] = 'foreign'
    if kind == 'wrong_discovery': project['recovery_provenance']['discovery_receipt_sha256'] = 'f' * 64
    if kind == 'adopted': project['recovery_provenance']['arbitrary_project_adoption'] = True
    if kind == 'creates': project['recovery_provenance']['network_creates'] = 1
    f['save'](f['operations'], d.ON + '.project.json', e.canonical(project)); result = execute(f)
    assert result['status'] == 'FAILED_OR_UNCERTAIN' and f['calls'] == []


def test_documented_optional_errors_absence_stays_absent(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); target = f['plan']['targets'][0]
    target = {**target, 'md5': hashlib.md5(f['values'][target['name']]).hexdigest()}
    assert d._response(e.canonical({'success': True}), 'object/delete', target) == {'success': True}
    assert d._response(e.canonical({'success': True, 'metadata': {'key': target['key'], 'size': target['bytes'], 'md5': target['md5']}}), 'object/properties', target)['success'] is True
    with pytest.raises(ValueError): d._response(e.canonical({'success': True, 'errors': None}), 'object/delete', target)


def test_changed_organization_with_unchanged_project_id_and_provenance_never_calls_network(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); f['project']['organization_id'] = 'foreign-org'
    f['save'](f['operations'], d.ON + '.project.json', e.canonical(f['project']))
    result = execute(f)
    assert result['status'] == 'FAILED_OR_UNCERTAIN' and result['requests'] == [] and f['calls'] == []
    assert ('operations/' + d.DISCOVERY_ADMISSION) not in result['read_inventory']


@pytest.mark.parametrize('kind', ['same_size_changed', 'size_changed', 'missing', 'foreign_organization', 'destination_name', 'privacy', 'wrong_original_wire'])
def test_pinned_original_admission_change_or_lineage_disagreement_refuses(tmp_path, monkeypatch, kind):
    f = fixture(tmp_path, monkeypatch); path = f['operations'] / d.DISCOVERY_ADMISSION
    if kind == 'same_size_changed': path.write_bytes(b'x' * path.stat().st_size)
    elif kind == 'size_changed': path.write_bytes(path.read_bytes() + b'x')
    elif kind == 'missing': path.unlink()
    else:
        if kind == 'foreign_organization': f['admission']['project']['organization_id'] = 'foreign'
        if kind == 'destination_name': f['admission']['project']['name'] = 'foreign'
        if kind == 'privacy': f['admission']['privacy']['privacy_attested'] = True
        if kind == 'wrong_original_wire': f['admission']['response_wire_sha256'] = 'f' * 64
        raw = e.canonical(f['admission']); monkeypatch.setattr(d, 'DISCOVERY_ADMISSION_SHA256', d._sha(raw)); monkeypatch.setattr(d, 'DISCOVERY_ADMISSION_BYTES', len(raw))
        f['plan'].update(discovery_admission_sha256=d.DISCOVERY_ADMISSION_SHA256, discovery_admission_bytes=len(raw))
        f['project']['recovery_provenance']['discovery_admission_sha256'] = d.DISCOVERY_ADMISSION_SHA256
        f['save'](f['operations'], d.ON + '.project.json', e.canonical(f['project'])); f['save'](f['operations'], d.DISCOVERY_ADMISSION, raw)
    result = execute(f)
    assert result['status'] == 'FAILED_OR_UNCERTAIN' and f['calls'] == []
