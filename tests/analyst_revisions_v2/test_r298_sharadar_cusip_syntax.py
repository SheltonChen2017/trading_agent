"""U complete-vocabulary syntax, synthetic captures only; native denial required."""
import inspect
import json

import pytest

from scripts import arv2_r298_sharadar_cusip_syntax as m
from tests.analyst_revisions_v2 import test_r298_sharadar_probe_metadata as fixture


TOKENS = ('000000001', '000000002', '000000003', 'ABCDEF123')


def bind(monkeypatch, captures):
    """Synthetic literal-pin seam; never any real retained source read."""
    pins = {name: {'byte_count': len(raw), 'sha256': m.sha(raw)} for name, raw in captures.items()}
    monkeypatch.setattr(m, 'CAPTURE_PINS', pins)
    monkeypatch.setattr(m, 'T_RECEIPT_SHA256', m.sha(m.canonical(m.previous._receipt(captures))))
    return captures


@pytest.fixture
def payloads(monkeypatch):
    captures = fixture.payloads()
    funds = fixture.rows(captures[m.CAPTURE_NAMES[1]])
    funds[1]['cusips'] = ' '.join(TOKENS[:3])
    funds[4]['cusips'] = ', '.join(TOKENS[:2])
    captures[m.CAPTURE_NAMES[1]] = fixture.csv_bytes(m.previous.META_FIELDS, funds)
    return bind(monkeypatch, captures)


@pytest.fixture(autouse=True)
def no_operations(monkeypatch):
    def deny(*args, **kwargs): raise AssertionError('no old operation')
    for module in (m.previous, m.previous.previous, m.previous.previous.previous):
        monkeypatch.setattr(module, 'observe', deny)
        monkeypatch.setattr(module, '_fetch', deny)


def refused(code, callback):
    with pytest.raises(m.Refused) as caught: callback()
    assert m.finite(caught.value) == code


@pytest.mark.parametrize('value,expected', [
    ('000000001', ('000000001',)),
    ('000000001,000000002', TOKENS[:2]),
    ('000000001, 000000002', TOKENS[:2]),
    (' 000000001 ,  000000002 ', TOKENS[:2]),
    ('000000001 000000002 000000003', TOKENS[:3]),
    (' 000000001   000000002 ', TOKENS[:2]),
    ('abcdef123', ('ABCDEF123',)),
    ('abcdef123,000000001', ('000000001', 'ABCDEF123')),
    ('abcdef123 000000001', ('000000001', 'ABCDEF123')),
])
def test_complete_supported_grammars_and_explicit_ASCII_case_normalization(value, expected):
    assert m.parse_cusips(value) == expected


@pytest.mark.parametrize('value,code', [
    (None, 'field_type'), (False, 'field_type'), (9, 'field_type'), ([], 'field_type'),
    ('', 'missing'), ('   ', 'missing'),
    ('000000001,', 'empty_token'), (',000000001', 'empty_token'),
    ('000000001,,000000002', 'empty_token'), ('000000001,  ,000000002', 'empty_token'),
    ('000000001;000000002', 'token_shape'), ('000000001|000000002', 'token_shape'),
    ('000000001/000000002', 'token_shape'), ('000000001.000000002', 'token_shape'),
    ('000000001 000000002,000000003', 'token_shape'),
    ('000000001,000000002 000000003', 'token_shape'),
    ('000000001X', 'token_shape'), ('00000000', 'token_shape'),
    ('000000001junk', 'token_shape'), ('prefix000000001', 'token_shape'),
    ('000000001\t000000002', 'control'), ('000000001\n', 'control'),
    ('\r000000001', 'control'), ('000000001\x00', 'control'), ('000000001\x7f', 'control'),
    ('000000001\u00a0000000002', 'non_ascii'), ('Ａ00000001', 'non_ascii'),
    ('000000001\ud800', 'non_ascii'),
    ('000000001,000000001', 'duplicate'), ('000000001 000000001', 'duplicate'),
    ('abcdef123,ABCDEF123', 'duplicate'),
    ('a' * 2049, 'field_bound'),
])
def test_no_partial_unknown_empty_control_unicode_or_duplicate_acceptance(value, code):
    refused(code, lambda: m.parse_cusips(value))


def test_token_cap_and_full_field_bound_are_independent():
    tokens = [f'{index:09d}' for index in range(65)]
    assert len(m.parse_cusips(' '.join(tokens[:64]))) == 64
    refused('token_count', lambda: m.parse_cusips(' '.join(tokens)))
    refused('field_bound', lambda: m.parse_cusips(' ' * 2048 + TOKENS[0]))


@pytest.mark.parametrize('delimiter', [',', ' '])
def test_duplicate_after_ASCII_case_normalization_is_never_accepted(delimiter):
    refused('duplicate', lambda: m.parse_cusips(delimiter.join(('abcdef123', 'ABCDEF123'))))


def test_complete_token_not_prefix_or_substring():
    refused('token_shape', lambda: m.parse_cusips('000000001JUNK'))


def test_exact_captures_recompute_old_T_projection_without_operations(payloads):
    receipt = m.inspect_captures(payloads)
    assert m.validate_capture(receipt, payloads) == receipt
    assert receipt['capture_pins'] == m.CAPTURE_PINS
    assert receipt['t_receipt_sha256'] == m.sha(m.canonical(m.previous._receipt(payloads)))
    assert [row['probe_index'] for row in receipt['probes']] == list(range(9))
    space, comma = receipt['probes'][2], receipt['probes'][5]
    assert space['grammar'] == 'ascii_space' and space['separator_ordinals'] == [{'ordinal': 32, 'count': 2}]
    assert space['legacy_parse_count'] == 0 and space['new_parse_count'] == 3 and space['accepted'] is True
    assert comma['grammar'] == 'comma' and comma['separator_ordinals'] == [{'ordinal': 32, 'count': 1}, {'ordinal': 44, 'count': 1}]
    assert comma['legacy_parse_count'] == comma['new_parse_count'] == 2
    encoded = m.canonical(receipt)
    assert all(token.encode() not in encoded for token in TOKENS)
    assert b'QCOM' not in encoded and b'QQQ' not in encoded and b'REMX' not in encoded
    assert all(receipt[name] is False for name in m.FALSE_FLAGS)
    assert receipt['provider_application_dispatches'] == receipt['qc_application_dispatches'] == 0


@pytest.mark.parametrize('value,reason,ordinals', [
    ('000000001;000000002', 'token_shape', [{'ordinal': 59, 'count': 1}]),
    ('000000001 000000001', 'duplicate', [{'ordinal': 32, 'count': 1}]),
    ('', 'missing', []),
    ('000000001\u00a0000000002', 'non_ascii', [{'ordinal': 160, 'count': 1}]),
])
def test_unknown_syntax_is_honest_closed_observation_not_loosened_admission(monkeypatch,value,reason,ordinals):
    captures=fixture.payloads();funds=fixture.rows(captures[m.CAPTURE_NAMES[1]])
    funds[1]['cusips']=value;captures[m.CAPTURE_NAMES[1]]=fixture.csv_bytes(m.previous.META_FIELDS,funds)
    bind(monkeypatch,captures);receipt=m.inspect_captures(captures);row=receipt['probes'][2]
    assert row['accepted'] is False and row['new_parse_count'] == 0 and row['reason'] == reason
    assert row['separator_ordinals'] == ordinals and all(receipt[key] is False for key in m.FALSE_FLAGS)
    assert m.validate_capture(receipt,captures)==receipt


def test_byte_pins_are_checked_before_any_old_parser(payloads,monkeypatch):
    def deny(*args,**kwargs):raise AssertionError('parsed mismatched bytes')
    monkeypatch.setattr(m.previous,'_receipt',deny)
    for name in m.CAPTURE_NAMES:
        changed=dict(payloads);changed[name]+=b'\n'
        refused('capture_pin',lambda:m.inspect_captures(changed))
    refused('capture_shape',lambda:m.inspect_captures({}))


def test_closed_T_receipt_digest_is_independently_bound(payloads,monkeypatch):
    monkeypatch.setattr(m,'T_RECEIPT_SHA256','0'*64)
    refused('t_projection',lambda:m.inspect_captures(payloads))


def test_exact_nine_unique_current_candidates_required_even_with_synthetic_pins(monkeypatch):
    captures=fixture.payloads();stocks=fixture.rows(captures[m.CAPTURE_NAMES[0]])
    captures[m.CAPTURE_NAMES[0]]=fixture.csv_bytes(m.previous.META_FIELDS,stocks*2)
    bind(monkeypatch,captures)
    refused('t_projection',lambda:m.inspect_captures(captures))


@pytest.mark.parametrize('change', ['flag','index_bool','accepted_bool','false_acceptance','reason',
    'newcount','duplicate','separators','alnum_separator','ordinal_bool','field_hash','field_bound',
    'capture_pin','t_receipt','legacy_count','private_field','grammar'])
def test_receiver_rejects_forged_or_impossible_syntax_claims(payloads,change):
    receipt=m.inspect_captures(payloads);row=receipt['probes'][2]
    if change=='flag':receipt['new_parser_admitted']=True
    elif change=='index_bool':row['probe_index']=True
    elif change=='accepted_bool':row['accepted']=1
    elif change=='false_acceptance':row['accepted']=False
    elif change=='reason':row['reason']='unknown_delimiter_actual_value'
    elif change=='newcount':row['new_parse_count']=2
    elif change=='duplicate':row['duplicate_token_count']=1
    elif change=='separators':row['separator_ordinals']=[{'ordinal':32,'count':1}]
    elif change=='alnum_separator':row['separator_ordinals']=[{'ordinal':65,'count':2}]
    elif change=='ordinal_bool':row['separator_ordinals']=[{'ordinal':True,'count':2}]
    elif change=='field_hash':row['field_sha256']=m.sha(m.canonical(''))
    elif change=='field_bound':row['field_utf8_byte_count']=2049
    elif change=='capture_pin':receipt['capture_pins'][m.CAPTURE_NAMES[0]]['byte_count']=True
    elif change=='t_receipt':receipt['t_receipt_sha256']='0'*64
    elif change=='legacy_count':row['legacy_parse_count']=1
    elif change=='private_field':row['tokens']=list(TOKENS)
    else:row['grammar']='single'
    refused('receipt',lambda:m.validate_receipt(receipt))


def test_received_capture_is_recomputed_not_just_accepted(payloads):
    receipt=m.inspect_captures(payloads)
    receipt['probes'][0]['field_sha256']='1'*64
    assert m.validate_receipt(receipt)
    refused('receipt',lambda:m.validate_capture(receipt,payloads))


def test_returns_fresh_receipt_copies(payloads):
    receipt=m.inspect_captures(payloads);checked=m.validate_receipt(receipt)
    checked['capture_pins'][m.CAPTURE_NAMES[0]]['byte_count']=0
    checked['probes'][2]['separator_ordinals'][0]['count']=99
    assert receipt['capture_pins']==m.CAPTURE_PINS
    assert receipt['probes'][2]['separator_ordinals'][0]['count']==2


def test_profile_is_only_syntax_evidence_and_old_sources_untouched():
    profile=m.profile_record()
    assert profile['old_parser_and_S_T_composer_sources_unchanged'] is True
    assert profile['historical_CUSIP_vocabulary_is_not_active_or_effective_interval_proof'] is True
    assert all(profile[name] is False for name in m.FALSE_FLAGS)
    source=inspect.getsource(m)
    assert '.findall(' not in source and '.observe(' not in source and '._fetch(' not in source
    assert json.loads(m.canonical(profile))==profile


def test_exact_exception_type_only_and_no_hostile_error_inspection():
    class Child(m.Refused):pass
    assert m.finite(Child('duplicate'))=='unknown'
    assert m.finite(RuntimeError('000000001'))=='unknown'
    assert m.finite(m.Refused('duplicate'))=='duplicate'
