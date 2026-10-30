"""Synthetic AV shape/closure/normal-return proof; no AU DATA or operation."""
import copy
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace as NS

import pytest

from scripts import read_arv2_r298_eodhd_metadata_shape as m


def row():return {'Code':'SPY','Name':'Synthetic private fund','Country':'USA','Exchange':'NYSE ARCA',
    'Currency':'USD','Type':'ETF','Isin':'US78462F1030'}


def raw(value):return json.dumps(value,ensure_ascii=False).encode('utf-8')


def args():return NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)


def fails(code,call):
    with pytest.raises(m.Refused) as caught:call()
    assert m.finite(caught.value)==code


def test_fixed_one_DATA_pin_and_failed_AU_provenance_are_exact_no_renewal():
    assert len(m.pins())==203
    assert all(m.sha((m.ROOT/name).read_bytes())==value for name,value in m.pins().items())
    assert m.DATA_PLAN=={'au_metadata':{'relative_path':'artifacts/analyst_revisions_v2/newrule_eodhd_history_diagnostic/R326-20261027-AU/metadata-private.json',
        'byte_count':170,'sha256':'27fe1cfd219c064793151e03c98ce70eb43889b568056d5810f8db3dc2b1355a'}}
    fact=m.observed_failure();assert fact['parent_actual_exit']==2 and fact['native_validator_actual_exit']==0
    assert fact['AU_identity_accepted'] is False and fact['new_operation_or_read_granted'] is False
    assert m.profile_record()['claim_before_metadata_DATA_read'] is True


def test_exact_shape_has_known_fields_hashes_flags_and_no_licensed_values():
    value=m.shape(raw([row()]));m.validate_shape(value)
    assert value['original_AU_predicates']['would_pass_metadata_shape'] is True
    assert value['selected_field_count']==7
    by_name={field['name']:field for field in value['fields']}
    for name in ('Code','Type','Currency','Isin'):assert by_name[name]['public_expected_match'] is True
    assert by_name['Name']['public_expected_match'] is None
    output=m.canonical(value)
    for forbidden in (b'Synthetic private fund',b'SPY',b'USD',b'US78462F1030',b'NYSE ARCA'):assert forbidden not in output
    assert all(value[key] is False for key in m.FALSE_FLAGS)


def test_nonASCII_display_name_identifies_original_shape_refusal_without_value_export():
    item=row();item['Name']='Synthetic private \u00ae fund'
    value=m.shape(raw([item]));pred=value['original_AU_predicates']
    assert pred['exact_seven_keys'] is pred['Isin_type_bound'] is True
    assert pred['six_bounded_printable_ASCII_strings'] is pred['would_pass_metadata_shape'] is False
    field=next(field for field in value['fields'] if field.get('name')=='Name')
    assert field['value_type']=='string' and field['ASCII_string'] is field['printable_ASCII_string'] is False
    output=m.canonical(value);assert b'\\u00ae' not in output and b'Synthetic' not in output


def test_unknown_fields_are_hash_only_and_do_not_get_selected_as_identity():
    item=row();unknown='private_vendor_extension_do_not_print';item[unknown]={'private_name':'not exported'}
    value=m.shape(raw([item]));field=next(field for field in value['fields'] if not field['known_name'])
    assert 'name' not in field and field['name_sha256']==m.sha(m.canonical(unknown))
    assert field['value_type']=='object' and field['public_expected_match'] is None
    assert value['original_AU_predicates']['exact_seven_keys'] is False
    output=m.canonical(value)
    assert unknown.encode() not in output and b'private_name' not in output and b'not exported' not in output


@pytest.mark.parametrize('change',('ISIN','isin','code','currency','extra','null','wrong','empty','numeric','control'))
def test_known_case_variants_and_public_comparisons_never_become_acceptance(change):
    item=row()
    if change in ('ISIN','isin'):item[change]=item.pop('Isin')
    elif change=='code':item['code']=item.pop('Code')
    elif change=='currency':item['currency']=item.pop('Currency')
    elif change=='extra':item['CodeAlias']='SPY'
    elif change=='null':item['Isin']=None
    elif change=='wrong':item['Isin']='US0000000000'
    elif change=='empty':item['Name']=''
    elif change=='numeric':item['Name']=123
    else:item['Name']='synthetic\ncontrol'
    value=m.shape(raw([item]));pred=value['original_AU_predicates']
    if change in ('null','wrong'):assert pred['would_pass_metadata_shape'] is True
    else:assert pred['would_pass_metadata_shape'] is False
    assert value['identity_accepted'] is value['price_input_admitted'] is False
    if change in ('null','wrong'):
        field=next(field for field in value['fields'] if field.get('name')=='Isin')
        assert field['public_expected_match'] is False


@pytest.mark.parametrize('value,top,count,selection',(([], 'array',0,'no_unique_object'),
    ([row(),row()],'array',2,'no_unique_object'),({'error':'private error message'},'object',None,'top_object'),
    ('private error','string',None,'no_unique_object'),(None,'null',None,'no_unique_object'),
    (True,'boolean',None,'no_unique_object'),(123,'number',None,'no_unique_object')))
def test_no_first_row_or_value_inference_for_nonunique_or_error_envelope(value,top,count,selection):
    result=m.shape(raw(value))
    assert result['top_level_type']==top and result['array_row_count']==count and result['field_selection']==selection
    if selection=='no_unique_object':assert result['fields']==[]
    assert result['original_AU_predicates']['would_pass_metadata_shape'] is False
    assert b'private error' not in m.canonical(result)


@pytest.mark.parametrize('value',(b'[{"Code":"SPY","Code":"OTHER"}]',b'[{"x":{"a":1,"a":2}}]',b'NaN',b'not JSON',b'[',b'\xff'))
def test_duplicate_nested_duplicate_and_malformed_JSON_refuse_finitely(value):
    fails('shape',lambda:m.shape(value))


@pytest.mark.parametrize('kind',('extra','name_leak','unknown_match','numeric_flag','inventory','predicate','grant'))
def test_closed_output_rejects_raw_values_unwhitelisted_names_and_forged_flags(kind):
    value=m.shape(raw([row()]))
    if kind=='extra':value['raw_row']=row()
    elif kind=='name_leak':value['fields'][0]['name']='private_unknown_name'
    elif kind=='unknown_match':
        item=value['fields'][0];item['known_name']=False;item.pop('name');item['public_expected_match']=True
    elif kind=='numeric_flag':value['fields'][0]['ASCII_string']=1
    elif kind=='inventory':value['field_inventory_sha256']='f'*64
    elif kind=='predicate':value['original_AU_predicates']['would_pass_metadata_shape']=False
    else:value['identity_accepted']=True
    if kind in ('name_leak','unknown_match','numeric_flag'):value['field_inventory_sha256']=m.sha(m.canonical(value['fields']))
    fails('output',lambda:m.validate_shape(value))


def test_known_name_claim_cannot_smuggle_unknown_field_even_with_matching_hashes():
    value=m.shape(raw([row()]));field=value['fields'][0]
    field.update(name='private_unknown_field_name',name_sha256=m.sha(m.canonical('private_unknown_field_name')),
        public_expected_match=None)
    value['field_inventory_sha256']=m.sha(m.canonical(value['fields']))
    fails('output',lambda:m.validate_shape(value))


def test_native_policy_is_exact_one_metadata_leaf_no_history_controls_or_network():
    policy=m.native_profile()
    assert '(deny network*)' in policy and '(deny process-exec (literal "/usr/bin/security"))' in policy
    assert '/Library/Keychains' in policy and 'remote tcp' not in policy
    assert m.DATA_PLAN['au_metadata']['relative_path'] in policy
    assert f'(require-not (literal "{m.CONTROL.parent}"))' in policy
    assert f'(require-not (subpath "{m.CONTROL.parent}"))' not in policy
    for forbidden in ('history-private.json','requests.jsonl','report.json','claim.json','R326-20261027-AR/',str(m.au.ar.worker.previous.PACKAGE)):
        assert forbidden not in policy


@pytest.fixture
def store_scope(monkeypatch,tmp_path):
    monkeypatch.setattr(m,'CONTROL',tmp_path/'parent'/'AV');monkeypatch.setattr(m,'_security',lambda fd:('synthetic',))
    def walk(path):
        chain=tuple((os.stat(Path(*path.parts[:i+1])).st_dev,os.stat(Path(*path.parts[:i+1])).st_ino) for i in range(1,len(path.parts)))
        return os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW),chain
    monkeypatch.setattr(m.admitted,'_storage_module',lambda:NS(_walk=walk));return m.CONTROL


def test_own_claim_exclusive_retained_no_reuse_or_third_file(store_scope):
    with m.Store() as store:
        store.write('claim.json',b'{}');store.write('result-metadata.json',b'{}');store.verify()
        fails('output_bound',lambda:store.write('third.json',b'{}'))
    fails('claim_spent',m.Store)


@pytest.mark.parametrize('failure',(None,'read','return','postflight','store_return'))
def test_claim_bytepin_and_guard_normal_return_precede_result_and_emission(monkeypatch,failure):
    events=[];body=raw([row()]);plan={'au_metadata':{'relative_path':m.DATA_PLAN['au_metadata']['relative_path'],**m.pin(body)}}
    monkeypatch.setattr(m,'DATA_PLAN',plan)
    class Store:
        def __enter__(self):return self
        def __exit__(self,*_):
            events.append('store-return')
            if failure=='store_return':raise m.Refused('output_changed')
        def write(self,name,raw):events.append(name)
        def verify(self):events.append('store-check')
    class Guard:
        def __init__(self,value,*,deadline):assert value==plan
        def __enter__(self):events.append('guard-enter');return self
        def __exit__(self,kind,*_):
            events.append('guard-normal' if kind is None else 'guard-exception')
            if failure=='return' and kind is None:raise m.guard_module.Refused('named_changed')
        def read_all_once(self):
            events.append('authenticated-read')
            if failure=='read':raise m.guard_module.Refused('byte_pin')
            return {'au_metadata':body}
        def verify(self):events.append('guard-check')
        def receipt(self):return {'synthetic':'receipt'}
    monkeypatch.setattr(m,'Store',Store);monkeypatch.setattr(m.guard_module,'FixedDataGuard',Guard)
    monkeypatch.setattr(m.guard_module,'validate_receipt',lambda value,plan:value)
    original=m.shape
    def shape(raw):events.append('shape');return original(raw)
    monkeypatch.setattr(m,'shape',shape)
    def preflight(*_):
        events.append('postflight')
        if failure=='postflight':raise m.Refused('source_pin')
    monkeypatch.setattr(m,'preflight',preflight);monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    if failure is None:
        output=m.run(args(),time.monotonic()+20)
        assert output.endswith(b'\n')
        assert events.index('claim.json')<events.index('authenticated-read')<events.index('shape')
        assert events.index('guard-normal')<events.index('postflight')<events.index('result-metadata.json')<events.index('store-return')
    else:
        with pytest.raises((m.Refused,m.guard_module.Refused)):m.run(args(),time.monotonic()+20)
        if failure!='store_return':assert 'result-metadata.json' not in events
    assert events.count('authenticated-read')<=1


def test_only_fixed_metadata_bytes_are_parsed_even_if_guard_fixture_supplies_wrong_leaf(monkeypatch):
    import inspect
    source=inspect.getsource(m.run)
    assert source.index('guard.read_all_once()')<source.index('pin(raw)')<source.index('shape(raw)')
    assert source.count("['au_metadata']")==2
    assert 'history' not in source and 'au.run(' not in source and 'au.main(' not in source


def test_external_actual_exit_is_required_for_success_and_failure_never_accepted_as_success(monkeypatch):
    value={'binding':m.binding(args()),'failure_code':'shape','allocation_unknown':True,**m.FALSE_FLAGS}
    output=m.canonical(value)+b'\n'
    assert m.validate_output(output,2,args())==value
    fails('output',lambda:m.validate_output(output,0,args()))
    fails('output',lambda:m.validate_output(output,False,args()))


@pytest.mark.parametrize('change',(None,'nonzero','normal_return','failure_fact','source_pin','guard_pin','grant'))
def test_success_output_joins_actual0_fixed_SOURCE_and_normal_guard_receipt(monkeypatch,change):
    body=raw([row()]);plan={'au_metadata':{'relative_path':m.DATA_PLAN['au_metadata']['relative_path'],**m.pin(body)}}
    monkeypatch.setattr(m,'DATA_PLAN',plan)
    receipt={'schema':m.guard_module.SCHEMA+'-receipt',
        'profile_sha256':m.sha(m.canonical(m.guard_module.profile_record(plan))),
        'files':{'au_metadata':{**plan['au_metadata'],'current_metadata_sha256':'a'*64,'current_security_sha256':'b'*64}},
        'fresh_current_security_authenticated':True,'fixed_bytes_authenticated':True,'requires_normal_return_before_use':True,
        'historical_continuity_proven':False,'continuous_integrity_proven':False}
    result={'schema':m.SCHEMA+'-result','shape':m.shape(body),'source_guard_receipt':receipt,
        'source_guard_normal_return':True,'AU_failure_binding_sha256':m.sha(m.canonical(m.observed_failure())),**m.FALSE_FLAGS}
    actual=0
    if change=='nonzero':actual=2
    elif change=='normal_return':result['source_guard_normal_return']=False
    elif change=='failure_fact':result['AU_failure_binding_sha256']='c'*64
    elif change=='source_pin':result['shape']['source_pin']['sha256']='d'*64
    elif change=='guard_pin':result['source_guard_receipt']['files']['au_metadata']['sha256']='e'*64
    elif change=='grant':result['identity_accepted']=True
    output=m.canonical({'binding':m.binding(args()),'result':result})+b'\n'
    if change is None:assert m.validate_output(output,actual,args())['result']==result
    else:
        with pytest.raises((m.Refused,m.guard_module.Refused)):m.validate_output(output,actual,args())


def test_host_source_and_profile_preflight_are_exact_and_no_operational_callbacks():
    import inspect
    source=inspect.getsource(m.preflight)
    for text in ("sys.platform=='darwin'",'(3,13)','Path(sys.executable)==PYTHON',"['status','--porcelain']",'cat-file','args.profile_sha256'):
        assert text in source
    whole=inspect.getsource(m)
    assert 'au.run(' not in whole and 'load_key(' not in whole and 'requests.' not in whole
