"""One first attempt for a remaining plain R343 arm, gated on accepted A4.

Each process exclusively consumes one candidate claim, authenticates eight
prepared DATA leaves before credentials, and allocates one new project. Exact
source/access/input gates precede one compile/job. Only matching Completed.
permits one bounded aggregate read and semantic validation. This preparation
refuses before DATA/contact while the genuine accepted A4 fact is unselected.
"""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import importlib
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec, PathFinder
from importlib.util import spec_from_loader
import json
import math
import os
from pathlib import Path
import re
import resource
import signal
import stat
import subprocess
import sys
import time
from types import ModuleType

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
BRANCH = 'codex/strategy-analyst-revisions-v2'
PYTHON = '/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
SOURCE = ROOT / 'scripts/run_arv2_r348_remaining_six.py'
PLAN = ROOT / 'scripts/arv2_r348_remaining_six_plan.json'
PARENT_PLAN = ROOT / 'scripts/arv2_r348_ar100_result_plan.json'
PARENT_PLAN_PIN = {'byte_count':39811,'sha256':'165de7a174f3c4b0cf873a2aae0e434bcbee0a92f9e0c8a533526c006b8e6a9c'}
SUPPORT = ROOT / '.pytest_cache/r348-remaining-six'
DATA_DIRECTORY = ROOT / 'artifacts/analyst_revisions_v2/legacy_six_plain/R346-20261107-A'
DATA_NAMES = ('evaluator-manifest.json','session_axis-0000.jsonl','memberships-0000.jsonl',
    'contributions-0000.jsonl','runtime_symbol_bindings-0000.jsonl','transport-manifest.json',
    'source-proposal.json','report.json')
CONTROL_PARENT = ROOT / 'artifacts/analyst_revisions_v2/legacy_six_runs'
SCHEMA = 'arv2-r348-remaining-six-operation-v1'
PLAN_SCHEMA = 'arv2-r348-remaining-six-plan-v1'
CANDIDATES = ('R343-AR080','R343-AR120','R343-AR140','R343-AR160','R343-AR180','R343-AR200')
A4_PROJECT = 39054561
PREPARATION_FACT = ROOT / 'scripts/arv2_r346_preparation_result_fact.json'
PREPARATION_FACT_PIN = {'byte_count':43136,'sha256':'c7b22ba9e82558e23097d3d0802f864a87f6ae56d1ef9d415045f4d9cb68b4cd'}
A4_RESULT_FACT = ROOT / 'scripts/arv2_r348_ar100_result_fact.json'
A4_RESULT_FACT_PIN = None
# Historical D1 failed and could not yield an accepted fact. A successor
# reader needs a new coherent contract; these pins must not auto-refresh.
D1_BINDING = {'schema':'arv2-r348-ar100-status-result-v1','candidate_id':'R343-AR100','attempt':4,
    'expected_head':'bf8e6064fb1eafdf099a697876a2406edd6e90e7',
    'caller_sha256':'d358ba396714685a6547bcb4c2108dc78b36398c0b7f8521c2440fc112c0d5dc',
    'plan_sha256':'165de7a174f3c4b0cf873a2aae0e434bcbee0a92f9e0c8a533526c006b8e6a9c',
    'profile_sha256':'216da6ed4fcb55457e3eda975be84b95261304b1f1034672062a788408b02186'}
CONSUMER_PATH = 'scripts/arv2_r348_plain_submission_data.py'
CONSUMER_PIN = {'byte_count':8604,'sha256':'f31257edf0d7b56d968818ad59820f7ba1cf3edac4be0a620bab5e87e85682f2'}
ENGINE_PATH = 'scripts/arv2_r348_legacy_six_qc.py'
VALIDATOR_PATH = 'scripts/arv2_r348_legacy_result.py'
TRANSPORT_PATH = 'scripts/arv2_r345_qc_error_transport_v3.py'
SECONDS, MAX_PUBLIC, MAX_PLAN, MAX_JOURNAL = 7200, 2 * 1024 * 1024, 256 * 1024, 8 * 1024 * 1024
MAX_OUTPUT, MAX_EVENTS = 128 * 1024, 4096
STATUS_CHECKS = 110
STATISTICS = ('ARV2_SIX_GATE_ORDER_META','ARV2_SIX_GATE_ORDER_AGGREGATES',
    'ARV2_SIX_GATE_ORDER_DIAGNOSTICS','ARV2_R343_LEGACY_SIX_PERIODS')
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags')
CREDENTIALS = ('QC_USER_ID', 'QC_API_TOKEN')
STAGE, CLAIM, LAST_FAILURE = 'preflight', 'unallocated', None
FLAGS = {'point_in_time_proven': False, 'formal_identity_admitted': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False}
FINITE = frozenset(('arguments', 'environment', 'git', 'plan', 'source_pin', 'source_changed',
    'inventory', 'claim_spent', 'control', 'deadline', 'data', 'credentials', 'access', 'capacity',
    'object_admission', 'request', 'operation', 'compile', 'launch', 'output', 'close', 'unknown',
    'a4_result_unselected','a4_result','status','runtime_error','not_completed','statistics','semantic'))


class Refused(ValueError):
    pass


class Deadline(BaseException):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise Refused('output') from None


def pin(raw):
    return {'byte_count': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def loads(raw, maximum):
    require(type(raw) is bytes and 0 < len(raw) <= maximum, 'plan')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'plan')
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('plan')))
        require(canonical(value) == raw, 'plan')
        return value
    except Refused:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('plan') from None


def valid_pin(value, maximum):
    return type(value) is dict and set(value) == {'byte_count', 'sha256'} and type(value['byte_count']) is int \
        and 0 <= value['byte_count'] <= maximum and type(value['sha256']) is str \
        and re.fullmatch('[0-9a-f]{64}', value['sha256']) is not None


def budget(deadline):
    left = deadline - time.monotonic()
    require(type(deadline) in (int, float) and math.isfinite(left) and 0 < left <= SECONDS, 'deadline')
    return left


def metadata(info):
    result = tuple(getattr(info, name, None) for name in FIELDS)
    require(all(type(item) is int and item >= 0 for item in result), 'source_changed')
    return result


def control(candidate):
    require(candidate in CANDIDATES, 'arguments')
    return CONTROL_PARENT / ('R348-20261107-' + candidate.removeprefix('R343-') + '-A1')


def safe_env():
    return {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C',
        'TMPDIR': str(SUPPORT), 'XDG_CACHE_HOME': str(SUPPORT / 'cache'),
        'SQLITE_TMPDIR': str(SUPPORT), 'PYTHONPYCACHEPREFIX': str(SUPPORT / 'pycache'),
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'GIT_OPTIONAL_LOCKS': '0'}


def native_profile(candidate):
    own = control(candidate)
    value = '(version 1)(allow default)(deny network-bind)(deny network-inbound)'
    value += '(deny network-outbound (require-all (require-not (remote tcp "*:443"))(require-not (remote tcp "*:53"))(require-not (remote udp "*:53"))(require-not (literal "/private/var/run/mDNSResponder"))))'
    for path in ('/Volumes', '/Users/sheltonchen/Library/Keychains', '/Library/Keychains'):
        value += '(deny file-read* file-write* (subpath ' + json.dumps(path) + '))'
    value += '(deny process-exec (literal "/usr/bin/security"))(deny file-read-data (regex "[.]pyc$"))'
    value += '(deny file-write* (require-all (require-not (subpath ' + json.dumps(str(own)) + '))'
    value += '(require-not (literal ' + json.dumps(str(CONTROL_PARENT)) + '))'
    value += '(require-not (subpath ' + json.dumps(str(SUPPORT)) + '))(require-not (literal "/dev/null"))))'
    data_paths = tuple(DATA_DIRECTORY / name for name in DATA_NAMES)
    ancestors = {path for leaf in (*data_paths, own) for path in leaf.parents
        if path == ROOT / 'artifacts' or ROOT / 'artifacts' in path.parents}
    value += '(deny file-read* (require-all (subpath ' + json.dumps(str(ROOT / 'artifacts')) + ')'
    value += ''.join('(require-not (literal ' + json.dumps(str(path)) + '))' for path in data_paths)
    value += '(require-not (subpath ' + json.dumps(str(own)) + '))'
    value += ''.join('(require-not (literal ' + json.dumps(str(path)) + '))' for path in sorted(ancestors)) + '))'
    return value


def profile_record(candidate):
    require(candidate in CANDIDATES, 'arguments')
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': BRANCH, 'python': PYTHON,
        'candidate_id': candidate, 'attempt': 1, 'control': str(control(candidate)),
        'preparation_fact_pin': dict(PREPARATION_FACT_PIN),
        'accepted_A4_result_fact_pin': A4_RESULT_FACT_PIN, 'parent_plan_pin':dict(PARENT_PLAN_PIN),
        'preparation_status': 'unselected_A4_result_refuses_before_DATA_or_contact' if A4_RESULT_FACT_PIN is None
            else 'selected_prerequisite_still_requires_exact_clean_run_freeze',
        'scope': 'one_first_attempt_new_own_project_for_one_remaining_arm_no_AR100_replay',
        'maximum_attempts_per_candidate':3,'automatic_retry_permitted':False,
        'data_directory':str(DATA_DIRECTORY),'exact_data_names':list(DATA_NAMES),'plan': str(PLAN), 'seconds': SECONDS,
        'native_policy_sha256': pin(native_profile(candidate).encode())['sha256'],
        'credential_policy': 'existing_environment_after_exclusive_claim_and_DATA_guard_normal_return',
        'object_policy': 'six_exact_prepared_plain_properties_size_and_MD5_metadata_before_mutation_and_launch_no_get_download_upload',
        'object_qualification': 'metadata_MD5_is_not_remote_SHA256_attestation_runtime_reader_checks_all_SHA256',
        'source_policy': 'all_selected_bytes_held_compiled_full_metadata_empty_ACL_all_observed_public_xattrs',
        'error_observation': 'new_bounded_response_and_context_redacted_error_projection_before_discard_no_raw_retention',
        'failed_HTTP_body': 'new_bounded_identity_encoded_JSON_only_non200_max64KiB_never_arbitrary_download',
        'max_output_bytes': MAX_OUTPUT, 'max_failure_evidence_bytes': 48 * 1024,
        'max_API_diagnostic_bytes': 24 * 1024,
        'terminal': 'one_job_bounded_statistics_disabled_status_until_Completed_then_one_aggregate_read_and_semantic_check',
        'status_checks':STATUS_CHECKS,'status_interval_seconds':60,
        'result_statistics':list(STATISTICS),'result_body_qualification':
            'bounded_full_JSON_parsed_ephemerally_only_four_selected_custom_strings_retained',
        'privacy_qualification':'missing_API_public_is_unknown_no_continuous_privacy_proof',
        'deadline_qualification': 'cannot_bound_uninterruptible_IO_or_host_suspension', **FLAGS}


def binding(args):
    require(args.candidate in CANDIDATES and type(args.expected_head) is str
        and re.fullmatch('[0-9a-f]{40}', args.expected_head)
        and all(type(getattr(args, key)) is str and re.fullmatch('[0-9a-f]{64}', getattr(args, key))
            for key in ('caller_sha256', 'plan_sha256')), 'arguments')
    return {'schema': SCHEMA, 'candidate_id': args.candidate, 'attempt': 1,
        'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256,
        'plan_sha256': args.plan_sha256, 'profile_sha256': pin(canonical(profile_record(args.candidate)))['sha256']}


def preflight(args, deadline):
    require(valid_pin(A4_RESULT_FACT_PIN,MAX_PUBLIC), 'a4_result_unselected')
    bound = binding(args)
    require(Path.cwd() == ROOT and ROOT.resolve() == ROOT and sys.platform == 'darwin'
        and os.name == 'posix' and sys.version_info[:2] == (3, 13) and sys.executable == PYTHON
        and sys.flags.isolated == 1 and sys.dont_write_bytecode and Path(__file__).absolute() == SOURCE, 'environment')
    safe = safe_env()
    require(set(os.environ) <= set(safe) | set(CREDENTIALS) | {'__CF_USER_TEXT_ENCODING'}
        and all(os.environ.get(key) == value for key, value in safe.items())
        and ('__CF_USER_TEXT_ENCODING' not in os.environ
            or os.environ['__CF_USER_TEXT_ENCODING'] == f'0x{os.getuid():X}:0x0:0x0'), 'environment')
    for key in ('TMPDIR', 'XDG_CACHE_HOME', 'SQLITE_TMPDIR', 'PYTHONPYCACHEPREFIX'):
        path = Path(safe[key]); require(path.is_dir() and path.resolve() == path, 'environment')
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)), (['branch', '--show-current'], BRANCH),
            (['rev-parse', 'HEAD'], args.expected_head), (['status', '--porcelain'], '')):
        result = subprocess.run(['/usr/bin/git', *command], cwd=ROOT, env=safe, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=min(15, budget(deadline)), check=False)
        require(result.returncode == 0 and not result.stderr and len(result.stdout) <= 262144
            and result.stdout.decode('ascii').strip() == expected, 'git')
    return bound


def validate_a4_result_fact(raw):
    """Pinned original-result consistency, followed by fresh DATA semantics.

    Exit observations remain external facts, not process attestation.
    """
    require(valid_pin(A4_RESULT_FACT_PIN,MAX_PUBLIC), 'a4_result_unselected')
    require(type(raw) is bytes and pin(raw)==A4_RESULT_FACT_PIN and raw.endswith(b'\n'), 'a4_result')
    fact=loads(raw[:-1],MAX_PUBLIC)
    require(type(fact) is dict and fact.get('schema')=='arv2-r348-ar100-result-fact-v1'
        and type(fact.get('observation')) is dict and type(fact.get('original_result')) is dict,'a4_result')
    observation=fact['observation'];original=fact['original_result']
    require(type(observation.get('actual_exit')) is int and observation['actual_exit']==0
        and observation.get('original_stdout_validated') is True
        and observation.get('original_stdout_pin')==pin(canonical(original)+b'\n')
        and set(original)=={'schema','binding','attempt_consumed','result','report_pin'}
        and original.get('schema')=='arv2-r348-ar100-status-result-v1-result'
        and original.get('attempt_consumed') is True and type(original.get('result')) is dict
        and original.get('report_pin')==pin(canonical({key:value for key,value in original.items()
            if key!='report_pin'})),'a4_result')
    result=original['result'];validation=result.get('semantic_validation')
    binding=original.get('binding');source=result.get('source')
    require(result.get('candidate_id')=='R343-AR100' and type(result.get('attempt')) is int
        and result['attempt']==4 and type(result.get('project_id')) is int and result['project_id']==A4_PROJECT
        and result.get('backtest_id')=='007d4ab27c26d337ae53acb492a83410'
        and result.get('compile_id')=='251b7dbcc94a6db5740a3b83a83ec133-232313c1c0b6b9f62aae03cca921fd2f'
        and result.get('backtest_name')=='ARV2 LEGACY SIX R343-AR100 OCT2026 A4'
        and result.get('observed_status')=='Completed.' and result.get('result_read') is True
        and result.get('selected_result_read') is True and type(validation) is dict
        and validation.get('accepted') is True and validation.get('run_valid') is True
        and type(result.get('statistics')) is dict and set(result['statistics'])==set(STATISTICS)
        and result.get('statistics_pin')==pin(canonical(result['statistics']))
        and type(binding) is dict and canonical(binding)==canonical(D1_BINDING)
        and binding.get('schema')=='arv2-r348-ar100-status-result-v1'
        and binding.get('candidate_id')=='R343-AR100' and type(binding.get('attempt')) is int
        and binding['attempt']==4 and type(binding.get('expected_head')) is str
        and re.fullmatch('[0-9a-f]{40}',binding['expected_head'])
        and all(type(binding.get(key)) is str and re.fullmatch('[0-9a-f]{64}',binding[key])
            for key in ('caller_sha256','plan_sha256','profile_sha256'))
        and type(source) is dict and type(source.get('file_count')) is int and source['file_count']==18
        and type(source.get('source_byte_total')) is int and source['source_byte_total']==417652
        and source.get('source_inventory_pin')=={'byte_count':2775,
            'sha256':'71857bac63298b6b9dd4221ffc180ca4a59f10574edd109220a335d9370a232c'}
        and all(result.get(key) is False for key in FLAGS),'a4_result')
    return fact


def validate_a4_prerequisite(fact,submission,validator):
    """Join the pinned original result to current freshly authenticated DATA."""
    fact=validate_a4_result_fact(canonical(fact)+b'\n')
    candidates=[item for item in submission.candidates if item.candidate_id=='R343-AR100']
    require(len(candidates)==1,'a4_result')
    result=fact['original_result']['result']
    identity=loads(submission.source_identity_json,MAX_OUTPUT)
    require(type(identity) is dict and canonical(result.get('input_source_identity'))==canonical(identity),
            'a4_result')
    checked=validator.validate_statistics(result['statistics'],candidate_record=candidates[0].cell_record(),
        evaluation_sessions=submission.evaluation_sessions)
    require(type(checked) is dict and len(canonical(checked))<=16384
        and checked.get('accepted') is True and checked.get('run_valid') is True
        and canonical(checked)==canonical(result['semantic_validation']),'a4_result')
    return {'accepted_A4_prerequisite_recomputed':True,
        'original_stdout_pin':fact['observation']['original_stdout_pin'],
        'semantic_validation_pin':pin(canonical(checked)),'current_input_identity_pin':pin(canonical(identity))}


def build_plan(parent_raw, additional_buffers):
    """Pure public-buffer preparation; generated pins are not run authority."""
    require(pin(parent_raw)==PARENT_PLAN_PIN,'plan')
    parent=loads(parent_raw,MAX_PLAN)
    require(type(parent) is dict and type(parent.get('source_pins')) is dict
        and len(parent['source_pins'])==210,'plan')
    require(parent['source_pins'].get(CONSUMER_PATH)==CONSUMER_PIN
        and VALIDATOR_PATH in parent['source_pins'],'source_pin')
    keys={ENGINE_PATH,A4_RESULT_FACT.relative_to(ROOT).as_posix()}
    require(type(additional_buffers) is dict and set(additional_buffers)==keys
        and all(type(raw) is bytes and 0<len(raw)<=MAX_PUBLIC for raw in additional_buffers.values()),'plan')
    validate_a4_result_fact(additional_buffers[A4_RESULT_FACT.relative_to(ROOT).as_posix()])
    pins=dict(parent['source_pins'])
    require(not (set(pins)&keys),'inventory')
    pins.update({name:pin(raw) for name,raw in additional_buffers.items()})
    return canonical({'schema':PLAN_SCHEMA,'candidate_ids':list(CANDIDATES),'attempt':1,
        'parent_plan_pin':PARENT_PLAN_PIN,'a4_result_fact_pin':A4_RESULT_FACT_PIN,'source_pins':pins})


class Sources:
    """Selected code/JSON held through the operation and executed from buffers."""
    def __init__(self, args, deadline):
        self.args, self.deadline, self.rows, self.cache, self.raws = args, deadline, [], {}, {}
        self.finder = self.security = self.public_security = None

    def hold(self, path, expected):
        require(valid_pin(expected, MAX_PUBLIC), 'source_pin')
        if not self.cache:
            fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.cache[Path('/')] = (fd, fd, '.', metadata(os.fstat(fd)))
        row = self.cache[Path('/')]
        current = Path('/')
        for part in path.parts[1:-1]:
            budget(self.deadline); current /= part
            if current not in self.cache:
                before = metadata(os.stat(part, dir_fd=row[0], follow_symlinks=False))
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=row[0])
                self.cache[current] = (fd, row[0], part, before)
                require(stat.S_ISDIR(before[2]) and metadata(os.fstat(fd)) == before, 'source_changed')
            row = self.cache[current]
        before = metadata(os.stat(path.name, dir_fd=row[0], follow_symlinks=False))
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=row[0])
        item = [fd, row[0], path.name, before, expected, None]
        self.rows.append(item)
        require(stat.S_ISREG(before[2]) and before[3] == os.getuid() and before[5] == 1
            and stat.S_IMODE(before[2]) in (0o600, 0o644) and metadata(os.fstat(fd)) == before, 'source_pin')
        raw = os.pread(fd, MAX_PUBLIC + 1, 0)
        require(pin(raw) == expected and before[6] == len(raw), 'source_pin')
        return raw

    def __enter__(self):
        try:
            self.hold(SOURCE, {'byte_count': SOURCE.stat().st_size, 'sha256': self.args.caller_sha256})
            raw = self.hold(PLAN, {'byte_count': PLAN.stat().st_size, 'sha256': self.args.plan_sha256})
            require(len(raw) <= MAX_PLAN, 'plan')
            self.plan = loads(raw, MAX_PLAN)
            require(type(self.plan) is dict and set(self.plan) == {'schema','candidate_ids','attempt',
                'parent_plan_pin','a4_result_fact_pin','source_pins'}
                and self.plan['schema'] == PLAN_SCHEMA and self.plan['candidate_ids']==list(CANDIDATES)
                and type(self.plan['attempt']) is int and self.plan['attempt']==1
                and self.plan['parent_plan_pin']==PARENT_PLAN_PIN
                and valid_pin(A4_RESULT_FACT_PIN,MAX_PUBLIC)
                and self.plan['a4_result_fact_pin']==A4_RESULT_FACT_PIN
                and type(self.plan['source_pins']) is dict, 'plan')
            parent = loads(self.hold(PARENT_PLAN,PARENT_PLAN_PIN),MAX_PLAN)
            require(type(parent) is dict and type(parent.get('source_pins')) is dict
                and len(parent['source_pins'])==210, 'plan')
            fact_path=A4_RESULT_FACT.relative_to(ROOT).as_posix()
            additional = {ENGINE_PATH,fact_path}
            require(set(self.plan['source_pins'])==set(parent['source_pins'])|additional
                and all(self.plan['source_pins'].get(key)==value for key,value in parent['source_pins'].items())
                and self.plan['source_pins'].get(CONSUMER_PATH)==CONSUMER_PIN
                and self.plan['source_pins'].get(fact_path)==A4_RESULT_FACT_PIN, 'inventory')
            soft, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
            require(soft == resource.RLIM_INFINITY or soft >= len(self.plan['source_pins']) + 180, 'environment')
            for relative, expected in sorted(self.plan['source_pins'].items()):
                require(type(relative) is str and not relative.startswith('/') and '..' not in Path(relative).parts
                    and relative.endswith(('.py', '.json')) and 'artifacts' not in Path(relative).parts
                    and relative != PLAN.relative_to(ROOT).as_posix(), 'plan')
                self.raws[relative] = self.hold(ROOT / relative, expected)
            for required in ('scripts/arv2_relocation_security.py', 'scripts/prepare_arv2_r343_legacy_six.py',
                    'scripts/arv2_r343_legacy_six_source_pins.json',CONSUMER_PATH,ENGINE_PATH,VALIDATOR_PATH,TRANSPORT_PATH,
                    'scripts/arv2_r298_qc_error_text.py','scripts/arv2_r298_qc_response_evidence.py',
                    fact_path,PREPARATION_FACT.relative_to(ROOT).as_posix()):
                require(required in self.raws, 'inventory')
            original = loads(self.raws['scripts/arv2_r343_legacy_six_source_pins.json'], MAX_PUBLIC)
            require(type(original) is dict and type(original.get('files')) is dict
                and all(self.plan['source_pins'].get(key) == expected for key, expected in original['files'].items()), 'inventory')
            helper = ModuleType('_r345_public_source_helpers')
            exec(compile(self.raws['scripts/prepare_arv2_r343_legacy_six.py'],
                str(ROOT / 'scripts/prepare_arv2_r343_legacy_six.py'), 'exec'), helper.__dict__)
            security_module = ModuleType('_r345_exact_security')
            exec(compile(self.raws['scripts/arv2_relocation_security.py'],
                str(ROOT / 'scripts/arv2_relocation_security.py'), 'exec'), security_module.__dict__)
            self.security, self.public_security = security_module, helper.public_source_security
            for item in self.rows:
                item[5] = self.public_security(item[0], self.security)
            names = {key[:-3].replace('/', '.').removesuffix('.__init__'): key
                for key in self.raws if key.endswith('.py')}
            require('scripts' not in sys.modules and not any(name in sys.modules for name in names), 'environment')
            raws = self.raws
            class ExactLoader(Loader):
                def __init__(self, relative): self.relative = relative
                def create_module(self, spec): return None
                def exec_module(self, module):
                    module.__file__ = str(ROOT / self.relative)
                    if self.relative.endswith('/__init__.py'):
                        module.__path__ = [str((ROOT / self.relative).parent)]
                    exec(compile(raws[self.relative], module.__file__, 'exec'), module.__dict__)
            class ExactFinder(MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if fullname == 'scripts':
                        result = ModuleSpec(fullname, loader=None, is_package=True)
                        result.submodule_search_locations = [str(ROOT / 'scripts')]
                        return result
                    if fullname in names:
                        relative = names[fullname]
                        return spec_from_loader(fullname, ExactLoader(relative), origin=str(ROOT / relative),
                            is_package=relative.endswith('/__init__.py'))
                    found = PathFinder.find_spec(fullname, path)
                    origin = None if found is None else found.origin
                    require(not (type(origin) is str and Path(origin).is_absolute()
                        and Path(origin).is_relative_to(ROOT)), 'source_pin')
                    return None
            self.finder = ExactFinder(); sys.meta_path.insert(0, self.finder)
            self.consumer = importlib.import_module(CONSUMER_PATH[:-3].replace('/','.'))
            self.engine = importlib.import_module(ENGINE_PATH[:-3].replace('/','.'))
            self.validator = importlib.import_module(VALIDATOR_PATH[:-3].replace('/','.'))
            self.preparation_fact_bytes=self.raws[PREPARATION_FACT.relative_to(ROOT).as_posix()]
            self.consumer.parse_fact(self.preparation_fact_bytes)
            self.accepted_A4_fact=validate_a4_result_fact(self.raws[fact_path])
            self.transport = importlib.import_module(TRANSPORT_PATH[:-3].replace('/','.'))
            self.verify()
            return self
        except BaseException:
            self.close(); raise

    def verify(self):
        for fd, parent, name, before in self.cache.values():
            budget(self.deadline)
            require(metadata(os.fstat(fd)) == before == metadata(os.stat(name, dir_fd=parent, follow_symlinks=False)), 'source_changed')
        for fd, parent, name, before, expected, native in self.rows:
            budget(self.deadline)
            require(metadata(os.fstat(fd)) == before == metadata(os.stat(name, dir_fd=parent, follow_symlinks=False))
                and pin(os.pread(fd, MAX_PUBLIC + 1, 0)) == expected, 'source_changed')
            if native is not None:
                require(self.public_security(fd, self.security) == native, 'source_changed')

    def close(self):
        if self.finder in sys.meta_path:
            sys.meta_path.remove(self.finder)
        failed = False
        for fd in [item[0] for item in reversed(self.rows)] + [row[0] for row in reversed(tuple(self.cache.values()))]:
            try: os.close(fd)
            except OSError: failed = True
        self.rows.clear(); self.cache.clear()
        require(not failed, 'close')

    def __exit__(self, *_):
        try: self.verify()
        finally: self.close()


class Store:
    """Exclusive original-FD claim, append-only fsynced journal and final output."""
    def __init__(self, path, security_module, *, candidate):
        require(candidate in CANDIDATES and path==control(candidate),'arguments')
        self.path, self.security = path, security_module
        self.candidate,self.allocated_project_id=candidate,None
        self.chain, self.leaves, self.events = [], [], bytearray()
        self.fd = self.journal_fd = None
        self.application_dispatch_count = self.intents = self.event_count = 0
        self.first_evaluation_dispatch = None
    def __enter__(self):
        global CLAIM
        try:
            parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.chain.append([parent, parent, '.', metadata(os.fstat(parent)), None])
            path = Path('/')
            for part in self.path.parts[1:]:
                path /= part
                if path in (self.path.parent, self.path):
                    try:
                        os.mkdir(part, 0o700, dir_fd=parent); os.fsync(parent)
                        if path == self.path: CLAIM = 'allocated_unknown'
                        old = self.chain[-1]; after = metadata(os.fstat(parent))
                        require(all(after[i] == old[3][i] for i in (0, 1, 2, 3, 4, 9)), 'control')
                        old[3] = after
                    except FileExistsError:
                        require(path != self.path, 'claim_spent')
                before = metadata(os.stat(part, dir_fd=parent, follow_symlinks=False))
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                checked = path == ROOT or ROOT in path.parents
                require(stat.S_ISDIR(before[2]) and metadata(os.fstat(fd)) == before
                    and (not checked or before[3] == os.getuid() and stat.S_IMODE(before[2]) == (0o755 if path == ROOT else 0o700)), 'control')
                self.chain.append([fd, parent, part, before, self.security.snapshot(fd) if checked else None])
                parent = fd
            self.fd = parent; self.verify(); return self
        except BaseException:
            self.close(); raise
    def verify(self):
        require(self.fd is not None and set(os.listdir(self.fd)) == {item[0] for item in self.leaves}, 'control')
        for fd, parent, name, before, native in self.chain:
            require(metadata(os.fstat(fd)) == before == metadata(os.stat(name, dir_fd=parent, follow_symlinks=False))
                and (native is None or self.security.snapshot(fd) == native), 'control')
        for name, fd, before, native, raw in self.leaves:
            require(metadata(os.fstat(fd)) == before == metadata(os.stat(name, dir_fd=self.fd, follow_symlinks=False))
                and self.security.snapshot(fd) == native and os.pread(fd, len(raw) + 1, 0) == raw, 'control')
    def write(self, name, value):
        global CLAIM
        require(name in ('claim.json', 'events.jsonl', 'report.json', 'failure.json'), 'output')
        raw = canonical(value) if name != 'events.jsonl' else value
        require(type(raw) is bytes and len(raw) <= MAX_JOURNAL, 'output')
        self.verify(); before = self.chain[-1][3]
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            require(not raw or os.write(fd, raw) == len(raw), 'output'); os.fsync(fd)
            info = metadata(os.fstat(fd)); secure = self.security.snapshot(fd)
            require(stat.S_ISREG(info[2]) and info[3] == os.getuid() and info[5] == 1
                and stat.S_IMODE(info[2]) == 0o600, 'control')
            self.leaves.append([name, fd, info, secure, raw]); fd = None
            after = metadata(os.fstat(self.fd))
            require(all(after[i] == before[i] for i in (0, 1, 2, 3, 4, 9)), 'control')
            self.chain[-1][3] = after; os.fsync(self.fd); self.verify()
            if name == 'claim.json': CLAIM = 'consumed'
            if name == 'events.jsonl': self.journal_fd = self.leaves[-1][1]
            return pin(raw)
        finally:
            if fd is not None: os.close(fd)
    def journal(self, marker, value):
        require(type(marker) is str and re.fullmatch('[a-z0-9-]{1,120}', marker)
            and self.journal_fd is not None and self.event_count < MAX_EVENTS, 'output')
        raw = canonical({'ordinal': self.event_count, 'marker': marker, 'value': value}) + b'\n'
        require(len(raw) <= 32768 and len(self.events) + len(raw) <= MAX_JOURNAL, 'output')
        self.verify()
        row = next(item for item in self.leaves if item[0] == 'events.jsonl')
        before = row[2]
        require(os.lseek(self.journal_fd, 0, os.SEEK_END) == len(self.events)
            and os.write(self.journal_fd, raw) == len(raw), 'output')
        os.fsync(self.journal_fd); after = metadata(os.fstat(self.journal_fd))
        require(all(after[i] == before[i] for i in (0, 1, 2, 3, 4, 5, 9)), 'control')
        self.events.extend(raw); row[2], row[4] = after, bytes(self.events)
        self.event_count += 1; self.verify()
        if marker=='project-created':
            require(type(value) is dict and value.get('candidate_id')==self.candidate
                and type(value.get('project_id')) is int and 0<value['project_id']<2**63
                and self.allocated_project_id is None,'request')
            self.allocated_project_id=value['project_id']
    def intent(self, endpoint, project_id):
        self.journal('http-intent', {'endpoint': endpoint, 'project_id': project_id, 'ordinal': self.intents})
        self.intents += 1
    def attempt(self, endpoint, project_id):
        require(self.application_dispatch_count < self.intents, 'request')
        self.journal('http-dispatch', {'endpoint': endpoint, 'project_id': project_id, 'ordinal': self.application_dispatch_count})
        if endpoint in ('compile/create', 'backtests/create') and self.first_evaluation_dispatch is None:
            require(type(project_id) is int and project_id==self.allocated_project_id
                and project_id!=A4_PROJECT, 'request')
            self.first_evaluation_dispatch = {'endpoint': endpoint,
                'application_dispatch_ordinal': self.application_dispatch_count,
                'candidate_id': self.candidate, 'attempt': 1}
        self.application_dispatch_count += 1
    def look_accounting(self):
        spent = int(self.first_evaluation_dispatch is not None)
        return {'shared_look_delta': spent, 'development_look_delta': spent,
            'infrastructure_look_delta': 0, 'accepted_result_cell_delta': 0,
            'first_application_dispatch': None if not spent else dict(self.first_evaluation_dispatch),
            'physical_request_count_measured': False}
    def close(self):
        failed = False
        for fd in [row[1] for row in reversed(self.leaves)] + [row[0] for row in reversed(self.chain)]:
            try: os.close(fd)
            except OSError: failed = True
        self.leaves.clear(); self.chain.clear(); self.fd = self.journal_fd = None
        require(not failed, 'close')
    def __exit__(self, *_):
        try: self.verify()
        finally: self.close()


def result_access(project_packet,dedicated_packet,operation,user_id):
    """Current read-only access, not new mutation or continuous privacy proof."""
    require(type(project_packet) is dict and project_packet.get('success') is True
        and type(dedicated_packet) is dict and dedicated_packet.get('success') is True,'access')
    rows=project_packet.get('projects')
    require(type(rows) is list and len(rows)==1 and type(rows[0]) is dict,'access')
    row=rows[0]
    require(type(row.get('projectId')) is int and row['projectId']==operation.project_id
        and row.get('name')==operation.name and row.get('language')=='Py'
        and row.get('organizationId')==operation.organization and row.get('owner') is True
        and type(row.get('ownerId')) is int and row['ownerId']==user_id
        and type(row.get('codeRunning')) is bool and ('public' not in row or row['public'] is False)
        and type(row.get('libraries')) is list and not row['libraries']
        and ('libraryIds' not in row or type(row['libraryIds']) is list and not row['libraryIds'])
        and ('isLibrary' not in row or row['isLibrary'] is False)
        and 'lastLiveDeployment' in row and row['lastLiveDeployment'] in (None,'')
        and type(row.get('leanEnvironment')) is int and row['leanEnvironment']>=0
        and all(key not in row or row[key] is False for key in ('liveMode','liveRunning','live'))
        and ('liveResults' not in row or type(row['liveResults']) is list and not row['liveResults']),'access')
    for packet in (project_packet,dedicated_packet):
        require(('projectId' not in packet or type(packet['projectId']) is int
            and packet['projectId']==operation.project_id)
            and ('organizationId' not in packet or packet['organizationId']==operation.organization),'access')
    general,owners=row.get('collaborators'),dedicated_packet.get('collaborators')
    require(type(owners) is list and len(owners)==1 and type(owners[0]) is dict
        and canonical(owners[0])==operation._owner_raw and owners[0].get('owner') is True
        and type(owners[0].get('uid')) is int and owners[0]['uid']==user_id
        and owners[0].get('permission')=='write' and owners[0].get('liveControl') is True
        and dedicated_packet.get('userPermissions')=='write' and dedicated_packet.get('userLiveControl') is True
        and type(general) is list and len(general) in (1,2)
        and all(type(item) is dict for item in general),'access')
    if len(general)==1:
        require(canonical(general)==canonical(owners),'access')
    else:
        require(pin(canonical(general))==operation._general_pin,'access')
    return {'dedicated_owner_only':True,'general_row_count':len(general),
        'general_rows_pin':pin(canonical(general)),'dedicated_rows_pin':pin(canonical(owners)),
        'private_field_present_and_false':'public' in row and row['public'] is False,
        'privacy_proven':False,'exclusive_resource_lease':False,'mutation_authority_granted':False}


def result_sources(packet,operation):
    require(type(packet) is dict and packet.get('success') is True
        and ('projectId' not in packet or type(packet['projectId']) is int
            and packet['projectId']==operation.project_id),'operation')
    rows=packet.get('files');seen={}
    require(type(rows) is list and len(rows)==len(operation.sources)==18,'operation')
    for row in rows:
        require(type(row) is dict and type(row.get('projectId')) is int
            and row['projectId']==operation.project_id and type(row.get('name')) is str
            and row['name'] in operation.sources and row['name'] not in seen
            and type(row.get('content')) is str and row['content']==operation.sources[row['name']],'operation')
        seen[row['name']]=row['content']
    vector=[{'project_path':name,**pin(raw.encode('ascii'))} for name,raw in sorted(seen.items())]
    return {'file_count':18,'source_inventory_pin':pin(canonical(vector)),
        'source_byte_total':sum(len(raw) for raw in seen.values())}


def selected_statistics(packet,operation):
    require(type(packet) is dict and packet.get('success') is True,'statistics')
    row=packet.get('backtest');receipt=operation.launch_receipt
    require(type(row) is dict and type(row.get('projectId')) is int and row['projectId']==operation.project_id
        and row.get('backtestId')==receipt['backtest_id'] and row.get('name')==operation.backtest_name
        and row.get('status')=='Completed.' and ('compileId' not in row or row['compileId']==operation.compile_id),
        'statistics')
    values=row.get('statistics')
    require(type(values) is dict and all(type(key) is str for key in values),'statistics')
    names={name for name in values if name.startswith('ARV2_')}
    require(names in (set(STATISTICS[:3]),set(STATISTICS)),'statistics')
    selected={}
    for name in sorted(names):
        text=values[name];maximum=16384 if name.endswith('DIAGNOSTICS') else 8192
        require(type(text) is str and text.isascii() and 0<len(text)<=maximum,'statistics')
        loads(text.encode('ascii'),maximum);selected[name]=text
    return selected


def journal_original_statistics(store,statistics):
    """Keep every original ASCII character in bounded, reconstructable parts."""
    require(type(statistics) is dict and set(statistics) in (set(STATISTICS[:3]),set(STATISTICS)),'statistics')
    for index,name in enumerate(sorted(statistics)):
        text=statistics[name];maximum=16384 if name.endswith('DIAGNOSTICS') else 8192
        require(type(text) is str and text.isascii() and 0<len(text)<=maximum,'statistics')
        original_pin=pin(text.encode('ascii'));part_count=(len(text)+4095)//4096
        for part_index in range(part_count):
            store.journal(f'statistic-{index:02d}-part-{part_index:03d}',
                {'name':name,'part_index':part_index,'part_count':part_count,
                 'original_string_pin':original_pin,'text':text[part_index*4096:(part_index+1)*4096]})


def operate(submission, candidate_id, *, engine, validator, api, secret, store, deadline, state,
            sleep=time.sleep):
    """One fresh A1, Completed identity, exact readback and semantic result."""
    global STAGE
    candidates = [row for row in submission.candidates if row.candidate_id == candidate_id]
    require(len(candidates) == 1, 'plan')
    allowed_keys = {item.object_store_key for item in submission.uploads}
    def request(endpoint, payload):
        budget(deadline)
        require(type(endpoint) is str and (endpoint in engine.PAYLOAD_KEYS or endpoint=='backtests/read')
            and endpoint not in ('projects/collaboration/lock/release','object/get','object/set')
            and type(payload) is dict, 'request')
        operation=state.get('operation')
        expected_source=f'Codex R348 {candidate_id} A1'
        keys={'projectId','backtestId'} if endpoint=='backtests/read' else engine.PAYLOAD_KEYS[endpoint]
        require(set(payload)==keys or (endpoint=='projects/read' and not payload)
            or (endpoint=='files/read' and state.get('result_mode') and set(payload)=={'projectId'})
            or (endpoint=='files/read' and operation is not None and not operation._lock
                and set(payload)=={'projectId'}),'request')
        if 'projectId' in payload:
            allowed={engine.REFERENCE_PROJECT}
            if operation is not None and operation.project_id is not None:allowed.add(operation.project_id)
            require(type(payload['projectId']) is int and payload['projectId'] in allowed
                and payload['projectId']!=A4_PROJECT,'request')
        if endpoint=='projects/read' and not payload:
            require(operation is not None and operation.project_id is None
                and not state.get('project_listing_spent',False),'request')
            state['project_listing_spent']=True
        if endpoint=='projects/create':
            require(operation is not None and operation.project_id is None
                and payload=={'name':operation.name,'language':'Py','organizationId':operation.organization}
                and not state.get('allocation_dispatch_spent',False),'request')
            state['allocation_dispatch_spent']=True
        if 'codeSourceId' in payload:
            require(payload['codeSourceId']==expected_source,'request')
        if endpoint.startswith('files/') and endpoint!='files/read':
            require(operation is not None and operation._lock and payload['projectId']==operation.project_id,'request')
            if endpoint=='files/delete':require(payload['name']=='research.ipynb','request')
            else:require(payload['name'] in operation.sources and payload['content']==operation.sources[payload['name']],'request')
        if endpoint=='projects/collaboration/lock/acquire':
            require(operation is not None and payload['projectId']==operation.project_id
                and not state.get('lock_dispatch_spent',False),'request')
            state['lock_dispatch_spent']=True
        if endpoint in ('compile/create','backtests/create'):
            require(operation is not None and type(operation.project_id) is int
                and operation.project_id!=engine.REFERENCE_PROJECT
                and payload['projectId']==operation.project_id,'request')
        if endpoint=='backtests/list':require(payload['includeStatistics'] is False,'request')
        if endpoint=='backtests/read':
            require(operation is not None and state.get('result_mode') and state.get('result_access_verified')
                and state.get('result_source_verified') and operation.terminal_receipt is not None
                and operation.terminal_receipt.get('status')=='Completed.'
                and payload=={'projectId':operation.project_id,'backtestId':operation.launch_receipt['backtest_id']}
                and not state.get('result_read_dispatched',False),'request')
            state['result_read_dispatched']=True
        if endpoint=='object/properties':
            require(set(payload)=={'organizationId','key'} and payload['key'] in allowed_keys
                and type(payload['organizationId']) is str
                and re.fullmatch('[0-9a-f]{32}',payload['organizationId'])
                and pin(payload['organizationId'].encode('ascii'))['sha256']==engine.ORGANIZATION_SHA256,'request')
        state['last_request'] = {'endpoint': endpoint, 'payload_sha256': pin(canonical(payload))['sha256']}
        api.deadline = min(deadline, time.monotonic() + 89)
        return api._exchange(endpoint, payload)
    STAGE = 'access'
    for index in range(engine.CAPACITY_POLLS):
        if index:
            require(budget(deadline)>engine.CAPACITY_INTERVAL,'deadline');sleep(engine.CAPACITY_INTERVAL)
        access = engine.access_capacity(request,user_id=int(secret['QC_USER_ID']),journal=store.journal)
        if access['public']['capacity']['available_count']>0: break
    else: raise Refused('capacity')
    uploads=tuple((loads(item.descriptor_json,MAX_OUTPUT),item.payload) for item in submission.uploads)
    operation = engine.LegacySixQc(candidates[0].cell_record(), uploads, organization_id=access['organization_id'],
        user_id=int(secret['QC_USER_ID']), attempt=1,
        request=request, journal=store.journal)
    state['operation'] = operation
    STAGE = 'source_compile'
    begin = operation.begin_once()
    require(begin['state'] == 'compiling', 'capacity')
    for index in range(engine.COMPILE_POLLS):
        if index:
            require(budget(deadline) > engine.COMPILE_INTERVAL, 'deadline'); sleep(engine.COMPILE_INTERVAL)
        compile_state = operation.poll_compile(index)
        require(compile_state['state'] != 'BuildError', 'compile')
        if compile_state['state'] == 'BuildSuccess':
            break
    else:
        raise Refused('compile')
    STAGE = 'launch'
    for index in range(engine.CAPACITY_POLLS):
        if index:
            require(budget(deadline) > engine.CAPACITY_INTERVAL, 'deadline'); sleep(engine.CAPACITY_INTERVAL)
        # Engine owns fresh current project/source/input-properties/compile/
        # capacity validation. A missing/mismatched object refuses; no upload.
        launched = operation.launch_once()
        if launched['state'] == 'launched':
            break
    else:
        raise Refused('capacity')
    require(type(launched.get('launch_receipt')) is dict, 'launch')
    status=launched.get('launch_status')
    require(status in ('In Queue...','In Progress...','Completed.','Runtime Error'),'launch')
    STAGE='status';state['observed_status']=status
    if status in ('In Queue...','In Progress...'):
        for index in range(STATUS_CHECKS):
            require(budget(deadline)>engine.STATUS_INTERVAL,'deadline');sleep(engine.STATUS_INTERVAL)
            observed=operation.poll_status(index);status=observed.get('status')
            require(status in ('In Queue...','In Progress...','Completed.','Runtime Error'),'launch')
            state['observed_status']=status
            if status in ('Completed.','Runtime Error'): break
        else: raise Refused('not_completed')
    require(status!='Runtime Error','runtime_error');require(status=='Completed.','not_completed')
    STAGE='result_access';state['result_mode']=True
    project=request('projects/read',{'projectId':operation.project_id})
    dedicated=request('projects/collaboration/read',{'projectId':operation.project_id})
    current_access=result_access(project,dedicated,operation,int(secret['QC_USER_ID']))
    state['result_access_verified']=True
    source=result_sources(request('files/read',{'projectId':operation.project_id}),operation)
    state['result_source_verified']=True
    completed=operation._history('result-completed',own=True)
    require(completed['status']=='Completed.','not_completed')
    STAGE='statistics'
    packet=request('backtests/read',{'projectId':operation.project_id,
                                    'backtestId':operation.launch_receipt['backtest_id']})
    state['result_read_response_received']=True
    statistics=selected_statistics(packet,operation)
    state['selected_result_read']=True
    journal_original_statistics(store,statistics)
    state['statistics_pin']=pin(canonical(statistics))
    STAGE='semantic'
    validation=validator.validate_statistics(statistics,candidate_record=candidates[0].cell_record(),
        evaluation_sessions=submission.evaluation_sessions)
    require(type(validation) is dict and len(canonical(validation))<=16384,'semantic')
    state['semantic_validation']=validation
    require(validation.get('accepted') is True and validation.get('run_valid') is True,'semantic')
    STAGE='accepted'
    return {'candidate_id': candidate_id, 'attempt': 1,'project_id':operation.project_id,
        'launch_receipt': launched['launch_receipt'],
        'terminal_receipt': operation.terminal_receipt, 'access': access['public'],
        'observed_status':status,'terminal_identity_observed':True,
        'statistics':statistics,'statistics_pin':state['statistics_pin'],'semantic_validation':validation,
        'result_access':current_access,'source':source,'result_read':True,'selected_result_read':True,
        'source_identity':loads(submission.source_identity_json,MAX_OUTPUT),
        'input_metadata_admission': {'observations': loads(canonical(operation.metadata_admissions),MAX_OUTPUT),
            'qualification':'current_key_size_MD5_metadata_not_remote_SHA256_attestation_runtime_reader_rechecks_all_SHA256'},
        'application_dispatch_count': store.application_dispatch_count,
        'look_accounting':dict(store.look_accounting(),accepted_result_cell_delta=1),
        'last_access_observation': access_observation(engine, operation),
        'result_semantics': 'current_vintage_qualified_research_accepted_only_after_full_semantic_check', **FLAGS}


def run(args):
    global STAGE, LAST_FAILURE
    deadline = time.monotonic() + SECONDS
    bound = preflight(args, deadline)
    with Sources(args, deadline) as sources:
        with Store(control(args.candidate), sources.security, candidate=args.candidate) as store:
            store.write('claim.json', {'binding': bound, 'profile': profile_record(args.candidate),
                'consumed_at': datetime.now(timezone.utc).isoformat()})
            store.write('events.jsonl', b'')
            api = None
            state = {'api': None, 'operation': None, 'last_request': None, 'last_object_observation': None,
                'store': store}
            try:
                STAGE = 'data'
                with sources.consumer.FreshAllPlainSubmission(fact_bytes=sources.preparation_fact_bytes,
                        deadline=min(deadline, time.monotonic() + 179)) as held:
                    submission = held.value
                # Only detached immutable buffers survive the DATA guard's
                # normal return; no secret/contact existed during that read.
                STAGE='a4_prerequisite'
                state['a4_prerequisite']=validate_a4_prerequisite(sources.accepted_A4_fact,submission,sources.validator)
                STAGE = 'credentials'
                secret = sources.transport.credentials({key: os.environ.get(key) for key in CREDENTIALS})
                api = sources.transport.API(secret, store, min(deadline, time.monotonic() + 89))
                state['api'] = api
                result = operate(submission, args.candidate, engine=sources.engine, validator=sources.validator,
                    api=api, secret=secret, store=store, deadline=deadline, state=state)
                result['last_api_diagnostic'] = api_diagnostic(sources.transport, api)
                # Preserve safe allocation/contact facts even if a subsequent
                # final source/control verification or descriptor close fails
                # outside this inner handler, before stdout can be emitted.
                LAST_FAILURE = failure_evidence(state, sources, Refused('unknown'))
                api.close(); api = None
                sources.verify()
                report = {'schema': SCHEMA + '-result', 'binding': bound, 'attempt_consumed': True, 'result': result}
                report_pin = store.write('report.json', report)
                store.verify()
            except BaseException as error:
                LAST_FAILURE = failure_evidence(state, sources, error)
                if api is not None:
                    api.close()
                reason = finite(error, sources)
                store.write('failure.json', {'schema': SCHEMA + '-failure', 'binding': bound,
                    'stage': STAGE, 'failure_code': reason, 'attempt_consumed': True,
                    'application_dispatch_count': store.application_dispatch_count,
                    'evidence': LAST_FAILURE, **FLAGS})
                raise Refused(reason) from None
    STAGE = 'complete'
    LAST_FAILURE = None
    return {**report, 'report_pin': report_pin}


def finite(error, sources=None):
    if isinstance(error, (Deadline, TimeoutError, subprocess.TimeoutExpired)):
        return 'deadline'
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    if len(args) == 1 and type(args[0]) is str and args[0] in FINITE:
        return args[0]
    if sources is not None:
        for module, code in ((sources.consumer, 'data'), (sources.engine, 'operation'),
                (sources.transport, 'request'), (sources.validator,'semantic')):
            if type(error) is module.Refused:
                return code
    return 'unknown'


def validate_original_stdout(raw,*,actual_exit,expected_binding):
    """Pure original-output/actual-exit check; never reread an operational leaf."""
    require(type(expected_binding) is dict and set(expected_binding)=={'schema','candidate_id','attempt',
        'expected_head','caller_sha256','plan_sha256','profile_sha256'}
        and expected_binding.get('schema')==SCHEMA and expected_binding.get('candidate_id') in CANDIDATES
        and type(expected_binding.get('attempt')) is int and expected_binding['attempt']==1
        and type(expected_binding.get('expected_head')) is str
        and re.fullmatch('[0-9a-f]{40}',expected_binding['expected_head'])
        and all(type(expected_binding.get(key)) is str and re.fullmatch('[0-9a-f]{64}',expected_binding[key])
            for key in ('caller_sha256','plan_sha256','profile_sha256')),'output')
    require(type(actual_exit) is int and actual_exit==0 and type(raw) is bytes
        and 0<len(raw)<=MAX_OUTPUT and raw.endswith(b'\n'),'output')
    value=loads(raw[:-1],MAX_OUTPUT)
    require(type(value) is dict and set(value)=={'schema','binding','attempt_consumed','result','report_pin'}
        and value['schema']==SCHEMA+'-result' and canonical(value['binding'])==canonical(expected_binding)
        and value['attempt_consumed'] is True
        and value['report_pin']==pin(canonical({key:item for key,item in value.items() if key!='report_pin'})),
        'output')
    result=value['result'];require(type(result) is dict,'output')
    receipt=result.get('launch_receipt');terminal=result.get('terminal_receipt')
    require(result.get('candidate_id') in CANDIDATES and result['candidate_id']==expected_binding.get('candidate_id')
        and type(result.get('attempt')) is int and result['attempt']==1
        and type(result.get('project_id')) is int and 0<result['project_id']<2**63
        and result['project_id']!=A4_PROJECT and result.get('observed_status')=='Completed.'
        and result.get('terminal_identity_observed') is True and result.get('result_read') is True
        and result.get('selected_result_read') is True and type(receipt) is dict
        and receipt.get('candidate_id')==result['candidate_id'] and type(receipt.get('attempt')) is int
        and receipt['attempt']==1 and type(receipt.get('project_id')) is int
        and receipt['project_id']==result['project_id'] and type(receipt.get('backtest_id')) is str
        and re.fullmatch('[A-Za-z0-9][A-Za-z0-9._:-]{0,127}',receipt['backtest_id'])
        and type(receipt.get('compile_id')) is str
        and re.fullmatch('[A-Za-z0-9][A-Za-z0-9._:-]{0,127}',receipt['compile_id'])
        and receipt.get('backtest_name')==f"ARV2 LEGACY SIX {result['candidate_id']} OCT2026 A1"
        and type(terminal) is dict and terminal=={**receipt,'status':'Completed.'}
        and type(result.get('statistics')) is dict and set(result['statistics'])==set(STATISTICS)
        and result.get('statistics_pin')==pin(canonical(result['statistics']))
        and type(result.get('semantic_validation')) is dict
        and result['semantic_validation'].get('accepted') is True
        and result['semantic_validation'].get('run_valid') is True
        and all(result.get(key) is False for key in FLAGS),'output')
    accounting=result.get('look_accounting')
    require(type(accounting) is dict and all(type(accounting.get(key)) is int and accounting[key]==wanted
        for key,wanted in (('shared_look_delta',1),('development_look_delta',1),
            ('infrastructure_look_delta',0),('accepted_result_cell_delta',1))) ,'output')
    return value


def access_observation(engine, operation):
    """Only the engine's closed type/count projection, never remote values."""
    validator = getattr(engine, 'validate_metadata_observation', None)
    if not callable(validator):
        return None
    try:
        result = validator(getattr(operation, 'last_access_observation', None))
        if type(result) is dict and len(canonical(result)) <= 4096:
            return result
    except Exception:
        pass
    return None


def api_diagnostic(transport, api):
    """Validate finite/lossy diagnostic only; never serialize raw API state."""
    validator = getattr(transport, 'validate_diagnostic', None)
    if not callable(validator):
        return None
    try:
        result = validator(getattr(api, 'last_diagnostic', None))
        if type(result) is dict and len(canonical(result)) <= 24 * 1024:
            return result
    except Exception:
        pass
    return None


def failure_evidence(state, sources, error):
    """Closed finite projection; never serialize opaque API/engine instances."""
    allowed = set(sources.engine.PAYLOAD_KEYS) | {'object/properties','backtests/read'}
    def endpoint(value):
        return value if type(value) is str and value in allowed else None
    def digest(value):
        return value if type(value) is str and re.fullmatch('[0-9a-f]{64}', value) else None
    def identity(value):
        return value if type(value) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', value) else None
    def request(value):
        if type(value) is not dict:
            return None
        result = {'endpoint': endpoint(value.get('endpoint')), 'payload_sha256': digest(value.get('payload_sha256'))}
        marker, stage = value.get('marker'), value.get('stage')
        if type(marker) is str and re.fullmatch('[a-z0-9-]{1,100}', marker): result['marker'] = marker
        if stage in ('intent_or_request_unaccepted', 'response_unaccepted'): result['stage'] = stage
        if digest(value.get('response_sha256')) is not None:
            result['response_sha256'] = value['response_sha256']
        count = value.get('response_bytes')
        if type(count) is int and 0 < count <= 2 * 1024 * 1024: result['response_bytes'] = count
        return result
    module_error = {'module': 'unknown', 'code': 'unknown'}
    for name, module in (('caller', sys.modules.get(__name__)), ('consumer', sources.consumer),
            ('engine', sources.engine), ('transport', sources.transport),('validator',sources.validator)):
        if module is not None and type(error) is getattr(module, 'Refused', None):
            args = BaseException.args.__get__(error)
            if len(args) == 1 and type(args[0]) is str and args[0] in module.FINITE:
                module_error = {'module': name, 'code': args[0]}
    api, operation = state.get('api'), state.get('operation')
    statuses, responses = [], []
    if api is not None:
        for row in getattr(api, 'statuses', ()):
            if type(row) is dict and endpoint(row.get('endpoint')) is not None \
                    and type(row.get('http_status')) is int and 100 <= row['http_status'] <= 599:
                statuses.append({'endpoint': row['endpoint'], 'http_status': row['http_status']})
        for row in getattr(api, 'responses', ()):
            if type(row) is dict and endpoint(row.get('endpoint')) is not None \
                    and valid_pin({key: row.get(key) for key in ('byte_count', 'sha256')}, 2 * 1024 * 1024):
                responses.append({key: row[key] for key in ('endpoint', 'byte_count', 'sha256')})
    last_status = getattr(api, 'last_http_status', None)
    project_id = getattr(operation, 'project_id', None)
    receipt = getattr(operation, 'launch_receipt', None)
    allocated = {'project_id': project_id if type(project_id) is int and 0 < project_id < 2**63 else None,
        'compile_id': identity(getattr(operation, 'compile_id', None)),
        'backtest_id': identity(receipt.get('backtest_id')) if type(receipt) is dict else None}
    # Object observations were constructed solely from exact booleans, bounded
    # integers, finite type names and an expected-key hash before refusal.
    observation = state.get('last_object_observation')
    object_keys = {'ordinal', 'key_sha256', 'metadata_present', 'key_exact', 'size_type',
        'observed_size', 'expected_size', 'md5_lower_hex', 'md5_hex', 'md5_matches'}
    if (type(observation) is not dict or set(observation) != object_keys
            or type(observation.get('ordinal')) is not int or not 0 <= observation['ordinal'] < 6
            or digest(observation.get('key_sha256')) is None
            or not all(type(observation.get(key)) is bool for key in ('metadata_present', 'key_exact', 'md5_lower_hex', 'md5_hex', 'md5_matches'))
            or observation.get('size_type') not in ('int', 'bool', 'string', 'null', 'other')
            or not (observation.get('observed_size') is None or type(observation['observed_size']) is int and 0 <= observation['observed_size'] < 2**63)
            or type(observation.get('expected_size')) is not int or not 0 < observation['expected_size'] <= 32 * 1024 * 1024):
        observation = None
    result = {'module_error': module_error,
        'last_http_status': last_status if type(last_status) is int and 100 <= last_status <= 599 else None,
        'http_status_count': len(statuses), 'http_status_vector_pin': pin(canonical(statuses)),
        'last_http_statuses': statuses[-12:], 'response_pin_count': len(responses),
        'response_pin_vector_pin': pin(canonical(responses)), 'last_response_pins': responses[-6:],
        'last_request': request(state.get('last_request')),
        'engine_last_request': request(getattr(operation, 'last_request', None)),
        'engine_last_failure': request(getattr(operation, 'last_failure', None)),
        'last_access_observation': access_observation(sources.engine, operation),
        'last_api_diagnostic': api_diagnostic(sources.transport, api),
        'allocated_identities': allocated, 'object_observation': observation,
        'observed_status':state.get('observed_status') if state.get('observed_status') in
            ('In Queue...','In Progress...','Completed.','Runtime Error') else None,
        'result_read_dispatched':state.get('result_read_dispatched') is True,
        'result_read_response_received':state.get('result_read_response_received') is True,
        'selected_result_read':state.get('selected_result_read') is True,
        'statistics_pin':state.get('statistics_pin') if valid_pin(state.get('statistics_pin'),MAX_OUTPUT) else None,
        'look_accounting': state['store'].look_accounting() if state.get('store') is not None else None}
    require(len(canonical(result)) <= 48 * 1024, 'output')
    return result


class Parser(argparse.ArgumentParser):
    def error(self, message): raise Refused('arguments')


def main():
    parser = Parser(add_help=False)
    parser.add_argument('mode', choices=('profile', 'run'))
    parser.add_argument('candidate', choices=CANDIDATES)
    for key in ('expected-head', 'caller-sha256', 'plan-sha256'):
        parser.add_argument('--' + key)
    args = parser.parse_args()
    if args.mode == 'profile':
        require(all(getattr(args, key) is None for key in ('expected_head', 'caller_sha256', 'plan_sha256')), 'arguments')
        return profile_record(args.candidate)
    def expired(*_): raise Deadline()
    signal.signal(signal.SIGALRM, expired); signal.setitimer(signal.ITIMER_REAL, SECONDS)
    return run(args)


if __name__ == '__main__':
    try:
        raw = canonical(main()) + b'\n'
        require(len(raw) <= MAX_OUTPUT, 'output'); sys.stdout.buffer.write(raw)
    except BaseException as error:
        sys.stdout.buffer.write(canonical({'schema': SCHEMA + '-failure', 'stage': STAGE,
            'claim_state': CLAIM, 'failure_code': finite(error), 'evidence': LAST_FAILURE, **FLAGS}) + b'\n')
        raise SystemExit(2)
