"""Small supplied-data codec fixtures; no source corpus or operational reads."""
import copy
import pickle
import time
from types import SimpleNamespace as NS

import pytest

from scripts import arv2_r298_common_price_sidecar as m
from research.analyst_revisions_v2_qc import newrule_common_price_format as f


@pytest.fixture
def case(monkeypatch):
    for name, value in {'STOCK_COUNT': 3, 'FUND_COUNT': 1, 'VENDOR_COUNT': 1, 'NATIVE_COUNT': 1,
            'CONDITIONAL_COUNT': 1, 'SESSION_COUNT': 3, 'MONTH_COUNT': 2, 'LAST': '2021-01-05', 'OWN_FUNDS': ('SPY',),
            'OBSERVED_ROWS': 5, 'ABSENT_CELLS': 1}.items():
        monkeypatch.setattr(f, name, value)
    monkeypatch.setattr(m, 'REQUEST_COUNT', 2); monkeypatch.setattr(m, 'OBSERVED_ROWS', 5); monkeypatch.setattr(m, 'ABSENT_CELLS', 1)
    sessions = ['2020-12-31', '2021-01-04', '2021-01-05']
    assignments = []
    for ordinal, role in enumerate((f.VENDOR, f.NATIVE, f.CONDITIONAL)):
        assignments.append({'binding_ordinal': ordinal, 'security_id': 'synthetic-' + str(ordinal),
            'whole_binding_sha256': m.digest({'synthetic_whole': ordinal}),
            'semantic_binding_sha256': m.digest({'synthetic_semantic': ordinal}), 'role': role,
            'table': 'stocks' if role == f.VENDOR else None, 'ticker': 'AAA' if role == f.VENDOR else None,
            'refusal_reason': None if role == f.VENDOR else 'identity_missing' if role == f.NATIVE else None})
    assignments.append({'fund_ordinal': 0, 'own_ETF': 'SPY', 'role': f.VENDOR, 'table': 'funds', 'ticker': 'SPY', 'route_sha256': 'e' * 64})
    requests = []
    for ordinal, (table, ticker, window) in enumerate((('stocks', 'AAA', m.prices.STOCK_WINDOWS[0]), ('funds', 'SPY', m.prices.FUND_WINDOWS[0]))):
        requests.append({'ordinal': ordinal, 'table': table, 'tickers': [ticker], 'first': window[0], 'last': window[1],
            'calendar_key_bound': 1462, 'parameters': m.prices._parameters([ticker], window)})
    plan = {'schema': m.prices.PLAN_PRIVATE_SCHEMA, 'ac_summary_sha256': 'a' * 64,
        'ac_frame_pin': {'byte_count': 1, 'sha256': 'b' * 64}, 'native_specification_sha256': 'c' * 64,
        'full_axis_sha256': f.FULL_AXIS_SHA256, 'price_sessions': sessions, 'assignments': assignments, 'requests': requests}
    raw = m.canonical(plan)
    summary = {'assignment_inventory_sha256': m.digest(assignments), 'request_inventory_sha256': m.digest(requests)}
    source = {'plan_pin': m.pin(raw), 'plan_summary': summary}
    auth = {'request_count': 2}
    pins = {role: {'byte_count': 1, 'sha256': m.sha(role.encode())} for role in ('corpus', 'dispatch', 'captures')}
    pins['plan'] = m.pin(raw)
    fact = {'data_plan': {role: {**pin, 'relative_path': 'synthetic/' + role} for role, pin in pins.items()}}
    for name, value in (('AP_FACT_SHA256', m.digest(fact)), ('AP_SOURCE_SHA256', m.digest(source)),
            ('AP_AUTH_SHA256', m.digest(auth)), ('AP_DATA_PINS', pins)):
        monkeypatch.setattr(f, name, value)
    def validate_summary(value):
        assert value == summary
        return copy.deepcopy(value)
    monkeypatch.setattr(m.prices, 'validate_plan_summary', validate_summary)
    context = {'fact': fact, 'source_summary': source, 'authentication_summary': auth}
    def layout(): return m.make_layout(raw, expected_plan_summary=summary, frozen_AP_context=context)[1]
    stock = b'ticker,date,closeunadj,lastupdated\nAAA,2020-12-31,10.00,2026-10-14\nAAA,2021-01-05,12,2026-10-14\n'
    fund = b'ticker,date,closeunadj,lastupdated\nSPY,2020-12-31,100,2026-10-14\nSPY,2021-01-04,101,2026-10-14\nSPY,2021-01-05,102,2026-10-14\n'
    def complete():
        value = layout(); buckets = {0: b'', 1: b''}
        for ordinal, body in ((1, fund), (0, stock)):
            for month, fragment in m.split_response(value, ordinal, body): buckets[month] += fragment
        completed = [m.finalize_month(value, month, buckets[month]) for month in range(2)]
        summary, manifest = m.finish_manifest(value, [row[0] for row in completed])
        return value, completed, summary, manifest
    return NS(raw=raw, context=context, summary=summary, plan=plan, layout=layout,
        stock=stock, fund=fund, complete=complete)


def test_small_full_pipeline_retains_all_assignments_and_explicit_null_grid(case):
    layout, completed, summary, manifest = case.complete()
    assert layout.catalog_record()['vendor_slots'] == [0, 3]
    assert len(layout.catalog_record()['assignments']) == 4
    assert summary['row_count'] == 6 and summary['valid_count'] == 5 and summary['absent_count'] == 1
    assert f.validate_manifest(f.loads(manifest.bytes(), f.MAX_MANIFEST_BYTES))['catalog_pin'] == layout.catalog_pin()
    assert f.validate_shard(completed[1][1].bytes(), catalog=layout.catalog_record(), summary=completed[1][0]) == (None, '12', '101', '102')
    assert b'10.00' not in completed[0][1].bytes() and b'"10"' in completed[0][1].bytes()
    assert all(summary[key] is False for key in f.FALSE_FLAGS)


@pytest.mark.parametrize('field', ['fact', 'source_summary', 'authentication_summary'])
def test_context_mismatch_refuses_before_plan_decode(case, field, monkeypatch):
    bad = copy.deepcopy(case.context); bad[field]['unexpected'] = True
    def denied(*args, **kwargs): raise AssertionError('plan decoded before context pins')
    monkeypatch.setattr(f, 'loads', denied)
    with pytest.raises(f.Refused): m.make_layout(case.raw, expected_plan_summary=case.summary, frozen_AP_context=bad)


def test_plan_byte_pin_refuses_before_JSON(case, monkeypatch):
    def denied(*args, **kwargs): raise AssertionError('unpinned plan parsed')
    monkeypatch.setattr(f, 'loads', denied)
    with pytest.raises(f.Refused): m.make_layout(case.raw + b' ', expected_plan_summary=case.summary, frozen_AP_context=case.context)


def test_duplicate_request_and_missing_request_refuse(case):
    layout = case.layout(); m.split_response(layout, 0, case.stock)
    with pytest.raises(f.Refused): m.split_response(layout, 0, case.stock)
    with pytest.raises(f.Refused): m.finish_manifest(layout, [])


@pytest.mark.parametrize('fragment', [b'[0,0,"1"]\n[0,0,"2"]\n', b'[1,0,"1"]\n', b'[0,2,"1"]\n', b'[0,0,null]\n', b'[0,0,"NaN"]\n'])
def test_duplicate_wrong_source_wrong_month_or_nonprice_fragment_refuses(case, fragment):
    with pytest.raises(f.Refused): m.finalize_month(case.layout(), 0, fragment)


@pytest.mark.parametrize('text', ['0', '-1', '01', '1.0', '1e2', 'NaN', 'Infinity', '+1', ' 1', '1.'])
def test_noncanonical_or_nonpositive_prices_refuse(text):
    with pytest.raises(f.Refused): f.price_text(text)


def test_mutated_derived_route_map_is_detected(case):
    layout = case.layout(); layout._identity[('stocks', 'AAA')] = 3
    with pytest.raises(f.Refused): m.split_response(layout, 0, case.stock)


def test_month_hash_authenticates_before_any_grid_decode(case, monkeypatch):
    layout, completed, _, _ = case.complete()
    def denied(*args, **kwargs): raise AssertionError('grid decoded before byte pin')
    monkeypatch.setattr(f, 'loads', denied)
    with pytest.raises(f.Refused): f.validate_shard(completed[0][1].bytes() + b' ', catalog=layout.catalog_record(), summary=completed[0][0])


def test_wrong_grid_order_even_rehashed_refuses(case):
    layout, completed, _, _ = case.complete(); raw = b''.join(reversed(completed[0][1].bytes().splitlines(keepends=True)))
    summary = {**completed[0][0], **m.pin(raw)}
    with pytest.raises(f.Refused): f.validate_shard(raw, catalog=layout.catalog_record(), summary=summary)


def test_explicit_bounds_deadline_and_private_repr(case, monkeypatch):
    with pytest.raises(f.Refused): m.make_layout(case.raw, expected_plan_summary=case.summary, frozen_AP_context=case.context, deadline=time.monotonic() - 1)
    layout = case.layout(); monkeypatch.setattr(f, 'MAX_MONTH_BYTES', 1)
    with pytest.raises(f.Refused): m.finalize_month(layout, 0, b'')
    assert 'AAA' not in repr(layout)
    with pytest.raises(TypeError): pickle.dumps(layout)


def test_catalog_and_manifest_closed_shapes_and_all_roles_retained(case):
    layout, _, _, private = case.complete(); catalog = layout.catalog_record()
    for mutate in (lambda x: x.update(extra=True), lambda x: x['assignments'][1].update(role=f.VENDOR),
            lambda x: x['assignments'][0].update(binding_ordinal=True), lambda x: x['vendor_slots'].append(1)):
        value = copy.deepcopy(catalog); mutate(value)
        with pytest.raises(f.Refused): f.validate_catalog(value)
    manifest = f.loads(private.bytes(), f.MAX_MANIFEST_BYTES); manifest['months'].reverse()
    with pytest.raises(f.Refused): f.validate_manifest(manifest)
