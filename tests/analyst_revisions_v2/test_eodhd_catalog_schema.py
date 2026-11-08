"""Pure supplied-data schema regression; no API, credentials or private files."""
import copy
import json
import unicodedata

import pytest

from scripts import arv2_r298_eodhd_catalog_schema as m


def row():return {'Code':'SPY','Name':'Synthetic fund','Country':'USA','Exchange':'NYSE ARCA',
    'Currency':'USD','Type':'ETF','Isin':'US78462F1030'}


def raw(value):return json.dumps(value,ensure_ascii=False).encode('utf-8')


def history():
    return raw([{'date':day,'open':300,'high':302,'low':299,'close':300.125,'adjusted_close':275.5,'volume':100}
        for day in m.frozen.DATES])


def fails(code,call):
    with pytest.raises(m.Refused) as caught:call()
    assert m.finite(caught.value)==code


def test_unicode_display_values_are_exactly_preserved_without_normalization():
    item=row();item.update(Name='Synthetic \u00ae e\u0301 \U0001f30e fund',Country='\u00d6sterreich')
    rows=m.checked_symbol_rows(raw([item]))
    assert type(rows) is tuple and rows==(item,)
    assert rows[0]['Name']!=unicodedata.normalize('NFC',rows[0]['Name'])
    assert rows[0]['Name'].encode('utf-8')==item['Name'].encode('utf-8')


def test_all_rows_unknown_types_unavailable_ISINs_and_duplicates_remain_in_original_order():
    a=row();b=dict(row(),Code='EXOTIC.^+/= $',Type='Unknown Future Type?!',Isin=None)
    c=dict(row(),Code='OTHER',Type='FUND',Isin='');d=dict(row(),Code='same',Isin='notARealISIN')
    values=[a,b,c,d,copy.deepcopy(a)]
    assert m.checked_symbol_rows(raw(values))==tuple(values)
    assert len(m.checked_symbol_rows(raw(values)))==5
    assert m.checked_symbol_rows(b'[]')==()


@pytest.mark.parametrize('field',('Code','Currency','Type','Exchange','Isin'))
@pytest.mark.parametrize('bad',('\u0421ODE','\uff35SD','A\x00B','A\nB','A\tB','A\x7fB','A\u200bB'))
def test_identifier_homoglyphs_nonASCII_and_controls_are_never_accepted(field,bad):
    item=row();item[field]=bad
    fails('Isin' if field=='Isin' else 'identifier',lambda:m.checked_symbol_rows(raw([item])))


@pytest.mark.parametrize('field',('Name','Country'))
@pytest.mark.parametrize('bad',('A\x00B','A\nB','A\u200bB','A\ue000B','A\u0378B'))
def test_all_Unicode_category_C_display_characters_refuse_without_replacement(field,bad):
    item=row();item[field]=bad
    fails('display',lambda:m.checked_symbol_rows(raw([item])))


@pytest.mark.parametrize('field',('Code','Currency','Type','Exchange','Name','Country','Isin'))
def test_field_types_are_not_coerced_or_identity_case_normalized(field):
    item=row();item[field]=123
    expected='display' if field in ('Name','Country') else 'Isin' if field=='Isin' else 'identifier'
    fails(expected,lambda:m.checked_symbol_rows(raw([item])))
    item=row();item.update(Code='spy',Currency='usd',Type='etf',Exchange='nyse arca',Isin='us78462f1030')
    assert m.checked_symbol_rows(raw([item]))[0]==item
    assert m.authenticate_retained_spy(raw([item]),history())['identity_matched'] is False


def test_empty_display_text_is_preserved_but_required_identifiers_are_nonempty():
    item=row();item.update(Name='',Country='');assert m.checked_symbol_rows(raw([item]))==(item,)
    for field in ('Code','Currency','Type','Exchange'):
        bad=dict(item,**{field:''});fails('identifier',lambda:m.checked_symbol_rows(raw([bad])))


@pytest.mark.parametrize('value',(b'[{"Code":"SPY","Code":"OTHER"}]',b'NaN',b'{',b'\xff',b'[{"Name":{"x":1,"x":2}}]'))
def test_duplicate_JSON_keys_constants_or_bad_UTF8_fail_finitely(value):
    fails('json',lambda:m.checked_symbol_rows(value))


@pytest.mark.parametrize('change',('extra','missing','row_type','outer_type'))
def test_exact_seven_fields_and_list_shape_are_required(change):
    value=[row()]
    if change=='extra':value[0]['future_field']='private'
    elif change=='missing':value[0].pop('Name')
    elif change=='row_type':value=['not a row']
    else:value={'data':value}
    fails('rows' if change=='outer_type' else 'fields',lambda:m.checked_symbol_rows(raw(value)))


def test_row_raw_and_display_bounds_refuse_without_dropping(monkeypatch):
    monkeypatch.setattr(m,'MAX_ROWS',2);fails('rows',lambda:m.checked_symbol_rows(raw([row(),row(),row()])))
    monkeypatch.setattr(m,'MAX_RAW_BYTES',10);fails('bytes',lambda:m.checked_symbol_rows(raw([row()])))
    monkeypatch.setattr(m,'MAX_RAW_BYTES',32*1024*1024)
    item=dict(row(),Name='x'*513);fails('display',lambda:m.checked_symbol_rows(raw([item])))
    monkeypatch.setattr(m,'MAX_DISPLAY_UTF8',3)
    item=dict(row(),Name='\U0001f30e');fails('display',lambda:m.checked_symbol_rows(raw([item])))


def test_specific_retained_SPY_uses_unicode_schema_and_frozen_RAW_history_only():
    item=dict(row(),Name='Synthetic \u00ae fund')
    old=m.frozen.analyse(raw([item]),history());assert old['metadata_schema_valid'] is False
    value=m.authenticate_retained_spy(raw([item]),history());m.validate_spy_summary(value)
    assert value['metadata_schema_valid'] is value['identity_matched'] is value['expected_date_coverage'] is True
    assert value['positive_RAW_close_count']==6
    assert value['RAW_close_series_sha256']==old['RAW_close_series_sha256']
    output=m.canonical(value)
    for forbidden in (b'Synthetic',b'\\u00ae',b'US78462F1030',b'300.125',b'275.5'):assert forbidden not in output
    assert all(value[key] is False for key in m.FALSE_FLAGS)


@pytest.mark.parametrize('field,bad',(('Code','OTHER'),('Type','FUND'),('Currency','CAD'),('Isin',None),
    ('Isin',''),('Isin','FOO'),('Isin','US0000000000')))
def test_no_identity_inference_from_display_or_malformed_current_identifier(field,bad):
    item=dict(row(),Name='SPY US78462F1030 ETF USD');item[field]=bad
    value=m.authenticate_retained_spy(raw([item]),history())
    assert value['metadata_schema_valid'] is True and value['identity_matched'] is False
    assert value['expected_date_coverage'] is True and value['history_row_count']==6


def test_no_first_match_or_duplicate_drop_even_for_specific_SPY():
    value=m.authenticate_retained_spy(raw([row(),row()]),history())
    assert value['metadata_schema_valid'] is False and value['identity_matched'] is False
    assert value['expected_date_coverage'] is True


def test_bad_history_preserves_metadata_match_but_never_full_date_coverage():
    value=m.authenticate_retained_spy(raw([row()]),b'[]')
    assert value['identity_matched'] is True and value['expected_date_coverage'] is False
    assert value['history_row_count']==0
    assert value['price_input_admitted'] is False


@pytest.mark.parametrize('change',('extra','grant','field','schema'))
def test_specific_observation_summary_closed_no_grant_or_payload_fields(change):
    value=m.authenticate_retained_spy(raw([row()]),history())
    if change=='extra':value['private_row']=row()
    elif change=='grant':value['price_input_admitted']=True
    elif change=='field':value['metadata_display_used_for_identity']=True
    else:value['schema']='wrong'
    fails('summary',lambda:m.validate_spy_summary(value))


def test_profile_no_class_filtering_normalization_or_operational_entrypoint():
    import inspect
    profile=m.profile_record();assert profile['maximum_rows']==100000 and profile['maximum_raw_bytes']==32*1024*1024
    assert profile['deduplication_or_class_or_venue_filtering'] is False
    source=inspect.getsource(m)
    for forbidden in ('if __name__','load_key(','requests.','subprocess.','frozen.run(','frozen.main('):assert forbidden not in source
