"""Bounded external capture for the separately authorized R321 read-only probe.

This runner never uploads, mutates permissions, compiles or launches. It invokes
one fixed observation child and validates its finite output once in a separate
native network/private-data-denied child. Captured raw channels never print.
The frozen helper is reused only for low-level capture/environment/source tools;
none of its historical operational entry points or controls are invoked.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import observe_arv2_r298_handoff_recovery as capture


SCHEMA = 'arv2-r298-access-mismatch-observation-v1'
BRANCH = 'codex/strategy-analyst-revisions-v2'
PYTHON = Path('/Users/sheltonchen/.venvs/trading_agent-py313/bin/python')
SOURCE = ROOT / 'scripts/run_arv2_r298_access_mismatch_observation.py'
CALLER = ROOT / 'scripts/observe_arv2_r298_access_mismatch.py'
TESTS = ROOT / 'tests/analyst_revisions_v2/test_r298_access_mismatch_observation.py'
CALLER_TESTS = ROOT / 'tests/analyst_revisions_v2/test_r298_access_mismatch.py'
HELPER = ROOT / 'scripts/observe_arv2_r298_handoff_recovery.py'
HELPER_SHA256 = 'cfba31c04d5ff10f33779f1c497cefa3885d63b737f7c260bd9b41a27db6f55f'
PARENT_SECONDS = 75
VALIDATOR_SECONDS = 15
SANDBOX = capture.SANDBOX
CREDENTIAL_NAMES = capture.CREDENTIAL_NAMES
FINITE = capture.FINITE
ObserverError = capture.ObserverError
Captured = capture.Captured
canonical = capture.canonical
sha = capture.sha
require = capture.require
_capture = capture._capture
_credential_handoff = capture._credential_handoff
_environment = capture._environment
_source_bytes = capture._source_bytes
_git = capture._git
_validated_packet = capture._validated_packet

VALIDATOR_CODE = '''import json,sys,time
from types import SimpleNamespace
try:
 from scripts import observe_arv2_r298_access_mismatch as c
 raw=sys.stdin.buffer.read(131073)
 args=SimpleNamespace(expected_head=sys.argv[1],caller_sha256=sys.argv[2])
 actual_exit=int(sys.argv[3])
 c._preflight(args,time.monotonic()+12)
 value=c.validate_output(raw,actual_exit,args)
 if "assistant.dispatch_fence" in sys.modules: raise ValueError()
 payload={"validated":True,"actual_exit":actual_exit,"value":value}
 encoded=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode("ascii")+b"\\n"
 if len(encoded)>131072: raise ValueError()
 sys.stdout.buffer.write(encoded)
except BaseException:
 sys.stdout.buffer.write(b'{"validated":false}\\n')
 raise SystemExit(2)
'''


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': BRANCH,
        'python': str(PYTHON), 'runner': str(SOURCE), 'caller': str(CALLER),
        'helper': str(HELPER), 'helper_sha256': HELPER_SHA256,
        'parent_seconds': PARENT_SECONDS, 'validator_seconds': VALIDATOR_SECONDS,
        'max_channel_bytes': capture.MAX_CHANNEL, 'git_seconds': capture.GIT_SECONDS,
        'reap_seconds': capture.REAP_SECONDS, 'max_observation_dispatches': 1,
        'max_validator_dispatches': 1, 'credential_handoff_before_any_subprocess': True,
        'credential_lookup': 'inherited_existing_environment_only',
        'post_parent_public_source_reauthentication': True,
        'validator_source_only_preflight_seconds': 12,
        'validator_code_sha256': sha(VALIDATOR_CODE.encode('ascii')),
        'validator_sandbox': SANDBOX, 'raw_channels_printed': False,
        'output_leaf_reads': False, 'upload_permission_compile_launch_allowed': False,
        'post_dispatch_outcome': 'consumed_or_ambiguous_no_retry',
        'parent_seconds_scope': 'capture_only_excludes_bounded_git_validator_and_reap',
        'uninterruptible_io_or_host_suspension_bounded': False,
        'whole_interpreter_integrity': False, 'same_user_memory_sandbox': False}


PROFILE_SHA256 = sha(canonical(profile_record()))


def _arguments(args):
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}', args.expected_head)
        and type(args.caller_sha256) is str and re.fullmatch('[0-9a-f]{64}', args.caller_sha256)
        and type(args.runner_sha256) is str and re.fullmatch('[0-9a-f]{64}', args.runner_sha256),
        'arguments')


def _preflight(args, environment):
    _arguments(args)
    require(sys.platform == 'darwin' and os.name == 'posix'
        and sys.version_info[:2] == (3, 13) and Path(sys.executable).absolute() == PYTHON
        and Path.cwd() == ROOT and Path(__file__).absolute() == SOURCE
        and ROOT.resolve() == ROOT, 'host')
    require(_git(['rev-parse', '--show-toplevel'], environment) == (str(ROOT) + '\n').encode()
        and _git(['branch', '--show-current'], environment) == (BRANCH + '\n').encode()
        and _git(['rev-parse', 'HEAD'], environment) == (args.expected_head + '\n').encode()
        and _git(['status', '--porcelain', '--untracked-files=normal'], environment) == b'', 'git_state')
    for path, expected in ((SOURCE, args.runner_sha256), (CALLER, args.caller_sha256),
            (HELPER, HELPER_SHA256), (TESTS, None), (CALLER_TESTS, None)):
        raw = _source_bytes(path)
        require(expected is None or sha(raw) == expected, 'source_pin')
        relative = str(path.relative_to(ROOT))
        require(_git(['show', args.expected_head + ':' + relative], environment) == raw, 'source_pin')
    require(_git(['rev-parse', 'HEAD'], environment) == (args.expected_head + '\n').encode()
        and _git(['status', '--porcelain', '--untracked-files=normal'], environment) == b'', 'git_state')


def _validator_command(args, actual_exit):
    return ['/usr/bin/sandbox-exec', '-p', SANDBOX, str(PYTHON), '-B', '-c',
        VALIDATOR_CODE, args.expected_head, args.caller_sha256, str(actual_exit)]


def observe(args, *, environ=None):
    """Dispatch at most one observation child; no implicit repeat or recovery."""
    result = {'schema': SCHEMA, 'profile_sha256': PROFILE_SHA256, 'source_binding': None,
        'observation_child_dispatch_attempted': False, 'validator_dispatched': False,
        'observation_consumption': 'no_child_dispatched', 'parent': None, 'validator': None,
        'output_validated': False, 'validated_output': None, 'failure_code': None}
    credentials = child_environment = None
    try:
        credentials = _credential_handoff(os.environ if environ is None else environ)
        _arguments(args)
        result['source_binding'] = {'expected_head': args.expected_head,
            'caller_sha256': args.caller_sha256, 'runner_sha256': args.runner_sha256}
        require(ROOT.resolve() == ROOT and (ROOT / '.pytest_cache').resolve()
            == ROOT / '.pytest_cache', 'support_path')
        support = Path(tempfile.mkdtemp(prefix='r321-observation-', dir=ROOT / '.pytest_cache'))
        safe_environment = _environment(support)
        _preflight(args, safe_environment)
        child_environment = _environment(support, credentials)
        result['observation_child_dispatch_attempted'] = True
        result['observation_consumption'] = 'consumed_or_ambiguous_no_retry'
        observed = _capture([str(PYTHON), '-B', str(CALLER), '--expected-head',
            args.expected_head, '--caller-sha256', args.caller_sha256],
            environ=child_environment, timeout=PARENT_SECONDS)
        result['parent'] = observed.metadata()
        child_environment.clear()
        credentials.clear()
        require(observed.bound is None, 'parent_bound')
        require(not observed.stderr, 'parent_stderr')
        require(type(observed.actual_exit) is int and observed.actual_exit in (0, 2), 'parent_exit')
        _preflight(args, safe_environment)
        result['validator_dispatched'] = True
        validated = _capture(_validator_command(args, observed.actual_exit),
            environ=safe_environment, timeout=VALIDATOR_SECONDS, input_bytes=observed.stdout)
        result['validator'] = validated.metadata()
        result['validated_output'] = _validated_packet(validated, observed.actual_exit)
        result['output_validated'] = True
        return result, 0 if observed.actual_exit == 0 else 2
    except BaseException as error:
        code = 'observer_refused'
        if type(error) is ObserverError:
            items = BaseException.args.__get__(error)
            if len(items) == 1 and type(items[0]) is str and items[0] in FINITE:
                code = items[0]
        result['failure_code'] = code
        return result, 2
    finally:
        if type(child_environment) is dict:
            child_environment.clear()
        if type(credentials) is dict:
            credentials.clear()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--caller-sha256', required=True)
    parser.add_argument('--runner-sha256', required=True)
    args = parser.parse_args(argv)
    result, code = observe(args)
    sys.stdout.buffer.write(canonical(result))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
