"""Frozen financial project actions with generated-source and compile custody.

This successor leaves executed historical producers/receipts untouched. Pure
preparation regenerates each frozen arm; it accepts no caller upload bytes,
config hash, generic adapter marker or noneconomic bypass. Production dispatch
uses the real registered API and claims each retained compile input before
reading it. Receipt framing is not independent native-origin attestation.
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time

from . import comparison_20261029_project_api as api
from . import comparison_20261029_project_bundle as bundle

MODULE = 'research/target_price_revisions_qc/comparison_20261030_project_actions.py'
BUNDLE_MODULE = 'research/target_price_revisions_qc/comparison_20261029_project_bundle.py'
PINNED = {
    api.MODULE: '680f31f17447e240f919435ee1d56a9a48526f5197e37ac97332b4b70ee42b87',
    BUNDLE_MODULE: 'a5534dbebc994f3e6ffe301a721f210d9110384216e539f2c2d42c69e8fcb300',
}
REQUIRED_SOURCES = frozenset(api.REQUIRED_SOURCES | set(bundle.SOURCE_PATHS) |
    {MODULE, BUNDLE_MODULE, bundle.OFF_PATH, bundle.MULTI_PATH})
PRIVATE_ROOT = api.PRIVATE_ROOT.parent / 'project-actions-20261030'
PROOF_KEYS = ('compile_plan', 'compile_result', 'source_before', 'compile_response',
    'source_after', 'build_plan', 'build_result', 'build_response')
MAX_PROOF_BYTES = 12 * 1024 * 1024
MAX_INPUT_BYTES = 4 * 1024 * 1024
SPEC_KEYS = frozenset(('arm', 'operation_id', 'attempt', 'prior_attempts_looks_sha256'))
ACTION_KEYS = frozenset(('schema', 'phase', 'financial_spec', 'before_inventory',
    'source_inventory', 'source_inventory_sha256', 'candidate_report_sha256',
    'generated_source_hashes', 'generated_source_bytes', 'compile_evidence',
    'compile_id', 'private_reads_max', 'private_bytes_max', 'api_plan',
    'automatic_retry', 'native_origin_authenticated', 'economics_accepted'))


class ActionRefusal(ValueError):
    pass


class ActionCancelled(KeyboardInterrupt):
    def __init__(self, report):
        self.report = _clone(report)
        super().__init__('financial project action cancelled; no automatic retry')


class ActionFatal(BaseException):
    def __init__(self, report):
        self.report = _clone(report)
        super().__init__('financial project action stopped; no automatic retry')


def _fail():
    raise ActionRefusal('source-bound financial project action refused') from None


def _wire(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True, allow_nan=False).encode('ascii')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _clone(value):
    return json.loads(_wire(value))


def _pairs(rows):
    value = {}
    for key, cell in rows:
        if key in value:
            _fail()
        value[key] = cell
    return value


def _parse(raw, maximum=MAX_INPUT_BYTES):
    if type(raw) is not bytes or not 0 < len(raw) <= maximum:
        _fail()
    try:
        return json.loads(raw, object_pairs_hook=_pairs,
            parse_constant=lambda _: _fail())
    except ActionRefusal:
        raise
    except Exception:
        _fail()


def _closed(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        _fail()


def _hash(value):
    if type(value) is not str or re.fullmatch('[a-f0-9]{64}', value) is None or value == '0'*64:
        _fail()
    return value


def _descriptor(value):
    _closed(value, ('name', 'bytes', 'sha256'))
    if (type(value['name']) is not str or
            re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,159}', value['name']) is None or
            type(value['bytes']) is not int or not 0 < value['bytes'] <= MAX_INPUT_BYTES):
        _fail()
    _hash(value['sha256'])
    return _clone(value)


def _spec(spec):
    _closed(spec, SPEC_KEYS)
    if (spec['arm'] not in api.PROJECT_KEYS or type(spec['attempt']) is not int or
            not 1 <= spec['attempt'] <= 2**31-1 or type(spec['operation_id']) is not str or
            re.fullmatch(r'TPR-CMP28-[A-Za-z0-9][A-Za-z0-9_.-]{0,148}', spec['operation_id']) is None):
        _fail()
    _hash(spec['prior_attempts_looks_sha256'])
    return _clone(spec)


def _candidate(public_sources, registry_raw, registry_sha, financial_spec):
    """Regenerate actual frozen financial bytes, never trust a submitted report."""
    spec = _spec(financial_spec)
    if type(public_sources) is not dict or set(public_sources) != REQUIRED_SOURCES:
        _fail()
    for name, raw in public_sources.items():
        if type(raw) is not bytes or not 0 <= len(raw) <= api.MAX_BODY:
            _fail()
        if name in PINNED and _sha(raw) != PINNED[name]:
            _fail()
    registry = api.projects.validate_bindings(registry_raw, expected_sha256=registry_sha)
    if {key: row['project_id'] for key, row in registry['projects'].items()} != api.REGISTERED_PROJECTS:
        _fail()
    packet = None if spec['arm'] == 'cap_off' else {
        'key': bundle.PACKET_KEY, 'sha256': bundle.PACKET_SHA256,
        'bytes': bundle.PACKET_BYTES, 'encoding': 'utf-8-json',
        'source_inventory_sha256': bundle.INVENTORY_SHA256}
    files, raw_report = bundle.build_project_candidate(
        public_sources={name: public_sources[name] for name in bundle.SOURCE_PATHS},
        project_binding_raw=registry_raw, expected_project_binding_sha256=registry_sha,
        arm=spec['arm'], operation_id=spec['operation_id'], attempt=spec['attempt'],
        prior_attempts_looks_sha256=spec['prior_attempts_looks_sha256'], signal_packet=packet)
    report = _parse(raw_report)
    tree = ast.parse(files['comparison_20261028_config.py'])
    if (len(tree.body) != 1 or not isinstance(tree.body[0], ast.Assign) or
            len(tree.body[0].targets) != 1 or not isinstance(tree.body[0].targets[0], ast.Name) or
            tree.body[0].targets[0].id != 'CONFIG_JSON'):
        _fail()
    raw_config = ast.literal_eval(tree.body[0].value).encode('ascii')
    config = _parse(raw_config)
    project = api.REGISTERED_PROJECTS[api.PROJECT_KEYS[spec['arm']]]
    hashes = {name: _sha(raw) for name, raw in sorted(files.items())}
    if (config['arm'] != spec['arm'] or config['project_id'] != project or
            report['arm'] != spec['arm'] or report['project_id'] != project or
            report['attempt'] != spec['attempt'] or report['operation_id'] != spec['operation_id'] or
            report['config_sha256'] != _sha(raw_config) or report['cloud_source_hashes'] != hashes):
        _fail()
    return spec, files, report, raw_report


def _inventory(value, files, *, full):
    if type(value) is not dict or not 1 <= len(value) <= 25:
        _fail()
    expected = {name: {'bytes': len(raw), 'sha256': _sha(raw)}
        for name, raw in files.items()}
    for name, cell in value.items():
        if name not in expected and name != 'research.ipynb':
            _fail()  # Preserve unknown files, but do not launch them unaudited.
        _closed(cell, ('bytes', 'sha256'))
        if type(cell['bytes']) is not int or not 0 < cell['bytes'] <= 1024*1024:
            _fail()
        _hash(cell['sha256'])
    if full and (not set(expected) <= set(value) or
            any(value[name] != cell for name, cell in expected.items())):
        _fail()
    return _clone(value)


def _request(identity, endpoint, payload, inventory=None):
    result = {'id': identity, 'endpoint': endpoint, 'payload': payload,
        'payload_file': None, 'payload_sha256': api._sha(api._canonical(payload)),
        'max_response_bytes': 2*1024*1024 if endpoint == 'files/read' else 131072,
        'seconds': 30}
    if inventory is not None:
        result['source_inventory_sha256'] = inventory
    return result


def _base(phase, financial_spec, before, inventory, report_raw, files, plan,
        evidence=None, compile_id=None):
    deps = {} if evidence is None else evidence
    return {'schema': 'tpr-cmp30-financial-project-action-v1', 'phase': phase,
        'financial_spec': financial_spec, 'before_inventory': before,
        'source_inventory': inventory,
        'source_inventory_sha256': api._sha(api._canonical(inventory)),
        'candidate_report_sha256': _sha(report_raw),
        'generated_source_hashes': {name: _sha(raw) for name, raw in sorted(files.items())},
        'generated_source_bytes': {name: len(raw) for name, raw in sorted(files.items())},
        'compile_evidence': deps, 'compile_id': compile_id,
        'private_reads_max': len(deps),
        'private_bytes_max': sum(row['bytes'] for row in deps.values()),
        'api_plan': plan, 'automatic_retry': False,
        'native_origin_authenticated': False, 'economics_accepted': False}


def _prepare(phase, *, public_sources, project_bindings_raw,
        expected_project_bindings_sha256, financial_spec, operation_id, git_head,
        owner_instruction_sha256, created_utc, expires_utc, attempt_id,
        reserved_look_id, source_inventory, before_inventory=None,
        compile_evidence=None, compile_id=None, mode='production'):
    spec, files, report, report_raw = _candidate(public_sources, project_bindings_raw,
        expected_project_bindings_sha256, financial_spec)
    project = report['project_id']
    inventory = _inventory(source_inventory, files, full=True)
    pin = api._sha(api._canonical(inventory))
    before = None
    deps = {}
    if phase == 'upload':
        if before_inventory is None or compile_evidence is not None or compile_id is not None:
            _fail()
        before = _inventory(before_inventory, files, full=False)
        expected = {**before, **{name: {'bytes': len(raw), 'sha256': _sha(raw)}
            for name, raw in files.items()}}
        if inventory != expected:
            _fail()
        requests = [_request('before', 'files/read', {'projectId': project},
            api._sha(api._canonical(before)))]
        requests += [_request('write'+str(index), 'files/update' if name in before else 'files/create',
            {'projectId': project, 'name': name, 'content': raw.decode('ascii')})
            for index, (name, raw) in enumerate(sorted(files.items()))]
        requests.append(_request('after', 'files/read', {'projectId': project}, pin))
    elif phase == 'compile':
        if before_inventory is not None or compile_evidence is not None or compile_id is not None:
            _fail()
        requests = [_request('before', 'files/read', {'projectId': project}, pin),
            _request('compile', 'compile/create', {'projectId': project}),
            _request('after', 'files/read', {'projectId': project}, pin)]
    elif phase == 'launch':
        if before_inventory is not None or compile_evidence is None:
            _fail()
        _closed(compile_evidence, PROOF_KEYS)
        deps = {key: _descriptor(value) for key, value in compile_evidence.items()}
        if len({row['name'] for row in deps.values()}) != len(deps):
            _fail()
        if sum(row['bytes'] for row in deps.values()) > MAX_PROOF_BYTES:
            _fail()
        api._identity(compile_id)
        requests = [_request('before', 'files/read', {'projectId': project}, pin),
            _request('launch', 'backtests/create', {'projectId': project, 'compileId': compile_id,
                'backtestName': 'TPR-CMP30-'+api.PROJECT_KEYS[spec['arm']]+'-A'+str(spec['attempt'])}),
            _request('after', 'files/read', {'projectId': project}, pin)]
    else:
        _fail()
    plan = api.prepare_plan(project_bindings_raw=project_bindings_raw,
        expected_project_bindings_sha256=expected_project_bindings_sha256,
        arm=spec['arm'], candidate_config_sha256=report['config_sha256'],
        candidate_attempt=spec['attempt'], operation_id=operation_id, git_head=git_head,
        source_hashes={name: _sha(raw) for name, raw in public_sources.items()},
        owner_instruction_sha256=owner_instruction_sha256,
        created_utc=created_utc, expires_utc=expires_utc, requests=requests,
        allowed_source_hashes={name: _sha(raw) for name, raw in files.items()} if phase == 'upload' else {},
        attempt_id=attempt_id, reserved_look_id=reserved_look_id,
        max_total_response_bytes=sum(row['max_response_bytes'] for row in requests), mode=mode)
    return _base(phase, spec, before, inventory, report_raw, files, plan, deps, compile_id)


def prepare_upload(**kwargs):
    """Pure complete frozen upload; caller cannot supply source bodies or fees."""
    try:
        return _prepare('upload', **kwargs)
    except ActionRefusal:
        raise
    except Exception:
        _fail()


def prepare_compile(**kwargs):
    """Pure source-pinned compile of an already verified full financial bundle."""
    try:
        return _prepare('compile', **kwargs)
    except ActionRefusal:
        raise
    except Exception:
        _fail()


def prepare_launch(**kwargs):
    """Pure framed launch; retained compile evidence is checked again before effect."""
    try:
        return _prepare('launch', **kwargs)
    except ActionRefusal:
        raise
    except Exception:
        _fail()


def _validate(action, public_sources):
    _closed(action, ACTION_KEYS)
    plan = action['api_plan']
    if type(plan) is not dict:
        _fail()
    args = dict(public_sources=public_sources,
        project_bindings_raw=plan['project_bindings_json'].encode('utf-8'),
        expected_project_bindings_sha256=plan['project_bindings_sha256'],
        financial_spec=action['financial_spec'], operation_id=plan['operation_id'],
        git_head=plan['git_head'], owner_instruction_sha256=plan['owner_instruction_sha256'],
        created_utc=plan['created_utc'], expires_utc=plan['expires_utc'],
        attempt_id=plan['attempt_id'], reserved_look_id=plan['reserved_look_id'],
        source_inventory=action['source_inventory'], before_inventory=action['before_inventory'],
        compile_evidence=action['compile_evidence'] or None, compile_id=action['compile_id'],
        mode=plan['mode'])
    expected = _prepare(action['phase'], **args)
    if _wire(expected) != _wire(action):
        _fail()
    return expected


def _raw_descriptor(raw, descriptor):
    if type(raw) is not bytes or len(raw) != descriptor['bytes'] or _sha(raw) != descriptor['sha256']:
        _fail()


def _raw_inventory(raw, project):
    body = _parse(raw)
    if type(body) is not dict or body.get('success') is not True:
        _fail()
    if 'projectId' in body and type(body['projectId']) is not int:
        _fail()
    if 'projectId' in body and body['projectId'] != project:
        _fail()
    rows = body.get('files')
    if type(rows) is not list or not 1 <= len(rows) <= 25:
        _fail()
    found = {}
    for row in rows:
        if (type(row) is not dict or type(row.get('name')) is not str or
                row['name'] in found or type(row.get('content')) is not str or
                'projectId' in row and (type(row['projectId']) is not int or row['projectId'] != project)):
            _fail()
        raw_file = row['content'].encode('utf-8')
        if not 0 < len(raw_file) <= 1024*1024:
            _fail()
        found[row['name']] = {'bytes': len(raw_file), 'sha256': _sha(raw_file)}
    return found


def _result(raw, plan):
    result = _parse(raw)
    if (type(result) is not dict or result.get('schema') != 'tpr-cmp29-project-api-result-v1' or
            result.get('status') != 'completed' or result.get('receipt_published') is not True or
            result.get('lock_cleanup_complete') is not True or
            result.get('plan_sha256') != api._sha(api._canonical(plan)) or
            type(result.get('actual_new_backtests')) is not int or result['actual_new_backtests'] != 0 or
            result.get('observed_new_backtest_ids') != [] or
            result.get('economics_accepted') is not False or result.get('market_trading_authorized') is not False):
        _fail()
    if type(result.get('project_id')) is not int or type(result.get('candidate_attempt')) is not int:
        _fail()
    for key in ('operation_id', 'project_id', 'arm', 'project_registration_key',
            'project_bindings_sha256', 'candidate_config_sha256', 'candidate_attempt',
            'candidate_binding_sha256', 'attempt_id', 'reserved_look_id'):
        if result.get(key) != plan.get(key):
            _fail()
    rows = result.get('requests')
    if type(rows) is not list or len(rows) != len(plan['requests']):
        _fail()
    for row, request in zip(rows, plan['requests']):
        if (type(row) is not dict or row.get('id') != request['id'] or
                row.get('endpoint') != request['endpoint'] or row.get('status') != 'succeeded' or
                row.get('http_status') != 200):
            _fail()
    return result


def _proof(action, raws):
    """Check retained native wire/plan/result chain; never infer from a compile ID."""
    _closed(raws, PROOF_KEYS)
    deps = action['compile_evidence']
    for key in PROOF_KEYS:
        _raw_descriptor(raws[key], deps[key])
    compile_plan = _parse(raws['compile_plan'])
    build_plan = _parse(raws['build_plan'])
    try:
        compile_plan = api._validated(compile_plan)
        build_plan = api._validated(build_plan)
    except Exception:
        _fail()
    launch = action['api_plan']
    for plan in (compile_plan, build_plan):
        for key in ('project_id', 'arm', 'project_registration_key',
                'project_bindings_sha256', 'candidate_config_sha256', 'candidate_attempt',
                'candidate_binding_sha256', 'git_head', 'owner_instruction_sha256'):
            if plan[key] != launch[key]:
                _fail()
        if plan['mode'] != launch['mode']:
            _fail()
    if ([row['endpoint'] for row in compile_plan['requests']] != ['files/read', 'compile/create', 'files/read'] or
            compile_plan['allowed_source_hashes'] != {} or
            compile_plan['source_hashes'] != launch['source_hashes'] or
            build_plan['source_hashes'] != launch['source_hashes'] or
            [row['endpoint'] for row in build_plan['requests']] != ['compile/read']):
        _fail()
    if (compile_plan['attempt_id'] is None or compile_plan['reserved_look_id'] is None or
            compile_plan['operation_id'] == launch['operation_id'] or
            build_plan['operation_id'] in (compile_plan['operation_id'], launch['operation_id'])):
        _fail()
    compiled = _result(raws['compile_result'], compile_plan)
    built = _result(raws['build_result'], build_plan)
    if compiled.get('compile_requests_attempted') != 1 or built.get('compile_requests_attempted') != 0:
        _fail()
    expected_names = {
        'compile_plan': compile_plan['operation_id']+'.operation.spent.json',
        'compile_result': compile_plan['operation_id']+'.result.json',
        'build_plan': build_plan['operation_id']+'.operation.spent.json',
        'build_result': build_plan['operation_id']+'.result.json'}
    for key, name in expected_names.items():
        if deps[key]['name'] != name:
            _fail()
    identities = ((compiled['requests'][0], 'source_before', compile_plan),
        (compiled['requests'][1], 'compile_response', compile_plan),
        (compiled['requests'][2], 'source_after', compile_plan),
        (built['requests'][0], 'build_response', build_plan))
    for row, key, plan in identities:
        if (row.get('raw_response') != deps[key] or
                deps[key]['name'] != plan['operation_id']+'.'+row['id']+'.response.raw'):
            _fail()
    pin = action['source_inventory_sha256']
    for row, raw_key, request in ((compiled['requests'][0], 'source_before', compile_plan['requests'][0]),
            (compiled['requests'][2], 'source_after', compile_plan['requests'][2])):
        inv = _raw_inventory(raws[raw_key], launch['project_id'])
        if (inv != action['source_inventory'] or row.get('source_inventory') != inv or
                row.get('source_inventory_sha256') != pin or request.get('source_inventory_sha256') != pin):
            _fail()
    created = _parse(raws['compile_response'])
    ready = _parse(raws['build_response'])
    for body in (created, ready):
        if (type(body) is not dict or body.get('success') is not True or
                body.get('compileId') != action['compile_id'] or
                'projectId' in body and (type(body['projectId']) is not int or body['projectId'] != launch['project_id'])):
            _fail()
    if (type(created.get('state')) is not str or not 0 < len(created['state']) <= 40 or
            ready.get('state') != 'BuildSuccess' or
            compiled['requests'][1].get('compile_id') != action['compile_id'] or
            compiled['requests'][1].get('compile_state') != created['state'] or
            built['requests'][0].get('compile_id') != action['compile_id'] or
            built['requests'][0].get('compile_state') != 'BuildSuccess' or
            build_plan['requests'][0]['payload'] != {
                'projectId': launch['project_id'], 'compileId': action['compile_id']}):
        _fail()
    # Plan times are prospective; this is not a remote atomic-CAS or clock attestation.
    if not (api._clock(compile_plan['created_utc']) <= api._clock(build_plan['created_utc'])
            <= api._clock(launch['created_utc'])):
        _fail()
    return True


def _load_sources(action):
    """Public committed source only. Private reads occur exclusively after claims."""
    plan = action['api_plan']
    api._guard(plan)
    if Path(__file__) != api.LANE/MODULE:
        _fail()
    sources = {}
    for name in REQUIRED_SOURCES:
        path = api.LANE/name
        if path.resolve() != path or path.is_symlink() or not path.is_file() or path.stat().st_size > api.MAX_BODY:
            _fail()
        sources[name] = path.read_bytes()
    return sources


def _execute(action, root, api_root, *, public_sources, api_execute, guard,
        clock, monotonic, production):
    action = _validate(action, public_sources)
    plan = action['api_plan']
    if (production and (root != PRIVATE_ROOT or api_root != api.PRIVATE_ROOT or
            api_execute is not api.execute_plan or guard is not api._guard or
            clock is not api._utcnow or monotonic is not time.monotonic or plan['mode'] != 'production') or
            not production and (plan['mode'] != 'offline-fixture' or
                root == PRIVATE_ROOT or root.is_relative_to(api.LANE) or
                api_root == api.PRIVATE_ROOT or api_root.is_relative_to(api.LANE) or
                api_execute is api.execute_plan)):
        _fail()
    frozen = _wire(action)
    started = monotonic()
    last_now = last_tick = None

    def check():
        nonlocal last_now, last_tick
        guard(plan)
        now, tick = clock(), monotonic()
        if (type(now) is not datetime or now.utcoffset() != timedelta(0) or
                not api._clock(plan['created_utc']) <= now < api._clock(plan['expires_utc']) or
                type(tick) not in (int, float) or not 0 <= tick-started < 600 or
                last_now is not None and now < last_now or last_tick is not None and tick < last_tick or
                _wire(action) != frozen):
            _fail()
        last_now, last_tick = now, tick

    check()
    if root.resolve() != root or api_root.resolve() != api_root:
        _fail()
    if production:
        for path in (api.ops.PRIVATE_PARENT, PRIVATE_ROOT.parent, PRIVATE_ROOT):
            path.mkdir(mode=0o700, exist_ok=True)
            api.ops._custody(path.lstat(), True)
    else:
        root.mkdir(mode=0o700, exist_ok=True)
        api.ops._custody(root.lstat(), True)
    operation = plan['operation_id']
    result = {'schema': 'tpr-cmp30-financial-project-action-result-v1',
        'operation_id': operation, 'phase': action['phase'],
        'project_id': plan['project_id'], 'arm': plan['arm'],
        'candidate_config_sha256': plan['candidate_config_sha256'],
        'action_sha256': _sha(frozen), 'status': 'failed_or_uncertain',
        'private_reads_max': action['private_reads_max'], 'private_reads_attempted': 0,
        'private_bytes_max': action['private_bytes_max'], 'private_bytes_read': 0,
        'private_bytes_read_semantics': 'returned_bytes_not_unobserved_partial_reads',
        'action_claim_published': None, 'dependency_claims': [], 'native_api_result': None,
        'receipt_published': False, 'automatic_retry': False,
        'native_origin_authenticated': False, 'economics_accepted': False}
    stop = None
    try:
        api._publish(root, operation+'.action.spent.json', frozen)
        result['action_claim_published'] = True
    except KeyboardInterrupt:
        result['status'] = 'cancelled'
        raise ActionCancelled(result) from None
    except BaseException as error:
        if not isinstance(error, Exception):
            raise ActionFatal(result) from None
        _fail()
    try:
        raws = {}
        for key in PROOF_KEYS if action['phase'] == 'launch' else ():
            descriptor = action['compile_evidence'][key]
            check()
            claim = api._publish(root, operation+'.'+key+'.read.spent.json',
                _wire({'action_sha256': result['action_sha256'], 'git_head': plan['git_head'],
                    'source_hashes': plan['source_hashes'], 'created_utc': plan['created_utc'],
                    'expires_utc': plan['expires_utc'], 'purpose': 'exact retained compile proof',
                    'input': descriptor, 'project_id': plan['project_id'], 'arm': plan['arm'],
                    'attempt_id': plan['attempt_id'], 'reserved_look_id': plan['reserved_look_id']}))
            result['dependency_claims'].append(claim)
            check()  # Claim fsync may consume the remaining access window.
            if result['private_reads_attempted'] >= action['private_reads_max']:
                _fail()
            result['private_reads_attempted'] += 1
            raw = api.ops.read_private(api_root, descriptor['name'], descriptor['bytes'])
            result['private_bytes_read'] += len(raw)
            if result['private_bytes_read'] > action['private_bytes_max']:
                _fail()
            _raw_descriptor(raw, descriptor)
            raws[key] = raw
            check()
        if action['phase'] == 'launch':
            _proof(action, raws)
        check()
        result['native_api_result'] = api_execute(plan)
        check()
        if (type(result['native_api_result']) is not dict or
                result['native_api_result'].get('plan_sha256') != api._sha(api._canonical(plan))):
            _fail()
        result['status'] = ('completed' if result['native_api_result'].get('status') == 'completed'
            else 'failed_or_uncertain')
    except BaseException as error:
        stop = error
        if isinstance(error, (api.APICancelled, api.APIFatal)):
            result['native_api_result'] = _clone(error.report)
    finally:
        if stop is not None:
            result['status'] = 'cancelled' if isinstance(stop, KeyboardInterrupt) else 'failed_or_uncertain'
        result['receipt_published'] = True
        try:
            result['receipt'] = api._publish(root, operation+'.result.json', _wire(result))
        except BaseException as error:
            result['receipt_published'] = False
            stop = api._retain_stop(stop, error)
            result['status'] = 'cancelled' if isinstance(stop, KeyboardInterrupt) else 'failed_or_uncertain'
    if isinstance(stop, KeyboardInterrupt):
        raise ActionCancelled(result) from None
    if stop is not None and not isinstance(stop, Exception):
        raise ActionFatal(result) from None
    return _clone(result)


def execute_action(action):
    """Real registered API only; no callback, flag or synthetic adapter admission."""
    try:
        sources = _load_sources(action)
        return _execute(action, PRIVATE_ROOT, api.PRIVATE_ROOT, public_sources=sources,
            api_execute=api.execute_plan, guard=api._guard, clock=api._utcnow,
            monotonic=time.monotonic, production=True)
    except (ActionCancelled, ActionFatal):
        raise
    except Exception:
        _fail()


def _execute_fixture(action, root, api_root, *, public_sources, api_execute,
        clock, guard=lambda _: None, monotonic=lambda: 0.0):
    """Synthetic temp roots only; never a production native-authority adapter."""
    return _execute(action, root, api_root, public_sources=public_sources,
        api_execute=api_execute, guard=guard, clock=clock, monotonic=monotonic,
        production=False)
