"""Synthetic metadata only; actual roots, credentials and HTTPS are denied."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import os
import subprocess

import pytest
from research.target_price_revisions_qc import extended_store_probe as d

e = d.e


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    def deny(*_args, **_kwargs): raise AssertionError('actual private/network/credential/Git call forbidden')
    monkeypatch.setattr(d.http.client, 'HTTPSConnection', deny)
    monkeypatch.setattr(d.ops, 'credential', deny)
    monkeypatch.setattr(subprocess, 'run', deny)
    opening = d._open_directory
    def isolated(path):
        assert not path.is_relative_to(d.LANE)
        return opening(path)
    monkeypatch.setattr(d, '_open_directory', isolated)


def fixture(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    directory = 'tpr-ext26/inputs/' + e.STUDY_ID + '/' + 'b' * 64 + '/'
    originals, payloads = [], []
    for index in range(72):
        plain = hashlib.sha256(('synthetic-plain-' + str(index)).encode()).hexdigest()
        zipped = d.FIRST_GZIP_SHA256 if index == 0 else hashlib.sha256(('synthetic-gzip-' + str(index)).encode()).hexdigest()
        size = d.FIRST_GZIP_BYTES if index == 0 else 50 + index
        originals.append({'name': plain + '.json', 'sha256': plain, 'bytes': 400000 + index, 'key': directory + plain + '.json'})
        payloads.append({'plain_name': plain + '.json', 'plain_sha256': plain, 'plain_bytes': 400000 + index,
            'logical_key': directory + plain + '.json', 'gzip_sha256': zipped, 'gzip_bytes': size,
            'stored_name': 'gzip.' + zipped + '.json', 'stored_key': directory + 'gzip.' + zipped + '.json'})
    mapping = {'schema': 'tpr-ext26-gzip-input-map-v1', 'study_id': e.STUDY_ID, 'freeze_sha256': e.FREEZE_SHA256,
        'preparation_sha256': 'b' * 64, 'bundle_sha256': 'c' * 64,
        'processing_operation_id': 'TPR-EXT26-COMPRESS-SYNTHETIC-001', 'processing_plan_sha256': 'd' * 64,
        'encoding': 'gzip', 'gzip_level': 9, 'gzip_mtime': 0, 'payloads': payloads}
    files = {'compressed_packet.py': 'COMPRESSION_JSON = ' + repr(e.canonical(mapping).decode()) + '\n'}
    bundle = {'schema': 'tpr-ext26-source-bundle-v1', 'candidates': [{'candidate_id': d.ON, 'project_name': 'SYNTHETIC-OWN', 'files': files}],
        'inputs': originals, 'preparation_sha256': 'b' * 64, 'repository_sources': []}
    bundle_raw = e.canonical(bundle)
    monkeypatch.setattr(d.census, 'BUNDLE_SHA256', d._sha(bundle_raw))
    organization = 'SYNTHETIC-SECRET-ORGANIZATION'
    monkeypatch.setattr(d, 'ORGANIZATION_SHA256', d._sha(organization.encode()))
    sources = {name: b'# synthetic committed closure\n' for name in d.SOURCE_PATHS}; sources[d.BUNDLE] = bundle_raw
    plan = d._plan(source_hashes={name: d._sha(raw) for name, raw in sources.items()}, git_head='a' * 40,
        owner_instruction_sha256='e' * 64, created_utc=(now - timedelta(seconds=1)).isoformat(),
        expires_utc=(now + timedelta(hours=1)).isoformat(), operation_id='TPR-EXT26-STORE-PROBE-SYNTHETIC-001',
        bundle_raw=bundle_raw, mode='offline-fixture')
    root = tmp_path / 'metadata'; root.mkdir(mode=0o700)
    def save(name, value):
        (root / name).write_bytes(value if type(value) is bytes else e.canonical(value)); (root / name).chmod(0o600)
    project = {'candidate_id': d.ON, 'project_id': d.PROJECT_ID, 'name': 'SYNTHETIC-OWN',
        'organization_id': organization, 'owner': True}
    save(d.ON + '.project.json', project)
    listed = {'success': True, 'errors': [], 'path': directory, 'page': 1, 'totalPages': 1,
        'objects': [{'key': row['stored_key'], 'name': 'DO-NOT-RETURN-NAME', 'folder': False,
            'size': row['gzip_bytes'], 'mime': 'DO-NOT-RETURN-MIME'} for row in payloads[:2]],
        'objectStorageUsed': 999999, 'objectStorageUsedHuman': 'DO-NOT-RETURN-HUMAN'}
    properties = {'success': True, 'errors': [], 'metadata': {'key': payloads[0]['stored_key'],
        'size': d.FIRST_GZIP_BYTES, 'md5': 'a' * 32, 'modified': 'DO-NOT-RETURN-DATE'}}
    calls = []
    def transport(endpoint, raw):
        assert (root / (plan['operation_id'] + '.claim.spent.json')).is_file()
        assert (root / (plan['operation_id'] + '.request.' + str(len(calls) + 1) + '.spent.json')).is_file()
        payload = e.parse_json(raw); calls.append((endpoint, payload))
        expected = {'organizationId': organization,
            'path' if endpoint == 'object/list' else 'key': directory if endpoint == 'object/list' else payloads[0]['stored_key']}
        assert payload == expected
        return e.canonical(listed if endpoint == 'object/list' else properties), 200
    return {'now': now, 'plan': plan, 'sources': sources, 'root': root, 'save': save,
        'transport': transport, 'calls': calls, 'listed': listed, 'properties': properties,
        'project': project, 'organization': organization, 'payloads': payloads, 'bundle': bundle}


def execute(f, **kwargs):
    return e.parse_json(d._execute(f['plan'], f['sources'], f['root'], clock=lambda: f['now'],
        guard=kwargs.pop('guard', lambda *_: None), transport=kwargs.pop('transport', f['transport']), **kwargs))


def test_exact_two_claimed_routes_report_usage_without_inventing_capacity_or_content(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); answer = execute(f)
    assert answer['status'] == 'COMPLETED' and answer['scope_spent'] is True
    assert [row[0] for row in f['calls']] == ['object/list', 'object/properties']
    assert len(answer['requests']) == 2
    listed, properties = [row['safe_response'] for row in answer['requests']]
    assert listed['reported_object_storage_used'].fraction() == 999999
    assert listed['directory_census_complete'] is False
    assert listed['own_gzip_objects_on_page'].fraction() == 2
    assert properties['object_existence'] == 'present_metadata' and properties['size_matches'] is True
    assert properties['remote_md5'] == 'a' * 32 and properties['expected_md5'] is None
    for row in (answer, listed, properties):
        assert row['capacity_bytes'] is row['free_bytes'] is row['capacity_sufficient'] is row['other_lane_contention'] is None
    assert properties['md5_matches'] is None and properties['remote_content_verified'] is False
    assert answer['new_looks'].fraction() == answer['quantconnect_attempts'].fraction() == 0
    raw = e.canonical(answer)
    for secret in (f['organization'], 'SYNTHETIC-OWN', 'DO-NOT-RETURN-NAME', 'DO-NOT-RETURN-MIME',
                   'DO-NOT-RETURN-HUMAN', 'DO-NOT-RETURN-DATE', f['payloads'][0]['stored_key']):
        assert secret.encode() not in raw
    with pytest.raises(FileExistsError): execute(f)
    assert len(f['calls']) == 2


def test_claim_precedes_only_exact_project_metadata_read(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); original, reads = d._read, []
    def read(fd, name, **kwargs):
        assert (f['root'] / (f['plan']['operation_id'] + '.claim.spent.json')).is_file()
        assert name == d.ON + '.project.json' and kwargs['maximum'] == d.MAX_PROJECT
        reads.append(name); return original(fd, name, **kwargs)
    monkeypatch.setattr(d, '_read', read)
    assert execute(f)['status'] == 'COMPLETED' and reads == [d.ON + '.project.json']


@pytest.mark.parametrize('kind', ['organization', 'project', 'owner', 'candidate', 'name'])
def test_foreign_project_metadata_blocks_both_requests(tmp_path, monkeypatch, kind):
    f = fixture(tmp_path, monkeypatch)
    key, value = {'organization': ('organization_id', 'FOREIGN-SECRET'), 'project': ('project_id', 1),
        'owner': ('owner', False), 'candidate': ('candidate_id', 'FOREIGN'), 'name': ('name', 'FOREIGN')}[kind]
    f['project'][key] = value; f['save'](d.ON + '.project.json', f['project'])
    answer = execute(f)
    assert answer['status'] == 'FAILED_OR_UNCERTAIN' and answer['scope_spent'] is True and not f['calls']
    assert b'FOREIGN' not in e.canonical(answer)


@pytest.mark.parametrize('value', [True, -1, '100', 1.5])
def test_malformed_usage_does_not_become_free_capacity(tmp_path, monkeypatch, value):
    f = fixture(tmp_path, monkeypatch); f['listed']['objectStorageUsed'] = value
    answer = execute(f)
    assert answer['status'] == 'FAILED_OR_UNCERTAIN' and len(f['calls']) == 1
    assert answer['capacity_bytes'] is answer['free_bytes'] is None


@pytest.mark.parametrize('kind', ['foreign_path', 'foreign_key', 'duplicate_key', 'folder_child', 'size_bool', 'objects_string'])
def test_unrelated_or_malformed_listing_fails_without_echo_or_second_request(tmp_path, monkeypatch, kind):
    f = fixture(tmp_path, monkeypatch); row = f['listed']['objects'][0]
    if kind == 'foreign_path': f['listed']['path'] = 'UNRELATED-SECRET-PATH'
    if kind == 'foreign_key': row['key'] = 'UNRELATED-SECRET-PATH/unrelated.json'
    if kind == 'duplicate_key': f['listed']['objects'].append(deepcopy(row))
    if kind == 'folder_child': row.update(folder=True, key=f['plan']['targets']['directory'] + 'UNRELATED-DIR')
    if kind == 'size_bool': row['size'] = True
    if kind == 'objects_string': f['listed']['objects'] = 'UNRELATED-SECRET-ROW'
    answer = execute(f)
    assert answer['status'] == 'FAILED_OR_UNCERTAIN' and len(f['calls']) == 1
    assert b'UNRELATED' not in e.canonical(answer)


def test_multiple_pages_remain_incomplete_and_are_never_followed(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); f['listed']['totalPages'] = 3
    answer = execute(f)
    assert answer['status'] == 'COMPLETED' and len(f['calls']) == 2
    listed = answer['requests'][0]['safe_response']
    assert listed['directory_census_complete'] is False and listed['pagination_followed'] is False


def test_missing_usage_and_pagination_stay_unknown(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    for field in ('objectStorageUsed', 'page', 'totalPages'): f['listed'].pop(field)
    listed = execute(f)['requests'][0]['safe_response']
    assert listed['reported_object_storage_used'] is None and listed['directory_census_complete'] is False


@pytest.mark.parametrize('page,pages,usage', [(0, 0, 0), (0, 1, 1), (1, 1, 0)])
def test_exact_zero_usage_and_page_counts_are_observed_without_capacity_or_census_claim(tmp_path, monkeypatch, page, pages, usage):
    f = fixture(tmp_path, monkeypatch)
    f['listed'].update(page=page, totalPages=pages, objectStorageUsed=usage)
    answer = execute(f); listed = answer['requests'][0]['safe_response']
    assert answer['status'] == 'COMPLETED' and len(f['calls']) == 2
    assert listed['reported_page'].fraction() == page and listed['reported_total_pages'].fraction() == pages
    assert listed['reported_object_storage_used'].fraction() == usage
    assert listed['directory_census_complete'] is False and listed['pagination_followed'] is False
    assert listed['capacity_bytes'] is listed['free_bytes'] is listed['capacity_sufficient'] is None


@pytest.mark.parametrize('field', ['page', 'totalPages'])
@pytest.mark.parametrize('value', [True, -1, '0', 0.5])
def test_page_counts_reject_bool_negative_string_or_fraction_without_second_request(tmp_path, monkeypatch, field, value):
    f = fixture(tmp_path, monkeypatch); f['listed'][field] = value
    answer = execute(f)
    assert answer['status'] == 'FAILED_OR_UNCERTAIN' and len(f['calls']) == 1


def test_exact_zero_object_sizes_remain_metadata_not_content_verification(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    f['listed']['objects'][0]['size'] = 0; f['properties']['metadata']['size'] = 0
    answer = execute(f)
    assert answer['status'] == 'COMPLETED'
    properties = answer['requests'][1]['safe_response']
    assert properties['remote_bytes'].fraction() == 0
    assert properties['size_matches'] is False and properties['remote_content_verified'] is False


@pytest.mark.parametrize('value', [True, 0, '0', 0.0, -1, e.JsonNumber('-0'), e.JsonNumber('0.0'),
    e.JsonNumber('1.0'), e.JsonNumber('1e0'), e.JsonNumber('-1'), e.JsonNumber('9223372036854775808')])
def test_nonnegative_boundary_admits_only_bounded_native_integer_tokens(value):
    with pytest.raises(d.Refusal): d._nonnegative(value)


def test_nonnegative_boundary_accepts_zero_and_exact_maximum():
    assert d._nonnegative(e.JsonNumber('0')) == 0
    assert d._nonnegative(e.JsonNumber('9223372036854775807')) == 2**63 - 1
    with pytest.raises(d.Refusal): d._nonnegative(e.JsonNumber('10001'), 10000)


@pytest.mark.parametrize('kind', ['not_found', 'quota', 'http', 'unknown'])
def test_native_refusal_classifies_without_claiming_absence_or_capacity(tmp_path, monkeypatch, kind):
    f = fixture(tmp_path, monkeypatch)
    body = {'success': False, 'errors': ['SENSITIVE-ACCOUNT PRIVATE-ROW ' + {'not_found': 'key not found',
        'quota': 'storage quota exceeded', 'http': 'forbidden', 'unknown': 'unrecognized'}[kind]]}
    def transport(endpoint, raw):
        if endpoint == 'object/list': return f['transport'](endpoint, raw)
        assert (f['root'] / (f['plan']['operation_id'] + '.request.2.spent.json')).is_file()
        f['calls'].append((endpoint, e.parse_json(raw))); return e.canonical(body), 404 if kind == 'not_found' else 200
    answer = execute(f, transport=transport)
    properties = answer['requests'][1]['safe_response']
    assert answer['status'] == 'COMPLETED' and properties['object_existence'] == 'unknown'
    assert properties['remote_content_verified'] is False and properties['capacity_sufficient'] is None
    if kind == 'not_found':
        assert 'not_found' in properties['error_classification']['classes']
        assert properties['error_classification']['unknown_classification'] is False
    assert b'SENSITIVE-ACCOUNT' not in e.canonical(answer) and b'PRIVATE-ROW' not in e.canonical(answer)


def test_wrong_remote_size_is_an_observation_not_matching_content(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); f['properties']['metadata']['size'] -= 1
    properties = execute(f)['requests'][1]['safe_response']
    assert properties['size_matches'] is False and properties['remote_content_verified'] is False


@pytest.mark.parametrize('field,value', [('key', 'FOREIGN-KEY'), ('size', True), ('md5', 'bad-md5')])
def test_invalid_properties_are_never_admitted(tmp_path, monkeypatch, field, value):
    f = fixture(tmp_path, monkeypatch); f['properties']['metadata'][field] = value
    answer = execute(f)
    assert answer['status'] == 'FAILED_OR_UNCERTAIN' and len(f['calls']) == 2
    assert answer['requests'][1]['safe_response'] is None


def test_transport_exception_consumes_request_without_retry(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); calls = []
    def failing(endpoint, raw): calls.append(endpoint); raise OSError('SECRET-DO-NOT-RETURN')
    answer = execute(f, transport=failing)
    assert answer['status'] == 'FAILED_OR_UNCERTAIN' and calls == ['object/list']
    assert b'SECRET-DO-NOT-RETURN' not in e.canonical(answer)
    terminal = e.parse_json((f['root'] / (f['plan']['operation_id'] + '.request.1.terminal.json')).read_bytes())
    assert terminal['status'] == 'FAILED_OR_UNCERTAIN'


def test_response_byte_ceiling_precedes_parsing(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    answer = execute(f, transport=lambda *_: (b'X' * (d.MAX_RESPONSE + 1), 200))
    assert answer['status'] == 'FAILED_OR_UNCERTAIN' and len(answer['requests']) == 1


def test_private_file_ceiling_checked_before_body(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); f['save'](d.ON + '.project.json', b'X' * (d.MAX_PROJECT + 1))
    monkeypatch.setattr(os, 'read', lambda *_: pytest.fail('oversized private body was read'))
    assert execute(f)['status'] == 'FAILED_OR_UNCERTAIN' and not f['calls']


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'mode', 'directory_mode'])
def test_private_custody_refusal_precedes_transport(tmp_path, monkeypatch, kind):
    f = fixture(tmp_path, monkeypatch); path = f['root'] / (d.ON + '.project.json')
    if kind == 'symlink':
        original = f['root'] / 'synthetic-project.json'; path.rename(original); path.symlink_to(original)
    if kind == 'hardlink': os.link(path, f['root'] / 'synthetic-hardlink')
    if kind == 'mode': path.chmod(0o644)
    if kind == 'directory_mode': f['root'].chmod(0o755)
    if kind == 'directory_mode':
        with pytest.raises(d.Refusal): execute(f)
    else: assert execute(f)['status'] == 'FAILED_OR_UNCERTAIN'
    assert not f['calls']


@pytest.mark.parametrize('kind', ['expired', 'source', 'plan', 'duration', 'identifier'])
def test_bad_scope_refuses_before_private_open(tmp_path, monkeypatch, kind):
    f = fixture(tmp_path, monkeypatch)
    if kind == 'expired': f['now'] += timedelta(hours=2)
    if kind == 'source': f['sources'][next(name for name in f['sources'] if name != d.BUNDLE)] = b'# changed\n'
    if kind == 'plan': f['plan']['mutations'] = True
    if kind == 'duration': f['plan']['expires_utc'] = (f['now'] + timedelta(hours=5)).isoformat()
    if kind == 'identifier': f['plan']['operation_id'] = 'OLD-SPENT-OPERATION'
    monkeypatch.setattr(d, '_open_directory', lambda *_: pytest.fail('invalid scope opened metadata'))
    with pytest.raises(d.Refusal): execute(f)
    assert not f['calls']


def test_offline_fixture_cannot_target_actual_lane_root(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    with pytest.raises(d.Refusal):
        d._execute(f['plan'], f['sources'], d.PRIVATE_ROOT, clock=lambda: f['now'], guard=lambda *_: None, transport=f['transport'])


@pytest.mark.parametrize('endpoint', ['object/get', 'object/set', 'object/delete', 'projects/read', 'backtests/create'])
def test_forbidden_transport_route_refuses_before_credentials(endpoint):
    with pytest.raises(d.Refusal): d._transport(endpoint, b'{}')


def test_mutation_scope_has_no_effectful_routes():
    assert d.ENDPOINTS == frozenset({'object/list', 'object/properties'})
    assert d.MAX_REQUESTS == 2 and d.MAX_SECONDS == 120 and d.MAX_RESPONSE == 1024 * 1024
