"""Real tiny children and finite formatting only; no preparation or DATA use."""
import ast
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from scripts import collect_arv2_r346_preparation as m
from scripts import prepare_arv2_r346_legacy_plain as preparer


SAFE={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'}
RAW=b'{"synthetic_safe":true}\n'


def child(code):
    return [sys.executable,'-I','-B','-c',code]


def fake_validator(raw,*,actual_exit,expected_binding):
    assert raw==RAW and type(actual_exit) is int and actual_exit==0 and expected_binding=={'synthetic':True}
    return {'original_stdout_validated':True}


def test_real_tiny_child_collected_once_with_actual_exit_and_private_bytes_hidden_from_repr():
    result=m.collect(child('import os;os.write(1,b\'{"synthetic_safe":true}\\n\')'),SAFE,seconds=3)
    assert result.actual_exit==0 and result.reaped and result.streams_complete
    assert result.stdout==RAW and result.stderr==b'' and not result.timeout and not result.overbound
    assert 'synthetic_safe' not in repr(result)
    packet=m.packet(result,NS(validate_original_stdout=fake_validator),{'synthetic':True})
    assert packet['original_stdout_validated'] is True and packet['original_stdout']==RAW.decode()
    assert packet['collection_only'] is True


@pytest.mark.parametrize('stream', [1,2])
def test_real_noisy_child_is_bounded_killed_and_reaped_without_printing_noise(stream):
    result=m.collect(child(f'import os,time;os.write({stream},b"PRIVATE-NOISE"*10000);time.sleep(10)'),
        SAFE,seconds=2,maximum_stdout=128,maximum_stderr=128)
    assert result.overbound and result.reaped and result.actual_exit is not None
    assert not result.streams_complete
    assert len(result.stdout)<=129 and len(result.stderr)<=129
    packet=m.packet(result,NS(validate_original_stdout=fake_validator),{'synthetic':True})
    assert packet['original_stdout'] is None and packet['stream_hash_scope']=='bounded_observed_prefixes'
    assert 'PRIVATE-NOISE' not in m.canonical(packet).decode()


def test_real_sleeping_child_timeout_kills_only_own_process_and_reaps():
    result=m.collect(child('import time;time.sleep(10)'),SAFE,seconds=.08)
    assert result.timeout and result.reaped and type(result.actual_exit) is int and result.actual_exit<0
    assert result.stdout==result.stderr==b'' and not result.streams_complete


def test_actual_zero_and_valid_stdout_with_noisy_stderr_is_not_accepted():
    result=m.Collected(0,RAW,b'PRIVATE-STDERR',False,False,True,'none',True)
    packet=m.packet(result,NS(validate_original_stdout=fake_validator),{'synthetic':True})
    assert packet['original_stdout_validated'] is False and packet['original_stdout'] is None
    assert packet['stderr_len']==len(b'PRIVATE-STDERR')
    assert 'PRIVATE-STDERR' not in m.canonical(packet).decode()


def failure():
    return {'schema':preparer.SCHEMA+'-failure','stage':'compute_first','claim_state':'consumed',
        'failure_code':'conversion','dependency_failure':{'module':'bridge','code':'plain'},**preparer.FLAGS}


def test_finite_failure_can_be_retained_with_nonempty_stderr_but_stderr_is_hash_only():
    raw=m.canonical(failure())+b'\n'
    result=m.Collected(2,raw,b'PRIVATE-TRACEBACK',False,False,True,'none',True)
    packet=m.packet(result,preparer,{'synthetic':True})
    assert packet['closed_failure_frame_validated'] is True and packet['original_stdout']==raw.decode()
    assert packet['original_stdout_validated'] is False
    assert 'PRIVATE-TRACEBACK' not in m.canonical(packet).decode()


@pytest.mark.parametrize('fault',['extra','flag','stage','claim','code','dependency','trailing','duplicate','nonASCII'])
def test_unchecked_failure_or_output_text_is_never_retained(fault):
    value=failure()
    if fault=='extra':value['raw']='PRIVATE-TEXT'
    elif fault=='flag':value['QC_contact']=True
    elif fault=='stage':value['stage']='PRIVATE-TEXT'
    elif fault=='claim':value['claim_state']=True
    elif fault=='code':value['failure_code']='PRIVATE-TEXT'
    elif fault=='dependency':value['dependency_failure']['code']='PRIVATE-TEXT'
    raw=m.canonical(value)+b'\n'
    if fault=='trailing':raw+=b'\n'
    elif fault=='duplicate':raw=b'{"raw":"PRIVATE-TEXT","raw":"PRIVATE-TEXT"}\n'
    elif fault=='nonASCII':raw=b'\xffPRIVATE-TEXT\n'
    packet=m.packet(m.Collected(2,raw,b'',False,False,True,'none',True),preparer,{'synthetic':True})
    assert packet['closed_failure_frame_validated'] is False and packet['original_stdout'] is None
    assert 'PRIVATE-TEXT' not in m.canonical(packet).decode()


@pytest.mark.parametrize('actual',[None,-9,True,'0'])
def test_unknown_nonzero_or_invalid_actual_exit_never_inherits_stdout_success(actual):
    result=m.Collected(actual,RAW,b'',False,False,True,'none',True)
    if type(actual) not in (int,type(None)):
        with pytest.raises(m.Refused):m.packet(result,NS(validate_original_stdout=fake_validator),{'synthetic':True})
    else:
        packet=m.packet(result,NS(validate_original_stdout=fake_validator),{'synthetic':True})
        assert packet['original_stdout'] is None and packet['original_stdout_validated'] is False


def test_late_public_descriptor_close_refuses_collector_but_preserves_actual_child_metadata(tmp_path,monkeypatch):
    path=tmp_path/'synthetic-public.py';path.write_bytes(b'pass\n');path.chmod(0o600)
    target=io.BytesIO();real_close=os.close
    monkeypatch.setattr(m,'LAST_PACKET',None)
    def main():
        with m.PublicSource(path,m.pin(b'pass\n')['sha256']) as held:
            result=m.collect(child('import os;os.write(1,b\'{"synthetic_safe":true}\\n\')'),SAFE,seconds=3)
            answer=m.retain_result(result,NS(validate_original_stdout=fake_validator),{'synthetic':True})
            fd=held.fd
            def failed_close(value):
                real_close(value)
                if value==fd:raise OSError('PRIVATE-CLOSE-ERROR')
            monkeypatch.setattr(m.os,'close',failed_close)
        return answer
    top=ast.parse(Path(m.__file__).read_bytes()).body[-1]
    namespace={'__name__':'__main__','main':main,'sys':NS(stdout=NS(buffer=target)),
        'canonical':m.canonical,'require':m.require,'MAX_STDOUT':m.MAX_STDOUT,
        'collector_failure_packet':m.collector_failure_packet}
    with pytest.raises(SystemExit) as caught:
        exec(compile(ast.Module(body=[top],type_ignores=[]),'<synthetic-collector-main>','exec'),namespace)
    assert caught.value.code==2
    value=json.loads(target.getvalue())
    assert value['collector_failed'] is True and value['original_stdout'] is None
    assert value['retained_child']['actual_exit']==0 and value['retained_child']['reaped'] is True
    assert value['retained_child']['original_stdout'] is None
    assert value['retained_child']['original_stdout_validated'] is False
    assert 'PRIVATE-CLOSE-ERROR' not in target.getvalue().decode()


def test_cli_builds_only_exact_preparer_and_has_no_arbitrary_command_argument():
    tree=ast.parse(Path(m.__file__).read_bytes())
    run=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='run')
    assignment=next(node for node in ast.walk(run) if isinstance(node,ast.Assign)
        and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='command'
        and isinstance(node.value,ast.List))
    assert ast.unparse(assignment.value).startswith("[PYTHON, '-I', '-B', str(PREPARER), 'prepare'")
    assert m.PREPARER_SHA256=='f9bb012166df92525fd77888206b792b7279a12a2ea44485da3f75accc1c30cc'
    assert m.PLAN_SHA256=='699788fa6d53f0bf4cd8048986e78d96e7c0a4cb0cbcd729fe5fa4a45600849a'
    assert m.SECONDS==210 and m.MAX_STDOUT==65536 and m.MAX_STDERR==16384
