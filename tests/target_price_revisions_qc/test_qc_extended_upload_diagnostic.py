"""Synthetic upload metadata only; credentials/network/actual roots denied."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os

import pytest
from research.target_price_revisions_qc import extended_upload_diagnostic as d
from test_qc_extended_operations import manifest as original_manifest

e = d.e


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    def deny(*_a, **_kw): raise AssertionError('actual credentials/network/repository/private access forbidden')
    monkeypatch.setattr(d.ops, 'credential', deny)
    monkeypatch.setattr(d.ops.http.client, 'HTTPSConnection', deny)
    monkeypatch.setattr(d.subprocess, 'run', deny)
    original = d._open_directory
    def opening(path):
        assert not path.is_relative_to(d.LANE)
        return original(path)
    monkeypatch.setattr(d, '_open_directory', opening)


def fixture(tmp_path, monkeypatch, *, failed=True):
    now = datetime.now(timezone.utc)
    body = original_manifest(operation=d.QC_OPERATION)
    body['inputs'] = [{'name': f'synthetic-{index:02d}.json', 'sha256': f'{index + 1:064x}', 'bytes': 1,
        'key': 'tpr-ext26/inputs/' + e.STUDY_ID + '/' + body['preparation_sha256'] + '/' + f'{index + 1:064x}' + '.json'}
        for index in range(d.INPUT_COUNT)]
    bundle = {'schema': 'tpr-ext26-source-bundle-v1', **{key: body[key] for key in ('candidates', 'inputs', 'preparation_sha256')}, 'repository_sources': []}
    raw_bundle, raw_manifest = e.canonical(bundle), e.canonical(body)
    monkeypatch.setattr(d, 'BUNDLE_SHA256', d._sha(raw_bundle)); monkeypatch.setattr(d, 'MANIFEST_SHA256', d._sha(raw_manifest))
    source = {name: b'# synthetic committed fixture\n' for name in d.SOURCE_PATHS}; source[d.BUNDLE] = raw_bundle
    plan = d._plan(source_hashes={name: d._sha(raw) for name, raw in source.items()}, git_head='c' * 40,
        owner_instruction_sha256='a' * 64, created_utc=(now - timedelta(seconds=1)).isoformat(),
        expires_utc=(now + timedelta(hours=1)).isoformat(), read_operation_id='TPR-EXT26-UPLOAD-DIAG-SYNTHETIC-001',
        expected_manifest_sha256=d._sha(raw_manifest), mode='offline-fixture')
    root = tmp_path / 'private'; root.mkdir(mode=0o700)
    data = {'manifest.' + d.QC_OPERATION + '.json': raw_manifest}
    for index in range(2):
        row = body['inputs'][index]; prefix = 'input.' + row['sha256']; at = now.isoformat(); payload = f'{index + 101:064x}'
        data[prefix + '.read.spent.json'] = e.canonical({'at': at, 'name': row['name'], 'sha256': row['sha256'], 'manifest_sha256': d.MANIFEST_SHA256})
        data[prefix + '.upload.spent.json'] = e.canonical({'at': at, 'payload_sha256': payload, 'manifest_sha256': d.MANIFEST_SHA256})
        data[prefix + '.upload.transport.json'] = e.canonical({'at': at, 'endpoint': 'object/set'})
        request = 'request.' + f'{index + 3:04d}'
        data[request + '.spent.json'] = e.canonical({'at': at, 'endpoint': 'object/set', 'payload_sha256': payload, 'manifest_sha256': d.MANIFEST_SHA256})
        projection = e.project_wire(e.canonical({'success': False, 'errors': [{'errorCode': 413, 'message': 'Storage quota too large PRIVATE-TOKEN ACCOUNT-123'}]}
            if index == 1 and failed else {'success': True}))
        data[request + '.projection.json'] = e.canonical(projection)
        if index == 1 and failed:
            terminal = {'at': at, 'status': 'failed_or_unknown', 'automatic_retry': False}
        else:
            terminal = {'at': at, 'status': 'succeeded', **{key: projection[key] for key in ('original_wire_sha256', 'projection_sha256')}}
            data[prefix + '.completed.json'] = e.canonical({key: row[key] for key in ('sha256', 'key', 'bytes')})
        data[request + '.terminal.json'] = e.canonical(terminal)
    # OFF source/outcome projections are hostile fixtures and must never open.
    data['request.0005.spent.json'] = e.canonical({'at': now.isoformat(), 'endpoint': 'backtests/read', 'payload_sha256': 'f' * 64, 'manifest_sha256': d.MANIFEST_SHA256})
    data['request.0005.projection.json'] = b'LICENSED-OFF-OUTCOME-MUST-NOT-READ'
    data['request.0005.terminal.json'] = b'OFF-MUST-NOT-READ'
    for name, raw in data.items():
        (root / name).write_bytes(raw); (root / name).chmod(0o600)
    return plan, source, root, data, now, body


def execute(f):
    plan, source, root, _, now, _ = f
    return e.parse_json(d._execute(plan, source, root, clock=lambda: now, guard=lambda *_: None))


def test_completed_census_retains_failed_unknown_and_never_reads_off_or_payload(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); original = d._read; seen = []
    def reading(directory, name, **kw):
        assert (f[2] / (f[0]['read_operation_id'] + '.claim.spent.json')).is_file()
        assert name not in {'request.0005.projection.json', 'request.0005.terminal.json'} and not name.startswith('synthetic-')
        seen.append(name); return original(directory, name, **kw)
    monkeypatch.setattr(d, '_read', reading)
    before = dict(f[3]); result = execute(f)
    assert result['status'] == 'COMPLETED' and result['scope_spent'] is True
    census = result['census']; assert census['counts'] == {'completed': e.JsonNumber('1'), 'failed_or_unknown': e.JsonNumber('1'), 'unattempted': e.JsonNumber('70')}
    failed = census['inputs'][1]; assert failed['request_sequence'].fraction() == 4
    assert failed['error_classification']['classes'] == ['quota', 'size']
    assert failed['error_classification']['explicit_api_error_codes'] == [e.JsonNumber('413')]
    assert census['unrelated_spent_request_count'].fraction() == 1 and census['all_uploads_completed'] is False
    for name, raw in before.items(): assert (f[2] / name).read_bytes() == raw
    returned = e.canonical(result); assert b'PRIVATE-TOKEN' not in returned and b'ACCOUNT-123' not in returned and b'LICENSED-OFF' not in returned
    assert result['quantconnect_attempts'].fraction() == result['new_looks'].fraction() == 0
    assert sum(name.endswith('.spent.json') and name.startswith('request.') for name in seen) == 96
    with pytest.raises(FileExistsError): execute(f)


def test_two_completed_uploads_are_not_all_72_completed(tmp_path, monkeypatch):
    result = execute(fixture(tmp_path, monkeypatch, failed=False))
    assert result['census']['counts']['completed'].fraction() == 2
    assert result['census']['all_uploads_completed'] is False


@pytest.mark.parametrize('part', ['manifest', 'bundle', 'read_name', 'upload_manifest', 'transport', 'completed', 'payload', 'projection', 'wire', 'retry', 'future'])
def test_material_metadata_corruption_retains_spent_failed_diagnostic(tmp_path, monkeypatch, part):
    f = fixture(tmp_path, monkeypatch); plan, source, root, data, now, body = f
    first = 'input.' + body['inputs'][0]['sha256']; name = None
    if part == 'manifest': name = 'manifest.' + d.QC_OPERATION + '.json'; raw = data[name] + b' '
    elif part == 'bundle': source[d.BUNDLE] += b' '; plan['source_hashes'][d.BUNDLE] = d._sha(source[d.BUNDLE]); raw = None
    else:
        name = {'read_name': first + '.read.spent.json', 'upload_manifest': first + '.upload.spent.json',
            'transport': first + '.upload.transport.json', 'completed': first + '.completed.json',
            'payload': 'request.0003.spent.json', 'projection': 'request.0003.projection.json',
            'wire': 'request.0003.terminal.json', 'retry': 'request.0004.terminal.json', 'future': first + '.read.spent.json'}[part]
        value = e.parse_json(data[name])
        if part == 'read_name': value['name'] = 'foreign.json'
        if part == 'upload_manifest': value['manifest_sha256'] = 'f' * 64
        if part == 'transport': value['endpoint'] = 'files/update'
        if part == 'completed': value['bytes'] = e.JsonNumber('2')
        if part == 'payload': value['payload_sha256'] = 'e' * 64
        if part == 'projection': value['projection']['success'] = False
        if part == 'wire': value['original_wire_sha256'] = 'e' * 64
        if part == 'retry': value['automatic_retry'] = True
        if part == 'future': value['at'] = (now + timedelta(days=2)).isoformat()
        raw = e.canonical(value)
    if name: (root / name).write_bytes(raw)
    result = execute(f)
    assert result['status'] == 'FAILED_OR_UNCERTAIN' and result['scope_spent'] is True and result['census'] is None
    assert (root / (plan['read_operation_id'] + '.claim.spent.json')).is_file()


def test_missing_failed_terminal_is_unavailable_not_failed_or_success(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); (f[2] / 'request.0004.terminal.json').unlink()
    result = execute(f)
    assert result['census']['inputs'][1]['status'] == 'request_terminal_unavailable'
    assert result['census']['inputs'][1]['terminal_status'] is None


@pytest.mark.parametrize('kind', ['mode', 'symlink', 'hardlink', 'oversize'])
def test_private_metadata_custody_refuses_after_claim(tmp_path, monkeypatch, kind):
    f = fixture(tmp_path, monkeypatch); path = f[2] / 'request.0004.projection.json'
    if kind == 'mode': path.chmod(0o644)
    if kind == 'symlink':
        target = f[2] / 'target'; target.write_bytes(path.read_bytes()); target.chmod(0o600); path.unlink(); path.symlink_to(target)
    if kind == 'hardlink': os.link(path, f[2] / 'second-link')
    if kind == 'oversize':
        with path.open('ab') as stream: stream.truncate(d.MAX_FILE + 1)
    result = execute(f)
    assert result['status'] == 'FAILED_OR_UNCERTAIN' and result['scope_spent'] is True


def test_plan_independent_expected_manifest_and_24h_bounds(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); plan = f[0]
    args = {key: plan[key] for key in ('source_hashes', 'git_head', 'owner_instruction_sha256', 'created_utc', 'expires_utc', 'read_operation_id', 'expected_manifest_sha256', 'mode')}
    with pytest.raises(ValueError): d._plan(**{**args, 'expected_manifest_sha256': 'a' * 64})
    with pytest.raises(ValueError): d._plan(**{**args, 'expires_utc': (f[4] + timedelta(hours=25)).isoformat()})
    with pytest.raises(ValueError): d._plan(**{**args, 'read_operation_id': '../arbitrary'})
    with pytest.raises(ValueError): d._execute(plan, f[1], d.PRIVATE_ROOT, clock=lambda: f[4], guard=lambda *_: None)


def test_error_classification_never_echoes_unknown_text_or_arbitrary_ids():
    body = e.parse_json(e.canonical({'errors': ['secret account123 error unknown'], 'accountId': 123, 'rows': [{'code': 123}]}))
    answer = d._errors(body)
    assert answer['unknown_classification'] is True and answer['explicit_api_error_codes'] == []
    assert b'account123' not in e.canonical(answer)


def test_total_bound_refuses_before_reading_file_that_crosses_budget(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(d, 'MAX_TOTAL', len(f[3]['manifest.' + d.QC_OPERATION + '.json']) + 1)
    f[0]['max_total_bytes'] = d.MAX_TOTAL
    observed, original = [], d.os.read
    def reading(fd, amount):
        observed.append(amount)
        return original(fd, amount)
    monkeypatch.setattr(d.os, 'read', reading)
    answer = execute(f)
    assert answer['status'] == 'FAILED_OR_UNCERTAIN' and answer['scope_spent'] is True
    assert sum(observed) == len(f[3]['manifest.' + d.QC_OPERATION + '.json'])


def test_cli_refuses_without_private_error_text(monkeypatch, capsys):
    def refusal(**_kw): raise ValueError('PRIVATE-TOKEN ACCOUNT-123')
    monkeypatch.setattr(d, 'run', refusal)
    assert d.main(['--read-operation-id', 'TPR-EXT26-UPLOAD-DIAG-SYNTHETIC', '--owner-instruction-sha256', 'a' * 64,
        '--created-utc', '2026-10-10T00:00:00+00:00', '--expires-utc', '2026-10-10T01:00:00+00:00', '--expected-manifest-sha256', 'b' * 64]) == 1
    output = capsys.readouterr().out
    assert 'PRIVATE-TOKEN' not in output and 'ACCOUNT-123' not in output and 'REFUSED_OR_UNCERTAIN' in output
