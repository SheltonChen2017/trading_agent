"""Synthetic temporal/precision evidence; production DATA and all networks denied."""
import ast
import copy
from contextlib import ExitStack
from datetime import date, timedelta
from decimal import Decimal, localcontext, ROUND_UP
import inspect
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace as NS

import pytest

from scripts import inspect_arv2_r336_remx_fractional as m
from scripts import inspect_arv2_r335_remx_fields as helper


def args():
    return NS(expected_head='a'*40, caller_sha256='b'*64, profile_sha256='c'*64)


def refuse(code, call):
    with pytest.raises(m.Refused) as caught:
        call()
    assert m.finite(caught.value) == code


@pytest.mark.parametrize('context_precision',[1,2])
@pytest.mark.parametrize('token,places,micro', [
    ('1.5',1,True), ('1.2300',2,True), ('0.000001',6,True),
    ('100.0000010000',6,True), ('0.0000001000',7,False),
    ('123.1234567890123456789012345678900',29,False), ('1e-9999',9999,False),
])
def test_exact_precision_uses_digits_not_decimal_context_rounding(token, places, micro,context_precision):
    value = Decimal(token)
    before = value.as_tuple()
    with localcontext() as context:
        context.prec = context_precision
        context.rounding = ROUND_UP
        actual = m.fractional_precision(value)
    assert actual == {'encoded_decimal_scale':max(0,-before.exponent),
                      'decimal_places':places, 'at_most_six_decimal_places':micro,
                      'exact_microshare_increment':micro}
    assert value.as_tuple() == before


@pytest.mark.parametrize('value', [Decimal('0'), Decimal('1.0000'), Decimal('-0.1'),
    Decimal('NaN'), Decimal('sNaN'), Decimal('Infinity'), '0.1', True, 0.1])
def test_precision_rejects_integer_nonfinite_negative_and_non_decimal(value):
    refuse('precision', lambda: m.fractional_precision(value))


@pytest.fixture
def scenario(monkeypatch):
    old = [(date(2005,1,4)+timedelta(days=i)).isoformat() for i in range(322)] + ['2006-06-30']
    ETF = [(date(2010,10,28)+timedelta(days=i)).isoformat() for i in range(3995)]
    fractional_dates = [(date(2026,2,10)+timedelta(days=i)).isoformat() for i in range(20)]
    tokens = ['1.2300', '0.000001', '1.0000001', '12.00001000']*5
    rows = [(session, '1') for session in old+ETF]
    rows += list(zip(fractional_dates, tokens, strict=True)) + [('2026-10-16','1')]
    records = [(session+',1,2,1,2,'+volume).encode('ascii') + (b'\r\n' if i%2 else b'\n')
               for i,(session,volume) in enumerate(rows)]
    # A complete final EOF record remains byte-for-byte preserved.
    records[-1] = records[-1].rstrip(b'\r\n')
    raw = b''.join(records)
    monkeypatch.setattr(m, 'REMX_PIN', m.pin(raw))
    listing = {'name':'Synthetic ETF','first_date':'2010-10-28','last_date':'2026-10-16'}
    calls = []
    class Partition:
        def to_record(self):
            return {'metadata_partition_matches_policy':True}
    def validate(metadata):
        calls.append(copy.deepcopy(metadata))
        assert metadata == {'raw_member_pin':m.REMX_PIN,'ticker':'REMX','listing':listing,
            'segments':[{'first_date':first,'last_date':last,'row_count':count}
                        for _,first,last,count in m.ERAS], 'total_row_count':4339}
        return Partition()
    remx = NS(validate_partition=validate, profile_sha256=lambda:m.PARTITION_SHA256)
    def inspect_raw(value=raw):
        return m.inspect_fractional(value,listing,remx,helper)
    return NS(raw=raw, records=records, rows=rows, remx=remx, listing=listing,
              inspect=inspect_raw, calls=calls, fractional_dates=fractional_dates)


def test_full_source_temporal_precision_counts_and_private_exact_records(scenario):
    public, private = scenario.inspect()
    assert public['temporal_counts'] == {'before_cutoff':13,'at_cutoff':1,'after_cutoff':6}
    assert public['fractional_scale_counts'] == [
        {'decimal_places':2,'row_count':5}, {'decimal_places':5,'row_count':5},
        {'decimal_places':6,'row_count':5}, {'decimal_places':7,'row_count':5}]
    assert public['at_most_six_decimal_places_count'] == public['exact_microshare_increment_count'] == 15
    assert public['over_six_decimal_places_count'] == public['not_microshare_increment_count'] == 5
    assert len(private['fractional_records']) == 20
    for index, record in enumerate(private['fractional_records'], start=4318):
        assert record['source_record_ordinal'] == index
        assert bytes.fromhex(record['source_record_hex']) == scenario.records[index]
        original = scenario.records[index].rstrip(b'\r\n').decode('ascii').split(',')
        assert record['original_fields'] == original
    assert scenario.calls and all(private[name] is False for name in m.FALSE_FLAGS)
    assert b'2026-02-10' not in m.canonical(public)
    assert b'source_record_hex' not in m.canonical(public)
    assert 'original_fields' not in public


def test_source_pin_is_checked_before_any_parser(scenario, monkeypatch):
    def forbidden(*_):
        pytest.fail('source bytes parsed before pin match')
    monkeypatch.setattr(helper,'line_ending_evidence',forbidden)
    refuse('source_pin',lambda:scenario.inspect(scenario.raw+b'changed'))


def test_old_D_entrypoints_are_never_invoked_or_globals_patched(scenario,monkeypatch):
    original = (helper.ROOT,helper.CONTROL,helper.REMX_PIN,helper.LEXICAL_EVIDENCE)
    def forbidden(*_,**__):
        pytest.fail('old operation or whole member inspector invoked')
    for name in ('worker','parent','preflight','load_modules','inspect_member','profile_record','Store'):
        monkeypatch.setattr(helper,name,forbidden)
    scenario.inspect()
    assert (helper.ROOT,helper.CONTROL,helper.REMX_PIN,helper.LEXICAL_EVIDENCE) == original


@pytest.mark.parametrize('change,code', [('fraction_old','volume'),('remove_fraction','volume'),
    ('negative','volume'),('nonfinite','volume'),('bare_CR','line_ending'),('bad_OHLC','source_data'),
    ('date_duplicate','date_order'),('short_row','row_shape')])
def test_source_changes_do_not_turn_anomalies_into_admissible_rows(scenario,monkeypatch,change,code):
    records = list(scenario.records)
    if change == 'fraction_old': records[0] = records[0].replace(b',1\n',b',1.5\n')
    elif change == 'remove_fraction': records[4318] = records[4318].replace(b',1.2300\n',b',1\n')
    elif change == 'negative': records[4318] = records[4318].replace(b',1.2300\n',b',-1.23\n')
    elif change == 'nonfinite': records[4318] = records[4318].replace(b',1.2300\n',b',NaN\n')
    elif change == 'bare_CR': records[100] = records[100].replace(b'\n',b'\r')
    elif change == 'bad_OHLC': records[0] = records[0].replace(b',1,2,1,2,',b',1,1,2,2,')
    elif change == 'date_duplicate': records[1] = records[1].replace(records[1][:10],records[0][:10])
    else: records[0] = b'2005-01-04,1,2\n'
    raw = b''.join(records)
    monkeypatch.setattr(m,'REMX_PIN',m.pin(raw))
    refuse(code,lambda:scenario.inspect(raw))


def test_partition_refusal_and_false_profile_are_not_waived(scenario):
    scenario.remx.validate_partition = lambda metadata:NS(to_record=lambda:{'metadata_partition_matches_policy':False})
    refuse('partition',scenario.inspect)
    scenario.remx.validate_partition = lambda metadata:NS(to_record=lambda:{'metadata_partition_matches_policy':True})
    scenario.remx.profile_sha256 = lambda:'f'*64
    refuse('partition',scenario.inspect)


@pytest.mark.parametrize('change',['temporal','duplicate_cutoff','precision','micro','duplicate_scale','boolean','admission','private_rows','cutoff'])
def test_public_counts_are_closed_consistent_and_cannot_disclose_records(scenario,change):
    public,_ = scenario.inspect()
    if change == 'temporal': public['temporal_counts']['at_cutoff'] += 1
    elif change == 'duplicate_cutoff': public['temporal_counts']={'before_cutoff':0,'at_cutoff':20,'after_cutoff':0}
    elif change == 'precision': public['at_most_six_decimal_places_count'] += 1
    elif change == 'micro': public['exact_microshare_increment_count'] += 1
    elif change == 'duplicate_scale': public['fractional_scale_counts'][1]['decimal_places'] = 2
    elif change == 'boolean': public['old_integer_volume_count'] = True
    elif change == 'admission': public['RAW_volume_units_admitted'] = True
    elif change == 'private_rows': public['records'] = ['SYNTHETIC']
    else: public['cutoff'] = '2020-04-15'
    refuse('output',lambda:m.validate_inspection(public))


def result_for(scenario):
    public,private=scenario.inspect()
    return {'schema':m.SCHEMA,'complete':True,'inspection':public,'private_pin':m.pin(m.canonical(private)),
        'original_member_pin':m.REMX_PIN,'archive_pin':m.ARCHIVE_PIN,'source_guard_normal_return':True,**m.FALSE_FLAGS}


def envelope_for(scenario):
    result=result_for(scenario)
    packet={'binding':m.binding(args()),'result':result}
    packet['report_pin']=m.pin(m.canonical(packet))
    raw=m.canonical(packet)+b'\n'
    return raw, {'binding':m.binding(args()),'actual_child_exit':0,'output_authenticated':True,
        'child_stdout_pin':m.pin(raw),'child_stderr_byte_count':0,'outcome':packet}


def test_actual_exits_and_matching_report_pin_are_mandatory(scenario):
    raw,parent=envelope_for(scenario)
    assert m.validate_envelope(raw,0,args())['result']['complete'] is True
    for actual in (True,None,2,-9):
        refuse('child_failure',lambda:m.validate_envelope(raw,actual,args()))
    encoded=m.canonical(parent)+b'\n'
    assert m.validate_parent_output(encoded,0,args())['result']['complete'] is True
    refuse('output',lambda:m.validate_parent_output(encoded,2,args()))
    bad=copy.deepcopy(parent);bad['outcome']['report_pin']['sha256']='f'*64
    bad['child_stdout_pin']=m.pin(m.canonical(bad['outcome'])+b'\n')
    refuse('output',lambda:m.validate_parent_output(m.canonical(bad)+b'\n',0,args()))


@pytest.mark.parametrize('field,value',[('source_guard_normal_return',False),('volume_rounded',True),
    ('price_input_admitted',True),('original_member_pin',{'byte_count':1,'sha256':'a'*64})])
def test_source_and_false_flags_cannot_be_forged_as_clearance(scenario,field,value):
    result=result_for(scenario);result[field]=value
    refuse('output',lambda:m.validate_result(result))


class Security:
    @staticmethod
    def snapshot(fd):
        return {'acl_empty':True,'xattrs':{}}


def own_control(tmp_path,monkeypatch):
    root=tmp_path/'root';root.mkdir(mode=0o755);root.chmod(0o755)
    path=root/'artifacts/analyst_revisions_v2/firstrate'
    path.mkdir(mode=0o700,parents=True)
    for item in (root/'artifacts',root/'artifacts/analyst_revisions_v2',path):item.chmod(0o700)
    monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m,'CONTROL',path/'R336-L')


def test_new_claim_is_exclusive_and_private_records_are_not_cleaned(tmp_path,monkeypatch):
    own_control(tmp_path,monkeypatch)
    with m.Store(Security) as store:
        store.write('claim.json',b'{}')
        store.write('private-diagnosis.json',b'{"synthetic":true}')
        store.write('report.json',b'{}')
        assert all((m.CONTROL/name).stat().st_mode&0o777==0o600 for name in ('claim.json','private-diagnosis.json','report.json'))
    refuse('claim_spent',lambda:m.Store(Security).__enter__())
    assert (m.CONTROL/'private-diagnosis.json').read_bytes()==b'{"synthetic":true}'


def test_late_output_change_and_unexpected_leaf_are_not_absorbed(tmp_path,monkeypatch):
    own_control(tmp_path,monkeypatch)
    with pytest.raises(m.Refused):
        with m.Store(Security) as store:
            store.write('claim.json',b'{}')
            (m.CONTROL/'claim.json').write_bytes(b'{"changed":true}')
            store.verify()
    monkeypatch.setattr(m,'CONTROL',m.CONTROL.parent/'another-synthetic')
    with pytest.raises(m.Refused):
        with m.Store(Security) as store:
            store.write('claim.json',b'{}');(m.CONTROL/'unexpected.json').write_bytes(b'{}')
            store.write('report.json',b'{}')


def test_original_held_named_source_and_streaming_hash_reject_change(tmp_path):
    path=tmp_path/'synthetic';path.write_bytes(b'synthetic')
    with m.HeldFile(path,maximum=100,expected=m.pin(b'synthetic'),deadline=time.monotonic()+299) as held:
        assert held.read()==b'synthetic'
        m.hash_held(held,m.pin(b'synthetic'))
        refuse('source_pin',lambda:m.hash_held(held,m.pin(b'other')))
    with pytest.raises(m.Refused):
        with m.HeldFile(path,maximum=100,deadline=time.monotonic()+299) as held:
            path.write_bytes(b'changed!!');held.verify()


def test_selected_sources_are_authenticated_before_explicit_compilation(tmp_path,monkeypatch):
    root=tmp_path/'root';(root/'scripts').mkdir(parents=True)
    (root/'scripts/synthetic.py').write_bytes(b'raise RuntimeError("MUST_NOT_EXECUTE")\n')
    monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m,'SOURCE_PINS',{'scripts/synthetic.py':'f'*64})
    with ExitStack() as stack:
        refuse('source_pin',lambda:m.bootstrap('worker',stack,time.monotonic()+299))


def test_native_policy_has_exact_USB_files_no_private_source_or_credentials():
    policy=m.native_profile()
    assert '(deny network*)' in policy and '(deny file-write* (subpath "/Volumes"))' in policy
    assert '(subpath "/Volumes")' in policy and '(subpath "'+str(m.ROOT/'artifacts')+'")' in policy
    assert 'login.keychain' not in policy
    assert '/Users/sheltonchen/Library/Keychains' in policy and '/Library/Keychains' in policy
    assert '(deny process-exec (literal "/usr/bin/security"))' in policy
    for relative in (*m.USB_PINS,m.REMX_ARCHIVE):assert '(literal "'+str(m.USB/relative)+'")' in policy
    assert 'R335-20261103-D' not in policy and 'R335-20261103-G' not in policy


def test_source_order_claim_before_USB_and_normal_return_before_private_publication():
    text=inspect.getsource(m.worker)
    assert text.index("store.write('claim.json'") < text.index('for relative,expected in USB_PINS.items()')
    assert text.index('hash_held(held,ARCHIVE_PIN)') < text.index('helper.Archive(held,expected)')
    assert text.index('sources.close()') < text.index("store.write('private-diagnosis.json'") < text.index("store.write('report.json'")
    source=inspect.getsource(m.bootstrap)
    assert 'exec(compile(' in source and '.load_modules(' not in source and 'import_module(' not in source
    assert 'helper.CONTROL=' not in inspect.getsource(m)
    assert 'helper.worker(' not in inspect.getsource(m) and 'helper.inspect_member(' not in inspect.getsource(m)
    tree=ast.parse(inspect.getsource(m.worker))
    helper_calls={node.func.attr for node in ast.walk(tree) if isinstance(node,ast.Call)
        and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name)
        and node.func.value.id=='helper'}
    assert helper_calls=={'HeldFile','Archive','listings','manifest_entry'}
    assert "preflight(args, ENTRY_DEADLINE)" in inspect.getsource(m.main)


@pytest.mark.parametrize('late_source_failure',[False,True])
def test_worker_waits_for_normal_source_return_before_either_publication(scenario,monkeypatch,late_source_failure):
    writes=[];closed=[]
    class SyntheticHeld:
        def __init__(self,path,**kwargs):self.path=Path(path)
        def __enter__(self):return self
        def __exit__(self,*_):closed.append(self.path.name)
        def read(self):return b'{}'
    class SyntheticArchive:
        container_pin=m.ARCHIVE_PIN
        def __init__(self,*_):pass
        def __enter__(self):return self
        def __exit__(self,*_):
            closed.append('archive')
            if late_source_failure:raise m.Refused('source_changed')
        def member(self,name):
            assert name==m.REMX_MEMBER
            return scenario.raw
    class SyntheticStore:
        def __init__(self,*_):pass
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def write(self,name,raw):
            if name!='claim.json':assert 'archive' in closed
            writes.append(name)
            return m.pin(raw)
    proxy=NS(HeldFile=SyntheticHeld,Archive=SyntheticArchive,
        listings=lambda raw:[{'Ticker':'REMX','Name':scenario.listing['name'],
            'First Date':scenario.listing['first_date'],'Last Date':scenario.listing['last_date']}],
        manifest_entry=lambda *args:{'byte_count':1,'md5':'0'*32},
        validate_lexical=helper.validate_lexical,line_ending_evidence=helper.line_ending_evidence,
        timestamp=helper.timestamp,price_number=helper.price_number,volume_class=helper.volume_class)
    monkeypatch.setattr(m,'bootstrap',lambda *args:{'helper':proxy,'security':Security,'remx':scenario.remx})
    monkeypatch.setattr(m,'preflight',lambda *args:None)
    monkeypatch.setattr(m,'hash_held',lambda *args:None)
    monkeypatch.setattr(m,'Store',SyntheticStore)
    actual=args();reader,writer=os.pipe();actual.intent_fd=reader
    os.write(writer,m.canonical(m.binding(actual)));os.close(writer)
    if late_source_failure:
        refuse('source_changed',lambda:m.worker(actual,time.monotonic()+299))
        assert writes==['claim.json']
    else:
        result=m.worker(actual,time.monotonic()+299)
        assert result['result']['source_guard_normal_return'] is True
        assert writes==['claim.json','private-diagnosis.json','report.json']


def test_helpers_preserve_proven_held_and_store_checks():
    for name in ('HeldFile','preflight','parent','validate_envelope','validate_parent_output'):
        assert inspect.getsource(getattr(m,name)).strip()==inspect.getsource(getattr(helper,name)).strip()
    assert inspect.getsource(m.Store).strip()==inspect.getsource(helper.Store).strip().replace(
        "('claim.json', 'report.json')","('claim.json', 'private-diagnosis.json', 'report.json')")


@pytest.mark.parametrize('field,value',[('expected_head',True),('expected_head','a'*39),
    ('caller_sha256','f'*65),('profile_sha256',None)])
def test_exact_run_arguments_refuse_missing_or_boolean_source_bindings(field,value):
    actual=args();setattr(actual,field,value)
    refuse('arguments',lambda:m.binding(actual))


def test_failure_envelope_has_no_rows_values_dates_or_retry_authority():
    old=m.ACTIVE_BINDING;m.ACTIVE_BINDING=m.binding(args())
    try:
        packet=m.failure_packet('precision')
        assert m.validate_failure(packet,args())==packet
        assert not any(key in packet for key in ('date','volume','row','source_record_ordinal','source_record_hex'))
        assert packet['attempt_reusable'] is False
    finally:m.ACTIVE_BINDING=old


def test_cli_bad_argument_never_echoes_supplied_text():
    completed=subprocess.run([sys.executable,'-I','-B',str(m.SOURCE),'--PRIVATE-SYNTHETIC'],
        cwd=m.ROOT,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
    assert completed.returncode==2 and completed.stderr==b''
    assert b'PRIVATE-SYNTHETIC' not in completed.stdout


def test_parent_alarm_is_armed_and_actual_handler_reached_before_preflight(monkeypatch):
    previous_handler=signal.getsignal(signal.SIGALRM)
    previous_timer=signal.getitimer(signal.ITIMER_REAL)
    previous_binding=m.ACTIVE_BINDING
    old_calls=[]
    signal.setitimer(signal.ITIMER_REAL,0)
    signal.signal(signal.SIGALRM,lambda *_:old_calls.append('previous_handler'))
    monkeypatch.setattr(sys,'argv',[str(m.SOURCE),'launch','--expected-head','a'*40,
        '--caller-sha256','b'*64,'--profile-sha256','c'*64])
    def parent_before_preflight(actual):
        assert m.binding(actual)==m.binding(args())
        assert 0<signal.getitimer(signal.ITIMER_REAL)[0]<=m.SECONDS
        signal.raise_signal(signal.SIGALRM)
        pytest.fail('new parent deadline handler did not interrupt')
    monkeypatch.setattr(m,'parent',parent_before_preflight)
    try:
        refuse('deadline',m.main)
        assert old_calls==[]
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,previous_handler)
        signal.setitimer(signal.ITIMER_REAL,*previous_timer)
        m.ACTIVE_BINDING=previous_binding


def test_profile_exposes_temporal_question_and_preserves_all_false_flags():
    profile=m.profile_record()
    assert profile['cutoff']=='2026-02-23' and profile['expected_preserved_fractional_ETF_rows']==20
    assert len(profile['primary_docs'])==3 and profile['archive_pin']==m.ARCHIVE_PIN
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
    assert 'not_vendor_feed_proof' in profile['cutoff_meaning']
    assert profile['normal_guard_return_before_publication'] is True
    assert 'separate_from_still_integer_Quantity' in profile['FINRA_field_distinction']
