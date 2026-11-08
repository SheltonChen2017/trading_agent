"""Public-byte renderer checks only; synthetic registry and no native effects."""
import ast
from copy import deepcopy
import hashlib
import inspect
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

from research.target_price_revisions_qc import cap_tilt
from research.target_price_revisions_qc import comparison_20261107_sid_cash_bundle as p


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def deny_effects(monkeypatch):
    def denied(*_args, **_kwargs):
        raise AssertionError('native/private/provider effect forbidden')
    monkeypatch.setattr(p.bundle.projects.ops, 'credential', denied)
    monkeypatch.setattr(p.bundle.projects.ops, 'read_private', denied)
    monkeypatch.setattr(p.bundle.projects.http.client, 'HTTPSConnection', denied)
    monkeypatch.setattr(p.bundle.projects.subprocess, 'run', denied)


@pytest.fixture
def sources():
    return {name: (ROOT / name).read_bytes() for name in p.REQUIRED_SOURCES}


def registry():
    owner, organization = 123, 'a' * 32
    return {'schema': 'tpr-cmp28-five-project-bindings-v1', 'round_id': p.bundle.ROUND,
        'owner_instruction_sha256': p.REGISTRY_CREATION_OWNER_SHA256, 'git_head': 'a' * 40,
        'adapter_source_sha256': p.bundle.PROJECTS_SHA256,
        'organization_id': organization, 'owner_id': owner,
        'baseline_receipt_sha256': 'b' * 64,
        'privacy_basis': 'documented_private_default_and_observed_collaborators',
        'explicit_privacy_flag_observed': False, 'independent_native_origin_attested': False,
        'projects': {key: {'project_id': project, 'name': p.bundle.NAMES[key],
            'organization_id': organization, 'owner_id': owner, 'language': 'Py',
            'create_receipt_sha256': p._sha((key + '-create').encode()),
            'read_receipt_sha256': p._sha((key + '-read').encode()),
            'collaboration_receipt_sha256': p._sha((key + '-collaboration').encode()),
            'collaborator_count': 1, 'nonowner_collaborator_count': 0,
            'collaborators_sha256': 'c' * 64}
            for key, project in p.preflight.REGISTERED_PROJECTS.items()}}


def arguments(sources, arm='cap_off', binding=None):
    raw = p._wire(registry() if binding is None else binding)
    operation = ('TPR-CMP28-OFF-' if arm == 'cap_off' else 'TPR-CMP28-') + 'SID-CASH-20261107-SYNTHETIC-' + str(arm)
    return {'public_sources': sources, 'project_bindings_raw': raw,
        'expected_project_bindings_sha256': p._sha(raw), 'arm': arm,
        'operation_id': operation, 'attempt': 1, 'prior_attempts_looks_sha256': 'd' * 64,
        'latest_owner_instruction_sha256': p.OWNER_SHA256}


def build(sources, arm='cap_off', binding=None, **changes):
    kwargs = arguments(sources, arm, binding)
    kwargs.update(changes)
    return p.build_cash_candidate(**kwargs)


def parent(sources, arm):
    kwargs = arguments(sources, arm)
    files, raw = p.bundle.build_project_candidate(
        public_sources={name: sources[name] for name in p.bundle.SOURCE_PATHS},
        project_binding_raw=kwargs['project_bindings_raw'],
        expected_project_binding_sha256=kwargs['expected_project_bindings_sha256'],
        arm=arm, operation_id=kwargs['operation_id'], attempt=kwargs['attempt'],
        prior_attempts_looks_sha256=kwargs['prior_attempts_looks_sha256'],
        signal_packet=None if arm == 'cap_off' else p._packet())
    rendered, config_sha, closure = p.preflight._recovery_files(files, json.loads(raw),
        {name: sources[name] for name in p.preflight.RECOVERY_REQUIRED_SOURCES})
    return rendered, json.loads(raw), config_sha, closure


def comparison(raw, monkeypatch):
    module = ModuleType('comparison_20261028')
    monkeypatch.setitem(sys.modules, 'cap_tilt', cap_tilt)
    exec(compile(raw, 'comparison_20261028.py', 'exec'), module.__dict__)
    return module


def assignment(raw, name):
    nodes = [node for node in ast.parse(raw).body if isinstance(node, ast.Assign)
        and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == name]
    assert len(nodes) == 1
    return nodes[0].value


@pytest.mark.parametrize('arm', p.ARMS)
def test_all_arms_deterministic_new_identity_and_honest_economic_lineage(sources, arm):
    before = deepcopy(sources)
    files, raw = build(sources, arm)
    again, repeat = build(sources, arm)
    assert files == again and raw == repeat and sources == before
    report = json.loads(raw)
    config = p.preflight._config(files['comparison_20261028_config.py'])
    old, baseline, old_config_sha, old_closure = parent(sources, arm)
    assert report['schema'] == 'tpr-cmp1107-sid-cash-project-bundle-v1'
    assert report['study_id'] == config['study_id'] == p.STUDY_ID
    assert report['candidate_id'] == config['candidate_id'] == p.CANDIDATES[arm]
    assert p.PARENT_STUDY_ID not in config['candidate_id']
    assert report['source_epoch'] == p.SOURCE_EPOCH
    assert report['project_id'] == config['project_id'] == p.preflight.REGISTERED_PROJECTS[p.bundle.ARM_KEYS[arm]]
    assert report['project_name'] == baseline['project_name']
    assert report['parent_config_sha256'] == old_config_sha != report['config_sha256']
    assert report['parent_source_template_closure_sha256'] == old_closure != report['source_template_closure_sha256']
    assert report['parent_policy_sha256'] == baseline['policy_sha256'] != report['policy_sha256']
    assert report['parent_calendar_sha256'] == baseline['calendar_sha256'] != report['calendar_sha256']
    assert report['config_sha256'] == p._sha(p._wire(config))
    assert report['cloud_source_hashes'] == {name: p._sha(value) for name, value in files.items()}
    assert report['cloud_source_bytes'] == {name: len(value) for name, value in files.items()}
    assert report['rendered_source_closure_sha256'] == p._sha(p._wire(report['cloud_source_hashes']))
    assert report['template_source_hashes'] == {name: p._sha(value) for name, value in sources.items()}
    assert config['source_template_closure_sha256'] == report['source_template_closure_sha256']
    assert report['latest_owner_instruction_sha256'] == p._sha(b'can we bypass that specific stock?')
    assert report['registry_creation_owner_instruction_sha256'] == p.REGISTRY_CREATION_OWNER_SHA256
    assert report['strategy_economics_changed'] is True
    assert report['financial_function_bodies_unchanged'] is False
    assert report['base_constructor_function_bodies_unchanged'] is True
    assert report['mark_policy_changed'] is False
    assert report['parent_input_study_id'] == report['parent_study_id'] == p.PARENT_STUDY_ID
    assert report['file_count'] == len(files) == len(old) == (11 if arm == 'cap_off' else 15)
    for key in ('native_permission', 'independent_native_origin_attested',
            'project_metadata_native_origin_attested', 'native_origin_authenticated',
            'native_economic_parity_verified', 'economics_accepted', 'native_accounting_accepted',
            'source_inputs_admitted', 'source_rights_admitted', 'point_in_time_data',
            'canonical_admission', 'strategy_accepted', 'original_frozen_study_resolved',
            'historical_attempts_looks_pooled', 'signal_packet_body_opened',
            'trading_authority', 'backtesting_ready', 'prior_attempts_reset'):
        assert report[key] is False
    for key in ('accepted_performance', 'financial_metrics', 'reservation_sha256'):
        assert report[key] is None
    for key in ('qc_requests', 'qc_compiles', 'backtests_launched', 'new_attempts', 'new_observed_looks'):
        assert report[key] == 0


@pytest.mark.parametrize('arm', p.ARMS)
def test_only_policy_metadata_existing_function_changes_and_parent_packet_is_exact(sources, monkeypatch, arm):
    files, raw = build(sources, arm)
    report = json.loads(raw)
    old, _, _, _ = parent(sources, arm)
    allowed = {'comparison_20261028.py', 'comparison_20261028_config.py', 'main.py',
        'comparison_20261028_algorithm.py' if arm == 'cap_off' else 'comparison_20261028_multi_algorithm.py'}
    assert {name for name in files if files[name] != old[name]} == allowed
    assert report['changed_sid_cash_files'] == sorted(allowed)
    for name, value in files.items():
        if name == 'main.py':
            continue
        if name == 'comparison_20261028.py':
            assert p._functions_except_policy(value) == p._functions_except_policy(old[name])
        else:
            assert p.bundle._functions(value) == p.bundle._functions(old[name])
    module = comparison(files['comparison_20261028.py'], monkeypatch)
    old_policy = json.loads(sources[p.PREFIX + 'comparison_20261028_policy.json'])
    expected = deepcopy(old_policy)
    expected.update(study_id=p.STUDY_ID, execution_mask_policy=p._policy_metadata())
    assert module.policy() == expected
    assert p._sha(module.policy_bytes()) == report['policy_sha256']
    assert expected['construction'] == old_policy['construction']
    assert expected['unchanged_execution_contract'] == old_policy['unchanged_execution_contract']
    assert expected['valuation_verification_contract'] == old_policy['valuation_verification_contract']
    assert module.STUDY_ID == p.STUDY_ID
    # OFF and Multi derive journal/summary/order identity from this one module;
    # their financial method bodies and identity expressions are untouched.
    study_expr = ast.parse('comparison.STUDY_ID', mode='eval').body
    assert ast.dump(assignment(files['comparison_20261028_algorithm.py'], 'STUDY')) == ast.dump(study_expr)
    assert ast.dump(assignment(files['comparison_20261028_algorithm.py'], 'CANDIDATE')) == ast.dump(
        ast.parse('STUDY + "-OFF"', mode='eval').body)
    if arm != 'cap_off':
        multi = ast.parse(files['comparison_20261028_multi_algorithm.py'])
        identity = [node for node in multi.body if isinstance(node, ast.Assign)
            and len(node.targets) == 1 and isinstance(node.targets[0], ast.Tuple)
            and [item.id for item in node.targets[0].elts] == ['STUDY', 'SLEEVES', 'NY', 'UTC']]
        assert len(identity) == 1 and ast.dump(identity[0].value.elts[0]) == ast.dump(study_expr)
        assert ast.dump(assignment(files['comparison_20261028_multi_algorithm.py'], 'CANDIDATES')) == ast.dump(
            assignment(old['comparison_20261028_multi_algorithm.py'], 'CANDIDATES'))
        config = p.preflight._config(files['comparison_20261028_config.py'])
        assert config['signal_packet'] == report['parent_signal_packet_descriptor'] == p._packet()
        assert report['signal_packet_descriptor_sha256'] == p._sha(p._wire(p._packet()))
        assert report['parent_signal_packet_descriptor_unchanged'] is True
        for name in ('comparison_20261028_events.py', 'comparison_20261028_signal_native.py', 'raw_revision.py'):
            assert files[name] == old[name]
        assert p.PARENT_STUDY_ID.encode() in files['comparison_20261028_events.py']
        assert p.STUDY_ID.encode() not in files['comparison_20261028_events.py']


@pytest.mark.parametrize('arm', p.ARMS)
def test_actual_calendar_dates_cutoffs_and_source_calendar_are_unchanged(sources, arm):
    files, raw = build(sources, arm)
    report = json.loads(raw)
    config = p.preflight._config(files['comparison_20261028_config.py'])
    source = sources[p.PREFIX + 'extended_calendar.json']
    original = json.loads(source)
    expected = p.bundle.off._calendar(source, report['policy_sha256'])
    expected['study_id'] = p.STUDY_ID
    assert p._sha(p._wire(expected)) == config['calendar_sha256'] == report['calendar_sha256']
    assert report['actual_calendar_rows_unchanged'] is True
    assert report['source_calendar_sha256'] == p._sha(source) == expected['source_calendar_sha256']
    for key in ('valuation_sessions', 'warmup_sessions', 'decisions'):
        assert expected[key] == original[key]
    assert len(expected['decisions']) == expected['decision_count'] == 301
    assert len(expected['valuation_sessions']) == expected['valuation_count'] == 1449
    assert (expected['start'], expected['end'], expected['warmup_start']) == ('2021-01-04', '2026-10-09', '2020-09-01')
    literal = ast.literal_eval(assignment(files['extended_loader.py'], 'CALENDAR_JSON'))
    assert literal.encode() == source


@pytest.mark.parametrize('arm', p.ARMS)
def test_fixed_readable_inline_main_exact_runtime_bytes_mro_and_60000_bounds(sources, arm):
    files, raw = build(sources, arm)
    report = json.loads(raw)
    module = 'comparison_20261028_algorithm' if arm == 'cap_off' else 'comparison_20261028_multi_algorithm'
    cls = 'ComparisonOffAlgorithm' if arm == 'cap_off' else 'ComparisonMultiAlgorithm'
    suffix = ('\nimport ' + module + ' as candidate\n\nclass Main(CashExclusionMixin, ResourceRecoveryMixin, candidate.' + cls + '):\n    pass\n').encode('ascii')
    assert files['main.py'] == sources[p.preflight.RECOVERY_PATH] + b'\n' + sources[p.RUNTIME_PATH] + suffix
    assert p._sha(sources[p.RUNTIME_PATH]) == p.RUNTIME_SHA256
    tree = ast.parse(files['main.py'])
    main = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Main']
    assert len(main) == 1
    assert [ast.unparse(base) for base in main[0].bases] == ['CashExclusionMixin', 'ResourceRecoveryMixin', 'candidate.' + cls]
    assert report['main_class'] == 'Main(CashExclusionMixin, ResourceRecoveryMixin, candidate.' + cls + ')'
    for name, value in files.items():
        assert 0 < len(value) <= 60000
        parsed = ast.parse(value, filename=name)
        compile(parsed, name, 'exec')
        imports = {node.module for node in ast.walk(parsed) if isinstance(node, ast.ImportFrom)}
        imports |= {item.name for node in ast.walk(parsed) if isinstance(node, ast.Import) for item in node.names}
        assert not imports & {'gzip', 'zlib', 'codecs', 'extended_compressed_store'}
        calls = {node.func.id for node in ast.walk(parsed) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        assert not calls & {'eval', 'exec', '__import__'}


@pytest.mark.parametrize('path', sorted(p.REQUIRED_SOURCES))
def test_every_pinned_public_source_rejects_one_byte_drift(sources, path):
    sources[path] += b'\n'
    with pytest.raises(p.CashBundleRefusal):
        build(sources)


@pytest.mark.parametrize('fault', ('missing', 'extra', 'str_instead_of_bytes'))
def test_closed_source_set_cannot_accept_arbitrary_upload_fragments(sources, fault):
    if fault == 'missing':
        sources.pop(p.RUNTIME_PATH)
    elif fault == 'extra':
        sources['main.py'] = b'raise RuntimeError("arbitrary")\n'
    else:
        sources[p.RUNTIME_PATH] = 'source text'
    with pytest.raises(p.CashBundleRefusal):
        build(sources)


@pytest.mark.parametrize('changes', (
    {'latest_owner_instruction_sha256': 'f' * 64},
    {'expected_project_bindings_sha256': 'e' * 64},
    {'expected_project_bindings_sha256': '0' * 64},
    {'project_bindings_raw': b'{}'}, {'project_bindings_raw': '{}'},
    {'arm': 'OTHER'}, {'arm': True}, {'attempt': 0}, {'attempt': 4}, {'attempt': True},
    {'prior_attempts_looks_sha256': '0' * 64}, {'prior_attempts_looks_sha256': 'bad'},
    {'operation_id': 'TPR-CMP28-OFF-OLD-001'},
    {'operation_id': 'TPR-CMP28-SID-CASH-20261107-001'}, {'operation_id': 'foreign'}))
def test_wrong_binding_owner_lineage_arm_and_attempt_refuse(sources, changes):
    with pytest.raises(p.CashBundleRefusal):
        build(sources, **changes)


@pytest.mark.parametrize('fault', ('wrong_creation_owner', 'foreign_project', 'nonowner', 'missing_arm'))
def test_creation_authority_and_all_five_registered_projects_remain_required(sources, fault):
    value = registry()
    if fault == 'wrong_creation_owner':
        value['owner_instruction_sha256'] = p.OWNER_SHA256
    elif fault == 'foreign_project':
        value['projects']['TPR100']['project_id'] = 41000001
    elif fault == 'nonowner':
        value['projects']['PURE']['nonowner_collaborator_count'] = 1
    else:
        value['projects'].pop('OFF')
    with pytest.raises(p.CashBundleRefusal):
        build(sources, binding=value)


def test_public_api_has_no_selector_descriptor_patch_or_upload_byte_override(sources):
    assert tuple(inspect.signature(p.build_cash_candidate).parameters) == (
        'public_sources', 'project_bindings_raw', 'expected_project_bindings_sha256',
        'arm', 'operation_id', 'attempt', 'prior_attempts_looks_sha256',
        'latest_owner_instruction_sha256')
    for key in ('excluded_sid_sha256', 'excluded_sid', 'signal_packet', 'main_source', 'files', 'override'):
        with pytest.raises(TypeError):
            build(sources, **{key: 'caller-choice'})
    tree = ast.parse((ROOT / p.MODULE).read_bytes())
    calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not calls & {'open', 'exec', 'eval', '__import__'}
    attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not attrs & {'read_bytes', 'read_text', 'write_bytes', 'write_text', 'credential', 'read_private', 'HTTPSConnection'}


def test_new_attempt_retains_parent_history_and_changes_only_candidate_lineage(sources):
    a_files, a_raw = build(sources)
    b_files, b_raw = build(sources, attempt=2, operation_id='TPR-CMP28-OFF-SID-CASH-20261107-SYNTHETIC-002')
    a, b = json.loads(a_raw), json.loads(b_raw)
    for key in ('source_epoch', 'study_id', 'candidate_id', 'policy_sha256', 'calendar_sha256',
            'source_template_closure_sha256', 'prior_attempts_looks_sha256'):
        assert a[key] == b[key]
    assert a['config_sha256'] != b['config_sha256']
    assert a['rendered_source_closure_sha256'] != b['rendered_source_closure_sha256']
    assert a_files['main.py'] == b_files['main.py']
    assert a['prior_attempts_reset'] is b['prior_attempts_reset'] is False
    assert a['new_attempts'] == b['new_attempts'] == a['new_observed_looks'] == b['new_observed_looks'] == 0
