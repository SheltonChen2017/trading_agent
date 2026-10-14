"""One post-upgrade storage reconciliation; no operation occurs on import.

The old failed upload is not renewed. Actual exit0 and a matching externally
pinned new receipt precede any separately frozen strategy continuation.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from types import SimpleNamespace
import sys
import time

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_arv2_newrule_comparison as frozen

helpers = frozen.helpers
SOURCE = ROOT / 'scripts/run_arv2_newrule_storage_recovery.py'
RECOVERY_SOURCE = ROOT / 'scripts/arv2_newrule_storage_recovery.py'
RECOVERY_SHA256 = 'c9952791bce1b802777c80b24a42a86be0d462a2b75a82b462200d58d6100682'
DIAGNOSTIC_PINS = {
    'scripts/diagnose_arv2_newrule_upload.py': 'b8477fe9246b7355c9b10bec91a9ad6e6305fcd0a7e2d4f00f61da1c35ce9901',
    'scripts/diagnose_arv2_newrule_object_metadata.py': '0a566b6b049f160daf6cc1a1bb2a507e18dd645c64d948dea50136cebbbede23',
}
FROZEN_CALLER_SHA256 = '533c1ebf520e9ebf836c78067b9b1480eccf49cfb01aaeb240e3a73b77087d05'
FAMILY_SHA256 = '8b8ee913dcfb5ad37f4748ea70db4fcbd6ff15580e52cd160bccf2b37e10a9e5'
SCHEMA = 'arv2-newrule-storage-recovery-operation-v1'
DEADLINE_SECONDS, MAX_OUTPUT_BYTES = 500, 24 * 1024


class RecoveryOperationRefusal(ValueError):
    pass


def _require(value):
    if not value:
        raise RecoveryOperationRefusal('operation_refused')


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': frozen.BRANCH,
        'python': str(frozen.PYTHON), 'family_sha256': FAMILY_SHA256,
        'frozen_caller_sha256': FROZEN_CALLER_SHA256,
        'recovery_sha256': RECOVERY_SHA256, 'diagnostic_pins': dict(DIAGNOSTIC_PINS),
        'source_pins': dict(frozen.SOURCE_PINS),
        'new_source_pins': dict(frozen.NEW_SOURCE_PINS),
        'deadline_seconds': DEADLINE_SECONDS, 'max_output_bytes': MAX_OUTPUT_BYTES,
        'purpose': 'post_owner_storage_upgrade_reconcile_then_publish_missing_exact_objects',
        'original_upload_accepted': False, 'strategy_launch': False,
        'point_in_time_proven': False, 'formal_forward_ready': False, 'paper_or_live_ready': False}


def profile_sha256():
    return hashlib.sha256(helpers.canonical_json_bytes(profile_record())).hexdigest()


def _preflight(args, deadline):
    _require(Path(__file__).absolute() == SOURCE)
    frozen._preflight(SimpleNamespace(operation='summarize', expected_head=args.expected_head,
        caller_sha256=FROZEN_CALLER_SHA256, candidate=None, attempt=None,
        family_sha256=FAMILY_SHA256, prior_failure_sha256=None, justification_sha256=None), deadline)
    helpers.require_sha256(args.caller_sha256, 'caller')
    _require(helpers._source_digest(SOURCE) == args.caller_sha256
        and RECOVERY_SHA256 != '0' * 64
        and helpers._source_digest(RECOVERY_SOURCE) == RECOVERY_SHA256)
    for relative, digest in DIAGNOSTIC_PINS.items():
        _require(helpers._source_digest(ROOT / relative) == digest)
    helpers._remaining(deadline)


def _load_plan():
    from research.analyst_revisions_v2_qc import newrule_comparison_submission as submission
    value = frozen.prepared_input.october.load_october_order_input_package(frozen.PACKAGE,
        expected_package_sha256=frozen.PACKAGE_SHA256, lineage_path=frozen.LINEAGE,
        expected_lineage_sha256=frozen.LINEAGE_SHA256)
    return submission.load_family(value, expected_family_sha256=FAMILY_SHA256,
        expected_new_source_pins=dict(frozen.NEW_SOURCE_PINS),
        expected_host_source_pins={name: frozen.SOURCE_PINS[name]
                                  for name in submission.HOST_SOURCE_NAMES})


def _failure(error):
    # Exact built-in types only; never stringify an opaque exception or payload.
    for kind, label in ((RecoveryOperationRefusal, 'operation_refused'),
            (helpers.Deadline, 'deadline'), (FileExistsError, 'claim_collision'),
            (FileNotFoundError, 'file_missing'), (PermissionError, 'permission_error'),
            (KeyboardInterrupt, 'cancelled'), (SystemExit, 'cancelled'),
            (OSError, 'os_error'), (ValueError, 'value_error'), (TypeError, 'type_error')):
        if type(error) is kind:
            return label
    return 'unknown_exception'


def _safe_result(value, recovery):
    _require(type(value) is dict and type(value.get('complete')) is bool)
    fields = {'complete', 'report_sha256', 'report_bytes', 'failure_code',
              'attempted_request_count', 'requests'}
    if value['complete']:
        fields |= {'receipt_sha256', 'receipt_bytes'}
    _require(set(value) == fields)
    for prefix in ('report', 'receipt') if value['complete'] else ('report',):
        helpers.require_sha256(value[prefix + '_sha256'], prefix)
        size = value[prefix + '_bytes']
        _require(type(size) is int and 0 < size <= 512 * 1024)
    failure = value['failure_code']
    _require(failure is None if value['complete'] else
             type(failure) is str and len(failure) <= 64 and failure in recovery.FINITE_FAILURE_CODES)
    count, trace = value['attempted_request_count'], value['requests']
    _require(type(count) is int and 0 <= count <= 13 and type(trace) is list and len(trace) <= 13)
    for ordinal, item in enumerate(trace):
        _require(type(item) is dict and set(item) == {'ordinal', 'endpoint', 'index',
            'request_sha256', 'attempted', 'http_status', 'response_schema_valid', 'api_success', 'error_category'})
        helpers.require_sha256(item['request_sha256'], 'request')
        _require(type(item['ordinal']) is int and item['ordinal'] == ordinal
            and type(item['endpoint']) is str and item['endpoint'] in
                {'object/list', 'object/properties', 'object/set'}
            and type(item['attempted']) is bool and type(item['response_schema_valid']) is bool
            and (item['api_success'] is None or type(item['api_success']) is bool)
            and (item['http_status'] is None or type(item['http_status']) is int
                 and 100 <= item['http_status'] <= 599)
            and type(item['error_category']) is str and item['error_category'] in
                {'unknown', 'permission', 'not_found', 'quota', 'subscription'})
        index = item['index']
        _require(index is None if item['endpoint'] == 'object/list' else
                 type(index) is int and 0 <= index < 6)
        if value['complete']:
            _require(item['attempted'] is item['response_schema_valid'] is item['api_success'] is True
                and type(item['http_status']) is int and 200 <= item['http_status'] < 300)
    _require(count == sum(item['attempted'] for item in trace))
    return value


def run(args):
    stage, consumed = 'preflight', 'not_claimed_by_this_invocation'
    started = helpers._utc_now()
    deadline = time.monotonic() + DEADLINE_SECONDS
    try:
        with helpers._alarm(deadline):
            _preflight(args, deadline)
            from scripts import arv2_newrule_storage_recovery as recovery
            stage, consumed = 'claim', 'consumed_or_ambiguous'
            recovery.claim(args.expected_head, args.caller_sha256)
            stage = 'input_authentication'
            plan = _load_plan()
            helpers._remaining(deadline)
            stage = 'storage_reconciliation'
            result = _safe_result(recovery.recover(plan, FAMILY_SHA256, args.expected_head,
                                      args.caller_sha256, deadline), recovery)
            helpers._remaining(deadline)
            payload = helpers.canonical_json_bytes({'schema': SCHEMA,
                'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256,
                'profile_sha256': profile_sha256(), 'started_at': started,
                'finished_at': helpers._utc_now(), 'operation_completed': result['complete'],
                'result': result, 'original_upload_accepted': False,
                'point_in_time_proven': False, 'formal_forward_ready': False,
                'paper_or_live_ready': False})
            _require(len(payload) <= MAX_OUTPUT_BYTES)
            print(payload.decode('ascii'))
            return 0 if result['complete'] else 2
    except BaseException as error:
        print(helpers.canonical_json_bytes({'schema': SCHEMA, 'operation_completed': False,
            'stage': stage, 'failure_code': _failure(error), 'attempt_consumption': consumed,
            'original_upload_accepted': False, 'point_in_time_proven': False,
            'formal_forward_ready': False, 'paper_or_live_ready': False}).decode('ascii'))
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--caller-sha256', required=True)
    return run(parser.parse_args(argv))


if __name__ == '__main__':
    raise SystemExit(main())
