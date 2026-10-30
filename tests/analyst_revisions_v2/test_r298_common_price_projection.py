"""Public-source-only projection and synthetic import/constructor checks."""
import ast
import builtins
import copy
import dataclasses
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS

import pytest

from scripts import arv2_r298_common_price_projection as m
from tests.analyst_revisions_v2 import test_quote_execution_projection as frozen_tests
from tests.analyst_revisions_v2 import test_newrule_runtime_projection as old

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')


@pytest.fixture(scope='module')
def public():
    prior = frozen_tests.public.__wrapped__()
    folder = ROOT / 'research/analyst_revisions_v2_qc'
    addons = tuple((name, (folder / name).read_bytes()) for name in m.ADDON_NAMES)
    from research.analyst_revisions_v2_qc import newrule_common_price_format as fmt
    vendor = {'schema': fmt.SCHEMA + '-QC-context', 'runtime_project_id': 123,
        'manifest_pin': {'byte_count': 1000, 'sha256': 'a' * 64},
        'catalog_pin': {'byte_count': 2000, 'sha256': 'b' * 64},
        'object_key_prefix': '123/arv2/r326-common/' + 'a' * 64 + '/',
        'AP_fact_sha256': fmt.AP_FACT_SHA256, 'AP_authentication_sha256': fmt.AP_AUTH_SHA256}
    patcher = (ROOT / 'scripts' / m.PATCHER_NAME).read_bytes()
    return NS(prior=prior, addons=addons, pins={name: m.sha(raw) for name, raw in addons},
        native=m.native_reader.source_context(), vendor=vendor, patcher=patcher,
        axis=m.frozen.comparison.bridge.frozen.october._sessions())


def build(public, *, count=6, arm=0, **changes):
    arguments = {'session_axis': public.axis, 'runtime_project_id': 123, 'universe_count': count,
        'ar_percent': arm, 'native_source_context': public.native, 'vendor_source_context': public.vendor,
        'expected_addon_pins': public.pins, 'patcher_source_bytes': public.patcher,
        'expected_patcher_sha256': m.sha(public.patcher)}
    arguments.update(changes)
    return m.public_specification(public.prior.projected.record_bytes, public.prior.projected.source_pairs,
        public.addons, **arguments)


def refused(code, operation):
    with pytest.raises(m.Refused) as caught: operation()
    assert m.finite(caught.value) == code


@pytest.mark.parametrize('count', [6, 8])
@pytest.mark.parametrize('arm', [0, 100, 200])
def test_pure_projection_six_cells_share_exact_source_policy_and_preserve_quote_base(public, count, arm):
    result = build(public, count=count, arm=arm)
    record, profile, files = result.to_record(), json.loads(result.profile_bytes), dict(result.source_pairs)
    assert m.runtime.validate_profile(profile) == profile
    assert profile['universe_count'] == count and profile['ar_percent'] == arm
    assert files[m.BASE_NAME] == public.prior.files[m.BASE_NAME]
    assert m.sha(files[m.BASE_NAME]) == m.runtime.FROZEN_BASE_SHA256
    assert record['unchanged_frozen_files'] == [name for name, _ in public.prior.projected.source_pairs if name != 'main.py']
    assert all(record[key] is False for key in m.FALSE_FLAGS)
    assert profile['strategy_profile']['execution_policy'] == m.frozen.POLICY
    assert profile['strategy_profile']['source_pins'] == public.prior.profile['source_pins']
    assert profile['source_pins'][m.DRIVER_NAME] == m.sha(files[m.DRIVER_NAME])
    assert 'main.py' not in profile['source_pins']  # External manifest pins Main without recursive self-pins.
    assert len(result.source_pairs) == 18 and all(len(raw) <= 64000 for raw in files.values())


def test_main_changes_only_pinned_class_import_profiles_and_early_project_guard(public):
    result = build(public)
    original, actual = ast.parse(public.prior.files['main.py']), ast.parse(dict(result.source_pairs)['main.py'])
    old_class = next(node for node in original.body if isinstance(node, ast.ClassDef) and node.name == 'NewruleComparisonAlgorithm')
    new_class = next(node for node in actual.body if isinstance(node, ast.ClassDef) and node.name == 'NewruleComparisonAlgorithm')
    old_methods = {node.name: node for node in old_class.body if isinstance(node, ast.FunctionDef)}
    new_methods = {node.name: node for node in new_class.body if isinstance(node, ast.FunctionDef)}
    assert set(old_methods) == set(new_methods)
    for name in old_methods.keys() - {'initialize'}: assert m._dump(old_methods[name]) == m._dump(new_methods[name])
    old_fee = next(node for node in original.body if isinstance(node, ast.ClassDef) and node.name == 'NewruleTenBpsFeeModel')
    new_fee = next(node for node in actual.body if isinstance(node, ast.ClassDef) and node.name == 'NewruleTenBpsFeeModel')
    assert m._dump(old_fee) == m._dump(new_fee)
    assert isinstance(new_methods['initialize'].body[0], ast.If)
    old_seed = next(node for node in ast.walk(old_methods['initialize']) if isinstance(node, ast.Assign)
        and len(node.targets) == 1 and isinstance(node.targets[0], ast.Attribute)
        and node.targets[0].attr == 'seed_initial_prices')
    new_seed = next(node for node in ast.walk(new_methods['initialize']) if isinstance(node, ast.Assign)
        and len(node.targets) == 1 and isinstance(node.targets[0], ast.Attribute)
        and node.targets[0].attr == 'seed_initial_prices')
    assert old_seed.value.value is True and new_seed.value.value is False
    assert json.loads(result.profile_bytes)['automatic_security_price_seeding'] is False
    call = next(node for node in ast.walk(actual) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id == 'NewruleComparisonDriver')
    keywords = {key.arg: key.value for key in call.keywords}
    assert ast.unparse(keywords['profile']) == "COMMON_PRICE_PROFILE['strategy_profile']"
    assert ast.unparse(keywords['fee_model_factory']) == 'lambda: NewruleTenBpsFeeModel(self._driver)'


def load_cloud_modules(public, monkeypatch):
    files = dict(build(public).source_pairs)
    order = ('accepted_risk_preliminary_rating_policy', 'accepted_risk_preliminary_rating_evaluator',
        'accepted_risk_order_level_core', 'accepted_risk_order_level_forced_exit',
        'accepted_risk_order_level_input_runtime', 'accepted_risk_preliminary_qc_figi',
        'accepted_risk_preopen_rating_score', 'newrule_comparison_targets', 'newrule_legacy_primitives',
        'newrule_comparison_qc_runtime', 'newrule_common_price_format', 'newrule_native_price_source_diagnostic',
        'newrule_native_price_book_publication', 'newrule_native_price_book_runtime',
        'newrule_raw_vendor_price_book_runtime', 'newrule_common_price_qc_runtime',
        'newrule_common_price_comparison_runtime')
    modules = {}
    for name in order:
        module = ModuleType(name); monkeypatch.setitem(sys.modules, name, module)
        exec(compile(files[name + '.py'], '<public-' + name + '>', 'exec'), module.__dict__)
        modules[name] = module
    return modules


def test_all_eighteen_cloud_modules_compile_and_import_one_shared_concrete_type_graph(public, monkeypatch):
    modules = load_cloud_modules(public, monkeypatch)
    driver = modules[m.DRIVER_NAME[:-3]]
    base = modules[m.BASE_NAME[:-3]]
    assert driver.CommonPriceComparisonDriver.__bases__ == (base.NewruleComparisonDriver,)
    assert driver.native_reader is modules['newrule_native_price_book_runtime']
    assert driver.monetary._provider_types() == (driver.native_reader.SpecificNativePriceBook,
        modules['newrule_raw_vendor_price_book_runtime'].SpecificVendorPriceBook)
    for name in ('on_before_open', 'on_after_open', '_split_factors', 'on_order_event', '_quote_snapshot', 'fee_basis'):
        assert getattr(driver.CommonPriceComparisonDriver, name) is getattr(base.NewruleComparisonDriver, name)
    strategy = json.loads(build(public).profile_bytes)['strategy_profile']
    assert base.make_profile(public.axis, package_sha256=strategy['package_sha256'],
        lineage_sha256=strategy['lineage_sha256'], universe_count=6, ar_percent=0,
        source_pins=strategy['source_pins']) == strategy


def constructor(public, modules):
    driver = modules[m.DRIVER_NAME[:-3]]
    prior, algorithm, _ = old.driver()
    algorithm.project_id, algorithm.live_mode = 123, False
    profile = json.loads(build(public).profile_bytes)
    names = ('activation_manifest_key', 'activation_manifest_sha256', 'activation_manifest_byte_count',
        'benchmark_symbol', 'etf_symbols', 'fundamental_universe', 'constituent_universes',
        'trade_bar_type', 'minute_resolution', 'daily_resolution', 'raw_normalization',
        'fee_model_factory', 'slippage_model_factory', 'order_status_enum', 'order_status_to_int',
        'split_occurred_type', 'split_warning_type', 'split_data_type')
    kwargs = {name: getattr(prior, '_' + name) for name in names}
    kwargs.update(profile=profile['strategy_profile'], quote_bar_type=object())
    value = driver.CommonPriceComparisonDriver(algorithm, common_profile=profile,
        native_source_context=public.native, vendor_source_context=public.vendor, **kwargs)
    return value, prior, algorithm, kwargs


def test_cloud_constructor_is_inert_binds_project_context_and_requires_actual_quote_base(public, monkeypatch):
    modules = load_cloud_modules(public, monkeypatch)
    value, prior, algorithm, kwargs = constructor(public, modules)
    driver = modules[m.DRIVER_NAME[:-3]]
    assert value._profile == json.loads(build(public).profile_bytes)['strategy_profile']
    assert value._common_ready is False and value._native_book is value._vendor_book is None
    assert not algorithm.history.calls and not algorithm.submitted
    for project in (True, 124):
        algorithm.project_id = project
        with pytest.raises(driver.Refused): driver.CommonPriceComparisonDriver(algorithm,
            common_profile=json.loads(build(public).profile_bytes), native_source_context=public.native,
            vendor_source_context=public.vendor, **kwargs)


@pytest.mark.parametrize('resolution_mismatch', [False, True])
def test_initialization_authenticates_native_then_vendor_after_base_and_binds_fresh_resolution(public, monkeypatch, resolution_mismatch):
    modules = load_cloud_modules(public, monkeypatch)
    value, prior, algorithm, _ = constructor(public, modules)
    driver = modules[m.DRIVER_NAME[:-3]]
    trace, resolution = [], NS(resolution_sha256='c' * 64)
    def base_initialize(self):
        trace.append('base')
        self._initialized = True
        for name in ('_security_by_sid', '_symbol_by_security', '_security_by_etf_sid', '_session_axis'):
            setattr(self, name, copy.copy(getattr(prior, name)))
        self._resolution, self._package = resolution, NS(runtime_symbol_bindings=({'synthetic': 'binding'},))
        return True
    class Native:
        def __init__(self, algorithm_arg, **kwargs):
            assert trace == ['base'] and algorithm_arg is algorithm
            assert kwargs['frozen_runtime_project_id'] == 123
            trace.append('native_constructed')
        def authenticate_once(self): trace.append('native_auth')
        def receipt(self):
            return {'fresh_full_forward_reverse_resolution_sha256': ('d' if resolution_mismatch else 'c') * 64}
    class Vendor:
        def __init__(self, algorithm_arg, **kwargs):
            assert algorithm_arg is algorithm and kwargs['resolution'] is resolution
            assert kwargs['stock_bindings'] == ({'synthetic': 'binding'},)
            assert type(kwargs['etf_symbols']) is tuple and len(kwargs['etf_symbols']) == 8
            trace.append('vendor_constructed')
        def authenticate_once(self):
            assert trace[-1] == 'native_auth'; trace.append('vendor_auth')
    class Common:
        def __init__(self, native, vendor, **kwargs): self.native, self.vendor = native, vendor
        def authenticate_once(self): self.native.authenticate_once(); self.vendor.authenticate_once()
    monkeypatch.setattr(driver.base.NewruleComparisonDriver, 'initialize', base_initialize)
    monkeypatch.setattr(driver.native_reader, 'SpecificNativePriceBook', Native)
    monkeypatch.setattr(driver.monetary, '_provider_types', lambda: (Native, Vendor))
    monkeypatch.setattr(driver.monetary, 'SpecificCommonPriceBook', Common)
    monkeypatch.setattr(driver.monetary, 'CommonPriceLedger', lambda source: NS(source=source))
    monkeypatch.setattr(driver.base.figi, 'require_preliminary_qc_figi_resolution', lambda observed: observed is resolution)
    if resolution_mismatch:
        with pytest.raises(driver.Refused, match='resolution'): value.initialize()
        assert value._common_ready is False
    else:
        assert value.initialize() is True and value._common_ready is True
    assert trace == ['base', 'native_constructed', 'vendor_constructed', 'native_auth', 'vendor_auth']
    with pytest.raises(driver.Refused, match='once'): value.initialize()
    assert not algorithm.submitted


def test_pure_builder_does_not_read_files_or_old_admission_controls(public, monkeypatch):
    def denied(*args, **kwargs): pytest.fail('public pure builder crossed I/O or admission boundary')
    with monkeypatch.context() as patch:
        patch.setattr(builtins, 'open', denied); patch.setattr(Path, 'read_bytes', denied)
        patch.setattr(m.frozen.admission, 'admit', denied)
        assert build(public).to_record()['backtest_created'] is False


def test_initialize_passes_ordered_tuple_through_actual_vendor_constructor_boundary(public, monkeypatch):
    """Only constructors execute: genuine Vendor type checks, no source authentication."""
    modules = load_cloud_modules(public, monkeypatch)
    value, prior, algorithm, _ = constructor(public, modules)
    driver = modules[m.DRIVER_NAME[:-3]]
    actual_vendor = modules['newrule_raw_vendor_price_book_runtime'].SpecificVendorPriceBook
    actual_native = driver.native_reader.SpecificNativePriceBook
    resolution = NS(resolution_sha256='c' * 64)
    algorithm.time_zone, algorithm.account_currency = 'America/New_York', 'USD'
    algorithm.settings = NS(daily_precise_end_time=True, seed_initial_prices=False)
    def prepared_base(self):
        self._initialized = True
        for name in ('_security_by_sid', '_symbol_by_security', '_security_by_etf_sid', '_session_axis'):
            setattr(self, name, copy.copy(getattr(prior, name)))
        self._resolution, self._package = resolution, NS(runtime_symbol_bindings=tuple(
            {'synthetic': index} for index in range(6151)))
        return True
    class Common:
        def __init__(self, native, vendor, **kwargs):
            assert type(native) is actual_native and type(vendor) is actual_vendor
        def authenticate_once(self): pass  # This test never reads any source or invokes real authentication.
    monkeypatch.setattr(driver.base.NewruleComparisonDriver, 'initialize', prepared_base)
    monkeypatch.setattr(actual_native, '__init__', lambda self, *args, **kwargs: None)
    monkeypatch.setattr(actual_native, 'receipt', lambda self: {
        'fresh_full_forward_reverse_resolution_sha256': resolution.resolution_sha256})
    monkeypatch.setattr(actual_vendor, 'authenticate_once', lambda self: pytest.fail('actual auth forbidden'))
    monkeypatch.setattr(driver.monetary, 'SpecificCommonPriceBook', Common)
    monkeypatch.setattr(driver.monetary, 'CommonPriceLedger', lambda source: NS(source=source))
    monkeypatch.setattr(driver.base.figi, 'require_preliminary_qc_figi_resolution', lambda observed: observed is resolution)
    assert value.initialize() is True
    assert type(value._vendor_book) is actual_vendor
    assert type(value._vendor_book._fund_symbols) is tuple
    assert value._vendor_book._fund_symbols == tuple(value._etf_symbols[ticker] for ticker in driver.monetary.native.UNIVERSES)
    assert not algorithm.submitted and not algorithm.history.calls



@pytest.mark.parametrize('mutation', ['source_pin', 'missing_source', 'bad_context', 'project', 'axis', 'patcher'])
def test_builder_requires_explicit_matching_source_context_and_full_original_axis(public, mutation):
    changes = {}
    if mutation == 'source_pin': changes['expected_addon_pins'] = {**public.pins, m.DRIVER_NAME: '0' * 64}
    elif mutation == 'missing_source': changes['expected_addon_pins'] = {name: pin for name, pin in public.pins.items() if name != m.DRIVER_NAME}
    elif mutation == 'bad_context': changes['vendor_source_context'] = {**public.vendor, 'price_admitted': True}
    elif mutation == 'project': changes['runtime_project_id'] = True
    elif mutation == 'axis': changes['session_axis'] = public.axis[:-1]
    else: changes['expected_patcher_sha256'] = '0' * 64
    with pytest.raises(m.Refused): build(public, **changes)


def test_original_base_record_and_source_pins_are_required_no_runtime_alias_substitution(public):
    changed = tuple((name, raw + b'\n' if name == m.BASE_NAME else raw) for name, raw in public.prior.projected.source_pairs)
    refused('base', lambda: m.public_specification(public.prior.projected.record_bytes, changed,
        public.addons, session_axis=public.axis, runtime_project_id=123, universe_count=6, ar_percent=0,
        native_source_context=public.native, vendor_source_context=public.vendor,
        expected_addon_pins=public.pins, patcher_source_bytes=public.patcher, expected_patcher_sha256=m.sha(public.patcher)))


def test_future_import_only_normalization_does_not_change_native_helper_AST_or_allow_annotations():
    raw = b'"""public"""\nfrom __future__ import annotations\nVALUE = 1\n'
    cloud = m._cloud_source(raw, 'synthetic.py')
    assert cloud == b'"""public"""\nVALUE = 1\n'
    refused('source_annotations', lambda: m._cloud_source(
        b'from __future__ import annotations\ndef f(value: int): return value\n', 'synthetic.py'))


def test_projection_is_immutable_copy_return_and_metadata_is_not_source_or_run_authority(public):
    result = build(public)
    record = result.to_record(); record['backtest_created'] = True
    assert result.to_record()['backtest_created'] is False
    with pytest.raises(dataclasses.FrozenInstanceError): result.profile_bytes = b'{}'
    changed = dataclasses.replace(result, profile_bytes=result.profile_bytes + b'\n')
    refused('projection', changed.to_record)
    record = result.to_record(); record['raw_extra'] = 'PRIVATE'
    raw = m.canonical(record)
    changed = dataclasses.replace(result, record_bytes=raw, projection_sha256=m.sha(raw))
    refused('projection', changed.to_record)


def test_exact_corrected_prospective_reader_pins_and_frozen_used_helpers(public):
    assert public.pins['newrule_native_price_book_runtime.py'] == '76b2a193fe1b8de9c9f8c598464edc2d0058b61aa690e13cc6216051f862a3f6'
    assert public.pins['newrule_raw_vendor_price_book_runtime.py'] == 'c97c9d0d4874b85bd50676e3e87c54840be9f3eab952302deb42a301f67fc430'
    assert public.pins['newrule_native_price_source_diagnostic.py'] == '57450eac9126831bc9d1c106325ed1832c10ba32e883563bb85e10060948e697'
    assert public.pins['newrule_native_price_book_publication.py'] == '03d100e962b98cd8b174d947a33636e421692445422c0dcce2282b46015435e2'
