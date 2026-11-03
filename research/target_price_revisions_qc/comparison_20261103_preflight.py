"""Pure five-arm source preparation while QuantConnect access is deferred.

Supplied public bytes and a separately claimed registry are regenerated using
the preserved frozen builders. No file, environment, credential, provider or
native service is opened here. Returned source is locally syntax-checked;
neither this manifest nor its fixture seam is an execution authority.

The recovery candidate has a separate pinned source epoch. It cannot be sent
through the old frozen-financial action route, and local checks cannot prove
native resource capacity, input/identity repair or complete financial results.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re

from . import comparison_20261029_project_bundle as bundle


MODULE = 'research/target_price_revisions_qc/comparison_20261103_preflight.py'
PREFIX = 'research/target_price_revisions_qc/'
HELPER_PINS = {
    PREFIX + 'comparison_20261028_bundle.py':
        '76637ed47522b6f4eb0a8e19d0962afce5e08cd249d28348dc1204547ee71b6a',
    PREFIX + 'comparison_20261029_project_bundle.py':
        'a5534dbebc994f3e6ffe301a721f210d9110384216e539f2c2d42c69e8fcb300',
}
SOURCE_PINS = {**bundle.PINS, **HELPER_PINS}
REQUIRED_SOURCES = frozenset(SOURCE_PINS)
RECOVERY_PATH = PREFIX + 'subscription_recovery_20261103.py'
# Separate candidate bytes; changing them requires a newly reviewed source epoch.
RECOVERY_SHA256 = '14083a5213f24e929c21308f507ad28e18fdd92dbfdd6c3d29581749631e253a'
RECOVERY_REQUIRED_SOURCES = REQUIRED_SOURCES | frozenset((RECOVERY_PATH,))
REGISTRY_BYTES = 3573
REGISTRY_SHA256 = '154e8ff056eb776f070fd73922b724367e634b1b37d4052b70a464601d0c94f1'
REGISTERED_PROJECTS = {
    'OFF': 38609822, 'TPR050': 38609834, 'TPR100': 38609836,
    'TPR200LONG': 38609837, 'PURE': 38609840,
}
ARMS = tuple(bundle.ARM_KEYS)
STUDY_ID = 'TPR-SIX-UNIVERSE-FIVE-ARM-20261028-v1'
FROZEN_EPOCH = 'TPR-CMP28-R107-FROZEN-20261029A'
RECOVERY_EPOCH = 'TPR-CMP28-FINAL-SUBSCRIPTION-INLINE-CANDIDATE-20261103-v1'
MAX_SOURCE_BYTES = 131072
MAX_SOURCES_BYTES = 2 * 1024 * 1024
REQUEST_KEYS = frozenset(('operation_id', 'attempt', 'prior_attempts_looks_sha256'))
BLOCKERS = (
    'owner_deferred_all_qc_access_20261103',
    'native_subscription_resource_recovery_and_full_window_capacity_unverified',
    'exact_native_raw_mark_identity_input_recovery_unverified',
    'owner_mia_changed_source_epoch_not_admitted',
    'source_rights_pit_native_sid_and_complete_input_admission_unproved',
    'native_orders_fills_fees_cash_actions_nav_exposure_clock_accounting_unverified',
)


class PreflightRefusal(ValueError):
    """Body-free source, binding or lineage refusal."""


def _fail():
    raise PreflightRefusal('offline five-arm source preparation refused') from None


def _wire(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True, allow_nan=False).encode('ascii')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _hash(value, length=64):
    if (type(value) is not str or re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is None
            or set(value) == {'0'}):
        _fail()
    return value


def _closed(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        _fail()


def _sources(public_sources, recovery):
    expected = RECOVERY_REQUIRED_SOURCES if recovery else REQUIRED_SOURCES
    _closed(public_sources, expected)
    total = 0
    for name, raw in public_sources.items():
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_SOURCE_BYTES:
            _fail()
        total += len(raw)
        digest = RECOVERY_SHA256 if name == RECOVERY_PATH else SOURCE_PINS[name]
        if digest is None or _sha(raw) != _hash(digest):
            _fail()
    if total > MAX_SOURCES_BYTES:
        _fail()


def _requests(requests):
    _closed(requests, ARMS)
    operations = set()
    for arm in ARMS:
        row = requests[arm]
        _closed(row, REQUEST_KEYS)
        operation = row['operation_id']
        pattern = r'TPR-CMP28-OFF-[A-Za-z0-9][A-Za-z0-9_.-]*' if arm == 'cap_off' else r'TPR-CMP28-[A-Za-z0-9][A-Za-z0-9_.-]*'
        if (type(operation) is not str or len(operation) > 160
                or re.fullmatch(pattern, operation) is None or operation in operations
                or type(row['attempt']) is not int or not 1 <= row['attempt'] <= 2**31 - 1):
            _fail()
        _hash(row['prior_attempts_looks_sha256'])
        operations.add(operation)
    return json.loads(_wire(requests))


def _packet():
    return {'key': bundle.PACKET_KEY, 'sha256': bundle.PACKET_SHA256,
        'bytes': bundle.PACKET_BYTES, 'encoding': 'utf-8-json',
        'source_inventory_sha256': bundle.INVENTORY_SHA256}


def _config(raw):
    tree = ast.parse(raw)
    if (len(tree.body) != 1 or not isinstance(tree.body[0], ast.Assign)
            or len(tree.body[0].targets) != 1
            or not isinstance(tree.body[0].targets[0], ast.Name)
            or tree.body[0].targets[0].id != 'CONFIG_JSON'):
        _fail()
    return json.loads(ast.literal_eval(tree.body[0].value))


def _recovery_files(files, baseline, public_sources):
    """Only a pinned mixin, explicit MRO and source/config literals may change."""
    original = dict(files)
    result = dict(files)
    source_hashes = {name: _sha(raw) for name, raw in sorted(public_sources.items())}
    closure = _sha(_wire({'schema': 'tpr-cmp28-final-subscription-template-closure-v1',
        'source_epoch': RECOVERY_EPOCH, 'cloud_layout': 'fixed-inline-main-v1',
        'recovery_helper_sha256': RECOVERY_SHA256, 'source_hashes': source_hashes}))
    config = _config(result['comparison_20261028_config.py'])
    previous_config = dict(config)
    config['source_template_closure_sha256'] = closure
    config_raw = _wire(config)
    config_sha = _sha(config_raw)
    result['comparison_20261028_config.py'] = ('CONFIG_JSON = ' +
        repr(config_raw.decode('ascii')) + '\n').encode('ascii')
    driver = 'comparison_20261028_algorithm.py' if baseline['arm'] == 'cap_off' else 'comparison_20261028_multi_algorithm.py'
    result[driver] = bundle._assignment(result[driver], 'EXPECTED_CONFIG_SHA256',
        repr(baseline['config_sha256']), repr(config_sha))
    algo_module = 'comparison_20261028_algorithm' if baseline['arm'] == 'cap_off' else 'comparison_20261028_multi_algorithm'
    algo_class = 'ComparisonOffAlgorithm' if baseline['arm'] == 'cap_off' else 'ComparisonMultiAlgorithm'
    suffix = ('\nimport ' + algo_module + ' as candidate\n\n'
        'class Main(ResourceRecoveryMixin, candidate.' + algo_class + '):\n    pass\n').encode('ascii')
    # Exact pinned bytes precede a fixed MRO suffix. No caller source fragment
    # or generic patch surface can extend Main, and old API names stay fixed.
    result['main.py'] = public_sources[RECOVERY_PATH] + suffix
    if (not result['main.py'].startswith(public_sources[RECOVERY_PATH])
            or result['main.py'][len(public_sources[RECOVERY_PATH]):] != suffix):
        _fail()
    if {key: value for key, value in config.items() if key != 'source_template_closure_sha256'} != {
            key: value for key, value in previous_config.items() if key != 'source_template_closure_sha256'}:
        _fail()
    for name, raw in original.items():
        if name == 'main.py':
            continue  # The complete allowed extension was checked byte-for-byte.
        if bundle._functions(result[name]) != bundle._functions(raw):
            _fail()
        if name not in {'main.py', driver, 'comparison_20261028_config.py'} and result[name] != raw:
            _fail()
    return result, config_sha, closure


def _prepare(*, public_sources, project_bindings_raw, registry_sha256, requests,
        git_head, owner_instruction_sha256, recovery, fixture):
    try:
        _hash(git_head, 40)
        _hash(owner_instruction_sha256)
        _hash(registry_sha256)
        _sources(public_sources, recovery)
        lineage = _requests(requests)
        if not fixture and (registry_sha256 != REGISTRY_SHA256
                or type(project_bindings_raw) is not bytes or len(project_bindings_raw) != REGISTRY_BYTES):
            _fail()
        binding = bundle.projects.validate_bindings(project_bindings_raw, expected_sha256=registry_sha256)
        if {key: row['project_id'] for key, row in binding['projects'].items()} != REGISTERED_PROJECTS:
            _fail()
        source_hashes = {name: _sha(raw) for name, raw in sorted(public_sources.items())}
        bundles, arms = {}, {}
        for arm in ARMS:
            request = lineage[arm]
            files, baseline_raw = bundle.build_project_candidate(
                public_sources={path: public_sources[path] for path in bundle.SOURCE_PATHS},
                project_binding_raw=project_bindings_raw,
                expected_project_binding_sha256=registry_sha256, arm=arm,
                operation_id=request['operation_id'], attempt=request['attempt'],
                prior_attempts_looks_sha256=request['prior_attempts_looks_sha256'],
                signal_packet=None if arm == 'cap_off' else _packet())
            baseline = json.loads(baseline_raw)
            config_sha, template_sha = baseline['config_sha256'], baseline['source_template_closure_sha256']
            if recovery:
                files, config_sha, template_sha = _recovery_files(files, baseline, public_sources)
            for name, raw in files.items():
                if (re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*\.py', name) is None
                        or type(raw) is not bytes or not 0 < len(raw) <= 60000):
                    _fail()
                compile(ast.parse(raw, filename=name), name, 'exec')
            inventory = {name: {'bytes': len(raw), 'sha256': _sha(raw)}
                for name, raw in sorted(files.items())}
            arms[arm] = {
                'project_id': baseline['project_id'], 'project_name': baseline['project_name'],
                'candidate_id': baseline['candidate_id'], 'lineage_metadata': request,
                'attempt_metadata_semantics': 'PROPOSED_METADATA_ONLY',
                'requires_fresh_native_operation_attempt_assignment': True,
                'config_sha256': config_sha, 'baseline_config_sha256': baseline['config_sha256'],
                'policy_sha256': baseline['policy_sha256'], 'calendar_sha256': baseline['calendar_sha256'],
                'source_template_closure_sha256': template_sha,
                'baseline_report_sha256': _sha(baseline_raw), 'source_inventory': inventory,
                'source_inventory_sha256': _sha(_wire(inventory)),
                'financial_function_bodies_unchanged': True,
                'native_economic_parity_verified': False,
                'native_compilation': 'NOT_RUN', 'backtest': 'NOT_RUN',
                'financial_metrics': None, 'native_accounting_accepted': False,
            }
            bundles[arm] = files
        if (len({row['calendar_sha256'] for row in arms.values()}) != 1
                or len({row['policy_sha256'] for row in arms.values()}) != 1):
            _fail()
        identity = {'source_epoch': RECOVERY_EPOCH if recovery else FROZEN_EPOCH,
            'git_head': git_head, 'registry_sha256': registry_sha256,
            'owner_instruction_sha256': owner_instruction_sha256,
            'source_hashes': source_hashes, 'requests': lineage}
        manifest = {
            'schema': 'tpr-five-arm-offline-preparation-v1',
            'preparation_id': 'TPR-OFFLINE-20261103-' + _sha(_wire(identity))[:24],
            'mode': 'offline-fixture' if fixture else 'offline-preparation',
            **identity, 'study_id': STUDY_ID,
            'registry_bytes': len(project_bindings_raw),
            'registry_creation_owner_instruction_sha256': binding['owner_instruction_sha256'],
            'registry_creation_git_head': binding['git_head'],
            'arm_order': list(ARMS), 'arms': arms,
            'dates': {'warmup': '2020-09-01', 'first_valuation': '2021-01-04',
                'last_valuation': '2026-10-09', 'valuations': 1449, 'weekly_decisions': 301},
            'input_packet': {'descriptor': _packet(), 'body_opened': False,
                'native_availability_authenticated': False},
            'usb_data_use': 'INDEPENDENT_DIAGNOSTIC_ONLY_NOT_FROZEN_FINANCIAL_INPUT',
            'recovery_mixin_included': recovery,
            'cloud_layout': 'fixed-inline-main-v1' if recovery else 'frozen-flat-files-v1',
            'recovery_helper_sha256': RECOVERY_SHA256 if recovery else None,
            'existing_financial_action_source_epoch_compatible': not recovery,
            'candidate_native_activation_approved': False,
            'local_syntax_units_checked': sum(len(files) for files in bundles.values()),
            'qc_access_deferred_by_owner': True, 'qc_requests': 0,
            'qc_compiles': 0, 'backtests_launched': 0,
            'new_attempts': 0, 'new_observed_financial_looks': 0,
            'attempt_metadata_semantics': 'PROPOSED_METADATA_ONLY',
            'requires_fresh_native_operation_attempt_assignment': True,
            'generated_configs_are_preview_only': True,
            'historical_attempts_looks_reset': False, 'automatic_retry': False,
            'software_preparation_complete': True,
            'source_head_committed_independently_verified': False,
            'backtesting_ready': False, 'native_origin_authenticated': False,
            'source_inputs_admitted': False, 'point_in_time_data': False,
            'source_rights_admitted': False, 'canonical_admission': False,
            'trading_authority': False, 'accepted_performance': None,
            'blocking_reasons': list(BLOCKERS),
            'continuation': [
                'Wait for owner release of QC; this preparation executes nothing.',
                'Independently verify recovery source epoch, resource capacity and exact native RAW/SID inputs.',
                'Use fresh committed HEAD/source/access/operation/attempt/look claims before every later effect.',
                'Regenerate through an action route that explicitly accepts the reviewed source epoch; no override.',
                'After prerequisites, compile and launch OFF then remaining frozen arms serially.',
                'Accept only independent full native order/fill/fee/cash/action/NAV/exposure/clock coverage accounting.',
            ],
        }
        return bundles, _wire(manifest) + b'\n'
    except PreflightRefusal:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, SyntaxError, RecursionError):
        _fail()


def prepare_offline(*, public_sources, project_bindings_raw, requests, git_head,
        owner_instruction_sha256):
    """Regenerate the five frozen baselines against the exact retained registry."""
    return _prepare(public_sources=public_sources, project_bindings_raw=project_bindings_raw,
        registry_sha256=REGISTRY_SHA256, requests=requests, git_head=git_head,
        owner_instruction_sha256=owner_instruction_sha256, recovery=False, fixture=False)


def prepare_recovery_candidate(*, public_sources, project_bindings_raw, requests,
        git_head, owner_instruction_sha256):
    """Prepare the distinct pinned final-subscription candidate, never activate it."""
    return _prepare(public_sources=public_sources, project_bindings_raw=project_bindings_raw,
        registry_sha256=REGISTRY_SHA256, requests=requests, git_head=git_head,
        owner_instruction_sha256=owner_instruction_sha256, recovery=True, fixture=False)


def _prepare_fixture(*, public_sources, project_bindings_raw, expected_registry_sha256,
        requests, git_head, owner_instruction_sha256, recovery=False):
    """Synthetic framing seam; its output is permanently labelled offline-fixture."""
    if type(recovery) is not bool:
        _fail()
    return _prepare(public_sources=public_sources, project_bindings_raw=project_bindings_raw,
        registry_sha256=expected_registry_sha256, requests=requests, git_head=git_head,
        owner_instruction_sha256=owner_instruction_sha256, recovery=recovery, fixture=True)
