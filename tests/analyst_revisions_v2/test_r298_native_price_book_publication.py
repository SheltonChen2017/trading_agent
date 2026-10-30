"""Synthetic QC-local retention only; no cloud, private artifacts or datasets."""
import ast
import builtins
import copy
import hashlib
import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from research.analyst_revisions_v2_qc import newrule_native_price_book_publication as m
from tests.analyst_revisions_v2 import test_r298_native_price_source_diagnostic as source_fixture


class MemoryStore:
    def __init__(self):
        self.data, self.calls = {}, []
        self.lookup_result, self.save_result = False, True
        self.fail, self.read_mode, self.after = None, 'bytes', None

    def contains_key(self, key):
        self.calls.append(('contains_key', key))
        if self.fail == 'lookup':
            raise RuntimeError('SYNTHETIC PRIVATE LOOKUP ERROR')
        return self.lookup_result

    def save_bytes(self, key, raw):
        self.calls.append(('save_bytes', key))
        assert type(raw) is bytes
        self.data[key] = raw  # A refused/unknown save can still have a partial object.
        if self.after:
            self.after('save')
        if self.fail == 'save':
            raise RuntimeError('SYNTHETIC PRIVATE SAVE ERROR')
        return self.save_result

    def read_bytes(self, key):
        self.calls.append(('read_bytes', key))
        if self.after:
            self.after('read')
        if self.fail == 'read':
            raise RuntimeError('SYNTHETIC PRIVATE READ ERROR')
        raw = self.data[key]
        if self.read_mode == 'mismatch':
            return b'x' * len(raw)
        if self.read_mode == 'short':
            return raw[:-1]
        if self.read_mode == 'bytearray':
            return bytearray(raw)
        if self.read_mode == 'none':
            return None
        return raw


@pytest.fixture
def case(monkeypatch):
    source = source_fixture.scenario.__wrapped__(monkeypatch)
    source.algorithm.project_id = 38364439
    store = MemoryStore()
    source.algorithm.object_store = store
    summary, book = source.driver().prepare()
    scope = m.make_scope(source.algorithm.project_id, m.digest(source.spec), 'SYNTHETIC-A1')

    def publisher(scope_override=None, spec_override=None):
        selected = scope if scope_override is None else scope_override
        return m.SpecificSourceBookNamespace(source.algorithm, frozen_scope=selected,
            expected_scope_sha256=m.digest(selected),
            expected_specification=source.spec if spec_override is None else spec_override)
    return NS(source=source, store=store, summary=summary, book=book, scope=scope, publisher=publisher)


def refused(code, operation):
    with pytest.raises(m.Refused) as caught:
        operation()
    assert m.finite(caught.value) == code
    assert 'PRIVATE' not in str(caught.value)


def altered(case, change):
    record = json.loads(object.__getattribute__(case.book, '_raw'))
    change(record)
    book = m.native.PrivateNativeBook(record)
    summary = copy.deepcopy(case.summary)
    summary['private_book_byte_count'], summary['private_book_sha256'] = book.byte_count, book.sha256
    return summary, book


def test_one_fixed_project_content_key_exact_save_readback_and_metadata_only(case, monkeypatch):
    publisher = case.publisher()
    def deny(*args, **kwargs):
        raise AssertionError('QC-local retention tried host filesystem access')
    with monkeypatch.context() as patch:
        for module, name in ((builtins, 'open'), (os, 'open'), (os, 'read'),
                (Path, 'read_bytes'), (Path, 'read_text')):
            patch.setattr(module, name, deny)
        receipt = publisher.publish(case.summary, case.book)
    key = '38364439/arv2/r326-native/' + m.digest(case.scope) + '/' + case.book.sha256
    assert [name for name, _ in case.store.calls] == ['contains_key', 'save_bytes', 'read_bytes']
    assert all(value == key for _, value in case.store.calls)
    assert case.store.data[key] == object.__getattribute__(case.book, '_raw')
    assert receipt['object_key'] == key and receipt['book_sha256'] == case.book.sha256
    assert receipt['book_byte_count'] == case.book.byte_count
    assert receipt['source_summary_sha256'] == m.digest(case.summary)
    assert receipt['publication_API_checks_complete'] is True and receipt['attempt_consumed'] is True
    assert m.validate_receipt(receipt, frozen_scope=case.scope,
        expected_specification=case.source.spec, expected_summary=case.summary) == receipt
    assert all(receipt[key] is False for key in m.FALSE_FLAGS)
    assert b'123.45' not in m.canonical(receipt) and b'SYNTH0' not in m.canonical(receipt)
    assert 'cache' in m.profile_record()['readback']
    assert receipt['independent_remote_durability_proven'] is False
    refused('once', lambda: publisher.publish(case.summary, case.book))
    assert len(case.store.calls) == 3


@pytest.mark.parametrize('field,value', [('own_project_id', True), ('own_project_id', 0),
    ('own_project_id', -1), ('own_project_id', '38364439'),
    ('run_scope_tag', '../other'), ('run_scope_tag', 'x/y'), ('run_scope_tag', ''),
    ('run_scope_tag', 'x' * 65), ('protocol_source_profile_sha256', 'f' * 64),
    ('source_specification_sha256', 'f' * 64), ('extra_authority', True)])
def test_scope_rejects_arbitrary_namespace_and_authority_fields_before_store(case, field, value):
    scope = copy.deepcopy(case.scope); scope[field] = value
    refused('scope', lambda: case.publisher(scope))
    assert case.store.calls == []


@pytest.mark.parametrize('mode', ['project', 'project_bool', 'live', 'orders', 'holding'])
def test_actual_project_live_orders_and_positions_are_checked_before_any_store_call(case, mode):
    if mode == 'project':
        case.source.algorithm.project_id += 1
    elif mode == 'project_bool':
        case.source.algorithm.project_id = True
    elif mode == 'live':
        case.source.algorithm.live_mode = True
    elif mode == 'orders':
        case.source.algorithm.transactions.get_orders = lambda: [NS()]
    else:
        case.source.algorithm.portfolio = {'synthetic': NS(quantity=1)}
    refused('project' if mode.startswith('project') else 'orders', case.publisher)
    assert case.store.calls == []


def test_existing_identical_object_is_neither_read_nor_overwritten_and_attempt_is_spent(case):
    publisher = case.publisher()
    key = str(case.source.algorithm.project_id) + '/arv2/r326-native/' + m.digest(case.scope) + '/' + case.book.sha256
    case.store.data[key] = object.__getattribute__(case.book, '_raw')
    case.store.lookup_result = True
    refused('store_key_exists', lambda: publisher.publish(case.summary, case.book))
    assert case.store.calls == [('contains_key', key)]
    receipt = publisher.attempt_record()
    assert receipt['attempt_consumed'] is True and receipt['known_absent_observed'] is False
    assert receipt['publication_API_checks_complete'] is False
    refused('once', lambda: publisher.publish(case.summary, case.book))


@pytest.mark.parametrize('mode,code', [('lookup_exception', 'store_lookup_unknown'),
    ('lookup_unknown', 'store_lookup_unknown'), ('lookup_int', 'store_lookup_unknown'),
    ('save_false', 'store_save_false'), ('save_unknown', 'store_save_unknown'),
    ('save_int', 'store_save_unknown'), ('save_exception', 'store_save_unknown'),
    ('read_exception', 'store_read_unknown'), ('read_none', 'store_read_unknown'),
    ('read_bytearray', 'store_read_unknown'), ('read_mismatch', 'store_read_mismatch'),
    ('read_short', 'store_read_mismatch')])
def test_false_unknown_exception_or_mismatched_store_results_are_terminal_no_cleanup(case, mode, code):
    if mode.endswith('_exception'):
        case.store.fail = mode.split('_')[0]
    elif mode == 'lookup_unknown': case.store.lookup_result = None
    elif mode == 'lookup_int': case.store.lookup_result = 0
    elif mode == 'save_false': case.store.save_result = False
    elif mode == 'save_unknown': case.store.save_result = None
    elif mode == 'save_int': case.store.save_result = 1
    elif mode.startswith('read_'): case.store.read_mode = mode[5:]
    publisher = case.publisher()
    refused(code, lambda: publisher.publish(case.summary, case.book))
    record = publisher.attempt_record()
    assert record['failure_code'] == code and record['attempt_consumed'] is True
    assert record['publication_API_checks_complete'] is False
    assert b'PRIVATE' not in m.canonical(record)
    assert all(name in ('contains_key', 'save_bytes', 'read_bytes') for name, _ in case.store.calls)
    if mode.startswith(('save_', 'read_')):
        assert record['object_key'] in case.store.data  # Partial object is retained.
    refused('once', lambda: publisher.publish(case.summary, case.book))


@pytest.mark.parametrize('mode', ['summary', 'book_type', 'subclass', 'bytes', 'declared_size'])
def test_wrong_summary_or_opaque_type_or_bytes_is_refused_without_store_probe(case, mode):
    publisher, summary, book = case.publisher(), copy.deepcopy(case.summary), case.book
    if mode == 'summary': summary['point_in_time_proven'] = True
    elif mode == 'book_type': book = {'raw': 'not a book'}
    elif mode == 'subclass':
        class Subclass(m.native.PrivateNativeBook): pass
        book = Subclass(json.loads(object.__getattribute__(book, '_raw')))
    elif mode == 'bytes': object.__setattr__(book, '_raw', b'changed')
    else: object.__setattr__(book, 'byte_count', True)
    refused('summary' if mode == 'summary' else 'book_type' if mode in ('book_type', 'subclass') else 'book_bytes',
        lambda: publisher.publish(summary, book))
    assert case.store.calls == [] and publisher.attempt_record()['attempt_consumed'] is True


@pytest.mark.parametrize('mode,code', [('scope', 'book_metadata'), ('package', 'book_metadata'),
    ('schedule', 'book_metadata'), ('binding', 'book_rows'), ('native', 'book_rows'), ('sid_date', 'book_rows'),
    ('status', 'book_rows'), ('price', 'book_rows'), ('duplicate_cell', 'book_rows'),
    ('census_ordinal', 'census'), ('census_state', 'census'), ('census_extra', 'census')])
def test_rehashed_forged_private_record_still_requires_exact_metadata_rows_and_census(case, mode, code):
    def change(record):
        if mode == 'scope': record['specification_sha256'] = 'f' * 64
        elif mode == 'package': record['package_sha256'] = 'f' * 64
        elif mode == 'schedule': record['session_schedule'][-1]['close_utc'] = '2026-10-13T21:00:00+00:00'
        elif mode == 'binding': record['selected'][-1]['original_binding']['diagnostic_current_ticker'] = 'CHANGED'
        elif mode == 'native': record['selected'][-1]['native']['sid'] = 'OTHER 123'
        elif mode == 'sid_date': record['selected'][-1]['native']['sid_date'] = '2020-99-99'
        elif mode == 'status': record['selected'][-1]['status'] = 'lookup_failed'
        elif mode == 'price': record['selected'][-1]['raw_USD_closes'][-1][1] = '-1'
        elif mode == 'duplicate_cell': record['selected'][-1]['raw_USD_closes'][-1][0] = 0
        elif mode == 'census_ordinal': record['forward_sid_census'][-1]['binding_ordinal'] = 0
        elif mode == 'census_state': record['forward_sid_census'][-1]['state'] = 'unknown-ignored'
        else: record['forward_sid_census'][-1]['new_authority'] = True
    summary, book = altered(case, change)
    refused(code, lambda: case.publisher().publish(summary, book))
    assert case.store.calls == []


@pytest.mark.parametrize('raw', [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1.5}',
    b'{"x":"raw-non-ascii-\xff"}', b'[' * 20 + b'0' + b']' * 20])
def test_even_rehashed_opaque_bytes_cannot_bypass_closed_json_policy(case, raw):
    book = m.native.PrivateNativeBook({})
    object.__setattr__(book, '_raw', raw)
    object.__setattr__(book, 'byte_count', len(raw))
    object.__setattr__(book, 'sha256', hashlib.sha256(raw).hexdigest())
    summary = copy.deepcopy(case.summary)
    summary['private_book_byte_count'], summary['private_book_sha256'] = book.byte_count, book.sha256
    refused('book_bytes', lambda: case.publisher().publish(summary, book))
    assert case.store.calls == []


@pytest.mark.parametrize('mode', ['missing', 'identity_refused'])
def test_valid_incomplete_or_identity_refused_book_is_retained_only_as_private_evidence(case, mode):
    if mode == 'missing':
        case.source.history.mutate = lambda symbol, batches: batches[1:]
    else:
        case.source.symbols[case.source.rows[-1]['composite_figi']].id.text = str(case.source.etfs['SPY'].id)
    summary, book = case.source.driver().prepare()
    receipt = case.publisher().publish(summary, book)
    assert summary['unpriced_cell_count'] > 0 and receipt['publication_API_checks_complete'] is True
    assert receipt['price_input_admitted'] is receipt['price_coverage_proven'] is False
    if mode == 'identity_refused':
        assert summary['identity_phase'] == 'refused' and summary['explicit_history_calls'] == 0
    else:
        assert summary['identity_phase'] == 'observed'


@pytest.mark.parametrize('stage,mode,code', [('save', 'project', 'project'), ('save', 'live', 'orders'),
    ('read', 'holding', 'orders'), ('read', 'summary', 'source_changed'),
    ('read', 'book', 'book_bytes'), ('save', 'deadline', 'deadline')])
def test_drift_or_late_failure_after_save_keeps_object_but_never_returns_admissible_receipt(case, stage, mode, code):
    publisher = case.publisher()
    def after(actual_stage):
        if actual_stage != stage: return
        if mode == 'project': case.source.algorithm.project_id += 1
        elif mode == 'live': case.source.algorithm.live_mode = True
        elif mode == 'holding': case.source.algorithm.portfolio = {'synthetic': NS(quantity=1)}
        elif mode == 'summary': case.summary['resolution_sha256'] = 'f' * 64
        elif mode == 'book': object.__setattr__(case.book, '_raw', b'changed')
        else: publisher._deadline = 0
    case.store.after = after
    refused(code, lambda: publisher.publish(case.summary, case.book))
    record = publisher.attempt_record()
    assert record['object_key'] in case.store.data and record['publication_API_checks_complete'] is False
    refused('once', lambda: publisher.publish(case.summary, case.book))


def test_unknown_iterable_is_not_coerced_and_only_exact_bound_NET_array_uses_conversion(case, monkeypatch):
    class Untrusted:
        touched = False
        def GetType(self): return NS(FullName='System.Byte[]')
        def __bytes__(self): self.touched = True; raise AssertionError('untrusted conversion')
    unknown = Untrusted()
    refused('store_read_unknown', lambda: m._read_bytes(unknown, case.book.byte_count))
    assert unknown.touched is False
    class SyntheticArray:
        Rank = 1
        def __init__(self, raw): self.raw, self.Length = raw, len(raw)
        def GetType(self): return NS(FullName='System.Byte[]')
        def __bytes__(self): return self.raw
    monkeypatch.setattr(m, '_SYSTEM_BYTE_ARRAY', SyntheticArray)
    raw = object.__getattribute__(case.book, '_raw')
    assert m._read_bytes(SyntheticArray(raw), len(raw)) == raw
    invalid = SyntheticArray(raw); invalid.Rank = 2
    refused('store_read_mismatch', lambda: m._read_bytes(invalid, len(raw)))
    invalid = SyntheticArray(raw); invalid.Length = len(raw) + 1
    refused('store_read_mismatch', lambda: m._read_bytes(invalid, len(raw)))


def test_source_scope_copy_isolation_and_pure_receipt_validation_never_grant_rights(case):
    scope = copy.deepcopy(case.scope)
    publisher = case.publisher(scope)
    scope['own_project_id'] = 1
    receipt = publisher.publish(case.summary, case.book)
    snapshot = publisher.attempt_record()
    snapshot['object_key'] = 'synthetic/elsewhere'; snapshot['publication_API_checks_complete'] = False
    assert publisher.attempt_record() == receipt
    for key, value in (('independent_remote_durability_proven', True), ('book_sha256', 'f' * 64),
            ('object_key', 'other/path'), ('save_returned_true', 1), ('extra_authority', True)):
        changed = copy.deepcopy(receipt); changed[key] = value
        refused('receipt', lambda: m.validate_receipt(changed, frozen_scope=case.scope,
            expected_specification=case.source.spec, expected_summary=case.summary))
    assert 'atomic' in m.profile_record()['creation']


def test_attempt_record_is_closed_bounded_failure_metadata_and_does_not_claim_success(case):
    publisher = case.publisher()
    before = publisher.attempt_record()
    assert before['attempt_consumed'] is False and before['phase'] == 'not_started'
    assert before['object_key'] is before['failure_code'] is None
    case.store.fail = 'save'
    refused('store_save_unknown', lambda: publisher.publish(case.summary, case.book))
    record = publisher.attempt_record()
    assert record['phase'] == 'save' and record['save_returned_true'] is None
    assert record['object_key'] in case.store.data and record['publication_API_checks_complete'] is False
    assert m.validate_attempt_record(record, frozen_scope=case.scope,
        expected_specification=case.source.spec, expected_summary=case.summary) == record
    for name, value in (('object_key', 'other/project/raw-data'), ('failure_code', 'PRIVATE-EXCEPTION'),
            ('publication_API_checks_complete', True), ('extra', 'PRIVATE-DATA')):
        changed = copy.deepcopy(record); changed[name] = value
        refused('receipt', lambda: m.validate_attempt_record(changed, frozen_scope=case.scope,
            expected_specification=case.source.spec))
    refused('receipt', lambda: m.validate_receipt(record, frozen_scope=case.scope,
        expected_specification=case.source.spec, expected_summary=case.summary))


def test_expired_before_first_probe_still_spends_instance_without_any_store_call(case, monkeypatch):
    publisher = case.publisher()
    ticks = iter((0, m.MAX_SECONDS + 1))
    monkeypatch.setattr(m.time, 'monotonic', lambda: next(ticks))
    refused('deadline', lambda: publisher.publish(case.summary, case.book))
    assert case.store.calls == []
    assert publisher.attempt_record()['attempt_consumed'] is True
    refused('once', lambda: publisher.publish(case.summary, case.book))


def test_production_source_has_no_export_cleanup_path_or_arbitrary_transport_callbacks():
    tree = ast.parse(inspect.getsource(m))
    calls = {node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Name, ast.Attribute))}
    assert not calls & {'open', 'print', 'debug', 'log', 'error', 'download', 'request', 'post',
        'delete', 'clear', 'get_file_path', 'GetFilePath', 'save', 'write', 'write_bytes', 'read_text'}
    assert {'contains_key', 'save_bytes', 'read_bytes'} <= calls
    params = list(inspect.signature(m.SpecificSourceBookNamespace.publish).parameters)
    assert params == ['self', 'summary', 'book']
    assert not hasattr(m.SpecificSourceBookNamespace, 'read_raw')
    assert not any(isinstance(node, ast.ImportFrom) and node.module == '__future__' for node in tree.body)
