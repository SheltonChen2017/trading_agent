"""Public synthetic identifiers only; native-denied pure mapping checks."""
import copy
import json
import pickle
import time

import pytest

from scripts import arv2_r298_public_figi_corroboration as m

A, B, C, D, SHARE = ('BBG000BLNNH6', 'BBG000BLNQ16', 'BBG000NRMJ71', 'BBG000NHN466', 'BBG001S5S399')


_SELF_COMPOSITE = object()


def row(figi, *, composite=_SELF_COMPOSITE, share=SHARE, **changes):
    if composite is _SELF_COMPOSITE: composite = figi
    result = {'figi': figi, 'securityType': 'Common Stock', 'marketSector': 'Equity', 'ticker': 'SYNTH',
        'name': 'Synthetic caf\u00e9 issuer', 'exchCode': 'US', 'shareClassFIGI': share,
        'compositeFIGI': composite, 'securityType2': 'Common Stock', 'securityDescription': 'Synthetic security'}
    result.update(changes); return result


def analyze(response=None, *, claims=(A, B), status=200):
    if response is None and status == 200: response = [{'data': [row(value)]} for value in claims]
    return m.analyze_batch(claims, request_raw=m.canonical(m.mapping_jobs(claims)),
        response_raw=None if status != 200 else m.canonical(response), http_status=status)


def compare(response=None, *, status=200):
    summary, private = analyze(response, status=status)
    return m.corroborate(A, B, batches=[(summary, private.private_record())])


def same_claim():
    summary, private = analyze(claims=(A,))
    return m.corroborate(A, A, batches=[(summary, private.private_record())])


def refused(code, call):
    with pytest.raises(m.Refused) as error: call()
    assert m.finite(error.value) == code


def test_fixed_jobs_export_only_public_FIGIs_and_include_unlisted_from_first_request():
    assert m.mapping_jobs([A, B]) == [{'idType': 'ID_BB_GLOBAL', 'idValue': value,
        'includeUnlistedEquities': True} for value in (A, B)]
    assert not any(text in m.canonical(m.mapping_jobs([A])) for text in (b'CUSIP', b'permaticker', b'ticker', b'name'))


@pytest.mark.parametrize('bad', ['BBG000BLNNH7', 'BBG000BLNNHA', 'BBG000ALNNH6', 'ABG000BLNNH6', '123456789012'])
def test_claimed_and_response_hierarchy_FIGIs_require_canonical_alphabet_and_checksum(bad):
    refused('claims', lambda: m.mapping_jobs([bad]))
    for field in ('figi', 'compositeFIGI', 'shareClassFIGI'):
        jobs = [{'data': [row(A)]}, {'data': [row(B)]}]
        jobs[0]['data'][0][field] = bad
        refused('result_shape', lambda: analyze(jobs))


def test_canonical_checksum_shape_is_not_an_invented_BBG_only_prefix_rule():
    assert m._figi('KKG000000007') is True
    assert m._figi('KKG000000008') is False


def test_same_current_US_composite_requires_both_nonnull_groups_and_grants_no_route_acceptance():
    summary, private = analyze(claims=(A,))
    result = m.corroborate(A, A, batches=[(summary, private.private_record())])
    assert result['observation'] == 'same_current_us_composite_observed'
    assert result['same_nonnull_US_composite'] is result['same_nonnull_share_class'] is True
    assert all(result[key] is False for key in m.FALSE_FLAGS)
    assert m.validate_summary(summary) == summary
    assert m.validate_private_record(private.private_record(), expected_summary=summary) == private.private_record()
    for text in (A, B, C, SHARE, 'SYNTH', 'Synthetic', 'caf'):
        assert text.encode() not in m.canonical(summary) + m.canonical(result)


@pytest.mark.parametrize('share,observation', [
    (SHARE, 'unresolved_share_class_only'), (D, 'unresolved_composite_disagreement')])
def test_shared_share_class_never_clears_distinct_claimed_US_composites(share, observation):
    result = compare([{'data': [row(A)]}, {'data': [row(B, share=share)]}])
    assert result['observation'] == observation and result['route_acceptance_granted'] is False


@pytest.mark.parametrize('claims,rows', [
    ((A,), [row(A, composite=C)]),
    ((A, B), [row(A, composite=C), row(B, composite=C)]),
    ((A, B), [row(A), row(B, composite=A)]),
])
def test_US_instrument_different_from_its_composite_is_hierarchy_unresolved(claims, rows):
    summary, private = analyze([{'data': [value]} for value in rows], claims=claims)
    assert summary['state_counts']['hierarchy_level_inconsistent'] >= 1
    result = m.corroborate(claims[0], claims[-1], batches=[(summary, private.private_record())])
    assert result['observation'] == 'unresolved_hierarchy_level'
    assert result['unresolved_causes'] == ['unresolved_hierarchy_level']
    assert result['same_nonnull_US_composite'] is result['same_nonnull_share_class'] is None
    assert all(result[key] is False for key in m.FALSE_FLAGS)
    assert m.validate_private_record(private.private_record(), expected_summary=summary) == private.private_record()


@pytest.mark.parametrize('job,observation', [
    ({'data': []}, 'unresolved_no_match'), ({'warning': 'No identifier found.'}, 'unresolved_no_match'),
    ({'error': 'No identifier found.'}, 'unresolved_no_match'),
    ({'error': 'Synthetic provider error'}, 'unresolved_job_error'),
    ({'warning': 'Synthetic warning'}, 'unresolved_job_error'),
    ({'data': [{'figi': A, 'metadata': 'Metadata N/A'}]}, 'unresolved_metadata'),
    ({'data': [row(A, composite=None)]}, 'unresolved_composite_or_share_class_missing'),
    ({'data': [row(A, share=None)]}, 'unresolved_composite_or_share_class_missing'),
    ({'data': [row(A, exchCode='UW')]}, 'unresolved_instrument_scope'),
    ({'data': [row(A, marketSector='Corp')]}, 'unresolved_instrument_scope')])
def test_complete_HTTP200_errors_warnings_unlisted_unknown_and_nullable_metadata_remain_unresolved(job, observation):
    result = compare([job, {'data': [row(B)]}])
    assert result['observation'] == observation
    assert result['same_nonnull_US_composite'] is result['same_nonnull_share_class'] is None


@pytest.mark.parametrize('second', [row(A), row(D), row(D, composite=D), row(D, share=D)])
def test_no_first_result_or_duplicate_result_acceptance_even_when_first_is_perfect(second):
    result = compare([{'data': [row(A), second]}, {'data': [row(B)]}])
    assert result['observation'] == 'unresolved_ambiguity'


def test_job_order_and_exact_requested_instrument_binding_are_not_inferred_from_shared_group():
    result = compare([{'data': [row(B)]}, {'data': [row(A)]}])
    assert result['observation'] == 'unresolved_identity_binding'


@pytest.mark.parametrize('status', [403, 429, 500])
def test_non200_does_not_parse_failed_body_and_never_suggests_retry(status):
    summary, private = analyze(status=status)
    assert summary['response_pin'] is None and private.private_record()['response_jobs'] is None
    assert compare(status=status)['observation'] == 'unresolved_http_status'
    refused('failed_body', lambda: m.analyze_batch([A], request_raw=m.canonical(m.mapping_jobs([A])),
        response_raw=b'PRIVATE FAILED BODY', http_status=status))


@pytest.mark.parametrize('change', ['missing_job', 'extra_job', 'mixed_data_error', 'extra_job_key',
    'result_unknown_key', 'bad_figi', 'bad_composite', 'field_bound', 'surrogate'])
def test_every_job_and_result_is_checked_with_closed_bounded_shapes(change):
    jobs = [{'data': [row(A)]}, {'data': [row(B)]}]
    if change == 'missing_job': jobs.pop()
    elif change == 'extra_job': jobs.append({'data': [row(D)]})
    elif change == 'mixed_data_error': jobs[0]['error'] = 'Synthetic'
    elif change == 'extra_job_key': jobs[0]['next'] = 'not allowed'
    elif change == 'result_unknown_key': jobs[0]['data'][0]['CUSIP'] = 'forbidden'
    elif change == 'bad_figi': jobs[0]['data'][0]['figi'] = 'not-figi'
    elif change == 'bad_composite': jobs[0]['data'][0]['compositeFIGI'] = ''
    elif change == 'field_bound': jobs[0]['data'][0]['name'] = 'A' * 2049
    else: jobs[0]['data'][0]['name'] = '\ud800'
    with pytest.raises(m.Refused): analyze(jobs)


@pytest.mark.parametrize('raw', [b'[{},{}]junk', b'[{"data":[],"data":[]},{}]', b'[NaN,{}]', b'{}'])
def test_raw_response_duplicate_trailing_nonfinite_or_wrong_top_level_refuses(raw):
    with pytest.raises(m.Refused):
        m.analyze_batch([A, B], request_raw=m.canonical(m.mapping_jobs([A, B])), response_raw=raw, http_status=200)


@pytest.mark.parametrize('change', ['CUSIP', 'no_unlisted', 'nonUS', 'wrong_order', 'bool_status', 'duplicate_claim'])
def test_request_protocol_and_HTTP_status_are_exact_before_interpreting_responses(change):
    claims = [A, B]; jobs = m.mapping_jobs(claims); status = 200
    if change == 'CUSIP': jobs[0] = {'idType': 'ID_CUSIP', 'idValue': '123456789'}
    elif change == 'no_unlisted': jobs[0]['includeUnlistedEquities'] = False
    elif change == 'nonUS': jobs[0]['exchCode'] = 'EU'
    elif change == 'wrong_order': jobs.reverse()
    elif change == 'bool_status': status = True
    else: claims = [A, A]
    with pytest.raises(m.Refused):
        m.analyze_batch(claims, request_raw=m.canonical(jobs), response_raw=m.canonical([{'data': [row(A)]}, {'data': [row(B)]}]), http_status=status)


def test_separate_batches_complete_all_claims_once_and_missing_mapping_stays_unknown():
    left, left_private = analyze(claims=(A,)); right, right_private = analyze(claims=(B,))
    result = m.corroborate(A, B, batches=[(left, left_private.private_record()), (right, right_private.private_record())])
    assert result['observation'] == 'unresolved_share_class_only'
    assert m.corroborate(A, A, batches=[(left, left_private.private_record())])['observation'] == 'same_current_us_composite_observed'
    assert m.corroborate(A, D, batches=[(left, left_private.private_record())])['observation'] == 'unresolved_mapping_missing'
    refused('duplicate_claim', lambda: m.corroborate(A, B, batches=[(left, left_private.private_record())] * 2))


def test_all_relevant_unresolved_job_causes_are_retained_instead_of_first_error_selection():
    result = compare([{'error': 'Synthetic provider error'}, {'data': [{'figi': B, 'metadata': 'Metadata N/A'}]}])
    assert result['unresolved_causes'] == ['unresolved_job_error', 'unresolved_metadata']
    assert m.validate_observation(result) == result


@pytest.mark.parametrize('change', ['route_flag', 'composite_flag', 'causes', 'distinct_claim_positive', 'extra'])
def test_closed_observation_never_promotes_false_hierarchy_or_historical_acceptance(change):
    result = same_claim()
    if change == 'route_flag': result['route_acceptance_granted'] = True
    elif change == 'composite_flag': result['same_nonnull_US_composite'] = False
    elif change == 'causes': result['unresolved_causes'] = ['unresolved_share_class_only']
    elif change == 'distinct_claim_positive': result['current_claim_sha256'] = m.sha(m.canonical(B))
    else: result['old_identity_replaced'] = True
    refused('summary', lambda: m.validate_observation(result))


def test_private_data_and_summary_are_opaque_fresh_and_content_bound():
    summary, private = analyze(); changed = private.private_record(); changed['response_jobs'][0]['data'][0]['compositeFIGI'] = D
    refused('private_record', lambda: m.validate_private_record(changed, expected_summary=summary))
    assert 'SYNTH' not in repr(private) and A not in repr(private)
    with pytest.raises(TypeError): json.dumps(private)
    with pytest.raises(TypeError): pickle.dumps(private)
    with pytest.raises(TypeError): private._raw = b'changed'


@pytest.mark.parametrize('change', ['flag', 'extra', 'ordinal', 'count_bool', 'state', 'result_count', 'pin'])
def test_closed_summary_cannot_fabricate_acceptance_or_impossible_job_counts(change):
    summary, _ = analyze()
    if change == 'flag': summary['route_acceptance_granted'] = True
    elif change == 'extra': summary['ready'] = True
    elif change == 'ordinal': summary['jobs'][0]['job_ordinal'] = 1
    elif change == 'count_bool': summary['job_count'] = True
    elif change == 'state': summary['jobs'][0]['state'] = 'accepted'
    elif change == 'result_count': summary['jobs'][0]['result_count'] = 0
    else: summary['request_pin']['sha256'] = 'bad'
    refused('summary', lambda: m.validate_summary(summary))


def test_limit_hit_is_not_complete_result_and_deadline_is_bounded(monkeypatch):
    monkeypatch.setattr(m, 'MAX_RESULTS_PER_JOB', 2)
    refused('result_bound', lambda: analyze([{'data': [row(A), row(A)]}, {'data': [row(B)]}]))
    refused('deadline', lambda: m.analyze_batch([A], request_raw=m.canonical(m.mapping_jobs([A])),
        response_raw=m.canonical([{'data': [row(A)]}]), http_status=200, deadline=time.monotonic() - 1))


def test_profile_documents_current_only_public_identifier_scope_and_no_replacement_authority():
    profile = m.profile_record()
    assert 'includeUnlistedEquities_true' in profile['request']
    assert 'no_CUSIP_vendor_perma' in profile['public_provenance']
    assert 'unresolved' in profile['shared_share_class_only']
    assert 'instrument_equals_composite' in profile['positive_observation']
    assert 'unresolved_hierarchy_level' in profile['US_composite_hierarchy']
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
