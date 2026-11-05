"""One future offline recording of exactly one selected Safari R329 statistic.

This reads bounded supplied metadata, not Safari/QC or any old DATA/control.
The caller freezes actual UI build/job/source linkage and raw selected-byte pin;
this recorder does not authenticate those external facts. Original transport
bytes are retained, including the one explicitly selected trailing-space mode.
"""
import argparse
from contextlib import contextmanager
import hashlib
from importlib.machinery import PathFinder
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import time

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
SOURCE = ROOT / 'scripts/record_arv2_r329_native_coverage_result.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_available_history_native_coverage_result/R329-20261028-C'
PYTHON = '/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
BRANCH = 'codex/strategy-analyst-revisions-v2'
STAGE_PATH = 'scripts/prepare_arv2_r329_native_coverage_source.py'
STAGE_SHA256 = '652a46b6b0db83f50cf042e1b374b9beed3192d897e5886557e48cf25a75193e'
PARSER_PATH = 'scripts/arv2_r329_native_coverage_result.py'
PARSER_SHA256 = 'daaac5778c4f6c2a98996c6a061c5051b07207939f83df110a3fe74898c923ea'
SCHEMA = 'arv2-r329-one-shot-selected-UI-result-record-v1'
RUN_SCHEMA = SCHEMA + '-external-run-binding'
OUTER_SCHEMA = SCHEMA + '-bounded-process'
VALIDATION_SCHEMA = SCHEMA + '-offline-output-validation'
PROJECT_ID = 38522505
STATISTIC = 'ARV2_W5_NATIVE_COVERAGE'
BUILD_KIND = 'Safari_combined_compile_launch_IDE_token_not_REST_compileId'
ENGINE_VERSION = '2.5.0.0.18207'
READBACK_METHODS = ('Safari_download11', 'named_API_read11')
FRAMINGS = ('canonical', 'exactly_one_trailing_space')
UI_TERMINALS = {'Completed': 'Completed.', 'Runtime Error': 'Runtime Error.',
    'Build Error': 'Build Error.', 'Stopped': 'Stopped.', 'Cancelled': 'Cancelled.', 'Invalid': 'Invalid.'}
MAX_RAW_BYTES, MAX_RUN_BYTES, MAX_OUTPUT_BYTES = 8003, 8192, 32768
SECONDS, PARENT_SECONDS, REAP_SECONDS = 30, 60, 5
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
    'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags')
FALSE_FLAGS = {'QC_contact': False, 'Safari_access': False, 'provider_contact': False,
    'credential_access': False, 'old_control_or_private_DATA_read': False,
    'UI_selection_origin_authenticated_by_recorder': False,
    'source_build_job_linkage_authenticated_by_recorder': False,
    'REST_compile_id_observed': False, 'strategy_result_accepted': False,
    'price_input_admitted': False, 'source_or_processing_rights_granted': False,
    'point_in_time_proven': False, 'formal_forward_ready': False, 'paper_or_live_ready': False,
    'continuous_integrity_proven': False, 'retry_granted': False}
FINITE = frozenset(('arguments', 'host', 'environment', 'binding', 'run', 'source_pin', 'source_changed',
    'profile', 'raw_bound', 'raw_pin', 'framing', 'summary', 'deadline', 'claim_spent', 'output',
    'output_bound', 'output_changed', 'output_write', 'security', 'git_state', 'os_error', 'unknown'))
stage = result_parser = None
BOOTSTRAP_METADATA = {}


class Refused(ValueError):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    if len(args) == 1 and type(args[0]) is str and args[0] in FINITE:
        return args[0]
    if stage is not None and type(error) is stage.Refused:
        code = stage.finite(error)
        return code if code in FINITE else 'unknown'
    if result_parser is not None and type(error) is result_parser.Refused:
        return 'summary'
    return 'os_error' if isinstance(error, OSError) else 'unknown'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
        allow_nan=False).encode('ascii')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(raw):
    return {'byte_count': len(raw), 'sha256': sha(raw)}


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _keys(value, keys):
    return type(value) is dict and all(type(key) is str for key in value) and set(value) == keys


def _exact(left, right):
    if type(left) is not type(right): return False
    if type(right) is dict:
        return _keys(left, set(right)) and all(_exact(left[key], right[key]) for key in right)
    if type(right) is list:
        return len(left) == len(right) and all(_exact(a, b) for a, b in zip(left, right))
    return type(right) in (str, int, bool, type(None)) and left == right


def _loads(raw, bound, code):
    require(type(raw) is bytes and 0 < len(raw) <= bound, code)
    def pairs(items):
        value = {}
        for key, child in items:
            require(key not in value, code)
            value[key] = child
        return value
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused(code)))
        require(canonical(value) == raw, code)
        return value
    except Refused:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise Refused(code) from None


def _meta(info):
    return tuple(getattr(info, key, None) for key in FIELDS)


def _public_source(relative, expected):
    """Stdlib pre-import nofollow endpoint check; native security follows."""
    path = ROOT / relative
    opened, rows = [], []
    try:
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW); opened.append(fd)
        for part in path.parts[1:-1]:
            before = _meta(os.stat(part, dir_fd=fd, follow_symlinks=False))
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd); opened.append(child)
            require(stat.S_ISDIR(before[2]) and _meta(os.fstat(child)) == before, 'source_changed')
            rows.append((fd, part, child, before)); fd = child
        before = _meta(os.stat(path.name, dir_fd=fd, follow_symlinks=False))
        leaf = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd); opened.append(leaf)
        require(stat.S_ISREG(before[2]) and before[3] == os.getuid() and before[5] == 1
            and 0 < before[6] <= 131072 and _meta(os.fstat(leaf)) == before, 'source_pin')
        raw = os.pread(leaf, 131073, 0)
        require(len(raw) == before[6] and sha(raw) == expected and _meta(os.fstat(leaf)) == before
            and _meta(os.stat(path.name, dir_fd=fd, follow_symlinks=False)) == before, 'source_pin')
        for parent, name, child, metadata in rows:
            require(_meta(os.fstat(child)) == metadata
                and _meta(os.stat(name, dir_fd=parent, follow_symlinks=False)) == metadata, 'source_changed')
        return before
    finally:
        for fd in reversed(opened): os.close(fd)


def _dependencies():
    global stage, result_parser, BOOTSTRAP_METADATA
    if stage is not None:
        return
    if __name__ == '__main__':
        for name, module in tuple(sys.modules.items()):
            path = getattr(module, '__file__', None)
            require(name == '__main__' or type(path) is not str
                or not (Path(path) == ROOT or ROOT in Path(path).parents), 'source_pin')
    observed = {path: _public_source(path, expected) for path, expected in
        ((STAGE_PATH, STAGE_SHA256), (PARSER_PATH, PARSER_SHA256))}
    sys.path[:] = [str(ROOT), *(item for item in sys.path if item and Path(item).is_absolute()
        and Path(item) != ROOT and ROOT not in Path(item).parents)]
    package = PathFinder.find_spec('scripts', sys.path)
    require(package is not None and package.origin is None
        and tuple(package.submodule_search_locations) == (str(ROOT / 'scripts'),), 'source_pin')
    if 'scripts' in sys.modules:
        require(tuple(sys.modules['scripts'].__path__) == (str(ROOT / 'scripts'),), 'source_pin')
    for path in (STAGE_PATH, PARSER_PATH):
        name = path[:-3].replace('/', '.')
        spec = PathFinder.find_spec(name, [str(ROOT / 'scripts')])
        require(spec is not None and spec.origin == str(ROOT / path), 'source_pin')
        if name in sys.modules:
            require(__name__ != '__main__' and getattr(sys.modules[name], '__file__', None) == str(ROOT / path), 'source_pin')
    from scripts import prepare_arv2_r329_native_coverage_source as loaded_stage
    from scripts import arv2_r329_native_coverage_result as loaded_parser
    stage, result_parser = loaded_stage, loaded_parser
    BOOTSTRAP_METADATA = {**stage.BOOTSTRAP_METADATA, **observed}


def selected_plan():
    _dependencies()
    return {**stage.public_plan(), STAGE_PATH: STAGE_SHA256, PARSER_PATH: PARSER_SHA256}


def _pin(value, maximum):
    require(_keys(value, {'byte_count', 'sha256'}) and type(value['byte_count']) is int
        and 0 < value['byte_count'] <= maximum and _hash(value['sha256']), 'run')


def validate_run(value):
    require(_keys(value, {'schema', 'expected_run', 'UI_build_kind', 'engine_version', 'raw_terminal', 'source_readback_method',
        'statistic_name', 'framing', 'raw_statistic_pin'}) and type(value['schema']) is str and value['schema'] == RUN_SCHEMA
        and type(value['UI_build_kind']) is str and value['UI_build_kind'] == BUILD_KIND
        and type(value['engine_version']) is str and value['engine_version'] == ENGINE_VERSION
        and type(value['source_readback_method']) is str and value['source_readback_method'] in READBACK_METHODS
        and type(value['raw_terminal']) is str and value['raw_terminal'] in UI_TERMINALS
        and type(value['statistic_name']) is str and value['statistic_name'] == STATISTIC and type(value['framing']) is str
        and value['framing'] in FRAMINGS, 'run')
    run = value['expected_run']
    require(_keys(run, {'project_id', 'compile_id', 'backtest_id', 'name', 'source_projection_pin',
        'source_profile_pin', 'source_readback_pin', 'coverage_profile_sha256'})
        and type(run['project_id']) is int and run['project_id'] == PROJECT_ID
        and type(run['compile_id']) is str and re.fullmatch('[0-9a-f]{6}-[0-9a-f]{6}', run['compile_id'])
        and type(run['backtest_id']) is str and re.fullmatch('[0-9a-f]{32}', run['backtest_id'])
        and type(run['name']) is str and 0 < len(run['name']) <= 200 and run['name'].isascii()
        and all(32 <= ord(char) < 127 for char in run['name']) and _hash(run['coverage_profile_sha256']), 'run')
    for key in ('source_projection_pin', 'source_profile_pin', 'source_readback_pin'):
        _pin(run[key], 65536)
    _pin(value['raw_statistic_pin'], 8002 if value['framing'] == 'canonical' else MAX_RAW_BYTES)
    require(len(canonical(value)) <= MAX_RUN_BYTES, 'run')
    return json.loads(canonical(value))


def run_record(args):
    require(type(args.run_json) is str and args.run_json.isascii() and _hash(args.run_sha256), 'arguments')
    raw = args.run_json.encode('ascii')
    require(sha(raw) == args.run_sha256, 'binding')
    return validate_run(_loads(raw, MAX_RUN_BYTES, 'run'))


def native_profile():
    value = '(version 1)(allow default)(deny network*)'
    for path in ('/Users/sheltonchen/Library/Keychains', '/Library/Keychains'):
        value += f'(deny file-read* file-write* (subpath "{path}"))'
    value += '(deny process-exec (literal "/usr/bin/security"))(deny file-read-data (regex "[.]pyc$"))'
    value += '(deny file-write* (require-all ' + ''.join((f'(require-not (subpath "{CONTROL}"))',
        f'(require-not (literal "{CONTROL.parent}"))', f'(require-not (subpath "{ROOT / ".pytest_cache"}"))',
        '(require-not (literal "/dev/null"))')) + '))'
    ancestors = (ROOT / 'artifacts', ROOT / 'artifacts/analyst_revisions_v2', CONTROL.parent)
    value += f'(deny file-read* (require-all (subpath "{ROOT / "artifacts"}")' + f'(require-not (subpath "{CONTROL}"))' \
        + ''.join(f'(require-not (literal "{path}"))' for path in ancestors) + '))'
    return value


def profile_record(run):
    checked = validate_run(run)
    _dependencies()
    result_parser._binding(checked['expected_run'], result_parser.coverage.profile_record(PROJECT_ID))
    return {'schema': SCHEMA, 'root': str(ROOT), 'source': str(SOURCE), 'control': str(CONTROL),
        'branch': BRANCH, 'python': PYTHON, 'run_binding': checked, 'selected_public_source_pins': selected_plan(),
        'pure_result_policy_sha256': sha(canonical(result_parser.profile_record())),
        'native_policy_sha256': sha(native_profile().encode('ascii')), 'child_seconds': SECONDS,
        'parent_seconds': PARENT_SECONDS, 'reap_seconds': REAP_SECONDS, 'maximum_raw_bytes': MAX_RAW_BYTES,
        'maximum_public_output_bytes': MAX_OUTPUT_BYTES, 'output_files': ['claim.json', 'selected.raw', 'report.json', 'failure.json'],
        'parent_deadline_scope': 'before_fixed_child_Popen_includes_child_bootstrap_import_preflight_recording',
        'parent_exclusions': 'parent_argument_source_validation_before_Popen_uninterruptible_IO_host_suspension',
        'parent_execution': 'ordinary_clean_env_i_process_launches_own_native_denied_child_nested_outer_sandbox_unsupported',
        'validator_execution': 'direct_native_all_artifact_network_denied_no_child_no_claim_clean_HEAD_public_source_guard',
        'validator_deadline_scope': '30s_after_public_bootstrap_imports_external_startup_deadline_required',
        'kill_scope': 'only_own_child_not_arbitrary_process_or_descendant_tree',
        'UI_terminal_translation': dict(UI_TERMINALS), 'framing': 'explicit_canonical_or_one_trailing_ASCII_SPACE_only',
        'original_bytes_retained_no_generic_trim_or_trial': True,
        'actual_recorder_exit_zero_authenticates_metadata_record_not_QC_strategy_success': True,
        'external_provenance': 'owner_run_freeze_UI_selection_build_job_and_source_readback_not_proven_here',
        'source_integrity': 'selected_current_endpoints_not_whole_interpreter_or_continuous_same_user_integrity', **FALSE_FLAGS}


def binding(args):
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}', args.expected_head)
        and _hash(args.caller_sha256) and _hash(args.profile_sha256), 'arguments')
    run = run_record(args)
    return {'schema': SCHEMA, 'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256,
        'profile_sha256': args.profile_sha256, 'run_sha256': args.run_sha256, 'project_id': PROJECT_ID,
        'backtest_id': run['expected_run']['backtest_id']}


def _environment():
    allowed = {'PATH', 'TMPDIR', 'PYTHONPYCACHEPREFIX', 'PYTHONDONTWRITEBYTECODE',
        'PYTEST_DISABLE_PLUGIN_AUTOLOAD', 'LC_ALL', 'LANG', '__CF_USER_TEXT_ENCODING'}
    require(set(os.environ) <= allowed and os.environ.get('PYTHONDONTWRITEBYTECODE') == '1'
        and os.environ.get('PYTEST_DISABLE_PLUGIN_AUTOLOAD') == '1' and os.environ.get('LC_ALL') == 'C', 'environment')
    for key in ('TMPDIR', 'PYTHONPYCACHEPREFIX'):
        path = Path(os.environ.get(key, ''))
        require(path.is_absolute() and ROOT / '.pytest_cache' in path.parents and path.resolve() == path, 'environment')


def remaining(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline), 'deadline')
    left = deadline - time.monotonic()
    require(0 < left <= SECONDS, 'deadline')
    return left


@contextmanager
def alarm(deadline):
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'deadline')
    old = signal.getsignal(signal.SIGALRM)
    def expired(_a, _b): raise Refused('deadline')
    signal.signal(signal.SIGALRM, expired); signal.setitimer(signal.ITIMER_REAL, remaining(deadline))
    try: yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, old)


def preflight(args, deadline):
    binding(args); _environment()
    require(sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and sys.executable == PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT
        and Path(__file__).absolute() == SOURCE, 'host')
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)), (['branch', '--show-current'], BRANCH),
        (['rev-parse', 'HEAD'], args.expected_head), (['status', '--porcelain'], '')):
        require(stage._git(command, deadline).decode('ascii').strip() == expected, 'git_state')
    require(sha(stage._git(['cat-file', 'blob', args.expected_head + ':' + SOURCE.relative_to(ROOT).as_posix()], deadline))
        == args.caller_sha256 and sha(canonical(profile_record(run_record(args)))) == args.profile_sha256, 'profile')
    remaining(deadline)


def normalize(raw, run):
    run = validate_run(run)
    require(type(raw) is bytes and 0 < len(raw) <= MAX_RAW_BYTES, 'raw_bound')
    require(pin(raw) == run['raw_statistic_pin'], 'raw_pin')
    if run['framing'] == 'canonical':
        body = raw
    else:
        require(raw.endswith(b'} ') and not raw.startswith(b' '), 'framing')
        body = raw[:-1]
    require(0 < len(body) <= 8002, 'raw_bound')
    return body


def interpret(raw, run):
    _dependencies(); checked = validate_run(run); body = normalize(raw, checked)
    expected = checked['expected_run']
    actual = {key: expected[key] for key in result_parser.RUN_KEYS}
    actual['terminal'] = UI_TERMINALS[checked['raw_terminal']]
    parsed = result_parser.validate_selected(STATISTIC, body, actual_run=actual, expected_run=expected,
        expected_profile=result_parser.coverage.profile_record(PROJECT_ID))
    return {'raw_statistic_pin': pin(raw), 'body_pin': pin(body), 'framing': checked['framing'],
        'raw_UI_terminal': checked['raw_terminal'], 'normalized_terminal': actual['terminal'],
        'UI_build_kind': checked['UI_build_kind'], 'engine_version': checked['engine_version'],
        'source_readback_method': checked['source_readback_method'],
        'literal_UI_status_translation_not_API_observation': True, 'selected': parsed}


class Store:
    def __init__(self):
        self.guard = stage.DirectoryGuard(CONTROL, create=True, control=CONTROL)
        self.fd, self.files, self.failed = self.guard.fd, {}, False

    def verify(self):
        stage.Store.verify(self)

    def write(self, name, raw, deadline):
        require(name in ('claim.json', 'selected.raw', 'report.json', 'failure.json') and name not in self.files
            and len(self.files) < 4 and type(raw) is bytes and 0 < len(raw) <= (MAX_RAW_BYTES if name == 'selected.raw' else MAX_OUTPUT_BYTES), 'output_bound')
        remaining(deadline); self.verify()
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            initial = stage.metadata(fd)
            row = {'fd': fd, 'parent': self.fd, 'name': name, 'metadata': initial, 'security': stage._security(fd)}
            require(stage._regular(initial, private=True) and initial[6] == 0
                and initial == stage.named(self.fd, name), 'output_changed')
            self.guard.own_created(self.guard.rows[-1], row, directory=False)
            self.files[name] = row; os.fsync(self.fd)
            view = memoryview(raw)
            while view:
                remaining(deadline); count = os.write(fd, view[:8192]); require(type(count) is int and count > 0, 'output_write')
                view = view[count:]
            os.fsync(fd); fresh = stage.metadata(fd)
            require(fresh[:6] == initial[:6] and fresh[9] == initial[9] and fresh[6] == len(raw)
                and stage._security(fd) == row['security'], 'output_changed')
            row['metadata'] = fresh
            require(os.pread(fd, len(raw) + 1, 0) == raw, 'output_write')
            self.verify(); return pin(raw)
        except BaseException:
            if name not in self.files: os.close(fd)
            raise

    def __enter__(self): return self

    def __exit__(self, kind, *rest):
        return stage.Store.__exit__(self, kind, *rest)


def failure(args, error, *, consumed=False):
    return {'binding': binding(args), 'failure_code': finite(error), 'claim_consumed': consumed,
        'allocation_unknown': not consumed, **FALSE_FLAGS}


def produce(args, raw, deadline):
    _dependencies(); preflight(args, deadline); run = run_record(args)
    plan = {**selected_plan(), SOURCE.relative_to(ROOT).as_posix(): args.caller_sha256}
    with stage.PublicSources(plan, deadline) as sources:
        require(all(sources.files[key]['metadata'] == value for key, value in BOOTSTRAP_METADATA.items()), 'source_changed')
        with Store() as store:
            store.write('claim.json', canonical(binding(args)), deadline)
            try:
                require(type(raw) is bytes and 0 < len(raw) <= MAX_RAW_BYTES, 'raw_bound')
                store.write('selected.raw', raw, deadline)
                interpreted = interpret(raw, run)
                sources.verify(); preflight(args, deadline); store.verify()
                result = {'schema': SCHEMA, 'run_binding': run, 'interpretation': interpreted,
                    'selected_public_sources_sha256': sha(canonical(plan)),
                    'source_endpoint_metadata_sha256': sha(canonical({key: list(row['metadata']) for key, row in sources.files.items()})),
                    'input_endpoint_metadata_sha256': sha(canonical(list(store.files['selected.raw']['metadata']))),
                    'original_input_and_source_descriptors_postchecked': True, **FALSE_FLAGS}
                report = canonical({'binding': binding(args), 'result': result})
                report_pin = store.write('report.json', report, deadline)
                sources.verify(); store.verify()
                outcome = {'result': result, 'report_pin': report_pin}
            except BaseException as error:
                store.failed = True; value = failure(args, error, consumed=True)
                try: store.write('failure.json', canonical(value), deadline)
                except BaseException: pass
                outcome = {'failure': value}
    return {'binding': binding(args), 'outcome': outcome}


def validate_child(raw, actual_exit, args):
    _dependencies()
    require(type(actual_exit) is int and actual_exit in (0, 2) and type(raw) is bytes
        and 0 < len(raw) <= MAX_OUTPUT_BYTES and raw.endswith(b'\n') and raw.count(b'\n') == 1, 'output')
    value = _loads(raw[:-1], MAX_OUTPUT_BYTES, 'output')
    if _keys(value, {'failure_code', 'attempt_reusable'}):
        require(actual_exit == 2 and type(value['failure_code']) is str
            and value['failure_code'] in FINITE and value['attempt_reusable'] is False, 'output')
        return value
    if _keys(value, {'binding', 'outcome'}):
        require(_exact(value['binding'], binding(args)) and type(value['outcome']) is dict, 'output')
        outcome = value['outcome']
        if _keys(outcome, {'result', 'report_pin'}):
            require(actual_exit == 0, 'output'); result = outcome['result']; run = run_record(args)
            keys = {'schema', 'run_binding', 'interpretation', 'selected_public_sources_sha256',
                'source_endpoint_metadata_sha256', 'input_endpoint_metadata_sha256',
                'original_input_and_source_descriptors_postchecked', *FALSE_FLAGS}
            require(_keys(result, keys) and result['schema'] == SCHEMA and _exact(result['run_binding'], run)
                and result['original_input_and_source_descriptors_postchecked'] is True
                and all(result[key] is False for key in FALSE_FLAGS), 'output')
            observed = result['interpretation']
            require(type(observed) is dict and type(observed.get('selected')) is dict
                and type(observed['selected'].get('summary')) is dict, 'output')
            body = canonical(observed['selected']['summary'])
            original = body + b' ' if run['framing'] == 'exactly_one_trailing_space' else body
            require(_exact(observed, interpret(original, run)), 'output')
            plan = {**selected_plan(), SOURCE.relative_to(ROOT).as_posix(): args.caller_sha256}
            require(result['selected_public_sources_sha256'] == sha(canonical(plan))
                and all(_hash(result[key]) for key in ('source_endpoint_metadata_sha256', 'input_endpoint_metadata_sha256'))
                and _exact(outcome['report_pin'], pin(canonical({'binding': binding(args), 'result': result}))), 'output')
            return value
        require(_keys(outcome, {'failure'}), 'output'); value = outcome['failure']
    require(actual_exit == 2 and _keys(value, {'binding', 'failure_code', 'claim_consumed', 'allocation_unknown', *FALSE_FLAGS})
        and _exact(value['binding'], binding(args)) and type(value['failure_code']) is str and value['failure_code'] in FINITE
        and type(value['claim_consumed']) is bool and value['allocation_unknown'] is (not value['claim_consumed'])
        and all(value[key] is False for key in FALSE_FLAGS), 'output')
    return value


def _read_input(stream, maximum=MAX_RAW_BYTES):
    require(type(maximum) is int and maximum in (MAX_RAW_BYTES, MAX_OUTPUT_BYTES + 2048), 'raw_bound')
    raw = stream.read(maximum + 1)
    require(type(raw) is bytes and 0 < len(raw) <= maximum, 'raw_bound')
    return raw


def collect(argv, env, raw, *, seconds=PARENT_SECONDS, maximum=MAX_OUTPUT_BYTES):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_RAW_BYTES and type(seconds) in (int, float)
        and 0 < seconds <= PARENT_SECONDS and type(maximum) is int and 0 < maximum <= MAX_OUTPUT_BYTES, 'binding')
    deadline = time.monotonic() + seconds; child = None; output = bytearray(); status = 'unknown'; actual_exit = None
    sent = 0; stderr_seen = False
    try:
        child = subprocess.Popen(argv, cwd=str(ROOT), env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
        with selectors.DefaultSelector() as selector:
            for pipe, event, label in ((child.stdin, selectors.EVENT_WRITE, 'stdin'),
                (child.stdout, selectors.EVENT_READ, 'stdout'), (child.stderr, selectors.EVENT_READ, 'stderr')):
                os.set_blocking(pipe.fileno(), False); selector.register(pipe, event, label)
            while selector.get_map() or child.poll() is None:
                left = deadline - time.monotonic()
                if left <= 0: status = 'deadline'; break
                for key, _ in selector.select(min(0.25, left)):
                    if key.data == 'stdin':
                        count = os.write(key.fileobj.fileno(), raw[sent:sent + 4096]); require(count > 0, 'output_write'); sent += count
                        if sent == len(raw): selector.unregister(key.fileobj); key.fileobj.close()
                        continue
                    chunk = os.read(key.fileobj.fileno(), min(4096, maximum + 1))
                    if not chunk: selector.unregister(key.fileobj)
                    elif key.data == 'stderr': stderr_seen = True; status = 'stderr'; break
                    elif len(output) + len(chunk) > maximum: status = 'stdout_bound'; break
                    else: output.extend(chunk)
                if status != 'unknown': break
            if status == 'unknown':
                actual_exit = child.wait(timeout=max(0.01, deadline - time.monotonic())); status = 'returned'
    except BaseException: status = 'collector_failure'
    finally:
        if child is not None:
            if child.poll() is None: child.kill()
            try: actual_exit = child.wait(timeout=REAP_SECONDS)
            except BaseException: actual_exit = None; status = 'reap_ambiguous'
            for pipe in (child.stdin, child.stdout, child.stderr):
                if pipe is not None and not pipe.closed: pipe.close()
    envelope = None
    if status == 'returned' and type(actual_exit) is int and actual_exit in (0, 2) and not stderr_seen:
        try:
            require(output.endswith(b'\n') and output.count(b'\n') == 1, 'output')
            envelope = _loads(bytes(output[:-1]), MAX_OUTPUT_BYTES, 'output')
            require(_keys(envelope, {'binding', 'outcome'}) or _keys(envelope, {'failure_code', 'attempt_reusable'})
                or _keys(envelope, {'binding', 'failure_code', 'claim_consumed', 'allocation_unknown', *FALSE_FLAGS}), 'output')
        except BaseException: status = 'malformed_output'; envelope = None
    return {'schema': OUTER_SCHEMA, 'collector_status': status, 'actual_child_exit': actual_exit,
        'stdin_byte_count': sent, 'stdout_pin': pin(bytes(output)), 'stderr_seen': stderr_seen,
        'child_envelope': envelope, 'child_output_accepted': False, 'attempt_reusable': False}


def validate_output(raw, actual_parent_exit, args):
    require(type(actual_parent_exit) is int and actual_parent_exit == 0 and type(raw) is bytes
        and 0 < len(raw) <= MAX_OUTPUT_BYTES + 2048 and raw.endswith(b'\n') and raw.count(b'\n') == 1, 'output')
    value = _loads(raw[:-1], MAX_OUTPUT_BYTES + 2048, 'output')
    keys = {'schema', 'collector_status', 'actual_child_exit', 'stdin_byte_count', 'stdout_pin',
        'stderr_seen', 'child_envelope', 'child_output_accepted', 'attempt_reusable'}
    require(_keys(value, keys) and value['schema'] == OUTER_SCHEMA and value['collector_status'] == 'returned'
        and value['stderr_seen'] is False and value['child_output_accepted'] is False and value['attempt_reusable'] is False
        and type(value['stdin_byte_count']) is int and value['stdin_byte_count'] == run_record(args)['raw_statistic_pin']['byte_count'], 'output')
    child = canonical(value['child_envelope']) + b'\n'
    require(_exact(value['stdout_pin'], pin(child)), 'output')
    return validate_child(child, value['actual_child_exit'], args)


def validate_supplied_output(args, raw, deadline):
    """Authenticate supplied metadata only; never reopen a recorded control."""
    preflight(args, deadline)
    plan = {**selected_plan(), SOURCE.relative_to(ROOT).as_posix(): args.caller_sha256}
    with stage.PublicSources(plan, deadline) as sources:
        require(all(sources.files[key]['metadata'] == value for key, value in BOOTSTRAP_METADATA.items()), 'source_changed')
        checked = validate_output(raw, args.actual_parent_exit, args)
        outcome = checked.get('outcome', {})
        recorded = 'result' in outcome
        if recorded:
            interpretation = outcome['result']['interpretation']
            selected = interpretation['selected']
            status, complete = selected['classification'], selected['diagnostic_complete']
            report_pin, body_pin, failure_code = outcome['report_pin'], interpretation['body_pin'], None
        else:
            failed = outcome.get('failure', checked)
            status, complete = 'recorder_failed', False
            report_pin, body_pin, failure_code = None, None, failed['failure_code']
        result = {'schema': VALIDATION_SCHEMA, 'binding': binding(args), 'supplied_output_pin': pin(raw),
            'actual_parent_exit_externally_observed': args.actual_parent_exit,
            'actual_child_exit_from_validated_parent': 0 if recorded else 2,
            'supplied_envelope_validated': True, 'output_authenticated': 'binding' in checked,
            'recording_success': recorded, 'diagnostic_status': status,
            'diagnostic_complete': complete, 'report_pin': report_pin, 'body_pin': body_pin,
            'raw_statistic_pin': run_record(args)['raw_statistic_pin'], 'failure_code': failure_code,
            'persisted_output_reopened': False, 'control_claimed': False, **FALSE_FLAGS}
        sources.verify(); preflight(args, deadline)
    return result


class _Parser(argparse.ArgumentParser):
    def error(self, message): raise Refused('arguments')


def _arguments(argv):
    parser = _Parser(add_help=False)
    for key in ('expected-head', 'caller-sha256', 'profile-sha256', 'run-json', 'run-sha256'):
        parser.add_argument('--' + key, required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--worker', action='store_true')
    modes.add_argument('--validate-output', action='store_true')
    parser.add_argument('--actual-parent-exit', type=int)
    args = parser.parse_args(argv)
    require(args.validate_output == (args.actual_parent_exit is not None), 'arguments')
    return args


def main(argv=None):
    try:
        args = _arguments(argv); binding(args); _environment()
        if args.validate_output:
            _dependencies(); deadline = time.monotonic() + SECONDS
            with alarm(deadline):
                raw = _read_input(sys.stdin.buffer, MAX_OUTPUT_BYTES + 2048)
                value = validate_supplied_output(args, raw, deadline)
                sys.stdout.buffer.write(canonical(value) + b'\n')
                return 0
        if args.worker:
            _dependencies(); deadline = time.monotonic() + SECONDS
            with alarm(deadline):
                raw = _read_input(sys.stdin.buffer)
                try: value = produce(args, raw, deadline)
                except BaseException as error: value = failure(args, error)
                code = 2 if 'failure_code' in value or 'failure' in value.get('outcome', {}) else 0
                encoded = canonical(value) + b'\n'; validate_child(encoded, code, args)
                sys.stdout.buffer.write(encoded); return code
        require(Path.cwd() == ROOT and sys.platform == 'darwin' and sys.version_info[:2] == (3, 13)
            and sys.executable == PYTHON, 'host')
        _public_source(SOURCE.relative_to(ROOT).as_posix(), args.caller_sha256)
        # Bound the parent's stdin acquisition separately; child60s starts at Popen.
        with alarm(time.monotonic() + SECONDS): raw = _read_input(sys.stdin.buffer)
        run = run_record(args); require(pin(raw) == run['raw_statistic_pin'], 'raw_pin')
        child_args = ['/usr/bin/sandbox-exec', '-p', native_profile(), PYTHON, '-B', str(SOURCE),
            '--worker', '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256,
            '--profile-sha256', args.profile_sha256, '--run-json', args.run_json, '--run-sha256', args.run_sha256]
        value = collect(child_args, dict(os.environ), raw)
        sys.stdout.buffer.write(canonical(value) + b'\n')
        return 0 if value['collector_status'] == 'returned' and type(value['actual_child_exit']) is int and value['actual_child_exit'] in (0, 2) else 2
    except BaseException as error:
        sys.stdout.buffer.write(canonical({'failure_code': finite(error), 'attempt_reusable': False}) + b'\n')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
