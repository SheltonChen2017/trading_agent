"""Pinned public sources and synthetic registry only; no native/private I/O."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

from research.target_price_revisions_qc import comparison_20261103_preflight as p


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def deny_effects(monkeypatch):
    def deny(*_, **__):
        raise AssertionError('native/private/account effects forbidden')
    monkeypatch.setattr(p.bundle.projects.ops, 'credential', deny)
    monkeypatch.setattr(p.bundle.projects.http.client, 'HTTPSConnection', deny)
    monkeypatch.setattr(p.bundle.projects.subprocess, 'run', deny)
    monkeypatch.setattr(p.bundle.projects.ops, 'read_private', deny)


@pytest.fixture
def sources():
    return {name: (ROOT / name).read_bytes() for name in p.REQUIRED_SOURCES}


def registry():
    owner, organization = 123, 'a' * 32
    return {
        'schema': 'tpr-cmp28-five-project-bindings-v1', 'round_id': p.bundle.ROUND,
        'owner_instruction_sha256': 'b' * 64, 'git_head': 'a' * 40,
        'adapter_source_sha256': p.bundle.PROJECTS_SHA256,
        'organization_id': organization, 'owner_id': owner,
        'baseline_receipt_sha256': 'c' * 64,
        'privacy_basis': 'documented_private_default_and_observed_collaborators',
        'explicit_privacy_flag_observed': False,
        'independent_native_origin_attested': False,
        'projects': {key: {
            'project_id': project, 'name': p.bundle.NAMES[key],
            'organization_id': organization, 'owner_id': owner, 'language': 'Py',
            'create_receipt_sha256': p._sha((key + '-create').encode()),
            'read_receipt_sha256': p._sha((key + '-read').encode()),
            'collaboration_receipt_sha256': p._sha((key + '-collaborators').encode()),
            'collaborator_count': 1, 'nonowner_collaborator_count': 0,
            'collaborators_sha256': 'd' * 64,
        } for key, project in p.REGISTERED_PROJECTS.items()},
    }


def requests():
    return {arm: {
        'operation_id': 'TPR-CMP28-' + ('OFF-' if arm == 'cap_off' else '') + 'LOCAL-' + arm,
        'attempt': 5, 'prior_attempts_looks_sha256': p._sha(('prior-' + arm).encode()),
    } for arm in p.ARMS}


def args(sources, binding=None):
    raw = p._wire(registry() if binding is None else binding)
    return {'public_sources': sources, 'project_bindings_raw': raw,
        'expected_registry_sha256': p._sha(raw), 'requests': requests(),
        'git_head': 'a' * 40, 'owner_instruction_sha256': 'e' * 64}


def prepare(sources, **changes):
    parameters = args(sources)
    parameters.update(changes)
    return p._prepare_fixture(**parameters)


def test_all_five_frozen_bundles_are_deterministic_bound_and_compiled(sources):
    original = deepcopy(sources)
    a, raw = prepare(sources)
    b, again = prepare(sources)
    assert a == b and raw == again and sources == original
    report = json.loads(raw)
    assert report['mode'] == 'offline-fixture'
    assert report['source_epoch'] == p.FROZEN_EPOCH
    assert report['study_id'] == p.STUDY_ID
    assert report['arm_order'] == list(p.ARMS)
    assert report['dates'] == {'warmup': '2020-09-01', 'first_valuation': '2021-01-04',
        'last_valuation': '2026-10-09', 'valuations': 1449, 'weekly_decisions': 301}
    assert report['local_syntax_units_checked'] == 71
    assert report['source_hashes'] == {name: p._sha(value) for name, value in sources.items()}
    assert report['registry_creation_owner_instruction_sha256'] == 'b' * 64
    assert report['owner_instruction_sha256'] == 'e' * 64
    for arm, files in a.items():
        row = report['arms'][arm]
        assert row['project_id'] == p.REGISTERED_PROJECTS[p.bundle.ARM_KEYS[arm]]
        assert row['lineage_metadata'] == requests()[arm]
        assert row['attempt_metadata_semantics'] == 'PROPOSED_METADATA_ONLY'
        assert row['requires_fresh_native_operation_attempt_assignment'] is True
        assert row['source_inventory'] == {name: {'bytes': len(value), 'sha256': p._sha(value)}
            for name, value in files.items()}
        assert row['source_inventory_sha256'] == p._sha(p._wire(row['source_inventory']))
        config = p._config(files['comparison_20261028_config.py'])
        assert config['project_id'] == row['project_id'] and config['arm'] == arm
        assert row['config_sha256'] == p._sha(p._wire(config))
        assert row['config_sha256'] == row['baseline_config_sha256']
        assert row['financial_function_bodies_unchanged'] is True
        assert row['financial_metrics'] is None
        assert row['native_economic_parity_verified'] is False
        assert row['native_accounting_accepted'] is False
        assert row['native_compilation'] == row['backtest'] == 'NOT_RUN'
        for name, value in files.items():
            compile(ast.parse(value, filename=name), name, 'exec')
            assert len(value) <= 60000
    assert len({r['calendar_sha256'] for r in report['arms'].values()}) == 1
    assert len({r['policy_sha256'] for r in report['arms'].values()}) == 1
    assert report['input_packet']['descriptor']['bytes'] == 280105389
    assert report['input_packet']['body_opened'] is False


def test_preparation_never_mints_a_native_run_or_input_admission(sources):
    _, raw = prepare(sources)
    report = json.loads(raw)
    for key in ('backtesting_ready', 'native_origin_authenticated', 'source_inputs_admitted',
            'point_in_time_data', 'source_rights_admitted', 'canonical_admission',
            'trading_authority', 'historical_attempts_looks_reset', 'automatic_retry',
            'candidate_native_activation_approved', 'source_head_committed_independently_verified'):
        assert report[key] is False
    for key in ('qc_requests', 'qc_compiles', 'backtests_launched', 'new_attempts',
            'new_observed_financial_looks'):
        assert report[key] == 0
    assert report['qc_access_deferred_by_owner'] is True
    assert report['software_preparation_complete'] is True
    assert report['attempt_metadata_semantics'] == 'PROPOSED_METADATA_ONLY'
    assert report['requires_fresh_native_operation_attempt_assignment'] is True
    assert report['generated_configs_are_preview_only'] is True
    assert report['accepted_performance'] is None
    assert report['blocking_reasons'] == list(p.BLOCKERS)
    assert 'owner_deferred_all_qc_access_20261103' in report['blocking_reasons']


@pytest.mark.parametrize('name', sorted(p.REQUIRED_SOURCES))
def test_every_supplied_public_template_or_builder_rejects_drift(sources, name):
    sources[name] += b'\n'
    with pytest.raises(p.PreflightRefusal, match='offline five-arm source preparation refused'):
        prepare(sources)


@pytest.mark.parametrize('fault', ('missing', 'extra', 'wrong_type'))
def test_source_closure_cannot_add_arbitrary_mia_files(sources, fault):
    if fault == 'missing':
        sources.pop(next(iter(sources)))
    elif fault == 'extra':
        sources['mia.py'] = b'raise RuntimeError("no")\n'
    else:
        sources[next(iter(sources))] = 'text rather than bytes'
    with pytest.raises(p.PreflightRefusal):
        prepare(sources)


@pytest.mark.parametrize('fault', ('missing_arm', 'extra_arm', 'duplicate_operation',
    'attempt_zero', 'attempt_bool', 'bad_prior', 'extra_flag', 'off_prefix'))
def test_lineage_is_complete_closed_and_not_reset_or_implicitly_reserved(sources, fault):
    value = requests()
    if fault == 'missing_arm':
        value.pop('pure_tpr')
    elif fault == 'extra_arm':
        value['other'] = deepcopy(value['pure_tpr'])
    elif fault == 'duplicate_operation':
        value['pure_tpr']['operation_id'] = value['cap_tilt_100']['operation_id']
    elif fault == 'attempt_zero':
        value['cap_off']['attempt'] = 0
    elif fault == 'attempt_bool':
        value['cap_off']['attempt'] = True
    elif fault == 'bad_prior':
        value['cap_off']['prior_attempts_looks_sha256'] = '0' * 64
    elif fault == 'extra_flag':
        value['pure_tpr']['native_ready'] = True
    else:
        value['cap_off']['operation_id'] = 'TPR-CMP28-FOREIGN'
    with pytest.raises(p.PreflightRefusal):
        prepare(sources, requests=value)


@pytest.mark.parametrize('fault', ('swapped', 'foreign', 'legacy', 'wrong_sha', 'origin_claim'))
def test_registered_project_mapping_and_registry_framing_cannot_drift(sources, fault):
    value = registry()
    if fault == 'swapped':
        value['projects']['OFF']['project_id'], value['projects']['TPR100']['project_id'] = (
            value['projects']['TPR100']['project_id'], value['projects']['OFF']['project_id'])
    elif fault == 'foreign':
        value['projects']['TPR100']['project_id'] = 41000001
    elif fault == 'legacy':
        value['projects']['OFF']['project_id'] = 37650980
    elif fault == 'origin_claim':
        value['independent_native_origin_attested'] = True
    raw = p._wire(value)
    with pytest.raises(p.PreflightRefusal):
        prepare(sources, project_bindings_raw=raw,
            expected_registry_sha256='f' * 64 if fault == 'wrong_sha' else p._sha(raw))


def test_fixture_registry_cannot_enter_production_preparation(sources):
    value = args(sources)
    value.pop('expected_registry_sha256')
    for function in (p.prepare_offline, p.prepare_recovery_candidate):
        with pytest.raises(p.PreflightRefusal):
            function(**value)


def test_returned_mappings_cannot_mutate_inputs_or_later_preparations(sources):
    params = args(sources)
    before = deepcopy(params)
    files, raw = p._prepare_fixture(**params)
    files['cap_off']['main.py'] = b'changed'
    _, second = p._prepare_fixture(**params)
    assert params == before and raw == second


def test_module_has_no_effect_dispatch_or_file_credential_openers():
    # This invariant is specifically the source/import boundary of this pure
    # entry point. The runtime tests above also forbid existing adapter effects.
    tree = ast.parse((ROOT / p.MODULE).read_bytes())
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imports == {'__future__', None}
    assert not any(isinstance(node, ast.Name) and node.id in {
        'open', 'exec', 'eval', '__import__', 'Path', 'socket', 'http', 'subprocess', 'os'
    } for node in ast.walk(tree))
    assert not any(isinstance(node, ast.FunctionDef) and node.name.startswith(('execute', 'upload', 'launch'))
        for node in tree.body)


def recovery_sources(sources):
    return {**sources, p.RECOVERY_PATH: (ROOT / p.RECOVERY_PATH).read_bytes()}


def test_recovery_is_a_separate_pinned_epoch_with_only_bound_source_metadata_changes(sources):
    baseline, baseline_raw = prepare(sources)
    candidate, raw = prepare(recovery_sources(sources), recovery=True)
    repeated, repeated_raw = prepare(recovery_sources(sources), recovery=True)
    report, old = json.loads(raw), json.loads(baseline_raw)
    assert candidate == repeated and raw == repeated_raw
    assert report['source_epoch'] == p.RECOVERY_EPOCH != old['source_epoch']
    assert report['preparation_id'] != old['preparation_id']
    assert report['recovery_mixin_included'] is True
    assert report['existing_financial_action_source_epoch_compatible'] is False
    assert report['candidate_native_activation_approved'] is False
    assert report['backtesting_ready'] is False
    assert report['local_syntax_units_checked'] == 71
    assert report['cloud_layout'] == 'fixed-inline-main-v1'
    for arm in p.ARMS:
        files, previous = candidate[arm], baseline[arm]
        driver = 'comparison_20261028_algorithm.py' if arm == 'cap_off' else 'comparison_20261028_multi_algorithm.py'
        assert set(files) == set(previous)
        changed = {name for name in previous if files[name] != previous[name]}
        assert changed == {'main.py', driver, 'comparison_20261028_config.py'}
        for name in previous:
            if name != 'main.py':
                assert p.bundle._functions(files[name]) == p.bundle._functions(previous[name])
        new_config = p._config(files['comparison_20261028_config.py'])
        old_config = p._config(previous['comparison_20261028_config.py'])
        assert {key: value for key, value in new_config.items() if key != 'source_template_closure_sha256'} == {
            key: value for key, value in old_config.items() if key != 'source_template_closure_sha256'}
        row = report['arms'][arm]
        assert row['config_sha256'] != row['baseline_config_sha256'] == old['arms'][arm]['config_sha256']
        assert row['policy_sha256'] == old['arms'][arm]['policy_sha256']
        assert row['calendar_sha256'] == old['arms'][arm]['calendar_sha256']
        helper = recovery_sources(sources)[p.RECOVERY_PATH]
        assert files['main.py'].startswith(helper)
        module = 'comparison_20261028_algorithm' if arm == 'cap_off' else 'comparison_20261028_multi_algorithm'
        class_name = 'ComparisonOffAlgorithm' if arm == 'cap_off' else 'ComparisonMultiAlgorithm'
        suffix = ('\nimport ' + module + ' as candidate\n\n'
            'class Main(ResourceRecoveryMixin, candidate.' + class_name + '):\n    pass\n').encode()
        assert files['main.py'] == helper + suffix
        assert p._sha(helper) == p.RECOVERY_SHA256
        assert b'4096' in files['extended_algorithm_successor.py']
        for name, value in files.items():
            compile(ast.parse(value, filename=name), name, 'exec')
            assert not any(isinstance(node, ast.ImportFrom) and node.level for node in ast.walk(ast.parse(value)))


@pytest.mark.parametrize('fault', ('absent', 'changed', 'unknown_pin', 'extra_mia'))
def test_recovery_cannot_activate_unpinned_code_or_fall_back_to_old_epoch(sources, monkeypatch, fault):
    value = recovery_sources(sources)
    if fault == 'absent':
        value.pop(p.RECOVERY_PATH)
    elif fault == 'changed':
        value[p.RECOVERY_PATH] += b'\n'
    elif fault == 'unknown_pin':
        monkeypatch.setattr(p, 'RECOVERY_SHA256', None)
    else:
        value['mia.py'] = b'candidate = True\n'
    with pytest.raises(p.PreflightRefusal):
        prepare(value, recovery=True)


@pytest.mark.parametrize('arm', p.ARMS)
def test_candidate_main_dispatches_parent_before_retaining_unknown_resource_state(sources, monkeypatch, arm):
    from research.target_price_revisions_qc import subscription_recovery_20261103 as recovery
    files, _ = prepare(recovery_sources(sources), recovery=True)
    module_name = 'comparison_20261028_algorithm' if arm == 'cap_off' else 'comparison_20261028_multi_algorithm'
    class_name = 'ComparisonOffAlgorithm' if arm == 'cap_off' else 'ComparisonMultiAlgorithm'
    calls = []
    class Parent:
        def __init__(self):
            self._manual_symbols = {'retained-id'}
        def on_data(self, data):
            calls.append(('parent', data))
            return 'parent-result'
    fake = ModuleType(module_name)
    setattr(fake, class_name, Parent)
    monkeypatch.setitem(sys.modules, module_name, fake)
    monkeypatch.setitem(sys.modules, 'subscription_recovery_20261103', recovery)
    namespace = {}
    exec(compile(files[arm]['main.py'], 'main.py', 'exec'), namespace)
    namespace['_native_types'] = lambda: (_ for _ in ()).throw(ValueError('unknown typed context'))
    algorithm = namespace['Main']()
    assert algorithm.on_data('synthetic-slice') == 'parent-result'
    assert calls == [('parent', 'synthetic-slice')]
    assert algorithm._manual_symbols == {'retained-id'}
    def parent_failure(self, data):
        raise RuntimeError('synthetic parent accounting failure')
    monkeypatch.setattr(Parent, 'on_data', parent_failure)
    with pytest.raises(RuntimeError, match='synthetic parent accounting failure'):
        algorithm.on_data('later-synthetic-slice')
