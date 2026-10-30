"""Committed, finite outer collector for R329's two offline one-shot callers.

The exact specification is separately frozen before use. Its hash is a source
binding, never authorization. This collector reads no operational control and
does not retry. A normal child exit is still subject to that caller's validator.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import sys
import time

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
PYTHON = '/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
CALLERS = {'stage': 'prepare_arv2_r329_native_coverage_source.py',
    'readback': 'verify_arv2_r329_native_coverage_readback.py'}
SECONDS = 210
MAX_BYTES = 65536
SCHEMA = 'arv2-r329-bounded-offline-process-v1'
FAILURE_BASE = {'binding', 'failure_code', 'claim_consumed', 'allocation_unknown'}
COMMON_FALSE = {'QC_contact', 'Safari_access', 'provider_contact', 'credential_access',
    'private_source_DATA_read', 'old_control_read', 'price_coverage_admitted',
    'new_launch_attempt_granted', 'point_in_time_proven', 'formal_forward_ready',
    'paper_or_live_ready', 'continuous_integrity_proven'}
STAGE_FALSE = COMMON_FALSE | {'project_access_verified', 'source_book_recreated',
    'source_data_exported', 'QC_transfer_granted', 'source_or_processing_rights_granted'}
READBACK_FALSE = COMMON_FALSE | {'downloaded_code_executed', 'download_origin_proven_by_verifier',
    'cloud_saved_source_currently_authenticated'}


class Refused(ValueError):
    pass


def require(value):
    if not value:
        raise Refused('process_binding')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
        allow_nan=False).encode('ascii')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result)
        result[key] = value
    return result


def parse(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES)
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('process_binding')))
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('process_binding') from None
    require(canonical(value) == raw)
    return value


def command(spec):
    require(type(spec) is dict and set(spec) == {'schema', 'operation', 'expected_head',
        'caller_sha256', 'profile_sha256', 'native_policy', 'native_policy_sha256', 'extra_args'})
    require(spec['schema'] == SCHEMA and type(spec['operation']) is str
        and spec['operation'] in CALLERS)
    require(type(spec['expected_head']) is str and re.fullmatch('[0-9a-f]{40}', spec['expected_head']))
    for field in ('caller_sha256', 'profile_sha256', 'native_policy_sha256'):
        require(type(spec[field]) is str and re.fullmatch('[0-9a-f]{64}', spec[field]))
    policy = spec['native_policy']
    require(type(policy) is str and policy.isascii() and 0 < len(policy) <= 20000
        and sha(policy.encode('ascii')) == spec['native_policy_sha256']
        and policy.startswith('(version 1)(allow default)(deny network*)')
        and '(deny process-exec (literal "/usr/bin/security"))' in policy)
    extra = spec['extra_args']
    require(type(extra) is list and all(type(item) is str and item.isascii() and len(item) <= 12000
        for item in extra))
    if spec['operation'] == 'stage':
        require(extra == [])
    else:
        require(len(extra) == 4 and extra[0] == '--download-map-json'
            and extra[2] == '--download-map-sha256' and re.fullmatch('[0-9a-f]{64}', extra[3]))
    source = ROOT / 'scripts' / CALLERS[spec['operation']]
    return ['/usr/bin/sandbox-exec', '-p', policy, PYTHON, '-B', str(source),
        '--expected-head', spec['expected_head'], '--caller-sha256', spec['caller_sha256'],
        '--profile-sha256', spec['profile_sha256'], *extra]


def collect(argv, env, *, seconds=SECONDS, maximum=MAX_BYTES):
    """Bound pipes before accumulation; kill/reap only our own child on refusal.

    Deadline cannot bound uninterruptible OS I/O or host suspension. Descendant
    Git commands retain their own short timeout; this is not an OS process-tree
    sandbox or a guarantee of continuous process integrity.
    """
    require(type(seconds) in (int, float) and 0 < seconds <= SECONDS
        and type(maximum) is int and 0 < maximum <= MAX_BYTES)
    deadline = time.monotonic() + seconds
    child = None
    output = bytearray()
    status = 'unknown'
    actual_exit = None
    stderr_seen = False
    try:
        child = subprocess.Popen(argv, cwd=str(ROOT), env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
        with selectors.DefaultSelector() as selector:
            for pipe, label in ((child.stdout, 'stdout'), (child.stderr, 'stderr')):
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ, label)
            while selector.get_map() or child.poll() is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    status = 'deadline'
                    break
                ready = selector.select(min(0.25, remaining))
                for key, _ in ready:
                    chunk = os.read(key.fileobj.fileno(), min(8192, maximum + 1))
                    if not chunk:
                        selector.unregister(key.fileobj)
                    elif key.data == 'stderr':
                        stderr_seen = True
                        status = 'stderr'
                        break
                    elif len(output) + len(chunk) > maximum:
                        status = 'stdout_bound'
                        break
                    else:
                        output.extend(chunk)
                if status != 'unknown':
                    break
            if status == 'unknown':
                actual_exit = child.wait(timeout=max(0.01, deadline - time.monotonic()))
                status = 'returned'
    except BaseException:
        status = 'collector_failure'
    finally:
        if child is not None:
            if child.poll() is None:
                child.kill()
            try:
                actual_exit = child.wait(timeout=5)
            except BaseException:
                actual_exit = None
                status = 'reap_ambiguous'
            for pipe in (child.stdout, child.stderr):
                if pipe is not None:
                    pipe.close()
    # Only the two pinned callers' finite canonical envelopes may be forwarded.
    envelope = None
    if status == 'returned' and actual_exit in (0, 2) and not stderr_seen:
        try:
            require(output.endswith(b'\n') and output.count(b'\n') == 1)
            envelope = parse(bytes(output[:-1]))
            require(type(envelope) is dict)
            keys = set(envelope)
            allowed = keys in ({'binding', 'outcome'}, {'failure_code'})
            for flags in (STAGE_FALSE, READBACK_FALSE):
                allowed = allowed or (keys == FAILURE_BASE | flags
                    and all(envelope[key] is False for key in flags))
            require(allowed)
        except BaseException:
            status = 'malformed_output'
            envelope = None
    return {'schema': SCHEMA, 'collector_status': status, 'actual_child_exit': actual_exit,
        'stdout_byte_count': len(output), 'stdout_sha256': sha(bytes(output)),
        'stderr_seen': stderr_seen, 'child_envelope': envelope,
        'child_output_accepted': False, 'attempt_reusable': False}


def run(spec, expected_sha):
    require(sha(canonical(spec)) == expected_sha and Path.cwd() == ROOT
        and sys.platform == 'darwin' and sys.version_info[:2] == (3, 13)
        and sys.executable == PYTHON)
    argv = command(spec)
    allowed = {'PATH', 'TMPDIR', 'PYTHONPYCACHEPREFIX', 'PYTHONDONTWRITEBYTECODE',
        'PYTEST_DISABLE_PLUGIN_AUTOLOAD', 'LC_ALL', 'LANG', '__CF_USER_TEXT_ENCODING'}
    require(set(os.environ) <= allowed and os.environ.get('PYTHONDONTWRITEBYTECODE') == '1'
        and os.environ.get('PYTEST_DISABLE_PLUGIN_AUTOLOAD') == '1')
    for name in ('TMPDIR', 'PYTHONPYCACHEPREFIX'):
        path = Path(os.environ.get(name, ''))
        require(path.is_absolute() and ROOT / '.pytest_cache' in path.parents and path.resolve() == path)
    # Current public caller bytes only, before dispatch. The child binds its
    # clean Git snapshot and full selected closure before allocating its claim.
    path = ROOT / 'scripts' / CALLERS[spec['operation']]
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(0 < info.st_size <= 131072 and info.st_nlink == 1)
        raw = os.pread(fd, 131073, 0)
        require(len(raw) == info.st_size and sha(raw) == spec['caller_sha256']
            and os.fstat(fd) == info and path.stat(follow_symlinks=False) == info)
    finally:
        os.close(fd)
    value = collect(argv, dict(os.environ), seconds=210 if spec['operation'] == 'stage' else 60)
    return {'spec_sha256': expected_sha, **value}


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused('arguments')


def main():
    try:
        parser = _Parser(add_help=False)
        parser.add_argument('--spec-json', required=True)
        parser.add_argument('--spec-sha256', required=True)
        args = parser.parse_args()
        value = run(parse(args.spec_json.encode('ascii')), args.spec_sha256)
        sys.stdout.buffer.write(canonical(value) + b'\n')
        return 0 if value['collector_status'] == 'returned' and value['actual_child_exit'] in (0, 2) else 2
    except BaseException:
        sys.stdout.buffer.write(b'{"failure_code":"outer_binding","attempt_reusable":false}\n')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
