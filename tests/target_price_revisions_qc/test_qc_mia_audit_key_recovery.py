"""Exact captured Mia source QA; synthetic storage, not native/QC proof.

Supply pytest plugin tpr_mia_captured_source.source, or a later public port.
Absent source is an explicit skip. No private capture or candidate is written.
"""
import ast
from copy import deepcopy
from fractions import Fraction
import hashlib
import http.client
import inspect
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
from types import ModuleType

import pytest
from research.target_price_revisions_qc import extended_compressed_store as base
from tests.target_price_revisions_qc.test_qc_extended_runtime import binding, runtime

SOURCE_SHA256 = 'bce4182d09dc9d31132cb54d404712471ddff5e2b706c2988fbe9fcc48c93aea'
SOURCE_BYTES = 7490
LANE = Path(__file__).resolve().parents[2]
PUBLIC_SOURCE = LANE / 'research/target_price_revisions_qc/audit_key_recovery.py'
SAVE_KEY = re.compile(r'[.]?[a-zA-Z0-9/_#$= -]+[.]?[a-zA-Z0-9]*')


@pytest.fixture(autouse=True)
def no_actual_effects(monkeypatch):
    def deny(*_args, **_kwargs):
        raise AssertionError('actual credential/network/operator/private effect forbidden')
    for owner, name in ((http.client, 'HTTPSConnection'), (socket, 'create_connection'),
                        (subprocess, 'run'), (subprocess, 'Popen')):
        monkeypatch.setattr(owner, name, deny)
    original_open = os.open
    private = str(LANE / 'artifacts/target_price_extended')
    def opened(path, *args, **kwargs):
        if isinstance(path, (str, bytes, os.PathLike)):
            named = os.fsdecode(path)
            if named == private or named.startswith(private + os.sep): deny()
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(os, 'open', opened)


def verified_source(value):
    if type(value) is str: value = value.encode('utf-8')
    if (type(value) is not bytes or len(value) != SOURCE_BYTES
            or hashlib.sha256(value).hexdigest() != SOURCE_SHA256):
        raise ValueError('exact independently captured helper bytes required')
    return value


def public_source_bytes():
    try: fd = os.open(PUBLIC_SOURCE, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        pytest.skip('captured Mia helper plugin absent; no later public helper port exists')
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size != SOURCE_BYTES:
            raise ValueError('bounded regular public helper required')
        blocks, size = [], 0
        while size <= SOURCE_BYTES:
            block = os.read(fd, SOURCE_BYTES + 1 - size)
            if not block: break
            blocks.append(block); size += len(block)
        return b''.join(blocks)
    finally: os.close(fd)


@pytest.fixture
def helper(request, monkeypatch):
    plugin = request.config.pluginmanager.get_plugin('tpr_mia_captured_source')
    source = verified_source(plugin.source if plugin is not None else public_source_bytes())
    monkeypatch.setitem(sys.modules, 'extended_compressed_store', base)
    module = ModuleType('audit_key_recovery')
    module.__file__ = '<captured-public-source:' + SOURCE_SHA256 + '>'
    monkeypatch.setitem(sys.modules, module.__name__, module)
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    module._captured_source = source
    return module


class Native:
    """Current-rule simulation, not old-build/CLR attestation.

    Legacy ContainsKey/ReadBytes strings are allowed; SaveBytes alone applies
    the current upstream regex. All events, faults and partial writes survive.
    """
    def __init__(self, prefix, values=None):
        self.prefix, self.values = prefix, dict(values or {})
        self.events, self.saves = [], []
        self.check_fault, self.save_fault, self.read_fault = None, None, None
    def _owned(self, key):
        assert type(key) is str and key.startswith(self.prefix)
        suffix = key[len(self.prefix):]
        assert (re.fullmatch(r'chunks[0-9]{5}(?:\.json|\.json\.gz|_json\.gz)', suffix)
                or suffix in {'index.json', 'index.json.gz', 'index_json.gz',
                              'storage.json', 'storage.json.gz', 'storage_json.gz'})
    def contains_key(self, key):
        self._owned(key); self.events.append(('contains', key))
        return self.check_fault(key) if self.check_fault is not None else key in self.values
    def read_bytes(self, key):
        self._owned(key); self.events.append(('read', key))
        return self.read_fault(key) if self.read_fault is not None else self.values[key]
    def save_bytes(self, key, raw):
        self._owned(key); self.events.append(('save_attempt', key))
        if SAVE_KEY.fullmatch(key) is None or key.count('/') > 100:
            raise ValueError('LocalObjectStore: path is not supported')
        if self.save_fault is not None: return self.save_fault(key, raw)
        assert key not in self.values
        self.values[key] = bytes(raw); self.saves.append(key)
        return True


def adapter(helper, runtime, *, bound=None):
    bound = binding(runtime) if bound is None else bound
    prefix = runtime.core.evidence_prefix(bound['candidate_id'], bound['config_sha256'],
        bound['attempt'], bound['project_id'], bound['job_id'])
    native = Native(prefix)
    return helper.CompressedAuditStore(native, bound), native


def journal(runtime, bound, *, full=False, multichunk=False):
    result = runtime.core.PrivateEvidence(bound)
    if full:
        for day in runtime.core.VALUATIONS:
            result.append('NAV', {'session': day, 'nav': Fraction(100000), 'residual': Fraction(0)})
        for day in runtime.core.DECISIONS:
            result.append('COVERAGE', {'session': day, 'selected': 60})
    else: result.append('NAV', {'session': '2021-01-04', 'nav': Fraction(100000)})
    if multichunk:
        for number in range(40):
            result.append('COVERAGE', {'synthetic_number': number, 'synthetic_text': 'x' * 20000})
    result.append('SUMMARY', {'canonical_admission': False})
    return result


class Plain:
    def __init__(self): self.values = {}
    def contains_key(self, key): return key in self.values
    def save(self, key, value): self.values[key] = value; return True
    def read(self, key): return self.values[key]


@pytest.mark.parametrize('bad', [b'', b'x' * SOURCE_BYTES, True, 7490])
def test_exact_captured_source_required_before_execution(bad):
    with pytest.raises(ValueError): verified_source(bad)


def test_direct_import_and_inherited_business_methods(helper):
    namespace = {}
    exec('from audit_key_recovery import CompressedAuditStore', namespace)
    assert namespace['CompressedAuditStore'] is helper.CompressedAuditStore
    assert issubclass(helper.CompressedAuditStore, base.CompressedAuditStore)
    for name in ('save', 'read', '_index', 'storage_declaration'):
        assert inspect.getattr_static(helper.CompressedAuditStore, name) is inspect.getattr_static(base.CompressedAuditStore, name)
    overrides = {name for name, value in helper.CompressedAuditStore.__dict__.items()
                 if inspect.isfunction(value) or isinstance(value, staticmethod)}
    assert overrides == {'__init__', '_validate_full_key', '_build_physical_mapping',
                         '_collision_sweep', '_key', 'contains_key', '_sidecar'}
    imports = [node for node in ast.walk(ast.parse(helper._captured_source))
               if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert {node.module for node in imports if isinstance(node, ast.ImportFrom)} == {'__future__', 'extended_compressed_store'}
    assert [alias.name for node in imports if isinstance(node, ast.Import) for alias in node.names] == ['re']


def test_exact_binding_closed_map_and_all_boundary_keys(helper, runtime):
    bound = binding(runtime); candidate, native = adapter(helper, runtime, bound=bound)
    original = base.CompressedAuditStore(Native(candidate.prefix), bound)
    assert candidate.binding == original.binding == bound and candidate.prefix == original.prefix
    assert not native.events
    expected = {candidate.prefix + f'chunks{number:05d}.json': candidate.prefix + f'chunks{number:05d}_json.gz'
                for number in range(1024)}
    expected[candidate.prefix + 'index.json'] = candidate.prefix + 'index_json.gz'
    assert candidate._physical_by_logical == expected and len(set(expected.values())) == 1025
    assert candidate._storage_physical == candidate.prefix + 'storage_json.gz'
    assert candidate._storage_physical not in set(expected.values())
    for logical, physical in expected.items():
        assert candidate._key(logical) == physical and SAVE_KEY.fullmatch(physical)
        assert physical.count('.') == 1 and physical.count('/') <= 100


@pytest.mark.parametrize('suffix', ['chunks01024.json', 'chunks99999.json', 'chunks0000.json',
    'chunks-0001.json', 'chunks00000.json.gz', 'storage.json', 'storage_json.gz', 'unknown.json', '../index.json'])
def test_public_logical_api_never_admits_sidecar_or_bad_shapes(helper, runtime, suffix):
    candidate, native = adapter(helper, runtime)
    for operation in (lambda: candidate._key(candidate.prefix + suffix),
                      lambda: candidate.contains_key(candidate.prefix + suffix),
                      lambda: candidate.save(candidate.prefix + suffix, '[]')):
        with pytest.raises(ValueError): operation()
    assert not native.events and not native.saves


@pytest.mark.parametrize('job', ['a.b', '.leading', 'trailing.', 'two..dots'])
def test_dotted_native_job_refuses_before_any_query(helper, runtime, job):
    native = Native('unused/')
    with pytest.raises(ValueError): helper.CompressedAuditStore(native, {**binding(runtime), 'job_id': job})
    assert not native.events


@pytest.mark.parametrize('kind', ['dict_subclass', 'extra', 'missing', 'bool_project', 'bool_attempt', 'wrong_freeze'])
def test_inherited_closed_binding_refusals_remain(helper, runtime, kind):
    bound = deepcopy(binding(runtime))
    if kind == 'dict_subclass': bound = type('Binding', (dict,), {})(bound)
    if kind == 'extra': bound['new_field'] = 'refuse'
    if kind == 'missing': bound.pop('job_id')
    if kind == 'bool_project': bound['project_id'] = True
    if kind == 'bool_attempt': bound['attempt'] = True
    if kind == 'wrong_freeze': bound['freeze_sha256'] = 'b' * 64
    native = Native('unused/')
    with pytest.raises(ValueError): helper.CompressedAuditStore(native, bound)
    assert not native.events


def test_native_full_key_rule_and_slash_boundary_are_not_basename_only(helper):
    assert helper.CompressedAuditStore._validate_full_key('a/' * 100 + 'index_json.gz')
    for key in ('a/' * 101 + 'index_json.gz', 'job.with.dot/chunks00000_json.gz',
                'a/chunks00000.json.gz', 'a/é.gz', 'a/back\\slash.gz', 'a/key\n.gz'):
        with pytest.raises(ValueError): helper.CompressedAuditStore._validate_full_key(key)


@pytest.mark.parametrize('suffix', [f'chunks{number:05d}{ending}' for number in (0, 1023)
    for ending in ('.json', '.json.gz', '_json.gz')] +
    ['index.json', 'index.json.gz', 'index_json.gz', 'storage.json', 'storage.json.gz', 'storage_json.gz'])
def test_entire_logical_legacy_new_collision_census_precedes_first_write(helper, runtime, suffix):
    candidate, native = adapter(helper, runtime); key = candidate.prefix + suffix
    native.values[key] = b'preserve synthetic collision'; before = dict(native.values)
    with pytest.raises(ValueError): journal(runtime, candidate.binding).export(candidate)
    assert native.values == before and not native.saves
    assert not any(kind == 'save_attempt' for kind, _key in native.events) and not candidate.closed


@pytest.mark.parametrize('value', [None, 0, 1, 'False', [], {}])
def test_unknown_or_nonbool_census_refuses_before_first_write(helper, runtime, value):
    candidate, native = adapter(helper, runtime); native.check_fault = lambda _key: value
    with pytest.raises(ValueError): journal(runtime, candidate.binding).export(candidate)
    assert not native.saves and not candidate.closed


def test_query_failure_at_last_census_target_refuses_before_write(helper, runtime):
    candidate, native = adapter(helper, runtime)
    def query(key):
        if key == candidate._storage_physical: raise RuntimeError('synthetic unknown census')
        return False
    native.check_fault = query
    with pytest.raises(RuntimeError): journal(runtime, candidate.binding).export(candidate)
    assert not native.saves


@pytest.mark.parametrize('value', [None, 0, 1])
def test_existence_recheck_after_sweep_still_requires_native_bool(helper, runtime, value):
    candidate, native = adapter(helper, runtime)
    candidate._collision_sweep()
    native.check_fault = lambda _key: value
    with pytest.raises(ValueError): candidate.contains_key(candidate.prefix + 'chunks00000.json')
    assert not native.saves


@pytest.mark.parametrize('full,multichunk', [(True, False), (False, True)])
def test_same_complete_journal_original_red_successor_green_exact_index_and_sidecar(helper, runtime, full, multichunk):
    candidate, native = adapter(helper, runtime); bound = candidate.binding
    baseline = journal(runtime, bound, full=full, multichunk=multichunk)
    old_journal = journal(runtime, bound, full=full, multichunk=multichunk)
    observed = journal(runtime, bound, full=full, multichunk=multichunk); old_native = Native(candidate.prefix)
    with pytest.raises(ValueError, match='LocalObjectStore: path is not supported'):
        old_journal.export(base.CompressedAuditStore(old_native, bound))
    assert not old_journal.closed and not old_native.saves
    plaintext = Plain(); expected = baseline.export(plaintext)
    assert observed.export(candidate) == expected
    assert observed.closed and candidate.closed and observed.records == baseline.records == old_journal.records
    if multichunk: assert expected['chunks'] >= 2
    if full: assert observed.counts == {'NAV': 1449, 'COVERAGE': 301, 'SUMMARY': 1}
    for logical, text in plaintext.values.items():
        assert candidate.read(logical) == text
        row = candidate.descriptors[logical]
        assert row['stored_key'] == candidate._key(logical)
        assert row['plain_sha256'] == base.sha256(text.encode()) and row['plain_bytes'] == len(text.encode())
        assert base.decode_gzip(native.values[row['stored_key']], plain_bytes=row['plain_bytes'],
            plain_sha256=row['plain_sha256'], gzip_bytes=row['gzip_bytes'], gzip_sha256=row['gzip_sha256'],
            maximum=base.MAX_CHUNK) == text.encode()
    declaration = base.canonical(candidate.storage_declaration)
    assert base.decode_gzip(native.values[candidate._storage_physical], plain_bytes=len(declaration),
        plain_sha256=base.sha256(declaration), maximum=base.MAX_METADATA) == declaration
    assert candidate.storage_declaration['raw_journal_records_dropped'] is False
    assert len(candidate.descriptors) == len(plaintext.values)
    assert all(SAVE_KEY.fullmatch(key) and key.count('.') == 1 for key in native.values)


@pytest.mark.parametrize('suffix', ['storage.json', 'storage.json.gz', 'storage_json.gz'])
def test_sidecar_collision_arriving_after_preflight_is_rechecked_and_partial(helper, runtime, suffix):
    candidate, native = adapter(helper, runtime); original = native.save_bytes
    collision = candidate.prefix + suffix
    def saved(key, raw):
        result = original(key, raw)
        if key.endswith('index_json.gz'): native.values[collision] = b'preserve late collision'
        return result
    native.save_bytes = saved; observed = journal(runtime, candidate.binding)
    with pytest.raises(ValueError): observed.export(candidate)
    assert native.saves and native.values[collision] == b'preserve late collision'
    assert collision not in native.saves and not candidate.closed and not observed.closed


@pytest.mark.parametrize('failure', ['false', 'nonbool', 'raise', 'readback', 'truncated', 'tail', 'second_member', 'wrong_payload'])
def test_native_failures_never_complete_or_drop_journal(helper, runtime, failure):
    candidate, native = adapter(helper, runtime); observed = journal(runtime, candidate.binding)
    before = list(observed.records)
    if failure == 'false': native.save_fault = lambda *_args: False
    if failure == 'nonbool': native.save_fault = lambda *_args: 1
    if failure == 'raise':
        def failed(*_args): raise RuntimeError('synthetic failed write')
        native.save_fault = failed
    if failure == 'readback': native.read_fault = lambda _key: b'corrupt'
    if failure in {'truncated', 'tail', 'second_member', 'wrong_payload'}:
        def corrupt(key):
            raw = native.values[key]
            return raw[:-1] if failure == 'truncated' else raw + b'tail' if failure == 'tail' else raw + raw if failure == 'second_member' else base.encode_gzip(b'changed')
        native.read_fault = corrupt
    with pytest.raises((ValueError, RuntimeError)): observed.export(candidate)
    assert observed.records == before and not observed.closed and not candidate.closed


@pytest.mark.parametrize('failure', ['false', 'nonbool', 'raise', 'truncated', 'tail', 'second_member', 'wrong_payload'])
def test_sidecar_failure_is_partial_and_never_completes_journal(helper, runtime, failure):
    candidate, native = adapter(helper, runtime)
    observed = journal(runtime, candidate.binding)
    before = list(observed.records)
    original_save, original_read = native.save_bytes, native.read_bytes
    def saved(key, raw):
        if key != candidate._storage_physical: return original_save(key, raw)
        if failure == 'false': return False
        if failure == 'nonbool': return 1
        if failure == 'raise': raise RuntimeError('synthetic sidecar failure')
        return original_save(key, raw)
    def read(key):
        raw = original_read(key)
        if key != candidate._storage_physical: return raw
        if failure == 'truncated': return raw[:-1]
        if failure == 'tail': return raw + b'tail'
        if failure == 'second_member': return raw + raw
        if failure == 'wrong_payload': return base.encode_gzip(b'changed')
        return raw
    native.save_bytes, native.read_bytes = saved, read
    with pytest.raises((ValueError, RuntimeError)): observed.export(candidate)
    assert native.saves and native.saves[0].endswith('chunks00000_json.gz')
    assert candidate.prefix + 'index_json.gz' in native.saves
    assert observed.records == before and not observed.closed and not candidate.closed


@pytest.mark.parametrize('budget', ['plain', 'gzip'])
def test_inherited_aggregate_bounds_refuse_before_write(helper, runtime, budget):
    candidate, native = adapter(helper, runtime)
    if budget == 'plain': candidate.raw_bytes = base.MAX_JOURNAL + base.MAX_CHUNK
    else: candidate.gzip_bytes = base.MAX_JOURNAL
    with pytest.raises(ValueError): candidate.save(candidate.prefix + 'chunks00000.json', '[]')
    assert not native.saves and not candidate.closed


def test_inherited_index_refusal_bounds_and_after_close(helper, runtime):
    candidate, native = adapter(helper, runtime)
    with pytest.raises(ValueError): candidate.save(candidate.prefix + 'chunks00000.json', 'x' * (base.MAX_CHUNK + 1))
    assert not native.saves
    candidate.save(candidate.prefix + 'chunks00000.json', '[{"kind":"NAV","payload":{}}]')
    with pytest.raises(ValueError): candidate.save(candidate.prefix + 'index.json', '{}')
    with pytest.raises(ValueError): candidate.save(candidate.prefix + 'chunks00000.json', '[]')
    assert not candidate.closed
    complete, own = adapter(helper, runtime); journal(runtime, complete.binding).export(complete)
    before = list(own.saves)
    with pytest.raises(ValueError): complete.save(complete.prefix + 'chunks00001.json', '[]')
    assert own.saves == before and complete.closed
