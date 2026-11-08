"""Technical bounded own-child capture; no protocol or operation authority.

Arguments and all bounds are resolved before spawning. Only supplied argv,
environment and stdin are used. Raw stdout is returned internally; stderr,
commands, environment values and exception text are never printed or returned.
On a limit, counts/hashes describe the retained prefix; one additional observed
byte proves the limit was crossed. Unread output is explicitly incomplete.
"""
from datetime import datetime, timezone
import hashlib
import math
import os
from pathlib import Path
import selectors
import subprocess
import time

ROOT=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
SCHEMA='arv2-r298-technical-bounded-actual-capture-v1'
MAX_SECONDS=7200
MAX_STDOUT,MAX_STDERR,MAX_STDIN=8*1024*1024,1024*1024,128*1024
MAX_ARGV,MAX_ENV_BYTES,CHUNK=128*1024,128*1024,65536
BOUNDS=frozenset(('arguments','scope','spawn_failed','deadline','stdout_limit','stderr_limit','stdin_closed','capture_io'))
FIELDS=frozenset(('schema','dispatched_at','completion_observed_at','spawn_observed','actual_exit','bound',
    'stdin_bytes_requested','stdin_bytes_written','stdin_sha256','stdin_complete',
    'stdout_bytes','stdout_sha256','stdout_observed_bytes','stdout_complete',
    'stderr_bytes','stderr_sha256','stderr_observed_bytes','stderr_complete',
    'protocol_accepted','operation_granted','physical_output_bytes_measured'))


class _Stop(Exception):pass


def _sha(raw):return hashlib.sha256(raw).hexdigest()


def _utc():return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def _hash(value):return type(value) is str and len(value)==64 and all(char in '0123456789abcdef' for char in value)


def profile_record():
    return {'schema':SCHEMA,'cwd':str(ROOT),'maximum_seconds':MAX_SECONDS,'maximum_stdout_bytes':MAX_STDOUT,
        'maximum_stderr_bytes':MAX_STDERR,'maximum_stdin_bytes':MAX_STDIN,'maximum_argv_bytes':MAX_ARGV,
        'maximum_environment_bytes':MAX_ENV_BYTES,'read_chunk_bytes':CHUNK,
        'all_arguments_bounds_and_environment_copied_before_Popen':True,'shell':False,'environment_inherited':False,
        'close_fds':True,'arbitrary_progress_callback':False,'one_nonblocking_selector_for_all_three_pipes':True,
        'stdout_returned_internally_only':True,'stderr_command_environment_exception_values_not_returned':True,
        'retained_output_prefix_hashes_not_unread_or_wire_bytes':True,'one_extra_limit_detection_byte_not_retained':True,
        'own_child_only_kill_and_reap':True,'uninterruptible_IO_or_host_suspension_can_exceed_deadline':True,
        'UTC_timestamps_are_external_process_brackets_not_provider_event_times':True,
        'protocol_accepted':False,'operation_granted':False,'physical_output_bytes_measured':False}


def validate_metadata(value):
    if not (type(value) is dict and set(value)==FIELDS and value['schema']==SCHEMA
            and type(value['spawn_observed']) is type(value['stdin_complete']) is type(value['stdout_complete'])
                is type(value['stderr_complete']) is bool
            and (value['actual_exit'] is None or type(value['actual_exit']) is int)
            and value['bound'] in BOUNDS|{None}
            and all(type(value[key]) is int and value[key]>=0 for key in ('stdin_bytes_requested','stdin_bytes_written',
                'stdout_bytes','stdout_observed_bytes','stderr_bytes','stderr_observed_bytes'))
            and value['stdin_bytes_written']<=value['stdin_bytes_requested']<=MAX_STDIN
            and value['stdout_bytes']<=value['stdout_observed_bytes']<=value['stdout_bytes']+1
            and value['stderr_bytes']<=value['stderr_observed_bytes']<=value['stderr_bytes']+1
            and value['stdout_bytes']<=MAX_STDOUT and value['stderr_bytes']<=MAX_STDERR
            and all(_hash(value[key]) for key in ('stdin_sha256','stdout_sha256','stderr_sha256'))
            and value['protocol_accepted'] is value['operation_granted'] is value['physical_output_bytes_measured'] is False):
        raise ValueError('capture_metadata')
    for key in ('dispatched_at','completion_observed_at'):
        if type(value[key]) is not str:raise ValueError('capture_metadata')
        try:stamp=datetime.fromisoformat(value[key])
        except (ValueError,TypeError):raise ValueError('capture_metadata') from None
        if stamp.utcoffset()!=timezone.utc.utcoffset(stamp):raise ValueError('capture_metadata')
    if datetime.fromisoformat(value['dispatched_at'])>datetime.fromisoformat(value['completion_observed_at']):
        raise ValueError('capture_metadata')
    if value['stdin_complete'] and value['stdin_bytes_written']!=value['stdin_bytes_requested']:
        raise ValueError('capture_metadata')
    if value['stdout_complete'] and value['stdout_observed_bytes']!=value['stdout_bytes']:raise ValueError('capture_metadata')
    if value['stderr_complete'] and value['stderr_observed_bytes']!=value['stderr_bytes']:raise ValueError('capture_metadata')
    if not value['spawn_observed'] and (value['actual_exit'] is not None or value['stdin_bytes_written']
            or value['stdout_observed_bytes'] or value['stderr_observed_bytes']):raise ValueError('capture_metadata')
    if value['bound'] is None and not (value['spawn_observed'] and type(value['actual_exit']) is int
            and value['stdin_complete'] and value['stdout_complete'] and value['stderr_complete']):
        raise ValueError('capture_metadata')
    return value


def _arguments(command,safeenv,input_raw,seconds,stdout_limit,stderr_limit):
    if not (type(stdout_limit) is int and 0<=stdout_limit<=MAX_STDOUT
            and type(stderr_limit) is int and 0<=stderr_limit<=MAX_STDERR
            and type(seconds) in (int,float) and math.isfinite(seconds) and 0<seconds<=MAX_SECONDS
            and type(input_raw) is bytes and len(input_raw)<=MAX_STDIN
            and type(command) in (tuple,list) and 0<len(command)<=128
            and all(type(arg) is str and '\x00' not in arg for arg in command)
            and command[0] and Path(command[0]).is_absolute()
            and sum(len(arg.encode('utf-8'))+1 for arg in command)<=MAX_ARGV
            and type(safeenv) is dict and len(safeenv)<=128
            and all(type(key) is type(value) is str and 0<len(key)<=256 and '=' not in key
                and '\x00' not in key and '\x00' not in value for key,value in safeenv.items())
            and sum(len(key.encode('utf-8'))+len(value.encode('utf-8'))+2 for key,value in safeenv.items())<=MAX_ENV_BYTES):
        return None
    return tuple(command),dict(safeenv),input_raw,float(seconds),stdout_limit,stderr_limit


def capture(command,safeenv,input_raw,seconds,*,stdout_limit,stderr_limit):
    """Return internal bounded stdout and closed actual process observations.

    Invalid arguments return finite no-spawn metadata. A completed child with
    a nonzero exit is faithfully recorded, not accepted or retried. This helper
    neither examines protocol framing nor authorizes the supplied command.
    """
    started=_utc();empty=_sha(b'')
    observed={'schema':SCHEMA,'dispatched_at':started,'completion_observed_at':started,
        'spawn_observed':False,'actual_exit':None,'bound':None,'stdin_bytes_requested':0,'stdin_bytes_written':0,
        'stdin_sha256':empty,'stdin_complete':False,'stdout_bytes':0,'stdout_sha256':empty,'stdout_observed_bytes':0,
        'stdout_complete':False,'stderr_bytes':0,'stderr_sha256':empty,'stderr_observed_bytes':0,'stderr_complete':False,
        'protocol_accepted':False,'operation_granted':False,'physical_output_bytes_measured':False}
    output,errors=bytearray(),bytearray();process=None;selector=None
    out_eof=err_eof=False
    # All configurable and global bounds below are copied before Popen. No
    # caller module attribute or callback is evaluated after the child starts.
    try:
        checked=_arguments(command,safeenv,input_raw,seconds,stdout_limit,stderr_limit)
        if checked is None:observed['bound']='arguments';raise _Stop()
        argv,environ,payload,duration,out_cap,err_cap=checked
        cwd=ROOT;chunk_cap=CHUNK
        if type(cwd) is not type(Path()) or not cwd.is_absolute() or cwd.resolve()!=cwd or Path.cwd()!=cwd:
            observed['bound']='scope';raise _Stop()
        observed.update(stdin_bytes_requested=len(payload),stdin_sha256=_sha(payload))
        deadline=time.monotonic()+duration
        try:
            process=subprocess.Popen(argv,cwd=str(cwd),env=environ,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,close_fds=True,shell=False)
        except BaseException:
            observed['bound']='spawn_failed';raise _Stop()
        observed['spawn_observed']=True
        selector=selectors.DefaultSelector()
        for pipe in (process.stdin,process.stdout,process.stderr):os.set_blocking(pipe.fileno(),False)
        selector.register(process.stdout,selectors.EVENT_READ,'stdout')
        selector.register(process.stderr,selectors.EVENT_READ,'stderr')
        if payload:selector.register(process.stdin,selectors.EVENT_WRITE,'stdin')
        else:process.stdin.close();observed['stdin_complete']=True
        while selector.get_map() and observed['bound'] is None:
            left=deadline-time.monotonic()
            if left<=0:observed['bound']='deadline';break
            for event,_mask in selector.select(min(1,left)):
                if event.data=='stdin':
                    try:count=os.write(event.fileobj.fileno(),payload[observed['stdin_bytes_written']:observed['stdin_bytes_written']+4096])
                    except BlockingIOError:continue
                    except BrokenPipeError:observed['bound']='stdin_closed';break
                    if type(count) is not int or count<=0:observed['bound']='stdin_closed';break
                    observed['stdin_bytes_written']+=count
                    if observed['stdin_bytes_written']==len(payload):
                        selector.unregister(event.fileobj);event.fileobj.close();observed['stdin_complete']=True
                    continue
                target,cap=(output,out_cap) if event.data=='stdout' else (errors,err_cap)
                try:raw=os.read(event.fileobj.fileno(),min(chunk_cap,cap-len(target)+1))
                except BlockingIOError:continue
                if not raw:
                    selector.unregister(event.fileobj)
                    if event.data=='stdout':out_eof=True
                    else:err_eof=True
                    continue
                key=event.data+'_observed_bytes';observed[key]+=len(raw)
                available=cap-len(target);target.extend(raw[:available])
                if len(raw)>available:observed['bound']=event.data+'_limit';break
        if observed['bound'] is None:
            try:process.wait(timeout=max(.001,deadline-time.monotonic()))
            except subprocess.TimeoutExpired:observed['bound']='deadline'
    except _Stop:pass
    except BaseException:
        # Never serialize exceptions, argv, environment or raw stderr.
        observed['bound']='arguments' if process is None else 'capture_io'
    finally:
        if selector is not None:
            try:selector.close()
            except BaseException:observed['bound']=observed['bound'] or 'capture_io'
        if process is not None:
            try:
                if process.poll() is None:process.kill()
                process.wait();observed['actual_exit']=process.returncode
            except BaseException:observed['bound']=observed['bound'] or 'capture_io'
            for pipe in (process.stdin,process.stdout,process.stderr):
                try:pipe.close()
                except BaseException:observed['bound']=observed['bound'] or 'capture_io'
        observed.update(completion_observed_at=_utc(),stdout_bytes=len(output),stdout_sha256=_sha(bytes(output)),
            stderr_bytes=len(errors),stderr_sha256=_sha(bytes(errors)),stdout_complete=out_eof,stderr_complete=err_eof)
    # A validation refusal is finite and cannot become process acceptance.
    return bytes(output),validate_metadata(observed)
