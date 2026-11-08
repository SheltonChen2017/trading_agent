"""Public CGS examples and synthetic format evidence; no source admission."""
import pickle

import pytest

from scripts import arv2_r298_isin_cusip_evidence as m


def complete_isin(seed):
    # Synthetic test construction only. The production helper never generates,
    # pads, repairs or substitutes a check digit.
    assert len(seed) == 11
    for digit in '0123456789':
        if m.checks._isin(seed + digit): return seed + digit
    raise AssertionError('synthetic ISIN seed has no check digit')


@pytest.mark.parametrize('isin,local,prefix', [
    ('US0231351067', '023135106', 'US'), ('CA0089117034', '008911703', 'CA')])
def test_public_CGS_examples_extract_the_exact_existing_nine_characters(isin, local, prefix):
    summary, evidence = m.inspect(isin)
    assert summary['status'] == 'supported_prefix_CUSIP_observed' and summary['reason'] is None
    assert summary['provenance_supported_prefix'] == prefix
    assert summary['valid_ISIN_checksum'] is summary['local_cusip9_from_ISIN_observed'] is True
    assert summary['original_ISIN_sha256'] == m.sha(isin.encode('ascii'))
    assert summary['local_cusip9_sha256'] == m.sha(local.encode('ascii'))
    private = evidence.private_record()
    assert private['original_ISIN'] == isin and private['local_cusip9_from_ISIN'] == local
    assert private['provenance'] == 'unmodified_ISIN_positions_3_through_11'
    assert private['provenance_supported_prefix'] == prefix
    assert private['raw_CUSIP_field_observed'] is private['raw_CUSIP_overridden'] is False
    assert evidence.summary_sha256 == m.digest(summary)
    assert m.validate_summary(summary) == summary
    assert all(summary[key] is False for key in m.FALSE_FLAGS)


@pytest.mark.parametrize('isin', ['KYG3165B1032', complete_isin('GB023135106')])
def test_valid_non_US_CA_ISIN_never_implies_a_supported_CUSIP_even_with_a_valid_local_checksum(isin):
    assert m.checks._isin(isin)
    summary, evidence = m.inspect(isin)
    assert summary['status'] == 'unresolved' and summary['reason'] == 'unsupported_prefix'
    assert summary['valid_ISIN_checksum'] is True
    assert summary['local_cusip9_from_ISIN_observed'] is False
    assert summary['provenance_supported_prefix'] is summary['local_cusip9_sha256'] is None
    assert evidence is None


@pytest.mark.parametrize('value', [None, True, False, 123, 1.5, b'US0231351067', [], {}])
def test_missing_and_non_string_values_are_not_coerced(value):
    summary, evidence = m.inspect(value)
    assert summary['reason'] == ('missing' if value is None else 'type')
    assert summary['original_ISIN_sha256'] is None and evidence is None


@pytest.mark.parametrize('value', ['02313510', '023135106', 'US023135106', 'US02313510670',
    'us0231351067', ' US0231351067', 'US0231351067 ', 'US02313510ο7',
    'ＵS0231351067', 'US023135106\n', 'US023135106\x00', 'US02313510\ud800'])
def test_length_case_whitespace_homoglyph_and_shape_are_never_normalized(value):
    summary, evidence = m.inspect(value)
    assert summary['reason'] == 'shape' and summary['original_ISIN_sha256'] is None
    assert evidence is None


@pytest.mark.parametrize('isin', ['US0231351068', 'CA0089117035'])
def test_full_ISIN_checksum_is_mandatory_before_local_extraction(isin):
    summary, evidence = m.inspect(isin)
    assert summary['reason'] == 'isin_checksum'
    assert summary['valid_ISIN_checksum'] is summary['local_cusip9_from_ISIN_observed'] is False
    assert summary['provenance_supported_prefix'] is summary['local_cusip9_sha256'] is None
    assert evidence is None


def test_valid_ISIN_with_invalid_embedded_CUSIP_is_not_repaired_or_exposed_as_evidence():
    isin = complete_isin('US023135107')
    assert m.checks._isin(isin) and not m.checks._cusip(isin[2:11])
    summary, evidence = m.inspect(isin)
    assert summary['reason'] == 'local_cusip_checksum' and summary['valid_ISIN_checksum'] is True
    assert summary['provenance_supported_prefix'] == 'US'
    assert summary['local_cusip9_sha256'] is None and evidence is None


def test_arbitrary_objects_and_string_subclasses_cannot_trigger_coercion_or_comparison_callbacks():
    class Trap:
        def __str__(self): raise AssertionError('coerced input')
        def __eq__(self, other): raise AssertionError('compared arbitrary input')
    class StringSubclass(str): pass
    for value in (Trap(), StringSubclass('US0231351067')):
        summary, evidence = m.inspect(value)
        assert summary['reason'] == 'type' and evidence is None
    assert m.finite(m.Refused(Trap())) == 'unknown'


def test_private_evidence_is_immutable_independently_copied_redacted_and_not_pickleable():
    summary, evidence = m.inspect('US0231351067')
    assert 'US0231351067' not in repr(evidence) and '023135106' not in repr(evidence)
    with pytest.raises(TypeError): evidence.summary_sha256 = 'a' * 64
    with pytest.raises(TypeError): pickle.dumps(evidence)
    copied = evidence.private_record(); copied['original_ISIN'] = 'CHANGED'
    assert evidence.private_record()['original_ISIN'] == 'US0231351067'
    public = m.canonical(summary)
    assert b'US0231351067' not in public and b'023135106' not in public
    checked = m.validate_summary(summary); checked['original_ISIN_sha256'] = 'b' * 64
    assert evidence.summary_sha256 == m.digest(summary)


@pytest.mark.parametrize('field,value', [('reason', 'shape'), ('valid_ISIN_checksum', False),
    ('local_cusip9_from_ISIN_observed', False), ('provenance_supported_prefix', 'GB'),
    ('local_cusip9_sha256', None), ('raw_CUSIP_overridden', True), ('route_created', True),
    ('source_or_price_admission_granted', True)])
def test_closed_metadata_rejects_inconsistent_or_authority_shaped_changes(field, value):
    summary, _ = m.inspect('US0231351067'); summary[field] = value
    with pytest.raises(m.Refused) as caught: m.validate_summary(summary)
    assert m.finite(caught.value) == 'summary'


def test_unknown_or_raw_fields_cannot_be_added_to_public_metadata():
    summary, _ = m.inspect('US0231351067'); summary['raw_CUSIP'] = '023135106'
    with pytest.raises(m.Refused): m.validate_summary(summary)


def test_profile_limits_the_observation_and_preserves_raw_CUSIP_disagreement_as_a_caller_obligation():
    profile = m.profile_record()
    assert profile['supported_prefixes'] == ['CA', 'US']
    assert profile['primary_source'] == 'https://www.cusip.com/identifiers.html?section=ISIN'
    assert profile['checksum_source_pin']['sha256'] == '39464645b7acb8187eac2209e7e994d74ddd3c077911cb32d1a9c1820ffd6843'
    assert 'separate' in profile['caller_obligations'] and 'disagreement' in profile['provenance']
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
