"""Offline metadata-only proposal for five exact original native-price sources.

A failed AD mapping attempt remains failure. Its authenticated, normally
guarded source-selection DATA can bind this new proposal, never identity,
price admission, an upload, a QC invocation or strategy readiness.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
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
from scripts import inspect_arv2_r298_public_figi_lineage as previous
from scripts import arv2_r298_ad_source_binding as anchor
from scripts import arv2_r298_fixed_data_guard as data_guard
from research.analyst_revisions_v2_qc import newrule_native_price_source_diagnostic as diagnostic

admitted, environment, security = previous.admitted, previous.environment, previous.security
capture_support, canonical, parse, sha, metadata, capture = (
    previous.capture_support, previous.canonical, previous.parse, previous.sha, previous.metadata, previous.capture)
PYTHON = previous.PYTHON
SOURCE = ROOT / 'scripts/prepare_arv2_r298_native_price_specification.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_native_price_spec/R326-20261027-AE'
SCHEMA = 'arv2-r298-native-five-source-specification-ae-v1'
DEADLINE_SECONDS, OUTER_SECONDS, VALIDATOR_SECONDS = 120, 150, 20
MAX_SOURCE, MAX_OUTPUT, MAX_FILES = 1024 * 1024, 128 * 1024, 8
MAX_OBSERVER_OUTPUT = MAX_OUTPUT + 4096
FILE_PLAN = {'ad_selection': {
    'relative_path': 'artifacts/analyst_revisions_v2/newrule_public_figi_lineage/R326-20261027-AD/public-figi-private.json',
    'byte_count': 26503, 'sha256': 'babb09c92ccf109bede02e0e9d125dc650ad3d64fee99b64b08770f19a62961c'}}
SPEC_NAME = 'native-price-specification.json'
AD_HEAD = '874b349d8b681b1fbca908502c40994869229b92'
AD_CALLER_SHA256 = '0e1328c07fa82690625a49dbc043cc9facdf125516bfff8a411dd0eb5bfa2ab4'
AD_PROFILE_SHA256 = 'd4f0a0fa48dc248d11660888d4a130c8b2f5a9bac64576fbdcf1e05fbf79e230'
AD_FACT_SHA256 = '9283ca349c8ee2ca06392b8c977155acf733de0d342a286590362da648e40464'
AD_FAILURE_SHA256 = 'dfa82225a1d2502a1e0bd2645f79f951c20a7a53a269e06b9f1c901cb25b3fb4'
SELECTION_BYTES = 24516
SELECTION_SHA256 = '0776dc737e2b35f481b2f732d8bb17f5e2bf32e8faa3478e2897f64488740e7a'
NEW_PINS = {
    'scripts/inspect_arv2_r298_public_figi_lineage.py': AD_CALLER_SHA256,
    'scripts/arv2_r298_ad_source_binding.py': '0f123b2a81718abbdb1c529f8ac8d974ac62ad45ab358cd99d825b1a5ae4eec2',
    'research/analyst_revisions_v2_qc/newrule_native_price_source_diagnostic.py': '57450eac9126831bc9d1c106325ed1832c10ba32e883563bb85e10060948e697',
}
FALSE_FLAGS = {'old_AD_mapping_accepted': False, 'QC_history_invoked': False, 'QC_data_exported': False, 'provider_contact': False, 'credential_access': False, 'qc_contact': False,
    'old_controls_read': False, 'original_TICKERS_reread': False,
    'refused_bindings_dropped': False, 'old_operation_invoked': False, 'new_paid_rights': False,
    'price_acquired': False, 'strategy_price_admitted': False, 'strategy_nav_admitted': False,
    'strategy_result_accepted': False, 'family_comparable': False, 'point_in_time_proven': False,
    'formal_identity_admitted': False, 'formal_forward_ready': False,
    'paper_or_live_ready': False, 'licensed_rows_disclosed': False,
    'historical_metadata_preservation_proven': False, 'continuous_security_proven': False}
FINITE = frozenset(('deadline', 'host', 'arguments', 'git_state', 'source_pin', 'source_binding',
    'source_changed', 'claim_spent', 'control_changed', 'control_name', 'control_bound', 'control_write',
    'capture_changed', 'capture_security', 'package', 'selection', 'binding', 'original_evidence', 'specification',
    'output', 'output_bound', 'parent_failed', 'validator_failed', 'execution_environment_refused',
    'os_error', 'refused', 'unknown_exception'))


class Refused(ValueError):
    """Finite recovery predicate only, never rows or exception strings."""


def require(value, code):
    if not value:
        raise Refused(code)


def remaining(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline), 'deadline')
    value = deadline - time.monotonic()
    require(0 < value <= DEADLINE_SECONDS, 'deadline')
    return value


def finite(error):
    if type(error) is admitted.helpers.Deadline:
        return 'deadline'
    for module, prefix in ((diagnostic, 'native_'), (data_guard, 'guard_')):
        if type(error) is module.Refused:
            code = module.finite(error)
            return prefix + code if code in module.FINITE else 'refused'
    if type(error) is environment.EnvironmentRefused:
        return 'execution_environment_refused'
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'refused'
    if isinstance(error, OSError):
        return 'os_error'
    return 'unknown_exception'


def _finite_code(value):
    return type(value) is str and value in FINITE | {
        prefix + code for module, prefix in ((diagnostic, 'native_'), (data_guard, 'guard_')) for code in module.FINITE}


def pins():
    result = previous.pins()
    require(len(result) == 178, 'source_pin')
    for name, pin in NEW_PINS.items():
        require(name not in result or result[name] == pin, 'source_pin')
        require(type(pin) is str and re.fullmatch('[0-9a-f]{64}', pin) and pin != '0' * 64, 'source_pin')
        result[name] = pin
    return result


def preflight(args, deadline):
    require(not admitted.v5._under_test() and Path(__file__).absolute() == SOURCE
        and sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT, 'host')
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}', args.expected_head)
        and type(args.caller_sha256) is str and re.fullmatch('[0-9a-f]{64}', args.caller_sha256), 'arguments')
    environment._require_environment()
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)),
        (['branch', '--show-current'], admitted.frozen.BRANCH), (['rev-parse', 'HEAD'], args.expected_head),
        (['status', '--porcelain'], '')):
        require(admitted.v5._git(command, deadline).decode('ascii').strip() == expected, 'git_state')
    for name, pin in pins().items():
        require(sha((ROOT / name).read_bytes()) == pin, 'source_pin')
    require(sha(SOURCE.read_bytes()) == args.caller_sha256, 'source_pin')
    committed = admitted.v5._git(['cat-file', 'blob', args.expected_head + ':'
        + SOURCE.relative_to(ROOT).as_posix()], deadline, MAX_OUTPUT)
    require(sha(committed) == args.caller_sha256, 'source_pin')
    remaining(deadline)


def security_snapshot(fd, *, source=False):
    try:
        return security.snapshot(fd)
    except security.Refusal:
        raise Refused('source_security' if source else 'capture_security') from None


class Store:
    """Only the new AE leaf and original descriptors; no old control reader."""
    def __init__(self):
        self.fd, self.chain, self.files, self.held = None, [], {}, {}
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for index, part in enumerate(CONTROL.parts[1:], 1):
                path = Path(*CONTROL.parts[:index + 1])
                if path in (CONTROL.parent, CONTROL):
                    try:
                        os.mkdir(part, 0o700, dir_fd=fd); os.fsync(fd)
                    except FileExistsError:
                        require(path != CONTROL, 'claim_spent')
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd); fd = nxt
                self.chain.append((os.fstat(fd).st_dev, os.fstat(fd).st_ino))
            self.fd = fd
            self.directory_security = security_snapshot(fd)
            self.verify()
        except BaseException:
            os.close(fd)
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        for fd, _ in self.held.values():
            os.close(fd)
        os.close(self.fd)

    def verify(self):
        other, chain = admitted._storage_module()._walk(CONTROL)
        try:
            require(chain == tuple(self.chain) and metadata(os.fstat(self.fd)) == metadata(os.fstat(other))
                and os.fstat(other).st_uid == os.getuid() and stat.S_IMODE(os.fstat(other).st_mode) == 0o700
                and set(os.listdir(other)) == set(self.files) and len(self.files) <= MAX_FILES
                and security_snapshot(self.fd) == self.directory_security, 'control_changed')
            for name, baseline in self.files.items():
                fd, snapshot = self.held[name]
                require(baseline == metadata(os.fstat(fd))
                    == metadata(os.stat(name, dir_fd=other, follow_symlinks=False))
                    and security_snapshot(fd) == snapshot, 'capture_changed')
        finally:
            os.close(other)

    @staticmethod
    def _read(fd, size, *, deadline=None):
        os.lseek(fd, 0, os.SEEK_SET)
        result = bytearray()
        while len(result) <= size:
            if deadline is not None:
                remaining(deadline)
            chunk = os.read(fd, min(65536, size + 1 - len(result)))
            if not chunk:
                break
            result.extend(chunk)
        return bytes(result)

    def write(self, name, value):
        return self.write_bytes(name, canonical(value), private=False)

    def write_bytes(self, name, raw, *, private):
        self.verify()
        require(type(name) is str and name not in self.files and len(self.files) < MAX_FILES
            and private is False and re.fullmatch(r'[a-z0-9-]{1,100}\.json', name), 'control_name')
        require(type(raw) is bytes and 0 < len(raw) <= MAX_OUTPUT, 'control_bound')
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        kept = False
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_uid == os.getuid() and info.st_nlink == 1 and info.st_size == 0, 'control_write')
            snapshot = security_snapshot(fd)
            view = memoryview(raw)
            while view:
                count = os.write(fd, view); require(count > 0, 'control_write'); view = view[count:]
            os.fsync(fd); os.fsync(self.fd)
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_uid == os.getuid() and info.st_nlink == 1 and info.st_size == len(raw), 'control_write')
            require(self._read(fd, len(raw)) == raw and metadata(info) == metadata(os.fstat(fd))
                and security_snapshot(fd) == snapshot, 'capture_changed')
            self.files[name] = metadata(info); self.held[name] = (fd, snapshot); kept = True
        finally:
            if not kept:
                os.close(fd)
        self.verify()
        return {'byte_count': len(raw), 'sha256': sha(raw)}


def _artifact_policy(leaves, *, package=None):
    directories = {ROOT / 'artifacts'}
    for path in [*leaves, *(() if package is None else (package,))]:
        directories.update(parent for parent in path.parents if ROOT / 'artifacts' == parent
            or ROOT / 'artifacts' in parent.parents)
    exceptions = ''.join(f'(require-not (literal "{path}"))' for path in sorted(directories | set(leaves)))
    subtree = '' if package is None else f'(require-not (subpath "{package}"))'
    return f'(deny file-read* (require-all (subpath "{ROOT / "artifacts"}") {subtree} {exceptions}))'


def source_binding():
    fact, failure = anchor.observed_fact(), anchor.expected_failure()
    require(sha(diagnostic.canonical(fact)) == AD_FACT_SHA256
        and sha(diagnostic.canonical(failure)) == AD_FAILURE_SHA256, 'source_binding')
    pin = FILE_PLAN['ad_selection']
    require(fact['expected_head'] == AD_HEAD and fact['caller_sha256'] == AD_CALLER_SHA256
        and fact['profile_sha256'] == AD_PROFILE_SHA256 and fact['failure_code'] == 'transport_unknown'
        and fact['source_guard_returned'] is True and fact['private_file'] == pin
        and type(fact['producer']['actual_exit']) is int and fact['producer']['actual_exit'] == 2
        and type(fact['validator']['actual_exit']) is int and fact['validator']['actual_exit'] == 0
        and all(fact[name]['bound'] is None and fact[name]['spawn_observed'] is True
            and fact[name]['stderr_bytes'] == 0 and fact[name]['stderr_sha256'] == sha(b'')
            for name in ('producer', 'validator')), 'source_binding')
    state = failure['state']
    require(failure['failure_code'] == 'transport_unknown' and failure['claim_consumed'] is True
        and failure['provider_request_count'] is None and state['source_guard_returned'] is True
        and state['mapping_complete'] is False and state['terminal_failure_code'] == 'transport_unknown'
        and state['private_pin'] == state['package_pin'] == {'byte_count': pin['byte_count'], 'sha256': pin['sha256']}
        and state['selection_summary']['private_case_byte_count'] == SELECTION_BYTES
        and state['selection_summary']['private_case_sha256'] == SELECTION_SHA256
        and state['http_statuses'] == [] and state['response_pins'] == {}
        and state['batch_summaries'] == [] and state['corroboration_counts'] == {}, 'source_binding')
    previous._selection_summary(state['selection_summary'])
    data_guard.validate_receipt(state['source_receipt'], previous.FILE_PLAN)
    return state['selection_summary']


def profile_record():
    source_binding()
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': admitted.frozen.BRANCH,
        'python': str(PYTHON), 'source': str(SOURCE), 'control': str(CONTROL), 'source_pins': pins(),
        'purpose': 'one_offline_metadata_only_specification_for_five_exact_original_native_price_sources',
        'fixed_data_plan': data_guard.checked_plan(FILE_PLAN),
        'source_guard_profile': data_guard.profile_record(FILE_PLAN),
        'AD_observation': anchor.profile_record(), 'AD_actual_failure_preserved': True,
        'AD_observed_fact_sha256': AD_FACT_SHA256, 'AD_failure_sha256': AD_FAILURE_SHA256,
        'selection_byte_count': SELECTION_BYTES, 'selection_sha256': SELECTION_SHA256,
        'source_data_leaf_count': 1, 'prior_source_frame_pins_are_history_not_new_reads': True,
        'native_helper_profile': diagnostic.profile_record(),
        'whole_binding_hash_namespace': 'full_canonical_sorted_ASCII_JSON_WITHOUT_LF',
        'original_semantic_row_hash_checked_by_frozen_input_row_WITH_LF_namespace': True,
        'original_SF1_functional_currency_is_not_native_quote_currency': True,
        'original_class_and_every_other_original_identity_predicate_remain_required': True,
        'original_QC_SIDs_absent_never_inferred': True,
        'future_QC_requires_fresh_full_6151_package_roundtrip_full_collision_and_all8_ownETF_checks_before_History': True,
        'source_stop_retained_vendor_issues': 5, 'same_full_window_source_proposal_for_all_six_cells': True,
        'claim_consumes_even_without_source_read': True, 'partial_claim_is_ambiguous_spent': True,
        'source_descriptor_held_through_direct_metadata_preparation_and_normal_return': True,
        'metadata_specification_written_only_after_normal_source_guard_return': True,
        'pure_validation_recomputation_is_not_another_operational_invocation': True,
        'specification_is_not_QC_upload_project_compile_capacity_or_run_authority': True,
        'producer_seconds': DEADLINE_SECONDS, 'outer_seconds': OUTER_SECONDS,
        'validator_seconds': VALIDATOR_SECONDS, 'maximum_source_bytes': MAX_SOURCE,
        'maximum_public_bytes': MAX_OUTPUT, 'maximum_control_files': MAX_FILES,
        'native_all_network_Keychain_security_CLI_denial': True,
        'producer_writes_only_own_AE_control_root_cache_or_null': True,
        'one_native_producer_no_inner_child_or_nested_sandbox': True,
        'observer_public_only_no_data_broker': True,
        'selected_pins_not_whole_interpreter_integrity': True,
        'actual_new_exit_zero_and_separate_native_validator_zero_required': True,
        'deadline_host_suspension_uninterruptible_IO_qualification': True,
        'diagnostic_only': True, 'result_cell': 0, **FALSE_FLAGS}


def binding(args):
    return {'schema': SCHEMA, 'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256,
        'profile_sha256': sha(canonical(profile_record()))}


def native_profile(*, mode):
    require(mode in ('producer', 'validator'), 'arguments')
    base = '(version 1)(allow default)(deny network*)'
    base += ''.join(f'(deny file-read* file-write* (subpath "{path}"))'
        for path in ('/Users/sheltonchen/Library/Keychains', '/Library/Keychains'))
    base += '(deny process-exec (literal "/usr/bin/security"))'
    exceptions = f'(require-not (subpath "{ROOT / ".pytest_cache"}"))(require-not (literal "/dev/null"))'
    if mode == 'producer':
        exceptions += f'(require-not (subpath "{CONTROL}"))(require-not (literal "{CONTROL.parent}"))'
    base += f'(deny file-write* (require-all {exceptions}))'
    if mode == 'validator':
        return base + f'(deny file-read* (subpath "{ROOT / "artifacts"}"))'
    return base + _artifact_policy([*(ROOT / row['relative_path'] for row in FILE_PLAN.values()), CONTROL,
        *(CONTROL / name for name in ('claim.json', 'source-start.json', SPEC_NAME, 'report.json', 'failure.json'))])


def _selection_hashes(selection, deadline):
    require(type(selection) is dict and set(selection) == {'schema', 'cases', 'figis'}
        and selection['schema'] == previous.SCHEMA + '-private-selection'
        and type(selection['cases']) is list and len(selection['cases']) == 5
        and type(selection['figis']) is list and len(selection['figis']) == 9
        and selection['figis'] == sorted(set(selection['figis']))
        and all(previous._valid_figi(value) for value in selection['figis']), 'selection')
    price = previous.previous.routes
    contract = previous.source_binding()['aa_routing_summary']['binding_contract']
    require(contract['binding_count'] == 6151
        and contract['binding_stream_sha256'] == diagnostic.BINDING_STREAM_SHA256
        and contract['security_master_admission_sha256'] == diagnostic.ADMISSION_SHA256, 'binding')
    hashes, ordinals, reasons, figis, non_USD = [], set(), [], set(), 0
    for index, case in enumerate(selection['cases']):
        remaining(deadline)
        require(type(case) is dict and set(case) == {'case_ordinal', 'ac_stock', 'aa_stock', 'original_figi', 'candidate_figis'}
            and type(case['case_ordinal']) is int and case['case_ordinal'] == index, 'selection')
        ac, aa = case['ac_stock'], case['aa_stock']
        require(type(ac) is dict and set(ac) == price.STOCK_FIELDS
            and type(aa) is dict and set(aa) == {'binding_ordinal', 'binding', 'original_row', 'original_cusip_tokens',
                'required_first_date', 'required_last_date', 'current_candidate_rows', 'disposition', 'reason', 'route'}
            and type(ac['binding_ordinal']) is int and 0 <= ac['binding_ordinal'] < 6151
            and type(aa['binding_ordinal']) is int and ac['binding_ordinal'] == aa['binding_ordinal']
            and ac['binding_ordinal'] not in ordinals and type(ac['binding']) is dict
            and ac['binding'] == aa['binding'] and ac['potential'] is True
            and ac['conditional_never_potential'] is False and ac['disposition'] == 'refused'
            and ac['reason'] in ('identity_missing', 'global_collision') and ac['route'] is None
            and ac['query_window'] is None and ac['aa_disposition'] == aa['disposition']
            and ac['aa_reason'] == aa['reason'] and type(ac['observed_flags']) is dict
            and set(ac['observed_flags']) == price.FLAGS
            and all(type(value) is bool for value in ac['observed_flags'].values()), 'selection')
        ordinals.add(ac['binding_ordinal']); reasons.append(ac['reason'])
        try:
            checked = diagnostic.figi._input_row(dict(ac['binding']), diagnostic.ADMISSION_SHA256)
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            raise Refused('binding') from None
        require(checked == ac['binding'] and checked['qc_security_id'] is None
            and checked['qc_sid_available'] is False and case['original_figi'] == checked['composite_figi']
            and checked['admitted_mapping_count'] == contract['binding_count']
            and checked['admitted_mapping_inventory_sha256'] == contract['admitted_mapping_inventory_sha256'], 'binding')
        try:
            original = price._original(aa)
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            raise Refused('original_evidence') from None
        require(type(aa['original_row']) is dict and aa['original_row'].get('table') == 'SF1'
            and type(aa['original_row'].get('currency')) is str
            and aa['original_cusip_tokens'] == list(original['tokens']), 'original_evidence')
        non_USD += aa['original_row'].get('currency') != 'USD'
        candidates = aa['current_candidate_rows']
        require(type(candidates) is list and candidates
            and all(type(row) is dict and previous._valid_figi(row.get('figi')) for row in candidates)
            and case['candidate_figis'] == sorted(set(row['figi'] for row in candidates)), 'selection')
        figis.add(case['original_figi']); figis.update(case['candidate_figis'])
        hashes.append(diagnostic.digest(checked))
    require(Counter(reasons) == {'identity_missing': 4, 'global_collision': 1}
        and sorted(figis) == selection['figis'] and len(set(hashes)) == 5, 'selection')
    return {'selected_whole_binding_sha256s': sorted(hashes), 'selected_case_count': 5,
        'original_binding_schema_and_semantic_row_hash_checked_count': 5,
        'original_class_and_identity_evidence_checked_count': 5,
        'original_non_USD_functional_reporting_currency_count': non_USD,
        'original_native_QC_SIDs_available': False, 'vendor_source_blockers_remaining': 5}


def prepare(raw, deadline):
    """Authenticate one fixed selection DATA leaf; return public metadata only."""
    pin = FILE_PLAN['ad_selection']
    require(type(raw) is bytes and len(raw) == pin['byte_count'] and sha(raw) == pin['sha256'], 'package')
    value = previous._decode_private(raw)
    expected = source_binding()
    require(set(value) == {'schema', 'source_pins', 'AC_summary_sha256', 'selection_summary', 'selection',
        'mapping_batches', 'corroborations', 'response_pins', 'terminal_failure_code',
        'vendor_source_blockers_remaining', 'candidate_scope', 'no_original_identifier_or_vendor_collision_clearance'}
        and value['schema'] == previous.SCHEMA + '-private'
        and value['source_pins'] == {role: {'byte_count': row['byte_count'], 'sha256': row['sha256']}
            for role, row in previous.FILE_PLAN.items()}
        and value['AC_summary_sha256'] == previous.AC_SUMMARY_SHA256
        and value['selection_summary'] == expected and value['mapping_batches'] == []
        and value['corroborations'] == [] and value['response_pins'] == {}
        and value['terminal_failure_code'] == 'transport_unknown'
        and type(value['vendor_source_blockers_remaining']) is int and value['vendor_source_blockers_remaining'] == 5
        and value['candidate_scope'] == 'complete_retained_AA_subset_not_vendor_global_counterparty_census'
        and value['no_original_identifier_or_vendor_collision_clearance'] is True, 'package')
    selection_raw = diagnostic.canonical(value['selection'])
    require(len(selection_raw) == SELECTION_BYTES and sha(selection_raw) == SELECTION_SHA256, 'selection')
    evidence = _selection_hashes(value['selection'], deadline)
    specification = diagnostic.make_specification(evidence['selected_whole_binding_sha256s'])
    specification = diagnostic.validate_specification(specification)
    remaining(deadline)
    return evidence, specification


def _evidence(value):
    keys = {'selected_whole_binding_sha256s', 'selected_case_count',
        'original_binding_schema_and_semantic_row_hash_checked_count', 'original_class_and_identity_evidence_checked_count',
        'original_non_USD_functional_reporting_currency_count', 'original_native_QC_SIDs_available', 'vendor_source_blockers_remaining'}
    require(type(value) is dict and set(value) == keys and value['selected_case_count'] == 5
        and type(value['selected_case_count']) is int
        and type(value['original_binding_schema_and_semantic_row_hash_checked_count']) is int
        and value['original_binding_schema_and_semantic_row_hash_checked_count'] == 5
        and type(value['original_class_and_identity_evidence_checked_count']) is int
        and value['original_class_and_identity_evidence_checked_count'] == 5
        and type(value['original_non_USD_functional_reporting_currency_count']) is int
        and 0 <= value['original_non_USD_functional_reporting_currency_count'] <= 5
        and value['original_native_QC_SIDs_available'] is False
        and type(value['vendor_source_blockers_remaining']) is int and value['vendor_source_blockers_remaining'] == 5, 'output')
    diagnostic.make_specification(value['selected_whole_binding_sha256s'])


def run(args, deadline):
    with Store() as directory:
        directory.write('claim.json', {**binding(args), 'offline_only': True, 'old_controls_spent': True})
        state = {'stage': 'source', 'source_receipt': None, 'selection_evidence': None,
            'specification': None, 'source_guard_returned': False, 'specification_pin': None}
        raw = None
        try:
            directory.write('source-start.json', {**binding(args), 'stage': 'one-AD-source-selection-DATA-leaf'})
            environment.require_safe_environment()
            with data_guard.FixedDataGuard(FILE_PLAN, deadline=deadline) as guard:
                raw = guard.read_all_once()['ad_selection']
                receipt = guard.receipt(); state['source_receipt'] = receipt
                state['stage'] = 'prepare'
                environment.require_safe_environment()
                evidence, specification = prepare(raw, deadline)
                environment.require_safe_environment()
                _evidence(evidence); diagnostic.validate_specification(specification)
                require(specification['selected_whole_binding_sha256s'] == evidence['selected_whole_binding_sha256s'], 'specification')
                state['selection_evidence'], state['specification'] = evidence, specification
                require(guard.receipt() == receipt, 'source_changed'); remaining(deadline)
            state['source_guard_returned'] = True; state['stage'] = 'publication'; raw = None
            environment.require_safe_environment()
            spec_raw = diagnostic.canonical(specification)
            state['specification_pin'] = directory.write_bytes(SPEC_NAME, spec_raw, private=False)
            require(state['specification_pin'] == {'byte_count': len(spec_raw), 'sha256': sha(spec_raw)}, 'specification')
            state['stage'] = 'postflight'
            environment.require_safe_environment()
            preflight(args, deadline); environment.require_safe_environment(); directory.verify()
            result = {'schema': SCHEMA, **state, 'AD_actual_producer_exit': 2,
                'AD_actual_validator_exit': 0, 'AD_mapping_accepted': False,
                'AD_observed_fact_sha256': AD_FACT_SHA256, 'AD_failure_sha256': AD_FAILURE_SHA256,
                'post_checks_complete': True, 'diagnostic_only': True, 'result_cell': 0, **FALSE_FLAGS}
            validate_result(result); state['stage'] = 'report'
            report = directory.write('report.json', {**binding(args), 'result': result})
            directory.verify(); return {'result': result, 'report': report}
        except BaseException as error:
            failed = {'failure_code': finite(error), 'state': state, 'claim_consumed': True, **FALSE_FLAGS}
            try: directory.write('failure.json', {**binding(args), **failed})
            except BaseException: pass
            return {'failure': failed}
        finally:
            raw = None


def _state(value, *, success=False):
    require(type(value) is dict and set(value) == {'stage', 'source_receipt', 'selection_evidence',
        'specification', 'source_guard_returned', 'specification_pin'}
        and value['stage'] in ('source', 'prepare', 'publication', 'postflight', 'report')
        and type(value['source_guard_returned']) is bool, 'output')
    if value['source_receipt'] is not None:
        data_guard.validate_receipt(value['source_receipt'], FILE_PLAN)
    if value['selection_evidence'] is not None: _evidence(value['selection_evidence'])
    if value['specification'] is not None:
        diagnostic.validate_specification(value['specification'])
        require(value['selection_evidence'] is not None and value['source_receipt'] is not None
            and value['specification']['selected_whole_binding_sha256s'] ==
                value['selection_evidence']['selected_whole_binding_sha256s'], 'output')
    if value['source_guard_returned']: require(value['specification'] is not None, 'output')
    if value['stage'] == 'source':
        require(value['selection_evidence'] is None and value['specification'] is None
            and value['source_guard_returned'] is False and value['specification_pin'] is None, 'output')
    if value['stage'] == 'prepare':
        require(value['source_receipt'] is not None and value['source_guard_returned'] is False
            and value['specification_pin'] is None, 'output')
    if value['stage'] in ('publication', 'postflight', 'report'): require(value['source_guard_returned'] is True, 'output')
    if value['specification_pin'] is not None:
        encoded = diagnostic.canonical(value['specification'])
        require(value['source_guard_returned'] is True and type(value['specification_pin']) is dict
            and value['specification_pin'] == {'byte_count': len(encoded), 'sha256': sha(encoded)}, 'specification')
    if value['stage'] in ('postflight', 'report') or success:
        require(value['specification_pin'] is not None, 'output')


def validate_result(result):
    fields = {'stage', 'source_receipt', 'selection_evidence', 'specification', 'source_guard_returned', 'specification_pin'}
    require(type(result) is dict and set(result) == {'schema', *fields, 'AD_actual_producer_exit', 'AD_actual_validator_exit',
        'AD_mapping_accepted', 'AD_observed_fact_sha256', 'AD_failure_sha256', 'post_checks_complete',
        'diagnostic_only', 'result_cell', *FALSE_FLAGS} and result['schema'] == SCHEMA and result['stage'] == 'postflight'
        and type(result['AD_actual_producer_exit']) is int and result['AD_actual_producer_exit'] == 2
        and type(result['AD_actual_validator_exit']) is int and result['AD_actual_validator_exit'] == 0
        and result['AD_mapping_accepted'] is False and result['AD_observed_fact_sha256'] == AD_FACT_SHA256
        and result['AD_failure_sha256'] == AD_FAILURE_SHA256 and result['post_checks_complete'] is True
        and result['diagnostic_only'] is True and type(result['result_cell']) is int and result['result_cell'] == 0
        and all(result[key] is False for key in FALSE_FLAGS), 'output')
    _state({key: result[key] for key in fields}, success=True)


def validate_output(raw, actual_exit, args):
    require(type(actual_exit) is int and actual_exit in (0, 2)
        and type(raw) is bytes and 0 < len(raw) <= MAX_OUTPUT, 'output')
    value = parse(raw)
    require(type(value) is dict and value.get('binding') == binding(args), 'output')
    if set(value) == {'binding', 'preflight_failure'}:
        require(actual_exit == 2 and _finite_code(value['preflight_failure']), 'output')
        return value
    require(set(value) == {'binding', 'outcome'} and type(value['outcome']) is dict, 'output')
    outcome = value['outcome']
    if set(outcome) == {'failure'}:
        failed = outcome['failure']
        require(actual_exit == 2 and type(failed) is dict and set(failed) == {
            'failure_code', 'state', 'claim_consumed', *FALSE_FLAGS}
            and _finite_code(failed['failure_code']) and failed['claim_consumed'] is True
            and all(failed[key] is False for key in FALSE_FLAGS), 'output')
        _state(failed['state'])
    else:
        require(actual_exit == 0 and set(outcome) == {'result', 'report'}, 'output')
        validate_result(outcome['result'])
        report = canonical({**binding(args), 'result': outcome['result']})
        require(outcome['report'] == {'byte_count': len(report), 'sha256': sha(report)}, 'output')
    return value


def observe(args):
    """No-data stage broker: one native producer, then one native validator."""
    outer = {'schema': SCHEMA + '-observer', 'producer': None, 'validator': None,
        'output_authenticated': False, 'output': None, 'failure_code': None}
    try:
        runtime = Path(tempfile.mkdtemp(prefix='r326-ae-observer-', dir=ROOT / '.pytest_cache'))
        safe = capture_support._environment(runtime)
        raw, errors, actual = capture(['/usr/bin/sandbox-exec', '-p', native_profile(mode='producer'),
            str(PYTHON), '-B', str(SOURCE), 'run', '--expected-head', args.expected_head,
            '--caller-sha256', args.caller_sha256], safe, OUTER_SECONDS, stdout_limit=MAX_OUTPUT)
        outer['producer'] = actual
        require(type(actual['actual_exit']) is int and actual['actual_exit'] in (0, 2)
            and actual['spawn_observed'] is True and actual['bound'] is None and not errors
            and actual['stdout_bytes'] == len(raw) and actual['stdout_sha256'] == sha(raw)
            and actual['stderr_bytes'] == 0 and actual['stderr_sha256'] == sha(b''), 'parent_failed')
        valid, errors, checked = capture(['/usr/bin/sandbox-exec', '-p', native_profile(mode='validator'),
            str(PYTHON), '-B', str(SOURCE), 'validate', '--expected-head', args.expected_head,
            '--caller-sha256', args.caller_sha256, '--actual-exit', str(actual['actual_exit'])],
            safe, VALIDATOR_SECONDS, input_bytes=raw, stdout_limit=MAX_OUTPUT)
        outer['validator'] = checked
        require(type(checked['actual_exit']) is int and checked['actual_exit'] == 0
            and checked['spawn_observed'] is True and checked['bound'] is None and not errors
            and checked['stdout_bytes'] == len(valid) and checked['stdout_sha256'] == sha(valid)
            and checked['stderr_bytes'] == 0 and checked['stderr_sha256'] == sha(b''), 'validator_failed')
        outer['output'] = parse(valid)
        require(canonical(outer['output']) == raw and valid == raw, 'validator_failed')
        outer['output_authenticated'] = True
        require(len(canonical(outer)) <= MAX_OBSERVER_OUTPUT, 'output_bound')
        return outer, actual['actual_exit']
    except BaseException as error:
        outer['failure_code'] = finite(error)
        return outer, 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('observe', 'run', 'validate'))
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--caller-sha256', required=True)
    parser.add_argument('--actual-exit', type=int)
    args = parser.parse_args(argv)
    if args.operation == 'observe':
        value, code = observe(args)
        sys.stdout.buffer.write(canonical(value))
        return code
    deadline = time.monotonic() + (VALIDATOR_SECONDS if args.operation == 'validate' else DEADLINE_SECONDS)
    try:
        with admitted.helpers._alarm(deadline):
            preflight(args, deadline); environment._bootstrap_cli_logging()
            if args.operation == 'validate':
                value = validate_output(sys.stdin.buffer.read(MAX_OUTPUT + 1), args.actual_exit, args)
                code = 0
            else:
                outcome = run(args, deadline)
                value = {'binding': binding(args), 'outcome': outcome}
                code = 2 if 'failure' in outcome else 0
            raw = canonical(value)
            require(len(raw) <= MAX_OUTPUT, 'output_bound')
            sys.stdout.buffer.write(raw)
            return code
    except BaseException as error:
        sys.stdout.buffer.write(canonical({'binding': binding(args), 'preflight_failure': finite(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
