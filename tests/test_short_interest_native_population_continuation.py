"""Fabricated retained pages only; no credentials, sources or network access."""
from __future__ import annotations

import json
from pathlib import Path
import urllib.parse

import pytest
from data.hashing import canonical_json, hash_bytes, hash_payload
from short_interest_capture_fixtures import portable_capture_platform
import scripts.continue_short_interest_native_population as continuation
from scripts.short_interest_keychain import KeychainSecret

NOW, EARLIER, LATER = '2026-10-14T00:00:00Z', '2026-10-13T23:59:59Z', '2026-10-14T00:00:01Z'
HEAD, REMOTE, KEY = 'a' * 40, 'b' * 40, 'fabricated-continuation-key/one'


def encoded(value):
    return (canonical_json(value) + '\n').encode()


def body(next_url=None):
    payload = {'status': 'OK', 'results': [{'ticker': 'FABRICATED', 'settlement_date': '2023-02-28'}]}
    if next_url is not None:
        payload['next_url'] = next_url
    return encoded(payload), 'application/json', 200


@pytest.fixture
def parent(monkeypatch, tmp_path):
    root = tmp_path
    directory = root / continuation.SOURCE
    directory.mkdir(parents=True)
    values = {}
    old_protocol = continuation.original.protocol()
    monkeypatch.setattr(continuation, 'SOURCE_PROTOCOL', hash_payload(old_protocol))
    monkeypatch.setattr(continuation, 'SOURCE_STARTED_AT', NOW)
    start = {'schema': 'si-native-population-start-v1', 'code_head': continuation.SOURCE_HEAD,
             'remote_head': continuation.SOURCE_REMOTE, 'code_identity_sha256': continuation.SOURCE_CODE_IDENTITY,
             'protocol_sha256': continuation.SOURCE_PROTOCOL, 'started_at': NOW,
             'maximum_attempts': 32, 'outcome_looks': 0, 'qc_attempts': 0}
    values['protocol.json'], values['started.json'] = encoded(old_protocol), encoded(start)
    values['refused.json'] = encoded({'schema': 'si-native-population-refusal-v1', 'status': 'source_capture_refused',
        'refused_at': NOW, 'outcome_looks': 0, 'qc_attempts': 0, 'backtest_result_exists': False})
    url = continuation.ENDPOINT + '?' + urllib.parse.urlencode(continuation.PARAMS)
    pages = []
    for ordinal in range(1, 33):
        prefix = f'page-{ordinal:02d}'
        descriptor = continuation._descriptor(url)
        next_url = continuation.ENDPOINT + '?cursor=fabricated-page-' + str(ordinal + 1)
        raw, media, status = body(next_url)
        began = {'schema': 'si-native-population-page-start-v1', 'ordinal': ordinal, 'request': descriptor,
                 'request_sha256': hash_payload(descriptor), 'protocol_sha256': continuation.SOURCE_PROTOCOL,
                 'code_head': continuation.SOURCE_HEAD, 'started_at': NOW}
        receipt = {'schema': 'si-native-population-page-received-v1', 'ordinal': ordinal,
                   'request_sha256': hash_payload(descriptor), 'http_status': status, 'content_type': media,
                   'raw_path': prefix + '.raw', 'raw_sha256': hash_bytes(raw), 'raw_bytes': len(raw), 'received_at': NOW}
        values[prefix + '.started.json'], values[prefix + '.received.json'], values[prefix + '.raw'] = encoded(began), encoded(receipt), raw
        pages.append({'ordinal': ordinal, 'segment': 'parent', 'request': descriptor, 'receipt': receipt,
                      'row_count': 1, 'next_url': next_url})
        url = next_url
    values['page-32.refused.json'] = encoded({'schema': 'si-native-population-page-refusal-v1', 'ordinal': 32,
                'code': 'whole_population_page_budget_exhausted', 'http_status': 200, 'refused_at': NOW})
    budget = encoded({'schema': 'si-native-population-budget-v1', 'code_head': continuation.SOURCE_HEAD,
                'remote_head': continuation.SOURCE_REMOTE, 'run_id': directory.name, 'protocol_sha256': continuation.SOURCE_PROTOCOL,
                'maximum_attempts': 32, 'started_at': NOW, 'restart_or_resume': False})
    monkeypatch.setattr(continuation, 'SOURCE_BUDGET_SHA256', hash_bytes(budget))
    monkeypatch.setattr(continuation, 'SOURCE_CURSOR_SHA256', hash_bytes(url.encode()))
    def repin():
        monkeypatch.setattr(continuation, 'SOURCE_INVENTORY_SHA256', hash_payload([
            {'name': name, 'sha256': hash_bytes(raw), 'bytes': len(raw)} for name, raw in sorted(values.items())]))
    repin()
    for name in values:
        (directory / name).touch()
    events = []
    monkeypatch.setattr(continuation, '_guard', lambda *args: events.append('guard'))
    def read(read_root, path, **kwargs):
        assert read_root == root
        return budget if path.parent == directory.parent else values[path.name]
    monkeypatch.setattr(continuation, '_read', read)
    monkeypatch.setattr(continuation, '_historical_identity', lambda *args, **kwargs: continuation.SOURCE_CODE_IDENTITY)
    return root, values, pages, url, repin


@pytest.mark.usefixtures('portable_capture_platform')
def test_replay_authenticates_all_100_parent_files_spent_claim_and_exact_cursor(parent):
    root, values, pages, url, _ = parent
    assert len(values) == 100
    source = continuation._source(root, head=HEAD, remote=REMOTE)
    assert source.pages() == pages and source.next_url == url and source.refused_at == NOW
    assert 'complete_advertised_page_chain' not in source.metadata_json


@pytest.mark.parametrize('name', ['protocol.json', 'page-01.raw', 'page-17.received.json', 'page-32.refused.json', 'refused.json'])
@pytest.mark.usefixtures('portable_capture_platform')
def test_each_changed_parent_byte_is_refused_before_any_secret_or_request(parent, monkeypatch, name):
    root, values, _, _, _ = parent
    values[name] += b' '
    monkeypatch.setattr(continuation, '_credential', lambda *args, **kwargs: pytest.fail('secret reached'))
    monkeypatch.setattr(continuation, '_http', lambda *args: pytest.fail('network reached'))
    with pytest.raises(continuation.CaptureRefusal, match='parent_source_inventory_bytes'):
        continuation._source(root, head=HEAD, remote=REMOTE)


@pytest.mark.parametrize('kind', ['terminal_code', 'clock', 'status', 'request', 'short_chain', 'bool_counter', 'cursor'])
@pytest.mark.usefixtures('portable_capture_platform')
def test_parent_semantics_not_admitted_by_repinning_or_truthy_flags(parent, kind):
    root, values, _, _, repin = parent
    name = 'page-32.refused.json'
    if kind == 'clock':
        name = 'page-02.started.json'
    elif kind in ('status', 'request'):
        name = 'page-12.received.json' if kind == 'status' else 'page-12.started.json'
    elif kind in ('short_chain', 'cursor'):
        name = 'page-32.raw'
    elif kind == 'bool_counter':
        name = 'started.json'
    value = json.loads(values[name])
    if kind == 'terminal_code': value['code'] = 'some_other_failure'
    elif kind == 'clock': value['started_at'] = EARLIER
    elif kind == 'status': value['http_status'] = True
    elif kind == 'request': value['request']['url'] += '&ticker=AAPL'
    elif kind == 'short_chain': value.pop('next_url')
    elif kind == 'bool_counter': value['outcome_looks'] = False
    elif kind == 'cursor': value['next_url'] += '-changed'
    values[name] = encoded(value)
    if kind in ('short_chain', 'cursor'):
        receipt = json.loads(values['page-32.received.json'])
        receipt.update(raw_sha256=hash_bytes(values[name]), raw_bytes=len(values[name]))
        values['page-32.received.json'] = encoded(receipt)
    repin()
    with pytest.raises(continuation.CaptureRefusal):
        continuation._source(root, head=HEAD, remote=REMOTE)


@pytest.fixture
def offline(monkeypatch):
    events, saved, responses, requests = [], {}, [], []
    monkeypatch.setattr(continuation, '_guard', lambda *args: events.append('guard'))
    monkeypatch.setattr(continuation, '_utc_now', lambda: NOW)
    def publish(directory, name, value):
        assert events[-1] == 'guard'
        if name in saved: raise FileExistsError('exclusive fixture')
        saved[name] = value
        events.append(name)
    monkeypatch.setattr(continuation, '_publish_json', publish)
    monkeypatch.setattr(continuation, '_publish', publish)
    def http(opener, request, maximum):
        ordinal = 33 + len(requests)
        assert f'page-{ordinal:02d}.started.json' in saved and events[-1] == 'guard'
        assert request.get_header('Authorization') == 'Bearer ' + KEY
        assert KEY not in request.full_url and maximum == 32 * 1024 * 1024
        requests.append(request)
        result = responses.pop(0)
        if isinstance(result, Exception): raise result
        return result
    monkeypatch.setattr(continuation, '_http', http)
    pages, url = [], continuation.ENDPOINT + '?' + urllib.parse.urlencode(continuation.PARAMS)
    for number in range(1, 33):
        descriptor = continuation._descriptor(url)
        following = continuation.ENDPOINT + ('?cursor=retained33' if number == 32 else '?cursor=old-' + str(number))
        pages.append({'ordinal': number, 'segment': 'parent', 'request': descriptor,
                      'receipt': {'request_sha256': hash_payload(descriptor), 'received_at': NOW}, 'next_url': following})
        url = following
    monkeypatch.setattr(continuation, 'SOURCE_CURSOR_SHA256', hash_bytes(url.encode()))
    monkeypatch.setattr(continuation, 'EXPECTED_PROTOCOL_SHA256', hash_payload(continuation.protocol()))
    source = continuation._parent_population(canonical_json(pages), url, NOW)
    return events, saved, responses, requests, source


def capture(offline):
    return continuation._capture(Path('/fabricated'), Path('/fabricated/output'), None, KeychainSecret(KEY), offline[4],
                                 head=HEAD, remote=REMOTE, started_at=NOW, identity='c' * 64)


@pytest.mark.usefixtures('portable_capture_platform')
def test_only_exact_retained_cursor_then_complete_chain_no_parent_raw_copy(offline):
    _, saved, responses, requests, source = offline
    following = continuation.ENDPOINT + '?cursor=retained34'
    responses.extend((body(following), body()))
    result = capture(offline)
    assert [request.full_url for request in requests] == [source.next_url, following]
    assert result['http_attempts'] == 2 and result['total_http_attempts'] == 34
    report = json.loads(saved['population.private.json'])
    assert [page['ordinal'] for page in report['pages']] == list(range(1, 35))
    assert sorted(name for name in saved if name.endswith('.raw')) == ['page-33.raw', 'page-34.raw']
    assert report['outcome_looks'] == report['qc_attempts'] == 0 and report['ready_for_empirical_backtest'] is False


@pytest.mark.parametrize('complete', [False, True])
@pytest.mark.usefixtures('portable_capture_platform')
def test_64_additional_96_total_budget_never_calls_97_or_reports_partial_completion(offline, complete):
    _, saved, responses, requests, _ = offline
    for attempt in range(1, 65):
        responses.append(body(None if complete and attempt == 64 else continuation.ENDPOINT + '?cursor=extra-' + str(attempt)))
    if complete:
        assert capture(offline)['total_http_attempts'] == 96
    else:
        with pytest.raises(continuation.CaptureRefusal, match='continuation_page_budget_exhausted'):
            capture(offline)
        assert 'page-96.refused.json' in saved and 'completed.json' not in saved
    assert len(requests) == 64 and 'page-97.started.json' not in saved


@pytest.mark.parametrize('url', [
    'https://evil.invalid/stocks/v1/short-interest?cursor=x',
    'https://api.massive.com/stocks/v1/short-volume?cursor=x',
    'https://api.massive.com/stocks/v1/short-interest?cursor=x&apiKey=secret',
    'https://api.massive.com/stocks/v1/short-interest?cursor=x&settlement_date.lte=2030-01-01',
    'https://api.massive.com/stocks/v1/short-interest?cursor=old-1',
    'https://api.massive.com/stocks/v1/short-interest?cursor=retained33',
])
@pytest.mark.usefixtures('portable_capture_platform')
def test_unsafe_scope_secret_or_cross_segment_cycle_retains_received_page_no_follow(offline, url):
    _, saved, responses, requests, _ = offline
    responses.append(body(url))
    with pytest.raises(continuation.CaptureRefusal): capture(offline)
    assert len(requests) == 1 and 'page-33.raw' in saved and 'page-34.started.json' not in saved


@pytest.mark.parametrize('encoded_key', [KEY, urllib.parse.quote(KEY, safe=''), ''.join('\\u%04x' % ord(c) for c in KEY)])
@pytest.mark.usefixtures('portable_capture_platform')
def test_secret_echo_is_refused_before_raw_persistence_or_body_hash(offline, monkeypatch, encoded_key):
    _, saved, responses, _, _ = offline
    raw = ('{"status":"OK","results":[],"notice":"' + encoded_key + '"}').encode()
    responses.append((raw, 'application/json', 200))
    original = continuation.hash_bytes
    hashes = []
    monkeypatch.setattr(continuation, 'hash_bytes', lambda value: hashes.append(value) or original(value))
    with pytest.raises(continuation.CaptureRefusal, match='credential_echo_refused'): capture(offline)
    assert raw not in hashes and set(saved) == {'page-33.started.json', 'page-33.refused.json'}


@pytest.mark.usefixtures('portable_capture_platform')
def test_failed_started_call_consumes_attempt_and_is_not_retried(offline):
    _, saved, responses, requests, _ = offline
    responses.append(OSError('external secret text must never be published'))
    with pytest.raises(OSError): capture(offline)
    assert len(requests) == 1 and set(saved) == {'page-33.started.json', 'page-33.refused.json'}
    assert 'external secret text' not in repr(saved)


@pytest.mark.parametrize('edge', ['enclosing', 'response', 'between', 'report', 'completion'])
@pytest.mark.usefixtures('portable_capture_platform')
def test_all_run_request_response_report_completion_clock_edges_refuse(offline, monkeypatch, edge):
    _, saved, responses, _, _ = offline
    responses.extend((body(continuation.ENDPOINT + '?cursor=next34'), body()))
    clocks = [NOW] * 6
    if edge == 'enclosing': clocks[0] = EARLIER
    elif edge == 'response': clocks[0] = LATER
    elif edge == 'between': clocks[1], clocks[2] = LATER, NOW
    elif edge == 'report': clocks[4] = EARLIER
    elif edge == 'completion': clocks[5] = EARLIER
    iterator = iter(clocks)
    monkeypatch.setattr(continuation, '_utc_now', lambda: next(iterator, NOW))
    with pytest.raises(continuation.CaptureRefusal, match='chronology'): capture(offline)
    assert 'completed.json' not in saved


@pytest.mark.usefixtures('portable_capture_platform')
def test_callback_cannot_change_frozen_scope_before_another_call_or_completion(offline, monkeypatch):
    _, saved, responses, requests, _ = offline
    responses.append(body(continuation.ENDPOINT + '?cursor=next34'))
    real = continuation._http
    def change(*args):
        result = real(*args)
        monkeypatch.setitem(continuation.PARAMS, 'settlement_date.lte', '2030-01-01')
        return result
    monkeypatch.setattr(continuation, '_http', change)
    with pytest.raises(continuation.CaptureRefusal, match='protocol_pending_or_changed'): capture(offline)
    assert len(requests) == 1 and set(saved) == {'page-33.started.json'}


def test_claim_identity_cannot_be_reset_with_policy_time_or_code_head(monkeypatch):
    digest = continuation.claim_sha256()
    monkeypatch.setattr(continuation, 'ADDITIONAL_PAGES', 640)
    monkeypatch.setattr(continuation, 'EXPECTED_PROTOCOL_SHA256', 'f' * 64)
    assert continuation.claim_sha256() == digest


@pytest.mark.parametrize('field,value', [
    ('next_url', 'https://evil.invalid/stocks/v1/short-interest?cursor=steal'),
    ('metadata_json', '[]'), ('refused_at', LATER),
])
@pytest.mark.usefixtures('portable_capture_platform')
def test_reflection_cannot_retarget_bound_parent_before_bearer_request(offline, field, value):
    _, _, responses, requests, source = offline
    object.__setattr__(source, field, value)
    responses.append(body())
    with pytest.raises(continuation.CaptureRefusal, match='parent'):
        capture(offline)
    assert not requests


def test_public_parent_construction_refuses():
    with pytest.raises(continuation.CaptureRefusal, match='parent_factory'):
        continuation.ParentPopulation()


@pytest.fixture
def run_facade(offline, monkeypatch):
    source = offline[4]
    root, stored, owned, keys = Path('/fabricated'), {}, set(), []
    monkeypatch.setattr(continuation, '_source', lambda *args, **kwargs: source)
    monkeypatch.setattr(continuation, '_git', lambda root, *args: args[-1])
    monkeypatch.setattr(continuation, 'CODE_FILES', ())
    def prepare(path):
        if path in owned: raise FileExistsError('owned original preserved')
        owned.add(path)
        return path
    def publish(directory, name, value):
        key = (directory, name)
        if key in stored: raise FileExistsError('immutable consumed claim')
        stored[key] = value
    monkeypatch.setattr(continuation, '_prepare_capture_directory', prepare)
    monkeypatch.setattr(continuation, '_publish_json', publish)
    def credential(*args, **kwargs):
        keys.append('credential')
        return KeychainSecret(KEY)
    monkeypatch.setattr(continuation, '_credential', credential)
    monkeypatch.setattr(continuation, '_capture', lambda *args, **kwargs: {'status': 'fixture_no_request'})
    return root, stored, owned, keys


@pytest.mark.usefixtures('portable_capture_platform')
def test_existing_global_claim_refuses_before_secret_and_only_new_owned_refusal_is_written(run_facade):
    root, stored, owned, keys = run_facade
    key = (root / continuation.PARENT, 'budget-' + continuation.claim_sha256() + '.json')
    stored[key] = {'immutable': 'prior run'}
    with pytest.raises(FileExistsError): continuation.run(root, head=HEAD, remote=REMOTE)
    assert not keys and stored[key] == {'immutable': 'prior run'}
    assert len(owned) == 1 and len(stored) == 2
    assert next(value for (directory, name), value in stored.items() if name == 'refused.json')['outcome_looks'] == 0


@pytest.mark.usefixtures('portable_capture_platform')
def test_missing_named_key_retains_claim_protocol_start_and_owned_zero_request_refusal(run_facade, monkeypatch):
    root, stored, owned, _ = run_facade
    def unavailable(*args, **kwargs):
        raise continuation.PopulationContinuationRefusal('known_MASSIVE_API_KEY_unavailable')
    monkeypatch.setattr(continuation, '_credential', unavailable)
    with pytest.raises(continuation.CaptureRefusal, match='known_MASSIVE_API_KEY'):
        continuation.run(root, head=HEAD, remote=REMOTE)
    assert len(owned) == 1
    assert {name for directory, name in stored} >= {'protocol.json', 'started.json', 'refused.json'}
    assert not any(name.startswith('page-') for directory, name in stored)


def test_unsupported_host_is_first_before_source_read_secret_output_or_request(monkeypatch):
    def refuse(): raise continuation.CaptureRefusal('unsupported_host')
    monkeypatch.setattr(continuation, '_require_capture_platform', refuse)
    for name in ('_guard', '_source', '_credential', '_prepare_capture_directory', '_http'):
        monkeypatch.setattr(continuation, name, lambda *args, **kwargs: pytest.fail('after host guard'))
    with pytest.raises(continuation.CaptureRefusal, match='unsupported_host'):
        continuation.run(Path('/fabricated'), head=HEAD, remote=REMOTE)


@pytest.fixture
def completed(parent, offline, monkeypatch):
    root, values, _, _, _ = parent
    _, saved, responses, _, _ = offline
    monkeypatch.setattr(continuation, 'SOURCE_CURSOR_SHA256', hash_bytes(parent[3].encode()))
    monkeypatch.setattr(continuation, 'EXPECTED_PROTOCOL_SHA256', hash_payload(continuation.protocol()))
    source = continuation._source(root, head=HEAD, remote=REMOTE)
    directory = root / continuation.PARENT / 'native-population-continuation-20261014T000000Z'
    directory.mkdir(parents=True)
    responses.append(body())
    continuation._capture(root, directory, None, KeychainSecret(KEY), source, head=HEAD, remote=REMOTE,
                          started_at=NOW, identity=continuation.SOURCE_CODE_IDENTITY)
    saved['protocol.json'] = continuation.protocol()
    saved['started.json'] = {'schema': 'si-native-population-continuation-start-v1',
        'code_head': HEAD, 'remote_head': REMOTE, 'code_identity_sha256': continuation.SOURCE_CODE_IDENTITY,
        'protocol_sha256': continuation.EXPECTED_PROTOCOL_SHA256, 'parent_inventory_sha256': continuation.SOURCE_INVENTORY_SHA256,
        'started_at': NOW, 'maximum_additional_attempts': 64, 'outcome_looks': 0, 'qc_attempts': 0}
    files = {name: value if type(value) is bytes else encoded(value) for name, value in saved.items()}
    budget = encoded({'schema': 'si-native-population-continuation-budget-v1', 'claim_sha256': continuation.claim_sha256(),
        'code_head': HEAD, 'remote_head': REMOTE, 'run_id': directory.name,
        'protocol_sha256': continuation.EXPECTED_PROTOCOL_SHA256, 'parent_inventory_sha256': continuation.SOURCE_INVENTORY_SHA256,
        'last_next_url_sha256': continuation.SOURCE_CURSOR_SHA256, 'old_spent_attempts': 32,
        'maximum_additional_attempts': 64, 'started_at': NOW, 'restart_or_resume': False})
    for name in files: (directory / name).touch()
    base_read = continuation._read
    def read(read_root, path, **kwargs):
        if path.parent == directory: return files[path.name]
        if path.parent == directory.parent: return budget
        return base_read(read_root, path, **kwargs)
    monkeypatch.setattr(continuation, '_read', read)
    def pins():
        return {'child_run': directory.relative_to(root).as_posix(), 'source_head': HEAD,
                'report_bytes_sha256': hash_bytes(files['population.private.json']),
                'budget_bytes_sha256': hash_bytes(budget), 'inventory_sha256': hash_payload([
                    {'name': name, 'sha256': hash_bytes(raw), 'bytes': len(raw)} for name, raw in sorted(files.items())])}
    return root, files, values, pins


@pytest.mark.usefixtures('portable_capture_platform')
def test_completed_loader_replays_old_plus_new_without_copy_or_boolean_admission(completed):
    from research.short_interest_etf.native_population_class_matrix import bind_native_population_manifest, freeze_native_population_class_matrix
    root, _, _, pins = completed
    raw, pages = continuation.load_population_pages(root, head=HEAD, remote=REMOTE, **pins())
    matrix = freeze_native_population_class_matrix(bind_native_population_manifest(raw, pins()['report_bytes_sha256']), pages)
    assert matrix.parts()[0]
    assert json.loads(raw)['ready_for_empirical_backtest'] is False


@pytest.mark.parametrize('name', ['page-33.started.json', 'page-33.received.json', 'page-33.raw', 'started.json', 'completed.json'])
@pytest.mark.usefixtures('portable_capture_platform')
def test_completed_loader_rejects_each_changed_child_byte(completed, name):
    root, files, _, pins = completed
    frozen = pins()
    files[name] += b' '
    with pytest.raises(continuation.CaptureRefusal, match='inventory_bytes'):
        continuation.load_population_pages(root, head=HEAD, remote=REMOTE, **frozen)


@pytest.mark.usefixtures('portable_capture_platform')
def test_lazy_loader_rechecks_original_bytes_changed_after_full_replay(completed):
    root, _, parent_values, pins = completed
    _, pages = continuation.load_population_pages(root, head=HEAD, remote=REMOTE, **pins())
    parent_values['page-01.raw'] += b' '
    with pytest.raises(continuation.CaptureRefusal, match='streamed_source_bytes_changed'):
        next(pages)


@pytest.mark.usefixtures('portable_capture_platform')
def test_loader_rejects_laundered_complete_boolean_when_final_raw_link_is_unfinished(completed):
    root, files, _, pins = completed
    new_raw = body(continuation.ENDPOINT + '?cursor=not-complete')[0]
    files['page-33.raw'] = new_raw
    received = json.loads(files['page-33.received.json'])
    received.update(raw_sha256=hash_bytes(new_raw), raw_bytes=len(new_raw))
    files['page-33.received.json'] = encoded(received)
    with pytest.raises(continuation.CaptureRefusal, match='completed_exact_terminal_chain'):
        continuation.load_population_pages(root, head=HEAD, remote=REMOTE, **pins())


@pytest.mark.usefixtures('portable_capture_platform')
def test_loader_never_accepts_current_code_identity_for_historical_capture(completed, monkeypatch):
    root, _, _, pins = completed
    monkeypatch.setattr(continuation, '_historical_identity', lambda *args, **kwargs: 'd' * 64)
    with pytest.raises(continuation.CaptureRefusal, match='parent_historical_code_identity'):
        continuation.load_population_pages(root, head=HEAD, remote=REMOTE, **pins())
