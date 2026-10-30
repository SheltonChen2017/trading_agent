"""Fabricated access responses only; all real sockets/Keychain calls denied."""
from datetime import datetime, timedelta, timezone
import json
import socket
from urllib.parse import parse_qs, urlsplit

import pytest

from scripts import audit_short_interest_provider_access as access
from scripts import short_interest_keychain as keys
from scripts.qualify_sharadar_companion import SharadarCaptureRefusal
import os

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


@pytest.fixture(autouse=True)
def no_external_access(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail('real network/Keychain is forbidden in focused tests')
    monkeypatch.setattr(socket, 'create_connection', denied)
    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(keys, 'read_named_keychain', denied)
    monkeypatch.setattr(access, 'read_named_keychain', denied)


class Harness:
    def __init__(self, tmp_path):
        self.root = tmp_path
        self.saved, self.requests, self.reads, self.events = {}, [], [], []
        self.tick = 0
        self.bodies = [
            {'table': 'stocks', 'name': 'stocks_full.zip'},
            {'name': 'PRIVATE PERSON', 'email': 'private@example.invalid', 'inviteToken': 'PRIVATE-INVITE',
             'paymentMethod': 'PRIVATE-PAYMENT', 'subscriptionMode': 'paid', 'subscriptionType': 'monthly',
             'availableDataFeeds': ['EOD Historical Data', 'PRIVATE-UNKNOWN-FEED'],
             'apiRequests': '3', 'dailyRateLimit': 100000, 'extraLimit': '0', 'apiRequestsDate': '2026-10-24'},
            {'status': 'OK', 'results': [{'code': 'CS', 'asset_class': 'stocks', 'locale': 'us'}]},
            [{'exchange': 'NASDAQ', 'name': 'Nasdaq'}],
            {'status': 'OK', 'results': {'ticker': 'AAPL', 'share_class_shares_outstanding': 123}},
            [{'symbol': 'AAPL', 'date': '2022-01-03', 'marketCap': 123456}],
        ]

    def clock(self):
        self.tick += 1
        return (datetime(2026, 10, 24, tzinfo=timezone.utc) + timedelta(seconds=self.tick)).isoformat()

    def check(self):
        self.events.append('check')

    def claim(self, value):
        self.events.append('claim')
        with (self.root / access.CLAIM_NAME).open('xb') as output:
            output.write(json.dumps(value).encode())

    def read(self, provider):
        self.events.append('key'); self.reads.append(provider)
        return keys.KeychainSecret('fictional-' + provider + '-credential')

    def publish(self, name, value):
        assert name not in self.saved
        self.saved[name] = value if type(value) is bytes else json.loads(json.dumps(value))

    def transport(self, request, maximum):
        self.events.append('HTTP'); self.requests.append(request)
        assert maximum == 65536
        value = self.bodies[len(self.requests) - 1]
        if isinstance(value, BaseException):
            raise value
        return value if type(value) is tuple else (json.dumps(value).encode(), 'application/json', 200)

    def run(self, **changes):
        args = dict(check=self.check, claim=self.claim, publish=self.publish, read_secret=self.read,
                    transport=self.transport, clock=self.clock, registration={'head': 'a' * 40, 'remote': 'b' * 40})
        args.update(changes)
        return access._capture(**args)


def test_six_exact_routes_caps_and_no_readiness(tmp_path):
    h = Harness(tmp_path); result = h.run()
    assert result['routes_considered'] == result['start_debits'] == result['http_invocations'] == 6
    assert h.reads == ['sharadar', 'eodhd', 'massive', 'fmp']
    assert h.events.index('claim') < h.events.index('key') < h.events.index('HTTP')
    assert all(item['paid_tier_verified'] is False and item['full_history_verified'] is False
               and item['point_in_time_verified'] is False for item in result['results'])
    assert not result['source_admitted'] and not result['ready_for_backtest'] and result['outcome_looks'] == 0
    routes = access.protocol()['routes']
    for n, request in enumerate(h.requests):
        assert request.get_method() == 'GET'
        if n != 1:
            assert request.full_url == routes[n]['url']
            assert 'fictional-' not in request.full_url
    assert h.requests[0].get_header('X-api-key') == 'fictional-sharadar-credential'
    assert h.requests[2].get_header('Authorization') == 'Bearer fictional-massive-credential'
    assert h.requests[3].get_header('Apikey') == 'fictional-fmp-credential'


def test_eodhd_exact_builder_no_general_target_or_secret_stringification():
    secret = keys.KeychainSecret('fictional&token?with=reserved')
    request = secret.eodhd_internal_user_request()
    parsed = urlsplit(request.full_url)
    assert parsed.scheme == 'https' and parsed.netloc == 'eodhd.com' and parsed.path == '/api/internal-user'
    assert parse_qs(parsed.query) == {'api_token': ['fictional&token?with=reserved'], 'fmt': ['json']}
    assert 'fictional' not in repr(secret) + str(secret) + repr(request)
    with pytest.raises(TypeError):
        secret.eodhd_internal_user_request('https://evil.invalid')


def test_account_original_never_hashed_or_persisted(tmp_path, monkeypatch):
    h = Harness(tmp_path); original = json.dumps(h.bodies[1]).encode()
    real = access.hash_bytes
    def checked(raw):
        assert raw != original and b'PRIVATE PERSON' not in raw and b'private@example.invalid' not in raw
        return real(raw)
    monkeypatch.setattr(access, 'hash_bytes', checked)
    result = h.run()
    assert 'route-02.raw' not in h.saved and 'raw_sha256' not in result['results'][1]
    rendered = repr(h.saved)
    assert all(token not in rendered for token in ('PRIVATE', 'private@example.invalid', 'fictional-'))
    projection = result['results'][1]['account']
    assert projection['documented_feeds']['EOD Historical Data'] and projection['unknown_feed_count'] == 1
    assert projection['dailyRateLimit'] == 100000 and projection['apiRequests'] == 3
    assert not projection['expiry_verified'] and not projection['licensing_verified']


@_POSIX_CAPTURE_ONLY
def test_stable_claim_blocks_second_run_before_key_even_changed_registration(tmp_path):
    h = Harness(tmp_path); directory = tmp_path / 'capture'; directory.mkdir(mode=0o700)
    access._prepared_capture(directory, check=lambda: None, registration={'head': 'a' * 40},
                             read_secret=h.read, transport=h.transport, clock=h.clock)
    reads = list(h.reads); requests = len(h.requests)
    with pytest.raises(FileExistsError):
        access._prepared_capture(directory, check=lambda: None, registration={'head': 'b' * 40},
                                 read_secret=h.read, transport=h.transport, clock=h.clock)
    assert h.reads == reads and len(h.requests) == requests


def test_missing_key_continues_independent_routes_without_fallback(tmp_path):
    h = Harness(tmp_path)
    def read(provider):
        if provider == 'massive':
            h.reads.append(provider); raise RuntimeError('private OS diagnostic')
        return h.read(provider)
    # Feed remaining independent routes in actual transport order.
    h.bodies = [h.bodies[n] for n in (0, 1, 3, 5)]
    result = h.run(read_secret=read)
    assert result['http_invocations'] == result['start_debits'] == 4
    assert h.reads.count('massive') == 1
    assert [item['code'] for item in result['results']][2:5:2] == ['credential_unavailable_no_HTTP'] * 2
    assert 'private OS' not in repr(h.saved)


@pytest.mark.parametrize('body', [
    b'{"table":"stocks","name":"fictional-sharadar-credential"}',
    b'{"table":"stocks","name":"fictional%2Dsharadar%2Dcredential"}',
    b'{"table":"stocks","name":"fictional\\u002dsharadar\\u002dcredential"}',
    b'{"table":"stocks","name":"fictional-fmp-credential"}',
])
def test_secret_echo_rejected_before_body_hash_or_publication(tmp_path, monkeypatch, body):
    h = Harness(tmp_path); h.bodies[0] = (body, 'application/json', 200)
    real = access.hash_bytes
    def checked(raw):
        assert raw != body
        return real(raw)
    monkeypatch.setattr(access, 'hash_bytes', checked)
    result = h.run()
    assert result['results'][0]['code'] == 'source_access_refused'
    assert 'route-01.raw' not in h.saved and len(h.requests) == 6
    assert result['results'][0]['charged_bytes'] == 65536


@pytest.mark.parametrize('failure,status', [(RuntimeError('https://private/?token=SECRET'), None),
                                         (SharadarCaptureRefusal('secret body', status=403), 403)])
def test_unknown_or_explicit_failure_is_negative_and_not_retried(tmp_path, failure, status):
    h = Harness(tmp_path); h.bodies[0] = failure; result = h.run()
    assert result['http_invocations'] == 6 and not result['all_routes_observed']
    assert result['results'][0]['http_status'] == status and result['results'][0]['observation'] == 'unknown'
    assert result['results'][0]['charged_bytes'] == 65536
    assert 'SECRET' not in repr(h.saved) and 'secret body' not in repr(h.saved)


@pytest.mark.parametrize('body', [b'{}', b'{"a":NaN}', b'{"table":"stocks","table":"stocks"}',
                                 b' ' * 65537, b'{"x":"\\ud800"}'],
                         # Short ids: pytest exports the node id through PYTEST_CURRENT_TEST, and a
                         # 65,537-byte id exceeds the 32,767-character environment limit on Windows.
                         ids=['empty', 'nan', 'duplicate-key', '65537-spaces', 'lone-surrogate'])
def test_malformed_or_large_body_never_stored(tmp_path, body):
    h = Harness(tmp_path); h.bodies[0] = (body, 'application/json', 200)
    result = h.run()
    assert result['results'][0]['code'] == 'source_access_refused' and 'route-01.raw' not in h.saved


def test_empty_historical_result_is_not_coverage(tmp_path):
    h = Harness(tmp_path); h.bodies[5] = []; result = h.run()
    assert result['results'][5]['observation'] == 'empty_exact_date_no_coverage'
    assert not result['results'][5]['full_history_verified']


def test_out_of_date_or_extra_cap_rows_refused(tmp_path):
    h = Harness(tmp_path); h.bodies[5][0]['date'] = '2022-01-04'; result = h.run()
    assert result['results'][5]['code'] == 'source_access_refused'
    assert 'route-06.raw' not in h.saved


@_POSIX_CAPTURE_ONLY
def test_registration_requires_complete_manifest_before_any_side_effect(monkeypatch):
    monkeypatch.setattr(access, '_prepare_capture_directory', lambda *a: pytest.fail('must not create output'))
    with pytest.raises(access.ProviderAccessRefusal, match='complete_current_code_manifest'):
        access.run_registered(head='a' * 40, remote='b' * 40, code_manifest={}, expected_protocol_sha256='a' * 64)


def test_no_automatic_network_in_tests_and_closed_fixed_budget():
    value = access.protocol()
    assert value['maximum_requests'] == len(value['routes']) == 6 and value['maximum_total_bytes'] == 393216
    assert value['automatic_retries'] == 0 and value['redirects'] is value['proxies'] is False
    value['routes'][0]['url'] = 'https://evil.invalid'
    assert access.protocol()['routes'][0]['url'].startswith('https://api.sharadar.com/')


def test_exponent_encoded_numeric_secret_refuses_before_any_hash():
    with pytest.raises(access.ProviderAccessRefusal, match='credential_echo'):
        access._json(b'{"value":1.23456789e8}', (keys.KeychainSecret('123456789'),))


@_POSIX_CAPTURE_ONLY
def test_replaced_owned_output_cannot_receive_a_private_payload(tmp_path):
    directory = tmp_path / 'capture'; directory.mkdir(mode=0o700)
    h = Harness(tmp_path)
    def replace_on_key(provider):
        if provider == 'sharadar':
            directory.rename(tmp_path / 'original-capture')
            directory.mkdir(mode=0o700)
        return h.read(provider)
    with pytest.raises(ValueError, match='inode_changed'):
        access._prepared_capture(directory, check=lambda: None, registration={}, read_secret=replace_on_key,
                                 transport=h.transport, clock=h.clock)
    assert not list(directory.iterdir()) and not h.requests
