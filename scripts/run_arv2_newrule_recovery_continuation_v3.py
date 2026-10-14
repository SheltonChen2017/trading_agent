"""Fixed six-cell lifecycle after externally admitted storage recovery.

Receipt and source arguments are bindings, not review or run authority. Each
actual action still requires its committed prospective run decision and the
externally observed successful recovery exit. No exit is inferred from a
receipt. This caller executes A1 only; later attempts need a new decision.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
from types import SimpleNamespace
import sys
import time

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_arv2_newrule_comparison as frozen

helpers = frozen.helpers
SOURCE = ROOT / 'scripts/run_arv2_newrule_recovery_continuation_v3.py'
FROZEN_CALLER_SHA256 = '533c1ebf520e9ebf836c78067b9b1480eccf49cfb01aaeb240e3a73b77087d05'
FAMILY_SHA256 = '8b8ee913dcfb5ad37f4748ea70db4fcbd6ff15580e52cd160bccf2b37e10a9e5'
NEW_PINS = {
    'scripts/arv2_newrule_storage_recovery_v3.py': '7f817962d49ac4d692351131e1a1af004efa2db7ee720eb0aaf29533757f8c4c',
    'scripts/arv2_newrule_storage_recovery_v2.py': '02d40ea52084111cf6a04c6ffad629df0bb9008890133e16ef5b2a8f7b4406e9',
    'scripts/arv2_newrule_storage_recovery.py': 'c9952791bce1b802777c80b24a42a86be0d462a2b75a82b462200d58d6100682',
    'scripts/run_arv2_newrule_storage_recovery.py': '7b8aec7979c4df5f0818e06f86fe91f9ea8f6cefd4db085941ff8c04af7381b6',
    'scripts/arv2_newrule_recovery_continuation_v3.py': '331a3ef113489f98dbe11d21c448798840c461af0fda6e99f4e6aef32d64a2aa',
    'scripts/diagnose_arv2_newrule_upload.py': 'b8477fe9246b7355c9b10bec91a9ad6e6305fcd0a7e2d4f00f61da1c35ce9901',
    'scripts/diagnose_arv2_newrule_object_metadata.py': '0a566b6b049f160daf6cc1a1bb2a507e18dd645c64d948dea50136cebbbede23',
    'scripts/diagnose_arv2_newrule_properties_matrix.py': '47b8eec8296beb0433a1223adea38c471ba2034b26ac81cb20a2e4143431f363',
    'scripts/diagnose_arv2_newrule_storage_error.py': '090c0ad92811820cb87d37df7c13f8b63033d14b5d23f20cac770c729760a252',
}
OPERATIONS = ('capacity', 'begin', 'compile', 'launch', 'status', 'read', 'summarize')
SCHEMA = 'arv2-newrule-recovery-continuation-operation-v3'
MAX_OUTPUT_BYTES = 24 * 1024


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': frozen.BRANCH,
        'python': str(frozen.PYTHON), 'family_sha256': FAMILY_SHA256,
        'frozen_caller_sha256': FROZEN_CALLER_SHA256, 'new_pins': dict(NEW_PINS),
        'source_pins': dict(frozen.SOURCE_PINS), 'operations': list(OPERATIONS),
        'deadlines': {key: frozen.DEADLINES[key] for key in OPERATIONS},
        'max_output_bytes': MAX_OUTPUT_BYTES, 'actual_recovery_exit_zero_required_externally': True,
        'executable_attempts': [1], 'original_candidate_attempt_ceiling': 3,
        'mandatory_preflight_before_private_input': True, 'pytest_operational_context': False,
        'own_clean_head_blob_binding': True,
        'original_upload_accepted': False, 'point_in_time_proven': False,
        'formal_forward_ready': False, 'paper_or_live_ready': False}


def profile_sha256():
    return hashlib.sha256(helpers.canonical_json_bytes(profile_record())).hexdigest()


def _under_test():
    return ('PYTEST_CURRENT_TEST' in os.environ or 'pytest' in sys.modules
        or any(name == '_pytest' or name.startswith('_pytest.') for name in tuple(sys.modules)))


def _git(arguments, deadline, limit=65536):
    value = frozen.subprocess.run(['git', *arguments], cwd=ROOT, stdin=frozen.subprocess.DEVNULL,
        capture_output=True, timeout=min(3, helpers._remaining(deadline)), check=False)
    frozen.require(type(value.returncode) is int and value.returncode == 0 and value.stderr == b''
        and type(value.stdout) is bytes and len(value.stdout) <= limit)
    return value.stdout


def _preflight(args, deadline):
    frozen.require(not _under_test() and Path(__file__).absolute() == SOURCE
        and type(args.operation) is str and args.operation in OPERATIONS)
    frozen.require(args.prior_failure_sha256 is None and args.justification_sha256 is None)
    if args.operation not in ('capacity', 'summarize'):
        frozen.require(type(args.attempt) is int and args.attempt == 1)
    bindings = SimpleNamespace(**vars(args))
    bindings.caller_sha256, bindings.family_sha256 = FROZEN_CALLER_SHA256, FAMILY_SHA256
    frozen._preflight(bindings, deadline)
    helpers.require_sha256(args.caller_sha256, 'caller')
    helpers.require_sha256(args.receipt_sha256, 'recovery receipt')
    frozen.require(helpers._source_digest(SOURCE) == args.caller_sha256)
    for relative, digest in NEW_PINS.items():
        helpers.require_sha256(digest, 'new source pin')
        frozen.require(digest != '0' * 64 and helpers._source_digest(ROOT / relative) == digest)
    selected = args.expected_head + ':' + SOURCE.relative_to(ROOT).as_posix()
    count = _git(['cat-file', '-s', selected], deadline).decode('ascii').strip()
    frozen.require(re.fullmatch(r'[1-9][0-9]{0,6}', count) is not None and int(count) <= 2*1024*1024)
    raw = _git(['cat-file', 'blob', selected], deadline, int(count))
    frozen.require(len(raw) == int(count) and hashlib.sha256(raw).hexdigest() == args.caller_sha256
        and _git(['rev-parse', 'HEAD'], deadline).decode('ascii').strip() == args.expected_head
        and _git(['status', '--porcelain'], deadline) == b'')
    helpers._remaining(deadline)


def _operation(args, deadline):
    # This check is mandatory even when this internal function is called
    # directly; no private input load relies solely on its outer caller.
    _preflight(args, deadline)
    from scripts import arv2_newrule_recovery_continuation_v3 as continuation
    from research.analyst_revisions_v2_qc import newrule_comparison_submission as submission
    value = frozen.prepared_input.october.load_october_order_input_package(frozen.PACKAGE,
        expected_package_sha256=frozen.PACKAGE_SHA256, lineage_path=frozen.LINEAGE,
        expected_lineage_sha256=frozen.LINEAGE_SHA256)
    plan = submission.load_family(value, expected_family_sha256=FAMILY_SHA256,
        expected_new_source_pins=dict(frozen.NEW_SOURCE_PINS),
        expected_host_source_pins={name: frozen.SOURCE_PINS[name] for name in submission.HOST_SOURCE_NAMES})
    helpers._remaining(deadline)
    result = continuation.dispatch(args.operation, plan, args.candidate, args.attempt,
        expected_family_sha256=FAMILY_SHA256, expected_receipt_sha256=args.receipt_sha256,
        prior_failure_sha256=args.prior_failure_sha256,
        retry_justification_sha256=args.justification_sha256)
    if args.operation == 'read':
        meta = result['statistics']['meta']
        return {**{key: result[key] for key in ('family_sha256', 'candidate_id', 'attempt_id',
            'project_id', 'backtest_id', 'status', 'cell_completed', 'family_comparable', 'result_cell')},
            'statistics_sha256': hashlib.sha256(helpers.canonical_json_bytes(result['statistics'])).hexdigest(),
            'account_aggregates': meta['account_aggregates'],
            'common_source_path_sha256': meta['common_source_path_sha256'],
            'decision_count': meta['decision_count'], 'evaluation_session_count': meta['evaluation_session_count'],
            'order_count': meta['order_count'], 'fill_count': meta['fill_count'],
            'coverage_fallback_counts': meta['coverage_fallback_counts']}
    return result


def _failure(error, submission, recovery):
    if recovery is not None and type(error) is recovery.StorageRecoveryError:
        return recovery.finite_failure(error)
    return frozen._failure(error, submission)


def run(args):
    started, stage, submission = helpers._utc_now(), 'preflight', None
    recovery = None
    deadline = time.monotonic() + frozen.DEADLINES.get(args.operation, 1)
    try:
        with helpers._alarm(deadline):
            _preflight(args, deadline)
            from research.analyst_revisions_v2_qc import newrule_comparison_submission as submission
            from scripts import arv2_newrule_storage_recovery_v3 as recovery
            stage = args.operation
            result = _operation(args, deadline)
            helpers._remaining(deadline)
            payload = helpers.canonical_json_bytes({'schema': SCHEMA, 'operation': args.operation,
                'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256,
                'receipt_sha256': args.receipt_sha256, 'profile_sha256': profile_sha256(),
                'started_at': started, 'finished_at': helpers._utc_now(),
                'operation_completed': True, 'result': result, 'original_upload_accepted': False,
                'formal_forward_ready': False, 'point_in_time_proven': False, 'paper_or_live_ready': False})
            frozen.require(len(payload) <= MAX_OUTPUT_BYTES)
            print(payload.decode('ascii'))
            return 0
    except BaseException as error:
        print(helpers.canonical_json_bytes({'schema': SCHEMA,
            'operation': args.operation if args.operation in OPERATIONS else 'unknown',
            'operation_completed': False, 'stage': stage,
            'failure_code': _failure(error, submission, recovery),
            'attempt_consumption': 'consult_exact_claim_no_automatic_retry',
            'original_upload_accepted': False, 'formal_forward_ready': False,
            'point_in_time_proven': False, 'paper_or_live_ready': False}).decode('ascii'))
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=OPERATIONS)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--caller-sha256', required=True)
    parser.add_argument('--receipt-sha256', required=True)
    parser.add_argument('--candidate', choices=frozen.CANDIDATES)
    parser.add_argument('--attempt', type=int)
    parser.add_argument('--prior-failure-sha256')
    parser.add_argument('--justification-sha256')
    return run(parser.parse_args(argv))


if __name__ == '__main__':
    raise SystemExit(main())
