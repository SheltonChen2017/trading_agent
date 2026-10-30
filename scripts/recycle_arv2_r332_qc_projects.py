"""One exact owner-directed Analyst-only recoverable QC cleanup batch.

The externally pinned metadata plan must come from the separate inventory.
Each target is freshly checked against its name, safe metadata and complete
history before its one delete dispatch. Unknown/changed state is preserved.
This does not provide an atomic lease against concurrent same-user edits.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
SOURCE = ROOT / 'scripts/recycle_arv2_r332_qc_projects.py'
INVENTORY = ROOT / 'scripts/inspect_arv2_r332_qc_cleanup.py'
POLICY = ROOT / 'scripts/arv2_r332_qc_cleanup_policy_v2.py'
RECORD = ROOT / 'docs/Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/qc_cleanup/R332-20261028-B'
PYTHON = '/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
BRANCH = 'codex/strategy-analyst-revisions-v2'
SCHEMA = 'arv2-r332-exact-Analyst-recycle-batch-v1'
PARENT_SECONDS, WORKER_SECONDS = 1200, 1100
ENTRY = time.monotonic()
lib = None


def require(value, code):
    if not value:
        raise ValueError(code)


def load_library(expected):
    import hashlib
    raw = INVENTORY.read_bytes()
    require(len(raw) <= 128 * 1024 and hashlib.sha256(raw).hexdigest() == expected, 'inventory_pin')
    module = type(sys)('r332_inventory_library')
    module.__file__ = str(INVENTORY)
    exec(compile(raw, str(INVENTORY), 'exec'), module.__dict__)
    return module


def plan_value(raw, expected):
    value = lib.parse(raw.encode('ascii'), 128 * 1024)
    require(lib.sha(lib.canonical(value)) == expected and type(value) is list
        and 0 < len(value) <= 256, 'plan')
    ids = []
    for row in value:
        require(type(row) is dict and set(row) == {'project_id', 'name', 'history_sha256',
            'summary_sha256', 'reason'}, 'plan')
        require(type(row['project_id']) is int and 0 < row['project_id'] < 2**31
            and type(row['name']) is str and 0 < len(row['name']) <= 240, 'plan')
        require(row['reason'] in ('verification_only', 'no_successful_backtest')
            and all(type(row[key]) is str and re.fullmatch('[0-9a-f]{64}', row[key])
                for key in ('history_sha256', 'summary_sha256')), 'plan')
        ids.append(row['project_id'])
    require(ids == sorted(set(ids)), 'plan')
    return value


def binding(args):
    return {'schema': SCHEMA, **{name: getattr(args, name) for name in
        ('expected_head', 'caller_sha256', 'inventory_sha256', 'policy_sha256',
         'record_sha256', 'plan_sha256')}}


def preflight(args):
    require(Path.cwd() == ROOT and ROOT.resolve() == ROOT and sys.platform == 'darwin'
        and sys.version_info[:2] == (3, 13) and sys.executable == PYTHON
        and sys.flags.isolated == 1 and Path(__file__).absolute() == SOURCE, 'host')
    for key in ('caller_sha256', 'inventory_sha256', 'policy_sha256', 'record_sha256', 'plan_sha256'):
        require(re.fullmatch('[0-9a-f]{64}', getattr(args, key)) is not None, 'arguments')
    require(re.fullmatch('[0-9a-f]{40}', args.expected_head) is not None, 'arguments')
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)),
        (['branch', '--show-current'], BRANCH), (['rev-parse', 'HEAD'], args.expected_head),
        (['status', '--porcelain'], '')):
        got = subprocess.run(['/usr/bin/git', *command], cwd=ROOT, env=lib.safe_env(),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        require(got.returncode == 0 and not got.stderr and got.stdout.decode().strip() == expected, 'git_state')
    lib.read_public(SOURCE, args.caller_sha256, 128 * 1024)
    lib.read_public(INVENTORY, args.inventory_sha256, 128 * 1024)
    policy_raw = lib.read_public(POLICY, args.policy_sha256, 128 * 1024)
    record_raw = lib.read_public(RECORD, args.record_sha256, 16 * 1024 * 1024)
    return policy_raw, record_raw, plan_value(args.plan_json, args.plan_sha256)


def catalog(api, policy):
    packet = api.request('projects/read', {})
    projects = packet.get('projects')
    require(type(projects) is list and len(projects) <= 1024, 'projects')
    ids = [row.get('projectId') for row in projects if type(row) is dict]
    require(len(ids) == len(projects) and all(type(i) is int and 0 < i < 2**31 for i in ids)
        and len(set(ids)) == len(ids), 'projects')
    return projects, policy.referenced_project_ids(projects)


def recycle(api, policy, record_raw, user_id, plan):
    initial, references = catalog(api, policy)
    # A record-confirmed Analyst study has a legacy name without ARV2.
    # Report only this explicit scope exception; it is protected, never a target.
    legacy = [row for row in initial if row['projectId'] == 37017548]
    retained = {'legacy_37017548_present': len(legacy) == 1,
        'legacy_37017548_exact_name': len(legacy) == 1
            and legacy[0].get('name') == 'Systematic Weekly Large-Cap Equity'}
    rows = []
    for expected in plan:
        project_id = expected['project_id']
        result = {'project_id': project_id, 'name': expected['name'], 'recycled': False}
        try:
            packet = api.request('projects/read', {'projectId': project_id})
            current = packet.get('projects')
            require(type(current) is list and len(current) == 1
                and current[0].get('projectId') == project_id, 'project')
            project = current[0]
            history = api.request('backtests/list', {'projectId': project_id, 'includeStatistics': False})
            decision = policy.decision(project, history, user_id=user_id,
                record_bytes=record_raw, referenced_ids=references)
            require(decision['eligible'] is True and decision['name'] == expected['name']
                and decision['history_sha256'] == expected['history_sha256']
                and decision['reason'] == expected['reason']
                and policy.digest(policy.project_summary(project, user_id)) == expected['summary_sha256'], 'changed_or_ineligible')
            # Other lanes may link a library while this batch is running.
            # Refresh incoming references and the target's idle/owner metadata
            # immediately before this mutation; this still is not an atomic lock.
            latest, references = catalog(api, policy)
            named = [item for item in latest if item['projectId'] == project_id]
            require(len(named) == 1 and project_id not in references
                and policy.digest(policy.project_summary(named[0], user_id)) == expected['summary_sha256'],
                'changed_or_ineligible')
            # No retry: this durable intent precedes the single deletion request.
            result['delete_attempted'] = True
            api.request('projects/delete', {'projectId': project_id})
            packet = api.request('projects/read', {'projectId': project_id})
            after = packet.get('projects')
            require(type(after) is list and len(after) == 1 and after[0].get('projectId') == project_id
                and type(after[0].get('name')) is str
                and after[0]['name'].startswith('Recycle Bin/')
                and after[0]['name'].endswith('/' + expected['name']), 'recycle_not_confirmed')
            result.update(recycled=True, reason=expected['reason'])
        except BaseException as error:
            # A mutation or its post-read may be ambiguous. Stop the batch;
            # never continue or redispatch that mutation on this claim.
            result['reason'] = safe_failure(error)
            result['deletion_outcome_ambiguous'] = result.get('delete_attempted') is True
            rows.append(result)
            return {**retained, 'complete': False, 'projects': rows, 'planned_count': len(plan),
                'recycled_count': sum(row['recycled'] for row in rows)}
        rows.append(result)
    return {**retained, 'complete': True, 'projects': rows, 'planned_count': len(plan),
        'recycled_count': sum(row['recycled'] for row in rows)}


def safe_failure(error):
    args = BaseException.args.__get__(error) if type(error) is ValueError else ()
    known = {'inventory_pin', 'host', 'arguments', 'git_state', 'plan', 'projects',
        'project', 'changed_or_ineligible', 'recycle_not_confirmed', 'child_failure', 'output'}
    if len(args) == 1 and type(args[0]) is str and args[0] in known:
        return args[0]
    return lib.finite(error) if lib is not None else 'unknown'


def worker(args):
    policy_raw, record_raw, plan = preflight(args)
    policy = type(sys)('r332_policy')
    exec(compile(policy_raw, str(POLICY), 'exec'), policy.__dict__)
    # A new B store; no global mutation or reading of inventory A's control.
    class Store(lib.Store):
        def __init__(self):
            self.parents = []
            self.intents = self.dispatches = 0
            fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.parents.append(fd)
            try:
                for part in CONTROL.relative_to(ROOT).parts[:-1]:
                    try:
                        child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    except FileNotFoundError:
                        os.mkdir(part, 0o700, dir_fd=fd)
                        os.fsync(fd)
                        child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    fd = child
                    require(os.fstat(fd).st_uid == os.getuid(), 'host')
                    self.parents.append(fd)
                os.mkdir(CONTROL.name, 0o700, dir_fd=fd)
                os.fsync(fd)
                self.fd = os.open(CONTROL.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                self.parents.append(self.fd)
                self.journal = os.open('dispatch.jsonl', os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                    0o600, dir_fd=self.fd)
            except BaseException:
                self.close()
                raise
    allowed = frozenset(row['project_id'] for row in plan)
    class API(lib.API):
        def request(self, endpoint, payload):
            require(type(payload) is dict and ((endpoint == 'projects/read' and payload == {})
                or (endpoint in ('projects/read', 'projects/delete') and set(payload) == {'projectId'}
                    and type(payload['projectId']) is int and payload['projectId'] in allowed)
                or (endpoint == 'backtests/list' and set(payload) == {'projectId', 'includeStatistics'}
                    and type(payload['projectId']) is int and payload['projectId'] in allowed
                    and payload['includeStatistics'] is False)), 'arguments')
            return self._exchange(endpoint, payload)
    store, api = Store(), None
    try:
        store.write('claim.json', {**binding(args), 'claimed_utc': lib.utc(), 'attempt_consumed': True})
        secret = lib.credentials(lib.parse(sys.stdin.buffer.read(4097), 4096))
        api = API(secret, store)
        result = recycle(api, policy, record_raw, int(secret['QC_USER_ID']), plan)
        preflight(args)
        report = {**binding(args), 'finished_utc': lib.utc(), 'result': result,
            'request_intent_count': store.intents,
            'application_dispatch_count': store.dispatches, 'physical_request_count_measured': False,
            'strategy_launch_performed': False, 'statistics_requested': False, 'Safari_access': False}
        output = {'report': report, 'report_pin': store.write('report.json', report)}
        raw = lib.canonical(output) + b'\n'
        require(len(raw) <= lib.MAX_OUTPUT, 'output')
        sys.stdout.buffer.write(raw)
        return 0 if result['complete'] else 2
    finally:
        if api is not None:
            api.close()
        store.close()


def launch(args):
    preflight(args)
    secret = lib.credentials({key: os.environ.get(key) for key in ('QC_USER_ID', 'QC_API_TOKEN')})
    profile = lib.native_profile().replace(str(lib.CONTROL), str(CONTROL))
    argv = ['/usr/bin/sandbox-exec', '-p', profile, PYTHON, '-I', '-B', str(SOURCE), 'worker']
    for key in ('expected_head', 'caller_sha256', 'inventory_sha256', 'policy_sha256', 'record_sha256', 'plan_sha256', 'plan_json'):
        argv.extend(('--' + key.replace('_', '-'), getattr(args, key)))
    child = subprocess.Popen(argv, cwd=ROOT, env=lib.safe_env(), stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        raw, err = child.communicate(lib.canonical(secret), timeout=max(1, PARENT_SECONDS - (time.monotonic() - ENTRY)))
    except BaseException:
        child.kill(); child.wait(timeout=5)
        raise ValueError('child_failure') from None
    require(not err and len(raw) <= lib.MAX_OUTPUT and raw.endswith(b'\n')
        and raw.count(b'\n') == 1, 'output')
    output = lib.parse(raw[:-1], lib.MAX_OUTPUT)
    require(type(output) is dict and set(output) == {'report', 'report_pin'}
        and lib.pin(lib.canonical(output['report'])) == output['report_pin']
        and all(output['report'].get(key) == value for key, value in binding(args).items()), 'output')
    preflight(args)
    accepted = child.returncode == 0 and output['report']['result']['complete'] is True
    sys.stdout.buffer.write(lib.canonical({'schema': SCHEMA + '-parent',
        'actual_child_exit': child.returncode, 'output_accepted': accepted, **output}) + b'\n')
    return 0 if accepted else 2


if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('mode', choices=('launch', 'worker'))
        for name in ('expected-head', 'caller-sha256', 'inventory-sha256', 'policy-sha256', 'record-sha256', 'plan-sha256', 'plan-json'):
            parser.add_argument('--' + name, required=True)
        args = parser.parse_args()
        lib = load_library(args.inventory_sha256)
        with lib.alarm(PARENT_SECONDS if args.mode == 'launch' else WORKER_SECONDS):
            status = launch(args) if args.mode == 'launch' else worker(args)
        raise SystemExit(status)
    except SystemExit:
        raise
    except BaseException as error:
        # No exception text, response or credential can cross this boundary.
        print('{"schema":"' + SCHEMA + '","failure_code":"' + safe_failure(error) + '"}')
        raise SystemExit(2)
