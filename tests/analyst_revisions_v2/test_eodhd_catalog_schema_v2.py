"""Pure V2 representation tests: opaque displays never identify or escape."""
import copy
import json

import pytest

from scripts import arv2_r298_eodhd_catalog_schema_v2 as m


def row():return {'Code':'SPY','Name':'Synthetic private fund','Country':'USA','Exchange':'NYSE ARCA',
    'Currency':'USD','Type':'ETF','Isin':'US78462F1030'}


def raw(value):return json.dumps(value,ensure_ascii=True).encode('ascii')


def fails(code,call):
    with pytest.raises(m.Refused) as caught:call()
    assert m.finite(caught.value)==code


@pytest.mark.parametrize('value',(None,'','opaque\x00payload','opaque\ntext','opaque\u200btext',
    'opaque\ue000text','opaque\u0378text','opaque\ud800text','opaque\udffftext','e\u0301\u00ae\U0001f30e'))
@pytest.mark.parametrize('field',('Name','Country'))
def test_opaque_display_payload_exactly_preserved_even_when_unrenderable(field,value):
    item=row();item[field]=value
    rows=m.checked_symbol_rows(raw([item]))
    assert rows==(item,) and rows[0][field]==value
    assert m.canonical(rows[0])==m.canonical(item)


def test_all_rows_duplicates_nullable_labels_unknown_classes_and_malformed_ISIN_remain_private():
    a=row();b=dict(row(),Code='EXOTIC.^+/= $',Currency=None,Type=None,Exchange=None,Isin='N/A',Name=None,Country=None)
    c=dict(row(),Code='OTHER',Currency='',Type='New Unknown Type?!',Exchange='',Isin=' - ')
    d=dict(row(),Code='same',Type='FUND',Isin='')
    values=[a,b,c,d,copy.deepcopy(a)]
    assert m.checked_symbol_rows(raw(values))==tuple(values)
    assert len(m.checked_symbol_rows(raw(values)))==5 and m.checked_symbol_rows(b'[]')==()
    observed=m.observe_raw(raw(values));assert observed['row_count']==5
    assert observed['field_availability_types']['Name']['null']==1
    assert observed['field_availability_types']['Currency']['null']==1
    assert all(observed[key] is False for key in m.FALSE_FLAGS)


@pytest.mark.parametrize('field',('Code','Currency','Type','Exchange','Isin'))
@pytest.mark.parametrize('bad',('\u0421ODE','\uff35SD','A\x00B','A\nB','A\x7fB','A\u200bB'))
def test_identifier_representation_remains_ASCII_and_control_free(field,bad):
    item=row();item[field]=bad
    expected='Code' if field=='Code' else 'Isin' if field=='Isin' else 'label'
    fails(expected,lambda:m.checked_symbol_rows(raw([item])))


@pytest.mark.parametrize('bad',(None,'',123,True))
def test_Code_is_nonempty_printable_ASCII_and_never_coerced(bad):
    item=dict(row(),Code=bad);fails('Code',lambda:m.checked_symbol_rows(raw([item])))


def test_null_empty_and_printable_placeholders_are_not_normalized_into_identities():
    values=[]
    for index,isin in enumerate((None,'','N/A',' - ','notAnISIN','US78462F1030')):
        values.append(dict(row(),Code='code'+str(index),Isin=isin))
    rows=m.checked_symbol_rows(raw(values));assert rows==tuple(values)
    observed=m.observe_raw(raw(values));counts=observed['field_availability_types']['Isin']
    assert counts=={'null':1,'empty_string':1,'nonempty_string':4}
    assert observed['route_eligibility_proven'] is observed['identity_crosswalk_admitted'] is False


@pytest.mark.parametrize('field',('Currency','Type','Exchange','Isin','Name','Country'))
@pytest.mark.parametrize('bad',(123,True,[],{}))
def test_nonstring_nonnull_payloads_are_not_repaired_or_coerced(field,bad):
    item=dict(row(),**{field:bad})
    expected='display_bound' if field in ('Name','Country') else 'Isin' if field=='Isin' else 'label'
    fails(expected,lambda:m.checked_symbol_rows(raw([item])))


def test_character_serialized_byte_identifier_row_and_raw_bounds(monkeypatch):
    item=dict(row(),Name='a'*4096);assert m.checked_symbol_rows(raw([item]))==(item,)
    item['Name']+='a';fails('display_bound',lambda:m.checked_symbol_rows(raw([item])))
    item=dict(row(),Name='\ud800'*3000)
    fails('display_bound',lambda:m.checked_symbol_rows(raw([item])))  # 18002 serialized JSON bytes, not a category ban.
    for field,maximum,code in (('Code',64,'Code'),('Currency',16,'label'),('Type',64,'label'),('Exchange',64,'label'),('Isin',32,'Isin')):
        item=dict(row(),**{field:'A'*(maximum+1)});fails(code,lambda:m.checked_symbol_rows(raw([item])))
    monkeypatch.setattr(m,'MAX_ROWS',2);fails('rows',lambda:m.checked_symbol_rows(raw([row(),row(),row()])))
    monkeypatch.setattr(m,'MAX_RAW_BYTES',10);fails('bytes',lambda:m.checked_symbol_rows(raw([row()])))


@pytest.mark.parametrize('value',(b'[{"Code":"SPY","Code":"OTHER"}]',b'NaN',b'[',b'\xff',b'[{"Name":{"x":1,"x":2}}]'))
def test_duplicate_keys_or_bad_JSON_refuse_without_error_value_export(value):
    fails('json',lambda:m.checked_symbol_rows(value))


@pytest.mark.parametrize('change',('extra','missing','row','outer'))
def test_exact_seven_key_list_shape_remains_binding(change):
    value=[row()]
    if change=='extra':value[0]['Extra']='private'
    elif change=='missing':value[0].pop('Country')
    elif change=='row':value=['private']
    else:value={'data':value}
    fails('rows' if change=='outer' else 'fields',lambda:m.checked_symbol_rows(raw(value)))


def test_observation_outputs_only_counts_availability_types_and_hashes_not_display_values():
    item=dict(row(),Name='OPAQUE_SECRET_VALUE_X\x00PAYLOAD\ud800',Country=None)
    value=m.observe_raw(raw([item]));m.validate_observation(value)
    output=m.canonical(value)
    for forbidden in (b'OPAQUE_SECRET_VALUE_X',b'PAYLOAD',b'\\u0000',b'\\ud800',b'US78462F1030',b'SPY',b'NYSE ARCA'):
        assert forbidden not in output
    assert value['field_availability_types']['Name']=={'null':0,'empty_string':0,'nonempty_string':1}
    assert value['raw_pin']=={'byte_count':len(raw([item])),'sha256':m.sha(raw([item]))}


@pytest.mark.parametrize('change',('extra','grant','row_bool','sum','Code_null','hash','raw_bool'))
def test_closed_observation_cannot_become_route_or_price_admission(change):
    value=m.observe_raw(raw([row()]))
    if change=='extra':value['display_payload']='private'
    elif change=='grant':value['route_eligibility_proven']=True
    elif change=='row_bool':value['row_count']=True
    elif change=='sum':value['field_availability_types']['Name']['nonempty_string']=0
    elif change=='Code_null':value['field_availability_types']['Code']={'null':1,'empty_string':0,'nonempty_string':0}
    elif change=='hash':value['ordered_private_records_sha256']='z'*64
    else:value['raw_pin']['byte_count']=True
    fails('summary',lambda:m.validate_observation(value))


def test_profile_is_representation_only_and_source_has_no_display_normalization_or_I_O():
    import inspect
    profile=m.profile_record();assert profile['maximum_rows']==100000
    assert profile['opaque_display_control_format_unassigned_surrogate_payloads_preserved'] is True
    assert profile['strict_route_preparation_independent_from_catalog_representation'] is True
    source=inspect.getsource(m)
    for forbidden in ('if __name__','load_key(','requests.','subprocess.','unicodedata','normalize(','print(','open('):assert forbidden not in source
