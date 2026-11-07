"""Bounded monthly direct-Sharadar source capture; no strategy or outcome join."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import urllib.parse
import urllib.request

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_market_input_protocol as inputs
from scripts.qualify_finra_short_interest import (
    CaptureRefusal, _NoRedirect, _git, _prepare_capture_directory, _publish, _publish_json, _require_capture_platform,
)
from scripts.qualify_sharadar_companion import _guard, _http, _read_key, _utc_now
from scripts.qualify_short_interest_action_supplement import _clock
from scripts.short_interest_keychain import KeychainSecret, ShortInterestKeychainError

PARENT = Path('artifacts/short_interest/native_market_inputs')
CREDENTIAL_PATH = Path('/Users/sheltonchen/.config/trading-agent/sharadar.env')
CODE_FILES = ('data/hashing.py', 'ml/immutable_io.py', 'scripts/qualify_finra_short_interest.py',
              'scripts/qualify_sharadar_companion.py', 'scripts/qualify_short_interest_action_supplement.py',
              'scripts/short_interest_keychain.py', 'research/short_interest_etf/native_market_input_protocol.py',
              'scripts/capture_short_interest_native_market_inputs.py')
EXPECTED_PROTOCOL_SHA256 = 'b95ecfeefdc8b0bd01a7cb9fd1ea7b250e777356a2db8f7a026810899e7582b1'


class NativeMarketCaptureRefusal(CaptureRefusal):
    pass


def _require(value, code):
    if not value:
        raise NativeMarketCaptureRefusal(code)


def protocol():
    return inputs.market_input_protocol()


def _policy():
    value = protocol()
    _require(hash_payload(value) == EXPECTED_PROTOCOL_SHA256, 'prospective_market_protocol_pending_or_changed')
    return value


def claim_sha256():
    return hash_payload({'schema': 'si-native-market-input-claim-v1', 'source': 'direct_Sharadar',
                         'first_date': inputs.FIRST_DATE, 'last_date': inputs.LAST_DATE,
                         'tables': list(inputs.TABLES), 'fields': {key: list(value) for key, value in inputs.FIELDS.items()},
                         'population': 'all_reported_no_ticker_current_active_or_financial_screen'})


def _capture(root, directory, opener, secret, *, head, remote, started_at):
    _require_capture_platform()
    frozen = _policy()
    _require(type(secret) is KeychainSecret, 'exact_redacted_credential_required')
    previous = _clock(started_at)
    attempts, total_rows, total_bytes, panels = 0, 0, 0, []
    def publish(name, value, raw=False):
        _require(_policy() == frozen, 'market_capture_scope_changed')
        _guard(root, head, remote)
        (_publish if raw else _publish_json)(directory, name, value)
    for panel in frozen['panels']:
        table, month = panel['table'], panel['month']
        pages, groups, refusals, previous_date = [], {}, [], None
        for page_number in range(frozen['maximum_pages_per_table_month']):
            _require(_policy() == frozen, 'market_capture_scope_changed')
            _require(attempts < frozen['maximum_requests']
                     and total_rows + frozen['page_limit'] <= frozen['maximum_total_rows']
                     and total_bytes + frozen['maximum_response_bytes'] <= frozen['maximum_total_raw_bytes'],
                     'whole_next_page_request_budget_exhausted')
            spec = inputs.page_request(table, month, page_number)
            expected = json.loads(canonical_json(panel['initial_request']))
            expected['params']['offset'] = str(page_number * frozen['page_limit'])
            _require(canonical_json(spec) == canonical_json(expected), 'market_request_descriptor_binding')
            url = spec['url'] + '?' + urllib.parse.urlencode(spec['params'])
            began = _utc_now()
            _require(previous <= _clock(began), 'market_request_chronology')
            attempts += 1
            prefix, digest, status = f'attempt-{attempts:05d}', hash_payload(spec), None
            publish(prefix + '.started.json', {'schema': 'si-native-market-request-start-v1', 'attempt': attempts,
                'table': table, 'month': month, 'page': page_number, 'request': spec, 'request_sha256': digest,
                'code_head': head, 'protocol_sha256': EXPECTED_PROTOCOL_SHA256, 'started_at': began})
            try:
                _require(_policy() == frozen, 'market_capture_scope_changed')
                _guard(root, head, remote)
                request = urllib.request.Request(url, method='GET', headers={
                    'Accept': 'application/json', 'x-api-key': secret.for_authorization_header()})
                raw, media, status = _http(opener, request, frozen['maximum_response_bytes'])
                _require(type(raw) is bytes and len(raw) <= frozen['maximum_response_bytes']
                         and type(media) is str and len(media) <= 4096, 'market_response_types_or_bytes')
                _require(not secret.echoed_in(raw) and not secret.echoed_in(media.encode()), 'credential_echo_refused')
                received = _utc_now()
                _require(_clock(began) <= _clock(received), 'market_response_chronology')
                _require(type(status) is int and status == 200
                         and media.split(';', 1)[0].strip().lower() == 'application/json', 'market_HTTP_or_media_refused')
                rows = inputs.decode_page(raw)
                inputs.verify_page_dates(rows, month=month)
                publish(prefix + '.raw', raw, True)
                raw_sha256 = hash_bytes(raw)
                receipt = {'schema': 'si-native-market-response-v1', 'attempt': attempts, 'request_sha256': digest,
                    'http_status': status, 'content_type': media, 'raw_path': prefix + '.raw',
                    'raw_sha256': raw_sha256, 'raw_bytes': len(raw), 'received_at': received}
                publish(prefix + '.received.json', receipt)
                observations, previous_date = inputs.inspect_page(rows, table=table, month=month, previous_date=previous_date)
                issues, duplicate_events = [], {}
                for row_index, slot, reason in observations:
                    origin = {'attempt': attempts, 'row_index': row_index, 'source_file_sha256': raw_sha256}
                    if reason is not None:
                        issue = {'source_origin': origin, 'reason': reason}
                        issues.append(issue)
                        refusals.append(issue)
                    if slot is not None:
                        peers = groups.setdefault(slot, [])
                        peers.append(origin)
                        if len(peers) > 1:
                            event = duplicate_events.setdefault(slot, {'source_key': {
                                'table': table, 'ticker': slot[0], 'date': slot[1]},
                                'reason': 'all_identifiable_duplicate_copies_quarantined',
                                'first_source_origin': peers[0], 'new_source_origins': []})
                            event['new_source_origins'].append(origin)
                issues.extend(duplicate_events.values())
                publish(prefix + '.refusals.private.json', {'schema': 'si-native-market-page-refusals-v1',
                    'attempt': attempts, 'request_sha256': digest, 'raw_sha256': raw_sha256, 'refusals': issues,
                    'financial_values_normalized': False, 'signal_or_return_computed': False})
                count = len(rows)
                total_rows += count
                total_bytes += len(raw)
                previous = _clock(received)
                pages.append({'attempt': attempts, 'request': spec, 'receipt': receipt, 'row_count': count})
                if count < frozen['page_limit']:
                    break
                _require(page_number + 1 < frozen['maximum_pages_per_table_month'], 'table_month_page_budget_exhausted')
            except (CaptureRefusal, inputs.NativeMarketInputError, ShortInterestKeychainError, ValueError, TypeError, OSError, KeyError) as error:
                status = status if type(status) is int else getattr(error, 'http_status', None)
                publish(prefix + '.refused.json', {'schema': 'si-native-market-request-refusal-v1', 'attempt': attempts,
                    'table': table, 'month': month, 'page': page_number, 'http_status': status,
                    'code': 'market_source_contract_or_transport_refused', 'refused_at': _utc_now()})
                raise
        panels.append({'table': table, 'month': month, 'pages': pages, 'malformed_refusals': refusals,
            'duplicate_groups': [{'source_key': {'table': table, 'ticker': key[0], 'date': key[1]},
                'reason': 'all_identifiable_duplicate_copies_quarantined', 'source_origins': origins}
                for key, origins in groups.items() if len(origins) > 1]})
    retrieved = _utc_now()
    _require(previous <= _clock(retrieved) and _policy() == frozen, 'market_inventory_chronology_or_scope')
    report = {'schema': 'si-native-market-input-inventory-v1', 'code_head': head,
        'protocol_sha256': EXPECTED_PROTOCOL_SHA256, 'retrieved_at': retrieved, 'panels': panels,
        'total_raw_bytes': total_bytes, 'total_raw_rows': total_rows, 'http_attempts': attempts,
        'source_only': True, 'data_or_fitness_admitted': False, 'financial_values_normalized': False,
        'signal_or_return_computed': False, 'outcome_looks': 0, 'qc_attempts': 0, 'backtest_result_exists': False}
    report['report_sha256'] = hash_payload(report)
    publish('inventory.private.json', report)
    completed = _utc_now()
    _require(_clock(retrieved) <= _clock(completed), 'market_completion_chronology')
    result = {'schema': 'si-native-market-input-complete-v1', 'status': 'private_market_source_capture_complete',
        'code_head': head, 'protocol_sha256': EXPECTED_PROTOCOL_SHA256, 'http_attempts': attempts,
        'private_report_sha256': report['report_sha256'], 'completed_at': completed,
        'outcome_looks': 0, 'qc_attempts': 0, 'backtest_result_exists': False}
    publish('completed.json', result)
    return result


def run(root, *, head, remote):
    _require_capture_platform()
    _guard(root, head, remote)
    frozen = _policy()
    began = _utc_now()
    target = root / PARENT / ('native-market-inputs-' + _clock(began).strftime('%Y%m%dT%H%M%SZ'))
    _require(_git(root, 'check-ignore', str(target)) == str(target), 'market_capture_not_ignored')
    _guard(root, head, remote)
    directory = _prepare_capture_directory(target)
    def publish(owner, name, value):
        _require(_policy() == frozen, 'market_capture_scope_changed')
        _guard(root, head, remote)
        _publish_json(owner, name, value)
    try:
        publish(directory.parent, 'budget-' + claim_sha256() + '.json', {
            'schema': 'si-native-market-input-budget-v1', 'claim_sha256': claim_sha256(),
            'code_head': head, 'remote_head': remote, 'run_id': directory.name,
            'protocol_sha256': EXPECTED_PROTOCOL_SHA256, 'maximum_requests': frozen['maximum_requests'],
            'started_at': began, 'restart_or_resume': False})
        publish(directory, 'protocol.json', frozen)
        files = []
        for name in CODE_FILES:
            _require(_policy() == frozen, 'market_capture_scope_changed')
            _guard(root, head, remote)
            files.append({'path': name, 'sha256': hash_bytes((root / name).read_bytes())})
        publish(directory, 'started.json', {'schema': 'si-native-market-input-start-v1', 'code_head': head,
            'remote_head': remote, 'protocol_sha256': EXPECTED_PROTOCOL_SHA256,
            'code_identity_sha256': hash_payload({'git_commit': head, 'files': files}), 'started_at': began,
            'maximum_requests': frozen['maximum_requests'], 'outcome_looks': 0, 'qc_attempts': 0})
        _guard(root, head, remote)
        secret = KeychainSecret(_read_key(CREDENTIAL_PATH))
        _guard(root, head, remote)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        return _capture(root, directory, opener, secret, head=head, remote=remote, started_at=began)
    except (CaptureRefusal, inputs.NativeMarketInputError, ShortInterestKeychainError, ValueError, TypeError, OSError, KeyError):
        publish(directory, 'refused.json', {'schema': 'si-native-market-input-refusal-v1', 'status': 'source_capture_refused',
            'refused_at': _utc_now(), 'outcome_looks': 0, 'qc_attempts': 0, 'backtest_result_exists': False})
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--expected-remote', required=True)
    args = parser.parse_args(argv)
    try:
        result = run(Path.cwd().resolve(), head=args.expected_head, remote=args.expected_remote)
    except (CaptureRefusal, inputs.NativeMarketInputError, ShortInterestKeychainError, ValueError, TypeError, OSError, KeyError):
        print(json.dumps({'status': 'market_source_capture_refused', 'outcome_looks': 0,
                          'qc_attempts': 0, 'backtest_result_exists': False}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
