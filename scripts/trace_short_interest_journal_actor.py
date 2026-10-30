"""One fixed, source-free macOS metadata-actor trace; never source admission.

Run only after owner-admin authorization. This does not create the subject or
change flags, privacy settings, daemons, source files, claims, or budgets.
The JSON adapter is intentionally versioned: unfamiliar output is incomplete.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import shlex
import stat
import subprocess
import sys
import time

ROOT = Path('/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest')
BRANCH = 'codex/strategy-short-interest'
SCRIPT = 'scripts/trace_short_interest_journal_actor.py'
TRACE_DIR = ROOT / 'artifacts/short_interest/private/custody_attribution/journal-20261030-v1'
TARGET = TRACE_DIR / 'exec/subject.json'
OUTPUT = TRACE_DIR / 'trace.private.json'
COMMAND = ('/usr/bin/eslogger', '--format', 'json', 'setflags', 'setattrlist', 'utimes')
ENV = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}
MAX_SECONDS = 30.0
INITIAL_TARGET_WAIT = 90.0
MAX_INPUT = 8 * 1024 * 1024
MAX_RECORD = 64 * 1024
MAX_STDERR = 4096
MAX_MATCHES = 256
MAX_OUTPUT = 1024 * 1024
MAX_PROJECTION = MAX_OUTPUT - 65536
# Apple's installed ESTypes.h (SHA b25c5f75474afd1dba841e7cbb8510a64077806175a29187395e81023c55f51a).
# These notification enum values are concordant with their semantic union keys.
EVENTS = {'setattrlist': 26, 'setflags': 28, 'utimes': 59}
TIME = re.compile(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?(?:Z|[+-]\d\d:\d\d)\Z')
# This literal is executed by isolated root Python BEFORE any repository code.
# It executes only the exact held bytes whose SHA the owner reviewed.
BOOTSTRAP = """import hashlib,os,re,stat,sys
p=%r
h,s=sys.argv[1:]
if os.geteuid()!=0 or re.fullmatch('[0-9a-f]{40}',h) is None or re.fullmatch('[0-9a-f]{64}',s) is None: raise SystemExit(2)
f=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
a=os.fstat(f)
if not stat.S_ISREG(a.st_mode) or a.st_nlink!=1 or a.st_uid==0 or a.st_uid!=os.stat(%r,follow_symlinks=False).st_uid or a.st_mode&0o022 or a.st_size>65536: raise SystemExit(2)
b=os.read(f,65537)
z=os.fstat(f)
pin=lambda q:(q.st_dev,q.st_ino,q.st_uid,q.st_gid,q.st_mode,q.st_nlink,q.st_size,q.st_mtime_ns,q.st_ctime_ns,getattr(q,'st_flags',0))
if pin(a)!=pin(z) or len(b)!=a.st_size or hashlib.sha256(b).hexdigest()!=s: raise SystemExit(2)
sys.argv=[p,'root-trace','--head',h,'--code-sha256',s]
exec(compile(b,p,'exec'),{'__name__':'__main__','__file__':p})
""" % (str(ROOT / SCRIPT), str(ROOT))


class TraceRefusal(Exception):
    """Only fixed local codes, never exception text, may leave this helper."""


class EvidenceRefusal(Exception):
    """Keep bounded, already projected evidence if safe publication later fails."""

    def __init__(self, report):
        self.report = report


def require(ok, code):
    if not ok:
        raise TraceRefusal(code)


def uint(value, bits=64):
    require(type(value) is int and 0 <= value < 2 ** bits, 'schema_integer')
    return value


def string(value, maximum=4096):
    require(type(value) is str and 0 < len(value) <= maximum and
            all(ord(c) >= 32 for c in value), 'schema_string')
    return value


def timestamp(value):
    value = string(value, 64)
    require(TIME.fullmatch(value) is not None, 'schema_time')
    return value


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'duplicate_json_key')
        result[key] = value
    return result


class Consumer:
    """Bounded object-stream framing; unrelated rows are never persisted."""

    def __init__(self):
        self.buffer = bytearray()
        self.depth = 0
        self.quoted = self.escaped = False
        self.total = self.records = 0
        self.last_seq = self.first_seq = None
        self.inode = None
        self.tracer_pid = None
        self.calibrated = False
        self.matches = []
        self.projected_bytes = 0
        self.issues = []

    def issue(self, code):
        if code not in self.issues:
            self.issues.append(code)

    def feed(self, data):
        self.total += len(data)
        require(self.total <= MAX_INPUT, 'input_limit')
        for byte in data:
            if not self.buffer and byte in b' \n\r\t':
                continue
            require(bool(self.buffer) or byte == 123, 'object_stream_required')
            self.buffer.append(byte)
            require(len(self.buffer) <= MAX_RECORD, 'record_limit')
            if self.quoted:
                if self.escaped:
                    self.escaped = False
                elif byte == 92:
                    self.escaped = True
                elif byte == 34:
                    self.quoted = False
            elif byte == 34:
                self.quoted = True
            elif byte in (123, 91):
                self.depth += 1
                require(self.depth <= 32, 'nesting_limit')
            elif byte in (125, 93):
                self.depth -= 1
                require(self.depth >= 0, 'json_structure')
                if self.depth == 0:
                    try:
                        obj = json.loads(self.buffer.decode('utf-8'), object_pairs_hook=pairs,
                                         parse_constant=lambda _: require(False, 'nonfinite_json'))
                    except (UnicodeError, ValueError, RecursionError):
                        raise TraceRefusal('invalid_json') from None
                    self.buffer.clear()
                    self.consume(obj)

    def consume(self, obj):
        require(type(obj) is dict and obj.get('schema_version') == 1 and
                type(obj.get('schema_version')) is int, 'schema_version')
        require(uint(obj.get('version'), 32) >= 5 and obj.get('action_type') == 1 and
                type(obj.get('action_type')) is int, 'message_version_or_action')
        sequence = uint(obj.get('global_seq_num'))
        if self.first_seq is None:
            self.first_seq = sequence
        if self.last_seq is not None and sequence != self.last_seq + 1:
            self.issue('global_sequence_gap_or_reorder')
        self.last_seq = sequence  # Before filtering: unrelated records also consume sequence.
        self.records += 1
        event = obj.get('event')
        require(type(event) is dict and len(event) == 1, 'event_union')
        kind = next(iter(event))
        require(kind in EVENTS and type(obj.get('event_type')) is int and
                obj['event_type'] == EVENTS[kind], 'event_numeric_concordance')
        body = event[kind]
        require(type(body) is dict and type(body.get('target')) is dict, 'target_schema')
        target = body['target']
        require(type(target.get('path')) is str and type(target.get('path_truncated')) is bool,
                'target_path_schema')
        if target['path_truncated']:
            self.issue('truncated_target_path')
            return
        if target['path'] != str(TARGET):
            return
        target_stat = target.get('stat')
        require(type(target_stat) is dict, 'target_stat_schema')
        inode = (uint(target_stat.get('st_dev')), uint(target_stat.get('st_ino')))
        require(inode[1] != 0, 'target_inode_zero')
        if self.inode is None:
            self.inode = inode
        if self.inode != inode:
            self.issue('target_inode_changed')  # Original pin never changes.
        process = obj.get('process')
        require(type(process) is dict and type(process.get('audit_token')) is dict,
                'actor_schema')
        audit = process['audit_token']
        executable = process.get('executable')
        require(type(executable) is dict and executable.get('path_truncated') is False,
                'actor_executable_schema')
        executable_path = string(executable.get('path'))
        require(executable_path.startswith('/'), 'actor_executable_path')
        signing_id = process.get('signing_id')
        require(type(signing_id) is str and len(signing_id) <= 1024 and
                all(ord(c) >= 32 for c in signing_id), 'actor_signing_schema')
        projected = {'event': kind, 'global_seq_num': sequence, 'time': timestamp(obj.get('time')),
                     'target': {'path': str(TARGET), 'dev': inode[0], 'ino': inode[1]},
                     'actor': {'pid': uint(audit.get('pid'), 32),
                               'pidversion': uint(audit.get('pidversion'), 32),
                               'pgid': uint(process.get('group_id'), 32),
                               'executable': executable_path, 'signing_id': signing_id}}
        if kind == 'setflags':
            projected['requested_flags'] = uint(body.get('flags'), 32)
        elif kind == 'setattrlist':
            attrs = body.get('attrlist')
            keys = ('bitmapcount', 'reserved', 'commonattr', 'volattr', 'dirattr', 'fileattr', 'forkattr')
            require(type(attrs) is dict and set(attrs) == set(keys), 'attribute_bitmap_schema')
            projected['attribute_bitmaps'] = {key: uint(attrs[key], 32) for key in keys}
        else:
            projected['requested_times'] = {key: timestamp(body.get(key)) for key in ('atime', 'mtime')}
        if not self.matches and (kind != 'setflags' or projected.get('requested_flags') != 2):
            self.issue('initial_immutable_notification_missing')
        elif not self.matches:
            self.calibrated = True
        if projected['actor']['pgid'] == self.tracer_pid:
            self.issue('actor_in_suppressed_tracer_process_group')
        require(len(self.matches) < MAX_MATCHES, 'match_limit')
        projected_bytes = len(json.dumps(projected, sort_keys=True, separators=(',', ':')).encode())
        require(self.projected_bytes + projected_bytes <= MAX_PROJECTION, 'projection_limit')
        self.projected_bytes += projected_bytes
        self.matches.append(projected)

    def finish(self):
        if self.buffer:
            self.issue('truncated_json_record')
        if not self.records:
            self.issue('no_records_observed')
        if not self.matches:
            self.issue('no_target_event_observed')


def stop_child(child):
    """Only the original Popen handle is ever signaled; never a PID lookup."""
    if child.poll() is None:
        child.terminate()
    try:
        return child.wait(timeout=2), False
    except subprocess.TimeoutExpired:
        child.kill()
        return child.wait(timeout=2), True


def clock_value(clock):
    value = clock()
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0, 'invalid_clock')
    return value


def supervise(consumer, clock=time.monotonic, popen=subprocess.Popen,
              selector_factory=selectors.DefaultSelector, read=os.read, on_ready=lambda: None):
    start = previous = clock_value(clock)
    child = popen(COMMAND, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                  stderr=subprocess.PIPE, cwd=str(ROOT), env=ENV, close_fds=True,
                  start_new_session=True)
    stderr_bytes = 0
    stopped = False
    calibrated_at = None
    ready = False
    try:
        consumer.tracer_pid = uint(child.pid, 32)
        with selector_factory() as selector:
            selector.register(child.stdout, selectors.EVENT_READ, 'stdout')
            selector.register(child.stderr, selectors.EVENT_READ, 'stderr')
            while selector.get_map():
                current = clock_value(clock)
                require(current >= previous, 'monotonic_clock_reversed')
                previous = current
                deadline = min(start + INITIAL_TARGET_WAIT + MAX_SECONDS,
                               start + INITIAL_TARGET_WAIT if calibrated_at is None else
                               calibrated_at + MAX_SECONDS)
                if current >= deadline:
                    if calibrated_at is None:
                        consumer.issue('initial_target_wait_expired')
                    stopped = True
                    break
                for key, _ in selector.select(min(0.25, deadline - current)):
                    data = read(key.fileobj.fileno(), 8192)
                    if not data:
                        selector.unregister(key.fileobj)
                    elif key.data == 'stdout':
                        consumer.feed(data)
                        observed = clock_value(clock)
                        require(observed >= previous, 'monotonic_clock_reversed')
                        previous = observed
                        if observed >= deadline:
                            consumer.issue('initial_target_wait_expired' if calibrated_at is None else
                                           'read_crossed_observation_deadline')
                            stopped = True
                            break
                        if consumer.calibrated and calibrated_at is None:
                            calibrated_at = observed
                        if consumer.records and not ready:
                            on_ready()  # A valid event, not mere process dispatch, is the readiness marker.
                            ready = True
                    else:
                        stderr_bytes += len(data)  # Content is discarded, including paths/accounts.
                        require(stderr_bytes <= MAX_STDERR, 'stderr_limit')
                if stopped:
                    break
    except TraceRefusal as error:
        consumer.issue(error.args[0])
    except KeyboardInterrupt:
        consumer.issue('interrupted')
    except (OSError, ValueError):
        consumer.issue('tracer_read_failed')
    finally:
        try:
            try:
                code, killed = stop_child(child)
                if killed:
                    consumer.issue('tracer_required_kill')
                if not stopped:
                    consumer.issue('tracer_ended_before_window')
                if code not in (0, -15):
                    consumer.issue('tracer_exit_unsuccessful')
            except (OSError, subprocess.SubprocessError):
                code = None
                consumer.issue('tracer_termination_unknown')
        finally:
            child.stdout.close()
            child.stderr.close()
    if stderr_bytes:
        consumer.issue('native_stderr_observed')
    consumer.finish()
    return code, stderr_bytes


def guard(head, code_sha):
    require(re.fullmatch(r'[0-9a-f]{40}', head) is not None and
            re.fullmatch(r'[0-9a-f]{64}', code_sha) is not None, 'binding_format')
    require(Path.cwd().resolve() == ROOT and ROOT.resolve() == ROOT and
            Path(__file__).resolve() == ROOT / SCRIPT, 'physical_root')
    command = ['/usr/bin/git', '-c', 'safe.directory=' + str(ROOT), '-c', 'core.fsmonitor=false',
               '-c', 'core.hooksPath=/dev/null', '-C', str(ROOT)]
    def git(*args):
        return subprocess.check_output(command + list(args), env=ENV, stderr=subprocess.DEVNULL)
    require(git('rev-parse', '--show-toplevel').decode().strip() == str(ROOT) and
            git('branch', '--show-current').decode().strip() == BRANCH and
            git('rev-parse', 'HEAD').decode().strip() == head and
            git('status', '--porcelain=v1', '--untracked-files=all') == b'', 'lane_git_binding')
    actual = (ROOT / SCRIPT).read_bytes()
    require(hashlib.sha256(actual).hexdigest() == code_sha and
            actual == git('show', head + ':' + SCRIPT), 'committed_code_binding')


def open_directory(path, uid, gid):
    require(path.resolve() == path, 'directory_symlink')
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(fd)
    if not (stat.S_ISDIR(info.st_mode) and info.st_uid == uid and info.st_gid == gid and
            stat.S_IMODE(info.st_mode) == 0o700):
        os.close(fd)
        raise TraceRefusal('private_directory_protection')
    return fd


def directory_pin(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid,
            stat.S_IMODE(info.st_mode), info.st_nlink)


def report_for(consumer, head, code_sha, exit_code, stderr_bytes):
    return {'schema': 'si-journal-actor-trace-v1', 'head': head, 'code_sha256': code_sha,
            'status': 'incomplete' if consumer.issues else 'bounded_observation_closed',
            'target': str(TARGET), 'original_observed_inode': consumer.inode,
            'scope': 'three_metadata_notifications_only_not_all_possible_mutations',
            'actor_causality': 'requires_original_creator_lineage_and_observed_transition',
            'source_authority': False, 'new_source_requests': 0, 'new_claims': 0,
            'maximum_seconds': MAX_SECONDS, 'tracer_exit_code': exit_code,
            'initial_target_wait_seconds': INITIAL_TARGET_WAIT,
            'maximum_total_observation_seconds': INITIAL_TARGET_WAIT + MAX_SECONDS,
            'tracer_pid': consumer.tracer_pid, 'tracer_pgid': consumer.tracer_pid,
            'tracer_pgid_basis': 'original_Popen_PID_with_start_new_session',
            'tracer_isolated_session': True, 'native_suppression': 'tracer_process_group',
            'stderr_bytes_discarded': stderr_bytes, 'input_bytes': consumer.total,
            'records_seen': consumer.records, 'first_global_seq': consumer.first_seq,
            'last_global_seq': consumer.last_seq, 'issues': list(consumer.issues),
            'matched_events': list(consumer.matches)}


def absent(name, directory):
    try:
        os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise TraceRefusal('reserved_name_exists')


def root_trace(head, code_sha):
    require(sys.platform == 'darwin' and os.geteuid() == 0, 'root_macos_required')
    guard(head, code_sha)
    owner = ROOT.stat()
    require(owner.st_uid != 0, 'nonroot_lane_owner_required')
    directory = open_directory(TRACE_DIR, owner.st_uid, owner.st_gid)
    subject_dir = output = None
    consumer = None
    exit_code = None
    stderr_bytes = 0
    try:
        subject_dir = open_directory(TARGET.parent, owner.st_uid, owner.st_gid)
        directory_pins = {directory: directory_pin(os.fstat(directory)),
                          subject_dir: directory_pin(os.fstat(subject_dir))}
        absent(TARGET.name, subject_dir)
        absent(OUTPUT.name, directory)
        output = os.open(OUTPUT.name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory)
        os.fchown(output, owner.st_uid, owner.st_gid)
        os.fchmod(output, 0o600)
        created = os.fstat(output)
        require(created.st_nlink == 1 and stat.S_ISREG(created.st_mode), 'output_protection')
        consumer = Consumer()
        def ready():
            print(json.dumps({'status': 'tracer_stream_ready', 'source_authority': False,
                              'tracer_pid': consumer.tracer_pid, 'tracer_pgid': consumer.tracer_pid}), flush=True)
        exit_code, stderr_bytes = supervise(consumer, on_ready=ready)
        guard(head, code_sha)
        for path, fd in ((TRACE_DIR, directory), (TARGET.parent, subject_dir)):
            require(directory_pin(os.stat(path, follow_symlinks=False)) == directory_pins[fd] ==
                    directory_pin(os.fstat(fd)), 'directory_changed')
        report = report_for(consumer, head, code_sha, exit_code, stderr_bytes)
        encoded = (json.dumps(report, sort_keys=True, separators=(',', ':')) + '\n').encode()
        require(len(encoded) <= MAX_OUTPUT, 'output_limit')
        original_report_sha256 = hashlib.sha256(encoded).hexdigest()
        current = os.stat(OUTPUT.name, dir_fd=directory, follow_symlinks=False)
        require((created.st_dev, created.st_ino) == (current.st_dev, current.st_ino) and
                current.st_uid == owner.st_uid and current.st_gid == owner.st_gid and
                stat.S_IMODE(current.st_mode) == 0o600 and current.st_nlink == 1 and
                current.st_size == 0, 'output_changed')
        offset = 0
        while offset < len(encoded):
            count = os.write(output, encoded[offset:])
            require(count > 0, 'output_write_stopped')
            offset += count
        os.fsync(output)
        require(os.pread(output, len(encoded) + 1, 0) == encoded, 'output_readback')
        return {'status': report['status'], 'matches': len(consumer.matches),
                'source_authority': False, 'output': str(OUTPUT),
                'original_report_sha256': original_report_sha256, 'original_report_bytes': len(encoded)}
    except (TraceRefusal, OSError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        if consumer is not None:
            consumer.issue('interrupted' if type(error) is KeyboardInterrupt else
                           'trace_or_terminal_publication_failed')
            raise EvidenceRefusal(report_for(consumer, head, code_sha, exit_code, stderr_bytes)) from None
        raise
    finally:
        cleanup_failed = False
        for fd in (output, subject_dir, directory):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    cleanup_failed = True
        if cleanup_failed:
            if consumer is not None:
                consumer.issue('resource_cleanup_failed')
                raise EvidenceRefusal(report_for(consumer, head, code_sha, exit_code, stderr_bytes)) from None
            raise TraceRefusal('resource_cleanup_failed')


def plan(head, code_sha):
    require(re.fullmatch(r'[0-9a-f]{40}', head) is not None and
            re.fullmatch(r'[0-9a-f]{64}', code_sha) is not None, 'binding_format')
    command = ['sudo', '/usr/bin/python3', '-I', '-S', '-c', BOOTSTRAP, head, code_sha]
    return {'command': command, 'shell_command': 'cd ' + shlex.quote(str(ROOT)) + ' && ' + shlex.join(command),
            'working_directory': str(ROOT),
            'native_command': list(COMMAND), 'maximum_seconds': MAX_SECONDS,
            'initial_target_wait_seconds': INITIAL_TARGET_WAIT,
            'maximum_total_observation_seconds': INITIAL_TARGET_WAIT + MAX_SECONDS,
            'maximum_shutdown_wait_seconds': 4,
            'responsible_process_full_disk_access_required': True,
            'target_initially_absent': str(TARGET), 'output_exclusive': str(OUTPUT),
            'requires_prepared_private_directories': True, 'source_authority': False,
            'changes_privacy_settings_or_daemons': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('print-plan', 'root-trace'))
    parser.add_argument('--head', required=True)
    parser.add_argument('--code-sha256', required=True)
    args = parser.parse_args()
    try:
        result = plan(args.head, args.code_sha256) if args.action == 'print-plan' else root_trace(
            args.head, args.code_sha256)
    except EvidenceRefusal as error:
        # Projection only: no original/raw unrelated messages or stderr survive.
        print(json.dumps(error.report, sort_keys=True))
        return 2
    except (TraceRefusal, OSError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        result = {'status': 'trace_refused', 'source_authority': False,
                  'code': error.args[0] if type(error) is TraceRefusal else
                  ('interrupted' if type(error) is KeyboardInterrupt else 'local_operation_failed')}
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get('status') != 'incomplete' else 2


if __name__ == '__main__':
    sys.exit(main())
