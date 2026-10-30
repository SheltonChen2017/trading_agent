"""Synthetic launch admission: no operational artifact, credential or request."""
import copy
import os
from pathlib import Path
import time
from types import SimpleNamespace as NS

import pytest

from scripts import arv2_r298_launch_admission as m
from tests.analyst_revisions_v2 import test_r298_plain_readiness_caller as fixtures


@pytest.fixture(autouse=True)
def no_operational_entrypoint(monkeypatch):
    def refuse(*_, **__):
        raise AssertionError('operational entrypoint reached')
    for module, names in ((m.a11, ('main', '_execute', '_worker', '_child')),
                          (m.a11.prep, ('main', 'construct')),
                          (m.a11._storage_module(), ('main', 'publish', 'worker'))):
        for name in names:
            monkeypatch.setattr(module, name, refuse)


@pytest.fixture
def valid(monkeypatch):
    cloud = fixtures.cloud.__wrapped__(monkeypatch)
    args = NS(operation='recover', expected_head=m.READINESS_HEAD, caller_sha256=m.READINESS_CALLER,
              control_fd=None, deadline=None)
    result, _ = fixtures.recover(cloud, args)
    value = {**m.a11.binding(args), 'result': result, 'operation_completed': True, **m.a11.FALSE_FLAGS}
    raw = m.canonical(value)
    monkeypatch.setattr(m, 'READINESS_BYTES', len(raw))
    monkeypatch.setattr(m, 'READINESS_SHA256', m.sha(raw))
    monkeypatch.setattr(m, 'COMPILE_ID', result['ready_receipt']['compile_id'])
    monkeypatch.setattr(m, 'SOURCE_MANIFEST', result['ready_receipt']['source_manifest_sha256'])
    return NS(cloud=cloud, args=args, value=value, raw=raw)


def repin(monkeypatch, value):
    raw = m.canonical(value)
    monkeypatch.setattr(m, 'READINESS_BYTES', len(raw))
    monkeypatch.setattr(m, 'READINESS_SHA256', m.sha(raw))
    return raw


def test_fixed_external_facts_and_no_entrypoint():
    pin = m.readiness_pin()
    assert pin['actual_readiness_exit'] == 0 and type(pin['actual_readiness_exit']) is int
    assert pin['byte_count'] == 10684
    assert pin['expected_head'] == '9d4725e78ce4baaa39fc080de54aba25ce69b56f'
    assert pin['sha256'] == 'a0ac64a13299e9fa2a37816a15394448bbec8236c9b6636bc379b00dece375e7'
    assert not hasattr(m, 'main') and not hasattr(m, 'Store')
    pin.clear()
    assert m.readiness_pin()['byte_count'] == 10684


@pytest.mark.parametrize('field,bad', [('READINESS_ACTUAL_EXIT', False), ('READINESS_ACTUAL_EXIT', None),
    ('READINESS_ACTUAL_EXIT', 2), ('READINESS_HEAD', 'f' * 39), ('READINESS_CALLER', 'f' * 63),
    ('READINESS_SHA256', None), ('READINESS_BYTES', True), ('READINESS_BYTES', 0),
    ('READINESS_BYTES', 131073), ('COMPILE_ID', '../compile'), ('SOURCE_MANIFEST', 'x' * 64)])
def test_external_exit_and_pins_cannot_be_inferred_from_success(field, bad, monkeypatch):
    monkeypatch.setattr(m, field, bad)
    with pytest.raises(m.Refused, match='readiness_fact'):
        m.readiness_pin()


def test_report_reconstructs_original_envelope_without_reread(valid):
    pin = m.validate_report(valid.raw)
    assert pin['compile_id'] == valid.value['result']['ready_receipt']['compile_id']
    assert pin['sha256'] == m.sha(valid.raw)
    assert pin['actual_readiness_exit'] == 0


@pytest.mark.parametrize('raw', [b'', b'{}\n', b'not JSON', b'\xff' * 16])
def test_report_pin_checked_before_parser(valid, raw, monkeypatch):
    monkeypatch.setattr(m, 'parse', lambda *_: pytest.fail('parse before exact external pin'))
    with pytest.raises(m.Refused, match='readiness_pin'):
        m.validate_report(raw)


def test_equal_length_report_tamper_refuses_before_parser(valid, monkeypatch):
    raw = valid.raw.replace(b'"operation_completed":true', b'"operation_completed":null', 1)
    assert len(raw) == len(valid.raw) and raw != valid.raw
    monkeypatch.setattr(m, 'parse', lambda *_: pytest.fail('parse before report hash'))
    with pytest.raises(m.Refused, match='readiness_pin'):
        m.validate_report(raw)


@pytest.mark.parametrize('change', ['operation', 'binding', 'terminal', 'compile', 'manifest',
    'readiness_attempt', 'storage', 'dispatch', 'source', 'extra', 'flag', 'access'])
def test_pinned_but_semantically_invalid_report_refuses(valid, change, monkeypatch):
    value = copy.deepcopy(valid.value)
    if change == 'operation': value['operation_completed'] = False
    elif change == 'binding': value['expected_head'] = 'f' * 40
    elif change == 'terminal': value['result']['terminal'] = 'Completed.'
    elif change == 'compile': value['result']['ready_receipt']['compile_id'] = 'different-compile'
    elif change == 'manifest': value['result']['ready_receipt']['source_manifest_sha256'] = 'f' * 64
    elif change == 'readiness_attempt': value['result']['ready_receipt']['attempt'] = 10
    elif change == 'storage': value['result']['storage_receipt']['actual_storage_exit'] = 2
    elif change == 'dispatch': value['result']['application_dispatch_count'] = True
    elif change == 'source': value['result']['ready_receipt']['projection_sha256'] = 'f' * 64
    elif change == 'extra': value['unexpected'] = True
    elif change == 'flag': value['backtest_created'] = True
    else: value['result']['access_observation'] = None
    with pytest.raises((m.Refused, m.a11.Refused, m.a11.remote.Refused)):
        m.validate_report(repin(monkeypatch, value))


@pytest.mark.parametrize('suffix', [b'\n', b'garbage'])
def test_even_rebound_noncanonical_report_refuses(valid, suffix, monkeypatch):
    raw = valid.raw + suffix
    monkeypatch.setattr(m, 'READINESS_BYTES', len(raw))
    monkeypatch.setattr(m, 'READINESS_SHA256', m.sha(raw))
    with pytest.raises(m.Refused, match='readiness_report'): m.validate_report(raw)


@pytest.fixture
def workflow(valid, monkeypatch):
    order = []
    projected = NS(record_bytes=valid.cloud.record_bytes,
        source_files=tuple(NS(project_path=name, source_bytes=raw) for name, raw in valid.cloud.pairs))
    plain = NS(private_payload=b'synthetic licensed row never in public packet')
    def construct(deadline):
        order.append('construct')
        return plain, projected
    def authenticate(p, q, deadline):
        assert p is plain and q is projected
        order.append('storage')
        return copy.deepcopy(valid.cloud.packet['storage_receipt'])
    def source_checks(deadline): order.append('sources')
    def snapshot(p, q):
        assert p is plain and q is projected
        order.append('snapshot')
        return b'exact synthetic data and code'
    class Reader:
        def __enter__(self): order.append('open-report'); return self
        def __exit__(self, *_): order.append('close-report')
        def read(self, deadline): order.append('read-report'); return valid.raw
        def verify(self): order.append('verify-report')
    monkeypatch.setattr(m.a11.prep, 'construct', construct)
    monkeypatch.setattr(m.a11, 'authenticate_storage', authenticate)
    monkeypatch.setattr(m, 'source_checks', source_checks)
    monkeypatch.setattr(m, '_snapshot', snapshot)
    monkeypatch.setattr(m, 'ReadinessReport', Reader)
    return NS(order=order, plain=plain, projected=projected, valid=valid)


def test_admit_checks_fresh_sources_storage_report_then_fresh_sources(workflow):
    packet = m.admit(time.monotonic() + 800)
    assert workflow.order == ['sources', 'construct', 'snapshot', 'storage', 'open-report',
        'read-report', 'construct', 'snapshot', 'sources', 'verify-report', 'close-report']
    assert set(packet) == {'admission_authenticated', 'projection_record', 'source_pairs',
                           'readiness_pin', 'storage_receipt'}
    assert packet['admission_authenticated'] is True
    assert b'synthetic licensed row' not in m.canonical(packet)
    assert len(packet['source_pairs']) == 11


def test_public_packet_validation_returns_bound_projection_and_sources(workflow):
    packet = m.admit(time.monotonic() + 800)
    raw, pairs = m.validate_packet(packet)
    assert raw == workflow.projected.record_bytes
    assert pairs == workflow.valid.cloud.pairs


@pytest.mark.parametrize('change', ['extra', 'missing', 'exit-bool', 'exit-nonzero', 'compile',
    'manifest', 'head', 'report', 'admitted', 'source-bytes', 'source-name', 'source-order',
    'projection', 'storage', 'opaque'])
def test_public_worker_packet_cannot_change_bindings_or_include_extra_data(workflow, change):
    packet = m.admit(time.monotonic() + 800)
    if change == 'extra': packet['private_rows'] = []
    elif change == 'missing': packet.pop('readiness_pin')
    elif change == 'exit-bool': packet['readiness_pin']['actual_readiness_exit'] = False
    elif change == 'exit-nonzero': packet['readiness_pin']['actual_readiness_exit'] = 2
    elif change == 'compile': packet['readiness_pin']['compile_id'] = 'another-compile'
    elif change == 'manifest': packet['readiness_pin']['source_manifest_sha256'] = 'f' * 64
    elif change == 'head': packet['readiness_pin']['expected_head'] = 'f' * 40
    elif change == 'report': packet['readiness_pin']['sha256'] = 'f' * 64
    elif change == 'admitted': packet['admission_authenticated'] = 1
    elif change == 'source-bytes': packet['source_pairs'][0][1] += '\n'
    elif change == 'source-name': packet['source_pairs'][0][0] = 'different.py'
    elif change == 'source-order': packet['source_pairs'].reverse()
    elif change == 'projection': packet['projection_record'] += '\n'
    elif change == 'storage': packet['storage_receipt']['actual_storage_exit'] = 2
    else: packet['source_pairs'][0][1] = object()
    with pytest.raises((m.Refused, m.a11.Refused, m.a11.remote.Refused)):
        m.validate_packet(packet)


@pytest.mark.parametrize('step', ['initial-source', 'initial-construct', 'storage', 'report',
                                'final-construct', 'drift', 'final-source', 'final-report'])
def test_failure_stops_at_each_admission_boundary(workflow, monkeypatch, step):
    sources = constructs = snapshots = 0
    original_sources, original_construct, original_snapshot = m.source_checks, m.a11.prep.construct, m._snapshot
    def source_checks(deadline):
        nonlocal sources
        sources += 1
        if (sources == 1 and step == 'initial-source') or (sources == 2 and step == 'final-source'):
            raise m.Refused('source')
        return original_sources(deadline)
    def construct(deadline):
        nonlocal constructs
        constructs += 1
        if (constructs == 1 and step == 'initial-construct') or (constructs == 2 and step == 'final-construct'):
            raise m.Refused('fresh_source')
        return original_construct(deadline)
    def snapshot(p, q):
        nonlocal snapshots
        snapshots += 1
        result = original_snapshot(p, q)
        return b'different' if snapshots == 2 and step == 'drift' else result
    monkeypatch.setattr(m, 'source_checks', source_checks)
    monkeypatch.setattr(m.a11.prep, 'construct', construct)
    monkeypatch.setattr(m, '_snapshot', snapshot)
    def fail(*_, **__): raise m.Refused('readiness_report')
    if step == 'storage': monkeypatch.setattr(m.a11, 'authenticate_storage', fail)
    if step == 'report': monkeypatch.setattr(m, 'validate_report', fail)
    if step == 'final-report': monkeypatch.setattr(m.ReadinessReport, 'verify', fail)
    with pytest.raises(m.Refused): m.admit(time.monotonic() + 800)
    assert constructs <= 2 and sources <= 2
    if step.startswith('initial'): assert 'open-report' not in workflow.order
    if step == 'storage': assert 'open-report' not in workflow.order


@pytest.mark.parametrize('deadline', [None, True, 0, -1, float('nan'), float('inf')])
def test_deadline_is_finite_actual_clock_bound(deadline):
    with pytest.raises(m.Refused, match='deadline'): m.remaining(deadline)


def test_source_checks_exact_pins_and_deadline(monkeypatch):
    monkeypatch.setattr(m, 'selected_pins', lambda: {'scripts/synthetic.py': 'f' * 64})
    seen = []
    monkeypatch.setattr(m.a11.helpers, '_source_digest', lambda path: seen.append(path) or 'f' * 64)
    m.source_checks(time.monotonic() + 10)
    assert seen == [m.ROOT / 'scripts/synthetic.py']
    monkeypatch.setattr(m.a11.helpers, '_source_digest', lambda path: 'e' * 64)
    with pytest.raises(m.Refused, match='source'): m.source_checks(time.monotonic() + 10)


def test_snapshot_compares_actual_transport_payload_profile_and_source(monkeypatch):
    # The genuine-capability validators are exercised separately by the frozen
    # transport/projection suites. Here assert this helper invokes both before
    # retaining all byte-bearing components for the second fresh construction.
    calls = []
    monkeypatch.setattr(m.transport, 'require_plain_transport', lambda value: calls.append(('plain', value)))
    monkeypatch.setattr(m.projection, 'require_plain_projection', lambda value, pin: calls.append(('projection', value, pin)))
    plain = NS(record_bytes=b'plain', upload_objects=(NS(to_record=lambda: {'safe': True}, payload=b'rows'),))
    projected = NS(_transport=plain, record_bytes=b'record', profile_bytes=b'profile',
                   source_files=(NS(project_path='module.py', source_bytes=b'code'),))
    result = m._snapshot(plain, projected)
    assert calls == [('plain', plain), ('projection', projected, m.a11.remote.PROJECTION_SHA256)]
    assert result == (b'plain', b'record', b'profile', ((m.canonical({'safe': True}), b'rows'),), (('module.py', b'code'),))
    projected._transport = object()
    with pytest.raises(m.Refused, match='fresh_source'): m._snapshot(plain, projected)


@pytest.fixture
def report_leaf(tmp_path, monkeypatch):
    leaf = tmp_path / 'synthetic-readiness'
    leaf.mkdir(mode=0o700)
    raw = b'{"synthetic":true}\n'
    target = leaf / 'report.json'
    target.write_bytes(raw)
    target.chmod(0o600)
    monkeypatch.setattr(m, 'READINESS_CONTROL', leaf)
    monkeypatch.setattr(m, 'READINESS_BYTES', len(raw))
    monkeypatch.setattr(m, 'READINESS_SHA256', m.sha(raw))
    return NS(leaf=leaf, target=target, raw=raw)


def test_reader_opens_only_fixed_report_and_holds_descriptor(report_leaf, monkeypatch):
    opened = []
    original = m.os.open
    def observe(path, *args, **kwargs):
        if kwargs.get('dir_fd') is not None and not (args[0] & os.O_DIRECTORY): opened.append(path)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(m.os, 'open', observe)
    with m.ReadinessReport() as reader:
        assert reader.read(time.monotonic() + 10) == report_leaf.raw
        assert reader.leaf is not None
        reader.verify()
        with pytest.raises(m.Refused): reader.read(time.monotonic() + 10)
    assert opened == ['report.json']


@pytest.mark.parametrize('change', ['mode', 'hardlink', 'symlink', 'directory', 'fifo', 'size', 'hash'])
def test_reader_refuses_unsafe_or_unpinned_leaf(report_leaf, change):
    if change == 'mode': report_leaf.target.chmod(0o644)
    elif change == 'hardlink': os.link(report_leaf.target, report_leaf.leaf / 'second.json')
    elif change in ('symlink', 'directory', 'fifo'):
        report_leaf.target.unlink()
        if change == 'symlink': report_leaf.target.symlink_to('missing')
        elif change == 'directory': report_leaf.target.mkdir(mode=0o700)
        else: os.mkfifo(report_leaf.target, mode=0o600)
    elif change == 'size': report_leaf.target.write_bytes(report_leaf.raw + b'x')
    else: report_leaf.target.write_bytes(report_leaf.raw.replace(b'true', b'null'))
    with m.ReadinessReport() as reader:
        with pytest.raises((m.Refused, OSError)): reader.read(time.monotonic() + 10)


@pytest.mark.parametrize('change', ['leaf-mode', 'leaf-replace', 'leaf-inplace', 'directory-mode', 'directory-replace', 'new-sibling'])
def test_reader_refuses_changes_after_read(report_leaf, change):
    with m.ReadinessReport() as reader:
        reader.read(time.monotonic() + 10)
        if change == 'leaf-mode': report_leaf.target.chmod(0o644)
        elif change == 'leaf-replace':
            report_leaf.target.unlink(); report_leaf.target.write_bytes(report_leaf.raw); report_leaf.target.chmod(0o600)
        elif change == 'leaf-inplace': report_leaf.target.write_bytes(report_leaf.raw)
        elif change == 'directory-mode': report_leaf.leaf.chmod(0o755)
        elif change == 'directory-replace':
            report_leaf.leaf.rename(report_leaf.leaf.with_name('retained'))
            report_leaf.leaf.mkdir(mode=0o700)
        else: (report_leaf.leaf / 'new.json').write_bytes(b'{}\n')
        with pytest.raises(m.Refused, match='readiness_changed'): reader.verify()


def test_reader_refuses_linked_or_public_control_directory(report_leaf):
    report_leaf.leaf.chmod(0o755)
    with pytest.raises(m.Refused): m.ReadinessReport()


def test_source_bound_selection_contains_exact_frozen_readiness_caller():
    assert m.selected_pins()['scripts/run_arv2_r298_plain_readiness.py'] == m.READINESS_CALLER
    assert m.selected_pins()['scripts/prepare_arv2_newrule_plain_transport.py'] == '858d631f3aecd4107581ee768fbb606eb5f48addacbf0c1c43ecabf5b615158a'
