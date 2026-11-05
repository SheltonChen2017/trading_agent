"""Six one-shot source-access observations, never a subscription/readiness grant.

No CLI and no access on import. The owner registers the exact committed code
manifest and protocol before run_registered. Account responses are never
persisted or hashed; only a closed, bounded projection may leave memory.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import re
import stat
import subprocess
import urllib.request

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts.qualify_finra_short_interest import (
    _NoRedirect, _prepare_capture_directory, _require_capture_platform,
)
from scripts.qualify_sharadar_companion import _guard, _http, SharadarCaptureRefusal
from scripts.short_interest_keychain import KeychainSecret, read_named_keychain
from scripts.continue_short_interest_native_identity import _OwnedOutput

ROOT = Path('/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest')
PARENT = Path('artifacts/short_interest/private/provider_access')
RUN_NAME = 'provider-access-20261024-v1'
CLAIM_NAME = RUN_NAME + '.spent.json'
MAXIMUM_BYTES = 65536
MAXIMUM_REQUESTS = 6
CODE_FILES = tuple(sorted((
    'data/__init__.py', 'data/exchange_calendar.py', 'data/financial_primitives.py', 'data/hashing.py',
    'ml/__init__.py', 'ml/immutable_io.py', 'research/__init__.py',
    'research/short_interest_etf/__init__.py', 'research/short_interest_etf/availability.py',
    'research/short_interest_etf/contracts.py', 'research/short_interest_etf/preregistration.py',
    'research/short_interest_etf/finra_source_qualification.py',
    'research/short_interest_etf/massive_action_supplement.py',
    'research/short_interest_etf/native_dated_identity.py',
    'research/short_interest_etf/native_population_class_matrix.py',
    'research/short_interest_etf/sharadar_actual_input_binding.py',
    'research/short_interest_etf/sharadar_companion_qualification.py',
    'research/short_interest_etf/sharadar_master_segments.py',
    'research/short_interest_etf/sharadar_native_master_index.py',
    'research/short_interest_etf/sharadar_native_observations.py',
    'research/short_interest_etf/sharadar_securities_master.py',
    'scripts/build_short_interest_native_master_offline.py',
    'scripts/capture_short_interest_native_identity.py',
    'scripts/capture_short_interest_native_population.py',
    'scripts/capture_short_interest_securities_master.py',
    'scripts/continue_short_interest_native_identity.py',
    'scripts/finalize_short_interest_master_offline.py',
    'scripts/load_short_interest_native_class_matrix.py',
    'scripts/qualify_finra_short_interest.py', 'scripts/qualify_sharadar_companion.py',
    'scripts/qualify_short_interest_action_supplement.py',
    'scripts/short_interest_keychain.py', 'scripts/audit_short_interest_provider_access.py',
)))
FEEDS = (
    'Bulk Splits and Dividends API', 'Fundamental Data', 'Bond Fundamentals API',
    'Stock Options Data', 'News API', 'commodities', 'sec_filings', 'id_mapping',
    'Technical API Data', 'Intraday Data API', 'EOD Historical Data', 'Search API',
    'dividends', 'Dividends Data Feed', 'Split Data Feed', 'Calendar Data',
    'Live (delayed) Data API', 'CBOE Data API', 'Real-time Data via WebSockets',
    'Economic Events API', 'Sentiment Data API', 'Tick Data', 'Exchanges List API',
)


class ProviderAccessRefusal(ValueError):
    """Only fixed local diagnostics; never provider/credential exception text."""


def require(value, code):
    if not value:
        raise ProviderAccessRefusal(code)


def protocol():
    return {
        'schema': 'si-provider-access-six-routes-v1', 'run_name': RUN_NAME, 'claim_name': CLAIM_NAME,
        'maximum_requests': 6, 'maximum_response_bytes': 65536, 'maximum_total_bytes': 393216,
        'maximum_invocations_per_route': 1, 'automatic_retries': 0, 'redirects': False, 'proxies': False,
        'timeout_seconds': 30, 'claim_before_any_key': True, 'restart_or_resumption_allowed': False,
        'routes': [
            {'id': 'sharadar-metadata', 'provider': 'sharadar', 'kind': 'catalog', 'header': 'x-api-key',
             'url': 'https://api.sharadar.com/v1.0/data/stocks?status=True&years=full'},
            {'id': 'eodhd-account', 'provider': 'eodhd', 'kind': 'account_projection', 'header': None,
             'url': 'https://eodhd.com/api/internal-user', 'query_authentication': 'fixed_keychain_request_only'},
            {'id': 'massive-types', 'provider': 'massive', 'kind': 'catalog', 'header': 'Authorization',
             'url': 'https://api.massive.com/v3/reference/tickers/types?asset_class=stocks&locale=us'},
            {'id': 'fmp-exchanges', 'provider': 'fmp', 'kind': 'catalog', 'header': 'apikey',
             'url': 'https://financialmodelingprep.com/stable/available-exchanges'},
            {'id': 'massive-dated-overview', 'provider': 'massive', 'kind': 'dated_source', 'header': 'Authorization',
             'url': 'https://api.massive.com/v3/reference/tickers/AAPL?date=2022-01-03'},
            {'id': 'fmp-dated-cap', 'provider': 'fmp', 'kind': 'dated_source', 'header': 'apikey',
             'url': 'https://financialmodelingprep.com/stable/historical-market-capitalization?symbol=AAPL&from=2022-01-03&to=2022-01-03&limit=1'},
        ],
        'account_storage': 'no_original_body_or_body_hash_only_allowlisted_projection',
        'response_privacy': 'all_loaded_keys_raw_and_every_decoded_string_before_body_hash_or_publication',
        'account_known_feeds': list(FEEDS), 'key_failure': 'retain_negative_continue_independent_routes_no_fallback',
        'code_manifest': list(CODE_FILES),
        'limits': ['catalog_200_not_paid_entitlement', 'dated_row_not_complete_history',
                   'dated_overview_not_publication_aware', 'provider_account_assertion_not_licensing_proof'],
        'source_admitted': False, 'point_in_time_data': False, 'ready_for_backtest': False,
        'outcome_looks': 0, 'qc_access': False, 'trading_authority': False,
    }


def _clock(value):
    require(type(value) is str and value.endswith(('Z', '+00:00')), 'UTC_clock_required')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ProviderAccessRefusal('UTC_clock_required') from None
    require(result.tzinfo is not None and result.utcoffset().total_seconds() == 0, 'UTC_clock_required')
    return result


def _now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _json(raw, secrets):
    require(type(raw) is bytes and 0 < len(raw) <= MAXIMUM_BYTES, 'response_size_or_type_refused')
    require(all(not secret.echoed_in(raw) for secret in secrets), 'credential_echo_refused')
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'duplicate_JSON_key_refused')
            value[key] = item
        return value
    def invalid(unused):
        raise ProviderAccessRefusal('nonfinite_JSON_refused')
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_float=Decimal, parse_constant=invalid)
    except (ValueError, UnicodeError, RecursionError):
        raise ProviderAccessRefusal('JSON_contract_refused') from None
    nodes = [value]
    count = 0
    while nodes:
        item = nodes.pop(); count += 1
        require(count <= 20000, 'JSON_node_limit')
        if type(item) is str:
            try:
                text = item.encode('utf-8')
            except UnicodeError:
                raise ProviderAccessRefusal('JSON_string_encoding_refused') from None
            require(all(not secret.echoed_in(text) for secret in secrets), 'credential_echo_refused')
        elif type(item) is dict:
            nodes.extend(item.keys()); nodes.extend(item.values())
        elif type(item) is list:
            nodes.extend(item)
        elif type(item) in (int, Decimal):
            if type(item) is Decimal:
                require(item.is_finite() and abs(item.adjusted()) <= 4096, 'JSON_numeric_bound')
                text = format(item, 'f').encode('ascii')
            else:
                text = str(item).encode('ascii')
            require(all(not secret.echoed_in(text) for secret in secrets), 'credential_echo_refused')
        else:
            require(item is None or type(item) is bool, 'JSON_scalar_refused')
    return value


def _quota(value):
    if type(value) is str and re.fullmatch(r'0|[1-9][0-9]{0,11}', value):
        value = int(value)
    require(type(value) is int and 0 <= value <= 10 ** 12, 'account_quota_refused')
    return value


def account_projection(value):
    """No identity/contact/payment/token or unknown strings leave this function."""
    require(type(value) is dict, 'account_object_required')
    result = {'provider_assertions_only': True, 'expiry_verified': False, 'licensing_verified': False}
    observed = 0
    for name, allowed in (('subscriptionType', {'monthly', 'yearly', 'free'}),
                          ('subscriptionMode', {'paid', 'free', 'trial', 'demo'})):
        if name in value:
            observed += 1
            require(type(value[name]) is str and len(value[name]) <= 128, 'account_subscription_shape')
            result[name] = value[name] if value[name] in allowed else 'unrecognized_value_redacted'
    for name in ('apiRequests', 'dailyRateLimit', 'extraLimit'):
        if name in value:
            observed += 1; result[name] = _quota(value[name])
    if 'apiRequestsDate' in value:
        text = value['apiRequestsDate']
        require(type(text) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}', text), 'account_quota_date_refused')
        try:
            require(date.fromisoformat(text).isoformat() == text, 'account_quota_date_refused')
        except ValueError:
            raise ProviderAccessRefusal('account_quota_date_refused') from None
        result['apiRequestsDate'] = text
    if 'availableDataFeeds' in value:
        observed += 1; feeds = value['availableDataFeeds']
        require(type(feeds) is list and len(feeds) <= 128 and all(type(item) is str and len(item) <= 256 for item in feeds),
                'account_feed_shape_refused')
        result['documented_feeds'] = {name: name in feeds for name in FEEDS}
        result['unknown_feed_count'] = sum(item not in FEEDS for item in feeds)
    require(observed > 0, 'account_supported_projection_missing')
    return result


def _observe(route, value):
    route_id = route['id']
    base = {'request_completed_with_runtime_credential': True, 'credential_validity_independently_verified': False,
            'paid_tier_verified': False, 'full_history_verified': False,
            'point_in_time_verified': False, 'source_admitted': False, 'ready_for_backtest': False}
    if route_id == 'eodhd-account':
        return dict(base, observation='account_assertion_only', account=account_projection(value))
    if route_id == 'sharadar-metadata':
        require(type(value) is dict and value.get('table') == 'stocks'
                and ('files' in value or 'name' in value), 'metadata_schema_refused')
    elif route_id == 'massive-types':
        require(type(value) is dict and value.get('status') == 'OK' and type(value.get('results')) is list
                and bool(value['results']), 'metadata_schema_refused')
    elif route_id == 'fmp-exchanges':
        require(type(value) is list and 0 < len(value) <= 1000 and all(type(item) is dict for item in value),
                'metadata_schema_refused')
    elif route_id == 'massive-dated-overview':
        require(type(value) is dict and value.get('status') == 'OK' and type(value.get('results')) is dict
                and value['results'].get('ticker') == 'AAPL', 'dated_source_schema_refused')
    elif route_id == 'fmp-dated-cap':
        require(type(value) is list and len(value) <= 1, 'dated_source_schema_refused')
        if not value:
            return dict(base, observation='empty_exact_date_no_coverage')
        require(type(value[0]) is dict and value[0].get('symbol') == 'AAPL'
                and value[0].get('date') == '2022-01-03'
                and type(value[0].get('marketCap')) in (int, Decimal)
                and value[0]['marketCap'] > 0, 'dated_source_schema_refused')
    else:
        raise ProviderAccessRefusal('unknown_fixed_route')
    return dict(base, observation='catalog_access_only' if route['kind'] == 'catalog' else 'single_dated_source_only')


def _request(route, secret):
    if route['id'] == 'eodhd-account':
        return secret.eodhd_internal_user_request()
    token = secret.for_authorization_header()
    return urllib.request.Request(route['url'], method='GET', headers={
        'Accept': 'application/json', route['header']: ('Bearer ' + token if route['provider'] == 'massive' else token)})


def _capture(*, check, claim, publish, read_secret, transport, clock, registration):
    """Test seam; operational composition below supplies every fixed boundary."""
    frozen = canonical_json(protocol()); routes = json.loads(frozen)['routes']
    def boundary():
        require(canonical_json(protocol()) == frozen, 'prospective_scope_changed')
        check()
    def store(name, value):
        boundary(); publish(name, value); boundary()
    boundary()
    began = clock(); _clock(began)
    claim({'schema': 'si-provider-access-spent-v1', 'protocol_sha256': hash_bytes(frozen.encode()),
           'registration': registration, 'started_at': began, 'maximum_requests': 6,
           'maximum_total_bytes': 393216, 'restart_or_resumption_allowed': False})
    boundary()
    secrets, key_status = {}, {}
    for provider in ('sharadar', 'eodhd', 'massive', 'fmp'):
        boundary()
        try:
            secret = read_secret(provider)
            require(type(secret) is KeychainSecret, 'exact_key_type_required')
            secrets[provider] = secret; key_status[provider] = 'available'
        except Exception:
            key_status[provider] = 'unavailable_no_fallback'
        boundary()
    store('keys.private.json', {'schema': 'si-provider-key-availability-v1', 'providers': key_status})
    results, invocations, charged, starts = [], 0, 0, 0
    latest = _clock(began)
    for ordinal, route in enumerate(routes, 1):
        boundary()
        started = clock(); require(latest <= _clock(started), 'request_clock_backwards'); latest = _clock(started)
        prefix = f'route-{ordinal:02d}'
        result = {'route': route['id'], 'ordinal': ordinal, 'http_invoked': False, 'http_status': None,
                  'charged_bytes': 0, 'started_at': started, 'source_admitted': False}
        if route['provider'] not in secrets:
            result.update(code='credential_unavailable_no_HTTP', observation='unknown')
            store(prefix + '.refused.json', result); results.append(result); continue
        starts += 1
        store(prefix + '.started.json', {'schema': 'si-provider-access-start-v1', 'route': route['id'],
              'ordinal': ordinal, 'start_debit': starts, 'started_at': started,
              'maximum_response_bytes_reserved': MAXIMUM_BYTES, 'registration': registration})
        secret = secrets[route['provider']]
        raw = None; status = None
        try:
            boundary()
            request = _request(route, secret)
            require(invocations < 6, 'fixed_request_budget')
            invocations += 1; result['http_invoked'] = True
            raw, media, status = transport(request, MAXIMUM_BYTES)
            boundary()
            require(type(status) is int and status == 200 and type(media) is str and len(media) <= 256,
                    'HTTP_or_media_refused')
            require(all(not item.echoed_in(media.encode('utf-8')) for item in secrets.values()), 'credential_echo_refused')
            require(media.split(';', 1)[0].strip().lower() == 'application/json', 'JSON_media_required')
            value = _json(raw, tuple(secrets.values()))
            observation = _observe(route, value)
            # A boundary precedes both original body hashing and publication.
            boundary()
            if route['kind'] != 'account_projection':
                digest = hash_bytes(raw)
                store(prefix + '.raw', raw)
                result.update(raw_sha256=digest, raw_bytes=len(raw))
            result.update(code='received', http_status=200, charged_bytes=len(raw), **observation)
        except Exception as error:
            if type(error) is SharadarCaptureRefusal:
                status = error.http_status
            result.update(code='source_access_refused', observation='unknown',
                          http_status=status if type(status) is int and 100 <= status <= 599 else None,
                          charged_bytes=MAXIMUM_BYTES if result['http_invoked'] else 0)
        received = clock(); require(latest <= _clock(received), 'receipt_clock_backwards'); latest = _clock(received)
        result['received_at'] = received
        charged += result['charged_bytes']
        require(charged <= 6 * MAXIMUM_BYTES, 'fixed_byte_budget')
        store(prefix + ('.received.json' if result['code'] == 'received' else '.refused.json'), result)
        results.append(result)
    inventory = {'schema': 'si-provider-access-inventory-v1', 'protocol_sha256': hash_bytes(frozen.encode()),
                 'registration': registration, 'routes_considered': len(results), 'start_debits': starts,
                 'http_invocations': invocations, 'charged_bytes': charged, 'results': results,
                 'all_routes_observed': all(item['code'] == 'received' for item in results),
                 'source_admitted': False, 'ready_for_backtest': False, 'outcome_looks': 0, 'qc_access': False}
    store('inventory.private.json', inventory)
    boundary()
    store('closed.json', {'schema': 'si-provider-access-closed-v1', 'registration': registration,
          'http_invocations': invocations, 'all_routes_observed': inventory['all_routes_observed'],
          'source_admitted': False, 'ready_for_backtest': False, 'outcome_looks': 0, 'qc_access': False})
    return inventory


def _prepared_capture(directory, *, check, registration, read_secret, transport, clock):
    with _OwnedOutput(directory, check) as owned:
        def claim(value):
            owned.publish(CLAIM_NAME, (canonical_json(value) + '\n').encode(), parent=True)
        def publish(name, value):
            raw = value if type(value) is bytes else (canonical_json(value) + '\n').encode()
            owned.publish(name, raw)
        return _capture(check=owned.check, claim=claim, publish=publish, read_secret=read_secret,
                        transport=transport, clock=clock, registration=registration)


def run_registered(*, head, remote, code_manifest, expected_protocol_sha256):
    """Root-only operation after prospective commit; stable claim prevents rerun."""
    _require_capture_platform()
    require(all(type(value) is str and re.fullmatch(r'[0-9a-f]{40}', value) for value in (head, remote)),
            'exact_committed_registration_required')
    require(type(code_manifest) is dict and tuple(sorted(code_manifest)) == CODE_FILES
            and all(type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value) for value in code_manifest.values()),
            'complete_current_code_manifest_required')
    pins = tuple(sorted(code_manifest.items()))
    require(expected_protocol_sha256 == hash_payload(protocol()), 'prospective_protocol_pin_required')
    def check():
        require(ROOT == Path.cwd().resolve() and ROOT == Path(__file__).resolve().parents[1], 'designated_root_required')
        _guard(ROOT, head, remote)
        require(hash_payload(protocol()) == expected_protocol_sha256, 'prospective_protocol_changed')
        for name, digest in pins:
            path = ROOT / name
            require(path.resolve() == path and stat.S_ISREG(path.lstat().st_mode), 'current_code_path_refused')
            raw = path.read_bytes()
            require(hash_bytes(raw) == digest, 'current_code_changed')
            blob = subprocess.run(['git', 'show', head + ':' + name], cwd=ROOT, capture_output=True, check=False)
            require(blob.returncode == 0 and hash_bytes(blob.stdout) == digest, 'uncommitted_code_refused')
        _guard(ROOT, head, remote)
    check()
    ignore = subprocess.run(['git', 'check-ignore', '--quiet', str(ROOT / PARENT / RUN_NAME)],
                            cwd=ROOT, capture_output=True, check=False)
    require(ignore.returncode == 0, 'private_ignored_output_required')
    directory = _prepare_capture_directory(ROOT / PARENT / RUN_NAME)
    registration = {'head': head, 'remote': remote, 'code_manifest_sha256': hash_payload(dict(pins))}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    return _prepared_capture(directory, check=check, registration=registration, read_secret=read_named_keychain,
                             transport=lambda request, maximum: _http(opener, request, maximum), clock=_now)
