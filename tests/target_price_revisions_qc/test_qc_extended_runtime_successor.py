"""Synthetic native engine identity timing; no account/provider/state I/O."""
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import sys
from types import ModuleType
from types import SimpleNamespace

import pytest
from tests.target_price_revisions_qc.test_qc_extended_runtime import runtime


@pytest.fixture(autouse=True)
def no_actual_calls(monkeypatch):
    from research.target_price_revisions_qc import extended_operations as ops
    def denied(*_a, **_kw): raise AssertionError('actual filesystem, credential, provider or QC access forbidden')
    monkeypatch.setattr(ops, 'credential', denied)
    monkeypatch.setattr(ops.http.client, 'HTTPSConnection', denied)
    monkeypatch.setattr(ops.Operations, '__init__', denied)
    monkeypatch.setattr(ops.subprocess, 'run', denied)
    monkeypatch.setattr(os, 'open', denied)


def binding(core):
    return {'candidate_id': core.CANDIDATES['tpr_off'], 'config_sha256': 'a' * 64,
        'freeze_sha256': core.FREEZE_SHA256, 'input_hashes': {'calendar.json': core.CALENDAR_SHA256}, 'attempt': 1}


@pytest.fixture
def successor(runtime):
    module = ModuleType('extended_runtime_successor')
    source = Path('research/target_price_revisions_qc/extended_runtime_successor.py').read_bytes()
    exec(compile(source, 'extended_runtime_successor.py', 'exec'), module.__dict__)
    return module


def native_state(project=123, job='', locked=False):
    state = SimpleNamespace(project_id=project, algorithm_id=job, locked=locked)
    getter = lambda: (state.project_id, state.algorithm_id, state.locked)
    return state, getter


class Store:
    def __init__(self): self.values, self.calls = {}, []
    def contains_key(self, key): self.calls.append(('contains', key)); return key in self.values
    def save(self, key, value): self.calls.append(('save', key)); self.values[key] = value; return True
    def read(self, key): self.calls.append(('read', key)); return self.values[key]


def test_native_initialize_empty_job_then_native_locked_identity_preserves_records(runtime, successor):
    native, getter = native_state()
    journal = successor.DeferredPrivateEvidence(binding(runtime.core), getter)
    journal.append('SUBSCRIPTION', {'initialization_record': True, 'exact': Fraction(1, 3)})
    pending = journal.records
    assert journal.prefix is journal.binding['job_id'] is None and not journal.closed
    native.algorithm_id, native.locked = 'native-job', True
    assert journal.require_binding().endswith('/123/native-job/')
    assert journal.records == pending and journal.counts == {'SUBSCRIPTION': 1}
    assert journal.bytes == len(pending[0].encode()) + 1


@pytest.mark.parametrize('missing', ['', None])
def test_pending_export_never_calls_store_but_preserves_buffer(runtime, successor, missing):
    native, getter = native_state(job=missing); journal = successor.DeferredPrivateEvidence(binding(runtime.core), getter)
    journal.append('CAPS', {'initial': True}); store = Store(); before = journal.records
    with pytest.raises(ValueError): journal.export(store)
    assert store.calls == [] and journal.records == before and journal.prefix is None
    native.algorithm_id, native.locked = 'native-job', True
    assert journal.export(store)['records'] == 1 and journal.closed


@pytest.mark.parametrize('project', [0, -1, True, False, '123', 123.0, None])
def test_strict_native_project_no_coercion(runtime, successor, project):
    _, getter = native_state(project=project)
    with pytest.raises(ValueError): successor.DeferredPrivateEvidence(binding(runtime.core), getter)


def test_native_clr_like_conversion_not_invoked_without_evidence(runtime, successor):
    class UnverifiedInt32:
        def __int__(self): raise AssertionError('generic CLR coercion forbidden')
    _, getter = native_state(project=UnverifiedInt32())
    with pytest.raises(ValueError): successor.DeferredPrivateEvidence(binding(runtime.core), getter)


@pytest.mark.parametrize('job', [True, False, 123, 1.0, [], {}, 'bad/job', 'x' * 201])
def test_invalid_native_job_type_or_namespace_refuses_even_unlocked(runtime, successor, job):
    _, getter = native_state(job=job)
    with pytest.raises(ValueError): successor.DeferredPrivateEvidence(binding(runtime.core), getter)


@pytest.mark.parametrize('lock', [None, 0, 1, 'true'])
def test_lock_must_be_native_boolean(runtime, successor, lock):
    _, getter = native_state(locked=lock)
    with pytest.raises(ValueError): successor.DeferredPrivateEvidence(binding(runtime.core), getter)


def test_locked_empty_job_is_postinitialize_refusal_not_more_pending_records(runtime, successor):
    native, getter = native_state(); journal = successor.DeferredPrivateEvidence(binding(runtime.core), getter)
    journal.append('CAPS', {'initial': True}); before = journal.records
    native.locked = True
    with pytest.raises(ValueError): journal.append('ORDER', {'must_not_append': True})
    assert journal.records == before and journal.prefix is None
    native.algorithm_id = 'native-job'
    with pytest.raises(ValueError): journal.export(Store())


@pytest.mark.parametrize('change', ['project', 'job', 'lock'])
def test_bound_native_identity_cannot_change_or_reopen_initialization(runtime, successor, change):
    native, getter = native_state(job='native-job', locked=True)
    journal = successor.DeferredPrivateEvidence(binding(runtime.core), getter); journal.append('CAPS', {'known': True})
    before = journal.records
    if change == 'project': native.project_id = 999
    elif change == 'job': native.algorithm_id = 'foreign-job'
    else: native.locked = False
    with pytest.raises(ValueError): journal.append('ORDER', {'wrong_identity': True})
    assert journal.records == before
    with pytest.raises(ValueError): journal.export(Store())


def test_getter_error_has_closed_message_and_no_secret_echo(runtime, successor):
    def getter(): raise RuntimeError('SECRET-NATIVE-VALUE')
    with pytest.raises(ValueError, match='native evidence identity refused') as error:
        successor.DeferredPrivateEvidence(binding(runtime.core), getter)
    assert 'SECRET' not in str(error.value)


@pytest.mark.parametrize('change', ['binding', 'prefix'])
def test_bound_journal_metadata_or_prefix_cannot_redirect_export(runtime, successor, change):
    _, getter = native_state(job='native-job', locked=True)
    journal = successor.DeferredPrivateEvidence(binding(runtime.core), getter)
    journal.append('CAPS', {})
    if change == 'binding': journal._journal.binding['job_id'] = 'foreign-job'
    else: journal._journal.prefix = 'tpr-ext26/evidence/foreign-job/'
    store = Store()
    with pytest.raises(ValueError): journal.export(store)
    assert store.calls == [] and not journal.closed


@pytest.mark.parametrize('field,value', [('project_id', 123), ('job_id', 'configured-job'), ('attempt', True),
    ('candidate_id', 'foreign'), ('freeze_sha256', 'b' * 64), ('config_sha256', 'bad'), ('input_hashes', {})])
def test_only_closed_frozen_static_binding_accepted(runtime, successor, field, value):
    meta = binding(runtime.core); meta[field] = value; _, getter = native_state()
    with pytest.raises(ValueError): successor.DeferredPrivateEvidence(meta, getter)


def test_original_mutable_binding_or_payload_cannot_change_buffered_records(runtime, successor):
    meta = binding(runtime.core); native, getter = native_state(); journal = successor.DeferredPrivateEvidence(meta, getter)
    payload = {'number': Fraction(2, 3)}; journal.append('CAPS', payload)
    payload['number'] = Fraction(999); meta['input_hashes']['calendar.json'] = 'b' * 64
    assert journal.records[0] == runtime.core.exact_json({'kind': 'CAPS', 'payload': {'number': Fraction(2, 3)}})
    assert journal.binding['input_hashes']['calendar.json'] == runtime.core.CALENDAR_SHA256
    copy = journal.binding; copy['input_hashes']['calendar.json'] = 'c' * 64
    assert journal.binding['input_hashes']['calendar.json'] == runtime.core.CALENDAR_SHA256


def test_original_kind_record_and_byte_bounds_apply_while_pending(runtime, successor, monkeypatch):
    native, getter = native_state(); journal = successor.DeferredPrivateEvidence(binding(runtime.core), getter)
    with pytest.raises(ValueError): journal.append('UNKNOWN', {})
    with pytest.raises(ValueError): journal.append('CAPS', {'unsupported': 1.0})
    monkeypatch.setattr(runtime.core, 'MAX_EVIDENCE_RECORDS', 1)
    journal.append('CAPS', {'one': True}); before = journal.records
    with pytest.raises(ValueError): journal.append('CAPS', {'two': True})
    assert journal.records == before
    native.algorithm_id, native.locked = 'native-job', True; journal.require_binding()
    with pytest.raises(ValueError): journal.append('CAPS', {'two': True})


def test_original_byte_bounds_not_refunded_by_native_binding(runtime, successor, monkeypatch):
    monkeypatch.setattr(runtime.core, 'MAX_EVIDENCE_BYTES', 80)
    native, getter = native_state(); journal = successor.DeferredPrivateEvidence(binding(runtime.core), getter)
    journal.append('CAPS', {'one': 'small'}); size = journal.bytes
    native.algorithm_id, native.locked = 'native-job', True; journal.require_binding()
    assert journal.bytes == size
    with pytest.raises(ValueError): journal.append('CAPS', {'two': 'x' * 50})


def test_deferred_export_exactly_matches_original_records_chunks_hashes_and_closure(runtime, successor):
    native, getter = native_state(); meta = binding(runtime.core)
    deferred = successor.DeferredPrivateEvidence(meta, getter)
    deferred.append('CAPS', {'initial': True, 'fraction': Fraction(1, 7)})
    native.algorithm_id, native.locked = 'native-job', True
    deferred.append('SUMMARY', {'native_after_initialize': True})
    original = runtime.core.PrivateEvidence({**meta, 'project_id': 123, 'job_id': 'native-job'})
    original.append('CAPS', {'initial': True, 'fraction': Fraction(1, 7)})
    original.append('SUMMARY', {'native_after_initialize': True})
    first, second = Store(), Store()
    assert deferred.export(first) == original.export(second) and first.values == second.values
    assert deferred.closed and deferred.counts == {'CAPS': 1, 'SUMMARY': 1}
    with pytest.raises(ValueError): deferred.append('CAPS', {})
    with pytest.raises(ValueError): deferred.export(first)
    index = json.loads(first.values[deferred.prefix + 'index.json'])
    assert index['project_id'] == 123 and index['job_id'] == 'native-job'
    for chunk in index['chunks']:
        assert chunk['sha256'] == hashlib.sha256(first.values[chunk['key']].encode()).hexdigest()


def test_store_interaction_identity_change_stops_before_any_write(runtime, successor):
    native, getter = native_state(job='native-job', locked=True)
    journal = successor.DeferredPrivateEvidence(binding(runtime.core), getter); journal.append('CAPS', {})
    class ChangingStore(Store):
        def contains_key(self, key):
            result = super().contains_key(key); native.algorithm_id = 'foreign-job'; return result
    store = ChangingStore()
    with pytest.raises(ValueError): journal.export(store)
    assert store.values == {} and not journal.closed


def test_existing_key_or_failed_save_not_closed_and_no_index_replacement(runtime, successor):
    native, getter = native_state(job='native-job', locked=True)
    journal = successor.DeferredPrivateEvidence(binding(runtime.core), getter); journal.append('CAPS', {})
    store = Store(); store.values[journal.prefix + 'index.json'] = 'immutable-prior'
    with pytest.raises(ValueError): journal.export(store)
    assert store.values == {journal.prefix + 'index.json': 'immutable-prior'} and not journal.closed
    class FailedSave(Store):
        def save(self, key, value): return False
    failed = FailedSave()
    with pytest.raises(ValueError): journal.export(failed)
    assert not journal.closed and not failed.values
