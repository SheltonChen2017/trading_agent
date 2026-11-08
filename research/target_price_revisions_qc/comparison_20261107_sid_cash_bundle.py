"""Pure fixed-SID cash-variant renderer from the pinned financial predecessor.

Only supplied public bytes and the separately claimed project registry are
processed. The original construction remains intact; the new native mixin
changes execution economics by leaving one fixed SID's final allocation cash.
This render opens no input packet and mints no claim, reservation or authority.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re

from . import comparison_20261029_project_bundle as bundle
from . import comparison_20261103_preflight as preflight


PREFIX = 'research/target_price_revisions_qc/'
MODULE = PREFIX + 'comparison_20261107_sid_cash_bundle.py'
PREFLIGHT_MODULE = PREFIX + 'comparison_20261103_preflight.py'
RUNTIME_PATH = PREFIX + 'sid_cash_exclusion_20261107.py'
RUNTIME_SHA256 = '5fe401a620bfc455a1aa840bb3e8d1f970e084407fb0a5ea73fdd8b711a53c18'
PINS = {**preflight.SOURCE_PINS,
    PREFLIGHT_MODULE: 'e16d50cd8bb3fa0716b9e1994552f07b2dcf02554493c6bbf1b41661de847082',
    preflight.RECOVERY_PATH: preflight.RECOVERY_SHA256,
    RUNTIME_PATH: RUNTIME_SHA256}
REQUIRED_SOURCES = frozenset(PINS)
SOURCE_EPOCH = 'TPR-SIX-UNIVERSE-FIVE-ARM-SID-CASH-20261107-v1'
STUDY_ID = SOURCE_EPOCH
PARENT_STUDY_ID = preflight.STUDY_ID
PARENT_SOURCE_EPOCH = preflight.RECOVERY_EPOCH
EXCLUDED_SID_SHA256 = '1122fa5f1349f79e231e106127c098da27ef730836a97052d2154ecc46f1afc1'
OWNER_INSTRUCTION = 'can we bypass that specific stock?'
OWNER_SHA256 = hashlib.sha256(OWNER_INSTRUCTION.encode('utf-8')).hexdigest()
REGISTRY_CREATION_OWNER_SHA256 = 'ea2dd7037a0f33ab78771a2f6deb3016da34b164ab04f5b2c69f30c4ae31157f'
ARMS = tuple(bundle.ARM_KEYS)
CANDIDATES = {'cap_off': STUDY_ID + '-OFF',
    'cap_tilt_50': STUDY_ID + '-CAP-TILT-50',
    'cap_tilt_100': STUDY_ID + '-CAP-TILT-100',
    'cap_tilt_200': STUDY_ID + '-CAP-TILT-200',
    'pure_tpr': STUDY_ID + '-PURE-TPR'}
MAX_SOURCE_BYTES = 131072
MAX_TOTAL_SOURCE_BYTES = 2 * 1024 * 1024
MAX_CLOUD_FILE_BYTES = 60000


class CashBundleRefusal(ValueError):
    """Body-free refusal of fixed variant/source/registry framing."""


def _fail():
    raise CashBundleRefusal('fixed SID cash-variant source render refused') from None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _wire(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True, allow_nan=False).encode('ascii')


def _hash(value):
    if (type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None
            or set(value) == {'0'}):
        _fail()
    return value


def _sources(public_sources):
    if type(public_sources) is not dict or set(public_sources) != REQUIRED_SOURCES:
        _fail()
    total = 0
    for name, digest in PINS.items():
        raw = public_sources[name]
        if (type(raw) is not bytes or not 0 < len(raw) <= MAX_SOURCE_BYTES
                or _sha(raw) != _hash(digest)):
            _fail()
        total += len(raw)
    if total > MAX_TOTAL_SOURCE_BYTES:
        _fail()


def _packet():
    return {'key': bundle.PACKET_KEY, 'sha256': bundle.PACKET_SHA256,
        'bytes': bundle.PACKET_BYTES, 'encoding': 'utf-8-json',
        'source_inventory_sha256': bundle.INVENTORY_SHA256}


def _policy_metadata():
    """One frozen policy; deliberately no caller-selected SID or patch input."""
    return {'schema': 'tpr-fixed-sid-cash-execution-mask-v1',
        'excluded_sid_sha256': EXCLUDED_SID_SHA256,
        'identity': 'SHA256 of canonical native SecurityIdentifier ASCII; no ticker selection',
        'arms': list(ARMS), 'effective_first_session': '2021-01-04',
        'stage': 'construct original arm completely, then remove fixed SID execution targets',
        'cash_rule': 'sum of removed final exact sleeve weights remains cash',
        'remove_zero_weight_target_keys': True, 'redistribution': False,
        'rank11_refill': False, 'reranking': False, 'renormalization': False,
        'construction_selected_slots_preserved': True,
        'membership_subscription_action_custody_preserved': True,
        'unexpected_excluded_holding_order_or_fill': 'fail closed',
        'execution_mark_requirement': 'omit only fixed SID with zero holdings, ledger and orders',
        'other_held_mark_policy': 'unchanged',
        'strategy_economics_changed': True,
        'parent_study_id': PARENT_STUDY_ID,
        'parent_source_epoch': PARENT_SOURCE_EPOCH,
        'parent_policy_sha256': bundle.off.PINS['comparison_20261028_policy.json'],
        'source_calendar_sha256': bundle.off.PINS['extended_calendar.json'],
        'parent_input_study_id': PARENT_STUDY_ID,
        'parent_signal_packet_descriptor': _packet(),
        'latest_owner_instruction_sha256': OWNER_SHA256}


def _policy_source(raw):
    """Rebind one study literal and add one policy metadata key only."""
    result = bundle._assignment(raw, 'STUDY_ID', repr(PARENT_STUDY_ID), repr(STUDY_ID))
    tree = ast.parse(result)
    policies = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'policy']
    if len(policies) != 1:
        _fail()
    returns = [node for node in ast.walk(policies[0]) if isinstance(node, ast.Return)]
    if len(returns) != 1 or not isinstance(returns[0].value, ast.Dict):
        _fail()
    value = returns[0].value
    if any(isinstance(key, ast.Constant) and key.value == 'execution_mask_policy' for key in value.keys):
        _fail()
    # The existing AST expressions remain exact, including all construction
    # declarations. Only this explicit literal metadata entry is appended.
    value.keys.append(ast.Constant(value='execution_mask_policy'))
    value.values.append(ast.parse(repr(_policy_metadata()), mode='eval').body)
    return bundle.off._span_replace(result.decode('utf-8'), returns[0].value,
        ast.unparse(value)).encode('utf-8')


def _functions_except_policy(raw):
    return {ast.dump(node, include_attributes=False) for node in ast.walk(ast.parse(raw))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name != 'policy'}


def _checked_cloud(files):
    for name, raw in files.items():
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_CLOUD_FILE_BYTES:
            _fail()
        tree = ast.parse(raw, filename=name)
        if any(isinstance(node, ast.ImportFrom) and node.level for node in ast.walk(tree)):
            _fail()
        compile(tree, name, 'exec')


def build_cash_candidate(*, public_sources, project_bindings_raw,
        expected_project_bindings_sha256, arm, operation_id, attempt,
        prior_attempts_looks_sha256, latest_owner_instruction_sha256):
    """Return fixed flat financial source bytes/report without any I/O or effect.

    The attempt is proposed lineage metadata (1..3), never a reservation. All
    private/native work remains separately claimed and source-bound by actions.
    The immutable parent signal descriptor is supplied internally, never read.
    """
    try:
        if (type(arm) is not str or arm not in ARMS
                or type(attempt) is not int or not 1 <= attempt <= 3
                or type(operation_id) is not str or len(operation_id) > 160
                or latest_owner_instruction_sha256 != OWNER_SHA256):
            _fail()
        prefix = 'TPR-CMP28-OFF-SID-CASH-20261107-' if arm == 'cap_off' else 'TPR-CMP28-SID-CASH-20261107-'
        if re.fullmatch(re.escape(prefix) + '[A-Za-z0-9][A-Za-z0-9_.-]*', operation_id) is None:
            _fail()
        prior = _hash(prior_attempts_looks_sha256)
        registry_sha = _hash(expected_project_bindings_sha256)
        _sources(public_sources)
        if (type(project_bindings_raw) is not bytes or not 0 < len(project_bindings_raw) <= 65536
                or _sha(project_bindings_raw) != registry_sha):
            _fail()
        binding = bundle.projects.validate_bindings(project_bindings_raw, expected_sha256=registry_sha)
        if (binding['owner_instruction_sha256'] != REGISTRY_CREATION_OWNER_SHA256
                or {key: row['project_id'] for key, row in binding['projects'].items()}
                    != preflight.REGISTERED_PROJECTS):
            _fail()
        parent_files, parent_report_raw = bundle.build_project_candidate(
            public_sources={name: public_sources[name] for name in bundle.SOURCE_PATHS},
            project_binding_raw=project_bindings_raw, expected_project_binding_sha256=registry_sha,
            arm=arm, operation_id=operation_id, attempt=attempt,
            prior_attempts_looks_sha256=prior, signal_packet=None if arm == 'cap_off' else _packet())
        parent_report = json.loads(parent_report_raw)
        recovery_sources = {name: public_sources[name] for name in preflight.RECOVERY_REQUIRED_SOURCES}
        preflight._sources(recovery_sources, True)
        files, parent_config_sha, parent_template_sha = preflight._recovery_files(
            parent_files, parent_report, recovery_sources)
        original = dict(files)
        parent_config = preflight._config(files['comparison_20261028_config.py'])
        if parent_config['study_id'] != PARENT_STUDY_ID:
            _fail()
        source_hashes = {name: _sha(raw) for name, raw in sorted(public_sources.items())}
        closure = _sha(_wire({'schema': 'tpr-cmp1107-sid-cash-template-closure-v1',
            'source_epoch': SOURCE_EPOCH, 'cloud_layout': 'fixed-inline-main-v1',
            'parent_source_epoch': PARENT_SOURCE_EPOCH, 'source_hashes': source_hashes,
            'excluded_sid_sha256': EXCLUDED_SID_SHA256}))
        policy = json.loads(public_sources[PREFIX + 'comparison_20261028_policy.json'])
        policy.update(study_id=STUDY_ID, execution_mask_policy=_policy_metadata())
        policy_sha = _sha(_wire(policy) + b'\n')
        calendar = bundle.off._calendar(public_sources[PREFIX + 'extended_calendar.json'], policy_sha)
        calendar['study_id'] = STUDY_ID
        calendar_sha = _sha(_wire(calendar))
        config = dict(parent_config)
        config.update(study_id=STUDY_ID, candidate_id=CANDIDATES[arm],
            policy_sha256=policy_sha, calendar_sha256=calendar_sha,
            source_template_closure_sha256=closure)
        config_raw = _wire(config)
        config_sha = _sha(config_raw)
        files['comparison_20261028_config.py'] = ('CONFIG_JSON = ' + repr(config_raw.decode('ascii')) + '\n').encode('ascii')
        files['comparison_20261028.py'] = _policy_source(files['comparison_20261028.py'])
        driver = 'comparison_20261028_algorithm.py' if arm == 'cap_off' else 'comparison_20261028_multi_algorithm.py'
        files[driver] = bundle._assignment(files[driver], 'EXPECTED_CONFIG_SHA256',
            repr(parent_config_sha), repr(config_sha))
        algo_module = driver[:-3]
        algo_class = 'ComparisonOffAlgorithm' if arm == 'cap_off' else 'ComparisonMultiAlgorithm'
        suffix = ('\nimport ' + algo_module + ' as candidate\n\n'
            'class Main(CashExclusionMixin, ResourceRecoveryMixin, candidate.' + algo_class + '):\n    pass\n').encode('ascii')
        files['main.py'] = public_sources[preflight.RECOVERY_PATH] + b'\n' + public_sources[RUNTIME_PATH] + suffix
        changed = {name for name in files if files[name] != original[name]}
        if changed != {'main.py', driver, 'comparison_20261028.py', 'comparison_20261028_config.py'}:
            _fail()
        # Every parent economic/helper body is preserved. The policy metadata
        # function is the sole permitted existing function change; Main adds
        # real economic behavior, so overall body/parity claims remain false.
        for name in original:
            if name == 'main.py':
                continue
            if name == 'comparison_20261028.py':
                if _functions_except_policy(files[name]) != _functions_except_policy(original[name]):
                    _fail()
            elif bundle._functions(files[name]) != bundle._functions(original[name]):
                _fail()
        if arm != 'cap_off':
            if config['signal_packet'] != _packet() or any(files[name] != original[name] for name in (
                    'comparison_20261028_events.py', 'comparison_20261028_signal_native.py', 'raw_revision.py')):
                _fail()
        _checked_cloud(files)
        hashes = {name: _sha(raw) for name, raw in sorted(files.items())}
        report = {**parent_report,
            'schema': 'tpr-cmp1107-sid-cash-project-bundle-v1', 'study_id': STUDY_ID,
            'candidate_id': config['candidate_id'], 'source_epoch': SOURCE_EPOCH,
            'parent_study_id': PARENT_STUDY_ID, 'parent_source_epoch': PARENT_SOURCE_EPOCH,
            'parent_input_study_id': PARENT_STUDY_ID, 'cloud_layout': 'fixed-inline-main-v1',
            'baseline_report_sha256': _sha(parent_report_raw),
            'parent_config_sha256': parent_config_sha,
            'parent_source_template_closure_sha256': parent_template_sha,
            'parent_policy_sha256': parent_config['policy_sha256'],
            'parent_calendar_sha256': parent_config['calendar_sha256'],
            'source_calendar_sha256': bundle.off.PINS['extended_calendar.json'],
            'actual_calendar_rows_unchanged': True,
            'config_sha256': config_sha, 'policy_sha256': policy_sha,
            'calendar_sha256': calendar_sha, 'source_template_closure_sha256': closure,
            'template_source_hashes': source_hashes, 'cloud_source_hashes': hashes,
            'cloud_source_bytes': {name: len(raw) for name, raw in sorted(files.items())},
            'rendered_source_closure_sha256': _sha(_wire(hashes)), 'file_count': len(files),
            'main_class': 'Main(CashExclusionMixin, ResourceRecoveryMixin, candidate.' + algo_class + ')',
            'changed_sid_cash_files': sorted(changed), 'execution_mask_policy': _policy_metadata(),
            'excluded_sid_sha256': EXCLUDED_SID_SHA256,
            'registry_creation_owner_instruction_sha256': binding['owner_instruction_sha256'],
            'latest_owner_instruction_sha256': OWNER_SHA256,
            'strategy_economics_changed': True, 'financial_function_bodies_unchanged': False,
            'base_constructor_function_bodies_unchanged': True, 'mark_policy_changed': False,
            'parent_signal_packet_descriptor': _packet(),
            'parent_signal_packet_descriptor_unchanged': True, 'signal_packet_body_opened': False,
            'original_frozen_study_resolved': False, 'historical_attempts_looks_pooled': False,
            'attempt_metadata_semantics': 'PROPOSED_METADATA_ONLY',
            'new_resource_adapter_native_verification_pending': True,
            'native_origin_authenticated': False, 'native_economic_parity_verified': False,
            'economics_accepted': False, 'native_accounting_accepted': False,
            'financial_metrics': None, 'accepted_performance': None,
            'native_permission': False, 'source_inputs_admitted': False,
            'source_rights_admitted': False, 'point_in_time_data': False,
            'canonical_admission': False, 'strategy_accepted': False,
            'trading_authority': False, 'backtesting_ready': False,
            'source_head_committed_independently_verified': False,
            'qc_requests': 0, 'qc_compiles': 0, 'backtests_launched': 0,
            'new_attempts': 0, 'new_observed_looks': 0, 'reservation_sha256': None}
        return files, _wire(report) + b'\n'
    except CashBundleRefusal:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, SyntaxError,
            OverflowError, RecursionError):
        _fail()
