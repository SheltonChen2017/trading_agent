"""Pure supplied metadata only; no USB, archive, control or service reads."""
import copy
from dataclasses import FrozenInstanceError
import hashlib
import json

import pytest

from scripts import arv2_r335_remx_identity as m


def example():
    return {
        'raw_member_pin': {'byte_count': 181222,
            'sha256': 'b8c54990689501ddc55183e6bb28c8eb7cd47a8817c04153480a6ef613b1de5e'},
        'ticker': 'REMX',
        'listing': {'name': 'Vaneck Vectors Rare Earth/Strategic Metals ETF',
            'first_date': '2010-10-28', 'last_date': '2026-10-16'},
        'segments': [
            {'first_date': '2005-01-04', 'last_date': '2006-06-30', 'row_count': 323},
            {'first_date': '2010-10-28', 'last_date': '2026-10-16', 'row_count': 4016}],
        'total_row_count': 4339,
    }


def refused(code, call):
    with pytest.raises(m.Refused) as caught:
        call()
    assert m.finite(caught.value) == code


def test_profile_pins_original_and_explicit_preserving_partition_without_source_authority():
    profile = m.profile_record()
    assert profile['raw_member_pin'] == example()['raw_member_pin']
    assert profile['quarantined_segment'] == example()['segments'][0]
    assert profile['ETF_segment'] == example()['segments'][1]
    assert profile['official_ETF_inception_date'] == '2010-10-27'
    assert profile['provider_listing']['first_date'] == '2010-10-28'
    evidence = profile['historical_symbol_reuse_evidence']
    assert evidence['documented_old_issuer'] == 'RemedyTemp, Inc.'
    assert evidence['announced_expected_acquisition_effective_date'] == '2006-06-30'
    assert 'not_row_level_issuer_authentication' in evidence['limitation']
    assert evidence['primary_source_URLs'] == list(m.PROVENANCE_URLS)
    assert 'no_silent_drop_or_original_rewrite' in profile['quarantine_rule']
    assert profile['validator_scope'] == 'supplied_metadata_only_not_actual_source_or_rows'
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
    assert m.canonical_profile_bytes() == m.canonical(profile)
    assert m.profile_sha256() == hashlib.sha256(m.canonical_profile_bytes()).hexdigest()


def test_exact_partition_retains_both_eras_and_false_admission_flags():
    result = m.validate_partition(example())
    record = result.to_record()
    assert record['metadata'] == example()
    assert record['metadata_partition_matches_policy'] is True
    assert record['quarantined_row_count'] == 323 and record['ETF_row_count'] == 4016
    assert record['policy_sha256'] == m.profile_sha256()
    assert all(record[key] is False for key in m.FALSE_FLAGS)


def test_returned_evidence_does_not_borrow_nested_caller_state_or_mutable_records():
    supplied = example()
    result = m.validate_partition(supplied)
    expected = result.to_record()
    supplied['segments'][0]['row_count'] = 0
    supplied['raw_member_pin']['sha256'] = 'a' * 64
    changed = result.to_record()
    changed['metadata']['listing']['name'] = 'synthetic replacement'
    assert result.to_record() == expected
    with pytest.raises(FrozenInstanceError):
        result.metadata_bytes = b'{}'


def test_profile_records_are_fresh_and_canonical_reordering_is_harmless():
    first = m.profile_record()
    first['raw_member_pin']['sha256'] = 'a' * 64
    first['historical_symbol_reuse_evidence']['primary_source_URLs'].clear()
    assert m.profile_record()['raw_member_pin']['sha256'] == m.MEMBER_SHA256
    assert len(m.profile_record()['historical_symbol_reuse_evidence']['primary_source_URLs']) == 3
    value = example()
    reordered = dict(reversed(list(value.items())))
    assert m.validate_partition(value) == m.validate_partition(reordered)


@pytest.mark.parametrize('mutation,code', (
    ('mutable', 'metadata'), ('empty', 'metadata'), ('oversize', 'metadata'),
    ('noncanonical', 'record'), ('duplicate', 'record'), ('bad_json', 'record'),
    ('changed_partition', 'partition'), ('forged_policy', 'record'), ('policy_bool', 'record')))
def test_direct_frozen_result_construction_cannot_bypass_metadata_validation(mutation, code):
    raw, policy = m.canonical(example()), m.profile_sha256()
    if mutation == 'mutable': raw = bytearray(raw)
    elif mutation == 'empty': raw = b''
    elif mutation == 'oversize': raw = b'x' * 4097
    elif mutation == 'noncanonical': raw = b' ' + raw
    elif mutation == 'duplicate': raw = raw[:-1] + b',"ticker":"REMX"}'
    elif mutation == 'bad_json': raw = b'not-json'
    elif mutation == 'changed_partition':
        value = example()
        value['segments'].pop(0)
        raw = m.canonical(value)
    elif mutation == 'forged_policy': policy = 'a' * 64
    else: policy = True
    refused(code, lambda: m.RemxPartition(raw, policy))


@pytest.mark.parametrize('value', (None, [], (), 'metadata', 1, True))
def test_non_dictionary_metadata_refuses(value):
    refused('metadata', lambda: m.validate_partition(value))


@pytest.mark.parametrize('key', ('raw_member_pin', 'ticker', 'listing', 'segments', 'total_row_count'))
def test_missing_top_level_field_refuses(key):
    value = example()
    value.pop(key)
    refused('metadata', lambda: m.validate_partition(value))


@pytest.mark.parametrize('extra', ('price_input_admitted', 'source_bytes_authenticated', 'unknown'))
def test_no_extra_authority_or_unknown_fields(extra):
    value = example()
    value[extra] = True
    refused('metadata', lambda: m.validate_partition(value))


@pytest.mark.parametrize('ticker', ('remx', 'REMX-DELISTED', 'REMX ', '', 1, True))
def test_exact_ticker_only(ticker):
    value = example()
    value['ticker'] = ticker
    refused('metadata', lambda: m.validate_partition(value))


@pytest.mark.parametrize('mutation', ('missing', 'extra', 'bytes_bool', 'bytes_float', 'bytes_changed',
    'hash_changed', 'hash_upper', 'hash_non_string', 'not_dict'))
def test_raw_full_member_pin_cannot_be_changed_or_replaced_by_a_cleaned_subset(mutation):
    value = example()
    pin = value['raw_member_pin']
    if mutation == 'missing': pin.pop('sha256')
    elif mutation == 'extra': pin['CRC'] = 123
    elif mutation == 'bytes_bool': pin['byte_count'] = True
    elif mutation == 'bytes_float': pin['byte_count'] = float(pin['byte_count'])
    elif mutation == 'bytes_changed': pin['byte_count'] -= 1
    elif mutation == 'hash_changed': pin['sha256'] = 'a' * 64
    elif mutation == 'hash_upper': pin['sha256'] = pin['sha256'].upper()
    elif mutation == 'hash_non_string': pin['sha256'] = 1
    else: value['raw_member_pin'] = []
    refused('raw_member_pin', lambda: m.validate_partition(value))


@pytest.mark.parametrize('mutation', ('name', 'first', 'last', 'extra', 'missing', 'not_dict', 'bool_date'))
def test_provider_listing_must_match_the_post_inception_segment(mutation):
    value = example()
    row = value['listing']
    if mutation == 'name': row['name'] = 'RemedyTemp, Inc.'
    elif mutation == 'first': row['first_date'] = '2005-01-04'
    elif mutation == 'last': row['last_date'] = '2026-10-15'
    elif mutation == 'extra': row['source_admitted'] = True
    elif mutation == 'missing': row.pop('first_date')
    elif mutation == 'bool_date': row['first_date'] = True
    else: value['listing'] = ()
    refused('listing', lambda: m.validate_partition(value))


@pytest.mark.parametrize('count', (True, False, 4339.0, '4339', 4016, 4340, 0, -1))
def test_exact_total_requires_integer_and_retains_quarantined_rows(count):
    value = example()
    value['total_row_count'] = count
    refused('partition', lambda: m.validate_partition(value))


@pytest.mark.parametrize('mutation', ('none', 'tuple', 'missing_old', 'extra_segment', 'reversed',
    'old_first', 'old_last', 'old_rows', 'ETF_first', 'ETF_last', 'ETF_rows',
    'count_float', 'count_bool', 'missing_date', 'extra_field', 'not_dict'))
def test_exact_two_segment_partition_refuses_generic_date_filter_or_changed_inventory(mutation):
    value = example()
    segments = value['segments']
    if mutation == 'none': value['segments'] = None
    elif mutation == 'tuple': value['segments'] = tuple(segments)
    elif mutation == 'missing_old': segments.pop(0)
    elif mutation == 'extra_segment': segments.append(copy.deepcopy(segments[0]))
    elif mutation == 'reversed': segments.reverse()
    elif mutation == 'old_first': segments[0]['first_date'] = '2005-01-03'
    elif mutation == 'old_last': segments[0]['last_date'] = '2010-10-26'
    elif mutation == 'old_rows': segments[0]['row_count'] = 0
    elif mutation == 'ETF_first': segments[1]['first_date'] = '2010-10-27'
    elif mutation == 'ETF_last': segments[1]['last_date'] = '2026-10-15'
    elif mutation == 'ETF_rows': segments[1]['row_count'] += 1
    elif mutation == 'count_float': segments[0]['row_count'] = 323.0
    elif mutation == 'count_bool': segments[0]['row_count'] = True
    elif mutation == 'missing_date': segments[1].pop('first_date')
    elif mutation == 'extra_field': segments[0]['drop_allowed'] = True
    else: segments[0] = []
    refused('partition', lambda: m.validate_partition(value))


@pytest.mark.parametrize('value', (float('nan'), float('inf'), object()))
def test_canonical_refusals_are_finite_and_do_not_render_supplied_values(value):
    refused('record', lambda: m.canonical({'synthetic': value}))
    assert m.finite(ValueError('private supplied value')) == 'unknown'


def test_module_does_not_parse_source_bytes_or_touch_files_services_or_callbacks(monkeypatch):
    from pathlib import Path
    def forbidden(*args, **kwargs):
        raise AssertionError('pure metadata boundary touched an operational surface')
    monkeypatch.setattr(Path, 'read_bytes', forbidden)
    monkeypatch.setattr(Path, 'open', forbidden)
    assert m.validate_partition(example()).to_record()['metadata']['segments'][0]['row_count'] == 323
    assert json.loads(m.canonical_profile_bytes()) == m.profile_record()
