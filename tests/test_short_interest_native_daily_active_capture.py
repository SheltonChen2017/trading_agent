"""Offline fictional reference transport; no source, keys, QC or network."""
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import io
import json
from pathlib import Path
import threading
from urllib.parse import parse_qsl, urlsplit
import zipfile

import pytest

from data.hashing import canonical_json, hash_payload
from data.exchange_calendar import _schedule
import research.short_interest_etf.native_dated_identity as identity
import research.short_interest_etf.sharadar_securities_master as master
from scripts.qualify_sharadar_companion import SharadarCaptureRefusal
from scripts.short_interest_keychain import KeychainSecret
import research.short_interest_etf.native_daily_active_reference as contract
from scripts import capture_short_interest_native_daily_active as runtime

SECRET = 'FABRICATED-DAILY-ACTIVE-TOKEN/42'
START = '2026-10-14T01:00:00Z'
EMPTY = b'{"status":"OK","results":[]}'


@lru_cache(maxsize=1)
def sessions():
    return tuple(index.date().isoformat() for index in _schedule(date(2022, 1, 3), date(2026, 8, 31)).index)


def native_index():
    rows = ('table,permaticker,ticker,exchange,isdelisted,category,figi\n'
            'stocks,1,SYN,XNYS,N,Domestic Common Stock Primary Class,BBG000000001\n')
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED) as archive:
        archive.writestr('tickers.csv', rows)
    captured = master.CapturedSharadarMasterArchive('tickers', output.getvalue(), master.request_sha256('download-tickers'))
    return identity.build_composite_native_index(captured)


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 14, 1, tzinfo=timezone.utc)
        self.lock = threading.Lock()
    def __call__(self):
        with self.lock:
            self.value += timedelta(microseconds=1)
            return self.value.isoformat().replace('+00:00', 'Z')


def setup(monkeypatch):
    plan = contract.freeze_daily_active_plan(sessions(), calendar_sha256='a' * 64)
    index = native_index()
    monkeypatch.setattr(runtime, '_guard', lambda *_args: None)
    monkeypatch.setattr(runtime, 'PLAN_SHA256', plan.sha256)
    monkeypatch.setattr(runtime, 'PROTOCOL_SHA256', hash_payload(runtime.protocol()))
    saved, events, calls, lock = {}, [], [], threading.RLock()
    def publish(directory, name, value):
        with lock:
            assert name not in saved
            saved[name] = value
    def key(provider):
        assert events == ['whole-claim'] and provider == 'massive'
        events.append('key')
        return KeychainSecret(SECRET)
    def claim(value):
        events.append('whole-claim')
        assert value['maximum_attempts'] == 1169 * 64
        assert value['maximum_total_bytes'] == contract.MAXIMUM_TOTAL_BYTES
    def http(opener, request, maximum):
        with lock:
            calls.append(request)
            starts = [v for n, v in saved.items() if n.endswith('.started.json') and 'page_ordinal' in v]
        assert any(v['request']['url'] == request.full_url for v in starts)
        assert all(v['whole_page_bytes_reserved'] == 2 * 1024 * 1024
                   and v['whole_page_rows_reserved'] == 1000 for v in starts)
        assert request.get_header('Authorization') == 'Bearer ' + SECRET
        assert SECRET not in request.full_url and 'apiKey=' not in request.full_url
        assert maximum == 2 * 1024 * 1024
        return EMPTY, 'application/json', 200
    monkeypatch.setattr(runtime, '_http', http)
    def sources(p, i):
        p._guard(); i._guard()
    kwargs = {'head': 'b' * 40, 'remote': 'c' * 40, 'started_at': START,
        'verify_sources': sources, 'verify_code': lambda p: p._guard(),
        'claim_budget': claim, 'publish': publish, 'publish_json': publish,
        'read_secret': key, 'clock': Clock()}
    return plan, index, kwargs, saved, events, calls


def run(case):
    plan, index, kwargs, *_ = case
    return runtime.capture_with_seams(Path('/fabricated/root'), Path('/fabricated/protected-capture'),
        plan, index, **kwargs)


def test_all1169_actual_advertised_fabricated_day_chains_complete_only_active_panel(monkeypatch):
    case = setup(monkeypatch)
    value = run(case)
    plan, _, _, saved, events, calls = case
    assert events == ['whole-claim', 'key']
    assert value['complete_frozen_sequence'] is True and value['halted'] is False
    assert value['planned_days'] == value['days_started'] == value['days_returned'] == 1169
    assert value['attempts_claimed'] == value['http_invocations'] == len(calls) == 1169
    assert value['charged_bytes'] == len(EMPTY) * 1169 and value['charged_rows'] == value['rows'] == 0
    assert value['ready_for_empirical_backtest'] is False and value['outcome_looks'] == value['qc_attempts'] == 0
    assert {dict(parse_qsl(urlsplit(r.full_url).query))['active'] for r in calls} == {'true'}
    assert len([n for n in saved if n.endswith('.completed.json')]) == 1169
    assert all(d['complete_advertised_chain'] for d in value['days'])


def gated_failure(monkeypatch, case, failure):
    _, _, kwargs, saved, _, calls = case
    gate, failure_saved, lock = threading.Event(), threading.Event(), threading.Lock()
    publish = kwargs['publish_json']
    def observer(directory, name, value):
        publish(directory, name, value)
        if name == 'day-0001-page-01.refused.json':
            failure_saved.set()
    kwargs['publish_json'] = observer
    def http(opener, request, maximum):
        with lock:
            calls.append(request)
            if len(calls) == 8:
                gate.set()
        assert gate.wait(3)
        first = 'date=' + sessions()[0] in request.full_url
        if first:
            return failure() if callable(failure) else failure
        assert failure_saved.wait(3)
        return EMPTY, 'application/json', 200
    monkeypatch.setattr(runtime, '_http', http)


@pytest.mark.parametrize('status', [403, 429, 500, None])
def test_fatal_stops_new_days_drains_all8_and_retains_failure_status_no_body(monkeypatch, status):
    case = setup(monkeypatch)
    def failure():
        raise SharadarCaptureRefusal('fabricated_HTTP_refusal', status=status)
    gated_failure(monkeypatch, case, failure)
    value = run(case)
    _, _, _, saved, _, calls = case
    assert len(calls) == value['http_invocations'] == value['attempts_claimed'] == 8
    assert value['days_started'] == value['days_returned'] == 8
    assert value['complete_frozen_sequence'] is False and value['halted'] is True
    failed = saved['day-0001-page-01.refused.json']
    assert failed['http_status'] == status and failed['body_observed'] is False
    assert value['charged_bytes'] == contract.MAXIMUM_RESPONSE_BYTES + len(EMPTY) * 7
    assert value['charged_rows'] == contract.MAXIMUM_PAGE_ROWS
    assert not any(n.startswith('day-0009') for n in saved)
    assert len(value['attempts']) == 8


@pytest.mark.parametrize('kind', ['ASCII', 'Unicode', 'percent', 'slash', 'media'])
def test_echo_discard_precedes_hash_and_publication_all_started_work_drained(monkeypatch, kind):
    from urllib.parse import quote
    case = setup(monkeypatch)
    raw = {'ASCII': SECRET.encode(), 'Unicode': ''.join('\\u%04x' % ord(c) for c in SECRET).encode(),
           'percent': quote(SECRET, safe='').encode(), 'slash': SECRET.replace('/', '\\/').encode(),
           'media': b'{}'}[kind]
    media = SECRET if kind == 'media' else 'application/json'
    real_hash = runtime.hash_bytes
    def no_secret_hash(value):
        assert value != raw
        return real_hash(value)
    monkeypatch.setattr(runtime, 'hash_bytes', no_secret_hash)
    gated_failure(monkeypatch, case, (raw, media, 200))
    result = run(case)
    saved = case[3]
    assert result['complete_frozen_sequence'] is False
    assert 'day-0001-page-01.raw' not in saved and 'day-0001.qualified.private.json' not in saved
    assert saved['day-0001-page-01.refused.json']['body_observed'] is True
    assert all(SECRET not in canonical_json(v) for n, v in saved.items() if not n.endswith('.raw') and type(v) is dict)


@pytest.mark.parametrize('bad', [b'not JSON', b'{"status":"OK","results":[],"count":1}',
    b'{"status":"OK","status":"OK","results":[]}', b'{"status":"OK","results":{},"next_url":null}'])
def test_bounded_nonsecret_bad_shape_raw_is_retained_but_day_and_full_capture_refuse(monkeypatch, bad):
    case = setup(monkeypatch)
    gated_failure(monkeypatch, case, (bad, 'application/json', 200))
    result = run(case)
    assert result['complete_frozen_sequence'] is False
    assert case[3]['day-0001-page-01.raw'] == bad
    assert case[3]['day-0001-page-01.received.json']['body_observed'] is True
    assert 'day-0001.qualified.private.json' not in case[3]


def test_serial_cursor_inside_day_exact_chain_while8_days_overlap(monkeypatch):
    case = setup(monkeypatch)
    first_date = sessions()[0]
    next_url = contract.ENDPOINT + '?cursor=fabricated-next-page'
    first_raw = canonical_json({'status': 'OK', 'results': [], 'next_url': next_url}).encode()
    original = runtime._http
    def http(opener, request, maximum):
        if 'date=' + first_date in request.full_url:
            case[5].append(request)
            return first_raw, 'application/json', 200
        if request.full_url == next_url:
            assert 'day-0001-page-01.received.json' in case[3]
            case[5].append(request)
            return EMPTY, 'application/json', 200
        return original(opener, request, maximum)
    monkeypatch.setattr(runtime, '_http', http)
    value = run(case)
    assert value['complete_frozen_sequence'] is True and value['attempts_claimed'] == 1170
    assert case[3]['day-0001.completed.json']['pages_received'] == 2


@pytest.mark.parametrize('url', ['https://outside.invalid/v3/reference/tickers?cursor=x',
    contract.ENDPOINT + '?cursor=x&apiKey=other-secret', contract.ENDPOINT + '?cursor=x&active=false',
    contract.ENDPOINT + '?cursor=x&date=2027-01-01', contract.ENDPOINT + '?cursor=x&limit=2000'])
def test_unsafe_cursor_retained_private_never_followed_or_reported_complete(monkeypatch, url):
    case = setup(monkeypatch)
    raw = canonical_json({'status': 'OK', 'results': [], 'next_url': url}).encode()
    gated_failure(monkeypatch, case, (raw, 'application/json', 200))
    value = run(case)
    assert value['complete_frozen_sequence'] is False
    assert case[3]['day-0001-page-01.raw'] == raw
    assert all(request.full_url != url for request in case[5])


def test_unterminated64page_chain_never_calls65_or_completes_any_missing_day(monkeypatch):
    monkeypatch.setattr(contract, 'MAXIMUM_DAY_CHAINS', 1)  # Explicit smaller fabricated scheduling fixture.
    case = setup(monkeypatch)
    def http(opener, request, maximum):
        case[5].append(request)
        following = contract.ENDPOINT + '?cursor=fabricated-page-' + str(len(case[5]) + 1)
        return canonical_json({'status': 'OK', 'results': [], 'next_url': following}).encode(), 'application/json', 200
    monkeypatch.setattr(runtime, '_http', http)
    value = run(case)
    assert len(case[5]) == value['attempts_claimed'] == 64
    assert value['days_started'] == 1 and value['complete_frozen_sequence'] is False
    assert 'day-0001.completed.json' not in case[3] and 'day-0001.qualified.private.json' not in case[3]
    assert 'day-0001.refused.json' in case[3]


def test_no_complete_or_source_admission_can_be_supplied_as_boolean(monkeypatch):
    case = setup(monkeypatch)
    monkeypatch.setattr(runtime, 'PLAN_SHA256', 'PENDING')
    with pytest.raises(contract.DailyActiveReferenceError, match='pending_or_changed'):
        run(case)
    assert case[4] == [] and case[5] == [] and case[3] == {}
    with pytest.raises(contract.DailyActiveReferenceError, match='no_operational_entrypoint'):
        runtime.main()


def test_failed_key_retains_consumed_whole_claim_zero_HTTP_without_secret_diagnostics(monkeypatch):
    case = setup(monkeypatch)
    def key(_provider):
        raise RuntimeError(SECRET)
    case[2]['read_secret'] = key
    with pytest.raises(contract.DailyActiveReferenceError) as error:
        run(case)
    assert SECRET not in str(error.value) and case[4] == ['whole-claim'] and case[5] == []
    assert case[3]['run.refused.json']['attempts_claimed'] == 0


def test_missing_terminal_receipt_or_publication_failure_never_completes_and_drains(monkeypatch):
    case = setup(monkeypatch)
    original = case[2]['publish']
    def broken(directory, name, value):
        if name == 'day-0001-page-01.raw':
            raise OSError('fixture custody failure')
        original(directory, name, value)
    case[2]['publish'] = broken
    result = run(case)
    assert result['complete_frozen_sequence'] is False and result['halted'] is True
    assert result['attempts_claimed'] == len(result['attempts'])
    assert 'day-0001-page-01.refused.json' in case[3]


def test_native_worker_high_water_is_exactly8_not_more_and_all_chains_drain(monkeypatch):
    case = setup(monkeypatch)
    active, peak = 0, 0
    gate, lock = threading.Event(), threading.Lock()
    def http(opener, request, maximum):
        nonlocal active, peak
        with lock:
            case[5].append(request)
            active += 1; peak = max(peak, active)
            if active == 8:
                gate.set()
        assert gate.wait(3)
        with lock:
            active -= 1
        return EMPTY, 'application/json', 200
    monkeypatch.setattr(runtime, '_http', http)
    result = run(case)
    assert peak == 8 and active == 0 and result['http_invocations'] == 1169
    assert result['complete_frozen_sequence'] is True


def test_actual_receipt_clock_inversion_across_days_is_kept_not_fabricated(monkeypatch):
    case = setup(monkeypatch)
    second_retained = threading.Event()
    original_publish = case[2]['publish_json']
    def publish(directory, name, value):
        original_publish(directory, name, value)
        if name == 'day-0002-page-01.received.json':
            second_retained.set()
    case[2]['publish_json'] = publish
    def http(opener, request, maximum):
        case[5].append(request)
        if 'date=' + sessions()[0] in request.full_url:
            assert second_retained.wait(3)
        return EMPTY, 'application/json', 200
    monkeypatch.setattr(runtime, '_http', http)
    result = run(case)
    assert result['complete_frozen_sequence'] is True
    first = case[3]['day-0001-page-01.received.json']
    second = case[3]['day-0002-page-01.received.json']
    assert first['received_at'] > second['received_at']
    assert first['request_started_at'] <= first['received_at']
    assert second['request_started_at'] <= second['received_at']


@pytest.mark.parametrize('budget', ['bytes', 'rows'])
def test_fullpage_reservation_blocks_extra_HTTP_until_unused_success_ceiling_is_known(monkeypatch, budget):
    # Smaller explicit fabricated allowance: enough actual empty bodies for
    # all1169 days but only one full page may be admitted concurrently.
    if budget == 'bytes':
        monkeypatch.setattr(contract, 'MAXIMUM_TOTAL_BYTES', contract.MAXIMUM_RESPONSE_BYTES + len(EMPTY) * 1169)
    else:
        monkeypatch.setattr(contract, 'MAXIMUM_ROWS', contract.MAXIMUM_PAGE_ROWS)
    case = setup(monkeypatch)
    active, peak = 0, 0
    lock = threading.Lock()
    eight_days_started = threading.Event()
    original_publish = case[2]['publish_json']
    def publish(directory, name, value):
        original_publish(directory, name, value)
        if name == 'day-0008.started.json':
            eight_days_started.set()
        if 'page_ordinal' in value and name.endswith('.started.json'):
            assert value['cumulative_bytes_charged_before'] + value['inflight_bytes_reserved_after'] <= contract.MAXIMUM_TOTAL_BYTES
            assert value['cumulative_rows_charged_before'] + value['inflight_rows_reserved_after'] <= contract.MAXIMUM_ROWS
    case[2]['publish_json'] = publish
    def http(opener, request, maximum):
        nonlocal active, peak
        with lock:
            case[5].append(request)
            active += 1; peak = max(peak, active)
            first = len(case[5]) == 1
        # Peak proof is causal reservation accounting, not a wall-time limit.
        if first:
            assert eight_days_started.wait(3)
        with lock:
            active -= 1
        return EMPTY, 'application/json', 200
    monkeypatch.setattr(runtime, '_http', http)
    result = run(case)
    assert peak == 1 and active == 0 and result['complete_frozen_sequence'] is True
    assert result['attempts_claimed'] == result['http_invocations'] == 1169
    assert result['charged_bytes'] == 1169 * len(EMPTY) and result['charged_rows'] == 0


@pytest.mark.parametrize('budget', ['bytes', 'rows'])
def test_smaller_than_fullpage_allowance_never_invokes_HTTP_or_fakes_completed_days(monkeypatch, budget):
    if budget == 'bytes':
        monkeypatch.setattr(contract, 'MAXIMUM_TOTAL_BYTES', contract.MAXIMUM_RESPONSE_BYTES - 1)
    else:
        monkeypatch.setattr(contract, 'MAXIMUM_ROWS', contract.MAXIMUM_PAGE_ROWS - 1)
    case = setup(monkeypatch)
    result = run(case)
    assert result['attempts_claimed'] == result['http_invocations'] == 0
    assert result['halted'] is True and result['complete_frozen_sequence'] is False
    assert not any(n.endswith('.completed.json') for n in case[3])


def test_request_receipt_custody_failure_claims_no_HTTP_and_drain_never_emits_success(monkeypatch):
    case = setup(monkeypatch)
    original = case[2]['publish_json']
    def publish(directory, name, value):
        if name == 'day-0001-page-01.started.json':
            raise OSError('fabricated exclusive-storage failure')
        original(directory, name, value)
    case[2]['publish_json'] = publish
    with pytest.raises(contract.DailyActiveReferenceError, match='publication_failed_after_drain'):
        run(case)
    value = case[3]['inventory.private.json']
    assert value['publication_failed'] is True and value['complete_frozen_sequence'] is False
    assert value['attempts_claimed'] >= value['http_invocations']
    assert not any('date=' + sessions()[0] in r.full_url for r in case[5])
