"""Fixed single-base prospective exact-SID cash variant; no import or preparation I/O.

Regenerate financial bytes from the new pinned builder. The exclusion changes
economics from the original study and never establishes acceptance. Private
compile proofs and each native request require fresh durable claims. Immutable
project-creation authority is distinct from the latest owner instruction.
Historical producers, evidence and routes remain unchanged.
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

from . import comparison_20261029_project_api as api
from . import comparison_20261029_project_bundle as bundle
from . import comparison_20261103_preflight as preflight
from . import comparison_20261107_sid_cash_single_base_bundle as cash_bundle
from . import comparison_20261103_project_custody as custody

projects, ops, evidence = api.projects, api.ops, api.e

MODULE = 'research/target_price_revisions_qc/comparison_20261107_sid_cash_single_base_actions.py'
CASH_BUNDLE_MODULE = 'research/target_price_revisions_qc/comparison_20261107_sid_cash_single_base_bundle.py'
STUDY_ID = 'TPR-SIX-UNIVERSE-FIVE-ARM-SID-CASH-20261107-v1'
SOURCE_EPOCH = 'TPR-SID-CASH-SINGLE-BASE-20261107-v2'
CURRENT_OWNER_SHA256 = '54a40d169a093baa0ee4efc8963799a0c24483631881708942a21774e751c2fa'
PREFLIGHT_MODULE = 'research/target_price_revisions_qc/comparison_20261103_preflight.py'
REGISTRY_CREATION_OWNER_SHA256 = 'ea2dd7037a0f33ab78771a2f6deb3016da34b164ab04f5b2c69f30c4ae31157f'
CURRENT_NO_QC_OWNER_SHA256 = '2a2c63386634e2ebbe4504bb8938827d5b19fdd0f895257b26a1df16673278c4'
CURRENT_NO_QC_OR_SAFARI_OWNER_SHA256 = '248f50170a8b85644a109959aafe181b2240c5e09e50165c61cfa36b986086b8'
CURRENT_REMX_LOCAL_REPAIR_OWNER_SHA256 = 'feaed725a68dabae6283578d21e55dddd70bb78ace7a6cedfc40b2b5665dfeb0'
CURRENT_REMX_FOLLOWUP_OWNER_SHA256 = '4cb8250f94c8f79e54b0bad593d926fc4d36527733e661c239126800ffdc757a'
CURRENT_LOCAL_PREBACKTEST_OWNER_SHA256 = 'cbe4ec0970d66d09ab8da68d35b78383ead0ae6ea5c0b19177003492a89ddc2e'
BLOCKED_OWNER_INSTRUCTION_SHA256S = frozenset((
    CURRENT_NO_QC_OWNER_SHA256, CURRENT_NO_QC_OR_SAFARI_OWNER_SHA256,
    CURRENT_REMX_LOCAL_REPAIR_OWNER_SHA256, CURRENT_REMX_FOLLOWUP_OWNER_SHA256,
    CURRENT_LOCAL_PREBACKTEST_OWNER_SHA256))
OPAQUE_NOTEBOOKS = frozenset(('research.ipynb', 'mia.ipynb'))
BUNDLE_MODULE = 'research/target_price_revisions_qc/comparison_20261029_project_bundle.py'
PINNED = {
    'research/target_price_revisions_qc/comparison_20261028_api.py': 'a2a160ac951a8a9f96b9531e5b51a5bf6b4e7b116b7873f77515780f059ebc5a',
    'research/target_price_revisions_qc/extended_operations.py': '824b3f0c180f1aeb7038d8f280c44507b5c39687fcccc87c539f242d9256d167',
    'research/target_price_revisions_qc/extended_evidence.py': 'a816b1ddca5a8428f07e9029bc3a7f7db3c5e1a1f50521664992dabf556aa2d7',
    'research/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'research/target_price_revisions_qc/__init__.py': '3bc79e69bc0c775d8ef0ec154551436011cba407f37690c27ccbeb9000153c59',
    CASH_BUNDLE_MODULE: 'fb75e8cde2f99b1ace170e42d74d00b77714b3611a1dc7c117f5ec3f614e0dd1',
    custody.MODULE: '702d31144a7e62b59a53d374af695078f150809b19f0992415e690d07fa418a4',
    api.MODULE: '680f31f17447e240f919435ee1d56a9a48526f5197e37ac97332b4b70ee42b87',
    BUNDLE_MODULE: 'a5534dbebc994f3e6ffe301a721f210d9110384216e539f2c2d42c69e8fcb300',
    PREFLIGHT_MODULE: 'e16d50cd8bb3fa0716b9e1994552f07b2dcf02554493c6bbf1b41661de847082',
    preflight.RECOVERY_PATH: '14083a5213f24e929c21308f507ad28e18fdd92dbfdd6c3d29581749631e253a',
}
REQUIRED_SOURCES = frozenset(api.REQUIRED_SOURCES | cash_bundle.REQUIRED_SOURCES |
    {MODULE, CASH_BUNDLE_MODULE, custody.MODULE})
PRIVATE_ROOT = api.ops.PRIVATE_PARENT / STUDY_ID / 'project-actions-20261107-sid-cash-single-base-v2'
NATIVE_ROOT = api.ops.PRIVATE_PARENT / STUDY_ID / 'project-native-20261107-sid-cash-single-base-v2'
MAX_OUTPUT_BYTES = 32*1024*1024
SECONDS = 20
MIA_PUBLIC_ID_SHA256 = '790fd84f9177e87e0c5bc385f8bef44e107330b3d2ff329d9b59f26298704ee1'
MIA_PRIVACY_BASIS = 'owner_and_authorized_mia_component'
TERMINAL = frozenset(('Completed', 'Completed.', 'Runtime Error', 'RuntimeError', 'Error', 'Stopped', 'Cancelled'))
KNOWN_PUBLIC_EXTRAS = {'tpr_public_parent_source_20261107.py': {
    'bytes': 17368,
    'sha256': '8ab9c6dd9bbeb57c4e29dc88f4b0131046cba15a90899ddc44382ed73e13a98a'}}
PROOF_KEYS = ('compile_plan', 'compile_result', 'source_before', 'compile_response',
    'source_after', 'build_plan', 'build_result', 'build_response')
MAX_PROOF_BYTES = 12 * 1024 * 1024
MAX_INPUT_BYTES = 4 * 1024 * 1024
SPEC_KEYS = frozenset(('arm', 'operation_id', 'attempt', 'prior_attempts_looks_sha256',
    'latest_owner_instruction_sha256'))
ACTION_KEYS = frozenset(('schema', 'phase', 'financial_spec', 'before_inventory',
    'source_inventory', 'source_inventory_sha256', 'candidate_report_sha256',
    'generated_source_hashes', 'generated_source_bytes', 'compile_evidence',
    'compile_id', 'private_reads_max', 'private_bytes_max', 'api_plan',
    'automatic_retry', 'native_origin_authenticated', 'economics_accepted',
    'study_id', 'source_epoch', 'strategy_economics_changed', 'native_requests_max', 'native_response_bytes_max'))


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
            not 1 <= spec['attempt'] <= 3 or type(spec['operation_id']) is not str or
            re.fullmatch(r'TPR-CMP28-' + ('OFF-' if spec['arm'] == 'cap_off' else '') +
                r'SID-CASH-20261107-[A-Za-z0-9][A-Za-z0-9_.-]{0,100}', spec['operation_id']) is None):
        _fail()
    _hash(spec['prior_attempts_looks_sha256'])
    _hash(spec['latest_owner_instruction_sha256'])
    if spec['latest_owner_instruction_sha256'] != CURRENT_OWNER_SHA256:
        _fail()  # The current explicit deferral is never native-effect authority.
    _operational_id(spec['operation_id'])
    return _clone(spec)



def _operational_id(value):
    # Offline preview metadata never spends or substitutes a native identity.
    if type(value) is not str or any(word in value.upper() for word in ('OFFLINE', 'PREVIEW')):
        _fail()
    return value


def _candidate(public_sources, registry_raw, registry_sha, financial_spec):
    """Regenerate exact cash-variant financial bytes, never trust a submitted report."""
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
    files, raw_report = cash_bundle.build_cash_candidate(
        public_sources={name: public_sources[name] for name in cash_bundle.REQUIRED_SOURCES},
        project_bindings_raw=registry_raw,
        expected_project_bindings_sha256=registry_sha,
        arm=spec['arm'], operation_id=spec['operation_id'], attempt=spec['attempt'],
        prior_attempts_looks_sha256=spec['prior_attempts_looks_sha256'],
        latest_owner_instruction_sha256=spec['latest_owner_instruction_sha256'])
    report = _parse(raw_report)
    if (report.get('schema') != 'tpr-cmp1107-sid-cash-single-base-project-bundle-v2' or
            report.get('study_id') != STUDY_ID or
            report.get('source_epoch') != SOURCE_EPOCH or
            report.get('strategy_economics_changed') is not True or
            report.get('economics_accepted') is not False or
            report.get('latest_owner_instruction_sha256') != CURRENT_OWNER_SHA256):
        _fail()
    if set(files) & (OPAQUE_NOTEBOOKS | set(KNOWN_PUBLIC_EXTRAS)):
        _fail()
    for name, raw in files.items():
        if (name not in api.WRITE_FILES or type(raw) is not bytes or
                not 0 < len(raw) <= 60000 or b'\r' in raw or not raw.endswith(b'\n')):
            _fail()
        raw.decode('ascii')
        ast.parse(raw, filename=name)
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
        if name not in expected and name not in OPAQUE_NOTEBOOKS and name not in KNOWN_PUBLIC_EXTRAS:
            _fail()  # Preserve unknown files, but do not launch them unaudited.
        _closed(cell, ('bytes', 'sha256'))
        if type(cell['bytes']) is not int or not 0 < cell['bytes'] <= 1024*1024:
            _fail()
        _hash(cell['sha256'])
        if name in KNOWN_PUBLIC_EXTRAS and cell != KNOWN_PUBLIC_EXTRAS[name]:
            _fail()
    if full and (not set(expected) <= set(value) or
            any(value[name] != cell for name, cell in expected.items())):
        _fail()
    return _clone(value)


def _request(identity, endpoint, payload, inventory=None):
    result = {'id': identity, 'endpoint': endpoint, 'payload': payload,
        'payload_file': None, 'payload_sha256': api._sha(api._canonical(payload)),
        'max_response_bytes': 2*1024*1024 if endpoint in ('files/read', 'backtests/list') else 131072,
        'seconds': SECONDS}
    if inventory is not None:
        result['source_inventory_sha256'] = inventory
    return result


def _base(phase, financial_spec, before, inventory, report_raw, files, plan,
        evidence=None, compile_id=None):
    deps = {} if evidence is None else evidence
    return {'schema': 'tpr-cmp1107-sid-cash-financial-project-action-v1', 'phase': phase,
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
        'native_origin_authenticated': False, 'economics_accepted': False,
        'study_id': STUDY_ID, 'source_epoch': SOURCE_EPOCH,
        'strategy_economics_changed': True,
        'native_requests_max': len(plan['requests']) + 3,
        'native_response_bytes_max': sum(row['max_response_bytes'] for row in _native_requests(plan))}


def _prepare(phase, *, public_sources, project_bindings_raw,
        expected_project_bindings_sha256, financial_spec, operation_id, git_head,
        owner_instruction_sha256, created_utc, expires_utc, attempt_id,
        reserved_look_id, source_inventory, before_inventory=None,
        compile_evidence=None, compile_id=None, mode='production'):
    _spec(financial_spec)
    _operational_id(operation_id)
    if mode == 'production' and (
            expected_project_bindings_sha256 != preflight.REGISTRY_SHA256
            or type(project_bindings_raw) is not bytes
            or len(project_bindings_raw) != preflight.REGISTRY_BYTES
            or owner_instruction_sha256 != REGISTRY_CREATION_OWNER_SHA256):
        _fail()
    spec, files, report, report_raw = _candidate(public_sources, project_bindings_raw,
        expected_project_bindings_sha256, financial_spec)
    if spec['latest_owner_instruction_sha256'] == owner_instruction_sha256:
        _fail()  # Current authority and immutable creation authority stay separate.
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
    elif phase == 'build':
        if before_inventory is not None or compile_evidence is not None:
            _fail()
        api._identity(compile_id)
        requests = [_request('build', 'compile/read', {'projectId': project, 'compileId': compile_id})]
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
                'backtestName': 'SID-CASH-SINGLE-BASE-20261107-'+api.PROJECT_KEYS[spec['arm']]+'-A'+str(spec['attempt'])}),
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
        attempt_id=None if phase == 'build' else attempt_id,
        reserved_look_id=None if phase == 'build' else reserved_look_id,
        max_total_response_bytes=sum(row['max_response_bytes'] for row in requests), mode=mode)
    if sum(row['seconds'] for row in _native_requests(plan)) > (api._clock(expires_utc)-api._clock(created_utc)).total_seconds():
        _fail()
    return _base(phase, spec, before, inventory, report_raw, files, plan, deps, compile_id)


def prepare_upload(**kwargs):
    """Pure exact cash-variant upload; caller cannot supply source bodies or fees."""
    try:
        return _prepare('upload', **kwargs)
    except ActionRefusal:
        raise
    except Exception:
        _fail()


def prepare_compile(**kwargs):
    """Pure source-pinned compile of the full cash-variant financial bundle."""
    try:
        return _prepare('compile', **kwargs)
    except ActionRefusal:
        raise
    except Exception:
        _fail()


def prepare_build(**kwargs):
    """Pure fixed compile/read plan; no generic request or mutation surface."""
    try:
        return _prepare('build', **kwargs)
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
    if (type(result) is not dict or result.get('schema') != 'tpr-cmp1107-sid-cash-native-result-v1' or
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
    if (result.get('study_id') != STUDY_ID or result.get('source_epoch') != SOURCE_EPOCH
            or result.get('strategy_economics_changed') is not True
            or result.get('latest_owner_instruction_sha256') != CURRENT_OWNER_SHA256
            or result.get('preflight_complete') is not True
            or type(rows) is not list or len(rows) != len(plan['requests']) + 3):
        _fail()
    for row, request in zip(rows, _native_requests(plan)):
        if (type(row) is not dict or row.get('id') != request['id'] or
                row.get('endpoint') != request['endpoint'] or row.get('status') != 'succeeded' or
                row.get('http_status') != 200):
            _fail()
    result['requests'] = rows[3:]
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
        _operational_id(plan['operation_id'])
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
    if production:
        _fail()
    action = _validate(action, public_sources)
    plan = action['api_plan']
    if (production and (root != PRIVATE_ROOT or api_root != NATIVE_ROOT or
            api_execute is not api.execute_plan or guard is not api._guard or
            clock is not api._utcnow or monotonic is not time.monotonic or plan['mode'] != 'production') or
            not production and (plan['mode'] != 'offline-fixture' or
                root == PRIVATE_ROOT or root.is_relative_to(api.LANE) or
                api_root == NATIVE_ROOT or api_root.is_relative_to(api.LANE) or
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
    result = {'schema': 'tpr-cmp1107-sid-cash-financial-project-action-result-v1',
        'operation_id': operation, 'phase': action['phase'],
        'project_id': plan['project_id'], 'arm': plan['arm'],
        'candidate_config_sha256': plan['candidate_config_sha256'],
        'latest_owner_instruction_sha256': action['financial_spec']['latest_owner_instruction_sha256'],
        'registry_creation_owner_instruction_sha256': plan['owner_instruction_sha256'],
        'action_sha256': _sha(frozen), 'status': 'failed_or_uncertain',
        'private_reads_max': action['private_reads_max'], 'private_reads_attempted': 0,
        'private_bytes_max': action['private_bytes_max'], 'private_bytes_read': 0,
        'private_bytes_read_semantics': 'returned_bytes_not_unobserved_partial_reads',
        'action_claim_published': None, 'dependency_claims': [], 'native_api_result': None,
        'receipt_published': False, 'automatic_retry': False,
        'native_origin_authenticated': False, 'economics_accepted': False,
        'study_id': STUDY_ID, 'source_epoch': SOURCE_EPOCH,
        'strategy_economics_changed': True,
        'native_requests_max': len(plan['requests']) + 3,
        'native_response_bytes_max': sum(row['max_response_bytes'] for row in _native_requests(plan))}
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
                    'attempt_id': plan['attempt_id'], 'reserved_look_id': plan['reserved_look_id'],
                    'latest_owner_instruction_sha256': action['financial_spec']['latest_owner_instruction_sha256']}))
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


def _execute_fixture(action, root, api_root, *, public_sources, api_execute,
        clock, guard=lambda _: None, monotonic=lambda: 0.0):
    """Synthetic temp roots only; never a production native-authority adapter."""
    return _execute(action, root, api_root, public_sources=public_sources,
        api_execute=api_execute, guard=guard, clock=clock, monotonic=monotonic,
        production=False)


def _read_proof(root, descriptor):
    """Anchored nonblocking regular-file read; no legacy special-file open."""
    directory = leaf = None
    def stamp(value):
        return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    try:
        with ops.wall_deadline(SECONDS):
            directory = os.open(root, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            parent = os.fstat(directory)
            ops._custody(parent, True)
            leaf = os.open(descriptor["name"], os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK, dir_fd=directory)
            before = os.fstat(leaf)
            ops._custody(before)
            if not stat.S_ISREG(before.st_mode) or before.st_size != descriptor["bytes"] or before.st_nlink != 1:
                _fail()
            if stamp(os.stat(descriptor["name"], dir_fd=directory, follow_symlinks=False)) != stamp(before):
                _fail()
            chunks, remaining = [], descriptor["bytes"]
            while remaining:
                part = os.read(leaf, min(remaining, 131072))
                if not part:
                    _fail()
                chunks.append(part)
                remaining -= len(part)
            raw = b"".join(chunks)
            named_root = os.stat(root, follow_symlinks=False)
            if ((named_root.st_dev, named_root.st_ino) != (parent.st_dev, parent.st_ino)
                    or stamp(os.fstat(leaf)) != stamp(before)
                    or stamp(os.stat(descriptor["name"], dir_fd=directory, follow_symlinks=False)) != stamp(before)
                    or _sha(raw) != descriptor["sha256"]):
                _fail()
            return raw
    finally:
        if leaf is not None: os.close(leaf)
        if directory is not None: os.close(directory)



def _native_integer(value):
    try:
        if type(value) is not int:
            _fail()
        return projects._integer(value)
    except Exception:
        _fail()


def _component_context(context, registry, project):
    # Check present documented context fields; absence is not invented evidence.
    for key, expected in (("projectId", project), ("ownerId", registry["owner_id"])):
        if key in context and _native_integer(context[key]) != expected:
            _fail()
    if "organizationId" in context and context["organizationId"] != registry["organization_id"]:
        _fail()
    for key, private_value in (("isPublic", False), ("public", False),
            ("isPrivate", True), ("private", True), ("shared", False)):
        if key in context and context[key] is not private_value:
            _fail()


def _component_collaborators(rows, registry, latest_owner_instruction_sha256, project, arm):
    """This OFF component uses owner direction plus an exact instance hash.

    Nullable UID or a display name alone proves nothing. This recognition is
    deliberately not independent platform/agent identity attestation, and it
    changes no permission or live authority. Unknown and duplicate actors fail.
    """
    if arm != "cap_off":
        return projects._collaborators(rows, registry["owner_id"]), rows
    if (latest_owner_instruction_sha256 != CURRENT_OWNER_SHA256 or type(rows) is not list or len(rows) > 2
            or registry["projects"]["OFF"]["project_id"] != project
            or type(registry["organization_id"]) is not str
            or re.fullmatch("[a-f0-9]{32}", registry["organization_id"]) is None):
        _fail()
    owner, owners, safe, mia = _native_integer(registry["owner_id"]), [], [], 0
    for row in rows:
        if type(row) is not dict or not {"uid", "owner", "permission", "liveControl"} <= set(row):
            _fail()
        if row["uid"] is None:
            public_id = row.get("publicId")
            if (mia or row["owner"] is not False or row.get("name") != "Mia"
                    or row["permission"] != "write" or row["liveControl"] is not True
                    or type(public_id) is not str or re.fullmatch("A-[a-f0-9]{32}", public_id) is None
                    or _sha(public_id.encode("ascii")) != MIA_PUBLIC_ID_SHA256):
                _fail()
            mia = 1
            safe.append({"role": "owner_authorized_mia", "public_id_sha256": MIA_PUBLIC_ID_SHA256,
                "uid_is_null": True, "owner": False, "permission": "write", "liveControl": True})
        else:
            if (owners or _native_integer(row["uid"]) != owner or row["owner"] is not True
                    or row["permission"] not in ("read", "write") or type(row["liveControl"]) is not bool
                    or type(row.get("publicId")) is str and row["publicId"].startswith("A-")):
                _fail()
            owners.append(row)
            safe.append({"role": "owner", "uid": owner, "owner": True,
                "permission": row["permission"], "liveControl": row["liveControl"]})
    stats = {"collaborator_count": len(rows), "nonowner_collaborator_count": mia,
        "recognized_mia_count": mia, "unknown_other_count": 0, "owner_only": mia == 0,
        "collaborators_sha256": _sha(_wire(sorted(safe, key=lambda row: row["role"]))),
        "privacy_basis": MIA_PRIVACY_BASIS if mia else custody.PRIVACY_BASIS,
        "independent_agent_identity_attested": False}
    return stats, owners


def _native_requests(plan):
    """Fixed fresh preflight plus exactly the regenerated phase requests."""
    project = plan['project_id']
    return [_request('metadata', 'projects/read', {'projectId': project}),
        _request('collaborators', 'projects/collaboration/read', {'projectId': project}),
        _request('jobs', 'backtests/list', {'projectId': project})] + plan['requests']


def _native_projection(body, request, registry, plan):
    if type(body) is not dict or body.get('success') is not True or body.get('errors') not in (None, []):
        _fail()
    project, arm = plan['project_id'], plan['arm']
    if 'projectId' in body and projects._integer(body['projectId']) != project:
        _fail()
    identity, endpoint, payload = request['id'], request['endpoint'], request['payload']
    if identity in ('metadata', 'collaborators'):
        _component_context(body, registry, project)
        if identity == 'metadata':
            rows = body.get('projects')
            if type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict:
                _fail()
            _component_context(rows[0], registry, project)
            stats, owners = _component_collaborators(rows[0].get('collaborators'),
                registry, CURRENT_OWNER_SHA256, project, arm)
            core = custody._projection({**body, 'projects': [{**rows[0], 'collaborators': owners}]},
                {'project_id': project, 'phase': identity, 'arm': arm}, registry)
            core_hash = core.pop('normalized_metadata_sha256')
            return {**core, **stats, 'owner_core_metadata_sha256': core_hash,
                'normalized_metadata_sha256': _sha(_wire({'owner_core': core_hash, 'actual_collaborators': stats}))}
        if body.get('userPermissions') != 'write':
            _fail()
        stats, _ = _component_collaborators(body.get('collaborators'), registry,
            CURRENT_OWNER_SHA256, project, arm)
        return {'project_id': project, 'phase': identity, 'user_permissions': 'write', **stats}
    if identity == 'jobs':
        jobs = body.get('backtests')
        if (type(jobs) is not list or len(jobs) > 1000 or
                type(body.get('count')) is not int or projects._integer(body.get('count'), 0, 1000) != len(jobs)):
            _fail()
        ids = set()
        for row in jobs:
            if (type(row) is not dict or row.get('completed') is not True or
                    row.get('status') not in TERMINAL or type(row.get('backtestId')) is not str or
                    re.fullmatch('[a-f0-9]{32}', row['backtestId']) is None or row['backtestId'] in ids or
                    'projectId' in row and projects._integer(row['projectId']) != project):
                _fail()
            ids.add(row['backtestId'])
        return {'terminal_jobs_observed': len(jobs), 'nonterminal_jobs_observed': 0}
    if endpoint == 'files/read':
        inventory = _raw_inventory(_wire(body), project)
        digest = _sha(api._canonical(inventory))
        if digest != request['source_inventory_sha256']:
            _fail()
        return {'source_inventory': inventory, 'source_inventory_sha256': digest}
    if endpoint in ('files/create', 'files/update'):
        return {'generated_source_acknowledged': True}
    if endpoint in ('compile/create', 'compile/read'):
        api._identity(body.get('compileId'))
        state = body.get('state')
        if (type(state) is not str or re.fullmatch('[A-Za-z ]{1,40}', state) is None or
                endpoint == 'compile/read' and (body['compileId'] != payload['compileId'] or state != 'BuildSuccess')):
            _fail()
        return {'compile_id': body['compileId'], 'compile_state': state}
    if endpoint == 'backtests/create':
        job = body.get('backtest')
        if (type(job) is not dict or type(job.get('backtestId')) is not str or
                re.fullmatch('[a-f0-9]{32}', job['backtestId']) is None or
                'projectId' in job and projects._integer(job['projectId']) != project):
            _fail()
        return {'backtest_id': job['backtestId']}
    _fail()


def _guard(plan):
    api._guard(plan)
    if (Path(__file__) != api.LANE/MODULE or Path(cash_bundle.__file__) != api.LANE/CASH_BUNDLE_MODULE or
            Path(custody.__file__) != api.LANE/custody.MODULE):
        _fail()
    for root in (PRIVATE_ROOT, NATIVE_ROOT):
        if api.subprocess.run(['git', 'check-ignore', '-q', str(root)],
                cwd=api.LANE, capture_output=True, timeout=10).returncode:
            _fail()


def _reservation_names(action):
    plan = action['api_plan']
    candidate = _wire({'study_id': STUDY_ID, 'project_id': plan['project_id'],
        'financial_operation_id': action['financial_spec']['operation_id'],
        'candidate_config_sha256': plan['candidate_config_sha256'],
        'candidate_attempt': plan['candidate_attempt']})
    return ['attempt-'+_sha(plan['attempt_id'].encode('ascii'))+'.launch.spent.json',
        'look-'+_sha(plan['reserved_look_id'].encode('ascii'))+'.launch.spent.json',
        'candidate-'+_sha(candidate)+'.launch.spent.json']


def _dispatch(action, root, native_root, lock_root, *, public_sources, transport, guard, clock, monotonic, fixture):
    action = _validate(action, public_sources)
    plan = action['api_plan']
    if (not fixture and (root != PRIVATE_ROOT or native_root != NATIVE_ROOT or lock_root != api.PRIVATE_ROOT or
            transport is not projects._native_request or guard is not _guard or clock is not api._utcnow or
            monotonic is not time.monotonic or plan['mode'] != 'production') or
            fixture and (plan['mode'] != 'offline-fixture' or
                any(value in (PRIVATE_ROOT, NATIVE_ROOT, api.PRIVATE_ROOT) or value.is_relative_to(api.LANE)
                    for value in (root, native_root, lock_root)) or
                transport is projects._native_request)):
        _fail()
    registry = projects.validate_bindings(plan['project_bindings_json'].encode('ascii'),
        expected_sha256=plan['project_bindings_sha256'])
    frozen, started, previous = _wire(action), monotonic(), None

    def check(seconds=0):
        nonlocal previous
        guard(plan)
        now, tick = clock(), monotonic()
        if (type(now) is not datetime or now.utcoffset() != timedelta(0) or
                not api._clock(plan['created_utc']) <= now < api._clock(plan['expires_utc']) or
                type(tick) not in (int, float) or not 0 <= tick-started < 600 or
                previous is not None and (now < previous[0] or tick < previous[1]) or
                api._clock(plan['expires_utc'])-now < timedelta(seconds=seconds) or
                600-(tick-started) < seconds or _wire(action) != frozen):
            _fail()
        previous = now, tick

    check()
    if any(value.resolve() != value for value in (root, native_root, lock_root)):
        _fail()
    paths = (ops.PRIVATE_PARENT, PRIVATE_ROOT.parent, root, native_root, api.PRIVATE_ROOT.parent, lock_root) if not fixture else (root, native_root, lock_root)
    for path in paths:
        path.mkdir(mode=0o700, exist_ok=True)
        ops._custody(path.lstat(), True)
    operation, lock, stop, written = plan['operation_id'], None, None, 0
    result = {'schema': 'tpr-cmp1107-sid-cash-native-result-v1', 'phase': action['phase'],
        'study_id': STUDY_ID, 'source_epoch': SOURCE_EPOCH,
        'strategy_economics_changed': True, 'operation_id': operation, 'project_id': plan['project_id'],
        'arm': plan['arm'], 'project_registration_key': plan['project_registration_key'],
        'project_bindings_sha256': plan['project_bindings_sha256'],
        'candidate_config_sha256': plan['candidate_config_sha256'], 'candidate_attempt': plan['candidate_attempt'],
        'candidate_binding_sha256': plan['candidate_binding_sha256'],
        'action_sha256': _sha(frozen), 'plan_sha256': _sha(api._canonical(plan)),
        'git_head': plan['git_head'], 'latest_owner_instruction_sha256': CURRENT_OWNER_SHA256,
        'registry_creation_owner_instruction_sha256': plan['owner_instruction_sha256'],
        'attempt_id': plan['attempt_id'], 'reserved_look_id': plan['reserved_look_id'],
        'status': 'failed_or_uncertain', 'requests': [], 'transport_calls_attempted': 0,
        'compile_requests_attempted': 0, 'actual_new_backtests': 0, 'observed_new_backtest_ids': [],
        'new_observed_looks': 0, 'financial_outcome_looks_count': None,
        'private_reads_attempted': 0, 'private_bytes_read': 0, 'dependency_claims': [],
        'launch_reservations': [], 'action_claim_published': None,
        'response_bytes': 0, 'receipt_published': False, 'lock_cleanup_complete': False,
        'preflight_complete': False, 'automatic_retry': False, 'market_trading_authorized': False,
        'native_origin_authenticated': False, 'economics_accepted': False}

    def publish(directory, name, raw, final=False):
        nonlocal written
        reserve = 0 if final else 131072
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_INPUT_BYTES or written+len(raw) > MAX_OUTPUT_BYTES-reserve:
            _fail()
        descriptor = api._publish(directory, name, raw)
        written += len(raw)
        return descriptor

    try:
        publish(root, operation+'.action.spent.json', frozen)
        result['action_claim_published'] = True
    except FileExistsError:
        _fail()
    except BaseException as error:
        stop = error
    lock_path = lock_root/'comparison-api.lock'
    try:
        if stop is not None:
            raise stop
        lock = os.open(lock_path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
        ops._custody(os.fstat(lock))
        wire = _wire({'operation_id': operation, 'action_sha256': result['action_sha256']})
        if os.write(lock, wire) != len(wire):
            _fail()
        os.fsync(lock)
        directory = os.open(lock_root, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try: os.fsync(directory)
        finally: os.close(directory)
        publish(native_root, operation+'.operation.spent.json', api._canonical(plan))
        raws = {}
        for key in PROOF_KEYS if action['phase'] == 'launch' else ():
            check()
            descriptor = action['compile_evidence'][key]
            claim = publish(root, operation+'.'+key+'.read.spent.json', _wire({
                'action_sha256': result['action_sha256'], 'source_hashes': plan['source_hashes'],
                'git_head': plan['git_head'], 'input': descriptor, 'attempt_id': plan['attempt_id'],
                'reserved_look_id': plan['reserved_look_id'], 'created_utc': plan['created_utc'],
                'expires_utc': plan['expires_utc'], 'latest_owner_instruction_sha256': CURRENT_OWNER_SHA256}))
            result['dependency_claims'].append(claim)
            check(SECONDS)
            if result['private_reads_attempted'] >= action['private_reads_max']:
                _fail()
            result['private_reads_attempted'] += 1
            raw = _read_proof(native_root, descriptor)
            result['private_bytes_read'] += len(raw)
            if result['private_bytes_read'] > action['private_bytes_max']:
                _fail()
            _raw_descriptor(raw, descriptor)
            raws[key] = raw
            check()
        if action['phase'] == 'launch':
            _proof(action, raws)
            for name in _reservation_names(action):
                check()
                result['launch_reservations'].append(publish(native_root, name, _wire({
                    'action_sha256': result['action_sha256'], 'study_id': STUDY_ID,
                    'git_head': plan['git_head'], 'source_hashes': plan['source_hashes'],
                    'project_id': plan['project_id'], 'candidate_config_sha256': plan['candidate_config_sha256'],
                    'attempt_id': plan['attempt_id'], 'reserved_look_id': plan['reserved_look_id'],
                    'financial_spec': action['financial_spec']})))
        for request in _native_requests(plan):
            check()
            row = {'id': request['id'], 'endpoint': request['endpoint'], 'status': 'failed_or_unknown',
                'http_status': None, 'request_claim': None, 'raw_response': None, 'projection': None,
                'source_inventory': None, 'source_inventory_sha256': None, 'compile_id': None,
                'compile_state': None, 'backtest_id': None}
            result['requests'].append(row)
            row['request_claim'] = publish(native_root, operation+'.'+request['id']+'.request.spent.json', _wire({
                'action_sha256': result['action_sha256'], 'plan_sha256': result['plan_sha256'],
                'request': request, 'git_head': plan['git_head'], 'source_hashes': plan['source_hashes'],
                'created_utc': plan['created_utc'], 'expires_utc': plan['expires_utc'],
                'latest_owner_instruction_sha256': CURRENT_OWNER_SHA256,
                'registry_creation_owner_instruction_sha256': plan['owner_instruction_sha256'],
                'attempt_id': plan['attempt_id'], 'reserved_look_id': plan['reserved_look_id']}))
            check(request['seconds'])
            if result['transport_calls_attempted'] >= action['native_requests_max']:
                _fail()
            result['transport_calls_attempted'] += 1
            if request['id'] == 'compile':
                result['compile_requests_attempted'] += 1
            if request['id'] == 'launch':
                result['actual_new_backtests'] = None
            raw, status, credential, owner = transport(request['endpoint'], api._canonical(request['payload']),
                request['seconds'], request['max_response_bytes'], registry['owner_id'])
            # Retain safe returned job identity before a subsequent clock/source refusal.
            if (type(raw) is not bytes or not 0 < len(raw) <= request['max_response_bytes'] or
                    result['response_bytes']+len(raw) > action['native_response_bytes_max'] or
                    type(status) is not int or not 100 <= status <= 599 or
                    projects._integer(owner) != registry['owner_id'] or type(credential) is not str or
                    re.fullmatch(r'[!-~]{1,256}', credential) is None):
                _fail()
            evidence.project_wire(raw, credential=credential)
            result['response_bytes'] += len(raw)
            row['http_status'] = status
            row['raw_response'] = publish(native_root, operation+'.'+request['id']+'.response.raw', raw)
            if status != 200:
                _fail()
            row['projection'] = _native_projection(_parse(raw), request, registry, plan)
            row.update({key: value for key, value in row['projection'].items()
                if key in ('source_inventory', 'source_inventory_sha256', 'compile_id', 'compile_state', 'backtest_id')})
            if request['id'] == 'jobs':
                result['preflight_complete'] = True
            if request['id'] == 'launch':
                result['observed_new_backtest_ids'].append(row['backtest_id'])
                result['actual_new_backtests'] = result['new_observed_looks'] = 1
            row['status'] = 'succeeded'
            check()
        check()
        result['status'] = 'completed'
    except BaseException as error:
        stop = error
    finally:
        if lock is not None:
            try:
                current, owned = os.stat(lock_path, follow_symlinks=False), os.fstat(lock)
                if (current.st_dev, current.st_ino) != (owned.st_dev, owned.st_ino):
                    _fail()
                os.unlink(lock_path)
                os.close(lock)
                lock = None
                directory = os.open(lock_root, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                try: os.fsync(directory)
                finally: os.close(directory)
                result['lock_cleanup_complete'] = True
            except BaseException as error:
                stop = api._retain_stop(stop, error)
            finally:
                if lock is not None:
                    try: os.close(lock)
                    except BaseException as error: stop = api._retain_stop(stop, error)
        if stop is not None:
            result['status'] = 'cancelled' if isinstance(stop, KeyboardInterrupt) else 'failed_or_uncertain'
        result['receipt_published'] = True
        try:
            publish(root, operation+'.result.json', _wire(result), True)
            result['receipt'] = publish(native_root, operation+'.result.json', _wire(result), True)
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
    """Fixed real TLS, roots, clocks and source guards; no injectable adapters."""
    try:
        _spec(action['financial_spec'])
        sources = _load_sources(action)
        return _dispatch(action, PRIVATE_ROOT, NATIVE_ROOT, api.PRIVATE_ROOT,
            public_sources=sources, transport=projects._native_request, guard=_guard,
            clock=api._utcnow, monotonic=time.monotonic, fixture=False)
    except (ActionCancelled, ActionFatal):
        raise
    except Exception:
        _fail()


def _dispatch_fixture(action, root, native_root, *, public_sources, transport, clock,
        guard=lambda _: None, monotonic=lambda: 0.0):
    """Synthetic temporary roots only; no production transport or custody claim."""
    return _dispatch(action, root, native_root, root, public_sources=public_sources,
        transport=transport, guard=guard, clock=clock, monotonic=monotonic, fixture=True)
