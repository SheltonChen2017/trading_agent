"""One prospectively frozen continuation of the retained 32-page SI inventory.

The previous claim and all original bytes remain immutable. This is private
source custody only: no outcome, price, strategy, coverage or PIT admission.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import subprocess
import urllib.parse
import urllib.request

from data.hashing import canonical_json, hash_bytes, hash_payload
import scripts.capture_short_interest_native_population as original
from scripts.qualify_finra_short_interest import (
    CaptureRefusal, _NoRedirect, _git, _prepare_capture_directory, _publish,
    _publish_json, _require_capture_platform,
)
from scripts.qualify_sharadar_companion import _guard, _http, _utc_now
from scripts.qualify_short_interest_action_supplement import _clock, _protected_bytes
from scripts.short_interest_keychain import KeychainSecret, ShortInterestKeychainError

SOURCE = original.PARENT / 'native-population-20261013T233820Z'
SOURCE_HEAD = '69ad639b8fde268e2272db214e2120a6d8af4b8b'
SOURCE_REMOTE = '1f90c626328a236c51e78f57e0fe301e0412aabf'
SOURCE_PROTOCOL = '845ea39d5d3d16d7e852f33abc91d33796363207b32f4655ad5aa7eae30e4683'
SOURCE_INVENTORY_SHA256 = 'f666b32dccf9eb913fa8d371e4ccb75fbcbbae289323a13aecf29ddb0078abb8'
SOURCE_BUDGET_SHA256 = '6a3b9281127c1a2dc3e0478077f758211e59aedfe22c1534fd69390b259bd673'
SOURCE_CURSOR_SHA256 = '0f406a3ef8f6c2a6ecb91f51d5bf8169414ba75a73609892f165dc78fb20b361'
SOURCE_CODE_IDENTITY = '86a608e1ef526042e633744816ec2728fed088de6b270c75a4df54d087e43bc0'
SOURCE_STARTED_AT = '2026-10-13T23:38:20.797117Z'
OLD_PAGES = 32
ADDITIONAL_PAGES = 64
MAXIMUM_BYTES = 32 * 1024 * 1024
ENDPOINT = 'https://api.massive.com/stocks/v1/short-interest'
PARAMS = {'settlement_date.gte': '2022-01-01', 'settlement_date.lte': '2026-08-31',
          'limit': '50000', 'sort': 'settlement_date.asc,ticker.asc'}
PARENT = Path('artifacts/short_interest/native_population_continuation')
CODE_FILES = original.CODE_FILES + ('scripts/continue_short_interest_native_population.py',
    'research/short_interest_etf/native_population_class_matrix.py',
    'research/short_interest_etf/contracts.py')
EXPECTED_PROTOCOL_SHA256 = 'dca838952e3d991b1e98cfb334383c57dda2fcda1cc74eabc1db303de83545c1'


class PopulationContinuationRefusal(CaptureRefusal):
    pass


def _require(value, code):
    if not value:
        raise PopulationContinuationRefusal(code)


def _same(left, right, code):
    _require(canonical_json(left) == canonical_json(right), code)


def protocol():
    return {'schema': 'si-native-population-continuation-protocol-v1',
            'parent_source': {'run': str(SOURCE), 'head': SOURCE_HEAD, 'remote': SOURCE_REMOTE,
                'protocol_sha256': SOURCE_PROTOCOL, 'inventory_sha256': SOURCE_INVENTORY_SHA256,
                'budget_bytes_sha256': SOURCE_BUDGET_SHA256,
                'last_next_url_sha256': SOURCE_CURSOR_SHA256,
                'code_identity_sha256': SOURCE_CODE_IDENTITY, 'started_at': SOURCE_STARTED_AT},
            'endpoint': ENDPOINT, 'initial_query': dict(PARAMS), 'old_spent_attempts': OLD_PAGES,
            'maximum_additional_attempts': ADDITIONAL_PAGES, 'maximum_total_attempts': OLD_PAGES + ADDITIONAL_PAGES,
            'maximum_response_bytes': MAXIMUM_BYTES, 'initial_request': 'exact_retained_last_cursor_only',
            'authentication': 'known_MASSIVE_API_KEY_environment_fixed_HTTPS_Bearer_header_only',
            'claim_identity': 'original_parent_inventory_and_cursor_never_timestamp_or_code_head',
            'automatic_retries': 0, 'restart_or_resume': False, 'redirects': False, 'proxies': False,
            'publication': 'private_compact_original_references_no_raw_parent_copy',
            'source_kind': 'latest_revised_SI_not_daily_short_volume', 'outcome_looks': 0,
            'qc_attempts': 0, 'ready_for_empirical_backtest': False}


def claim_sha256():
    # Policy/head/time changes must not reopen this one continuation allowance.
    return hash_payload({'schema': 'si-native-population-continuation-claim-v1',
                         'parent_inventory_sha256': SOURCE_INVENTORY_SHA256,
                         'last_next_url_sha256': SOURCE_CURSOR_SHA256})


def _policy():
    _require(hash_payload(protocol()) == EXPECTED_PROTOCOL_SHA256,
             'prospective_continuation_protocol_pending_or_changed')


def _read(root, path, *, head, remote, maximum=MAXIMUM_BYTES):
    _require_capture_platform()
    _guard(root, head, remote)
    return _protected_bytes(path, maximum)


def _historical_identity(root, commit, files, *, head, remote):
    _require_capture_platform()
    _guard(root, head, remote)
    _require(type(commit) is str and len(commit) == 40
             and all(c in '0123456789abcdef' for c in commit), 'historical_source_head')
    result = subprocess.run(['git', 'merge-base', '--is-ancestor', commit, head],
                            cwd=root, capture_output=True, check=False)
    _require(result.returncode == 0, 'historical_source_not_lane_ancestor')
    bindings = []
    for name in files:
        _guard(root, head, remote)
        result = subprocess.run(['git', 'show', commit + ':' + name], cwd=root,
                                capture_output=True, check=False)
        _require(result.returncode == 0 and type(result.stdout) is bytes, 'historical_source_code_blob')
        bindings.append({'path': name, 'sha256': hash_bytes(result.stdout)})
    return hash_payload({'git_commit': commit, 'files': bindings})


def _descriptor(url):
    return {'method': 'GET', 'url': url, 'authentication': 'Bearer_header_not_recorded'}


def _next_url(value):
    _require(type(value) is str and len(value) <= 16384, 'pagination_URL_shape')
    parsed = urllib.parse.urlsplit(value)
    _require(parsed.scheme == 'https' and parsed.netloc == 'api.massive.com'
             and parsed.path == '/stocks/v1/short-interest' and not parsed.fragment,
             'pagination_URL_origin_or_path')
    pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    _require(pairs and len({key for key, _ in pairs}) == len(pairs), 'pagination_query_duplicates')
    query = dict(pairs)
    _require(set(query) <= set(PARAMS) | {'cursor'} and 'cursor' in query
             and 1 <= len(query['cursor']) <= 8192
             and all(33 <= ord(c) <= 126 for c in query['cursor']), 'pagination_cursor_or_secret_query')
    _require(all(key not in query or query[key] == value for key, value in PARAMS.items()),
             'pagination_scope_changed')
    return value


def _page(raw):
    payload = original._json(raw)
    _require(type(payload) is dict and payload.get('status') == 'OK'
             and type(payload.get('results')) is list and len(payload['results']) <= 50000,
             'source_page_contract')
    following = payload.get('next_url')
    _require(following is None or type(following) is str, 'pagination_URL_shape')
    return len(payload['results']), None if following is None else _next_url(following)


@dataclass(frozen=True, slots=True, init=False)
class ParentPopulation:
    metadata_json: str = field(repr=False)
    next_url: str = field(repr=False)
    refused_at: str
    _seal: object = field(repr=False)
    _anchor: tuple = field(repr=False)
    _anchor_identity: tuple = field(repr=False)

    def __init__(self):
        raise PopulationContinuationRefusal('protected_parent_factory_required')

    def _bound(self):
        _require(type(self) is ParentPopulation and self._seal is _PARENT_SEAL
                 and self._anchor is self._anchor_identity
                 and self.metadata_json is self._anchor[0]
                 and self.next_url is self._anchor[1] and self.refused_at is self._anchor[2],
                 'protected_parent_replay_changed')

    def pages(self):
        self._bound()
        return json.loads(self.metadata_json)


_PARENT_SEAL = object()


def _parent_population(metadata_json, next_url, refused_at):
    obj = object.__new__(ParentPopulation)
    anchor = (metadata_json, next_url, refused_at)
    for name, value in (('metadata_json', metadata_json), ('next_url', next_url), ('refused_at', refused_at),
                        ('_seal', _PARENT_SEAL), ('_anchor', anchor), ('_anchor_identity', anchor)):
        object.__setattr__(obj, name, value)
    obj._bound()
    return obj


def _bound_parent(source):
    _require(type(source) is ParentPopulation, 'exact_protected_parent_replay_required')
    pages = source.pages()
    _require(type(pages) is list and len(pages) == OLD_PAGES, 'parent_metadata_chain_count')
    url, seen, previous = ENDPOINT + '?' + urllib.parse.urlencode(PARAMS), set(), _clock(SOURCE_STARTED_AT)
    for ordinal, page in enumerate(pages, 1):
        _require(type(page) is dict and type(page.get('ordinal')) is int and page['ordinal'] == ordinal
                 and page.get('segment') == 'parent' and url not in seen, 'parent_metadata_chain_binding')
        _same(page.get('request'), _descriptor(url), 'parent_metadata_request_binding')
        seen.add(url)
        receipt = page.get('receipt')
        _require(type(receipt) is dict and receipt.get('request_sha256') == hash_payload(_descriptor(url))
                 and previous <= _clock(receipt.get('received_at')), 'parent_metadata_receipt_binding')
        previous = _clock(receipt['received_at'])
        url = _next_url(page.get('next_url'))
    _require(url == source.next_url and url not in seen and hash_bytes(url.encode()) == SOURCE_CURSOR_SHA256
             and previous <= _clock(source.refused_at), 'parent_cursor_or_chronology_binding')
    return pages


def _source(root, *, head, remote):
    """Verify the exact spent parent, one bounded raw file at a time."""
    _require_capture_platform()
    _guard(root, head, remote)
    directory = root / SOURCE
    names = {'protocol.json', 'started.json', 'refused.json', f'page-{OLD_PAGES:02d}.refused.json'}
    for ordinal in range(1, OLD_PAGES + 1):
        names.update(f'page-{ordinal:02d}' + suffix for suffix in ('.started.json', '.received.json', '.raw'))
    _require({path.name for path in directory.iterdir()} == names, 'parent_source_inventory')
    inventory = []
    for name in sorted(names):
        raw = _read(root, directory / name, head=head, remote=remote)
        inventory.append({'name': name, 'sha256': hash_bytes(raw), 'bytes': len(raw)})
    _require(hash_payload(inventory) == SOURCE_INVENTORY_SHA256, 'parent_source_inventory_bytes')
    def receipt(name):
        return original._json(_read(root, directory / name, head=head, remote=remote, maximum=65536))
    saved_protocol, start, end = (receipt(name) for name in ('protocol.json', 'started.json', 'refused.json'))
    _require(hash_payload(saved_protocol) == SOURCE_PROTOCOL, 'parent_source_protocol')
    _require(saved_protocol.get('endpoint') == ENDPOINT and saved_protocol.get('initial_query') == PARAMS
             and type(saved_protocol.get('maximum_pages')) is int and saved_protocol['maximum_pages'] == OLD_PAGES
             and saved_protocol.get('maximum_response_bytes') == MAXIMUM_BYTES,
             'parent_source_scope')
    _same(start, {'schema': 'si-native-population-start-v1', 'code_head': SOURCE_HEAD,
                 'remote_head': SOURCE_REMOTE, 'code_identity_sha256': SOURCE_CODE_IDENTITY,
                 'protocol_sha256': SOURCE_PROTOCOL, 'started_at': SOURCE_STARTED_AT,
                 'maximum_attempts': OLD_PAGES, 'outcome_looks': 0, 'qc_attempts': 0}, 'parent_start_binding')
    _require(_historical_identity(root, SOURCE_HEAD, original.CODE_FILES, head=head, remote=remote)
             == SOURCE_CODE_IDENTITY, 'parent_historical_code_identity')
    budget_raw = _read(root, directory.parent / ('budget-' + SOURCE_PROTOCOL + '.json'),
                       head=head, remote=remote, maximum=65536)
    _require(hash_bytes(budget_raw) == SOURCE_BUDGET_SHA256, 'parent_consumed_budget_bytes')
    _same(original._json(budget_raw), {'schema': 'si-native-population-budget-v1', 'code_head': SOURCE_HEAD,
          'remote_head': SOURCE_REMOTE, 'run_id': directory.name, 'protocol_sha256': SOURCE_PROTOCOL,
          'maximum_attempts': OLD_PAGES, 'started_at': SOURCE_STARTED_AT, 'restart_or_resume': False},
          'parent_consumed_budget_binding')
    _same(end, {'schema': 'si-native-population-refusal-v1', 'status': 'source_capture_refused',
               'refused_at': end.get('refused_at'), 'outcome_looks': 0, 'qc_attempts': 0,
               'backtest_result_exists': False}, 'parent_run_refusal')
    url, seen, pages, previous = ENDPOINT + '?' + urllib.parse.urlencode(PARAMS), set(), [], _clock(SOURCE_STARTED_AT)
    for ordinal in range(1, OLD_PAGES + 1):
        _require(url not in seen, 'parent_pagination_cycle')
        seen.add(url)
        prefix, descriptor = f'page-{ordinal:02d}', _descriptor(url)
        began, received = receipt(prefix + '.started.json'), receipt(prefix + '.received.json')
        raw = _read(root, directory / (prefix + '.raw'), head=head, remote=remote)
        _same(began, {'schema': 'si-native-population-page-start-v1', 'ordinal': ordinal,
              'request': descriptor, 'request_sha256': hash_payload(descriptor), 'protocol_sha256': SOURCE_PROTOCOL,
              'code_head': SOURCE_HEAD, 'started_at': began.get('started_at')}, 'parent_request_binding')
        _same(received, {'schema': 'si-native-population-page-received-v1', 'ordinal': ordinal,
              'request_sha256': hash_payload(descriptor), 'http_status': 200, 'content_type': received.get('content_type'),
              'raw_path': prefix + '.raw', 'raw_sha256': hash_bytes(raw), 'raw_bytes': len(raw),
              'received_at': received.get('received_at')}, 'parent_response_binding')
        media = received.get('content_type')
        _require(type(media) is str and len(media) <= 4096
                 and media.split(';', 1)[0].strip().lower() == 'application/json', 'parent_response_media')
        _require(previous <= _clock(began.get('started_at')) <= _clock(received.get('received_at')),
                 'parent_page_chronology')
        previous = _clock(received['received_at'])
        rows, following = _page(raw)
        _require(following is not None, 'parent_not_exhausted_exact_chain')
        pages.append({'ordinal': ordinal, 'segment': 'parent', 'request': descriptor,
                      'receipt': received, 'row_count': rows, 'next_url': following})
        url = following
    refused = receipt(f'page-{OLD_PAGES:02d}.refused.json')
    _same(refused, {'schema': 'si-native-population-page-refusal-v1', 'ordinal': OLD_PAGES,
                   'code': 'whole_population_page_budget_exhausted', 'http_status': 200,
                   'refused_at': refused.get('refused_at')}, 'parent_terminal_budget_refusal')
    _require(previous <= _clock(refused.get('refused_at')) <= _clock(end.get('refused_at')),
             'parent_refusal_chronology')
    _require(url not in seen and hash_bytes(url.encode()) == SOURCE_CURSOR_SHA256, 'parent_retained_cursor_binding')
    return _parent_population(canonical_json(pages), url, end['refused_at'])


def _credential(root, *, head, remote):
    _guard(root, head, remote)
    value = os.environ.get('MASSIVE_API_KEY')
    _require(type(value) is str and bool(value), 'known_MASSIVE_API_KEY_unavailable')
    return KeychainSecret(value)


def _capture(root, directory, opener, secret, source, *, head, remote, started_at, identity):
    _require_capture_platform()
    _policy()
    parent_pages = _bound_parent(source)
    _require(type(secret) is KeychainSecret, 'exact_redacted_credential_required')
    url, seen = source.next_url, {page['request']['url'] for page in parent_pages}
    previous, pages = _clock(started_at), []
    _require(_clock(source.refused_at) <= previous, 'parent_continuation_start_chronology')
    def publish(name, value, raw=False):
        _policy()
        _guard(root, head, remote)
        (_publish if raw else _publish_json)(directory, name, value)
    for attempt in range(1, ADDITIONAL_PAGES + 1):
        _policy()
        _require(url not in seen, 'pagination_cycle')
        seen.add(url)
        ordinal, status = OLD_PAGES + attempt, None
        prefix, descriptor = f'page-{ordinal:02d}', _descriptor(url)
        began = _utc_now()
        _require(previous <= _clock(began), 'request_chronology')
        publish(prefix + '.started.json', {'schema': 'si-native-population-continuation-page-start-v1',
                'ordinal': ordinal, 'attempt': attempt, 'request': descriptor,
                'request_sha256': hash_payload(descriptor), 'protocol_sha256': EXPECTED_PROTOCOL_SHA256,
                'code_head': head, 'started_at': began})
        try:
            _policy()
            _guard(root, head, remote)
            request = urllib.request.Request(url, method='GET', headers={
                'Accept': 'application/json', 'Authorization': 'Bearer ' + secret.for_authorization_header()})
            raw, media, status = _http(opener, request, MAXIMUM_BYTES)
            _require(type(raw) is bytes and len(raw) <= MAXIMUM_BYTES
                     and type(media) is str and len(media) <= 4096, 'response_size_or_types_refused')
            _require(not secret.echoed_in(raw) and not secret.echoed_in(media.encode()), 'credential_echo_refused')
            received = _utc_now()
            _require(_clock(began) <= _clock(received), 'response_chronology')
            publish(prefix + '.raw', raw, True)
            receipt = {'schema': 'si-native-population-page-received-v1', 'ordinal': ordinal,
                       'request_sha256': hash_payload(descriptor), 'http_status': status, 'content_type': media,
                       'raw_path': prefix + '.raw', 'raw_sha256': hash_bytes(raw), 'raw_bytes': len(raw),
                       'received_at': received}
            publish(prefix + '.received.json', receipt)
            _require(type(status) is int and status == 200
                     and media.split(';', 1)[0].strip().lower() == 'application/json', 'response_HTTP_or_media_refused')
            rows, following = _page(raw)
            pages.append({'ordinal': ordinal, 'segment': 'child', 'request': descriptor,
                          'receipt': receipt, 'row_count': rows, 'next_url': following})
            previous = _clock(received)
            if following is None:
                break
            _require(attempt < ADDITIONAL_PAGES, 'continuation_page_budget_exhausted')
            url = following
        except (CaptureRefusal, ValueError, TypeError, OSError, KeyError):
            publish(prefix + '.refused.json', {'schema': 'si-native-population-continuation-page-refusal-v1',
                    'ordinal': ordinal, 'attempt': attempt, 'code': 'source_page_refused',
                    'http_status': status, 'refused_at': _utc_now()})
            raise
    retrieved = _utc_now()
    _require(previous <= _clock(retrieved), 'report_chronology')
    report = {'schema': 'si-native-population-continuation-inventory-v1',
              'parent_source': protocol()['parent_source'],
              'child_source': {'run': directory.relative_to(root).as_posix(), 'head': head,
                              'protocol_sha256': EXPECTED_PROTOCOL_SHA256, 'code_identity_sha256': identity},
              'retrieved_at': retrieved, 'pages': parent_pages + pages,
              'scope': 'reported_provider_population_not_US_universe', 'source_latest_revised': True,
              'point_in_time_data': False, 'original_vintages_or_availability_admitted': False,
              'signal_or_return_computed': False, 'outcome_looks': 0, 'qc_attempts': 0,
              'ready_for_empirical_backtest': False}
    report['report_sha256'] = hash_payload(report)
    raw_report = (canonical_json(report) + '\n').encode()
    publish('population.private.json', raw_report, True)
    finished = _utc_now()
    _require(_clock(retrieved) <= _clock(finished), 'completion_chronology')
    result = {'schema': 'si-native-population-continuation-completion-v1', 'status': 'source_capture_complete',
              'code_head': head, 'protocol_sha256': EXPECTED_PROTOCOL_SHA256,
              'old_spent_attempts': OLD_PAGES, 'http_attempts': len(pages), 'total_http_attempts': OLD_PAGES + len(pages),
              'private_report_sha256': report['report_sha256'], 'private_report_bytes_sha256': hash_bytes(raw_report),
              'completed_at': finished, 'outcome_looks': 0, 'qc_attempts': 0, 'backtest_result_exists': False}
    publish('completed.json', result)
    return result


def run(root, *, head, remote):
    _require_capture_platform()
    _guard(root, head, remote)
    _policy()
    source = _source(root, head=head, remote=remote)
    _bound_parent(source)
    began = _utc_now()
    _require(_clock(source.refused_at) <= _clock(began), 'continuation_start_chronology')
    target = root / PARENT / ('native-population-continuation-' + _clock(began).strftime('%Y%m%dT%H%M%SZ'))
    _require(_git(root, 'check-ignore', str(target)) == str(target), 'continuation_capture_not_ignored')
    _guard(root, head, remote)
    directory = _prepare_capture_directory(target)
    def publish(owner, name, value):
        _policy()
        _guard(root, head, remote)
        _publish_json(owner, name, value)
    try:
        publish(directory.parent, 'budget-' + claim_sha256() + '.json', {
            'schema': 'si-native-population-continuation-budget-v1', 'claim_sha256': claim_sha256(),
            'code_head': head, 'remote_head': remote, 'run_id': directory.name,
            'protocol_sha256': EXPECTED_PROTOCOL_SHA256, 'parent_inventory_sha256': SOURCE_INVENTORY_SHA256,
            'last_next_url_sha256': SOURCE_CURSOR_SHA256, 'old_spent_attempts': OLD_PAGES,
            'maximum_additional_attempts': ADDITIONAL_PAGES, 'started_at': began, 'restart_or_resume': False})
        publish(directory, 'protocol.json', protocol())
        files = []
        for name in CODE_FILES:
            _policy()
            _guard(root, head, remote)
            files.append({'path': name, 'sha256': hash_bytes((root / name).read_bytes())})
        identity = hash_payload({'git_commit': head, 'files': files})
        publish(directory, 'started.json', {'schema': 'si-native-population-continuation-start-v1',
                'code_head': head, 'remote_head': remote, 'code_identity_sha256': identity,
                'protocol_sha256': EXPECTED_PROTOCOL_SHA256, 'parent_inventory_sha256': SOURCE_INVENTORY_SHA256,
                'started_at': began, 'maximum_additional_attempts': ADDITIONAL_PAGES,
                'outcome_looks': 0, 'qc_attempts': 0})
        _policy()
        _guard(root, head, remote)
        secret = _credential(root, head=head, remote=remote)
        _require(type(secret) is KeychainSecret, 'exact_redacted_credential_required')
        _policy()
        _guard(root, head, remote)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        return _capture(root, directory, opener, secret, source, head=head, remote=remote,
                        started_at=began, identity=identity)
    except (CaptureRefusal, ShortInterestKeychainError, ValueError, TypeError, OSError, KeyError):
        publish(directory, 'refused.json', {'schema': 'si-native-population-continuation-refusal-v1',
                'status': 'source_capture_refused', 'refused_at': _utc_now(), 'outcome_looks': 0,
                'qc_attempts': 0, 'backtest_result_exists': False})
        raise


def load_population_pages(root, *, head, remote, child_run, source_head,
                          report_bytes_sha256, budget_bytes_sha256, inventory_sha256):
    """Return authenticated report bytes and a guarded one-page-at-a-time iterator.

    The three byte pins are registered from the completed private capture.
    Completion is independently reconstructed; no report flag admits a source.
    """
    _require_capture_platform()
    _guard(root, head, remote)
    _policy()
    for digest in (report_bytes_sha256, budget_bytes_sha256, inventory_sha256):
        _require(type(digest) is str and len(digest) == 64 and all(c in '0123456789abcdef' for c in digest),
                 'completed_source_byte_pin_required')
    path = Path(child_run)
    _require(not path.is_absolute() and path.parent == PARENT
             and path.name.startswith('native-population-continuation-')
             and path.as_posix() == child_run, 'completed_child_run_path')
    parent = _source(root, head=head, remote=remote)
    directory = root / path
    def read(name, maximum=65536):
        return _read(root, directory / name, head=head, remote=remote, maximum=maximum)
    raw_report = read('population.private.json', 4 * 1024 * 1024)
    _require(hash_bytes(raw_report) == report_bytes_sha256, 'completed_report_bytes_changed')
    report, start, end = (original._json(value) for value in
                         (raw_report, read('started.json'), read('completed.json')))
    _same(original._json(read('protocol.json')), protocol(), 'completed_protocol_binding')
    identity = _historical_identity(root, source_head, CODE_FILES, head=head, remote=remote)
    began = start.get('started_at')
    _same(start, {'schema': 'si-native-population-continuation-start-v1', 'code_head': source_head,
          'remote_head': start.get('remote_head'), 'code_identity_sha256': identity,
          'protocol_sha256': EXPECTED_PROTOCOL_SHA256, 'parent_inventory_sha256': SOURCE_INVENTORY_SHA256,
          'started_at': began, 'maximum_additional_attempts': ADDITIONAL_PAGES,
          'outcome_looks': 0, 'qc_attempts': 0}, 'completed_start_binding')
    budget_raw = _read(root, directory.parent / ('budget-' + claim_sha256() + '.json'),
                       head=head, remote=remote, maximum=65536)
    _require(hash_bytes(budget_raw) == budget_bytes_sha256, 'completed_consumed_budget_bytes')
    _same(original._json(budget_raw), {'schema': 'si-native-population-continuation-budget-v1',
          'claim_sha256': claim_sha256(), 'code_head': source_head, 'remote_head': start['remote_head'],
          'run_id': directory.name, 'protocol_sha256': EXPECTED_PROTOCOL_SHA256,
          'parent_inventory_sha256': SOURCE_INVENTORY_SHA256, 'last_next_url_sha256': SOURCE_CURSOR_SHA256,
          'old_spent_attempts': OLD_PAGES, 'maximum_additional_attempts': ADDITIONAL_PAGES,
          'started_at': began, 'restart_or_resume': False}, 'completed_consumed_budget_binding')
    _require(_clock(parent.refused_at) <= _clock(began), 'completed_parent_start_chronology')
    count = end.get('http_attempts')
    _require(type(count) is int and 1 <= count <= ADDITIONAL_PAGES, 'completed_attempt_count')
    names = {'protocol.json', 'started.json', 'completed.json', 'population.private.json'}
    for ordinal in range(OLD_PAGES + 1, OLD_PAGES + count + 1):
        names.update(f'page-{ordinal:02d}' + suffix for suffix in ('.started.json', '.received.json', '.raw'))
    _guard(root, head, remote)
    _require({item.name for item in directory.iterdir()} == names, 'completed_child_inventory')
    inventory = []
    for name in sorted(names):
        raw = read(name, MAXIMUM_BYTES)
        inventory.append({'name': name, 'sha256': hash_bytes(raw), 'bytes': len(raw)})
    _require(hash_payload(inventory) == inventory_sha256, 'completed_child_inventory_bytes')
    parent_pages = parent.pages()
    url, seen = parent.next_url, {page['request']['url'] for page in parent_pages}
    previous, child_pages = _clock(began), []
    for attempt in range(1, count + 1):
        ordinal, prefix = OLD_PAGES + attempt, f'page-{OLD_PAGES + attempt:02d}'
        _require(url not in seen, 'completed_pagination_cycle')
        seen.add(url)
        descriptor = _descriptor(url)
        requested, received = (original._json(read(prefix + suffix)) for suffix in ('.started.json', '.received.json'))
        raw = read(prefix + '.raw', MAXIMUM_BYTES)
        _same(requested, {'schema': 'si-native-population-continuation-page-start-v1', 'ordinal': ordinal,
              'attempt': attempt, 'request': descriptor, 'request_sha256': hash_payload(descriptor),
              'protocol_sha256': EXPECTED_PROTOCOL_SHA256, 'code_head': source_head,
              'started_at': requested.get('started_at')}, 'completed_request_binding')
        _same(received, {'schema': 'si-native-population-page-received-v1', 'ordinal': ordinal,
              'request_sha256': hash_payload(descriptor), 'http_status': 200,
              'content_type': received.get('content_type'), 'raw_path': prefix + '.raw',
              'raw_sha256': hash_bytes(raw), 'raw_bytes': len(raw), 'received_at': received.get('received_at')},
              'completed_response_binding')
        media = received.get('content_type')
        _require(type(media) is str and len(media) <= 4096
                 and media.split(';', 1)[0].strip().lower() == 'application/json', 'completed_response_media')
        _require(previous <= _clock(requested.get('started_at')) <= _clock(received.get('received_at')),
                 'completed_page_chronology')
        previous = _clock(received['received_at'])
        rows, following = _page(raw)
        _require((following is None) == (attempt == count), 'completed_exact_terminal_chain')
        child_pages.append({'ordinal': ordinal, 'segment': 'child', 'request': descriptor,
                            'receipt': received, 'row_count': rows, 'next_url': following})
        url = following
    retrieved = report.get('retrieved_at')
    _require(previous <= _clock(retrieved) <= _clock(end.get('completed_at')), 'completed_report_chronology')
    rebuilt = {'schema': 'si-native-population-continuation-inventory-v1', 'parent_source': protocol()['parent_source'],
               'child_source': {'run': child_run, 'head': source_head, 'protocol_sha256': EXPECTED_PROTOCOL_SHA256,
                                'code_identity_sha256': identity}, 'retrieved_at': retrieved,
               'pages': parent_pages + child_pages, 'scope': 'reported_provider_population_not_US_universe',
               'source_latest_revised': True, 'point_in_time_data': False,
               'original_vintages_or_availability_admitted': False, 'signal_or_return_computed': False,
               'outcome_looks': 0, 'qc_attempts': 0, 'ready_for_empirical_backtest': False}
    rebuilt['report_sha256'] = hash_payload(rebuilt)
    _require((canonical_json(rebuilt) + '\n').encode() == raw_report, 'completed_report_rebuild')
    _same(end, {'schema': 'si-native-population-continuation-completion-v1', 'status': 'source_capture_complete',
          'code_head': source_head, 'protocol_sha256': EXPECTED_PROTOCOL_SHA256, 'old_spent_attempts': OLD_PAGES,
          'http_attempts': count, 'total_http_attempts': OLD_PAGES + count,
          'private_report_sha256': rebuilt['report_sha256'], 'private_report_bytes_sha256': report_bytes_sha256,
          'completed_at': end.get('completed_at'), 'outcome_looks': 0, 'qc_attempts': 0,
          'backtest_result_exists': False}, 'completed_receipt_binding')
    # Metadata is sealed as immutable JSON before the lazy iterator is exposed.
    metadata = canonical_json(rebuilt['pages'])
    def pages():
        from research.short_interest_etf.native_population_class_matrix import capture_native_population_page
        for page in json.loads(metadata):
            _require_capture_platform()
            _policy()
            receipt = page['receipt']
            owner = root / SOURCE if page['segment'] == 'parent' else directory
            raw = _read(root, owner / receipt['raw_path'], head=head, remote=remote)
            _require(len(raw) == receipt['raw_bytes'] and hash_bytes(raw) == receipt['raw_sha256'],
                     'streamed_source_bytes_changed')
            yield capture_native_population_page(ordinal=page['ordinal'], segment=page['segment'],
                descriptor=page['request'], request_sha256=receipt['request_sha256'], raw=raw,
                raw_sha256=receipt['raw_sha256'], received_at=receipt['received_at'],
                http_status=receipt['http_status'], content_type=receipt['content_type'])
    return raw_report, pages()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--expected-remote', required=True)
    args = parser.parse_args(argv)
    try:
        result = run(Path.cwd().resolve(), head=args.expected_head, remote=args.expected_remote)
    except (CaptureRefusal, ShortInterestKeychainError, ValueError, TypeError, OSError, KeyError):
        print(json.dumps({'status': 'source_capture_refused', 'code': 'continuation_or_custody_refused',
                          'outcome_looks': 0, 'qc_attempts': 0, 'backtest_result_exists': False}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
