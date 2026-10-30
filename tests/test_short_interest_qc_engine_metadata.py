"""Fabricated endpoint contracts only: no environment secrets or network."""
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace as NS
import urllib.error
import urllib.request

import pytest

from data.hashing import canonical_json, hash_bytes
from scripts import read_short_interest_qc_engine_metadata as m

# Only protected-I/O cases require POSIX; pure parsing, transport and early
# refusal checks must remain active on the supported Windows host.
_POSIX_CAPTURE_ONLY = pytest.mark.skipif(
    not hasattr(os, "getuid"),
    reason=(
        "the protected-capture runtime requires POSIX ownership and mode "
        "semantics (os.getuid, O_NOFOLLOW, 0o600/0o700, symlinks); it cannot "
        "execute on this host, see the lane record SI-CR17-002"
    ),
)

USER = '918273645'
TOKEN = 'fabricated-only-token-abcdef0123456789'
STAMP = 1234567890


def version(id=1, created='2023-01-03T14:30:00Z', public=True, **changes):
    row = {'id': id, 'created': created, 'description': 'catalog description omitted from output',
           'leanHash': 'a' * 40, 'leanCloudHash': 'b' * 40, 'name': 'master',
           'ref': 'refs/heads/master', 'public': public}
    row.update(changes)
    return row


def response(rows=None, **changes):
    value = {'versions': [version()] if rows is None else rows, 'success': True, 'errors': []}
    value.update(changes)
    return json.dumps(value).encode()


def frozen():
    return {'protocol': m.metadata_protocol(), 'source_sha256': 'c' * 64,
            'decision_id': 'SI-DEC-FAKE-METADATA-01',
            'registered_head': 'a' * 40, 'registered_remote': 'b' * 40}


def directory(tmp_path):
    path = tmp_path / 'fixed-budget'
    path.mkdir(mode=0o700)
    return path


def run(path, raw=None, *, credentials=None, transport=None, guard=None, registration=None):
    return m.capture_one(path, frozen=frozen() if registration is None else registration,
        guard=lambda: None if guard is None else guard(),
        credential_reader=(lambda: (USER, TOKEN)) if credentials is None else credentials,
        transport=(lambda _request: response() if raw is None else raw) if transport is None else transport,
        timestamp=STAMP)


def test_protocol_is_data_free_one_fixed_read_without_project_node_or_automatic_authenticate():
    p = m.metadata_protocol()
    assert p['fixed_endpoint'] == 'https://www.quantconnect.com/api/v2/lean/versions/read'
    assert p['method'] == 'POST' and p['body'] == {} and p['maximum_requests'] == 1
    assert p['automatic_retries'] == 0 and p['projects_nodes_history_upload_compile_jobs_backtests'] is False
    assert p['selection_is_execution_pin'] is False


@_POSIX_CAPTURE_ONLY
def test_exclusive_durable_claim_precedes_credentials_and_wire_and_blocks_restart(tmp_path):
    path = directory(tmp_path)
    trace = []
    def credentials():
        claim = json.loads((path / m.CLAIM).read_bytes())
        assert claim['claimed_requests'] == 1 and claim['resumption_or_restart_allowed'] is False
        assert claim['frozen_registration'] == frozen()
        trace.append('credentials')
        return USER, TOKEN
    def transport(request):
        assert trace == ['credentials']
        trace.append('wire')
        assert request.full_url == m.ENDPOINT and request.data == b'{}'
        return response()
    result = run(path, credentials=credentials, transport=transport)
    assert trace == ['credentials', 'wire'] and result['body_observed'] is True
    with pytest.raises(m.MetadataRefusal, match='request_budget_consumed'):
        run(path, credentials=lambda: pytest.fail('repeat must not read secrets'))
    assert trace == ['credentials', 'wire']


@pytest.mark.parametrize('stage', ['credentials', 'wire', 'changed_scope'])
@_POSIX_CAPTURE_ONLY
def test_failure_spends_budget_and_never_records_arbitrary_exception_detail(tmp_path, stage):
    path = directory(tmp_path)
    def boom():
        raise RuntimeError(TOKEN + USER)
    guard_count = 0
    def guard():
        nonlocal guard_count
        guard_count += 1
        if stage == 'changed_scope' and guard_count == 2:
            boom()
    with pytest.raises(m.MetadataRefusal) as error:
        run(path, credentials=boom if stage == 'credentials' else None,
            transport=(lambda _request: boom()) if stage == 'wire' else None, guard=guard)
    assert TOKEN not in str(error.value) and USER not in str(error.value)
    if stage == 'changed_scope':
        assert error.value.code == 'scope_changed'
    refused = (path / 'refused.json').read_bytes()
    assert TOKEN.encode() not in refused and USER.encode() not in refused
    assert not (path / 'response.raw.json').exists()
    with pytest.raises(m.MetadataRefusal, match='request_budget_consumed'):
        run(path)


@_POSIX_CAPTURE_ONLY
def test_ephemeral_wire_authentication_matches_primary_documented_signature_not_receipt(tmp_path):
    path = directory(tmp_path)
    def wire(request):
        signature = hashlib.sha256(f'{TOKEN}:{STAMP}'.encode()).hexdigest()
        basic = base64.b64encode(f'{USER}:{signature}'.encode()).decode()
        assert request.get_header('Authorization') == 'Basic ' + basic
        assert request.get_header('Timestamp') == str(STAMP)
        return response()
    run(path, transport=wire)
    for p in path.iterdir():
        raw = p.read_bytes()
        assert all(v.encode() not in raw for v in (USER, TOKEN,
            hashlib.sha256(f'{TOKEN}:{STAMP}'.encode()).hexdigest()))
        info = p.lstat()
        assert stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1 and info.st_uid == os.getuid()


@pytest.mark.parametrize('kind', ['token', 'unicode_token', 'signature', 'basic', 'header', 'encoded_token', 'user'])
@_POSIX_CAPTURE_ONLY
def test_secret_echo_is_discarded_before_any_raw_or_public_receipt(tmp_path, kind):
    path = directory(tmp_path)
    _request, markers = m.authenticated_request((USER, TOKEN), STAMP)
    text = {'token': TOKEN, 'unicode_token': TOKEN, 'signature': markers[2],
            'basic': markers[3], 'header': markers[4],
            'encoded_token': base64.b64encode(TOKEN.encode()).decode(), 'user': USER}[kind]
    raw = response([version(description=text)])
    if kind == 'unicode_token':
        raw = raw.replace(TOKEN.encode(), ''.join(f'\\u{ord(c):04x}' for c in TOKEN).encode())
    with pytest.raises(m.MetadataRefusal, match='credential_echo_discarded'):
        run(path, raw)
    assert not (path / 'response.raw.json').exists() and not (path / 'public-observation.json').exists()
    refusal = json.loads((path / 'refused.json').read_bytes())
    assert refusal['body_observed'] is True and refusal['raw_response_write_started'] is False


@_POSIX_CAPTURE_ONLY
def test_protected_raw_mixed_catalog_kept_but_public_output_omits_nonpublic_description(tmp_path):
    path = directory(tmp_path)
    raw = response([version(7, public=False, name='private-branch'), version(3),
                    version(5, created='2023-02-01T00:00:00.000Z')])
    result = run(path, raw)
    assert (path / 'response.raw.json').read_bytes() == raw
    assert result['raw_response_sha256'] == hash_bytes(raw)
    assert result['selected'] == {k: version(5, created='2023-02-01T00:00:00.000Z')[k] for k in m.PUBLIC_FIELDS}
    public = canonical_json(result)
    assert 'private-branch' not in public and 'description' not in public
    assert result['public_version_count'] == 2 and result['runtime_or_wrapper_proof'] is False


def test_selection_latest_created_then_highest_id_is_order_independent():
    rows = [version(6), version(4), version(9, created='2022-01-01T00:00:00Z'), version(10, public=False)]
    selected = m.select_public_metadata(json.loads(response(rows)))
    assert selected['selected']['id'] == 6
    assert m.select_public_metadata(json.loads(response(list(reversed(rows))))) == selected


@pytest.mark.parametrize('raw', [
    b'not JSON', b'{"success":true,"success":false,"errors":[],"versions":[]}',
    response(success=False), response(errors=['private error']),
    response(accountId='private'), response([version(id=True)]),
    response([version(leanHash='not a commit')]), response([version(leanCloudHash='a' * 64)]),
    response([version(created='2023-01-03T14:30:00')]), response([version(public=1)]),
    response([version(name='email@example.com')]), response([version(), version()]),
    response([version(public=False)]), response([]), response([version(userId='private')]),
])
@_POSIX_CAPTURE_ONLY
def test_unqualified_response_never_persisted_or_reported_as_public_metadata(tmp_path, raw):
    path = directory(tmp_path)
    with pytest.raises(m.MetadataRefusal):
        run(path, raw)
    assert not (path / 'response.raw.json').exists()
    assert json.loads((path / 'refused.json').read_bytes())['body_observed'] is True


@pytest.mark.parametrize('fault', ['directory_mode', 'symlink', 'claim_symlink', 'claim_hardlink'])
@_POSIX_CAPTURE_ONLY
def test_storage_protection_and_exclusive_claim_fail_before_secret_read(tmp_path, fault):
    path = directory(tmp_path)
    if fault == 'directory_mode':
        path.chmod(0o755)
    elif fault == 'symlink':
        alias = tmp_path / 'link'; alias.symlink_to(path); path = alias
    else:
        outside = tmp_path / 'unrelated'; outside.write_bytes(b'untouched')
        if fault == 'claim_symlink':
            (path / m.CLAIM).symlink_to(outside)
        else:
            os.link(outside, path / m.CLAIM)
    with pytest.raises(m.MetadataRefusal):
        run(path, credentials=lambda: pytest.fail('protection before secrets'))
    if fault.startswith('claim_'):
        assert outside.read_bytes() == b'untouched'


def test_wire_fixed_request_no_proxy_no_redirect_no_error_detail_and_no_retry(monkeypatch):
    class Opener:
        calls = 0
        def open(self, request, timeout):
            self.calls += 1
            raise urllib.error.HTTPError('https://private.invalid/?key=' + TOKEN,
                403, TOKEN, {'Authorization': USER}, None)
    opener = Opener()
    handlers = []
    monkeypatch.setattr(m.urllib.request, 'build_opener', lambda *h: handlers.extend(h) or opener)
    request, _ = m.authenticated_request((USER, TOKEN), STAMP)
    with pytest.raises(m.MetadataRefusal, match='wire_request_refused') as error:
        m.wire_read(request)
    assert str(error.value) == 'REFUSED: wire_request_refused' and opener.calls == 1
    assert isinstance(handlers[0], urllib.request.ProxyHandler) and handlers[0].proxies == {}
    assert isinstance(handlers[1], m._NoRedirect)
    for forbidden in ('https://other.invalid/', m.ENDPOINT + '?x=1'):
        with pytest.raises(m.MetadataRefusal):
            m.wire_read(urllib.request.Request(forbidden, data=b'{}', method='POST'))
    assert opener.calls == 1


@pytest.mark.parametrize('user,token', [('0', TOKEN), ('x', TOKEN), (USER, 'short'), (USER, TOKEN + '\n')])
def test_named_environment_only_credential_shape(monkeypatch, user, token):
    monkeypatch.setenv('QC_USER_ID', user); monkeypatch.setenv('QC_API_TOKEN', token)
    with pytest.raises(m.MetadataRefusal, match='named_credentials_unavailable'):
        m.named_credentials()


@pytest.mark.parametrize('fault', ['changed_url', 'status', 'oversized'])
def test_success_wire_is_still_fixed_bounded_and_failed_body_is_not_persisted(monkeypatch, fault):
    class Reply:
        status = 201 if fault == 'status' else 200
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def geturl(self): return m.ENDPOINT + '/redirected' if fault == 'changed_url' else m.ENDPOINT
        def read(self, maximum):
            assert maximum == m.MAX_BYTES + 1
            return b'x' * maximum if fault == 'oversized' else response()
    monkeypatch.setattr(m.urllib.request, 'build_opener', lambda *_args: NS(open=lambda *_a, **_k: Reply()))
    request, _ = m.authenticated_request((USER, TOKEN), STAMP)
    with pytest.raises(m.MetadataRefusal, match='wire_request_refused'):
        m.wire_read(request)


@_POSIX_CAPTURE_ONLY
def test_public_receipt_failure_does_not_claim_clean_observed_raw_was_absent(tmp_path):
    path = directory(tmp_path)
    (path / 'public-observation.json').write_bytes(b'preexisting unrelated output')
    with pytest.raises(m.MetadataRefusal, match='protected_storage_refused'):
        run(path)
    refused = json.loads((path / 'refused.json').read_bytes())
    assert refused['body_observed'] is True and refused['raw_response_persisted'] is True
    assert (path / 'response.raw.json').read_bytes() == response()
    assert (path / 'public-observation.json').read_bytes() == b'preexisting unrelated output'


def test_unregistered_protocol_refuses_before_storage_claim_and_credentials(tmp_path):
    path = directory(tmp_path)
    registration = frozen(); registration['protocol']['maximum_requests'] = 2
    with pytest.raises(m.MetadataRefusal, match='protocol_refused'):
        run(path, registration=registration, credentials=lambda: pytest.fail('no secret access'))
    assert tuple(path.iterdir()) == ()
