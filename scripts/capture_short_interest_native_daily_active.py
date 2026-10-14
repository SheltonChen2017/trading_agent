"""PENDING ignored active-only daily reference producer, no operational CLI.

Eight independent dated chains at most. Every attempt/full response ceiling is
claimed durably before HTTP, every started chain drains, and incomplete daily
coverage can never become a successful full capture. Main supplies pinned code,
original custody and protected create-exclusive publication; no parser is forked.
"""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import threading
import urllib.request

from data.hashing import hash_bytes, hash_payload
from scripts.qualify_finra_short_interest import _require_capture_platform
from scripts.qualify_sharadar_companion import _guard, _http, _utc_now, SharadarCaptureRefusal
from scripts.short_interest_keychain import KeychainSecret, read_named_keychain
from scripts.capture_short_interest_native_grouped_market import build_protected_opener, _opener
import research.short_interest_etf.native_daily_active_reference as contract

PLAN_SHA256 = '029173c8fa4eeb6ff29f0325011aeec44eb4044ab504a2caddb011c6dba47ad8'
PROTOCOL_SHA256 = 'dc25d57e5b181c7028385ea689805e72b62a09c6e687cd11ac1eb6b7c5e139ce'


def protocol():
    return {'schema': 'si-daily-active-capture-prototype-protocol-v1',
        'plan_sha256': PLAN_SHA256, 'qualification_policy': contract.daily_active_policy(),
        'authentication': 'named_existing_Massive_Keychain_Bearer_header_memory_only',
        'source_guards': 'physical_root_branch_HEAD_status_matching_remote_frozen_code_calendar_original_custody',
        'budget': 'one_exclusive_whole_round_claim_before_key_attempt_and_whole_page_before_HTTP',
        'maximum_parallel_day_chains': contract.MAXIMUM_DAY_CHAINS,
        'concurrency': 'pages_serial_inside_each_active_only_day_chain',
        'fatal': 'stop_new_days_and_pages_drain_every_started_HTTP_no_automatic_retry',
        'publication': 'protected_owned_no_link_create_exclusive_serialized',
        'receipt_clocks': 'actual_per_attempt_not_logical_ordinal_replay_order',
        'proxies': False, 'redirects': False, 'automatic_retries': 0,
        'incomplete_daily_coverage': 'negative_never_empty_fabricated_completed_panel',
        'source_only': True, 'outcome_looks': 0, 'qc_attempts': 0}


def validated(plan):
    contract._require(type(plan) is contract.DailyActiveReferencePlan and plan.sha256 == PLAN_SHA256
        and plan.to_payload()['policy_sha256'] == hash_payload(contract.daily_active_policy())
        and hash_payload(protocol()) == PROTOCOL_SHA256,
        'daily_active_prospective_plan_or_protocol_pending_or_changed')


def capture_with_seams(root, directory, plan, index, *, head, remote, started_at,
        verify_sources, verify_code, claim_budget, publish, publish_json,
        read_secret=read_named_keychain, clock=_utc_now,
        lane_guard=None, transport=None, on_qualified_day=None):
    """Root-only injected prototype; no provider calls authorized by import.

    The concrete main must freeze exact pins and prove all custody/publication
    seams. Tests inject fictional credentials and fixed wire responses only.
    """
    _require_capture_platform()
    contract._require(type(index) is contract.CompositeNativeIndex, 'exact_source_index_required')
    began_at = contract._clock(started_at)
    fatal = threading.Event()
    state_lock, publication_lock = threading.RLock(), threading.RLock()
    capacity_changed = threading.Condition(state_lock)
    state = {'attempts': 0, 'http_invocations': 0, 'charged_bytes': 0,
             'reserved_bytes': 0, 'reserved_rows': 0, 'charged_rows': 0,
             'rows': 0, 'latest_start': began_at,
             'latest_receipt': began_at, 'publication_failed': False}
    days, attempts = {}, {}

    def guard():
        validated(plan)
        (_guard if lane_guard is None else lane_guard)(root, head, remote)
        verify_code(plan)
        verify_sources(plan, index)

    def store(name, value, raw=False):
        with publication_lock:
            guard()
            (publish if raw else publish_json)(directory, name, value)

    guard()
    claim_budget({'schema': 'si-daily-active-spent-whole-round-prototype-v1',
        'plan_sha256': plan.sha256, 'protocol_sha256': PROTOCOL_SHA256,
        'code_head': head, 'remote_head': remote, 'started_at': started_at,
        'maximum_attempts': contract.MAXIMUM_REQUESTS,
        'maximum_total_bytes': contract.MAXIMUM_TOTAL_BYTES,
        'maximum_total_rows': contract.MAXIMUM_ROWS,
        'maximum_day_chains': contract.MAXIMUM_DAY_CHAINS,
        'maximum_pages_per_day': contract.MAXIMUM_PAGES_PER_DAY,
        'restart_or_resumption_allowed': False})
    try:
        guard()
        secret = read_secret('massive')
        contract._require(type(secret) is KeychainSecret, 'redacted_existing_Massive_key_required')
    except Exception:
        ended = clock()
        contract._require(began_at <= contract._clock(ended), 'key_refusal_chronology')
        store('run.refused.json', {'schema': 'si-daily-active-preflight-refusal-v1',
            'code': 'guard_or_key_unavailable_after_spent_claim', 'started_at': started_at,
            'refused_at': ended, 'http_invocations': 0, 'attempts_claimed': 0,
            'complete_frozen_sequence': False, 'outcome_looks': 0, 'qc_attempts': 0})
        raise contract.DailyActiveReferenceError('REFUSED: guard_or_key_unavailable_after_spent_claim') from None

    def record_receipt(prefix, receipt):
        at = contract._clock(receipt['received_at'])
        contract._require(contract._clock(receipt['request_started_at']) <= at,
                          'daily_active_attempt_receipt_chronology')
        store(prefix + '.received.json', receipt)
        with state_lock:
            attempts[receipt['attempt']] = receipt
            state['latest_receipt'] = max(state['latest_receipt'], at)

    def request_page(day, date, ordinal, url):
        """Atomic budget reservations and durable attempt precede wire access."""
        with state_lock:
            if fatal.is_set():
                return None
            guard()
            while not fatal.is_set():
                # A successful in-flight page can free only its unused reserved
                # ceiling. Wait for that known byte/row accounting, not a retry
                # or reset of a consumed attempt/failed-body allowance.
                contract._require(state['attempts'] < contract.MAXIMUM_REQUESTS
                    and state['charged_bytes'] + contract.MAXIMUM_RESPONSE_BYTES <= contract.MAXIMUM_TOTAL_BYTES
                    and state['charged_rows'] + contract.MAXIMUM_PAGE_ROWS <= contract.MAXIMUM_ROWS,
                    'daily_active_whole_page_budget')
                if (state['charged_bytes'] + state['reserved_bytes'] + contract.MAXIMUM_RESPONSE_BYTES <= contract.MAXIMUM_TOTAL_BYTES
                    and state['charged_rows'] + state['reserved_rows'] + contract.MAXIMUM_PAGE_ROWS <= contract.MAXIMUM_ROWS):
                    break
                capacity_changed.wait(timeout=0.1)
            if fatal.is_set():
                return None
            guard()
            started = clock()
            at = contract._clock(started)
            contract._require(state['latest_start'] <= at, 'daily_active_start_clock_backdated')
            state['latest_start'] = at
            state['attempts'] += 1
            attempt = state['attempts']
            state['reserved_bytes'] += contract.MAXIMUM_RESPONSE_BYTES
            state['reserved_rows'] += contract.MAXIMUM_PAGE_ROWS
            prefix = f'day-{day:04d}-page-{ordinal:02d}'
            page_request = {'method': 'GET', 'url': url, 'authentication': 'Bearer_header_not_recorded'}
            request_sha = contract.page_request_sha256(url)
            try:
                store(prefix + '.started.json', {'schema': 'si-daily-active-request-start-v1',
                    'attempt': attempt, 'day_ordinal': day, 'query_date': date,
                    'page_ordinal': ordinal, 'request': page_request, 'request_sha256': request_sha,
                    'plan_sha256': plan.sha256, 'code_head': head,
                    'request_started_at': started, 'whole_page_bytes_reserved': contract.MAXIMUM_RESPONSE_BYTES,
                    'whole_page_rows_reserved': contract.MAXIMUM_PAGE_ROWS,
                    'global_attempts_claimed': state['attempts'],
                    'cumulative_bytes_charged_before': state['charged_bytes'],
                    'inflight_bytes_reserved_after': state['reserved_bytes'],
                    'cumulative_rows_charged_before': state['charged_rows'],
                    'inflight_rows_reserved_after': state['reserved_rows']})
            except Exception:
                # Claim is still consumed; no HTTP is started on a receipt fault.
                state['reserved_bytes'] -= contract.MAXIMUM_RESPONSE_BYTES
                state['reserved_rows'] -= contract.MAXIMUM_PAGE_ROWS
                state['publication_failed'] = True
                fatal.set()
                capacity_changed.notify_all()
                raise
        status, invoked, observed, retained, raw, media = None, False, False, False, None, None
        code = 'daily_active_page_refused'
        receipt = None
        decoded_rows = None
        try:
            guard()
            if fatal.is_set():
                code = 'cooperative_fatal_before_HTTP'
            else:
                opener = build_protected_opener(); _opener(opener)
                request = urllib.request.Request(url, method='GET', headers={
                    'Accept': 'application/json', 'Authorization': 'Bearer ' + secret.for_authorization_header()})
                def mark_http_start():
                    nonlocal invoked
                    with state_lock:
                        contract._require(invoked is False, 'one_HTTP_start_per_attempt')
                        contract._require(not fatal.is_set(), 'cooperative_fatal_before_HTTP')
                        state['http_invocations'] += 1
                        invoked = True
                if transport is None:
                    with state_lock:
                        if not fatal.is_set():
                            mark_http_start()
                    if invoked:
                        raw, media, status = _http(opener, request, contract.MAXIMUM_RESPONSE_BYTES)
                elif not fatal.is_set():
                    raw, media, status = transport(opener, request, contract.MAXIMUM_RESPONSE_BYTES,
                        on_http_start=mark_http_start)
                    contract._require(invoked is True, 'injected_transport_must_record_actual_HTTP_start')
                if invoked:
                    observed = type(raw) is bytes
                    contract._require(observed and len(raw) <= contract.MAXIMUM_RESPONSE_BYTES
                        and type(media) is str and len(media) <= 256
                        and type(status) is int and status == 200, 'bounded_daily_active_HTTP_response')
                    contract._require(not secret.echoed_in(raw) and not secret.echoed_in(media.encode()),
                                      'daily_active_secret_echo_discarded')
                    code = 'received'
            received = clock()
            receipt = {'schema': 'si-daily-active-page-received-v1', 'attempt': attempt,
                'day_ordinal': day, 'query_date': date, 'page_ordinal': ordinal,
                'request_sha256': request_sha, 'request_started_at': started,
                'received_at': received, 'http_invoked': invoked, 'http_status': status,
                'body_observed': observed, 'raw_path': None, 'raw_sha256': None,
                'raw_bytes': None, 'content_type': None, 'code': code}
            contract._require(contract._clock(started) <= contract._clock(received),
                              'daily_active_attempt_receipt_chronology')
            if code == 'received':
                # Retain bounded nonsecret raw even if the pure shape/chain
                # qualifier later refuses it. No licensed rows in diagnostics.
                digest = hash_bytes(raw)
                store(prefix + '.raw', raw, raw=True)
                retained = True
                receipt.update(raw_path=prefix + '.raw', raw_sha256=digest,
                               raw_bytes=len(raw), content_type=media)
                record_receipt(prefix, receipt)
                page = contract.CapturedDailyActiveReferencePage(date, ordinal, url, raw,
                    started, received, status, media)
                payload = contract.page_payload(raw)
                rows = len(payload['results'])
                decoded_rows = rows
                with state_lock:
                    state['rows'] += rows
                    contract._require(state['rows'] <= contract.MAXIMUM_ROWS, 'daily_active_row_budget')
                next_value = payload.get('next_url')
                next_page = None if next_value is None else contract.next_url(next_value, date)
                return page, next_page, received
            record_receipt(prefix, receipt)
            return None
        except Exception as error:
            fatal.set()
            if type(error) is SharadarCaptureRefusal:
                status = error.http_status
            # No error body, exception detail, response headers or keys escape.
            failed = clock()
            contract._require(contract._clock(started) <= contract._clock(failed),
                              'daily_active_failure_clock')
            refusal = {'schema': 'si-daily-active-page-refusal-v1', 'attempt': attempt,
                'day_ordinal': day, 'query_date': date, 'page_ordinal': ordinal,
                'request_sha256': request_sha, 'request_started_at': started,
                'received_at': failed, 'http_invoked': invoked,
                'http_status': status if type(status) is int and 100 <= status <= 599 else None,
                'body_observed': observed, 'raw_retained': retained,
                'code': 'daily_active_page_or_chain_refused'}
            try:
                store(prefix + '.refused.json', refusal)
                if receipt is None or attempt not in attempts:
                    refusal.update(raw_path=prefix + '.raw' if retained else None,
                        raw_sha256=hash_bytes(raw) if retained else None,
                        raw_bytes=len(raw) if retained else None, content_type=media if retained else None)
                    with state_lock:
                        attempts[attempt] = refusal
                        state['latest_receipt'] = max(state['latest_receipt'], contract._clock(failed))
            except Exception:
                with state_lock:
                    state['publication_failed'] = True
            return None
        finally:
            with state_lock:
                state['reserved_bytes'] -= contract.MAXIMUM_RESPONSE_BYTES
                state['reserved_rows'] -= contract.MAXIMUM_PAGE_ROWS
                # Unknown/rejected response spends its full ceiling; it is not
                # released as a new budget. No HTTP invocation consumes zero.
                state['charged_bytes'] += len(raw) if retained else (contract.MAXIMUM_RESPONSE_BYTES if invoked else 0)
                state['charged_rows'] += decoded_rows if decoded_rows is not None else (contract.MAXIMUM_PAGE_ROWS if invoked else 0)
                capacity_changed.notify_all()

    def day_chain(day, day_start):
        date = plan.sessions()[day - 1]
        pages, seen = [], set()
        url = contract.first_url(plan, day)
        last = day_start
        try:
            for ordinal in range(1, contract.MAXIMUM_PAGES_PER_DAY + 1):
                if fatal.is_set():
                    break
                contract._require(url not in seen, 'daily_active_repeated_cursor')
                seen.add(url)
                result = request_page(day, date, ordinal, url)
                if result is None:
                    break
                page, url, last = result
                pages.append(page)
                if url is None:
                    qualified = contract.qualify_daily_active_reference(plan, day, tuple(pages), index,
                        started_at=day_start, retrieved_at=last)
                    if on_qualified_day is not None:
                        on_qualified_day(qualified)
                    raw = qualified.to_bytes()
                    store(f'day-{day:04d}.qualified.private.json', raw, raw=True)
                    value = {'schema': 'si-daily-active-day-result-v1', 'day_ordinal': day,
                        'query_date': date, 'started_at': day_start, 'retrieved_at': last,
                        'pages_received': len(pages), 'complete_advertised_chain': True,
                        'qualification_path': f'day-{day:04d}.qualified.private.json',
                        'qualification_sha256': hash_bytes(raw), 'source_admitted': False}
                    store(f'day-{day:04d}.completed.json', value)
                    return value
                contract._require(ordinal < contract.MAXIMUM_PAGES_PER_DAY, 'daily_active_page_limit')
        except Exception:
            fatal.set()
        ended = clock()
        contract._require(contract._clock(last) <= contract._clock(ended), 'daily_active_day_failure_chronology')
        value = {'schema': 'si-daily-active-day-result-v1', 'day_ordinal': day,
            'query_date': date, 'started_at': day_start, 'retrieved_at': ended,
            'pages_received': len(pages), 'complete_advertised_chain': False,
            'qualification_path': None, 'qualification_sha256': None,
            'code': 'halted_incomplete_or_refused_day_chain', 'source_admitted': False}
        try:
            store(f'day-{day:04d}.refused.json', value)
        except Exception:
            with state_lock:
                state['publication_failed'] = True
        return value

    total, next_day, pending = len(plan.sessions()), 1, {}
    with ThreadPoolExecutor(max_workers=contract.MAXIMUM_DAY_CHAINS) as pool:
        while pending or next_day <= total:
            while not fatal.is_set() and next_day <= total and len(pending) < contract.MAXIMUM_DAY_CHAINS:
                try:
                    guard()
                    if fatal.is_set():
                        break
                    day_start = clock()
                    contract._require(began_at <= contract._clock(day_start), 'daily_active_day_start_clock')
                    store(f'day-{next_day:04d}.started.json', {'schema': 'si-daily-active-day-start-v1',
                        'day_ordinal': next_day, 'query_date': plan.sessions()[next_day - 1],
                        'started_at': day_start, 'plan_sha256': plan.sha256})
                    pending[pool.submit(day_chain, next_day, day_start)] = next_day
                    next_day += 1
                except Exception:
                    fatal.set()
                    with state_lock:
                        state['publication_failed'] = True
            if not pending:
                break
            complete, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
            for future in sorted(complete, key=lambda f: pending[f]):
                day = pending.pop(future)
                try:
                    value = future.result()
                    contract._require(value['day_ordinal'] == day, 'daily_active_worker_day_changed')
                    days[day] = value
                except Exception:
                    fatal.set()
                    with state_lock:
                        state['publication_failed'] = True
    contract._require(not pending and state['reserved_bytes'] == state['reserved_rows'] == 0,
                      'daily_active_started_requests_not_drained')
    done = clock()
    contract._require(state['latest_receipt'] <= contract._clock(done), 'daily_active_final_clock')
    complete_sequence = (not fatal.is_set() and not state['publication_failed']
        and len(days) == total and set(days) == set(range(1, total + 1))
        and len(attempts) == state['attempts']
        and all(d['complete_advertised_chain'] for d in days.values()))
    value = {'schema': 'si-daily-active-capture-inventory-prototype-v1',
        'plan_sha256': plan.sha256, 'protocol_sha256': PROTOCOL_SHA256,
        'started_at': started_at, 'retrieved_at': done, 'planned_days': total,
        'days_started': next_day - 1, 'days_returned': len(days),
        'attempts_claimed': state['attempts'], 'http_invocations': state['http_invocations'],
        'charged_bytes': state['charged_bytes'], 'charged_rows': state['charged_rows'], 'rows': state['rows'],
        'attempts': [attempts[k] for k in sorted(attempts)], 'days': [days[k] for k in sorted(days)],
        'halted': fatal.is_set(), 'publication_failed': state['publication_failed'],
        'complete_frozen_sequence': complete_sequence, 'source_admitted': False,
        'historical_identity_admitted': False, 'outcome_looks': 0, 'qc_attempts': 0,
        'ready_for_empirical_backtest': False}
    store('inventory.private.json', value)
    if state['publication_failed']:
        raise contract.DailyActiveReferenceError('REFUSED: daily_active_publication_failed_after_drain')
    return value


def main():
    raise contract.DailyActiveReferenceError('REFUSED: pending_ignored_daily_active_prototype_no_operational_entrypoint')
