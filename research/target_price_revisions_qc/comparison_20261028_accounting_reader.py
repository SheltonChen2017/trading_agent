"""Pure optional in-QC account-comparison source renderer; no effects or I/O.

The preserved reader performs actual child/project/custody checks. This version
adds a separately claimed compact-evidence comparison, never retrieval rights
or native authority. Runtime helper/source hashes are externally verified build
bindings, not a self-declared proof of the loaded native implementation.
"""
from __future__ import annotations
import ast
from copy import deepcopy
import hashlib
import json
import re

from . import comparison_20261028_native_result_reader as base
from . import comparison_20261028_accounting as accounting

PREFIX=base.PREFIX
BASE_PATH=PREFIX+'comparison_20261028_native_result_reader.py'
ACCOUNTING_PATH=PREFIX+'comparison_20261028_accounting.py'
BASE_SHA256='33fa772f8a0b1899937d4a9e4bb70a6c168df3cfea3dd7be69928996fb19144a'
ACCOUNTING_SHA256='9ff8df1cf142308d8cd73e2950ddfe02d64bbe88c02b5316b424f50cc49b1bc6'
CALENDAR_PATH=PREFIX+'extended_calendar.json'
PINS={**base.PINS,BASE_PATH:BASE_SHA256,ACCOUNTING_PATH:ACCOUNTING_SHA256,
    CALENDAR_PATH:'3eccdf3cf9a2542ffd249983241d5747c2ecd4e21bc4a71f7f826c77ec1fe53d'}
SOURCE_PATHS=tuple(PINS)
HELPER='comparison_20261028_accounting_runtime.py'
MAX_COMPACT_BYTES=16384


class AccountingReaderBuildRefusal(ValueError):pass


def _fail():raise AccountingReaderBuildRefusal('CMP28 accounting reader build refused') from None
def _sha(raw):return hashlib.sha256(raw).hexdigest()
def _wire(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')


def _helper(raw,summary_raw,config_raw,compact_raw,binding):
    """Select only compact/journal arithmetic; pass pure dependencies explicitly."""
    nodes=[node for node in ast.parse(raw).body if base._declared(node)]
    declarations={name:node for node in nodes for name in base._declared(node)}
    needed={'audit_compact'}
    while True:
        selected=[node for node in nodes if base._declared(node)&needed]
        loaded={child.id for node in selected for child in ast.walk(node)
            if isinstance(child,ast.Name) and isinstance(child.ctx,ast.Load)}
        expanded=needed|(loaded&set(declarations))
        if expanded==needed:break
        needed=expanded
    if needed&{'normalize_api_observations','audit_accounting','_orders','_envelope'}:_fail()
    dependencies={}
    for node in selected:
        for child in ast.walk(node):
            if isinstance(child,ast.Attribute) and isinstance(child.value,ast.Name):
                root=child.value.id
                if root in ('native','collector'):_fail()
                if root in ('c','e','metrics'):
                    dependencies[root+'.'+child.attr]=(root,child.attr)
    class Dependencies(ast.NodeTransformer):
        def visit_Attribute(self,node):
            if isinstance(node.value,ast.Name) and node.value.id in ('c','e','metrics'):
                return ast.copy_location(ast.Subscript(value=ast.Name(id='callbacks',ctx=ast.Load()),
                    slice=ast.Constant(node.value.id+'.'+node.attr),ctx=node.ctx),node)
            return self.generic_visit(node)
    selected=Dependencies().visit(ast.Module(body=deepcopy(selected),type_ignores=[]))
    ast.fix_missing_locations(selected)
    header=('from collections import Counter\nfrom datetime import datetime, timedelta, timezone\n'
        'from decimal import Context, Decimal, localcontext\nfrom fractions import Fraction\n'
        'import hashlib\nimport re\nfrom zoneinfo import ZoneInfo\n'
        'SOURCE_SHA256 = '+repr(ACCOUNTING_SHA256)+'\n'
        'PARENT_SUMMARY_JSON = '+repr(summary_raw.decode('ascii'))+'\n'
        'PARENT_CONFIG_JSON = '+repr(config_raw.decode('ascii'))+'\n'
        'COMPACT_JSON = '+repr(compact_raw.decode('ascii'))+'\n'
        'PARENT_BINDING_JSON = '+repr(_wire(binding).decode('ascii'))+'\n'
        'CALLBACK_NAMES = '+repr(tuple(sorted(dependencies)))+'\n')
    body=ast.unparse(selected)
    outer=('def audit_compact(summary_raw,index_raw,config_raw,calendar_raw,source_calendar_raw,*,binding,chunks,compact_raw,'
        'expected_compact_sha256,expected_normalizer_source_sha256,callbacks):\n'
        '    if type(callbacks) is not dict or set(callbacks)!=set(CALLBACK_NAMES):\n'
        '        raise ValueError("accounting callback contract refused")\n'
        +''.join('    '+line+'\n' for line in body.splitlines())
        +'    return audit_compact(summary_raw,index_raw,config_raw,calendar_raw,source_calendar_raw,binding=binding,chunks=chunks,'
        'compact_raw=compact_raw,expected_compact_sha256=expected_compact_sha256,'
        'expected_normalizer_source_sha256=expected_normalizer_source_sha256)\n')
    helper=(header+outer).encode('utf-8')
    if not 0<len(helper)<=60000:_fail()
    compile(ast.parse(helper),HELPER,'exec')
    return helper,dependencies


BOUND=r'''
def _accounting_bound(self):
    if (type(ACCOUNTING_RUNTIME_SHA256) is not str or ACCOUNTING_RUNTIME_SHA256!=self._accounting_helper_hash
            or accounting_runtime.SOURCE_SHA256!=self._accounting_source_hash
            or accounting_runtime.audit_compact is not _ACCOUNTING_REPLAY
            or _ACCOUNTING_REPLAY is not self._accounting_replay_function
            or accounting_runtime.PARENT_SUMMARY_JSON!=READER_CONFIG['summary_json']
            or accounting_runtime.PARENT_CONFIG_JSON!=READER_CONFIG['parent_config_json']
            or accounting_runtime.COMPACT_JSON!=self._accounting_compact_json
            or hashlib.sha256(accounting_runtime.PARENT_BINDING_JSON.encode('ascii')).hexdigest()!=self._accounting_parent_hash
            or type(ACCOUNTING_CALLBACKS) is not dict or set(ACCOUNTING_CALLBACKS)!=set(self._accounting_callbacks)
            or any(ACCOUNTING_CALLBACKS[key] is not value for key,value in self._accounting_callbacks.items())
            or tuple(accounting_runtime.CALLBACK_NAMES)!=self._accounting_callback_names):
        raise ValueError('accounting implementation binding drift refused')
    cfg=READER_CONFIG['accounting']
    if (type(cfg) is not dict or set(cfg)!={'compact_json','compact_sha256','compact_bytes','normalizer_source_sha256','helper_sha256','parent_binding_sha256'}
            or cfg['compact_json']!=self._accounting_compact_json or cfg['compact_sha256']!=self._accounting_compact_hash
            or cfg['compact_bytes']!=len(self._accounting_compact_json.encode('ascii'))
            or cfg['normalizer_source_sha256']!=self._accounting_source_hash
            or cfg['helper_sha256']!=self._accounting_helper_hash
            or cfg['parent_binding_sha256']!=self._accounting_parent_hash
            or hashlib.sha256(cfg['compact_json'].encode('ascii')).hexdigest()!=self._accounting_compact_hash
            or hashlib.sha256(json.dumps(READER_CONFIG['binding'],sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')).hexdigest()!=self._accounting_parent_hash):
        raise ValueError('accounting compact binding drift refused')
'''

AUDIT=r'''
def _audit(self):
    if self._called or self._disabled:return
    self._called=True
    try:
        self._bound();binding=READER_CONFIG['binding']
        index=self._read('index',{'key':READER_CONFIG['index_key'],**binding['envelopes']['index']},2*1024*1024)
        self._report['index_hash_verified']=True
        summary=READER_CONFIG['summary_json'].encode('ascii');config=READER_CONFIG['parent_config_json'].encode('ascii')
        original=self._effect('public_calendar',lambda:core.CALENDAR_JSON.encode('utf-8'))
        calendar=self._effect('public_calendar',lambda:core.exact_json(R_comparison_calendar()).encode('utf-8'))
        plan=self._effect('framing',lambda:C_chunk_replay_plan(summary,index,config,calendar,original,binding=binding))
        chunks=[]
        for descriptor in plan:
            chunks.append(self._read('chunk',{'key':descriptor['key'],'bytes':descriptor['bytes'],'sha256':descriptor['sha256']},512*1024))
        replay={'key':READER_CONFIG['index_key'],'sha256':binding['envelopes']['index']['sha256'],
            'bytes':len(index),'journal_total_bytes':sum(map(len,chunks)),'maximum_records':300000,'maximum_chunks':1024,'maximum_parse_calls':900150}
        self._claim('replay',replay)
        report=self._effect('replay',lambda:C_replay_chunks(summary,index,config,calendar,original,binding=binding,chunks=chunks))
        self._report.update(completed_read_replay=True,completion_report=report)
        scope={**replay,'compact_sha256':self._accounting_compact_hash,'compact_bytes':len(self._accounting_compact_json.encode('ascii')),
            'normalizer_source_sha256':self._accounting_source_hash,'helper_sha256':self._accounting_helper_hash,
            'parent_binding_sha256':self._accounting_parent_hash}
        self._claim('accounting',scope)
        accounting_report=self._effect('accounting',lambda:_ACCOUNTING_REPLAY(summary,index,config,calendar,original,
            binding=binding,chunks=chunks,compact_raw=self._accounting_compact_json.encode('ascii'),
            expected_compact_sha256=self._accounting_compact_hash,expected_normalizer_source_sha256=self._accounting_source_hash,
            callbacks=ACCOUNTING_CALLBACKS))
        self._report.update(status='completed_supplied_accounting_comparison',phase='complete',
            completed_accounting_processing=True,accounting_report=accounting_report,
            supplied_evidence_accounting_reconciled=accounting_report['supplied_evidence_accounting_reconciled'] is True)
    except KeyboardInterrupt:
        self._error('cancelled','KeyboardInterrupt')
        raise KeyboardInterrupt('CMP28 accounting reader cancelled') from None
    except Exception as error:
        kind=next((item.__name__ for item in (C_CompletionRefusal,E_EvidenceError,ValueError,TypeError,KeyError,AttributeError,OverflowError) if type(error) is item),'Exception')
        self._error('private_read_or_accounting_refused',kind)
    except BaseException:
        self._error('fatal_or_uncertain','BaseException')
        raise ReaderStopped('CMP28 accounting reader stopped') from None
'''


def build_native_accounting_reader(*,public_sources,binding,summary_raw,config_raw,index_key,operation_id,git_head,
                                  compact_raw,expected_compact_sha256,expected_normalizer_source_sha256):
    """Return {main.py, one pure helper} plus body-free build metadata only.

    Supplied parent/compact bytes require a fresh caller-side private processing
    claim before this pure function is invoked. This function opens nothing.
    """
    try:
        if type(public_sources) is not dict or set(public_sources)!=set(PINS):_fail()
        for name,digest in PINS.items():
            raw=public_sources[name]
            if type(raw) is not bytes or not 0<len(raw)<=131072 or _sha(raw)!=digest:_fail()
        if (not isinstance(operation_id,str) or not operation_id.startswith('TPR-CMP28-RESULT-READER-ACCOUNTING-')
                or type(binding) is not dict or binding.get('project_id')!=37650980
                or type(compact_raw) is not bytes or not 0<len(compact_raw)<=MAX_COMPACT_BYTES
                or _sha(compact_raw)!=expected_compact_sha256 or expected_normalizer_source_sha256!=ACCOUNTING_SHA256):_fail()
        source,old_report=base.build_native_result_reader(public_sources={name:public_sources[name] for name in base.PINS},
            binding=binding,summary_raw=summary_raw,config_raw=config_raw,index_key=index_key,operation_id=operation_id,git_head=git_head)
        original=public_sources[CALENDAR_PATH]
        accounting._compact(compact_raw,expected_compact_sha256,binding,original,expected_normalizer_source_sha256)
        helper,dependencies=_helper(public_sources[ACCOUNTING_PATH],summary_raw,config_raw,compact_raw,binding);helper_hash=_sha(helper)
        tree=ast.parse(source);main=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='Main')
        assignments={name:node for node in tree.body if isinstance(node,ast.Assign) for name in base._declared(node)}
        cfg=json.loads(ast.literal_eval(assignments['READER_CONFIG_JSON'].value))
        cfg['schema']='tpr-cmp28-native-accounting-reader-config-v1'
        cfg['public_source_hashes']=dict(PINS)
        parent_hash=_sha(_wire(binding))
        cfg['accounting']={'compact_json':compact_raw.decode('ascii'),'compact_sha256':expected_compact_sha256,
            'compact_bytes':len(compact_raw),'normalizer_source_sha256':ACCOUNTING_SHA256,'helper_sha256':helper_hash,
            'parent_binding_sha256':parent_hash}
        config_text=_wire(cfg).decode('ascii');config_hash=_sha(config_text.encode('ascii'))
        # Plain metadata literals live in the same pure helper. Compute its
        # COMPLETE file hash before assembling the configuration that binds it;
        # no source-hash cycle or encoded executable body is introduced.
        frame=deepcopy(cfg);frame['summary_json']=None;frame['parent_config_json']=None
        frame['accounting']['compact_json']=None;frame['binding']=None
        expression=ast.parse(repr(frame),mode='eval').body
        for key,value in zip(expression.keys,expression.values):
            if key.value in ('summary_json','parent_config_json'):
                field={'summary_json':'PARENT_SUMMARY_JSON','parent_config_json':'PARENT_CONFIG_JSON'}[key.value]
                expression.values[expression.keys.index(key)]=ast.Attribute(value=ast.Name(id='accounting_runtime',ctx=ast.Load()),attr=field,ctx=ast.Load())
            elif key.value=='binding':
                expression.values[expression.keys.index(key)]=ast.Call(func=ast.Attribute(value=ast.Name(id='json',ctx=ast.Load()),attr='loads',ctx=ast.Load()),
                    args=[ast.Attribute(value=ast.Name(id='accounting_runtime',ctx=ast.Load()),attr='PARENT_BINDING_JSON',ctx=ast.Load())],keywords=[])
            elif key.value=='accounting':
                for child in value.keys:
                    if child.value=='compact_json':
                        value.values[value.keys.index(child)]=ast.Attribute(value=ast.Name(id='accounting_runtime',ctx=ast.Load()),attr='COMPACT_JSON',ctx=ast.Load())
        assignments['READER_CONFIG_JSON'].value=ast.Call(func=ast.Attribute(value=ast.Name(id='json',ctx=ast.Load()),attr='dumps',ctx=ast.Load()),
            args=[expression],keywords=[ast.keyword(arg='sort_keys',value=ast.Constant(True)),
                ast.keyword(arg='separators',value=ast.Tuple(elts=[ast.Constant(','),ast.Constant(':')],ctx=ast.Load())),
                ast.keyword(arg='ensure_ascii',value=ast.Constant(True)),ast.keyword(arg='allow_nan',value=ast.Constant(False))])
        assignments['READER_CONFIG_SHA256'].value=ast.Constant(config_hash)
        methods={node.name:node for node in main.body if isinstance(node,ast.FunctionDef)}
        init=methods['initialize'];position=next(i for i,node in enumerate(init.body) if isinstance(node,ast.Try))
        for node in ast.walk(init):
            if isinstance(node,ast.Name) and isinstance(node.ctx,ast.Load):
                node.id={'READER_CONFIG_JSON':'_FROZEN_READER_CONFIG_JSON',
                    'READER_CONFIG_SHA256':'_FROZEN_READER_CONFIG_SHA256'}.get(node.id,node.id)
        setup=ast.parse("self._accounting_compact_json=frozen['accounting']['compact_json']\n"
            "self._accounting_compact_hash=frozen['accounting']['compact_sha256']\n"
            "self._accounting_source_hash=frozen['accounting']['normalizer_source_sha256']\n"
            "self._accounting_helper_hash=frozen['accounting']['helper_sha256']\n"
            "self._accounting_parent_hash=frozen['accounting']['parent_binding_sha256']\n"
            "self._accounting_callback_names=tuple(ACCOUNTING_CALLBACK_NAMES)\n"
            "self._accounting_replay_function=_ACCOUNTING_REPLAY\n"
            "self._accounting_callbacks=dict(ACCOUNTING_CALLBACKS)\n"
            "self._report.update(completed_accounting_processing=False,accounting_report=None,supplied_evidence_accounting_reconciled=False,"
            "compact_sha256=self._accounting_compact_hash,normalizer_source_sha256=self._accounting_source_hash,"
            "helper_sha256=self._accounting_helper_hash,raw_api_pages_revalidated_in_child=False,"
            "exact_journal_to_event_id_mapping_proven=False,original_strategy_intent_verified=False,"
            "moo_order_type_verified=False,cancellation_policy_verified=False,slippage_model_verified=False)\n").body
        init.body[position:position]=setup
        methods['_config_bound'].body.append(ast.parse('self._accounting_bound()').body[0])
        main.body.append(ast.parse(BOUND).body[0])
        main.body[main.body.index(methods['_audit'])]=ast.parse(AUDIT).body[0]
        for node in ast.walk(methods['_claim']):
            if isinstance(node,ast.Constant) and node.value==1026:node.value=1027
        for node in ast.walk(methods['_effect']):
            if isinstance(node,ast.Constant) and node.value==300050:node.value=900150
        for node in ast.walk(main):
            if isinstance(node,ast.Constant) and type(node.value) is str:
                node.value=node.value.replace('tpr-cmp28/native-private-result-reader','tpr-cmp28/native-accounting-result-reader')
                node.value=node.value.replace('tpr-cmp28-native-private-result-reader-v1','tpr-cmp28-native-accounting-result-reader-v1')
                node.value=node.value.replace('tpr-cmp28/result-reader/','tpr-cmp28/accounting-result-reader/')
                node.value=node.value.replace('CMP28_PRIVATE_RESULT_READER_RESULT ','CMP28_ACCOUNTING_READER_RESULT ')
        callback_names=tuple(sorted(dependencies));entries=[]
        existing=set().union(*(base._declared(node) for node in tree.body))
        for key,(alias,name) in sorted(dependencies.items()):
            target={'c':'C_','e':'E_','metrics':'M_'}[alias]+name
            if target not in existing:
                path={'c':'comparison_20261028_completion.py','e':'extended_evidence.py','metrics':'extended_metrics.py'}[alias]
                nodes,names=base._select(public_sources[PREFIX+path],{name})
                extra=ast.parse(base._render(nodes,{name:target},{})).body;tree.body.extend(extra);existing.add(target)
            if key=='e.parse_json':target='_reader_parse'
            elif key=='c._sha':target='_reader_hash'
            entries.append(repr(key)+':'+target)
        tree.body.insert(1,ast.parse('import comparison_20261028_accounting_runtime as accounting_runtime').body[0])
        prelude=ast.parse('_FROZEN_READER_CONFIG_JSON = READER_CONFIG_JSON\n_FROZEN_READER_CONFIG_SHA256 = READER_CONFIG_SHA256\n'
            '_ACCOUNTING_REPLAY = accounting_runtime.audit_compact\n'
            'ACCOUNTING_RUNTIME_SHA256 = '+repr(helper_hash)+'\n'
            'ACCOUNTING_CALLBACK_NAMES = '+repr(callback_names)+'\n'
            'ACCOUNTING_CALLBACKS = {'+','.join(entries)+'}\n').body
        tree.body.extend(prelude)
        removed_docstrings=0
        class Documentation(ast.NodeTransformer):
            def generic_visit(self,node):
                nonlocal removed_docstrings
                node=super().generic_visit(node)
                if isinstance(node,(ast.Module,ast.ClassDef,ast.FunctionDef)) and node.body:
                    first=node.body[0]
                    if isinstance(first,ast.Expr) and isinstance(first.value,ast.Constant) and type(first.value.value) is str:
                        node.body.pop(0);removed_docstrings+=1
                        if not node.body:node.body=[ast.Pass()]
                return node
        tree=Documentation().visit(tree);ast.fix_missing_locations(tree)
        emitted=(ast.unparse(tree)+'\n').encode('utf-8')
        if not 0<len(emitted)<=60000:_fail()
        compile(ast.parse(emitted),'main.py','exec')
        report=json.loads(old_report);report.update(schema='tpr-cmp28-native-accounting-reader-build-v1',
            main_bytes=len(emitted),main_sha256=_sha(emitted),config_sha256=config_hash,
            public_source_hashes=dict(PINS),base_reader_sha256=BASE_SHA256,accounting_source_sha256=ACCOUNTING_SHA256,
            helper_name=HELPER,helper_bytes=len(helper),helper_sha256=helper_hash,compact_sha256=expected_compact_sha256,
            compact_bytes=len(compact_raw),parent_binding_sha256=parent_hash,main_only_cloud_edit=False,
            new_helper_files=1,preserve_other_cloud_files=23,max_cloud_files_after_install=25,max_claims=1027,
            max_parse_calls=900150,private_processing_claims=2,raw_api_pages_revalidated_in_child=False,
            exact_journal_to_event_id_mapping_proven=False,original_strategy_intent_verified=False,
            moo_order_type_verified=False,cancellation_policy_verified=False,slippage_model_verified=False,
            runtime_self_source_authentication_proven=False,generated_main_docstrings_removed=removed_docstrings,
            helper_contains_plain_own_aggregate_metadata=True)
        return {'main.py':emitted,HELPER:helper},_wire(report)+b'\n'
    except AccountingReaderBuildRefusal:raise
    except (ValueError,TypeError,KeyError,UnicodeError,SyntaxError,OverflowError,StopIteration):_fail()
