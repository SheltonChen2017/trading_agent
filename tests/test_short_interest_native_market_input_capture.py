"""Fabricated bounded JSON pages only: no actual key, source, price or QC."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import urllib.parse

import pytest
from data.hashing import hash_bytes, hash_payload
from short_interest_capture_fixtures import portable_capture_platform
import scripts.capture_short_interest_native_market_inputs as capture
from scripts.short_interest_keychain import KeychainSecret

NOW, EARLIER, LATER = '2026-10-14T01:00:00Z', '2026-10-14T00:59:59Z', '2026-10-14T01:00:01Z'
HEAD, REMOTE, KEY = 'a' * 40, 'b' * 40, 'fabricated-market-key/one'


def row(ticker='FAKE', at='2022-01-03', table='stocks', **changes):
    values = dict.fromkeys(capture.inputs.FIELDS[table], 1)
    values.update(ticker=ticker, date=at, lastupdated='2026-10-13')
    values.update(changes)
    return values


def page(rows=(), **changes):
    envelope = {'count': len(rows), 'data': list(rows)}
    envelope.update(changes)
    return json.dumps(envelope, separators=(',', ':')).encode(), 'application/json', 200


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(capture.inputs, 'MONTHS', (('2022-01', '2022-01-03', '2022-01-31'),))
    monkeypatch.setattr(capture.inputs, 'TABLES', ('stocks',))
    monkeypatch.setattr(capture.inputs, 'PAGE_LIMIT', 2)
    monkeypatch.setattr(capture.inputs, 'PAGES_PER_PANEL', 2)
    monkeypatch.setattr(capture.inputs, 'MAXIMUM_REQUESTS', 2)
    monkeypatch.setattr(capture, 'EXPECTED_PROTOCOL_SHA256', hash_payload(capture.protocol()))
    events, saved, responses, requests = [], {}, [], []
    monkeypatch.setattr(capture, '_guard', lambda *args: events.append('guard'))
    monkeypatch.setattr(capture, '_utc_now', lambda: NOW)
    def publish(directory, name, value):
        assert events[-1] == 'guard'
        if name in saved: raise FileExistsError('immutable fixture')
        saved[name] = copy.deepcopy(value)
        events.append(name)
    monkeypatch.setattr(capture, '_publish_json', publish)
    monkeypatch.setattr(capture, '_publish', publish)
    def http(opener, request, maximum):
        attempt = len(requests) + 1
        assert f'attempt-{attempt:05d}.started.json' in saved and events[-1] == 'guard'
        assert request.get_header('X-api-key') == KEY and maximum == 8 * 1024 * 1024
        assert KEY not in request.full_url
        requests.append(request)
        result = responses.pop(0)
        if isinstance(result, Exception): raise result
        return result
    monkeypatch.setattr(capture, '_http', http)
    return events, saved, responses, requests


def run(offline):
    return capture._capture(Path('/fabricated'), Path('/fabricated/output'), None, KeychainSecret(KEY),
                            head=HEAD, remote=REMOTE, started_at=NOW)


def test_actual_frozen_months_fields_bounds_and_caps_no_zip_or_current_ticker_filter():
    protocol = capture.protocol()
    assert protocol['months'] == 56 and len(protocol['panels']) == 112
    assert protocol['maximum_requests'] == 7168 and protocol['maximum_total_rows'] == 32000000
    assert protocol['maximum_pages_per_table_month'] == 64 and protocol['page_limit'] == 10000
    assert protocol['maximum_response_bytes'] == 8 * 1024 * 1024 and protocol['maximum_total_raw_bytes'] == 8 * 1024**3
    for panel in protocol['panels']:
        descriptor = panel['initial_request']
        assert descriptor['url'] in ('https://api.sharadar.com/v1.0/data/stocks', 'https://api.sharadar.com/v1.0/data/daily')
        assert descriptor['params']['sort'] == 'date.asc' and descriptor['params']['format'] == 'json'
        assert descriptor['params']['offset'] == '0' and descriptor['params']['limit'] == '10000'
        assert 'ticker' not in descriptor['params'] and 'active' not in descriptor['params']
        assert '2022-01-03' <= descriptor['params']['from'] <= descriptor['params']['to'] <= '2026-08-31'
    assert protocol['signal_or_return_computed'] is False and protocol['data_or_fitness_admitted'] is False


@pytest.mark.usefixtures('portable_capture_platform')
def test_exact_page_offsets_require_full_prior_page_and_final_short_page(offline):
    _, saved, responses, requests = offline
    responses.extend((page([row('ONE'), row('TWO')]), page([row('THREE')])))
    result = run(offline)
    assert result['status'] == 'private_market_source_capture_complete' and result['http_attempts'] == 2
    assert [dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(request.full_url).query))['offset'] for request in requests] == ['0', '2']
    report = saved['inventory.private.json']
    assert report['total_raw_rows'] == 3 and report['financial_values_normalized'] is False
    assert report['outcome_looks'] == report['qc_attempts'] == 0 and report['backtest_result_exists'] is False


@pytest.mark.usefixtures('portable_capture_platform')
def test_identifiable_duplicate_and_malformed_peers_all_retained_without_repair(offline):
    _, saved, responses, _ = offline
    responses.extend((page([row('FAKE'), row('OTHER')]), page([row(' FAKE ', close='1.23')])))
    run(offline)
    report = saved['inventory.private.json']['panels'][0]
    assert len(report['malformed_refusals']) == 1
    assert len(report['duplicate_groups']) == 1 and len(report['duplicate_groups'][0]['source_origins']) == 2
    assert report['duplicate_groups'][0]['source_key']['ticker'] == 'FAKE'
    assert saved['attempt-00002.refusals.private.json']['refusals']
    assert len([name for name in saved if name.endswith('.raw')]) == 2


@pytest.mark.usefixtures('portable_capture_platform')
def test_repeated_duplicate_slot_has_one_linear_page_event_not_quadratic_peer_copies(offline, monkeypatch):
    _, saved, responses, _ = offline
    monkeypatch.setattr(capture.inputs, 'PAGE_LIMIT', 10000)
    monkeypatch.setattr(capture, 'EXPECTED_PROTOCOL_SHA256', hash_payload(capture.protocol()))
    responses.append(page([row('SAME') for _ in range(10)]))
    run(offline)
    issues = saved['attempt-00001.refusals.private.json']['refusals']
    assert len(issues) == 1
    assert len(issues[0]['new_source_origins']) == 9
    assert len(saved['inventory.private.json']['panels'][0]['duplicate_groups'][0]['source_origins']) == 10


@pytest.mark.parametrize('bad_date', ['2026-09-01', ' 2026-09-01 ', '2026-09-01T00:00:00Z', '2022-02-01', '2022-01-01'])
@pytest.mark.usefixtures('portable_capture_platform')
def test_any_recognizable_outside_slice_date_refuses_before_financial_validation(offline, monkeypatch, bad_date):
    _, saved, responses, requests = offline
    responses.append(page([row(close=0.1), row('FUTURE', bad_date)]))
    monkeypatch.setattr(capture.inputs, '_NUMBER', type('Dangerous', (), {'fullmatch': lambda *args: pytest.fail('financial validation reached')})())
    hashes, original = [], capture.hash_bytes
    monkeypatch.setattr(capture, 'hash_bytes', lambda value: hashes.append(value) or original(value))
    with pytest.raises(capture.inputs.NativeMarketInputError, match='date_refused|month_filter_refused'):
        run(offline)
    assert len(requests) == 1 and 'attempt-00001.raw' not in saved and 'attempt-00001.received.json' not in saved
    assert not hashes and set(saved) == {'attempt-00001.started.json', 'attempt-00001.refused.json'}
    assert 'inventory.private.json' not in saved and 'completed.json' not in saved


def test_lexical_decimal_is_preserved_without_binary_float_or_price_normalization():
    raw = b'{"count":1,"data":[{"ticker":"FAKE","date":"2022-01-03","open":0.10000000000000000001,"high":1,"low":1,"close":1,"volume":100,"closeunadj":1,"lastupdated":"2026-10-13"}]}'
    rows = capture.inputs.decode_page(raw)
    assert type(rows[0]['open']) is capture.inputs.NumberToken and rows[0]['open'] == '0.10000000000000000001'
    observations, last = capture.inputs.inspect_page(rows, table='stocks', month='2022-01')
    assert observations[0][2] is None and last == '2022-01-03'


@pytest.mark.parametrize('kind', ['raw', 'unicode', 'percent', 'media'])
@pytest.mark.usefixtures('portable_capture_platform')
def test_echo_is_refused_before_hashing_or_persistence_even_for_malformed_json(offline, monkeypatch, kind):
    _, saved, responses, _ = offline
    value, media = KEY, 'application/json'
    if kind == 'unicode': value = ''.join('\\u%04x' % ord(c) for c in KEY)
    if kind == 'percent': value = urllib.parse.quote(KEY, safe='')
    if kind == 'media': media += '; token=' + urllib.parse.quote(KEY, safe=''); value = 'safe'
    raw = ('{"count":0,"data":[],"not_finished":"' + value).encode()
    responses.append((raw, media, 200))
    hashes, original = [], capture.hash_bytes
    monkeypatch.setattr(capture, 'hash_bytes', lambda value: hashes.append(value) or original(value))
    with pytest.raises(capture.CaptureRefusal, match='credential_echo_refused'): run(offline)
    assert not hashes and set(saved) == {'attempt-00001.started.json', 'attempt-00001.refused.json'}


@pytest.mark.parametrize('kind', ['page', 'rows', 'bytes'])
@pytest.mark.usefixtures('portable_capture_platform')
def test_hard_budgets_preserve_partial_pages_without_next_request_or_completion(offline, monkeypatch, kind):
    _, saved, responses, requests = offline
    if kind == 'rows': monkeypatch.setattr(capture.inputs, 'MAXIMUM_ROWS', 2)
    if kind == 'bytes': monkeypatch.setattr(capture.inputs, 'MAXIMUM_RAW_BYTES', capture.inputs.MAXIMUM_BYTES)
    monkeypatch.setattr(capture, 'EXPECTED_PROTOCOL_SHA256', hash_payload(capture.protocol()))
    responses.extend((page([row('ONE'), row('TWO')]), page([row('THREE'), row('FOUR')])))
    with pytest.raises(capture.CaptureRefusal, match='budget_exhausted'): run(offline)
    assert len(requests) == (2 if kind == 'page' else 1)
    assert 'completed.json' not in saved and 'attempt-00003.started.json' not in saved


@pytest.mark.parametrize('malformed', [b'{"count":true,"data":[]}', b'{"count":1,"data":[]}',
    b'{"count":0,"count":0,"data":[]}', b'{"count":0,"data":[],"next_url":"https://evil.invalid"}', b'{"count":NaN,"data":[]}'])
@pytest.mark.usefixtures('portable_capture_platform')
def test_malformed_page_envelope_scope_cannot_be_established_or_followed(offline, malformed):
    _, saved, responses, requests = offline
    responses.append((malformed, 'application/json', 200))
    with pytest.raises(capture.inputs.NativeMarketInputError): run(offline)
    assert len(requests) == 1 and 'attempt-00001.raw' not in saved and 'completed.json' not in saved


@pytest.mark.usefixtures('portable_capture_platform')
def test_later_request_descriptor_cannot_retarget_header_to_another_host(offline, monkeypatch):
    _, saved, responses, requests = offline
    responses.append(page([row('ONE'), row('TWO')]))
    original = capture.inputs.page_request
    def retarget(table, month, number):
        spec = original(table, month, number)
        if number: spec['url'] = 'https://evil.invalid/stocks'
        return spec
    monkeypatch.setattr(capture.inputs, 'page_request', retarget)
    with pytest.raises(capture.CaptureRefusal, match='request_descriptor_binding'): run(offline)
    assert len(requests) == 1 and 'attempt-00002.started.json' not in saved


@pytest.mark.usefixtures('portable_capture_platform')
def test_unsupported_endpoint_failure_is_started_retained_redacted_and_not_retried(offline):
    _, saved, responses, requests = offline
    responses.append(OSError('external secret/provider body must not be logged'))
    with pytest.raises(OSError): run(offline)
    assert len(requests) == 1 and set(saved) == {'attempt-00001.started.json', 'attempt-00001.refused.json'}
    assert 'external secret' not in repr(saved)


@pytest.mark.parametrize('edge', ['enclosing', 'response', 'between', 'report', 'completion'])
@pytest.mark.usefixtures('portable_capture_platform')
def test_every_request_response_report_completion_clock_edge_refuses(offline, monkeypatch, edge):
    _, saved, responses, _ = offline
    responses.extend((page([row('ONE'), row('TWO')]), page()))
    clocks = [NOW] * 6
    if edge == 'enclosing': clocks[0] = EARLIER
    elif edge == 'response': clocks[0] = LATER
    elif edge == 'between': clocks[1], clocks[2] = LATER, NOW
    elif edge == 'report': clocks[4] = EARLIER
    elif edge == 'completion': clocks[5] = EARLIER
    iterator = iter(clocks)
    monkeypatch.setattr(capture, '_utc_now', lambda: next(iterator, NOW))
    with pytest.raises(capture.CaptureRefusal, match='chronology'): run(offline)
    assert 'completed.json' not in saved


def test_claim_cannot_be_reset_with_head_time_or_unconsumed_limit_refinement(monkeypatch):
    digest = capture.claim_sha256()
    monkeypatch.setattr(capture.inputs, 'MAXIMUM_ROWS', 1)
    monkeypatch.setattr(capture, 'EXPECTED_PROTOCOL_SHA256', 'f' * 64)
    assert capture.claim_sha256() == digest


@pytest.mark.parametrize('at', [None, '2022-02-30', '', 20220103])
@pytest.mark.usefixtures('portable_capture_platform')
def test_unrecognizable_date_refuses_body_and_hash_before_financial_validation(offline, monkeypatch, at):
    _, saved, responses, _ = offline
    responses.append(page([row(at=at)]))
    monkeypatch.setattr(capture, 'hash_bytes', lambda *args: pytest.fail('body hashed before scope'))
    with pytest.raises(capture.inputs.NativeMarketInputError, match='unrecognizable_source_price_date'):
        run(offline)
    assert set(saved) == {'attempt-00001.started.json', 'attempt-00001.refused.json'}


@pytest.mark.parametrize('at', ['2022-01-03garbage', '2022-01-03T00:00:00Z'])
@pytest.mark.usefixtures('portable_capture_platform')
def test_in_month_prefix_never_admits_unbound_suffix_or_timestamp_body(offline, monkeypatch, at):
    _, saved, responses, _ = offline
    responses.append(page([row(at=at)]))
    monkeypatch.setattr(capture, 'hash_bytes', lambda *args: pytest.fail('unbound scope body hashed'))
    with pytest.raises(capture.inputs.NativeMarketInputError, match='unrecognizable_source_price_date'):
        run(offline)
    assert set(saved) == {'attempt-00001.started.json', 'attempt-00001.refused.json'}


@pytest.fixture
def run_facade(offline, monkeypatch):
    root, stored, owned, keys = Path('/fabricated'), {}, set(), []
    monkeypatch.setattr(capture, 'CODE_FILES', ())
    monkeypatch.setattr(capture, '_git', lambda root, *args: args[-1])
    def prepare(path):
        if path in owned: raise FileExistsError('existing owned output')
        owned.add(path)
        return path
    def publish(directory, name, value):
        key = (directory, name)
        if key in stored: raise FileExistsError('existing immutable claim')
        stored[key] = value
    def key(path):
        keys.append(path)
        assert path == Path('/Users/sheltonchen/.config/trading-agent/sharadar.env')
        assert {'protocol.json', 'started.json'} <= {name for directory, name in stored}
        return KEY
    monkeypatch.setattr(capture, '_prepare_capture_directory', prepare)
    monkeypatch.setattr(capture, '_publish_json', publish)
    monkeypatch.setattr(capture, '_read_key', key)
    monkeypatch.setattr(capture, '_capture', lambda *args, **kwargs: {'status': 'fabricated_no_HTTP'})
    return root, stored, owned, keys


@pytest.mark.usefixtures('portable_capture_platform')
def test_duplicate_spent_global_claim_refuses_before_key_and_keeps_old_claim_immutable(run_facade):
    root, stored, owned, keys = run_facade
    claim = (root / capture.PARENT, 'budget-' + capture.claim_sha256() + '.json')
    stored[claim] = {'immutable': 'prior'}
    with pytest.raises(FileExistsError): capture.run(root, head=HEAD, remote=REMOTE)
    assert not keys and stored[claim] == {'immutable': 'prior'} and len(owned) == 1
    assert {name for directory, name in stored} == {claim[1], 'refused.json'}


@pytest.mark.usefixtures('portable_capture_platform')
def test_missing_known_protected_key_retains_owned_claim_start_zero_HTTP_refusal(run_facade, monkeypatch):
    root, stored, owned, _ = run_facade
    def unavailable(path): raise capture.CaptureRefusal('protected_file_unavailable')
    monkeypatch.setattr(capture, '_read_key', unavailable)
    with pytest.raises(capture.CaptureRefusal, match='protected_file_unavailable'):
        capture.run(root, head=HEAD, remote=REMOTE)
    assert len(owned) == 1 and {'protocol.json', 'started.json', 'refused.json'} <= {name for directory, name in stored}
    assert not any(name.startswith('attempt-') for directory, name in stored)


@pytest.mark.usefixtures('portable_capture_platform')
def test_existing_output_cannot_receive_new_refusal_or_key_read(run_facade):
    root, stored, owned, keys = run_facade
    owned.add(root / capture.PARENT / 'native-market-inputs-20261014T010000Z')
    with pytest.raises(FileExistsError): capture.run(root, head=HEAD, remote=REMOTE)
    assert not keys and not stored


def test_unsupported_host_is_first_before_key_output_or_transport(monkeypatch):
    def refuse(): raise capture.CaptureRefusal('unsupported_host')
    monkeypatch.setattr(capture, '_require_capture_platform', refuse)
    for name in ('_guard', '_read_key', '_prepare_capture_directory', '_http'):
        monkeypatch.setattr(capture, name, lambda *args, **kwargs: pytest.fail('after first host guard'))
    with pytest.raises(capture.CaptureRefusal, match='unsupported_host'):
        capture.run(Path('/fabricated'), head=HEAD, remote=REMOTE)
