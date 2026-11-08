"""Synthetic concrete QC vendor reader; no actual ObjectStore or DATA access."""
import copy
from datetime import datetime
from decimal import Decimal
import pickle
from types import SimpleNamespace as NS

import pytest

from research.analyst_revisions_v2_qc import newrule_raw_vendor_price_book_runtime as m
from tests.analyst_revisions_v2 import test_r298_native_price_book_runtime as fixture

f = m.fmt


@pytest.fixture(autouse=True)
def forbid_old_operations(monkeypatch):
    def denied(*args, **kwargs): raise AssertionError('old source/History/publication operation forbidden')
    monkeypatch.setattr(m.native.NativePriceSourceDiagnostic, 'prepare', denied)
    monkeypatch.setattr(m.native.NativePriceSourceDiagnostic, '_capture', denied)
    monkeypatch.setattr(m.native_reader.publication.SpecificSourceBookNamespace, 'publish', denied)
    monkeypatch.setattr(fixture.fixture.History, '__getitem__', denied)


@pytest.fixture
def case(monkeypatch):
    original = fixture.case.__wrapped__(monkeypatch)
    native_book = original.reader(); native_book.authenticate_once()
    source = original.source; rows = tuple(source.rows)
    resolution = original.driver._resolve_with_census(rows)
    sessions = [row['session'] for row in source.grid]
    for name, value in {'STOCK_COUNT': 7, 'VENDOR_COUNT': 1, 'NATIVE_COUNT': 5,
            'CONDITIONAL_COUNT': 1, 'SESSION_COUNT': 4, 'MONTH_COUNT': 4,
            'BINDING_SHA256': m.native.inputs._stream_hash(rows), 'FULL_AXIS_SHA256': m.digest(sessions),
            'OBSERVED_ROWS': 35, 'ABSENT_CELLS': 1}.items():
        monkeypatch.setattr(f, name, value)
    assigned = []
    for index, row in enumerate(rows):
        role = f.NATIVE if index < 5 else f.VENDOR if index == 5 else f.CONDITIONAL
        assigned.append({'binding_ordinal': index, 'security_id': row['security_id'],
            'whole_binding_sha256': m.digest(row), 'semantic_binding_sha256': row['row_sha256'],
            'role': role, 'table': 'stocks' if role == f.VENDOR else None,
            'ticker': 'SYNTH5' if role == f.VENDOR else None, 'refusal_reason': None if role != f.NATIVE else 'identity_missing'})
    for index, ticker in enumerate(f.OWN_FUNDS):
        assigned.append({'fund_ordinal': index, 'own_ETF': ticker, 'role': f.VENDOR,
            'table': 'funds', 'ticker': ticker, 'route_sha256': m.digest({'fund': ticker})})
    catalog = {'schema': f.SCHEMA + '-catalog', 'AP_fact_sha256': f.AP_FACT_SHA256,
        'AP_source_sha256': f.AP_SOURCE_SHA256, 'AP_authentication_sha256': f.AP_AUTH_SHA256,
        'source_data_pins': copy.deepcopy(f.AP_DATA_PINS), 'binding_stream_sha256': f.BINDING_SHA256,
        'full_axis_sha256': f.FULL_AXIS_SHA256, 'price_sessions': sessions, 'assignments': assigned,
        'vendor_slots': [5, *range(7, 15)], 'months': f.months(sessions), **f.FALSE_FLAGS}
    f.validate_catalog(catalog); catalog_raw = f.canonical(catalog)
    shards, metas = {}, []
    for month in catalog['months']:
        index = month['session_indexes'][0]
        raw = b''.join(f.canonical([slot, index, None if slot == 5 and index == 1 else '123.45']) + b'\n' for slot in catalog['vendor_slots'])
        valid = 8 if index == 1 else 9
        meta = {**month, 'row_count': 9, 'valid_count': valid, 'absent_count': 9 - valid, **f.pin(raw)}
        metas.append(meta); shards[index] = raw
    manifest = {'schema': f.SCHEMA + '-manifest', 'catalog_pin': f.pin(catalog_raw),
        'AP_fact_sha256': f.AP_FACT_SHA256, 'AP_authentication_sha256': f.AP_AUTH_SHA256,
        'binding_stream_sha256': f.BINDING_SHA256, 'full_axis_sha256': f.FULL_AXIS_SHA256,
        'assignment_count': 15, 'vendor_slot_count': 9, 'session_count': 4, 'months': metas,
        'row_count': 36, 'valid_count': 35, 'absent_count': 1,
        'total_shard_bytes': sum(len(raw) for raw in shards.values()), **f.FALSE_FLAGS}
    f.validate_manifest(manifest); manifest_raw = f.canonical(manifest)
    prefix = '40000001/arv2/r326-common/' + f.sha(manifest_raw) + '/'
    context = {'schema': f.SCHEMA + '-QC-context', 'runtime_project_id': 40000001,
        'manifest_pin': f.pin(manifest_raw), 'catalog_pin': f.pin(catalog_raw), 'object_key_prefix': prefix,
        'AP_fact_sha256': f.AP_FACT_SHA256, 'AP_authentication_sha256': f.AP_AUTH_SHA256}
    payloads = {prefix + 'manifest.json': manifest_raw, prefix + 'catalog.json': catalog_raw}
    for index, raw in shards.items(): payloads[prefix + 'month-' + format(index, '02d') + '-' + f.sha(raw) + '.jsonl'] = raw
    class Store:
        def __init__(self): self.calls = []; self.payloads = payloads
        def read_bytes(self, key): self.calls.append(key); return self.payloads[key]
        def save_bytes(self, *args): raise AssertionError('no ObjectStore writes')
        def contains_key(self, *args): raise AssertionError('no ObjectStore census')
    store = Store(); source.algorithm.object_store = store
    def reader(**changes):
        kwargs = dict(native_book=native_book, resolution=resolution, stock_bindings=rows,
            etf_symbols=tuple(source.etfs[ticker] for ticker in f.OWN_FUNDS), frozen_source_context=copy.deepcopy(context),
            expected_context_sha256=m.digest(context), frozen_runtime_project_id=40000001)
        kwargs.update(changes); return m.SpecificVendorPriceBook(source.algorithm, **kwargs)
    return NS(reader=reader, original=original, source=source, native=native_book, rows=rows, resolution=resolution, context=context,
        store=store, shards=shards, manifest=manifest, catalog=catalog, prefix=prefix, sessions=sessions)


def test_inert_constructor_concrete_authentication_and_actual_point_lookup(case):
    value = case.reader(); assert case.store.calls == []
    receipt = value.authenticate_once()
    assert len(case.store.calls) == 2 and receipt['fresh_resolution_sha256'] == case.resolution.resolution_sha256
    assert value.price(dict(case.rows[5]), case.sessions[0]) == Decimal('123.45')
    assert len(case.store.calls) == 3 and case.source.history.calls == []
    assert value.symbol_for_binding(dict(case.rows[5])) is case.resolution.symbol_for_security(case.rows[5]['security_id'])
    fund = {'schema': m.FUND_SCHEMA, 'ticker': 'SPY'}
    assert value.price(fund, case.sessions[0]) == Decimal('123.45')
    assert value.symbol_for_fund(fund) is case.source.etfs['SPY']
    assert all(receipt[key] is False for key in f.FALSE_FLAGS)


def test_manifest_hash_before_JSON_and_no_silent_pin_refresh(case, monkeypatch):
    case.store.payloads[case.prefix + 'manifest.json'] += b' '
    decoded = []
    def denied(*args, **kwargs): decoded.append(True); raise AssertionError('unpinned source decoded')
    monkeypatch.setattr(f, 'loads', denied)
    with pytest.raises(f.Refused): case.reader().authenticate_once()
    assert len(case.store.calls) == 1 and decoded == []


def test_genuine_resolution_native_join_refuses_before_ObjectStore(case):
    object.__setattr__(case.resolution, 'resolution_sha256', 'f' * 64)
    with pytest.raises(f.Refused): case.reader().authenticate_once()
    assert case.store.calls == []


def test_native_and_base_current_resolution_join_is_not_a_receipt_label_only(case):
    case.native._receipt['fresh_full_forward_reverse_resolution_sha256'] = 'f' * 64
    with pytest.raises(f.Refused): case.reader().authenticate_once()
    assert case.store.calls == []


def test_missing_cell_stops_without_other_source_quote_or_date_fallback(case):
    value = case.reader(); value.authenticate_once()
    with pytest.raises(f.Refused, match='missing'): value.price(dict(case.rows[5]), case.sessions[1])
    assert len(case.store.calls) == 3 and case.source.history.calls == []


def test_unknown_current_QC_identity_is_retained_then_stops_if_requested(case):
    case.source.unavailable.add(case.rows[5]['composite_figi'])
    case.source.algorithm.object_store = case.original.store
    native_book = case.original.reader(); native_book.authenticate_once()
    resolution = case.original.driver._resolve_with_census(case.rows)
    case.source.algorithm.object_store = case.store
    value = case.reader(native_book=native_book, resolution=resolution); value.authenticate_once()
    assert len(value._catalog['assignments']) == 15
    with pytest.raises(f.Refused, match='missing'): value.price(dict(case.rows[5]), case.sessions[0])
    assert len(case.store.calls) == 2


@pytest.mark.parametrize('ordinal', [0, 6])
def test_native_and_conditional_whole_assignments_never_use_vendor(case, ordinal):
    value = case.reader(); value.authenticate_once()
    with pytest.raises(f.Refused): value.price(dict(case.rows[ordinal]), case.sessions[0])
    assert len(case.store.calls) == 2


@pytest.mark.parametrize('hour,minute', [(9, 20), (15, 59)])
def test_same_day_EOD_before_actual_NYSE_close_refuses(case, hour, minute):
    value = case.reader(); value.authenticate_once(); case.source.algorithm.time = datetime(2020, 12, 31, hour, minute)
    with pytest.raises(f.Refused): value.price(dict(case.rows[5]), case.sessions[0])
    assert len(case.store.calls) == 2


def test_price_at_close_and_early_close_are_usable(case):
    value = case.reader(); value.authenticate_once()
    case.source.algorithm.time = datetime(2021, 11, 26, 12, 59)
    with pytest.raises(f.Refused): value.price(dict(case.rows[5]), case.sessions[2])
    case.source.algorithm.time = datetime(2021, 11, 26, 13, 0)
    assert value.price(dict(case.rows[5]), case.sessions[2]) == Decimal('123.45')


def test_current_USD_RAW_and_runtime_project_guards(case):
    value = case.reader(); value.authenticate_once(); symbol = value.symbol_for_binding(dict(case.rows[5]))
    case.source.algorithm.securities[symbol].quote_currency.conversion_rate = Decimal('2')
    with pytest.raises(f.Refused): value.price(dict(case.rows[5]), case.sessions[0])
    case.source.algorithm.securities[symbol].quote_currency.conversion_rate = Decimal('1')
    case.source.algorithm.securities[symbol].data_normalization_mode = 'Adjusted'
    with pytest.raises(f.Refused): value.price(dict(case.rows[5]), case.sessions[0])
    case.source.algorithm.project_id += 1
    with pytest.raises(f.Refused): value.receipt()


def test_same_SID_rename_on_current_security_keeps_vendor_price_identity(case):
    value=case.reader();value.authenticate_once();row=case.rows[5]
    symbol=case.source.symbols[row['composite_figi']]
    case.source.securities[symbol].symbol=fixture.fixture.Symbol('SYNTHETICMAPPED',str(symbol.id))
    assert value.price(dict(row),case.sessions[0])==Decimal('123.45')


@pytest.mark.parametrize('field',['sid','kind','market','sid_date','malformed_display'])
def test_vendor_rename_policy_never_waives_stable_identity_or_display_validation(case,field):
    value=case.reader();value.authenticate_once();row=case.rows[5]
    symbol=case.source.symbols[row['composite_figi']]
    changed=fixture.fixture.Symbol(symbol.value,str(symbol.id))
    if field=='sid':changed.id.text='CHANGED 123'
    elif field=='kind':changed.security_type='Option'
    elif field=='market':changed.id.market='canada'
    elif field=='sid_date':changed.id.date=datetime(2011,1,1)
    else:changed.value='malformed value'
    case.source.securities[symbol].symbol=changed
    with pytest.raises(f.Refused):value.price(dict(row),case.sessions[0])


def test_month_cache_is_bounded_and_month_identity_authenticated(case):
    value = case.reader(); value.authenticate_once()
    for session in case.sessions:
        value.price({'schema': m.FUND_SCHEMA, 'ticker': 'SPY'}, session)
        assert len(value._cache) <= 2
    assert list(value._cache) == [2, 3]
    key = case.prefix + 'month-00-' + case.manifest['months'][0]['sha256'] + '.jsonl'
    case.store.payloads[key] += b' '
    with pytest.raises(f.Refused): value.price(dict(case.rows[5]), case.sessions[0])


def test_no_orders_before_authentication_and_no_repeat(case):
    value = case.reader(); case.source.algorithm.transactions.get_orders = lambda: (object(),)
    with pytest.raises(f.Refused): value.authenticate_once()
    assert case.store.calls == []
    case.source.algorithm.transactions.get_orders = lambda: ()
    with pytest.raises(f.Refused): value.authenticate_once()


def test_authenticated_strategy_orders_are_not_a_later_blanket_reader_stop(case):
    value = case.reader(); value.authenticate_once()
    case.source.algorithm.transactions.get_orders = lambda: (object(),)
    assert value.price(dict(case.rows[5]), case.sessions[0]) == Decimal('123.45')


def test_context_closed_deepcopy_receipt_and_no_export(case):
    fresh = m.validate_source_context(case.context); fresh['manifest_pin']['sha256'] = 'f' * 64
    assert m.validate_source_context(case.context) == case.context
    bad = copy.deepcopy(case.context); bad['grant'] = True
    with pytest.raises(f.Refused): case.reader(frozen_source_context=bad)
    value = case.reader(); value.authenticate_once(); receipt = value.receipt(); receipt['source_rows'] = 0
    assert value.receipt()['source_rows'] == 35
    assert '123.45' not in repr(value)
    with pytest.raises(TypeError): pickle.dumps(value)


def test_same_closed_adapter_accepts_only_exact_System_byte_array_shape(case, monkeypatch):
    class ByteArray:
        Rank = 1
        def __init__(self, raw): self.raw = raw; self.Length = len(raw)
        def __bytes__(self): return self.raw
        def GetType(self): return NS(FullName='System.Byte[]')
    monkeypatch.setattr(m.native_reader.publication, '_SYSTEM_BYTE_ARRAY', ByteArray)
    case.store.payloads = {key: ByteArray(raw) for key, raw in case.store.payloads.items()}
    value = case.reader(); value.authenticate_once()
    assert value.price(dict(case.rows[5]), case.sessions[0]) == Decimal('123.45')
    case.store.payloads[case.prefix + 'manifest.json'].Rank = 2
    with pytest.raises(f.Refused): case.reader().authenticate_once()


def test_bounded_authentication_timeout_refuses_before_any_ObjectStore_read(case, monkeypatch):
    monkeypatch.setattr(m, 'MAX_AUTHENTICATION_SECONDS', -1)
    with pytest.raises(f.Refused): case.reader().authenticate_once()
    assert case.store.calls == []
