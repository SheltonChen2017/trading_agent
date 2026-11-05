"""Fabricated streams/handles only: no eslogger, source files, flags or root action."""
import copy
import builtins
import errno
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
from types import SimpleNamespace

import pytest
import os

# Only protected-I/O cases require POSIX; pure parsing, transport and early
# refusal checks must remain active on the supported Windows host.
_POSIX_CAPTURE_ONLY = pytest.mark.skipif(
    not hasattr(os, "getuid"),
    reason=(
        "the protected-capture runtime requires POSIX ownership and mode "
        "semantics (os.getuid, O_NOFOLLOW, 0o600/0o700, symlinks); it cannot "
        "execute on this host, see the lane record SI-CR17-002"
    ),
)

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
@_POSIX_CAPTURE_ONLY
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


@_POSIX_CAPTURE_ONLY
def test_privilege_gate_precedes_all_opens_and_subprocesses(monkeypatch):
    monkeypatch.setattr(t.os, 'geteuid', lambda: 501)
    monkeypatch.setattr(t.os, 'open', lambda *a, **k: pytest.fail('opened before root gate'))
    monkeypatch.setattr(t.subprocess, 'check_output', lambda *a, **k: pytest.fail('git before root gate'))
    with pytest.raises(t.TraceRefusal, match='root_macos_required'):
        t.root_trace(HEAD, SHA)


@_POSIX_CAPTURE_ONLY
def test_absence_means_any_entry_not_only_regular_file(monkeypatch):
    monkeypatch.setattr(t.os, 'stat', lambda *a, **k: SimpleNamespace(st_mode=stat.S_IFLNK))
    with pytest.raises(t.TraceRefusal, match='reserved_name_exists'):
        t.absent('subject.json', 31)
    def absent(*args, **kwargs):
        assert kwargs == {'dir_fd': 31, 'follow_symlinks': False}
        raise FileNotFoundError
    monkeypatch.setattr(t.os, 'stat', absent)
    t.absent('subject.json', 31)


def info(ino=1, mode=0o40700, size=0, uid=501, links=None, clock=1, flags=0):
    return SimpleNamespace(st_dev=9, st_ino=ino, st_uid=uid, st_gid=20,
                           st_mode=mode, st_nlink=(2 if stat.S_ISDIR(mode) else 1)
                           if links is None else links, st_size=size,
                           st_mtime_ns=clock, st_ctime_ns=clock, st_flags=flags)


class RootWorld:
    """Fabricated all-entry-count filesystem, never actual trace or files."""

    def __init__(self, monkeypatch):
        # Isolate fake filesystem calls to the helper. An expected causal
        # failure must not poison pytest's own traceback/fixture cleanup.
        real_os = t.os
        monkeypatch.setattr(t, 'os', SimpleNamespace(**{
            name: getattr(real_os, name) for name in dir(real_os) if not name.startswith('__')}))
        class ObservedPath(type(Path())):
            def resolve(self):
                return self
        for name in ('TRACE_DIR', 'TARGET', 'OUTPUT'):
            monkeypatch.setattr(t, name, ObservedPath(getattr(t, name)))
        self.trace_names = {'trace.private.json'}  # Preserve the old spent result.
        self.subject_names = set()
        self.trace_ino, self.subject_ino, self.output_ino, self.target_ino = 31, 32, 33, 71
        self.trace_link_drift = self.subject_link_drift = 0
        self.output_clock = 1
        self.target_mode, self.target_uid, self.target_links = 0o100600, 501, 1
        self.written = bytearray()
        self.guards, self.absent, self.opened, self.owned = [], [], [], []
        self.modes, self.synced, self.closed = [], [], []
        self.guard_fails = self.close_fails = False
        self.after_output_close = lambda: None
        monkeypatch.setattr(t.sys, 'platform', 'darwin')
        monkeypatch.setattr(t.os, 'geteuid', lambda: 0)
        monkeypatch.setattr(t, 'ROOT', SimpleNamespace(stat=lambda: info()))
        monkeypatch.setattr(t, 'guard', self.guard)
        monkeypatch.setattr(t, 'open_directory', lambda path, *a: 31 if path == t.TRACE_DIR else 32)
        monkeypatch.setattr(t, 'absent', self.require_absent)
        monkeypatch.setattr(t.os, 'open', self.open_output)
        monkeypatch.setattr(t.os, 'fchown', lambda *a: self.owned.append(a))
        monkeypatch.setattr(t.os, 'fchmod', lambda *a: self.modes.append(a))
        monkeypatch.setattr(t.os, 'fstat', self.fstat)
        monkeypatch.setattr(t.os, 'stat', self.named)
        monkeypatch.setattr(t.os, 'listdir', self.listdir)
        monkeypatch.setattr(t.os, 'write', self.write)
        monkeypatch.setattr(t.os, 'fsync', self.synced.append)
        monkeypatch.setattr(t.os, 'pread', lambda *a: bytes(self.written))
        monkeypatch.setattr(t.os, 'close', self.close)

    def guard(self, *args):
        self.guards.append(args)
        if self.guard_fails and len(self.guards) > 1:
            raise t.TraceRefusal('lane_git_binding')

    def listdir(self, value):
        if value in (31, t.TRACE_DIR):
            return list(self.trace_names)
        assert value in (32, t.TARGET.parent)
        return list(self.subject_names)

    def require_absent(self, name, fd):
        self.absent.append((name, fd))
        assert name not in self.listdir(fd)

    def open_output(self, name, flags, mode, dir_fd):
        self.opened.append((name, flags, mode, dir_fd))
        assert name == 'trace-v2.private.json' and dir_fd == 31 and name not in self.trace_names
        self.trace_names.add(name)
        return 33

    def fstat(self, fd):
        assert fd not in self.closed
        if fd == 31:
            return info(self.trace_ino, links=len(self.trace_names) + 2 + self.trace_link_drift)
        if fd == 32:
            return info(self.subject_ino, links=len(self.subject_names) + 2 + self.subject_link_drift)
        assert fd == 33
        return info(self.output_ino, mode=0o100600, size=len(self.written), clock=self.output_clock)

    def named(self, path, **kwargs):
        if path == t.TRACE_DIR:
            return info(self.trace_ino, links=len(self.trace_names) + 2 + self.trace_link_drift)
        if path == t.TARGET.parent:
            return info(self.subject_ino, links=len(self.subject_names) + 2 + self.subject_link_drift)
        if path in (t.OUTPUT, t.OUTPUT.name):
            return info(self.output_ino, mode=0o100600, size=len(self.written), clock=self.output_clock)
        assert path in (t.TARGET, t.TARGET.name)
        if t.TARGET.name not in self.subject_names:
            raise FileNotFoundError
        return info(self.target_ino, mode=self.target_mode, uid=self.target_uid,
                    links=self.target_links)

    def write(self, fd, data):
        assert fd == 33
        count = min(len(data), 137)
        self.written.extend(data[:count])
        self.output_clock += 1
        return count

    def close(self, fd):
        self.closed.append(fd)
        if fd == 33:
            self.after_output_close()
            if self.close_fails:
                raise OSError('PRIVATE arbitrary close detail')

    def observed(self, consumer, on_ready=lambda: None):
        self.subject_names.add(t.TARGET.name)
        consumer.tracer_pid = 900
        consumer.consume(event())
        on_ready()
        consumer.consume(event(2, flags=64))
        return -15, 0


@pytest.mark.parametrize('bad', [info(mode=0o40755), info(uid=0)])
@_POSIX_CAPTURE_ONLY
def test_directory_protection_never_adopts_drift(monkeypatch, bad):
    monkeypatch.setattr(t.os, 'open', lambda *a, **k: 31)
    monkeypatch.setattr(t.os, 'fstat', lambda fd: bad)
    closed = []
    monkeypatch.setattr(t.os, 'close', closed.append)
    with pytest.raises(t.TraceRefusal, match='private_directory_protection'):
        t.open_directory(t.TRACE_DIR, 501, 20)
    assert closed == [31]


@pytest.mark.parametrize('failure', ['guard', 'directory', 'publication', 'guard_and_close'])
@_POSIX_CAPTURE_ONLY
def test_post_observation_failure_retains_only_projected_evidence(monkeypatch, failure):
    world = RootWorld(monkeypatch)
    world.guard_fails = failure.startswith('guard')
    world.close_fails = failure == 'guard_and_close'
    def observed(consumer, **kwargs):
        result = world.observed(consumer)
        if failure == 'directory': world.trace_ino = 99
        if failure == 'publication': world.output_ino = 99
        return result
    monkeypatch.setattr(t, 'supervise', observed)
    with pytest.raises(t.EvidenceRefusal) as caught:
        t.root_trace(HEAD, SHA)
    report = caught.value.report
    assert report['status'] == 'incomplete' and len(report['matched_events']) == 2
    if failure == 'guard_and_close':
        assert 'resource_cleanup_failed' in report['issues']
    assert report['matched_events'][-1]['requested_flags'] == 64
    assert 'secret-argument' not in json.dumps(report)
    assert 'PRIVATE' not in json.dumps(report)
    assert report['terminal_failure']['contract_code'] in ('lane_git_binding', 'directory_changed',
                                                          'output_creator_identity_changed')
    assert world.owned == [(33, 501, 20)] and sorted(world.closed) == [31, 32, 33]
    assert world.opened[0][0] == 'trace-v2.private.json' and world.opened[0][2:] == (0o600, 31)
    assert world.opened[0][1] & t.os.O_EXCL and world.opened[0][1] & t.os.O_NOFOLLOW


@_POSIX_CAPTURE_ONLY
def test_successful_root_trace_writes_only_fixed_owned_output_and_returns_original_digest(monkeypatch, capsys):
    world = RootWorld(monkeypatch)
    monkeypatch.setattr(t, 'supervise', world.observed)
    result = t.root_trace(HEAD, SHA)
    report = json.loads(world.written)
    assert result['status'] == 'bounded_observation_closed' and result['matches'] == 2
    assert result['original_report_sha256'] == hashlib.sha256(world.written).hexdigest()
    assert result['original_report_bytes'] == len(world.written)
    assert report['source_authority'] is False and report['tracer_pgid'] == 900
    assert report['matched_events'][-1]['requested_flags'] == 64
    assert 'secret-argument' not in world.written.decode() and 'SECRET=' not in world.written.decode()
    assert world.guards == [(HEAD, SHA)] * 3
    assert world.absent == [('subject.json', 32), ('trace-v2.private.json', 31)]
    assert world.opened == [('trace-v2.private.json', t.os.O_RDWR | t.os.O_CREAT | t.os.O_EXCL | t.os.O_NOFOLLOW, 0o600, 31)]
    assert world.owned == [(33, 501, 20)] and world.modes == [(33, 0o600)]
    assert world.synced == [33] and world.closed == [33, 32, 31]
    assert world.trace_names == {'trace.private.json', 'trace-v2.private.json'}
    assert world.subject_names == {'subject.json'}
    ready = json.loads(capsys.readouterr().out)
    assert ready == {'status': 'tracer_stream_ready', 'source_authority': False,
                     'tracer_pid': 900, 'tracer_pgid': 900}


@_POSIX_CAPTURE_ONLY
def test_native_failure_publishes_negative_under_owned_nlink_transition_without_creating_subject(monkeypatch):
    world = RootWorld(monkeypatch)
    def failed_native(consumer, **kwargs):
        consumer.tracer_pid = 900
        for code in ('tracer_exit_unsuccessful', 'native_stderr_observed'):
            consumer.issue(code)
        consumer.finish()
        return 1, 168
    monkeypatch.setattr(t, 'supervise', failed_native)
    result = t.root_trace(HEAD, SHA)
    report = json.loads(world.written)
    assert result['status'] == report['status'] == 'incomplete'
    assert report['native_stderr_claim']['classification'] == 'unclassified_native_stderr'
    assert report['native_stderr_claim']['codes'] == []
    assert report['terminal_failure'] is report['cleanup_failure'] is None
    assert world.subject_names == set() and world.closed == [33, 32, 31]
    assert world.trace_names == {'trace.private.json', 'trace-v2.private.json'}


@pytest.mark.parametrize('place', ['trace', 'subject'])
@pytest.mark.parametrize('mutation', ['extra_entry', 'link_only_drift'])
@_POSIX_CAPTURE_ONLY
def test_unowned_namespace_or_link_change_is_never_rebaselined(monkeypatch, place, mutation):
    world = RootWorld(monkeypatch)
    def observed(consumer, **kwargs):
        result = world.observed(consumer)
        if mutation == 'extra_entry':
            (world.trace_names if place == 'trace' else world.subject_names).add('PRIVATE-unowned-name')
        elif place == 'trace':
            world.trace_link_drift += 1
        else:
            world.subject_link_drift += 1
        return result
    monkeypatch.setattr(t, 'supervise', observed)
    with pytest.raises(t.EvidenceRefusal) as caught:
        t.root_trace(HEAD, SHA)
    report = caught.value.report
    expected = 'directory_membership_changed' if mutation == 'extra_entry' else 'directory_creation_count'
    assert report['terminal_failure']['contract_code'] == expected
    assert report['terminal_failure']['stage'] == 'terminal_' + place + '_directory_audit'
    assert len(report['matched_events']) == 2 and report['source_authority'] is False
    assert 'PRIVATE' not in json.dumps(report)


@pytest.mark.parametrize('bad', ['deleted', 'replaced', 'mode', 'owner', 'links'])
@_POSIX_CAPTURE_ONLY
def test_reserved_target_needs_original_calibration_inode_and_protection(monkeypatch, bad):
    world = RootWorld(monkeypatch)
    def observed(consumer, **kwargs):
        result = world.observed(consumer)
        if bad == 'deleted': world.subject_names.remove(t.TARGET.name)
        elif bad == 'replaced': world.target_ino = 999
        elif bad == 'mode': world.target_mode = 0o100644
        elif bad == 'owner': world.target_uid = 999
        else: world.target_links = 2
        return result
    monkeypatch.setattr(t, 'supervise', observed)
    with pytest.raises(t.EvidenceRefusal) as caught:
        t.root_trace(HEAD, SHA)
    report = caught.value.report
    expected = ('target_unseen_or_deleted' if bad == 'deleted' else
                'target_original_inode_changed' if bad == 'replaced' else 'target_protection_changed')
    assert report['terminal_failure']['contract_code'] == expected
    assert len(report['matched_events']) == 2
    assert world.closed == [33, 32, 31]


@_POSIX_CAPTURE_ONLY
def test_subject_creation_without_valid_native_calibration_is_not_adopted(monkeypatch):
    world = RootWorld(monkeypatch)
    def unobserved(consumer, **kwargs):
        world.subject_names.add(t.TARGET.name)
        consumer.finish()
        return 1, 0
    monkeypatch.setattr(t, 'supervise', unobserved)
    with pytest.raises(t.EvidenceRefusal) as caught:
        t.root_trace(HEAD, SHA)
    assert caught.value.report['terminal_failure']['contract_code'] == 'target_unseen_or_deleted'


@_POSIX_CAPTURE_ONLY
def test_wrong_precreation_count_refuses_before_output_or_native_dispatch(monkeypatch):
    world = RootWorld(monkeypatch)
    world.trace_link_drift = 1
    monkeypatch.setattr(t, 'supervise', lambda *a, **k: pytest.fail('dispatched after invalid pre-count'))
    with pytest.raises(t.EvidenceRefusal) as caught:
        t.root_trace(HEAD, SHA)
    assert caught.value.report['terminal_failure']['contract_code'] == 'directory_count_contract'
    assert world.opened == [] and world.trace_names == {'trace.private.json'}


@_POSIX_CAPTURE_ONLY
def test_deleting_an_old_entry_is_not_hidden_by_owned_addition(monkeypatch):
    world = RootWorld(monkeypatch)
    def observed(consumer, **kwargs):
        result = world.observed(consumer)
        world.trace_names.remove('trace.private.json')
        return result
    monkeypatch.setattr(t, 'supervise', observed)
    with pytest.raises(t.EvidenceRefusal) as caught:
        t.root_trace(HEAD, SHA)
    assert caught.value.report['terminal_failure']['contract_code'] == 'directory_membership_changed'


@pytest.mark.parametrize('mutation', ['output', 'target', 'directory'])
@_POSIX_CAPTURE_ONLY
def test_final_named_audit_outlives_all_owned_handle_closes(monkeypatch, mutation):
    world = RootWorld(monkeypatch)
    monkeypatch.setattr(t, 'supervise', world.observed)
    def after_close():
        if mutation == 'output': world.output_clock += 1
        elif mutation == 'target': world.target_ino += 1
        else: world.trace_link_drift += 1
    world.after_output_close = after_close
    with pytest.raises(t.EvidenceRefusal) as caught:
        t.root_trace(HEAD, SHA)
    report = caught.value.report
    assert report['terminal_failure'] is None
    assert report['cleanup_failure']['stage'] == 'post_close_original_audit'
    assert report['cleanup_failure']['contract_code'] == {
        'output': 'post_close_output_changed', 'target': 'target_original_inode_changed',
        'directory': 'directory_creation_count'}[mutation]
    assert 'post_close_original_audit_failed' in report['issues']
    assert world.closed == [33, 32, 31] and len(report['matched_events']) == 2


@pytest.mark.parametrize('trigger', ['subject_directory', 'output'])
@_POSIX_CAPTURE_ONLY
def test_last_target_check_follows_directory_and_other_file_audits(monkeypatch, trigger):
    world = RootWorld(monkeypatch)
    monkeypatch.setattr(t, 'supervise', world.observed)
    state = {'armed': False, 'changed': False}
    world.after_output_close = lambda: state.update(armed=True)
    original_named = t.os.stat
    def replace_after_named(path, **kwargs):
        result = original_named(path, **kwargs)
        match = path == (t.TARGET.parent if trigger == 'subject_directory' else t.OUTPUT)
        if state['armed'] and not state['changed'] and match:
            world.target_ino = 999
            state['changed'] = True
        return result
    monkeypatch.setattr(t.os, 'stat', replace_after_named)
    with pytest.raises(t.EvidenceRefusal) as caught:
        t.root_trace(HEAD, SHA)
    report = caught.value.report
    assert state['changed'] and report['terminal_failure'] is None
    assert report['cleanup_failure']['contract_code'] == 'target_original_inode_changed'
    assert report['cleanup_failure']['stage'] == 'post_close_original_audit'
    assert world.closed == [33, 32, 31]


@pytest.mark.parametrize('literal,code', sorted(t._NATIVE_ENUMS.items()))
def test_native_claim_literals_are_chunk_safe_and_never_forensic_cause(literal, code):
    raw = b'PRIVATE-account/path ' + literal + b' description not retained'
    for split in range(len(raw) + 1):
        claims = t.NativeClaims()
        claims.feed(raw[:split]); claims.feed(raw[split:]); claims.finish()
        payload = claims.to_payload(len(raw))
        assert payload == {'classification': 'one_allowlisted_native_literal_claim',
                           'codes': [code], 'forensic_cause_verified': False}
        assert claims.token == b'' and 'PRIVATE' not in json.dumps(payload)


@pytest.mark.parametrize('raw,classification', [
    (b'PRIVATE unknown native failure', 'unclassified_native_stderr'),
    (b'ES_NEW_CLIENT_RESULT_ERR_NOT_PERMITTED_EXTRA', 'ambiguous_or_unknown_native_claim'),
    (b'ES_NEW_CLIENT_RESULT_ERR_NOT_PERMITTEDevil', 'ambiguous_or_unknown_native_claim'),
    (b'evilES_NEW_CLIENT_RESULT_ERR_NOT_PERMITTED', 'unclassified_native_stderr'),
    (b'ES_NEW_CLIENT_RESULT_' + b'X' * 4096, 'ambiguous_or_unknown_native_claim'),
    (b'ES_NEW_CLIENT_RESULT_ERR_NOT_PERMITTED ES_NEW_CLIENT_RESULT_ERR_NOT_ENTITLED',
     'ambiguous_or_unknown_native_claim'),
    (b'ES_NEW_CLIENT_RESULT_SUCCESS', 'ambiguous_or_unknown_native_claim'),
])
def test_unknown_conflicting_or_extended_native_literals_stay_unclassified_or_ambiguous(raw, classification):
    claims = t.NativeClaims()
    for value in raw: claims.feed(bytes((value,)))
    claims.finish()
    assert claims.to_payload(len(raw))['classification'] == classification
    assert claims.to_payload(len(raw))['forensic_cause_verified'] is False
    assert len(claims.token) == 0


@pytest.mark.parametrize('error,category,contract,err', [
    (t.TraceRefusal('directory_changed'), 'local_contract_refusal', 'directory_changed', None),
    (t.TraceRefusal('PRIVATE unknown contract'), 'unclassified_local_failure', None, None),
    (OSError(errno.EACCES, 'PRIVATE path'), 'local_os_refusal', None, 'EACCES'),
    (OSError(987654, 'PRIVATE path'), 'local_os_refusal', None, None),
    (subprocess.CalledProcessError(1, ['PRIVATE command']), 'local_subprocess_refusal', None, None),
    (KeyboardInterrupt(), 'interrupted', None, None),
])
def test_terminal_failures_emit_only_fixed_category_contract_errno_and_entered_stage(error, category, contract, err):
    payload = t.fixed_failure(error, 'output_write')
    assert payload == {'stage': 'output_write', 'category': category,
                       'contract_code': contract, 'errno': err}
    assert 'PRIVATE' not in json.dumps(payload)
    assert t.fixed_failure(error, 'PRIVATE stage')['stage'] == 'unknown_stage'


@pytest.mark.parametrize('bad', ['dirty', 'head', 'branch', 'code'])
@_POSIX_CAPTURE_ONLY
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
