"""U fixtures use only synthetic local leaves; actual T data is denied."""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from types import SimpleNamespace as NS

import pytest

from scripts import inspect_arv2_r298_sharadar_cusip_syntax as m


@pytest.fixture(autouse=True)
def deny_operations(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('unmocked historical operation, credential or provider')
    for module, names in ((m.previous, ('run', 'observe', 'main')),
        (m.previous.observation, ('observe', '_fetch')),
        (m.previous.previous, ('run', 'observe', 'main')),
        (m.previous.previous.keychain, ('load_key',))):
        for name in names:
            monkeypatch.setattr(module, name, denied)


@pytest.fixture
def args():
    return NS(expected_head='a' * 40, caller_sha256='b' * 64)


@pytest.fixture
def sources(tmp_path, monkeypatch):
    source = tmp_path / 'synthetic-source'
    source.mkdir(mode=0o700)
    values = {'stocks-probe.csv': b'synthetic private stock bytes\n',
        'funds-probe.csv': b'synthetic private fund bytes\n'}
    for name, raw in values.items():
        path = source / name
        path.write_bytes(raw)
        path.chmod(0o600)
    monkeypatch.setattr(m, 'SOURCE_DIRECTORY', source)
    monkeypatch.setattr(m, 'SOURCE_PINS', {name: {'byte_count': len(raw), 'sha256': m.sha(raw)}
        for name, raw in values.items()})
    monkeypatch.setattr(m, 'security_snapshot', lambda fd: {'acl_empty': True, 'xattrs': {}})
    return NS(path=source, values=values)


@pytest.fixture
def control(tmp_path, monkeypatch):
    parent = tmp_path / 'own-parent'
    parent.mkdir(mode=0o700)
    target = parent / 'synthetic-u'
    monkeypatch.setattr(m, 'CONTROL', target)
    return target


@pytest.fixture
def workflow(sources, control, args, monkeypatch):
    state = NS(events=[], receipt={'schema': 'synthetic-syntax-summary'}, fail_postflight=False)
    def inspect_captures(values):
        claim = m.parse((control / 'claim.json').read_bytes())
        assert claim['offline_only'] is True
        assert (control / 'source-start.json').exists()
        assert values == sources.values
        state.events.append('analysis')
        return copy.deepcopy(state.receipt)
    def validate_receipt(value):
        assert value == state.receipt
        return copy.deepcopy(value)
    def preflight(*unused):
        state.events.append('postflight')
        if state.fail_postflight:
            raise m.Refused('source_pin')
    monkeypatch.setattr(m.syntax, 'inspect_captures', inspect_captures)
    monkeypatch.setattr(m.syntax, 'validate_receipt', validate_receipt)
    monkeypatch.setattr(m, 'preflight', preflight)
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: None)
    return state


def envelope(args, outcome):
    return m.canonical({'binding': m.binding(args), 'outcome': outcome})


def test_public_scope_and_native_policy_literals():
    profile = m.profile_record()
    assert m.CONTROL.name == 'R323-20261025-U'
    assert m.DEADLINE_SECONDS == profile['deadline_seconds'] == 90
    assert profile['outer_seconds'] == 120 and profile['validator_seconds'] == 20
    assert profile['max_control_files'] == 8 and profile['source_stage_uses'] == 1
    assert profile['logical_bounded_source_passes_per_leaf'] == 1
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
    producer = m.native_producer_profile()
    assert '(deny network*)' in producer
    assert '(deny file-read-data' in producer
    assert '/usr/bin/security' in producer and 'Library/Keychains' in producer
    assert '(subpath "/Library/Keychains")' in producer
    for name in m.SOURCE_PINS:
        assert str(m.SOURCE_DIRECTORY / name) in producer
    assert str(m.SOURCE_DIRECTORY / 'claim.json') not in producer
    assert str(m.SOURCE_DIRECTORY / 'report.json') not in producer
    assert 'artifact' in m.profile_record()['native_artifact_read_data'].lower() or profile['native_artifact_read_data'].startswith('two_')


def test_selected_pins_and_in_memory_compilation():
    for name, pin in m.pins().items():
        assert re.fullmatch('[0-9a-f]{64}', pin) and pin != '0' * 64
        assert m.sha((m.ROOT / name).read_bytes()) == pin
    for name in ('scripts/inspect_arv2_r298_sharadar_cusip_syntax.py',
        'tests/analyst_revisions_v2/test_r298_sharadar_cusip_syntax_caller.py'):
        compile((m.ROOT / name).read_bytes(), name, 'exec')
    assert 'assistant.dispatch_fence' not in sys.modules


def test_claim_source_stage_then_analysis_with_fds_held_through_report(control, args, workflow, monkeypatch):
    actual_write = m.Store.write
    actual_enter = m.SourceGuard.__enter__
    entered = []
    def enter(self):
        result = actual_enter(self)
        entered.append(self)
        return result
    def write(self, name, value):
        if name == 'report.json':
            assert workflow.events == ['analysis', 'postflight']
            assert len(entered) == 1 and len(entered[0].held) == 2
            assert all(os.fstat(fd).st_size == m.SOURCE_PINS[leaf]['byte_count']
                for leaf, (fd, _, _) in entered[0].held.items())
        return actual_write(self, name, value)
    held_counts = []
    actual_close = m.SourceGuard.close
    def close(self):
        held_counts.append(len(self.held))
        return actual_close(self)
    monkeypatch.setattr(m.SourceGuard, '__enter__', enter)
    monkeypatch.setattr(m.Store, 'write', write)
    monkeypatch.setattr(m.SourceGuard, 'close', close)
    outcome = m.run(args, time.monotonic() + 60)
    assert workflow.events == ['analysis', 'postflight']
    assert held_counts == [2]
    assert m.validate_output(envelope(args, outcome), 0, args)
    assert sorted(path.name for path in control.iterdir()) == ['claim.json', 'report.json', 'source-start.json']
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in control.iterdir())
    assert control.stat().st_mode & 0o777 == 0o700
    public = json.dumps(outcome)
    assert 'synthetic private' not in public
    with pytest.raises(m.Refused, match='claim_spent'):
        m.run(args, time.monotonic() + 60)


def test_source_guard_reads_once_and_no_directory_census(sources, monkeypatch):
    actual_listdir = os.listdir
    def no_source_listdir(path):
        if type(path) is int and os.fstat(path).st_ino == sources.path.stat().st_ino:
            raise AssertionError('source directory data census forbidden')
        return actual_listdir(path)
    monkeypatch.setattr(m.os, 'listdir', no_source_listdir)
    with m.SourceGuard() as guard:
        assert guard.read_once(time.monotonic() + 60) == sources.values
        with pytest.raises(m.Refused, match='source_stage'):
            guard.read_once(time.monotonic() + 60)
        assert m.validate_source(guard.receipt())


@pytest.mark.parametrize('fault', ['hash', 'size', 'mode', 'symlink', 'hardlink'])
def test_source_refuses_corrupt_or_unsafe_leaf(sources, tmp_path, fault):
    path = sources.path / 'stocks-probe.csv'
    if fault == 'hash':
        path.write_bytes(b'X' * len(sources.values[path.name]))
    elif fault == 'size':
        path.write_bytes(b'truncated')
    elif fault == 'mode':
        path.chmod(0o644)
    elif fault == 'symlink':
        destination = tmp_path / 'outside'
        destination.write_bytes(sources.values[path.name])
        path.unlink()
        path.symlink_to(destination)
    elif fault == 'hardlink':
        os.link(path, tmp_path / 'second-name')
    with pytest.raises((m.Refused, OSError)):
        with m.SourceGuard() as guard:
            guard.read_once(time.monotonic() + 60)


@pytest.mark.parametrize('fault', ['mtime', 'replacement', 'security', 'directory'])
def test_source_guard_detects_held_named_or_security_drift(sources, monkeypatch, fault):
    with pytest.raises(m.Refused, match='source_changed'):
        with m.SourceGuard() as guard:
            guard.read_once(time.monotonic() + 60)
            path = sources.path / 'funds-probe.csv'
            if fault == 'mtime':
                info = path.stat()
                os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1000))
            elif fault == 'replacement':
                raw = path.read_bytes()
                path.unlink()
                path.write_bytes(raw)
                path.chmod(0o600)
            elif fault == 'security':
                monkeypatch.setattr(m, 'security_snapshot', lambda fd: {'acl_empty': True, 'xattrs': {'opaque': 1}})
            else:
                (sources.path / 'unexpected-name').write_bytes(b'no-data-read')


def test_source_guard_detects_drift_after_analysis_before_report(control, sources, args, workflow, monkeypatch):
    actual = m.syntax.inspect_captures
    def drift(values):
        result = actual(values)
        path = sources.path / 'funds-probe.csv'
        info = path.stat()
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1000))
        return result
    monkeypatch.setattr(m.syntax, 'inspect_captures', drift)
    outcome = m.run(args, time.monotonic() + 60)
    assert outcome['failure']['failure_code'] == 'source_changed'
    assert outcome['failure']['state']['stage'] == 'analysis'
    assert m.validate_output(envelope(args, outcome), 2, args)


def test_source_security_before_any_leaf_bytes(sources, monkeypatch):
    actual = m.Store._read
    reads = []
    monkeypatch.setattr(m.Store, '_read', staticmethod(lambda fd, size: (reads.append(fd), actual(fd, size))[1]))
    monkeypatch.setattr(m, 'security_snapshot', lambda fd: (_ for _ in ()).throw(m.Refused('capture_security')))
    with pytest.raises(m.Refused, match='capture_security'):
        with m.SourceGuard():
            pass
    assert reads == []


def test_postflight_failure_retains_observation_but_never_admits(control, args, workflow):
    workflow.fail_postflight = True
    outcome = m.run(args, time.monotonic() + 60)
    assert outcome['failure']['failure_code'] == 'source_pin'
    assert outcome['failure']['state']['receipt'] == workflow.receipt
    assert m.validate_output(envelope(args, outcome), 2, args)
    with pytest.raises(m.Refused):
        m.validate_output(envelope(args, outcome), 0, args)


@pytest.mark.parametrize('actual_exit', [2, None, True, False, -1])
def test_nonzero_unknown_or_boolean_exit_never_accepts_report(control, args, workflow, actual_exit):
    outcome = m.run(args, time.monotonic() + 60)
    with pytest.raises(m.Refused):
        m.validate_output(envelope(args, outcome), actual_exit, args)


def test_late_report_failure_can_leave_report_but_actual_two_is_failure(control, args, workflow, monkeypatch):
    real = m.Store.write
    def late(self, name, value):
        result = real(self, name, value)
        if name == 'report.json':
            raise m.Refused('control_changed')
        return result
    monkeypatch.setattr(m.Store, 'write', late)
    outcome = m.run(args, time.monotonic() + 60)
    assert (control / 'report.json').exists()
    assert outcome['failure']['failure_code'] == 'control_changed'
    assert m.validate_output(envelope(args, outcome), 2, args)
    with pytest.raises(m.Refused):
        m.validate_output(envelope(args, outcome), 0, args)


@pytest.mark.parametrize('mutation', ['source_pin', 'source_metadata', 'continuous', 'receipt', 'report', 'binding', 'flags'])
def test_public_tampering_refuses(control, args, workflow, mutation):
    outcome = m.run(args, time.monotonic() + 60)
    packet = m.parse(envelope(args, outcome))
    result = packet['outcome']['result']
    if mutation == 'source_pin':
        result['source']['files']['stocks-probe.csv']['sha256'] = 'e' * 64
    elif mutation == 'source_metadata':
        result['source']['files']['stocks-probe.csv']['current_metadata_sha256'] = 'not-hash'
    elif mutation == 'continuous':
        result['source']['continuous_security_proven'] = True
    elif mutation == 'receipt':
        result['receipt']['extra'] = True
    elif mutation == 'report':
        packet['outcome']['report']['sha256'] = 'e' * 64
    elif mutation == 'binding':
        packet['binding']['expected_head'] = 'c' * 40
    else:
        result['strategy_price_admitted'] = True
    with pytest.raises((m.Refused, AssertionError)):
        m.validate_output(m.canonical(packet), 0, args)


@pytest.mark.parametrize('code', sorted(m.FINITE))
def test_finite_closed_own_codes(code):
    assert m.finite(m.Refused(code)) == code


@pytest.mark.parametrize('code', sorted(m.syntax.FINITE))
def test_finite_closed_helper_codes(code):
    assert m.finite(m.syntax.Refused(code)) == 'syntax_' + code


def test_unknown_exception_is_not_rendered():
    class Hostile(Exception):
        def __str__(self):
            raise AssertionError('must not render')
    class Foreign(m.Refused):
        pass
    assert m.finite(Hostile('secret')) == 'unknown_exception'
    assert m.finite(Foreign('source_pin')) == 'unknown_exception'


@pytest.mark.parametrize('value', [True, None, float('nan'), float('inf'), -1])
def test_deadline_shape(value):
    with pytest.raises(m.Refused, match='deadline'):
        m.remaining(value)


def test_observer_dispatches_native_producer_and_artifact_denied_validator(args, tmp_path, monkeypatch):
    monkeypatch.setattr(m, 'ROOT', tmp_path)
    (tmp_path / '.pytest_cache').mkdir()
    calls = []
    public = m.canonical({'synthetic': True})
    def capture(argv, safe, timeout, **kwargs):
        calls.append((argv, safe, timeout, kwargs))
        assert argv[0] == '/usr/bin/sandbox-exec'
        assert not any('KEY' in key or 'TOKEN' in key for key in safe)
        if len(calls) == 1:
            assert argv[2] == m.native_producer_profile() and timeout == 120
            return public, b'', {'actual_exit': 2, 'bound': None}
        assert argv[2] == m.native_validator_profile() and timeout == 20
        assert kwargs['input_bytes'] == public and argv[-1] == '2'
        return public, b'', {'actual_exit': 0, 'bound': None}
    monkeypatch.setattr(m, 'capture', capture)
    result, code = m.observe(args)
    assert code == 2 and result['output_authenticated'] is True
    assert result['parent']['actual_exit'] == 2 and len(calls) == 2


@pytest.mark.parametrize('actual', [
    {'actual_exit': None, 'bound': None}, {'actual_exit': 0, 'bound': 'timeout'},
    {'actual_exit': True, 'bound': None}])
def test_observer_parent_ambiguity_stops_without_validator(args, tmp_path, monkeypatch, actual):
    monkeypatch.setattr(m, 'ROOT', tmp_path)
    (tmp_path / '.pytest_cache').mkdir()
    calls = []
    monkeypatch.setattr(m, 'capture', lambda *a, **k: (calls.append(a), (b'{}', b'', actual))[1])
    result, code = m.observe(args)
    assert code == 2 and result['output_authenticated'] is False and len(calls) == 1


def test_real_current_security_snapshots_on_synthetic_fds(tmp_path):
    directory = tmp_path / 'security-fixture'
    directory.mkdir(mode=0o700)
    leaf = directory / 'leaf'
    leaf.write_bytes(b'synthetic')
    leaf.chmod(0o600)
    fd = os.open(leaf, os.O_RDONLY)
    try:
        snapshot = m.security_snapshot(fd)
        assert snapshot['acl_empty'] is True and type(snapshot['xattrs']) is dict
        assert m.metadata(os.fstat(fd)) == m.previous.metadata(os.fstat(fd))
    finally:
        os.close(fd)


def native_policy_probe(tmp_path, monkeypatch):
    """Run directly under clean Python, not nested inside pytest's sandbox."""
    root = tmp_path / 'synthetic-native-root'
    artifacts = root / 'artifacts'
    source = artifacts / 't-source'
    source.mkdir(parents=True, mode=0o700)
    control = artifacts / 'u-parent' / 'u-control'
    support = root / '.pytest_cache'
    support.mkdir()
    for name in ('stocks-probe.csv', 'funds-probe.csv', 'report.json'):
        (source / name).write_bytes(b'synthetic')
        (source / name).chmod(0o600)
    monkeypatch.setattr(m, 'ROOT', root)
    monkeypatch.setattr(m, 'SOURCE_DIRECTORY', source)
    monkeypatch.setattr(m, 'CONTROL', control)
    code = """import json,os,socket
from pathlib import Path
from scripts import inspect_arv2_r298_sharadar_cusip_syntax as guarded
source=Path(SOURCE)
control=Path(CONTROL)
observed={}
for name in ('stocks-probe.csv','funds-probe.csv','report.json'):
    try: observed[name]=source.joinpath(name).read_bytes()==b'synthetic'
    except PermissionError: observed[name]=False
try: os.listdir(source); observed['list']=True
except PermissionError: observed['list']=False
try: fd=os.open(source,os.O_SEARCH|os.O_NOFOLLOW); os.fstat(fd); os.close(fd); observed['metadata']=True
except PermissionError: observed['metadata']=False
guarded.CONTROL=control
with guarded.Store() as own:
    own.write('claim.json',{'synthetic':True})
    own.write('report.json',{'closed':True})
    own.verify()
    observed['own']=observed['full_store']=True
try: (control.parent/'other.json').write_bytes(b'bad'); observed['outside_write']=True
except PermissionError: observed['outside_write']=False
try: sock=socket.socket(); sock.connect(('127.0.0.1',1)); observed['network']=True
except PermissionError: observed['network']=False
try: Path('/Users/sheltonchen/Library/Keychains').stat(); observed['keychain_metadata']=True
except PermissionError: observed['keychain_metadata']=False
guarded.SOURCE_DIRECTORY=source
guarded.SOURCE_PINS={name:{'byte_count':9,'sha256':guarded.sha(b'synthetic')} for name in ('stocks-probe.csv','funds-probe.csv')}
with guarded.SourceGuard() as guard:
    observed['full_guard']=all(raw==b'synthetic' for raw in guard.read_once(guarded.time.monotonic()+60).values())
    guarded.validate_source(guard.receipt())
print(json.dumps(observed,sort_keys=True))
""".replace('source=Path(SOURCE)', 'source=Path(' + repr(str(source)) + ')') \
        .replace('control=Path(CONTROL)', 'control=Path(' + repr(str(control)) + ')')
    result = subprocess.run(['/usr/bin/sandbox-exec', '-p', m.native_producer_profile(),
        str(m.PYTHON), '-B', '-c', code], capture_output=True, timeout=10,
        env={'PATH': '/usr/bin:/bin', 'TMPDIR': str(support), 'PYTHONDONTWRITEBYTECODE': '1',
            'PYTHONPATH': str(m.SOURCE.parent.parent)})
    assert result.returncode == 0 and result.stderr == b'', (result.returncode, result.stderr)
    values = json.loads(result.stdout)
    assert values == {'stocks-probe.csv': True, 'funds-probe.csv': True,
        'report.json': False, 'list': False, 'metadata': True, 'own': True,
        'outside_write': False, 'network': False, 'keychain_metadata': False,
        'full_guard': True, 'full_store': True}, values


@pytest.mark.parametrize('field', ['space', 'comma', 'unknown'])
def test_genuine_syntax_interoperability_with_synthetic_source_pins(tmp_path, control, args, monkeypatch, field):
    from tests.analyst_revisions_v2 import test_r298_sharadar_cusip_syntax as catalog
    captures = catalog.fixture.payloads()
    funds = catalog.fixture.rows(captures['funds-probe.csv'])
    funds[1]['cusips'] = {'space': '000000001 000000002',
        'comma': '000000001, 000000002',
        'unknown': '000000001;000000002'}[field]
    captures['funds-probe.csv'] = catalog.fixture.csv_bytes(m.syntax.previous.META_FIELDS, funds)
    catalog.bind(monkeypatch, captures)
    source = tmp_path / 'fresh-synthetic-source'
    source.mkdir(mode=0o700)
    for name, raw in captures.items():
        (source / name).write_bytes(raw)
        (source / name).chmod(0o600)
    monkeypatch.setattr(m, 'SOURCE_DIRECTORY', source)
    monkeypatch.setattr(m, 'SOURCE_PINS', copy.deepcopy(m.syntax.CAPTURE_PINS))
    monkeypatch.setattr(m, 'preflight', lambda *args: None)
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: None)
    outcome = m.run(args, time.monotonic() + 60)
    assert 'result' in outcome
    receipt = outcome['result']['receipt']
    observed = receipt['probes'][2]
    assert observed['accepted'] is (field != 'unknown')
    assert observed['new_parse_count'] == (0 if field == 'unknown' else 2)
    assert all(receipt[key] is False for key in m.syntax.FALSE_FLAGS)
    assert m.validate_output(envelope(args, outcome), 0, args)
    assert b'000000001' not in envelope(args, outcome)


@pytest.mark.parametrize('fault', [None, 'branch', 'head', 'dirty', 'committed', 'selected_source'])
def test_preflight_exact_host_git_and_committed_source_bindings(monkeypatch, fault):
    actual = m.SOURCE.read_bytes()
    args = NS(expected_head='a' * 40, caller_sha256=m.sha(actual))
    monkeypatch.setattr(m.admitted.v5, '_under_test', lambda: False)
    monkeypatch.setattr(m.environment, '_require_environment', lambda: None)
    selected = 'scripts/run_arv2_r298_sharadar_probe_metadata.py'
    selected_pin = m.sha((m.ROOT / selected).read_bytes())
    monkeypatch.setattr(m, 'pins', lambda: {selected: 'f' * 64 if fault == 'selected_source' else selected_pin})
    answers = {('rev-parse', '--show-toplevel'): str(m.ROOT),
        ('branch', '--show-current'): 'wrong' if fault == 'branch' else m.admitted.frozen.BRANCH,
        ('rev-parse', 'HEAD'): 'b' * 40 if fault == 'head' else args.expected_head,
        ('status', '--porcelain'): ' M tracked.py' if fault == 'dirty' else ''}
    def git(command, deadline, *bound):
        if command[:2] == ['cat-file', 'blob']:
            return b'changed' if fault == 'committed' else actual
        return answers[tuple(command)].encode()
    monkeypatch.setattr(m.admitted.v5, '_git', git)
    if fault is None:
        m.preflight(args, time.monotonic() + 60)
    else:
        with pytest.raises(m.Refused, match='source_pin' if fault in ('committed', 'selected_source') else 'git_state'):
            m.preflight(args, time.monotonic() + 60)


def test_source_final_exit_drift_refuses_even_after_report(control, args, workflow, monkeypatch):
    real_exit = m.SourceGuard.__exit__
    def exit_after_drift(self, kind, *rest):
        path = m.SOURCE_DIRECTORY / 'stocks-probe.csv'
        info = path.stat()
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1000))
        return real_exit(self, kind, *rest)
    monkeypatch.setattr(m.SourceGuard, '__exit__', exit_after_drift)
    outcome = m.run(args, time.monotonic() + 60)
    assert (control / 'report.json').exists()
    assert outcome['failure']['state']['stage'] == 'report'
    assert outcome['failure']['failure_code'] == 'source_changed'
    assert m.validate_output(envelope(args, outcome), 2, args)


def test_source_guard_consumes_before_failed_read(sources, monkeypatch):
    with m.SourceGuard() as guard:
        actual = m.Store._read
        monkeypatch.setattr(m.Store, '_read', staticmethod(lambda *args: b'bad'))
        with pytest.raises(m.Refused, match='source_bytes'):
            guard.read_once(time.monotonic() + 60)
        monkeypatch.setattr(m.Store, '_read', staticmethod(actual))
        with pytest.raises(m.Refused, match='source_stage'):
            guard.read_once(time.monotonic() + 60)
