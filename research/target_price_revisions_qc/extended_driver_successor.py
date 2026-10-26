"""Explicit fresh-scope invoker for the named project-admission successor.

Executed base driver, operation001 claims and cloud strategy sources remain
immutable. A separately committed metadata successor bundle must include both
new producer paths and the discovery helper in its source closure. Recovery
uses original successful metadata only; no recreate, cap refund or implicit
retry exists. Private org/account metadata is never emitted by this CLI.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import subprocess

from . import extended_driver as original_driver
from . import extended_evidence as e
from . import extended_operations as base
from . import extended_operations_successor as successor

preflight, committed = original_driver.preflight, original_driver.committed


def prepare(operation_id, bundle_path):
    base._name(operation_id)
    if operation_id == successor.discovery.DISCOVERY_QC_OPERATION:
        raise base.Refusal('executed original operation is not reusable access')
    state = preflight()
    successor.verify_initializers(state['head'])
    bundle = e.parse_json(committed(bundle_path, state['head']))
    e._closed(bundle, {'schema', 'candidates', 'inputs', 'preparation_sha256', 'repository_sources'})
    names = bundle['repository_sources']
    if (bundle['schema'] != 'tpr-ext26-source-bundle-v1' or type(names) is not list
            or not 6 <= len(names) <= 31 or any(type(name) is not str for name in names)
            or len(set(names)) != len(names) or not successor.REQUIRED <= set(names)):
        raise base.Refusal('committed bounded successor source closure required')
    sources = {name: e.digest(committed(name, state['head'])) for name in names}
    sources[bundle_path] = e.digest(committed(bundle_path, state['head']))
    clock = datetime.now(timezone.utc)
    manifest = {'schema': 'tpr-ext26-operations-manifest-v1', 'study_id': e.STUDY_ID,
        'operation_id': operation_id, 'created_utc': clock.isoformat(), 'expires_utc': (clock + timedelta(hours=48)).isoformat(),
        'git_head': state['head'], 'freeze_sha256': e.FREEZE_SHA256, 'preparation_sha256': bundle['preparation_sha256'],
        'repository_source_hashes': sources, 'candidates': bundle['candidates'], 'inputs': bundle['inputs'],
        'max_requests': base.MAX_REQUESTS, 'max_response_bytes': e.MAX_BYTES, 'request_seconds': 30,
        'max_orders': base.MAX_ORDERS, 'max_collections': base.MAX_COLLECTIONS}
    controller = successor.Operations(manifest, manifest_sha256=e.digest(e.canonical(manifest)))
    return controller.prepare()


def controller_for(operation_id):
    base._name(operation_id); preflight()
    raw = base.read_private(base.PRIVATE_ROOT, 'manifest.' + operation_id + '.json')
    controller = successor.Operations(e.parse_json(raw), manifest_sha256=e.digest(raw))
    controller.access()
    return controller


def _main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'authenticate', 'create', 'recover-project', 'inputs', 'sources', 'reserve',
        'compile', 'compile-status', 'launch', 'status', 'orders', 'collect-native'))
    parser.add_argument('--operation', required=True)
    parser.add_argument('--bundle')
    parser.add_argument('--candidate', choices=tuple(e.CANDIDATES))
    parser.add_argument('--attempt', type=int)
    parser.add_argument('--discovery-receipt')
    parser.add_argument('--discovery-sha256')
    parser.add_argument('--admission')
    parser.add_argument('--admission-sha256')
    args = parser.parse_args(argv); preflight()
    recovery = (args.discovery_receipt, args.discovery_sha256, args.admission, args.admission_sha256)
    if args.action != 'recover-project' and any(value is not None for value in recovery):
        parser.error('discovery arguments are recovery-only')
    if args.action == 'prepare':
        if args.bundle is None or args.candidate is not None or args.attempt is not None:
            parser.error('prepare requires only the committed bundle')
        result = prepare(args.operation, args.bundle)
    else:
        if args.bundle is not None: parser.error('--bundle is prepare-only')
        controller = controller_for(args.operation)
        if args.action == 'authenticate':
            result = {'authenticated': controller.request('authenticate', {}).get('success') is True}
        else:
            if args.candidate is None: parser.error('--candidate required')
            attempted = {'compile', 'compile-status', 'launch', 'status', 'orders', 'collect-native'}
            if args.action in attempted and args.attempt is None: parser.error('--attempt required')
            if args.action not in attempted and args.attempt is not None: parser.error('--attempt is attempt-action only')
            if args.action == 'recover-project':
                if any(value is None for value in recovery): parser.error('all exact discovery/admission arguments required')
                project = controller.recover_project(args.candidate, discovery_receipt_name=args.discovery_receipt,
                    expected_receipt_sha256=args.discovery_sha256, admission_name=args.admission,
                    expected_admission_sha256=args.admission_sha256)
                result = {key: project[key] for key in ('candidate_id', 'project_id', 'owner', 'lean_version_id')}
                result.update(recovered=True, network_creates=0, new_looks=0, quantconnect_attempts=0, privacy_attested=False)
            else:
                methods = {'create': controller.create_project, 'inputs': controller.upload_inputs, 'sources': controller.upload_sources,
                    'reserve': controller.reserve, 'compile': controller.compile, 'compile-status': controller.compile_status,
                    'launch': controller.launch, 'status': controller.status, 'orders': controller.collect_orders,
                    'collect-native': controller.collect_native}
                result = methods[args.action](args.candidate, args.attempt) if args.action in attempted else methods[args.action](args.candidate)
                if args.action == 'create':
                    result = {key: result[key] for key in ('candidate_id', 'project_id', 'owner', 'lean_version_id')}
    print(e.canonical(result).decode(), end='')
    return 0


def main(argv=None):
    try: return _main(argv)
    except (base.Refusal, OSError, ValueError, TypeError, KeyError, subprocess.CalledProcessError):
        print(e.canonical({'status': 'refused_or_uncertain', 'automatic_retry': False}).decode(), end='')
        return 1


if __name__ == '__main__': raise SystemExit(main())
