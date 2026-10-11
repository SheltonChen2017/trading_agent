"""Fresh exact-size/aggregate-budget successor for retained own-job results.

No generic path, credentials, network, QC, input data or discovery entry point.
Fixed role names and explicit expected hashes/bytes bind one newly spent result
claim. The opened descriptor must match expected size and remaining budget
before any body is read. Executed reader/inventory modules remain immutable.
Native metrics retain their original nulls, lineage checks and limitations;
this helper grants no new look, attempt, export, strategy or canonical approval.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
import os
from pathlib import Path
import re
import stat
import subprocess
import time

from . import extended_result_inventory_successor as strict_inventory

reader, e = strict_inventory.reader, strict_inventory.e
LANE, PRIVATE_ROOT = reader.LANE, reader.PRIVATE_ROOT
SOURCE_RELATIVE = reader.PREFIX + 'extended_result_reader_successor.py'
SOURCE_PATHS = (*strict_inventory.SOURCE_PATHS, SOURCE_RELATIVE)
READER_SHA256 = 'cda6340bb84ea6f5e9e0715fed57e210f1d2e5020f273fc4d8e4651046a7c037'
INVENTORY_SUCCESSOR_SHA256 = '44de86581286d5712843fb4f3b58509a2a5fdb82a639602e5ce000703e9bee1a'
MAX_FILE, MAX_TOTAL, MAX_SECONDS = reader.MAX_FILE, reader.MAX_TOTAL, reader.MAX_SECONDS
Refusal = reader.Refusal
_ARGS = ('source_hashes','git_head','owner_instruction_sha256','created_utc','expires_utc','read_operation_id',
    'qc_operation_id','candidate_id','attempt','project_id','backtest_id','action','inventory','collection_sequence','order_pages','mode')
_PINS = {reader.PREFIX + 'extended_result_driver.py': READER_SHA256,
    strict_inventory.SOURCE_RELATIVE: INVENTORY_SUCCESSOR_SHA256,
    strict_inventory.predecessor.SOURCE_RELATIVE: strict_inventory.PREDECESSOR_SHA256}


def _fail(): raise Refusal('exact-size bounded own-job result refused; no automatic retry')


def _verify_imports():
    if Path(__file__) != LANE / SOURCE_RELATIVE or Path(strict_inventory.__file__) != LANE / strict_inventory.SOURCE_RELATIVE: _fail()
    strict_inventory._verify_imports()


def _sources(head):
    sources = strict_inventory._sources(head)
    reader._guard(head); directory = reader._open_directory((LANE / SOURCE_RELATIVE).parent)
    try: raw = reader._read(directory, Path(SOURCE_RELATIVE).name, private=False)
    finally: os.close(directory)
    reader._guard(head)
    recorded = subprocess.run(['git','show',head+':'+SOURCE_RELATIVE],cwd=LANE,capture_output=True,timeout=5,check=True).stdout
    if raw != recorded or any(reader._sha(sources[name]) != identity for name,identity in _PINS.items()): _fail()
    sources[SOURCE_RELATIVE] = raw; reader._guard(head)
    return sources


def _plan(**arguments):
    if set(arguments) != set(_ARGS): _fail()
    hashes, operation = arguments['source_hashes'], arguments['read_operation_id']
    if (type(hashes) is not dict or set(hashes) != set(SOURCE_PATHS)
            or any(hashes.get(name) != identity for name,identity in _PINS.items())
            or type(operation) is not str or re.fullmatch(r'TPR-EXT26-RESULT-V2-[A-Za-z0-9-]{1,50}',operation) is None): _fail()
    for identity in hashes.values(): e._hash(identity)
    old_arguments = dict(arguments); old_arguments['source_hashes'] = {name:hashes[name] for name in reader.SOURCE_PATHS}
    plan = reader._plan(**old_arguments)
    plan.update(schema='tpr-ext26-result-reader-successor-plan-v1',source_hashes=dict(hashes),
        predecessor_reader_sha256=READER_SHA256,strict_inventory_source_sha256=INVENTORY_SUCCESSOR_SHA256,
        strict_read_policy='opened-descriptor-exact-expected-size-and-remaining-before-body-v1')
    return plan


def _validate_plan(plan):
    if e.canonical(plan) != e.canonical(_plan(**{key:plan[key] for key in _ARGS})): _fail()


def _read_bound(directory,name,expected,remaining):
    """Same opened-FD budget discipline, with exact expected bytes pre-body."""
    e._closed(expected,{'sha256','bytes'});e._hash(expected['sha256']);size=e._integer(expected['bytes'],MAX_FILE)
    if (type(name) is not str or re.fullmatch(r'[A-Za-z0-9_.-]{1,220}',name) is None
            or type(remaining) is not int or not 0 < remaining <= MAX_TOTAL or size > remaining): _fail()
    fd = None
    try:
        fd = os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != os.getuid()
                or stat.S_IMODE(before.st_mode) != 0o600 or before.st_size != size or before.st_size > remaining): _fail()
        named_before = os.stat(name,dir_fd=directory,follow_symlinks=False)
        fields = strict_inventory._FIELDS
        if any(getattr(before,key) != getattr(named_before,key) for key in fields): _fail()
        pieces,left = [],size
        while left:
            piece = os.read(fd,min(65536,left))
            if not piece or len(piece) > left: _fail()
            pieces.append(piece);left -= len(piece)
        raw = b''.join(pieces);after = os.fstat(fd);named_after = os.stat(name,dir_fd=directory,follow_symlinks=False)
        if (len(raw) != size or len(raw) > remaining or reader._sha(raw) != expected['sha256']
                or any(getattr(before,key) != getattr(after,key) or getattr(before,key) != getattr(named_after,key) for key in fields)): _fail()
        return raw
    finally:
        if fd is not None:os.close(fd)


def _execute(plan,sources,path,*,clock,guard):
    _validate_plan(plan)
    if (plan['mode']=='production' and path != PRIVATE_ROOT
            or plan['mode']=='offline-fixture' and (path==PRIVATE_ROOT or path.is_relative_to(LANE))): _fail()
    start,total,directory,read_inflight = time.monotonic(),0,None,False
    def check():
        guard(plan['git_head']);current=clock()
        if (type(current) is not reader.datetime or current.utcoffset() != timedelta(0)
                or not reader._clock(plan['created_utc']) <= current < reader._clock(plan['expires_utc'])
                or time.monotonic()-start >= MAX_SECONDS
                or {name:reader._sha(raw) for name,raw in sources.items()} != plan['source_hashes']): _fail()
    check()
    try:
        directory=reader._open_directory(path);info=os.fstat(directory)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:_fail()
        check();operation=plan['read_operation_id']
        reader._publish(directory,operation+'.claim.spent.json',e.canonical(plan))
        report={'schema':'tpr-ext26-result-reader-successor-receipt-v1','study_id':e.STUDY_ID,
            'read_operation_id':operation,**{key:plan[key] for key in ('candidate_id','attempt','project_id','backtest_id','qc_operation_id','action')},
            'status':'FAILED_OR_UNCERTAIN','scope_spent':True,'plan_sha256':reader._sha(e.canonical(plan)),
            'git_head':plan['git_head'],'source_hashes':plan['source_hashes'],'owner_instruction_sha256':plan['owner_instruction_sha256'],
            'predecessor_reader_sha256':READER_SHA256,'strict_inventory_source_sha256':INVENTORY_SUCCESSOR_SHA256,
            'strict_read_policy':plan['strict_read_policy'],'read_inventory':{},'read_bytes':0,'read_attempts':0,
            'failed_read_body_bytes_unknown':False,'read_bytes_semantics':'retained custody-verified bytes; unsuccessful-read body bytes may be unknown',
            'body_budget_and_expected_size_enforced_before_read':True,'terminal_status':None,'compile_id':None,
            'diagnostic':None,'metrics':None,'private_output_hashes':{},'automatic_retry':False,'old_receipts_renewed':False,
            'new_looks':0,'quantconnect_attempts':0,'full_cloud_journal_exported':False,'independent_input_row_replay':False,
            'canonical_admission':False,'trading':False}
        try:
            names=reader._names(plan['candidate_id'],plan['attempt'],plan['qc_operation_id'],plan['action'],
                plan['backtest_id'] is not None,plan['collection_sequence'],plan['order_pages'])
            data={}
            for role,name in names.items():
                check();report['read_attempts']+=1;read_inflight=True
                raw=_read_bound(directory,name,plan['inventory'][role],MAX_TOTAL-total);total+=len(raw);read_inflight=False
                data[role]=raw;report['read_inventory'][role]={'sha256':reader._sha(raw),'bytes':len(raw)}
            check();manifest,compile_id,terminal,diagnostic=reader._binding(plan,data)
            report.update(compile_id=compile_id,terminal_status=terminal,diagnostic=diagnostic)
            if plan['action']=='metrics':
                if terminal not in {'Completed','Completed.'}:_fail()
                result,orders=reader._metrics(plan,manifest,compile_id,data,sources[reader.PREFIX+'extended_calendar.json'])
                for kind,pages in (('normalized-orders',orders.pages),('order-observations',orders.observations)):
                    for number,raw in enumerate(pages):
                        check();name=operation+'.'+kind+'.'+f'{number:04d}'+'.json'
                        reader._publish(directory,name,raw);report['private_output_hashes'][kind+'.'+str(number)]=reader._sha(raw)
                report['metrics']=result
            check();report['status']='COMPLETED'
        except (Exception,KeyboardInterrupt):
            report['metrics']=None;report['failed_read_body_bytes_unknown']=read_inflight
        report.update(read_bytes=total,ended_utc=clock().isoformat());guard(plan['git_head'])
        raw=e.canonical(report);reader._publish(directory,operation+'.result.json',raw)
        return raw
    finally:
        if directory is not None:os.close(directory)


def run_result(**arguments):
    _verify_imports();head=reader._guard();sources=_sources(head)
    plan=_plan(source_hashes={name:reader._sha(raw) for name,raw in sources.items()},git_head=head,mode='production',**arguments)
    def committed_guard(expected):reader._guard(expected);_verify_imports()
    with reader._deadline():
        raw=_execute(plan,sources,PRIVATE_ROOT,clock=reader._now,guard=committed_guard)
        if _sources(head) != sources:_fail()
        return raw


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for option in ('read-operation-id','qc-operation-id','candidate-id','attempt','project-id','backtest-id','action',
                   'inventory-json','inventory-sha256','owner-instruction-sha256','created-utc','expires-utc'):parser.add_argument('--'+option,required=True)
    parser.add_argument('--collection-sequence',type=int,default=0);parser.add_argument('--order-pages',type=int,default=0)
    arguments=vars(parser.parse_args(argv))
    try:
        inventory_raw=arguments.pop('inventory_json').encode();expected=arguments.pop('inventory_sha256')
        if reader._sha(inventory_raw) != e._hash(expected):_fail()
        arguments['inventory']=e.parse_json(inventory_raw)
        arguments['project_id']=e._integer(e.JsonNumber(arguments['project_id']));arguments['attempt']=e._integer(e.JsonNumber(arguments['attempt']),3)
        if arguments['backtest_id']=='none':arguments['backtest_id']=None
        raw=run_result(**arguments);print(raw.decode(),end='')
        return 0 if e.parse_json(raw)['status']=='COMPLETED' else 1
    except (Exception,KeyboardInterrupt):
        print(e.canonical({'status':'REFUSED_OR_UNCERTAIN','scope_spent':None,'automatic_retry':False}).decode(),end='');return 1


if __name__=='__main__':raise SystemExit(main())
