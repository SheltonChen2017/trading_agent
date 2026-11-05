"""One read-only metadata-shape observation for R332, never a recycle caller.

The frozen inventory transport is reused without invoking its producer or
opening its control. Only project37705240's selected environment fields cross
the boundary. Neither liveForm nor any account or last-live value is retained.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import types

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
SOURCE = ROOT / 'scripts/diagnose_arv2_r332_project_environment.py'
INVENTORY = ROOT / 'scripts/inspect_arv2_r332_qc_cleanup.py'
INVENTORY_SHA256 = '84a17a710ea1de2acb1a63ffa162c26200f8f6dbb5325ea1d48465a9053083a5'
RECORD = ROOT / 'docs/Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/qc_cleanup/R332-20261028-C'
PYTHON = '/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
BRANCH = 'codex/strategy-analyst-revisions-v2'
PROJECT = 37705240
SCHEMA = 'arv2-r332-one-project-environment-shape-v1'
PARENT_SECONDS, WORKER_SECONDS, MAX_OUTPUT = 90, 60, 16384
ENTRY = time.monotonic()


def load_inventory():
    fd = os.open(INVENTORY, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        raw = os.pread(fd, 128 * 1024, 0)
        if not (stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
                and before.st_nlink == 1 and len(raw) == before.st_size
                and hashlib.sha256(raw).hexdigest() == INVENTORY_SHA256):
            raise ValueError('inventory_source_pin')
        module = types.ModuleType('r332_frozen_inventory_transport')
        exec(compile(raw, str(INVENTORY), 'exec'), module.__dict__)
        module.require(module.metadata(os.fstat(fd)) == module.metadata(before)
            == module.metadata(INVENTORY.stat(follow_symlinks=False)), 'source_pin')
        return module
    finally:
        os.close(fd)


def environment():
    support = ROOT / '.pytest_cache/r332-environment-runtime'
    support.mkdir(mode=0o700, parents=True, exist_ok=True)
    if support.resolve() != support:
        raise ValueError('environment')
    return {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LC_ALL': 'C', 'LANG': 'C',
        'TMPDIR': str(support), 'PYTHONPYCACHEPREFIX': str(support / 'pycache'),
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'GIT_OPTIONAL_LOCKS': '0'}


def binding(args):
    return {'schema': SCHEMA, 'project_id': PROJECT, 'expected_head': args.expected_head,
        'caller_sha256': args.caller_sha256, 'inventory_sha256': INVENTORY_SHA256,
        'record_sha256': args.record_sha256}


def preflight(inv, args):
    inv.require(Path.cwd() == ROOT and ROOT.resolve() == ROOT and sys.platform == 'darwin'
        and os.name == 'posix' and sys.version_info[:2] == (3, 13) and sys.executable == PYTHON
        and Path(__file__).absolute() == SOURCE and sys.flags.isolated == 1, 'host')
    for key, width in (('expected_head', 40), ('caller_sha256', 64), ('record_sha256', 64)):
        inv.require(re.fullmatch('[0-9a-f]{' + str(width) + '}', getattr(args, key)) is not None, 'arguments')
    inv.read_public(SOURCE, args.caller_sha256, 128 * 1024)
    inv.read_public(INVENTORY, INVENTORY_SHA256, 128 * 1024)
    inv.read_public(RECORD, args.record_sha256, 16 * 1024 * 1024)
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)),
            (['branch', '--show-current'], BRANCH), (['rev-parse', 'HEAD'], args.expected_head),
            (['status', '--porcelain'], '')):
        row = subprocess.run(['/usr/bin/git', *command], cwd=ROOT, env=environment(),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        inv.require(row.returncode == 0 and not row.stderr and row.stdout.decode('utf-8').strip() == expected, 'git_state')


def native_profile(inv):
    old = str(inv.CONTROL)
    policy = inv.native_profile()
    inv.require(policy.count(old) == 2, 'policy')
    return policy.replace(old, str(CONTROL))


class Store:
    """Independent C control; no inherited A path or producer state."""
    def __init__(self, inv):
        self.inv, self.parents = inv, []
        self.intents = self.dispatches = 0
        fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.parents.append(fd)
        try:
            for part in CONTROL.relative_to(ROOT).parts[:-1]:
                try:
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                except FileNotFoundError:
                    os.mkdir(part, 0o700, dir_fd=fd); os.fsync(fd)
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                inv.require(os.fstat(child).st_uid == os.getuid(), 'control')
                self.parents.append(child); fd = child
            try:
                os.mkdir(CONTROL.name, 0o700, dir_fd=fd)
            except FileExistsError:
                raise inv.Refused('claim_spent') from None
            os.fsync(fd)
            self.fd = os.open(CONTROL.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            self.parents.append(self.fd)
            self.journal = os.open('dispatch.jsonl', os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                0o600, dir_fd=self.fd)
        except BaseException:
            self.close(); raise

    def write(self, name, value):
        inv = self.inv
        inv.require(name in ('claim.json', 'report.json', 'failure.json'), 'output')
        raw = inv.canonical(value); inv.require(len(raw) <= MAX_OUTPUT, 'bound')
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            inv.require(os.write(fd, raw) == len(raw), 'output')
            os.fsync(fd); os.fsync(self.fd); before = os.fstat(fd)
            inv.require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                and before.st_uid == os.getuid() and stat.S_IMODE(before.st_mode) == 0o600
                and before.st_size == len(raw) and os.pread(fd, len(raw) + 1, 0) == raw
                and inv.metadata(os.fstat(fd)) == inv.metadata(before)
                == inv.metadata(os.stat(name, dir_fd=self.fd, follow_symlinks=False)), 'output')
            return inv.pin(raw)
        finally:
            os.close(fd)

    def event(self, kind, endpoint, project):
        inv = self.inv
        inv.require(endpoint == 'projects/read' and project == PROJECT, 'arguments')
        raw = inv.canonical({'kind': kind, 'endpoint': endpoint, 'project_id': project,
            'utc': datetime.now(timezone.utc).isoformat()}) + b'\n'
        inv.require(os.write(self.journal, raw) == len(raw), 'output'); os.fsync(self.journal)

    def intent(self, endpoint, project):
        self.inv.require(self.intents == 0, 'arguments')
        self.event('request_intent', endpoint, project); self.intents += 1

    def attempt(self, endpoint, project):
        self.inv.require(self.dispatches == 0, 'arguments')
        self.event('application_dispatch_attempt', endpoint, project); self.dispatches += 1

    def close(self):
        if hasattr(self, 'journal'):
            os.close(self.journal); del self.journal
        for fd in reversed(self.parents):
            os.close(fd)
        self.parents = []


def shape(value):
    return {type(None): 'null', bool: 'boolean', int: 'integer', float: 'number',
        str: 'string', list: 'array', dict: 'object'}.get(type(value), 'other')


def last_live_class(project):
    if 'lastLiveDeployment' not in project:
        return 'missing'
    value = project['lastLiveDeployment']
    if value is None:
        return 'null'
    if value == '':
        return 'empty'
    if type(value) is not str or len(value) > 64:
        return 'other'
    if re.fullmatch(r'0001-01-01T00:00:00(?:[.]0+)?(?:Z|[+]00:00)?', value):
        return 'year0001_zero_sentinel'
    if re.fullmatch(r'1970-01-01T00:00:00(?:[.]0+)?(?:Z|[+]00:00)?', value):
        return 'unix_zero_sentinel'
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return 'nonempty_timestamp' if parsed.tzinfo is not None else 'other'
    except ValueError:
        return 'other'


def select_project(inv, packet, user_id):
    inv.require(type(packet) is dict and packet.get('success') is True
        and ('errors' not in packet or packet['errors'] == []), 'response')
    rows = packet.get('projects')
    inv.require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict, 'projects')
    project = rows[0]; inv.require(type(project.get('projectId')) is int and project['projectId'] == PROJECT, 'projects')
    name = project.get('name')
    inv.require(type(name) is str and 0 < len(name) <= 240 and name.isascii()
        and all(32 <= ord(c) < 127 for c in name), 'projects')
    lean = project.get('leanEnvironment')
    return {'project_id': PROJECT, 'name': name,
        'owner_match': project.get('owner') is True and type(project.get('ownerId')) is int
            and project['ownerId'] == user_id,
        'codeRunning': project.get('codeRunning') if type(project.get('codeRunning')) is bool else None,
        'leanEnvironment': lean if type(lean) is int and -(2**31) <= lean < 2**31 else None,
        'lastLiveDeployment_class': last_live_class(project),
        'field_shapes': {key: shape(project[key]) if key in project else 'missing'
            for key in ('owner', 'ownerId', 'codeRunning', 'leanEnvironment', 'lastLiveDeployment')}}


def worker(inv, args):
    preflight(inv, args); store = Store(inv); api = None
    try:
        store.write('claim.json', {**binding(args), 'attempt_consumed': True})
        secret = inv.credentials(inv.parse(sys.stdin.buffer.read(4097), 4096))
        class OneProjectAPI(inv.API):
            def request(self, endpoint, payload):
                inv.require(endpoint == 'projects/read' and type(payload) is dict
                    and set(payload) == {'projectId'} and type(payload['projectId']) is int
                    and payload['projectId'] == PROJECT and self.store.intents == 0, 'arguments')
                return self._exchange(endpoint, payload)
        api = OneProjectAPI(secret, store)
        # Fixed new path invokes only the transport primitive, never A's request
        # sequence, Store, worker or control. Store bounds the single dispatch.
        packet = api.request('projects/read', {'projectId': PROJECT})
        selected = select_project(inv, packet, int(secret['QC_USER_ID']))
        preflight(inv, args)
        result = {'complete': True, 'selected': selected, 'request_intent_count': store.intents,
            'application_dispatch_count': store.dispatches, 'http_status': api.last_http_status,
            'deletion_performed': False, 'Safari_access': False, 'physical_request_count_measured': False}
        report = {**binding(args), 'finished_utc': inv.utc(), 'result': result}
        report_pin = store.write('report.json', report)
        sys.stdout.buffer.write(inv.canonical({**report, 'report_pin': report_pin, 'attempt_consumed': True}) + b'\n')
        return 0
    except BaseException as error:
        value = {**binding(args), 'failure_code': inv.finite(error), 'attempt_consumed': True,
            'application_dispatch_count': store.dispatches, 'http_status': api.last_http_status if api else None,
            'deletion_performed': False}
        try:
            value['failure_pin'] = store.write('failure.json', value)
        except BaseException:
            pass
        sys.stdout.buffer.write(inv.canonical(value) + b'\n'); return 2
    finally:
        if api is not None:
            api.close()
        store.close()


def launch(inv, args):
    preflight(inv, args)
    secret = inv.credentials({key: os.environ.get(key) for key in ('QC_USER_ID', 'QC_API_TOKEN')})
    command = ['/usr/bin/sandbox-exec', '-p', native_profile(inv), PYTHON, '-I', '-B', str(SOURCE), 'worker',
        '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256,
        '--record-sha256', args.record_sha256]
    child = subprocess.Popen(command, cwd=ROOT, env=environment(), stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        raw, err = child.communicate(inv.canonical(secret), timeout=max(1, PARENT_SECONDS - (time.monotonic() - ENTRY)))
    except BaseException:
        child.kill(); child.wait(timeout=5); raise inv.Refused('child_failure') from None
    inv.require(not err and len(raw) <= MAX_OUTPUT and raw.endswith(b'\n') and raw.count(b'\n') == 1, 'output')
    packet = inv.parse(raw[:-1], MAX_OUTPUT)
    inv.require(type(packet) is dict and all(packet.get(key) == value for key, value in binding(args).items()), 'output')
    accepted = child.returncode == 0 and packet.get('result', {}).get('complete') is True
    if accepted:
        report = {**binding(args), 'finished_utc': packet.get('finished_utc'), 'result': packet['result']}
        inv.require(type(report['finished_utc']) is str and len(report['finished_utc']) <= 64
            and packet.get('report_pin') == inv.pin(inv.canonical(report)), 'output')
        preflight(inv, args)
    sys.stdout.buffer.write(inv.canonical({'schema': SCHEMA + '-parent', 'actual_child_exit': child.returncode,
        'output_accepted': accepted, 'child_output_pin': inv.pin(raw), 'child_envelope': packet}) + b'\n')
    return 0 if accepted else 2


if __name__ == '__main__':
    inv = None
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('mode', choices=('launch', 'worker'))
        for name in ('expected-head', 'caller-sha256', 'record-sha256'):
            parser.add_argument('--' + name, required=True)
        args = parser.parse_args(); inv = load_inventory()
        with inv.alarm(PARENT_SECONDS if args.mode == 'launch' else WORKER_SECONDS):
            code = launch(inv, args) if args.mode == 'launch' else worker(inv, args)
        raise SystemExit(code)
    except SystemExit:
        raise
    except BaseException as error:
        # Never render startup exceptions or inherited values.
        print('{"deletion_performed":false,"failure_code":"' + (inv.finite(error) if inv else 'source_pin')
            + '","attempt_reusable":false}')
        raise SystemExit(2)
