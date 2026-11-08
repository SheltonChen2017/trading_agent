"""Public projection and synthetic metadata-only feed adversaries, no QC/data."""
import ast
import copy
import dataclasses
from datetime import datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from scripts import arv2_r298_reference_feed_projection as m

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')


@pytest.fixture(scope='module')
def public():
    comparison = m.comparison
    research = ROOT / 'research/analyst_revisions_v2_qc'
    names = set(comparison.bridge.parent.SOURCE_PINS) | set(comparison.NEW_SOURCE_PINS) | {comparison.HOST_SOURCE_NAME}
    sources = {name: (research / name).read_bytes() for name in names}
    old = comparison.public_specification(sources=sources,
        expected_host_source_pins={comparison.HOST_SOURCE_NAME: m.sha(sources[comparison.HOST_SOURCE_NAME])})
    pairs = tuple((item.project_path, item.source_bytes) for item in old.cells[0].source_files)
    patcher = (ROOT / 'scripts' / m.PATCHER_NAME).read_bytes()
    projection = m.public_specification(pairs, patcher_source_bytes=patcher, expected_patcher_sha256=m.sha(patcher))
    return NS(pairs=pairs, patcher=patcher, projection=projection, files=dict(projection.source_pairs),
        profile=json.loads(projection.profile_bytes))


@pytest.fixture
def runtime():
    namespace = {}
    exec(compile(m._runtime(), 'synthetic feed runtime', 'exec'), namespace)
    return namespace


class Bar:
    def __init__(self, symbol, left, right, ff=False):
        self.symbol, self.time, self.end_time, self.is_fill_forward = symbol, left, right, ff

    def __getattr__(self, name):
        raise AssertionError('only metadata properties are allowed')


class Batch:
    def __init__(self, symbol, bar): self.time, self.entries = bar.end_time, [(symbol, bar)]
    def items(self): return iter(self.entries)


class History:
    def __init__(self, batches=()): self.batches, self.calls, self.failure = batches, [], None
    def __getitem__(self, kind):
        assert kind is Bar
        if self.failure == 'lookup': raise RuntimeError('synthetic lookup')
        def call(symbols, start, end, resolution, **kwargs):
            self.calls.append((symbols, start, end, resolution, kwargs))
            if self.failure == 'call': raise RuntimeError('synthetic call')
            return self.batches[resolution] if isinstance(self.batches, dict) else self.batches
        return call


def driver(runtime, public=None, history=None):
    profile = copy.deepcopy(public.profile) if public else {'schema': m.PROFILE_SCHEMA}
    profile['profile_sha256'] = runtime['digest']({key: value for key, value in profile.items() if key != 'profile_sha256'})
    algorithm = NS(live_mode=False, history=history or History(), time_zone='America/New_York',
        transactions=NS(get_orders=lambda: ()), portfolio={}, time=datetime(2022, 10, 24))
    value = runtime['ReferenceFeedDiagnostic'](algorithm, profile=profile,
        activation_manifest_key='synthetic-key', activation_manifest_sha256='a' * 64,
        activation_manifest_byte_count=1, benchmark_symbol='synthetic-benchmark', trade_bar_type=Bar,
        minute_resolution='minute', daily_resolution='daily', raw_normalization='RAW')
    runtime['sid'] = lambda value: value
    return value


def minute_batches(symbol='synthetic-native-SID', count=390, offset=0):
    opening = datetime(2022, 10, 21, 9, 30) + timedelta(seconds=offset)
    return [Batch(symbol, Bar(symbol, opening + timedelta(minutes=i),
        opening + timedelta(minutes=i + 1))) for i in range(count)]


def test_public_projection_is_pure_and_only_two_edits_relative_to_current_a19(public, monkeypatch):
    files, old = public.files, dict(public.pairs)
    preserved = m.identity_parent._legacy(m.identity_parent.parent._legacy(old['newrule_legacy_primitives.py']))
    assert m.sha(preserved) == m.A19_LEGACY and files['newrule_legacy_primitives.py'] == preserved
    assert all(files[name] == old[name] for name in old if name not in ('main.py', m.RUNTIME_NAME, 'newrule_legacy_primitives.py'))
    record, profile, pairs = m.validate_public_projection(public.projection.record_bytes, public.projection.source_pairs,
        expected_projection_sha256=public.projection.projection_sha256,
        expected_profile_sha256=public.profile['profile_sha256'])
    assert record == public.projection.to_record() and profile == public.profile and pairs == public.projection.source_pairs
    assert len(record['unchanged_cloud_files']) == 9 and record['unchanged_comparison_basis'] == 'current_A19_cloud_source'
    assert m.comparison.bridge.INPUT_NAME in record['unchanged_cloud_files']
    assert profile['profile_sha256'] == m.profile_digest(profile)
    def forbidden(*args, **kwargs): pytest.fail('pure builder performed IO')
    monkeypatch.setattr(Path, 'read_bytes', forbidden)
    monkeypatch.setattr(m.admission, 'admit', forbidden)
    assert m.public_specification(public.pairs, patcher_source_bytes=public.patcher,
        expected_patcher_sha256=m.sha(public.patcher)) == public.projection
    with pytest.raises(dataclasses.FrozenInstanceError): public.projection.record_bytes = b'changed'


def test_generated_main_exact_midnight_clock_no_scheduler_seed_or_explicit_spy_feed(public):
    source = public.files['main.py'].decode('ascii')
    assert 'set_start_date(2022, 10, 24)' in source and 'set_end_date(2022, 10, 24)' in source
    assert 'seed_initial_prices = False' in source
    assert "Symbol.create('SPY', SecurityType.EQUITY, Market.USA)" in source
    assert 'add_equity' not in source and 'schedule' not in source
    assert 'set_runtime_statistic' not in m.RUNTIME_SOURCE and 'set_summary_statistic' in m.RUNTIME_SOURCE
    tree = ast.parse(public.files[m.RUNTIME_NAME])
    forbidden = {'price', 'close', 'open', 'high', 'low', 'value', 'volume', 'market_order', 'set_holdings', 'liquidate'}
    assert not any(isinstance(node, ast.Attribute) and node.attr in forbidden for node in ast.walk(tree))
    assert all(len(raw) <= 64000 for raw in public.files.values())


def test_complete_exact_regular_grid_metadata_only(runtime):
    history = History(minute_batches())
    value = driver(runtime, history=history)
    row = value.observe('synthetic-native-SID', 'minute', datetime(2022, 10, 21, 9, 30), datetime(2022, 10, 21, 16), 390)
    assert row['status'] == 'complete' and row['items'] == row['batches'] == 390
    assert row['minute_grid_complete'] is True and row['valid_regular_minute_count'] == 390
    assert row['first_minute_endpoint_present'] is row['last_regular_endpoint_present'] is True
    symbols, start, end, resolution, kwargs = history.calls[0]
    assert symbols == ['synthetic-native-SID'] and resolution == 'minute'
    assert kwargs == {'fill_forward': False, 'extended_market_hours': False, 'data_normalization_mode': 'RAW'}


@pytest.mark.parametrize('mode', ['seconds', 'microseconds', 'duplicate', 'wrong_sid', 'fill_forward', 'wrong_batch', 'outside'])
def test_390_rows_never_imply_valid_grid_without_all_witnesses(runtime, mode):
    batches = minute_batches()
    if mode in ('seconds', 'microseconds'):
        shift = timedelta(seconds=1) if mode == 'seconds' else timedelta(microseconds=1)
        for batch in batches:
            bar = batch.entries[0][1]; bar.time += shift; bar.end_time += shift; batch.time = bar.end_time
    elif mode == 'duplicate': batches[1] = batches[0]
    elif mode == 'wrong_sid':
        for batch in batches: batch.entries[0][1].symbol = 'other-SID'
    elif mode == 'fill_forward':
        for batch in batches: batch.entries[0][1].is_fill_forward = True
    elif mode == 'wrong_batch':
        for batch in batches: batch.time += timedelta(minutes=1)
    else:
        for batch in batches:
            bar = batch.entries[0][1]; bar.time -= timedelta(days=1); bar.end_time -= timedelta(days=1); batch.time = bar.end_time
    value = driver(runtime, history=History(batches))
    row = value.observe('synthetic-native-SID', 'minute', datetime(2022, 10, 21, 9, 30), datetime(2022, 10, 21, 16), 390)
    assert row['items'] == 390 and row['minute_grid_complete'] is False
    if mode not in ('duplicate',):
        assert row['valid_regular_minute_count'] == 0
        assert row['first_minute_endpoint_present'] is row['last_regular_endpoint_present'] is False


@pytest.mark.parametrize('legacy', [False, True])
def test_daily_observes_both_timestamp_conventions_without_using_close(runtime, legacy):
    left = datetime(2022, 10, 21) if legacy else datetime(2022, 10, 21, 9, 30)
    right = datetime(2022, 10, 22) if legacy else datetime(2022, 10, 21, 16)
    value = driver(runtime, history=History([Batch('synthetic-native-SID', Bar('synthetic-native-SID', left, right))]))
    row = value.observe('synthetic-native-SID', 'daily', datetime(2022, 10, 21), datetime(2022, 10, 22), 1)
    assert row['status'] == 'complete' and row['valid_daily_bar_count'] == 1
    assert row['end_day']['after_reference' if legacy else 'exact_reference'] == 1
    assert row['period']['one_day' if legacy else 'regular_session'] == 1
    assert row['valid_regular_minute_count'] == 0 and row['minute_grid_complete'] is False


@pytest.mark.parametrize('mode,status,invoked', [('lookup', 'lookup_failed', False), ('call', 'call_failed', True),
    ('generator', 'read_failed', True), ('excess', 'bound_exceeded', True), ('empty', 'complete', True)])
def test_finite_partial_failure_and_explicit_request_accounting(runtime, mode, status, invoked):
    history = History()
    if mode in ('lookup', 'call'): history.failure = mode
    elif mode == 'generator':
        def broken():
            yield minute_batches(count=1)[0]
            raise RuntimeError('synthetic iterator failure')
        history.batches = broken()
    elif mode == 'excess': history.batches = minute_batches(count=391)
    value = driver(runtime, history=history)
    row = value.observe('synthetic-native-SID', 'minute', datetime(2022, 10, 21, 9, 30), datetime(2022, 10, 21, 16), 390)
    assert row['status'] == status and row['call_invoked'] is invoked
    assert row['items'] <= 390 and row['batches'] <= 390
    assert row['minute_grid_complete'] is False


def initialized(runtime, public, monkeypatch):
    daily = [Batch('synthetic-native-SID', Bar('synthetic-native-SID', datetime(2022, 10, 21, 9, 30), datetime(2022, 10, 21, 16)))]
    history = History({'daily': daily, 'minute': minute_batches()})
    value = driver(runtime, public, history)
    selected = {'security_id': 'synthetic-selected', 'source_row_sha256': m.SOURCE_ROW}
    rows = [{'security_id': 'synthetic-' + str(i)} for i in range(6150)] + [selected]
    runtime['WITNESS'] = runtime['digest']({'schema': 'arv2-missing-reference-identity-v1',
        'security_id': selected['security_id'], 'reference_session': '2022-10-21', 'decision_session': '2022-10-24'})
    runtime['BINDING_ROW'] = runtime['digest'](selected)
    loaded = NS(package_sha256=public.profile['package_sha256'], activation_manifest_sha256='a' * 64,
        evaluator_input=NS(session_axis=m.comparison.bridge.frozen.october._sessions(),
            source_lineage_sha256s=(('security_master_admission_sha256', 'b' * 64),)), runtime_symbol_bindings=rows)
    loaded_calls, resolved_calls, summaries = [], [], []
    def load(*args, **kwargs): loaded_calls.append(kwargs); return loaded
    def resolve(rows, **kwargs):
        resolved_calls.append((len(rows), kwargs))
        return NS(input_row_count=6151, resolved_count=5116, named_refusal_count=1035,
            symbol_for_security=lambda identity: 'synthetic-native-SID' if identity == 'synthetic-selected' else None)
    monkeypatch.setattr(runtime['inputs'], 'load_accepted_risk_preliminary_package', load)
    monkeypatch.setattr(runtime['figi'], 'resolve_preliminary_qc_figis', resolve)
    monkeypatch.setattr(runtime['figi'], '_input_row', lambda row, pin: dict(row))
    security = NS(symbol='synthetic-native-SID', data_normalization_mode=None,
        exchange=NS(hours=NS(time_zone='America/New_York')))
    security.set_data_normalization_mode = lambda mode: setattr(security, 'data_normalization_mode', mode)
    value.algorithm.add_security = lambda *args: security
    value.algorithm.composite_figi = lambda *args: pytest.fail('fake resolver must not call provider')
    value.algorithm.set_summary_statistic = lambda key, text: summaries.append((key, text))
    value.algorithm.set_runtime_statistic = lambda *args: pytest.fail('wrong statistic channel')
    return value, history, summaries, loaded_calls, resolved_calls


def receipt(runtime, public, monkeypatch):
    value, history, summaries, _, _ = initialized(runtime, public, monkeypatch)
    result = value.initialize()
    # The synthetic resolver/identity seam cannot produce the real witness
    # preimage; rebind only public hash fields to test the closed receiver.
    result['identity_sha256'] = m.WITNESS
    result['whole_binding_row_sha256'] = m.BINDING_ROW
    return result


def test_initialize_full_input_once_two_fixed_histories_and_one_summary(runtime, public, monkeypatch):
    value, history, summaries, loaded_calls, resolved_calls = initialized(runtime, public, monkeypatch)
    result = value.initialize()
    assert len(loaded_calls) == len(resolved_calls) == 1 and resolved_calls[0][0] == 6151
    assert len(history.calls) == 2
    assert history.calls[0][1:4] == (datetime(2022, 10, 21), datetime(2022, 10, 22), 'daily')
    assert history.calls[1][1:4] == (datetime(2022, 10, 21, 9, 30), datetime(2022, 10, 21, 16), 'minute')
    assert len(summaries) == 1 and summaries[0][0] == m.META_STATISTIC
    assert len(summaries[0][1]) <= 8192 and json.loads(summaries[0][1]) == result
    assert result['diagnostic_complete'] is True and result['minute']['minute_grid_complete'] is True
    assert all(result[key] is False for key in m.FALSE_FLAGS)
    value.on_end()
    with pytest.raises(RuntimeError, match='feed_once'): value.initialize()


def test_summary_receiver_accepts_only_bound_closed_diagnostic_not_strategy(runtime, public, monkeypatch):
    result = receipt(runtime, public, monkeypatch)
    statistics = {m.META_STATISTIC: m.canonical(result).decode('ascii')}
    assert m.validate_result_statistics(statistics, expected_profile=public.profile) == result
    assert result['diagnostic_complete'] is True
    assert all(result[key] is False for key in m.FALSE_FLAGS)
    assert len(statistics[m.META_STATISTIC]) <= 8192


@pytest.mark.parametrize('change', ['empty_endpoint', 'no_call_counts', 'wrong_zone', 'bool_alias',
    'calls', 'grid', 'daily_bad_sid', 'daily_bad_ff', 'items_without_batches',
    'daily_wrong_day', 'daily_wrong_endpoint', 'minute_wrong_session',
    'price', 'profile', 'unknown_field', 'malformed', 'oversized'])
def test_summary_receiver_rejects_forged_presence_false_flags_and_bounds(runtime, public, monkeypatch, change):
    result = receipt(runtime, public, monkeypatch)
    if change == 'empty_endpoint':
        result['minute']['valid_regular_minute_count'] = 0
        result['minute']['minute_grid_complete'] = False
    elif change == 'no_call_counts':
        result['minute']['call_invoked'] = False; result['minute']['status'] = 'lookup_failed'
        result['minute']['minute_grid_complete'] = False; result['explicit_history_calls'] = 1
    elif change == 'wrong_zone': result['subscription']['security_exchange_timezone_ny'] = False
    elif change == 'bool_alias': result['subscription']['raw'] = 1
    elif change == 'calls': result['explicit_history_calls'] = 3
    elif change == 'grid': result['minute']['valid_regular_minute_count'] = 389
    elif change == 'daily_bad_sid': result['daily']['sid_mismatch_count'] = 1
    elif change == 'daily_bad_ff': result['daily']['fill_forward_count'] = 1
    elif change == 'items_without_batches': result['daily']['batches'] = 0
    elif change == 'daily_wrong_day':
        result['daily']['time_day'] = {'before_reference': 1, 'exact_reference': 0, 'after_reference': 0}
    elif change == 'daily_wrong_endpoint':
        result['daily']['end_session']['at_close'] = 0; result['daily']['end_session']['before_open'] = 1
    elif change == 'minute_wrong_session':
        result['minute']['time_session'] = {'at_open': 0, 'inside_regular': 0, 'before_open': 390, 'at_close': 0, 'after_close': 0}
    elif change == 'price': result['price_used'] = True
    elif change == 'profile': result['profile_sha256'] = '0' * 64
    elif change == 'unknown_field': result['raw_ticker'] = 'SYNTHETIC'
    raw = m.canonical(result).decode('ascii')
    if change == 'malformed': raw += '\n'
    if change == 'oversized': raw = 'x' * 8193
    with pytest.raises(m.Refused):
        m.validate_result_statistics({m.META_STATISTIC: raw}, expected_profile=public.profile)


@pytest.mark.parametrize('zone', ['UTC', 'America/Chicago'])
def test_wrong_observed_algorithm_or_exchange_zone_refuses_before_history(runtime, public, monkeypatch, zone):
    value, history, _, _, _ = initialized(runtime, public, monkeypatch)
    value.algorithm.time_zone = zone
    with pytest.raises(RuntimeError, match='feed_subscription'): value.initialize()
    assert history.calls == []


@pytest.mark.parametrize('change,code', [('clock', 'feed_clock'), ('live', 'feed_live'), ('order', 'feed_orders'),
    ('witness', 'feed_witness'), ('source_row', 'feed_witness'), ('binding', 'feed_witness')])
def test_initialize_safety_and_source_stops_before_history(runtime, public, monkeypatch, change, code):
    value, history, summaries, _, _ = initialized(runtime, public, monkeypatch)
    if change == 'clock': value.algorithm.time += timedelta(minutes=1)
    elif change == 'live': value.algorithm.live_mode = True
    elif change == 'order': value.algorithm.transactions.get_orders = lambda: ('synthetic-order',)
    elif change == 'witness': runtime['WITNESS'] = '0' * 64
    elif change == 'source_row': runtime['SOURCE_ROW'] = '0' * 64
    else: runtime['BINDING_ROW'] = '0' * 64
    with pytest.raises(RuntimeError, match=code): value.initialize()
    assert history.calls == [] and summaries == []


@pytest.mark.parametrize('change', ['main', 'runtime', 'other', 'profile', 'record'])
def test_public_packet_pin_and_schema_tampering_refuse(public, change):
    raw, pairs = public.projection.record_bytes, list(public.projection.source_pairs)
    if change in ('main', 'runtime', 'other'):
        name = 'main.py' if change == 'main' else m.RUNTIME_NAME if change == 'runtime' else m.comparison.bridge.INPUT_NAME
        pairs = tuple((key, value + b'\n' if key == name else value) for key, value in pairs)
    elif change == 'record': raw += b'\n'
    with pytest.raises(m.Refused):
        m.validate_public_projection(raw, tuple(pairs), expected_projection_sha256=public.projection.projection_sha256,
            expected_profile_sha256='0' * 64 if change == 'profile' else public.profile['profile_sha256'])
