"""Committed bounded collector for the single frozen R346 preparation.

Exit zero means collection only. Preparation success requires actual child
exit zero AND the original-output validator. Native isolation is inherited
from the externally applied exact preparer policy; this file is not a sandbox.
No artifact, credential, provider or QC reader exists here.
"""
import argparse
from contextlib import ExitStack
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import sys
import time
from types import ModuleType, SimpleNamespace

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
BRANCH = 'codex/strategy-analyst-revisions-v2'
PYTHON = '/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
SOURCE = ROOT / 'scripts/collect_arv2_r346_preparation.py'
PREPARER = ROOT / 'scripts/prepare_arv2_r346_legacy_plain.py'
PLAN = ROOT / 'scripts/arv2_r346_legacy_plain_plan.json'
SCHEMA = 'arv2-r346-preparation-bounded-collector-v1'
SECONDS, MAX_STDOUT, MAX_STDERR, MAX_PUBLIC = 210, 64*1024, 16*1024, 2*1024*1024
PREPARER_SHA256 = 'f9bb012166df92525fd77888206b792b7279a12a2ea44485da3f75accc1c30cc'
PLAN_SHA256 = '699788fa6d53f0bf4cd8048986e78d96e7c0a4cb0cbcd729fe5fa4a45600849a'
FIELDS = ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns','st_flags')
LAST_PACKET = None


class Refused(ValueError):
    pass


def require(value, code):
    if not value: raise Refused(code)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')


def pin(raw):
    return {'byte_count':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


@dataclass(frozen=True,slots=True)
class Collected:
    actual_exit: int | None
    stdout: bytes = field(repr=False)
    stderr: bytes = field(repr=False)
    timeout: bool
    overbound: bool
    reaped: bool
    collection_error: str
    streams_complete: bool


def collect(command, env, *, seconds=SECONDS, maximum_stdout=MAX_STDOUT, maximum_stderr=MAX_STDERR):
    """Pure injection seam; CLI supplies one exact command, never user code.

    Starts the deadline before Popen, including the entire child's startup.
    Timeout/overflow retain only bounded observed prefixes, never claim a full
    output hash. Uninterruptible I/O or host suspension cannot be bounded.
    """
    require(type(command) in (tuple,list) and command and all(type(value) is str for value in command),'arguments')
    require(type(env) is dict and all(type(key) is str and type(value) is str for key,value in env.items())
        and not {'QC_USER_ID','QC_API_TOKEN'} & set(env),'environment')
    require(type(seconds) in (int,float) and 0<seconds<=SECONDS
        and type(maximum_stdout) is int and 0<maximum_stdout<=MAX_STDOUT
        and type(maximum_stderr) is int and 0<maximum_stderr<=MAX_STDERR,'arguments')
    deadline=time.monotonic()+seconds
    child=None;out=bytearray();err=bytearray();actual=None;timed=over=reaped=False;error='none';complete=False
    try:
        child=subprocess.Popen(command,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True)
        with selectors.DefaultSelector() as selected:
            for pipe,label in ((child.stdout,'stdout'),(child.stderr,'stderr')):
                os.set_blocking(pipe.fileno(),False);selected.register(pipe,selectors.EVENT_READ,label)
            while selected.get_map() or child.poll() is None:
                left=deadline-time.monotonic()
                if left<=0:timed=True;break
                for key,_ in selected.select(min(.1,left)):
                    buffer,maximum=(out,maximum_stdout) if key.data=='stdout' else (err,maximum_stderr)
                    raw=os.read(key.fileobj.fileno(),min(8192,maximum+1-len(buffer)))
                    if not raw:selected.unregister(key.fileobj)
                    else:
                        buffer.extend(raw)
                        if len(buffer)>maximum:over=True;break
                if over:break
                if not selected.get_map() and child.poll() is None:
                    time.sleep(min(.01,max(0,deadline-time.monotonic())))
            complete=not timed and not over and not selected.get_map()
        if not timed and not over:
            try:actual=child.wait(timeout=max(.001,min(1,deadline-time.monotonic())));reaped=True
            except subprocess.TimeoutExpired:timed=True;complete=False
    except Exception:
        error='start' if child is None else 'io';complete=False
    finally:
        if child is not None:
            if child.poll() is None:
                try:child.kill()
                except ProcessLookupError:pass
                except OSError:error='kill';complete=False
            try:actual=child.wait(timeout=5);reaped=True
            except (subprocess.TimeoutExpired,OSError):actual=None;reaped=False;error='reap';complete=False
            for pipe in (child.stdout,child.stderr):
                if pipe is not None:
                    try:pipe.close()
                    except OSError:error='close';complete=False
    return Collected(actual,bytes(out),bytes(err),timed,over,reaped,error,complete)


def finite_failure(raw, preparer):
    """Accept only the producer's exact closed failure metadata, no text."""
    require(type(raw) is bytes and 0<len(raw)<=MAX_STDOUT and raw.endswith(b'\n') and raw.count(b'\n')==1,'failure_frame')
    try:value=preparer.loads(raw[:-1],MAX_STDOUT)
    except Exception:raise Refused('failure_frame') from None
    keys={'schema','stage','claim_state','failure_code','dependency_failure',*preparer.FLAGS}
    require(type(value) is dict and set(value)==keys and value['schema']==preparer.SCHEMA+'-failure'
        and type(value['stage']) is str and value['stage'] in ('preflight','B_DATA','compute_first','compute_second',
            'source_guard_return','publication','complete')
        and type(value['claim_state']) is str and value['claim_state'] in
            ('unallocated','allocated_unknown','consumed_or_unknown','consumed')
        and type(value['failure_code']) is str and value['failure_code'] in preparer.FINITE
        and all(value[key] is False for key in preparer.FLAGS),'failure_frame')
    dependency=value['dependency_failure']
    consumer_codes=frozenset(('scope','deadline','pin','json','binding','summary','bundle','input_receipt','candidate',
        'upload','metadata','security','path','state','close','unknown'))
    require(dependency is None or type(dependency) is dict and set(dependency)=={'module','code'}
        and type(dependency['module']) is str and type(dependency['code']) is str
        and ((dependency['module']=='bridge' and dependency['code'] in preparer.BRIDGE_CODES|{'unknown'})
            or (dependency['module']=='B_consumer' and dependency['code'] in consumer_codes)),'failure_frame')
    return value


def collected_metadata(result):
    require(type(result) is Collected and type(result.stdout) is bytes and type(result.stderr) is bytes
        and len(result.stdout)<=MAX_STDOUT+1 and len(result.stderr)<=MAX_STDERR+1
        and (result.actual_exit is None or type(result.actual_exit) is int)
        and all(type(getattr(result,key)) is bool for key in ('timeout','overbound','reaped','streams_complete'))
        and result.collection_error in ('none','start','io','kill','reap','close'),'output')
    return {'schema':SCHEMA,'actual_exit':result.actual_exit,'stdout_len':len(result.stdout),
        'stdout_sha256':pin(result.stdout)['sha256'],'stderr_len':len(result.stderr),
        'stderr_sha256':pin(result.stderr)['sha256'],'timeout':result.timeout,'overbound':result.overbound,
        'reaped':result.reaped,'collection_error':result.collection_error,'streams_complete':result.streams_complete,
        'stream_hash_scope':'complete_collected_streams' if result.streams_complete else 'bounded_observed_prefixes',
        'original_stdout_validated':False,'closed_failure_frame_validated':False,'original_stdout':None,
        'collection_only':True,'child_success_requires_actual_zero_and_original_stdout_validation':True}


def packet(result, preparer, expected_binding):
    summary=collected_metadata(result)
    accepted=False;failure=False;original=None
    admissible=result.reaped and result.streams_complete and not result.timeout and not result.overbound \
        and result.collection_error=='none' and type(result.actual_exit) is int
    if admissible and result.actual_exit==0 and result.stderr==b'':
        try:
            checked=preparer.validate_original_stdout(result.stdout,actual_exit=result.actual_exit,expected_binding=expected_binding)
            accepted=checked.get('original_stdout_validated') is True
        except Exception:pass
    if admissible and result.actual_exit==2:
        try:finite_failure(result.stdout,preparer);failure=True
        except Exception:pass
    if accepted or failure:
        original=result.stdout.decode('ascii')
    return {**summary,
        'original_stdout_validated':accepted,'closed_failure_frame_validated':failure,'original_stdout':original,
        'collection_only':True,'child_success_requires_actual_zero_and_original_stdout_validation':True}


def collector_failure_packet():
    return {'schema':SCHEMA,'collector_failed':True,'retained_child':LAST_PACKET,
        'original_stdout':None,'collection_only':True}


def retain_result(result, preparer, expected_binding):
    global LAST_PACKET
    LAST_PACKET=collected_metadata(result)
    return packet(result,preparer,expected_binding)


def metadata(info):
    values=tuple(getattr(info,key,None) for key in FIELDS)
    require(all(type(value) is int and value>=0 for value in values),'source_pin');return values


class PublicSource:
    """Original public FD and named/held metadata until collection finishes."""
    def __init__(self,path,digest):self.path,self.digest,self.fd=path,digest,None
    def __enter__(self):
        try:
            self.fd=os.open(self.path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            self.info=metadata(os.fstat(self.fd))
            require(stat.S_ISREG(self.info[2]) and self.info[3]==os.getuid() and self.info[5]==1
                and stat.S_IMODE(self.info[2]) in (0o600,0o644) and 0<self.info[6]<=MAX_PUBLIC,'source_pin')
            self.raw=os.pread(self.fd,MAX_PUBLIC+1,0);self.verify();return self
        except BaseException:
            if self.fd is not None:os.close(self.fd);self.fd=None
            raise
    def verify(self):
        require(self.fd is not None and metadata(os.fstat(self.fd))==self.info
            ==metadata(self.path.stat(follow_symlinks=False)) and len(self.raw)==self.info[6]
            and pin(self.raw)['sha256']==self.digest and os.pread(self.fd,MAX_PUBLIC+1,0)==self.raw,'source_pin')
    def __exit__(self,*args):
        try:self.verify()
        finally:os.close(self.fd);self.fd=None


def run(args):
    global LAST_PACKET
    LAST_PACKET=None
    require(Path.cwd()==ROOT and ROOT.resolve()==ROOT and sys.platform=='darwin' and os.name=='posix'
        and sys.version_info[:2]==(3,13) and sys.executable==PYTHON and sys.flags.isolated==1
        and sys.dont_write_bytecode and Path(__file__).absolute()==SOURCE,'host')
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}',args.expected_head)
        and args.caller_sha256==PREPARER_SHA256 and args.plan_sha256==PLAN_SHA256
        and type(args.collector_sha256) is str and re.fullmatch('[0-9a-f]{64}',args.collector_sha256),'arguments')
    with ExitStack() as held:
        held.enter_context(PublicSource(SOURCE,args.collector_sha256))
        source=held.enter_context(PublicSource(PREPARER,args.caller_sha256))
        held.enter_context(PublicSource(PLAN,args.plan_sha256))
        preparer=ModuleType('_r346_exact_preparer_observation_only');preparer.__file__=str(PREPARER)
        exec(compile(source.raw,str(PREPARER),'exec'),preparer.__dict__)
        safe=preparer.safe_env()
        require(set(os.environ)<=set(safe)|{'__CF_USER_TEXT_ENCODING'}
            and all(os.environ.get(key)==value for key,value in safe.items())
            and ('__CF_USER_TEXT_ENCODING' not in os.environ
                or os.environ['__CF_USER_TEXT_ENCODING']==f'0x{os.getuid():X}:0x0:0x0'),'environment')
        for command,expected in ((['rev-parse','--show-toplevel'],str(ROOT)),(['branch','--show-current'],BRANCH),
                (['rev-parse','HEAD'],args.expected_head),(['status','--porcelain'],'')):
            observed=subprocess.run(['/usr/bin/git',*command],cwd=ROOT,env=safe,stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,check=False)
            require(observed.returncode==0 and not observed.stderr and len(observed.stdout)<=262144
                and observed.stdout.decode('ascii').strip()==expected,'git')
        for path,digest in ((SOURCE,args.collector_sha256),(PREPARER,args.caller_sha256),(PLAN,args.plan_sha256)):
            observed=subprocess.run(['/usr/bin/git','cat-file','blob',args.expected_head+':'+path.relative_to(ROOT).as_posix()],
                cwd=ROOT,env=safe,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,check=False)
            require(observed.returncode==0 and not observed.stderr and len(observed.stdout)<=MAX_PUBLIC
                and pin(observed.stdout)['sha256']==digest,'source_pin')
        child_args=SimpleNamespace(expected_head=args.expected_head,caller_sha256=args.caller_sha256,plan_sha256=args.plan_sha256)
        expected_binding=preparer.binding(child_args)
        command=[PYTHON,'-I','-B',str(PREPARER),'prepare','--expected-head',args.expected_head,
            '--caller-sha256',args.caller_sha256,'--plan-sha256',args.plan_sha256]
        result=collect(command,safe)
        answer=retain_result(result,preparer,expected_binding)
    return answer


class Parser(argparse.ArgumentParser):
    def error(self,message):raise Refused('arguments')


def main():
    parser=Parser(add_help=False)
    for key in ('expected-head','caller-sha256','plan-sha256','collector-sha256'):parser.add_argument('--'+key)
    return run(parser.parse_args())


if __name__=='__main__':
    try:
        # Zero describes completed collection, never preparation acceptance.
        raw=canonical(main())+b'\n'
        require(len(raw)<=2*MAX_STDOUT+8192,'output')
        sys.stdout.buffer.write(raw)
    except BaseException:
        sys.stdout.buffer.write(canonical(collector_failure_packet())+b'\n')
        raise SystemExit(2)
