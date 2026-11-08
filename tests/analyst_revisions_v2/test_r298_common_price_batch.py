"""Real supplied public code vectors, synthetic project binding; no DATA/QC."""
import ast
import builtins
import copy
import dataclasses
import json
from pathlib import Path

import pytest

from scripts import arv2_r298_common_price_batch as m

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')


@pytest.fixture(scope='module')
def supplied():
    folder = ROOT / 'research/analyst_revisions_v2_qc'
    public = {name: (folder / name).read_bytes() for name in m.PUBLIC_SOURCE_PINS}
    addons = tuple((name, (folder / name).read_bytes()) for name in m.common.ADDON_NAMES)
    context = {'schema': m.vendor.fmt.SCHEMA + '-QC-context', 'runtime_project_id': 123,
        'manifest_pin': dict(m.AR_MANIFEST_PIN), 'catalog_pin': dict(m.AR_CATALOG_PIN),
        'object_key_prefix': '123/arv2/r326-common/' + m.AR_MANIFEST_PIN['sha256'] + '/',
        'AP_fact_sha256': m.vendor.fmt.AP_FACT_SHA256,
        'AP_authentication_sha256': m.vendor.fmt.AP_AUTH_SHA256}
    return {'public_sources': public, 'addon_source_pairs': addons,
        'quote_patcher_source_bytes': (ROOT / 'scripts/arv2_newrule_quote_execution_projection.py').read_bytes(),
        'common_patcher_source_bytes': (ROOT / 'scripts/arv2_r298_common_price_projection.py').read_bytes(),
        'runtime_project_id': 123, 'native_source_context': m.native.source_context(),
        'vendor_source_context': context}


def prepare(supplied, **changes):
    arguments = dict(supplied); arguments.update(changes)
    return m.prepare(**arguments)


@pytest.fixture(scope='module')
def batch(supplied):
    return prepare(supplied)


def refused(code, operation):
    with pytest.raises(m.Refused) as caught: operation()
    assert m.finite(caught.value) == code


def test_genuine_17_public_sources_and_seven_addons_make_exactly_the_ordered_six_cells(batch, supplied):
    record = batch.to_record()
    assert record['cell_order'] == [[6, 0], [6, 100], [6, 200], [8, 0], [8, 100], [8, 200]]
    assert tuple((cell['universe_count'], cell['ar_percent']) for cell in record['cells']) == m.CELL_ORDER
    assert len(batch.specs) == record['cell_count'] == 6
    assert all(cell['source_file_count'] == 18 for cell in record['cells'])
    assert all(record[key] is False for key in m.FALSE_FLAGS)
    assert record['AR_manifest_pin'] == m.AR_MANIFEST_PIN and record['AR_catalog_pin'] == m.AR_CATALOG_PIN
    assert record['native_source_context_sha256'] == m.native.SOURCE_CONTEXT_SHA256
    assert record['vendor_source_context_sha256'] == m.digest(supplied['vendor_source_context'])
    assert record['all18_sources_equal_except_Main'] is True and record['same_source_policy_all_six_cells'] is True
    assert len(record['shared_non_main_source_files']) == 17
    assert len({cell['main_pin']['sha256'] for cell in record['cells']}) == 6
    assert len({cell['common_profile_sha256'] for cell in record['cells']}) == 6


def test_frozen_quote_base_genuine_profile_geometry_economics_and_each_source_manifest_are_bound(batch):
    for (size, arm), spec, cell in zip(m.CELL_ORDER, batch.specs, batch.to_record()['cells'], strict=True):
        profile = m.common.runtime.validate_profile(json.loads(spec.profile_bytes))
        assert profile['universe_count'] == size and profile['ar_percent'] == arm
        strategy = profile['strategy_profile']
        assert strategy['gross_target'] == '0.98' and strategy['aggregate_stock_target_cap'] == '0.098'
        assert strategy['fee_bps'] == '10' and strategy['execution_policy'] == m.common.frozen.POLICY
        assert len(strategy['decision_sessions']) == 302 and len(strategy['evaluation_sessions']) == 1451
        assert strategy['decision_sessions'][-1] == '2026-10-12' and strategy['evaluation_sessions'][-1] == '2026-10-13'
        assert m.sha(dict(spec.source_pairs)[m.common.BASE_NAME]) == m.common.runtime.FROZEN_BASE_SHA256
        assert cell['projection_pin'] == m.pin(spec.record_bytes) and cell['projection_sha256'] == spec.projection_sha256
        assert cell['profile_pin'] == m.pin(spec.profile_bytes)
        manifest = {'schema': m.SCHEMA + '-source-manifest', 'runtime_project_id': 123,
            'profile_sha256': profile['profile_sha256'], 'source_files': spec.to_record()['source_files']}
        assert cell['source_manifest_pin'] == m.pin(m.canonical(manifest))


def test_main_AST_varies_only_common_profile_across_six_cells_no_execution_or_callback_change(batch, supplied):
    baseline = None
    for spec in batch.specs:
        tree = ast.parse(dict(spec.source_pairs)['main.py'])
        constants = {node.targets[0].id: node for node in tree.body if isinstance(node, ast.Assign)
            and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in ('COMMON_PRICE_PROFILE', 'NATIVE_SOURCE_CONTEXT', 'VENDOR_SOURCE_CONTEXT')}
        assert set(constants) == {'COMMON_PRICE_PROFILE', 'NATIVE_SOURCE_CONTEXT', 'VENDOR_SOURCE_CONTEXT'}
        assert ast.literal_eval(constants['VENDOR_SOURCE_CONTEXT'].value) == supplied['vendor_source_context']
        assert ast.literal_eval(constants['NATIVE_SOURCE_CONTEXT'].value) == supplied['native_source_context']
        constants['COMMON_PRICE_PROFILE'].value = ast.Constant('normalized-profile-only')
        normalized = ast.dump(tree, include_attributes=False)
        if baseline is None: baseline = normalized
        assert normalized == baseline


@pytest.mark.parametrize('mutation', ['public_bad', 'public_missing', 'public_extra', 'addon_bad',
    'addon_missing', 'addon_reverse', 'addon_type', 'quote_patcher', 'common_patcher'])
def test_source_pins_are_literal_not_refreshed_or_ignored(supplied, mutation):
    arguments = copy.deepcopy(supplied)
    if mutation == 'public_bad':
        name = next(iter(arguments['public_sources'])); arguments['public_sources'][name] += b'\n'
    elif mutation == 'public_missing': arguments['public_sources'].pop(next(iter(arguments['public_sources'])))
    elif mutation == 'public_extra': arguments['public_sources']['unexpected.py'] = b'pass\n'
    elif mutation == 'addon_bad':
        arguments['addon_source_pairs'] = tuple((name, raw + b'\n' if index == 6 else raw)
            for index, (name, raw) in enumerate(arguments['addon_source_pairs']))
    elif mutation == 'addon_missing': arguments['addon_source_pairs'] = arguments['addon_source_pairs'][:-1]
    elif mutation == 'addon_reverse': arguments['addon_source_pairs'] = tuple(reversed(arguments['addon_source_pairs']))
    elif mutation == 'addon_type': arguments['addon_source_pairs'] = list(arguments['addon_source_pairs'])
    elif mutation == 'quote_patcher': arguments['quote_patcher_source_bytes'] += b'\n'
    else: arguments['common_patcher_source_bytes'] += b'\n'
    with pytest.raises(m.Refused): m.prepare(**arguments)


@pytest.mark.parametrize('mutation', ['manifest', 'catalog', 'grant', 'project', 'APfact', 'native'])
def test_other_sidecars_grants_native_context_or_mismatched_project_cannot_enter_batch(supplied, mutation):
    arguments = copy.deepcopy(supplied); context = arguments['vendor_source_context']
    if mutation == 'manifest':
        context['manifest_pin']['sha256'] = 'a' * 64
        context['object_key_prefix'] = '123/arv2/r326-common/' + 'a' * 64 + '/'
    elif mutation == 'catalog': context['catalog_pin']['sha256'] = 'a' * 64
    elif mutation == 'grant': context['QC_processing_rights_granted'] = True
    elif mutation == 'project': arguments['runtime_project_id'] = 124
    elif mutation == 'APfact': context['AP_fact_sha256'] = 'a' * 64
    else: arguments['native_source_context']['source_book_sha256'] = 'a' * 64
    with pytest.raises(m.Refused): m.prepare(**arguments)


@pytest.mark.parametrize('value', [True, False, 0, -1, None, '123'])
def test_future_project_must_be_explicit_positive_int_not_an_authorization_switch(supplied, value):
    refused('project', lambda: prepare(supplied, runtime_project_id=value))


@pytest.mark.parametrize('mutation', ['missing', 'reordered', 'duplicate', 'list'])
def test_all_six_family_geometry_is_checked_on_every_metadata_export(batch, mutation):
    specs = batch.specs
    if mutation == 'missing': specs = specs[:-1]
    elif mutation == 'reordered': specs = specs[::-1]
    elif mutation == 'duplicate': specs = (specs[0],) * 6
    else: specs = list(specs)
    changed = dataclasses.replace(batch, specs=specs)
    with pytest.raises(m.Refused): changed.to_record()


def test_wrong_cell_returned_by_dependency_is_not_silently_relabelled(supplied, batch, monkeypatch):
    monkeypatch.setattr(m.common, 'public_specification', lambda *args, **kwargs: batch.specs[0])
    refused('geometry', lambda: prepare(supplied))


def test_metadata_never_relabels_valid_cells_from_another_arm_or_universe(batch):
    refused('geometry', lambda: m._metadata(batch.specs[::-1]))


def test_batch_is_immutable_closed_fresh_metadata_and_rejects_changed_record_pin(batch):
    first = batch.to_record(); first['QC_transfer_granted'] = True
    first['cells'][0]['source_files'][0]['byte_count'] = 0
    assert batch.to_record()['QC_transfer_granted'] is False
    assert batch.to_record()['cells'][0]['source_files'][0]['byte_count'] > 0
    with pytest.raises(dataclasses.FrozenInstanceError): batch.specs = ()
    changed = dataclasses.replace(batch, record_bytes=batch.record_bytes + b'\n')
    refused('batch', changed.to_record)


def test_only_public_pure_source_functions_called_no_files_old_control_or_admission(supplied, monkeypatch):
    def denied(*args, **kwargs): pytest.fail('pure batch crossed I/O or old operational boundary')
    with monkeypatch.context() as patch:
        patch.setattr(builtins, 'open', denied); patch.setattr(Path, 'read_bytes', denied)
        patch.setattr(m.plain, 'build_plain_comparison', denied)
        patch.setattr(m.plain, '_input_authority', denied)
        patch.setattr(m.common.frozen.admission, 'admit', denied)
        result = prepare(supplied)
    assert result.to_record()['backtest_created'] is False
    raw = Path(m.__file__).read_bytes(); tree = ast.parse(raw)
    assert not any(isinstance(node, ast.Attribute) and node.attr in ('read_bytes', 'write_bytes', 'admit',
        'request', 'get_file_path', 'save_bytes', 'getenv', 'system', 'Popen') for node in ast.walk(tree))
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id in ('open', 'eval', 'exec', '__import__') for node in ast.walk(tree))
