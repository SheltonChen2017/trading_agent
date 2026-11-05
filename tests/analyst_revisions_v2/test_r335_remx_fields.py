"""Synthetic REMX-only field-shape diagnostic; all operational source reads denied."""
import ast
import copy
from contextlib import ExitStack
from datetime import date, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace as NS
import zipfile
import pytest
from scripts import inspect_arv2_r335_remx_fields as m


def args():
    return NS(expected_head='a' * 40, caller_sha256='b' * 64, profile_sha256='c' * 64)


def refuse(code, call):
    with pytest.raises(m.Refused) as caught:
        call()
    assert m.finite(caught.value) == code


def test_changed_bootstrap_source_refuses_before_any_repository_import(tmp_path, monkeypatch):
    root = tmp_path / 'root'; (root / 'scripts').mkdir(parents=True)
    (root / 'scripts' / 'synthetic.py').write_bytes(b'pass\n')
    monkeypatch.setattr(m, 'ROOT', root)
    monkeypatch.setattr(m, 'SOURCE_PINS', {'scripts/synthetic.py': 'f' * 64})
    monkeypatch.setattr(m.importlib, 'import_module', lambda *args: pytest.fail('executed before pin equality'))
    with ExitStack() as stack:
        refuse('source_pin', lambda: m.load_modules(stack, time.monotonic() + 299))


@pytest.mark.parametrize('field,value', [('expected_head', 'a' * 39), ('expected_head', True),
    ('caller_sha256', 'x' * 64), ('profile_sha256', None), ('caller_sha256', 'b' * 65)])
def test_arguments_refuse_malformed_bindings(field, value):
    value_args = args(); setattr(value_args, field, value)
    refuse('arguments', lambda: m.binding(value_args))


def test_binding_accepts_exact_source_run_pins_only():
    assert m.binding(args()) == {'schema': m.SCHEMA, 'expected_head': 'a' * 40,
        'caller_sha256': 'b' * 64, 'profile_sha256': 'c' * 64}


@pytest.mark.parametrize('raw', [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'not-json', b''])
def test_json_refuses_duplicates_constants_and_malformed(raw):
    with pytest.raises(m.Refused): m.parse(raw, 100)


def listing_raw():
    return b'Ticker,Name,First Date,Last Date\nSYN0,Synthetic,2020-01-02,2026-10-16\n'


def test_listing_schema_is_fixed_and_keeps_duplicate_symbol_candidates():
    raw = listing_raw() + b'SYN0,Other Synthetic,2000-01-03,2006-06-30\n'
    rows = m.listings(raw)
    assert len(rows) == 2 and rows[0]['Ticker'] == rows[1]['Ticker']
    assert m.listings(b'\xef\xbb\xbf' + raw) == rows
    refuse('listing', lambda: m.listings(raw.replace(b'First Date', b'Other Date')))


def test_original_held_named_file_rejects_byte_pin_symlink_and_late_replacement(tmp_path):
    source = tmp_path / 'source'; source.write_bytes(b'synthetic')
    deadline = time.monotonic() + 299
    with m.HeldFile(source, maximum=100, expected=m.pin(b'synthetic'), deadline=deadline) as held:
        assert held.read() == b'synthetic'
    with pytest.raises(m.Refused):
        with m.HeldFile(source, maximum=100, expected=m.pin(b'other'), deadline=deadline) as held: held.read()
    link = tmp_path / 'link'; link.symlink_to(source)
    with pytest.raises(OSError):
        with m.HeldFile(link, maximum=100, deadline=deadline): pass
    with pytest.raises(m.Refused):
        with m.HeldFile(source, maximum=100, deadline=deadline) as held:
            source.write_bytes(b'changed!'); held.verify()


def make_zip(path, entries):
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED) as target:
        for name, raw in entries: target.writestr(name, raw)
    raw = path.read_bytes()
    return {'byte_count': len(raw), 'md5': hashlib.md5(raw).hexdigest()}


def test_archive_fixed_MD5_before_parse_CRC_before_member_and_no_extraction(tmp_path):
    path = tmp_path / 'archive.txt'
    expected = make_zip(path, [('SYN_full_1day_UNADJUSTED.txt', b'synthetic-data')])
    with m.HeldFile(path, maximum=m.MAX_ZIP_BYTES, deadline=time.monotonic() + 299) as held:
        with m.Archive(held, expected) as archive:
            assert archive.member('missing.txt') is None
            assert archive.member('SYN_full_1day_UNADJUSTED.txt') == b'synthetic-data'
            assert archive.container_pin == m.pin(path.read_bytes())
    wrong = {**expected, 'md5': '0' * 32}
    with m.HeldFile(path, maximum=m.MAX_ZIP_BYTES, deadline=time.monotonic() + 299) as held:
        refuse('archive', lambda: m.Archive(held, wrong).__enter__())
    assert not (tmp_path / 'SYN_full_1day_UNADJUSTED.txt').exists()


def test_duplicate_or_traversal_zip_member_is_never_accepted(tmp_path):
    path = tmp_path / 'bad.zip'
    expected = make_zip(path, [('../SECRET.txt', b'synthetic')])
    with m.HeldFile(path, maximum=m.MAX_ZIP_BYTES, deadline=time.monotonic() + 299) as held:
        with m.Archive(held, expected) as archive:
            refuse('member', lambda: archive.member('../SECRET.txt'))


class Security:
    @staticmethod
    def snapshot(fd): return {'acl_empty': True, 'xattrs': {}}


def fixture_control(tmp_path, monkeypatch):
    root = tmp_path / 'root'; root.mkdir(mode=0o755); root.chmod(0o755)
    artifacts = root / 'artifacts'; artifacts.mkdir(mode=0o700)
    lane = artifacts / 'analyst_revisions_v2'; lane.mkdir(mode=0o700)
    monkeypatch.setattr(m, 'ROOT', root)
    monkeypatch.setattr(m, 'CONTROL', lane / 'firstrate/R335-A')
    return lane


def test_one_exclusive_claim_all_outputs_original_FDs_and_no_retry(tmp_path, monkeypatch):
    fixture_control(tmp_path, monkeypatch)
    with m.Store(Security) as store:
        store.write('claim.json', b'{"synthetic":true}')
        assert store.write('report.json', b'{}') == m.pin(b'{}')
        store.verify()
        assert all(stat_mode == 0o600 for stat_mode in [
            (m.CONTROL / name).stat().st_mode & 0o777 for name in ('claim.json', 'report.json')])
    refuse('claim_spent', lambda: m.Store(Security).__enter__())
    assert (m.CONTROL / 'claim.json').read_bytes() == b'{"synthetic":true}'


def test_symlink_output_ancestor_refuses_before_any_own_claim(tmp_path, monkeypatch):
    lane = fixture_control(tmp_path, monkeypatch)
    other = tmp_path / 'other'; other.mkdir()
    (lane / 'firstrate').symlink_to(other, target_is_directory=True)
    with pytest.raises((OSError, m.Refused)): m.Store(Security).__enter__()
    assert not (other / 'R335-A').exists()


def test_late_output_mutation_is_refused_and_evidence_retained(tmp_path, monkeypatch):
    fixture_control(tmp_path, monkeypatch)
    with pytest.raises(m.Refused):
        with m.Store(Security) as store:
            store.write('claim.json', b'{}')
            (m.CONTROL / 'claim.json').write_bytes(b'changed')
            store.verify()
    assert (m.CONTROL / 'claim.json').read_bytes() == b'changed'


def test_unexpected_owned_control_leaf_is_not_absorbed_by_later_own_write(tmp_path, monkeypatch):
    fixture_control(tmp_path, monkeypatch)
    with pytest.raises(m.Refused):
        with m.Store(Security) as store:
            store.write('claim.json', b'{}')
            (m.CONTROL / 'unexpected').write_bytes(b'synthetic')
            refuse('control', lambda: store.write('report.json', b'{}'))
    assert (m.CONTROL / 'unexpected').read_bytes() == b'synthetic'
    assert not (m.CONTROL / 'report.json').exists()


def test_cli_unknown_argument_never_echoes_supplied_value():
    result = subprocess.run([sys.executable, '-I', '-B', str(m.SOURCE), 'launch', '--SYNTHETIC-SECRET-ARG'],
        cwd=m.ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5,
        env={'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'})
    assert result.returncode == 2 and not result.stderr
    assert b'SYNTHETIC-SECRET' not in result.stdout
    assert json.loads(result.stdout)['failure_code'] == 'arguments'


def test_public_scope_exact_USB_and_no_retained_or_stock_DATA():
    assert all(m.sha((m.ROOT / name).read_bytes()) == pin for name, pin in m.SOURCE_PINS.items())
    assert set(m.SOURCE_PINS) == {'scripts/arv2_relocation_security.py', 'scripts/arv2_r335_remx_identity.py'}
    profile = m.profile_record(); policy = m.native_profile()
    assert profile['control'].endswith('/R335-20261103-D')
    assert len(profile['USB_pins']) == 2 and profile['allowed_archives'] == [m.REMX_ARCHIVE]
    assert profile['outputs'] == ['claim.json', 'report.json']
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
    assert '(deny network*)' in policy and '(deny file-write* (subpath "/Volumes/SANDISK"))' in policy
    assert '/Users/sheltonchen/Library/Keychains' in policy and '/Library/Keychains' in policy
    assert '/usr/bin/security' in policy and 'identity-demand-private' not in policy
    assert 'Stocks_Complete' not in policy and 'arv2_r327' not in repr(profile)
    assert '1-Day_Unadjusted' not in policy and 'private-diagnosis' not in policy
    assert set(m.ARCHIVES) == {m.REMX_ARCHIVE}


def test_bootstrap_only_two_pinned_dependencies():
    with ExitStack() as stack:
        modules = m.load_modules(stack, time.monotonic() + 299)
        assert set(modules) == {'security', 'remx'}


def test_manifest_returns_only_bounded_transport_evidence():
    relative = m.REMX_ARCHIVE
    manifest = {relative[:-4]: {'path': 'SYNTHETIC-SECRET', 'url': 'SYNTHETIC-SECRET',
        'bytes': 123, 'md5': 'a' * 32, 'ok': True, 'fetched': '2026-10-17'}}
    assert m.manifest_entry(manifest, relative) == {'byte_count': 123, 'md5': 'a' * 32}
    refuse('scope', lambda: m.manifest_entry(manifest, 'market/Stocks_Complete_10_000+_Tickers/1-Day_Unadjusted_Archive_1.zip'))
    assert 'SYNTHETIC' not in repr(m.manifest_entry(manifest, relative))


@pytest.mark.parametrize('field,value', [('ok', False), ('bytes', True), ('bytes', m.MAX_ZIP_BYTES + 1), ('md5', 'bad')])
def test_manifest_refuses_bad_transport_evidence(field, value):
    relative = m.REMX_ARCHIVE
    manifest = {relative[:-4]: {'path': 'not-used', 'url': 'not-used', 'bytes': 123, 'md5': 'a' * 32, 'ok': True, 'fetched': 'now'}}
    manifest[relative[:-4]][field] = value
    refuse('manifest', lambda: m.manifest_entry(manifest, relative))


@pytest.mark.parametrize('value,expected', [('0', 'integer_nonnegative_count'), ('42.000', 'integer_nonnegative_count'),
    ('0.25', 'fractional_nonnegative_count'), ('-0.5', 'negative_finite_count'), ('NaN', 'nonfinite_count'),
    ('sNaN', 'nonfinite_count'), ('-Infinity', 'nonfinite_count'), ('1e-4', 'fractional_nonnegative_count'),
    ('1E4', 'integer_nonnegative_count'), ('+0', 'integer_nonnegative_count'), ('', 'malformed_count'),
    (' 1', 'malformed_count'), ('1,000', 'malformed_count'), ('1_000', 'malformed_count'),
    ('1e99999', 'malformed_count'), ('x' * 129, 'malformed_count')])
def test_volume_classes_are_counts_without_normalizing_or_returning_values(value, expected):
    category, lexical = m.volume_class(value)
    assert category == expected and set(lexical) == set(m.VOLUME_LEXICAL_COUNTS)
    assert all(type(item) is int and item in (0, 1) for item in lexical.values())
    assert value not in repr((category, lexical)) if value and value != '0' else True


class Policy:
    @staticmethod
    def validate_partition(metadata):
        assert metadata['raw_member_pin'] == m.REMX_PIN
        assert metadata['ticker'] == 'REMX'
        assert metadata['listing'] == listing()
        assert metadata['segments'] == [dict(first_date=first, last_date=last, row_count=count) for _, first, last, count in m.ERAS]
        assert metadata['total_row_count'] == 4339
        return NS(to_record=lambda: {'metadata_partition_matches_policy': True})
    @staticmethod
    def profile_sha256(): return '4674c20222e26c369abbd654c61ed14f08a7e49861d34251b129db49d392632e'


def listing():
    return {'name': 'Vaneck Vectors Rare Earth/Strategic Metals ETF', 'first_date': '2010-10-28', 'last_date': '2026-10-16'}


def synthetic_raw(volume='1'):
    rows=[]
    for ordinal, first, last, count in m.ERAS:
        dates=[(date.fromisoformat(first) + timedelta(days=index)).isoformat() for index in range(count - 1)] + [last]
        rows.extend(value.encode() + b',1,2,1,1,' + volume.encode() for value in dates)
    return b'\n'.join(rows[:-5]) + b'\n' + b'\r\n'.join(rows[-5:]) + b'\r\n'


def inspect_fixture(monkeypatch, raw):
    monkeypatch.setattr(m, 'REMX_PIN', m.pin(raw))
    return m.inspect_member(raw, listing(), Policy)


def result_fixture(monkeypatch, raw=None):
    raw=synthetic_raw() if raw is None else raw
    inspection=inspect_fixture(monkeypatch, raw)
    return {'schema':m.SCHEMA, 'complete':True, 'inspection':inspection, 'original_member_pin':m.pin(raw),
        'archive_pin': {'byte_count': 123, 'sha256': 'a' * 64}, 'source_guard_normal_return':True, **m.FALSE_FLAGS}


def test_all_two_eras_count_fractional_or_other_volume_without_price_admission(monkeypatch):
    volumes=('1','0.5','-1','NaN','garbage')
    raw=synthetic_raw()
    lines=raw.splitlines()
    for index, value in enumerate(volumes):
        lines[index]=lines[index].rsplit(b',',1)[0]+b','+value.encode()
        lines[323+index]=lines[323+index].rsplit(b',',1)[0]+b','+value.encode()
    raw=b'\n'.join(lines)+b'\n'; before=m.pin(raw)
    value=result_fixture(monkeypatch, raw)
    for actual, (_, first, last, count) in zip(value['inspection']['eras'],m.ERAS):
        assert actual['first_date']==first and actual['last_date']==last
        assert actual['integer_nonnegative_count']==count-4
        assert all(actual[key]==1 for key in m.VOLUME_CLASSES[1:])
    assert value['inspection']['volume_values_accepted'] is False
    assert all(value[key] is False for key in m.FALSE_FLAGS)
    assert m.pin(raw)==before and m.validate_result(value)==value
    assert b',1,2,1,1,' not in m.canonical(value)


def test_empty_sixth_field_counts_malformed_without_weakening_field_count_or_OHLC(monkeypatch):
    raw=synthetic_raw('')
    value=result_fixture(monkeypatch,raw)
    assert value['inspection']['lexical_evidence']['complete_final_record'] is False
    assert all(era['malformed_count']==era['row_count'] for era in value['inspection']['eras'])
    assert m.validate_result(value)==value


@pytest.mark.parametrize('change,code', [('pin','source_pin'), ('rows','partition'), ('bare_CR','line_ending'),
    ('fields','row_shape'), ('session','session'), ('time','timestamp'), ('date_order','date_order'),
    ('price','price'), ('number','number'), ('OHLC','OHLC'), ('last','partition')])
def test_row_date_and_price_errors_remain_terminal(monkeypatch,change,code):
    raw=synthetic_raw(); lines=raw.splitlines()
    if change=='pin':
        monkeypatch.setattr(m,'REMX_PIN',m.pin(raw+b'x'))
        refuse(code,lambda:m.inspect_member(raw,listing(),Policy));return
    if change=='rows':lines.pop()
    elif change=='bare_CR':lines[0]+=b'\r'
    elif change=='fields':lines[0]+=b',secret'
    elif change=='session':lines[0]=lines[0].replace(b'2005-01-04',b'2005-99-99')
    elif change=='time':lines[0]=lines[0].replace(b'2005-01-04',b'2005-01-04 01:00:00')
    elif change=='date_order':lines[1]=lines[0]
    elif change=='price':lines[0]=lines[0].replace(b',1,2,1,1,',b',0,2,1,1,')
    elif change=='number':lines[0]=lines[0].replace(b',1,2,1,1,',b',NaN,2,1,1,')
    elif change=='OHLC':lines[0]=lines[0].replace(b',1,2,1,1,',b',1,2,3,1,')
    else:lines[-1]=lines[-1].replace(b'2026-10-16',b'2026-10-15')
    # Do not convert bare CR into valid CRLF when forming the synthetic failure.
    raw=b'\n'.join(lines)+b'\n'
    if change=='bare_CR':raw=raw.replace(b'\r\n',b'\rX\n',1)
    monkeypatch.setattr(m,'REMX_PIN',m.pin(raw))
    refuse(code,lambda:m.inspect_member(raw,listing(),Policy))


@pytest.mark.parametrize('change', ['raw','flag','bool_count','negative','sum','era','boundary','aliasflag','pin','normal_return','extra'])
def test_external_result_is_closed_and_all_counts_strict(monkeypatch,change):
    value=result_fixture(monkeypatch)
    if change=='raw':value['inspection']['raw_volume']='SECRET'
    elif change=='flag':value['price_input_admitted']=True
    elif change=='bool_count':value['inspection']['eras'][0]['nonfinite_count']=False
    elif change=='negative':value['inspection']['eras'][0]['malformed_count']=-1
    elif change=='sum':value['inspection']['eras'][0]['integer_nonnegative_count']-=1
    elif change=='era':value['inspection']['eras'][0]['era_ordinal']=False
    elif change=='boundary':value['inspection']['eras'][0]['first_date']='2005-01-05'
    elif change=='aliasflag':value['inspection']['volume_values_accepted']=0
    elif change=='pin':value['original_member_pin']['sha256']='0'*64
    elif change=='normal_return':value['source_guard_normal_return']=False
    else:value['secret']='SECRET'
    refuse('output',lambda:m.validate_result(value))


def test_actual_exit_and_report_pin_mandatory_even_for_diagnostic_success(monkeypatch):
    value=result_fixture(monkeypatch);report={'binding':m.binding(args()),'result':value}
    outcome={**report,'report_pin':m.pin(m.canonical(report))};raw=m.canonical(outcome)+b'\n'
    assert m.validate_envelope(raw,0,args())==outcome
    for actual in (None,True,2,-9):refuse('child_failure',lambda:m.validate_envelope(raw,actual,args()))
    outcome['report_pin']['sha256']='0'*64
    refuse('output',lambda:m.validate_envelope(m.canonical(outcome)+b'\n',0,args()))


def test_finite_failure_preserves_actual_two_and_never_becomes_success(monkeypatch):
    monkeypatch.setattr(m,'ACTIVE_BINDING',m.binding(args()));monkeypatch.setattr(m,'CLAIM_STATE','consumed')
    monkeypatch.setattr(m,'FAILURE_STAGE','REMX_fields');monkeypatch.setattr(m,'LEXICAL_EVIDENCE',None)
    failure=m.failure_packet('OHLC')
    parent={'binding':m.binding(args()),'actual_child_exit':2,'output_authenticated':True,
        'child_stdout_pin':m.pin(m.canonical(failure)+b'\n'),'child_stderr_byte_count':0,'failure':failure}
    actual=m.validate_parent_output(m.canonical(parent)+b'\n',2,args())
    assert actual['accepted'] is False and actual['failure']['failure_code']=='OHLC'
    assert actual['actual_child_exit']==2 and actual['output_authenticated'] is True
    refuse('output',lambda:m.validate_parent_output(m.canonical(parent)+b'\n',0,args()))


def test_dynamic_output_security_mismatch_is_not_ignored(tmp_path,monkeypatch):
    fixture_control(tmp_path,monkeypatch)
    class Changing(Security):
        changed=False
        @staticmethod
        def snapshot(fd):return {'synthetic_security_state':Changing.changed}
    with pytest.raises(m.Refused):
        with m.Store(Changing) as store:
            store.write('claim.json',b'{}');Changing.changed=True;store.verify()


def test_worker_contains_no_identity_or_stock_read_and_unchanged_source_guards_close_before_report():
    text=m.SOURCE.read_text();tree=ast.parse(text)
    worker=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='worker')
    rendered=ast.get_source_segment(text,worker)
    assert 'DATA_PLAN' not in text and 'stock_archive' not in rendered and 'FixedDataGuard' not in text
    assert rendered.index("store.write('claim.json'")<rendered.index('for relative, expected in USB_PINS')
    assert rendered.index('sources.close()')<rendered.index("store.write('report.json'")
    assert "Store(modules['security'])" in rendered
    old=m.ROOT/'scripts/inspect_arv2_r335_firstrate_coverage_v3.py'
    frozen=old.read_bytes();assert hashlib.sha256(frozen).hexdigest()=='827259694d4746b715e9280c48ec2fcdc56c74548b30e2f224f9ea25ec26522e'
    before=ast.parse(frozen)
    names=('HeldFile','Archive','parent','validate_envelope','validate_parent_output','Parser','main','preflight','safe_env')
    for name in names:
        a=next(node for node in before.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name==name)
        b=next(node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name==name)
        assert ast.dump(a,include_attributes=False)==ast.dump(b,include_attributes=False)


def test_worker_dynamic_read_set_claim_order_and_normal_return_before_output(monkeypatch):
    raw=synthetic_raw();inspection=inspect_fixture(monkeypatch,raw)
    events=[];open_count=0
    manifest={m.REMX_ARCHIVE[:-4]:{'path':'PRIVATE-UNUSED','url':'PRIVATE-UNUSED','bytes':123,'md5':'a'*32,'ok':True,'fetched':'now'}}
    listing_bytes=b'Ticker,Name,First Date,Last Date\nREMX,Vaneck Vectors Rare Earth/Strategic Metals ETF,2010-10-28,2026-10-16\n'
    fixed={m.USB/'manifest.json':m.canonical(manifest),m.USB/(m.ETF_DIR+'Ticker_Listing.txt'):listing_bytes}
    class Held:
        def __init__(self,path,**kwargs):
            self.path=path
            assert path in (*fixed,m.USB/m.REMX_ARCHIVE)
        def __enter__(self):
            nonlocal open_count
            open_count+=1;events.append(('enter',self.path));return self
        def read(self):events.append(('read',self.path));return fixed[self.path]
        def __exit__(self,*args):
            nonlocal open_count
            open_count-=1;events.append(('exit',self.path))
    class Archive:
        container_pin={'byte_count':123,'sha256':'a'*64}
        def __init__(self,*args):pass
        def __enter__(self):return self
        def member(self,name):
            assert name==m.REMX_MEMBER;events.append(('member',name));return raw
        def __exit__(self,*args):events.append(('archive_return',None))
    class Store:
        def __init__(self,security):assert security is Security
        def __enter__(self):return self
        def write(self,name,data):
            assert name in ('claim.json','report.json')
            assert open_count==0
            events.append(('write',name));return m.pin(data)
        def __exit__(self,*args):events.append(('output_return',None))
    monkeypatch.setattr(m,'preflight',lambda *args:None)
    monkeypatch.setattr(m,'load_modules',lambda *args:{'security':Security,'remx':Policy})
    monkeypatch.setattr(m,'HeldFile',Held);monkeypatch.setattr(m,'Archive',Archive);monkeypatch.setattr(m,'Store',Store)
    value_args=args();reader,writer=os.pipe();value_args.intent_fd=reader
    os.write(writer,m.canonical(m.binding(value_args)));os.close(writer)
    output=m.worker(value_args,time.monotonic()+299)
    assert m.validate_result(output['result'])==output['result']
    assert [value for event,value in events if event=='read']==list(fixed)
    assert [value for event,value in events if event=='write']==['claim.json','report.json']
    assert events[0]==('write','claim.json') and open_count==0
    assert events.index(('archive_return',None))<events.index(('write','report.json'))
    assert output['result']['retained_identity_DATA_read'] is False
    assert output['result']['stock_archive_read'] is False


def test_real_offline_validation_preserves_observed_two_without_control_reads(monkeypatch):
    monkeypatch.setattr(m,'ACTIVE_BINDING',m.binding(args()));monkeypatch.setattr(m,'CLAIM_STATE','consumed')
    monkeypatch.setattr(m,'FAILURE_STAGE','REMX_fields');monkeypatch.setattr(m,'LEXICAL_EVIDENCE',None)
    failure=m.failure_packet('OHLC')
    value={'binding':m.binding(args()),'actual_child_exit':2,'output_authenticated':True,
        'child_stdout_pin':m.pin(m.canonical(failure)+b'\n'),'child_stderr_byte_count':0,'failure':failure}
    result=subprocess.run([sys.executable,'-I','-B',str(m.SOURCE),'validate',
        '--expected-head',args().expected_head,'--caller-sha256',args().caller_sha256,
        '--profile-sha256',args().profile_sha256,'--actual-parent-exit','2'],cwd=m.ROOT,
        input=m.canonical(value)+b'\n',stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5,
        env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'})
    assert result.returncode==2 and not result.stderr
    output=json.loads(result.stdout)
    assert output['accepted'] is False and output['output_authenticated'] is True
    assert output['actual_child_exit']==2 and output['failure']['failure_code']=='OHLC'


def test_numeric_lexical_counts_distinguish_format_without_leaking_original_tokens():
    assert m.volume_class('1e-4')[1]['exponent_lexical_count']==1
    assert m.volume_class('-1')[1]['signed_lexical_count']==1
    assert m.volume_class('1.25')[1]['decimal_point_lexical_count']==1
    assert m.volume_class('1.00')[1]['unsigned_decimal_lexical_count']==1
    assert m.volume_class('garbage')[1]==dict.fromkeys(m.VOLUME_LEXICAL_COUNTS,0)
