"""Synthetic source/Main integration only; no DATA, QC or launch operation."""
import ast
import copy
import dataclasses
import importlib.abc
import importlib.util
import inspect
import json
import sys
import types
from decimal import Decimal
from pathlib import Path

import pytest

from scripts import arv2_r337_quarantine_projection as m
from research.analyst_revisions_v2_qc import accepted_risk_october_order_package as calendar


PUBLIC = Path(__file__).resolve().parents[2] / 'research' / 'analyst_revisions_v2_qc'
PROJECT = 40000001


def vendor_context(project=PROJECT):
    fmt = m.vendor.fmt
    return {'schema': fmt.SCHEMA + '-QC-context', 'runtime_project_id': project,
        'manifest_pin': {'byte_count': 700, 'sha256': 'a' * 64},
        'catalog_pin': {'byte_count': 900, 'sha256': 'b' * 64},
        'object_key_prefix': str(project) + '/arv2/r326-common/' + 'a' * 64 + '/',
        'AP_fact_sha256': fmt.AP_FACT_SHA256,
        'AP_authentication_sha256': fmt.AP_AUTH_SHA256}


@pytest.fixture(scope='module')
def prepared():
    # Only public code is read. The five identifiers are invented; changing the
    # pure policy's expected hashes is a synthetic seam, never data admission.
    sources = tuple((name, (PUBLIC / name).read_bytes()) for name in sorted(m.HOST_SOURCE_PINS))
    axis = calendar._sessions()
    rows = [{'security_id': f'SYNTHETIC-QUARANTINE-{i}', 'synthetic_only': i}
        for i in range(5)]
    with pytest.MonkeyPatch.context() as patch:
        wholes = tuple(m.digest(row) for row in rows)
        for module in (m.quarantine, m.quarantine.policy):
            patch.setattr(module, 'QUARANTINED_WHOLE_BINDING_SHA256S', wholes)
        catalog = m.quarantine.make_quarantine_catalog_from_bindings(rows)
        arguments = dict(expected_source_pins=dict(m.HOST_SOURCE_PINS), session_axis=axis,
            quarantine_catalog=catalog, expected_quarantine_catalog_sha256=m.digest(catalog),
            runtime_project_id=PROJECT, vendor_source_context=vendor_context())
        batch = m.prepare(sources, **arguments)
        yield sources, arguments, batch


def build(prepared, **changes):
    sources, arguments, _ = prepared
    return m.prepare(changes.pop('source_pairs', sources), **{**arguments, **changes})


def test_exact_six_cells_new_epoch_and_distinct_source_bindings(prepared):
    sources, arguments, batch = prepared
    record = batch.to_record()
    assert record['cell_order'] == [list(cell) for cell in m.CELL_ORDER]
    assert len(sources) == 21 and len(m.CLOUD_SOURCE_PINS) == 19
    assert len(record['cells']) == 6
    assert len({cell['candidate_id'] for cell in record['cells']}) == 6
    assert len({cell['profile_sha256'] for cell in record['cells']}) == 6
    assert record['research_epoch_id'] == 'R337-five-case-quarantine-exploratory-v1'
    assert all(record[field] is False for field in m.FALSE_FLAGS)
    shared = tuple((name, raw) for name, raw in batch.cells[0].source_pairs if name != 'main.py')
    assert all(tuple(pair for pair in cell.source_pairs if pair[0] != 'main.py') == shared
        for cell in batch.cells)
    for cell, (count, arm) in zip(batch.cells, m.CELL_ORDER):
        profile = json.loads(cell.profile_bytes)
        strategy = profile['strategy_profile']
        assert (profile['universe_count'], profile['ar_percent']) == (count, arm)
        assert len(strategy['decision_sessions']) == 259
        assert len(strategy['evaluation_sessions']) == 1242
        assert strategy['first_reference_close'] == '2021-10-29'
        assert strategy['native_price_book_initialized'] is False
        assert strategy['maximum_reference_history_calls'] == 0
        assert profile['quarantine_catalog_sha256'] == arguments['expected_quarantine_catalog_sha256']
        assert profile['source_pins'] == m.CLOUD_SOURCE_PINS
        assert profile['source_pins'] != m.HOST_SOURCE_PINS
        assert all(profile[field] is False for field in m.runtime.FALSE_FLAGS)
    # Public metadata contains no supplied private identifiers/catalog rows.
    assert b'SYNTHETIC-QUARANTINE-' not in batch.record_bytes
    assert 'SYNTHETIC-QUARANTINE-' not in repr(batch)
    assert all('SYNTHETIC-QUARANTINE-' not in repr(cell) for cell in batch.cells)


@pytest.mark.parametrize('index', range(6))
def test_every_emitted_cloud_file_compiles_with_qc_prefix_and_is_bounded(prepared, index):
    cell = prepared[2].cells[index]
    assert len(cell.source_pairs) == 20
    assert sum(len(raw) for _, raw in cell.source_pairs) <= m.MAX_TOTAL_BYTES
    for name, raw in cell.source_pairs:
        assert raw.isascii() and 0 < len(raw) <= 64000
        compile(raw, name, 'exec')
        compile(b'from AlgorithmImports import *\n' + raw, name, 'exec')
    names = dict(cell.source_pairs)
    assert m.LEGACY_NAME not in names and m.TEMPLATE_NAME not in names and m.HELPER_NAME not in names
    assert 'newrule_legacy_primitives.py' in names
    assert m.INPUT_NAME in names and m.LOADER_NAME not in names
    assert b'SpecificNativePriceBook(' not in names[m.DRIVER_NAME]


@pytest.mark.parametrize('name', [
    'accepted_risk_preliminary_rating_evaluator.py', 'accepted_risk_preliminary_rating_policy.py',
    'accepted_risk_order_level_core.py', 'accepted_risk_preopen_rating_score.py'])
def test_frozen_semantic_dependencies_have_identical_ast(prepared, name):
    source = dict(prepared[0])[name]
    output = dict(prepared[2].cells[0].source_pairs)[name]
    assert m._dump(ast.parse(source)) == m._dump(ast.parse(output))


def test_plain_loader_alias_and_legacy_extraction_are_exact_pure_transformations(prepared):
    host = dict(prepared[0]); cloud = dict(prepared[2].cells[0].source_pairs)
    assert m._dump(ast.parse(host[m.LOADER_NAME])) == m._dump(ast.parse(cloud[m.INPUT_NAME]))
    expected = m.frozen.legacy_primitives(host[m.LEGACY_NAME])
    assert m._dump(ast.parse(expected)) == m._dump(ast.parse(cloud['newrule_legacy_primitives.py']))
    assert len(host[m.LEGACY_NAME]) > 64000
    assert len(cloud['newrule_legacy_primitives.py']) < 64000
    tree = ast.parse(cloud['newrule_legacy_primitives.py'])
    assert not any(isinstance(node, ast.FunctionDef) and node.name in ('initialize', 'on_after_open')
        for node in ast.walk(tree))


def test_semantically_equal_mapping_insertion_order_never_changes_main(prepared):
    cell = prepared[2].cells[0]
    profile = json.loads(cell.profile_bytes)
    catalog = prepared[1]['quarantine_catalog']
    context = prepared[1]['vendor_source_context']
    reorder = lambda value: dict(reversed(tuple(value.items())))
    assert m._main(reorder(profile), reorder(catalog), reorder(context),
        cell.template_source_bytes) == dict(cell.source_pairs)['main.py']


class EnumValue(int):
    def GetType(self): return type(self)


STATUS_NAMES = ('New', 'Submitted', 'PartiallyFilled', 'Filled', 'Canceled',
    'None', 'Invalid', 'CancelPending', 'UpdateSubmitted')
STATUS_NUMBERS = (0, 1, 2, 3, 5, 6, 7, 8, 9)


class FakeAlgorithm:
    def __init__(self):
        self.settings = types.SimpleNamespace()
        self.universe_settings = types.SimpleNamespace()
        self.calls, self.equities, self.scheduled = [], [], []
        self.schedule = types.SimpleNamespace(on=lambda *args: self.scheduled.append(args))
        self.date_rules = types.SimpleNamespace(every_day=lambda value: ('every', value))
        self.time_rules = types.SimpleNamespace(
            before_market_open=lambda *args: ('before_open',) + args,
            after_market_open=lambda *args: ('after_open',) + args,
            after_market_close=lambda *args: ('after_close',) + args)
        self.universe = types.SimpleNamespace(etf=lambda *args: ('etf',) + args)
    def set_time_zone(self, *args): self.calls.append(('zone', args))
    def set_start_date(self, *args): self.calls.append(('start', args))
    def set_end_date(self, *args): self.calls.append(('end', args))
    def set_cash(self, *args): self.calls.append(('cash', args))
    def set_benchmark(self, *args): self.calls.append(('benchmark', args))
    def add_equity(self, ticker, resolution, **kwargs):
        self.equities.append((ticker, resolution, kwargs))
        return types.SimpleNamespace(symbol='SYMBOL-' + ticker)
    def add_universe(self, value):
        self.calls.append(('universe', value)); return ('universe', len(self.calls))


def fake_modules(monkeypatch, driver):
    qc = types.ModuleType('AlgorithmImports')
    qc.QCAlgorithm = FakeAlgorithm
    qc.FeeModel = type('FeeModel', (), {})
    qc.OrderFee = lambda amount: ('fee', amount)
    qc.CashAmount = lambda amount, currency: (amount, currency)
    qc.NullSlippageModel = type('NullSlippageModel', (), {})
    qc.Resolution = types.SimpleNamespace(DAILY='DAILY', MINUTE='MINUTE')
    qc.DataNormalizationMode = types.SimpleNamespace(RAW='RAW')
    for name in ('TradeBar', 'QuoteBar', 'Split', 'OrderStatus'):
        setattr(qc, name, type(name, (), {}))
    qc.SplitType = types.SimpleNamespace(SPLIT_OCCURRED='occurred', WARNING='warning')
    system = types.ModuleType('System')
    system.Convert = types.SimpleNamespace(ToInt32=lambda value: int(value))
    system.Enum = types.SimpleNamespace(GetNames=lambda _: STATUS_NAMES,
        GetValues=lambda _: tuple(EnumValue(value) for value in STATUS_NUMBERS))
    runtime = types.ModuleType(m.DRIVER_NAME[:-3])
    runtime.FiveCaseQuarantineComparisonDriver = driver
    runtime.STARTING_CASH = m.runtime.STARTING_CASH
    monkeypatch.setitem(sys.modules, 'AlgorithmImports', qc)
    monkeypatch.setitem(sys.modules, 'System', system)
    monkeypatch.setitem(sys.modules, m.DRIVER_NAME[:-3], runtime)
    return qc


@pytest.mark.parametrize('index', range(6))
def test_actual_main_executes_new_constructor_and_preserves_all_callback_routes(prepared, monkeypatch, index):
    captured = {}
    class CapturedDriver:
        def __init__(self, algorithm, **kwargs):
            # Bind against the actual concrete new-driver AND full initializer
            # signatures, so a fake accepting arbitrary kwargs cannot hide drift.
            bound = inspect.signature(m.runtime.FiveCaseQuarantineComparisonDriver.__init__).bind(
                self, algorithm, **kwargs)
            inspect.signature(m.runtime.FiveCaseQuarantineComparisonDriver._initialize_strategy_state).bind(
                self, algorithm, **bound.arguments['base_kwargs'])
            captured.update(algorithm=algorithm, kwargs=kwargs, events=[])
        def initialize(self): captured['events'].append(('initialize',))
        def fee_basis(self, parameters): return Decimal('123.45')
        def __getattr__(self, name):
            def callback(*args):
                captured['events'].append((name, *args)); return ('result', name, args)
            return callback
    qc = fake_modules(monkeypatch, CapturedDriver)
    cell = prepared[2].cells[index]
    namespace = {'__name__': 'synthetic_main'}
    exec(compile(dict(cell.source_pairs)['main.py'], 'main.py', 'exec'), namespace)
    algorithm = namespace['NewruleComparisonAlgorithm']()
    assert algorithm._fundamentals('before') == []
    assert algorithm._constituents('SPY', 'before') == []
    algorithm.initialize()
    profile = json.loads(cell.profile_bytes)
    kwargs = captured['kwargs']
    assert kwargs['profile'] == profile['strategy_profile']
    assert kwargs['common_profile'] == profile
    assert kwargs['quarantine_catalog'] == prepared[1]['quarantine_catalog']
    assert kwargs['vendor_source_context'] == prepared[1]['vendor_source_context']
    assert 'native_source_context' not in kwargs
    assert kwargs['quote_bar_type'] is qc.QuoteBar
    assert kwargs['trade_bar_type'] is qc.TradeBar
    assert tuple(kwargs[key] for key in ('activation_manifest_key', 'activation_manifest_sha256',
        'activation_manifest_byte_count')) == m.ACTIVATION
    assert ('start', (2021, 9, 1)) in algorithm.calls
    assert ('end', (2026, 10, 13)) in algorithm.calls
    assert ('cash', (Decimal('1000000'),)) in algorithm.calls
    assert algorithm.settings.daily_precise_end_time is True
    assert algorithm.settings.seed_initial_prices is False
    assert algorithm.universe_settings.data_normalization_mode == 'RAW'
    assert algorithm.universe_settings.asynchronous is False
    assert len(algorithm.equities) == 8
    assert all(settings['data_normalization_mode'] == 'RAW' for _, _, settings in algorithm.equities)
    assert [(name, value['fill_forward'], value['extended_market_hours'])
        for name, _, value in algorithm.equities] == [
            (name, name == 'SPY', name == 'SPY') for name in m.quarantine.UNIVERSES]
    assert [item[1] for item in algorithm.scheduled] == [
        ('before_open', 'SYMBOL-SPY', 10), ('after_open', 'SYMBOL-SPY', 1),
        ('after_close', 'SYMBOL-SPY', 0)]
    for _, _, callback in algorithm.scheduled: callback()
    algorithm.on_data('data'); algorithm.on_order_event('order')
    algorithm.on_securities_changed('securities'); algorithm.on_splits('splits')
    algorithm.on_end_of_algorithm()
    assert algorithm._fundamentals('fundamentals') == ('result', 'accept_fundamentals', ('fundamentals',))
    assert algorithm._constituents('QQQ', 'rows') == ('result', 'accept_constituents', ('QQQ', 'rows'))
    assert [event[0] for event in captured['events']] == ['initialize', 'on_before_open',
        'on_after_open', 'on_after_close', 'on_data', 'on_order_event', 'on_securities_changed',
        'on_splits', 'on_end_of_algorithm', 'accept_fundamentals', 'accept_constituents']
    parameters = types.SimpleNamespace(order=types.SimpleNamespace(absolute_quantity=-3),
        security=types.SimpleNamespace(price='999999'))
    configured = []
    security = types.SimpleNamespace(symbol=types.SimpleNamespace(id='SYNTHETIC-CONFIGURED-SID'),
        set_data_normalization_mode=lambda value: configured.append(('raw', value)),
        set_fee_model=lambda value: configured.append(('fee', value)),
        set_slippage_model=lambda value: configured.append(('slippage', value)),
        set_leverage=lambda value: configured.append(('leverage', value)))
    state = object.__new__(m.runtime.FiveCaseQuarantineComparisonDriver)
    state.__dict__.update(_initialized=True, _raw_normalization='RAW',
        _fee_model_factory=kwargs['fee_model_factory'],
        _slippage_model_factory=kwargs['slippage_model_factory'], _configured_sids=set())
    # Reach the genuine inherited zero-argument consumer, rather than only
    # checking the new constructor's keyword names or calling an invented ABI.
    assert m.runtime.FiveCaseQuarantineComparisonDriver.configure_security(state, security) is security
    assert state._configured_sids == {'SYNTHETIC-CONFIGURED-SID'}
    assert [kind for kind, _ in configured] == ['raw', 'fee', 'slippage', 'leverage']
    assert configured[-1] == ('leverage', 1)
    assert configured[1][1].get_order_fee(parameters) == ('fee', (Decimal('.37035'), 'USD'))


def test_cloud_import_closure_executes_without_any_host_research_fallback(prepared, monkeypatch):
    pairs = dict(prepared[2].cells[0].source_pairs)
    # All cloud code executes through an in-memory importer. Any missing flat
    # dependency fails instead of silently finding the host research package.
    class FlatImporter(importlib.abc.MetaPathFinder, importlib.abc.Loader):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.startswith('research'):
                raise AssertionError('host research fallback forbidden')
            if fullname + '.py' in pairs:
                return importlib.util.spec_from_loader(fullname, self)
        def create_module(self, spec): return None
        def exec_module(self, module):
            exec(compile(pairs[module.__name__ + '.py'], module.__name__, 'exec'), module.__dict__)
    finder = FlatImporter()
    previous = {name[:-3]: sys.modules.get(name[:-3]) for name in pairs}
    for name in previous: monkeypatch.delitem(sys.modules, name, raising=False)
    system = types.ModuleType('System')
    monkeypatch.setitem(sys.modules, 'System', system)
    monkeypatch.setattr(sys, 'meta_path', [finder, *sys.meta_path])
    try:
        module = __import__(m.DRIVER_NAME[:-3])
        assert module.__name__ == m.DRIVER_NAME[:-3]
        assert module.FiveCaseQuarantineComparisonDriver.__module__ == module.__name__
        assert module.inputs.__name__ == m.INPUT_NAME[:-3]
        assert module.vendor_reader.IdentityCalendarBridge.__module__ == 'newrule_five_case_quarantine_vendor_book'
        assert module.monetary.__name__ == 'newrule_five_case_quarantine_common_price'
    finally:
        for name, prior in previous.items():
            if prior is None: sys.modules.pop(name, None)
            else: sys.modules[name] = prior


@pytest.mark.parametrize('value', [True, False, 0, -1, 2147483648, '40000001', None])
def test_project_must_be_explicit_positive_exact_integer(prepared, value):
    with pytest.raises(m.Refused, match='project'): build(prepared, runtime_project_id=value)


@pytest.mark.parametrize('change', ['list', 'missing', 'reordered', 'duplicate', 'extra', 'changed', 'nonascii', 'huge'])
def test_exact_supplied_source_inventory_and_bytes_are_bound(prepared, change):
    pairs = prepared[0]
    if change == 'list': pairs = list(pairs)
    elif change == 'missing': pairs = pairs[:-1]
    elif change == 'reordered': pairs = tuple(reversed(pairs))
    elif change == 'duplicate': pairs = pairs[:-1] + (pairs[0],)
    elif change == 'extra': pairs = pairs + (('z.py', b'pass\n'),)
    elif change == 'changed': pairs = ((pairs[0][0], pairs[0][1] + b'# drift\n'),) + pairs[1:]
    elif change == 'nonascii': pairs = ((pairs[0][0], b'\xff'),) + pairs[1:]
    else: pairs = ((pairs[0][0], b'x' * (m.MAX_HOST_BYTES + 1)),) + pairs[1:]
    with pytest.raises(m.Refused): build(prepared, source_pairs=pairs)


@pytest.mark.parametrize('change', ['wrong', 'missing', 'extra', 'list'])
def test_expected_pins_cannot_automatically_refresh(prepared, change):
    pins = dict(m.HOST_SOURCE_PINS)
    if change == 'wrong': pins[next(iter(pins))] = 'f' * 64
    elif change == 'missing': pins.pop(next(iter(pins)))
    elif change == 'extra': pins['unknown.py'] = 'a' * 64
    else: pins = list(pins.items())
    with pytest.raises(m.Refused, match='source_pin'): build(prepared, expected_source_pins=pins)


@pytest.mark.parametrize('change', ['list', 'missing', 'reorder', 'wrong_date'])
def test_entire_genuine_axis_is_required(prepared, change):
    axis = prepared[1]['session_axis']
    if change == 'list': axis = list(axis)
    elif change == 'missing': axis = axis[:-1]
    elif change == 'reorder': axis = tuple(reversed(axis))
    else: axis = ('2013-01-03',) + axis[1:]
    with pytest.raises(m.Refused, match='profile'): build(prepared, session_axis=axis)


@pytest.mark.parametrize('change', ['project', 'prefix', 'extra', 'bool', 'bad_manifest', 'bad_catalog', 'AP'])
def test_vendor_context_closed_shape_project_and_original_evidence_pins(prepared, change):
    context = copy.deepcopy(prepared[1]['vendor_source_context'])
    if change == 'project': context = vendor_context(PROJECT + 1)
    elif change == 'prefix': context['object_key_prefix'] += 'extra/'
    elif change == 'extra': context['authorized'] = True
    elif change == 'bool': context['runtime_project_id'] = True
    elif change == 'bad_manifest': context['manifest_pin']['byte_count'] = True
    elif change == 'bad_catalog': context['catalog_pin']['sha256'] = 'not a pin'
    else: context['AP_fact_sha256'] = 'f' * 64
    with pytest.raises(m.Refused): build(prepared, vendor_source_context=context)


@pytest.mark.parametrize('change', ['pin', 'ID', 'flag', 'extra', 'reorder'])
def test_private_catalog_not_replaced_by_claims_or_silent_hash_refresh(prepared, change):
    catalog = copy.deepcopy(prepared[1]['quarantine_catalog'])
    pin = prepared[1]['expected_quarantine_catalog_sha256']
    if change == 'pin': pin = 'a' * 64
    elif change == 'ID': catalog['quarantined_bindings'][0]['security_id'] = 'OTHER'
    elif change == 'flag': catalog['formal_identity_admitted'] = True
    elif change == 'extra': catalog['authorized'] = True
    else: catalog['quarantined_bindings'].reverse()
    with pytest.raises(m.Refused): build(prepared, quarantine_catalog=catalog,
        expected_quarantine_catalog_sha256=pin)


@pytest.mark.parametrize('change', ['start', 'end', 'seed', 'callback', 'fee', 'driver', 'activation', 'profile'])
def test_coherently_rehashed_main_tampering_refuses(prepared, change):
    cell = prepared[2].cells[0]
    pairs = dict(cell.source_pairs)
    raw = pairs['main.py']
    replacements = {
        'start': (b'set_start_date(2021, 9, 1)', b'set_start_date(2021, 8, 1)'),
        'end': (b'set_end_date(2026, 10, 13)', b'set_end_date(2026, 10, 12)'),
        'seed': (b'seed_initial_prices = False', b'seed_initial_prices = True'),
        'callback': (b'self._driver.on_data(data)', b'self._driver.on_splits(data)'),
        'fee': (b"Decimal('0.001')", b"Decimal('0.002')"),
        'driver': (b'FiveCaseQuarantineComparisonDriver as NewruleComparisonDriver', b'OtherDriver as NewruleComparisonDriver'),
        'activation': (m.ACTIVATION[1].encode(), b'f' * 64),
        'profile': (b"COMMON_PRICE_PROFILE['strategy_profile']", b'COMMON_PRICE_PROFILE')}
    before, after = replacements[change]
    assert before in raw
    pairs['main.py'] = raw.replace(before, after, 1)
    pairs = tuple(sorted(pairs.items()))
    # Rehashing the public file record alone never approves changed strategy.
    profile = json.loads(cell.profile_bytes)
    changed = dataclasses.replace(cell, source_pairs=pairs,
        record_bytes=m.canonical(m._cell_record(profile, pairs)))
    with pytest.raises(m.Refused, match='main'): changed.to_record()


@pytest.mark.parametrize('change', ['source', 'profile', 'record', 'duplicate_json', 'template'])
def test_each_cell_authenticates_all_contents_not_only_its_record_hash(prepared, change):
    cell = prepared[2].cells[0]
    if change == 'source':
        pairs = tuple((name, raw + b'# forged\n' if name == m.INPUT_NAME else raw) for name, raw in cell.source_pairs)
        changed = dataclasses.replace(cell, source_pairs=pairs)
    elif change == 'profile':
        profile = json.loads(cell.profile_bytes); profile['strategy_result_accepted'] = True
        changed = dataclasses.replace(cell, profile_bytes=m.canonical(profile))
    elif change == 'record':
        record = json.loads(cell.record_bytes); record['backtest_created'] = True
        changed = dataclasses.replace(cell, record_bytes=m.canonical(record))
    elif change == 'duplicate_json':
        changed = dataclasses.replace(cell, record_bytes=b'{"schema":1,"schema":2}')
    else: changed = dataclasses.replace(cell, template_source_bytes=cell.template_source_bytes + b'\n')
    with pytest.raises(m.Refused): changed.to_record()


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'reorder', 'record', 'wrong_type'])
def test_closed_all_six_family_refuses_partial_or_mislabelled_results(prepared, change):
    batch = prepared[2]
    if change == 'missing': changed = dataclasses.replace(batch, cells=batch.cells[:-1])
    elif change == 'duplicate': changed = dataclasses.replace(batch, cells=batch.cells[:-1] + (batch.cells[0],))
    elif change == 'reorder': changed = dataclasses.replace(batch, cells=tuple(reversed(batch.cells)))
    elif change == 'wrong_type': changed = dataclasses.replace(batch, cells=list(batch.cells))
    else:
        record = json.loads(batch.record_bytes); record['strategy_result_accepted'] = True
        changed = dataclasses.replace(batch, record_bytes=m.canonical(record))
    with pytest.raises(m.Refused): changed.to_record()


def test_individually_valid_other_project_cell_cannot_enter_six_cell_family(prepared):
    batch = prepared[2]
    cell = batch.cells[0]
    original = json.loads(cell.profile_bytes)
    context = vendor_context(PROJECT + 1)
    profile = m.runtime.make_profile(original['strategy_profile'], runtime_project_id=PROJECT + 1,
        vendor_source_context_sha256=m.digest(context),
        quarantine_catalog_sha256=original['quarantine_catalog_sha256'], source_pins=m.CLOUD_SOURCE_PINS)
    pairs = dict(cell.source_pairs)
    pairs['main.py'] = m._main(profile, prepared[1]['quarantine_catalog'], context, cell.template_source_bytes)
    pairs = tuple(sorted(pairs.items()))
    other = dataclasses.replace(cell, profile_bytes=m.canonical(profile), source_pairs=pairs,
        record_bytes=m.canonical(m._cell_record(profile, pairs)))
    assert other.to_record()['runtime_project_id'] == PROJECT + 1
    changed = dataclasses.replace(batch, cells=(other,) + batch.cells[1:])
    record = json.loads(batch.record_bytes)
    record['cells'][0] = other.to_record()
    changed = dataclasses.replace(changed, record_bytes=m.canonical(record))
    with pytest.raises(m.Refused, match='batch'): changed.to_record()


@pytest.mark.parametrize('main', [b'def broken(\n',
    b'COMMON_PRICE_PROFILE = nonliteral()\n', b'\x00', b'\xff'])
def test_untrusted_main_shape_has_finite_refusal_not_raw_parser_error(prepared, main):
    cell = prepared[2].cells[0]
    pairs = tuple((name, main if name == 'main.py' else raw) for name, raw in cell.source_pairs)
    with pytest.raises(m.Refused): dataclasses.replace(cell, source_pairs=pairs).to_record()


@pytest.mark.parametrize('scope', ['cell', 'batch'])
@pytest.mark.parametrize('field,value', [('backtest_created', 0), ('all_sources_equal_except_main', 1)])
def test_public_records_preserve_exact_bool_types_not_python_numeric_equality(prepared, scope, field, value):
    item = prepared[2].cells[0] if scope == 'cell' else prepared[2]
    record = json.loads(item.record_bytes)
    record[field] = value
    changed = dataclasses.replace(item, record_bytes=m.canonical(record))
    with pytest.raises(m.Refused): changed.to_record()


def test_no_old_generator_or_operational_entrypoint_is_called(prepared, monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('old operational/generator call')
    monkeypatch.setattr(m.frozen, 'build_projection', forbidden)
    monkeypatch.setattr(m.frozen, 'render_projection', forbidden)
    batch = build(prepared)
    assert batch.batch_sha256 == prepared[2].batch_sha256
    tree = ast.parse(Path(m.__file__).read_bytes())
    names = {node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Name, ast.Attribute))}
    assert not names.intersection({'open', 'read_bytes', 'read_text', 'write_bytes', 'write_text',
        'Popen', 'run', 'urlopen', 'download', 'read', 'read_bytes', 'save', 'submit', 'system'})


@pytest.mark.parametrize('source', [b'from __future__ import annotations\nx: int = 1\n',
    b'from __future__ import division\nx = 1\n', b'def broken(\n', b'\xff'])
def test_normalization_never_silently_waives_annotations_or_invalid_bytes(source):
    with pytest.raises(m.Refused): m._normalize(source, 'synthetic.py')


def test_finite_refusals_do_not_render_arbitrary_exception_or_private_values():
    class Hostile(ValueError):
        def __str__(self): raise AssertionError('raw exception string observed')
    assert m.finite(Hostile('PRIVATE')) == 'unknown'
    assert m.finite(m.Refused('source_pin')) == 'source_pin'
    assert m.finite(m.Refused('PRIVATE')) == 'unknown'
    assert all(value is False for value in m.profile_record().values() if type(value) is bool)
