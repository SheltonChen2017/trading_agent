"""One A19 hashed-reference witness and native private binding join.

All prior claims remain spent. Fresh native D2/A11 input admission is projected
into a separately versioned failure-only RAW-reference diagnostic. Only the
legacy runtime and main change. One compile/job and one selected result/error
read are bounded; whole response objects and ignored outcome sections are never
canonicalized, journaled or represented as authenticated by the selector.
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
import stat
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_arv2_r298_plain_readiness as admitted
from scripts import run_arv2_r298_plain_backtest as prior
from scripts import arv2_r298_launch_admission as admission
from scripts import arv2_newrule_quote_execution_projection as quote
from scripts import arv2_newrule_raw_reference_diagnostic_projection as raw_projection
from scripts import arv2_newrule_reference_identity_projection as projection
from scripts import arv2_r298_reference_identity_join as identity_join
from scripts import arv2_newrule_reference_identity_response as response_selector
from scripts import observe_arv2_r298_plain_readiness as capture_support
from scripts import arv2_newrule_execution_environment as environment
from scripts import arv2_r298_mia_access_representation as access
from scripts import observe_arv2_r298_post_mia_access_a17 as access_context
from scripts import arv2_r298_readiness_recovery_remote as recovery
from research.analyst_revisions_v2_qc import newrule_comparison_submission as submission

SOURCE = ROOT / 'scripts/run_arv2_r298_reference_identity_diagnostic.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_reference_identity/R323-20261025-J'
PYTHON = admitted.frozen.PYTHON
SCHEMA = 'arv2-r298-reference-identity-diagnostic-a19-v1'
DEADLINE_SECONDS = 15120
MAX_OUTPUT = 128 * 1024
MAX_OBSERVER_OUTPUT = MAX_OUTPUT + 4096
MAX_PACKET = 640 * 1024
MAX_FILES = 1024
MAX_DISPATCHES = 420
NEW_PINS = {
    'scripts/run_arv2_r298_plain_backtest.py': '56b286ddff9ec934c9309e58753618264b089069b8de95436c900c9658a9e654',
    'scripts/arv2_newrule_quote_diagnostic_projection.py': '227a00f8ecec730c9ddf2524b510eda24205e797192c388542137812b2d5b177',
    'scripts/arv2_newrule_quote_execution_projection.py': 'ebc6d921c5dbaa5e9bc83379ab45c167780fb87db8441dbd9d618b3efcb1715f',
    'scripts/arv2_r298_quote_diagnostic_remote.py': 'bed3653baeeeb5c1338127832ccd51af4587d957d733e18cdde33a11ef27c6e0',
    'scripts/run_arv2_r298_quote_diagnostic.py': '770ce5b92fcd46e862a40a763b492d6561b55a82b4e244242a900eda71509257',
    'scripts/arv2_r298_quote_diagnostic_a14_remote.py': '58cbc1b1f2fec140a5d4cd19660e6f2f61a94ab728a3da20ce011b7687f478f8',
    'scripts/run_arv2_r298_quote_diagnostic_a14.py': '283468d50fb22fa68143266a3074c83eac3658d8bb934094d1c8ad1f72dcc65c',
    'scripts/arv2_r298_quote_execution_remote.py': '5777c6cefd93a738817f2ef523ccbadee6763a9183cc6c14a96c43140f216893',
    'scripts/run_arv2_r298_quote_execution.py': 'bc3e8039a9f86b39a82b26079f2acfda6738acb935cd2ca909249b0233a13152',
    'scripts/arv2_r298_quote_execution_a16_remote.py': 'e538b19725d0e61f0a5da9b2bc1e80de56e34f99645ac789adcc7872288d13a4',
    'scripts/run_arv2_r298_quote_execution_a16.py': 'd614744f07021c40e5ce0de6385232c96dc8aaabcd2f51671ad9c8daf4d6e6b4',
    'scripts/arv2_newrule_raw_reference_diagnostic_projection.py': 'ef92bdb198586243166f7cf76276f6ed339fda90f52792eeab70da56894fcae6',
    'scripts/arv2_newrule_backtest_response.py': '24f77bfc8764137ae387ab01d546a9a6a13fe5799ba6697068e0cd6e2d314a08',
    'scripts/arv2_r298_raw_reference_diagnostic_remote.py': '2ad47581084c0bc9f42673dccc94c11563cd5122c0c5a1b717c0a2c7d57d5470',
    'scripts/run_arv2_r298_raw_reference_diagnostic.py': '1f2f88de601312c1e5ee16381a64fdd091ada2ea7ab2a0709a991bbc6b6d71ff',
    'scripts/observe_arv2_r298_post_mia_access_a17.py': '21c1f99db2b0ab3029ad3a1957eaf9cb122c76465ae22445c2ad2c6f6621580c',
    'scripts/arv2_r298_mia_access_representation.py': '18cfacf19757fd6359747f1c78b93e662daf7492ac658f48673dd4d628d56a04',
    'scripts/arv2_r298_raw_reference_diagnostic_a18_remote.py': '8553ac2b4819cb13948e1c4358bb4cf1dfd26c46427eeaced0931643f04adc30',
    'scripts/run_arv2_r298_raw_reference_diagnostic_a18.py': '8633694f7c705a83b197e310f916c59c9083956e9afa034824c42668d6c4be40',
    'scripts/arv2_newrule_reference_identity_projection.py': '97e2c5bc33a3eb820a9b2c28b2b254fd90ce6ff511f36d92fbfbb8c37dd1beba',
    'scripts/arv2_newrule_reference_identity_response.py': '9703fa8ea178811a6b5f5eca86cff87dc8daa33d939179006fd04905cae182ec',
    'scripts/arv2_r298_reference_identity_join.py': '742895938a69e2ab40c64a222542162d281077769fa0142c9bfeb929b73afd71',
    'scripts/arv2_r298_reference_identity_remote.py': '1e437c6d82eefcef9660b4e15099bf0e26e88b325d971c1bc2c1b97d9c08ef3a',
}
PROJECTION_SHA256 = '83255174a37e1aa69ec8436c2b77561c9988007e526d0ad2ced630826e10589f'
PROFILE_SHA256 = '86f12ed5705d2413575855e61d6b92ec2a02856b2a8cbe07dcc048b32ed7809d'
SOURCE_MANIFEST_SHA256 = '7a852d8e1d575843340cc87d4e1495133cf3a045702094c89b852b25360294a7'
PATCHER_SHA256 = NEW_PINS['scripts/arv2_newrule_reference_identity_projection.py']

FALSE_FLAGS = {'point_in_time_proven': False, 'formal_identity_admitted': False,
               'formal_forward_ready': False, 'paper_or_live_ready': False}
FINITE = frozenset(('deadline', 'host', 'arguments', 'git_state', 'source_pin',
    'claim_spent', 'control_changed', 'control_name', 'control_bound', 'control_write',
    'diagnostic_binding', 'admission_packet', 'worker_scope', 'worker_credentials',
    'admission_failed', 'request_scope', 'compile_budget', 'status_budget', 'admission_changed',
    'output', 'output_bound', 'parent_failed', 'validator_failed', 'refused',
    'projection_refused', 'execution_environment_refused', 'qc_client_refused',
    'qc_not_configured', 'response_scope', 'os_error', 'unknown_exception',
    'join_scope', 'join_binding', 'join_unavailable', 'join_packet'))
canonical, parse, sha, metadata = admitted.canonical, admitted.parse, admitted.sha, admitted.metadata


class Refused(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise Refused(code)


def remaining(deadline):
    value = deadline - time.monotonic()
    require(value > 0, 'deadline')
    return value


def finite(error):
    if type(error) is identity_join.Refused:
        return 'join_' + identity_join.finite(error)
    if type(error) is response_selector.Refused:
        return 'response_' + response_selector.finite(error)
    if type(error) is access.AccessRefused:
        return 'access_' + access.finite_error(error)['code']
    if type(error) is submission.NewruleSubmissionError:
        return 'submission_' + submission.finite_failure(error)
    if type(error) is recovery.RecoveryError:
        return 'recovery_' + recovery.finite_error(error)['helper_code']
    if type(error) is Refused:
        values = BaseException.args.__get__(error)
        if len(values) == 1 and type(values[0]) is str and values[0] in FINITE:
            return values[0]
        return 'refused'
    for name in ('arv2_r298_reference_identity_remote', 'arv2_r298_launch_admission',
                 'arv2_newrule_reference_identity_projection', 'arv2_newrule_raw_reference_diagnostic_projection',
                 'arv2_newrule_quote_execution_projection'):
        module = sys.modules.get('scripts.' + name)
        if module is not None and type(error) is vars(module).get('Refused'):
            method = vars(module).get('finite')
            if callable(method):
                code = method(error)
                return 'launch_' + code if type(code) is str and code in module.FINITE | {'unknown'} else 'refused'
            values = BaseException.args.__get__(error)
            if len(values) == 1 and type(values[0]) is str and values[0] in vars(module).get('FINITE', ()):
                return 'launch_' + values[0]
            return 'projection_refused' if name in ('arv2_newrule_reference_identity_projection',
                'arv2_newrule_raw_reference_diagnostic_projection',
                'arv2_newrule_quote_execution_projection') else 'refused'
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
    return {**access_context.pins(), **NEW_PINS}


def _finite_code(value):
    codes = FINITE | {'access_' + code for code in access.FINITE_CODES | {'unknown'}}
    codes |= {'launch_' + code for code in _remote().FINITE | admission.FINITE | projection.FINITE | quote.FINITE | {'unknown'}}
    codes |= {'response_' + code for code in response_selector.FINITE | {'unknown'}}
    codes |= {'submission_' + code for code in submission.FINITE_REFUSAL_CODES | {'operation_refused'}}
    codes |= {'recovery_' + code for code in recovery.FINITE_CODES | {'unknown'}}
    codes |= {'join_' + code for code in identity_join.FINITE | {'unknown'}}
    return type(value) is str and value in codes


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': admitted.frozen.BRANCH,
        'python': str(PYTHON), 'control': str(CONTROL), 'source_pins': pins(),
        'project_id': 38364439, 'attempt': 19, 'max_launches': 1,
        'max_dispatches': MAX_DISPATCHES, 'deadline_seconds': DEADLINE_SECONDS,
        'max_output': MAX_OUTPUT, 'max_observer_output': MAX_OBSERVER_OUTPUT,
        'max_public_packet': MAX_PACKET,
        'capacity_polls': 3, 'capacity_interval': 60,
        'status_polls': 240, 'status_interval': 60,
        'result_reads': 1, 'old_attempts_spent': True,
        'runtime_error_detail_reads': 1, 'success_and_error_share_read_budget': True,
        'comparison_specification_sha256': 'ee8df6e992c0763c3448bd0f601f0cb789f8abe9bdc86497274163805a424a13',
        'readiness_exit': 0, 'readiness_head': '9d4725e78ce4baaa39fc080de54aba25ce69b56f',
        'readiness_report_sha256': 'a0ac64a13299e9fa2a37816a15394448bbec8236c9b6636bc379b00dece375e7',
        'readiness_report_bytes': 10684,
        'worker_credentials': False, 'source_uploads': 2, 'new_compiles': 1,
        'purpose': 'date_bound_missing_reference_identity_witness_and_private_catalog_join',
        'failure_codes': list(projection.FAILURE_CODES),
        'failure_context_schema': projection.CONTEXT_SCHEMA,
        'context_is_diagnostic_not_cause': True,
        'projection_sha256': PROJECTION_SHA256, 'candidate_profile_sha256': PROFILE_SHA256,
        'source_manifest_sha256': SOURCE_MANIFEST_SHA256,
        'compile_polls': 120, 'compile_interval': 1,
        'a12_actual_exit': 2, 'a12_control_read': False,
        'a13_spent': True, 'a13_control_read': False,
        'a14_spent': True, 'a14_actual_exit': 2,
        'a14_report_bytes': 3256,
        'a14_report_sha256': 'c8d14b163bc214f78ed912271035deac88bbb9e6bd1cd7583d7d502151ffd5fe',
        'a14_report_documentary_only': True, 'a14_control_read': False,
        'a15_spent': True, 'a15_actual_exit': 2, 'a15_control_read': False,
        'a15_parent_stdout_bytes': 729,
        'a15_parent_stdout_sha256': '690b239757c3665c388088719c2d212f1c1ffa9dc158194972b421c433a02cab',
        'a15_failure_code': 'access_idle', 'a15_failure_stage': 'prepare',
        'a15_application_dispatch_count': 2, 'a15_returned_response_count': 2,
        'a15_new_source_writes': 0, 'a15_new_compiles': 0, 'a15_jobs': 0,
        'a15_evidence_documentary_only': True,
        'ui_remediation_scope': 'stop_only_owned_R298_code_environment',
        'ui_remediation_observation': 'owned_environment_removed_other_lane_retained',
        'ui_remediation_not_historical_cause_or_access_authority': True,
        'quote_policy_changed_from_a15': False,
        'a16_spent': True, 'a16_actual_exit': 2, 'a16_control_read': False,
        'a16_parent_stdout_bytes': 3275,
        'a16_parent_stdout_sha256': 'f1611fb828bc0904a1551c056a80e48eba3d6a51f342c412bc01badf3092349d',
        'a16_failure_code': 'launch_response_bound', 'a16_failure_stage': 'failure_detail',
        'a16_failure_evidence_documentary_only': True,
        'a17_spent': True, 'a17_actual_exit': 2, 'a17_control_read': False,
        'a17_parent_stdout_bytes': 755,
        'a17_parent_stdout_sha256': 'fbcb3c200ee9acac2bd4549e714ab60b5c181f0750c0495a65231cb66ea7710c',
        'a17_failure_code': 'access_general_collaborators', 'a17_failure_stage': 'prepare',
        'a17_application_dispatch_count': 2, 'a17_returned_response_count': 2,
        'a17_source_writes': 0, 'a17_compiles': 0, 'a17_jobs': 0,
        'historical_a17_cause_authenticated': False,
        'a18_spent': True, 'a18_actual_exit': 2, 'a18_control_read': False,
        'a18_report_bytes': 3852,
        'a18_report_sha256': '071515e58fd03478bf0b6ec21695c6767ba6e3bc09f7f91fa840981eb08552d2',
        'a18_backtest_id': '78ba7a236450cdeffea5efe07d087637',
        'a18_compile_id': 'ed8233767e663d42a2ea3c9d5590d8f5-e3908e134c5314de5875830686db3b0b',
        'a18_evidence_documentary_only': True, 'a18_historical_cause_authenticated': False,
        'h_observation_spent': True, 'h_observation_actual_exit': 0,
        'h_observation_report_bytes': 5271,
        'h_observation_report_sha256': '156d7f98e8c68819ef507d15f6d0390729f82afb3bb00f3054de61458a0d7171',
        'h_observation_head': '283ec2c3ce0bdc04499dbf476bc42d2b1bb76442',
        'h_observation_documentary_only': True, 'h_control_read': False,
        'h_observation_access_policy_accepted': False,
        'access_representation_schema': access.SCHEMA,
        'access_representation_profile_sha256': sha(canonical(access.profile_record())),
        'new_access_verifier_direct_import': True,
        'current_access_required_before_mutation': True,
        'ui_control_reclaim_documentary_only': True,
        'mia_synthetic_identity_proven': False, 'privacy_proven': False,
        'exclusive_lease_proven': False,
        'raw_reference_ui_category_known': True, 'raw_reference_ui_counts_known': False,
        'missing_identity_domain': 'arv2-missing-reference-identity-v1',
        'identity_witness_date_bound': True, 'extra_RAW_history_probe': False,
        'diagnostic_join_workers': 1, 'diagnostic_join_worker_index': 2,
        'diagnostic_join_worker_deadline_seconds': 120,
        'diagnostic_join_requires_complete_own_runtime_error_witness': True,
        'diagnostic_join_credential_and_network_access': False,
        'diagnostic_join_profile_sha256': sha(canonical(identity_join.profile_record())),
        'diagnostic_join_changes_primary_terminal_or_actual_exit': False,
        'diagnostic_join_provider_routing_authorized': False,
        'diagnostic_only': True, 'family_result_cell_eligible': False,
        'diagnostic_policy_record_sha256': sha(canonical(projection.policy_record())),
        'execution_policy_changed_from_a16': False,
        'execution_policy': quote.POLICY,
        'execution_policy_record_sha256': sha(canonical(quote.policy_record())),
        'execution_price_basis': 'buy_ask_sell_bid_current_non_fill_forward_quote',
        'fee_and_fill_price_basis_match_required': True,
        'accepted_risk_only': True, 'family_comparable': False,
        'common_new_runtime_family_reconstruction_required': True,
        'response_projection': response_selector.SCHEMA,
        'response_projection_profile_sha256': sha(canonical(response_selector.profile_record())),
        'response_projection_before_canonicalization': True,
        'whole_response_authenticated': False, 'wire_bound_bytes': 16 * 1024 * 1024,
        'access_observation_actual_exit': 0,
        'access_observation_report_bytes': 3612,
        'access_observation_report_sha256': '625111ca3458ec173c0c9f1dfcbab70222a27bec23bd1b56342fc23488830a6f',
        'access_observation_head': '6eda8f4098e22dc2a6afa2e73cc2e4d682890212',
        'access_observation_policy': 'passed', 'access_observation_documentary_only': True,
        'access_observation_control_read': False,
        'fresh_access_before_mutation': True, 'strict_finite_foreign_errors': True,
        'foreign_error_categories': ['access', 'submission', 'recovery', 'qc_client', 'environment'],
        'request_response_accounting': True, 'diagnostic_not_family_cell': True,
        'historical_a13_cause_known': False,
        'same_user_sandbox': False, 'continuous_integrity_proven': False,
        'uninterruptible_io_or_suspension_bounded': False, **FALSE_FLAGS}


def binding(args):
    return {'schema': SCHEMA, 'expected_head': args.expected_head,
        'caller_sha256': args.caller_sha256, 'profile_sha256': sha(canonical(profile_record()))}


def preflight(args, deadline):
    require(not admitted.v5._under_test() and Path(__file__).absolute() == SOURCE
        and sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT, 'host')
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}', args.expected_head)
        and type(args.caller_sha256) is str and re.fullmatch('[0-9a-f]{64}', args.caller_sha256), 'arguments')
    environment._require_environment()
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)),
        (['branch', '--show-current'], admitted.frozen.BRANCH),
        (['rev-parse', 'HEAD'], args.expected_head), (['status', '--porcelain'], '')):
        require(admitted.v5._git(command, deadline).decode('ascii').strip() == expected, 'git_state')
    for name, pin in pins().items():
        require(pin != '0' * 64 and sha((ROOT / name).read_bytes()) == pin, 'source_pin')
    require(sha(SOURCE.read_bytes()) == args.caller_sha256, 'source_pin')
    blob = admitted.v5._git(['cat-file', 'blob', args.expected_head + ':' + SOURCE.relative_to(ROOT).as_posix()],
                           deadline, 128 * 1024)
    require(sha(blob) == args.caller_sha256, 'source_pin')
    remaining(deadline)


class Store:
    """Exclusive immutable records, held directory and checked named metadata.

    Leaf descriptors close after verification to avoid an unbounded FD census
    over four hours of status observations. This is endpoint authentication.
    """
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
                os.close(fd)
                fd = nxt
                self.chain.append((os.fstat(fd).st_dev, os.fstat(fd).st_ino))
            self.fd = fd
            self.verify()
        except BaseException:
            os.close(fd)
            raise

    def __enter__(self): return self
    def __exit__(self, *_): os.close(self.fd)

    def verify(self):
        other, chain = admitted._storage_module()._walk(CONTROL)
        try:
            held, named = os.fstat(self.fd), os.fstat(other)
            require(chain == tuple(self.chain) and metadata(held) == metadata(named)
                and held.st_uid == os.getuid() and stat.S_IMODE(held.st_mode) == 0o700
                and set(os.listdir(other)) == set(self.files) and len(self.files) <= MAX_FILES
                and held.st_nlink == 2 + len(self.files),
                'control_changed')
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
        require(0 < len(raw) <= MAX_PACKET, 'control_bound')
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            view = memoryview(raw)
            while view:
                n = os.write(fd, view)
                require(n > 0, 'control_write')
                view = view[n:]
            os.fsync(fd)
            os.fsync(self.fd)
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


capture, credential_shape = prior.capture, prior.credential_shape


def native_profile(*, artifacts=False):
    value = prior.native_profile(artifacts=artifacts)
    return value + ''.join(f'(deny file-read* (subpath "{path}"))' for path in (
        prior.CONTROL,
        ROOT / 'artifacts/analyst_revisions_v2/newrule_quote_diagnostic/R323-20261025-B',
        ROOT / 'artifacts/analyst_revisions_v2/newrule_post_mia_access/R323-20261025-C',
        ROOT / 'artifacts/analyst_revisions_v2/newrule_quote_diagnostic/R323-20261025-D',
        ROOT / 'artifacts/analyst_revisions_v2/newrule_quote_execution/R323-20261025-E',
        ROOT / 'artifacts/analyst_revisions_v2/newrule_quote_execution/R323-20261025-F',
        ROOT / 'artifacts/analyst_revisions_v2/newrule_raw_reference_diagnostic/R323-20261025-G',
        ROOT / 'artifacts/analyst_revisions_v2/newrule_post_mia_access/R323-20261025-H',
        ROOT / 'artifacts/analyst_revisions_v2/newrule_raw_reference_diagnostic/R323-20261025-I'))


def _remote():
    from scripts import arv2_r298_reference_identity_remote as remote
    require(remote.PROJECTION_SHA256 == PROJECTION_SHA256
        and remote.PROFILE_SHA256 == PROFILE_SHA256
        and remote.SOURCE_MANIFEST_SHA256 == SOURCE_MANIFEST_SHA256, 'diagnostic_binding')
    return remote


def validate_packet(packet):
    require(type(packet) is dict and set(packet) == {'admission_authenticated', 'readiness_pin',
        'storage_receipt', 'projection_record', 'source_pairs'} and packet['admission_authenticated'] is True
        and canonical(packet['readiness_pin']) == canonical(admission.readiness_pin())
        and canonical(packet['storage_receipt']) == canonical(admitted._storage_receipt())
        and type(packet['projection_record']) is str and packet['projection_record'].isascii()
        and type(packet['source_pairs']) is list and len(packet['source_pairs']) == 11, 'admission_packet')
    pairs = []
    for row in packet['source_pairs']:
        require(type(row) is list and len(row) == 2
            and all(type(item) is str and item.isascii() for item in row), 'admission_packet')
        pairs.append((row[0], row[1].encode('ascii')))
    raw = packet['projection_record'].encode('ascii')
    projection.validate_public_projection(raw, tuple(pairs),
        expected_projection_sha256=PROJECTION_SHA256, expected_profile_sha256=PROFILE_SHA256)
    require(len(canonical(packet)) <= MAX_PACKET, 'admission_packet')
    return raw, tuple(pairs)


def worker(args, deadline):
    require(type(args.control_fd) is int and args.control_fd > 2
        and type(args.worker_index) is int and args.worker_index in (0, 1), 'worker_scope')
    fd, _ = admitted._storage_module()._walk(CONTROL)
    try:
        require(metadata(os.fstat(fd)) == metadata(os.fstat(args.control_fd)), 'worker_scope')
        source = os.open('worker-' + str(args.worker_index) + '-intent.json',
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            info = os.fstat(source)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
                and 0 < info.st_size <= 65536, 'worker_scope')
            raw = os.read(source, info.st_size + 1)
            require(len(raw) == info.st_size and metadata(info) == metadata(os.fstat(source))
                == metadata(os.stat('worker-' + str(args.worker_index) + '-intent.json',
                    dir_fd=fd, follow_symlinks=False))
                and parse(raw) == {**binding(args), 'worker_index': args.worker_index}, 'worker_scope')
        finally:
            os.close(source)
    finally:
        os.close(fd)
    require(not {'QC_USER_ID', 'QC_API_TOKEN'} & set(os.environ), 'worker_credentials')
    old_packet = admission.admit(deadline)
    patched = projection.build_projection(old_packet,
        patcher_source_bytes=(ROOT / 'scripts' / projection.PATCHER_NAME).read_bytes(),
        expected_patcher_sha256=PATCHER_SHA256,
        quote_patcher_source_bytes=(ROOT / 'scripts' / quote.PATCHER_NAME).read_bytes(),
        raw_patcher_source_bytes=(ROOT / 'scripts' / raw_projection.PATCHER_NAME).read_bytes())
    packet = {'admission_authenticated': True, 'readiness_pin': old_packet['readiness_pin'],
        'storage_receipt': old_packet['storage_receipt'],
        'projection_record': patched.record_bytes.decode('ascii'),
        'source_pairs': [[name, raw.decode('ascii')] for name, raw in patched.source_pairs]}
    validate_packet(packet)
    preflight(args, deadline)
    environment.require_safe_environment()
    return packet


def run_worker(args, directory, deadline, index):
    directory.write('worker-' + str(index) + '-intent.json', {**binding(args), 'worker_index': index})
    env = {key: value for key, value in os.environ.items() if key not in ('QC_USER_ID', 'QC_API_TOKEN')}
    command = ['/usr/bin/sandbox-exec', '-p', native_profile(), str(PYTHON), '-B', str(SOURCE), 'worker',
        '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256,
        '--control-fd', str(directory.fd), '--worker-index', str(index)]
    raw, errors, observed = capture(command, env, min(120, remaining(deadline)), stdout_limit=MAX_PACKET,
        pass_fds=(directory.fd,))
    directory.write('worker-' + str(index) + '-observed.json', observed)
    require(type(observed['actual_exit']) is int and observed['actual_exit'] == 0
        and observed['bound'] is None and not errors, 'admission_failed')
    value = parse(raw)
    require(type(value) is dict and set(value) == {'binding', 'packet'}
        and value['binding'] == binding(args), 'admission_packet')
    validate_packet(value['packet'])
    return value['packet']


def _join_terminal(value):
    remote = _remote()
    remote.validate_terminal_receipt(value)
    require(value['status'] == 'Runtime Error', 'join_scope')
    return projection.validate_complete_witness(value['failure_evidence']['diagnostic_context'])


def _join_intent(args):
    """Authenticate only this claim's once-only, retained worker-two intent."""
    require(type(args.control_fd) is int and args.control_fd > 2
        and type(args.worker_index) is int and args.worker_index == 2, 'worker_scope')
    fd, _ = admitted._storage_module()._walk(CONTROL)
    try:
        require(metadata(os.fstat(fd)) == metadata(os.fstat(args.control_fd)), 'worker_scope')
        source = os.open('worker-2-intent.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            info = os.fstat(source)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
                and 0 < info.st_size <= 65536, 'worker_scope')
            raw = os.read(source, info.st_size + 1)
            require(len(raw) == info.st_size and metadata(info) == metadata(os.fstat(source))
                == metadata(os.stat('worker-2-intent.json', dir_fd=fd, follow_symlinks=False)), 'worker_scope')
            value = parse(raw)
            require(set(value) == {'binding', 'worker_index', 'terminal'}
                and value['binding'] == binding(args) and type(value['worker_index']) is int
                and value['worker_index'] == 2, 'join_binding')
            _join_terminal(value['terminal'])
            return value['terminal']
        finally:
            os.close(source)
    finally:
        os.close(fd)


def _constructed_matches(plain, projected, packet):
    """Match a genuine fresh private construct to the original public admission."""
    admission.validate_packet(packet)
    snapshot = admission._snapshot(plain, projected)
    require(projected.record_bytes.decode('ascii') == packet['projection_record']
        and [[item.project_path, item.source_bytes.decode('ascii')] for item in projected.source_files]
        == packet['source_pairs'], 'join_packet')
    return snapshot


def join_worker(args, deadline):
    """One private binding join; no credentials, transport or provider routing."""
    terminal = _join_intent(args)
    require(not {'QC_USER_ID', 'QC_API_TOKEN'} & set(os.environ), 'worker_credentials')
    context = _join_terminal(terminal)
    old_packet = admission.admit(deadline)
    plain, projected = admitted.prep.construct(deadline)
    snapshot = _constructed_matches(plain, projected, old_packet)
    receipt = identity_join.join(plain, context, old_packet)
    identity_join.validate_receipt(receipt)
    fresh_plain, fresh_projected = admitted.prep.construct(deadline)
    require(_constructed_matches(fresh_plain, fresh_projected, old_packet) == snapshot, 'admission_changed')
    require(admission.admit(deadline) == old_packet, 'admission_changed')
    preflight(args, deadline)
    environment.require_safe_environment()
    return receipt


def validate_join(value, terminal):
    require(type(value) is dict and all(type(key) is str for key in value), 'join_binding')
    if value.get('status') == 'unavailable':
        require(set(value) == {'status', 'failure_code'} and _finite_code(value['failure_code']), 'join_binding')
        return dict(value)
    require(set(value) == {'status', 'receipt'} and value.get('status') == 'joined', 'join_binding')
    context = _join_terminal(terminal)
    receipt = identity_join.validate_receipt(value['receipt'])
    expected = {'old_projection_sha256': admitted.remote.PROJECTION_SHA256,
        'old_profile_sha256': admitted.remote.PROFILE_SHA256,
        'plain_package_sha256': admitted.remote.PACKAGE_SHA256,
        'activation_manifest_sha256': admitted.remote.ACTIVATION_SHA256,
        'source_package_sha256': admitted.prep.frozen.PACKAGE_SHA256,
        'source_lineage_sha256': admitted.prep.frozen.LINEAGE_SHA256,
        'a11_report_sha256': admission.READINESS_SHA256,
        'd2_receipt_sha256': identity_join.sha(identity_join.canonical(admitted._storage_receipt())),
        'session_axis_sha256': context['session_axis_sha256'],
        'context_sha256': identity_join.context_digest(context)}
    require(all(receipt.get(key) == pin for key, pin in expected.items())
        and receipt['witness_count'] == receipt['matched_count'] == context['missing']
        and [{key: row[key] for key in ('identity_sha256', 'holding', 'kind', 'sid_date')}
             for row in receipt['matches']] == context['witnesses'], 'join_binding')
    return {'status': 'joined', 'receipt': receipt}


def run_join_worker(args, directory, deadline, terminal):
    """Dispatch at most once, retaining actual child exit before interpreting output."""
    _join_terminal(terminal)
    directory.write('worker-2-intent.json', {'binding': binding(args), 'worker_index': 2, 'terminal': terminal})
    env = {key: value for key, value in os.environ.items() if key not in ('QC_USER_ID', 'QC_API_TOKEN')}
    command = ['/usr/bin/sandbox-exec', '-p', native_profile(), str(PYTHON), '-B', str(SOURCE), 'join-worker',
        '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256,
        '--control-fd', str(directory.fd), '--worker-index', '2']
    raw, errors, observed = capture(command, env, min(120, remaining(deadline)), stdout_limit=MAX_OUTPUT,
        pass_fds=(directory.fd,))
    directory.write('worker-2-observed.json', observed)
    require(type(observed['actual_exit']) is int and observed['actual_exit'] in (0, 2)
        and observed['bound'] is None and not errors, 'join_unavailable')
    value = parse(raw)
    require(value.get('binding') == binding(args), 'join_binding')
    if observed['actual_exit'] == 2:
        require(set(value) == {'binding', 'preflight_failure'} and _finite_code(value['preflight_failure']),
            'join_binding')
        result = {'status': 'unavailable', 'failure_code': value['preflight_failure']}
    else:
        require(set(value) == {'binding', 'diagnostic_join'}, 'join_binding')
        result = validate_join({'status': 'joined', 'receipt': value['diagnostic_join']}, terminal)
    directory.write('worker-2-result.json', {**binding(args), 'diagnostic_join': result})
    return result


def _read_binding(state, payload):
    """Bind the sole result/error read before contact, without any response IO."""
    require(type(state) is dict and state.get('stage') in ('failure_detail', 'result'), 'response_scope')
    launch, terminal = state.get('launch'), state.get('terminal')
    remote = _remote()
    remote.validate_launch_receipt(launch)
    remote.validate_terminal_receipt(terminal)
    mode = 'error' if state['stage'] == 'failure_detail' else 'completed'
    require(terminal['status'] == ('Runtime Error' if mode == 'error' else 'Completed.')
        and all(terminal[key] == item for key, item in launch.items())
        and type(payload) is dict and set(payload) == {'projectId', 'backtestId'}
        and type(payload['projectId']) is int and payload['projectId'] == launch['project_id']
        and type(payload['backtestId']) is str and payload['backtestId'] == launch['backtest_id'], 'response_scope')
    return {'project_id': launch['project_id'], 'backtest_id': launch['backtest_id'],
        'backtest_name': launch['backtest_name'], 'compile_id': launch['compile_id'], 'mode': mode}


def run(args, deadline):
    credential_shape().clear()
    remote = _remote()
    with Store() as directory:
        directory.write('claim.json', {**binding(args), 'attempt': 19, 'old_attempts_spent': True})
        state = {'stage': 'initial_admission', 'dispatch_count': 0, 'response_count': 0,
                 'last_endpoint': None, 'last_response_received': False, 'compiled': None,
                 'launch': None, 'terminal': None}
        runner = None
        try:
            packet = run_worker(args, directory, deadline, 0)
            environment.require_safe_environment()
            from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
            api = old._client()
            environment.require_safe_environment()

            def request(endpoint, payload):
                remaining(deadline)
                environment.require_safe_environment()
                require(endpoint in remote.PAYLOAD_KEYS and type(payload) is dict
                    and set(payload) == remote.PAYLOAD_KEYS[endpoint]
                    and type(payload['projectId']) is int and payload['projectId'] == 38364439
                    and state['dispatch_count'] < MAX_DISPATCHES
                    and type(api) is old.QuantConnectClient and api._base_url == old.API_BASE
                    and api._transport is old.coverage._bounded_transport and api._timeout == 30, 'request_scope')
                selected_binding = _read_binding(state, payload) if endpoint == 'backtests/read' else None
                state['dispatch_count'] += 1
                state['last_endpoint'], state['last_response_received'] = endpoint, False
                response = api.request(endpoint, payload)
                state['response_count'] += 1
                state['last_response_received'] = True
                # The unchanged client already applied its 16-MiB wire bound.
                # Select BEFORE the remote hashes or canonicalizes anything;
                # ignored charts/trades/outcome subtrees must never enter it.
                return response_selector.select_response(response, **selected_binding) if selected_binding else response

            def journal(marker, event):
                remaining(deadline)
                directory.write(marker + '-' + event['event'].replace('_', '-') + '.json',
                                {**binding(args), **event})

            runner = remote.QuoteDiagnostic(packet['projection_record'].encode('ascii'),
                tuple((name, text.encode('ascii')) for name, text in packet['source_pairs']),
                request=request, journal=journal)
            state['stage'] = 'prepare'
            compiled = runner.prepare_once()
            state['compiled'] = compiled
            state['stage'] = 'compile'
            for index in range(120):
                require(remaining(deadline) > 1, 'deadline')
                time.sleep(1)
                value = runner.poll_compile(index)
                if value['state'] in ('BuildSuccess', 'BuildError'): break
            else:
                raise Refused('compile_budget')
            if value['state'] == 'BuildError':
                result = {'terminal': 'compile_error', 'application_dispatch_count': state['dispatch_count'],
                    'compiled': compiled, 'launch': None, 'result': runner.terminal_receipt, **FALSE_FLAGS}
            else:
                state['stage'] = 'launch'
                for index in range(3):
                    if index:
                        require(remaining(deadline) > 60, 'deadline')
                        time.sleep(60)
                    outcome = runner.launch_once()
                    if outcome['state'] != 'wait': break
                else:
                    result = {'terminal': 'capacity_wait', 'application_dispatch_count': state['dispatch_count'],
                        'compiled': compiled, 'launch': None, 'result': None, **FALSE_FLAGS}
                    preflight(args, deadline)
                    pin = directory.write('report.json', {**binding(args), 'result': result})
                    return {'result': result, 'report': pin}
                state['launch'] = runner.launch_receipt
                state['stage'] = 'status'
                for index in range(240):
                    if runner.terminal_receipt is not None: break
                    require(remaining(deadline) > 60, 'deadline')
                    time.sleep(60)
                    runner.poll_status(index)
                require(runner.terminal_receipt is not None, 'status_budget')
                state['terminal'] = runner.terminal_receipt
                if state['terminal']['status'] != 'Completed.':
                    state['stage'] = 'failure_detail'
                    runner.read_failure_once()
                    state['terminal'] = runner.terminal_receipt
                    try:
                        joined = run_join_worker(args, directory, deadline, state['terminal'])
                    except BaseException as error:
                        joined = {'status': 'unavailable', 'failure_code': finite(error)}
                    result = {'terminal': 'runtime_error', 'application_dispatch_count': state['dispatch_count'],
                        'compiled': compiled, 'launch': runner.launch_receipt,
                        'result': state['terminal'], 'diagnostic_join': joined, **FALSE_FLAGS}
                else:
                    state['stage'] = 'result'
                    accepted = runner.read_once()
                    state['stage'] = 'final_admission'
                    require(run_worker(args, directory, deadline, 1) == packet, 'admission_changed')
                    result = {'terminal': 'completed', 'application_dispatch_count': state['dispatch_count'],
                        'compiled': compiled, 'launch': runner.launch_receipt, 'result': accepted, **FALSE_FLAGS}
            preflight(args, deadline)
            pin = directory.write('report.json', {**binding(args), 'result': result})
            return {'result': result, 'report': pin}
        except BaseException as error:
            state['compiled'] = runner.compile_receipt if runner is not None else None
            state['launch'] = runner.launch_receipt if runner is not None else None
            state['terminal'] = runner.terminal_receipt if runner is not None else None
            failed = {'failure_code': finite(error), 'state': state, 'provider_request_count': None,
                'attempt_consumption': 'consumed_or_ambiguous_no_retry', **FALSE_FLAGS}
            try: directory.write('failure.json', {**binding(args), **failed})
            except BaseException: pass
            return {'failure': failed}


def _state(value):
    require(type(value) is dict and set(value) == {'stage', 'dispatch_count', 'response_count',
        'last_endpoint', 'last_response_received', 'compiled', 'launch', 'terminal'}
        and value['stage'] in ('initial_admission', 'prepare', 'compile', 'launch', 'status',
                              'failure_detail', 'result', 'final_admission')
        and type(value['dispatch_count']) is int and 0 <= value['dispatch_count'] <= MAX_DISPATCHES
        and type(value['response_count']) is int and 0 <= value['response_count'] <= value['dispatch_count']
        and type(value['last_response_received']) is bool, 'output')
    remote = _remote()
    count = value['dispatch_count']
    require((count == 0 and value['response_count'] == 0 and value['last_endpoint'] is None
             and value['last_response_received'] is False)
        or (count > 0 and type(value['last_endpoint']) is str and value['last_endpoint'] in remote.PAYLOAD_KEYS
            and value['response_count'] == count - (not value['last_response_received'])), 'output')
    if value['stage'] == 'initial_admission': require(count == 0, 'output')
    if value['compiled'] is not None: remote.validate_compile_receipt(value['compiled'])
    if value['launch'] is not None:
        remote.validate_launch_receipt(value['launch'])
        require(value['compiled'] is not None and all(value['launch'][key] == item
            for key, item in value['compiled'].items()), 'output')
    if value['terminal'] is not None:
        remote.validate_terminal_receipt(value['terminal'])
        base = value['compiled'] if value['terminal']['status'] == 'BuildError' else value['launch']
        require(base is not None and all(value['terminal'][key] == item for key, item in base.items()), 'output')


def validate_output(raw, actual_exit, args):
    require(type(actual_exit) is int and actual_exit in (0, 2) and type(raw) is bytes
        and 0 < len(raw) <= MAX_OUTPUT, 'output')
    value = parse(raw)
    if set(value) == {'binding', 'preflight_failure'}:
        require(actual_exit == 2 and value['binding'] == binding(args)
            and _finite_code(value['preflight_failure']), 'output')
        return value
    require(set(value) == {'binding', 'outcome'} and value['binding'] == binding(args), 'output')
    outcome = value['outcome']
    require(type(outcome) is dict, 'output')
    if 'failure' in outcome:
        require(actual_exit == 2 and set(outcome) == {'failure'}, 'output')
        failed = outcome['failure']
        require(type(failed) is dict and set(failed) == {'failure_code', 'state',
            'provider_request_count', 'attempt_consumption', *FALSE_FLAGS}
            and _finite_code(failed['failure_code'])
            and failed['provider_request_count'] is None
            and failed['attempt_consumption'] == 'consumed_or_ambiguous_no_retry'
            and all(failed[key] is False for key in FALSE_FLAGS), 'output')
        _state(failed['state'])
    else:
        require(set(outcome) == {'result', 'report'} and type(outcome['result']) is dict, 'output')
        result = outcome['result']
        expected_keys = {'terminal', 'application_dispatch_count', 'compiled', 'launch', 'result', *FALSE_FLAGS}
        if result.get('terminal') == 'runtime_error': expected_keys.add('diagnostic_join')
        require(set(result) == expected_keys
            and result['terminal'] in ('completed', 'runtime_error', 'compile_error', 'capacity_wait')
            and type(result['application_dispatch_count']) is int
            and 0 <= result['application_dispatch_count'] <= MAX_DISPATCHES
            and all(result[key] is False for key in FALSE_FLAGS), 'output')
        report = canonical({**binding(args), 'result': result})
        require(outcome['report'] == {'byte_count': len(report), 'sha256': sha(report)}
            and actual_exit == (2 if result['terminal'] in ('runtime_error', 'compile_error') else 0), 'output')
        remote = _remote()
        remote.validate_compile_receipt(result['compiled'])
        if result['launch'] is not None:
            remote.validate_launch_receipt(result['launch'])
            require(all(result['launch'][key] == item for key, item in result['compiled'].items()), 'output')
        if result['terminal'] == 'completed':
            require(result['launch'] is not None, 'output')
            remote.validate_result_receipt(result['result'])
            require(all(result['result'][key] == item for key, item in result['launch'].items()), 'output')
        elif result['terminal'] in ('runtime_error', 'compile_error'):
            remote.validate_terminal_receipt(result['result'])
            wanted = 'Runtime Error' if result['terminal'] == 'runtime_error' else 'BuildError'
            base = result['launch'] if wanted == 'Runtime Error' else result['compiled']
            require(result['result']['status'] == wanted and base is not None
                and (wanted != 'BuildError' or result['launch'] is None)
                and all(result['result'][key] == item for key, item in base.items()), 'output')
            if wanted == 'Runtime Error': validate_join(result['diagnostic_join'], result['result'])
        else:
            require(result['launch'] is None and result['result'] is None, 'output')
    return value


def observe(args):
    credentials, parent_env = {}, {}
    outer = {'schema': SCHEMA + '-observer', 'parent': None, 'validator': None,
             'output_authenticated': False, 'output': None, 'failure_code': None}
    try:
        credentials = credential_shape()
        runtime = Path(tempfile.mkdtemp(prefix='r323-a19-observer-', dir=ROOT / '.pytest_cache'))
        safe = capture_support._environment(runtime)
        parent_env = capture_support._environment(runtime, credentials)
        raw, errors, observed = capture([str(PYTHON), '-B', str(SOURCE), 'run',
            '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256],
            parent_env, DEADLINE_SECONDS + 30)
        outer['parent'] = observed
        credentials.clear(); parent_env.clear()
        require(observed['bound'] is None and not errors and type(observed['actual_exit']) is int
                and observed['actual_exit'] in (0, 2), 'parent_failed')
        command = ['/usr/bin/sandbox-exec', '-p', native_profile(artifacts=True), str(PYTHON), '-B', str(SOURCE),
            'validate', '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256,
            '--actual-exit', str(observed['actual_exit'])]
        valid, stderr, checked = capture(command, safe, 20, input_bytes=raw)
        outer['validator'] = checked
        require(checked['actual_exit'] == 0 and checked['bound'] is None and not stderr, 'validator_failed')
        outer['output'] = parse(valid)
        outer['output_authenticated'] = True
        require(len(canonical(outer)) <= MAX_OBSERVER_OUTPUT, 'output_bound')
        return outer, observed['actual_exit']
    except BaseException as error:
        outer['failure_code'] = finite(error)
        return outer, 2
    finally:
        credentials.clear(); parent_env.clear()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('observe', 'run', 'worker', 'join-worker', 'validate'))
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--caller-sha256', required=True)
    parser.add_argument('--control-fd', type=int)
    parser.add_argument('--worker-index', type=int)
    parser.add_argument('--actual-exit', type=int)
    args = parser.parse_args(argv)
    if args.operation == 'observe':
        result, code = observe(args)
        sys.stdout.buffer.write(canonical(result))
        return code
    deadline = time.monotonic() + (120 if args.operation in ('worker', 'join-worker', 'validate') else DEADLINE_SECONDS)
    try:
        with admitted.helpers._alarm(deadline):
            preflight(args, deadline)
            environment._bootstrap_cli_logging()
            if args.operation == 'worker':
                payload, code = {'binding': binding(args), 'packet': worker(args, deadline)}, 0
            elif args.operation == 'join-worker':
                payload, code = {'binding': binding(args), 'diagnostic_join': join_worker(args, deadline)}, 0
            elif args.operation == 'validate':
                payload = validate_output(sys.stdin.buffer.read(MAX_OUTPUT + 1), args.actual_exit, args)
                code = 0
            else:
                outcome = run(args, deadline)
                payload = {'binding': binding(args), 'outcome': outcome}
                code = 2 if 'failure' in outcome or outcome.get('result', {}).get('terminal') in ('runtime_error', 'compile_error') else 0
            raw = canonical(payload)
            require(len(raw) <= (MAX_PACKET if args.operation == 'worker' else MAX_OUTPUT), 'output_bound')
            sys.stdout.buffer.write(raw)
            return code
    except BaseException as error:
        sys.stdout.buffer.write(canonical({'binding': binding(args), 'preflight_failure': finite(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
