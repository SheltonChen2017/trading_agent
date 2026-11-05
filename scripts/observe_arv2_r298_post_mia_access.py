"""One read-only post-Mia access reconciliation; no project mutation or launch.

Two fixed requests retain only a strict redacted projection and the exact
finite access predicate. A failed observation never grants recovery authority.
All previous controls and attempts remain spent and are not read here.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_arv2_r298_quote_diagnostic as prior
from scripts import arv2_r298_collaborator_access as access
from scripts import arv2_newrule_execution_environment as environment

SOURCE = ROOT / 'scripts/observe_arv2_r298_post_mia_access.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_post_mia_access/R323-20261025-C'
PYTHON = prior.PYTHON
SCHEMA = 'arv2-r298-post-mia-access-v1'
DEADLINE_SECONDS, MAX_OUTPUT, MAX_FILES = 120, 64 * 1024, 8
ENDPOINTS = ('projects/read', 'projects/collaboration/read')
HELPER_NAME = 'arv2_r298_post_mia_access'
NEW_PINS = {
    'scripts/run_arv2_r298_quote_diagnostic.py': '770ce5b92fcd46e862a40a763b492d6561b55a82b4e244242a900eda71509257',
    'scripts/arv2_r298_post_mia_access.py': '09705275244935bce92c096e18d3beaaedd3eed13ab31deb8ef8788fb9df8672',
}
FALSE_FLAGS = {'access_policy_accepted': False, 'operational_retry_authority': False,
    'project_ready': False, 'point_in_time_proven': False, 'formal_identity_admitted': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False, 'strategy_result_accepted': False}
FINITE = frozenset(('arguments', 'host', 'git_state', 'source_pin', 'deadline',
    'claim_spent', 'control_changed', 'control_name', 'control_bound', 'control_write',
    'request_scope', 'output', 'output_bound', 'parent_failed', 'validator_failed',
    'execution_environment_refused', 'credential_handoff', 'qc_client_refused',
    'qc_not_configured', 'refused', 'os_error', 'unknown_exception'))
canonical, parse, sha, metadata = prior.canonical, prior.parse, prior.sha, prior.metadata
capture, credential_shape = prior.capture, prior.credential_shape


class Refused(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise Refused(code)


def remaining(deadline):
    value = deadline - time.monotonic()
    require(value > 0, 'deadline')
    return value


def helper():
    from scripts import arv2_r298_post_mia_access as module
    return module


def finite(error):
    if type(error) is access.AccessRefused:
        return 'access_' + access.finite_error(error)['code']
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE:
            return args[0]
    module = sys.modules.get('scripts.' + HELPER_NAME)
    if module is not None and type(error) is vars(module).get('Refused'):
        return 'projection_' + module.finite(error)
    if type(error) is environment.EnvironmentRefused:
        return 'execution_environment_refused'
    qc = sys.modules.get('research.quantconnect')
    if qc is not None:
        if type(error) is vars(qc).get('QuantConnectError'): return 'qc_client_refused'
        if type(error) is vars(qc).get('QuantConnectNotConfigured'): return 'qc_not_configured'
    if isinstance(error, OSError):
        return 'os_error'
    return 'unknown_exception'


def pins():
    return {**prior.pins(), **NEW_PINS}


def _finite_code(value):
    codes = FINITE | {'access_' + code for code in access.FINITE_CODES | {'unknown'}}
    codes |= {'projection_' + code for code in helper().FINITE | {'unknown'}}
    return type(value) is str and value in codes


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': prior.admitted.frozen.BRANCH,
        'python': str(PYTHON), 'control': str(CONTROL), 'source_pins': pins(),
        'project_id': access.PROJECT_ID, 'purpose': 'post_mia_access_predicate_reconciliation_only',
        'endpoints': list(ENDPOINTS), 'max_application_dispatches': 2,
        'deadline_seconds': DEADLINE_SECONDS, 'max_output': MAX_OUTPUT,
        'prior_attempts_spent': True, 'old_control_reads': False,
        'response_bodies_retained': False, 'actual_exit_required': True,
        'automatic_retry': False, 'lock_changes': 0, 'uploads': 0,
        'capacity_calls': 0, 'compiles': 0, 'backtests': 0,
        'same_user_sandbox': False, 'continuous_integrity_proven': False,
        'uninterruptible_io_or_suspension_bounded': False, **FALSE_FLAGS}


def binding(args):
    def checked(value, length):
        return value if type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value) else None
    return {'schema': SCHEMA, 'expected_head': checked(args.expected_head, 40),
        'caller_sha256': checked(args.caller_sha256, 64),
        'profile_sha256': sha(canonical(profile_record()))}


def preflight(args, deadline):
    require(not prior.admitted.v5._under_test() and Path(__file__).absolute() == SOURCE
        and sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT, 'host')
    require(binding(args)['expected_head'] is not None and binding(args)['caller_sha256'] is not None,
            'arguments')
    environment._require_environment()
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)),
        (['branch', '--show-current'], prior.admitted.frozen.BRANCH),
        (['rev-parse', 'HEAD'], args.expected_head), (['status', '--porcelain'], '')):
        require(prior.admitted.v5._git(command, deadline).decode('ascii').strip() == expected, 'git_state')
    for name, pin in pins().items():
        require(pin != '0' * 64 and sha((ROOT / name).read_bytes()) == pin, 'source_pin')
    require(sha(SOURCE.read_bytes()) == args.caller_sha256, 'source_pin')
    blob = prior.admitted.v5._git(['cat-file', 'blob', args.expected_head + ':' + SOURCE.relative_to(ROOT).as_posix()],
                                  deadline, MAX_OUTPUT)
    require(sha(blob) == args.caller_sha256, 'source_pin')
    remaining(deadline)


class Store:
    """Exclusive new leaf, immutable records and endpoint metadata checks."""
    def __init__(self):
        self.fd, self.chain, self.files = None, [], {}
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for index, part in enumerate(CONTROL.parts[1:], 1):
                here = Path(*CONTROL.parts[:index + 1])
                if here in (CONTROL.parent, CONTROL):
                    try:
                        os.mkdir(part, 0o700, dir_fd=fd)
                        os.fsync(fd)
                    except FileExistsError:
                        require(here != CONTROL, 'claim_spent')
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd); fd = nxt
                info = os.fstat(fd)
                self.chain.append((info.st_dev, info.st_ino))
            self.fd = fd
            self.verify()
        except BaseException:
            os.close(fd)
            raise

    def __enter__(self): return self
    def __exit__(self, *_): os.close(self.fd)

    def verify(self):
        other, chain = prior.admitted._storage_module()._walk(CONTROL)
        try:
            held, named = os.fstat(self.fd), os.fstat(other)
            require(chain == tuple(self.chain) and metadata(held) == metadata(named)
                and held.st_uid == os.getuid() and stat.S_IMODE(held.st_mode) == 0o700
                and set(os.listdir(other)) == set(self.files) and len(self.files) <= MAX_FILES
                and held.st_nlink == 2 + len(self.files), 'control_changed')
            for name, baseline in self.files.items():
                require(metadata(os.stat(name, dir_fd=other, follow_symlinks=False)) == baseline,
                        'control_changed')
        finally:
            os.close(other)

    def write(self, name, value):
        self.verify()
        require(type(name) is str and re.fullmatch('[a-z0-9-]{1,100}\\.json', name)
            and name not in self.files and len(self.files) < MAX_FILES, 'control_name')
        raw = canonical(value)
        require(0 < len(raw) <= MAX_OUTPUT, 'control_bound')
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            view = memoryview(raw)
            while view:
                n = os.write(fd, view)
                require(n > 0, 'control_write'); view = view[n:]
            os.fsync(fd); os.fsync(self.fd)
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_uid == os.getuid() and info.st_nlink == 1 and info.st_size == len(raw), 'control_write')
            os.lseek(fd, 0, os.SEEK_SET)
            reread = bytearray()
            while len(reread) <= len(raw):
                chunk = os.read(fd, min(65536, len(raw) + 1 - len(reread)))
                if not chunk: break
                reread.extend(chunk)
            require(bytes(reread) == raw and metadata(info) == metadata(os.fstat(fd)), 'control_changed')
            self.files[name] = metadata(info)
        finally:
            os.close(fd)
        self.verify()
        return {'byte_count': len(raw), 'sha256': sha(raw)}


def _client():
    environment.require_safe_environment()
    from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
    api = old._client()
    require(type(api) is old.QuantConnectClient and api._base_url == old.API_BASE
        and api._transport is old.coverage._bounded_transport and api._timeout == 30, 'request_scope')
    environment.require_safe_environment()
    return api


def run(args, deadline):
    credential_shape().clear()
    with Store() as directory:
        directory.write('claim.json', {**binding(args), 'read_only': True, 'prior_attempts_spent': True})
        state = {'stage': 'credentials', 'application_dispatch_count': 0,
                 'response_count': 0, 'last_endpoint': None, 'last_response_received': False}
        try:
            api, responses = _client(), []
            for index, endpoint in enumerate(ENDPOINTS):
                state['stage'] = 'project' if index == 0 else 'collaboration'
                remaining(deadline); environment.require_safe_environment()
                require(state['application_dispatch_count'] == index, 'request_scope')
                directory.write('request-' + str(index) + '-intent.json',
                    {**binding(args), 'endpoint': endpoint, 'project_id': access.PROJECT_ID})
                state['last_endpoint'], state['last_response_received'] = endpoint, False
                state['application_dispatch_count'] += 1
                response = api.request(endpoint, {'projectId': access.PROJECT_ID})
                state['response_count'] += 1; state['last_response_received'] = True
                raw = access._canonical(response)
                require(0 < len(raw) <= access.MAX_RESPONSE_BYTES, 'output_bound')
                directory.write('request-' + str(index) + '-observed.json',
                    {**binding(args), 'endpoint': endpoint, 'response_sha256': sha(raw),
                     'response_byte_count': len(raw)})
                responses.append(response)
            state['stage'] = 'projection'
            observation = helper().observe(*responses)
            try:
                access.verify_access(*responses)
                access_code = None
            except access.AccessRefused as error:
                access_code = access.finite_error(error)['code']
                require(access_code in access.FINITE_CODES, 'output')
            require(observation['access_failure_code'] == access_code, 'output')
            responses.clear()
            result = {'terminal': 'observed', 'application_dispatch_count': 2,
                'access_failure_code': access_code, 'observation': observation, **FALSE_FLAGS}
            validate_result(result)
            state['stage'] = 'postflight'; preflight(args, deadline)
            state['stage'] = 'report'
            pin = directory.write('report.json', {**binding(args), 'result': result})
            return {'result': result, 'report': pin}
        except BaseException as error:
            failed = {'failure_code': finite(error), 'state': state,
                'attempt_consumption': 'consumed_or_ambiguous_no_retry', **FALSE_FLAGS}
            try: directory.write('failure.json', {**binding(args), **failed})
            except BaseException: pass
            return {'failure': failed}


def validate_result(result):
    require(type(result) is dict and set(result) == {'terminal', 'application_dispatch_count',
        'access_failure_code', 'observation', *FALSE_FLAGS} and result['terminal'] == 'observed'
        and type(result['application_dispatch_count']) is int and result['application_dispatch_count'] == 2
        and (result['access_failure_code'] is None or type(result['access_failure_code']) is str
             and result['access_failure_code'] in access.FINITE_CODES)
        and all(result[key] is False for key in FALSE_FLAGS), 'output')
    helper().validate_observation(result['observation'])
    require(result['observation']['access_failure_code'] == result['access_failure_code'], 'output')


def validate_output(raw, actual_exit, args):
    require(type(actual_exit) is int and actual_exit in (0, 2) and type(raw) is bytes
        and 0 < len(raw) <= MAX_OUTPUT, 'output')
    value = parse(raw)
    require(type(value) is dict and value.get('binding') == binding(args), 'output')
    if set(value) == {'binding', 'preflight_failure'}:
        require(actual_exit == 2 and _finite_code(value['preflight_failure']), 'output')
        return value
    require(set(value) == {'binding', 'outcome'} and type(value['outcome']) is dict, 'output')
    outcome = value['outcome']
    if set(outcome) == {'failure'}:
        failed = outcome['failure']
        require(actual_exit == 2 and type(failed) is dict
            and set(failed) == {'failure_code', 'state', 'attempt_consumption', *FALSE_FLAGS}
            and _finite_code(failed['failure_code'])
            and failed['attempt_consumption'] == 'consumed_or_ambiguous_no_retry'
            and all(failed[key] is False for key in FALSE_FLAGS), 'output')
        state = failed['state']
        require(type(state) is dict and set(state) == {'stage', 'application_dispatch_count',
            'response_count', 'last_endpoint', 'last_response_received'}
            and state['stage'] in ('credentials', 'project', 'collaboration', 'projection', 'postflight', 'report')
            and type(state['application_dispatch_count']) is int
            and 0 <= state['application_dispatch_count'] <= 2
            and type(state['response_count']) is int
            and 0 <= state['response_count'] <= state['application_dispatch_count']
            and type(state['last_response_received']) is bool
            and (state['last_endpoint'] is None or type(state['last_endpoint']) is str
                 and state['last_endpoint'] in ENDPOINTS), 'output')
        count = state['application_dispatch_count']
        require((count == 0 and state['response_count'] == 0 and state['last_endpoint'] is None
                 and state['last_response_received'] is False)
            or (count in (1, 2) and state['last_endpoint'] == ENDPOINTS[count - 1]
                and state['response_count'] == count - (not state['last_response_received'])), 'output')
        require((state['stage'] == 'credentials' and count == 0)
            or (state['stage'] == 'project' and count <= 1)
            or (state['stage'] == 'collaboration' and count in (1, 2))
            or (state['stage'] in ('projection', 'postflight', 'report')
                and count == state['response_count'] == 2), 'output')
    else:
        require(actual_exit == 0 and set(outcome) == {'result', 'report'}, 'output')
        validate_result(outcome['result'])
        report = canonical({**binding(args), 'result': outcome['result']})
        require(outcome['report'] == {'byte_count': len(report), 'sha256': sha(report)}, 'output')
    return value


def observe(args):
    credentials, parent_env = {}, {}
    outer = {'schema': SCHEMA + '-observer', 'parent': None, 'validator': None,
             'output_authenticated': False, 'output': None, 'failure_code': None}
    try:
        credentials = credential_shape()
        runtime = Path(tempfile.mkdtemp(prefix='r323-post-mia-', dir=ROOT / '.pytest_cache'))
        safe = prior.capture_support._environment(runtime)
        parent_env = prior.capture_support._environment(runtime, credentials)
        raw, errors, observed = capture([str(PYTHON), '-B', str(SOURCE), 'run',
            '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256],
            parent_env, DEADLINE_SECONDS + 30, stdout_limit=MAX_OUTPUT)
        outer['parent'] = observed
        credentials.clear(); parent_env.clear()
        require(observed['bound'] is None and not errors and type(observed['actual_exit']) is int
            and observed['actual_exit'] in (0, 2), 'parent_failed')
        command = ['/usr/bin/sandbox-exec', '-p', prior.native_profile(artifacts=True), str(PYTHON), '-B',
            str(SOURCE), 'validate', '--expected-head', args.expected_head,
            '--caller-sha256', args.caller_sha256, '--actual-exit', str(observed['actual_exit'])]
        valid, stderr, checked = capture(command, safe, 20, input_bytes=raw, stdout_limit=MAX_OUTPUT)
        outer['validator'] = checked
        require(type(checked['actual_exit']) is int and checked['actual_exit'] == 0
            and checked['bound'] is None and not stderr, 'validator_failed')
        outer['output'] = parse(valid); outer['output_authenticated'] = True
        require(len(canonical(outer)) <= MAX_OUTPUT + 4096, 'output_bound')
        return outer, observed['actual_exit']
    except BaseException as error:
        outer['failure_code'] = finite(error)
        return outer, 2
    finally:
        credentials.clear(); parent_env.clear()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('observe', 'run', 'validate'))
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--caller-sha256', required=True)
    parser.add_argument('--actual-exit', type=int)
    args = parser.parse_args(argv)
    if args.operation == 'observe':
        result, code = observe(args)
        sys.stdout.buffer.write(canonical(result)); return code
    deadline = time.monotonic() + (20 if args.operation == 'validate' else DEADLINE_SECONDS)
    try:
        with prior.admitted.helpers._alarm(deadline):
            preflight(args, deadline); environment._bootstrap_cli_logging()
            if args.operation == 'validate':
                payload = validate_output(sys.stdin.buffer.read(MAX_OUTPUT + 1), args.actual_exit, args)
                code = 0
            else:
                outcome = run(args, deadline)
                payload = {'binding': binding(args), 'outcome': outcome}
                code = 2 if 'failure' in outcome else 0
            raw = canonical(payload)
            require(len(raw) <= MAX_OUTPUT, 'output_bound')
            sys.stdout.buffer.write(raw); return code
    except BaseException as error:
        sys.stdout.buffer.write(canonical({'binding': binding(args), 'preflight_failure': finite(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
