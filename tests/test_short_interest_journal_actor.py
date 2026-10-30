"""Fabricated streams/handles only: no eslogger, source files, flags or root action."""
import copy
import builtins
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    'journal_actor_trace', Path(__file__).parents[1] / 'scripts/trace_short_interest_journal_actor.py')
t = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(t)
HEAD = 'b' * 40
SHA = 'a' * 64


def event(seq=1, kind='setflags', flags=2, path=None, ino=71):
    body = {'target': {'path': str(t.TARGET) if path is None else path,
                       'path_truncated': False, 'stat': {'st_dev': 9, 'st_ino': ino}}}
    if kind == 'setflags':
        body['flags'] = flags
    elif kind == 'setattrlist':
        body['attrlist'] = dict(bitmapcount=5, reserved=0, commonattr=1,
                                volattr=0, dirattr=0, fileattr=0, forkattr=0)
    else:
        body.update(atime='2026-10-30T01:02:03.123456789Z', mtime='2026-10-30T01:02:04Z')
    return {'schema_version': 1, 'version': 8, 'action_type': 1,
            'global_seq_num': seq, 'event_type': t.EVENTS[kind], 'event': {kind: body},
            'time': '2026-10-30T01:02:05Z',
            'process': {'audit_token': {'pid': 123, 'pidversion': 45, 'ruid': 777},
                        'group_id': 122,
                        'executable': {'path': '/usr/libexec/example', 'path_truncated': False},
                        'signing_id': 'com.example.metadata', 'args': ['secret-argument'],
                        'env': ['SECRET=never-retain']}, 'unrelated_private': 'never-retain'}


def encoded(obj):
    return json.dumps(obj, indent=2).encode()


def test_literal_native_command_and_pure_plan(monkeypatch):
    monkeypatch.setattr(t.os, 'open', lambda *a, **k: pytest.fail('plan opened a file'))
    monkeypatch.setattr(t.subprocess, 'Popen', lambda *a, **k: pytest.fail('plan launched a process'))
    plan = t.plan(HEAD, SHA)
    assert plan['native_command'] == ['/usr/bin/eslogger', '--format', 'json',
                                      'setflags', 'setattrlist', 'utimes']
    assert plan['command'] == ['sudo', '/usr/bin/python3', '-I', '-S', '-c', t.BOOTSTRAP, HEAD, SHA]
    assert plan['maximum_seconds'] == 30
    assert plan['initial_target_wait_seconds'] == 90 and plan['maximum_total_observation_seconds'] == 120
    assert plan['source_authority'] is False
    assert plan['target_initially_absent'] == str(t.TARGET)
    assert plan['output_exclusive'] == str(t.OUTPUT)


def test_pretty_concatenated_stream_filters_before_actor_extraction_and_keeps_sequence():
    c = t.Consumer()
    unrelated = event(2, path='/private/unrelated-account-and-secret')
    unrelated['process'] = {'unrecognized_private_payload': 'discard-me'}
    stream = encoded(event(1)) + b' \n' + encoded(unrelated) + encoded(event(3, flags=64))
    for i in range(0, len(stream), 7):
        c.feed(stream[i:i + 7])
    c.finish()
    assert c.issues == [] and c.records == 3 and c.last_seq == 3
    assert [x['requested_flags'] for x in c.matches] == [2, 64]
    assert c.matches[1]['actor'] == {'pid': 123, 'pidversion': 45, 'pgid': 122,
                                    'executable': '/usr/libexec/example',
                                    'signing_id': 'com.example.metadata'}
    report = json.dumps(t.report_for(c, HEAD, SHA, -15, 0))
    for secret in ('secret-argument', 'SECRET', 'ruid', 'unrelated-account', 'discard-me', 'never-retain'):
        assert secret not in report


@pytest.mark.parametrize('kind', ['setattrlist', 'utimes'])
def test_metadata_projections_preserve_only_requested_fields(kind):
    c = t.Consumer()
    c.consume(event())
    c.consume(event(2, kind))
    if kind == 'utimes':
        assert c.matches[-1]['requested_times']['mtime'] == '2026-10-30T01:02:04Z'
    else:
        assert c.matches[-1]['attribute_bitmaps']['commonattr'] == 1
    assert 'requested_flags' not in c.matches[-1]


@pytest.mark.parametrize('mutate,code', [
    (lambda e: e.update(schema_version=2), 'schema_version'),
    (lambda e: e.update(version=4), 'message_version_or_action'),
    (lambda e: e.update(action_type=0), 'message_version_or_action'),
    (lambda e: e.update(global_seq_num=True), 'schema_integer'),
    (lambda e: e.update(event_type=26), 'event_numeric_concordance'),
    (lambda e: e['event'].update(unknown={}), 'event_union'),
    (lambda e: e['event']['setflags'].update(flags=-1), 'schema_integer'),
    (lambda e: e['event']['setflags']['target']['stat'].update(st_ino=0), 'target_inode_zero'),
    (lambda e: e['process']['audit_token'].update(pid='123'), 'schema_integer'),
    (lambda e: e['process']['executable'].update(path_truncated=True), 'actor_executable_schema'),
    (lambda e: e.update(time='/private/untrusted/path'), 'schema_time'),
])
def test_strict_consumed_schema_refuses(mutate, code):
    obj = event()
    mutate(obj)
    with pytest.raises(t.TraceRefusal, match=code):
        t.Consumer().consume(obj)


def test_gap_truncation_and_replacement_latch_without_rebasing():
    c = t.Consumer()
    c.consume(event())
    c.consume(event(4, flags=64, ino=72))
    truncated = event(5, path='/unrelated')
    truncated['event']['setflags']['target']['path_truncated'] = True
    c.consume(truncated)
    c.consume(event(6, flags=2))
    assert c.inode == (9, 71)
    assert c.issues == ['global_sequence_gap_or_reorder', 'target_inode_changed', 'truncated_target_path']
    assert t.report_for(c, HEAD, SHA, -15, 0)['status'] == 'incomplete'


def test_missing_creator_calibration_cannot_claim_closed():
    c = t.Consumer()
    c.consume(event(flags=64))
    c.consume(event(2, flags=2))
    assert c.issues == ['initial_immutable_notification_missing']


@pytest.mark.parametrize('data,code', [
    (b'{"schema_version":1,"schema_version":1}', 'duplicate_json_key'),
    (b'{"number":NaN}', 'nonfinite_json'),
    (b'{"bad":\xff}', 'invalid_json'),
    (b'[]', 'object_stream_required'),
    (b'{"bad":}', 'invalid_json'),
])
def test_malformed_stream_never_persists_raw(data, code):
    c = t.Consumer()
    with pytest.raises(t.TraceRefusal, match=code):
        c.feed(data)
    assert c.matches == []


def test_stream_truncation_and_finite_limits(monkeypatch):
    c = t.Consumer()
    c.feed(b'{"secret":"unfinished')
    c.finish()
    assert c.issues == ['truncated_json_record', 'no_records_observed', 'no_target_event_observed']
    monkeypatch.setattr(t, 'MAX_INPUT', 4)
    with pytest.raises(t.TraceRefusal, match='input_limit'):
        t.Consumer().feed(b'     ')
    monkeypatch.setattr(t, 'MAX_INPUT', 100)
    monkeypatch.setattr(t, 'MAX_RECORD', 5)
    with pytest.raises(t.TraceRefusal, match='record_limit'):
        t.Consumer().feed(b'{"long')


def test_projected_output_limit_retains_earlier_matches(monkeypatch):
    c = t.Consumer()
    c.consume(event())
    monkeypatch.setattr(t, 'MAX_PROJECTION', c.projected_bytes)
    with pytest.raises(t.TraceRefusal, match='projection_limit'):
        c.consume(event(2, flags=64))
    assert len(c.matches) == 1 and c.matches[0]['requested_flags'] == 2


class Pipe:
    def __init__(self, number):
        self.number, self.closed = number, False

    def fileno(self):
        return self.number

    def close(self):
        self.closed = True


class Child:
    def __init__(self, waits=None):
        self.stdout, self.stderr = Pipe(11), Pipe(12)
        self.calls, self.waits = [], iter(waits or [-15])
        self.pid = 900

    def poll(self):
        return None

    def terminate(self):
        self.calls.append('terminate')

    def kill(self):
        self.calls.append('kill')

    def wait(self, timeout):
        self.calls.append(('wait', timeout))
        result = next(self.waits)
        if isinstance(result, Exception):
            raise result
        return result


class Selector:
    def __init__(self):
        self.entries = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def register(self, pipe, mask, data):
        self.entries[pipe] = SimpleNamespace(fileobj=pipe, data=data)

    def unregister(self, pipe):
        del self.entries[pipe]

    def get_map(self):
        return self.entries

    def select(self, timeout):
        assert 0 < timeout <= .25
        return [(key, 1) for key in self.entries.values()]


def test_finite_supervision_uses_only_original_child_and_discards_stderr():
    c, child = t.Consumer(), Child()
    ticks = iter([0., 0., 0., 30.])
    seen = []
    def popen(*args, **kwargs):
        seen.append((args, kwargs))
        return child
    data = {11: encoded(event()), 12: b'secret-account-native-error'}
    code, stderr_count = t.supervise(c, clock=lambda: next(ticks), popen=popen,
                                      selector_factory=Selector, read=lambda fd, size: data[fd])
    assert seen[0][0] == (t.COMMAND,)
    assert seen[0][1]['env'] == {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}
    assert seen[0][1]['start_new_session'] is True and c.tracer_pid == 900
    assert child.calls == ['terminate', ('wait', 2)] and code == -15
    assert child.stdout.closed and child.stderr.closed
    assert stderr_count == len(data[12]) and c.issues == ['native_stderr_observed']
    assert 'secret-account' not in json.dumps(t.report_for(c, HEAD, SHA, code, stderr_count))


def test_timeout_escalation_is_only_original_popen_handle():
    child = Child([subprocess.TimeoutExpired('eslogger', 2), -9])
    assert t.stop_child(child) == (-9, True)
    assert child.calls == ['terminate', ('wait', 2), 'kill', ('wait', 2)]


def test_backward_clock_and_unknown_termination_remain_incomplete():
    c = t.Consumer()
    child = Child([subprocess.TimeoutExpired('eslogger', 2), subprocess.TimeoutExpired('eslogger', 2)])
    ticks = iter([2., 1.])
    code, _ = t.supervise(c, clock=lambda: next(ticks), popen=lambda *a, **k: child,
                         selector_factory=Selector)
    assert code is None
    assert 'monotonic_clock_reversed' in c.issues and 'tracer_termination_unknown' in c.issues
    assert child.stdout.closed and child.stderr.closed


@pytest.mark.parametrize('value', [float('inf'), float('nan'), -1, True])
def test_nonfinite_or_invalid_clock_before_child_dispatch(value):
    with pytest.raises(t.TraceRefusal, match='invalid_clock'):
        t.supervise(t.Consumer(), clock=lambda: value,
                    popen=lambda *a, **k: pytest.fail('launched with invalid initial clock'))


def test_initial_wait_is_finite_without_subject_and_readiness_requires_valid_event():
    c, child = t.Consumer(), Child()
    ticks = iter([0., 0., 0., 90.])
    callbacks = []
    t.supervise(c, clock=lambda: next(ticks), popen=lambda *a, **k: child,
                selector_factory=Selector, on_ready=lambda: callbacks.append('ready'),
                read=lambda fd, size: encoded(event(path='/unrelated')) if fd == 11 else b'')
    assert callbacks == ['ready'] and 'initial_target_wait_expired' in c.issues
    assert child.calls == ['terminate', ('wait', 2)]


def test_delayed_calibration_gets_only_30_seconds_after_original_event():
    c, child = t.Consumer(), Child()
    ticks = iter([0., 89., 89., 119.])
    t.supervise(c, clock=lambda: next(ticks), popen=lambda *a, **k: child,
                selector_factory=Selector,
                read=lambda fd, size: encoded(event()) if fd == 11 else b'')
    assert c.calibrated and c.issues == []
    assert child.calls == ['terminate', ('wait', 2)]


def test_late_parse_cannot_calibrate_after_initial_deadline():
    c, child = t.Consumer(), Child()
    ticks = iter([0., 89., 90.])
    callbacks = []
    t.supervise(c, clock=lambda: next(ticks), popen=lambda *a, **k: child,
                selector_factory=Selector, on_ready=lambda: callbacks.append('ready'),
                read=lambda fd, size: encoded(event()) if fd == 11 else b'')
    assert c.issues == ['initial_target_wait_expired'] and callbacks == []
    assert child.calls == ['terminate', ('wait', 2)]


def test_calibration_window_starts_after_read_not_before_select():
    c, child = t.Consumer(), Child()
    ticks = iter([0., 0., 1.5, 31.5])
    t.supervise(c, clock=lambda: next(ticks), popen=lambda *a, **k: child,
                selector_factory=Selector,
                read=lambda fd, size: encoded(event()) if fd == 11 else b'')
    assert c.issues == [] and child.calls == ['terminate', ('wait', 2)]


def test_graceful_interrupt_preserves_matches_and_stops_original_child():
    c, child = t.Consumer(), Child()
    c.consume(event())
    def interrupted_read(*args):
        raise KeyboardInterrupt
    t.supervise(c, clock=lambda: 0., popen=lambda *a, **k: child,
                selector_factory=Selector, read=interrupted_read)
    assert c.issues == ['interrupted', 'tracer_ended_before_window']
    assert len(c.matches) == 1 and child.calls == ['terminate', ('wait', 2)]


@pytest.mark.parametrize('bad', ['hash', 'mode', 'owner', 'drift', None])
def test_root_bootstrap_verifies_held_bytes_before_exec(monkeypatch, bad):
    source = b'raise RuntimeError("must not execute fixture source")'
    sha = hashlib.sha256(source).hexdigest()
    original = SimpleNamespace(st_dev=9, st_ino=71, st_uid=501, st_gid=20,
                               st_mode=0o100644, st_nlink=1, st_size=len(source),
                               st_mtime_ns=1, st_ctime_ns=2, st_flags=0)
    if bad == 'mode':
        original.st_mode = 0o100666
    if bad == 'owner':
        original.st_uid = 502
    final = copy.copy(original)
    if bad == 'drift':
        final.st_ctime_ns += 1
    stamps = iter([original, final])
    opened, executed = [], []
    monkeypatch.setattr(t.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(t.os, 'open', lambda path, flags: opened.append((path, flags)) or 77)
    monkeypatch.setattr(t.os, 'fstat', lambda fd: next(stamps))
    monkeypatch.setattr(t.os, 'stat', lambda *a, **k: SimpleNamespace(st_uid=501))
    monkeypatch.setattr(t.os, 'read', lambda fd, limit: source)
    monkeypatch.setattr(t.sys, 'argv', ['-c', HEAD, '0' * 64 if bad == 'hash' else sha])
    namespace = {'exec': lambda held_code, scope: executed.append((held_code, scope))}
    if bad is None:
        builtins.exec(t.BOOTSTRAP, namespace)
        assert len(executed) == 1 and executed[0][1]['__file__'] == str(t.ROOT / t.SCRIPT)
    else:
        with pytest.raises(SystemExit):
            builtins.exec(t.BOOTSTRAP, namespace)
        assert executed == []
    assert opened[0] == (str(t.ROOT / t.SCRIPT), t.os.O_RDONLY | t.os.O_NOFOLLOW)


def test_privilege_gate_precedes_all_opens_and_subprocesses(monkeypatch):
    monkeypatch.setattr(t.os, 'geteuid', lambda: 501)
    monkeypatch.setattr(t.os, 'open', lambda *a, **k: pytest.fail('opened before root gate'))
    monkeypatch.setattr(t.subprocess, 'check_output', lambda *a, **k: pytest.fail('git before root gate'))
    with pytest.raises(t.TraceRefusal, match='root_macos_required'):
        t.root_trace(HEAD, SHA)


def test_absence_means_any_entry_not_only_regular_file(monkeypatch):
    monkeypatch.setattr(t.os, 'stat', lambda *a, **k: SimpleNamespace(st_mode=stat.S_IFLNK))
    with pytest.raises(t.TraceRefusal, match='reserved_name_exists'):
        t.absent('subject.json', 31)
    def absent(*args, **kwargs):
        assert kwargs == {'dir_fd': 31, 'follow_symlinks': False}
        raise FileNotFoundError
    monkeypatch.setattr(t.os, 'stat', absent)
    t.absent('subject.json', 31)


def info(ino=1, mode=0o40700, size=0, uid=501):
    return SimpleNamespace(st_dev=9, st_ino=ino, st_uid=uid, st_gid=20,
                           st_mode=mode, st_nlink=1, st_size=size)


@pytest.mark.parametrize('bad', [info(mode=0o40755), info(uid=0)])
def test_directory_protection_never_adopts_drift(monkeypatch, bad):
    monkeypatch.setattr(t.os, 'open', lambda *a, **k: 31)
    monkeypatch.setattr(t.os, 'fstat', lambda fd: bad)
    closed = []
    monkeypatch.setattr(t.os, 'close', closed.append)
    with pytest.raises(t.TraceRefusal, match='private_directory_protection'):
        t.open_directory(t.TRACE_DIR, 501, 20)
    assert closed == [31]


@pytest.mark.parametrize('failure', ['guard', 'directory', 'publication', 'guard_and_close'])
def test_post_observation_failure_retains_only_projected_evidence(monkeypatch, failure):
    monkeypatch.setattr(t.sys, 'platform', 'darwin')
    monkeypatch.setattr(t.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(t, 'ROOT', SimpleNamespace(stat=lambda: info()))
    guards = []
    def guard(*args):
        guards.append(args)
        if len(guards) > 1 and failure.startswith('guard'):
            raise t.TraceRefusal('lane_git_binding')
    monkeypatch.setattr(t, 'guard', guard)
    directories = iter([31, 32])
    monkeypatch.setattr(t, 'open_directory', lambda *a: next(directories))
    monkeypatch.setattr(t, 'absent', lambda *a: None)
    opens, owners, closed = [], [], []
    def open_output(name, flags, mode, dir_fd):
        opens.append((name, flags, mode, dir_fd))
        return 33
    monkeypatch.setattr(t.os, 'open', open_output)
    monkeypatch.setattr(t.os, 'fchown', lambda *a: owners.append(a))
    monkeypatch.setattr(t.os, 'fchmod', lambda *a: None)
    monkeypatch.setattr(t.os, 'fstat', lambda fd: info(ino=fd, mode=0o100600 if fd == 33 else 0o40700))
    monkeypatch.setattr(t.os, 'stat', lambda path, **kw: info(
        ino=99 if failure == 'directory' else (31 if path == t.TRACE_DIR else 32)))
    def close(fd):
        closed.append(fd)
        if failure == 'guard_and_close' and fd == 33:
            raise OSError('private exception text must never be emitted')
    monkeypatch.setattr(t.os, 'close', close)
    def observed(consumer, **kwargs):
        consumer.consume(event())
        consumer.consume(event(2, flags=64))
        return -15, 0
    monkeypatch.setattr(t, 'supervise', observed)
    with pytest.raises(t.EvidenceRefusal) as caught:
        t.root_trace(HEAD, SHA)
    report = caught.value.report
    assert report['status'] == 'incomplete' and len(report['matched_events']) == 2
    if failure == 'guard_and_close':
        assert 'resource_cleanup_failed' in report['issues']
    assert report['matched_events'][-1]['requested_flags'] == 64
    assert 'secret-argument' not in json.dumps(report)
    assert owners == [(33, 501, 20)] and sorted(closed) == [31, 32, 33]
    assert opens[0][0] == 'trace.private.json' and opens[0][2:] == (0o600, 31)
    assert opens[0][1] & t.os.O_EXCL and opens[0][1] & t.os.O_NOFOLLOW


def test_successful_root_trace_writes_only_fixed_owned_output_and_returns_original_digest(monkeypatch, capsys):
    monkeypatch.setattr(t.sys, 'platform', 'darwin')
    monkeypatch.setattr(t.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(t, 'ROOT', SimpleNamespace(stat=lambda: info()))
    guards, absent, opened, owned, modes, synced, closed = [], [], [], [], [], [], []
    written = bytearray()
    monkeypatch.setattr(t, 'guard', lambda *args: guards.append(args))
    directories = iter([31, 32])
    monkeypatch.setattr(t, 'open_directory', lambda *a: next(directories))
    monkeypatch.setattr(t, 'absent', lambda *args: absent.append(args))
    def open_output(name, flags, mode, dir_fd):
        opened.append((name, flags, mode, dir_fd))
        return 33
    monkeypatch.setattr(t.os, 'open', open_output)
    monkeypatch.setattr(t.os, 'fchown', lambda *args: owned.append(args))
    monkeypatch.setattr(t.os, 'fchmod', lambda *args: modes.append(args))
    monkeypatch.setattr(t.os, 'fstat', lambda fd: info(ino=fd, mode=0o100600 if fd == 33 else 0o40700))
    def named(path, **kwargs):
        if path == t.OUTPUT.name:
            assert kwargs == {'dir_fd': 31, 'follow_symlinks': False}
            return info(ino=33, mode=0o100600)
        return info(ino=31 if path == t.TRACE_DIR else 32)
    monkeypatch.setattr(t.os, 'stat', named)
    def write(fd, data):
        assert fd == 33
        count = min(len(data), 137)  # Exercise partial writes.
        written.extend(data[:count])
        return count
    monkeypatch.setattr(t.os, 'write', write)
    monkeypatch.setattr(t.os, 'fsync', synced.append)
    monkeypatch.setattr(t.os, 'pread', lambda fd, length, offset: bytes(written))
    monkeypatch.setattr(t.os, 'close', closed.append)
    def observed(consumer, on_ready):
        consumer.tracer_pid = 900
        consumer.consume(event())
        on_ready()
        consumer.consume(event(2, flags=64))
        return -15, 0
    monkeypatch.setattr(t, 'supervise', observed)
    result = t.root_trace(HEAD, SHA)
    report = json.loads(written)
    assert result['status'] == 'bounded_observation_closed' and result['matches'] == 2
    assert result['original_report_sha256'] == hashlib.sha256(written).hexdigest()
    assert result['original_report_bytes'] == len(written)
    assert report['source_authority'] is False and report['tracer_pgid'] == 900
    assert report['matched_events'][-1]['requested_flags'] == 64
    assert 'secret-argument' not in written.decode() and 'SECRET=' not in written.decode()
    assert guards == [(HEAD, SHA), (HEAD, SHA)]
    assert absent == [('subject.json', 32), ('trace.private.json', 31)]
    assert opened == [('trace.private.json', t.os.O_RDWR | t.os.O_CREAT | t.os.O_EXCL | t.os.O_NOFOLLOW, 0o600, 31)]
    assert owned == [(33, 501, 20)] and modes == [(33, 0o600)]
    assert synced == [33] and closed == [33, 32, 31]
    ready = json.loads(capsys.readouterr().out)
    assert ready == {'status': 'tracer_stream_ready', 'source_authority': False,
                     'tracer_pid': 900, 'tracer_pgid': 900}


@pytest.mark.parametrize('bad', ['dirty', 'head', 'branch', 'code'])
def test_clean_committed_exact_binding_before_dispatch(monkeypatch, bad):
    original_root = t.ROOT
    source = b'fabricated committed helper'
    sha = hashlib.sha256(source).hexdigest()
    monkeypatch.setattr(t.Path, 'cwd', lambda: original_root)
    monkeypatch.setattr(t.Path, 'resolve', lambda self: self)
    monkeypatch.setattr(t.Path, 'read_bytes', lambda self: source)
    def git(command, **kwargs):
        assert 'safe.directory=' + str(original_root) in command
        assert 'core.fsmonitor=false' in command and kwargs['env'] == t.ENV
        if command[-1] == '--show-toplevel':
            return str(original_root).encode()
        if command[-1] == '--show-current':
            return b'other' if bad == 'branch' else t.BRANCH.encode()
        if command[-1] == 'HEAD':
            return b'0' * 40 if bad == 'head' else HEAD.encode()
        if '--porcelain=v1' in command:
            return b' M other.py' if bad == 'dirty' else b''
        return b'other source' if bad == 'code' else source
    monkeypatch.setattr(t.subprocess, 'check_output', git)
    with pytest.raises(t.TraceRefusal, match='lane_git_binding|committed_code_binding'):
        t.guard(HEAD, sha)
