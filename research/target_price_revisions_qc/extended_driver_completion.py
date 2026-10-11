"""Explicit current-HEAD completion access for the same owned frozen candidates.

No automatic retries, project creation, adoption, cleanup or input-read renewal.
Prepare compares the supplied committed successor against a pure exact render of
the immutable public predecessor; no private compression metadata is reopened.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import subprocess

from . import extended_driver_compressed as predecessor
from . import extended_operations_completion as operations
from . import extended_completion_successor as completion

base, e = predecessor.base, predecessor.e
preflight, committed = predecessor.preflight, predecessor.committed
SPENT_OPERATIONS = frozenset(('TPR-EXT26-QC-20261010-001', 'TPR-EXT26-QC-20261010-002',
    'TPR-EXT26-QC-20261010-003', 'TPR-EXT26-QC-20261011-004', 'TPR-EXT26-QC-20261011-005'))


def prepare(operation_id, bundle_path):
    base._name(operation_id)
    if operation_id in SPENT_OPERATIONS:
        raise base.Refusal('spent operation cannot be renewed')
    state = preflight(); operations.predecessor.previous.verify_initializers(state['head'])
    raw = committed(bundle_path, state['head']); bundle = e.parse_json(raw)
    e._closed(bundle, {'schema', 'candidates', 'inputs', 'preparation_sha256', 'repository_sources'})
    names = bundle['repository_sources']
    if (bundle['schema'] != 'tpr-ext26-source-bundle-v1' or type(names) is not list or not 6 <= len(names) <= 31
            or any(type(name) is not str for name in names) or len(set(names)) != len(names)
            or not operations.REQUIRED <= set(names)):
        raise base.Refusal('committed complete completion producer closure required')
    values = {name: committed(name, state['head']) for name in names}
    helper = values[completion.PREFIX + completion.HELPER]
    expected = completion.render_completion_bundle(values[completion.PREDECESSOR_BUNDLE],
        helper_raw=helper, expected_helper_sha256=e.digest(helper))
    if e.canonical(expected) != raw:
        raise base.Refusal('only exact completion import/call and OFF3 source literal changes allowed')
    sources = {name: e.digest(value) for name, value in values.items()}; sources[bundle_path] = e.digest(raw)
    clock = datetime.now(timezone.utc)
    manifest = {'schema': 'tpr-ext26-operations-manifest-v1', 'study_id': e.STUDY_ID, 'operation_id': operation_id,
        'created_utc': clock.isoformat(), 'expires_utc': (clock + timedelta(hours=48)).isoformat(), 'git_head': state['head'],
        'freeze_sha256': e.FREEZE_SHA256, 'preparation_sha256': bundle['preparation_sha256'], 'repository_source_hashes': sources,
        'candidates': bundle['candidates'], 'inputs': bundle['inputs'], 'max_requests': base.MAX_REQUESTS,
        'max_response_bytes': e.MAX_BYTES, 'request_seconds': 30, 'max_orders': base.MAX_ORDERS, 'max_collections': base.MAX_COLLECTIONS}
    return operations.Operations(manifest, manifest_sha256=e.digest(e.canonical(manifest))).prepare()


def controller_for(operation_id):
    base._name(operation_id); preflight()
    raw = base.read_private(base.PRIVATE_ROOT, 'manifest.' + operation_id + '.json')
    controller = operations.Operations(e.parse_json(raw), manifest_sha256=e.digest(raw)); controller.access(); return controller


def _main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'authenticate', 'inputs', 'sources', 'reserve', 'compile',
        'compile-status', 'launch', 'status', 'orders', 'collect-native'))
    parser.add_argument('--operation', required=True); parser.add_argument('--bundle')
    parser.add_argument('--candidate', choices=tuple(e.CANDIDATES)); parser.add_argument('--attempt', type=int)
    args = parser.parse_args(argv); preflight()
    if args.action == 'prepare':
        if args.bundle is None or args.candidate is not None or args.attempt is not None:
            parser.error('prepare requires only exact committed bundle')
        result = prepare(args.operation, args.bundle)
    else:
        if args.bundle is not None:
            parser.error('bundle is prepare-only')
        controller = controller_for(args.operation)
        if args.action == 'authenticate':
            if args.candidate is not None or args.attempt is not None:
                parser.error('authenticate needs no candidate/attempt')
            result = {'authenticated': controller.request('authenticate', {}).get('success') is True}
        else:
            attempted = {'compile', 'compile-status', 'launch', 'status', 'orders', 'collect-native'}
            if args.candidate is None or args.action in attempted and args.attempt is None:
                parser.error('exact candidate/attempt required')
            if args.action not in attempted and args.attempt is not None:
                parser.error('attempt is attempt-action only')
            methods = {'inputs': controller.upload_inputs, 'sources': controller.upload_sources, 'reserve': controller.reserve,
                'compile': controller.compile, 'compile-status': controller.compile_status, 'launch': controller.launch,
                'status': controller.status, 'orders': controller.collect_orders, 'collect-native': controller.collect_native}
            result = methods[args.action](args.candidate, args.attempt) if args.action in attempted else methods[args.action](args.candidate)
    print(e.canonical(result).decode(), end=''); return 0


def main(argv=None):
    try:
        return _main(argv)
    except (base.Refusal, OSError, ValueError, TypeError, KeyError, subprocess.CalledProcessError):
        print(e.canonical({'status': 'refused_or_uncertain', 'automatic_retry': False}).decode(), end=''); return 1


if __name__ == '__main__': raise SystemExit(main())
