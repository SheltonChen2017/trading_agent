"""Prospective full-range Massive SI source inventory, not a strategy look.

All tickers, including delisted-source rows, remain captured. A complete page
chain is provider-covered inventory, never universal coverage or PIT evidence.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request

from data.hashing import hash_bytes, hash_payload
from scripts.qualify_finra_short_interest import (
    CaptureRefusal, _NoRedirect, _git, _prepare_capture_directory, _publish,
    _publish_json, _require_capture_platform, _unique_object,
)
from scripts.qualify_sharadar_companion import _guard, _http, _utc_now
from scripts.qualify_short_interest_action_supplement import _clock, _protected_bytes
from scripts.short_interest_keychain import KeychainSecret, ShortInterestKeychainError

ENDPOINT = 'https://api.massive.com/stocks/v1/short-interest'
PARAMS = {'settlement_date.gte': '2022-01-01', 'settlement_date.lte': '2026-08-31',
          'limit': '50000', 'sort': 'settlement_date.asc,ticker.asc'}
MAXIMUM_PAGES = 32
MAXIMUM_BYTES = 32 * 1024 * 1024
PARENT = Path('artifacts/short_interest/native_population')
CODE_FILES = ('data/hashing.py', 'ml/immutable_io.py', 'scripts/qualify_finra_short_interest.py',
              'scripts/qualify_sharadar_companion.py', 'scripts/qualify_short_interest_action_supplement.py',
              'scripts/short_interest_keychain.py', 'scripts/capture_short_interest_native_population.py')
PRIOR_REFUSAL = PARENT / 'native-population-20261013T233128Z'
PRIOR_PROTOCOL = 'f01bfeb383b6879468507f90d2b6ded073402427a934cff52ca2ca569c0ed72a'
PRIOR_HEAD = '3784f4f8779b4a8a14aed109b6a9cb8354126dd7'
PRIOR_BUDGET_SHA256 = '15a4c75a6af5f003753e6c6624c075d34647558fea30aa8e90bef410032e928d'
PRIOR_BYTES = {
    'protocol.json': 'e47c01ae6a6ccf880727fde8f7be3199f82882bb46e83055d34f0ac74935b705',
    'started.json': '0137c0aba2c7bc874e4db8ba78eb19fa95fd81a63f490a3304d62e132a776b09',
    'refused.json': '65cadbc9129840ba9b0abee5aa2cb0fed56946f4e44b9975e7413b4066ad223a',
}


class NativePopulationCaptureError(CaptureRefusal):
    pass


def protocol():
    return {'schema': 'si-native-population-capture-protocol-v1', 'endpoint': ENDPOINT,
            'initial_query': dict(PARAMS), 'population': 'all_reported_tickers_no_ticker_filter',
            'maximum_pages': MAXIMUM_PAGES, 'maximum_response_bytes': MAXIMUM_BYTES,
            'authentication': 'explicit_known_MASSIVE_API_KEY_after_verified_zero_HTTP_Keychain_refusal_header_only',
            'previous_failed_claim': {'run': PRIOR_REFUSAL.as_posix(), 'head': PRIOR_HEAD,
                                     'protocol_sha256': PRIOR_PROTOCOL, 'file_byte_pins': dict(PRIOR_BYTES),
                                     'budget_bytes_sha256': PRIOR_BUDGET_SHA256,
                                     'HTTP_attempts': 0, 'old_claim_retained_not_reset': True},
            'continuation': 'exact_received_fixed_origin_path_cursor_no_secret_query',
            'automatic_retries': 0, 'restart_or_resume': False, 'proxies': False, 'redirects': False,
            'source_kind': 'latest_revised_SI_not_daily_short_volume',
            'publication': 'protected_private_complete_raw_pages_and_chain',
            'outcome_looks': 0, 'qc_attempts': 0, 'ready_for_empirical_backtest': False}


PROTOCOL_SHA256 = '845ea39d5d3d16d7e852f33abc91d33796363207b32f4655ad5aa7eae30e4683'


def _require(condition, reason):
    if not condition:
        raise NativePopulationCaptureError(reason)


def _credential(root, *, head, remote):
    """Explicit documented alternate, never an automatic secret search."""
    _guard(root, head, remote)
    directory = root / PRIOR_REFUSAL
    _require({path.name for path in directory.iterdir()} == set(PRIOR_BYTES),
             'prior_Keychain_refusal_inventory_changed')
    receipts = {}
    for name, digest in PRIOR_BYTES.items():
        _guard(root, head, remote)
        raw = _protected_bytes(directory / name, 65536)
        _require(hash_bytes(raw) == digest, 'prior_Keychain_refusal_bytes_changed')
        receipts[name] = _json(raw)
    start, refused, old_protocol = receipts['started.json'], receipts['refused.json'], receipts['protocol.json']
    _require(hash_payload(old_protocol) == PRIOR_PROTOCOL and start.get('code_head') == PRIOR_HEAD
             and start.get('protocol_sha256') == PRIOR_PROTOCOL
             and refused.get('status') == 'source_capture_refused'
             and _clock(start['started_at']) <= _clock(refused['refused_at']),
             'prior_zero_HTTP_refusal_binding')
    _guard(root, head, remote)
    raw_budget = _protected_bytes(directory.parent / ('budget-' + PRIOR_PROTOCOL + '.json'), 65536)
    _require(hash_bytes(raw_budget) == PRIOR_BUDGET_SHA256, 'prior_consumed_claim_bytes_changed')
    budget = _json(raw_budget)
    _require(budget == {'schema': 'si-native-population-budget-v1', 'code_head': PRIOR_HEAD,
             'remote_head': start['remote_head'], 'run_id': directory.name, 'protocol_sha256': PRIOR_PROTOCOL,
             'maximum_attempts': 32, 'started_at': start['started_at'], 'restart_or_resume': False},
             'prior_consumed_claim_changed')
    _guard(root, head, remote)
    value = os.environ.get('MASSIVE_API_KEY')
    _require(type(value) is str and bool(value), 'known_MASSIVE_API_KEY_unavailable')
    return KeychainSecret(value)


def _next_url(value):
    _require(type(value) is str and len(value) <= 16384, 'pagination_URL_shape')
    parsed = urllib.parse.urlsplit(value)
    _require(parsed.scheme == 'https' and parsed.netloc == 'api.massive.com'
             and parsed.path == '/stocks/v1/short-interest' and not parsed.fragment,
             'pagination_URL_origin_or_path')
    pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    _require(pairs and len({k for k, _ in pairs}) == len(pairs), 'pagination_query_duplicates')
    query = dict(pairs)
    _require(set(query) <= set(PARAMS) | {'cursor'} and 'cursor' in query
             and 1 <= len(query['cursor']) <= 8192
             and all(33 <= ord(c) <= 126 for c in query['cursor']), 'pagination_cursor_or_secret_query')
    _require(all(k not in query or query[k] == v for k, v in PARAMS.items()),
             'pagination_scope_changed')
    return value


def _json(raw):
    def constant(value):
        raise NativePopulationCaptureError('nonfinite_source_JSON')
    try:
        return json.loads(raw.decode('utf-8'), parse_float=Decimal,
                          parse_constant=constant, object_pairs_hook=_unique_object)
    except (UnicodeError, json.JSONDecodeError):
        raise NativePopulationCaptureError('source_JSON_refused') from None


def capture_pages(root, directory, opener, secret, *, head, remote, started_at):
    _require_capture_platform()
    _require(hash_payload(protocol()) == PROTOCOL_SHA256, 'prospective_capture_protocol_pending_or_changed')
    _require(type(secret) is KeychainSecret, 'exact_redacted_Keychain_credential_required')
    url = ENDPOINT + '?' + urllib.parse.urlencode(PARAMS)
    seen, pages, previous = set(), [], _clock(started_at)

    def publish(name, value, raw=False):
        _guard(root, head, remote)
        (_publish if raw else _publish_json)(directory, name, value)

    for ordinal in range(1, MAXIMUM_PAGES + 1):
        _require(hash_payload(protocol()) == PROTOCOL_SHA256, 'prospective_capture_protocol_changed')
        _require(url not in seen, 'pagination_cycle')
        seen.add(url)
        prefix = f'page-{ordinal:02d}'
        descriptor = {'method': 'GET', 'url': url, 'authentication': 'Bearer_header_not_recorded'}
        digest = hash_payload(descriptor)
        began = _utc_now()
        _require(previous <= _clock(began), 'request_chronology')
        publish(prefix + '.started.json', {'schema': 'si-native-population-page-start-v1',
                'ordinal': ordinal, 'request': descriptor, 'request_sha256': digest,
                'protocol_sha256': PROTOCOL_SHA256, 'code_head': head, 'started_at': began})
        status = None
        try:
            _guard(root, head, remote)
            request = urllib.request.Request(url, method='GET', headers={
                'Accept': 'application/json', 'Authorization': 'Bearer ' + secret.for_authorization_header()})
            raw, media, status = _http(opener, request, MAXIMUM_BYTES)
            _require(type(raw) is bytes and len(raw) <= MAXIMUM_BYTES
                     and type(media) is str and len(media) <= 4096,
                     'response_size_or_types_refused')
            _require(not secret.echoed_in(raw) and not secret.echoed_in(media.encode()), 'credential_echo_refused')
            received = _utc_now()
            _require(_clock(began) <= _clock(received), 'response_chronology')
            publish(prefix + '.raw', raw, raw=True)
            receipt = {'schema': 'si-native-population-page-received-v1', 'ordinal': ordinal,
                       'request_sha256': digest, 'http_status': status, 'content_type': media,
                       'raw_path': prefix + '.raw', 'raw_sha256': hash_bytes(raw),
                       'raw_bytes': len(raw), 'received_at': received}
            publish(prefix + '.received.json', receipt)
            _require(status == 200 and media.split(';', 1)[0].strip().lower() == 'application/json',
                     'response_HTTP_or_media_refused')
            payload = _json(raw)
            _require(type(payload) is dict and payload.get('status') == 'OK'
                     and type(payload.get('results')) is list
                     and len(payload['results']) <= 50000, 'source_page_contract')
            next_url = payload.get('next_url')
            _require(next_url is None or type(next_url) is str, 'pagination_URL_shape')
            if next_url is not None:
                next_url = _next_url(next_url)
            pages.append({'ordinal': ordinal, 'request': descriptor, 'receipt': receipt,
                          'row_count': len(payload['results']), 'next_url': next_url})
            previous = _clock(received)
            if next_url is None:
                break
            _require(ordinal < MAXIMUM_PAGES, 'whole_population_page_budget_exhausted')
            url = next_url
        except (CaptureRefusal, ValueError, TypeError, OSError, KeyError) as error:
            publish(prefix + '.refused.json', {'schema': 'si-native-population-page-refusal-v1',
                    'ordinal': ordinal, 'code': str(error) if type(error) is NativePopulationCaptureError
                    else 'source_page_refused', 'http_status': status, 'refused_at': _utc_now()})
            raise
    retrieved_at = _utc_now()
    _require(hash_payload(protocol()) == PROTOCOL_SHA256, 'prospective_capture_protocol_changed')
    _require(previous <= _clock(retrieved_at), 'report_chronology')
    report = {'schema': 'si-native-population-inventory-v1', 'protocol_sha256': PROTOCOL_SHA256,
              'code_head': head, 'retrieved_at': retrieved_at, 'pages': pages,
              'complete_advertised_page_chain': True, 'scope': 'reported_provider_population_not_US_universe',
              'source_latest_revised': True, 'point_in_time_data': False,
              'original_vintages_or_availability_admitted': False, 'signal_or_return_computed': False,
              'outcome_looks': 0, 'qc_attempts': 0, 'ready_for_empirical_backtest': False}
    report['report_sha256'] = hash_payload(report)
    publish('population.private.json', report)
    finished = _utc_now()
    _require(_clock(retrieved_at) <= _clock(finished), 'completion_chronology')
    result = {'schema': 'si-native-population-completion-v1', 'status': 'source_capture_complete',
              'code_head': head, 'protocol_sha256': PROTOCOL_SHA256, 'http_attempts': len(pages),
              'private_report_sha256': report['report_sha256'], 'completed_at': finished,
              'outcome_looks': 0, 'qc_attempts': 0, 'backtest_result_exists': False}
    publish('completed.json', result)
    return result


def run(root, *, head, remote):
    _require_capture_platform()
    _guard(root, head, remote)
    _require(hash_payload(protocol()) == PROTOCOL_SHA256, 'prospective_capture_protocol_pending_or_changed')
    began = _utc_now()
    target = root / PARENT / ('native-population-' + _clock(began).strftime('%Y%m%dT%H%M%SZ'))
    _require(_git(root, 'check-ignore', str(target)) == str(target), 'population_capture_not_ignored')
    directory = _prepare_capture_directory(target)

    def publish(owner, name, value):
        _guard(root, head, remote)
        _publish_json(owner, name, value)

    try:
        publish(directory.parent, 'budget-' + PROTOCOL_SHA256 + '.json', {
            'schema': 'si-native-population-budget-v1', 'code_head': head, 'remote_head': remote,
            'run_id': directory.name, 'protocol_sha256': PROTOCOL_SHA256,
            'maximum_attempts': MAXIMUM_PAGES, 'started_at': began, 'restart_or_resume': False})
        publish(directory, 'protocol.json', protocol())
        files = []
        for name in CODE_FILES:
            _guard(root, head, remote)
            files.append({'path': name, 'sha256': hash_bytes((root / name).read_bytes())})
        identity = hash_payload({'git_commit': head, 'files': files})
        publish(directory, 'started.json', {'schema': 'si-native-population-start-v1',
            'code_head': head, 'remote_head': remote, 'code_identity_sha256': identity,
            'protocol_sha256': PROTOCOL_SHA256, 'started_at': began,
            'maximum_attempts': MAXIMUM_PAGES, 'outcome_looks': 0, 'qc_attempts': 0})
        _guard(root, head, remote)
        secret = _credential(root, head=head, remote=remote)
        _guard(root, head, remote)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        return capture_pages(root, directory, opener, secret, head=head, remote=remote, started_at=began)
    except (CaptureRefusal, ShortInterestKeychainError, ValueError, TypeError, OSError, KeyError):
        publish(directory, 'refused.json', {'schema': 'si-native-population-refusal-v1',
            'status': 'source_capture_refused', 'refused_at': _utc_now(), 'outcome_looks': 0,
            'qc_attempts': 0, 'backtest_result_exists': False})
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--expected-remote', required=True)
    args = parser.parse_args(argv)
    try:
        result = run(Path.cwd().resolve(), head=args.expected_head, remote=args.expected_remote)
    except (CaptureRefusal, ShortInterestKeychainError, ValueError, TypeError, OSError, KeyError) as error:
        result = {'status': 'source_capture_refused', 'code': str(error) if type(error) in
                  (NativePopulationCaptureError, ShortInterestKeychainError) else 'local_or_source_contract_refused',
                  'outcome_looks': 0, 'qc_attempts': 0, 'backtest_result_exists': False}
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
