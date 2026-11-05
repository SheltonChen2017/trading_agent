"""Synthetic public hierarchy responses only; no provider or original DATA."""
import copy
import pickle
import time

import pytest

from scripts import arv2_r327_public_figi_hierarchy as m


def figi(number):
    seed = 'BBG' + str(number).zfill(8)
    values = [int(char, 36) * (1 if index % 2 == 0 else 2) for index, char in enumerate(seed)]
    return seed + str((10 - sum(value // 10 + value % 10 for value in values) % 10) % 10)


def row(claim, *, composite=None, share=None, exchange='US', market='Equity'):
    return {'figi': claim, 'compositeFIGI': claim if composite is None else composite,
        'shareClassFIGI': figi(1000) if share is None else share, 'exchCode': exchange,
        'marketSector': market, 'name': 'PUBLIC SYNTHETIC', 'ticker': 'SYNTHETIC',
        'securityType': 'Common Stock', 'securityType2': 'Common Stock', 'securityDescription': 'SYNTHETIC'}


@pytest.fixture
def case():
    claims = [figi(index) for index in range(1, 10)]
    composite, share = figi(101), figi(1001)
    jobs = [{'data': [row(claim, share=figi(1100 + index))]} for index, claim in enumerate(claims)]
    jobs[0] = {'data': [row(claims[0], composite=composite, share=share, exchange='UN')]}
    jobs[1] = {'data': [row(claims[1], composite=composite, share=share, exchange='UW')]}
    return {'claims': claims, 'response': jobs, 'composite': composite, 'share': share}


def first(case, *, response=None, status=200, raw=None):
    claims = case['claims']
    summary, private = m.analyze_phase1(claims, request_raw=m.canonical(m.mapping_jobs(claims)),
        response_raw=(m.canonical(case['response'] if response is None else response) if raw is None else raw)
            if status == 200 else raw, http_status=status)
    return summary, private.private_record()


def second(phase1, *, response=None, exchange='US', share=None, status=200):
    jobs = m.phase2_jobs(phase1)
    rows = [{'data': [row(job['idValue'], share=share, exchange=exchange)]} for job in jobs] if response is None else response
    summary, private = m.analyze_phase2(phase1, request_raw=m.canonical(jobs),
        response_raw=m.canonical(rows) if status == 200 else None, http_status=status)
    return summary, private.private_record()


def refused(code, operation):
    with pytest.raises(m.Refused) as caught: operation()
    assert m.finite(caught.value) == code


def test_phase1_venue_rows_derive_one_sorted_new_composite_then_same_US_witness_can_be_observed(case):
    one = first(case)
    assert one[0]['state_counts']['unique_equity_hierarchy'] == 2
    assert one[0]['derived_composite_count'] == 1
    assert m.phase2_jobs(one) == [{'idType': 'ID_BB_GLOBAL', 'idValue': case['composite'], 'includeUnlistedEquities': True}]
    two = second(one, share=case['share'])
    observed = m.corroborate(*case['claims'][:2], phase1=one, phase2=two)
    assert observed['observation'] == 'same_validated_US_composite_and_share_class_observed'
    assert observed['same_nonnull_composite'] is observed['same_nonnull_share_class'] is True
    assert observed['validated_US_witness'] is observed['all_input_jobs_unambiguous'] is True
    assert observed['witness_phase'] == 2
    assert all(observed[key] is False for key in m.FALSE_FLAGS)
    assert two[0]['derived_composite_count'] == 0


def test_already_requested_phase1_US_composite_is_the_witness_without_a_second_call(case):
    witness = case['claims'][2]
    for index in (0, 1): case['response'][index]['data'][0]['compositeFIGI'] = witness
    case['response'][2] = {'data': [row(witness, share=case['share'])]}
    one = first(case)
    assert m.phase2_jobs(one) == []
    observed = m.corroborate(*case['claims'][:2], phase1=one)
    assert observed['witness_phase'] == 1 and observed['validated_US_witness'] is True
    refused('phase2_not_required', lambda: m.analyze_phase2(one,
        request_raw=b'[]', response_raw=b'[]', http_status=200))


def test_original_listing_exchange_may_be_nonUS_but_cannot_replace_a_US_composite_witness(case):
    one = first(case)
    two = second(one, exchange='CA', share=case['share'])
    observed = m.corroborate(*case['claims'][:2], phase1=one, phase2=two)
    assert observed['observation'] == 'unresolved_US_composite_witness_missing'
    assert observed['validated_US_witness'] is False


def test_matching_share_class_alone_does_not_clear_distinct_composites(case):
    case['response'][1]['data'][0]['compositeFIGI'] = figi(102)
    one = first(case); two = second(one, share=case['share'])
    observed = m.corroborate(*case['claims'][:2], phase1=one, phase2=two)
    assert observed['observation'] == 'unresolved_share_class_only'
    assert observed['same_nonnull_share_class'] is True and observed['same_nonnull_composite'] is False


@pytest.mark.parametrize('where', ['input', 'witness'])
def test_same_composite_with_different_share_class_never_corroborates(case, where):
    if where == 'input': case['response'][1]['data'][0]['shareClassFIGI'] = figi(2001)
    one = first(case)
    two = second(one, share=figi(2002) if where == 'witness' else case['share'])
    observed = m.corroborate(*case['claims'][:2], phase1=one, phase2=two)
    assert observed['observation'] == ('unresolved_share_class_disagreement' if where == 'input'
        else 'unresolved_witness_share_class_disagreement')
    assert observed['validated_US_witness'] is False


def test_derived_phase_is_deterministic_unique_excludes_all_initial_claims_and_stops_after_one_hop(case):
    case['response'][2] = {'data': [row(case['claims'][2], composite=figi(99), share=figi(1099), exchange='UN')]}
    one = first(case)
    assert [job['idValue'] for job in m.phase2_jobs(one)] == sorted([figi(99), case['composite']])
    replies = [{'data': [row(job['idValue'], composite=figi(303), exchange='CA')]} for job in m.phase2_jobs(one)]
    two = second(one, response=replies)
    assert two[0]['derived_composite_count'] == 0
    refused('phase_binding', lambda: m.phase2_jobs(two))


def test_missing_required_second_phase_is_explicit_even_if_other_phase1_pairs_have_a_witness(case):
    observed = m.corroborate(*case['claims'][:2], phase1=first(case))
    assert observed['observation'] == 'unresolved_phase2_missing'
    assert observed['all_input_jobs_unambiguous'] is False


@pytest.mark.parametrize('replacement,state', [({'warning': 'No identifier found.'}, 'no_match'),
    ({'error': 'provider unavailable'}, 'job_error_unknown'), ({'warning': 'unknown warning'}, 'job_warning_unknown'),
    ({'data': []}, 'no_match'), ({'data': [], 'extra': 'unknown'}, 'job_schema_invalid'),
    ('wrong-job-type', 'job_schema_invalid')])
def test_every_job_is_retained_and_no_favourable_subset_can_clear_an_unrelated_unresolved_job(case, replacement, state):
    case['response'][-1] = replacement
    one = first(case); assert one[0]['jobs'][-1]['state'] == state
    assert one[1]['response_jobs'][-1] == replacement
    two = second(one, share=case['share'])
    observed = m.corroborate(*case['claims'][:2], phase1=one, phase2=two)
    assert observed['observation'] == 'unresolved_input_jobs' and state in observed['unresolved_job_states']
    assert observed['validated_US_witness'] is False


@pytest.mark.parametrize('change,state', [('metadata', 'metadata_unavailable'), ('identity', 'identity_mismatch'),
    ('market', 'instrument_scope_unknown'), ('missing_composite', 'composite_or_share_class_missing'),
    ('missing_share', 'composite_or_share_class_missing'), ('US_level', 'US_hierarchy_inconsistent'),
    ('bad_composite_checksum', 'result_schema_invalid'), ('bad_share_checksum', 'result_schema_invalid'),
    ('unknown_field', 'result_schema_invalid')])
def test_hierarchy_null_metadata_scope_and_checksum_failures_are_named_not_substituted(case, change, state):
    result = case['response'][0]['data'][0]
    if change == 'metadata': case['response'][0] = {'data': [{'figi': case['claims'][0], 'metadata': 'Metadata N/A'}]}
    elif change == 'identity': result['figi'] = figi(500)
    elif change == 'market': result['marketSector'] = 'Corp'
    elif change == 'missing_composite': result['compositeFIGI'] = None
    elif change == 'missing_share': result['shareClassFIGI'] = None
    elif change == 'US_level': result['exchCode'] = 'US'
    elif change == 'bad_composite_checksum': result['compositeFIGI'] = result['compositeFIGI'][:-1] + '9'
    elif change == 'bad_share_checksum': result['shareClassFIGI'] = result['shareClassFIGI'][:-1] + '9'
    else: result['not_documented'] = 'unexpected'
    one = first(case)
    assert one[0]['jobs'][0]['state'] == state
    assert one[0]['all_jobs_unambiguous'] is False


def test_all_result_rows_are_validated_and_identical_duplicate_rows_remain_ambiguous(case):
    case['response'][0]['data'].append(copy.deepcopy(case['response'][0]['data'][0]))
    one = first(case)
    assert one[0]['jobs'][0]['state'] == 'ambiguous_results'
    assert one[0]['jobs'][0]['result_count'] == 2
    case['response'][0]['data'][-1]['shareClassFIGI'] = 'not-a-FIGI'
    one = first(case)
    assert one[0]['jobs'][0]['state'] == 'result_schema_invalid'
    assert one[0]['jobs'][0]['invalid_result_count'] == 1
    assert len(one[1]['response_jobs'][0]['data']) == 2


def test_unrelated_ambiguity_vetoes_an_otherwise_matching_pair_and_US_witness(case):
    case['response'][-1]['data'].append(copy.deepcopy(case['response'][-1]['data'][0]))
    one = first(case); two = second(one, share=case['share'])
    observed = m.corroborate(*case['claims'][:2], phase1=one, phase2=two)
    assert observed['observation'] == 'unresolved_input_jobs'
    assert observed['unresolved_job_states'] == ['ambiguous_results']
    assert observed['validated_US_witness'] is False


def test_failed_second_status_cannot_be_replaced_by_first_phase_share_class_agreement(case):
    one = first(case); two = second(one, status=403)
    observed = m.corroborate(*case['claims'][:2], phase1=one, phase2=two)
    assert observed['observation'] == 'unresolved_input_jobs'
    assert observed['unresolved_job_states'] == ['not_parsed_http_status']
    assert observed['validated_US_witness'] is False


def test_documented_maximum15000_results_is_inclusive_and_no_first_row_is_selected(case):
    case['response'][0] = {'data': [{'figi': case['claims'][0]}] * 15000}
    one = first(case)
    assert one[0]['jobs'][0]['result_count'] == 15000
    assert one[0]['jobs'][0]['state'] == 'ambiguous_results'
    case['response'][0]['data'].append({'figi': case['claims'][0]})
    refused('result_bound', lambda: first(case))


def test_non200_requires_unread_body_and_derives_no_followup(case, monkeypatch):
    monkeypatch.setattr(m, '_decode', lambda *_: pytest.fail('failed HTTP body parsed'))
    one = first(case, status=429)
    assert one[0]['response_pin'] is None and one[0]['state_counts'] == {'not_parsed_http_status': 9}
    assert one[0]['derived_composite_count'] == 0
    refused('failed_body', lambda: first(case, status=403, raw=b'private failed response'))


@pytest.mark.parametrize('raw,code', [(b'[]', 'job_count'), (b'{}', 'job_count'), (b'\xff', 'json'),
    (b'[{"data":[],"data":[]}]', 'json'), (b'[{"extra":1.5}]', 'json'),
    (b'[{"extra":NaN}]', 'json'), (b'[' * 9 + b']' * 9, 'json_bound')])
def test_strict_UTF8_duplicate_key_float_count_and_depth_bounds(case, raw, code):
    refused(code, lambda: first(case, raw=raw))


def test_response_byte_bound_and_http_status_exact_integer_are_mandatory(case):
    refused('body', lambda: first(case, raw=b'x' * (m.MAX_BODY + 1)))
    refused('http_status', lambda: m.analyze_phase1(case['claims'], request_raw=m.canonical(m.mapping_jobs(case['claims'])),
        response_raw=None, http_status=True))


def test_claims_and_exact_requests_do_not_accept_extra_repeated_reordered_or_filtered_jobs(case):
    refused('claims', lambda: m.mapping_jobs(case['claims'][:-1]))
    refused('claims', lambda: m.mapping_jobs([*case['claims'][:-1], case['claims'][0]]))
    jobs = m.mapping_jobs(case['claims']); jobs[0]['exchCode'] = 'US'
    refused('request', lambda: m.analyze_phase1(case['claims'], request_raw=m.canonical(jobs),
        response_raw=m.canonical(case['response']), http_status=200))
    one = first(case); jobs = m.phase2_jobs(one); jobs[0]['idValue'] = case['claims'][0]
    refused('request', lambda: m.analyze_phase2(one, request_raw=m.canonical(jobs), response_raw=b'[]', http_status=200))


def test_phase2_predecessor_and_exact_derived_claim_list_are_bound(case):
    one = first(case); two = second(one, share=case['share'])
    bad_summary, bad_record = copy.deepcopy(two)
    bad_summary['phase1_summary_sha256'] = bad_record['phase1_summary_sha256'] = 'a' * 64
    bad_summary['private_frame_pin'] = m.pin(m.canonical(bad_record))
    refused('phase_binding', lambda: m.corroborate(*case['claims'][:2], phase1=one, phase2=(bad_summary, bad_record)))
    refused('pair', lambda: m.corroborate(figi(999), case['claims'][1], phase1=one, phase2=two))


def test_private_record_revalidation_recomputes_all_rows_claims_derivations_and_hashes(case):
    one = first(case); checked = m.validate_private_record(one[1], expected_summary=one[0])
    assert checked == one[1] and checked is not one[1]
    changed = copy.deepcopy(one[1]); changed['response_jobs'][0]['data'][0]['compositeFIGI'] = figi(999)
    refused('private_record', lambda: m.validate_private_record(changed, expected_summary=one[0]))
    changed = copy.deepcopy(one[0]); changed['derived_composite_count'] = 9
    refused('private_record', lambda: m.validate_private_record(one[1], expected_summary=changed))


def test_private_repr_pickle_copy_and_public_metadata_never_disclose_identifiers(case):
    summary, private = m.analyze_phase1(case['claims'], request_raw=m.canonical(m.mapping_jobs(case['claims'])),
        response_raw=m.canonical(case['response']), http_status=200)
    assert 'BBG' not in repr(private) and b'BBG' not in m.canonical(summary)
    with pytest.raises(TypeError): pickle.dumps(private)
    with pytest.raises(TypeError): private._raw = b'changed'
    copied = private.private_record(); copied['claims'][0] = figi(999)
    assert private.private_record()['claims'][0] == case['claims'][0]


def test_summary_and_pair_metadata_are_closed_and_reject_authority_claims(case):
    one = first(case); two = second(one, share=case['share'])
    observed = m.corroborate(*case['claims'][:2], phase1=one, phase2=two)
    bad = copy.deepcopy(observed); bad['alias_or_route_created'] = True
    refused('summary', lambda: m.validate_observation(bad))
    bad = copy.deepcopy(observed); bad['unresolved_job_states'] = [{}]
    refused('summary', lambda: m.validate_observation(bad))
    bad = copy.deepcopy(one[0]); bad['raw_figis'] = case['claims']
    refused('summary', lambda: m.validate_summary(bad))
    bad = copy.deepcopy(one[0]); bad['derived_composite_count'] = True
    refused('summary', lambda: m.validate_summary(bad))


def test_deadline_and_profile_limits_are_explicit_without_acquisition_authority(case):
    refused('deadline', lambda: m.analyze_phase1(case['claims'], request_raw=b'[]', response_raw=None,
        http_status=200, deadline=time.monotonic() - 1))
    profile = m.profile_record()
    assert profile['initial_jobs'] == 9 and profile['maximum_phases'] == 2
    assert profile['maximum_results_per_job_inclusive'] == 15000
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
