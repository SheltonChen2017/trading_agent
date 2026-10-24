"""Committed explicit invoker for freshly scoped extended QC operations.

Every call is explicit: no implicit polling/retries, old captures or projects,
Object Store export, provider discovery or operator-state access. Source bundle
and producer closure must be committed before prepare. CLI emits identities and
aggregate receipts only; licensed inputs and account metadata remain private.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess

from . import extended_evidence as evidence, extended_operations as operations


def preflight():
    if Path.cwd() != operations.LANE or Path.cwd().resolve() != operations.LANE:
        raise operations.Refusal('driver requires exact physical lane')
    def git(*args):
        return subprocess.run(['git', *args], cwd=operations.LANE, capture_output=True, text=True, check=True).stdout.strip()
    if git('rev-parse', '--show-toplevel') != str(operations.LANE) or git('branch', '--show-current') != operations.BRANCH:
        raise operations.Refusal('driver Git lane differs')
    return {'head': git('rev-parse', 'HEAD'), 'status': git('status', '--short')}


def committed(relative, head):
    if type(relative) is not str or not relative.startswith('research/target_price_revisions_qc/'):
        raise operations.Refusal('committed lane bundle/source required')
    path = operations.LANE / relative
    if path.resolve() != path or path.is_symlink() or not path.is_file() or path.stat().st_size > evidence.MAX_BYTES:
        raise operations.Refusal('source path custody refused')
    raw = path.read_bytes()
    recorded = subprocess.run(['git', 'show', head + ':' + relative], cwd=operations.LANE, capture_output=True, check=True).stdout
    if raw != recorded: raise operations.Refusal('producer input is not committed exact bytes')
    return raw


def prepare(operation_id, bundle_path):
    operations._name(operation_id)
    state = preflight()
    bundle = evidence.parse_json(committed(bundle_path, state['head']))
    evidence._closed(bundle, {'schema', 'candidates', 'inputs', 'preparation_sha256', 'repository_sources'})
    if bundle['schema'] != 'tpr-ext26-source-bundle-v1' or type(bundle['repository_sources']) is not list:
        raise operations.Refusal('reviewable committed source bundle required')
    if (not 3 <= len(bundle['repository_sources']) <= 31 or any(type(item) is not str for item in bundle['repository_sources'])
            or len(set(bundle['repository_sources'])) != len(bundle['repository_sources'])):
        raise operations.Refusal('exact bounded producer census required')
    sources = {relative: evidence.digest(committed(relative, state['head'])) for relative in bundle['repository_sources']}
    sources[bundle_path] = evidence.digest(committed(bundle_path, state['head']))
    clock = datetime.now(timezone.utc)
    manifest = {'schema': 'tpr-ext26-operations-manifest-v1', 'study_id': evidence.STUDY_ID,
        'operation_id': operation_id, 'created_utc': clock.isoformat(), 'expires_utc': (clock + timedelta(hours=48)).isoformat(),
        'git_head': state['head'], 'freeze_sha256': evidence.FREEZE_SHA256, 'preparation_sha256': bundle['preparation_sha256'], 'repository_source_hashes': sources,
        'candidates': bundle['candidates'], 'inputs': bundle['inputs'], 'max_requests': 4096,
        'max_response_bytes': evidence.MAX_BYTES, 'request_seconds': 30, 'max_orders': operations.MAX_ORDERS,
        'max_collections': operations.MAX_COLLECTIONS}
    controller = operations.Operations(manifest, manifest_sha256=evidence.digest(evidence.canonical(manifest)))
    return controller.prepare()


def controller_for(operation_id):
    operations._name(operation_id); preflight()
    raw = operations.read_private(operations.PRIVATE_ROOT, 'manifest.' + operation_id + '.json')
    controller = operations.Operations(evidence.parse_json(raw), manifest_sha256=evidence.digest(raw))
    controller.access(); return controller


def _main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'authenticate', 'create', 'inputs', 'sources', 'reserve',
        'compile', 'compile-status', 'launch', 'status', 'orders', 'collect-native'))
    parser.add_argument('--operation', required=True)
    parser.add_argument('--bundle', help='Prepare only: exact committed lane source-bundle path')
    parser.add_argument('--candidate', choices=tuple(evidence.CANDIDATES))
    parser.add_argument('--attempt', type=int)
    args = parser.parse_args(argv)
    preflight()
    if args.action == 'prepare':
        if args.bundle is None: parser.error('--bundle required for prepare')
        result = prepare(args.operation, args.bundle)
    else:
        if args.bundle is not None: parser.error('--bundle is prepare-only')
        controller = controller_for(args.operation)
        if args.action == 'authenticate':
            result = {'authenticated': controller.request('authenticate', {}).get('success') is True}
        else:
            if args.candidate is None: parser.error('--candidate required')
            if args.action in {'compile', 'compile-status', 'launch', 'status', 'orders', 'collect-native'} and args.attempt is None:
                parser.error('--attempt required')
            methods = {'create': controller.create_project, 'inputs': controller.upload_inputs, 'sources': controller.upload_sources,
                'reserve': controller.reserve, 'compile': controller.compile, 'compile-status': controller.compile_status,
                'launch': controller.launch, 'status': controller.status, 'orders': controller.collect_orders, 'collect-native': controller.collect_native}
            result = methods[args.action](args.candidate, args.attempt) if args.action in {'compile', 'compile-status', 'launch', 'status', 'orders', 'collect-native'} else methods[args.action](args.candidate)
            if args.action == 'create':
                result = {key: result[key] for key in ('candidate_id', 'project_id', 'owner', 'lean_version_id')}
    print(evidence.canonical(result).decode(), end='')
    return 0


def main(argv=None):
    try:
        return _main(argv)
    except (operations.Refusal, OSError, ValueError, TypeError, KeyError, subprocess.CalledProcessError):
        # API/input bodies and exception text may contain licensed rows or echoes.
        # Every spent claim remains intact; the invoker never retries implicitly.
        print(evidence.canonical({'status': 'refused_or_uncertain', 'automatic_retry': False}).decode(), end='')
        return 1


if __name__ == '__main__': raise SystemExit(main())
