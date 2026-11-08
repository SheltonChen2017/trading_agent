"""Synthetic bounded FirstRate observer; all operational DATA/USB denied."""
import copy
import ast
from contextlib import ExitStack
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace as NS
import zipfile

import pytest

from scripts import inspect_arv2_r335_firstrate_coverage_v2 as m
from scripts import arv2_r327_available_history_period as period
from research.analyst_revisions_v2_qc import accepted_risk_october_order_package as october


def args():
    return NS(expected_head='a' * 40, caller_sha256='b' * 64, profile_sha256='c' * 64)


def refuse(code, call):
    with pytest.raises(m.Refused) as caught:
        call()
    assert m.finite(caught.value) == code


def test_public_only_source_pins_and_exact_native_scope():
    assert all(m.sha((m.ROOT / name).read_bytes()) == pin for name, pin in m.SOURCE_PINS.items())
    profile = m.profile_record()
    assert len(profile['allowed_archives']) == 33
    assert len(profile['data_plan']) == 1 and profile['data_plan']['identity']['byte_count'] == 4984462
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
    policy = m.native_profile()
    assert '(deny network*)' in policy and '(deny file-write* (subpath "/Volumes/SANDISK"))' in policy
    assert '/Users/sheltonchen/Library/Keychains' in policy and '/Library/Keychains' in policy
    assert '/usr/bin/security' in policy and '[.]pyc$' in policy
    assert 'identity-demand-private.json' in policy and 'API_Access' not in policy
    assert 'report.json' not in m.DATA_PLAN['identity']['relative_path']
    assert m.CONTROL.name == 'R335-20261103-B'


def test_selected_public_imports_are_pinned_before_execution():
    with ExitStack() as stack:
        modules = m.load_modules(stack, time.monotonic() + 299)
        assert set(modules) == {'guard', 'anchor', 'prices'}
        assert modules['prices'].FINITE == m.PRICE_CODES


def test_changed_bootstrap_source_refuses_before_any_repository_import(tmp_path, monkeypatch):
    root = tmp_path / 'root'; (root / 'scripts').mkdir(parents=True)
    (root / 'scripts' / 'synthetic.py').write_bytes(b'pass\n')
    monkeypatch.setattr(m, 'ROOT', root)
    monkeypatch.setattr(m, 'SOURCE_PINS', {'scripts/synthetic.py': 'f' * 64})
    monkeypatch.setattr(m.importlib, 'import_module', lambda *args: pytest.fail('executed before pin equality'))
    with ExitStack() as stack:
        refuse('source_pin', lambda: m.load_modules(stack, time.monotonic() + 299))


@pytest.mark.parametrize('field,value', [('expected_head', 'a' * 39), ('expected_head', True),
    ('caller_sha256', 'x' * 64), ('profile_sha256', None), ('caller_sha256', 'b' * 65)])
def test_arguments_refuse_malformed_bindings(field, value):
    value_args = args(); setattr(value_args, field, value)
    refuse('arguments', lambda: m.binding(value_args))


def test_binding_accepts_exact_source_run_pins_only():
    assert m.binding(args()) == {'schema': m.SCHEMA, 'expected_head': 'a' * 40,
        'caller_sha256': 'b' * 64, 'profile_sha256': 'c' * 64}


@pytest.mark.parametrize('raw', [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'not-json', b''])
def test_json_refuses_duplicates_constants_and_malformed(raw):
    with pytest.raises(m.Refused): m.parse(raw, 100)


@pytest.fixture(scope='module')
def genuine_public_period():
    return period.make_period(october._sessions())


@pytest.fixture
def demand_case(monkeypatch, genuine_public_period):
    view = copy.deepcopy(genuine_public_period)
    axis = tuple(view['reference_and_valuation_price_sessions'])
    decisions = view['decision_sessions']; positions = {value: i for i, value in enumerate(axis)}
    expected = {}; stock_demand = [None] * 6151; cases = []
    for ordinal, (first, count, refs) in enumerate(m.EXPECTED_DEMAND.values()):
        binding = {'diagnostic_current_ticker': 'SYN' + str(ordinal), 'row_sha256': str(ordinal) * 64}
        whole = m.sha(m.canonical(binding)); expected[whole] = (first, count, refs)
        eligible = [value for value in decisions if positions[value] > positions[first]]
        assert len(eligible) == refs
        demand = {'whole_binding_sha256': whole, 'potential': True,
            'source_role': 'pending_native_original_identity_source',
            'membership_or_binding_end_used_as_price_end': False,
            'required_price_first': first, 'required_price_last': axis[-1],
            'first_eligible_decision': eligible[0], 'last_eligible_decision': eligible[-1],
            'eligible_decision_count': refs, 'eligible_decisions_sha256': m.sha(m.canonical(eligible))}
        stock_demand[ordinal] = demand
        cases.append({'case_ordinal': ordinal, 'whole_binding_sha256': whole,
            'original_case': {'aa_stock': {'binding': binding, 'binding_ordinal': ordinal}}, 'demand': demand})
    monkeypatch.setattr(m, 'EXPECTED_DEMAND', expected)
    record = {'schema': 'arv2-r327-W5-identity-necessary-demand-i-v1-private',
        'source_fingerprint': 'f' * 64, 'period': view, 'stock_demand': stock_demand,
        'fund_demand': [None] * 8, 'cases': cases, 'metadata_receipt': {}}
    return record, {'source_fingerprint': 'f' * 64}


def test_private_demand_has_all_five_whole_lifetime_and_hash_verified_references(demand_case):
    cases, axis = m.demands(*demand_case)
    assert len(axis) == 1243 and sum(len(case['required']) for case in cases) == 2286
    assert sum(len(case['references']) for case in cases) == 477
    assert all(case['required'][-1] == '2026-10-13' for case in cases)
    assert sorted(case['case_ordinal'] for case in cases) == list(range(5))


@pytest.mark.parametrize('change', ['period', 'fingerprint', 'case_ordinal', 'bool_ordinal', 'binding',
    'ticker_path', 'ticker_alias', 'demand_role', 'window_end', 'eligible_hash', 'eligible_count', 'clip_holding'])
def test_demand_refuses_changed_identity_dates_geometry_or_reference_vector(demand_case, change):
    record, summary = copy.deepcopy(demand_case)
    case = record['cases'][0]; demand = case['demand']
    if change == 'period': record['period']['evaluation_first'] = '2022-01-03'
    elif change == 'fingerprint': record['source_fingerprint'] = 'e' * 64
    elif change == 'case_ordinal': case['case_ordinal'] = 5
    elif change == 'bool_ordinal': case['case_ordinal'] = False
    elif change == 'binding': case['original_case']['aa_stock']['binding']['row_sha256'] = 'f' * 64
    elif change == 'ticker_path': case['original_case']['aa_stock']['binding']['diagnostic_current_ticker'] = '../SECRET'
    elif change == 'ticker_alias': case['original_case']['aa_stock']['binding']['diagnostic_current_ticker'] += '-DELISTED'
    elif change == 'demand_role': demand['source_role'] = 'Sharadar_RAW_full_window'
    elif change == 'window_end': demand['required_price_last'] = '2025-01-27'
    elif change == 'eligible_hash': demand['eligible_decisions_sha256'] = 'f' * 64
    elif change == 'eligible_count': demand['eligible_decision_count'] -= 1
    else: demand['membership_or_binding_end_used_as_price_end'] = True
    with pytest.raises(m.Refused): m.demands(record, summary)


def listing_raw():
    return b'Ticker,Name,First Date,Last Date\nSYN0,Synthetic,2020-01-02,2026-10-16\n'


def test_listing_schema_is_fixed_and_keeps_duplicate_symbol_candidates():
    raw = listing_raw() + b'SYN0,Other Synthetic,2000-01-03,2006-06-30\n'
    rows = m.listings(raw)
    assert len(rows) == 2 and rows[0]['Ticker'] == rows[1]['Ticker']
    assert m.listings(b'\xef\xbb\xbf' + raw) == rows
    refuse('listing', lambda: m.listings(raw.replace(b'First Date', b'Other Date')))


def test_manifest_never_exports_URL_or_local_path():
    relative = m.CURRENT_ARCHIVES[0]
    manifest = {relative[:-4]: {'path': '/SYNTHETIC-SECRET', 'url': 'SYNTHETIC-PRIVATE-URL',
        'bytes': 123, 'md5': 'a' * 32, 'ok': True, 'fetched': '2026-10-17'}}
    assert m.manifest_entry(manifest, relative) == {'byte_count': 123, 'md5': 'a' * 32}
    assert 'SYNTHETIC' not in repr(m.manifest_entry(manifest, relative))
    refuse('scope', lambda: m.manifest_entry(manifest, '../misc/API_Access.txt'))


@pytest.mark.parametrize('field,value', [('ok', False), ('bytes', True), ('bytes', m.MAX_ZIP_BYTES + 1),
    ('md5', 'bad'), ('md5', 'a' * 33)])
def test_manifest_refuses_nonaccepted_unbounded_or_bad_transport_pins(field, value):
    relative = m.DELISTED_ARCHIVES[-1]
    manifest = {relative[:-4]: {'path': 'not-used', 'url': 'not-used', 'bytes': 123,
        'md5': 'a' * 32, 'ok': True, 'fetched': '2026-10-17'}}
    manifest[relative[:-4]][field] = value
    refuse('manifest', lambda: m.manifest_entry(manifest, relative))


def test_original_held_named_file_rejects_byte_pin_symlink_and_late_replacement(tmp_path):
    source = tmp_path / 'source'; source.write_bytes(b'synthetic')
    deadline = time.monotonic() + 299
    with m.HeldFile(source, maximum=100, expected=m.pin(b'synthetic'), deadline=deadline) as held:
        assert held.read() == b'synthetic'
    with pytest.raises(m.Refused):
        with m.HeldFile(source, maximum=100, expected=m.pin(b'other'), deadline=deadline) as held: held.read()
    link = tmp_path / 'link'; link.symlink_to(source)
    with pytest.raises(OSError):
        with m.HeldFile(link, maximum=100, deadline=deadline): pass
    with pytest.raises(m.Refused):
        with m.HeldFile(source, maximum=100, deadline=deadline) as held:
            source.write_bytes(b'changed!'); held.verify()


def make_zip(path, entries):
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED) as target:
        for name, raw in entries: target.writestr(name, raw)
    raw = path.read_bytes()
    return {'byte_count': len(raw), 'md5': hashlib.md5(raw).hexdigest()}


def test_archive_fixed_MD5_before_parse_CRC_before_member_and_no_extraction(tmp_path):
    path = tmp_path / 'archive.txt'
    expected = make_zip(path, [('SYN_full_1day_UNADJUSTED.txt', b'synthetic-data')])
    with m.HeldFile(path, maximum=m.MAX_ZIP_BYTES, deadline=time.monotonic() + 299) as held:
        with m.Archive(held, expected) as archive:
            assert archive.member('missing.txt') is None
            assert archive.member('SYN_full_1day_UNADJUSTED.txt') == b'synthetic-data'
            assert archive.container_pin == m.pin(path.read_bytes())
    wrong = {**expected, 'md5': '0' * 32}
    with m.HeldFile(path, maximum=m.MAX_ZIP_BYTES, deadline=time.monotonic() + 299) as held:
        refuse('archive', lambda: m.Archive(held, wrong).__enter__())
    assert not (tmp_path / 'SYN_full_1day_UNADJUSTED.txt').exists()


def test_duplicate_or_traversal_zip_member_is_never_accepted(tmp_path):
    path = tmp_path / 'bad.zip'
    expected = make_zip(path, [('../SECRET.txt', b'synthetic')])
    with m.HeldFile(path, maximum=m.MAX_ZIP_BYTES, deadline=time.monotonic() + 299) as held:
        with m.Archive(held, expected) as archive:
            refuse('member', lambda: archive.member('../SECRET.txt'))


class FakePrices:
    def line_ending_evidence(self, raw):
        from scripts import arv2_r335_firstrate_prices_v2 as prices
        return prices.line_ending_evidence(raw)

    def parse_daily(self, raw, **kwargs):
        if raw == b'bad': raise ValueError('SYNTHETIC SECRET ROW')
        return raw

    def assess_coverage(self, series, required, *, reference_sessions=()):
        remx = series == b'2010-10-28,3,4,3,3,1'
        return {'observed_date_coverage_complete': True, 'present_required_count': len(required),
            'missing_required_count': 0, 'present_reference_count': len(reference_sessions),
            'missing_reference_count': 0, 'row_count': 4339 if remx else len(required),
            'selected_row_count': 4016 if remx else len(required), 'quarantined_row_count': 323 if remx else 0,
            'required_session_count': len(required)}

    def private_missing_sessions(self, series, required): return ()
    def apply_remx_partition(self, series, *, listing): return series


def synthetic_study(demand_case, monkeypatch, *, all_missing=False, bad=False):
    cases, axis = m.demands(*demand_case); remx_raw = b'2010-10-28,3,4,3,3,1'
    monkeypatch.setattr(m, 'REMX_PIN', m.pin(remx_raw))
    opened = []
    class FakeArchive:
        container_pin = {'byte_count': 111, 'sha256': 'a' * 64}
        def __init__(self, relative): self.relative = relative
        def member(self, name):
            if self.relative == m.REMX_ARCHIVE: return remx_raw if name == m.REMX_MEMBER else None
            if all_missing: return None
            if self.relative in m.CURRENT_ARCHIVES and name == 'SYN0_full_1day_UNADJUSTED.txt':
                return b'bad' if bad else b'2026-10-13,1,2,1,1,1'
            if self.relative == m.DELISTED_ARCHIVES[0] and name == 'SYN0-DELISTED_full_1day_UNADJUSTED.txt':
                return b'2026-10-13,1,2,1,1,1'
            return None
    def archive_for(relative): opened.append(relative); return FakeArchive(relative)
    etfs = [{'Ticker': 'REMX', 'Name': 'Synthetic', 'First Date': '2010-10-28', 'Last Date': '2026-10-16'}]
    public, private, remx = m.study(cases, axis, m.listings(listing_raw()), etfs, archive_for, FakePrices())
    return public, private, remx, opened


def test_all_candidates_and_missing_cases_preserved_without_identity_admission(demand_case, monkeypatch):
    public, private, remx, opened = synthetic_study(demand_case, monkeypatch)
    assert public[0]['candidate_count'] == 2 and public[0]['source_state'] == 'ambiguous_candidates_unadmitted'
    assert all(row['source_state'] == 'finite_missing' for row in public[1:])
    assert 'SYN0' not in repr(public) and 'SYN0' in repr(private)
    assert all(row['identity_admitted'] is row['price_input_admitted'] is False for row in public)
    assert remx['exact_partition_validated'] is True and remx['quarantined_row_count'] == 323
    assert all(value is False for key, value in private.items() if key in m.FALSE_FLAGS)
    assert all(relative in m.ARCHIVES for relative in opened)


def test_missing_candidate_does_not_drop_other_cases_or_clear_flags(demand_case, monkeypatch):
    public, _, remx, _ = synthetic_study(demand_case, monkeypatch, all_missing=True)
    assert len(public) == 5 and all(row['candidate_count'] == 0 for row in public)
    assert remx['price_input_admitted'] is False


def test_invalid_actual_candidate_is_terminal_not_skipped(demand_case, monkeypatch):
    refuse('price_parse', lambda: synthetic_study(demand_case, monkeypatch, bad=True))


def test_finite_parser_cause_and_case_are_retained_without_row_or_symbol(demand_case, monkeypatch):
    class ParserError(ValueError): pass
    class Prices(FakePrices):
        Refused = ParserError
        @staticmethod
        def finite(error): return 'row_shape'
        def parse_daily(self, raw, **kwargs): raise ParserError('SYNTHETIC SECRET ROW')
    monkeypatch.setattr(sys.modules[__name__], 'FakePrices', Prices)
    monkeypatch.setattr(m, 'ACTIVE_BINDING', m.binding(args()))
    monkeypatch.setattr(m, 'CLAIM_STATE', 'consumed')
    monkeypatch.setattr(m, 'PARSER_FAILURE_CODE', None)
    refuse('price_parse', lambda: synthetic_study(demand_case, monkeypatch))
    packet = m.failure_packet('price_parse')
    assert packet['stage'] == 'stock_candidate' and packet['case_ordinal'] == 0
    assert packet['parser_failure_code'] == 'row_shape'
    assert 'SYNTHETIC' not in repr(packet)
    assert m.validate_failure(packet, args()) == packet


def result_value(demand_case, monkeypatch):
    cases, private, remx, _ = synthetic_study(demand_case, monkeypatch)
    return {'schema': m.SCHEMA, 'complete': True, 'case_count': 5, 'cases': cases,
        'required_session_count': 2286, 'potential_reference_count': 477, 'archive_count': 8,
        'REMX': remx, 'private_pin': m.pin(m.canonical(private)),
        'retained_identity_DATA_authenticated': True, 'source_guard_normal_return': True,
        'retained_identity_receipt_sha256': 'f' * 64, **m.FALSE_FLAGS}


def test_actual_exit_and_external_report_pin_are_both_mandatory(demand_case, monkeypatch):
    result = result_value(demand_case, monkeypatch)
    report = {'binding': m.binding(args()), 'result': result}
    envelope = {**report, 'report_pin': m.pin(m.canonical(report))}
    raw = m.canonical(envelope) + b'\n'
    assert m.validate_envelope(raw, 0, args()) == envelope
    for actual in (None, True, 2, -9): refuse('child_failure', lambda: m.validate_envelope(raw, actual, args()))
    envelope['report_pin']['sha256'] = '0' * 64
    refuse('output', lambda: m.validate_envelope(m.canonical(envelope) + b'\n', 0, args()))


def test_observed_child_two_preserves_authenticated_failure_not_success(monkeypatch):
    monkeypatch.setattr(m, 'ACTIVE_BINDING', m.binding(args()))
    monkeypatch.setattr(m, 'CLAIM_STATE', 'consumed')
    monkeypatch.setattr(m, 'FAILURE_STAGE', 'stock_candidate')
    monkeypatch.setattr(m, 'FAILURE_CASE', 3)
    monkeypatch.setattr(m, 'PARSER_FAILURE_CODE', 'row_shape')
    failure = m.failure_packet('price_parse'); child_raw = m.canonical(failure) + b'\n'
    parent = {'binding': m.binding(args()), 'actual_child_exit': 2, 'output_authenticated': True,
        'child_stdout_pin': m.pin(child_raw), 'child_stderr_byte_count': 0, 'failure': failure}
    value = m.validate_parent_output(m.canonical(parent) + b'\n', 2, args())
    assert value['accepted'] is False and value['output_authenticated'] is True
    assert value['actual_child_exit'] == 2 and value['failure']['failure_code'] == 'price_parse'
    assert value['failure']['parser_failure_code'] == 'row_shape'
    refuse('output', lambda: m.validate_parent_output(m.canonical(parent), 0, args()))
    for actual in (None, True, -9): refuse('output', lambda: m.validate_parent_output(m.canonical(parent), actual, args()))
    parent['failure']['failure_code'] = 'SYNTHETIC UNKNOWN ERROR'
    parent['child_stdout_pin'] = m.pin(m.canonical(parent['failure']) + b'\n')
    refuse('output', lambda: m.validate_parent_output(m.canonical(parent) + b'\n', 2, args()))


@pytest.mark.parametrize('change', ['flag', 'count', 'case_count', 'case_bool', 'sum', 'candidate_state',
    'candidate_complete', 'negative', 'remx_prefix', 'remx_missing', 'remx_bool_count', 'remx_int_flag', 'guard_return', 'extra'])
def test_result_refuses_invented_readiness_counts_and_partition(demand_case, monkeypatch, change):
    value = result_value(demand_case, monkeypatch)
    if change == 'flag': value['identity_admitted'] = True
    elif change == 'count': value['required_session_count'] = 2285
    elif change == 'case_count': value['case_count'] = 4
    elif change == 'case_bool': value['cases'][0]['case_ordinal'] = False
    elif change == 'sum': value['cases'][0]['required_session_count'] -= 1
    elif change == 'candidate_state': value['cases'][0]['source_state'] = 'one_candidate_unadmitted'
    elif change == 'candidate_complete': value['cases'][0]['date_complete_candidate_count'] = 0
    elif change == 'negative': value['cases'][0]['candidate_counts'][0]['present_required_count'] = -1
    elif change == 'remx_prefix': value['REMX']['quarantined_row_count'] = 0
    elif change == 'remx_missing': value['REMX']['missing_required_count'] = 1
    elif change == 'remx_bool_count': value['REMX']['missing_required_count'] = False
    elif change == 'remx_int_flag': value['REMX']['exact_partition_validated'] = 1
    elif change == 'guard_return': value['source_guard_normal_return'] = False
    else: value['private_row'] = 'SYNTHETIC SECRET'
    with pytest.raises(m.Refused): m.validate_result(value)


class Security:
    @staticmethod
    def snapshot(fd): return {'acl_empty': True, 'xattrs': {}}


def fixture_control(tmp_path, monkeypatch):
    root = tmp_path / 'root'; root.mkdir(mode=0o755); root.chmod(0o755)
    artifacts = root / 'artifacts'; artifacts.mkdir(mode=0o700)
    lane = artifacts / 'analyst_revisions_v2'; lane.mkdir(mode=0o700)
    monkeypatch.setattr(m, 'ROOT', root)
    monkeypatch.setattr(m, 'CONTROL', lane / 'firstrate/R335-A')
    return lane


def test_one_exclusive_claim_all_outputs_original_FDs_and_no_retry(tmp_path, monkeypatch):
    fixture_control(tmp_path, monkeypatch)
    with m.Store(Security) as store:
        store.write('claim.json', b'{"synthetic":true}')
        assert store.write('private-diagnosis.json', b'{}') == m.pin(b'{}')
        assert store.write('report.json', b'{}') == m.pin(b'{}')
        store.verify()
        assert all(stat_mode == 0o600 for stat_mode in [
            (m.CONTROL / name).stat().st_mode & 0o777 for name in ('claim.json', 'private-diagnosis.json', 'report.json')])
    refuse('claim_spent', lambda: m.Store(Security).__enter__())
    assert (m.CONTROL / 'claim.json').read_bytes() == b'{"synthetic":true}'


def test_symlink_output_ancestor_refuses_before_any_own_claim(tmp_path, monkeypatch):
    lane = fixture_control(tmp_path, monkeypatch)
    other = tmp_path / 'other'; other.mkdir()
    (lane / 'firstrate').symlink_to(other, target_is_directory=True)
    with pytest.raises((OSError, m.Refused)): m.Store(Security).__enter__()
    assert not (other / 'R335-A').exists()


def test_late_output_mutation_is_refused_and_evidence_retained(tmp_path, monkeypatch):
    fixture_control(tmp_path, monkeypatch)
    with pytest.raises(m.Refused):
        with m.Store(Security) as store:
            store.write('claim.json', b'{}')
            (m.CONTROL / 'claim.json').write_bytes(b'changed')
            store.verify()
    assert (m.CONTROL / 'claim.json').read_bytes() == b'changed'


def test_unexpected_owned_control_leaf_is_not_absorbed_by_later_own_write(tmp_path, monkeypatch):
    fixture_control(tmp_path, monkeypatch)
    with pytest.raises(m.Refused):
        with m.Store(Security) as store:
            store.write('claim.json', b'{}')
            (m.CONTROL / 'unexpected').write_bytes(b'synthetic')
            refuse('control', lambda: store.write('report.json', b'{}'))
    assert (m.CONTROL / 'unexpected').read_bytes() == b'synthetic'
    assert not (m.CONTROL / 'report.json').exists()


def test_cli_unknown_argument_never_echoes_supplied_value():
    result = subprocess.run([sys.executable, '-I', '-B', str(m.SOURCE), 'launch', '--SYNTHETIC-SECRET-ARG'],
        cwd=m.ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5,
        env={'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'})
    assert result.returncode == 2 and not result.stderr
    assert b'SYNTHETIC-SECRET' not in result.stdout
    assert json.loads(result.stdout)['failure_code'] == 'arguments'


def test_real_offline_validator_keeps_actual_failure_exit_and_finite_reason(monkeypatch):
    monkeypatch.setattr(m, 'ACTIVE_BINDING', m.binding(args()))
    monkeypatch.setattr(m, 'CLAIM_STATE', 'consumed')
    monkeypatch.setattr(m, 'FAILURE_STAGE', 'stock_candidate')
    monkeypatch.setattr(m, 'FAILURE_CASE', 1)
    monkeypatch.setattr(m, 'PARSER_FAILURE_CODE', 'row_shape')
    failure = m.failure_packet('price_parse')
    parent = {'binding': m.binding(args()), 'actual_child_exit': 2, 'output_authenticated': True,
        'child_stdout_pin': m.pin(m.canonical(failure) + b'\n'), 'child_stderr_byte_count': 0, 'failure': failure}
    result = subprocess.run([sys.executable, '-I', '-B', str(m.SOURCE), 'validate',
        '--expected-head', args().expected_head, '--caller-sha256', args().caller_sha256,
        '--profile-sha256', args().profile_sha256, '--actual-parent-exit', '2'],
        cwd=m.ROOT, input=m.canonical(parent) + b'\n', stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=5,
        env={'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'})
    assert result.returncode == 2 and not result.stderr
    value = json.loads(result.stdout)
    assert value['accepted'] is False and value['output_authenticated'] is True
    assert value['actual_child_exit'] == 2 and value['failure']['failure_code'] == 'price_parse'
    assert value['failure']['parser_failure_code'] == 'row_shape'


def test_success_retains_count_only_unterminated_complete_record_evidence(demand_case, monkeypatch):
    public, private, remx, _ = synthetic_study(demand_case, monkeypatch)
    evidence = public[0]['candidate_counts'][0]['lexical_evidence']
    assert evidence['ends_LF'] is False and evidence['unterminated_final_record'] is True
    assert evidence['complete_final_record'] is evidence['line_endings_consistent'] is True
    assert evidence['final_record_field_count'] == 6 and evidence['physical_record_count'] == 1
    assert 'SYN0' not in repr(evidence) and '2026-10-13' not in repr(evidence)
    assert private['cases'][0]['candidates'][0]['lexical_evidence'] == evidence
    assert remx['lexical_evidence']['complete_final_record'] is True


@pytest.mark.parametrize('change', ['extra', 'schema', 'bool_count', 'int_flag', 'negative',
    'CRLF_more_than_LF', 'false_physical_count', 'false_termination', 'missing_field_count'])
def test_lexical_payload_is_exact_and_cannot_export_a_row(change):
    from scripts import arv2_r335_firstrate_prices_v2 as prices
    value = prices.line_ending_evidence(b'2026-10-13,1,2,1,1,1')
    if change == 'extra': value['raw_row'] = 'SYNTHETIC SECRET'
    elif change == 'schema': value['schema'] = 'unknown'
    elif change == 'bool_count': value['LF_count'] = False
    elif change == 'int_flag': value['ends_LF'] = 0
    elif change == 'negative': value['bare_CR_count'] = -1
    elif change == 'CRLF_more_than_LF': value['CRLF_count'] = 1
    elif change == 'false_physical_count': value['physical_record_count'] = 0
    elif change == 'false_termination': value['unterminated_final_record'] = False
    else: value['final_record_field_count'] = 5
    refuse('output', lambda: m.validate_lexical(value))


def test_mixed_line_endings_remain_failure_with_current_evidence(demand_case, monkeypatch):
    from scripts import arv2_r335_firstrate_prices_v2 as prices
    cases, axis = m.demands(*demand_case)
    raw = b'2026-10-12,1,2,1,1,1\n2026-10-13,1,2,1,1,1\r\n'
    class Archive:
        container_pin = {'byte_count': 111, 'sha256': 'a' * 64}
        def member(self, name):
            return raw if name == 'SYN0_full_1day_UNADJUSTED.txt' else None
    monkeypatch.setattr(m, 'ACTIVE_BINDING', m.binding(args()))
    monkeypatch.setattr(m, 'CLAIM_STATE', 'consumed')
    monkeypatch.setattr(m, 'PARSER_FAILURE_CODE', None)
    refuse('price_parse', lambda: m.study(cases, axis, [], [], lambda _: Archive(), prices))
    packet = m.failure_packet('price_parse')
    assert packet['parser_failure_code'] == 'line_ending' and packet['case_ordinal'] == 0
    assert packet['lexical_evidence']['line_endings_consistent'] is False
    assert packet['lexical_evidence']['LF_count'] == 2 and packet['lexical_evidence']['CRLF_count'] == 1
    assert packet['lexical_evidence']['ends_CRLF'] is True
    assert m.validate_failure(packet, args()) == packet


@pytest.mark.parametrize('where', ['candidate', 'REMX'])
def test_success_refuses_lexical_metadata_that_does_not_match_complete_records(demand_case, monkeypatch, where):
    value = result_value(demand_case, monkeypatch)
    evidence = value['cases'][0]['candidate_counts'][0]['lexical_evidence'] if where == 'candidate' else value['REMX']['lexical_evidence']
    evidence['complete_final_record'] = False
    refuse('output', lambda: m.validate_result(value))


def test_bounded_inverse_semantic_transform_preserves_every_other_A_protocol_body():
    """Only declared source bindings and lexical evidence may differ from A.

    This is an AST inverse proof, not byte equality or arbitrary diff reversal.
    New lexical helpers are separately checked for their strictly pure calls.
    """
    old_path = m.ROOT / 'scripts/inspect_arv2_r335_firstrate_coverage.py'
    old_raw = old_path.read_bytes()
    assert hashlib.sha256(old_raw).hexdigest() == '4f600f3633b9fda42a7b32abf6d9f8ef35a8b9c000ba5c14631c1e7011b20197'
    old, new = ast.parse(old_raw), ast.parse(m.SOURCE.read_bytes())
    versions = {
        'One new complete-final-record FirstRate observation, never price admission.':
            'One new offline FirstRate coverage observation, never price admission.',
        'scripts/inspect_arv2_r335_firstrate_coverage_v2.py': 'scripts/inspect_arv2_r335_firstrate_coverage.py',
        'artifacts/analyst_revisions_v2/firstrate/R335-20261103-B': 'artifacts/analyst_revisions_v2/firstrate/R335-20261103-A',
        'arv2-r335-offline-firstrate-coverage-v2': 'arv2-r335-offline-firstrate-coverage-v1',
        'scripts/arv2_r335_firstrate_prices_v2.py': 'scripts/arv2_r335_firstrate_prices.py',
        'a0c8d235036d37c95af47d1719c69405b0c2e979d92fcb32070ef42ac672cc5e':
            '53a136d12f5e2979cfbec6395e57923078a398316fb6bab0678fb50db79d3868',
        'arv2_r335_firstrate_prices_v2': 'arv2_r335_firstrate_prices',
    }
    additions = {'lexical_evidence', 'line_ending_delta'}
    class Inverse(ast.NodeTransformer):
        def visit_Constant(self, node):
            if type(node.value) is str:
                for current, prior in versions.items():
                    if node.value == current or node.value.startswith(current + '\n'):
                        node.value = prior + node.value[len(current):]
            return node
        def visit_FunctionDef(self, node):
            if node.name in ('validate_lexical', 'attach_lexical'): return None
            return self.generic_visit(node)
        def visit_Global(self, node):
            node.names = [name for name in node.names if name != 'LEXICAL_EVIDENCE']; return node
        def visit_Assign(self, node):
            if any(isinstance(target, ast.Name) and target.id == 'LEXICAL_EVIDENCE' for target in node.targets): return None
            return self.generic_visit(node)
        def visit_Expr(self, node):
            value = node.value
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
                if value.func.id in ('validate_lexical', 'attach_lexical'): return None
                if value.func.id == 'require' and value.args and any(isinstance(item, ast.Subscript)
                    and isinstance(item.slice, ast.Constant) and item.slice.value == 'complete_final_record'
                    for item in ast.walk(value.args[0])): return None
            return self.generic_visit(node)
        def visit_Dict(self, node):
            pairs = [(key, value) for key, value in zip(node.keys, node.values, strict=True)
                if not isinstance(key, ast.Constant) or key.value not in additions]
            node.keys, node.values = [item[0] for item in pairs], [item[1] for item in pairs]
            return self.generic_visit(node)
        def visit_Set(self, node):
            node.elts = [item for item in node.elts if not isinstance(item, ast.Constant) or item.value not in additions]
            return self.generic_visit(node)
        def visit_GeneratorExp(self, node):
            if len(node.generators) == 1:
                comp = node.generators[0]
                if isinstance(comp.target, ast.Tuple) and [item.id for item in comp.target.elts] == ['key', 'count'] \
                        and isinstance(comp.iter, ast.Call) and isinstance(comp.iter.func, ast.Attribute) \
                        and isinstance(comp.iter.func.value, ast.Name) and comp.iter.func.value.id == 'item' \
                        and comp.iter.func.attr == 'items':
                    assert ast.unparse(comp.ifs[0]) == "key != 'lexical_evidence'"
                    comp.target = ast.Name(id='count', ctx=ast.Store()); comp.iter.func.attr = 'values'; comp.ifs = []
            return self.generic_visit(node)
        def visit_DictComp(self, node):
            if ast.unparse(node) == "{key: item for key, item in value['REMX'].items() if key != 'lexical_evidence'}":
                return ast.parse("value['REMX']", mode='eval').body
            return self.generic_visit(node)
    inverse = Inverse().visit(copy.deepcopy(new))
    assert ast.dump(inverse, include_attributes=False) == ast.dump(old, include_attributes=False)
    for function in (node for node in new.body if isinstance(node, ast.FunctionDef)
            and node.name in ('validate_lexical', 'attach_lexical')):
        calls = {node.func.id for node in ast.walk(function) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        allowed = {'require', 'type', 'set', 'all', 'len', 'zip'}
        if function.name == 'attach_lexical': allowed.add('validate_lexical')
        assert calls <= allowed
        assert not any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(function))
