"""Fabricated aggregates only; no actual observation/archive values or access."""
import importlib.util
import json
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[1] / 'research/short_interest_etf/firstrate_retained_qualification.py'


@pytest.fixture
def q():
    spec = importlib.util.spec_from_file_location('_fabricated_retained_qualification', SOURCE)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def aggregate(q):
    def report(role, rows, clear, quarantine, start, end, dates):
        unused, length, digest = next(row for row in q.PINS if row[0] == role)
        return {'archive_sha256': digest, 'archive_bytes': length, 'member_count': 2, 'inflated_bytes': 1000,
                'rows': rows, 'structurally_clear_rows': clear, 'quarantined_rows': quarantine, 'empty_members': 0,
                'row_reason_counts': {'days_to_cover_numeric': quarantine},
                'reported_field_observations': {'zero_average_volume': 2, 'zero_average_volume_positive_SI': 1,
                                               'zero_average_volume_positive_reported_DTC': 1},
                'earliest_settlement_date': start, 'latest_settlement_date': end, 'distinct_settlement_dates': dates,
                'member_origin_disposition_commitment_sha256': 'c' * 64,
                'all_member_tokens_commitment_sha256': 'e' * 64,
                'year_2026_tokens_commitment_sha256': 'e' * 64,
                'year_2026_rows': 4, 'year_2026_members': 2, 'all_members_CRC_verified': True,
                'complete_byte_inspection': True, 'DTC_recalculated_or_substituted': False}
    full = report('full', 6, 4, 2, '2025-12-15', '2026-01-30', 3)
    full['row_reason_counts']['duplicate_settlement_all_peers'] = 2  # Four issue occurrences, TWO quarantined rows.
    full['all_member_tokens_commitment_sha256'] = 'f' * 64
    year = report('year', 4, 3, 1, '2026-01-15', '2026-01-30', 2)
    return {'schema': q.INSPECTION_SCHEMA, 'policy_sha256': q.INSPECTION_POLICY_SHA256,
            'scope': 'registered_full_and_2026_pair', 'full': full, 'year': year,
            'manifest_sha256': q.PINS[2][2], 'readme_sha256': q.PINS[3][2],
            'selected_manifest_observations_match': True, 'paired_member_mismatches': 0,
            'year_is_exact_full_2026_token_multiset_subset': True, 'semantic_gaps': list(q.GAPS),
            'authority': dict(q.MODEL_AUTHORITY)}


def evaluate(q, payload):
    return q.evaluate_retained_aggregate(q._canonical(payload))


def test_overlapping_reasons_and_reported_attributes_are_retained_without_an_S1_gate(q):
    payload = aggregate(q); value = evaluate(q, payload); private = value.to_payload()
    assert sum(payload['full']['row_reason_counts'].values()) != payload['full']['quarantined_rows']
    assert private['inspection_aggregate'] == payload
    assert private['structural_dispositions']['rows'] == 'quarantine_dispositions_retained'
    assert private['structural_dispositions']['reported_attributes'] == 'retained_without_DTC_recalculation_or_S1_gate'
    assert private['authority']['source_authenticated'] is False
    assert value.sha256 == q._sha(value.canonical_bytes())


def test_public_projection_contains_only_hashes_and_false_authority(q):
    value = evaluate(q, aggregate(q)); public = value.public_summary()
    assert set(public) == {'schema', 'policy_sha256', 'input_aggregate_sha256', 'assessment_sha256', 'authority'}
    assert all(item is False if type(item) is bool else item == 0 for key, item in public['authority'].items()
               if key != 'structural_aggregate_only')
    assert not any(hasattr(value, name) for name in ('iter_rows', 'iter_cells', 'execution_inputs', 'source_lease'))
    assert b'quarantine_dispositions_retained' not in q._canonical(public)


def test_discordant_pair_is_preserved_privately_without_source_admission(q):
    payload = aggregate(q); payload['paired_member_mismatches'] = 1
    payload['year_is_exact_full_2026_token_multiset_subset'] = False
    payload['year']['all_member_tokens_commitment_sha256'] = 'a' * 64
    value = evaluate(q, payload)
    assert value.to_payload()['structural_dispositions']['pair'] == 'reported_discordance_retained'
    assert value.to_payload()['inspection_aggregate']['paired_member_mismatches'] == 1
    assert value.public_summary()['authority']['ready_for_backtest'] is False


def test_no_quarantine_is_also_a_valid_inspection_disposition(q):
    payload = aggregate(q)
    for role in ('full', 'year'):
        report = payload[role]; report['structurally_clear_rows'] = report['rows']
        report['quarantined_rows'] = 0; report['row_reason_counts'] = {}
    assert evaluate(q, payload).to_payload()['structural_dispositions']['rows'] == 'no_row_quarantines_reported'


def test_empty_members_and_no_valid_dates_remain_an_inspection_not_a_successful_pair(q):
    payload = aggregate(q)
    for role in ('full', 'year'):
        report = payload[role]
        report.update(member_count=1, rows=0, structurally_clear_rows=0, quarantined_rows=0, empty_members=1,
                      row_reason_counts={}, reported_field_observations={}, earliest_settlement_date=None,
                      latest_settlement_date=None, distinct_settlement_dates=0, year_2026_rows=0, year_2026_members=0)
    payload.update(paired_member_mismatches=1, year_is_exact_full_2026_token_multiset_subset=False)
    assert evaluate(q, payload).to_payload()['inspection_aggregate']['full']['empty_members'] == 1


@pytest.mark.parametrize('change', ['top_unknown', 'report_unknown', 'missing', 'policy', 'full_pin', 'year_pin',
                                  'manifest_pin', 'readme_pin', 'model_authority_bool_alias', 'model_counter_bool_alias',
                                  'model_authority_true', 'gap', 'manifest_match'])
def test_frozen_schema_pin_and_authority_checks(q, change):
    payload = aggregate(q)
    if change == 'top_unknown': payload['unfrozen'] = True
    elif change == 'report_unknown': payload['full']['unfrozen'] = True
    elif change == 'missing': del payload['year']['rows']
    elif change == 'policy': payload['policy_sha256'] = 'a' * 64
    elif change == 'full_pin': payload['full']['archive_sha256'] = 'a' * 64
    elif change == 'year_pin': payload['year']['archive_bytes'] += 1
    elif change == 'manifest_pin': payload['manifest_sha256'] = 'a' * 64
    elif change == 'readme_pin': payload['readme_sha256'] = 'a' * 64
    elif change == 'model_authority_bool_alias': payload['authority']['source_admitted'] = 0
    elif change == 'model_counter_bool_alias': payload['authority']['provider_HTTP'] = False
    elif change == 'model_authority_true': payload['authority']['source_admitted'] = True
    elif change == 'gap': payload['semantic_gaps'].pop()
    else: payload['selected_manifest_observations_match'] = False
    with pytest.raises(q.RetainedQualificationRefusal): evaluate(q, payload)


@pytest.mark.parametrize('change', ['rows_bool', 'rows_negative', 'rows_bound', 'inflated_bound', 'members_bound',
                                  'clear_sum', 'empty_count', 'reason_count_bool', 'reason_unknown', 'reason_zero',
                                  'unexplained_quarantine', 'reason_more_than_quarantine', 'observation_unknown',
                                  'positive_more_than_zero', 'CRC', 'complete', 'recalculated'])
def test_archive_accounting_and_original_inspection_controls(q, change):
    payload = aggregate(q); report = payload['full']
    if change == 'rows_bool': report['rows'] = True
    elif change == 'rows_negative': report['rows'] = -1
    elif change == 'rows_bound': report['rows'] = q.MAX_ROWS + 1
    elif change == 'inflated_bound': report['inflated_bytes'] = q.MAX_INFLATED + 1
    elif change == 'members_bound': report['member_count'] = q.MAX_MEMBERS + 1
    elif change == 'clear_sum': report['structurally_clear_rows'] += 1
    elif change == 'empty_count': report['empty_members'] = 3
    elif change == 'reason_count_bool': report['row_reason_counts']['days_to_cover_numeric'] = True
    elif change == 'reason_unknown': report['row_reason_counts']['unfrozen_reason'] = 1
    elif change == 'reason_zero': report['row_reason_counts']['days_to_cover_numeric'] = 0
    elif change == 'unexplained_quarantine': report['row_reason_counts'] = {'days_to_cover_numeric': 1}
    elif change == 'reason_more_than_quarantine': report['row_reason_counts']['days_to_cover_numeric'] = 3
    elif change == 'observation_unknown': report['reported_field_observations']['unfrozen_observation'] = 1
    elif change == 'positive_more_than_zero': report['reported_field_observations']['zero_average_volume_positive_SI'] = 3
    elif change == 'CRC': report['all_members_CRC_verified'] = False
    elif change == 'complete': report['complete_byte_inspection'] = False
    else: report['DTC_recalculated_or_substituted'] = True
    with pytest.raises(q.RetainedQualificationRefusal): evaluate(q, payload)


@pytest.mark.parametrize('change', ['invalid_ISO', 'reverse', 'null', 'distinct_span', 'one_date', 'date_accounting',
                                  'year_count', 'year_members', 'mismatch_bool', 'pair_flag', 'pair_hash', 'pair_rows'])
def test_date_and_paired_commitment_contradictions(q, change):
    payload = aggregate(q); report = payload['year']
    if change == 'invalid_ISO': report['earliest_settlement_date'] = '2026-02-30'
    elif change == 'reverse': report['earliest_settlement_date'] = '2026-02-01'
    elif change == 'null': report['earliest_settlement_date'] = None
    elif change == 'distinct_span': report.update(earliest_settlement_date='2026-01-29', distinct_settlement_dates=3)
    elif change == 'one_date': report['latest_settlement_date'] = report['earliest_settlement_date']
    elif change == 'date_accounting': report['row_reason_counts']['settlement_date'] = 1; report['distinct_settlement_dates'] = 4
    elif change == 'year_count': report['year_2026_rows'] = report['rows'] + 1
    elif change == 'year_members': report['year_2026_members'] = 0
    elif change == 'mismatch_bool': payload['paired_member_mismatches'] = False
    elif change == 'pair_flag': payload['year_is_exact_full_2026_token_multiset_subset'] = False
    elif change == 'pair_hash': report['all_member_tokens_commitment_sha256'] = 'a' * 64
    else: report['rows'] = report['year_2026_rows'] = 3; report['structurally_clear_rows'] = 2
    with pytest.raises(q.RetainedQualificationRefusal): evaluate(q, payload)


@pytest.mark.parametrize('change', ['noncanonical', 'duplicate', 'NaN', 'bound', 'mutable'])
def test_strict_canonical_bytes_only(q, change):
    raw = q._canonical(aggregate(q))
    if change == 'noncanonical': raw += b'\n'
    elif change == 'duplicate': raw = raw[:-1] + b',"scope":"registered_full_and_2026_pair"}'
    elif change == 'NaN': raw = raw.replace(b'"rows":6', b'"rows":NaN')
    elif change == 'bound': raw = b'x' * (q.MAX_BYTES + 1)
    else: raw = bytearray(raw)
    with pytest.raises(q.RetainedQualificationRefusal): q.evaluate_retained_aggregate(raw)


def test_factory_seal_and_detached_private_payload_are_not_caller_mutable(q):
    original = aggregate(q); raw = q._canonical(original); value = q.evaluate_retained_aggregate(raw)
    digest = value.sha256; original['full']['rows'] = 100
    copied = value.to_payload(); copied['authority']['source_authenticated'] = True
    assert value.sha256 == digest and value.to_payload()['authority']['source_authenticated'] is False
    with pytest.raises(q.RetainedQualificationRefusal, match='factory'): q.RetainedAggregateAssessment()
    with pytest.raises(q.RetainedQualificationRefusal, match='changed'): value._anchor = ()


def test_copied_object_and_synthetic_registry_row_cannot_adopt_issuance(q):
    original = evaluate(q, aggregate(q)); copied = object.__new__(q.RetainedAggregateAssessment)
    row = original._anchor; fabricated = (copied, *row[1:])
    object.__setattr__(copied, '_anchor', fabricated); q._ISSUED[id(copied)] = fabricated
    with pytest.raises(q.RetainedQualificationRefusal, match='changed'): copied.public_summary()
    assert original.public_summary()['authority']['source_authenticated'] is False


def test_failure_latches_after_class_restore_and_does_not_corrupt_other_issuance(q):
    first = evaluate(q, aggregate(q)); second = evaluate(q, aggregate(q)); cls = q.RetainedAggregateAssessment
    q.RetainedAggregateAssessment = object
    try:
        with pytest.raises(q.RetainedQualificationRefusal, match='changed'): first.public_summary()
    finally: q.RetainedAggregateAssessment = cls
    with pytest.raises(q.RetainedQualificationRefusal, match='changed'): first.canonical_bytes()
    assert second.to_payload()['authority']['source_admitted'] is False


def test_original_getter_wrapping_and_policy_change_latch(q):
    value = evaluate(q, aggregate(q)); cls = q.RetainedAggregateAssessment; method = cls.__dict__['canonical_bytes']
    cls.canonical_bytes = staticmethod(method)
    try:
        with pytest.raises(q.RetainedQualificationRefusal, match='changed'): value.public_summary()
    finally: cls.canonical_bytes = method
    with pytest.raises(q.RetainedQualificationRefusal, match='changed'): value.sha256
    other = evaluate(q, aggregate(q)); q.MODEL_AUTHORITY['source_admitted'] = True
    try:
        with pytest.raises(q.RetainedQualificationRefusal, match='policy'): other.public_summary()
    finally: q.MODEL_AUTHORITY['source_admitted'] = False
    with pytest.raises(q.RetainedQualificationRefusal, match='changed'): other.public_summary()


@pytest.mark.parametrize('change', ['authority', 'authority_code', 'policy', 'hash'])
def test_issued_assessment_rejects_public_policy_rebasing_and_latches(q, change):
    value = evaluate(q, aggregate(q)); original_authority = q.authority; original_code = q.authority.__code__
    original_policy, original_hash = q.qualification_policy, q.POLICY_SHA256
    if change == 'authority': q.authority = lambda: {**original_authority(), 'source_admitted': True}
    elif change == 'authority_code':
        q.authority.__code__ = (lambda: {'source_admitted': True}).__code__
    elif change == 'policy': q.qualification_policy = lambda: {**original_policy(), 'unfrozen': True}
    else: q.POLICY_SHA256 = 'a' * 64
    if change != 'hash': q.POLICY_SHA256 = q._sha(q._canonical(q.qualification_policy()))
    try:
        with pytest.raises(q.RetainedQualificationRefusal, match='policy') as caught: value.public_summary()
        assert q.failure_summary(caught.value)['authority']['source_admitted'] is False
    finally:
        q.authority = original_authority; original_authority.__code__ = original_code
        q.qualification_policy = original_policy; q.POLICY_SHA256 = original_hash
    with pytest.raises(q.RetainedQualificationRefusal, match='changed'): value.public_summary()


@pytest.mark.parametrize('replacement', ['raised_authority', 'equal_copy', 'original_alias'])
def test_authority_byte_snapshot_rebinding_vetoes_fresh_issuance_and_latches_existing(q, replacement):
    payload = aggregate(q); value = evaluate(q, payload); original = q._AUTHORITY_BYTES
    before = len(q._ISSUED)
    original_alias = q._ORIGINAL_AUTHORITY_BYTES
    if replacement == 'original_alias':
        q._ORIGINAL_AUTHORITY_BYTES = q._canonical({**q.authority(), 'source_admitted': True})
    else:
        q._AUTHORITY_BYTES = (q._canonical({**q.authority(), 'source_admitted': True})
                              if replacement == 'raised_authority' else original.decode().encode())
        assert q._AUTHORITY_BYTES is not original
    try:
        with pytest.raises(q.RetainedQualificationRefusal, match='policy'): evaluate(q, payload)
        assert len(q._ISSUED) == before
        with pytest.raises(q.RetainedQualificationRefusal, match='policy') as caught: value.public_summary()
        assert q.failure_summary(caught.value)['authority']['source_admitted'] is False
    finally: q._AUTHORITY_BYTES = original; q._ORIGINAL_AUTHORITY_BYTES = original_alias
    with pytest.raises(q.RetainedQualificationRefusal, match='changed'): value.public_summary()
    assert evaluate(q, payload).public_summary()['authority']['source_admitted'] is False


def test_fixed_failure_projection_cannot_echo_private_values(q):
    for error in (ValueError('/private/FABRICATED'), q.RetainedQualificationRefusal('/private/FABRICATED')):
        summary = q.failure_summary(error)
        assert summary['code'] is None and b'FABRICATED' not in q._canonical(summary)
