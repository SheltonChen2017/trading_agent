"""Fresh four-file own-account paired processing; no import-time I/O.

Independent expected hashes bind two completed strict-reader receipts and their
collector-emitted NAV series. A new exclusive claim precedes any private file
observation. Supplied launch-look metadata is checked, not rediscovered. No raw
orders, licensed packets, credentials, API calls, Object export or new QC look
exists here. Full journal/source replay and canonical acceptance remain false.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import time

from . import extended_result_reader_successor as strict

reader, e, metrics, native = strict.reader, strict.e, strict.reader.metrics, strict.reader.native
ops = native.collector
LANE, PRIVATE_ROOT, PREFIX = reader.LANE, reader.PRIVATE_ROOT, reader.PREFIX
SOURCE_RELATIVE = PREFIX + 'extended_paired_results.py'
BUNDLE = PREFIX + 'extended_source_bundle_compressed.json'
BUNDLE_SHA256 = '223efa83c9ed7ed2bc17547f31583886e7705559635a38946bf55010902f0a92'
SOURCE_PATHS = (*strict.SOURCE_PATHS, SOURCE_RELATIVE, BUNDLE)
MAX_FILE, MAX_TOTAL, MAX_SECONDS = 16 * 1024 * 1024, 64 * 1024 * 1024, 120
PROJECTS = {'tpr_on': 37650453, 'tpr_off': 37650980}
ARMS = ('tpr_on', 'tpr_off')
LOOK_KEYS = frozenset(('schema at candidate_id attempt manifest_sha256 execution_manifest_sha256 config_sha256 '
    'source_hashes input_hashes consumed fixture old_looks baseline_observed_looks persistent_observed_looks_before '
    'observed_total_before look_census_sha256').split())
ARM_KEYS = frozenset(('candidate_id attempt project_id backtest_id read_operation_id qc_operation_id config_sha256 '
    'source_hashes input_hashes result_sha256 result_bytes nav_sha256 nav_bytes look_receipt_sha256 look '
    'collection_operations_manifest_sha256').split())
RECEIPT_KEYS = frozenset(('schema study_id read_operation_id candidate_id attempt project_id backtest_id qc_operation_id action '
    'status scope_spent plan_sha256 git_head source_hashes owner_instruction_sha256 predecessor_reader_sha256 '
    'strict_inventory_source_sha256 strict_read_policy read_inventory read_bytes read_attempts failed_read_body_bytes_unknown '
    'read_bytes_semantics body_budget_and_expected_size_enforced_before_read terminal_status compile_id diagnostic metrics '
    'private_output_hashes automatic_retry old_receipts_renewed new_looks quantconnect_attempts full_cloud_journal_exported '
    'independent_input_row_replay canonical_admission trading ended_utc').split())
METRIC_KEYS = frozenset(('schema study_id candidate_id project_id backtest_id attempt compile_id freeze_sha256 config_sha256 '
    'source_hashes input_hashes metrics_binding nav_census order_census nav_metrics execution_metrics summary '
    'evidence_index_receipt summary_aggregate_sha256 index_aggregate_sha256 meaningful_native_orders classification '
    'full_cloud_journal_exported independent_input_row_replay provider_authenticity_attested point_in_time_data '
    'independent_sleeve_pnl_observed strategy_accepted canonical_admission confirmatory_alpha new_looks quantconnect_attempts').split())
EXECUTION_KEYS = frozenset(('order_count status_counts invalid_order_count canceled_order_count missing_fee_or_currency_orders '
    'missing_fill_or_currency_orders reported_usd_fee_subtotal complete_reported_fees_usd reported_gross_turnover_subtotal_decimal '
    'complete_reported_gross_turnover_decimal known_underfilled_shares known_overfilled_shares independent_sleeve_pnl_observed').split())
SHARED_MODULES = frozenset(('cap_observer.py', 'cap_tilt.py', 'extended_construction.py', 'extended_core.py', 'extended_loader.py',
    'extended_runtime_successor.py', 'extended_compressed_store.py'))
NAV_KEYS = frozenset(('schema study_id candidate_id project_id backtest_id attempt calendar_sha256 envelope_sha256 '
    'normalized_series_sha256 observations first_session last_session observation_clock native_numeric_tokens_preserved '
    'provider_authenticity_attested private_journal_replay_verified new_looks quantconnect_attempts').split())
ORDER_KEYS = frozenset(('schema study_id candidate_id project_id backtest_id attempt calendar_sha256 collection_sha256 '
    'page_count order_count status_counts native_event_count unavailable_order_counts orders_missing_fill_observations '
    'orders_missing_fee_observations derived_rational_vwap_orders normalized_page_sha256 observation_page_sha256 orders_sha256 '
    'original_strategy_intent_verified private_journal_replay_verified provider_authenticity_attested new_looks quantconnect_attempts').split())
Refusal = e.EvidenceError


def _fail(): raise Refusal('bounded paired own-account results refused; no automatic retry')
def _sha(raw): return hashlib.sha256(raw).hexdigest()


def _count(value, maximum=2**63 - 1):
    if type(value) is int:
        if not 0 <= value <= maximum: _fail()
        return value
    if type(value) is not e.JsonNumber or value.fraction().denominator != 1 or not 0 <= value.fraction() <= maximum: _fail()
    return int(value.fraction())


def _hashes(value, *, source=False):
    if type(value) is not dict or not 1 <= len(value) <= 32: _fail()
    for name, identity in value.items():
        if source and (type(name) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,100}[.]py', name) is None): _fail()
        e._id(name); e._hash(identity)
    return value


def _configurations(raw):
    if type(raw) is not bytes or _sha(raw) != BUNDLE_SHA256: _fail()
    body = e.parse_json(raw)
    e._closed(body, {'schema', 'candidates', 'inputs', 'preparation_sha256', 'repository_sources'})
    if body['schema'] != 'tpr-ext26-source-bundle-v1' or type(body['candidates']) is not list or len(body['candidates']) != 2: _fail()
    rows = {}
    for row in body['candidates']:
        candidate = row['candidate_id']; arm = e.CANDIDATES.get(candidate)
        if arm is None or arm in rows: _fail()
        text = row['config_raw']; config = e.parse_json(text.encode())
        e._closed(config, {'schema', 'study_id', 'candidate_id', 'arm', 'freeze_sha256', 'input_hashes'})
        if (config['schema'] != 'tpr-ext26-config-v1' or config['study_id'] != e.STUDY_ID
                or config['candidate_id'] != candidate or config['arm'] != arm or config['freeze_sha256'] != e.FREEZE_SHA256
                or config['input_hashes'] != row['input_hashes']): _fail()
        rows[arm] = {'candidate_id': candidate, 'config_sha256': _sha(text.encode()), 'input_hashes': _hashes(config['input_hashes'])}
    if set(rows) != set(ARMS): _fail()
    shared = {key: value for key, value in rows['tpr_on']['input_hashes'].items() if key not in {'identities.json', 'signal-manifest.json'}}
    if (shared != rows['tpr_off']['input_hashes'] or set(shared) != {'calendar.json', 'preparation.json'}
            or shared['calendar.json'] != metrics.CALENDAR_SHA256): _fail()
    return rows


def _arms(value, configurations, expected_observed_looks):
    e._closed(value, set(ARMS)); total = _count(expected_observed_looks, 22)
    if total < 18: _fail()
    for arm in ARMS:
        row = value[arm]; e._closed(row, ARM_KEYS); frozen = configurations[arm]
        attempt = _count(row['attempt'], 3)
        if (attempt != 1 if arm == 'tpr_on' else attempt not in {2, 3}): _fail()
        if (row['candidate_id'] != frozen['candidate_id'] or _count(row['project_id']) != PROJECTS[arm]
                or row['config_sha256'] != frozen['config_sha256'] or row['input_hashes'] != frozen['input_hashes']
                or type(row['read_operation_id']) is not str or re.fullmatch(r'TPR-EXT26-RESULT-V2-[A-Za-z0-9-]{1,50}', row['read_operation_id']) is None
                or type(row['qc_operation_id']) is not str or re.fullmatch(r'TPR-EXT26-QC-2026101[01]-[0-9]{3}', row['qc_operation_id']) is None): _fail()
        e._id(row['backtest_id']); _hashes(row['source_hashes'], source=True)
        if not SHARED_MODULES <= set(row['source_hashes']): _fail()
        for key in ('result_sha256', 'nav_sha256', 'look_receipt_sha256', 'collection_operations_manifest_sha256'): e._hash(row[key])
        if any(not 0 < _count(row[key], MAX_FILE) <= MAX_FILE for key in ('result_bytes', 'nav_bytes')): _fail()
        look = row['look']; e._closed(look, LOOK_KEYS)
        if (look['schema'] != 'tpr-ext26-look-v2' or _sha(e.canonical(look)) != row['look_receipt_sha256']
                or look['candidate_id'] != row['candidate_id'] or _count(look['attempt'], 3) != attempt
                or any(look[key] != row[key] for key in ('config_sha256', 'source_hashes', 'input_hashes'))
                or look['consumed'] is not True or look['fixture'] is not False or _count(look['baseline_observed_looks']) != 16
                or _count(look['observed_total_before']) != 16 + _count(look['persistent_observed_looks_before'], 5)
                or _count(look['old_looks']) != _count(look['observed_total_before'])
                or total < _count(look['observed_total_before']) + 1): _fail()
        reader._clock(look['at'])
        for key in ('manifest_sha256', 'execution_manifest_sha256', 'look_census_sha256'): e._hash(look[key])
    if (value['tpr_on']['backtest_id'] == value['tpr_off']['backtest_id']
            or value['tpr_on']['read_operation_id'] == value['tpr_off']['read_operation_id']): _fail()
    for name in SHARED_MODULES:
        if value['tpr_on']['source_hashes'][name] != value['tpr_off']['source_hashes'][name]: _fail()
    return value


def _files(arms):
    result = {}
    for arm in ARMS:
        row = arms[arm]
        result[arm + '_result'] = {'name': row['read_operation_id'] + '.result.json', 'sha256': row['result_sha256'], 'bytes': row['result_bytes']}
        result[arm + '_nav'] = {'name': row['candidate_id'] + '.attempt.' + str(_count(row['attempt'])) + '.native.' + row['qc_operation_id']
            + '.chart.account-nav.normalized-nav.json', 'sha256': row['nav_sha256'], 'bytes': row['nav_bytes']}
    if len({row['name'] for row in result.values()}) != 4 or sum(_count(row['bytes']) for row in result.values()) > MAX_TOTAL: _fail()
    return result


def _rational(value):
    e._closed(value, {'numerator', 'denominator'})
    for key in value:
        if type(value[key]) is not str or len(value[key]) > 1000 or re.fullmatch(r'-?[0-9]+', value[key]) is None: _fail()
    from fractions import Fraction
    try: result = Fraction(int(value['numerator']), int(value['denominator']))
    except (ValueError, ZeroDivisionError): _fail()
    if result < 0 or str(result.numerator) != value['numerator'] or str(result.denominator) != value['denominator']: _fail()
    return result


def _execution(body):
    e._closed(body, EXECUTION_KEYS)
    e._closed(body['status_counts'], set(metrics.STATUSES))
    for key in ('order_count', 'invalid_order_count', 'canceled_order_count', 'missing_fee_or_currency_orders', 'missing_fill_or_currency_orders'):
        _count(body[key], 50000)
    if (sum(_count(value, 50000) for value in body['status_counts'].values()) != _count(body['order_count'])
            or body['independent_sleeve_pnl_observed'] is not False): _fail()
    for key in ('reported_usd_fee_subtotal', 'known_underfilled_shares', 'known_overfilled_shares'): _rational(body[key])
    if body['complete_reported_fees_usd'] is not None: _rational(body['complete_reported_fees_usd'])
    from decimal import Decimal
    for key in ('reported_gross_turnover_subtotal_decimal', 'complete_reported_gross_turnover_decimal'):
        value = body[key]
        if value is None and key == 'complete_reported_gross_turnover_decimal': continue
        if type(value) is not str or len(value) > 128 or re.fullmatch(r'[0-9]+(?:[.][0-9]+)?(?:[Ee][+-]?[0-9]+)?', value) is None: _fail()
        parsed = Decimal(value)
        if not parsed.is_finite() or parsed < 0 or abs(parsed.as_tuple().exponent) > 1000: _fail()
    if ((_count(body['missing_fee_or_currency_orders']) == 0) != (body['complete_reported_fees_usd'] is not None)
            or (_count(body['missing_fill_or_currency_orders']) == 0) != (body['complete_reported_gross_turnover_decimal'] is not None)): _fail()
    return body


def _arm_result(row, result_raw, nav_raw, calendar, source_hashes, now):
    result = e.parse_json(result_raw); e._closed(result, RECEIPT_KEYS)
    if (result['schema'] != 'tpr-ext26-result-reader-successor-receipt-v1' or result['study_id'] != e.STUDY_ID
            or result['status'] != 'COMPLETED' or result['scope_spent'] is not True or result['action'] != 'metrics'
            or any(result[key] != row[key] for key in ('read_operation_id', 'qc_operation_id', 'candidate_id', 'backtest_id'))
            or _count(result['attempt'], 3) != _count(row['attempt']) or _count(result['project_id']) != _count(row['project_id'])
            or result['terminal_status'] not in {'Completed', 'Completed.'}
            or result['body_budget_and_expected_size_enforced_before_read'] is not True
            or result['failed_read_body_bytes_unknown'] is not False
            or result['predecessor_reader_sha256'] != strict.READER_SHA256
            or result['strict_inventory_source_sha256'] != strict.INVENTORY_SUCCESSOR_SHA256
            or result['strict_read_policy'] != 'opened-descriptor-exact-expected-size-and-remaining-before-body-v1'
            or result['source_hashes'] != {name: source_hashes[name] for name in strict.SOURCE_PATHS}): _fail()
    for key in ('automatic_retry', 'old_receipts_renewed', 'full_cloud_journal_exported', 'independent_input_row_replay', 'canonical_admission', 'trading'):
        if result[key] is not False: _fail()
    for key in ('new_looks', 'quantconnect_attempts'):
        if _count(result[key]) != 0: _fail()
    e._hash(result['plan_sha256']); e._hash(result['git_head'], 40); e._hash(result['owner_instruction_sha256'])
    ended = reader._clock(result['ended_utc']); reader._clock(row['look']['at'])
    if not reader._clock(row['look']['at']) <= ended <= now: _fail()
    inventory = result['read_inventory']
    if type(inventory) is not dict or not 17 <= len(inventory) <= 522: _fail()
    for descriptor in inventory.values():
        e._closed(descriptor, {'sha256', 'bytes'}); e._hash(descriptor['sha256'])
        if not 0 < _count(descriptor['bytes'], reader.MAX_FILE): _fail()
    if (_count(result['read_attempts']) != len(inventory) or _count(result['read_bytes']) != sum(_count(value['bytes']) for value in inventory.values())
            or inventory.get('nav_series') != {'sha256': row['nav_sha256'], 'bytes': row['nav_bytes']}
            or inventory.get('execution_manifest', {}).get('sha256') != row['look']['execution_manifest_sha256']
            or inventory.get('operations_manifest', {}).get('sha256') != row['collection_operations_manifest_sha256']): _fail()
    body = result['metrics']; e._closed(body, METRIC_KEYS)
    if (body['schema'] != 'tpr-ext26-own-job-metrics-v1' or body['study_id'] != e.STUDY_ID or body['freeze_sha256'] != e.FREEZE_SHA256
            or any(body[key] != row[key] for key in ('candidate_id', 'backtest_id', 'config_sha256', 'source_hashes', 'input_hashes'))
            or _count(body['attempt']) != _count(row['attempt']) or _count(body['project_id']) != _count(row['project_id'])
            or body['compile_id'] != result['compile_id']): _fail()
    for key in ('full_cloud_journal_exported', 'independent_input_row_replay', 'provider_authenticity_attested', 'point_in_time_data',
            'independent_sleeve_pnl_observed', 'strategy_accepted', 'canonical_admission', 'confirmatory_alpha'):
        if body[key] is not False: _fail()
    for key in ('new_looks', 'quantconnect_attempts'):
        if _count(body[key]) != 0: _fail()
    binding = metrics._binding(body['metrics_binding'], row['candidate_id'], nav_raw)
    if (any(binding[key] != body[key] for key in ('candidate_id', 'project_id', 'compile_id', 'backtest_id', 'freeze_sha256', 'config_sha256', 'source_hashes', 'input_hashes'))
            or binding['summary_aggregate_sha256'] != body['summary_aggregate_sha256']
            or binding['index_aggregate_sha256'] != body['index_aggregate_sha256']): _fail()
    if e.canonical(body['nav_metrics']) != e.canonical(metrics.nav_metrics(nav_raw, calendar, expected_series_sha256=row['nav_sha256'])): _fail()
    manifest = {key: body[key] for key in ('candidate_id', 'project_id', 'config_sha256', 'input_hashes')}
    manifest['arm'] = e.CANDIDATES[row['candidate_id']]
    for field, marker, hash_field in (('summary', 'EXT26_SUMMARY', 'summary_aggregate_sha256'), ('evidence_index_receipt', 'EXT26_EVIDENCE_INDEX', 'index_aggregate_sha256')):
        raw = e.canonical(body[field])
        if _sha(raw) != body[hash_field]: _fail()
        ops.compact_aggregate(marker + ' ' + raw.decode(), marker, manifest, _count(row['attempt']), row['backtest_id'])
    nav_census = body['nav_census']; e._closed(nav_census, NAV_KEYS)
    if (nav_census['schema'] != 'tpr-ext26-normalized-native-nav-v1' or nav_census['study_id'] != e.STUDY_ID
            or any(nav_census[key] != row[key] for key in ('candidate_id', 'project_id', 'backtest_id', 'attempt'))
            or nav_census['calendar_sha256'] != metrics.CALENDAR_SHA256 or _count(nav_census['observations']) != 1449
            or nav_census['normalized_series_sha256'] != row['nav_sha256']
            or nav_census['envelope_sha256'] != inventory['nav_envelope']['sha256']
            or nav_census['first_session'] != '2021-01-04' or nav_census['last_session'] != '2026-10-09'
            or nav_census['observation_clock'] != '16:01:00 America/New_York'
            or nav_census['native_numeric_tokens_preserved'] is not True): _fail()
    summary, order = body['summary'], body['order_census']; e._closed(order, ORDER_KEYS)
    if (_count(summary['valuation_days']) != 1449 or summary['last_valuation_session'] != '2026-10-09'
            or any(order.get(key) != row[key] for key in ('candidate_id', 'project_id', 'backtest_id', 'attempt'))
            or order.get('schema') != 'tpr-ext26-normalized-native-orders-v1'
            or order.get('study_id') != e.STUDY_ID or order.get('calendar_sha256') != metrics.CALENDAR_SHA256
            or order['collection_sha256'] != inventory['orders_collection']['sha256']
            or order['collection_sha256'] != binding['order_collection_sha256']): _fail()
    for census in (nav_census, order):
        for key in ('private_journal_replay_verified', 'provider_authenticity_attested'):
            if census[key] is not False: _fail()
        for key in ('new_looks', 'quantconnect_attempts'):
            if _count(census[key]) != 0: _fail()
    if order['original_strategy_intent_verified'] is not False: _fail()
    pages = _count(order['page_count'], 506)
    if pages != max(1, (_count(order['order_count'], 50000) + 98) // 99): _fail()
    outputs = {}
    for role, prefix in (('normalized_page_sha256', 'normalized-orders.'), ('observation_page_sha256', 'order-observations.')):
        if type(order[role]) is not list or len(order[role]) != pages: _fail()
        for index, identity in enumerate(order[role]): outputs[prefix + str(index)] = e._hash(identity)
    if (result['private_output_hashes'] != outputs
            or order['orders_sha256'] != _sha(e.canonical({'schema': 'tpr-ext26-normalized-order-pages-v1', 'page_sha256': order['normalized_page_sha256']}))): _fail()
    for key in ('native_event_count', 'orders_missing_fill_observations', 'orders_missing_fee_observations', 'derived_rational_vwap_orders'):
        _count(order[key], 500000)
    execution = _execution(body['execution_metrics']); count = _count(order['order_count'], 50000)
    if (count != _count(execution['order_count']) or type(body['meaningful_native_orders']) is not bool
            or body['meaningful_native_orders'] != (count > 0)
            or body['classification'] not in {'diagnostic_zero_native_orders', 'diagnostic_native_fill_observations_incomplete', 'native_metrics_require_accounting_audit'}): _fail()
    return body


def evaluate(data, arms, calendar, source_hashes, *, now):
    e._closed(data, {'tpr_on_result', 'tpr_on_nav', 'tpr_off_result', 'tpr_off_nav'})
    parsed = {arm: _arm_result(arms[arm], data[arm + '_result'], data[arm + '_nav'], calendar, source_hashes, now) for arm in ARMS}
    paired = metrics.paired_metrics(data['tpr_on_nav'], data['tpr_off_nav'], calendar,
        on_binding=parsed['tpr_on']['metrics_binding'], off_binding=parsed['tpr_off']['metrics_binding'])
    chains = ops.compare_matched_chain_receipts(parsed['tpr_on']['summary']['matched_input_chains'], parsed['tpr_off']['summary']['matched_input_chains'])
    diagnostics, evidence = [], {}
    for arm in ARMS:
        body = parsed[arm]; execution, summary, order = body['execution_metrics'], body['summary'], body['order_census']
        if not body['meaningful_native_orders']: diagnostics.append(arm + ':zero_orders')
        if _count(order['orders_missing_fill_observations']) or not _count(order['native_event_count']): diagnostics.append(arm + ':incomplete_native_fills')
        if execution['complete_reported_fees_usd'] is None: diagnostics.append(arm + ':native_fees_unavailable')
        if execution['complete_reported_gross_turnover_decimal'] is None: diagnostics.append(arm + ':native_turnover_unavailable')
        if not summary['coverage_complete']: diagnostics.append(arm + ':incomplete_input_coverage')
        if not summary['internally_meaningful_execution']: diagnostics.append(arm + ':runtime_not_meaningful')
        if _count(summary['position_ledger_mismatches']) or ops._rational(summary['max_cash_ledger_residual']) or ops._rational(summary['max_nav_ledger_residual']): diagnostics.append(arm + ':observed_accounting_residual')
        evidence[arm] = {'candidate_id': body['candidate_id'], 'attempt': body['attempt'], 'project_id': body['project_id'], 'backtest_id': body['backtest_id'],
            'compile_id': body['compile_id'], 'config_sha256': body['config_sha256'], 'input_hashes': body['input_hashes'], 'source_hashes': body['source_hashes'],
            'metrics_binding': body['metrics_binding'], 'classification': body['classification'], 'execution_metrics': execution,
            'coverage': {key: summary[key] for key in ('coverage_complete', 'internally_meaningful_execution', 'decisions', 'refused_decisions',
                'valuation_days', 'last_valuation_session', 'submitted_orders', 'fill_events', 'per_sleeve_coverage', 'cap_snapshot_coverage', 'cash_exposure_aggregate')},
            'accounting': {key: summary[key] for key in ('fees', 'max_cash_ledger_residual', 'max_nav_ledger_residual', 'position_ledger_mismatches', 'risk_breaches', 'name_soft_cap_breaches')},
            'summary_aggregate_sha256': body['summary_aggregate_sha256'], 'index_aggregate_sha256': body['index_aggregate_sha256']}
    if not chains['matched_chain_receipts_equal']: diagnostics.append('matched_input_chain_receipts_differ')
    if not chains['all_domain_decisions_observed']: diagnostics.append('matched_input_chain_coverage_incomplete')
    return {'paired_metrics': paired, 'matched_input_chain_comparison': chains, 'arm_evidence': evidence, 'diagnostics': diagnostics,
        'classification': 'paired_account_metrics_require_independent_review' if not diagnostics else 'diagnostic_paired_native_evidence',
        'frozen_configurations_and_shared_source_hashes_verified': True, 'shared_native_module_hashes_equal': True,
        'strategy_economics_independently_replayed': False, 'independent_sleeve_pnl_observed': False,
        'full_cloud_journal_exported': False, 'independent_input_row_replay': False, 'point_in_time_verified': False,
        'confirmatory_alpha': False, 'strategy_accepted': False, 'canonical_admission': False, 'quantconnect_ready': False}


def _plan(*, source_hashes, git_head, owner_instruction_sha256, created_utc, expires_utc, processing_operation_id,
          arms, expected_observed_looks, mode='production'):
    if (type(processing_operation_id) is not str or re.fullmatch(r'TPR-EXT26-PAIRED-[A-Za-z0-9-]{1,60}', processing_operation_id) is None
            or mode not in {'production', 'offline-fixture'} or type(source_hashes) is not dict or set(source_hashes) != set(SOURCE_PATHS)): _fail()
    for value in source_hashes.values(): e._hash(value)
    e._hash(git_head, 40); e._hash(owner_instruction_sha256)
    created, expires = reader._clock(created_utc), reader._clock(expires_utc)
    if not 0 < (expires - created).total_seconds() <= 86400: _fail()
    _files(arms)
    return {'schema': 'tpr-ext26-paired-results-plan-v1', 'study_id': e.STUDY_ID, 'processing_operation_id': processing_operation_id,
        'source_hashes': source_hashes, 'git_head': git_head, 'owner_instruction_sha256': owner_instruction_sha256,
        'created_utc': created.isoformat(), 'expires_utc': expires.isoformat(), 'arms': arms,
        'expected_observed_looks': _count(expected_observed_looks, 22), 'mode': mode, 'files': _files(arms),
        'max_file_bytes': MAX_FILE, 'max_total_bytes': MAX_TOTAL, 'max_seconds': MAX_SECONDS,
        'licensed_input_reads': 0, 'order_row_reads': 0, 'network': False, 'credentials': False, 'object_export': False,
        'new_looks': 0, 'quantconnect_attempts': 0, 'old_receipts_renewed': False, 'canonical_admission': False, 'trading': False}


def _execute(plan, sources, path, *, clock, guard):
    keys = ('source_hashes', 'git_head', 'owner_instruction_sha256', 'created_utc', 'expires_utc', 'processing_operation_id', 'arms', 'expected_observed_looks', 'mode')
    if e.canonical(plan) != e.canonical(_plan(**{key: plan[key] for key in keys})): _fail()
    if (plan['mode'] == 'production' and path != PRIVATE_ROOT
            or plan['mode'] == 'offline-fixture' and (path == PRIVATE_ROOT or path.is_relative_to(LANE))): _fail()
    start, directory, total, inflight = time.monotonic(), None, 0, False
    def check():
        guard(plan['git_head']); current = clock()
        if (type(current) is not datetime or current.utcoffset() != timedelta(0)
                or not reader._clock(plan['created_utc']) <= current < reader._clock(plan['expires_utc'])
                or time.monotonic() - start >= MAX_SECONDS or {name: _sha(raw) for name, raw in sources.items()} != plan['source_hashes']): _fail()
    check(); _arms(plan['arms'], _configurations(sources[BUNDLE]), plan['expected_observed_looks'])
    try:
        directory = reader._open_directory(path); info = os.fstat(directory)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700: _fail()
        check(); operation = plan['processing_operation_id']; reader._publish(directory, operation + '.claim.spent.json', e.canonical(plan))
        report = {'schema': 'tpr-ext26-paired-results-receipt-v1', 'study_id': e.STUDY_ID, 'processing_operation_id': operation,
            'status': 'FAILED_OR_UNCERTAIN', 'scope_spent': True, 'plan_sha256': _sha(e.canonical(plan)), 'git_head': plan['git_head'],
            'source_hashes': plan['source_hashes'], 'owner_instruction_sha256': plan['owner_instruction_sha256'],
            'read_inventory': {}, 'read_bytes': 0, 'failed_read_body_bytes_unknown': False, 'result': None,
            'expected_observed_looks': plan['expected_observed_looks'], 'look_metadata_basis': 'independently supplied launch receipts; no event discovery',
            'launch_look_receipt_hashes': {arm: plan['arms'][arm]['look_receipt_sha256'] for arm in ARMS},
            'launch_operations_manifest_sha256': {arm: plan['arms'][arm]['look']['manifest_sha256'] for arm in ARMS},
            'collection_operations_manifest_sha256': {arm: plan['arms'][arm]['collection_operations_manifest_sha256'] for arm in ARMS},
            'licensed_input_reads': 0, 'order_row_reads': 0, 'network': False, 'credentials': False, 'object_export': False,
            'new_looks': 0, 'quantconnect_attempts': 0, 'automatic_retry': False, 'old_receipts_renewed': False,
            'canonical_admission': False, 'trading': False}
        try:
            data = {}
            for role, descriptor in plan['files'].items():
                check(); inflight = True
                expected = {key: descriptor[key] for key in ('sha256', 'bytes')}
                # The strict predecessor uses the opened inode's exact expected
                # size, remaining budget and no-follow custody BEFORE body I/O.
                raw = strict._read_bound(directory, descriptor['name'], expected, MAX_TOTAL - total)
                total += len(raw); inflight = False; data[role] = raw
                report['read_inventory'][role] = {'sha256': _sha(raw), 'bytes': len(raw)}
            check(); report['result'] = evaluate(data, plan['arms'], sources[PREFIX + 'extended_calendar.json'], plan['source_hashes'], now=clock())
            check(); report['status'] = 'COMPLETED'
        except (Exception, KeyboardInterrupt):
            report['result'] = None; report['failed_read_body_bytes_unknown'] = inflight
        report.update(read_bytes=total, ended_utc=clock().isoformat()); guard(plan['git_head'])
        raw = e.canonical(report); reader._publish(directory, operation + '.result.json', raw); return raw
    finally:
        if directory is not None: os.close(directory)


def _verify_imports():
    if Path(__file__) != LANE / SOURCE_RELATIVE or Path(strict.__file__) != LANE / strict.SOURCE_RELATIVE: _fail()
    strict._verify_imports()


def _sources(head):
    result = strict._sources(head)
    for name in (SOURCE_RELATIVE, BUNDLE):
        reader._guard(head); directory = reader._open_directory((LANE / name).parent)
        try: raw = reader._read(directory, Path(name).name, private=False)
        finally: os.close(directory)
        recorded = subprocess.run(['git', 'show', head + ':' + name], cwd=LANE, capture_output=True, timeout=5, check=True).stdout
        if raw != recorded: _fail()
        result[name] = raw
    _configurations(result[BUNDLE]); reader._guard(head); return result


def run(**arguments):
    _verify_imports(); head = reader._guard(); sources = _sources(head)
    plan = _plan(source_hashes={name: _sha(raw) for name, raw in sources.items()}, git_head=head, mode='production', **arguments)
    with reader._deadline():
        raw = _execute(plan, sources, PRIVATE_ROOT, clock=reader._now, guard=reader._guard)
        if _sources(head) != sources: _fail()
        return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('processing-operation-id', 'owner-instruction-sha256', 'created-utc', 'expires-utc', 'arms-json', 'arms-sha256', 'expected-observed-looks'):
        parser.add_argument('--' + name, required=True)
    arguments = vars(parser.parse_args(argv))
    try:
        raw = arguments.pop('arms_json').encode(); expected = arguments.pop('arms_sha256')
        if _sha(raw) != e._hash(expected): _fail()
        arguments['arms'] = e.parse_json(raw); arguments['expected_observed_looks'] = _count(e.JsonNumber(arguments['expected_observed_looks']), 22)
        result = run(**arguments); print(result.decode(), end='')
        return 0 if e.parse_json(result)['status'] == 'COMPLETED' else 1
    except (Exception, KeyboardInterrupt):
        print(e.canonical({'status': 'REFUSED_OR_UNCERTAIN', 'scope_spent': None, 'automatic_retry': False}).decode(), end=''); return 1


if __name__ == '__main__': raise SystemExit(main())
