"""Real tiny-child capture tests inside native denial; no protocol operation."""
import copy
import hashlib
import inspect
import json
import os
import sys

import pytest

from scripts import arv2_r298_bounded_actual_capture as m


def safe(tmp_path):return {'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','TMPDIR':str(tmp_path),
    'PYTHONDONTWRITEBYTECODE':'1'}


def run(tmp_path,code,payload=b'',seconds=5,out=262144,err=131072):
    raw,observed=m.capture([sys.executable,'-B','-c',code],safe(tmp_path),payload,seconds,
        stdout_limit=out,stderr_limit=err)
    assert m.validate_metadata(observed)==observed
    assert observed['stdout_bytes']==len(raw) and observed['stdout_sha256']==hashlib.sha256(raw).hexdigest()
    assert observed['protocol_accepted'] is observed['operation_granted'] is False
    return raw,observed


def test_real_success_stdin_exact_EOF_raw_output_and_UTC_metadata(tmp_path):
    payload=b'binary\x00synthetic\xffinput\n'
    raw,value=run(tmp_path,'import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())',payload)
    assert raw==payload and value['actual_exit']==0 and value['bound'] is None
    assert value['spawn_observed'] is value['stdin_complete'] is value['stdout_complete'] is value['stderr_complete'] is True
    assert value['stdin_bytes_requested']==value['stdin_bytes_written']==len(payload)
    assert value['stdin_sha256']==hashlib.sha256(payload).hexdigest()
    assert value['dispatched_at'].endswith('+00:00') and value['completion_observed_at'].endswith('+00:00')


def test_nonzero_exit_and_stderr_are_facts_not_protocol_acceptance(tmp_path):
    secret=b'synthetic-private-stderr'
    raw,value=run(tmp_path,'import sys;sys.stdout.write("partial");sys.stderr.write("synthetic-private-stderr");sys.exit(7)')
    assert raw==b'partial' and value['actual_exit']==7 and value['bound'] is None
    assert value['stderr_bytes']==len(secret) and value['stderr_sha256']==hashlib.sha256(secret).hexdigest()
    assert secret.decode() not in json.dumps(value)


def test_trailing_raw_output_is_preserved_for_separate_protocol_validator(tmp_path):
    raw,value=run(tmp_path,'import sys;sys.stdout.buffer.write(b"{}\\nTRAILING\\n")')
    assert raw==b'{}\nTRAILING\n' and value['bound'] is None and value['actual_exit']==0
    assert value['protocol_accepted'] is False


def test_deadline_preserves_partial_stdout_and_kills_reaps_own_child(tmp_path):
    raw,value=run(tmp_path,'import sys,time;sys.stdout.write("partial");sys.stdout.flush();time.sleep(2)',seconds=.4)
    assert raw==b'partial' and value['bound']=='deadline' and type(value['actual_exit']) is int
    assert value['stdout_complete'] is False and value['stderr_complete'] is False


@pytest.mark.parametrize('stream',('stdout','stderr'))
def test_output_limit_retains_exact_prefix_and_one_detection_byte_not_unknown_tail(tmp_path,stream):
    code='import sys;sys.'+stream+'.buffer.write(b"x"*100);sys.'+stream+'.flush()'
    raw,value=run(tmp_path,code,out=8 if stream=='stdout' else 1024,err=8 if stream=='stderr' else 1024)
    assert value['bound']==stream+'_limit'
    assert value[stream+'_bytes']==8 and value[stream+'_observed_bytes']==9 and value[stream+'_complete'] is False
    assert value[stream+'_sha256']==hashlib.sha256(b'x'*8).hexdigest()
    assert raw==(b'x'*8 if stream=='stdout' else b'')


def test_zero_limits_allow_empty_output_and_refuse_first_byte(tmp_path):
    raw,value=run(tmp_path,'pass',out=0,err=0)
    assert raw==b'' and value['bound'] is None and value['actual_exit']==0
    raw,value=run(tmp_path,'print("x")',out=0,err=0)
    assert raw==b'' and value['bound']=='stdout_limit' and value['stdout_observed_bytes']==1
    assert value['stdout_bytes']==0 and value['stdout_sha256']==hashlib.sha256(b'').hexdigest()


def test_simultaneous_large_outputs_before_reading_stdin_does_not_deadlock(tmp_path):
    payload=b'z'*m.MAX_STDIN
    code='import sys;sys.stdout.buffer.write(b"o"*131072);sys.stdout.flush();sys.stderr.buffer.write(b"e"*65536);sys.stderr.flush();sys.stdout.buffer.write(sys.stdin.buffer.read())'
    raw,value=run(tmp_path,code,payload,seconds=5,out=262144,err=65536)
    assert raw==b'o'*131072+payload and value['actual_exit']==0 and value['bound'] is None
    assert value['stdin_bytes_written']==len(payload) and value['stdin_complete'] is True
    assert value['stderr_bytes']==65536


def test_early_closed_stdin_is_not_falsely_reported_delivered(tmp_path):
    raw,value=run(tmp_path,'import os,time;os.close(0);time.sleep(.2)',b'x'*m.MAX_STDIN)
    assert value['bound']=='stdin_closed' and value['stdin_complete'] is False
    assert value['stdin_bytes_written']<value['stdin_bytes_requested'] and type(value['actual_exit']) is int


@pytest.mark.parametrize('issue',('out_bool','out_negative','out_float','out_huge','err_bool','err_negative','err_huge',
    'seconds_bool','seconds_zero','seconds_nan','seconds_inf','seconds_huge','stdin_type','stdin_huge',
    'argv_empty','argv_relative','argv_NUL','argv_value','env_None','env_key','env_NUL'))
def test_invalid_limits_and_arguments_never_spawn(monkeypatch,tmp_path,issue):
    command=[sys.executable,'-B','-c','pass'];env=safe(tmp_path);payload=b'';seconds=5;out=10;err=10;called=[]
    if issue=='out_bool':out=True
    elif issue=='out_negative':out=-1
    elif issue=='out_float':out=10.0
    elif issue=='out_huge':out=m.MAX_STDOUT+1
    elif issue=='err_bool':err=False
    elif issue=='err_negative':err=-1
    elif issue=='err_huge':err=m.MAX_STDERR+1
    elif issue=='seconds_bool':seconds=True
    elif issue=='seconds_zero':seconds=0
    elif issue=='seconds_nan':seconds=float('nan')
    elif issue=='seconds_inf':seconds=float('inf')
    elif issue=='seconds_huge':seconds=m.MAX_SECONDS+1
    elif issue=='stdin_type':payload='not bytes'
    elif issue=='stdin_huge':payload=b'x'*(m.MAX_STDIN+1)
    elif issue=='argv_empty':command=[]
    elif issue=='argv_relative':command=['python','-c','pass']
    elif issue=='argv_NUL':command=[sys.executable,'x\x00']
    elif issue=='argv_value':command=[sys.executable,object()]
    elif issue=='env_None':env=None
    elif issue=='env_key':env={'bad=key':'value'}
    else:env={'X':'value\x00'}
    def spawn(*_,**__):called.append(True);raise RuntimeError('must never dispatch')
    monkeypatch.setattr(m.subprocess,'Popen',spawn)
    raw,value=m.capture(command,env,payload,seconds,stdout_limit=out,stderr_limit=err)
    assert raw==b'' and value['bound']=='arguments' and value['spawn_observed'] is False and called==[]
    m.validate_metadata(value)


def test_explicit_environment_does_not_inherit_parent_secrets_or_other_values(tmp_path,monkeypatch):
    monkeypatch.setenv('SHOULD_NOT_INHERIT','synthetic-private-parent-value')
    raw,value=run(tmp_path,'import os,sys;sys.stdout.write(os.environ.get("SHOULD_NOT_INHERIT","absent"))')
    assert raw==b'absent' and value['bound'] is None
    assert 'synthetic-private-parent-value' not in json.dumps(value)


def test_exact_ROOT_cwd_and_close_fds_are_explicit_before_dispatch(tmp_path,monkeypatch):
    original=m.subprocess.Popen;calls=[]
    def spawn(command,**kwargs):
        calls.append(kwargs)
        assert kwargs['cwd']==str(m.ROOT) and kwargs['close_fds'] is True and kwargs['shell'] is False
        assert kwargs['env']==safe(tmp_path)
        return original(command,**kwargs)
    monkeypatch.setattr(m.subprocess,'Popen',spawn)
    raw,value=run(tmp_path,'import os,sys;sys.stdout.write(os.getcwd())')
    assert raw.decode()==str(m.ROOT) and len(calls)==1
    monkeypatch.setattr(m,'ROOT',tmp_path)
    raw,value=m.capture([sys.executable,'-c','pass'],safe(tmp_path),b'',5,stdout_limit=10,stderr_limit=10)
    assert value['bound']=='scope' and value['spawn_observed'] is False and len(calls)==1


def test_spawn_failure_is_finite_no_message_or_environment_serialized(tmp_path,monkeypatch):
    def spawn(*_,**__):raise OSError('synthetic-sensitive-exception-url')
    monkeypatch.setattr(m.subprocess,'Popen',spawn)
    raw,value=m.capture([sys.executable,'-c','pass'],safe(tmp_path),b'input',5,stdout_limit=10,stderr_limit=10)
    assert raw==b'' and value['spawn_observed'] is False and value['actual_exit'] is None
    assert value['bound']=='spawn_failed' and value['stdin_bytes_written']==0
    assert 'synthetic-sensitive' not in json.dumps(value)


def test_capture_IO_exception_preserves_partial_stdout_and_reaps_own_child(tmp_path,monkeypatch):
    original=m.os.read;armed=[False]
    def read(fd,size):
        if armed[0]:raise OSError('synthetic-sensitive-capture-error')
        raw=original(fd,size)
        if raw==b'partial':armed[0]=True
        return raw
    monkeypatch.setattr(m.os,'read',read)
    raw,value=run(tmp_path,'import sys,time;sys.stdout.write("partial");sys.stdout.flush();time.sleep(.05);sys.stderr.write("next");sys.stderr.flush();time.sleep(2)')
    assert raw==b'partial' and value['bound']=='capture_io' and type(value['actual_exit']) is int
    assert value['stdout_complete'] is False and 'synthetic-sensitive' not in json.dumps(value)


@pytest.mark.parametrize('change',('extra','exit_bool','spawn_bool','bound','hash','count','stdin','completion','grant'))
def test_actual_metadata_closed_types_counts_UTC_and_no_acceptance(tmp_path,change):
    _,value=run(tmp_path,'pass')
    if change=='extra':value['raw_stderr']='private'
    elif change=='exit_bool':value['actual_exit']=False
    elif change=='spawn_bool':value['spawn_observed']=1
    elif change=='bound':value['bound']='private error text'
    elif change=='hash':value['stdout_sha256']='z'*64
    elif change=='count':value['stdout_observed_bytes']=2
    elif change=='stdin':value['stdin_bytes_written']=1
    elif change=='completion':value['completion_observed_at']='notUTC'
    else:value['protocol_accepted']=True
    with pytest.raises(ValueError):m.validate_metadata(value)


def test_profile_and_source_have_no_callback_shell_or_operational_entrypoint():
    value=m.profile_record();assert value['arbitrary_progress_callback'] is False
    assert value['environment_inherited'] is False and value['own_child_only_kill_and_reap'] is True
    source=inspect.getsource(m)
    for forbidden in ('eval(','shell=True','os.environ','keychain','requests','if __name__','getattr('):
        assert forbidden not in source
