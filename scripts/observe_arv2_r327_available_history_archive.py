"""Fixed external actual collector for the one-shot R327-K diagnostic.

Only public closed protocol bytes and process metadata may cross this seam.
The producer owns its new one-use claim. This collector supplies no new
attempt, source admission, price coverage or trading authority. The independent
native validator reads only the new archive DATA and owns one exclusive marker.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from types import SimpleNamespace
import zlib

ROOT=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts import prepare_arv2_r327_available_history_archive as h
from scripts import arv2_r298_bounded_actual_capture as actual_capture

SOURCE=ROOT/'scripts/observe_arv2_r327_available_history_archive.py'
SCHEMA='arv2-r327-fixed-K-archive-external-actual-collector-v1'
K_CALLER_SHA256='9f3d261ea4ac99548a0931af3d82729545df24077c7135e27268025bfbb060c5'
K_PROFILE_SHA256='7c7679f448165bcf5548c207236e0adf3b7b81a012a7c9451352d9af50427651'
CAPTURE_SHA256='febe87c53010227eeca399b8a5087c42d2363c7d3a9ee583d18dfd06b3a68356'
CAPTURE_BYTES=12105
SECONDS,PRODUCER_SECONDS,VALIDATOR_SECONDS=3700,1830,1830
MAX_STDOUT,MAX_STDERR,MAX_ENCODED,MAX_RESULT=131072,8192,65536,98304
FALSE_FLAGS={'new_attempt_granted':False,'new_control_created':False,'credential_access':False,
    'source_DATA_read':False,'private_body_or_identifier_disclosed':False,'whole_interpreter_integrity_proven':False,
    'ordinary_parent_native_network_denial_proven':False,'archive_price_coverage_proven':False,'QC_contact':False,'Safari_access':False,
    'source_or_price_admission_granted':False,'point_in_time_proven':False,
    'formal_forward_ready':False,'paper_or_live_ready':False}
FAILURES=frozenset(('preflight','deadline','producer_incomplete','producer_exit','producer_format',
    'validator_incomplete','validator_exit','validator_output','public_output_bound','postflight','os_error','unknown'))
TERMINALS=frozenset(('external_failure','authenticated_protocol_failure','technical_observation_complete'))


class Refused(ValueError):pass


def require(value,code):
    if not value:raise Refused(code)


def finite(error):
    if type(error) is Refused:
        args=BaseException.args.__get__(error)
        return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FAILURES else 'unknown'
    if type(error) is h.admitted.helpers.Deadline:return 'deadline'
    if type(error) is h.Refused:return 'preflight'
    if type(error) is h.environment.EnvironmentRefused:return 'preflight'
    if isinstance(error,OSError):return 'os_error'
    return 'unknown'


def remaining(deadline):
    require(type(deadline) in (int,float) and math.isfinite(deadline)
        and 0<deadline-time.monotonic()<=SECONDS,'deadline')
    return deadline-time.monotonic()


def _hash(value):return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None


def h_args(args):
    return SimpleNamespace(expected_head=args.expected_head,caller_sha256=K_CALLER_SHA256,profile_sha256=K_PROFILE_SHA256)


def binding(args):
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}',args.expected_head)
        and _hash(args.collector_sha256),'preflight')
    return {'schema':SCHEMA,'expected_head':args.expected_head,'collector_sha256':args.collector_sha256,
        'K_binding':h.binding(h_args(args))}


def profile_record():
    return {'schema':SCHEMA,'source':str(SOURCE),'root':str(ROOT),'branch':h.admitted.frozen.BRANCH,
        'python':str(h.PYTHON),'K_source':str(h.SOURCE),'K_caller_sha256':K_CALLER_SHA256,
        'K_profile_sha256':K_PROFILE_SHA256,'capture_source_sha256':CAPTURE_SHA256,'capture_byte_count':CAPTURE_BYTES,
        'capture_profile':actual_capture.profile_record(),'seconds':SECONDS,'producer_seconds':PRODUCER_SECONDS,
        'validator_seconds':VALIDATOR_SECONDS,'stdout_limit':MAX_STDOUT,'stderr_limit':MAX_STDERR,
        'maximum_encoded_public_envelope_bytes':MAX_ENCODED,'maximum_result_bytes':MAX_RESULT,
        'fixed_operations':['Kproduce_once','independent_native_Karchive_validate_once_if_complete_actual0or2'],
        'ordinary_credential_free_collector_launches_separate_native_producer_and_validator':True,
        'validator_native_only_new_archive_and_marker_all_network_Keychain_security_CLI_denial':True,
        'all_arguments_and_integer_bounds_resolved_before_each_spawn':True,
        'strict_complete_original_actual_metadata_required':True,
        'native_validator_zero_and_byte_equal_public_output_required':True,
        'actual_K_exit2_authenticates_failure_only_and_collector_returns2':True,
        'unknown_nonzero_timeout_or_incomplete_never_success':True,
        'only_canonical_closed_K_public_frame_compressed_after_validation':True,
        'compression':'zlib9_then_standard_base64_ASCII','no_retry_or_arbitrary_callback':True,
        'source_DATA_controls_private_bodies_credentials_not_read_by_collector':True,
        'deadline_uninterruptible_IO_host_suspension_qualification':True,**FALSE_FLAGS}


def preflight(args,deadline):
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}',args.expected_head)
        and _hash(args.collector_sha256) and Path(__file__).absolute()==SOURCE
        and Path.cwd()==ROOT and ROOT.resolve()==ROOT and sys.platform=='darwin' and os.name=='posix'
        and sys.version_info[:2]==(3,13) and Path(sys.executable)==h.PYTHON,'preflight')
    h.preflight(h_args(args),min(deadline,time.monotonic()+h.SECONDS))
    require(h.sha(SOURCE.read_bytes())==args.collector_sha256
        and h.sha(h.admitted.v5._git(['cat-file','blob',args.expected_head+':'+SOURCE.relative_to(ROOT).as_posix()],
            min(deadline,time.monotonic()+h.SECONDS),256*1024))==args.collector_sha256,'preflight')
    capture_raw=(ROOT/'scripts/arv2_r298_bounded_actual_capture.py').read_bytes()
    require(len(capture_raw)==CAPTURE_BYTES and h.sha(capture_raw)==CAPTURE_SHA256
        and h.pins()['scripts/arv2_r298_bounded_actual_capture.py']==CAPTURE_SHA256,'preflight')
    remaining(deadline)


def _complete(actual,*,stdin):
    try:actual_capture.validate_metadata(actual)
    except (ValueError,TypeError,KeyError):return False
    return actual['spawn_observed'] is True and actual['bound'] is None \
        and actual['stdin_bytes_requested']==actual['stdin_bytes_written']==len(stdin) \
        and actual['stdin_sha256']==h.sha(stdin) and actual['stdin_complete'] is True \
        and actual['stdout_complete'] is True and actual['stderr_complete'] is True \
        and actual['stderr_bytes']==actual['stderr_observed_bytes']==0 and actual['stderr_sha256']==h.sha(b'')


def _matches(actual,raw):
    return type(raw) is bytes and actual['stdout_bytes']==actual['stdout_observed_bytes']==len(raw) \
        and actual['stdout_sha256']==h.sha(raw) and 0<len(raw)<=MAX_STDOUT


def _pack(raw):
    require(type(raw) is bytes and 0<len(raw)<=MAX_STDOUT,'public_output_bound')
    encoded=base64.b64encode(zlib.compress(raw,9)).decode('ascii')
    require(len(encoded)<=MAX_ENCODED,'public_output_bound');return encoded


def _unpack(value):
    require(type(value) is str and 0<len(value)<=MAX_ENCODED and value.isascii(),'public_output_bound')
    try:
        compressed=base64.b64decode(value.encode('ascii'),validate=True)
        require(base64.b64encode(compressed).decode('ascii')==value,'public_output_bound')
        decoder=zlib.decompressobj();raw=decoder.decompress(compressed,MAX_STDOUT+1)
        require(0<len(raw)<=MAX_STDOUT and decoder.eof and not decoder.unconsumed_tail
            and not decoder.unused_data,'public_output_bound')
        require(zlib.compress(raw,9)==compressed,'public_output_bound')
        return raw
    except (binascii.Error,zlib.error,ValueError,UnicodeError):raise Refused('public_output_bound') from None


def initial_result(args):
    return {'binding':binding(args),'terminal':'external_failure','external_failure_code':None,
        'producer':None,'validator':None,'validated_public_envelope_pin':None,'validated_public_envelope_zlib_base64':None,
        'output_authenticated':False,'K_technical_observation_succeeded':False,
        'K_failure_authenticated':False,'collector_actual_success':False,**FALSE_FLAGS}


def observe(args,deadline):
    result=initial_result(args)
    try:
        preflight(args,deadline);h.ar._credential_free();h.environment._bootstrap_cli_logging()
        h.environment.require_safe_environment()
        runtime=Path(tempfile.mkdtemp(prefix='r327-k-archive-collector-',dir=ROOT/'.pytest_cache'))
        safe=h.ap.capture_support._environment(runtime,None)
        hargs=h_args(args)
        common=['--expected-head',args.expected_head,'--caller-sha256',K_CALLER_SHA256,'--profile-sha256',K_PROFILE_SHA256]
        command=['/usr/bin/sandbox-exec','-p',h.native_profile('produce'),str(h.PYTHON),
            '-B',str(h.SOURCE),'produce',*common]
        raw,producer=actual_capture.capture(command,safe,b'',min(PRODUCER_SECONDS,remaining(deadline)),
            stdout_limit=MAX_STDOUT,stderr_limit=MAX_STDERR)
        result['producer']=producer
        require(_complete(producer,stdin=b'') and _matches(producer,raw),'producer_incomplete')
        require(type(producer['actual_exit']) is int and producer['actual_exit'] in (0,2),'producer_exit')
        # Strict public shape is checked with the OBSERVED exit, never assumed0.
        try:h.validate_output(raw,producer['actual_exit'],hargs)
        except BaseException:raise Refused('producer_format') from None
        preflight(args,deadline);h.ar._credential_free();h.environment.require_safe_environment()
        command=['/usr/bin/sandbox-exec','-p',h.native_profile('validate'),str(h.PYTHON),'-B',str(h.SOURCE),
            'validate',*common,'--actual-exit',str(producer['actual_exit'])]
        validated,validator=actual_capture.capture(command,safe,raw,min(VALIDATOR_SECONDS,remaining(deadline)),
            stdout_limit=MAX_STDOUT,stderr_limit=MAX_STDERR)
        result['validator']=validator
        require(_complete(validator,stdin=raw) and _matches(validator,validated),'validator_incomplete')
        require(type(validator['actual_exit']) is int and validator['actual_exit']==0,'validator_exit')
        require(validated==raw,'validator_output')
        encoded=_pack(raw)
        try:preflight(args,deadline);h.ar._credential_free();h.environment.require_safe_environment()
        except BaseException:raise Refused('postflight') from None
        result.update(terminal='technical_observation_complete' if producer['actual_exit']==0 else 'authenticated_protocol_failure',
            validated_public_envelope_pin=h.pin(raw),validated_public_envelope_zlib_base64=encoded,
            output_authenticated=True,K_technical_observation_succeeded=producer['actual_exit']==0,
            K_failure_authenticated=producer['actual_exit']==2,collector_actual_success=producer['actual_exit']==0)
    except BaseException as error:
        result.update(terminal='external_failure',external_failure_code=finite(error),
            validated_public_envelope_pin=None,validated_public_envelope_zlib_base64=None,
            output_authenticated=False,K_technical_observation_succeeded=False,K_failure_authenticated=False,
            collector_actual_success=False)
    validate_result(result,args)
    return result


def validate_result(value,args):
    require(type(value) is dict and set(value)==set(initial_result(args))
        and value['binding']==binding(args) and value['terminal'] in TERMINALS
        and (value['external_failure_code'] is None or value['external_failure_code'] in FAILURES)
        and all(type(value[key]) is bool for key in ('output_authenticated','K_technical_observation_succeeded',
            'K_failure_authenticated','collector_actual_success'))
        and all(value[key] is False for key in FALSE_FLAGS),'public_output_bound')
    for role in ('producer','validator'):
        if value[role] is not None:
            try:actual_capture.validate_metadata(value[role])
            except (ValueError,TypeError,KeyError):raise Refused('public_output_bound') from None
    if value['terminal']=='external_failure':
        require(value['external_failure_code'] in FAILURES
            and value['validated_public_envelope_pin'] is value['validated_public_envelope_zlib_base64'] is None
            and value['output_authenticated'] is value['K_technical_observation_succeeded']
                is value['K_failure_authenticated'] is value['collector_actual_success'] is False,'public_output_bound')
        return value
    producer,validator=value['producer'],value['validator']
    require(producer is not None and validator is not None and type(producer['actual_exit']) is int
        and producer['actual_exit'] in (0,2) and type(validator['actual_exit']) is int and validator['actual_exit']==0
        and value['external_failure_code'] is None and value['output_authenticated'] is True,'public_output_bound')
    raw=_unpack(value['validated_public_envelope_zlib_base64'])
    require(_complete(producer,stdin=b'') and _matches(producer,raw)
        and _complete(validator,stdin=raw) and _matches(validator,raw)
        and value['validated_public_envelope_pin']==h.pin(raw),'public_output_bound')
    h.validate_output(raw,producer['actual_exit'],h_args(args))
    successful=producer['actual_exit']==0
    require(value['K_technical_observation_succeeded'] is value['collector_actual_success'] is successful
        and value['K_failure_authenticated'] is (not successful)
        and value['terminal']==('technical_observation_complete' if successful else 'authenticated_protocol_failure'),'public_output_bound')
    return value


def emit(value):
    raw=h.canonical(value)
    require(len(raw)+1<=MAX_RESULT,'public_output_bound')
    sys.stdout.buffer.write(raw+b'\n');sys.stdout.buffer.flush()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-head',required=True);parser.add_argument('--collector-sha256',required=True)
    args=parser.parse_args(argv);deadline=time.monotonic()+SECONDS
    try:
        with h.admitted.helpers._alarm(deadline):
            result=observe(args,deadline);emit(result)
            return 0 if result['collector_actual_success'] else 2
    except BaseException as error:
        # An outer alarm/validation failure must never print a traceback or
        # an unvalidated process packet. Invalid CLI binding values are omitted.
        try:
            result=initial_result(args);result['external_failure_code']=finite(error)
            validate_result(result,args);emit(result)
        except BaseException:
            sys.stdout.buffer.write(h.canonical({'schema':SCHEMA,'outside_failure':'preflight',
                'output_authenticated':False,'collector_actual_success':False})+b'\n')
        return 2


if __name__=='__main__':raise SystemExit(main())
