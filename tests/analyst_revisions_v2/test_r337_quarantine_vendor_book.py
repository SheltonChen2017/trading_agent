"""Synthetic concrete quarantine reader/bridge; no private data or operations."""
import ast
import copy
from datetime import datetime
from decimal import Decimal
import inspect
import pickle
from types import SimpleNamespace as NS

import pytest

from research.analyst_revisions_v2_qc import newrule_five_case_quarantine_vendor_book as m
from tests.analyst_revisions_v2 import test_r298_native_price_source_diagnostic as fixtures

f, q = m.fmt, m.quarantine


def deny(*args, **kwargs):
    raise AssertionError('native book, History, package reload, provider or publication forbidden')


@pytest.fixture(autouse=True)
def no_old_operations(monkeypatch):
    for name in ('prepare', '_capture', '_package', '_resolve_with_census', '_schedule', '_configure'):
        monkeypatch.setattr(m.native.NativePriceSourceDiagnostic, name, deny)
    monkeypatch.setattr(m.publication.SpecificSourceBookNamespace, 'publish', deny)
    monkeypatch.setattr(fixtures.History, '__getitem__', deny)


@pytest.fixture
def case(monkeypatch):
    s = fixtures.scenario.__wrapped__(monkeypatch)
    rows = tuple(s.rows); axis = tuple(row['session'] for row in s.grid)
    s.algorithm.project_id = 40000001
    for name, value in {'STOCK_COUNT': 7, 'VENDOR_COUNT': 1, 'NATIVE_COUNT': 5,
            'CONDITIONAL_COUNT': 1, 'SESSION_COUNT': 4, 'MONTH_COUNT': 4,
            'BINDING_SHA256': m.native.inputs._stream_hash(rows), 'FULL_AXIS_SHA256': m.digest(list(axis)),
            'OBSERVED_ROWS': 35, 'ABSENT_CELLS': 1}.items():
        monkeypatch.setattr(f, name, value)
    wholes = tuple(m.digest(row) for row in rows[:5])
    policy = getattr(q, 'policy', q)
    for owner in {q, policy}:
        monkeypatch.setattr(owner, 'ORIGINAL_BINDING_COUNT', len(rows))
        monkeypatch.setattr(owner, 'ORIGINAL_BINDING_STREAM_SHA256', f.BINDING_SHA256)
        monkeypatch.setattr(owner, 'QUARANTINED_WHOLE_BINDING_SHA256S', wholes)
    monkeypatch.setattr(m, 'QUARANTINED_WHOLES', frozenset(wholes))
    catalog = q.make_quarantine_catalog(rows); catalog_sha = m.digest(catalog)
    package = m.native.inputs.LoadedAcceptedRiskPreliminaryPackage('synthetic-package', m.native.PACKAGE_SHA256,
        m.native.ACTIVATION_SHA256, s.loaded.evaluator_input, rows)
    resolution = m.native.figi.resolve_preliminary_qc_figis(rows,
        expected_security_master_admission_sha256=m.native.ADMISSION_SHA256,
        composite_figi=s.algorithm.composite_figi, benchmark_symbol=s.etfs['SPY'])
    s.algorithm.composite_figi = deny
    monkeypatch.setattr(m.native.inputs, 'load_accepted_risk_preliminary_package', deny)
    def bridge(**changes):
        kwargs = dict(package=package, resolution=resolution, stock_bindings=rows, full_axis=axis,
            benchmark_symbol=s.etfs['SPY'], etf_symbols=s.etfs, raw_normalization='RAW',
            frozen_runtime_project_id=40000001, quarantine_catalog=copy.deepcopy(catalog),
            expected_quarantine_catalog_sha256=catalog_sha)
        kwargs.update(changes); return m.IdentityCalendarBridge(s.algorithm, **kwargs)
    identity = bridge(); identity.authenticate_once()
    assignments = []
    for index, row in enumerate(rows):
        role = f.NATIVE if index < 5 else f.VENDOR if index == 5 else f.CONDITIONAL
        assignments.append({'binding_ordinal': index, 'security_id': row['security_id'],
            'whole_binding_sha256': m.digest(row), 'semantic_binding_sha256': row['row_sha256'],
            'role': role, 'table': 'stocks' if role == f.VENDOR else None,
            'ticker': 'SYNTH5' if role == f.VENDOR else None,
            'refusal_reason': 'identity_missing' if role == f.NATIVE else None})
    for index, ticker in enumerate(f.OWN_FUNDS):
        assignments.append({'fund_ordinal': index, 'own_ETF': ticker, 'role': f.VENDOR,
            'table': 'funds', 'ticker': ticker, 'route_sha256': m.digest({'fund': ticker})})
    payload_catalog = {'schema': f.SCHEMA + '-catalog', 'AP_fact_sha256': f.AP_FACT_SHA256,
        'AP_source_sha256': f.AP_SOURCE_SHA256, 'AP_authentication_sha256': f.AP_AUTH_SHA256,
        'source_data_pins': copy.deepcopy(f.AP_DATA_PINS), 'binding_stream_sha256': f.BINDING_SHA256,
        'full_axis_sha256': f.FULL_AXIS_SHA256, 'price_sessions': list(axis), 'assignments': assignments,
        'vendor_slots': [5, *range(7, 15)], 'months': f.months(list(axis)), **f.FALSE_FLAGS}
    f.validate_catalog(payload_catalog); catalog_raw = f.canonical(payload_catalog)
    shards, months = {}, []
    for month in payload_catalog['months']:
        index = month['session_indexes'][0]
        raw = b''.join(f.canonical([slot, index, None if slot == 5 and index == 1 else '123.45']) + b'\n'
            for slot in payload_catalog['vendor_slots'])
        valid = 8 if index == 1 else 9
        months.append({**month, 'row_count': 9, 'valid_count': valid, 'absent_count': 9 - valid, **f.pin(raw)})
        shards[index] = raw
    manifest = {'schema': f.SCHEMA + '-manifest', 'catalog_pin': f.pin(catalog_raw),
        'AP_fact_sha256': f.AP_FACT_SHA256, 'AP_authentication_sha256': f.AP_AUTH_SHA256,
        'binding_stream_sha256': f.BINDING_SHA256, 'full_axis_sha256': f.FULL_AXIS_SHA256,
        'assignment_count': 15, 'vendor_slot_count': 9, 'session_count': 4, 'months': months,
        'row_count': 36, 'valid_count': 35, 'absent_count': 1,
        'total_shard_bytes': sum(map(len, shards.values())), **f.FALSE_FLAGS}
    f.validate_manifest(manifest); manifest_raw = f.canonical(manifest)
    prefix = '40000001/arv2/r326-common/' + f.sha(manifest_raw) + '/'
    context = {'schema': f.SCHEMA + '-QC-context', 'runtime_project_id': 40000001,
        'manifest_pin': f.pin(manifest_raw), 'catalog_pin': f.pin(catalog_raw), 'object_key_prefix': prefix,
        'AP_fact_sha256': f.AP_FACT_SHA256, 'AP_authentication_sha256': f.AP_AUTH_SHA256}
    payloads = {prefix + 'manifest.json': manifest_raw, prefix + 'catalog.json': catalog_raw}
    for index, raw in shards.items():
        payloads[prefix + 'month-' + format(index, '02d') + '-' + f.sha(raw) + '.jsonl'] = raw
    class Store:
        def __init__(self): self.calls = []; self.payloads = payloads
        def read_bytes(self, key): self.calls.append(key); return self.payloads[key]
        save_bytes = contains_key = deny
    store = Store(); s.algorithm.object_store = store
    def reader(**changes):
        kwargs = dict(identity_bridge=identity, resolution=resolution, stock_bindings=rows,
            etf_symbols=tuple(s.etfs[ticker] for ticker in f.OWN_FUNDS), frozen_source_context=copy.deepcopy(context),
            expected_context_sha256=m.digest(context), frozen_runtime_project_id=40000001,
            quarantine_catalog=copy.deepcopy(catalog), expected_quarantine_catalog_sha256=catalog_sha)
        kwargs.update(changes); return m.SpecificQuarantineVendorPriceBook(s.algorithm, **kwargs)
    return NS(source=s, rows=rows, axis=axis, catalog=catalog, catalog_sha=catalog_sha,
        package=package, resolution=resolution, bridge=bridge, identity=identity,
        reader=reader, store=store, context=context, shards=shards, payload_catalog=payload_catalog,
        manifest=manifest, prefix=prefix)


def test_genuine_loaded_bridge_no_native_book_reload_history_subscription_or_second_resolution(case):
    receipt = case.identity.receipt()
    assert receipt['fresh_input_binding_count'] == 7
    assert receipt['fresh_resolution_sha256'] == case.resolution.resolution_sha256
    assert receipt['fresh_resolved_count'] + receipt['fresh_named_refusal_count'] == 7
    assert receipt['native_price_book_initialized'] is False
    assert receipt['native_price_book_reads'] == receipt['native_price_lookup_attempts'] == receipt['native_price_lookup_completed'] == 0
    assert receipt['separate_forward_native_SID_census_collected'] is False
    assert len(case.source.forwards) == len(case.source.reverses) == 7
    assert case.source.loads == case.source.adds == case.source.history.calls == case.store.calls == []


def test_new_vendor_constructor_inert_original_payload_context_unchanged_and_price_lookup(case):
    value = case.reader(); assert case.store.calls == []
    receipt = value.authenticate_once()
    assert len(case.store.calls) == 2
    assert receipt['schema'] != f.SCHEMA + '-vendor-runtime-receipt'
    assert receipt['quarantine_epoch'] == q.RESEARCH_EPOCH_ID
    assert receipt['quarantine_catalog_sha256'] == case.catalog_sha
    assert receipt['reader_profile_sha256'] == m.digest(m.profile_record())
    assert value.price(dict(case.rows[5]), case.axis[0]) == Decimal('123.45')
    assert len(case.store.calls) == 3
    assert value.symbol_for_binding(dict(case.rows[5])) is case.resolution.symbol_for_security(case.rows[5]['security_id'])
    fund = {'schema': m.FUND_SCHEMA, 'ticker': 'SPY'}
    assert value.symbol_for_fund(fund) is case.source.etfs['SPY']
    assert value.price(fund, case.axis[0]) == Decimal('123.45')
    assert all(receipt[key] is False for key in f.FALSE_FLAGS)


@pytest.mark.parametrize('ordinal', range(5))
@pytest.mark.parametrize('access', ['price', 'symbol', 'bridge_symbol'])
def test_all_five_denied_before_any_public_symbol_or_month_read(case, monkeypatch, ordinal, access):
    value = case.reader(); value.authenticate_once()
    observed = []
    original = m.native.figi.PreliminaryQcFigiResolution.symbol_for_security
    def watched(self, security_id):
        observed.append(security_id); return original(self, security_id)
    monkeypatch.setattr(m.native.figi.PreliminaryQcFigiResolution, 'symbol_for_security', watched)
    row = dict(case.rows[ordinal])
    with pytest.raises(m.Refused, match='quarantine'):
        if access == 'price': value.price(row, case.axis[0])
        elif access == 'symbol': value.symbol_for_binding(row)
        else: case.identity.symbol_for_binding(row)
    assert observed == [] and len(case.store.calls) == 2


def test_catalog_and_month_schema_guards_are_shared_not_forked(case):
    value = case.reader(); value.authenticate_once()
    assert len(value._catalog['assignments']) == 15
    assert value._catalog['assignments'] == case.payload_catalog['assignments']
    assert value._catalog['vendor_slots'] == [5, *range(7, 15)]
    assert value._catalog['binding_stream_sha256'] == f.BINDING_SHA256


@pytest.mark.parametrize('access', ['price', 'symbol'])
def test_conditional_never_role_still_refuses_if_held_or_requested(case, access):
    value = case.reader(); value.authenticate_once()
    with pytest.raises(m.Refused):
        if access == 'price': value.price(dict(case.rows[6]), case.axis[0])
        else: value.symbol_for_binding(dict(case.rows[6]))
    assert len(case.store.calls) == 2


@pytest.mark.parametrize('hour, minute', [(9, 20), (15, 59)])
def test_no_lookahead_before_actual_regular_close(case, hour, minute):
    value = case.reader(); value.authenticate_once(); case.source.algorithm.time = datetime(2020, 12, 31, hour, minute)
    with pytest.raises(m.Refused): value.price(dict(case.rows[5]), case.axis[0])
    assert len(case.store.calls) == 2


def test_early_close_uses_frozen_current_NYSE_calendar(case):
    value = case.reader(); value.authenticate_once(); case.source.algorithm.time = datetime(2021, 11, 26, 12, 59)
    with pytest.raises(m.Refused): value.price(dict(case.rows[5]), case.axis[2])
    case.source.algorithm.time = datetime(2021, 11, 26, 13, 0)
    assert value.price(dict(case.rows[5]), case.axis[2]) == Decimal('123.45')


def test_missing_validated_cell_refuses_without_any_native_quote_or_other_date_fallback(case):
    value = case.reader(); value.authenticate_once()
    with pytest.raises(m.Refused, match='missing'): value.price(dict(case.rows[5]), case.axis[1])
    assert len(case.store.calls) == 3 and case.source.history.calls == []


def test_hash_before_decode_and_no_auto_pin_refresh(case, monkeypatch):
    case.store.payloads[case.prefix + 'manifest.json'] += b' '
    monkeypatch.setattr(f, 'loads', deny)
    with pytest.raises(m.Refused, match='hash'): case.reader().authenticate_once()
    assert len(case.store.calls) == 1


@pytest.mark.parametrize('field', ['package', 'activation', 'axis', 'lineage', 'bindings', 'resolution'])
def test_bridge_binds_genuine_loaded_source_and_full_resolution(case, field):
    changes = {}
    if field == 'package': changes['package'] = NS(**vars(case.package))
    elif field == 'activation': object.__setattr__(case.package, 'activation_manifest_sha256', 'f' * 64)
    elif field == 'axis': changes['full_axis'] = tuple(reversed(case.axis))
    elif field == 'lineage': case.package.evaluator_input.source_lineage_sha256s = (('security_master_admission_sha256', 'f' * 64),)
    elif field == 'bindings': changes['stock_bindings'] = tuple(reversed(case.rows))
    else: object.__setattr__(case.resolution, 'resolution_sha256', 'f' * 64)
    with pytest.raises(m.Refused): case.bridge(**changes)
    assert case.store.calls == []


@pytest.mark.parametrize('kind', ['catalog_pin', 'catalog_extra', 'other_project', 'bool_project', 'fake_bridge', 'other_resolution'])
def test_constructor_external_policy_project_and_genuine_bridge_binding(case, kind):
    changes = {}
    if kind == 'catalog_pin': changes['expected_quarantine_catalog_sha256'] = 'f' * 64
    elif kind == 'catalog_extra':
        changes['quarantine_catalog'] = {**case.catalog, 'authorized': True}
        changes['expected_quarantine_catalog_sha256'] = m.digest(changes['quarantine_catalog'])
    elif kind == 'other_project': changes['frozen_runtime_project_id'] = 40000002
    elif kind == 'bool_project': changes['frozen_runtime_project_id'] = True
    elif kind == 'fake_bridge': changes['identity_bridge'] = NS(**vars(case.identity))
    else: changes['resolution'] = copy.copy(case.resolution)
    with pytest.raises(m.Refused): case.reader(**changes)
    assert case.store.calls == []


def test_nonquarantine_unknown_identity_remains_in_catalog_then_stops(case):
    case.source.unavailable.add(case.rows[5]['composite_figi'])
    def resolve(value):
        if type(value) is str:
            return None if value in case.source.unavailable else case.source.symbols[value]
        return next(key for key, symbol in case.source.symbols.items() if symbol is value)
    resolution = m.native.figi.resolve_preliminary_qc_figis(case.rows,
        expected_security_master_admission_sha256=m.native.ADMISSION_SHA256,
        composite_figi=resolve, benchmark_symbol=case.source.etfs['SPY'])
    bridge = case.bridge(resolution=resolution); bridge.authenticate_once()
    value = case.reader(identity_bridge=bridge, resolution=resolution); value.authenticate_once()
    assert len(value._catalog['assignments']) == 15
    with pytest.raises(m.Refused, match='missing'): value.price(dict(case.rows[5]), case.axis[0])
    assert len(case.store.calls) == 2


@pytest.mark.parametrize('change', ['rate', 'currency', 'normalization', 'project', 'stable_SID'])
def test_later_current_USD_RAW_project_and_stable_identity_guards(case, change):
    value = case.reader(); value.authenticate_once(); symbol = value.symbol_for_binding(dict(case.rows[5]))
    security = case.source.securities[symbol]
    if change == 'rate': security.quote_currency.conversion_rate = Decimal(2)
    elif change == 'currency': security.quote_currency.symbol = 'EUR'
    elif change == 'normalization': security.data_normalization_mode = 'Adjusted'
    elif change == 'project': case.source.algorithm.project_id += 1
    else: security.symbol = fixtures.Symbol('SYNTH5', 'CHANGED 123')
    with pytest.raises(m.Refused): value.price(dict(case.rows[5]), case.axis[0])


def test_same_native_SID_display_rename_is_not_a_new_price_identity(case):
    value = case.reader(); value.authenticate_once(); symbol = value.symbol_for_binding(dict(case.rows[5]))
    case.source.securities[symbol].symbol = fixtures.Symbol('MAPPEDLITERAL', str(symbol.id))
    assert value.price(dict(case.rows[5]), case.axis[0]) == Decimal('123.45')


def test_bridge_schedule_change_and_fund_collision_stop_before_payload(case):
    case.source.hours.shift = __import__('datetime').timedelta(minutes=1)
    with pytest.raises(m.Refused): case.bridge().authenticate_once()
    assert case.store.calls == []


def test_initial_orders_or_positive_holding_refuse_and_once_is_consumed(case):
    bridge = case.bridge(); case.source.algorithm.transactions.get_orders = lambda: (object(),)
    with pytest.raises(m.Refused, match='orders'): bridge.authenticate_once()
    case.source.algorithm.transactions.get_orders = lambda: ()
    with pytest.raises(m.Refused, match='once'): bridge.authenticate_once()
    case.source.algorithm.portfolio = {'SYNTH': NS(quantity=Decimal(1))}
    with pytest.raises(m.Refused, match='orders'): case.bridge().authenticate_once()


def test_later_strategy_orders_are_not_a_blanket_vendor_stop(case):
    value = case.reader(); value.authenticate_once()
    case.source.algorithm.transactions.get_orders = lambda: (object(),)
    assert value.price(dict(case.rows[5]), case.axis[0]) == Decimal('123.45')


def test_context_receipt_defensive_copy_and_private_objects_cannot_export(case):
    fresh = m.validate_source_context(case.context); fresh['manifest_pin']['sha256'] = 'f' * 64
    assert m.validate_source_context(case.context) == case.context
    value = case.reader(); value.authenticate_once()
    receipt = value.receipt(); receipt['stock_count'] = 0
    assert value.receipt()['stock_count'] == 7
    receipt = case.identity.receipt(); receipt['fresh_input_binding_count'] = 0
    assert case.identity.receipt()['fresh_input_binding_count'] == 7
    for item in (value, case.identity):
        assert '123.45' not in repr(item)
        with pytest.raises(TypeError): pickle.dumps(item)


def test_two_month_cache_and_changed_month_pin_refuse(case):
    value = case.reader(); value.authenticate_once()
    for session in case.axis:
        value.price({'schema': m.FUND_SCHEMA, 'ticker': 'SPY'}, session)
        assert len(value._cache) <= 2
    key = case.prefix + 'month-00-' + case.manifest['months'][0]['sha256'] + '.jsonl'
    case.store.payloads[key] += b' '
    with pytest.raises(m.Refused, match='hash'): value.price(dict(case.rows[5]), case.axis[0])


def test_closed_System_byte_array_adapter(case, monkeypatch):
    class ByteArray:
        Rank = 1
        def __init__(self, raw): self.raw = raw; self.Length = len(raw)
        def __bytes__(self): return self.raw
        def GetType(self): return NS(FullName='System.Byte[]')
    monkeypatch.setattr(m.publication, '_SYSTEM_BYTE_ARRAY', ByteArray)
    case.store.payloads = {key: ByteArray(raw) for key, raw in case.store.payloads.items()}
    value = case.reader(); value.authenticate_once()
    assert value.price(dict(case.rows[5]), case.axis[0]) == Decimal('123.45')
    case.store.payloads[case.prefix + 'manifest.json'].Rank = 2
    with pytest.raises(m.Refused): case.reader().authenticate_once()


def test_old_payload_source_context_month_price_core_preserved_by_AST():
    from research.analyst_revisions_v2_qc import newrule_raw_vendor_price_book_runtime as old
    assert ast.dump(ast.parse(inspect.getsource(m.validate_source_context)), include_attributes=False) == ast.dump(
        ast.parse(inspect.getsource(old.validate_source_context)), include_attributes=False)
    for name in ('_load_month', 'price'):
        assert ast.dump(ast.parse(__import__('textwrap').dedent(inspect.getsource(getattr(m.SpecificQuarantineVendorPriceBook, name)))), include_attributes=False) == ast.dump(
            ast.parse(__import__('textwrap').dedent(inspect.getsource(getattr(old.SpecificVendorPriceBook, name)))), include_attributes=False)
    imports = [node for node in ast.walk(ast.parse(inspect.getsource(m))) if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert not any('newrule_native_price_book_runtime' in ast.unparse(node) for node in imports)


def refreeze_payload(case, *, shard_ordinal=None, raw=None, catalog=None):
    """Synthetic external pin selection; no automatic production refresh exists."""
    manifest = copy.deepcopy(case.manifest)
    changed_catalog = case.payload_catalog if catalog is None else catalog
    catalog_raw = f.canonical(changed_catalog)
    manifest['catalog_pin'] = f.pin(catalog_raw)
    if shard_ordinal is not None:
        summary = manifest['months'][shard_ordinal]
        summary.update(f.pin(raw))
        manifest['total_shard_bytes'] = sum(row['byte_count'] for row in manifest['months'])
    manifest_raw = f.canonical(manifest)
    prefix = '40000001/arv2/r326-common/' + f.sha(manifest_raw) + '/'
    context = {**case.context, 'manifest_pin': f.pin(manifest_raw), 'catalog_pin': f.pin(catalog_raw), 'object_key_prefix': prefix}
    payloads = {prefix + 'manifest.json': manifest_raw, prefix + 'catalog.json': catalog_raw}
    for index, value in case.shards.items():
        if index == shard_ordinal: value = raw
        payloads[prefix + 'month-' + format(index, '02d') + '-' + f.sha(value) + '.jsonl'] = value
    case.store.payloads = payloads
    return case.reader(frozen_source_context=context, expected_context_sha256=m.digest(context))


def test_bridge_algorithm_object_is_not_just_a_matching_project_number(case):
    other = NS(**vars(case.source.algorithm))
    with pytest.raises(m.Refused, match='source'):
        m.SpecificQuarantineVendorPriceBook(other, identity_bridge=case.identity,
            resolution=case.resolution, stock_bindings=case.rows,
            etf_symbols=tuple(case.source.etfs[ticker] for ticker in f.OWN_FUNDS),
            frozen_source_context=case.context, expected_context_sha256=m.digest(case.context),
            frozen_runtime_project_id=40000001, quarantine_catalog=case.catalog,
            expected_quarantine_catalog_sha256=case.catalog_sha)
    assert case.store.calls == []


def test_bridge_own_fund_objects_are_bound_to_the_same_runtime(case):
    symbols = tuple(case.source.etfs[ticker] for ticker in f.OWN_FUNDS)
    other = fixtures.Symbol('SPY', str(symbols[0].id))
    with pytest.raises(m.Refused): case.reader(etf_symbols=(other, *symbols[1:]))
    assert case.store.calls == []


def test_full_month_guard_checks_a_nonrequested_fund_price_row(case):
    rows = [f.loads(line, 1024) for line in case.shards[0].splitlines()]
    assert rows[-1][0] == 14
    rows[-1][2] = '0'
    raw = b''.join(f.canonical(row) + b'\n' for row in rows)
    value = refreeze_payload(case, shard_ordinal=0, raw=raw); value.authenticate_once()
    with pytest.raises(m.Refused, match='price'):
        value.price(dict(case.rows[5]), case.axis[0])
    assert len(case.store.calls) == 3


@pytest.mark.parametrize('field', ['security_id', 'semantic_binding_sha256'])
def test_catalog_assignment_cannot_rebind_an_original_whole_binding(case, field):
    catalog = copy.deepcopy(case.payload_catalog)
    catalog['assignments'][5][field] = 'invented-security' if field == 'security_id' else 'f' * 64
    value = refreeze_payload(case, catalog=catalog)
    with pytest.raises(m.Refused, match='assignment'): value.authenticate_once()
    assert len(case.store.calls) == 2


def test_quarantined_native_role_set_cannot_be_swapped_with_a_vendor_stock(case):
    catalog = copy.deepcopy(case.payload_catalog)
    for index, role in ((0, f.VENDOR), (5, f.NATIVE)):
        row = catalog['assignments'][index]; row['role'] = role
        row['table'] = 'stocks' if role == f.VENDOR else None
        row['ticker'] = 'SYNTH0' if role == f.VENDOR else None
        row['refusal_reason'] = None if role == f.VENDOR else 'identity_missing'
    catalog['vendor_slots'] = [0, *range(7, 15)]
    f.validate_catalog(catalog)
    value = refreeze_payload(case, catalog=catalog)
    with pytest.raises(m.Refused, match='quarantine'): value.authenticate_once()
    assert len(case.store.calls) == 2


def test_resolved_stock_collision_with_any_own_fund_refuses_before_payload(case):
    stock = case.source.symbols[case.rows[5]['composite_figi']]
    same_sid = fixtures.Symbol('QQQ', str(stock.id))
    case.source.etfs['QQQ'] = same_sid
    case.source.securities[same_sid] = fixtures.Security(same_sid, case.source.hours)
    with pytest.raises(m.Refused, match='identity'): case.bridge().authenticate_once()
    assert case.store.calls == []


def test_failed_source_authentication_is_not_reusable(case):
    case.store.payloads[case.prefix + 'manifest.json'] += b' '
    value = case.reader()
    with pytest.raises(m.Refused): value.authenticate_once()
    with pytest.raises(m.Refused): value.authenticate_once()
    assert len(case.store.calls) == 1


def test_plausible_but_wrong_close_schedule_still_refuses_exact_calendar_pin(case):
    original = case.source.hours.get_next_market_close
    case.source.hours.get_next_market_close = lambda when, extended: original(when, extended) - __import__('datetime').timedelta(minutes=1)
    with pytest.raises(m.Refused, match='calendar'): case.bridge().authenticate_once()
    assert case.store.calls == []


@pytest.mark.parametrize('stage',['manifest','catalog','month'])
def test_actual_ObjectStore_builtin_timeout_is_deadline_without_retry(case,stage):
    value=case.reader()
    if stage=='month':value.authenticate_once()
    target=(case.prefix+'manifest.json' if stage=='manifest' else case.prefix+'catalog.json'
        if stage=='catalog' else case.prefix+'month-00-'+case.manifest['months'][0]['sha256']+'.jsonl')
    original=case.store.read_bytes;reached=[]
    def read(key):
        if key==target:
            case.store.calls.append(key);reached.append(key)
            raise TimeoutError('SYNTHETIC PRIVATE TRANSPORT MESSAGE')
        return original(key)
    case.store.read_bytes=read
    with pytest.raises(m.Refused) as caught:
        if stage=='month':value.price(dict(case.rows[5]),case.axis[0])
        else:value.authenticate_once()
    assert reached==[target]
    assert len(case.store.calls)=={'manifest':1,'catalog':2,'month':3}[stage]
    assert caught.value.args==('deadline',) and m.finite(caught.value)=='deadline'
    assert 'PRIVATE' not in str(caught.value)
    assert value._cache=={}
    if stage!='month':
        with pytest.raises(m.Refused):value.authenticate_once()
        assert reached==[target]  # A failed authentication cannot be dispatched again.


@pytest.mark.parametrize('fault',['runtime','key','malformed','timeout_subclass'])
def test_unclassified_store_error_or_malformed_value_stays_missing(case,fault):
    class OtherTimeout(TimeoutError):pass
    value=case.reader();reached=[]
    def read(key):
        case.store.calls.append(key);reached.append(key)
        if fault=='malformed':return object()
        error={'runtime':RuntimeError,'key':KeyError,'timeout_subclass':OtherTimeout}[fault]
        raise error('SYNTHETIC PRIVATE ERROR')
    case.store.read_bytes=read
    with pytest.raises(m.Refused) as caught:value.authenticate_once()
    assert reached==[case.prefix+'manifest.json']
    assert caught.value.args==('missing',) and m.finite(caught.value)=='missing'


def test_already_normalized_local_deadline_not_relabelled_as_missing(case):
    value=case.reader();reached=[]
    def read(key):
        case.store.calls.append(key);reached.append(key)
        raise m.Refused('deadline')
    case.store.read_bytes=read
    with pytest.raises(m.Refused) as caught:value.authenticate_once()
    assert reached==[case.prefix+'manifest.json'] and caught.value.args==('deadline',)


@pytest.mark.parametrize('method',['get_next_market_open','get_next_market_close'])
def test_actual_calendar_provider_builtin_timeout_is_deadline_no_store_contact(case,method):
    reached=[]
    def timeout(*args):
        reached.append(method);raise TimeoutError('SYNTHETIC PRIVATE CALENDAR MESSAGE')
    setattr(case.source.hours,method,timeout)
    bridge=case.bridge()
    with pytest.raises(m.Refused) as caught:bridge.authenticate_once()
    assert reached==[method] and caught.value.args==('deadline',)
    assert m.finite(caught.value)=='deadline' and case.store.calls==[]
    with pytest.raises(m.Refused,match='once'):bridge.authenticate_once()
    assert reached==[method]


@pytest.mark.parametrize('fault',['runtime','timeout_subclass'])
def test_unclassified_calendar_failure_stays_calendar(case,fault):
    class OtherTimeout(TimeoutError):pass
    reached=[]
    def failure(*args):
        reached.append(True)
        error=RuntimeError if fault=='runtime' else OtherTimeout
        raise error('SYNTHETIC PRIVATE CALENDAR MESSAGE')
    case.source.hours.get_next_market_open=failure
    with pytest.raises(m.Refused) as caught:case.bridge().authenticate_once()
    assert reached==[True] and caught.value.args==('calendar',) and case.store.calls==[]
